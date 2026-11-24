# Risk-based access là gì? Truy cập dựa trên rủi ro trong vòng đời danh tính IAM

Một nhân viên đăng nhập vào cổng nội bộ từ laptop được quản lý, sử dụng passkey và truy cập tài liệu ít nhạy cảm. Vài giờ sau, cũng tài khoản ấy yêu cầu xuất dữ liệu khách hàng từ một thiết bị mới, trong khi hệ thống vừa phát hiện dấu hiệu token bị tái sử dụng bất thường. **Có nên áp cùng một quyết định cho hai yêu cầu chỉ vì người dùng có cùng vai trò (role)?**

**Risk-based access (truy cập dựa trên rủi ro)** là cách đưa **đánh giá rủi ro theo ngữ cảnh và thời điểm** vào quyết định xác thực, thiết lập phiên hoặc cấp phép hành động trên tài nguyên. Thay vì chỉ hỏi *“tài khoản có role nào?”*, hệ thống còn xét *“ai đang yêu cầu, từ thiết bị và kênh nào, làm gì trên tài nguyên nào, tín hiệu hiện tại đáng tin tới đâu và hậu quả tiềm tàng nếu quyết định sai là gì?”*. Từ đó, hệ thống có thể **cho phép, yêu cầu xác minh bổ sung, giới hạn phạm vi, từ chối hoặc chuyển đánh giá thủ công** theo chính sách.

Bài thuộc chương **Risk-based access**, chủ đề trực tiếp **Risk-based access là gì**, trong mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Mô-đun nghiên cứu quản lý vòng đời danh tính **Joiner–Mover–Leaver (JML)**, từ xác minh, tạo tài khoản và cấp quyền đến rà soát, thu hồi khi thay đổi vai trò; liên kết **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và giảm quyền truy cập tồn dư.

Sau bài học, người học có thể:

- Giải thích **risk-based access** và phân biệt với **RBAC, ABAC, adaptive authentication, conditional access và Zero Trust**.
- Phân loại tín hiệu **identity, device, authentication, session, network, behavior, resource, transaction** và chất lượng của chúng.
- Mô tả kiến trúc **Policy Information Point (PIP) → Policy Decision Point (PDP) → Policy Enforcement Point (PEP)**, kèm điểm ghi log và vòng phản hồi.
- Thiết kế quyết định **ALLOW / STEP_UP / RESTRICT / DENY / REVIEW**, tránh coi “chưa biết” là “rủi ro thấp”.
- Liên kết policy rủi ro với **Joiner–Mover–Leaver, IdP/SSO/SCIM, PAM/JIT, tài khoản dịch vụ, thiết bị, session/token**.
- Phân tích các hạn chế của **risk scoring, dữ liệu đến muộn, sai lệch danh tính, quyền riêng tư, false positives và tình huống khẩn cấp**.
- Viết policy minh họa, phác thảo logic thực thi, xây dựng kịch bản kiểm thử, tình huống vận hành, chỉ số và checklist.

## 1. Risk-based access: định nghĩa và mục tiêu

Một quyết định truy cập truyền thống thường dựa vào điều kiện tĩnh: account ACTIVE, mật khẩu đúng, group thuộc `finance-users`. Những điều kiện ấy vẫn cần thiết nhưng không đủ trong nhiều tình huống.

Ví dụ, cùng một quyền `customer.export` có thể có rủi ro khác nhau:

| Ngữ cảnh | Yêu cầu | Phản ứng chính sách minh họa |
| --- | --- | --- |
| Nhân viên Finance ACTIVE, thiết bị quản lý đạt posture, xác thực mạnh, làm báo cáo theo phạm vi được giao. | Xem tổng hợp dữ liệu. | **ALLOW** nếu role và resource authorization đều đúng. |
| Cùng người, máy cá nhân chưa đủ bằng chứng quản lý. | Tải về toàn bộ dữ liệu khách hàng. | **RESTRICT** hoặc **DENY** export; đưa đường truy cập được bảo vệ. |
| Cùng người, thiết bị được EDR đánh dấu nguy cơ cao. | Đổi cấu hình thanh toán. | **DENY/CONTAIN** theo policy và xem xét sự cố. |
| Cùng người, máy hợp lệ nhưng không có role Finance. | Thực hiện `customer.export`. | **DENY** vì thiếu **authorization**, dù điểm rủi ro đăng nhập thấp. |
| Tài khoản đã Leaver. | Truy cập bất cứ tài nguyên nội bộ nào. | **DENY/REVOKE** theo lifecycle policy; không dùng risk score thấp để mở ngoại lệ. |

Các phản ứng chỉ là **ví dụ về cách thiết kế chính sách**, không phải quy tắc phổ quát.

### 1.1. Mục tiêu chính

1. **Giảm truy cập trái phép** trong bối cảnh có dấu hiệu bất thường hoặc bằng chứng danh tính yếu.
2. **Áp kiểm soát tương xứng với rủi ro**: thêm bước cho tác vụ nhạy cảm, giảm ma sát cho tình huống rõ ràng hợp lệ.
3. **Đưa thay đổi theo thời gian** vào quyết định: user Mover/Leaver, device bị mất, token bị nghi lộ, role bị thu hồi.
4. **Giảm blast radius**: một phiên đăng nhập hợp lệ không mặc nhiên được phép thực hiện mọi hành động.
5. **Tăng khả năng điều tra**: ghi lý do, tín hiệu, phiên bản policy, điểm thực thi và kết quả.
6. **Cải thiện vận hành** bằng vòng phản hồi từ incident, false positive và thay đổi môi trường.

### 1.2. Risk-based không đồng nghĩa cho hệ thống “đoán” quyền

Một engine không nên vì nhận định “rủi ro thấp” mà **tạo ra entitlement không có**, bỏ qua SoD, hoặc cấp admin ngoài quy trình. Risk-based access thường là **lớp điều kiện bổ sung** trên nền identity lifecycle và authorization hợp lệ.

**Bất biến:** *Người dùng không có quyền nghiệp vụ không thể biến thành người có quyền chỉ vì rủi ro được đánh giá thấp.*

## 2. Risk-based access khác gì RBAC, ABAC và adaptive authentication?

| Khái niệm | Trọng tâm | Ví dụ | Quan hệ với risk-based access |
| --- | --- | --- | --- |
| **RBAC (Role-Based Access Control)** | Role → permissions. | Role Reader được đọc hóa đơn. | Định nghĩa quyền nền tảng; risk bổ sung điều kiện. |
| **ABAC (Attribute-Based Access Control)** | Thuộc tính subject, resource, action, environment. | Chỉ xem hồ sơ thuộc tenant được giao, máy compliant. | Là cách biểu diễn nhiều policy rủi ro; không phải mọi ABAC đều dùng risk score. |
| **Risk-based access** | Đánh giá nguy cơ theo ngữ cảnh và hậu quả hành động. | Export số lượng lớn cần device trust và step-up. | Có thể triển khai bằng ABAC, policy engine hoặc cơ chế sản phẩm riêng. |
| **Adaptive authentication** | Thay đổi yêu cầu xác thực theo tín hiệu risk. | Yêu cầu MFA bổ sung khi đăng nhập bất thường. | Là **một phần** của risk-based access, chưa bao trùm API authorization. |
| **Conditional access** | Cho/không cho truy cập theo điều kiện. | Chỉ cho admin console từ thiết bị đạt compliance. | Có thể dùng risk signals; tên và khả năng tùy hệ thống. |
| **Zero Trust** | Không mặc nhiên tin cậy; xác minh rõ và giới hạn truy cập. | Re-evaluate identity, device và resource. | Triết lý/kiến trúc rộng hơn, risk-based decisions là một cơ chế hỗ trợ. |
| **PAM/JIT** | Quản lý, kích hoạt và giới hạn đặc quyền. | Admin production có phê duyệt và TTL. | Risk signals có thể ảnh hưởng eligibility/step-up và kích hoạt. |
| **SoD (Segregation of Duties)** | Ngăn xung đột quyền/hành vi. | Người tạo khoản chi không tự duyệt khoản đó. | Risk thấp **không được vượt SoD** trừ exception hợp lệ. |

### 2.1. Quyền nền và quyền tại thời điểm truy cập

~~~text
Quyền nền (entitlement/role):
    subject có được phép yêu cầu action trên resource không?

Điều kiện động (risk/context):
    tại thời điểm này, với device/session/auth context này,
    có cho thực thi action đó không?

Quyết định cuối:
    phải đạt cả quyền nền + các điều kiện bắt buộc.
~~~

Có thể nhìn nhận risk-based access theo hướng **Risk-Adaptive Access Control (RAdAC)** trong một số tài liệu kiến trúc, nhưng **không đồng nhất tên gọi với một giao thức chuẩn duy nhất**. Mô hình triển khai cụ thể phụ thuộc yêu cầu doanh nghiệp, policy engine và nền tảng.

## 3. Rủi ro ở đâu? Danh tính, phiên, tài nguyên và hành động

Cần phân biệt **khả năng bị lạm dụng** với **mức hậu quả nếu lạm dụng xảy ra**.

- **Identity risk:** credential đã bị nghi lộ, account có dấu hiệu bị chiếm, factor bị reset bất thường.
- **Sign-in/session risk:** yêu cầu xác thực từ môi trường mới, session/token có dấu hiệu bị dùng lại bất thường.
- **Device risk:** thiết bị bị báo mất, không đạt compliance, EDR nguy cơ cao, chứng chỉ hết hiệu lực.
- **Network/context risk:** kênh truy cập, nguồn địa chỉ, proxy, tính nhất quán theo ngữ cảnh; IP không phải danh tính chắc chắn.
- **Behavior/transaction risk:** hành động bất thường so với mục đích và phạm vi, chẳng hạn nhiều lần export dữ liệu.
- **Resource impact:** truy cập dashboard ít nhạy cảm và sửa IAM policy có hậu quả khác nhau dù cùng tín hiệu đăng nhập.

### 3.1. Risk score và resource sensitivity là hai trục khác nhau

Một thiết kế có thể kết hợp điểm rủi ro phiên với độ nhạy tài nguyên, nhưng không nên hiểu:

~~~text
riskScore = resourceSensitivity
~~~

**Resource sensitivity** có thể ảnh hưởng **ngưỡng kiểm soát**: cùng một phiên rủi ro trung bình có thể được phép đọc help page nhưng bị yêu cầu step-up khi mở giao dịch giá trị cao. Risk score bản thân là **mô hình ước lượng**, không phải bằng chứng toán học rằng một yêu cầu chắc chắn an toàn/nguy hiểm.

### 3.2. Sai lầm khi chỉ dùng geolocation

“Đăng nhập từ quốc gia lạ” có thể là tín hiệu đáng xem, nhưng VPN công ty, proxy, mobile roaming và cơ sở dữ liệu Geo-IP không chính xác. Không tự suy luận **nơi ở, vị trí vật lý hoặc danh tính con người** từ IP. Dùng tín hiệu này cùng device, session, auth factor, time và user context.

## 4. Thành phần kiến trúc Risk-based access

~~~mermaid
flowchart LR
    H["HRIS / JML / IGA<br/>Person, Engagement, entitlements"] --> PIP["PIP<br/>Trusted attributes + freshness"]
    D["UEM / MDM / EDR<br/>Device trust"] --> PIP
    I["IdP / MFA / SSO<br/>Auth + session signals"] --> PIP
    T["SOC / SIEM / Threat events<br/>Risk signals"] --> PIP
    R["Resource catalog<br/>Data classification + actions"] --> PIP
    PIP --> PDP["PDP<br/>Authorization + risk policy"]
    PDP --> PEP["PEP<br/>IdP / ZTNA / API / Application"]
    PEP --> APP["Protected resource / transaction"]
    PEP --> AUD["Decision / effect / session logs"]
    AUD --> SOC["Security monitoring + investigations"]
    SOC --> PIP
~~~

### 4.1. Vai trò PIP, PDP, PEP

| Thành phần | Chức năng | Câu hỏi vận hành |
| --- | --- | --- |
| **PIP (Policy Information Point)** | Cung cấp dữ liệu đã xác minh từ các nguồn danh tính, thiết bị, rủi ro và tài nguyên. | Thuộc tính do ai quản lý, mới tới đâu, namespace gì? |
| **PDP (Policy Decision Point)** | Đánh giá quyền nền, risk, resource/action, policy version và quyết định. | Nếu nguồn thiếu, rule nào ưu tiên và tại sao? |
| **PEP (Policy Enforcement Point)** | Chặn/cho request hoặc áp điều kiện tại điểm có thể kiểm soát hành động. | Có đường API hay app-local bỏ qua PEP không? |
| **Policy Administration** | Quản trị quy tắc, owner, duyệt và phiên bản policy. | Ai có quyền thay đổi deny/step-up? |
| **Audit/Monitoring** | Ghi tín hiệu, quyết định, sự kiện sử dụng, phát hiện drift. | Có chứng minh resource đã thực thi DENY? |

### 4.2. Điểm thực thi có thể khác nhau

1. **Tại IdP:** chặn sign-in hoặc yêu cầu MFA/step-up trước khi phát token.
2. **Tại ZTNA/proxy/gateway:** hạn chế đường kết nối dựa user, device và policy.
3. **Tại API/application:** kiểm role, object scope và context cho hành động thực tế.
4. **Tại PAM/JIT:** ràng buộc risk với privilege activation và session.
5. **Trong giao dịch:** revalidate tại bước nhạy cảm/commit nếu policy yêu cầu.

**Chỉ kiểm risk lúc login không bảo vệ đầy đủ dữ liệu nhạy cảm** nếu session tiếp tục hoạt động và hành động quan trọng không được API/PEP kiểm lại.

## 5. Những nhóm tín hiệu đánh giá rủi ro

| Nhóm | Tín hiệu minh họa | Nguồn khả dĩ | Lưu ý |
| --- | --- | --- | --- |
| **Account/identity** | Account ACTIVE, risk flag, credential compromise, lock state. | IdP/IAM/security operations. | Gắn issuer, tenant và subject. |
| **Lifecycle** | Start date, Mover effectiveAt, End date, sponsor/owner. | HRIS/contract source, IGA. | Data có thể đến muộn; cần source version. |
| **Authentication** | MFA/passkey, factor reset, recent auth, failed attempts. | IdP, MFA provider. | Challenge sent ≠ factor verified. |
| **Session/token** | Session age, refresh replay, token revocation, unusual reuse. | IdP, app, gateway. | Access token vẫn có thể được chấp nhận sau logout. |
| **Device** | Enrollment, compliance, EDR risk, certificate, attestation. | UEM/MDM, EDR, PKI. | Managed ≠ uncompromised. |
| **Network** | ASN, IP class, VPN/proxy, source reputation. | Trusted edge, network security. | Không tin header do client tự khai. |
| **Behavior** | Tần suất export, tài nguyên mới, hoạt động trái baseline. | API/app audit. | Cần xem vai trò, ca trực, thay đổi nghiệp vụ. |
| **Resource** | Classification, tenant, operation sensitivity. | Resource owner/catalog. | Tác động cao có thể đòi assurance cao. |
| **Privilege** | Admin role, JIT window, prior approvals, SoD conflict. | IGA/PAM/app. | Không tự cấp thêm quyền khi risk thấp. |
| **Threat intel** | Credential breach, suspicious infrastructure, confirmed incident. | Security/SOC/verified feeds. | Độ tin cậy và thời gian sống của tín hiệu. |
| **Workload** | Issuer, attestation, deployment provenance, principal owner. | Cloud IAM, workload platform. | Không đánh giá máy như user MFA. |

### 5.1. Phải phân biệt dấu hiệu và kết luận

- **Observed fact:** một request đến từ IP cụ thể qua gateway có nguồn đáng tin.
- **Derived signal:** nguồn đó được xếp vào một loại mạng theo classifier.
- **Risk inference:** classifier dự báo tình huống này có thể bất thường.
- **Policy decision:** áp STEP_UP hoặc DENY trên request với quyền/resource cụ thể.
- **Enforcement evidence:** ứng dụng thực sự đã yêu cầu step-up hoặc từ chối action.

Không gộp tất cả thành `trusted=true`. Sự minh bạch theo tầng giúp truy nguyên lỗi và cải thiện mô hình.

## 6. Độ tin cậy và độ tươi của tín hiệu (freshness)

Một MDM báo COMPLIANT từ ngày hôm qua không tương đương đo mới ngay trước thao tác. Một HRIS Leaver có hiệu lực lúc 09:00 nhưng tới IAM lúc 09:15 không được coi là một User ACTIVE không có vấn đề chỉ vì bản cache mới nhất chưa cập nhật.

### 6.1. Metadata nên có

~~~text
sourceSystem    = nơi phát tín hiệu
issuer/tenant   = namespace của tín hiệu
subjectRef      = Person/Account/Device/Workload cụ thể
observedAt      = lúc nguồn thực sự quan sát
receivedAt      = lúc PIP/collector nhận
effectiveAt     = mốc hiệu lực nếu dữ liệu nghiệp vụ có
expiresAt/TTL   = khi nào tín hiệu không còn hợp lệ theo policy
sourceVersion   = version/cursor sự kiện
confidence      = mức tin cậy được định nghĩa rõ
provenanceRef   = tham chiếu chứng cứ và cách kiểm integrity
~~~

### 6.2. Bốn trạng thái không nên đánh đồng

| Trạng thái | Ý nghĩa | Quyết định minh họa |
| --- | --- | --- |
| **KNOWN_GOOD** | Có bằng chứng tươi, đạt điều kiện được yêu cầu. | Có thể tiếp tục kiểm authorization. |
| **KNOWN_BAD** | Có bằng chứng tiêu cực đủ tin cậy. | DENY/CONTAIN khi policy quy định. |
| **UNKNOWN** | Không đủ dữ liệu để biết. | RESTRICT, STEP_UP, DENY hoặc quy trình continuity tùy risk. |
| **STALE** | Có dữ liệu cũ nhưng đã quá thời hạn. | Yêu cầu cập nhật/giới hạn thay vì coi là GOOD. |

**UNKNOWN và STALE không tự động là LOW_RISK.** Nếu risk model bỏ trống dữ liệu bằng 0 điểm, kẻ tấn công hoặc sự cố telemetry có thể vô tình mở đường truy cập thuận lợi.

### 6.3. Xung đột giữa các nguồn

Ví dụ: MDM báo compliant còn asset registry xác định laptop bị mất. Không nên lấy trung bình “hai nguồn, một tốt một xấu → rủi ro trung bình”. Cần **quy tắc nguồn có thẩm quyền theo thuộc tính và precedence theo rủi ro**: trạng thái LOST có thể chặn truy cập, dù compliance snapshot chưa đổi.

## 7. Các loại quyết định và nghĩa vụ đi kèm

| Decision | Ý nghĩa | Ví dụ obligation/response |
| --- | --- | --- |
| **ALLOW** | Cho action sau khi đủ entitlement và điều kiện. | Ghi decision, giới hạn session/scope theo policy. |
| **STEP_UP** | Chưa cho action; cần xác thực/bảo đảm bổ sung. | Recent MFA, phishing-resistant factor hoặc xác minh bằng phương thức phù hợp. |
| **RESTRICT** | Cho phạm vi an toàn hơn, không cấp toàn bộ action. | Read-only, cấm export, chỉ VDI, giảm session duration. |
| **DENY** | Không thực hiện action. | Thông báo chung, ghi reason code và alert khi cần. |
| **REVIEW** | Chuyển đánh giá có thẩm quyền, chưa cấp quyền nhạy cảm. | Giao owner, SLA, evidence, approval có SoD. |
| **QUARANTINE** | Cô lập device/session theo incident/endpoint policy. | Hạn chế kết nối, điều tra, phục hồi có kiểm chứng. |

### 7.1. STEP_UP chưa phải ALLOW

Khi PDP trả STEP_UP, API **chưa được thực hiện hành động nhạy cảm**. Sau khi factor được xác minh, phải đánh giá lại request và quyền hiện hành; một MFA thành công không được tự tạo role còn thiếu.

### 7.2. RESTRICT phải được thực thi ở resource

“Read-only” không chỉ là ẩn nút Export ở giao diện. API cần ngăn download/export/create/update/delete trong phạm vi policy. Nếu ứng dụng không thể thực thi hạn chế, PDP/PEP phải chọn lựa chọn khác hợp lệ, ví dụ DENY hoặc route qua môi trường đã được kiểm soát.

### 7.3. REVIEW không phải auto-approval

Nếu reviewer không trả lời đúng hạn, giữ trạng thái PENDING/OVERDUE hoặc escalate theo policy; không tự biến thành ALLOW. Người duyệt phải đủ thẩm quyền **tại lúc ra quyết định** và kiểm xung đột lợi ích/SoD.

## 8. Điều kiện bắt buộc khác với điểm rủi ro tùy chỉnh

Không phải mọi yếu tố đều nên quy thành điểm và cộng/trừ.

### 8.1. Các điều kiện hard deny có thể có

- Subject đã **Leaver/TERMINATED** và không có tư cách truy cập.
- Account, session hoặc token đã bị **REVOKED**.
- Không có **RBAC/ABAC entitlement** cho action/resource.
- Chứng chỉ/device credential không hợp lệ khi policy bắt buộc.
- Tenant/issuer/audience không khớp.
- Vi phạm SoD không có ngoại lệ đã được phê duyệt hợp lệ.
- Tài nguyên đang bị policy bảo vệ do incident nghiêm trọng.

Ngay cả khi những tín hiệu khác cho kết quả “rủi ro thấp”, **hard deny vẫn phải có hiệu lực**.

### 8.2. Những yếu tố có thể yêu cầu giảm rủi ro

- Đăng nhập từ thiết bị mới nhưng có khả năng xác minh/đăng ký hợp lệ.
- Context lệch baseline nhưng chưa có bằng chứng chiếm đoạt.
- Auth strength không đủ cho hành động nhạy cảm.
- IP/Geo-IP bất thường nhưng nguồn tin không đủ chắc.
- Device posture thiếu một tín hiệu có thể cập nhật.
- Transaction rủi ro vừa phải cần duyệt độc lập.

### 8.3. Độ nhạy tài nguyên quyết định ngưỡng

Một request có risk score tương đương có thể được:
- ALLOW khi xem tài liệu nội bộ ít nhạy cảm.
- STEP_UP khi xuất một báo cáo đã giới hạn.
- DENY hoặc REVIEW khi thay IAM policy production.

**Đừng sử dụng điểm risk đơn độc để xóa bỏ khác biệt giữa các loại hành động.**

## 9. Luồng đánh giá từ đăng nhập tới hành động

~~~mermaid
flowchart TD
    A["Request đến IdP / API / App"] --> B["Validate principal + credential / session"]
    B --> C{"Current JML + entitlement hợp lệ?"}
    C -->|"Không"| D["DENY + audit"]
    C -->|"Có"| E["Collect verified risk signals<br/>device / login / behavior / resource"]
    E --> F{"Signal quality, freshness & hard rules"}
    F -->|"Hard deny"| D
    F -->|"Unknown / stale"| G["Apply uncertainty policy<br/>restrict / step-up / deny"]
    F -->|"Known"| H["PDP evaluate risk + policy"]
    H --> I{"Decision"}
    I -->|"Allow"| J["PEP enforce requested action"]
    I -->|"Step-up"| K["Verify stronger authentication"]
    K --> C
    I -->|"Restrict"| L["PEP enforce limited action"]
    I -->|"Review"| M["Independent approval queue"]
    I -->|"Deny"| D
    J --> N["Audit actual outcome + feedback"]
    L --> N
    G --> N
    D --> N
    M --> N
~~~

### 9.1. Ba thời điểm khác nhau

1. **Trước đăng nhập:** IdP đánh giá điều kiện cấp authentication/session/token.
2. **Trong phiên:** posture, credential risk, JML và hành vi có thể thay đổi.
3. **Trước thao tác quan trọng:** API/transaction PEP đánh giá lại resource/action, auth assurance và quyền hiện tại.

Một số hệ thống hỗ trợ continuous access evaluation hoặc event-driven session revocation, nhưng **không mặc định mọi token và app session đều bị ngắt tức thì** khi tín hiệu thay đổi. Phải kiểm khả năng của issuer, RP/SP và resource server.

## 10. Adaptive authentication trong Risk-based access

Adaptive authentication điều chỉnh yêu cầu chứng minh danh tính theo ngữ cảnh.

### 10.1. Những thay đổi có thể áp dụng

| Tình huống | Phản ứng minh họa | Vì sao |
| --- | --- | --- |
| Thiết bị quen thuộc, auth assurance đủ cho read-only. | Giữ login flow thông thường. | Tránh friction không cần thiết. |
| Device mới, source bất thường, hành động quan trọng. | Yêu cầu factor mạnh hơn hoặc reauth gần thời điểm action. | Tăng assurance cho yêu cầu nhạy cảm. |
| Nhiều MFA push bị từ chối rồi một approval. | Đánh giá session rủi ro cao, có thể chặn và điều tra. | Một approval không tự chứng minh actor thật. |
| Credential bị xác nhận compromise. | Revoke/chặn và bắt đầu recovery an toàn. | Step-up đơn giản có thể không đủ. |
| Account đã Leaver. | DENY; không đề nghị MFA để vượt termination. | Hard eligibility rule. |

### 10.2. Phishing-resistant factor và device trust

Passkey/WebAuthn hoặc phương pháp xác thực mạnh có thể tăng mức bảo đảm về quá trình xác thực, nhưng **không tự chứng minh laptop đang compliant hoặc người dùng có quyền truy cập tài nguyên**. Cần tách **user authentication, device trust và authorization**.

### 10.3. Yêu cầu step-up tại thời điểm hành động

Một user có thể đăng nhập lúc 08:00 nhưng tới 16:00 mới yêu cầu thay tài khoản ngân hàng nhà cung cấp. Nếu policy yêu cầu recent authentication, ứng dụng nên dựa vào **auth time/assurance đáng tin**, không chỉ `iat` của access token được refresh gần đây hoặc sự tồn tại của SSO cookie.

## 11. Risk-based authorization tại API và giao dịch

Một phần lớn rủi ro phát sinh **sau khi login**, nên RBAC/ABAC cùng PEP tại API là bắt buộc cho hành động nhạy cảm.

### 11.1. Phân biệt identity/session và business transaction

~~~text
Login:
    user chứng minh danh tính và nhận session.

Authorization:
    user có quyền cơ sở làm action trên object cụ thể.

Risk-based decision:
    session / device / action / resource tại thời điểm này
    có đáp ứng policy không?

Transaction integrity:
    trạng thái nghiệp vụ, maker-checker, approvals,
    giá trị, recipient, hạn mức có hợp lệ không?
~~~

Ví dụ, hệ thống thanh toán phải kiểm **người tạo ≠ người duyệt** trên cùng giao dịch nếu policy SoD yêu cầu; device risk thấp hoặc recent MFA không thể thay điều kiện này.

### 11.2. Transaction-level policies

- Export dữ liệu: xét số lượng bản ghi, classification, tenant và device.
- Thay người nhận thanh toán: yêu cầu reauth/approval theo risk và business policy.
- IAM role assignment: kiểm role sensitivity, requester/beneficiary/approver và SoD.
- Cloud policy change: kiểm privileged eligibility, PAM/JIT, resource scope và session risk.
- Key rotation/deletion: đánh giá chủ thể máy, owner, request source và business impact.

### 11.3. Thực thi không chỉ ở UI

Nếu frontend ẩn nút Delete nhưng API vẫn cho phép gửi HTTP request trực tiếp, policy không được bảo vệ. **PEP ở server/resource** phải thực thi kết luận; UI chỉ hiển thị trạng thái và hướng dẫn.

## 12. Risk-based access và nguyên tắc least privilege

**Least privilege** là quyền tối thiểu cần thiết theo nhiệm vụ. Risk-based access điều chỉnh **điều kiện dùng quyền**, không nên dùng để **cấp vượt nhiệm vụ**.

| Tình huống | Least privilege | Risk-based bổ sung |
| --- | --- | --- |
| Nhân viên đọc báo cáo nội bộ. | Chỉ quyền read đúng dự án. | Có thể cho phép từ device phù hợp và session hiện hành. |
| Nhân viên export dữ liệu. | Chỉ dataset/tenant được giao. | Có thể yêu cầu device managed và recent MFA. |
| SRE vận hành production. | JIT role có scope resource và TTL. | Chặn activation từ thiết bị high-risk, kiểm session. |
| Service principal gọi một API. | Scope/chức năng tối thiểu. | Xác minh issuer/host/credential provenance khi policy yêu cầu. |
| Nhân viên Mover khỏi SRE. | Thu hồi role SRE. | Không giữ quyền dù thiết bị và login có risk score thấp. |

### 12.1. Không để policy rủi ro tạo “standing admin”

Nếu engine thấy người dùng luôn “low risk”, điều đó không có nghĩa hệ thống nên biến JIT admin thành quyền vĩnh viễn. **Standing entitlements, JIT activation và adaptive risk decisions là ba lớp khác nhau.**

**Chốt phần nền tảng:** Risk-based access chỉ có ý nghĩa khi **đặt trên danh tính và quyền hợp lệ, đánh giá tín hiệu đủ tin cậy, áp quyết định ở điểm thực thi và lưu được bằng chứng kết quả**.


## 13. Liên kết Risk-based access với Joiner–Mover–Leaver

Trong IAM, các sự kiện JML không chỉ thay đổi điểm rủi ro; nhiều thay đổi **làm mất hoặc tạo mới tư cách được cấp quyền**. Chính sách rủi ro phải phân biệt **eligibility/entitlement** với tín hiệu động.

### 13.1. Joiner: rủi ro của danh tính mới

Một nhân viên Joiner có thể có account IdP, laptop và group từ trước Start date:

1. HRIS xác nhận Person, Engagement, manager/sponsor, workerType, startDate.
2. IAM/IGA tạo account, birthright entitlements theo policy.
3. UEM/MDM xác minh thiết bị được cấp, posture và enrollment.
4. IdP cung cấp authentication flow thích hợp.
5. PEP kiểm **Start date/engagementState, entitlement, device/session/resource risk** trước truy cập.
6. Ứng dụng đối soát các quyền đã provision thực tế.

**Trường hợp đáng chú ý:** account được pre-provision trước khi người đó bắt đầu làm việc. Risk score đăng nhập thấp **không thể cho phép truy cập dữ liệu production trước Start date** nếu policy không cho phép. Nếu có quyền preboarding, phải định nghĩa **scope riêng**.

### 13.2. Mover: role cũ và token tồn dư

Ví dụ, 13:00 HRIS công bố một SRE chuyển sang Marketing. 13:05 người đó dùng session SSO đã tạo từ 09:00 để gọi API thay IAM policy.

~~~text
09:00  User login (legitimate at this time).
13:00  HRIS Mover effective: SRE -> Marketing.
13:01  IGA calculates revoke(old SRE), grant(new Marketing).
13:03  SaaS role/session propagation may lag.
13:05  Old API token includes SRE admin claim.

Expected:
    High-privilege action DENY because old entitlement is no longer valid.
    Risk score LOW for device/network does not override current JML.
~~~

Risk-based access cần **xử lý freshness và authorization hiện hành**, không chỉ chờ access token hết hạn. Nếu thực tế có propagation window thì phải đo, báo và giảm thiểu đúng risk tier.

### 13.3. Leaver: hard revoke không phải soft risk signal

Với Leaver:
- **Termination effectiveAt** là tín hiệu authoritative về tư cách trong phạm vi hợp đồng.
- IdP, app, API và PAM cần xử lý account/session/role/credential tương ứng.
- Đăng nhập thất bại sau Leaver có thể là bằng chứng policy chặn đúng; **đăng nhập hoặc resource action thành công** sau Leaver cần điều tra.
- Không áp STEP_UP như lối đi vượt termination. Người đã không còn tư cách không được lấy MFA hợp lệ làm cơ sở mở quyền.
- Revoke phải kiểm ở **resource/session/token**; SCIM hoặc IdP ACK riêng lẻ có thể chưa đủ.

### 13.4. Rehire và Engagement mới

Một người quay lại có thể vẫn là cùng Person, nhưng có **Engagement mới**. Không tự mở lại role, session, device exception, PAM eligibility và approvals từ lần làm việc trước. Policy phải kiểm **identity correlation theo namespace + engagement/version** để tránh email tái cấp và tài khoản cũ làm sai kết luận.

### 13.5. Guest/Contractor

Các subject từ đối tác có thể dùng **external IdP**, sponsor và endDate. Risk-based policy phải kiểm:
- External issuer/trust agreement.
- Contract/sponsor/guest expiry.
- Resource allowed scope và tenant isolation.
- Khả năng thu hồi khi đối tác đổi nhân sự.
- Khi source bên ngoài không cung cấp posture, lựa chọn restricted route/VDI nếu phù hợp.

**Risk thấp không bù cho sponsor hết hiệu lực hoặc guest account không có owner.**

## 14. SCIM, IGA và vai trò của provisioning trong quyết định rủi ro

**SCIM (System for Cross-domain Identity Management)** thường phục vụ provisioning User/Group giữa IdP/IGA và ứng dụng. Nó **không phải giao thức đánh giá thiết bị, phát hiện tấn công, kiểm token hay kiểm user session toàn cục**.

| Sự kiện | Dữ liệu SCIM/IGA có thể cung cấp | Điều risk-based PEP vẫn phải xử lý |
| --- | --- | --- |
| Joiner | Tạo user/nhóm/quyền dự kiến. | Session mới có hợp lệ và đúng Start date không? |
| Mover | Remove/add groups/role mappings. | Old claims, local roles và active sessions còn quyền không? |
| Leaver | User `active=false`, remove group. | SSO/local sessions, PAT và API tokens có bị chặn không? |
| Role review | Entitlement và approval evidence. | Effective privileges ở resource có khớp không? |
| Provisioning error | HTTP response/retry/connector state. | Không coi “request đã gửi” là “quyền đã đổi”. |

### 14.1. Desired state khác effective state

~~~text
HRIS/IGA desired entitlement:   no production-admin
SCIM group removal:              ACKNOWLEDGED
SaaS local direct role:          ACTIVE
Session token with old claims:   ACCEPTED

=> Không báo “no residual access”.
=> Risk/PEP phải đánh giá actual access và mở discrepancy.
~~~

### 14.2. Risk và trạng thái connector

Một connector error hoặc missing inventory cần được xem là **không đủ bằng chứng**, không tự tạo risk score 0. Với tài nguyên đặc quyền, có thể tạm **hold new grants** cho tới khi đối soát; với chức năng ít nhạy cảm có thể chọn cơ chế continuity nếu policy đã quy định.

## 15. IdP, SSO, OAuth và các tầng phiên

Trong hệ thống liên kết danh tính có thể tồn tại **ít nhất bốn lớp**:

~~~text
1. IdP/OP sign-in + risk evaluation.
2. SAML/OIDC federation response/identity assertion.
3. Relying Party / Service Provider application session.
4. API/resource access token + authorization.
~~~

### 15.1. OIDC authentication khác OAuth API access

OIDC có thể cung cấp bằng chứng người dùng được xác thực tại OP, trong khi OAuth access token được resource server dùng để đánh giá quyền API. Một token chỉ có chữ ký hợp lệ, `exp` chưa tới và audience đúng **chưa chứng minh** thiết bị hiện compliant, user chưa Leaver hay transaction không vi phạm SoD.

Cần:
- Kiểm token theo issuer, audience, signature, expiry, token type và policy.
- Xác định app/API có nhận được **risk/assurance signals đáng tin** hay phải lookup tại server.
- Nếu policy cần recent authentication, kiểm `auth_time` và yêu cầu phù hợp; **token `iat` mới do refresh không phải lần reauth mới**.
- Không đưa bearer token/refresh token vào log, score engine hoặc audit ticket.

### 15.2. SAML

SAML IdP có thể xác thực thành công nhưng SP từ chối assertion do audience hoặc signature mismatch. Risk evaluation tại IdP và authorization tại SP phải là hai bước có log/tương quan riêng. SP session được tạo có thể tiếp tục sống sau khi IdP account thay đổi nếu logout/revocation không được tích hợp.

### 15.3. Token freshness và claim version

Một nhóm quyền mới có thể phản ánh ở IdP nhưng access token cũ vẫn chứa role cũ. Risk-based access không được nhìn `risk=LOW` rồi tự tin rằng cached role là hiện hành. Có thể dùng token TTL ngắn, session/authorization version, introspection hoặc resource lookup theo rủi ro — tùy kiến trúc và giới hạn hiệu năng.

### 15.4. SSO không đồng nghĩa kiểm rủi ro một lần là đủ

Một người dùng xác thực từ laptop healthy lúc 09:00, nhưng lúc 10:00 laptop bị báo mất. IdP có thể chặn **đăng nhập mới**, còn ứng dụng có local session riêng. Cần biết PEP nào có thể **revoke, re-evaluate hoặc hạn chế session đang sống**.

## 16. Risk-based session management và device trust

### 16.1. Session có thể thay đổi risk theo thời gian

~~~text
09:00  Auth success; managed device; LOW session risk.
09:30  Access report.read -> ALLOW.
10:00  EDR detects high-risk behavior; device state updated.
10:02  User attempts customer.export.
10:02  PEP re-evaluates -> DENY or RESTRICT according to policy.
~~~

Khi trạng thái device đổi, **không sửa quá khứ** rằng login lúc 09:00 “đã thất bại”; phải ghi thêm risk event và quyết định cho request 10:02.

### 16.2. Absolute, idle và risk-driven termination

| Điều kiện | Tác dụng |
| --- | --- |
| **Idle timeout** | Hạn chế phiên bị bỏ quên, có thể trượt theo hoạt động có ý nghĩa. |
| **Absolute timeout** | Đặt hard cap cho tuổi session, không trượt bởi heartbeat. |
| **Risk event** | Có thể yêu cầu step-up/restrict/revoke trước mọi timeout. |
| **JML revoke** | Mất eligibility hoặc entitlement trước deadline. |
| **Privileged TTL** | Chỉ quyền nâng cao có expiry riêng, có thể ngắn hơn user session. |

**Không dùng phiên web hết hạn sau nhiều giờ như cơ chế duy nhất để xử lý tài khoản đã Leaver, máy đã mất hoặc credential bị xâm phạm.**

### 16.3. Device enrolled không tự trusted

Bản ghi `registered` hoặc `managed` không tự chứng minh:
- Posture hiện tại.
- EDR đang healthy.
- Key/attestation còn hợp lệ.
- Asset chưa bị mất/bàn giao.
- User đang có quyền resource.

Kết hợp device identity proof, lifecycle, telemetry freshness và application authorization đúng phạm vi.

### 16.4. Risk-driven session restrictions

Các biện pháp tùy khả năng PEP:
- Reauthentication trước tác vụ nhạy cảm.
- Session duration ngắn hơn cho risk tier cao.
- Hạn chế file download/copy/export.
- Chỉ cho phép VDI hoặc managed client.
- Revoke refresh family hoặc session khi có evidence compromise.

**Thực thi phải được kiểm tại API/ứng dụng**, không chỉ hiện một banner cảnh báo.

## 17. PAM/JIT, privileged access và emergency access

Đặc quyền có **blast radius** cao; vì vậy điều kiện risk-based thường chặt hơn.

### 17.1. Trước khi kích hoạt admin role

Ví dụ yêu cầu `production-admin`:
1. Verify người yêu cầu và Engagement hiện hành.
2. Check **PAM eligibility**, approval authority và SoD.
3. Kiểm recent authentication/MFA assurance.
4. Kiểm device trust, session anomaly và policy risk.
5. Ràng buộc resource/tenant, duration và hành động được phép.
6. Kích hoạt JIT, ghi actor/approver, session audit và expiry.
7. Thu hồi sau task/expiry và xác minh ở target.

Một điểm risk thấp **không tạo eligibility** nếu người dùng không được cấp quyền admin theo policy.

### 17.2. Risk tăng trong phiên privileged

Nếu token/credential bị nghi lộ hoặc EDR phát hiện compromised host, tổ chức có thể chấm dứt/khoanh vùng privilege trước TTL; nhưng phải có **evidence về enforcement** ở cloud/API/SSH/PAM, vì dashboard PAM báo ENDED không tự chứng minh token cũ không còn dùng được.

### 17.3. Emergency/break-glass

Khi IdP/PAM hoặc risk telemetry bị outage, cơ chế cứu hệ thống không nên phụ thuộc hoàn toàn vào chính thành phần đang lỗi. Chính sách emergency cần:
- Được chuẩn bị và phê duyệt **trước sự cố**.
- Chỉ rõ actor/principal, scope, điều kiện, duration tối đa.
- Có giám sát/cảnh báo, log và đường dự phòng nếu có.
- Đóng/rotate/revoke credential/session theo quy trình.
- Có **post-event independent review**, xử lý sai lệch và residual access.

**Emergency access không đồng nghĩa “risk check bị tắt trên toàn doanh nghiệp”**.

## 18. Workload/service accounts và risk-based access

Principal máy gồm service account, API client, managed identity, pod/workload principal, VM/node hoặc CI/CD runner. **Không dùng mô hình “user vừa bấm MFA” cho workload không tương tác.**

### 18.1. Tín hiệu dành cho workload

| Yếu tố | Ví dụ |
| --- | --- |
| **Principal identity** | Service principal/workload ID, issuer, trust domain. |
| **Owner/purpose** | OwnerTeam, application, environment, business purpose. |
| **Credential** | mTLS certificate, short-lived token, workload federation, key status. |
| **Execution provenance** | Cluster/namespace, node, deployment signature/attestation khi có. |
| **Resource/action** | API audience, permission scope, tenant, operation. |
| **Behavior** | Lượng request khác baseline, tài nguyên mới, deployment ngoài change. |
| **Lifecycle** | Deploy, rotate, disable, decommission, owner chuyển giao. |
| **Security events** | Suspicious token exchange, credential reuse, compromised runner. |

### 18.2. Ví dụ workload risk

~~~text
Service: invoice-reader
OwnerTeam: billing-platform
Expected: read invoices from tenant-a API
Observed: attempt to modify IAM policy in tenant-b

Authorization: DENY (not entitled to tenant-b IAM policy)
Risk: ALERT (unexpected action / audience / tenant)
Do not: grant admin because host attestation passed.
~~~

### 18.3. Leaver không được kéo theo account cá nhân làm service credential

Nếu scheduler dùng PAT của người đã nghỉ, risk monitoring cần phát hiện **credential use after owner termination**. Giải pháp bền vững là **chuyển sang workload identity có ownerTeam**, scope tối thiểu, rotate/revoke PAT cũ và xác minh ở API. Không giữ account Leaver ACTIVE để automation chạy được.

### 18.4. Host trust và workload identity không đồng nhất

mTLS xác nhận quyền sử dụng private key của client, không mặc nhiên chứng minh mọi phần mềm trên host an toàn. Node attestation có thể làm tăng assurance, nhưng **service principal và resource permission** phải được kiểm riêng. Một node healthy không cho mọi pod quyền admin.

## 19. Biểu diễn risk-based policy minh họa

Một chính sách có thể có **hard gates**, **signal quality**, **risk thresholds theo resource**, **obligations** và **audit reason codes**.

~~~yaml
# PSEUDOCONFIG: minh họa ý tưởng, không phải schema của vendor hay chuẩn IAM.
policyId: RBA-WORKFORCE-RESOURCE
policyVersion: 7
scope:
  principals: [HUMAN]
  resources: [internal-read, customer-export, production-admin]

hardRequirements:
  validAuthenticatedSubject: true
  activeEngagement: true
  effectiveEntitlement: true
  tenantAndIssuerMatch: true
  noUnapprovedSoDConflict: true
  noRevokedSessionOrCredential: true

signalRules:
  devicePosture:
    source: trusted-uem
    freshness: policy-defined
    onUnknownForSensitiveAction: RESTRICT_OR_DENY
  identityRisk:
    source: identity-security
    onConfirmedCompromise: DENY_AND_ALERT
  networkRisk:
    source: trusted-edge
    role: supporting-signal
  sessionRisk:
    source: trusted-idp-and-resource

actions:
  internal-read:
    lowRisk: ALLOW
    unknownContext: RESTRICT_AS_DEFINED
  customer-export:
    mediumRisk: STEP_UP
    highRisk: DENY
    requireManagedDevice: true
  production-admin:
    requirePAMEligibility: true
    requireIndependentApproval: true
    requireRecentStrongAuth: true
    highRisk: DENY_AND_ALERT

audit:
  include: [policyVersion, evidenceRefs, decision, reasonCodes, pepResult]
  redactSecrets: true
~~~

### 19.1. Những gì policy chưa nói

Tài liệu thật còn phải định nghĩa:
- Cách tính low/medium/high và phiên bản model.
- Resource classification do owner quản lý.
- Từng loại signal có độ tươi và độ tin cậy ra sao.
- Khi telemetry outage, thứ tự hard gates và continuity.
- Ý nghĩa `RESTRICT_AS_DEFINED`, nơi thực thi và cơ chế hồi phục.
- SoD, JML exception, approval authority và change control.

Không nên triển khai một YAML minh họa như sản phẩm production mà chưa có các hợp đồng này.

## 20. Pseudocode của risk decision engine

~~~text
authorize(request):
    now = trustedServerTime()
    principal = validateSubjectAndCredential(request)
    if principal.invalid:
        return DENY("AUTHENTICATION_INVALID")

    identity = loadCurrentAuthoritativeIdentity(principal)
    entitlements = resolveEffectivePermissions(identity, request.resource)
    if not identity.eligibleAt(now):
        return DENY("LIFECYCLE_INELIGIBLE")
    if not entitlements.allows(request.action, request.resource):
        return DENY("ENTITLEMENT_MISSING")
    if violatesMandatorySoD(identity, request):
        return DENY("SOD_CONFLICT")
    if sessionOrCredentialRevoked(principal):
        return DENY("CREDENTIAL_REVOKED")
    if tenantOrIssuerMismatch(principal, request.resource):
        return DENY("TRUST_BOUNDARY")

    evidence = collectTrustedSignals(
        identity, request.device, request.session,
        request.resource, request.action, now
    )

    if evidence.confirmedCompromiseOrDeviceLost:
        return DENY_AND_ALERT("CONFIRMED_HIGH_RISK")

    if evidence.requiredFieldsMissingOrStale:
        return applyUncertaintyPolicy(
            request.resource.riskTier,
            request.action,
            evidence.missingFields
        )

    risk = evaluateVersionedRiskModel(evidence)
    decision = applyResourceAndActionPolicy(
        risk, request.action, request.resource,
        principal.authStrength, entitlements
    )

    auditDecisionWithEvidenceRefsAndPolicyVersion(decision)
    return decision

onStepUpCompleted(request, trustedAuthResult):
    verifyAuthResultBoundToPrincipalAndRequest(trustedAuthResult)
    return authorizeFreshRequestWithCurrentSignals(request)
~~~

**Đây là giả mã thiết kế**, không phải mã chạy được. Trong hệ thống thật còn cần kiểm nguyên tử/concurrency, timeouts, caching, event precedence, issuer trust, data privacy, error handling và authorization ngay tại transaction boundary.

### 20.1. Kiểm tra lại sau step-up

Một OTP/passkey được xác minh lúc 10:01 không được dùng để tự chấp nhận kết quả PDP từ 09:59 nếu trong khoảng đó user đã Leaver, role bị thu hồi hoặc request chuyển sang tenant khác. **Tái đánh giá quyết định đối với đúng resource/action**.

### 20.2. Policy do client quyết định là thiết kế nguy hiểm

Không tin payload:
~~~json
{"riskScore":0,"isTrustedDevice":true,"isApproved":true}
~~~

nếu do client tự gửi. Chỉ chấp nhận **assertion được xác minh** hoặc server-side lookup từ trusted source với audience/tenant/time binding.

## 21. Risk scoring định lượng: ví dụ và giới hạn

Một số tổ chức dùng score để xếp hạng cảnh báo hoặc chọn control. Ví dụ **hoàn toàn minh họa** với các tín hiệu đã chuẩn hóa về khoảng 0–100, trong đó 100 nghĩa là rủi ro cao hơn:

\[
S = 0.30C + 0.30D + 0.25B + 0.15N
\]

Trong đó:
- \(C\) = credential/identity risk.
- \(D\) = device risk.
- \(B\) = behavior/session anomaly.
- \(N\) = network-context risk.

### 21.1. Ví dụ tính toán

| Tín hiệu | Giá trị giả định | Trọng số | Đóng góp |
| --- | ---: | ---: | ---: |
| Credential risk \(C\) | 20 | 0,30 | 6,0 |
| Device risk \(D\) | 80 | 0,30 | 24,0 |
| Behavior risk \(B\) | 70 | 0,25 | 17,5 |
| Network risk \(N\) | 40 | 0,15 | 6,0 |
| **Tổng** | | **1,00** | **53,5** |

Giả sử policy thí điểm đánh giá 53,5 là **trung bình**, nó có thể yêu cầu step-up cho báo cáo thường, nhưng **deny export** nếu policy high-risk resource yêu cầu device healthy.

### 21.2. Điểm số không được thắng hard gates

Nếu device được xác nhận STOLEN, token đã REVOKED hoặc người dùng Leaver, **không được để score trung bình 53,5 mở quyền**. Hard rules phải được áp trước hoặc có precedence rõ.

### 21.3. Thang điểm không phải xác suất

Score 53,5 **không có nghĩa xác suất bị tấn công là 53,5%** nếu chưa có calibration và bằng chứng định lượng. Weights/thresholds nêu ở đây chỉ minh họa. Mô hình thật cần dữ liệu đủ chất lượng, validation, monitoring và owner chấp thuận.

### 21.4. Missing signals không phải số 0

Nếu \(D\) thiếu vì EDR outage, gán \(D=0\) sẽ làm score giảm giả. Tốt hơn:
- Trả trạng thái thiếu/UNKNOWN riêng.
- Áp policy theo resource risk.
- Nếu có imputation, phải được kiểm chứng và **không làm mất hard safety rules**.
- Ghi confidence/coverage và nguyên nhân thiếu.

## 22. Chọn threshold, calibration và tác động tới người dùng

Threshold quá thấp có thể chặn nhiều người dùng hợp lệ; threshold quá cao có thể bỏ qua tấn công.

### 22.1. Cân bằng sai số

| Sai số | Ví dụ | Tác động |
| --- | --- | --- |
| **False positive** | Nhân viên đi công tác hợp lệ bị chặn vì Geo-IP lạ. | Gián đoạn công việc và tăng support load. |
| **False negative** | Credential bị chiếm nhưng thiết bị/browser giống baseline nên được phép. | Unauthorized access và mất dữ liệu. |
| **False assurance** | Dấu vết nguồn thiếu làm score=LOW. | Policy tưởng an toàn khi không có evidence. |
| **Control bypass** | Step-up ở UI, API cho phép trực tiếp. | Mất hiệu lực của toàn bộ đánh giá rủi ro. |

### 22.2. Cách đánh giá threshold

1. Xác định **resource/action risk tier** và hậu quả.
2. Xây dataset gồm sự kiện hợp lệ, tấn công đã xác minh và case mơ hồ, ghi thời gian/ngữ cảnh.
3. Chia tập để tránh leakage qua user/session/time hoặc dùng dữ liệu tương lai cho dự đoán quá khứ.
4. Phân tích false positives/false negatives theo nhóm trường hợp nghiệp vụ.
5. Đo ảnh hưởng accessibility, BYOD/đối tác, kết nối không ổn định và ca trực.
6. Chạy policy ở **observe-only/shadow** khi phù hợp trước khi enforce.
7. Bật dần theo risk tier và monitor drift, cùng cơ chế rollback được kiểm soát.
8. Lưu policy/model version để audit và tái dựng quyết định.

### 22.3. Không suy đặc điểm nhạy cảm từ proxy tùy tiện

Mô hình hành vi hoặc vị trí có thể gây khác biệt tác động giữa những nhóm người dùng do loại thiết bị, mạng, địa điểm, khả năng tiếp cận. Nên kiểm **tính hợp lý, fairness, privacy và business necessity** của signals; tránh sử dụng thuộc tính nhạy cảm hoặc proxy không cần thiết. Risk-based access phải có kênh hỗ trợ người dùng hợp lệ mà không yêu cầu tắt kiểm soát theo cảm tính.

### 22.4. Giải thích quyết định

Một quyết định hữu ích nên có **reason codes** như `DEVICE_POSTURE_STALE`, `RECENT_AUTH_REQUIRED`, `ENTITLEMENT_MISSING`, `RISKY_SESSION`. Giao diện người dùng không cần tiết lộ logic phòng thủ chi tiết hay dữ liệu threat intelligence có thể giúp attacker, nhưng đội IAM/SOC cần evidence đủ để hỗ trợ và điều tra.

## 23. Risk thay đổi liên tục: caching, eventual consistency và race

### 23.1. Ví dụ cửa sổ rủi ro

~~~text
10:00  User logs in: LOW risk.
10:01  PDP caches ALLOW for customer.export for 30 minutes.
10:05  Device EDR reports HIGH_RISK.
10:07  API receives export request.
10:07  API reuses cached ALLOW (unsafe if policy requires fresh device check).
~~~

Khi thiết kế cache cần ràng buộc **TTL vào tuổi của bằng chứng và độ nhạy hành động**, cùng cơ chế invalidation cho sự kiện quan trọng. Không coi cache efficiency là lý do mặc định cho phép xuất dữ liệu sau device compromise.

### 23.2. Race/TOCTOU

**Time-of-check to time-of-use** xảy ra khi policy được kiểm ở bước đầu nhưng resource/action thay đổi trước khi thực thi hoặc commit.

| Tình huống | Điều cần thiết kế |
| --- | --- |
| Risk score LOW trước khi bắt đầu giao dịch, HIGH trước commit. | Kiểm lại tại transaction boundary khi policy yêu cầu. |
| Mover revoke và new grant chạy song song. | Xác minh actual entitlements; tránh quyền xung đột tạm. |
| Leaver và token refresh chạy đồng thời. | Recheck current authoritative state, không hồi sinh phiên. |
| Hai request privilege activation song song. | Atomic/versioned approval và kiểm SoD. |
| Tín hiệu EDR COMPLIANT cũ đến sau LOST. | Không để sự kiện cũ ghi đè trạng thái chặn mới. |
| Policy version đổi trong khi request chờ reviewer. | Xác định version áp dụng và revalidate authority. |

### 23.3. Không coi risk ALLOW là bảo đảm vĩnh viễn

Một quyết định chỉ đúng **cho request, principal, action, resource, context và thời điểm trong phạm vi kiểm soát**. Nếu lưu decision cache, phải xác định thời gian sử dụng được, scope, invalidation và mức bảo đảm khi tín hiệu thay đổi.

## 24. Khi IdP, MDM, EDR hoặc risk engine bị lỗi

### 24.1. Các lỗi thường gặp

| Lỗi | Rủi ro | Phương án policy có thể lựa chọn |
| --- | --- | --- |
| **IdP unavailable** | Không thể xác thực/kiểm account theo đường thường. | Continuity/emergency đã định nghĩa; không mở blanket access. |
| **MDM/EDR offline** | Posture stale/unknown. | Restrict/deny high-risk resource hoặc đường bảo vệ thay thế. |
| **PIP timeout** | Không đủ risk signals để đánh giá. | Timeout budget, fallback theo resource tier, audit UNKNOWN. |
| **Risk engine degraded** | Score thiếu hoặc sai. | Hard gates tiếp tục áp; giới hạn chức năng, alert. |
| **SCIM connector lỗi** | Role/revoke không đồng bộ. | Reconciliation, hold grant nhạy cảm, target readback. |
| **API gateway cache stale** | PEP áp decision cũ. | Invalidation/TTL cap/incident mitigation. |
| **Threat feed false alarm** | Người dùng hợp lệ bị chặn. | Phân loại confidence và escalation độc lập. |
| **SIEM/event backlog** | Risk signal đến muộn. | Telemetry health, degraded mode, risk tier policy. |

### 24.2. Fail-closed/fail-open không thể là khẩu hiệu chung

- **Production IAM admin/PII export:** thiếu bằng chứng quan trọng thường dẫn tới **DENY/RESTRICT** theo policy.
- **Tài liệu ít nhạy cảm:** có thể có degraded mode giới hạn thời gian/chức năng nếu risk owner cho phép.
- **Hệ thống OT/khẩn cấp:** ưu tiên safety/availability có thể đòi đường continuity được định nghĩa và giám sát riêng.
- **Mọi trường hợp:** không giả `UNKNOWN = LOW_RISK`; không tự cấp đặc quyền vì scoring service lỗi.

### 24.3. Giảm phụ thuộc vòng tròn

Nếu điều kiện truy cập vào IdP recovery console **bắt buộc kiểm cùng IdP và EDR gateway đang hỏng**, đội vận hành có thể không khôi phục được hệ thống. Cần thiết kế đường break-glass hẹp, có owner, accountability, thời hạn, cảnh báo và **post-event review**, không biến thành cửa hậu thường trực.

**Chốt phần kiến trúc:** Risk-based access cần giữ ranh giới **hard authorization/JML**, **signals có provenance/freshness**, **risk policy theo resource/action** và **PEP thực thi**; mọi exception hay degraded mode phải có owner và bằng chứng.


## 25. Quyền riêng tư và quản trị dữ liệu trong risk-based access

Một hệ thống risk-based có thể tiếp cận địa chỉ mạng, tình trạng thiết bị, lịch sử đăng nhập, thời gian hoạt động và hành vi sử dụng ứng dụng. Những dữ liệu này có thể **nhạy cảm** dù không chứa password.

### 25.1. Nguyên tắc thiết kế

| Nguyên tắc | Áp dụng cụ thể |
| --- | --- |
| **Purpose limitation** | Chỉ lấy tín hiệu để bảo vệ truy cập và kiểm soát được công bố/cho phép. |
| **Data minimization** | Không cần lưu GPS chi tiết để dùng một Geo-IP vùng rộng. |
| **Provenance** | Biết thuộc tính do server quan sát hay client tự khai. |
| **Retention** | Thời hạn lưu theo mục đích/chính sách/nghĩa vụ áp dụng; không giữ vô hạn. |
| **Access control** | SOC xem investigation evidence theo nhiệm vụ; app owner không mặc nhiên xem mọi hoạt động cá nhân. |
| **Transparency** | Giải thích loại dữ liệu được dùng và phương án xử lý khi device không đủ điều kiện. |
| **Review/appeal** | Có lối xử lý false positive có kiểm soát, tránh tắt policy tùy tiện. |
| **Cross-tenant isolation** | Risk records và subject/device IDs phải gắn tenant/issuer chính xác. |

### 25.2. Hạn chế giám sát quá mức

Không nên biến risk-based access thành hệ thống theo dõi người lao động vô hạn. Hãy ưu tiên **tín hiệu kỹ thuật có mục tiêu**, ví dụ device compliance state, mức rủi ro phiên, factor verified, resource action. Nếu dùng location, behavior profiling hoặc device fingerprinting, phải đánh giá nhu cầu, tác động, thông báo và quyền truy cập theo quy định.

### 25.3. Không lộ secrets trong risk telemetry

Dữ liệu risk và audit không nên chứa:
- Raw password, OTP, passkey private key, recovery code.
- Access/refresh/ID token, OAuth authorization code.
- Session cookies, API key/PAT, private key/certificate secret.
- Full sensitive request body, dữ liệu khách hàng hoặc nội dung nghiệp vụ không cần thiết.

Thay vào đó dùng **sessionRef, credentialRef, traceId, token family reference, reason codes, timestamps và các thuộc tính đã giảm dữ liệu**. Hash/tokenize cũng cần quản lý khóa và đánh giá rủi ro tái nhận diện.

## 26. Bằng chứng kiểm toán cho mỗi quyết định

Một quyết định risk-based có thể bị chất vấn nhiều ngày sau. Cần đủ dữ liệu để trả lời **policy nào, tín hiệu nào, tài nguyên nào và PEP đã thực thi gì**.

### 26.1. Trường dữ liệu gợi ý

| Field | Ý nghĩa |
| --- | --- |
| **decisionId / requestId / traceId** | Tương quan request, PDP và PEP. |
| **principalType** | HUMAN, WORKLOAD, GUEST, PRIVILEGED hoặc phân loại phù hợp. |
| **issuerId + tenantId + subjectId** | Namespace của principal được xác thực. |
| **personId/engagementId hoặc workloadId** | Liên kết JML hoặc owner của machine principal khi đủ tin cậy. |
| **accountId/sessionRef/deviceRef** | Account, phiên và thiết bị liên quan, không chứa raw secrets. |
| **action/resource/tenantScope** | Quyền được yêu cầu và phạm vi tác động. |
| **entitlementEvidenceRef** | Role/ABAC/JIT/SoD được kiểm theo nguồn nào. |
| **riskSignalRefs + observedAt** | Nguồn, độ tươi và bản chứng tín hiệu. |
| **riskModelVersion/policyVersion** | Logic đã dẫn tới quyết định. |
| **riskTier/score/confidence** | Kết quả mô hình nếu được dùng; nêu thang và giới hạn. |
| **decision + obligations** | ALLOW, STEP_UP, RESTRICT, DENY, REVIEW; điều kiện thực thi. |
| **PEP outcome** | Resource thực sự allow/deny/restrict hay lỗi/unknown. |
| **exceptionId/approvalRef** | Ngoại lệ có thẩm quyền, scope, hạn và reviewer. |
| **decisionAt + effectiveAt** | Mốc đánh giá và hiệu lực trong ngữ cảnh. |

### 26.2. JSON sự kiện minh họa

~~~json
{
  "eventType": "RISK_BASED_ACCESS_DECISION",
  "schemaVersion": "rba-decision-v1",
  "decisionId": "rba-dec-20261201-0017",
  "traceId": "trace-api-1188",
  "decisionAt": "2026-12-01T10:14:03+07:00",
  "principalType": "HUMAN",
  "issuerId": "corp-idp",
  "tenantId": "tenant-a",
  "subjectId": "idp-sub-1042",
  "personId": "person-1042",
  "engagementId": "EMP-5812",
  "sessionRef": "sess-ref-781",
  "deviceRef": "device-ref-101",
  "resourceId": "customer-dataset",
  "action": "customer.export",
  "entitlement": "PERMITTED",
  "signals": [
    {
      "name": "device_posture",
      "state": "STALE",
      "source": "trusted-uem",
      "observedAt": "2026-12-01T08:00:00+07:00"
    },
    {
      "name": "session_risk",
      "state": "MEDIUM",
      "source": "identity-risk-provider",
      "observedAt": "2026-12-01T10:13:50+07:00"
    }
  ],
  "policyId": "RBA-WORKFORCE-RESOURCE",
  "policyVersion": 7,
  "riskModelVersion": "rba-model-v3",
  "decision": "RESTRICT",
  "obligations": ["NO_EXPORT", "REQUIRE_FRESH_DEVICE_EVIDENCE"],
  "reasonCodes": ["DEVICE_POSTURE_STALE", "SENSITIVE_ACTION"],
  "pepOutcome": "EXPORT_DENIED",
  "evidenceRefs": ["evidence-rba-901"]
}
~~~

**Mẫu dữ liệu giả định**, không phải schema bắt buộc của OAuth, SCIM, một nhà cung cấp IdP hay SIEM. Các IDs không phải thông tin thật. Không dùng `pepOutcome=EXPORT_DENIED` chỉ vì PDP trả RESTRICT; cần bằng chứng PEP đã chặn endpoint tương ứng.

### 26.3. Bảo vệ integrity và lịch sử

- Ghi policy/version tại thời điểm đánh giá.
- Giữ provenance và evidence reference; nếu nguồn thay đổi sau đó, không viết lại lịch sử để trông như đã biết trước.
- Có logging riêng cho policy admin, risk exception, reviewer approval và override.
- Phân quyền xem/đổi log, tách nhiệm vụ và retention có kiểm soát.
- Nếu điều tra pháp lý/incident, bảo toàn evidence theo quy trình và chain of custody khi cần.

## 27. Pipeline rủi ro và khả năng quan sát

### 27.1. Một luồng dữ liệu điển hình

~~~mermaid
flowchart TD
    EV["HRIS / IAM / IdP / Device / App events"] --> COL["Authenticated ingestion"]
    COL --> VALID["Validate schema, provenance, timestamp"]
    VALID --> STORE["Protected signals + evidence references"]
    STORE --> ENR["Identity correlation + JML + resource context"]
    ENR --> RISK["Versioned risk evaluation"]
    RISK --> PDP["Risk and authorization policy"]
    PDP --> PEP["Action enforcement"]
    PEP --> AUD["Decision + outcome audit"]
    AUD --> MON["Monitoring + alerts + incident response"]
    MON --> FB["Feedback / calibration / policy reviews"]
    FB --> RISK
~~~

### 27.2. Health của pipeline cũng là tín hiệu

| Trục quan sát | Cần đo |
| --- | --- |
| **Source coverage** | Bao nhiêu nguồn IdP/MDM/EDR/app/JML trong scope thực sự được giám sát? |
| **Signal freshness** | `receivedAt - observedAt` và TTL được đáp ứng thế nào? |
| **Ingestion lag** | Độ trễ/percentile cho sự kiện quan trọng. |
| **Source heartbeat** | Nguồn mất tín hiệu hay thực sự không có hoạt động? |
| **Schema error** | Bao nhiêu record parse lỗi, missing fields, sai namespace? |
| **Dedup/replay** | Một event có bị xử lý nhiều lần hoặc mất do checkpoint không? |
| **Decision latency** | PDP đáp ứng ngân sách thời gian cho API không? |
| **PEP enforcement** | Bao nhiêu quyết định đã được áp thật ở target? |
| **Incident/review feedback** | False positive/negative, accepted exceptions, drift. |

### 27.3. Không suy “0 alerts = an toàn”

Nếu EDR collector ngừng gửi sự kiện trong hai giờ, dashboard rủi ro có thể giảm cảnh báo. Đó là **mất khả năng quan sát**, không phải bằng chứng môi trường an toàn hơn. Cần alert riêng cho **data freshness, source outage và gap**.

### 27.4. Không để events đến muộn ghi đè trạng thái chặn

~~~text
10:00  Device D marked COMPLIANT by MDM.
10:05  Asset registry marks D LOST.
10:07  Delayed MDM COMPLIANT event from 10:00 arrives again.

Correct:
    LOST risk gate remains in force.
    Historical COMPLIANT is not a new authorization.
~~~

Dùng **source authority, eventTime, effectiveAt, sourceVersion và precedence policy** để xử lý, không chỉ kiểu “last message wins”.

## 28. Threat model cho Risk-based access

| Nguy cơ | Cách xảy ra | Phòng vệ cần xem |
| --- | --- | --- |
| **Signal spoofing** | Client tự gửi `risk=low` hoặc `deviceTrusted=true`. | Server-side verified source, signed assertion, tenant binding. |
| **Risk model gaming** | Attacker bắt chước thói quen user để đạt baseline. | Multi-signal, transaction checks, hard gates và threat monitoring. |
| **MFA fatigue** | Nhiều challenge bị từ chối rồi một approval. | Contextual factor, rate controls, session risk response. |
| **Token replay/session hijack** | Token bị lấy cắp, dùng ngoài session context. | Sender constraints khi hỗ trợ, revocation, short TTL và resource checks. |
| **Policy bypass qua API** | UI yêu cầu step-up nhưng API cho action trực tiếp. | PEP tại resource, negative integration tests. |
| **Cross-tenant confusion** | Subject/device ID được coi giống nhau ở hai issuers. | Issuer + tenant + audience namespace. |
| **Stale group claims** | Token còn role cũ sau Mover. | Authorization refresh/version, revoke và target readback. |
| **Incomplete JML mapping** | Email tái cấp hoặc account phụ không gắn Engagement. | Canonical identity graph, unresolved-risk handling. |
| **False signal from compromised source** | Admin sửa risk flag hoặc MDM status. | Source governance, SoD, integrity, independent telemetry. |
| **Risk outage fail-open** | PDP không nhận signals nhưng vẫn ALLOW. | Risk-tier degraded policy và hard gates. |
| **Overblocking/denial of service** | Attacker gây false alerts để khóa người hợp lệ. | Confidence, triage, rate controls, independent approval. |
| **Privacy harm** | Thu thập quá mức location/behavior hoặc SIEM export. | Minimization, restricted access, retention. |
| **Exception abuse** | Approver tạo allowlist không hạn cho mọi truy cập. | Owner, justification, scope, expiry, audit và review. |
| **AI/model drift** | Risk predictions sai sau thay nền tảng hoặc user patterns. | Monitoring, calibration, rollback và human review. |

### 28.1. Không đặt toàn bộ tin cậy vào risk model

Risk engine có thể bị sai hoặc bị vô hiệu. **Khóa ranh giới** gồm token validation, lifecycle eligibility, tenant isolation, resource authorization và SoD phải còn hiệu lực ngay cả khi risk model gặp sự cố.

### 28.2. Kiểm soát ngoại lệ là bề mặt tấn công

Allowlist một IP hoặc một user để “không bị MFA làm phiền” có thể bị khai thác lâu dài. Cần ghi:
- Ai phê duyệt, dựa vào chính sách nào?
- Chủ thể, action, resource, thời gian, thiết bị/tenant cụ thể.
- Compensating controls và mức rủi ro còn lại.
- Owner và `expiresAt`/review date.
- Evidence khi exception được gỡ.

**“Đã được exception” không nghĩa là “rủi ro đã biến mất”.**

## 29. Case study 1 — Người dùng đi công tác, Geo-IP bất thường

**Bối cảnh giả định:** Hương là nhân viên ACTIVE, có role để xem báo cáo. Hương đi công tác, dùng laptop công ty managed/compliant và passkey để mở portal. Geo-IP cho thấy nước ngoài so với hoạt động tuần trước.

### 29.1. Những tín hiệu
| Nhóm | Quan sát |
| --- | --- |
| **Identity** | User ACTIVE, role read hợp lệ. |
| **Authentication** | Passkey verified với assurance phù hợp. |
| **Device** | Managed/compliant, posture tươi. |
| **Network** | Geo-IP khác baseline; có thể dùng VPN. |
| **Resource** | Báo cáo read-only, risk tier tương đối thấp. |
| **Behavior** | Chưa có hành động bất thường được xác minh. |

### 29.2. Quyết định minh họa

PDP có thể **ALLOW read** hoặc yêu cầu một bước xác minh tương xứng, tùy policy. Nếu chỉ do Geo-IP khác, **tự khóa toàn bộ quyền** có thể là false positive không cần thiết.

Đối với `customer.export`, chính sách có thể **STEP_UP** hoặc **RESTRICT** vì tác động cao hơn, ngay cả khi nguồn mạng chỉ là tín hiệu phụ.

### 29.3. Bài học

Một risk signal phải được xem trong **ngữ cảnh, độ tin cậy và hậu quả hành động**. Địa chỉ IP không xác nhận chính xác vị trí của người dùng. Cần kênh hỗ trợ hợp lệ khi signal bị sai.

## 30. Case study 2 — Đăng nhập qua MFA nhưng session bị nghi chiếm

**Bối cảnh giả định:** một tài khoản tài chính nhận nhiều MFA push bị từ chối, sau đó một push được chấp nhận. Session mới lập tức thực hiện nhiều lần export lượng dữ liệu lớn từ một thiết bị chưa được xác minh.

### 30.1. Dòng sự kiện giả định

~~~text
14:00–14:08  9 MFA challenges: DENIED/EXPIRED.
14:09        MFA_VERIFIED.
14:09        AUTHENTICATION_SUCCEEDED.
14:10        Device posture: UNKNOWN.
14:11        API: customer.export requests spike.
14:12        Risk engine raises session risk to HIGH.
~~~

### 30.2. Phân tích

MFA_VERIFIED cho biết provider chấp nhận yếu tố theo giao thức, nhưng **không tự bảo đảm không có social engineering, push fatigue hoặc session hijack**. Cần tương quan:
- Flow/issuer/subject và source network đáng tin.
- Device binding, posture và mới/cũ.
- Factor enrollment/reset gần đây.
- Session/token issuance và API resource actions.
- User report, PAM activity, role và business need.

### 30.3. Phản ứng minh họa

Theo security policy, high-confidence compromise có thể dẫn tới:
1. **DENY customer.export** ở API/PEP.
2. Revoke session/token family khi đủ căn cứ hoặc theo quy trình rủi ro.
3. Cảnh báo SOC/IAM, bảo toàn chứng cứ và xác minh yếu tố xác thực.
4. Điều tra dữ liệu đã xuất và các session/credential liên quan.
5. Khôi phục truy cập qua đường an toàn sau xử lý, không chỉ reset risk score.

### 30.4. Bài học

**Một lần authentication success không thể thay thế đánh giá rủi ro ở mức hành động/resource**. Cần phát hiện hành vi sau đăng nhập và thực thi ở API.

## 31. Case study 3 — Mover vẫn dùng admin token cũ

**Bối cảnh giả định:** Tuấn chuyển khỏi đội SRE lúc 13:00. IGA đã chuyển role, nhưng token `production-admin` phát lúc 12:50 vẫn còn thời hạn. Thiết bị và network của Tuấn đều healthy.

### 31.1. Các trạng thái cần tách

| Nguồn | Trạng thái tại 13:05 |
| --- | --- |
| **HRIS** | Mover effectiveAt=13:00, không còn nhiệm vụ SRE. |
| **IGA desired entitlement** | Production admin phải bị thu hồi. |
| **IdP/SSO session** | Có thể còn ACTIVE. |
| **API token** | `exp` chưa đến, claims cũ. |
| **Resource authorization** | Cần kiểm entitlement hiện hành, không chỉ JWT exp. |
| **Device risk** | LOW nhưng không liên quan việc người dùng còn quyền admin. |

### 31.2. Kết quả kỳ vọng

Action sửa IAM policy sau 13:00 phải **bị từ chối theo policy Mover**, nếu role/authorization đã hết hiệu lực. Nếu API chỉ dựa JWT claim cũ, cần đánh giá **confirmed residual access** và khắc phục bằng session/authorization version, revocation hoặc resource-side check phù hợp.

### 31.3. Bài học

Risk-based access không được thay thế JML. **Risk thấp không làm entitlement cũ hợp lệ trở lại.**

## 32. Case study 4 — Service principal từ môi trường lạ

**Bối cảnh giả định:** workload `billing-reporter` thường chỉ đọc API báo cáo từ một cụm workload. Một ngày, credential của nó được sử dụng từ môi trường mới và gọi API thay đổi quyền IAM.

### 32.1. Bằng chứng
- Service principal ID, issuer, audience, credential ref và ownerTeam.
- Deployment/change records, runtime/host attestation nếu có.
- Trust domain, cloud region/network signals, device/host risk.
- API action/resource, tenant, authorization outcomes.
- Credential issuance/rotation history và thời điểm nghi lộ.

### 32.2. Phản ứng đúng

- **DENY** IAM policy mutation vì workload không có quyền.
- Tạo finding rủi ro về hành vi ngoài baseline và nguồn thực thi mới.
- Kiểm có rollout hợp lệ hay credential bị lộ; phối hợp service owner/SOC.
- Rotate/revoke credential khi policy/incident yêu cầu, đối soát API deny.
- Không đưa service principal qua human MFA hay gắn nhầm với kỹ sư tạo nó.

### 32.3. Bài học

Workload risk có thể dựa **cryptographic identity, runtime context, scope, behavior và owner**, nhưng **resource authorization vẫn là chốt chặn chính**.

## 33. Case study 5 — Mất IdP/MDM trong tình huống khẩn cấp

**Bối cảnh giả định:** một outage đồng thời khiến IdP không phát login mới và MDM không cập nhật compliance. Đội vận hành cần khôi phục production identity gateway, nhưng risk-based policy thông thường yêu cầu cả IdP và posture tươi.

### 33.1. Không nên làm

- Tắt toàn bộ risk engine hoặc MFA toàn doanh nghiệp.
- Mở admin role cho mọi network nội bộ.
- Chấp nhận `UNKNOWN=LOW` hoặc device `compliant=true` do client tự gửi.
- Dùng account Leaver hoặc PAT cá nhân lâu dài để sửa hệ thống.
- Bỏ ghi log vì “đang khẩn” rồi xem như không cần hậu kiểm.

### 33.2. Phương án kiểm soát

Sử dụng cơ chế emergency/break-glass **đã được phê duyệt và diễn tập**:
- Principal khẩn và actor được quy định, xác minh bằng phương án còn hoạt động.
- Scope và TTL tối thiểu cần cho phục hồi.
- Cảnh báo và audit độc lập hoặc lưu đệm an toàn có kiểm chứng khi hệ thống phục hồi.
- Thu hồi/rotate credential/session đúng quy trình.
- Review sau sự kiện bởi reviewer đủ thẩm quyền, độc lập và xử lý mọi exception.
- Đọc lại quyền ở IdP/PAM/cloud/application sau outage.

### 33.3. Bài học

Risk-based access phải hỗ trợ **khả năng khôi phục có kiểm soát**, không tạo phụ thuộc vòng tròn khiến tổ chức phải mở cửa truy cập vô hạn lúc sự cố.

**Chốt phần tình huống:** Năm ví dụ cho thấy quyết định không được dựa **một tín hiệu đơn lẻ**, và mọi action bị giới hạn phải được kiểm thực tế ở PEP, kèm bằng chứng và phương án khắc phục.


## 34. Ma trận kiểm thử Risk-based access

Một engine có thể xuất ra quyết định đẹp ở API nội bộ nhưng vẫn có lỗ hổng nếu resource server không thực thi, tín hiệu quá hạn hoặc quyền JML bị bỏ qua. Cần kiểm **positive, negative, boundary, failure, concurrency và end-to-end**.

### 34.1. Bộ test nền tảng

| Test ID | Tiền điều kiện | Hành động | Expected |
| --- | --- | --- | --- |
| **RBA-01** | User ACTIVE, entitlement đúng, device healthy, risk thấp. | Đọc dữ liệu thuộc scope. | ALLOW + audit. |
| **RBA-02** | User ACTIVE, risk thấp nhưng thiếu entitlement. | Gọi API admin. | DENY vì authorization; không cấp role. |
| **RBA-03** | Tài khoản Leaver, thiết bị managed/compliant. | Thử sign-in/API. | DENY/revoke theo JML. |
| **RBA-04** | Joiner trước Start date, pre-provisioned account. | Truy cập resource production. | DENY nếu policy chưa cho. |
| **RBA-05** | Mover đã mất role SRE, token cũ còn claim. | Gọi privileged API. | DENY theo quyền hiệu lực mới. |
| **RBA-06** | Rehire cùng email, Engagement mới. | Dùng old session/token. | DENY, không hồi sinh quyền E1. |
| **RBA-07** | User có role Export, device posture STALE. | Export sensitive dataset. | RESTRICT/DENY hoặc yêu cầu posture tươi theo policy. |
| **RBA-08** | Device được xác nhận LOST. | Gọi endpoint bằng session cũ. | DENY/REVOKE theo scope. |
| **RBA-09** | EDR báo HIGH_RISK sau login. | Gọi API export đang có session. | Re-evaluate và block/restrict theo policy. |
| **RBA-10** | IP Geo-IP lạ nhưng device/assurance tốt. | Đọc portal low-risk. | Không mặc định hard deny nếu policy coi location là tín hiệu phụ. |
| **RBA-11** | Client tự gửi `risk=0`, `trusted=true`. | Gọi resource high-risk. | Bỏ qua dữ liệu tự khai, xác minh server-side. |
| **RBA-12** | MFA challenge chỉ được gửi, chưa verified. | Gọi action cần step-up. | DENY/STEP_UP_PENDING, không ALLOW. |
| **RBA-13** | STEP_UP hoàn tất nhưng role đã bị thu hồi. | Retry action. | DENY, recheck current entitlements. |
| **RBA-14** | User verified step-up cho resource A. | Replay kết quả sang tenant/resource B. | DENY nếu binding/scope không phù hợp. |
| **RBA-15** | Risk model hạ điểm nhưng SoD conflict. | Tự duyệt khoản chi do chính mình tạo. | DENY nếu không có exception hợp lệ. |
| **RBA-16** | PAM JIT approval chưa có. | Thực hiện admin action. | DENY, risk LOW không thay approval. |
| **RBA-17** | JIT TTL hết, web session còn. | Gọi admin API bằng token cũ. | DENY privilege tại resource. |
| **RBA-18** | Local admin SaaS không qua SSO. | Thử authentication/authorization. | Được giám sát và policy tương ứng, không bỏ đường local. |
| **RBA-19** | SCIM group removal ACK nhưng local role còn. | Dùng local admin action. | Phát hiện residual grant và chặn theo khả năng/mitigation. |
| **RBA-20** | EDR outage, thiếu required posture. | Gọi API high-risk. | UNKNOWN policy, không tự coi risk LOW. |
| **RBA-21** | Geo-IP enrichment sai hoặc lag. | Gọi low-risk action hợp lệ. | Kết quả có giải thích, không chặn vô căn cứ ngoài policy. |
| **RBA-22** | Credential được xác nhận compromise. | Gọi resource dù những signal khác là good. | Hard DENY/incident theo policy. |
| **RBA-23** | Device `COMPLIANT` event cũ đến sau `LOST`. | Yêu cầu access. | Không cho stale event ghi đè trạng thái chặn. |
| **RBA-24** | Hai policy evaluations chạy đồng thời với Leaver. | Grant/token refresh. | Không hồi sinh quyền cũ, version/atomic handling. |
| **RBA-25** | API đi thẳng resource, bỏ UI step-up. | Gửi protected action. | PEP server-side vẫn chặn. |
| **RBA-26** | PDP trả RESTRICT read-only. | Thử export/update/delete. | Các thao tác ngoài phạm vi bị từ chối. |
| **RBA-27** | Session bị revoke, token vẫn còn `exp`. | Gọi resource API. | Đúng revoke policy; báo nếu không thể đảm bảo tức thời. |
| **RBA-28** | Workload hợp lệ, node healthy nhưng sai audience. | Gọi API tenant khác. | DENY trust/resource boundary. |
| **RBA-29** | Workload owner Leaver, job còn dùng PAT cá nhân. | Kiểm API/credential activity. | Finding + migration/rotate theo policy. |
| **RBA-30** | Two accounts same canonical Person. | Tự approve privileged exception. | Chặn SoD/self-approval. |
| **RBA-31** | Reviewer đã Mover/Leaver. | Dùng approval link cũ. | Recheck authority và từ chối/escalate. |
| **RBA-32** | Risk model/telemetry outage. | Admin production request. | Degraded mode đã định nghĩa, không blanket ALLOW. |
| **RBA-33** | Risk score LOW nhưng client không có device proof. | Gọi resource yêu cầu device identity. | DENY/STEP_UP theo policy, không tin một score. |
| **RBA-34** | Cert device đã revoke nhưng cache PEP cũ. | mTLS/auth API. | Từ chối sau giới hạn propagation cam kết; ghi window và defect. |
| **RBA-35** | Transaction bắt đầu khi LOW, risk HIGH trước commit. | Commit thay đổi nhạy cảm. | Recheck tại transaction boundary theo policy. |
| **RBA-36** | User được phép nhưng số lượng export vượt hạn. | Gọi export khối lượng lớn. | Limit/approval/deny theo business policy. |
| **RBA-37** | Exception đã hết `expiresAt`. | Dùng exception cho high-risk action. | DENY/route bình thường; không auto-extend. |
| **RBA-38** | Cross-tenant subject/device IDs trùng chuỗi. | Thử access tenant khác. | DENY nhờ issuer/tenant namespace. |
| **RBA-39** | Risk scoring thay model version. | Replay các trường hợp đã có nhãn. | Không làm mất hard gates, có drift/coverage report. |
| **RBA-40** | Risk engine trả STEP_UP, client bỏ qua challenge. | Gọi action với request ban đầu. | DENY, không có side effects. |

**Expected** phải được ràng buộc với policy thật của tổ chức. Không phải mọi PEP hỗ trợ RESTRICT hay QUARANTINE; hệ thống không có khả năng đó phải có phương án được duyệt, không giả định chức năng tồn tại.

### 34.2. Bằng chứng cho mỗi testcase

~~~text
testRunId / testCaseId
policyId / version / riskModelVersion
subject / issuer / tenant / engagement or workload owner
device / session / resource / action
preconditions and signal timestamps
expected decision + expected enforcement
actual PDP decision
actual API/PEP outcome
traceId / evidenceRefs
cleanup and residual access verification
PASS / FAIL / BLOCKED / INDETERMINATE
~~~

**Không tính BLOCKED/INDETERMINATE như PASS**. Nếu nguồn telemetry quan trọng offline, test cho tài nguyên nhạy cảm cần đánh giá risk/fallback và ghi nhận khoảng trống, không làm đẹp tỷ lệ.

## 35. Kiểm thử định tính, property-based và failure injection

### 35.1. Những bất biến đáng kiểm

~~~text
LOW risk cannot grant an entitlement that is absent.
TERMINATED subject cannot access protected resources.
REVOKED credential/session cannot authorize new actions.
Unapproved SoD conflict cannot be bypassed by scoring.
STEP_UP_PENDING cannot commit protected business action.
RESTRICT cannot be bypassed by direct API route.
Unknown mandatory signals cannot silently become known good.
Stale COMPLIANT cannot overwrite newer LOST.
Cross-tenant issuer/subject/device identifiers cannot collide.
Exception expiry must not create a renewed privilege.
Review decision cannot directly activate a privilege.
PEP outcome must match the security decision.
~~~

Có thể dùng property-based tests để sinh nhiều tổ hợp subject/device/resource/action/time và xác minh bất biến. **Đừng dùng cùng một bản sao policy engine làm oracle** nếu cả hai đều có thể mắc cùng lỗi; nên có test cases độc lập dựa vào policy được duyệt.

### 35.2. Failure injection trong staging

- IdP sign-in service unavailable.
- UEM/EDR signal stale hoặc missing.
- Policy engine latency vượt timeout budget.
- SCIM connector trả error/retry.
- Risk event tới trễ/đến đảo thứ tự.
- Redis/session cache giữ ALLOW cũ.
- PAM elevation kết thúc nhưng API token còn hạn.
- HRIS gửi Leaver cùng lúc token refresh.
- Authenticated log producer gửi record sai schema.
- Reviewer mất authority trước lúc approve.

### 35.3. Positive controls quan trọng như negative controls

Nếu engine DENY tất cả thì nhiều negative tests sẽ PASS, nhưng hệ thống không đáp ứng nghiệp vụ. Phải kiểm **user hợp lệ ở hoàn cảnh rủi ro thấp có thể tiếp cận tài nguyên được phép**, và đường remediation/step-up có thể hoàn tất khi đủ điều kiện.

### 35.4. An toàn khi diễn tập

Dùng staging, test tenant, dữ liệu giả, service principal thử nghiệm và kịch bản được ủy quyền. Không thực hiện phá hoại production, không đánh cắp token, không ép MFA người thật hoặc vô hiệu IAM policy thật để “kiểm tra khả năng chặn”. Các test accounts/keys/sessions phải có owner và được cleanup/readback.

## 36. KPI đánh giá chất lượng Risk-based access

Một hệ thống tốt không nhất thiết có nhiều DENY nhất; cần đo **quyết định đúng, tín hiệu đủ, độ trễ hợp lý và tác động nghiệp vụ**.

| KPI | Cách tính/diễn giải | Điều cần cảnh giác |
| --- | --- | --- |
| **Policy coverage** | Resources/actions bắt buộc có risk policy ÷ toàn bộ scope. | Scope thiếu thì kết quả đẹp giả. |
| **PEP enforcement coverage** | Đường resource có kiểm actual enforcement ÷ đường cần bảo vệ. | PDP decision không thay API check. |
| **Risk signal freshness rate** | Các quyết định dùng evidence trong TTL ÷ quyết định yêu cầu evidence. | Không gộp missing thành fresh. |
| **Unknown/stale decision share** | Decisions thiếu tín hiệu bắt buộc ÷ tổng cần check. | Thiếu telemetry không phải an toàn. |
| **Step-up completion rate** | Legitimate challenges hoàn tất ÷ step-ups được đưa ra, chia theo ngữ cảnh. | Tỷ lệ thấp có thể do UX/outage. |
| **False-positive rate** | Findings bị xác minh là nhầm ÷ findings đủ kết luận. | Không coi UNKNOWN là false positive. |
| **False-negative findings** | Các bypass/tấn công được phát hiện sau khi policy ALLOW. | Cần nguồn ground truth và review. |
| **High-risk action block success** | Known disallowed high-risk actions bị PEP chặn ÷ cases có bằng chứng. | Một critical bypass có thể chặn release. |
| **Risk decision latency p50/p95/p99** | Thời gian PDP/PIP phục vụ request theo percentile. | Average có thể che outliers. |
| **Risk propagation latency** | Từ signal observedAt tới PEP enforcement. | Phát hiện cửa sổ quyền tồn dư. |
| **Lifecycle revoke latency** | Leaver/Mover effectiveAt tới actual deny ở target. | Phải theo scope từng ứng dụng. |
| **Privileged exception compliance** | Exceptions có owner/expiry/verification ÷ exceptions bắt buộc. | Accepted không đồng nghĩa resolved. |
| **Device high-risk access** | Requests được ALLOW từ device xác nhận high-risk trái policy. | Chỉ số đòi evidence đáng tin. |
| **Session residual risk** | Sessions/tokens vẫn có hiệu lực sau revoke trái policy. | Không suy chỉ từ IdP disabled. |
| **User impact** | Support tickets, legitimate denials, recovery/reauth time. | Bảo mật phải xét khả năng sử dụng. |
| **Model/rule drift** | Biến động signal distribution và outcome qua version. | Thay policy/nguồn có thể tạo drift nhân tạo. |
| **Coverage gaps** | Apps/tenants/principal types không quan sát đủ. | Không báo “0 issue” ở vùng mù. |

### 36.1. Ví dụ báo cáo giả định

~~~text
RISK-BASED ACCESS – ILLUSTRATIVE OPERATING REVIEW
As-of: 2026-12-01 10:00 +07:00

In-scope protected action paths: 120
Paths with integrated risk PEP: 110
Coverage: 110 / 120 = 91.67%

Decisions observed in scope: 50,000
ALLOW:     42,000
STEP_UP:    4,000
RESTRICT:   2,000
DENY:       1,700
REVIEW:       300
Total:     50,000

Decisions with missing/stale mandatory signal: 600
Confirmed critical API bypass defects: 2
Leaver post-effective-access confirmed findings: 1
Privileged exceptions overdue: 3
Missing protected paths: 10
Next actions:
  - Fix two API bypass defects before widening rollout.
  - Investigate one post-Leaver access incident.
  - Onboard ten uncovered paths and resolve stale telemetry.
  - Review three overdue privileged exceptions.
~~~

**Số hoàn toàn minh họa.** 50.000 decision là các request đã được hệ thống tích hợp quan sát, không phải mọi lần truy cập. Không suy “ALLOW 84% nghĩa là an toàn 84%” hoặc “91,67% coverage là đạt” khi có critical bypass.

### 36.2. Cẩn thận với mẫu số

Nếu 110/120 PEP paths đã được bảo vệ nhưng 10 đường còn lại gồm tất cả production admin APIs, **coverage theo số lượng** không phản ánh exposure. Nên báo thêm **coverage theo risk tier, ứng dụng, credential/grant path và mức độ nhạy cảm**, không chỉ một tỷ lệ chung.

## 37. Runbook khi có quyết định rủi ro bất thường

### Bước 1 — Xác định request và hệ thống

Thu `decisionId`, `traceId`, issuer/tenant, principalRef, resource/action, eventTime, policy/riskModel version và PEP outcome. Không lấy raw tokens hoặc credentials vào ticket.

### Bước 2 — Kiểm định dữ liệu đầu vào

Đối chiếu:
- Identity/Engagement từ authoritative source.
- Device lifecycle và freshness; có LOST/REVOKED/STALE không?
- IdP/session/token assurance và issuer/audience.
- Entitlements/SoD/approval hiện hành.
- Risk signal provenance/ingestion lag, cả khả năng false positive.

### Bước 3 — Phân loại vấn đề

| Loại | Ví dụ | Hướng xử lý |
| --- | --- | --- |
| **False positive** | Người dùng công tác hợp lệ bị Geo-IP deny. | Tìm ngưỡng/correlation sai, cung cấp đường xác minh hợp lệ. |
| **False negative / bypass** | Admin API ALLOW dù Leaver hoặc role bị revoke. | Contain, incident/defect, kiểm tác động và fix PEP. |
| **Telemetry issue** | EDR outage khiến risk UNKNOWN. | Khôi phục nguồn, degraded policy và owner. |
| **Policy misconfiguration** | STEP_UP với action không hỗ trợ challenge. | Sửa policy/PEP mapping, kiểm regression. |
| **JML drift** | Old group/local grant còn sau Mover. | Reconciliation và verified revoke. |
| **Credential compromise** | Token reuse hoặc issuer trust bị lạm dụng. | Revoke/rotate, điều tra resource access. |
| **Business exception** | Trường hợp khẩn cần quy trình đặc biệt. | Escalation/approval độc lập, scope/TTL/audit. |

### Bước 4 — Giảm thiểu phù hợp

Có thể DENY resource, RESTRICT session, yêu cầu step-up, revoke token family, cách ly device hoặc chuyển human review theo risk policy. Không tự mở blanket admin, không gỡ MFA cho mọi user chỉ để chữa một false positive.

### Bước 5 — Sửa và kiểm xác nhận

Chạy negative/positive/boundary tests, kiểm API/PEP actual response và business side effects. Nếu API đã thực thi hành động trái policy, phải đánh giá **transaction/data changes đã xảy ra**, không kết luận sự cố khép kín chỉ vì request sau đã DENY.

### Bước 6 — Đóng hồ sơ và phản hồi model

Ghi root cause, impact, confidence, signal gaps, affected versions, remediation owner/dueAt, verifiedAt và thay đổi policy/model có thẩm quyền. Không xóa event gốc khi nhận định thay đổi.

## 38. Triển khai từng giai đoạn và release gates

### 38.1. Giai đoạn 1: xác định phạm vi và tính pháp lý

1. Inventory apps, API, workforce/partner identities, service principals và privileged paths.
2. Phân loại tài nguyên/hành động theo risk tier.
3. Xác định data sources, owners, privacy/retention và trust boundaries.
4. Viết chính sách hard gates + signal freshness + escalation.
5. Chuẩn bị UX cho step-up, restricted route và hỗ trợ người dùng bị chặn nhầm.

### 38.2. Giai đoạn 2: quan sát và hiệu chỉnh

1. Bật **observe-only/shadow policy** khi khả thi.
2. Đo tín hiệu thiếu, false positives, latency và policy distribution.
3. Kiểm identity correlation và phân loại PrincipalType.
4. Chạy case tests JML, device, MFA, session/token, PAM và workload.
5. Đánh giá fairness/privacy và đảm bảo quyền quyết định của policy owner.

### 38.3. Giai đoạn 3: enforcement theo rủi ro

Có thể bắt đầu ở nhóm **hành động high-impact được kiểm soát tốt**, hoặc rollout thận trọng theo app/tenant để giảm gián đoạn; chiến lược phụ thuộc khả năng phục hồi và risk appetite. Cần:
- A/B hoặc canary có kiểm soát, không mở rộng truy cập ngoài policy.
- Giám sát API bypass, adverse user impact và outage.
- Incident/rollback plan đã duyệt, không “rollback = tắt tất cả controls”.
- Đào tạo Helpdesk/SOC/App owners về reason codes và đường remediation.
- Bằng chứng pre/post rollout theo policy version.

### 38.4. Giai đoạn 4: vận hành và cải tiến

- Review thresholds/model drift và thay đổi threats.
- Reconcile privileged, direct/local, group, service credentials.
- Cập nhật owner, exception expiry, support playbooks.
- Diễn tập outage/emergency, JML drift và source tampering.
- Đánh giá coverage theo app, API, tenant và principal type định kỳ.

### 38.5. Release gate theo mức rủi ro

| Gate | Điều kiện kỳ vọng |
| --- | --- |
| **Hard gate regression** | Không có test chứng minh LOW risk vượt Leaver/entitlement/SoD. |
| **API enforcement** | Critical actions được bảo vệ ở server/resource. |
| **Session/token integration** | JML/security revoke không bị bypass bởi active token theo policy. |
| **Signal provenance** | Client spoofing và stale/unknown handling đã test. |
| **Positive usability** | User hợp lệ không bị deny-all ngoài policy. |
| **Audit completeness** | Decision, policy version và PEP result có evidence. |
| **Break-glass readiness** | Recovery có scope, TTL, alert và hậu kiểm. |
| **Owner sign-off** | Risk, Security, IAM, App owner chấp thuận phạm vi và nợ rủi ro. |

Các gate trên là **mẫu thiết kế**; severity, ngưỡng và thẩm quyền cuối cùng do tổ chức xác định.

## 39. Operating model và phân công trách nhiệm

| Vai trò | Trách nhiệm |
| --- | --- |
| **HRIS/People Ops** | Person, Engagement, Start/End/Move effectiveAt, sponsor dữ liệu nhân sự. |
| **IAM/IGA** | Identity correlation, entitlement, approval, JML reconciliation. |
| **IdP/SSO owner** | Authentication, MFA assurance, sign-in/session signals, token life cycle. |
| **UEM/MDM/EDR** | Device identity/posture/risk, evidence freshness. |
| **Application/API owner** | Resource classification, PEP, object-level authorization và action audit. |
| **PAM/Security Ops** | Privileged activation, JIT/SoD, emergency access và monitoring. |
| **Workload/Platform owner** | Service principal, issuer, deployment and credential lifecycle. |
| **Detection/SOC** | Threat signals, incident validation, feedback loop và false positive review. |
| **Risk/Governance** | Appetite, exception policy, compensating controls, approval authority. |
| **Privacy/Compliance** | Data minimization, processing purpose, retention/access rights. |
| **SRE/Platform** | Reliability, latency, caches, circuit breakers và continuity. |
| **Audit** | Đánh giá evidence và hiệu lực kiểm soát, không sửa log gốc. |

### 39.1. Không có “một đội sở hữu mọi risk field”

Account status từ HRIS/IGA khác device risk từ EDR và transaction value do ứng dụng nghiệp vụ quản lý. Cần **data contracts** cho từng signal: source owner, authority, version, freshness, error semantics và cách kiểm truy vết.

### 39.2. SoD trong quản trị policy

Người tạo exception hoặc thay threshold không nên có thể tự cấp quyền sensitive rồi tự chứng nhận an toàn. Cần **change approval, audit, review độc lập và separation of policy administration với enforcement** theo mức rủi ro.

## 40. Những ngộ nhận và lỗi triển khai thường gặp

| Ngộ nhận/sai lầm | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| **Risk-based = chỉ thêm MFA lúc login.** | Bỏ transaction/API/session changes. | Áp policy ở resource/action và trong phiên. |
| **Risk LOW nghĩa là được mọi quyền.** | Risk khác entitlement. | RBAC/ABAC/SoD hard gates trước ALLOW. |
| **Có role admin thì mọi lúc đều admin.** | Bỏ JIT, session, device và risk. | Privilege TTL, scope, approval, PEP. |
| **Device managed là trusted vĩnh viễn.** | Posture thay đổi, mất máy/compromise. | Fresh UEM/EDR/credential/lifecycle evidence. |
| **MFA challenge sent = đã xác minh.** | Challenge có thể bị deny/timeout. | Factor verification outcome. |
| **IP lạ là chắc chắn attacker.** | VPN/proxy/Geo-IP sai. | Multi-signal và user context. |
| **Missing signal = risk 0.** | Outage làm hệ thống dễ dãi. | UNKNOWN/STALE explicit policy. |
| **Gán score 80 là xác suất 80% bị hack.** | Score thường không calibrated probability. | Document scale và calibration. |
| **Chỉ cần PDP trả DENY.** | App/API có thể bypass PEP. | Actual resource/transaction tests. |
| **SCIM 204 nghĩa session đã bị cắt.** | Provisioning và session khác nhau. | Session/token/PAM/target readback. |
| **IdP disable là mọi SaaS không thể truy cập.** | Local sessions và PAT còn sống. | Multi-path revoke, effective-access evidence. |
| **Leaver có thể MFA để vào cứu hệ thống.** | Mất eligibility không được vượt bằng auth step-up. | Emergency governance riêng và named actor hợp lệ. |
| **Risk score luôn tăng đúng với rủi ro.** | Model bị drift/false signal/bias. | Monitor, tests, owner review. |
| **Review quá hạn tự động ALLOW.** | Mở cửa đặc quyền khi không có approval. | Escalation độc lập và deny/hold. |
| **Cấp token mới làm mới lại quyền cũ.** | JML/role stale hoặc refresh bypass. | Current authority check, token family constraints. |
| **Exception có thể tồn tại vô hạn.** | Standing bypass không được kiểm soát. | Scope, owner, expiry, compensating controls. |
| **Không có alerts nghĩa là không có vấn đề.** | Collector có thể hỏng. | Source health, coverage, gap detection. |
| **Thu thập càng nhiều dữ liệu người dùng càng tốt.** | Privacy/retention risk. | Data minimization và purpose limitation. |
| **Phê duyệt risk policy là xong vĩnh viễn.** | Thay role, app, threat và dữ liệu. | Regression, monitoring, periodic review. |

## 41. Checklist thực hành Risk-based access

### 41.1. Danh tính, quyền và chính sách

1. Đã có **authoritative Person/Engagement hoặc workload principal** và issuer/tenant namespace rõ chưa?
2. Có tách **risk signals** với **entitlement, authorization và hard deny** không?
3. User **Joiner trước Start date, Mover mất role, Leaver terminated, Rehire** có được kiểm effectiveAt chính xác không?
4. Mọi action quan trọng có **resource owner, classification và risk tier** không?
5. RBAC/ABAC, object/tenant scope và SoD có giữ hiệu lực dù score LOW không?
6. Risk policy có **ID/version, owner, reason codes và approval/change control** không?
7. Exception có **scope, time limit, approval authority, owner và compensating controls** không?

### 41.2. Tín hiệu và độ tin cậy

8. Mỗi signal có **provenance, source authority, observedAt, TTL và sourceVersion** không?
9. Hệ thống có phân biệt **GOOD/BAD/UNKNOWN/STALE** không?
10. Có chống **client-supplied risk score, spoofed device trust và cross-tenant identifier** không?
11. Geo-IP/network signals có được dùng với **độ không chắc chắn** phù hợp không?
12. Có kiểm source **IdP/SSO, UEM/MDM, EDR, PAM, HRIS/IGA, app và threat feeds** theo scope không?
13. MDM/EDR outage và telemetry lag có **degraded policy** rõ không?
14. Có logic precedence chống event `COMPLIANT` cũ ghi đè `LOST` mới không?
15. Có đánh giá **privacy, data minimization, retention và fairness** của signals không?

### 41.3. Thực thi và phiên

16. Quyết định PDP có được **PEP thực thi tại API/app/resource**, không chỉ UI không?
17. STEP_UP có **gắn đúng principal/action/resource** và re-evaluate sau khi hoàn tất không?
18. RESTRICT có thực sự chặn export/write/delete khi cho read-only không?
19. Có phân biệt **IdP session, RP/SP session, access/refresh token family và resource authorization** không?
20. Có cách xử lý **token/session còn sống sau Mover/Leaver/compromise** không?
21. PAM/JIT có **eligibility, approval, SoD, TTL, target verification và risk checks** không?
22. Workload có **ownerTeam, credential, scope, issuer, runtime context** khác với user MFA không?
23. Có continuity/break-glass không phụ thuộc vòng tròn vào IdP/MDM đang lỗi không?

### 41.4. Thử nghiệm, audit và cải tiến

24. Có test cả **positive/negative/boundary/failure/concurrency** với PEP outcome không?
25. Có test **API bypass, cross-tenant, stale signal, spoof client, JML, SoD, MFA fatigue** không?
26. Có test **credential/token revoked** thực sự bị API từ chối theo policy không?
27. Có theo dõi **false positive, false negative, source gaps, user friction và model drift** không?
28. Có log **policy/model version, evidenceRefs, decision, reason, PEP result** mà không lộ secret không?
29. Báo cáo có **mẫu số theo resource/action/tenant/principalType/risk tier** không?
30. Có phát hiện **outage của risk engine hoặc telemetry** thay vì báo 0 alert không?
31. Mỗi high-risk finding có **severity, owner, dueAt, mitigation và verified closure** không?
32. Việc thay role, device policy, IdP, SCIM, PAM hoặc API có kích hoạt **regression tests** không?
33. Có phân biệt **PASS, FAIL, BLOCKED, INDETERMINATE và NOT_RUN** khi test không có evidence không?
34. Test users, tokens, JIT roles, policy exceptions có được **cleanup và readback** không?
35. Có đường hỗ trợ người dùng bị chặn nhầm mà vẫn **bảo toàn kiểm soát rủi ro** không?
36. Có kiểm **định kỳ hoặc sau thay đổi trọng yếu** theo trách nhiệm owner được xác định không?

## 42. Kết luận: risk-based access là kiểm soát quyền theo ngữ cảnh, không phải chiếc máy chấm điểm tự cấp quyền

Một triển khai vững cần kết nối:

~~~text
IDENTITY LIFECYCLE VÀ ENTITLEMENT HỢP LỆ
    Person / Engagement / Workload / Tenant
    Joiner – Mover – Leaver + RBAC / ABAC / SoD
                         ↓
TÍN HIỆU RỦI RO ĐÁNG TIN
    IdP / MFA / Session + Device / EDR + Behavior
    observedAt + freshness + provenance + uncertainty
                         ↓
PDP ĐÁNH GIÁ THEO RESOURCE VÀ ACTION
    Hard gates trước; risk tier + auth assurance
    ALLOW / STEP_UP / RESTRICT / DENY / REVIEW
                         ↓
PEP THỰC THI QUYỀN THỰC TẾ
    IdP / ZTNA / API / Application / PAM
    Không có API bypass hoặc stale session grant
                         ↓
AUDIT, RECONCILIATION VÀ FEEDBACK
    Decision/evidence + JML drift + incident response
    Metrics + calibration + privacy + exception expiry
~~~

**Ghi nhớ:** **Risk-based access là cách đưa rủi ro theo ngữ cảnh, thời điểm và hậu quả hành động vào quyết định truy cập**, chứ không phải chỉ đặt một điểm số bên cạnh tài khoản hay yêu cầu MFA với mọi đăng nhập. Cần kiểm **danh tính và quyền nền hợp lệ**, lấy tín hiệu **IdP/SSO, device, session, hành vi và tài nguyên** với nguồn gốc/độ tươi rõ, áp **policy theo risk tier và loại hành động** rồi xác minh **PEP đã thực thi**. Trong vòng đời **Joiner–Mover–Leaver**, risk thấp **không được vượt** Start date, termination, entitlement, SoD hoặc credential revocation. Risk-based access chỉ đem lại giá trị thực tế khi gắn với **RBAC/ABAC, SCIM, PAM/JIT, service/workload identities, audit và phát hiện quyền tồn dư**, đồng thời quản trị được **tín hiệu thiếu, false positives, quyền riêng tư, ngoại lệ và khả năng khôi phục trong sự cố**.
