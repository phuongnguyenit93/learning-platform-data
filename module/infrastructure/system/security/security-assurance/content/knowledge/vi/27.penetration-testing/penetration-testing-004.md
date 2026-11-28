# Gray-box Penetration Testing: kiểm thử xâm nhập với thông tin và quyền truy cập một phần

## 1. Gray box là gì?

**Gray-box penetration testing (kiểm thử xâm nhập hộp xám)** là cách đánh giá an ninh trong đó người kiểm thử được cung cấp **một phần thông tin nội bộ, quyền truy cập hoặc ngữ cảnh kiến trúc** của hệ thống, nhưng không nhất thiết có toàn bộ mã nguồn, toàn bộ cấu hình hoặc đặc quyền quản trị. Mục tiêu là kiểm chứng các đường tấn công thực tế trong một **phạm vi được ủy quyền** với mức hiểu biết gần với một số lớp tác nhân hợp lý, đồng thời tận dụng thông tin được chia sẻ để tăng độ sâu và hiệu quả kiểm thử.

Điểm đặc biệt của *gray box* không nằm ở một công cụ hoặc một “tỷ lệ phần trăm kiến thức” cố định. Nó nằm ở **mô hình thông tin và quyền hạn được cấp cho người kiểm thử**: có thể biết sơ đồ luồng dữ liệu và có tài khoản người dùng, nhưng không được xem mã nguồn; hoặc được xem một số API specifications và cách phân quyền, nhưng chỉ thực hiện các phép thử như một tenant thông thường.

Trong module **SECURITY_SECURITY_ASSURANCE**, người học không chỉ thực hành phát hiện lỗ hổng. Mục tiêu của bài là **đánh giá có bằng chứng** rằng hệ thống đáp ứng yêu cầu bảo mật: từ phân tích rủi ro, mô hình đe dọa, yêu cầu/control đến kiểm thử, audit, phát hiện, khắc phục và tái kiểm. Gray-box pentest trở thành một nguồn bằng chứng cho assurance khi các giả định, phạm vi, kết quả và giới hạn kiểm thử được ghi rõ.

### Ví dụ xuyên suốt

Một nền tảng học tập Java/Spring Boot có:

- `identity-api`: đăng nhập, quản lý phiên và xác thực token;
- `course-api`: khóa học, lớp học và danh sách thành viên;
- `submission-api`: bài nộp, tệp đính kèm và deadline;
- `grade-service`: điểm số và nhận xét;
- `notification-worker`: công việc nền, thông báo;
- PostgreSQL, object storage, Redis, message queue, API gateway và IdP.

Người kiểm thử được cung cấp tài khoản **Student A**, **Student B**, **Teacher X**, **Teacher Y**, một bản OpenAPI được lược bỏ dữ liệu nhạy cảm, sơ đồ data flow và mô tả các roles. Nhưng người kiểm thử **không có quyền cluster-admin, không đọc production database và không được giả lập tấn công gây gián đoạn**.

Đó là một ví dụ về gray-box engagement: tester hiểu đủ để tập trung vào các trust boundaries có rủi ro cao mà vẫn phải **chứng minh ứng dụng thực sự ngăn thao tác vượt quyền**.

> **Nguyên tắc:** Kiến thức được cung cấp là **đầu vào để thiết kế phép thử**, không phải bằng chứng rằng attacker ngoài đời có kiến thức ấy; quyền tài khoản kiểm thử là **ràng buộc về những hành động được phép**, không phải lời mời vượt ngoài Rules of Engagement (ROE).

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt gray-box với black-box và white-box theo **mức hiểu biết, phạm vi quyền và mục tiêu assurance**.
2. Xác định threat model, test identities, asset scope, Rules of Engagement và safe-test boundaries.
3. Lập kế hoạch kiểm thử authenticated APIs, **BOLA/IDOR, BFLA**, tenant isolation, session/authorization, business logic và các tích hợp.
4. Áp dụng thông tin kiến trúc, API specifications và một phần mã nguồn để chọn các phép thử có sức thuyết phục.
5. Ghi bằng chứng có khả năng lặp lại nhưng **không làm lộ PII, credentials hoặc dữ liệu của người khác**.
6. Phân biệt *observation*, *confirmed finding*, *risk assessment*, *not verified* và *control operating effectiveness*.
7. Tái kiểm sau remediation và liên kết phát hiện với source, artifact, deployment và acceptance criteria.
8. Thiết kế chương trình kiểm thử hộp xám liên tục phù hợp rủi ro của nền tảng học tập.

## 2. Vì sao cần gray-box pentest trong Security Assurance?

Hệ thống hiện đại có các đường truy cập đan xen: SPA → API gateway → microservices → queues → datastore. Một lỗ hổng nghiêm trọng có thể không thấy rõ từ giao diện bên ngoài, nhưng lại dễ kiểm chứng nếu biết endpoint cần kiểm và có identity thích hợp.

Gray-box giúp cân bằng:

- **Hiệu quả khám phá:** tester không phải đoán toàn bộ endpoint, workflow hoặc role model từ đầu.
- **Độ sâu:** tập trung vào data flows, trust boundaries, object ownership, token claims, file-handling và role transitions có rủi ro.
- **Tính thực tế:** vẫn kiểm tra từ góc nhìn một hoặc nhiều tác nhân giới hạn quyền, thay vì dùng quyền root/admin để đọc mọi thứ.
- **Khả năng truy vết:** ánh xạ security requirements/threat scenarios tới test case và evidence cụ thể.
- **Hợp tác phát hiện–khắc phục:** developer và tester dùng cùng ngữ cảnh để giải thích root cause, rủi ro và retest.

Nhưng gray-box cũng tạo nguy cơ **thiên lệch xác nhận (confirmation bias)**: người kiểm thử chỉ thử những endpoint đã được đưa trong spec, bỏ qua API “ẩn” hoặc misconfiguration nằm ngoài tài liệu. Do đó, gray-box nên kết hợp **discovery có kiểm soát** với **đánh giá các yêu cầu đã biết**, không đơn thuần “test đúng checklist chủ hệ thống cung cấp”.

## 3. So sánh black-box, gray-box và white-box

| Khía cạnh | Black-box | Gray-box | White-box |
| --- | --- | --- | --- |
| **Thông tin đầu vào** | Ít hoặc không có thông tin nội bộ ngoài scope. | Có phần sơ đồ, API specs, account test, role model hoặc selected code. | Có thể có source, kiến trúc, cấu hình và thông tin nội bộ toàn diện. |
| **Quyền kiểm thử** | Theo ROE; thường public/limited accounts. | Các roles/tenants và dữ liệu test được cấp rõ. | Có thể có quyền sâu hơn để review, không mặc định được khai thác mọi tài sản. |
| **Ưu điểm** | Quan sát bề mặt theo góc nhìn ít kiến thức. | Tập trung test logic và trust boundaries có liên quan. | Có thể kiểm code/config flow sâu và hiểu nguyên nhân. |
| **Giới hạn** | Có thể tốn thời gian discovery, bỏ sót protected flows. | Phụ thuộc chất lượng tài liệu/test data, dễ bỏ sót ngoài giả định. | Có thể bỏ qua chênh lệch môi trường thực và external attack surface. |
| **Phù hợp** | External exposure, kiểm defense khi thiếu ngữ cảnh. | Authenticated apps, business processes, multi-tenant APIs. | Code-level assurance, architecture review, secure design validation. |
| **Bằng chứng chính** | Observed behavior trong approved scope. | Observed behavior + context/identity/requirements. | Source/config evidence + behavioral validation khi có. |

**Không có loại nào “tốt nhất” trong mọi tình huống.** Một gray-box engagement không tự kém toàn diện hơn black-box hay ngược lại; chất lượng phụ thuộc threat model, goals, phạm vi, thời gian, phương pháp và khả năng kiểm chứng. Có thể kết hợp nhiều cách trong cùng assurance program nhưng phải công bố phần nào thực hiện theo cách nào.

### Tên gọi không quyết định quyền

“White-box” không có nghĩa được phép đọc dữ liệu thật của tất cả người học, và “gray-box” không có nghĩa được phép dùng kỹ thuật có khả năng gây hỏng production. **ROE và authorization là nguồn thẩm quyền**, không phải nhãn box.

## 4. Thông tin được cung cấp: đủ dùng, không mặc định toàn quyền

| Loại thông tin | Có thể cung cấp cho tester | Giá trị | Cần bảo vệ |
| --- | --- | --- | --- |
| **Architecture overview** | Sơ đồ API gateway, services, datastore. | Nhìn trust boundary và high-value flows. | Network/internal topology không phát tán. |
| **API specification** | OpenAPI/GraphQL schema theo scope. | Xác định operations, parameters và auth schemes. | Endpoints nhạy cảm/undocumented cần xử lý theo NDA. |
| **Role/tenant model** | Student, Teacher, Admin scoped, tenant relationships. | Thiết kế negative authorization tests. | Không cung cấp quyền thật không cần thiết. |
| **Test accounts** | Synthetic identities, MFA/test login, session constraints. | Kiểm role matrix và session lifecycle. | Secrets giữ trong vault, TTL, không hardcode report. |
| **Selected source/config** | Controller/filter hoặc snippets đã phê duyệt. | Xác minh assumption về authorization/data flow. | Không sao chép source/signer keys vượt scope. |
| **Data model sơ lược** | OwnerId, TenantId, ClassId, GradeId relationships. | Kiểm record ownership và data isolation. | Dùng dữ liệu giả, không chia sẻ PII. |
| **Threat model/requirements** | Data flows, abuse cases, ASVS requirements. | Tập trung tài nguyên vào risk trọng yếu. | Không biến assumptions thành kết quả test. |
| **Deployment boundary** | Staging/production scope, hostnames, IP/ports. | Tránh kiểm sai môi trường. | Không cho phép mở rộng tự ý. |
| **Observability** | Test environment logs được redact, correlation IDs. | Tìm root cause và chứng minh behavior. | Không lộ tokens, identifiers thật, secrets. |
| **Incident/exception context** | Known gaps, compensating controls. | Retest unresolved risks. | Tránh thiên lệch chỉ kiểm vấn đề đã biết. |

**Đánh dấu độ tin cậy của input**: một sơ đồ từ sáu tháng trước hoặc API spec chưa cập nhật có thể không đại diện runtime. Test plan nên có bước reconcile với deployed route inventory/config trong phạm vi được cấp.

## 5. Hai trục quan trọng: knowledge và privileges

Gray-box không tương đương “tester có một tài khoản đăng nhập”. Cần mô tả cả hai trục:

1. **Knowledge:** tester biết gì về architecture, source, data model, API operations, tenancy và security controls?
2. **Privileges:** tester **được phép** thao tác với roles, resources, networks, environments và kỹ thuật nào?

| Kịch bản | Knowledge | Privileges theo ROE | Mục tiêu |
| --- | --- | --- | --- |
| Student-level gray box | OpenAPI + tenancy model. | Student A/B test accounts. | Kiểm horizontal escalation/BOLA. |
| Teacher-level gray box | Class ownership and grade workflows. | Teacher X/Y thuộc tenants khác. | Kiểm class/tenant isolation và BFLA. |
| API integration gray box | OAuth/OIDC flows và service contracts. | Test API client scopes. | Kiểm token audience/scope, service-to-service authorization. |
| Selected-code gray box | Được đọc controller/filter thuộc scope. | Chỉ gọi endpoints staging. | Xác minh source assumption và behavior. |
| Admin-workflow gray box | Biết admin operations và change process. | Admin scoped test identity, không global superuser. | Kiểm privilege boundaries, audit và approval. |

**Attack scenario assumption** có thể mô tả “attacker chiếm được tài khoản Student A”, nhưng điều này không cho phép tester tự chiếm tài khoản thật. Tester sử dụng **synthetic account được cấp** như proxy cho giả định đó.

## 6. Phạm vi và Rules of Engagement (ROE)

Một gray-box pentest chỉ đáng tin và an toàn khi có **ROE được phê duyệt trước**. Đây vừa là cơ sở pháp lý/vận hành vừa là điều kiện làm bằng chứng kiểm thử có thể được kiểm toán.

### Các thành phần ROE

1. **Authority:** ai sở hữu tài sản và ai có quyền cho phép đánh giá?
2. **In-scope:** hostnames, IP ranges, API routes, environments, tenants, service accounts và test data.
3. **Out-of-scope:** assets/third parties, thật sự cấm truy cập hoặc kỹ thuật không được thử.
4. **Thời gian:** ngày/giờ, timezone, maintenance/blackout window, notification/on-call.
5. **Allowed methods:** passive observation, limited active testing, authenticated calls; các phép thử state-changing cần phép riêng.
6. **Load limits:** rate, concurrency, request budgets, stop conditions; cấm DoS/stress nếu không có authorization đặc thù.
7. **Account handling:** cách cấp, dùng, thay đổi, vô hiệu hóa và rotate test credentials.
8. **Data handling:** sử dụng synthetic data; redaction, retention, encryption, access, không exfiltrate dữ liệu thật.
9. **Escalation:** liên hệ IR/owner khi phát hiện critical vulnerability, data leak, instability hoặc unintended side effects.
10. **Cleanup:** xóa test artifacts/records theo scope, revoke credentials, restore state và xác minh không còn tác động.
11. **Reporting:** schema finding, deadline thông báo critical issue, evidence owners và dissemination restrictions.
12. **Third parties:** có được phép chạm tới IdP/SaaS/cloud-managed endpoints hay không; nếu không, ghi **không được kiểm**.

### Những điều không được mặc định

Tài khoản Teacher test **không** là quyền quét toàn bộ network của trường; việc biết một subdomain **không** tự cho phép truy cập nếu không thuộc scope. Một permission “read API” **không đồng nghĩa** được gửi payloads gây sửa/xóa dữ liệu, cố tình làm hỏng parser hoặc đo phá tải.

**Dừng kiểm thử** khi hệ thống có dấu hiệu gây ảnh hưởng ngoài ngưỡng: tăng lỗi đột ngột, chạm dữ liệu thật, token bị lộ, storage corruption hoặc vượt request budget. Bảo toàn evidence theo quy trình và báo owner/IR.

## 7. Phân biệt mô hình đe dọa và mô hình kiểm thử

### Threat model

Mô tả actor, tài sản, các điểm tin cậy, preconditions và impact. Ví dụ: “Một sinh viên đã đăng nhập có thể thử truy cập bản ghi điểm của một sinh viên khác thông qua object identifier”.

### Test model

Mô tả chính xác **test identity, dữ liệu giả, endpoint, expected deny và cách thu evidence**. Ví dụ: “Student A dùng token test hợp lệ gửi một yêu cầu GET tới Grade B do Student B sở hữu; server phải trả deny, không trả dữ liệu Grade B; test không thay đổi state”.

**Attacker capability và tester authorization là hai khái niệm khác nhau.** Threat model có thể bao gồm stolen staff credentials, malicious insider hoặc compromised SaaS, nhưng tester không thể tự thực hiện hành vi vượt ROE để chứng minh tất cả threat scenarios.

### Assumptions phải công khai

- Tester được cung cấp một phần knowledge mà attacker thực tế có thể không có.
- Tài khoản và datasets test có thể khác users/permissions thật.
- WAF/rate limits, observability hoặc feature flags ở staging có thể khác production.
- Manual testers có hạn chế thời gian và kỹ thuật; kết quả chưa tìm thấy lỗi không chứng minh absence of flaws.
- Một số internal services/data stores không được phép truy cập nên chỉ được đánh giá qua code/config/evidence hoặc **NOT VERIFIED**.

## 8. Asset inventory và attack surface trong gray-box

Inventory từ owner giúp tập trung nhưng **không thay discovery có kiểm soát**.

| Asset | Tín hiệu từ owner | Phép đối chiếu hợp lệ | Lỗ hổng có thể bị bỏ sót |
| --- | --- | --- | --- |
| API gateway | Route list, OIDC auth scheme. | So sánh runtime routes/test logs. | Undocumented/legacy operations. |
| Spring controllers | Endpoints, role annotations. | OpenAPI vs deployed behavior. | Object-level authorization ngoài annotations. |
| Worker/queue | Event types và principals. | Read event schemas, controlled synthetic events. | Consumer auth, event replay, idempotency. |
| PostgreSQL | Logical data model, tenant keys. | Authenticated API tests và limited test DB evidence nếu được phép. | Direct DB exposure và RLS misconfig nếu ngoài scope. |
| Object storage | Upload/presigned URL design. | Controlled upload/download với test objects. | URL leaks, tenant-level object references. |
| Identity provider | OAuth/OIDC flows và token claims. | Test token matrix, safe invalid token cases. | Provider-level issues ngoài quyền. |
| Kubernetes | Namespaces/service accounts. | Configuration read-only evidence theo ROE. | Cluster privilege escalation nếu không được test. |
| Third-party SaaS | Shared responsibility docs. | Integration behavior trong owned app. | Vendor vulnerabilities cần provider evidence riêng. |

### Gray-box enumeration: câu hỏi hơn là “quét bừa”

Ghi nhận route/service từ thông tin được cấp, đối chiếu API documentation và response của **synthetic clients** trong rate budget. Nếu thấy route chưa nằm trong inventory, báo owner để xác nhận scope trước khi kiểm sâu. Không suy từ khả năng truy cập URL public rằng endpoint đã được phê duyệt để scan.

## 9. Luồng dữ liệu và trust boundaries của nền tảng học tập

```mermaid
flowchart LR
  STU["Student A / Student B"] --> GW["API gateway"]
  TEA["Teacher X / Teacher Y"] --> GW
  GW --> AUTH["Identity / token verifier"]
  GW --> COURSE["Course API: membership"]
  GW --> SUB["Submission API"]
  GW --> GRD["Grade service"]
  SUB --> OBJ[("Object storage")]
  SUB --> Q[("Submission events")]
  Q --> WORK["Background grader"]
  GRD --> DB[("PostgreSQL: grades + tenant IDs")]
  COURSE --> DB
  WORK --> DB
  AUTH --> IDP["OIDC IdP"]
```

### Ranh giới cần xác minh

| Boundary | Câu hỏi gray-box |
| --- | --- |
| **Client → gateway** | Token có được validate issuer/audience/expiry và route policy không? |
| **Gateway → service** | Service có kiểm authorization riêng, hay tin mù quáng header do caller cung cấp? |
| **Student/Teacher → object** | Quyền trên từng grade/submission có gắn identity, tenant, class ownership? |
| **API → object storage** | Presigned URL có đúng owner, scope, TTL và content restrictions? |
| **API → queue → worker** | Event có integrity/authorization, tenant context và replay/idempotency guards? |
| **Service → DB** | Tenant filter, query parameterization, least privilege và RLS nếu áp dụng? |
| **Service → IdP** | JWKS rotation, token replay/session expiry và trust configuration hoạt động? |
| **Service → audit/monitoring** | Các thao tác denied/privileged có evidence mà không lộ PII? |

**Không chỉ test cổng vào.** Ví dụ gateway chặn một endpoint admin nhưng internal `grade-service` vẫn chấp nhận user-supplied `X-Role: ADMIN` sẽ tạo rủi ro nếu có đường bỏ gateway; nếu đường đó ngoài ROE, báo **control gap/NOT VERIFIED** thay vì tự truy cập trái quyền.

## 10. Security requirements làm cơ sở chọn test cases

Trong security assurance, mỗi phép thử phải có **security objective** thay vì chỉ “thử request lạ”. Mã yêu cầu dưới đây là **mẫu nội bộ**, không là điều khoản chính thức của OWASP/NIST.

| Requirement | Diễn đạt kiểm chứng được |
| --- | --- |
| **GB-REQ-01** | Mọi hoạt động trong pentest có authorization/scope và stop conditions rõ. |
| **GB-REQ-02** | Mỗi role/tenant chỉ truy cập tài nguyên của mình hoặc tài nguyên được cấp quyền. |
| **GB-REQ-03** | Protected operation không chấp nhận missing/invalid/expired token. |
| **GB-REQ-04** | Backend thực thi object-level và function-level authorization, không dựa UI. |
| **GB-REQ-05** | Service-to-service boundaries chỉ chấp nhận trusted identities/scopes theo thiết kế. |
| **GB-REQ-06** | File upload/download có ownership, scope, size/type và safe processing policies. |
| **GB-REQ-07** | Sensitive records không lộ qua errors, responses, logs hoặc caching sai scope. |
| **GB-REQ-08** | Critical state-changing actions có permission check, integrity và audit. |
| **GB-REQ-09** | Session/token lifecycle và credential hygiene đáp ứng policy. |
| **GB-REQ-10** | Inputs đi vào SQL/templating/path/serialized contexts được xử lý an toàn. |
| **GB-REQ-11** | Các test không làm ảnh hưởng availability/data integrity ngoài safety budget. |
| **GB-REQ-12** | Findings có evidence, risk context, owner, treatment và retest. |
| **GB-REQ-13** | Khác biệt staging/production và các mục ngoài scope được nêu minh bạch. |
| **GB-REQ-14** | Control conclusions phân biệt PASS, FAIL, NOT VERIFIED, EXCEPTION và N/A. |
| **GB-REQ-15** | Production remediation chỉ được đóng sau khi đúng artifact/deployment được verified. |
| **GB-REQ-16** | Kết quả pentest được tích hợp vào continuous security assurance có risk-based triggers. |

### Requirements vs findings

Không tìm ra lỗi trong một buổi kiểm thử không tự chứng minh `GB-REQ-02` đạt trên mọi service. Phải xác định **test case coverage**, được chạy bằng role nào, với object của ai, expected/actual và giới hạn. Với phép thử không được phép thực hiện, trạng thái phù hợp thường là **NOT VERIFIED** hoặc có evidence thay thế được phê duyệt, không đánh dấu PASS vô điều kiện.

## 11. Khởi tạo test accounts, tenants và fixtures

### Bảng danh tính mẫu

| Identity | Tenant | Vai trò | Quyền hợp lệ |
| --- | --- | --- | --- |
| **Student A** | School X | Student | Xem/nộp bài của bản thân theo lớp đã đăng ký. |
| **Student B** | School X | Student | Bài nộp và điểm của B; không đọc data riêng của A. |
| **Student C** | School Y | Student | Data thuộc School Y; không chạm School X. |
| **Teacher X** | School X | Teacher | Đọc/chấm bài của lớp do X phụ trách. |
| **Teacher Y** | School Y | Teacher | Đọc/chấm bài lớp School Y. |
| **Tenant Admin X** | School X | Admin scoped | Quản trị School X, không vượt tenant. |
| **API Client Read** | School X | Machine scope | Chỉ đọc APIs trong scope được cấp. |
| **Unauthenticated** | Không có | None | Chỉ public resources và login flow. |

### Fixtures cần có

- Hai bài nộp giống cấu trúc nhưng khác **owner**, hai classes khác nhau, hai tenants khác nhau.
- Records thuộc user test và records không thuộc user test, ID có dạng giống nhau để tránh chỉ dựa vào đoán chuỗi.
- Các trạng thái workflow: nháp, đã nộp, hết hạn, đã chấm, đã công bố điểm.
- Test files không chứa malware thật hoặc dữ liệu nhạy cảm, có checksums và cleanup plan.
- Session/token fixtures với issuer/audience/role/scope/expiry hợp lệ và không hợp lệ do test IdP hỗ trợ.

### Integrity và data privacy

Không dùng tên, điểm, email hoặc submissions thật khi không cần. Tài khoản kiểm thử nên có **TTL**, điều kiện được cấp, MFA nếu áp dụng và revocation cuối engagement. Không cho một identity vô tình biết dữ liệu cần “đoán” khi test yêu cầu quan sát từ góc nhìn khác.

## 12. Phương pháp gray-box: từ risk đến evidence

Một chu trình đủ sâu có thể thực hiện theo **mười bước**:

1. **Kickoff/ROE:** chốt quyền, targets, hazards, test actors và contacts.
2. **Review knowledge pack:** sơ đồ architecture, APIs, role matrix, selected code và documentation freshness.
3. **Map trust boundaries:** vẽ actors/data flows, xác định target resources và security controls.
4. **Prioritize:** theo dữ liệu nhạy cảm, privilege, exposure, threat scenarios và blast radius.
5. **Prepare fixtures:** synthetic users, tenants, objects, sessions và known-good behavior.
6. **Execute tests safely:** positive + negative tests, giới hạn requests, tránh state corruption.
7. **Validate findings:** xác minh expected vs actual, root cause đủ thuyết phục, loại false positives.
8. **Assess impact:** attacker prerequisites, affected assets, privilege, data/availability impact.
9. **Report & remediation:** owner, severity/risk, reproducer an toàn, fix/mitigation, evidence.
10. **Retest & closure:** xác minh lại trên target release/config và chuyển risk vào continuous monitoring.

### Hai lượt kiểm có giá trị

- **Lượt A – context-driven:** dùng sơ đồ và role matrix để kiểm những boundaries đã biết, đặc biệt negative authorization.
- **Lượt B – assumption-challenge:** so tài liệu với behavior/route inventory và tìm những flow hợp lệ nhưng chưa được mô tả, trong ROE.

Nếu chỉ làm lượt A, engagement dễ tái xác nhận chính assumptions sai của tài liệu.

## 13. Kiểm thử xác thực và phiên (authentication/session)

### Nhóm điều kiện cần kiểm

| Điều kiện | Phép thử an toàn | Expected behavior |
| --- | --- | --- |
| Missing credentials | Gọi protected API không token. | Từ chối, không trả dữ liệu bí mật. |
| Expired token | Token hết hạn do test IdP cấp. | Từ chối và không tiếp tục dùng quyền cũ. |
| Wrong issuer/audience | Fixture token có claims không thuộc policy. | Verifier reject theo cấu hình. |
| Insufficient scope | Read-only client gọi write operation. | Từ chối ở server; không state change. |
| Session logout/revoke | Logout test user rồi dùng lại session. | Không được chấp nhận nếu session revocation policy yêu cầu. |
| MFA workflow | Dùng test persona và phương thức MFA trong ROE. | Protected privileged action tuân thủ step-up/MFA policy. |
| Session fixation/cookie scope | Quan sát session/cookie behavior. | Session identifiers/cookie flags theo yêu cầu. |
| Account state | Test user bị disabled/locked. | Không cấp quyền truy cập trái policy. |

**Không khai thác tài khoản người thật** bằng password spraying, brute force, reset-email abuse hoặc credential stuffing nếu không có phạm vi/authorization đặc thù. Có thể dùng test IdP, synthetic accounts và negative cases được chuẩn bị để đánh giá controls.

### Test identity vs authenticated context

Một token có claim `tenant_id=School X` không tự chứng minh backend sẽ ràng buộc mọi data access theo School X. Phải kiểm **authorization ở resource boundary**, không chỉ token validation.

## 14. BOLA/IDOR: tài nguyên đúng nhưng chủ sở hữu sai

**Broken Object Level Authorization (BOLA)** là trường hợp service cho phép actor thao tác trên object mà actor **không có quyền đối với object ấy**, bất kể actor đã đăng nhập. **Insecure Direct Object Reference (IDOR)** mô tả một mẫu biểu hiện thường gặp: identifier của object được dùng làm điểm truy cập nhưng thiếu kiểm soát quyền phù hợp. Không phải mọi BOLA đều chỉ do identifier dễ đoán.

### Quy trình test theo hai tài khoản giả

1. Tạo `Submission A` thuộc Student A và `Submission B` thuộc Student B.
2. Đăng nhập bằng Student A, xác minh Student A xem được `Submission A` theo policy (**positive control**).
3. Dùng **chính token của Student A** yêu cầu `Submission B`, không dùng token của B.
4. Kỳ vọng deny theo API contract (thường 403 hoặc 404 để không tiết lộ sự tồn tại), **không trả nội dung/metadata trái quyền**.
5. Kiểm không có thay đổi trạng thái, thông tin audit không lộ nội dung, cache không trả response của B.
6. Lặp lại bằng Teacher X đối với bài thuộc lớp chưa được phân công và tài nguyên của Tenant Y.
7. Thu response đã redact, test data mapping, log correlation ID, target build và policy.

### Ví dụ HTTP minh họa

```http
GET /api/submissions/submission-b-test HTTP/1.1
Host: staging.example.invalid
Authorization: Bearer TEST_STUDENT_A_TOKEN
Accept: application/json
```

**Tài khoản và endpoint là dữ liệu giả trên môi trường kiểm thử đã cho phép.** Token chỉ là placeholder, không dùng token thật trong tài liệu, chat hoặc issue. Dấu hiệu lỗi là response **chứa dữ liệu riêng của B** hoặc cho phép state change trái quyền; chỉ nhìn HTTP 200 mà không kiểm payload/context có thể kết luận sai.

### Vì sao đổi UUID không phải fix?

Đổi ID tuần tự thành UUID khó đoán có thể giảm khả năng khám phá nhưng không thay **server-side authorization**. Nếu người dùng lấy được UUID qua logs, links, cache hoặc share, backend vẫn phải kiểm tenant, owner, class membership và action permission.

## 15. BFLA: chức năng có quyền cao bị gọi bởi actor thấp quyền

**Broken Function Level Authorization (BFLA)** xảy ra khi actor có thể thực hiện một chức năng **không thuộc quyền của role/scope**, như Student gọi API quản trị lớp hoặc Teacher thường gọi thao tác đổi global grading policy.

| Actor | Request trong lab | Expected |
| --- | --- | --- |
| Student A | Thử cập nhật grade của mình sau khi đã công bố. | Reject nếu chỉ Teacher được sửa. |
| Teacher X | Thử tạo tenant administrator. | Reject, không làm thay đổi roles. |
| Tenant Admin X | Thử cập nhật cấu hình global toàn nền tảng. | Reject ngoài tenant scope. |
| Machine client read-only | Thử gọi write endpoint. | Reject nếu thiếu scope. |
| Unauthenticated | Thử protected admin route. | Reject trước state change. |

**Ẩn nút “Edit” trên UI không phải authorization.** Phép thử hộp xám gọi API qua test client được phép để xác minh enforcement thực sự ở server.

### Kiểm cả workflow conditions

Một Teacher có thể được sửa điểm **trước** ngày chốt nhưng **không sau** khi công bố, trừ khi có approval bổ sung. BFLA theo business state cần kiểm quyền kết hợp **actor, action, object và trạng thái**, chứ không chỉ role name.

## 16. Tenant isolation và object ownership matrix

Nền tảng multi-tenant đặc biệt phù hợp với gray-box vì tester được chia sẻ dữ liệu giả và quan hệ tenant để thiết kế **các cặp cho phép/từ chối** chính xác.

| Test actor | Resource | Condition | Expected |
| --- | --- | --- | --- |
| Student A – X | Submission của A – X | Owner, lớp đăng ký. | ALLOW theo policy. |
| Student A – X | Submission của B – X | Khác owner, cùng tenant. | DENY. |
| Student A – X | Submission của C – Y | Khác tenant. | DENY. |
| Teacher X – X | Grade trong lớp X phụ trách | Assigned teacher, valid state. | ALLOW theo policy. |
| Teacher X – X | Grade lớp X không phụ trách | Same tenant, wrong class. | DENY. |
| Teacher X – X | Grade Tenant Y | Cross-tenant. | DENY. |
| Tenant Admin X | Cấu hình School X | Tenant scope. | ALLOW theo policy. |
| Tenant Admin X | Cấu hình School Y | Cross-tenant. | DENY. |
| Service Account read-only | POST grade update | Wrong OAuth scope. | DENY. |

### Một số bypass routes cần có trong test plan

- URL parameter / path identifier.
- JSON body và nested object IDs.
- Query filters, pagination, sorting và search results.
- GraphQL fields/resolvers nếu có.
- Batch operations: một phần IDs thuộc actor, một phần ngoài quyền.
- Export/download endpoints và presigned object links.
- Cache keys, ETag và shared response caching.
- Async job IDs và status endpoints.

**Không tự viết code brute-force/enumeration** để tìm IDs thật. Tài khoản fixtures phải được chuẩn bị trước; chỉ gửi một số request tối thiểu đủ xác minh điều kiện, không chạm dữ liệu người dùng khác.

## 17. Spring Security: phương pháp xác minh ở controller và service

Gray-box tester đôi khi được xem **selected code** để hiểu liệu application chỉ kiểm role tại controller hay có cả **resource-level authorization**.

### Một mẫu code chưa đủ

```java
// Illustrative: role check alone is not object-level authorization.
@PreAuthorize("hasRole('TEACHER')")
@GetMapping("/grades/{gradeId}")
public GradeDto getGrade(@PathVariable UUID gradeId) {
    return gradeService.findById(gradeId);
}
```

Rule trên có thể chỉ chứng minh user có role TEACHER, **không xác định giáo viên có phụ trách lớp của grade đó hoặc grade có thuộc tenant của token không**. Không nhất thiết ứng dụng vulnerable nếu `gradeService.findById` thực hiện đủ authorization; phải kiểm **toàn bộ call path/behavior**, không kết luận chỉ từ annotation.

### Một hướng thiết kế được kiểm chứng bằng negative tests

```java
// Illustrative service-level authorization, not a complete Spring app.
public GradeDto readGrade(UUID gradeId, CurrentActor actor) {
    Grade grade = gradeRepository.findById(gradeId)
        .orElseThrow(() -> new NotFoundException("grade not available"));

    // Actor tenant identity comes from a verified authentication context,
    // never a caller-controlled X-Tenant-Id header alone.
    if (!grade.getTenantId().equals(actor.tenantId())) {
        throw new NotFoundException("grade not available");
    }
    if (!authorization.canReadGrade(actor, grade)) {
        throw new AccessDeniedException("not allowed");
    }
    return mapper.toDto(grade);
}
```

Ở production cần thiết kế **query filtering/row-level security, least-privilege DB permissions, tenant scoping, caching và concurrency** phù hợp. Một check ở Java nhưng repository query cho phép trả nhiều dữ liệu trước khi lọc có thể gây leakage hoặc performance issues.

### Ví dụ test MockMvc có kiểm soát

```java
// Illustrative JUnit / Spring Security test excerpt.
// Requires spring-security-test, a configured test application and fixtures.
@Test
void studentCannotReadAnotherStudentsGrade() throws Exception {
    mockMvc.perform(get("/api/grades/{gradeId}", "grade-b-test")
            .with(jwt().jwt(jwt -> jwt
                .subject("student-a")
                .claim("tenant_id", "school-x"))
                .authorities(new SimpleGrantedAuthority("SCOPE_grades.read"))))
        .andExpect(status().isForbidden());
}
```

Một số API có thể trả **404** thay 403 để tránh tiết lộ existence; assertion phải theo approved contract. `jwt()` là **mock authentication context** cho integration layer, **không chứng minh** real JWT signature/issuer/audience validation; phải có test riêng với real IdP/verifier trong phạm vi cho phép. Các fixtures/beans/imports đã được rút gọn; đoạn trên không phải ứng dụng độc lập sẵn chạy.

### Hai lớp kết luận

1. **Source observation:** control được triển khai ở service level hoặc DB/query boundary.
2. **Behavioral evidence:** Student A với identity xác định thật sự bị deny khi truy vấn Grade B ở test runtime.

Gray box có thể cung cấp cả hai, nhưng không nên thay kết quả một phép thử bằng suy diễn từ source.

## 18. Session, OAuth/OIDC và delegated authorization

Test identities thường có access tokens từ IdP; cần phân biệt **authentication, delegated scopes và business authorization**.

### Những trường hợp phù hợp

| Điều kiện | Cách kiểm trong lab | Kết quả mong đợi |
| --- | --- | --- |
| Token hết hạn | Test token có expiry đã qua. | Reject theo verifier policy. |
| Issuer không tin cậy | Fixture token từ test issuer không có trong allowlist. | Reject; không dùng unchecked claims. |
| Audience không hợp lệ | Token dành cho service A gọi service B. | Service B reject. |
| Scope không đủ | Token chỉ read gọi update. | Reject. |
| User đã bị disabled | Identity được vô hiệu hóa theo test setup. | Session/token lifecycle đáp ứng revocation policy. |
| Tenant claim sai context | Token của X tham chiếu object Y. | Resource-level deny. |
| Key rotation | Test IdP đổi signing key trong window có kế hoạch. | Validator cập nhật trust an toàn, không fail-open. |
| Refresh token reuse | Chỉ trong lab với test token và flow cho phép. | Rotate/revoke/replay controls theo chính sách. |

### Cần tránh kết luận từ một client

Một browser flow có thể bảo vệ CSRF/session khác API dùng Bearer token. Một số roles kiểm ở gateway, số khác kiểm ở service. Tester phải ghi rõ **auth mechanism, client type, token audience và trust assumptions** cho từng test.

## 19. Business logic testing: thời hạn, trạng thái và workflow

Gray-box đặc biệt hữu ích với *business logic flaws* vì có thể cung cấp **workflow diagram và dữ liệu giả** để xác minh bất biến.

### Các bất biến điển hình của LMS

- Student không được nộp bài sau deadline, trừ khi có exception được cấp có kiểm soát.
- Một submission chỉ thuộc đúng owner/course/assignment.
- Teacher chỉ chấm trong lớp được phân công.
- Điểm đã công bố chỉ đổi theo quy trình được ủy quyền, có audit.
- Mỗi submission receipt tương ứng một committed state.
- Các request lặp lại không tạo multiple submissions/grade updates trái quy định.
- Export lớp học không chứa dữ liệu khác tenant.
- Một học viên chuyển lớp không tiếp tục thấy private resources đã bị thu hồi.

### Test design theo state machine

| Trạng thái trước | Actor/action | Expected |
| --- | --- | --- |
| Draft, trước hạn | Owner submits. | Một bản nộp hợp lệ, có receipt. |
| Draft, sau hạn | Owner submits (no extension). | Deny/late policy đúng. |
| Submitted | Owner requests repeated submit. | Idempotency/versioning đúng policy. |
| Graded | Teacher assigned edits score. | Allow nếu state còn mở sửa. |
| Published/locked | Teacher thường edits score. | Deny hoặc require approved override. |
| Course transferred | Former teacher reads private grade. | Deny sau khi rights được cập nhật. |

### An toàn thực nghiệm

Chỉ tạo/chỉnh sửa **synthetic records** trong staging hoặc scope được phê duyệt. Nếu cần test concurrency/race, dùng một số lượng request giới hạn với rollback/cleanup, tránh tạo tải lớn hoặc thay đổi điểm thật. Phép thử gây side effect phải có **pre/post state snapshot**.

## 20. Upload, object storage và signed URL trong gray-box

Một file-upload flow có thể đi từ frontend → API → object storage → worker → DB. Tester có sơ đồ kiến trúc nên có thể kiểm **mối liên hệ giữa ID, owner, pre-signed permission và lifecycle**, không chỉ upload file.

| Threat | Test an toàn với dữ liệu giả | Bằng chứng |
| --- | --- | --- |
| Wrong-owner download | Student A yêu cầu object của Student B. | Denied response, không có file bytes B. |
| Cross-tenant presigned URL | Token của Tenant X xin URL cho object Y. | Policy reject hoặc URL không được cấp. |
| URL TTL | Test URL hết hạn trong window được phép. | Access denied sau expiry. |
| Unexpected content type | Upload harmless fixture sai type. | Rejection/validation theo policy. |
| Size/processing limit | File nhỏ tại boundary được phê duyệt. | Safe limit enforcement, không gây DoS. |
| Worker authorization | Synthetic event chứa object khác owner. | Worker không xử lý/trả data trái policy. |
| Error/log leakage | Test lỗi xử lý file. | No secret/PII exposure trong response/logs. |

**Không dùng file chứa mã độc thật, payload phá parser hoặc dữ liệu sản xuất** để đạt được bằng chứng. Với đánh giá anti-malware/parser vulnerabilities rủi ro cao, cần lab/authorization chuyên biệt và có thể dùng synthetic benign fixtures hoặc code/config review bổ sung.

## 21. Injection, unsafe deserialization và input validation

Kiến thức về framework/architecture giúp tester tập trung vào những nơi untrusted input đi vào **SQL, templating, file paths hoặc serializers**. Tuy nhiên việc quan sát một request gây lỗi không tự chứng minh vulnerability.

### Các phương pháp an toàn

1. Xác định **source–transformation–sink** từ selected code/spec, trong phạm vi tester được xem.
2. Chọn harmless input cases và expected behavior theo contract.
3. So sánh với behavior khi dùng parameterized queries/allowlisted operation.
4. Dùng logging redacted và correlation IDs để developer xác minh root cause.
5. Nếu nghi có impact lớn, **dừng ở bằng chứng tối thiểu**; không đọc bảng dữ liệu ngoài scope hoặc chạy destructive payload.

### Java example: query parameterization

```java
// Anti-pattern: avoid concatenating untrusted values into SQL.
String unsafe = "SELECT id FROM submissions WHERE owner_id = '" + userInput + "'";

// Safer query shape, with authorization checked separately:
String sql = """
    SELECT id FROM submissions
    WHERE owner_id = ? AND tenant_id = ?
    """;
return jdbcTemplate.queryForList(sql, verifiedActorId, verifiedTenantId);
```

Parameter binding giúp giảm SQL injection, nhưng không tự chứng minh **verifiedActorId** hay **verifiedTenantId** được lấy từ auth context đáng tin hoặc quyền trên object đã đúng. Một gray-box engagement cần liên kết **source review** và **negative authorization behavior**.

### Đánh giá loại lỗi khác

- **XSS/template injection:** kiểm encoding/context handling bằng harmless markers trong lab, không ép browser thực thi hành vi độc hại.
- **Path traversal:** kiểm safe filename handling/normalization trong fixture directory, không truy xuất file thật ngoài scope.
- **Unsafe deserialization:** xem parser configuration/allowlist và expected behavior, tránh input có khả năng thực thi mã.
- **SSRF:** nếu in scope, kiểm validation và egress policy bằng **mock endpoint do tổ chức sở hữu**, không probe internal metadata/admin services.
- **Command injection:** ưu tiên code review/safe arguments và controlled unit tests, không thực hiện shell payload trên production.

**Finding phải phản ánh evidence:** “đã quan sát xử lý input sai” khác “đã chứng minh attacker đọc DB hoặc chạy lệnh”. Không nâng tác động tưởng tượng thành kết quả kiểm thử thực tế.

## 22. Service-to-service trust và asynchronous workflows

Một API không chỉ phục vụ con người. Jobs, message consumers và service accounts có thể giữ đặc quyền rộng hơn test user; tester có thể được cấp **service contract và synthetic event schema** thay vì production credentials.

### Các câu hỏi hộp xám

- Service A có gửi identity/tenant context theo một **trusted channel**, hay chỉ truyền header bất kỳ?
- Service B xác minh caller identity, audience và permissions của endpoint nội bộ không?
- Async consumer có kiểm event issuer/authorization, object ownership và schema?
- Có idempotency/dedup key ngăn repeated events thay đổi điểm nhiều lần?
- Một event do actor X tạo có bị xử lý dưới **quyền global worker** mà thiếu object check không?
- Retry/dead-letter handling có làm rò PII hoặc bypass deadline policy?
- Service account có cần quyền cluster/cloud rộng như đã được cấp không?

### Vấn đề deputy

Một service có quyền cao có thể vô tình trở thành **confused deputy** nếu nhận identifier do user cung cấp và làm thay user mà không kiểm quyền. Test nên thiết kế **actor–resource–action tuples** và quan sát kết quả đối với fixtures, không dùng token admin thật để “giả vờ” thành attacker.

## 23. Cấu hình, cloud/IAM và khác biệt giữa môi trường

Gray-box tester có thể nhận **read-only config evidence** về IAM, API gateway, Kubernetes manifests, network policies hoặc CI. Điều đó giúp đánh giá risks chưa quan sát được chỉ bằng HTTP.

| Lớp | Một số control cần xác minh | Phương pháp phù hợp |
| --- | --- | --- |
| API gateway | Routing, authentication, request size/rate. | Config review và permitted behavior checks. |
| Spring Security | Filter chains, request matchers, role policies. | Selected code review + negative tests. |
| Kubernetes | Runtime identity, namespace/RBAC, network policy. | Read-only inventory/review trong ROE. |
| Cloud IAM | Workload role, object storage access, trust relationships. | Effective policy review/test fixtures khi được phép. |
| CI/CD | Trusted build/deploy identity, secret exposure. | Workflow evidence và authorization checks. |
| Database | Tenant scoping, RLS/least privilege. | Approved config evidence hoặc synthetic API tests. |
| Monitoring | Audit events, PII redaction. | Read-only log review theo case IDs. |

**Không truy cập secret stores, cloud metadata endpoints hoặc admin APIs chỉ vì có đường mạng.** Nếu ROE không cho kiểm, mô tả limitation và đề xuất chuyên đề kiểm tra riêng.

### Staging–production equivalence

Với mỗi finding/control, ghi các yếu tố có thể khác:

- Build artifact/source revision, feature flags và cấu hình authorization.
- IdP/OIDC issuer/audience, MFA và token TTL.
- Gateway/WAF, API routing, rate limits và TLS termination.
- Database schema/constraints, RLS và seed data.
- Cloud IAM/Kubernetes policies, privileged sidecars và storage ACLs.
- Logging/sensor coverage và version của external dependencies.

Kết luận PASS trên staging **không tự thành PASS production**. Có thể sử dụng configuration comparison và release/runtime lineage như *evidence bổ trợ* nếu active testing trên production không được phép.

## 24. Gray-box khác credentialed vulnerability scan và code review

Một **authenticated vulnerability scan** dùng credentials để scanner khám phá protected routes và dấu hiệu điểm yếu. **Gray-box pentest** có thể bao gồm authenticated scanning, nhưng còn dùng **context, giả thuyết, test design và manual validation** để đánh giá logic, workflow và trust boundaries.

| Hoạt động | Điểm mạnh | Giới hạn |
| --- | --- | --- |
| **Authenticated DAST** | Tìm web/API issues lặp lại ở protected routes. | Không tự bao phủ object ownership và business states. |
| **SAST/Code review** | Thấy source/sink, design/security control implementation. | Source không tự chứng minh runtime config/behavior. |
| **SCA** | Known vulnerable third-party dependencies. | Chưa biết exploitability hay malicious behavior ngoài CVE. |
| **Config assessment** | Detect IAM, network, deployment mismatches. | Cấu hình đúng không đủ chứng minh logic đúng. |
| **Gray-box pentest** | Test targeted attacker actions với partial knowledge. | Time-bound/authorized scope, không tự bao phủ mọi code/path. |

Một engagement tốt **kết hợp** các nguồn, không gắn nhãn “pentest complete” chỉ vì một automated scan chạy xong.

## 25. Evidence hygiene: đủ chứng minh nhưng không gây hại

Mục đích bằng chứng là cho phép **người có thẩm quyền tái kiểm** vấn đề trong scope mà không phơi dữ liệu bí mật hoặc duy trì quyền truy cập trái phép.

### Finding evidence tối thiểu

| Trường | Ý nghĩa |
| --- | --- |
| **Engagement/test ID** | Liên kết ROE, owner và mục tiêu kiểm. |
| **Target build/environment** | Host/service, version/image digest, staging/prod và thời điểm. |
| **Test identity** | Role/tenant/scope của synthetic account, **không chứa raw token**. |
| **Preconditions** | Test fixture owner, class/tenant mapping, initial state. |
| **Request/operation** | Endpoint/method hoặc hành động theo cách có thể tái lập, đã redacted. |
| **Expected behavior** | Security requirement và điều kiện ALLOW/DENY. |
| **Observed behavior** | Status, response shape, state change, audit event; giữ bằng chứng tối thiểu. |
| **Root cause/assumption** | Giả thuyết và mức độ chắc chắn, code/config evidence nếu có. |
| **Risk context** | Attacker prerequisites, privilege, affected data, blast radius. |
| **Attachments** | Screenshots/log references được kiểm PII/secrets, checksum/integrity khi cần. |
| **Limitations** | Không test production, không có admin role hoặc route ngoài scope. |

### Nếu vô tình nhận dữ liệu thật

Dừng việc truy xuất thêm, không sao chép/sàng lọc hàng loạt để tìm thông tin nhạy cảm; thông báo đúng incident contact, **giảm quyền truy cập evidence**, bảo toàn metadata cần thiết theo quy trình và xóa/retention dữ liệu theo chỉ dẫn có thẩm quyền.

### Proof of concept (PoC) cần giới hạn

Một PoC nên chứng minh **security invariant bị vi phạm** bằng dữ liệu giả và thao tác tối thiểu. Không cần lấy toàn bộ bảng điểm hoặc chiếm tài khoản thật để xác nhận BOLA khi một test object do engagement tạo đã đủ.

## 26. Risk assessment: phân biệt độ nghiêm trọng công cụ và rủi ro thực

Một finding đáng xử lý cần có **impact và likelihood context**, không chỉ một nhãn Critical/High.

### Các yếu tố

1. **Actor capability:** unauthenticated, ordinary student, assigned teacher, tenant admin, compromised service identity.
2. **Preconditions:** cần biết object ID, có membership, session hợp lệ, feature enabled?
3. **Exposure:** public API, internal-only API, egress restrictions, reachable path.
4. **Impact:** Confidentiality/Integrity/Availability, privacy, điểm số và audit integrity.
5. **Scope:** một record, cả lớp, nhiều tenants hay toàn hệ thống?
6. **Ease/repeatability:** request đơn lẻ hay chain phức tạp, rate-limits, compensating controls.
7. **Detectability/response:** audit logs có nhận diện và chặn abuse không?
8. **Evidence certainty:** đã test behavior hay chỉ nghi ngờ từ code/config?

| Tình huống | Observation | Triage cần xem |
| --- | --- | --- |
| Student A đọc được grade của Student B. | Confirmed BOLA trên fixture. | Exposure, data sensitivity, tenant scope, detectability. |
| Student A đoán được UUID của record khác nhưng API deny. | No unauthorized data observed. | Phần còn lại của object/endpoint matrix; không báo BOLA chỉ vì ID đoán được. |
| Token wrong audience bị gateway reject. | Một negative auth test PASS. | Internal service bypass path có được test/config review không? |
| SAST phát hiện unsafe function, chưa có runtime path. | Source risk candidate. | Reachability, input control, method/config, retest. |
| DAST báo HTTP 500 với harmless input. | Error condition observed. | Có data leak/denial/security impact không; không nâng thành RCE không chứng cứ. |

**CVSS** có thể là đầu vào severity cho vulnerability phù hợp, nhưng không thay context, scope và business risk assessment. Nếu dữ liệu chưa đủ để xác định exploitability, ghi **uncertain/NOT VERIFIED** theo chính sách chứ không giả định nghiêm trọng nhất hoặc vô hại.

## 27. Kết luận PASS, FAIL, NOT VERIFIED, N/A và exception

| Trạng thái | Điều kiện | Ví dụ |
| --- | --- | --- |
| **PASS** | Có evidence control đáp ứng expected result trong đúng scope/conditions. | Student A bị deny khi truy cập Grade B trong test environment với đúng token/fixture. |
| **FAIL** | Có evidence security requirement bị vi phạm. | Teacher X đọc được grade của lớp/tenant không được phân công. |
| **NOT VERIFIED** | Chưa kiểm được hoặc thiếu evidence đủ tin cậy. | Một internal route không trong ROE, chưa có config/test evidence. |
| **N/A** | Requirement không áp dụng theo kiến trúc/phạm vi, reviewer ghi căn cứ. | No GraphQL interface đã được xác minh trong scope. |
| **EXCEPTION** | Control áp dụng nhưng gap/risk được chấp thuận tạm thời đúng thẩm quyền và policy. | Legacy interface chưa thể sửa ngay, có isolation đã test, owner và expiry. |

### Giới hạn của “PASS”

Một testcase PASS **không** chứng minh toàn bộ control đạt trên mọi role, object state và environment. Muốn đánh giá operational effectiveness cần coverage assessment, test case sampling, review risk và evidence về implementation/runtime.

### Accepted risk không phải fixed

Nếu một BOLA được xác nhận nhưng business owner chấp nhận tạm thời vì migration, kết luận kỹ thuật **vẫn là vulnerability tồn tại**, với risk decision và compensating controls được tracking riêng; không đổi finding thành “No issue”.

## 28. Threat–requirement–test–evidence traceability

Với security assurance, giá trị của gray-box pentest là **khả năng trả lời có bằng chứng những giả thuyết rủi ro**. Một danh sách 100 endpoint đã gọi không đủ cho câu hỏi “hệ thống có cô lập dữ liệu giữa tenants không?”.

| Threat ID | Threat scenario | Requirement | Test/evidence | Giới hạn |
| --- | --- | --- | --- | --- |
| **GB-THR-01** | Student đọc submission của Student khác. | GB-REQ-02/04 | Test A vs B, response shape, ownership fixture, audit. | Một endpoint/state chưa bao phủ batch/export. |
| **GB-THR-02** | Teacher sửa grade ngoài lớp được giao. | GB-REQ-02/08 | Role/class matrix + pre/post-state verification. | Test data có thể khác production relationships. |
| **GB-THR-03** | API tin role chỉ được kiểm ở frontend. | GB-REQ-04 | Direct authorized API client negative function test. | Không kiểm mọi routes nếu discovery thiếu. |
| **GB-THR-04** | API nhận token sai issuer/audience. | GB-REQ-03/09 | Token fixtures + verifier logs. | MockMvc mock JWT không kiểm crypto signature thực. |
| **GB-THR-05** | Internal service tin header role/tenant do caller đặt. | GB-REQ-05 | Selected config review + synthetic inter-service request. | Nếu internal network ngoài ROE, chỉ đánh giá cấu hình. |
| **GB-THR-06** | URL download khác tenant cho phép đọc object. | GB-REQ-06/07 | Synthetic object URLs, owner/expiry tests. | CDN caching/region khác chưa chắc được kiểm. |
| **GB-THR-07** | Workflow cho sửa điểm sau khi khóa. | GB-REQ-08 | State machine tests với Test Teacher X và fixture. | Các exception/override workflows cần test riêng. |
| **GB-THR-08** | SQL query xây từ untrusted input. | GB-REQ-10 | Code review + targeted harmless negative cases. | Không chứng minh mọi sink an toàn. |
| **GB-THR-09** | Queue worker chạy dưới global role cho event giả. | GB-REQ-05/08 | Test event ownership + audit + idempotency. | Cần ROE cho async messages và cleanup. |
| **GB-THR-10** | Evidence chứa credentials/PII và bị chia sẻ rộng. | GB-REQ-01/12 | Report hygiene/access review và retention check. | Report redaction không chứng minh log production an toàn. |

### Assurance case mẫu

**Claim GB-C1:** “Trong scope đã đánh giá, Student không thể đọc/sửa bài nộp hoặc điểm của sinh viên khác, kể cả khi biết object identifier”.

**Subclaims:**

- GB-C1.1: mỗi authenticated request được gắn một actor/tenant đáng tin.
- GB-C1.2: service kiểm object ownership/class membership ở server, không chỉ UI.
- GB-C1.3: data lookup, batch/export, signed URLs và cache không làm lộ data ngoài quyền.
- GB-C1.4: test identities/fixtures thể hiện đúng các trạng thái và tenants được yêu cầu.
- GB-C1.5: test results khớp target build và security policies, có logs/evidence cho phép retest.

**Evidence:** role matrix, request/response đã redact, pre/post-state fixtures, authz service tests, source/config review, audit traces, report findings và retest nếu đã fix.

**Limitation:** Nếu test chỉ chạy 2 endpoints ở staging, không thể biến GB-C1 thành kết luận “mọi endpoint production đều an toàn”.

## 29. Phân bổ độ sâu: risk-first thay vì “quét mọi thứ”

Trong một engagement có giới hạn thời gian, nên phân bố nỗ lực theo **impact và trust boundary**, đồng thời công bố những gì chưa kiểm.

| Risk tier minh họa | Các yếu tố | Kiểm thử ưu tiên |
| --- | --- | --- |
| **Critical** | Grade integrity, identity takeover, cross-tenant data disclosure, privileged APIs. | Multi-role negative tests, business state, audit, patch/exception validation. |
| **High** | Submission confidentiality, unsafe uploads, service-to-service identity, direct data access. | Owner/tenant checks, file handling, client scopes, egress/config. |
| **Medium** | Security headers, session settings, information exposure có điều kiện. | Passive/limited active checks và triage theo risk. |
| **Low/informational** | Non-sensitive metadata differences, documentation mismatch không có impact. | Record, xác minh scope, theo dõi khi thay đổi. |

### Risk-based coverage

Một kế hoạch có thể dùng **mỗi high-value API operation × ít nhất các actor/resource class có khả năng dẫn tới vi phạm**. Ví dụ, grade view/edit phải được kiểm với owner/non-owner, same-tenant/cross-tenant, assigned/unassigned teacher, read/write scopes và published/unpublished states; file upload có matrix khác.

Không gán cứng “mỗi endpoint phải có 5 test” mà không xét business behavior và hiện trạng hệ thống. **Coverage được đo bằng các yêu cầu/risk scenarios đã nêu**, không phải request count.

## 30. Bộ test matrix gray-box minh họa

Các mã `TC-GB-01` đến `TC-GB-40` là ví dụ nội bộ. Chúng **không phải một script khai thác**; thực hiện với synthetic accounts/data, target đã cấp quyền và safety budget đã được duyệt.

| Test ID | Điều kiện và hành động có kiểm soát | Expected result |
| --- | --- | --- |
| **TC-GB-01** | Xác nhận test charter và in-scope target, kiểm environment marker. | Không chạm tài sản ngoài ROE. |
| **TC-GB-02** | Kiểm test account roles/tenants đã cấp. | Quyền thực tế khớp persona matrix. |
| **TC-GB-03** | So OpenAPI với routes có thể quan sát trong scope. | Chênh lệch được ghi/owner xác định, không tự test ngoài phạm vi. |
| **TC-GB-04** | Student A gọi own submission. | ALLOW, response đúng owner và không lộ dữ liệu khác. |
| **TC-GB-05** | Student A gọi submission của Student B cùng tenant. | DENY, không có data/metadata ngoài quyền. |
| **TC-GB-06** | Student A gọi submission thuộc Tenant Y. | DENY xuyên tenant. |
| **TC-GB-07** | Teacher X xem grade lớp X được phân công. | ALLOW theo business state. |
| **TC-GB-08** | Teacher X xem grade lớp X không phụ trách. | DENY dù cùng tenant. |
| **TC-GB-09** | Teacher X truy cập grade lớp Tenant Y. | DENY, không side effect. |
| **TC-GB-10** | Student tự gọi teacher-only grade update. | BFLA guard từ chối ở server. |
| **TC-GB-11** | Scoped admin X gọi global admin function. | DENY theo tenant/function scope. |
| **TC-GB-12** | Read-only machine client thử write operation. | Token scope enforcement từ chối. |
| **TC-GB-13** | Protected route không token. | Deny, không dữ liệu riêng. |
| **TC-GB-14** | Expired test token gọi protected route. | Reject theo lifecycle policy. |
| **TC-GB-15** | Test token wrong issuer hoặc audience. | Reject; verifier logs theo policy. |
| **TC-GB-16** | Disabled synthetic user thử sử dụng session/token. | Access đáp ứng revocation/session policy. |
| **TC-GB-17** | Student A thử truy vấn Grade B qua search/filter. | Filtered/denied, không leak result counts nhạy cảm. |
| **TC-GB-18** | Batch endpoint có IDs vừa sở hữu vừa không sở hữu. | Không có unauthorized object result hoặc partial update trái policy. |
| **TC-GB-19** | Student A thử export bảng điểm ngoài lớp. | DENY; export không chứa foreign records. |
| **TC-GB-20** | Student A xin signed URL cho file của B. | Không cấp unauthorized URL. |
| **TC-GB-21** | URL test đã hết hạn theo fixture được truy cập. | Deny sau expiry, không bypass qua cache. |
| **TC-GB-22** | Synthetic file có type không được cho phép. | Reject/handle an toàn, không xử lý độc hại. |
| **TC-GB-23** | Submission sau deadline với user không có extension. | Workflow state guard từ chối hoặc late rule đúng. |
| **TC-GB-24** | Teacher thường sửa điểm sau publish/lock. | Deny/approved override theo policy, có audit. |
| **TC-GB-25** | Repeated submit trong sandbox. | Idempotency/versioning đúng, không nhân đôi ngoài dự kiến. |
| **TC-GB-26** | Former teacher sau khi thu hồi quyền thử đọc grade. | Permission revoke được áp dụng đúng. |
| **TC-GB-27** | Service client A gọi service B với insufficient scope. | Reject theo trusted service identity. |
| **TC-GB-28** | Synthetic queue event tham chiếu object ngoài tenant. | Consumer reject/quarantine; không tác động dữ liệu. |
| **TC-GB-29** | Harmless input fixture đi tới query path. | Parameterized handling và authz, không unsafe SQL behavior. |
| **TC-GB-30** | Controlled filename fixture có ký tự bất thường. | Safe normalization/allowlist, không đọc ngoài test directory. |
| **TC-GB-31** | Error response được tạo bằng invalid test input. | Không leak stack trace, secrets hoặc PII. |
| **TC-GB-32** | Cache test với A và B sau cùng route. | Không trả cached private response của A cho B. |
| **TC-GB-33** | Audit log sau denied privileged call được xem read-only. | Có event đủ ngữ cảnh, không lộ sensitive payload. |
| **TC-GB-34** | Staging và production config/release comparison trong ROE. | Khác biệt về trust, authz, IAM được ghi đúng. |
| **TC-GB-35** | Một API do spec mô tả nhưng không tồn tại runtime. | Không tạo finding vulnerability nếu chỉ là tài liệu lệch, ghi coverage gap. |
| **TC-GB-36** | Một critical testcase chưa được phép chạy production. | NOT VERIFIED hoặc approved alternate evidence, không chấm PASS giả. |
| **TC-GB-37** | PoC BOLA trên fixture sau khi code fix ở staging. | Negative retest deny, positive use-case vẫn ALLOW. |
| **TC-GB-38** | Fix merge nhưng production vẫn chạy old image. | Production finding chưa đóng cho scope còn affected. |
| **TC-GB-39** | Test account hết hạn và artifacts còn trong môi trường. | Revoke/cleanup, xác minh data state và evidence retention. |
| **TC-GB-40** | Independent reviewer thử tái kiểm một finding theo evidence. | Có thể hiểu/reproduce trong phạm vi cho phép, ghi giới hạn. |

### Một testcase record mẫu

```yaml
gray_box_test:
  id: "TC-GB-05"
  engagement: "LMS-GRAYBOX-TRAINING"
  authorization_ref: "ROE-APPROVED-REFERENCE"
  target:
    service: "submission-api"
    environment: "authorized-staging"
    source_revision: "REVIEWED_COMMIT"
    artifact_digest: "sha256:REPLACE_WITH_REAL_DIGEST"
  actor:
    synthetic_identity: "student-a"
    role: "STUDENT"
    tenant: "school-x"
  fixture:
    resource: "submission-b-test"
    owner: "student-b"
    tenant: "school-x"
  requirement: "GB-REQ-02"
  expected: "DENY_NO_OTHER_STUDENT_DATA"
  observed: "NOT_RUN"
  evidence_ref: null
  assessment: "NOT_VERIFIED"
  cleanup_required: false
```

Đây là **mẫu hồ sơ, không phải cú pháp của scanner hoặc tool pentest cụ thể**. Chỉ khi được thực thi, quan sát và lưu evidence mới được đổi `observed`/`assessment`; không đánh PASS trước.

## 31. Evidence matrix và quality criteria

| Evidence | Vai trò trong assurance | Giới hạn cần ghi |
| --- | --- | --- |
| **Signed/approved ROE** | Quyền, scope, thời gian, safety conditions. | Không chứng minh phép thử đã thực hiện. |
| **Knowledge pack version** | Tester biết kiến trúc/spec/role model gì. | Tài liệu có thể lệch runtime. |
| **Test accounts and fixtures** | Kiểm soát actor/resource relationships. | Không có người dùng thật; production behavior có thể khác. |
| **Request/response trace** | Behavioral observation có thể đối chiếu. | Một response không chứng minh toàn bộ flow. |
| **Pre/post state evidence** | Chứng minh state-changing test có/không side effect. | Phụ thuộc timing và dữ liệu quan sát. |
| **Selected source/config snippets** | Hỗ trợ giả thuyết về control/root cause. | Code chỉ một phần, có thể có compensating controls khác. |
| **Audit logs/correlation ID** | Liên hệ request, identity và service decision. | Sensor có thể chưa bao phủ mọi path. |
| **Build/deploy identity** | Gắn tested behavior với source/artifact/runtime. | Staging digest không tự đại diện production. |
| **Finding disposition** | Đã xác minh hay đang điều tra/false positive. | Reviewer bias và stale context. |
| **Retest results** | Cho biết condition còn không ở target sau fix. | Đúng test/environment đã chạy, không tự bao phủ tất cả. |
| **Exceptions/out-of-scope record** | Làm rõ unresolved claims và permissions. | Không biến điều chưa test thành PASS. |
| **Cleanup confirmation** | Tài khoản, dữ liệu, test artifacts đã xử lý. | Không chứng minh mọi biến cố vận hành đã kết thúc. |

### Tiêu chí chất lượng

1. **Relevance:** nối đúng requirement, actor, object, environment, threat.
2. **Authenticity:** biết tester/tool, thời điểm, authorization và nguồn của observation.
3. **Integrity:** bằng chứng không bị sửa hoặc chọn lọc trái phép; lưu immutable reference/digest khi phù hợp.
4. **Completeness:** ghi cả positive/negative results, errors, skipped tests và limitations.
5. **Minimization:** đủ xác minh nhưng không thu thập credentials/PII thừa.
6. **Repeatability:** fixtures và test steps rõ để assessor tái kiểm theo ROE.
7. **Freshness:** source/build/config/role permissions tương ứng thời điểm.
8. **Independence:** người review findings/closure không chỉ tin khẳng định của người sửa.

### Tránh báo cáo ảnh chụp không có ngữ cảnh

Ảnh HTTP 200 có thể là thao tác hợp lệ; ảnh HTTP 403 có thể do token đã hết hạn chứ không phải object-level authorization. Bằng chứng phải có **identity của actor, quyền expected, object owner, auth state, build/version và response semantics**.

## 32. Chuẩn hóa finding report

Một báo cáo kỹ thuật cần giúp developer tái tạo và risk owner ra quyết định, đồng thời không cung cấp dữ liệu thật hoặc hướng dẫn gây hại không cần thiết.

| Trường | Nội dung mẫu |
| --- | --- |
| **Finding ID** | `GB-FIND-007` |
| **Title** | Object-level authorization chưa áp dụng khi đọc grade. |
| **Affected scope** | `grade-service`, staging build R, API `GET /api/grades/{gradeId}`. |
| **ROE/test** | Authorized TC-GB-09 và knowledge pack phiên bản X. |
| **Preconditions** | Teacher X School X, fixture Grade Y School Y. |
| **Expected** | DENY theo tenant/class ownership policy. |
| **Observed** | Response trả synthetic grade value của Tenant Y. |
| **Impact** | Data confidentiality và tenant isolation; scope chưa xác định ngoài fixture. |
| **Root-cause hypothesis** | Repository fetch theo ID không kiểm tenant/assignment. |
| **Severity/risk** | Được risk reviewer xác định theo exposure/impact/evidence. |
| **Remediation** | Central object authorization + tenant-scoped query + tests. |
| **Retest plan** | TC-GB-07/08/09, list/export/cache và release runtime verification. |
| **Owner/status** | Grade service owner / CONFIRMED / pending fix. |
| **Evidence** | Redacted response, fixture refs, trace ID, build/ref/version. |
| **Limitations** | Test account fixture; production không chạy active test. |

### Viết impact đúng bằng chứng

Nếu tester chỉ thấy **một** record fixture khác tenant bị lộ, báo rõ “đã xác nhận cross-tenant read trên fixture”, sau đó giải thích **tiềm năng ảnh hưởng rộng hơn nếu cùng control thiếu ở nhiều records**. Không tự khẳng định “toàn bộ dữ liệu trường học đã bị đánh cắp”.

### Risk owner cần gì?

Business impact, khả năng khai thác hợp lý, ảnh hưởng dữ liệu, số users/tenants có thể chịu rủi ro, mitigation, fix complexity, due date, residual risk và confidence. Một điểm CVSS có thể hỗ trợ một số finding nhưng không thay quyết định ngữ cảnh.

## 33. Triage, false positives và phát hiện chưa kiểm chứng

Gray-box tester có nhiều ngữ cảnh, nhưng vẫn có thể nhầm:

- API trả 404 khi unauthorized — tưởng record không tồn tại.
- Response 200 chỉ là wrapper với error code trong body.
- Test account vô tình có admin privilege do setup sai.
- Test data ownership không khớp fixture/documentation.
- Proxy/cache trả stale response từ phiên trước.
- Một endpoint đã bị deprecated và không có runtime route.
- Feature flag hoặc asynchronous processing khiến state chưa nhất quán tạm thời.
- WAF/rate limiting chặn test nhưng tester coi authorization đạt.

### Triage process

1. Đối chiếu ROE/scope và authentic actor identity.
2. Kiểm expected policy từ owner/requirements, không tự suy role semantics.
3. Xác minh fixture/ownership và môi trường/version.
4. Thu **minimal** behavior evidence, tránh thử thêm vượt mức.
5. Xem compensating controls và relevant code/config nếu được phép.
6. Xác định **confirmed issue / false positive / needs more evidence** có rationale.
7. Ghi uncertainty và limitations, không biến unknown thành fixed.

**False positive dismissal phải hẹp** theo finding/version/route và có reviewer; không xóa toàn bộ rule hoặc finding family vì một observation sai.

## 34. Remediation: sửa authorization đúng trust boundary

Một lỗ hổng gray-box thường xuất phát từ **thiếu/không nhất quán security control** qua nhiều routes hơn là từ một dòng code duy nhất.

### Các mẫu khắc phục thường gặp

| Root cause | Treatment | Verification |
| --- | --- | --- |
| IDOR/BOLA | Server-side object authorization, tenant-scoped queries, deny by default. | Same-owner allow, wrong-owner/tenant deny, batch/export tests. |
| BFLA | Central function/role/scope policy, guard ở service boundary. | Direct API tests cho low-priv roles. |
| User-controlled tenant header | Lấy identity từ verified auth context, integrity giữa gateway/services. | Spoofed header bị ignore/reject trong lab. |
| JWT verifier yếu | Kiểm issuer/audience/expiry/alg/key trust theo IdP policy. | Token fixture matrix, real verifier tests. |
| File download lộ | Owner-scoped storage access, signed URL TTL/scope, no public ACL. | Cross-owner/expired URL deny. |
| Async privileged worker | Event authenticity, tenant context, per-object check, idempotency. | Wrong-tenant event deny, no data mutation. |
| Unsafe SQL | Parameter binding + input constraints, object-level authorization. | SAST/code review + authorized negative tests. |
| Workflow bypass | Enforce state machine/approval at server, audit. | Locked/deadline/override tests. |
| Cache leak | Tenant/actor-scoped cache key, no shared private responses. | A/B sequential cache tests. |
| PII/error leakage | Structured errors, log minimization/redaction. | Error-path tests và log sampling. |

**Đừng “sửa” chỉ bằng ẩn nút frontend, đổi ID thành UUID, thêm WAF rule chung chung hoặc cho scanner báo xanh.** Những biện pháp này có thể có lợi phụ trợ nhưng không thay kiểm soát quyền ở nơi truy cập dữ liệu/chức năng.

### Một change cần xem tác động hệ thống

Thêm tenant filter có thể ảnh hưởng queries, search, exports và background processing. Một policy làm teacher mất quyền chính đáng có thể gây **availability/operability regression**. Remediation phải có **positive tests**, không chỉ negative tests.

## 35. Retest và closure sau fix

### Retest checklist

1. Xác nhận finding ID, requirement/control, root cause và expected fix.
2. Xác định source commit, build artifact digest, staging/release environment và chính sách mới.
3. Khôi phục **same test actor/object state** hoặc fixture tương đương đã ghi.
4. Chạy lại negative test từng dẫn tới lỗi và **positive control** được phép.
5. Mở rộng trong phạm vi sang routes liên quan: list/search/export/batch/async/cache.
6. Kiểm security regression đối với role khác, token, logging, data integrity và performance.
7. Xác minh production target version/deployment khi closing **production finding**.
8. Thu evidence mới; so sánh previous/actual một cách trung thực.
9. Đánh giá residual risk, exceptions, missing scope và cleanup.
10. Independent reviewer quyết định **CLOSED_VERIFIED**, FAIL, NOT VERIFIED hoặc treatment khác.

### Những tình huống chưa được đóng

- PR đã merge nhưng image production còn dùng source cũ.
- Issue không còn tái hiện vì test role đã mất quyền truy cập hoàn toàn, làm không còn positive control.
- Test route bị tắt nhưng replacement route chưa được kiểm.
- Staging fail/deny do WAF không tồn tại production.
- Scanner báo “No findings” nhưng role/tenant negative test chưa chạy.
- Risk accepted nhưng technical weakness vẫn còn.

### Thời điểm đóng

**Source-fixed** và **production-verified** nên là những milestone khác nhau. Đối với code-only scope có thể có closure ở source/review level; đối với claim production security assurance, cần bằng chứng deployment và behavior liên quan.

## 36. Case study: Student xem được bài nộp của bạn cùng lớp

### Tình huống

LMS cung cấp test accounts Student A và B cùng School X. API cho xem submission:

```http
GET /api/submissions/submission-b-test HTTP/1.1
Host: staging.example.invalid
Authorization: Bearer TEST_STUDENT_A_TOKEN
Accept: application/json
```

Trước đó positive control bằng Student B có quyền xem submission B. Student A không là owner, không được chia sẻ bài. Trong **tình huống giả định**, API trả body có `ownerId=student-b` và nội dung câu trả lời B. Tester ghi một response **đã redact** và dừng sau PoC tối thiểu.

### Phân tích

| Thành phần | Observation | Diễn giải |
| --- | --- | --- |
| Identity | Token test của A hợp lệ, role Student. | Authentication hoạt động; không đủ cho object authorization. |
| Object | Submission B thuộc B theo fixture có kiểm. | Có expected deny rõ ràng. |
| API behavior | Trả nội dung B. | **Confirmed BOLA** cho endpoint/fixture này. |
| Business impact | Disclosure of another student's submission. | Có ảnh hưởng confidentiality/privacy trong scope; scale cần điều tra. |
| Root cause | Service tìm submission theo ID, có thể thiếu owner/class check. | **Hypothesis**; phải review code/config để xác nhận. |
| Remediation | Check owner/tenant/class + query filtering. | Cần tests same-owner allow/wrong-owner deny. |
| Evidence | ROE/test ID, roles, fixture, trace, build, redacted response. | Không được chứa raw token hay câu trả lời thật. |

### Đường khắc phục

1. AppSec xác minh finding, thông báo owner theo quy định.
2. Service owner kiểm data access path và quyền trên object.
3. Thêm object authorization ở trusted service boundary, áp cho list/export/batch nếu liên quan.
4. Thêm regression tests cho same-tenant wrong-owner và cross-tenant.
5. Retest trên patched build với positive + negative fixtures.
6. Đối chiếu production deployment và xử lý các endpoints chưa được kiểm.
7. Lưu closure evidence, giám sát recurrence và cập nhật review checklist.

### Kết luận chuẩn

> “TC-GB-05 xác nhận trong staging build R rằng Student A có thể đọc synthetic Submission B trái requirement GB-REQ-02; đây là finding cần xử lý. Chưa có phép thử production và không có cơ sở tuyên bố dữ liệu thật bị truy xuất. Sau fix, yêu cầu retest cả owner/tenant variants và đối chiếu build chạy thực tế.”

Thông tin có giới hạn nhưng đủ hỗ trợ quyết định remediation.

## 37. Case study: “đã kiểm JWT” nhưng thực ra chỉ kiểm mock

### Tình huống

Team `identity-api` dùng Spring Security và đã viết nhiều MockMvc tests với `jwt()`. Các tests đều PASSED khi token có audience/issuer expected, expired token hoặc wrong issuer. Nhóm kết luận rằng **OIDC token verification trong production đã đủ mạnh**.

Assessor đọc test setup và phát hiện các tests **chỉ inject mock authentication** vào SecurityContext, không đi qua đường xác minh chữ ký JWT và không dùng cấu hình real `JwtDecoder` như runtime.

### Phân tích assurance

| Claim | Evidence hiện có | Kết luận đúng |
| --- | --- | --- |
| Endpoint phân quyền theo scopes/roles đã đưa vào mock. | MockMvc với `jwt()` và role matrix. | Có thể hỗ trợ kiểm application authorization ở layer phù hợp. |
| JwtDecoder chỉ tin issuer/audience được duyệt. | Không có real verifier test. | **NOT VERIFIED**. |
| Signature/key rotation và alg policy đúng. | Không có real signature/cert tests. | **NOT VERIFIED**. |
| Service không tin user-controlled tenant header. | Source review một phần, chưa có behavior test. | Needs targeted integration test. |
| Production dùng cùng auth config như staging. | Chưa có release/config comparison. | **NOT VERIFIED**. |

### Kế hoạch khắc phục

1. Tách **authorization integration tests** và **token-verifier protocol tests** thành những claim khác nhau.
2. Dùng test IdP/trusted test signing keys trong isolated environment có permission, không dùng production private keys.
3. Kiểm real filter chain/JwtDecoder với wrong issuer, wrong audience, expired tokens và acceptable key rotation semantics.
4. Kiểm backend lấy tenant identity từ claims đã xác thực, không từ user-controlled header.
5. Reconcile runtime environment config theo scope và kiểm không có bypass paths.
6. Lưu tool/source/deployment evidence riêng cho từng claim, retest sau fix.

**Bài học:** Gray-box knowledge về framework giúp nhìn rõ một lỗ hổng trong **test coverage**; việc một mock-based test PASS không phải dấu hiệu code auth yếu, mà là **giới hạn của bằng chứng** cần xử lý trung thực.

## 38. Case study: Teacher thay đổi điểm qua đường batch

### Bối cảnh

Trong School X, Teacher X chỉ được cập nhật grades của lớp A. API đơn lẻ `PATCH /grades/{gradeId}` đã kiểm class ownership đầy đủ. Nhưng tính năng batch được thêm gần đây để nhập điểm từ bảng CSV:

```text
POST /api/grades/batch-update
Body contains test-only grade IDs and proposed scores.
Caller: Teacher X from School X.
Fixture set:
  - Grade 1: Class A, assigned to Teacher X
  - Grade 2: Class B, not assigned to Teacher X
```

Tester biết sơ đồ class ownership và được cấp **hai grade records giả**. Sau một lần request trong staging theo ROE, cả hai grades đều thay đổi trong **tình huống giả định**, dù operation đối với Grade 2 phải bị deny.

### Vì sao test chỉ trên UI không đủ?

UI có thể chỉ cho Teacher X chọn lớp A. Nhưng API batch có thể tin danh sách IDs client gửi và dùng một câu cập nhật không kiểm ownership từng record. Tương tự, audit log và cache invalidation cũng có thể được thực thi sai ngữ cảnh.

### Kết quả và giới hạn

| Observation | Ý nghĩa |
| --- | --- |
| Single-item endpoint từ chối sửa Grade 2. | Control có mặt ở path đơn lẻ. |
| Batch endpoint cập nhật Grade 2 từ token Teacher X. | Confirmed function/object authorization gap tại batch path trên fixture. |
| Database pre/post snapshot trên test records. | Chứng minh unauthorized state change; evidence cần che data nhạy cảm. |
| Không test toàn bộ teachers/tenants production. | Chưa xác định scale rộng hơn. |

### Fix và retest

Thực thi **authorization cho từng object** tại service/data boundary, không chỉ kiểm Teacher role một lần. Với batch operations, cần xác định **transaction semantics**: tất cả hoặc không item nào được cập nhật nếu có unauthorized item, hay partial success theo contract được phê duyệt. Đảm bảo audit/tenant scoping, idempotency và no unauthorized write. Retest cả allow path, wrong-class, cross-tenant và mixed batch fixtures; không làm thay đổi điểm thật.

## 39. Đánh giá coverage: test đã bao phủ điều gì?

Một engagement thời gian cố định không thể kiểm mọi input/actor/state. Do đó cần **coverage ledger** và **uncertainty report**.

### Các chiều coverage

| Dimension | Câu hỏi | Measurement basis |
| --- | --- | --- |
| **Requirements** | Bao nhiêu GB-REQ có test/evidence phù hợp? | Requirements-to-test mapping. |
| **Threat scenarios** | Các high-risk abuse cases đã được kiểm? | Threat register / risk tier. |
| **Actors** | Student, Teacher, Admin, machine clients, unauthenticated? | Test personas và trust assumptions. |
| **Tenants** | Same-tenant wrong-owner và cross-tenant paths? | Synthetic tenant/object matrix. |
| **Endpoints/actions** | Read, write, batch, export, async và internal routes? | API spec + authorized discovery. |
| **Business states** | Draft/submitted/graded/published/locked? | Workflow state coverage. |
| **Environments** | Staging, production evidence, DR? | Build/config equivalence và ROE. |
| **Security controls** | Authn, authz, audit, privacy, rate, storage? | Control matrix/tests. |
| **Evidence quality** | Complete observations, version/source, limitations? | Assessor review và reproducibility. |

### Tránh coverage ảo

“100% endpoint URLs đã được gọi” có thể thiếu **role, object và state combinations**. “100% security checks PASS” có thể chỉ bao gồm **những checks được chọn**, không có nghĩa mọi requirement đạt. Báo cáo coverage phải chỉ ra **mẫu số**, cách chọn testcase và các high-risk paths chưa được thực hiện.

### Risk-based sampling

Nếu có hàng trăm endpoints, chọn mẫu theo các nhóm có **security invariant giống nhau** và xác nhận những điểm quyết định khác biệt (role, tenant, ownership, state). Đừng lấy một test ở một controller rồi suy rằng tất cả handlers/frameworks đều thực thi y hệt.

## 40. Chỉ số hiệu quả và continuous gray-box assurance

Pentest theo dự án thường chỉ diễn ra tại một thời điểm. Để dùng nó trong assurance liên tục, tổ chức cần nối findings/tests vào **release, change, vulnerability remediation và security verification workflows**.

| KPI/KRI | Ý nghĩa | Cạm bẫy |
| --- | --- | --- |
| **Critical threat coverage** | Tỷ lệ high-value abuse scenarios có evidence. | Inventory/threat model thiếu làm mẫu số nhỏ. |
| **Authorization matrix coverage** | Các actor–resource–action/tenant conditions đã test. | Đếm endpoint thay vì negative combinations. |
| **Confirmed high-risk findings** | Những violations đã xác minh và chưa xử lý. | Số findings tăng khi test sâu hơn không tự nghĩa hệ thống xấu đi. |
| **Time to triage** | Từ observation đến owner/risk decision. | Không đồng nhất scanner alert với confirmed issue. |
| **Time to verified remediation** | Từ finding tới deployment/retest đúng scope. | Merge PR không phải production fix. |
| **Reopened/regression rate** | Issues tái xuất hiện sau closure. | Không có stable finding identity gây số giả. |
| **Unverified critical controls** | Các requirement còn thiếu phép thử/evidence. | “Không test” không thành “không có lỗi”. |
| **Exception age** | Gaps tạm được chấp thuận còn bao lâu. | Accepted risk không phải PASS. |
| **Test environment fidelity** | Khác biệt staging/prod ảnh hưởng claims. | Staging giống source nhưng khác IAM/WAF/IdP. |
| **Test impact/safety incidents** | ROE breaches, cleanup gaps, unexpected state changes. | Không che incident chỉ để KPI pentest đẹp. |
| **Repeatability** | Assessor có thể tái thực hiện PoC đã scrub. | Report thiếu fixtures/build IDs. |
| **Root-cause recurrence** | BOLA/BFLA/workflow flaws tái phát ở services. | Đóng tickets nhanh không đồng nghĩa phòng ngừa tốt. |

### Reassessment triggers

- Thêm role/tenant model, phân quyền lớp học hoặc workflows mới.
- Đổi OAuth/OIDC issuer, key rotation, gateway/authorization policies.
- Thêm API batch/export, GraphQL resolver, object storage presigned URL.
- Refactor authz code hoặc repository tenant filtering.
- Triển khai service-to-service proxy, queue consumer, new cloud IAM roles.
- Chuyển từ monolith sang microservices, thay network trust boundaries.
- Incident nghi authorization bypass, PII leakage hoặc compromised identity.
- Remediation cho finding high-risk đã deploy, cần independent retest.
- Major framework update hoặc changes trong session/cookie/token semantics.
- Third-party provider config hoặc contract thay đổi làm lệch shared responsibility.

**Không phải lần thay đổi nào cũng cần full pentest ngay**, nhưng cần impact assessment và targeted testing cho threat/control bị ảnh hưởng. Kỳ pentest định kỳ không thay patching, continuous scanning và incident response.

## 41. Tổ chức engagement: roles, trách nhiệm và RACI

| Vai trò | Trách nhiệm |
| --- | --- |
| **Engagement sponsor/business owner** | Mục tiêu, business impact, scope và approval giao việc. |
| **Asset/service owner** | Kiến trúc, asset inventory, role model, data/test fixtures và safety constraints. |
| **Gray-box penetration tester** | Theo ROE, thiết kế/thi hành phép thử, báo evidence và limitations. |
| **AppSec/security lead** | Threat model, validation, triage và remediation guidance. |
| **Platform/SRE** | Môi trường staging, monitoring, test traffic budgets, rollback/on-call. |
| **Identity/IAM owner** | Test accounts, token scopes, MFA/revocation và trust boundaries. |
| **Data/privacy owner** | Synthetic data, data minimization, retention và incident handling. |
| **Developer** | Root-cause analysis, code/control fix, unit/integration regression tests. |
| **Independent assessor** | Review findings/evidence, validate scope và retest decisions. |
| **Risk owner** | Risk acceptance, prioritization và exception approval đúng thẩm quyền. |
| **Incident response** | Containment/escalation khi có leak, outage, unauthorized side effect. |
| **Vendor owner** | Shared responsibility và kiểm third-party scope/authorization. |

### RACI mẫu

R = Responsible, A = Accountable, C = Consulted, I = Informed. Đây là ví dụ cần điều chỉnh theo người thực sự có quyền.

| Hoạt động | Sponsor/Owner | Tester | AppSec | Platform/Dev | Assessor | Risk owner |
| --- | :---: | :---: | :---: | :---: | :---: | :---: |
| Xác định goals, ROE và authorization | **A** | C | R | C | C | I |
| Cung cấp knowledge pack/test fixtures | **A** | C | C | **R** | I | I |
| Lập threat/risk test plan | C | **R** | **A** | C | C | I |
| Thực hiện gray-box tests an toàn | I | **A/R** | C | C | I | I |
| Triage và severity/risk context | C | R | **A/R** | C | C | C |
| Code/config remediation | C | C | C | **A/R** | I | I |
| Independent retest/closure | C | R | C | C | **A** | I |
| Accepted risk/exception decision | C | C | C | C | C | **A/R** |
| Incident/escalation khi test gây tác động | **A** | R | R | R | C | C |
| Continuous assurance follow-up | C | C | **A** | R | R | I |

**Separation of duties:** người viết code có thể chạy unit/security tests, nhưng **không nên là người duy nhất tự xác nhận closure** của một finding critical do mình sửa. Mức độ độc lập phải phù hợp risk/governance.

## 42. Anti-patterns và những nhầm lẫn phổ biến

| Nhầm lẫn | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| “Gray box nghĩa chỉ được cấp một user/password.” | Cần mô tả cả knowledge và privileges. | Test access matrix + knowledge pack/assumptions. |
| “Đã có kiến trúc thì không cần discovery.” | Sơ đồ/spec có thể cũ và bỏ routes. | Reconcile in-scope runtime evidence. |
| “Authenticated scan = gray-box pentest đầy đủ.” | Automated scan dễ bỏ sót BOLA/business logic. | Manual hypothesis-driven tests và threat coverage. |
| “Black-box luôn thực tế hơn gray-box.” | Attacker capabilities đa dạng; black-box bỏ nhiều protected flows. | Chọn approach theo mục tiêu và ROE. |
| “Gray-box tester biết secrets thì được dùng mọi nơi.” | Knowledge ≠ authorization. | Secret minimization, separate credentials/scope. |
| “HTTP 200 chứng minh BOLA.” | Có thể request hợp lệ hoặc body chứa error. | Owner/role fixture, expected policy và data response. |
| “HTTP 403 chứng minh object auth đúng.” | Có thể do token hết hạn/route khác. | Positive controls và normalized auth context. |
| “UUID khó đoán khắc phục IDOR.” | Object-level authorization vẫn thiếu. | Server-side checks từng resource/action. |
| “Frontend không có nút Admin nên không test API.” | UI không là server authorization. | Direct in-scope API negative tests. |
| “Mock JWT test xanh nghĩa verifier an toàn.” | Mock bypass cryptographic verification path. | Real verifier/test IdP validation riêng. |
| “Source code có @PreAuthorize thì mọi record an toàn.” | Function-level role ≠ object/tenant check. | Full call path + behavior tests. |
| “Pentest không tìm lỗi nghĩa hệ thống không có lỗ hổng.” | Scope/time/coverage giới hạn. | Claim có điều kiện và NOT VERIFIED gaps. |
| “Dùng dữ liệu thật giúp PoC thuyết phục hơn.” | Tăng rủi ro privacy/legal/impact. | Synthetic fixtures và minimal evidence. |
| “Không thấy data leak là có thể tiếp tục thử đến khi đủ nhiều.” | Vi phạm safety/ROE khi mở rộng thử. | Stop at sufficient proof, escalate. |
| “Fix được merge thì finding production đóng.” | Prod có thể chạy artifact/config cũ. | Deployed digest + targeted retest. |
| “Accepted risk là PASS.” | Technical gap còn, residual risk chưa biến mất. | Separate exception và reassessment. |
| “Bản report nhiều screenshots là đầy đủ.” | Thiếu identity, expected result, data context. | Structured evidence with version and traceability. |
| “Một tenant test đủ chứng minh multi-tenant isolation.” | Cross-tenant boundary cần negative matrix. | Role×tenant×object×state sampling. |

## 43. Bài tập tình huống có đáp án định hướng

### A. Tester biết endpoint admin nhưng không được cấp account admin

**Hỏi:** Có nên thử quyền quản trị bằng các token đoán được?

**Định hướng:** Không. Kiểm allowed personas trong ROE, dùng config/source evidence hoặc đề xuất bổ sung synthetic scoped admin account sau approval. Không mở rộng quyền hoặc dùng thông tin thu được trái phép.

### B. Student A đọc được Grade B trên staging

**Hỏi:** Có thể ghi “mọi người dùng xem điểm của nhau trên production” không?

**Định hướng:** Chỉ báo confirmed unauthorized read trên fixture/staging build và đánh giá potential impact. Cần production equivalence, scope assessment và các tests bổ sung để kết luận rộng hơn.

### C. Teacher xem được toàn bộ lớp vì đã đăng nhập

**Hỏi:** Authentication đã đúng có nghĩa authorization đạt không?

**Định hướng:** Không. Kiểm class assignment, tenant, object ownership và operations với positive/negative controls.

### D. Một test MockMvc với `jwt()` PASS

**Hỏi:** Điều gì còn chưa được chứng minh?

**Định hướng:** Real JWT signature/issuer/audience/key rotation và production filter configuration, nếu mock bypass verifier. Tách claims và test IdP/verifier thực trong lab.

### E. API trả 404 khi Student A yêu cầu object của B

**Hỏi:** Có thể đóng tất cả BOLA requirements?

**Định hướng:** Một testcase có thể PASS nếu token của A hợp lệ và positive control xác minh route, fixture đúng. Các list/export/batch/cache/async paths vẫn cần coverage riêng.

### F. Staging có WAF nhưng production không có

**Hỏi:** Tester không tìm thấy injection ở staging có đủ chưa?

**Định hướng:** Không tự suy production PASS. Phải xem WAF differences, code/database controls, target build equivalence và limited production evidence hoặc NOT VERIFIED.

### G. Teacher được phép sửa điểm trước deadline, nhưng test sau deadline lại ALLOW

**Hỏi:** Đây là BFLA hay business workflow gap?

**Định hướng:** Có thể là authorization theo business state; xác minh policy/exception và impact, ghi chính xác violated invariant. Không chỉ gắn nhãn framework mà bỏ remediation root cause.

### H. Test API vô tình trả về PII của người học thật

**Hỏi:** Có tiếp tục tìm các records khác để xác nhận scale không?

**Định hướng:** Không. Dừng thu thập, báo incident/owner, bảo vệ evidence tối thiểu, xử lý theo privacy/ROE. Dùng synthetic data để kiểm những trường hợp còn lại.

### I. Scanner kết luận “No Critical” nhưng chưa test Teacher/Student roles

**Hỏi:** Chấm assurance thế nào?

**Định hướng:** Automated scan có kết quả có phạm vi, nhưng role authorization chưa được xác minh. Ghi coverage gap/NOT VERIFIED, làm targeted gray-box tests.

### J. Fix đã merge nhưng production chưa deploy

**Hỏi:** Báo cáo “remediated” có chính xác?

**Định hướng:** Source fix có thể được xác nhận; production risk chưa được closed nếu không có deployment/retest evidence trên affected artifact.

### K. Test case chạm một internal API ngoài phạm vi

**Hỏi:** Nên tiếp tục vì có thể có lỗ hổng?

**Định hướng:** Dừng, xác minh scope với engagement owner và xin authorization bằng quy trình mới nếu cần. Không mặc định biết internal URL là quyền gọi.

### L. Một lỗ hổng chỉ xuất hiện khi batch update gồm hai grade IDs

**Hỏi:** Tại sao single-object test không tìm thấy?

**Định hướng:** Authorization có thể được thực thi ở handler đơn lẻ nhưng thiếu trong batch path; cần test mixed ownership, transaction semantics và shared service boundary.

### M. Test identity của Student A bị cấp nhầm quyền admin

**Hỏi:** Kết quả request tới Grade B có còn dùng được?

**Định hướng:** Phải xác minh effective permissions, ghi test setup error và chạy lại với đúng identity. Không suy BOLA khi actor vốn được phép xem dữ liệu theo config test.

### N. Vendor IdP nằm ngoài ROE

**Hỏi:** Có thể đánh giá token validation của ứng dụng không?

**Định hướng:** Có thể kiểm integration và app-side verifier với test IdP/config evidence trong phạm vi owned assets; không thực hiện tấn công vào vendor endpoint. Provider controls ngoài scope cần shared responsibility evidence riêng.

### O. Một lỗ hổng BOLA bị risk owner chấp nhận tạm thời

**Hỏi:** Technical finding có chuyển thành PASS?

**Định hướng:** Không. Giữ confirmed weakness, risk treatment/compensating controls, expiry, owner và monitoring/retest. Chỉ đóng khi condition đã được xử lý theo yêu cầu.

## 44. Checklist tổ chức và đánh giá gray-box pentest

### Trước khi thực hiện

1. **Purpose:** Đã xác định security objectives, requirements và risk decisions mà engagement phục vụ?
2. **Authorization:** Có ROE với owner, targets, permitted activities, thời gian, limits và stop conditions?
3. **Scope:** Service, environment, APIs, tenants, roles, data stores và vendors được xác định?
4. **Knowledge pack:** Sơ đồ, API spec, data model, selected code/config có version, nguồn và độ tin cậy?
5. **Threat model:** Có attacker assumptions, trust boundaries, impact, abuse scenarios và priority?
6. **Access matrix:** Test accounts/roles/scopes/tenants chính xác, có TTL/MFA và revocation procedure?
7. **Fixtures:** Synthetic users, objects, tenant relationships, business states và cleanup đã chuẩn bị?
8. **Safety:** Có non-destructive default, traffic limits, rollback, on-call, monitoring và escalation?
9. **Privacy:** Không dùng PII/credentials thật nếu không cần; evidence retention/redaction được quy định?
10. **Coverage:** Expected test matrix cho critical actors–objects–actions và integrations đã được duyệt?

### Trong khi thực hiện

11. **Reconciling context:** API/spec/architecture có được đối chiếu với in-scope runtime behavior?
12. **Positive controls:** Các quyền hợp lệ được xác minh trước khi negative tests được diễn giải?
13. **Authentication:** Missing, expired, wrong issuer/audience/scope và disabled sessions được kiểm đúng layer?
14. **Authorization:** BOLA/IDOR/BFLA kiểm theo object, tenant, class ownership và function ở server?
15. **Business state:** Deadline, publish/lock, override, batch và event workflows có tests?
16. **Backend flows:** Storage, queues, service-to-service identity và caches được xem xét đúng scope?
17. **Input handling:** Các tests an toàn và code/config reviews gắn đúng risk, không destructive proof?
18. **Observability:** Ghi test identity, target revision, request context và audit trace một cách redacted?
19. **Data safety:** Không truy xuất thêm dữ liệu thật khi thấy leak; xử lý ngay qua incident channel?
20. **Control result:** Expected/observed/limitations được ghi cho cả PASS, FAIL và NOT VERIFIED?

### Sau kiểm thử

21. **Findings:** Mỗi confirmed issue có affected asset, preconditions, risk/impact và PoC tối thiểu?
22. **False positives:** Dispositions có evidence, reviewer và scope rõ, không suppress toàn cục?
23. **Evidence package:** ROE, accounts/fixtures, test IDs, build, traces, timestamps và data protection đủ?
24. **Reporting:** Executive risk summary và technical report không đánh đồng observed với assumed impact?
25. **Remediation:** Owner/action/due date, root cause và server-side controls được đề xuất?
26. **Risk acceptance:** Compensating controls, approval, expiry và residual risk hiển thị riêng?
27. **Retest:** Fix được kiểm bằng positive + negative cases trên target revision/release phù hợp?
28. **Production closure:** Đã đối chiếu deployed artifact/config và runtime scope trước khi chấm fixed?
29. **Cleanup:** Test identities/tokens/files/records được xử lý và evidence được giữ theo retention policy?
30. **Continuous assurance:** Các regression tests, threat model updates, lessons learned và triggers đã được chuyển cho owner?

**Tóm lại:** Một gray-box pentest có chất lượng không được đo bằng số lượng requests hoặc số lỗ hổng tìm thấy. Nó đáng tin khi **mô tả rõ mức hiểu biết và quyền hạn được cấp, kiểm chứng đúng trust boundaries bằng các actor/object states có kiểm soát, chỉ kết luận trong phạm vi evidence, và đưa findings vào chu trình remediation/retest/continuous assurance**.

## 45. Tài liệu tham khảo và hướng học tiếp

Các tài liệu dưới đây là nguồn định hướng phương pháp; khi dùng cho hệ thống thật, cần kiểm **phiên bản đang áp dụng, scope của tiêu chuẩn, quyền đánh giá và yêu cầu tổ chức**:

- **NIST SP 800-115 – Technical Guide to Information Security Testing and Assessment:** lập kế hoạch, quy tắc thực hiện, phân tích kết quả và reporting cho kiểm thử bảo mật được phép.
- **OWASP Web Security Testing Guide (WSTG):** các nhóm kỹ thuật kiểm thử xác thực, quản lý phiên, ủy quyền, input validation và business logic, cần điều chỉnh theo ROE.
- **OWASP Application Security Verification Standard (OWASP ASVS):** nguồn tham khảo requirements và verification levels cho ứng dụng; dùng để kết nối claim–test–evidence theo version phù hợp.
- **OWASP API Security Top 10:** các nhóm rủi ro API như **Broken Object Level Authorization** và **Broken Function Level Authorization**; không phải checklist đủ cho mọi app.
- **Penetration Testing Execution Standard (PTES):** cách tổ chức scope, intelligence gathering, threat modeling, analysis, validation và reporting; cân nhắc tương thích với policy.
- **NIST SP 800-53 / SP 800-53A:** security controls và assessment methods như examine/interview/test, giúp liên kết kết quả pentest với assurance claims.
- **NIST SP 800-218 (SSDF):** secure software development và vulnerability response, giúp đưa pentest findings về quy trình sửa và regression tests.
- **MITRE CWE:** phân loại weakness như incorrect authorization, SQL injection, unsafe deserialization; không đồng nghĩa mọi finding đều có CVE.
- **FIRST CVSS:** hệ thống chấm mức nghiêm trọng có điều kiện; cần kết hợp attacker preconditions, business impact và context.
- **OAuth 2.0/OIDC và JWT specifications:** các nguyên tắc identity, token audience/issuer, delegation và verifier; đánh giá đúng profile/implementation.
- **Spring Security/Spring Boot và `spring-security-test` documentation:** phương thức authorization, filter chains, JwtDecoder, MockMvc và test fixtures; chú ý mock JWT vs real cryptographic token verification.
- **Kubernetes/Cloud IAM/Storage provider security guides:** effective permissions, service identities, network policies, resource access và shared responsibility theo provider version.
- **OWASP SAMM:** tổ chức security assurance/verification như chương trình cải tiến theo chu kỳ thay đổi.

### Những bước học tiếp

1. Dùng **threat modeling và DFD** để phát hiện các trust boundaries quan trọng của hệ thống.
2. Chuyển **ASVS/API security requirements** thành test cases theo role–object–action–state.
3. Kết hợp **SAST, DAST, SCA, code review và gray-box pentest** để bù blind spots của từng phương pháp.
4. Xây **finding lifecycle** từ validated issue tới code fix, deployment evidence, retest và closure.
5. Kiểm **control operating effectiveness** qua nhiều releases và xử lý exceptions/minor incidents có evidence.

**Lưu ý học thuật và an toàn:** Các IDs, hosts, URLs, tokens, data fixtures, YAML/HTTP/Java snippets, findings và case studies trong bài là **mẫu giáo dục**, không phải bằng chứng của môi trường thật. Chỉ thực hiện phép thử trên **tài sản được ủy quyền với Rules of Engagement rõ**, dữ liệu kiểm thử đã chuẩn bị, giới hạn tác động và người chịu trách nhiệm. Khi chưa được phép kiểm một thành phần, phải ghi limitation hoặc **NOT VERIFIED**, không tìm cách truy cập vượt quyền.
