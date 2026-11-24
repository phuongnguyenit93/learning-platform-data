# Joiner flow

## 1. Joiner flow là gì?

**Joiner flow** là quy trình tạo danh tính số, tài khoản và quyền truy cập ban đầu cho một người hoặc một thực thể mới tham gia tổ chức/dịch vụ. Trong môi trường doanh nghiệp, joiner thường là nhân viên mới, nhà thầu, thực tập sinh hoặc đối tác được cấp quyền. Trong một nền tảng số, joiner có thể là khách hàng mới hoàn tất đăng ký. Quy trình phải xác định đúng chủ thể, tạo account ổn định, cấp credential an toàn và chỉ bật các quyền cần thiết khi điều kiện đã được phê duyệt.

Joiner là giai đoạn đầu của **account lifecycle**. Nó thường nối tiếp các quy trình mover (thay đổi vai trò/đơn vị/quyền) và leaver (ngừng quan hệ, thu hồi quyền). Một tài khoản được tạo đúng nhưng không có nguồn dữ liệu đáng tin, không có owner hoặc được cấp quyền quá rộng vẫn là một rủi ro bảo mật.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, joiner flow kết nối identity proofing, login identifier, credential, MFA/passkey, SSO, session, authorization và account recovery. Mục tiêu là bảo đảm tài khoản được gắn với đúng principal, credential được thiết lập qua kênh tin cậy và quyền ban đầu phản ánh đúng quan hệ công việc hoặc mục đích sử dụng.

Sau bài học, người học có thể:

- Mô tả các bước từ yêu cầu tham gia đến tài khoản hoạt động.
- Xác định nguồn dữ liệu có thẩm quyền và cách đối chiếu chủ thể.
- Phân biệt identity record, account, login identifier, credential và entitlement.
- Thiết kế phê duyệt, role assignment và least privilege.
- Chọn provisioning tự động, SCIM, just-in-time hoặc thủ công theo bối cảnh.
- Bootstrap password, passkey và MFA an toàn cho người mới.
- Xử lý start date, duplicate identity, retry và provisioning failure.
- Ghi audit, bảo vệ dữ liệu và chuẩn bị các sự kiện mover/leaver.

## 2. Joiner nằm ở đâu trong account lifecycle?

Account lifecycle quản lý một principal từ lúc được tạo, hoạt động, thay đổi cho tới khi bị vô hiệu hóa hoặc xóa theo policy.

| Giai đoạn | Sự kiện điển hình | Kết quả cần có |
| --- | --- | --- |
| **Joiner** | Nhân sự/thành viên mới được chấp thuận | Identity record, account, credential và quyền ban đầu |
| **Mover** | Đổi phòng ban, vai trò, dự án hoặc hợp đồng | Điều chỉnh entitlement, nhóm và phạm vi truy cập |
| **Leaver** | Nghỉ việc, kết thúc hợp đồng hoặc rời dịch vụ | Disable account, thu hồi session/token và quyền |
| **Rehire / Rejoin** | Người đã rời quay lại | Khôi phục hoặc tạo quan hệ mới theo policy, kiểm tra identity correlation |
| **Suspension** | Tạm nghỉ, điều tra hoặc rủi ro bảo mật | Tạm khóa hoặc giới hạn truy cập, bảo toàn audit |
| **Recovery** | Mất credential hoặc cần lấy lại quyền kiểm soát | Xác minh chủ tài khoản và cấp lại credential an toàn |

Joiner không nên được xem là một thao tác INSERT vào bảng user. Nó là workflow nhiều bước có trạng thái, phụ thuộc dữ liệu nguồn, phê duyệt, provisioning, credential enrollment và thời điểm bắt đầu quan hệ.

### 2.1. Human identity và non-human identity

Joiner flow thường được mô tả cho con người, nhưng tổ chức cũng tạo service account, workload identity, bot hoặc thiết bị. Những thực thể này không có cùng cách proofing hay credential bootstrap với nhân viên.

- **Human identity:** gắn với một người; có thể dùng HR, sponsor, manager, identity proofing và MFA.
- **Contractor/partner identity:** có sponsor, tổ chức bên ngoài, hợp đồng và thời hạn; quyền cần giới hạn theo dự án.
- **Workload identity:** gắn với service hoặc workload; dùng certificate, workload federation hoặc secret được quản lý.
- **Device identity:** gắn với thiết bị được quản lý; cần enrollment và kiểm tra posture.

Không tạo service account bằng cách mượn email của một nhân viên rồi coi đó là danh tính máy. Mỗi loại principal cần owner, vòng đời, credential và policy riêng.

## 3. Nguồn dữ liệu và sự kiện khởi tạo

Joiner flow cần một sự kiện khởi tạo đáng tin cậy. Trong doanh nghiệp, nguồn thường là HR Information System (HRIS), hệ thống quản lý nhà thầu, hệ thống quản lý đối tác hoặc workflow tuyển dụng đã được phê duyệt. Với khách hàng, nguồn có thể là registration flow và bằng chứng xác minh theo mức rủi ro của dịch vụ.

Một bản ghi khởi tạo có thể chứa:

- Mã hồ sơ hoặc mã quan hệ do nguồn cấp.
- Loại quan hệ: employee, contractor, intern, partner hoặc customer.
- Họ tên và thuộc tính cần thiết.
- Đơn vị, manager/sponsor và vị trí công việc.
- Ngày bắt đầu, ngày kết thúc dự kiến và trạng thái quan hệ.
- Nhóm công việc hoặc job code dùng để xác định quyền ban đầu.
- Môi trường, tenant hoặc tổ chức liên quan.
- Mã yêu cầu và dấu vết phê duyệt.

Không phải mọi trường đều cần sao chép sang identity store. Hãy chọn các thuộc tính phục vụ định danh, authorization, liên hệ và vận hành; giữ nguồn authoritative cho những dữ liệu thay đổi thường xuyên nếu kiến trúc cho phép.

### 3.1. Nguồn có thẩm quyền theo từng thuộc tính

Một nguồn có thể có thẩm quyền với quan hệ công việc nhưng không phải mọi thông tin về con người.

| Thuộc tính/quyết định | Nguồn có thể có thẩm quyền | Giới hạn |
| --- | --- | --- |
| Quan hệ nhân viên, ngày bắt đầu, trạng thái làm việc | HRIS hoặc hệ thống nhân sự được chỉ định | Không tự chứng minh người đang kích hoạt tài khoản là nhân viên đó |
| Quan hệ nhà thầu và thời hạn | Hệ thống hợp đồng/vendor hoặc sponsor workflow | Cần kiểm tra sponsor và phạm vi hợp đồng |
| Vai trò công việc, đơn vị | HR/job architecture hoặc hệ thống quản lý tổ chức | Role công việc không tự động tương đương quyền kỹ thuật |
| Tài khoản đối tác | Partner registry và owner nội bộ | Cần tenant, hợp đồng và quyền được phê duyệt |
| Danh tính pháp lý | Nguồn proofing phù hợp với luật/mục đích | Không phải mọi joiner đều cần thu thập giấy tờ pháp lý |
| Email công việc | Hệ thống directory/mail đã cấp | Có mailbox không tự chứng minh toàn bộ quyền hoặc danh tính |

Không suy ra người dùng đã được proofing chỉ vì HRIS có một record. HRIS xác nhận quan hệ theo hệ thống nhân sự; quy trình activation vẫn cần ràng buộc người thực hiện với invitation hoặc account đúng người.

### 3.2. Xác định thời điểm hiệu lực

Một tài khoản có thể được chuẩn bị trước ngày bắt đầu nhưng chưa nên truy cập hệ thống nội bộ trước thời điểm được phép. Tách các trạng thái như pending, scheduled, active và suspended.

Nếu ngày bắt đầu bị lùi, hủy hoặc thay đổi, workflow cần cập nhật provisioning và credential activation. Không để invitation cũ tự động mở quyền khi quan hệ đã bị hủy.

## 4. Identity correlation và chống tạo trùng tài khoản

Trước khi tạo principal mới, hệ thống cần xác định người đó đã có identity record hay chưa. Duplicate account có thể dẫn tới quyền phân tán, dữ liệu trùng, audit khó truy vết hoặc một người có nhiều tài khoản với mức bảo vệ khác nhau.

Dùng một định danh nguồn ổn định trong namespace rõ ràng, ví dụ HR person ID trong tenant/organization. Internal subject ID do identity platform cấp sẽ là khóa tham chiếu ổn định trong các hệ thống sau đó.

Nguyên tắc:

- Dùng source system + source identifier để tương quan record, không chỉ dùng tên hoặc email.
- Giữ internal subject ID ổn định khi email, username hoặc đơn vị thay đổi.
- Kiểm tra trạng thái tài khoản cũ, rehire và lịch sử quan hệ.
- Không tự động gộp account chỉ vì cùng email hoặc số điện thoại.
- Khi có collision hoặc dữ liệu mâu thuẫn, đưa vào review có kiểm soát.
- Ghi lại quyết định match/merge và người phê duyệt.

### 4.1. Ví dụ về duplicate identity

Một nhân viên từng làm việc tại công ty với email a@example.test, rời công ty và quay lại sau hai năm. Hệ thống HR tạo một employment record mới nhưng person ID vẫn ổn định. Joiner flow cần xác định đây là cùng một identity principal theo policy, cập nhật quan hệ việc làm và xem xét quyền/credential cũ.

Nếu email đã được cấp lại cho người khác, email không thể dùng để gộp tài khoản. Nếu person ID bị thay đổi bởi hệ thống nguồn, cần quy trình mapping đã được xác minh thay vì fuzzy match theo tên và ngày sinh.

### 4.2. Không để client tự chọn principal

Trong invitation hoặc activation link, token nên tham chiếu một enrollment transaction phía server có thời hạn và ràng buộc với principal dự kiến. Không tin subject ID, employee ID hoặc tenant ID do browser gửi trong form rồi tạo tài khoản theo các giá trị đó.

## 5. Phê duyệt và xác định quyền ban đầu

Account có thể được tạo tự động, nhưng entitlement phải xuất phát từ policy đã phê duyệt. Một job title như “Finance Analyst” không nên tự động cấp mọi quyền trong hệ thống tài chính nếu chưa có role mapping và kiểm tra phạm vi.

Quy trình cần xác định:

1. Ai yêu cầu tạo account?
2. Ai xác nhận quan hệ và sponsor?
3. Ai phê duyệt quyền đặc biệt?
4. Role nào được gán theo job code hoặc nhóm công việc?
5. Quyền nào cần approval riêng?
6. Khi nào quyền có hiệu lực?
7. Ai là owner chịu trách nhiệm review?

### 5.1. Role bundle và least privilege

Có thể dùng role bundle theo chức năng để cấp tập quyền đã được review. Ví dụ:

- Employee baseline: directory, email và các ứng dụng cơ bản.
- Support agent: hệ thống ticket và dữ liệu khách hàng trong phạm vi được giao.
- Finance analyst: báo cáo tài chính cần thiết cho đơn vị.
- Contractor project access: workspace và repository của dự án trong thời hạn hợp đồng.

Role bundle cần được version hóa và review. Không gán role quản trị hoặc quyền truy cập dữ liệu nhạy cảm chỉ dựa trên job title.

### 5.2. RBAC kết hợp ABAC

RBAC giúp quản lý quyền theo vai trò; ABAC bổ sung điều kiện theo thuộc tính như tenant, department, location, contract status, device posture hoặc time window.

Ví dụ, một nhân viên hỗ trợ chỉ được truy cập hồ sơ thuộc nhóm khách hàng được giao, trong giờ làm việc và khi quan hệ nhân sự còn active. Việc có role support không đủ để bỏ qua các điều kiện object-level hoặc purpose.

### 5.3. Separation of duties

Với quyền đặc biệt, người yêu cầu, người phê duyệt và người thực thi có thể cần được tách biệt. Ví dụ cấp quyền production administrator hoặc truy cập dữ liệu payroll có thể cần approval của owner và security. Không để người mới tự phê duyệt quyền của chính mình qua form onboarding.

## 6. Provisioning: tạo tài khoản ở các hệ thống đích

Sau khi principal và quyền được phê duyệt, identity platform có thể provision account tới directory, email, SaaS, VPN, source control, HR tools hoặc ứng dụng nội bộ.

Các mô hình phổ biến:

| Mô hình | Cách hoạt động | Ưu điểm/giới hạn |
| --- | --- | --- |
| **Central provisioning** | Identity platform tạo và quản lý account ở hệ thống đích | Kiểm soát tập trung; cần tích hợp API/connector |
| **SCIM provisioning** | Dùng giao thức SCIM để tạo/cập nhật/disable user và group | Chuẩn hóa trao đổi identity; vẫn cần mapping và lifecycle logic |
| **Just-in-time (JIT)** | Ứng dụng tạo account khi user đăng nhập liên kết lần đầu | Giảm bước tạo trước; dễ phát sinh quyền sai nếu mapping lỏng |
| **Manual provisioning** | Admin tạo account theo ticket/quy trình | Phù hợp hệ thống cũ; dễ chậm và sai sót nếu thiếu audit |
| **Hybrid** | Tạo identity trung tâm trước, một số app JIT hoặc thủ công | Linh hoạt; cần một nguồn trạng thái và owner rõ |

Provisioning không phải authentication. SCIM tạo hoặc cập nhật user resource; SSO xác minh người dùng và phát hành kết quả đăng nhập. Một tài khoản được provision không có nghĩa người dùng đã đăng nhập hoặc credential đã được thiết lập.

### 6.1. SCIM và lifecycle

SCIM (System for Cross-domain Identity Management) thường được dùng để đồng bộ user và group giữa identity platform và ứng dụng đích. Các thao tác có thể gồm create, update, deactivate và group membership management.

Khi triển khai:
- Dùng externalId ổn định theo nguồn và mapping rõ với internal subject.
- Bảo vệ SCIM endpoint bằng credential riêng, TLS và quyền tối thiểu.
- Validate schema, tenant và uniqueness.
- Xử lý PATCH/PUT và semantics active theo đúng implementation.
- Không coi email là khóa duy nhất nếu hệ thống có thể thay đổi email.
- Ghi audit cho create, update, group change và deactivate.
- Có reconciliation job để phát hiện account drift.

SCIM token hoặc bearer credential có thể cấp quyền provisioning rất rộng. Bảo vệ chúng như credential đặc quyền, rotate và revoke khi connector bị compromise.

### 6.2. Just-in-time provisioning

Với JIT, account được tạo khi user lần đầu đăng nhập qua IdP. RP có thể lấy claims để tạo local profile. Cần kiểm tra issuer, audience, signature, subject, tenant và mapping trước khi tạo.

Không tự động cấp role nhạy cảm dựa trên claim do IdP không được tin cậy hoặc giá trị group không được quản lý. JIT nên dùng allowlist issuer/client, attribute mapping đã phê duyệt và default role tối thiểu. Nếu cần approval, account có thể ở trạng thái pending cho tới khi owner xác nhận.

## 7. Credential bootstrap cho người mới

Sau khi identity record được tạo, người dùng cần một cách an toàn để thiết lập credential đầu tiên. Đây là bước nhạy cảm vì kẻ tấn công có thể chiếm invitation hoặc activation channel.

Một số nguyên tắc:

- Không gửi password mặc định hoặc password dùng chung qua email/chat.
- Không dùng ngày sinh, employee ID hoặc thông tin dễ đoán làm password ban đầu.
- Dùng invitation/activation token ngẫu nhiên, entropy đủ cao, thời hạn ngắn và chỉ dùng một lần.
- Ràng buộc token với enrollment transaction, principal và mục đích.
- Không đưa token vào analytics, referrer hoặc log.
- Khi token bị dùng, hết hạn hoặc bị revoke, không cho tái sử dụng.
- Thông báo khi credential đầu tiên được đăng ký.
- Nếu người dùng không thể hoàn tất, dùng recovery workflow có xác minh riêng.

~~~mermaid
sequenceDiagram
    participant HR as Nguồn nhân sự
    participant ID as Identity Platform
    participant U as Người mới
    participant OP as Identity Provider
    HR->>ID: Joiner event đã phê duyệt
    ID->>ID: Tạo principal và enrollment transaction
    ID-->>U: Invitation qua kênh đã xác minh
    U->>ID: Mở invitation
    ID->>ID: Kiểm tra token, thời hạn và binding
    ID->>OP: Bắt đầu credential enrollment
    OP->>U: Hướng dẫn đăng ký passkey/MFA
    U->>OP: Hoàn tất enrollment
    OP->>ID: Credential enrollment result
    ID->>ID: Kích hoạt theo start date và policy
~~~

### 7.1. Invitation token

Invitation token là một credential tạm thời, không phải identifier công khai. Nên:
- Sinh bằng CSPRNG.
- Lưu hash/HMAC của token ở server nếu phù hợp.
- Chỉ hiển thị/gửi một lần qua kênh đã xác minh.
- Ràng buộc với principal và transaction.
- Có expiry ngắn theo thời gian onboarding.
- Tiêu thụ atomically khi activation thành công.
- Cho phép revoke khi invitation bị gửi nhầm hoặc nghi bị lộ.

Không cho phép một invitation token thay đổi principal ID hoặc email recipient tùy ý sau khi tạo. Nếu cần chuyển người nhận, hủy transaction cũ và tạo transaction mới sau khi kiểm tra.

### 7.2. Passkey và MFA enrollment

Nếu tổ chức dùng passkey, enrollment cần được gắn với đúng relying party/origin và account đang được bootstrap. Người dùng phải xác nhận hành động trên authenticator; server xác minh challenge, origin, RP ID hash, chữ ký và user verification theo policy.

Nếu bắt buộc MFA, không coi việc chỉ đăng ký một phương thức là đã hoàn thành MFA. Cần kiểm tra trạng thái enrollment và policy, đồng thời cung cấp phương án dự phòng an toàn. Recovery code nếu có phải hiển thị một lần, lưu theo dạng bảo vệ và giải thích cách cất giữ.

### 7.3. Không để email là yếu tố duy nhất cho mọi trường hợp

Email invitation có thể phù hợp cho một số onboarding ít rủi ro, nhưng với quyền đặc quyền hoặc dữ liệu nhạy cảm, cần kiểm tra người nhận qua một nguồn độc lập hoặc sponsor workflow. Nếu email mới được tạo cùng lúc trong onboarding, việc gửi activation link tới chính mailbox đó không phải bằng chứng độc lập về danh tính.

## 8. SSO và account activation

Tổ chức có thể dùng SSO để người mới đăng nhập qua IdP trung tâm. Joiner flow cần bảo đảm:

- Account ở IdP đã được tạo và active đúng thời điểm.
- Client/RP đã đăng ký và chỉ nhận issuer được tin cậy.
- Identifier liên kết bằng issuer + subject, không chỉ email.
- Claims cần thiết được mapping rõ và tối thiểu.
- Role/entitlement ở RP được cấp theo policy đã phê duyệt.
- Account pending không được JIT thành active chỉ vì user đã có token hợp lệ.
- Khi quan hệ bị hủy hoặc thay đổi, RP nhận lifecycle event hoặc có reconciliation.

Đăng nhập thành công chứng minh một credential/session được chấp nhận theo IdP; nó không tự chứng minh user có quyền vào mọi ứng dụng. RP vẫn cần authorization theo tenant, resource, role và trạng thái quan hệ.

## 9. Quyền theo thời điểm và loại quan hệ

Joiner flow cần quản lý ngày bắt đầu và thời hạn quan hệ. Ví dụ, contractor có thể được cấp account trước ngày dự án bắt đầu nhưng chỉ được kích hoạt khi hợp đồng có hiệu lực.

Một số trạng thái:

| Trạng thái | Ý nghĩa | Quyền |
| --- | --- | --- |
| **Requested** | Có yêu cầu tạo tài khoản | Chưa có quyền |
| **Pending approval** | Chờ manager/owner phê duyệt | Chưa có hoặc chỉ quyền onboarding hạn chế |
| **Provisioning** | Đang tạo account ở hệ thống đích | Chưa cấp quyền nhạy cảm cho tới khi bước bắt buộc hoàn tất |
| **Scheduled** | Đã chuẩn bị nhưng chưa tới ngày hiệu lực | Chưa được truy cập tài nguyên nội bộ |
| **Active** | Quan hệ và điều kiện kích hoạt hợp lệ | Quyền theo role/policy |
| **Suspended** | Tạm dừng do rủi ro hoặc thay đổi quan hệ | Quyền bị hạn chế hoặc thu hồi |
| **Failed / Rejected** | Quy trình lỗi hoặc bị từ chối | Không được kích hoạt; cleanup theo policy |

Không nên dùng một cờ active duy nhất cho cả HR relationship, identity principal, account tại từng app và credential. Các hệ thống có thể có trạng thái riêng; cần một state model và quy tắc đồng bộ rõ ràng.

## 10. Provisioning failure, retry và idempotency

Joiner flow có thể tạo account ở nhiều hệ thống. Một connector lỗi sau khi đã tạo email nhưng chưa tạo VPN có thể để lại trạng thái không nhất quán.

Thiết kế cần:
- Mỗi joiner request có correlation ID và idempotency key.
- Mỗi bước có trạng thái và kết quả riêng.
- Retry không tạo account trùng.
- Dùng externalId/source ID để tra cứu account đã tạo.
- Retry có backoff và giới hạn; lỗi vĩnh viễn cần chuyển manual review.
- Có reconciliation để so sánh trạng thái identity platform với hệ thống đích.
- Có compensation/rollback khi workflow bị hủy.
- Không xóa account đã hoạt động chỉ vì một retry lặp lại hoặc event đến sai thứ tự.

Ví dụ pseudocode:

~~~text
function processJoiner(event):
    verifySourceAndApproval(event)
    request = loadOrCreateJoinerRequest(event.idempotencyKey)

    principal = correlateOrCreatePrincipal(
        sourceSystem = event.source,
        sourceId = event.personId
    )

    ensureIdentityRecord(principal, event.attributes)
    ensureApprovedEntitlements(principal, event.approvals)

    for target in requiredProvisioningTargets:
        result = provisionIdempotently(
            target = target,
            externalId = principal.subjectId,
            desiredState = event.desiredState
        )
        recordStepResult(request, target, result)

    if allRequiredStepsSucceeded(request) and activationConditionsMet(event):
        activateAccount(principal)
    else:
        keepPendingAndRaiseOperationalTask(request)
~~~

Đây là pseudocode khái niệm. Thực tế cần xử lý event ordering, transaction boundary, concurrent event, API quota, partial failure và quyền của connector.

### 10.1. Event ordering

Một event joiner có thể tới sau event hủy tuyển dụng do queue chậm hoặc hệ thống nguồn gửi lại. Không xử lý chỉ theo thứ tự nhận. So sánh version/updatedAt hoặc sequence từ nguồn đáng tin, và kiểm tra trạng thái quan hệ hiện tại trước khi active.

Nếu event cũ nói active nhưng event mới hơn nói cancelled, event cũ không được hồi sinh tài khoản. Cần xử lý clock và version theo hợp đồng nguồn; không tự so timestamp client nếu nguồn không đáng tin.

### 10.2. Compensation và cleanup

Nếu một phần provisioning đã thành công rồi workflow bị hủy, có thể cần:
- Disable account đã tạo.
- Xóa group membership vừa cấp.
- Thu hồi credential hoặc invitation.
- Hủy token/session nếu account đã từng active.
- Giữ audit và record tối thiểu để điều tra.
- Tạo ticket nếu cleanup tự động thất bại.

Không xóa lịch sử hoặc audit để “rollback sạch”. Compensation phải bảo toàn khả năng truy vết.

## 11. Privacy và bảo vệ dữ liệu onboarding

Joiner flow thường xử lý dữ liệu nhân sự hoặc thông tin cá nhân. Cần giới hạn dữ liệu sao chép giữa HR, identity platform và ứng dụng đích.

- Chỉ đồng bộ thuộc tính cần cho authentication, authorization và vận hành.
- Không gửi toàn bộ hồ sơ HR tới mọi ứng dụng.
- Tách contact attribute khỏi identifier và authorization attribute.
- Mã hóa dữ liệu nhạy cảm khi truyền/lưu.
- Hạn chế người có quyền xem invitation, giấy tờ hoặc dữ liệu cá nhân.
- Không log password, activation token, MFA secret, recovery code hoặc session cookie.
- Đặt retention cho enrollment request, bằng chứng và audit.
- Xóa hoặc giảm dữ liệu tại hệ thống đích khi account bị hủy theo policy.
- Có thông báo quyền riêng tư và kênh yêu cầu sửa dữ liệu.

Không dùng ngày sinh, địa chỉ nhà hoặc thông tin gia đình làm thuộc tính authorization nếu không có mục đích rõ ràng. Một role thường nên dựa trên quan hệ công việc và approval đã được xác minh, không dựa trên thuộc tính cá nhân không liên quan.

## 12. Security controls và threat model

| Mối đe dọa | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| **Fake joiner event** | Attacker giả mạo yêu cầu tạo account | Xác thực nguồn, chữ ký/API credential, approval và audit |
| **Invitation theft** | Link activation bị lộ hoặc chuyển tiếp | Token entropy cao, TTL, one-time, binding và notification |
| **Wrong-person activation** | Người khác dùng invitation của nhân viên | Sponsor/identity correlation, kênh độc lập và proofing theo rủi ro |
| **Duplicate principal** | Nhiều account cho cùng một người | Source ID, internal subject và collision review |
| **Overprovisioning** | Job title tự động cấp quyền quá rộng | Role bundle, least privilege, approval và access review |
| **JIT privilege escalation** | Claims không tin cậy cấp role admin | Issuer/claim allowlist, mapping và backend authorization |
| **SCIM credential theft** | Token provisioning bị lộ | Secret manager, scope tối thiểu, rotation và revoke |
| **Start-date bypass** | Account active trước ngày hiệu lực | State machine và server-side activation gate |
| **Event replay/out of order** | Event cũ tạo lại account hoặc quyền | Idempotency, source version và state validation |
| **Partial provisioning** | Một số app có account, app khác thất bại | Workflow state, reconciliation và compensation |
| **Insider abuse** | Người duyệt tự cấp quyền cho mình hoặc người quen | Separation of duties, audit và dual approval |
| **Recovery takeover** | Kênh onboarding yếu trở thành recovery yếu | Re-proofing, MFA, notification và recovery policy |
| **Data overcollection** | Đồng bộ quá nhiều dữ liệu HR | Data minimization, field mapping và retention |
| **Stale account** | Hợp đồng bị hủy nhưng account vẫn active | Leaver event, expiry và reconciliation |

## 13. Ví dụ: joiner flow cho nhân viên mới

Một công ty tuyển một nhân viên mới vào nhóm hỗ trợ khách hàng. Ngày bắt đầu là 1 tháng 12. Người quản lý đã phê duyệt role Support Agent nhưng nhân viên chỉ được truy cập dữ liệu khách hàng sau khi hoàn tất onboarding và MFA.

Flow có thể:

1. HRIS gửi joiner event đã xác nhận với person ID, job code, manager và start date.
2. Identity platform kiểm tra nguồn, event version và trạng thái tuyển dụng.
3. Hệ thống tìm principal hiện có theo HR namespace; nếu không có thì tạo subject ID mới.
4. Manager xác nhận nhóm và role bundle; quyền nhạy cảm cần approval riêng.
5. Identity platform provision directory, email và các ứng dụng cơ bản qua SCIM/connector.
6. Account ở trạng thái scheduled tới ngày bắt đầu; chưa truy cập dữ liệu khách hàng.
7. Gửi invitation token tới kênh onboarding đã được xác minh.
8. Nhân viên kích hoạt, đăng ký passkey và phương thức MFA dự phòng theo policy.
9. IdP tạo session sau khi xác thực; ứng dụng chỉ nhận issuer/subject đã đăng ký.
10. Backend kiểm tra role, training/approval nếu có, trạng thái quan hệ và purpose trước khi mở dữ liệu khách hàng.
11. Audit ghi lại ai phê duyệt, account nào được tạo, credential enrollment event và thời điểm kích hoạt.
12. Khi role hoặc employment status thay đổi, mover/leaver workflow cập nhật quyền và session.

~~~mermaid
flowchart TD
    A[HRIS: Joiner đã phê duyệt] --> B[Validate nguồn, event và start date]
    B --> C[Correlate identity / kiểm tra duplicate]
    C --> D[Tạo hoặc cập nhật principal]
    D --> E[Manager/owner phê duyệt entitlement]
    E --> F[Provision directory và ứng dụng]
    F --> G{Các bước bắt buộc thành công?}
    G -- Không --> H[Pending, retry hoặc manual review]
    G -- Có --> I[Scheduled tới ngày hiệu lực]
    I --> J[Invitation và credential enrollment]
    J --> K[Passkey/MFA theo policy]
    K --> L[Activate account và session]
    L --> M[Authorization theo role, resource và purpose]
    M --> N[Audit và lifecycle monitoring]
~~~

Trong ví dụ này, account tồn tại trước ngày làm việc nhưng quyền truy cập dữ liệu nhạy cảm chỉ được cấp khi điều kiện về ngày hiệu lực, credential và approval đều đạt. Việc đăng nhập thành công không tự bỏ qua kiểm tra quyền nghiệp vụ.

## 14. Chỉ số vận hành và access review

Theo dõi joiner flow giúp phát hiện account bị bỏ quên, provisioning chậm và cấp quyền sai.

| Nhóm | Chỉ số | Ý nghĩa |
| --- | --- | --- |
| **Timeliness** | Thời gian từ approval đến account ready | Onboarding có đúng hạn không? |
| **Provisioning** | Tỷ lệ thành công theo target app | Connector hoặc mapping nào hay lỗi? |
| **Credential** | Tỷ lệ activation và MFA/passkey enrollment | Người mới có thiết lập bảo vệ tài khoản không? |
| **Quality** | Duplicate/collision và attribute mismatch | Identity correlation có chính xác không? |
| **Access** | Số entitlement mặc định, quyền đặc biệt và exception | Có cấp quá rộng không? |
| **Lifecycle** | Account active trước start date hoặc còn tồn tại sau cancellation | State transition có đúng không? |
| **Security** | Invitation replay, activation failure, SCIM token abuse | Có dấu hiệu lạm dụng không? |
| **Operations** | Retry, manual ticket, partial provisioning và reconciliation drift | Quy trình có ổn định không? |

Định kỳ xác nhận manager/owner vẫn chịu trách nhiệm với account và quyền đã cấp. Access review không thay thế sự kiện mover/leaver tự động; nó là lớp kiểm soát bổ sung để phát hiện dữ liệu nguồn sai hoặc integration bỏ sót.

## 15. Checklist review Joiner flow

| Câu hỏi | Dấu hiệu thiết kế tốt |
| --- | --- |
| Sự kiện joiner đến từ nguồn tin cậy? | Source authentication, schema và approval được xác minh |
| Có source ID ổn định? | Namespace rõ và mapping tới internal subject |
| Duplicate/rejoin được xử lý? | Không match chỉ bằng email/tên; collision có review |
| Thuộc tính được tối thiểu hóa? | Chỉ đồng bộ field cần thiết |
| Có start date và trạng thái? | Pending/scheduled/active được phân biệt |
| Role mapping có được phê duyệt? | Job code không tự cấp quyền rộng |
| Có least privilege? | Baseline role và quyền đặc biệt tách biệt |
| Provisioning có idempotent? | Retry không tạo account/group trùng |
| SCIM connector được bảo vệ? | TLS, secret riêng, scope tối thiểu và rotation |
| JIT có kiểm soát? | Issuer, subject, audience, tenant và claim mapping |
| Invitation có an toàn? | Token ngẫu nhiên, TTL, one-time và binding |
| Credential enrollment có tin cậy? | Passkey/MFA enrollment gắn với đúng principal |
| Account chỉ active đúng thời điểm? | Server-side activation gate |
| Partial failure có xử lý? | Retry, reconciliation và compensation |
| Event cũ có thể hồi sinh account? | Version/order và current state được kiểm tra |
| Có separation of duties? | Người yêu cầu không tự duyệt quyền đặc biệt |
| Có audit và privacy controls? | Không log secret; retention và access control rõ |
| Có test negative cases? | Fake event, duplicate, expired invite, replay và SCIM failure |

### Tình huống tự kiểm tra

**Tình huống 1:** HRIS có record của nhân viên mới. Có thể tự động cấp quyền administrator theo job title không?

**Trả lời:** Không. HRIS xác nhận quan hệ và thuộc tính công việc; quyền đặc biệt cần role mapping, least privilege và approval riêng.

**Tình huống 2:** Invitation link bị mở hai lần. Có nên tạo hai account không?

**Trả lời:** Không. Enrollment transaction phải dùng một lần và provisioning phải idempotent; lần lặp chỉ nhận trạng thái phù hợp hoặc được từ chối an toàn.

**Tình huống 3:** Email của người mới đã được xác minh. Có thể coi đó là bằng chứng duy nhất cho mọi loại tài khoản đặc quyền không?

**Trả lời:** Không. Quyền truy cập cao cần kiểm tra nguồn quan hệ và có thể cần proofing/kênh độc lập cùng step-up phù hợp.

**Tình huống 4:** Một event joiner cũ đến sau event hủy tuyển dụng mới hơn. Hệ thống có nên active account theo event vừa nhận không?

**Trả lời:** Không. Cần kiểm tra version/trạng thái hiện tại của nguồn; event cũ không được hồi sinh account đã bị hủy.

**Tình huống 5:** SCIM đã tạo user ở ứng dụng A nhưng lỗi ở ứng dụng B. Có nên đánh dấu toàn bộ onboarding hoàn tất không?

**Trả lời:** Không. Ghi trạng thái từng bước, retry hoặc chuyển manual review; chỉ active quyền cần thiết khi các điều kiện bắt buộc đạt.

**Tình huống 6:** Một người nghỉ việc rồi quay lại. Có nên tạo principal mới chỉ vì email đã thay đổi không?

**Trả lời:** Không mặc nhiên. Dùng identity correlation từ nguồn có thẩm quyền và policy rehire; internal subject ID ổn định nếu tổ chức xác định đó vẫn là cùng principal.

## 16. Ghi nhớ

**Joiner flow là quy trình tạo và kích hoạt danh tính số cùng quyền truy cập ban đầu cho một chủ thể mới.** Quy trình đáng tin bắt đầu từ sự kiện nguồn đã được xác thực, đối chiếu identity ổn định, phê duyệt entitlement, provisioning có kiểm soát và credential bootstrap an toàn. Account chỉ nên active khi quan hệ, ngày hiệu lực, credential và các điều kiện bắt buộc đều đạt.

Tách identity record, account, identifier, credential và entitlement; dùng least privilege; bảo vệ invitation, SCIM và JIT; xử lý retry/idempotency, event ordering và partial failure; ghi audit và tối thiểu hóa dữ liệu. Joiner là điểm bắt đầu của account lifecycle, vì vậy mọi quyết định ban đầu cần hỗ trợ thay đổi vai trò, thu hồi quyền và kết thúc quan hệ một cách có thể truy vết.
