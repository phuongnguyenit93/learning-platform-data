# Session creation — Tạo phiên an toàn sau khi xác thực

> **Chương:** Session  
> **Chủ đề:** Session creation  
> **Phạm vi:** Bài học thuộc module SECURITY_AUTHENTICATION_FUNDAMENTALS, tìm hiểu xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này tập trung vào cách tạo phiên sau khi verifier xác thực thành công, gắn phiên với principal và authentication context, bảo vệ session identifier, chống session fixation và duy trì ranh giới tin cậy trong suốt vòng đời phiên.

## 1. Session là gì?

**Session (phiên)** là trạng thái tương tác mà server duy trì để nhận biết một client đã được xác thực trong những request tiếp theo. Sau khi người dùng hoàn tất đăng nhập, server có thể tạo một session và gửi cho client một **session identifier** (session ID) ngẫu nhiên. Client gửi lại ID này trong cookie hoặc cơ chế tương đương; server tra cứu session tương ứng rồi xác định principal và ngữ cảnh xác thực.

Ví dụ, Mai đăng nhập vào nền tảng học tập bằng passkey. Server kiểm tra chữ ký WebAuthn, challenge, origin và RP ID. Sau khi xác thực thành công, server tạo session mới gắn với account của Mai, thời điểm xác thực, phương thức đã dùng và các giới hạn của phiên. Trình duyệt nhận cookie chứa session ID. Ở request tiếp theo, server kiểm tra cookie, trạng thái session, account và quyền truy cập trước khi trả dữ liệu.

**Session không phải credential gốc.** Password, passkey hoặc certificate được dùng để chứng minh quyền kiểm soát authenticator. Session là trạng thái truy cập được phát hành sau kết quả xác thực. Nếu session ID bị đánh cắp, kẻ tấn công có thể sử dụng nó như một bearer credential trong phạm vi phiên mà không cần lặp lại toàn bộ quá trình đăng nhập.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt authentication, principal, session, session identifier và authorization.
2. Xác định thời điểm an toàn để tạo phiên và cách xử lý phiên tạm trước MFA.
3. Sinh session ID đủ ngẫu nhiên, bảo vệ ở client/server và chống session fixation.
4. Gắn session với account, tenant, thời điểm xác thực, phương thức và assurance context.
5. Thiết kế cookie, CSRF protection, idle timeout, absolute timeout và logout/revocation.
6. Quản lý session trong hệ thống nhiều instance, xử lý race condition và thay đổi trạng thái account.
7. Phân biệt server-side session với access token và refresh token.

## 2. Authentication, principal, session và authorization

Các khái niệm thường xuất hiện cạnh nhau nhưng trả lời các câu hỏi khác nhau:

| Khái niệm | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Authentication** | Bằng chứng nào đã được kiểm tra và kết quả ra sao? | Password hợp lệ; WebAuthn assertion hợp lệ; MFA hoàn tất. |
| **Account** | Tài khoản nội bộ nào được hệ thống quản lý? | Account ID nội bộ của Mai. |
| **Principal** | Chủ thể nào đang thực hiện request? | Account Mai trong tenant Alpha, cùng các thuộc tính tin cậy cần thiết. |
| **Session** | Server duy trì trạng thái truy cập nào cho principal? | Phiên S-opaque được tạo sau đăng nhập. |
| **Session ID** | Client dùng giá trị nào để tham chiếu phiên? | Cookie ngẫu nhiên, khó đoán, không mang dữ liệu profile. |
| **Authorization** | Principal có quyền làm hành động này trên tài nguyên này không? | Mai được xem bài học đã đăng ký nhưng không được sửa điểm người khác. |

Luồng khái niệm:

~~~text
Credential / authenticator
          |
          v
Authentication verifier
          |
          | kiểm tra thành công theo policy
          v
Principal + authentication context
          |
          | tạo session mới
          v
Session record <---- opaque session ID ----> Client
          |
          v
Mỗi request: kiểm tra session + trạng thái + authorization
~~~

Một session hợp lệ chỉ chứng minh server đang nhận diện một principal trong phạm vi phiên. Nó không tự cấp quyền trên mọi API hoặc mọi tenant. Mỗi request vẫn phải kiểm tra quyền của principal đối với action và resource cụ thể.

## 3. Khi nào được tạo session?

Server chỉ nên phát hành **phiên đã xác thực** sau khi hoàn tất toàn bộ các bước xác thực bắt buộc theo policy. Nếu hệ thống yêu cầu password + MFA, kiểm tra password thành công mới là bước đầu; chưa được tạo session có đầy đủ quyền trước khi yếu tố bổ sung thành công.

Có thể tồn tại một **pre-authentication transaction** hoặc phiên tạm để giữ trạng thái giữa các bước đăng nhập. Phiên tạm chỉ được phép truy cập các endpoint cần thiết cho đăng nhập/MFA, không được đọc dữ liệu người dùng hoặc gọi API nghiệp vụ như một phiên đã xác thực.

~~~mermaid
flowchart TD
    A["Client bắt đầu đăng nhập"] --> B["Server tạo giao dịch pre-auth"]
    B --> C["Xác minh yếu tố chính"]
    C --> D{"Yếu tố chính hợp lệ?"}
    D -- "Không" --> X["Từ chối / giới hạn thử"]
    D -- "Có" --> E{"Policy có yêu cầu MFA/step-up?"}
    E -- "Có" --> F["Xác minh yếu tố bổ sung"]
    F --> G{"MFA hợp lệ?"}
    G -- "Không" --> X
    G -- "Có" --> H["Tạo principal và authentication context"]
    E -- "Không" --> H
    H --> I["Hủy hoặc nâng cấp pre-auth state"]
    I --> J["Sinh session ID mới"]
    J --> K["Lưu session và phát cookie"]
    K --> L["Request tiếp theo kiểm tra session + quyền"]
~~~

### Phiên tạm không được trở thành đường vòng

Nếu client gửi một cờ như **mfaCompleted=true**, server không được tin cờ đó. Trạng thái MFA phải đến từ verifier và giao dịch được lưu ở server. Không cho endpoint nghiệp vụ chấp nhận pre-auth session chỉ vì nó có một cookie hợp lệ.

Khi đăng nhập thất bại, hết hạn hoặc người dùng hủy, server cần hủy giao dịch tạm và không để trạng thái pending được sử dụng về sau. Khi MFA thành công, tạo session mới hoặc nâng cấp theo một quy trình rotation an toàn; không tiếp tục dùng một session ID mà attacker có thể đã biết trước khi xác thực.

## 4. Session identifier: opaque, ngẫu nhiên và không mang dữ liệu

Session ID thường là một **bearer secret**. Bất kỳ bên nào có ID hợp lệ đều có thể tham chiếu session trong giới hạn hệ thống, vì vậy ID cần:

- Được sinh bằng CSPRNG (cryptographically secure pseudorandom number generator).
- Có entropy đủ cao; 128 bit ngẫu nhiên là mức tối thiểu thường được dùng làm tham chiếu, còn 256 bit giúp có biên an toàn rộng.
- Không dự đoán được từ account ID, email, timestamp, địa chỉ IP, counter hoặc dữ liệu profile.
- Không tái sử dụng sau logout, expiry hoặc revoke.
- Không chứa role, tenant, email, account ID hoặc thông tin nhạy cảm có thể đọc trực tiếp.
- Được truyền qua kênh bảo vệ, thường là HTTPS và cookie có thuộc tính phù hợp.

Ví dụ tạo ID trong Java:

~~~java
byte[] random = new byte[32]; // 256 bit
secureRandom.nextBytes(random);

String sessionId = Base64.getUrlEncoder()
    .withoutPadding()
    .encodeToString(random);
~~~

Đây là ví dụ minh họa; dùng CSPRNG chuẩn của nền tảng. Không dùng Math.random(), UUID dựa trên thời gian, số thứ tự hoặc hash của email làm session ID.

### Opaque ID và session record

Client chỉ cần giữ một chuỗi opaque. Trạng thái thực nằm ở server:

~~~text
Client cookie:
  __Host-app_session = <random opaque value>

Server session record:
  session_id_digest
  account_id
  tenant_id
  authenticated_at
  authentication_methods
  assurance_context
  created_at
  last_seen_at
  idle_expires_at
  absolute_expires_at
  revoked_at
~~~

Có thể lưu digest/HMAC của session ID thay vì giá trị thô để giảm tác động khi kho session bị đọc. Khi client gửi ID, server tính digest theo cùng cơ chế rồi tra cứu. Thiết kế này cần cân nhắc hiệu năng, key rotation và khả năng revoke. Không lưu session ID trong log.

## 5. Chống session fixation bằng cách tạo ID mới

**Session fixation** xảy ra khi attacker khiến nạn nhân sử dụng một session ID mà attacker đã biết hoặc có thể dự đoán. Nếu ứng dụng giữ nguyên ID đó sau đăng nhập và chỉ nâng trạng thái từ anonymous sang authenticated, attacker có thể dùng cùng ID để chiếm phiên đã xác thực.

Ví dụ lỗi:

~~~text
1. Client nhận session ID = S1 khi chưa đăng nhập.
2. Attacker biết hoặc cố định được S1.
3. Nạn nhân đăng nhập thành công.
4. Server giữ nguyên S1 và gắn account của nạn nhân vào session.
5. Attacker gửi S1 và truy cập phiên đã xác thực.
~~~

**Cách phòng vệ:** sau khi xác thực thành công, server phải sinh session ID mới, vô hiệu ID cũ và gắn session mới với principal. Nếu có pre-auth transaction, giữ trạng thái cần thiết bằng một tham chiếu server-side an toàn nhưng không giữ nguyên bearer session ID cũ làm ID của phiên đã xác thực.

~~~text
Trước xác thực:
  anonymous session = S1

Sau khi password/MFA/passkey đạt policy:
  revoke S1
  create fresh session = S2
  bind S2 -> authenticated principal

S1 không thể được dùng để truy cập account đã đăng nhập.
~~~

Cần rotation thêm khi có thay đổi mức tin cậy quan trọng, chẳng hạn hoàn tất step-up hoặc đổi quyền theo policy. Không rotate vô tội vạ ở mọi request vì có thể gây lỗi nhiều tab hoặc request đồng thời; xác định rõ sự kiện và cơ chế chuyển tiếp.

## 6. Gắn session với principal và authentication context

Session record nên chứa tham chiếu tới account nội bộ và các thuộc tính xác thực đã được verifier kiểm tra. Không dùng email hoặc username làm khóa chính của session vì chúng có thể đổi.

Một cấu trúc khái niệm:

~~~json
{
  "sessionId": "<opaque>",
  "principal": {
    "accountId": "account-1742",
    "tenantId": "tenant-alpha"
  },
  "authentication": {
    "authenticatedAt": "2026-11-22T10:00:00Z",
    "methods": ["webauthn"],
    "userVerified": true,
    "assurancePolicy": "standard-v2"
  },
  "lifecycle": {
    "createdAt": "2026-11-22T10:00:00Z",
    "lastSeenAt": "2026-11-22T10:04:00Z",
    "idleExpiresAt": "2026-11-22T10:34:00Z",
    "absoluteExpiresAt": "2026-11-22T18:00:00Z"
  }
}
~~~

Đây là cấu trúc minh họa, không phải token format. Những giá trị authentication chỉ được ghi sau khi verifier xác minh bằng chứng. Không nhận tenant ID, role, userVerified hoặc assurance level từ body của client để tự gắn vào session.

### Authentication time khác session creation time

- **authenticatedAt:** thời điểm credential thực sự được xác minh theo policy.
- **createdAt:** thời điểm session record được tạo.
- **lastSeenAt:** thời điểm request gần nhất được tính là hoạt động.
- **refreshedAt:** thời điểm token/session được làm mới nếu hệ thống có cơ chế đó.

Không được cập nhật authenticatedAt thành thời điểm hiện tại chỉ vì người dùng refresh trang, gọi API hoặc refresh access token. Điều đó sẽ làm sai chính sách yêu cầu xác thực mới.

### Tenant context và membership

Một account có thể tham gia nhiều tenant. Session có thể được scope cho một tenant sau khi server xác minh membership, hoặc account-scoped và yêu cầu resolve tenant ở từng request. Dù chọn mô hình nào, không lấy tenant ID do client gửi rồi ghi vào principal mà chưa kiểm tra. Vai trò cũng cần được xác minh theo membership hiện hành; không mặc định role đã lưu trong session luôn đúng nếu membership bị thu hồi hoặc thay đổi.

## 7. Cookie để mang session ID

Với ứng dụng web, cookie thường là phương thức phù hợp để mang session ID opaque. Cookie cần cấu hình theo threat model.

| Thuộc tính | Vai trò | Khuyến nghị |
| --- | --- | --- |
| **Secure** | Chỉ gửi cookie qua HTTPS | Bật trong production. |
| **HttpOnly** | JavaScript không đọc trực tiếp cookie | Bật cho session cookie để giảm nguy cơ đánh cắp qua XSS; XSS vẫn có thể thực hiện request thay người dùng. |
| **SameSite** | Giới hạn gửi cookie trong một số ngữ cảnh cross-site | Chọn Lax/Strict/None theo flow; None cần Secure. Không coi SameSite là thay thế đầy đủ cho CSRF protection. |
| **Path** | Giới hạn đường dẫn gửi cookie | Thường dùng / cho session ứng dụng; tránh phạm vi rộng hơn nhu cầu. |
| **Domain** | Chọn host/subdomain nhận cookie | Nếu không cần chia sẻ subdomain, bỏ Domain để cookie host-only. |
| **Max-Age / Expires** | Thời hạn cookie phía trình duyệt | Phù hợp với session policy; server vẫn phải kiểm tra expiry riêng. |

Ví dụ header:

~~~http
Set-Cookie: __Host-app_session=<opaque>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Prefix **__Host-** yêu cầu cookie Secure, Path=/ và không có Domain trong các trình duyệt hỗ trợ quy tắc này. Nó giúp giới hạn cookie vào host đã đặt, giảm một số rủi ro ghi đè từ subdomain. Cần kiểm tra tương thích client và chọn tên cookie phù hợp.

Cookie expiry không phải nguồn quyết định cuối cùng. Client có thể giữ cookie lâu hơn hoặc xóa cookie bất kỳ lúc nào; server phải kiểm tra idle expiry, absolute expiry, revoke và trạng thái account ở mỗi request.

### SameSite và luồng đăng nhập liên kết

Một số luồng OIDC/SAML hoặc callback từ nhà cung cấp danh tính có thể cần cookie giao dịch cross-site. Cần thiết kế cookie tạm cho state/nonce/correlation riêng với session chính và cấu hình SameSite phù hợp. Không hạ toàn bộ session cookie xuống None chỉ để một callback hoạt động mà chưa phân tích CSRF và kiến trúc.

## 8. CSRF: cookie tự động được gửi nên cần kiểm soát request

**Cross-Site Request Forgery (CSRF)** lợi dụng việc trình duyệt tự động gửi cookie tới website đích. Attacker có thể khiến trình duyệt người dùng gửi một request thay đổi trạng thái nếu server không kiểm tra nguồn và ý định.

Các biện pháp có thể kết hợp:

- CSRF token khó đoán, gắn với session hoặc giao dịch và kiểm tra ở server.
- SameSite cookie phù hợp.
- Kiểm tra Origin/Referer theo policy cho các request thay đổi trạng thái.
- Không dùng GET cho thao tác tạo, xóa, chuyển tiền, đổi credential hoặc hành động có side effect.
- Kiểm tra content type và custom header theo mô hình API; CORS không phải CSRF defense độc lập.
- Xác thực lại hoặc step-up cho hành động nhạy cảm.

**HttpOnly không ngăn CSRF.** Nó ngăn JavaScript đọc cookie trực tiếp, nhưng browser vẫn tự gửi cookie trong request phù hợp. **SameSite cũng không phải lớp duy nhất**: có flow cross-site hợp lệ, trình duyệt khác nhau và cấu hình domain/subdomain phức tạp.

## 9. Idle timeout và absolute timeout

Session cần giới hạn thời gian sử dụng. Hai loại timeout thường được kết hợp:

- **Idle timeout:** phiên hết hạn sau một khoảng không có hoạt động đủ điều kiện.
- **Absolute timeout:** phiên hết hạn sau một tổng thời gian tối đa kể từ lúc tạo hoặc xác thực, bất kể có hoạt động liên tục.

Ví dụ policy minh họa:

~~~text
createdAt          = 09:00
idleTimeout        = 30 phút
absoluteTimeout    = 8 giờ

lastSeenAt          = 09:20
idleExpiresAt       = 09:50
absoluteExpiresAt   = 17:00

Nếu có request hợp lệ lúc 09:40:
  lastSeenAt mới    = 09:40
  idleExpiresAt mới = 10:10
  absoluteExpiresAt vẫn là 17:00
~~~

Idle timeout không nên được gia hạn bởi request vô nghĩa, heartbeat không kiểm soát hoặc request thất bại. Xác định hành động nào được coi là hoạt động và cách cập nhật lastSeenAt trong môi trường nhiều request đồng thời.

Absolute timeout giúp ngăn phiên tồn tại vô hạn do liên tục hoạt động. Với tác vụ rủi ro cao, có thể yêu cầu xác thực lại trước khi absolute timeout kết thúc hoặc yêu cầu step-up theo authTime.

Thời lượng cụ thể phụ thuộc rủi ro, loại account, thiết bị, tiêu chuẩn và trải nghiệm; không dùng một con số chung cho mọi ứng dụng.

## 10. Session rotation, refresh và concurrent requests

Rotation thay session ID hiện tại bằng ID mới. Nó có ích khi:
- đăng nhập thành công,
- hoàn tất MFA/step-up theo policy,
- thay đổi mức đặc quyền,
- phát hiện nghi ngờ session fixation hoặc compromise,
- thay đổi tenant context nếu mô hình session yêu cầu phiên mới.

Khi rotate, server cần:
1. Tạo ID mới đủ ngẫu nhiên.
2. Tạo session record mới gắn đúng principal và context.
3. Vô hiệu session ID cũ hoặc đặt một chuyển tiếp rất ngắn, có kiểm soát nếu cần hỗ trợ request đang bay.
4. Phát cookie mới.
5. Không để session cũ tiếp tục có quyền cao sau khi đã rotate.

### Nhiều request đồng thời

Một trình duyệt có thể gửi nhiều request cùng lúc. Nếu request A rotate session và request B vẫn dùng cookie cũ, B có thể thất bại. Thiết kế cần quyết định có chấp nhận một khoảng chuyển tiếp ngắn hay yêu cầu client retry bằng cookie mới. Nếu cho phép alias/overlap, phải giới hạn thời gian và quyền; không để ID cũ sống vô thời hạn.

### Race giữa logout và request đang chạy

Logout có thể xảy ra trong khi request khác đang xử lý. Nếu chỉ xóa cookie ở browser mà session record còn active, attacker có thể dùng cookie đã sao chép. Server phải revoke session record; các request mới cần bị từ chối. Với thao tác nhạy cảm, có thể kiểm tra session status gần thời điểm commit để giảm race.

## 11. Server-side session store và hệ thống nhiều instance

Trong mô hình server-side session, client chỉ giữ opaque ID, còn trạng thái được lưu ở server-side store như database, Redis hoặc hệ thống session chuyên dụng.

| Mô hình | Ưu điểm | Điều cần lưu ý |
| --- | --- | --- |
| **In-memory per instance** | Đơn giản, độ trễ thấp | Session mất khi restart; load balancing phải sticky; không phù hợp scale-out nếu không có replication. |
| **Shared Redis/cache** | Truy cập nhanh từ nhiều instance, TTL tự nhiên | Cần HA, bảo vệ mạng/credential, eviction policy, persistence và consistency. |
| **Database** | Có transaction, audit và ràng buộc | Có thể tăng độ trễ và tải; cần index/cleanup. |
| **Hybrid** | Cache nhanh và nguồn bền vững | Invalidation, consistency và failure mode phức tạp hơn. |

Với nhiều instance, mọi server phải nhìn thấy cùng trạng thái session hoặc có cơ chế định tuyến đảm bảo. Nếu logout ở instance A nhưng instance B vẫn giữ cache active, session có thể tiếp tục được chấp nhận. Cần invalidation/TTL và SLA thu hồi rõ.

### Session store outage

Nếu server không thể xác minh session status, quyết định phụ thuộc mức rủi ro. Đối với thao tác nhạy cảm, không nên tự động chấp nhận session dựa trên cookie chỉ vì store lỗi. Có thể trả lỗi tạm thời và yêu cầu retry sau; không fail open để duy trì availability bằng mọi giá.

### Lưu session ID an toàn

Có thể lưu hash/digest của session ID thay vì ID thô, dùng index lookup và TTL. Bảo vệ store bằng network isolation, access control, encryption at rest khi phù hợp, secret rotation và audit. Không cho phép user-controlled query chọn session record bất kỳ.

## 12. Logout, revoke và thay đổi trạng thái account

**Logout** cần làm mất hiệu lực phiên ở server, không chỉ xóa cookie trên client.

Một luồng logout:

1. Kiểm tra request/logout CSRF theo mô hình cookie.
2. Lấy session từ cookie đã xác minh.
3. Đánh dấu session revoked hoặc xóa record theo chính sách lưu audit.
4. Thu hồi refresh token liên quan nếu có.
5. Xóa cookie bằng cùng Path/Domain/SameSite attributes phù hợp.
6. Ghi audit event không chứa session secret.

Các sự kiện có thể cần thu hồi session:

- Người dùng bấm logout hoặc logout all devices.
- Password/passkey/MFA thay đổi hoặc credential bị compromise.
- Account bị khóa, suspend hoặc đóng.
- Membership/tenant bị thu hồi.
- Quản trị viên thu hồi phiên của nhân viên rời tổ chức.
- Phát hiện session bất thường hoặc token bị đánh cắp.
- Chính sách bảo mật yêu cầu reauthentication sau một thay đổi.

Một số hệ thống giữ session record revoked trong thời gian ngắn để audit và chống tái sử dụng; không nhất thiết phải xóa vật lý ngay. Nếu session ID bị revoke, request dùng ID đó phải bị từ chối.

### Logout trên mọi thiết bị

Cần một quan hệ từ account tới tất cả session đang hoạt động, hoặc một account/session version. Khi tăng session version, các session có version cũ bị từ chối nếu verifier kiểm tra version hiện hành. Cơ chế version có thể giảm chi phí liệt kê từng session nhưng cần kiểm tra trạng thái mới đủ nhanh.

## 13. Session assurance và step-up authentication

Session nên giữ thông tin về **thời điểm và phương thức xác thực** để API có thể áp dụng yêu cầu bảo đảm khác nhau theo hành động.

Ví dụ:
- Xem bài học có thể chấp nhận phiên còn hiệu lực.
- Xem thông tin cá nhân nhạy cảm có thể cần xác thực gần đây.
- Thêm passkey, đổi email khôi phục hoặc gỡ MFA có thể cần step-up.
- Tác vụ quản trị có thể yêu cầu passkey/WebAuthn với user verification hoặc phương thức chống phishing theo policy.

Không nhầm **session age** với **authentication age**. Session có thể vừa được tạo lại hoặc access token vừa được refresh, nhưng credential có thể đã được xác minh từ lâu. Server cần lưu authenticatedAt và phương thức đã xác minh; không tăng mức assurance chỉ vì có request mới.

~~~text
Session:
  authenticatedAt = 09:00
  createdAt       = 09:00
  lastSeenAt      = 11:30

11:30 refresh token/session:
  lastSeenAt có thể đổi
  createdAt có thể thay tùy cơ chế
  authenticatedAt không tự đổi

Action cần xác thực trong 5 phút:
  09:00 evidence đã quá cũ lúc 11:30
  -> yêu cầu step-up/re-authentication
~~~

Kết quả step-up nên gắn với session, account, tenant, action và thời hạn. Nếu người dùng đổi tenant hoặc tài nguyên giữa lúc challenge đang chờ, server phải kiểm tra lại binding trước khi thực hiện.

## 14. Server-side session khác access token và refresh token

Các hệ thống có thể dùng session cookie, JWT access token hoặc opaque token. Không nên gọi tất cả là “session” mà không phân biệt.

| Đặc điểm | Server-side session | Access token | Refresh token |
| --- | --- | --- | --- |
| Vai trò | Tham chiếu trạng thái phiên do server quản lý | Mang quyền truy cập API trong phạm vi/audience/thời hạn | Dùng xin access token mới |
| Dữ liệu client giữ | Opaque session ID | Token (JWT hoặc opaque) | Token bí mật có thể dùng dài hơn |
| Trạng thái | Thường tra session store | JWT có thể tự xác minh; opaque thường introspect | Server cần quản lý rotation/revocation |
| Thu hồi | Revoke session record/version | Phụ thuộc TTL, denylist, introspection hoặc sender constraint | Revoke token family/record |
| CSRF | Nếu cookie tự gửi, cần CSRF controls | Nếu bearer trong Authorization header, mô hình CSRF khác; XSS/token theft vẫn nguy hiểm | Nếu refresh token trong cookie, cần CSRF protection |
| Quyền | Server tra principal/context rồi authorize | Scope/audience là giới hạn, API vẫn cần authorization | Không nên dùng trực tiếp để gọi API nghiệp vụ |

JWT không mặc định là session an toàn hơn. Một JWT đã ký vẫn có thể bị đánh cắp và dùng đến khi hết hạn nếu không có cơ chế ràng buộc/thu hồi. Ngược lại, server-side session có thể thu hồi nhanh nhưng phụ thuộc availability của store.

### Access token không phải proof rằng người dùng vừa xác thực

Token được phát hành lúc 10:00 có thể được refresh lúc 10:30. Thời điểm phát hành token mới không nhất thiết là thời điểm người dùng nhập credential hoặc hoàn tất MFA. Dùng claim auth_time hoặc authentication context có nguồn đáng tin và ý nghĩa được xác định; không suy từ iat rằng user vừa xác thực lại.

## 15. Bảo vệ session khỏi các kiểu tấn công phổ biến

| Rủi ro | Cách xảy ra | Kiểm soát |
| --- | --- | --- |
| **Session fixation** | ID cũ được giữ sau đăng nhập | Rotate ID sau authentication/privilege change. |
| **Session hijacking** | Attacker lấy cookie/session ID | HTTPS, Secure/HttpOnly, XSS defense, hạn dùng, revoke và cảnh báo. |
| **CSRF** | Browser tự gửi cookie từ site khác | CSRF token, SameSite, Origin checks, không dùng GET cho side effect. |
| **XSS** | Script độc hại thực hiện request thay user hoặc đánh cắp token có thể đọc | Output encoding, CSP, sanitization, HttpOnly và giảm script bên thứ ba. |
| **Predictable ID** | ID có thể đoán hoặc suy ra | CSPRNG, entropy cao, opaque ID. |
| **Replay** | Cookie/token bị gửi lại | Expiry, revoke, sender constraint nếu phù hợp, phát hiện bất thường. |
| **Privilege persistence** | Session giữ role cũ sau khi quyền bị gỡ | Kiểm tra membership/role hiện hành hoặc version/invalidation. |
| **Concurrent logout race** | Request khác vẫn được xử lý sau logout | Recheck session status ở điểm commit cho tác vụ nhạy cảm. |
| **Cross-tenant confusion** | Session hoặc cache giữ tenant cũ/sai | Tenant context được xác minh và scope mỗi request. |
| **Session store compromise** | Kẻ tấn công đọc/ghi session records | Least privilege, network isolation, encryption, audit, digest và rotation. |

Không có một thuộc tính cookie đơn lẻ nào giải quyết toàn bộ rủi ro. Ví dụ HttpOnly giảm khả năng đọc cookie qua JavaScript nhưng XSS vẫn có thể thực hiện hành động thay người dùng trong origin tin cậy.

## 16. Ví dụ tạo session phía server

Giả mã Java minh họa sau khi authentication service đã trả về kết quả xác minh hợp lệ:

~~~java
SessionResult createAuthenticatedSession(
        VerifiedAuthentication verified,
        TenantContext tenantContext) {

    Account account = accountStore.requireActive(verified.accountId());

    if (tenantContext != null) {
        membershipService.requireActive(
            tenantContext.tenantId(), account.id());
    }

    // Không dùng session ID trước đăng nhập.
    String rawSessionId = sessionIdGenerator.generateSecureRandom();

    SessionRecord record = new SessionRecord();
    record.setSessionIdDigest(sessionHasher.digest(rawSessionId));
    record.setAccountId(account.id());
    record.setTenantId(
        tenantContext == null ? null : tenantContext.tenantId());
    record.setAuthenticatedAt(verified.authenticatedAt());
    record.setAuthenticationMethods(verified.methods());
    record.setAssuranceContext(verified.assuranceContext());
    record.setCreatedAt(clock.instant());
    record.setLastSeenAt(clock.instant());
    record.setIdleExpiresAt(clock.instant().plus(idleTimeout));
    record.setAbsoluteExpiresAt(clock.instant().plus(absoluteTimeout));
    record.setRevokedAt(null);

    sessionRepository.insert(record);

    return new SessionResult(
        rawSessionId,
        cookiePolicy.secureSessionCookie(rawSessionId));
}
~~~

Đây là giả mã giải thích trách nhiệm, không phải implementation hoàn chỉnh. Trong code thật:
- Kiểm tra account, membership và policy phải có xử lý race với việc account bị suspend hoặc membership bị revoke.
- Việc tạo record và thu hồi pre-auth session cần có transaction hoặc workflow nhất quán.
- Raw session ID chỉ được trả về một lần qua kênh an toàn; không ghi vào log.
- Cookie attributes cần được cấu hình theo domain, path, HTTPS và flow thực tế.
- Cần xử lý lỗi khi session store không khả dụng; không cấp cookie nếu record không được lưu thành công.
- Không dùng clock của client để tính expiry.

### Xử lý request tiếp theo

~~~java
Principal requirePrincipal(HttpRequest request) {
    String rawId = cookieReader.requireSessionCookie(request);
    String digest = sessionHasher.digest(rawId);

    SessionRecord session = sessionRepository.findActiveByDigest(digest)
        .orElseThrow(UnauthenticatedException::new);

    Instant now = clock.instant();
    if (session.isRevoked()
            || now.isAfter(session.idleExpiresAt())
            || now.isAfter(session.absoluteExpiresAt())) {
        throw new UnauthenticatedException();
    }

    Account account = accountStore.requireActive(session.accountId());
    return principalFactory.fromSession(session, account);
}
~~~

Phần minh họa cần bổ sung trong production: cập nhật lastSeenAt có kiểm soát, kiểm tra tenant/membership, session version, risk signals, concurrency và authorization cho resource. Repository không nên trả session revoked hoặc hết hạn như session active.

## 17. Kiểm thử session creation và lifecycle

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Password/passkey hợp lệ và policy không yêu cầu MFA | Tạo session mới sau khi verifier thành công. |
| Password đúng nhưng MFA chưa hoàn tất | Chỉ có pre-auth state giới hạn; không có session đầy đủ. |
| Client tự gửi mfaCompleted=true | Không làm thay đổi trạng thái server. |
| Session ID trước đăng nhập được giữ lại sau login | Test thất bại; phải rotate sang ID mới. |
| Session ID có thể đoán từ timestamp/account ID | Test phải phát hiện generator không đạt yêu cầu. |
| Cookie thiếu Secure ở production | Cấu hình bị từ chối qua security test/config check. |
| JavaScript đọc session cookie | Không thể đọc cookie HttpOnly. |
| Request cross-site thay đổi trạng thái | Bị CSRF protection từ chối. |
| Idle timeout đã qua | Session bị từ chối. |
| Absolute timeout đã qua dù có hoạt động liên tục | Session bị từ chối. |
| Session bị revoke sau logout | Request dùng cookie cũ bị từ chối. |
| Account bị khóa sau khi session tạo | Request tiếp theo bị từ chối theo policy. |
| Membership tenant bị thu hồi | Request tenant-scoped không còn được phép. |
| Hai request rotate session đồng thời | Trạng thái nhất quán; ID cũ không giữ quyền ngoài policy. |
| Logout xảy ra trong lúc request nhạy cảm đang xử lý | Điểm commit kiểm tra trạng thái/revocation theo policy. |
| Session store không khả dụng | Không tự động fail open cho thao tác nhạy cảm. |
| Access token refresh | Không tự cập nhật authenticatedAt. |
| Người dùng step-up | Authentication context được cập nhật theo sự kiện đã xác minh, có thời hạn. |
| Cookie bị xóa ở client nhưng server record còn | Logout server-side vẫn phải revoke record. |
| Một session ID được gửi từ nhiều thiết bị/vị trí bất thường | Áp dụng risk policy, cảnh báo hoặc revoke theo mức độ. |

## 18. Vận hành, quan sát và quyền riêng tư

Các chỉ số vận hành có thể gồm:
- số session đang hoạt động theo tenant và loại client,
- số lần tạo session thành công/thất bại,
- số session bị revoke theo nguyên nhân,
- tỷ lệ session hết hạn do idle/absolute timeout,
- lỗi session store, latency, eviction và replication lag,
- số lần session rotation và lỗi do concurrent request,
- sự kiện đăng nhập mới, step-up, recovery và logout all devices,
- số request bị từ chối vì account/membership bị revoke.

Audit nên lưu account ID, tenant ID đã xác minh, session reference không phải raw secret, authentication method, auth time, sự kiện rotation/revoke, actor và request ID. Không log session cookie, raw session ID, access/refresh token, password, OTP hoặc private key.

Session metadata có thể chứa thông tin về thiết bị, IP và hành vi. Chỉ thu thập dữ liệu cần thiết, hạn chế quyền truy cập và thời gian lưu giữ. Không coi fingerprint thiết bị là bằng chứng danh tính tuyệt đối; tín hiệu đó chỉ hỗ trợ risk evaluation.

## 19. Bài tập tình huống

Một ứng dụng doanh nghiệp tạo session ngay sau khi password đúng, trong khi MFA được kiểm tra ở request kế tiếp. Session ID được giữ nguyên từ phiên anonymous. Cookie được đặt Secure nhưng không HttpOnly. Server chạy ba instance, mỗi instance lưu session trong bộ nhớ riêng. Khi người dùng logout ở instance A, request tiếp theo có thể được route tới instance B.

**Yêu cầu phân tích:**

1. Vì sao tạo phiên đầy đủ trước khi MFA hoàn tất là lỗi?
2. Vì sao giữ nguyên anonymous session ID tạo nguy cơ session fixation?
3. Cookie thiếu HttpOnly làm tăng rủi ro gì và HttpOnly không giải quyết điều gì?
4. Vì sao logout ở instance A không bảo đảm session bị vô hiệu ở B?
5. Thiết kế lại thời điểm tạo session, rotation, session store và revocation.
6. Những thông tin authentication context nào cần gắn vào session để step-up?
7. Vì sao mỗi API vẫn phải kiểm tra authorization?

**Hướng phân tích:** Chỉ pre-auth transaction giới hạn được tạo trước MFA. Khi toàn bộ policy đạt, server tạo principal và session ID mới, thu hồi ID cũ. Cookie cần Secure, HttpOnly, SameSite phù hợp và CSRF protection. Các instance dùng shared session store hoặc cơ chế consistency/invalidation có SLA. Logout revoke record ở nguồn trạng thái chung. Session lưu account ID, tenant context đã xác minh, auth time, methods, assurance và expiry. API kiểm tra session, account/membership và quyền trên resource.

## 20. Checklist review

- [ ] Session chỉ được tạo đầy đủ sau khi verifier hoàn tất mọi yếu tố bắt buộc.
- [ ] Pre-auth state bị giới hạn và không truy cập API nghiệp vụ.
- [ ] Session ID được sinh bằng CSPRNG, entropy cao, opaque và không chứa PII.
- [ ] Session ID cũ được rotate sau đăng nhập và thay đổi đặc quyền phù hợp.
- [ ] Session record gắn account ID và tenant context được xác minh.
- [ ] Authentication context lưu method, authenticatedAt và assurance theo kết quả verifier.
- [ ] Cookie có Secure, HttpOnly, SameSite, Path và Domain phù hợp.
- [ ] CSRF được xử lý; không coi SameSite/HttpOnly là đủ.
- [ ] Idle timeout và absolute timeout được thực thi phía server.
- [ ] Logout/revoke vô hiệu session ở server, không chỉ xóa cookie.
- [ ] Multi-instance session store có consistency, invalidation và failure policy rõ.
- [ ] Session store outage không làm fail open cho tác vụ nhạy cảm.
- [ ] Account, tenant membership và role được kiểm tra theo policy hiện hành.
- [ ] Access token refresh không làm giả thời điểm xác thực mới.
- [ ] Có kiểm thử fixation, hijacking, CSRF, replay, expiry, logout và concurrency.
- [ ] Log không chứa raw session ID, cookie, access token hoặc refresh token.

## 21. Ghi nhớ

**Session là trạng thái truy cập được phát hành sau khi xác thực thành công; session ID là bearer secret dùng để tham chiếu trạng thái đó.** Tạo session an toàn cần chờ hoàn tất policy, sinh ID ngẫu nhiên và opaque, rotate để chống fixation, gắn principal cùng authentication context đã xác minh, bảo vệ cookie, giới hạn thời gian và hỗ trợ revoke nhanh.

Một session hợp lệ vẫn không thay thế authorization. Mỗi request cần kiểm tra trạng thái phiên, account, tenant/membership và quyền đối với tài nguyên. Khi review, hãy hỏi: **Phiên được tạo sau bước xác thực nào? ID cũ có bị rotate không? Cookie có được bảo vệ và chống CSRF không? Server có thể revoke trên mọi instance không? Auth time có phản ánh lần xác thực thật không? Phiên bị đánh cắp hoặc account bị khóa thì hệ thống ngăn truy cập tiếp theo bằng cách nào?**
