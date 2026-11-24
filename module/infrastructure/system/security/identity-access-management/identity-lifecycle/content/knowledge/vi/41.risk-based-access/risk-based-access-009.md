# Risk threshold trong Risk-based Access: thiết kế ngưỡng rủi ro để quyết định quyền truy cập

## 1. Risk threshold là gì?

Trong **Risk-based Access Control** (kiểm soát truy cập dựa trên rủi ro), **risk threshold** là **ngưỡng hoặc tập ngưỡng được chính sách quy định** để chuyển kết quả đánh giá rủi ro thành hành động kiểm soát, chẳng hạn **ALLOW sau khi đáp ứng các điều kiện thông thường**, **STEP_UP**, **RESTRICT**, **DENY** hoặc **REQUIRE_REVIEW**. Ngưỡng có thể dựa trên điểm số, mức phân loại định tính, các rule bắt buộc hoặc tổ hợp của chúng.

Ví dụ một mô hình nội bộ chấm risk từ **0 đến 100**: dưới 30 được xem là thấp; từ 30 đến dưới 60 là trung bình; từ 60 đến dưới 85 là cao; từ 85 trở lên là nghiêm trọng. Một lượt đăng nhập với điểm 55 có thể được yêu cầu MFA bổ sung, trong khi yêu cầu thay chính sách IAM với cùng điểm 55 có thể bị chặn vì tính nhạy cảm của hành động.

**Risk threshold không tự là quyền truy cập.** Một user không có role đọc dữ liệu tài chính vẫn bị từ chối dù risk score bằng 0. Một nhân viên đã **Leaver** không được quay lại làm việc chỉ vì IP quen thuộc làm giảm điểm rủi ro. Ngưỡng rủi ro là **một lớp quyết định bổ sung**, phải hoạt động cùng **authentication, authorization, entitlement, tenant isolation, SoD, token policy** và trạng thái vòng đời danh tính.

Trong module **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, chủ đề gắn với **Joiner–Mover–Leaver (JML)**, xác minh danh tính, cấp và thu hồi quyền, **IdP/SSO/MFA, SCIM, RBAC/ABAC/PBAC, service/workload accounts, audit** và mục tiêu loại bỏ **quyền truy cập tồn dư**.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Định nghĩa risk score, threshold, risk band, policy outcome và hard deny.
2. Thiết kế các ngưỡng với ranh giới chính xác và hành động tương ứng.
3. Chọn tín hiệu rủi ro đủ tin cậy, đủ mới, có nguồn gốc rõ ràng.
4. Phân biệt rủi ro **đăng nhập, phiên, giao dịch, tài nguyên, thiết bị và workload**.
5. Đặt ngưỡng theo độ nhạy tài nguyên thay vì áp một con số cho mọi yêu cầu.
6. Xử lý **UNKNOWN/INDETERMINATE**, dữ liệu lỗi, scoring service outage và risk override.
7. Liên kết threshold với MFA step-up, Conditional Access, JIT/PAM và resource authorization.
8. Hiệu chỉnh ngưỡng, đo false positive/false negative và drift.
9. Kiểm soát thay đổi ngưỡng qua governance, audit và kiểm thử.
10. Xác minh các quyền đã bị thu hồi khi danh tính hoặc ngữ cảnh thay đổi.

## 2. Ngưỡng rủi ro trả lời câu hỏi gì?

Một policy có thể chia việc quyết định truy cập thành ba lớp:

| Lớp | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Eligibility / hard controls** | Chủ thể có được phép xét cấp quyền hay không? | Employee active; tenant khớp; không có explicit deny |
| **Base authorization** | Chủ thể có quyền thực hiện action trên resource không? | Role BillingReader cho hóa đơn thuộc org-a |
| **Risk threshold decision** | Trong ngữ cảnh hiện tại, phải tăng cường hoặc hạn chế gì? | MFA step-up, deny export, session review |

Ví dụ một API được gọi bằng token hợp lệ và role đúng, nhưng từ thiết bị đã báo mất. **Đúng role không đồng nghĩa được truy cập**; một **hard deny do device bị revoke** phải thắng quyết định ALLOW từ điểm số thấp.

Ngược lại, một request có score cao chưa đủ để xác định **người dùng gian lận**. Điểm số cao là **tín hiệu để kích hoạt kiểm soát hoặc điều tra**, không phải lời kết tội; phần lớn hệ thống risk score có thể bị sai số, lệch dữ liệu hoặc gặp tình huống mới.

## 3. Phân biệt risk signal, score, band và threshold

| Thuật ngữ | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Risk signal** | Dữ liệu đầu vào phản ánh một khía cạnh của nguy cơ | Device posture, IP reputation, impossible travel |
| **Risk feature** | Dữ liệu đã chuẩn hóa từ một hoặc nhiều tín hiệu | NewDevice=true, sessionAgeMinutes=180 |
| **Risk score** | Giá trị tổng hợp theo mô hình hoặc rules | 67/100 |
| **Risk band** | Nhóm ngữ nghĩa của score | HIGH |
| **Risk threshold** | Mốc phân chia band hoặc hành động | Step-up khi score >= 30 |
| **Risk appetite/tolerance** | Mức rủi ro được tổ chức chấp nhận | Admin API không chấp nhận rủi ro HIGH |
| **Policy outcome** | Hành động sau đánh giá | STEP_UP, RESTRICT, DENY |
| **Risk override / exception** | Ngoại lệ đã được kiểm soát theo policy | JIT grant có phê duyệt, không vượt hard deny |
| **Control effectiveness** | Kiểm soát được thực thi và có bằng chứng hay không | API Deny thực sự sau khi risk đổi |

**Risk score không mặc nhiên là xác suất gian lận.** Điểm 80/100 của một mô hình heuristic không có nghĩa **80% khả năng bị tấn công**. Chỉ có thể diễn giải như xác suất nếu mô hình đã được **calibrate** và kiểm định đúng cho outcome, population và khoảng thời gian liên quan.

## 4. Vì sao không nên dùng một ngưỡng cố định cho mọi tài nguyên?

Tác động của một hành động phụ thuộc tài nguyên:

| Resource/action | Mức nhạy cảm thường gặp | Kỳ vọng kiểm soát |
| --- | --- | --- |
| Xem trang trợ giúp công khai | Rất thấp | Có thể không yêu cầu token |
| Đọc profile nội bộ ít nhạy cảm | Thấp/trung bình | Authentication và quyền đúng |
| Đọc dữ liệu khách hàng | Cao | Device/assurance checks theo policy |
| Export hàng loạt dữ liệu cá nhân | Rất cao | Fresh authorization, step-up, volume controls |
| Tạo API key hay refresh grant lâu hạn | Cao | MFA/approval và hạn chế phạm vi |
| Sửa IAM policy hoặc cấp OrgAdmin | Rất cao | JIT/PAM, SoD, hard restrictions |
| Khôi phục backup production | Cao nhưng có yêu cầu sẵn sàng | Emergency playbook độc lập và audit |

**Một risk score bằng nhau có thể dẫn đến outcome khác nhau**: đọc báo cáo ít nhạy cảm được step-up; xuất toàn bộ dữ liệu nhạy cảm bị deny; kiểm tra health không cần tăng friction.

Đặt threshold theo **resource classification, action, environment, principal type và risk policy**, nhưng không biến các ngưỡng thành tập ngoại lệ tùy hứng khó kiểm toán.

## 5. Ví dụ risk band với ranh giới được định nghĩa chính xác

Giả sử score là số **thực hữu hạn trong khoảng 0–100**. Một policy minh họa:

| Khoảng score | Risk band | Xử lý gợi ý sau base authorization |
| --- | --- | --- |
| **0 ≤ score < 30** | LOW | ALLOW nếu mọi điều kiện bắt buộc đạt |
| **30 ≤ score < 60** | MEDIUM | STEP_UP/thiết bị kiểm tra lại cho resource được yêu cầu |
| **60 ≤ score < 85** | HIGH | RESTRICT hoặc DENY theo sensitivity và action |
| **85 ≤ score ≤ 100** | CRITICAL | DENY hành động nhạy cảm; gửi cảnh báo/điều tra theo policy |
| **UNKNOWN/không hợp lệ** | INDETERMINATE | Không tự coi là LOW; xử lý fail-safe theo risk |

**Đây là số liệu minh họa, không phải chuẩn của OAuth, NIST hay một IdP nào.** Các con số phải được hiệu chỉnh theo môi trường và mục tiêu đo. Một hệ thống có thể chọn 3 band, 5 band hoặc rule engine thay vì số 0–100.

Ranh giới phải thống nhất giữa frontend, gateway, PDP và backend: **30 thuộc MEDIUM, 60 thuộc HIGH, 85 thuộc CRITICAL**. Cần kiểm cả **0, 29.999, 30, 59.999, 60, 84.999, 85, 100** để tránh lỗi off-by-one.

## 6. Risk threshold không thể ghi đè hard deny

**Hard deny** là điều kiện cấm theo chính sách không được bỏ qua bằng cách có score thấp hoặc MFA mới thành công.

| Hard control | Ví dụ | Vì sao không chỉ dựa score? |
| --- | --- | --- |
| **Account/relation inactive** | Employee đã Leaver | Không còn căn cứ truy cập |
| **No entitlement** | Không có BillingApprover | Không có quyền cơ sở |
| **Tenant boundary** | org-a token đọc org-b resource | Ngăn cross-tenant leakage |
| **Explicit deny/SoD** | Người tạo không được duyệt cùng invoice | Quy tắc nghiệp vụ bắt buộc |
| **Compromised/revoked credential** | Token/grant/key đã bị revoke | Credential không còn tin cậy |
| **Suspended/lost device** | Device đã báo mất | Không được dùng trust cũ tùy policy |
| **Expired JIT lease** | PAM grant đã hết hạn | Hết thời gian nâng quyền |
| **Resource legal/policy restriction** | Dữ liệu bị chặn theo phân loại | Không được hợp thức hóa bằng điểm số |

Điểm 5/100 chỉ có thể dẫn tới ALLOW **sau khi** các lớp authorization bắt buộc đều đạt. **STEP_UP thành công cũng không tự cấp role mới, không thay approval của resource owner và không hóa giải SoD**.

## 7. Những yếu tố cấu thành một risk score

Tín hiệu có thể đến từ nhiều lớp:

| Nhóm tín hiệu | Ví dụ | Lưu ý về nguồn/độ tin cậy |
| --- | --- | --- |
| **Identity** | User risk, account state, enrollment/recovery history | Nguồn IdP/HRIS có thẩm quyền theo field |
| **Authentication** | MFA method, phishing-resistant factor, failed attempts | Không tin claim assurance tự khai từ client |
| **Session** | Session age, reauthentication age, refresh reuse | Token mới không tự chứng minh user mới MFA |
| **Device** | Managed enrollment, compliance, attestation, lost state | Cần device ID/assessment timestamp đáng tin |
| **Network** | IP reputation, ASN, TOR/proxy indicators | VPN/NAT/proxy có thể gây false positive |
| **Geo/behavior** | Di chuyển bất thường, giờ truy cập, chuỗi hành động | Không suy chắc malicious chỉ từ vị trí/IP |
| **Resource/action** | Privileged action, export size, data classification | Nhiều khi là yếu tố impact hơn là threat likelihood |
| **Workload** | Issuer/subject/audience, CI/CD environment, secret age | M2M không có human MFA tương đương |
| **Threat intelligence** | Credential leak indicator, known abuse | Cần freshness, false positive handling |
| **Operational state** | Incident, compromised service, monitoring outage | Không biến outage thành lý do ALLOW_ALL |

**Không phải mọi hệ thống nên thu thập mọi tín hiệu**. Phải chọn những tín hiệu có căn cứ, độ chính xác, sự cần thiết và quyền riêng tư phù hợp với mục tiêu kiểm soát.

## 8. Provenance, freshness và confidence của tín hiệu

Một bản ghi điểm rủi ro thiếu thông tin nguồn dễ tạo **false assurance**. Cần ghi:

- **sourceSystem và sourceAuthority** theo từng loại dữ liệu.
- **observedAt, assessedAt, receivedAt và expiresAt/TTL**.
- **signalVersion/modelVersion** và cách diễn giải giá trị.
- **confidence/quality flag** nếu nguồn cung cấp hoặc tổ chức đánh giá có căn cứ.
- **tenantId, identityId/deviceId/sessionId/workloadId** đã xác minh.
- **clock skew** và event ordering khi ảnh hưởng kết luận.
- **collection gaps**, API timeout và trạng thái UNKNOWN.

Ví dụ, **MDM COMPLIANT lúc 08:00** không tự chứng minh thiết bị vẫn compliant lúc 20:00. **IP risk ở lần đăng nhập trước** không nhất thiết là risk của API call hiện tại. Quy định freshness cần căn cứ vào sensitivity và tốc độ biến động của tín hiệu.

**Không lấy giá trị LOW mặc định khi PIP/MDM/SIEM lỗi**. Cần phân biệt **điểm đo được thấp** với **không đo được**.

## 9. Các chiều rủi ro không nên cộng tùy tiện

Nguy cơ thường gồm ít nhất **khả năng xảy ra** và **tác động**. Nếu điểm risk đã bao gồm resource sensitivity, không được cộng thêm cùng yếu tố tác động lần nữa mà không biết mô hình, vì sẽ **double counting**.

Ví dụ một tổ chức dùng:

~~~text
SessionThreatScore = f(authentication, device, network, behavior)
ResourceImpactTier = classification(resource, action)
OverallDecision = policy(SessionThreatScore, ResourceImpactTier, hardControls)
~~~

Mô hình khác có thể tính score tổng hợp từ các tín hiệu, nhưng phải document rõ. Một **risk score 70 do IP bất thường** không hoàn toàn tương đương **risk score 70 do tài khoản bị nghi compromised**; cả hai có thể cần hành động khác nhau.

**Hard indicators** như credential xác nhận bị thu hồi có thể dẫn trực tiếp tới DENY thay vì chỉ tăng tổng điểm. Ngược lại, nhiều tín hiệu yếu tương quan (IP mới, ASN mới, geo mới) không nên được xem là ba bằng chứng độc lập nếu thực chất cùng xuất phát từ một kết nối VPN.

## 10. Tín hiệu người dùng, thiết bị, phiên và giao dịch là các scope khác nhau

| Risk scope | Chủ thể quan sát | Ví dụ | Chu kỳ đánh giá |
| --- | --- | --- | --- |
| **User/identity risk** | Danh tính và credential | Suspected account compromise | Theo sự kiện và risk policy |
| **Sign-in risk** | Lần authentication | New IP + failure pattern | Mỗi lần đăng nhập |
| **Session risk** | Phiên đã xác thực | Token reuse, posture thay đổi | Trong suốt phiên khi cần |
| **Device risk** | Máy và trạng thái quản lý | Lost, malware, stale posture | Khi posture/MDM đổi |
| **Transaction risk** | Hành động cụ thể | Export toàn bộ dữ liệu | Mỗi hành động nhạy cảm |
| **Resource impact** | Đối tượng bị truy cập | Database secrets, payment approval | Theo classification/version |
| **Workload risk** | Service principal/CI runner | Trust subject rộng, secret leak | Mỗi issuance/use theo khả năng |

**Một lần SSO login có risk LOW không bảo đảm mọi thao tác sau đó risk LOW**. User có thể đăng nhập bình thường rồi bất ngờ tạo một PAT với quyền admin, hoặc device bị mất sau khi đã tạo session.

Risk threshold cần được **đánh giá ở đúng điểm ra quyết định**: sign-in tại IdP, token issuance tại authorization server và resource action tại API/PEP.

## 11. Ngưỡng trên luồng authentication và Conditional Access

Tại **IdP/Conditional Access**, risk threshold có thể dẫn tới:

- **ALLOW authentication** nếu identity/credential hợp lệ và baseline policy đã đạt.
- **STEP_UP MFA** khi yêu cầu assurance cao hơn.
- **REQUIRE_MANAGED_DEVICE** hoặc compliance check.
- **REAUTHENTICATE** khi phiên quá cũ.
- **RESTRICT_SESSION** theo khả năng ứng dụng, ví dụ giới hạn download.
- **DENY** khi có tín hiệu rủi ro cao/hard deny theo policy.
- **ESCALATE_FOR_REVIEW** hoặc mở incident khi nghi compromise.

**MFA challenge không tự bảo đảm chống phishing**. Với hành động rất nhạy cảm, policy có thể yêu cầu **phishing-resistant authenticator**, device binding hoặc assurance cụ thể, thay vì chỉ tăng một bước OTP.

Nếu session đã được MFA trước đó, policy phải phân biệt **assurance còn được chấp nhận** với yêu cầu step-up mới. Không bắt người dùng MFA liên tục khi không cần thiết; cần phối hợp **auth_time, amr/acr theo hợp đồng IdP** và session freshness.

## 12. Ngưỡng tại authorization của resource server

Ngay cả sau khi IdP cho đăng nhập, resource server phải kiểm:

~~~text
Request: user iam-482 -> POST /org-a/payments/approve
Authentication: verified access token for payments-api
Base access: role PaymentApprover for org-a/cost-center-7
SoD: invoice.createdBy != iam-482
Resource impact: HIGH
Session risk score: 55
Action policy: STEP_UP if score >= 30
Decision: CHALLENGE_OR_DENY until step-up satisfied
~~~

**Resource authorization không được tin claim actor, tenant hoặc riskScore do browser gửi** nếu chưa có verifier đáng tin. Token phải có đúng **issuer, audience, expiry, scope**, cùng session policy; risk score nên đến từ **risk engine/PIP đã được bảo vệ** và có version/freshness.

Một policy **PDP Permit** chỉ có ý nghĩa khi **PEP chặn hoặc cho phép đúng action/resource**. Nếu có API batch hay đường local admin bỏ qua PEP, threshold đặt đúng cũng không bảo vệ được đường đó.

## 13. Thiết kế bảng quyết định Risk × Resource × Action

Ví dụ tổ chức phân 3 mức impact (LOW, HIGH, CRITICAL) và risk bands từ mục 5:

| Risk band | Read internal info (LOW impact) | Export customer data (HIGH impact) | Modify IAM policy (CRITICAL impact) |
| --- | --- | --- | --- |
| **LOW** | ALLOW nếu base authz đạt | ALLOW với assurance bắt buộc | REQUIRE_JIT + strong step-up + approval |
| **MEDIUM** | STEP_UP hoặc hạn chế theo policy | STEP_UP + additional controls | DENY hoặc independent review |
| **HIGH** | RESTRICT/STEP_UP theo risk | DENY | DENY + alert |
| **CRITICAL** | DENY theo policy | DENY + alert | DENY + incident response |
| **UNKNOWN** | RESTRICT hoặc remediation-only theo policy | DENY/REQUIRE_VALID_EVIDENCE | DENY |

Bảng chỉ minh họa **hành vi sau khi các hard controls đã đạt**. Một yêu cầu không có permission cơ sở luôn bị DENY, bất kể ô “ALLOW”.

**Rủi ro và mức tác động không luôn tuyến tính**, nhưng ngưỡng cần mang tính nhất quán: trong cùng một scope và cùng các điều kiện khác, tăng risk không được vô tình làm quyền mở rộng từ DENY sang ALLOW.

## 14. Luồng ra quyết định: từ tín hiệu đến enforcement

~~~mermaid
flowchart TD
    A["Request từ human hoặc workload"] --> B["Xác minh actor/token/credential"]
    B --> C{"Hard deny hoặc thiếu base permission?"}
    C -->|"Có"| D["DENY + audit"]
    C -->|"Không"| E["Đọc trusted risk signals từ PIP"]
    E --> F{"Nguồn có đủ mới và đáng tin?"}
    F -->|"Không"| G["UNKNOWN / INDETERMINATE policy"]
    F -->|"Có"| H["Risk engine tính score/band có version"]
    H --> I["Policy kết hợp impact/action và thresholds"]
    I --> J{"Outcome?"}
    J -->|"ALLOW"| K["PEP enforce + audit decision"]
    J -->|"STEP_UP"| L["IdP/verifier yêu cầu assurance mới"]
    L --> M{"Step-up hợp lệ?"}
    M -->|"Có"| N["Re-evaluate toàn bộ policy"]
    N --> C
    M -->|"Không"| D
    J -->|"DENY"| D
    J -->|"RESTRICT"| O["PEP chỉ thực thi quyền hạn chế"]
    G --> P{"Có fallback/remediation đã duyệt?"}
    P -->|"Có"| O
    P -->|"Không"| D
~~~

Sơ đồ nhấn mạnh **risk evaluation không thay authorization**. Sau step-up, hệ thống cần **đánh giá lại base permission và trạng thái danh tính** trước khi chấp nhận request. Một request được duyệt ở đầu flow có thể đã mất quyền khi chờ xác minh.

**PEP phải thực thi outcome thật**. Nếu PDP trả RESTRICT nhưng API không hỗ trợ giới hạn hành động, không được mặc định đổi thành ALLOW_ALL; cần policy quyết định chặn hoặc chuyển vào luồng an toàn.

## 15. Threshold cho từng hành động thay vì chỉ theo người dùng

Đặt ngưỡng ở cấp user có thể không đủ cho một application:

~~~text
User: iam-482, session risk = 42 (MEDIUM)
Action A: READ_STATUS      -> impact LOW   -> STEP_UP nếu policy yêu cầu
Action B: EXPORT_CUSTOMERS -> impact HIGH  -> STEP_UP + export controls
Action C: ASSIGN_ORG_ADMIN -> impact CRIT  -> DENY hoặc JIT workflow độc lập
~~~

Một **risk score 42** không bắt buộc dẫn đến cùng outcome cho mọi action. Tuy vậy, **đừng tạo hàng trăm threshold hardcode ở các controller**: nên dùng **central policy with version**, local enforcement thống nhất và test matrix.

Các tham số quan trọng:

| Tham số | Ý nghĩa |
| --- | --- |
| **actionId** | READ, EXPORT, APPROVE, DELETE, MANAGE_ACCESS |
| **resourceClassification** | Mức nhạy cảm được chủ dữ liệu xác nhận |
| **principalType** | Employee, guest, privileged, workload |
| **environment** | Production, staging, development |
| **authnAssurance** | Mức xác thực đủ cho action |
| **riskBand/score** | Đánh giá rủi ro đủ mới |
| **entitlementScope** | Role/quyền và tenant được phê duyệt |
| **approval/JIT lease** | Thẩm quyền bổ sung nếu cần |

**Resource classification phải đến từ catalog/source có thẩm quyền**. Không tin nhãn classification do client tự đính kèm với request để lấy threshold thấp hơn.

## 16. Step-up MFA: ngưỡng dẫn tới kiểm soát bổ sung

Một phương án phổ biến cho risk band MEDIUM là yêu cầu **step-up authentication**. Nhưng cần phân biệt:

1. **MFA enrollment**: user đã đăng ký factor chưa?
2. **MFA challenge**: user được yêu cầu chứng minh factor khi nào?
3. **Authenticator assurance**: loại factor có đáp ứng chính sách hành động không?
4. **Authentication freshness**: xác thực gần đây tới mức nào?
5. **Risk after step-up**: sự kiện nghi compromise có còn cần chặn không?
6. **Authorization**: user có role và được phép thực hiện action đó hay không?

Ví dụ một user đăng nhập bằng mật khẩu và bị đánh dấu risk MEDIUM có thể hoàn thành WebAuthn/passkey step-up, rồi resource server đánh giá lại quyền. Nhưng nếu hệ thống đã xác định **refresh token bị reuse từ nguồn không được phép**, step-up không nhất thiết đủ để khắc phục; chính sách có thể buộc revoke phiên và điều tra.

**Step-up nên có TTL/freshness riêng**, không đánh dấu account “trusted forever” sau một lần MFA. **Không cho một OTP thành công tạo role Admin** nếu role chưa được phê duyệt.

## 17. Risk UNKNOWN và INDETERMINATE: chọn hành vi an toàn

Trạng thái UNKNOWN có thể do:

- Risk service timeout hoặc outage.
- MDM/device posture chưa gửi dữ liệu.
- PIP trả attribute không có nguồn xác minh.
- Policy version không load được.
- User/session mapping mơ hồ.
- Thời gian nguồn bị lệch làm evidence không dùng được.
- Mô hình scoring không hỗ trợ một loại workload mới.
- Log collector ngừng hoạt động.

| Resource/action | Hướng xử lý khi risk UNKNOWN |
| --- | --- |
| Nội dung công khai | Có thể tiếp tục theo policy bình thường |
| Đọc nội bộ rủi ro thấp | Hạn chế/step-up hoặc chờ đánh giá nếu được duyệt |
| Export dữ liệu nhạy cảm | DENY hoặc REQUIRE_TRUSTED_EVIDENCE |
| Tạo credential đặc quyền | DENY nếu thiếu risk/assurance bắt buộc |
| Recovery/sự cố nghiêm trọng | Đường emergency fallback có thẩm quyền và audit bù trừ |

**Không có score không phải score = 0**. Cũng không nên mặc định mọi UNKNOWN phải khóa cả tổ chức trong mọi hoàn cảnh: policy cần **failure mode** theo action, dữ liệu và tác động tới tính sẵn sàng, được phê duyệt trước.

Một đường fallback an toàn phải có **scope, expiry, approver, evidence, giám sát và hậu kiểm**; không được triển khai **riskServiceDown → allowAll**.

## 18. Risk engine và policy engine có thể là hai thành phần khác nhau

Một kiến trúc hợp lý tách:

- **Signal collectors/PIP**: thu thập dữ liệu xác thực, device, network, session, HR, resource.
- **Risk engine**: tính score/band, model version và provenance.
- **Policy administration (PAP)**: định nghĩa threshold, hard controls, action mapping.
- **Policy decision (PDP)**: kết hợp score, principal, action, resource và hard controls.
- **Policy enforcement (PEP)**: chặn, yêu cầu step-up hoặc giới hạn tại app/API.
- **Audit/SIEM**: ghi sự kiện và phát hiện bypass/drift.

~~~mermaid
flowchart LR
    H["HRIS / IAM / IGA"] --> PIP["Trusted PIP"]
    D["MDM / Device"] --> PIP
    ID["IdP / MFA / Session"] --> PIP
    S["SIEM / Threat intel"] --> PIP
    PIP --> RE["Risk scoring engine"]
    RA["Resource & action catalog"] --> PDP["Policy Decision Point"]
    RE --> PDP
    PA["PAP: thresholds / guardrails / versions"] --> PDP
    C["Client / workload"] --> PEP["PEP API / gateway"]
    PEP --> PDP
    PDP --> PEP
    PEP --> T["Target resource/action"]
    PDP --> A["Decision audit"]
    PEP --> A
~~~

**PDP không tự thay PEP**: một risk policy đúng nhưng một API endpoint không gọi engine vẫn là lỗ hổng enforcement. Audit phải bao gồm những đường **batch, CLI, API, direct DB và service-to-service** phù hợp.

## 19. Risk-score freshness và cache của quyết định

Risk score có thể bị cache để giảm độ trễ. Nhưng cần phân biệt:

| Dữ liệu/cached object | Cần xét |
| --- | --- |
| **Risk signal** | Tuổi tín hiệu, nguồn, event invalidation |
| **Computed score** | Scoring model version, assessedAt, TTL |
| **PDP decision** | Resource/action, user, session, tenant, policyVersion |
| **Authorization role** | Thời điểm Mover/Leaver, entitlement version |
| **Device compliance** | Đổi posture hoặc device bị mất |
| **Token validation** | Exp, revocation epoch, audience và session |

Một **cached ALLOW không được vượt thời hạn token, JIT lease hoặc quyền bị thu hồi**. Thậm chí cache risk score LOW một giờ cũng không phù hợp nếu tài nguyên nhạy cảm cần đánh giá thiết bị mỗi vài phút.

Cache keys cần gắn **principal, tenant, action, resource scope, session/credential context và policy version**; nếu dùng cache key chỉ theo userId, có thể vô tình dùng quyết định cho resource ít nhạy cảm để ALLOW admin operation.

**TTL của risk cache** cần dựa trên mức độ biến động của tín hiệu và SLA thu hồi; không có con số chung áp dụng cho mọi application.

## 20. Rủi ro biến động trong một phiên

Một phiên có thể bắt đầu an toàn rồi chuyển thành rủi ro:

~~~text
09:00  User login từ laptop quản lý, score 12 -> LOW
09:30  Token refresh, score 18 -> LOW
10:00  Device được báo mất, hard control SUSPENDED
10:01  Session/token cũ vẫn có thể còn hạn
10:02  PEP phải áp dụng device revocation/online policy
10:03  Sensitive API request -> DENY theo policy
~~~

Không chỉ đánh giá risk khi login. Những điểm nên **re-evaluate**:

- Thay authentication assurance hoặc session age.
- Token issuance/refresh, đặc biệt khi scope mới.
- Resource/action tăng sensitivity (export, delete, grant).
- Device posture đổi hoặc credential bị revoke.
- HR event Mover/Leaver, sponsor/contract expiry.
- Phát hiện bất thường account compromise.
- Emergency/JIT lease sắp hết hạn.

**Cùng một user có thể có nhiều session với risk khác nhau**. Không tự áp điểm LOW của session A sang session B, hoặc reuse score của browser login cho CI/CD service principal.

## 21. Hysteresis và tránh thay đổi quyết định liên tục

Nếu score dao động quanh ngưỡng 60:

~~~text
09:00  59 -> MEDIUM
09:01  61 -> HIGH
09:02  58 -> MEDIUM
09:03  62 -> HIGH
~~~

Ứng dụng có thể liên tục bật/tắt quyền hoặc yêu cầu MFA nếu không có thiết kế. **Hysteresis**, **debounce**, **cooldown** và **minimum hold time** là kỹ thuật có thể cân nhắc:

- **Escalate quickly** khi vượt ngưỡng rủi ro, đặc biệt hành động nhạy cảm.
- **De-escalate only after** đủ bằng chứng hoặc khoảng ổn định theo policy.
- Không hạ từ HIGH xuống LOW chỉ vì một tín hiệu duy nhất tạm biến mất.
- Với dấu hiệu compromise, yêu cầu **reauthentication, revoke, security review** thay vì chờ điểm tự giảm.
- Ghi rõ **currentBand, previousBand, stateTransitionReason, assessedAt**.

**Hysteresis không được vô hiệu hard deny hoặc kéo dài quyền đã hết hạn**. Nếu user Leaver, token revoked hoặc JIT lease ended, quyết định DENY áp dụng ngay theo policy bất kể score đang dao động.

## 22. Threshold cho tài khoản privileged và emergency access

Đối với tài khoản có khả năng thay IAM policy, đọc secret, sửa backup hoặc disable security control:

- **Baseline authorization** phải cấp đúng role/permission, không dùng risk LOW để tự tăng đặc quyền.
- **JIT/PAM** cấp trong cửa sổ thời gian hạn chế, gắn incident/ticket/owner khi cần.
- **Strong authentication/step-up** có thể là điều kiện bắt buộc **ở mọi risk band**.
- **SoD** kiểm tra self-approval, quyền cấp role và xóa audit.
- **Transaction risk** đánh giá action như create key/export secrets chứ không chỉ sign-in risk.
- **Risk HIGH/CRITICAL** có thể DENY và điều tra trước khi dùng quyền.
- **Emergency continuity** phải là một policy có phê duyệt sẵn, hạn và bằng chứng riêng.

Một operator có risk LOW vẫn không được tự tạo **standing OrgAdmin** nếu policy chỉ cho emergency JIT role trong 20 phút. **Risk threshold bổ sung điều kiện**, không thay approval, role catalog hoặc hard cutoff.

Nếu PAM/IdP lỗi đúng lúc cần recovery, fallback có thể dùng **break-glass path độc lập đã kiểm thử**. Nó phải ghi actor, lý do, scope, session và hậu kiểm; không đơn giản bỏ mọi risk control.

## 23. Ngưỡng cho service account và workload identity

**Non-human identities** không có human session/MFA theo cách thông thường. Risk signals phải phù hợp:

| Workload signal | Rủi ro |
| --- | --- |
| **Issuer không được chấp nhận** | Token/federation giả hoặc sai trust |
| **Audience/subject không khớp** | Dùng token của service khác |
| **Unexpected runner/repository/branch** | CI/CD giả mạo trusted workload |
| **Static key đã lộ** | Credential replay dù access token ngắn hạn |
| **Role vượt scope** | Service chỉ READ nhưng được ADMIN |
| **Workload owner Leaver** | Owner drift, secret từng được người cũ biết |
| **Runtime compromise** | Pod/host bị chiếm quyền |
| **Unexpected geography/volume** | Có thể lạm dụng, cần ngữ cảnh hạ tầng |
| **Credential age/rotation failure** | Rủi ro secret tồn dư |

Một pipeline chạy từ runner mới không mặc định là attacker; có thể do deployment migration. Nhưng nếu **federation subject không đúng trust policy**, đó có thể là **hard deny** chứ không phải tăng risk score lên 65 rồi thử MFA con người.

**Managed identity hoặc token ngắn hạn không miễn review**. Nếu mọi namespace được assume production role, attacker vẫn có thể xin token mới hợp lệ dù mỗi token chỉ tồn tại vài phút.

## 24. Device trust và risk threshold

**Device registration**, **MDM enrollment**, **compliance**, **attestation** và **authentication** là các trạng thái khác nhau:

| Device fact | Vai trò trong risk decision |
| --- | --- |
| Registered | Có record identity; chưa chứng minh posture |
| Managed/enrolled | Có enrollment từ nguồn được tin cậy |
| Compliant | Đáp ứng baseline tại assessedAt được kiểm |
| Attested | Có bằng chứng cho một số hardware/key/boot claims |
| Lost/suspended | Có thể là hard deny/incident trigger |
| Unknown/stale posture | Không tự coi là compliant/LOW |
| Certificate expired/revoked | Credential không còn được chấp nhận |

**Device risk phải gắn với resource policy**, không phải mọi BYOD đều cấm mọi truy cập. Có hệ thống cho phép BYOD truy cập thông tin ít nhạy cảm qua browser, nhưng chặn export hoặc admin action nếu không có managed device.

**Không dùng serial number/IP do client gửi làm chứng minh danh tính thiết bị**. PoP, certificate, MDM/attestation verifier và trust source có thể giúp xác minh, với giới hạn riêng.

## 25. Joiner: threshold không được cho quyền trước thời điểm bắt đầu

Ví dụ account của người mới được tạo ngày 29/11 nhưng employment chỉ có hiệu lực từ 01/12:

~~~text
Account: PROVISIONED
Employment relation: FUTURE_START
Risk score: 8 (LOW)
Request: READ production reports
Base eligibility: FALSE until startAt
Decision: DENY
~~~

Quy trình Joiner nên:

1. HRIS/sponsor xác nhận identity, organization, employmentRelation và startAt.
2. IAM/IGA tính expected rights và risk tier của role.
3. Phê duyệt role nhạy cảm, SoD và policy trước khi provisioning.
4. Có thể chuẩn bị IdP account/SSO/MFA nhưng không tự cho quyền sớm.
5. Risk engine chỉ dùng signals cho một request đã có căn cứ được xét.
6. Resource server kiểm **hard eligibility + permission + threshold**.
7. Audit thử **ALLOW khi hợp lệ** và **DENY trước startAt hoặc ngoài scope**.

Điểm thấp không hợp thức hóa **tài khoản giả, chưa proofing, tenant sai hoặc role không được cấp**.

## 26. Mover: score thấp không giữ được vai trò cũ

Khi người dùng chuyển nhóm Atlas sang Nova:

~~~text
Before Mover:
    AtlasEditor = ACTIVE
    risk = LOW

After Mover effectiveAt:
    AtlasEditor = REVOKED
    NovaViewer = APPROVED
    old access token still carries AtlasEditor claim
    risk = LOW
~~~

**Không được ALLOW Atlas editing chỉ vì risk LOW**. Cần:

- Tính lại **expected rights** và revoke role cũ ở IdP/SCIM/SaaS/direct ACL.
- Xác minh **authorization hiện hành** ở backend, dù JWT cũ vẫn còn exp.
- Nếu cần, dùng **security epoch, token introspection, denylist, policy re-evaluation hoặc short TTL** đúng risk/SLA.
- Ngăn **event cũ/approval trễ** regrant role cũ.
- Giữ **tenant/organization relation** chính xác khi người có nhiều vai trò hợp lệ.
- Ghi **effective-deny verification**, không chỉ IGA ticket CLOSED.

Một risk threshold là **lớp phân tích khả năng compromise**, không thể thay **vòng đời quyền nghiệp vụ**.

## 27. Leaver: hard cutoff thắng mọi risk score

Đối với Leaver, nguồn có thẩm quyền xác nhận quan hệ làm việc đã kết thúc:

| Bước | Trạng thái cần kiểm |
| --- | --- |
| HRIS/contract source | Relation ended với effectiveAt |
| IAM/IGA | Không còn entitlement trái policy |
| IdP/SSO | Account/session/grant bị disable/revoke |
| SCIM/target SaaS | Group, role, direct ACL đã cập nhật |
| OAuth/resource server | Token cũ bị Deny theo SLA |
| PAM/JIT | Lease và elevated sessions kết thúc |
| Device/credential | PAT, SSH key, local credential được xử lý |
| NHI ownership | Service bot chuyển owner/rotate secret nếu cần |

Nếu user đã Leaver, **risk score 3 không cho phép đăng nhập**. Nếu hệ thống không lấy được risk score, **hard deny vẫn có hiệu lực** từ trạng thái Leaver/authorization.

**SCIM active=false không tự chặn JWT được API xác thực offline hoặc PAT cục bộ**. Quy trình phải **đối soát target và kiểm tra negative access** trong phạm vi kiểm thử được ủy quyền. Nếu target không hỗ trợ kiểm chứng, ghi **UNVERIFIED**, không báo quyền đã bị cắt hoàn toàn.

## 28. Contractor, guest và quan hệ tài trợ có hạn

Đối tượng ngoài tổ chức thường có **contractEndAt, sponsor, tenant association và điều kiện truy cập khác nhân viên nội bộ**.

Ví dụ một guest có risk LOW nhưng sponsor đã rời tổ chức hoặc hợp đồng hết hạn:

~~~text
identityType = EXTERNAL_GUEST
sponsorState = INACTIVE
contractEndAt = 2026-11-30T17:00+07:00
requestAt = 2026-12-01T09:00+07:00
riskScore = 12

Result: DENY vì guest access eligibility đã hết
~~~

Một policy có thể yêu cầu **step-up ở ngưỡng thấp hơn cho guest** khi truy cập dữ liệu nhạy cảm, nhưng phải có căn cứ risk và đánh giá tác động. Không mặc định “mọi external user là độc hại”; threshold cần dựa trên tín hiệu, resource impact, trust và yêu cầu nghiệp vụ.

**Guest không được tự nâng scope sang tenant khác bằng một authentication/session hợp lệ**. Cross-tenant access cần authorization, federation trust và approval theo chính sách của từng tổ chức.

## 29. Token, SSO và session risk phải được nối đúng

Rủi ro tại thời điểm phát token có thể không phản ánh rủi ro tại thời điểm gọi API:

~~~text
09:00  SSO login, riskScore=14, access token A exp=09:30
09:10  Device được đánh dấu COMPROMISED
09:11  Risk engine cập nhật riskScore=94
09:12  Token A vẫn có chữ ký hợp lệ và chưa exp
09:13  API thực hiện sensitive operation
~~~

Nếu API chỉ validate **signature + exp**, request 09:13 có thể được ALLOW dù policy mới yêu cầu DENY. Risk-based access cần làm rõ **thời điểm và phạm vi tái đánh giá**:

| Lớp | Cần kiểm |
| --- | --- |
| **IdP sign-in** | Login/session risk và factor assurance |
| **Authorization server** | Client/user eligibility, scope, token issuance policy |
| **Refresh grant** | Grant active, rotation/reuse, revoked state |
| **Resource server** | Token đúng issuer/audience/exp và quyền/resource risk hiện hành |
| **Session cache** | Risk state, security epoch và stale Permit |
| **Audit/SIEM** | Dòng thời gian session risk và action result |

**ID token là token authentication cho OIDC client**, không phải access token gửi tùy ý đến API. **Refresh token không dùng làm bearer credential của resource server**. **JWT exp không tự xử lý risk tăng hoặc Mover/Leaver trước hạn**; cần revocation/policy freshness tùy yêu cầu.

## 30. Quy tắc đánh giá risk và cách chọn threshold

Đặt threshold nên là quá trình có lý do:

1. **Định nghĩa decision goal**: giảm account takeover, chống credential replay, giảm data exfiltration hoặc bảo vệ administrator actions?
2. **Chọn population/resource/action**: employee sign-in, high-risk export hay workload token issuance?
3. **Định nghĩa labels/outcomes** nếu dùng dữ liệu thực: incident confirmed, unauthorized access attempt, fraud case, benign transaction.
4. **Đánh giá tính đầy đủ của dữ liệu**: logging coverage, missing cohorts, false labels, policy changes.
5. **Thiết kế score/rules** có version và giải thích được phạm vi.
6. **Chọn thresholds dựa trên risk appetite** và chi phí false positive/false negative.
7. **Đo tác động** trên dữ liệu lịch sử và thử nghiệm có kiểm soát.
8. **Bổ sung hard denies/step-up policy** độc lập điểm số.
9. **Phê duyệt change và rollout** theo nhóm nhỏ trước khi enforcement rộng.
10. **Giám sát drift/outcomes, định kỳ hiệu chỉnh**.

**Không khuyến nghị chọn số 70 chỉ vì nghe có vẻ “nguy hiểm”**. Nếu score 0–100 được tạo bằng heuristic chưa calibration, cần ghi rõ ý nghĩa kỹ thuật, giới hạn và kỳ vọng hành vi của thresholds.

## 31. Ví dụ cách tính điểm minh họa — và giới hạn của nó

Một scoring scheme thủ công có thể dùng:

~~~text
Initial score = 0
New unmanaged device                    +25
Unfamiliar network with weak reputation +20
Authentication anomalies                +25
Sensitive bulk export action            +15
Known session token reuse               +40

score = min(100, sumOfApplicableWeights)
~~~

Giả sử một request có **new device + unusual network** thì score 45, nằm MEDIUM theo bảng trước. Nhưng ví dụ này chỉ minh họa:

- **Các trọng số không được suy từ chuẩn bảo mật**.
- Nhiều tín hiệu có thể **correlated**; cộng độc lập gây double counting.
- Nếu resource impact đã được xét ở action matrix, đưa bulk export vào score lần nữa có thể đếm đôi.
- Biến “known token reuse” có thể cần **hard deny**, không chỉ +40.
- Đầu vào thiếu không được được xem là **0 điểm**.
- Output 45/100 không thể đọc thành xác suất 45%.

Trong triển khai, nên dùng **risk model có tài liệu, confidence/coverage, kiểm thử historical replay** hoặc policy rules có lý do; tránh triển khai các trọng số trên như một công thức production mặc định.

## 32. JSON kết quả đánh giá Risk threshold

Ví dụ một decision context được chuẩn hóa:

~~~json
{
  "assessmentId": "risk-assessment-2026-0192",
  "assessmentVersion": "v3",
  "assessedAt": "2026-11-23T09:15:00+07:00",
  "validUntil": "2026-11-23T09:17:00+07:00",
  "principal": {
    "identityRef": "iam-user-482",
    "identityType": "EMPLOYEE",
    "tenantId": "org-a",
    "employmentRelationRef": "emp-org-a-482"
  },
  "sessionRef": "session-482-03",
  "deviceRef": "dev-org-a-000482",
  "resource": {
    "resourceId": "payments/invoice-782",
    "classification": "HIGH",
    "action": "APPROVE_PAYMENT"
  },
  "signals": [
    {
      "signalType": "NEW_DEVICE",
      "value": true,
      "source": "device-trust-service",
      "observedAt": "2026-11-23T09:14:00+07:00"
    },
    {
      "signalType": "NETWORK_REPUTATION",
      "value": "UNFAMILIAR",
      "source": "network-risk-service",
      "observedAt": "2026-11-23T09:14:30+07:00"
    }
  ],
  "riskScore": 45,
  "riskBand": "MEDIUM",
  "modelVersion": "risk-rules-v12",
  "policyVersion": "payments-risk-threshold-v6",
  "baseAuthorization": "PERMIT",
  "hardDeny": false,
  "requiredControl": "STEP_UP_PHISHING_RESISTANT_MFA",
  "finalDecision": "CHALLENGE_PENDING",
  "evidenceCoverage": "SUFFICIENT_FOR_THIS_POLICY",
  "correlationId": "payments-request-782-04"
}
~~~

**Đây là schema tự thiết kế**, không phải định dạng chuẩn cho một IdP, OAuth server hoặc PDP. **riskScore, signal sources và assessmentValidUntil** phải được xác minh từ những nguồn tin cậy. Không nên đưa **raw IP, token, credential hoặc PII không cần thiết** vào các log phân phối rộng.

Trạng thái **CHALLENGE_PENDING** không phải ALLOW. Sau khi step-up, cần tạo **final authorization decision** có actor/session, resource/action và evidence cập nhật, đồng thời kiểm tra các hard controls lần nữa.

## 33. YAML minh họa cấu hình threshold có version

~~~yaml
policy:
  id: payment-risk-threshold
  version: v6
  organization: org-a
  score:
    min: 0
    max: 100
    requireFiniteNumber: true
    bands:
      - name: LOW
        minInclusive: 0
        maxExclusive: 30
      - name: MEDIUM
        minInclusive: 30
        maxExclusive: 60
      - name: HIGH
        minInclusive: 60
        maxExclusive: 85
      - name: CRITICAL
        minInclusive: 85
        maxInclusive: 100
  hardControls:
    - DENY_IF_IDENTITY_RELATION_INACTIVE
    - DENY_IF_RESOURCE_TENANT_MISMATCH
    - DENY_IF_NO_BASE_ENTITLEMENT
    - DENY_IF_EXPLICIT_POLICY_DENY
    - DENY_IF_CREDENTIAL_REVOKED
    - DENY_IF_JIT_LEASE_EXPIRED
  actionPolicy:
    APPROVE_PAYMENT:
      impact: HIGH
      LOW: ALLOW_IF_ASSURANCE_SUFFICIENT
      MEDIUM: STEP_UP_PHISHING_RESISTANT_MFA
      HIGH: DENY
      CRITICAL: DENY_AND_ALERT
      UNKNOWN: DENY
    READ_INTERNAL_STATUS:
      impact: LOW
      LOW: ALLOW
      MEDIUM: STEP_UP_IF_ASSURANCE_STALE
      HIGH: RESTRICT
      CRITICAL: DENY
      UNKNOWN: RESTRICT_OR_REMEDIATE
  assessment:
    maxAgeSecondsForHighImpact: 120
    rejectClientSuppliedRiskScore: true
  audit:
    logSignalsByReference: true
    includeRawCredentials: false
~~~

**Đây là YAML minh họa**, không phải cấu hình chính thức của Keycloak, Entra ID, Spring Security hay bất kỳ sản phẩm nào. Các mốc số không phải chuẩn bắt buộc. Trong thực tế, **schema validation** cần kiểm ngưỡng liên tục, không chồng lấn, không để lỗ hổng giữa các band, đủ mọi action bắt buộc và không có giá trị ngoài 0–100.

**DENY_IF_NO_BASE_ENTITLEMENT** không nên tự suy từ một claim không được xác minh. Resource server phải thực thi authorization thực tế theo đúng object và tenant.

## 34. Mã giả: áp threshold nhưng không vượt hard controls

~~~text
evaluateRiskBasedAccess(request, trustedNow):
    identity = verifyPrincipalAndCredential(request)
    if identity.unverified:
        return DENY_AUTHENTICATION

    resource = loadAuthoritativeResourceAndTenant(request.resource)
    policy = loadCurrentApprovedPolicy(resource, request.action)
    if policy.unavailable:
        return DENY_OR_APPROVED_CONTROLLED_FALLBACK

    if not identity.activeFor(resource.organization, trustedNow):
        return DENY_INACTIVE_RELATION
    if not resource.tenantMatches(identity, request):
        return DENY_CROSS_TENANT
    if not authorizeBaseEntitlement(identity, request.action, resource):
        return DENY_NO_PERMISSION
    if violatesHardDenyOrSoD(identity, request, policy):
        return DENY_HARD_CONTROL

    assessment = getTrustedCurrentRiskAssessment(
        identity, request.session, request.device,
        request.action, resource, trustedNow
    )

    if assessment.missingOrInvalidOrStale:
        return policy.outcomeForUnknownRisk(request.action, resource)

    score = assessment.score
    if not isFiniteNumber(score) or score < 0 or score > 100:
        return policy.outcomeForUnknownRisk(request.action, resource)

    band = policy.findExactlyOneRiskBand(score)
    outcome = policy.outcomeFor(band, resource.classification, request.action)

    if outcome == STEP_UP:
        result = verifyFreshAuthenticationWithRequiredAssurance(request)
        if not result.satisfied:
            return DENY_OR_CHALLENGE
        return reevaluateAllHardControlsAndRiskPolicy(request, currentTrustedNow())

    recordSanitizedDecision(policy.version, assessment.id, outcome)
    return enforceAtResourceServer(outcome, request, resource)
~~~

**Không đưa toàn bộ business authorization vào risk score** rồi bỏ qua hard deny. Khi step-up thành công, **không nên gọi đệ quy vô hạn**: thực thi lại với session assurance mới, có giới hạn số lần challenge, loop protection và kiểm tra score/authorization hiện hành.

Một **PDP decision** cần được PEP thực thi. Nếu policy trả RESTRICT mà API không hỗ trợ chế độ giới hạn, không được âm thầm coi là Permit.

## 35. Java minh họa: phân band ở ranh giới chính xác

Code Java dưới đây chỉ xử lý **phân nhóm điểm số** và một lớp outcome mẫu; **không phải bộ authorization production**. Nó dùng quy tắc từ mục 5, không tự đánh giá token hay quyền người dùng.

~~~java
public final class RiskThresholds {
    public enum Band {
        LOW, MEDIUM, HIGH, CRITICAL, UNKNOWN
    }

    public enum Decision {
        ALLOW_AFTER_BASE_AUTHZ, STEP_UP, DENY
    }

    private RiskThresholds() {}

    public static Band classify(Double score) {
        if (score == null || !Double.isFinite(score)
                || score < 0.0 || score > 100.0) {
            return Band.UNKNOWN;
        }
        if (score < 30.0) return Band.LOW;
        if (score < 60.0) return Band.MEDIUM;
        if (score < 85.0) return Band.HIGH;
        return Band.CRITICAL;
    }

    // Example for a HIGH-impact operation only.
    // Must be called AFTER authentication, entitlement,
    // tenant and hard-deny checks have succeeded.
    public static Decision highImpactDecision(
            Band band, boolean assuranceSatisfied) {
        if (band == null || band == Band.UNKNOWN) {
            return Decision.DENY;
        }
        return switch (band) {
            case LOW -> assuranceSatisfied
                    ? Decision.ALLOW_AFTER_BASE_AUTHZ
                    : Decision.STEP_UP;
            case MEDIUM -> Decision.STEP_UP;
            case HIGH, CRITICAL -> Decision.DENY;
            case UNKNOWN -> Decision.DENY;
        };
    }
}
~~~

**Hàm không cấp quyền**; nó giả định những điều kiện bắt buộc đã kiểm tra ở nơi khác. Không lấy dữ liệu **Double score** trực tiếp từ request client để quyết định ALLOW. Java switch expression phù hợp các phiên bản Java hiện đại hỗ trợ tính năng này; khi dùng Java cũ hơn phải điều chỉnh syntax.

Trong production, hãy chọn risk thresholds từ **versioned policy source**, kiểm **assessedAt, signal quality, identity relation, action/resource**, audit và thực thi PEP. Nếu risk engine trả **NaN, Infinity, -1 hoặc 101**, class UNKNOWN nên dẫn tới xử lý đã định, không bị ép về LOW.

## 36. Kỹ thuật hiệu chỉnh: false positive và false negative

Ngưỡng càng thấp thường phát hiện nhiều trường hợp nghi vấn hơn nhưng có thể gây nhiều **false positives**; ngưỡng cao hơn giảm friction nhưng có thể làm tăng **false negatives**. Tuy nhiên quan hệ thực tế phụ thuộc mô hình, labels, action và population.

| | Thực tế là attack/abuse | Thực tế hợp lệ |
| --- | --- | --- |
| **Rule chặn/cảnh báo** | True Positive (TP) | False Positive (FP) |
| **Rule cho qua** | False Negative (FN) | True Negative (TN) |

Các metric thường dùng:

~~~text
Precision = TP / (TP + FP)
Recall (TPR) = TP / (TP + FN)
False Positive Rate = FP / (FP + TN)
False Negative Rate = FN / (FN + TP)
~~~

Các công thức chỉ có ý nghĩa nếu **labels đủ tin cậy**. Một trường hợp không có incident report không đương nhiên là True Negative, và một cảnh báo SIEM cũng chưa tự là ground truth attack.

**Base rate rất quan trọng**: nếu tấn công hiếm, một detector có FPR tưởng thấp vẫn có thể gây nhiều bước MFA hoặc chặn nhầm. Vì thế phải đánh giá cả **an ninh, thời gian xử lý, business impact, accessibility và tính sẵn sàng**, không tối ưu riêng một con số.

## 37. Calibrate score, chọn threshold và kiểm định theo thời gian

Nếu score được dự định là xác suất, cần thực hiện **probability calibration** dựa trên tập dữ liệu có labels đáng tin; nếu chỉ là điểm thứ bậc, hãy gọi đúng là **ordinal/heuristic score**.

Các bước:

1. **Phân tách dữ liệu theo thời gian** để tránh training/test leakage từ cùng incident hoặc session.
2. **Đánh giá theo resource/action/persona**: employee, guest, workload, privileged.
3. **Kiểm tra precision/recall/FPR** và hậu quả của các threshold khác nhau.
4. **Kiểm chứng trên thời kỳ mới** và những tình huống chưa thấy trong training.
5. **Phân tích drift** về nguồn IP, thiết bị, factor, hành vi người dùng.
6. **Tách hard deny rules** ra khỏi score để tránh bị mô hình “bù” điểm.
7. **Tính impact của step-up/deny** lên trải nghiệm và vận hành.
8. **Document threshold rationale**, người phê duyệt và cách rollback.

Một threshold tốt cho **đăng nhập thông thường** chưa chắc tốt cho **export dữ liệu production**. Nếu một mô hình được huấn luyện từ sự kiện sign-in, không tự suy nó dự đoán chính xác hành động gian lận ở API.

**Không nên diễn giải điểm 80 như “80% compromised”** khi chưa có calibration/validation tương ứng.

## 38. Shadow mode, canary và rollout threshold

Thay ngưỡng từ 60 xuống 40 có thể làm tăng đột biến số request bị challenge hoặc chặn. Một quy trình rollout:

- **Offline replay** trên dữ liệu lịch sử với đầy đủ giả định/giới hạn.
- **Shadow evaluation**: tính outcome dự kiến nhưng không thực thi để đo tác động, đồng thời không làm lộ dữ liệu nhạy cảm.
- **Canary rollout** trên một tập user/app/resource có owner và kế hoạch rollback.
- **Safety checks**: hard deny vẫn chặn trong mọi mode, không giảm bảo vệ production ngoài phê duyệt.
- **Outcome telemetry**: step-up completion, Deny, false positive investigations, API latency.
- **Threshold version comparison**: policy v5 vs v6, exact population, normalized exposure.
- **Approval/rollback criteria** rõ nếu outage, false positive hoặc bypass tăng.

**Shadow mode không phải nơi thử bỏ hard deny** đối với môi trường production. Một risk rule mới có thể chạy shadow, nhưng những điều kiện an toàn đã bắt buộc vẫn phải được enforce.

Nếu system risk scoring outage khi canary, fallback phải đúng **đường xử lý UNKNOWN đã phê duyệt**, không sử dụng policy mới chưa kiểm chứng để mở quyền rộng.

## 39. Drift, monitoring và chu kỳ điều chỉnh ngưỡng

Sau khi chạy production, cần theo dõi:

| Tín hiệu | Ý nghĩa |
| --- | --- |
| **Risk score distribution** | Điểm bỗng tập trung ở mức rất cao/thấp |
| **Challenge rate** | Tỷ lệ step-up theo action/resource/client |
| **Challenge success/failure** | Chất lượng assurance và UX |
| **Deny/incident confirmation** | Hiệu quả và sai số của policy |
| **Risk UNKNOWN rate** | Signal/source coverage gap |
| **Signal freshness violations** | MDM/IdP/PIP đưa dữ liệu cũ |
| **Policy version divergence** | PDP/PEP dùng threshold khác nhau |
| **Unexpected ALLOW after revoke** | Hard control/cached decision lỗi |
| **False positive impact** | Người dùng bị chặn sai, productivity/outage |
| **Privilege bypass path** | API không gọi risk/authorization policy |
| **Authentication method drift** | Người dùng chuyển factor, thiết bị mới |
| **Decision latency** | Risk lookup gây trễ giao dịch |

Thay đổi rủi ro có thể đến từ **tấn công mới**, **thay đổi hợp lệ của doanh nghiệp** hoặc **dữ liệu đầu vào hỏng**. Không tự giảm threshold khi thấy nhiều người bị chặn mà chưa phân tích nguyên nhân.

Đặt **owner, review cadence và emergency rollback** cho ngưỡng rủi ro. **Không coi một lần tune score là cấu hình vĩnh viễn**.

## 40. Privacy, fairness và tính giải thích được của threshold

Risk-based access có thể sử dụng dữ liệu liên quan con người như IP, vị trí gần đúng, device ID, lịch hoạt động và bất thường hành vi. Hệ thống phải kiểm soát **thu thập, mục đích sử dụng, độ chính xác, phân quyền và retention**.

| Chủ đề | Nguyên tắc |
| --- | --- |
| **Data minimization** | Chỉ dùng tín hiệu cần thiết để kiểm soát truy cập |
| **Source transparency** | Ghi nguồn, assessedAt, policy/model version |
| **Sensitive attributes** | Không sử dụng đặc tính nhạy cảm làm yếu tố đánh giá rủi ro không có căn cứ |
| **Proxy discrimination** | Kiểm tra tác động bất lợi do geo, language, network hoặc device ownership |
| **Accessibility** | Step-up phải có phương án khả dụng cho người có nhu cầu hỗ trợ |
| **Appeal/remediation** | Có cách xử lý false positive, mất thiết bị hoặc factor lỗi |
| **Retention/access** | Giới hạn người đọc risk history và thời hạn lưu |
| **Explainability** | Có reasonCode hữu ích mà không tiết lộ logic chống gian lận dễ bị lách |

Một điểm risk tăng vì user đi công tác, dùng VPN hoặc thay điện thoại không mặc nhiên có nghĩa người đó gian lận. **IP/geo có thể là proxy gián tiếp** cho đặc điểm cá nhân hoặc điều kiện làm việc, tạo nhóm người bị step-up nhiều hơn dù hành vi hợp lệ.

Nên theo dõi **false positive, friction và khả năng truy cập** theo các nhóm ngữ cảnh phù hợp với chính sách quyền riêng tư. Không nên đưa toàn bộ bí mật của detector vào thông báo lỗi; có thể trả **MFA_REQUIRED, DEVICE_STATE_STALE, RISK_ASSESSMENT_UNAVAILABLE** theo mức công khai được phép.

## 41. Audit trail cho Risk threshold

Mỗi quyết định rủi ro có tác động truy cập nên ghi:

| Nhóm | Thuộc tính | Vì sao cần |
| --- | --- | --- |
| **Event** | eventId, eventType, correlationId | Theo dõi chuỗi |
| **Actor** | Verified principalRef, principalType, issuer | Ai yêu cầu |
| **Session/device** | sessionRef, deviceRef, authenticationRef | Bằng chứng ngữ cảnh |
| **Target** | tenantId, resourceId, action | Scope thực thi |
| **Risk** | assessmentRef, score/band, freshness, modelVersion | Ngưỡng đã áp |
| **Policy** | policyId/version, hard controls, required assurance | Vì sao quyết định |
| **Decision** | ALLOW/STEP_UP/RESTRICT/DENY/UNKNOWN | Outcome của PDP |
| **Enforcement** | PEP action result, target operation/result | Kiểm chứng đã áp dụng |
| **Time** | eventTime, receivedAt, evaluationAt | Điều tra thứ tự/sai lệch |
| **Exception** | approvalRef, owner, expiresAt nếu có | Kiểm soát ngoại lệ |

Ví dụ log **không chứa raw token**:

~~~json
{
  "eventId": "risk-decision-2026-1292",
  "eventType": "RISK_BASED_ACCESS_DECISION",
  "correlationId": "req-payments-782-04",
  "principalRef": "org-a/iam-user-482",
  "tenantId": "org-a",
  "resourceRef": "payments/invoice-782",
  "action": "APPROVE_PAYMENT",
  "assessmentRef": "risk-assessment-2026-0192",
  "riskScore": 45,
  "riskBand": "MEDIUM",
  "modelVersion": "risk-rules-v12",
  "policyVersion": "payments-risk-threshold-v6",
  "hardControlsResult": "PASS",
  "baseAuthorization": "PERMIT",
  "requiredControl": "STEP_UP_PHISHING_RESISTANT_MFA",
  "decision": "CHALLENGE_PENDING",
  "enforcementStatus": "NO_BUSINESS_ACTION_EXECUTED",
  "evaluatedAt": "2026-11-23T09:15:00+07:00"
}
~~~

**PDP gửi CHALLENGE không đồng nghĩa người dùng đã hoàn thành challenge**; khi step-up thành công phải có event riêng và authorization re-evaluation. **Log kết quả ALLOW không chứng minh backend action đã hoàn tất** nếu operation chạy bất đồng bộ.

Audit trail cần được lưu ở hệ thống **không thể bị principal đặc quyền tùy ý sửa/xóa**, với integrity/access controls phù hợp. Không giữ raw refresh token, private key, OTP seed hoặc session cookie trong log.

## 42. Threat model cho ngưỡng rủi ro

| Mối đe dọa | Ví dụ | Biện pháp cần xem xét |
| --- | --- | --- |
| **Score injection** | Client gửi riskScore=0 | Risk assessment chỉ từ nguồn server tin cậy |
| **PIP spoofing** | Thiết bị khai compliant=true | Verifier/MDM và provenance |
| **Score tampering** | Attacker sửa model weights | Access control, signed/versioned change, audit |
| **Policy downgrade** | Thay threshold high từ 60 lên 99 | SoD approval, version diff, deployment controls |
| **Risk lookup outage** | Service timeout → code fallback Permit | UNKNOWN fail-safe và controlled continuity |
| **Cache confusion** | Permit API thường tái dùng cho admin endpoint | Cache key đầy đủ action/resource/tenant |
| **Cross-tenant mix-up** | Risk của org-a được dùng cho org-b | Namespaced principal/resource matching |
| **Expired token acceptance** | Risk LOW bypass exp | Token verifier bắt buộc |
| **Replay/credential theft** | Refresh token cũ bị dùng lại | Family revocation và hard indicators |
| **Missing enforcement path** | Batch API bỏ gọi PDP | PEP coverage/integration tests |
| **Decision oscillation** | Score 59↔61 liên tục | Hysteresis trong phạm vi không làm yếu hard deny |
| **Data poisoning** | Log giả làm model giảm risk | Data validation, separate truth labels |
| **Privacy overreach** | Thu toàn bộ lịch vị trí cá nhân | Minimization, retention/access review |
| **Alert suppression** | Admin tắt SIEM để giảm risk | Independent audit/monitoring |

Đặc biệt, **risk engine có thể trở thành một hệ thống ảnh hưởng trực tiếp tới tính sẵn sàng**. Nếu một rule sai đánh CRITICAL cho mọi account, phải có **approved rollback/incident playbook**, không cho một cá nhân tự tắt toàn bộ security policies mà không audit.

## 43. Governance: ai được quyết định hoặc thay đổi threshold?

| Vai trò | Trách nhiệm | Giới hạn |
| --- | --- | --- |
| **Security/risk owner** | Phê duyệt risk appetite và threshold cho high impact | Không tự bỏ hard controls theo ý muốn |
| **Resource/data owner** | Xác định impact và controls cho tài nguyên | Không tự cấp quyền vượt tổ chức |
| **IAM/IdP owner** | Triển khai sign-in/session/step-up policy | Không thay authorization của app owner |
| **Application owner** | Triển khai PEP và action-level enforcement | Không tự tin client-supplied score |
| **Risk engineering** | Xây và hiệu chỉnh model/rules | Phải document provenance, metrics, validation |
| **SRE/operations** | Vận hành pipeline và rollback khi sự cố | Không bỏ audit và giới hạn bảo mật đã duyệt |
| **SOC** | Điều tra risk alerts và false positives | Alert không tự là ground truth |
| **Independent auditor** | Kiểm tra policy change/effectiveness | Không mặc nhiên có quyền sửa production policy |

Một bản thay đổi threshold nên có **policy diff, test results, risk rationale, affected population, expected challenge/deny volume, approver, planned rollout, rollback rule và audit reference**.

**Không cho developer hoặc operator bị threshold chi phối tự phê duyệt việc nới lỏng threshold** nếu quy định SoD yêu cầu tách người. Chế độ khẩn cấp khi outage phải có cơ chế kiểm soát bù trừ và hậu kiểm.

## 44. Exception, manual review và quy tắc hết hạn

Có thể tồn tại trường hợp nhu cầu nghiệp vụ hợp lệ nhưng risk engine false positive, ví dụ nhân viên đi công tác và không thể dùng thiết bị cũ. Một **exception** phải rõ:

- **Request/incidentRef** và business justification.
- **Subject, resource, action, tenant và environment** được ngoại lệ.
- **Risk/approval owner** có thẩm quyền, độc lập nếu cần.
- **Controls vẫn bắt buộc**, ví dụ authentication assurance, base RBAC, SoD.
- **Compensating controls** như VPN/bastion, giới hạn chỉ đọc, audit tăng cường.
- **StartsAt/expiresAt** và quy trình hết hạn tự động.
- **Re-review** khi device/role/tenant hoặc trạng thái nguy cơ thay đổi.
- **Audit và negative tests** sau expiry.

**Exception không cho phép lấy score thấp giả tạo**. Nên giữ assessment gốc và ghi **override decision reference** riêng. Không tự đặt riskScore=0 chỉ vì manager đồng ý cho user làm việc.

**Hard deny không được miễn trừ** nếu policy không cho phép. Ví dụ user không có entitlement, token đã revoked hoặc tenant mismatch phải bị chặn dù exception về unusual network có hợp lệ.

## 45. Tình huống thực hành: nhân viên Mover và giao dịch nhạy cảm

**Bối cảnh:** Lan làm việc ở **org-a**, trước đây có role AtlasEditor và vừa chuyển sang nhóm Nova. Lan đăng nhập qua SSO từ thiết bị mới để xem báo cáo, sau đó thử phê duyệt một thanh toán.

### 45.1. Đầu vào và policy

~~~text
Identity: iam-lan-482
Employment: ACTIVE org-a
Role after Mover: Nova ReportViewer
Old AtlasEditor: REVOKED
Device: REGISTERED, compliance UNKNOWN
Network: new ASN
Risk score: 55 (MEDIUM)

Request A: READ Nova report
Request B: EDIT Atlas report
Request C: APPROVE_PAYMENT
~~~

### 45.2. Ra quyết định theo thứ tự

| Request | Base entitlement | Risk handling | Kết quả |
| --- | --- | --- | --- |
| **READ Nova** | Có Viewer | MEDIUM có thể STEP_UP/VERIFY_DEVICE | ALLOW sau điều kiện bổ sung thành công |
| **EDIT Atlas** | Đã revoke sau Mover | Hard deny: NO_PERMISSION | DENY dù MFA thành công |
| **APPROVE_PAYMENT** | Không có PaymentApprover | Hard deny: NO_PERMISSION | DENY trước khi risk threshold |

Điều quan trọng: **MFA step-up chỉ xác minh lại chủ thể**, không biến ReportViewer thành PaymentApprover. Nếu target còn direct Atlas ACL, audit phải ghi **permission drift** và kiểm tra quyền thực ở endpoint.

### 45.3. Rủi ro tăng trong phiên

Lúc 14:00, MDM cập nhật device là **SUSPENDED** do nghi mất. User vẫn có access token chưa hết hạn. Lúc 14:01, client gọi API Nova:

~~~text
Session token: cryptographically valid
Risk: HIGH hoặc device hard deny theo policy
Device state: SUSPENDED
Outcome: DENY / revoke session theo chính sách
~~~

Nếu API chỉ dùng cached sign-in score 55 mà không nhận trạng thái device mới, đây là **risk freshness/enforcement gap**. Cần xét invalidate cache hoặc online policy tại resource server.

### 45.4. Hậu kiểm

Audit liên kết **HRIS Mover event, IGA role delta, IdP session, risk assessments, MDM state, PDP policy version, PEP decisions, token/session revoke và target readback**. Nếu một API không có log hoặc vẫn ALLOW, không báo toàn bộ quyền đã được chặn.

## 46. Tình huống thực hành: CI/CD workload nhận token production

**Bối cảnh:** Pipeline build của service **billing-sync** dùng workload federation để lấy token cloud. Ban đầu policy chỉ cho repository được duyệt, branch protected và environment production.

### 46.1. Trust và risk signals

| Signal | Bình thường | Bất thường |
| --- | --- | --- |
| **Issuer** | CI platform được chấp nhận | Issuer ngoài trust |
| **Subject** | Repo và branch đã duyệt | Fork hoặc branch không có quyền |
| **Audience** | Cloud token exchange đúng | Token audience khác |
| **Environment** | Production approval đúng | Dev job tự lấy prod role |
| **Role** | BillingReader và deploy hạn chế | OrgIAMAdmin |
| **Credential** | Federated short-lived | PAT/secret static mới xuất hiện |

Một lần run từ branch lạ không nên được cứu bằng **user MFA step-up** nếu **federation subject không đáp ứng hard trust policy**. Risk threshold có thể dùng để phát cảnh báo/giới hạn đối với tín hiệu yếu; **signature, issuer, audience và principal trust** phải là điều kiện xác thực cơ sở.

### 46.2. Khi owner Leaver

Người từng cấu hình pipeline nghỉ việc. Workload vẫn cần chạy, nên IAM phải **chuyển service owner**, rút quyền CI/CD của người cũ và rà soát shared secrets/trust. **Không xóa service chỉ vì owner Leaver**, nhưng cũng không cho phép người cũ tiếp tục mint token do giữ key hoặc quyền sửa workflow.

**Token ngắn hạn chỉ bảo vệ cửa sổ một lần dùng**, không ngăn một principal không được kiểm soát **tiếp tục xin token mới**.

## 47. Bộ kiểm thử Risk threshold

| Test | Tình huống | Kết quả mong đợi |
| --- | --- | --- |
| T01 | Score 0, đủ base authorization | LOW; ALLOW nếu mọi hard controls đạt |
| T02 | Score 29.999 | LOW theo policy minh họa |
| T03 | Score đúng 30 | MEDIUM, không LOW |
| T04 | Score 59.999 | MEDIUM |
| T05 | Score đúng 60 | HIGH |
| T06 | Score 84.999 | HIGH |
| T07 | Score đúng 85 | CRITICAL |
| T08 | Score đúng 100 | CRITICAL |
| T09 | Score -1/101/NaN/Infinity/null | UNKNOWN/invalid, không ép LOW |
| T10 | User không có entitlement, score 0 | DENY_NO_PERMISSION |
| T11 | Token hết hạn, score 0 | 401/invalid_token theo API contract |
| T12 | User đã Leaver, score 0 | Hard deny |
| T13 | Tenant org-a request resource org-b | Deny cross-tenant |
| T14 | SoD cấm self-approve, score LOW | Deny hành động tự duyệt |
| T15 | MFA step-up thành công nhưng role đã revoke | Deny sau re-evaluation |
| T16 | Device LOST nhưng risk cache LOW | Hard deny hoặc policy block phù hợp |
| T17 | PIP timeout khi export nhạy cảm | DENY/REQUIRE_EVIDENCE, không allowAll |
| T18 | PIP timeout ở chức năng ít nhạy cảm | Đúng fallback đã duyệt |
| T19 | Client tự gửi header Risk-Score: 0 | Không tin dữ liệu client |
| T20 | Risk score assessedAt quá cũ | UNKNOWN/refresh theo policy |
| T21 | Risk oscillates 59↔61 | Escalation an toàn, hysteresis không bỏ hard deny |
| T22 | Cache Permit từ API read dùng cho API admin | Không được tái sử dụng sai action |
| T23 | Policy version thay giữa request | Revalidate/ghi version nhất quán |
| T24 | User Mover còn token role cũ | Không ALLOW hành động ngoài quyền |
| T25 | Guest hết contract nhưng score LOW | Deny access eligibility |
| T26 | CI/CD subject sai branch | Deny trust/identity policy |
| T27 | Service principal owner Leaver | Transfer/rotate review, không auto cấp quyền |
| T28 | DPoP proof hợp lệ nhưng token sai audience | Deny |
| T29 | Risk LOW nhưng JIT lease đã hết | Deny |
| T30 | Emergency fallback khi risk engine outage | Chỉ đường đã duyệt, có audit |
| T31 | Endpoint batch không gọi PDP/PEP | Integration test phát hiện bypass |
| T32 | Simulated risk raised từ LOW lên CRITICAL | Revoke/restrict theo action policy |
| T33 | Quyết định RESTRICT nhưng API không có chế độ restrict | Deny/challenge thay vì allowAll |
| T34 | Một alert SIEM sai | Không kết luận compromise nếu thiếu điều tra |
| T35 | Đổi threshold không có approval/version | Deployment control chặn |
| T36 | Rollback threshold trong outage | Audit và kiểm tra hard deny còn hiệu lực |
| T37 | Score cùng mức ở READ và EXPORT | Outcome khác theo impact policy |
| T38 | Signal false positive khi người dùng đi công tác | Remediation/appeal không bỏ authorization |
| T39 | Target không có log enforcement | Mark UNVERIFIED, không PASS |
| T40 | Risk policy thiếu coverage cho resource mới | Fail-safe/explicit policy default |

**Test ở unit level** cần đi cùng **integration tests tại IdP, PDP, PEP, SaaS/resource server, cloud IAM và workload identity**. Sử dụng **fake clock, test principals, test tenants và dữ liệu được phép**, không tự khóa hay đổi chính sách production chỉ để thử một threshold.

## 48. Bài tập thiết kế threshold

### Bài tập A — Phân band đúng ranh giới

Cho policy:

~~~text
LOW       0 <= score < 30
MEDIUM   30 <= score < 60
HIGH     60 <= score < 85
CRITICAL 85 <= score <= 100
UNKNOWN  missing/invalid/untrusted
~~~

Hãy phân loại các giá trị **29.9, 30, 60, 84.99, 85, null và 101**. Đáp án: **LOW, MEDIUM, HIGH, HIGH, CRITICAL, UNKNOWN, UNKNOWN**.

### Bài tập B — Xác định hard deny trước score

Một user có điểm 15 và passkey authentication thành công, nhưng cố export dữ liệu tenant khác. Đáp án: **DENY theo tenant authorization**, không cần đợi risk band.

### Bài tập C — Risk service outage

SaaS thanh toán không nhận được điểm risk. Việc đọc trang hướng dẫn có thể tiếp tục theo policy; hành động tạo API key production cần **DENY hoặc chờ trusted evidence**. Đáp án phụ thuộc **action classification và approved failure mode**, không được phép fallback ALLOW_ALL.

### Bài tập D — Mover với token cũ

User bị rút role AtlasAdmin lúc 10:00, token cũ hết hạn 10:20. Risk LOW lúc 10:05. Đáp án: **không ALLOW AtlasAdmin**, phải có revocation/online policy hoặc cơ chế đạt SLA quyền hiện hành; báo finding nếu API còn cho qua.

## 49. Câu hỏi tự kiểm tra

**Câu 1. Risk score bằng 0 có nghĩa được phép truy cập không?**

Không. Phải xác thực và thỏa base authorization, hard controls, tenant, resource/action policy; score thấp chỉ là một tín hiệu hỗ trợ.

**Câu 2. Risk score 80/100 có nghĩa 80% khả năng bị hack không?**

Không mặc nhiên. Chỉ có thể diễn giải như xác suất nếu mô hình đã được calibration và validation tương ứng.

**Câu 3. Nếu điểm risk bằng đúng ngưỡng 60 thì vào band nào trong ví dụ?**

**HIGH** vì MEDIUM kết thúc ngay trước 60.

**Câu 4. MFA step-up thành công có làm user có quyền mới không?**

Không. MFA tăng assurance, không thay approval/RBAC/ABAC/SoD.

**Câu 5. Nếu score không lấy được thì có thể lấy LOW mặc định không?**

Không. Phải dùng UNKNOWN/INDETERMINATE và failure mode theo risk policy.

**Câu 6. Vì sao cùng score nhưng export có thể bị chặn còn read thường được cho?**

Do resource impact/action sensitivity và requirements khác nhau.

**Câu 7. Hysteresis có được giữ Permit sau Leaver không?**

Không. Hard deny và quyền đã hết hiệu lực không thể bị kéo dài nhờ hysteresis.

**Câu 8. Workload token còn hạn nhưng federation subject sai thì xử lý?**

Từ chối theo trust và token validation; không dùng điểm risk thấp để hợp thức hóa.

**Câu 9. Có cần đánh giá risk lại trong phiên?**

Có khi action tăng sensitivity, device/identity/token state đổi hoặc policy yêu cầu; không chỉ nhìn sign-in risk.

**Câu 10. Vì sao phải giữ modelVersion và policyVersion trong audit?**

Để giải thích ngưỡng đã dùng, so kết quả giữa các giai đoạn và điều tra drift/rollback; nếu thiếu có thể kết luận sai theo chính sách hiện tại thay vì thời điểm xảy ra sự kiện.

## 50. Checklist triển khai Risk threshold

| Câu hỏi | Bằng chứng/kiểm soát |
| --- | --- |
| Đã phân biệt risk score, band, threshold và outcome? | Risk model contract và policy glossary |
| Đã có policy owner và risk appetite? | Approval/reference, phạm vi resource |
| Có hard deny tách score? | No permission, inactive, tenant mismatch, revoked credential |
| Có ngưỡng bao phủ chính xác 0–100? | Boundary unit tests, no gap/overlap |
| Có xử lý NaN/Infinity/null/out of range? | UNKNOWN/INDETERMINATE outcome |
| Có phân risk scope user/session/device/workload/transaction? | Feature contract và correlation |
| Signal có provenance/source authority? | Issuer, MDM/PIP, assessedAt, version |
| Có freshness threshold cho resource nhạy cảm? | Cache/PIP TTL và tests |
| Có phân action/resource sensitivity? | Resource catalog và impact matrix |
| Có authorization ở backend/PEP? | Object/action/tenant tests |
| MFA step-up có assurance/freshness phù hợp? | IdP verification, auth_time, policy |
| Step-up thành công có đánh giá lại base permission? | Re-evaluation, loop guard |
| Cache ALLOW có bị vô hiệu sau revoke? | Security epoch/invalidation/recheck |
| Risk UNKNOWN có đường xử lý an toàn? | Fail-safe per action và approved fallback |
| Có JIT/PAM/SoD cho quyền đặc biệt? | Approval, lease, target audit |
| Có xử lý emergency khi risk service lỗi? | Playbook giới hạn scope/expiry và hậu kiểm |
| Có workload-specific trust rules? | Issuer/subject/audience/role/owner |
| Có device posture/lost-state integration? | Registry/MDM/PKI evidence |
| Joiner trước startAt có Deny dù risk LOW? | HRIS effectiveAt + negative test |
| Mover role cũ có Deny dù token chưa exp? | Target authorization/readback |
| Leaver có chặn quyền theo SLA trước token exp? | Revocation/epoch/introspection và target Deny |
| Guest/contractor có sponsor/endAt? | Contract authority và access cutoff |
| Có kiểm soát approval và exception có hạn? | Independent owner, expiry, audit |
| Có version hóa policy/model? | Signed/diffed changes, rollback plan |
| Có shadow/canary và đo tác động? | Risk, FP/FN, availability reports |
| Có đo drift và signal outage? | Monitoring, model performance, source gap |
| Có biện pháp quyền riêng tư/fairness? | Minimized features, redaction, impact checks |
| Audit ghi decision và PEP outcome? | EventId, policyVersion, source/time/operation |
| Có negative tests ở API thật được ủy quyền? | Enforcement evidence trong phạm vi test |
| Có trạng thái UNVERIFIED khi thiếu target evidence? | Không đánh PASS khi chưa biết |

## 51. Tổng kết

**Risk threshold** là cơ chế chuyển **đánh giá rủi ro đã được xác minh** thành hành động kiểm soát như **ALLOW có điều kiện, STEP_UP, RESTRICT, DENY hoặc REVIEW**. Nó phải dựa trên **nguồn tín hiệu đáng tin, điểm/band có ngữ nghĩa rõ, ranh giới chính xác, độ mới dữ liệu, mức nhạy cảm của resource/action và chính sách có version**. Điểm rủi ro chỉ là một đầu vào; **không thể ghi đè quyền cơ sở, ranh giới tenant, hard deny, SoD hoặc trạng thái credential bị thu hồi**.

Trong quản lý vòng đời **Joiner–Mover–Leaver**, **HRIS/nguồn bảo trợ** xác định căn cứ và thời hạn làm việc; **IAM/IGA** quản lý expected entitlements và approval; **IdP/SSO/MFA** cung cấp authentication assurance; **SCIM** đồng bộ user/group; **OAuth/OIDC và credential lifecycle** quản lý token/grant; còn **RBAC/ABAC/PBAC, PDP/PEP và resource server** phải thực thi quyền tại từng tài nguyên. **Non-human identities, devices, privileged/PAM và emergency paths** cần signals, thresholds, trust và bằng chứng riêng.

Một triển khai có chất lượng cần **xử lý UNKNOWN không phải LOW, re-evaluate khi ngữ cảnh thay đổi, bảo vệ cache khỏi stale Permit, hiệu chỉnh threshold bằng dữ liệu, kiểm soát false positives/fairness/privacy, version hóa và kiểm toán quyết định, và xác minh quyền đã thật sự bị từ chối ở hệ thống đích**. Mục tiêu là **giảm nguy cơ truy cập trái phép mà không nhầm điểm rủi ro thấp với quyền tồn tại mãi mãi**, từ đó hạn chế đặc quyền thừa và **quyền truy cập tồn dư**.
