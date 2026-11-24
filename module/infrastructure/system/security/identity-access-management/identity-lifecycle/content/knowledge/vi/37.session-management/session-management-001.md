# Session là gì trong Session management và IAM Identity Lifecycle?

## 1. Session là gì?

**Session (phiên làm việc hoặc phiên đăng nhập)** là **ngữ cảnh được duy trì trong một khoảng thời gian** để hệ thống nhận biết chuỗi yêu cầu hoặc tương tác đến từ một chủ thể đã được xác thực, đồng thời áp dụng những điều kiện bảo mật và trạng thái phù hợp. Trong ứng dụng web, session thường bắt đầu sau khi người dùng đăng nhập thành công; trình duyệt giữ một **session cookie** và gửi nó ở những request tiếp theo để server tra cứu phiên.

Ví dụ, Lan đăng nhập Finance Portal bằng SSO và MFA lúc 09:00. Sau đó Lan mở trang báo cáo, chuyển trang và tải dữ liệu mà không phải nhập lại mật khẩu ở mỗi lần click. Ứng dụng dùng session đã thiết lập để nhận diện **Lan đang dùng phiên nào** và tiếp tục **kiểm tra Lan có quyền làm action nào trên resource nào**.

**Session không phải là quyền truy cập vĩnh viễn.** Việc một session còn hiệu lực về xác thực **không tự đồng nghĩa** người dùng vẫn được phép xem tài liệu, duyệt hóa đơn hay quản trị hệ thống. Khi quyền thay đổi, account bị khóa, thời hạn hết hoặc nhân viên Leaver, hệ thống phải áp dụng **cập nhật authorization và/hoặc chấm dứt session** theo chính sách.

Bài thuộc chương **Session management** của mô-đun **SECURITY_IDENTITY_ACCESS_MANAGEMENT_IDENTITY_LIFECYCLE**, tập trung **Joiner–Mover–Leaver (JML)**: xác minh danh tính, tạo account, cấp quyền, rà soát và thu hồi khi quan hệ hoặc vai trò thay đổi. Nội dung liên hệ **IdP, SSO, SCIM, RBAC/ABAC, tài khoản dịch vụ, audit** và mục tiêu giảm **quyền truy cập tồn dư**.

### Mục tiêu học tập

Sau bài học, người đọc có thể:

1. Giải thích session, session ID, session state và session lifecycle.
2. Phân biệt **session ứng dụng**, **session IdP**, **cookie**, **JWT access token**, **refresh token** và **TLS session**.
3. Mô tả mô hình **server-side stateful** và **client-side/stateless** cùng giới hạn thu hồi.
4. Thiết kế cookie, timeout, rotation, logout và bảo vệ chống session fixation, hijacking, CSRF, XSS.
5. Hiểu **MFA/step-up, reauthentication, concurrent sessions** và đánh giá rủi ro theo ngữ cảnh.
6. Liên kết session với **IdP/SSO/OIDC, SCIM, RBAC/ABAC, PAM/JIT**.
7. Phân tích tác động của **Joiner, Mover, Leaver và Rejoiner** tới các session và token còn sống.
8. Thiết kế audit, quan sát quyền thực tế, kiểm thử, xử lý sự cố và đối soát session.

## 2. Vì sao cần session?

HTTP về bản chất xử lý request/response; mỗi request không tự mang đầy đủ lịch sử người dùng đã đăng nhập ở những request trước. Session giúp ứng dụng gắn những tương tác liên tiếp với một **ngữ cảnh đăng nhập được xác minh**.

~~~mermaid
sequenceDiagram
    participant U as Trình duyệt Lan
    participant APP as Finance Portal
    participant STORE as Session Store
    U->>APP: Đăng nhập / hoàn tất SSO
    APP->>APP: Xác thực kết quả và tạo phiên
    APP->>STORE: Lưu session state gắn ID ngẫu nhiên
    APP-->>U: Set-Cookie: session ID
    U->>APP: GET /reports + Cookie
    APP->>STORE: Lookup session / kiểm timeout
    STORE-->>APP: Lan, auth context, expiry
    APP->>APP: Kiểm quyền đọc báo cáo cụ thể
    APP-->>U: Dữ liệu được phép hoặc 403
~~~

Đây là **mô hình server-side session**, không phải cách duy nhất để duy trì phiên. Một số hệ thống dùng token tự chứa hoặc kiến trúc BFF (Backend for Frontend), nhưng vẫn phải giải quyết những vấn đề tương tự về **thời hạn, danh tính, quyền và chấm dứt truy cập**.

### Session giúp ích những gì?

- Giảm số lần người dùng phải nhập credential.
- Gắn request với **identity, mức xác thực và ngữ cảnh phiên**.
- Hỗ trợ idle timeout, logout và giới hạn thiết bị đồng thời.
- Ghi lại lịch sử đăng nhập, IP/device risk hoặc sự kiện an ninh theo chính sách.
- Cho phép một phần authorization phụ thuộc **session assurance**, ví dụ bắt buộc step-up trước thao tác nhạy cảm.
- Cung cấp đầu mối để **chấm dứt phiên** khi tài khoản bị khóa, nghi bị chiếm đoạt hoặc Leaver.

### Session không nên làm gì?

Không dùng session như nguồn quyền duy nhất trong thời gian vô hạn. Nếu role và permission được sao chép vào session lúc đăng nhập rồi không bao giờ cập nhật, người dùng có thể tiếp tục có quyền cũ sau Mover hoặc access review Revoke.

## 3. Các thuật ngữ cốt lõi của session

| Thuật ngữ | Ý nghĩa | Ví dụ |
|---|---|---|
| **Session** | Ngữ cảnh tương tác được duy trì giữa những request | Phiên Lan tại Finance Portal |
| **Session ID** | Định danh không thể đoán dùng để lookup phiên | Giá trị ngẫu nhiên trong cookie |
| **Session cookie** | Cơ chế browser gửi session ID hoặc token đã được bảo vệ | __Host-session |
| **Session state** | Dữ liệu server/payload cho biết chủ thể, hiệu lực, assurance | subjectId, createdAt, expiry |
| **Authentication context** | Thông tin về lần xác thực/mức xác thực | auth_time, MFA đạt |
| **Session store** | Nơi lưu phiên stateful | Redis hoặc database |
| **Idle timeout** | Hết phiên nếu không có hoạt động hợp lệ trong khoảng | 15 phút minh họa |
| **Absolute timeout** | Hạn tối đa từ lúc tạo hoặc xác thực, bất kể hoạt động | 8 giờ minh họa |
| **Reauthentication** | Xác thực lại khi cần | Đăng nhập lại sau hạn |
| **Step-up authentication** | Nâng assurance cho action rủi ro | Security key trước export |
| **Session revocation** | Vô hiệu phiên trước khi hết hạn | Server hủy session ID |
| **Federated session** | Quan hệ phiên liên quan IdP và ứng dụng SSO | IdP còn login, RP đã logout |
| **Token session** | Cách gọi không thống nhất cho token/phiên dựa token | OAuth refresh/token family |
| **TLS session** | Ngữ cảnh mật mã của kết nối TLS | TLS resumption; không phải web login |

Các từ **session** và **token** đôi khi bị dùng thay nhau trong sản phẩm, nhưng khi thiết kế phải xác định chính xác **issuer, holder, thời hạn, nơi kiểm tra và cơ chế revocation**.

## 4. Session khác authentication và authorization

Ba câu hỏi khác nhau:

| Lớp | Câu hỏi | Ví dụ |
|---|---|---|
| **Authentication** | Chủ thể hiện đang chứng minh mình là ai? | Lan xác thực bằng passkey |
| **Session management** | Làm sao giữ ngữ cảnh xác thực an toàn giữa các request? | Session cookie, TTL, revocation |
| **Authorization** | Lan có được thực hiện action trên resource này ngay lúc này? | report.export của tenant A |
| **Access governance** | Lan có nên tiếp tục nắm entitlement này không? | Access review sau khi Mover |
| **Identity lifecycle** | Quan hệ làm việc của Lan hiện còn hợp lệ không? | HRIS ACTIVE/LEAVER |
| **Audit** | Ai đã truy cập, dùng phiên nào, kết quả ra sao? | eventId và session correlation |

**Session hợp lệ chưa đủ để Permit một action.** Ví dụ Lan đã xác thực hợp lệ nhưng không có permission **payment.approve**; API phải trả **403 Forbidden** hoặc quyết định từ chối tương ứng, thay vì cho phép vì session còn tồn tại.

**MFA không tự cấp quyền.** MFA có thể làm tăng assurance của session, nhưng user vẫn phải có entitlement và phạm vi hợp lệ.

## 5. Những loại session thường gặp

| Loại | Chủ thể/nơi giữ | Cơ chế | Lưu ý |
|---|---|---|---|
| **Application local session** | Một web app/Relying Party | Cookie + server store hoặc signed/encrypted payload | Logout tại app không nhất thiết kết thúc IdP session |
| **IdP/SSO session** | Identity Provider | IdP cookies và login context | Có thể cho phép SSO tới nhiều app |
| **OAuth authorization server session** | Authorization server | Login/consent/account context | Không đồng nhất với access token |
| **Mobile app session** | Ứng dụng di động/backend | Access/refresh token, device binding | Token storage cần bảo vệ theo OS |
| **API access context** | API/resource server | Bearer token hoặc sender-constrained token | Có audience/scope/expiry |
| **Privileged PAM session** | PAM/broker/target | JIT grant và session record | TTL, step-up, command audit, kill session |
| **Remote desktop/SSH session** | Hệ thống remote | Connection/auth context | Hủy IdP login không tự ngắt mọi phiên |
| **TLS session** | Network TLS peers | Session resumption/cryptographic state | Khác ứng dụng session |
| **Workload-to-workload context** | Service/machine identities | mTLS, service token | Không gắn cookie browser theo mặc định |

### Một người có thể có nhiều session

Lan có thể đồng thời đăng nhập:

- Finance Portal trên laptop.
- CRM trên điện thoại.
- IdP SSO trong browser.
- CLI admin qua PAM.
- Một ứng dụng SaaS có local session độc lập.

**Chỉ xóa một cookie không chứng minh đã chấm dứt tất cả các session này.** Cần biết ranh giới phát hành, nơi kiểm và khả năng logout/revocation của từng bên.

## 6. Những thành phần trong một session state

Một session stateful có thể chứa metadata như:

~~~json
{
  "sessionIdHash": "sha256:example-not-a-real-hash",
  "subjectId": "person-2046",
  "relationshipId": "employment-2046-v2",
  "targetApplication": "finance-portal",
  "createdAt": "2026-11-23T09:00:00+07:00",
  "authenticatedAt": "2026-11-23T09:00:00+07:00",
  "lastActivityAt": "2026-11-23T09:12:00+07:00",
  "absoluteExpiresAt": "2026-11-23T17:00:00+07:00",
  "idleTimeoutSeconds": 900,
  "assuranceLevel": "MFA",
  "deviceRef": "managed-device-718",
  "state": "ACTIVE",
  "authzVersion": 18
}
~~~

Đây là **schema minh họa**, không phải chuẩn phiên của OIDC hay một framework. **sessionIdHash** ở đây chỉ là giá trị giả; trong sản phẩm thật cần bảo vệ định danh session đủ ngẫu nhiên, không log raw ID và thiết kế lookup phù hợp.

### Thông tin nên có khi cần

- Identity bền vững: subjectId, tenantId và relationshipId.
- Lần xác thực/mức assurance, auth_time theo định nghĩa của hệ thống.
- Thời gian tạo, last activity, absolute expiry, trạng thái.
- Session generation hoặc authorization version để chặn state lỗi thời.
- Device/risk metadata có nguồn được xác minh.
- Mapping đến IdP session hoặc federated logout reference khi hỗ trợ.
- Audit correlation ID không chứa credential.

### Thông tin không nên để trong session

- Mật khẩu người dùng, khóa riêng, mã recovery hoặc secret nội bộ không cần thiết.
- Toàn bộ hồ sơ HR/PII không phục vụ access control.
- Danh sách quyền admin được coi là bất biến suốt nhiều tháng.
- Token thô trong audit log hoặc các giá trị nhạy cảm trả về client tùy tiện.

## 7. Session lifecycle: Create–Use–Refresh–Revoke–Expire

~~~mermaid
stateDiagram-v2
    [*] --> Unauthenticated
    Unauthenticated --> Authenticated: Login / IdP response validated
    Authenticated --> Active: Session created, cookie issued
    Active --> Active: Authorized activity and safe activity update
    Active --> StepUpRequired: Sensitive action / risk
    StepUpRequired --> Active: Successful reauthentication / MFA
    StepUpRequired --> Revoked: Failed security policy / incident
    Active --> IdleExpired: Inactivity timeout
    Active --> AbsoluteExpired: Maximum session lifetime
    Active --> Revoked: Logout / admin revoke / Leaver
    Active --> Suspended: Account/policy state changed
    Suspended --> Active: Validated recovery per policy
    Suspended --> Revoked: Not eligible
    IdleExpired --> [*]
    AbsoluteExpired --> [*]
    Revoked --> [*]
~~~

**State machine này là mô hình tham khảo**, không bắt buộc mọi hệ thống có Suspended hoặc StepUpRequired. Quan trọng là **không nhầm phiên đã được tạo với phiên đang đủ điều kiện sử dụng**.

### Một số sự kiện chuyển trạng thái

- User đăng nhập thành công.
- User đăng xuất, IdP gửi logout event hoặc admin revoke.
- Idle timeout/absolute timeout.
- User đổi mật khẩu hoặc thêm/bỏ authenticator khi policy yêu cầu.
- MFA risk tăng hoặc thiết bị không còn compliant.
- Account bị lock/suspend hoặc HRIS phát Mover/Leaver.
- PAM privileged grant hết hạn.
- Phát hiện session hijacking, token replay hoặc concurrent sessions bất thường.

Các sự kiện JML phải có **precedence phù hợp**, ví dụ không để một job “refresh session” phục hồi phiên đã bị Leaver revoke.

## 8. Server-side session (stateful)

Trong **stateful session**, browser chỉ giữ một **opaque session ID** còn server giữ session state.

~~~mermaid
flowchart LR
    B[Browser: Secure Cookie] --> APP[Application]
    APP --> STORE[(Shared Session Store)]
    STORE --> APP
    APP --> ID[Identity Lifecycle / Policy]
    APP --> API[Protected Action]
    ID --> API
~~~

### Điểm mạnh

- Có thể **vô hiệu session ID trực tiếp** tại session store.
- Session payload nhạy cảm không cần nằm ở browser.
- Hỗ trợ idle timeout, absolute expiry, device tracking và centralized session control.
- Có thể gắn session với current identity/authorization version.

### Những hạn chế

- Cần store có độ tin cậy/availability phù hợp.
- Session lookup phải được bảo vệ khỏi cache poisoning, session ID enumeration và privilege escalation.
- Nhiều instance cần dùng store chung hoặc cơ chế đồng bộ đáng tin; không dựa vào in-memory local store nếu load balancer có thể chuyển request giữa instances.
- Xóa session ở app A **không tự xóa phiên của app B hoặc IdP**.
- Nếu store không phản ánh token/credential ngoài hệ thống, access vẫn có thể tồn dư.

### Session ID là bearer secret

Nếu attacker có session ID còn sống và ứng dụng không có bảo vệ bổ sung, attacker có thể giả làm user. **Không cần biết mật khẩu** để sử dụng session ID đã bị đánh cắp. Vì vậy session ID phải đủ ngẫu nhiên, chỉ đi qua TLS, không bị lộ qua URL/log và được rotate/hủy đúng lúc.

## 9. Stateless hoặc client-carried session

Một số ứng dụng dùng **signed/encrypted cookie** hoặc **JWT tự chứa** để biểu diễn session thay vì lookup server mỗi request.

Ví dụ thông tin token logic:

~~~json
{
  "iss": "https://auth.example.org",
  "sub": "person-2046",
  "aud": "finance-portal",
  "iat": 1795399200,
  "exp": 1795402800,
  "sid": "session-reference-illustrative",
  "amr": ["mfa"],
  "sessionVersion": 12
}
~~~

Đây là **payload minh họa**, không phải token đã ký. Giá trị thời gian chỉ mang tính ví dụ.

### Điểm mạnh

- Có thể kiểm chữ ký và claims mà không lookup session store ở mỗi request.
- Phù hợp một số kiến trúc phân tán.
- Giảm số lần truy cập backend store khi verification local được phép.

### Giới hạn bảo mật

1. **JWT hợp lệ về chữ ký vẫn có thể chứa role cũ** sau Mover/Leaver.
2. **Không có revocation tức thì theo mặc định** khi token còn hạn và API chỉ xác minh chữ ký/exp.
3. Signed token **không có nghĩa payload được mã hóa**; client có thể đọc claims.
4. Token phải được kiểm **issuer, audience, signature, time, algorithm, token type và policy**.
5. Cookie session có thể cần **CSRF protection** ngay cả khi payload là JWT.
6. Token lộ ra có thể bị replay nếu không sender-constrained hoặc không có kiểm soát bổ sung.
7. SessionVersion hoặc denylist chỉ có tác dụng khi resource server **kiểm nguồn trạng thái mới**.

**Stateless về mặt kiểm chữ ký không đồng nghĩa stateless về an toàn thu hồi**. Khi cần cắt truy cập nhanh, có thể phải bổ sung **server-side state, revocation list, introspection, short TTL hoặc runtime policy checks**.

## 10. Session ID: tính ngẫu nhiên, bí mật và rotation

Một session ID an toàn nên:

- Được sinh bằng **cryptographically secure random number generator (CSPRNG)**.
- Có **entropy đủ lớn** để chống đoán/duyệt brute force theo policy.
- Không nhúng trực tiếp userId, email, role hoặc mốc thời gian dễ đoán như giá trị bảo mật.
- Không xuất hiện trong query string, URL fragment không được bảo vệ hoặc referrer.
- Không bị ghi vào log/tracing/audit ở dạng thô.
- Có **thời hạn, rotation và revocation** được thực thi ở server.
- Không được ứng dụng chấp nhận theo giá trị do attacker ép khi chuyển từ anonymous sang authenticated.

### Tại sao không dùng userId làm session ID?

Người khác có thể biết hoặc đoán userId; đó là **định danh chủ thể**, không phải bearer secret ngẫu nhiên. Dùng userId làm session token cho phép truy cập trái phép nếu backend tin trực tiếp giá trị này.

### Tại sao không để session ID trong URL?

URL có thể bị ghi ở history, analytics, reverse proxy log, access log hoặc truyền qua referrer. Đây là kênh dễ làm rò rỉ session ID; cách thông thường hơn là **Secure/HttpOnly cookie** hoặc cơ chế transport token được quản trị.

### Rotation khi có thay đổi mức tin cậy

Hệ thống nên **regenerate session identifier** khi đăng nhập, sau khi xác thực/step-up hoặc thay đổi privilege quan trọng theo policy. Không nên tiếp tục dùng mã session vô danh mà attacker có thể đã đặt sẵn trước khi user đăng nhập.

## 11. Session cookie và các thuộc tính bảo mật

Ví dụ response cấp session cookie:

~~~http
HTTP/1.1 200 OK
Cache-Control: no-store
Set-Cookie: __Host-session=opaque-random-example; Path=/; Secure; HttpOnly; SameSite=Lax
Content-Type: application/json

{"status":"authenticated"}
~~~

Đây là ví dụ **minh họa**, giá trị cookie không phải session ID thực tế.

| Thuộc tính | Tác dụng | Lưu ý |
|---|---|---|
| **Secure** | Chỉ gửi cookie qua HTTPS theo điều kiện của browser | Không thay thế HSTS/TLS policy |
| **HttpOnly** | JavaScript trong trang không đọc trực tiếp cookie | Không ngăn XSS thực hiện action thay user |
| **SameSite=Lax** | Hạn chế một số trường hợp cross-site gửi cookie | Không thay thế CSRF token |
| **SameSite=Strict** | Chặt hơn, có thể ảnh hưởng UX/SSO | Phải test cross-site navigation |
| **SameSite=None; Secure** | Cho phép cross-site trong trường hợp browser hỗ trợ | Bắt buộc Secure; tăng nhu cầu CSRF defense |
| **Path** | Giới hạn URL path cookie được gửi | Không phải ranh giới isolation mạnh giữa apps cùng origin |
| **Domain** | Giới hạn hoặc mở rộng host nhận cookie | Domain quá rộng tăng rủi ro subdomain |
| **Max-Age/Expires** | Tuổi cookie ở browser | Không thay thế session TTL ở server |
| **__Host- prefix** | Cookie host-only: Secure, Path=/, không Domain | Giảm nguy cơ subdomain can thiệp cookie |

### Quy tắc với __Host- cookie

Cookie tên **__Host-session** cần **Secure, Path=/ và không được đặt Domain**. Browser hỗ trợ prefix sẽ áp các yêu cầu tương ứng. **HttpOnly và SameSite vẫn nên cấu hình riêng** theo use case.

### Hai thời hạn không đồng nhất

**Cookie tồn tại trên browser** không chứng minh **session ở server còn hợp lệ**. Nếu server đã revoke, cookie cũ phải bị từ chối. Ngược lại, xóa cookie browser không nhất thiết xóa bản ghi server nếu logout API không được gọi; cần xử lý cả hai.

## 12. Session cookie, localStorage và token storage

Một lựa chọn kiến trúc thường gặp:

| Cơ chế | Ưu điểm | Rủi ro |
|---|---|---|
| **HttpOnly Secure cookie + server session** | JS khó đọc session ID, server có thể revoke | Cần CSRF defense và session store |
| **HttpOnly cookie + BFF** | Token backend không lộ trực tiếp cho browser JS | Cần bảo vệ BFF, cookie và CSRF |
| **localStorage giữ bearer token** | Client code truy cập tiện lợi | Token dễ bị lấy khi XSS chạy trong origin |
| **sessionStorage giữ bearer token** | Vòng đời thường theo tab | XSS vẫn có thể đọc; tab lifetime không phải session policy |
| **In-memory access token trong SPA** | Tránh persistence lâu dài vào storage | XSS vẫn có thể lạm dụng trong runtime |
| **Secure OS keystore trên mobile** | Bảo vệ token tốt hơn plain file | Thiết bị bị chiếm quyền vẫn có nguy cơ |
| **Server-side vault/token store** | Credential không đưa thẳng cho client | Cần RBAC, rotation và audit |

**Không có một cách lưu trữ tối ưu cho mọi kiến trúc**. Với browser web chứa dữ liệu nhạy cảm, **BFF hoặc server-managed session với cookie bảo vệ tốt** thường dễ quản lý token/revocation hơn việc để refresh token dài hạn trong JavaScript.

### HttpOnly không loại bỏ XSS

Attacker có XSS vẫn có thể **gửi request trong ngữ cảnh user**, kể cả khi không đọc được cookie. Bảo vệ cần gồm **input/output encoding, CSP khi phù hợp, giới hạn origin, CSRF controls, authorization và khả năng revoke**.

## 13. Session timeout: idle, absolute và reauthentication

Ba giới hạn thường cần thiết kế riêng:

| Giới hạn | Tính từ | Ý nghĩa |
|---|---|---|
| **Idle timeout** | Hoạt động hợp lệ gần nhất | Ngăn phiên bị bỏ quên tồn tại quá lâu |
| **Absolute timeout** | Mốc tạo session hoặc reauthentication theo policy | Ngăn giữ phiên vô hạn dù liên tục hoạt động |
| **Reauthentication timeout** | Mốc chứng minh danh tính/assurance gần nhất | Buộc xác thực lại trước hành động nhạy cảm |

### Ví dụ minh họa

- Session được tạo lúc **09:00**.
- Idle timeout: **15 phút**.
- Absolute lifetime: **8 giờ**.
- Reauthentication cho **payment.approve** khi auth_time quá cũ theo policy.

Nếu không có hoạt động hợp lệ từ 09:10 tới 09:26, phiên có thể hết idle dù absolute expiry chưa tới. Nếu liên tục sử dụng đến 17:01, phiên phải hết absolute lifetime dù lastActivity mới được cập nhật.

**Những số trên là ví dụ**, không phải cấu hình bắt buộc của mọi sản phẩm. Timeout nên dựa vào **mức bảo đảm, rủi ro action, khả năng sử dụng, chính sách nội bộ và tiêu chuẩn áp dụng**.

### Cẩn thận sliding expiration

Nếu mọi request tĩnh, polling hoặc keep-alive đều được tính là hoạt động hợp lệ, session có thể sống vô hạn mà user thực không tương tác. Phải định nghĩa **qualified activity** và giữ absolute timeout độc lập.

### Đồng hồ đáng tin

Tính thời hạn trên **server clock** với điều kiện clock skew thích hợp; không tin client tự gửi “lastActiveAt” để kéo dài phiên.

## 14. Login, reauthentication và step-up

### Login

User hoàn thành cơ chế xác thực (passwordless/MFA/SSO) và ứng dụng xác minh kết quả. Chỉ sau đó mới tạo hoặc nâng cấp session authenticated.

### Reauthentication

Khi phiên đã quá hạn về assurance hoặc có sự kiện bảo mật, hệ thống yêu cầu người dùng **xác thực lại** theo chính sách, không chỉ refresh cookie.

### Step-up

Một phiên đủ để đọc báo cáo nhưng không đủ để **export dữ liệu nhạy cảm** có thể cần step-up. Ví dụ:

~~~mermaid
flowchart TD
    R[Request: report.export] --> S{Session active?}
    S -->|Không| LOGIN[Login required]
    S -->|Có| A{Entitlement and resource valid?}
    A -->|Không| DENY[403 Deny]
    A -->|Có| M{MFA assurance and auth_time sufficient?}
    M -->|Không| STEP[Step-up / Reauthenticate]
    M -->|Có| POLICY[SoD + Data Policy + Limits]
    STEP --> M
    POLICY -->|Permit| DONE[Execute and audit]
    POLICY -->|Deny| DENY
~~~

### Security assurance và authorization độc lập

**Step-up thành công không cấp role mới**. Nếu user không có permission export, API vẫn Deny dù dùng security key. Nếu user có role export nhưng account đã Leaver, session cũng không thể Permit.

### Regenerate session sau privilege change

Đăng nhập hoặc nâng mức tin cậy có thể cần **rotate session ID** và cập nhật authentication context để giảm fixation/hijacking risk. Các token hay phiên liên quan cũng cần xử lý theo kiến trúc, không chỉ đổi cờ **isMfa=true** do client gửi.

## 15. Session fixation

**Session fixation** là tấn công trong đó attacker làm nạn nhân dùng một session ID đã biết trước khi đăng nhập; sau khi nạn nhân đăng nhập, attacker có thể lợi dụng cùng ID nếu ứng dụng **không đổi ID khi nâng cấp session**.

### Diễn biến

1. Attacker có một session ID vô danh.
2. Attacker khiến nạn nhân sử dụng ID đó qua cơ chế ứng dụng bị lỗi.
3. Nạn nhân đăng nhập thành công.
4. Ứng dụng giữ nguyên session ID từ trước login.
5. Attacker dùng ID đã biết để truy cập phiên authenticated.

### Biện pháp

- **Regenerate session ID** khi xác thực thành công hoặc tăng privilege.
- Không chấp nhận session ID qua URL/query khi có thể.
- Ngăn session ID do client tự chọn hoặc do URL parameter áp đặt.
- Cấu hình cookie **Secure, HttpOnly, SameSite, host-only** phù hợp.
- Hủy hoặc giảm privilege session vô danh sau login.
- Test phiên cũ không còn truy cập được sau regeneration.

**Chỉ mã hóa lưu session state ở database không giải quyết fixation** nếu cùng identifier vẫn có thể được attacker biết và dùng.

## 16. Session hijacking và replay

**Session hijacking** xảy ra khi attacker chiếm được session ID/token hoặc ngữ cảnh cần thiết để mạo danh user.

### Đường tấn công phổ biến

- Cookie/token lộ qua XSS hoặc log.
- Truyền session trên HTTP không được bảo vệ.
- Extension hoặc thiết bị bị xâm nhập đọc browser profile.
- Session ID trong URL/referrer.
- Token trong CI artifact, screenshot hoặc error report.
- Cookie được gửi tới subdomain không đáng tin.
- Thiếu timeout hoặc không revoke sau password reset/Leaver.
- Token bearer bị đánh cắp và replay từ môi trường khác.

### Kiểm soát theo lớp

1. **TLS/HTTPS**, HSTS khi phù hợp và không chấp nhận downgrade.
2. Session ID dùng CSPRNG, đủ entropy và không log.
3. **HttpOnly/Secure/SameSite** cùng origin isolation.
4. Giới hạn TTL và rotate session theo sự kiện.
5. Quản lý concurrent devices, risk signals và cảnh báo.
6. Chặn XSS/CSRF và injection.
7. Revoke server-side và cập nhật authorization version.
8. Sender-constrained token/PoP trong những use case hỗ trợ.
9. Theo dõi hành vi bất thường và session anomaly.
10. Negative test sau revoke để chứng minh quyền không còn dùng được.

**Ràng buộc tuyệt đối session vào IP có thể gây lỗi với mobile/VPN/NAT và không tự chống được mọi attacker**. Nên dùng risk-based signals có kiểm soát thay vì coi IP thay đổi luôn là tấn công.

## 17. CSRF và vai trò của SameSite

**Cross-Site Request Forgery (CSRF)** xảy ra khi site độc hại khiến browser đã đăng nhập gửi request ngoài ý muốn tới ứng dụng đích, có thể tự đính kèm cookie.

### Ví dụ nguy cơ

User đang đăng nhập Finance Portal. Một trang độc hại cố khiến browser gửi request **POST /payments/approve**. Nếu ứng dụng chỉ kiểm session cookie mà không có CSRF guard, hành động có thể được thực thi nếu browser gửi cookie.

### Biện pháp

- Dùng **anti-CSRF token** hoặc cơ chế xác minh request phù hợp framework.
- Xác minh **Origin/Referer** theo chính sách với request thay đổi trạng thái.
- **SameSite=Lax/Strict** khi phù hợp và test luồng SSO.
- Không cho **GET** thay đổi trạng thái nghiệp vụ.
- Yêu cầu **step-up** cho action đặc quyền.
- Kiểm **permission, object ownership và SoD** tại server.
- Tách endpoint chính sách nhạy cảm khỏi cross-origin requests không cần thiết.

**SameSite không thay thế CSRF protection**. Các subdomain trong cùng site, các ngoại lệ điều hướng, browser behavior và luồng federation cần được xem xét. Nếu bắt buộc dùng **SameSite=None**, cookie phải Secure và phòng vệ CSRF càng phải rõ.

### CSRF khác XSS

- **CSRF:** browser bị lợi dụng gửi request trong phiên hợp lệ.
- **XSS:** mã không đáng tin chạy trong origin, có thể đọc dữ liệu mà script được phép và gửi action thay user.

Hai loại thường cần **phòng vệ kết hợp**, không thể chữa hết bằng chỉ một cookie flag.

## 18. XSS và bảo vệ session

**Cross-Site Scripting (XSS)** có thể cho attacker chạy JavaScript trong trang ứng dụng, lạm dụng phiên của user.

### Tại sao HttpOnly vẫn hữu ích?

HttpOnly ngăn JavaScript truy cập giá trị cookie trực tiếp theo hành vi browser. Điều này **giảm nguy cơ đánh cắp raw cookie bằng XSS**, nhưng attacker vẫn có thể:

- Gửi request same-origin qua fetch với cookie được browser đính kèm.
- Đọc nội dung trang mà JavaScript được phép.
- Lợi dụng UI để kích hoạt action.
- Thu thập dữ liệu không được bảo vệ bởi authorization.
- Thao túng form hoặc thay nội dung người dùng thấy.

### Kiểm soát quan trọng

- Encode output đúng ngữ cảnh HTML/JS/URL.
- Sanitization cho rich HTML theo thư viện đáng tin.
- Content Security Policy phù hợp và hạn chế inline script khi có thể.
- Hạn chế third-party scripts, dependency integrity và browser permissions.
- Không lưu refresh token dài hạn trong nơi JS có thể đọc khi kiến trúc không cần.
- Sensitive action reauthentication, transaction authorization và least privilege.
- Có cơ chế thu hồi session nếu nghi bị chiếm đoạt.

**Không coi SameSite là phòng chống XSS**, và không coi HttpOnly là đủ để chặn mọi lạm dụng trong một origin bị xâm nhập.

## 19. Session và IdP/SSO: hai phiên có thể sống độc lập

Trong **Single Sign-On (SSO)**, IdP và từng ứng dụng (Relying Party/Service Provider) có thể quản lý những phiên khác nhau.

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant APP1 as Finance Portal
    participant IDP as IdP
    participant APP2 as CRM
    U->>APP1: Truy cập Finance Portal
    APP1-->>U: Redirect đến IdP
    U->>IDP: Authenticate / existing IdP session
    IDP-->>U: Login success / federation response
    U->>APP1: Federation response validated
    APP1-->>U: App1 local session cookie
    U->>APP2: Truy cập CRM
    APP2-->>U: Redirect tới IdP
    U->>IDP: Existing IdP SSO session
    IDP-->>U: Federation response
    U->>APP2: Federation response validated
    APP2-->>U: App2 local session cookie
~~~

### Điều dễ nhầm

- Logout **Finance Portal** có thể chỉ hủy **local session** của Finance.
- IdP session vẫn còn nên lần mở Finance tiếp theo có thể **SSO lại** nếu policy cho phép.
- Logout IdP không tự đảm bảo mọi ứng dụng đã hủy local sessions.
- Mỗi SP có thể có **absolute/idle timeout khác IdP**.
- SaaS có thể giữ session hoặc API key độc lập với federation.
- **IdP session còn ACTIVE** không tự chứng minh user còn quyền truy cập ứng dụng.

### SSO cần rõ ownership

Khi thiết kế logout hoặc Leaver, phải liệt kê **IdP, RPs/SPs, PAM, token issuer và local apps**. Không giả định một sự kiện ở một thành phần đã đồng bộ ngay lập tức tới toàn bộ session.

## 20. OIDC session, ID token và session identifiers

**OpenID Connect (OIDC)** xây trên OAuth 2.0 để hỗ trợ đăng nhập liên kết. Một Relying Party cần xác minh **authorization code, ID token và các tham số bảo vệ** theo flow đang dùng trước khi tạo local session.

### Những giá trị liên quan

| Thành phần | Vai trò |
|---|---|
| **ID token** | Khẳng định xác thực từ OpenID Provider tới client |
| **iss/sub/aud** | Định danh issuer, user và client nhận ID token |
| **auth_time** | Thời điểm xác thực khi được cung cấp/yêu cầu theo giao thức |
| **acr/amr** | Claims về ngữ cảnh/phương thức xác thực khi có |
| **sid** | Session identifier của OP trong một số cơ chế logout |
| **state/nonce** | Bảo vệ flow OIDC theo yêu cầu tương ứng |
| **Authorization code + PKCE** | Hạn chế đánh cắp/đổi code trái phép |
| **RP local session** | Phiên do ứng dụng tạo sau khi validate OIDC response |

### Một điều không nên làm

Không sử dụng **ID token như session cookie duy nhất vô hạn** hoặc gửi ID token trực tiếp làm API credential chỉ vì nó cũng là JWT. ID token có audience/mục đích dành cho **client**, còn API phải xác minh **OAuth access token và authorization riêng**.

### Phiên OIDC có thể được tái tạo

Nếu user logout local RP nhưng OP session vẫn hợp lệ, RP có thể được OIDC login trở lại tùy cấu hình. Muốn **global logout**, cần phối hợp các cơ chế OIDC logout mà OP/RP hỗ trợ và kiểm kết quả, không đơn thuần xóa một cookie.

## 21. Session và OAuth access/refresh token

OAuth dùng token để ủy quyền truy cập API; token liên quan nhưng **không đồng nhất** với browser session.

| Đối tượng | Nơi sử dụng | Thời hạn và thu hồi |
|---|---|---|
| **Browser session cookie** | Browser ↔ web application/BFF | Server session TTL hoặc signed cookie policy |
| **OAuth access token** | Client ↔ Resource Server | exp, audience, scope; revocation/introspection tùy kiến trúc |
| **OAuth refresh token** | Client ↔ Authorization Server | Xin access token mới, chính sách rotation/revocation |
| **OIDC ID token** | OP ↔ RP/client | Chứng minh authentication event, không phải API bearer cho mọi resource |
| **PAM/JIT grant** | Broker/target | Activation window, expiry, forced revoke |
| **Session token của SaaS** | SaaS/browser/app | Chính sách local riêng |

### Refresh token rotation

Với client phù hợp, authorization server có thể cấp **refresh token mới** và vô hiệu refresh token cũ trong mỗi lần dùng. Phát hiện reuse của token cũ có thể giúp nhận diện **theft/replay** và thu hồi cả token family theo policy.

**Refresh token rotation không đảm bảo vô hiệu ngay mọi access token đã phát**. Resource server phải có cơ chế phù hợp để từ chối action sau revoke hoặc chờ exp nếu rủi ro cho phép.

### Bearer và sender-constrained tokens

**Bearer token** thường có thể được sử dụng bởi bất kỳ ai nắm giữ nó trong phạm vi/TTL. Những cơ chế như **DPoP hoặc mTLS sender-constrained token** có thể ràng buộc token với khóa/endpoint được xác minh trong điều kiện triển khai tương ứng.

Chúng **giảm một số rủi ro replay**, nhưng không thay thế kiểm quyền trên resource hoặc cơ chế Leaver.

## 22. Logout: local, IdP và federated logout

**Logout** có thể có nhiều phạm vi:

| Loại | Mục tiêu | Không tự bảo đảm |
|---|---|---|
| **Local application logout** | Hủy phiên hiện tại của app | IdP/ứng dụng khác cũng logout |
| **All sessions logout** | Hủy mọi phiên của chủ thể trong ứng dụng | Token cấp bởi AS khác bị revoke |
| **IdP logout** | Chấm dứt OP/IdP session | Mọi RP local session bị hủy |
| **OIDC RP-initiated logout** | RP yêu cầu OP xử lý logout | Tất cả downstream RP tuân thủ hoàn toàn |
| **OIDC front-channel logout** | OP thông báo logout qua browser | Chạy được khi browser/network bị giới hạn |
| **OIDC back-channel logout** | OP gửi logout token trực tiếp tới RP endpoint | RP không triển khai vẫn không được đóng |
| **SAML Single Logout** | Hệ sinh thái SAML thông báo logout | Tất cả SP đều phản hồi thành công |
| **PAM session termination** | Chấm dứt privileged session | User mất mọi role khác hoặc API key |

**Không có “logout toàn cầu” tự động hiệu quả cho mọi hệ thống** nếu thiếu tích hợp và test từng RP/SP/target.

### Ví dụ local logout

~~~http
POST /logout HTTP/1.1
Host: finance.example.org
Cookie: __Host-session=opaque-session-id
X-CSRF-Token: example-csrf-protection
~~~

Server thực hiện:

1. Xác minh request và scope phiên hiện tại.
2. Vô hiệu **session ID trong store** hoặc cơ chế tương đương.
3. Clear cookie với thuộc tính khớp.
4. Thu hồi token/refresh token liên quan nếu policy và capability yêu cầu.
5. Ghi audit logout mà không log credential.

~~~http
HTTP/1.1 204 No Content
Set-Cookie: __Host-session=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax
Cache-Control: no-store
~~~

**Clear cookie chỉ là thao tác phía browser.** Kết quả an toàn cần server từ chối session ID cũ nếu attacker đã lưu một bản sao.

## 23. Session và SCIM provisioning: hai trách nhiệm riêng

**SCIM 2.0** thường dùng để đồng bộ **User/Group** giữa IAM/IdP và ứng dụng. Khi user Leaver, IAM có thể gửi **active=false**, xóa membership hoặc gọi API thích hợp.

### SCIM có thể làm gì?

- Create/Update/Deactivate User theo khả năng provider.
- Thêm/gỡ membership qua **Group.members** khi SP hỗ trợ.
- Đồng bộ dữ liệu account/role mapping.
- Cung cấp dữ liệu đối soát về account hoặc group ở target.

### SCIM không mặc nhiên làm gì?

- Đóng mọi browser session ở SP.
- Thu hồi toàn bộ OAuth access token còn hạn.
- Xóa PAT/API key/local credentials.
- Ngắt mọi SSH/VPN/PAM session.
- Ngăn một ứng dụng chỉ dựa vào JWT stale claims tiếp tục Permit.
- Thực thi mọi object-level RBAC/ABAC condition trong API.

**Deprovisioning và session termination phải phối hợp**, không thể coi HTTP 200 của SCIM là bằng chứng không còn truy cập.

### Một event có thể cần nhiều tác vụ

~~~mermaid
flowchart TD
    HR[HRIS: Leaver effectiveAt] --> IAM[IAM / IGA]
    IAM --> IDP[Disable login, revoke IdP sessions]
    IAM --> SCIM[SCIM/API: deactivate user, remove groups]
    IAM --> AS[Revoke refresh tokens / token families]
    IAM --> PAM[Terminate privileged sessions]
    IAM --> APP[Application local-session revoke]
    IAM --> AUDIT[Audit and Reconciliation]
    IDP --> AUDIT
    SCIM --> AUDIT
    AS --> AUDIT
    PAM --> AUDIT
    APP --> AUDIT
    AUDIT --> CHECK{Observed access denied?}
    CHECK -->|No| REM[Remediation / escalation]
    CHECK -->|Yes| DONE[Verified within coverage]
~~~

## 24. Authorization của từng request không được dựa vào session ID một mình

Một session có thể được xác thực là user Lan, nhưng **authorization** phải kiểm:

1. Subject và relationship còn ACTIVE?
2. Session còn valid, đáp ứng MFA/reauthentication policy?
3. Action đã được cho phép qua RBAC/ABAC/PBAC?
4. Resource thuộc tenant/department/project được phép?
5. Có **SoD conflict** hoặc dynamic rule cấm action này?
6. Entitlement vừa bị Revoke/Mover/Leaver có đang stale trong cache?
7. Access grant/JIT activation còn thời hạn?
8. Resource classification, amount limit và context còn phù hợp?
9. API có kiểm **object-level permission** chứ không chỉ endpoint chung?
10. Kết quả được audit đúng user/session/action/resource?

~~~text
function authorizeRequest(sessionId, action, resourceId):
    session = loadSessionByOpaqueId(sessionId)

    if session is absent or revoked or expired:
        return UNAUTHENTICATED

    identity = loadAuthoritativeIdentity(session.subjectId)
    relationship = loadCurrentRelationship(session.relationshipId)

    if identity.disabled or relationship.notActive:
        revokeSession(session)
        return UNAUTHENTICATED

    resource = loadTrustedResource(resourceId)
    effective = resolveCurrentEffectivePermissions(identity)

    if not matchesTenantAndScope(identity, resource):
        return FORBIDDEN

    if not permits(effective, action, resource):
        return FORBIDDEN

    if not meetsSessionAssurance(session, action):
        return REAUTHENTICATION_REQUIRED

    if violatesDynamicSoD(identity, action, resource):
        return FORBIDDEN

    return PERMIT
~~~

Đây là **giả mã khái niệm**, không thay thế bộ lọc bảo mật/framework production. Đường xử lý account bị vô hiệu có thể trả 401 hoặc phản hồi khác theo kiến trúc; quan trọng là **không Permit** khi policy không cho phép.

### Cache quyền phải có chiến lược invalidation

Nếu quyền hiện hành được cache trong session, phải có **TTL, version hoặc invalidation event** đủ nhanh theo rủi ro. Không để một phiên admin còn quyền đặc biệt chỉ vì backend không kiểm quyền mới.

## 25. Session trong Joiner lifecycle

**Joiner** là người mới được xác minh, tạo identity, account và quyền baseline.

### Quy trình liên quan session

1. HRIS/contract source ghi nhận **personId, relationshipId, effectiveAt**.
2. Identity proofing/enrollment xác minh người và authenticator.
3. IdP/SSO được cấu hình đúng account; MFA theo policy.
4. IAM cấp **birthright access** và quyền riêng sau approval nếu cần.
5. Chỉ cho phép session authenticated theo thời điểm hiệu lực phù hợp.
6. Mỗi app tạo local session khi federation response hợp lệ.
7. API kiểm RBAC/ABAC theo resource và scope.
8. Ghi session creation, device/risk context và audit access.

### Trước ngày bắt đầu

Một account có thể được chuẩn bị trước effectiveAt, nhưng **không được mặc nhiên tạo session có khả năng truy cập production sớm** nếu chính sách cấm. Cần phân biệt **account prepared** với **identity eligible to authenticate/use resource**.

### Ví dụ

Lan bắt đầu làm việc ngày 01/12. Ngày 28/11 HRIS đã tạo account, nhưng Finance Portal chỉ cho vào tài liệu onboarding được duyệt. Đến effectiveAt, quyền Finance Reader trở nên có hiệu lực theo policy; session cũng phải được đánh giá với trạng thái mới.

## 26. Session trong Mover lifecycle

**Mover** xảy ra khi user đổi department, role, manager, project, tenant hoặc quan hệ hợp đồng.

### Rủi ro

Lan đang đăng nhập Sales CRM và có cookie session. Lan chuyển sang Finance; IAM gỡ role Sales ở IdP, nhưng:

- CRM local session vẫn active.
- JWT/claim trong app được phát trước đó chứa role SALES_EXPORT.
- Cache permission chưa được cập nhật.
- Group local ở SaaS chưa được gỡ.
- PAM eligible grant cũ chưa revoke.

Nếu CRM chỉ dựa vào dữ liệu session cũ, Lan vẫn có thể export khách hàng.

### Kiểm soát cần thực hiện

1. Nhận Mover event cùng **source version/effectiveAt**.
2. Tính lại **desired entitlements**; thu hồi role/group cũ và áp quyền mới.
3. Xác định những phiên đang dùng quyền bị thu hồi.
4. **Invalidate hoặc re-evaluate session authorization context**; buộc reauth/step-up khi phù hợp.
5. Gỡ delegated grants/JIT/PAM privilege không còn căn cứ.
6. Đồng bộ target SCIM/API rồi đọc lại trạng thái.
7. Chặn action cũ ở resource server, kể cả token/session còn sống.
8. Ghi finding nếu còn quyền tồn dư.

### Một session có thể tiếp tục nhưng giảm quyền

Không phải mọi Mover đều cần logout toàn bộ apps. Nếu ứng dụng có cơ chế authorization luôn kiểm quyền hiện hành, session authenticated có thể tiếp tục trong khi action cũ bị Deny. Với thay đổi rủi ro cao, **buộc reauthentication hoặc session termination** có thể cần theo policy.

**Điểm phải bảo đảm là quyền hiệu lực**, không nhất thiết số session đang mở bằng 0 trong mọi Mover.

## 27. Session trong Leaver lifecycle

**Leaver** đòi hỏi cắt các đường truy cập không còn căn cứ kể từ effectiveAt hoặc sớm hơn trong trường hợp khẩn cấp.

### Những lớp phải xem

| Lớp | Rủi ro còn lại | Hành động |
|---|---|---|
| **HRIS / identity lifecycle** | Event đến muộn hoặc sai relationship | Source of truth, version, effectiveAt |
| **IdP** | IdP session/SSO còn active | Disable login, revoke IdP sessions |
| **Application session** | Local browser sessions ở SaaS | Session revocation/API hoặc runtime deny |
| **SCIM target** | User/group/entitlement vẫn tồn tại | Deactivate/remove, readback |
| **OAuth AS/RS** | Refresh token và access token còn dùng được | Revoke/deny/introspect theo khả năng |
| **PAM/JIT** | Privileged active grants và terminal sessions | Terminate, revoke eligibility/activation |
| **Local credentials** | PAT, API key, SSH key, VPN cert | Revoke/rotate và đối soát |
| **Cache/long-lived connections** | Claims/scope cũ hoặc WebSocket tiếp tục chạy | Invalidate, close/revalidate |
| **Audit** | Không biết quyền đã chặn thực sự chưa | Verified readback, negative tests |

### Tình huống Leaver khẩn cấp

- 16:00 HRIS phát Leaver hiệu lực ngay.
- 16:01 IdP disable user.
- 16:03 CRM session cũ vẫn có thể gọi API bằng session cookie.
- 16:04 Gateway/CRM chưa nhận revocation hoặc vẫn tin role cache.

**Leaver chưa hoàn tất về mặt access revocation**. Phải xử lý CRM session/authorization và đối soát, không kết luận “xong” chỉ từ IdP status.

### Session store và access token phải được phân biệt

Một server-side session có thể bị xóa tức thì ở store. Nhưng JWT access token được phát trước đó có thể tiếp tục được RS chấp nhận đến **exp** nếu không có cơ chế runtime state/revocation. Chính sách Leaver cần tính cả hai và chọn mức latency chấp nhận được.

## 28. Session trong Rejoiner và nhiều quan hệ

Một người quay lại tổ chức có thể dùng lại một identity lịch sử theo chính sách, nhưng thường có **relationship mới** với role và scope khác.

### Không tái sử dụng session cũ

- Session từ quan hệ đã kết thúc phải bị vô hiệu, không tự hồi sinh.
- Refresh token/SSO remember-me token cũ không được cấp lại quyền theo quan hệ mới nếu chưa xác minh.
- Role cũ và JIT eligibility cũ không tự được kích hoạt.
- Identity/account linking phải dùng **stable identifiers**, không chỉ email có thể tái sử dụng.
- MFA/reauthentication theo chính sách mới.
- Resource server kiểm relationship/version, không chỉ personId.

### Nhiều quan hệ đồng thời

Một người có thể có hai quan hệ hợp lệ riêng. Khi một relationship kết thúc, hệ thống phải thu hồi **quyền phát sinh từ quan hệ đó**, nhưng không tự xóa những quyền thật sự còn hợp lệ của quan hệ khác nếu policy cho phép.

Đối với session, nên xác định rõ **đang hoạt động trong ngữ cảnh quan hệ/tenant nào**. Một session chỉ mang personId mà không có phân biệt scope có thể tạo nhầm lẫn quyền giữa contractor/employee hoặc giữa các tenant.

## 29. Privileged session, PAM và Just-in-time access

**Privileged Access Management (PAM)** và **Just-in-time (JIT)** thường cung cấp cơ chế kiểm soát phiên đặc quyền.

### Những đối tượng cần phân biệt

- **Eligible role:** người có quyền xin kích hoạt.
- **Active grant:** quyền đã kích hoạt trong cửa sổ thời gian.
- **Privileged session:** phiên đang dùng quyền cao qua SSH, RDP, database hoặc console.
- **Authentication session:** user đã xác thực với PAM/IdP.
- **Workload or API token:** credential phát trong lúc grant đang active.

Một user có thể vẫn có session thường ở IdP nhưng **không còn quyền admin** khi JIT grant đã hết.

### Quy trình JIT minh họa

~~~mermaid
flowchart TD
    REQ[User requests privileged access] --> EL{Eligible and business need?}
    EL -->|No| DENY[Deny]
    EL -->|Yes| SOD{SoD, MFA, risk and approval}
    SOD -->|Fail| DENY
    SOD -->|Pass| ACT[Activate time-bound grant]
    ACT --> SESSION[Privileged session brokered/recorded]
    SESSION --> EXP[Expiry / Emergency revoke / Leaver]
    EXP --> TERM[Terminate session and revoke grant]
    TERM --> VERIFY[Verify target no longer permits privileged action]
~~~

### Mục tiêu an toàn

- Step-up gần thời điểm activation.
- Không tạo standing admin chỉ để tránh approval.
- Giới hạn **action, resource và TTL**.
- Log/record session nhạy cảm với chính sách riêng tư phù hợp.
- Có khả năng **kill session** và revoke grant khi incident/Leaver.
- Xử lý token/credential được sinh từ session đặc quyền.
- Readback và negative tests sau expiry.

**Đóng cửa sổ JIT không đủ nếu terminal session hoặc token đã phát vẫn còn thực thi action**.

## 30. Concurrent sessions, device sessions và Remember me

Người dùng có thể có nhiều phiên trên laptop, điện thoại và browser.

### Những lựa chọn chính sách

| Chính sách | Lợi ích | Chi phí/rủi ro |
|---|---|---|
| **Cho nhiều session** | Trải nghiệm đa thiết bị | Nhiều đường cần revoke |
| **Giới hạn số session đồng thời** | Giảm số session tồn tại | Có thể làm gián đoạn user hợp lệ |
| **Logout all devices** | Phản ứng khi account compromise | Cần có registry và coverage |
| **Device-aware session** | Theo dõi/khoanh vùng thiết bị | Device ID có thể bị giả nếu chỉ client tự khai |
| **Remember me** | Giảm login lặp | Long-lived credential cần bảo vệ/rotation |
| **Risk-based reauthentication** | Tăng kiểm soát khi anomalous | False positives và UX |
| **Privileged single session** | Giảm đặc quyền đồng thời | Cần áp đúng loại access |

### Remember me không phải session vô hạn

Một “remember this device” có thể là một token/cookie khác với session thông thường. Nó phải có **thời hạn, rotation, revoke, device verification và điều kiện reauthentication**. Không nên dùng remember-me để tự nâng phiên thành MFA-high-assurance bất cứ lúc nào.

### Session inventory

User/admin có thể cần xem danh sách phiên, thời điểm tạo, thiết bị, approximate location hoặc recent activity; dữ liệu này phải được trình bày có trách nhiệm, không lộ raw session identifiers, và chỉ người có thẩm quyền được revoke.

## 31. Session management trong kiến trúc phân tán

Một hệ thống production thường có nhiều application instances và nhiều zone.

### Kiến trúc tham khảo

~~~mermaid
flowchart LR
    B[Browser] --> LB[Load Balancer]
    LB --> A1[App Instance A]
    LB --> A2[App Instance B]
    A1 --> REDIS[(Session Store)]
    A2 --> REDIS
    A1 --> PDP[Policy / Identity State]
    A2 --> PDP
    HR[HRIS / IAM Event] --> INV[Session Revocation Consumer]
    INV --> REDIS
    INV --> PDP
    A1 --> AUDIT[Audit/Telemetry]
    A2 --> AUDIT
~~~

### Các yêu cầu thiết kế

1. Session ID phải được lookup nhất quán giữa nhiều instances.
2. Store có TTL, encryption in transit và access control phù hợp.
3. Không lưu trực tiếp sensitive secrets khi không cần.
4. Thao tác revoke phải có **tính nhất quán và trạng thái quan sát được**.
5. Không để một node dùng **stale local cache** quá lâu khi quyền bị thu hồi.
6. Chống session ID collision, enumeration và session fixation.
7. Cấu hình dự phòng cho store failure theo mức rủi ro.
8. Session data schema và encryption key rotation cần kế hoạch migration.
9. Metrics và logs đủ để phân tích sự cố mà không lộ bearer secret.
10. Khi triển khai đa region, cần định nghĩa **độ trễ đồng bộ revocation**.

### Khi Session Store bị lỗi

Một ứng dụng không nên tự chuyển sang **Permit-all** chỉ vì không tra được session store. Đối với action nhạy cảm, **fail-closed** thường là cần thiết; với những trang công khai có thể xử lý riêng. Phương án degrade phải được thiết kế, test và phù hợp mục tiêu availability.

## 32. Concurrency, eventual consistency và session stale

Trong IAM, dữ liệu tới từ nhiều hệ thống và có thể không đồng bộ tức thì.

### Một race condition điển hình

1. 10:00 người dùng Mover, quyền SALES_EXPORT được thu hồi.
2. 10:01 session service đánh dấu phiên cần revalidate.
3. 10:02 một request dùng session cache cũ vẫn gửi report.export.
4. 10:03 app instance B chưa nhận sự kiện invalidation.
5. 10:04 app trả dữ liệu trái policy nếu không kiểm quyền hiện hành.

### Cơ chế giảm rủi ro

- **Authorization version / session generation** gắn với subject/relationship.
- Kiểm version tại request hoặc ranh giới action nhạy cảm.
- Cache TTL phù hợp mức rủi ro và event invalidation.
- **Idempotent revoke** và cơ chế deduplication.
- Source event có **version/fencing**, tránh event cũ mở lại phiên.
- Revalidation ngay trước privilege escalation.
- Khi timeout store, không tự coi “chưa thấy revoke” là Permit nếu policy yêu cầu hard deny.
- Theo dõi **revocation latency**, chứ không chỉ job đã nhận event.

### Stale login response

Một OIDC login hoàn tất sau khi HRIS đã phát Leaver. Nếu ứng dụng chỉ kiểm ID token ở lúc login mà không kiểm trạng thái identity hiện hành, nó có thể tạo session mới cho người đã nghỉ.

**Chính sách cần chặn tạo session mới dựa trên account/relationship đã không còn hợp lệ**, kể cả request đăng nhập bắt đầu trước sự kiện Leaver.

## 33. WebSocket, SSE và long-lived connections

Không phải mọi session đều đi qua các HTTP request ngắn.

### WebSocket

Sau khi handshake, kết nối có thể tồn tại nhiều giờ. Nếu ứng dụng chỉ kiểm cookie/session lúc kết nối và không kiểm lại, một user Leaver vẫn có thể tiếp tục gửi action qua kết nối mở.

### Server-Sent Events (SSE)

SSE là kết nối stream dài từ server tới client. Dù endpoint ban đầu được kiểm, luồng dữ liệu có thể tiếp tục sau khi entitlement đổi nếu không có cơ chế đóng/revalidate.

### SSH/RDP/database connections

Nhiều phiên remote hoặc kết nối database có authorization tại thời điểm tạo phiên, nhưng không nhất thiết được ngắt khi IdP account bị disable.

### Những biện pháp cần thiết

1. Gắn connection với **sessionId/subjectId/relationshipId** có thể truy vết.
2. Có **idle/absolute limits** hoặc heartbeat/revalidation phù hợp.
3. Đóng connection trên **logout, Leaver, JIT expiry hoặc security incident** khi policy yêu cầu.
4. Kiểm quyền **mỗi action nhạy cảm**, không chỉ handshake.
5. Kiểm token refresh và role changes.
6. Không coi **network connection còn sống** là bằng chứng entitlement còn hợp lệ.
7. Ghi log connection terminated/revoked và đối soát khi cần.

## 34. Session audit và bảo vệ dữ liệu cá nhân

Một hệ thống audit tốt có thể trả lời:

> Ai đã tạo phiên, bằng cách nào, ở ứng dụng nào, dùng phiên để thực hiện action gì, phiên hết hạn hoặc bị thu hồi khi nào, và sau thời điểm đó còn request nào được Permit không?

### Event hữu ích

- **AuthenticationSucceeded/Failed**.
- **SessionCreated**.
- **SessionRotated**.
- **SessionRefreshed/ActivityUpdated**.
- **ReauthenticationRequired/Completed**.
- **StepUpSucceeded/Failed**.
- **PrivilegedGrantActivated**.
- **SessionRevoked/Expired**.
- **AllSessionsRevoked**.
- **FederatedLogoutReceived**.
- **AccessDeniedAfterRevoke**.
- **StaleSessionRejected**.
- **LongLivedConnectionTerminated**.
- **SessionReconciliationFinding**.

### Audit record minh họa

~~~json
{
  "eventId": "session-evt-20261123-081",
  "eventType": "SessionRevoked",
  "subjectId": "person-2046",
  "relationshipId": "employment-2046-v2",
  "applicationId": "finance-portal",
  "sessionReference": "hashed-or-random-audit-ref",
  "reasonCode": "LEAVER_EFFECTIVE",
  "sourceEventId": "hris-event-8192",
  "sourceVersion": 24,
  "revokedAt": "2026-11-23T16:00:04+07:00",
  "policyVersion": "session-policy-v7",
  "correlationId": "corr-session-889"
}
~~~

Đây là schema minh họa, không phải chuẩn SCIM/OIDC. **sessionReference dùng cho audit không được cho phép đăng nhập hoặc lookup trái phép**; tránh log raw cookie, access/refresh token, private key hoặc password.

### Quyền riêng tư

- Thu thập **chỉ dữ liệu cần thiết** để bảo mật và vận hành.
- Hạn chế người được xem session/device/IP metadata.
- Định nghĩa retention theo chính sách và nghĩa vụ áp dụng.
- Tránh dùng lịch sử session cho mục đích ngoài phạm vi đã được cho phép.
- Phân biệt **security signal** với suy đoán định danh người dùng từ IP hoặc thiết bị.
- Bảo vệ log chống sửa trái phép và tránh leak trong traces.

## 35. Chỉ số và cảnh báo session management

| Metric | Mục đích | Điều cần tránh suy diễn |
|---|---|---|
| **Active sessions by application** | Biết phạm vi các phiên đang sống | Active session không đồng nghĩa active entitlement |
| **Session creation rate** | Phát hiện login anomaly | Có thể tăng do traffic hợp lệ |
| **Idle/absolute expiration counts** | Kiểm timeout hoạt động | Nhiều expire không tự chứng minh an toàn |
| **Session fixation prevention rate** | Theo dõi ID rotation/login security | Phải kiểm old ID không còn dùng được |
| **Concurrent sessions per user** | Phát hiện dùng quá nhiều thiết bị | Có thể hợp lệ cho on-call |
| **Step-up completion/failure** | Đánh giá bảo mật và UX | Không đồng nghĩa granting permission |
| **Session revocation latency** | Từ JML/incident đến local sessions không usable | Cần đo ở target, không chỉ queue |
| **Leaver residual sessions** | Session còn có thể dùng sau effectiveAt | Ưu tiên action-level validation |
| **Token replay/reuse alerts** | Phát hiện nghi token theft | Phải xác minh false positive |
| **Stale authz cache denies** | Quyền cũ bị từ chối sau Mover | Tốt nhưng cần kiểm coverage |
| **Federated logout success** | OP/RP có nhận/áp logout | Không kết luận mọi RP cùng logout |
| **Local session inventory coverage** | Bao nhiêu SaaS có API/session visibility | Có thể thiếu legacy apps |
| **Privileged session termination time** | PAM grant/session bị cắt khi expiry | Token/connection bên ngoài có thể còn |
| **WebSocket termination coverage** | Long-lived connections được revalidate | Kiểm mọi protocol sử dụng |
| **Unauthorized action after revoke** | Negative validation khi quyền đã cắt | Phải xử lý sự cố khi còn Permit |

**Không tối ưu chỉ theo “bao nhiêu phiên đã bị xóa”**. Mục tiêu an ninh là **không còn action trái chính sách được thực thi**, trong khi UX và availability được quản trị hợp lý.

## 36. Những lỗi thiết kế session phổ biến

| Sai lầm | Hệ quả | Khắc phục |
|---|---|---|
| **Session ID đoán được** | Session enumeration/hijacking | CSPRNG và đủ entropy |
| **Không rotate sau login** | Session fixation | Regenerate khi nâng cấp identity |
| **Đưa session ID vào URL** | Lộ qua logs/referrer | Cookie được bảo vệ |
| **Thiếu Secure/HttpOnly** | Rò rỉ cookie dễ hơn | Cookie flags + TLS |
| **Chỉ dựa SameSite** | CSRF vẫn có thể xảy ra | CSRF token/Origin policy |
| **Lưu refresh token trong localStorage** | XSS đánh cắp token | BFF/server storage hoặc thiết kế phù hợp |
| **Không có absolute timeout** | Sliding session sống quá lâu | Max lifetime độc lập |
| **Không phân biệt IdP và RP session** | Logout không hoàn chỉnh | Federated logout integration |
| **Chỉ disable IdP ở Leaver** | SaaS/API session tiếp tục | Multi-layer revoke/readback |
| **Tin JWT claim role cũ** | Mover vẫn dùng quyền cũ | State/version check, TTL phù hợp |
| **Không xử lý refresh token** | Client có thể xin token mới | AS revocation/rotation |
| **Không đóng WebSocket** | Action tiếp tục trên kết nối cũ | Connection lifecycle/revalidate |
| **MFA = admin Permit** | Vượt authorization | Kiểm action/resource/SoD |
| **Session trong RAM một node** | Mất phiên/inconsistent qua load balancing | Shared store hoặc kiến trúc đúng |
| **Permit khi session store lỗi** | Fail-open ngoài ý muốn | Fail-closed cho action nhạy cảm |
| **Trust cookie Domain quá rộng** | Subdomain attack/session confusion | Host-only cookie |
| **Logout chỉ xóa cookie** | Server session vẫn có thể dùng | Invalidate backend session |
| **Không map relationshipId** | Quyền từ quan hệ cũ sống sau Rejoiner | Scoped session context |
| **Log raw session cookie** | Lộ bearer secret vào observability | Redaction và audit reference riêng |
| **Đóng incident khi revocation job SUCCESS** | Quyền đích chưa cắt | Readback, negative action tests |

## 37. Kiểm thử session: chức năng, bảo mật và JML

| Test case | Tình huống | Kết quả mong đợi |
|---|---|---|
| **Login hợp lệ** | User ACTIVE, xác thực thành công | Tạo session mới đúng subject |
| **Login thất bại** | Credential/MFA sai | Không tạo authenticated session |
| **Session fixation** | ID vô danh bị attacker biết | ID đổi khi login; ID cũ vô hiệu |
| **Randomness** | Nhiều session được tạo | Không đoán/reuse được ID theo policy |
| **Idle expiry** | Không hoạt động sau ngưỡng | Session không còn usable |
| **Absolute expiry** | Request liên tục tới quá hạn | Session vẫn expire |
| **Reauth freshness** | Auth_time cũ khi action nhạy cảm | Reauthenticate/step-up |
| **Cookie flags** | Response Set-Cookie | Secure, HttpOnly, SameSite, Path đúng |
| **Host-only cookie** | __Host-session có Domain | Browser reject hoặc policy test fail |
| **CSRF** | Cross-site POST không có protection | Deny |
| **XSS** | Script injection cố đọc cookie | HttpOnly bảo vệ raw cookie; app cần phòng XSS |
| **Logout** | Session đã revoke | Cookie cũ không được server chấp nhận |
| **Logout all devices** | Hai phiên trên hai thiết bị | Tất cả phiên thuộc scope bị revoke |
| **IdP logout only** | RP giữ local session | Không giả định RP đã logout; test integration |
| **RP logout only** | OP session còn | Hành vi login lại theo policy, không báo global logout sai |
| **Refresh token reuse** | Token đã rotate được dùng lại | Phát hiện/xử lý theo AS policy |
| **Access token stale** | Role đã gỡ, JWT còn hạn | API Deny action trái policy |
| **Wrong audience** | Token dành API A gửi API B | Deny |
| **Wrong tenant** | User tenant A gọi object tenant B | Deny |
| **MFA success no permission** | User không có report.export | 403/Deny dù step-up thành công |
| **Mover** | Gỡ Sales role khi CRM session còn | Sales action bị Deny |
| **Leaver** | Account disabled trong khi session còn | Không cho tạo session mới/tiếp tục action |
| **Rejoiner** | Relationship mới, session cũ còn | Không hồi sinh phiên/role cũ |
| **PAM expiry** | Privileged grant hết hạn | Admin action bị Deny, session xử lý |
| **Long-lived socket** | Leaver trong lúc WebSocket active | Socket đóng/revalidate, action không Permit |
| **Multi-instance** | Request qua app node khác | Session state/expiry nhất quán |
| **Revocation event out of order** | Login event đến sau Leaver event | Version/fencing chặn regrant |
| **Session store outage** | Store không khả dụng | Không tự Permit action nhạy cảm |
| **Audit** | Session create/revoke | Truy vết đủ nhưng không lộ credential |
| **Reconciliation** | Local SaaS session chưa revoke | Finding OPEN cho tới khi chặn được |

### Các lớp test cần có

1. **Unit tests:** TTL, session state transitions, version checks.
2. **Cookie/browser tests:** flags, SameSite/SSO compatibility và cross-origin.
3. **Authentication tests:** login, MFA, reauth, risk changes.
4. **Authorization tests:** action/resource/tenant/SoD với session hợp lệ.
5. **Federation tests:** RP/OP sessions và supported logout protocols.
6. **Token tests:** access/refresh validity, replay, revocation.
7. **JML regression tests:** Joiner, Mover, Leaver, Rejoiner.
8. **Concurrency/failure injection:** session store outages, event reorder, race.
9. **Long-lived connection tests:** WebSocket, SSE, SSH/PAM.
10. **Audit/privacy tests:** event correlation không ghi raw secrets.

## 38. Runbook: lỗi session và sự cố chiếm đoạt phiên

### A. User bị đăng xuất quá sớm

1. Kiểm **idle/absolute TTL**, cookie Max-Age và server clock.
2. Kiểm load balancer/shared session store và node-specific caching.
3. Kiểm cookie Path/Domain/SameSite/Secure hoặc browser policy.
4. Kiểm IdP/RP login/logout và OIDC callback/nonce/state.
5. Kiểm session rotation hoặc account/risk signal có revoke hợp lệ.
6. Không sửa bằng cách tăng TTL vô hạn hoặc tắt session validation.

### B. User đăng xuất nhưng truy cập vẫn được

1. Xác định logout thuộc **app, IdP hay tất cả thiết bị**.
2. Kiểm backend session record đã invalidated chưa.
3. Kiểm RP/SaaS local sessions và global logout integration.
4. Kiểm access/refresh token, local PAT và cache.
5. Kiểm long-lived connections.
6. Thử action cũ bằng credential đã revoke theo môi trường kiểm soát.
7. Ghi finding khi còn đường Permit.

### C. Phát hiện session hijacking

1. Ưu tiên chặn action nhạy cảm và **revoke sessions** thuộc phạm vi.
2. Thu hồi/rotate refresh tokens và credentials liên quan khi cần.
3. Xác định thời điểm, user, ứng dụng, session audit reference.
4. Kiểm dấu hiệu XSS, cookie/token leak qua log, browser extension hoặc thiết bị.
5. Buộc reauthentication mạnh theo policy.
6. Kiểm các action đã thực hiện và dữ liệu bị truy cập.
7. Xử lý root cause, cập nhật detection/risk controls.
8. Không gửi raw session cookie trong incident ticket.

### D. Leaver vẫn còn session active

1. Lấy HRIS Leaver event, relationshipId, effectiveAt và version.
2. Kiểm IdP disable và khả năng tạo login/session mới.
3. Revoke local sessions theo từng app và token families tại AS.
4. Kiểm SaaS SCIM User/Group, PAM, SSH/VPN, PAT/API keys.
5. Đóng hoặc revalidate WebSocket/SSE và connection dài.
6. Chặn resource/action ở PEP/RS theo rủi ro.
7. Readback, negative tests và SLA revoke; không kết luận từ job status.
8. Giữ finding có owner tới khi effective access phù hợp policy.

### E. User vừa Mover và mất quyền cần thiết

1. Kiểm nguồn JML và desired roles của vị trí mới.
2. Xác định quyền bị gỡ do Mover là đúng hay sai.
3. Kiểm SCIM/API provisioning và authorization cache/sessionVersion.
4. Nếu quyền mới cần approval, thực hiện đúng Access request.
5. Không khôi phục Sales Admin cũ để chữa lỗi Finance Reader.
6. Sau thay đổi, test cả **new action Permit** và **old action Deny**.

## 39. Tình huống xuyên suốt: phiên làm việc của Lan

Giả sử doanh nghiệp dùng **HRIS, IdP có MFA, Finance Portal, CRM, IAM/IGA, SCIM** và một **PAM broker** cho quyền đặc biệt.

### Giai đoạn 1 — Joiner và phiên đầu tiên

HRIS tạo identity **person-2046**, relationshipId và effectiveAt cho Lan. Sau identity proofing và enrollment passkey/MFA, Lan đăng nhập IdP; Finance Portal xác minh OIDC login response và tạo **local session** có cookie Secure/HttpOnly/SameSite. Lan đọc báo cáo qua API, nơi hệ thống kiểm Finance Reader và tenant.

### Giai đoạn 2 — Phiên thường và quyền đặc biệt

Lan cần export dữ liệu nhạy cảm. Session thường chỉ đạt điều kiện đọc nên API yêu cầu **step-up**. Lan xác thực mạnh, song API vẫn kiểm **report.export entitlement** và dữ liệu thuộc dự án được phép. Khi Lan cần JIT export trong 30 phút, PAM/IGA kích hoạt grant có hạn; không biến cả browser session thành quyền export vô hạn.

### Giai đoạn 3 — Thay đổi thiết bị

Lan đăng nhập trên một thiết bị khác. Hệ thống tạo **session mới** với identity và device metadata riêng, đồng thời theo dõi concurrent sessions. Nếu Lan chọn “logout all devices”, backend cần revoke cả hai phiên ở Finance và các token có liên quan theo phạm vi được hỗ trợ.

### Giai đoạn 4 — Mover

Lan chuyển từ Sales sang Finance. HRIS phát Mover. CRM vẫn có local session và JWT chứa role SALES_EXPORT cũ. IAM gỡ role/group và CRM kiểm lại authorization version; request **customer.export** bị Deny. Finance Portal có thể giữ phiên authenticated nhưng chỉ Permit theo quyền mới, không cần tự động logout mọi dịch vụ nếu policy không yêu cầu.

### Giai đoạn 5 — Leaver

Lan nghỉ việc hiệu lực ngay. IdP chặn login mới, nhưng Finance Portal vẫn có cookie còn hạn. App nhận sự kiện revocation và server store vô hiệu session; authorization layer cũng kiểm lifecycle mới. OAuth refresh token bị xử lý tại AS, API ngừng cho phép token còn claim cũ theo chính sách. PAM chấm dứt privileged sessions. Một kết nối WebSocket lâu dài phải được đóng hoặc revalidate.

### Giai đoạn 6 — Rejoiner

Lan quay lại dưới quan hệ công việc mới. IAM có thể liên kết identity lịch sử nhưng không dùng lại session/token/approval đã bị thu hồi trước đây. App tạo session mới sau xác thực, quyền được tính từ role, relationship và policy hiện hành.

### Kết luận tình huống

**Session là cơ chế duy trì ngữ cảnh xác thực, không phải nguồn cấp quyền bất biến.** Một hệ thống an toàn phải quản lý đồng thời **phiên IdP, phiên ứng dụng, token API, credential ngoài SSO và quyền tại resource server**, đặc biệt khi Mover/Leaver.

## 40. Checklist thiết kế Session management an toàn

1. **Định nghĩa:** đã phân biệt session, cookie, ID token, access token và refresh token?
2. **Identity:** session gắn đúng subjectId, tenant và relationship/version khi cần?
3. **Creation:** chỉ tạo authenticated session sau khi validate login/federation result?
4. **Session ID:** dùng CSPRNG và độ ngẫu nhiên phù hợp?
5. **Fixation:** rotate session ID khi login/step-up hoặc thay đổi privilege?
6. **Cookie:** Secure, HttpOnly, SameSite, Path/Domain và __Host- được cấu hình đúng?
7. **Transport:** chỉ dùng TLS, không đưa raw session ID vào URL/log?
8. **Timeout:** có idle và absolute lifetime được thực thi tại server?
9. **Reauthentication:** action nhạy cảm có yêu cầu MFA/step-up phù hợp?
10. **Browser token storage:** đã đánh giá XSS/CSRF và BFF/server-side alternatives?
11. **CSRF:** cookie-authenticated state-changing APIs có phòng vệ thực tế?
12. **XSS:** có output encoding/CSP/script control phù hợp?
13. **Logout:** xóa cookie cùng hủy backend session, không chỉ một phía?
14. **Federated logout:** biết rõ IdP/RP nào hỗ trợ OIDC/SAML logout?
15. **Token revocation:** access/refresh token xử lý theo issuer và RS capability?
16. **RBAC/ABAC:** session hợp lệ vẫn phải kiểm quyền trên action/resource?
17. **SoD:** dynamic SoD và object ownership vẫn được enforce?
18. **Authz cache:** quyền cũ được invalidated/versioned sau Mover/Leaver?
19. **SCIM:** deactivate account/group không bị hiểu là toàn bộ session đã chết?
20. **JIT/PAM:** privileged session/grant kết thúc đúng expiry?
21. **Concurrent sessions:** có inventory, device-aware revoke và logout all devices khi cần?
22. **Remember me:** token riêng có TTL, rotation và revoke?
23. **Long-lived connections:** WebSocket/SSE/remote sessions được revalidate hoặc terminate?
24. **Distributed store:** nhiều instances có session state và TTL nhất quán?
25. **Failure mode:** store/IdP/PDP lỗi không tự Permit hành động nhạy cảm?
26. **JML Joiner:** không tạo phiên có quyền sản xuất trước effectiveAt nếu policy cấm?
27. **JML Mover:** role cũ bị Deny ngay cả khi session còn authenticated?
28. **JML Leaver:** revoke local sessions, IdP, refresh tokens, PAM và local creds?
29. **Rejoiner:** session và quyền thuộc relationship cũ không tự hồi sinh?
30. **Event version:** không cho event/login/refresh stale regrant sau Leaver?
31. **Audit:** ghi session creation/rotation/revoke/action với ref không phải credential?
32. **Privacy:** metadata IP/device/đăng nhập được thu thập và lưu tối thiểu?
33. **Monitoring:** đo session revocation latency và access denied after revoke?
34. **Tests:** có kiểm fixation, CSRF, XSS, JWT stale claims và replay?
35. **Coverage:** có inventory những SaaS/local apps không hỗ trợ global logout?
36. **Negative verification:** token/session cũ phải bị Deny tại các đường action quan trọng?
37. **Closure:** không đóng incident/JML chỉ vì “đã disable IdP” hoặc xóa cookie?

### Ghi nhớ

**Session là ngữ cảnh được duy trì để hệ thống nhận biết và kiểm soát chuỗi tương tác của một chủ thể đã xác thực.** Session có thể dựa trên **opaque ID + server store**, **cookie/token được bảo vệ** hoặc những mô hình đặc thù; quan trọng là **tạo đúng, bảo vệ, giới hạn thời gian, rotation, logout, reauthentication và revocation**. **Cookie không phải session ở server; session không phải access token; IdP session không phải mọi local application session; authentication không phải authorization.** Trong **IAM Identity Lifecycle**, thay đổi theo **Joiner–Mover–Leaver** phải được phản ánh vào **session, token, RBAC/ABAC, SCIM provisioning, PAM/JIT và resource server** để bảo đảm **không còn quyền truy cập tồn dư** khi căn cứ danh tính hoặc quyền đã chấm dứt.
