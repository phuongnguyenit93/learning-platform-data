# Thời hạn khẩn cấp trong IAM: giới hạn quyền Emergency Access đúng lúc và thu hồi có kiểm chứng

**Thời hạn khẩn cấp** (*emergency access duration*, *time-bound emergency privilege*) là **khoảng thời gian được chính sách cho phép sử dụng một quyền truy cập đặc biệt để xử lý sự cố**. Quyền này có thể được cấp hoặc kích hoạt bằng cơ chế **Emergency Access / Break-glass / Just-in-Time (JIT)** khi đường quản trị thông thường không đáp ứng được nhu cầu khôi phục. Nó phải có **mốc bắt đầu, mốc kết thúc, điều kiện chấm dứt sớm, quy tắc gia hạn, người chịu trách nhiệm và bằng chứng thu hồi**. Hết thời gian ghi trên ticket **không tự đồng nghĩa** hết hiệu lực ở ứng dụng, session, token, credential hay tài khoản đặc quyền.

Ví dụ: một kỹ sư được kích hoạt quyền `service:restart` trên `cluster-vn-2` để khôi phục một dịch vụ production trong 45 phút. Đến phút 45, PAM có thể đánh dấu yêu cầu **EXPIRED**, nhưng SSH session vẫn mở, OAuth access token còn hiệu lực, hoặc một local administrator account vẫn chấp nhận đăng nhập. Nếu những đường truy cập đó vẫn cho restart sau hạn, **thời hạn mới chỉ tồn tại trên giấy**. Quy trình phải kiểm soát quyền thực thi tại target và xác minh thời điểm quyền thực sự bị chặn.

Bài nằm trong chương **Emergency access** của module **Identity and Access Management (IAM) — Identity Lifecycle**. Bối cảnh quản lý danh tính theo **Joiner–Mover–Leaver (JML)**, tích hợp **HRIS, IdP/SSO, SCIM, RBAC/ABAC, Privileged Access Management (PAM), service/workload identities, audit và reconciliation**. Người học sẽ biết mô hình hóa cửa sổ thời hạn khẩn cấp, bảo đảm khả năng khôi phục ngay cả khi IdP/PAM lỗi và chặn **đặc quyền tồn dư** sau khẩn cấp.

> **Thông điệp chính:** Quyền khẩn cấp phải **khả dụng khi có sự cố hợp lệ** nhưng **không được biến thành quyền quản trị thường trực không kiểm soát**. Thiết kế phải phân biệt **thời gian được phép**, **thời gian credential/session còn hiệu lực** và **thời điểm target thật sự từ chối thao tác**.

## 1. Emergency access và ý nghĩa của thời hạn

**Emergency access** là đường truy cập được quản trị để xử lý tình huống nghiêm trọng khi quy trình truy cập bình thường quá chậm, không khả dụng hoặc không đủ quyền để khôi phục dịch vụ. Ví dụ:
- IdP/SSO không thể đăng nhập nên đội vận hành cần một đường khôi phục độc lập.
- PAM/gateway gặp lỗi trong khi một control plane cần được khôi phục.
- Sự cố production đòi hỏi thao tác đặc quyền vượt role thường nhật.
- Sự cố khóa cấu hình IAM khiến người quản trị thông thường không thể sửa policy.
- Hệ thống dữ liệu bị lỗi cần một khả năng phục hồi được chuẩn bị trước và có kiểm soát.

**Break-glass** thường nói tới **đường dự phòng có thể sử dụng khi kiểm soát thông thường không hoạt động**. **JIT privileged access** thường nói tới **kích hoạt quyền trong khoảng thời gian ngắn theo yêu cầu và điều kiện**. Chúng có thể phối hợp nhưng **không đồng nhất**:
- Một JIT flow phụ thuộc IdP/PAM có thể **không dùng được** khi chính IdP/PAM bị outage.
- Một break-glass account có thể được **pre-provisioned** để bảo đảm khôi phục; nếu credential của nó không có expiry tự động, **thời hạn sử dụng vẫn phải được kiểm soát bằng activation, custody, session, monitoring và post-use recovery** ở những lớp còn hoạt động.
- Một quyền emergency được phép dùng trong 30 phút có thể cần **hết trước** nếu sự cố kết thúc hoặc owner rút approval.

### 1.1. Vì sao không nên cấp Emergency Admin vô hạn?

Nếu account luôn có quyền cao và credential có thể dùng tự do:
1. Bất kỳ ai biết credential có thể truy cập **ngoài ca khẩn cấp**.
2. Sau khi sự cố kết thúc, quyền **không tự thu hẹp**.
3. Đội vận hành có thể dần dùng đường emergency thay vì JIT chuẩn.
4. Khó xác định ai chịu trách nhiệm nếu account dùng chung.
5. Một nhân viên Mover/Leaver vẫn có thể biết credential hoặc giữ session cũ.
6. Việc rà soát định kỳ có thể bỏ qua một đường truy cập chỉ dùng ít lần.

**Thời hạn** là một lớp giảm rủi ro. Nó **không thay** MFA, credential protection, least privilege, SoD, logging hoặc target authorization.

### 1.2. Không phải mọi quyền khẩn cấp đều giống nhau

| Trường hợp | Đường truy cập | Điều cần giới hạn thời gian |
| --- | --- | --- |
| Restart một service trong incident | PAM/JIT scoped role | Grant, session, action và ticket. |
| Sửa policy IdP khi IdP offline | Break-glass recovery account | Việc lấy/dùng credential, session, tác vụ khôi phục và hậu kiểm. |
| Khôi phục cloud control plane | Emergency admin role | Activation/role assignment, API token, resource scope. |
| Truy cập database phục hồi | Privileged DB credential | Checkout, DB session, secret rotation và các quyền thay đổi dữ liệu. |
| Chạy recovery workload | Workload identity/certificate | Workload lease, audience/scope, credential validity và job lifecycle. |
| Bàn giao khẩn cấp sau Mover | Temporary delegated role | Assignment, expiry, JML revalidation. |

Không có một con số thời lượng áp dụng cho mọi tổ chức. Thời hạn cần dựa vào **mức tác động, khả năng thu hồi, phương án khôi phục, chủ thể và độ nhạy tài nguyên**.

## 2. Phân biệt sáu loại “đồng hồ” của emergency access

Một quyền khẩn cấp có thể gắn đồng thời nhiều hạn, nhưng chúng không tự đồng bộ.

| Loại hạn | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Request/approval validity** | Quyết định cho phép activation còn có thể được dùng tới khi nào? | Approval chỉ hợp lệ để bắt đầu trong 15 phút. |
| **Emergency business window** | Sự cố/ticket còn hợp lệ, thao tác cần thiết được phép đến khi nào? | Incident window 10:00–10:45. |
| **Privilege activation lease** | Role/grant JIT được kích hoạt đến mốc nào? | PAM role từ 10:03–10:33. |
| **Session lifetime** | Phiên SSH/RDP/DB/web còn kết nối, được thao tác đến lúc nào? | SSH session duy trì qua 10:33 nếu không bị ngắt. |
| **Token/credential lifetime** | Access token, SSH cert, API key hoặc vault checkout còn được target chấp nhận không? | Token `exp=11:00`. |
| **Verification/closure deadline** | Khi nào hệ thống phải chứng minh quyền đã mất và đóng hồ sơ? | Kiểm tra và xử lý residual privilege theo SLA sau hết hạn. |

### 2.1. Một grant đã hết hạn vẫn có thể có session hợp lệ

~~~text
10:00  Emergency request được phê duyệt cho 45 phút
10:05  PAM kích hoạt role trên target
10:08  API phát access token có hạn 60 phút
10:45  Request business window hết hạn
10:50  Token cũ vẫn gọi API vì target chỉ kiểm chữ ký/exp
11:08  Token mới hết hạn

Nếu API cho action tại 10:50 -> residual emergency privilege.
~~~

Thời điểm token hết hạn không nhất thiết là thời điểm permission được đánh giá lại. Muốn giới hạn thực sự ở 10:45, target phải **ràng buộc thời hạn authorization** hoặc có cơ chế revoke/introspection/session invalidation phù hợp.

### 2.2. Approval hết hạn không đồng nghĩa account hết hạn

Một break-glass account dự phòng có thể **tồn tại thường xuyên** để sẵn sàng phục hồi, nhưng quyết định **cho phép dùng** account đó có thời hạn. Không nên xóa account dự phòng sau mọi sự cố nếu thiết kế phục hồi cần nó tồn tại; thay vào đó cần bảo vệ credential, đóng phiên, rotation/resealing nếu policy yêu cầu, audit và tái sẵn sàng.

### 2.3. Hiệu lực không đồng nghĩa ticket “đã đóng”

Đóng incident ticket là **một tín hiệu chấm dứt sớm**. Nhưng phải truyền tín hiệu tới PAM/IdP/target và kiểm tra không còn quyền thực thi. Không dùng `incident.status=CLOSED` trong một hệ thống nếu API authorization hoàn toàn không đọc hoặc nhận được trạng thái đó.

## 3. Mô hình cửa sổ thời gian và điều kiện chấm dứt

Một chính sách thường định nghĩa:

- `notBefore` hoặc `validFrom`: mốc bắt đầu được phép.
- `validUntil` hoặc `expiresAt`: hạn kết thúc.
- `maxDuration`: giới hạn mỗi lần activation.
- `absoluteDeadline`: mốc cuối **không thể vượt** ngay cả khi có renewals, nếu policy quy định.
- `requestSubmissionDeadline`: approval không còn dùng để activate sau quá hạn.
- `incidentOrTaskState`: điều kiện business purpose còn hiệu lực.
- `earlyRevokeTriggers`: điều kiện kết thúc trước thời hạn.
- `postUseVerificationSla`: hạn hoàn tất kiểm chứng; **không kéo dài quyền**.

### 3.1. Khoảng nửa mở để tránh nhầm ở ranh giới

~~~text
timeWindowValid(now) =
    validFrom <= now
    AND now < validUntil
~~~

Với khoảng `[10:00, 10:45)`, quyền có thể được xét từ **10:00:00**, và phải **không còn được phép** từ đúng **10:45:00**. Cần thống nhất precision, timezone, clock skew và nguồn thời gian đáng tin.

Đây là **pseudocode**, không phải cú pháp OIDC/SCIM/PAM chuẩn.

### 3.2. Tính hạn hiệu lực từ nhiều ranh giới

~~~text
effectiveDeadline = minimum(
    approvedRequest.validUntil,
    incident.authorizedUntil,
    privilegedRole.leaseExpiresAt,
    policy.absoluteDeadline,
    currentAssignment.validUntil
)
~~~

Chỉ tính những ranh giới thực sự được policy yêu cầu và có ngữ nghĩa rõ. Nếu một phần tử thiếu/mâu thuẫn, không mặc định biến nó thành `infinity`. Cần **fail-safe handling** hoặc cơ chế emergency được quản trị riêng, tùy loại thao tác.

### 3.3. Hết sớm khi mục đích không còn

Một emergency grant phải được **revoke hoặc suspend trước `validUntil`** nếu:
- Incident được giải quyết và không còn nhiệm vụ.
- Người được cấp chủ động kết thúc phiên.
- Owner/risk approver rút approval.
- JML state chuyển sang Mover/Leaver làm mất căn cứ.
- Security phát hiện credential compromise hoặc hành vi lạ.
- SoD conflict hoặc policy thay đổi khiến grant không còn hợp lệ.
- Compensating control bắt buộc bị hỏng.
- Đã hoàn thành thao tác khôi phục, không cần tiếp tục đặc quyền.

**Đừng hiểu 45 phút là quyền bảo đảm được dùng đủ 45 phút**; đó thường là một **giới hạn tối đa của một lần phê duyệt**, không phải mức tối thiểu.

## 4. Chọn thời hạn dựa trên rủi ro và khả năng vận hành

Không nên đặt mọi emergency request cùng một hạn chỉ vì thuận tiện cấu hình. Hãy cân nhắc:

| Yếu tố | Tác động tới thời hạn |
| --- | --- |
| **Độ rộng quyền** | Global IAM admin thường cần cửa sổ chặt hơn một role chỉ đọc log. |
| **Tác động tài nguyên** | Production và dữ liệu nhạy cảm cần kiểm soát chặt hơn môi trường test. |
| **Khả năng thu hồi** | Target không hỗ trợ revoke token tức thời cần hạn token/cơ chế kiểm soát bổ sung. |
| **Độ dài nhiệm vụ** | Restart vài phút khác migration nhiều giờ. |
| **Phụ thuộc availability** | Phục hồi IdP offline khác thao tác khi PAM hoạt động. |
| **Khả năng giám sát** | Có người on-call/independent reviewer giúp phát hiện và kết thúc sớm. |
| **Đường credential** | Static secret khó thu hồi hơn token ngắn hạn hoặc PAM-brokered capability. |
| **Khả năng cấp lại an toàn** | Gia hạn có phê duyệt phù hợp có thể tốt hơn cấp một grant dài. |

### 4.1. Thời hạn minh họa, không phải chuẩn bắt buộc

| Nhiệm vụ minh họa | Hạn có thể đề xuất để đánh giá | Điều kiện |
| --- | --- | --- |
| Restart một service cụ thể | Cửa sổ ngắn, ví dụ 15–45 phút. | PAM/JIT, owner, log và target-scope. |
| Thay cấu hình production có phê duyệt | Một change window được hạn rõ. | Ràng buộc ticket và scoped permissions. |
| Khôi phục control plane trong sự cố lớn | Có thể cần dài hơn, nhưng chia thành giai đoạn. | Gia hạn/review, kiểm soát người và phạm vi. |
| Xử lý sự cố dữ liệu nhạy cảm | Ngắn và giới hạn action/dataset. | Chống export ngoài scope, audit độc lập. |
| Recovery account dự phòng không phụ thuộc IdP | Account có thể được duy trì, **quyền dùng theo ca khẩn** có thời hạn. | Custody, alerting, rotation/resealing, post-use audit. |

Những khoảng thời gian nêu trên chỉ là **ví dụ đào tạo**, không phải một SLA/chuẩn bắt buộc hay mặc định cho mọi sản phẩm. Hãy chọn từ chính sách và khả năng kiểm soát được **actual access**.

### 4.2. Không tối ưu bằng “thời hạn càng ngắn càng tốt” một cách máy móc

Một hạn không đủ để thực hiện các bước phục hồi an toàn có thể làm kỹ sư liên tục renew, tạo thao tác gấp, hoặc buộc dùng credential không quản lý. Thiết kế tốt đặt **hạn đủ cho nhiệm vụ**, nhưng kèm giới hạn action/resource, early termination, monitoring và quy trình gia hạn hiệu quả mà không tự mở quyền.

## 5. Luồng kích hoạt quyền khẩn cấp có giới hạn thời gian

~~~mermaid
flowchart TD
    I["Sự cố / nhu cầu emergency có căn cứ"] --> Q["Xác định actor, target, action, business scope"]
    Q --> E{"Có đường thường/JIT an toàn khả dụng?"}
    E -->|Có| J["JIT/PAM theo chính sách"]
    E -->|Không, dependency outage| B["Break-glass pathway được thiết kế trước"]
    J --> A["Identity + approval/eligibility + SoD"]
    B --> A
    A --> W["Tính validFrom, validUntil, max duration"]
    W --> C["Credential/session protection + monitoring ready"]
    C --> P["Grant/activate đúng target và scope"]
    P --> V["Readback + kiểm tra PEP enforcement"]
    V --> M["Monitor, early termination triggers"]
    M --> X["Hết hạn / kết thúc sớm / JML change"]
    X --> R["Revoke role/session/token/credential theo scope"]
    R --> Z{"Actual emergency access đã bị chặn?"}
    Z -->|Có| D["VERIFIED_CLOSED + audit"]
    Z -->|Chưa| F["Containment + remediation owner/SLA"]
    F --> R
~~~

### 5.1. Chuẩn bị trước sự cố

Emergency access rất khó thiết kế trong lúc chính hệ thống quản trị đang bị lỗi. Trước đó phải biết:
- Ai được quyền kích hoạt hoặc yêu cầu đường emergency?
- Cần xác minh danh tính như thế nào nếu IdP không hoạt động?
- Chứng cứ/ticket có thể lập **offline** hoặc theo đường dự phòng nào?
- Những tài nguyên/action tối thiểu để khôi phục?
- Ai giữ credential hoặc quản trị vault?
- Cách ghi log độc lập và gửi cảnh báo?
- Thời gian sử dụng và quy tắc gia hạn?
- Khi IdP/PAM trở lại, làm sao thu hồi, rotate và reconcile?
- Đã kiểm thử khôi phục định kỳ nhưng không làm hỏng availability chưa?

### 5.2. Activation là một hành động có audit

Một record activation tốt liên kết:
`incidentId`, `activationId`, `personIdentityId`, `targetAccountId`, `action`, `resourceScope`, `validFrom`, `validUntil`, `approverIdentityId` (nếu yêu cầu), `policyVersion` và trạng thái. Nếu dùng break-glass account chung, phải ghi **ai thực sự tiếp cận credential** bằng kênh tin cậy và có người giám sát/đối chiếu.

### 5.3. Đừng cấp GlobalAdmin nếu chỉ cần restart

Ngay cả khi sự cố khẩn, least privilege vẫn có thể dùng:
- Role/operator capability chỉ cho một service.
- Namespace/project-scoped permission.
- Tạm activate một action qua broker.
- Runbook/script được review trước, giới hạn lệnh và tài nguyên.
- Token gắn audience/action/resource thay vì token cloud-wide.

**Không phải emergency là ngoại lệ cho mọi nguyên tắc phân quyền.** Nếu không thể thu hẹp kỹ thuật vì nền tảng cũ, phải đánh giá residual risk, monitoring, thời hạn và kế hoạch cải thiện.

## 6. Điều kiện xác thực và độc lập khi IdP/PAM outage

### 6.1. Hai đường có nhu cầu khác nhau

**Đường bình thường:** IdP/SSO xác thực, PAM/JIT kiểm tra eligibility, approval, step-up MFA và activate role.

**Đường dự phòng:** khi IdP/PAM hoặc mạng quản trị không khả dụng, cần một **recovery path độc lập vừa đủ** để sửa sự cố. Nếu recovery credential **phụ thuộc hoàn toàn vào đúng IdP/PAM đã lỗi**, break-glass chỉ có tên mà không hoạt động.

### 6.2. Break-glass phải bảo vệ nhưng không tự khóa đường khôi phục

Cần cân bằng:
- Credential hoặc authenticator được lưu trữ an toàn và có quy trình truy xuất khẩn.
- Có thể xác minh người sử dụng bằng cơ chế **phù hợp với failure mode**.
- Người được ủy quyền đủ và được huấn luyện; tránh phụ thuộc một cá nhân duy nhất.
- Giảm khả năng dùng ngoài emergency bằng custody, alerting, monitoring và review.
- Không khóa/rotate mọi recovery credential đồng thời khi không có phương án dự phòng hoạt động.
- Định kỳ kiểm thử cách truy cập, bảo đảm không phụ thuộc ngầm vào SSO/PAM bị outage.

Không có hướng dẫn “tắt MFA” chung cho break-glass: một số nền tảng có emergency account với mô hình AuthN đặc thù; phải tuân theo đặc điểm sản phẩm và threat model, có **kiểm soát tương đương/compensating controls** hợp lệ.

### 6.3. Offline approval và hồ sơ hậu kiểm

Khi hệ thống ticket/approval offline, có thể dùng **quy trình khẩn dự phòng đã được phê duyệt trước**: hai người độc lập ghi nhận quyết định trên kênh còn hoạt động, ghi mốc giờ và scope, sau đó nhập evidence vào hệ thống khi phục hồi. Không giả mạo một approval timestamp về trước hoặc gắn tên approver chưa tham gia.

**Post-incident review không tự biến thao tác bị cấm thành hợp lệ**, nhưng giúp kiểm tra việc dùng đúng quy trình emergency đã được ủy quyền và khắc phục sai lệch.

## 7. PAM/JIT: thời hạn activation, session và credential

### 7.1. Bốn tầng cần xem xét

| Tầng | Thao tác thời hạn | Kiểm tra cần thiết |
| --- | --- | --- |
| **Eligibility** | Người được phép yêu cầu một role trong phạm vi. | Quyền eligibility có còn phù hợp JML/SoD? |
| **Activation** | JIT grant bật từ `validFrom` đến `validUntil`. | PAM và target có cùng hiểu TTL không? |
| **Session** | Kết nối tới DB/SSH/RDP hoặc UI privileged. | Hết hạn có ngắt hoặc chặn thao tác tiếp không? |
| **Credential** | Secret được checkout, SSH cert/token được phát. | Có thể dùng trực tiếp sau khi PAM đóng session không? |

### 7.2. Credential checkout không phải là token hủy ngay được

Nếu người dùng đã xem/copy mật khẩu root, sau 30 phút không thể “hết quyền” chỉ bằng cách đánh dấu vault checkout expired. Cần đánh giá:
- Đã rotate/disable mật khẩu sau checkout theo policy chưa?
- Có session direct sử dụng credential đó không?
- Có phương án tránh lộ credential qua broker/proxy không?
- Có secret khác hoặc backdoor account còn đường truy cập không?
- Rotation có ảnh hưởng account khẩn khác hoặc gây lockout không?

### 7.3. Session recording khác enforcement

PAM có thể ghi hình session, nhưng **không có nghĩa session tự đóng đúng thời điểm**. Ngoài recording, cần cơ chế **session TTL/termination, command allowlist, target policy và revoke** thích hợp. Với phiên không thể hủy giữa chừng, phải nêu rõ rủi ro và đặt hạn/cách containment phù hợp.

### 7.4. Phân biệt eligible và active khi Mover/Leaver

Một kỹ sư rời nhóm Operations:
- **Gỡ eligibility** xin role production nếu không còn assignment.
- **Chấm dứt activation** còn mở theo policy.
- Kiểm tra **credential/session** đã phát.
- Bảo đảm app/cloud target không còn direct grants.
- Không giữ JIT eligibility chỉ vì user ít khi kích hoạt.

## 8. IdP/SSO, OAuth token và điều kiện runtime

### 8.1. Token hợp lệ về chữ ký chưa chắc còn được ủy quyền

Một OAuth access token có thể được phát khi user còn emergency grant. Khi grant hết hạn, token **vẫn có `exp` trong tương lai**. Nếu resource server chỉ kiểm chữ ký, issuer, audience và `exp` rồi tin role claim cũ, quyền có thể **sống lâu hơn emergency window**.

Có thể dùng (tùy hệ thống):
- **Access token TTL** không vượt thời hạn activation nếu token được phát riêng cho emergency.
- **Opaque token + introspection** và kiểm tra session/grant hiện hành.
- **Request-time authorization** tra trạng thái emergency grant và resource scope.
- **Revocation/invalidation** của token/session/refresh token khi có trigger.
- **Policy/entitlement version** để vô hiệu hóa cached authorization.
- **Short-lived scoped capability** gắn action/resource/audience.
- Giám sát độ trễ propagation giữa IdP, gateway và target.

Không phải ứng dụng nào cũng hỗ trợ thu hồi JWT tức thời. Cần mô tả **cửa sổ quyền tồn dư tối đa theo thiết kế** và biện pháp giảm thiểu, không hứa không thể thực hiện được.

### 8.2. OIDC ID token khác OAuth access token

**ID token** phục vụ xác thực tại relying party; **access token** phục vụ resource server. Không dùng ID token như credential gọi API hoặc làm “giấy phép admin toàn quyền”. Một claim `amr/acr` có thể chứng minh phương thức/mức assurance theo trust với IdP, **không chứng minh incident còn active** hoặc grant JIT vẫn hợp lệ.

### 8.3. Session SSO và application session

Người dùng đã đăng xuất IdP không nhất thiết làm **application session** ở mọi SaaS bị đóng ngay. Ngược lại, gỡ SCIM Group không nhất thiết xóa cookie session ứng dụng. Khi emergency kết thúc, cần kiểm tra **cơ chế session/token lifecycle của từng target**, không chỉ gọi logout trên cổng SSO.

## 9. SCIM và deprovisioning quyền khẩn cấp

**SCIM 2.0** thường hỗ trợ User và Group provisioning; nó **không định nghĩa chung một loại “emergency lease” hoặc bảo đảm session/tokens sẽ bị chặn ngay khi gỡ Group**. Một target có thể hỗ trợ mapping SCIM Group tới role nội bộ; target khác dùng API riêng hoặc PAM.

### 9.1. Ví dụ Group membership là đường cấp quyền

~~~text
IAM emergency approval
  -> IdP group emergency-platform-operators
  -> SCIM Group mapping tại SaaS target
  -> Target role emergency-admin
  -> API permission production:restart
~~~

Sau khi hết hạn:
1. Gỡ membership **ở source of authority** đúng.
2. Sync qua SCIM nếu target hỗ trợ.
3. Readback Group/User membership target.
4. Kiểm tra app role mapping và permission effective.
5. Đánh giá session/token đã được phát.
6. Mở remediation nếu role hoặc session vẫn hoạt động.

### 9.2. Đừng thay toàn bộ Group từ snapshot cũ

Nếu chỉ gỡ một member bằng SCIM PATCH, nên dùng operation chọn đúng member khi provider hỗ trợ, hoặc dùng API tương đương có kiểm soát. Gửi PUT cả danh sách từ snapshot cũ có thể ghi đè những membership hợp lệ vừa được thêm. Với API có ETag/If-Match hoặc version, cần dùng đúng cơ chế concurrency và readback.

### 9.3. Dynamic group có thể tái cấp quyền

Nếu một Group được tính động từ `department` hay `emergencyEligible=true`, gỡ membership thủ công có thể bị policy thêm lại. Cần sửa **đúng nguồn rule/attribute/grant** và kiểm tra re-provision sau deadline. Không sửa dữ liệu HRIS thành giá trị giả chỉ để chặn quyền; hãy xử lý điều kiện hoặc entitlement đúng nguồn có thẩm quyền.

## 10. RBAC/ABAC: thời hạn phải được PEP hiểu

**RBAC** xác định quyền qua role; **ABAC** xét thêm subject, action, resource và environment. Với emergency, một role được gán không đủ để cho phép action nếu:
- Identity đã Leaver.
- Incident/ticket không còn hợp lệ.
- `now >= emergencyGrant.validUntil`.
- Resource ngoài scope được phê duyệt.
- MFA/device/session requirements không đạt.
- SoD hoặc policy bắt buộc chặn.

~~~text
permitEmergencyAction =
    subject.accountState == ACTIVE
    AND hasApprovedScopedPermission(subject, action, resource)
    AND emergencyGrant.status == ACTIVE
    AND emergencyGrant.validFrom <= trustedNow
    AND trustedNow < emergencyGrant.validUntil
    AND incident.isAuthorizedAndOpen
    AND resource.tenantId == emergencyGrant.tenantId
    AND resource.resourceId in emergencyGrant.allowedResources
    AND requiredAuthenticationAndSoDControlsSatisfied
~~~

Đây là **pseudocode policy**. Các trường phải đến từ nguồn đáng tin (IAM/IGA, PAM, resource database, risk/approval system). Không tin cờ do client tự gửi như `emergency=true` hoặc `expiresAt=tomorrow`.

### 10.1. PDP, PIP và PEP

| Thành phần | Vai trò |
| --- | --- |
| **PAP** | Quản lý/chấp thuận policy emergency và ngoại lệ. |
| **PIP** | Lấy authoritative identity/JML, incident, grant, resource, risk attributes. |
| **PDP** | Đánh giá role + conditions và trả Permit/Deny/theo semantics engine. |
| **PEP** | Thực thi tại API, gateway, service hoặc dữ liệu nhạy cảm. |

**PDP Permit nhưng PEP không chặn đúng tài nguyên** có thể dẫn tới BOLA/IDOR hoặc vượt scope. Cần negative tests trên action/resource cụ thể; API bulk/export và các đường truy cập trực tiếp cũng phải được tính.

### 10.2. Không “fail open mọi API” khi PDP lỗi

Với luồng thường, nếu policy engine không có dữ liệu thời hạn đáng tin, quyền nhạy cảm nên **fail-safe** theo thiết kế. Với đường khôi phục khi PDP cũng lỗi, tổ chức phải xây **emergency path riêng đã được đánh giá và kiểm soát**, thay vì nếu timeout thì tự `Permit` cho mọi người.

## 11. Gia hạn, rút ngắn và giới hạn tổng thời gian

### 11.1. Gia hạn không phải sửa thẳng `expiresAt`

Khi khôi phục mất nhiều thời gian hơn kế hoạch, **extension** phải là một quyết định mới hoặc một nhánh workflow có kiểm soát, ghi:
- Lý do công việc/sự cố còn mở.
- Người yêu cầu và beneficiary còn eligible.
- Thời gian đã sử dụng và thời gian đề xuất thêm.
- Risk impact và quyền/action vẫn tối thiểu.
- Owner/approver độc lập khi policy yêu cầu.
- Control/monitoring vẫn hoạt động.
- Giới hạn `absoluteDeadline` nếu có.
- Policy version, approval evidence và extension count.

Một lệnh trực tiếp `UPDATE grant SET expiresAt = ...` không có authorization/review có thể biến short-lived emergency thành standing privilege.

### 11.2. Tự gia hạn liên tiếp có thể che giấu đặc quyền thường trực

~~~text
Request A: 30 phút
Extension 1: +30 phút
Extension 2: +30 phút
...
Extension 20: +30 phút

Nếu không có absolute bound và review:
  Một quyền "tạm" thành đặc quyền kéo dài hàng giờ/ngày.
~~~

Nên có **giới hạn tổng thời gian hoặc escalation cấp cao hơn** theo policy, và yêu cầu **tạo request/risk review mới** khi đạt ngưỡng. Không có giới hạn thời gian toàn cầu; cần theo rủi ro và quy trình.

### 11.3. Gia hạn trước hay sau expiry?

- **Trước expiry:** request mới phải được phê duyệt và cập nhật policy/target trước hạn, tránh quyền kéo dài ngoài kiểm soát.
- **Sau expiry:** không nên âm thầm “khôi phục hiệu lực lùi về quá khứ”; cần **activation mới** có timestamp, actor, approval và kiểm tra current eligibility.
- **Trong outage:** có thể dùng emergency extension protocol theo đường độc lập có audit; nhập bằng chứng sau sự cố mà **không sửa giả thời điểm quyết định**.

### 11.4. Thu hồi sớm

Nếu incident đóng lúc 10:20 dù role có hạn 10:45, workflow nên trigger revoke ngay theo policy, không chờ hết 25 phút còn lại. Target phải hiểu early termination bằng revocation/event hoặc runtime policy, không chỉ giữ `validUntil` cũ.

## 12. JML: thời hạn khẩn cấp phụ thuộc vòng đời danh tính

### 12.1. Joiner

Một nhân viên mới không mặc nhiên có emergency eligibility chỉ vì job title là “Engineer”. Cần:
1. Identity proofing và xác minh employment/assignment.
2. Mapping person → IdP account → privileged account.
3. Business/security owner phê duyệt eligibility phù hợp.
4. MFA/privileged access enrollment theo policy.
5. Chỉ cho emergency activation khi nhiệm vụ và incident hợp lệ.
6. Không kích hoạt trước `startDate` của assignment trừ exception onboarding riêng.
7. Readback và test rằng quyền không mặc định active.

### 12.2. Mover

Khi nhân viên chuyển từ Operations sang Finance, có thể vẫn sở hữu session hoặc token emergency từ nhiệm vụ cũ. Mover phải trigger:
- Re-evaluate emergency eligibility và active activation.
- Thu hồi role/group/PAM grants không còn căn cứ.
- Xét handover exception riêng có scope/time nếu thật sự cần.
- Kiểm tra SSO claim/attribute cũ, token và session.
- Không để quyền production tồn tại chỉ vì ticket ban đầu chưa hết hạn.

### 12.3. Leaver

**Leaver có hiệu lực thường là trigger thu hồi khẩn cấp bất kể cửa sổ đã duyệt còn bao lâu**. Theo policy:
- Disable IdP/SSO account cho truy cập mới.
- Gỡ SCIM/target entitlements và direct grants.
- Chấm dứt PAM/JIT eligibility/activations.
- Xử lý privileged/local accounts và credential.
- Revoke/rotate tokens, API keys, SSH keys/certificates khi liên quan.
- Kiểm tra app sessions, break-glass custody và những người từng biết credential.
- Readback actual access, mở remediation khi chưa chặn được.

**Không chờ reviewer quý hoặc emergency approver bấm “cho phép revoke”** nếu HRIS/contractor source đã khiến quyền không còn căn cứ theo chính sách.

### 12.4. Rehire

Nếu người tái tuyển dùng lại email hoặc IAM identity theo chính sách, không tự khôi phục emergency eligibility, old privileged accounts hay exemption/activation cũ. Phải tính lại assignment, proofing/binding và approval.

## 13. Emergency access cho service account và workload

Một workload phục hồi có thể cần quyền cloud/DB cao trong thời gian ngắn, nhưng **không có HR Joiner–Mover–Leaver giống người**. Nó có **service lifecycle**, owner/team và credential/trust riêng.

### 13.1. Workload recovery lease

Ví dụ một job phục hồi dữ liệu:
- Workload identity: `backup-restore-job`.
- Business owner: storage-platform.
- Target: `backup-vault-vn`.
- Action: `backup:restore` vào một bucket hoặc cluster.
- Trigger: approved incident/recovery ticket.
- Lease: có `validFrom`, `validUntil`, absolute bound.
- Credential: managed identity/federation hoặc short-lived token phù hợp.
- Monitoring: job ID, artifact version, resource scope, outcome.
- End: thu hồi role/token/lease, kiểm tra quyền không còn.

### 13.2. Không dùng một static key quản trị tất cả môi trường

Một API key quyền toàn tổ chức được hard-code vào pipeline emergency có thể bị sao chép và sử dụng sau sự cố. Nếu có thể, nên cấp **short-lived scoped workload credentials**; nếu nền tảng cũ chỉ hỗ trợ static secret, cần vault/custody, rotation, phạm vi mạng/resource và kế hoạch thay thế.

### 13.3. Owner con người nghỉ việc

Khi engineer phụ trách workload Leaver:
1. Chuyển service owner/sponsor.
2. Thu hồi quyền cá nhân tới vault/CI/CD/IAM.
3. Đánh giá credential người đó từng có thể trích xuất.
4. Rotate/revoke credential có rủi ro theo kiểm soát vận hành.
5. Re-evaluate emergency eligibility của workload.
6. Không xóa workload phục hồi cần thiết chỉ vì một cá nhân nghỉ việc.

### 13.4. Workload identity không tương đương MFA con người

Workload có thể dùng mTLS, workload federation, managed identity hoặc private-key JWT theo chính sách. Đó là cơ chế xác thực máy–máy, không tự là **MFA của một nhân sự**. Approval/SoD cho việc mở quyền workload phải gắn owner và người thực sự phê duyệt quyết định.

## 14. Time synchronization, clock skew và expiry boundary

### 14.1. Không tin giờ từ thiết bị client

User có thể chỉnh đồng hồ máy cá nhân. Mốc `now` dùng để quyết định emergency access phải lấy từ **server/PDP/target** hoặc nguồn tin cậy theo kiến trúc. Đừng dùng `Date.now()` trong frontend làm kiểm soát duy nhất.

### 14.2. Lưu instant, hiển thị timezone rõ

Một mốc lưu như:

~~~text
validFrom  = 2026-12-02T10:00:00+07:00
validUntil = 2026-12-02T10:45:00+07:00

Tương ứng UTC:
2026-12-02T03:00:00Z đến 2026-12-02T03:45:00Z
~~~

Dữ liệu hiển thị có thể dùng timezone người vận hành, nhưng so sánh nên dựa trên **instant đã chuẩn hóa**. Không hiểu `23:59:59` kiểu “đến hết ngày” mà bỏ milliseconds hoặc offset.

### 14.3. Clock skew không phải lý do mặc định mở thêm quyền

Token validation có thể có clock tolerance cho `iat/nbf/exp` theo hệ thống. Nhưng **thời hạn policy emergency** có thể cần chặt hơn. Nếu cho tolerance, phải tính rõ **độ trễ tối đa chấp nhận được** và hậu quả. Không để mỗi lớp tự cộng một tolerance khiến quyền kéo dài ngoài thiết kế.

### 14.4. Cache TTL và eventual consistency

Một hệ thống có thể cache `Permit` trong 10 phút. Nếu emergency grant hết hạn ngay sau khi cache, PEP vẫn có thể cho thao tác cho tới khi cache hết hạn nếu không ràng buộc deadline.

Giải pháp tùy kiến trúc:
- Cache decision **không lâu hơn grant remaining lifetime**.
- Bind cache key với subject/action/resource/grant version.
- Invalidate cache khi revoke/incident closed/JML change.
- Chặn tại target khi `now >= validUntil`.
- Test hành vi khi PIP/PDP timeout hoặc message queue chậm.

### 14.5. TOCTOU: kiểm tra trước, sử dụng sau

Với thao tác rất nhạy cảm, grant có thể hợp lệ khi bắt đầu request nhưng hết hạn **trước commit**. Cần định nghĩa action là giao dịch atomic hay chuỗi kéo dài; sử dụng transaction/version check, signed short-lived capability, step boundaries và kiểm soát kéo dài tác vụ theo policy. Không cắt thao tác phục hồi ở trạng thái nguy hiểm chỉ vì đồng hồ vượt hạn mà không có thiết kế **safe stop/checkpoint**.

## 15. Kiến trúc với control plane bị hỏng và fail-safe

Khẩn cấp thường xảy ra đúng lúc các thành phần quản trị quyền không hoạt động. Đây là điểm khó nhất của thời hạn.

### 15.1. Mô hình hai đường

~~~mermaid
flowchart LR
    U["Authorized operator"] --> A{"IAM/IdP/PAM online?"}
    A -->|Có| J["Normal JIT + MFA + approval"]
    A -->|Không| B["Pre-designed break-glass path"]
    J --> T["Target emergency capability"]
    B --> T
    T --> L["Independent logs + monitoring"]
    L --> R["Revoke/rotate/reseal after use"]
    R --> V["Post-incident reconciliation + verification"]
~~~

**Đường dự phòng phải được kiểm thử theo dependency graph**: nếu cần vault token nhưng vault chính phụ thuộc IdP đang lỗi, đường dự phòng thất bại. Nếu dùng recovery credential luôn tồn tại, phải bù bằng custody, alert, scope và audit. Không có cách “TTL trong IAM” tự giải quyết mọi outage.

### 15.2. Khi không thể tự revoke lúc offline

Một hệ thống isolated recovery có thể không liên lạc IAM trong lúc sự cố. Không nên tuyên bố hết `validUntil` sẽ ngay lập tức revoke nếu target không thực thi hoặc không có đồng hồ/lease đáng tin.

Thiết kế cần xác định:
- **Local enforcement** có thể đọc hạn và chặn không?
- Credential có thời hạn tự xác minh (ví dụ certificate) không?
- Có thể rotate local credential sau khi phục hồi không?
- Có thể cắt kết nối mạng hoặc cô lập quyền tạm như containment không?
- Kênh log/custody nào hoạt động offline?
- Sau phục hồi, ai phải reconcile và xác minh?
- Rủi ro quyền tồn dư trong outage được ai chấp nhận, trong phạm vi nào?

### 15.3. Availability không phải lý do fail-open toàn hệ thống

Đừng đặt “nếu PDP timeout thì allow mọi admin API”. Đó là **bypass có thể bị khai thác**. Thay vào đó, chuẩn bị một **narrow break-glass channel** tách biệt và có giới hạn, phù hợp tình huống khôi phục.

### 15.4. Bảo vệ nguồn credential khẩn cấp

- Có ít nhất các người/đội có quyền khôi phục theo policy, tránh single point of failure.
- Credential không nằm trong tài liệu công khai, chat hoặc source code.
- Có quy trình cấp phát/niêm phong/đổi lại sau dùng.
- Cảnh báo mọi lần truy cập emergency account khi hệ thống quan sát có thể hoạt động.
- Định kỳ kiểm thử cả **tính dùng được** lẫn **quy trình hết quyền**.
- Tách person identity và shared recovery account thông qua custody/session logs khi khả thi.

## 16. Renewal, extension và approval độc lập

### 16.1. Ai có thể gia hạn?

Tùy mức rủi ro, một extension có thể cần:
- Incident commander/business owner xác nhận sự cố chưa kết thúc.
- Resource owner xác nhận đúng target/action.
- Security/risk owner chấp nhận thời gian đặc quyền tiếp tục.
- PAM approver/SoD reviewer độc lập khi cần.
- Beneficiary không tự ký nếu policy yêu cầu độc lập.

Một emergency account quản trị không được tự sửa **approval policy hoặc absolute deadline** của chính yêu cầu của mình.

### 16.2. Quyết định phải bám snapshot

~~~text
Extension V1: service:restart, cluster-vn-2, đến 10:45
Extension V2: cloud:owner, all-clusters, đến 18:00

V2 thay action/scope/risk:
  Không thể dùng approval V1 như đã chấp thuận V2.
~~~

Cần `requestVersion`/scope hash, approval timestamp và người ký. Bất kỳ thay đổi material nào cũng cần re-evaluate và reapprove theo policy.

### 16.3. Escalation khi approver vắng mặt

Timeout nên dẫn tới reminder, alternate approver có authority, escalation hoặc emergency route độc lập. Không tự kéo dài privileged access vì “không có ai bấm từ chối”.

## 17. Revocation sau emergency: đóng đúng tất cả đường

### 17.1. Checklist theo lớp

| Đường quyền | Việc cần làm khi hết hạn | Bằng chứng |
| --- | --- | --- |
| **PAM/JIT grant** | Deactivate và gỡ temporary role. | PAM state + target readback. |
| **IdP group/role** | Gỡ đúng source grant; sync xuống target. | IdP/SCIM Group membership absent. |
| **Application direct grant** | Xóa resource-scoped entitlement. | App/cloud/DB permission readback. |
| **Privileged/local account** | Disable/khóa nếu dùng riêng cho emergency; hoặc reset custody nếu là recovery account dài hạn. | Target login/access state, credential audit. |
| **SSH/RDP/DB session** | Terminate hoặc hạn chế thao tác theo khả năng. | Session inventory/target enforcement evidence. |
| **OAuth access/refresh token** | Revoke/invalidate hoặc bảo đảm request-time expiry. | Token status/introspection/API authorization. |
| **PAT, API key, SSH key/cert** | Revoke/rotate/hết hạn theo loại credential. | Credential inventory + verification. |
| **Break-glass credential** | Rotate/reseal khi cần, cập nhật custody, bảo đảm recovery path cho lần sau. | Credential rotation/custody evidence. |
| **Delegated/admin approvals** | Hủy exception/delegation không còn căn cứ. | Approval/exception registry. |
| **Audit/monitoring** | Đối soát thao tác và cảnh báo bất thường. | Review outcome, incident closure. |

### 17.2. “Đã revoke” khác “không thể dùng lại”

Để một emergency role không tự bật lại, cần tìm:
- Dynamic group rule tự cấp lại.
- Scheduled provisioning job.
- Local admin account chưa được inventory.
- Nested group hoặc role hierarchy cho permission tương đương.
- Resource policy và IAM trust cho impersonation.
- Secret hoặc token đã được trích xuất.
- Một request activation cũ bị retry sau expiry.

**Readback một Group không chứng minh tất cả đường grant đã mất** nếu mục tiêu là thu hồi effective privileged access.

### 17.3. Đóng hồ sơ với residual access

Nếu quyền còn tồn dư:
- Đánh dấu `REMEDIATION_REQUIRED`, không `VERIFIED_CLOSED`.
- Phân loại severity theo action/resource và thời gian còn tiếp tục.
- Contain bằng policy deny, credential disable, network isolation hoặc biện pháp phù hợp được phê duyệt.
- Phân công target owner và deadline.
- Giữ log, trace và evidence.
- Lặp readback/negative test an toàn sau sửa.
- Escalate nếu vượt revocation SLA.

## 18. State machine cho một emergency activation

~~~mermaid
stateDiagram-v2
    [*] --> REQUESTED
    REQUESTED --> VALIDATED: identity + incident + policy
    VALIDATED --> APPROVED: mandatory approvals
    APPROVED --> READY: controls and target available
    READY --> ACTIVE: activate scoped grant
    ACTIVE --> ENDING: operator stops / incident closed
    ACTIVE --> EXPIRED: validUntil reached
    ACTIVE --> SUSPENDED: risk or control failure
    ENDING --> REVOKING
    EXPIRED --> REVOKING
    SUSPENDED --> REVOKING
    REVOKING --> PENDING_RECONCILIATION
    PENDING_RECONCILIATION --> VERIFIED_CLOSED: actual access blocked
    PENDING_RECONCILIATION --> REMEDIATION_REQUIRED: privilege persists
    REMEDIATION_REQUIRED --> REVOKING: containment + fix
    VERIFIED_CLOSED --> [*]
~~~

**Đây là mô hình minh họa**, không phải trạng thái bắt buộc của mọi PAM/IGA. Một break-glass flow offline có thể thu thập evidence sau khi phục hồi, nhưng không được giả mạo việc đã kiểm chứng trong thời gian offline.

### 18.1. Các invariants cần giữ

- Không active trước `validFrom` hoặc sau `validUntil` theo quyền được cấp.
- Không mở rộng scope/action sau approval nếu không reapprove.
- Một user Leaver không tiếp tục có quyền emergency thông thường chỉ vì deadline chưa tới.
- Gia hạn phải chịu risk/authority constraints, không tự sửa expiration.
- Token/session cũ không làm bypass deadline khi policy yêu cầu chặn.
- Một activation đã Cancel/Expired không được tái kích hoạt qua retry.
- Mất monitoring/control bắt buộc cần hành vi fail-safe theo policy.
- Không coi trạng thái `EXPIRED` là `VERIFIED_CLOSED` trước reconciliation.

## 19. Pseudocode: cấp một lease và chặn ở thời điểm request

### 19.1. Cấp activation hẹp

~~~text
function activateEmergency(request, trustedNow):
    identity = resolveAuthoritativeIdentity(request.beneficiary)
    incident = loadApprovedIncident(request.incidentId)
    policy = loadEmergencyPolicy(request.policyId)
    target = resolveTargetAndResource(request)

    require identity.active
    require identity.eligibleForEmergencyRole(request.role, target)
    require incident.isOpenAndAuthorized
    require request.hasRequiredApprovals(policy)
    require request.passesSoDAndRiskChecks
    require request.scopeIsWithinApprovedBoundaries
    require emergencyControlsAreReady

    start = max(trustedNow, request.validFrom)
    end = min(
        start + policy.maxActivationDuration,
        request.validUntil,
        incident.authorizedUntil,
        identity.assignmentValidUntil,
        policy.absoluteDeadline
    )
    require end > start

    grant = provisionScopedEmergencyGrantOnce(
        identity, target, request.action, request.resourceScope,
        start, end, request.version, request.idempotencyKey
    )

    readbackAndVerifyActivation(grant)
    return grant
~~~

Pseudocode không được chạy trực tiếp; các hệ thống khác nhau có policy và trường dữ liệu khác nhau. Nếu `identity.assignmentValidUntil` hoặc `policy.absoluteDeadline` không được xác định, phải có semantics rõ theo policy, không lấy giá trị tùy ý.

### 19.2. Kiểm tra tại PEP

~~~text
function authorizeEmergencyAction(subject, action, resource, context):
    require authenticationAndTokenValidationPass(context)
    require subject.identityActive
    require resource.existsAndTrusted

    grant = findActiveEmergencyGrant(subject, action, resource)

    if grant missing:
        return DENY

    now = trustedServerTime()
    if now < grant.validFrom or now >= grant.validUntil:
        return DENY

    if grant.revoked or grant.suspended:
        return DENY

    if grant.incidentClosedOrApprovalWithdrawn:
        return DENY

    if not grant.scopeCovers(action, resource):
        return DENY

    if not requiredMfaSoDAndMonitoringConditionsSatisfied:
        return DENY

    return PERMIT_FOR_THIS_ACTION_AND_RESOURCE
~~~

Đây là khung khái niệm: thực thi phải có các kiểm tra authorization còn lại, object-level scope, transaction integrity, logging, policy semantics và xử lý thời gian chính xác. Không để một `Permit` cached vô hạn vượt deadline.

### 19.3. Tính token expiry

Nếu hệ thống cấp **access token riêng cho emergency lease** và target chỉ tin token tại request, một ranh giới cần xét:

~~~text
token.expiresAt <= emergencyGrant.validUntil
token.audience == intendedResourceServer
token.scope subset_of emergencyGrant.approvedActions
~~~

Điều này giúp giảm rủi ro nhưng **không đủ** khi incident đóng sớm, user Leaver hoặc token bị compromise: có thể cần revocation/request-time authorization. Không lấy ID token làm access token.

## 20. Concurrency, idempotency và các tình huống sát hạn

| Tình huống | Rủi ro | Kiểm soát |
| --- | --- | --- |
| Approval tới đúng lúc user Leaver. | Cấp quyền không còn căn cứ. | Revalidate JML trước grant và ở target. |
| Hai approvers cùng ký, hai workers cùng provision. | Grant trùng hoặc tăng TTL ngoài ý muốn. | Atomic finalization, idempotency key. |
| Renewal gửi sau deadline nhưng queue xử lý muộn. | Grant cũ hồi sinh. | Deadline/version check ở worker. |
| Incident đóng trong khi activation đang xử lý. | Role active dù sự cố đã hết. | Current incident revalidation. |
| SCIM PATCH timeout nhưng target đã gỡ group. | Retry sai hoặc ghi đè. | Target readback và idempotent reconcile. |
| Token phát hành ngay trước hết hạn. | Token còn hiệu lực lâu hơn lease. | Bound token TTL, resource authorization check. |
| Cache Permit còn sau revoke. | Vượt deadline/early stop. | Cache bounded by remaining lease và invalidation. |
| Clock ở target chậm hơn PDP. | Quyền kéo dài ngoài mốc thiết kế. | Clock sync, skew budget, safe boundaries. |
| Mất mạng tại recovery target. | Không nhận revoke event. | Local expiry enforcement, containment và post-recovery reconciliation. |
| Credential rotation sau dùng làm hỏng recovery account duy nhất. | Không còn đường khôi phục tương lai. | Tested rotation/resealing with independent recovery readiness. |
| Session đang thực hiện write quan trọng khi hết hạn. | Trạng thái dữ liệu hỏng nếu kill tức thời. | Transaction-safe stopping và thiết kế checkpoint trước. |

### 20.1. Idempotency key gắn phiên bản và target

~~~text
activationKey =
    emergencyRequestId + ":" +
    requestVersion + ":" +
    targetAccountId + ":" +
    approvedScopeHash
~~~

Cùng request/version không được tạo nhiều grant ngầm hoặc **tự cộng dồn duration** khi retry. Đối với retry sau timeout, trước hết phải đọc lại target/activation state.

### 20.2. Kiểm soát race khi thay đổi quyền theo JML

Một worker activation có thể kiểm tra employee ACTIVE lúc 10:00:00, HRIS đánh dấu Leaver lúc 10:00:01, worker cấp admin lúc 10:00:02. Cần policy về **mốc nguồn có thẩm quyền, event ordering, version/check trước commit và revocation worker** để giảm cửa sổ. Với tác động lớn có thể cần request-time check tại PEP, không dựa vào một snapshot employee status duy nhất.

## 21. JSON event mẫu và bằng chứng thời hạn

~~~json
{
  "eventId": "emergency-activation-2026-0482",
  "correlationId": "incident-2026-482",
  "actorIdentityId": "person-2048",
  "target": {
    "system": "production-platform",
    "accountRef": "ops-admin-2048",
    "resourceRef": "cluster-vn-2/service-catalog",
    "actions": ["service:restart"]
  },
  "approval": {
    "policyId": "emergency-jit-v4",
    "requestVersion": 2,
    "resourceOwnerRef": "person-901",
    "riskOwnerRef": "person-902"
  },
  "window": {
    "validFrom": "2026-12-02T10:00:00+07:00",
    "validUntil": "2026-12-02T10:45:00+07:00",
    "absoluteDeadline": "2026-12-02T12:00:00+07:00"
  },
  "activation": {
    "status": "ACTIVE",
    "pamActivationId": "pam-act-0482",
    "targetReadback": "SCOPE_MATCHED"
  },
  "revocation": {
    "trigger": null,
    "status": "NOT_YET_DUE"
  },
  "verification": {
    "status": "PENDING"
  }
}
~~~

**Đây là JSON minh họa nội bộ**, không phải schema chuẩn của SCIM/PAM/OIDC. Khi đã revoke, cần bổ sung thời điểm, action, connector, session/token check, target readback và kết quả. Không ghi password, private key, OTP, full token hoặc dữ liệu nhạy cảm không cần thiết.

### 21.1. Chuỗi audit cần thiết

~~~text
EMERGENCY_REQUESTED
IDENTITY_AND_ELIGIBILITY_CHECKED
MANDATORY_APPROVALS_RECORDED
SCOPE_AND_DURATION_CALCULATED
GRANT_ACTIVATION_STARTED
TARGET_GRANT_READBACK_VERIFIED
PRIVILEGED_ACTION_RECORDED
INCIDENT_CLOSED_OR_LEASE_EXPIRED
GRANT_DEACTIVATION_STARTED
SESSION_TOKEN_CREDENTIAL_REVIEWED
TARGET_EFFECTIVE_ACCESS_VERIFIED
EMERGENCY_CASE_CLOSED_OR_REMEDIATION_OPENED
~~~

Với break-glass offline, có thể có **manual custody and decision evidence** thu thập trong sự cố rồi nhập sau. Cần giữ timestamp thật, actor thực và giải thích độ trễ ghi nhận; không sửa log quá khứ để “trông như hệ thống online”.

### 21.2. Phân biệt bốn dấu mốc chứng cứ

| Dấu mốc | Câu hỏi |
| --- | --- |
| **ApprovedAt** | Ai cho phép đường emergency, trong scope/window nào? |
| **ActivatedAt** | Target thực sự có grant từ lúc nào? |
| **RevokedAt** | Lệnh hoặc policy đã chặn quyền từ khi nào? |
| **VerifiedAt** | Evidence xác nhận action không còn được phép từ khi nào? |

Nếu `RevokedAt=10:45` nhưng `VerifiedAt=11:20` và target logs cho thấy một privileged action lúc 11:00, phải báo **residual-access breach** thay vì gộp cả hai vào “đã xong lúc 10:45”.

## 22. Tình huống xuyên suốt: IdP lỗi và kỹ sư phải khôi phục

**Bối cảnh:** Doanh nghiệp có HRIS/IAM, IdP SSO, PAM/JIT, cloud và ứng dụng hỗ trợ một phần SCIM. Lúc 10:00 IdP gặp lỗi khiến kỹ sư không thể đăng nhập qua SSO để sửa cấu hình.

### 22.1. Đường JIT bình thường không khả dụng

Lan đang là SRE trực ca, nhưng PAM yêu cầu đăng nhập IdP. Nếu mọi đường emergency đều dựa vào PAM/IdP, doanh nghiệp có thể **mất khả năng khôi phục chính IdP**. Vì vậy phải có **đường break-glass đã chuẩn bị và kiểm thử trước**.

### 22.2. Kích hoạt qua quy trình dự phòng

- Incident commander xác nhận phạm vi sự cố và mốc bắt đầu.
- Người có quyền theo custody policy truy xuất emergency credential.
- Quy trình hai người hoặc kiểm soát tương đương được áp nếu bắt buộc và khả dụng.
- Ghi danh tính người dùng thật, account đích, resource, action và hạn.
- Chỉ dùng quyền cần để khôi phục IdP/control plane.
- Kích hoạt independent alert/logging còn khả dụng; bảo vệ evidence sau sự cố.

**Không mặc định mọi employee đều có thể dùng recovery credential** chỉ vì SSO đang hỏng.

### 22.3. Vấn đề thời hạn

Chính sách cho phép dùng quyền trong cửa sổ khôi phục đến 10:45, nhưng công việc chưa xong lúc 10:35. Đội cần xin **extension** theo emergency protocol được chuẩn bị. Nếu không có đường approval online, ghi quyết định thật qua phương án dự phòng, có risk owner và giới hạn tổng thời gian.

Nếu credential recovery account **không tự hết hạn**, các controls về custody và use window vẫn có giá trị, nhưng **không nên khẳng định target tự khóa lúc 10:45** nếu nó không thực thi deadline. Đặt rõ điều kiện gỡ/sửa quyền, rotate/reseal sau sự cố và kiểm tra thực tế.

### 22.4. Sau khi IdP phục hồi

1. Chấm dứt dùng break-glass account.
2. Terminate emergency sessions nếu khả thi.
3. Rotate hoặc reseal credential theo policy, bảo đảm recovery readiness.
4. Gỡ các temporary role/group/direct grants đã thêm trong lúc sửa.
5. Kiểm tra token/keys/credential đã phát sinh.
6. Đối soát cấu hình security/IdP có thay đổi ngoài phạm vi không.
7. Đọc lại quyền ở cloud/IdP/SCIM targets và kiểm tra action ngoài emergency window bị chặn.
8. Audit độc lập mọi thao tác, đóng incident hoặc mở remediation.

### 22.5. Nếu Lan thành Leaver trước khi case được đóng

HRIS event phải kích hoạt thu hồi quyền cá nhân, PAM/JIT eligibility và session/token theo policy; đánh giá credential break-glass mà Lan từng biết. Không chờ incident postmortem mới xử lý. Đường recovery cho người khác vẫn phải sẵn sàng.

**Bài học:** Một account dự phòng có thể cần tồn tại để bảo đảm availability, nhưng **việc sử dụng quyền qua account đó** phải được giới hạn, giám sát và kết thúc bằng **target evidence**; không dùng “IdP đang lỗi” làm lý do bỏ qua toàn bộ governance.

## 23. Tình huống: JIT hết hạn nhưng JWT và SSH session còn sống

**Bối cảnh:** Một engineer được JIT quyền `database:maintain` từ 14:00–14:30.

### 23.1. Điều xảy ra

- 14:00: PAM role active.
- 14:05: Engineer mở DB session qua broker.
- 14:10: Client có access token hết hạn 15:10.
- 14:30: PAM UI hiển thị `EXPIRED`.
- 14:35: Engineer vẫn có thể thực hiện thao tác DB qua session.
- 14:40: Một REST API tiếp tục nhận token cũ.

### 23.2. Phân tích

Đang có ít nhất **hai residual paths**:
1. DB session không bị chặn dù activation lease hết.
2. API token không ràng buộc đúng emergency deadline/authorization hiện hành.

### 23.3. Hướng xử lý

- Định nghĩa session termination/command enforcement khi PAM lease kết thúc.
- Cân nhắc token bound `exp` theo grant hoặc runtime authorization.
- Phát revoke/invalidations phù hợp khi incident đóng sớm.
- Readback cả PAM state và target sessions/tokens.
- Test một thao tác **không phá hủy** sau hạn trong môi trường/đối tượng được ủy quyền.
- Báo remediation/incident nếu target tiếp tục cho quyền ngoài SLA.

**Không xóa log hoặc “chỉnh lại `validUntil` thành 15:10” để hợp thức hóa quyền còn hoạt động.**

## 24. Tình huống: workload phục hồi sao lưu

**Bối cảnh:** Job `backup-restore` bình thường chỉ được đọc metadata. Trong sự cố mất dữ liệu, job cần `backup:restore` vào một resource cụ thể.

### 24.1. Phương án hạn chế

- Workload identity được kiểm chứng bằng trust phù hợp.
- Service owner và incident owner xác nhận scope.
- Tạo temporary role/credential scoped tới backup vault và restore target.
- Lease có duration vừa đủ, absolute limit và monitoring.
- Chỉ chạy artifact/job version được duyệt.
- Hết tác vụ, revoke role/secret, kết thúc job session và đọc lại permission.
- Owner team chịu trách nhiệm giải trình; không để “bot tự xin, tự duyệt, tự cấp admin”.

### 24.2. Rủi ro hậu sự cố

Một static API key được dùng để phục hồi có thể nằm trong environment variables, logs hoặc artifacts. Khi đã dùng credential có quyền cao, phải đánh giá exposure và rotation. Nếu job tiếp tục chạy bằng role admin dù phục hồi xong, đó là **workload residual privilege** cần khắc phục.

## 25. Ma trận kiểm thử thời hạn khẩn cấp

| Test | Tình huống | Kết quả kỳ vọng |
| --- | --- | --- |
| **T1 — Before start** | Attempt lúc `now < validFrom`. | Deny, không activate sớm. |
| **T2 — At start** | `now == validFrom` và mọi điều kiện hợp lệ. | Permit đúng scope nếu policy cho phép. |
| **T3 — At expiry** | `now == validUntil`. | Deny cho action không còn căn cứ. |
| **T4 — Past expiry** | Token/session cũ thử action sau hạn. | Deny theo revocation/enforcement policy. |
| **T5 — Early close** | Incident đóng trước `validUntil`. | Revoke/suspend kịp và readback. |
| **T6 — Leaver** | HRIS phát Leaver trong active window. | Chặn quyền cá nhân theo JML, không chờ expiry. |
| **T7 — Mover** | Assignment đổi làm mất eligibility. | Re-evaluate/terminate hoặc có exception riêng. |
| **T8 — Extension approval** | Renewal đủ risk owner và scope hợp lệ. | New approved window, không vượt hard cap. |
| **T9 — Extension missing** | Approver không phản hồi. | Escalate/expire; không auto-extend. |
| **T10 — Max lifetime** | Tổng renewals vượt `absoluteDeadline`. | Block/escalate theo policy, không lặng lẽ kéo dài. |
| **T11 — Scope bypass** | Restart service khác cùng cluster. | Deny dù role emergency active. |
| **T12 — IdP outage** | JIT phụ thuộc IdP không hoạt động. | Đường break-glass hợp lệ vẫn có thể khôi phục. |
| **T13 — Vault outage** | Recovery credential nằm sau vault cũng offline. | Có phương án dự phòng đã kiểm thử; ghi risk. |
| **T14 — PAM session** | Lease hết nhưng SSH/DB session chưa đóng. | Session/action bị chặn hoặc remediation được mở. |
| **T15 — Stale JWT** | Access token có `exp` sau grant deadline. | Resource server không cho phép vượt window. |
| **T16 — Cached permit** | PDP cache Permit trước expiry. | Cache không làm vượt deadline. |
| **T17 — Clock skew** | Target clock lệch. | Enforce trong tolerance policy; đo worst-case latency. |
| **T18 — Queue retry** | Activation job chạy lại sau expiry. | No reactivation, idempotency. |
| **T19 — Dynamic group** | Group tự gán lại grant đã revoke. | Source rule được sửa, reconciliation phát hiện. |
| **T20 — Workload owner** | Người owner Leaver nhưng job còn cần. | Thu hồi quyền cá nhân, chuyển owner, giữ workload đúng scope. |
| **T21 — Rotation** | Recovery password rotated sau dùng. | Credential cũ không dùng được; recovery path mới được kiểm thử. |
| **T22 — Broken audit** | Log collector offline trong incident. | Có evidence dự phòng; post-use review, không silent closure. |
| **T23 — Parallel approvals** | Hai approvals tới đồng thời. | Một activation hữu hiệu, đúng version/time. |
| **T24 — Cancellation** | Beneficiary rút yêu cầu giữa activation. | Early termination theo policy, no stale grants. |

### 25.1. Test cả positive và negative

Một thay đổi an toàn phải chứng minh:
- **Positive:** kỹ sư **có thể thực hiện đúng tác vụ khôi phục hợp lệ** trong cửa sổ đã duyệt.
- **Negative:** không thể thực hiện action ngoài resource, ngoài thời gian hoặc bằng identity không có thẩm quyền.
- **Failure:** dependency outage không gây fail-open toàn hệ thống hoặc mất hoàn toàn đường recovery đã được thiết kế.
- **Closure:** sau hạn, actual access đã giảm; không chỉ request status là EXPIRED.

Chỉ kiểm tra “có đăng nhập thành công khi khẩn cấp” là **chưa đủ** để xác minh cả vòng đời.

## 26. Audit, KPI và cách đo thực sự hết quyền

### 26.1. KPI gợi ý

| KPI | Ý nghĩa | Cần tránh |
| --- | --- | --- |
| **Emergency activation count** | Số lần quyền emergency được sử dụng theo service/risk. | Nhiều lần chưa chắc là lạm dụng nếu incident có thật. |
| **Mean/median active duration** | Thời gian grant thực sự active. | Lấy thời gian ticket thay active state. |
| **Exposure beyond approved window** | Tổng thời gian actual permission còn dùng được sau deadline. | Không tính token/session cũ. |
| **Early revocation latency** | Từ incident close/approval withdrawn tới quyền bị chặn. | Chỉ ghi timestamp revoke request. |
| **Verified closure rate** | Tỷ lệ emergency cases có evidence target đã chặn. | Coi `EXPIRED` là verified. |
| **Extension frequency** | Số gia hạn mỗi incident/identity/role. | Renewals liên tục có thể là standing privilege trá hình. |
| **Unscoped emergency grants** | Grants rộng hơn tài nguyên/action được duyệt. | Chỉ nhìn role name, bỏ resource policy. |
| **Break-glass readiness** | Đường recovery có được kiểm thử theo dependency outage không? | Một login test online không đủ. |
| **Credential rotation compliance** | Credential yêu cầu rotation/resealing đã được xử lý đúng policy. | Rotation làm mất đường recovery duy nhất. |
| **JML forced revocation success** | Mover/Leaver dừng emergency access đúng SLA. | Dựa vào HRIS event mà không đọc target. |
| **Residual access reappearance** | Quyền đã revoke lại được dynamic group/job cấp. | Không chỉ kiểm tra một thời điểm. |
| **Independent post-use review** | Có reviewer hợp lệ đã kiểm tra logs/commands. | Log được thu không đồng nghĩa đã được xem xét. |
| **Workload emergency owner coverage** | Non-human grants có owner/expiry/service purpose rõ. | Không quản lý vì không có employee HR record. |

### 26.2. Bằng chứng cần để đóng

Một hồ sơ nên thể hiện:
1. Incident/emergency request và authorization basis.
2. Identity/account binding và danh tính người thật.
3. Scope/action/resource và thời hạn được duyệt.
4. Approval/authority (hoặc route emergency đã được phê duyệt trước).
5. Activation/credential/session thực tế.
6. Các hành động đặc quyền đã thực hiện.
7. Early close/expiry/Leaver triggers.
8. Deactivation/revocation commands và target responses.
9. Session/token/credential review.
10. Target readback hoặc negative tests có kiểm soát.
11. Post-use independent review, kết luận và remediation owner nếu cần.

**Không ghi plaintext password, private key, OTP, full access token hoặc dữ liệu nhạy cảm không cần thiết** vào ticket hoặc log. Với shared emergency account, cần giữ được attribution của người sử dụng theo cơ chế custody/session/ticket.

### 26.3. Không dùng một trạng thái “COMPLETED” cho mọi lớp

Một mẫu báo cáo hữu ích:

~~~text
Emergency approval:         APPROVED
Activation lease:           EXPIRED
PAM deactivation:           SUCCEEDED
Target role readback:       REMOVED
SSO/app sessions:           VERIFIED_CLOSED
Access token invalidation:  PENDING
Direct grants:              VERIFIED_ABSENT
Effective privileged action: STILL_ALLOWED
Overall closure:            REMEDIATION_REQUIRED
~~~

**Overall** chưa thể `VERIFIED_CLOSED` nếu còn effective action trái thời hạn, dù phần lớn các bước con đã thành công.

## 27. Anti-patterns và cách tránh

| Sai lầm | Hậu quả | Cách sửa |
| --- | --- | --- |
| Cấp GlobalAdmin vô hạn “để dự phòng”. | Đường đặc quyền thường trực khó kiểm soát. | Break-glass custody/monitoring và permission narrowing nếu khả thi. |
| Tin `expiresAt` trong ticket là target đã revoke. | Session/token có thể vẫn dùng được. | Runtime enforcement + readback. |
| Token TTL 60 phút cho activation chỉ 15 phút mà API không recheck. | Residual privileged access 45 phút. | Bound token expiry hoặc policy revalidation. |
| Đặt recovery account phụ thuộc IdP đang cần phục hồi. | Không thể break glass khi outage. | Recovery architecture độc lập, kiểm thử. |
| “PAM timeout thì allow mọi request”. | Fail-open nghiêm trọng. | Emergency path riêng có scope và audit. |
| Đặt hạn quá ngắn khiến operator phải gia hạn liên tục. | Rủi ro thao tác vội và workaround. | Chọn duration theo nhiệm vụ, có extension controls. |
| Gia hạn bằng chỉnh date không approval. | Standing privilege trá hình. | Versioned request/risk review. |
| User tự duyệt emergency admin của chính mình bằng account thứ hai. | SoD thất bại. | Person identity binding và authority. |
| Không revoke sớm khi incident đóng. | Quyền thừa tiếp tục khả dụng. | Early termination trigger. |
| Chỉ remove IdP group, bỏ local account/direct grant. | Còn đường quản trị khác. | Grant-path reconciliation. |
| Dùng SCIM PATCH làm bằng chứng session đã đóng. | Token/session tiếp tục. | Kiểm tra target runtime. |
| Clock client quyết định `now`. | Người dùng chỉnh thời gian để mở quyền. | Trusted server clock và policy. |
| Cache Permit không ràng buộc TTL. | Quyền còn sau hạn. | Cache expiry <= remaining lease; invalidation. |
| Hết hạn trong lúc recovery transaction nhưng không có safe-stop. | Có thể làm hỏng dữ liệu hoặc gián đoạn. | Checkpoint và transaction-safe expiry semantics. |
| Rotate recovery credential mà không kiểm tra đường dự phòng. | Lockout lần sau. | Tested reseal/rotation và redundancy. |
| Quên human owner khi workload chạy emergency. | Orphaned privileged identity. | Service owner registry và credential lifecycle. |
| Leaver vẫn giữ JIT eligibility vì ticket chưa đóng. | Quyền truy cập không còn căn cứ. | Event-driven JML revocation. |
| Bỏ qua monitoring khi offline rồi đóng case ngay. | Không có accountability. | Independent offline evidence + post-use review. |
| Dùng một policy emergency để bypass mọi luật/SoD bắt buộc. | Vi phạm kiểm soát cốt lõi. | Non-waivable rules và phương án khôi phục hợp lệ. |
| Coi 100% expired tickets là 100% revoked. | Đánh giá sai residual exposure. | Đo actual effective-access closure. |

## 28. Checklist triển khai thời hạn khẩn cấp

### 28.1. Trước sự cố

- [ ] Có inventory emergency roles, privileged accounts và break-glass credentials với owner.
- [ ] Tách normal JIT path khỏi recovery path khi IdP/PAM có thể outage.
- [ ] Test dependency tree để emergency access vẫn dùng được khi thành phần được phục hồi bị lỗi.
- [ ] Định nghĩa `validFrom`, `validUntil`, max activation TTL và hard deadline nếu áp dụng.
- [ ] Chọn duration theo impact, scope, nhiệm vụ và khả năng revoke.
- [ ] Phân biệt approval validity, lease, session, token/credential và verification SLA.
- [ ] Có route approval/SoD hoặc emergency pre-authorization phù hợp policy.
- [ ] Không mặc định mọi employee có quyền GlobalAdmin.
- [ ] Chuẩn bị credential custody, MFA/trust, logging, alert và independent review.
- [ ] Có kế hoạch extension, early termination và containment.
- [ ] Có cơ chế target enforcement và âm bản test ở ranh giới thời gian.
- [ ] Có phương án rotation/resealing mà không gây lockout recovery account.

### 28.2. Khi kích hoạt

- [ ] Xác minh identity/account và business/incident purpose.
- [ ] Xác định target/resource/action scope rõ và tối thiểu.
- [ ] Revalidate JML, SoD, effective assignment và current policy.
- [ ] Kiểm tra required approvals và control readiness.
- [ ] Grant/credential có validity không vượt phạm vi được duyệt.
- [ ] IdP/SSO/PAM/target có logging/correlation ID theo khả năng.
- [ ] Token audience/scope/session không vượt quyền emergency.
- [ ] Readback grant active tại target và positive/negative kiểm thử được ủy quyền.
- [ ] Monitoring nhận được cảnh báo và incident owner có thể kết thúc sớm.

### 28.3. Sau hạn hoặc khi kết thúc sớm

- [ ] Trigger revoke khi `validUntil`, incident close, Mover/Leaver hoặc security alert.
- [ ] Deactivate PAM/JIT, gỡ group/role/direct grants và delegation.
- [ ] Đánh giá app sessions, access/refresh tokens, PAT, API keys, SSH/RDP/DB sessions.
- [ ] Rotate/reseal credentials đã được dùng khi policy yêu cầu; giữ khả năng khôi phục.
- [ ] Kiểm tra dynamic/nested groups và tự cấp lại từ automation.
- [ ] Readback actual target access và negative tests an toàn.
- [ ] Có incident/post-use audit độc lập và owner chịu trách nhiệm.
- [ ] Nếu chưa đạt, mở `REMEDIATION_REQUIRED`, containment và SLA.
- [ ] Không đóng `VERIFIED_CLOSED` chỉ vì ticket/PAM ghi `EXPIRED`.
- [ ] Kiểm tra lại emergency readiness sau rotation và điều chỉnh runbook.

## 29. Bài tập tự kiểm tra

### 29.1. Bài A — Phân biệt hai hạn

Một JIT role có `validUntil=10:30` nhưng access token `exp=11:00`. API chỉ kiểm chữ ký và `exp`. Quyền có thực sự kết thúc lúc 10:30 không? Hãy mô tả cách dùng scoped token TTL, introspection/revocation hoặc request-time policy để chặn.

### 29.2. Bài B — IdP outage và recovery account

IdP offline nên PAM login không dùng được. Một đề xuất là “mở admin API không cần xác thực cho đến khi hệ thống hoạt động trở lại”. Hãy đánh giá rủi ro và xây một break-glass path đã chuẩn bị, bảo vệ credential, log, hạn sử dụng và hậu kiểm.

### 29.3. Bài C — Gia hạn nhiều lần

Engineer xin 30 phút rồi gia hạn 12 lần liên tiếp. Điều gì khiến đây có thể là standing privilege trá hình? Hãy đề xuất giới hạn thời lượng tổng, escalation/approval và audit renewal.

### 29.4. Bài D — Incident đóng sớm

Ticket đã đóng lúc 10:20, nhưng `validUntil=10:45`. Có nên để quyền còn tới 10:45 không? Cần những trigger và readback nào để bảo đảm chấm dứt sớm?

### 29.5. Bài E — Mover/Leaver giữa emergency

Lan chuyển sang Finance hoặc trở thành Leaver khi đang có privileged session. Vì sao effective date của HRIS có thể vô hiệu hóa căn cứ dù lease chưa hết? Nêu các bước revoke ở IdP, SCIM, PAM, local accounts và token.

### 29.6. Bài F — Workload recovery

Job `backup-restore` có một static cloud admin key vô hạn. Thiết kế workload identity và grant phục hồi có scope, thời hạn, owner và credential lifecycle; phân biệt quyền job với quyền nhân sự operator.

### 29.7. Bài G — Clock skew

PDP dùng UTC chuẩn, target clock chậm ba phút và cache Permit thêm 10 phút. Dự đoán rủi ro expiry, đề xuất đồng bộ giờ, bound cache TTL và test ở ranh giới.

### 29.8. Bài H — Session không ngắt

PAM hiển thị `EXPIRED` nhưng DB session vẫn dùng được và credential root đã checkout. Vì sao không được đóng emergency case? Cần kiểm tra session termination, secret rotation và actual authorization như thế nào?

### 29.9. Bài I — Rotation gây lockout

Đội vận hành rotate emergency password sau sự cố nhưng cập nhật sai secret vault dự phòng. Lần IdP outage tiếp theo không ai đăng nhập được. Hãy đề xuất quy trình dual-check và rehearsal đảm bảo credential cũ bị vô hiệu hóa nhưng đường khôi phục mới còn hoạt động.

### 29.10. Bài J — KPI closure

Dashboard có 100% emergency requests ở trạng thái `EXPIRED`, nhưng 8 tokens còn active và 3 direct grants vẫn cho admin. Vì sao không thể báo 100% thu hồi? Đề xuất KPI riêng cho **approved duration, actual exposure, session/token residual, target readback và remediation SLA**.

**Điểm cần ghi nhớ:** **Thời hạn khẩn cấp** là **một kiểm soát về quyền sử dụng thực tế**, không phải chỉ một timestamp trong ticket. Cần phân biệt **request approval, emergency business window, JIT/PAM lease, session, access token/credential và verification deadline**; giới hạn scope/action, quản lý gia hạn và chấm dứt sớm, bảo đảm đường khôi phục khi **IdP/SSO/PAM outage**, đồng thời thực thi đúng tại **RBAC/ABAC PEP, SCIM/app target và mọi access path**. Trong IAM **Joiner–Mover–Leaver**, quyền đã mất căn cứ phải được **thu hồi ngay theo policy**, không chờ expiry, và chỉ được xem là hoàn tất khi **actual effective access đã bị chặn**, có **readback, reconciliation và audit** chứng minh.

