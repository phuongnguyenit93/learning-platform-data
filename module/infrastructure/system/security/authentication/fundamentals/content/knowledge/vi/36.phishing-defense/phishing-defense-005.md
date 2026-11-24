# Origin binding — Ràng buộc xác thực với đúng nguồn gốc web

> **Chương:** Chống phishing  
> **Chủ đề:** Origin binding  
> **Phạm vi:** Bài học thuộc module SECURITY_AUTHENTICATION_FUNDAMENTALS, tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này giải thích cách ràng buộc một lần xác thực với nguồn gốc web dự kiến, đặc biệt trong WebAuthn/passkey, OAuth/OIDC callback, cookie và các request giữa origin; đồng thời phân biệt origin binding với TLS, CORS, device binding và transaction confirmation.

## 1. Origin binding là gì?

**Origin binding (ràng buộc nguồn gốc)** là nguyên tắc gắn một credential, response hoặc thao tác xác thực với đúng nguồn gốc web mà ứng dụng dự kiến. Nhờ vậy, bằng chứng được tạo cho website hợp lệ không thể tùy tiện sử dụng ở một website giả mạo có địa chỉ khác.

Ví dụ, Mai đăng nhập vào `https://login.example.edu` bằng passkey. Trình duyệt và authenticator thực hiện WebAuthn cho relying party ID (RP ID) đã cấu hình. Assertion mang thông tin origin của trang gọi API WebAuthn và hash của RP ID. Server kiểm tra cả hai theo cấu hình của mình. Nếu Mai bị dụ mở một website giả có tên gần giống, chẳng hạn `https://login-example.edu`, passkey của `example.edu` không thể được dùng như credential hợp lệ cho RP ID của website giả đó.

Origin binding là một lớp phòng vệ quan trọng trước phishing, nhưng không giải quyết mọi vấn đề:
- Nó không ngăn người dùng tự nhập password vào một trang giả.
- Nó không bảo đảm thiết bị hoặc browser không bị malware kiểm soát.
- Nó không tự xác minh người dùng đã đọc đúng nội dung giao dịch.
- Nó không thay thế kiểm tra issuer, audience, session, authorization hoặc trạng thái account.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Định nghĩa origin theo scheme, host và port.
2. Phân biệt origin với URL, site, domain, RP ID và TLS certificate.
3. Giải thích cách WebAuthn ràng buộc assertion với origin và RP ID.
4. Xác minh `clientDataJSON.origin`, `authenticatorData.rpIdHash`, challenge và chữ ký.
5. Thiết kế RP ID và allowlist origin phù hợp, tránh wildcard quá rộng.
6. Kết hợp redirect URI, state, nonce và PKCE trong OAuth/OIDC.
7. Bảo vệ cookie, CSRF và `postMessage` theo ranh giới origin.
8. Nhận diện rủi ro từ subdomain, IDN homograph, reverse proxy và cấu hình Host.
9. Hiểu giới hạn của origin binding và xây dựng kiểm thử chống phishing.

## 2. Origin được cấu thành như thế nào?

Trong web platform, một origin thông thường được xác định bởi bộ ba:

- **Scheme:** giao thức, ví dụ `https` hoặc `http`.
- **Host:** hostname hoặc địa chỉ host đã được URL parser chuẩn hóa.
- **Port:** cổng kết nối hiệu lực.

Ví dụ:

| URL | Origin |
| --- | --- |
| `https://login.example.edu/sign-in` | `https://login.example.edu` |
| `https://login.example.edu/help` | `https://login.example.edu` |
| `https://login.example.edu:8443/sign-in` | `https://login.example.edu:8443` |
| `http://login.example.edu` | `http://login.example.edu` |
| `https://portal.example.edu` | `https://portal.example.edu` |

Path, query và fragment không thuộc origin. Hai URL có path khác nhau nhưng cùng scheme, host và port thường có cùng origin. Ngược lại, đổi scheme, host hoặc port có thể tạo origin khác.

Port mặc định được URL parser chuẩn hóa theo scheme: HTTPS thường dùng 443 và HTTP thường dùng 80. Không tự viết logic so sánh origin bằng cách cắt chuỗi URL hoặc bỏ port theo suy đoán; hãy dùng parser chuẩn và quy tắc của giao thức.

## 3. Phân biệt origin, site, domain, RP ID và URL

Các khái niệm gần nhau nhưng có mục đích khác nhau:

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **URL** | Địa chỉ đầy đủ của tài nguyên | `https://login.example.edu/account?tab=security` |
| **Origin** | Scheme + host + port | `https://login.example.edu` |
| **Site** | Khái niệm dùng trong một số chính sách browser, thường dựa trên scheme và registrable domain | `https://example.edu` |
| **Domain/hostname** | Tên host trong DNS | `login.example.edu` |
| **RP ID** | Domain identifier mà WebAuthn credential được ràng buộc vào | `example.edu` |
| **TLS certificate identity** | Tên host mà chứng chỉ máy chủ được cấp để xác minh kết nối TLS | `login.example.edu` |

Origin và site không đồng nghĩa. Ví dụ `https://login.example.edu` và `https://portal.example.edu` là hai origin khác nhau nhưng có thể được xem là same-site theo quy tắc browser. Vì thế, cookie SameSite và same-origin policy giải quyết các vấn đề khác nhau.

RP ID không phải origin: nó không chứa scheme hoặc port. Một origin như `https://login.example.edu` có thể dùng RP ID `login.example.edu`, và trong điều kiện hợp lệ có thể dùng domain cha `example.edu`. Server vẫn phải xác minh origin cụ thể được phép.

## 4. Origin binding bảo vệ trước kiểu phishing nào?

Phishing site thường cố làm người dùng tin rằng họ đang đăng nhập vào dịch vụ thật. Attacker có thể:
- đăng ký domain gần giống tên thật;
- dùng subdomain gây nhầm lẫn;
- sao chép giao diện và logo;
- lấy TLS certificate hợp lệ cho domain giả;
- chuyển tiếp password hoặc OTP người dùng nhập theo thời gian thực;
- yêu cầu người dùng approve một lần đăng nhập do attacker khởi tạo.

Nếu credential không ràng buộc với website, người dùng có thể nhập password/OTP vào trang giả và attacker relay dữ liệu tới dịch vụ thật.

Với passkey/WebAuthn, authenticator tạo assertion trong ngữ cảnh RP ID; client data cũng ghi origin. Trang giả ở domain khác không thể yêu cầu authenticator tạo assertion hợp lệ cho RP ID của website thật. Server kiểm tra origin và RP ID hash nên từ chối response sai nguồn gốc.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant P as Phishing site
    participant A as Authenticator
    participant R as RP thật
    U->>P: Mở trang giả có giao diện giống thật
    P->>A: Yêu cầu WebAuthn với RP ID của domain giả
    A-->>P: Không có credential phù hợp / assertion khác RP
    P->>R: Attacker thử dùng response giả hoặc response không đúng origin
    R->>R: Kiểm tra origin + rpIdHash + challenge + signature
    R-->>P: Từ chối
~~~

Origin binding không ngăn mọi lừa đảo. Người dùng vẫn có thể bị lừa chuyển tiền, cấp quyền OAuth, cài malware hoặc nhập password vào trang giả. Nó làm cho một số credential proof không thể relay thành công giữa các origin khác nhau.

## 5. TLS bảo vệ kết nối nhưng không tự ngăn phishing

HTTPS/TLS bảo vệ tính bí mật và toàn vẹn của kênh truyền, đồng thời giúp browser xác minh server có certificate hợp lệ cho hostname đang truy cập. Tuy nhiên, attacker có thể sở hữu một domain giả và xin TLS certificate hợp lệ cho domain đó.

Ví dụ:
- Website thật: `https://login.example.edu`
- Website giả: `https://login-example.edu`

Cả hai có thể dùng HTTPS và hiển thị biểu tượng khóa. TLS cho biết kết nối tới hostname trong URL được bảo vệ theo certificate validation; nó không chứng minh hostname đó thuộc thương hiệu mà người dùng nghĩ tới.

Do đó:
- HTTPS là điều kiện cần cho đăng nhập hiện đại.
- HSTS giúp giảm downgrade và một số rủi ro HTTP.
- Người dùng và hệ thống cần xác minh đúng hostname/origin.
- Passkey/WebAuthn bổ sung ràng buộc credential với RP ID/origin.
- Không dùng biểu tượng khóa làm bằng chứng website là dịch vụ chính thức.

## 6. WebAuthn ràng buộc credential với RP ID và origin

Trong WebAuthn, có hai dữ liệu quan trọng:

1. **`clientDataJSON.origin`:** origin của client context đã khởi tạo thao tác WebAuthn.
2. **`authenticatorData.rpIdHash`:** SHA-256 hash của RP ID mà authenticator sử dụng.

Authenticator ký dữ liệu gồm `authenticatorData` và hash của raw `clientDataJSON`. Server cần xác minh chữ ký bằng public key của credential đã đăng ký và kiểm tra origin/RP ID theo cấu hình tin cậy.

Các trường thường gặp trong client data:
- `type`: ví dụ `webauthn.get` cho assertion;
- `challenge`: challenge do RP tạo;
- `origin`: origin của trang;
- `crossOrigin`: tín hiệu về ngữ cảnh cross-origin nếu có;
- `topOrigin`: top-level origin trong một số flow cross-origin.

Trong authenticator data:
- `rpIdHash`: hash của RP ID;
- cờ UP (User Presence);
- cờ UV (User Verification);
- sign counter nếu authenticator cung cấp;
- extension data nếu được sử dụng.

Không tự giải mã rồi tin payload. Các trường cần được kiểm tra như một phần của quá trình xác minh WebAuthn đầy đủ.

## 7. Quy trình xác minh WebAuthn origin binding

Một RP verifier nên thực hiện các kiểm tra sau theo đặc tả và thư viện WebAuthn đã được kiểm chứng:

1. Tìm pending authentication transaction theo challenge/session đã lưu.
2. Giải mã `clientDataJSON` nhưng giữ nguyên bytes gốc để tính hash.
3. Kiểm tra `type` đúng với ceremony, ví dụ `webauthn.get`.
4. Kiểm tra challenge khớp transaction, còn hạn và chưa dùng.
5. Parse origin theo URL parser chuẩn và so sánh với allowlist origin chính xác.
6. Xử lý `crossOrigin`/`topOrigin` theo policy; từ chối cross-origin flow nếu không được cấu hình.
7. Tính SHA-256 của RP ID đã cấu hình và so sánh với `authenticatorData.rpIdHash`.
8. Xác minh chữ ký trên `authenticatorData || SHA-256(clientDataJSON)` bằng public key đã gắn với credential.
9. Kiểm tra UP và UV theo policy.
10. Kiểm tra credential ID/account binding, trạng thái credential và các extension cần thiết.
11. Consume challenge một lần và hoàn tất transaction theo cách chống replay.

### Minh họa dữ liệu assertion

~~~json
{
  "id": "credential-id",
  "type": "public-key",
  "response": {
    "clientDataJSON": "<base64url-encoded-client-data>",
    "authenticatorData": "<base64url-encoded-authenticator-data>",
    "signature": "<base64url-encoded-signature>",
    "userHandle": "<optional-user-handle>"
  }
}
~~~

Các giá trị trên chỉ minh họa cấu trúc. Không thể xác minh assertion chỉ bằng cách decode JSON; phải kiểm tra chữ ký, challenge, origin, RP ID hash, credential và flags theo WebAuthn.

## 8. RP ID phải được chọn có chủ đích

RP ID là domain mà passkey được ràng buộc. Nó:
- không chứa scheme;
- không chứa port;
- không chứa path;
- phải thỏa quy tắc domain relationship với origin hiện tại;
- không được là public suffix như `com` hoặc `co.uk`.

Ví dụ, trang `https://login.example.edu` có thể sử dụng RP ID `login.example.edu`; tùy cấu hình hợp lệ, có thể chọn `example.edu` để chia sẻ credential giữa các subdomain thuộc cùng relying party.

### RP ID rộng có hệ quả gì?

Nếu chọn RP ID ở domain cha, các subdomain hợp lệ có thể có khả năng gọi WebAuthn với RP ID đó. Điều này có thể hữu ích cho hệ thống nhiều subdomain, nhưng làm tăng tác động nếu một subdomain bị chiếm quyền hoặc có XSS.

Server phải:
- duy trì allowlist origin cụ thể;
- không chấp nhận mọi subdomain chỉ vì cùng RP ID;
- kiểm soát subdomain takeover và DNS;
- phân tách ứng dụng không cùng trust level sang RP ID khác nếu phù hợp;
- tránh đổi RP ID tùy tiện sau khi credential đã đăng ký vì có thể làm credential hiện tại không còn dùng được.

RP ID hẹp thường dễ giới hạn phạm vi hơn. Chọn RP ID rộng chỉ khi có yêu cầu kiến trúc rõ và có kiểm soát origin tương ứng.

## 9. Origin allowlist: so sánh chính xác

RP nên cấu hình danh sách origin được phép, ví dụ:

~~~text
https://login.example.edu
https://account.example.edu
https://localhost:8443   # chỉ cho môi trường phát triển cục bộ
~~~

Trong production, chỉ đưa origin thật sự cần thiết vào allowlist. Không dùng:
- kiểm tra chuỗi con như `origin.contains("example.edu")`;
- kiểm tra suffix thiếu dấu phân cách domain;
- wildcard toàn bộ subdomain nếu không có threat model;
- giá trị Host/X-Forwarded-Host do request không tin cậy cung cấp;
- origin lấy từ query parameter hoặc form do client gửi.

Ví dụ, `https://example.edu.attacker.invalid` có chứa chuỗi `example.edu` nhưng không thuộc domain đó. So sánh chuỗi con có thể chấp nhận nhầm origin giả.

Hãy parse origin theo chuẩn, chuẩn hóa scheme/host/port theo URL semantics và so sánh với cấu hình được quản trị. Không tự thêm wildcard hoặc bỏ port để “làm cho login hoạt động”.

## 10. Origin binding không đồng nghĩa device binding

WebAuthn origin binding ràng buộc credential proof với RP ID và origin. Nó không nhất thiết chứng minh:
- private key nằm trên đúng thiết bị vật lý đã đăng ký ban đầu;
- credential không được đồng bộ giữa thiết bị;
- thiết bị không bị malware;
- user đang dùng một thiết bị do tổ chức quản lý;
- user đã xem và chấp thuận nội dung giao dịch.

Một passkey có thể được đồng bộ qua hệ sinh thái nền tảng. Dù credential có thể dùng trên nhiều thiết bị, nó vẫn được ràng buộc với RP ID. Nếu cần device assurance, cần thêm device certificate, attestation hoặc MDM signal theo policy; các tín hiệu đó có mục đích khác và có giới hạn riêng.

## 11. Password và OTP không có origin binding tương đương

Password là secret người dùng nhập. Một trang giả có thể yêu cầu người dùng nhập password và relay tới website thật. OTP cũng có thể bị attacker chuyển tiếp theo thời gian thực.

Các biện pháp như:
- kiểm tra URL và hostname;
- password manager có domain matching;
- MFA;
- cảnh báo phishing;
- rate limit;
- phát hiện đăng nhập bất thường;

có thể giảm rủi ro, nhưng password/OTP không có ràng buộc mật mã với origin theo cách WebAuthn làm.

TOTP không tự gắn mã với website, transaction hoặc RP ID. SMS OTP càng dễ bị relay hoặc đánh cắp qua SIM swap. Với hệ thống cần chống phishing mạnh, ưu tiên passkey/security key và kiểm tra WebAuthn đầy đủ.

## 12. OAuth/OIDC: ràng buộc callback với redirect URI

Trong OAuth/OIDC, authorization response phải quay về redirect URI đã đăng ký cho client. Authorization server cần kiểm tra redirect URI theo quy tắc giao thức; tránh wildcard rộng và open redirect.

RP/client nên kết hợp:
- **Exact redirect URI registration:** chỉ chấp nhận callback đã đăng ký, theo quy tắc áp dụng.
- **state:** ràng buộc response với browser transaction, giảm login CSRF và response mix-up.
- **PKCE:** ràng buộc authorization code với code verifier của client đã khởi tạo request.
- **nonce:** ràng buộc ID Token với OIDC authentication request.
- **issuer validation:** xác minh response đến từ OP dự kiến.
- **audience validation:** xác minh ID Token dành cho client hiện tại.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant RP as Client / RP
    participant OP as Authorization Server
    B->>RP: Bắt đầu sign-in
    RP->>RP: Tạo state, nonce, PKCE verifier
    RP-->>B: Redirect tới OP với redirect_uri đã đăng ký
    B->>OP: Authorization request
    OP-->>B: Redirect về callback + code + state
    B->>RP: Callback
    RP->>RP: Kiểm tra state và pending transaction
    RP->>OP: Đổi code + PKCE verifier
    OP-->>RP: ID Token / Access Token
    RP->>RP: Verify issuer, audience, signature, nonce
~~~

OAuth redirect URI binding không giống WebAuthn origin binding, nhưng cùng góp phần ràng buộc response vào đúng client và callback. Không cho phép người dùng hoặc query parameter tùy ý chọn redirect target.

## 13. Cookie và origin/host scope

Cookie được gửi tự động theo domain/path và các thuộc tính browser. Cấu hình sai có thể làm credential session bị chia sẻ quá rộng.

Khuyến nghị cho session cookie:
- ưu tiên host-only cookie nếu không cần chia sẻ subdomain;
- dùng `Secure` để chỉ gửi qua HTTPS;
- dùng `HttpOnly` để JavaScript không đọc trực tiếp cookie;
- đặt `SameSite` phù hợp với flow;
- cân nhắc prefix `__Host-` với Path=/ và không có Domain;
- không đặt session cookie trên domain cha nếu subdomain có mức tin cậy khác nhau.

Ví dụ:

~~~http
Set-Cookie: __Host-session=<opaque>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Cookie Domain rộng không phải cách thay thế cho SSO. Nếu các subdomain cần chia sẻ đăng nhập, hãy dùng federation hoặc cơ chế session exchange được thiết kế rõ, thay vì chia sẻ bearer cookie cho mọi subdomain.

## 14. CSRF và kiểm tra Origin header

Origin header có thể hỗ trợ server xác định nguồn của một request thay đổi trạng thái. Với endpoint nhạy cảm, server có thể kiểm tra Origin theo allowlist và dùng CSRF token/SameSite theo threat model.

Ví dụ:
- request POST từ `https://account.example.edu` được chấp nhận nếu đó là origin hợp lệ cho endpoint;
- request từ `https://evil.invalid` bị từ chối;
- request thiếu Origin được xử lý theo policy rõ, không tự động coi là trusted.

Không dùng Origin header làm bằng chứng đăng nhập. Client có thể không gửi Origin trong một số request; non-browser client có thể tự đặt header; proxy hoặc middleware sai cấu hình có thể làm mất thông tin. Origin check là một lớp CSRF defense, không thay thế session authentication và authorization.

## 15. CORS không phải cơ chế xác thực

CORS (Cross-Origin Resource Sharing) là chính sách browser kiểm soát việc JavaScript ở origin này có được đọc response từ origin khác hay không. CORS không chứng minh danh tính người gọi và không tự ngăn mọi CSRF.

Những hiểu lầm thường gặp:
- “Chỉ bật CORS cho domain thật thì API đã được bảo vệ.” Sai: request vẫn có thể được gửi trong một số tình huống; CORS chủ yếu điều khiển quyền đọc response.
- “Có Access-Control-Allow-Origin nghĩa request đã authenticated.” Sai: authentication cần cookie/token/credential hợp lệ.
- “CORS thay CSRF token.” Sai: cần thiết kế CSRF riêng cho cookie-authenticated state-changing requests.
- “Origin trong CORS có thể wildcard khi bật credentials.” Browser có giới hạn cụ thể; cấu hình sai có thể làm lộ dữ liệu.

Chỉ echo origin sau khi kiểm tra allowlist chính xác; không phản chiếu Origin tùy ý từ request.

## 16. postMessage và iframe cross-origin

Ứng dụng có thể dùng `window.postMessage` để trao đổi dữ liệu giữa các window/iframe. Khi đó, origin là một phần quan trọng của kiểm soát tin cậy.

Nguyên tắc:
- đặt `targetOrigin` cụ thể, không dùng `*` cho dữ liệu nhạy cảm;
- khi nhận message, kiểm tra `event.origin` chính xác;
- kiểm tra `event.source` nếu cần ràng buộc đúng window;
- validate schema, loại message và transaction state;
- không gửi token hoặc secret cho origin không được phép;
- không coi message từ một origin hợp lệ là authorization cho mọi hành động.

Với WebAuthn trong iframe cross-origin, cần cấu hình theo quy tắc WebAuthn/Permissions Policy và kiểm tra `crossOrigin`/`topOrigin` phù hợp. Nếu ứng dụng không cần flow embedded, cách an toàn hơn thường là từ chối cross-origin ceremony.

## 17. Reverse proxy, Host header và external origin

Ứng dụng sau reverse proxy có thể nhận request nội bộ bằng HTTP hoặc hostname nội bộ, trong khi người dùng truy cập qua HTTPS và public hostname. Nếu ứng dụng tự suy ra origin từ header không tin cậy, attacker có thể thao túng callback URL, redirect hoặc origin validation.

Kiểm soát:
- cấu hình public/external origin rõ ràng ở server;
- chỉ tin `Forwarded`/`X-Forwarded-Host`/`X-Forwarded-Proto` từ proxy đã xác thực;
- proxy phải xóa header forwarded do client gửi trước khi thêm giá trị của nó;
- allowlist Host ở ingress;
- không dựng redirect URI từ Host header tùy ý;
- bảo đảm TLS giữa các hop theo threat model;
- kiểm tra cấu hình callback trong từng môi trường.

Không dùng request Host làm nguồn chân lý để tự thêm origin vào allowlist. Sai cấu hình proxy có thể biến kiểm tra origin thành kiểm tra dữ liệu attacker kiểm soát.

## 18. IDN homograph, subdomain và canonicalization

Tên miền quốc tế hóa (IDN) có thể chứa ký tự Unicode trông giống ký tự Latin. Attacker có thể đăng ký domain có hình thức gần giống domain thật. Browser thường biểu diễn IDN qua quy tắc punycode/canonicalization, nhưng cách hiển thị có thể khác nhau.

Rủi ro khác:
- `login.example.edu.attacker.invalid` không phải subdomain của `example.edu`;
- subdomain bị bỏ quên có thể bị takeover;
- cookie Domain quá rộng có thể bị ảnh hưởng bởi subdomain yếu;
- RP ID ở domain cha làm tăng phạm vi origin cần kiểm soát;
- so sánh Unicode/ASCII tùy tiện có thể tạo bypass.

Nguyên tắc:
- dùng URL parser và thư viện domain chuẩn;
- không tự viết Unicode normalization hoặc suffix matching;
- quản lý DNS/subdomain và loại bỏ record không còn dùng;
- tránh wildcard origin rộng;
- dùng allowlist origin đã canonicalize theo quy tắc chuẩn;
- kiểm tra cả IDN/punycode trong test và log điều tra.

## 19. Origin binding có giới hạn gì?

Origin binding không phải một lớp bảo vệ toàn năng.

| Tình huống | Origin binding giúp gì? | Cần thêm gì? |
| --- | --- | --- |
| Phishing domain khác | Passkey proof cho RP thật không dùng được ở origin giả | User education, password manager và cảnh báo domain. |
| TLS hợp lệ trên domain giả | Không coi certificate của domain giả là origin thật | Kiểm tra domain và dùng passkey. |
| Password bị nhập vào trang giả | Không ngăn password bị lộ | Passkey, password manager, MFA chống phishing và incident response. |
| Malware trên origin thật | Origin có thể vẫn đúng dù nội dung bị kiểm soát | Browser/device security, CSP, patching và monitoring. |
| XSS trên origin thật | Script chạy trong origin hợp lệ có thể thao tác phiên | Output encoding, CSP, dependency security và session controls. |
| Subdomain takeover | Origin của subdomain có thể nằm trong phạm vi RP ID rộng | Origin allowlist hẹp, DNS/subdomain governance. |
| Thiết bị bị chiếm | Credential có thể được dùng từ môi trường bị kiểm soát | Device posture, revocation và risk-based step-up. |
| Giao dịch bị thay sau khi hiển thị | WebAuthn origin binding không tự ký amount/payee | Transaction confirmation/dynamic linking/trusted display. |

Nếu attacker kiểm soát origin thật, origin binding không thể phân biệt code hợp lệ và code độc hại đang chạy cùng origin. Bảo vệ origin là một phần của bảo vệ toàn bộ ứng dụng.

## 20. Logging và vận hành

Có thể ghi:
- origin đã được parse/canonicalize;
- RP ID và client ID theo cấu hình;
- kết quả kiểm tra origin/RP ID hash;
- reason code như origin mismatch, RP ID mismatch, challenge expired;
- correlation ID và credential reference opaque;
- phiên bản allowlist/configuration;
- môi trường (production/staging/development).

Không log:
- raw session cookie, authorization code, ID/access/refresh token;
- private key hoặc raw credential secret;
- toàn bộ authenticator response nếu không cần cho điều tra;
- dữ liệu cá nhân không cần thiết.

Origin mismatch có thể là lỗi cấu hình, browser extension, app domain migration hoặc dấu hiệu phishing. Theo dõi tỷ lệ lỗi theo client/version và thay đổi cấu hình; không tự động mở rộng allowlist khi thấy lỗi tăng. Mọi thay đổi origin/RP ID cần review, phê duyệt và kiểm thử trước triển khai.

## 21. Pseudocode xác minh origin trong WebAuthn

Ví dụ Java minh họa trách nhiệm chính; không thay thế thư viện WebAuthn:

~~~java
VerifiedCredential verifyAssertion(
        AssertionResponse response,
        PendingChallenge pending,
        CredentialRecord credential) {

    ClientData clientData =
        webAuthnLibrary.parseClientData(response.clientDataJson());

    require(clientData.type().equals("webauthn.get"));
    require(challengeStore.matchesAndIsActive(
        pending.id(), clientData.challenge()));

    // Parse/canonicalize with a standards-compliant URL implementation.
    Origin origin = originParser.parse(clientData.origin());
    require(configuredAllowedOrigins().contains(origin));

    AuthenticatorData authData =
        webAuthnLibrary.parseAuthenticatorData(response.authenticatorData());

    byte[] expectedRpIdHash = sha256(configuredRpId().getBytes(UTF_8));
    require(constantTimeEquals(authData.rpIdHash(), expectedRpIdHash));

    byte[] clientDataHash = sha256(response.rawClientDataJsonBytes());
    byte[] signedBytes = concat(response.authenticatorData(), clientDataHash);

    signatureVerifier.verify(
        credential.publicKey(), signedBytes, response.signature());

    require(authData.userPresent());
    if (policy.requiresUserVerification()) {
        require(authData.userVerified());
    }

    credentialPolicy.requireActive(credential);
    challengeStore.consumeOnce(pending.id());

    return VerifiedCredential.from(credential, origin);
}
~~~

Pseudocode giả định thư viện đã xử lý base64url, cấu trúc CBOR/authenticator data, thuật toán, credential binding và các kiểm tra bắt buộc khác. Trong production:
- hash raw bytes của clientDataJSON, không parse rồi serialize lại;
- kiểm tra `crossOrigin` và `topOrigin` theo policy;
- kiểm tra credential ID/account binding;
- xử lý sign counter theo semantics authenticator;
- kiểm tra challenge expiry, session transaction và replay atomically;
- dùng thư viện WebAuthn được duy trì và test theo chuẩn.

## 22. Kiểm thử origin binding

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| WebAuthn assertion từ origin chính xác | Tiếp tục xác minh các trường còn lại. |
| Origin khác scheme (`http` thay vì `https`) | Từ chối. |
| Origin khác host | Từ chối. |
| Origin khác port | Từ chối nếu không nằm trong allowlist. |
| Origin có suffix giả như `example.edu.attacker.invalid` | Từ chối. |
| RP ID hash không khớp RP ID cấu hình | Từ chối. |
| Challenge không khớp hoặc đã dùng | Từ chối. |
| `clientDataJSON.type` sai | Từ chối. |
| Chữ ký assertion sai | Từ chối. |
| Credential bị revoke | Từ chối. |
| UV bắt buộc nhưng UV flag thiếu | Từ chối theo policy. |
| Cross-origin iframe không được phép | Từ chối. |
| Cross-origin iframe được phép theo policy | Kiểm tra origin, topOrigin và Permissions Policy đầy đủ. |
| RP ID domain cha với origin không nằm trong allowlist | Từ chối. |
| Subdomain bị takeover | Origin ngoài allowlist không được chấp nhận. |
| IDN/punycode lookalike | Từ chối origin không khớp canonical allowlist. |
| Host header giả | Không làm thay đổi external origin hoặc redirect URI tin cậy. |
| X-Forwarded-Host do client tự gửi | Proxy phải loại bỏ; app không tin giá trị đó. |
| OAuth callback redirect URI không đăng ký | Authorization server từ chối. |
| OAuth state sai hoặc thiếu transaction | RP từ chối callback. |
| PKCE verifier sai | Token exchange thất bại. |
| OIDC issuer/audience sai | RP từ chối token. |
| CORS phản chiếu Origin tùy ý | Security test thất bại. |
| CSRF request từ origin lạ | Bị từ chối theo CSRF policy. |
| postMessage từ origin lạ | Bị bỏ qua/từ chối. |
| `targetOrigin="*"` cho message nhạy cảm | Static/security review phát hiện. |

### Kiểm thử cấu hình theo môi trường

Kiểm tra riêng production, staging, development và localhost:
- origin allowlist không trộn môi trường;
- RP ID đúng với domain dự kiến;
- callback URI đúng đăng ký;
- proxy header chỉ được tin từ proxy;
- cookie scope không bị mở rộng;
- không còn domain cũ hoặc subdomain không quản lý;
- migration origin có kế hoạch credential và redirect rõ ràng.

## 23. Bài tập tình huống

Một tổ chức có ba ứng dụng: `login.example.edu`, `portal.example.edu` và `admin.example.edu`. Họ chọn RP ID `example.edu` cho cả ba. Server kiểm tra origin bằng điều kiện `origin.endsWith("example.edu")`. Một subdomain cũ bị bỏ quên có thể được attacker chiếm quyền. Ứng dụng cũng nhận `X-Forwarded-Host` từ request và dùng nó để dựng redirect URI. Khi đăng nhập, password và OTP được chấp nhận từ mọi domain có giao diện giống cổng thật.

**Yêu cầu phân tích:**

1. Vì sao RP ID domain cha làm tăng phạm vi cần bảo vệ?
2. Điều kiện suffix hiện tại có thể chấp nhận hostname giả nào?
3. Nên dùng allowlist origin ra sao cho ba ứng dụng?
4. Khi nào nên tách RP ID theo ứng dụng?
5. Vì sao TLS certificate trên subdomain giả không chứng minh website là chính thức?
6. Cách xử lý `X-Forwarded-Host` và external origin như thế nào?
7. Password/OTP có thể bị relay ra sao và passkey thay đổi điều gì?
8. Những kiểm thử nào cần thêm trước khi triển khai?

**Hướng phân tích:** RP ID cha có thể cho phép các subdomain hợp lệ gọi WebAuthn trong phạm vi đó; vì vậy phải kiểm tra origin chính xác. Suffix matching thiếu dấu phân cách và URL parsing có thể chấp nhận hostname attacker. Cấu hình allowlist gồm đúng origin của ba app; cân nhắc RP ID riêng nếu cần cô lập trust. Proxy phải strip forwarded headers do client gửi và app dùng external origin cấu hình tĩnh. TLS bảo vệ hostname đang truy cập, không xác nhận thương hiệu. Password/OTP không origin-bound; passkey assertion được ràng buộc với RP ID/origin, nhưng vẫn cần bảo vệ origin thật và kiểm tra WebAuthn đầy đủ.

## 24. Checklist review

- [ ] Origin được hiểu là scheme + host + port; path/query không thuộc origin.
- [ ] Origin được parse/canonicalize bằng thư viện chuẩn, không dùng substring/suffix tự viết.
- [ ] Phân biệt origin, site, domain, RP ID và TLS certificate identity.
- [ ] HTTPS/TLS được bật; không coi biểu tượng khóa là bằng chứng thương hiệu.
- [ ] RP ID không phải URL; không dùng public suffix.
- [ ] RP ID scope được chọn có chủ đích và có đánh giá rủi ro subdomain.
- [ ] WebAuthn kiểm tra clientDataJSON.type, challenge, origin và cross-origin context.
- [ ] WebAuthn kiểm tra authenticatorData.rpIdHash, signature, UP/UV và credential binding.
- [ ] Hash raw clientDataJSON bytes, không serialize lại trước khi hash.
- [ ] Origin allowlist là danh sách origin chính xác, không wildcard tùy tiện.
- [ ] OAuth redirect URI được đăng ký chặt; state, nonce, PKCE, issuer và audience được kiểm tra.
- [ ] Cookie session có scope hẹp, Secure, HttpOnly và SameSite phù hợp.
- [ ] CSRF được bảo vệ riêng; Origin header không bị dùng như authentication.
- [ ] CORS không bị coi là authorization hoặc CSRF defense đầy đủ.
- [ ] postMessage dùng targetOrigin cụ thể và kiểm tra event.origin/source.
- [ ] Cross-origin iframe WebAuthn chỉ bật khi có nhu cầu và policy rõ.
- [ ] Reverse proxy chỉ được tin forwarded headers từ nguồn đã xác thực.
- [ ] Host header không điều khiển allowlist hoặc redirect URI.
- [ ] IDN, subdomain takeover và domain migration được kiểm soát.
- [ ] Có test phishing origin giả, replay, challenge mismatch, proxy header và CORS/CSRF.

## 25. Ghi nhớ

**Origin binding ràng buộc bằng chứng xác thực với đúng nguồn gốc web dự kiến.** Trong WebAuthn, RP xác minh origin trong client data và RP ID hash trong authenticator data, cùng challenge, chữ ký và credential đã đăng ký. Nhờ vậy, passkey khó bị relay từ website thật sang domain phishing. OAuth/OIDC dùng redirect URI, state, nonce, PKCE, issuer và audience để ràng buộc callback và token với đúng client.

Origin binding không thay thế HTTPS, bảo vệ XSS, authorization, device assurance hoặc transaction confirmation. Khi review, hãy hỏi: **Origin nào được phép? RP ID rộng tới đâu? Server kiểm tra origin và rpIdHash bằng cách nào? Subdomain hoặc proxy có thể làm thay đổi trust boundary không? Password/OTP có bị relay không? Nếu origin thật bị chiếm quyền, lớp bảo vệ tiếp theo là gì?**
