# Token truy cập, phiên đăng nhập và vòng đời thông tin xác thực

> **Bối cảnh:** Software Design / Software Architecture / System Architecture / Microservices  
> **Nhóm:** Bảo mật (Security)  
> **Mục tiêu:** Hiểu rõ cách một hệ thống xác thực người dùng hoặc dịch vụ, cấp và kiểm tra token, quản lý phiên đăng nhập, gia hạn, thu hồi, phục hồi thông tin xác thực và hạn chế thiệt hại khi thông tin bị lộ.

## 1. Tại sao cần phân biệt token, session và credential?

Một người dùng bấm **Đăng nhập** và nhận quyền sử dụng hệ thống. Phía sau nút bấm có thể tồn tại ít nhất ba đối tượng có vòng đời khác nhau:

1. **Credential (thông tin dùng để chứng minh danh tính):** mật khẩu, passkey, khóa riêng của ứng dụng, mã OTP hoặc một yếu tố xác thực phù hợp. Credential được dùng để **xác thực** chủ thể, không nhất thiết được gửi trong mọi request.
2. **Login session (phiên đăng nhập):** trạng thái hệ thống ghi nhận rằng một người dùng đã xác thực và có thể tiếp tục tương tác theo chính sách. Session có thể nằm ở server và được tra cứu bằng session ID trong cookie, hoặc được biểu diễn một phần bằng token.
3. **Access token (token truy cập):** chứng chỉ có giới hạn để client gọi một tài nguyên/API đã định. Token thể hiện một số ngữ cảnh ủy quyền như chủ thể, nơi phát hành, đối tượng nhận, quyền và thời gian hiệu lực. Token không đồng nghĩa với credential gốc hay toàn bộ phiên đăng nhập.

Ví dụ: sau khi xác thực bằng passkey, trình duyệt giữ cookie phiên của ứng dụng; backend gọi API đơn hàng bằng một access token ngắn hạn. Người dùng có thể tiếp tục đăng nhập dù access token cũ đã hết hạn, vì thành phần giữ session có thể cấp hoặc lấy token mới theo chính sách.

Một số thuật ngữ dễ nhầm:

| Thành phần | Mục đích chính | Ai thường lưu? | Điểm cần lưu ý |
|---|---|---|---|
| Password / passkey / khóa dịch vụ | Chứng minh danh tính hoặc quyền sở hữu bí mật/khóa | Trình quản lý credential, thiết bị, vault, hệ thống xác thực | Phải có cơ chế đổi, khóa, phục hồi |
| Session ID | Tham chiếu đến trạng thái đăng nhập ở server | Cookie phía browser; record ở session store | ID phải khó đoán, chống fixation |
| Access token | Cho phép gọi resource server trong phạm vi cụ thể | Client hoặc BFF giữ để gửi cho API | Thường ngắn hạn, giới hạn audience/scope |
| Refresh token | Xin access token mới theo chính sách | Client/BFF được phép sử dụng | Giá trị cao, cần lưu an toàn và chống replay |
| ID token (OpenID Connect) | Truyền thông tin kết quả xác thực đến OIDC client | OIDC client | Không dùng thay access token để gọi API |
| API key | Định danh/xác thực một ứng dụng hoặc tích hợp theo hợp đồng | Server hoặc secret manager | Không mặc nhiên đại diện người dùng hay có chuẩn claim giống OAuth token |
| CSRF token | Chống giả mạo yêu cầu từ trình duyệt trong ngữ cảnh phù hợp | Client/server theo cơ chế chống CSRF | Không phải access token hay bằng chứng danh tính |

**Authentication** trả lời “Ai đang được xác thực?”. **Authorization** trả lời “Chủ thể này có được phép thực hiện hành động này trên tài nguyên cụ thể không?”. **Session management** trả lời “Hệ thống duy trì và kết thúc trạng thái đã xác thực như thế nào?”.

Access token hợp lệ về chữ ký nhưng không có quyền xem đơn hàng của khách khác vẫn phải bị từ chối ở bước authorization.

## 2. Ba kiến trúc truy cập thường gặp

### 2.1. Browser dùng session ở backend (server-side session)

~~~text
Browser                  Web App / BFF                Session Store
   | POST /login + bằng chứng xác thực |                    |
   |---------------------------------->| Xác thực           |
   |                                   | Tạo session mới    |
   |                                   |------------------->|
   |<--- Set-Cookie: session=<opaque> --|                    |
   |                                   |                    |
   | GET /orders + Cookie              |                    |
   |---------------------------------->| Tra session        |
   |                                   |------------------->|
   |                                   | Kiểm tra quyền     |
   |<----------------------------------| Trả đơn hàng       |
~~~

Browser chỉ giữ một session ID khó đoán trong cookie. Server có thể quản lý trạng thái phiên, mức xác thực, thiết bị, thời gian hoạt động và hiệu lực trực tiếp. Nếu server giữ access/refresh token để gọi API khác thì đây thường được gọi là mô hình **Backend for Frontend (BFF)** hoặc tương đương.

Ưu điểm: giảm phơi bày token nhạy cảm cho JavaScript ở browser; dễ thu hồi session tập trung; phù hợp web truyền thống và ứng dụng dùng BFF. Đánh đổi: cần session store có khả dụng tốt, chính sách cookie/CSRF, và chiến lược scale phù hợp.

### 2.2. Client OAuth/OIDC dùng access token

~~~text
Browser/Mobile Client          Authorization Server          Resource API
       | /authorize + PKCE ---------->|                             |
       |<---- authorization code -----|                             |
       | code + PKCE verifier ------->|                             |
       |<---- access token -----------|                             |
       | Authorization: Bearer token ------------------------------->|
       |                                             Kiểm tra token |
       |                                             + quyền truy cập
       |<------------------------------------------------ kết quả --|
~~~

Trong **OAuth 2.0**, access token được cấp để truy cập tài nguyên thay mặt chủ thể hoặc theo quyền của client. Đăng nhập/định danh người dùng thường dùng **OpenID Connect (OIDC)** trên nền OAuth, kèm cơ chế xác minh ID token và luồng đăng nhập.

Đối với ứng dụng công khai (public client) như mobile hoặc SPA, **Authorization Code Flow với PKCE** là lựa chọn nền tảng. Không dựa vào client secret nhúng trong mã browser/mobile để bảo mật, vì secret đó có thể bị trích xuất. Chọn nơi giữ refresh token theo loại client, khả năng lưu bí mật và chính sách của nhà cung cấp danh tính.

### 2.3. Service-to-service / machine identity

Service A gọi Service B không nhất thiết cần session người dùng. Nó có thể sử dụng mTLS, OAuth client credentials hoặc cơ chế workload identity tương đương. Access token dành cho service phải có **audience, scope và quyền phù hợp**, không gắn nhầm quyền cá nhân.

Nếu Service A làm việc thay mặt người dùng, cần thiết kế rõ luồng **delegation / token exchange / on-behalf-of** khi có hỗ trợ. Tránh chuyển tiếp nguyên một bearer token của người dùng qua mọi service nếu token đó có audience hoặc quyền quá rộng.

## 3. Chu kỳ xác thực nhìn từ trạng thái

Một vòng đời tiêu biểu:

~~~text
Chưa xác thực
    |
    | Xác minh credential + chính sách MFA / risk
    v
Đã xác thực
    |
    | Tạo session / cấp token giới hạn
    v
Đang hoạt động
    |   |                 |
    |   | Access token    | Hoạt động nhạy cảm
    |   | hết hạn         | → step-up / re-authentication
    |   v                 |
    | Gia hạn có kiểm soát |
    |_____________________|
    |
    +--> Hết idle/absolute timeout --> Kết thúc phiên
    +--> Người dùng logout ---------> Thu hồi trạng thái liên quan
    +--> Phát hiện rủi ro ----------> Khóa/thu hồi/đòi xác thực lại
    +--> Đổi mật khẩu hoặc MFA -----> Đánh giá thu hồi phiên
~~~

Vòng đời không chỉ có “đăng nhập thành công” và “logout”. Cần đặc tả sự kiện làm đổi trạng thái, bên nào chịu trách nhiệm, và sự kiện đó có hiệu lực ở đâu. **Hết hạn**, **thu hồi**, **vô hiệu hóa tài khoản** và **xóa cookie** là bốn việc khác nhau.

### 3.1. Credential được tạo và sử dụng

Đối với mật khẩu, server không lưu mật khẩu nguyên văn hay mã hóa hai chiều để kiểm tra lại. Lưu **password hash chống đoán brute force** như Argon2id theo tham số được đánh giá định kỳ hoặc thuật toán đáp ứng chính sách hiện hành; dùng salt riêng, có thể thêm pepper được quản lý trong secret store. Khi xác thực, kiểm tra bằng hàm hash tương ứng, giới hạn tốc độ thử và giám sát bất thường.

Đối với passkey/WebAuthn, server xác minh challenge, origin/RP ID, chữ ký và các điều kiện liên quan; bí mật khóa riêng được giữ theo mô hình authenticator, không gửi khóa riêng cho server. Với MFA, cần phân biệt đăng ký thiết bị, xác minh yếu tố thứ hai, hủy thiết bị, mã khôi phục và chính sách chống phishing phù hợp.

### 3.2. Session được thiết lập

Sau khi xác thực thành công, server cấp **session ID mới** có entropy đủ lớn, bảo đảm ID trước xác thực không tiếp tục dùng trong trạng thái đặc quyền. Việc thay session ID giúp giảm **session fixation**. Lưu session record với thông tin cần thiết theo nguyên tắc tối thiểu: user ID, thời điểm cấp, thời điểm cuối hoạt động, thời hạn tuyệt đối, trạng thái thu hồi, mức xác thực, metadata thiết bị ở mức phù hợp.

### 3.3. Token được cấp

Issuer quyết định claim, đối tượng nhận, quyền, tuổi thọ và phương thức ký/tra cứu. Resource server phải kiểm tra token theo **hợp đồng tin cậy cụ thể**, rồi thực hiện authorization theo tài nguyên và hành động.

### 3.4. Gia hạn

Khi access token hết hạn, client có thể xin token mới bằng refresh token hợp lệ hoặc BFF có thể cấp token cho API dựa trên session và cơ chế OAuth tương ứng. Gia hạn phải có kiểm soát về tuổi đời, rủi ro, số lần và trạng thái thu hồi. Không nên vô hạn kéo dài phiên chỉ vì client còn gửi request.

### 3.5. Kết thúc và thu hồi

Logout có thể xóa cookie phía client, xóa session record ở server, thu hồi refresh token liên quan và/hoặc vô hiệu hóa grant/token tại authorization server. Một access token tự chứa đã phát hành có thể vẫn được một số resource server chấp nhận đến khi hết hạn, nếu không có tra cứu trạng thái thu hồi. Cần xác định rõ **mức độ thu hồi tức thời cần đạt**.

## 4. Access token: định dạng, giới hạn và xác minh

### 4.1. Opaque token hay JWT?

**Opaque token** là chuỗi không có ý nghĩa nghiệp vụ đối với bên nhận. API cần tra cứu một hệ thống tin cậy hoặc **token introspection** để biết token có còn active và mang những quyền gì. Ưu điểm: kiểm soát trạng thái tập trung dễ hơn; nhược điểm: tăng phụ thuộc vào nơi tra cứu, cache và thời gian phản hồi.

**JWT** (JSON Web Token) thường gồm header, payload và chữ ký theo một định dạng gọn. JWT cho phép resource server xác minh các claim được ký mà không nhất thiết gọi issuer mỗi request. Ưu điểm: giảm số lần tra cứu; nhược điểm: khó thu hồi tức thì nếu tất cả API chỉ dựa vào chữ ký và thời hạn. JWT **được ký không có nghĩa payload được mã hóa**: người cầm token thường đọc được claim.

Không đánh giá token “an toàn hơn” chỉ vì nó là JWT. Chọn định dạng theo mô hình tin cậy, yêu cầu thu hồi, nhu cầu tra cứu, số hệ thống nhận và cách quản lý khóa.

### 4.2. Các claim quan trọng của JWT access token

Ví dụ payload minh họa, không phải hợp đồng chung cho mọi issuer:

~~~json
{
  "iss": "https://identity.example.com",
  "sub": "user-123",
  "aud": "orders-api",
  "exp": 1790000900,
  "iat": 1790000000,
  "nbf": 1790000000,
  "jti": "random-unique-token-id",
  "scope": "orders:read orders:create"
}
~~~

| Claim | Vai trò kiểm tra |
|---|---|
| iss (issuer) | Token do đúng nhà phát hành được tin cậy cấp |
| aud (audience) | Token được cấp **cho đúng API này** |
| exp (expiration) | Token chưa quá hạn |
| nbf (not before) | Chưa sử dụng trước thời điểm cho phép |
| iat (issued at) | Thời điểm cấp, có thể hỗ trợ chính sách tuổi token |
| sub (subject) | Chủ thể mà token đại diện |
| scope/permissions | Phạm vi quyền được cấp cho lần truy cập này |
| jti | Định danh token dùng cho theo dõi hoặc chính sách thu hồi khi có state |

Claim cụ thể tùy hợp đồng issuer và profile token đang dùng. Một JWT hoàn toàn hợp lệ về chữ ký nhưng có **aud=payments-api** không được API Orders dùng như access token của mình. Một ID token có **aud** dành cho OIDC client cũng không được dùng làm access token của Orders.

### 4.3. Chuỗi kiểm tra access token

~~~text
Request tới Orders API
    |
    +-- Có token đúng vị trí và đúng định dạng?
    +-- Chữ ký / MAC hợp lệ theo thuật toán được cho phép?
    +-- Khóa xác minh có thuộc issuer được cấu hình tin cậy?
    +-- iss, aud, exp, nbf và các claim bắt buộc hợp lệ?
    +-- Token có active, bị thu hồi hoặc bị chặn theo chính sách không?
    +-- Scope / role cho phép gọi endpoint này không?
    +-- Người dùng/tenant có được thao tác với đơn hàng cụ thể không?
    |
    +-- Nếu qua tất cả → thực thi nghiệp vụ
~~~

Cần **pin/allowlist thuật toán** phù hợp với issuer và thư viện; không chấp nhận thuật toán do token tự chọn khi chưa kiểm soát. Không tải khóa từ URL tùy ý trong header JWT. Nếu tra khóa theo key ID (kid), chỉ chọn trong tập khóa của issuer đã được cấu hình tin cậy. Cache khóa công khai theo chính sách với khả năng cập nhật khi issuer xoay khóa; không bỏ qua xác minh chữ ký chỉ vì endpoint lấy khóa tạm lỗi.

Phân biệt quyền cấp **ở cấp API** với **quyền trên đối tượng cụ thể**. Scope “orders:read” chưa đủ để kết luận user-123 được xem order thuộc user-456. Quyết định cuối phải dựa trên dữ liệu ownership, tenant, chính sách và trạng thái nghiệp vụ.

### 4.4. Token là bearer credential

Bearer token hoạt động theo nguyên tắc: bên nào sở hữu token thường có thể dùng token trong giới hạn của nó. Vì vậy:

- Truyền token qua kết nối HTTPS/TLS được xác thực.
- Với API HTTP, thường gửi access token trong header Authorization theo Bearer scheme; tránh nhét vào URL query vì URL dễ nằm trong log, lịch sử trình duyệt, referer và công cụ quan sát.
- Không ghi access/refresh token nguyên văn vào application log, exception, tracing attribute, analytics hoặc ticket hỗ trợ.
- Chỉ cấp audience/scope tối thiểu và tuổi token phù hợp.
- Đối với rủi ro cao, xem xét token gắn với người giữ khóa như DPoP hoặc mTLS theo khả năng của client và server. Chúng giảm nguy cơ token bị phát lại khi chỉ có chuỗi token bị lộ, nhưng vẫn có giới hạn và cần kiểm tra đúng cơ chế proof/binding.

## 5. Session trình duyệt: cookie, timeout và ranh giới bảo vệ

### 5.1. Cookie phiên an toàn

Ví dụ header minh họa:

~~~http
Set-Cookie: __Host-session=<random-opaque-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Ý nghĩa của các thuộc tính:

- **Secure:** cookie chỉ được gửi qua kết nối bảo mật theo quy tắc trình duyệt; ứng dụng vẫn phải dùng HTTPS và chính sách TLS/HSTS thích hợp.
- **HttpOnly:** JavaScript trong trang không thể đọc trực tiếp cookie này. Nó không chặn hoàn toàn XSS thực hiện hành động dưới quyền của người dùng.
- **SameSite:** giảm một số trường hợp gửi cookie trong yêu cầu cross-site. Giá trị Lax/Strict/None phải phù hợp nhu cầu đăng nhập/redirect; **SameSite không thay thế đánh giá CSRF**.
- **Path=/:** đường dẫn cookie hợp lệ.
- **Tiền tố __Host-:** trình duyệt có hỗ trợ áp dụng các ràng buộc như Secure, Path=/ và không có Domain; giúp giảm một số rủi ro nhầm phạm vi cookie.

Không đặt Domain rộng hơn cần thiết và không đưa session ID vào query string. Nếu hệ thống cần cookie cross-site (ví dụ một số tích hợp), cấu hình và phòng chống CSRF phải được thiết kế cẩn trọng; không sao chép máy móc mẫu cookie ở trên cho mọi ngữ cảnh.

### 5.2. CSRF khác XSS

**CSRF:** browser tự động gửi cookie khi bị một trang khác kích hoạt request, khiến ứng dụng nhận một thao tác mà người dùng không cố ý thực hiện. Kiểm soát bằng token CSRF, SameSite, xác minh Origin/Referer phù hợp và chính sách endpoint; không xem CORS là một hệ thống authorization.

**XSS:** mã độc chạy trong ngữ cảnh trang có thể gọi API như chính ứng dụng, đọc dữ liệu phản hồi mà nó được phép truy cập và thao tác dưới quyền người dùng. HttpOnly làm giảm khả năng trực tiếp đánh cắp cookie, nhưng vẫn cần chống XSS từ đầu: output encoding, tránh DOM sink nguy hiểm, CSP phù hợp và kiểm soát dependency.

### 5.3. Idle timeout và absolute timeout

Hai loại timeout phục vụ hai mục đích:

| Loại | Ý nghĩa | Cơ chế thường gặp |
|---|---|---|
| Idle timeout | Kết thúc phiên sau một khoảng không có hoạt động đủ điều kiện | Theo dõi lastActivity theo policy, cập nhật có giới hạn |
| Absolute timeout | Kết thúc phiên sau thời gian tối đa kể từ khi lập, bất kể còn hoạt động | createdAt + maxLifetime |
| Re-authentication / step-up | Đòi xác thực mới hoặc yếu tố mạnh hơn khi thao tác nhạy cảm | So thời điểm và mức xác thực với yêu cầu thao tác |

Ví dụ: session có idle timeout 20 phút và absolute timeout 12 giờ là một **cấu hình minh họa**, không phải mặc định phù hợp mọi ứng dụng. Ứng dụng tài chính, quản trị, công cụ nội bộ và dịch vụ tiêu dùng có mức rủi ro khác nhau. Đồng hồ server phải là cơ sở quyết định; không tin cậy hoàn toàn thời gian do browser gửi.

Không nên gia hạn idle timestamp trên mọi request tự động như health/polling định kỳ nếu điều đó khiến người dùng không bao giờ thực sự hết phiên. Quy định “hoạt động” cần có chủ đích.

### 5.4. Session fixation và đăng nhập nhiều thiết bị

Sau đăng nhập hoặc nâng quyền, nên tạo session ID mới và gắn trạng thái xác thực mới vào ID đó. Khi logout một thiết bị, có thể chỉ vô hiệu hóa session cụ thể; khi “logout khỏi mọi thiết bị”, hệ thống cần biết và thu hồi tất cả session/refresh token liên quan theo hợp đồng.

Session cần một định danh ổn định phía server để theo dõi hoạt động. Có thể lưu thiết bị/lần đăng nhập phục vụ người dùng tự quản lý, nhưng phải hạn chế fingerprinting xâm lấn và lộ thông tin không cần thiết.

## 6. Refresh token: gia hạn và chống phát lại

Refresh token có thể cho phép client lấy access token mới nhiều lần mà không đòi người dùng nhập lại credential. Vì có vòng đời dài và giá trị cao, refresh token cần mức bảo vệ cao hơn access token thông thường.

### 6.1. Chính sách cấp và lưu

- Chỉ cấp cho client và luồng thực sự cần khả năng gia hạn.
- Sử dụng secure storage phù hợp loại client, chẳng hạn BFF/server vault hoặc cơ chế lưu an toàn của hệ điều hành cho mobile; tránh đưa refresh token vào JavaScript-accessible storage khi có thể giữ phía server.
- Ràng buộc refresh token vào client/grant và các điều kiện bảo mật phù hợp.
- Dùng thời hạn sống tối đa, idle expiry và sự kiện thu hồi tùy rủi ro.
- Không log giá trị token; với token tra cứu state, thường lưu **hash/định danh tra cứu an toàn** để giảm ảnh hưởng nếu DB bị đọc.

### 6.2. Refresh token rotation

Mô hình rotation thường cấp refresh token **mới** khi dùng refresh token **cũ** hợp lệ và làm mất hiệu lực token cũ. Điều này giúp phát hiện tình huống token cũ bị dùng lại.

~~~text
Client             Authorization Server               Token Store
  | RT-1 + grant ---------->|                               |
  |                         | Kiểm tra RT-1 còn active       |
  |                         |------------------------------>|
  |                         | Đánh dấu RT-1 consumed         |
  |                         | Tạo RT-2 trong cùng transaction
  |<----- AT-2 + RT-2 ------|                               |
  |
  | RT-1 bị dùng lại ------>|                               |
  |                         | Phát hiện reuse; áp dụng policy
  |<--- Từ chối / thu hồi --| của token family / grant       |
~~~

**Yêu cầu quan trọng:** thao tác “kiểm tra và đánh dấu đã dùng” cần tính nguyên tử. Nếu hai request refresh cùng lúc cùng đọc RT-1 là active rồi đều nhận token mới, rotation mất ý nghĩa.

Ví dụ pseudocode cho store có transaction hoặc compare-and-swap:

~~~text
begin transaction
  record = lookup_by_hash(hash(presented_refresh_token))

  require record.active
  require not record.expired
  require record.client_id == authenticated_client
  require record.grant still valid

  mark record as consumed atomically
  create successor refresh token record with same family/grant
  issue bounded access token
commit

return new access token + new refresh token
~~~

Đây là mô hình logic, không phải code đầy đủ cho nhà cung cấp danh tính. Trong thực tế phải xử lý an toàn các trường hợp network timeout sau khi server commit nhưng client không nhận RT-2, request refresh đua nhau giữa các tab, và chính sách reuse detection. Một lựa chọn là client/BFF có cơ chế **single-flight refresh** để cùng một phiên không tự phát nhiều yêu cầu refresh đồng thời. Đừng vô tình coi mọi race hợp lệ của client là dấu hiệu xâm nhập rồi khóa toàn bộ người dùng mà không thiết kế chính sách.

### 6.3. Token family và reuse detection

Các refresh token kế tiếp thuộc một phiên cấp quyền có thể được liên kết trong **token family**. Nếu RT cũ bị dùng sau khi đã tiêu thụ, issuer có thể từ chối và thu hồi token family để giảm rủi ro kẻ tấn công đang giữ token. Hành vi cụ thể cần theo hợp đồng issuer và mục tiêu trải nghiệm: không phải mọi lần dùng lại đều chứng minh được ai là kẻ tấn công, nhưng đều là tín hiệu phải xử lý.

Một số kiến trúc dùng sender-constrained refresh token thay thế hoặc bổ sung rotation. Không có công thức duy nhất cho mọi client.

## 7. Vòng đời của credential và secret

Để bảo vệ phiên đăng nhập, phải quản lý cả **credential gốc** và thông tin dùng để cấp/kiểm tra token.

### 7.1. Tạo và đăng ký

Đối với tài khoản người dùng, cần xác thực sở hữu kênh liên hệ theo yêu cầu sản phẩm, bảo vệ luồng đăng ký trước abuse, khởi tạo mật khẩu/passkey/MFA bằng giao thức phù hợp. Đối với máy/dịch vụ, cấp workload identity hoặc secret cho đúng service, đúng môi trường và đúng phạm vi quyền.

Không nhúng shared secret dài hạn trong mã nguồn, container image, ứng dụng mobile hoặc bundle JavaScript. Đưa secret vào secret manager/KMS hoặc hệ thống cấp danh tính workload thích hợp.

### 7.2. Lưu giữ và sử dụng

- **Password:** lưu bằng password hashing phù hợp, không lưu plaintext.
- **API key và refresh token tra cứu state:** giảm rủi ro lộ DB bằng cách lưu định danh/hash phù hợp; giá trị gốc chỉ trả khi tạo hoặc theo hợp đồng kiểm soát.
- **Private signing key:** lưu ở KMS/HSM hoặc nơi quản lý khóa có kiểm soát truy cập, audit và rotation.
- **MFA recovery codes:** cấp chuỗi ngẫu nhiên độc lập, chỉ hiện một lần khi phù hợp, lưu dạng verifier không tiết lộ giá trị gốc.
- **Passkey:** quản lý public key credential và metadata cần để xác minh, hỗ trợ quy trình thu hồi credential đã đăng ký.

### 7.3. Đổi, xoay và khôi phục

**Rotation** là cấp giá trị mới, chuyển hệ thống sang sử dụng giá trị mới và vô hiệu hóa giá trị cũ đúng lúc. Cần hỗ trợ giai đoạn chồng lấn khi có bên đang dùng key cũ, nhưng thời gian này phải được giới hạn.

**Password reset / account recovery** cần luồng xác minh độc lập, token một lần đủ ngẫu nhiên và thời hạn ngắn, tránh để lộ token reset trong log hay URL chuyển tiếp không kiểm soát. Sau reset, cân nhắc thu hồi session/refresh token và yêu cầu MFA/step-up theo mức rủi ro. Không để câu hỏi bảo mật dễ đoán trở thành đường vòng vượt qua MFA.

**Change email / enrollment MFA** cũng là thao tác nhạy cảm: cần xác thực lại hoặc step-up, thông báo cho chủ tài khoản theo chính sách và tránh để phiên bị chiếm âm thầm thay đổi kênh phục hồi.

### 7.4. Thu hồi khi nghi ngờ bị lộ

Kịch bản lộ secret nên có quy trình: xác định phạm vi, chặn quyền dùng credential, phát hành khóa/secret mới, cập nhật nơi dùng, thu hồi token/grant liên quan, kiểm tra log và phát hiện truy cập trái phép, truyền thông theo quy định. **Chỉ đổi mật khẩu chưa chắc vô hiệu hóa access token hoặc session đang tồn tại**, nếu kiến trúc không liên kết sự kiện đổi mật khẩu với hệ thống session/token.

### 7.5. Xóa và kết thúc vòng đời

Khi người dùng đóng tài khoản hoặc service ngừng vận hành, cần vô hiệu hóa credential, session, refresh token, API key và quyền liên quan. Việc xóa dữ liệu cá nhân và log tuân theo chính sách lưu giữ; không giữ token bí mật vô thời hạn chỉ để “debug”.

## 8. Logout và thu hồi token trong hệ thống phân tán

Từ góc nhìn người dùng, “Đăng xuất” thường có nghĩa: **thiết bị này không còn tiếp tục truy cập với trạng thái đăng nhập vừa có**. Để đạt kỳ vọng đó, các thành phần cần thống nhất phạm vi thu hồi.

| Thành phần | Sau logout, nên xử lý gì? | Giới hạn cần biết |
|---|---|---|
| Browser | Xóa cookie phiên đúng Path/Domain và các token phía client được quản lý | Chỉ xóa phía client không chặn bản sao token đã lộ |
| BFF / Session Store | Hủy session record hoặc đánh dấu revoked | Có thể cần lan truyền đến nhiều replica/cache |
| Authorization Server | Thu hồi refresh token/grant phù hợp và cập nhật trạng thái | Phụ thuộc cơ chế của issuer |
| Resource API | Từ chối request mới khi trạng thái thu hồi có hiệu lực | JWT tự chứa có thể còn hợp lệ trước exp |
| Audit/monitoring | Ghi sự kiện logout/forced revocation không lộ secret | Không dựa vào audit như cơ chế chặn truy cập |

**Thu hồi access token tức thời** có thể cần token introspection, denylist theo jti, version/session epoch, hoặc cơ chế xác minh state khi API nhận request. Các cơ chế này tăng truy cập mạng/cache hoặc state và đặt ra bài toán nhất quán khi trạng thái thu hồi lan truyền chậm. Access token ngắn hạn giúp thu nhỏ cửa sổ rủi ro, nhưng không giải quyết yêu cầu thu hồi ngay lập tức nếu nghiệp vụ đòi hỏi điều đó.

Đặc tả rõ thời gian tối đa thu hồi có hiệu lực ở từng dịch vụ. Ví dụ “logout all devices phải chặn truy cập mới trong 30 giây” là yêu cầu kiểm chứng được; “logout phải an toàn” quá chung để triển khai.

### 8.1. Vấn đề cache và đồng hồ

Resource server cache introspection result có thể tiếp tục coi token active sau khi issuer đã thu hồi. Nếu cache TTL là 60 giây, đó có thể là một phần độ trễ thu hồi, trừ khi có cơ chế invalidation khác. Tương tự, JWT validator cho phép clock skew nhỏ để xử lý sai lệch đồng hồ, nhưng skew quá lớn vô tình nới cửa sổ chấp nhận token hết hạn.

### 8.2. Mất kết nối với nơi xác thực

Nếu resource server không lấy được khóa công khai hoặc introspection response:

- Với dữ liệu khóa đã cache và vẫn hợp lệ theo chính sách, có thể tiếp tục xác minh JWT theo trust policy.
- Với token opaque cần tra cứu mà không thể xác định trạng thái, không tự ý cho qua như đã active.
- Với đường thao tác nhạy cảm, chọn hành vi fail closed thích hợp. Với dữ liệu ít rủi ro, chế độ suy giảm nếu có phải được thiết kế từ trước, chứ không mặc định bỏ qua xác thực.

## 9. Ranh giới bảo mật trong microservices

~~~text
                  +---------------------------+
Browser / Mobile -> API Gateway / BFF         |
                  |  Bảo vệ kết nối, routing   |
                  +---------------------------+
                          |
            +-------------+--------------+
            |                            |
            v                            v
       Orders API                    Profile API
       - kiểm token                 - kiểm token
       - kiểm audience              - kiểm audience
       - kiểm scope                 - kiểm scope
       - kiểm owner/tenant          - kiểm owner/tenant
            |                            |
            v                            v
      Order Database                Profile Database
~~~

Gateway có thể chặn request thiếu token và giảm lượng traffic xấu, nhưng **downstream vẫn phải thực thi ranh giới tin cậy**. Nếu Orders API có thể bị gọi nội bộ từ service khác, chỉ tin header “X-User-Id” do client tự đặt là nguy hiểm. Nếu sử dụng identity headers, gateway cần xóa header do client gửi, thiết lập lại theo ngữ cảnh đã xác thực và bảo vệ kênh nội bộ; downstream phải xác định caller được tin cậy.

### 9.1. Audience và nguyên tắc quyền tối thiểu

Một access token dành cho Billing API không nên dùng tại Orders API. Với đường gọi service-to-service, yêu cầu quyền và audience tương ứng service nhận. Không dùng một “super token” có tất cả scope cho mọi microservice chỉ để đơn giản hóa tích hợp.

Token exchange hoặc quyền delegation giúp phát hành token thứ cấp cho đúng dịch vụ nhận khi có hỗ trợ. Quyền thực thi phải bị giới hạn bởi quyền của người dùng, quyền của service và chính sách nghiệp vụ.

### 9.2. Tenant isolation và đối tượng tài nguyên

Phải kiểm tra tenant/owner khi truy cập record, object storage, event và cache. Nếu user thuộc Tenant A có scope “orders:read” nhưng API truy vấn order theo ID không kèm tenant boundary, lỗi **broken object-level authorization** có thể xảy ra dù token hợp lệ.

Một pattern ứng dụng: repository query gồm cả order ID và tenant ID đã được xác minh; không dùng tenant ID do request body tự khai nếu chưa được ràng buộc vào danh tính/ủy quyền.

### 9.3. Tránh phụ thuộc đồng bộ không cần thiết

Khi mọi request phải gọi authorization server từ nhiều tầng, identity service có thể trở thành điểm nghẽn. Cache khóa công khai có thời hạn, token validation cục bộ, introspection cache theo mức rủi ro và session store HA giúp cân bằng khả dụng với yêu cầu thu hồi. Không tối ưu khả dụng bằng việc bỏ kiểm tra issuer, audience, chữ ký hoặc trạng thái quyền nhạy cảm.

### 9.4. Session store là một failure domain

Hệ thống stateful session nên thiết kế session store có bảo vệ truy cập, replication/HA, backup, TTL và chính sách khi store lỗi. Nếu một cluster Redis chứa session cho toàn bộ website bị mất, blast radius có thể là tất cả người dùng đang đăng nhập. Tách cache thông thường khỏi session security state hoặc chia vùng theo workload khi yêu cầu độ tin cậy cho phép.

## 10. Lựa chọn nơi lưu token theo loại client

| Client | Hướng triển khai thường phù hợp | Rủi ro trọng tâm |
|---|---|---|
| Web với BFF | Browser giữ cookie session HttpOnly; BFF giữ token server-side | CSRF, XSS thực hiện hành động, session store |
| SPA gọi API trực tiếp | Authorization Code + PKCE; thiết kế token storage và vòng đời theo threat model | XSS và đánh cắp token trong môi trường JS |
| Native mobile | Authorization Code + PKCE, system browser khi phù hợp, OS secure storage | Thiết bị mất, app độc hại, backup/debug leak |
| Backend tích hợp | Workload identity, OAuth client credentials, mTLS hoặc secret được quản lý | Rò rỉ private key/client secret, phân quyền quá rộng |
| CLI / thiết bị hạn chế input | Luồng được issuer hỗ trợ như device authorization hoặc cơ chế phù hợp | Phishing, verification URI giả, token lưu trên thiết bị dùng chung |

Đừng xem localStorage hay sessionStorage là “kho bí mật” vì mã JavaScript chạy trong origin có thể đọc chúng. Cookie HttpOnly giảm khả năng JS đọc cookie, nhưng browser sẽ tự gắn cookie cho request thuộc phạm vi, nên cần bảo vệ CSRF và XSS. Không có lựa chọn lưu token phổ quát; hãy bắt đầu bằng threat model và khả năng kiểm soát client.

## 11. HTTP status và lỗi trong API

Một số cách biểu diễn phổ biến:

- **401 Unauthorized:** request chưa có thông tin xác thực hợp lệ hoặc token hết hạn/không xác minh được. Có thể trả cơ chế challenge thích hợp khi API dùng Bearer.
- **403 Forbidden:** caller đã được xác thực nhưng không có quyền với thao tác/tài nguyên.
- **429 Too Many Requests:** vượt giới hạn tốc độ hoặc chính sách chống abuse; phản hồi có thể kèm gợi ý thời gian retry.
- **5xx:** lỗi hạ tầng/thực thi. Không nên biến mọi lỗi xác thực thành 500 hoặc âm thầm trả quyền truy cập.

Tránh lộ chi tiết nội bộ như secret, stack trace, token value, tồn tại hay không của tài khoản trong những luồng có thể bị user enumeration. Thông báo người dùng cần hữu ích nhưng không tiết lộ tín hiệu cho kẻ tấn công.

### Ví dụ một API kiểm tra quyền đơn hàng

~~~text
GET /orders/ord-456
Authorization: Bearer <access-token>

1. Kiểm tra TLS và token hợp lệ cho orders-api.
2. Xác định subject và tenant từ ngữ cảnh đã xác thực.
3. Kiểm tra quyền orders:read.
4. Đọc order theo order ID + tenant boundary từ dữ liệu đáng tin.
5. Kiểm tra owner / business policy và trạng thái tài nguyên.
6. Trả kết quả đã lọc trường dữ liệu theo quyền, hoặc lỗi phù hợp.
~~~

Không dùng “token đã được xác minh tại gateway” làm lý do bỏ qua bước 3–5 trong API nghiệp vụ.

## 12. Tấn công thường gặp và cơ chế phòng vệ

| Rủi ro | Sai lầm dẫn tới rủi ro | Cơ chế hạn chế |
|---|---|---|
| Token bị lộ qua log/URL | Ghi Authorization header hoặc access token vào query | Redaction, HTTPS, bỏ token khỏi log/tracing |
| Session hijacking | Session ID bị lấy cắp, không có timeout/thu hồi | Cookie an toàn, giới hạn phiên, phát hiện rủi ro, re-auth |
| Session fixation | Dùng lại session ID trước và sau đăng nhập | Regenerate session sau authentication |
| CSRF | Browser dùng cookie tự động, endpoint đổi trạng thái thiếu bảo vệ | CSRF token, SameSite, Origin check phù hợp |
| XSS | Render HTML/JS không an toàn | Encoding, tránh dangerous sinks, CSP, kiểm soát dependency |
| Token replay | Bearer token bị sao chép và sử dụng nơi khác | Token ngắn hạn, rotation/revoke, sender-constraining khi phù hợp |
| Refresh token reuse | RT cũ vẫn dùng được hoặc refresh song song không nguyên tử | Rotation atomically, reuse detection, single-flight |
| JWT algorithm/key confusion | Tin thuật toán hoặc nguồn khóa do token tự chỉ định | Allowlist thuật toán, issuer-bound JWKS, kiểm chữ ký |
| Token mix-up / wrong audience | API nhận token dành cho client/API khác | Kiểm issuer, audience, loại token và hợp đồng claim |
| Broken object authorization | Chỉ kiểm scope mà bỏ qua owner/tenant | Policy tại resource, truy vấn có tenant boundary |
| Credential stuffing | Thử password bị lộ hàng loạt | Rate limit/risk controls, MFA/passkey, giám sát bất thường |
| Recovery abuse | Reset/MFA recovery dễ bị chiếm | Token một lần, proof phù hợp, thông báo, step-up |
| Secret/key leakage | Lưu key trong repo, image, frontend | Secret manager/KMS, quyền tối thiểu, rotation, audit |
| Cấu hình token lifetime quá dài | Token còn giá trị lâu sau khi lộ | TTL theo rủi ro, thu hồi, giám sát, giới hạn scope |

Không một cơ chế nào tự mình thay thế những lớp còn lại. Ví dụ PKCE bảo vệ một số rủi ro của authorization code flow, nhưng không làm cho access token bị lộ trong runtime client trở nên vô hại.

## 13. Thiết kế chính sách thời hạn và thu hồi

Thay vì sao chép một con số cố định, đặt ra các yêu cầu:

1. **Dữ liệu và thao tác nhạy cảm đến đâu?** Đọc dữ liệu công khai, xem hồ sơ, chuyển tiền và thay đổi MFA có thể cần mức xác thực khác nhau.
2. **Client có giữ bí mật được không?** Browser JS, mobile, BFF và backend có bề mặt tấn công khác nhau.
3. **Token bị lộ gây hại trong bao lâu?** TTL access token và yêu cầu thu hồi phải dựa trên giới hạn rủi ro.
4. **Phiên có thể tồn tại lâu đến mức nào?** Quy định idle và absolute session timeout, chính sách “remember me”, rủi ro của thiết bị dùng chung.
5. **Thu hồi phải có hiệu lực trong bao lâu?** Tức thì, vài giây hay đến khi access token hết hạn? Mỗi lựa chọn ảnh hưởng tới cache, API latency và availability.
6. **Có cần xác thực lại ở bước nhạy cảm không?** Yêu cầu re-auth cho đổi mật khẩu, thêm phương thức MFA, thanh toán lớn hoặc xuất dữ liệu theo chính sách.
7. **Người dùng có quản lý thiết bị được không?** Cần cho xem phiên đang hoạt động, logout một phiên hoặc tất cả phiên nếu sản phẩm yêu cầu.
8. **Hệ thống có ứng xử đúng khi issuer/session store lỗi không?** Phải có lựa chọn fail closed, cache an toàn và khả năng phục hồi đã được đánh giá.

### Ví dụ chính sách minh họa

Giả sử một ứng dụng bán hàng có browser với BFF:

- Session web dùng cookie HttpOnly + Secure; record ở server, có idle và absolute timeout.
- Access token gọi Orders API có thời hạn ngắn; audience là Orders API, scope chỉ đủ cho thao tác cần làm.
- BFF giữ refresh token tại server nếu issuer cấp, sử dụng rotation và bảo vệ single-flight khi làm mới.
- Khi người dùng logout, BFF hủy session và thu hồi các credential/token liên quan theo hợp đồng.
- Khi đổi email, mật khẩu hoặc MFA, yêu cầu step-up và đánh giá thu hồi session khác.
- Nếu Recommendations API lỗi, có thể dùng fallback chức năng phụ; nếu identity state không xác minh được, không tự bỏ qua authorization cho Orders/Payment.

Đây là **một phương án kiến trúc**, không phải quy định chung. Thời hạn cụ thể và cách thu hồi phải được xác nhận bằng threat model, SLO, yêu cầu pháp lý và khả năng của Identity Provider.

## 14. Quan sát và vận hành

### 14.1. Chỉ số nên có

| Tín hiệu | Ý nghĩa vận hành |
|---|---|
| Tỷ lệ login thành công/thất bại theo loại nguyên nhân | Phát hiện lỗi xác thực hoặc tăng tấn công thử mật khẩu |
| Tần suất MFA challenge, step-up, recovery | Quan sát khả năng sử dụng và rủi ro |
| 401/403 theo endpoint và tenant | Phát hiện lỗi token, quyền và thay đổi cấu hình |
| Refresh success/failure, token reuse detection | Phát hiện lỗi rotation, race hoặc nghi ngờ token bị lộ |
| Session active/revoked/expired | Kiểm chứng logout và chính sách vòng đời |
| Issuer/JWKS/introspection latency và error rate | Phát hiện dependency xác thực bị chậm hoặc lỗi |
| Token validation reject theo iss/aud/exp/signature | Phát hiện lỗi tích hợp hoặc token không đúng đối tượng |
| Key rotation progress | Bảo đảm khóa mới được dùng và khóa cũ đã hết cửa sổ cần thiết |
| Độ trễ revoke propagation | Kiểm chứng thời gian thu hồi hiệu lực ở API |
| Số yêu cầu bị rate limit và bất thường theo client | Phát hiện abuse, credential stuffing |

Không đưa raw token, password, OTP, refresh token hay secret vào nhãn metric/log. Nếu cần tương quan, dùng request ID, session record ID nội bộ hoặc ID đã biến đổi/giới hạn truy cập thay vì bí mật mang quyền truy cập.

### 14.2. Câu hỏi khi điều tra incident

- Lỗi phát sinh ở nhà cung cấp danh tính, BFF, session store, gateway hay API nghiệp vụ?
- Có bao nhiêu phiên/tài khoản/tenant bị ảnh hưởng, trong khoảng thời gian nào?
- Token có sai issuer/audience, hết hạn, chưa đến hiệu lực, chữ ký sai hay state đã bị revoke?
- Key rotation có khiến các API cache JWKS quá lâu không?
- Có đợt refresh đồng thời lớn, retry storm hay traffic bất thường làm bão hòa issuer?
- Logout/forced revoke đã có hiệu lực ở mọi service chưa?
- Có dữ liệu nhạy cảm hoặc token nào vô tình xuất hiện trong log, trace hay URL không?

Một hệ thống có tỷ lệ login thành công cao vẫn có thể tồn tại broken object authorization; metric authentication và authorization phải được theo dõi riêng.

## 15. Kiểm thử vòng đời token và session

| Tình huống | Kỳ vọng |
|---|---|
| Access token đúng issuer nhưng sai audience | API từ chối |
| JWT hết hạn hoặc chữ ký sai | API từ chối, không âm thầm bỏ qua |
| ID token được gửi thay access token | Resource API từ chối theo hợp đồng |
| Token hợp lệ nhưng truy cập đơn hàng của tenant khác | API từ chối ở tầng authorization |
| Session ID trước đăng nhập bị dùng lại sau đăng nhập | Không được thừa hưởng phiên đã xác thực |
| Browser cookie thiếu một lớp bảo vệ đã quy định | Cấu hình bị phát hiện qua test/kiểm tra triển khai |
| Idle timeout hoặc absolute timeout đã vượt | Phiên hết hiệu lực theo policy |
| Người dùng logout một thiết bị | Phiên đó bị chặn; phiên khác theo đúng hợp đồng |
| Người dùng logout tất cả thiết bị | Các phiên/refresh token liên quan bị thu hồi |
| Refresh token cũ bị dùng lại | Từ chối; áp dụng reuse policy và ghi tín hiệu điều tra |
| Hai tab refresh đồng thời | Client xử lý race đúng, không tạo nhiều token hợp lệ từ cùng RT cũ |
| Đổi mật khẩu/khôi phục tài khoản | Quy tắc step-up và thu hồi phiên được thực thi |
| Authorization Server tạm lỗi | Hành vi bảo mật và availability đúng theo thiết kế |
| Ký JWT bằng khóa cũ sau key rotation | Chấp nhận/từ chối theo cửa sổ rotation có kiểm soát |
| Header định danh do client tự gửi | Không được dùng làm user identity tin cậy |
| Access token xuất hiện trong log/tracing | Kiểm tra redaction phải phát hiện và chặn |

Kiểm thử nên có cả trường hợp **race condition**, phân tán nhiều instance, đồng hồ lệch nhẹ, mất mạng và phục hồi. Chỉ kiểm tra login/logout trên một process trong môi trường local là chưa phản ánh đủ vòng đời.

### Tình huống tự phân tích

Ứng dụng SPA giữ refresh token trong localStorage, access token sống 30 phút. Ba API microservices đều nhận bất kỳ JWT nào có chữ ký hợp lệ của issuer, không kiểm tra audience; logout chỉ xóa localStorage. Người dùng có thể xem dữ liệu theo order ID mà API không kiểm tra tenant.

Hãy xác định:

1. Những rủi ro xuất hiện từ nơi lưu refresh token và khả năng XSS?
2. Vì sao chữ ký đúng vẫn không đủ để API chấp nhận token?
3. Điều gì còn có thể xảy ra sau logout nếu token đã bị sao chép?
4. Vì sao token mang scope “orders:read” không đủ để bảo vệ order của tenant khác?
5. Nếu thiết kế lại với BFF, server-side session, issuer-bound validation, audience và chính sách thu hồi, thành phần nào chịu trách nhiệm cho mỗi quyết định?

**Gợi ý:** rủi ro ở đây gồm token theft, token confusion/wrong audience, thu hồi chưa thực sự có hiệu lực và broken object-level authorization. Cần giải quyết tại đúng trust boundary: client storage, session management, issuer/resource server validation, và business authorization.

## 16. Mẫu checklist thiết kế hệ thống

Trước khi đưa cơ chế đăng nhập/token vào production, đội phát triển cần xác định rõ:

- **Chủ thể:** người dùng, máy, ứng dụng hay delegated actor?
- **Nguồn danh tính:** issuer nào được tin cậy, dùng giao thức xác thực nào, có MFA/step-up không?
- **Loại token:** session ID, JWT/opaque access token, refresh token, ID token có vai trò nào và ai được nhận?
- **Điều kiện xác minh:** chữ ký/khóa, issuer, audience, thời hạn, trạng thái thu hồi, quyền và đối tượng tài nguyên.
- **Ranh giới lưu trữ:** cookie, server store, OS secure storage, vault/KMS; token có lọt vào browser JS, URL hoặc log không?
- **Thời hạn:** idle/absolute session timeout, access token TTL, refresh lifetime, key rotation overlap và re-authentication interval.
- **Gia hạn:** refresh rotation, tính nguyên tử, phát hiện reuse và xử lý concurrent refresh.
- **Thu hồi:** logout từng thiết bị/tất cả thiết bị, reset credential, khóa tài khoản, compromise response, SLA lan truyền.
- **Phân quyền:** kiểm tra quyền trên tenant/record, không chỉ role/scope tổng quát.
- **Khả dụng:** session store, JWKS, introspection, issuer outages; cách fail closed và phục hồi.
- **Quan sát:** metric, audit, anomaly detection, redaction; không lưu bí mật.
- **Kiểm thử:** happy path, hết hạn, sai audience, token replay, concurrency, logout, phục hồi và khoá xoay vòng.

## 17. Ghi nhớ cốt lõi

1. **Credential, login session và access token là ba khái niệm khác nhau.** Xác thực danh tính, duy trì phiên và cho phép truy cập tài nguyên cần chính sách và vòng đời riêng.
2. **Token hợp lệ không tự động chứng minh quyền trên một tài nguyên cụ thể.** API phải kiểm tra issuer, audience, thời gian, chữ ký, scope và authorization theo bản ghi/tenant.
3. **Access token và refresh token có giá trị rủi ro khác nhau.** Refresh token cần lưu đặc biệt an toàn, gia hạn có kiểm soát và xử lý replay/rotation.
4. **Logout phải có hợp đồng thu hồi rõ ràng.** Xóa token ở client chưa chắc vô hiệu hóa bản sao token mà người khác đã lấy được.
5. **Bảo vệ phiên đòi hỏi nhiều lớp:** cookie an toàn, CSRF/XSS controls, session rotation, timeout, re-authentication, secret management và quan sát.
6. **Trong microservices, xác thực ở gateway không thay thế authorization ở service.** Audience, tenant boundary và quyền đối tượng là những ranh giới bắt buộc phải thiết kế.
7. **Thiết kế vòng đời ngay từ đầu:** cấp, lưu, sử dụng, gia hạn, xoay, thu hồi, hết hạn, khôi phục và xử lý lộ credential đều ảnh hưởng trực tiếp đến mức an toàn và khả dụng của hệ thống.
