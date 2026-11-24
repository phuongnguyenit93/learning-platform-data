# Authentication context cho authorization — Dùng ngữ cảnh xác thực trong quyết định cấp quyền

> **Chương:** Authorization boundary  
> **Chủ đề:** Authentication context cho authorization  
> **Phạm vi:** Bài học thuộc module SECURITY_AUTHENTICATION_FUNDAMENTALS, tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này giải thích cách chuyển kết quả xác thực đã được kiểm chứng thành ngữ cảnh đáng tin cậy cho quyết định authorization, gồm thời điểm và phương thức xác thực, mức assurance, trạng thái phiên, thiết bị, môi trường, tenant và hành động được yêu cầu.

## 1. Authentication context cho authorization là gì?

**Authentication context** là tập thuộc tính mô tả một lần xác thực và trạng thái xác thực hiện tại của principal. Nó có thể bao gồm issuer, subject, thời điểm xác thực, phương thức đã dùng, mức assurance theo hợp đồng, kết quả user verification, tuổi của phiên và một số tín hiệu môi trường đã được xác minh.

**Authorization** quyết định principal có được phép thực hiện một hành động trên một tài nguyên cụ thể trong bối cảnh hiện tại hay không. Policy có thể cần biết người dùng vừa xác thực bằng passkey, lần xác thực gần nhất đã cách đây bao lâu, session có bị thu hồi không, thiết bị có đáp ứng yêu cầu quản lý không và request đang nhắm tới tenant/resource nào.

Ví dụ, Mai đã đăng nhập vào hệ thống quản trị bằng passkey. Cô có quyền quản lý thành viên, nhưng thao tác cấp quyền Owner cho một người khác có rủi ro cao. Policy có thể yêu cầu lần xác thực gần nhất đủ mới, phương thức đáp ứng mức chống phishing đã được tổ chức chấp thuận và thiết bị đáp ứng posture policy. Nếu ngữ cảnh hiện tại không đủ, hệ thống yêu cầu step-up trước khi đánh giá lại quyền.

Authentication context giúp policy trả lời câu hỏi **“Trong điều kiện xác thực nào principal đang yêu cầu hành động?”**. Nó không tự trả lời câu hỏi **“Principal có quyền thực hiện hành động này không?”**.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt authentication context với identity, session, authorization và risk score.
2. Nhận diện các thuộc tính xác thực có thể được dùng trong policy.
3. Hiểu semantics và giới hạn của auth_time, acr, amr và User Verification.
4. Gắn context đã xác minh với principal và session phía server.
5. Thiết kế policy dựa trên action, resource, tenant, freshness và assurance.
6. Phân biệt thuộc tính xác thực với tín hiệu thiết bị, mạng và hành vi.
7. Dùng PDP/PEP và ABAC để đánh giá context có kiểm soát.
8. Ngăn spoofing, stale context, downgrade, confused deputy và rò rỉ giữa tenant.
9. Thiết kế step-up, audit và kiểm thử cho authorization phụ thuộc context.

## 2. Authentication, authentication context và authorization

Ba bước liên quan nhưng có mục tiêu khác nhau:

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Authentication** | Chủ thể đã chứng minh quyền kiểm soát credential hợp lệ chưa? | Assertion passkey được xác minh thành công. |
| **Authentication context** | Lần xác thực được thực hiện khi nào, bằng phương thức và assurance nào? | auth_time, acr/amr theo semantics của issuer, UV flag đã xác minh. |
| **Authorization** | Principal có được phép làm hành động này trên tài nguyên này không? | Mai có thể cấp role Editor trong tenant A nhưng không thể cấp Owner trong tenant B. |

Một authentication thành công chỉ xác lập principal và kết quả xác thực theo policy. Authorization còn cần kiểm tra quyền, phạm vi, quan hệ tài nguyên, trạng thái account, tenant, điều kiện nghiệp vụ và các thuộc tính môi trường.

Ví dụ, người dùng có session hợp lệ không đồng nghĩa được đọc mọi hồ sơ. Người dùng có MFA cũng không tự động trở thành administrator. Role trong token hoặc context không nên được tin nếu issuer, audience, nguồn phát hành và quy tắc mapping chưa được xác minh.

## 3. Những thành phần có thể tạo nên authentication context

Tùy ứng dụng và giao thức, context có thể gồm:

| Thuộc tính | Ý nghĩa | Nguồn cần tin cậy |
| --- | --- | --- |
| Principal | Account nội bộ đã được xác định | Authentication service hoặc federation mapping đã xác minh |
| Issuer | Hệ thống phát hành assertion/token | Cấu hình issuer tin cậy và kiểm tra chữ ký |
| Subject | Định danh người dùng trong issuer | Claim đã xác minh; mapping theo issuer + subject |
| Authentication time | Thời điểm người dùng thực sự được xác thực | Claim/protocol đã xác minh hoặc event nội bộ |
| Authentication method | Phương thức hoặc nhóm phương thức đã dùng | Authenticator/verifier result và semantics đã thỏa thuận |
| Authentication context class | Lớp/ngữ cảnh xác thực do issuer định nghĩa | ACR contract và issuer configuration |
| User verification | Authenticator đã thực hiện UV theo giao thức hay chưa | WebAuthn authenticator data đã xác minh |
| Session state | Phiên còn active, revoked hay expired | Session store có thẩm quyền |
| Session age | Thời gian từ lần xác thực hoặc hoạt động gần nhất | Server timestamp và session policy |
| Device posture | Trạng thái thiết bị do nguồn quản lý báo cáo | MDM/attestation connector đã xác thực, có freshness |
| Network context | Thuộc tính mạng và risk signal | Hạ tầng ingress/proxy tin cậy |
| Request context | Action, resource, tenant và transaction | API/backend đã xác định và kiểm tra |

Không phải ứng dụng nào cũng cần tất cả thuộc tính. Thu thập và truyền càng nhiều context càng tăng độ phức tạp, rủi ro riêng tư và khả năng policy vô tình phụ thuộc vào tín hiệu không đáng tin.

## 4. Authentication context không phải risk score

Authentication context chứa facts về lần xác thực hoặc trạng thái liên quan đã được xác minh. Risk score là kết quả suy luận từ một hoặc nhiều tín hiệu.

Ví dụ:
- auth_time là thời điểm xác thực đã được xác minh;
- UV flag là kết quả từ authenticator data đã xác minh;
- device posture là trạng thái do MDM báo cáo;
- “risk = high” là kết quả của risk engine dựa trên nhiều dữ liệu.

Không ghi một risk score như thể đó là một authentication factor. Không nâng assurance chỉ vì IP quen thuộc hoặc browser fingerprint giống lần trước. Risk engine có thể yêu cầu thêm bằng chứng, hạn chế hành động hoặc chuyển review; nó không thể biến một chữ ký sai thành hợp lệ.

Tách nguồn facts khỏi kết quả suy luận giúp policy có thể giải thích được vì sao quyết định được đưa ra và cho phép thay đổi risk model mà không làm thay đổi lịch sử xác thực.

## 5. OIDC claims: auth_time, acr và amr

OpenID Connect có các claim hữu ích cho authentication context:

- **auth_time:** thời điểm End-User được xác thực. Đây không phải thời điểm ID Token được phát hành và cũng không nhất thiết là thời điểm refresh token được sử dụng.
- **acr:** Authentication Context Class Reference, giá trị xác định lớp/ngữ cảnh xác thực theo semantics do OpenID Provider (OP) định nghĩa.
- **amr:** Authentication Methods References, thường là danh sách phương thức xác thực mà OP báo cáo theo semantics của mình.

Các claim này chỉ có ý nghĩa khi RP xác minh ID Token và hiểu hợp đồng với issuer. Không có một mapping toàn cầu bảo đảm mọi OP dùng cùng chuỗi acr/amr với cùng mức assurance.

Ví dụ, hai OP có thể dùng cùng giá trị amr nhưng triển khai khác nhau. Một OP có thể phát hành acr cho MFA với policy chống phishing; OP khác có thể dùng acr tương tự cho một flow yếu hơn. RP cần tài liệu và kiểm thử với từng issuer trước khi dùng claim để cấp quyền nhạy cảm.

### Không suy ra assurance từ tên claim

Không tự kết luận:
- amr chứa chuỗi “mfa” nghĩa là MFA chống phishing;
- amr chứa “otp” nghĩa là phương thức đủ mạnh cho mọi hành động;
- acr có chuỗi “high” nghĩa là đạt một AAL tiêu chuẩn;
- auth_time gần đây nghĩa là mọi credential đều còn an toàn.

Nếu policy cần assurance cụ thể, tổ chức phải định nghĩa mapping rõ từ issuer/credential profile sang policy class, có bằng chứng và quy trình thay đổi.

## 6. Authentication freshness và auth_time

Một phiên có thể còn active trong nhiều giờ hoặc nhiều ngày, nhưng một số hành động yêu cầu người dùng xác thực lại gần thời điểm thực hiện.

Freshness có thể được đánh giá bằng:
- thời gian kể từ auth_time;
- thời gian kể từ step-up gần nhất;
- session idle time và absolute lifetime;
- sự kiện thay đổi credential hoặc account state;
- mức nhạy cảm của action/resource;
- policy của tenant hoặc tổ chức.

Ví dụ:
- Xem trang hồ sơ thông thường: session active có thể đủ.
- Thay đổi email khôi phục: yêu cầu xác thực lại trong khoảng thời gian ngắn.
- Cấp quyền quản trị: yêu cầu step-up đạt assurance được quy định.
- Thay đổi khóa thanh toán: yêu cầu transaction confirmation gắn với nội dung thay đổi.

Không dùng iat thay cho auth_time. iat cho biết token được phát hành lúc nào; token mới có thể được phát hành từ một session xác thực cũ. Nếu OP hỗ trợ max_age, RP có thể yêu cầu freshness theo giao thức và vẫn phải kiểm tra auth_time trong ID Token theo quy tắc OIDC.

## 7. ACR, AMR và mức assurance

Một tổ chức có thể định nghĩa các lớp policy nội bộ, ví dụ:

| Policy class nội bộ | Ý nghĩa khái quát | Ví dụ yêu cầu |
| --- | --- | --- |
| BASIC | Xác thực phù hợp truy cập thông thường | Credential hợp lệ và session active |
| MFA_REQUIRED | Cần nhiều yếu tố theo policy | Hai yếu tố độc lập đã được xác minh |
| PHISHING_RESISTANT | Cần phương thức chống phishing theo tiêu chí tổ chức | Passkey/WebAuthn hoặc security key được cấu hình phù hợp |
| HIGH_ASSURANCE | Hành động đặc biệt nhạy cảm | Authenticator, user verification, freshness, device/context và kiểm soát bổ sung theo risk |

Đây là ví dụ policy class nội bộ, không phải chuẩn ACR toàn cầu hoặc mapping tự động sang NIST AAL. Nếu tổ chức áp dụng NIST SP 800-63 AAL, phải đánh giá đầy đủ yêu cầu của mức đó và các điều kiện triển khai; không thể suy ra AAL chỉ từ một claim amr.

### Mapping issuer

Với mỗi OP:
1. Xác minh issuer và metadata.
2. Xác định acr/amr values mà OP thực sự phát hành.
3. Hiểu cách OP thực hiện enrollment, MFA, user verification và recovery.
4. Xác minh cách OP xử lý reauthentication và max_age.
5. Mapping giá trị sang policy class nội bộ bằng cấu hình được review.
6. Fail closed hoặc yêu cầu step-up nếu giá trị không biết hay không đủ bằng chứng.

Không dùng substring như acr.contains("strong") để quyết định quyền. Mapping nên là allowlist rõ ràng theo issuer và value chính xác.

## 8. WebAuthn User Verification trong context

WebAuthn phân biệt User Presence (UP) và User Verification (UV):
- UP cho biết có user interaction/presence theo ceremony;
- UV cho biết authenticator đã thực hiện xác minh người dùng theo khả năng và policy của authenticator.

RP phải xác minh assertion trước khi sử dụng các flags. Không suy từ giao diện browser rằng người dùng đã dùng vân tay hoặc khuôn mặt; authenticator có thể dùng PIN hoặc phương thức khác. Server không nhận biometric template trong WebAuthn thông thường.

Context có thể ghi:
- credential ID reference;
- RP ID và origin đã xác minh;
- UP/UV flags;
- thời điểm assertion;
- authenticator metadata nếu policy và privacy cho phép;
- credential status.

Không coi UV đơn lẻ là bằng chứng rằng thiết bị không bị malware, hoặc rằng người dùng đã chấp thuận nội dung giao dịch. Nếu cần transaction signing, phải có cơ chế ràng buộc và hiển thị giao dịch phù hợp.

## 9. Gắn context đã xác minh với principal và session

Sau khi authentication hoàn tất, server nên tạo một authenticated principal/session với context đã được kiểm chứng.

Ví dụ cấu trúc khái niệm:

~~~json
{
  "principal": {
    "accountId": "acct-1842",
    "issuer": "https://id.example.edu",
    "subject": "student-8821",
    "tenantId": "campus-a"
  },
  "authentication": {
    "authenticatedAt": "2026-11-22T09:40:00Z",
    "methods": ["webauthn"],
    "contextClass": "PHISHING_RESISTANT",
    "userVerified": true,
    "credentialRef": "cred-opaque-71"
  },
  "session": {
    "sessionRef": "session-opaque-22",
    "createdAt": "2026-11-22T09:40:01Z",
    "expiresAt": "2026-11-22T17:40:01Z",
    "status": "ACTIVE"
  }
}
~~~

Ví dụ không phải schema chuẩn. Không lưu raw assertion, private key, OTP, token secret hoặc biometric data vào context. Dữ liệu cần được bảo vệ như thông tin xác thực và chỉ chia sẻ cho service cần thiết.

Session context cần:
- nguồn và thời điểm của từng thuộc tính;
- issuer/client/tenant binding;
- policy mapping version;
- trạng thái và expiry;
- cách cập nhật khi step-up;
- cách revoke khi credential/account bị thu hồi.

Không để client tự gửi JSON context ở request tiếp theo rồi backend tin trực tiếp. Context phải được giữ server-side hoặc được chuyển trong token/service assertion đã ký và xác minh đúng audience.

## 10. PDP, PEP và ABAC sử dụng context ra sao?

Trong kiến trúc authorization:
- **PEP (Policy Enforcement Point):** điểm chặn request, thu thập context cần thiết và thực thi quyết định allow/deny/challenge.
- **PDP (Policy Decision Point):** đánh giá policy dựa trên principal, action, resource và environment.
- **PIP (Policy Information Point):** nguồn thuộc tính như account status, membership, device posture hoặc resource metadata.
- **PAP (Policy Administration Point):** nơi quản trị policy.

**ABAC (Attribute-Based Access Control)** quyết định dựa trên thuộc tính của subject, resource, action và environment. Authentication context có thể cung cấp một phần thuộc tính subject/session.

~~~mermaid
flowchart LR
    C["Client request"] --> PEP["PEP / API gateway"]
    PEP --> AUTH["Verify session / token"]
    AUTH --> CTX["Verified authentication context"]
    PEP --> PIP["PIP: account, tenant, resource, device"]
    CTX --> PDP["PDP / Policy engine"]
    PIP --> PDP
    PEP --> PDP
    PDP --> DEC{"Decision"}
    DEC -->|Permit| APP["Execute action"]
    DEC -->|Deny| DENY["Reject"]
    DEC -->|Step-up required| STEP["Start step-up flow"]
~~~

PEP không nên tự đoán assurance từ request header. PDP cần nhận thuộc tính đã có provenance, timestamp và scope rõ. Quyết định nên có reason code để audit và hỗ trợ vận hành.

## 11. Policy phải kết hợp subject, action, resource và environment

Một policy authorization có thể xem xét:

- **Subject:** account ID, role, group, tenant membership, authentication context.
- **Action:** read, update, export, approve, grant-role, delete.
- **Resource:** loại tài nguyên, owner, tenant, sensitivity label.
- **Environment:** thời gian, device posture, network risk, session state, transaction context.

Ví dụ, Mai có role MembershipAdmin trong tenant A:
- xem danh sách thành viên: role và membership có thể đủ;
- thêm thành viên: có thể yêu cầu session active và MFA;
- cấp role Owner: yêu cầu context chống phishing và xác thực mới;
- thao tác trên tenant B: từ chối vì thiếu membership, dù authentication context mạnh.

Authentication context là một điều kiện trong policy, không thay thế quyền trên resource. Một principal xác thực rất mạnh vẫn không được truy cập tenant hoặc resource mà họ không có quyền.

## 12. Ví dụ policy theo freshness và assurance

Policy minh họa:

~~~text
POLICY: grant_role

REQUIRE:
  principal.status == ACTIVE
  session.status == ACTIVE
  principal has TENANT_ADMIN in resource.tenant
  action == GRANT_ROLE
  resource.tenant == request.tenant
  authentication.contextClass in approved_classes
  authentication.authenticatedAt >= now - 5 minutes
  authentication.userVerified == true

IF all requirements hold:
  PERMIT
ELSE IF identity and membership are valid
        AND only freshness/assurance is insufficient:
  STEP_UP_REQUIRED
ELSE:
  DENY
~~~

Đây là ví dụ minh họa. Policy thực tế phải xác định:
- ai được phép cấp role nào;
- có được cấp role bằng hoặc cao hơn role của chính mình không;
- tenant/resource binding;
- context class nào được chấp nhận theo issuer;
- freshness window và clock-skew;
- cách xử lý device posture không có hoặc stale;
- step-up có được thực hiện bằng credential đủ mạnh không.

Không biến “context class đạt” thành quyền cấp mọi role. Authorization vẫn phải kiểm tra separation of duties, approval workflow và business constraints.

## 13. Step-up khi context chưa đủ

Nếu principal hợp lệ nhưng context không đáp ứng policy, PDP có thể trả kết quả yêu cầu step-up thay vì permit.

Ví dụ:
1. Mai có session active nhưng auth_time đã quá cũ.
2. Cô yêu cầu đổi email khôi phục.
3. PDP xác định action cần xác thực mới trong 5 phút.
4. PEP khởi tạo step-up transaction gắn với account, session, action và resource.
5. Người dùng hoàn tất passkey/MFA phù hợp.
6. Server xác minh proof và cập nhật authentication context.
7. PDP đánh giá lại request ban đầu với context mới.
8. Chỉ thực hiện hành động nếu các điều kiện authorization còn đúng.

Step-up không được tự cấp quyền. Nó chỉ bổ sung bằng chứng xác thực để PDP đánh giá lại. Challenge cần gắn với đúng account/session/action, có expiry và chống replay. Nếu resource hoặc action thay đổi, phải đánh giá lại context và policy.

## 14. Context phải được ràng buộc với đúng tenant và resource

Trong hệ thống multi-tenant, một context xác thực không tự tạo quyền ở mọi tenant. Principal có thể thuộc nhiều tenant với role khác nhau.

Cần kiểm tra:
- tenant được xác định từ resource hoặc routing đã xác minh;
- principal có membership active trong tenant đó;
- role/grant nằm trong đúng tenant scope;
- context không bị lấy từ session của tenant khác;
- token audience và client phù hợp với service;
- resource ID thuộc tenant đã chọn;
- delegated/admin access có scope và expiry rõ.

Không tin tenant ID do client gửi mà không kiểm tra resource ownership và membership. Không dùng global role hoặc claim trong token để bỏ qua tenant boundary nếu policy yêu cầu tenant-scoped authorization.

## 15. Tín hiệu thiết bị và mạng trong authorization context

Device posture, network location, IP reputation, browser fingerprint và hành vi có thể hỗ trợ risk-based authorization, nhưng chúng có độ tin cậy và freshness khác nhau.

| Tín hiệu | Có thể hỗ trợ | Không tự chứng minh |
| --- | --- | --- |
| MDM compliant | Thiết bị báo cáo đáp ứng policy quản lý | Người dùng hiện tại là chủ account hoặc mọi app an toàn |
| Device certificate | Client kiểm soát private key tương ứng | Người đang dùng thiết bị là người cụ thể |
| Known device cookie | Browser từng hoàn tất flow ghi nhớ | Thiết bị không bị đánh cắp hoặc cookie không bị copy |
| IP/network risk | Request đến từ network có đặc điểm nhất định | Danh tính hoặc vị trí vật lý chính xác của người dùng |
| Browser fingerprint | Một số đặc điểm client tương đồng | Device identity bền vững hoặc chống spoofing |
| Geolocation estimate | Tín hiệu khu vực có thể hỗ trợ phát hiện bất thường | Bằng chứng xác thực hoặc quyền truy cập |

Mỗi signal cần nguồn, timestamp, confidence và policy khi unavailable. Không dùng IP hoặc fingerprint làm yếu tố xác thực. Không từ chối người dùng chỉ vì VPN hoặc mạng di động làm thay đổi IP nếu không có tín hiệu bổ sung.

## 16. Provenance, integrity và freshness của context

Mỗi thuộc tính context nên trả lời được:
- ai/ hệ thống nào phát hành;
- được xác minh bằng cách nào;
- gắn với principal, session, client và tenant nào;
- thời điểm phát hành và thời điểm hết hạn;
- có thể bị thay đổi bởi service nào;
- policy mapping version nào đã diễn giải nó.

Ví dụ:
- auth_time từ ID Token đã xác minh của issuer cụ thể;
- userVerified từ WebAuthn assertion đã được verifier kiểm tra;
- deviceCompliant từ MDM connector đã xác thực;
- sessionStatus từ session store authoritative;
- tenantMembership từ entitlement service.

Không lấy context từ header như X-Auth-Method, X-User-Role hoặc X-MFA-Verified nếu client có thể tự đặt. Nếu API gateway thêm header nội bộ, gateway phải xóa header trùng do client gửi, xác thực downstream channel và service phải chỉ tin gateway đã được cấu hình.

Context cũ có thể trở nên sai sau khi:
- account bị disable;
- credential bị revoke;
- session bị logout;
- user bị gỡ khỏi tenant;
- device bị đánh dấu lost/non-compliant;
- issuer key bị compromise;
- policy mapping thay đổi.

Do đó, context không phải một snapshot bất biến được tin mãi. Cần kiểm tra freshness và trạng thái hiện hành tại thời điểm quyết định.

## 17. Token và claim: xác minh trước khi dùng cho authorization

Nếu authentication context được truyền trong JWT hoặc token khác, consumer phải xác minh token theo giao thức:
- chữ ký và thuật toán được phép;
- issuer chính xác;
- audience dành cho service hiện tại;
- thời hạn exp/nbf/iat theo policy;
- subject và client binding;
- nonce hoặc transaction binding khi giao thức yêu cầu;
- claim schema và semantics đã thỏa thuận;
- revocation/session/account state nếu action yêu cầu kiểm tra mới.

Không coi một JWT decode được là token hợp lệ. Không nhận token dành cho API A ở API B chỉ vì cùng issuer. Không dùng ID Token thay Access Token hoặc ngược lại.

Với Access Token, authorization server có thể phát scope/role/claim theo audience. Resource server vẫn cần kiểm tra token và policy cục bộ. Claim authorization có thể stale trước khi token hết hạn; với quyền nhạy cảm, cần introspection, short TTL, version check hoặc truy vấn entitlement hiện hành tùy kiến trúc.

## 18. Session context và reauthentication

Một session có thể lưu tham chiếu tới authentication event và context đã xác minh. Nhưng session lifetime không đồng nghĩa authentication freshness.

Các thời gian cần phân biệt:
- **authenticatedAt:** lần xác thực người dùng gần nhất theo semantics;
- **sessionCreatedAt:** lúc session được tạo;
- **lastActivityAt:** lần hoạt động gần nhất;
- **sessionExpiresAt:** hạn tuyệt đối của session;
- **lastStepUpAt:** lần step-up gần nhất;
- **credentialChangedAt:** thời điểm credential thay đổi.

Refresh token hoặc silent token renewal không tự làm mới auth_time. Một session có thể còn active nhưng cần step-up cho hành động nhạy cảm. Khi credential/account bị revoke, session cần được revoke hoặc đánh giá lại theo policy.

## 19. Context downgrade và confused deputy

Một số lỗi thiết kế làm policy chấp nhận context yếu hơn dự kiến:

- client tự khai acr/amr hoặc MFA result;
- mapping issuer quá rộng hoặc dựa substring;
- service A xác minh token nhưng không ràng buộc audience cho service B;
- session của tenant A được dùng để truy cập resource tenant B;
- step-up hoàn tất cho action X nhưng proof được tái sử dụng cho action Y;
- gateway chuyển tiếp header giả từ client;
- stale role/context được cache sau khi account bị deprovision;
- một service có quyền cao dùng token của người dùng cho action ngoài scope.

Phòng vệ:
- allowlist issuer/claim mapping chính xác;
- audience và client binding;
- context provenance và expiry;
- step-up transaction bound với action/resource;
- tenant/resource authorization độc lập;
- PEP tại mọi trust boundary;
- service identity và least privilege;
- revoke/version checks;
- audit quyết định và reason code.

## 20. Deny, step-up và fail-safe behavior

PDP có thể trả:
- **Permit:** tất cả điều kiện cần thiết đã đạt.
- **Deny:** principal không có quyền hoặc điều kiện bắt buộc không thể thỏa.
- **Step-up required:** principal có thể hợp lệ nhưng context hiện tại chưa đủ.
- **Indeterminate:** policy engine hoặc nguồn thuộc tính không thể đưa ra quyết định đáng tin.

Không biến Indeterminate thành Permit cho hành động nhạy cảm. Nếu session store, entitlement service hoặc context provider không khả dụng, policy cần xác định fail closed hoặc degraded mode được phê duyệt. Hành động ít rủi ro có thể có fallback hẹp; hành động quản trị, tài chính hoặc không thể đảo ngược cần kiểm tra đầy đủ.

Không yêu cầu step-up vô hạn khi vấn đề thực tế là account không có quyền. Nếu membership sai, phải deny hoặc yêu cầu quy trình cấp quyền riêng; xác thực mạnh hơn không sửa được authorization failure.

## 21. Audit quyết định authorization có dùng context

Audit nên ghi:
- principal/account reference;
- issuer/client và authentication event reference;
- auth_time, context class/method đã mapping;
- policy version và mapping version;
- action, resource và tenant;
- context attributes đã sử dụng và provenance;
- decision (permit/deny/step-up/indeterminate);
- reason code;
- PDP/PEP request correlation ID;
- thời điểm quyết định và trạng thái session;
- step-up transaction reference nếu có.

Không ghi raw token, session cookie, password, OTP hoặc private key. Tránh lưu fingerprint, IP chính xác hoặc dữ liệu thiết bị chi tiết nếu không cần cho mục đích đã xác định. Bảo vệ audit bằng access control, retention và integrity.

## 22. Ví dụ pseudocode PDP

Ví dụ Java khái niệm:

~~~java
AuthorizationDecision evaluate(
        VerifiedPrincipal principal,
        AuthenticationContext authContext,
        Action action,
        Resource resource,
        EnvironmentContext environment) {

    accountPolicy.requireActive(principal.accountId());
    sessionPolicy.requireActive(authContext.sessionRef());

    if (!tenantPolicy.hasMembership(
            principal.accountId(), resource.tenantId())) {
        return AuthorizationDecision.deny("TENANT_MEMBERSHIP_REQUIRED");
    }

    if (!entitlementPolicy.permits(
            principal.accountId(), action, resource)) {
        return AuthorizationDecision.deny("ENTITLEMENT_REQUIRED");
    }

    if (policy.requiresRecentAuthentication(action)
            && !authContext.isFreshWithin(policy.maxAuthAge(action))) {
        return AuthorizationDecision.stepUp("AUTHENTICATION_TOO_OLD");
    }

    if (policy.requiresContextClass(action)
            && !policy.approvedContextClasses(action)
                    .contains(authContext.contextClass())) {
        return AuthorizationDecision.stepUp("ASSURANCE_INSUFFICIENT");
    }

    if (policy.requiresUserVerification(action)
            && !authContext.userVerified()) {
        return AuthorizationDecision.stepUp("USER_VERIFICATION_REQUIRED");
    }

    if (policy.requiresManagedDevice(action)
            && !environment.devicePostureIsFreshAndCompliant()) {
        return AuthorizationDecision.denyOrStepUp(
            "DEVICE_POSTURE_NOT_SATISFIED");
    }

    return AuthorizationDecision.permit();
}
~~~

Đây là pseudocode minh họa, không phải policy engine hoàn chỉnh. Trong production:
- chỉ truyền VerifiedPrincipal/AuthenticationContext do verifier tạo;
- không nhận object context từ request body như nguồn tin cậy;
- policy mapping phải gắn issuer và version;
- kiểm tra resource ownership, tenant và action constraints;
- phân biệt context không đủ với thiếu entitlement;
- kiểm tra trạng thái hiện hành cho hành động nhạy cảm;
- log reason code mà không lưu secret;
- xác định behavior khi PIP/PDP không khả dụng.

## 23. Kiểm thử authentication context cho authorization

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| ID Token chữ ký hợp lệ, issuer đúng, audience đúng | Chỉ sau validation mới dùng claims trong context. |
| Issuer không nằm trong trust configuration | Từ chối token/context. |
| Audience dành cho API khác | Từ chối tại service hiện tại. |
| auth_time cũ nhưng iat mới | Không coi token mới là xác thực mới. |
| acr không được mapping | Không nâng assurance; step-up hoặc deny. |
| amr chứa giá trị không được thỏa thuận | Không tự suy ra MFA/phishing resistance. |
| WebAuthn UV flag hợp lệ | Context ghi UV true theo verifier result. |
| UV bắt buộc nhưng flag thiếu | Step-up hoặc deny theo policy. |
| Client gửi X-MFA-Verified=true | Bị bỏ qua/từ chối; chỉ tin verifier context. |
| Session đã revoked | Authorization bị từ chối dù token cũ còn được gửi. |
| Account bị disabled | Không permit dựa trên context cũ. |
| Membership tenant đã bị gỡ | Deny trong tenant đó. |
| Principal có role ở tenant A nhưng request tenant B | Deny nếu không có membership/grant ở B. |
| Device posture stale | Không coi là compliant; áp dụng fallback policy. |
| Device fingerprint giống known device | Không tự nâng assurance hoặc bỏ MFA. |
| Context class đủ nhưng không có entitlement | Deny. |
| Entitlement đủ nhưng auth freshness thiếu | Step-up nếu policy cho phép. |
| Step-up cho action X được replay vào action Y | Từ chối do transaction/action binding. |
| Policy mapping version thay đổi | Cache/context được re-evaluate theo migration policy. |
| PIP không khả dụng | Không fail open cho hành động nhạy cảm. |
| Gateway nhận header giả từ client | Header bị strip; service chỉ tin context nội bộ đã xác thực. |
| JWT hết hạn hoặc nbf chưa tới | Từ chối. |
| Token có claim role không nằm trong allowlist | Không cấp role từ claim đó. |
| Logout all devices đã hoàn tất | Session/context cũ bị từ chối theo revocation policy. |
| Audit decision | Ghi đủ policy version, context source, action/resource và reason code. |

## 24. Bài tập tình huống

Một nền tảng đa tenant dùng OIDC. Sau khi đăng nhập, API gateway tạo header X-User, X-MFA-Verified và X-Tenant từ các trường client gửi lên. Backend tin header để cho phép người dùng xuất dữ liệu. ID Token có acr="2" và amr=["pwd","otp"], nhưng tổ chức chưa có tài liệu mapping giữa issuer và giá trị này. Token được refresh mỗi 10 phút nên đội phát triển cho rằng auth_time luôn mới. Người dùng có role Exporter ở tenant A nhưng gửi request tới tenant B.

**Yêu cầu phân tích:**

1. Vì sao các header hiện tại không phải authentication context đáng tin?
2. Cần xác minh ID Token và issuer như thế nào trước khi mapping claim?
3. Vì sao không thể suy ra assurance chỉ từ acr/amr chưa có semantics?
4. Vì sao iat/refresh time không thay thế auth_time?
5. Cách gắn verified context với principal/session ra sao?
6. PDP cần kiểm tra những thuộc tính nào ngoài context?
7. Làm sao xử lý tenant A/B và device posture?
8. Khi context không đủ, khi nào step-up và khi nào deny?

**Hướng phân tích:** Gateway phải strip header client gửi và tự tạo context từ token/session đã xác minh. Kiểm tra signature, issuer, audience, exp và claim theo OIDC. Mapping acr/amr cần contract theo issuer; nếu chưa rõ thì không nâng assurance. Refresh token không phải authentication mới, nên auth_time giữ semantics của lần xác thực. PDP kiểm tra account, session, membership tenant, entitlement, action/resource và freshness. Role ở tenant A không cho phép truy cập B. Step-up chỉ phù hợp khi principal có quyền nhưng context chưa đủ; thiếu membership thì deny.

## 25. Checklist review

- [ ] Phân biệt authentication, authentication context và authorization.
- [ ] Context chỉ được tạo từ verifier hoặc service nguồn đã xác thực.
- [ ] Principal mapping dùng issuer + subject hoặc identity key đã quản trị.
- [ ] ID Token/Access Token được xác minh đúng issuer, audience, signature và thời hạn.
- [ ] auth_time không bị nhầm với iat hoặc token refresh time.
- [ ] acr/amr có mapping rõ theo issuer; không suy assurance từ tên claim.
- [ ] User Presence và User Verification được phân biệt và xác minh đúng.
- [ ] Context có provenance, timestamp, expiry và policy mapping version.
- [ ] Session/account/credential revocation được kiểm tra theo mức rủi ro.
- [ ] Device/network signals là context/risk attributes, không tự thành authentication factor.
- [ ] PEP/PDP kiểm tra subject, action, resource, tenant và environment.
- [ ] Entitlement/membership được đánh giá độc lập với authentication strength.
- [ ] Step-up gắn với đúng principal, session, action/resource và expiry.
- [ ] Context từ client header/body không được tin trực tiếp.
- [ ] Multi-tenant boundary và resource ownership được xác minh.
- [ ] Stale context, policy downgrade, confused deputy và replay được kiểm soát.
- [ ] PIP/PDP outage không fail open cho hành động nhạy cảm.
- [ ] Audit ghi context source, policy version, decision và reason code.
- [ ] Có test issuer mismatch, stale auth_time, untrusted acr/amr, revoke, tenant và step-up replay.

## 26. Ghi nhớ

**Authentication context cung cấp các thuộc tính đã được xác minh về lần xác thực và trạng thái phiên để policy authorization đánh giá trong đúng bối cảnh.** Các claim như auth_time, acr và amr chỉ có ý nghĩa theo issuer và hợp đồng đã thỏa thuận; device/network signals là dữ liệu môi trường có freshness và độ tin cậy riêng. PDP vẫn phải kiểm tra principal, action, resource, tenant, entitlement và trạng thái hiện hành.

Khi review, hãy hỏi: **Context đến từ verifier nào? Issuer và claim semantics đã được mapping chưa? Lần xác thực thực sự diễn ra khi nào? Session còn active không? Principal có quyền trên resource và tenant này không? Nếu context thiếu thì cần step-up hay deny? Có cách nào để client giả header hoặc tái sử dụng context cũ không?**
