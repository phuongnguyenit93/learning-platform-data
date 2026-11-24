# Admin authentication

## 1. Admin authentication là gì?

**Admin authentication (xác thực tài khoản quản trị)** là tập hợp cơ chế xác minh danh tính và trạng thái tin cậy của người hoặc workload có khả năng thực hiện thao tác quản trị trên hệ thống. Các thao tác này có thể tạo hoặc xóa tài khoản, cấp quyền, thay đổi chính sách bảo mật, đọc dữ liệu nhạy cảm, quản lý khóa, cấu hình hạ tầng hoặc vô hiệu hóa kiểm soát.

Tài khoản quản trị có tác động lớn hơn tài khoản người dùng thông thường. Nếu attacker chiếm được một tài khoản admin, họ có thể tạo thêm danh tính, thay đổi MFA, thu hồi log, tạo credential mới hoặc mở rộng quyền sang nhiều hệ thống. Vì vậy, xác thực admin cần assurance cao, thiết bị và phiên làm việc được kiểm soát, cùng audit đủ chi tiết để phát hiện và điều tra hành vi bất thường.

Ví dụ: một kỹ sư đăng nhập vào cloud console để thay đổi policy IAM. Hệ thống yêu cầu passkey hoặc security key chống phishing, kiểm tra thiết bị quản trị, tạo phiên đặc quyền có thời hạn và ghi lại danh tính, phương thức xác thực, nguồn truy cập, policy decision cùng các thay đổi sau đăng nhập.

Trong module SECURITY_AUTHENTICATION_FUNDAMENTALS, Admin authentication kết nối credential, MFA, passkey, federation, session và account lifecycle. Xác thực thành công chỉ xác minh principal đã chứng minh được quyền kiểm soát credential; mỗi thao tác quản trị vẫn phải qua authorization, giới hạn phạm vi và audit riêng.

## 2. Phân biệt admin authentication với admin authorization

Hai khái niệm này liên quan nhưng không thay thế nhau:

| Hoạt động | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Admin authentication** | Ai đang đăng nhập và bằng chứng xác thực có đủ mạnh không? | Admin đăng nhập bằng passkey trên thiết bị quản trị được quản lý. |
| **Admin authorization** | Admin được phép làm gì, trên hệ thống và phạm vi nào? | Role cho phép xem audit log nhưng không được thay đổi policy IAM. |
| **Privilege elevation** | Khi nào principal được nhận quyền cao hơn và trong bao lâu? | Admin yêu cầu quyền production trong 30 phút. |
| **Session management** | Phiên đặc quyền được tạo, bảo vệ, gia hạn và thu hồi ra sao? | Session có idle timeout ngắn và re-auth trước thao tác nhạy cảm. |
| **Audit** | Ai đã đăng nhập, thực hiện hành động gì và kết quả ra sao? | Ghi actor, target, thời điểm, approval và kết quả thay đổi quyền. |

Một tài khoản đã xác thực mạnh không mặc nhiên được quyền quản trị mọi tài nguyên. Hệ thống phải kiểm tra role, tenant, environment, resource, action và separation of duties tại thời điểm thực hiện.

## 3. Những loại danh tính quản trị

Không phải mọi danh tính có quyền cao đều là nhân viên đăng nhập bằng browser:

| Loại danh tính | Mục đích | Kiểm soát chính |
| --- | --- | --- |
| **Named human admin** | Nhân viên được cấp quyền quản trị theo vai trò. | Danh tính riêng, MFA chống phishing, thiết bị quản trị và audit theo cá nhân. |
| **Separate admin account** | Tài khoản quản trị tách khỏi tài khoản làm việc thường ngày. | Không dùng chung mailbox/chat; liên kết với một owner đã xác minh. |
| **Break-glass account** | Truy cập khẩn cấp khi IdP hoặc quy trình thông thường gặp sự cố. | Số lượng ít, bảo vệ ngoại tuyến, cảnh báo khi dùng và kiểm tra sau sự kiện. |
| **Temporary elevated identity** | Danh tính hoặc quyền được nâng tạm thời cho một nhiệm vụ. | Approval, scope hẹp, expiry và tự động thu hồi. |
| **Service/workload admin identity** | Workload tự động thực hiện tác vụ quản trị. | Workload identity, credential ngắn hạn, owner và policy riêng. |
| **Vendor/support admin** | Đối tác truy cập để hỗ trợ hệ thống. | Federation có kiểm soát, thời hạn hợp đồng, scope hẹp và giám sát phiên. |

Mỗi người cần có định danh cá nhân để audit không bị mơ hồ. Tài khoản dùng chung như `administrator` hoặc `root-team` làm mất khả năng xác định ai thực hiện hành động và khiến việc thu hồi quyền trở nên khó khăn. Nếu nền tảng bắt buộc có tài khoản built-in, cần quản lý việc sử dụng qua PAM, session recording và quy trình checkout có owner.

## 4. Threat model cho tài khoản quản trị

Attacker có thể nhắm tới:

- Password hoặc credential bị tái sử dụng từ một dịch vụ khác.
- Phishing proxy đánh cắp password và OTP theo thời gian thực.
- MFA fatigue để người dùng chấp thuận push ngoài ý muốn.
- Session cookie, refresh token hoặc thiết bị admin đã bị xâm nhập.
- Quy trình password reset, account recovery hoặc help desk yếu.
- OAuth consent hoặc ứng dụng quản trị được cấp quyền quá rộng.
- Máy trạm quản trị có extension độc hại, malware hoặc cấu hình không an toàn.
- Tài khoản nhà cung cấp, service account hoặc API key không còn owner.
- Insider misuse hoặc admin có quyền vượt quá nhiệm vụ.

Hậu quả có thể gồm tạo tài khoản persistence, thêm factor của attacker, cấp role mới, thay đổi trust policy, đọc/xuất dữ liệu, tắt logging hoặc phá hủy hệ thống.

Vì tác động cao, admin authentication cần phòng thủ theo nhiều lớp: credential mạnh, thiết bị tin cậy, session có giới hạn, privilege elevation có kiểm soát và giám sát hành vi sau đăng nhập.

## 5. Tách tài khoản admin khỏi tài khoản thường

Người quản trị nên dùng tài khoản riêng cho công việc đặc quyền. Tài khoản làm việc thường ngày dùng email, chat, tài liệu và web; tài khoản admin chỉ dùng trên các giao diện và thiết bị cần cho nhiệm vụ quản trị.

Lợi ích:

- Giảm khả năng phishing email hoặc duyệt web làm lộ credential đặc quyền.
- Tách session và cookie quản trị khỏi hoạt động thường ngày.
- Dễ áp dụng policy MFA, device posture và conditional access nghiêm ngặt hơn.
- Giúp audit phân biệt hành động quản trị với hoạt động người dùng.
- Giảm quyền của tài khoản được dùng thường xuyên.

Tài khoản admin không nên có mailbox hoặc quyền truy cập ứng dụng không cần thiết. Nếu phải nhận thông báo, sử dụng kênh thông báo được kiểm soát, không biến tài khoản đặc quyền thành tài khoản làm việc tổng hợp.

Không dùng cùng một tài khoản admin cho nhiều người. Không chia sẻ password hoặc security key giữa các admin. Mỗi principal phải gắn với một người hoặc workload owner cụ thể.

## 6. Phishing-resistant authentication cho admin

Tài khoản quản trị nên ưu tiên phương thức xác thực chống phishing:

- **FIDO2/WebAuthn security key:** credential được ràng buộc với RP ID/origin; phù hợp cho tài khoản đặc quyền và break-glass.
- **Passkey:** public-key credential có thể đồng bộ hoặc gắn với thiết bị; cần policy phù hợp với mức assurance, quản lý thiết bị và yêu cầu của tổ chức.
- **Certificate-based authentication:** có thể dùng trong môi trường quản trị được quản lý, với PKI, private key protection và lifecycle rõ ràng.

Password + SMS OTP hoặc TOTP có thể tăng bảo vệ so với password đơn, nhưng mã OTP có thể bị phishing/relay. Push notification cũng có nguy cơ MFA fatigue nếu người dùng có thể chấp thuận mà không kiểm tra ngữ cảnh.

Với admin, policy nên:

- Yêu cầu factor chống phishing cho thao tác quản trị quan trọng.
- Hiển thị rõ dịch vụ, thiết bị hoặc yêu cầu đang được xác thực.
- Dùng number matching hoặc transaction context nếu push vẫn được hỗ trợ.
- Không cho phép downgrade âm thầm sang password-only khi factor mạnh lỗi.
- Giới hạn phương thức dự phòng và kiểm tra việc dùng fallback.
- Yêu cầu re-authentication hoặc step-up trước thao tác có tác động lớn.

### 6.1. Nhiều security key và dự phòng

Admin nên đăng ký ít nhất một phương thức dự phòng được tổ chức phê duyệt, chẳng hạn security key thứ hai được lưu giữ an toàn. Việc thay thế factor phải yêu cầu xác minh mạnh và audit.

Không để help desk tự thêm factor mới chỉ dựa trên email hoặc thông tin cá nhân công khai. Việc thêm authenticator có thể trao cho attacker quyền truy cập lâu dài, vì vậy phải dùng identity proofing và approval phù hợp.

## 7. Thiết bị quản trị tin cậy

Credential mạnh vẫn có thể bị đánh cắp nếu thiết bị admin bị kiểm soát. Admin access nên giới hạn vào thiết bị có trạng thái bảo mật đáp ứng policy:

- Thiết bị do tổ chức quản lý và có inventory/owner.
- Hệ điều hành và browser được hỗ trợ, cập nhật bản vá.
- Disk encryption, screen lock và endpoint protection được bật.
- Không dùng tài khoản local admin thường trực nếu không cần.
- Extension, phần mềm và certificate được kiểm soát.
- Có thể dùng privileged access workstation (PAW) hoặc môi trường quản trị chuyên dụng.
- Thiết bị không ở trạng thái compromised hoặc có tín hiệu rủi ro cao.

Device posture là tín hiệu bổ sung, không phải bằng chứng danh tính độc lập. Không cho phép một thiết bị compliant bỏ qua authentication hoặc authorization.

Với thao tác quản trị production, có thể yêu cầu kết nối qua bastion hoặc privileged access workstation riêng. Bastion cần xác thực workload và user, ghi audit, giới hạn protocol và không trở thành điểm tin cậy không kiểm soát.

## 8. Federation và IdP dành cho admin

Tổ chức có thể dùng một IdP trung tâm để xác thực admin tới cloud, SaaS và hệ thống nội bộ. Điều này giúp quản lý MFA, lifecycle, device policy và thu hồi tập trung, nhưng cũng làm IdP trở thành trust anchor có giá trị cao.

Các yêu cầu:

- Chỉ chấp nhận issuer và federation metadata đã cấu hình.
- Kiểm tra audience, signature, thời hạn, nonce/state và protocol binding.
- Tách policy admin khỏi policy người dùng thông thường.
- Yêu cầu assurance level phù hợp với thao tác quản trị.
- Bảo vệ admin console và tài khoản quản trị của chính IdP.
- Kiểm soát thay đổi federation, signing key, redirect URI và trusted domain.
- Có phương án break-glass khi IdP không khả dụng.

Nếu attacker chiếm được quyền quản trị IdP, họ có thể phát hành hoặc chấp nhận danh tính cho nhiều ứng dụng downstream. Vì vậy, tài khoản quản trị IdP phải được bảo vệ nghiêm ngặt hơn hoặc ít nhất tương đương tài khoản quản trị hạ tầng quan trọng.

## 9. Step-up authentication trước hành động nhạy cảm

Một phiên admin có thể được xác thực mạnh lúc đăng nhập nhưng tồn tại lâu. Khi admin thực hiện hành động nhạy cảm, hệ thống nên yêu cầu xác minh lại hoặc step-up theo policy.

Ví dụ hành động cần step-up:

- Tạo hoặc xóa admin khác.
- Thay đổi role, group membership hoặc policy IAM.
- Thay đổi MFA, recovery method hoặc federation settings.
- Truy cập secret, signing key hoặc certificate private key.
- Tắt audit, thay đổi retention hoặc export log.
- Xóa dữ liệu production hoặc thay đổi cấu hình bảo mật.

Step-up phải ràng buộc với đúng session, user, action và context. Không nên chấp nhận một lần xác thực tăng cường chung để cho phép mọi hành động nhạy cảm vô thời hạn.

## 10. Privileged Access Management và Just-in-Time elevation

**Privileged Access Management (PAM)** quản lý việc cấp, sử dụng, giám sát và thu hồi quyền đặc quyền. **Just-in-Time (JIT) elevation** cấp quyền cao trong thời gian giới hạn khi có nhu cầu được xác minh.

Một quy trình JIT điển hình:

1. Admin đăng nhập bằng factor mạnh trên thiết bị được quản lý.
2. Admin yêu cầu quyền cụ thể cho resource, environment và action.
3. Hệ thống kiểm tra role cơ sở, ticket/change request và lý do.
4. Người phê duyệt độc lập chấp thuận nếu policy yêu cầu.
5. PAM cấp quyền có thời hạn và ghi nhận session.
6. Admin thực hiện công việc trong phạm vi được cấp.
7. Quyền tự hết hạn hoặc bị thu hồi khi nhiệm vụ kết thúc.
8. Hệ thống đối chiếu thay đổi và lưu audit evidence.

~~~mermaid
flowchart TD
    A["Admin đăng nhập bằng factor mạnh"] --> B["Yêu cầu quyền JIT"]
    B --> C["Kiểm tra device, role, scope và lý do"]
    C --> D{"Cần approval?"}
    D -->|Có| E["Approver độc lập xem xét"]
    E --> F{"Được duyệt?"}
    F -->|Không| G["Từ chối và audit"]
    F -->|Có| H["Cấp quyền tạm thời"]
    D -->|Không| H
    H --> I["Thực hiện thao tác có giám sát"]
    I --> J["Hết hạn hoặc revoke"]
    J --> K["Đối chiếu thay đổi và lưu evidence"]
~~~

JIT giảm standing privilege nhưng không tự đảm bảo an toàn. Cần giới hạn thời hạn, scope, resource, approval, session và khả năng gia hạn. Việc gia hạn phải được xem như một quyết định mới, có lý do và audit.

## 11. Quản lý phiên quản trị

Phiên admin có thể cho phép truy cập nhiều tài nguyên nhạy cảm. Vì vậy, cần kiểm soát vòng đời session:

- Session ID ngẫu nhiên, không suy ra từ username hoặc user ID.
- Cookie có thuộc tính Secure, HttpOnly và SameSite phù hợp.
- Xoay session ID sau login, MFA step-up và thay đổi mức quyền.
- Idle timeout và absolute lifetime ngắn hơn phiên người dùng thông thường theo risk policy.
- Re-authentication trước thao tác nhạy cảm hoặc sau thay đổi thiết bị/ngữ cảnh.
- Thu hồi session khi admin nghỉ việc, bị disable, factor bị mất hoặc có dấu hiệu compromise.
- Giới hạn số phiên quản trị đồng thời và hiển thị phiên đang hoạt động nếu nền tảng hỗ trợ.
- Không lưu session cookie hoặc bearer token trong log, URL hay ticket.

Logout trên browser không đủ nếu server không thu hồi session hoặc token. Với JWT access token tự chứa, cần biết token còn hiệu lực tới exp hay có cơ chế denylist/introspection/session version.

## 12. Break-glass account

Break-glass là tài khoản hoặc phương thức truy cập khẩn cấp khi IdP, MFA provider hoặc hệ thống quản trị thông thường không khả dụng. Đây là đường truy cập có giá trị cao và cần kiểm soát nghiêm.

Thiết kế:

- Chỉ duy trì số lượng tối thiểu và có owner rõ ràng.
- Không dùng cho công việc hàng ngày.
- Credential và security key được bảo vệ ngoại tuyến hoặc trong vault kiểm soát.
- Có ít nhất hai người chịu trách nhiệm theo quy trình dual control nếu phù hợp.
- Không phụ thuộc hoàn toàn vào chính IdP đang có thể gặp sự cố.
- Giới hạn quyền và tài nguyên ở mức cần thiết cho khôi phục.
- Phát cảnh báo tức thời khi đăng nhập hoặc sử dụng.
- Bắt buộc ghi lý do, incident/change reference và thời điểm.
- Sau khi dùng, rotate credential, rà soát session, xác nhận thay đổi và kiểm tra lại trạng thái tài khoản.

Không nên tạo quá nhiều break-glass account hoặc để chúng không được kiểm tra. Tài khoản không sử dụng lâu có thể có credential hết hạn, cấu hình MFA lỗi thời hoặc owner không còn làm việc.

## 13. Admin authentication cho workload và service account

Một số tác vụ quản trị được tự động hóa, chẳng hạn deployment controller thay đổi cấu hình hoặc backup service quản lý snapshot. Những workload này cũng là danh tính đặc quyền.

Kiểm soát:

- Cấp workload identity riêng cho từng service/job và môi trường.
- Tránh shared API key hoặc credential dùng chung nhiều workload.
- Ưu tiên credential ngắn hạn, certificate hoặc token được cấp tự động.
- Giới hạn audience, scope, resource và action.
- Lưu private key/secret trong KMS, HSM hoặc secret manager.
- Có owner, purpose, expiry, rotation và quy trình revoke.
- Audit cả lần lấy credential lẫn hành động quản trị được thực hiện.
- Không cho workload tự cấp quyền mới cho chính nó nếu không có policy/approval riêng.

Không áp dụng MFA tương tác của con người cho workload theo cách không phù hợp. Thay vào đó, dùng workload authentication mạnh và kiểm soát quyền máy theo vòng đời.

## 14. Monitoring và audit sự kiện admin authentication

Để phát hiện chiếm tài khoản quản trị, hệ thống cần ghi nhận các sự kiện từ lúc xác thực tới khi quyền được sử dụng:

| Sự kiện | Trường dữ liệu hữu ích |
| --- | --- |
| Admin login success/failure | Principal, tenant, IdP, factor, assurance, device, source, thời điểm và kết quả. |
| MFA challenge | Loại factor, challenge ID tham chiếu, approve/deny/timeout và số lần thử; không ghi OTP. |
| Passkey/security key enrollment | Actor, target account, thời điểm, thiết bị và approval reference. |
| Recovery/reset | Kênh, actor, target, lý do, proofing level và kết quả. |
| Privilege elevation | Requester, approver, role/scope, resource, ticket, thời hạn và expiry. |
| Session lifecycle | Session reference, create/refresh/revoke, idle/absolute expiry và nguyên nhân. |
| Federation/config change | Actor, issuer/client, signing key, redirect URI, policy và before/after reference. |
| Break-glass use | Account, người checkout, incident ID, thời điểm, hành động và post-use review. |
| Admin action | Actor, subject nếu có, action, target resource, tenant, result và correlation ID. |

Audit record phải cho phép trả lời: ai đã xác thực, bằng phương thức nào, từ thiết bị nào, nhận quyền gì, ai phê duyệt, thực hiện hành động nào và kết quả ra sao.

Không ghi password, OTP, recovery code, private key, session cookie, bearer token hoặc client secret. Dùng ID tham chiếu và metadata không nhạy cảm để liên kết các sự kiện.

## 15. Phát hiện hành vi bất thường

Một số tín hiệu cần được kết hợp:

- Đăng nhập admin từ thiết bị mới, không quản lý hoặc có posture không đạt.
- Đăng nhập từ ASN, quốc gia hoặc mạng không thường dùng.
- MFA prompt bị từ chối nhiều lần hoặc có push approval không mong muốn.
- Admin đăng nhập thành công sau chuỗi password failure hoặc credential stuffing.
- Factor, recovery method hoặc passkey mới được thêm ngay sau login.
- Privilege elevation ngoài giờ, không có change ticket hoặc approver bất thường.
- Break-glass account được sử dụng ngoài incident đã ghi nhận.
- Nhiều lần thay đổi IAM, federation, audit hoặc logging trong thời gian ngắn.
- Session admin tồn tại quá lâu hoặc hoạt động từ nhiều thiết bị không hợp lý.
- Workload credential được dùng từ môi trường hoặc resource ngoài phạm vi.

Không coi một tín hiệu như impossible travel hoặc IP lạ là bằng chứng chắc chắn của compromise. VPN, proxy, NAT, travel và thay đổi mạng có thể tạo false positive. Kết hợp device, factor, session, action, tenant và baseline trước khi quyết định khóa hoặc thu hồi.

## 16. Xử lý khi nghi ngờ admin account bị chiếm

Khi có bằng chứng hoặc tín hiệu rủi ro cao:

1. Xác minh incident và xác định principal, tenant, resource cùng thời gian bị ảnh hưởng.
2. Revoke session, refresh token và grant liên quan; đánh giá access token còn hiệu lực.
3. Tạm ngưng hoặc giới hạn tài khoản theo incident policy, đặc biệt với thao tác đặc quyền.
4. Xác minh lại factor, passkey, security key, recovery email/phone và phương thức federation.
5. Xóa authenticator, OAuth grant, API key, certificate hoặc session không nhận diện.
6. Kiểm tra role, group, policy, federation config và tài khoản persistence được tạo.
7. Kiểm tra audit log, export dữ liệu, secret access và thay đổi hệ thống trong cửa sổ sự cố.
8. Đổi credential từ thiết bị sạch và yêu cầu identity proofing/step-up nếu cần.
9. Khôi phục quyền theo nguyên tắc least privilege, có approval và expiry.
10. Theo dõi tăng cường và xác nhận attacker không còn session hoặc credential hợp lệ.

Không chỉ đổi password rồi mở lại quyền admin. Cần kiểm tra mọi đường persistence mà attacker có thể đã thiết lập.

## 17. Ví dụ policy admin authentication

Một policy minh họa:

~~~json
{
  "principalType": "human-admin",
  "authentication": {
    "requiredAssurance": "phishing-resistant",
    "allowedMethods": ["webauthn", "managed-certificate"],
    "fallbackRequiresApproval": true
  },
  "device": {
    "managed": true,
    "compliant": true,
    "adminWorkstation": true
  },
  "session": {
    "idleTimeoutMinutes": 15,
    "absoluteLifetimeMinutes": 60,
    "stepUpForSensitiveActions": true
  },
  "elevation": {
    "justInTime": true,
    "maxDurationMinutes": 30,
    "approvalRequired": true
  },
  "audit": {
    "recordAuthenticationEvents": true,
    "recordElevationAndAdminActions": true,
    "alertOnBreakGlass": true
  }
}
~~~

Đây là cấu hình minh họa, không phải giá trị mặc định cho mọi tổ chức. Thời hạn session, phương thức được phép, assurance và approval phải dựa trên risk assessment, khả năng nền tảng và yêu cầu vận hành.

## 18. Các lỗi triển khai thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Dùng tài khoản admin cho email và duyệt web hàng ngày | Tăng cơ hội phishing và lộ session đặc quyền. | Tách tài khoản thường và tài khoản quản trị. |
| Chỉ dùng password hoặc SMS OTP | Dễ bị phishing, stuffing hoặc SIM swap. | Ưu tiên passkey/security key chống phishing. |
| Chia sẻ tài khoản admin | Không xác định được actor và khó thu hồi riêng. | Named identity và audit theo cá nhân. |
| Standing privilege quá rộng | Tài khoản bị chiếm có quyền lớn ngay lập tức. | JIT elevation, scope hẹp và expiry. |
| Không kiểm tra device posture | Credential mạnh được dùng trên endpoint đã bị kiểm soát. | PAW/managed device và kiểm tra posture. |
| Step-up một lần cho mọi hành động | Một session bị chiếm có thể làm nhiều thao tác nhạy cảm. | Re-auth theo action, context và thời hạn. |
| Break-glass không được kiểm tra | Credential khẩn cấp có thể hỏng hoặc bị lộ lâu ngày. | Test định kỳ, alert, dual control và post-use rotation. |
| Help desk tự thêm factor | Social engineering có thể chiếm quyền lâu dài. | Identity proofing, approval và audit cho factor enrollment. |
| Bỏ qua service account đặc quyền | Workload có thể giữ quyền rộng không owner. | Workload identity riêng, scope hẹp và lifecycle. |
| Chỉ log login, không log elevation/action | Không dựng được chuỗi từ xác thực tới hành động. | Audit session, grant, approval và admin action. |
| Log token hoặc recovery secret | Audit store trở thành nơi lộ credential. | Redact secret, dùng reference và kiểm soát truy cập. |
| Khóa admin chỉ theo IP lạ | VPN/NAT tạo false positive và attacker có thể đổi nguồn. | Kết hợp device, factor, behavior và action risk. |

## 19. Checklist admin authentication

Trước khi đưa quyền quản trị vào production, hãy kiểm tra:

1. Mỗi admin có danh tính riêng và owner rõ ràng không?
2. Tài khoản admin có tách khỏi tài khoản làm việc thường ngày không?
3. Có yêu cầu phishing-resistant MFA/passkey/security key cho thao tác đặc quyền không?
4. Factor dự phòng có được đăng ký, bảo vệ và kiểm tra theo policy không?
5. Có ngăn help desk thêm factor chỉ dựa trên thông tin dễ giả mạo không?
6. Admin chỉ đăng nhập từ thiết bị quản trị được quản lý và đạt posture không?
7. Federation/IdP và tài khoản quản trị IdP có assurance tương ứng không?
8. Step-up có được yêu cầu trước thao tác nhạy cảm và ràng buộc với action/context không?
9. Quyền admin có được cấp JIT, scope hẹp, approval và expiry không?
10. Session có idle/absolute timeout, rotation, re-auth và revoke phù hợp không?
11. Break-glass có ít account, credential được bảo vệ, alert và post-use review không?
12. Workload admin identity có credential riêng, ngắn hạn, owner và rotation không?
13. Audit có ghi login, factor, elevation, approval, session, federation change và admin action không?
14. Monitoring có phát hiện thiết bị mới, MFA fatigue, factor enrollment và hành động bất thường không?
15. Incident response có thể revoke session/grant, rotate credential và tìm persistence không?
16. Có kiểm thử phishing, token/session theft, lost key, IdP outage, break-glass và false positive không?

**Kết luận:** Admin authentication cần assurance cao hơn đăng nhập thông thường vì một tài khoản quản trị bị chiếm có thể làm thay đổi toàn bộ trust boundary của hệ thống. Hãy dùng danh tính admin riêng, phương thức chống phishing, thiết bị quản trị tin cậy, step-up theo hành động và JIT privilege. Phiên, factor, workload identity và break-glass đều phải có lifecycle và audit. Chỉ xác thực mạnh là chưa đủ: authorization phải giới hạn đúng resource/action, còn monitoring phải nối được đăng nhập với quyền được cấp và hành động thực tế.
