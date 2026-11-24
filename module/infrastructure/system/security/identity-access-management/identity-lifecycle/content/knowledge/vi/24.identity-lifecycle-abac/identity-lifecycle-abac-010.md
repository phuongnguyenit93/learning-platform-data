# Rà soát ABAC trong quản lý vòng đời danh tính IAM

**Rà soát ABAC (Attribute-Based Access Control review)** là hoạt động đánh giá có hệ thống xem chính sách truy cập dựa trên thuộc tính có còn **đúng mục đích nghiệp vụ, đúng nguồn dữ liệu, đúng phạm vi tài nguyên và được thực thi đúng ở thời điểm hiện tại** hay không. Khác với việc duyệt một danh sách role tĩnh, rà soát ABAC phải xem xét tổ hợp **chủ thể – hành động – tài nguyên – môi trường**, cách các thuộc tính thay đổi, những chính sách được áp dụng và **quyền truy cập thực tế** tại ứng dụng.

Bài thuộc chương **ABAC** của module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**. Module tập trung quản lý vòng đời danh tính theo mô hình **Joiner–Mover–Leaver (JML)**, từ xác minh danh tính, tạo tài khoản, cấp quyền, rà soát, thay đổi vai trò tới thu hồi quyền. Rà soát ABAC liên kết với **HRIS/IGA, IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** và mục tiêu ngăn **quyền truy cập tồn dư**.

**Tình huống dẫn nhập:** Nhân viên Hòa chuyển từ bộ phận Sales sang Finance. Hệ thống nhân sự đã cập nhật department=Finance; IdP và SCIM cũng đã bỏ nhóm Sales. Tuy nhiên, ứng dụng CRM còn một thuộc tính department=Sales trong cache, một tài liệu có ACL cấp trực tiếp cho Hòa và một access token còn hạn mang claim cũ. Nếu quản trị viên chỉ xem policy “chỉ nhân viên Sales được đọc dữ liệu Sales” rồi kết luận đạt, quyền cũ có thể tiếp tục hoạt động. Một đợt **rà soát ABAC đúng nghĩa** phải tìm ra các đường truy cập đó và chứng minh kết quả sau khi sửa.

## 1. ABAC là gì và rà soát điều gì?

**ABAC** đưa ra quyết định dựa trên các thuộc tính đã được xác minh của:

- **Subject:** người dùng, service account hoặc workload; ví dụ subjectId, trạng thái quan hệ, department, clearance, tenant và nhiệm vụ hiện hành.
- **Action:** read, create, update, delete, approve, export, grantRole, rotateSecret hoặc thao tác nghiệp vụ cụ thể.
- **Resource:** tài nguyên được yêu cầu; ví dụ owner, tenantId, project, classification, trạng thái hóa đơn hoặc nhãn dữ liệu.
- **Environment/context:** thời gian, mức bảo đảm phiên, thiết bị được quản lý, môi trường production, mục đích truy cập hay điều kiện rủi ro.

Về mặt khái niệm:

\[
\operatorname{Decision} = \operatorname{EvaluatePolicy}(S,A,R,E,P)
\]

Trong đó P là phiên bản tập chính sách đang được áp dụng. Một điều kiện ALLOW chỉ đúng nếu **mọi điều kiện bắt buộc** trong chính sách được thỏa mãn và không có quy tắc DENY ưu tiên theo mô hình kết hợp quyết định đã chọn.

### Bốn câu hỏi chính khi rà soát

1. **Policy còn phù hợp không?** Luật có phản ánh nhu cầu nghiệp vụ, mức rủi ro, SoD và yêu cầu pháp lý hiện hành?
2. **Thuộc tính có đáng tin không?** Ai sở hữu, ai cập nhật, có đủ mới, đúng tenant, không bị người dùng tự sửa, không mất giá trị?
3. **Enforcement có đúng không?** PDP đánh giá đúng nhưng mọi PEP/API có gọi và tuân theo quyết định không? Cache, token, ACL khác có bypass không?
4. **Effective access có đúng sau JML không?** Người mới chỉ có quyền đã duyệt, người chuyển vai trò mất quyền cũ, người nghỉ việc không còn đường truy cập hợp lệ?

**Rà soát ABAC không đồng nghĩa viết lại toàn bộ policy** hoặc chỉ kiểm syntax của một tệp cấu hình. Kết quả cần gồm quyết định quản trị, bằng chứng kỹ thuật và hành động khắc phục có owner/thời hạn.

## 2. Rà soát ABAC khác rà soát RBAC và kiểm toán đăng nhập

| Hoạt động | Đối tượng xem xét | Ví dụ câu hỏi | Giới hạn nếu làm riêng lẻ |
| --- | --- | --- | --- |
| **RBAC role review** | Role, membership, entitlement theo vai trò. | Hòa còn thuộc nhóm Sales-Reader không? | Không nhìn hết điều kiện tenant, classification, trạng thái tài nguyên và cache. |
| **ABAC policy review** | Luật, thuộc tính, nguồn dữ liệu, quyết định và nơi thực thi. | Hòa có còn thỏa điều kiện đọc dữ liệu Sales trong mọi API không? | Có thể bỏ sót grant độc lập nếu không kiểm effective access. |
| **Access certification / attestation** | Chủ sở hữu xác nhận quyền hoặc điều kiện được phép. | Data owner có đồng ý cho người thuộc nhóm dự án này đọc dữ liệu không? | Chữ ký xác nhận không chứng minh quyền đã được thu hồi kỹ thuật. |
| **Authentication audit** | Ai đăng nhập, bằng phương thức nào, phiên nào. | IdP đã yêu cầu MFA đúng chưa? | Xác thực mạnh không tự mang lại quyền nghiệp vụ. |
| **Deprovisioning verification** | Kết quả thu hồi tại target, token/session và API. | Sau Leaver, API còn nhận quyền cũ không? | Không thay thế việc đánh giá chất lượng chính sách theo định kỳ. |

Trong hệ thống lai, **RBAC và ABAC bổ sung nhau**. Ví dụ role FINANCE_READER cho phép yêu cầu hành động invoice.read, còn ABAC giới hạn hóa đơn đúng tenant, classification và ngày hiệu lực. Chỉ duyệt role mà không kiểm điều kiện ABAC hoặc ngược lại đều có thể thiếu.

## 3. Mục tiêu, đối tượng và phạm vi một đợt review

Mỗi đợt rà soát cần có **scope đã được duyệt**:

| Phạm vi | Ví dụ | Bằng chứng tối thiểu |
| --- | --- | --- |
| **Ứng dụng/API** | CRM, Finance API, Data Lake, vault, CI/CD. | Danh sách PEP, API/action và tài nguyên nhạy cảm. |
| **Policy** | Policy ID, phiên bản, rule combining, default decision. | Source đã version hóa, owner, approval và deploy record. |
| **Thuộc tính subject** | employmentStatus, department, tenant, clearance, project assignment. | Authoritative source, mapping, freshness và khả năng thay đổi. |
| **Thuộc tính resource** | tenantId, data classification, owner, legal hold, trạng thái workflow. | Resource inventory, data owner, tag/attribute quality. |
| **Context** | auth_time, authentication assurance, device posture, time window. | Nguồn context đáng tin, SLA và cách xử lý thiếu thông tin. |
| **Quyền bổ sung** | RBAC groups, nested groups, direct ACL, delegated grant, link chia sẻ. | Danh sách nguồn cấp quyền và phép thử effective access. |
| **Vòng đời** | Joiner, Mover, Leaver, contractor expiry, service identity owner change. | Event, effectiveAt, desired state, trạng thái đích. |
| **Các hệ thống tích hợp** | IdP/SSO, SCIM, HRIS, IGA, token service, SaaS local role. | Mapping chủ thể và readback, propagation metrics. |

Một review có thể chọn **tất cả quyền nhạy cảm** hoặc **mẫu đại diện theo rủi ro**. Nếu chỉ lấy mẫu, phải ghi rõ phạm vi không kiểm và không tuyên bố “toàn bộ quyền an toàn”.

### Những đối tượng phải có người chịu trách nhiệm

- **Business/data owner:** xác nhận nhu cầu truy cập, phạm vi dữ liệu, SoD và ngoại lệ nghiệp vụ.
- **Policy owner / IAM governance:** quản lý policy, tiêu chuẩn và quyết định recertification.
- **Attribute steward:** chịu trách nhiệm chất lượng, tính mới và nguồn của thuộc tính.
- **Application/API owner:** chứng minh các PEP thực thi policy đúng, không có đường bypass.
- **Security reviewer:** thách thức các giả định, kiểm quyền nhạy cảm và xử lý exception.
- **Audit/compliance:** xác minh bằng chứng, không nên tự trở thành người duy nhất phê duyệt nhu cầu nghiệp vụ.

Không để một người vừa tạo grant, vừa tự chứng nhận grant của mình và vừa xóa bằng chứng sai lệch nếu chính sách yêu cầu phân tách nhiệm vụ.

## 4. Kiến trúc ABAC và vị trí thu thập bằng chứng

~~~mermaid
flowchart LR
    HR["HRIS / Sponsor<br/>Lifecycle JML"] --> IGA["IAM / IGA<br/>Desired state, approvals"]
    IGA --> DIR["IdP / Directory / SCIM"]
    DIR --> PIP["PIP: trusted subject attributes"]
    RES["Resource metadata / Data catalog"] --> PIP
    CTX["Session / Device / Time context"] --> PIP
    PAP["PAP: policy owner<br/>Versioned policies"] --> PDP["PDP: evaluate ABAC"]
    PIP --> PDP
    USER["User / Workload"] --> PEP["PEP: API / Gateway / Service"]
    PEP -->|"Authorization request"| PDP
    PDP -->|"ALLOW, DENY, obligations"| PEP
    PEP --> DATA["Protected resource"]
    PEP --> AUD["Audit / SIEM"]
    PDP --> AUD
    IGA --> AUD
~~~

| Thành phần | Chức năng | Cần rà soát |
| --- | --- | --- |
| **PAP – Policy Administration Point** | Quản lý và xuất bản chính sách. | Có version, approval, rollback, least privilege, owner và change history? |
| **PIP – Policy Information Point** | Cung cấp thuộc tính từ nguồn đáng tin. | Thuộc tính lấy từ đâu, có đúng chủ thể/tenant, TTL, khả năng stale và missing? |
| **PDP – Policy Decision Point** | Đánh giá yêu cầu bằng chính sách. | Logic, conflict, precedence, default deny, policy version, decision reason. |
| **PEP – Policy Enforcement Point** | Áp quyết định vào truy cập thật. | Mọi endpoint/job đều kiểm? Không có side effect khi DENY? |
| **HRIS/IGA/IdP/SCIM** | Quản lý nguồn danh tính, phê duyệt và provisioning. | Desired/actual đồng bộ chưa, có event cũ hoặc duplicate? |
| **Audit** | Lưu quyết định và bằng chứng review. | Có correlation ID, actor, policy version và thông tin tối thiểu không lộ secret? |

**PDP đúng không đủ nếu PEP quên gọi.** Một ứng dụng có thể dùng policy engine tốt nhưng endpoint export chạy nền không kiểm quyền khi tạo tệp. Review phải đối chiếu cả **policy evaluation** lẫn **đường thực thi**.

## 5. Kiểm kê và phân loại chính sách cần rà soát

Trước khi kiểm policy, xây dựng **policy inventory** gồm:

- **Policy ID / version / target environment**: định danh ổn định, nơi triển khai và phiên bản đang chạy.
- **Business purpose**: lý do cho phép, loại thông tin, tài nguyên nào được bảo vệ.
- **Owner và reviewer**: người phụ trách business, security, kỹ thuật.
- **Action/resource scope**: read, export, approve, delete, admin..., tenant, project, classification.
- **Attribute dependencies**: những thuộc tính nào, lấy từ hệ thống nào và yêu cầu độ mới.
- **Combining rules**: khi nhiều rule cùng match thì allow/deny được kết hợp ra sao.
- **Default behavior**: thiếu rule, thiếu attribute, lỗi PIP/PDP hoặc bị time-out thì làm gì.
- **Related entitlements**: role/group, ACL và grant khác có thể bổ sung quyền.
- **Activation/expiry**: ngày hiệu lực, mức ưu tiên, thời hạn ngoại lệ.
- **Test/evidence references**: các bộ positive/negative tests và kết quả review gần nhất.

### Rủi ro khi policy inventory thiếu

| Hiện tượng | Hậu quả |
| --- | --- |
| Policy tại gateway khác policy trong service. | Một số endpoint cho phép rộng hơn hoặc từ chối sai. |
| Bản policy staging dùng cho production. | Rule thử nghiệm có thể bypass kiểm soát thật. |
| Có policy cũ chưa gỡ khỏi engine. | Quyền cũ có thể được kích hoạt lại bởi combining rule. |
| Không rõ owner của rule. | Không ai xác nhận nhu cầu nghiệp vụ hoặc giải quyết exception. |
| Chỉ review policy mới, bỏ qua ACL/direct grants. | Không thấy effective access từ nguồn khác. |

Policy review nên có bước **so sánh policy đã phê duyệt với policy thực tế đang triển khai** (configuration drift), không chỉ đọc bản trong Git.

## 6. Rà soát độ tin cậy và vòng đời thuộc tính

Trong ABAC, một quyết định chỉ đáng tin khi dữ liệu thuộc tính đầu vào đáng tin. Một policy đẹp nhưng dựa trên department do người dùng tự sửa trong hồ sơ cá nhân có thể mở quyền trái phép.

### Bảng kiểm thuộc tính

| Thuộc tính | Nguồn ưu tiên theo thiết kế | Câu hỏi cần kiểm |
| --- | --- | --- |
| **subjectId** | Identity registry/IdP có định danh ổn định. | Có tái sử dụng, duplicate hoặc link nhầm khi đổi email/rehire? |
| **employmentStatus** | HRIS/contract registry được ủy quyền. | Leaver có được ghi ngay, hiệu lực và revision rõ không? |
| **department** | HRIS hoặc nguồn tổ chức được phê duyệt. | Mover thay department thì IdP, PIP và API cập nhật khi nào? |
| **tenantId** | Account mapping và nguồn tenant đáng tin. | Có bị override bởi header/query parameter không? |
| **clearance** | Quy trình phê duyệt phân loại/quyền hạn. | Có ngày hết hạn, người phê duyệt và điều kiện thu hồi không? |
| **projectAssignment** | Project/sponsor system có owner. | Dự án kết thúc có tự hủy quan hệ hay không? |
| **resource.classification** | Data owner / data catalog đáng tin. | Nhãn mặc định có đúng và có thể bị user sửa để hạ cấp không? |
| **resource.owner** | Backend nghiệp vụ hoặc workflow ownership. | Có xác minh owner transfer và ACL sau chuyển quyền không? |
| **resource.tenantId** | Database/backend của tài nguyên. | Có bị lấy từ request client thay vì bản ghi thật không? |
| **deviceCompliant** | MDM/UEM hoặc kiểm tra posture được tin. | Tín hiệu có timestamp, nguồn và TTL phù hợp không? |
| **authenticationAge** | IdP/session service đáng tin. | Có dùng auth_time thực thay vì thời điểm phát token mới iat? |
| **requestTime** | Đồng hồ server/PEP đáng tin. | Đơn vị, múi giờ và clock skew có được xử lý nhất quán không? |

### Mô hình metadata cho một thuộc tính

~~~yaml
attributeName: employmentStatus
subjectType: WORKFORCE_USER
authoritativeSource: HRIS
valueSet: [PRE_HIRE, ACTIVE, SUSPENDED, LEAVER]
ownerTeam: workforce-identity
propagationTargets: [IGA, workforce-idp, finance-pip]
trustRequirement: SERVER_VERIFIED
freshnessSlaSeconds: 120
onMissingOrStale: DENY_SENSITIVE_ACTIONS
audit:
  recordSourceRevision: true
  recordEffectiveAt: true
~~~

Đây là **YAML mô hình minh họa**, không phải cấu hình áp dụng trực tiếp cho một sản phẩm. Giá trị 120 giây là ví dụ chính sách cần thẩm định theo mức rủi ro thực tế, không phải SLA chuẩn cho mọi tổ chức.

### Các lỗi dữ liệu cần phát hiện

1. **Stale attribute:** role/department trong token, session hoặc PIP đã quá cũ so với HRIS.
2. **Missing attribute:** policy không có resource classification, tenant hoặc owner mà mặc định cho phép.
3. **Conflicting attributes:** HRIS nói Leaver nhưng SaaS user vẫn active.
4. **Untrusted override:** client tự gửi department=Finance hoặc X-Tenant=other-tenant.
5. **Incorrect mapping:** email đổi nhưng API liên kết account sai người, sai tenant.
6. **Over-broad enum:** ký hiệu ANY hoặc PUBLIC được gán nhầm cho tài nguyên nhạy cảm.
7. **Ownerless data:** thuộc tính không có steward, không có ngày hết hạn hoặc không ai xác minh.

**Kết quả rà soát không thể chỉ là “attribute có giá trị”.** Phải trả lời **giá trị do ai cung cấp, mới đến đâu, áp dụng cho chủ thể nào và có đúng tại điểm ra quyết định không**.

## 7. Đánh giá effective access thay vì chỉ nhìn điều kiện policy

**Effective access** là quyền truy cập thực tế sau khi tổng hợp các cơ chế cấp và từ chối quyền trong ứng dụng. Trong hệ thống lai, một chủ thể có thể được phép qua nhiều đường:

- Role nghiệp vụ theo **RBAC**, bao gồm nhóm lồng nhau.
- Rule theo **ABAC** dựa trên department, tenant, clearance và classification.
- Quan hệ owner/member theo **ReBAC**.
- **Direct ACL**, delegated access, temporary share hoặc tài liệu được chia sẻ trực tiếp.
- Session, cached role hoặc token phát trước khi đổi quyền.
- Local user/account và API key riêng tại SaaS không đi qua SSO.
- Quyền quản lý một service account/workload có thể dùng credential riêng.

Đánh giá quyền hữu hiệu cần lấy đúng dữ liệu từ **điểm thực thi**, không chỉ đọc policy từ kho mã nguồn:

~~~text
Review input:
  current HRIS status + IGA desired entitlements
  policy version active at target PEP/PDP
  trusted subject/resource/context attributes
  RBAC roles, nested groups, ACL and delegated grants
  live session, token and workload routes (where relevant)

Review output:
  expected action-resource decision from approved business policy
  observed effective decision at each required enforcement point
  differences with owner, severity, remediation and evidence
~~~

**Lưu ý:** effective access không luôn bằng phép hợp đơn giản của các grants. Một số chính sách có **explicit DENY, deny-overrides, permit-overrides, first-applicable, SoD** hoặc quy tắc ưu tiên khác. Phải dùng đúng **combining semantics** của policy engine và hành vi thực của ứng dụng.

### Các trường hợp quyền tồn dư khó thấy

| Hiện tượng | Vì sao rà soát sơ bộ bỏ sót? | Bằng chứng cần |
| --- | --- | --- |
| Group Finance đã gỡ, direct ACL vẫn còn. | Chỉ xem membership IdP. | ACL readback và API probe. |
| Department đã chuyển, JWT còn claim department cũ. | Attribute thay đổi nhưng token chưa hết hạn. | Kiểm API với phiên cũ theo SLA. |
| Mất role SaaS, nhưng còn personal API token. | SCIM không nhất thiết quản lý PAT. | Token inventory, revoke và effective access. |
| Chủ thể Leaver có link chia sẻ còn hiệu lực. | Link không phụ thuộc login mới của user. | Capability/link lifecycle và quyền tài nguyên. |
| Policy trả DENY, endpoint batch không gọi PDP. | Chỉ unit test policy. | PEP integration test và side-effect audit. |
| ABAC cho phép theo location nhưng geolocation stale/giả. | Nguồn context yếu hoặc không đáng tin. | Kiểm nguồn/timestamp và policy xử lý tín hiệu thiếu. |

**Review đạt** khi có bằng chứng các đường truy cập nằm trong scope đều thực thi policy đã duyệt. Nếu không thể quan sát một target, phải ghi **UNVERIFIED/COVERAGE_GAP**, không biến thiếu bằng chứng thành PASS.

## 8. Quy trình rà soát ABAC theo vòng đời

Một quy trình lặp lại và có thể kiểm toán:

~~~mermaid
flowchart TD
    A["Kích hoạt: lịch, JML, policy change hoặc incident"] --> B["Chốt scope, owner, policy baseline và SLA"]
    B --> C["Thu inventory PEP/PDP, rule, attribute và source"]
    C --> D["Thu desired state từ HRIS/IGA và business owner"]
    D --> E["Tính decision mong đợi + effective-access snapshot"]
    E --> F["Chạy positive/negative tests, readback và đối soát"]
    F --> G{"Có drift/rủi ro/coverage gap?"}
    G -->|Không| H["Reviewers chứng nhận có căn cứ"]
    G -->|Có| I["Phân loại, revoke/fix policy/attribute, exception"]
    I --> F
    H --> J["Lưu evidence, thời hạn và giám sát tiếp"]
~~~

### Bước 1 – Kích hoạt và xác định rủi ro

Review có thể diễn ra theo lịch hoặc do một sự kiện: thay đổi HR, thay ownership dữ liệu, phát hiện token bị lộ, thay policy, tích hợp SaaS mới hoặc cảnh báo vượt quyền. Phân loại **tài nguyên, hành động, người dùng và phạm vi ảnh hưởng**.

### Bước 2 – Đóng băng baseline kiểm chứng

Ghi **policy version, target environment, danh sách PEP, nguồn thuộc tính và thời điểm snapshot**. Nếu hệ thống thay đổi trong lúc review, cần cơ chế version/correlation để không so dữ liệu từ hai thời điểm không tương đương.

### Bước 3 – Thu desired state từ nguồn có thẩm quyền

Lấy trạng thái JML từ HRIS, approval/role/SoD từ IGA và các quy tắc business từ data owner. Một account đang ACTIVE tại IdP không nhất thiết có quyền trên Finance; ngược lại, group bị gỡ ở IdP không chứng minh mọi grant SaaS biến mất.

### Bước 4 – Lập ma trận quyết định mong đợi

Liệt kê subject groups, actions, resource types và điều kiện boundary. Phải biết những yêu cầu nào **được phép**, những yêu cầu nào **phải từ chối**, và rule nào giải thích quyết định.

### Bước 5 – Thu trạng thái thực và kiểm tra nguồn thuộc tính

Đọc policy phiên bản đang chạy, PIP/attribute freshness, mappings, direct ACL, group, role, session/token và các account kỹ thuật. Giữ **timestamp và provenance** để không lấy một cache lâu ngày làm bằng chứng trạng thái hiện hành.

### Bước 6 – Kiểm thử ở PDP và PEP

Chạy **policy unit tests** với tổ hợp điều kiện; sau đó chạy **API/effective-access probes** có kiểm soát để xác minh enforcement. Negative test phải có positive control để phân biệt policy DENY với lỗi mạng hoặc dữ liệu fixture không tồn tại.

### Bước 7 – Phân loại sai lệch

Tách:

- **Policy defect:** rule quá rộng, precedence sai, không có SoD.
- **Attribute defect:** stale/wrong mapping/thiếu nguồn tin cậy.
- **Enforcement defect:** PEP bypass, local ACL, resource-level check thiếu.
- **Lifecycle defect:** Mover/Leaver chưa được áp tới token/session và app đích.
- **Coverage gap:** không thể đọc hoặc thử một đường truy cập bắt buộc.
- **False deny:** user hợp lệ bị chặn vì policy/attribute sai.

### Bước 8 – Khắc phục theo mức rủi ro

Nếu có tài khoản đã Leaver hoặc quyền admin trái phép, ưu tiên **chặn quyền nguy hiểm** bằng cơ chế được phê duyệt, sau đó sửa nguồn/policy/connector. Những lỗi ít rủi ro hơn có thể theo change workflow nhưng vẫn cần owner, deadline và kiểm soát bù trừ.

### Bước 9 – Xác minh lại và chứng nhận

Business owner xác nhận nhu cầu tiếp tục cấp quyền; application/security team xác minh PEP thực tế đã đúng. Trạng thái **APPLIED** (đã thay đổi cấu hình) khác với **VERIFIED** (đã chứng minh effective access thay đổi).

### Bước 10 – Đóng vòng và giám sát drift

Lưu phiên bản policy, attribute provenance, quyết định reviewer, kết quả probe, thời gian thu hồi, exceptions và bằng chứng phù hợp retention. Thiết lập giám sát để phát hiện trạng thái tái lệch sau lần review.

## 9. Tần suất rà soát và các trigger quan trọng

Không có một chu kỳ cố định phù hợp mọi tổ chức. Cần chọn cadence **theo rủi ro, thay đổi, tác động nghiệp vụ và yêu cầu tuân thủ**.

| Rủi ro/biến động | Ví dụ | Cách lập lịch minh họa |
| --- | --- | --- |
| **Rất cao** | Global admin, quyền xuất dữ liệu nhạy cảm, chính sách duyệt thanh toán. | Kiểm liên tục/đột xuất theo sự kiện, review độc lập thường xuyên. |
| **Cao** | Tenant isolation, cloud production, service-principal privilege. | Review theo policy change, owner change, JML và định kỳ ngắn. |
| **Trung bình** | Quyền đọc báo cáo nội bộ và dự án có thời hạn. | Rà soát định kỳ theo vòng công việc và sự kiện bất thường. |
| **Thấp** | Đọc thông tin công khai trong nội bộ. | Rà soát sau policy/ứng dụng thay đổi và theo chương trình chung. |

**Tần suất là lựa chọn chính sách của tổ chức**, không phải cam kết mặc định của ABAC. Một số trigger cần xử lý **ngay theo SLA** thay vì đợi chu kỳ định kỳ:

- Leaver hoặc suspended user có quyền nhạy cảm.
- Mover tạo xung đột **Separation of Duties**.
- Phát hiện thuộc tính HR/IGA không đồng bộ với PIP.
- Thay đổi schema, data classification hoặc resource ownership.
- Đổi policy combining rule, default decision hoặc nền tảng PDP.
- Phát hiện token lộ, API key tồn dư hoặc PEP bypass.
- Onboard/offboard đối tác, tài khoản nhà thầu hoặc service account owner.
- Sự cố directory restore hoặc failover có nguy cơ phục hồi trạng thái cũ.

## 10. Ví dụ policy ABAC và tiêu chí review

Giả sử hệ thống Finance chỉ cho nhân viên ACTIVE thuộc Finance, có role Reader, đọc hóa đơn APPROVED của tenant hiện hành. Hóa đơn phân loại RESTRICTED cần clearance tương xứng.

~~~yaml
policyId: finance-invoice-read
version: 7
owner: finance-data-owner
effect: PERMIT_IF_ALL
subject:
  employmentStatus: ACTIVE
  department: FINANCE
  requiredRole: FINANCE_INVOICE_READER
action: invoice.read
resource:
  tenantMatchesSubject: true
  statusIn: [APPROVED, PAID]
  classificationNotAboveSubjectClearance: true
context:
  trustedAuthentication: true
fallback: DENY
~~~

**Đây là cấu hình mang tính khái niệm**, không phải định dạng chuẩn có thể nạp trực tiếp vào OPA, XACML hay dịch vụ IAM cụ thể. Thuộc tính được lấy từ nguồn đáng tin; role trong rule không nên được client tự khai.

### Những câu hỏi khi đọc policy

1. **Điều kiện employmentStatus là ACTIVE** lấy từ nguồn nào, có cập nhật đúng thời điểm Leaver?
2. Nếu subject thiếu department, có **DENY** hay vô tình bỏ qua điều kiện?
3. Tenant của hóa đơn do backend đọc từ database hay client gửi trong URL?
4. Clearance có **mô hình phân cấp rõ** và đúng label classification không?
5. Có quyền ngoại lệ, ACL hoặc nhóm lồng nào cấp quyền rộng hơn policy này không?
6. Nếu API export dùng cùng dataset, có áp rule tương xứng không?
7. Nếu request từ workload không có employmentStatus, có một policy workload khác, chặt chẽ và được phê duyệt không?
8. Nếu nhiều policy cùng match, quy tắc kết hợp có vô tình chọn PERMIT trước một DENY bắt buộc?
9. Mức assurance của session có đủ cho action cụ thể không, và thông tin đó có đáng tin không?
10. Nếu PIP không hoạt động, có ngăn truy cập nhạy cảm hay cho qua không?

### Không nhầm điều kiện trong policy với trạng thái được thực thi

Một bộ unit test của PDP có thể đánh giá đúng rule ở trên nhưng API vẫn cho truy cập do controller dùng một nhánh code không gọi PEP. Phải có **integration test và kiểm tra side effects**, ví dụ request bị từ chối không trả dữ liệu và không tạo file export.

## 11. Ma trận quyết định mẫu cho review ABAC

| Subject/điều kiện | Resource/action | Kỳ vọng | Lý do |
| --- | --- | --- | --- |
| Finance Reader ACTIVE, tenant A, clearance đủ. | Đọc invoice APPROVED tenant A. | **ALLOW** | Thỏa mọi điều kiện. |
| Sales Reader ACTIVE, tenant A. | Đọc invoice APPROVED tenant A. | **DENY** | Sai department/role. |
| Finance Reader ACTIVE, tenant A. | Đọc invoice tenant B. | **DENY** | Tenant isolation. |
| Finance Reader ACTIVE, clearance thấp. | Đọc invoice RESTRICTED vượt clearance. | **DENY** | Classification rule. |
| Finance Reader ACTIVE. | Đọc invoice DRAFT khi policy chỉ cho APPROVED/PAID. | **DENY** | Resource state. |
| Finance Reader, department không xác định. | Đọc invoice tenant A. | **DENY** | Thuộc tính bắt buộc bị thiếu. |
| Finance Reader nhưng HRIS=LEAVER. | Đọc invoice tenant A bằng token cũ. | **DENY** theo SLA | Lifecycle gate. |
| Finance Reader, session chưa xác thực đủ điều kiện. | Đọc tài nguyên cần authentication hợp lệ. | **DENY/reauthenticate** | Không đáp ứng context. |
| Finance Approver nhưng là người tạo hóa đơn. | Approve invoice của mình. | **DENY** | SoD độc lập với quyền đọc. |
| Finance Reader có group role nhưng direct tenant grant cũ trái policy. | Đọc invoice tenant khác qua API phụ. | **DENY** | Không cho bypass qua ACL. |
| Sync workload đúng scope/tenant. | Gọi API đọc theo workload policy. | **ALLOW** khi đủ điều kiện | Workload policy tách khỏi user policy. |
| Sync workload không có role duyệt. | Approve payment. | **DENY** | Chặn machine privilege escalation. |

Một bảng quyết định là **test oracle theo policy được duyệt**. Kết quả mong đợi không được lấy từ chính hàm đang được kiểm thử, vì cả hai có thể cùng chứa lỗi.

## 12. Kiểm soát Joiner–Mover–Leaver khi rà soát ABAC

### Joiner: cấp quyền theo trạng thái đủ điều kiện

Trước ngày bắt đầu, account có thể được tạo sẵn trong IdP hoặc SCIM target để chuẩn bị. Nhưng một policy với điều kiện **employmentStatus=ACTIVE** phải chặn quyền nghiệp vụ nếu chưa tới ngày hiệu lực, chưa hoàn tất identity proofing hoặc chưa được approval theo quy định.

Các bước rà soát:

1. Kiểm **subject ID ổn định** liên kết HRIS, IdP, IGA và app account.
2. So effectiveAt với thời điểm account active và thuộc tính trong PIP.
3. Đảm bảo department, tenant, clearance và project assignment đến từ nguồn được duyệt.
4. Chứng minh request trước hiệu lực bị từ chối, còn request hợp lệ sau hiệu lực được phép đúng phạm vi.
5. Chặn việc người dùng tự sửa thuộc tính hoặc dùng token của hệ thống khác để mở quyền.

### Mover: quyền cũ phải mất hiệu lực

Khi chuyển từ Sales sang Finance, policy theo department có thể tự chuyển **nếu mọi PEP đọc thuộc tính mới**. Tuy nhiên các quyền cũ có thể vẫn đến từ:

- JWT/session chứa department hoặc role cũ.
- Group membership chậm cập nhật giữa HRIS, IdP và SaaS.
- Direct ACL hoặc quyền chia sẻ trước đó.
- Delegation từ người quản lý cũ.
- Project membership, temporary override hoặc account phụ.
- Quyền truy cập vault/CI/CD/service principal của nhóm Sales.

**Rà soát Mover cần cả negative và positive tests**: người dùng không còn quyền Sales trái policy nhưng vẫn có quyền Finance mới đã được phê duyệt. Nếu hai chức năng xung đột SoD, cần kiểm thứ tự thu hồi/cấp để không có khoảng chồng lấn nguy hiểm.

### Leaver: xác thực mạnh vẫn không cho phép truy cập

Một Leaver có thể có session SSO, OAuth token hoặc local SaaS account đã được tạo trước ngày nghỉ. Một lần MFA hợp lệ từ hôm qua **không làm employmentStatus=LEAVER trở thành ACTIVE**.

Rà soát phải:

1. Xác minh source event Leaver, subjectId, effectiveAt và revision.
2. Disable account/login tại IdP và xử lý session/refresh token theo chính sách.
3. Đối soát SCIM User/Group và các quyền tại app đích.
4. Kiểm RS/API từ chối token cũ theo kiến trúc và SLA thu hồi.
5. Xem direct ACL, service account ownership, vault và personal API key.
6. Chỉ đóng **VERIFIED** khi các target bắt buộc có bằng chứng thu hồi.

### Rehire hoặc ngừng hợp đồng

Người được tuyển lại có thể giữ email cũ nhưng không nên được cấp lại mọi quyền lịch sử. Cần proofing/identity linking theo nguồn tin cậy, tính desired state của quan hệ mới, kiểm account mapping và expiry của grant. Nhà thầu hết hợp đồng phải được xử lý như một biến cố lifecycle có thời điểm hiệu lực rõ, không chờ review quý mới thu hồi.

## 13. Review chứng nhận quyền và trách nhiệm người phê duyệt

Trong **access certification**, data owner hoặc quản lý phải xem quyền thực sự được cấp, hiểu lý do và quyết định **KEEP, REVOKE, CHANGE, INVESTIGATE**.

| Quyết định | Khi nào dùng | Việc kỹ thuật theo sau |
| --- | --- | --- |
| **KEEP** | Nhu cầu truy cập còn hợp lệ, đúng policy. | Lưu lý do, owner và kỳ review tiếp theo. |
| **REVOKE** | Không còn nhu cầu, quan hệ đã kết thúc hoặc vi phạm policy. | Thu hồi tại nguồn và target; readback/verify DENY. |
| **CHANGE** | Cần thu hẹp action, tenant, resource, expiry hoặc điều kiện. | Sửa policy/attribute/grant, test regression và xác minh. |
| **INVESTIGATE** | Thiếu dữ liệu, mapping mâu thuẫn hoặc không có owner rõ. | Escalate, tạm bảo vệ tài nguyên rủi ro cao và thu chứng cứ. |
| **EXCEPTION** | Tạm cho phép khác baseline do nhu cầu hợp lệ và phê duyệt riêng. | Giới hạn scope, TTL, kiểm soát bù trừ, auto-expire và kiểm lại. |

### Cách trình bày để người duyệt hiểu được ABAC

Đừng chỉ đưa JSON policy dài và yêu cầu manager bấm “Approve”. Hãy đưa **ảnh hưởng nghiệp vụ**:

~~~text
Subject: person-4821
Current department: Finance (nguồn HRIS)
Policy: finance-invoice-read v7
Effective capability:
  - READ hóa đơn APPROVED của tenant-vn
  - KHÔNG được EXPORT tổng hợp
  - KHÔNG được APPROVE nếu là requester
Attribute validity: HR revision 204; verified within approved SLA
Business justification: Công việc phân tích chi phí tháng
Owner decision: KEEP until role review date
Evidence: policy simulation + API readback/probe refs
~~~

Đây là bản mô tả cho reviewer, không phải proof toàn diện; vẫn cần bằng chứng test PEP. Người duyệt không nên chịu trách nhiệm đánh giá chữ ký JWT hoặc mọi chi tiết kỹ thuật, nhưng phải xác nhận **mục đích nghiệp vụ và phạm vi cần thiết**.

## 14. Rà soát ABAC qua IdP/SSO, SCIM và hệ thống phân quyền

Các chính sách ABAC thường lấy thuộc tính từ nhiều nơi. Mỗi bước truyền dữ liệu có khả năng làm sai **ngữ nghĩa, độ mới, subject mapping** hoặc phạm vi tenant.

| Công nghệ/nguồn | Vai trò trong IAM | Việc ABAC review phải xác minh |
| --- | --- | --- |
| **HRIS** | Nguồn thông tin nhân sự, chức danh, ngày hiệu lực. | Đúng đối tượng, trạng thái hiện hành, revision và thời điểm thay đổi. |
| **IGA** | Approval, desired entitlements và access certification. | Rule nghiệp vụ, SoD, owner và quyền sau JML. |
| **IdP/directory** | Danh tính và thuộc tính, group, trạng thái account. | Mapping đúng, không nhận user tự khai thuộc tính nhạy cảm. |
| **SSO/OIDC/SAML** | Truyền kết quả xác thực và đôi khi mang attributes. | Claims/assertions được xác minh, nguồn và độ mới theo contract. |
| **SCIM** | Provision/deprovision Users/Groups ở SaaS. | Readback target account, active, group/role; không coi HTTP thành công là hết quyền. |
| **OAuth AS** | Cấp token theo client/grant/scope. | Token đang cấp và refresh grant có còn phù hợp trạng thái quyền? |
| **Resource Server** | Thực hiện quyết định API và object access. | PEP thực tế chặn quyền ngoài policy, kể cả JWT cũ. |
| **SaaS local ACL/role** | Grant riêng bên cạnh IdP. | Inventory các grant và local sessions không chịu SCIM/SSO hoàn toàn. |

### Claim trong token không tự là thuộc tính luôn mới

IdP có thể phát JWT chứa department=Sales tại thời điểm đăng nhập. Sau Mover, token này có thể vẫn hợp lệ về chữ ký và thời gian. Nếu API chỉ dùng claim cũ để xét thuộc tính, nó có thể cho phép truy cập trái policy hiện hành.

Biện pháp tùy rủi ro và khả năng:

- Giới hạn TTL của access token theo cửa sổ tồn dư được chấp nhận.
- Kiểm **current entitlement** hoặc trạng thái subject tại backend khi tác vụ nhạy cảm.
- Sử dụng introspection, token version, revocation list hoặc chính sách invalidation nếu kiến trúc hỗ trợ.
- Chủ động revoke refresh token/grant khi Mover/Leaver; đồng thời xử lý **access token đã cấp** riêng.
- Định kỳ kiểm API bằng phiên/token được tạo **trước** thay đổi quyền, không chỉ token mới.

**Không tin các trường department, clearance, tenantId do browser gửi trong body/header** dù chúng trùng giá trị token. Backend phải dùng những claims đã xác minh hoặc thuộc tính tra cứu từ nguồn đáng tin, với độ mới phù hợp mục tiêu.

### SCIM User inactive không đồng nghĩa mọi phiên đã chết

SCIM có thể đặt User active=false hoặc thay Group membership, nhưng **không phải giao thức quản lý phiên**. App có thể tiếp tục nhận local session, personal access token hoặc API key. Một review chỉ xác nhận SCIM PATCH được áp nhưng chưa thử **effective access** phải để trạng thái chưa được kiểm chứng hoàn toàn.

## 15. Rà soát ABAC đối với service account và workload

Danh tính phi con người có thể có thuộc tính khác nhân viên: **workload name, namespace, environment, project, deployment identity, owner team, attested platform, audience, certificate identity**. Không nên ép tất cả workload qua một policy dựa trên department của con người.

Ví dụ chính sách workload:

~~~yaml
policyId: reporting-workload-read
version: 3
principalType: WORKLOAD
subject:
  workloadId: report-generator
  environment: production
  ownerTeam: finance-platform
action: invoice.summary.read
resource:
  tenant: tenant-vn
  classificationAtMost: INTERNAL
context:
  trustedWorkloadIdentity: true
  tokenAudience: reporting-api
fallback: DENY
~~~

Đây là pseudoconfiguration, không phải định dạng policy của một nền tảng cụ thể. Giá trị ownerTeam phải là metadata được quản trị, không phải claim client tự khai.

### Checklist review workload

1. **Workload có còn tồn tại?** Job/service đã decommission nhưng principal hoặc role vẫn active?
2. **Ai sở hữu?** Có owner kỹ thuật và business owner hợp lệ? Owner đã Mover/Leaver thì đã bàn giao?
3. **Thuộc tính có xác minh được không?** Environment, namespace, repository, certificate, issuer có được ràng buộc bằng nguồn đáng tin?
4. **Scope tối thiểu?** Service chỉ đọc các tài nguyên cần cho mục đích, không có đặc quyền admin tùy tiện?
5. **Credential**: có secret dài hạn, key/certificate sắp hết hạn hoặc khả năng rotate/revoke?
6. **Cross-environment**: token staging có bị production nhận sai audience/trust không?
7. **Delegation**: service có thể hành động thay user ở phạm vi nào, ai có quyền yêu cầu, có chống confused deputy?
8. **Audit**: có phân biệt actor người dùng với principal workload đang thực thi?

**Không xóa một service account quan trọng chỉ vì người sở hữu cũ nghỉ việc.** Cần chuyển owner, thu hồi quyền quản trị của người cũ, đánh giá secret từng biết và kiểm workload còn được phép phục vụ nghiệp vụ.

### Test rủi ro đặc biệt

Giả sử service invoice-sync chỉ được đọc hóa đơn nội bộ tenant VN. Test phải bảo đảm nó **không thể duyệt thanh toán, truy cập tenant khác, sửa policy hoặc đọc secret của workload khác**, ngay cả khi client credentials token còn hạn và được xác thực thành công.

## 16. Rà soát SoD, delegated access và ngoại lệ ABAC

**Separation of Duties (SoD)** yêu cầu tách các hành động xung đột, ví dụ người tạo thanh toán không thể tự phê duyệt thanh toán đó. Trong ABAC, điều kiện SoD có thể phụ thuộc **subjectId của requester** và **resource.requesterId**, không chỉ role.

~~~text
ALLOW payment.approve WHEN
  subject.active == true
  AND subject.hasRole("PAYMENT_APPROVER")
  AND subject.tenant == payment.tenant
  AND payment.status == "PENDING_APPROVAL"
  AND subject.id != payment.requesterId
  AND authentication.isRecentEnough == true
ELSE DENY
~~~

Rà soát phải kiểm cả chính sách lẫn quyền thực tế nếu user có hai role xung đột hoặc resource ownership đổi.

### Ngoại lệ có giới hạn

Một ngoại lệ bàn giao có thể cho nhân viên sau Mover được đọc một tập tài liệu cũ trong thời gian ngắn. Muốn review hợp lệ, ngoại lệ cần:

| Thuộc tính ngoại lệ | Tiêu chí |
| --- | --- |
| Business reason | Nêu rõ công việc cụ thể, không chỉ “cần truy cập”. |
| Owner và approver | Người phê duyệt đủ thẩm quyền, không tự cấp tự duyệt. |
| Subject/resource/action | Phạm vi tài nguyên và hành động tối thiểu. |
| Tenant/classification | Không được mở xuyên tenant hoặc phân loại nhạy cảm trái quy định. |
| Validity | startAt, expiresAt, timezone và cơ chế tự hết hạn. |
| Compensating controls | MFA/step-up, giám sát, chặn export khi cần, audit. |
| Revocation proof | Bằng chứng sau hết hạn không còn effective permission. |

**EXCEPTION_APPROVED không tương đương “mọi quyền đã thu hồi”.** Hệ thống báo cáo phải phân biệt quyền còn được phép tạm theo ngoại lệ và các quyền đã thực sự mất hiệu lực. Ngoại lệ không có expiry hoặc owner cần được xử lý theo mức rủi ro, không duy trì vô hạn.

### Break-glass access

Quyền khẩn cấp là trường hợp đặc biệt: có thể bỏ qua một số điều kiện thông thường theo policy đã duyệt, nhưng vẫn cần **định danh người sử dụng, giới hạn thời gian, ghi lại lý do, giám sát, phê duyệt sau sử dụng khi phù hợp và thu hồi**. Không thiết kế break-glass như một rule global PERMIT không có kiểm soát.

## 17. Kiểm tra semantics của policy engine và lỗi fail-open

ABAC có thể được thực thi bằng engine khác nhau: rule tự viết, OPA/Rego, XACML-style PDP hoặc dịch vụ cloud IAM. Khi rà soát phải hiểu **ngữ nghĩa quyết định** của engine đang dùng.

Những câu hỏi quan trọng:

- Nếu không có rule phù hợp, engine trả **DENY**, NOT_APPLICABLE hay trạng thái khác? PEP áp fallback ra sao?
- Nếu policy A PERMIT và policy B DENY cùng match, quy tắc **combining** nào quyết định kết quả?
- Nếu thiếu department/tenant/classification, so sánh có fail-safe không?
- Nếu PIP mất kết nối, có **INDETERMINATE** và PEP xử lý khác với một DENY thông thường không?
- Nếu policy mới deploy ở một region nhưng region khác còn bản cũ, sự chênh lệch kéo dài bao lâu?
- Nếu cache giữ kết quả ALLOW cũ, TTL, invalidation và revocation mechanism có đáp ứng SLA?
- Các nhánh code import, bulk, export, async và admin có kiểm lại ABAC hay không?
- Policy có dùng giờ hệ thống hoặc trạng thái workflow ở thời điểm **commit** khi hành động ghi nhạy cảm?

### Không chuyển lỗi thành quyền

| Lỗi đầu vào/hạ tầng | Kết quả cần xem xét | Nguy cơ nếu triển khai sai |
| --- | --- | --- |
| PIP thiếu tenantId. | DENY hoặc fail-safe theo policy. | Truy cập xuyên tenant vì tenant rỗng được hiểu wildcard. |
| PDP timeout. | Chặn hành động nhạy cảm/đáp lỗi kỹ thuật có kiểm soát. | Default PERMIT để hệ thống “tiếp tục hoạt động”. |
| Resource classification chưa gắn. | Không cho xử lý dữ liệu nhạy cảm khi chưa xác định. | Mặc định PUBLIC dù dữ liệu thực tế RESTRICTED. |
| Session assurance không còn đủ mới. | Step-up hoặc DENY. | Chỉ kiểm MFA đã từng đăng ký, bỏ auth_time. |
| User LEAVER nhưng claim token ACTIVE. | Trạng thái hiện hành/TTL/revocation quyết định. | Tiếp tục truy cập theo claim cũ. |
| Hai policies có quyết định xung đột. | Áp đúng combining rule đã duyệt và audit. | Rule PERMIT rộng vô tình thắng rule DENY quan trọng. |

**Deny by default** là nguyên tắc thiết kế quan trọng, nhưng cách phản hồi HTTP và trạng thái nội bộ phải phù hợp contract. Một lỗi PDP không phải “policy DENY” có căn cứ; cần ghi đúng nguyên nhân để vận hành có thể xử lý và người dùng không nhận thông tin nhạy cảm.

## 18. Propagation, cache và độ trễ thu hồi ABAC

Đối tượng ABAC có thể thay đổi ở nhiều nơi không đồng thời:

~~~mermaid
sequenceDiagram
    participant HR as HRIS
    participant IGA as IAM / IGA
    participant IDP as IdP / Token service
    participant PIP as Attribute service
    participant API as PEP / Resource Server
    HR->>IGA: Mover/Leaver event + effectiveAt + revision
    IGA->>IDP: Disable / role update / token policy
    IGA->>PIP: Attribute update
    PIP-->>IGA: Applied version
    IGA->>API: Invalidate policy/authorization cache if supported
    API->>PIP: Fresh attribute query when required
    API-->>IGA: Access decision evidence
~~~

Một lần readback từ PIP chưa chứng minh **mọi API instance** đã cập nhật cache. Review nên đo:

\[
\operatorname{RevocationLatency} =
t_{\mathrm{last\ required\ verified\ DENY}} - t_{\mathrm{effectiveAt}}
\]

Trong đó mốc cuối là lúc **tất cả PEP bắt buộc** đã được chứng minh từ chối quyền cũ theo phạm vi đã định, không phải lúc connector trả HTTP 200.

### Kiểm thử cửa sổ propagation

1. Thiết lập trạng thái ban đầu, xác minh principal có quyền.
2. Tạo session/token trước khi thay đổi, ghi metadata an toàn.
3. Kích hoạt Mover/Leaver với effectiveAt và revision rõ.
4. Ghi thời điểm HRIS/IGA, IdP, SCIM, PIP và API instance áp thay đổi.
5. Lặp probe đọc không phá hoại tại các PEP/regions trọng yếu theo kế hoạch test.
6. Kiểm cả token mới và token đã cấp trước sự kiện.
7. Báo **FAIL** nếu còn ALLOW ngoài cửa sổ SLA; báo **UNVERIFIED** nếu không có khả năng thử.

Tránh dùng HTTP 503 do API down làm bằng chứng quyền đã bị thu hồi. Cần **positive control** xác nhận dịch vụ vẫn hoạt động và reason code phù hợp.

### Chống sự kiện cũ ghi đè trạng thái mới

Mọi luồng đồng bộ thuộc tính JML cần xem **event revision, current HR state, idempotency key và mốc hiệu lực**. Nếu Mover cũ đến sau Leaver, connector hoặc PIP không được đưa employmentStatus về ACTIVE hay tạo lại role. Test theo thứ tự đảo và retry để chứng minh điều đó.

## 19. Hồ sơ rà soát, quyết định và bằng chứng kiểm toán

Một hồ sơ review phải cho biết **ai đánh giá, đánh giá policy nào, dựa trên dữ liệu nào, đối với những quyền nào và kết luận đã được xác minh tới đâu**.

~~~yaml
reviewCaseId: abac-review-2026-0142
scope:
  application: finance-api
  environment: production
  policyId: finance-invoice-read
  policyVersion: 7
  subjects: [person-4821, person-3910]
  actions: [invoice.read, invoice.export]
trigger:
  type: MOVER_EVENT
  sourceRef: hris-event-204
  effectiveAt: "2026-11-23T09:00:00Z"
attributeEvidence:
  sourceSystem: HRIS
  sourceRevision: 204
  freshnessCheck: PASSED
policyVerification:
  unitTestStatus: PASSED
  apiProbeStatus: PARTIAL
targetVerification:
  - target: finance-api-primary
    result: PASSED
    evidenceRef: authz-probe-133
  - target: finance-export-worker
    result: PENDING
    evidenceRef: null
reviewDecision: INVESTIGATE
overallStatus: VERIFICATION_IN_PROGRESS
ownerTeam: identity-governance
~~~

Đây là **schema minh họa**, không phải định dạng bắt buộc của sản phẩm. Trạng thái **VERIFICATION_IN_PROGRESS** là đúng vì worker xuất báo cáo chưa được kiểm tra, dù unit test và API chính đã PASS.

### Evidence nên gồm những gì?

| Metadata | Mục đích |
| --- | --- |
| Review ID, scope, trigger | Biết đợt rà soát bắt đầu vì lý do nào. |
| Policy ID/version/deployment digest | Kiểm đúng chính sách thực tế được chạy. |
| Authoritative attribute source/revision | Chứng minh dữ liệu thuộc tính đúng nguồn và đủ mới. |
| Subject/resource references | Xác định đúng người/workload và tài nguyên, tránh gộp nhầm. |
| Expected/actual decision | Phát hiện sai lệch và bảo vệ test oracle. |
| PEP/PDP/region/target | Không đánh đồng một API với toàn bộ hệ thống. |
| Reviewer, decision, timestamp | Truy vết quyết định nghiệp vụ và bảo mật. |
| Remediation/exception/expiry | Biết hành động tiếp theo và mức tồn dư. |
| verifiedAt và coverage | Chứng minh đã hoàn tất điều kiện bắt buộc hay còn thiếu. |

**Không lưu credential thật trong evidence**: mật khẩu, OTP, access/refresh token, cookie phiên, private key, client secret, nội dung chứng từ nhạy cảm. Các ID resource cũng có thể là dữ liệu cá nhân, cần kiểm soát truy cập và retention.

### Trạng thái review khác trạng thái xử lý kỹ thuật

| Trạng thái | Ý nghĩa |
| --- | --- |
| **SCHEDULED** | Đã lập scope, owner và lịch/trigger. |
| **IN_REVIEW** | Đang thu thập policy, thuộc tính và đối chiếu quyền. |
| **REMEDIATION_REQUIRED** | Có sai lệch đã xác nhận cần sửa. |
| **BLOCKED/UNVERIFIED** | Thiếu nguồn dữ liệu/PEP hoặc không thể xác minh một phần bắt buộc. |
| **EXCEPTION_APPROVED** | Có quyền tạm được phê duyệt theo hạn và kiểm soát bù trừ. |
| **VERIFIED** | Tất cả kiểm tra bắt buộc đạt và không còn quyền ngoài policy trong scope. |
| **CLOSED** | Hồ sơ được ký duyệt và lưu bằng chứng theo retention. |

Không ghi VERIFIED chỉ vì owner đã click “Approve”; điều đó có thể chứng minh nhu cầu nghiệp vụ, **không tự chứng minh cấu hình và effective access đã được áp**.

## 20. Ma trận kiểm thử rà soát ABAC

Một chương trình ABAC review phải có **positive controls, negative tests và kiểm tra thuộc tính thiếu/sai/đã cũ**. Bảng dưới là bộ khung để map sang chính sách thật.

| ID | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| R01 | Finance Reader ACTIVE đọc invoice APPROVED cùng tenant. | ALLOW nếu các điều kiện khác đạt. |
| R02 | Sales Reader thử đọc invoice Finance. | DENY theo department/role. |
| R03 | Finance Reader đọc invoice tenant khác. | DENY dù biết object ID. |
| R04 | Finance Reader đọc invoice vượt clearance. | DENY classification. |
| R05 | Resource không có classification đáng tin. | DENY/fail-safe theo policy, không mặc định PUBLIC. |
| R06 | Subject thiếu tenantId trong PIP. | DENY/fail-safe, không wildcard. |
| R07 | Client tự gửi department=Finance để vượt policy. | Không dùng thuộc tính chưa tin cậy. |
| R08 | Client gửi header X-Role=ADMIN. | Không được cấp quyền vì header tự khai. |
| R09 | Subject có role nhưng HRIS đã LEAVER. | API DENY theo SLA. |
| R10 | Subject PRE_HIRE chưa tới effectiveAt. | Không cấp quyền nghiệp vụ. |
| R11 | Mover đổi department, token chứa department cũ. | Quyền cũ bị chặn trong cửa sổ cam kết. |
| R12 | Mover vẫn có direct ACL sau khi group được gỡ. | Detect drift, thu hồi grant và verify. |
| R13 | Nested group giữ quyền đã không còn phù hợp. | Effective access không còn trái policy. |
| R14 | Contract/project assignment hết hạn. | DENY sau expiresAt. |
| R15 | Delegated access có ngoại lệ hợp lệ còn hạn. | Chỉ ALLOW trong scope/TTL được duyệt. |
| R16 | Ngoại lệ đã quá hạn nhưng cache còn grant. | DENY theo SLA, alert drift. |
| R17 | Approver muốn duyệt giao dịch do mình tạo. | DENY theo SoD. |
| R18 | Role mới tạo xung đột SoD với role cũ. | Không có khoảng chồng lấn ALLOW trái policy. |
| R19 | Mất kết nối PIP lấy employmentStatus. | Không mở quyền nhạy cảm vì thiếu dữ liệu. |
| R20 | PDP timeout khi xử lý export. | Fail-safe, phân biệt lỗi kỹ thuật với policy deny. |
| R21 | Policy A PERMIT, policy B DENY cùng match. | Áp đúng combining rule đã phê duyệt. |
| R22 | PEP dùng policy version cũ sau rollout. | Detect drift, chặn/quarantine theo mức rủi ro. |
| R23 | Batch/export worker không gọi PDP. | Regression test FAIL; không xuất dữ liệu ngoài quyền. |
| R24 | API trả DENY nhưng file/event đã tạo. | FAIL; không có side effect trái quyền. |
| R25 | GraphQL nested field trả dữ liệu classification cao. | Bị lọc/chặn đúng chính sách. |
| R26 | JWT có chữ ký hợp lệ nhưng audience sai. | Token verifier từ chối. |
| R27 | Token đã hết hạn hoặc sai issuer. | Không dùng để xác định principal hợp lệ. |
| R28 | SCIM active=false nhưng SaaS local session còn dùng. | Chưa VERIFIED; xử lý local session. |
| R29 | Leaver vẫn có personal API token tại app đích. | Detect và revoke; kiểm effective access. |
| R30 | Service principal staging gọi tài nguyên production. | DENY cross-environment/trust. |
| R31 | Workload có scope đọc nhưng thử approve thanh toán. | DENY do thiếu workload permission. |
| R32 | Owner service principal đã Leaver, quyền vault cũ còn. | Thu hồi quyền người cũ; đánh giá rotation. |
| R33 | Event Mover cũ được phát lại sau Leaver. | Không tái cấp role/attribute cũ. |
| R34 | Một PEP vùng B vẫn cache ALLOW sau vùng A đã DENY. | Fail nếu quá SLA, ghi region-specific evidence. |
| R35 | Request DENY vì API downtime (503). | Không được tính PASS về authorization. |
| R36 | Account rehire có email cũ nhưng subject khác. | Không gán nhầm account/quyền lịch sử. |
| R37 | Resource đổi owner giữa kiểm quyền và commit. | Bảo vệ TOCTOU theo contract. |
| R38 | Policy file trong Git đúng, deployment thực tế khác. | Detect configuration drift. |
| R39 | Reviewer xác nhận KEEP nhưng tài nguyên đã classified cao hơn. | Yêu cầu đánh giá lại quyết định và policy. |
| R40 | Reviewer chọn REVOKE nhưng connector báo success còn quyền thật. | Chưa VERIFIED; có remediation và readback. |

### Phương pháp thực hiện

1. Định nghĩa **expected decision** độc lập từ business policy đã duyệt.
2. Tạo fixture với ít nhất hai tenant, hai principal, resource hợp lệ và resource ngoài quyền.
3. Kiểm positive control để chắc chắn endpoint hoạt động.
4. Thay đổi từng attribute, role, resource state hoặc environment theo test case.
5. Kiểm cả **PDP decision, HTTP/body, database, event/job và log** tùy loại hành động.
6. Với JML, giữ token/session cũ để thử đường truy cập tồn dư.
7. Lưu evidence, policy version, PIP revision và timestamp; không dùng credential thật trong artifact.

**HTTP 403 hay 404** có thể cùng phù hợp với contract che giấu resource; một số API cần tránh tiết lộ đối tượng tồn tại. Điều cốt lõi là **không trả dữ liệu và không thực hiện side effect trái quyền**.

## 21. Ví dụ policy-as-code với OPA/Rego

Một tổ chức có thể dùng **Open Policy Agent (OPA)** hoặc policy engine khác. Đoạn Rego sau chỉ nhằm minh họa việc tách luật khỏi controller; việc chạy thực cần cấu hình runtime, version và integration tương ứng:

~~~rego
package finance.invoice

import rego.v1

default allow := false

allow if {
    input.action == "invoice.read"
    input.subject.employmentStatus == "ACTIVE"
    input.subject.department == "FINANCE"
    "FINANCE_INVOICE_READER" in input.subject.roles
    input.subject.tenantId == input.resource.tenantId
    input.resource.status == "APPROVED"
}
~~~

**Đây là policy tối giản**: nó chỉ bao gồm những điều kiện được nêu và **chưa** kiểm classification, authentication assurance, data masking, SoD hoặc delegated access. Nếu policy nghiệp vụ có các điều kiện đó, phải bổ sung rule và tests tương ứng trước khi đưa vào môi trường thật.

Ví dụ input dùng khi kiểm thử:

~~~json
{
  "action": "invoice.read",
  "subject": {
    "subjectId": "test-person-4821",
    "employmentStatus": "ACTIVE",
    "department": "FINANCE",
    "tenantId": "tenant-a",
    "roles": ["FINANCE_INVOICE_READER"]
  },
  "resource": {
    "id": "test-invoice-100",
    "tenantId": "tenant-a",
    "status": "APPROVED"
  }
}
~~~

Kỳ vọng rule minh họa trả **allow=true**. Thay resource.tenantId thành tenant-b hoặc employmentStatus thành LEAVER thì **allow=false**.

### Lưu ý đặc biệt khi dùng OPA

- Một input hợp lệ về JSON nhưng chứa thuộc tính **do browser tự khai** không trở thành đáng tin chỉ vì OPA đã đánh giá.
- PEP phải tạo input từ **verified identity + trusted PIP + resource thật**, không từ role/tenant tùy ý trong body.
- Đảm bảo chính sách triển khai đúng version ở các instance; cần công cụ deployment/reconciliation riêng.
- Test **deny-by-default, missing attributes và conflict semantics**, không chỉ happy path.
- Kết quả policy engine trả PERMIT nhưng controller không kiểm resource ownership hoặc bỏ qua PEP vẫn có thể là lỗi nghiêm trọng.
- OPA/Rego không tự xử lý provisioning, SCIM hoặc revoke JWT; IAM cần vòng đời riêng.

## 22. Java pseudocode: điều phối một ABAC review

Ví dụ Java dưới đây **không phải API thực của thư viện IAM**, mà minh họa cách tách **expected state** khỏi **observed state** và yêu cầu bằng chứng độc lập.

~~~java
// Pseudocode, không phải mã production-ready.
ReviewReport reviewAbac(ApprovedReviewScope scope) {
    policyGovernance.assertApprovedScope(scope);

    // Expected được lấy từ business policy + HRIS/IGA hiện hành,
    // không sử dụng cùng một hàm runtime PDP làm oracle duy nhất.
    WorkforceSnapshot workforce = hris.currentTrustedSnapshot();
    DesiredAccess desired = iga.calculateDesiredAccess(workforce, scope);
    PolicyBaseline baseline = policyRegistry.approvedPolicy(scope.policyId());

    ReviewReport report = new ReviewReport(scope.reviewId());

    for (TargetPep target : scope.mandatoryTargets()) {
        try {
            DeployedPolicy deployed = target.readDeployedPolicy();
            TrustedAttributeSnapshot attributes =
                attributeCatalog.readWithSourceRevision(target);

            if (!baseline.compatibleWith(deployed)) {
                report.markDrift(target.id(), "policy_version_mismatch");
                continue;
            }
            if (!attributes.isWithinApprovedFreshness()) {
                report.markBlocked(target.id(), "stale_attributes");
                continue;
            }

            // Các probe được phép, không phá hoại, có positive control.
            DecisionTestResult tests = authzTester.runApprovedMatrix(
                target, desired, baseline, attributes
            );

            EffectiveAccessSnapshot actual = target.readEffectiveAccess();
            if (tests.allMandatoryCasesPassed()
                    && desired.matchesApprovedEffectiveAccess(actual)) {
                report.markVerified(target.id(), tests.evidenceRefs());
            } else {
                report.markRemediationRequired(
                    target.id(), tests.safeMismatchSummary()
                );
            }
        } catch (TargetUnavailableException ex) {
            report.markUnverified(target.id(), "target_unavailable");
        }
    }

    if (report.allMandatoryTargetsVerified()
            && !report.hasUnapprovedResidualAccess()) {
        report.markVerifiedAt(clock.now());
    }

    auditStore.persistMetadataWithoutSecrets(report);
    return report;
}
~~~

Trong production cần mô hình hóa rõ:

- **Policy baseline độc lập** được business/data owner phê duyệt.
- **Source revision** và thời điểm lấy thuộc tính để tránh so snapshot không đồng nhất.
- **PEP target coverage** gồm API, batch, export, admin và các đường ngoài SSO nếu thuộc scope.
- **Kiểm thử không phá hoại**, sử dụng dữ liệu tổng hợp và kiểm no-side-effects.
- **Readback tại target** và trạng thái UNVERIFIED khi thiếu khả năng quan sát.
- **Ràng buộc JML** với effectiveAt, current HR state, event version, session/token và SCIM.
- **Exception governance** không tự cho phép đóng VERIFIED khi tồn dư ngoài baseline.

### Phân biệt lỗi policy với lỗi kỹ thuật

Một test nhận lỗi 503 vì target down phải ghi **UNVERIFIED/TARGET_UNAVAILABLE**, không được ghi “DENY đúng policy”. Ngược lại, PDP trả DENY trong khi API vẫn thực hiện ghi dữ liệu là lỗi **enforcement** dù log PDP trông đúng.

## 23. Tình huống thực hành: rà soát ABAC sau Mover và Leaver

### Bối cảnh

Công ty có hai ứng dụng: **Sales CRM** và **Finance Portal**. Nhân viên **Minh** thuộc Sales, được xem khách hàng tenant VN theo quy định về owner/project. Một tuần sau, Minh chuyển sang Finance và được cấp quyền đọc hóa đơn đã duyệt. Nhà thầu **Bình** làm trong dự án Sales có hợp đồng hết hạn cùng ngày.

Kiến trúc sử dụng HRIS/contract registry, IGA, IdP/SSO, SCIM và API gateway có PDP đánh giá ABAC. Một số tài liệu được chia sẻ trực tiếp bằng ACL; CRM giữ session cục bộ; job report-generator có quyền đọc dữ liệu tổng hợp.

### Bước 1 – Thu policy và xác định oracle

Business owner phê duyệt mục tiêu:

~~~text
Minh sau Mover:
  ALLOW Finance.Invoice.Read
    khi ACTIVE, department=Finance, tenant=VN,
    invoice=APPROVED, clearance phù hợp.
  DENY Sales.Customer.Read/Export
    ngoại trừ grant bàn giao có hạn và phê duyệt cụ thể.
  DENY Finance.Payment.Approve
    vì không có nhiệm vụ và role Approver.

Bình sau contract expiry:
  DENY Sales.Customer.Read/Export và mọi API theo quan hệ cũ.

report-generator:
  ALLOW Summary.Read theo workload policy và tenant VN.
  DENY Payment.Approve, GlobalAdmin và tenant khác.
~~~

Những điều kiện ở đây là **giả định của tình huống đào tạo**. Một hệ thống thực cần dùng policies/approvals cụ thể làm oracle.

### Bước 2 – Kiểm nguồn thuộc tính

Reviewer xác nhận:

- Minh có subjectId ổn định; HRIS đã chuyển department=Finance với revision hợp lệ.
- Bình có contractor status=EXPIRED và effectiveAt đã đến.
- IdP và PIP có trạng thái mới; SCIM target ID ánh xạ đúng người.
- Finance invoices có tenant/classification/status từ database, không nhận từ browser.
- Rule ngoại lệ bàn giao nếu có ghi approver, scope và expiry.

**Phát hiện thứ nhất:** API gateway đã có policy Finance mới, nhưng một instance CRM giữ cache department=Sales từ trước sự kiện Mover.

### Bước 3 – Kiểm effective access qua API và ACL

Chạy test không phá hoại:

| Probe | Expected | Observed lần đầu | Kết luận |
| --- | --- | --- | --- |
| Minh đọc invoice APPROVED tenant VN. | ALLOW | ALLOW | Đúng. |
| Minh đọc invoice tenant khác. | DENY | DENY | Đúng tenant isolation. |
| Minh gọi CRM export bằng token cũ. | DENY | ALLOW | **Sai lệch nguy cơ cao.** |
| Minh đọc folder Sales direct share. | DENY | ALLOW | **ACL tồn dư.** |
| Minh approve payment. | DENY | DENY | Đúng action. |
| Bình dùng session CRM cũ sau hết hạn. | DENY | ALLOW | **Chưa deprovision đầy đủ.** |
| report-generator đọc summary tenant VN. | ALLOW | ALLOW | Workload đúng quyền. |
| report-generator đọc tenant khác. | DENY | DENY | Đúng workload isolation. |

Một đợt review chỉ xem policy trong Git sẽ bỏ sót cả **CRM cache**, **direct ACL** và **session của nhà thầu**.

### Bước 4 – Khắc phục

1. Cập nhật/invalidate CRM entitlement cache theo thiết kế và xác nhận PIP nhận đúng revision.
2. Gỡ direct ACL Sales của Minh hoặc chuyển thành ngoại lệ có hạn nếu business owner thật sự phê duyệt.
3. Vô hiệu hóa tài khoản Bình, xử lý SCIM/IdP session và local CRM session theo khả năng; revoke token/grant liên quan.
4. Đánh giá personal API keys, secrets và quyền với service account mà Minh/Bình từng sở hữu.
5. Kiểm policy phiên bản thực tế ở tất cả API instances và export workers.
6. Chặn grant/event cũ tái áp quyền từ trạng thái trước Mover/Leaver.

### Bước 5 – Kiểm tra lại

Chạy lại các positive/negative probes, ghi timestamp và **reason code**. Chỉ khi mọi đường bắt buộc đã DENY/ALLOW đúng theo scope mới có thể đánh dấu VERIFIED. Nếu app không có khả năng readback session/token, ghi **coverage gap** và escalated owner thay vì tự gán PASS.

### Bước 6 – Chứng nhận và theo dõi

Finance owner xác nhận Minh cần quyền đọc hóa đơn, Sales owner xác nhận không còn nhu cầu export, IAM/security xác nhận kết quả kỹ thuật. Lưu policy version, source revision, evidence references và các khoảng thời gian quyền tồn dư để cải thiện SLA.

**Bài học:** rà soát ABAC là hoạt động đồng thời của **quản trị nghiệp vụ, chất lượng thuộc tính và kiểm chứng kỹ thuật**. Không thể tách hoàn toàn khỏi JML, token/session, provisioning và các grant nằm ngoài chính sách ABAC chính.

## 24. Quản trị thay đổi policy sau kết quả review

Khi review phát hiện rule quá rộng, không nên sửa trực tiếp trên production mà không có kiểm soát; có thể làm gián đoạn tác vụ hợp lệ hoặc mở quyền mới.

~~~mermaid
flowchart TD
    I["ABAC review phát hiện drift / policy defect"] --> A["Business owner phê duyệt desired decision"]
    A --> D["Thay policy / thuộc tính / PEP implementation"]
    D --> T["Unit + policy simulation + integration tests"]
    T --> C["Canary / shadow evaluation theo scope"]
    C --> R{"Expected decisions khớp?"}
    R -->|Không| X["Sửa hoặc rollback có kiểm soát"]
    X --> T
    R -->|Có| P["Triển khai policy version được duyệt"]
    P --> V["Readback phiên bản + effective-access verification"]
    V --> E["Audit + theo dõi false allow/false deny"]
~~~

### Kiểm tra trước khi deploy

- **Policy diff** nêu rõ allow mới, deny mới, các resource/tenant bị ảnh hưởng.
- **Test oracle** được business owner phê duyệt độc lập với code.
- **Regression tests** có case BOLA, BFLA, SoD, missing attributes và JML.
- **Shadow evaluation**, nếu có, chỉ dùng để so quyết định và không tự tạo quyền thực tế.
- **Canary** với test principals/tenant phù hợp, không dùng dữ liệu khách hàng thật.
- **Rollback** có version, quy trình phê duyệt và điều kiện không tái mở lỗi bảo mật đã khắc phục.
- **Approval & sign-off** cho quyền nhạy cảm và policy có ảnh hưởng rộng.

### Cảnh báo về shadow mode

Trong **shadow mode**, policy mới có thể tính quyết định giả lập nhưng chưa thực thi. Một kết quả “policy mới sẽ DENY” chỉ là **dự báo**, không chứng minh production PEP đã chặn. Sau deploy vẫn cần **đọc lại phiên bản và test truy cập thực**.

### Không rollback vô điều kiện

Nếu policy mới được triển khai để chặn một lỗ hổng, rollback về policy cũ có thể mở lại đường tấn công. Kế hoạch khôi phục phải có phương án **giới hạn phạm vi, feature flag được kiểm soát hoặc chặn thêm ở PEP** thay vì tự trả về trạng thái kém an toàn khi có lỗi vận hành.

## 25. Bảo vệ quyền riêng tư, audit và KPI

ABAC sử dụng nhiều thuộc tính cá nhân và bối cảnh. **Review không phải giấy phép thu thập vô hạn dữ liệu** về người dùng, thiết bị hoặc vị trí.

### Quy tắc bảo vệ dữ liệu

1. Chỉ dùng các thuộc tính cần thiết để ra quyết định và giải thích policy.
2. Mỗi attribute cần có **owner, purpose, độ chính xác, TTL và retention**.
3. Không dùng dữ liệu nhạy cảm làm chính sách nếu chưa có căn cứ pháp lý/nghiệp vụ, kiểm soát bảo vệ và phê duyệt cần thiết.
4. Hạn chế người xem evidence, tránh lưu toàn bộ hồ sơ HR/resource payload trong log.
5. Tách quyền quản trị policy, quyền sửa nguồn thuộc tính và quyền phê duyệt exception.
6. Xem xét bias/false deny nếu tín hiệu ngữ cảnh không đáng tin hoặc không phù hợp với người dùng có nhu cầu trợ năng.
7. Khi dùng location/device signals, phải đánh giá **độ chính xác và mục đích**, không biến một tín hiệu yếu thành bằng chứng tuyệt đối.

### Metrics có ý nghĩa

| KPI | Cách hiểu | Không nên nhầm với |
| --- | --- | --- |
| **Review coverage** | Tỷ lệ policy/PEP/target thuộc scope có bằng chứng đầy đủ. | Tỷ lệ reviewer đã mở email. |
| **Certification completion** | Tỷ lệ quyết định KEEP/REVOKE/CHANGE được owner xác nhận. | Quyền đã bị thu hồi thực tế. |
| **Attribute freshness compliance** | Tỷ lệ thuộc tính đủ mới theo SLA khi PDP quyết định. | Chỉ có giá trị thuộc tính khác null. |
| **Policy drift count** | Sai lệch giữa policy được duyệt và bản triển khai. | Số dòng code thay đổi. |
| **Effective-access mismatch** | Số kết quả thực tế không khớp quyết định mong đợi. | Số lượng policy tổng cộng. |
| **Residual privilege count** | Số quyền ngoài desired state còn dùng được sau JML. | Số account đã gửi lệnh disable. |
| **Revocation latency** | Thời gian từ mốc hiệu lực đến verified DENY. | Thời gian connector trả HTTP 200. |
| **Exception aging** | Quyền tạm còn mở/quá hạn so với chính sách. | Số exception được tạo. |
| **False deny impact** | Tác vụ hợp lệ bị chặn sai, ảnh hưởng vận hành. | Mặc định ALLOW khi không chắc chắn. |
| **Service principal coverage** | Workloads có owner, scope, trust và review hợp lệ. | Chỉ đếm service accounts trong directory. |

Không tối ưu một KPI bằng cách bỏ các trường hợp không xác minh được. **Coverage gap phải nằm trong báo cáo**; nếu không sẽ tạo cảm giác an toàn giả.

## 26. Những sai lầm thường gặp khi rà soát ABAC

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Duyệt policy bằng cách đọc tên rule. | Không thấy thuộc tính sai hoặc PEP bypass. | Review cả data lineage, tests và effective access. |
| Coi department trong JWT luôn là hiện hành. | Mover còn quyền cũ qua token/session. | Dùng freshness/revocation/current state phù hợp. |
| Dùng email làm khóa identity duy nhất. | Link sai người khi đổi email/rehire. | Stable subject ID và mapping theo nguồn tin cậy. |
| Tin tenantId do client gửi. | Cross-tenant access. | Tenant của resource và principal từ backend/PIP đáng tin. |
| Mặc định classification rỗng là PUBLIC. | Dữ liệu nhạy cảm bị mở khi thiếu nhãn. | Fail-safe và remediation cho missing labels. |
| Review mỗi RBAC group. | Direct ACL/ReBAC/delegation còn hiệu lực. | Đánh giá mọi đường grant liên quan. |
| Coi SCIM 204 là quyền đã thu hồi. | Session/API key vẫn hoạt động. | Readback và probe effective access. |
| Chỉ test policy unit, không test API. | Endpoint thiếu PEP vẫn cho quyền. | Integration/security tests và no-side-effects. |
| Chấp nhận HTTP 503 như DENY. | Hạ tầng lỗi bị nhầm kết quả authorization. | Positive control và audit decision. |
| Cho phép khi PIP/PDP timeout. | Fail-open ở tài nguyên nhạy cảm. | Fallback bảo vệ và fault tests. |
| Cho exception không có expiry. | Quyền tạm trở thành quyền lâu dài. | TTL, owner, phê duyệt, auto-revoke và recheck. |
| Để reviewer tự duyệt grant của mình. | Thiếu độc lập và tăng rủi ro đặc quyền. | SoD và approval tách biệt. |
| Không xét service account. | Credential/workload quyền cao không được rà soát. | Inventory owner/trust/scope và secret lifecycle. |
| Bỏ qua event thứ tự đảo. | Leaver có thể bị tái cấp quyền. | Revision, idempotency, current HR state và test replay. |
| Chỉ đo policy deployment success. | Drift hiệu lực chưa được phát hiện. | Measure verified decisions ở PEP/target. |
| Shadow policy báo đúng thì chốt VERIFIED. | Production chưa áp quyết định mới. | Verify readback và live PEP probes. |

## 27. Checklist hoàn tất đợt rà soát ABAC

Trước khi đóng review, người phụ trách kiểm các điều kiện sau:

1. **Scope rõ ràng:** tài nguyên, actions, tenants, applications, PEP, user/workload groups và thời gian review đã định nghĩa.
2. **Policy baseline đúng:** policy ID, version, owner, approval, combining rule và default behavior đã xác minh.
3. **Attribute inventory:** mỗi thuộc tính bắt buộc có nguồn có thẩm quyền, steward, mapping, validity và SLA.
4. **JML current state:** HRIS/IGA hiện hành đã được dùng, không chỉ bản sao từ token/session cũ.
5. **Resource quality:** tenant, classification, owner và workflow status không bị client tự khai/override.
6. **Tính hiệu lực quyền:** RBAC groups, direct ACL, ReBAC, delegation, grants và local SaaS permissions trong scope đã được đối soát.
7. **Positive controls:** các tác vụ hợp lệ không bị false deny ngoài chính sách.
8. **Negative tests:** cross-tenant, cross-owner, thiếu role, sai classification, SoD, stale attributes và Leaver đều bị chặn.
9. **PEP coverage:** API chính, admin endpoints, export/bulk/async workers và routes khác cần thiết đều thực thi rule.
10. **Fault semantics:** PIP/PDP timeout, data thiếu, cache stale hoặc policy conflict có hành vi fail-safe.
11. **Token/session:** quyền cũ qua SSO session, refresh/access token hoặc local token đã được xử lý theo SLA.
12. **SCIM/reconciliation:** account, group/role được đọc lại, không chỉ dựa vào response success.
13. **Service identities:** principal, owner, workload scope, credential và quyền gián tiếp đã được rà soát.
14. **Exceptions:** có scope, approval, expiry, kiểm soát bù trừ và trạng thái riêng.
15. **Remediation:** sai lệch đã sửa, có probe xác nhận; còn gap có owner, deadline, risk.
16. **Audit:** evidence đầy đủ, policy/source revision, timestamp/correlation, không lộ secret.
17. **Đóng hồ sơ:** chỉ chốt VERIFIED khi **toàn bộ target bắt buộc** có bằng chứng; chưa rõ phải báo UNVERIFIED/BLOCKED.

Khi có rủi ro đang hoạt động, **đừng đợi đủ chữ ký review định kỳ mới chặn quyền trái phép**. Áp biện pháp bảo vệ được phê duyệt và tiếp tục điều tra, rồi chứng nhận sau khi có bằng chứng kỹ thuật.

## 28. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao review ABAC không thể chỉ đọc nội dung rule và kiểm syntax?

**Trả lời:** Vì rule có thể đúng nhưng PIP cung cấp thuộc tính sai/cũ, PEP không thực thi, cache còn ALLOW hoặc direct ACL cấp quyền độc lập. Phải kiểm cả dữ liệu, triển khai và effective access.

**Câu 2.** Tại sao department=Finance trong một request body không đủ để áp policy Finance?

**Trả lời:** Client có thể tự khai hoặc sửa giá trị. Thuộc tính có ảnh hưởng quyền phải đến từ nguồn tin cậy như HRIS/IGA/IdP/PIP và được liên kết với subject đã xác minh.

**Câu 3.** Một người đã rời công ty nhưng có JWT access token còn hạn. Chính sách ABAC employmentStatus=ACTIVE có tự chặn ngay không?

**Trả lời:** Không mặc định nếu API chỉ dùng claim ACTIVE cũ trong token. Cần cơ chế cập nhật trạng thái, kiểm quyền hiện hành, token revocation/TTL hoặc giải pháp tương ứng theo SLA.

**Câu 4.** Vì sao business owner đã nhấn REVOKE không đủ để đóng review?

**Trả lời:** REVOKE là quyết định quản trị. Cần thực thi ở IdP/IGA/SCIM/ứng dụng và readback hoặc kiểm quyền thực tế để xác nhận trạng thái VERIFIED.

**Câu 5.** Nếu thiếu classification của resource, có thể coi là PUBLIC để tránh làm gián đoạn không?

**Trả lời:** Không nên mặc định cho phép. Phải áp hành vi fail-safe theo policy và xử lý dữ liệu thiếu; nếu phân loại không đáng tin thì không có cơ sở an toàn để mở dữ liệu nhạy cảm.

**Câu 6.** ABAC có thay thế hoàn toàn RBAC và ACL không?

**Trả lời:** Không nhất thiết. Nhiều hệ thống kết hợp role, thuộc tính và ACL/quan hệ. Review cần đánh giá quyết định cuối cùng từ các nguồn cấp/deny có thể ảnh hưởng quyền.

**Câu 7.** Khi Mover sang vai trò mới, vì sao phải kiểm cả ALLOW và DENY?

**Trả lời:** Cần chắc chắn quyền mới hợp lệ vẫn hoạt động, đồng thời quyền cũ không còn. Chỉ DENY mọi request có thể là lỗi vận hành, còn chỉ ALLOW quyền mới có thể che giấu quyền tồn dư.

**Câu 8.** Service account không có department như nhân viên. Làm sao review?

**Trả lời:** Dùng policy workload với các thuộc tính đáng tin như workload identity, issuer, environment, owner, tenant, audience và scope. Không tự giả lập service thành nhân viên hay cho qua kiểm quyền.

**Câu 9.** Vì sao PEP trả HTTP 503 không thể tính như negative test PASS?

**Trả lời:** HTTP 503 thể hiện vấn đề khả dụng, không chứng minh rule authorization đã được áp. Cần positive control và bằng chứng policy decision/no-side-effects.

**Câu 10.** Ngoại lệ được phê duyệt có nghĩa toàn bộ quyền cũ đã thu hồi chưa?

**Trả lời:** Không. Ngoại lệ cho phép một phạm vi tạm có thời hạn. Cần ghi riêng quyền còn hiệu lực, owner, expiry và xác minh tự thu hồi sau khi hết hạn.

**Câu 11.** Khi policy mới chạy ở shadow mode và trả DENY đúng, có thể báo production đã an toàn chưa?

**Trả lời:** Chưa. Shadow chỉ mô phỏng quyết định. Cần triển khai, đọc lại version và kiểm quyền tại PEP thực đang phục vụ request.

**Câu 12.** Một đợt rà soát ABAC hoàn tất cần có những loại bằng chứng nào?

**Trả lời:** Baseline policy đã duyệt, attribute provenance/freshness, desired access từ nguồn JML, decision matrix, effective-access readback/probes, reviewer decisions, remediation/exception, timestamp và audit an toàn không lộ credential.

---

**Ghi nhớ:** **Rà soát ABAC là kiểm chứng rằng chính sách dựa trên thuộc tính vẫn đúng và đang thực sự bảo vệ tài nguyên**, không chỉ kiểm tra file rule hoặc danh sách nhóm. Phải xem **nguồn và độ mới thuộc tính, PDP/PEP, cách kết hợp RBAC/ABAC/ACL, session/token, service account, ngoại lệ và quyền thực tế sau Joiner–Mover–Leaver**. Rà soát chỉ đáng tin khi có cả **quyết định nghiệp vụ của người có thẩm quyền** lẫn **bằng chứng kỹ thuật tại điểm thực thi**, giúp phát hiện và loại bỏ **quyền truy cập tồn dư** theo SLA.
