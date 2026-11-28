# Quản lý quyền truy cập hệ thống giám sát và bộ dữ liệu

Một ứng dụng Spring AI có thể tạo ra logs, metrics, traces, evaluation cases, prompt versions, kết quả judge và các báo cáo chất lượng. Những dữ liệu này thường được tập trung vào observability platform và evaluation store để đội vận hành, kỹ sư AI, reviewer và quản trị viên cùng sử dụng. Nếu mọi người dùng chung một tài khoản datasource, dashboard chỉ lọc bằng biến giao diện hoặc API export không kiểm tra quyền, người xem có thể đọc prompt, tài liệu RAG, dữ liệu khách hàng hoặc kết quả đánh giá ngoài phạm vi công việc.

**Quyền xem phải được thực thi tại backend dựa trên danh tính, tenant scope, vai trò, mục đích và loại dữ liệu.** Dashboard, trace ID, link chia sẻ hay bộ lọc trong truy vấn chỉ là cách điều hướng; chúng không phải ranh giới bảo mật. Cần quản lý cả người dùng, service account, collector, exporter, evaluator và reviewer, đồng thời ghi audit cho các thao tác đọc, tìm kiếm, tải xuống và thay đổi quyền.

Bài này thuộc chương **Bảo vệ dữ liệu** của module **SPRING_AI_EVALUATION_OBSERVABILITY**. Module đánh giá chất lượng ứng dụng Spring AI bằng dataset, tiêu chí relevance, fact checking và kiểm thử RAG/tool calling; đồng thời đo metrics, traces, chi phí và độ trễ để phát hiện nguyên nhân suy giảm qua từng phiên bản prompt, model và pipeline. Bài tập trung vào quản lý quyền truy cập observability systems và evaluation datasets sao cho người đúng xem đúng dữ liệu, đúng mục đích và trong đúng thời hạn.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt authentication, authorization, tenant scope và data classification.
2. Xây dựng RBAC/ABAC cho logs, metrics, traces, evaluation datasets và reports.
3. Thiết kế quyền tối thiểu cho on-call, AI engineer, evaluator, reviewer, data steward và platform admin.
4. Bảo vệ truy vấn, API, dashboard, trace links, alerts, exports và shared links ở backend.
5. Quản lý danh tính service-to-service của application, collector, exporter và evaluation workers.
6. Phân tách quyền đọc telemetry vận hành với quyền đọc raw evaluation content.
7. Áp dụng tenant-aware authorization và purpose-bound access.
8. Quản lý break-glass access, audit trail, access review và thu hồi quyền.
9. Viết Spring Security examples và kiểm thử truy cập hợp lệ/không hợp lệ.
10. Điều tra sự cố lộ dữ liệu mà không mở rộng thêm phạm vi truy cập.

## 2. Vì sao hệ thống giám sát và bộ dữ liệu cần phân quyền?

Observability không chỉ chứa số liệu kỹ thuật. Một trace có thể có prompt, retrieved chunks, tool arguments hoặc exception details. Một evaluation case có thể chứa câu hỏi thật, câu trả lời chuẩn, evidence, customer references và nhận xét của reviewer. Một dashboard chi phí có thể tiết lộ tenant nào sử dụng nhiều model hoặc đang gặp lỗi.

| Tài sản | Nội dung | Rủi ro nếu quyền quá rộng |
|---|---|---|
| **Metrics** | Request count, latency, token usage, cost, error rate. | Suy ra hoạt động, quy mô hoặc hành vi của tenant. |
| **Traces** | Span attributes/events, provider calls, retrieval/tool flow. | Lộ prompt, document references, arguments hoặc PII. |
| **Logs** | Structured fields, exception, audit và application messages. | Lộ secrets, raw payload hoặc dữ liệu nghiệp vụ. |
| **Evaluation datasets** | Inputs, expected answers, gold facts, evidence, labels. | Đọc dữ liệu sản xuất hoặc benchmark thuộc tenant khác. |
| **Evaluation results** | Judge rationale, scores, human annotations, failure examples. | Lộ nội dung case hoặc nhận xét nội bộ. |
| **Prompt/model registry** | Prompt templates, model configuration, release metadata. | Lộ system instructions, endpoint và cấu hình nhạy cảm. |
| **Reports/exports** | CSV, JSON, attachments, screenshots. | Tạo bản sao khó thu hồi và chia sẻ ngoài phạm vi. |
| **Alerts/notifications** | Error snippets, trace links, tenant/service context. | Gửi nội dung nhạy cảm tới người nhận không đúng. |

### 2.1. Quyền truy cập là một phần của data lifecycle

Phân quyền không chỉ diễn ra khi mở dashboard. Nó áp dụng lúc ingest, query, search, drill-down, export, share, annotate, delete và restore. Một user có thể được phép xem metric tổng hợp nhưng không được mở trace chi tiết; evaluator có thể đọc một dataset đã giao nhưng không có quyền sửa prompt production; platform admin có thể quản lý backend nhưng không mặc nhiên cần đọc raw conversation.

### 2.2. Không dùng một vai trò quản trị cho mọi công việc

Tài khoản admin dùng chung tạo phạm vi quyền lớn và làm audit khó quy trách nhiệm. Nên tách vai trò quản trị hạ tầng, quản trị dữ liệu, đánh giá chất lượng và vận hành dịch vụ. Quyền đặc biệt chỉ được cấp khi có nhiệm vụ, thời hạn và audit tương ứng.

## 3. Authentication và authorization

Hai bước này giải quyết hai câu hỏi khác nhau:

- **Authentication (AuthN):** xác minh người hoặc service đang gọi là ai.
- **Authorization (AuthZ):** quyết định danh tính đó được làm gì trên tài nguyên nào, trong tenant và mục đích nào.

Ví dụ: một người đăng nhập thành công vào observability platform (AuthN) nhưng chỉ được đọc traces của service support-ai trong tenant đã được cấp (AuthZ). Đăng nhập hợp lệ không đồng nghĩa được xem tất cả dữ liệu.

### 3.1. Danh tính người dùng

Ứng dụng thường xác thực người dùng qua OIDC/OAuth2 identity provider hoặc SSO. Backend cần xác minh issuer, audience, signature, expiry và các claim theo cấu hình. Không tự decode JWT rồi tin payload; decode không xác minh chữ ký.

### 3.2. Danh tính máy và service account

Application, collector, exporter, evaluation worker và scheduled job cần danh tính riêng. Ưu tiên workload identity hoặc credential ngắn hạn nếu nền tảng hỗ trợ. Không dùng access token của developer làm credential cho service chạy production.

### 3.3. Authorization ở mỗi ranh giới

Một request có thể đi qua gateway, observability backend, datasource, query API và object store. Mỗi backend cần biết identity hoặc nhận assertion được xác thực từ gateway tin cậy. Không coi header do browser tự gửi hoặc span attribute là bằng chứng quyền.

## 4. Xác định tài nguyên và phạm vi quyền

Trước khi thiết kế role, cần liệt kê tài nguyên có thể được đọc hoặc thay đổi.

| Resource | Ví dụ operation |
|---|---|
| **Service** | View telemetry của service cụ thể; xem service metadata. |
| **Environment** | Đọc staging; đọc production; xem deployment comparison. |
| **Signal** | Query metrics, logs hoặc traces. |
| **Trace** | Mở trace, xem span detail, tải trace JSON. |
| **Dataset** | List dataset, read case, add annotation, create version. |
| **Evaluation run** | Start run, read result, compare versions, cancel run. |
| **Prompt/model version** | View, propose change, approve, publish. |
| **Report** | View, export, share, delete. |
| **Access policy** | Grant/revoke membership, assign role, change retention. |
| **Audit record** | Search access events, export audit evidence. |

Phạm vi có thể gồm tenant, project, service, environment, dataset, classification, region và time range. Một quyền như TRACE_READ nên được hiểu cùng scope; không có scope rõ thì dễ biến thành quyền đọc toàn hệ thống.

## 5. RBAC và ABAC

### 5.1. Role-Based Access Control (RBAC)

RBAC gán permissions cho role, sau đó gán role cho user hoặc service identity. Ví dụ:

```text
ROLE_ONCALL:
  - METRIC_READ
  - TRACE_READ_REDACTED
  - LOG_READ_REDACTED

ROLE_EVALUATOR:
  - DATASET_READ_ASSIGNED
  - EVALUATION_RUN_CREATE
  - EVALUATION_RESULT_READ

ROLE_REVIEWER:
  - DATASET_CASE_READ_ASSIGNED
  - HUMAN_LABEL_WRITE

ROLE_DATA_STEWARD:
  - DATASET_POLICY_READ
  - RETENTION_MANAGE
  - DELETION_REQUEST_REVIEW
```

Đây là tên role/permission minh họa, không phải role mặc định của Spring hay một observability vendor. Role phải được ánh xạ tới phạm vi tenant/project/service và phân loại dữ liệu.

### 5.2. Attribute-Based Access Control (ABAC)

ABAC quyết định dựa trên thuộc tính của principal, resource, action và context. Ví dụ một policy có thể cho phép nếu:

```text
principal.role contains EVALUATOR
AND principal.tenant == resource.tenant
AND resource.classification <= principal.clearance
AND action == DATASET_CASE_READ
AND request.purpose == APPROVED_EVALUATION
```

ABAC hữu ích khi một role có thể truy cập nhiều tenant/project khác nhau hoặc dữ liệu có classification khác nhau. Các thuộc tính phải đến từ nguồn đáng tin: principal đã xác thực, resource metadata được quản lý và context được backend tạo/kiểm chứng.

### 5.3. Kết hợp RBAC và ABAC

RBAC xác định nhóm quyền cơ bản; ABAC giới hạn tài nguyên và bối cảnh. Ví dụ, role EVALUATOR cho phép đọc evaluation cases, nhưng ABAC chỉ cho phép đọc dataset được giao, thuộc tenant đã xác minh và đang trong thời gian assignment.

### 5.4. Deny by default

Nếu không có policy cho phép rõ ràng, từ chối truy cập. Nếu policy service không khả dụng, không fallback sang quyền rộng. Backend có thể trả lỗi 403/404 theo chính sách không tiết lộ sự tồn tại của tài nguyên.

## 6. Least privilege và ma trận vai trò

Người dùng chỉ nên có quyền tối thiểu cần thiết cho công việc hiện tại. Bảng sau là điểm khởi đầu; mỗi quyền vẫn phải được giới hạn theo tenant, service, environment và classification.

| Vai trò | Metrics | Logs/traces | Evaluation content | Quản lý policy |
|---|---|---|---|---|
| **On-call engineer** | Đọc scope được giao. | Đọc bản đã redacted; raw chỉ qua incident approval. | Không mặc định đọc. | Không. |
| **AI engineer** | Đọc metrics và traces kỹ thuật. | Đọc bản đã giảm thiểu. | Đọc dataset synthetic/được giao. | Đề xuất thay đổi. |
| **Evaluator service** | Ghi evaluation metrics được phép. | Không cần đọc toàn bộ logs. | Đọc case trong run/tenant scope. | Không. |
| **Human reviewer** | Không cần truy cập trực tiếp. | Không mặc định đọc. | Đọc sample được giao; ghi label. | Không. |
| **Data steward** | Xem aggregate phục vụ governance. | Chỉ khi cần điều tra. | Quản lý purpose, retention, access. | Có trong phạm vi dữ liệu. |
| **Platform admin** | Quản lý hạ tầng. | Quản lý pipeline/backend. | Raw content cần elevated access riêng. | Quản trị platform, có audit. |
| **Security auditor** | Đọc bằng chứng được cấp. | Đọc audit/security events. | Chỉ khi scope audit yêu cầu. | Đọc policy và access history. |

### 6.1. Tách quyền đọc và quyền ghi

DATASET_READ không nên tự động bao gồm DATASET_EDIT, DATASET_DELETE hoặc DATASET_EXPORT. PROMPT_VIEW khác PROMPT_PUBLISH. TRACE_READ khác TRACE_SHARE. Dùng permissions riêng để giảm tác động của tài khoản bị chiếm.

### 6.2. Quyền có thời hạn

Role nhạy cảm nên có expiry hoặc periodic review. Temporary assignment cho evaluator/reviewer cần ngày bắt đầu, kết thúc, dataset scope và owner. Thu hồi assignment khi run hoàn tất hoặc người dùng rời nhóm.

### 6.3. Không chia sẻ tài khoản

Mỗi người dùng cần identity riêng để audit biết ai đã đọc/export. Service account cũng phải riêng theo workload và môi trường, không dùng chung giữa staging và production.

## 7. Phân loại dữ liệu và mức truy cập

Một policy truy cập nên xét classification của dữ liệu:

| Mức | Ví dụ | Cách truy cập gợi ý |
|---|---|---|
| **Public/low risk** | Aggregate latency không có định danh. | Có thể chia sẻ rộng trong tổ chức. |
| **Internal** | Service topology, model family, release metadata. | Nhân viên nội bộ có nhu cầu công việc. |
| **Confidential** | Tenant-level metrics, redacted traces, evaluation scores. | Role và tenant/project scope cụ thể. |
| **Restricted** | Raw prompt, PII, retrieved private documents, tool payload. | Purpose-bound, assignment/elevated access, audit và retention ngắn. |
| **Secret** | API keys, passwords, bearer tokens, private keys. | Secret manager/identity system; không hiển thị trong observability UI. |

Classification cần được áp dụng nhất quán từ ingestion tới query/export. Nếu một trace có một span chứa Restricted content, cả trace view hoặc export có thể cần được xử lý theo mức nhạy cảm cao nhất hoặc theo field-level policy.

## 8. Bảo vệ query và API ở backend

Đây là ranh giới quan trọng nhất: authorization phải được kiểm tra tại nơi thực sự trả dữ liệu.

### 8.1. Không chỉ lọc ở dashboard

Dashboard variable tenant=A có thể bị đổi thành tenant=B. Người dùng cũng có thể gọi query API trực tiếp hoặc sửa request từ browser. Nếu datasource credential đọc được tất cả tenants, filter trong giao diện không ngăn được truy cập chéo tenant.

Backend/gateway phải:

1. Xác thực người gọi.
2. Resolve tenant membership và role.
3. Xác định resource/signal đang được truy vấn.
4. Áp dụng tenant/service/environment/classification scope ở query layer.
5. Kiểm tra quyền với drill-down, export và linked resources.
6. Ghi audit event cho hành động nhạy cảm.

### 8.2. Query rewriting và policy enforcement

Một gateway có thể thêm predicate theo principal đã xác thực trước khi query tới backend. Cần bảo đảm user không thể ghi đè predicate bằng raw query, subquery, alternate API hoặc datasource route khác. Nếu backend hỗ trợ native tenant authorization, ưu tiên enforcement ở backend và dùng gateway như lớp bổ sung.

### 8.3. Không tin resource ID hoặc trace ID là quyền

Trace ID, dataset ID và case reference chỉ là identifiers. Backend vẫn phải kiểm tra caller có quyền đọc resource thuộc tenant/project đó. ID khó đoán không phải authorization.

### 8.4. API phải bảo vệ mọi operation

Kiểm tra riêng list, get-by-ID, search, query, export, share, delete, annotate và bulk operations. Một endpoint list có filter đúng nhưng endpoint get-by-ID không kiểm tra tenant vẫn có thể lộ dữ liệu.

## 9. Phân quyền logs, metrics và traces

Ba tín hiệu có cấu trúc và rủi ro khác nhau; quyền đọc nên tách theo mức cần thiết.

### 9.1. Metrics

Metrics thường được dùng cho dashboard và alert. Có thể cấp quyền đọc aggregate rộng hơn, nhưng tenant-level labels, exemplars hoặc dimensions hiếm có thể tiết lộ hành vi của khách hàng. Kiểm soát query, cardinality, export và khả năng drill-down từ metric sang trace.

### 9.2. Logs

Logs có thể chứa exception, user content, request context và secrets do logging sai. Ưu tiên chỉ cho on-call đọc structured logs đã giảm thiểu; raw logs cần quyền hẹp, thời gian giới hạn và audit. Không dùng một log index chung với quyền đọc toàn bộ nếu có dữ liệu Restricted.

### 9.3. Traces

Traces có thể kết nối model call, retriever và tools. Quyền đọc trace metadata có thể rộng hơn quyền đọc span events hoặc content attributes. Nếu backend hỗ trợ field-level filtering, dùng policy để ẩn raw prompt/response khỏi role thông thường. Nếu không, tách raw evaluation content ra store riêng.

### 9.4. Linked signals

Một metric exemplar có thể mở trace; log record có thể có trace ID; alert có thể chứa deep link. Quyền phải được kiểm tra lại khi người dùng đi theo link. Không để quyền đọc metrics tự động cấp quyền đọc trace content.

## 10. Dashboard, export, share link và notification

Một dashboard có thể an toàn trong giao diện nhưng không an toàn ở các đường phụ.

### 10.1. Dashboard

- Datasource credential phải có scope phù hợp với người dùng hoặc gateway policy.
- Dashboard variables chỉ là tiện ích, không phải security control.
- Không nhúng static admin token vào browser.
- Hạn chế query editor/raw query cho role không cần.
- Ẩn panel không thay authorization ở API.
- Test dashboard bằng cách sửa variable, query và resource ID.

### 10.2. Export

CSV, JSON, PDF và screenshots tạo bản sao ngoài retention/backend ban đầu. Kiểm tra quyền export riêng, giới hạn field/row/time range, watermark hoặc audit nếu cần, và áp dụng policy lưu trữ cho file xuất. Không gửi raw evaluation content vào email/chat chỉ vì người nhận có quyền xem dashboard.

### 10.3. Shared links

Link chia sẻ phải có expiry, scope, recipient/access policy và khả năng revoke. Nếu dùng bearer link, coi link là credential; không đưa vào logs hoặc ticket công khai. Ưu tiên link yêu cầu đăng nhập và kiểm tra authorization mỗi lần mở.

### 10.4. Alerts và notifications

Alert payload nên chứa error category, service, time window và link được bảo vệ. Tránh đính kèm prompt, document chunk hoặc raw exception. Kiểm tra recipient groups và quyền mở link trước khi gửi.

## 11. Quản lý quyền truy cập evaluation datasets

Evaluation store cần policy riêng vì case có thể chứa nội dung chi tiết hơn operational telemetry.

### 11.1. Quyền theo dataset và operation

Phân tách các quyền:

```text
DATASET_LIST
DATASET_METADATA_READ
DATASET_CASE_READ
DATASET_CASE_ANNOTATE
DATASET_CASE_CREATE
DATASET_VERSION_CREATE
DATASET_EXPORT
DATASET_DELETE
EVALUATION_RUN_CREATE
EVALUATION_RESULT_READ
```

Không gộp tất cả thành DATASET_ADMIN. Ví dụ reviewer chỉ cần DATASET_CASE_READ cho cases được giao và DATASET_CASE_ANNOTATE; họ không cần export toàn bộ dataset hoặc xóa version.

### 11.2. Dataset scope

Dataset access có thể giới hạn theo tenant/workspace, project/product feature, dataset classification, dataset version và evaluation run, case assignment hoặc reviewer group, environment/source kind (synthetic, curated, production-derived), purpose và thời hạn.

### 11.3. Case-level authorization

Một user có thể được đọc metadata của dataset nhưng không được đọc mọi case. Backend cần kiểm tra assignment, tenant scope và classification khi lấy từng case, kể cả endpoint bulk read. Không trả cả dataset rồi dựa vào UI để ẩn những case không được phép.

### 11.4. Raw content và redacted content

Có thể có hai quyền riêng: đọc redacted case và đọc raw case. Raw access nên yêu cầu purpose cụ thể, elevated role, thời hạn ngắn và audit. Nếu một case đã được redacted đủ để review, không cấp raw access chỉ vì tiện.

### 11.5. Evaluation result không đồng nghĩa với quyền xem evidence

Một user có thể được xem aggregate score nhưng không được mở gold answer, source documents hoặc judge rationale. Tách EVALUATION_RESULT_READ khỏi EVALUATION_EVIDENCE_READ.

## 12. Quyền truy cập trong online và offline evaluation

### 12.1. Online evaluator

Evaluator chạy trong request path chỉ nên nhận input đã được policy cho phép. Service identity của evaluator có quyền đọc đúng case/context cần thiết, không có quyền query toàn bộ tenant. Output thường là verdict, score, criterion và references đã chuẩn hóa.

### 12.2. Offline evaluation worker

Worker xử lý batch cần workload identity riêng, dataset assignment, tenant scope và run-specific permission. Job message phải được xác thực; worker không tin dataset ID hoặc tenant ID tùy ý từ message. Kết quả ghi về store phải giữ provenance và access scope tương ứng.

### 12.3. LLM-as-judge provider

Khi gửi case tới model judge bên ngoài, đây là một lần chia sẻ dữ liệu sang processor khác. Quyền đọc dataset nội bộ không tự động cho phép export content tới provider. Cần policy riêng về data minimization, approved provider, region, purpose, retention và audit.

### 12.4. Human review

Reviewer chỉ thấy case được giao, nội dung đã redacted nếu đủ dùng và rubric version tương ứng. Reviewer không nên tải hàng loạt raw dataset hoặc xem tenant khác qua URL thay đổi. Ghi audit khi mở raw content, thay label hoặc export.

## 13. Service identities, collector và exporter

Không chỉ người dùng cần phân quyền. Hạ tầng observability cũng là một nhóm principal có quyền đọc/ghi dữ liệu.

### 13.1. Tách identity theo workload

| Workload | Quyền tối thiểu gợi ý |
|---|---|
| **Spring AI application** | Gửi telemetry tới collector; không query backend nếu không cần. |
| **OTel Collector** | Nhận telemetry từ workload được phép và export tới đích đã cấu hình. |
| **Metrics scraper** | Scrape endpoint/target được cấp. |
| **Evaluation worker** | Đọc dataset/run được giao và ghi kết quả vào đúng scope. |
| **Report generator** | Đọc aggregate/result được phép, ghi report vào namespace riêng. |
| **Dashboard datasource** | Query scope được backend/gateway giới hạn; tránh admin-wide credential. |

### 13.2. Collector không phải người dùng có toàn quyền

Collector cần nhận/export telemetry nhưng không nhất thiết cần quyền đọc mọi dataset hoặc query backend. Nếu collector có processor cần field để transform, cấp quyền và network path đúng mức. Bảo vệ config/secret của exporter; không log token, endpoint có signed query hoặc credential.

### 13.3. Xác thực workload-to-workload

Ưu tiên mTLS, workload identity hoặc short-lived tokens. Kiểm tra peer identity ở receiver/gateway. Không mở OTLP receiver công khai không authentication nếu nó có thể nhận telemetry giả mạo hoặc bị lợi dụng để làm đầy backend.

### 13.4. Tách write và read credentials

Credential ghi telemetry không nên tự động có quyền đọc, query hoặc delete. Credential của dashboard không nên có quyền thay đổi collector config. Tách write-only ingestion, query read-only, admin và export roles.

### 13.5. Quản lý rotation và revocation

Service credentials cần owner, expiry/rotation plan, scope và audit. Khi workload bị thu hồi, disable identity ở issuer/backend, cập nhật deployment và kiểm tra các token/cache còn hiệu lực. Không chỉ xóa secret khỏi file cấu hình.

## 14. Tenant-aware authorization và purpose limitation

Một người có thể thuộc nhiều tenant nhưng không có quyền đọc mọi dữ liệu ở mọi tenant. Backend phải kết hợp role với tenant scope và resource attributes.

### 14.1. Ví dụ policy logic

```text
ALLOW when:
  principal.authenticated == true
  AND principal.role includes DATASET_REVIEWER
  AND principal.activeTenant == resource.tenant
  AND principal.assignment includes resource.dataset
  AND resource.classification <= principal.clearance
  AND request.purpose == EVALUATION_REVIEW
  AND assignment.expiresAt > now
```

Đây là logic minh họa. activeTenant, assignment và purpose phải được backend resolve/validate từ identity, workflow và policy registry. Không tin các giá trị do browser hoặc model gửi nếu chưa kiểm tra.

### 14.2. Purpose-bound access

Quyền đọc raw case để adjudicate một lỗi cụ thể không nên tự động cho phép dùng case đó làm training data, benchmark chia sẻ hoặc demo. Purpose là thuộc tính của request truy cập và phải được kiểm tra ở policy layer.

### 14.3. Break-glass access

Break-glass là quyền khẩn cấp, không phải role admin thường trực:

1. Người dùng nêu incident/ticket và lý do.
2. Hệ thống cấp quyền tạm thời với scope cụ thể.
3. Nếu quy trình yêu cầu, người thứ hai phê duyệt.
4. Quyền có expiry ngắn và tự động thu hồi.
5. Mọi lần đọc/export được audit.
6. Sau incident, review việc sử dụng và thu hồi quyền còn lại.

Không dùng break-glass để bỏ qua mọi tenant boundary hoặc tắt audit.

## 15. Ví dụ Spring Security: bảo vệ endpoint observability

Ví dụ dưới đây dùng Spring Security Resource Server và method security. Các role/permission là authority do hệ thống identity/policy mapping cung cấp; đây không phải cấu hình đầy đủ cho mọi ứng dụng.

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class ObservabilitySecurityConfiguration {

    @Bean
    SecurityFilterChain observabilityApi(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers("/api/observability/**")
                    .authenticated()
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Health endpoint chỉ nên public nếu response không tiết lộ chi tiết nhạy cảm và deployment policy cho phép. JWT decoder phải được cấu hình issuer/audience và authorities mapping phù hợp. Method-level authorization bên dưới vẫn cần kiểm tra tenant/resource scope.

### 15.1. Bảo vệ operation theo permission

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class EvaluationDatasetController {

    private final EvaluationDatasetService datasets;

    public EvaluationDatasetController(EvaluationDatasetService datasets) {
        this.datasets = datasets;
    }

    @GetMapping("/api/observability/datasets/{datasetId}")
    @PreAuthorize("hasAuthority('DATASET_METADATA_READ')")
    public DatasetMetadata getDataset(@PathVariable String datasetId) {
        return datasets.getMetadataForCurrentPrincipal(datasetId);
    }
}
```

Annotation kiểm tra permission tổng quát. Service vẫn phải xác minh tenant, dataset assignment, classification và purpose; không được tìm dataset chỉ bằng ID rồi trả dữ liệu. Nếu method được gọi từ một internal path không đi qua proxy security, cần bảo đảm authorization được đặt ở service boundary hoặc mọi call path được kiểm soát.

## 16. Ví dụ Java: authorization ở service layer

Ví dụ minh họa một policy service kiểm tra cả principal và dataset resource:

```java
public DatasetMetadata getMetadataForCurrentPrincipal(String datasetId) {
    PrincipalContext principal = principalContext.requireAuthenticated();
    DatasetMetadata dataset = datasetRepository
        .findMetadataById(datasetId)
        .orElseThrow(DatasetNotFoundException::new);

    accessPolicy.requireAllowed(
        principal,
        dataset,
        DatasetAction.METADATA_READ,
        AccessPurpose.OPERATIONS
    );

    return dataset;
}
```

Các class PrincipalContext, DatasetAction, AccessPurpose và accessPolicy là abstraction nội bộ. Repository query và policy cần tránh lộ metadata tenant khác; có thể lọc tenant ngay trong repository thay vì load metadata trước nếu ID có thể bị dò. Backend nên trả response nhất quán theo policy khi resource không tồn tại hoặc caller không được phép biết sự tồn tại.

### 16.1. Case-level authorization

```java
public EvaluationCase readAssignedCase(String caseRef) {
    PrincipalContext principal = principalContext.requireAuthenticated();
    EvaluationCaseMetadata metadata =
        caseRepository.findMetadataForAuthorizedScope(
            caseRef,
            principal.tenantScope()
        ).orElseThrow(CaseNotFoundException::new);

    accessPolicy.requireAssignment(principal, metadata);
    accessPolicy.requirePurpose(
        principal,
        AccessPurpose.EVALUATION_REVIEW
    );

    return restrictedContentStore.read(metadata.contentReference());
}
```

Đây là pseudocode minh họa. Restricted content store cũng phải enforce authorization, encryption và audit; không được coi việc metadata repository đã kiểm tra quyền là đủ nếu object storage có URL công khai hoặc bucket credential rộng.

## 17. Audit access và quản lý vòng đời quyền

Audit record cần trả lời ai đã làm gì, với tài nguyên nào, vào lúc nào, theo purpose nào và kết quả ra sao. Audit không nên chứa raw content mà người dùng vừa xem.

### 17.1. Audit events cần có

- Login/SSO outcome và service identity authentication.
- Role/permission grant, change, expiry và revoke.
- Dataset/case/trace/log query với resource scope.
- Raw content access và break-glass use.
- Export, download, share link create/open/revoke.
- Evaluation run create/cancel và reviewer annotation.
- Retention/deletion policy change và deletion outcome.
- Denied access và policy evaluation failure.

### 17.2. Audit event schema minh họa

```json
{
  "event": "evaluation.case.read",
  "actorRef": "principal-ref-71",
  "actorType": "human",
  "tenantRef": "tenant-ref-opaque-A",
  "resourceRef": "case-ref-opaque-92",
  "action": "DATASET_CASE_READ",
  "purpose": "EVALUATION_REVIEW",
  "policyVersion": "access-v5",
  "decision": "allow",
  "timestamp": "2026-11-27T10:15:00Z"
}
```

Schema trên là ví dụ nội bộ. Dùng opaque references đã được phân loại; không ghi email, prompt, retrieved text, secret hoặc raw query. Audit store cần write protection, access control, retention và khả năng phát hiện sửa/xóa trái phép.

### 17.3. Access review

Theo chu kỳ hoặc khi có thay đổi nhân sự:

1. Liệt kê user/service identities và role assignments.
2. Xác định owner và mục đích của từng quyền.
3. Tìm quyền không dùng, quá rộng hoặc hết hạn chưa thu hồi.
4. Xác nhận reviewer/evaluator còn assignment.
5. Thu hồi quyền thừa và kiểm tra token/session còn hiệu lực.
6. Lưu kết quả review và người phê duyệt.

### 17.4. Break-glass phải có hậu kiểm

Sau khi quyền khẩn cấp hết hạn, kiểm tra truy vấn, export, tài nguyên đã xem và mọi file được tạo. Hậu kiểm giúp phát hiện quyền được sử dụng ngoài purpose hoặc dữ liệu đã được sao chép ra nơi khác.

## 18. Retention, deletion và quyền của bản export

Quyền truy cập cần theo dữ liệu trong suốt vòng đời:

- Dataset bị archive không có nghĩa quyền đọc được mở rộng.
- Export phải có owner, classification, expiry và access policy.
- Shared link cần revoke khi người nhận đổi vai trò hoặc hết purpose.
- Backup và object versioning cần được tính trong deletion lifecycle.
- Report tổng hợp có thể vẫn tiết lộ tenant nhỏ nếu cohort quá ít.
- Audit record giữ bằng chứng truy cập nhưng không nên giữ lại raw content.

Nếu dữ liệu gốc bị xóa, kiểm tra derived datasets, caches, reports, attachments, reviewer exports và search indexes theo policy. Một bản CSV tải về không tự biến mất khi quyền ở dashboard bị thu hồi.

## 19. Kiểm thử authorization

Authorization test phải bao gồm positive và negative paths, API lẫn giao diện và mọi đường truy cập phụ.

### 19.1. Test matrix

| Test | Kịch bản | Kỳ vọng |
|---|---|---|
| **ACL01 — Unauthenticated** | Gọi query API không token. | 401 hoặc response theo gateway policy. |
| **ACL02 — Missing role** | User đăng nhập nhưng không có TRACE_READ. | Bị từ chối. |
| **ACL03 — Wrong tenant** | User A đọc dataset/trace tenant B. | Backend không trả dữ liệu B. |
| **ACL04 — Wrong classification** | Role chỉ xem Confidential nhưng resource Restricted. | Bị từ chối hoặc chỉ trả view đã giảm thiểu theo policy. |
| **ACL05 — Dashboard bypass** | Đổi tenant variable/raw query trong dashboard. | Backend vẫn enforce scope của principal. |
| **ACL06 — Direct API** | Gọi get-by-ID/export API ngoài UI. | Authorization được kiểm tra tương tự. |
| **ACL07 — Trace link** | User có metrics access mở trace detail. | Chỉ được xem nếu có TRACE_READ trong scope. |
| **ACL08 — Dataset assignment** | Reviewer đọc case không được giao. | Bị từ chối. |
| **ACL09 — Raw content** | On-call đọc raw prompt không có elevated permission. | Chỉ redacted view hoặc từ chối. |
| **ACL10 — Export** | User có read nhưng không có export permission. | Export bị từ chối. |
| **ACL11 — Shared link** | Link hết hạn hoặc đã revoke. | Không mở được, kể cả khi còn URL. |
| **ACL12 — Service identity** | Collector dùng credential dashboard để query backend. | Bị từ chối theo tách quyền. |
| **ACL13 — Token expiry** | Dùng token hết hạn hoặc sai audience. | Authentication thất bại. |
| **ACL14 — Break-glass** | Quyền khẩn cấp hết hạn. | Truy cập bị thu hồi và audit còn nguyên. |
| **ACL15 — Audit integrity** | Principal thông thường thử sửa/xóa audit. | Không có quyền. |
| **ACL16 — Bulk endpoint** | Gửi nhiều case IDs, trong đó có case ngoài scope. | Không có dữ liệu ngoài scope trong response. |
| **ACL17 — Secondary path** | Truy cập object storage/report URL trực tiếp. | Store tự kiểm tra quyền hoặc URL hết hạn/đúng scope. |
| **ACL18 — Access revocation** | Role bị revoke khi session/token cũ còn tồn tại. | Policy có hiệu lực trong thời gian thu hồi được quy định. |

### 19.2. Synthetic access markers

Dùng dữ liệu giả:

```text
TENANT_A_TRACE_PRIVATE_71A
TENANT_B_TRACE_PRIVATE_82B
DATASET_A_CASE_SECRET_31C
DATASET_B_CASE_SECRET_42D
```

Tạo trace/case riêng cho hai tenant. Thử query, drill-down, export, share link, dashboard variable và direct API bằng từng identity. Kiểm tra response body, logs, downloaded files và audit trail để xác nhận marker chỉ được trả cho principal đúng scope.

### 19.3. Test permission matrix tự động

Có thể biểu diễn test fixtures theo cặp principal/resource/action/expected decision. Khi role hoặc policy thay đổi, chạy lại toàn bộ matrix để phát hiện quyền vô tình mở rộng. Test phải kiểm tra cả deny reason category và không rò rỉ metadata của resource ngoài quyền.

## 20. Bài tập thực hành

Một nhóm vận hành Spring AI có các thành phần:

- Grafana dashboard dùng một datasource credential có quyền query mọi tenant.
- On-call engineer được cấp quyền xem metrics.
- Evaluation reviewer chỉ được giao dataset của tenant A.
- Tempo trace chứa prompt và retrieved chunks.
- Evaluation API có endpoint get-by-ID và export CSV.
- Một scheduled evaluator worker dùng chung service token với dashboard.

### Câu hỏi

1. Liệt kê các quyền đang bị cấp quá rộng hoặc thiếu tách biệt.
2. Vì sao dashboard filter theo tenant không đủ bảo vệ?
3. Thiết kế permission matrix cho on-call, evaluator, reviewer và platform admin.
4. Nên xử lý prompt/retrieved chunks trong trace thế nào?
5. Endpoint get-by-ID và export cần kiểm tra những thuộc tính nào?
6. Vì sao scheduled worker không nên dùng dashboard token?
7. Thiết kế break-glass cho on-call cần xem raw trace trong incident.
8. Đề xuất sáu audit events quan trọng.
9. Nêu tám access-control tests cần có trước release.
10. Nếu CSV đã được tải trước khi quyền bị revoke, cần xử lý gì?

### Gợi ý đáp án

**1.** Datasource credential có quyền mọi tenant, on-call chỉ cần metrics nhưng có thể query sâu, trace chứa raw content, export endpoint cần permission riêng và evaluator worker dùng chung identity với dashboard.

**2.** User có thể đổi dashboard variable hoặc gọi datasource API trực tiếp. Backend/gateway phải xác thực principal và enforce tenant scope cho query/export.

**3.** On-call đọc aggregate metrics và redacted telemetry trong scope; evaluator đọc dataset/run được giao; reviewer đọc assigned redacted cases và ghi labels; platform admin quản lý hạ tầng với raw access riêng theo break-glass.

**4.** Không lưu raw prompt/chunk trong trace vận hành. Dùng metadata và opaque case reference; content đã redacted lưu trong restricted evaluation store khi policy cho phép.

**5.** Principal identity, tenant membership, dataset assignment, classification, action permission, purpose, expiry và export scope.

**6.** Worker cần quyền đọc dataset/run và ghi result; dashboard cần query read-only. Tách identity giúp giảm quyền và xác định chính xác actor trong audit.

**7.** Yêu cầu incident/ticket, approval nếu policy yêu cầu, scope service/tenant/time range, expiry ngắn, audit từng read/export và hậu kiểm.

**8.** Login, role grant/revoke, trace query, raw content access, dataset case read, CSV export, break-glass grant/use và policy change.

**9.** Unauthenticated request, missing role, wrong tenant, dashboard bypass, direct API, case assignment, export permission và service identity separation.

**10.** Xác định nơi lưu, người nhận và bản sao; revoke link/credential nếu có; yêu cầu xử lý/xóa theo policy và quy trình tổ chức; ghi audit và đánh giá phạm vi đã chia sẻ. Revoke dashboard permission không xóa file CSV đã tải.

## 21. Ghi nhớ

Quản lý quyền truy cập observability và evaluation data bắt đầu từ authentication đáng tin cậy, sau đó authorization phải xét role, tenant, resource classification, purpose và thời hạn. RBAC tạo quyền nền; ABAC giới hạn tài nguyên và bối cảnh; deny by default và least privilege giảm phạm vi sự cố. Backend phải enforce query, get-by-ID, drill-down, export, share link và object access; dashboard filter hoặc trace ID không phải security boundary. Tách danh tính người dùng, application, collector, exporter, evaluator và dashboard datasource; tách quyền ingest khỏi query, read khỏi export và redacted content khỏi raw content. Audit access, review role định kỳ, quản lý break-glass và kiểm thử positive/negative paths trên cả API lẫn đường phụ. Nhờ vậy, nhóm vẫn điều tra được latency, cost và chất lượng Spring AI trong khi bảo vệ prompt, RAG documents, tool data và evaluation cases.

### Tài liệu tham khảo

- [Spring Security — Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html): authorization rules trong ứng dụng Spring.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): bảo vệ service methods bằng annotations và authorization managers.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): xác thực JWT access tokens.
- [OpenTelemetry — Security](https://opentelemetry.io/docs/security/): bảo mật instrumentation, transport và collector.
- [OpenTelemetry — Collector Configuration](https://opentelemetry.io/docs/collector/configuration/): receivers, processors, exporters và pipelines.
- [Grafana — Authentication and Authorization](https://grafana.com/docs/grafana/latest/administration/authentication/): xác thực và quản lý quyền; áp dụng theo phiên bản/deployment.
- [Grafana — Role-Based Access Control](https://grafana.com/docs/grafana/latest/administration/roles-and-permissions/): roles, permissions và access scopes.
- [PostgreSQL — Row Security Policies](https://www.postgresql.org/docs/current/ddl-rowsecurity.html): database-level row access policies.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): nguyên tắc kiểm tra quyền.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): kiểm soát dữ liệu và quyền truy cập logs.
