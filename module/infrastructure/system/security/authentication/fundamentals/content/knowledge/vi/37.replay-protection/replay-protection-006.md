# Token reuse — Phân biệt sử dụng hợp lệ và tấn công phát lại

Một ứng dụng di động gửi access token tới API nhiều lần trong thời hạn của token. Đây là hành vi bình thường: access token thường được thiết kế để dùng cho nhiều request trong phạm vi audience và scope đã cấp. Nhưng nếu attacker sao chép được bearer token từ log, thiết bị hoặc proxy, họ cũng có thể gửi lại token đó từ một máy khác và được chấp nhận cho tới khi token hết hạn hoặc bị thu hồi. Với refresh token rotation, tình huống còn rõ hơn: client đổi refresh token cũ lấy token mới, nhưng sau đó token cũ lại xuất hiện. Việc token đã được sử dụng quay lại có thể là dấu hiệu token bị sao chép và đang bị replay.

**Token reuse** là việc một token được sử dụng lại sau hoặc ngoài ngữ cảnh mà hệ thống dự kiến. Cụm từ này cần được hiểu theo loại token và giao thức: access token thường được dùng lặp lại hợp lệ; refresh token đã bị tiêu thụ trong rotation thường không được dùng lại; one-time token hoặc nonce phải chỉ được chấp nhận một lần; còn session cookie có thể được gửi trong nhiều request nhưng không được phép bị người khác chiếm và phát lại. Vì vậy, hệ thống phải xác định đâu là reuse hợp lệ, đâu là replay trái phép, và đâu là tín hiệu compromise cần phản ứng.

Bài học thuộc chương **Chống replay** của học phần **SECURITY_AUTHENTICATION_FUNDAMENTALS**. Nội dung kết nối token reuse với credential, mật khẩu, MFA, passkey, chứng chỉ, token, phiên, liên kết danh tính và khôi phục tài khoản. Người học sẽ biết mô hình hóa ranh giới tin cậy, phòng chống phishing, replay và lạm dụng đăng nhập; đồng thời thiết kế việc cấp, xoay vòng, ràng buộc, phát hiện và thu hồi token an toàn.

## 1. Kết quả học tập

Sau bài này, người học có thể:

- Phân biệt token reuse hợp lệ, replay attack, token theft và retry của client.
- Giải thích sự khác nhau giữa access token, refresh token, ID token, session cookie, one-time token và idempotency key.
- Mô tả vì sao bearer token bị sao chép có thể được phát lại bởi bất kỳ bên nào nắm giữ nó.
- Thiết kế refresh token rotation, token family và reuse detection.
- Xử lý trường hợp refresh đồng thời, request retry và race condition mà không vô tình phát hành nhiều nhánh token hợp lệ.
- Áp dụng audience, issuer, expiry, scope, nonce, jti và transaction binding phù hợp với loại token.
- Giải thích sender-constrained token qua DPoP hoặc mTLS và giới hạn của từng cơ chế.
- Thiết kế replay cache có thao tác consume nguyên tử và đồng bộ giữa nhiều node.
- Phân biệt replay protection với idempotency và bảo vệ session/cookie.
- Lập quy trình phát hiện, thu hồi, thông báo và khôi phục khi token bị lộ.
- Viết tiêu chí kiểm thử cho replay, refresh reuse, clock skew, cache outage và concurrent requests.

## 2. Token reuse và replay attack là gì?

Token là một vật mang thông tin hoặc quyền được hệ thống chấp nhận theo một giao thức. Một số token được thiết kế để dùng nhiều lần; một số khác chỉ dùng cho một giao dịch hoặc một lần đổi token. Hệ thống cần gắn chính sách sử dụng với loại token, không áp dụng quy tắc “token chỉ được dùng một lần” cho tất cả.

### 2.1. Phân biệt các trường hợp

| Trường hợp | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Reuse hợp lệ | Token được sử dụng nhiều lần đúng thiết kế và đúng chủ thể/ngữ cảnh | Client gửi cùng access token cho nhiều API request |
| Replay attack | Attacker phát lại token hoặc proof hợp lệ đã lấy được trong ngữ cảnh không được phép | Bearer access token bị đánh cắp rồi dùng từ thiết bị attacker |
| Refresh token reuse | Refresh token đã được rotation/tiêu thụ lại xuất hiện | Token cũ được dùng sau khi server đã cấp token kế tiếp |
| One-time token replay | Mã/challenge được thiết kế dùng một lần nhưng được gửi lại | Password reset token hoặc nonce đã consume bị dùng lần hai |
| Retry hợp lệ | Client gửi lại cùng thao tác vì timeout hoặc mất response | Request refresh đã thành công nhưng response bị thất lạc |
| Session hijacking | Attacker chiếm session identifier/cookie và dùng nó như người dùng | Cookie phiên bị lấy từ malware hoặc log |

Không thể kết luận replay chỉ từ việc cùng một access token xuất hiện ở nhiều request. Cần xem token type, client binding, request context, thời gian, thiết bị và giao thức. Ngược lại, một refresh token cũ xuất hiện sau khi rotation đã hoàn tất là tín hiệu mạnh hơn, đặc biệt nếu server có state để biết token đó đã được tiêu thụ.

### 2.2. Bearer token và nguy cơ sao chép

Bearer token trao quyền cho bên đang nắm giữ token. Nếu token bị lộ, server thường không thể chỉ từ chuỗi token biết người gửi có phải client ban đầu hay không. Kẻ lấy được token có thể gửi nó qua TLS từ máy của họ; TLS bảo vệ token trên đường truyền hiện tại nhưng không làm token đã bị đánh cắp mất hiệu lực.

Các nguồn rò rỉ thường gặp:

- Log, trace, error report hoặc analytics vô tình ghi Authorization header.
- Browser storage, extension độc hại, XSS hoặc thiết bị bị malware kiểm soát.
- Proxy, debug tool, crash dump, clipboard hoặc file cấu hình.
- Mobile backup, secret lưu không an toàn hoặc thiết bị bị root/jailbreak.
- URL query string, referrer hoặc redirect chứa token.
- Token bị gửi tới sai audience hoặc client có quyền quá rộng.

## 3. Phân biệt các loại token

| Loại | Mục đích | Mẫu sử dụng | Kiểm soát quan trọng |
| --- | --- | --- | --- |
| Access token | Gọi resource server/API | Thường dùng nhiều lần đến khi hết hạn/revoke | Audience, scope, expiry, sender constraint, revoke strategy |
| Refresh token | Xin access token mới | Thường dài hạn; rotation có thể tiêu thụ token cũ | Rotation, family, reuse detection, client binding |
| ID token | Mang thông tin xác thực cho client trong OIDC | Được kiểm tra trong authentication response | Issuer, audience, nonce, signature, time claims |
| Session cookie | Tham chiếu phiên đăng nhập tại server | Gửi trong nhiều request trình duyệt | Cookie flags, session rotation, server-side revoke, CSRF |
| Password reset token | Cho phép một thao tác recovery giới hạn | Một lần, thời hạn ngắn | One-time consume, purpose binding, expiry |
| Email verification token | Xác minh quyền kiểm soát một địa chỉ | Một lần hoặc theo transaction | Recipient/purpose binding, expiry, replay prevention |
| DPoP proof | Chứng minh client giữ private key ràng buộc với token | Proof mới cho từng request | Signature, htm/htu, iat, jti, nonce, ath |
| Idempotency key | Nhận diện retry của một thao tác | Có thể được gửi lại cùng request | Gắn principal/operation/body, lưu kết quả và TTL |

### 3.1. Access token được phép dùng nhiều lần

Một access token có thể được gửi cho nhiều request trong thời hạn hiệu lực. Resource server cần kiểm tra chữ ký hoặc introspection, issuer, audience, expiry, scope/authorization và các ràng buộc khác. Nếu mỗi lần dùng access token đều bị coi là replay, ứng dụng sẽ không thể hoạt động bình thường.

### 3.2. Refresh token rotation thay đổi quy tắc

Trong rotation, refresh token hiện tại được đổi lấy một refresh token mới. Token cũ được đánh dấu đã tiêu thụ và không được tiếp tục dùng cho lần refresh mới. Nếu token cũ xuất hiện sau đó, server có thể phát hiện một bản sao hoặc client retry không được xử lý đúng.

### 3.3. ID token không phải access token

ID token dành cho client để xác nhận kết quả authentication theo OIDC; nó không mặc nhiên là credential để gọi API. Dùng ID token làm access token hoặc chấp nhận token không kiểm tra audience có thể tạo lỗi confused deputy và mở rộng phạm vi replay.

## 4. Mô hình đe dọa và ranh giới tin cậy

Một luồng token thường đi qua client, authorization server/identity provider, API gateway, resource server, session store, token store và các hệ thống log/monitoring. Mỗi nơi có thể trở thành điểm rò rỉ hoặc điểm chấp nhận token.

~~~mermaid
flowchart TD
    C[Client / device] -->|Access token| G[API gateway]
    G --> R[Resource server]
    C -->|Refresh token| A[Authorization server]
    A --> T[(Refresh token family store)]
    R --> S[(Session / revocation state)]
    C -. token leaked .-> X[Attacker]
    X -->|Replay bearer token| G
    G --> D[Validation and risk policy]
    D --> R
    T --> D
~~~

### 4.1. Tài sản và ranh giới

- **Token issuer:** phát hành token và quản lý vòng đời/revocation.
- **Client:** lưu và gửi token; có thể là browser, mobile app, desktop app hoặc workload.
- **Resource server:** kiểm tra token và quyết định request có được tiếp tục.
- **Token/session store:** lưu trạng thái refresh family, session, denylist hoặc revocation epoch.
- **Proxy/gateway:** xử lý header và có thể vô tình log token.
- **Device/authenticator:** giữ private key nếu dùng sender constraint.
- **Notification/recovery:** kênh người dùng nhận cảnh báo và khôi phục quyền kiểm soát.

Không tin client tự khai rằng token đã được rotate, revoke hoặc chưa từng dùng. Trạng thái authoritative phải được lưu và kiểm tra ở server hoặc authority phù hợp.

## 5. Nguyên tắc cơ bản để hạn chế replay

Không có một thuộc tính token duy nhất ngăn mọi dạng replay. Cần kết hợp nhiều kiểm soát:

1. **Giới hạn thời gian:** expiry ngắn phù hợp với giá trị token và khả năng refresh.
2. **Giới hạn phạm vi:** issuer, audience, scope, subject/client và purpose rõ ràng.
3. **Ràng buộc giao dịch:** token/challenge gắn với đúng transaction, redirect, resource hoặc thao tác.
4. **One-time consume:** token dùng một lần phải có trạng thái consumed được cập nhật nguyên tử.
5. **Chống phát lại proof:** nonce/jti/timestamp và cache kiểm tra reuse trong cửa sổ cho phép.
6. **Sender constraint:** gắn token với khóa của client bằng DPoP hoặc mTLS khi phù hợp.
7. **Phát hiện reuse:** lưu trạng thái token family/rotation và phát hiện token cũ quay lại.
8. **Thu hồi:** revoke token/session/credential liên quan và truyền trạng thái tới validator.
9. **Bảo vệ nơi lưu:** không log token, không để token trong URL và bảo vệ client storage.

Expiry chỉ giới hạn khoảng thời gian token có thể bị lạm dụng; nó không ngăn replay trong khoảng đó. Nonce và jti chỉ có tác dụng nếu server kiểm tra uniqueness/consumption; chỉ thêm claim vào token mà không lưu trạng thái không ngăn một bearer token bị gửi lại.

## 6. Refresh token rotation và token family

Refresh token thường có tuổi thọ dài hơn access token và có thể cấp quyền tiếp tục phiên. Vì vậy, nếu refresh token bị đánh cắp, attacker có thể duy trì quyền truy cập sau khi access token cũ hết hạn.

### 6.1. Rotation cơ bản

Một token family đại diện cho chuỗi refresh token được phát hành nối tiếp cho cùng grant/client:

~~~text
RT-1 ACTIVE
   |
   | refresh exchange succeeds
   v
RT-1 CONSUMED  --->  RT-2 ACTIVE
                         |
                         | next successful exchange
                         v
                    RT-2 CONSUMED ---> RT-3 ACTIVE
~~~

Khi RT-1 đã được tiêu thụ, server lưu trạng thái để không chấp nhận RT-1 như một token mới. Token mới RT-2 có quan hệ với cùng family và grant. Nếu RT-1 quay lại sau khi RT-2 đã được cấp, đó là dấu hiệu có thể có hai bên đang giữ bản sao của RT-1.

### 6.2. Reuse detection

Khi nhận refresh token:

1. Xác minh token thuộc issuer/client/grant hợp lệ.
2. Tìm trạng thái token và family trong kho authoritative.
3. Nếu token active và chưa hết hạn, xử lý rotation trong transaction/atomic operation.
4. Đánh dấu token cũ consumed và tạo token mới trong cùng thao tác logic.
5. Nếu token đã consumed/revoked, áp dụng reuse policy.
6. Ghi security event và đánh giá có cần revoke cả family/grant/session hay không.

Nhiều hệ thống chọn revoke toàn bộ token family khi phát hiện reuse, vì server không thể biết bên nào đang giữ token cũ là client hợp lệ hay attacker. Quyết định cụ thể phụ thuộc protocol, khả năng ràng buộc client và cách xử lý retry.

### 6.3. Vì sao reuse là tín hiệu nhưng không phải kết luận tuyệt đối?

Một refresh token cũ có thể xuất hiện vì:

- Attacker đã sao chép token và dùng nó sau client thật.
- Client gửi refresh đồng thời từ hai tab/device.
- Response thành công bị mất nên client retry token cũ.
- Mobile app bị suspend/crash rồi khôi phục trạng thái cũ.
- Hai worker xử lý cùng token do queue hoặc race condition.
- Token store replica/cache trả trạng thái stale.

Vì vậy, hệ thống cần thiết kế client single-flight refresh, idempotency/response recovery phù hợp và lưu trạng thái rotation nguyên tử. Không tạo một khoảng grace quá rộng chỉ để che lỗi concurrency; grace window có thể cho attacker thêm cơ hội dùng bản sao token.

### 6.4. Token family và blast radius

Khi revoke một family, thu hồi mọi refresh token descendant thuộc family đó. Cần xác định access token đã phát hành từ family có bị ảnh hưởng không. Nếu access token là JWT tự xác minh, chúng có thể vẫn hợp lệ tới expiry trừ khi resource server kiểm tra session/family revocation. Chính sách cần nói rõ phạm vi:

- Revoke refresh family ngăn cấp access token mới.
- Revoke session có thể làm các request tiếp theo bị từ chối nếu resource server kiểm tra session.
- Access token đang tồn tại cần TTL ngắn, introspection, denylist hoặc revocation epoch nếu cần chặn sớm.
- Credential/thiết bị bị compromise có thể cần unlink hoặc reset riêng.

## 7. Xử lý refresh đồng thời và retry hợp lệ

Một client có thể mở nhiều request gần như cùng lúc khi access token hết hạn. Nếu mọi request tự refresh, hai request có thể gửi cùng refresh token cũ. Server xử lý request thứ nhất và rotate sang token mới; request thứ hai đến sau có thể bị coi là reuse.

### 7.1. Single-flight ở client

Client nên có một refresh operation đang chạy cho mỗi session/token family. Các request chờ kết quả đó thay vì tự gửi refresh song song. Sau khi nhận token mới, client cập nhật token state một cách nguyên tử rồi retry request cần thiết.

### 7.2. Idempotent refresh handling

Có thể thiết kế một cơ chế xử lý retry trong thời gian ngắn nếu client chứng minh được cùng transaction/client và server có thể trả lại kết quả đã commit mà không cấp thêm nhánh token. Cơ chế này cần:

- Operation ID hoặc idempotency key ngẫu nhiên gắn với principal, client, token family và request.
- Lưu kết quả exchange đã commit trong thời gian ngắn và bảo vệ dữ liệu token mới.
- Chỉ trả lại kết quả cho đúng client context đã xác minh.
- Giới hạn TTL và số lần retry.
- Không cho một idempotency key tùy ý biến token đã revoked thành active.

Nếu không thể xác minh retry là cùng một giao dịch hợp lệ, xử lý như reuse theo policy và yêu cầu authentication/recovery lại.

### 7.3. Atomic state transition

Chuyển trạng thái refresh token phải là một thao tác atomic hoặc được serialize theo token family. Nếu hai node cùng đọc RT-1 là active rồi đều phát RT-2a và RT-2b, hệ thống tạo hai nhánh hợp lệ và mất khả năng xác định token family. Dùng compare-and-swap, unique constraint, row lock hoặc transaction store phù hợp để chỉ một exchange thành công.

## 8. Access token: replay, expiry và revocation

Access token thường là bearer token và được dùng nhiều lần. Replay protection cần tập trung vào việc giảm giá trị của token bị lấy cắp và phát hiện sử dụng bất thường.

### 8.1. Giới hạn lifetime và scope

- Dùng access token TTL phù hợp, thường ngắn hơn refresh token.
- Chỉ cấp audience cần thiết; API A không nên chấp nhận token dành cho API B.
- Scope/permission theo least privilege.
- Không đưa dữ liệu nhạy cảm không cần thiết vào token.
- Kiểm tra issuer, signature, algorithm allowlist, expiry, not-before và audience.
- Không tin claim chỉ vì token có chữ ký; phải kiểm tra semantics và policy.

### 8.2. Revocation strategy

JWT access token tự chứa claims có thể được xác minh offline. Issuer revoke token không làm chữ ký mất hiệu lực. Các lựa chọn:

- TTL ngắn để giới hạn cửa sổ lạm dụng.
- Opaque/reference token và introspection tới authorization server.
- Denylist theo token ID hoặc session reference.
- Principal/session revocation epoch được resource server kiểm tra.
- Sender-constrained token để token bị sao chép không đủ dùng nếu thiếu private key.

Mỗi cách có trade-off về độ trễ, availability, privacy và chi phí. Nếu API không kiểm tra revocation state, đừng thông báo rằng access token đã bị vô hiệu hóa tức thời.

### 8.3. Không dùng jti một mình để ngăn access token reuse

Claim jti định danh token và có thể hỗ trợ denylist/audit. Nhưng access token thông thường được phép dùng nhiều lần, nên việc lưu jti rồi từ chối lần thứ hai sẽ phá vỡ semantics. Chỉ áp dụng one-time-use cho loại token/giao dịch được thiết kế như vậy, hoặc dùng jti để phát hiện duplicate trong một giao thức có định nghĩa rõ.

## 9. Sender-constrained token: DPoP và mTLS

Bearer token có thể bị replay nếu attacker chỉ cần sao chép chuỗi token. Sender-constrained token bổ sung bằng chứng rằng request được gửi bởi client nắm giữ khóa được gắn với token.

### 9.1. DPoP

Demonstrating Proof of Possession (DPoP) dùng một khóa bất đối xứng do client giữ để tạo proof cho request. Token có thể được ràng buộc với public key thumbprint; resource server kiểm tra proof có khớp key được gắn với token không.

Một DPoP proof thường chứa các thông tin như:

- HTTP method (htm).
- URI đích (htu) theo quy tắc chuẩn hóa của giao thức.
- Thời điểm phát hành (iat).
- ID duy nhất của proof (jti).
- Nonce do server cung cấp nếu policy yêu cầu.
- Hash access token (ath) khi proof dùng cho resource request.

Server xác minh chữ ký, key binding, method/URI, thời gian, token hash và nonce. Để chống phát lại proof, server cần lưu jti đã dùng trong cửa sổ thời gian cho phép hoặc dùng cơ chế nonce có trạng thái. Nếu chỉ kiểm tra chữ ký và iat, attacker có thể gửi lại cùng proof trong cửa sổ chấp nhận.

DPoP giảm khả năng token bị đánh cắp riêng lẻ có thể dùng từ client khác. Nó không bảo vệ nếu attacker chiếm được cả private key/client runtime, có thể yêu cầu client hợp lệ ký proof hoặc kiểm soát thiết bị.

### 9.2. mTLS

Mutual TLS xác thực client bằng certificate trong TLS handshake. Token có thể được ràng buộc với certificate/key client; resource server kiểm tra chứng chỉ của kết nối khớp binding trong token.

mTLS phù hợp nhiều môi trường service-to-service hoặc client được quản lý. Cần quản lý vòng đời certificate, private key, rotation, revocation và proxy termination. Nếu TLS kết thúc tại proxy, backend phải nhận được bằng chứng client certificate qua một kênh proxy được xác thực và cấu hình tin cậy; không tin header client tự gửi.

### 9.3. Giới hạn sender constraint

- Nếu private key bị đánh cắp cùng token, sender constraint không còn bảo vệ.
- Nếu client bị compromise, malware có thể dùng key trong thiết bị để tạo proof hợp lệ.
- Đồng hồ sai có thể khiến proof bị từ chối hoặc mở rộng replay window.
- DPoP/mTLS cần hỗ trợ đồng bộ từ issuer, client và resource server.
- Token binding phải được kiểm tra ở mọi resource server, không chỉ gateway.

## 10. Nonce, timestamp, jti và replay cache

Nonce là giá trị ngẫu nhiên hoặc duy nhất gắn với challenge/giao dịch. Timestamp giới hạn tuổi của request/proof. jti định danh một token hoặc proof. Những trường này chỉ giúp chống replay khi verifier có chính sách kiểm tra phù hợp.

### 10.1. One-time nonce

Một flow one-time challenge:

1. Server sinh nonce bằng CSPRNG.
2. Lưu nonce cùng principal/client, purpose, transaction, thời điểm tạo và TTL.
3. Gửi nonce tới client qua kênh đã xác thực.
4. Client đưa nonce vào proof/request được ký hoặc bảo vệ.
5. Server kiểm tra chữ ký, transaction binding, TTL và trạng thái chưa consume.
6. Server atomically đánh dấu nonce đã dùng trước khi thực hiện side effect.
7. Request gửi lại cùng nonce bị từ chối hoặc nhận kết quả idempotent đã lưu theo thiết kế.

### 10.2. Replay cache

Replay cache lưu dấu hiệu đã dùng, ví dụ key kết hợp issuer, client/key thumbprint và jti. Cache cần:

- TTL dài ít nhất bằng replay acceptance window cộng clock skew cho phép.
- Atomic insert-if-absent hoặc thao tác consume nguyên tử.
- Đồng bộ giữa node/region nơi cùng proof có thể được gửi tới.
- Chống eviction sớm hoặc mất dữ liệu khi restart đối với mức bảo đảm cần thiết.
- Giới hạn kích thước và bảo vệ trước flood nonce/jti.
- Có fail policy: với thao tác nhạy cảm, nếu không thể kiểm tra replay thì không tự động accept.

Local in-memory cache riêng từng node không đủ nếu attacker có thể gửi cùng proof tới nhiều node khác nhau. Dùng store chia sẻ, partition theo key hoặc cơ chế có bảo đảm consistency phù hợp.

### 10.3. Clock skew

Timestamp giúp giới hạn cửa sổ replay nhưng cần chấp nhận sai lệch đồng hồ có kiểm soát. Cửa sổ quá rộng tạo thêm thời gian cho attacker; quá hẹp gây lỗi cho thiết bị có đồng hồ sai. Dùng đồng hồ server tin cậy, NTP được quản lý, giới hạn skew, nonce challenge khi cần và giám sát clock drift.

## 11. Session cookie và replay

Session cookie thường được gửi trong mọi request của browser tới domain/path phù hợp. Việc cookie xuất hiện nhiều lần là bình thường. Rủi ro nằm ở việc attacker lấy được cookie và dùng nó từ một môi trường khác.

### Biện pháp bảo vệ

- Dùng HTTPS và cookie Secure.
- Dùng HttpOnly để giảm khả năng JavaScript đọc cookie; vẫn cần chống XSS.
- Chọn SameSite phù hợp và bảo vệ CSRF cho thao tác thay đổi trạng thái.
- Giới hạn Domain/Path; không mở rộng cookie tới subdomain không cần thiết.
- Rotate session ID sau login, step-up và thay đổi quyền.
- Đặt idle timeout và absolute lifetime.
- Revoke session phía server và đồng bộ tới các node.
- Không ghi cookie/session ID vào log, URL hoặc analytics.
- Phát hiện session dùng đồng thời từ ngữ cảnh bất thường nhưng tránh kết luận chỉ dựa trên IP.

Session binding với device signal có thể giúp phát hiện bất thường nhưng fingerprint không phải khóa mật mã. Với mức bảo đảm cao, cân nhắc sender-constrained token, device certificate hoặc passkey step-up.

### 11.1. CSRF và replay khác nhau

CSRF khiến browser gửi request mang cookie phiên của người dùng tới site mục tiêu do attacker điều khiển. Replay là phát lại một token/request/proof đã thu được. Hai vấn đề có thể giao nhau nhưng cần kiểm soát riêng: SameSite/CSRF token/origin checks cho CSRF; nonce, jti, timestamp, one-time consume và sender constraint cho replay theo giao thức.

## 12. Request signing và HMAC replay protection

Một số API dùng HMAC hoặc chữ ký request thay bearer token. Client ký dữ liệu request bằng secret/key; server xác minh chữ ký. Để chống replay, chữ ký cần bao phủ dữ liệu đủ để ràng buộc request:

- HTTP method.
- Canonical request target/path/query theo một quy tắc duy nhất.
- Hash body hoặc payload digest.
- Timestamp.
- Nonce/request ID duy nhất.
- Key ID/client identity và audience.

Server xác minh chữ ký và timestamp, sau đó consume nonce/request ID nguyên tử. Nếu không có nonce hoặc trạng thái chống trùng, attacker có thể phát lại nguyên request đã ký trong cửa sổ timestamp.

Canonicalization cần được định nghĩa chặt: cách xử lý query parameter, percent-encoding, header trùng, khoảng trắng, body encoding và proxy rewriting. Client và server phải tạo cùng canonical representation; nếu không, request hợp lệ có thể bị từ chối hoặc hai request khác nhau có thể được hiểu nhầm là một.

HMAC chỉ chứng minh bên gửi có secret tương ứng; nếu secret bị lộ, attacker có thể tạo chữ ký mới. Dùng secret riêng theo client, rotation, scope, storage an toàn và revocation.

## 13. Idempotency không thay thế replay protection

Idempotency xử lý việc cùng một thao tác được gửi lại do retry mà không tạo side effect lặp. Replay protection ngăn một credential/proof/request cũ được sử dụng trái phép. Hai cơ chế có thể phối hợp:

| Cơ chế | Mục tiêu | Ví dụ |
| --- | --- | --- |
| Replay protection | Từ chối proof/token one-time đã được dùng hoặc không đúng sender | DPoP jti bị gửi lại |
| Idempotency | Trả kết quả nhất quán khi cùng thao tác hợp lệ được retry | Client retry tạo payment sau timeout |
| Rate limiting | Giới hạn số request trong khoảng thời gian | Hạn chế token endpoint bị flood |
| Revocation | Ngăn credential/session tiếp tục được chấp nhận | Revoke refresh token family |

Một idempotency key không phải bí mật và không xác thực người gửi. Phải gắn nó với principal/client, operation, payload hash và TTL. Nếu cùng key được dùng với payload khác, từ chối. Nếu key bị dùng bởi principal khác, không chia sẻ kết quả.

Với thao tác tài chính hoặc thay đổi credential, idempotency record phải được lưu bền vững đủ lâu và gắn với kết quả commit. Không cho retry một request đã bị từ chối do authentication/authorization như thể nó là giao dịch thành công.

## 14. Phát hiện và ứng phó token reuse

Tín hiệu có thể gồm:

- Refresh token đã consumed xuất hiện lại.
- DPoP jti trùng trong replay window.
- One-time nonce đã dùng xuất hiện lần nữa.
- Token family có refresh từ client/device không khớp.
- Token cùng session được sử dụng đồng thời từ ngữ cảnh không phù hợp.
- Refresh token rotation có hai nhánh hoặc nhiều descendant bất thường.
- Access token bị dùng sau khi principal/session đã revoke.
- Token xuất hiện trong log, URL, telemetry hoặc secret scan.

### 14.1. Quy trình phản ứng

1. Xác định token type, issuer, client, subject, audience và token family.
2. Xác minh trạng thái: active, consumed, revoked, expired hay unknown.
3. Phân biệt retry/concurrency hợp lệ với reuse trái phép bằng operation ID, client binding, thời gian và lịch sử.
4. Nếu có dấu hiệu compromise, revoke refresh family/grant/session theo policy.
5. Chặn access token liên quan theo khả năng: introspection, denylist, session epoch hoặc chờ TTL ngắn nếu không có revoke tức thời.
6. Thu hồi/rotate client credential hoặc key nếu private key/secret có thể bị lộ.
7. Thông báo qua contact đã xác minh; hướng người dùng tự mở ứng dụng chính thức.
8. Kiểm tra thay đổi tài khoản, passkey/MFA, recovery method và hành động đã thực hiện.
9. Bảo toàn audit evidence không chứa token thô.
10. Khôi phục bằng xác thực/recovery có bảo đảm tương xứng và giám sát đăng nhập tiếp theo.

Không tự động khóa tài khoản vĩnh viễn chỉ vì một access token được sử dụng từ IP mới. Ngược lại, không bỏ qua refresh reuse đã xác nhận chỉ vì request đến từ IP quen thuộc.

### 14.2. Thông báo và recovery

Thông báo không nên chứa token hoặc link bearer có thể dùng để thu hồi mọi phiên chỉ bằng một lần mở. Nếu người dùng không nhận ra hoạt động, đưa họ tới trang quản lý phiên chính thức, yêu cầu xác thực lại bằng phương thức còn tin cậy và hỗ trợ thu hồi phiên/credential. Nếu email hoặc thiết bị nhận thông báo cũng có thể bị chiếm, dùng một kênh recovery độc lập.

## 15. Pseudocode: refresh rotation với atomic consume

Đoạn mã khái niệm dưới đây minh họa chuyển trạng thái refresh token. Không dùng nó thay cho giao thức OAuth/OIDC hoặc thư viện đã được đánh giá.

~~~ts
async function rotateRefreshToken(presentedToken, clientContext) {
  const tokenRef = await identifyRefreshToken(presentedToken);
  if (!tokenRef) return rejectRefresh();

  return database.transaction(async (tx) => {
    const current = await tx.lockRefreshToken(tokenRef.id);

    if (!current || current.clientId !== clientContext.clientId) {
      return rejectRefresh();
    }

    if (current.status === "CONSUMED" || current.status === "REVOKED") {
      await tx.revokeTokenFamily(current.familyId, "REFRESH_TOKEN_REUSE");
      await tx.insertSecurityEvent({
        type: "REFRESH_TOKEN_REUSE_DETECTED",
        familyRef: current.familyRef,
        clientRef: clientContext.safeClientRef
      });
      return { action: "REAUTHENTICATE" };
    }

    if (current.status !== "ACTIVE" || current.expiresAt <= now()) {
      return rejectRefresh();
    }

    const next = await createNextRefreshToken(tx, current);
    await tx.markConsumed(current.id, now());
    await tx.insertRefreshToken(next);

    return { action: "ROTATED", refreshToken: next.secret };
  });
}
~~~

Đây là pseudocode minh họa. Một triển khai cần:

- Lưu verifier/hash của refresh token thay vì token plaintext nếu kiến trúc cho phép.
- Dùng unique constraint/row lock/compare-and-swap để một token chỉ có một lần transition active-to-consumed.
- Không gửi token mới ra ngoài trước khi transaction commit.
- Xử lý response bị mất bằng idempotent exchange có ràng buộc client, nếu hệ thống hỗ trợ.
- Không trả chi tiết giúp attacker dò token family hoặc trạng thái tài khoản.
- Revoke family theo policy và xử lý access token đã phát hành.
- Ghi event bằng outbox để notification/monitoring không làm hỏng transaction.

## 16. Tình huống thực tế: refresh token bị dùng lại

Một ứng dụng mobile nhận RT-17 và dùng nó để xin access token mới. Authorization server đánh dấu RT-17 là consumed, phát RT-18 và trả response. Sau đó, một request khác mang RT-17 tới từ một thiết bị khác. Hệ thống phải quyết định đây là attacker hay retry hợp lệ do response trước bị thất lạc.

### Phân tích

1. Kiểm tra RT-17 đã được đánh dấu consumed và RT-18 đã được phát hành trong family tương ứng.
2. Kiểm tra client/device binding, operation ID và dấu thời gian của lần exchange đầu.
3. Nếu request thứ hai là retry cùng operation đã commit và client context có thể xác minh, trả lại kết quả đã lưu theo cơ chế idempotent, không tạo RT-19 mới.
4. Nếu không chứng minh được là cùng operation hoặc client binding không khớp, coi là reuse đáng ngờ.
5. Revoke family theo policy, xử lý access token còn hiệu lực và yêu cầu người dùng xác thực lại.
6. Ghi audit event, cảnh báo qua kênh đã xác minh và kiểm tra các thay đổi gần đây.

### Những lỗi thiết kế cần tránh

- Chỉ lưu token hiện tại mà không lưu trạng thái token đã tiêu thụ.
- Hai node đồng thời chấp nhận cùng refresh token và tạo hai nhánh.
- Dùng grace period dài không ràng buộc client.
- Revoke refresh token nhưng tuyên bố access JWT đã bị vô hiệu hóa tức thời khi API không kiểm tra trạng thái.
- Coi mọi access token lặp lại là tấn công.
- Dùng idempotency key do client tùy ý gửi mà không ràng buộc principal/client/payload.

## 17. Tiêu chí chấp nhận và kiểm thử

| Tình huống | Kết quả mong đợi |
| --- | --- |
| Access token hợp lệ được dùng cho nhiều API request | Chấp nhận theo audience, scope, expiry và policy |
| Bearer token bị sao chép và dùng từ client khác | Bị giảm thiểu bằng sender constraint/risk policy; phát hiện theo tín hiệu có sẵn |
| Refresh token active được đổi lần đầu | Token cũ consumed và token kế tiếp active trong cùng family |
| Refresh token consumed được gửi lại | Reuse policy kích hoạt; family/grant được xử lý theo thiết kế |
| Hai refresh request đến đồng thời | Chỉ một state transition active-to-consumed thành công |
| Response refresh bị mất và client retry | Idempotent recovery chỉ trả kết quả cũ cho cùng operation/client đã xác minh |
| Retry dùng idempotency key nhưng payload khác | Từ chối vì request fingerprint không khớp |
| DPoP proof có chữ ký hợp lệ nhưng jti đã dùng | Từ chối trong replay window |
| DPoP proof dùng sai HTTP method hoặc URI | Từ chối vì proof không gắn với request thực tế |
| DPoP proof hết cửa sổ thời gian | Từ chối hoặc yêu cầu nonce/challenge mới |
| Nonce one-time đã consume được gửi lại | Từ chối; không thực hiện side effect lần hai |
| Cùng proof tới hai API node khác nhau | Shared atomic replay store chỉ cho một lần chấp nhận |
| Replay cache không khả dụng | Hành động nhạy cảm không tự động accept nếu không kiểm tra được replay |
| Client dùng mTLS với certificate không khớp token binding | Từ chối |
| JWT access token đã revoke nhưng chưa hết hạn | Resource server áp dụng revocation strategy/SLA đã định nghĩa; không giả định chữ ký tự mất hiệu lực |
| Session cookie bị revoke phía server | Request tiếp theo bị từ chối dù browser vẫn gửi cookie cũ |
| Refresh token family bị revoke | Không thể cấp token mới từ bất kỳ descendant nào |
| Clock skew vượt giới hạn | Proof bị từ chối hoặc chuyển challenge theo policy; không mở replay window vô hạn |
| Token xuất hiện trong log | Secret scanning/redaction phát hiện; log được xử lý theo incident policy |
| Token reuse được xác nhận | Audit, revoke, notification và recovery được kích hoạt theo phạm vi |

### Chỉ số vận hành

Theo dõi số refresh reuse theo client/app version, tỷ lệ refresh concurrency, token family revoke, DPoP replay rejection, nonce duplicate, replay cache latency/error, clock skew, access token lifetime, thời gian propagation revoke và số false positive do retry. Phân tích theo client version giúp phát hiện lỗi single-flight hoặc retry sau timeout mà không hạ thấp kiểm soát toàn hệ thống.

## 18. Bài tập tự kiểm tra

Một nền tảng có web app, mobile app và API. Access token là JWT sống ngắn; refresh token được rotation; mobile app có thể chạy nhiều request song song. Một số API hỗ trợ DPoP, còn hệ thống nội bộ dùng mTLS. Nhóm bảo mật phát hiện một refresh token cũ xuất hiện hai lần sau khi đã cấp token mới.

Hãy:

1. Phân biệt access token reuse hợp lệ với refresh token reuse đáng ngờ.
2. Vẽ state machine cho refresh token family và nêu trạng thái của token cũ/mới.
3. Thiết kế single-flight refresh và idempotent retry để xử lý response bị mất.
4. Giải thích cách atomic consume ngăn hai node tạo hai nhánh token.
5. Mô tả DPoP jti/nonce/ath và vì sao proof cần replay cache.
6. So sánh sender constraint bằng DPoP và mTLS; nêu giới hạn khi private key bị chiếm.
7. Chọn chiến lược revoke cho JWT access token và định nghĩa SLA.
8. Viết test case cho concurrent refresh, replay proof, cache outage, clock skew và session revoke.

**Gợi ý đánh giá:** câu trả lời tốt phải phân biệt semantics từng token, có token family state, atomic rotation, xử lý retry không mở grace window tùy tiện, sender constraint, replay cache phân tán và kế hoạch revoke access/session. Không coi jti hoặc expiry đơn lẻ là giải pháp chống replay đầy đủ.

---

**Ghi nhớ:** token reuse không tự động là replay: access token thường được dùng nhiều lần; refresh token đã consumed trong rotation hoặc nonce/proof one-time bị dùng lại mới là tín hiệu cần xử lý theo semantics cụ thể. Hãy dùng **refresh rotation và token family**, atomic state transition, sender constraint (DPoP/mTLS), nonce/jti/timestamp cùng replay cache nhất quán; phân biệt retry hợp lệ bằng idempotency gắn với client/operation; và có kế hoạch revoke session/token, thông báo và recovery. Expiry, chữ ký hợp lệ hoặc một claim jti riêng lẻ không đủ ngăn mọi hình thức phát lại.
