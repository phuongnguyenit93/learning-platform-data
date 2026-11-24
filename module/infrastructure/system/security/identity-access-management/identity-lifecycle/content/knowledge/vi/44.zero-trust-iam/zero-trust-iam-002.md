# Verify explicitly — Xác minh tường minh trong Zero Trust IAM

> **Chương:** Zero Trust IAM  
> **Bài học:** Verify explicitly  
> **Phạm vi:** Quản lý vòng đời danh tính trong IAM theo **Joiner–Mover–Leaver (JML)**: xác minh danh tính, tạo tài khoản, cấp quyền, đánh giá lại và thu hồi khi vai trò thay đổi. Nội dung kết nối Identity Provider (IdP), Single Sign-On (SSO), SCIM, RBAC/ABAC, danh tính máy, kiểm toán và ngăn quyền truy cập tồn dư.

## 1. Mục tiêu học tập

Sau bài học, người học có thể:

1. Giải thích nguyên tắc **Verify explicitly**: quyết định truy cập phải dựa trên bằng chứng và chính sách hiện hành, không dựa vào sự tin cậy ngầm từ mạng nội bộ hoặc một phiên đăng nhập trong quá khứ.
2. Phân biệt **xác minh danh tính ban đầu (identity proofing)**, **xác thực (authentication)**, **phân quyền (authorization)** và **kiểm tra ngữ cảnh/rủi ro**.
3. Chỉ ra các tín hiệu cần xác minh cho một yêu cầu cụ thể: chủ thể, danh tính/token, trạng thái vòng đời, tài nguyên, hành động, thiết bị, phiên và mức độ rủi ro.
4. Phác thảo luồng ra quyết định giữa IdP, PEP, PDP, nguồn thuộc tính, hệ thống quản lý vòng đời và ứng dụng.
5. Xử lý tình huống Joiner, Mover, Leaver khi quyền, token hoặc đồng bộ tài khoản không cập nhật cùng lúc.
6. Đề xuất cách kiểm thử, ghi log và đo hiệu quả xác minh tường minh mà vẫn giảm lộ thông tin riêng tư và gián đoạn nghiệp vụ.

## 2. Verify explicitly có nghĩa là gì?

Trong Zero Trust, **Verify explicitly** có thể hiểu là:

> Khi một chủ thể yêu cầu thực hiện một hành động trên tài nguyên, hệ thống phải kiểm tra các bằng chứng phù hợp và áp dụng chính sách trước khi cho phép. Mức kiểm tra tương ứng với độ nhạy của hành động, trạng thái danh tính và rủi ro hiện tại.

Ví dụ, nhân viên Mai đăng nhập SSO thành công lúc 08:00 từ máy công ty. Đến 10:00, Mai yêu cầu xuất dữ liệu khách hàng. Hệ thống vẫn phải hỏi:

- Token/phiên còn hợp lệ, có dành cho API này và được phát hành bởi nguồn đáng tin không?
- Danh tính Mai hiện còn active, hợp đồng/quan hệ công việc còn hiệu lực không?
- Mai có **quyền xuất dữ liệu**, hay chỉ có quyền xem hồ sơ trong phạm vi được giao?
- Dữ liệu có thuộc đúng tenant, dự án và mức độ nhạy cảm mà Mai được phép truy cập không?
- Thiết bị, mức xác thực phiên và tín hiệu rủi ro có đáp ứng chính sách của thao tác **export** không?
- Quyền của Mai có vừa bị thay đổi do chuyển nhóm, kết thúc hợp đồng hoặc quyết định thu hồi khẩn cấp không?

Đăng nhập hợp lệ giúp xác định danh tính, nhưng không trả lời đầy đủ các câu hỏi về **phạm vi quyền tại thời điểm sử dụng**.

### Ba điều nguyên tắc này không đồng nghĩa

| Cách hiểu sai | Cách hiểu đúng |
|---|---|
| “Verify explicitly = nhập mật khẩu/MFA ở mọi request.” | Dịch vụ **đánh giá điều kiện cho phép ở mỗi điểm thực thi chính sách cần thiết**; người dùng có thể tái sử dụng phiên được quản lý và chỉ cần step-up ở hành động rủi ro cao. |
| “Có JWT hợp lệ là có quyền.” | JWT hợp lệ xác nhận một số phát biểu của bên phát hành; phải kiểm tra **audience, chính sách, tài nguyên, action và trạng thái quyền**. |
| “Dùng VPN, mạng nội bộ hoặc thiết bị công ty là đáng tin.” | Mạng/thiết bị là **tín hiệu ngữ cảnh**, không tự tạo ra quyền truy cập. |

**Verify explicitly là quá trình ra quyết định dựa trên nhiều tín hiệu**, không phải tăng số lần người dùng phải đăng nhập. Kiến trúc có thể sử dụng đánh giá lại theo từng yêu cầu, theo phiên, theo sự kiện thay đổi rủi ro và theo yêu cầu nâng mức xác thực, tùy chính sách; điều quan trọng là không để một bằng chứng đã cũ kéo dài quyền truy cập trái phép.

## 3. Xác minh điều gì? Mô hình sáu lớp

Một quyết định truy cập có thể diễn tả:

**Decision = Policy(subject, authentication, resource, action, context, current lifecycle state)**

Công thức trên là mô hình tư duy, không phải một API tiêu chuẩn. Sáu lớp được xem xét như sau.

| Lớp cần xác minh | Câu hỏi | Nguồn bằng chứng ví dụ | Hệ quả nếu bỏ qua |
|---|---|---|---|
| **1. Danh tính chủ thể** | Ai, ứng dụng hoặc workload nào đang gọi? | Subject ID, IdP, workload identity, chứng chỉ dịch vụ | Nhầm người dùng, tài khoản dùng chung không truy vết được |
| **2. Bằng chứng xác thực/phiên** | Bằng chứng có đáng tin, còn hạn và dành đúng hệ thống không? | OIDC/SAML, access token, MFA, thời điểm xác thực, sender constraint | Chấp nhận token giả, token sai đối tượng nhận hoặc phiên bị chiếm quyền |
| **3. Trạng thái vòng đời** | Danh tính hiện đang active, thuộc vai trò nào, còn quan hệ hợp lệ không? | HRIS, hệ thống IAM, IdP, sự kiện JML, dữ liệu quyền hiện tại | Mover/Leaver vẫn dùng quyền cũ |
| **4. Tài nguyên và hành động** | Người gọi muốn làm gì trên đúng tài nguyên nào? | Record owner, tenant, classification, quyền đọc/ghi/duyệt | BOLA/IDOR, xuất dữ liệu chéo tenant, thao tác ngoài trách nhiệm |
| **5. Ngữ cảnh và rủi ro** | Điều kiện truy cập có phù hợp với độ nhạy không? | Mức tin cậy thiết bị, kiểu đăng nhập, dấu hiệu bất thường, thời gian, nguồn kết nối | Hành động rủi ro cao diễn ra với bằng chứng yếu |
| **6. Chính sách và nghĩa vụ** | Quy tắc nào quyết định allow/deny/step-up, có điều kiện tiếp theo nào? | RBAC, ABAC, chính sách phân tách nhiệm vụ, phê duyệt, logging | Hành vi tùy ý theo từng dịch vụ, khó kiểm toán |

Không phải mọi request đều cần thu thập mới toàn bộ sáu lớp. Nhiều bằng chứng có thể được phát hành sẵn hoặc lưu cache có kiểm soát. Tuy nhiên phải xác định **độ mới (freshness), độ tin cậy, thời hạn sử dụng và cách vô hiệu hóa** từng nguồn, nhất là tín hiệu dễ thay đổi như user status hoặc role.

### Ví dụ so sánh mức kiểm tra

| Hành động | Bằng chứng tối thiểu minh họa | Có thể yêu cầu thêm |
|---|---|---|
| Xem trang thông báo chung của công ty | Phiên hợp lệ, nhân viên active | Không cần step-up trong điều kiện thông thường |
| Đọc ticket khách hàng | Phiên hợp lệ, role support, đúng tenant và được giao ticket | Thiết bị đáp ứng yêu cầu xử lý dữ liệu khách hàng |
| Xuất toàn bộ hồ sơ khách hàng | Role riêng cho export, phạm vi dữ liệu được duyệt | MFA chống phishing mới thực hiện, phê duyệt hoặc giới hạn số lượng |
| Duyệt thanh toán | Role finance approver, phân tách người tạo/người duyệt | Xác thực tăng cường và ngữ cảnh thiết bị đạt yêu cầu |
| Triển khai lên production bằng CI/CD | Workload identity tin cậy, repo/branch/environment được phép | Artifact attestation, phê duyệt hoặc bằng chứng provenance theo chính sách |

Các điều kiện trên là ví dụ học tập. Chính sách thật phải được xây dựng từ phân loại dữ liệu, mô hình đe dọa, khả năng kỹ thuật và yêu cầu pháp lý của tổ chức.

## 4. Phân biệt các bước kiểm chứng danh tính

### 4.1. Identity proofing: đúng người ngay từ đầu

Khi một nhân viên mới được onboarding, tổ chức cần xác nhận danh tính, tính hợp lệ của hợp đồng và người bảo trợ hoặc quản lý tương ứng. Mức độ kiểm chứng tùy rủi ro và loại danh tính: nhân viên chính thức, nhà thầu, đối tác và người dùng bên ngoài có thể có luồng khác nhau.

**Bằng chứng cần liên kết với một subject ID bền vững** để giữ được lịch sử khi email, họ tên hay phòng ban thay đổi. Không nên dùng địa chỉ email làm khóa duy nhất cho mọi nghiệp vụ: email có thể đổi hoặc tái sử dụng. Việc tổ chức xác minh danh tính đầu vào tạo nền tảng đáng tin hơn cho các lần xác thực về sau, nhưng không thay thế kiểm tra quyền ở runtime.

### 4.2. Authentication: chứng minh ai đang sử dụng danh tính

IdP có thể xác thực bằng passkey, khóa bảo mật, MFA hoặc các cơ chế được hỗ trợ. Cần xem xét:

- Phương thức và **mức bảo đảm xác thực**, khả năng chống phishing và nguy cơ chiếm phiên.
- Thời điểm thực hiện xác thực; thao tác nhạy cảm có thể cần xác thực lại gần thời điểm hành động.
- Thiết bị hoặc client có đáp ứng các điều kiện gắn với chính sách phiên không.
- Kết quả đăng nhập có được truyền tới ứng dụng thông qua giao thức, cấu hình và quan hệ tin cậy đúng không.

**MFA không thay thế authorization**: một người dùng được xác thực rất mạnh vẫn có thể không được phép đọc hồ sơ của tenant khác.

### 4.3. Authorization: có được phép làm hành động này không?

Phân quyền phải gắn với **action cụ thể và tài nguyên thực tế**. Vai trò nền tảng (RBAC) quy định nhóm khả năng; thuộc tính và quan hệ (ABAC, kiểm tra ownership/membership) giới hạn các khả năng đó theo tenant, vùng dữ liệu, loại bản ghi, ngữ cảnh và thời hạn.

Ví dụ cùng vai trò finance_analyst:

- Được xem hóa đơn thuộc pháp nhân A mà người dùng phụ trách.
- Bị từ chối đọc hóa đơn thuộc pháp nhân B.
- Bị từ chối duyệt khoản thanh toán, vì action approve không nằm trong quyền analyst.

Vì vậy, không nên áp dụng một kiểm tra “người gọi thuộc nhóm Finance?” rồi dùng kết quả cho mọi endpoint.

### 4.4. Continuous/adaptive evaluation: phát hiện bằng chứng đã thay đổi

Khi một phiên đang diễn ra, trạng thái có thể đổi: người dùng bị khóa, thiết bị mất tuân thủ, vai trò bị thu hồi, mức rủi ro tăng. Kiến trúc cần có **điểm đánh giá lại** ở những quyết định phù hợp, có thể dựa vào sự kiện, tuổi token, tra cứu trạng thái, introspection hoặc khả năng đánh giá phiên của nền tảng.

“Continuous” không nhất thiết là liên tục hỏi IdP mỗi mili giây. Đó là khả năng **không giữ niềm tin cũ vô hạn định** và phản ứng theo rủi ro với tốc độ đáp ứng yêu cầu nghiệp vụ.

## 5. Chuỗi tin cậy và luồng ra quyết định

Trong kiến trúc Zero Trust, các thành phần sau thường tham gia:

- **Nguồn vòng đời**: HRIS, hệ thống quản lý hợp đồng, quyết định phân công, hoặc registry workload; cung cấp sự kiện Joiner–Mover–Leaver.
- **IAM/IdP**: duy trì trạng thái user, phương thức xác thực, nhóm, phiên và thuộc tính được quản trị.
- **SCIM/API provisioning**: đồng bộ user/group/trạng thái sang ứng dụng đích; có thể xử lý bất đồng bộ.
- **Policy Enforcement Point (PEP)**: điểm chặn request hoặc phiên để thi hành quyết định.
- **Policy Decision Point (PDP)**: đánh giá chính sách dựa trên subject, resource, action, context và nguồn thuộc tính.
- **Policy Administrator (PA)**: trong mô hình kiến trúc NIST, hỗ trợ thiết lập hoặc chấm dứt kết nối/đường truy cập theo quyết định chính sách.
- **Ứng dụng/tài nguyên**: lưu thuộc tính đáng tin của tài nguyên; thực thi kiểm tra ở mức đối tượng khi cần.
- **Telemetry/audit**: thu nhận quyết định truy cập và thay đổi của các nguồn vòng đời.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng / Workload
    participant I as IdP / Workload IdP
    participant E as PEP (Gateway/API)
    participant D as PDP / Policy Engine
    participant A as Thuộc tính & trạng thái hiện tại
    participant R as Resource Service
    participant L as Audit

    U->>I: Nhận bằng chứng xác thực/phiên phù hợp
    I-->>U: Token hoặc credential
    U->>E: Yêu cầu action trên resource
    E->>E: Xác minh credential, issuer, audience, hạn
    E->>D: Subject, action, resource, context
    D->>A: Lấy trạng thái JML, role, tenant, rủi ro
    A-->>D: Thuộc tính với độ mới/nguồn tin cậy
    D-->>E: Allow / Deny / Step-up + obligations
    E->>L: Ghi policy decision
    alt Cho phép và đáp ứng nghĩa vụ
        E->>R: Chuyển yêu cầu đã kiểm tra
        R->>R: Kiểm tra object/tenant cho thao tác thật
        R-->>U: Kết quả được phép
    else Từ chối hoặc cần xác thực tăng cường
        E-->>U: Deny hoặc yêu cầu step-up
    end
~~~

Sơ đồ biểu diễn trách nhiệm logic, không bắt buộc mọi tổ chức phải có một PDP dịch vụ riêng. PDP có thể được nhúng trong ứng dụng, dùng engine dùng chung hoặc kết hợp nhiều lớp. **Điểm kiểm tra ở gateway không tự động bảo vệ quyền ở cấp bản ghi**; dịch vụ cuối cùng phải kiểm tra thuộc tính tài nguyên đáng tin mà nó sử dụng.

### Một vòng đời dữ liệu bằng chứng cần trả lời được

1. **Ai phát hành?** Ví dụ: IdP có hợp đồng tin cậy, HRIS được ủy quyền, hệ thống quản trị thiết bị đã đăng ký.
2. **Bằng chứng nói về ai/cái gì?** Subject ID, service principal, device ID, resource ID phải liên kết đúng.
3. **Bằng chứng chứng minh điều gì?** MFA chứng minh một sự kiện xác thực; role biểu đạt quyền được cấp; kết quả EDR là tín hiệu thiết bị; không đánh đồng phạm vi các phát biểu.
4. **Có còn mới không?** Role đã đổi? Thiết bị còn tuân thủ? Token chưa hết hạn nhưng trạng thái tài khoản đã bị khóa?
5. **Có thể giả mạo hoặc sửa đổi không?** Chỉ nhận thuộc tính từ nguồn đáng tin, xác minh chữ ký hoặc đường truyền; không lấy quyết định quyền từ JSON/HTTP header do client tự điền.
6. **Phản ứng khi bằng chứng vắng mặt?** Tác vụ nhạy cảm phải có hành vi từ chối hoặc yêu cầu bằng chứng bổ sung theo chính sách; không ngầm allow vì dịch vụ kiểm tra lỗi.

## 6. Verify explicitly trong IdP, SSO, OIDC, SAML và OAuth 2.0

### 6.1. SSO và IdP xác thực tập trung, nhưng không quyết định mọi quyền

SSO giảm số lần người dùng nhập thông tin đăng nhập và giúp áp dụng chính sách xác thực thống nhất. Tuy nhiên, một ứng dụng vẫn cần kiểm soát người dùng được phép xem/sửa **tài nguyên của ứng dụng**.

Với OpenID Connect, **ID token** mô tả sự kiện xác thực và thông tin liên quan đến người dùng cho client tương ứng. Với OAuth 2.0, **access token** được dùng để truy cập resource server theo phạm vi/đối tượng nhận. Không nên dùng ID token như một bearer access token mặc định cho API. SAML assertion có ngữ nghĩa riêng, thường dùng cho đăng nhập liên kết; ứng dụng phải kiểm tra các ràng buộc của assertion tương ứng.

### 6.2. Resource server cần xác minh access token thế nào?

Kiểm tra cụ thể tùy loại token và giao thức; với JWT access token đã ký, thường gồm:

1. **Chữ ký và thuật toán được phép**: dùng khóa từ issuer đã cấu hình; tránh thuật toán không mong đợi hoặc chấp nhận token không ký.
2. **Issuer (iss)**: khớp nhà phát hành tin cậy, không lấy tùy ý từ claim rồi tự tin tưởng.
3. **Audience (aud)**: token dành đúng API/tài nguyên nhận; không chấp nhận token cấp cho dịch vụ khác.
4. **Thời gian (exp, nbf, iat khi áp dụng)**: token còn hạn và trong khoảng hợp lệ; sai lệch đồng hồ được cấu hình chặt.
5. **Loại và ngữ nghĩa token**: xem token có đúng là loại access token mà API kỳ vọng; kiểm tra client, scope và sender constraint khi có quy định.
6. **Trạng thái và authorization**: xem user/workload còn active, quyền thực tế còn hiệu lực, action/resource hiện tại nằm trong phạm vi chính sách hay không.

Nếu access token là **opaque token**, resource server thường dùng cơ chế xác minh/introspection tương ứng thay vì cố phân tích JWT. Một token có scope “invoice.read” không có nghĩa tất cả invoice đều được phép đọc: phải kiểm tra tenant, owner hoặc quan hệ được ủy quyền.

**Giới hạn quan trọng:** chỉ kiểm tra chữ ký và thời hạn không bảo đảm thu hồi tức thời. Nếu token tự chứa vẫn còn hạn, API chỉ dùng dữ liệu claim cũ có thể cho phép quyền đã bị thu hồi. Cần thiết kế biện pháp cho nguồn trạng thái thay đổi nhanh: token ngắn hạn, hủy refresh token/phiên, introspection, claim phiên có độ mới phù hợp, event-driven revocation hoặc tra cứu quyền hiện tại ở những endpoint nhạy cảm.

### 6.3. Xác minh “người đang giữ token” khi có rủi ro bị đánh cắp

Bearer token bị lộ có thể bị kẻ khác dùng đến khi hết hạn hoặc bị thu hồi. Với các luồng thích hợp, có thể cân nhắc **sender-constrained token** (ví dụ mTLS hoặc DPoP trong những mô hình hỗ trợ), để token gắn với bằng chứng sở hữu khóa của bên gọi. Cơ chế này giảm rủi ro phát lại nhưng không thay thế chính sách authorization, bảo vệ khóa riêng, kiểm tra thời gian/đối tượng nhận hoặc quản lý vòng đời.

## 7. Chính sách quyết định: RBAC + ABAC + ngữ cảnh

Một chính sách truy cập tốt có đủ ba đặc điểm: **rõ đầu vào**, **rõ kết quả**, và **rõ trạng thái khi thiếu bằng chứng**.

Giả sử API CRM có hành động export customer data. Chính sách mô tả:

~~~yaml
# Ví dụ khái niệm, KHÔNG phải cấu hình trực tiếp của sản phẩm IAM.
policy_id: crm.customer.export
version: 3
request:
  subject: user-482
  resource: dataset-customer-01
  action: customer.export
requirements:
  identity:
    status: active
    employment_relation: valid
  authorization:
    required_role: crm_exporter
    subject_tenant_matches_resource: true
    approved_data_scope: true
  session:
    phishing_resistant_mfa: required
    max_authentication_age_minutes: 15
  device:
    compliance: required
  risk:
    max_risk_level: medium
  safeguards:
    export_approval: required
fallback:
  missing_required_signal: deny
  policy_evaluation_error: deny
outcomes:
  permit: allow
  additional_authentication_needed: step_up
  otherwise: deny
~~~

**Giải thích:** user có role crm_exporter vẫn có thể bị từ chối khi xuất dữ liệu thuộc tenant khác, tài khoản đã bị inactive hoặc thiết bị mất trạng thái compliant. “15 phút”, “medium” và yêu cầu phê duyệt chỉ là giá trị minh họa; không có ngưỡng an toàn cố định cho mọi hệ thống.

### Đánh giá chính sách bằng tư duy “nghĩa vụ” (obligations)

Một PDP có thể đưa ra:

- **Allow**: các điều kiện được thỏa; PEP thực thi và vẫn kiểm tra quyền tài nguyên ở lớp thích hợp.
- **Deny**: không đủ quyền, sai tenant, danh tính bị vô hiệu hóa hoặc điều kiện bắt buộc không đạt.
- **Step-up / challenge**: cần MFA mạnh hơn, xác thực lại hoặc chứng minh điều kiện bổ sung.
- **Require approval / constrained allow**: tùy kiến trúc, có thể yêu cầu phê duyệt hoặc giới hạn hành động trước khi cho phép.

Trong triển khai thực tế, nhiều policy engine chỉ trả về Permit/Deny/Indeterminate/NotApplicable, còn ứng dụng tự quy đổi sang step-up hoặc workflow phê duyệt. Không giả định tất cả PDP đều có API “step_up” sẵn.

### Pseudocode cho API xử lý request

~~~text
function readInvoice(request):
    token = validateAccessToken(
        request.authorization,
        trustedIssuer,
        expectedAudience = "invoice-api"
    )
    if token.invalid:
        return UNAUTHORIZED

    invoice = trustedDatabase.getInvoice(request.invoiceId)
    if invoice.notFound:
        return NOT_FOUND

    subject = identityStore.getCurrentState(token.subjectId)
    context = collectTrustedContext(request, token)

    decision = policy.evaluate(
        subject = subject,
        resource = invoice.authorizationAttributes,
        action = "invoice.read",
        context = context
    )

    audit(decision, subject.id, invoice.id, policy.version)

    if decision.requiresStepUp:
        return AUTHENTICATION_CHALLENGE
    if not decision.permit:
        return FORBIDDEN

    return invoice.toPermittedView(subject)
~~~

Đây là pseudocode để mô tả thứ tự trách nhiệm, chưa phải mã production. API cần xử lý thêm lỗi nguồn dữ liệu, kiểm soát lộ thông tin khi trả về mã lỗi, phân trang/lọc theo quyền, race condition và audit có bảo vệ. Tài nguyên và tenant phải lấy từ nguồn backend tin cậy, không từ tham số user tự khẳng định.

## 8. Thay đổi JML làm “bằng chứng hợp lệ” thay đổi ra sao?

Trong quản lý vòng đời danh tính, Verify explicitly đặc biệt quan trọng vì **quyền hôm qua có thể không còn hợp lệ hôm nay**.

### 8.1. Joiner: kiểm chứng trước khi cấp quyền

Kịch bản: Huy là nhà thầu mới nhận dự án trong 30 ngày.

1. Nguồn hợp đồng đã phê duyệt ghi nhận Huy, người bảo trợ, ngày bắt đầu/kết thúc và phạm vi dự án.
2. IAM tạo subject ID riêng, ràng buộc bằng chứng danh tính, yêu cầu phương thức xác thực phù hợp.
3. Gán nhóm theo vai trò/dự án, đồng bộ tài khoản ứng dụng qua SCIM hoặc API với quyền có thời hạn.
4. Khi Huy truy cập tài liệu, policy kiểm tra: tài khoản active, hợp đồng còn hiệu lực, tài liệu thuộc đúng dự án, action được phép.
5. Trước ngày bắt đầu, sau ngày kết thúc hoặc khi phạm vi được thay đổi, quyết định sẽ chuyển sang deny cho hành động ngoài quyền hiện tại.

**Điều cần tránh:** cấp quyền truy cập production chỉ vì danh tính đã được tạo thành công ở IdP. Kết quả identity proofing và provisioning là bước đầu của chuỗi tin cậy, không phải giấy phép chung.

### 8.2. Mover: kiểm chứng lại sau chuyển vai trò

Kịch bản: Ngọc chuyển từ Sales sang Finance lúc 09:00, nhưng access token CRM được phát hành lúc 08:50 và hết hạn lúc 10:50.

Nếu API CRM dựa hoàn toàn vào claim role=sales trong token, Ngọc có thể tiếp tục xem báo cáo Sales trong gần hai giờ mặc dù không còn được phép. Để kiểm soát:

1. Hệ thống nguồn phát sự kiện Mover có thời điểm hiệu lực và vai trò mới.
2. IAM tính lại **desired entitlements**, xóa quyền Sales không còn cần và cấp quyền Finance theo phê duyệt.
3. Đồng bộ nhóm/tài khoản ứng dụng; giám sát xác nhận từ đích, lỗi và retry.
4. Các điểm kiểm soát truy cập áp dụng trạng thái mới bằng cơ chế thu hồi/cập nhật phiên hoặc tra cứu quyền hiện tại theo yêu cầu. Có phương án chặn tạm thời với tài nguyên nhạy cảm nếu đồng bộ chưa hoàn tất.
5. Kiểm thử cả hai chiều: Ngọc không xem được dữ liệu Sales đã thu hồi, nhưng sử dụng được tài nguyên Finance đã được phê duyệt.

Nguyên tắc ở đây là **không cộng dồn vô thời hạn quyền cũ và mới**. Sự chuyển đổi vai trò phải được phản ánh tại **lúc kiểm tra request**, không chỉ trong một bản ghi thay đổi của phòng nhân sự.

### 8.3. Leaver: xác minh quyền chặn sau khi rời tổ chức

Kịch bản: Nhà thầu dừng hợp đồng lúc 18:00 nhưng còn phiên ứng dụng, refresh token và API key cá nhân.

Các bước cần có:

- Đặt trạng thái danh tính không còn được sử dụng theo thời điểm hiệu lực, chặn lần đăng nhập mới.
- Kết thúc phiên IdP và phiên ứng dụng khi nền tảng hỗ trợ; thu hồi refresh token hoặc quyền ủy quyền phù hợp.
- Thu hồi quyền/group, khóa tài khoản tại các ứng dụng đích qua SCIM/API, đặc biệt là ứng dụng không đi qua SSO.
- Kiểm kê và thu hồi API key, PAT, SSH key, secret hoặc ủy quyền được tạo cho cá nhân đó; chuyển automation hợp lệ sang workload identity do tổ chức quản lý.
- Đối soát kết quả và kiểm thử khả năng truy cập còn tồn dư; nếu đích chưa xác nhận thu hồi, tạo cảnh báo và xử lý theo mức độ ưu tiên.
- Lưu bằng chứng audit theo chính sách; việc chặn truy cập không đồng nghĩa phải xóa ngay toàn bộ dữ liệu nghiệp vụ.

**Tình huống dễ bỏ sót:** IdP khóa user nhưng token JWT tự chứa vẫn được một API offline chấp nhận, hoặc tài khoản SaaS có mật khẩu riêng tiếp tục đăng nhập. Kết quả thu hồi cần được đánh giá **tại nơi dữ liệu thực sự được truy cập**.

### Ma trận bằng chứng theo JML

| Tín hiệu cần cập nhật | Joiner | Mover | Leaver |
|---|---|---|---|
| Trạng thái danh tính | Tạo và active theo hiệu lực | Vẫn active nhưng vai trò/thuộc tính đổi | Disabled/revoked theo chính sách |
| Vai trò/phạm vi | Quyền tối thiểu ban đầu | Xóa quyền cũ, gán quyền mới | Xóa/khóa quyền được ủy quyền |
| Phiên/token | Cấp khi đủ yêu cầu | Làm mất hiệu lực quyền cũ trong giới hạn SLA | Chặn phiên/refresh token, giới hạn access token tồn dư |
| Ứng dụng đích | Provision có xác nhận | Đồng bộ và đối soát thay đổi | Deprovision và xác nhận từng đích |
| Điểm kiểm tra runtime | Kiểm tra hợp đồng và phạm vi | Kiểm tra quyền hiện tại | Từ chối theo trạng thái đã thu hồi |
| Audit | Ai phê duyệt việc tạo/quyền | Ai yêu cầu, quyền nào thay đổi | Khi nào truy cập bị chặn trên từng hệ thống |

## 9. Verify explicitly cho service account và workload identity

Danh tính không chỉ là con người. Các máy chủ, pod, pipeline CI/CD, job nền và API client cũng cần được xác minh tường minh.

Một request **service-to-service** cần kiểm chứng:

- **Danh tính workload:** workload được phát hành danh tính bằng cơ chế nào, thuộc cluster/namespace/project nào; có thể dùng federation dựa trên nền tảng, identity ngắn hạn hoặc mTLS phù hợp.
- **Ràng buộc workload thực:** credential có được cấp cho đúng workload và audience đích không; có điều kiện về môi trường hoặc nguồn gọi không.
- **Quyền:** service A được gọi endpoint cụ thể của service B với action và data scope nào; tránh quyền admin dùng chung.
- **Vòng đời:** workload còn được triển khai hợp lệ, service account có owner, credential có ngày hết hạn/rotation và bị thu hồi khi ứng dụng ngừng hoạt động.
- **Ghi nhận:** nhật ký có service principal ID và correlation ID để quy trách nhiệm, không chứa secret.

Ví dụ pipeline triển khai:

~~~text
Git repository -> CI runner -> workload identity federation
                                  |
                                  v
                         short-lived credential
                                  |
                                  v
                    Deployment API / policy check
                    - repo và branch được phép?
                    - môi trường production?
                    - artifact có đủ bằng chứng?
                    - workflow/job còn được ủy quyền?
                    - phê duyệt có cần thiết?
                                  |
                           allow hoặc deny
~~~

Một API key quyền admin được chia sẻ cho mọi pipeline tạo ra “điểm tin cậy ngầm” kéo dài và khó thu hồi. Nếu chưa thể loại bỏ secret dài hạn, cần giới hạn scope, tách môi trường, lưu trong hệ thống quản lý secret, rotation và cảnh báo sử dụng bất thường.

**Mạng nội bộ/mTLS hỗ trợ xác minh kết nối và giảm di chuyển ngang**, nhưng không tự cấp quyền nghiệp vụ. Service đã xác thực vẫn có thể bị từ chối khi gọi dữ liệu của tenant khác.

## 10. Độ mới, cache và các thời điểm phải xác minh lại

Xác minh tường minh phụ thuộc không chỉ *giá trị* của tín hiệu mà còn *khi nào tín hiệu còn đáng tin*.

| Loại bằng chứng | Tốc độ thay đổi điển hình | Cách quản lý độ mới |
|---|---|---|
| Subject ID, hệ thống phát hành đáng tin | Hiếm thay đổi | Bảo vệ ánh xạ và khóa nhận diện; không tái sử dụng ID tùy tiện |
| Trạng thái active/inactive, role, quan hệ hợp đồng | Có thể đổi ngay khi JML xảy ra | Sự kiện cập nhật, kiểm tra trạng thái, version/revocation hoặc cache ngắn theo rủi ro |
| Access token | Có thời điểm cấp/hết hạn | Xác minh hạn, audience, thu hồi khi hỗ trợ; giới hạn tuổi theo độ nhạy |
| Mức xác thực/MFA | Liên quan phiên xác thực | Dùng timestamp/mức xác thực có nguồn tin cậy; step-up khi cần |
| Trạng thái thiết bị và tín hiệu rủi ro | Có thể đổi nhanh | Tín hiệu có thời hạn, cơ chế cập nhật và chính sách khi không có dữ liệu |
| Thuộc tính resource/tenant/ownership | Đổi theo nghiệp vụ | Đọc từ nguồn authoritative gần với thời điểm quyết định, tránh dữ liệu client |

### Ví dụ về khoảng hở thu hồi

- 09:00 — HRIS phát sự kiện Ngọc chuyển vai trò; quyền Sales bị thu hồi.
- 09:01 — IdP cập nhật group mới.
- 09:02 — Ứng dụng CRM chưa nhận SCIM.
- 09:10 — Ngọc gọi CRM API với token phát hành trước 09:00.
- 10:00 — Token cũ mới hết hạn.

**Kết quả phụ thuộc vào thiết kế:** nếu CRM chỉ kiểm tra chữ ký và claim cũ, yêu cầu 09:10 có thể được cho phép. Nếu CRM kiểm tra quyền hiện tại qua nguồn đủ mới hoặc đã thực thi thu hồi phiên/token thích hợp, request sẽ bị từ chối.

Không có một TTL phù hợp cho tất cả hệ thống. Khi chọn thời hạn cache và token, nên cân nhắc:

1. SLA thu hồi theo mức độ nhạy của tài nguyên và rủi ro của người dùng.
2. Độ trễ phát sự kiện từ nguồn JML đến các đích.
3. Độ tin cậy/sẵn sàng của nguồn thuộc tính và PDP.
4. Hiệu năng, khả năng chịu tải và mức độ khó chấp nhận gián đoạn.
5. Rủi ro khi sử dụng quyết định đã cache sau khi quyền bị thay đổi.

### Khi PDP hoặc IdP không khả dụng

Không biến lỗi hạ tầng thành quyền mặc định. Có thể quy định các chế độ:

- Với giao dịch nhạy cảm: **fail closed** hoặc yêu cầu xác minh tăng cường.
- Với thao tác ít rủi ro: cân nhắc dùng quyết định cache còn hạn và có phạm vi rất hẹp, nếu kiến trúc/chính sách cho phép.
- Với tình trạng thiếu tín hiệu bắt buộc: báo lỗi phù hợp, ghi log và cảnh báo thay vì tự điền “trusted”.
- Với nhu cầu vận hành khẩn cấp: dùng đường **break-glass** được kiểm soát, thời hạn, owner, xác thực mạnh và audit riêng.

Cần kiểm thử những chế độ này bằng tình huống thật, không chỉ trên tài liệu thiết kế.

## 11. Privacy, trải nghiệm người dùng và bảo vệ bằng chứng

Verify explicitly không cho phép thu thập vô hạn dữ liệu về người dùng. Mục tiêu là bằng chứng **đủ và liên quan** với quyết định truy cập.

- **Giảm dữ liệu:** chỉ sử dụng thuộc tính cần thiết cho chính sách; tránh thu vị trí chính xác nếu điều kiện mạng/thiết bị đã đủ.
- **Giới hạn mục đích:** bảo vệ thông tin về sức khỏe, vị trí và hành vi theo quy định áp dụng; không biến telemetry truy cập thành giám sát cá nhân không có mục đích rõ ràng.
- **Bảo vệ bí mật:** không log mật khẩu, bearer token, private key, recovery code hoặc dữ liệu khách hàng nguyên văn.
- **Giải thích được quyết định:** lưu reason code, policy ID/version và correlation ID để điều tra sự cố; tránh làm lộ chi tiết nhạy cảm cho client.
- **Trải nghiệm hợp lý:** step-up theo độ nhạy và trạng thái rủi ro; tránh gây MFA fatigue bằng các thử thách lặp đi lặp lại thiếu căn cứ.
- **Kênh hỗ trợ và khôi phục:** khi tín hiệu thiết bị bị lỗi hoặc người dùng đổi thiết bị, cung cấp quy trình khôi phục xác minh có kiểm soát và audit.

## 12. Kiểm thử Verify explicitly bằng các tình huống có thể quan sát

Một kiểm thử đạt yêu cầu không chỉ thấy API trả 200; nó chứng minh **bằng chứng, chính sách và kết quả** đúng với kịch bản.

| ID | Kịch bản kiểm thử | Kết quả mong đợi |
|---|---|---|
| T1 | Access token được cấp cho API A đem gọi API B | **Deny** vì audience sai |
| T2 | Token hợp lệ nhưng người dùng không có quyền invoice.read | **Deny** |
| T3 | Đúng role, sai tenant của invoice | **Deny** và không lộ dữ liệu tenant khác |
| T4 | Người dùng chuyển vai trò nhưng token vẫn chứa role cũ | **Deny** quyền cũ trong SLA thiết kế |
| T5 | Người dùng Leaver có refresh token hoặc local account còn lưu | Không đăng nhập/đổi token hoặc truy cập tài nguyên tiếp tục được sau thời điểm thu hồi yêu cầu |
| T6 | Người dùng active truy cập hành động nhạy cảm với MFA chưa đủ mức | **Step-up** hoặc **Deny** theo chính sách |
| T7 | Workload đúng danh tính nhưng gọi tài nguyên ngoài scope | **Deny** |
| T8 | PDP mất kết nối, request export dữ liệu khách hàng | **Deny**/fail closed theo thiết kế |
| T9 | SCIM lỗi khi gỡ quyền trên ứng dụng đích | Alert, retry và reconciliation; không đánh dấu đã thu hồi hoàn tất nếu chưa xác nhận |
| T10 | Request hợp lệ, nguồn tin cậy, role và tenant đúng, đáp ứng ngữ cảnh | **Allow**, ghi audit theo chính sách |

Khi kiểm thử T4/T5, cần xác nhận **tại ứng dụng đích** và đo thời gian từ sự kiện thay đổi đến khi quyền thực sự không thể sử dụng. Chỉ kiểm tra trạng thái “disabled” ở bảng user chưa chứng minh thu hồi thành công.

### Bản ghi audit minh họa

~~~json
{
  "timestamp": "2026-11-23T09:10:15Z",
  "event_type": "authorization_decision",
  "subject_id": "usr-482",
  "subject_lifecycle_version": 28,
  "resource_type": "invoice",
  "resource_id": "inv-2048",
  "action": "invoice.read",
  "decision": "deny",
  "reason_code": "ROLE_REVOKED",
  "policy_id": "finance.invoice.read",
  "policy_version": 7,
  "correlation_id": "req-a174"
}
~~~

Đây là mẫu thiết kế cho audit, không phải schema bắt buộc. Phiên bản vòng đời và policy version giúp truy tìm **quyết định đã dựa trên trạng thái nào**. Nếu lưu các thuộc tính chi tiết, cần kiểm soát quyền xem, tính toàn vẹn, retention và yêu cầu bảo vệ dữ liệu cá nhân.

### Chỉ số vận hành cần theo dõi

- **Revocation latency:** từ sự kiện Mover/Leaver đến khi API và ứng dụng nhạy cảm từ chối quyền cũ; đo p95/p99 và ngoại lệ vượt SLA.
- **Policy coverage:** tỷ lệ endpoint/hành động nhạy cảm có kiểm tra action + resource + subject + context phù hợp.
- **Authentication assurance coverage:** tỷ lệ thao tác rủi ro cao có kiểm tra mức xác thực/step-up theo yêu cầu.
- **Provisioning correctness:** chênh lệch desired/actual entitlements, số lần SCIM thất bại hoặc đích chưa xác nhận.
- **Orphaned identities:** người dùng, service account, local account và key không có owner hoặc không còn quan hệ hợp lệ.
- **Quality of decisions:** lỗi false deny, số lần policy thất bại, số phiên còn dùng quyền cũ sau thay đổi; cân bằng bảo mật và trải nghiệm.
- **Auditability:** tỷ lệ quyết định có subject/resource/action, policy version, reason code và correlation ID đủ điều tra.

Những chỉ số này nên có chủ sở hữu, ngưỡng cảnh báo, hành động khắc phục và chu kỳ rà soát. Tỷ lệ sử dụng SSO cao chưa nói lên độ đúng của kiểm tra quyền ở runtime.

## 13. Bài tập thực hành: một quyết định truy cập có đủ bằng chứng chưa?

**Bối cảnh**

Công ty triển khai ba ứng dụng: CRM, Finance và Data Lake. Tất cả người dùng đăng nhập qua IdP; SCIM đồng bộ user/group. Nhân viên Linh chuyển từ nhóm Support sang nhóm Finance lúc 14:00. Lúc 14:15, Linh dùng thiết bị cá nhân để thực hiện hai hành động:

- **A:** xem hóa đơn thuộc tenant của nhóm Finance, chỉ yêu cầu quyền đọc.
- **B:** xuất 50.000 bản ghi khách hàng từ CRM của nhóm Support cũ.

Hệ thống quan sát: access token CRM cấp lúc 13:55 còn hạn; nhóm tại IdP đã cập nhật lúc 14:01; CRM SCIM đang lỗi; mức compliance thiết bị **unknown**; phiên SSO được xác thực bằng mật khẩu và yếu tố thứ hai nhưng chưa có bằng chứng đạt chính sách cho export.

**Yêu cầu**

1. Xác định tín hiệu nào đáng tin, tín hiệu nào đã cũ hoặc chưa đủ cho A và B.
2. Đề xuất quyết định cho A và B; nêu dữ liệu cần kiểm tra thêm.
3. Thiết kế tối thiểu ba kiểm thử để xác nhận quyền Support cũ không còn sử dụng được.
4. Nêu cách xử lý khi SCIM tiếp tục lỗi mà không làm mất khả năng kiểm toán.
5. Đề xuất hai chỉ số đánh giá hiệu quả của biện pháp khắc phục.

**Gợi ý lời giải**

- **A:** Chưa thể tự động allow chỉ dựa vào việc Linh thuộc nhóm Finance. Cần biết action, tài nguyên hóa đơn đúng tenant, quyền thực tế đã có hiệu lực và yêu cầu thiết bị cho dữ liệu Finance. Nếu chính sách đọc hóa đơn đòi thiết bị compliant mà trạng thái là unknown, phải deny hoặc yêu cầu bước khắc phục/xác minh bổ sung. Nếu chính sách không đòi tín hiệu đó và các điều kiện khác đạt, có thể allow.
- **B:** Token cũ còn hạn không chứng minh quyền Support hiện tại. Hành động export nhạy cảm và quyền CRM đã bị thu hồi theo Mover; kết quả thích hợp là **deny**. Thiếu device compliance và mức xác thực cho export cũng là lý do không thể tự động allow.
- **Kiểm thử:** dùng token CRM cũ gọi export, gọi read ticket Support cũ, thử refresh token cũ, kiểm tra một tài khoản local đích nếu tồn tại và đo kết quả từng request; thử tình huống IdP/SCIM/PDP unavailable.
- **Khắc phục:** chặn quyền cũ ở PEP/PDP bằng trạng thái hiện hành hoặc cơ chế revocation, đặt cảnh báo cho lỗi SCIM, retry có kiểm soát, reconciliation và lưu thời điểm đích xác nhận.
- **Đo lường:** revocation latency p95 và số request được cho phép trái chính sách sau Mover; có thể thêm số ứng dụng chậm cập nhật quyền và số ngoại lệ quá hạn.

## 14. Checklist thiết kế và tài liệu đọc tiếp

### Checklist

- [ ] Có nguồn xác thực đáng tin cho **subject ID**, trạng thái danh tính và thời điểm hiệu lực JML.
- [ ] Xác minh đúng loại token/chứng thực, issuer, audience, chữ ký hoặc cơ chế introspection và thời hạn.
- [ ] Không coi SSO/MFA, mạng nội bộ hoặc JWT còn hạn là quyết định cấp quyền đầy đủ.
- [ ] Mỗi thao tác nhạy cảm được kiểm tra theo **subject + action + resource + context**.
- [ ] Thuộc tính tenant/owner/classification được lấy từ nguồn backend tin cậy, tránh client tự khai báo.
- [ ] RBAC kết hợp kiểm tra thuộc tính và quan hệ nơi cần, có deny mặc định.
- [ ] Có cơ chế đánh giá lại khi Mover/Leaver, trạng thái thiết bị, phiên hoặc quyền thay đổi.
- [ ] Hiểu và giám sát độ trễ SCIM, cache, access token và đường thu hồi khẩn cấp.
- [ ] Workload/service account có danh tính riêng, scope hẹp, owner, credential và vòng đời rõ ràng.
- [ ] Hệ thống kiểm toán được quyết định và kiểm thử được tình huống quyền tồn dư, cross-tenant và mất tín hiệu.
- [ ] Thiết kế step-up theo rủi ro và bảo vệ dữ liệu/credential trong log.

### Thuật ngữ quan trọng

| Thuật ngữ | Ý nghĩa sử dụng trong bài |
|---|---|
| **Verify explicitly** | Đánh giá bằng chứng và chính sách phù hợp trước khi cho phép truy cập |
| **Identity proofing** | Xác minh chủ thể được khai báo ở bước thiết lập danh tính |
| **AuthN / AuthZ** | Xác thực chủ thể / phân quyền đối với hành động và tài nguyên |
| **IdP / SSO** | Hệ thống xác thực danh tính / khả năng đăng nhập liên kết |
| **SCIM** | Chuẩn đồng bộ tài khoản, thuộc tính và nhóm giữa hệ thống |
| **RBAC / ABAC** | Quyền theo vai trò / quyền theo thuộc tính của request |
| **PEP / PDP / PA** | Điểm thực thi / đánh giá / quản trị đường truy cập theo kiến trúc chính sách |
| **Step-up authentication** | Yêu cầu bằng chứng xác thực mạnh hoặc mới hơn trước hành động |
| **JML** | Joiner–Mover–Leaver: gia nhập, chuyển vai trò, rời đi |
| **Residual access** | Quyền, phiên hoặc credential còn sử dụng được sau khi không còn ủy quyền |
| **Workload identity** | Danh tính của dịch vụ, tiến trình hoặc môi trường thực thi tự động |

### Tài liệu tham khảo khái niệm

- **NIST SP 800-207 — Zero Trust Architecture:** nguyên tắc loại bỏ tin cậy ngầm, điểm thực thi/điều khiển truy cập và quyết định theo chính sách.
- **NIST SP 800-63 — Digital Identity Guidelines:** khái niệm xác minh danh tính, xác thực và quản lý vòng đời các bằng chứng nhận dạng/xác thực.
- **RFC 7643 và RFC 7644 — SCIM:** mô hình tài nguyên và giao thức quản lý user/group.
- **OpenID Connect Core và OAuth 2.0:** phân biệt chứng thực đăng nhập, token và đối tượng nhận; đọc thêm hướng dẫn bảo mật token cho mô hình triển khai cụ thể.
- **OWASP API Security Top 10:** tham khảo các dạng sai sót authorization, đặc biệt kiểm tra ở cấp đối tượng và chức năng.

**Điểm cần ghi nhớ:** “Verify explicitly” không hỏi đơn giản “đã đăng nhập chưa?” mà hỏi **“ở thời điểm này, với danh tính và bằng chứng hiện có, hành động này trên tài nguyên này có được cho phép không?”**. Câu trả lời phải thay đổi đúng lúc khi chủ thể gia nhập, chuyển vai trò, rời đi hoặc khi rủi ro truy cập thay đổi.
