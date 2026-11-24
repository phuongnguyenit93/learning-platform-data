# API authentication policy

## 1. API authentication policy là gì?

**API authentication policy** là tập quy tắc xác định bằng chứng danh tính nào một API chấp nhận, mức xác thực nào cần thiết và điều kiện nào phải được đáp ứng trước khi request được xử lý. Policy có thể khác nhau theo caller, loại API, dữ liệu, hành động, thiết bị, môi trường và rủi ro tại thời điểm request.

Một API công khai chỉ đọc nội dung có thể không yêu cầu đăng nhập. API xem hồ sơ khách hàng có thể yêu cầu access token của người dùng với scope phù hợp. API quản trị có thể yêu cầu passkey hoặc MFA chống phishing gần đây. API nội bộ giữa hai workload có thể yêu cầu workload identity hoặc mTLS. Các quyết định này cần được mô tả thành policy có thể kiểm tra và thực thi nhất quán.

Trong module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, API authentication policy kết nối credential, token, session, assurance, service identity, authorization và trust boundary. Policy tốt xác định rõ ai đang gọi, họ đại diện cho ai, bằng chứng có đủ mạnh và đủ mới không, token dành cho API nào, quyền có bao phủ resource/action hay không và điều gì xảy ra khi context thiếu hoặc không đáng tin.

Sau bài học, người học có thể:

- Phân biệt authentication policy với authorization policy.
- Mô hình hóa quyết định theo principal, client, tenant, resource, action và context.
- Chọn authentication method, assurance và freshness theo rủi ro.
- Xác định yêu cầu issuer, audience, token type, scope và claim.
- Áp dụng RBAC, ABAC và relationship-based authorization.
- Phân chia Policy Administration, Decision, Enforcement và Information Point.
- Thiết kế default-deny, least privilege và step-up.
- Quản lý policy version, cache, revocation và thay đổi quyền.
- Ghi audit có ích mà không làm lộ credential hoặc dữ liệu nhạy cảm.
- Kiểm thử policy với request hợp lệ, sai context, thiếu quyền và tình huống phân tán.

## 2. Authentication policy khác authorization policy

Hai loại policy thường phối hợp nhưng trả lời hai câu hỏi khác nhau.

- **Authentication policy:** bằng chứng nào được chấp nhận để xác minh caller hoặc user? Có cần MFA, passkey, certificate, reauthentication hay freshness giới hạn không?
- **Authorization policy:** principal đã xác minh được phép thực hiện hành động nào trên resource nào, trong tenant và context nào?

Ví dụ, một nhân viên hỗ trợ có thể đăng nhập thành công bằng passkey. Authentication policy kết luận principal đã được xác minh với assurance phù hợp. Authorization policy vẫn phải kiểm tra nhân viên có được giao case khách hàng đó, có quyền xem trường dữ liệu cần thiết và purpose có hợp lệ hay không.

| Tình huống | Authentication policy | Authorization policy |
| --- | --- | --- |
| Đọc hồ sơ khách hàng | Token từ issuer tin cậy, user session hợp lệ | Có quyền đọc đúng khách hàng/case |
| Xuất báo cáo tài chính | MFA chống phishing mới gần đây | Role export, tenant và phạm vi báo cáo được phép |
| Service gọi API inventory | Workload identity hoặc client certificate hợp lệ | Scope reserve và quyền trên stock resource |
| Xóa API key | Reauthentication hoặc step-up | Chỉ owner/admin được phép thu hồi key |
| Truy cập API public | Có thể không cần identity | Chỉ trả nội dung công khai và áp dụng quota |

Không dùng authentication thành công để thay thế kiểm tra quyền. Ngược lại, role hoặc scope do caller tự khai không thể thay bằng chứng xác thực.

## 3. Policy phải xác định principal và caller context

Một request có thể mang nhiều danh tính. Policy cần phân biệt chúng thay vì gộp thành một user ID.

Các thuộc tính thường gặp:

- **Principal/subject:** người dùng hoặc workload đã được xác minh.
- **Client:** ứng dụng OAuth hoặc integration gửi request.
- **Actor:** thành phần thực hiện hành động trực tiếp.
- **Tenant:** tổ chức hoặc phạm vi dữ liệu.
- **Issuer:** hệ thống phát hành token hoặc assertion.
- **Audience:** API/resource server dự kiến nhận token.
- **Authentication context:** phương thức, thời điểm, assurance và MFA.
- **Device/workload context:** thiết bị, namespace, service account hoặc posture.
- **Network context:** nguồn mạng, proxy, vị trí ước lượng hoặc risk signal.
- **Resource/action:** đối tượng và thao tác đang được yêu cầu.
- **Purpose:** mục đích nghiệp vụ được phép nếu domain yêu cầu.

Không tin giá trị tenant, role, device trust hoặc user ID chỉ vì nó xuất hiện trong JSON hoặc header. Thuộc tính phải đến từ token đã xác minh, registry nội bộ, policy information point hoặc kênh đã được xác thực.

### 3.1. Subject, actor và client

Một backend có thể gọi API thay mặt user. Khi đó:
- Subject là người dùng mà quyền được ủy quyền.
- Actor là service thực hiện request.
- Client là ứng dụng đã khởi tạo flow.
- Audience là resource server nhận token.

Policy có thể yêu cầu cả subject và actor đều được phép. Ví dụ, user được xem hồ sơ nhưng service gọi thay họ phải thuộc danh sách integration được tin cậy. Không tự thêm user ID vào header để giả lập delegation.

### 3.2. Tenant binding

Trong SaaS đa tenant, tenant là một ranh giới authorization quan trọng. Policy cần xác minh principal có membership trong tenant, resource thuộc tenant đó và client được phép hoạt động trong tenant tương ứng.

Không lấy tenant ID từ query string rồi tin ngay. Nếu API hỗ trợ tenant parameter, server phải đối chiếu với membership/organization context đã xác minh. Không để token của tenant A truy cập resource thuộc tenant B chỉ vì caller thay ID.

## 4. Xây dựng quyết định policy

Một quyết định API thường cần xét nhiều thuộc tính. Có thể mô tả logic khái niệm:

~~~text
allow_request =
    trusted_issuer
    AND valid_token_profile
    AND authenticated_principal
    AND trusted_client_or_actor
    AND correct_audience
    AND authentication_context_satisfies_policy
    AND tenant_membership_is_valid
    AND principal_is_authorized_for_resource
    AND action_is_allowed
    AND business_context_is_valid
    AND risk_policy_allows
~~~

Nếu một điều kiện bắt buộc không đạt hoặc không thể xác minh, policy phải có kết quả xác định: deny, challenge/step-up hoặc chuyển sang xử lý lỗi theo contract. Không mặc định cho phép vì policy service timeout hoặc claim bị thiếu.

### 4.1. Policy decision theo từng request

Không nên quyết định quyền chỉ một lần khi người dùng đăng nhập rồi dùng mãi cho mọi API. Quyền có thể thay đổi, session có thể bị revoke, resource có thể đổi owner và risk context có thể tăng.

Với mỗi request, API cần:
1. Xác minh credential/token/session.
2. Resolve principal và context.
3. Xác định resource/action cụ thể.
4. Đánh giá policy hiện hành.
5. Thực thi hoặc từ chối.
6. Ghi audit theo mức cần thiết.

Có thể cache một số quyết định để giảm latency, nhưng cache cần gắn với principal, resource, action, tenant, policy version và thời hạn phù hợp. Phần cache sẽ được bàn ở mục riêng.

### 4.2. Policy outcome

Không phải mọi request đều chỉ có allow hoặc deny. Một policy engine có thể trả:
- **Permit:** request được tiếp tục trong phạm vi xác định.
- **Deny:** request bị từ chối.
- **Challenge/Step-up:** cần bằng chứng mạnh hơn hoặc mới hơn.
- **Not applicable:** policy này không áp dụng; cần xử lý theo composition rule.
- **Indeterminate:** không thể đưa ra quyết định đáng tin do lỗi hoặc thiếu dữ liệu.

API phải định nghĩa cách xử lý từng outcome. Đặc biệt, indeterminate do lỗi dependency không nên biến thành permit.

## 5. Authentication requirements theo rủi ro

Không phải endpoint nào cũng cần cùng mức xác thực. Policy có thể phân loại theo tác động nếu request bị chiếm quyền.

| Nhóm API/action | Authentication requirement có thể cân nhắc |
| --- | --- |
| Nội dung public | Không yêu cầu user authentication; vẫn áp dụng abuse controls |
| Hồ sơ người dùng thông thường | Session/token hợp lệ, audience và scope phù hợp |
| Dữ liệu cá nhân nhạy cảm | Authentication mới hơn, assurance phù hợp và risk check |
| Xuất dữ liệu hàng loạt | Step-up, purpose, quota và có thể approval |
| Thay đổi email/recovery/MFA | Reauthentication mạnh và thông báo bảo mật |
| Thao tác quản trị | Phishing-resistant MFA, device/workload trust và session ngắn hơn |
| Service-to-service | Workload identity, mTLS hoặc client authentication phù hợp |

Đây là cách phân loại minh họa. Owner của API và dữ liệu phải xác định requirement theo threat model, luật, hợp đồng và tác động nghiệp vụ.

### 5.1. Assurance và authentication method

Policy không nên chỉ kiểm tra một cờ mơ hồ như authenticated=true. Cần mapping rõ phương thức và assurance:
- Password đơn lẻ.
- Password kết hợp TOTP hoặc push.
- Passkey/WebAuthn với user verification.
- Security key FIDO2 chống phishing.
- Client certificate/mTLS cho workload.
- Federation assertion từ issuer được tin cậy.

Không phải mọi MFA đều chống phishing. SMS/TOTP có thể bị relay; push có thể bị fatigue. Với hành động có tác động cao, policy nên ưu tiên phương thức có origin binding hoặc proof-of-possession phù hợp.

Nếu dùng ACR/AMR, cần hiểu semantics của issuer và mapping nội bộ. Không suy luận mọi giá trị AMR "mfa" đều tương đương cùng assurance. Chỉ tin claim từ issuer được cấu hình và có hợp đồng.

### 5.2. Freshness và reauthentication

Một session hợp lệ có thể chứa authentication event đã quá cũ cho hành động nhạy cảm. Policy có thể yêu cầu authentication time nằm trong freshness window và phương thức đạt assurance.

Cần phân biệt:
- Token issue time.
- User authentication time.
- Session creation time.
- Last activity.
- MFA completion time.
- Credential enrollment/change time.

Refresh token có thể tạo access token mới mà không có user reauthentication. Token mới không tự chứng minh người dùng vừa xác thực. Dùng claim/event phù hợp như auth_time hoặc server-side authentication context đã xác minh.

### 5.3. Step-up

Nếu context hiện tại không đạt, API có thể trả challenge hoặc trạng thái yêu cầu step-up. Sau khi user hoàn tất, server cần:
- Xác minh kết quả từ issuer.
- Ràng buộc với principal và session.
- Kiểm tra freshness, assurance và method.
- Ràng buộc với action/resource/transaction khi cần.
- Chạy lại authorization.
- Không tiết lộ dữ liệu trước khi quyết định cuối cùng là permit.

Step-up chỉ nâng chất lượng authentication context. Nó không cấp thêm quyền trên resource.

## 6. Token policy: issuer, audience, type và claims

Token là một phần của authentication context, nhưng token hợp lệ về chữ ký chưa đủ. Policy cần xác định token profile nào được chấp nhận.

| Thuộc tính | Câu hỏi policy |
| --- | --- |
| Issuer | Token đến từ authorization server nào? |
| Audience | Token được phát hành cho API/resource server nào? |
| Token type/profile | Access token, ID token, client assertion hay loại khác? |
| Subject | Token đại diện cho user hay service? |
| Client ID | Ứng dụng nào nhận token? |
| Scope/role | Token có quyền coarse-grained nào? |
| Expiry/nbf | Token đang trong thời hạn hiệu lực không? |
| Authentication context | Phương thức, assurance và auth time nào được khẳng định? |
| Tenant | Token/context có gắn đúng tổ chức không? |
| Confirmation/sender constraint | Token có bị ràng buộc với key/certificate của caller không? |

### 6.1. Issuer allowlist

Chỉ chấp nhận issuer đã được cấu hình. Không tự động tin issuer từ claim hoặc metadata do client gửi. Khi nhiều issuer cùng phục vụ một API, mapping subject phải giữ issuer context để tránh trộn hai principal có cùng sub.

### 6.2. Audience và token type

Audience phải xác định API hiện tại là consumer hợp lệ. Token dành cho reporting API không được chấp nhận ở payroll API chỉ vì cùng issuer ký. Resource server cũng phải phân biệt ID token với access token theo profile.

Không chấp nhận token có audience wildcard hoặc thiếu audience nếu profile yêu cầu audience cụ thể. Không tự suy đoán token type chỉ từ việc payload là JWT.

### 6.3. Scope không phải policy đầy đủ

Scope thường mô tả quyền ở mức API hoặc nhóm action. Nó không chứng minh principal có quan hệ với resource cụ thể. Một token có scope customer:read vẫn không được phép đọc mọi khách hàng nếu object-level policy không cho phép.

Scope cần được kết hợp với tenant, resource ownership, relationship, purpose và business state.

## 7. Authorization models: RBAC, ABAC và ReBAC

API policy thường dùng một hoặc nhiều mô hình authorization.

### 7.1. RBAC — Role-Based Access Control

RBAC cấp quyền thông qua role. Ví dụ:
- support-agent có thể đọc ticket được giao.
- finance-analyst có thể xem báo cáo trong đơn vị.
- security-admin có thể quản lý policy bảo mật.

Ưu điểm là dễ quản lý và review. Rủi ro là role phình to, cấp sai theo job title hoặc quyền quá rộng. Role phải có owner, scope, approval và review định kỳ.

### 7.2. ABAC — Attribute-Based Access Control

ABAC quyết định dựa trên thuộc tính của subject, resource, action và environment.

Ví dụ:
- Subject.department = support.
- Resource.tenant = tenant-A.
- Action = read.
- Environment.device_posture = managed.
- Request.purpose = assigned_case.

Policy có thể cho phép nếu tất cả điều kiện bắt buộc đạt. ABAC linh hoạt nhưng cần quản lý chất lượng thuộc tính, nguồn dữ liệu, freshness và cách xử lý missing value.

### 7.3. ReBAC — Relationship-Based Access Control

ReBAC dựa trên quan hệ giữa principal và resource. Ví dụ:
- User được assign vào support case.
- Manager quản lý nhân viên.
- User là owner của document.
- Service thuộc project có quyền đọc repository.

Relationship cần được quản lý bởi nguồn đáng tin và có lifecycle. Không suy ra quan hệ chỉ từ email hoặc tên hiển thị.

### 7.4. Kết hợp mô hình

Một policy có thể dùng role để xác định chức năng, ABAC để giới hạn tenant/device/time và ReBAC để kiểm tra quan hệ với object.

Ví dụ: user có role support-agent, thuộc tenant A, được assign vào case 123 và session đạt assurance. Chỉ khi các điều kiện đều đạt mới cho đọc hồ sơ khách hàng gắn với case đó.

## 8. Policy architecture: PAP, PDP, PEP và PIP

Một kiến trúc policy thường tách nơi quản lý quy tắc, nơi quyết định và nơi thực thi.

| Thành phần | Trách nhiệm |
| --- | --- |
| **PAP — Policy Administration Point** | Tạo, review, version và publish policy |
| **PDP — Policy Decision Point** | Đánh giá request/context và trả decision |
| **PEP — Policy Enforcement Point** | Chặn hoặc cho request đi tiếp theo decision |
| **PIP — Policy Information Point** | Cung cấp thuộc tính như membership, device posture, resource owner hoặc risk |
| **Policy store** | Lưu policy version và metadata |
| **Audit/decision log** | Ghi decision, policy version và reason code |

~~~mermaid
flowchart LR
    A[Policy author / owner] --> PAP[PAP: publish policy]
    PAP --> S[(Versioned policy store)]
    PEP[PEP: API / gateway] --> PDP[PDP: evaluate]
    PDP --> S
    PDP --> PIP[PIP: trusted attributes]
    PIP --> PDP
    PDP --> PEP
    PEP --> R[Allow / deny / step-up]
    PDP --> L[Decision audit]
~~~

### 8.1. PEP phải fail safely

PEP là nơi thực thi cuối cùng. Nếu PDP timeout hoặc không thể xác minh thuộc tính bắt buộc, PEP cần theo policy rõ ràng. Với dữ liệu nhạy cảm, default thường là deny hoặc yêu cầu retry/step-up an toàn. Không permit chỉ vì policy engine không phản hồi.

Có thể dùng cached decision trong thời gian ngắn nếu policy định nghĩa rõ điều kiện và stale tolerance. Không dùng cache cũ vô thời hạn để thay quyết định hiện tại.

### 8.2. Policy composition

Một request có thể chịu nhiều policy: organization baseline, API-specific rule, tenant policy, resource owner policy và emergency restriction. Cần quy định precedence và cách kết hợp. Ví dụ, explicit deny có thể thắng permit; nhưng phải định nghĩa rõ để tránh hai service diễn giải khác nhau.

Không phụ thuộc thứ tự evaluation ngẫu nhiên. Policy conflict phải được phát hiện khi publish hoặc kiểm thử.

## 9. Default-deny và least privilege

Default-deny nghĩa là request chỉ được phép khi có rule rõ ràng cho phép. Nếu không có policy, policy không khớp hoặc thuộc tính bắt buộc không xác minh được, request bị từ chối.

Least privilege giới hạn quyền theo:
- Principal cụ thể.
- Client/workload cụ thể.
- Audience/resource server.
- Scope/action.
- Resource/tenant.
- Thời gian và purpose.
- Authentication assurance khi cần.

Tránh:
- Wildcard scope cho mọi API.
- Role admin mặc định cho service.
- Tin mọi user cùng domain email.
- Cho phép resource ID bất kỳ chỉ vì token hợp lệ.
- Cho quyền tạm thời mà không có expiry.
- Dùng policy "allow all internal network".

### 9.1. Explicit deny và deny reason

Explicit deny hữu ích cho tình huống như account suspended, tenant disabled, resource restricted hoặc incident lock. Deny reason nên được giữ nội bộ với mã có cấu trúc; response bên ngoài không cần tiết lộ chi tiết nhạy cảm.

Không trả thông tin kiểu "user tồn tại nhưng đang suspended" cho caller chưa được xác thực nếu điều đó tạo enumeration.

## 10. Policy theo resource và action

Policy nên đánh giá resource/action cụ thể. Các action có mức tác động khác nhau:
- read metadata.
- read sensitive fields.
- create.
- update.
- delete.
- export/download.
- share/delegate.
- approve.
- administer.

Cùng một role không nhất thiết được phép thực hiện mọi action trên resource. Ví dụ support-agent có thể xem trạng thái đơn hàng nhưng không được export toàn bộ lịch sử thanh toán hoặc thay đổi chủ tài khoản.

### 10.1. Object-level authorization

Một lỗi phổ biến là API chỉ kiểm tra scope hoặc role ở cấp route rồi dùng ID do client gửi để lấy object. Attacker đổi ID có thể truy cập dữ liệu của người khác (BOLA/IDOR).

Backend phải:
1. Resolve principal đã xác minh.
2. Load resource theo tenant/partition an toàn.
3. Kiểm tra relationship/ownership.
4. Kiểm tra action.
5. Áp dụng field-level policy nếu cần.
6. Trả đúng dữ liệu được phép.

Không tải toàn bộ dữ liệu nhạy cảm rồi che ở frontend. Authorization cần xảy ra trước khi response chứa dữ liệu được gửi đi.

### 10.2. Field-level policy

Một user có thể được đọc tên và trạng thái nhưng không được xem số định danh, thông tin thanh toán hoặc hồ sơ sức khỏe. API nên chọn projection/field ở backend theo policy. Không dựa vào CSS, JavaScript hoặc hidden field để bảo vệ dữ liệu đã gửi tới browser.

## 11. Contextual và risk-based policy

API có thể đánh giá thêm context:
- Authentication freshness và assurance.
- Device managed/compliant.
- Workload identity và deployment environment.
- Source network hoặc anomaly signal.
- Thời điểm và hành vi request.
- Transaction amount hoặc data volume.
- Credential vừa được đổi/recover.
- Account/session risk state.

Risk signal không phải lúc nào cũng chắc chắn. Policy cần định nghĩa cách xử lý missing, stale hoặc conflicting signal. Không biến vị trí IP thành bằng chứng danh tính. Dùng signal như một thuộc tính bổ sung và cân nhắc privacy.

### 11.1. Step-up theo hành động

Ví dụ:
- GET profile thông thường: session hợp lệ và quyền read.
- GET payment details: authentication mới trong khoảng policy và assurance đủ.
- POST change recovery email: reauthentication mạnh, transaction binding và notification.
- POST bulk export: step-up, purpose, quota và approval bổ sung.

Sau step-up, chạy lại policy trên resource/action. Không tự động nâng role hoặc scope vĩnh viễn.

### 11.2. Risk-based không có nghĩa tùy tiện

Decision cần có reason code và policy version để có thể giải thích, audit và tái hiện. Không để một model hoặc risk score không kiểm soát tự cấp quyền quản trị. Đặt ngưỡng, owner, review, fallback và quy trình override được kiểm soát.

## 12. Policy cache, freshness và revocation

Policy decision caching giúp giảm latency nhưng có thể khiến quyền đã thu hồi vẫn còn hiệu lực.

Cache key nên bao gồm các yếu tố ảnh hưởng decision như:
- Principal/subject.
- Issuer/client.
- Tenant.
- Resource/action hoặc policy route.
- Relevant context.
- Policy version.
- Resource/relationship version nếu có.

TTL phải phù hợp rủi ro. Quyền quản trị, dữ liệu nhạy cảm và account disable có thể cần kiểm tra mới hơn hoặc invalidation event.

### 12.1. Cache invalidation

Khi role, membership, resource owner hoặc policy thay đổi:
- Phát event invalidation.
- Tăng version của subject/resource/policy.
- Giảm TTL cho quyết định nhạy cảm.
- Có thể kiểm tra trực tiếp trạng thái revoke ở mỗi request rủi ro cao.
- Theo dõi propagation delay giữa region.

Không giả định event bus luôn giao ngay. Cần có reconciliation hoặc maximum stale period.

### 12.2. Token claims có thể cũ

Một token đã phát hành có thể chứa role/scope snapshot. Nếu quyền bị thu hồi sau đó, API cần strategy: token lifetime ngắn, introspection, denylist, policy lookup hoặc revocation event. Quyết định chọn phụ thuộc latency và yêu cầu revoke.

Không dùng access token dài hạn làm kho quyền duy nhất cho hành động có tác động lớn.

## 13. API policy cho service-to-service

Service-to-service policy cần xác minh workload và giới hạn quyền theo nhiệm vụ.

Một request có thể yêu cầu:
- Workload identity từ issuer tin cậy.
- Audience đúng API.
- Scope hẹp.
- mTLS hoặc sender-constrained token.
- Environment và namespace đúng.
- Service owner còn active.
- Resource/action trong phạm vi workload.
- Không có delegation ngoài policy.

Ví dụ:
- order-worker được reserve stock, không được xóa inventory.
- reporting-job chỉ đọc dữ liệu tổng hợp.
- backup-agent ghi vào backup store nhưng không được xóa bản backup immutable.
- CI deployer chỉ cập nhật môi trường staging; production cần approval và identity riêng.

Không dùng network zone làm policy duy nhất. Workload nội bộ có thể bị compromise; identity và authorization vẫn cần thiết.

## 14. Policy cho delegated API và confused deputy

Khi service hành động thay user, policy cần giữ cả user subject và service actor. Một service token riêng không tự chứng minh quyền delegated.

Kiểm tra:
- User đã được xác thực và còn active.
- Client/service được phép thực hiện delegation.
- Delegation scope và audience phù hợp.
- User có quyền trên resource/action.
- Service có quyền kỹ thuật thực hiện thao tác.
- Context và transaction được ràng buộc.
- Audit ghi cả subject lẫn actor.

Confused deputy xảy ra khi service có quyền cao thực hiện request mà caller không đủ quyền. Tránh bằng cách không dùng quyền service để bỏ qua authorization của user và không tin user ID do caller tự khai.

## 15. Policy change, versioning và governance

Policy là mã điều khiển quyền truy cập. Một thay đổi sai có thể mở dữ liệu cho nhiều principal hoặc làm ngừng toàn bộ API.

Governance nên có:
- Owner cho từng policy/domain.
- Version và changelog.
- Review/approval trước publish.
- Test cases gắn với policy.
- Static validation và conflict detection.
- Rollout có kiểm soát.
- Rollback version.
- Audit người thay đổi và thời điểm.
- Access review định kỳ.
- Emergency deny/revoke path có kiểm soát.

Không chỉnh trực tiếp policy production mà không có traceability. Thay đổi policy cần được kiểm tra cả permit và deny cases.

### 15.1. Policy as code

Policy-as-code có thể dùng ngôn ngữ hoặc engine chuyên dụng để lưu policy trong version control, review như code và chạy test tự động. Ví dụ, policy engine có thể đánh giá input principal/resource/action/context rồi trả decision có cấu trúc.

Không để policy engine trở thành nơi chứa secret. Dữ liệu đầu vào phải được xác minh trước; policy chỉ nên quyết định trên context có nguồn gốc và integrity rõ ràng.

## 16. Audit, privacy và khả năng giải thích

Một decision log hữu ích nên trả lời:
- Ai yêu cầu?
- Client/service nào gửi?
- Resource/action nào?
- Tenant nào?
- Policy version nào?
- Decision là permit, deny hay challenge?
- Reason code nào?
- Authentication context nào được dùng?
- Thuộc tính nào đến từ nguồn nào?
- Correlation ID nào liên kết các service?

Không ghi password, token thô, cookie, private key, OTP hoặc dữ liệu nhạy cảm đầy đủ. Dùng principal reference, token ID/keyed reference và resource ID đã giảm nhạy cảm theo policy. Giới hạn quyền đọc log và đặt retention.

Người dùng có thể cần thông báo rằng hành động bị yêu cầu step-up hoặc bị từ chối. Thông báo bên ngoài cần đủ hướng dẫn nhưng không tiết lộ policy nội bộ, trạng thái tài khoản người khác hoặc tín hiệu phát hiện fraud.

## 17. Threat model và lỗi policy thường gặp

| Mối đe dọa/lỗi | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| **Authentication bypass** | Route quên middleware hoặc endpoint phụ không áp policy | Route inventory, default-deny và negative tests |
| **Overbroad scope** | Token có quyền rộng hơn nhiệm vụ | Scope nhỏ, audience riêng và least privilege |
| **BOLA/IDOR** | Principal đổi resource ID | Object-level authorization ở backend |
| **Tenant confusion** | Client tự đổi tenant context | Membership và resource tenant binding |
| **Role spoofing** | Header/claim không tin cậy được coi là role | Verified issuer, strip external headers và trusted attributes |
| **Stale authorization** | Cache/token giữ quyền đã thu hồi | TTL, invalidation, version và revoke strategy |
| **Weak MFA policy** | Mọi AMR=mfa được coi như assurance giống nhau | Issuer mapping, phishing-resistant requirement và review |
| **Step-up bypass** | API trả dữ liệu trước challenge hoặc dùng grant sai resource | Backend gate và transaction binding |
| **PDP outage fail-open** | Policy engine lỗi nhưng PEP cho phép | Default-deny hoặc fallback có giới hạn |
| **Policy conflict** | Rule permit/deny không có precedence rõ | Composition semantics và conflict test |
| **Confused deputy** | Service quyền rộng hành động thay user | Subject/actor binding và delegated authorization |
| **Policy cache leak** | Cache key bỏ tenant hoặc resource | Cache key đầy đủ và partitioning |
| **Claim injection** | Caller tự gửi role/tenant/device claim | Chỉ dùng nguồn đã xác minh |
| **Insider policy abuse** | Admin sửa policy để cấp quyền trái phép | Separation of duties, approval và audit |
| **Information disclosure** | Error nói rõ account/resource tồn tại | Response normalization và reason code nội bộ |
| **Risk signal manipulation** | Caller giả device/network context | Trusted PIP, freshness và integrity |

## 18. Ví dụ: policy cho API truy cập dữ liệu khách hàng

Một ứng dụng hỗ trợ khách hàng gọi API đọc hồ sơ. Policy yêu cầu:
- User token từ issuer nội bộ.
- Audience là customer API.
- Authentication gần đây và MFA phù hợp khi đọc trường nhạy cảm.
- Client là support portal đã đăng ký.
- User có role support-agent.
- User được assign vào case đang hoạt động.
- Customer record thuộc tenant của case.
- Purpose là xử lý case.
- Chỉ trả field cần thiết.

~~~mermaid
flowchart TD
    A[API request] --> B[Verify token profile]
    B --> C{Issuer, audience, expiry OK?}
    C -- No --> X[Deny]
    C -- Yes --> D[Resolve subject, client, tenant]
    D --> E[Check role and case assignment]
    E --> F{Resource and purpose allowed?}
    F -- No --> X
    F -- Yes --> G{Sensitive fields?}
    G -- No --> H[Return allowed projection]
    G -- Yes --> I{Fresh auth and assurance?}
    I -- No --> J[Step-up required]
    I -- Yes --> H
    J --> K[Verify step-up context]
    K --> L{Same principal and transaction?}
    L -- No --> X
    L -- Yes --> H
~~~

Nếu user vừa hoàn tất MFA nhưng không được assign vào case, policy vẫn deny. Nếu user có case assignment nhưng authentication quá cũ để đọc trường nhạy cảm, policy yêu cầu step-up. Sau step-up, API chạy lại authorization và chỉ trả projection được phép.

## 19. Kiểm thử API authentication policy

| Test case | Kết quả mong đợi |
| --- | --- |
| Token issuer đúng, audience đúng, scope đủ và resource được phép | Permit |
| Token chữ ký đúng nhưng issuer không được tin | Deny |
| Token audience dành cho API khác | Deny |
| ID token gửi tới resource API | Deny theo profile |
| Token hết hạn hoặc nbf chưa tới | Deny |
| Token hợp lệ nhưng thiếu scope | Deny |
| Scope đủ nhưng resource thuộc tenant khác | Deny |
| Role đúng nhưng không có relationship với object | Deny |
| User có quyền nhưng auth freshness quá cũ | Step-up |
| MFA claim từ issuer không được tin | Không nâng assurance |
| Step-up đúng principal nhưng sai transaction/resource | Deny |
| Account bị suspended sau khi token phát hành | Deny theo revocation policy |
| PDP timeout | Fail-safe theo policy; không permit mặc định |
| PIP trả thuộc tính stale/unknown | Deny hoặc challenge theo rule |
| Policy cache cũ sau revoke | Invalidation hoặc TTL ngăn quyền cũ kéo dài quá mức |
| Hai policy xung đột | Kết quả theo precedence đã định nghĩa |
| Client gửi X-Role/X-Tenant giả | Bị strip/ignore |
| Service token gọi API ngoài audience | Deny |
| Delegated request thiếu actor context | Deny |
| User được phép nhưng service actor không được phép | Deny |
| Resource ID thay đổi sau step-up | Transaction binding ngăn reuse |
| Policy version rollout lỗi | Rollback và audit |
| Error response | Không lộ account/resource/policy secret |
| Audit event | Có subject, actor, action, decision và policy version; không có token thô |

### 19.1. Test matrix theo chiều policy

Ngoài test từng điều kiện, cần kiểm tra kết hợp thuộc tính:
- Principal hợp lệ + tenant đúng + resource đúng.
- Principal hợp lệ + tenant sai.
- Role hợp lệ + relationship thiếu.
- Scope đủ + audience sai.
- Assurance đủ + freshness hết hạn.
- Freshness đủ + assurance thấp.
- User hợp lệ + client không được phép.
- Workload hợp lệ + environment sai.
- PDP thành công + PIP stale.
- Permit cache + policy mới explicit deny.

Policy test nên có cả positive và negative cases. Đừng chỉ kiểm tra một happy path.

## 20. Checklist review policy

| Câu hỏi | Dấu hiệu thiết kế tốt |
| --- | --- |
| Authentication và authorization được tách? | Bằng chứng identity khác với quyết định quyền |
| Principal/client/actor có rõ? | Delegation không bị nhập nhằng |
| Tenant/resource/action được ràng buộc? | Không tin ID do caller tự khai |
| Issuer/audience/token type có allowlist? | Token dành đúng resource server |
| Assurance/freshness có yêu cầu theo rủi ro? | Endpoint nhạy cảm có policy riêng |
| MFA method được mapping đúng? | Không coi mọi MFA là tương đương |
| RBAC/ABAC/ReBAC có owner? | Role, attributes và relationships có nguồn tin cậy |
| PDP/PEP/PIP/PAP có trách nhiệm rõ? | Decision và enforcement không bị bỏ trống |
| Default-deny được áp dụng? | Missing/unknown không tự thành permit |
| Object/field-level authorization có? | Backend kiểm tra trước khi trả dữ liệu |
| Step-up có transaction binding? | Cùng principal, resource, action và expiry |
| Cache có version và invalidation? | Revoke/policy change lan truyền theo SLA |
| PDP/PIP outage có fallback? | Fail-safe và có giới hạn stale context |
| Policy change được review? | Version, approval, test và rollback |
| Audit đủ để điều tra? | Decision, reason, actor và policy version |
| Privacy được bảo vệ? | Không log token/secret hoặc dữ liệu dư thừa |
| Có negative/combinatorial tests? | Wrong tenant, audience, relationship, stale context và outage |

### Tình huống tự kiểm tra

**Tình huống 1:** Người dùng có token hợp lệ và scope customer:read. Có thể đọc mọi hồ sơ khách hàng không?

**Trả lời:** Không. API phải kiểm tra tenant, relationship, ownership/case assignment và field-level policy cho resource cụ thể.

**Tình huống 2:** API yêu cầu MFA. Mọi giá trị AMR chứa mfa có thể được coi là chống phishing không?

**Trả lời:** Không. Cần hiểu semantics của issuer và phương thức thực tế. TOTP hoặc SMS vẫn có thể bị phishing/relay; policy nhạy cảm có thể yêu cầu passkey/security key phù hợp.

**Tình huống 3:** PDP timeout. Có nên cho request tiếp tục vì user đã đăng nhập thành công?

**Trả lời:** Không mặc định. Authentication không thay authorization. PEP phải dùng fallback đã định nghĩa, thường deny hoặc retry với dữ liệu nhạy cảm.

**Tình huống 4:** User vừa step-up để xem hồ sơ A, sau đó đổi resource ID sang hồ sơ B. Có được dùng lại grant không?

**Trả lời:** Không nếu grant ràng buộc resource/transaction. Backend cần kiểm tra lại authorization cho B.

**Tình huống 5:** Policy cache cho phép truy cập, nhưng manager vừa thu hồi role. Có thể dùng cache cũ vô thời hạn không?

**Trả lời:** Không. Cần TTL, invalidation/version và maximum stale period phù hợp rủi ro.

**Tình huống 6:** Service có quyền đọc mọi hồ sơ. User gọi service yêu cầu đọc hồ sơ người khác. Service có thể dùng quyền riêng của mình để cho phép không?

**Trả lời:** Không. Cần kiểm tra quyền delegated của user và service actor; tránh confused deputy.

**Tình huống 7:** Client gửi tenant ID hợp lệ trong request nhưng principal không có membership. Policy có permit không?

**Trả lời:** Không. Tenant phải được xác minh qua membership/issuer context và resource binding, không chỉ vì ID tồn tại.

## 21. Ghi nhớ

**API authentication policy quy định bằng chứng danh tính và context cần có trước khi request được xử lý; authorization policy quyết định principal được làm gì trên resource cụ thể.** Một policy đầy đủ xét principal, client/actor, issuer, audience, assurance, freshness, tenant, resource, action, purpose và risk context.

Dùng RBAC/ABAC/ReBAC phù hợp, phân chia PAP/PDP/PEP/PIP rõ ràng, áp dụng default-deny và least privilege. Gateway có thể xác minh token và route-level scope nhưng backend vẫn phải kiểm tra object/field-level authorization. Step-up chỉ nâng authentication context, không cấp quyền. Quản lý policy version, cache invalidation, revocation, audit và test kết hợp để quyền truy cập nhất quán ngay cả khi hệ thống phân tán hoặc dependency gặp lỗi.
