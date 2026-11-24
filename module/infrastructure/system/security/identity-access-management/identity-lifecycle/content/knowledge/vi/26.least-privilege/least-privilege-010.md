# Đo mức tối thiểu của đặc quyền trong IAM (Measuring Least Privilege)

**Đo mức tối thiểu (measuring least privilege)** là quá trình xác định và định lượng sự khác biệt giữa **quyền thực sự cần thiết để hoàn thành nhiệm vụ đã được phê duyệt** với **quyền mà một danh tính hiện có khả năng sử dụng**. Mục tiêu không phải giảm số quyền về 0, mà là cung cấp **đủ quyền, đúng tài nguyên, đúng thời điểm, đúng thời hạn và đúng bối cảnh**, đồng thời phát hiện các quyền dư thừa và chứng minh việc thu hồi có hiệu lực.

Bài học thuộc chương **Least privilege**, module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Theo phạm vi module, IAM quản lý vòng đời danh tính **Joiner–Mover–Leaver (JML)** từ xác minh, tạo tài khoản, cấp quyền đến rà soát và thu hồi khi thay đổi vai trò. Việc đo quyền tối thiểu cần liên kết với **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và mục tiêu giảm **quyền truy cập tồn dư**. Đo lường là cầu nối giữa lời tuyên bố “chúng tôi áp dụng least privilege” và bằng chứng rằng người dùng, ứng dụng hoặc workload **không thể thực hiện hành động ngoài nhu cầu hợp lệ**.

**Tình huống dẫn nhập:** Nhân viên An chuyển từ Sales sang Finance. IdP đã gỡ nhóm Sales, nhưng An vẫn giữ quyền xuất dữ liệu CRM qua một role tại ứng dụng, một liên kết chia sẻ và access token còn hạn. Dashboard chỉ đếm nhóm IdP sẽ báo ít quyền hơn, trong khi API vẫn chấp nhận thao tác không còn phù hợp. Để đo least privilege, phải xem **quyền có hiệu lực ở mọi đường truy cập**, đối chiếu **nhu cầu hiện hành được phê duyệt**, rồi kiểm chứng kết quả thu hồi tại tài nguyên.

## 1. “Mức tối thiểu” là tối thiểu theo cái gì?

Least privilege thường được diễn đạt là **cấp đúng quyền cần thiết, không rộng hơn, không lâu hơn nhu cầu**. Tuy nhiên, “tối thiểu” không phải một số tuyệt đối có thể áp dụng cho mọi tài khoản.

Xét hai người:

- **Nhân viên hỗ trợ** có thể cần quyền đọc thông tin liên hệ của khách hàng trong tenant được phân công, nhưng không được xuất toàn bộ dữ liệu hoặc đổi chính sách.
- **Quản trị viên khôi phục thảm họa** đôi khi cần quyền rất mạnh trong một khoảng thời gian khẩn cấp đã được duyệt; duy trì quyền global admin liên tục khi không có nhiệm vụ là một vấn đề khác.

Vì vậy, một phép đo tốt luôn gắn với **nhiệm vụ, phạm vi tài nguyên, danh tính, điều kiện và thời gian**. Một vai trò ít permissions chưa chắc an toàn nếu permission duy nhất là wildcard administrator; ngược lại, nhiều quyền đọc hẹp phục vụ công việc có thể phù hợp.

### Ba câu hỏi cần trả lời

1. **Được phép cần gì (required/approved)?** Nhu cầu nghiệp vụ, quyết định của chủ sở hữu dữ liệu, phê duyệt, role và chính sách.
2. **Đang có thể làm gì (effective)?** Quyền cuối cùng sau RBAC, ABAC, ACL, nhóm lồng, delegation, token và enforcement.
3. **Thật sự đã làm gì (observed)?** Những hành động ghi nhận trong log, trong cửa sổ quan sát, với giới hạn dữ liệu phù hợp.

**Observed usage không phải bằng chứng đầy đủ của required access.** Quyền khôi phục thảm họa có thể không được dùng cả năm nhưng vẫn cần thiết ở chế độ khẩn cấp; ngược lại, một quyền được dùng nhiều lần cũng có thể không được phê duyệt.

## 2. Phân biệt các tập quyền trước khi tính chỉ số

Để không nhầm ý nghĩa, ký hiệu theo một chủ thể và phạm vi xác định:

| Ký hiệu | Tập hợp | Diễn giải |
| --- | --- | --- |
| **N** | Needed / approved permissions | Những khả năng truy cập thực sự cần cho nhiệm vụ, được phê duyệt ở trạng thái hiện hành. |
| **G** | Granted / assigned permissions | Các quyền được cấu hình qua role, group, ACL, policy hoặc grant. |
| **E** | Effective permissions | Các hành động hệ thống có thể cho phép trên tài nguyên/ngữ cảnh, sau khi thực thi rule kết hợp. |
| **U** | Used / observed permissions | Các hành động đã được quan sát trong cửa sổ đo, trên các nguồn log đã thu thập. |
| **V** | Verified permissions | Các quyết định ALLOW/DENY đã được kiểm chứng bằng readback hoặc probe hợp lệ tại PEP. |

**Thông thường không thể giả định E = G.** Một grant có thể bị explicit DENY, giới hạn tenant, bị khóa do status LEAVER hoặc chưa tới ngày hiệu lực. Ngược lại, E có thể xuất phát từ đường ACL trực tiếp, SaaS local account hay token không có trong inventory G ban đầu.

### Mô hình chênh lệch

Từ tập quyền được phê duyệt N và quyền hiệu lực E, có hai nhóm trọng tâm:

\[
\text{Excess} = E \setminus N
\]

\[
\text{Missing} = N \setminus E
\]

- **Excess** là những quyền có hiệu lực nhưng không có cơ sở cần thiết/được duyệt tại thời điểm đánh giá.
- **Missing** là những quyền cần thiết và được duyệt nhưng hiện chưa sử dụng được; có thể gây gián đoạn vận hành.
- **E ∩ N** là quyền cần thiết và đang có hiệu lực.

Các phép toán tập hợp chỉ có nghĩa nếu **cùng mô hình permission, cùng phiên bản policy và cùng thời điểm/ngữ cảnh**. Một entitlement “đọc mọi hóa đơn” không thể được so bằng một chuỗi đơn giản với entitlement “đọc hóa đơn thuộc tenant VN” mà không chuẩn hóa phạm vi.

## 3. Đơn vị đo: đừng chỉ đếm role

Một phép đo thực dụng nên bắt đầu từ một **permission decision tuple**:

\[
p = (\text{subject}, \text{action}, \text{resource scope}, \text{context}, \text{validity})
\]

Ví dụ:

~~~text
subject        = person-4821
action         = invoice.read
resourceScope  = tenant-vn / APPROVED
context        = employee ACTIVE + Finance Reader
validity       = 2026-11-01T00:00:00Z .. no-expiry
~~~

Các chiều này tạo ra sự khác biệt:

| Permission mô tả | Không thể coi tương đương với |
| --- | --- |
| invoice.read trong tenant-vn | invoice.read trên mọi tenant |
| customer.export cho 1 dự án | customer.export trên toàn CRM |
| secret.read cho 1 path | secret.read với wildcard toàn vault |
| deploy trên staging | deploy production |
| admin trong 30 phút với phê duyệt | standing admin suốt năm |
| access token scope report.read | API token có khả năng thao tác report.delete |

**Không đếm số tên role rồi kết luận giảm quyền.** Một role lớn có thể mở hàng trăm tài nguyên. Khi chính sách quá rộng hoặc tài nguyên động, nên phân loại theo **cấp độ quyền/capability và phạm vi thực tế**, hoặc dùng kiểm thử đại diện theo rủi ro, thay vì giả vờ liệt kê mọi đối tượng vô hạn.

### Chuẩn hóa quyền trước khi so sánh

1. Định nghĩa **action taxonomy**: read, export, approve, admin, assignRole...
2. Định nghĩa **resource scope**: tenant, project, classification, environment, object ID hoặc điều kiện policy.
3. Gắn **principal type**: HUMAN, WORKLOAD, SERVICE_ACCOUNT, PARTNER.
4. Xác định **effectiveAt/expiry** và quyền đang ở dạng standing, eligible, activated hay revoked.
5. Tách **phương thức cấp**: role, nested group, direct ACL, ABAC, JIT, delegated grant, OAuth scope, local account.
6. Xác minh **permission equivalence/subsumption**: quyền wildcard bao trùm các quyền hẹp nhưng không nên được tính là một quyền hẹp duy nhất.

Một đơn vị đo có thể là **entitlement edge** (subject → capability → resource scope), **policy decision case** hoặc **privilege-hours** theo thời gian. Phải công khai đơn vị trên dashboard để người đọc không nhầm các số liệu khác bản chất.

## 4. Nguồn dữ liệu để đo least privilege

| Nguồn | Giá trị cung cấp | Giới hạn và rủi ro |
| --- | --- | --- |
| **HRIS / Contractor registry** | Trạng thái Joiner–Mover–Leaver, chức danh, department, effectiveAt. | Không trực tiếp biết mọi quyền SaaS đang có. |
| **IAM/IGA** | Approval, desired entitlements, access review, SoD. | Quyền mong đợi có thể chưa đồng bộ tới hệ thống đích. |
| **IdP/Directory** | User, group, role claim, account state, SSO session. | Không phản ánh hết ACL, local account, token đã phát. |
| **SCIM/Provisioning connectors** | User/Group trên target, trạng thái đồng bộ và identifiers. | API success không chứng minh mọi đường authorization bị thu hồi. |
| **PAM/PIM/JIT platform** | Eligible/active admin roles, thời gian activation và approval. | Cần tính cả admin ngoài PAM hoặc break-glass account. |
| **Cloud IAM / K8s / Vault** | Policies, bindings, service accounts, secrets và quyền máy. | Cần diễn giải wildcards, conditions, deny, trust boundaries. |
| **Ứng dụng/API** | Effective roles, ACL, authorization decisions, audit events. | Log có thể thiếu đường batch/async hoặc bị cache. |
| **OAuth AS / token service** | Clients, grants, scopes, refresh token/revocation metadata. | JWT access token đã cấp có thể còn được RS chấp nhận. |
| **SIEM / audit trail** | Sử dụng quan sát được, từ chối, bất thường. | Không có log không đồng nghĩa quyền chưa dùng; log có thể mất hoặc chưa bật. |
| **Data catalog / owner** | Resource classification và yêu cầu truy cập hợp lệ. | Nhãn hoặc owner không cập nhật làm méo kết quả đo. |

### Điều kiện chất lượng dữ liệu

Trước khi công bố số liệu, gắn mỗi nguồn với:

- **Coverage**: bao nhiêu ứng dụng, PEP, tài nguyên và kiểu principal đang được quan sát.
- **Freshness**: trạng thái snapshot chậm bao lâu so với event nhân sự và policy.
- **Accuracy**: mapping stable ID, subject/tenant và group nesting có đáng tin.
- **Completeness**: có bỏ sót local ACL, direct shares, workload roles, PAT hoặc session không.
- **Integrity/provenance**: ai có thể sửa và nguồn dữ liệu có được xác thực.
- **Sampling limitations**: nếu chỉ thử mẫu, phần nào không được kiểm và sai số có thể ra sao.

**Thiếu một đường quyền quan trọng phải được báo là coverage gap**. Không đặt mặc định phần không quan sát được bằng 0 quyền dư thừa.

## 5. Kiến trúc đo lường và đối soát

~~~mermaid
flowchart TD
    HR["HRIS / Partner Registry<br/>JML events"] --> NEED["IGA + Business Approval<br/>Required Access N"]
    POL["Policy inventory<br/>RBAC/ABAC/SoD"] --> NEED
    IDP["IdP / Directory / SCIM"] --> COL["Entitlement Collector"]
    APP["Apps / APIs / ACLs"] --> COL
    PAM["PAM / PIM / Cloud IAM"] --> COL
    TOKEN["OAuth / Service Identity"] --> COL
    COL --> EFFECT["Normalized Effective Access E"]
    PEP["Authorization events / probes"] --> OBS["Observed Usage U + Verified V"]
    NEED --> COMP["Comparison + Risk Scoring"]
    EFFECT --> COMP
    OBS --> COMP
    COMP --> DRIFT["Excess / Missing / Unverified"]
    DRIFT --> OWNER["Owner Review + Remediation"]
    OWNER --> VERIFY["Readback + Verify at PEP"]
    VERIFY --> METRIC["Metrics / Audit / Trend"]
~~~

Điểm mấu chốt là **hai dòng độc lập**:

1. **Desired/approved access** được xác lập từ nghiệp vụ, IGA, chính sách và trạng thái HR hiện hành.
2. **Actual/effective access** được thu thập và kiểm chứng từ hệ thống đích, bao gồm quyền tồn dư ngoài IdP.

Nếu dùng **chính kết quả runtime** để tạo “expected access”, phép đo sẽ tự xác nhận lỗi: policy cấp quá rộng rồi dashboard tự gọi mọi grant hiện hữu là “cần thiết”.

## 6. KPI 1 — Tỷ lệ quyền dư thừa (Excess Privilege Rate)

Với một tập các permission units đã chuẩn hóa và quan sát đủ:

\[
\text{Excess Privilege Rate} =
\frac{|E \setminus N|}{|E|} \times 100\%
\]

Nếu **E rỗng**, không chia cho 0: KPI này là **N/A** hoặc được quy ước minh bạch. Cần tách tình huống thực sự không có quyền khỏi tình huống **không thu thập được quyền**.

### Ví dụ có số liệu

Một nhóm có 12 permission edges đã xác minh, được business owner đánh giá:

- 7 quyền **cần thiết và được phê duyệt**.
- 3 quyền **đã xác định không còn cần và phải thu hồi**.
- 2 quyền **chưa rõ nghiệp vụ**, đang chờ owner xác nhận.

Không nên đưa cả 2 quyền chưa rõ vào tử số “đã xác nhận dư thừa”. Nên báo **excess confirmed = 3/12 = 25%**, **under review = 2/12 ≈ 16,7%** và coverage/confidence. Nếu sau review 2 quyền đều được xác nhận không cần, chỉ số sẽ thay đổi thành **5/12 ≈ 41,7%** (trên snapshot cùng phạm vi).

**Không kết luận 25% quyền đã được thu hồi**. Đó là tỷ lệ quyền dư thừa **được phát hiện**, còn việc giảm quyền cần đo ở target sau remediation.

### Những hạn chế

- 1 quyền global admin nguy hiểm hơn nhiều quyền read-only nhưng **đếm thô** có thể đánh giá thấp.
- Một permission wildcard có thể bao trùm nhiều tài nguyên; định nghĩa đơn vị quyết định kết quả.
- N có thể thiếu nhu cầu nghiệp vụ bất thường nhưng hợp lệ, ví dụ khôi phục hệ thống.
- E có thể thay đổi theo thời gian, tenant, trạng thái tài nguyên và conditional access.
- Một quyền cấp qua nhiều đường không nhất thiết là nhiều quyền hiệu lực độc lập; cần **deduplicate theo capability** và vẫn lưu các nguồn grant để remediation.

Vì vậy nên hiển thị EPR cùng **mức độ rủi ro, coverage và các nhóm quyền cao**, không xếp hạng đội ngũ chỉ từ một phần trăm.

## 7. KPI 2 — Bao phủ nhu cầu quyền hợp lệ (Required Access Coverage)

Để không giảm quyền quá mức dẫn đến gián đoạn:

\[
\text{Required Access Coverage} =
\frac{|N \cap E|}{|N|} \times 100\%
\]

Ví dụ trong một hệ thống có 10 permission units đã được business owner phê duyệt, nhưng user chỉ thực thi được 8:

- **Coverage = 8/10 = 80%**.
- Hai quyền thiếu cần điều tra: chưa provision, lỗi policy, sai tenant hoặc source attribute bị lỗi.

Chỉ số này quan trọng vì chiến dịch least privilege thiếu cân bằng có thể tạo nhiều **false deny**, khiến người dùng dùng tài khoản chung, xin admin đặc biệt hoặc tìm đường vòng.

### Khi nào hai chỉ số nhìn có vẻ mâu thuẫn?

Nếu hệ thống vừa có quyền thừa vừa thiếu quyền, EPR có thể cao và Required Access Coverage thấp. Ví dụ user được cấp wildcard admin ở sai môi trường nhưng không được deploy đúng ứng dụng cần dùng. Đếm tổng số quyền không thấy được sự cố đó.

**Mục tiêu không phải 100% quyền được dùng.** Mục tiêu là **100% nhu cầu hợp lệ được đáp ứng theo policy** và **không có quyền ngoài nhu cầu ở điểm thực thi**, trong giới hạn bằng chứng thu thập được.

## 8. KPI 3 — Mức quyền nhạy cảm còn tồn tại (High-Risk Exposure)

Tỷ lệ dư thừa thô cần bổ sung **trọng số rủi ro**. Có thể phân nhóm:

| Mức | Ví dụ capability | Rủi ro điển hình |
| --- | --- | --- |
| **Critical** | Global admin, root, kiểm soát chính sách IAM, đọc toàn vault hoặc tạo signing key. | Có thể kiểm soát nhiều hệ thống/danh tính và mở rộng phạm vi tấn công. |
| **High** | Export toàn bộ dữ liệu nhạy cảm, approve payment, sửa production deployment. | Hậu quả dữ liệu/tài chính lớn. |
| **Medium** | Update dữ liệu theo tenant/project, đọc báo cáo nội bộ hạn chế. | Ảnh hưởng trong phạm vi nghiệp vụ rõ. |
| **Low** | Đọc dữ liệu nội bộ không nhạy cảm trong phạm vi hẹp. | Thiệt hại thấp hơn, nhưng vẫn cần kiểm soát. |

Một **risk-weighted excess** minh họa:

\[
\text{Weighted Excess Ratio} =
\frac{\sum_{p \in E \setminus N} w(p)}
{\sum_{p \in E} w(p)} \times 100\%
\]

Với trọng số thử nghiệm Low=1, Medium=3, High=10, Critical=30, một quyền global admin dư thừa có sức nặng lớn hơn nhiều quyền chỉ đọc. Tuy nhiên các trọng số **là lựa chọn quản trị của tổ chức**, không phải điểm chuẩn chung hoặc xác suất rủi ro chính xác. Phải có owner, hiệu chuẩn và phương pháp kiểm tra lại.

### Đừng để điểm tổng hợp che mất rủi ro cực đoan

Bên cạnh weighted ratio, luôn tách riêng:

- Số **standing global admins** và service principals có quyền rất rộng.
- Số tài khoản **privileged không có owner** hoặc không có MFA/PAM thích hợp.
- Số quyền **wildcard / cross-account / cross-tenant** đang có hiệu lực.
- Số grant nhạy cảm **không có expiry** hoặc không có approval.
- Số **đường tồn dư chưa thể kiểm chứng** sau Leaver hoặc incident.

**Zero critical unapproved grants** là mục tiêu an toàn cụ thể hơn việc chỉ cố giảm một chỉ số tổng hợp.

## 9. KPI 4 — Quyền không sử dụng và quyền không còn cần

Một chỉ số thường gặp là **Dormant Privilege Rate**, chẳng hạn tỷ lệ quyền không có hoạt động tương ứng trong 90 ngày.

\[
\text{Dormant Rate}_{T} =
\frac{|\{p \in E : \operatorname{ObservedUse}(p,T)=0\}|}{|E|} \times 100\%
\]

Trong đó T là cửa sổ quan sát **đã được nêu rõ**. Nếu không có log tin cậy hoặc không có dữ liệu đủ thời gian, kết quả phải là **UNKNOWN**, không coi là “chưa từng dùng”.

### Dormant không bằng excess

| Quyền không thấy dùng | Có thể cần thiết? | Hướng đánh giá |
| --- | --- | --- |
| Chạy failover khi sự cố hiếm gặp | Có, thường chỉ dùng khi thảm họa. | Có runbook, owner, thời hạn và khả năng kích hoạt JIT. |
| Đóng kỳ tài chính cuối quý | Có, không dùng đều mỗi tuần. | Kiểm chu kỳ nghiệp vụ, không cắt khi chưa đến kỳ. |
| Admin role của dự án đã đóng | Thường không còn. | Xác minh với owner, thu hồi rồi thử truy cập. |
| Quyền export của nhân viên đã chuyển phòng | Thường không còn hợp lệ. | Ưu tiên revoke theo JML, không cần đợi đủ 90 ngày. |
| Service principal của job chạy hàng năm | Có thể cần thiết. | Kiểm lịch job/DR, owner và cân nhắc activation theo thời gian. |
| Permission không có telemetry | Chưa rõ. | Bổ sung log/probe hoặc đánh dấu không quan sát được. |

**Không tự động thu hồi mọi permission “không dùng trong N ngày”** nếu có nhiệm vụ ít xảy ra nhưng được phê duyệt. Thay vào đó, phân nhóm: **dormant and unjustified**, **dormant but approved**, **unknown usage** và **active but unjustified**.

### Đo quyền đang được lạm dụng

Một quyền xuất dữ liệu được dùng hằng ngày **vẫn có thể trái least privilege** nếu nó vượt nhu cầu công việc. Do đó, cần so sánh với approved purpose/N và behavior baseline, không dùng tần suất sử dụng làm chứng cứ tự động rằng quyền hợp lệ.

## 10. KPI 5 — Standing privilege, eligible privilege và JIT

**Standing privilege** là quyền có hiệu lực liên tục; **eligible privilege** là quyền chủ thể có thể kích hoạt sau điều kiện; **JIT (Just-in-Time) privilege** là quyền tạm được kích hoạt theo thời hạn và mục đích.

| Trạng thái | Ý nghĩa | Cần đo |
| --- | --- | --- |
| **Standing** | Có thể thực hiện hành động bất cứ lúc nào khi các điều kiện khác đạt. | Số principal, cấp độ, khoảng thời gian có hiệu lực. |
| **Eligible** | Có thể xin/kích hoạt quyền, chưa chắc đang sử dụng được. | Ai có khả năng nâng quyền, điều kiện phê duyệt và phạm vi. |
| **Activated** | Quyền JIT đã được cấp tạm cho một phiên/khoảng thời gian. | Start/end, approval, action/resource, session recording nếu áp dụng. |
| **Expired/Revoked** | Quyền không còn hợp lệ theo policy. | Readback và kiểm PEP từ chối, kể cả token/session cũ. |

### Privilege-hours

Khi so hai cơ chế cấp admin quyền rộng, **số phút/giờ quyền có hiệu lực** có thể phản ánh thời gian phơi bày tốt hơn số lần cấp.

\[
\text{Standing Privilege Hours}
= \sum_{p \in \text{HighRiskActive}} \operatorname{HoursActive}(p,T)
\]

Ví dụ một role admin tồn tại liên tục 30 ngày tạo ra **720 privilege-hours** trong khoảng đo. Nếu một nhiệm vụ hợp lệ chỉ cần admin 2 giờ, dùng JIT có thể giảm đáng kể **thời gian quyền hiệu lực**, nhưng phải xác minh JIT được thu hồi khi hết hạn.

**Không cộng privilege-hours thành xác suất tấn công.** Đây là thước đo thời gian phơi bày; rủi ro còn phụ thuộc scope, cách dùng, MFA, nguồn truy cập và khả năng giám sát.

### KPI bổ sung

- **High-risk standing access count:** số chủ thể giữ đặc quyền cao liên tục.
- **JIT activation share:** tỷ lệ các trường hợp sử dụng quyền cao đi qua JIT/PAM trong tập đã xác định.
- **JIT policy compliance:** activation có approval, TTL, justification và session control đúng không.
- **Expired activation residuals:** số activation đã hết hạn nhưng PEP còn cho phép.
- **Eligible privilege sprawl:** số tài khoản đủ điều kiện tự nâng quyền dù hiếm khi dùng.

**Không xếp “eligible” ngang “active”.** Eligibility tạo khả năng nâng quyền và có rủi ro riêng; nhưng privilege-hours chỉ nên tính quyền thực sự đã kích hoạt hoặc có thể dùng theo định nghĩa được công bố.

## 11. KPI 6 — Thời gian thu hồi quyền (Revocation Latency)

Trong JML, việc thu hồi quyền chỉ hoàn thành khi **điểm thực thi không còn chấp nhận hành động đã bị cấm**.

\[
\text{Revocation Latency}
= t_{\text{verified DENY at required PEPs}} - t_{\text{effectiveAt}}
\]

Ví dụ:

~~~text
09:00  HRIS: Mover effectiveAt
09:02  IGA: desired access cập nhật
09:03  IdP: group cũ đã gỡ
09:05  SCIM: SaaS role update accepted
09:08  API chính: DENY hành động Sales
09:15  Export worker: vẫn ALLOW do cache cũ
09:20  Export worker: verified DENY
~~~

Với **cả API chính và export worker đều bắt buộc**, Revocation Latency ở phạm vi này là **20 phút** (từ 09:00 đến 09:20), không phải 3 phút từ IdP hoặc 5 phút từ SCIM.

### Các chiều cần báo cáo

- **P50/P95/P99** độ trễ theo ứng dụng/loại quyền, khi có đủ dữ liệu để tính phân vị.
- **Maximum unresolved age** của quyền dư thừa chưa khắc phục.
- **Tỷ lệ thu hồi trong SLA** theo risk tier.
- **Leaver residual access count** và số target chưa VERIFIED.
- **Privilege regrant after revoke** do sự kiện cũ, cache, connector replay hoặc khôi phục directory.

Nếu một target không có khả năng probe, latency không thể xác minh phải ghi **UNVERIFIED/UNKNOWN**, không mặc định là 0. Với các tài nguyên đặc biệt nhạy cảm, tổ chức cần chọn SLA đủ ngắn và kiến trúc RS có thể kiểm trạng thái hiện hành.

## 12. KPI 7 — SoD, orphaned access và ngoại lệ

Các quyền gây rủi ro không nhất thiết là “thừa” theo một role đơn giản. **Separation of Duties (SoD)** có thể cấm hai quyền cùng tồn tại hoặc cấm một người vừa tạo vừa duyệt một giao dịch.

### SoD violation rate

~~~text
SoD conflict = principal có tập quyền/quan hệ vi phạm policy
               hoặc thực hiện thao tác kết hợp bị cấm
~~~

Một báo cáo hữu ích cần phân biệt:

- **Static SoD:** quyền có thể đồng thời được cấp, tạo khả năng thực hiện hành động xung đột.
- **Dynamic SoD:** thực tế cùng người cố tự phê duyệt tài nguyên do chính họ tạo.
- **Approved exception:** ngoại lệ được duyệt có thời hạn, kiểm soát bù trừ và audit riêng.

Không chỉ đếm số role trong một chủ thể; policy cần xét **mức tài nguyên và ngữ cảnh**. Hai role không xung đột trên hai môi trường cô lập có thể xung đột trên cùng một quy trình production.

### Orphaned privilege

**Orphaned privilege** là quyền/tài khoản thiếu chủ sở hữu nghiệp vụ hoặc kỹ thuật hợp lệ, như:

- Service account không có owner sau khi người phụ trách rời tổ chức.
- App integration không còn sản phẩm sử dụng nhưng client credential vẫn active.
- Project cũ đã đóng nhưng shared ACL và API keys còn tồn tại.
- Direct admin grant không tìm được approval/sponsor.

Chỉ số cần có:

| Chỉ số | Cách xác định |
| --- | --- |
| **Orphaned privileged identity count** | Tài khoản đặc quyền không có owner hợp lệ trên danh mục. |
| **Unapproved high-risk grants** | Quyền hiệu lực nhạy cảm không tìm được approval đang còn hiệu lực. |
| **Exception aging** | Thời gian ngoại lệ tồn tại, có quá hạn hoặc vượt TTL không. |
| **SoD conflicts unresolved** | Xung đột chưa được gỡ hoặc chưa có xử lý tạm phù hợp. |
| **Re-attestation overdue** | Quyền tới hạn review nhưng owner chưa chứng nhận. |

Một grant đang được sử dụng đều nhưng không có owner/approval vẫn cần điều tra. **Mức độ sử dụng không hợp thức hóa quyền.**

## 13. Đo Blast Radius và phạm vi đặc quyền

**Blast radius** chỉ phạm vi tài nguyên, dữ liệu hoặc hệ thống có thể bị ảnh hưởng nếu một chủ thể/credential bị lạm dụng. Trong least privilege, cần đánh giá **khả năng gây tác động**, không chỉ số quyền được đặt tên.

Một admin permission có wildcard trên mọi cloud project có thể nguy hiểm hơn nhiều permission read-only bị giới hạn một nhóm nhỏ. Khi đo, phân tích:

1. **Số tenant/account/project** bị bao trùm.
2. **Loại hành động**: read, export, write, destroy, grant permission, impersonate.
3. **Mức nhạy cảm tài nguyên**: dữ liệu khách hàng, tiền, secret, signing key, IAM control plane.
4. **Khả năng mở rộng quyền**: tạo role mới, assume role, thay trust policy, đọc secret dùng ở nơi khác.
5. **Đường truy cập gián tiếp**: service account, delegated API, pipeline, group nested, shared vault.
6. **Giới hạn context**: thời gian, IP/network, device assurance, approval, JIT hoặc môi trường.
7. **Kiểm soát phòng ngừa/phát hiện**: MFA, PAM, segmentation, alerts, immutable audit.

### Vì sao không có một công thức blast radius chung?

“10.000 resource có thể đọc” và “1 vault chứa signing key” không thể quy đổi bằng một phép đếm khách quan duy nhất. Nên báo **nhiều chiều**, lập risk tier do security/data owner hiệu chuẩn, và công khai giả định.

Ví dụ dashboard minh họa:

~~~text
Principal                  = ci-deployer-prod
Active permission          = deploy:update, secret:read
Environment                = production
Affected projects          = 4
Tenant boundary            = tenant-vn
Can modify IAM policies?   = NO (đã kiểm)
Can read signing keys?     = NO (đã kiểm)
Owner                      = platform-team
JIT / time limit           = deployment window
Last recertified           = 2026-11-01
Residual unknown paths     = 1 legacy runner (UNVERIFIED)
~~~

Một dòng **UNVERIFIED** không được bỏ khỏi xếp hạng vì chưa biết scope; nên coi là **rủi ro quan sát chưa đầy đủ** và lên kế hoạch xác minh.

## 14. Đo least privilege theo Joiner–Mover–Leaver

| Giai đoạn | Quyền hợp lệ được xác định từ đâu? | KPI/kiểm chứng trọng tâm |
| --- | --- | --- |
| **Joiner** | HRIS, identity proofing, onboarding role, manager và application owner approval. | Zero pre-start access, baseline access đúng thời hạn, không có default admin. |
| **Mover** | Vai trò/tổ chức/dự án mới, SoD và thu hồi entitlement cũ. | Excess sau Mover, revocation latency, quyền role mới đúng, không privilege overlap sai. |
| **Leaver** | Thời điểm chấm dứt quan hệ và retention policy. | Zero unapproved residual access, disable/login, token/session, SaaS local, API key và vault. |
| **Suspension** | Quyết định HR/security tạm khóa. | Đường truy cập nhạy cảm bị chặn, hoạt động hỗ trợ vẫn được audit. |
| **Rehire** | Quan hệ mới và identity linking có thẩm quyền. | Không tự tái cấp quyền lịch sử từ account/email cũ. |
| **Contract expiry** | Ngày hết hạn hợp đồng/sponsor. | Auto-revoke và xác minh quyền theo mốc hiệu lực. |

### Joiner: không đo “số quyền tối thiểu” theo account trống

Người mới có thể được **pre-provision** trước ngày bắt đầu nhưng chưa được hoạt động. Đo:

- **Early privilege exposure:** quyền có hiệu lực trước approved effectiveAt.
- **Baseline coverage:** quyền cần thiết được cấp đúng thời hạn để người mới làm việc.
- **Approval-to-grant traceability:** quyền nào có sponsor/owner và chính sách cấp.
- **Default privileged grants:** tài khoản mới có quyền admin/tenant-wide ngoài nhu cầu không.

Một account được tạo sẵn nhưng disabled và không có quyền sử dụng thực tế **khác** với account đã có thể truy cập tài nguyên.

### Mover: cả quyền cũ lẫn quyền mới

Khi chuyển bộ phận:

1. Tính **N_before** và **N_after** theo ngày hiệu lực.
2. Xác định **to-revoke = E_before \ N_after**, bao gồm ACL và grants trực tiếp.
3. Xác định **to-grant = N_after \ E_before**, nhưng kiểm SoD trước khi cấp.
4. Thu hồi quyền cũ tại mọi hệ thống đích và token/session liên quan theo SLA.
5. Verify **DENY quyền cũ, ALLOW quyền mới** trên tài nguyên đúng phạm vi.

**Một Mover được cấp đúng Finance nhưng vẫn có Sales là thất bại về least privilege**, dù tổng số quyền sau thay đổi có thể thấp hơn trước.

### Leaver: đo effective denial thay vì success của connector

Các chỉ số:

- Tỷ lệ tài khoản bị chặn đăng nhập mới đúng mốc.
- Tỷ lệ ứng dụng/đường quyền đã readback.
- **Residual API/session/token access** sau effectiveAt.
- Số personal access tokens, direct ACL, service principal ownership hoặc secrets còn tồn dư.
- Thời gian từ event Leaver tới **verified DENY** tại các PEP bắt buộc.

**SCIM 204, IdP disabled hoặc “revocation requested” chưa đủ để đánh dấu quyền đã mất**. Một JWT access token tự chứa còn hạn có thể vẫn được API chấp nhận nếu RS chỉ kiểm chữ ký/exp. Cần kiến trúc TTL, introspection, denylist, entitlement check hoặc phương án tương đương đã được thiết kế.

## 15. Đo quyền con người và quyền máy (service accounts)

Một **workload identity** có quyền kỹ thuật khác với user: job đọc object storage, deploy lên cluster, lấy secret hoặc gọi API qua OAuth Client Credentials. Nó không nhất thiết có employmentStatus, department hay MFA tương tác.

| Chiều đo | Human identity | Service/workload identity |
| --- | --- | --- |
| Nguồn nhu cầu | Job role, owner approval, JML. | Service catalog, workload purpose, application owner. |
| Đơn vị quyền | Action/resource/tenant, role, ACL. | API scope, cloud role, namespace, secret path, trust binding. |
| Thời hạn | Nhân sự/dự án hoặc phiên JIT. | Lifecycle workload, runtime và rotation interval. |
| Principal proof | IdP authentication/MFA. | Managed identity, workload federation, mTLS hoặc confidential client. |
| Phơi bày | Standing user/admin access. | Long-lived secret, wildcard permissions, cross-env trust. |
| Thu hồi | Leaver/Mover, session/token. | Decommission, owner change, credential revoke/rotation. |

### Chỉ số hữu ích cho workload

- **Workload identity coverage:** tỷ lệ workloads có principal riêng và owner hợp lệ.
- **High-risk wildcard grants:** số quyền resource=* hoặc action=* còn hiệu lực.
- **Secret age/rotation status:** credential tĩnh đã tồn tại bao lâu, có theo policy không.
- **Unused active service principals:** principal còn active nhưng workload không còn sử dụng, sau khi kiểm log/owner.
- **Cross-environment privilege:** danh tính staging có quyền production ngoài policy không.
- **Workload impersonation reach:** ai có quyền assume role, đọc secret hoặc thay trust policy.
- **Revocation verification:** khi workload ngừng sử dụng, RS/cluster/vault có thực sự từ chối credential cũ?

Khi owner là nhân viên đã Leaver, **không nhất thiết xóa workload** đang phục vụ khách hàng. Hãy chuyển owner, thu hồi quyền quản lý của người cũ, đánh giá rotate secrets hoặc trust bindings và đo lại effective access.

## 16. RBAC, ABAC, ACL và quyền có hiệu lực: bài toán phân giải

Hệ thống thường kết hợp nhiều cơ chế:

- **RBAC:** user được cấp role qua group hoặc trực tiếp.
- **ABAC:** quyền phụ thuộc tenant, department, data classification, context và trạng thái resource.
- **ACL/ReBAC:** quyền từ quan hệ owner, team, project hoặc share trực tiếp.
- **Cloud IAM conditions:** quyền có thể phụ thuộc resource tags, action, thời gian, network hoặc permission boundaries.
- **SaaS app-local roles:** ứng dụng lưu quyền riêng mà IdP không nhìn thấy.

### Vì sao không thể lấy union của tất cả grants?

Giả sử một user có role FinanceReader và quyền invoice.read trong token. Nếu invoice thuộc tenant khác, ABAC tenant check phải **DENY**. Một effective permission tương ứng với **decision sau toàn bộ kiểm soát** chứ không phải danh sách các yếu tố PERMIT rời rạc.

Một pipeline đo:

~~~text
Assigned grants from role/group/ACL/cloud policy
    |
    +-- identity and tenant mapping
    +-- group nesting / inheritance
    +-- allow/deny policy precedence
    +-- ABAC conditions and resource properties
    +-- principal status, effectiveAt, expiry
    +-- session/token trust and freshness
    +-- application-local enforcement
    v
Effective access (by action/resource/context)
    |
    +-- test representative and high-risk boundaries at PEP
    v
Verified effective-access evidence
~~~

### Quyền động khó liệt kê toàn bộ

Một ABAC policy có thể mở quyền cho “mọi bản ghi thuộc tenant và có status APPROVED”; số tài nguyên có thể thay đổi từng phút. Thay vì liệt kê vô hạn, tổ chức có thể:

1. Chuẩn hóa **permission scope** bằng biểu thức có ngữ nghĩa rõ.
2. Chọn **representative policy decision cases** với positive và negative tests.
3. Đo **policy drift và attribute freshness** bên cạnh permission edges.
4. Kiểm thủ tục **object-level authorization** tại PEP.
5. Đánh dấu phần chưa được phủ bằng phép thử thay vì khẳng định 100% coverage.

Đối với permission wildcard hoặc quyền quản trị, cần đánh giá **phạm vi thực tế** và tác động, không để một wildcard được đếm như một quyền nhỏ.

## 17. Lược đồ dữ liệu đo lường: desired, effective, observed

Để tính KPIs tái lập được, cần lưu các snapshot theo thời gian và định danh ổn định. Ví dụ mô hình dữ liệu **khái niệm**:

~~~yaml
measurementId: leastpriv-snapshot-20261123-vn
measuredAt: "2026-11-23T04:00:00Z"
scope:
  applications: [finance-api, crm, secret-vault]
  principalTypes: [HUMAN, WORKLOAD]
  tenants: [tenant-vn]
  excludedTargets:
    - target: legacy-reporting
      reason: NO_EFFECTIVE_ACCESS_READBACK
      owner: legacy-platform
method:
  permissionUnit: SUBJECT_ACTION_RESOURCE_SCOPE
  policyVersion: leastpriv-review-v4
  usageObservationDays: 90
  riskWeights:
    LOW: 1
    MEDIUM: 3
    HIGH: 10
    CRITICAL: 30
  unknownApprovalHandling: SEPARATE_BUCKET
results:
  verifiedEffectiveEdges: 12
  approvedRequiredEdges: 8
  confirmedExcessEdges: 3
  pendingOwnerReviewEdges: 2
  missingRequiredEdges: 1
  verificationCoverage: PARTIAL
~~~

Đây là **YAML minh họa**, không phải schema chuẩn cho các sản phẩm IAM. Những số liệu cần được hiểu theo đúng định nghĩa; ví dụ 12 effective, 10 required và 1 missing **không tự cho biết** có bao nhiêu quyền được chấp nhận nếu chưa thấy các tập/khóa trùng nhau.

### Đề xuất các trường bản ghi permission

| Trường | Ý nghĩa |
| --- | --- |
| measurementId / observedAt | Mốc snapshot, phục vụ trend và đối soát. |
| principalId / principalType | Stable ID của human hoặc workload. |
| targetId / tenantId | Ứng dụng, môi trường, tenant. |
| action / resourceScope | Đơn vị permission đã chuẩn hóa. |
| grantSource / grantRef | Role, group, ACL, JIT, token, local account... |
| isEffective / decisionContext | Trạng thái quyền và điều kiện đã xét. |
| approvedNeedRef / approvalExpiry | Liên kết nhu cầu được phê duyệt. |
| riskTier / resourceSensitivity | Mức tác động để ưu tiên xử lý. |
| lastObservedUseAt / telemetryCoverage | Usage được ghi nhận và chất lượng log. |
| effectiveAt / expiresAt | Thời hạn quyền, bao gồm quyền JIT. |
| verificationStatus / verifiedAt | Bằng chứng quyết định tại target PEP. |
| dataSourceRevision | Phiên bản dữ liệu HRIS/IGA/PIP được sử dụng. |
| owner / remediationRef | Ai giải trình và xử lý sai lệch. |

**Không lưu bearer token hoặc mật khẩu thật** cùng tập dữ liệu đo quyền. Dùng ID, hashed reference được bảo vệ và metadata tối thiểu khi cần tương quan.

## 18. Ví dụ SQL: tìm entitlement dư thừa từ snapshot đã chuẩn hóa

Giả sử có hai bảng snapshot minh họa:

- **effective_permission_snapshot** chứa những permission edges đã xác minh có hiệu lực tại một mốc.
- **approved_permission_snapshot** chứa những permission edges cần thiết và còn phê duyệt tại cùng mốc.

Trước khi chạy truy vấn cần chuẩn hóa scope và identity mapping; **phép so sánh bằng chuỗi không xử lý được wildcard, role inheritance hoặc điều kiện ABAC phức tạp**.

~~~sql
-- SQL minh họa theo một schema tự thiết kế; không phải câu lệnh
-- chạy trực tiếp trên Azure AD, LDAP hay một sản phẩm IAM.
SELECT
    e.measurement_id,
    e.principal_id,
    e.target_id,
    e.tenant_id,
    e.action,
    e.resource_scope,
    e.risk_tier
FROM effective_permission_snapshot e
WHERE e.measurement_id = :measurement_id
  AND e.verification_status = 'VERIFIED'
  AND NOT EXISTS (
      SELECT 1
      FROM approved_permission_snapshot n
      WHERE n.measurement_id = e.measurement_id
        AND n.principal_id = e.principal_id
        AND n.target_id = e.target_id
        AND n.tenant_id = e.tenant_id
        AND n.action = e.action
        AND n.resource_scope = e.resource_scope
        AND n.approval_status = 'APPROVED'
  );
~~~

**Diễn giải đúng phạm vi:** kết quả là **các edge có hiệu lực và đã được xác minh không có bản ghi approval tương ứng** trong snapshot. Chúng là **ứng viên cần review**, không nhất thiết đều là quyền không cần: có thể approval chưa được nhập, permission scope chưa chuẩn hóa đúng hoặc ngoại lệ hợp lệ chưa được đồng bộ.

### Ngăn kết luận sai do thiếu dữ liệu

Một SQL anti-join không thể tự phát hiện rằng collector không có dữ liệu cho ứng dụng X. Cần bổ sung bảng **measurement_coverage** theo target/PEP/telemetry để dashboard loại target chưa đủ coverage khỏi mẫu số KPI đã xác nhận và **hiển thị riêng số lượng chưa kiểm**.

Trước khi tự động revoke:

1. Xác minh stable principal/resource mapping.
2. Xác nhận quyền có thực sự effective tại target.
3. Lấy quyết định từ business owner/IGA hoặc quy tắc đã duyệt.
4. Kiểm không có nhu cầu đặc biệt theo kỳ, DR hay pháp lý.
5. Gỡ quyền theo workflow phù hợp, giữ bằng chứng và verify DENY.

### Quyền được duyệt nhưng chưa được cấp

Phép đối chiếu ngược từ N sang E cho thấy **missing permissions**, giúp theo dõi tác động vận hành của chương trình least privilege. Không dùng chiến lược chỉ gỡ quyền mà bỏ qua quyền hợp lệ chưa được đáp ứng.

## 19. Java pseudocode: tính excess, missing và unknown

Mã sau mô tả phép đo **sau khi đã canonicalize permission** và tách trường hợp chưa rõ approval. Nó không triển khai authorization engine hoặc kết nối trực tiếp IdP.

~~~java
import java.util.HashSet;
import java.util.Set;

record PermissionKey(
    String principalId,
    String targetId,
    String tenantId,
    String action,
    String resourceScope
) {}

record LeastPrivilegeMetrics(
    int effectiveCount,
    int requiredCount,
    int confirmedExcessCount,
    int missingRequiredCount,
    int unknownApprovalCount,
    double excessRate,
    double requiredCoverage
) {}

final class LeastPrivilegeMeasurement {
    LeastPrivilegeMetrics measure(
            Set<PermissionKey> verifiedEffective,
            Set<PermissionKey> approvedRequired,
            Set<PermissionKey> unknownApproval) {

        // Snapshot và scope được kiểm chứng trước khi gọi hàm này.
        Set<PermissionKey> effective = new HashSet<>(verifiedEffective);
        Set<PermissionKey> required = new HashSet<>(approvedRequired);
        Set<PermissionKey> unknown = new HashSet<>(unknownApproval);

        // Chỉ các effective edges được đánh dấu UNKNOWN mới vào bucket này.
        unknown.retainAll(effective);

        Set<PermissionKey> unmatched = new HashSet<>(effective);
        unmatched.removeAll(required);

        Set<PermissionKey> confirmedExcess = new HashSet<>(unmatched);
        confirmedExcess.removeAll(unknown);

        Set<PermissionKey> missing = new HashSet<>(required);
        missing.removeAll(effective);

        int approvedAndEffective = required.size() - missing.size();
        double excessRate = effective.isEmpty()
                ? Double.NaN
                : 100.0 * confirmedExcess.size() / effective.size();
        double coverage = required.isEmpty()
                ? Double.NaN
                : 100.0 * approvedAndEffective / required.size();

        return new LeastPrivilegeMetrics(
            effective.size(),
            required.size(),
            confirmedExcess.size(),
            missing.size(),
            unknown.size(),
            excessRate,
            coverage
        );
    }
}
~~~

**Quan trọng:** logic trên chỉ phù hợp khi các permissions đã được biểu diễn chính xác thành các **đơn vị so sánh tương đương**. Nếu một quyền wildcard bao gồm nhiều quyền hẹp hoặc conditions phụ thuộc thời gian, một tập String/PermissionKey đơn giản **không thay thế** policy evaluator và phép thử thực tế. Trạng thái **unknown** cần được đưa vào đúng tập trước khi tính; không tự coi mọi quyền không khớp approval là “confirmed excess” khi còn thiếu dữ liệu.

### Ví dụ test oracle cho hàm tính

~~~text
E = {read-A, read-B, export-A, admin-C}
N = {read-A, read-B, approve-D}
UNKNOWN = {admin-C}

Expected:
  effectiveCount       = 4
  requiredCount        = 3
  confirmedExcessCount = 1  (export-A)
  unknownApprovalCount = 1  (admin-C)
  missingRequiredCount = 1  (approve-D)
  excessRate           = 25.0%
  requiredCoverage     = 66.67% (2/3)
~~~

Không gọi **export-A chắc chắn nguy hiểm hơn admin-C** chỉ vì một case đã xác minh excess, một case còn unknown. **Admin-C unknown** có thể là ưu tiên khẩn cần reviewer giải trình.

## 20. Kiểm thử phép đo: positive, negative và fault cases

Một hệ thống đo least privilege cũng là một hệ thống phần mềm cần test; nếu collector hoặc normalizer sai, KPI có thể đẹp lên trong lúc quyền thực tế xấu đi.

| ID | Tình huống | Kỳ vọng |
| --- | --- | --- |
| M01 | Quyền được duyệt và API thật ALLOW đúng scope. | N ∩ E được ghi đúng, không flag excess. |
| M02 | Quyền có hiệu lực nhưng business owner xác nhận không còn cần. | Ghi confirmed excess và remediation. |
| M03 | Quyền không có approval record, owner chưa trả lời. | Ghi UNKNOWN, không tự coi đã xác nhận dư thừa. |
| M04 | Quyền cần có nhưng PEP trả DENY. | Ghi missing, tìm false deny/provisioning defect. |
| M05 | Một quyền qua hai nested groups. | Không đếm đôi effective capability; vẫn lưu hai grant sources. |
| M06 | Wildcard admin và read-only hẹp. | Không coi mức rủi ro ngang nhau theo một điểm số thô. |
| M07 | ABAC deny tenant khác dù role cho phép read. | Effective access phản ánh DENY trên tenant khác. |
| M08 | Resource classification bị thiếu. | Không tự coi PUBLIC và báo quyền hợp lệ. |
| M09 | API chỉ có log từ một region. | Coverage chưa đủ; không coi region khác không có quyền. |
| M10 | Log usage vắng mặt 90 ngày nhưng job theo lịch năm. | Dormant không tự thành excess; cần review nghiệp vụ. |
| M11 | Role đã bị gỡ ở IdP nhưng local ACL còn. | E vẫn phản ánh đường quyền cục bộ, cảnh báo drift. |
| M12 | SCIM trả success nhưng target role chưa thay. | Chưa VERIFIED; kiểm lại và cảnh báo. |
| M13 | Token JWT trước Mover vẫn cho API ALLOW. | Bị tính residual access trong SLA tương ứng. |
| M14 | Leaver bị disable tại IdP, session SaaS vẫn active. | Residual access không bằng 0. |
| M15 | Token của CRM được trình vào Finance API. | Verifier từ chối sai audience; không biến thành quyền hiệu lực hợp lệ. |
| M16 | User thuộc tenant A thử resource tenant B. | DENY đúng ABAC/resource-level. |
| M17 | Service principal staging có quyền production. | Flag cross-environment privilege. |
| M18 | Owner workload đã Leaver, secret chưa rotate. | Ghi owner/control gap và đánh giá exposure. |
| M19 | Eligible admin role chưa kích hoạt. | Không đếm là standing privilege-hours; đo riêng eligibility. |
| M20 | JIT role hết hạn nhưng cache còn cho phép. | Ghi privilege-hours quá hạn/residual, FAIL TTL enforcement. |
| M21 | PDP timeout khiến API trả 503. | Không tính là verified DENY; phân loại outage. |
| M22 | Policy trả DENY nhưng async export vẫn tạo file. | Đo thấy bypass/side effect, không báo least privilege đạt. |
| M23 | Hai snapshots khác thời điểm bị join. | Chặn hoặc chú thích không tương đương, không tính drift giả. |
| M24 | HRIS Leaver event cũ đến sau rehire hợp lệ. | Revision/current state ngăn thao tác sai. |
| M25 | Số effective quyền bằng 0. | Excess rate = N/A, không chia 0. |
| M26 | Số quyền cần thiết bằng 0. | Required coverage = N/A, không chia 0. |
| M27 | Một target không cho readback quyền. | Hiển thị coverage gap; không mặc định đủ hay không có excess. |
| M28 | Permission export dùng nhiều nhưng chưa phê duyệt. | Vẫn flag cần review; usage không biến quyền thành hợp lệ. |
| M29 | Quyền break-glass chưa dùng cả năm nhưng có runbook/owner. | Đo exposure/eligibility và kiểm JIT, không auto-delete. |
| M30 | SoD self-approval bị chặn dù role Approver tồn tại. | Effective permission theo ngữ cảnh, không chỉ role. |

**Không kiểm thử bằng token thật hoặc tài nguyên khách hàng ngoài phạm vi được ủy quyền.** Có thể dùng policy simulator, test tenant, synthetic objects và endpoint probe không phá hoại với kết quả được audit.

## 21. Đo chất lượng phép đo: coverage, confidence và độ lệch

Một con số “excess privilege 5%” có thể gây hiểu nhầm nếu chỉ bao phủ 20% ứng dụng. Do đó mọi KPI cần đi kèm **khả năng quan sát**.

### Measurement coverage

\[
\text{Verified Target Coverage} =
\frac{\text{Targets bắt buộc đã xác minh}}
{\text{Tổng targets bắt buộc trong scope}} \times 100\%
\]

Ví dụ 9/10 target có quyền/evidence hợp lệ thì **target coverage = 90%**. Nhưng một target chưa quan sát có thể là cloud production admin với rủi ro cực lớn; vì vậy **coverage theo đếm target** không được thay thế **risk-based coverage**.

### Ba lớp tin cậy

| Lớp | Câu hỏi | Nếu thiếu |
| --- | --- | --- |
| **Source confidence** | Approval, HRIS, policy và mapping có đúng nguồn không? | Không thể khẳng định N chính xác. |
| **Effective-access confidence** | Quyền đã được resolve và kiểm tại PEP đúng không? | Không thể khẳng định E đầy đủ. |
| **Usage confidence** | Telemetry có đủ nguồn, phạm vi, độ dài quan sát không? | Không thể kết luận một quyền dormant. |

Mỗi KPI nên hiển thị **snapshot timestamp, cửa sổ đo, coverage, dữ liệu unknown và excluded targets**. Khi thiếu dữ liệu, ghi một **confidence note** do quy trình định nghĩa, không tùy tiện đặt “99% confidence” nếu không có mô hình thống kê.

### Tránh bẫy denominator

Nếu một quý hệ thống đo 10 ứng dụng và quý sau đo 30 ứng dụng, tỷ lệ dư thừa có thể tăng do **mở rộng coverage** thay vì quyền thực sự xấu đi. Dashboard nên cung cấp:

- Trend trên **fixed cohort** các target được đo cả hai kỳ.
- Trend theo phạm vi đo hiện hành, kèm ghi chú tăng coverage.
- Số tuyệt đối **critical unapproved grants** và residual Leaver.
- Tỷ lệ target/permission edges còn unknown.

Không xóa các target rủi ro cao khỏi mẫu số chỉ để KPI đẹp hơn.

## 22. Tình huống thực hành: đo least privilege sau khi chuyển vai trò

### Bối cảnh

Một doanh nghiệp dùng HRIS để quản lý nhân viên, IGA để phê duyệt entitlement, IdP/SSO để xác thực, SCIM để cập nhật SaaS, và Finance API để thực thi RBAC/ABAC. Nhân viên **Linh** từ Sales chuyển sang Finance vào lúc **09:00 ngày 23/11**. Các quyền cũ cần thu hồi:

- Đọc khách hàng của dự án Sales.
- Export dữ liệu CRM.
- Đọc một thư mục chia sẻ Sales.
- Đọc secret của service account sales-sync.

Quyền Finance mới hợp lệ:

- Xem hóa đơn APPROVED trong tenant VN.
- Xem báo cáo chi phí không có thông tin nhạy cảm ngoài phạm vi.
- **Không** có quyền payment.approve hoặc tenant-wide admin.

### Bước 1 — Xác định đơn vị quyền và oracle

Business owner phê duyệt permission matrix tại 09:00:

| ID | Permission unit | N sau Mover | Lý do |
| --- | --- | --- | --- |
| P1 | CRM.customer.read, Sales tenant VN | NO | Đã rời Sales. |
| P2 | CRM.customer.export, Sales tenant VN | NO | Không còn nhu cầu xuất dữ liệu. |
| P3 | Sales.folder.read, project A | NO | Không có bàn giao được phê duyệt. |
| P4 | Vault.secret.read, sales-sync | NO | Không còn owner/quyền vận hành. |
| P5 | Finance.invoice.read, tenant VN, approved | YES | Nhiệm vụ mới. |
| P6 | Finance.report.read, tenant VN | YES | Nhiệm vụ mới. |
| P7 | Finance.payment.approve | NO | Thiếu role/phân tách nhiệm vụ. |
| P8 | Finance.globalAdmin | NO | Không có nhu cầu quản trị. |

### Bước 2 — Thu quyền thực tế sau khi đồng bộ

Lúc 09:10, collectors/readback và kiểm chứng PEP ghi nhận:

| Quyền | Actual E lúc 09:10 | Tình trạng |
| --- | --- | --- |
| P1: Sales customer read | **ALLOW** | CRM cache chưa invalidated. |
| P2: Sales export | **ALLOW** | SaaS local role còn tồn tại. |
| P3: Sales shared folder | **ALLOW** | Direct ACL chưa gỡ. |
| P4: Sales secret | DENY | Vault đã thu hồi. |
| P5: Finance invoice read | **ALLOW** | Cấp đúng qua policy Finance. |
| P6: Finance report read | **ALLOW** | Cấp đúng qua policy Finance. |
| P7: Payment approve | DENY | SoD/role policy chặn. |
| P8: Global admin | DENY | Không có grant. |

Với đơn vị quyền P1–P8 và **chỉ xét các quyền ALLOW được xác minh**:

- E = {P1, P2, P3, P5, P6}: **5** quyền hiệu lực.
- N = {P5, P6}: **2** quyền được duyệt.
- E \ N = {P1, P2, P3}: **3** quyền dư thừa.
- N \ E = ∅: **0** quyền thiếu.

Khi đó:

\[
\text{Excess Privilege Rate} = \frac{3}{5}\times100\%=60\%
\]

\[
\text{Required Access Coverage} = \frac{2}{2}\times100\%=100\%
\]

**Ý nghĩa:** Linh có đủ hai quyền Finance cần thiết, nhưng **60% permission units có hiệu lực trong scope của ví dụ không còn được duyệt**. Không nên chỉ báo “đã hoàn thành Mover vì Finance hoạt động”.

### Bước 3 — Đo độ trễ thu hồi

Giả sử tại **09:12**, CRM đọc khách hàng đã DENY; tại **09:18**, export bị chặn; đến **09:25**, thư mục Sales mới từ chối sau khi xử lý ACL và cache.

Với ba đường P1–P3 bắt buộc bị thu hồi:

\[
\text{Revocation Latency} = 09{:}25 - 09{:}00 = 25\text{ phút}
\]

Nếu SLA của quyền Sales nhạy cảm là 15 phút, trường hợp này **FAIL SLA**. Không được lấy mốc 09:05 (SCIM accepted) để tuyên bố 5 phút.

### Bước 4 — Kiểm quyền sau remediation

Tại 09:26, chạy lại cả:

- Positive probes: P5 và P6 **ALLOW** đúng tenant, đúng loại tài nguyên.
- Negative probes: P1–P4, P7–P8 **DENY** đúng lý do.
- Test với token cũ được phát trước Mover nếu chính sách và môi trường cho phép.
- Direct ACL, local SaaS, session và service secret access đều được đọc lại.

Nếu E = N = {P5, P6}, phép đo trong **scope đã kiểm chứng** có thể cho **Excess = 0** và **Required Coverage = 100%**. Không tự suy từ đó rằng mọi quyền của Linh trên toàn doanh nghiệp đều tối thiểu, bởi vẫn có thể có app khác chưa thuộc scope.

### Bước 5 — Tránh “đẹp số” nhờ cắt mất quyền hợp lệ

Nếu do lỗi policy, P5 bị chặn sau khi gỡ Sales:

- E = {P6}; N = {P5, P6}.
- Excess = 0/1 = 0%.
- Required Coverage = 1/2 = 50%.

Chỉ số dư thừa tốt hơn nhưng người dùng **không làm được công việc cần thiết**. Dashboard phải hiển thị **cả hai chiều**.

### Bước 6 — Leaver và service identity

Một tháng sau Linh nghỉ việc. Bên cạnh role Finance, cần kiểm:

- SSO session, OAuth grants/refresh token và access token còn hạn tại Finance API.
- App-local account, direct shares, personal API key.
- Quyền quản lý service principal hoặc vault secret từng được cấp.
- Owner của workload được bàn giao, không ngừng dịch vụ hợp lệ một cách máy móc.
- Readback/verified DENY tại từng target theo SLA Leaver.

**Kết luận tình huống:** số liệu least privilege có ích nhất khi có **oracle nghiệp vụ, phép đo effective access, dữ liệu được kiểm chứng theo thời gian và remediation proof**.

## 23. Ưu tiên khắc phục dựa trên số liệu

Không phải tất cả quyền dư thừa đều có cùng mức khẩn cấp. Có thể lập hàng đợi xử lý theo:

1. **Impact:** quyền có thể xuất dữ liệu, chi tiền, xóa hệ thống hoặc quản trị IAM không.
2. **Reach:** bao nhiêu tenant, tài nguyên và môi trường.
3. **Exploitability:** credential/token có thể bị lộ, dùng từ Internet, thiếu MFA/sender binding hoặc trust yếu không.
4. **Lifecycle urgency:** Leaver/suspended, Mover SoD conflict hay ngoại lệ quá hạn.
5. **Observed misuse/risk signals:** các hoạt động bất thường, không coi usage làm hợp thức hóa.
6. **Evidence confidence:** quyền đã verified ALLOW hay mới chỉ suy đoán từ role.
7. **Remediation feasibility:** có thể revoke ngay, cần change window hay cần phương án bù trừ.

### Quy trình xử lý một finding

~~~mermaid
flowchart TD
    F["Finding: confirmed / suspected excess"] --> R["Risk tier + evidence review"]
    R --> A{"Có grant trái policy đang nguy cấp?"}
    A -->|Có| C["Áp biện pháp chặn/thu hồi khẩn được duyệt"]
    A -->|Không| O["Business owner attestation"]
    C --> O
    O --> D{"Cần quyền này không?"}
    D -->|Có, được duyệt| K["Ghi approval / scope / expiry / controls"]
    D -->|Không| X["Thu hồi tại nguồn và target"]
    D -->|Chưa rõ| Q["Quarantine/monitor theo risk; INVESTIGATE"]
    X --> V["Readback + PEP test + kiểm no side effects"]
    V --> Z{"Đạt không?"}
    Z -->|Có| E["VERIFIED + audit"]
    Z -->|Không| M["Escalation / remediation lại"]
    M --> V
    K --> E
~~~

**Không tự động xóa quyền nhạy cảm chỉ vì permission count cao.** Cần kết hợp rule đã được phê duyệt, nhu cầu đặc biệt và đảm bảo không làm mất khả năng khôi phục/hỗ trợ vận hành. Với **Leaver** hoặc grant vi phạm chính sách nghiêm trọng, biện pháp chặn khẩn nên được ưu tiên theo kế hoạch ứng cứu.

### Sau remediation đo những gì?

- **Confirmed excess đã được loại khỏi E** hay chỉ đã gửi request revoke.
- **Required access vẫn đầy đủ** hay tạo false deny.
- **SoD conflict** có thực sự biến mất.
- **Privilege-hours tương lai** giảm theo policy JIT/TTL.
- **Regrant/rollback drift** có xảy ra khi event cũ hoặc config cũ được áp lại.
- **Owner/approval** đã được cập nhật để finding không xuất hiện lặp do thiếu hồ sơ.

## 24. Dashboard đo least privilege: hiển thị để ra quyết định

Một dashboard hữu ích cho IAM governance không chỉ có một con số “Privilege Score”.

| Thành phần báo cáo | Thông tin hiển thị | Quyết định hỗ trợ |
| --- | --- | --- |
| **Phạm vi đo** | Ứng dụng, tenants, principal types, snapshot, fixed cohort. | Số liệu có đại diện không? |
| **Verified coverage** | Số target/PEP đã kiểm và các target UNVERIFIED. | Cần mở rộng observability ở đâu? |
| **Excess privilege** | Số và tỷ lệ quyền dư thừa được xác nhận theo risk tier. | Nên gỡ quyền nào trước? |
| **Unknown approval** | Quyền cần owner xác nhận, số ngày chờ. | Ai phải chứng nhận nhu cầu nghiệp vụ? |
| **Missing required** | Quyền hợp lệ chưa dùng được, false-deny incidents. | Cần khôi phục quyền đúng nào? |
| **High-risk standing** | Global admin, wildcard, sensitive export, cross-tenant. | Chuyển sang JIT/PAM hoặc scope hẹp ở đâu? |
| **Dormant / seasonal** | Không thấy dùng, nhưng gắn độ đầy đủ telemetry và kỳ nghiệp vụ. | Cần review, không auto-revoke nhầm. |
| **JML residual** | Target còn ALLOW sau Mover/Leaver, SLA breach. | Cần khắc phục thu hồi chậm ở đâu? |
| **Workload posture** | Owner, secret age, unused principals, cross-env trust. | Cần rotate, decommission hoặc tách quyền nào? |
| **Exceptions/SoD** | Grant ngoại lệ, hạn hết, xung đột, approver. | Có quyền tồn tại quá thời gian/phạm vi không? |

### Cách đọc trend

Một dashboard đẹp cần giải thích các biến động:

- EPR giảm vì đã **thu hồi thực tế** hay vì collector mất kết nối một ứng dụng?
- Standing admin giảm nhưng **eligible admin** tăng hay không?
- Dormant count giảm do người dùng sử dụng quyền **nhiều hơn** hay do quyền đã được loại bỏ?
- Revocation latency giảm nhưng hệ thống **bỏ target khó kiểm** khỏi scope hay không?
- Quyền read-only tăng do ứng dụng mới được onboard, nhưng mức **wildcard admin** có giảm không?

**Mỗi phép đo nên có drill-down tới evidence và owner**, tránh bảng xếp hạng gây áp lực khiến đội ngũ né ghi nhận rủi ro.

## 25. Sai lầm thường gặp khi đo quyền tối thiểu

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Đếm số role thay cho khả năng truy cập. | Một role wildcard trông “ít” dù rất nguy hiểm. | Chuẩn hóa action/resource scope, risk tier và effective decisions. |
| Cho rằng quyền không dùng 90 ngày là quyền thừa. | Gỡ mất năng lực DR/đóng kỳ, gây gián đoạn. | Review theo nhiệm vụ và telemetry coverage. |
| Cho rằng quyền có usage là hợp lệ. | Hợp thức hóa hành động vượt quyền đã xảy ra. | Đối chiếu N và approval độc lập. |
| Chỉ đọc IdP group. | Không thấy app-local role, direct ACL, token cũ. | Thu thập/readback tại PEP/target. |
| Chỉ tính assigned G, bỏ qua E. | Không hiểu rule DENY/ABAC hoặc quyền khác đường. | Đo effective access và verification probes. |
| Gộp unknown vào số 0. | KPI đẹp giả và bỏ sót hệ thống rủi ro. | Bucket UNKNOWN và coverage gap riêng. |
| Tính percent khi mẫu số bằng 0. | Số liệu sai, lỗi hệ thống. | Trả N/A theo quy tắc được công bố. |
| Dùng một trọng số rủi ro mà không giải thích. | Mọi người hiểu “score” như xác suất khách quan. | Công bố phương pháp, hiệu chuẩn, risk tiers và uncertainty. |
| Lấy SCIM 200/204 là verified revoke. | Ứng dụng vẫn có local session/ACL. | Verify DENY cuối đường và token/session. |
| Chỉ đo thời gian từ event đến connector. | Che giấu stale cache và export worker còn ALLOW. | Đo tới PEP cuối cùng trong scope. |
| Không tách standing với eligible JIT. | Đánh giá sai thời gian quyền cao có hiệu lực. | Báo riêng privilege-hours, activation và eligibility. |
| Gộp service principal với user role. | Bỏ sót cross-env trust/secret và quyền máy. | Workload-specific entitlement model. |
| Quên direct delegation và SoD. | Người rời role vẫn có effective access trái policy. | Review mọi nguồn grants và điều kiện workflow. |
| So KPI hai kỳ khác coverage mà không ghi. | Kết luận tình trạng xấu đi/tốt lên sai. | Fixed cohort, coverage metadata và trend được chú thích. |
| Chỉ đo quyền dư thừa, không đo quyền thiếu. | Ngắt công việc hợp lệ, khuyến khích tài khoản chung. | Đo Required Access Coverage và false-deny rate. |
| Ghi token hoặc PII để chứng minh quyền. | Tạo kho dữ liệu/credential nhạy cảm. | Log reference an toàn, data minimization và retention. |
| Chỉ tính KPI nhưng không có owner remediation. | Quyền thừa tồn tại mãi dù đã phát hiện. | Finding workflow, SLA, readback và audit sign-off. |

## 26. Checklist triển khai chương trình đo least privilege

1. **Define scope:** ứng dụng, tenants, principal types, tài nguyên nhạy cảm, PEP và kỳ đo.
2. **Define unit:** permission edge, policy decision case, risk-weighted capability hoặc privilege-hours; không trộn mẫu số.
3. **Establish N:** nhu cầu được duyệt từ HRIS, IGA, business/data owner và policy, có thời điểm hiệu lực.
4. **Collect G/E:** group, role, nested role, ACL, ABAC, SaaS local, JIT, token và workload identities.
5. **Verify E:** kiểm tại PEP/resource bằng readback và probes được phép; có positive và negative controls.
6. **Collect U:** usage telemetry với cửa sổ, retention, độ tin cậy và missing-log treatment.
7. **Normalize permissions:** stable subject ID, tenant, resource/action taxonomy, precedence và temporal context.
8. **Separate buckets:** needed, confirmed excess, missing, unknown và exception-approved.
9. **Calculate KPIs:** EPR, required coverage, high-risk excess, dormant, standing-hours, JIT, SoD và orphaned.
10. **Track coverage:** target/PEP coverage, confidence và exclusions; không coi unknown là zero.
11. **JML events:** đo trước/sau Joiner–Mover–Leaver, xác minh revoked access, SLA và regrant anomalies.
12. **Handle workload:** owner, secret/trust, scopes, cross-env và decommissioned identities.
13. **Prioritize risk:** dữ liệu/tiền/secret/control-plane, rộng quyền, blast radius và thời gian tồn tại.
14. **Obtain owner decisions:** KEEP, REVOKE, CHANGE, INVESTIGATE hoặc ngoại lệ có hạn.
15. **Remediate safely:** không gỡ nhầm quyền hiếm dùng nhưng hợp lệ; có rollback và kiểm soát SoD.
16. **Verify effects:** đo lại E, no unauthorized side effects, không false-deny quyền N.
17. **Audit:** policy/source revision, timestamp, owner, evidence, exceptions, không lưu credential.
18. **Improve continuously:** xem xu hướng fixed cohort, điểm đo chưa phủ và tự động hóa có guardrails.

**Đừng đánh dấu chương trình đạt “Least Privilege Verified” khi còn target bắt buộc chưa kiểm, có quyền critical dư thừa hoặc không thể chứng minh quyền Leaver đã bị chặn**. Trạng thái báo cáo nên phản ánh chính xác **VERIFIED, PARTIAL, UNVERIFIED hoặc REMEDIATION_REQUIRED** theo tiêu chí đã duyệt.

## 27. Câu hỏi tự kiểm tra

**Câu 1.** Một tài khoản có 2 role, tài khoản khác có 10 role. Tài khoản nào có least privilege tốt hơn?

**Trả lời:** Không thể kết luận từ số role. Cần so **effective actions/resource scope** với nhu cầu được duyệt, tính quyền nhạy cảm, wildcard, duration và điều kiện.

**Câu 2.** Vì sao quyền không sử dụng 90 ngày chưa chắc là quyền dư thừa?

**Trả lời:** Có thể là quyền phục hồi thảm họa, thao tác cuối quý hoặc job hằng năm. Log cũng có thể thiếu. Phải xác nhận nhu cầu và chất lượng telemetry trước khi revoke.

**Câu 3.** Excess Privilege Rate đo điều gì, và tại sao cần Required Access Coverage?

**Trả lời:** EPR đo tỷ lệ quyền hiệu lực ngoài nhu cầu được duyệt theo đơn vị đã chuẩn hóa. Required Access Coverage đo quyền cần thiết đang được đáp ứng, ngăn chương trình “giảm quyền” thành chặn công việc hợp lệ.

**Câu 4.** Một global admin permission có đáng lo hơn 20 read-only permissions không?

**Trả lời:** Có thể rất đáng lo vì blast radius và khả năng leo thang quyền, nhưng phải đánh giá context. Đếm thô không phản ánh tác động; cần risk tier, wildcard reach và critical findings riêng.

**Câu 5.** IdP đã gỡ nhóm Sales, SCIM cập nhật thành công. Có thể ghi revocation latency bằng thời gian xử lý SCIM không?

**Trả lời:** Chưa. Phải chứng minh tại API, local ACL, session/token và các PEP bắt buộc rằng quyền Sales không còn được thực thi. Mốc kết thúc là verified DENY theo scope.

**Câu 6.** Standing admin và eligible admin khác nhau như thế nào khi đo?

**Trả lời:** Standing là quyền có hiệu lực liên tục, nên có thể đo privilege-hours. Eligible chỉ là khả năng kích hoạt sau điều kiện; đo riêng eligibility và số lần/ thời lượng JIT activation.

**Câu 7.** Vì sao token JWT cũ có thể làm một phép đo quyền tại IdP bị sai?

**Trả lời:** JWT đã phát có thể còn claim/role cũ và RS có thể tiếp tục cho phép đến khi token hết hạn nếu không kiểm trạng thái mới. Cần đối chiếu quyết định tại RS theo SLA.

**Câu 8.** Một quyền xuất dữ liệu được sử dụng nhiều có tự chứng minh cần thiết không?

**Trả lời:** Không. Usage chỉ chứng minh hành động được quan sát, không thay thế phê duyệt và nhu cầu hiện hành. Có thể đó là hành động vượt quyền.

**Câu 9.** Vì sao phải đo least privilege của service principal khác với nhân viên?

**Trả lời:** Workload có identity, scopes, secrets, owner và trust boundaries riêng, thường không có người đăng nhập. Phải kiểm quyền kỹ thuật, cross-environment, wildcard, impersonation và vòng đời workload.

**Câu 10.** Tỷ lệ dư thừa giảm từ 15% xuống 5% có chắc là thành công?

**Trả lời:** Chưa chắc. Coverage có thể giảm, quyền rủi ro cao vẫn còn, hoặc quyền N bị mất. Cần xem fixed-cohort trend, mức rủi ro, coverage, missing required và evidence tại PEP.

**Câu 11.** Vì sao quyền critical chưa rõ owner không nên bị ghi bằng 0 trong báo cáo?

**Trả lời:** Không có owner/approval không làm quyền biến mất. Phải hiển thị UNKNOWN/UNAPPROVED, ưu tiên điều tra và có kiểm soát rủi ro trong khi chưa rõ.

**Câu 12.** Khi nào có thể đóng finding “đã thu hồi quyền”?

**Trả lời:** Sau khi đã sửa nguồn/cấu hình thích hợp và có **readback hoặc effective-access probe** chứng minh action không còn được phép tại target bắt buộc, đồng thời không gây mất quyền hợp lệ ngoài ý muốn.

---

**Ghi nhớ:** **Đo least privilege không phải đếm số role hoặc số lần dùng quyền.** Cần phân biệt **quyền cần thiết đã duyệt (N), quyền gán (G), quyền có hiệu lực (E), quyền quan sát sử dụng (U)** và quyền đã kiểm chứng. Các chỉ số hữu ích gồm **excess/missing permissions, rủi ro đặc quyền cao, dormant exposure, standing privilege-hours, SoD, workload scope và revocation latency**, luôn kèm phạm vi, thời điểm và độ tin cậy của dữ liệu. Trong vòng đời **Joiner–Mover–Leaver**, thước đo cuối cùng là **quyền hợp lệ vẫn hoạt động và quyền không còn hợp lệ thực sự bị từ chối tại tài nguyên**, có bằng chứng kiểm toán để ngăn **quyền truy cập tồn dư**.
