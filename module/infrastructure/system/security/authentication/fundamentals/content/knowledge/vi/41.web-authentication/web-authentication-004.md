# Redirect flow — Luồng chuyển hướng trình duyệt trong xác thực web

> **Chương:** Authentication trong web  
> **Chủ đề:** Redirect flow  
> **Phạm vi:** Bài học thuộc module SECURITY_AUTHENTICATION_FUNDAMENTALS, tìm hiểu nguyên lý xác thực danh tính từ credential, mật khẩu, MFA, passkey và chứng chỉ đến token, phiên, liên kết danh tính và khôi phục tài khoản. Bài này giải thích cách trình duyệt chuyển người dùng giữa ứng dụng (Relying Party/client) và nhà cung cấp danh tính/Authorization Server, tập trung vào OpenID Connect Authorization Code Flow với PKCE, callback, state, nonce, redirect URI, trao đổi code, quản lý session và phòng chống lỗi chuyển hướng.

## 1. Redirect flow là gì?

**Redirect flow (luồng chuyển hướng)** là cách một ứng dụng web điều hướng trình duyệt của người dùng tới một hệ thống xác thực hoặc nhà cung cấp danh tính, để người dùng đăng nhập tại nơi đó, rồi quay lại ứng dụng qua một địa chỉ callback đã đăng ký.

Ví dụ, Mai mở cổng học tập. Cổng không trực tiếp xử lý mật khẩu của Mai mà chuyển browser tới Identity Provider (IdP). Sau khi Mai đăng nhập và hoàn tất MFA, IdP chuyển browser về callback của cổng học tập cùng một authorization code và giá trị state. Backend của cổng xác minh transaction, đổi code lấy token qua kênh server-to-server, xác minh ID Token, rồi tạo session riêng cho Mai.

Redirect chỉ là cơ chế điều hướng browser. Nó không tự chứng minh danh tính và cũng không có nghĩa ứng dụng được phép tin mọi dữ liệu browser gửi về. Bằng chứng xác thực phải được xác minh theo giao thức và gắn với đúng transaction, client, issuer và session.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Mô tả các vai trò Browser, Relying Party/client, Identity Provider và callback endpoint.
2. Giải thích Authorization Code Flow trong OpenID Connect.
3. Phân biệt authorization code, ID Token, Access Token và session cookie.
4. Thiết kế redirect URI chính xác và bảo vệ callback.
5. Dùng state, nonce và PKCE đúng mục đích.
6. Xác minh ID Token và ràng buộc kết quả với đúng issuer/client/browser transaction.
7. Phòng chống open redirect, login CSRF, authorization response injection và mix-up.
8. Xử lý cookie SameSite, response mode, reverse proxy và session fixation.
9. Phân biệt front-channel redirect với back-channel token exchange/logout.
10. Kiểm thử các nhánh thành công, lỗi, timeout, replay và cấu hình sai.

## 2. Các vai trò trong redirect-based authentication

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| **User Agent / Browser** | Điều hướng giữa RP và IdP; giữ trạng thái browser theo cookie | Browser của Mai |
| **Relying Party (RP) / OAuth Client** | Ứng dụng muốn xác thực người dùng | Cổng học tập |
| **OpenID Provider (OP) / Identity Provider** | Xác thực người dùng và phát hành kết quả OIDC | IdP của trường |
| **Authorization Server (AS)** | Xác minh request và phát authorization code/token | Có thể cùng hệ thống với OP |
| **Callback endpoint** | Nhận authorization response tại RP | /auth/callback |
| **Token endpoint** | Nhận code và client proof từ backend để đổi token | /oauth2/token |

Trong OpenID Connect, OP thực hiện xác thực người dùng và phát ID Token. OAuth Authorization Server cấp access token để client truy cập resource. Nhiều nền tảng kết hợp OP và AS trong một hệ thống, nhưng RP vẫn phải hiểu mục đích của từng token.

## 3. Khi nào dùng redirect flow?

Redirect-based login phù hợp khi:
- ứng dụng muốn giao việc xác thực cho IdP tập trung;
- người dùng cần SSO giữa nhiều ứng dụng;
- IdP hỗ trợ MFA, passkey, federation hoặc policy đăng nhập;
- ứng dụng muốn tránh nhận và lưu password của người dùng;
- client có thể xử lý callback và bảo vệ transaction state.

Các ví dụ:
- ứng dụng doanh nghiệp chuyển browser tới IdP công ty;
- cổng học tập đăng nhập bằng tài khoản trường;
- ứng dụng SaaS dùng OIDC để đăng nhập khách hàng;
- ứng dụng nội bộ hỗ trợ nhiều IdP theo tenant.

Không dùng redirect flow để chuyển access token qua URL. Không coi một redirect về callback là bằng chứng đã đăng nhập. Ứng dụng cần kiểm tra response và chỉ tạo session sau khi xác minh hoàn tất.

## 4. OIDC Authorization Code Flow với PKCE

Với ứng dụng web có backend, mô hình thường dùng là OpenID Connect Authorization Code Flow. Client khởi tạo request tới authorization endpoint, browser điều hướng người dùng tới OP, OP trả authorization code về callback, rồi backend đổi code tại token endpoint.

PKCE bổ sung một cặp verifier/challenge để ràng buộc authorization code với client transaction đã khởi tạo. Dù confidential web client có thể xác thực bằng client credential tại token endpoint, vẫn nên dùng PKCE theo best practice hiện hành.

~~~mermaid
sequenceDiagram
    participant B as Browser
    participant RP as Web App / RP
    participant OP as OpenID Provider
    B->>RP: GET /login
    RP->>RP: Tạo state, nonce, code_verifier
    RP->>RP: Tạo code_challenge = S256(code_verifier)
    RP-->>B: Redirect tới authorization endpoint
    B->>OP: Authorization request
    OP->>OP: Xác thực user và áp dụng MFA/policy
    OP-->>B: Redirect callback với code + state
    B->>RP: GET /auth/callback?code=...&state=...
    RP->>RP: Kiểm tra state và transaction
    RP->>OP: POST token endpoint + code + code_verifier
    OP->>OP: Kiểm tra code, client, redirect_uri, PKCE
    OP-->>RP: ID Token + Access Token
    RP->>RP: Xác minh ID Token và nonce
    RP->>RP: Tạo session mới
    RP-->>B: Set-Cookie + redirect về trang nội bộ
~~~

Điểm quan trọng:
- browser chỉ mang authorization code qua front channel;
- code được đổi lấy token qua back channel;
- ID Token xác nhận kết quả authentication theo OIDC;
- Access Token dành cho resource server;
- RP tạo session cookie của chính ứng dụng sau khi xác minh;
- code, state, nonce và PKCE verifier phải gắn với transaction cụ thể.

## 5. Bước 1: khởi tạo login transaction

Khi người dùng chọn đăng nhập, RP tạo một transaction mới. Transaction nên có:
- state ngẫu nhiên, khó đoán và dùng một lần;
- nonce ngẫu nhiên nếu dùng OIDC;
- PKCE code_verifier và code_challenge;
- issuer/OP được chọn;
- client ID và redirect URI dự kiến;
- browser/session binding;
- thời điểm tạo và expiry;
- return path nội bộ đã được kiểm tra;
- response mode và các tham số policy cần thiết.

Transaction được lưu server-side hoặc trong một cơ chế integrity-protected phù hợp. Không lưu PKCE verifier, nonce hoặc state trong nơi JavaScript không đáng tin có thể đọc nếu kiến trúc yêu cầu giữ bí mật. Không dùng một state tĩnh cho tất cả người dùng.

Mỗi login attempt cần transaction riêng. Điều này hỗ trợ nhiều tab, nhiều IdP và chống việc response của một lần đăng nhập bị gắn nhầm vào một lần khác.

## 6. State: ràng buộc response với browser transaction

**State** là giá trị do RP tạo trước khi redirect và nhận lại trong authorization response. RP so sánh state nhận được với transaction đang chờ.

State giúp:
- chống login CSRF/authorization response injection;
- ghép callback với login attempt đã khởi tạo;
- ngăn attacker tự tạo response rồi ép browser nạn nhân gửi tới callback;
- mang correlation reference tới transaction server-side.

State nên:
- đủ ngẫu nhiên và không thể đoán;
- có expiry ngắn;
- dùng một lần;
- được ràng buộc với browser/session khởi tạo;
- được kiểm tra trước khi xử lý code hoặc error;
- không chứa dữ liệu nhạy cảm hoặc URL tùy ý.

Không dùng state như bằng chứng authentication. State đúng chỉ cho biết callback phù hợp với transaction đã bắt đầu; RP vẫn phải đổi code và xác minh token.

### State và return URL

Không nhúng một URL tùy ý vào state rồi redirect người dùng tới URL đó sau login. Nếu cần return path, lưu path nội bộ trong transaction server-side hoặc kiểm tra chặt theo allowlist. State nên là opaque random reference hoặc giá trị integrity-protected theo thiết kế.

## 7. Nonce: ràng buộc ID Token với authentication request

Trong OIDC, **nonce** là giá trị RP gửi trong authorization request và OP đưa vào ID Token. RP kiểm tra nonce trong ID Token khớp với nonce đã lưu cho transaction.

Nonce giúp chống replay hoặc gắn nhầm ID Token vào một authentication request khác. Nó khác state:
- state được trả qua authorization response để liên kết callback với browser transaction;
- nonce nằm trong ID Token để liên kết token với OIDC request.

State và nonce có thể đều là giá trị ngẫu nhiên, nhưng không thay thế cho nhau. Với OIDC, RP cần dùng và xác minh nonce theo profile đã chọn.

## 8. PKCE: ràng buộc authorization code với client transaction

PKCE (Proof Key for Code Exchange) dùng:
- **code_verifier:** chuỗi ngẫu nhiên do client tạo và giữ;
- **code_challenge:** giá trị dẫn xuất gửi trong authorization request;
- **code_challenge_method:** nên dùng S256.

Ví dụ khái niệm:

~~~text
code_verifier  = high-entropy-random-string
code_challenge = BASE64URL(SHA256(ASCII(code_verifier)))
method         = S256
~~~

Khi đổi code tại token endpoint, client gửi code_verifier. OP tính lại challenge và so sánh với giá trị gắn với authorization code. Attacker chỉ chặn được authorization code mà không có verifier thì không thể đổi code thành token.

Không dùng plain nếu S256 được hỗ trợ. Không gửi code_verifier qua browser redirect. Với backend web app, verifier nên được giữ server-side và gắn với transaction.

## 9. Redirect URI: đăng ký chính xác

Redirect URI xác định nơi OP được phép gửi authorization response. Client phải đăng ký trước các callback URI được phép. AS/OP cần so sánh theo quy tắc chính xác của OAuth/OIDC và tránh wildcard rộng.

Ví dụ callback đã đăng ký:

~~~text
https://portal.example.edu/oidc/callback
~~~

Không chấp nhận:
- bất kỳ URL nào client gửi trong query parameter;
- URL có hostname gần giống domain thật;
- wildcard toàn bộ subdomain không có threat model;
- callback tới domain bên thứ ba;
- open redirect endpoint có thể chuyển tiếp sang host attacker;
- redirect URI được dựng từ Host header không tin cậy.

Redirect URI cần nhất quán giữa authorization request và token request theo yêu cầu của AS. Không tự chuẩn hóa bằng cách bỏ port, path hoặc query theo suy đoán.

### Môi trường development

Localhost callback và native app loopback redirect có quy tắc riêng theo profile. Không đưa callback development vào production allowlist nếu không cần. Tách client registration theo môi trường.

## 10. Authorization request: tham số cần thiết

Một OIDC Authorization Code request thường có:
- response_type=code;
- client_id;
- redirect_uri;
- scope có chứa openid;
- state;
- nonce;
- code_challenge;
- code_challenge_method=S256;
- response_mode nếu client cần chỉ định;
- max_age hoặc acr_values khi có yêu cầu policy và OP hỗ trợ.

Ví dụ minh họa:

~~~http
GET /authorize?
 response_type=code&
 client_id=learning-portal&
 redirect_uri=https%3A%2F%2Fportal.example.edu%2Foidc%2Fcallback&
 scope=openid%20profile&
 state=RANDOM_STATE&
 nonce=RANDOM_NONCE&
 code_challenge=BASE64URL_S256_VALUE&
 code_challenge_method=S256
Host: id.example.edu
~~~

Thực tế URL phải được encode đúng và gửi tới authorization endpoint đã xác minh. Không đưa secret, PKCE verifier hoặc access token vào authorization URL.

## 11. Browser redirect và front channel

Authorization request/response đi qua browser nên được gọi là front channel. Browser điều hướng giữa các origin và có thể làm lộ URL qua:
- browser history;
- reverse proxy/access log;
- analytics;
- Referer header;
- screenshot hoặc browser extension;
- hệ thống quan sát URL;
- copy/paste hoặc support capture.

Authorization code là credential ngắn hạn, dùng một lần và gắn với client/redirect URI/PKCE. Tuy vậy, không nên để code tồn tại lâu trong URL hoặc log.

Biện pháp:
- callback chỉ chứa dữ liệu tối thiểu;
- không đưa access token hoặc refresh token vào URL;
- không tải analytics/script bên thứ ba trước khi callback được xử lý và URL được làm sạch;
- dùng Referrer-Policy phù hợp, ví dụ no-referrer trên callback;
- redaction query string ở ingress/application logs;
- sau khi xử lý callback, redirect sang URL sạch nội bộ;
- code có lifetime ngắn và one-time use.

## 12. Callback endpoint xử lý như thế nào?

Callback là trust boundary quan trọng. Backend cần xử lý theo trình tự có kiểm soát:

1. Chọn đúng issuer/OP transaction đã khởi tạo.
2. Kiểm tra callback method và response mode được mong đợi.
3. Đọc state và tìm transaction tương ứng.
4. Xác minh transaction chưa hết hạn, chưa được dùng và gắn với browser/session.
5. Nếu response chứa error, xử lý theo transaction và hiển thị thông báo an toàn.
6. Nếu có code, kiểm tra code không rỗng và thực hiện token exchange server-to-server.
7. Gửi đúng client authentication, redirect_uri và PKCE verifier.
8. Xác minh token response và ID Token.
9. Kiểm tra nonce và các claim bắt buộc.
10. Ánh xạ issuer + subject tới account nội bộ theo policy.
11. Kiểm tra account active, tenant và login policy.
12. Tạo session ID mới và xóa/consume transaction.
13. Redirect browser tới return path nội bộ đã được kiểm tra.

Không tạo session chỉ vì callback có code hoặc state. Nếu bất kỳ kiểm tra quan trọng nào thất bại, từ chối và ghi audit reason code.

## 13. Đổi authorization code tại token endpoint

Backend gửi code tới token endpoint qua TLS. Với confidential web client, backend thường xác thực client bằng phương thức đã đăng ký, ví dụ private_key_jwt, client secret hoặc mTLS. Nó cũng gửi:
- grant_type=authorization_code;
- code nhận được;
- redirect_uri tương ứng;
- code_verifier;
- client authentication theo cấu hình.

Token endpoint kiểm tra code:
- được phát hành cho đúng client;
- chưa hết hạn;
- chưa được sử dụng;
- gắn với redirect URI;
- gắn với PKCE challenge;
- thỏa client authentication nếu client cần xác thực.

Code là one-time credential. Nếu token exchange timeout, client không nên giả định code vẫn có thể đổi lại thành công; cần xử lý trạng thái không xác định theo giao thức và bắt đầu flow mới nếu code đã bị consume.

## 14. Xác minh ID Token sau redirect

RP phải xác minh ID Token theo OIDC, tối thiểu:
- chữ ký bằng key của issuer tin cậy;
- issuer (iss) đúng OP đã chọn;
- audience (aud) chứa client_id;
- azp nếu áp dụng theo quy tắc multi-audience;
- exp chưa hết hạn;
- iat hợp lý;
- nonce khớp transaction;
- auth_time nếu RP đã yêu cầu max_age hoặc policy freshness;
- các claim bổ sung theo policy.

Không chỉ decode JWT. Không tải JWKS từ URL tùy ý do token header cung cấp. Discovery/JWKS phải gắn với issuer đã được cấu hình và xác minh. ID Token xác nhận authentication cho client; không dùng nó thay Access Token để gọi API.

## 15. Issuer binding và mix-up attack

Nếu một RP hỗ trợ nhiều OP, callback cần được gắn với đúng issuer đã chọn khi login bắt đầu. Nếu không, attacker có thể gây nhầm lẫn khiến RP gửi code hoặc token tới nhầm token endpoint.

Phòng vệ:
- lưu issuer/OP trong transaction server-side;
- dùng redirect URI riêng cho từng issuer khi phù hợp;
- kiểm tra issuer identifier trong authorization response nếu profile hỗ trợ;
- xác minh iss trong ID Token;
- chỉ đổi code tại token endpoint của issuer đã chọn;
- không suy issuer từ dữ liệu callback không được xác minh;
- kiểm tra audience và client binding.

Đây là một dạng authorization server mix-up. RP cần ràng buộc cả authorization response lẫn token response với đúng OP. Không chọn token endpoint bằng URL do browser callback tự gửi.

## 16. Open redirect và redirect chaining

Open redirect xảy ra khi một endpoint chấp nhận URL đích do người dùng/attacker kiểm soát rồi chuyển hướng browser tới đó. Trong login flow, open redirect có thể:
- đưa code hoặc error về domain attacker;
- làm người dùng tin rằng họ đang ở website hợp lệ;
- tạo chuỗi redirect vượt qua kiểm tra callback;
- làm rò token hoặc dữ liệu trong URL;
- hỗ trợ phishing và OAuth authorization response theft.

Phòng vệ:
- chỉ đăng ký redirect URI cố định;
- tránh wildcard và pattern matching rộng;
- không dùng callback chung có tham số next tùy ý;
- nếu cần return path, dùng route nội bộ hoặc allowlist identifier;
- từ chối URL có scheme/host ngoài policy;
- không dùng open redirect trên domain RP trong chuỗi login;
- kiểm thử encoded URL, double encoding, userinfo và hostname suffix.

Ví dụ sai: callback nhận next=https://attacker.invalid rồi redirect sau khi xử lý code. Ví dụ đúng: callback lấy một returnRouteId đã lưu trong transaction và map tới route nội bộ.

## 17. Login CSRF và authorization response injection

Login CSRF xảy ra khi attacker khiến browser nạn nhân đăng nhập vào RP bằng account của attacker hoặc gắn nhầm kết quả xác thực vào session nạn nhân. Điều này có thể làm nạn nhân thao tác trên account không phải của họ hoặc để dữ liệu riêng tư bị gắn sai.

Phòng vệ:
- tạo state ngẫu nhiên cho từng transaction;
- gắn state với browser session đã bắt đầu login;
- consume state một lần;
- dùng nonce và xác minh ID Token;
- dùng PKCE;
- không chấp nhận unsolicited authorization response nếu không hỗ trợ profile tương ứng;
- rotate session ID sau login;
- kiểm tra issuer/client/redirect URI;
- bảo vệ callback khỏi request giả và replay.

State phải được kiểm tra trước khi token exchange. Nếu state không khớp, không tiếp tục xử lý code hoặc tạo session.

## 18. Response mode: query và form_post

OIDC hỗ trợ các response mode khác nhau tùy OP/client:
- **query:** code và state được trả trong query string của callback, thường qua GET;
- **form_post:** browser POST form tới callback, dữ liệu nằm trong form body;
- các mode khác chỉ dùng khi profile và ứng dụng hỗ trợ rõ ràng.

Không dùng fragment để truyền token trong ứng dụng web hiện đại nếu không có lý do và profile an toàn rõ ràng. Browser không gửi fragment tới server theo HTTP request thông thường, nên callback backend không thể xử lý nó như query.

### Cookie SameSite và form_post

Với callback cross-site POST, cookie SameSite=Lax thường không được gửi theo cách giống top-level GET navigation. Nếu callback dựa vào cookie để tìm browser transaction, form_post có thể làm mất correlation cookie.

Cần:
- chọn response mode phù hợp với kiến trúc;
- nếu dùng cookie cross-site, cấu hình SameSite=None; Secure khi thực sự cần và đánh giá CSRF;
- vẫn xác minh state và transaction;
- không hạ CSRF control chỉ để callback hoạt động;
- kiểm thử trên browser mục tiêu và các chính sách cookie thực tế.

SameSite là lớp defense-in-depth, không thay state, nonce hoặc PKCE.

## 19. Session fixation và tạo session sau login

Kẻ tấn công có thể cố làm nạn nhân dùng một session ID mà attacker biết trước. Nếu RP giữ nguyên session ID trước và sau login, attacker có thể chiếm session sau khi nạn nhân xác thực.

Sau khi xác thực thành công:
- tạo session ID mới bằng CSPRNG;
- rotate hoặc invalidate pre-auth session ID;
- chỉ gắn principal sau khi ID Token được xác minh;
- xóa transaction state đã dùng;
- đặt cookie Secure, HttpOnly và SameSite phù hợp;
- áp dụng idle và absolute timeout;
- không đưa session ID vào URL;
- không chia sẻ session cookie qua domain rộng nếu không cần.

Không tạo authenticated session trước khi callback validation và token verification hoàn tất.

## 20. Return path và điều hướng sau login

Ứng dụng thường muốn đưa người dùng về trang họ đang truy cập trước login. Cần lưu return path theo cách không tạo open redirect.

Thiết kế an toàn:
- lưu path tương đối nội bộ trong transaction server-side;
- từ chối scheme, authority hoặc network-path reference bên ngoài;
- canonicalize path bằng URL parser;
- không cho phép encoded slash hoặc double encoding bypass route policy;
- chỉ redirect sau khi session đã được tạo thành công;
- fallback về trang mặc định nếu return path không hợp lệ.

Không lấy return URL từ query parameter không kiểm soát rồi dùng trực tiếp trong Location header. Kiểm tra cả URL encoding và path traversal.

## 21. Error response và timeout

Redirect flow có nhiều điểm có thể lỗi:
- người dùng hủy login;
- OP từ chối hoặc account không đủ policy;
- state sai hoặc hết hạn;
- callback thiếu code;
- token endpoint timeout;
- code đã bị consume;
- ID Token sai issuer/audience/nonce;
- JWKS endpoint không khả dụng;
- session store lỗi.

Cách xử lý:
- hiển thị thông báo người dùng ngắn gọn, không tiết lộ chi tiết verifier;
- ghi reason code nội bộ và correlation ID;
- không retry code exchange vô hạn;
- không tạo session khi kết quả token exchange chưa xác định;
- nếu transaction hết hạn hoặc không thể xác minh, khởi tạo login flow mới;
- không redirect error về URL tùy ý;
- không log code, token, secret hoặc full callback URL.

Nếu token endpoint đã xử lý code nhưng response bị mất, code có thể đã dùng. Bắt đầu transaction mới thường an toàn hơn việc cố replay code cũ.

## 22. Front-channel redirect và back-channel exchange

Hai kênh này có đặc tính khác nhau:

| Kênh | Dữ liệu/hoạt động | Rủi ro và kiểm soát |
| --- | --- | --- |
| Front channel | Browser redirect, authorization request/response, code và state | URL/log/history leakage; exact redirect URI; state; code ngắn hạn |
| Back channel | RP backend đổi code lấy token qua TLS | Client authentication, PKCE verifier, TLS, issuer/token endpoint binding |
| Resource call | RP hoặc backend dùng access token gọi API | Audience, scope, expiry, sender constraint và authorization |
| Logout notification | OP/RP phối hợp kết thúc session | Xác minh logout token/request, issuer, audience, session mapping |

Không gửi access token hoặc refresh token qua front-channel redirect. Token exchange nên diễn ra trực tiếp giữa backend client và token endpoint.

## 23. Reverse proxy và external callback URL

Ứng dụng sau reverse proxy có thể nhận request nội bộ qua HTTP nhưng browser truy cập HTTPS. Nếu app dựng redirect_uri từ Host hoặc X-Forwarded-Proto do client kiểm soát, attacker có thể làm RP gửi callback tới domain giả.

Kiểm soát:
- cấu hình external/public base URL cố định theo môi trường;
- chỉ tin forwarded headers từ proxy đã xác thực;
- proxy xóa forwarded header do client gửi trước khi ghi giá trị của nó;
- allowlist Host ở ingress;
- đăng ký redirect URI chính xác tại OP;
- kiểm tra callback URI trong production/staging;
- không tự thêm host mới vào allowlist khi gặp lỗi redirect.

Redirect URI là cấu hình trust boundary. Không tạo nó từ request header không tin cậy.

## 24. SSO nhiều ứng dụng và IdP

Trong SSO, mỗi RP có client registration, redirect URI, client ID và policy riêng. Người dùng có thể đã có session tại OP, nên lần đăng nhập tiếp theo có thể quay về nhanh mà không nhập password.

Tuy vậy:
- session tại OP khác session tại từng RP;
- logout RP không nhất thiết logout OP;
- một ID Token dành cho client A không được dùng cho client B;
- redirect URI và audience cần tách theo client;
- mỗi RP tự xác minh token và tạo session của mình;
- tenant/issuer mapping phải rõ nếu một RP hỗ trợ nhiều tổ chức.

Không chia sẻ callback hoặc session cookie giữa các ứng dụng chỉ để đơn giản hóa SSO. Dùng giao thức federation và client registration đúng cách.

## 25. SAML HTTP Redirect binding: cùng mô hình điều hướng, giao thức khác

SAML Web SSO cũng có thể dùng browser redirect:
1. Service Provider (SP) tạo AuthnRequest.
2. Browser được chuyển tới Identity Provider.
3. IdP xác thực người dùng.
4. IdP trả SAML Response về Assertion Consumer Service (ACS), thường bằng HTTP POST binding trong nhiều triển khai.
5. SP xác minh chữ ký, issuer, audience, destination, recipient, thời hạn, InResponseTo và replay.
6. SP tạo local session.

SAML Redirect binding có quy tắc encoding/DEFLATE và signature riêng. Không áp dụng quy tắc OIDC state/nonce/PKCE một cách máy móc cho SAML. Hãy dùng thư viện SAML được duy trì và kiểm tra đầy đủ XML signature, canonicalization và assertion conditions.

SAML response/assertion cũng là bằng chứng xác thực; browser chỉ vận chuyển nó. SP không được tin response chỉ vì browser quay về ACS.

## 26. Logging, telemetry và bảo vệ dữ liệu callback

Có thể ghi:
- correlation ID và transaction reference opaque;
- client ID và issuer đã chọn;
- redirect URI identifier/config version;
- response mode;
- kết quả state/nonce/PKCE validation;
- token exchange outcome;
- reason code cho issuer/audience/expiry mismatch;
- session creation result;
- thời gian xử lý và lỗi dependency.

Không log:
- authorization code;
- access token, refresh token hoặc raw ID Token;
- client secret/private key;
- PKCE code_verifier;
- session cookie;
- full callback URL nếu chứa code/state;
- dữ liệu cá nhân không cần thiết.

Callback response nên dùng Referrer-Policy phù hợp, tránh tải script bên thứ ba và làm sạch URL sau khi xử lý. Log redaction cần được cấu hình ở CDN, proxy, APM và application, không chỉ ở một tầng.

## 27. Pseudocode khởi tạo redirect transaction

Ví dụ Java khái niệm:

~~~java
RedirectResponse beginLogin(BrowserRequest request) {
    String state = randomUrlSafeValue(32);
    String nonce = randomUrlSafeValue(32);
    String verifier = pkce.createVerifier();
    String challenge = pkce.s256Challenge(verifier);

    String issuer = issuerPolicy.selectTrustedIssuer(request.tenant());
    String redirectUri = clientConfig.callbackUriFor(issuer);

    LoginTransaction tx = new LoginTransaction(
        state,
        nonce,
        verifier,
        issuer,
        redirectUri,
        browserBinding(request),
        safeInternalReturnPath(request),
        clock.instant().plusSeconds(300));

    transactionStore.save(tx);

    return oidcClient.authorizationRedirect(
        issuer,
        redirectUri,
        state,
        nonce,
        challenge,
        "S256");
}
~~~

Pseudocode chỉ minh họa. Production cần:
- CSPRNG cho state, nonce và verifier;
- transaction storage có expiry và consume-once;
- browser binding an toàn;
- issuer selection từ cấu hình tin cậy;
- redirect URI không được dựng từ Host header;
- chống nhiều transaction đồng thời và session fixation;
- không log verifier hoặc full authorization URL.

## 28. Pseudocode xử lý callback

~~~java
LoginResult handleCallback(BrowserRequest request) {
    String state = request.requireState();
    LoginTransaction tx =
        transactionStore.requirePendingForBrowser(state, request);

    transactionStore.requireNotExpired(tx);
    transactionStore.requireExpectedIssuer(tx);

    if (request.hasAuthorizationError()) {
        transactionStore.consumeOnce(tx.id());
        return LoginResult.failed(genericLoginMessage());
    }

    String code = request.requireAuthorizationCode();

    TokenResponse tokens = oidcClient.exchangeCode(
        tx.issuer(),
        code,
        tx.redirectUri(),
        tx.pkceVerifier());

    VerifiedIdToken idToken =
        idTokenVerifier.verify(tokens.idToken(), tx.issuer(), tx.clientId());

    require(idToken.nonce().equals(tx.nonce()));
    accountPolicy.requireActive(idToken.issuer(), idToken.subject());

    transactionStore.consumeOnce(tx.id());
    BrowserSession newSession =
        sessionService.createNewSession(idToken.principal());

    return LoginResult.authenticated(
        newSession, tx.safeInternalReturnPath());
}
~~~

Đây là pseudocode khái niệm. Cần xử lý race khi hai callback cùng dùng state/code; transaction consume và code exchange phải có semantics rõ. Token exchange timeout có thể tạo ambiguous outcome. Không tạo session trước khi token/ID Token được xác minh đầy đủ.

## 29. Kiểm thử redirect flow

| Ca kiểm thử | Kết quả mong đợi |
| --- | --- |
| Login bình thường | Browser quay lại callback; code đổi token; ID Token được xác minh; session mới được tạo. |
| State thiếu | Callback bị từ chối. |
| State sai | Callback bị từ chối trước token exchange. |
| State đã dùng | Callback replay bị từ chối. |
| State hết hạn | Transaction bị từ chối; yêu cầu login mới. |
| Callback từ browser khác | Browser binding không khớp; từ chối. |
| Nonce trong ID Token sai | RP từ chối ID Token. |
| PKCE verifier sai | Token endpoint từ chối code exchange. |
| PKCE challenge dùng plain ngoài policy | Client/OP configuration test thất bại. |
| Redirect URI không đăng ký | OP từ chối authorization request. |
| Redirect URI khác ở token exchange | Token endpoint từ chối theo contract. |
| Authorization code bị dùng lại | OP từ chối second use. |
| Authorization code hết hạn | Token endpoint từ chối. |
| Issuer response không khớp transaction | RP từ chối và không gửi code tới token endpoint sai. |
| ID Token issuer sai | RP từ chối. |
| ID Token audience sai | RP từ chối. |
| ID Token hết hạn | RP từ chối. |
| ID Token chữ ký sai | RP từ chối. |
| ID Token thiếu nonce khi policy yêu cầu | RP từ chối. |
| Open redirect qua return URL | RP từ chối URL ngoài allowlist. |
| Host/X-Forwarded-Host giả | Không làm thay đổi redirect URI tin cậy. |
| Login CSRF | State/browser binding ngăn response injection. |
| Session fixation | Session ID được rotate sau authentication. |
| form_post callback với SameSite=Lax | Flow không phụ thuộc cookie không được gửi; test phát hiện cấu hình sai. |
| OP timeout trước authorization response | Không tạo session; cho phép retry flow mới. |
| Token endpoint timeout sau code exchange | Không replay mù code; xử lý ambiguous outcome. |
| JWKS key rotation | RP cập nhật key từ issuer đã tin cậy và xác minh token hợp lệ. |
| Callback query logging | Code/state/token được redacted khỏi logs. |
| Browser Back/refresh callback | Callback one-time không tạo session thứ hai. |
| Multi-tab login | Transaction state độc lập, response không bị gắn nhầm. |
| Hai IdP cùng được hỗ trợ | Issuer/client/redirect binding ngăn mix-up. |
| SAML response sai InResponseTo/audience | SP từ chối assertion. |

## 30. Bài tập tình huống

Một cổng học tập hỗ trợ hai IdP: IdP của trường và IdP của đối tác. Cả hai dùng chung callback. Backend nhận state nhưng không lưu transaction server-side; state chỉ được kiểm tra có tồn tại. Sau callback, ứng dụng đổi code bằng token endpoint được lấy từ tham số issuer trong query string. Return URL do browser gửi trong tham số next. Ứng dụng không dùng PKCE và không xác minh nonce trong ID Token.

**Yêu cầu phân tích:**

1. Vì sao kiểm tra state chỉ tồn tại là không đủ?
2. Làm sao gắn callback với browser transaction và đúng IdP?
3. Vì sao không được chọn token endpoint từ query string?
4. Cần dùng PKCE và nonce như thế nào?
5. Cần kiểm tra redirect URI và ID Token claims nào?
6. Return URL có thể tạo open redirect ra sao?
7. Nếu token endpoint timeout sau khi code đã được consume, xử lý thế nào?
8. Làm sao bảo đảm session mới chỉ được tạo sau khi xác minh hoàn tất?

**Hướng phân tích:** Lưu state, nonce, PKCE verifier, issuer, redirect URI, browser binding và return path trong transaction server-side có expiry/one-time use. Chỉ đổi code tại token endpoint của issuer đã chọn từ cấu hình tin cậy. Dùng PKCE S256; xác minh state, nonce, chữ ký, iss, aud, exp và các claim theo policy. Redirect URI exact registered. Return path chỉ là route nội bộ đã kiểm tra. Nếu token exchange có kết quả không xác định, không replay code mù quáng; khởi tạo flow mới theo policy. Rotate session ID và tạo authenticated session sau khi mọi kiểm tra pass.

## 31. Checklist review

- [ ] Redirect chỉ là điều hướng; không được coi là bằng chứng authentication.
- [ ] Dùng OIDC Authorization Code Flow với PKCE S256 cho browser login theo best practice.
- [ ] State ngẫu nhiên, có expiry, one-time và browser/session binding.
- [ ] Nonce được gửi và xác minh trong ID Token.
- [ ] PKCE verifier được giữ server-side và không đi qua front channel.
- [ ] Redirect URI exact registered và nhất quán khi đổi code.
- [ ] Callback gắn với đúng issuer, client và transaction.
- [ ] Token endpoint được lấy từ issuer configuration tin cậy.
- [ ] Authorization code ngắn hạn, one-time và không được log.
- [ ] ID Token được xác minh chữ ký, iss, aud, exp, iat và nonce.
- [ ] ID Token không bị dùng thay Access Token.
- [ ] Open redirect và return URL tùy ý được loại bỏ.
- [ ] Login CSRF, response injection và mix-up được kiểm soát.
- [ ] Response mode và SameSite cookie được kiểm thử trên browser thật.
- [ ] Session ID được rotate sau authentication.
- [ ] Authenticated session chỉ tạo sau token/ID Token validation.
- [ ] Reverse proxy headers không điều khiển public redirect URI.
- [ ] Callback URL/query được redacted; không log code/token/verifier.
- [ ] Front channel chỉ vận chuyển code/state; token exchange ở back channel.
- [ ] Multi-tab, retry, timeout, replay và JWKS rotation có test.
- [ ] SAML nếu dùng được xác minh theo đúng SAML profile, không áp dụng máy móc OIDC rules.

## 32. Ghi nhớ

**Redirect flow đưa browser tới IdP để xác thực rồi quay về RP qua callback đã đăng ký.** Với OIDC Authorization Code Flow, browser mang authorization code và state; backend đổi code tại token endpoint bằng PKCE verifier, xác minh ID Token và nonce, sau đó tạo session mới. Redirect URI, issuer, client, browser transaction và session phải được ràng buộc chặt chẽ.

State, nonce và PKCE có vai trò khác nhau: state liên kết callback với transaction/browser; nonce liên kết ID Token với authentication request; PKCE ràng buộc authorization code với client transaction. Không dùng redirect để chuyển access token, không tin callback chỉ vì có code, và không để open redirect hoặc proxy header quyết định callback đích.

Khi review, hãy hỏi: **Ai khởi tạo transaction? Callback có gắn với đúng browser và issuer không? Redirect URI có được đăng ký chính xác không? State, nonce và PKCE được xác minh riêng ra sao? Token exchange có chạy ở back channel không? ID Token đã được xác minh trước khi tạo session chưa? Return URL có thể đưa người dùng hoặc authorization response sang domain ngoài không?**
