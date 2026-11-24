# Thời hạn quyền trong Access Request: cấp đúng hạn, hết quyền đúng lúc

> **Chương:** Access request
>
> **Bài:** Thời hạn quyền
>
> **Module:** SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE
>
> **Ngữ cảnh:** Quản lý vòng đời danh tính IAM theo **Joiner–Mover–Leaver (JML)**, từ xác minh danh tính, tạo tài khoản, cấp quyền đến rà soát và thu hồi khi thay đổi vai trò. Kết nối **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, kiểm toán** nhằm giảm **quyền truy cập tồn dư**.

## 1. Thời hạn quyền là gì?

Một nhân viên được giao hỗ trợ kiểm toán dữ liệu tài chính trong hai tuần. Manager phê duyệt yêu cầu. Nếu sau hai tuần hệ thống vẫn cho phép người đó xuất dữ liệu thì quyền đã tồn tại **ngoài thời gian có căn cứ**, dù ban đầu việc cấp quyền đúng chính sách.

**Thời hạn quyền (access validity period)** là khoảng thời gian một **entitlement/grant cụ thể** được phép có hiệu lực đối với **subject, action và resource scope** trong điều kiện IAM đã phê duyệt. Trong **Access Request**, hạn phải được ghi nhận từ yêu cầu, giới hạn bởi approval và policy, được thực thi tại hệ thống đích và có bằng chứng thu hồi.

| Nhu cầu | Quyền | Thời hạn phù hợp |
|---|---|---|
| Kiểm toán báo cáo | report.export trên tập báo cáo được duyệt | Đến cuối đợt kiểm toán |
| Xử lý sự cố production | service.restart trên một service | Cửa sổ incident theo policy |
| Bàn giao khi đổi team | document.read trên ba tài liệu | Theo thời gian bàn giao |
| Contractor vào dự án | project.contribute trên project | Không vượt contract/assignment |
| Workload chạy batch | object.read trên bucket/prefix | Theo job hoặc trust lifecycle |
| Nhân viên dùng CRM thường xuyên | crm.viewer theo role cơ bản | Theo JML và access review |

Thời hạn không chỉ là trường ngày trên ticket: phải có cách khiến **quyền thực tế ngừng được chấp nhận**, bao gồm API, role ở SaaS, session/token và các đường liên quan.

### 1.1. Access Request cần có gì?

- **Who:** ai yêu cầu, ai thực sự hưởng quyền?
- **What:** action/role/entitlement nào?
- **Where:** resource, tenant và môi trường nào?
- **Why:** ticket, nhiệm vụ và lý do nghiệp vụ gì?
- **When:** bắt đầu và kết thúc lúc nào, timezone nào?
- **Approval:** ai có thẩm quyền trên dữ liệu/tài nguyên?
- **Conditions:** trạng thái nhân sự, MFA, SoD, classification?
- **End:** ai thu hồi, hệ thống nào thực thi và bằng chứng nào xác minh?

Nếu thời hạn bắt buộc nhưng người dùng không cung cấp, không tự coi là vô hạn. Policy phải yêu cầu bổ sung hoặc áp hạn an toàn đã được phê duyệt.

## 2. Các mốc thời gian không được nhầm lẫn

| Mốc | Ý nghĩa | Không đồng nghĩa |
|---|---|---|
| **requestedAt** | Request được tạo | Lúc quyền bắt đầu |
| **requestedFrom/Until** | Khoảng người dùng đề nghị | Khoảng được chấp thuận |
| **approvedAt** | Approver quyết định | Target đã cấp quyền |
| **approvedFrom/Until** | Cửa sổ được duyệt | Thực thi đã đạt |
| **effectiveFrom** | Bắt đầu được phép theo policy | Lúc account được tạo |
| **effectiveUntil** | Quyền phải chấm dứt theo policy | Lúc cleanup job chạy |
| **provisionedAt** | Lệnh grant được gửi/ghi | Quyền có hiệu lực ở target |
| **targetObservedAt** | Readback thấy trạng thái target | Mọi đường quyền đã đồng nhất |
| **revokeRequestedAt** | Lệnh thu hồi được gửi | Quyền thực sự bị chặn |
| **enforcedRevokeAt** | Target ngừng chấp nhận quyền nếu đo được | Đã kiểm chứng toàn bộ |
| **verifiedAt** | Có bằng chứng quyền cần gỡ đã hết | Tự động bằng effectiveUntil |

Ví dụ:

~~~text
08:50  Request: 09:00 đến 17:00
08:55  Manager chỉ duyệt tới 15:00
09:00  IAM gửi lệnh cấp quyền
09:02  SaaS readback thấy role ACTIVE
15:00  Quyền phải hết theo policy
15:03  SaaS mới chặn role tại API
15:05  IAM ghi VERIFIED_REVOKED
~~~

Khoảng 15:00–15:03 là quyền truy cập tồn dư; không được thay effectiveUntil thành 15:03 để báo cáo đẹp hơn.

### 2.1. Ngày có hiệu lực khác ngày nhận sự kiện

Hợp đồng kết thúc lúc 17:00, nhưng HRIS event đến connector lúc 17:08. Mốc hết quyền vẫn là thời điểm nghiệp vụ theo nguồn có thẩm quyền, không phải lúc xử lý message.

### 2.2. Quyền được cấp trước ngày làm việc

Có thể tạo account trước ngày đầu tiên, nhưng không được mở quyền truy cập tài nguyên nhạy cảm trước ngày có hiệu lực nếu policy không cho phép.

## 3. Quy ước khoảng hiệu lực và timezone

Một quy ước dễ kiểm thử là khoảng **bao gồm đầu, loại trừ cuối**:

~~~text
[validFrom, validUntil)

PERMIT xét thời gian khi:
    now >= validFrom
    AND now < validUntil

Khi now == validUntil:
    grant đã hết hiệu lực.
~~~

Hai grant có thể nối nhau không chồng lấn ở đúng mốc giữa:

~~~text
Grant A: [2026-11-23 09:00+07, 2026-11-23 12:00+07)
Grant B: [2026-11-23 12:00+07, 2026-11-23 15:00+07)
~~~

Nếu người dùng chọn “đến hết ngày 30/11”, cần xác định timezone và chuyển thành đầu ngày 01/12 theo lịch địa phương tương ứng, sau đó dùng khoảng half-open.

### 3.1. UTC instant và offset

~~~text
2026-11-23T09:00:00+07:00
2026-11-23T02:00:00Z
~~~

Hai giá trị cùng một instant. Không so sánh giờ địa phương của các server khác timezone như thể chúng là cùng múi giờ.

### 3.2. Date-only và daylight saving time

Một ngày lịch ở khu vực đổi giờ mùa hè không nhất thiết là 24 giờ. Nếu policy dựa trên lịch của địa điểm nghiệp vụ, phải chuyển đổi theo timezone của nơi đó thay vì cộng cứng 86.400 giây.

### 3.3. Clock skew

Đồng bộ đồng hồ và giám sát drift giữa IdP, API, PAM và target. Grace period nếu có phải được policy quy định, không tự kéo dài entitlement vì scheduler hoặc server chậm.

## 4. Quyền nền tảng, quyền có hạn và JIT

| Loại | Đặc trưng | Kiểm soát chính |
|---|---|---|
| **Baseline/standing** | Phù hợp công việc thường xuyên | JML, access review, least privilege |
| **Fixed-term** | Grant có validFrom/Until | Auto-expiry, readback |
| **Task-bound** | Kết thúc khi task/ticket xong | Early revoke và hard deadline |
| **JIT activated** | Eligible trước, active khi cần | Approval, activation TTL, session control |
| **Delegated** | Thay mặt người khác trong khoảng duyệt | Scope, SoD và thời hạn ủy quyền |
| **Break-glass** | Luồng khẩn cấp riêng | Cảnh báo, hậu kiểm và credential rotation |

Một grant admin 10 phút vẫn có thể quá rộng nếu áp lên toàn bộ cloud. Duration ngắn **không thay scope hẹp**.

### 4.1. Account lifetime khác entitlement lifetime

Account SaaS có thể tồn tại suốt thời gian làm việc, trong khi quyền export chỉ hợp lệ hai ngày. Hết export grant không nhất thiết disable cả account.

### 4.2. Eligible khác active

Một user eligible xin production operator chưa có quyền restart production. Eligibility deadline và activation deadline là hai khoảng riêng, cần thực thi từng điều kiện.

## 5. Mô hình request có thời hạn

Ví dụ JSON giả lập, không phải schema của IAM vendor:

~~~json
{
  "requestId": "AR-2026-006",
  "requesterId": "manager-301",
  "beneficiaryId": "employee-1042",
  "beneficiaryType": "USER",
  "target": "finance-saas/tenant-a",
  "entitlement": "report.export",
  "resourceScope": ["finance-report-2026-Q4"],
  "businessReason": "AUDIT-2841",
  "requestedFrom": "2026-11-23T09:00:00+07:00",
  "requestedUntil": "2026-12-01T00:00:00+07:00",
  "approvedFrom": "2026-11-23T09:00:00+07:00",
  "approvedUntil": "2026-11-28T00:00:00+07:00",
  "approvedBy": "finance-data-owner",
  "approvalRef": "APR-2094",
  "effectiveFrom": "2026-11-23T09:00:00+07:00",
  "effectiveUntil": "2026-11-28T00:00:00+07:00",
  "policyVersion": "access-ttl-v5",
  "requestStatus": "APPROVED",
  "targetStatus": "PENDING_PROVISIONING"
}
~~~

### 5.1. Requester có thể khác beneficiary

Manager yêu cầu cho nhân viên, automation yêu cầu cho workload. Hệ thống phải kiểm tra người yêu cầu có thẩm quyền thay mặt chủ thể hưởng quyền và không cho đổi beneficiary sau approval mà không xét lại.

### 5.2. Request, approval và grant cần trạng thái riêng

APPROVED không tự là ACTIVE. Grant có thể chưa provision hoặc đang chờ effectiveFrom. Lưu thông tin riêng cho approval, entitlement, target readback và audit.

### 5.3. Grant ID tách với account ID

Một người có nhiều grant từ các ticket khác nhau. Mỗi grant cần ID, owner, thời hạn, scope và lịch sử để revoke đúng một quyền mà không xóa nhầm quyền khác.

## 6. Tính thời hạn được phép từ nhiều ràng buộc

Không lấy nguyên requestedUntil do browser gửi làm quyết định cuối. IAM phải xét:

- Khoảng thời gian approver duyệt.
- Maximum duration theo policy và mức rủi ro.
- Ngày bắt đầu/kết thúc employment hoặc hợp đồng.
- Assignment/project/resource deadline.
- Thời hạn của delegation/ticket.
- Sự kiện Mover hoặc Leaver làm mất eligibility.
- Trạng thái resource, SoD và giới hạn dữ liệu.

Công thức **khái niệm** khi từng giới hạn có áp dụng:

~~~text
effectiveFrom = max(
    requestedFrom,
    approvedFrom,
    employmentStart,
    policyEarliestStart
)

effectiveUntil = min(
    requestedUntil,
    approvedUntil,
    activationAt + maxPolicyDuration,
    contractEnd,
    assignmentEnd,
    resourceDeadline
)
~~~

Nếu effectiveFrom không trước effectiveUntil, **không có khoảng quyền hợp lệ** để cấp. Không ép các trường không áp dụng vào công thức; từng constraint phải có provenance, ngữ nghĩa và thứ tự ưu tiên theo policy.

### 6.1. Ví dụ cắt ngắn thời hạn

User xin quyền production 8 giờ. Policy giới hạn tối đa 60 phút, approver chỉ duyệt 45 phút, hợp đồng còn sáu giờ. Khi kích hoạt hợp lệ, grant không được dài hơn 45 phút. Nếu ticket đóng sau 20 phút và policy quy định revoke theo ticket, quyền phải kết thúc sớm hơn.

### 6.2. Không biến dữ liệu thiếu thành vô hạn

Nếu contractor thiếu ngày hết hợp đồng hoặc nguồn HRIS đang lỗi, hệ thống không nên coi null là forever. Với quyền nhạy cảm, yêu cầu bổ sung bằng chứng hoặc dùng quy tắc bảo thủ đã được phê duyệt.

### 6.3. Nguồn có thẩm quyền

Độ dài hợp đồng, ngày đổi vai trò và trạng thái nhân sự phải đến từ HRIS/hệ thống hợp đồng được quản trị. Người hưởng quyền không được tự kéo dài các mốc đó qua request payload.

## 7. Luồng Request–Approve–Provision–Expire–Verify

~~~mermaid
flowchart TD
    R[Requester khai subject/action/resource/time] --> V[Kiểm tra identity, contract và policy]
    V --> E{Eligible, SoD và scope hợp lệ?}
    E -- Không --> DENY[Từ chối hoặc chỉnh yêu cầu]
    E -- Có --> A[Approver duyệt phạm vi và khoảng thời gian]
    A --> W[Tính effective window]
    W --> P{Window hợp lệ?}
    P -- Không --> DENY
    P -- Có --> PR[Provision grant ở target]
    PR --> RB[Readback quyền đã cấp]
    RB --> USE[PEP/PDP enforce action và thời hạn]
    USE --> X{Đến hạn, ticket đóng, Mover hay Leaver?}
    X -- Chưa --> USE
    X -- Có --> REV[Revoke và xử lý phiên/credential liên quan]
    REV --> CHECK[Kiểm chứng effective access]
    CHECK --> OK{Bằng chứng đủ?}
    OK -- Có --> CLOSE[VERIFIED_CLOSED + audit]
    OK -- Không --> PART[PARTIAL, owner, containment và escalation]
    PART --> CHECK
~~~

Quy trình phải xác định trước **cách quyền kết thúc**, không dựa vào một người nhớ xóa nhóm vào cuối ngày.

### 7.1. Approval giới hạn cả thời gian và nội dung

Approval cho quyền read trong hai ngày không thể tái dùng để cấp export trong hai tháng. Request ID, beneficiary, action, resource, tenant, duration và phiên bản policy phải khớp.

### 7.2. Cấp quyền có thể bất đồng bộ

Connector trả 200 có thể chỉ nghĩa lệnh được tiếp nhận. Chưa được gọi ACTIVE khi chưa có bằng chứng target đã thực thi đúng, đặc biệt với quyền nhạy cảm.

### 7.3. Hết hạn có thể cần nhiều bước

Gỡ group, chặn session, thu hồi credential và xác minh là các thao tác khác nhau. Trạng thái EXPIRED_PENDING_VERIFICATION phản ánh đúng khi target chưa được kiểm chứng.

## 8. Phê duyệt, thẩm quyền và SoD

Một người phê duyệt phải có thẩm quyền **trên đối tượng dữ liệu và entitlement**. Manager team A không mặc nhiên được duyệt quyền dữ liệu mật team B.

| Loại grant | Approval có thể phù hợp |
|---|---|
| Đọc log ít nhạy cảm | Auto-approval theo rule có owner |
| Đọc dữ liệu khách hàng | Chủ dữ liệu/manager phù hợp |
| Export dữ liệu nhạy cảm | Data owner duyệt scope, mục đích và thời hạn |
| Admin production | Owner hệ thống/ca trực, step-up assurance |
| IAM role/policy write | Approval đặc quyền, kiểm tra Separation of Duties |
| Break-glass | Quy trình khẩn cấp có cảnh báo và hậu kiểm |

### 8.1. Separation of Duties không biến mất vì TTL ngắn

Người tạo hóa đơn không được tự duyệt cùng hóa đơn nếu policy cấm, dù được kích hoạt approver trong năm phút. Tương tự, user không nên được tự request, tự approve, tự cấp rồi tự xóa audit quyền global-admin.

### 8.2. Không tin approval tự khai

Một JSON do user gửi có approvedBy="director" không chứng minh director đã phê duyệt. Cần hệ thống approval tin cậy, định danh approver, time, version, chữ ký/quyết định và bằng chứng phù hợp.

### 8.3. Approval có thể hết trước activation

Request được duyệt cho cửa sổ tuần này không đương nhiên đủ điều kiện để activate vào tháng sau. Nếu activation đến sau approvedUntil hoặc sau khi approver bị rút thẩm quyền theo policy, cần revalidation.

## 9. Kích hoạt ngay, hẹn giờ và theo nhu cầu

Có ba cách phổ biến:

1. **Immediate:** kích hoạt sau approval đủ điều kiện.
2. **Scheduled:** chuẩn bị record nhưng chỉ cho phép từ effectiveFrom trong tương lai.
3. **On-demand/JIT:** user đủ điều kiện trước đó, kích hoạt role khi có nhiệm vụ.

### 9.1. Duration bắt đầu từ mốc nào?

Một grant 30 phút phải định nghĩa rõ tính từ requestedAt, approvedAt, activatedAt hay một cửa sổ lịch cố định. Không tự giả định mọi PAM/PIM/SaaS cùng ngữ nghĩa.

Ví dụ approval lúc 09:00 nhưng user chỉ kích hoạt lúc 11:00. Nếu policy quy định “cửa sổ bảo trì 09:00–10:00”, không được mở quyền 11:00–11:30 chỉ vì activation muộn.

### 9.2. Account được tạo sớm không nghĩa access được mở sớm

SCIM có thể provision trước ngày vào làm. API/role enforcement phải ngăn quyền truy cập dữ liệu trước effectiveFrom nếu policy chưa cho phép.

### 9.3. Task-bound vẫn cần hard deadline

Một ticket có thể bị quên ở trạng thái OPEN. Nếu grant chỉ dựa vào ticket close mà không có thời hạn tối đa, quyền có thể trở thành vô hạn do lỗi quy trình.

## 10. Ai thực thi hạn quyền: IAM, PDP, PEP hay target?

Một thời hạn chỉ có hiệu lực bảo mật khi được kiểm tra **trên đường truy cập thật**.

| Thành phần | Trách nhiệm |
|---|---|
| **IAM/IGA** | Request, approval, desired grant, revoke scheduler |
| **IdP/Authorization Server** | Identity, SSO, phát token và trạng thái phiên theo contract |
| **PDP** | Quyết định PERMIT/DENY từ role, attributes, thời hạn và policy |
| **PEP** | Thực thi quyết định ở API/service/database/gateway |
| **Target SaaS/cloud/database** | Role/ACL/permission thực tế |
| **Reconciliation service** | Readback và kiểm chứng quyền có hiệu lực |

~~~mermaid
sequenceDiagram
    participant U as User
    participant IAM as IAM / Access Request
    participant AS as IdP / Authorization Server
    participant API as API / PEP
    participant PDP as Entitlement PDP
    participant T as Protected Resource
    U->>IAM: Xin report.export đến 15:00
    IAM->>IAM: Kiểm tra eligibility, approval, window
    IAM->>T: Provision đúng scope
    T-->>IAM: Readback
    U->>AS: Đăng nhập SSO
    AS-->>U: Token/phiên hợp lệ
    U->>API: Export lúc 14:30
    API->>PDP: Principal/action/resource/now
    PDP-->>API: PERMIT nếu grant còn hạn
    API->>T: Thực hiện theo quyền được xác minh
    U->>API: Export lúc 15:01
    API->>PDP: Kiểm tra lại thời hạn
    PDP-->>API: DENY
~~~

### 10.1. Native expiry tại target

Nếu SaaS/cloud hỗ trợ expiry trực tiếp trên role assignment, nên khai thác đúng API, nhưng vẫn kiểm tra hành vi session, token, cache và các grants khác.

### 10.2. Scheduler gỡ role

Nếu target không có native expiry, IAM có thể chạy job gỡ group/role khi đến hạn. Với quyền nhạy cảm, scheduler mỗi giờ có thể quá chậm; cân nhắc runtime check, session proxy hoặc biện pháp bù trừ.

### 10.3. Không chỉ ẩn chức năng trên UI

Browser có thể ẩn nút Export sau 15:00 nhưng request HTTP trực tiếp vẫn thành công nếu API bỏ kiểm tra. Enforcement phải nằm ở server/target và có object-level authorization.

## 11. Token, session và grant có lifetime khác nhau

~~~text
Entitlement valid:   09:00 -> 09:30
JWT access token:    09:20 -> 10:20
SSO session:         08:00 -> 17:00
PAM admin session:   09:10 -> 09:45
Refresh token:       Theo chính sách của Authorization Server
~~~

Nếu entitlement hết lúc 09:30, không thể suy JWT, cookie, PAM session hay refresh token tự hết ngay.

### 11.1. Access token khác ID token

Trong OAuth 2.0, Resource Server nhận access token. Trong OIDC, ID token chủ yếu dành cho Relying Party để xác nhận kết quả đăng nhập. API không được lấy ID token làm vé truy cập mọi resource.

RS phải kiểm tra issuer, audience, chữ ký hoặc introspection, thời hạn và token profile, sau đó kiểm tra **scope cùng quyền nghiệp vụ và resource cụ thể**.

### 11.2. JWT exp khác grant validUntil

Token được phát lúc 09:20 có exp 10:20 nhưng chứa role hết lúc 09:30. Chữ ký JWT còn hợp lệ không chứng minh role còn được phép. API/PDP có thể cần entitlement status checks, token TTL thích hợp, revocation hoặc session control theo kiến trúc.

### 11.3. MFA không gia hạn quyền

User vừa MFA thành công lúc 09:29 vẫn không được dùng admin sau 09:30 nếu grant hết. Authentication assurance và entitlement lifetime là các điều kiện riêng.

### 11.4. Logout tại IdP không mặc định hủy mọi SaaS session

SaaS có thể giữ local session/token, thậm chí local login. Cần xác minh cơ chế chặn quyền thực tế ở từng target.

## 12. RBAC, group và quyền chồng lấn

User có thể nhận quyền qua:

- Group IdP được đẩy tới SaaS.
- Role cấp trực tiếp trong ứng dụng.
- Nested groups và inherited permission.
- Cloud project/account policy.
- ACL riêng trên object.
- JIT role activation hoặc delegation.

### 12.1. Gỡ đúng entitlement

Khi grant export hết hạn, user có thể vẫn cần quyền viewer nền tảng. Gỡ grant export, không disable account hoặc xóa baseline viewer.

### 12.2. Nhiều grants cho cùng action

Nếu grant tạm A hết nhưng grant hợp lệ B cũng cấp read trên cùng resource, user có thể vẫn được đọc. Verification phải phân biệt **đường grant cần thu hồi** với **quyền hiệu lực hợp lệ còn lại**.

### 12.3. Gỡ Group không chứng minh effective access đã biến mất

Role trực tiếp, group lồng, share link hoặc token cũ có thể tiếp tục cấp quyền. Đối soát phải tính tổng các đường vào resource.

## 13. ABAC: thời gian là một điều kiện của authorization

Một pseudo-policy:

~~~text
PERMIT nếu:
    subject.status == ACTIVE
    AND subject.tenantId == resource.tenantId
    AND action IN grant.allowedActions
    AND resource.id IN grant.allowedResources
    AND now >= grant.validFrom
    AND now < grant.validUntil
    AND grant.approvalStatus == VALID
    AND resource.classification IN subject.allowedClasses
    AND session.assurance meets policy
~~~

Đây không phải schema của policy engine nào. Mọi thông tin để cấp quyền phải đến từ nguồn có thẩm quyền; không tin client tự gửi validUntil hoặc isApproved.

### 13.1. Freshness của trạng thái nhân sự

Nếu HRIS đã đánh dấu Leaver nhưng PDP vẫn cache ACTIVE quá lâu, action có thể được cho phép sai. Với quyền nhạy cảm, phải định nghĩa độ mới cần thiết cho subject status, entitlement và resource attributes.

### 13.2. Thời hạn là trần, không bảo đảm quyền luôn tồn tại

User bị suspended, resource đổi tenant, ticket đóng hoặc SoD conflict xảy ra trước validUntil đều có thể khiến quyền phải kết thúc sớm.

### 13.3. Resource state thay đổi

Invoice đã APPROVED có thể không còn được edit, dù user có grant edit đến ngày mai. Cần kết hợp condition theo trạng thái nghiệp vụ, không chỉ clock.

## 14. SCIM và expiry của entitlement

SCIM 2.0 hỗ trợ provisioning User, Group và membership. Nó hữu ích khi một SaaS ánh xạ group sang role, nhưng **không định nghĩa cơ chế hết hạn chung cho mọi entitlement tùy ý**.

Một luồng thường gặp:

1. IAM duyệt quyền report.export đến 15:00.
2. Connector thêm beneficiary vào Group finance-exporters tại SaaS.
3. SaaS ánh xạ membership thành role.
4. Đến hạn, scheduler hoặc trigger gửi thao tác gỡ member.
5. Connector readback Group và role tại target.
6. Nếu còn session, local grant hoặc API key, workflow tiếp tục xử lý.

### 14.1. Hết một grant không phải Leaver

SCIM User active=false phù hợp với một số tình huống vô hiệu hóa account theo lifecycle. Nếu chỉ hết quyền export, **không nên disable toàn bộ account** khi user còn những quyền hợp lệ khác.

### 14.2. HTTP success chưa chứng minh hết quyền

Response HTTP 200/204 có thể phản ánh thành công giao thức, nhưng không chứng minh session, token hay cache của SaaS đã được cập nhật. Cần readback hoặc kiểm tra effective access theo rủi ro.

### 14.3. SCIM khác SSO

SSO/OIDC/SAML xác thực và liên kết đăng nhập; SCIM đồng bộ identity/group. Người dùng có thể đăng nhập SSO thành công nhưng bị API từ chối report.export vì entitlement hết hạn.

## 15. Auto-expiry và nhiều lớp thu hồi

| Cơ chế | Lợi ích | Hạn chế |
|---|---|---|
| Native expiry ở target | Target tự chặn role khi đến hạn | Phụ thuộc vendor và session behavior |
| Runtime PDP/PEP check | Có thể chặn ngay tại validUntil | Cần dữ liệu quyền và clock đáng tin |
| Scheduler remove role/group | Tự động thu hồi ở target | Có thể trễ, timeout hoặc fail |
| Event-driven revoke | Chặn khi ticket đóng, Mover, Leaver | Event có thể mất hoặc đến sai thứ tự |
| Token/session controls | Hạn chế dùng claims cũ | Không thay resource authorization |
| Reconciliation | Phát hiện drift và quyền tồn dư | Không phải chặn tức thời |

### 15.1. Idempotency của cleanup job

Job revoke có thể chạy lại sau timeout. Xử lý nhiều lần không được cấp lại quyền, không xóa nhầm grant khác và không đánh dấu VERIFIED khi target chưa được kiểm chứng.

### 15.2. Scheduler đơn độc có thể quá chậm

Nếu scheduler chạy mỗi giờ, grant hết lúc 15:00 có thể còn hiệu lực đến 16:00. Với action nhạy cảm, cần cân nhắc runtime cutoff, native expiry hoặc containment bổ sung.

### 15.3. Khi target không phản hồi

Không coi grant đã hết thực tế chỉ vì portal hiển thị EXPIRED. Ghi PENDING_VERIFICATION/PARTIAL với owner, deadline, alert và biện pháp giảm rủi ro.

### 15.4. Quyền tạm có thể sinh quyền lâu dài

Một grant role.assign hoặc document.share có thể tạo role, API key hoặc share link tồn tại sau khi grant gốc hết. Quản trị **secondary grants** và tài nguyên dẫn xuất là một phần của expiry design.

## 16. Gia hạn: extension, renewal và request mới

User có quyền đến 15:00, lúc 14:55 xin gia hạn tới 17:00. Gia hạn không đơn giản là sửa timestamp; phải đánh giá lại:

1. Mục đích/ticket còn hợp lệ?
2. Beneficiary vẫn active và eligible?
3. Người duyệt cũ còn thẩm quyền?
4. Action, resource, tenant có thay đổi?
5. Có vượt maximum/cumulative duration hoặc số lần gia hạn?
6. Có Mover, Leaver hoặc SoD conflict?
7. Cơ chế target/session/token sẽ phản ánh hạn mới thế nào?
8. Có audit quyết định renewal và grant version mới?

### 16.1. Renewal không tạo quyền hồi tố

Grant hết 15:00, approval gia hạn tới 15:10 mới được chấp thuận. Không sửa lịch sử để tuyên bố quyền liên tục hợp lệ trong 10 phút chưa được duyệt.

### 16.2. Chống chuỗi renewal vô hạn

Nhiều grant 30 phút nối liên tục có thể trở thành standing privilege. Policy cần maximum total duration, renewal count, approval mới hoặc access review.

### 16.3. Thay action/scope cần xét lại

Kéo dài report.read khác với thêm report.export. Đổi target từ tenant A sang B cũng không phải chỉ gia hạn thời gian; cần quyết định và approval thích hợp.

### 16.4. Race giữa renew và revoke

Một worker đang xử lý Leaver revoke trong lúc worker khác gia hạn. Cần version/transaction và quy tắc state machine ngăn quyền sống lại.

## 17. Thu hồi trước hạn

Thời hạn được duyệt là **trần tối đa**, không phải bảo đảm luôn được giữ quyền đến cuối.

Trigger revoke sớm:

- Ticket đã hoàn tất.
- Data owner rút approval.
- Mover làm mất role hoặc assignment hợp lệ.
- Leaver, suspension hoặc hết hợp đồng.
- Resource đổi owner/tenant/classification.
- Thiết bị mất compliance hoặc credential bị nghi lộ.
- Workload kết thúc nhiệm vụ hoặc đổi môi trường.
- SoD conflict phát sinh.

### 17.1. Thời hạn kết thúc theo điều kiện sớm nhất

Nếu quyền được duyệt 60 phút nhưng ticket đóng sau 20 phút và policy yêu cầu chặn khi hoàn tất, quyền phải kết thúc sau 20 phút chứ không đợi TTL.

### 17.2. Kiểm soát trạng thái theo nguồn tin cậy

Một trường ticket.status do browser tự gửi không phải căn cứ revoke/permit. Cần dữ liệu ticket và role từ nguồn có thẩm quyền, đủ mới cho mức rủi ro.

### 17.3. Incident response không đợi deadline

Với tài khoản bị compromise, phải containment và revoke khẩn theo policy, không chờ grant tự hết.

## 18. Joiner: thời điểm bắt đầu và kết thúc hợp đồng

Joiner tạo danh tính, account và các quyền cơ bản theo HRIS/nguồn nhân sự có thẩm quyền.

~~~text
employmentStartAt = 2026-12-01T00:00:00+07:00
contractEndAt     = 2027-01-01T00:00:00+07:00
~~~

Có thể provision account trước ngày đầu, nhưng **quyền nhạy cảm phải không mở trước effectiveFrom** nếu không có ngoại lệ được duyệt.

### 18.1. Baseline role vẫn chịu JML

Một role theo vị trí có thể không có fixed expiry, nhưng phải bị thu hồi khi nhân viên hết quan hệ hoặc chuyển khỏi vai trò đủ điều kiện.

### 18.2. ID nguồn ổn định

Email/userName có thể đổi hoặc được tái cấp. Cần identity ID, tenant, target resource ID và correlation tin cậy để revoke đúng account.

### 18.3. Early onboarding exception

Nếu cần đọc tài liệu hướng dẫn trước ngày vào làm, cấp đúng tài liệu đó trong cửa sổ được duyệt, không mở toàn bộ CRM/production chỉ vì account đã được tạo.

## 19. Mover: hạn quyền cũ có thể đến sớm hơn approval

Một người chuyển từ Finance sang Operations nhưng vẫn active.

| Entitlement | Trước Mover | Sau Mover |
|---|---|---|
| finance.viewer | Quyền công việc cũ | Thu hồi |
| operations.viewer | Chưa có | Cấp theo vai trò mới |
| finance.handover.read | Chưa có | Có thể cấp hẹp và có hạn |
| invoice.approve | Có | Thu hồi nếu không còn nhiệm vụ |
| production.restart | Chưa có | Chỉ JIT khi cần |

### 19.1. Handover có scope và TTL riêng

Nếu chỉ cần ba tài liệu để bàn giao hai ngày, nên gỡ Finance role rộng và cấp quyền đọc ba tài liệu với approval/validUntil riêng.

### 19.2. Không đợi grant cũ tự hết

Grant Finance còn 90 ngày nhưng Mover xảy ra sau 10 ngày. Nếu policy yêu cầu thu hồi khi chuyển team, phải xử lý tại ngày Mover.

### 19.3. SoD khi hai quyền chồng lấn

Trong bàn giao, user có thể đồng thời có role tạo và duyệt giao dịch; phải đánh giá xung đột theo object/action và kiểm soát ngoại lệ.

### 19.4. Readback ứng dụng đích

IdP group đã gỡ nhưng local role hoặc direct share tại SaaS có thể còn. Reconciliation phải kiểm tra quyền thực tế.

## 20. Leaver: cutoff không đợi ngày hết grant

Một user nghỉ trước approvedUntil. Với policy yêu cầu account đang active, entitlement phải bị chặn không muộn hơn Leaver effectiveAt.

~~~text
approvedUntil       = 2026-12-31T23:59:00+07:00
leaverEffectiveAt   = 2026-11-25T17:00:00+07:00
accessCutoff        = 2026-11-25T17:00:00+07:00
~~~

### 20.1. Thu hồi theo nhiều lớp

1. IdP/SSO chặn xác thực mới.
2. IAM deactivate grants và pending activations.
3. SCIM/API gỡ role/group hoặc disable User theo đúng lifecycle.
4. PAM/PIM kết thúc activation/session khi hỗ trợ.
5. Cloud IAM/database/local ACL và share links được đối soát.
6. Token/session/API key được xử lý theo contract.
7. Readback tại mỗi target có rủi ro để đóng VERIFIED/PARTIAL.

### 20.2. JWT còn hạn sau Leaver

Token signature và exp hợp lệ không chứng minh user còn quyền. Nếu yêu cầu revoke sớm, phải có cơ chế entitlement status/revocation/session phù hợp, không chỉ disable IdP.

### 20.3. Đừng xóa tài nguyên kinh doanh theo người nghỉ

Tài liệu, hóa đơn, service account hoặc job còn cần thiết nên được bàn giao owner, bảo toàn dữ liệu và audit; thu hồi quyền cá nhân là việc khác.

## 21. Guest, đối tác và delegation

Guest access có ít nhất ba vòng đời:

- Invitation validity: link mời dùng đến khi nào?
- Guest/account/partner relationship validity: mối quan hệ còn hợp lệ không?
- Resource entitlement validity: quyền trên từng tài nguyên còn hạn không?

**Invitation expiry không tự thu hồi quyền** của guest đã nhận lời và có account.

### 21.1. Sponsor và owner

Guest nên có sponsor, purpose, tenant, classification, end date, cơ chế access review và rút quyền.

### 21.2. Delegated access có thể kết thúc sớm

Manager ủy quyền duyệt thanh toán trong một tuần; nếu quay lại sau ba ngày, có thể rút delegation theo policy. Người nhận không được tự nâng quyền hoặc kéo dài thời hạn.

### 21.3. Federation và trust

Claim group mới từ IdP đối tác không tự biến thành quyền quản trị ở tenant nội bộ. Phải có issuer/subject mapping, approval và thời hạn grant riêng.

## 22. Hạn quyền cho service account và workload

Workload không có ngày nghỉ việc như nhân viên, nhưng vẫn có **owner, nhiệm vụ, môi trường và vòng đời trust/entitlement**.

Ví dụ:

~~~text
principal = svc-backup-prod
action = object.read
resource = backup-bucket/tenant-a/prefix
credential = workload token ngắn hạn
grantValidity = theo nhiệm vụ backup
owner = platform-backup-team
~~~

### 22.1. Token TTL khác permission lifetime

Một access token client credentials sống năm phút có thể được xin lại vô hạn nếu service principal giữ standing role. **Credential ngắn hạn không chứng minh grant có thời hạn.**

### 22.2. Rotation không thay revoke

Đổi secret/certificate có thể ngăn dùng credential cũ nhưng không tự gỡ role của principal trên API/bucket. Cần quản trị credential validity và entitlement validity riêng.

### 22.3. Khi người sở hữu workload Leaver

Không xóa ngay backup job còn cần thiết chỉ vì kỹ sư từng quản lý nghỉ việc. Bàn giao ownership, thu hồi quyền cá nhân và rà soát service principal/trust/grants theo policy.

### 22.4. SCIM không quản trị toàn bộ non-human identities

Service principals, cloud IAM role, certificate, API key và workload federation thường có API lifecycle chuyên biệt. Không coi một SCIM User disable là bằng chứng mọi workload access đã bị chặn.

## 23. Break-glass và ngoại lệ vượt hạn

Break-glass là đường khẩn cấp được chuẩn bị khi luồng xác thực/cấp quyền bình thường không khả dụng hoặc không phù hợp với tình huống khẩn.

Nó cần:

- Điều kiện kích hoạt và authority rõ ràng.
- Scope thấp nhất khả thi để cứu tài nguyên.
- Credential được bảo vệ và phân công owner.
- Cảnh báo độc lập, audit và hậu kiểm.
- Session/command evidence nếu hạ tầng cho phép.
- Rotation/revoke credential sau khi kết thúc.
- Kiểm thử định kỳ khả năng dùng khi IdP/PAM chính outage.
- Không để tài khoản emergency thành standing admin vô giám sát.

### 23.1. Tránh phụ thuộc vòng tròn

Nếu IdP outage, một cơ chế break-glass vẫn yêu cầu IdP đó phát token sẽ không giúp xử lý sự cố. Kế hoạch dự phòng có thể cần kênh độc lập, nhưng vẫn phải có bảo vệ phù hợp.

### 23.2. Không dùng ngoại lệ để lách maxDuration mãi mãi

Một exception kéo dài quyền vượt policy cần owner, approval rủi ro, hạn mới và kế hoạch thu hồi. Không gọi standing admin là “temporary exception” khi không có cutoff.

### 23.3. Không suy mọi break-glass tự expire

Khả năng native expiry tùy nền tảng. Nếu không có, phải mô tả đúng biện pháp vận hành, khóa/rotate/hậu kiểm thực tế thay vì tuyên bố tự hết hạn.

## 24. Event trễ, retry, state machine và race condition

Trong hệ thống phân tán, sự kiện có thể đến sai thứ tự, được xử lý trùng hoặc chậm.

~~~mermaid
sequenceDiagram
    participant HR as HRIS
    participant IAM as IAM Event Processor
    participant T as Target
    HR->>IAM: Mover version 101
    HR->>IAM: Leaver version 102
    IAM->>T: Revoke theo state version 102
    T-->>IAM: Ack
    Note over IAM: Mover version 101 được retry đến muộn
    IAM->>IAM: Kiểm tra sourceVersion và desired state
    IAM-->>IAM: Bỏ event cũ
    IAM->>T: Readback quyền
    T-->>IAM: Actual state
~~~

### 24.1. Scheduled activation sau Leaver

Một request được APPROVED hôm qua, scheduled active ngày mai. Nếu hôm nay beneficiary Leaver, job phải tái xác minh eligibility, không được activate dựa vào approval cũ.

### 24.2. Renew và revoke cạnh tranh

Worker A đang revoke do expiry, worker B đang renew. Nếu không có transactional state transitions và optimistic version, quyền có thể sống lại hoặc lịch sử bị viết sai.

### 24.3. Cache và replica lag

PDP có thể đọc role/contract từ read replica hoặc cache chưa nhận update. Với action rủi ro, phải có freshness requirement, invalidation, source version hoặc mức nhất quán phù hợp.

### 24.4. Idempotent processing

Cùng một revoke được retry không được tạo role mới hoặc xóa nhầm grant hợp lệ khác. Dùng grantId, eventId, target identity và tenant namespace rõ.

### 24.5. Time-of-check to time-of-use

Nếu API kiểm tra quyền còn hạn lúc 14:59:59 nhưng thực hiện hành động nhạy cảm lúc 15:00:05, cần quy định **mốc quyền phải hợp lệ** và có thể kiểm tra trong cùng transaction hoặc dùng version/fencing cho các mutation quan trọng.

## 25. Ví dụ triển khai: policy, Java và SQL

### 25.1. Policy minh họa

~~~yaml
accessRequestPolicy:
  id: finance-export-timebound
  version: "2026-11-v5"
  entitlement: report.export
  resourceScope: finance-reports/tenant-a
  requireBusinessReason: true
  requireDataOwnerApproval: true
  disallowSelfApproval: true
  maximumDurationHours: 48
  enforceWindowAtRequest: true
  onTicketClosed: REVOKE_EARLY
  onMoverEligibilityLoss: REVOKE
  onLeaver: REVOKE_IMMEDIATELY
  onExpiry: REVOKE_AND_VERIFY
  onVerificationFailure: PARTIAL_AND_ESCALATE
~~~

Đây là schema đào tạo, không phải cấu hình của một sản phẩm IAM cụ thể. Capability native expiry, session revoke và SCIM group sync cần được xác minh ở từng nhà cung cấp.

### 25.2. Pseudocode duyệt và cấp

~~~text
function approveAndActivate(request):
    subject = identityStore.getCurrent(request.beneficiaryId)
    resource = trustedResourceCatalog.get(request.resourceId)
    policy = policyStore.forAction(request.action, resource)

    if subject.status != ACTIVE:
        return DENY
    if not policy.eligible(subject, request):
        return DENY
    if violatesSoD(subject, request):
        return DENY

    approval = approvalStore.verifyExactRequest(request)
    if not approval.valid:
        return DENY

    effectiveFrom = computeAllowedStart(request, approval, subject, policy)
    effectiveUntil = computeAllowedEnd(request, approval, subject, policy)
    if effectiveFrom >= effectiveUntil:
        return DENY

    grant = grantStore.createVersionedGrant(
        subjectId=subject.id,
        action=request.action,
        resourceId=resource.id,
        validFrom=effectiveFrom,
        validUntil=effectiveUntil,
        lifecycleVersion=subject.lifecycleVersion
    )

    if trustedClock.now() >= grant.validUntil:
        return DENY

    target.applyGrantIdempotently(grant)
    if not target.verifyExpectedEffectiveAccess(grant):
        grantStore.markPartial(grant.id)
        return PARTIAL

    grantStore.markActive(grant.id)
    return ACTIVE_WITH_AUDIT
~~~

### 25.3. Pseudocode API runtime

~~~text
function authorize(request):
    principal = verifyTrustedPrincipal(request)
    resource = loadTrustedResource(request.resourceId)
    grant = entitlementStore.findApplicable(
        principal.id, request.action, resource.id, resource.tenantId
    )

    if grant is NONE:
        return DENY

    now = trustedClock.now()
    if principal.status != ACTIVE:
        return DENY
    if now < grant.validFrom or now >= grant.validUntil:
        return DENY
    if grant.revoked or grant.state != ACTIVE:
        return DENY
    if not grant.approvalStillValid:
        return DENY
    if not evaluateRBAC_ABAC_SoD(principal, request.action, resource):
        return DENY

    return PERMIT_WITH_AUDIT_CONTEXT
~~~

Đây là pseudocode; implementation thật phải xử lý concurrency, transaction, TOCTOU, session/claim cũ và nguồn entitlement đủ mới.

### 25.4. Java: half-open access window

~~~java
import java.time.Clock;
import java.time.Instant;

public record AccessWindow(Instant validFrom, Instant validUntil) {
    public AccessWindow {
        if (validFrom == null || validUntil == null
                || !validFrom.isBefore(validUntil)) {
            throw new IllegalArgumentException("Invalid access window");
        }
    }

    public boolean contains(Instant now) {
        return !now.isBefore(validFrom) && now.isBefore(validUntil);
    }

    public boolean activeNow(Clock clock) {
        return contains(Instant.now(clock));
    }
}
~~~

Java code chỉ kiểm tra time window. Nó không tự bảo vệ API, xác thực principal, SoD hoặc role. Dùng Clock được inject để viết boundary tests thay vì đổi giờ máy sản xuất.

### 25.5. SQL: lọc grant còn hiệu lực

~~~sql
SELECT grant_id, subject_id, resource_id, action
FROM access_grants
WHERE subject_id = :trustedSubjectId
  AND resource_id = :trustedResourceId
  AND tenant_id = :trustedTenantId
  AND action = :requestedAction
  AND status = 'ACTIVE'
  AND revoked_at IS NULL
  AND valid_from <= :trustedNow
  AND valid_until > :trustedNow;
~~~

Các parameter phải đến từ principal/resource lookup tin cậy. SQL này chưa thay SoD, classification, approval authority, tenant policy hay các kiểm soát resource khác.

## 26. Audit về thời hạn và bằng chứng thu hồi

Audit phải trả lời: **Ai đã yêu cầu quyền gì, ai duyệt, quyền có hiệu lực khi nào, được dùng trên đâu và khi nào thực sự bị chặn?**

Các trường hữu ích:

- Request ID, grant ID, beneficiary, requester và approver.
- Entitlement/action, target application, tenant/resource scope.
- Business reason/ticket, policy version và approval evidence.
- Requested/approved/effective windows.
- Thời điểm provision, kết quả readback cấp quyền.
- Thời điểm expiry, revoke command và target enforced revoke.
- Trạng thái verification, exception, correlation ID và owner xử lý.
- JML event/source version nếu thay đổi quyền do Mover hoặc Leaver.

Ví dụ JSON **giả lập**:

~~~json
{
  "eventId": "ACCESS-WINDOW-2026-006",
  "requestId": "AR-2026-006",
  "grantId": "GRANT-8821",
  "principalRef": "employee-1042",
  "target": "finance-saas/tenant-a",
  "entitlement": "report.export",
  "resourceScope": "finance-report-2026-Q4",
  "requestedUntil": "2026-12-01T00:00:00+07:00",
  "approvedUntil": "2026-11-28T00:00:00+07:00",
  "effectiveUntil": "2026-11-28T00:00:00+07:00",
  "approvalRef": "APR-2094",
  "policyVersion": "access-ttl-v5",
  "revocationReason": "APPROVED_WINDOW_EXPIRED",
  "revokeRequestedAt": "2026-11-28T00:00:02+07:00",
  "targetVerifiedAt": "2026-11-28T00:00:10+07:00",
  "finalState": "VERIFIED_CLOSED",
  "correlationId": "AUDIT-2841"
}
~~~

Không ghi access token, refresh token, mật khẩu, API secret, OTP hoặc thông tin người dùng không cần thiết. Audit cần phân quyền xem, retention và phát hiện chỉnh sửa trái phép.

### 26.1. Trạng thái workflow nên phân biệt

| Trạng thái | Đã đạt | Chưa tự bảo đảm |
|---|---|---|
| REQUESTED | Đã nhận yêu cầu | Chưa phê duyệt |
| APPROVED | Scope và window được chấp thuận | Target đã cấp quyền |
| SCHEDULED | Chờ đến effectiveFrom | Chưa được dùng quyền |
| PROVISIONING | Đang cấp | Quyền đã hiệu lực |
| ACTIVE | Có bằng chứng cấp đúng phạm vi | Sẽ mãi đủ điều kiện |
| REVOKING | Đang thu hồi | Đã mất quyền |
| EXPIRED_PENDING_VERIFICATION | Deadline đã qua | Target đã chặn |
| VERIFIED_CLOSED | Có bằng chứng quyền cần thu hồi đã bị chặn | Tất cả các quyền khác của user cũng bị xóa |
| PARTIAL/ESCALATED | Có đường quyền chưa xử lý hoặc chưa kiểm chứng | Quy trình hoàn tất |

### 26.2. KPI và SLO

| Chỉ số | Mục đích |
|---|---|
| Tỷ lệ grant có effectiveUntil | Độ phủ quản lý hạn |
| Số request vượt maxDuration | Chính sách và hành vi yêu cầu |
| Tỷ lệ renewal có approval phù hợp | Ngăn kéo dài trái phép |
| Độ trễ approval-to-activation | Khả năng đáp ứng công việc |
| **Expiry-to-enforced lag** | Đo thời gian quyền tồn dư sau hạn |
| Tỷ lệ VERIFIED_CLOSED | Chất lượng xác minh |
| Oldest PARTIAL / pending | Theo dõi rủi ro chưa xử lý |
| Grants active sau Mover/Leaver trái policy | Phát hiện quyền cũ |
| Workload grants thiếu owner | Rủi ro non-human |
| Direct grants/share links ngoài window | Đường phụ bị bỏ quên |

Một dashboard báo 100% EXPIRED không có ý nghĩa nếu target vẫn cho action sau deadline.

## 27. Case study: quyền xuất báo cáo phục vụ kiểm toán

### 27.1. Bối cảnh

Doanh nghiệp có ứng dụng báo cáo tài chính tenant A. Nhân viên An cần export báo cáo quý IV để phục vụ kiểm toán. Data Owner Bình có quyền phê duyệt.

Request ban đầu xin quyền export mọi báo cáo trong 30 ngày. Policy chỉ cho phép một bộ báo cáo cụ thể trong tối đa năm ngày.

### 27.2. Xử lý yêu cầu

1. An gửi request gắn ticket AUDIT-2841, resource và requested window.
2. IAM xác minh An active, đúng tenant/department, role và SoD.
3. Bình duyệt đúng báo cáo, hạn đến đầu ngày 28/11 theo timezone nghiệp vụ.
4. IAM tính effective window theo approval, policy và assignment.
5. Connector cấp entitlement; readback xác minh role/scope target.
6. API đánh giá thời gian, tenant và report instance mỗi lần export.
7. Đến hạn hoặc khi ticket đóng, IAM revoke entitlement.
8. Kiểm tra local role, group, token/session và quyền còn lại theo rủi ro.
9. Nếu target đã chặn theo policy, đóng VERIFIED; nếu chưa, giữ PARTIAL và escalation.

### 27.3. Biến cố A: An Mover ngày 25/11

An chuyển sang phòng khác, không còn nhiệm vụ kiểm toán. Grant cần bị thu hồi sớm khi Mover làm mất eligibility, không giữ đến approvedUntil ngày 28/11.

### 27.4. Biến cố B: SaaS xử lý revoke chậm

IAM gửi remove lúc 00:00 ngày 28/11 nhưng SaaS còn cho export đến 00:07. Phải báo độ trễ bảy phút, không backdate thời điểm target chặn quyền.

### 27.5. Biến cố C: xin gia hạn

An yêu cầu thêm đến 01/12. Hệ thống phải xét lại eligibility, business reason, maximum duration, approval và data classification thay vì sửa tùy ý lịch sử grant.

### 27.6. Bài học

Một thời hạn an toàn cần được ràng buộc xuyên suốt **request → approval → grant → runtime enforcement → revoke → verification**. Thiếu một khâu có thể tạo quyền truy cập tồn dư.

## 28. Ma trận kiểm thử thời hạn quyền

| Kịch bản | Kết quả cần xác minh |
|---|---|
| Thiếu validUntil khi policy bắt buộc | Không cấp vô thời hạn |
| RequestedUntil vượt maximum | Giới hạn hoặc từ chối |
| ApprovedUntil ngắn hơn request | Không vượt approval |
| Contractor contractEnd sớm hơn | Chặn theo contract cutoff |
| Requester khác beneficiary | Kiểm tra thẩm quyền yêu cầu thay |
| Action/scope đổi sau approval | Không dùng approval cũ |
| Request trước validFrom | Từ chối |
| Request đúng validFrom | Tiếp tục xét quyền |
| Request ngay trước validUntil | Cho phép nếu policy khác đạt |
| Request đúng validUntil | Từ chối |
| Request sau validUntil | Từ chối |
| Date-only có timezone nghiệp vụ | Chuyển đúng boundary |
| Clock của API lệch | Không nới quyền trái policy |
| JWT vẫn còn hạn sau grant | Không dùng entitlement cũ |
| SSO session còn active | Chỉ các quyền còn hợp lệ được dùng |
| SCIM remove 200 nhưng role còn | PARTIAL và readback |
| Group đã gỡ nhưng local role còn | Phát hiện tồn dư |
| Baseline role hợp lệ vẫn cấp read | Không xóa nhầm quyền khác |
| Mover mất eligibility | Revoke sớm |
| Leaver trước scheduled activation | Không cấp |
| Event Mover cũ đến sau Leaver | Không tái cấp |
| Approval gia hạn sau khi hết | Không backdate |
| Hai worker revoke cùng grant | Idempotent |
| PDP cache PERMIT sau validUntil | Không cho phép |
| Resource đổi tenant/owner | Đánh giá lại authorization |
| Workload token ngắn nhưng standing role tồn tại | Phát hiện grant chưa có cutoff |
| Share link còn sau grant expiry | Xử lý đường quyền phụ |
| Target outage khi revoke | PENDING/PARTIAL, owner và containment |
| Một target verified, target khác chưa | Không đánh dấu toàn bộ VERIFIED |
| Đúng thời gian, scope, approval | Cho đúng action và audit |

### 28.1. Boundary testing

Thử ngay trước validFrom, đúng validFrom, ngay trước validUntil, đúng validUntil và sau validUntil. Kết hợp token cũ, cached PERMIT, sự kiện Mover/Leaver đến muộn và nhiều grants chồng lấn.

### 28.2. Không chỉnh đồng hồ production

Dùng injected clock/time provider hoặc môi trường test có kiểm soát, tài khoản và dữ liệu thử được phê duyệt. Không giả lập bằng cách làm sai đồng hồ máy sản xuất.

### 28.3. Kiểm chứng quyền thật

Không chỉ assert database status EXPIRED; cần kiểm tra API, target role, group, session/credential và những đường liên quan. Một test 403 duy nhất không chứng minh mọi đường đã bị chặn.

## 29. Những hiểu lầm phổ biến

**“RequestedUntil là hạn cuối được phép.”** Không; approval, policy maximum, hợp đồng và JML có thể làm hạn ngắn hơn.

**“APPROVED là ACTIVE.”** Không; target có thể chưa provision hoặc đang scheduled.

**“EXPIRED ở portal nghĩa là đã revoke hết.”** Không nếu còn session, local role, JWT hoặc direct grant.

**“JWT exp chính là entitlement expiry.”** Hai khái niệm khác nhau và có thể có thời hạn khác.

**“Logout SSO là đủ để thu hồi.”** Không mặc định với các SaaS session/local login.

**“Hết export thì phải disable cả User.”** Không nếu còn entitlement công việc hợp lệ khác.

**“Gia hạn chỉ là tăng timestamp.”** Cần kiểm tra eligibility, scope, approval, policy và SoD.

**“Baseline role không cần JML.”** Quyền thường trực vẫn phải được cập nhật khi nhân viên đổi vai trò hoặc nghỉ.

**“Một lần 403 chứng minh toàn bộ quyền đã hết.”** Không nếu có share link, API key, endpoint khác hoặc role trực tiếp.

**“Ngắn hạn nghĩa là least privilege.”** Một quyền global-admin trong thời gian ngắn vẫn có thể quá rộng.

**“MFA làm grant hợp lệ lâu hơn.”** Authentication assurance không thay entitlement lifetime.

**“Retry sự kiện luôn an toàn.”** Retry event cũ có thể tái cấp nếu thiếu lifecycle version và desired-state check.

## 30. Checklist thiết kế Access Request có thời hạn

1. **Identity:** requester và beneficiary được xác minh, ID ổn định?
2. **Target:** app, tenant, environment, resource, entitlement cụ thể?
3. **Purpose:** có ticket/mục đích, owner và bằng chứng?
4. **Requested window:** from/until có timezone và ngữ nghĩa rõ?
5. **Maximum duration:** policy giới hạn theo risk tier?
6. **Approval:** đúng approver và approved window?
7. **SoD:** tránh tự approve và role xung đột?
8. **Effective window:** đã tính các constraint áp dụng?
9. **Missing data:** không dùng null để mở quyền vô hạn?
10. **Boundary:** áp dụng [from, until) chính xác?
11. **Scheduled activation:** không cấp sớm?
12. **Provisioning:** readback quyền ACTIVE ở target?
13. **RBAC:** group, inherited role và direct grants được đánh giá?
14. **ABAC:** subject, tenant, resource, action, time được enforce?
15. **Token/session:** JWT, SSO, PAM có thể sống lâu hơn entitlement?
16. **SCIM:** chỉ gỡ đúng membership/role thay vì disable nhầm?
17. **Auto-expiry:** native expiry/runtime checks/scheduler đủ theo SLA?
18. **Fail-safe:** lỗi PDP/target không tự cho phép quyền nhạy cảm?
19. **Early revoke:** ticket close, Mover, Leaver, compromise có trigger?
20. **Renewal:** có reapproval, hạn tổng và chống gia hạn vô hạn?
21. **Clock:** UTC/offset/timezone, DST, clock skew được xử lý?
22. **Events:** retry, out-of-order, lifecycle version và idempotency?
23. **Source freshness:** employment status, entitlement, approval đủ mới?
24. **Multi-tenant:** cache/mapping/namespace không trộn tenant?
25. **Workload:** principal, credential, trust, grants có owner và lifecycle?
26. **Break-glass:** exception được giám sát/hậu kiểm?
27. **Secondary grants:** API key, share link, delegated rights được rà soát?
28. **Verification:** effective access tại target đã được chứng minh mất?
29. **Partial:** có owner, SLA, escalation và containment?
30. **Audit:** requested/approved/effective/enforced/verified timestamps và policy version?
31. **Metrics:** expiry lag, unresolved grants, residual access?
32. **Tests:** boundary, stale tokens, role overlap, outage, race conditions?

---

**Ghi nhớ:** **Thời hạn quyền trong Access Request là cửa sổ hiệu lực được phê duyệt và thực thi**, không đơn thuần là ngày ghi trên ticket. Phải phân biệt **requested, approved, effective, enforced và verified times**, đồng thời giới hạn theo **subject–action–resource–tenant**, policy và **Joiner–Mover–Leaver**. Kết hợp **IdP/SSO, SCIM, RBAC/ABAC, token/session controls, auto-expiry, renewal policy, reconciliation và audit** mới giúp quyền **được cấp đúng hạn và không tiếp tục sử dụng khi mất căn cứ**, giảm **quyền truy cập tồn dư**.






