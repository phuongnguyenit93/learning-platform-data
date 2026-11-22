# Đánh cắp token, phát lại và lạm dụng token chưa hết hạn

> **Module:** SECURITY_TOKEN_SECURITY_JWT — Security - JSON Web Token (JWT)  
> **Chương:** Tấn công JWT  
> **Phạm vi:** Phân tích việc đánh cắp, phát lại và lạm dụng token còn hiệu lực ở mức JWT, OAuth và bảo mật hệ thống; không phụ thuộc Java, Spring hay framework cụ thể.

Một access token có thể được ký hoàn toàn hợp lệ nhưng vẫn bị sử dụng trái phép nếu attacker đánh cắp được nó. Với **bearer token**, bên nắm giữ token có thể gửi token tới resource server và được xử lý như bên sở hữu hợp lệ, miễn là token còn hiệu lực và các điều kiện xác minh khác đạt.

Tấn công này không cần phá chữ ký JWT, biết private key của issuer hoặc sửa payload. Attacker chỉ cần lấy được một bản sao token hợp lệ rồi phát lại trước khi token hết hạn hoặc bị thu hồi. Nếu token có scope rộng, audience lớn, lifetime dài hoặc có thể dùng để lấy token mới, thiệt hại có thể vượt xa một request đơn lẻ.

Phòng vệ cần xử lý cả chuỗi: **ngăn token rò rỉ → hạn chế giá trị token → ràng buộc token với bên gửi khi phù hợp → phát hiện replay → thu hồi nhanh → điều tra hành động đã xảy ra**. Chỉ kiểm tra chữ ký và claim exp là chưa đủ để phát hiện token đã bị sao chép.

## 1. Bearer token và bản chất của replay

### 1.1. Vì sao người giữ token có thể sử dụng nó?

Bearer token là credential mà quyền sử dụng gắn với việc nắm giữ token. Client gửi token trong request, thường qua Authorization header:

~~~http
GET /accounts/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOi...
~~~

Resource server kiểm tra token theo profile: chữ ký hoặc trạng thái introspection, issuer, audience, token type, thời hạn, scope và quyền trên tài nguyên. Nếu mọi điều kiện đạt, request có thể được chấp nhận.

Trong mô hình bearer thông thường, server không có bằng chứng mật mã cho biết người gửi hiện tại có phải đúng thiết bị hoặc tiến trình đã nhận token ban đầu hay không. Một bản sao token có thể được gửi từ thiết bị khác.

### 1.2. Token replay là gì?

**Token replay** là việc sử dụng lại một token đã được phát hành và còn được chấp nhận để thực hiện request khác hoặc lặp lại request trước đó.

Có hai dạng thường gặp:

- **Replay credential:** attacker lấy access token rồi dùng nó cho request mới trong phạm vi audience/scope của token.
- **Replay request:** attacker ghi lại một request đã được xác thực rồi gửi lại request đó, có thể nhằm lặp lại một hành động như tạo đơn hàng hoặc chuyển trạng thái.

Hai dạng này có thể cùng xảy ra nhưng không giống nhau. Một access token bearer thường được thiết kế để dùng cho nhiều request trong thời gian hiệu lực; vì vậy, chỉ đánh dấu token đã dùng một lần không phù hợp với mọi access token. Với hành động nghiệp vụ không được phép lặp, cần thêm chống replay ở cấp request/giao dịch.

### 1.3. JWT hợp lệ không đồng nghĩa request hợp lệ

Chữ ký JWT xác nhận payload được ký bởi khóa tương ứng và chưa bị thay đổi kể từ khi ký, theo giả định khóa an toàn. Nó không chứng minh:

- Token vẫn thuộc về người đang gửi request.
- Token chưa bị sao chép.
- Session hoặc grant chưa bị thu hồi.
- Người dùng vẫn còn quyền ở thời điểm hiện tại.
- Request chưa từng được thực hiện.
- Nội dung giao dịch hiện tại là ý định thật của người dùng.

Nếu token bị đánh cắp, attacker có thể gửi nguyên token không chỉnh sửa. Chữ ký vẫn hợp lệ; resource server cần các tín hiệu khác để ngăn hoặc phát hiện việc sử dụng trái phép.

## 2. Điều kiện để token bị đánh cắp có thể bị lạm dụng

Attacker thường cần đồng thời có:

1. Một bản sao token hoặc khả năng sử dụng token trong runtime của nạn nhân.
2. Token chưa hết hạn và chưa bị thu hồi/chặn.
3. Một resource server chấp nhận token đó.
4. Audience phù hợp với resource server.
5. Scope/permission đủ cho hành động mục tiêu.
6. Không có sender constraint mà attacker không thể đáp ứng.
7. Không có kiểm tra trạng thái, replay hoặc risk signal đủ mạnh để từ chối request.

~~~mermaid
flowchart TD
    A[Token bị lộ] --> B{Token còn hiệu lực?}
    B -->|Không| X[Từ chối]
    B -->|Có| C{Audience và token type phù hợp?}
    C -->|Không| X
    C -->|Có| D{Có sender constraint?}
    D -->|Có| E{Attacker chứng minh được key/certificate?}
    E -->|Không| X
    E -->|Có| F[Kiểm tra quyền và trạng thái]
    D -->|Không| F
    F --> G{Scope, resource và trạng thái đạt?}
    G -->|Có| H[Request có thể được chấp nhận]
    G -->|Không| X
~~~

Sơ đồ mô tả các lớp kiểm tra điển hình. Một hệ thống có thể thêm kiểm tra session, risk score, thiết bị, giao dịch hoặc xác thực tăng cường.

### 2.1. Token phải còn trong cửa sổ chấp nhận

Attacker thường tận dụng khoảng thời gian từ lúc token bị lộ tới lúc token hết hạn hoặc bị thu hồi. Cửa sổ này phụ thuộc:

- Thời hạn access token.
- Clock skew/leeway của verifier.
- Thời gian cache trạng thái active.
- Độ trễ truyền sự kiện thu hồi.
- Thời gian phát hiện và phản ứng của đội vận hành.
- Khả năng refresh hoặc exchange token.

Claim exp không tự xóa token khỏi thiết bị và không tự thu hồi bản sao đã bị đánh cắp. Nó chỉ giúp verifier từ chối token sau thời điểm hết hạn theo policy.

### 2.2. Audience và scope quyết định phạm vi thiệt hại

Token có audience hẹp chỉ dùng được ở resource server được chỉ định. Scope tối thiểu giới hạn hành động attacker có thể thử thực hiện.

Một token có nhiều audience hoặc quyền quản trị rộng sẽ tạo phạm vi lạm dụng lớn hơn. Không cấp một access token dùng chung cho nhiều API chỉ để đơn giản hóa client nếu các resource có ranh giới tin cậy khác nhau.

### 2.3. Access token và refresh token có giá trị khác nhau

Access token thường cấp quyền truy cập resource trong một khoảng thời gian. Refresh token có thể cho phép lấy access token mới và vì vậy có giá trị lâu dài hơn.

Nếu refresh token bị lộ, attacker có thể duy trì quyền truy cập qua nhiều access token kế tiếp, tùy grant, rotation và reuse detection. Việc chỉ rút ngắn access token lifetime không đủ nếu refresh token vẫn bị đánh cắp và có thể tiếp tục dùng.

## 3. Các nguồn làm lộ token

### 3.1. Browser storage và XSS

Nếu access token hoặc refresh token được lưu trong localStorage/sessionStorage, JavaScript cùng origin có thể đọc dữ liệu. XSS hoặc script bên thứ ba bị xâm phạm có thể lấy token.

Các nguồn XSS gồm:

- Nội dung do người dùng gửi được render không an toàn.
- DOM injection hoặc dữ liệu URL được đưa vào HTML.
- Dependency frontend hoặc script CDN bị xâm phạm.
- Tag manager, analytics, widget hoặc script nhúng có quyền chạy trong trang.
- Tài khoản triển khai hoặc pipeline phát hành frontend bị chiếm quyền.

Ngay cả khi token không bị exfiltrate, XSS vẫn có thể gọi API trong phiên hiện tại bằng quyền của người dùng. HttpOnly cookie có thể ngăn JavaScript đọc cookie nhưng không ngăn script độc hại thực hiện request same-origin.

### 3.2. Log, tracing và hệ thống quan sát

Token có thể vô tình xuất hiện trong:

- Authorization header được ghi nguyên văn.
- Log request/response tại gateway, proxy hoặc API.
- Distributed tracing span attributes.
- Error report, crash dump hoặc debug snapshot.
- Analytics event hoặc telemetry frontend.
- Công cụ hỗ trợ người dùng thu thập request.

Hệ thống quan sát thường được chia sẻ giữa nhiều nhóm và lưu giữ lâu. Một token xuất hiện trong log có thể được sao chép qua nhiều hệ thống và khó thu hồi toàn bộ bản sao.

### 3.3. URL, browser history và referrer

Không đặt bearer token trong query string hoặc URL. URL có thể xuất hiện trong:

- Browser history và bookmark.
- Access log của web server/proxy.
- Referrer header trong một số luồng điều hướng.
- Screenshot, clipboard hoặc hệ thống hỗ trợ.
- Công cụ phân tích lưu trang và sự kiện.

Với OAuth callback, cần tuân thủ đúng authorization flow và bảo vệ authorization code, state, nonce; không biến URL thành nơi truyền access token.

### 3.4. Thiết bị đầu cuối và extension

Malware, extension có quyền rộng, phần mềm điều khiển từ xa hoặc tài khoản hệ điều hành bị chiếm có thể đọc dữ liệu trình duyệt, chặn request hoặc điều khiển phiên đã đăng nhập.

Sender-constrained token không giúp nhiều nếu attacker kiểm soát chính tiến trình client và có thể gọi thao tác ký bằng private key.

### 3.5. Service-to-service và hạ tầng

Token có thể bị lộ khi:

- Một service ghi token vào log hoặc truyền token qua queue không được bảo vệ.
- Credential bị nhúng vào image, repository, CI/CD variable hoặc file cấu hình.
- Backup/snapshot chứa token hoặc dữ liệu phiên.
- Proxy/gateway bị xâm phạm.
- Token bị chuyển tiếp tới service không cần quyền sử dụng.
- Một service có quyền rộng bị lợi dụng làm confused deputy.

Không chỉ browser mới là nguồn rò rỉ. Mọi thành phần có thể quan sát hoặc lưu Authorization header đều thuộc threat model.

### 3.6. Người dùng và quy trình vận hành

Token có thể bị chia sẻ qua chat, ticket, email, ảnh chụp màn hình hoặc công cụ hỗ trợ. Nhân viên có thể sao chép request mẫu có chứa token thật vào tài liệu hoặc issue công khai.

Tài liệu hướng dẫn, bug report và test fixture phải dùng token giả, không dùng bearer credential còn hoạt động.

## 4. Chuỗi tấn công đánh cắp và phát lại

### 4.1. Kịch bản: access token bị lộ từ frontend

Giả sử một SPA lưu access token trong browser storage:

1. Người dùng đăng nhập và nhận access token.
2. Ứng dụng lưu token phía client để gọi API.
3. Một lỗ hổng XSS hoặc script bên thứ ba bị xâm phạm chạy trong origin.
4. Script đọc được token hoặc gọi API thay người dùng.
5. Nếu token bị gửi ra ngoài, attacker có thể dùng bản sao từ môi trường khác.
6. Resource server xác minh chữ ký, issuer, audience và exp; các bước này đều có thể thành công.
7. Nếu không có sender constraint, trạng thái thu hồi hoặc risk control phù hợp, request trái phép có thể được chấp nhận.

### 4.2. Kịch bản: token lộ trong log

1. Gateway ghi nguyên Authorization header để debug.
2. Log được chuyển tới hệ thống tập trung và cấp quyền cho nhiều nhóm.
3. Một tài khoản log viewer bị chiếm hoặc log được xuất ra nơi không an toàn.
4. Attacker lấy token còn hạn.
5. Attacker phát lại token từ một client khác.
6. API chỉ kiểm tra token theo bearer semantics nên không biết token đã bị sao chép.

### 4.3. Kịch bản: refresh token bị đánh cắp

1. Refresh token dài hạn bị lộ từ storage hoặc backup.
2. Attacker gửi refresh token tới authorization server.
3. Nếu token còn active và không bị ràng buộc sender, server có thể cấp access token mới.
4. Attacker tiếp tục dùng access token mới sau khi access token cũ hết hạn.
5. Nếu hệ thống dùng refresh token rotation nhưng không phát hiện reuse hoặc không thu hồi family đúng cách, attacker có thể duy trì quyền truy cập.

~~~mermaid
sequenceDiagram
    participant U as User/Client
    participant AS as Authorization Server
    participant RS as Resource Server
    participant A as Attacker
    U->>AS: Đăng nhập và xin token
    AS-->>U: Access token + refresh token
    U->>U: Token bị lưu hoặc rò rỉ
    U-->>A: Token bị đánh cắp (ngoài ý muốn)
    A->>RS: Phát lại access token còn hạn
    RS-->>A: Request có thể được chấp nhận nếu không có lớp chặn
    A->>AS: Dùng refresh token bị lộ
    AS-->>A: Có thể cấp access token mới nếu refresh token còn active
~~~

Sơ đồ mô tả một khả năng tấn công. Kết quả thực tế phụ thuộc loại token, sender constraint, rotation, trạng thái grant và policy của authorization/resource server.

## 5. Lạm dụng token theo từng loại

| Loại token | Khả năng lạm dụng khi bị lộ | Điều cần kiểm soát |
|---|---|---|
| Access token | Gọi API trong audience, scope và lifetime | Lifetime, audience, scope, revocation, sender constraint |
| Refresh token | Xin access token mới hoặc duy trì phiên | Rotation, reuse detection, grant/session revocation, sender constraint |
| ID token | Phát lại thông tin xác thực trong flow sai hoặc làm lộ dữ liệu định danh | OIDC validation, nonce, audience/client binding, session policy |
| Password reset token | Đặt lại mật khẩu nếu token còn hiệu lực | Một lần dùng, ràng buộc tài khoản, thời hạn ngắn, trạng thái server-side |
| Email verification token | Xác minh địa chỉ hoặc kích hoạt tài khoản | Một lần dùng, đúng subject/email, thời hạn ngắn |
| Transaction/action token | Lặp lại hoặc xác nhận hành động | Nonce, transaction binding, atomic consume, xác nhận ý định |
| Service token | Gọi API nội bộ trong quyền của service | Audience hẹp, workload identity, scope tối thiểu, sender constraint |

Không phải mọi JWT đều là OAuth access token. Cần xác định profile và hành vi của endpoint trước khi quyết định cách thu hồi hoặc chống replay.

### 5.1. ID token không phải access token

ID token trong OpenID Connect cung cấp thông tin xác thực cho client. Nó được kiểm tra theo OIDC, bao gồm issuer, audience/client ID, thời hạn, nonce khi áp dụng và các quy tắc flow liên quan.

Không gửi ID token tới resource API như bearer access token. Nếu ID token bị đánh cắp, tác động phụ thuộc cách client quản lý session và liệu hệ thống có nhầm lẫn ID token với access token hay không.

### 5.2. Token một lần phải có trạng thái server-side

Với password reset, email verification hoặc transaction token, chỉ kiểm tra chữ ký và exp không bảo đảm token chỉ dùng một lần. Server cần lưu trạng thái consumed/revoked và cập nhật nguyên tử để hai request đồng thời không cùng sử dụng thành công.

## 6. JWT và giới hạn của exp, jti, chữ ký

### 6.1. exp giới hạn thời gian, không ngăn replay trong thời hạn

Claim exp giúp verifier từ chối token sau thời điểm hết hạn. Trước thời điểm đó, token bearer vẫn có thể được dùng lại nhiều lần nếu contract cho phép.

Access token ngắn hạn giảm cửa sổ khai thác, nhưng:

- Không ngăn attacker dùng token ngay sau khi đánh cắp.
- Không thu hồi token đã bị sao chép.
- Không chặn refresh token bị lộ.
- Không bảo đảm mọi verifier có đồng hồ và leeway giống nhau.

### 6.2. jti không tự chống replay

Claim jti là JWT ID. Nó có thể giúp nhận diện token và hỗ trợ denylist hoặc audit, nhưng chỉ có jti không làm token trở thành one-time token.

Để dùng jti chống replay, hệ thống phải:

- Bảo đảm jti duy nhất trong namespace đã định nghĩa.
- Lưu trạng thái đã dùng/đã thu hồi ở server-side.
- Tra cứu hoặc đồng bộ trạng thái ở verifier.
- Xử lý atomic khi nhiều request đến đồng thời.
- Giữ record đủ lâu theo exp, leeway và policy.

Với access token thông thường, cùng một jti có thể xuất hiện trong nhiều request hợp lệ. Không đánh dấu jti đã dùng sau request đầu tiên trừ khi contract định nghĩa token/request chỉ được dùng một lần.

### 6.3. Chữ ký hợp lệ không chứng minh người gửi là chủ token

Nếu attacker lấy token nguyên vẹn, chữ ký vẫn hợp lệ. Chữ ký bảo vệ tính toàn vẹn và nguồn phát hành; nó không ràng buộc token với thiết bị hoặc private key của client.

Để ràng buộc bên gửi, cân nhắc sender-constrained token như DPoP hoặc mTLS certificate-bound access token. Các cơ chế này yêu cầu proof/certificate phù hợp khi sử dụng token.

### 6.4. JWT không mặc định được mã hóa

JWS JWT thường chỉ được Base64url-encode header và payload rồi ký/MAC. Bất kỳ ai có token đều có thể đọc payload; chữ ký không che giấu claims.

Không đưa mật khẩu, secret, private key hoặc dữ liệu nhạy cảm không cần thiết vào payload. JWE có thể bảo vệ tính bí mật của nội dung, nhưng không ngăn việc sử dụng lại một bearer token đã giải mã/đánh cắp nếu giao thức vẫn cho phép bearer semantics.

## 7. Biện pháp giảm nguy cơ đánh cắp token

### 7.1. Bảo vệ token trong quá trình truyền

- Dùng HTTPS/TLS cho toàn bộ đường truyền có token.
- Không gửi bearer token trong URL.
- Không chuyển token tới domain hoặc service không thuộc audience.
- Không ghi Authorization header nguyên văn vào log.
- Bảo vệ kết nối giữa gateway và backend.
- Kiểm soát redirect để token không bị gửi tới host ngoài ý muốn.
- Tránh đưa token vào query, analytics event, exception hoặc telemetry.

TLS bảo vệ token trên đường truyền khỏi người nghe lén thụ động, nhưng không ngăn token bị lấy từ endpoint, log hoặc thiết bị đã bị xâm phạm.

### 7.2. Lưu trữ phía browser

Với ứng dụng trình duyệt:

- Tránh lưu refresh token dài hạn trong localStorage/sessionStorage nếu kiến trúc có lựa chọn phù hợp hơn.
- Có thể giữ access token ngắn hạn trong memory để giảm persistence, nhưng XSS vẫn có thể sử dụng token trong runtime.
- Cân nhắc Backend-for-Frontend (BFF): backend giữ OAuth tokens, browser chỉ giữ session cookie.
- Nếu dùng cookie, cấu hình Secure, HttpOnly, SameSite và bảo vệ CSRF.
- Ngăn XSS bằng output encoding, API DOM an toàn, CSP và kiểm soát dependency/script bên thứ ba.
- Xóa state/token khi logout hoặc đổi tài khoản, đồng thời thu hồi session phía server nếu cần.

HttpOnly giảm khả năng JavaScript đọc cookie nhưng không ngăn XSS thực hiện request same-origin trong phiên.

### 7.3. Bảo vệ token ở backend và service

- Không lưu token trong source code, image, repository hoặc cấu hình công khai.
- Dùng secret manager/KMS phù hợp cho credential và khóa.
- Phân quyền truy cập log, trace, backup và token store theo least privilege.
- Redact Authorization header và cookie tại gateway, proxy, application log và tracing.
- Giới hạn thời gian lưu trữ bản sao token.
- Dùng workload identity hoặc cơ chế cấp token theo service thay vì chia sẻ một token quyền rộng.
- Không chuyển tiếp token qua nhiều hop nếu service nhận không cần quyền đó.

### 7.4. Hạn chế giá trị của token

- Audience càng hẹp càng tốt.
- Scope/permission tối thiểu cho đúng thao tác.
- Lifetime access token ngắn phù hợp mức rủi ro.
- Không nhúng dữ liệu nhạy cảm không cần thiết.
- Tách token theo resource hoặc trust domain khi phù hợp.
- Giới hạn quyền của refresh token và client grant.
- Với hành động nhạy cảm, yêu cầu xác thực tăng cường hoặc xác nhận giao dịch.

## 8. Biện pháp giảm khả năng replay

### 8.1. Sender-constrained token

Sender-constrained token gắn access token với public key hoặc certificate của client:

- **DPoP (RFC 9449):** client ký proof cho từng request. Proof ràng buộc với key, method, URI và access token; resource server kiểm tra jti, iat, nonce khi áp dụng và key binding.
- **mTLS (RFC 8705):** access token được ràng buộc với thumbprint client certificate. Resource server xác minh certificate trong kết nối TLS và so khớp với claim cnf.

Attacker chỉ có token mà không có private key/certificate tương ứng khó sử dụng token từ một client khác. Nếu attacker kiểm soát client hoặc lấy cả key, lớp bảo vệ này có thể bị vượt qua.

### 8.2. DPoP proof replay khác access token replay

DPoP dùng một proof JWT cho request. Resource server cần kiểm tra:

- Chữ ký proof và public JWK.
- Thumbprint khớp cnf.jkt trong access token đã xác minh.
- htm và htu khớp request.
- ath khớp access token gửi cùng request tại resource server.
- iat nằm trong cửa sổ cho phép.
- jti proof chưa được chấp nhận trước đó.
- Nonce nếu server yêu cầu.

Replay cache của DPoP proof không đồng nghĩa denylist access token. Access token có thể được dùng cho nhiều request, mỗi request cần proof mới. Ngược lại, một proof đã dùng không được chấp nhận lại trong replay window.

### 8.3. mTLS certificate-bound token

Authorization server ghi certificate thumbprint vào cnf.x5t#S256. Resource server so sánh với certificate client đã xác thực trong kết nối TLS.

Nếu TLS kết thúc ở gateway, backend chỉ được tin certificate metadata được gateway xác minh và chuyển tiếp qua kênh nội bộ bảo vệ. Không tin header certificate do client tự gửi.

### 8.4. Nonce và challenge cho hành động nhạy cảm

Với hành động một lần hoặc giao dịch nhạy cảm, server có thể phát challenge/nonce gắn với:

- Transaction ID.
- User/session.
- Resource và hành động cụ thể.
- Thời hạn ngắn.
- Trạng thái chưa sử dụng.

Client hoặc người dùng phải đáp ứng challenge theo flow được thiết kế. Server cần consume challenge nguyên tử để ngăn hai request đồng thời cùng thành công.

Nonce ngẫu nhiên trong request không tự có giá trị nếu server không lưu hoặc xác minh trạng thái tương ứng.

### 8.5. Idempotency key cho request nghiệp vụ

Idempotency key giúp server nhận diện request lặp lại của cùng một thao tác nghiệp vụ, ví dụ tạo thanh toán hoặc đặt hàng. Server lưu kết quả theo key và principal/resource phù hợp.

Idempotency key không phải credential và không thay thế authentication, authorization hoặc sender constraint. Nếu attacker có token hợp lệ và tạo idempotency key mới, request vẫn có thể được thực hiện nếu policy không có lớp kiểm tra khác.

### 8.6. IP, User-Agent và fingerprint chỉ là tín hiệu phụ

Thay đổi IP hoặc User-Agent có thể giúp phát hiện bất thường, nhưng không nên dùng riêng làm bằng chứng quyết định:

- Người dùng di chuyển giữa mạng di động, Wi-Fi, VPN hoặc proxy.
- Nhiều người có thể dùng chung IP.
- User-Agent có thể bị giả mạo.
- Fingerprint có thể thay đổi và gây tác động quyền riêng tư.

Kết hợp các tín hiệu này trong risk engine, giới hạn tốc độ hoặc step-up authentication; không coi chúng tương đương proof of possession.

## 9. Thu hồi và giới hạn cửa sổ bị lạm dụng

### 9.1. Xóa token phía client không đủ

Logout có thể xóa token trong browser, nhưng attacker có thể đã sao chép token. Cần trạng thái phía server hoặc một cơ chế khiến token cũ không còn được chấp nhận.

Các lựa chọn:

- Denylist theo issuer + jti.
- Thu hồi session hoặc grant.
- Thu hồi refresh token/token family.
- Introspection theo RFC 7662.
- Credential/session version.
- Chặn key identity trong sự cố khóa bị lộ.

### 9.2. Access token ngắn hạn

Lifetime ngắn giới hạn thời gian sử dụng của token bị lộ. Tuy nhiên, cần cân bằng:

- Rủi ro replay.
- Tải authorization server do refresh thường xuyên.
- Khả năng cache và availability.
- Độ trễ thu hồi.
- Hành vi khi client offline hoặc mạng không ổn định.

Không chọn một thời hạn cố định cho mọi loại token. Refresh token, access token, ID token và token một lần có mục đích khác nhau.

### 9.3. Refresh token rotation và reuse detection

Với refresh token rotation:

1. Client dùng refresh token hiện tại.
2. Authorization server phát refresh token mới và vô hiệu hóa token cũ.
3. Nếu token cũ bị sử dụng lại, server có thể nhận diện dấu hiệu replay.
4. Theo policy, server thu hồi token family/grant và yêu cầu xác thực lại.

Rotation cần quản lý race condition và retry. Một client hợp lệ có thể gửi lại request do timeout; hệ thống cần phân biệt retry hợp lệ với reuse đáng ngờ theo thiết kế. Với public client, RFC 9700 khuyến nghị sender-constrained refresh token hoặc rotation có reuse detection theo điều kiện áp dụng.

### 9.4. Hybrid verification

Resource server có thể xác minh JWT offline rồi tra cứu trạng thái tập trung theo jti, session, grant hoặc subject. Cache active phải bị giới hạn bởi ngân sách thu hồi; sự kiện revoke khẩn cấp phải thắng cache active cũ.

Không phải endpoint nào cũng cần cùng mức tra cứu. Endpoint rủi ro cao có thể yêu cầu trạng thái trực tuyến; endpoint ít rủi ro có thể dùng cache ngắn hoặc lifetime ngắn nếu contract cho phép.

## 10. Phát hiện token bị đánh cắp và lạm dụng

### 10.1. Dấu hiệu bất thường

- Cùng token/session được dùng đồng thời từ các vị trí hoặc thiết bị không phù hợp.
- Một token được dùng từ nhiều ASN/quốc gia trong khoảng thời gian ngắn.
- Tần suất request tăng đột ngột hoặc xuất hiện pattern dò tài nguyên.
- User-Agent, TLS/client characteristics hoặc thiết bị thay đổi bất thường.
- Request vượt hành vi bình thường của subject/client.
- Scope được dùng cho endpoint nhạy cảm mà trước đó không xuất hiện.
- Refresh token cũ bị dùng lại sau rotation.
- Một session tiếp tục hoạt động sau logout hoặc revoke.
- Token có audience/scope hợp lệ nhưng hành vi truy cập không phù hợp.

Một tín hiệu đơn lẻ không đủ kết luận token bị đánh cắp. Cần kết hợp risk signal, trạng thái session, audit log và ngữ cảnh người dùng.

### 10.2. Theo dõi ở đâu?

Thu thập sự kiện tối thiểu cần thiết:

- Issuer/contract ID và loại token profile.
- Subject/client/session ID đã được xác minh.
- Audience, scope và resource/action.
- Thời điểm phát hành được ghi nhận ở server và thời điểm request.
- Key ID hoặc token identifier phù hợp, không ghi raw token.
- IP/ASN và thông tin thiết bị ở mức cần thiết, có xét quyền riêng tư.
- Kết quả xác minh, revocation/introspection và sender constraint.
- Mã lý do từ chối và request correlation ID.

Không ghi toàn bộ JWT, refresh token, cookie session hoặc private key vào log. Có thể dùng fingerprint/token ID đã được thiết kế an toàn để tương quan.

### 10.3. Phân biệt request hợp lệ lặp lại và replay độc hại

Một access token có thể hợp lệ khi được dùng nhiều lần bởi client. Không cảnh báo chỉ vì cùng jti xuất hiện ở nhiều request.

Hãy phân biệt:

- Nhiều request khác nhau với cùng access token theo đúng thiết kế.
- Cùng DPoP proof jti được gửi lại.
- Cùng one-time transaction token được consume nhiều lần.
- Cùng idempotency key được retry hợp lệ.
- Một bearer token xuất hiện đồng thời ở thiết bị/vị trí không phù hợp.

Mỗi loại có semantics và biện pháp chống replay riêng.

## 11. Ứng phó khi token bị đánh cắp

### 11.1. Xác nhận và khoanh vùng

1. Ghi incident ID và thời điểm phát hiện.
2. Xác định loại token, issuer, audience, subject/client và session/grant liên quan.
3. Bảo toàn log issuer, gateway, resource server, introspection/status service và hệ thống quan sát.
4. Xác định nguồn rò rỉ: browser, log, endpoint, thiết bị, backup hay service trung gian.
5. Xác định token còn hạn, refresh capability và các resource có thể bị truy cập.

Không gửi raw token qua chat/ticket để chứng minh sự cố. Dùng token identifier, request ID hoặc bản test đã redacted.

### 11.2. Chặn sử dụng tiếp

- Thu hồi session/grant hoặc refresh token family.
- Đưa jti vào denylist nếu cần chặn token cụ thể.
- Nếu key ký bị compromise, chặn key identity tại mọi verifier; không chỉ thu hồi các jti đã thấy.
- Nếu client PoP key/certificate bị lộ, thu hồi binding/token liên quan và cấp binding mới.
- Cập nhật cache và phát sự kiện revoke tới mọi region/verifier.
- Yêu cầu đăng nhập hoặc xác thực lại khi cần.

### 11.3. Đánh giá hành động đã xảy ra

Tìm các request được chấp nhận trong cửa sổ nghi ngờ:

- Dữ liệu được đọc/tải xuống/xuất.
- Tài nguyên được tạo, sửa hoặc xóa.
- Quyền, role, tenant membership hoặc thông tin xác thực bị thay đổi.
- Token mới được phát hành hoặc trao đổi.
- Giao dịch được thực hiện hoặc phê duyệt.
- Service downstream đã tin token hoặc quyết định của service bị ảnh hưởng.

Phân biệt rõ token có thể bị lạm dụng với hành động trái phép đã có bằng chứng. Nếu dữ liệu nhạy cảm bị truy cập, xử lý theo quy trình sự cố dữ liệu của tổ chức.

### 11.4. Khôi phục

- Xử lý nguồn rò rỉ trước khi cấp credential mới.
- Cấp token/session mới sau khi xác minh lại principal và grant.
- Thay client key/certificate nếu bị lộ.
- Xác nhận mọi verifier đã áp dụng trạng thái revoke.
- Theo dõi token cũ, refresh reuse và hoạt động bất thường.
- Xóa bản sao token khỏi log/storage theo quy trình lưu giữ và điều tra; không làm mất bằng chứng cần bảo toàn.

## 12. Ma trận kiểm thử đánh cắp và replay

| ID | Tình huống | Kết quả mong đợi |
|---|---|---|
| R01 | Access token hợp lệ được dùng bởi client đúng | Chấp nhận nếu claims và quyền đạt |
| R02 | Access token bị sao chép và dùng như bearer từ client khác | Có thể bị chấp nhận nếu không có sender constraint; test phải xác nhận rủi ro hiện tại |
| R03 | Token hết hạn | Từ chối |
| R04 | Token bị revoke theo jti | Từ chối sau khi trạng thái revoke có hiệu lực |
| R05 | Token đúng chữ ký nhưng sai audience | Từ chối |
| R06 | Token đúng audience nhưng thiếu scope | Từ chối quyền |
| R07 | Refresh token cũ bị dùng lại sau rotation | Phát hiện reuse và xử lý token family theo policy |
| R08 | Logout session nhưng access token cũ còn exp | Bị từ chối nếu contract yêu cầu session check |
| R09 | One-time token được gửi hai lần đồng thời | Chỉ một request consume thành công |
| R10 | Cùng access token dùng nhiều request bình thường | Không coi là replay chỉ vì jti giống nhau |
| R11 | DPoP proof cũ bị phát lại | Từ chối theo jti/replay window |
| R12 | Token DPoP bị đánh cắp nhưng attacker không có private key | Không tạo được proof binding hợp lệ |
| R13 | Attacker có cả token và PoP key | Đánh giá compromise client/key; PoP không còn đủ bảo vệ |
| R14 | Token xuất hiện trong log | Redaction ngăn credential raw được ghi |
| R15 | Token nằm trong query string | Kiểm tra bị chặn hoặc không được sử dụng theo policy |
| R16 | XSS thử nghiệm trong môi trường cô lập | Xác nhận storage/runtime/cookie exposure và hiệu quả biện pháp giảm thiểu |
| R17 | Status service lỗi, cache active hết TTL | Fail policy được thực thi; không dùng cache cũ |
| R18 | IP/User-Agent thay đổi nhưng token và proof hợp lệ | Xử lý theo risk policy, không tự động coi tín hiệu đơn lẻ là bằng chứng |
| R19 | Token giả được tạo do signing key bị lộ | Key identity block chặn; không chỉ dựa vào jti |
| R20 | Token bị đánh cắp đã thực hiện hành động nhạy cảm | Audit có thể liên kết request, principal, resource và hành động |

Các ca R02 và R13 là kiểm thử threat model; kết quả “có thể chấp nhận” không phải tiêu chí bảo mật mong muốn cho mọi kiến trúc. Nếu hệ thống cần ngăn replay từ thiết bị khác, phải có sender constraint hoặc lớp trạng thái/risk control tương ứng.

## 13. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| JWT có chữ ký nên không thể bị giả mạo hoặc lạm dụng | Token nguyên vẹn có thể bị đánh cắp và phát lại mà không cần sửa chữ ký |
| exp ngăn token replay | exp chỉ giới hạn thời gian chấp nhận |
| Có jti là token tự động dùng một lần | jti chỉ là định danh; cần trạng thái server-side và semantics one-time |
| Logout xóa localStorage là đủ | Bản sao token ở attacker vẫn còn dùng được |
| HTTPS ngăn mọi hình thức đánh cắp token | HTTPS bảo vệ đường truyền, không bảo vệ endpoint, log hoặc thiết bị bị xâm phạm |
| HttpOnly loại bỏ XSS | HttpOnly ngăn đọc cookie qua JavaScript nhưng XSS vẫn có thể hành động trong phiên |
| DPoP ngăn mọi replay | Cần kiểm tra proof, jti, iat, nonce và key binding; attacker có cả key vẫn có thể lạm dụng |
| IP binding đủ chống token theft | IP thay đổi và có thể dùng chung; chỉ là tín hiệu phụ |
| Thu hồi refresh token làm access token cũ mất hiệu lực ngay | Access token offline có thể còn được chấp nhận tới exp nếu không có central status/key block |
| Mọi request dùng cùng access token đều là replay | Access token thường được thiết kế cho nhiều request hợp lệ |

## 14. Checklist phòng chống token theft và replay

**Giảm khả năng rò rỉ**

- [ ] Không log Authorization header, cookie session hoặc raw JWT.
- [ ] Không đưa token vào URL, analytics hoặc telemetry.
- [ ] Bảo vệ browser storage và hạn chế XSS/script bên thứ ba.
- [ ] Bảo vệ token store, backup, CI/CD, gateway và service trung gian.
- [ ] Chỉ chuyển token tới resource thuộc audience đã định.

**Giới hạn giá trị token**

- [ ] Access token có lifetime ngắn phù hợp rủi ro.
- [ ] Audience và scope được giới hạn tối thiểu.
- [ ] Refresh token có rotation/reuse detection hoặc sender constraint phù hợp.
- [ ] Tách ID token, access token và token nghiệp vụ theo profile.
- [ ] Hành động nhạy cảm có step-up/challenge và transaction binding.

**Ngăn replay**

- [ ] Cân nhắc DPoP hoặc mTLS cho client/token có rủi ro cao.
- [ ] Nếu dùng DPoP, kiểm tra cnf.jkt, htm, htu, ath, iat, jti và nonce theo profile.
- [ ] Nếu dùng mTLS, xác minh certificate và cnf.x5t#S256.
- [ ] Dùng trạng thái server-side cho token một lần.
- [ ] Idempotency key được dùng đúng mục đích nghiệp vụ, không thay authentication.
- [ ] Không dùng jti đơn lẻ như cơ chế chống replay.

**Phát hiện và ứng phó**

- [ ] Có telemetry để phát hiện sử dụng token bất thường mà không ghi raw token.
- [ ] Có denylist/session/grant revocation hoặc introspection theo rủi ro.
- [ ] Cache active có TTL nằm trong ngân sách thu hồi.
- [ ] Có playbook khi access/refresh token hoặc PoP key bị lộ.
- [ ] Có thể điều tra request và hành động đã thực hiện trong cửa sổ phơi nhiễm.

**Điều cần nhớ:** Token theft và replay khai thác semantics của credential đang còn hiệu lực. Chữ ký JWT không ngăn người khác dùng một bản sao bearer token. Hãy bảo vệ mọi nơi token đi qua, giới hạn audience/scope/lifetime, dùng sender constraint khi phù hợp, quản lý trạng thái thu hồi và thiết kế chống replay riêng cho từng loại request. Khi token bị lộ, phải thu hồi phía server và điều tra hành động đã xảy ra; xóa token ở client không đủ.

## Tài liệu tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer token semantics và bảo vệ token khi sử dụng.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): Access token, refresh token và grant.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): Refresh token rotation, reuse detection và sender-constrained token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): Kiểm tra trạng thái token tập trung.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): Thu hồi token.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): DPoP và request proof.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): mTLS và certificate-bound token.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT claims, exp và jti.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): Thực hành xác minh JWT.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): Bảo vệ session credential, vòng đời phiên và xử lý logout.
- [OWASP Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): Bảo vệ dữ liệu nhạy cảm trong log.
- [OWASP HTML5 Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html): Rủi ro browser storage.
- [OWASP Cross Site Scripting Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross_Site_Scripting_Prevention_Cheat_Sheet.html): Ngăn XSS.
