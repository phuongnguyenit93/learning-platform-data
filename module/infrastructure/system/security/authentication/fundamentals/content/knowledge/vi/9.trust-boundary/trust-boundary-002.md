# Client và server

## 1. Ranh giới tin cậy client–server là gì?

Trong một hệ thống xác thực, **trust boundary** (ranh giới tin cậy) là nơi dữ liệu hoặc yêu cầu chuyển từ một miền mà hệ thống không thể kiểm soát hoàn toàn sang miền có quy tắc xác minh và thẩm quyền riêng. Ranh giới phổ biến nhất là **client ↔ server**: trình duyệt, ứng dụng di động hoặc CLI gửi credential, assertion, cookie và yêu cầu nghiệp vụ tới một máy chủ xác thực hoặc API.

**Nguyên tắc nền tảng:** server không được coi dữ liệu do client tự khai là sự thật chỉ vì nó đến từ ứng dụng do chính nhóm phát triển viết. Người dùng có thể sửa JavaScript, gọi API trực tiếp, chỉnh request, chạy phiên bản app cũ, dùng công cụ tự động hoặc bị phần mềm độc hại điều khiển. Các lớp kiểm tra trên giao diện hữu ích cho trải nghiệm nhưng không có thẩm quyền thay thế xác minh phía server.

Ví dụ, frontend có thể ẩn nút “Xóa tài khoản” với tài khoản không có quyền. Một client tùy chỉnh vẫn có thể gửi lệnh xóa trực tiếp. Server phải xác minh **ai đang gọi**, **phiên/token có hợp lệ không**, **đã xác thực đủ mạnh chưa** và **người đó có quyền thực hiện thao tác với tài nguyên cụ thể không**.

Trong phạm vi module **SECURITY_AUTHENTICATION_FUNDAMENTALS**, ranh giới client–server xuyên suốt các phần credential, mật khẩu, MFA, passkey, chứng chỉ, token, session, liên kết danh tính và khôi phục tài khoản. Hiểu đúng ranh giới này giúp phòng phishing, replay, lạm dụng đăng nhập, chiếm phiên và lỗi ủy quyền.

Sau bài học, người học có thể:

- Xác định nguồn dữ liệu **không đáng tin theo mặc định** ở từng bước đăng nhập và gọi API.
- Phân biệt kiểm tra trải nghiệm trên client với **xác minh và quyết định bảo mật** trên server.
- Mô hình hóa luồng mật khẩu + MFA, WebAuthn/passkey, cookie session và OAuth/OIDC qua các ranh giới.
- Thiết kế phương thức bảo vệ chống CSRF, XSS, replay, session fixation, phishing và giả mạo header.
- Kiểm thử việc vượt qua giao diện, sửa request, thay đổi principal và gọi endpoint trực tiếp.

## 2. Client nằm ngoài miền kiểm soát của server

“Client” có thể là nhiều thành phần khác nhau; mức bảo vệ kỹ thuật không giống nhau, nhưng **không nên mặc định client có thẩm quyền quyết định danh tính hoặc quyền**.

| Loại client | Có thể làm gì hợp lệ? | Điều server không được tự tin |
| --- | --- | --- |
| **Trình duyệt web** | Hiển thị UI, nhận thao tác, thực thi WebAuthn và gửi request | DOM, JavaScript, hidden input, localStorage, trạng thái đăng nhập do UI tính |
| **Ứng dụng di động** | Gọi API, dùng kho khóa của hệ điều hành, kích hoạt sinh trắc cục bộ | Mọi bản app đều nguyên vẹn; device flag/root flag gửi lên là sự thật |
| **Ứng dụng desktop/CLI** | Mở luồng ủy quyền, dùng token/credential đã được cấp | Bí mật hard-code bên trong binary luôn giữ bí mật |
| **Máy khách bên thứ ba** | Gọi endpoint theo giao thức công khai | Sẽ tuân thủ ràng buộc UI hoặc logic của ứng dụng chính |
| **Bot/script** | Tạo request phù hợp cú pháp HTTP | Có tương tác con người thật; đã hoàn thành CAPTCHA hoặc bước MFA chỉ vì gửi một cờ |
| **Service client** | Gọi API bằng mTLS, client assertion hoặc token được cấp | Header tự khai về service identity hoặc certificate text trong payload là chứng minh sở hữu private key |

Một trình duyệt có *same-origin policy* và một điện thoại có phần cứng bảo mật không có nghĩa rằng toàn bộ nội dung request đáng tin. Các cơ chế này bảo vệ một phần môi trường và giao thức, nhưng server vẫn phải kiểm tra **bằng chứng xác thực** và **chính sách truy cập**.

### 2.1. Phân biệt “client kiểm soát” và “server có thẩm quyền”

| Dữ liệu/hành vi | Client có thể đề xuất hoặc gửi | Bên có thẩm quyền xác minh/quyết định |
| --- | --- | --- |
| Username/email đăng nhập | Giá trị nhập | Server giải quyết danh tính, không mặc định tài khoản tồn tại |
| Mật khẩu/OTP | Bằng chứng ứng viên | Verifier kiểm tra bí mật, số lần thử, thời hạn và trạng thái flow |
| Challenge ID, nonce | Tham chiếu trong request | Server kiểm tra tính mới, binding, thời hạn và điều kiện tiêu thụ |
| User ID trong URL hoặc JSON | Đối tượng được yêu cầu | Server kiểm tra session/principal và quyền trên đối tượng đó |
| Trường role, isAdmin, mfaPassed | Có thể gửi tùy ý nếu API chấp nhận | Server phải bỏ qua hoặc so với dữ liệu có thẩm quyền |
| WebAuthn assertion | Chữ ký và dữ liệu authenticator | Server kiểm tra public key đăng ký, challenge, origin, RP ID và chính sách |
| Session cookie | Trình duyệt tự động gửi giá trị đã được cấp | Server tra cứu/kiểm tra phiên, TTL, rotation, revoke và ngữ cảnh |
| Access token | Client trình token với API | API xác minh issuer, audience, signature/introspection, thời hạn, scope và quyền |
| CAPTCHA/risk score | Một số tín hiệu từ widget/SDK | Server xác minh bằng chứng với bên phát hành và đánh giá chính sách |
| Redirect URI/callback | Client có thể đề xuất trong một số flow | Authorization Server chỉ chấp nhận giá trị phù hợp đăng ký và giao thức |

**Một kiểm tra bị bỏ qua ở server không thể được bù bằng một nút đã ẩn ở frontend.**

## 3. Hình dung luồng và các ranh giới tin cậy

~~~mermaid
flowchart LR
    subgraph UNTRUSTED[Client và môi trường do người dùng kiểm soát]
        U[Người dùng hoặc chương trình]
        B[Browser / Mobile / CLI]
        U --> B
    end
    subgraph SERVER[Hệ thống có thẩm quyền]
        G[Gateway / Reverse Proxy]
        A[Authentication Server]
        S[Session Store / Key Store]
        R[Resource Server / API]
        P[Policy và dữ liệu quyền]
        G --> A
        A <--> S
        G --> R
        R <--> P
    end
    B -->|TLS: request, credential, cookie, token| G
    A -->|Session, challenge, kết quả xác thực| B
    R -->|Response đã kiểm soát quyền| B
~~~

Sơ đồ giản lược hai miền. Trong hệ thống thật, còn có ranh giới phụ: **gateway → backend**, **backend → database**, **ứng dụng → IdP**, **authorization server → API**, và **thiết bị → authenticator**. Những thành phần nằm trong cùng trung tâm dữ liệu vẫn có thể thuộc các miền tin cậy khác nhau nếu quyền vận hành, khóa hoặc danh tính dịch vụ khác nhau.

Một giao dịch đi qua ranh giới nên tuân theo quy tắc **kiểm chứng tại điểm sử dụng**:

1. Dữ liệu vào được kiểm tra kiểu, kích thước, định dạng và ngữ nghĩa.
2. Credential hoặc token được kiểm chứng theo giao thức bởi bên có thẩm quyền.
3. Principal được lấy từ **kết quả đã xác minh**, không từ trường client tự khai.
4. Chính sách xác thực (MFA, freshness, step-up) được kiểm tra theo thao tác.
5. Authorization được thực thi tại API/server nơi tài nguyên được sử dụng.
6. Chỉ trả về dữ liệu được phép; mọi thông tin nhạy cảm cần được bảo vệ khi truyền và ghi log.

## 4. Ba loại niềm tin khác nhau

### 4.1. Tin rằng kênh truyền đúng

**TLS/HTTPS** giúp bảo vệ tính bí mật và toàn vẹn khi dữ liệu đi qua mạng và cho client cơ sở xác thực server theo chứng chỉ được kiểm tra đúng. HSTS có thể giúp giảm rủi ro hạ cấp HTTP đối với trình duyệt khi được cấu hình phù hợp.

Nhưng HTTPS **không chứng minh** người ở đầu client là chủ tài khoản. Một kẻ tấn công dùng cURL vẫn có thể gửi request HTTPS hợp lệ. Tương tự, TLS không ngăn JavaScript bị XSS, phần mềm độc hại trên máy khách hoặc người dùng tự sửa payload.

### 4.2. Tin rằng credential/token có giá trị

Server xác minh mật khẩu, TOTP, WebAuthn, certificate hoặc token theo giao thức tương ứng. Kết quả có thể xác nhận **quyền kiểm soát một authenticator đã đăng ký** hay rằng **một issuer tin cậy đã phát hành assertion** cho bên nhận cụ thể.

Độ tin cậy phụ thuộc việc kiểm tra đủ thông tin, chẳng hạn thời hạn, nonce/challenge, chữ ký, trạng thái thu hồi, subject và audience. Một chuỗi JWT giải mã được hoặc một certificate gửi dưới dạng văn bản **không đủ** để xác nhận danh tính.

### 4.3. Tin rằng thao tác được phép

Sau khi xác thực, server cần kiểm tra người dùng có quyền đối với **tài nguyên và hành động cụ thể**. Đây là authorization, khác authentication.

Ví dụ, session của người dùng A có thể đọc hồ sơ A. Nếu client đổi đường dẫn sang hồ sơ B, backend phải kiểm tra quyền trên B và từ chối khi không được phép. Lỗi tin vào userId trong request có thể tạo **IDOR/BOLA** (*Insecure Direct Object Reference / Broken Object Level Authorization*).

## 5. Mật khẩu và MFA: client chỉ cung cấp bằng chứng ứng viên

Xét flow đăng nhập mật khẩu + TOTP:

~~~mermaid
sequenceDiagram
    participant C as Client
    participant A as Auth Server
    participant D as Credential/Session Store
    C->>A: 1. Username + password qua HTTPS
    A->>D: 2. Kiểm chứng password hash và trạng thái account
    D-->>A: Kết quả kiểm tra
    A-->>C: 3. Challenge MFA (flowId, expiry)
    C->>A: 4. flowId + TOTP
    A->>D: 5. Kiểm tra binding, TOTP, rate limit, replay
    D-->>A: MFA result
    A->>D: 6. Tạo/rotate session, lưu auth context
    A-->>C: 7. Cookie session an toàn
    C->>A: 8. Request tiếp theo kèm cookie
    A->>D: 9. Kiểm tra session và policy
~~~

**Điểm quyết định:** Sau khi mật khẩu đúng nhưng MFA chưa hoàn tất, server phải giữ **trạng thái flow đang chờ** có phạm vi hạn chế. Không được cấp phiên có quyền truy cập đầy đủ chỉ vì giao diện đang hiển thị màn hình nhập OTP.

Một thiết kế sai:

~~~text
Client:
    if passwordResponse.ok:
        localStorage.setItem("mfaPassed", "true")

Request:
    POST /transfer
    { "userId": "alice", "mfaPassed": true, "amount": 1000 }

Server:
    if request.body.mfaPassed:
        executeTransfer()
~~~

Kẻ tấn công có thể gọi trực tiếp endpoint và gửi cờ *mfaPassed = true*. Dữ liệu đó không chứng minh OTP đã được verifier kiểm tra.

Thay bằng cách thiết kế theo thẩm quyền:

~~~text
Server:
    session = verifyAndLoadSession(request)
    if not session.valid:
        rejectUnauthenticated()

    principal = session.principal
    authContext = session.serverVerifiedAuthenticationContext

    if operation.requiresRecentMFA
       and not policy.meetsRequirement(authContext):
        requireStepUp()

    if not authorization.canTransfer(principal, request.accountId):
        rejectForbidden()

    executeTransferWithinBusinessRules()
~~~

Đây là **pseudocode**. Quyết định xác thực và quyền phải dùng trạng thái do server kiểm soát. Tham số số tiền, account ID, loại thao tác vẫn phải kiểm tra dữ liệu và quy tắc nghiệp vụ.

### 5.1. Ràng buộc thử thách với giao dịch

MFA challenge cần được gắn với **đúng flow, đúng principal, đúng hành động khi cần**, có thời hạn và giới hạn thử. Không chỉ kiểm tra “OTP khớp với tài khoản này” rồi chấp nhận nó cho mọi flow không liên quan.

TOTP cần chính sách chống đoán mã và sử dụng lại trong cửa sổ thời gian theo tiêu chuẩn áp dụng. WebAuthn yêu cầu kiểm tra challenge không bị dùng lại và các ràng buộc của relying party. Với thao tác quan trọng, có thể bổ sung xác nhận chi tiết giao dịch bằng cơ chế phù hợp để giảm rủi ro bị chuyển tiếp hoặc người dùng phê duyệt nhầm.

## 6. Passkey/WebAuthn: chứng minh từ client được xác minh ở server

Passkey sử dụng mô hình mật mã khóa công khai. Authenticator giữ private key, relying party lưu public key đã đăng ký. Browser và authenticator phối hợp tạo **assertion** cho challenge; server phải xác minh trước khi chấp nhận.

Một flow đăng nhập khái niệm:

1. Client yêu cầu bắt đầu flow cho tài khoản hoặc cơ chế khám phá credential thích hợp.
2. Server phát hành challenge ngẫu nhiên đủ mạnh; lưu trạng thái flow, thời hạn và ngữ cảnh relying party.
3. Browser gọi WebAuthn API; authenticator tạo chữ ký bằng private key đã đăng ký, kèm dữ liệu authenticator và client data.
4. Client gửi response về server. Response vẫn là **dữ liệu đến từ client** cho tới khi verifier kiểm tra.
5. Server xác minh challenge, origin, RP ID hash, credential ID/public key, chữ ký và các cờ **User Presence (UP)**, **User Verification (UV)** theo yêu cầu.
6. Chỉ khi đạt policy, server mới gắn principal với sự kiện xác thực và phát hành session/token phù hợp.

**Vì sao có khả năng chống phishing?** WebAuthn ràng buộc ceremony với relying party/origin. Một trang giả ở origin khác không thể tạo assertion hợp lệ cho relying party thật theo quy tắc chuẩn nếu phía server xác minh đúng. Trái lại, mật khẩu và TOTP có thể bị lừa nhập vào trang giả rồi chuyển tiếp.

**Vì sao vẫn cần ranh giới client–server?** Không được tin chuỗi JSON kiểu “webauthnSuccess: true” hoặc coi popup sinh trắc trên thiết bị là bằng chứng đã hoàn thành. Server phải xác minh chữ ký và các ràng buộc. Khả năng chống phishing cũng không tự xác lập quyền truy cập hay chứng minh tên pháp lý của người dùng.

## 7. Cookie session: phương tiện duy trì trạng thái sau xác thực

Trong ứng dụng web, server có thể tạo **session ID khó đoán** và lưu trạng thái tương ứng ở backend, rồi gửi cookie cho trình duyệt.

~~~http
HTTP/1.1 302 Found
Set-Cookie: __Host-session=<opaque-random-id>; Path=/; Secure; HttpOnly; SameSite=Lax
Location: /account
Cache-Control: no-store
~~~

- **Secure:** cookie chỉ được gửi trên kết nối bảo mật theo cơ chế trình duyệt.
- **HttpOnly:** giảm khả năng JavaScript đọc trực tiếp cookie; **không ngăn hoàn toàn XSS** thay mặt người dùng gọi API.
- **SameSite:** hạn chế một số tình huống cookie được đính kèm trong request cross-site; chọn *Lax* hoặc *Strict* theo luồng sử dụng.
- **Tiền tố __Host-:** trình duyệt hỗ trợ sẽ yêu cầu Secure, Path=/ và không có Domain, hạn chế một số rủi ro do phạm vi cookie.
- **Session ID:** cần đủ ngẫu nhiên, không chứa mật khẩu hoặc dữ liệu nghiệp vụ nhạy cảm dễ đọc.

### 7.1. Mọi request cần kiểm tra phiên và quyền

Backend không được coi cookie có mặt là đủ. Mỗi request bảo vệ tài nguyên phải xác minh session:

- Có được phát hành bởi hệ thống và còn tồn tại?
- Chưa hết hạn idle/absolute timeout, chưa bị thu hồi?
- Principal là ai? Tenant nào? Có thay đổi credential/recovery ảnh hưởng phiên không?
- Thao tác yêu cầu MFA gần đây hay authentication assurance khác không?
- Principal có quyền đối với tài nguyên cụ thể không?

Khi người dùng hoàn thành đăng nhập hoặc nâng mức xác thực, **rotate/regenerate session ID** giúp chống *session fixation*. Đăng xuất, phát hiện chiếm đoạt hoặc thay đổi credential có thể yêu cầu thu hồi session theo chính sách.

### 7.2. Vì sao vẫn có CSRF khi dùng cookie?

Trình duyệt có thể tự đính kèm cookie vào request phù hợp phạm vi. Kẻ tấn công có thể dụ người dùng mở trang chứa form hoặc request hướng tới ứng dụng thật. Nếu endpoint thay đổi trạng thái chỉ dựa vào cookie, có nguy cơ **Cross-Site Request Forgery (CSRF)**.

Biện pháp thường gồm token CSRF có ràng buộc phù hợp với session, kiểm tra Origin/Referer hoặc Fetch Metadata theo thiết kế, quy tắc SameSite hợp lý, tránh thay đổi trạng thái qua GET và xác thực lại ở thao tác nhạy cảm. **SameSite không thay thế mọi lớp phòng CSRF**, nhất là khi còn các tình huống cùng site hoặc luồng tích hợp đặc biệt.

XSS và CSRF có mối quan hệ khác nhau: XSS cho phép mã độc chạy trong origin hợp lệ; một token CSRF có thể bị sử dụng thông qua mã độc trong chính origin đó. Vì vậy cũng cần phòng XSS bằng xử lý output đúng ngữ cảnh, CSP khi thích hợp và giới hạn mã không đáng tin.

## 8. Access token, ID token và refresh token qua client–server

Không phải hệ thống nào cũng sử dụng session cookie. Ứng dụng API hoặc SSO có thể sử dụng token; mỗi loại token có bên nhận và mục đích riêng.

| Loại artefact | Bên nhận chính | Client có thể làm gì? | Server phải làm gì? |
| --- | --- | --- | --- |
| **Authorization code** | Token endpoint | Nhận từ redirect rồi đổi theo giao thức | Kiểm tra redirect URI, thời hạn, trạng thái flow, PKCE/client authentication khi áp dụng |
| **ID token (OIDC)** | OIDC client/relying party | Xác minh hoặc chuyển cho backend theo kiến trúc | Kiểm tra issuer, audience, chữ ký, thời hạn, nonce/flow; không dùng làm access token cho API |
| **Access token** | Resource server/API | Gửi để truy cập API | Xác minh token đúng issuer, audience, hạn, scope/quyền và dạng token được chấp nhận |
| **Refresh token** | Token endpoint | Dùng theo chính sách để xin token mới | Kiểm soát vòng đời, binding/rotation/reuse detection khi phù hợp |
| **Session cookie** | Backend quản lý phiên | Gửi tự động qua trình duyệt | Tra cứu/kiểm chứng trạng thái phiên, CSRF, authorization và step-up |

**JWT là định dạng, không phải cơ chế bảo đảm tự thân.** Việc có thể base64-decode payload hoặc đọc chữ ký trong header không làm claim trở nên đáng tin. API chỉ nhận token thuộc loại và đối tượng mình chấp nhận; phải kiểm tra chính xác thuật toán/khóa tin cậy và policy, tránh nhầm **ID token dành cho client** với **access token dành cho resource server**.

### 8.1. Bearer token và ranh giới thiết bị

Với **bearer token**, bên nào nắm token có thể thử sử dụng nó trong thời hạn/phạm vi hợp lệ. Vì vậy token có giá trị cao khi bị lấy cắp từ bộ nhớ, log, URL hoặc nơi lưu thiếu bảo vệ. Các kiểm soát có thể gồm:

- Access token có thời hạn ngắn và phạm vi/audience tối thiểu.
- Không đặt token trong URL hoặc log; cân nhắc rủi ro nếu token nằm trong JavaScript-accessible storage.
- Sử dụng backend-for-frontend (BFF) hoặc thiết kế lưu token phía server khi phù hợp, để trình duyệt chỉ giữ cookie phiên được bảo vệ.
- Với public client, áp dụng PKCE và các biện pháp bắt buộc theo flow; không tin rằng secret nhúng vào JavaScript/mobile binary có thể giữ bí mật.
- Cân nhắc token ràng buộc người giữ khóa như DPoP hoặc mTLS trong bối cảnh hỗ trợ để giảm giá trị sử dụng lại của token bị đánh cắp.
- Thiết kế thu hồi, rotate refresh token và phát hiện tái sử dụng khi chính sách/giao thức yêu cầu.

**Không có lựa chọn lưu token nào tự bảo vệ mọi rủi ro.** Cookie HttpOnly giúp hạn chế đánh cắp qua đọc trực tiếp từ JavaScript nhưng đòi hỏi kiểm soát CSRF; token trong JavaScript tránh mô hình cookie tự gửi ở một số kiến trúc nhưng dễ bị lấy khi có XSS. Cần chọn kiến trúc theo threat model và mục tiêu ứng dụng.

### 8.2. OIDC Authorization Code + PKCE

Một luồng chuẩn thường gồm:

1. Client tạo yêu cầu ủy quyền với **state** chống nhầm giao dịch/CSRF trong OAuth, **PKCE code_challenge** và các tham số OIDC phù hợp như **nonce** khi cần.
2. Trình duyệt đến Authorization Server/IdP trên HTTPS; IdP xác thực người dùng và thu thập chấp thuận khi áp dụng.
3. IdP redirect với **authorization code** về redirect URI đã đăng ký.
4. Client hoặc backend đổi code tại token endpoint, xuất trình **code_verifier** và thông tin client authentication nếu là confidential client.
5. Bên nhận ID token kiểm tra **iss, aud, exp, signature và nonce khi áp dụng**; API kiểm tra access token theo hợp đồng với Authorization Server.
6. Ứng dụng tạo phiên hoặc dùng token trong phạm vi được cấp, không tin vào tham số request do browser tự khai như “roles” hay “aal”.

**PKCE** ràng buộc việc đổi authorization code với bên khởi tạo code challenge, nhưng không thay thế kiểm tra issuer, audience, state, redirect URI và quyền truy cập API. **state** và **nonce** có mục đích khác nhau; không dùng tên gọi chung “một token chống mọi tấn công”.

## 9. API authorization: ranh giới tài nguyên

Một lỗi thường thấy là kiểm tra quyền trên client hoặc chỉ kiểm tra **đã đăng nhập**, bỏ qua **quyền trên object**.

Ví dụ endpoint:

~~~http
GET /api/users/user_b/invoices
Authorization: Bearer <access-token-of-user-a>
~~~

API phải xác minh token, xác lập principal *user_a* và kiểm tra user_a có quyền xem hóa đơn của *user_b* hay không. Nếu không, trả kết quả từ chối phù hợp chính sách. Không được sử dụng đường dẫn user_b để tự tạo principal.

Một endpoint cập nhật cũng cần kiểm tra các trường do client gửi. Nếu JSON chứa role, tenantId, ownerId hoặc isVerified, server cần có quy tắc rõ trường nào được phép sửa; tránh **mass assignment** đưa dữ liệu tự khai vào những thuộc tính có thẩm quyền.

~~~text
function getInvoices(request):
    auth = authenticateRequest(request)
    if not auth.valid:
        return 401

    principal = auth.principal
    targetUser = request.path.userId

    if not authorization.mayReadInvoices(principal, targetUser):
        return 403

    return invoices.fetchFor(targetUser)
~~~

Nếu cần che giấu sự tồn tại của tài nguyên, ứng dụng có thể áp dụng cách trả lỗi khác theo chính sách. Điều quan trọng là **không để lộ dữ liệu** và quyết định được đưa ra phía server.

### 9.1. Kiểm soát tenant và đối tượng liên kết

Trong hệ thống đa tenant, ranh giới tin cậy còn liên quan tới *tenantId*. Client chọn tenant trong UI không chứng minh tài khoản thuộc tenant đó. Backend phải xác minh tenant hiện hành được phép cho principal rồi áp dụng lọc quyền tới mọi truy vấn.

Tương tự, việc liên kết tài khoản qua OIDC/SAML cần dựa trên **issuer và subject đã được kiểm chứng**, cùng flow account linking có đủ xác thực. Hai IdP gửi cùng email không có nghĩa là có thể gộp tự động hai chủ thể.

## 10. CORS, CSP, Same-Origin Policy và CSRF khác nhau thế nào?

Những cơ chế này hay bị nhầm với xác thực hoặc phân quyền:

| Cơ chế | Mục tiêu | Giới hạn đáng nhớ |
| --- | --- | --- |
| **Same-Origin Policy (SOP)** | Hạn chế script của origin này đọc/tương tác với tài nguyên origin khác theo quy tắc trình duyệt | Không chặn công cụ ngoài trình duyệt gọi API, không kiểm tra quyền nghiệp vụ |
| **CORS** | Cho server quy định origin nào được script trên browser đọc response cross-origin | Không phải authentication/authorization; cURL/bot không bị CORS chặn |
| **CSRF defense** | Chống request không mong muốn được thực hiện với credential được trình duyệt tự gửi | Cần thiết khi phương thức xác thực và endpoint có nguy cơ CSRF |
| **CSP** | Hạn chế một số nguồn script/tài nguyên để giảm rủi ro khai thác XSS và tải mã không tin cậy | Cần cấu hình đúng, không thay sanitization/output encoding hay authorization |
| **TLS/HTTPS** | Bảo vệ kết nối và nhận dạng server theo kiểm tra chứng chỉ | Không chứng minh request từ người dùng hợp pháp hoặc client không bị can thiệp |
| **Input validation** | Giảm request sai và khai thác parser/dữ liệu | Không thay việc kiểm tra principal và quyền truy cập |

### 10.1. Tình huống CORS sai vai trò

Giả sử API cấu hình chỉ cho phép origin *https://app.example.test*. Đó là chính sách dành cho cách browser script truy cập tài nguyên. Kẻ tấn công vẫn có thể chạy script server-side hoặc dòng lệnh gửi HTTPS trực tiếp tới API. Nếu API thiếu xác thực hoặc authorization, CORS **không ngăn truy cập trái phép**.

Một cấu hình CORS “chỉ cho domain của tôi” vì vậy không bảo vệ endpoint quên kiểm tra token. Ngược lại, cấu hình CORS quá rộng với credential có thể làm tăng rủi ro lộ dữ liệu cho origin ngoài dự kiến. Cần áp dụng cả CORS chính xác lẫn xác thực và quyền trên API.

## 11. Reverse proxy, gateway và header giả mạo

Trong nhiều kiến trúc, client không kết nối trực tiếp tới ứng dụng. TLS có thể kết thúc tại load balancer, reverse proxy hoặc API gateway. Backend có thể nhận header biểu diễn user ID, tenant hoặc kết quả xác thực do gateway gửi.

**Ranh giới mới:** khi proxy chuyển danh tính cho backend, backend phải có cách phân biệt **header đáng tin do proxy cấp** với **header client tự chèn**.

Ví dụ nguy hiểm:

~~~http
GET /admin
X-Authenticated-User: admin
X-User-Role: administrator
~~~

Nếu backend tin trực tiếp những header này từ request Internet, ai cũng có thể tự khai thành quản trị viên.

Thiết kế đúng có thể áp dụng tổ hợp:

1. Chỉ cho phép backend nhận kết nối từ gateway được quản lý qua mạng và cơ chế chứng thực phù hợp (mTLS/service identity khi cần).
2. Gateway **loại bỏ hoặc ghi đè** mọi header danh tính đến từ client trước khi thêm header chính thức.
3. Backend kiểm tra nguồn đáng tin; trong mô hình phù hợp, dùng assertion nội bộ có chữ ký, audience, TTL và quyền kiểm soát rõ ràng.
4. Định danh dịch vụ và người dùng được ánh xạ tới principal và policy; header không có quyền tự cấp role ngoài giới hạn.
5. Backend không thể bị truy cập trực tiếp bỏ qua gateway trong các đường kết nối khác.

Header như *X-Forwarded-For*, *Forwarded*, *X-Forwarded-Proto* cũng phải được xử lý theo danh sách proxy tin cậy. Nếu tin client tự khai IP hoặc giao thức, hệ thống có thể tính sai URL redirect, rate limit, nhật ký bảo mật hoặc quyết định policy.

## 12. Ứng dụng mobile và public client

Ứng dụng mobile có thể sử dụng secure enclave, keychain/keystore và device attestation. Đây là các biện pháp tăng bảo đảm cho một số đặc tính thiết bị, nhưng server vẫn phải đánh giá đúng **bằng chứng nào đã được xác minh**.

- **Không nhúng client secret và coi đó là bí mật bền vững:** binary có thể bị phân tích, sao chép và sửa đổi.
- **Dùng Authorization Code + PKCE** cho luồng OAuth công khai theo hướng dẫn của giao thức, với redirect URI và state phù hợp.
- **Lưu token trong cơ chế bảo vệ của hệ điều hành** khi cần; giảm phạm vi token, hỗ trợ hết hạn và thu hồi.
- **Không xem cờ thiết bị không root là quyết định tuyệt đối:** dữ liệu có thể bị giả hoặc môi trường có thể thay đổi; attestation cần kiểm chứng phía server và phụ thuộc nhà phát hành.
- **Sinh trắc cục bộ không tự thay credential server-side:** màn hình mở khóa bằng vân tay có thể dùng để giải phóng private key trong authenticator, nhưng server cần thấy bằng chứng mật mã hợp lệ nếu muốn dựa vào nó.
- **Tránh ràng buộc bảo mật vào phiên bản UI:** client cũ, giả lập hoặc ứng dụng khác vẫn có thể gọi API; policy phải được kiểm soát tại server.

Mobile và browser có những đặc tính lưu trữ khác nhau, nhưng điểm chung là **không dùng sự hiện diện của ứng dụng chính hãng thay cho xác thực và phân quyền**.

## 13. Khôi phục tài khoản và thay đổi yếu tố xác thực

Ranh giới client–server dễ bị vượt qua ở những luồng “phụ” như reset mật khẩu, đăng ký passkey mới, liên kết IdP hoặc đổi email khôi phục.

Ví dụ, chỉ cần nhấp email reset đã được gửi tới tài khoản là có bằng chứng **quyền kiểm soát kênh email tại thời điểm đó**. Nó chưa chứng minh người dùng vừa hoàn tất MFA mạnh đã đăng ký trước đây. Server cần có chính sách riêng đối với quyền mà trạng thái recovery có thể thực hiện.

| Bước | Client cung cấp | Server quyết định |
| --- | --- | --- |
| Yêu cầu reset | Email hoặc định danh khai báo | Phản hồi chống enumeration, giới hạn tần suất, tạo challenge thích hợp |
| Mở reset link | Token/challenge từ URL | Kiểm tra entropy, TTL, ràng buộc, sử dụng một lần và đúng tài khoản |
| Đặt mật khẩu mới | Mật khẩu mới | Chính sách bí mật, hash, cập nhật credential và thu hồi phiên theo rủi ro |
| Thêm passkey | Public key/attestation và WebAuthn data | Kiểm tra đăng ký, account binding, step-up, policy |
| Liên kết IdP | Authorization response/assertion | Xác minh issuer, subject, token, consent/binding và account linking |
| Đổi email khôi phục | Email mới và xác nhận liên quan | Kiểm tra session, reauthentication, email mới, thông báo kênh cũ khi phù hợp |

Không được cho phép client đặt trường *verified = true*, *mfaCompleted = true* hoặc *recoveryApproved = true* để bỏ qua kiểm tra. Một flow recovery được phép làm gì phải được mô tả theo **quyền hạn cụ thể và thời hạn ngắn**, rồi tái xác lập session/credential theo chính sách.

Đường yếu nhất thường quyết định nguy cơ chiếm tài khoản: xác thực bằng security key rất mạnh cũng không giúp nhiều nếu attacker có thể thay key qua endpoint không cần kiểm tra quyền.

## 14. Phishing, replay và lạm dụng: rủi ro qua ranh giới

| Mối đe dọa | Cách vượt ranh giới | Phòng thủ trọng tâm |
| --- | --- | --- |
| **Phishing** | Trang giả lấy mật khẩu/OTP rồi relay tới server thật | WebAuthn/passkey có kiểm tra origin/RP ID; quản lý MFA và cảnh báo phù hợp |
| **Replay** | Gửi lại OTP, challenge response, authorization code hoặc recovery token | Nonce, TTL, binding phiên/giao dịch, tiêu thụ một lần khi cần |
| **Credential stuffing** | Bot gọi API login trực tiếp với mật khẩu lộ | Rate limit đa tín hiệu, MFA, bảo vệ mật khẩu, giám sát và phản ứng |
| **CSRF** | Trang ngoài kích hoạt request dùng cookie của nạn nhân | CSRF token, Origin/Fetch Metadata, SameSite, thiết kế phương thức HTTP phù hợp |
| **XSS** | Script không tin cậy chạy trong origin thật, gửi request hoặc lấy token dễ đọc | Output encoding, CSP khi phù hợp, hạn chế script, bảo vệ token và API |
| **Session fixation** | Đối thủ ép nạn nhân dùng session ID đã biết | Regenerate session ID khi đăng nhập/nâng assurance |
| **Session hijacking** | Token/cookie bị đánh cắp sau xác thực | TLS, bảo vệ lưu trữ, TTL, rotate/revoke, step-up thao tác nhạy cảm |
| **IDOR/BOLA** | Sửa object ID hoặc tenant trong request | Object-level authorization ở API và data layer |
| **Forged identity header** | Client gửi header giả chủ thể qua proxy/backend | Strip/overwrite ở gateway, chứng thực nội bộ, giới hạn đường tới backend |
| **Token confusion** | Gửi ID token tới API hoặc access token sai audience | Kiểm tra token type, issuer, audience, scope và chính sách |
| **MFA bypass** | Client gửi cờ đã xác thực hoặc gọi endpoint phụ trước MFA | State machine và auth context phía server, kiểm tra ở mọi endpoint |
| **Abuse của flow reset** | Đoán mã hoặc dùng lại token, enumerate email | Token đủ ngẫu nhiên, TTL, một lần, rate limit, thông báo trung tính |

Những kiểm soát này hoạt động cùng nhau. Một hệ thống dùng passkey có thể chống phishing tốt nhưng vẫn mắc IDOR; một API kiểm tra authorization đúng vẫn có thể gặp replay nếu nhận token/challenge không đúng ngữ cảnh.

## 15. Thiết kế hợp đồng API an toàn

Một API xác thực có thể phân biệt các trạng thái **chưa hoàn thành**, **đã hoàn thành** và **bị từ chối**. Ví dụ dưới đây là hợp đồng tham khảo:

~~~ts
type LoginOutcome =
  | {
      kind: "challenge";
      flowId: string;
      nextStep: "totp" | "passkey";
      expiresAt: string;
    }
  | {
      kind: "authenticated";
      principal: { id: string; tenantId?: string };
      authenticatedAt: string;
      completedMethods: string[];
    }
  | {
      kind: "rejected";
      code: "INVALID_CREDENTIALS" | "EXPIRED" | "RATE_LIMITED";
    };
~~~

Các trường *principal*, *authenticatedAt*, *completedMethods* trong response là thông tin hiển thị cho client. **Server phải lưu hoặc suy ra trạng thái xác thực từ kết quả verifier được tin cậy**; lần request sau không được tin client gửi lại response này dưới dạng JSON.

Với web session cookie, credential duy trì phiên thường được chuyển qua **Set-Cookie**, và các thông tin không nhạy cảm có thể trả qua JSON. Với API token, cần xem bên nhận, thời gian sống, cách lưu và rủi ro browser trước khi chọn vị trí token. Không đưa mật khẩu, OTP, recovery code, private key hoặc toàn bộ token vào payload trả về chỉ để thuận tiện debug.

### 15.1. Nguyên tắc xử lý lỗi

- Đối với login/forgot-password, giới hạn thông tin làm lộ việc tài khoản tồn tại hoặc bước bảo mật chính xác đã thành công.
- Phân biệt lỗi cú pháp request, lỗi xác thực và lỗi phân quyền trong API contract khi an toàn; **401** thường cho thiếu/sai xác thực, **403** cho có danh tính nhưng thiếu quyền.
- Kiểm soát số lần thử và trả thời gian chờ thích hợp mà không tiết lộ chi tiết chiến lược chống gian lận.
- Ghi correlation ID và audit event phía server, nhưng không log credential, OTP, session ID hoặc raw token.

### 15.2. Dữ liệu trong response cũng cần giới hạn

Nếu backend xác định đúng principal nhưng trả về toàn bộ profile, secret hoặc dữ liệu thuộc tenant khác, hệ thống vẫn vi phạm ranh giới tin cậy. Phân quyền và lọc dữ liệu cần diễn ra trước khi serialize response. Các trường chỉ phục vụ quản trị (ví dụ hash mật khẩu, nội dung reset token, seed MFA) không nên xuất hiện trong response thông thường.

## 16. Quy trình thiết kế từ một user story

Giả sử yêu cầu nghiệp vụ là: **“Người dùng đăng nhập được xem danh sách thiết bị đã đăng ký; muốn xóa passkey thì phải xác thực lại bằng một phương thức còn được phép.”**

Thiết kế theo ranh giới:

1. **Xác định actor và tài nguyên:** principal đã xác thực, danh sách passkey thuộc tài khoản nội bộ, thao tác xóa có độ nhạy cao.
2. **Liệt kê dữ liệu client gửi:** credential ID cần xóa, phiên/cookie, các bước reauthentication. Không tin principalId hoặc isReauthenticated do client đặt.
3. **Xác định bằng chứng cần kiểm tra:** session hợp lệ; tái xác thực gần đây bằng phương thức phù hợp; credential mục tiêu thuộc principal.
4. **Xác định state machine:** chưa xác thực → phiên cơ bản → challenge reauthentication → phiên đủ chính sách → xóa credential; mỗi bước cần TTL và kiểm soát trạng thái.
5. **Tách authorization khỏi authentication:** xác thực lại xác minh chủ thể; authorization quyết định chủ thể có quyền xóa credential đó.
6. **Bảo vệ side effect:** chặn race/double-submit theo logic; ghi audit, thông báo, bảo vệ khả năng khôi phục nếu xóa credential cuối cùng.
7. **Kiểm thử bypass:** gọi DELETE trực tiếp, đổi credentialId, thử replay challenge, dùng session cũ, gửi cờ reauthenticated giả.

~~~mermaid
flowchart TD
    A[DELETE passkey request từ client] --> B{Session hợp lệ?}
    B -- Không --> X[401 / yêu cầu đăng nhập]
    B -- Có --> C{Credential thuộc principal?}
    C -- Không --> Y[403/404 theo chính sách]
    C -- Có --> D{Reauthentication đủ mức và đủ mới?}
    D -- Không --> E[Challenge step-up qua verifier]
    E --> F{Kết quả đã xác minh?}
    F -- Không --> Z[Từ chối hoặc giới hạn thử]
    F -- Có --> G[Backend cập nhật auth context]
    G --> D
    D -- Có --> H[Thực hiện xóa credential trong transaction]
    H --> I[Audit + thông báo + bảo vệ recovery]
~~~

Trong ví dụ này, client được quyết định **credential nào muốn xóa**, nhưng không được quyết định **có quyền xóa hay đã reauthenticate thành công hay chưa**.

## 17. Checklist kiểm thử ranh giới client–server

| Thử nghiệm | Kết quả mong đợi |
| --- | --- |
| Ẩn nút trên UI rồi gọi endpoint trực tiếp | API vẫn yêu cầu xác thực và quyền độc lập |
| Sửa userId, tenantId hoặc objectId trong request | Server xác minh quyền đối tượng, không lộ dữ liệu khác |
| Thêm role=admin hoặc mfaPassed=true vào JSON/header | Server không nâng quyền hoặc đánh dấu hoàn tất MFA |
| Gửi OTP trước bước password hoặc bằng flowId khác | State machine từ chối thao tác không đúng trạng thái |
| Dùng lại mã/challenge đã tiêu thụ | Verifier từ chối theo quy tắc chống replay |
| Gửi WebAuthn assertion với origin/RP ID sai | Server từ chối dù các trường khác có vẻ hợp lệ |
| Gửi access token sai issuer/audience/hết hạn | API từ chối trước khi truy cập tài nguyên |
| Gửi ID token tới API thay access token | API từ chối token sai mục đích |
| Gửi cross-site POST có cookie nhưng thiếu bảo vệ CSRF | Side effect bị chặn |
| Gửi request cURL không có Origin được CORS cho phép | Endpoint vẫn phải kiểm tra authentication/authorization |
| Đặt X-Authenticated-User trong request Internet | Gateway/backend không tin header do client tự khai |
| Đăng nhập lại với session ID trước đó | Server rotate ID và tránh session fixation |
| Dùng session/token đã logout hoặc revoke | Server/API xử lý theo chính sách thu hồi, không vô điều kiện cho phép |
| Đổi email khôi phục từ session cũ | Yêu cầu step-up/freshness theo policy |
| Thêm authenticator bằng recovery flow chưa đủ yêu cầu | Từ chối, không tạo đường vòng so với chính sách bảo mật |
| Chạy client cũ hoặc sửa JavaScript trên browser | Không vượt được các kiểm tra phía server |
| Gây lỗi cấu hình IdP/issuer hoặc nhầm tenant | Assertion bị từ chối hoặc yêu cầu flow đáng tin |
| Log thử lỗi đăng nhập liên tục | Có audit/correlation an toàn; không ghi mật khẩu/OTP/token |

### 17.1. Những câu hỏi bắt buộc khi review

- **Ai đang khẳng định thông tin này?** Client, authenticator, IdP, gateway hay server?
- **Bằng chứng nào khiến bên nhận có thể tin?** Chữ ký, challenge, session lookup, nguồn đáng tin, kênh được chứng thực hay chỉ là một header?
- **Đã kiểm tra đối tượng nhận và phạm vi chưa?** Audience, origin, RP ID, tenant, resource, action, thời hạn và tình trạng thu hồi.
- **Điểm quyết định bảo mật ở đâu?** Có một nơi có thẩm quyền và được gọi từ mọi đường đi không?
- **Nếu bỏ qua toàn bộ UI thì API vẫn an toàn không?** Đây là phép kiểm tra thực dụng của ranh giới client–server.

## 18. Tình huống tự đánh giá

**Tình huống 1:** Frontend lưu localStorage.isAdmin=true sau khi người dùng nhập mã quản trị. Backend chỉ dựa vào trường này trong request. Điều gì sai?

**Trả lời:** localStorage và payload do client kiểm soát, không phải bằng chứng xác thực hoặc authorization. Backend phải kiểm tra vai trò/quyền từ session hoặc token đã xác minh và dữ liệu chính sách có thẩm quyền, đồng thời bảo vệ flow nâng quyền.

**Tình huống 2:** Một API đặt CORS chỉ chấp nhận domain ứng dụng, nhưng không xác minh access token. API đã an toàn chưa?

**Trả lời:** chưa. CORS kiểm soát khả năng browser script đọc response cross-origin, không phải cơ chế xác thực. Client ngoài browser vẫn có thể gọi API; server cần xác thực và phân quyền độc lập.

**Tình huống 3:** Server kiểm tra chữ ký của WebAuthn assertion nhưng bỏ qua challenge đã phát hành. Có rủi ro gì?

**Trả lời:** thiếu ràng buộc với giao dịch hiện tại, tạo điều kiện replay hoặc dùng response sai flow. Server phải kiểm tra challenge, thời hạn, origin, RP ID và chính sách chứng thực liên quan.

**Tình huống 4:** Browser đang có cookie session HttpOnly. Điều đó có bảo đảm không có CSRF hoặc XSS không?

**Trả lời:** không. HttpOnly hạn chế JavaScript đọc cookie, nhưng cookie vẫn có thể được trình duyệt tự gửi; CSRF cần kiểm soát riêng. XSS trong origin hợp lệ vẫn có thể gửi request với credential đi kèm.

**Tình huống 5:** API gateway đã xác thực user và thêm header định danh. Backend được tin mọi header cùng tên do request đưa đến không?

**Trả lời:** không. Phải có biện pháp loại bỏ/ghi đè header do client gửi, chứng thực đường kết nối từ gateway và giới hạn backend chỉ nhận danh tính từ nguồn đáng tin.

## 19. Ghi nhớ

**Client là nơi thu thập thao tác và trình bằng chứng, còn server/verifier là nơi kiểm chứng bằng chứng và đưa ra quyết định bảo mật.** Một request được gửi qua HTTPS, từ app chính hãng hoặc từ browser có cùng origin vẫn không tự chứng minh người gửi đã đăng nhập hay có quyền.

Để giữ ranh giới tin cậy trong hệ thống xác thực, cần bảo vệ các khâu: **thu thập credential → kiểm chứng challenge/MFA/passkey → cấp session/token → xác minh mỗi request → authorization theo tài nguyên → tái xác thực/khôi phục theo rủi ro**. Mỗi lần dữ liệu đi qua browser, IdP, gateway hoặc API phải đặt câu hỏi: **“Ai khẳng định điều này, bằng chứng gì đã được kiểm tra, và bên nhận có được phép tin đến mức nào?”**
