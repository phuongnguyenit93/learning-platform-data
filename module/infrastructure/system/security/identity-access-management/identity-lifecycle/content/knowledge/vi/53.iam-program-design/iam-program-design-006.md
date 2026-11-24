# Xác định approval khi thiết kế chương trình IAM

Trong chương trình **Identity and Access Management (IAM)**, xác minh được một người là nhân viên và có tài khoản hợp lệ chưa đủ để cấp cho người đó quyền truy cập dữ liệu khách hàng, hệ thống tài chính hoặc môi trường production. Tổ chức cần trả lời: **quyền này có thực sự cần cho công việc không, ai được phép chấp thuận, cần điều kiện gì, có hiệu lực trong bao lâu và làm sao biết quyền đã được cấp hoặc thu hồi đúng quyết định?**

**Approval** (phê duyệt) là một quyết định có trách nhiệm của chủ thể được ủy quyền đối với một yêu cầu hoặc thay đổi thuộc phạm vi kiểm soát. Trong IAM, approval thường xuất hiện ở yêu cầu cấp quyền, tăng đặc quyền, gia hạn quyền, ngoại lệ chính sách hoặc thay đổi owner. Approval cần gắn với một **đối tượng cụ thể, phạm vi, lý do nghiệp vụ, thời điểm hiệu lực và bằng chứng kiểm toán**.

Bài học thuộc chương **Thiết kế chương trình IAM** của module `SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE`, tập trung vào vòng đời **Joiner–Mover–Leaver (JML)** và các thành phần IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, rà soát quyền, kiểm toán và giảm quyền truy cập tồn dư.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **approval** với xác minh danh tính, xác thực, ủy quyền lúc truy cập, cấp phát quyền và access review.
2. Thiết kế **approval matrix** cho quyền cơ sở, quyền theo role, dữ liệu nhạy cảm, quyền quản trị, quyền tạm thời và tài khoản phi con người.
3. Xác định **ai có thẩm quyền phê duyệt**, thứ tự phê duyệt, điều kiện thay người, thời hạn và cách xử lý khi không có approver hợp lệ.
4. Áp dụng **least privilege**, **Separation of Duties (SoD)**, kiểm tra tính đủ điều kiện và thời hạn quyền trong một quy trình approval.
5. Kết nối kết quả phê duyệt với provisioning qua IdP/SCIM/API/PAM và **xác nhận trạng thái thực tế ở hệ thống đích**.
6. Xử lý approval trong Joiner, Mover, Leaver, trường hợp khẩn cấp, quyền dịch vụ, hợp đồng nhà thầu và yêu cầu thay đổi khi đang chờ duyệt.
7. Xây dựng trạng thái workflow, hợp đồng dữ liệu, bộ kiểm thử và chỉ số đo lường hiệu quả.

## 2. Approval là gì và khác các quyết định IAM khác như thế nào?

**Approval** trả lời câu hỏi: *chủ thể có thẩm quyền đã chấp thuận yêu cầu truy cập hoặc ngoại lệ cụ thể này chưa?* Nó là một phần của quản trị quyền, nhưng **không thay thế** các kiểm tra chính sách hoặc việc thực thi ở hệ thống đích.

| Khái niệm | Câu hỏi chính | Ví dụ |
|---|---|---|
| **Identity proofing / verification** | Danh tính có được xác minh đáng tin cậy không? | HR xác minh hồ sơ nhân viên; bộ phận đối tác xác thực danh tính nhà thầu. |
| **Authentication** | Ai đang đăng nhập và có đáp ứng yêu cầu xác thực không? | IdP xác thực MFA, phát phiên SSO. |
| **Eligibility check** | Chủ thể có đủ điều kiện để được xét quyền này không? | Chỉ nhân viên thuộc đơn vị cho phép mới có thể yêu cầu role quản lý tài chính. |
| **Approval** | Ai được ủy quyền đã đồng ý cho yêu cầu cụ thể? | Owner ứng dụng duyệt quyền đọc dữ liệu tài chính trong 30 ngày. |
| **Authorization** | Hành động cụ thể hiện có được cho phép trên tài nguyên này không? | API kiểm tra role, tenant và điều kiện ABAC trước khi trả dữ liệu. |
| **Provisioning** | Thao tác tạo account, cấp/gỡ entitlement đã được gửi tới đích và thực hiện chưa? | SCIM gán nhóm ở SaaS; PAM cấp role quản trị theo phiên. |
| **Access review / certification** | Quyền hiện có có còn cần thiết và hợp lệ không? | Owner tái chứng nhận quyền quý này. |
| **Audit / reconciliation** | Có chứng minh được quyết định và trạng thái quyền thực tế không? | Ghi request, approver, lý do và trạng thái entitlement đọc lại từ SaaS. |

Ví dụ: quản lý phê duyệt role `PROD_DB_ADMIN` không có nghĩa nhân viên ngay lập tức được vào cơ sở dữ liệu. IAM vẫn phải kiểm tra policy, thời hạn, xung đột SoD, xác thực mạnh và cấp quyền qua nền tảng phù hợp; database hoặc PAM phải xác nhận quyền đã thực sự có hiệu lực.

Ngược lại, nếu yêu cầu đã bị từ chối nhưng application owner tự thêm user vào nhóm local, đó là **quyền ngoài luồng** cần phát hiện khi đối soát. Một chương trình IAM tốt kiểm soát cả **đường ra quyết định** và **đường thực thi**.

## 3. Không phải quyền nào cũng cần phê duyệt thủ công

Thiết kế approval phải cân bằng **tự động hóa quyền hợp lệ** và **xem xét độc lập đối với quyền có rủi ro**. Yêu cầu mọi quyền đều phải có người bấm duyệt tạo tắc nghẽn, tăng nguy cơ duyệt theo thói quen. Nhưng tự động duyệt quyền đặc biệt chỉ vì người yêu cầu có chức danh phù hợp cũng nguy hiểm.

Một phân loại thực tế:

| Loại quyền hoặc thay đổi | Phương án approval điển hình | Điều kiện quan trọng |
|---|---|---|
| **Birthright / baseline** | Auto-grant theo policy được duyệt trước | Identity hợp lệ, nhóm danh tính phù hợp, đúng thời điểm hiệu lực, scope tối thiểu. |
| **Role nghiệp vụ thông thường** | Auto hoặc manager approval tùy rủi ro | Có nhu cầu công việc, role trong catalog, điều kiện gán đúng. |
| **Truy cập dữ liệu nhạy cảm** | Data owner/app owner approval, có thể thêm manager | Kiểm tra phạm vi dữ liệu, mục đích sử dụng, thời hạn và SoD. |
| **Quyền quản trị production** | Phê duyệt đặc quyền hoặc luồng PAM/JIT theo chính sách | MFA, lý do, ticket/sự cố, giới hạn tài nguyên, expiry ngắn và audit phiên. |
| **Yêu cầu vượt role chuẩn** | Exception approval có owner rủi ro | Biện pháp bù trừ, người chịu trách nhiệm và ngày hết hạn. |
| **Gia hạn quyền tạm thời** | Phê duyệt lại dựa trên nhu cầu hiện hành | Không tự gia hạn vì trước đó từng được chấp thuận. |
| **Thay đổi quyền do Mover** | Re-evaluate; quyền mới có thể cần approval | Thu hồi quyền cũ không còn hợp lệ; kiểm tra SoD khi chuyển vai trò. |
| **Leaver/hết hợp đồng** | Thu hồi bắt buộc theo nguồn vòng đời | Không chờ quản lý chấp thuận mới vô hiệu hóa quyền đã hết hiệu lực. |
| **Service/workload role** | Service owner và resource/security owner theo rủi ro | Dựa vào `serviceId`, mục đích, môi trường; không mượn danh tính kỹ sư tạo account. |

**Approval thủ công không phải bằng chứng một quyền là an toàn.** Tự động cấp quyền baseline cũng không đồng nghĩa thiếu kiểm soát: policy baseline phải được phê duyệt ở cấp **thiết kế chính sách**, có version, owner và kiểm tra định kỳ.

### Phê duyệt policy và phê duyệt từng yêu cầu

Phân biệt hai loại trách nhiệm:

1. **Policy-level approval:** chủ sở hữu quy trình và bảo mật thông qua quy tắc, chẳng hạn “nhân viên đang active được cấp quyền cổng thông tin nội bộ”.
2. **Request-level approval:** người được ủy quyền xét một yêu cầu cụ thể, chẳng hạn “nhân viên B được quyền xuất dữ liệu tenant VN đến ngày 30/11”.

Với chính sách cấp tự động đã duyệt, từng Joiner có thể không cần bấm duyệt lại. Với quyền nhạy cảm, mỗi assignment có thể cần quyết định riêng hoặc một yêu cầu được phê duyệt trong phạm vi rõ ràng.

## 4. Xác định người có thẩm quyền phê duyệt

Không nên mặc định **quản lý trực tiếp có quyền duyệt mọi tài nguyên**. Quản lý thường biết nhân viên có cần làm công việc đó không; application owner hoặc data owner hiểu quyền kỹ thuật và độ nhạy của tài nguyên.

| Vai trò trách nhiệm | Phê duyệt hoặc xác nhận nội dung gì? | Giới hạn |
|---|---|---|
| **Requester** | Gửi yêu cầu, nêu lý do, scope và thời gian | Không tự phê duyệt yêu cầu của mình. |
| **Subject / beneficiary** | Người hoặc workload sẽ nhận quyền | Có thể khác requester; cần nhận diện chính xác để tránh duyệt nhầm. |
| **Line manager / sponsor** | Nhu cầu công việc, quan hệ với tổ chức, dự án hoặc hợp đồng | Không thay data owner quyết định phạm vi dữ liệu nhạy cảm. |
| **Application owner** | Vai trò và entitlement tại ứng dụng | Không tự ghi đè trạng thái nguồn nhân sự/bảo mật. |
| **Data owner** | Mục đích, phân loại dữ liệu, tenant và giới hạn truy cập | Phải có authority đối với dữ liệu được đề nghị. |
| **Privileged access / security owner** | Đặc quyền, SoD, rủi ro bảo mật và ngoại lệ | Không tự bỏ qua quy trình audit hoặc thời hạn. |
| **Service owner** | Nhu cầu và vòng đời quyền của workload | Phải liên kết với service/workload đang tồn tại và có owner hợp lệ. |
| **IAM automation / IGA** | Thực thi policy, điều phối và kiểm tra điều kiện | Không tự thay thế quyết định chủ thể có thẩm quyền khi policy yêu cầu phê duyệt. |
| **Target application / PAM** | Thực hiện thay đổi quyền và xác nhận kết quả | Phản hồi kỹ thuật không tương đương phê duyệt nghiệp vụ. |

### Từ owner sang approver cụ thể

Một approval policy không nên chỉ ghi “manager duyệt” mà cần xác định:

- **Authority source:** lấy manager, sponsor, data owner hoặc application owner từ hệ thống nào?
- **Resolution rule:** với identity và tài nguyên này, ai là người có thẩm quyền hiện hành?
- **Conflict rule:** nếu approver chính là requester, người nhận quyền hoặc có xung đột lợi ích, ai được chuyển tới?
- **Delegation rule:** người được ủy quyền có được duyệt loại quyền này không, trong khoảng thời gian nào?
- **Fallback / escalation:** owner vắng mặt, dữ liệu thiếu hoặc SLA trễ thì chuyển tới ai?
- **Decision evidence:** quyết định được ghi bởi danh tính nào, có MFA/step-up phù hợp và thời điểm nào?

Ví dụ user gửi yêu cầu đọc dataset thuộc tenant VN. Approver phải là **owner có thẩm quyền của dataset trong tenant VN**, không chỉ là người có tên gần giống trong directory hoặc một thành viên ngẫu nhiên của nhóm quản trị.

### Ma trận phân quyền phê duyệt

| Yêu cầu | Kiểm tra tự động | Approver thứ nhất | Approver bổ sung |
|---|---|---|---|
| Quyền cổng thông tin nội bộ | Employment active, scope phù hợp | Không cần nếu policy baseline đã duyệt | Không |
| Role xử lý đơn hàng | Role eligibility, account scope, SoD | Line manager | App owner nếu quyền vượt chuẩn |
| Đọc dữ liệu tài chính nhạy cảm | Data classification, tenant, expiry | Manager/sponsor xác nhận nhu cầu | Data owner phê duyệt scope dữ liệu |
| Nâng quyền production | Chứng thực mạnh, thay đổi/ticket, expiry, SoD | Privileged owner hoặc on-call được ủy quyền | Security/production owner theo mức rủi ro |
| Tạo service principal production | Service record, environment, owner | Service owner | Resource owner/security owner |
| Gia hạn ngoại lệ SoD | Xung đột, compensating controls, risk tier | Business process owner | Chủ thể có thẩm quyền chấp nhận rủi ro |

Đây là mẫu tham khảo. Cấu hình thực tế phải phản ánh cơ cấu trách nhiệm và phân loại tài nguyên của tổ chức; không tự coi một luồng nhiều approver là an toàn nếu tất cả có cùng xung đột lợi ích.

## 5. Điều kiện phải kiểm tra trước và sau approval

Approval cần gắn với policy model; một người đồng ý **không thể hợp thức hóa một yêu cầu trái điều kiện bắt buộc**.

### Kiểm tra trước khi gửi yêu cầu

1. **Danh tính:** `identityId`, identity type, khóa nguồn, status và khoảng hiệu lực có đáng tin cậy?
2. **Mục đích:** công việc/incident/ticket nào cần quyền, lý do đủ cụ thể?
3. **Tài nguyên:** system, tenant, environment, resource và entitlement nào?
4. **Eligibility:** điều kiện RBAC/ABAC và quyền cơ sở có cho phép yêu cầu này không?
5. **Risk:** quyền có đặc quyền, dữ liệu nhạy cảm, tác động cross-tenant hoặc ngoại lệ SoD không?
6. **Thời gian:** startAt, endAt, giới hạn duration, gia hạn và lịch rà soát?
7. **Không trùng lặp:** đã có quyền qua một assignment hợp lệ khác hay một yêu cầu đang chờ chưa?

Nếu thiếu dữ kiện bắt buộc, hệ thống cần yêu cầu bổ sung hoặc chuyển xử lý phù hợp, không tự động phê duyệt dựa trên dữ liệu mặc định.

### Kiểm tra lại tại thời điểm cấp quyền

Thời gian giữa khi tạo request, khi approver bấm duyệt và khi SCIM/API thực thi có thể kéo dài. Trong khoảng đó, nhân viên có thể nghỉ việc, thay phòng ban hoặc tài nguyên chuyển owner. Do đó **trước provisioning** cần xác minh lại:

- Quan hệ và trạng thái danh tính vẫn đủ điều kiện;
- `securityHold` hoặc các điều kiện cấm không xuất hiện;
- scope/tenant/entitlement vẫn đúng yêu cầu đã duyệt;
- approver và quyết định còn hợp lệ, chưa hết hạn hoặc bị thu hồi;
- policy version và các quy tắc SoD không bị vi phạm;
- target account là account của đúng chủ thể được duyệt.

**Approval chỉ có giá trị đối với yêu cầu đã được xác định.** Nếu người yêu cầu sửa role từ read-only thành admin hoặc thay tenant sau khi được duyệt, quyết định trước đó không được tự áp cho nội dung mới.

## 6. Thiết kế đơn vị yêu cầu và hợp đồng dữ liệu

Một approval record cần chứa đủ dữ kiện để khi kiểm toán có thể trả lời: **ai xin quyền gì, cho ai, vì sao, do ai duyệt, theo policy nào, hiệu lực bao lâu và đích có thực thi không?**

| Trường | Ý nghĩa |
|---|---|
| `requestId` và `requestVersion` | Định danh ổn định, hỗ trợ chống xử lý trùng và sửa nội dung sau khi phê duyệt. |
| `requesterIdentityId` | Người gửi yêu cầu; có thể khác người nhận quyền. |
| `subjectIdentityId` hoặc `serviceId` | Danh tính/workload được nhận quyền. |
| `sourceRef` | Nguồn có thẩm quyền xác nhận trạng thái vòng đời hoặc owner. |
| `systemId`, `tenantId`, `resourceScope` | Hệ thống đích và phạm vi tài nguyên cụ thể. |
| `requestedEntitlements` | Role, permission hoặc nhóm yêu cầu. |
| `reason`, `businessTicket` | Lý do nghiệp vụ và tham chiếu công việc. |
| `effectiveFrom`, `effectiveUntil` | Thời hạn sử dụng, phân biệt với hạn trả lời approval. |
| `policyId`, `policyVersion` | Chính sách quyết định người duyệt và điều kiện kiểm tra. |
| `riskTier`, `sodResult` | Phân loại rủi ro và tình trạng xung đột quyền. |
| `approvalSteps` | Các bước, approver, delegated authority, quyết định và thời điểm. |
| `decisionState` | Trạng thái phê duyệt riêng với trạng thái cấp quyền. |
| `provisioningState` | Kết quả thực hiện và đọc lại quyền tại hệ thống đích. |
| `correlationId`, `auditRefs` | Liên kết request với sự kiện JML, action và bằng chứng. |

Ví dụ bản ghi yêu cầu có cấu trúc:

~~~json
{
  "requestId": "ar-2048",
  "requestVersion": 3,
  "requesterIdentityId": "idn-1050",
  "subjectIdentityId": "idn-1050",
  "scope": {
    "systemId": "reporting",
    "tenantId": "VN",
    "environment": "production",
    "resourceScope": "finance-approved-reports"
  },
  "requestedEntitlements": ["FINANCE_REPORT_EXPORT"],
  "reason": "Xuất báo cáo đã phê duyệt cho kỳ đối soát",
  "businessTicket": "FIN-2048",
  "effectiveFrom": "2026-11-25T08:00:00+07:00",
  "effectiveUntil": "2026-12-01T18:00:00+07:00",
  "policyRef": {
    "id": "finance-report-elevated-access",
    "version": 5
  },
  "riskTier": "HIGH",
  "decisionState": "PENDING_APPROVAL",
  "provisioningState": "NOT_STARTED",
  "correlationId": "corr-10298"
}
~~~

Đây là **schema minh họa**, không phải giao diện của một sản phẩm IAM cụ thể. Tách `decisionState` và `provisioningState` giúp tránh hiểu sai rằng “đã được duyệt” tức “quyền đã được cấp thành công”.

### Phê duyệt phải khóa nội dung được chấp thuận

Một cách kiểm soát là gắn mỗi quyết định với `requestId + requestVersion` và **tập trường quan trọng** (người nhận, entitlement, hệ thống, tenant, scope, khoảng thời gian). Nếu bất kỳ trường nào làm thay đổi rủi ro hoặc ý nghĩa yêu cầu, hệ thống phải tạo version mới và xét duyệt lại theo policy.

Khi quyền được bổ sung sau approval, không nên chỉ chỉnh một dòng database rồi dùng quyết định cũ. Cần giữ bản gốc hoặc nhật ký bất biến để điều tra sau này.

## 7. Workflow approval từ yêu cầu đến xác nhận quyền

Một workflow không chỉ gồm hai nút “Approve” và “Reject”. Nó cần thể hiện các trạng thái nghiệp vụ, điều kiện chuyển, xử lý quá hạn và đường đi sau phê duyệt.

~~~mermaid
flowchart TD
    A["Submit request<br/>subject + scope + reason + expiry"] --> B["Validate identity, policy, SoD"]
    B --> C{"Eligible?"}
    C -- "No" --> D["Reject / request correction<br/>log reason"]
    C -- "Yes" --> E{"Preapproved birthright policy?"}
    E -- "Yes" --> H["Authorize assignment<br/>policy evidence"]
    E -- "No" --> F["Resolve approvers<br/>authority + independence"]
    F --> G{"All required decisions approved?"}
    G -- "Rejected / expired" --> D
    G -- "Pending" --> W["Remind / escalate<br/>no automatic grant"]
    W --> G
    G -- "Yes" --> H
    H --> I["Revalidate identity, scope, SoD<br/>and approval freshness"]
    I --> J{"Still valid?"}
    J -- "No" --> D
    J -- "Yes" --> K["Provision via IdP / SCIM / API / PAM"]
    K --> L["Read target state + reconcile"]
    L --> M{"Confirmed?"}
    M -- "No" --> N["Retry / incident / owner<br/>keep fulfillment open"]
    N --> L
    M -- "Yes" --> O["Record grant + expiry<br/>audit and review"]
~~~

Trong thực tế, một quyết định bị từ chối khi **approval đã từng được chấp thuận nhưng điều kiện cấp quyền trở nên không hợp lệ** nên có trạng thái như `CANCELLED_STALE` hoặc `BLOCKED_BY_POLICY`, không nhất thiết gọi đó là “approver đã từ chối”. Điểm quan trọng là phân biệt nguyên nhân và giữ evidence.

### Hai trạng thái song song

**Trạng thái quyết định (decision):**

~~~text
DRAFT -> SUBMITTED -> PENDING_APPROVAL
                      |-> APPROVED
                      |-> REJECTED
                      |-> EXPIRED
                      |-> CANCELLED

APPROVED -> INVALIDATED (nếu dữ kiện hoặc scope đã thay đổi)
~~~

**Trạng thái thực thi (fulfillment):**

~~~text
NOT_STARTED -> PLANNED -> DISPATCHED -> IN_PROGRESS
                                        |-> CONFIRMED
                                        |-> FAILED -> RETRYING
                                        |-> EXCEPTION

CONFIRMED -> EXPIRED / REVOKED (có readback tại hệ thống đích)
~~~

Ví dụ `APPROVED + FAILED` nghĩa là quyết định phê duyệt tồn tại nhưng việc cấp quyền gặp lỗi. `APPROVED + CONFIRMED` cho thấy quyền đã được cấp và có bằng chứng. `EXPIRED` ở đây phải có ngữ nghĩa riêng cho **hạn trả lời duyệt** và **hạn quyền truy cập**, tránh gộp thành một trường mơ hồ.

## 8. Xác định approval policy theo loại quyền và rủi ro

Một **approval policy** cần quyết định:

- yêu cầu nào được cấp tự động theo role/policy đã duyệt;
- yêu cầu nào phải xin approval;
- ai có authority với loại entitlement và resource cụ thể;
- cần bao nhiêu bước, thứ tự và điều kiện tách biệt người xét;
- khi nào request hết hạn hoặc cần phê duyệt lại;
- có yêu cầu step-up authentication, ticket, đào tạo, xác nhận thiết bị hoặc kiểm tra SoD nào;
- khi nào quyền phải tự động thu hồi, rà soát hoặc chuyển ngoại lệ.

Ví dụ YAML minh họa:

~~~yaml
# Cấu trúc minh họa, không phải schema chạy trực tiếp của công cụ IAM.
approvalPolicy:
  id: prod-privileged-access
  version: 5
  ownerTeam: InfrastructureSecurity
  appliesTo:
    identityTypes: [EMPLOYEE, CONTRACTOR]
    entitlementRiskTier: CRITICAL
    environments: [production]
  eligibility:
    requireActiveRelationship: true
    requireNoSecurityHold: true
    requireNamedIdentity: true
    requireBusinessTicket: true
    requireSodCheck: true
  approvalSteps:
    - id: business-need
      authority: LINE_MANAGER_OR_CONTRACT_SPONSOR
      allowSelfApproval: false
    - id: resource-risk
      authority: PRIVILEGED_RESOURCE_OWNER
      allowSelfApproval: false
      distinctFromPreviousApprover: true
  assignment:
    maxDuration: PT2H
    requireStepUpMfa: true
    useJustInTimeGrant: true
  decision:
    expiresIfNotCompletedWithin: PT24H
    invalidateOnSubjectOrScopeChange: true
    defaultOnMissingApprover: ESCALATE_WITHOUT_GRANT
  fulfillment:
    requireTargetReadback: true
    revokeOnExpiry: true
    alertOnFailure: true
  review:
    owner: InfrastructureSecurity
    cadence: P90D
~~~

Thời hạn `PT2H`, `PT24H` và `P90D` chỉ là ví dụ để minh họa cách ghi duration; giá trị thật phải theo đánh giá rủi ro. `distinctFromPreviousApprover` là điều kiện policy cụ thể: nếu không tìm được hai approver độc lập, phải chuyển xử lý, không tự động bỏ bước.

### Tính nhất quán giữa policy và luồng thực thi

Hệ thống cần phân biệt:

1. **Approval cho phép tạo assignment** trong khoảng thời gian và scope đã duyệt.
2. **Provisioning tạo entitlement thực tế** bằng connector phù hợp.
3. **Runtime authorization** tiếp tục kiểm tra điều kiện hiện hành khi người dùng thao tác.

Một assignment đã duyệt không vượt qua lệnh `securityHold=true`, trạng thái quan hệ `TERMINATED` hay ABAC chặn truy cập sai tenant. Nếu nguồn danh tính thay đổi sau approval, quyết định phải được đánh giá lại.

## 9. Quản lý Separation of Duties (SoD) khi phê duyệt

**Separation of Duties** nhằm ngăn một chủ thể tự thực hiện toàn bộ chuỗi thao tác có xung đột lợi ích hoặc tự mở rộng quyền cho mình.

### SoD trong workflow

Các kiểm tra cần thiết:

- **Requestor–approver:** requester không tự phê duyệt yêu cầu của chính mình.
- **Beneficiary–approver:** người nhận quyền không tự duyệt quyền của chính mình, kể cả request do người khác gửi.
- **Approver–fulfillment:** nếu quy trình yêu cầu độc lập, người phê duyệt không tự ý vượt luồng bằng cách cấp quyền trực tiếp ngoài hệ thống.
- **Manager–resource owner:** hai bước độc lập không được âm thầm hợp nhất thành một nếu policy yêu cầu hai người khác nhau.
- **Delegation:** người được ủy quyền phải có đủ authority và không vướng xung đột như approver gốc.

### SoD của quyền được yêu cầu

Ngay cả khi hai approver độc lập đồng ý, IAM vẫn phải kiểm tra các **quyền xung đột**:

| Loại SoD | Ví dụ | Điểm kiểm tra |
|---|---|---|
| **Static SoD** | Không cho cùng người giữ `EXPENSE_APPROVER` và `PAYMENT_EXECUTOR` nếu chính sách cấm. | Khi tạo assignment và khi Mover. |
| **Dynamic SoD** | Người tạo khoản chi không được phê duyệt đúng khoản đó. | Ứng dụng/API khi xử lý giao dịch. |
| **Workflow SoD** | Requester không tự xét và tự cấp quyền của mình. | Approval workflow và hệ thống provisioning. |
| **Privileged SoD** | Không cho người quản trị IAM tự cấp đặc quyền production mà thiếu kiểm soát độc lập. | IAM, PAM, cloud authorization và audit. |

**Một approval hợp lệ không được vượt qua SoD bắt buộc.** Ngoại lệ SoD, nếu tổ chức cho phép, phải có owner rủi ro, bằng chứng kiểm soát bù trừ, thời hạn và phê duyệt riêng. Không phải mọi loại vi phạm SoD đều có thể được chấp thuận.

## 10. Approval trong Joiner–Mover–Leaver

### 10.1. Joiner — tách quyền cơ sở với quyền nhạy cảm

Một sự kiện `EMPLOYMENT_STARTED` từ HRIS có thể khiến IAM:

1. Xác minh danh tính, tình trạng quan hệ và thời điểm có hiệu lực.
2. Chuẩn bị tài khoản IdP và ứng dụng thuộc account scope.
3. Cấp những quyền **birthright** theo policy đã duyệt.
4. Tạo yêu cầu approval cho role đặc biệt nếu người mới thực sự cần.
5. Cấp quyền sau khi phê duyệt và kiểm tra lại điều kiện tại thời điểm thực thi.
6. Đối soát group/entitlement ở đích rồi thông báo trạng thái thực tế.

Ví dụ, nhân viên mới thuộc bộ phận tài chính được phép truy cập portal nội bộ theo role cơ sở, nhưng quyền `PAYMENT_EXECUTOR` cần manager và chủ hệ thống thanh toán duyệt độc lập. Một bản ghi HRIS `department=Finance` không tự chứng minh người đó cần quyền thanh toán.

### 10.2. Mover — quyền cũ phải được rà soát và thu hồi

Khi người dùng chuyển vai trò công việc, IAM tính lại các role dự kiến từ nguồn có thẩm quyền và approval còn hiệu lực:

~~~text
desiredRoles = evaluateCurrentIdentityAttributesAndValidApprovals()
actualRoles  = observeAssignedRolesAtTargets()

rolesToRevoke = actualRoles - desiredRoles
rolesToGrant  = desiredRoles - actualRoles

revokeObsoleteAndConflictingRoles()
verifyHighRiskRevocations()
requestApprovalForNewSensitiveRoles()
revalidateEligibilityAndSoD()
provisionApprovedRoles()
reconcileActualAccess()
~~~

Giả mã mô tả nguyên tắc; thực tế cần xét **scope, nguồn gốc assignment và entitlement được nhiều role cùng cấp**. Không được gỡ một quyền vẫn có căn cứ cấp hợp lệ khác; cũng không được giữ quyền trực tiếp không có căn cứ chỉ vì role catalog không quản lý nó.

**Thu hồi quyền không còn hợp lệ không chờ approver mới đồng ý.** Approval áp dụng cho việc cấp hoặc gia hạn quyền phù hợp. Nếu policy đã xác định quyền cũ phải chấm dứt sau Mover, việc thu hồi phải được thực hiện theo mốc hiệu lực và SoD, với bằng chứng ở hệ thống đích.

Ví dụ chuyển từ `EXPENSE_APPROVER` sang `PAYMENT_EXECUTOR`: cần bảo đảm quyền duyệt cũ đã bị gỡ hoặc được chặn theo biện pháp an toàn được thiết kế trước khi quyền thanh toán mới hoạt động. Tránh khoảng thời gian cùng giữ hai quyền xung đột do người phê duyệt phản hồi chậm.

### 10.3. Leaver — không dùng approval làm điều kiện để chặn truy cập

Khi HRIS/VMS xác nhận quan hệ đã kết thúc, IAM phải thực thi chính sách chấm dứt quyền theo thời điểm hiệu lực:

- khóa hoặc vô hiệu hóa đăng nhập ở IdP và hệ thống liên quan;
- gỡ role, nhóm và entitlement tại ứng dụng qua SCIM/API hoặc quy trình có bằng chứng;
- xử lý phiên, token, khóa API và tài khoản local theo khả năng kỹ thuật;
- đối soát trạng thái thực tế ở từng đích và xử lý sai lệch.

**Leaver không cần chờ quản lý bấm “Approve revoke”** nếu quan hệ đã hết hiệu lực theo nguồn có thẩm quyền và chính sách. Chờ phê duyệt để thu hồi là một nguyên nhân trực tiếp gây **quyền truy cập tồn dư**.

Nếu có nghĩa vụ lưu giữ hồ sơ, cần phân biệt **thu hồi truy cập** với **xóa dữ liệu hoặc account**. Các quyết định lưu giữ/xóa có thể cần phê duyệt riêng theo quy định, nhưng không làm chậm thao tác chặn truy cập đã bắt buộc.

### 10.4. Rehire và khôi phục tài khoản

Khi người từng nghỉ được tuyển lại, approval trước đây có thể đã hết hạn hoặc không còn phù hợp. Cần xác minh quan hệ mới, chính sách mới và owner hiện tại. **Không tự kích hoạt toàn bộ role nhạy cảm cũ** chỉ vì account hoặc identity nội bộ vẫn tồn tại trong lịch sử.

## 11. Approval cho tài khoản dịch vụ và workload

Tài khoản phi con người cần mô hình quyết định khác với quyền cá nhân. Người vận hành tạo một service principal **không tự động là owner nghiệp vụ lâu dài** của quyền đó.

Khi phê duyệt quyền cho service account/workload, cần ít nhất:

| Dữ kiện | Lý do |
|---|---|
| `serviceId` / `workloadId` | Xác định workload thật sự sử dụng quyền. |
| `businessOwner` / `technicalOwner` | Có owner chịu trách nhiệm nhu cầu và hoạt động. |
| `environment`, `resourceScope` | Ngăn dùng role dev ở production hoặc truy cập vượt hệ thống cần thiết. |
| `purpose` và tham chiếu triển khai | Chứng minh nhu cầu kỹ thuật, tránh role “chung cho tất cả”. |
| `credentialType` | Xem xét workload federation, chứng chỉ, khóa và chính sách luân chuyển. |
| `duration` / `reviewAt` | Hạn hoặc lịch rà soát quyền, đặc biệt quyền lâu dài. |
| `riskTier` và `approvers` | Xác định resource owner, service owner, security owner khi cần. |

Ví dụ robot tạo báo cáo đêm cần quyền đọc đúng dataset được duyệt. **Service owner** xác nhận công việc còn tồn tại, **data owner** xác nhận phạm vi dữ liệu, và policy chỉ provision quyền đọc tối thiểu cho workload identity ở production.

Nếu kỹ sư đang làm owner nghỉ việc, HRIS phát Leaver đối với quyền cá nhân của họ. Cần tạo tác vụ **chuyển giao owner và rà soát credential**, không tự xóa workload nếu dịch vụ vẫn hoạt động. Khi service catalog xác nhận workload kết thúc, quyền liên quan phải bị thu hồi theo lifecycle của dịch vụ.

## 12. Nhà thầu, đối tác và quyền truy cập có thời hạn

Một sponsor có thể xác nhận nhà thầu cần truy cập dự án, nhưng không có quyền phê duyệt mọi dữ liệu trong ứng dụng. Vì vậy cần phân biệt:

- **Sponsor approval:** nhu cầu dự án, trách nhiệm tổ chức, ngày kết thúc hợp đồng.
- **Resource approval:** quyền trên dataset/ứng dụng cụ thể và phạm vi tenant.
- **Security approval:** chính sách dành cho truy cập từ bên ngoài hoặc quyền có độ rủi ro cao.

Approval cho nhà thầu nên có `effectiveUntil` không vượt thời điểm kết thúc quan hệ đã được xác minh (trừ chính sách đặc biệt được quản trị riêng). Khi hợp đồng kết thúc sớm hoặc thay scope, quyền bị đánh giá lại và thu hồi theo sự kiện vòng đời, không cần chờ hết ngày trong request ban đầu.

**Gia hạn hợp đồng không tự gia hạn mọi quyền nhạy cảm.** Policy có thể yêu cầu sponsor và owner của tài nguyên tái xác nhận, đặc biệt nếu phạm vi công việc đã thay đổi.

## 13. Quy trình cấp quyền khẩn cấp và break-glass

Một số sự cố production đòi hỏi quyền truy cập nhanh. Thiết kế approval phải có đường **khẩn cấp được quản trị trước**, tránh để nhân viên tự chọn “emergency” để bỏ tất cả kiểm soát.

Một mẫu quy trình:

1. Sự cố hoặc nhiệm vụ khẩn cấp có mã tham chiếu và người chịu trách nhiệm.
2. Người yêu cầu được xác thực mạnh, thuộc nhóm đủ điều kiện và khai báo tài nguyên cần xử lý.
3. Approver on-call hoặc chính sách break-glass đã được phê duyệt xác định cách kích hoạt.
4. PAM/JIT cấp quyền tối thiểu trong thời gian ngắn, có ghi nhận phiên và cảnh báo ngay.
5. Khi hết hạn hoặc sự cố kết thúc, quyền được thu hồi và xác minh.
6. Chủ thể độc lập rà soát hậu kiểm, lý do sử dụng, thao tác đã làm và các ngoại lệ.

Break-glass account có thể cần hoạt động khi IdP chính gặp sự cố; vì vậy cần cơ chế bảo vệ credential, lưu giữ và giám sát riêng đã được thử nghiệm. **Đường khẩn cấp không được biến thành quyền đặc biệt vĩnh viễn** và không nên yêu cầu một approver không thể liên lạc để mở khóa hệ thống thiết yếu trong thảm họa nếu chính sách khôi phục đã định cơ chế thay thế an toàn.

## 14. Quản lý approver vắng mặt, xung đột hoặc phản hồi quá hạn

Trong thực tế, manager có thể nghỉ phép, application owner rời công ty, account approver bị vô hiệu hóa hoặc người được ủy quyền không đủ thẩm quyền.

Một workflow đáng tin cậy phải có **quy tắc resolution và escalation**, không tự chọn bất kỳ người nào có thể bấm nút.

| Trường hợp | Hành vi phù hợp |
|---|---|
| Manager chưa có trong HRIS | Chặn bước tự động tương ứng, yêu cầu sửa nguồn và chuyển tới owner được ủy quyền. |
| Approver là chính người nhận quyền | Chuyển tới approver độc lập theo policy; không tự duyệt. |
| App owner không hoạt động | Tra nguồn owner chính thức, chuyển tới người thay thế được ủy quyền hoặc hàng ngoại lệ. |
| Quyền đã có trong một assignment hợp lệ | Kiểm tra trùng lặp, chỉ yêu cầu gia hạn/thay scope nếu thật sự cần. |
| Approver không trả lời trước SLA | Nhắc, chuyển cấp hoặc đóng request; không mặc nhiên `APPROVED`. |
| Một bước từ chối | Đóng hoặc yêu cầu sửa theo policy; giữ lý do và bản ghi quyết định. |
| Bước trước đã duyệt nhưng yêu cầu đổi scope | Invalidated version cũ, xét duyệt lại phần thay đổi phù hợp policy. |
| Người dùng đã nghỉ trước khi phê duyệt xong | Hủy yêu cầu cấp, thu hồi quyền hiện có và ghi nhận sự kiện Leaver. |
| Có dấu hiệu bất thường trong approval | Tạm dừng cấp quyền nhạy cảm, cảnh báo và xác minh độc lập. |

Delegation phải có **người ủy quyền, người nhận ủy quyền, loại quyền được ủy quyền, giới hạn rủi ro, thời hạn, lý do và dấu vết audit**. Việc ủy quyền xét các quyền thông thường không nhất thiết cho phép người được ủy quyền duyệt quyền quản trị production.

## 15. An toàn quy trình: tránh sửa yêu cầu, duyệt lặp và cấp quyền sai

Approval là luồng có giá trị bảo mật. Ngoài logic nghiệp vụ, hệ thống cần kiểm soát những rủi ro kỹ thuật:

### Xác thực, phân quyền và bảo vệ quyết định

- Endpoint `approve(requestId)` phải xác thực người đưa ra quyết định và kiểm tra **quyền approver đối với đúng request version**.
- Client không được tự khai báo mình là resource owner hoặc tự thay `approverId` để hợp thức hóa quyền.
- Approval record phải liên kết với request cụ thể; không nhận một mã duyệt chung cho yêu cầu đã bị đổi subject, tenant hoặc entitlement.
- Cần ghi rõ người thực hiện, thời điểm, chính sách đang áp dụng, scope, lý do quyết định và kết quả.
- Với quyền nhạy cảm, yêu cầu step-up MFA hoặc xác thực phù hợp trước khi chấp thuận.

### Idempotency và xử lý đồng thời

Hai approver có thể bấm cùng lúc, một yêu cầu có thể được gửi nhiều lần hoặc người dùng thay đổi phòng ban trong khi workflow đang xử lý. Các hành động cần có **state transition hợp lệ** và kiểm tra version.

~~~text
approve(requestId, expectedVersion, approverId, decision):
    beginTransaction()
        request = loadRequestForUpdate(requestId)

        if request.version != expectedVersion:
            reject("stale-request-version")

        require(request.status == PENDING_APPROVAL)
        require(isAuthorizedApprover(approverId, request))
        require(independentFromRequesterAndBeneficiary(approverId, request))
        require(notAlreadyDecidedThisStep(request, approverId))

        recordImmutableDecision(request, approverId, decision)
        if allRequiredApprovalsSatisfied(request):
            transition(request, APPROVED)
            outbox.append(revalidationAndFulfillmentCommand(request))
    commit()

    # Worker fulfillment kiểm tra lại điều kiện rồi mới cấp quyền.
~~~

Đây là giả mã, không phải hàm có thể chạy trực tiếp. **Transactional outbox** là một phương án để tránh ghi approval thành công mà mất lệnh gửi cấp quyền; connector vẫn cần idempotency key và readback để tránh cấp/gỡ lặp khi retry.

### Kiểm soát trạng thái thay đổi giữa approval và fulfillment

Khi approval đã được duyệt, nhưng trước khi cấp quyền:

1. Xác minh request/version và approval chưa bị rút lại.
2. Đọc lại trạng thái identity/sponsor, quyền hiện có và `securityHold`.
3. Đánh giá policy và SoD phiên bản đang hiệu lực theo quy tắc quản trị thay đổi.
4. Xác định account đích bằng **native account ID + system/tenant**, không chỉ dựa vào email.
5. Chỉ cấp đúng entitlement, scope và expiry nằm trong quyết định.
6. Đọc lại trạng thái đích; nếu lỗi, đưa vào `FAILED`/`RETRYING` hoặc hàng ngoại lệ có owner.

Một quyền đã cấp nhưng chưa ghi được audit hoặc thiếu bằng chứng bắt buộc không nên được tuyên bố hoàn tất theo quy trình quản trị.

## 16. Liên kết approval với IdP, SSO, SCIM và policy engine

~~~mermaid
flowchart LR
    SRC["HRIS / VMS / Service Catalog<br/>Nguồn danh tính và quan hệ"] --> IGA["IAM / IGA<br/>Eligibility + request + approval"]
    ROLE["Role catalog / policy<br/>RBAC + ABAC + SoD"] --> IGA
    OWNER["Manager / App owner / Data owner<br/>Decisions"] --> IGA
    IGA --> CMD["Approved assignment<br/>scope + expiry + action"]
    CMD --> IDP["IdP / SSO<br/>account, group, session"]
    CMD --> SCIM["SCIM / API / PAM<br/>provisioning"]
    SCIM --> APP["SaaS / Cloud / Database"]
    IDP --> AUDIT["Readback / reconciliation<br/>audit + exception"]
    APP --> AUDIT
    AUDIT --> IGA
~~~

**IdP** xác thực danh tính, kiểm soát đăng nhập và có thể lưu nhóm; **SSO** truyền chứng thực hoặc claim; **SCIM/API/PAM** thực thi thay đổi tài khoản và entitlement. Những thành phần này không tự đảm bảo người dùng có nhu cầu công việc hoặc người phê duyệt đúng thẩm quyền.

Approval tạo **căn cứ cho phép cấp assignment**; RBAC/ABAC và policy engine tiếp tục quyết định điều kiện quyền, còn ứng dụng phải thực thi authorization tại API. Một role đã được approve nhưng `securityHold=true` hoặc tenant không khớp vẫn phải bị từ chối khi truy cập.

### Bằng chứng cần đối soát sau phê duyệt

| Thực thể | Điều phải xác nhận |
|---|---|
| **Approval record** | Ai duyệt, có thẩm quyền không, request version nào, thời hạn và scope nào? |
| **Identity/account** | Account đích gắn đúng subject hoặc workload, trong đúng tenant không? |
| **Entitlement** | Role/permission đã được tạo/gỡ đúng nội dung approval chưa? |
| **Runtime access** | API thực thi tenant, SoD, trạng thái nguồn và điều kiện phiên phù hợp không? |
| **Expiry/revocation** | Hết hạn đã gỡ quyền và chấm dứt phiên/credential liên quan nếu chính sách yêu cầu chưa? |
| **Audit** | Có correlation ID nối request, quyết định, lệnh và trạng thái thực tế không? |

Nếu SaaS trả HTTP thành công nhưng quyền thực tế chưa thay đổi, trạng thái fulfillment vẫn chưa nên là `CONFIRMED`. Cần đọc lại native entitlement hoặc dùng cơ chế xác nhận được owner đích chấp nhận.

## 17. Tình huống thiết kế approval

### Tình huống A — Quyền xuất báo cáo tài chính

Nhân viên Finance có role đọc báo cáo nhưng đề nghị bổ sung quyền xuất dữ liệu khách hàng thuộc tenant VN trong 14 ngày.

**Thiết kế:** manager xác nhận nhu cầu công việc, data owner xác nhận phân loại dữ liệu và tenant, policy kiểm tra role, SoD và thời hạn. Approval gắn cụ thể với `FINANCE_REPORT_EXPORT`, tenant VN và `effectiveUntil`. Sau khi được chấp thuận, hệ thống cấp đúng entitlement và đọc lại quyền tại SaaS. Đến hạn, entitlement được gỡ tự động; yêu cầu gia hạn phải được xét lại theo chính sách.

### Tình huống B — Mover từ phê duyệt sang thanh toán

Nhân viên đang giữ `EXPENSE_APPROVER`, chuyển sang vị trí cần `PAYMENT_EXECUTOR`. Manager mới đồng ý cấp role thanh toán nhưng account ở ứng dụng vẫn còn quyền phê duyệt cũ.

**Thiết kế:** quy trình Mover trước hết xác định xung đột SoD. Quyền phê duyệt đã không còn hợp lệ phải được thu hồi và xác minh trước khi role thanh toán mới có hiệu lực, hoặc dùng một cơ chế cách ly an toàn tương đương. Không dùng approval mới để giữ hai quyền xung đột trong lúc chờ đồng bộ.

### Tình huống C — Nhà thầu hết hạn trong khi request đang chờ

Nhà thầu C yêu cầu quyền đọc tài liệu dự án. Sponsor đã duyệt bước đầu, nhưng hợp đồng kết thúc trước khi data owner quyết định.

**Thiết kế:** VMS là nguồn có thẩm quyền cho trạng thái hợp đồng. IAM hủy hoặc đánh dấu stale request khi quan hệ đã hết hiệu lực; dù data owner duyệt sau đó, fulfillment vẫn không được cấp quyền. Nếu hợp đồng được gia hạn hợp lệ, cần đánh giá lại request, scope và approval theo chính sách mới.

### Tình huống D — Service account thiếu owner

Robot CI/CD đề nghị quyền ghi vào bucket production, nhưng service catalog không còn owner kỹ thuật vì nhân viên phụ trách đã nghỉ việc.

**Thiết kế:** policy không tự chọn người nghỉ việc hoặc gán quyền cho robot. Cần xác định lại service owner, kiểm tra workload còn hợp lệ và đưa yêu cầu đến resource/security owner có thẩm quyền. Truy cập cũ được rà soát và credential liên quan được xử lý theo rủi ro; quyền mới không cấp khi thiếu điều kiện bắt buộc.

### Tình huống E — Break-glass khi IdP không hoạt động

Hệ thống xác thực chính gặp sự cố, đội vận hành cần truy cập khẩn cấp để phục hồi.

**Thiết kế:** sử dụng kênh break-glass được quản trị trước, với credential độc lập được bảo vệ, giám sát bất thường, giới hạn phạm vi và hậu kiểm. Không thiết kế một nút tự duyệt admin vĩnh viễn chỉ vì workflow trực tuyến tạm thời không có approver.

## 18. Kiểm thử approval workflow

Quy trình cần được kiểm thử ở **cả bước quyết định và bước thực thi**, đặc biệt các trường hợp âm tính.

| Ca kiểm thử | Đầu vào | Kết quả mong đợi |
|---|---|---|
| 1. Birthright hợp lệ | Nhân viên active nhận role portal cơ sở | Cấp tự động theo policy có version, không cần request-level approval. |
| 2. Quyền nhạy cảm hợp lệ | Manager và data owner độc lập đồng ý đúng scope | Assignment hợp lệ, cấp đúng entitlement, xác nhận ở đích. |
| 3. Tự phê duyệt | Requester cũng là approver đề xuất | Bị từ chối ở workflow hoặc chuyển approver độc lập. |
| 4. Approver thiếu authority | Quản lý trực tiếp cố duyệt dữ liệu tenant khác | Không chấp nhận quyết định vượt thẩm quyền. |
| 5. Sửa scope sau khi duyệt | Thay read-only thành admin | Request cũ bị invalidated hoặc yêu cầu duyệt version mới. |
| 6. SoD xung đột | Người duyệt chi đề nghị thêm quyền thanh toán bị cấm | Chặn cấp ngay cả khi có approval cá nhân. |
| 7. Leaver trong lúc chờ | HRIS phát `TERMINATED` | Hủy yêu cầu cấp và thu hồi quyền hiện có theo policy. |
| 8. Mover xung đột | Role mới cần trong khi role cũ chưa được gỡ | Không kích hoạt quyền mới trái SoD; xử lý thu hồi trước. |
| 9. Approver vắng mặt | Owner không trả lời trước SLA | Escalate/expire; không tự duyệt. |
| 10. Delegation hết hạn | Người được ủy quyền bấm duyệt sau expiry | Từ chối quyết định, lưu audit. |
| 11. Provisioning lỗi | SCIM trả lỗi sau `APPROVED` | Giữ trạng thái chưa hoàn tất, retry/alert, không tuyên bố cấp xong. |
| 12. Role hết hạn | `effectiveUntil` đã qua | Gỡ quyền và xác nhận ở đích; kiểm tra cả quyền trực tiếp. |
| 13. Hai request trùng | Cùng subject/scope/entitlement được gửi lại | Dedupe theo policy, tránh cấp trùng và giữ evidence. |
| 14. Approval cũ | Policy hoặc trạng thái nguồn đổi trước khi cấp | Revalidate và ngăn cấp theo dữ kiện không còn hợp lệ. |
| 15. Service owner nghỉ việc | Robot còn hoạt động nhưng thiếu owner | Yêu cầu chuyển owner/rà soát; không tự cho phép quyền mới. |
| 16. API bị gọi trực tiếp | Client gửi lệnh `approve` thay cho người có quyền | Backend kiểm tra authorization, không chấp nhận payload tự khai authority. |

Các kiểm thử cần xác minh **dữ liệu tại đích** bằng API hoặc bằng chứng được chấp nhận; chỉ thấy workflow chuyển trạng thái `APPROVED` không chứng minh entitlement được thực thi.

## 19. Chỉ số vận hành và điều chỉnh approval model

| Chỉ số | Ý nghĩa |
|---|---|
| **Approval latency** | Thời gian từ request đủ điều kiện đến khi đủ quyết định; phân loại theo risk tier. |
| **Fulfillment latency** | Thời gian từ phê duyệt cuối đến khi quyền được xác nhận ở đích. |
| **Auto-grant coverage** | Tỷ lệ quyền an toàn được cấp theo policy baseline đã phê duyệt trước. |
| **Rejection / correction rate** | Tỷ lệ request bị từ chối hoặc phải sửa vì thiếu scope, owner hay lý do. |
| **Approver resolution failure** | Tỷ lệ không tìm được approver hợp lệ, delegation sai hoặc thiếu authority. |
| **Overdue approvals** | Request quá SLA đang chờ owner; cần phân loại theo hệ thống và mức độ rủi ro. |
| **Self-approval / SoD blocks** | Số lần hệ thống chặn xung đột trong workflow hoặc entitlement. |
| **Expiry revocation success** | Tỷ lệ quyền tạm thời đã được gỡ và xác nhận đúng mốc. |
| **Leaver closure latency** | Thời gian từ mốc Leaver có hiệu lực đến khi quyền bắt buộc tại đích được xác nhận thu hồi. |
| **Provisioning drift** | Quyền thực tế không khớp quyết định còn hiệu lực hoặc role policy. |
| **Exception aging** | Ngoại lệ quá hạn, thiếu owner hoặc chưa đủ bằng chứng kiểm soát bù trừ. |
| **Approval quality signals** | Các quyết định bất thường: duyệt nhiều yêu cầu trong thời gian rất ngắn, liên tục duyệt ngoại lệ hoặc cùng chủ thể đóng nhiều vai trò. |

Thời gian duyệt ngắn không tự chứng minh chất lượng cao. Ví dụ, approval gần như tức thời cho mọi quyền quản trị production có thể là dấu hiệu policy được thiết kế tốt **hoặc** người duyệt không kiểm tra. Cần kết hợp thời gian, tỷ lệ vi phạm, scope quyết định, chất lượng bằng chứng và kết quả review.

### Audit cần trả lời được câu hỏi gì?

Đối với một assignment nhạy cảm, từ log phải lần ra:

1. Ai gửi request, ai nhận quyền, quan hệ danh tính có hợp lệ không?
2. Role/entitlement nào được yêu cầu trên hệ thống, tenant và tài nguyên nào?
3. Policy nào xác định các bước approval và kết quả eligibility/SoD?
4. Approver nào thực sự quyết định, lúc nào, có delegation hợp lệ và lý do gì?
5. Có sửa request hoặc thay đổi policy/identity sau khi duyệt không?
6. Hành động provisioning được gửi đến đâu và đã xác nhận quyền thực tế chưa?
7. Khi nào quyền bị thu hồi, có sai lệch, quá hạn hoặc ticket ngoại lệ không?

Audit chỉ nên giữ dữ kiện cần thiết để chứng minh trách nhiệm; không ghi password, token, khóa bí mật hoặc dữ liệu cá nhân không cần thiết vào log. Cần bảo vệ tính toàn vẹn và truy cập log theo chính sách lưu giữ.

## 20. Quy trình xác định approval cho một chương trình IAM

Một nhóm triển khai có thể áp dụng các bước sau:

1. **Lập danh sách entitlement và risk tier:** từ role catalog, account scope và dữ liệu quyền thực tế tại IdP, SaaS, cloud, database, PAM.
2. **Xác định nguồn và owner:** HRIS/VMS cho điều kiện quan hệ; manager, sponsor, application owner và data owner từ các hệ thống quản trị có thẩm quyền.
3. **Phân loại quyền cấp tự động:** chỉ chọn baseline/role có chính sách rõ, ít rủi ro, có kiểm tra tự động và cơ chế thu hồi.
4. **Lập approval matrix:** với từng loại quyền chỉ rõ người xét, số bước, quy tắc độc lập, reason/ticket, giới hạn thời gian và escalation.
5. **Định nghĩa workflow và dữ liệu:** request/version, trạng thái quyết định, trạng thái fulfillment, expiry, audit và revalidation.
6. **Thiết kế kiểm soát:** SoD, MFA/step-up, authority, delegation, thiếu dữ liệu, sửa request, lỗi connector và break-glass.
7. **Gắn với JML:** Joiner tạo baseline/request; Mover tính lại quyền và approval; Leaver thu hồi mà không chờ duyệt.
8. **Pilot và kiểm thử:** thử user mới, Mover xung đột, nhà thầu hết hạn, tài khoản dịch vụ, approval quá hạn, SCIM lỗi và entitlement drift.
9. **Vận hành và rà soát:** theo dõi SLA, chất lượng approver, quyền tồn dư, quyền tạm thời quá hạn và thay đổi cấu trúc owner.

**Đầu ra tối thiểu** nên gồm: danh mục loại request, approval matrix đã phê duyệt, policy có version, sơ đồ trạng thái, nguồn dữ liệu approver, hợp đồng request/decision/action, quy tắc revalidation, bộ kiểm thử và kế hoạch audit/reconciliation.

## 21. Sai lầm thường gặp

- **Cho quản lý duyệt mọi entitlement:** quản lý biết nhu cầu công việc nhưng có thể không có authority đối với dữ liệu/ứng dụng nhạy cảm.
- **Dùng approval thay policy:** một chữ ký không được vượt `securityHold`, trạng thái hết hợp đồng hoặc SoD bắt buộc.
- **Tự phê duyệt hoặc ủy quyền không kiểm soát:** approver có xung đột lợi ích, delegation vượt phạm vi hoặc hết hạn.
- **Không khóa scope đã duyệt:** sau approval, request bị đổi tenant, entitlement hoặc thời gian mà không xét lại.
- **Không xác minh lại trước cấp:** request được duyệt khi nhân viên active nhưng cấp sau khi người đó đã nghỉ.
- **Chờ approval mới thu hồi Leaver:** giữ quyền tồn dư dù nguồn có thẩm quyền đã xác nhận kết thúc quan hệ.
- **Cấp quyền mới khi Mover còn quyền cũ xung đột:** gây vi phạm SoD trong giai đoạn chuyển đổi.
- **Coi request được duyệt là đã provision thành công:** SCIM/API lỗi hoặc ứng dụng vẫn thiếu/sót entitlement.
- **Không tự thu hồi quyền tạm thời:** expiry chỉ là metadata, không có hành động tại đích.
- **Bỏ qua danh tính phi con người:** service account nhận quyền theo sở thích kỹ sư mà không có service owner và scope.
- **Tự động duyệt request quá hạn:** deadline để nhắc/chuyển cấp bị hiểu thành deadline để cấp quyền.
- **Không kiểm toán thao tác duyệt và ngoại lệ:** không biết ai quyết định, theo policy nào hoặc dựa trên dữ kiện gì.

## 22. Bài tập thực hành: thiết kế approval matrix và luồng JML

Một doanh nghiệp có các nhóm người dùng: nhân viên, nhà thầu, quản trị viên và robot đồng bộ dữ liệu. Hệ thống gồm IdP hỗ trợ SSO, SaaS quản lý chi phí có SCIM, cổng báo cáo tài chính đa tenant và cloud production.

Các tình huống cần giải quyết:

1. Nhân viên mới được cấp portal nội bộ nhưng cần yêu cầu riêng để xem dữ liệu tài chính nhạy cảm.
2. Nhân viên Finance chuyển sang vai trò thanh toán, trong khi trước đây đang giữ quyền phê duyệt chi.
3. Nhà thầu yêu cầu quyền đọc dữ liệu tenant VN đến cuối hợp đồng.
4. Kỹ sư trực production cần quyền cloud admin trong hai giờ để xử lý sự cố.
5. Robot tạo báo cáo cần quyền đọc một dataset production; owner kỹ thuật hiện tại sắp nghỉ việc.
6. Một yêu cầu đã được manager duyệt nhưng SCIM trả lỗi; sau đó nhân viên nghỉ việc.

**Yêu cầu:**

1. Xây dựng approval matrix cho sáu tình huống: auto/manual, owner, approver độc lập, lý do, scope, thời hạn và SoD.
2. Phân biệt policy-level approval với request-level approval; chỉ ra quyền nào cấp theo policy đã duyệt trước.
3. Định nghĩa đối tượng `accessRequest` có `requestVersion`, beneficiary, entitlement, system/tenant, expiry, approval steps và trạng thái fulfillment.
4. Vẽ workflow từ request đến `APPROVED` rồi `CONFIRMED`, có đường xử lý `REJECTED`, `EXPIRED`, `FAILED` và `INVALIDATED`.
5. Giải thích cơ chế ngăn tự duyệt và xử lý khi manager đồng thời là requester, sponsor hoặc account owner.
6. Mô tả cách IAM xử lý Mover xung đột SoD và Leaver đến giữa lúc request đang chờ hoặc connector đang retry.
7. Thiết kế cách xác nhận quyền thực tế tại SaaS, cloud và tài khoản local; xác định khi nào fulfillment được đóng.
8. Đề xuất ít nhất tám ca kiểm thử, gồm test thiếu approver, stale approval, quyền quá hạn và gỡ quyền sau nghỉ việc.

### Tiêu chí nghiệm thu

Một thiết kế approval sẵn sàng cho triển khai cần chứng minh:

- **Authority** của từng approver được xác nhận theo loại quyền, tài nguyên và tenant.
- **Eligibility và SoD** được kiểm tra trước quyết định và trước khi thực thi.
- **Scope đã duyệt** gắn bất biến với request/version, thời hạn và lý do.
- **Quyền baseline** chỉ được tự cấp bằng policy đã chấp thuận; quyền nhạy cảm có các bước quyết định phù hợp.
- **Trường hợp vắng mặt, timeout, delegation và emergency** có quy trình kiểm soát rõ ràng.
- **Joiner–Mover–Leaver** cập nhật quyền theo trạng thái có thẩm quyền; thu hồi quyền hết hiệu lực không chờ approval tùy tiện.
- **Provisioning và readback** chứng minh trạng thái entitlement ở đích; failure/exception không bị che giấu.
- **Audit, SLA, expiry và review** giúp giải thích vì sao có quyền và khi nào quyền bị chấm dứt.

**Approval là cơ chế ghi nhận quyết định cấp quyền có trách nhiệm trong IAM.** Một approval model tốt chỉ yêu cầu con người xét những nơi cần phán đoán và chấp nhận rủi ro, tự động hóa phần đã có policy rõ ràng, đồng thời bảo đảm mọi quyền được cấp đúng scope và được thu hồi ngay khi không còn căn cứ hợp lệ trong vòng đời danh tính.
