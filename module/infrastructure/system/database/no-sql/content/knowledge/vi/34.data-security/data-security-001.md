# Mô hình đe dọa cho ứng dụng, database và công cụ quản trị

Một ứng dụng có thể dùng NoSQL để lưu đơn hàng, hồ sơ người dùng và sự kiện. API đã bật HTTPS, database yêu cầu mật khẩu, nhưng một nhân viên vận hành vẫn có thể dùng công cụ quản trị với quyền quá rộng; một endpoint tìm kiếm có thể diễn giải input người dùng thành toán tử truy vấn; hoặc một bản sao lưu dữ liệu khách hàng có thể bị đọc từ một bucket cấu hình sai. Mỗi ví dụ nằm ở **một ranh giới tin cậy khác nhau**, nên chỉ “bật xác thực database” không giải quyết hết rủi ro.

**Threat modeling (mô hình hóa đe dọa)** là cách phân tích có cấu trúc nhằm nhận diện tài sản cần bảo vệ, tác nhân và giả định, đường đi của dữ liệu, điểm vượt ranh giới tin cậy, tình huống bị lạm dụng, tác động và biện pháp kiểm soát. Bài học thuộc chương **Bảo mật dữ liệu** của module **Database No SQL**, tập trung vào ba lớp phải được xem xét cùng nhau:

1. **Ứng dụng**: client, API, logic phân quyền, session/token, input, cache và các dịch vụ tích hợp.
2. **Database NoSQL**: collections/tables/keys, cluster/network, xác thực, quyền, replica, encryption, backup, CDC và vận hành.
3. **Công cụ quản trị**: console, CLI, dashboard, query editor, migration script, tài khoản kỹ thuật, thiết bị quản trị và workflow cấp quyền.

Mục tiêu không phải liệt kê mọi cuộc tấn công có thể tưởng tượng. Mục tiêu là tạo được một **mô hình có thể kiểm tra, ưu tiên sửa chữa và cập nhật khi kiến trúc thay đổi**.

Những tên hệ thống, roles, đường dẫn, JSON và mã Java trong bài là **ví dụ giả định để học**, không phải cấu hình bảo mật hoàn chỉnh hay mô tả mặc định của một nhà cung cấp. Chi tiết quyền và tính năng phải được xác minh trên sản phẩm, phiên bản và deployment thực tế.

## 1. Phân biệt tài sản, đe dọa, lỗ hổng và rủi ro

Bốn khái niệm thường bị gộp nhầm:

- **Asset (tài sản)**: dữ liệu, chức năng, khóa mã hóa, danh tính hoặc tính sẵn sàng cần bảo vệ.
- **Threat (đe dọa)**: tình huống/tác nhân có thể gây hại, như người ngoài đọc đơn hàng của tenant khác.
- **Vulnerability/weakness (điểm yếu)**: điều kiện làm sự kiện xấu có thể xảy ra, như server tin `tenantId` từ request mà không kiểm tra.
- **Risk (rủi ro)**: khả năng và mức tác động của đe dọa trong bối cảnh kiểm soát hiện tại.

Ví dụ:

~~~text
Asset: đơn hàng của tenant T2.
Threat: user của tenant T1 đọc dữ liệu T2.
Weakness: API dùng tenantId do client tự truyền.
Attack path: client -> API -> NoSQL query không ràng buộc principal.
Impact: rò rỉ PII, vi phạm hợp đồng, mất lòng tin.
Control: server-side tenant scope + database permission boundary.
Evidence: integration test cross-tenant + audit logs.
~~~

Một database port có thể nằm trong mạng riêng nhưng API vẫn có lỗi phân quyền. Đánh giá rủi ro phải xem **toàn bộ đường truy cập**, không chỉ firewall.

## 2. CIA triad: ba mục tiêu bảo mật dữ liệu

| Thuộc tính | Ý nghĩa | Ví dụ trong NoSQL |
|---|---|---|
| **Confidentiality (bí mật)** | Người không được phép không xem được dữ liệu | PII không lộ qua API, backup, logs |
| **Integrity (toàn vẹn)** | Dữ liệu không bị sửa trái phép hoặc sai lệch | Giá, số dư, quyền và trạng thái đơn hàng đúng |
| **Availability (sẵn sàng)** | Hệ phục vụ đúng lúc cần | Không bị cạn connection, CPU hoặc read capacity |

Thực tế còn cần:

- **Authenticity**: biết yêu cầu thực sự đến từ ai/hệ nào.
- **Accountability**: có thể quy hành động tới danh tính được phép, với audit đáng tin.
- **Non-repudiation** khi có yêu cầu nghiệp vụ/pháp lý cụ thể.
- **Privacy**: thu thập, lưu, xuất và xóa dữ liệu theo mục đích/quy định.
- **Safety/correctness**: không dùng dữ liệu cũ/trái quyền để quyết định nghiệp vụ.

Một chức năng backup chỉ phục hồi được dữ liệu nhưng để backup public-read có thể tăng availability mà phá confidentiality. Cần đánh giá đồng thời các thuộc tính.

## 3. Xác định phạm vi trước khi vẽ sơ đồ

Một bài threat model nên có **scope có ranh giới**:

~~~text
System: Orders and Inventory Service
Entry points: public API, worker queue, admin console
Stores: document DB, cache, event log, object storage backups
Environments: production region A, DR region B
Data: orders, addresses, inventory, payment references
Actors: customer, support operator, DBA, CI/CD, service accounts
Out of scope: payment provider internal systems (assumed external)
Review trigger: new admin export, database migration, new region
~~~

Ghi rõ cái gì nằm ngoài phạm vi và **giả định nào cần kiểm chứng**. Ví dụ “cloud provider bảo vệ physical hosts” không có nghĩa provider chịu trách nhiệm cho IAM policy hoặc ứng dụng dùng khóa sai.

Một scope quá rộng (“bảo mật tất cả NoSQL”) dễ tạo danh sách chung chung; scope quá hẹp (“chỉ collection Orders”) sẽ bỏ lỡ backup/console/ETL vốn có quyền đọc cùng dữ liệu.

## 4. Tài sản cần bảo vệ: không chỉ là database records

Nhóm assets thường gặp:

| Nhóm | Tài sản | Mức ảnh hưởng điển hình |
|---|---|---|
| Dữ liệu khách hàng | Địa chỉ, email, lịch sử mua, thông tin hồ sơ | Privacy, compliance, uy tín |
| Dữ liệu nghiệp vụ | Giá, stock, order state, ledger references | Integrity, doanh thu |
| Thông tin xác thực | API keys, JWT signing keys, client certificates | Chiếm quyền nhiều hệ |
| Secrets nội bộ | DB passwords, connection strings, encryption keys | Truy cập database/bản sao |
| Administrative capability | Export all tenants, delete collection, change IAM | Blast radius rất lớn |
| Backup/archive | Snapshots, CDC logs, data lake exports | Lộ dữ liệu lịch sử |
| Metadata | Tên collection, schema, indices, hostnames, topology | Hỗ trợ khám phá hệ |
| Availability | API p99, DB read/write capacity, failover | Gián đoạn dịch vụ |
| Audit evidence | Access logs, admin activity trails, immutable events | Khó điều tra sau incident |
| Deployment pipeline | Migration scripts, images, package registry credentials | Tampering/supply chain |

**Khóa bí mật và quyền quản trị** thường quan trọng hơn một bảng đơn lẻ, vì bị lộ có thể mở đường tới nhiều collections, tenants, môi trường và backups.

## 5. Phân loại dữ liệu theo độ nhạy và mục đích

Trước khi đánh giá threats, lập data inventory:

- Public: mô tả sản phẩm công khai.
- Internal: cấu hình vận hành, metrics đã loại PII.
- Confidential: địa chỉ, số điện thoại, chi tiết Order.
- Highly restricted: secrets, security tokens, tài liệu định danh hoặc dữ liệu được quy định đặc biệt.
- Operational state: stock, trạng thái thanh toán, idempotency outcomes.

Các nhãn này là **ví dụ**, tổ chức cần quy định chính sách riêng. Với mỗi loại, ghi:

1. Nguồn có thẩm quyền.
2. Ai được đọc/sửa/xóa/xuất.
3. Retention và deletion policy.
4. Các bản sao: cache, index, analytics, backup, logs.
5. Encryption/key ownership.
6. Các region/tenants được phép.
7. Hậu quả khi dữ liệu bị mất, sai hoặc xuất hiện ở nơi không được phép.

Không thể mô hình hóa đầy đủ việc lộ PII nếu không biết PII còn nằm trong search index, report CSV hoặc crash dump.

## 6. Tác nhân: người ngoài, người trong và tài khoản máy

Một threat model cần xét những actor có thể tương tác với hệ, không mặc định tất cả là kẻ tấn công:

- Khách chưa đăng nhập.
- Người dùng đã đăng nhập với quyền hạn thấp.
- Chủ tenant A muốn xem dữ liệu tenant B.
- Nhân viên hỗ trợ được phép tra cứu một số hồ sơ.
- DBA/SRE có quyền vận hành cluster.
- CI/CD bot và migration runner.
- CDC connector/search-indexing worker.
- Dịch vụ đối tác gọi webhook.
- Một workload đã bị compromise.
- Nhân viên/nhà thầu rời tổ chức nhưng credential chưa thu hồi.
- Kẻ ngoài đã lấy được token, API key hoặc laptop quản trị.

Mô hình cần chứa cả **lạm dụng quyền hợp lệ** và **mất danh tính**. Một admin có quyền export dữ liệu toàn bộ tenants có thể gây tác động lớn dù không cần khai thác bug ở database.

## 7. Data Flow Diagram (DFD): vẽ đường đi của dữ liệu

Một sơ đồ tổng quát:

~~~mermaid
flowchart LR
    USER["Khách hàng"] -->|HTTPS| GW["API Gateway"]
    GW --> APP["Order API"]
    APP -->|NoSQL driver + TLS| DB[("Orders NoSQL")]
    APP --> CACHE[("Cache")]
    DB --> CDC["CDC / Outbox"]
    CDC --> BROKER[("Event log")]
    BROKER --> INDEX[("Search / reporting")]
    DB --> BACKUP[("Backup storage")]
    ADMIN["Nhân viên quản trị"] --> CONSOLE["Admin portal"]
    CONSOLE --> APP
    DBA["DBA / Ops"] --> JIT["Privileged access gateway"]
    JIT --> DB
    CICD["Migration pipeline"] --> DB
~~~

Đây là **data-flow view**, không phải khẳng định tất cả các kết nối trong hệ được phép. Với mỗi mũi tên, hỏi: Ai gọi? Dùng credential nào? Dữ liệu nào đi qua? Có xác thực/cấp quyền/mã hóa/audit không? Có thể đi chiều ngược hoặc export ra file không?

DFD tốt nhất nên có **tên trust boundary** và inventory endpoints. Đừng chỉ vẽ mạng vật lý mà bỏ qua authorization tại API.

## 8. Trust boundary: nơi dữ liệu đổi mức tin cậy

Các ranh giới thường gặp:

~~~text
[Untrusted internet]
      |
      | Boundary A: public ingress / authentication
      v
[API workload]
      |
      | Boundary B: service identity / DB permissions
      v
[NoSQL production]
      |
      | Boundary C: CDC / derived data publication
      v
[Search, analytics, object storage]

[Admin workstation]
      |
      | Boundary D: privileged access / approval / audit
      v
[Admin tools -> DB or privileged API]
~~~

Quan trọng:

- Network private không tự là **authorization boundary**.
- TLS bảo vệ dữ liệu trên đường truyền, không chứng minh người gọi **được phép** đọc một document cụ thể.
- Service identity mạnh nhưng app có thể query sai tenant.
- Backup encryption không bảo đảm bucket ACL và decrypt permission đúng.
- Admin portal có RBAC nhưng query editor có thể bỏ qua API row-level checks.

Mỗi boundary cần một hoặc nhiều **control và bằng chứng kiểm tra**.

## 9. Câu hỏi mô hình hóa cho một luồng dữ liệu

Với luồng `GET /orders/O1001`, ghi:

1. Ai tạo request và authentication được thiết lập ở đâu?
2. Identity/tenant từ token đã được verify và chuyển qua các services thế nào?
3. Object ID từ request có thể trỏ sang tenant khác không?
4. API có giới hạn read scope server-side?
5. NoSQL credential của service có được phép đọc toàn bộ collection không?
6. Input được chuyển thành filter theo kiểu dữ liệu nào?
7. Có cached version theo tenant/user scope không?
8. Query/index/log chứa PII ở đâu?
9. Response có che fields không được phép?
10. Audit có chỉ ra access bất thường mà không lộ dữ liệu không?

Đây là các **giả thuyết phải xác minh qua code/config/test**, không phải câu trả lời tự động “đã có JWT nên an toàn”.

## 10. STRIDE: một khung phân tích theo loại đe dọa

| STRIDE | Câu hỏi | Ví dụ trong hệ NoSQL |
|---|---|---|
| **S — Spoofing** | Có thể giả mạo danh tính không? | Stolen service token kết nối DB |
| **T — Tampering** | Có thể sửa dữ liệu trái phép không? | Admin script update sai tenant |
| **R — Repudiation** | Có thể phủ nhận hành động vì thiếu bằng chứng? | Export dữ liệu nhưng audit thiếu actor |
| **I — Information disclosure** | Dữ liệu bí mật có lộ không? | Bucket backup public/read IAM quá rộng |
| **D — Denial of service** | Có thể làm cạn tài nguyên không? | Unbounded NoSQL scan, hot partition |
| **E — Elevation of privilege** | Có thể lấy quyền cao hơn không? | App credential có quyền quản trị |

STRIDE là **công cụ gợi ý**, không phải danh sách kiểm tra hoàn chỉnh. Một threat có thể thuộc nhiều nhóm. Ví dụ stolen admin token vừa là spoofing, vừa mở đường tới information disclosure và tampering.

Không nhất thiết gán một điểm STRIDE cho từng database record; nên đánh giá **process, data store, data flow và trust boundary** nơi tấn công có đường thực tế.

## 11. Một threat scenario phải đủ cụ thể để kiểm tra

Mẫu viết:

~~~text
ID: TM-012
Asset: orders của tenant B
Entry point: GET /orders/{id}
Actor: authenticated tenant A user
Precondition: biết hoặc đoán được một order ID khác tenant
Threat: API truy vấn theo orderId mà không ràng buộc tenant
Impact: information disclosure
Existing controls: JWT verification, TLS
Missing control: record-level authorization query
Proposed control: server-derived tenant scope + deny-by-default
Evidence: integration test T1 cannot read T2 records
Owner: Order API team
Priority: high
Residual risk: admin path vẫn cần xem xét riêng
~~~

Một threat model có giá trị khi **mỗi ưu tiên có owner, control và verification**. “Kẻ xấu có thể tấn công database” không đủ cụ thể để viết test hoặc đặt một quyền IAM.

## 12. Risk prioritization: đánh giá likelihood, impact và điều kiện tồn tại

Một cách làm tương đối:

| Impact \ Likelihood | Thấp | Trung bình | Cao |
|---|---|---|---|
| **Thấp** | Theo dõi | Xử lý theo kế hoạch | Ưu tiên xử lý |
| **Trung bình** | Theo dõi/giảm | Ưu tiên | Khẩn |
| **Cao** | Ưu tiên | Khẩn | Khẩn |

Đây là thang định tính, không thay chính sách rủi ro của tổ chức. Khi chấm, xem:

- Internet-facing hay chỉ nội bộ có kiểm soát.
- Có sẵn credential/mạng nào phải compromise trước không?
- Dữ liệu lộ/sửa được một bản hay toàn bộ tenants?
- Có audit/alerts/detection thực sự không?
- Có backup/khôi phục được không?
- Tác động lên người dùng, hợp đồng, tài chính, privacy.
- Khả năng xảy ra từ lỗi vận hành vô ý bên cạnh lạm dụng có chủ đích.
- Biện pháp hiện hữu đã **được kiểm thử** hay chỉ có trên sơ đồ.

**Rủi ro còn lại (residual risk)** sau kiểm soát có thể khác rủi ro ban đầu. Ghi rõ quyết định chấp nhận rủi ro có người phê duyệt và ngày xem lại; không biến “low risk” thành lý do bỏ theo dõi.

## 13. Threat modeling phía ứng dụng: xác thực khác phân quyền

**Authentication (xác thực)** trả lời “ai đang gọi?”. **Authorization (phân quyền)** trả lời “danh tính đó có được làm hành động này trên tài nguyên này không?”.

Ví dụ API đã xác minh JWT của user `u42` thuộc tenant `t01`. Điều đó không cho phép user đó đọc mọi Order của `t01`, càng không cho phép xem Orders của tenant `t02`. Có thể cần thêm owner/customer ID, role hoặc relationship.

Một lỗi thường gặp:

~~~text
Authenticated user -> GET /orders/O999
Order O999 thuộc tenant khác.
API query chỉ theo orderId.
DB trả record thành công.
~~~

Chỗ thiếu là **object-level authorization**, dù authentication và TLS đều hoạt động.

Biện pháp:

- Lấy user identity/tenant từ **trusted verified identity context**, không tin body/query của client.
- Quy tắc quyền theo action và resource: read, update, export, delete.
- Kiểm tra ownership/tenant boundary server-side.
- Deny by default và tách support/admin privileges.
- Policy tests cho cả resources được và không được phép.
- Quyền DB của app nên nhỏ nhất có thể để giảm blast radius.

## 14. Multi-tenant isolation: nguy cơ xuyên tenant trong NoSQL

NoSQL thường tối ưu truy vấn theo partition key. Nếu data model đặt tenant làm một phần khóa, cần **bảo đảm ứng dụng luôn ràng buộc tenant đó**.

Ví dụ:

~~~text
PK = TENANT#t01
SK = ORDER#O1001
~~~

Truy vấn dùng `PK` do **server dựng từ identity** phù hợp hơn việc nhận partition key tùy ý từ client.

Ví dụ Java ở mức minh họa:

~~~java
public record PrincipalContext(
    String userId,
    String tenantId,
    java.util.Set<String> roles
) {}

public interface OrderRepository {
    OrderView findForTenant(String tenantId, String orderId);
}

public OrderView getOrder(
        PrincipalContext principal, String orderId) {
    OrderView order = repository.findForTenant(
        principal.tenantId(), orderId);
    if (order == null) {
        throw new NotFoundException();
    }
    authorization.requireCanReadOrder(principal, order);
    return order.toPublicView();
}
~~~

Đây là **pseudocode**, chưa khai báo toàn bộ classes và dependencies. Query có tenant filter là một tầng; **resource-level policy** vẫn cần nếu user cùng tenant không được đọc mọi Order.

Kiểm thử: tenant A đọc ID thuộc tenant B; staff có quyền một tenant; đổi tenant context sau login; cache hit; search và batch export. Một API dùng đúng tenant key nhưng có công cụ quản trị bỏ qua policy vẫn có lỗ hổng khác.

## 15. NoSQL query injection: dữ liệu bị diễn giải thành truy vấn

**NoSQL injection** xuất hiện khi dữ liệu không tin cậy được ghép hoặc diễn giải thành cấu trúc query mà không kiểm soát kiểu, tên trường hoặc toán tử.

Các tình huống:

- Input string được parse thành object filter.
- Client kiểm soát operator thay vì chỉ value.
- API nhận arbitrary aggregation stages hoặc search DSL.
- Table/collection/sort field lấy trực tiếp từ request.
- Query ghép chuỗi không dùng bound parameters.
- User-supplied structure có thể thay đổi điều kiện phân quyền.

Biện pháp không phải blacklist vài ký tự. **Server quyết định query shape; client chỉ được đưa các giá trị có type và allowlist đã xác minh.**

### 15.1. MongoDB: không nhận raw filter toàn quyền

Anti-pattern:

~~~javascript
// Không kiểm soát fields, operators và tenant constraints.
db.orders.find(clientSuppliedFilter);
~~~

Thay bằng:

~~~javascript
const trustedTenantId = authContext.tenantId;
const status = validateEnum(
  request.status, ["PENDING", "CONFIRMED", "CANCELLED"]);

db.orders.find({
  tenantId: trustedTenantId,
  status: status
});
~~~

`validateEnum` là pseudocode. Với Java/Spring Data, bind typed values, chỉ cho phép sort/filter fields từ allowlist và gắn tenant filter tại server. Kiểm tra cả updates/deletes, không chỉ GET.

### 15.2. Các NoSQL khác cũng có query-structure risk

- DynamoDB: SDK expression values/names cần được dựng đúng; client không được tự chọn attribute tùy tiện.
- Cassandra/CQL: prepared/bound statements cho values; table/column identifiers đến từ allowlist.
- Elasticsearch/OpenSearch: giới hạn DSL, script, aggregation, sort, fan-out và tenant filters.
- Redis: dựng command/key từ cấu trúc server-owned; không dùng input làm command tùy ý.
- Graph/document queries: giới hạn traversal depth, procedures và resource consumption.

Cần chống cả **injection, authorization bypass và resource exhaustion**.

## 16. Mass assignment: không cho user sửa field server-owned

Một document có:

~~~json
{
  "orderId": "O1001",
  "tenantId": "t01",
  "status": "PENDING",
  "discountPercent": 0,
  "approvedBy": null,
  "totalMinor": 240000
}
~~~

Nếu API PATCH áp trực tiếp mọi trường request body, user có thể ảnh hưởng `tenantId`, `approvedBy` hoặc `totalMinor`.

Controls:

1. Request DTO chỉ chứa fields được sửa.
2. Dựng update expression ở server.
3. Check quyền theo action.
4. Conditional version/state check.
5. Tính total/price từ nguồn server-trusted.
6. Audit khi sửa trường nhạy cảm.
7. Không hỗ trợ arbitrary update operators từ client.

**NoSQL schema linh hoạt không có nghĩa API chấp nhận update object không kiểm soát.**

## 17. Resource exhaustion: truy vấn hợp lệ vẫn có thể gây DoS

Một request hợp lệ về cú pháp có thể rất đắt:

- Regex/filters tốn CPU.
- Full scan không giới hạn.
- Aggregation cardinality cao.
- Sort thiếu index.
- Pagination offset sâu.
- Fan-out qua nhiều partitions/shards.
- Graph traversal depth lớn.
- Export nhiều triệu rows trong HTTP request.

~~~text
User được phép xem report.
API nhận tùy ý filters và date range.
Một query scan toàn dataset.
100 concurrent requests gây DB read queue tăng.
Checkout p99 tăng dù user không có DB credentials.
~~~

Biện pháp: cost budget, query templates, scan/time/bytes limits, rate + concurrency quotas theo tenant/user, pagination, async report jobs và reporting store tách OLTP.

**Giới hạn request/s là chưa đủ nếu một request cực nặng.** Cần giới hạn work và concurrency.

## 18. Cache và search: rò dữ liệu qua đường phụ

Một API có authorization đúng nhưng cache key thiếu tenant:

~~~text
cache key = "order:O1001"
~~~

Nếu object ID không globally unique hoặc cached view phụ thuộc quyền, tenant khác có thể đọc nhầm dữ liệu. Search index có thể lưu private fields dù API nguồn không trả chúng.

Các threat scenarios:

- Cache key thiếu tenant/user/permission variant.
- CDN public cache giữ authenticated response.
- Search query thiếu tenant filter.
- Search index chứa internal notes/PII hoặc soft-deleted records.
- Cache invalidation tới muộn sau revoke.
- CDC replay hồi sinh dữ liệu đã xóa.

Controls: private/public namespaces riêng, request-time authorization, projection minimization, tenant filtering trên **mọi** read path, versioned invalidation và deletion propagation, integration tests cho cache hit/search.

## 19. Session, token và credentials phía ứng dụng

Các câu hỏi:

- Token có được verify issuer, audience, signature, expiry và scopes?
- Session cookies có cấu hình bảo vệ phù hợp?
- Refresh/revocation/logout được thực hiện ra sao?
- API keys có rotation, expiry, owner và least privilege?
- Secrets có bị ghi vào logs/traces/source code không?
- Có kiểm soát login abuse/credential stuffing?
- Service-to-service identity/mTLS có được áp theo threat model?
- Privileged session có yêu cầu MFA/step-up auth không?
- User thuộc nhiều organizations được chọn tenant context hợp lệ ra sao?

Không lấy user-provided `X-Tenant-Id` làm bằng chứng quyền nếu chưa gắn nó vào danh tính được verify. Xác thực thành công không phải cấp quyền truy cập tất cả dữ liệu.

## 20. Webhook và async worker cũng là entry points

~~~mermaid
flowchart LR
    PARTNER["External partner"] -->|Webhook| IN["Webhook handler"]
    IN --> Q[("Queue/Event log")]
    Q --> W["Worker"]
    W --> DB[("NoSQL source")]
~~~

Hỏi:

- Webhook có signature/timestamp/replay-window validation?
- Event IDs có dedup/idempotency?
- Payload có schema/version validation?
- Worker có tin tenant từ event không được xác thực?
- Queue topic/consumer ACL có giới hạn ai gửi/đọc?
- DLQ có chứa PII và được bảo vệ?
- Retries có thể làm duplicate effects?
- Worker có DB credential quá rộng?

**Queue nội bộ không tự biến payload thành đáng tin.** Mỗi boundary cần validation và authorization tương ứng.

## 21. SSRF qua import hoặc remote fetch

Một ứng dụng cho phép import data từ URL hoặc tải ảnh bên ngoài có thể bị lợi dụng để server gọi tới tài nguyên không mong muốn.

Threat modeling:

- Destination URL/domain có allowlist theo mục đích?
- Scheme, redirect, DNS và IP ranges được kiểm soát?
- Có thể gọi internal admin services hoặc cloud metadata endpoints không?
- Egress firewall/proxy có hạn chế đích?
- Credentials có bị gửi nhầm kèm request?
- Download bytes/time/redirect count có giới hạn?
- Logs có ghi destination đã redacted phục vụ điều tra?

Một địa chỉ URL hợp lệ về cú pháp không đủ chứng minh nó an toàn. Workload nắm DB admin credentials không nên được dùng làm remote fetch proxy tùy ý.

## 22. Driver/SDK và service identity: đường vào database

Driver thường sở hữu connection string, credentials, TLS settings, topology discovery và quyền gửi operations. Khi app bị compromise, quyền của credential driver trở thành một phần **blast radius**.

Các tình huống:

- App credential được phép đọc/ghi mọi collections.
- Connection string chứa password bị log hoặc commit vào repository.
- TLS validation bị vô hiệu hóa.
- Driver kết nối endpoint ngoài mạng/region dự kiến.
- Credential dùng nhiều năm không rotate.
- Microservice có quyền tạo DB users hoặc drop collection.
- Driver dependency cũ hoặc không kiểm soát nguồn gốc.
- SDK retries khiến overload hoặc hành vi ghi lặp.

Controls:

- Workload identity/secrets manager, rotation và revoke.
- TLS + certificate validation, cluster member authentication.
- Tách credentials cho read, write, migration, admin.
- Network egress restrictions/private endpoint khi phù hợp.
- Quyền tối thiểu trên action + database/collection/keyspace.
- Dependency inventory, patch policy và pin/verify packages.
- Pool/retry/query deadline và logging an toàn.

**Một credential cho phép kết nối không đồng nghĩa nó cần quyền quản trị hệ database.** Xác thực và quyền vận hành phải tách nhau.

## 23. Threat modeling trực tiếp phía NoSQL server

Một bảng theo entry point:

| Entry point | Threat | Controls |
|---|---|---|
| DB listener | Truy cập trực tiếp không được phép | Private networking, firewall, TLS, DB auth |
| Authentication | Credential leak/brute force | Rotation, secret policy, audit |
| Database roles | Privilege escalation hoặc quyền quá rộng | Least privilege, periodic review |
| Collections/tables | Sửa/xóa/xuất dữ liệu | Per-action authorization, backup, audit |
| Admin commands | Drop/alter/disable security controls | JIT, approval, separation of duties |
| Replication endpoints | Node giả/traffic bị nghe lén | Member auth, encrypted channels |
| Disk/snapshots | Đọc raw data ngoài phạm vi | At-rest encryption, key control |
| Backups/logs | Dữ liệu lịch sử bị xuất | Restricted IAM, retention, access logs |
| Extensions/plugins | Code/chức năng không tin cậy | Hardening, provenance, patching |
| Availability | Hot partitions, disk exhaustion, overload | Quotas, rate limits, capacity |

**Tên role không cho biết chính xác quyền thực tế.** Phải kiểm tra permissions ở mức instance, database, schema, keyspace, table, collection và command mà engine hỗ trợ.

## 24. Least privilege và separation of duties

Một ma trận vai trò minh họa:

~~~text
order-api:
  read/write Orders cần thiết theo logic app
  no user management, no drop DB

report-worker:
  read reporting projection
  no operational transaction writes

migration-runner:
  schema/index permissions chỉ trong cửa sổ cấp phép

support-operator:
  filtered admin API, không raw DB shell mặc định

dba:
  privileged admin operations
  JIT + audited session + approval for destructive changes
~~~

Controls:

1. Mỗi service có identity riêng, không chia sẻ superuser.
2. Prod và non-prod tách accounts/credentials và policy.
3. Read-only jobs không được có quyền delete/update.
4. Migration credentials có TTL/JIT hoặc pipeline-only usage.
5. Backup accounts chỉ cần chức năng backup, không đồng nghĩa quyền restore/drop.
6. Sensitive changes có two-person review khi impact phù hợp.
7. Role assignment được review/thu hồi định kỳ.
8. Có quy trình revoke khẩn cấp khi một workload bị compromise.

Nếu database không có native row-level authorization, **đừng giả định tenant filter ở app tương đương DB-enforced isolation**. Cần bổ sung data layout, testing và phân vùng quyền ở các tầng có thể enforce.

## 25. Network segmentation và zero-trust assumptions

Một mô hình mạng:

~~~mermaid
flowchart TD
    INTERNET["Internet"] --> GATEWAY["WAF / API Gateway"]
    GATEWAY --> APP["Application subnet"]
    APP --> DB["Private NoSQL endpoint"]
    OPS["Admin workstation"] --> ACCESS["JIT privileged gateway"]
    ACCESS --> DB
    DB --> BACKUP["Restricted backup endpoint"]
    DB --> CDC["Restricted CDC endpoint"]
~~~

Cần đặt câu hỏi:

- Database có public listener/allow-all IP rule nào không?
- App subnet nào thực sự cần outbound DB access?
- DB có nhận kết nối từ developer laptop không?
- Môi trường staging có thể truy cập prod DB không?
- Cross-region replication được mã hóa/xác thực thế nào?
- Network policy có enforce east-west traffic không?
- VPN/bastion có MFA và session recording theo policy không?
- Các đường backup/CDC có bị mở rộng không cần thiết?
- Có egress restrictions cho workload bị compromise không?

“Ở trong VPC” không đủ nếu quá nhiều workloads có thể kết nối và mọi workload dùng chung DB password. Network segmentation giúp **giảm phạm vi xâm nhập**, nhưng không thay authentication và record-level authorization.

## 26. Encryption at rest, in transit và quản trị khóa

Ba vấn đề khác nhau:

1. **In transit**: TLS bảo vệ kết nối giữa client, app, DB, replicas, backup/CDC endpoints theo hỗ trợ.
2. **At rest**: encryption cho disk, snapshot, object storage và các bản sao.
3. **Key management**: ai có thể dùng/decrypt/rotate/revoke keys và lưu logs về thao tác đó.

Threat scenarios:

- Dữ liệu được mã hóa nhưng service account có quyền đọc plaintext toàn bộ.
- Backup bucket dùng một key mà quá nhiều roles có thể decrypt.
- App log plaintext PII trước khi encryption.
- Khóa mã hóa được lưu cạnh ciphertext trong source repo.
- Key rotation không kiểm thử và làm mất khả năng restore backup.
- Dữ liệu đi qua một connector không dùng TLS.
- Mã hóa trường khiến ứng dụng tưởng nó vẫn có thể query/index cùng semantics.

**Encryption không thay authorization**; một người có quyền hợp lệ để gọi decrypt vẫn có thể lạm dụng quyền đó. Threat model cần ghi cả đường đi **của khóa** và permission policy đối với KMS/HSM/vault, không chỉ checkbox “encrypted”.

### 26.1. Field-level encryption và searchable data

Mã hóa ở tầng trường có thể giảm tác động nếu DB storage bị lộ, nhưng việc query/sort/aggregate trên ciphertext phụ thuộc scheme và engine. Không giả định có thể mã hóa deterministic mọi PII mà không ảnh hưởng privacy leakage, key rotation hoặc query behavior.

Cần nêu:

- Threat nào muốn giảm: DBA thấy plaintext, storage theft, backup theft?
- Ai giữ keys: app, client hay KMS?
- Metadata nào vẫn lộ: lengths, access frequency, deterministic equality?
- Quy trình rotate/re-encrypt và migrate fields.
- Có cần search tokenization hoặc projection đã loại dữ liệu nhạy cảm không?

## 27. Secrets và credential lifecycle

Threat model cần theo **toàn vòng đời**, không chỉ nơi lưu:

~~~text
Create -> Distribute -> Use -> Rotate -> Revoke -> Audit -> Destroy
~~~

Danh sách kiểm soát:

- Không commit secrets vào git/images/test fixtures.
- Không đưa password/token vào URL logs, metrics labels hoặc error responses.
- Dùng secret manager/managed identity thay hardcode.
- Process/container chỉ thấy secret thực sự cần.
- Secret không được truyền sang công cụ quản trị không tin cậy.
- Có TTL/rotation/revocation và diễn tập xoay khóa.
- Khi credential bị lộ, biết nơi đang dùng và thứ tự thu hồi.
- Phân quyền đọc secret tách khỏi phân quyền quản trị database.
- Secrets dùng cho backup/DR có scope/retention riêng.
- Service accounts sau khi decommission được thu hồi và audit.

Một secret “đã được lưu trong vault” vẫn có rủi ro nếu mọi pod trong cluster đều được cấp quyền đọc nó.

## 28. Backup, snapshot, restore: rủi ro không biến mất ở bản sao

Một hệ NoSQL có thể bảo vệ primary database nhưng để snapshot ở object storage với IAM lỏng hơn.

Đường dữ liệu:

~~~mermaid
flowchart LR
    DB[("Production NoSQL")] --> B["Backup job"]
    B --> S[("Snapshot/object storage")]
    S --> R["Restore job"]
    R --> DR[("DR / test environment")]
~~~

Câu hỏi:

- Ai có thể tạo, đọc, download, copy, xóa và restore backup?
- Có mã hóa, key separation và key lifecycle không?
- Backup cross-region/cross-account được cấp quyền thế nào?
- Có versioning/immutability/object lock theo policy?
- Có kiểm tra restore định kỳ và RPO/RTO?
- Restore vào môi trường test có thể làm lộ PII không?
- Backup retention phù hợp deletion/legal hold không?
- Access logs cho download/copy/decrypt có được giám sát?
- Một ransomware actor có thể xóa cả primary và backups không?
- API hay admin tool có thể tạo public signed URL quá dài không?

**Backup là một database copy chứa nhiều dữ liệu lịch sử**, nên đôi khi cần quyền bảo vệ còn chặt hơn read API hàng ngày. Threat modeling phải gồm cả restore vào môi trường mới, không chỉ lúc lưu snapshot.

## 29. CDC, event log, search và warehouse: dữ liệu có thêm điểm lộ

CDC/event pipeline có thể nhân dữ liệu nhạy cảm sang nhiều systems:

~~~text
NoSQL source
  -> CDC connector
  -> broker topic
  -> search projection
  -> warehouse
  -> dashboard / exported reports
~~~

Các threats:

- Event envelope chứa PII không cần thiết.
- Topic ACL cho quá nhiều consumers.
- Consumer logs/DLQ chứa raw payload.
- Snapshot connector chạy với credential quá quyền.
- Search index cho phép query tất cả tenant records.
- Warehouse analyst role đọc field bị hạn chế.
- Dữ liệu đã xóa trong source nhưng vẫn còn tại projection/archive.
- Rebuild từ snapshot cũ hồi sinh deleted record.
- CDC lag làm các chính sách quyền/xóa có hiệu lực chậm.

Controls:

1. Data minimization và field masking tại publisher/consumer.
2. Topic ACL và encryption/integrity protection.
3. Separate identities per consumer.
4. Schema/version validation và idempotent event handling.
5. Retention/deletion propagation policy.
6. Restrict DLQ/error log access.
7. Lineage: biết dữ liệu đã được sao chép đi đâu.
8. Reconcile quyền/xóa trước khi công bố projection mới.

**Dữ liệu dẫn xuất không tự an toàn hơn nguồn**; nó thường dễ bị quên trong audit, retention và incident response.

## 30. Log, metrics, traces: telemetry cũng có thể là data leak

Một request chứa order ID, email, address hoặc database connection string. Nếu toàn bộ query/request được ghi vào logs, hệ telemetry có thể trở thành kênh xuất dữ liệu.

Nguy cơ:

- Raw query với parameters chứa PII.
- HTTP Authorization header hoặc cookies bị log.
- Database exceptions in ra secret/URI.
- Metrics labels chứa user ID hoặc token.
- Traces có query payload/raw document.
- Logs từ admin export nằm trên một hệ bên ngoài không có hạn mức.
- Dùng debug profiling lâu dài có overhead và data exposure.
- Người có quyền đọc observability logs rộng hơn quyền xem Orders.

Controls:

- Structured logs với allowlisted fields và redaction.
- Template routes/normalized query shapes thay raw parameter values.
- Không lưu secrets trong metric labels.
- RBAC cho log/tracing systems.
- Retention và deletion policy, access audit.
- Sampling/rate limits để tránh DoS từ logging.
- Security events/privileged access audit có bảo vệ riêng, không trộn hoàn toàn với debug logs.

Telemetry phải giúp điều tra sự cố **mà không tạo thêm bản sao bí mật không kiểm soát**.

## 31. Tính toàn vẹn của dữ liệu và các thao tác đồng thời

Threat modeling không chỉ xét attacker đọc dữ liệu; sửa sai dữ liệu có thể làm mất tiền hoặc sai nghiệp vụ.

Ví dụ hai requests đồng thời giữ chiếc ghế cuối:

~~~text
Source: availableSeats = 1

Request A reads 1.
Request B reads 1.
A writes 0 and confirms.
B writes 0 and confirms.

Two confirmations for one seat.
~~~

Đây có thể là **race condition** chứ không phải hacker; nhưng attacker có thể cố tình khuếch đại. Controls:

- Atomic conditional write/compare-and-set ở nguồn.
- Transaction hoặc reserve protocol phù hợp engine và partition boundary.
- Stable idempotency key cho business intent.
- Authoritative validation tại commit, không dùng cache stale để cấp hàng.
- Audit/quarantine cho unknown write outcomes.
- Kiểm tra state machine transitions.
- Safe retries khi SDK timeout.

**Integrity và concurrency control** là thành phần bảo mật: một API cho phép gửi hàng trăm requests song song có thể phá invariant dù mọi requests đều authenticated.

## 32. Data retention và right-to-delete trong mô hình đe dọa

Một dữ liệu có thể nằm trong:

- Document source, replica.
- Search index, cache.
- Event log/CDC.
- Warehouse, analytics extracts.
- Backup snapshots.
- Report CSVs, temporary files.
- Debug logs, tracing spans.
- Developer test data.

Một yêu cầu xóa/hạn chế xử lý có thể không đồng nghĩa phải xóa ngay khỏi mọi backup theo mọi luật; chính sách phụ thuộc nghĩa vụ pháp lý, giữ bằng chứng và kỹ thuật. Nhưng **phải có retention/deletion contract rõ cho từng bản sao**, không chỉ xóa document ở source.

Threat scenario: một người bị xóa hồ sơ trong source, sau đó operator rebuild search từ snapshot cũ và vô tình đưa hồ sơ trở lại public search. Cần tombstone/deletion suppression, policy check ở pipeline và verification sau rebuild.

## 33. Managed NoSQL và shared responsibility

Với managed DB, provider có thể quản lý phần cứng, một số patches, availability primitives và encryption defaults; **khách hàng vẫn có trách nhiệm** về IAM, query authorization, tenant isolation, data lifecycle, backups tùy cấu hình, network policy và app logic.

Threat modeling cần ghi:

- Ai cấu hình network endpoint và public access?
- Ai quản lý credentials/IAM, grants và KMS keys?
- Ai kiểm soát backup destination và retention?
- Ai quản trị query/index cost và resource limits?
- Có provider audit logs/service events gì?
- Provider có cung cấp điểm kiểm soát OS/storage hay không?
- Phần nào không quan sát/kiểm soát được, cần bù từ app/SDK?
- Incident escalation cho provider support ra sao?

Không viện dẫn “đây là dịch vụ cloud nên an toàn theo mặc định”. **Cấu hình và quyền sử dụng thực tế vẫn quyết định attack surface**.

## 34. Công cụ quản trị là một attack surface riêng

Một hệ có thể triển khai API với quyền tối thiểu nhưng DBA/superuser dùng công cụ có quyền rất rộng:

~~~mermaid
flowchart LR
    STAFF["Support / DBA"] --> PORTAL["Admin web portal"]
    PORTAL --> PRIV["Privileged API"]
    PRIV --> DB[("Production NoSQL")]
    DBA["DBA laptop"] --> BASTION["Access gateway"]
    BASTION --> DB
    CICD["CI/CD migration job"] --> DB
    VENDOR["Third-party support tool"] --> PORTAL
~~~

Các điểm cần mô hình hóa:

- Người dùng của console là ai, có authentication/MFA không?
- Console truy vấn qua **business API có authorization** hay raw DB credentials?
- Từ console có thể chạy batch update, delete, export, user management?
- Có quyền mặc định toàn bộ tenants/regions không?
- Công cụ có lưu query history, clipboard, exports, screenshots?
- Session bao lâu thì hết hạn, ai có thể dùng máy đang mở?
- Có audit và phê duyệt cho thao tác phá hủy?
- Third-party console/plugin có quyền gì?
- Cơ chế break-glass có bảo vệ và được kiểm tra không?

**Admin tool không an toàn chỉ vì người sử dụng là nhân viên nội bộ.** Credentials bị lộ, thao tác nhầm và lạm dụng quyền là ba loại rủi ro độc lập.

## 35. Admin portal: phân quyền chức năng và phạm vi dữ liệu

Ví dụ một nhân viên support chỉ nên xem Order của tenant mà họ đang được phân công, không được tải toàn bộ dữ liệu.

RBAC/ABAC cần phân biệt:

| Quyền | Mô tả | Đề xuất |
|---|---|---|
| View one order | Tra cứu Order đã được phép | Scope theo tenant/case |
| Search orders | Tìm trong phạm vi công việc | Filter server-side, rate limit |
| Export list | Tải hàng loạt | Approval, data minimization, audit |
| Change order status | Sửa trạng thái nghiệp vụ | Business command + invariant |
| Delete personal data | Thực thi deletion workflow | Specialized controlled flow |
| View secrets | Truy cập credentials | Không nằm trong support portal |
| Database schema change | Index/collection/keyspace | Migration pipeline role |
| Grant permissions | Cấp quyền admin | Separate identity governance |

Một quyền `ADMIN=true` duy nhất thường quá rộng. **Capability-based permissions** và resource constraints giúp giảm blast radius khi một tài khoản bị compromise.

Các chính sách phải enforce **ở backend**; việc ẩn nút trên UI chỉ thay đổi trải nghiệm, không chặn HTTP request trực tiếp.

## 36. Query console/DB shell: rủi ro từ quyền chạy truy vấn tùy ý

Query editors rất hữu dụng để chẩn đoán nhưng cũng nguy hiểm vì người dùng có thể:

- Đọc nhiều collections/tenants mà họ không cần.
- Chạy full scans, joins/traversals hoặc aggregates tốn tài nguyên.
- Thực hiện bulk updates/deletes trên phạm vi lớn.
- Thay đổi indexes/roles hoặc server configuration.
- Export raw PII ra máy cá nhân.
- Chạy script bị copy từ tài liệu bên ngoài không đáng tin.
- Bỏ qua validation/business invariants của application layer.

Controls:

1. Mặc định read-only cho truy vấn hỗ trợ.
2. Scope vào reporting/replica thích hợp, không primary cho scans nặng.
3. Timeouts, limit rows, bytes scanned, concurrency quotas.
4. Tách quyền DDL/destructive operations khỏi quyền read.
5. Query template/allowlist cho support users nếu có thể.
6. Approval hoặc JIT elevation cho thao tác rủi ro.
7. Log actor, reason, scope, thời gian và kết quả theo mức độ không lộ PII.
8. Có rollback/backups/snapshot point và dry-run khi engine hỗ trợ.
9. Không xem GUI extension/plugin là đáng tin mặc định.
10. Không để query editor lưu credentials plaintext trên shared workstation.

**Công cụ quản trị có thể vượt qua tất cả guardrails của API**, nên phải áp dụng kiểm soát tương đương hoặc mạnh hơn ở tầng DB, access gateway và process.

## 37. Just-in-time (JIT) privilege và break-glass

**JIT access** cấp quyền cao trong thời gian ngắn, theo một mục đích cụ thể, có audit.

Một workflow minh họa:

~~~text
Operator requests prod read-only diagnostic access
  -> verify identity + MFA/step-up
  -> select ticket/incident and scope
  -> approval or automated policy decision
  -> short-lived credential/session
  -> session audit + action controls
  -> automatic revoke on expiration
~~~

Thao tác destructive có thể yêu cầu cấp quyền riêng, thời gian ngắn hơn và xác nhận phạm vi.

**Break-glass** là đường truy cập khẩn cấp khi hệ xác thực/phê duyệt thông thường không dùng được. Nó phải:

- Có số người/credential rất hạn chế.
- Được bảo vệ bằng biện pháp độc lập, lưu kho đúng chính sách.
- Ghi/giám sát mọi lần sử dụng.
- Tự động thông báo và post-use review.
- Có quy trình revoke/rotate sau incident.
- Được diễn tập để biết hoạt động khi khẩn cấp.

Không biến break-glass thành tài khoản admin dùng thường xuyên cho tiện.

## 38. Admin export: đường rò dữ liệu quy mô lớn

Export là một hành động có rủi ro cao hơn point lookup vì có thể tạo **bản sao toàn bộ dữ liệu nhạy cảm**.

Data flow:

~~~text
Admin requests report
  -> server verifies role, tenant scope and reason
  -> durable background export job
  -> data source / reporting projection
  -> temporary encrypted artifact store
  -> short-lived authorized download
  -> audit / cleanup at retention deadline
~~~

Threat scenarios:

- User có quyền xem 1 Order nhưng export API cho toàn tenant.
- Query filter thiếu server-side tenant predicate.
- Download URL công khai hoặc tồn tại quá lâu.
- File CSV chứa PII không được che.
- Export lưu vào thư mục local/shared drive lâu ngày.
- Một user chạy nhiều exports gây DoS.
- Report job status có IDOR nên lộ artifact của người khác.
- Query chạy trên DB primary làm checkout chậm.
- Artifact bị backup/replicate ngoài retention mong muốn.

Controls: per-export authorization, quota, bound filters/time ranges, approval khi cần, encryption, short-lived URLs, file audit, tenant-scoped job IDs, expiration/cleanup, restricted object storage IAM.

Không đồng nhất “đã ẩn field trên UI” với “export không chứa field đó”. Export serializer phải chọn fields được phép độc lập.

## 39. Bulk update/delete: thao tác sai cũng là threat

Một operator có thể vô ý chạy update với filter quá rộng:

~~~text
Intended:
  update only tenant=t01 AND status=PENDING

Mistake:
  filter only status=PENDING

Impact:
  many tenants' records changed.
~~~

Threat model phải xét **human error**, không chỉ kẻ tấn công.

Biện pháp:

- Scoped query helpers gắn tenant từ authorized context.
- Require explicit target count preview và dry-run nếu phù hợp.
- Giới hạn số records mỗi batch, rate, deadline.
- Two-person approval đối với thay đổi quy mô lớn.
- Conditional version/state transition checks.
- Backup/restore hoặc compensating plan.
- Immutable audit của actor/filter scope/change ticket.
- Tách staging/test khỏi production, dễ thấy môi trường đang thao tác.
- Có stop/pause control và cảnh báo bất thường.

Tránh dựa vào confirmation dialog kiểu “Bạn chắc không?” làm biện pháp duy nhất; một người có thể bấm nhầm khi thiếu phân quyền và giới hạn phạm vi.

## 40. Thiết bị quản trị và đường vào production

Một admin laptop hoặc workstation có thể là trust boundary yếu nhất dù database được mã hóa và đặt trong private subnet.

Threat scenarios:

- Laptop mất nhưng lưu connection profiles/credentials.
- Browser session hoặc SSO token bị chiếm.
- Clipboard chứa dữ liệu PII hoặc secret.
- Truy cập console từ thiết bị không được quản trị.
- Browser extension đọc nội dung admin page.
- SSH private key được chia sẻ giữa nhân viên.
- Truy cập prod qua mạng ngoài dự kiến.
- Screen recording/export lưu vào nơi không kiểm soát.
- Người nghỉ việc vẫn còn quyền cloud/DB.

Controls: managed device posture, disk encryption, phishing-resistant MFA khi phù hợp, short-lived credentials, device-bound access, bastion/privileged access gateway, session logging, conditional access, automatic offboarding, regular access review.

**Không lưu credentials production lâu dài trong file cấu hình IDE/GUI client** nếu có thể dùng JIT/session credential.

## 41. CI/CD và migration runner: chuỗi cung ứng dữ liệu

Một migration script có thể thay indexes, sửa schema, backfill dữ liệu và cấp quyền. Nếu pipeline hoặc artifact bị thay đổi, attacker có thể ảnh hưởng trực tiếp tới DB.

Các câu hỏi:

- Ai được merge/approve migration code?
- CI runner nào có network access và secrets prod?
- Build artifacts có provenance/signature/hash?
- Dependencies/packages được pin, scan và cập nhật?
- Có bảo vệ branch và reviews?
- Migration có idempotent/rollback/stop conditions?
- Quyền schema migration có được cấp chỉ khi chạy?
- Job có giới hạn concurrency và connection pool không?
- Migration logs có ghi dữ liệu/credentials?
- Có environment/tenant scope, dry-run và planned maintenance window?

Control defense-in-depth:

~~~text
Protected source branch
  -> code review
  -> signed/reproducible artifact where feasible
  -> restricted deployment identity
  -> scoped JIT migration grant
  -> rate-limited migration
  -> audit + post-deploy verification
  -> revoke elevation
~~~

Một bản migration được review vẫn có thể lỗi logic, nên cần rollback plan và hạn mức; một pipeline đủ mạnh nhưng cho mọi developer sửa workflow file không có bảo vệ vẫn có supply-chain risk.

## 42. Quản trị đa môi trường và cấu hình nhầm

Các sự cố phổ biến:

- Dùng production connection string trong staging.
- Đẩy backup prod vào môi trường test không mã hóa.
- Copy dữ liệu PII sang laptop để debug.
- Chạy seed/reset script nhầm cluster.
- Role staging có trust policy truy cập prod.
- Dashboard admin không hiển thị rõ environment và region.
- Dùng một encryption key/secret chung giữa dev và prod.
- Mở firewall tạm thời rồi quên đóng lại.

Controls:

- Tách accounts/projects/VPC/credentials theo môi trường.
- Mark rõ production UI/CLI context; confirmation dựa trên identity/target.
- Default deny các đường cross-environment.
- Dùng synthetic/anonymous data trong test.
- CI approval cho production changes.
- Tự động kiểm tra IaC drift và policy misconfiguration.
- Expiry tự động cho temporary access rules.
- Audit mọi restore/copy data production sang nơi khác.

Một **mô hình đe dọa thực tế** phải bao gồm đường vận hành “ngoài giờ” và môi trường DR/test, nơi quyền và dữ liệu thường được copy với mức kiểm soát thấp hơn.

## 43. Third-party admin tools và plugins

Một công cụ dashboard, database GUI hoặc SaaS data exploration có thể yêu cầu DB credentials hoặc API token.

Cần đánh giá:

- Nó cần read-only hay có write/admin capabilities?
- Data/queries gửi qua vendor backend không?
- Có local agent chạy với quyền OS/container nào?
- Có lưu mật khẩu, query history, exports và screenshots?
- Có SSO/SCIM/offboarding và audit?
- Có giới hạn region, retention và subprocessor theo hợp đồng?
- Nếu vendor bị compromise, blast radius tới database nào?
- Có thể cấp temporary scoped credential thay full admin password không?
- Có network egress restrictions và review supply chain không?

Không cài ngẫu nhiên một GUI extension vào workstation có credential prod mà không xét quyền của extension. Với công cụ không cần raw data, ưu tiên **read-only API/reporting projection** thay cho kết nối trực tiếp nguồn.

## 44. Audit trail: ghi đủ để quy trách nhiệm, không ghi lộ data

Một sự kiện audit cho thao tác quản trị có thể là:

~~~json
{
  "timestamp": "2026-11-14T10:00:12Z",
  "actorType": "human",
  "actorRef": "operator-opaque-42",
  "action": "EXPORT_ORDERS",
  "resourceType": "orders",
  "scope": {"tenant": "t01", "dateRangeDays": 30},
  "ticketRef": "INC-204",
  "decision": "ALLOWED",
  "jobRef": "export-job-119",
  "result": "COMPLETED"
}
~~~

Nên ghi:

- Who/what identity và role/session.
- Action + target scope và môi trường.
- Authorization decision, approval/ticket.
- Thời gian và kết quả.
- Correlation/trace/job IDs.
- Đơn vị giám sát có thể phát hiện bất thường.

Không ghi raw PII hoặc secrets vào audit payload nếu không cần. Đặt **append-only/tamper-resistant access policy** và retention phù hợp để user bị điều tra không thể tự xóa dấu vết dễ dàng.

Audit log chỉ hữu ích nếu được **kiểm tra, alert và có ownership**, không chỉ “có bật”.

## 45. Phát hiện sự kiện đáng ngờ qua metrics, logs và alerts

Tín hiệu có thể giám sát:

- DB login failures/unknown source IP.
- Tăng đột biến quyền được cấp hoặc credential rotation failures.
- Admin access ngoài giờ thông thường theo chính sách.
- Export data volume bất thường.
- Full-scan/read capacity tăng sau một admin query.
- Massive update/delete count trên nhiều tenants.
- Backup download/copy/decrypt bất thường.
- API cross-tenant denials và enumeration patterns.
- NoSQL query execution timeouts và expensive query shapes.
- Audit logging bị tắt hoặc logs ngừng gửi.
- CDC/search xuất hiện deleted record trở lại.
- New public endpoint/firewall rule/IAM policy drift.

Một alert tốt có **dữ liệu đủ để điều tra, owner, severity và runbook**. Không lấy một anomaly signal đơn lẻ làm bằng chứng actor độc hại; có thể là maintenance hợp lệ. Xây escalation theo tác động và đối chiếu với ticket, approvals và deployments.

## 46. MongoDB: mô hình hóa collection, roles và đường quản trị

Một hệ MongoDB giả định:

~~~text
order-api -> MongoDB Orders
support-api -> filtered business API
DBA -> privileged gateway -> MongoDB admin
CDC connector -> change stream -> search index
Backup agent -> encrypted snapshot storage
~~~

Những câu hỏi:

- Connection string có chứa credentials trong logs/container env dumps?
- App DB user được cấp role ở database/collection nào, có quyền admin/DDL không?
- MongoDB authentication và TLS/member authentication được cấu hình phù hợp?
- Collection có dữ liệu của nhiều tenants nhưng app filter chỉ dựa vào request body?
- Aggregation pipeline cho client tự chọn stages/operator nào?
- Profiler/slow query logs có chứa PII?
- Change stream consumer dùng credentials và resume/access scope gì?
- Backup snapshot có quyền download/decrypt hạn chế không?
- Admin dùng shell có thể chạy bulk update/drop và được audit thế nào?
- Query scan có bị giới hạn bởi maxTimeMS, rate/concurrency và dedicated reporting path khi phù hợp?

Một mẫu **quyết định phân quyền**:

~~~text
order-api role:
  allowed: read/write required collections
  denied: role management, cluster admin, unrelated databases

support staff:
  allowed: filtered API actions in assigned tenant/case
  denied: raw database credentials

migration pipeline:
  allowed: scoped schema/index changes during approved window
~~~

Cơ chế RBAC thực tế phụ thuộc deployment/roles được hỗ trợ; nếu muốn cô lập từng tenant ở mức DB, cần đánh giá schema/data placement hoặc tách database/cluster khi business yêu cầu, không giả định mọi MongoDB role tự hỗ trợ row-level filtering.

## 47. DynamoDB: IAM policy, item identity và Streams

DynamoDB dùng cơ chế IAM/resource policies và những tính năng theo dịch vụ/tài khoản. Threat model cần xét:

- API role được phép thao tác những tables/indices nào?
- Conditions có giới hạn partition keys/tenants theo thiết kế thực tế không?
- Application có thể tự đưa key của tenant khác vào `GetItem/Query` không?
- GSI queries có mang đủ tenant constraints?
- Có quyền scan/export toàn table không cần thiết?
- Backup/export-to-object-storage được cấp IAM gì?
- Streams consumers có quyền đọc toàn stream dù chỉ cần một subset?
- KMS key policy và quyền decrypt có nằm ngoài scope DB role không?
- SDK retries khi throttled có gây DoS hoặc duplicate business outcomes?
- IAM condition logic đã được test với cả chính sách allow và deny chưa?

Ví dụ access pattern:

~~~text
Table Orders:
  PK = TENANT#t01
  SK = ORDER#O1001

API:
  builds PK from verified principal tenant.
  does not accept arbitrary PK from request.
  checks action and record-level policy.
~~~

Nếu muốn **enforce tenant isolation ở cả IAM**, phải xác minh API/actions/keys được policy condition hỗ trợ và cách thực thi với GSIs, transactions, scans hoặc batch operations. Không coi một điều kiện chung là đủ cho mọi DynamoDB call.

## 48. Cassandra/ScyllaDB: keyspace roles, CQL và operations

Threat scenarios:

- Service account có quyền trên mọi keyspaces.
- CQL query builder nối strings thay vì bind values.
- Quản trị viên chạy thao tác schema/repair ở nhầm cluster.
- Client sử dụng consistency level không đạt business contract.
- Network access cho phép host nội bộ không liên quan kết nối cluster.
- JMX/management API hoặc metrics endpoints bị lộ.
- Snapshot/SSTable backup không mã hóa hoặc bị copy ra ngoài.
- Tombstone/large partition scans bị lạm dụng làm DoS.
- CDC/repair pipelines có quyền rộng và thiếu retention/deletion controls.

Controls:

- RBAC/permissions theo khả năng của engine và version.
- Prepared/bound CQL statements cho values; identifier allowlist.
- Client-to-node/node-to-node authentication/TLS phù hợp.
- Network ACL/firewall, operator access gateway.
- Repair/compaction/backup quotas và audit.
- Bảo vệ snapshots và filesystem access.
- Partition-aware query limits và capacity monitoring.
- Mô hình quyền riêng cho application, repair agent, backup job và DBA.

**Không dùng “đã có Cassandra consistency level LOCAL_QUORUM” như một câu trả lời cho authorization.** Consistency và security là hai trục độc lập.

## 49. Redis: ACL, cache data scope và command surface

Redis có thể dùng làm cache, session store, queue hoặc database tùy thiết kế. Threat model phải **xác định vai trò thực sự của Redis**.

Các rủi ro:

- Redis listener có thể được truy cập ngoài trusted network.
- App credential được phép thực thi commands không cần.
- Keys chứa PII/token và bị liệt kê qua admin/debug tools.
- Key naming thiếu tenant scope gây cross-tenant leakage.
- Quá nhiều data làm eviction các session/critical keys.
- Một lệnh tốn CPU hoặc scan toàn keyspace gây DoS.
- Persistence/replication/backups giữ secrets vượt retention.
- Application coi cache value stale là nguồn authoritative.
- Monitoring tools hiển thị key/value nhạy cảm.
- Operations credentials được chia sẻ cho mọi microservice.

Controls:

- ACL giới hạn commands và key patterns đúng capability.
- TLS/auth/network restrictions theo chế độ triển khai.
- Không chứa raw secrets trong key name hoặc logs.
- Separate namespaces/instances cho data classes khác trust.
- Memory/eviction policy và request rate limits.
- Backup/persistence encryption, access audit.
- Không dựa vào keyspace notifications như durable audit/replay log.
- Xác định correctness contract khi cache down.

Một Redis instance đa mục đích có thể làm các quyền chồng chéo: **lỗi của cache module không nên cấp khả năng xóa durable coordination state**.

## 50. Search/OpenSearch/Elasticsearch: truy vấn hỗ trợ và index bảo mật

Search engine thường là **bản sao có thể chứa nhiều PII hơn người dùng nhìn thấy**. Các threat paths:

- Public search endpoint bỏ tenant filter.
- Raw search DSL do client điều khiển có script/query cost rất cao.
- Support tool cho phép wildcard search toàn bộ tài khoản.
- Index mappings chứa fields private không cần cho tìm kiếm.
- Search snapshot lưu ngoài retention policy.
- Reindex từ source snapshot cũ hồi sinh soft-deleted/private records.
- Dashboard plugin có quyền đọc nhiều indices.
- Bulk indexing logs/DLQ chứa payload nhạy cảm.
- Query templates không kiểm tra quyền user sau khi index stale.

Controls:

- Chỉ index các fields cần cho use case.
- Authorization tại search-serving API, tenant scoping server-side.
- Dedicated read-only roles/query patterns cho support.
- Bounds cho depth, size, aggregation, sort, pagination.
- Secure query templates và per-user quotas.
- Read model freshness, delete/tombstone propagation.
- ACL cho dashboard, snapshots và reindex jobs.
- Cross-tenant query tests sau mỗi schema/index migration.

Không giả định search engine là “chỉ đọc” nên không cần bảo mật: đọc tập hợp dữ liệu quy mô lớn cũng là khả năng nhạy cảm.

## 51. Threat register: bảng rủi ro có thể giao việc

Một bảng mẫu:

| ID | Boundary | Threat | Impact | Control ưu tiên | Evidence | Owner |
|---|---|---|---|---|---|---|
| TM-01 | Client → API | Đọc Order khác tenant | Cao | Server-enforced tenant/object auth | Cross-tenant integration tests | API team |
| TM-02 | Input → query | NoSQL query injection | Cao | Typed allowlisted query builder | Negative query tests | API team |
| TM-03 | API → DB | Credential quá quyền | Cao | Split service roles | Role policy review | Platform |
| TM-04 | Admin → DB | Bulk delete nhầm scope | Cao | JIT + two-person approval + limits | Dry-run/audit test | DBA |
| TM-05 | DB → backup | Public backup/download | Cao | Restricted IAM/KMS/retention | Access analyzer + restore drill | Security |
| TM-06 | CDC → search | PII hồi sinh sau delete | Cao | Tombstone/deletion propagation | Rebuild privacy test | Data team |
| TM-07 | Report export | Download file của tenant khác | Cao | Job-scoped RBAC + signed URL expiry | Download authorization test | Admin team |
| TM-08 | Admin laptop | Stolen persistent DB key | Cao | Device policy + short-lived credential | Revocation drill | IT/Security |
| TM-09 | Query console → DB | Scan gây DoS | Trung bình/cao | Query budgets + pool isolation | Load test OLTP p99 | SRE |
| TM-10 | Logs → observability | Secret/PII leakage | Cao | Redaction + RBAC | Log sampling/secret scan | Platform |

Mỗi dòng cần **tracking status, due date, test reference và residual risk**. Bảng này là ví dụ, không phải kết luận rằng hệ của người học thực sự có các lỗ hổng đó.

## 52. Attack tree: từ mục tiêu kẻ tấn công tới đường đi

Đặt mục tiêu trừu tượng **“đọc dữ liệu Orders ngoài phạm vi cho phép”**:

~~~mermaid
flowchart TD
    GOAL["Đọc Orders trái phép"] --> A["Lỗi API authorization"]
    GOAL --> B["Compromise DB credential"]
    GOAL --> C["Lộ dữ liệu qua backup/export"]
    GOAL --> D["Lộ qua search/cache"]
    A --> A1["Tenant filter thiếu"]
    A --> A2["Object ownership không kiểm tra"]
    B --> B1["Credential quá quyền"]
    B --> B2["Secret bị lộ"]
    C --> C1["Artifact ACL sai"]
    C --> C2["Admin export thiếu scope"]
    D --> D1["Cache key scope sai"]
    D --> D2["Search query thiếu filter"]
~~~

Sơ đồ giúp thấy **nhiều con đường tới cùng một tác động**. Chặn đường A không đủ nếu B/C/D còn mở. Những lá của cây cần được chuyển thành tests hoặc control assessments.

Không cần mô tả chi tiết thao tác khai thác mới lập được một threat model tốt. Điều quan trọng là **điểm tin cậy bị vi phạm và hậu quả cần ngăn**.

## 53. Mapping threat → control → verification

Một nguyên tắc:

~~~text
Threat statement
   -> prevention control
   -> detection control
   -> recovery control
   -> evidence/test
   -> owner and review cadence
~~~

Ví dụ TM-07: người dùng tải file báo cáo của tenant khác.

- **Prevention:** export job lưu authorized tenant scope; mỗi GET job/download revalidate principal và scope.
- **Detection:** audit cross-tenant denials, unusual downloads.
- **Recovery:** revoke signed URLs, disable compromised account, delete affected artifact, notify theo process.
- **Evidence:** integration test user A không thể đọc job của B; URL expired/rotated fails; audit đủ.
- **Owner:** Admin API team + storage security owner.
- **Review:** khi thêm export endpoint, đổi IAM, đổi job store hoặc thay quyền.

Một control được viết trong tài liệu nhưng không có evidence sẽ khó phân biệt với giả định chưa được triển khai.

## 54. Test design: security test phải đi qua đúng boundary

Các test đáng giá:

1. User A GET/UPDATE Order thuộc user B trong cùng tenant khi không được phép.
2. Tenant A không GET/SEARCH/EXPORT dữ liệu tenant B.
3. API không nhận raw query operators không có trong allowlist.
4. Update DTO bỏ qua/từ chối server-owned fields.
5. Read-only DB credential không thể thực thi commands write/admin.
6. Migration account chỉ hoạt động trong scope và window được cấp.
7. Admin export job download phải xác thực lại quyền.
8. Expired signed URL không tải được artifact.
9. Backup IAM role không có quyền download/decrypt trái policy.
10. Search/rebuild không hồi sinh record đã bị xóa.
11. Log sanitizer không phát secret/token/PII raw ra stdout/trace.
12. Một admin query nặng không làm OLTP p99 vượt safety budget.
13. Revocation quyền user có hiệu lực theo contract trên cache và search.
14. Khi support operator đổi tenant, mọi queries bắt buộc scope mới hợp lệ.
15. Break-glass use được audit, alert và auto revoke.

Tests cần có positive cases để bảo đảm quyền hợp lệ vẫn hoạt động. **Một test denied đơn lẻ không chứng minh policy đầy đủ**; cần ma trận roles × actions × resources × scopes.

## 55. Workshop threat modeling: một buổi phân tích có đầu ra thực tế

Một phiên làm việc hiệu quả có thể gồm backend engineer, DBA, SRE/platform, security, data engineer và chủ quy trình nghiệp vụ.

**Trước buổi họp:**

- Thu thập DFD, inventory dữ liệu và roles hiện có.
- Liệt kê API, DBs, caches, event logs, admin tools, backup paths.
- Xác nhận scope, assumptions, trust boundaries và môi trường.
- Chọn luồng có impact lớn: checkout, admin export, account deletion.

**Trong buổi họp:**

1. Đi một request từ client tới nguồn và các bản sao.
2. Xác định assets, actors và boundaries của từng process/store/flow.
3. Dùng STRIDE và misuse cases để viết threat statements cụ thể.
4. Phân tích impact, likelihood và controls đang triển khai.
5. Thêm prevention/detection/recovery cho mỗi threat quan trọng.
6. Giao owner, deadline, evidence/test.
7. Ghi các giả định còn cần chứng minh.

**Sau buổi họp:**

- Đưa threats vào backlog và ghi state.
- Thêm negative security tests, policy checks, alerts và runbooks.
- Kiểm tra những giả định có liên quan IAM/backups/roles thực tế.
- Review lại khi kiến trúc hay quyền thay đổi.

Một buổi threat modeling tốt tạo **các hành động có thể thực thi hoặc giả định đã được kiểm chứng**, không chỉ một slide đầy biểu tượng hacker.

## 56. Mẫu threat model document có thể tái sử dụng

~~~yaml
system: orders-nosql-platform
scope:
  environment: production
  included:
    - public-order-api
    - order-database
    - support-admin-portal
    - search-projection
    - backup-export
  excluded:
    - third-party-payment-provider-internals
assets:
  - order-customer-pii
  - reservation-integrity
  - db-admin-credentials
trustBoundaries:
  - id: public-to-api
  - id: api-to-database
  - id: admin-to-privileged-access
  - id: database-to-backup
threats:
  - id: TM-01
    boundary: public-to-api
    scenario: cross-tenant-order-read
    impact: high
    likelihood: medium
    control: server-enforced-tenant-and-object-auth
    verification: cross-tenant-integration-tests
    owner: order-api-team
    state: planned
reviewTriggers:
  - new-admin-export
  - new-data-store
  - permission-model-change
  - backup-region-change
~~~

Đây là **template ghi lại quyết định**, không phải configuration trực tiếp của MongoDB, Redis hay IAM. Tài liệu phải liên kết DFD version, policy source, test results, incident runbook và residual risk.

Một assumption chưa được kiểm tra cần ghi riêng:

~~~text
Assumption:
  "Only backup service can download DB snapshots."

Evidence:
  inspect identity/resource/KMS policies;
  test denied access from non-backup role;
  verify audit events for download and decrypt.
~~~

Đừng ghi **“đã an toàn”** chỉ vì sơ đồ mong muốn như vậy.

## 57. Tabletop exercise: một credential quản trị nghi bị lộ

Tình huống: security monitoring phát hiện privileged credential có khả năng đã bị lộ từ một máy quản trị, nhưng chưa có bằng chứng chắc chắn về data exfiltration.

Các câu hỏi:

1. Credential thuộc ai, có quyền trên DB/region/tenants nào?
2. Có thể revoke/rotate mà không làm các ứng dụng khác ngừng hoạt động không?
3. Có session/token ngắn hạn đang hoạt động cần đóng không?
4. Có audit của admin queries, exports, IAM changes, schema changes không?
5. Snapshot download/decrypt logs cho thấy điều gì?
6. Những search/CDC/warehouse copies nào có thể đã bị truy cập?
7. Có dấu hiệu sửa/xóa dữ liệu hoặc chỉ đọc không?
8. Cần giữ logs, configuration và bằng chứng thế nào?
9. Có thể tạm ngừng export nặng mà giữ OLTP phục vụ không?
10. Ai phụ trách incident, privacy/legal review, communications?
11. Làm sao xác minh integrity sau khi containment?
12. Biện pháp dài hạn nào giảm blast radius (JIT, role split, device policy)?

Không xóa audit logs hoặc reset hạ tầng một cách tùy tiện trước khi thống nhất quy trình lưu bằng chứng. Containment cần cân bằng continuity và forensic needs.

## 58. Runbook khi phát hiện truy cập dữ liệu trái phép

Quy trình mức hệ thống:

1. **Triage:** xác minh cảnh báo, principal, thời gian, nguồn, loại dữ liệu.
2. **Scope:** xác định credentials, permissions, tables, tenants và bản sao có thể bị ảnh hưởng.
3. **Contain:** revoke/rotate hoặc hạn chế session/network route theo quy trình khẩn cấp.
4. **Preserve evidence:** bảo vệ audit logs, traces, access events và configuration snapshots.
5. **Assess impact:** đã đọc/sửa/xóa data nào, có backup/export liên quan không?
6. **Protect integrity:** tạm ngăn thao tác rủi ro, đối soát facts/versions nếu bị sửa dữ liệu.
7. **Recover:** phục hồi permissions và dữ liệu theo protocol/source-of-truth.
8. **Validate:** authorization tests, policy denies, audit coverage và business invariants.
9. **Communicate:** theo quy trình security, privacy và nghĩa vụ liên quan.
10. **Improve:** sửa root cause, cập nhật threat model, alerts, ownership.

Read-only breach vẫn có thể nghiêm trọng vì confidentiality. Write compromise có thể gây integrity loss mà không cần rò PII; cần phân loại sự cố tương ứng.

## 59. Khi nào phải cập nhật mô hình đe dọa?

Các trigger thường gặp:

- Thêm public API, webhook hoặc đối tác tích hợp.
- Thêm NoSQL engine, cache, search index hoặc region.
- Chuyển sang multi-tenant collections chung.
- Mở admin console, query editor, report export.
- Thay IAM/SSO/service account/secrets rotation.
- Thêm backup, warehouse, CDC replay hoặc data pipeline.
- Dùng một GUI/plugin/SaaS vendor mới có quyền truy cập.
- Đổi driver, auth policy, query DSL hoặc feature permissions.
- Thêm batch job có quyền scan nhiều data.
- Index thêm field nhạy cảm, thay retention/deletion policy.
- Incident, audit, pentest hoặc compliance review.
- Đổi quyền truy cập hoặc ownership của team.

Nên version threat model cùng kiến trúc: DFD revision, owners, ngày review, open risks, evidence links. **Một mô hình được viết xong rồi để quên có thể tạo cảm giác an toàn giả khi hệ đã đổi.**

## 60. Những hiểu nhầm thường gặp

| Hiểu nhầm | Vì sao sai | Cách đúng |
|---|---|---|
| “DB có password là đủ” | API/backup/admin có nhiều đường khác | Xem toàn DFD |
| “TLS bảo đảm authorization” | TLS không kiểm tra quyền Order | AuthZ per resource |
| “JWT hợp lệ đọc được mọi record” | Authentication khác authorization | Tenant/object checks |
| “Private network loại mọi risk” | Insider và compromised workload vẫn kết nối | Network + identity |
| “NoSQL không bị injection” | Dynamic operators/filters có thể bị lạm dụng | Typed query builder |
| “Một GET không thể DoS DB” | Full scan/aggregation có thể rất đắt | Query cost budgets |
| “PATCH field nào cũng được” | Mass assignment | DTO allowlist |
| “Admin nội bộ luôn đáng tin” | Credential theft/human error | JIT/MFA/audit |
| “Ẩn nút UI là chặn quyền” | Endpoint vẫn có thể gọi trực tiếp | Server-side enforcement |
| “Read-only admin vô hại” | Có thể export PII/scan gây DoS | Scoped reads/quotas |
| “Backup mã hóa là hoàn toàn an toàn” | KMS decrypt và IAM có thể rộng | Key/role policies |
| “Xóa source là xóa toàn bộ copies” | Search/logs/backup còn | Deletion propagation |
| “Search index chỉ là công cụ phụ” | Có thể chứa PII ngoài scope | Field minimization |
| “Query logs càng chi tiết càng tốt” | Có thể lộ secrets/PII | Redaction/RBAC |
| “Một superuser giúp đơn giản” | Một compromise gây blast radius lớn | Per-service identity |
| “Managed DB tự bảo mật mọi thứ” | App/IAM/data thuộc trách nhiệm hệ sử dụng | Shared responsibility |
| “Admin export chỉ là GET” | Tạo dữ liệu copy độc lập | Artifact lifecycle |
| “Confirmation dialog ngăn bulk delete” | Không giới hạn phạm vi hay quyền | Scoped operations/approval |
| “Break-glass dùng hàng ngày được” | Mất tính khẩn cấp và audit | JIT riêng |
| “Threat model viết một lần” | Architecture và quyền thay đổi | Review theo trigger |
| “Không alert nghĩa không breach” | Có thể thiếu telemetry | Detection coverage |
| “Audit log tự phát hiện sự cố” | Không ai xem cũng vô ích | Alert và triage ownership |
| “Chỉ hacker ngoài mới là threat” | Human error có thể xóa dữ liệu | Accidental misuse |
| “Vendor bảo mật thay toàn bộ” | Third-party access cũng là attack surface | Vendor assessment |

## 61. Bài tập A — Vẽ threat model cho hệ đặt hàng đa tenant

Cho hệ giả định:

~~~text
Customer API -> Order service -> Document NoSQL
                           |-> Redis cache
                           |-> Search index

Support staff -> Admin portal -> Order service

DBA -> DB GUI -> NoSQL production

NoSQL -> Backup snapshots -> Object storage
NoSQL -> CDC -> Event log -> Analytics
~~~

Yêu cầu:

1. Xác định các assets quan trọng và data classifications.
2. Vẽ DFD có ít nhất năm trust boundaries.
3. Liệt kê sáu actors, bao gồm khách, support, DBA và service identities.
4. Tạo hai threat scenarios cho mỗi nhóm API, DB và admin portal.
5. Dùng STRIDE để phân loại ít nhất tám threats.
6. Viết scenario cross-tenant read gồm preconditions, impact và assets.
7. Thiết kế tenant/object authorization từ API tới cache/search.
8. Xác định nơi PII có thể còn nằm ngoài primary NoSQL.
9. Đề xuất ba controls giảm blast radius khi credential bị lộ.
10. Ghi evidence/test cho từng control.
11. Gán owner và review trigger.
12. Liệt kê assumption phải kiểm chứng trước khi tuyên bố backup an toàn.

### 61.1. Hướng triển khai bài giải

Đừng bắt đầu bằng “cài firewall”. Hãy đi từ **user journey, identity, permission boundary và data copies**. Một answer tốt có ít nhất một threat về confidentiality, một về integrity, một về availability và một về privileged operator action. Mỗi threat đi kèm test có thể thực hiện.

## 62. Bài tập B — Mô hình hóa admin export

Một admin portal cho nhân viên hỗ trợ xuất Orders trong 90 ngày. Người dùng có quyền tenant T1, nhưng request body gửi:

~~~json
{
  "tenantId": "T2",
  "dateRangeDays": 365,
  "includeCustomerAddress": true,
  "format": "csv"
}
~~~

Yêu cầu:

1. Đặt trust boundary giữa client và admin API.
2. Các fields nào không được tin từ request?
3. Role/action/scope nào thực sự cho phép export?
4. Date range, rows, bytes, concurrency và retry limits nên có gì?
5. Khi job tạo xong, download authorization cần kiểm tra gì?
6. Artifact URL cần TTL, revocation và audit thế nào?
7. CSV export có rủi ro formula injection và PII leakage nào?
8. File có thể đi vào downloads/browser cache/logs ở đâu?
9. Audit cần actor, scope, ticket, result và time nào?
10. Nếu quyền operator bị thu hồi lúc job RUNNING, policy nên quy định gì?
11. Thiết kế test user T1 không tải được artifact T2.
12. Nếu export làm DB primary throttling, kiến trúc cần đổi ra sao?

Một câu trả lời chỉ nói “kiểm tra JWT và lưu CSV trên S3” vẫn thiếu authorization trên **từng job/artifact**, cũng như data minimization, retention và quota.

## 63. Bài tập C — Permissions, encryption keys và backups

Giả sử tổ chức dùng một account chung cho application, migration và backup. Snapshots được mã hóa, nhưng role `developer` có quyền download và decrypt.

Hãy:

1. Vẽ đường từ compromised credential tới plaintext snapshot.
2. Phân loại hậu quả confidentiality, integrity, availability.
3. Tách identities cho app, migration, backup, DBA.
4. Thiết kế KMS/resource policies theo chức năng.
5. Giải thích tại sao at-rest encryption không chặn người có decrypt grant.
6. Quyền restore và download nên tách thế nào?
7. Thiết kế JIT và audit cho DBA.
8. Kiểm soát retention và quyền trên snapshot copies.
9. Viết một test deny cho role ngoài backup.
10. Đề xuất rotate/revoke workflow khi credential bị lộ.
11. Thiết kế restore drill không đưa PII vào môi trường test thiếu quyền.
12. Ghi owner và bằng chứng cần kiểm tra cho mỗi thay đổi.

## 64. Câu hỏi tự kiểm tra

1. Asset, threat, weakness và risk khác nhau thế nào?
2. CIA triad gồm những mục tiêu gì?
3. Vì sao cần liệt kê bản sao dữ liệu ngoài database?
4. Actor nội bộ có thể tạo threat gì?
5. Trust boundary là gì?
6. DFD giúp xác định đường truy cập nào?
7. STRIDE gồm sáu nhóm nào?
8. Authentication khác authorization thế nào?
9. Object-level authorization và tenant-level scope khác gì?
10. NoSQL query injection liên quan query structure thế nào?
11. Vì sao filter/sort fields phải có allowlist?
12. Mass assignment có thể sửa sai Order ra sao?
13. Một GET hợp lệ có thể gây DoS database không?
14. Cache key thiếu tenant ảnh hưởng gì?
15. Search index có cần tenant filtering riêng không?
16. Vì sao webhook/queue không tự làm payload đáng tin?
17. SSRF threat thường xuất hiện ở đâu?
18. Driver credential có quan hệ gì với blast radius?
19. Least privilege hơn strong password ở điểm nào?
20. Vì sao read-only role vẫn có thể nguy hiểm?
21. Network segmentation có thay DB authentication không?
22. Encryption at rest khác key management thế nào?
23. Vì sao backup chứa PII có thể nhạy cảm hơn API point lookup?
24. CDC/DLQ có thể chứa bí mật hoặc PII không?
25. Vì sao metrics/logs cũng là data leakage path?
26. Concurrent writes phá integrity theo kiểu gì?
27. Xóa source record còn phải xử lý bản sao nào?
28. Managed DB shared responsibility nghĩa gì?
29. Admin console khác user API ở điểm tin cậy nào?
30. JIT access và break-glass khác nhau ra sao?
31. Bulk export khác GET một document về blast radius?
32. Vì sao download URL cần TTL/audit?
33. CI/CD migration runner nên giữ quyền thế nào?
34. GUI/plugin của vendor làm tăng attack surface ra sao?
35. Audit logs phải được bảo vệ khỏi tampering như thế nào?
36. Threat register cần có những trường nào?
37. Threat → control → verification giúp team ra quyết định gì?
38. Vì sao cần negative authorization tests?
39. Khi nào threat model cần cập nhật?
40. Một tabletop exercise nên tạo ra kết quả và evidence gì?

## 65. Tổng kết: bảo vệ cả dữ liệu lẫn đường quản trị

Một hệ NoSQL có thể có xác thực database mạnh nhưng vẫn rò dữ liệu qua API thiếu kiểm tra tenant, cache key không đúng, search index, file export hoặc backup. Ngược lại, API có thể phân quyền chính xác nhưng một tài khoản DBA dùng lâu dài với quyền rộng khiến toàn bộ cluster vẫn có rủi ro lớn. **Threat modeling phải bao quát cả dữ liệu, quyền, đường truyền, bản sao và quá trình vận hành.**

Một quy trình thực hành có thể lặp lại:

~~~text
1. Xác định phạm vi, assets và data classifications.
2. Liệt kê user/service/admin actors và identities.
3. Vẽ DFD qua API, NoSQL, cache, CDC, backup, admin tools.
4. Đánh dấu trust boundaries và đường có quyền cao.
5. Dùng STRIDE và misuse cases để viết threat scenarios.
6. Đánh giá impact, likelihood, blast radius và existing controls.
7. Đặt prevention, detection và recovery cho từng threat.
8. Gắn owner, test/evidence, due date và residual risk.
9. Giữ credentials nhỏ quyền, ngắn hạn; tách admin workflows.
10. Kiểm tra tenant/object authorization trên mọi đường đọc/ghi/export.
11. Bảo vệ snapshots, KMS keys, event logs, search và telemetry.
12. Review lại khi có endpoint, pipeline, quyền hoặc môi trường mới.
~~~

**Nguyên tắc quan trọng nhất:** *Một hệ NoSQL an toàn không chỉ là một database được khóa. Đó là các ranh giới tin cậy được xác định rõ, quyền truy cập đúng ở từng đường đi, và những bằng chứng từ kiểm thử, audit và kế hoạch khôi phục chứng minh dữ liệu vẫn bí mật, toàn vẹn và sẵn sàng.*











