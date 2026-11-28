# Review trust boundary: rà soát ranh giới tin cậy trong thiết kế bảo mật

## Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích **trust boundary** và mục tiêu của hoạt động **review trust boundary** trong *security design review*, phân biệt với network segmentation, service boundary, administrative boundary và resilience/failure domain.
2. Xác định **actors, assets, data stores, processes, flows, identities, entry points và vùng tin cậy** trên sơ đồ kiến trúc/luồng dữ liệu (DFD).
3. Liệt kê những lần thông tin hoặc quyền đi qua trust boundary và đặt câu hỏi **“bên nhận dựa trên bằng chứng nào để tin dữ liệu, danh tính và quyền từ bên gửi?”**
4. Phân tích những mối đe dọa tại boundary: spoofing, tampering, repudiation, information disclosure, denial of service và elevation of privilege; nhận diện confused deputy, IDOR/BOLA, replay, SSRF và bypass.
5. Rà soát tính đầy đủ của **authentication, authorization, input validation, data protection, secure transport, key/secret handling, audit, error handling và safe failure** trên từng đường crossing.
6. Lập **trust-boundary register, review checklist, requirement/control mapping, review findings và risk decisions** có chủ sở hữu.
7. Thiết kế **positive, negative, integration và failure-path tests**, cùng những bằng chứng triển khai/vận hành để xác minh thiết kế đã được thực thi.
8. Viết **assurance claim có giới hạn**, tránh kết luận “an toàn” chỉ từ sơ đồ hoặc cấu hình chưa được kiểm chứng.

Trong module **SECURITY_SECURITY_ASSURANCE**, mục tiêu là xây dựng cách đánh giá **có bằng chứng** rằng hệ thống đáp ứng mục tiêu bảo mật, từ phân tích rủi ro, yêu cầu và controls đến kiểm thử, audit, khắc phục phát hiện và assurance liên tục. Chủ đề **Review trust boundary** thuộc chương **Security design review** tập trung vào một câu hỏi kiến trúc có ảnh hưởng rất lớn: **Ở đâu dữ liệu hoặc lệnh đi từ một miền có giả định tin cậy này sang một miền khác, và kiểm soát nào ngăn bên nhận tin nhầm?**

> **Nguyên tắc cốt lõi:** Ranh giới tin cậy không phải đường kẻ trang trí trên sơ đồ. Từng lần đi qua ranh giới phải có **hợp đồng bảo mật**: xác minh bên gửi, kiểm tra quyền, xác thực nguồn và toàn vẹn dữ liệu, hạn chế phạm vi, bảo vệ truyền dẫn, ghi nhận sự kiện và xử lý an toàn khi không thể xác minh.

## 1. Trust boundary là gì?

**Trust boundary (ranh giới tin cậy)** là điểm hoặc vùng mà khi luồng dữ liệu, lời gọi, phiên, token hay quyền quản trị đi qua, **giả định về độ tin cậy và quyền hạn thay đổi**. Thành phần bên nhận không được coi dữ liệu/identity/control signal của bên gửi là hợp lệ chỉ vì kết nối đã được thiết lập hoặc hai thành phần cùng nằm trong một mạng.

Ví dụ: Một browser gửi request đến API. Browser có thể sửa JSON, URL và headers. API phải xác minh danh tính, quyền và tính hợp lệ của dữ liệu; không được tin giá trị `role=admin` hoặc `tenantId=A` do browser tự khai.

Ví dụ khác: Một worker được cấp quyền đọc nhiều tenant từ database. API gateway đã kiểm tra user có quyền export, nhưng nếu worker nhận danh sách object IDs tùy ý và không gắn từng object với **tenant/owner đã xác minh**, user có thể dùng worker thành một **confused deputy**. Ranh giới quan trọng không chỉ là browser → API mà còn **request nghiệp vụ → privileged worker → data store**.

### 1.1. Những khác biệt cần nhớ

| Khái niệm | Câu hỏi trung tâm | Ví dụ |
|---|---|---|
| **Trust boundary** | Ở đâu cần xác minh lại danh tính, quyền, dữ liệu hoặc giả định? | Client → API; workload → KMS |
| **Network boundary** | Mạng/lưu lượng nào được định tuyến hoặc lọc? | Public subnet → private subnet |
| **Service boundary** | Thành phần nào sở hữu API và trách nhiệm? | Payment API → Refund Worker |
| **Data ownership boundary** | Ai được phép truy cập/sửa dataset hay field? | Tenant A → dữ liệu tenant B |
| **Administrative/control-plane boundary** | Ai được thay policy, deploy, config và cấp quyền? | Developer account → production admin |
| **Failure/resilience boundary** | Lỗi, quá tải hoặc compromise lan tới đâu? | Cell riêng hoặc worker pool riêng |
| **Compliance/legal boundary** | Nghĩa vụ hoặc quyền xử lý dữ liệu thay đổi ở đâu? | Organization → data processor/vendor |

Hai boundary có thể trùng nhau nhưng không đồng nghĩa. **Mạng private không tự biến user/service thành trusted**. Một service mesh mTLS có thể xác thực workload-to-workload nhưng **không tự kiểm tra quyền nghiệp vụ trên từng hóa đơn**. Một microservice tách code khỏi gateway cũng không tự bảo đảm mọi entry point đi qua cùng policy.

### 1.2. Ranh giới là quan hệ, không chỉ là máy chủ

Trust boundary có thể tồn tại giữa:

- Người dùng thường và privileged administrator.
- Hai tenant sử dụng cùng một application/database.
- Một request đã xác thực và một thao tác nhạy cảm cần **step-up**.
- Một workload và một token/secret được trao để gọi hệ thống khác.
- Một API với webhook từ vendor dù cả hai dùng HTTPS.
- Ứng dụng và KMS/HSM có quyền decrypt.
- CI/CD pipeline và production deployment control plane.
- Dữ liệu có nguồn gốc ngoài hệ thống với bộ phân tích/công cụ tự động.
- Quyết định policy và đường thực thi tại data plane.

Không phải mọi ranh giới đều có firewall hữu hình. **Tenant ownership check, object-level authorization, token audience và schema validation** cũng chính là các cơ chế bắt buộc ở những ranh giới logic.

### 1.3. Mục đích của review

Review trust boundary nhằm xác minh:

1. **Sơ đồ mô tả đúng hệ thống**: có đầy đủ actors, flows và implicit dependencies.
2. **Mỗi boundary crossing được nhận diện** và có lý do tin cậy minh bạch.
3. **Claims về identity, scope, data origin và policy** được kiểm tra bằng controls phù hợp.
4. **Threat scenarios** gắn với đường crossing thay vì chỉ gắn với tên sản phẩm.
5. **Failure/degraded behavior** không bỏ qua kiểm soát vì dependency lỗi.
6. **Evidence và tests** đủ để chứng minh controls hoạt động trong scope.
7. **Risks/gaps** có owner, quyết định và kế hoạch remediation/retest.

Một bản review tốt có thể kết luận thiết kế **cần sửa**. Điều đó là giá trị của review sớm: ngăn lỗ hổng ngay từ kiến trúc, trước khi trở thành sự cố sản xuất.

## 2. Chuẩn bị đầu vào cho security design review

Không cần hệ thống đã chạy ở production mới review. Nhưng cần có kiến trúc và giả định đủ rõ. Những đầu vào quan trọng:

| Đầu vào | Nội dung cần có | Nếu thiếu sẽ gây gì? |
|---|---|---|
| **Business use cases** | Ai làm gì, mục tiêu nào, dữ liệu nào | Không xác định được hành động cần bảo vệ |
| **Security objectives** | Bảo mật, toàn vẹn, khả dụng, truy vết | Không biết tiêu chí thành công |
| **Asset/data inventory** | Dataset, secrets, identities, logs, keys | Bỏ sót tài sản và đường rò rỉ |
| **Data classification** | Public/internal/restricted theo policy | Thiếu điều kiện bảo vệ khi chuyển dữ liệu |
| **Architecture/DFD** | Processes, data stores, external entities, flows | Không nhìn thấy boundary crossings |
| **Deployment topology** | Accounts, regions, clusters, VPC, endpoints | Dễ nhầm logical isolation với physical isolation |
| **Identity/authorization design** | AuthN, roles, ABAC, workload IDs, session | Dễ bỏ qua privilege escalation |
| **Integration contracts** | Webhooks, queues, APIs, files, third-party | Không biết ai xác minh input và callback |
| **Cryptography/key design** | TLS, encryption, KEK/DEK, KMS scope | Không thấy key custody và unwrap boundary |
| **Policy/risk baseline** | Approved standards, requirements, threat model | Không có chuẩn đối chiếu |
| **Known assumptions/changes** | Legacy paths, feature flags, exceptions | Claim rộng hơn phạm vi thực tế |

### 2.1. Kiểm tra sơ đồ còn thiếu

Sơ đồ kiến trúc đẹp nhưng chỉ có “Frontend → API → DB” gần như luôn thiếu thông tin review. Hỏi:

- Browser/mobile/third-party clients nằm ở đâu?
- Edge, API gateway, service mesh, sidecars và direct service paths?
- Admin portal, debug endpoints, support tools?
- Queue, event bus, worker, cron jobs, batch exports và webhooks?
- Object storage, cache, backup, log pipeline và analytics?
- IdP, policy engine, device posture, KMS/secrets service?
- CI/CD, IaC, release signing, artifact registry và admin console?
- Vendor processor và data residency boundary?
- **Data return path** và cách download/export được cấp quyền?

Đừng chỉ vẽ **happy path**. Dữ liệu có thể đi qua **retry queue, DLQ, cache, backup, temporary file, support ticket và operator workflow** mà sơ đồ ban đầu bỏ qua.

### 2.2. Scope và trust assumptions

Ghi rõ:

- **Scope:** hệ thống, component, môi trường, tenant, release/architecture version.
- **Assumptions:** Ví dụ IdP ký token theo giao thức được phê duyệt, KMS enforce key policy.
- **Dependencies:** Những giả định nào phải chứng minh bằng config/test/provider evidence?
- **Out-of-scope:** Có lý do và owner; không coi các phần ngoài scope là an toàn.
- **Unknowns:** Cần xác minh, không gán “trusted” vì chưa tìm thấy lỗi.

Ví dụ câu ghi chú review:

> “Payment API giả định object owner được lấy từ Payment DB; hiện chưa có evidence worker cũng dùng nguồn này. Review chỉ kết luận về API path và mở finding cho worker path.”

## 3. Vẽ DFD và đặt ranh giới tin cậy

### 3.1. Thành phần DFD

Một **Data Flow Diagram (DFD)** dùng:

- **External entity:** browser, mobile, vendor, operator hoặc dịch vụ ngoài scope.
- **Process:** API, worker, policy engine, transformer hoặc gateway.
- **Data store:** database, object storage, cache, queue, backup hoặc log store.
- **Data flow:** request, response, event, file, secret, token hoặc control instruction.
- **Trust boundary:** vùng chuyển mức tin cậy, quyền và trách nhiệm kiểm tra.

DFD là một góc nhìn. Có thể bổ sung **sequence diagram, C4/container diagram, IAM graph, deployment/account map** và dữ liệu thực tế; không ép tất cả chi tiết vào một biểu đồ.

### 3.2. Ví dụ nền tảng hóa đơn nhiều tenant

Giả sử **InvoiceHub** phục vụ các doanh nghiệp A và B, hỗ trợ xem hóa đơn và xuất CSV bất đồng bộ. Nó có website, edge gateway, Invoice API, Export Worker, Queue, Database, Object Storage và vendor gửi thông báo.

~~~mermaid
flowchart TD
    U["Browser / external subject"] -->|"request + token + object ID"| GW["Gateway / edge PEP"]
    GW -->|"verified request context"| API["Invoice API"]
    API -->|"read / ownership lookup"| DB[("Invoice database")]
    API -->|"authorized export job"| Q[("Job queue")]
    Q -->|"job event"| W["Export worker"]
    W -->|"read records"| DB
    W -->|"write export"| OS[("Export object storage")]
    W -->|"event"| V["Notification vendor"]
    OS -->|"authorized download"| DL["Download gateway"]
    DL --> U
    API --> IDP["Identity / authorization services"]
    W --> IDP
    API --> LOG[("Protected audit store")]
    W --> LOG
    DL --> LOG
~~~

Sơ đồ này chưa vẽ boundary chính thức; bước review kế tiếp là **nhóm các thành phần theo miền trách nhiệm/trust assumptions** và đánh dấu từng crossing:

| Boundary ID | Crossing | Điều bị thử thách |
|---|---|---|
| **TB-01** | Browser → Gateway/API | Client input và token có xác thực, scope đúng? |
| **TB-02** | Gateway → Invoice API | Gateway đã xác thực thì service có cần object authorization? |
| **TB-03** | Invoice API → Database | Service identity có quyền DB rộng; request có tenant scope? |
| **TB-04** | API → Queue → Worker | Job metadata có thể bị giả mạo, lặp hoặc lỗi thời? |
| **TB-05** | Worker → Object Storage/Download | File được giới hạn recipient, tenant, expiry và audit? |
| **TB-06** | Worker → Vendor | Dữ liệu nào chuyển ra ngoài, webhook/reply có được xác minh? |
| **TB-07** | Workloads → IdP/Policy | Token, role, device/tenant attributes có đủ freshness? |
| **TB-08** | Workloads → Audit | Ai ghi, ai sửa/xóa log; khi audit down thì sao? |

Đây là **danh mục minh họa**. Review thực tế cần gắn boundary với **chính xác các flows của sản phẩm** và có thể bổ sung KMS, CI/CD, backup, admin/control plane.

### 3.3. Minh họa vùng tin cậy

~~~mermaid
flowchart LR
  subgraph EXT["External / lower-trust domain"]
    C["Browser / vendor client"]
  end
  subgraph EDGE["Edge domain"]
    G["Gateway: AuthN, request limits"]
  end
  subgraph APP["Application domain"]
    A["Invoice API: object AuthZ"]
    Q["Queue"]
    W["Worker: job scope recheck"]
  end
  subgraph DATA["Protected data domain"]
    D[("Tenant-scoped records")]
    O[("Export objects")]
  end
  C -->|"TB-01"| G
  G -->|"TB-02"| A
  A -->|"TB-03"| D
  A -->|"TB-04"| Q
  Q --> W
  W -->|"TB-03"| D
  W -->|"TB-05"| O
~~~

Không suy từ việc API và worker cùng nằm trong “Application domain” rằng **worker không cần kiểm tra authorization**. Nếu worker xử lý job metadata từ queue, tenant context có thể thay đổi và service account có quyền rộng, vẫn có **logical trust boundary** tại API → queue → worker và worker → DB.

### 3.4. Đường đi và quay về đều quan trọng

Một request–response có ít nhất hai hướng:

- Request vào: **client input, user token, role, tenant ID, payload**.
- Response ra: **PII, data fields, error details, pagination metadata, file links**.

Review không được dừng ở việc “request đã xác thực”. Phải kiểm tra **output authorization, redaction, information disclosure, cache headers, URL expiry và error messages**. Ví dụ API có thể trả HTTP 403 nhưng response body vô tình chứa tiêu đề hóa đơn của tenant khác.

## 4. Phương pháp review từng boundary crossing

### 4.1. Hợp đồng kiểm tra tại mỗi crossing

Một cách thực hành là dùng bảng hỏi **I–A–D–P–E–F**:

- **I — Identity:** Bên gửi thực sự là ai? Authentication bằng chứng nào? Có máy, user và ủy quyền thay mặt user?
- **A — Authorization:** Hành động trên object/resource cụ thể có được phép không? Scope quyền, tenant, delegation, purpose?
- **D — Data:** Dữ liệu/tokens đến từ đâu, có toàn vẹn và được phân loại không? Input validation, output filtering?
- **P — Protection:** Bảo vệ khi truyền và lưu: TLS/mTLS, key/secret scope, encryption, quotas?
- **E — Evidence:** Decision, enforcement, correlation, policy version và audit có quan sát được không?
- **F — Failure:** Khi xác thực, ownership lookup, KMS, policy engine hoặc audit pipeline lỗi, có **safe failure** không?

Mỗi câu hỏi cần có **review outcome** (satisfied/gap/unknown/not applicable) và **tham chiếu evidence**. Tránh điền PASS chỉ vì tài liệu nói “đã có TLS”.

### 4.2. Identity và authentication

Kiểm tra:

1. **User identity** được xác minh bằng IdP/session/token nào? Token có issuer/audience/expiry/signature đúng?
2. **Workload identity** có được xác minh bằng mTLS, workload token hoặc cơ chế đáng tin khác? Có còn dùng shared secret/IP allowlist quá rộng?
3. Khi một service gọi thay user, **caller identity** và **end-user authorization context** được gắn kết thế nào?
4. Có thể **replay** credential hoặc dùng token từ environment/service khác không?
5. Khi account/role/key bị thu hồi, consumer cập nhật trong giới hạn thời gian nào?
6. Nếu IdP unavailable, hệ thống có **bỏ kiểm tra** hay sử dụng cache có căn cứ/freshness?

**TLS mã hóa kênh** và có thể xác thực peer, nhưng không chứng minh user được phép gọi một operation nghiệp vụ. Việc kiểm tra chỉ `userId` trong JSON không phải authentication.

### 4.3. Authorization và privilege boundaries

Hỏi:

- Ai có quyền `invoice.read` so với `invoice.export`, `refund.approve` hoặc `key.decrypt`?
- Có phân biệt **role-based** với **object-level/tenant authorization**?
- Có kiểm tra dữ liệu owner từ nguồn authoritative không, hay tin request header?
- Workload có quyền đọc nhiều tenant có được dùng như **confused deputy** không?
- Admin/support có **break-glass**, step-up, JIT privilege, approval và audit?
- **Separation of duties:** Người tạo có tự phê duyệt được giao dịch không?
- Khi đổi role/policy, job đang chờ và cache permit cũ xử lý thế nào?

Kiểm tra cả **control plane** và **data plane**: một admin có quyền sửa policy của tất cả tenants có thể gây tác động lớn dù API data path rất chặt.

### 4.4. Input integrity và parsing boundary

Mọi dữ liệu đi qua boundary cần được đánh giá theo **hợp đồng dữ liệu**:

- Schema, loại dữ liệu, range, size và encoding.
- Unexpected fields, duplicated headers, ambiguous JSON hoặc parameter pollution.
- URL/path canonicalization, ID normalization, path traversal.
- File upload validation, content type, size, zip bombs.
- SQL/command/template injection và unsafe deserialization.
- SSRF qua URL do user nhập; allowlist destination theo chức năng và bảo vệ metadata endpoints.
- Replay, out-of-order messages, duplicate event ID và idempotency.
- Parser differences giữa gateway, proxy, API và backend.

Validation không chỉ ở edge. **Boundary giữa queue và worker** hoặc giữa API và third-party webhook parser cũng cần kiểm tra, vì payload có thể bị thay đổi ở đường trung gian hoặc sinh từ nguồn thấp tin cậy.

### 4.5. Data confidentiality, integrity và privacy

Xác định:

- Những fields nào là public/internal/restricted? Có PII, credentials, secrets hoặc keys?
- Dữ liệu được **tối thiểu hóa** khi chuyển domain/vendor chưa?
- Kênh nào dùng TLS hoặc cơ chế bảo vệ tương đương theo baseline? Endpoint identity có được xác minh?
- Khi lưu/copy sang queue, cache, export, log hoặc backup, **classification và retention** có được giữ?
- Đối với nội dung nhạy cảm, có encrypt và key ownership đúng scope không?
- Có chống tampering/replay bằng signature/MAC/context binding khi phù hợp?
- Có dữ liệu được trả về client sai tenant, sai field hoặc không cần thiết không?
- Có trách nhiệm, hợp đồng và bằng chứng xử lý của vendor không?

Một **mã hóa thành công** không chứng minh **ủy quyền truy cập đúng**. Một user có quyền decrypt dữ liệu của tenant khác vẫn là lỗi boundary dù AES hoạt động chính xác.

### 4.6. Audit, monitoring và accountability

Một review cần xác định:

- Event nào cần log ở ingress, decision, action, error và admin change?
- Làm sao nối **request ID ↔ decision ID ↔ worker job ID ↔ object ID ↔ actual outcome**?
- Log có ghi principal, scope, operation, time, outcome và policy version nhưng **không ghi secret/PII không cần thiết**?
- Audit store có được bảo vệ khỏi principal đang thực thi hành động và người thay policy?
- Khi telemetry bị thiếu, có health alert/degraded status hay silent drop?
- Có phát hiện bất thường crossing như cross-tenant access, unexpected privileged operation, admin policy changes?

“Có log request” khác với **có evidence rằng request bị chặn hoặc chỉ tác động tới đúng dữ liệu**.

### 4.7. Failure và degraded behavior

Với từng crossing, đặt giả thiết:

1. Token validator/IdP timeout.
2. Authorization engine hoặc ownership database không phản hồi.
3. KMS không unwrap được DEK.
4. Queue/network delay tạo retry/out-of-order.
5. Audit pipeline bị ngắt.
6. Vendor callback bị lặp, sai signature hoặc tới quá hạn.
7. Session bị revoke sau khi job đã submit.
8. Failover sang region có policy/secret khác phiên bản.

Yêu cầu **trạng thái an toàn** cho mỗi trường hợp. Không tự động fail-open khi không chứng minh được quyền; cũng không đơn giản fail-closed cho mọi tác vụ mà bỏ qua availability của chức năng thiết yếu. Lựa chọn theo **rủi ro, nghĩa vụ, business invariants và policy được phê duyệt**, có test và giới hạn cụ thể.

## 5. Dùng STRIDE để tìm mối đe dọa tại trust boundary

**STRIDE** giúp hệ thống hóa câu hỏi về các dạng đe dọa. Nó không thay thế asset inventory, domain knowledge hoặc phân tích rủi ro. Khi review, dùng STRIDE như **bộ gợi ý để không bỏ sót**.

| STRIDE | Boundary question | Kịch bản | Security property / control |
|---|---|---|---|
| **S — Spoofing** | Bên gửi có thể giả danh không? | Webhook giả danh provider, token sai audience | Authentication, signature/token validation, peer identity |
| **T — Tampering** | Payload/policy có thể bị sửa không? | Job event đổi tenant; CI sửa artifact | Integrity protection, schema, provenance, signature/MAC |
| **R — Repudiation** | Có thể chối bỏ thao tác không? | Admin sửa policy nhưng audit thiếu actor | Protected audit, immutable/integrity controls, correlation |
| **I — Information disclosure** | Dữ liệu có lọt sai domain không? | Export worker trả CSV tenant khác | Object authz, scope, redaction, encryption |
| **D — Denial of service** | Một nguồn có thể làm cạn tài nguyên không? | Tenant gửi nhiều payload lớn tới parser | Quota, rate limit, timeout, backpressure |
| **E — Elevation of privilege** | Người ít quyền có thể lợi dụng đặc quyền của bên nhận? | Confused deputy dùng service account đọc DB rộng | Least privilege, delegated authorization, SoD |

### 5.1. Ví dụ STRIDE cho browser → Invoice API

- **Spoofing:** Token bị giả chữ ký hoặc issuer; server phải kiểm tra đầy đủ token và binding phù hợp.
- **Tampering:** Client thay `tenantId` hoặc `invoiceId`; API phải lấy owner từ DB và xác minh.
- **Repudiation:** Người dùng tranh cãi đã export; cần actor, action, time, decision, resource scope và evidence.
- **Information disclosure:** API trả metadata của invoice khác tenant khi từ chối; cần output/error review.
- **DoS:** Payload quá lớn hoặc request rate cao; cần request limits và tenant-aware quotas.
- **Elevation:** User thường lợi dụng endpoint support/admin; cần phân tách role và privileged control plane.

### 5.2. Ví dụ STRIDE cho queue → worker

- **Spoofing:** Producer không được phép publish job vào queue; cần producer/workload identity và quyền publish.
- **Tampering:** Job body đổi resource IDs hoặc thêm field vượt scope; worker không tin payload chỉ vì queue “internal”.
- **Repudiation:** Không nối được submitter với worker action; cần job ID, original principal, policy version và protected audit.
- **Information disclosure:** Worker có quyền DB rộng, export không kiểm tra tenant; cần business authorization ở worker.
- **DoS:** Poison message/retry liên tục làm nghẽn queue; cần bounded retries, DLQ và rate controls.
- **Elevation:** Job yêu cầu worker chạy tác vụ privileged thay user; cần kiểm tra delegation và restrictions.

### 5.3. Phân tích abuse cases ngoài STRIDE

STRIDE nên được bổ sung bằng abuse cases đặc thù:

1. **IDOR/BOLA:** Đổi ID object nhưng vẫn được trả dữ liệu.
2. **Cross-tenant confusion:** Client tự đưa tenant ID, backend tin mà không đối chiếu.
3. **Confused deputy:** Privileged service thao tác theo request không đủ quyền nghiệp vụ.
4. **SSRF:** Client đưa URL khiến service gọi metadata/internal API.
5. **Mass assignment:** Payload có thêm fields thay đổi owner, role hoặc approval status.
6. **Replay:** Event/payment callback bị phát lại làm đổi trạng thái nhiều lần.
7. **Stale authorization:** Role/tenant membership bị thu hồi nhưng job/cache vẫn cho phép.
8. **Token substitution:** Token hợp lệ cho service A được dùng ở service B sai audience.
9. **Parser differential:** Gateway và backend diễn giải cùng request khác nhau.
10. **Policy/config compromise:** Admin/pipeline thay rule hoặc secret ở nhiều environments.

Mỗi abuse case cần mô tả **precondition, attacker capability, crossing, expected forbidden behavior, likelihood/impact và verification**, không chỉ liệt kê tên lỗ hổng.

## 6. Những trust boundaries thường bị bỏ sót

### 6.1. Browser/mobile ↔ edge/API

Đây là boundary rõ nhất nhưng review dễ dừng quá sớm.

Checklist:

- Token/session được xác minh đầy đủ: issuer, audience, expiry, signature và revocation/freshness theo policy?
- API kiểm tra **authorization theo action và object**, không chỉ “đã login”?
- Client có thể tự đổi tenant, role, account, price, status hoặc risk field?
- Request size, file upload, encoding, parser và rate limit có được kiểm soát?
- Cookies, CSRF protection, CORS và browser security policies phù hợp ngữ cảnh?
- Error responses, caches và signed download URLs có rò rỉ dữ liệu không?
- Có endpoint nào bypass gateway như debug port hoặc internal hostname bị lộ?

### 6.2. API gateway ↔ internal service

Sai lầm thường gặp: “Gateway đã xác thực rồi nên backend không cần kiểm tra nữa.”

Review:

- Backend có **xác minh nguồn gọi** và identity/claims đã được bảo vệ khi truyền?
- Nếu gateway truyền headers như `X-User-ID` hoặc `X-Tenant`, client có thể tự gửi header đó và được giữ lại không?
- Có assurance rằng only trusted gateway/service được set headers này?
- Policy scope có bao gồm **direct internal API**, worker, admin path hoặc gRPC?
- Những thay đổi gateway/policy có được đồng bộ với service authorization không?
- Có least privilege mTLS/workload identity và authorization trên resource không?

**mTLS xác thực kênh hoặc workload**, nhưng không thay thế xác minh user/delegation và object ownership. Một internal service account có thể được xác thực đúng nhưng vẫn không được phép xuất dữ liệu tenant khác.

### 6.3. Service ↔ database và tenant boundary

Database thường tin service principal, nhưng chính service principal có thể có quyền rất rộng. Đây là nơi review phải kiểm tra **data access scope**:

- Query có tenant/owner constraint dùng dữ liệu authoritative?
- Row-level security hoặc data-layer guard có được dùng nếu phù hợp?
- Service có thể bỏ qua check do code path khác hoặc direct DB access không?
- Migrations và privileged admin scripts có quyền như thế nào?
- Batch queries hoặc export API có giới hạn fields và volume không?
- Cache có gắn tenant/identity key đúng không?
- DB credential có least privilege và được phân tách giữa prod/dev không?

**Đưa tenant ID vào WHERE** có thể là một biện pháp, nhưng chưa đủ nếu ID lấy từ input không tin cậy hoặc query builders có đường bỏ tenant filter. Cần **negative tests và source-of-truth**.

### 6.4. API ↔ queue ↔ worker

Đây là boundary quan trọng vì message **không giữ nguyên session context** mặc định:

- Producer identity, ACL publish và topic/queue scope?
- Job có correlation ID, submitter, tenant, action, resource scope và authorization context không?
- Các fields có integrity/authenticity và schema validation không?
- Worker có **recheck** khi job bắt đầu theo yêu cầu của use case?
- Message có retry/idempotency/replay protection khi ảnh hưởng trạng thái nghiệp vụ không?
- DLQ/retry storage có lưu PII/secret lâu hơn policy không?
- Consumer có thể gọi KMS/DB bằng quyền rộng không? Có tách service account theo job class?
- Khi quyền user bị thu hồi hoặc object đổi owner, job pending xử lý thế nào?

Giới hạn quyền queue publisher không thay thế **authorization trên object** khi worker xử lý.

### 6.5. Service ↔ third-party webhook/API

Không tin dữ liệu chỉ vì đến từ domain/vendor đã đăng ký:

- Endpoint và TLS peer có được xác minh, tránh bỏ certificate validation?
- Webhook có **signature/MAC** hoặc cơ chế xác thực được provider hỗ trợ và được kiểm tra đúng theo đặc tả?
- Có chống **replay**, kiểm tra timestamp/nonce hoặc event ID theo hợp đồng?
- Có idempotency và xác minh business state trước khi commit không?
- Dữ liệu trả về có schema/type validation và được xem là untrusted input?
- Ai có quyền sửa callback URL, API key và vendor configuration?
- Privacy/data-sharing scope, region, retention và incident notification rõ?
- Khi provider timeout, có phân biệt **unknown state** với failure chắc chắn để không double-charge?

**Không tự sáng chế thuật toán chữ ký webhook.** Dùng cơ chế provider công bố, kiểm tra input bytes/canonicalization theo đặc tả, bảo vệ secret và key rotation; test cả signature sai, event cũ và event lặp.

### 6.6. Workload ↔ KMS/secrets manager

Kiểm tra trust boundary liên quan key:

- Identity nào có thể encrypt/decrypt/sign/unwrap?
- Có tách quyền giữa application workloads và KMS administrators?
- Key scope có phân vùng tenant/environment/dataset khi phù hợp?
- “Non-exportable key” vẫn có thể bị lạm dụng qua **decrypt/sign oracle** không?
- Khi KMS unreachable có fallback thành plaintext hoặc key mặc định?
- Secrets có bị log, đưa vào image, CI variables, ticket hay crash dump không?
- Backup/rotation/revocation có dependency mapping và restore test?

Ranh giới crypto cần cả **key custody** và **quyền yêu cầu operation**, không chỉ xác nhận “dùng KMS”.

### 6.7. Developer/CI/CD ↔ production control plane

Boundary quản trị thường có **blast radius lớn hơn API**:

- Ai có thể merge, build, ký artifact và deploy lên production?
- Quyền pipeline chạy từ pull request untrusted có bị giới hạn không?
- Secrets/runner/cache/artifact có chia sẻ giữa trusted và untrusted jobs không?
- Release artifact có provenance/digest và approval?
- Có separation of duties cho thay policy, quyền admin và audit storage?
- IaC changes có được review/test và đối chiếu effective configuration?
- Có emergency deploy/rollback với identity, expiry và evidence?

**Repository private không tự bảo vệ production** nếu một automation token có quyền thay toàn bộ infrastructure và có thể bị lấy qua untrusted build step.

### 6.8. Admin/support ↔ user data

Support có thể cần truy cập dữ liệu cho case hợp lệ, nhưng việc có role “support” không được hiểu là **được tự do đọc mọi khách hàng**:

- Ticket/case reference và purpose có được xác minh?
- Quyền được cấp **JIT/time-bound**, giới hạn tenant/action/fields?
- Có cần step-up và independent approval?
- Có masking/redaction phù hợp không?
- Mọi truy cập privileged có audit và hậu kiểm không?
- Break-glass có expiry, monitoring và quy trình thu hồi?

### 6.9. Logging/analytics/backup ↔ phạm vi dữ liệu khác

Một dataset hạn chế có thể được bảo vệ tại API nhưng lộ qua:

- Access logs chứa request body hoặc bearer token.
- Analytics event thu thập identifiers và sensitive fields không cần thiết.
- Crash dump hoặc debug traces.
- CDC/replication sang kho dữ liệu ít kiểm soát.
- Backup/recovery account có quyền truy cập rộng.
- Export files tồn tại sau khi người dùng mất quyền.

Review phải theo **dữ liệu tới các bản sao**, không dừng ở source database. Những nơi lưu bằng chứng/log cũng có trust boundary riêng.

## 7. Kiểm tra ranh giới chính sách và quyết định

### 7.1. PDP và PEP

Với kiến trúc Zero Trust/authorization:

- **Policy Decision Point (PDP)** quyết định có cho phép request theo policy/tín hiệu không.
- **Policy Enforcement Point (PEP)** thực thi quyết định trên đường truy cập thực.
- **Identity provider, policy source, device/risk signals** có thể đóng vai trò nguồn dữ liệu ra quyết định.

Review phải tìm:

1. Decision request có **subject/action/resource** chính xác không?
2. Thuộc tính nào có nguồn gốc từ client, có được kiểm tra lại không?
3. Policy version và precedence có xác định rõ không?
4. PEP nào áp quyết định cho API, worker, data access và download?
5. Có đường **bypass** không đi qua PEP?
6. Obligations (redaction, audit, giới hạn fields) có được áp?
7. Nếu PDP unavailable/indeterminate, request được xử lý an toàn không?
8. Khi revoke quyền, cache/job/token đã cấp xử lý thế nào?

### 7.2. TOCTOU: check ở một miền, dùng ở miền khác

**Time-of-check to time-of-use (TOCTOU)** xảy ra khi quyền/trạng thái được đánh giá tại thời điểm A nhưng hành động thực thi tại thời điểm B và dữ liệu có thể đã thay đổi.

Ví dụ:

1. 09:00: Người dùng có quyền export; API tạo job.
2. 09:10: Quyền export bị thu hồi.
3. 10:00: Worker lấy job, đọc toàn bộ dữ liệu từ DB và tạo file.

Nếu yêu cầu bảo mật đòi hỏi quyền còn hiệu lực khi thực thi mà worker chỉ dùng quyết định từ 09:00, boundary **API → queue → worker** chưa được kiểm soát.

Biện pháp có thể gồm:

- Bind job với identity, tenant, action, resource IDs và policy context.
- Recheck khi job bắt đầu và trước delivery theo policy.
- Bounded decision lifetime và revocation propagation.
- Check resource ownership trong transaction hoặc bằng version checks.
- Cancel/quarantine output nếu quyền thay đổi theo rule.
- Ghi kết quả decision và actual data access.

Không khẳng định mọi job bắt buộc dừng ngay khi user logout; điều đó phụ thuộc business rule và nghĩa vụ áp dụng. Review phải **chốt chính sách rõ** và test theo chính sách đó.

### 7.3. Phân biệt identity, delegation và purpose

Khi Service A gọi Service B thay User U, có ba điều cần xác minh:

- **Service A** có được gọi API của B không?
- **User U** có được thực hiện action trên resource cụ thể không?
- **Service A** có được **ủy quyền thay User U** cho action/scope này không?

Chỉ kiểm tra mTLS giữa A và B bỏ sót hai câu sau. Chỉ kiểm tra token User U nhưng không xác thực A có thể tạo đường spoof service caller. Một thiết kế tốt nêu **đại diện ai, scope nào, expiry nào, audience nào**, và PEP nào thực thi.

## 8. Quy trình security design review theo từng bước

### 8.1. Bước 1 — Chốt scope, mục tiêu và phiên bản

Ghi:

- System/service, business flows và environments.
- Diagram version, architecture decision record (ADR), release hoặc proposed change.
- Assets/data classifications và mục tiêu CIA/privacy/accountability.
- System owner, security reviewer, data owner, control owner, risk owner.
- Dependencies/vendor, known gaps và out-of-scope exclusions.

Review chỉ có thể đánh giá **một thiết kế cụ thể**, không phải tất cả phiên bản trong tương lai.

### 8.2. Bước 2 — Walkthrough DFD và deployment

Lần lượt theo các use cases:

1. **Happy path:** data/request chạy qua những nodes nào?
2. **Sensitive path:** admin actions, export, approval, payment, key operations?
3. **Asynchronous path:** queue, webhook, batch, retry và callback?
4. **Failure path:** timeout, failover, stale policy, KMS outage?
5. **Operational path:** CI/CD, admin, support, logs, backup/recovery?

Với mỗi mũi tên, ghi **source/destination, transport/protocol, payload/schema, caller identity, resource/action scope**. Đừng bỏ qua các flows “chỉ internal”.

### 8.3. Bước 3 — Đánh dấu trust assumptions và boundary IDs

Trong DFD, nhóm theo:

- Ai kiểm soát code, cấu hình, secrets và policy?
- Ai có thể tạo/sửa dữ liệu?
- Có nguồn xác thực thông tin và mô hình quyền khác nhau không?
- Có sự khác biệt giữa admin/control plane và data plane?
- Có tenant, account, region, vendor hoặc môi trường khác không?

Đánh ID ổn định như `TB-01`, `TB-02`; lưu mapping flows. Đừng coi mỗi network hop là boundary bắt buộc giống nhau; **boundary được xác định bởi giả định tin cậy**, không phải số lượng routers.

### 8.4. Bước 4 — Threat enumeration

Tại từng crossing:

1. Liệt kê assets, attacker capabilities và security objectives.
2. Dùng STRIDE và abuse cases phù hợp.
3. Xác định điều attacker có thể **giả mạo, sửa, đọc, trì hoãn, làm lặp hoặc nâng quyền**.
4. Xác định những assumptions cần kiểm tra.
5. Gắn risk scenario ID, likelihood/impact theo phương pháp của tổ chức.

Không chấm **risk score** tùy tiện bằng con số nếu không có scale/baseline được phê duyệt. Tập trung vào **threat paths có căn cứ**.

### 8.5. Bước 5 — Kiểm tra control placement

Với mỗi threat scenario:

- Control nào thực sự ngăn/phát hiện/khắc phục?
- Nó nằm **trước, ngay tại hay sau boundary**? Đủ sớm để chặn side effect?
- Có đường vòng qua control?
- Ai có thể tắt/bypass, thay policy hoặc cấp ngoại lệ?
- Nếu dependency lỗi, control có tiếp tục hoặc fail-safe?
- Control có bảo vệ **actual resource** hay chỉ kiểm tra endpoint?

Ví dụ: “Gateway AuthN” chưa giải quyết cross-tenant read tại worker. Control placement cần kiểm tra ở **service/worker/data access**.

### 8.6. Bước 6 — Chuyển risk thành requirements và acceptance criteria

Ví dụ:

> **TB-AUTHZ-01:** Mỗi request đọc hoặc xuất invoice phải kiểm tra quyền của subject với action và invoice cụ thể, dựa trên tenant owner từ nguồn có thẩm quyền; request khác tenant phải bị chặn trước khi trả dữ liệu hoặc tạo file export.

Acceptance criteria cần có **positive, negative, bypass và failure**:

- User tenant A được đọc invoice A theo quyền.
- User tenant B không đọc/export invoice A bằng đổi ID.
- Direct worker invocation không bypass.
- Ownership source timeout không tạo unverified permit.
- Không có file/data output sai scope và audit ghi quyết định.

### 8.7. Bước 7 — Chốt evidence plan và review findings

Mỗi requirement/control cần:

- Test methods: static/config inspection, integration, end-to-end, negative, fault-injection, operational sampling.
- Owner, deadline/trigger và môi trường.
- Expected/actual artifacts: effective policy, logs, test results, screenshot có context, resource state.
- Finding nếu control/evidence thiếu.
- Risk treatment: remediation, accepted risk hoặc out-of-scope có căn cứ và authority.

Không đóng finding chỉ bằng sửa sơ đồ. Phải có **implementation evidence và retest** khi claim về operating effectiveness được đưa ra.

### 8.8. Bước 8 — Review sign-off có giới hạn và theo dõi thay đổi

Kết quả review có thể là:

- **APPROVED WITH EVIDENCE GAPS:** Thiết kế được chấp thuận có điều kiện kiểm chứng; chưa kết luận control chạy tốt.
- **CHANGES REQUIRED:** Có điểm thiết kế không đạt cần sửa trước gate tiếp theo.
- **RISK ACCEPTANCE REQUIRED:** Gap/risk cần quyết định của người có thẩm quyền.
- **BLOCKED/UNKNOWN:** Thiếu DFD, ownership hoặc evidence để kết luận.
- **APPROVED IN SCOPE:** Đủ căn cứ cho phạm vi và loại review đã xác định.

Trạng thái là **mẫu minh họa**, tổ chức cần thống nhất chính sách gating. Đặc biệt, **approved design** không đồng nghĩa **verified runtime security**.

### 8.9. Quy trình tổng quát

~~~mermaid
flowchart TD
  A["Scope + assets + risk objectives"] --> B["DFD / control-plane walkthrough"]
  B --> C["Mark boundaries + crossing register"]
  C --> D["STRIDE + abuse cases per crossing"]
  D --> E["Control placement + trusted input checks"]
  E --> F["Security requirements + tests"]
  F --> G["Review findings and risk decisions"]
  G --> H{"Design evidence sufficient?"}
  H -- "No" --> I["Revise design / clarify assumptions"]
  I --> B
  H -- "Yes, in scope" --> J["Design sign-off with limits"]
  J --> K["Implementation + test + runtime evidence"]
  K --> L["Assurance review / retest"]
  L --> M["Change trigger / new flows"]
  M --> B
~~~

## 9. Trust-boundary register: tài liệu hóa có cấu trúc

### 9.1. Vì sao cần register?

Một sơ đồ có đường kẻ màu không đủ cho audit. **Boundary register** giúp liên kết:

**boundary ID → crossing → assumptions → risk scenarios → controls → acceptance tests → evidence → gaps → review decision**.

Nó cũng hỗ trợ **impact analysis** khi thêm API route, đổi vendor hoặc di chuyển một service sang cloud account khác.

### 9.2. Ví dụ YAML

Mẫu bên dưới là **định dạng giáo dục**, không phải schema chính thức của một công cụ threat modeling:

~~~yaml
trustBoundaryReview:
  reviewId: SDR-INVOICE-TB-004
  reviewVersion: "1.0"
  status: design-review-in-progress
  system: InvoiceHub
  architectureReference: INVOICE-DFD-V3
  environmentScope:
    - staging
    - production
  scopeOwnerRole: Invoice Platform Owner
  securityReviewerRole: Security Architect
  riskOwnerRole: Invoice Business Risk Owner

  boundaries:
    - id: TB-04
      name: export-job-handoff
      source: invoice-api
      destination: invoice-export-worker
      transport: authenticated-message-queue
      trustAssumption: >-
        Queue payload is not by itself proof of business authorization.
      payload:
        - jobId
        - submittingPrincipalReference
        - tenantId
        - invoiceIds
        - requestedAction
      dataClass: restricted-metadata
      securityObjectives:
        - tenant-confidentiality
        - authorization-correctness
        - auditability
      identifiedThreats:
        - THREAT-JOB-TENANT-SPOOF
        - THREAT-JOB-REPLAY
        - THREAT-STALE-EXPORT-RIGHTS
      requiredControls:
        - authenticated-queue-producer
        - server-resolved-tenant-and-object-ownership
        - worker-authz-recheck-before-export
        - idempotency-and-replay-control
        - decision-to-output-audit-correlation
      failureBehavior: deny-or-quarantine-unauthorized-job
      requirementIds:
        - TB-AUTHZ-01
        - TB-EVENT-02
        - TB-AUDIT-03
      plannedTests:
        - TEST-CROSS-TENANT-JOB-REJECT
        - TEST-DIRECT-WORKER-BYPASS
        - TEST-REVOKED-ROLE-QUEUED-JOB
        - TEST-REPLAY-JOB-IDEMPOTENCY
      evidenceReferences:
        - EV-WORKER-EFFECTIVE-POLICY
        - EV-WORKER-TEST-RUN
      reviewResult: NEEDS_REMEDIATION
      openFindings:
        - FIND-WORKER-TRUSTS-CLIENT-TENANT

  knownLimitations:
    - Legacy support-export path not included in DFD yet
  approval:
    decision: PENDING
    decisionReference: null
    approvedByRole: null
~~~

### 9.3. Những trường register quan trọng

- **source/destination:** đủ chính xác để nhận diện boundary, không chỉ tên chung “frontend–backend”.
- **trustAssumption:** nêu cái gì không được tự tin, ai chịu trách nhiệm kiểm tra.
- **payload/dataClass:** biết tài sản và dữ liệu nào đi qua.
- **securityObjectives và identifiedThreats:** giải thích vì sao cần control.
- **requiredControls:** kết quả thiết kế yêu cầu, có owner tương ứng.
- **plannedTests:** ý định test, **chưa chứng minh đã chạy**.
- **evidenceReferences:** chỉ dẫn evidence thực khi có, không nhầm với evidence bản thân.
- **reviewResult/openFindings:** thể hiện gap minh bạch.
- **knownLimitations:** không che những đường chưa có trong sơ đồ.

### 9.4. Anti-pattern trong register

Không nên ghi:

> “TB-04: API → Worker, TLS = enabled, Security = PASS.”

Vì **TLS ở API → queue** không trả lời producer identity, tenant ownership, revoked rights, payload tampering, replay, worker privilege hay data export. PASS phải tương ứng với **requirement + evidence + scope**.

## 10. Từ review findings thành yêu cầu kiểm thử được

### 10.1. Ví dụ ma trận control

| Boundary | Requirement đề xuất | Control implementation | Test/evidence |
|---|---|---|---|
| **TB-01 Client → API** | Token sai issuer/audience/expiry không được chấp nhận | Token validator, session policy | Token negative tests, config và runtime logs |
| **TB-02 Gateway → Service** | Request không thể tự gán verified headers | Trusted ingress identity, strip/rebuild headers | Header spoofing và direct-service tests |
| **TB-03 Service → DB** | Truy cập invoice phải đúng subject–action–resource–tenant | Object-level AuthZ, authoritative ownership | Cross-tenant tests, DB/output state |
| **TB-04 Queue → Worker** | Job không được dùng unverified tenant hoặc expired permit | Worker recheck, job integrity, identity binding | Tampered/replayed/revoked job tests |
| **TB-05 Export → Download** | File chỉ được giao cho recipient có quyền | Scoped download authorization, expiry | Wrong-recipient, stale link tests |
| **TB-06 Vendor ↔ Webhook** | Callback giả/sai signature/replay không được commit | Vendor signature validation, idempotency | Invalid signature, replay, timeout/reconciliation |
| **TB-07 Workload → KMS** | Principal ngoài scope không được decrypt | Key policy, least privilege, audit | KMS negative tests, key operation logs |
| **TB-08 Control plane → Prod** | Deployment/policy change chỉ từ trusted approved workflow | Artifact provenance, change approval, SoD | Wrong digest, unauthorized change tests |
| **TB-09 Workload → Audit** | Sự kiện bảo mật không bị silent drop và không chứa secret | Protected audit, buffering/alert | Missing log/telemetry fault test |

Mỗi dòng phải có **requirement ID, owner, environment, threshold/baseline reference và trạng thái verified** khi áp dụng thật. Bảng ví dụ chưa chứng minh hệ thống đã đạt.

### 10.2. Cấu trúc requirement tại boundary

Mẫu câu:

> Tại crossing **[TB-ID, source → destination]**, khi **[subject]** gửi **[action/payload]** để sử dụng **[resource]**, thành phần nhận **phải [xác minh/giới hạn hành động]** theo **[policy và source-of-truth đã phê duyệt]** trước **[sensitive action]**; nếu thuộc tính quan trọng thiếu/không hợp lệ hoặc dependency lỗi thì **[safe behavior]**, và kết quả phải được ghi nhận bằng **[evidence]**.

Ví dụ với `TB-04`:

> **TB-REQ-04:** Export Worker phải lấy quyền thực thi của job từ job context được xác minh và resource ownership từ nguồn có thẩm quyền; trước khi đọc invoice, worker phải kiểm tra tenant/object/action theo policy có hiệu lực. Payload chứa invoice của tenant khác hoặc quyền đã bị thu hồi theo rule phải bị từ chối, không tạo output và tạo audit event liên kết job ID.

### 10.3. Acceptance criteria không chỉ là HTTP status

Một test có thể thấy API trả `403`, nhưng worker đã tạo file trong object storage từ trước. Khi đó **security objective không đạt**.

Kiểm tra:

- **Before:** Không có dữ liệu nào đã bị đọc/ghi trái phép trước quyết định deny.
- **During:** Không có side effect ở queue, DB, KMS hay vendor path.
- **After:** Không có file, message, cache hoặc link mang dữ liệu vượt scope.
- **Audit:** Có outcome, principal/resource ref, version/correlation đủ để điều tra.
- **Privacy:** Evidence không vô tình chứa PII hoặc secret thật.

## 11. Viết Gherkin cho trust-boundary tests

Gherkin giúp reviewer, developer và QA đồng ý về **expected behavior**; phải chạy test thực tế với synthetic fixtures và lưu actual evidence. Các scenario sau mang tính minh họa.

~~~gherkin
Feature: Trust boundary enforcement for InvoiceHub

  Background:
    Given tenant A and tenant B have separate invoice records
    And resource ownership is resolved from the authoritative database
    And the approved access policy is deployed to the test environment

  Scenario: A forged tenant header cannot cross the client-to-API boundary
    Given user U belongs only to tenant B
    And invoice IA belongs to tenant A
    When U requests invoice IA with a forged tenant A header
    Then the API must not treat the header as authoritative ownership
    And no invoice IA content may be returned
    And the denied request must be auditable

  Scenario: An authenticated service cannot become a confused deputy
    Given exporter W has a valid workload identity and broad database access
    And requester U lacks authority for tenant A
    When U asks W to export tenant A invoices using a crafted job payload
    Then W must reject the unauthorized business operation
    And no tenant A export file may be created

  Scenario: A queued job must not rely on stale user privileges
    Given U submitted an export while authorized
    And the job is waiting in the queue
    And U's export privilege has been revoked
    When the worker begins processing the job
    Then the required authorization recheck must not grant stale permission
    And the job must follow the approved deny-or-hold behavior

  Scenario: Direct internal service access cannot bypass the gateway
    Given a caller has no approved workload identity or delegated authority
    When the caller invokes the invoice worker through an internal endpoint
    Then the call must be refused
    And no protected record may be read or exported

  Scenario: Malformed or tampered job metadata cannot change ownership
    Given an export job was authorized for invoice IA in tenant A
    When the queue message is modified to include invoice IB from tenant B
    Then the worker must reject the changed resource scope
    And the event and actual outcome must be traceable

  Scenario: Missing resource ownership cannot become an unchecked permit
    Given the worker requires ownership metadata from an authoritative source
    And that source is unavailable
    When a restricted export is requested
    Then the worker must not export data under an unverified permit
    And the degraded condition must be detected

  Scenario: A webhook with an invalid signature cannot mutate payment state
    Given the payment provider uses an authenticated callback protocol
    And the provider signature is invalid
    When a callback claims a payment is successful
    Then payment state must not change based on the unverified callback
    And the invalid attempt must be recorded safely

  Scenario: Replaying a valid webhook does not duplicate a transaction
    Given a valid provider event was previously processed
    When the same event is delivered again
    Then the system must recognize the duplicate according to policy
    And no second business effect may occur

  Scenario: A valid token for another audience cannot authorize this API
    Given an access token is validly signed for service X
    When the token is presented to the invoice API for service Y
    Then the invoice API must reject the unauthorized audience
    And no protected action may be performed

  Scenario: Audit pipeline failure does not silently remove accountability
    Given sensitive export operations require protected audit evidence
    And the audit pipeline becomes unavailable
    When an export is attempted
    Then the system must follow its approved safe audit-failure policy
    And the degraded state must be visible to the designated control owner

  Scenario: A presigned download link does not ignore recipient controls
    Given an export file belongs to tenant A
    And the approved link policy binds the file to a permitted recipient
    When a user from tenant B attempts to obtain the file
    Then the download path must not disclose the file to tenant B
    And the attempted access must be traceable

  Scenario: An unapproved deployment cannot alter production policy
    Given only approved release artifacts may change production policy
    When an unapproved artifact or principal attempts a policy update
    Then the change must be blocked before becoming effective
    And the event must appear in protected administrative audit evidence
~~~

### 11.1. Cần thêm kiểm thử tích cực

Negative tests không thay thế kiểm thử **user/workload được phép**:

- Đúng user, tenant, action, resource → request được xử lý trong scope.
- Webhook hợp lệ → xử lý event đúng một hiệu ứng nghiệp vụ.
- Đúng admin được phê duyệt → policy change có thể chạy với audit.
- Khi audit/KMS/vendor có sự cố → đường phục hồi hợp lệ hoạt động theo policy.

Nếu chỉ có DENY tests, hệ thống có thể “an toàn” theo cách **từ chối mọi request**. Security design review cần cân bằng **security properties và business functionality**.

### 11.2. Test oracle độc lập

Không lấy quyết định của chính service đang kiểm thử làm chân lý:

- Tenant ownership trong fixture được kiểm tra độc lập với header.
- Business permission matrix được xác nhận trước, không suy từ output PDP.
- Actual DB/file state được kiểm tra thay vì chỉ tin `success=false`.
- Webhook payload/signature được tạo theo kịch bản có kiểm soát.
- Evidence có test run, release, effective config, environment và expected/actual.

### 11.3. Test các vùng kiểm tra khác nhau

| Loại test | Điểm cần chứng minh |
|---|---|
| **Design review** | Boundary và assumptions được nhận diện; control placement hợp lý |
| **Unit/property test** | Logic validation/policy xử lý input và edge cases đúng |
| **Integration test** | API–queue–worker–DB và vendor callbacks giữ scope |
| **E2E negative** | Attacker không bypass và không tạo side effects |
| **Fault injection** | IdP/KMS/PIP/audit outage không cho phép unsafe fallback |
| **Configuration review** | IAM/network/key policies và mTLS đúng effective config |
| **Runtime sampling** | Requests trong kỳ thực tế có audit/decision/enforcement evidence |
| **Recovery drill** | Failover/restore không thay đổi tenant, key và audit boundaries |

Không chạy thử nghiệm destructive, thao tác vào dữ liệu thật hoặc mô phỏng tấn công ngoài phạm vi được phép. Môi trường test có thể khác production; khi kết luận phải ghi sự khác biệt.

## 12. Đánh giá bằng chứng của thiết kế và triển khai

### 12.1. Ba mức kết luận khác nhau

| Lớp assurance | Có thể khẳng định | Cần bằng chứng |
|---|---|---|
| **Design effectiveness** | Thiết kế có xét crossing và threat, controls được đặt đúng theo lý luận | DFD, boundary register, threat model, architecture decision, requirements |
| **Implementation effectiveness** | Controls đã được triển khai đúng thiết kế trong scope/release | Effective config, code review, IAM/policy, deployment/version, integration results |
| **Operating effectiveness** | Controls thực sự hoạt động trong thời gian/môi trường đã đánh giá | Runtime logs, negative tests, admin access reviews, incident/drift và sampling |

Một bản design review có thể **pass về thiết kế** mà chưa có bằng chứng **operating effectiveness** vì hệ thống chưa triển khai. Không nên nhầm thiếu production evidence với lỗi thiết kế, nhưng cũng không tuyên bố production an toàn khi chưa test.

### 12.2. Evidence package cho boundary

Một hồ sơ có thể chứa:

1. **DFD, deployment diagram, scope, version và assumptions**.
2. **Boundary register** với crossing, data class, identity, protocol, policy và owner.
3. Risk scenarios/abuse cases và kết quả đánh giá.
4. Security requirements, acceptance criteria và design decisions.
5. Effective controls: AuthN/AuthZ, IAM, tenant data policies, TLS/KMS, secrets, queue ACL và audit.
6. Tests: positive, negative, direct-bypass, replay, fail-safe và outcome verification.
7. Test run metadata: release, environment, fixtures, test versions, expected/actual.
8. **Decision + enforcement traces** liên kết request/job/object/output.
9. Review findings, exception/risk decision và remediation/retest.
10. Known limitations, unverified paths, planned follow-up.

**Không đặt raw tokens, private keys, API secrets, recovery shares hoặc PII không cần thiết trong evidence package.** Nên lưu mã định danh/tham chiếu và bằng chứng đã bảo vệ truy cập/tính toàn vẹn.

### 12.3. Mẫu review decision record

```yaml
securityDesignReview:
  id: SDR-INVOICE-2026-04
  system: InvoiceHub
  architectureVersion: DFD-INVOICE-V3
  scope:
    - client-to-api
    - api-to-worker
    - worker-to-database
    - export-to-download
  assessedStage: design
  reviewResult: CHANGES_REQUIRED

  summary:
    identifiedBoundaries: 8
    reviewedBoundaries: 8
    approvedDesigns: 5
    designGaps: 2
    pendingEvidence: 1

  findings:
    - id: FIND-001
      boundary: TB-04
      issue: worker-trusts-client-supplied-tenant-id
      requirement: TB-AUTHZ-01
      remediationOwnerRole: Export Worker Owner
      verificationRequired:
        - cross-tenant-worker-negative-test
        - verified-resource-ownership-review
      status: OPEN
    - id: FIND-002
      boundary: TB-05
      issue: download-link-not-bound-to-recipient
      remediationOwnerRole: Export Delivery Owner
      status: OPEN

  assumptions:
    - Identity-provider-token-validation-follows-approved-baseline
  limitations:
    - production-runtime-assessment-not-yet-performed
    - vendor-archive-path-outside-current-scope

  signoff:
    decisionOwnerRole: Security Design Authority
    approvedRiskExceptionReference: null
    designApprovedForBuild: false
```

Đây là **mẫu minh họa**, không phải kết quả review thật. Các con số trong register chỉ có ý nghĩa khi boundary population đã được xác nhận và từng status có căn cứ.

### 12.4. Khi thiếu evidence

Nếu một bên nói “Gateway đã xác thực mọi request”, reviewer có thể yêu cầu:

- Inventory các routes, internal endpoints và worker entrances.
- Config token validation thực tế (issuer/audience/expiry/algorithm restrictions).
- Negative tests cho forged header/direct internal invocation.
- Runtime logs liên kết principal/request với protected action.
- Policy/version/change history.

Nếu chưa có, ghi **UNKNOWN / NEEDS_EVIDENCE**, không tự chọn PASS hoặc FAIL. Nếu có bằng chứng bypass, ghi **FAIL / finding**, phân biệt rõ với trường hợp chỉ chưa thử.

### 12.5. Claim–Argument–Evidence–Limitations

Ví dụ:

> **Claim:** Trong thiết kế InvoiceHub phiên bản DFD-INVOICE-V3, các boundary client→API, API→worker và worker→data đã được nhận diện, cùng các biện pháp dự kiến để kiểm tra danh tính, tenant authorization và chống job replay.
>
> **Argument:** Boundary register xác định nguồn tin cậy và những giả định bị thay đổi; threat model đề cập spoofing, tampering, confused deputy và stale authorization; requirements yêu cầu control tại API/worker thay vì chỉ gateway.
>
> **Evidence:** Approved DFD, trust-boundary register, threat model, control placement review và requirement IDs.
>
> **Limitations:** Đây là kết luận **thiết kế**. Chưa có bằng chứng runtime rằng worker thực hiện authorization đúng, mọi entry point đều được bảo vệ hoặc vendor archive tuân theo cùng policy; cần implementation và operating tests.

Chỉ khi có kết quả thực thi đủ scope mới mở rộng claim sang implementation/operating effectiveness. **Evidence quyết định độ mạnh của claim**, không phải mức độ tự tin của reviewer.

## 13. Risk prioritization và quyết định review

### 13.1. Ưu tiên boundary cần xem xét sâu

Những crossing thường đáng ưu tiên:

- Chuyển **untrusted data thành privileged instruction**.
- Chuyển quyền từ **user scope sang service/admin scope**.
- Chuyển dữ liệu **restricted** ra third party, analytics hoặc download channel.
- Chuyển thông điệp qua **async queue** có độ trễ/retry/replay.
- Thay **IAM, KMS key policy, routing, security controls** trong control plane.
- Chuyển giữa tenants, accounts, environments hoặc regions.
- Giao tiếp với **vendor** không thuộc quyền quản trị trực tiếp.
- Hành động tài chính, thay owner, secret access hoặc dữ liệu riêng tư quy mô lớn.

Không gán severity cố định chỉ vì crossing có “internet”. Severity phụ thuộc assets, attacker capability, controls, exploitability và business impact theo phương pháp risk assessment đã phê duyệt.

### 13.2. Phân biệt finding, risk và exception

- **Finding:** Thiếu sót cụ thể so với requirement hoặc evidence expectation.
- **Risk:** Kịch bản có thể gây tác động, với likelihood/impact và control assessment.
- **Exception:** Quyết định có thẩm quyền về sai lệch có phạm vi/thời hạn/biện pháp bù.
- **Assumption:** Điều được dùng để lập luận nhưng chưa nhất thiết đã được chứng minh.

Không được đánh dấu “accepted” chỉ vì developer đồng ý sửa sau. **Risk owner/approval authority** phải được xác định theo governance thực tế.

### 13.3. Mẫu issue/finding

> **Finding:** `FIND-TB-04-001` — Export Worker tin tenant ID từ queue payload và dùng service account đọc invoice toàn hệ thống.
>
> **Boundary/Threat:** `TB-04` và `TB-03`; tampering, confused deputy, cross-tenant disclosure.
>
> **Expected control:** Worker resolve authoritative ownership, check user/delegation scope và deny trước khi đọc/ghi dữ liệu.
>
> **Observed gap:** Design chưa chỉ rõ nguồn owner; review thấy payload có thể đổi và worker sử dụng ID trực tiếp.
>
> **Impact:** User tenant B có thể yêu cầu service có đặc quyền đọc/export tenant A nếu đường gọi bị lợi dụng.
>
> **Owner/Action:** Export owner cập nhật thiết kế, policy và worker authorization; security QA bổ sung bypass/negative tests.
>
> **Closure evidence:** Approved design diff, worker effective config/code, negative test run, actual output check và independent retest.

### 13.4. Review decision matrix

| Tình trạng | Kết quả review | Hành động |
|---|---|---|
| Boundary/controls rõ, evidence thiết kế đủ | Design acceptable **trong scope** | Ghi assumptions và triển khai tests |
| Có bypass nghiêm trọng trong thiết kế | Changes required | Sửa control placement trước gate |
| Không có data flow hoặc ownership | Unknown/blocked | Thu thập diagram/source-of-truth |
| Có control nhưng chưa chạy | Implement/test pending | Giữ verification gap |
| Có test FAIL trên đường dữ liệu nhạy cảm | Finding/failed control | Triage, remediation và retest |
| Có ngoại lệ được phê duyệt | Exception tracked | Theo dõi expiry/risk, không coi PASS |

## 14. Đo coverage và chất lượng của trust-boundary review

### 14.1. Không dùng số boundary được vẽ thay cho độ an toàn

Ví dụ một kiến trúc có 25 boundary crossings **đã kiểm kê**:

- 16 crossings có review design đủ, requirements, control mapping và test plan.
- 5 crossings đã review nhưng còn thiếu ownership hoặc evidence.
- 4 crossings chưa được đánh giá.

Nếu định nghĩa tỷ lệ coverage review theo số crossing có review đủ trên số đã kiểm kê:

~~~text
Known boundary population = 25
Design review coverage = 16 / 25 = 64%
Reviewed with evidence/ownership gaps = 5
Not yet reviewed = 4
~~~

**64% không phải tỷ lệ hệ thống “an toàn”.** Nó chỉ nói 16/25 boundary đã biết có kết quả review theo điều kiện nêu. Nếu 25 boundary bỏ qua direct DB access và legacy support export, mẫu số chưa đầy đủ. Và nếu 16 crossing chỉ được review trên giấy, **không có căn cứ khẳng định 64% controls đã chạy hiệu quả**.

### 14.2. Các chỉ số hữu ích

| Metric | Đo điều gì? | Nguy cơ diễn giải sai |
|---|---|---|
| **Boundary population completeness** | Số crossing/flows được phát hiện so với nguồn inventory độc lập | Không có cách chắc chắn mọi đường đều đã vẽ |
| **Design review coverage** | Crossings có review record/control/risk mapping | Không phải runtime security PASS |
| **Threat scenario coverage** | Crossings có abuse cases phù hợp | Nhiều threat entries không đồng nghĩa phân tích đúng |
| **Control owner coverage** | Controls có chủ sở hữu và yêu cầu | Gán tên owner chưa chứng minh control hoạt động |
| **Testable requirement coverage** | Threat scenarios có acceptance tests | Tests tồn tại chưa chắc chạy |
| **Verified boundary coverage** | Crossing có implementation + negative/failure evidence trong scope | Phụ thuộc môi trường và bản phát hành |
| **Bypass test coverage** | Entry points và internal paths đã được thử trực tiếp | Một test ở gateway không bao phủ backend |
| **Unknown high-risk paths** | Boundary nhạy cảm còn thiếu dữ liệu/evidence | Không được tính “compliant” |
| **Evidence freshness** | Test/config còn khớp release, policy và data flows hiện tại | PASS cũ có thể hết giá trị |
| **Open findings by risk** | Các gaps còn lại và hạn xử lý | Đếm ticket đóng không chứng minh remediation |
| **Change-triggered review rate** | Thay đổi architecture có kéo theo review/retest? | Review hình thức có thể không bắt lỗi |

### 14.3. Định nghĩa denominator rõ

Một báo cáo coverage nên ghi:

1. Nguồn population: DFD, API gateway/service registry, code/routes, queue inventory, cloud resources, data flows, vendor registers.
2. Ngày chốt inventory và môi trường/release.
3. Quy tắc thế nào được tính là **một crossing** (ví dụ một source→destination với một trust contract và action scope).
4. Exclusions, N/A và các paths chưa có thông tin.
5. Tỷ lệ **design reviewed**, **implemented**, **tested**, **verified** tách biệt.
6. Risk-weighted gaps trọng yếu, không chỉ số lượng.

Không nên chia nhỏ một boundary thành nhiều dòng giống nhau chỉ để làm tăng số review PASS hoặc gộp nhiều crossing độc lập thành một dòng “API → backend” để che đường chưa kiểm tra.

## 15. Liên kết review với secure SDLC và continuous assurance

### 15.1. Khi nào cần review?

Trust-boundary review có giá trị nhất **trước khi quyết định kiến trúc bị khóa**, nhưng phải lặp lại khi hệ thống đổi:

- Thêm API endpoint, webhook, queue topic, worker hoặc data export.
- Thêm cloud account, vùng, cluster, tenant hoặc môi trường.
- Chuyển workload sang managed service hoặc vendor mới.
- Thay IdP, token format, authorization engine, role hoặc delegation.
- Chuyển DB schema/ownership mapping, data classification hoặc retention.
- Thay KMS/key hierarchy, encryption-at-rest hoặc secrets access.
- Thêm admin/support integration và break-glass path.
- Thay CI/CD, build runner, IaC hoặc production policy.
- Bật feature flag tạo ingress mới hoặc bypass rule hiện có.
- Có incident, pentest, audit finding hoặc abnormal data access.

### 15.2. Review gates theo vòng đời

| Giai đoạn | Câu hỏi | Đầu ra cần có |
|---|---|---|
| **Discovery/design** | Có asset/flow/boundary inventory và risk scenario? | DFD, register, threat model |
| **Architecture review** | Control placement và requirements có hợp lý? | Review decisions, ADR, gaps |
| **Implementation** | Security invariants được cài tại đúng crossing? | Code/config/IAM review, unit/integration tests |
| **Release gate** | Negative/bypass/failure tests đạt trong phạm vi phát hành? | Test evidence, change approval, known risks |
| **Operations** | Boundary vẫn đúng sau drift/policy/vendor change? | Runtime monitoring, access reviews, incidents |
| **Remediation** | Finding đã sửa và retest? | Closed-loop evidence và residual risk |

### 15.3. Definition of Ready cho một design review

Trước phiên review:

- DFD và scope/version có thể truy cập.
- Sensitive data/asset inventory đủ để hiểu luồng.
- Business use case và threat assumptions có owner.
- Danh sách actors, API routes, async jobs, vendor flows.
- Identity/authorization/KMS/audit ownership được xác định.
- Những phần thiếu được ghi là questions/unknowns thay vì tự giả định.

### 15.4. Definition of Done cho phần review thiết kế

Một review có thể được xem là hoàn tất **trên phạm vi thiết kế** nếu:

1. Các crossing đã xác định có ID và trust assumptions.
2. High-risk crossings được đánh giá threat scenarios hợp lý.
3. Critical controls có vị trí, owner và requirements.
4. Không còn kiến trúc **bypass không có xử lý/decision** trong phạm vi gate.
5. Có acceptance criteria, test plan và evidence expectations.
6. Findings/unknowns/assumptions và risk decisions có người chịu trách nhiệm.
7. Kết luận nêu rõ **design review**, không mạo nhận đã kiểm chứng production.

Điểm cần nhớ: **Hoàn thành design review** và **đạt assurance vận hành** là hai kết quả khác nhau.

### 15.5. Change impact analysis

Khi thay một thành phần, hỏi:

- Data flows và boundary IDs nào thay đổi?
- Có nguồn tin cậy mới, quyền mới hoặc đối tượng mới?
- Có người/tenant/vendor mới nhận dữ liệu?
- Control nào đổi vị trí hoặc không còn hiệu lực?
- Test cases và evidence nào phải chạy lại?
- Risk/exception nào hết điều kiện hoặc trở nên nghiêm trọng hơn?

Ví dụ: chuyển export storage sang một provider khác cần review lại **KMS, signed link, recipient authorization, vendor contract, retention, audit, region và download delivery**, không chỉ đổi storage URI.

## 16. Case study: một luồng export vượt nhiều ranh giới

### 16.1. Bối cảnh

InvoiceHub phục vụ 200 doanh nghiệp. Người dùng đăng nhập bằng IdP, chọn hóa đơn, yêu cầu export CSV; API gửi job tới queue, worker đọc hóa đơn từ DB và ghi file vào object storage. Gateway dùng OAuth token validation; kết nối service-to-service dùng mTLS.

Trong kiến trúc ban đầu, nhóm phát triển tin rằng **“Gateway và mTLS đã bảo vệ hệ thống”**.

Một security design review phát hiện các giả định:

1. Gateway chỉ kiểm tra user đã đăng nhập và có role `invoice_exporter`.
2. API nhận `tenantId` từ JSON request; không đối chiếu tenant owner của invoice.
3. Job queue chứa `invoiceIds` và `tenantId` mà không được ràng buộc với quyết định authorization đã xác minh.
4. Export Worker có DB credential đọc toàn bộ bảng và không kiểm tra tenant.
5. Download link không xác minh recipient sau khi được tạo.
6. User bị revoke role trước khi job chạy nhưng worker không reevaluate.
7. Audit chỉ ghi “Export requested”, không liên kết ID hóa đơn hoặc output file.
8. Support tool có thể gọi worker trực tiếp bằng identity đặc quyền.

### 16.2. Boundary mapping và attacker path

~~~mermaid
sequenceDiagram
  participant U as User tenant B
  participant G as Gateway
  participant A as Invoice API
  participant Q as Export queue
  participant W as Export worker
  participant D as Invoice DB
  participant O as Export storage
  U->>G: Export invoice IA (owner tenant A)
  G->>A: Valid user token, exporter role
  Note over G,A: Gateway AuthN passes, object AuthZ missing
  A->>Q: job(tenant=B or forged A, invoice=IA)
  Q->>W: Async job delivery
  Note over Q,W: Unverified job authorization context
  W->>D: Read invoice IA with broad DB principal
  D-->>W: Sensitive tenant A fields
  W->>O: Write CSV export
  O-->>U: Download link may be shared
~~~

Sơ đồ thể hiện **một đường tấn công giả định**, chưa phải proof-of-exploit thực tế. Review có thể xác định risk từ thiết kế và cần test được phép để kiểm chứng.

### 16.3. Phân tích từng crossing

| Boundary | Giả định sai | Hậu quả | Sửa thiết kế |
|---|---|---|---|
| **TB-01 Browser → API** | Role exporter đủ để xuất mọi invoice | Role không gắn tenant/object | Resolve resource owner, check action |
| **TB-02 API → Queue** | Job từ API luôn đáng tin | Unverified tenant/scope trong payload | Bind authorized scope + schema, producer identity |
| **TB-03 Worker → DB** | Workload mTLS và credential là đủ | Confused deputy đọc DB quá rộng | Worker check business AuthZ, least privilege |
| **TB-04 Worker → Storage** | File tạo ra tự động được bảo vệ | Output chứa dữ liệu sai tenant | Validate fields/records + ownership before write |
| **TB-05 Storage → User** | Có link là được download | Link phát tán/đọc sai người | Scoped delivery authorization và expiry |
| **TB-06 Support → Worker** | Internal support identity luôn hợp lệ | Direct bypass gateway | Separate support policy, JIT approvals và worker PEP |
| **TB-07 API/Worker → Audit** | Log “requested” chứng minh hoạt động đúng | Không biết actual data output | Decision–job–file correlation và protected logs |

### 16.4. Kế hoạch remediation

**Thiết kế API:** Thực hiện object-level authorization dựa trên owner authoritative, không tin tenant header/JSON. Phân biệt read/export/approve.

**Thiết kế job contract:** Job có job ID, submitter reference, action, resource scope, verified tenant, policy/version context, expiry hoặc recheck trigger. Producer được xác thực và queue ACL giới hạn.

**Thiết kế worker:** Worker không dùng payload như chứng cứ quyền; xác minh đúng nguồn context và kiểm tra lại theo policy tại execution. Resource data và policy phải gắn scope tenant.

**Thiết kế storage/delivery:** Chỉ ghi dữ liệu được phép. Download gateway hoặc link issuance kiểm tra recipient, scope và expiry theo chính sách; bảo vệ file at rest.

**Thiết kế support:** Tách đường privileged, dùng approved case/purpose, JIT/review và logging độc lập.

**Khôi phục/audit:** Khi queue/job trễ, role bị revoke hoặc audit down, có safe failure và trạng thái job rõ; đối chiếu output với decision.

### 16.5. Test suite sau khi triển khai

1. User tenant B không export invoice tenant A bằng real/guessed IDs.
2. Header, job payload hoặc tenant metadata giả mạo không thay policy outcome.
3. Worker direct invocation bằng principal thiếu quyền bị chặn.
4. Export job bị trì hoãn sau role revoke bị xử lý đúng theo policy.
5. Worker có quyền DB nhưng không vượt tenant scope.
6. File CSV chỉ chứa fields và records được phép.
7. Download bởi wrong recipient và link hết hạn bị chặn.
8. Một job lặp không tạo duplicate output trái policy.
9. Khi ownership lookup timeout, worker không tự permit.
10. Decision logs liên kết request, principal, job, resource, file và actual outcome.

### 16.6. Kết luận review phù hợp

Tại thời điểm mới phát hiện thiết kế sai:

> **Claim:** Security design review đã xác định những trust boundaries chính của luồng InvoiceHub export và phát hiện các đường khả dĩ bypass object-level authorization.
>
> **Argument:** API → Queue → Worker → DB và Worker → Storage/Download chuyển từ user context sang privileged service context nhưng thiết kế chưa chứng minh ràng buộc quyền nghiệp vụ với từng object.
>
> **Evidence:** DFD version, boundary register, policy/API contract, worker permission model và design review findings.
>
> **Limitations:** Chưa đủ bằng chứng về mức độ lộ dữ liệu thật hoặc operating effectiveness sau khi sửa. Không kết luận tất cả tenants đã bị xâm phạm; phải đánh giá production logs và kiểm thử có phép.
>
> **Action:** Giao owners, ưu tiên theo risk, sửa thiết kế, triển khai negative tests, theo dõi đến khi retest và review evidence.

Sau khi sửa, câu claim có thể được nâng lên **implementation/operating assurance** nếu có evidence phù hợp, nhưng vẫn phải ghi scope, version, kỳ đánh giá và paths chưa kiểm tra.

## 17. Những sai lầm thường gặp khi review trust boundary

| Sai lầm | Vì sao sai/thiếu? | Cách cải thiện |
|---|---|---|
| Vẽ một đường “trusted zone” bao quanh toàn backend | Internal services vẫn có scope/identity khác | Kiểm tra logical and administrative boundaries |
| Đồng nhất private network với trusted | Có thể có compromised workloads, lateral movement | Xác thực workload và authorize từng operation |
| Coi mTLS là đủ cho object authorization | mTLS không xác định user–resource privilege | Gắn user/delegation và kiểm tra object scope |
| Chỉ review browser → gateway | Worker, storage, admin và vendor có đường khác | DFD đầy đủ và flow inventory |
| Chỉ nhìn request mà bỏ response | Sensitive fields có thể trả sai nơi | Output filtering, redaction, download review |
| Tin tenant/role do client khai | Attacker có thể tự sửa thuộc tính | Authoritative source, integrity binding |
| Dùng shared service account có quyền toàn DB | Confused deputy và blast radius lớn | Least privilege, job-level authorization |
| Giả định mọi queue message đều tin cậy | Payload có thể sai/stale/replay | Producer ACL, schema, integrity, recheck |
| Chỉ ghi “TLS enabled” ở crossing | Chưa kiểm tra peer, cert, domain và action | AuthN/AuthZ/data/audit/failure contract |
| Không xem CI/CD/control plane | Một admin/build token có thể thay mọi security policy | SoD, provenance, approval và drift detection |
| Bỏ qua backup/log/analytics | Dữ liệu rời source sang vùng khác | Data lineage, classification và copy inventory |
| Không kiểm tra fail-open khi dependency lỗi | Timeout có thể biến thành permit | Define safe failure, fault injection |
| Không ghi assumptions và unknowns | Scope bị hiểu là hoàn tất | Review record có limitations và owner |
| Chỉ dùng STRIDE checklist cơ học | Không hiểu domain hoặc actual attacker paths | Abuse cases, business invariants |
| Bắt một control phải dùng mọi nơi | Không cân bằng risk và mục đích | Apply approved policy theo crossing |
| Bỏ qua privilege escalation qua support | Support access có phạm vi lớn | JIT/case binding/step-up/audit |
| Đếm số đường kẻ thay cho risk coverage | Quantity không chứng minh hiệu quả | Threat–control–test–evidence mapping |
| Chỉ đọc sơ đồ, không kiểm tra config | Thiết kế và thực tế có thể lệch | Verify effective policy/route/IAM/SDK |
| Đóng finding vì code đã merge | Chưa test runtime và side effects | Evidence-backed retest |
| Claim “Zero Trust an toàn” từ một review | Không có phạm vi/thời gian và proof | Claim–argument–evidence–limitations |

## 18. Phân công vai trò và chuẩn bị phiên review

### 18.1. Vai trò cần có

| Vai trò | Giá trị trong review |
|---|---|
| **System/solution architect** | Sở hữu kiến trúc, DFD, các phương án và design decisions |
| **Security architect/reviewer** | Dẫn dắt threat analysis, boundary controls và security requirements |
| **Application/service owner** | Giải thích API/worker paths, identity, error handling và implementation feasibility |
| **Data owner** | Xác nhận resource classification, tenant/ownership, fields, retention |
| **Identity/access owner** | Xác nhận IdP/PDP/PEP, token scope, revocation, privileged access |
| **Platform/SRE/cloud owner** | Giải thích network, KMS, IAM, CI/CD, logging, resilience |
| **Third-party/vendor owner** | Giải thích trách nhiệm tích hợp, data-sharing và evidence vendor |
| **Risk owner** | Chấp nhận hay xử lý rủi ro theo thẩm quyền |
| **QA/security assurance** | Chuyển design claims thành test/evidence plan và đánh giá giới hạn |
| **Audit/independent reviewer** | Đánh giá độc lập tính đầy đủ của bằng chứng trong phạm vi được giao |

### 18.2. Agenda mẫu cho một buổi review

1. **Context:** Nghiệp vụ, rủi ro trọng yếu, release/change và phạm vi.
2. **Architecture walkthrough:** Các use cases và luồng dữ liệu, không chỉ sơ đồ tĩnh.
3. **Boundary identification:** Nhận diện actors, identities, data, control plane, vendor và boundaries.
4. **Threat analysis:** STRIDE/abuse cases theo crossing có tác động lớn.
5. **Control review:** Control placement, fail-safe, authorization và data protection.
6. **Verification:** Tests cần thiết, runtime/config evidence, unknown paths.
7. **Decisions:** Required changes, risk/exception authority, owner và thời điểm retest.
8. **Summary:** Kết luận thiết kế có giới hạn, lưu register và phiên bản.

**Người điều phối review** không cần biến buổi họp thành kiểm tra tất cả dòng code. Nhưng không nên chấp nhận phát biểu “đã được service mesh xử lý” mà không xác định **control gì, ở đâu, bảo vệ crossing nào và ai sẽ chứng minh nó hoạt động**.

### 18.3. Ví dụ quyết định ADR

> **ADR: Recheck export authorization at worker execution**
>
> **Context:** Export job có thể ở queue lâu; quyền user và resource ownership thay đổi sau request submit.
>
> **Decision:** Worker xác minh lại subject/action/resource/tenant từ nguồn có thẩm quyền trước khi đọc restricted invoice; job metadata không tự cấp quyền.
>
> **Alternatives:** Chỉ kiểm tra ở API; token export có TTL; capability binding kèm revocation. Các lựa chọn cần đánh giá theo threat model/operational cost.
>
> **Consequences:** Tăng dependency tới policy/ownership service và latency; đổi lại giảm stale permit và confused-deputy risk.
>
> **Failure behavior:** Nếu không thể xác minh điều kiện bắt buộc, hold/deny job theo policy; không tạo file.
>
> **Verification:** Negative cross-tenant, revoked queued job, ownership-source outage, worker direct invocation và protected audit trace.
>
> **Revisit triggers:** Thay queue, permission model, export ownership hoặc data classification.

## 19. Bài tập thực hành

### Bài tập 1 — Xác định boundaries từ sơ đồ

Một hệ thống có Browser, API Gateway, Order API, Payment API, Redis, PostgreSQL, Kafka, KMS, CI/CD pipeline và vendor giao hàng.

**Yêu cầu:**

- Vẽ DFD và đánh dấu ít nhất **sáu trust-boundary crossings**.
- Với mỗi crossing, ghi source/destination, data class, principal, action và trust assumption.
- Phân biệt boundary logic với network boundary và failure domain.
- Nêu **hai đường indirect data flow** thường bị bỏ sót.

**Tiêu chí tự kiểm tra:** Không đặt mọi service trong private subnet thành một nhóm “trusted” không cần xác minh. Có ít nhất một boundary cho control plane và một boundary cho vendor.

### Bài tập 2 — STRIDE cho webhook thanh toán

Payment Provider gọi webhook để báo giao dịch thành công. Một attacker có thể gửi request tới cùng endpoint và phát lại callback cũ.

**Yêu cầu:**

- Phân tích STRIDE tại Provider → Webhook API.
- Xác định authentication/integrity, replay/idempotency và business state verification.
- Viết requirements chống callback giả và double processing.
- Đề xuất negative tests với signature sai, event lặp, event hết hạn và payload malformed.
- Nêu evidence cần có để kết luận webhook path được bảo vệ.

**Tiêu chí tự kiểm tra:** Không coi HTTPS là đủ để xác minh nội dung webhook; kiểm tra dựa trên hợp đồng xác thực thật của provider.

### Bài tập 3 — Confused deputy trong export worker

Một Export Worker có thể đọc tất cả tenant trong DB. User chỉ có quyền trong tenant B nhưng có thể gửi invoice ID thuộc tenant A qua API.

**Yêu cầu:**

- Vẽ attacker path browser → API → queue → worker → DB → export storage.
- Chỉ rõ crossing nào chuyển **user privilege** thành **service privilege**.
- Viết yêu cầu kiểm tra resource ownership và job delegation.
- Thiết kế ít nhất **bốn test**: authorized, cross-tenant, direct worker invocation và stale queued job.

**Tiêu chí tự kiểm tra:** Có kiểm tra actual file/DB state, không chỉ status code; token của worker không thay authorization nghiệp vụ.

### Bài tập 4 — Review token forwarding

Service A nhận access token từ client và chuyển nguyên token sang Service B. B chỉ kiểm tra signature, không kiểm tra audience/scope. Một route nội bộ cho phép gọi B trực tiếp.

**Yêu cầu:**

- Nhận diện spoofing/elevation và token substitution risks.
- Đề xuất mô hình delegation/token exchange hoặc binding phù hợp nếu kiến trúc yêu cầu, có kiểm tra audience/expiry/action.
- Chỉ rõ PEP ở A, B và data layer.
- Thiết kế tests cho token đúng chữ ký nhưng sai audience, thiếu scope và direct route.

**Tiêu chí tự kiểm tra:** Không lấy “JWT hợp lệ” làm đồng nghĩa “được phép gọi mọi API”.

### Bài tập 5 — SSRF từ parser tài liệu

Một service lấy URL do user gửi, tải file về để phân tích. Service có quyền truy cập metadata service và internal admin APIs.

**Yêu cầu:**

- Đánh dấu trust boundary user URL → server egress.
- Xác định những vùng mạng/internal endpoints có thể bị truy cập.
- Đề xuất giới hạn destination, URL canonicalization, DNS resolution checks, redirect handling, egress policy và resource limits theo thiết kế.
- Viết negative tests **có phép** cho internal addresses và redirect-to-internal.

**Tiêu chí tự kiểm tra:** Không dựa vào string prefix `https://` hoặc domain allowlist hời hợt làm bằng chứng đầy đủ; có egress enforcement.

### Bài tập 6 — CI/CD và control-plane boundary

Một pipeline chạy test cho pull request từ người ngoài, đồng thời được cấu hình production deployment token trong cùng runner.

**Yêu cầu:**

- Phân tích actor/trust boundary giữa **untrusted contribution, build runner, artifact registry và production**.
- Xác định các quyền cần tách, secret exposure paths, artifact provenance và approval.
- Viết security requirements cho release integrity và không cho PR untrusted dùng production credential.
- Nêu evidence config/negative tests và phương án khắc phục.

**Tiêu chí tự kiểm tra:** Tách rõ quyền merge, quyền build, quyền ký, quyền deploy và quyền thay audit/controls.

### Bài tập 7 — Mô hình vendor và dữ liệu

Một vendor phân tích hành vi khách hàng nhận event qua API và trả risk scores. Tổ chức dùng risk score để xét duyệt giao dịch.

**Yêu cầu:**

- Đánh giá outbound data boundary về data minimization/classification/retention.
- Đánh giá inbound score như **untrusted external signal** cần source, signature/identity, freshness, range và failure handling.
- Đặt câu hỏi về hợp đồng trách nhiệm, data retention, logging và vendor outage.
- Viết một design claim và **limitations** nếu chưa có bằng chứng vendor.

**Tiêu chí tự kiểm tra:** Vendor trả “low risk” không phải authorization tuyệt đối hoặc chứng cứ identity đã được xác minh.

### Bài tập 8 — Missing KMS và audit pipeline

KMS có lúc unavailable; khi đó ứng dụng định ghi một file export plaintext để “không chặn khách hàng”. Đồng thời audit pipeline lỗi và worker dự định bỏ log.

**Yêu cầu:**

- Chỉ rõ boundary app→KMS, worker→storage và worker→audit.
- Phân loại confidentiality/accountability/security invariants.
- Viết safe-failure contract theo nghĩa vụ được phê duyệt.
- Thiết kế fault-injection tests chứng minh không có plaintext fallback không được phép và không silent audit loss.

**Tiêu chí tự kiểm tra:** Không hy sinh confidentiality hoặc audit bằng một fallback không có thẩm quyền chỉ vì muốn tăng availability.

### Bài tập 9 — Chấm review và viết assurance claim

Review có 25 boundary crossings đã biết: 16 được review đủ, 5 thiếu evidence/owner, 4 chưa review. Một legacy admin endpoint chưa được lập inventory. Nhóm dự án đề nghị ghi “Trust boundaries đã pass 100%”.

**Yêu cầu:**

- Tính design review coverage theo population đã biết.
- Giải thích tại sao không thể kết luận toàn bộ hệ thống an toàn.
- Viết **Claim–Argument–Evidence–Limitations** đúng với hiện trạng.
- Lập findings, owner, yêu cầu tìm endpoint legacy và triggers cho re-review.

**Tiêu chí tự kiểm tra:** Không gộp unknown/exceptions vào PASS; phân biệt design review với operating effectiveness.

### Bài tập 10 — Thiết kế một buổi review end-to-end

Một kiến trúc mới có mobile client, IdP, API gateway, tenant-aware service, queue, worker, database, KMS, notification vendor và support admin portal. Chưa có security review.

**Yêu cầu:**

- Chuẩn bị **agenda, participants, DFD và trust-boundary register**.
- Chọn năm crossings có rủi ro cao nhất và giải thích thứ tự ưu tiên.
- Với mỗi crossing, viết một threat scenario, requirement, control candidate và evidence plan.
- Chọn ba negative tests và một fault-injection scenario.
- Đưa ra decision categories, owner, ngày kiểm tra lại và sign-off có giới hạn.

**Tiêu chí tự kiểm tra:** Bài review phải xuất ra **quyết định có thể hành động**, không chỉ sơ đồ và checklist.

## 20. Checklist review trust boundary

### 20.1. Mục tiêu và phạm vi

- **Objective:** Đã rõ tài sản, nghiệp vụ, loại dữ liệu và security objectives?
- **Architecture version:** DFD/topology/release đã được cố định và có owner?
- **Flows:** Có happy path, admin, batch, queue, vendor, backup, logging và failure flows?
- **Population:** Có đối chiếu API routes, queues, cloud resources và integrations để tìm flows bị bỏ sót?
- **Exclusions:** Những phần ngoài scope/unknown có được ghi và gán owner?

### 20.2. Ranh giới và identity

- **Trust assumptions:** Mỗi crossing có mô tả điều gì được tin/không được tin?
- **Identity:** User, workload, administrator và delegated caller được xác minh theo source phù hợp?
- **Tokens:** Issuer, audience, expiry, signature, scope và revocation được kiểm tra?
- **Internal paths:** mTLS/private network không bị coi thay cho authorization?
- **Tenant boundaries:** Ownership/resource scope được resolve từ nguồn đáng tin?
- **Authorization:** PEP có kiểm tra action/object/field tại đúng đường xử lý?
- **Admin plane:** Người thay policy/deploy/config/secrets có phân quyền và SoD phù hợp?
- **Bypass:** Có đường gọi trực tiếp API/worker/DB/storage mà không qua kiểm tra?

### 20.3. Data integrity, confidentiality và input

- **Payload provenance:** Có xác minh source, schema, signature/MAC hoặc token binding khi cần?
- **Validation:** Input từ client/queue/vendor có bị coi untrusted và kiểm tra lại?
- **Replay/idempotency:** Webhook, job, payment hoặc retry có chống duplicate business effects?
- **Parser/SSRF:** URL, file upload, deserialization và redirects có biện pháp phù hợp?
- **Data minimization:** Có chỉ chuyển fields cần thiết qua vendor/analytics boundary?
- **Transport protection:** TLS/mTLS và certificate validation theo baseline?
- **Storage/crypto:** Data classification, key/secret scope và bản sao được đánh giá?
- **Output:** Response, export file, error, cache và signed link có tránh cross-tenant leakage?

### 20.4. Audit, failure và recovery

- **Audit:** Event có principal/action/resource/outcome/version và correlation được bảo vệ?
- **Audit permissions:** Principal thực hiện thao tác có thể xóa/sửa log bất hợp lệ không?
- **Telemetry failure:** Logging mất có detect và hành vi theo policy?
- **PDP/IdP/KMS outage:** Không tạo authorization/crypto fallback trái quy tắc?
- **Async/TOCTOU:** Job delayed, quyền revoke, resource đổi owner có recheck phù hợp?
- **Resilience:** Quota, timeout, bounded retry và rate limits bảo vệ high-risk boundaries?
- **Failover:** Khi đổi region/account, identities, keys và policies vẫn được xác minh?
- **Incident:** Có containment, key/token revocation, review và evidence preservation?

### 20.5. Assurance và quản trị

- **Threat model:** Có STRIDE/abuse cases theo crossing và attacker capability?
- **Requirements:** Threats có testable security requirements và acceptance criteria?
- **Control placement:** Controls nằm đúng chỗ và không có bypass?
- **Owners:** Business/system/security/data/vendor/control/risk owners được phân công?
- **Tests:** Positive, negative, direct bypass, failure/revocation và E2E effects được lên kế hoạch?
- **Design evidence:** DFD, boundary register, decisions và assumptions đầy đủ?
- **Implementation evidence:** Có effective config/code/policy và release linkage?
- **Operating evidence:** Có runtime logs, test results và review trong kỳ?
- **Findings:** Gaps, severity, owner, risk decisions và remediation/retest được lưu?
- **Claims:** Kết luận chỉ trong scope, version, môi trường và thời kỳ có bằng chứng?
- **Continuous review:** Có trigger khi thêm API, queue, vendor, tenant, data flow hoặc policy?

## 21. Tổng kết

Khi review một trust boundary, cách đặt câu hỏi hiệu quả không phải “chỗ này đã có firewall chưa?” mà là:

1. **Ai** gửi request/dữ liệu, bằng chứng identity nào được xác minh?
2. **Họ được phép làm gì** trên resource/tenant/action nào, theo source-of-truth và policy nào?
3. **Dữ liệu đi qua đâu** và ở điểm nào một bên có thể giả mạo, sửa, sao chép hoặc làm lặp?
4. **Control nào** kiểm tra ngay trước thao tác nhạy cảm, có bị bypass bởi đường khác không?
5. **Khi một dependency lỗi**, hệ thống có giữ security invariants hay vô tình fail-open?
6. **Evidence nào** chứng minh thiết kế, implementation và operating behavior, còn giới hạn nào chưa đánh giá?

**Điều cần ghi nhớ:** **Review trust boundary** là quá trình xem xét các **giả định tin cậy tại mọi luồng dữ liệu và quyền**, rồi xác định yêu cầu và controls phù hợp để ngăn giả mạo, thay đổi trái phép, lộ dữ liệu, nâng quyền và lan truyền sự cố. Trong **security design review**, một boundary được vẽ đúng là bước đầu; trong **security assurance**, chỉ có thể khẳng định kiểm soát hiệu quả khi **thiết kế có lập luận, không có đường bypass chưa xử lý, test kiểm tra actual outcomes và bằng chứng đủ tin cậy trong phạm vi đã công bố**. Mọi khoảng trống cần có owner, quyết định xử lý và retest khi hệ thống thay đổi.
