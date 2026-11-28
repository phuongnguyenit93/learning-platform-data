# Web security scan – Quét và kiểm chứng bảo mật ứng dụng web bằng bằng chứng

## Mục tiêu học tập

Sau bài học, bạn có thể:

- Giải thích **web security scan** trong **dynamic testing**, phân biệt quét thụ động, quét chủ động, authenticated scan, DAST, API security testing và penetration testing.
- Định nghĩa **mục tiêu assurance, phạm vi và sự cho phép** trước khi gửi traffic kiểm thử, đặc biệt với hệ thống có dữ liệu thật hoặc tác vụ thay đổi trạng thái.
- Lập danh mục endpoint, host, API version, vai trò, tenant, phương thức HTTP, dữ liệu đầu vào và trust boundary nhằm đo **độ bao phủ thực tế** của một lượt scan.
- Chọn và giới hạn các test cho authentication/session, authorization, input/output, TLS, cookies, security headers, CORS, CSRF, file upload, redirect, API business logic và cấu hình.
- Hiểu giới hạn của scanner tự động: **false positive, false negative, route không được khám phá, API không được gọi, hết hạn session, ẩn sau role, WAF, rate limit và thiếu thông tin business context**.
- Tổ chức workflow **chuẩn bị → baseline → crawl/coverage → kiểm thử → triage → remediation → retest → thu bằng chứng → continuous assurance**.
- Thiết kế quality gates CI/CD, quy tắc dừng, quản lý tài khoản kiểm thử, bảo vệ log/traffic, phát hiện scanner bị lỗi và kiểm soát rủi ro vận hành.
- Viết yêu cầu kiểm chứng, test case, cấu trúc report và evidence register có thể truy vết từ **risk → requirement → control → scan/test → finding → fix → retest**.
- Áp dụng ví dụ Java/Spring Boot, API OpenAPI, OWASP ZAP (minh họa) và case study đa tenant với các kết luận PASS/FAIL/INCONCLUSIVE chính xác.

## 1. Web security scan là gì?

**Web security scan** là hoạt động kiểm tra ứng dụng web hoặc API từ góc nhìn tương tác qua **HTTP/HTTPS và các giao diện runtime liên quan** nhằm phát hiện dấu hiệu lỗ hổng, cấu hình bảo mật sai hoặc hành vi không đáp ứng security requirements.

Scanner có thể:
- Gửi requests đến URLs/endpoint đã được phép.
- Phân tích responses, redirects, cookies, headers và chứng chỉ.
- Thu thập forms, links, API routes và tham số đầu vào.
- Quan sát phản ứng trước các test inputs an toàn trong môi trường được kiểm soát.
- So sánh hành vi giữa những tài khoản/roles theo test plan.
- Sinh findings với request/response evidence, mức tin cậy và hướng khắc phục.

Scan được xem là **một phương pháp kiểm chứng control đang vận hành**, không phải bản thân control. Trong module **SECURITY_SECURITY_ASSURANCE**, quét chỉ có giá trị khi kết quả được nối với mục tiêu bảo mật, threat scenario, phạm vi, phiên bản đã triển khai, phương pháp kiểm tra và bằng chứng có thể đánh giá lại.

> “Scan hoàn thành, không có critical finding” chỉ là kết quả của một lần chạy trong phạm vi đã quan sát; nó **không chứng minh** ứng dụng an toàn tuyệt đối, mọi endpoint đã được kiểm tra hoặc mọi security objective đã đạt.

### Ví dụ

`report-api` chạy Spring Boot có các endpoint:
- `GET /api/reports/{id}` trả tóm tắt report theo tenant.
- `POST /api/reports/export` tạo công việc xuất file.
- `GET /admin/audit` dành cho auditor.
- `POST /api/import` nhận tài liệu từ khách hàng.
- `GET /actuator/health` cung cấp thông tin vận hành.

Một scan không đăng nhập có thể thấy trang chủ và health endpoint, báo không có high severity finding. Tuy nhiên nó chưa thử luồng có authentication, endpoint admin, export, tenant boundaries, input file hoặc quyền tải kết quả. **Coverage thấp làm hạn chế kết luận** ngay cả khi kết quả scan “green”.

## 2. Phân biệt web scan với các hình thức kiểm thử bảo mật khác

| Kỹ thuật | Quan sát điều gì? | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- |
| **DAST/web scan** | Hành vi ứng dụng đang chạy qua giao diện truy cập | Phát hiện một số lỗi runtime/config/input handling | Phụ thuộc route, identity, dữ liệu và scanner coverage |
| **Passive scan** | Phân tích traffic/response có sẵn | Thường ít gây tác dụng phụ hơn active | Không tự tạo nhiều điều kiện bất thường |
| **Active scan** | Gửi thêm test requests nhằm phát hiện weakness | Có thể kiểm tra các hành vi không xuất hiện ở traffic bình thường | Có thể gây side effect/tải nếu không giới hạn |
| **SAST** | Source, bytecode hoặc patterns | Kiểm tra code paths không cần deploy | Có false positives và hạn chế runtime context |
| **SCA** | Dependency/package/advisory inventory | Tìm known vulnerable components | Không chứng minh endpoint vulnerable/reachable |
| **IAST** | Kết hợp runtime instrumentation với test traffic | Có thêm execution context | Cần instrumentation và test coverage |
| **Manual security test** | Các abuse cases/context cụ thể | Kiểm tra business logic, object authorization | Đòi hỏi chuyên môn và thiết kế |
| **Penetration test** | Đánh giá rủi ro, attack paths, chaining trong phạm vi cho phép | Nhận diện kịch bản phức tạp | Không thể thay đánh giá liên tục cho mọi release |
| **Configuration review** | Effective gateway, IAM, TLS, runtime policies | Hiểu trạng thái control ngoài app | Cần bằng chứng đúng môi trường |
| **Runtime monitoring** | Events và behavior trong vận hành | Phát hiện hoạt động sau deployment | “Không có alert” không chứng minh không có lỗ hổng |

Một web scan hoàn chỉnh thường phối hợp **automated DAST + authenticated journeys + API contract tests + negative authorization tests + manual review**. Không nên áp một từ “scan” cho mọi kỹ thuật mà không nêu scope và verification method.

## 3. Quy tắc đầu tiên: scope và quyền thực hiện

### 3.1. Chỉ scan tài sản được phép

Trước khi gửi traffic kiểm thử, cần có sự chấp thuận từ **system owner** hoặc thẩm quyền phù hợp. Văn bản/record nên xác định:

- Hostnames, schemes, ports, IP ranges và environment **được phép**.
- API routes/paths, redirect destinations và third-party integrations được bao gồm.
- Các loại test được phép: passive, crawl, authenticated, active, API fuzzing ở mức kiểm soát.
- Các kỹ thuật **không được phép**: gây tải, brute-force, account lockout, dữ liệu phá hủy, tạo giao dịch thật, tác động third party.
- Test accounts/roles/tenants và test data được phê duyệt.
- Maintenance window, giới hạn traffic/concurrency/rate/budget/time.
- Source IPs, user-agent/correlation headers, contact và on-call.
- Quy tắc lưu, redaction, encryption và retention của request/response evidence.
- Stop conditions, incident escalation và rollback/recovery.
- Phạm vi quét staging/preproduction vs production và điều kiện khác nhau.

**Robots.txt, sitemap, route documentation hoặc một URL công khai không phải giấy phép scan.** URL do response redirect tới cũng không tự động nằm trong scope, nhất là đối tác hoặc hệ thống nhận callback.

### 3.2. Quy tắc an toàn khi kiểm thử

- Ưu tiên môi trường staging **giống production về security controls** nhưng dùng dữ liệu giả lập.
- Với production, ưu tiên passive/limited verification và các test case đã thẩm định; yêu cầu phê duyệt riêng cho active intrusive tests.
- Không sử dụng payload làm xóa dữ liệu, thực hiện thanh toán thật, gửi email hàng loạt hoặc tăng quyền trái authorization.
- Thiết lập quota cho requests/sessions, concurrency, timeout và kích thước payload.
- Giới hạn crawling và không tự động theo redirects ra ngoài approved host/domain.
- Dùng identity, tenant và resource test riêng; không dùng tài khoản admin như mặc định cho mọi scan.
- Gắn scan run ID/correlation ID để Operations phân biệt test với abuse thực.
- Ngừng ngay nếu nhận thấy lỗi 5xx tăng, latency bất thường, khóa account, queue backlog, data mutation không mong đợi hoặc alert vận hành.
- Có runbook containment và communication channel khi scan gây gián đoạn.

Mục tiêu là **kiểm chứng bảo mật mà không tạo ra sự cố do kiểm thử**.

## 4. Threat model và các ranh giới cần quét

### 4.1. Kiến trúc tham chiếu

~~~mermaid
flowchart LR
    B["Browser / mobile app"] --> WAF["CDN / WAF / Gateway"]
    WAF --> WEB["Web frontend"]
    WAF --> API["Spring Boot report-api"]
    API --> IDP["OIDC identity provider"]
    API --> DB["PostgreSQL tenant data"]
    API --> Q["Message queue"]
    Q --> JOB["Export worker"]
    JOB --> S["Object storage"]
    API --> LOG["Audit / SIEM"]
    ADMIN["Internal admin"] --> API
    VENDOR["Partner webhook"] --> API
    SCAN["Authorized web/API scanner"] -. "Selected scope" .-> WAF
~~~

Trong sơ đồ này:
- Browser, API và identity provider có các trust boundaries khác nhau.
- Gateway có thể che hoặc sửa response headers so với backend.
- API có các routes dành cho nhiều vai trò.
- Worker xử lý asynchronous side effects mà scanner HTTP không nhìn thấy trực tiếp.
- Storage download URLs có authorization và expiry riêng.
- Webhook có signature/replay policy riêng.
- Admin interface có thể chỉ accessible từ private network.
- Audit logging là cả evidence và một tài sản cần bảo vệ.

### 4.2. Scan không chỉ phát hiện lỗi của một endpoint

Một request `POST /api/reports/export` có thể được gateway chấp nhận nhưng sau đó job được queue và worker truy xuất dữ liệu. Để kiểm chứng authorization đầy đủ, phải quan sát:
1. Request đã được authentication?
2. Principal có `export` permission trên **đúng report/tenant**?
3. Job có được tạo khi access denied không?
4. Worker có kiểm tra scope/expiry/quyền theo policy?
5. File export được lưu/download với quyền phù hợp?
6. Audit event không chứa secret/PII thừa?
7. Có đường internal/batch khác bypass HTTP gateway không?

DAST có thể khởi tạo và quan sát một phần workflow; các điểm còn lại cần **integration testing, runtime inspection và manual business-logic assessment**. Không tuyên bố DAST PASS bao phủ các bước chưa đo.

## 5. Những nhóm lỗ hổng web cần cân nhắc

| Nhóm | Security objective | Hướng kiểm chứng |
| --- | --- | --- |
| **Authentication/session** | Chỉ identity hợp lệ truy cập | Token/cookie validation, expiry, logout, session rotation |
| **Authorization/IDOR/BOLA** | Actor chỉ được thao tác resource phù hợp | Cross-role, cross-tenant, object and field-level negative tests |
| **Input validation** | Input không phá business invariants | Type/range/length/schema/error behavior |
| **Injection** | Untrusted data không đổi ý nghĩa lệnh/truy vấn | Safe controlled tests, code review, parameterized queries |
| **Output encoding/XSS** | Browser không thực thi dữ liệu không tin cậy | Contextual encoding, CSP, DOM testing |
| **CSRF** | State changes chỉ xảy ra theo hành động được phép | Cross-site request conditions, CSRF token/SameSite |
| **CORS** | Origin trust không mở rộng tùy tiện | Preflight/credentialed origin policy tests |
| **Cookies/headers** | Bảo vệ session, transport và browser boundary | Secure/HttpOnly/SameSite, HSTS, frame policy |
| **TLS/certificate** | Kênh truyền có peer validation và phiên bản phù hợp | Effective TLS policy/handshake checks |
| **File upload** | Input file không ảnh hưởng ngoài scope | Type/size/processing/storage policy |
| **Open redirect/SSRF** | Untrusted URLs không mở trust boundary | Allowlist và controlled destination tests |
| **API misuse/abuse** | Quota/authorization/rate limits đúng | Stateful/rate tests trong budget |
| **Business logic** | Không lách workflow approval/balance/ownership | Manual abuse cases and integration tests |
| **Sensitive data exposure** | Phản hồi, log, cache không lộ data | Response contract/field tests, redaction |
| **Security misconfiguration** | Không phơi management/debug endpoints | Route enumeration + effective config |
| **Dependency risk** | Không dùng known vulnerable component | SCA/SBOM kết hợp runtime verification |
| **Availability** | Test traffic không làm suy giảm dịch vụ | Rate limits + observability/stop conditions |

Đây là danh sách **kiểm tra theo risk**, không phải cam kết một scanner tự động tìm được tất cả các vấn đề trên.

## 6. Xây dựng attack-surface inventory trước khi scan

### 6.1. Inventory inputs

- **Hosts:** DNS names, ports, TLS endpoints, redirects, virtual hosts.
- **Applications:** web frontends, REST/GraphQL APIs, websocket endpoints, management routes.
- **Methods:** GET/POST/PUT/PATCH/DELETE, preflight OPTIONS khi liên quan.
- **Paths:** API versions, deprecated/legacy routes, internal/private endpoints trong approved scope.
- **Parameters:** path/query/header/cookie/body/form/multipart.
- **Content types:** JSON, form URL-encoded, XML, protobuf, file, images và custom formats.
- **Identity contexts:** anonymous, customer, support, admin, machine identity.
- **Authorization contexts:** tenant A/B, owner/non-owner, case approved/closed, row/field access.
- **Data classes:** public, internal, customer confidential, regulated theo policy.
- **Async behaviors:** job creation, notifications, object writes, webhook callbacks.
- **Dependencies:** IdP, external API, data store, telemetry, caches và WAF.
- **Deployments:** region, environment, release digest, gateway route config.
- **Risk metadata:** Internet exposure, criticality, threat paths, known incidents/findings.

### 6.2. Nguồn discovery phải đối chiếu

| Nguồn | Có thể cung cấp | Rủi ro nếu tin một mình |
| --- | --- | --- |
| OpenAPI/Swagger contract | Đường API, methods, schemas | Docs thiếu legacy routes/authorization |
| Gateway routing inventory | Deployed ingress | Có internal/direct routes bypass |
| Source/controller mapping | Handlers/annotations | Không chứng minh đã deploy |
| Browser crawl | Links/forms/SPA navigation | Chỉ thấy route của role đang đăng nhập |
| Sitemaps/robots | Route hints | Không phải nguồn ownership/permission |
| Access logs/APM | Routes thực sự có traffic | Routes ít dùng hoặc không log bị bỏ |
| Kubernetes/service mesh | Running workloads/routes | Không thay API application semantics |
| Product workflow | User journeys và protected actions | Không tự bao phủ lỗi kỹ thuật |
| Threat model/previous findings | Sensitive assets/entry points | Có thể lỗi thời |

Một scan có thể report `100% crawled URLs` mà vẫn bỏ sót hơn nửa protected API. Chỉ số “URLs visited” không tương đương “attack surface covered”.

### 6.3. Ma trận coverage

| Route/flow | Anonymous | Customer A | Customer B | Support | Admin |
| --- | --- | --- | --- | --- | --- |
| `GET /reports/{id}` | Deny | Own allow | Other deny | Scoped policy | Scoped policy |
| `POST /reports/export` | Deny | Own allow | Other deny | Case approval | Policy |
| `GET /admin/audit` | Deny | Deny | Deny | Deny | Allow |
| `POST /import` | Deny | Approved input | Tenant isolation | Limited | Controlled |
| `GET /actuator/health` | Minimal public status | Minimal | Minimal | Minimal | Minimal |

**Bảng này là acceptance matrix mẫu**, không phải kết quả một scanner đã chạy. Để claim PASS, phải có test execution evidence trên đúng deployment và identity.

## 7. Passive scan và active scan

### 7.1. Passive scanning

Passive scanner phân tích traffic đã đi qua proxy hoặc response được thu thập mà **không tự tạo payload chủ động kiểm tra lỗi**. Nó thường phù hợp:
- Headers/cookie attributes.
- Redirect chain và caching behavior.
- Information disclosure trong responses.
- Một số thông tin về server/software stack.
- Một số dấu hiệu form/session/CSP.

Tuy ít xâm nhập hơn, passive scan **không hoàn toàn vô rủi ro**: việc crawl/đăng nhập/đi qua journeys để tạo traffic có thể tạo giao dịch, dữ liệu thật hoặc session side effects. Kiểm soát test accounts và scope vẫn cần.

### 7.2. Active scanning

Active scan chủ động gửi inputs/requests kiểm tra điểm yếu, có thể tạo:
- Nhiều HTTP calls và tải cho service.
- Lỗi 4xx/5xx hoặc application error logs.
- Side effects đối với endpoints không idempotent.
- Account lockout, tạo jobs, spam notifications hoặc thay dữ liệu.
- WAF/rate-limit alerts và ảnh hưởng dịch vụ.

Vì vậy phải phân loại endpoints theo **safe-to-scan**, **requires-data-reset**, **manual-only** và **excluded** trước khi chạy. Một scanner không hiểu business semantics có thể gọi `DELETE /resources/{id}` hoặc `POST /payments` nếu được cấp credential và API spec.

### 7.3. Risk-based scan profiles

| Profile | Mục tiêu | Đặc điểm |
| --- | --- | --- |
| **Passive baseline** | Phát hiện lỗi headers/cookies/config cơ bản | Không kích hoạt active probes; vẫn kiểm soát crawl |
| **Authenticated discovery** | Đạt coverage của protected flows | Các users/roles dữ liệu giả; session health checks |
| **Controlled active staging** | Kiểm thử kỹ thuật sâu có traffic budget | Snapshot/reset dữ liệu, positive/negative cases |
| **API contract + authZ** | Kiểm thử endpoint/verb/role/resource | Request templates, trusted fixtures, deny tests |
| **Limited production verification** | Kiểm một số controls đang chạy | Owner-approved allowlist, rate caps, stop conditions |
| **Manual high-risk review** | Business logic/complex authorization | Test script đã xét duyệt, evidence chi tiết |

**Không tự suy rằng active scan production là an toàn** chỉ vì dùng công cụ phổ biến hoặc chọn chế độ “low”.

## 8. Authenticated scan và quản lý session

### 8.1. Vì sao authentication coverage khó?

Ứng dụng web hiện đại có thể dùng:
- OIDC/OAuth2 access tokens và refresh flows.
- Browser session cookie/SameSite/CSRF.
- MFA/step-up verification.
- Short-lived tokens hoặc device binding.
- API keys/service principals.
- Dynamic CSRF tokens và anti-automation controls.
- Separate tenants, roles và privileged workflows.

Nếu scanner bị logout nhưng không nhận biết, phần lớn requests chuyển thành `401/302 login`. Một report có hàng nghìn requests có thể vẫn **chỉ kiểm trang login**.

### 8.2. Kiểm tra authenticated context

Một authenticated scan plan cần:
1. Tài khoản test được cấp trong đúng environment và hạn chế quyền.
2. Cách lấy/refresh token/session do owner cho phép; không hardcode secret vào config công khai.
3. Login/logout detection hoặc session validity check.
4. Những route chứng minh user đã authenticated trong cùng tenant.
5. Không dùng một tài khoản admin để thay mọi role.
6. Đúng identity và user provisioning, không giả mạo header client làm quyền.
7. Fixture mapping: report của tenant A/B, owned/non-owned, case approved/not-approved.
8. Revocation/expiry handling; không giữ “authenticated=true” khi token đã hết hạn.
9. Secret/token redaction trong scan report và proxy history.
10. Cleanup test data và session khi kết thúc.

### 8.3. Session health sentinel

Ví dụ:
- Trước scan, gọi endpoint đã được phép `GET /api/me`.
- Xác nhận response có principal ID/tenant phù hợp với test account và không chứa dữ liệu nhạy cảm vượt scope.
- Kiểm tra lại sau một số bước hoặc khi thấy nhiều `401/302`.
- Nếu identity sai, session expired hoặc gateway redirect sang IdP, **tạm dừng/đánh giá lại coverage**.
- Không tự chuyển sang anonymous scan rồi gọi protected route PASS.

Session sentinel chỉ xác minh trạng thái identity một phần, không thay negative authorization tests.

### 8.4. Scanning theo role và tenant

| Persona | Test resource | Expected behavior |
| --- | --- | --- |
| Anonymous | Customer report | Deny |
| Customer A | Own report A | Allow theo scope |
| Customer A | Report B | Deny, không leak content |
| Customer B | Report A | Deny |
| Support chưa có case | Report A | Deny |
| Support được duyệt case A | Report A approved fields | Conditional allow |
| Admin trong maintenance context | Audit endpoint | Allow theo policy |
| Service identity | Admin HTTP route | Deny nếu không có quyền |

Nếu DAST chỉ chạy với Customer A và không có fixture Report B, nó không thể xác minh cross-tenant boundary. Cần thiết kế test data trước.

## 9. Scan API: REST, OpenAPI và ứng dụng SPA

### 9.1. API contract không đủ thay discovery

OpenAPI có thể mô tả paths/methods/schemas và hỗ trợ scanner sinh request. Nhưng:
- Tài liệu có thể không bao phủ endpoints đang deploy.
- Security schemes trong spec có thể lệch runtime.
- OpenAPI thường không mô tả object-level ownership, role/case/tenant rules chi tiết.
- State-changing endpoints cần fixture/preconditions/cleanup riêng.
- Async jobs không được quan sát đầy đủ chỉ bằng initial HTTP response.
- GraphQL/WebSocket có attack surface khác REST và cần plugin/test tương ứng.

Vì thế cần **so sánh OpenAPI với deployed gateway routes/controllers/log inventory**, xem mỗi method có thực sự được thử với đúng authorization context.

### 9.2. API scan có thể bỏ qua behavior

Các trường hợp cần kiểm tra thủ công hoặc integration test:
- `GET /reports/{id}`: BOLA/IDOR khi đổi resource ID giữa hai tenants.
- `PATCH /profiles/{id}`: mass assignment/field-level write.
- `POST /reports/export`: authorization tại lúc tạo và lúc worker thực thi.
- `POST /webhooks/payment`: signature, replay, time window.
- `POST /import`: file content/classification, async behavior.
- `POST /login/reset`: account enumeration, rate-limits, abuse logic.
- `GET /files/{id}`: expiry, signed URLs và download permissions.

Có thể đánh giá các trường hợp này bằng request/response có kiểm soát; không để scanner tự tạo payment/export/file jobs thật.

### 9.3. SPA và JavaScript-rendered routes

Một crawler HTTP truyền thống có thể chỉ thấy `index.html` và vài static assets. Với SPA:
- Dùng trình duyệt test hoặc browser-based spider trong môi trường được phép.
- Thu thập routes từ client router và network calls.
- Chạy user journeys trong từng role.
- Ghi phát hiện về API endpoints thật, không chỉ DOM routes.
- Đảm bảo logout/session expiry không làm scan vô hiệu.
- Không mở rộng scan sang external analytics/login domains ngoài scope.

Nếu browser-based spider không thể chạy do CSP, MFA hoặc CAPTCHA, ghi limitation; không tự suy scan đã hoàn tất.

## 10. Authentication, authorization và business logic

### 10.1. Authentication tests

Phải kiểm tra theo requirement:
- Missing/expired/malformed token bị từ chối.
- Issuer, audience, signature và token type được xác minh.
- Session rotation/expiry/logout phù hợp.
- Password recovery/MFA/step-up không bypass.
- Login errors không làm lộ secret hoặc account status trái policy.
- Session cookie gắn đúng transport/browser attributes.

### 10.2. Authorization tests

Một scanner có thể phát hiện dấu hiệu IDOR, nhưng **không biết** việc customer A được phép xem object B hay không nếu không có business fixture. Cần test cases:
- User A đọc/ghi object A vs object B.
- User A gửi tenant header của B: không tăng quyền.
- Support không có case vs có case đã duyệt.
- Admin privilege từ đúng identity; không tin `X-Role: admin` do client gửi.
- Field-level redaction theo data classification.
- Deactivated/expired user, revoked role, delegated access expiry.
- Export job sau revocation hoặc resource ownership đổi.
- Cache trả nội dung của tenant khác.
- Concurrent requests/race conditions tại boundary nhạy cảm.

### 10.3. Không đồng nhất status code với bảo mật

- `403` hoặc `404` có thể là kết quả phù hợp theo policy để không tiết lộ record tồn tại.
- Nhưng response vẫn có thể chứa sensitive headers, timing, resource names hoặc side effects.
- `200` không mặc nhiên là lỗ hổng nếu actor đã được phép và scope đúng.
- `401` với API route protected chỉ chứng minh authN gate tại đó, không chứng minh authZ.
- `500` có thể là bug/error handling, không tự chứng minh exploitability.

Acceptance criteria cần bao gồm **response body/fields, database/job side effects, logs và authorization source**, không chỉ HTTP status.

## 11. Input/output, browser security và transport

### 11.1. Input và injection

Lập tests theo:
- Data type, length, format, range, nesting, Unicode/normalization.
- SQL/NoSQL/query/template handling.
- JSON/XML parsers và deserialization.
- File upload type/size/content, storage path và processing.
- URL/webhook destination và outbound HTTP allowlist.
- Output encoding theo HTML/JavaScript/URL/CSS context.
- Error responses không phơi stack trace, SQL query, internal hostnames hoặc secret.

Các probes chỉ được dùng với **tài nguyên thuộc scope và payload không gây tác dụng phụ**. Một scanner không chứng minh application an toàn trước mọi injection variants. Phải kết hợp review code và tests dựa trên threat model.

### 11.2. Cookies và response headers

| Control | Kiểm tra | Lưu ý |
| --- | --- | --- |
| `Secure` cookie | Cookie session chỉ qua HTTPS theo policy | Không dùng trên HTTP thực nếu yêu cầu confidentiality |
| `HttpOnly` | Hạn chế JavaScript access với session cookies | Không ngăn toàn bộ XSS/CSRF |
| `SameSite` | Hạn chế cross-site cookie behavior | Định nghĩa phù hợp login/embedded use case |
| HSTS | Policy transport cho host thuộc scope | Kiểm tra max-age/subdomain impacts khi bật |
| CSP | Giới hạn executable/resource origins theo thiết kế | CSP không thay output encoding |
| Frame policy | Giới hạn embedding/clickjacking | Cần policy tương thích ứng dụng |
| Cache-Control | Không lưu sensitive responses trái policy | Kiểm tra gateway/CDN/browser contexts |
| CORS | Origins, methods, headers, credentials theo allowlist | CORS không phải server-side authorization |
| Referrer-Policy | Giảm tiết lộ URL/metadata | Không thay data minimization |

Không áp dụng một header baseline giống nhau cho mọi content type/endpoint nếu requirement khác nhau; dùng standard version và scope đã phê duyệt.

### 11.3. CSRF

CSRF liên quan đến các hành động state-changing trong bối cảnh browser tự gửi credentials như session cookies. Kiểm tra:
- Method nào làm đổi trạng thái?
- Có token/Origin/Referer/SameSite hoặc biện pháp phù hợp?
- API dùng bearer token trong Authorization header do JavaScript cung cấp có threat model khác cookie auth.
- Có endpoint GET tạo side effect trái expectation không?
- Có cross-origin iframe/form hoặc upload path?
- Token mất/sai có bị từ chối mà không tạo side effect?

Scanner có thể thấy token xuất hiện nhưng không kiểm tra được enforcement nếu không có **negative test** có kiểm soát.

### 11.4. TLS và gateway

HTTP scan chỉ cho thấy route/host trong scope. TLS verification cần kiểm:
- Certificate chain/hostname và effective protocol/cipher theo baseline.
- TLS ở các hop client→gateway, gateway→service, service→dependency theo threat model.
- Redirect HTTP→HTTPS nếu policy yêu cầu.
- Không bỏ certificate validation trong HTTP client hoặc mTLS.
- Certificate expiry/revocation và automation monitoring.
- Không kết luận “mTLS toàn hệ thống PASS” chỉ vì public endpoint dùng HTTPS.

## 12. Safe scan design cho endpoints thay đổi trạng thái

### 12.1. Endpoint risk classification

| Class | Ví dụ | Cách xử lý |
| --- | --- | --- |
| **Read-only low-impact** | `GET /health` đã phê duyệt | Có thể passive/limited crawl |
| **Read with sensitive data** | `GET /reports/{id}` | Synthetic fixtures, role/tenant controls, redaction |
| **State-changing reversible** | `POST /test/items` | Chỉ sandbox/staging, cleanup/reset |
| **State-changing high-impact** | `POST /payments`, `DELETE /accounts` | Exclude active auto-scan, manual-approved script |
| **Async side effects** | `POST /export`, `POST /email/send` | Verify queues/storage/notifications và data reset |
| **Third-party integration** | Partner webhook/callback | Mock/sandbox third party, không scan live partner |
| **Resource-intensive** | Bulk import/report generation | Request-size/rate bounds, stop conditions |
| **Privileged management** | Admin/config endpoint | Special approval và dedicated accounts |

### 12.2. Stop conditions

Dừng scan khi:
- Synthetic target có dấu hiệu dữ liệu thật ngoài fixture.
- Latency, 5xx, queue depth hoặc CPU/memory tăng vượt ngưỡng đã phê duyệt.
- Account test bị khóa hàng loạt, email/notification gửi ngoài sandbox.
- WAF/IdP/third party thông báo tấn công hoặc tạo incident.
- Scanner redirect khỏi approved scope.
- Session/identity bị sai, mất hoặc quyền không đúng.
- Data cleanup/recovery không thành công.
- Không xác định được tác dụng phụ của một test.
- Bất kỳ owner/on-call nào yêu cầu stop theo runbook.

Chạy với **tài khoản, dữ liệu và môi trường được cho phép**; không có kết quả scan nào đáng giá hơn integrity và availability của hệ thống thật.

## 13. Quy trình thực hiện web security scan

### Bước 1 – Định nghĩa assurance claim

Trước khi chạy tool, xác định claim:
- “Trong phạm vi các API routes/roles của release R, các negative authorization scenarios đã được kiểm chứng”.
- “Trong phạm vi gateway/hosts H, các response security headers đáp ứng baseline B”.
- “Các authenticated user journeys trong staging có scan evidence với coverage, limitations và findings”.
- “Finding F đã được sửa trên artifact digest D và retest thành công”.

Các claim này **khác nhau**. Chạy passive baseline không đủ chứng minh kiểm soát authorization, và một penetration test năm trước không tự chứng minh phiên bản production hiện tại.

### Bước 2 – Kiểm kê và phê duyệt scope

Ghi host/path/method, environment/region, identities/roles, tenant fixtures, allowed traffic budget, excluded actions, start/end time và escalation. Không có approval thì không chạy.

### Bước 3 – Chuẩn bị môi trường và dữ liệu

- Staging gần production về gateway, TLS, feature flags, authN/authZ, WAF và rate limiting.
- Synthetic data có owner, tenant A/B và resources cho phép/không cho phép.
- Reset/snapshot strategy cho state-changing workflows.
- Test accounts có permissions đủ để đạt protected routes nhưng không có quyền ngoài mục tiêu.
- Observability: HTTP logs, API request IDs, DB/job side effects, SIEM source-health.
- Trusted scanner configuration, plugin versions và rule set review.
- Scan traffic giới hạn và stop conditions được thống nhất.

### Bước 4 – Baseline và discovery

- Thu thập request/response của các approved user journeys.
- Dùng passive rules hoặc crawler trong scope.
- Ghi discovered routes, coverage gaps và các paths ngoài scope.
- Xác nhận authenticated session còn hợp lệ sau mỗi phase.
- Đối chiếu discovered endpoints với OpenAPI, gateway, controller và product workflows.
- Nếu thiếu critical route, bổ sung test riêng thay vì báo complete.

### Bước 5 – Active/negative tests theo risk

- Chạy trên **staging/sandbox đã phê duyệt**, với data reset và traffic budget.
- Ưu tiên tests đáp ứng security requirements có acceptance rõ.
- Kiểm tra negative paths của authN/authZ/session/tenant.
- Giới hạn probes tránh DoS, brute-force, destructive actions và third-party side effects.
- Theo dõi backend/queue/storage, không chỉ HTTP response.
- Ghi scan configuration, identity, roles, environment, build/deployment ID.

### Bước 6 – Triage kết quả

- Phân biệt finding confirmed, suspected, false positive, not affected, duplicate, risk accepted/exception và inconclusive.
- Xác minh technical evidence bằng test có kiểm soát.
- Link finding với CWE/security requirement/risk/asset/route.
- Phân loại severity theo **impact, exploitability, exposure, criticality**, không chỉ rating tool.
- Đánh giá gaps do test không chạy, rule thiếu hoặc session lỗi.

### Bước 7 – Khắc phục và retest

- Developer sửa code/config/dependency.
- Xác nhận patch vào đúng source commit/build/deployment.
- Chạy regression và negative test.
- Scan lại **đúng route/role/scenario** từng lỗi.
- Kiểm tra reverse proxy/gateway/production effective config.
- Đóng finding chỉ khi evidence đáp ứng acceptance criteria.

### Bước 8 – Báo cáo và continuous assurance

- Lưu evidence an toàn; hạn chế dữ liệu thật trong request/response.
- Report coverage, findings, severity, source health, false positives, limitations và exceptions.
- Thiết lập triggers quét lại sau thay API/identity/tenant/data/third-party/routing.
- Giữ baseline theo release để phát hiện regression, nhưng không so số lượng findings khi scope đổi mà không công bố sự khác biệt.

~~~mermaid
flowchart TD
    S["Authorized scope + claim"] --> B["Inventory + threat model"]
    B --> PREP["Synthetic data, roles, traffic limits"]
    PREP --> PASS["Passive baseline and route discovery"]
    PASS --> GAP{"Critical routes and personas covered?"}
    GAP -- "Không" --> MANUAL["Additional authenticated journeys / manual cases"]
    MANUAL --> GAP
    GAP -- "Có" --> ACTIVE["Controlled active / negative tests"]
    ACTIVE --> TRIAGE["Findings triage + evidence"]
    TRIAGE --> FIX{"Failure or gap?"}
    FIX -- "Có" --> REM["Owner, remediation, exception where appropriate"]
    REM --> RETEST["Same scenario / deployed artifact retest"]
    RETEST --> TRIAGE
    FIX -- "Không" --> CLAIM["Scoped assurance conclusion"]
    CLAIM --> MON["Change triggers, drift and next scan"]
    MON --> S
~~~

## 14. Minh họa cách sử dụng OWASP ZAP an toàn

**OWASP ZAP** là một công cụ DAST/proxy để quan sát và kiểm thử ứng dụng web. Ví dụ chỉ dành cho **hệ thống mà bạn được phép kiểm thử**; tên host `staging.example.test` là địa chỉ giả dành cho tài liệu, phải thay bằng host test thuộc phạm vi được phê duyệt.

Cú pháp lệnh phụ thuộc phiên bản công cụ/image. Khi triển khai thực tế, cần cố định tool version, kiểm tra help/docs đi kèm version đã duyệt, quản lý workspace/permissions và xác minh output.

### 14.1. Baseline passive scan

~~~bash
# Ví dụ dành cho một staging web app đã được cho phép quét.
# Tên staging.example.test chỉ là placeholder; cần thay host hợp lệ.
docker run --rm \
  -v "$PWD:/zap/wrk/:rw" \
  -t ghcr.io/zaproxy/zaproxy:stable \
  zap-baseline.py \
  -t https://staging.example.test \
  -r zap-baseline.html \
  -J zap-baseline.json
~~~

Baseline job thường tập trung **spider/crawl và passive rules**; nhưng các GET requests vẫn có thể tạo side effects với ứng dụng thiết kế không an toàn. Cần kiểm tra route classification, rate/crawl limits và redirects trước khi chạy.

- Không chạy lệnh với website bên thứ ba không cho phép.
- Không mặc định báo scan complete nếu tool không crawl được routes.
- Không hardcode authenticated cookie/token vào command hoặc report.
- Không cho phép scanner tự theo redirects sang domain ngoài scope.
- Không upload reports có raw customer data lên public CI artifacts.

### 14.2. API scan theo OpenAPI

~~~bash
# Chỉ chạy nếu API spec, endpoints và methods trong scope đã được duyệt.
# API scanning có thể tạo requests gây thay đổi trạng thái.
docker run --rm \
  -v "$PWD:/zap/wrk/:rw" \
  -t ghcr.io/zaproxy/zaproxy:stable \
  zap-api-scan.py \
  -t https://staging.example.test/openapi.json \
  -f openapi \
  -r zap-api.html \
  -J zap-api.json
~~~

**Cảnh báo:** API scan có thể chạy active checks và gọi methods có tác dụng phụ. Trước khi dùng cần:
- Đảm bảo spec không chứa production endpoints hoặc third-party URLs ngoài scope.
- Tách/endpoints disable các thao tác high-impact như payment, user deletion, email send và export thật.
- Dùng synthetic accounts/data với cleanup.
- Áp request budget, stop conditions, observability.
- Xem rule selection và request generation của ZAP version hiện hành.
- Không tự động chạy API scan toàn bộ production vì có OpenAPI URL.

### 14.3. Thu thập kết quả chưa đủ để kết luận PASS

Report nên lưu:
- Tool/version, script/profile/rule set/config checksum.
- Scan ID, timestamps, run status/exit code.
- Authorized scope và discovered route set.
- Authenticated persona/session-health evidence.
- Number of tested vs excluded endpoints.
- Severity/confidence và raw/sanitized request/response references.
- Operational status, rate/timeout/failure logs.
- Reviewer, triage decisions và retest IDs.

Một HTML report trống findings có thể là **false negative vì scanner chỉ được redirect về login**, không đủ assurance.

### 14.4. Không mặc định suppress warnings

Baseline tools có thể trả cảnh báo mức thấp về headers/cookies. Chỉ ignore/suppress khi:
- Có rationale và approved exception/scope.
- Control thực tế được kiểm chứng hoặc finding được phân loại false positive có bằng chứng.
- Entry có ID, owner, expiry/review trigger.
- Raw result vẫn được lưu cho audit.
- Không dùng wildcard che routes mới hoặc requirements quan trọng.

Nếu tool output không thể được parse hoặc scanner lỗi, quality gate phải là **INCONCLUSIVE/NOT_RUN hoặc BLOCK theo policy**, không thành PASS.

## 15. Ví dụ kiểm tra thủ công giới hạn và quan sát HTTP

Dưới đây là các lệnh **read-only** minh họa dành cho endpoint test do bạn sở hữu.

### 15.1. Headers, redirects và cookies

~~~bash
# Quan sát status/headers, không chủ động thử exploit.
curl --silent --show-error \
  --dump-header - \
  --output /dev/null \
  https://staging.example.test/health
~~~

Không tự diễn giải `200` là an toàn. Xem CSP/HSTS/Cookie/Cache-Control/redirect policy theo baseline và route. Nếu endpoint gửi header `Set-Cookie` chứa secret trong log công khai, cần redaction.

### 15.2. Authentication negative test

~~~bash
# Khi /api/me được thiết kế là protected:
# Không gửi credentials; expected là deny theo contract.
curl --silent --show-error \
  --output /dev/null \
  --write-out '%{http_code}\n' \
  https://staging.example.test/api/me
~~~

HTTP status phù hợp (ví dụ 401 theo contract) chỉ là **một điều kiện**; cần kiểm tra không có dữ liệu/side effect. Không thực hiện brute-force hoặc thử tài khoản người khác.

### 15.3. API contract và danh sách route

Ví dụ đối chiếu:
- `GET /api/me` (đòi authentication).
- `GET /api/reports/{id}` (đòi resource authorization).
- `POST /api/reports/export` (có side effect; dùng fixture và kiểm tra queue).
- `GET /admin/audit` (role-bound; không quét bừa).
- `POST /api/import` (file input, cần sandbox).
- `GET /actuator/health` (public minimal response theo policy).

Tập lệnh quan sát đơn giản không tự xác minh token expiry, CSRF, CORS hay object-level authorization. Thêm negative/integration tests có fixtures.

## 16. Risk-based prioritization và triage findings

### 16.1. Từ scanner alert đến risk scenario

Một finding hữu ích cần:
- **Affected asset:** service, URL/endpoint/role/region, release ID.
- **Weakness:** CWE hoặc mô tả kỹ thuật cụ thể.
- **Observed behavior:** request/response hoặc config chứng minh.
- **Expected behavior:** security requirement/acceptance.
- **Exploit prerequisites:** authentication, privilege, input, deployment condition.
- **Business impact:** data, tenancy, operations và user impact.
- **Likelihood/exposure:** Internet/internal, known exploitation nếu có bằng chứng.
- **Confidence/limitations:** scanner signal, manual reproduction, coverage gaps.
- **Owner/remediation:** team, deadline, fix plan, verification method.

### 16.2. Severity tool không tự là risk

| Tín hiệu | Ý nghĩa | Hạn chế |
| --- | --- | --- |
| Scanner severity | Mức cảnh báo theo rule/tool | Không biết toàn bộ business context |
| Scanner confidence | Tool tin đến đâu vào indicator | Không chứng minh actual exploitability |
| CVSS/CWE | Thông tin weakness/severity khi áp dụng | Không tự tính risk cho asset |
| Exposure | Có thể truy cập từ Internet/internal | Không mô tả hết attacker permissions |
| Data class | Tác động khi thông tin bị lộ/sửa | Cần biết actual fields/tenant |
| Authenticated reachability | Actor nào có thể tới route | Không tự chứng minh không có bypass |
| Defense controls | WAF, authZ, validation, isolation | Chỉ tính nếu verified effective |
| Existing exploit intel | Known exploited/active campaigns | Phải xét date/source và tình huống |
| Business criticality | Impact với doanh nghiệp | Không tự nói likelihood |

Không tự hạ tất cả findings “High” xuống “Low” vì đã có WAF; cần coverage/negative tests với cả direct/internal/API paths.

### 16.3. Triage states

| State | Khi dùng | Evidence cần có |
| --- | --- | --- |
| **NEW** | Scanner mới báo | Tool output/scope |
| **UNDER_REVIEW** | Chưa xác minh | Reviewer/task |
| **CONFIRMED** | Behavior sai đã tái hiện trong scope | Request/response + acceptance |
| **FALSE_POSITIVE** | Rule báo sai thực tế | Lý do và evidence |
| **NOT_APPLICABLE** | Điều kiện lỗi không hiện diện trong scope | Config/reachability/effective state proof |
| **DUPLICATE** | Trùng root cause/scope đã ghi | Link tới finding gốc |
| **MITIGATED** | Risk giảm bằng control còn giám sát | Verified control evidence |
| **EXCEPTION_APPROVED** | Risk owner cho phép sai lệch có hạn | Approval, expiry, scope; vẫn còn technical gap |
| **FIXED_AWAITING_RETEST** | Code/config đã thay nhưng chưa verify | Build/deploy references |
| **VERIFIED_CLOSED** | Retest trên actual-state PASS | Reproduced test + deployment evidence |
| **INCONCLUSIVE** | Thiếu scope/test/source để kết luận | Gaps và next steps |

Các trạng thái không nên được gộp thành “Resolved” nếu technical finding vẫn còn.

## 17. False positives, false negatives và coverage gaps

### 17.1. False positive

Ví dụ scanner cảnh báo thiếu header trên endpoint có response mode khác, nhưng threat model và policy xác định header đó không áp dụng. Cần review:
- Rule nào chạy, version và risk context?
- Route/response type nào?
- Header có được đặt tại gateway không?
- Có evidence cho exclusion/exception?
- Có kiểm tra response ở đúng môi trường?

Không đổi `FALSE_POSITIVE` chỉ vì finding gây khó chịu hoặc khó fix.

### 17.2. False negative

Scanner báo không tìm được lỗi, nhưng:
- Crawler chỉ thấy `/login`, protected routes không chạy.
- Session expired sau 5 phút.
- Scanner không hỗ trợ JavaScript SPA.
- OpenAPI spec thiếu route cũ.
- App nằm sau WAF và block scanner traffic trước khi chạm backend.
- User role không có resource fixtures.
- Bypass qua queue/internal endpoint không nằm trong scope.
- Scanner rule không phát hiện business authorization defect.
- Dữ liệu trả về có vulnerability chỉ khi state đặc biệt.
- Scan bị timeout hoặc incomplete, nhưng pipeline đánh dấu success.

**Không có finding không đồng nghĩa không có vulnerability.** Scan report phải gắn “coverage and limitations”.

### 17.3. Cách cải thiện độ tin cậy

- Dùng synthetic vulnerable/negative fixtures trong môi trường lab để kiểm chứng scanner/rule behavior.
- Đối chiếu route inventory với actual visited/method/role status.
- Kiểm session-health và login state thường xuyên.
- Test cross-tenant/role behavior ngoài scanner tổng quát.
- Triangulate với SAST/SCA/config review/manual testing.
- Chạy scan trên đúng release artifact; lưu scanner/tool version.
- Có separate source-health/scan-completion signals.
- Lưu failed tests và unreachable routes, không loại khỏi denominator.
- Đánh giá lại khi thêm route, tenant, data type, identity flow hoặc third party.

## 18. Đo web scan coverage đúng cách

Đếm requests hoặc URLs không nói đủ mức bảo đảm. Một URL có thể có:
- Nhiều HTTP methods.
- Nhiều roles/tenants.
- Nhiều resource ownership contexts.
- Nhiều content types và request variants.
- Nhiều allow/deny behaviors.
- Một hoặc nhiều side effects.

### 18.1. Đơn vị: scenario requirement

Một **coverage obligation** có thể là:

`(service, route, method, role, tenant/resource context, expected behavior, deployment)`

Ví dụ:
- Customer A + `GET /reports/{idA}` + own → allow only expected fields.
- Customer A + `GET /reports/{idB}` + other tenant → deny, no content.
- Anonymous + `GET /reports/{idA}` → deny.
- Support without case + `GET /reports/{idA}` → deny.
- Admin + `GET /admin/audit` → allow only approved audit fields.

### 18.2. Phân loại obligation

| Status | Ý nghĩa | Tính như verified? |
| --- | --- | --- |
| **PASS_VERIFIED** | Test đúng release/scope, behavior đạt, evidence fresh | Có |
| **FAIL_CONFIRMED** | Test thấy behavior không đáp ứng | Không |
| **NOT_RUN** | Chưa chạy | Không |
| **AUTH_FAILED** | Không vào đúng persona/session | Không |
| **INCONCLUSIVE** | Evidence hoặc result không đủ | Không |
| **STALE_EVIDENCE** | Kết quả của version/deployment cũ | Không |
| **EXCLUDED_APPROVED** | Không thuộc scope có rationale/authority | Báo riêng, không coi PASS |
| **NOT_APPLICABLE_VERIFIED** | Scenario không áp dụng có chứng cứ | Báo riêng, không trộn vào PASS |
| **EXCEPTION_ACTIVE** | Có chấp nhận rủi ro có điều kiện | Không biến technical result thành PASS |

### 18.3. Hai tỷ lệ nên báo riêng

~~~text
Scenario execution coverage (%) =
  100 × scenarios actually executed with valid identity and evidence
        / eligible in-scope scenarios

Scenario assurance pass coverage (%) =
  100 × eligible scenarios with verified PASS
        / eligible in-scope scenarios

Eligible scenarios = defined in-scope obligations
    − verified not-applicable/excluded obligations

NOT_RUN, AUTH_FAILED, INCONCLUSIVE, STALE and FAILED
remain in the eligible denominator.
~~~

Một scenario executed nhưng FAIL giúp execution coverage tăng, **không làm pass coverage tăng**. Đây là hai khái niệm khác nhau.

### 18.4. Ví dụ 50 scenarios

Một release có 50 in-scope scenarios, 5 được xác nhận không áp dụng theo decision có bằng chứng. Eligible = 45:
- 29 PASS_VERIFIED.
- 5 FAIL_CONFIRMED.
- 4 AUTH_FAILED.
- 3 NOT_RUN.
- 2 INCONCLUSIVE.
- 2 STALE_EVIDENCE.

Execution có thể được tính theo policy là 29 PASS + 5 FAIL = **34** scenarios hoàn tất với kết quả kiểm tra hợp lệ, tức **34/45 ≈ 75,6% execution coverage**.

**Pass coverage = 29/45 ≈ 64,4%.**

Không nên xóa bốn AUTH_FAILED hoặc hai stale entries khỏi mẫu số rồi báo con số đẹp hơn. Nếu population route/role ban đầu không đầy đủ, hai tỷ lệ cũng **chưa đại diện** cho toàn bộ hệ thống.

### 18.5. Coverage cần phân nhóm

- Critical Internet-facing API methods.
- Privileged/admin routes.
- Sensitive data read/export/write.
- Cross-tenant/object authorization.
- State-changing/async workflows.
- New routes vs legacy/deprecated.
- Region/environment/deployment.
- Tool/source health và authentication success.
- Browser/SPA vs REST/GraphQL/WebSocket.

Dashboard 95% tổng nhưng chưa có test cross-tenant cho payment/report API **không đủ** để kết luận security requirement đạt.

## 19. Security requirements cho chương trình web security scan

Những mã sau **chỉ là ví dụ học tập**; requirements thực phải gắn hệ thống, risk, owner, SLA, release policy và acceptance criteria của tổ chức.

| ID | Requirement có thể kiểm chứng | Phương pháp/evidence |
| --- | --- | --- |
| **WS-REQ-01** | Mọi web/API scan phải có authorized scope, owner, allowed methods, traffic budget và stop conditions | Approval record + scan configuration |
| **WS-REQ-02** | Scope discovery phải đối chiếu deployed routes với OpenAPI, gateway và workflow inventory | Route reconciliation report |
| **WS-REQ-03** | Critical protected routes phải có authenticated scenarios cho roles/tenants phù hợp | Persona matrix + test execution |
| **WS-REQ-04** | Scanner phải phát hiện mất authentication/session và không coi login redirect là tested protected route | Session sentinel + negative tests |
| **WS-REQ-05** | Active scan không được thực hiện hành động phá hủy hoặc third-party side effects ngoài scope | Scan profile, allow/deny list + cleanup |
| **WS-REQ-06** | Cross-tenant/object authorization phải được kiểm tra bằng fixtures known owner/non-owner | Manual/integration negative tests |
| **WS-REQ-07** | State-changing operations phải có observation của data/job/storage side effects khi đánh giá authorization | Side-effect evidence + audit |
| **WS-REQ-08** | Token/session/secrets và customer data không được đưa vào reports/log ngoài policy | Redaction checks + evidence access |
| **WS-REQ-09** | Tool/rule configuration, version, target environment và artifact/deployment identity phải được lưu với kết quả | Scan provenance record |
| **WS-REQ-10** | Coverage report phải nêu eligible scenarios, executed/PASS/FAIL/INCONCLUSIVE/NOT_RUN và exclusions | Coverage calculator + review |
| **WS-REQ-11** | Scan timeout, auth failure, route missing hoặc source unhealthy không được tính PASS | Failure-injection unit/integration test |
| **WS-REQ-12** | Critical confirmed findings phải có owner, risk assessment và remediation/retest plan | Finding register |
| **WS-REQ-13** | False positive/not affected phải có rationale, reviewer và evidence được lưu, không chỉ suppress rule | Triage record |
| **WS-REQ-14** | Exception/risk acceptance phải có authority, scope, expiry, monitoring; không biến technical finding thành fixed | Exception governance evidence |
| **WS-REQ-15** | Retest phải chạy trên đúng deployed artifact/config/route/persona và kiểm side effects | Repro scenario + retest result |
| **WS-REQ-16** | Thay trust boundary, authN/authZ, data flow, API route hoặc gateway phải kích hoạt scan/reassessment theo risk | Change impact/CI triggers |
| **WS-REQ-17** | Production active scan chỉ chạy nếu có approval và operational stop/rollback procedure | Authorization + on-call runbook |
| **WS-REQ-18** | Scanner/report credentials phải được bảo vệ, rotate và không xuất hiện trong CI artifacts | Secret scanning, access review |
| **WS-REQ-19** | Release quality gate phải xử lý confirmed critical findings và high-risk coverage gaps theo policy | Gate decision/audit |
| **WS-REQ-20** | Tool/source-health phải được kiểm chứng; không có alert/finding không đồng nghĩa không có vulnerability | Synthetic control checks |

### Traceability từ một finding

~~~text
RISK-REPORT-01:
  Customer of tenant A might read tenant B's report
  -> OBJECTIVE: Customer data confidentiality and tenant isolation
  -> REQUIREMENT: WS-REQ-06; object/resource authorization
  -> CONTROL: Trusted principal + ReportAccessPolicy + scoped query
  -> TEST: Customer A requests report owned by tenant B
  -> EXPECTED: Deny; no report body and no export side effect
  -> SCAN/TEST: Authenticated DAST journey + integration negative test
  -> EVIDENCE: Persona, request/response, CI run, deployment digest
  -> FINDING: Cross-tenant data disclosed (if observed)
  -> REMEDIATION: Server-side ownership check / query scope
  -> RETEST: Same wrong-tenant scenario on fixed deployment
  -> ASSURANCE: PASS, FAIL or INCONCLUSIVE within stated scope
~~~

Một request test có thể tạo evidence cho nhiều requirements, nhưng **mỗi requirement có acceptance criteria riêng**. Ví dụ có `403` chưa đủ cho logging requirement nếu audit event không được ghi.

## 20. Quality gates trong CI/CD

### 20.1. Scan phù hợp ở giai đoạn nào?

| Gate | Thời điểm | Loại kiểm tra | Kết quả cần giữ |
| --- | --- | --- | --- |
| Pull request | Source/config thay đổi | SAST, unit tests, authZ negative tests | Commit, test IDs, failures |
| CI build | Artifact mới | SCA, image scan, secret scan | Artifact digest, findings |
| Ephemeral staging | Sau deploy bản test | Passive baseline + smoke security tests | Scan ID, scoped routes |
| Integration/security stage | Khi có fixtures/sandbox | Authenticated DAST và API negative cases | Persona coverage, side effects |
| Release approval | Trước promote | Triage high-risk findings + coverage gaps | Gate decision và approved exceptions |
| Post-deploy verification | Đúng production release | Limited owner-approved controls | Actual runtime config/deploy ID |
| Periodic/risk-triggered | Theo risk/change/incident | Reassessment + DAST/manual scenarios | Updated evidence freshness |

Chạy DAST sau deploy staging không thay chứng minh production chạy **cùng artifact/config/security boundary**. Phải ràng buộc scan evidence với release promotion và có runtime checks khi cần.

### 20.2. Đầu vào gate

- Authorized target list và approved scan profile.
- Expected routes/methods/roles/tenants/scenarios.
- Login/session sentinel status.
- Tool version/plugin/rule set.
- Artifact digest, deployment ID, gateway policy version.
- Completed vs failed scan phases.
- Findings với severity/confidence/triage và risk mapping.
- Coverage metrics và critical untested scenarios.
- Exception IDs, expiry, owner và scope verification.
- Safe scan incident/side-effect observations.

### 20.3. Quy tắc gate minh họa

~~~text
if not authorization_for_scope_is_valid:
    BLOCK_SCAN_AND_RELEASE_AS_REQUIRED

scan = execute_approved_profile()

if scan.failed or scan.auth_context_invalid:
    return INCONCLUSIVE_OR_BLOCK_BY_RELEASE_POLICY

if scan.critical_route_coverage_missing:
    return INCONCLUSIVE_OR_BLOCK_BY_RELEASE_POLICY

for finding in scan.confirmed_findings:
    if finding.fully_fixed_and_retested_on_release:
        continue
    if policy.hard_block_applies(finding):
        BLOCK_RELEASE
    elif trusted_exception_is_valid_and_controls_verified(finding):
        RECORD_CONDITIONAL_RISK_DECISION
    else:
        BLOCK_OR_ESCALATE_BY_POLICY

if scan.high_risk_scenarios_have_verified_FAIL:
    BLOCK_OR_ESCALATE_BY_POLICY

if scan.evidence_is_stale_or_scope_mismatch:
    return INCONCLUSIVE

continue_other_release_security_gates()
~~~

**Không sử dụng exit code 0 của scanner như một claim PASS toàn hệ thống.** Exit code có thể chỉ thể hiện tool chạy được hoặc không có alerts thuộc mức được cấu hình; nó không chứng minh đủ scan coverage và không phát hiện business logic defect.

### 20.4. Điều kiện để có thể công bố PASS

- Scope/approval hợp lệ.
- Scanner/tool health và session health được xác minh.
- Expected critical scenarios thực sự đã chạy.
- Có kết quả PASS theo acceptance criteria riêng.
- Không có failed/untested scenario làm vô hiệu claim.
- Artifact/deployment/config đúng với bản được đánh giá.
- Findings/exception được quản trị minh bạch.
- Evidence có provenance/reviewer, lưu đúng quy định.
- Limitations không bị che và được đánh giá theo policy.

**PASS có phạm vi**, không phải tuyên bố phần mềm an toàn trong mọi điều kiện.

## 21. Java 17: tính scenario assurance coverage với bằng chứng

Ví dụ minh họa một bộ tổng hợp results có ba nguyên tắc:
- **Không tự coi một scenario chưa có observation là PASS**.
- Chỉ observation đúng `scenarioId + deploymentId` và evidence còn hợp lệ mới được tính vào executed/PASS.
- Một test thực thi và **FAIL** được tính là đã execution, nhưng không được tính assurance PASS.

Đây là logic aggregation phục vụ quản trị evidence; nó **không thay thế DAST engine, test runner, risk owner hoặc việc xác minh bản thân report là đáng tin**.

### 21.1. Model và calculator

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public final class WebScanCoverageCalculator {

    public enum Status {
        PASS_VERIFIED,
        FAIL_CONFIRMED,
        NOT_RUN,
        AUTH_FAILED,
        INCONCLUSIVE,
        STALE_EVIDENCE
    }

    public record Scenario(
            String scenarioId,
            String deploymentId) {}

    public record Observation(
            String scenarioId,
            String deploymentId,
            Status status,
            Instant observedAt,
            String evidenceRef) {}

    private record Key(String scenarioId, String deploymentId) {}

    public record Report(
            int eligible,
            int executed,
            int passed,
            int failed,
            int unresolved,
            Double executionCoveragePercent,
            Double assurancePassPercent) {}

    public Report calculate(
            List<Scenario> eligibleScenarios,
            List<Observation> observations,
            Clock clock,
            Duration maxEvidenceAge) {

        Objects.requireNonNull(eligibleScenarios);
        Objects.requireNonNull(observations);
        Objects.requireNonNull(clock);
        Objects.requireNonNull(maxEvidenceAge);

        if (maxEvidenceAge.isZero() || maxEvidenceAge.isNegative()) {
            throw new IllegalArgumentException("maxEvidenceAge must be positive");
        }

        Set<Key> population = new HashSet<>();

        for (Scenario scenario : eligibleScenarios) {
            if (scenario == null || blank(scenario.scenarioId())
                    || blank(scenario.deploymentId())) {
                throw new IllegalArgumentException("Invalid scenario");
            }
            Key key = new Key(
                    scenario.scenarioId(), scenario.deploymentId());
            if (!population.add(key)) {
                throw new IllegalArgumentException("Duplicate scenario");
            }
        }

        Map<Key, Observation> byKey = new HashMap<>();
        for (Observation obs : observations) {
            if (obs == null || blank(obs.scenarioId())
                    || blank(obs.deploymentId()) || obs.status() == null) {
                throw new IllegalArgumentException("Invalid observation");
            }
            Key key = new Key(obs.scenarioId(), obs.deploymentId());

            if (!population.contains(key)) {
                throw new IllegalArgumentException(
                        "Observation outside expected scope");
            }
            if (byKey.putIfAbsent(key, obs) != null) {
                throw new IllegalArgumentException(
                        "Conflicting/duplicate observation");
            }
        }

        Instant now = clock.instant();
        Instant earliest = now.minus(maxEvidenceAge);
        int executed = 0;
        int passed = 0;
        int failed = 0;

        for (Key scenario : population) {
            Observation obs = byKey.get(scenario);
            if (obs == null) {
                continue;
            }

            boolean fresh = obs.observedAt() != null
                    && !obs.observedAt().isAfter(now)
                    && !obs.observedAt().isBefore(earliest);
            boolean hasEvidence = !blank(obs.evidenceRef());
            if (!fresh || !hasEvidence) {
                continue;
            }

            if (obs.status() == Status.PASS_VERIFIED) {
                executed++;
                passed++;
            } else if (obs.status() == Status.FAIL_CONFIRMED) {
                executed++;
                failed++;
            }
            // AUTH_FAILED, INCONCLUSIVE, NOT_RUN không được
            // tính vào executed hay assurance PASS.
        }

        int eligible = population.size();
        int unresolved = eligible - executed;
        Double executionPercent = eligible == 0
                ? null : (100.0 * executed / eligible);
        Double assurancePercent = eligible == 0
                ? null : (100.0 * passed / eligible);

        return new Report(eligible, executed, passed, failed,
                unresolved, executionPercent, assurancePercent);
    }

    private static boolean blank(String value) {
        return value == null || value.isBlank();
    }
}
~~~

### 21.2. JUnit 5: negative tests cho metric integrity

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import org.junit.jupiter.api.Test;

class WebScanCoverageCalculatorTest {

    private static final Instant NOW =
            Instant.parse("2026-11-28T04:00:00Z");
    private static final Clock CLOCK =
            Clock.fixed(NOW, ZoneOffset.UTC);
    private static final Duration MAX_AGE =
            Duration.ofHours(24);

    private final WebScanCoverageCalculator calculator =
            new WebScanCoverageCalculator();

    private WebScanCoverageCalculator.Scenario scenario(String id) {
        return new WebScanCoverageCalculator.Scenario(id, "deploy-17");
    }

    private WebScanCoverageCalculator.Observation observation(
            String id, WebScanCoverageCalculator.Status status,
            Instant observedAt, String evidence) {
        return new WebScanCoverageCalculator.Observation(
                id, "deploy-17", status, observedAt, evidence);
    }

    @Test
    void executedFailureDoesNotIncreasePassCoverage() {
        var result = calculator.calculate(
                List.of(scenario("OWN_READ"), scenario("CROSS_TENANT"),
                        scenario("ADMIN_DENY")),
                List.of(
                        observation("OWN_READ",
                                WebScanCoverageCalculator.Status.PASS_VERIFIED,
                                NOW, "EV-01"),
                        observation("CROSS_TENANT",
                                WebScanCoverageCalculator.Status.FAIL_CONFIRMED,
                                NOW, "EV-02"),
                        observation("ADMIN_DENY",
                                WebScanCoverageCalculator.Status.AUTH_FAILED,
                                NOW, "EV-03")),
                CLOCK, MAX_AGE);

        assertEquals(3, result.eligible());
        assertEquals(2, result.executed());
        assertEquals(1, result.passed());
        assertEquals(1, result.failed());
        assertEquals(1, result.unresolved());
        assertEquals(100.0 * 2 / 3,
                result.executionCoveragePercent(), 0.0001);
        assertEquals(100.0 / 3,
                result.assurancePassPercent(), 0.0001);
    }

    @Test
    void stalePassIsNotAccepted() {
        var result = calculator.calculate(
                List.of(scenario("OWN_READ")),
                List.of(observation(
                        "OWN_READ",
                        WebScanCoverageCalculator.Status.PASS_VERIFIED,
                        NOW.minus(Duration.ofDays(5)), "OLD-EVIDENCE")),
                CLOCK, MAX_AGE);

        assertEquals(0, result.passed());
        assertEquals(0, result.executed());
    }

    @Test
    void missingEvidenceCannotProducePass() {
        var result = calculator.calculate(
                List.of(scenario("CROSS_TENANT")),
                List.of(observation(
                        "CROSS_TENANT",
                        WebScanCoverageCalculator.Status.PASS_VERIFIED,
                        NOW, null)),
                CLOCK, MAX_AGE);

        assertEquals(0, result.passed());
    }

    @Test
    void wrongDeploymentMustNotInheritTestResult() {
        var wrongRelease = new WebScanCoverageCalculator.Observation(
                "OWN_READ", "deploy-18",
                WebScanCoverageCalculator.Status.PASS_VERIFIED,
                NOW, "EV-WRONG");

        assertThrows(IllegalArgumentException.class, () ->
                calculator.calculate(
                        List.of(scenario("OWN_READ")),
                        List.of(wrongRelease), CLOCK, MAX_AGE));
    }

    @Test
    void futureTimestampIsNotCurrentEvidence() {
        var result = calculator.calculate(
                List.of(scenario("OWN_READ")),
                List.of(observation(
                        "OWN_READ",
                        WebScanCoverageCalculator.Status.PASS_VERIFIED,
                        NOW.plusSeconds(3600), "EV-FUTURE")),
                CLOCK, MAX_AGE);

        assertEquals(0, result.passed());
    }

    @Test
    void duplicateScenarioIsRejected() {
        assertThrows(IllegalArgumentException.class, () ->
                calculator.calculate(
                        List.of(scenario("OWN_READ"),
                                scenario("OWN_READ")),
                        List.of(), CLOCK, MAX_AGE));
    }

    @Test
    void noEligibleScenariosIsNotOneHundredPercent() {
        var result = calculator.calculate(
                List.of(), List.of(), CLOCK, MAX_AGE);

        assertEquals(0, result.eligible());
        assertNull(result.assurancePassPercent());
        assertNull(result.executionCoveragePercent());
    }
}
~~~

### 21.3. Giới hạn của ví dụ

- Program nhận `PASS_VERIFIED` từ nguồn ngoài, không tự xác minh request/response hoặc chữ ký chứng cứ. Hệ thống thật phải kiểm tra tool identity, authorized scope, test correctness, integrity và approval.
- `maxEvidenceAge` là rule minh họa; cần refresh/invalidations theo **change triggers** chứ không chỉ TTL.
- Nguồn obligation list phải xuất phát từ route/role/tenant inventory đã reconcile; nếu thiếu route, tỷ lệ có thể cao giả.
- Tool có thể gửi request nhưng không bao phủ negative authZ; status được tính PASS chỉ khi **acceptance criteria riêng** đã kiểm.
- Exclusions/NOT_APPLICABLE cần decision/evidence riêng trước khi xây `eligibleScenarios`.
- Duplicate observations trong cùng snapshot bị từ chối để tránh chọn một bản “xanh nhất”; upstream phải xử lý historical runs, conflicting sources và phiên bản.
- Các tests chỉ kiểm chứng **aggregation logic**; không thay thực thi DAST/MockMvc/HTTP integration tests.

## 22. Web scan evidence register

Một record có thể được viết YAML để quản lý và truy vết, nhưng phải bảo vệ access/integrity và không nhúng secret trong report.

### 22.1. Mẫu YAML

Các giá trị trong `<...>` là **placeholder**, không phải kết quả thật.

~~~yaml
assessment_id: WEB-SCAN-003
module: SECURITY_SECURITY_ASSURANCE
topic: Web security scan
service: report-platform
assessment:
  stage: pre-release-staging
  assessed_at: "<ISO_8601_UTC>"
  reviewer: "<AUTHORIZED_REVIEWER>"
  objective_ids: ["<SECURITY_OBJECTIVES>"]
  risk_ids: ["<RISK_IDS>"]
authorization:
  approval_ref: "<APPROVED_SCAN_AUTHORIZATION>"
  owner: "<SYSTEM_OWNER>"
  valid_window: "<APPROVED_TIME_WINDOW>"
  permitted_profile: "passive-and-scoped-authenticated"
  allowed_targets: ["<STAGING_HOSTS_AND_PORTS>"]
  excluded_actions:
    - "real-payment"
    - "account-deletion"
    - "third-party-callback"
  traffic_budget_ref: "<RATE_CONCURRENCY_LIMITS>"
  stop_runbook_ref: "<OPS_STOP_PROCEDURE>"
target:
  environment: staging
  regions: ["<REGIONS>"]
  source_commit: "<COMMIT_ID>"
  artifact_digest: "<DEPLOYED_IMAGE_OR_JAR_DIGEST>"
  deployment_id: "<DEPLOYMENT_ID>"
  gateway_policy_version: "<GATEWAY_POLICY_VERSION>"
inventory:
  expected_routes_ref: "<ROUTE_METHOD_INVENTORY>"
  openapi_ref: "<APPROVED_OPENAPI_DOCUMENT>"
  personas_ref: "<ROLE_AND_TENANT_TEST_FIXTURES>"
  reconciliation_ref: "<COVERAGE_DIFF_REPORT>"
scan_tool:
  product: "OWASP ZAP"
  version: "<PINNED_VERSION>"
  profile_ref: "<SCAN_POLICY_AND_RULE_SET>"
  run_id: "<CI_OR_SCAN_RUN>"
  started_at: "<ISO_8601_UTC>"
  completed_at: "<ISO_8601_UTC>"
  exit_status: "<RUN_STATUS>"
  scanner_health: "<HEALTH_CHECK_RESULT>"
  auth_session_health: "<LOGIN_STATE_SENTINEL>"
coverage:
  metric_version: "1.0"
  unit: "route-method-persona-resource-context-deployment"
  eligible_scenarios: 45
  executed_valid: 34
  verified_pass: 29
  confirmed_fail: 5
  auth_failed: 4
  not_run: 3
  inconclusive: 2
  stale: 2
  excluded_verified_not_applicable: 5
  execution_percent: 75.56
  assurance_pass_percent: 64.44
  high_risk_uncovered: ["<SCENARIO_IDS>"]
results:
  sanitized_report_ref: "<PROTECTED_SCAN_REPORT>"
  raw_report_ref: "<RESTRICTED_RAW_EVIDENCE>"
  findings: ["<FINDING_IDS>"]
  manual_tests: ["<NEGATIVE_AUTHORIZATION_TESTS>"]
  operational_side_effects_ref: "<STAGING_JOB_STORAGE_AUDIT_CHECKS>"
decisions:
  result: "<PASS_FAIL_INCONCLUSIVE>"
  exception_refs: ["<ACTIVE_EXCEPTIONS_IF_ANY>"]
  limitations:
    - "<UNSCANNED_LEGACY_ROUTES>"
    - "<UNSUPPORTED_BROWSER_OR_API_BEHAVIOR>"
    - "<MISSING_ROLE_OR_TENANT_CONTEXT>"
reassessment_triggers:
  - "New API method, role, tenant or sensitive field"
  - "Identity/session/authorization control changed"
  - "Gateway, WAF, TLS or deployment routing changed"
  - "New incident, risk or finding"
  - "Scanner source/rule/coverage failure"
~~~

Trong record ví dụ, numbers 45/34/29 là từ mục 18; **không là kết quả thật**. `decisions.result` chỉ được đánh giá từ policy acceptance và evidence; coverage chưa đủ không nên được mô tả là PASS chỉ vì tool chạy xong.

### 22.2. Evidence mỗi finding

| Trường | Ghi gì? |
| --- | --- |
| Finding ID | ID ổn định, liên kết scanner alert |
| Route/method/persona | Context cụ thể |
| Environment/deployment/digest | Bản được kiểm |
| Expected behavior | Security requirement/acceptance |
| Observed behavior | Sai khác đã xác minh |
| Request reference | Sanitized, redacted, protected |
| Response reference | Status/body/headers, không chứa secret thừa |
| Side-effect observation | DB/job/storage/audit result nếu cần |
| Tool/version/rule | Nguồn tìm thấy |
| Risk/context | Severity, exposure, impact, confidence |
| Finding owner | Nhóm chịu khắc phục |
| Remediation reference | PR/change/feature flag/config |
| Retest result | Trên artifact/deployment mới |
| Reviewer/time | Ai xác nhận, lúc nào |
| Exception/risk | Chỉ nếu có quyết định hợp lệ |

### 22.3. Evidence privacy và secret hygiene

Proxy/DAST tools có thể ghi:
- Authorization headers/cookies/CSRF tokens.
- Query parameters chứa PII hoặc URLs nhạy cảm.
- Request/response bodies có customer data.
- Webhook signatures và signed URLs.
- Internal hostnames, API keys, session IDs.

Bảo vệ evidence bằng:
- Synthetic fixtures khi có thể.
- Redaction tại nguồn và protected raw reports khi buộc phải giữ.
- Identity/secret scanning của generated reports.
- Encryption/access control, audit access và retention.
- Tránh đưa raw scan logs vào public PR comments.
- Không lộ credentials trong shell command, config committed hoặc CI stdout.
- Có process purge/revoke khi vô tình thu thập credential/data thật.

## 23. Remediation, retest, ngoại lệ và continuous assurance

### 23.1. Remediation workflow

1. Triage finding với risk/requirement và owner.
2. Reproduce bằng test trong controlled environment nếu an toàn.
3. Xác định root cause: authorization, schema, output encoding, configuration hoặc dependency.
4. Sửa với code/config/change record có review.
5. Chạy regression, unit, integration và negative security tests.
6. Triển khai fixed artifact vào testing environment.
7. **Retest chính scenario trước đây fail**, gồm response và side effect.
8. Xác minh production/admission context theo release policy.
9. Lưu evidence, reviewer và đổi finding state khi đủ.
10. Theo dõi changes/regressions trong tương lai.

### 23.2. Retest không phải “scan lại và không thấy alert”

Nếu scan cũ phát hiện cross-tenant data leak nhưng scan mới chỉ chạy anonymous:
- Alert có thể biến mất vì scanner không vào protected endpoint.
- Không có bằng chứng fix.
- Finding vẫn nên **OPEN hoặc INCONCLUSIVE**, không `VERIFIED_CLOSED`.

Cần lặp test user A → report B trên **đúng fixed deployment** với fixture và side-effect checks, hoặc một verification method được assessor chấp nhận có coverage tương đương.

### 23.3. Exception và compensating controls

Nếu chưa thể fix đúng hạn:
- Đánh giá risk theo actual exploit path, business impact và exposure.
- Xem xét disable route, tighten authZ, network segmentation, feature flags, WAF rule hoặc giới hạn scope.
- Verify control bằng negative/bypass tests; WAF ngoài gateway không bảo vệ direct API/queue path.
- Xin risk owner phê duyệt exception **có scope, expiration, conditions, monitoring và remediation milestones** nếu policy cho phép.
- Giữ technical finding state riêng, không đổi thành fixed.
- Reassess khi có exploit mới, route/tenant thay đổi, mitigation drift, exception hết hạn hoặc patch/fix xuất hiện.

### 23.4. Tần suất scan theo rủi ro

Không có một nhịp quét cố định phù hợp mọi application. Có thể dùng:
- PR/CI negative tests cho code và authZ logic.
- Staging DAST khi có deployed candidate release.
- Periodic baseline trên approved production scope.
- Event-driven scan khi thêm endpoint, auth flow, tenant, data field hoặc gateway/WAF.
- Risk-triggered verification khi có incident/advisory/known exploit.
- Targeted retest ngay sau remediation.

**Mỗi scan mới phải ghi scope, tool version, rule set, artifact, evidence freshness và changes từ scan trước**, tránh so sánh raw alert count như thể mọi lượt kiểm tra là tương đương.

### 23.5. Dashboard đo những gì?

| Metric | Giúp phát hiện | Giới hạn |
| --- | --- | --- |
| % critical scenarios verified PASS | Đáp ứng yêu cầu trọng yếu | Phụ thuộc inventory và đúng acceptance |
| % eligible scenarios executed | Độ bao phủ kiểm thử | FAIL cũng có thể tăng execution |
| Auth success/session health | Protected routes thực sự được scan | Login hợp lệ không bằng authZ đúng |
| Routes not discovered | Coverage gap | Inventory có thể thiếu |
| Confirmed critical/high findings | Risk remediation urgency | Tool severity không bằng full risk |
| Open findings age/retest due | Remediation debt | Ticket closed không đồng nghĩa fixed |
| Exceptions active/expiring | Chấp nhận rủi ro có điều kiện | Không là technical PASS |
| Tool/scanner outage/timeout | False green risk | Cần independent source health |
| False-positive rate by rule | Tuning và triage quality | Không được che vulnerabilities thật |
| Evidence freshness/validity | Tin cậy claim | Evidence mới vẫn có thể sai scope |
| High-risk untested paths | Quan trọng hơn tỷ lệ trung bình | Cần owner và plan |
| Unintended side effects | Scan operational safety | Cần monitoring và stop runbook |

Tránh KPI “0 findings” làm nhóm tắt rules hoặc giảm coverage. Kết hợp **risk, completeness, verified outcomes và remediation**.

## 24. Case study – Quét nền tảng báo cáo tài chính đa tenant

### 24.1. Bối cảnh

Hệ thống chạy Java/Spring Boot với:
- React SPA gọi `report-api` qua API gateway/WAF.
- OIDC identity provider.
- PostgreSQL lưu report theo tenant.
- Kafka cho export jobs và worker ghi object storage.
- Signed download URLs.
- `/admin/audit` và một legacy export route.
- CI/CD deploy container image digest tới hai Kubernetes regions.
- Công cụ DAST được chạy trên staging sau mỗi release candidate.

Nhóm QA nhận report:
> “DAST scan hoàn thành, không có High/Critical. Release đạt security gate.”

Nhưng khi đối chiếu thấy:
1. Scanner chạy anonymous session, liên tục nhận `302` tới login.
2. OpenAPI chỉ chứa `/api/v2`, bỏ `/api/v1/legacy-export`.
3. Không có user fixture ở tenant B, nên không thể test BOLA.
4. Support role có thể xem report không thuộc case đã duyệt.
5. Export endpoint trả `202 Accepted` trước khi worker kiểm quyền; chưa có side-effect test.
6. WAF block nhiều request test nhưng direct service route nội bộ chưa được đánh giá.
7. Một region chạy image cũ với configuration khác.
8. Scan report lưu Authorization header của test account trong CI artifact không được bảo vệ.

**Kết luận ban đầu:** không đủ điều kiện gọi security assurance PASS. Có **coverage gaps, identity/session failure, potential authorization issue và evidence hygiene problem**, ngay cả khi scanner không báo findings.

### 24.2. Mục tiêu bảo mật

| Objective | Risk scenario | Requirement minh họa |
| --- | --- | --- |
| Tenant isolation | Customer A đọc report B | WS-REQ-06, object-level authZ |
| Support least privilege | Support đọc report ngoài case | Case authorization và expiry |
| Async export integrity | Job vẫn chạy dù deny/revoke | Side-effect/worker authorization |
| Sensitive data protection | Report/headers bị lộ | Field allowlist + secret redaction |
| Release assurance | Scanner chạy sai scope/deploy | WS-REQ-09/10/15 |
| Attack surface completeness | Legacy route không được inventory | WS-REQ-02 |
| Operational safety | Active scan gây job/file thật | WS-REQ-05/17 |

### 24.3. Thiết kế fixtures

- `customer-a`, `customer-b` ở hai tenants khác nhau.
- `report-a` thuộc tenant A; `report-b` thuộc tenant B.
- `support-no-case` không có assigned case.
- `support-case-a` chỉ được truy cập report A trong thời hạn case được duyệt.
- `auditor` được phép xem audit metadata nhưng không customer raw payload.
- `export-worker` có workload identity chỉ đọc/ghi resource prefix phù hợp.
- Test data synthetic, không chứa PII thật.
- Queues/buckets của staging tách production, có cleanup.
- Session sentinel xác nhận từng persona đúng identity trước mỗi run.

### 24.4. Ma trận test theo trust boundary

| Test | Persona và thao tác | Expected |
| --- | --- | --- |
| **CASE-01** | Anonymous đọc `report-a` | Deny, không có report content |
| **CASE-02** | Customer A đọc `report-a` | Allow approved fields |
| **CASE-03** | Customer A đọc `report-b` | Deny, không side effect |
| **CASE-04** | Customer B đọc `report-a` | Deny, không content leak |
| **CASE-05** | Customer A gửi `X-Tenant-ID: tenant-B` | Header không tăng quyền |
| **CASE-06** | Support không case đọc `report-a` | Deny |
| **CASE-07** | Support có case đã duyệt đọc `report-a` | Allow scoped fields; audit event |
| **CASE-08** | Support case hết hạn đọc `report-a` | Deny |
| **CASE-09** | Customer A gọi export report B | Deny, không tạo Kafka job/file |
| **CASE-10** | Export job retry sau revoke | Worker không tạo export ngoài policy |
| **CASE-11** | Customer gọi `/admin/audit` | Deny |
| **CASE-12** | Auditor gọi `/admin/audit` | Allow only approved metadata |
| **CASE-13** | Truy cập legacy export route | Có authZ tương đương v2 hoặc finding |
| **CASE-14** | Session expired trong scan | Phát hiện AUTH_FAILED, không báo coverage |
| **CASE-15** | Gateway/WAF bypass qua internal route | Kiểm effective authZ tại service |
| **CASE-16** | Test request/response được lưu | Không có raw token/real customer data |
| **CASE-17** | Scan ở region A nhưng production có region B | Evidence không tự áp region B |
| **CASE-18** | Signed download URL sau expiry | Download bị từ chối theo policy |
| **CASE-19** | Một export job được phép | Đúng tenant/prefix/expiry/audit |
| **CASE-20** | Thêm một `/api/v3` route | Inventory/review/scans cập nhật trước release |

**Không phải mọi test đều được làm tự động bằng ZAP**. Các tests cho queue, case expiry, tenant ownership và worker identity cần integration/manual workflows với fixtures và backend observations.

### 24.5. Spring Boot/MockMvc test mẫu

Đoạn sau minh họa **kỳ vọng** cho một application đã có endpoint và server-side policy tương ứng. Nó không phải một application độc lập. Cần các dependencies Spring Boot Test và Spring Security Test trong môi trường kiểm thử.

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ReportTenantAuthorizationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void tenantCanReadOwnReport() throws Exception {
        mockMvc.perform(get("/api/reports/{id}", "report-a")
                .with(jwt()
                        .jwt(jwt -> jwt.subject("customer-a")
                                .claim("tenant_id", "tenant-A"))
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_report.read"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.reportId").value("report-a"))
                .andExpect(jsonPath("$.rawAccessToken").doesNotExist());
    }

    @Test
    void tenantCannotReadAnotherTenantsReport() throws Exception {
        mockMvc.perform(get("/api/reports/{id}", "report-b")
                .with(jwt()
                        .jwt(jwt -> jwt.subject("customer-a")
                                .claim("tenant_id", "tenant-A"))
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_report.read"))))
                .andExpect(status().isForbidden());
    }

    @Test
    void anonymousRequestCannotReadReport() throws Exception {
        mockMvc.perform(get("/api/reports/{id}", "report-a"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void spoofedTenantHeaderMustNotGrantAccess() throws Exception {
        mockMvc.perform(get("/api/reports/{id}", "report-b")
                .header("X-Tenant-ID", "tenant-B")
                .with(jwt()
                        .jwt(jwt -> jwt.subject("customer-a")
                                .claim("tenant_id", "tenant-A"))
                        .authorities(new SimpleGrantedAuthority(
                                "SCOPE_report.read"))))
                .andExpect(status().isForbidden());
    }
}
~~~

**Giới hạn quan trọng:**
- `jwt()` trong MockMvc tạo authentication test context; nó **không tự chứng minh signature/issuer/audience validation** của real OIDC flow. Cần token negative tests ở integration/end-to-end boundary.
- Cần fixtures `report-a` và `report-b` thuộc đúng tenants; nếu database test không có dữ liệu, các test có thể fail hoặc cho kết luận sai.
- 403 là **policy choice minh họa**. Ứng dụng có thể dùng 404 để không lộ object existence; acceptance phải theo contract, không đổi tùy tiện.
- Assertion `rawAccessToken` không có chỉ kiểm một field; cần response field allowlist và log/trace redaction tests toàn diện.
- MockMvc không tự quan sát Kafka job/file/side effect; bổ sung integration tests.
- Claim coverage chỉ áp vào controller/path/version/deployment đã kiểm; không tự áp cho legacy route hoặc production gateway.

### 24.6. Chuyển gaps thành remediation

| Gap | Owner | Remediation | Retest |
| --- | --- | --- | --- |
| Scanner mất session | QA/AppSec | Session health + fixture auth | CASE-14 |
| OpenAPI thiếu legacy | API Team | Route inventory/contract reconciliation | CASE-13/20 |
| Không có tenant B | QA/Data owner | Synthetic tenant A/B resources | CASE-03/04 |
| Support bypass case | API Team | Server-side case/resource authZ | CASE-06/07/08 |
| Worker export thiếu check | API/Worker Team | Job scope/expiry/authorization | CASE-09/10 |
| WAF-only confidence | Platform/AppSec | Effective service policy + bypass tests | CASE-15 |
| Two-region mismatch | Release/Ops | Digest-bound rollout + region verification | CASE-17 |
| Report chứa token | CI/Security | Redaction, restricted artifacts, secret revoke if leaked | CASE-16 |

### 24.7. Scoped assurance claim

> Trong phạm vi những routes/methods và personas đã kiểm thử trên staging deployment digest được ghi nhận, các cases về authentication, tenant/resource authorization và response field access có kết quả được xác minh theo acceptance; automated/passive scan findings được triage và có evidence. Các routes/roles không chạy, worker side effects, legacy API, region khác và production configuration khác được ghi là limitations hoặc kiểm thử riêng, không tự suy là PASS.

Nếu test CASE-03 FAIL hoặc CASE-14 AUTH_FAILED, claim tenant isolation **không đạt** dù dashboard DAST tổng có ít alerts.

## 25. Case study thứ hai – Scan “xanh” do WAF và session timeout

### Bối cảnh

Một portal quản trị nội bộ dùng SSO, MFA, WAF và server-rendered forms. Scanner được phép chạy authenticated staging nhưng report:
- `2.000 HTTP requests`.
- `0 confirmed High/Critical findings`.
- `100% HTTP response received`.

Kiểm tra logs thấy:
- 70% requests nhận `302 /login` do session hết hạn.
- 20% requests bị WAF trả `403` trước khi vào application.
- 10% requests chạm vào public landing page và health.
- Không có protected route được kiểm với role admin hợp lệ.
- Một hidden feature chỉ truy cập được sau MFA không được crawl.
- DAST tool không gửi required CSRF token cho forms.

### Phân tích

| Dấu hiệu “xanh” | Vì sao không đủ? | Bằng chứng cần bổ sung |
| --- | --- | --- |
| 2.000 requests | Request count không đồng nghĩa route/scenario coverage | Endpoint/method/persona matrix |
| 0 High/Critical | Scanner chưa tới logic nhạy cảm | Authenticated critical tests |
| WAF 403 | WAF có thể block scanner, không chứng minh backend đúng | Effective app authZ tests |
| Login redirects | Không còn authenticated session | Login sentinel và refresh |
| MFA flow không chạy | Privileged paths untested | Manual-approved MFA test |
| CSRF token missing | Forms không được exercise đúng | Valid state-changing test + missing-token denial |
| All HTTP responses received | Availability của HTTP không đồng nghĩa bảo mật | Expected behavior/side-effect tests |

**Kết luận phù hợp:** `INCONCLUSIVE` đối với authenticated web security coverage, dù công cụ hoàn tất một số passive observations. Nhóm cần:
- Sửa test login flow và xác minh session health.
- Có dedicated privileged test account với đúng approval.
- Test CSRF token behavior bằng fixtures.
- Đối chiếu protected-route inventory.
- Scan lại trong traffic/operational limits.
- Giữ evidence cũ và mới với tool/scope/time để giải thích vì sao kết quả khác.

**Bài học:** WAF, MFA và auth gateway có thể làm scanner không tới được code cần kiểm. Điều này có thể đúng về defense boundary, nhưng muốn kết luận control hiệu lực phải kiểm chứng explicit deny behavior và không có alternate route; muốn đánh giá ứng dụng cần test authorized flows với đúng persona.

## 26. Bộ test case tham khảo cho web scan assurance

Các tests dưới đây dành cho **ứng dụng, tài khoản, môi trường được cho phép**, sử dụng synthetic fixtures hoặc phương pháp phù hợp. Không tự chạy intrusive probes trên tài sản ngoài phạm vi.

| Test ID | Điều kiện | Kết quả mong đợi |
| --- | --- | --- |
| **WS-T01** | Redirect dẫn tới host ngoài approved scope | Scanner không tự mở rộng scope |
| **WS-T02** | Method state-changing thuộc exclude list | Không chạy active auto-test |
| **WS-T03** | Scanner login đúng persona | Session sentinel xác minh principal/role/tenant |
| **WS-T04** | Session hết hạn giữa run | Ghi AUTH_FAILED/INCONCLUSIVE, không tính PASS |
| **WS-T05** | Anonymous đọc protected resource | Deny, không body/side effect |
| **WS-T06** | Wrong issuer, expired token | Deny tại authN boundary |
| **WS-T07** | Customer A đọc own resource | Allow only approved fields |
| **WS-T08** | Customer A đọc tenant B resource | Deny, không data leak |
| **WS-T09** | Client spoof tenant/role headers | Không tăng quyền |
| **WS-T10** | Support không có case duyệt | Deny |
| **WS-T11** | Support case hết hạn | Deny, audit event |
| **WS-T12** | Low privilege role vào admin route | Deny |
| **WS-T13** | Missing/invalid CSRF context trong state change dùng session cookie | Deny theo policy |
| **WS-T14** | Valid origin/CSRF context | State change chỉ trong fixture scope |
| **WS-T15** | Untrusted origin gọi credentialed CORS route | Không mở origin ngoài policy |
| **WS-T16** | Cookie thiếu attributes bắt buộc | Config finding |
| **WS-T17** | Sensitive response có cache policy sai | Finding |
| **WS-T18** | TLS wrong hostname/certificate | Client verification từ chối |
| **WS-T19** | File upload vượt size/type duyệt | Deny, không tạo resource ngoài sandbox |
| **WS-T20** | Redirect destination ngoài allowlist | Deny/controlled behavior |
| **WS-T21** | Untrusted input được hiển thị | Contextual output handling |
| **WS-T22** | Invalid type/range | Validation response, không lộ stack trace/secrets |
| **WS-T23** | Forbidden export request | Không tạo queue job/file |
| **WS-T24** | Worker chạy export sau revoke | Theo policy authorization |
| **WS-T25** | Signed download URL hết hạn | Deny |
| **WS-T26** | Legacy route không nằm OpenAPI | Discovery gap hiển thị |
| **WS-T27** | Thêm API version/route | Trigger inventory và test |
| **WS-T28** | SPA protected route không crawl được | Coverage gap, không PASS |
| **WS-T29** | WAF block scanner trước backend | Không suy backend security PASS |
| **WS-T30** | Scanner timeout/crash | NOT_RUN/INCONCLUSIVE |
| **WS-T31** | Rule bị tắt do config | Source/rule health gate báo |
| **WS-T32** | Evidence thiếu deployment ID/digest | Không accept VERIFIED_PASS |
| **WS-T33** | Staging PASS nhưng production release khác | Không tự chuyển production PASS |
| **WS-T34** | Code fix đã merge nhưng chưa deploy | Finding chưa VERIFIED_CLOSED |
| **WS-T35** | Retest old failing case trên fixed release | Có thể đóng nếu đáp ứng criteria |
| **WS-T36** | Approved exception hết hạn | Không bypass release policy |
| **WS-T37** | Raw scan report chứa Authorization header | Evidence hygiene finding, xử lý token nếu lộ |
| **WS-T38** | Scan gây unexpected external email/job | Stop/recover theo runbook |
| **WS-T39** | Critical route thiếu tenant B fixture | High-risk coverage gap, không PASS |
| **WS-T40** | Scenario chuyển PASS thành FAIL | Execution có thể không giảm; pass coverage giảm |

### Test theo nhiều lớp

- **Unit:** report parsing, status, numerator/denominator, evidence freshness.
- **Integration:** authN/authZ, roles, tenants, API contract, DB/queue side effects.
- **DAST passive:** headers, cookies, redirect, cache-control indicators.
- **DAST controlled active:** behavior runtime trong staging có approval.
- **Manual:** business logic, ownership/approval, workflow transitions.
- **Operational:** source health, request budget, stop/recovery procedures.
- **Release:** artifact identity, promotion, exception/retest.

Phải phân biệt **test plan** với **đã thực thi thành công**. Danh sách 40 tests không phải bằng chứng rằng chúng đã chạy trên một hệ thống cụ thể.

## 27. Bài tập thực hành

### Tình huống

Một doanh nghiệp vận hành Spring Boot + React phục vụ đơn hàng và hồ sơ khách hàng với:
- API gateway/WAF và OIDC.
- PostgreSQL multi-tenant.
- Kafka export worker, object storage và signed URLs.
- OpenAPI chỉ có `/api/v2`, còn legacy `/api/v1/export`.
- SPA support role cần MFA.
- Staging có synthetic data, production chứa dữ liệu nhạy cảm.
- CI chạy ZAP baseline khi merge.
- Report “0 High/Critical” nhưng scanner chỉ thấy anonymous routes.

### Yêu cầu

1. Xác định authorized scan scope theo host, environment, routes, roles, traffic budget, exclusions và stop conditions.
2. Vẽ DFD, đánh dấu browser/gateway/IdP/service/DB/queue/storage/third-party boundaries.
3. Lập ít nhất **12 route–method–role–tenant–resource scenarios** với expected behavior.
4. Phân biệt passive findings với authZ/business logic tests cần manual/integration.
5. Thiết kế test identities: customer A/B, support no-case/case-approved, auditor và workload.
6. Xác định session-expiry, MFA-context và auth-redirect detection.
7. Giải thích tại sao `0 alerts` và `2.000 requests` không chứng minh scan completeness.
8. Thiết kế cross-tenant test và export-denial test có backend side-effect checks.
9. Tính coverage cho 40 eligible scenarios: 24 PASS, 5 FAIL, 4 AUTH_FAILED, 3 NOT_RUN, 2 INCONCLUSIVE, 2 STALE. Giải thích tác động khi thêm 5 route/scenarios mới.
10. Viết tối thiểu **10 security requirements** có ID, owner, risk, acceptance, verification và evidence.
11. Tạo YAML evidence record gắn release digest, tool version, auth/session health, route inventory và limitations.
12. Thiết lập CI gate cho scanner outage, critical authZ gap, expired exception và failed retest.
13. Thiết kế safe staging scan cho `POST /export` không gửi email/tạo file ngoài sandbox.
14. Triaging ba trạng thái: confirmed authZ gap, suspected header issue, false positive có evidence.
15. Xây remediation/retest plan cho legacy endpoint và cross-tenant gap.
16. Viết scoped assurance claim với PASS/FAIL/INCONCLUSIVE và unresolved limitations.

### Hướng giải cho câu 9

~~~text
Eligible scenarios = 40
Valid executed = 24 PASS + 5 FAIL = 29
Execution coverage = 29 / 40 × 100 = 72.5%
Assurance PASS = 24 / 40 × 100 = 60%

Remaining AUTH_FAILED/NOT_RUN/INCONCLUSIVE/STALE = 11
Confirmed FAIL = 5

Nếu thêm 5 scenarios chưa kiểm thử:
New eligible = 45
Executed = 29/45 ≈ 64.4%
PASS = 24/45 ≈ 53.3%
~~~

Không loại AUTH_FAILED hoặc STALE khỏi denominator để tăng tỷ lệ. Cần xác nhận **tập 40/45 scenarios đủ đại diện cho các critical paths thực sự hay chưa**.

### Câu hỏi nâng cao

Scanner xác nhận HTTP `403` khi customer A gọi `GET /api/reports/report-b`. Có thể tuyên bố tenant isolation PASS cho cả hệ thống không?

**Gợi ý:** chưa. Kết quả chỉ chứng minh hành vi của một route, persona, fixture và deployment. Các methods, indirect exports, field-level disclosure, cache, worker/queue, legacy API, region/config và revocation còn cần xem xét. Có thể kết luận PASS **cho test case cụ thể**, không tự suy ra tất cả endpoints.

## 28. Những sai lầm thường gặp

| Ngộ nhận | Vì sao sai? | Thực hành đúng |
| --- | --- | --- |
| “Web scan thành công nghĩa là secure.” | Chỉ kiểm phạm vi đã scan | Scoped claim và limitations |
| “Không có High finding thì PASS.” | Auth/route coverage có thể thiếu | Completeness và risk gates |
| “Nhiều requests là coverage cao.” | Có thể chủ yếu là `302 /login` | Scenario coverage |
| “Passive scan kiểm được business logic.” | Thiếu ownership/case context | Manual/integration tests |
| “Đăng nhập admin là đủ cho mọi test.” | Không kiểm least privilege/tenant | Persona matrix |
| “WAF 403 chứng minh backend đúng.” | Scanner không vào backend | Effective authZ + bypass review |
| “OpenAPI có mọi route.” | Legacy/internal/undocumented | Reconcile deployment routes |
| “401 chứng minh authorization.” | AuthN khác authZ | Resource/role/tenant tests |
| “403 có nghĩa không side effect.” | Job có thể đã tạo trước deny | DB/queue/file observation |
| “Có CSRF token là đủ.” | Có thể không enforce | Missing-token negative test |
| “Có CSP nên khỏi encode output.” | CSP không thay contextual encoding | Defense-in-depth |
| “HTTPS ở gateway đủ cho mọi hop.” | Internal calls có thể khác | Boundary-specific verification |
| “Không active probe thì không có test.” | Passive/targeted still useful | Risk-based profile |
| “Staging PASS tự là production PASS.” | Artifact/config có thể khác | Runtime/deployment binding |
| “Scan không thể gây thay đổi dữ liệu.” | Active tests hoặc GET sai design có thể side effects | Quota, stop, cleanup |
| “Report chứa token trong CI không sao.” | CI artifacts có thể rộng quyền | Redaction/access control |
| “False positive chỉ cần disable rule.” | Che lỗi thật về sau | Evidence-backed triage |
| “Exception nghĩa là fixed.” | Risk acceptance khác remediation | Tách trạng thái |
| “Scan lại không thấy alert là fixed.” | Test scenario cũ có thể chưa chạy | Retest same behavior |
| “Request count thay execution coverage.” | Persona/method/tenant không được tính | Explicit obligations |
| “Scanner timeout là no finding.” | Không có observation | NOT_RUN/INCONCLUSIVE |
| “Scanner version không quan trọng.” | Rule coverage thay đổi | Versioned evidence |
| “0 critical routes untested vì chưa inventory.” | Denominator incomplete | Inventory reconciliation |
| “Một lần quét là đủ cả năm.” | API/identity/deployment đổi | Continuous/event-driven assurance |

## 29. Checklist lập kế hoạch, thực hiện và báo cáo

### Trước khi scan

- [ ] Explicit owner/authorization và host/path/environment scope.
- [ ] Passive/active permissions, staging/production boundaries rõ.
- [ ] Excluded high-impact actions và third-party boundaries rõ.
- [ ] Traffic/concurrency/time budget và stop conditions được duyệt.
- [ ] Synthetic test data, roles/tenants, cleanup/rollback chuẩn bị.
- [ ] OpenAPI/gateway/controller/workflow routes được reconcile.
- [ ] Critical threat paths, assets và acceptance criteria rõ.
- [ ] Scanner version/rules/profile được kiểm soát.
- [ ] Monitoring/source-health, correlation và on-call runbook đầy đủ.
- [ ] Credentials và evidence storage không làm lộ secrets.

### Trong khi scan

- [ ] Session health xác minh đúng persona.
- [ ] Không tự theo redirects ngoài phạm vi.
- [ ] Discovered endpoints so với expected route inventory.
- [ ] Missing methods/roles/tenant test cases được ghi.
- [ ] Active tests không gọi destructive/third-party operations ngoài approval.
- [ ] Traffic/latency/backend health trong giới hạn.
- [ ] Không gửi email/tạo file/job ngoài fixture sandbox.
- [ ] Có response và side-effect evidence cho critical tests.
- [ ] Tool error/timeout/scan phase failure không bị che.
- [ ] Raw/sanitized results được bảo vệ phù hợp.

### Triage và retest

- [ ] Finding có requirement/risk/route/persona/deployment mapping.
- [ ] Confirmed/false positive/not affected/INCONCLUSIVE có evidence.
- [ ] Risk được đánh giá theo context, không chỉ scanner severity.
- [ ] Critical coverage gaps có owner, deadline và remediation.
- [ ] Exception có authority/scope/expiry và không thay technical state.
- [ ] Fix có change/commit/deploy references.
- [ ] Retest lặp scenarios trước đã fail và đúng fixtures.
- [ ] Backend side effects, runtime config và data exposure được xác minh.
- [ ] Không đóng finding chỉ vì tool không thấy alert.
- [ ] Report hygiene, access, retention, reviewer được kiểm.

### Trước khi tuyên bố assurance

- [ ] Scope, deployment, routes/methods, roles, tenants được ghi.
- [ ] Eligible/executed/pass/fail/auth-failed/not-run counts minh bạch.
- [ ] Denominator từ population đủ và đã reconcile.
- [ ] Session/tool/source health có evidence hoặc limitation.
- [ ] High-risk untested routes được nêu rõ.
- [ ] Exceptions không bị tính là technical PASS.
- [ ] Evidence đúng artifact/gateway policy/runtime version.
- [ ] Reviewer quyết định PASS/FAIL/INCONCLUSIVE theo acceptance.
- [ ] Có remediation/retest và reassessment triggers.
- [ ] Không diễn giải vượt phạm vi đã được xác minh.

## Ghi nhớ

- **Web security scan là kiểm thử động** một phần attack surface, không chứng minh ứng dụng an toàn tuyệt đối và không thay controls.
- Phải có **authorization, scope, traffic budget, excluded operations và stop conditions**; chỉ kiểm tài sản và môi trường được cho phép.
- **Passive, active, authenticated, API scan và manual business-logic tests** có coverage/risks khác nhau, cần phối hợp theo threat model.
- **Route/method/persona/tenant/resource/deployment** cần được đối chiếu actual inventory; request count không thay scenario coverage.
- Session expired, WAF block, legacy routes ngoài OpenAPI, SPA không crawl được có thể tạo **false negatives**; “0 finding” không bằng PASS.
- Authorization cần **positive/negative fixtures**, kiểm response fields và side effects, không chỉ mã HTTP.
- DAST bổ trợ nhưng không thay **SAST, SCA, configuration review, API contract tests và runtime assurance**.
- CI/CD phải gắn scan evidence với **tool/rule version, commit, artifact/deployment, identity, time, coverage, findings và reviewer**.
- Finding chỉ đóng khi **remediation đã được deploy và retest cùng scenario**; risk acceptance/exception quản trị riêng.
- Assurance claim phải **đúng scope, có evidence, nêu limitations và INCONCLUSIVE khi thiếu coverage**.
- Trong **SECURITY_SECURITY_ASSURANCE**, duy trì chuỗi **risk → requirement → control → scan/test → evidence → finding → remediation/retest → reassessment** trong phát triển và vận hành.

