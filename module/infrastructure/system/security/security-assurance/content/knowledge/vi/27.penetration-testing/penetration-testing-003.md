# Black-box Penetration Testing: Kiểm thử hộp đen có bằng chứng trong Security Assurance

## 1. Vì sao kiểm thử hộp đen vẫn cần thiết?

Giả sử một nền tảng SaaS quản lý hóa đơn đã vượt qua các bước code review, SAST, kiểm tra cấu hình, threat modeling và unit tests. Đội phát triển kết luận rằng API có xác thực, database queries có tenant filtering và object storage mặc định là private. Tuy nhiên, một người dùng có tài khoản hợp lệ ở tenant A vẫn có thể truy cập một link xuất dữ liệu của tenant B qua một endpoint cũ không có trong tài liệu. Điểm yếu nằm ở **hành vi quan sát được của hệ thống đã triển khai**, không nhất thiết nằm ở đoạn code mà reviewer trước đó đã xem.

**Black-box penetration testing (kiểm thử xâm nhập hộp đen)** là phương pháp kiểm thử bảo mật trong đó người kiểm thử tiếp cận mục tiêu **chủ yếu qua những giao diện và thông tin có thể quan sát từ vị trí đã xác định**, không được cung cấp sẵn kiến trúc nội bộ, source code hay đặc quyền quản trị như một phần của phương pháp kiểm thử. Người kiểm thử suy luận cách hệ thống hoạt động từ phản hồi, luồng nghiệp vụ, endpoints, trạng thái, lỗi và hành vi quyền truy cập.

Từ “black box” mô tả **mức thông tin về nội bộ hệ thống**, không có nghĩa người kiểm thử được tự do xâm nhập bất cứ đâu. Kiểm thử vẫn phải có **ủy quyền, phạm vi, giới hạn kỹ thuật, dữ liệu thử và quy tắc dừng** rõ ràng.

Trong module **SECURITY_SECURITY_ASSURANCE**, mục tiêu là học **cách đánh giá có bằng chứng** rằng hệ thống đáp ứng mục tiêu bảo mật, từ rủi ro và security requirements tới kiểm thử, audit và remediation liên tục. Black-box pentest cung cấp một góc nhìn quan trọng: **liệu một tác nhân với khả năng truy cập cụ thể có thực sự vượt được ranh giới bảo mật ở bề mặt hệ thống hay không?**

Chuỗi tư duy xuyên suốt bài:

**Business/security objectives → authorized scope → external observations → attack hypotheses → controlled validation → evidence → findings & impact → remediation → retest → assurance conclusion with limitations.**

> Một black-box pentest không phải tuyên bố rằng “hệ thống không thể bị tấn công”. Nó cung cấp kết quả quan sát có phạm vi và thời điểm rõ ràng về những đường tấn công đã thử, thành công, thất bại hoặc chưa thể kết luận.

## 2. Black box, gray box, white box khác nhau ra sao?

| Phương pháp | Thông tin người kiểm thử có trước | Điểm mạnh | Giới hạn |
| --- | --- | --- | --- |
| **Black box** | Chủ yếu interfaces/địa chỉ và điều kiện kiểm thử; ít hoặc không có source/kiến trúc nội bộ. | Mô phỏng góc nhìn bên ngoài, kiểm tra sự cố ngoài dự kiến và thiết kế thực tế đã deploy. | Mất thời gian khám phá, khó xác nhận root cause, có thể bỏ paths không thể thấy. |
| **Gray box** | Có một phần tài liệu, tài khoản/role, API contract, sơ đồ hoặc thông tin cấu hình. | Tập trung nhanh vào trust boundaries và nghiệp vụ, kiểm tra roles/tenant context. | Góc nhìn bị dẫn dắt bởi tài liệu hoặc giả định được cung cấp. |
| **White box** | Có source, architecture, code/permissions, cấu hình và có thể truy cập môi trường phân tích. | Tìm root cause và đường nội bộ sâu, review logic/coverage toàn diện hơn. | Cần nhiều thông tin/quyền, khó mô phỏng một số hành vi của đối thủ bên ngoài. |

### Không coi gray box là “black box thất bại”

Nếu tổ chức cung cấp **test accounts thuộc nhiều roles và tenants** để kiểm chứng object authorization, bài kiểm thử có thể có yếu tố gray-box về quyền được cấp. Quan trọng là **mô tả đúng mức tri thức của tester**, không giữ một nhãn phương pháp bằng cách từ chối thông tin cần cho kết luận.

### Một chương trình tốt kết hợp nhiều góc nhìn

Black-box tests giúp tìm sai lệch của **deployed interface**; white-box review giúp tìm root cause; threat modeling giúp khám phá đường tấn công chưa dễ thấy; SAST/SCA giúp kiểm soát code/dependencies; monitoring và incident drills giúp đánh giá hoạt động. Chúng **bổ sung**, không thay thế nhau.

## 3. Penetration testing không đồng nghĩa vulnerability scanning

Một vulnerability scanner có thể nhận diện banner, TLS configuration, gói phần mềm hoặc known signatures. Pentest bao gồm việc **xem lại điều kiện, kiểm tra tác động và thử xác minh một giả thuyết trong scope cho phép**, bằng tự động hóa, phân tích thủ công hoặc test logic nghiệp vụ.

| Hoạt động | Mục đích | Kết luận có thể hỗ trợ |
| --- | --- | --- |
| **Asset/attack surface discovery** | Xác định tài sản và giao diện reachable. | Có endpoint/host/service candidate cần đánh giá. |
| **Vulnerability scanning** | Tìm dấu hiệu lỗ hổng dựa rule/signature. | Potential findings, applicability cần triage. |
| **Black-box penetration testing** | Kiểm chứng một số đường tấn công từ viewpoint xác định. | Observed access bypass/data exposure/business impact trong scope. |
| **Security configuration assessment** | So effective config với baseline. | Control đúng/sai theo policy cụ thể. |
| **Code review/SAST** | Kiểm tra unsafe patterns hoặc data flows nội bộ. | Source-level issues, chưa chắc runtime exploit. |
| **Security assurance** | Kết hợp claim, argument, controls, tests và evidence để kết luận có giới hạn. | Mức tin cậy theo tài sản, yêu cầu, thời điểm, phương pháp. |

### Ví dụ phân biệt

Scanner nhận diện một API endpoint trả lỗi HTTP 500 cho input lạ. Đó **không tự chứng minh SQL injection**. Pentester có thể dùng các **test cases vô hại trong sandbox** để tìm xem input có gây thay đổi hành vi SQL không; code reviewer và database logs giúp xác minh root cause. Ngược lại, một API cho phép đọc tài liệu sai tenant có thể là lỗi nghiêm trọng **dù không có CVE hay scanner signature nào**.

## 4. Black-box pentest như một assurance activity

Một hoạt động pentest giúp đánh giá **security claim**, không chỉ sản xuất danh sách lỗi.

| Security claim | Câu hỏi black-box | Bằng chứng phù hợp |
| --- | --- | --- |
| **Unauthenticated actors không đọc dữ liệu khách hàng.** | Public endpoints có để lộ tài nguyên không? | Controlled anonymous requests và observed responses. |
| **Mọi request đều có authorization theo object và tenant.** | User A có đọc/sửa dữ liệu B qua API, export, download không? | Synthetic cross-tenant negative tests. |
| **Sessions/tokens chỉ dùng đúng scope/thời hạn.** | Revoked/expired token còn được chấp nhận? | Controlled session lifecycle tests. |
| **Input không thể thay đổi thao tác nhạy cảm trái phép.** | Validation/encoding có ngăn unsafe use trong các paths được thử? | Boundary/input tests và correlated evidence. |
| **Business workflows có kiểm soát chống abuse.** | Có thể bỏ qua bước phê duyệt hoặc replay transaction? | State-machine/role tests với dummy records. |
| **Data exports được bảo vệ.** | Link/object storage có accessible ngoài quyền? | Expiration, wrong-principal và revocation tests. |
| **Monitoring phát hiện hoạt động cần theo dõi.** | Security test events có vào audit/alerts? | SOC correlation, alert exercise và source health. |

Không một test PASS riêng lẻ nào chứng minh tất cả claim. Assurance cần nêu **population, viewpoint, account roles, paths, build/version, thời kỳ, known unknowns**.

## 5. Điều kiện tiên quyết: ủy quyền và Rules of Engagement

**Rules of Engagement (RoE)** là thỏa thuận quy định ai được phép kiểm thử những gì, bằng cách nào, trong thời gian nào và phản ứng thế nào khi có sự cố. Với black-box testing, đây là **ràng buộc kỹ thuật và pháp lý bắt buộc của phương pháp chuyên nghiệp**.

### Thông tin tối thiểu

1. **Văn bản ủy quyền:** chủ thể có quyền với hệ thống và contact được xác minh.
2. **Targets in scope:** hostnames, domains, IP ranges, cloud accounts, applications/APIs, version/environments.
3. **Explicit exclusions:** third-party infrastructure, customer data, shared production resources, sensitive services.
4. **Time window:** bắt đầu, kết thúc, timezone và maintenance constraints.
5. **Allowed methods:** passive observation, limited active checks, authenticated workflows, non-destructive validation.
6. **Prohibited methods:** ví dụ social engineering, phishing, DDoS, brute force, data exfiltration, destructive payloads, physical access nếu không cho phép.
7. **Test identities/data:** seeded accounts theo roles/tenants, synthetic records, approved canary endpoints.
8. **Rate/availability limits:** concurrency, volume, retries, stopping conditions và SLO guardrails.
9. **Incident communication:** contacts, escalation path, emergency pause, evidence/security handling.
10. **Data handling:** cách thu/ẩn danh/lưu/xóa logs, screenshots, tokens, PII và findings.
11. **Reporting/approval:** deliverables, deadlines, severity method, retest window, sign-off authority.
12. **Scope change procedure:** muốn thêm một target phải được đồng ý trước khi kiểm tra.

### Scope bằng URL không đủ

Một hostname có thể trỏ tới CDN, cloud provider, managed API hoặc tài sản vendor. Quyền kiểm thử domain của chính mình **không mặc nhiên cấp quyền kiểm thử underlying third-party services**; phải xem hợp đồng, provider policy và phần được ủy quyền.

### Dừng khi có rủi ro

Nếu thấy truy cập bất ngờ vào dữ liệu thật của khách hàng, dấu hiệu gián đoạn, khả năng thay đổi destructive state hoặc một hệ thống ngoài scope, **dừng thao tác liên quan, giữ bằng chứng tối thiểu cần thiết và thông báo đầu mối theo RoE**. Không “khai thác tiếp để xem có thể lấy được bao nhiêu”.

## 6. Kiểm soát an toàn và ethical boundary

Kỹ thuật kiểm thử có thể trông giống traffic xấu; sự khác biệt quan trọng nằm ở **quyền, mục đích, phạm vi và giới hạn tác động**.

### Quy tắc triển khai an toàn

- Chỉ thử trên targets được duyệt, tốt nhất là sandbox/staging tương đương production cho tests có khả năng biến đổi dữ liệu.
- Sử dụng **synthetic customers, tenants, invoices và credentials**, không lấy dữ liệu thật làm “mẫu minh họa”.
- Không thực hiện tải dữ liệu hàng loạt, cố tình gây cạn tài nguyên, phá hủy records hoặc cài persistence để chứng minh impact nếu không được cho phép cụ thể.
- Dùng **minimal proof of impact**: một canary resource đủ chứng minh boundary failure thay vì truy cập nhiều tài nguyên.
- Chỉ dùng test secrets và đối chiếu với incident team khi xuất hiện production secret thật.
- Không tự dùng tài khoản/thiết bị của người khác; mô phỏng attacker privileges bằng identities được cấp.
- Xác minh operator/monitoring biết traffic đến từ bài test, nhưng không tự tắt detection như cách “làm yên SOC”.
- Có quy trình tạm dừng, rollback và khôi phục cho các thao tác được phép biến đổi trạng thái.

### Những điều không được suy diễn

Không có sự cố trong lúc test không chứng minh test an toàn ở tất cả environments. Một request “read-only” vẫn có thể gây CPU/memory load lớn, tạo cache entries hoặc trigger downstream work. Người thử phải hiểu expected side effects của phương pháp trước khi thực hiện.

## 7. Xác định mục tiêu kinh doanh và security objectives

Trước khi tìm endpoint, hỏi “điều gì thực sự cần bảo vệ?”. Với Invoice SaaS:

| Asset/capability | Mục tiêu | Hậu quả nếu thất bại |
| --- | --- | --- |
| **Hóa đơn và khách hàng** | Confidentiality, integrity, tenant isolation. | Lộ/sửa dữ liệu giữa doanh nghiệp. |
| **Tài khoản và phiên đăng nhập** | Identity authenticity, session integrity. | Account takeover hoặc privilege misuse. |
| **Payments/refunds** | Transaction integrity và accountability. | Fraud, nghiệp vụ sai. |
| **Export/download** | Resource authorization và data lifecycle. | Leak file sau khi role bị thu hồi. |
| **Admin/support workflows** | Separation of duties, privileged access. | Thay chính sách, impersonation hoặc exposure lớn. |
| **API availability** | Resilience, abuse resistance. | Không xử lý giao dịch đúng SLO. |
| **Audit and telemetry** | Evidence completeness, integrity, incident readiness. | Không điều tra/kiểm soát được misuse. |
| **Integrations/vendor webhooks** | Integrity, caller authenticity, data sharing constraints. | Fake events hoặc dữ liệu đi ngoài purpose. |

### Ưu tiên theo asset và threat

Black-box testing có thời hạn. Đội kiểm thử nên ưu tiên **critical business paths, trust boundaries và security invariants**, không dành hết thời gian cho banner/header dễ kiểm chỉ vì scanner phát hiện nhanh.

## 8. Phạm vi kỹ thuật phải gắn với bề mặt truy cập

| Viewpoint | Mục tiêu mô phỏng | Dữ liệu/identity cần chuẩn bị |
| --- | --- | --- |
| **Unauthenticated external** | Khách truy cập chưa đăng nhập từ Internet. | Public hostnames/endpoints trong allowlist. |
| **Authenticated low-privilege** | User hợp lệ chỉ có quyền đọc một số objects. | Dummy Viewer account ở tenant A. |
| **Tenant administrator** | User có nhiều quyền trong một tenant, không phải platform admin. | TenantAdmin test account và data riêng. |
| **Cross-tenant comparison** | Chênh lệch quyền giữa A và B. | Paired synthetic tenants và resource IDs. |
| **API client/integration** | Partner có token/scope cụ thể. | Approved test app/token, webhook sandbox. |
| **Mobile client** | App/API flows nhìn từ thiết bị giả lập trong scope. | Test build/device và backend sandbox. |
| **Internal foothold** | Một compromised workload/network client giả định. | Chỉ nếu RoE cho phép vị trí/tài khoản này. |

**Black box không đồng nghĩa chỉ test anonymous.** Một actor với tài khoản hợp lệ có thể là threat quan trọng; cần mô tả chính xác viewpoint được cấp và cách nó ảnh hưởng kết luận.

## 9. Quy trình kiểm thử từ bên ngoài: overview

~~~mermaid
flowchart TD
    A["Authorized RoE and assurance objectives"] --> B["Scope / assets / viewpoints"]
    B --> C["Passive discovery and low-impact observation"]
    C --> D["Application and API surface mapping"]
    D --> E["Threat hypotheses and prioritization"]
    E --> F["Controlled validation on synthetic targets"]
    F --> G{"Observed security invariant violated?"}
    G -- "Yes" --> H["Minimal proof, impact and finding"]
    G -- "No / uncertain" --> I["Record limits, negative result or follow-up"]
    H --> J["Risk and remediation with owner"]
    I --> J
    J --> K["Retest approved release + evidence"]
    K --> L["Time-scoped assurance conclusion"]
    L --> M["Change triggers and continuous reassessment"]
~~~

### Ba mốc quyết định

**Trước kiểm thử:** có authority, scope, guardrails, owner, synthetic data và stop conditions.

**Trong kiểm thử:** mọi hypothesis có expected observable effect, giới hạn số request và cách ghi evidence không gây lộ dữ liệu.

**Sau kiểm thử:** phát hiện cần technical validation, risk assessment và remediation; kết quả “không khai thác được trong scope đã thử” phải có limitations.

## 10. Lập test charter theo threat hypotheses

Không nên bắt đầu bằng “chạy mọi công cụ trên mọi host”. Hãy viết **test charter**: một giả thuyết bảo mật có liên kết tới security requirement và hành vi quan sát được.

### Mẫu charter

| Trường | Nội dung cần có |
| --- | --- |
| **Charter ID** | Mã duy nhất cho đợt/nhánh kiểm thử. |
| **Business capability** | API đọc hóa đơn hoặc export files. |
| **Security invariant** | Principal chỉ truy cập objects trong tenant/quyền. |
| **Threat actor view** | Authenticated Viewer của tenant A. |
| **Preconditions** | Tạo synthetic tenants A/B, invoices riêng. |
| **Allowed surfaces** | Approved API endpoints và download service. |
| **Test technique** | Object-level negative tests, state/role variations. |
| **Expected outcome** | Deny/404 theo contract, không lộ dữ liệu B, audit thích hợp. |
| **Evidence** | Redacted request/response, actor, resource, version, timestamp. |
| **Stop condition** | Unexpected real customer data hoặc service impact. |
| **Owner & reviewer** | Tester, service owner, AppSec, risk assessor. |

### Threat hypothesis mẫu

**H-BOLA-01:** “Một authenticated user thuộc tenant A có thể đoán hoặc biết resource identifier thuộc B, và một API path có thể không kiểm tra tenant ownership.” Đây là **giả thuyết**, không phải confirmed vulnerability. Test chỉ được phép xác minh với **synthetic resources** đã được cấp.

## 11. Khám phá tài sản và interface trong phạm vi cho phép

Một black-box tester nhìn hệ thống từ ngoài và xác lập bản đồ:

- Hostnames và DNS records thuộc scope đã ủy quyền.
- Public website routes, API endpoints, authentication flows.
- Các client entry points: browser, mobile, partner integrations.
- Response metadata như content type, redirect, cache behavior.
- API versions, public documentation, OpenAPI nếu được cung cấp công khai.
- WebSocket, GraphQL, file uploads/downloads, webhooks theo test charter.
- Error paths, alternate environments được xác định đúng scope.
- Third-party endpoints có kết nối, nhưng **không kiểm thử trực tiếp** nếu ngoài quyền.

### Asset attribution cần kiểm tra

Một subdomain hoặc hostname phát hiện được không tự là asset được phép kiểm. Trước active validation cần xác minh **ownership, environment, provider boundaries và scope authorization**.

### Đầu ra

Lập **surface register** với endpoint/resource, viewpoint, authentication requirement, expected action, data class, exposure, host/service owner, evidence và trạng thái “được phép test”. Đây là điểm nối từ **discovery → risk-based test selection**.

## 12. Passive discovery và active testing có sự khác biệt

| Khía cạnh | Passive observation | Active interaction |
| --- | --- | --- |
| **Phương pháp** | Đọc tài liệu công khai, thông tin đã phê duyệt, metadata hoặc logs có sẵn. | Gửi các requests/checks tới hệ thống trong scope. |
| **Lợi ích** | Ít ảnh hưởng hệ thống, hiểu mặt ngoài. | Kiểm tra hành vi thực và effectiveness. |
| **Giới hạn** | Thông tin cũ/không đầy đủ, không chứng minh behavior. | Có thể kích hoạt side effects, rate limits hoặc outages. |
| **Bảo đảm** | Xác minh nguồn, attribution và tính mới. | Ủy quyền, rate/volume/target limits, monitoring và stop rules. |

### Lưu ý

Ngay cả một active request thông thường cũng có thể thay đổi audit logs, counters hoặc session state. Các hoạt động như enumeration số lượng lớn, password spraying, stress/load tests, exploit chains hoặc ghi/xóa dữ liệu phải được **phê duyệt riêng** nếu chương trình cho phép; không mặc định là thao tác “nhẹ”.

## 13. Khám phá ứng dụng web và API theo hành trình người dùng

Black-box testing hiệu quả khi đi theo **business workflows**, không chỉ dựa vào danh sách URL.

### Ví dụ hành trình Invoice SaaS

1. Người dùng mở trang login/federation.
2. Hoàn tất authentication và chọn tenant/session context.
3. Truy cập danh sách hóa đơn, tìm kiếm, xem chi tiết.
4. Tạo invoice hoặc sửa trạng thái theo role.
5. Gửi yêu cầu export.
6. Hệ thống tạo job bất đồng bộ.
7. Người dùng xem trạng thái job và tải file.
8. Admin đổi role hoặc thu hồi quyền.
9. Audit hiển thị các action quan trọng.

Với mỗi bước cần ghi **entry point, input, identity context, resource, authorization decision, response, side effect, data recipients và error behavior**. Phần sau của bài biến những yếu tố này thành test cases về authentication, authorization, workflow integrity và data protection.

### Một bản đồ tối thiểu

| Action | Interface | Actor | Protected resource | Test emphasis |
| --- | --- | --- | --- | --- |
| Login | Browser/IdP callback | Unauthenticated/IdP | Session | Federation, redirect, token/session binding. |
| Read invoice | GET API | Viewer | Invoice object | BOLA, tenant isolation, error disclosure. |
| Update invoice | PUT/PATCH API | Accountant | Invoice state | Function-level AuthZ, mass assignment, integrity. |
| Submit export | POST API | Authorized user | Export job | Scope of job, rate, replay, background permissions. |
| Download file | GET download | Job owner | Export artifact | Authorization, expiry, storage capability. |
| Modify user role | Admin API | TenantAdmin | Tenant user/permissions | BFLA, privilege escalation, audit. |
| Webhook event | Partner callback | External integration | Transaction state | Authenticity/replay and side-effect integrity. |

Không kết luận API an toàn chỉ vì UI không hiển thị button; **server-side controls** phải thực thi với requests phù hợp.

## 14. Authentication: đánh giá điều kiện tạo danh tính đáng tin

Một người kiểm thử hộp đen có thể quan sát **login, account recovery, step-up authentication và API token usage** từ bên ngoài mà không thấy mã nguồn xác thực.

### Những câu hỏi quan trọng

- Có đường truy cập quan trọng nào không đòi login dù tài liệu nói cần?
- Session được tạo khi nào, gắn với principal/tenant/IdP nào?
- Tài khoản bị disable hoặc credential bị revoke có còn tạo session mới?
- Login, logout, recovery và enrollment có nhất quán giữa web/mobile/API?
- Có thể sử dụng session trước xác thực sau khi login không (*session fixation*)?
- Tác vụ nhạy cảm có đòi **step-up** khi policy yêu cầu?
- Error responses có tiết lộ account tồn tại hay trạng thái nội bộ quá mức?
- Authentication rate/abuse protections có phù hợp business và availability?

### Kết quả cần phân biệt

Một response “401 Unauthorized” cho anonymous request có thể đáp ứng một assertion của login requirement, **nhưng không chứng minh toàn bộ authentication lifecycle an toàn**. Ngược lại, nếu user có session hợp lệ, test tiếp theo là **authorization**, không gọi đó là “bypass login” chỉ vì tìm được quyền vượt phạm vi.

### Khung kiểm thử an toàn

Dùng **test accounts** được cung cấp, thử login/invalid state, session expiry hoặc revoked session theo kịch bản phê duyệt. Không thực hiện credential stuffing, password spraying hoặc dùng tài khoản thật của người khác nếu không có thỏa thuận và kiểm soát riêng.

## 15. Session management và vòng đời token

Một session có thể được biểu diễn bằng cookie, bearer token hoặc nhiều credentials phối hợp. Black-box tester đánh giá **hành vi thực** của hệ thống trước các thay đổi session.

| Scenario | Expected theo policy | Điều không nên suy ra |
| --- | --- | --- |
| Session hết hạn | API từ chối hoặc yêu cầu reauthentication theo contract. | Một endpoint từ chối nghĩa là mọi endpoint khác đều đúng. |
| User logout | Session/refresh capabilities bị xử lý theo approved semantics. | Xóa cookie client đồng nghĩa backend credential vô hiệu ngay. |
| Role revoke | Quyền nhạy cảm thay đổi trong cửa sổ được phê duyệt. | JWT còn hạn nhất thiết phải chấp nhận quyền cũ. |
| Tenant switch | Session context/claims khớp tenant được cấp quyền. | Frontend dropdown là security boundary. |
| New device/session | Binding/notifications đúng policy. | Device string khó đoán chứng minh strong device binding. |
| Refresh token use | Chỉ đúng client/scopes, xử lý replay/rotation theo design. | Một token không truy cập API nào nghĩa là refresh flow an toàn. |
| Idle/absolute timeout | Timeout được thực thi ở server và APIs. | UI redirect thay token revocation ở backend. |

### Một thử nghiệm hợp lệ

Trong sandbox, tester tạo session bằng account A, dùng một endpoint đọc canary resource được phép, sau đó owner thu hồi role của A. Tester lặp lại thao tác có thời gian giới hạn để kiểm tra **policy revocation window** đã thỏa hay chưa. Kết quả phải ghi **clock synchronization, cache propagation, request identity và exact API path**.

### Cookie và browser attributes

Quan sát Secure, HttpOnly, SameSite, Domain, Path, rotation và session identifiers khi phù hợp; nhưng **chỉ nhìn flags không đủ kết luận chống CSRF/XSS/session abuse**. Cần xét cookie có được browser gửi trong contexts nào và server có bảo vệ state-changing actions.

## 16. Object-level authorization: BOLA và tenant isolation

**Broken Object Level Authorization (BOLA)** là nhóm lỗi khi server không xác minh **principal có quyền với object cụ thể**. Đây là mối nguy điển hình của SaaS multi-tenant: một user đã xác thực ở tenant A có thể gửi identifier của tenant B.

### Bộ fixture an toàn

- **Tenant A:** user A-Viewer, A-Accountant và invoice A-001.
- **Tenant B:** user B-Viewer và invoice B-001.
- Các IDs/records hoàn toàn giả lập, do owner tạo và cleanup theo RoE.
- Tester chỉ sử dụng **documented test endpoints** nằm trong scope.

### Mô hình kết quả

| Principal | Object | Action | Expected |
| --- | --- | --- | --- |
| A-Viewer | A-001 | READ | ALLOW nếu user thuộc phạm vi quyền. |
| A-Viewer | B-001 | READ | DENY, không lộ dữ liệu B. |
| A-Viewer | A-001 | UPDATE | DENY nếu Viewer không có quyền sửa. |
| A-Accountant | A-001 | UPDATE | ALLOW nếu policy, trạng thái và ownership hợp lệ. |
| B-Viewer | A-001 | READ | DENY, không lộ dữ liệu A. |
| Anonymous | A-001 | READ | DENY. |

### Điều cần quan sát

Không chỉ HTTP status. Một request có thể trả 403 nhưng **job đã được tạo**, message đã vào queue, cache đã bị điền, e-mail đã gửi hoặc file output vẫn được phép tải qua đường khác. Với risk cao, cần **side-effect verification bằng test data** và correlation từ API tới downstream theo phạm vi được duyệt.

### Kết luận có điều kiện

Một bài test phủ một endpoint và hai objects không chứng minh toàn bộ tenant isolation. Đánh giá phải ghi **API family, object types, roles, HTTP methods, export/download/caches, environment, build và scope được kiểm**.

## 17. Function-level authorization: BFLA và phân quyền nghiệp vụ

**Broken Function Level Authorization (BFLA)** liên quan chức năng mà principal không được phép thực hiện, ví dụ user Viewer truy cập một API chỉ dành cho TenantAdmin.

### Test matrix

| Function | Viewer | Accountant | TenantAdmin |
| --- | --- | --- | --- |
| Read invoice trong tenant | Theo scope | Theo scope | Theo scope |
| Create/update invoice | Deny | Allow theo policy | Theo policy |
| Manage users/roles | Deny | Deny | Allow trong tenant |
| Read platform-wide audit | Deny | Deny | Deny nếu không có platform role |
| Export bulk confidential data | Tùy policy có thể Deny | Theo entitlement | Theo entitlement |

Những ví dụ là **policy giả định**, không phải mọi SaaS đều có cùng role model. Reviewer phải xác minh matrix với owner và kiểm tra results theo từng chức năng.

### Giao diện không phải kiểm soát

Không thấy nút “Manage users” trên UI của Viewer **không chứng minh endpoint đã được bảo vệ**. Kiểm thử được ủy quyền nên gửi các **role-appropriate negative requests trên sandbox** và quan sát server decision.

### Cross-role và cross-tenant

TenantAdmin của A có thể được phép quản lý users thuộc A nhưng không được tạo role trong B. Một generic “admin=true” claim ở backend là dấu hiệu cần kiểm tra scope; tuy nhiên chỉ có thông tin từ black box thì phải ghi **observed behavior**, chưa chắc root cause là claim mapping.

## 18. Mass assignment và business data integrity

**Mass assignment** có thể xảy ra khi server vô tình cho phép request body ảnh hưởng các thuộc tính mà actor không có quyền sửa: tenantId, isAdmin, invoiceApproved, paymentStatus hoặc ownerId.

### Thiết kế phép thử với synthetic records

1. Chọn một business action được phép, chẳng hạn cập nhật invoice note trong tenant A.
2. Ghi rõ field nào **được phép** thay đổi theo approved schema/policy.
3. Chuẩn bị test request có **trường không được phép thay đổi** ở fixture sandbox.
4. Quan sát response và **readback state** qua đường được cấp quyền.
5. Xác nhận các thuộc tính protected không đổi, audit ghi decision phù hợp.

### Điều cần phân biệt

Server bỏ qua unknown field hoặc trả validation error có thể là outcome đúng, nhưng vẫn phải xác minh side effects. Một PATCH endpoint cho phép thay mọi field có thể là đúng với một privileged administrator nhưng sai với Viewer/Accountant.

### Requirement minh họa

**REQ-INT-04:** “Chỉ role được phê duyệt mới được thay invoice approval state; giá trị owner/tenant bắt nguồn từ server context và không bị thay bởi request payload của user thường.”

Black-box negative tests phải đo **readback business state**, không chỉ sự xuất hiện/biến mất của thông báo “Save successful”.

## 19. Business workflow abuse và state-machine testing

Nhiều lỗ hổng không dựa vào injection hay CVE; chúng dựa vào thứ tự bước nghiệp vụ:

- Bỏ qua phê duyệt trước khi hoàn tiền.
- Gửi lại cùng yêu cầu dẫn đến giao dịch trùng.
- Dùng invitation token sau khi đã thu hồi.
- Thay role giữa lúc tạo export và lúc download.
- Thực hiện action ở trạng thái nghiệp vụ không hợp lệ.
- Tái sử dụng dữ liệu phiên đã kết thúc để truy cập hành động nhạy cảm.

### Lập state machine trước khi test

~~~mermaid
stateDiagram-v2
    [*] --> Draft
    Draft --> Submitted: Owner submits
    Submitted --> Approved: Authorized reviewer approves
    Submitted --> Rejected: Authorized reviewer rejects
    Approved --> Paid: Payment confirmed
    Rejected --> Draft: Owner revises
    Paid --> [*]
    note right of Approved
      Direct Draft-to-Paid transitions
      are forbidden by this example policy
    end note
~~~

### Câu hỏi của black-box tester

Một actor hợp lệ có tạo ra **transition không nằm trong policy** không? Một state change có được ghi chỉ một lần không? Audit actor/action/data có đầy đủ? Nếu có race/retry, hệ thống có idempotency và reconciliation không?

### Thử nghiệm an toàn

Chỉ dùng transaction test, amounts/IDs giả và hệ thống sandbox. Các kịch bản concurrency/load phải được owner cho phép, tránh cố gây tranh chấp hoặc gián đoạn trên dữ liệu tài chính thật.

## 20. Input validation, output encoding và injection hypotheses

Hộp đen cho phép quan sát server xử lý các **giá trị biên, encoding, kiểu dữ liệu và phản hồi lỗi** ra sao. Nhưng không nên thử các payload phá hoại hoặc phức tạp trên production không được ủy quyền.

### Các nhóm rủi ro

| Nhóm | Security hypothesis | Cách kiểm chứng an toàn |
| --- | --- | --- |
| **SQL/NoSQL injection** | Input có thể thay đổi logic truy vấn. | Dùng fixture sandbox, boundary values; kiểm tra query behavior/logs qua owner. |
| **XSS** | User content được diễn giải như code/markup ngoài ý định. | Harmless test strings và DOM/text rendering observation. |
| **Command injection** | Input trở thành process command/arguments trái phép. | Kiểm tra contract và canary stubs được owner dựng. |
| **Path traversal** | Client kiểm soát filesystem/storage reference ngoài allowed scope. | Synthetic files, server-owned path IDs, denied access verification. |
| **Template injection** | Input ảnh hưởng template execution thay vì data. | Safe template fixtures và bounded rendering tests. |
| **Deserialization** | Input kích hoạt types/side effects không được phép. | Known harmless schema-invalid input và resource guardrail checks. |
| **Header/response injection** | Input thao túng HTTP header/caching behavior. | Test values giới hạn trong sandbox, response inspection. |
| **XML/external references** | Parser có thể resolve resources trái policy. | Bounded parser fixtures, không truy cập internal resources thật. |

### Một bất biến tốt hơn khẩu hiệu

Thay vì “ứng dụng phải không có SQL injection”, có thể viết: “HTTP query parameters phải được xử lý như **dữ liệu**, không thay cấu trúc truy vấn hoặc vượt tenant scope; tất cả read operations trả đúng authorized rows.” Điều này nối negative testing với security requirement và bảo vệ cả khi công nghệ DB thay đổi.

### Phản hồi lỗi có thể gây hiểu lầm

HTTP 500 không đủ là evidence cho injection; HTTP 200 cũng không đủ chứng minh an toàn. Phải tìm **observable security property violation hoặc evidence backend được owner cung cấp**, nêu phương pháp và giới hạn.

## 21. SSRF, external callbacks và network trust boundaries

Một SaaS cho phép cấu hình webhook destination có thể tạo rủi ro khi server phát network request đến địa chỉ do user chỉ định. Từ black-box view, tester quan sát **destination registration, verification, redirect policy, response và egress behavior**.

### Hypotheses cần xét

- Một tenant có thể đăng ký destination ngoài approved domains hoặc scheme?
- Destination đã đăng ký có được ràng buộc với owner/tenant?
- Có thể đổi redirect target sau khi kiểm tra policy?
- Egress có giới hạn access tới restricted internal network hoặc control-plane endpoints?
- Response/error có lộ server-side metadata hoặc dữ liệu thuộc hệ thống?
- Có bảo vệ chống recursion, queue storms và request replays?

### Cách dựng test đúng

Sử dụng **canary HTTP endpoints do tổ chức kiểm soát** trong môi trường kiểm thử, bao gồm một endpoint “allowed” và một endpoint “forbidden” mô phỏng policy. Không dùng metadata service, private hosts hoặc tài sản bên thứ ba thật để “thử SSRF” nếu không có quyền riêng.

### Hướng assurance

Gắn kết quả black-box với effective egress/IAM policies và code/config review khi có thể. Black-box không quan sát thấy một request tới canary có thể do firewall, timeout hoặc test setup sai; phân biệt **blocked by security control** với **inconclusive**.

## 22. Browser security: CSRF, CORS và clickjacking

Đây là nhóm controls thường có thể quan sát từ browser/session nhưng cần **context** để tránh kết luận vội.

### CSRF

**Cross-Site Request Forgery (CSRF)** có nguy cơ khi browser tự gửi credentials tới state-changing endpoint, trong khi server không có cơ chế xác định request được khởi tạo từ context được phép.

Reviewer cần xem **cookie authentication, SameSite behavior, anti-CSRF tokens, Origin/Referer validation nếu áp dụng, request methods và business side effects**. Các phép thử phải dùng test identities/records, không kích hoạt state changes thật.

### CORS

**Cross-Origin Resource Sharing (CORS)** là chính sách browser cho phép client-side script đọc response giữa origins trong một số điều kiện. Header CORS “rộng” không tự chứng minh dữ liệu đã lộ nếu response không chứa nhạy cảm/credentials context khác nhau; ngược lại, CORS không thay server authorization.

### Clickjacking

Xem X-Frame-Options hoặc Content-Security-Policy frame-ancestors và behavior của sensitive UI trong trình duyệt test. Một response header có mặt nhưng sai context hoặc chỉ áp một route chưa chứng minh toàn bộ UI không thể bị nhúng trái policy.

### XSS

Black-box quan sát hành vi render input trong DOM/output contexts. Test nên dùng chuỗi dữ liệu vô hại, không thực thi script nguy hiểm hoặc thu cookies; phối hợp source review/encoding tests để chứng minh root cause và fix.

## 23. API misuse: methods, versions, schemas và alternate routes

Một hệ thống có nhiều endpoints tương đương: REST API v1/v2, GraphQL operations, file service, mobile API, admin route hoặc legacy callback. Kiểm thử chỉ một route rồi kết luận chung sẽ bỏ những **đường enforcement không đồng nhất**.

### Surface coverage

| Dimension | Biến thể cần xem | Rủi ro |
| --- | --- | --- |
| **HTTP methods** | GET/POST/PUT/PATCH/DELETE phù hợp API contract. | Mutating action không kiểm tra quyền. |
| **API versions** | v1, v2, legacy/mobile/partner paths được phép. | Control mới chỉ có ở v2. |
| **Object identifiers** | URL params, query, body, nested IDs. | BOLA trong nested resources. |
| **Bulk actions** | Single object và bulk import/export. | Bulk path bỏ validation hoặc quota. |
| **GraphQL** | Query/mutation/schema resolver boundaries. | Resolver-level object authorization thiếu. |
| **Files** | Direct download, signed URL, CDN, preview. | Capability bypass quyền/session. |
| **Async** | Submit/status/cancel/result/download. | Job owner kiểm không đồng bộ. |
| **Error paths** | Not found, revoked, expired, timeout. | Data leak, fallback trái policy. |

### Không dùng HTTP status làm bằng chứng duy nhất

Một endpoint trả 404 cho wrong tenant có thể là thiết kế đúng để không tiết lộ resource existence. Nhưng nếu response body, pagination total hoặc timing/metadata giúp suy ra dữ liệu thuộc tenant khác, có thể còn leakage. Việc khai thác side channel phải nằm trong test charter và giới hạn an toàn.

## 24. Rate limiting và abuse resistance

Đánh giá abuse controls không nhất thiết cần stress test hoặc brute force. Có thể kiểm tra **giới hạn hợp lý trong sandbox** với rate/volume được RoE cho phép:

- Tài nguyên nào cần quota theo user, tenant, token, IP hay endpoint?
- Retry/backoff và bulk export có hạn chế request/work queue phù hợp?
- Authentication lockout có tránh gây account DoS cho user hợp lệ?
- API error/limit behavior có nhất quán giữa routes không?
- Abuse detection/alerts có signal khi test canary đạt ngưỡng?
- Có bypass do nhiều identities, API versions hoặc background tasks?

### Phân biệt test và load testing

Black-box pentest có thể kiểm tra **policy logic và response behavior** của rate controls, nhưng không mặc nhiên có quyền bắn lượng request lớn để chứng minh khả năng DoS. Kiểm tra capacity/availability ở tải cao cần **riêng một kế hoạch performance/resilience được duyệt** với emergency stop.

### False conclusions

Không nhận 429 trong 10 requests không tự chứng minh rate limit thiếu; policy có thể đặt ngưỡng cao hơn. Nhận 429 cũng không đủ chứng minh chống mọi phân tán abuse. Cần đọc contract/monitoring và báo đúng **window đã thử**.

## 25. Async jobs, queue và export/download

Đây là vùng có nhiều **trust boundaries** mà black-box tester không nhìn thấy trực tiếp nhưng có thể suy từ public behavior.

~~~mermaid
flowchart LR
    A["Authenticated tenant A user"] --> B["Export API"]
    B --> C[("Job queue")]
    C --> D["Export worker"]
    D --> E[("Shared tenant database")]
    D --> F[("Private export storage")]
    A --> G["Download/status service"]
    G --> F
    X["Tenant B dummy invoice"] --> E
    B -. "Server-owned job authorization" .-> D
    G -. "Per-user / per-resource access" .-> F
~~~

### Black-box hypotheses

1. User A có thể tạo job trên resource B không?
2. Một user khác có thể xem **job status/metadata** của A không?
3. Job ID có bị coi là đủ quyền để tải file?
4. Sau revoke role, một job đã tạo có thể tiếp tục/tải thế nào theo requirement?
5. Signed link có expire/revoke theo **capability semantics được duyệt**?
6. Retry/replay có tạo nhiều side effects hoặc bypass quota không?
7. Khi job fail, error messages có tiết lộ object IDs/records không?
8. Có route khác như storage/CDN preview bỏ qua download authorization?
9. Audit có liên kết actor→job→file→download không?

### Kết quả cần kiểm qua side effects

Ví dụ, một request tạo export job sai quyền trả 403; tester cần phối hợp owner kiểm tra **không có job/file trong synthetic tenant B**. Không được xem 403 là PASS nếu worker vẫn chạy sai.

### Hạn chế của black box

Tester không có quyền nhìn queue/DB không thể chứng minh hoàn toàn side effects không xảy ra. Có thể ghi **BLACK-BOX OBSERVATION PASS at API boundary; downstream UNKNOWN** và yêu cầu owner cung cấp log/DB reconciliation hoặc white-box follow-up.

## 26. Tenant context, caching và indirect data leakage

Trong multi-tenant SaaS, một API có thể enforce tenant filter đúng trên DB, nhưng cache, search index, export links hoặc analytics layer dùng keys thiếu tenant scope.

### Câu hỏi cần thử

- Cùng một resource identifier có thể xuất hiện trong cache của hai tenants không?
- Pagination, search suggestions hoặc autocomplete có hiển thị metadata tenant B?
- File preview có truy cập khác với download final không?
- Audit/report export có lọc đúng tenant và role?
- Resource update có làm sai object state ở tenant khác qua shared background job?
- Cơ chế chuyển tenant có bỏ session/cache context cũ?

### Phân biệt một hiện tượng với nguyên nhân

Nếu A nhận metadata B sau khi đổi tenant trong sandbox, có thể là **cache key collision, stale context, broken authorization hoặc data indexing bug**. Black-box finding nên mô tả **observable violation và impact**; root cause chỉ là giả thuyết cho đến khi có evidence code/config.

### Yêu cầu assurance

Định nghĩa **no-cross-tenant-data** ở mọi output: body, headers, exports, caches, notifications, analytics và indirect API responses. Không dựa vào việc ID “khó đoán” như một authorization control.

## 27. Account recovery, invitation và thay đổi đặc quyền

Những chức năng không dùng hằng ngày thường tạo lỗ hổng vì **các quy tắc quyền và tính hợp lệ của token khác login chính**:

- Reset password, recover account, enroll/recover MFA.
- Email verification, account invitation, tenant joining.
- API key creation/rotation và delegated access.
- Role assignment, ownership transfer, temporary support access.
- Session termination và identity unlink/relink.

### Charter mẫu

**Security requirement:** “Một invitation token chỉ có thể sử dụng trong scope tenant, identity và thời hạn được duyệt; việc chấp nhận invitation không tự nâng quyền vượt policy.”

**Test viewpoint:** hai test accounts thuộc tenant A/B, một invitation từ A đến test identity đã xác định.

**Expected:** dùng đúng context thành công một lần theo business semantics; wrong tenant, revoked hoặc expired invite phải bị từ chối và không tạo quyền mới. **Observed:** UI/API decision và actual role state qua authorized owner readback.

### Những điểm không được bỏ qua

Một URL chứa token có thể được chia sẻ qua browser history, referrer hoặc logs. Không có lỗi chỉ vì token nằm trong link nếu hệ thống dùng one-time, short-lived, scoped capability với controls phù hợp; reviewer phải đánh giá **hành vi, context và residual risk**, không gắn nhãn chỉ từ hình thức.

## 28. Federation, identity providers và multi-origin trust

Một tổ chức SaaS có thể hỗ trợ đăng nhập qua nhiều customer IdPs. Black-box tester có thể nhìn thấy **redirect flow, session binding, account linking và error behavior**, nhưng thường cần gray-box assistance từ test IdP để kiểm tra sâu federation.

### Ranh giới cần mô hình

| Ranh giới | Security invariant | Observable test |
| --- | --- | --- |
| Browser → RP | Session gắn đúng authenticated user. | Controlled login/logout và session switch. |
| RP ↔ IdP | Request/response có transaction binding, issuer/audience đúng. | Approved test IdP/issuer scenarios. |
| Identity → tenant account | Subject identity không chỉ dựa email có thể trùng. | Paired same-email test identities khác issuer/subject. |
| Account → roles | Role mapping thuộc tenant và policy được duyệt. | Cross-tenant authorization negative tests. |
| Session → API token | Audience/scope phù hợp resource server. | Controlled token scope mismatch tests. |
| Recovery → authenticated account | Recovery không tự tạo đường yếu hơn main login. | Revocation/re-enrollment flows trong sandbox. |

### Không tự thao tác với live customer IdPs

Những thử nghiệm thay claims, signatures, federation metadata hoặc redirect endpoints cần **test IdP được kiểm soát và RoE rõ**. Không gửi request bất thường tới nhà cung cấp danh tính của khách hàng ngoài thỏa thuận.

### Giới hạn của kết luận

Một successful login chứng minh một luồng hợp lệ vận hành được, **không chứng minh toàn bộ các issuer, accounts, roles, expired/replayed tokens hoặc account-linking cases đã an toàn**.

## 29. Mobile và client-side viewpoint

Ứng dụng mobile là một **client** của backend, không tự là ranh giới authorization của server. Black-box testing có thể quan sát:

- Login/session storage và token lifecycle ở test device.
- Các API calls thực, kể cả hidden/alternate endpoints.
- Behavior khi app offline, reconnect hoặc chuyển account/tenant.
- Insecure deep links và link-handling flows trong scope.
- Exposure của sensitive data trong notifications, caches hoặc clipboard khi policy liên quan.
- Cơ chế certificate validation và request routing ở test build, với phương pháp được phê duyệt.

### Lỗi tư duy thường gặp

“Mobile app không có chức năng đổi role” không có nghĩa backend role-change endpoint chặn user thường. “App chỉ gọi API qua TLS” không chứng minh token lưu an toàn ở thiết bị hoặc server authorization đúng.

### Evidence đúng

Gắn test với **app version/build, OS/device profile, account role, environment và backend release**. Một kết quả trên debug build có cấu hình đặc biệt không tự áp dụng cho production binary.

## 30. Internet-facing cloud và infrastructure surface

Black-box tester có thể quan sát một số network/web behaviors từ một vantage point, nhưng không nhìn được toàn bộ IAM, VPC, Kubernetes hoặc cloud control plane.

### Các lớp quan sát

| Lớp | Quan sát có thể có theo scope | Cần evidence bổ sung để kết luận sâu |
| --- | --- | --- |
| **DNS/routing** | Domain/redirect, public endpoints được cấp quyền. | Ownership, hidden/internal routes, DNS lifecycle. |
| **TLS** | Certificate chain, supported protocol theo approved tests. | Internal mTLS, private key custody, rotation controls. |
| **HTTP ingress** | Headers, redirects, auth behavior, caching. | Gateway policies, WAF scope, direct-to-origin bypass. |
| **CDN/object delivery** | Authorized download/expiry/anonymous access. | Effective bucket IAM, signing key, lifecycle. |
| **Public admin endpoint** | Có reachable hoặc challenged by authentication? | Backend role authorization, actual admin permissions. |
| **Network service** | Service presence/version candidate, limited behavior. | Patch applicability, internal segmentation, vulnerabilities. |
| **Cloud shared responsibility** | Public behavior của managed service. | Provider responsibility và customer configuration. |

### Ràng buộc của active network checks

Không tự mở rộng từ hostname được giao sang IP của CDN/provider, hoặc thử high-volume probes ngoài quota. Chỉ dùng **limited service checks** theo RoE, có asset owner và stop condition.

### Sai lầm về banner

Một service banner tiết lộ phiên bản không tự chứng minh phiên bản thực/patch state (có thể có backport). Ngược lại, xóa version banner không vá lỗ hổng. Cần kết hợp advisories, build inventory và effective configuration review khi phù hợp.

## 31. Logging, detection và incident response trong pentest

Một security control có thể **ngăn** truy cập nhưng không tạo được audit trail, hoặc **phát hiện** thao tác bất thường nhưng không ngăn data disclosure. Black-box pentest có thể đánh giá hai lớp qua test events.

### Cách đánh giá có kiểm soát

1. Tạo một security-relevant test action trên synthetic account/resource.
2. Ghi thời điểm, correlation ID, actor, request category, expected alert.
3. Chủ hệ thống/SOC tìm event qua authorized observability tools.
4. Xác nhận source, ingestion lag, fields cần thiết, redaction và retention.
5. Nếu có alert, xem severity/routing, người nhận và response playbook.
6. Nếu không có event, phân biệt **test không đi qua control**, **collector gap**, **rule gap** hay **latency**.

### Test limits

“Không thấy alert” không chứng minh chắc hệ thống thiếu detection nếu charter không nêu detector kỳ vọng. “Có alert” không chứng minh mọi attacks cùng loại sẽ được phát hiện; cần biết rule match conditions và false negative space.

### Audit privacy

Không để full invoice content, passwords, secrets hoặc session tokens đi vào logs chỉ để tăng evidence. Audit nên đủ attribution, action, resource reference và security decision nhưng bảo vệ dữ liệu theo policy.

## 32. Hướng tiếp cận dựa theo threat model và attack paths

Một black-box tester có thể sử dụng threat model để chọn test cases, nhưng vẫn giữ **góc nhìn quan sát bên ngoài** khi thu bằng chứng.

### Ví dụ attack-path hypothesis

**Mục tiêu của actor:** user A đọc file export của tenant B.

**Bước có thể tồn tại:** account hợp lệ ở A → biết job/resource identifier B → gọi job status → nhận download reference → tải file.

**Controls cần kiểm:** object/tenant authorization ở status endpoint, download service, storage capability; binding giữa job và principal; expiry và access logging.

### Các nhánh cần nghĩ tới

~~~mermaid
flowchart TD
    A["Tenant A test account"] --> B["Attempt authorized negative read of B's canary job"]
    B --> C{"Status metadata exposed?"}
    C -- "No" --> D["Status boundary passed in tested case"]
    C -- "Yes" --> E["Potential cross-tenant metadata disclosure"]
    B --> F["Attempt wrong-principal download in test"]
    F --> G{"File contents accessible?"}
    G -- "No" --> H["Download boundary passed in tested case"]
    G -- "Yes" --> I["Confirmed canary file disclosure"]
    E --> J["Minimal evidence + risk review"]
    I --> J
    D --> K["State scope and untested paths"]
    H --> K
~~~

**Kết quả không bị khai thác trong một đường** chỉ hỗ trợ claim cho đường đó. Không suy ra alternative routes/administrative paths đã an toàn nếu chúng không thuộc bài test.

## 33. Tác động kết hợp: từ một finding nhỏ thành business risk

Một finding “user A nhìn thấy job ID của B” có thể chỉ là metadata leakage trong một scope; nhưng nếu job ID dùng như bearer capability để download, hậu quả có thể là file disclosure. **Impact là kết quả của hành vi quan sát**, không phải độ “thú vị” của giả thuyết.

### Phân loại chuỗi kết quả

| Giai đoạn | Evidence | Diễn giải |
| --- | --- | --- |
| **Observation** | Status response có identifier của B. | Có khả năng data leakage nếu identifier được bảo vệ. |
| **Hypothesis** | Identifier có thể dùng gọi download. | Chưa xác nhận. |
| **Controlled validation** | Synthetic B file được trả cho A qua authorized test. | Có bằng chứng cross-tenant file disclosure trong test scope. |
| **Business impact** | File chứa Confidential invoice giả; production path có cùng control? | Cần xác minh scope equivalence/actual severity. |
| **Root cause** | Có thể là missing authz hoặc capability scope. | Chỉ kết luận sau code/config/effective policy evidence. |

### Tránh overclaim

Nếu chỉ có metadata identifier, không tự viết “attacker có thể tải mọi files của mọi khách hàng”. Ghi observed result, affected resource type, necessary conditions, tested sample size và uncertainty.

## 34. Bằng chứng black-box: khả năng tái hiện và độ tin cậy

Một finding cần đủ thông tin để kỹ sư **tái hiện hợp pháp và sửa đúng**, đồng thời không làm rò dữ liệu nhạy cảm.

### Evidence package tối thiểu

| Trường | Nội dung |
| --- | --- |
| **Engagement ID / RoE** | Mã ủy quyền, mục tiêu, time window, permitted actions. |
| **Target/service** | Host/API/module và version/environment trong scope. |
| **Actor context** | Anonymous hoặc synthetic account role/tenant, không lưu credential thô. |
| **Request context** | Method/path/parameters đã ẩn bí mật, correlation ID. |
| **Expected outcome** | Requirement, policy hoặc authorization matrix. |
| **Observed outcome** | Status, response data class/canary marker, side effect có bằng chứng. |
| **Preconditions** | Test fixture, state, role, runtime version, time. |
| **Impact proof** | Minimal proof trên dữ liệu giả, không bulk exfiltration. |
| **Scope/limitations** | Paths, accounts, versions đã/ chưa thử, environment differences. |
| **Reviewer/owner** | Người xác minh, remediation owner và risk owner. |
| **Evidence storage** | Nơi lưu an toàn, provenance, integrity, retention. |

### Tính tái lập

Một kết quả chỉ xuất hiện một lần có thể liên quan race, cache, stale session, propagation hoặc môi trường. Có thể thử lại **trong giới hạn RoE**, ghi deterministic fixtures/time và phân tích sự không ổn định. Không lặp vô hạn để “phải thành công” nếu gây tải hoặc ngoài thỏa thuận.

### Evidence mâu thuẫn

Nếu tester thấy file leak ở staging nhưng production owner nói storage policy khác, cần đánh giá **environment equivalence và deployment manifest**. Không tự áp kết luận staging lên production; cũng không bỏ finding chỉ vì production chưa được phép kiểm thử.

## 35. False positive, false negative và kết quả chưa đủ căn cứ

Black-box pentest thường sinh **observations/hypotheses**. Cần phân biệt trạng thái:

| Status | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **CONFIRMED** | Có bằng chứng security requirement bị vi phạm trong scope. | User A đọc synthetic file B. |
| **NOT_REPRODUCED** | Trong các conditions đã thử không tái hiện được. | Wrong-tenant request bị chặn ở endpoint X. |
| **FALSE_POSITIVE** | Giả thuyết/detector suy ra lỗi nhưng evidence đủ chứng minh không xảy ra trong context đã xét. | Version banner cũ nhưng vendor patch effective, có readback. |
| **INCONCLUSIVE** | Thiếu quyền/visibility, collector hỏng hoặc test fixture không đủ. | API trả 202 nhưng không có cách xem job side effect. |
| **NOT_APPLICABLE** | Không thuộc asset/role/scope, có rationale. | Feature chưa được deploy vào tested release. |
| **OUT_OF_SCOPE** | Tài sản/path ngoài ủy quyền. | Provider backend không thuộc target list. |
| **PARTIALLY_VALIDATED** | Một lớp control pass nhưng khác chưa kiểm. | API deny nhưng storage policy không được đánh giá. |

### Không nhầm “không thấy” với “không tồn tại”

Một pentest không phát hiện SQL injection có thể do input paths đã thử không có vấn đề hoặc do tester không có coverage/observability đủ. **Không thể suy false-negative rate bằng 0** từ việc không có finding.

### Khi cần gray/white-box follow-up

Nếu black-box không thể phân biệt deny ở API với silent side effects ở worker, có thể chuyển yêu cầu tới owner để đọc queue/DB logs, kiểm tra source code hoặc tạo một test hook trong sandbox. Điều này **nâng chất lượng assurance**, không phá giá trị của phần kiểm thử hộp đen đã thực hiện.

## 36. Đánh giá mức nghiêm trọng: severity khác exploitability và priority

Với mỗi finding cần phân biệt:

1. **Technical severity:** điều kiện/khả năng tác động mà vulnerability cho phép.
2. **Exploitability in tested view:** actor có quyền gì, endpoint reachable thế nào?
3. **Business impact:** dữ liệu nhạy cảm, transaction integrity, tenants, availability.
4. **Blast radius:** một object, một tenant, nhiều tenants, admin/control plane.
5. **Existing controls:** prevention, detection, response, recovery thực tế.
6. **Uncertainty:** còn condition nào chưa được thử?
7. **Remediation priority:** thời hạn/owner theo risk policy và nghĩa vụ.

### CVSS và business context

CVSS có thể hỗ trợ tính consistency của technical severity theo phiên bản/rubric tương ứng, nhưng **không tự tính toàn bộ rủi ro kinh doanh** hoặc thay test scope. Đối với business logic flaw không có CVE, reviewer vẫn có thể đánh giá severity theo security requirement và impact.

### Ví dụ

Một public information disclosure về framework version có thể có impact hạn chế nếu không có vulnerability/reachability đi kèm. Một lỗi BOLA sau login lại có thể ảnh hưởng Confidential cross-tenant data. **Việc cần tài khoản để khai thác không tự làm BOLA “Low”** nếu đăng ký account mở và dữ liệu quan trọng.

### Current risk vs target risk

Chỉ trừ rủi ro theo **controls đang vận hành được kiểm chứng**. Một PR fix chưa deploy hoặc WAF rule chưa test không tạo current residual risk thấp hơn; đó là target treatment.

## 37. Từ phát hiện tới finding có thể xử lý

Một finding report có cấu trúc:

| Trường | Mục đích |
| --- | --- |
| **ID/title/category** | Xác định lỗi, không dùng tiêu đề cảm tính. |
| **Affected scope** | Endpoint, resource, tenant/role, build và environment. |
| **Requirement/expected** | Hành vi phải đạt theo policy. |
| **Observed evidence** | Kết quả test từ viewpoint cụ thể. |
| **Preconditions** | Accounts, permissions, resource fixtures, time. |
| **Reproduction overview** | Các bước tối thiểu hợp pháp, không chứa secrets/dữ liệu thật. |
| **Security property** | Confidentiality, integrity, availability, authenticity, accountability. |
| **Risk rationale** | Severity, impact, blast radius, uncertainty. |
| **Root-cause hypothesis** | Phân biệt dự đoán với confirmed code defect. |
| **Remediation recommendation** | Control gắn đúng trust boundary và owner. |
| **Retest acceptance criteria** | Expected/observed cho positive/negative cases. |
| **Exceptions/status** | Decision, risk owner, expiry và review triggers. |

### Ví dụ finding viết tốt

**PT-AUTHZ-04 — Cross-tenant export file access trong sandbox release R.** Với synthetic account A-Viewer, tester nhận HTTP 200 và nội dung file marker B-ONLY qua đường download thuộc tenant B. Expected DENY theo requirement REQ-TEN-02. Evidence gồm redacted request/response, actor/session reference, file test ID, release, timestamp, audit correlation. **Root cause chưa xác định**. Đề nghị service owner kiểm tra per-resource authorization tại download/storage boundary và chạy retest qua API, storage/capability, job status.

### Ví dụ finding không đủ

“Endpoint không an toàn, có thể lấy mọi hóa đơn; mức Critical.” Câu này thiếu actor, scope, evidence, resource, preconditions, business impact và cách kiểm; rất khó sửa hoặc kiểm chứng.

## 38. Tương quan giữa pentest, SAST, design review và runtime evidence

Sau khi phát hiện hành vi từ ngoài, technical owners có thể dùng evidence khác để hiểu nguyên nhân:

| Black-box observation | Evidence bổ trợ | Có thể khẳng định sau khi đối chiếu |
| --- | --- | --- |
| User A thấy invoice B. | Code authz checks, repository queries, tenant policies. | Root cause ở service/data access nếu xác minh. |
| Có endpoint cũ public. | Gateway/IaC, deployment manifests, API registry. | Route drift hoặc missing gateway control. |
| Một session revoked vẫn gọi API được. | Token/session store, policy cache, revocation contract. | Cache TTL/revocation semantics nếu có evidence. |
| SSRF canary target ngoài allowlist nhận request. | Egress policy, URL validation, redirect rules. | Control missing/misconfigured trong path đã thử. |
| File export vẫn tải sau revoke. | Storage signed URL semantics, job owner, download PEP. | Capability lifetime/binding gap theo policy. |
| Security event không xuất hiện. | Audit sources, collector health, detection rules. | Telemetry gap, rule issue hoặc test path mismatch. |

### Không biến pentest thành audit mã nguồn một cách ngầm định

Report black-box nên tách **observed facts** khỏi **supplementary source analysis** nếu sau đó được cung cấp. Nêu phương pháp mỗi evidence để người đọc không nhầm rằng tester đã xác minh root cause chỉ bằng external probing.

### Khi không có lỗ hổng được tìm thấy

Đưa ra **negative test results, tested population, time window và limitations**. Đây vẫn là đầu vào assurance có giá trị, miễn không trình bày thành “đã chứng minh hệ thống hoàn toàn an toàn”.

## 39. Mô hình quy trình theo pha của một engagement

Một đợt black-box pentest chuyên nghiệp có thể được tổ chức thành bảy pha:

| Pha | Công việc | Exit criteria / evidence |
| --- | --- | --- |
| **1. Pre-engagement** | Xác minh authority, RoE, scope, contacts và data handling. | Signed authorization, target list, stop conditions. |
| **2. Discovery** | Quan sát bề mặt, lập service/API/user workflow inventory. | Scope-constrained surface map và timestamps. |
| **3. Threat/test planning** | Ưu tiên assets, hypotheses, roles, test fixtures. | Test charters, expected outcomes và approved method. |
| **4. Controlled validation** | Thực hiện tests với giới hạn traffic/dữ liệu, ghi facts. | Redacted requests/responses và observed side effects. |
| **5. Technical triage** | Loại lỗi thiết lập, xác nhận impact/conditions, gộp findings. | Reproducible findings, uncertainty và scope limits. |
| **6. Reporting** | Severity, risk, recommended controls, owners và evidence. | Report, management summary, risk decisions. |
| **7. Remediation/retest** | Sửa thiết kế/code/config, test lại trên release mới. | Observed fixed state hoặc remaining/accepted risk. |

### Chạy lại khi nào?

Phát hành API mới, thay IdP/tenant model, public ingress, export/download, storage capability, threat intelligence hoặc incident có thể kích hoạt **targeted retest**, không nhất thiết chờ kỳ pentest hàng năm.

### Không xem pentest report như giấy phép release vĩnh viễn

Report phải có **tested build/environment** và limitations. Release tiếp theo có thể thay bề mặt truy cập hoặc control; không suy kết luận của R1 áp dụng R2.

## 40. Mẫu test plan black-box có thể kiểm toán

Kế hoạch nên được viết trước để người kiểm thử, owner và người đánh giá hiểu **tại sao làm test** và **khi nào dừng**.

~~~yaml
engagement:
  id: "PT-BBOX-INVOICE-EXAMPLE"
  mode: "black_box_with_approved_test_accounts"
  purpose: "Evaluate externally observable security requirements"
  authorization: "REQUIRED_BEFORE_EXECUTION"
  environment: "approved-sandbox-only"
  time_window: "TO_BE_APPROVED"
  emergency_contact: "SET_IN_REAL_ENGAGEMENT"
scope:
  approved_origins:
    - "https://invoice-sandbox.example.invalid"
  permitted_functions:
    - "login-and-session"
    - "invoice-read"
    - "export-job"
    - "download"
    - "tenant-role-checks"
  excluded_targets:
    - "production-customer-data"
    - "third-party-provider-infrastructure"
  excluded_methods:
    - "destructive-data-changes"
    - "bulk-exfiltration"
    - "denial-of-service"
    - "credential-spraying"
test_data:
  classification: "SYNTHETIC_ONLY"
  tenant_ids:
    - "tenant-a-test"
    - "tenant-b-test"
  identities:
    - "viewer-a-test"
    - "accountant-a-test"
    - "viewer-b-test"
constraints:
  rate_limit: "APPROVED_SMALL_TEST_VOLUME"
  stop_on_unexpected_real_data: true
  stop_on_service_disruption: true
  evidence:
    redact_credentials: true
    collect_minimal_proof: true
    restrict_repository_access: true
charters:
  - id: "PT-CH-01"
    requirement: "Tenant object-level authorization"
    actor: "viewer-a-test"
    target: "invoice-b-test"
    action: "READ"
    expected: "DENY_NO_CROSS_TENANT_DATA"
    status: "NOT_EXECUTED"
  - id: "PT-CH-02"
    requirement: "Export download authorization"
    actor: "viewer-a-test"
    target: "export-b-test"
    action: "DOWNLOAD"
    expected: "DENY_AND_NO_FILE_DISCLOSURE"
    status: "NOT_EXECUTED"
verification:
  require_source_release_identity: true
  require_redacted_evidence: true
  require_scope_limited_conclusion: true
~~~

### Tại sao mẫu không có payloads khai thác?

Một test plan cần mô tả **điều muốn chứng minh và phương pháp được phép**, không cần chứa mọi chuỗi khai thác hoặc secrets. Các dữ liệu thử cụ thể có thể được lưu trong hệ thống kiểm thử bảo mật phù hợp, theo RoE và quyền truy cập.

### Không dùng ví dụ để tự chạy

Các hostnames kết thúc bằng **example.invalid** và identities đều giả; status **NOT_EXECUTED** nghĩa là chưa có bằng chứng. Muốn thử hệ thống thật phải thay bằng dữ liệu đã được owner cho phép và áp guardrails.

## 41. Java/JUnit: negative test black-box với synthetic tenants

Một black-box acceptance test có thể dùng HTTP client gửi request tới **sandbox localhost** mà không cần biết implementation của server. Mẫu này tập trung vào **server-side tenant authorization**; nó không chứa payloads khai thác hay xử lý credentials thật.

~~~java
// Illustrative JUnit 5 test against an authorized local sandbox.
// The sandbox owner must create synthetic tenant A/B records and tokens.
import static org.junit.jupiter.api.Assertions.*;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import org.junit.jupiter.api.Test;

class InvoiceBlackBoxAuthorizationTest {
    private final HttpClient client = HttpClient.newHttpClient();

    // Test-only service, never silently point this at a real host.
    private final String origin = "http://127.0.0.1:8080";

    private String requiredFixture(String name) {
        String value = System.getenv(name);
        assertNotNull(value, "Missing synthetic test fixture: " + name);
        assertFalse(value.isBlank(), "Empty synthetic test fixture");
        return value;
    }

    @Test
    void tenantAViewerCannotReadTenantBInvoice() throws Exception {
        String tokenA = requiredFixture("SANDBOX_TOKEN_TENANT_A");
        String invoiceB = requiredFixture("SANDBOX_INVOICE_B_ID");
        String markerB = requiredFixture("SANDBOX_INVOICE_B_MARKER");

        HttpRequest request = HttpRequest.newBuilder(
            URI.create(origin + "/api/invoices/" + invoiceB))
            .header("Authorization", "Bearer " + tokenA)
            .GET()
            .build();

        HttpResponse<String> response =
            client.send(request, HttpResponse.BodyHandlers.ofString());

        // This policy example uses 403/404 for unauthorized reads.
        assertTrue(response.statusCode() == 403 ||
                   response.statusCode() == 404);
        assertFalse(response.body().contains(markerB),
            "A response must not reveal tenant B test data");
    }

    @Test
    void tenantAViewerMayReadOwnAuthorizedInvoice() throws Exception {
        String tokenA = requiredFixture("SANDBOX_TOKEN_TENANT_A");
        String invoiceA = requiredFixture("SANDBOX_INVOICE_A_ID");
        String markerA = requiredFixture("SANDBOX_INVOICE_A_MARKER");

        HttpRequest request = HttpRequest.newBuilder(
            URI.create(origin + "/api/invoices/" + invoiceA))
            .header("Authorization", "Bearer " + tokenA)
            .GET()
            .build();

        HttpResponse<String> response =
            client.send(request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains(markerA));
    }
}
~~~

### Đọc kết quả đúng

Nếu cả hai tests PASS, điều đó chỉ hỗ trợ claim cho **hai fixtures, endpoint, role và build** đã thử. Không chứng minh:

- Bảo vệ invoice UPDATE/DELETE hoặc admin routes.
- Export worker, download link và caches không có đường bypass.
- Token bị revoke sẽ bị từ chối sau mọi thời điểm.
- Toàn bộ tenants/objects/regions được bao phủ.
- Backend không có SQL injection hoặc other vulnerabilities.

### Những cải tiến khi dùng thật

Đóng băng build/version và base URL theo approved test harness, gắn correlation IDs, dùng structured redacted evidence, cleanup fixtures, ghi test run ID và xác nhận side effects với owner. **Không in bearer tokens ra logs**, không đổi origin sang production chỉ để chạy test nhanh. Nếu hệ thống dùng response contract khác 403/404, thống nhất expected behavior trước test.

### Test có thể PASS sai nếu fixture sai

Nếu invoice B ID không tồn tại, server 404 không chứng minh authorization; chỉ cho thấy not found. Test setup cần **independent confirmation rằng invoice B thực sự tồn tại và user B truy cập được**, đồng thời user A không có quyền. Đây là điểm cốt lõi trong black-box assurance: **kiểm chứng preconditions**.

## 42. Ma trận 36 tình huống kiểm thử hộp đen

Ma trận dưới đây là **kịch bản học tập**, phải được lọc theo RoE, asset criticality và threat model. Chỉ dùng dummy identities, synthetic data và test endpoints.

| Test ID | Kịch bản | Expected outcome / evidence |
| --- | --- | --- |
| **BB-T01** | Anonymous request tới protected invoice read API. | DENY; không lộ invoice/test metadata. |
| **BB-T02** | User hợp lệ đọc own permitted invoice. | ALLOW theo scope; baseline positive test. |
| **BB-T03** | Tenant A user đọc tenant B invoice tồn tại. | DENY, không lộ marker B. |
| **BB-T04** | Tenant B user đọc tenant A invoice. | DENY đối xứng. |
| **BB-T05** | Viewer yêu cầu admin-only function. | DENY; không tạo side effect. |
| **BB-T06** | TenantAdmin A thử quản lý role của tenant B. | DENY; resource state B giữ nguyên. |
| **BB-T07** | User thử thay protected ownership/tenant fields. | Fields bị bỏ/từ chối theo approved schema. |
| **BB-T08** | Bỏ business approval transition với dummy invoice. | Invalid transition không được ghi nhận. |
| **BB-T09** | Gửi lại synthetic transaction cùng idempotency reference. | Không tạo duplicate side effect theo contract. |
| **BB-T10** | Session hết hạn gọi protected action. | Reauthentication/deny theo policy. |
| **BB-T11** | Role bị thu hồi trong sandbox. | Protected action bị deny trong approved window. |
| **BB-T12** | User logout rồi dùng session đã logout. | Effective revocation theo session design. |
| **BB-T13** | Invitation token revoked/expired. | DENY, không tạo account membership. |
| **BB-T14** | Federation same-email, khác issuer/subject. | Không gộp sai account/tenant. |
| **BB-T15** | Test input có ký tự biên trong query search. | Coi là data, không thay business query semantics. |
| **BB-T16** | Harmless user text render trong HTML context. | Text được encode/render đúng, không tạo executable markup. |
| **BB-T17** | Callback destination trỏ tới approved forbidden canary. | Reject/deny theo egress policy. |
| **BB-T18** | Callback redirect từ allowed sang forbidden canary. | Policy kiểm tra redirect chain. |
| **BB-T19** | File download với opaque ID ngoài quyền. | DENY, không đọc synthetic file khác. |
| **BB-T20** | API v1/v2 cùng action với role hạn chế. | Equivalent enforcement theo approved contract. |
| **BB-T21** | GraphQL query/resolver truy vấn object khác tenant. | Deny tại object/data boundary. |
| **BB-T22** | Bulk export chứa resource IDs nhiều tenant. | Không export dữ liệu trái quyền. |
| **BB-T23** | User A xem job status của B. | DENY không lộ metadata protected. |
| **BB-T24** | User A thử tải export file B. | DENY, không lộ marker test B. |
| **BB-T25** | Expired download capability URL. | Không còn hiệu lực theo approved semantics. |
| **BB-T26** | Revoke account khi export job pending. | Job/download behavior đúng yêu cầu. |
| **BB-T27** | Direct alternate storage/CDN link được cấp để thử. | Không bypass authorized download boundary. |
| **BB-T28** | Request invalid payload tới API test. | Safe validation/error handling, không lộ secrets. |
| **BB-T29** | Cross-origin browser request trong test harness. | CORS/CSRF responses phù hợp policy. |
| **BB-T30** | Sensitive UI được nhúng trong test frame. | Anti-clickjacking control theo requirement. |
| **BB-T31** | Controlled quota boundary dưới rate giới hạn được duyệt. | Limit/monitor theo tenant/account policy. |
| **BB-T32** | Security-relevant canary request có audit correlation. | Event/alert xuất hiện với fields đủ và redaction. |
| **BB-T33** | Audit collector thử nguồn mất kết nối trong sandbox. | Evidence gap/alert và status UNKNOWN. |
| **BB-T34** | Một API path trả 403 nhưng background job vẫn nhận request. | FAIL nếu unauthorized side effect xảy ra. |
| **BB-T35** | Fix đã deploy cho API nhưng worker path vẫn cũ. | Retest phát hiện residual bypass, không đóng toàn bộ finding. |
| **BB-T36** | Kết quả trên staging có cấu hình khác production. | Report limitation, không auto-claim production PASS. |

### Cách sử dụng ma trận

Mỗi test cần **scope, preconditions, actor/role, request category, expected security decision, observed result, source/time/version, side effects, evidence, owner và PASS/FAIL/INCONCLUSIVE**. Không dùng tỷ lệ “30/36 tests PASS” thay cho severity: một **FAIL trên BOLA critical path** có thể quan trọng hơn nhiều tests header/TLS đạt.

### Không phải mọi test đều áp dụng

Nếu hệ thống không dùng GraphQL hoặc không có invitations, có thể ghi **NOT APPLICABLE với lý do**. Nếu có nhưng RoE không cho phép thao tác, ghi **NOT TESTED/OUT OF SCOPE** và đánh giá gap, không xóa test khỏi mẫu số để tạo “100% passed”.

## 43. Case study đầy đủ: kiểm thử Invoice SaaS từ góc nhìn bên ngoài

### 43.1. Bối cảnh và phạm vi

Một Invoice SaaS hỗ trợ nhiều tenants, web UI, REST APIs, async export và partner webhooks. Engagement giả định do owner ủy quyền cho **sandbox tương đương kiến trúc**:

- Hostname test thuộc miền giả lập.
- Test accounts A-Viewer, A-Accountant, A-TenantAdmin, B-Viewer.
- Synthetic invoices A-001, B-001; export files chứa canary markers.
- Test flow: login → search → read → update → export → download → role revoke.
- Không được phép thử production customer data, destructive test, bulk enumeration, DDoS hoặc provider infrastructure.
- Có contact SOC và data owner trong trường hợp phát hiện unexpected data.

### 43.2. Threat hypotheses đã chọn

| Hypothesis | Threat objective | Security boundary |
| --- | --- | --- |
| **H-01** | User A có thể đọc invoice B. | API/resource/tenant authorization. |
| **H-02** | Viewer có thể sửa invoice status. | Function-level/business authorization. |
| **H-03** | User đổi protected fields qua update API. | Server-owned data integrity. |
| **H-04** | Export job và download URL chỉ cần biết identifier. | Async ownership/capability boundary. |
| **H-05** | Webhook destination có thể vượt egress policy. | External integration/network trust. |
| **H-06** | Revoked role còn dùng session để download. | Session/job authorization lifecycle. |
| **H-07** | Alternate API version không có control mới. | Deployment/version consistency. |
| **H-08** | Error/log pathways lộ secrets hoặc data. | Error handling/observability. |

### 43.3. Observations minh họa

Giả sử tester nhận các kết quả **hư cấu phục vụ bài học**:

| Observation ID | Điều quan sát | Kết luận phù hợp |
| --- | --- | --- |
| **OBS-01** | Anonymous access invoice API trả 401. | Positive evidence cho một anonymous boundary. |
| **OBS-02** | User A lấy invoice A đúng marker. | Fixture và allowed flow hoạt động. |
| **OBS-03** | User A nhận invoice B marker qua legacy API v1. | Confirmed BOLA trong sandbox scope. |
| **OBS-04** | API v2 từ chối cross-tenant read. | v2 boundary PASS trong test; chưa bù v1 failure. |
| **OBS-05** | Viewer update protected status trả 403, DB state không đổi. | BFLA/integrity control PASS trong fixture. |
| **OBS-06** | Job status của B lộ tên file cho A nhưng không lộ nội dung. | Metadata disclosure cần đánh giá impact. |
| **OBS-07** | Download của file B bị từ chối với A. | Download path PASS trong tested case. |
| **OBS-08** | Session role revoke cần 2 phút để lan truyền đúng policy. | Cần so với approved revocation SLA. |
| **OBS-09** | Webhook forbidden canary không nhận request, nhưng source logs thiếu. | Không đủ xác định control nào chặn; PARTIAL. |
| **OBS-10** | Audit event cho legacy v1 authorization bypass không xuất hiện. | Detection/evidence gap, cần owner xác minh source health. |

### 43.4. Chuỗi suy luận từ OBS-03

1. A và B là hai **test tenants khác nhau** đã được chủ hệ thống xác nhận.
2. B-001 tồn tại; B-Viewer có thể đọc B-001; A-Viewer không có permission cho B.
3. A-Viewer dùng legacy v1 read endpoint thuộc RoE.
4. Response có exact synthetic marker B-ONLY.
5. Expected DENY, observed ALLOW + data disclosure.
6. Kết luận: **confirmed object-level authorization failure** ở endpoint/version đã thử.
7. Chưa kết luận root cause là thiếu tenant filter hay cache issue nếu không có code/runtime evidence.
8. Việc endpoint v2 PASS không xóa issue ở v1, trừ khi v1 được chứng minh đã decommission/restricted.

### 43.5. Hai mức severity cần phân biệt

OBS-06 (tên file B lộ cho A) có thể là **metadata disclosure** đáng xử lý, nhưng không tự bằng lộ file contents. OBS-03 có bằng chứng lộ synthetic Confidential data giữa tenants nên có impact rõ hơn. Reviewer vẫn cần tính **production equivalence, exposure, reachable roles và threat prerequisites** trước khi quyết định priority theo policy.

### 43.6. Remediation roadmap

- Dùng centralized resource/action/tenant authorization tại các API versions được hỗ trợ.
- Review toàn bộ legacy endpoints và alternate paths, không chỉ sửa v1 read.
- Dùng verified principal tenant context ở repository/workers/caches; không tin client-supplied tenant IDs.
- Áp job owner validation cho status/download, storage capabilities có lifecycle được duyệt.
- Bổ sung negative tests cross-tenant đối xứng, read/write/export và role transitions.
- Ghi security decision audit, xác nhận logging source health.
- Quy định revocation semantics và test timing.
- Retire v1 theo change process hoặc duy trì control tương đương nếu vẫn phục vụ clients.

### 43.7. Retest outcome phải được quan sát

| Retest | Expected | Evidence |
| --- | --- | --- |
| A-Viewer đọc B qua v1 và v2. | DENY, không có marker B. | Redacted HTTP + test release. |
| A-Viewer đọc A. | ALLOW bình thường. | Positive control chống false PASS vì endpoint hỏng. |
| Bulk export trên v1/v2. | Không xuất B data. | Synthetic output + job readback. |
| Job status/download của B bởi A. | Không tiết lộ protected metadata/data. | API, storage/capability evidence. |
| Role revoked before download. | Behavior đúng approved window. | Timestamped sequence. |
| Authorization failure audit. | Event có actor, action, decision, correlation. | SOC/log readback. |
| Runtime version. | All supported endpoints chạy approved release. | Deployment/route inventory. |

Nếu chỉ có code fix nhưng chưa deployment, ghi **FIXED_IN_SOURCE/PENDING_PRODUCTION_VERIFICATION**. Nếu v1 vẫn trả marker B, finding vẫn open dù tất cả v2 tests xanh.

### 43.8. Kết luận case study có giới hạn

> “Trong sandbox và roles/flows được ủy quyền, black-box tests phát hiện BOLA ở legacy invoice API v1 cùng một metadata disclosure ở job status. API v2 và download path vượt qua các negative tests đã chọn nhưng không chứng minh toàn bộ hệ thống an toàn. Findings cần remediation và retest trên release/route inventory tương ứng; một số trạng thái egress/audit còn cần evidence bổ sung.”

Đây là kết luận **đúng với evidence hư cấu của case study**; không phải kết quả kiểm thử một hệ thống thật.

## 44. Viết báo cáo pentest cho người ra quyết định và người sửa lỗi

Một engagement thường cần **hai lớp trình bày**: lãnh đạo/risk owner cần biết business impact và quyết định; kỹ sư cần biết preconditions, evidence, control gap và retest.

### Cấu trúc báo cáo đề xuất

1. **Executive summary:** mục tiêu, những phát hiện material, mức độ rủi ro và điều cần quyết định.
2. **Engagement identifiers:** dates, tester organization, authorizing party, tested system/release.
3. **Scope/RoE:** targets, viewpoints, excluded assets, prohibited/allowed methods, test data.
4. **Methodology:** discovery, hypotheses, controlled validation, manual/automated tests.
5. **Coverage:** APIs, roles, tenants, versions, data classes, untested routes, time windows.
6. **Findings overview:** priority, affected assets, statuses, owner và treatment.
7. **Detailed findings:** expected vs observed, minimal repro, impact, assumptions, evidence, remediation.
8. **Negative test results:** controls được thử và không bị vượt trong scope.
9. **Evidence quality:** provenance, timestamp, build/host identity, redaction và storage.
10. **Limitations:** unknown environments, third-party dependencies, staging/production differences.
11. **Remediation/retest plan:** owners, timelines, acceptance criteria, control validation.
12. **Risk decisions:** exemptions, interim mitigations, sign-offs và expiry.
13. **Appendices:** allowed technical traces/report references, glossary, test IDs, references.

### Report finding khác một exploit story

Một finding cần giúp owner **sửa đúng security requirement**. Nếu report chỉ kể lại chuỗi thao tác nhưng không có expected outcome hoặc xác minh scope, nó khó dùng cho release gate hay audit. Ngược lại, báo cáo không nên chứa nguyên văn credentials, sensitive customer records hoặc quy trình chi tiết cho phép người ngoài tái sử dụng để gây hại.

### Executive summary có giới hạn

Thay vì “Ứng dụng yếu nghiêm trọng, dễ bị hack”, viết: “Trong sandbox release R, đã xác nhận một lỗi cho phép account tenant A đọc canary invoice của tenant B qua legacy API v1. Production impact cần owner xác nhận phiên bản/route tương đương. Đề nghị ưu tiên kiểm tra và khắc phục object authorization trên mọi API versions và retest.” Câu này **có chứng cứ, có giới hạn và có hành động**.

## 45. Claim–Argument–Evidence (CAE) cho Black-box Penetration Testing

Trong security assurance, black-box pentest là **một nguồn bằng chứng** hỗ trợ claim cụ thể, không phải bằng chứng duy nhất hệ thống “secure”.

### Claim minh họa

> “Đối với các protected Invoice API actions, job status và download paths trong sandbox release R, user identities thuộc tenants A/B được áp object-level và function-level authorization phù hợp security requirements, như được quan sát bằng tập negative/positive black-box tests đã chọn; mọi exceptions và phạm vi chưa thử được nêu rõ.”

### Argument

1. **Scope đúng:** target, environment, build, roles, routes và datasets đã được xác minh.
2. **Preconditions đúng:** tenant B resource tồn tại, user A không có quyền, account/token hợp lệ.
3. **Phương pháp đúng:** tests được ủy quyền, safe fixtures, expected behavior từ requirements.
4. **Observation đáng tin:** requests/responses, timestamps, side effects và audit có evidence.
5. **Coverage tương xứng:** critical business paths/variants được chọn theo threat model.
6. **Findings trung thực:** confirmed, not reproduced, inconclusive và out-of-scope được phân biệt.
7. **Risk được xử lý:** controls/remediation/retests hoặc accepted residual risk theo thẩm quyền.
8. **Limitations rõ:** black-box không tự quan sát tất cả internal checks, policies và alternate paths.

### CAE evidence matrix

| Claim component | Evidence | Giới hạn / phản chứng |
| --- | --- | --- |
| Authorized and safe engagement. | Approved RoE, target list, time window, test accounts. | Một request tới host ngoài scope không được dùng làm verified test. |
| Tested asset/version đúng. | Route inventory, release, origin, app build, headers có kiểm chứng. | Staging có thể khác production. |
| Test fixture hợp lệ. | Synthetic tenants, users, roles, owners, readback resource existence. | 404 với nonexistent B ID không chứng minh AuthZ. |
| Authorization hoạt động. | Positive/negative request outcomes, downstream side effects. | Chỉ API boundary có thể bỏ worker/storage paths. |
| Session controls theo policy. | Expiry/revoke sequences và timestamps. | Một session khác hoặc cache path có thể chưa thử. |
| Detection đủ trong scope. | Correlation IDs, SOC readback, source-health evidence. | Logs trống khi source bị tắt không thể là PASS. |
| Remediation verified. | Fix deployment identity, retest outcomes, policy readback. | PR merged không chứng minh production fixed. |
| Risk decision có thẩm quyền. | Finding register, exception approvals/expiry, residual risk. | Approved risk không là technical control PASS. |

### Trường hợp claim bị bác bỏ

Nếu black-box test cho user A đọc canary invoice B thành công, claim “mọi Invoice APIs enforce tenant isolation” bị bác bỏ **ít nhất trong path/role/environment đó**. Cần ghi finding và sửa, không lấy nhiều tests PASS khác để “trung bình hóa” một vi phạm material.

### Kết hợp nguồn evidence

Để tăng assurance, có thể dùng **source review, tests, effective IAM/storage policies, logs và monitoring** bổ trợ lập luận. Phải gắn nhãn từng nguồn và thời điểm; đừng mô tả một assertion từ code review như thể được chứng minh bằng black-box request.

## 46. Chất lượng, bảo mật và retention của pentest evidence

Pentest evidence thường mang tính nhạy cảm: endpoint names, phiên bản, access paths, test accounts, vulnerability details, audit traces và thậm chí dữ liệu thực nếu test gặp sự cố.

### Tiêu chí đánh giá evidence

| Tiêu chí | Câu hỏi |
| --- | --- |
| **Relevant** | Evidence đo đúng requirement/claim không? |
| **Complete for scope** | Có đủ request, response, side effect và precondition? |
| **Authentic/provenance** | Ai thu, ở endpoint nào, thời điểm và version nào? |
| **Accurate** | Fixture, role và resource ownership có được xác minh độc lập? |
| **Fresh** | Có áp dụng cho release sau thay đổi cuối cùng không? |
| **Repeatable** | Đủ chi tiết cho tester có quyền tái hiện trong sandbox? |
| **Integrity-protected** | Logs/report có audit trail hoặc cơ chế xác định sửa đổi? |
| **Least-data** | Đã giảm thiểu/che secrets, PII và payload không cần thiết? |
| **Traceable** | Có kết nối finding→risk→fix→test→release không? |
| **Limited** | Những kết luận chưa đạt hoặc chưa thể thử được mô tả? |

### Evidence handling workflow

1. Ghi **ID, timestamp, scope, viewpoint, build, action** khi test.
2. Chỉ thu **dấu hiệu tối thiểu** cần để chứng minh invariant.
3. Redact bearer tokens, cookies, PII, customer data và internal secrets trước khi chia sẻ.
4. Lưu raw evidence ở nơi hạn quyền theo policy; không đưa vào public tickets/chat.
5. Gắn hashes/audit metadata nếu cần chứng minh tính toàn vẹn sau thu.
6. Kiểm soát retention, handover, deletion và incident escalation.

### Hash không đủ chứng minh toàn bộ claim

Hash giúp kiểm tra tệp evidence không đổi sau khi thu, nhưng không chứng minh response đến từ đúng production release hoặc test fixture có đúng quyền. Vẫn phải có **origin/version/source attribution và precondition validation**.

## 47. Remediation và retest: sửa đường tấn công, không chỉ response code

Một finding có thể được sửa ở một lớp nhưng để lại đường bypass ở lớp khác. Retest cần phản ánh **root cause và affected path set**, không chỉ thử lại request đã thấy lỗi.

### Ví dụ cross-tenant export

| Layer | Fix candidate | Retest cần có |
| --- | --- | --- |
| API | Resource/action authorization trước tạo job. | A không tạo job cho resource B; own request vẫn chạy. |
| Queue/job | Server-owned job ID/tenant binding, producer controls. | Spoofed actor/tenant context không được tin. |
| Worker | Revalidate job and least-privilege access. | Không đọc B qua job ngoài quyền. |
| Database | Tenant-scoped queries/RLS khi phù hợp. | Wrong-tenant read deny, admin exceptions đúng policy. |
| Storage | Private object permissions. | Anonymous/direct unauthorized reads deny. |
| Download | Per-resource authorization hoặc bounded capability semantics. | Wrong principal/expired/revoked cases phù hợp contract. |
| Cache/CDN | Scope cache key và invalidation. | Không trả dữ liệu B từ stale/shared cache. |
| Audit | Actor→job→file correlation và source health. | Test event xuất hiện, không lộ contents. |

### Trạng thái vòng đời

- **OPEN / CONFIRMED:** violation đã có bằng chứng, chưa fix.
- **FIX_PLANNED:** code/config changes được đề xuất, chưa verified.
- **FIXED_IN_SOURCE:** PR/code merged, chưa triển khai.
- **DEPLOYED_PENDING_RETEST:** approved build đã lên, chưa xác minh effective.
- **VERIFIED_FIXED:** required positive/negative tests và scope readback đạt.
- **PARTIALLY_FIXED:** một số paths/versions chưa đạt.
- **INCONCLUSIVE:** thiếu evidence hoặc môi trường test không hợp lệ.
- **EXCEPTION / ACCEPTED_RISK:** chưa fix nhưng risk được quản trị theo thẩm quyền.

### Không dùng ticket close làm test evidence

Một ticket đóng sau sửa code không chứng minh legacy v1 đã retired, storage link đã hết hiệu lực hoặc worker không còn đọc cross-tenant data. Phải có **actual deployed version** và observed outcome.

### Retest thất bại

Nếu repeated violation vẫn tồn tại, cần giữ finding open, cập nhật risk/owner, xem root cause và rollback/interim containment. Không đổi test fixture hoặc expected behavior để làm dashboard xanh nếu security requirement chưa đổi có thẩm quyền.

## 48. RACI và governance trong engagement

| Vai trò | Trách nhiệm |
| --- | --- |
| **Authorizing business/system owner** | Xác định phạm vi, quyền, dữ liệu kiểm thử, operational constraints. |
| **Pentest lead** | RoE adherence, test charters, techniques, safety, evidence và reporting. |
| **Application/service owner** | Business invariants, fixture readiness, technical reproduction và remediation. |
| **Platform/cloud owner** | Ingress, storage, IAM, monitoring và network boundaries. |
| **Identity/data/privacy owners** | Roles, test accounts, data classification, federation và privacy constraints. |
| **SOC/incident responder** | Biết test windows, triage alerts, stop/escalation, evidence readback. |
| **AppSec/security architect** | Threat model, technical triage, root-cause review, control recommendations. |
| **Security assurance assessor** | Independent evidence challenge, claim scope, retest quality và conclusions. |
| **Risk owner** | Remediation priority/exception và residual risk acceptance theo thẩm quyền. |
| **Release/change owner** | Gate control, production deployment identity và retest schedule. |

### RACI minh họa

**R** thực hiện, **A** chịu trách nhiệm cuối cùng, **C** tham vấn, **I** được thông báo.

| Hoạt động | System owner | Pentest lead | App/platform | Assurance | Risk owner |
| --- | :---: | :---: | :---: | :---: | :---: |
| RoE scope, stop conditions | **A** | R | C | C | I |
| Threat charters/test design | C | **A/R** | C | C | I |
| Controlled black-box execution | I | **A/R** | C | I | I |
| Technical triage/confirmation | C | R | **A/R** | C | I |
| Severity/risk argument | C | R | C | **A/R** | C |
| Remediation and deployment | I | C | **A/R** | C | I |
| Independent retest/evidence | C | R | C | **A/R** | I |
| Risk acceptance/exceptions | C | C | C | C | **A/R** |

Một nhóm nhỏ có thể gộp vai nếu phù hợp, nhưng người làm pentest không được tự ý mở rộng scope hoặc chấp nhận residual risk thay cho owner. **Quyền kiểm thử** và **thẩm quyền chấp nhận rủi ro** là hai quyền khác nhau.

## 49. Chỉ số cho Black-box Penetration Testing và Security Assurance

Chỉ số phải mô tả **scope, chất lượng tests, mức rủi ro và remediation**, không chỉ số bugs hay số requests.

| Metric ID | Định nghĩa | Cảnh báo |
| --- | --- | --- |
| **BB-M01 Engagement authorization coverage** | Test activities có RoE/targets/methods được ủy quyền / các hoạt động cần approval. | Không bỏ các actions không hợp lệ khỏi denominator. |
| **BB-M02 Surface review coverage** | Critical endpoints/workflows được xem trong scope / population được đối chiếu. | Inventory có thể thiếu alternate routes. |
| **BB-M03 Viewpoint coverage** | Relevant attacker/role/tenant viewpoints đã thử / viewpoints trong charter. | Role count không đại diện đủ authorization matrix. |
| **BB-M04 Charter completion** | Material charters có observed result / approved material charters. | NOT_TESTED không tính PASS. |
| **BB-M05 Precondition validity** | Tests có fixtures/actors/versions được xác minh / executed tests. | 404 với nonexistent object gây false PASS. |
| **BB-M06 Observed security invariant failures** | Confirmed violations theo asset/risk tier. | Không dùng raw finding count thay risk. |
| **BB-M07 Inconclusive test rate** | Tests thiếu evidence/visibility / executed tests. | Không tự đưa vào success denominator. |
| **BB-M08 High-risk remediation age** | Tuổi confirmed high-risk findings theo scope/policy. | Average che các issue quá hạn. |
| **BB-M09 Verified remediation coverage** | Findings retest đủ trên approved release / findings đến hạn. | PR merged khác deployed verified. |
| **BB-M10 Retest reopen rate** | Findings tái xuất hiện trên relevant releases/viewpoints. | Có thể do coverage mở rộng, cần phân tích. |
| **BB-M11 Critical negative-test coverage** | Critical security invariants có test observed / identified critical invariants. | Invariant inventory do threat model cung cấp. |
| **BB-M12 Evidence traceability** | Material findings có req/threat→test→evidence→owner link. | Link có thể stale theo release. |
| **BB-M13 Detection correlation coverage** | Relevant test events có SOC/source evidence / expected events. | Source outage cần UNKNOWN. |
| **BB-M14 Time to containment** | Thời gian từ confirmed harmful finding đến effective interim control. | Containment không tự là permanent fix. |
| **BB-M15 Scope/evidence freshness** | Critical test evidence còn áp dụng current release / evidence cần có. | Code changes và config drift có thể làm lỗi thời. |
| **BB-M16 Exception hygiene** | Open exceptions có owner/scope/expiry/controls / exceptions phải quản trị. | Accepted không là PASS. |
| **BB-M17 Tested environment equivalence** | Claims production có mapping evidence từ test environment + runtime readback. | Staging tests không luôn đủ production proof. |
| **BB-M18 Source health** | Audit/monitoring sources dùng để xác minh tests còn đầy đủ và mới. | Có alert không chứng minh all detection paths. |

### Định nghĩa mẫu số là điều kiện tiên quyết

Giả sử có **40 critical business actions** trong inventory đã đối chiếu, 32 actions được pentest với charter hợp lệ và evidence:

\[
\text{Critical action coverage}=\frac{32}{40}\times 100\%=80\%.
\]

80% chỉ nói về **coverage trên population đã xác định**, không phải “80% hệ thống an toàn”. Nếu tám actions chưa test bao gồm transfer tiền và admin role grant, quyết định release phải xét rủi ro của gap đó thay vì chấp nhận mức trung bình.

### Vì sao không dùng số findings làm KPI duy nhất?

Một đội phát hiện nhiều issues có thể do test tốt hơn hoặc sản phẩm rủi ro hơn; đội báo 0 findings có thể do scope quá hẹp. Đánh giá nên xem **critical paths tested, severity-weighted findings, evidence quality, test gaps và verified remediation**.

## 50. Các phương pháp và hướng dẫn nên dùng như tài liệu hỗ trợ

Black-box penetration testing không có một checklist duy nhất đúng cho mọi hệ thống. Có thể tham chiếu những nguồn hướng dẫn phổ biến như **OWASP Web Security Testing Guide (WSTG)** cho web applications, **OWASP API Security Top 10** để khơi gợi rủi ro API, **OWASP ASVS** khi xây tiêu chí kiểm chứng security requirements, **NIST SP 800-115** như một hướng dẫn lập kế hoạch/đánh giá security testing và **PTES** như khung tổ chức engagement.

### Dùng tài liệu đúng vai trò

| Hướng dẫn/khung | Cách dùng | Giới hạn |
| --- | --- | --- |
| **OWASP WSTG** | Gợi ý categories và phương pháp kiểm thử web. | Không phải giấy chứng nhận ứng dụng không có lỗi. |
| **OWASP API Security Top 10** | Tập trung API risks như authorization, resource consumption, business flows. | Danh mục không tự là test evidence. |
| **OWASP ASVS** | Chọn security verification requirements và acceptance criteria. | Cần xác định level/phiên bản/requirements phù hợp. |
| **NIST SP 800-115** | Tham khảo định hướng security testing/assessment và reporting. | Phải thích nghi system scope và authority. |
| **PTES** | Tham khảo workflow pre-engagement tới reporting. | Không thay RoE, risk policy và kỹ năng người kiểm thử. |
| **Threat modeling/DFD** | Ưu tiên asset, trust boundaries, attacker paths. | Design model chưa chắc đúng runtime. |
| **SAST/SCA/IaC** | Bổ sung source, package, config và provenance. | Không thay observed black-box behavior. |

### Không “đạt chuẩn” chỉ vì đã tick đủ một danh sách

Việc chọn 20 tests từ một checklist không tự chứng minh sản phẩm đáp ứng toàn bộ một standard hoặc level. Kết luận tuân thủ, nếu cần, phải dựa **đúng phiên bản, scope, control objectives, evidence và thẩm quyền đánh giá**.

### Chuyển checklist thành testable requirements

Ví dụ một hướng dẫn nhắc tới authentication testing. Security requirement cụ thể của sản phẩm có thể là: “Sau khi role export bị revoke, user không thể tải file theo policy trong cửa sổ X đã được duyệt.” Chỉ khi có test identity, resource, expected time window và observed outcome thì yêu cầu này mới trở thành **cơ sở assurance**.

## 51. Continuous black-box assurance và trigger tái kiểm thử

Một lần pentest có thể phát hiện đường tấn công quan trọng, nhưng hệ thống thay liên tục. Cần cơ chế để **tái đánh giá những bề mặt/assumptions đã thay đổi**.

### Trigger trọng yếu

- Public route hoặc API version mới; legacy route chưa decommission.
- Chuyển authN/IdP, session/token, role hoặc tenant isolation.
- Thay object storage, CDN, signed URL/download semantics.
- Thêm queue/worker, webhook, partner API, vendor data recipient.
- Đổi framework, reverse proxy, WAF, cloud ingress/egress và deployed artifact.
- Business workflow mới như refund, bulk export, approval/delegation.
- New sensitive data class, enterprise tenant tier hoặc geographic region.
- Incident/pentest finding, suspicious telemetry, vulnerability advisory liên quan.
- Rollback một security fix hoặc một control bị mất hiệu lực.
- Audit collector/source health gap làm mất khả năng kết luận.

### Tích hợp vào SDLC

~~~mermaid
flowchart TD
    A["Approved requirements and prior pentest baseline"] --> B["API / identity / data / release change"]
    B --> C["Detect material trust or behavior change"]
    C --> D["Update threat hypotheses and test charter"]
    D --> E["Provision synthetic accounts, resources and authorized sandbox"]
    E --> F["Run targeted black-box checks"]
    F --> G{"Security invariant observed?"}
    G -- "Violation / unknown" --> H["Finding, triage, risk and remediation"]
    H --> E
    G -- "Expected behavior" --> I["Evidence-backed scope-limited result"]
    I --> J["Monitor runtime drift, incidents and risk changes"]
    J --> B
~~~

### Automation có ích

Có thể tự động chạy **positive/negative HTTP acceptance tests** với test identities trong CI/staging, đối soát route inventory, kiểm signed URL expiry, cross-tenant access và correlation logs. Tuy nhiên automation thường chỉ bao phủ scenarios đã biết; **human exploratory testing, business abuse analysis và scoped external assessment** vẫn cần cho threats mới.

### Không biến continuous testing thành quét ngoài quyền

New domains, vendor integrations hoặc production environments cần authorization phù hợp trước khi chạy automation. Một CI job tự động chạy mỗi giờ mà không giới hạn targets/rates/credentials có thể tạo rủi ro vận hành và vi phạm phạm vi.

## 52. Anti-patterns trong Black-box Penetration Testing

| Anti-pattern | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| **Không có RoE rõ ràng** | Scope creep, gián đoạn, tranh chấp quyền. | Authorization, target/method allowlists, stop rules. |
| **Black box nghĩa là được thử mọi thứ** | Quá phạm vi, ảnh hưởng hệ thống khác. | Phân biệt method với quyền. |
| **Chỉ chạy scanner** | Bỏ business logic, authorization, real behavior. | Manual threat-driven validation và tests. |
| **Một response 500 = exploit** | False positive, ưu tiên sai. | Quan sát security property và corroboration. |
| **Một request 403 = bảo mật đầy đủ** | Side effects/alternate routes có thể bypass. | Test state/worker/storage và scope limitations. |
| **404 nghĩa là AuthZ pass** | Object có thể không tồn tại. | Independent test fixture validation. |
| **Không có findings = an toàn** | Scope/skill/time/visibility limitations. | Report tested population và unknowns. |
| **Authenticated = không thể tấn công** | BOLA/BFLA/business abuse bị bỏ. | Test valid-but-low-privilege actors. |
| **Dùng dữ liệu khách hàng thật làm proof** | Tăng exposure và privacy harms. | Synthetic fixtures, minimum proof, escalation. |
| **Ưu tiên số lượng bugs** | Noise tăng, không tập trung impact. | Risk-based selection và verified remediation. |
| **Gộp API v1/v2 thành một kết luận** | Legacy route bypass control. | Report coverage theo version/route. |
| **Chỉ test UI** | Backend endpoints vẫn có thể bị gọi. | Server-side API authorization checks. |
| **Chỉ đo status code** | Side effects/file/cache leaks bị bỏ. | Response plus data/state/log readback. |
| **Có MFA là coi AuthZ đúng** | Login không bảo vệ object ownership. | Principal/action/resource testing. |
| **Coi IdP và vendor là target mặc định** | Vượt quyền third-party. | Provider/contract scope check. |
| **Stress test không giới hạn** | Gây outage ngoài mục tiêu. | Separate load-testing approval và guardrails. |
| **Copy secrets vào report** | Tạo data breach thứ cấp. | Redaction, secure storage và credential process. |
| **Hạ severity chỉ vì cần login** | Bỏ impact multi-tenant và account availability. | Business/context risk method. |
| **Root cause từ suy đoán black-box** | Sửa sai lớp hoặc overclaim. | Tách observed fact và hypothesis. |
| **Staging pass = production pass** | Config/deployment khác nhau. | Equivalence evidence và runtime readback. |
| **PR merged = fixed** | Old artifacts/paths vẫn chạy. | Deployed-version retest. |
| **Exception được coi là PASS** | Residual risk bị giấu. | Report accepted risk và technical status riêng. |
| **Không theo dõi telemetry health** | Không biết test event có đến SOC. | Collector canaries và evidence gap handling. |
| **Pentest một lần rồi bỏ** | Release mới tạo trust boundary mới. | Trigger-driven reassessment. |

### Các phát biểu cần hỏi lại

“API đã có TLS nên không có lỗ hổng”; “Chỉ user có account mới thao tác được, nên không quan trọng”; “Tôi thử một invoice ID và được 404, tất cả tenants an toàn”; “Không cần ghi version vì URL không đổi”; “Đã có pentest report nên không cần retest sau migration”. Những phát biểu này **thiếu scope hoặc bằng chứng cần thiết**.

## 53. Checklist nghiệm thu một bài Black-box Pentest

Checklist này giúp reviewer thấy **điều gì đã thực sự đánh giá** chứ không dùng để thay review chuyên môn.

1. **Authorization:** có văn bản/owner và time window rõ?
2. **RoE:** approved targets, methods, exclusions, stopping conditions đầy đủ?
3. **Third parties:** cloud/CDN/IdP/vendors có boundaries và approvals riêng?
4. **Safety:** synthetic data, low-impact methods, resource limits, emergency contact?
5. **Business assets:** dữ liệu, chức năng nhạy cảm, trust boundaries được ưu tiên?
6. **Viewpoints:** anonymous, authenticated roles, tenant scopes theo threat model?
7. **Discovery:** hostnames/APIs/versions/alternate routes được gắn attribution và scope?
8. **Test charters:** mỗi hypothesis có requirement, expected outcome và owner?
9. **Preconditions:** test objects tồn tại, role/tenant/identity đúng?
10. **Authentication:** login, logout, session recovery, token lifecycle theo scope?
11. **Object authorization:** READ/WRITE/EXPORT/DOWNLOAD có cross-tenant negative cases?
12. **Function authorization:** Viewer/admin/support workflows được xét đúng policy?
13. **Business logic:** state transitions, approvals, idempotency/replay được thử?
14. **Input risks:** validation/encoding/SSRF/file boundaries có test phù hợp và an toàn?
15. **Browser controls:** CSRF/CORS/clickjacking/session cookies được đánh giá theo context?
16. **API versions:** v1/v2/mobile/GraphQL/legacy endpoints không bị bỏ nếu thuộc scope?
17. **Async paths:** queue jobs, status, cancel, download, side effects và storage?
18. **Rate/abuse:** có policy và bounded tests, không stress ngoài thỏa thuận?
19. **Cloud/public:** routes/TLS/storage và provider scope được xem chính xác?
20. **Detection:** canary events, audit correlation và source health có evidence?
21. **Result statuses:** CONFIRMED, NOT_REPRODUCED, INCONCLUSIVE, N/A, OUT_OF_SCOPE phân biệt?
22. **Evidence:** facts, preconditions, request/response, test data, time/version đầy đủ?
23. **Privacy:** reports/logs tránh raw secrets, customer PII hoặc bulk data?
24. **Risk:** severity, prerequisites, exposure, business impact và uncertainty có rationale?
25. **Remediation:** fixes gắn vào đúng trust boundaries và affected versions?
26. **Retest:** actual approved release, positive/negative/side-effect evidence có?
27. **Exceptions:** owner, authority, expiry, interim controls và residual risk?
28. **Coverage:** tested denominator, exclusions và critical untested paths công bố?
29. **CAE:** claim, argument, test evidence, contradictions và limitations rõ?
30. **Continuous review:** change/incident/rollback triggers dẫn tới reassessment?

### Điền trạng thái đúng

Mỗi mục material nên có **PASS, FAIL, PARTIAL, UNKNOWN hoặc NOT_APPLICABLE kèm lý do**, evidence ID, risk impact, owner và next action. Không có evidence thì ghi **UNKNOWN**, không tự cho PASS vì không thấy lỗi.

## 54. Bài tập tình huống và gợi ý giải

### Bài tập A — Có URL là được quét?

Người kiểm thử được giao một domain SaaS nhưng DNS trả IP thuộc CDN bên thứ ba. Họ muốn quét toàn bộ dải IP vì “cùng phục vụ domain”.

**Gợi ý:** Authorization theo domain không tự bao phủ IP của provider. Xem RoE và provider policy, xác nhận attribution, xin mở rộng phạm vi trước bất kỳ active checks nào ngoài target.

### Bài tập B — Response 404 được coi là authorization PASS

User A đọc invoice B bằng ID mà tester tự đoán, API trả 404. Không ai xác nhận invoice B tồn tại.

**Gợi ý:** Test precondition sai/chưa đủ; 404 có thể do không có object. Chuẩn bị synthetic B record đã xác minh bằng B-Viewer rồi lặp bounded negative test với A.

### Bài tập C — UI ẩn nút quản lý user

Viewer không nhìn thấy chức năng Manage Roles. Nhóm sản phẩm tuyên bố BFLA PASS.

**Gợi ý:** UI visibility không phải server-side authorization. Dùng authorized test account để xác minh protected role-action endpoint và readback state; cần expected role policy.

### Bài tập D — Cross-tenant export trả 403 nhưng vẫn có file

API trả 403 khi A yêu cầu invoice B, nhưng worker vẫn tạo export job trong test tenant B.

**Gợi ý:** Negative test FAIL vì unauthorized side effect; xem API→queue→worker, job integrity và tenant scoping. Không dùng status 403 thay toàn bộ evidence.

### Bài tập E — Có signed URL thì đã an toàn?

Link export gồm token ngẫu nhiên, sống 24 giờ và có thể chia sẻ cho bất kỳ ai. Người dùng bị revoke role sau khi tạo link.

**Gợi ý:** Đây là **capability URL**; mức độ đúng phụ thuộc approved expiry, recipient binding và revoke policy. Test controlled wrong-principal/expired/revoked cases, không mặc định URL khó đoán tương đương session authorization.

### Bài tập F — Một endpoint v2 chặn đúng, v1 vẫn sai

Team fix BOLA trên v2, nhưng khách hàng mobile cũ vẫn gọi v1 và A có thể xem B.

**Gợi ý:** Finding chưa fixed trong toàn supported surface. Retest v1/v2, mobile route, update/decommission policy, deployment readback và residual risk.

### Bài tập G — Không tìm thấy SQL injection sau 30 phút

Tester kết luận toàn bộ ứng dụng không có SQL injection vì thử vài input ở search API không thấy response khác.

**Gợi ý:** Kết luận phải là **not reproduced in tested paths/conditions**, không là zero vulnerability. Xem scope, test coverage, SAST/code review complement và khả năng false negatives.

### Bài tập H — Quên synthetic accounts cho nhiều tenants

Engagement chỉ có một account ở tenant A, nhưng management muốn kết luận cross-tenant isolation.

**Gợi ý:** Thiếu preconditions, phải ghi INCONCLUSIVE/NOT_TESTED cho claim đó hoặc xin approved tenant B fixtures. Không tự truy cập customer tenant thật.

### Bài tập I — Callback URL đến server test, không thấy request

SSRF test canary không nhận outbound request. Team bảo đảm egress đã an toàn nhưng logs trống vì queue bị dừng.

**Gợi ý:** Kết quả INCONCLUSIVE; có thể request không được xử lý. Kiểm tra job/delivery state, source health, timing, policy và test again trong sandbox sau khôi phục.

### Bài tập J — Một secret thật xuất hiện trong error response

Trong lúc test API, response vô tình hiển thị một token có vẻ còn active.

**Gợi ý:** Dừng thao tác, lưu masked minimal proof, escalate theo RoE/incident policy; owner xác minh, rotate/revoke và đánh giá scope. Không thử token lên services khác.

### Bài tập K — “Có account mới khai thác được” nên Low

Tenant A có thể đọc dữ liệu B sau khi đăng nhập account miễn phí.

**Gợi ý:** Một authenticated attacker vẫn là actor hợp lệ; impact Confidential cross-tenant có thể cao. Đánh giá sign-up availability, scope và business impact, không tự hạ severity vì cần login.

### Bài tập L — Test làm tăng queue backlog

Team định gửi hàng trăm export requests cùng lúc để chứng minh thiếu rate limiting trên production.

**Gợi ý:** Đây có thể là load/DoS risk, cần approval và guardrails riêng. Dùng low-volume policy checks, sandbox, synthetic jobs và stop conditions; không gây disruption ngoài RoE.

### Bài tập M — Pentest trên staging nhưng báo production PASS

Staging dùng storage local, production dùng CDN signed links; cùng code API.

**Gợi ý:** Không có environment equivalence cho download control. Báo scope-limited staging outcome; bổ sung effective production policy evidence hoặc approved production test.

### Bài tập N — Root cause suy diễn từ bên ngoài

User A nhận dữ liệu B; tester viết finding “SQL query thiếu WHERE tenant_id” dù không có source/DB evidence.

**Gợi ý:** Viết confirmed **cross-tenant access violation**; SQL missing filter là hypothesis. Owner có thể tìm root cause ở cache, worker hoặc query; tránh sửa sai lớp.

### Bài tập O — Fix merged nhưng không triển khai

Đội dev sửa AuthZ trong source, CI chạy green; cluster production vẫn chạy image cũ.

**Gợi ý:** Trạng thái FIXED_IN_SOURCE nhưng chưa VERIFIED_FIXED. Cần deploy approved artifact, route/version inventory và retest positive/negative trên runtime.

### Bài tập P — Tỷ lệ 95% tests PASS

38/40 tests đạt; hai failures là cross-tenant export và admin role update trái phép.

**Gợi ý:** Không kết luận “95% secure”. Hai failures ảnh hưởng security invariants material; quyết định release/risk phải theo impact và critical gates, không theo trung bình.

### Bài tập Q — Token bị revoke nhưng vẫn dùng được ngắn hạn

Trong sandbox, token cũ còn truy cập API 45 giây sau revoke. Yêu cầu sản phẩm quy định tối đa 60 giây.

**Gợi ý:** So timestamps và approved semantics; chưa chắc đây là FAIL nếu trong window được phê duyệt. Tuy nhiên cần test các API critical actions, clock skew/cache và khả năng attacker abuse trong window, có risk decision rõ.

### Bài tập R — Test không phát hiện sự kiện audit

Một unauthorized operation bị chặn ở API nhưng SIEM không có event; collector health hiển thị source inactive.

**Gợi ý:** Prevention result có thể PASS cho path, nhưng detection assurance UNKNOWN/FAIL tùy requirement. Ghi riêng source outage và retest canary sau remediation.

## 55. Kết luận

**Black-box penetration testing** là một cách quan sát hệ thống từ vị trí của tác nhân được mô phỏng, chủ yếu qua **các giao diện đã triển khai**, mà không phụ thuộc vào khả năng đọc trước source code hay cấu hình nội bộ. Giá trị nổi bật của nó nằm ở việc kiểm tra **hành vi thực**: anonymous access, authentication/session lifecycle, object/function authorization, tenant isolation, business workflow, input validation, files/exports, async paths, public exposure và audit/monitoring.

Trong **SECURITY_SECURITY_ASSURANCE**, kiểm thử hộp đen chỉ có ý nghĩa khi được đặt trong **ủy quyền và Rules of Engagement rõ ràng**, sử dụng dữ liệu thử an toàn, có **preconditions, expected outcomes và observed evidence**. Những kết quả phát hiện phải truy vết về **security requirements, assets, threat hypotheses, business impact, controls, findings, remediation và retest**; những gì chưa kiểm hoặc không thể quan sát phải được báo là **INCONCLUSIVE/UNKNOWN/OUT_OF_SCOPE**, không che bằng kết luận “không có lỗ hổng”.

Một report tốt tách **factual observations** khỏi **root-cause hypotheses**, phân biệt server response với downstream side effects, gắn kết quả với **release/roles/tenants/environment/time window**, và bảo vệ dữ liệu nhạy cảm trong evidence. Black-box pentest không thay threat modeling, secure code review, SAST/SCA, cloud policy assessment hay operational assurance; nó bổ sung bằng chứng về những điều mà người dùng hoặc attacker với quyền cụ thể **thực sự có thể làm**.

**Mục tiêu cuối cùng không phải tạo càng nhiều findings càng tốt, mà là phát hiện những vi phạm quan trọng, sửa đúng trust boundary, kiểm chứng việc khắc phục và liên tục cập nhật mức tin cậy khi hệ thống, dữ liệu, danh tính và rủi ro thay đổi.**
