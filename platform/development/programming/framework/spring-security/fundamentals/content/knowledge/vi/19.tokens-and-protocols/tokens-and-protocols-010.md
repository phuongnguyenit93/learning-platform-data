# Thu hồi token, đánh cắp token và ảnh hưởng của cách lưu, cách gửi token

## 1. Tại sao token đúng chữ ký vẫn có thể nguy hiểm?

Một `access token` cho phép client gọi API trong phạm vi được cấp. Nếu đây là **bearer token**, bất kỳ ai có được giá trị token và gửi nó đúng cách tới resource server đều có thể được xem là bên đang sở hữu quyền sử dụng token, trừ khi hệ thống có biện pháp ràng buộc người gửi bổ sung. Token bị đánh cắp có thể được dùng **trước khi hết hạn**, kể cả khi người dùng đã đóng tab hoặc xóa token khỏi trình duyệt.

Ba câu hỏi phải được trả lời riêng:

1. **Token có hợp lệ về mặt mật mã và chính sách không?** Ví dụ JWT có chữ ký đúng, `iss`/`aud` phù hợp, còn trong khoảng `nbf`–`exp` và có `scope` cần thiết.
2. **Token còn được hệ thống cho phép sử dụng không?** Nó có bị thu hồi, vô hiệu do thay đổi quyền hay khóa tài khoản, hoặc nằm trong một phiên/authorization grant đã chấm dứt không?
3. **Ai đang trình token?** Nếu token là bearer thuần túy, server thường không phân biệt được người dùng hợp pháp với kẻ đánh cắp đúng chuỗi token. Sender-constrained token như DPoP/mTLS bổ sung bằng chứng bên gửi đang giữ khóa liên quan, nhưng không loại bỏ mọi dạng tấn công.

**JWT được ký hợp lệ không có nghĩa là “không thể bị thu hồi”.** Điều đúng hơn là: xác minh JWT **hoàn toàn ngoại tuyến** dựa trên chữ ký và claims thì resource server không tự biết việc authorization server vừa thu hồi token, trừ khi được bổ sung một cơ chế tra cứu trạng thái hoặc chính sách khác.

Bài này tập trung vào Spring Security Resource Server, OAuth 2.0/OIDC và các lựa chọn bảo vệ token trên browser, mobile và backend. Một token có thể là JWT hoặc opaque; lựa chọn **định dạng token**, **vị trí lưu**, **cách truyền** và **cách xác minh/thu hồi** là các quyết định liên quan nhưng không đồng nhất.

## 2. Phân biệt các loại token và phiên

| Khái niệm | Dùng để làm gì? | Tính chất khi bị lộ |
| --- | --- | --- |
| **Access token** | Client gọi API của resource server; gắn quyền, audience, hạn dùng | Kẻ có token bearer có thể gọi API trong phạm vi/hạn còn lại |
| **Refresh token** | Client xin access token mới tại authorization server | Nếu bị lộ, có thể duy trì quyền truy cập lâu hơn; cần bảo vệ và rotation hoặc sender constraint |
| **ID token (OIDC)** | Chứng minh một sự kiện đăng nhập cho OIDC client, chứa claims về authentication | Không được tự dùng làm access token cho API khác; RS phải yêu cầu token đúng loại/audience |
| **Session ID/cookie phiên** | Browser trình mã tham chiếu tới trạng thái đăng nhập trên server | Bị chiếm có thể dẫn tới session hijacking; xóa cookie phía client không thay thế việc hủy session server |
| **Authorization code** | Mã tạm thời để client đổi token trong Authorization Code flow | Có cơ chế redirect URI/PKCE, TTL và dùng một lần; không gửi token access qua URL |
| **JWT** | Một *định dạng* token tự mô tả gồm header, claims, signature (JWS) | Chữ ký bảo đảm toàn vẹn và xác nhận nguồn ký, **không mã hóa** nội dung payload; có thể cần kiểm tra trạng thái bổ sung |
| **Opaque/reference token** | Chuỗi token mà client/RS không suy ra claims trực tiếp từ cấu trúc | Thường xác minh qua introspection hoặc kho token của nhà phát hành; dễ phản ánh trạng thái active hơn nhưng cần kết nối/hạ tầng |

`Refresh token` **không nên được resource server chấp nhận để gọi API** chỉ vì nó là một chuỗi token hợp lệ. `ID token` cũng không nên thay thế access token; luôn kiểm tra type, issuer, audience và hợp đồng xác thực.

Các claims phổ biến trong JWT:

- `iss`: bên phát hành đáng tin.
- `aud`: đối tượng dự kiến nhận token; API phải kiểm tra token dành cho chính API đó.
- `sub`: chủ thể mà token đại diện.
- `exp`, `nbf`, `iat`: hết hạn, thời điểm bắt đầu hợp lệ và thời điểm phát hành.
- `jti`: định danh token duy nhất (nếu issuer cung cấp), hữu ích cho thu hồi một token.
- `scope` hoặc `scp`: phạm vi quyền; cách ánh xạ thành Spring Security authorities tùy issuer/cấu hình.
- `cnf`: thông tin ràng buộc khóa với sender-constrained token trong các profile phù hợp.

Không nhầm `iat` với “người dùng vừa nhập mật khẩu”: token có thể được refresh mà không tương ứng với một lần xác thực người dùng mới.

## 3. Token bị đánh cắp theo những đường nào?

**XSS (cross-site scripting).** JavaScript độc hại chạy trong origin có thể đọc token ở `localStorage`, `sessionStorage`, IndexedDB hoặc biến JavaScript mà nó truy cập được. Với cookie `HttpOnly`, script không đọc trực tiếp giá trị cookie bằng `document.cookie`, nhưng vẫn có thể **gửi yêu cầu cùng origin dưới quyền phiên của nạn nhân**. Do đó HttpOnly giảm khả năng trích xuất cookie, không khử sạch tác hại XSS.

**Lộ qua URL.** Token trong query string dễ xuất hiện ở browser history, logs của proxy/CDN, công cụ theo dõi, bookmark, screenshot hoặc header `Referer` tùy chính sách. Token trong fragment có bề mặt lộ khác, nhưng không được coi là cách lưu truyền access token tốt. RFC 9700 khuyến cáo tránh cách cấp token trực tiếp ở authorization response và ưu tiên authorization code với PKCE cho các client phù hợp.

**Lộ từ log/telemetry.** Header `Authorization`, `Cookie`, response body chứa token, URL, crash report hoặc trace của gateway rất dễ lọt vào log tập trung. Cần redaction trước khi ghi; không lưu raw token ở logs hoặc gửi token tới hệ thống analytics bên thứ ba.

**Ứng dụng hoặc thiết bị bị xâm nhập.** Extension trình duyệt độc hại, malware, thiết bị root/jailbreak, backup không mã hóa, file cấu hình chứa token hoặc token lưu trong repository đều có thể làm lộ credential.

**Kênh mạng và chuyển hướng.** Gửi bearer token qua HTTP không mã hóa, redirect sang origin không tin cậy hoặc truyền cho một bên thứ ba là rủi ro nghiêm trọng. Luôn dùng TLS và kiểm soát chặt audience, redirect và outbound requests.

**Refresh token replay.** Kẻ tấn công lấy được refresh token có thể dùng nó để lấy access token mới. Nếu refresh token không bị rotation, không sender-constrained hoặc không có cơ chế kiểm soát replay, ảnh hưởng có thể kéo dài hơn nhiều so với một access token bị mất.

**Lỗi xác minh JWT.** Chấp nhận sai issuer/audience, bỏ qua `exp`, tin thuật toán do attacker chỉ định, nhầm khóa ký hoặc chấp nhận token dành cho dịch vụ khác có thể biến một token “đúng chữ ký ở nơi khác” thành quyền truy cập sai. Spring Security Resource Server cung cấp verifier tiêu chuẩn; đừng tự xử lý JWT chỉ bằng giải mã Base64.

### 3.1. Minh họa hậu quả

~~~text
08:00  Người dùng login, nhận access token (hết hạn lúc 08:15)
08:03  Token bị lộ qua log hoặc XSS
08:05  Người dùng bấm Logout và trình duyệt xóa token
08:07  Kẻ tấn công dùng bản sao token gọi API
08:15  Token hết hạn

Nếu API chỉ xác minh JWT offline, không tra trạng thái thu hồi:
- Bản sao token vẫn có thể hoạt động từ 08:05 đến trước 08:15.
- Logout phía trình duyệt không thể làm cho bản sao này tự biến mất.
Nếu API có kiểm tra thu hồi tức thời, token có thể bị từ chối sớm hơn.
~~~

Thời điểm trong ví dụ chỉ minh họa cửa sổ rủi ro. Một `exp` ngắn giảm thời gian sử dụng lại token bị lộ, nhưng không tự triệt tiêu một vụ tấn công đang diễn ra.

## 4. Lưu token ở đâu? Sự khác nhau về XSS, CSRF và vòng đời

| Nơi lưu | Ai có thể đọc token? | Tác động XSS | Rủi ro CSRF/cách gửi | Nhận xét |
| --- | --- | --- | --- | --- |
| Biến JavaScript trong bộ nhớ | Code JavaScript trong ngữ cảnh ứng dụng | Script độc hại có thể dùng/trích xuất token khi chạy | Nếu client chủ động gắn `Authorization`, browser không tự thêm header vào request chéo nguồn | Ít tồn tại sau refresh/restart; cần cơ chế cấp token lại |
| `sessionStorage` | JavaScript của origin trong tab tương ứng | Có thể bị đọc khi XSS | Không tự gửi token tới server | Đóng tab thường xóa dữ liệu, **không chống XSS** |
| `localStorage` / IndexedDB | JavaScript cùng origin | Dễ trích xuất qua XSS; dữ liệu có thể tồn tại lâu | Không tự gửi token | Không nên lưu authentication tokens, refresh tokens hoặc session IDs ở Web Storage |
| Cookie thông thường (không HttpOnly) | JavaScript có quyền cookie và browser | Có thể bị đọc qua `document.cookie` | Browser tự gắn cookie theo scope/flags nên cần xét CSRF | Không thích hợp để bảo vệ bearer token |
| Cookie `HttpOnly; Secure; SameSite` | Browser gửi theo điều kiện; JavaScript không trực tiếp đọc giá trị | Giảm token exfiltration bằng JS; XSS vẫn có thể thực hiện hành động trong phiên | Cookie được browser tự gắn; phải đánh giá CSRF, origin và semantics của request | Phù hợp giữ session ID cho mô hình server-side/BFF |
| Secure storage của OS cho native app | API hệ điều hành, giới hạn theo app/thiết bị | Không áp dụng XSS browser theo cùng cách; malware/root vẫn là rủi ro | Native client gắn token vào request | Dùng Keychain/Keystore và Authorization Code + PKCE phù hợp |

**Kết luận thiết kế cho browser:** Khi có backend đáng tin cậy, mô hình **Backend-for-Frontend (BFF)** thường giúp giảm mức phơi bày OAuth tokens: backend cất access/refresh token ở phía server; browser chỉ mang **cookie phiên HttpOnly, Secure, SameSite** đến backend. Mã JavaScript không cần đọc refresh token. Phải bảo vệ session cookie, CSRF và backend khỏi XSS/session riding.

Không tồn tại cách lưu token nào “chống tất cả”:

- `HttpOnly` không ngăn kẻ tấn công có XSS gửi POST/GET hợp lệ trong cùng origin.
- `SameSite` giảm nhiều hình thức gửi cookie từ site khác, nhưng không thay thế đầy đủ thiết kế CSRF; cân nhắc same-site subdomain, trình duyệt cũ và các luồng redirect.
- `Secure` yêu cầu truyền cookie qua HTTPS trong triển khai thực tế; không bảo vệ nếu chính server bị chiếm quyền.
- `localStorage` dễ lập trình nhưng chuyển rủi ro thành khả năng JavaScript đọc và giữ token lâu.
- Bộ nhớ JavaScript chỉ giảm persistence; khi XSS đang chạy trong phiên, attacker vẫn có thể gọi API hoặc chặn token.
- `CORS` giới hạn khả năng đọc/gửi một số request từ trang khác qua browser; **CORS không phải authorization** và không thay thế xác thực, CSRF hay kiểm tra quyền.

Nếu lưu cookie phiên, cân nhắc tiền tố `__Host-` (cùng `Secure`, `Path=/`, không có `Domain`), `HttpOnly`, `SameSite=Lax` hoặc `Strict` phù hợp, rotation session ID sau login và timeout server. Phải cân nhắc OAuth redirect, domain hợp lệ và tương thích cross-site khi chọn SameSite.

## 5. Gửi token như thế nào? Header, cookie, query và body

### 5.1. Authorization: Bearer – phù hợp API dùng header

~~~http
GET /api/orders HTTP/1.1
Host: api.example.org
Authorization: Bearer <access-token>
Accept: application/json
~~~

Client chủ động gắn header `Authorization`. Đây là cách phổ biến cho OAuth 2.0 bearer token. Luôn dùng TLS; phía server cần kiểm tra token và quyền cho từng endpoint. Ở browser, JavaScript cần có cách truy cập token hoặc gửi request thông qua BFF.

Các trình duyệt không tự lấy token ở `localStorage` và gửi thành header `Authorization`. Vì thế API **chỉ** chấp nhận custom bearer header do JS chủ động gắn thường ít chịu kiểu CSRF cổ điển dựa vào cookie tự động gửi. Tuy nhiên, một XSS trong origin vẫn có thể lấy token hoặc gọi API. Nếu cùng API còn chấp nhận cookie, Basic Auth hoặc cơ chế credential tự động khác thì đánh giá CSRF phải bao gồm tất cả đường xác thực.

### 5.2. Cookie – tự gửi theo scope/flags

~~~http
GET /account HTTP/1.1
Host: app.example.org
Cookie: __Host-session=<opaque-session-id>
~~~

Cookie thường chứa **session ID** tham chiếu server, không cần chứa JWT. Nếu trực tiếp đặt access token trong cookie, cookie đó vẫn là bearer credential; bị gửi tự động, nên CSRF trở thành mối quan tâm. Với BFF, backend dùng session ID để tra trạng thái và lấy OAuth access token phía server, sau đó gọi API downstream bằng header bearer.

Cookie `HttpOnly` không phải một header bảo mật mà resource server có thể tin để biết đã xác thực: cần xác minh session/token ở server, gắn với đúng account, TTL, trạng thái revoke và quyền.

### 5.3. URL query / fragment – tránh gửi credential qua địa chỉ

~~~http
GET /api/orders?access_token=<token> HTTP/1.1
Host: api.example.org
~~~

Dù bearer token specification có mô tả một số phương thức truyền, đặt token trong URL là lựa chọn rất dễ rò qua logs/history/tracing; không làm theo cho ứng dụng hiện đại. Không truyền **refresh token** ở query hay redirect URL.

### 5.4. Body, redirect và gRPC

OAuth token endpoint có thể nhận một số credential hoặc authorization code bằng POST form body qua TLS theo giao thức; điều đó **khác** với việc gửi bearer access token vào JSON body của mọi API tự định nghĩa. Với gRPC hoặc protocol khác, token thường đi qua metadata có semantic tương tự `Authorization`; nguyên tắc TLS, lọc log, audience và revoke giữ nguyên.

**Bảng quyết định nhanh:**

| Client/kiến trúc | Cách thường phù hợp | Điều phải bảo vệ |
| --- | --- | --- |
| SPA + BFF | Browser cookie phiên HttpOnly; BFF giữ OAuth tokens ở backend | CSRF, cookie scope, session store, XSS/session riding |
| SPA gọi API trực tiếp | Authorization Code + PKCE; access token ngắn hạn, giữ trong memory theo thiết kế | XSS, token refresh, CORS, revoke, PKCE; tránh Web Storage cho credentials |
| Mobile/native | Authorization Code + PKCE, lưu credential trong OS secure storage, bearer header | Deep link/app link, OS storage, refresh rotation, device theft |
| Server-to-server | Client Credentials + mTLS/private key hoặc secret phù hợp; Authorization header | Client secret/keys, scope, audience, rotation và logging |
| Browser form-login truyền thống | Server session ID bằng cookie | Session fixation, CSRF, XSS, timeout, invalidation |

## 6. Thu hồi token nghĩa là gì?

**Revocation** là quyết định của hệ thống rằng một credential hoặc authorization grant **không còn được chấp nhận**, dù trước đó còn hạn. Tác động thực sự phụ thuộc vào việc thành phần kiểm tra token có biết và thực thi quyết định đó hay không.

Cần tách bốn thao tác:

1. **Client xóa token:** không sử dụng lại trong chính client đó. Bản sao bị đánh cắp vẫn tồn tại.
2. **Authorization server thu hồi refresh token:** ngăn refresh token đó cấp access token mới theo chính sách của AS. Access token đã phát có thể vẫn còn hiệu lực đến hết hạn.
3. **Resource server từ chối access token:** thực hiện qua introspection, denylist, allowlist, phiên bản tài khoản/session, hoặc chính sách trực tuyến khác. Đây là bước thực sự chặn access token đã phát trước hạn.
4. **Thu hồi session/cấp quyền rộng hơn:** kết thúc phiên browser, authorization grant, toàn bộ thiết bị hoặc phiên người dùng theo chính sách; cần phát tán trạng thái tới các service liên quan.

### 6.1. RFC 7009 – OAuth 2.0 Token Revocation

RFC 7009 định nghĩa endpoint để client yêu cầu authorization server thu hồi access/refresh token. Ví dụ giao thức:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: idp.example.org
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-authentication>

token=<url-encoded-token>&token_type_hint=refresh_token
~~~

`token_type_hint` là gợi ý; tên endpoint do AS quy định, không nhất thiết là `/oauth2/revoke`. Client phải xác thực với AS khi chính sách/giao thức yêu cầu, truyền token trong body qua TLS và tránh ghi token vào log. RFC 7009 yêu cầu AS hỗ trợ thu hồi refresh token; hỗ trợ thu hồi access token được khuyến nghị nhưng khả năng thực tế phải kiểm tra ở từng provider.

Một phản hồi **HTTP 200** thường được dùng cho cả token đã thu hồi thành công **và token vốn không hợp lệ/không tồn tại**, để hạn chế dò đoán token. HTTP 200 không đồng nghĩa tất cả resource server đã biết ngay quyết định thu hồi. Tùy loại token và hệ thống phân tán, có độ trễ truyền trạng thái.

### 6.2. RFC 7662 – Token Introspection

Resource server gửi token tới introspection endpoint của AS (thường qua kết nối được xác thực). AS trả metadata với `active`:

~~~json
{
  "active": true,
  "sub": "user-123",
  "scope": "orders:read",
  "exp": 1893456000
}
~~~

Sau khi bị revoke/hết hạn, AS có thể trả:

~~~json
{
  "active": false
}
~~~

`active=false` có nghĩa resource server phải từ chối token. Introspection thường được áp dụng cho opaque/reference token nhưng **cũng có thể dùng để kiểm tra JWT** nếu AS hỗ trợ. Ưu điểm là AS có thể phản ánh quyết định thu hồi; chi phí là network call, xác thực giữa RS–AS, tính sẵn sàng và hiệu năng. Nếu RS cache kết quả `active=true` trong 60 giây, việc revoke có thể chưa có hiệu lực ở RS cho đến khi cache hết hạn. Đừng tuyên bố “revoke tức thì” nếu có cache hoặc nhiều tầng truyền trạng thái.

Cần định nghĩa timeout, retry hợp lý, circuit breaker và **fail closed** cho endpoint nhạy cảm khi không xác minh được token; không vì introspection chậm mà tự chuyển sang “tin token”.

## 7. Các chiến lược thu hồi access token

| Chiến lược | Thế mạnh | Hạn chế | Trường hợp phù hợp |
| --- | --- | --- | --- |
| **Access token TTL ngắn** | Ít phụ thuộc state; giảm thời gian token bị lộ còn dùng được | Không chặn được ngay token đã phát | JWT offline, API tốc độ cao |
| **Opaque token + introspection** | AS quyết định trạng thái `active` cho mỗi lần kiểm tra | Thêm network/hạ tầng; cache làm tăng độ trễ thu hồi | Cần revoke nhanh và quản trị trung tâm |
| **JWT + denylist** | Giữ claims JWT, có thể từ chối trước `exp` | RS phải tra kho state; phải dọn TTL, đồng bộ nhiều node | Muốn revoke token cụ thể nhưng vẫn dùng JWT |
| **JWT + allowlist** | Chỉ token được AS/RS cho phép mới dùng | Kho trạng thái lớn hơn, phụ thuộc availability | Kiểm soát token chặt, tài nguyên nhạy cảm |
| **Token/session version hoặc issued-after** | Có thể chặn hàng loạt token theo user/device | Kiểm tra state; thay đổi user-level có thể chặn nhiều phiên vô ý | Đổi mật khẩu, mất thiết bị, sự cố tài khoản |
| **Sender-constrained access token** | Giảm replay nếu attacker chỉ đánh cắp chuỗi token | Không thay thế revoke; cần quản lý khóa và xác minh proof | Bảo vệ API giá trị cao, native/backends phù hợp |
| **Signing-key rotation** | Loại bỏ token ký bởi khóa bị loại bỏ trong sự cố nghiêm trọng | Ảnh hưởng diện rộng nếu retire khóa cũ quá sớm | Ứng phó lộ khóa ký; rotation thường kỳ có overlap |

### 7.1. TTL ngắn và cửa sổ rủi ro

Giả sử token sống 10 phút và bị lấy sau phút thứ ba; nếu không có revoke tức thời, attacker có thể còn gần 7 phút sử dụng. Chọn TTL dựa trên rủi ro, chi phí phát token, lưu lượng và trải nghiệm. **TTL ngắn chỉ hiệu quả khi kiểm tra `exp` đúng**, đồng hồ server được đồng bộ và không có clock skew quá lớn.

### 7.2. Denylist JWT dựa trên jti

Khi phát JWT, issuer nên bảo đảm `jti` đủ duy nhất trong phạm vi issuer. Khi phát hiện token bị đánh cắp, hệ thống ghi dấu “đã thu hồi” vào kho tra cứu mà mọi resource server đều dùng:

- Key có thể là (`iss`, `jti`), tránh collision giữa nhiều issuer; hoặc **hash mã hóa của token đầy đủ** nếu không có `jti` đáng tin. Không cần lưu bản gốc bearer token để đánh dấu thu hồi.
- Giá trị TTL của denylist tồn tại **ít nhất đến khi token không thể còn hợp lệ** theo thời gian `exp` và clock skew áp dụng. Không cần giữ denylist vĩnh viễn cho token đã hết hạn.
- Mọi request phải xác minh chữ ký, các claims bắt buộc, quyền truy cập **và** trạng thái thu hồi. Không chỉ kiểm tra denylist rồi bỏ qua verifier JWT.
- Kho denylist phải chia sẻ giữa các instance, xử lý mất kết nối, TTL, atomic update và khả năng bị xóa đột ngột. Trong sự cố lớn, cân nhắc lưu bền hoặc truyền sự kiện tin cậy.
- Không dựa vào `jti` do client tùy ý khai báo; giá trị phải đến từ JWT đã được xác minh với issuer hợp lệ.

Một API chỉ kiểm tra `jti` ở endpoint login hoặc gateway mà các đường vào nội bộ khác bỏ qua thì không đáp ứng mục tiêu revoke.

### 7.3. Thay đổi version/epoch để hủy nhiều phiên

Issuer có thể thêm `token_version`, `session_id` hoặc `auth_time` theo hợp đồng riêng. Resource server so sánh với trạng thái hiện hành:

~~~text
Token version (đã ký): 7
Current account token version (database/cache): 8
=> Từ chối token phiên bản 7, dù signature/exp hợp lệ.
~~~

Kỹ thuật này hữu ích khi đổi mật khẩu hoặc khóa toàn bộ phiên, nhưng có trade-off: cần truy vấn trạng thái, cache invalidation và định nghĩa rõ **chặn toàn bộ người dùng hay chỉ một session/thiết bị**. Không gán ý nghĩa bảo mật cho claim mà RS không kiểm tra.

### 7.4. Đổi khóa ký khi bị lộ signing key

Thay khóa ký thường kỳ có thời gian overlap giữa khóa mới/cũ để token hiện hữu hết hạn tự nhiên. Nếu **private signing key bị lộ**, có thể cần retire khóa cũ khẩn cấp và từ chối tất cả token ký bởi khóa đó, đổi JWKs, kiểm tra caching và kích hoạt lại xác thực. Đây là biện pháp ảnh hưởng rộng, không thích hợp để thu hồi một tài khoản bình thường. Đổi khóa dùng để verify JWT cũng **không thu hồi refresh token** đang nằm ở AS trừ khi AS xử lý riêng.

## 8. Refresh token bị đánh cắp: rotation và phát hiện replay

Refresh token có thể cho phép xin access token mới nhiều lần. Vì vậy, một access token TTL 5 phút không có ý nghĩa nhiều nếu attacker giữ refresh token tồn tại dài và vẫn đổi được token mới.

Theo OAuth 2.0 Security Best Current Practice (RFC 9700), nếu phát refresh token cho **public client**, authorization server phải dùng **refresh token rotation** hoặc **sender-constrained refresh tokens** để phát hiện/giảm replay, theo cách mô tả trong tiêu chuẩn.

**Rotation** vận hành như sau:

~~~text
T0: Client có refresh token R1 (đang active)
T1: Client dùng R1 -> AS phát access token A2 + refresh token R2
    AS vô hiệu R1, giữ thông tin quan hệ token family
T2: Một bên gửi R1 lần nữa -> phát hiện reuse của token đã bị rotation
T3: AS vô hiệu token family/refresh token hiện hành theo chính sách
    và buộc người dùng/ứng dụng xác thực lại
~~~

Việc phát hiện reuse **không khẳng định bên nào là attacker**. Nếu cả hai bên đều có token, AS thường không thể biết ai gửi lại R1; hủy token family làm gián đoạn cả client hợp lệ, nhưng chặn attacker tiếp tục lấy token mới.

**Chi tiết triển khai quan trọng:**

- Rotation phải **nguyên tử**. Hai request refresh đồng thời không được vô tình tạo hai nhánh token hợp lệ. Với nhiều tab/browser instance, phối hợp refresh để tránh tự gây “reuse detection”; không cho phép mọi request cùng refresh vô tội vạ.
- Refresh token nên được ràng buộc với client, scope, resource servers và thiết bị/session theo chính sách; cần idle/absolute expiration phù hợp.
- Lưu refresh token ở phía server hoặc secure store; nếu lưu trạng thái ở AS, cân nhắc hash token ngẫu nhiên trước khi lưu thay vì giữ raw token trong database/log.
- Reuse detection chỉ có hiệu quả nếu AS giữ quan hệ token family và thực thi vô hiệu hóa active token sau replay.
- Sender-constrained bằng **mTLS (RFC 8705)** hoặc **DPoP (RFC 9449)** yêu cầu thêm bằng chứng sở hữu khóa khi sử dụng. Nếu chỉ lộ *chuỗi token* mà không có khóa tương ứng, kẻ tấn công khó replay; nhưng malware/XSS đang kiểm soát client có thể vẫn thực hiện hành động ngay trong môi trường bị xâm nhập.

Trong OAuth 2.0, **logout ở client**, **revoke refresh token ở AS** và **chặn access token đang lưu hành ở resource server** là ba hành động cần được lên kế hoạch riêng. Đừng coi một request `/logout` là đủ để giải quyết mọi phiên và token đã bị đánh cắp.

## 9. Spring Security Resource Server: xác minh JWT offline

Ví dụ dưới đây dùng **Java 17+**, **Spring Boot 3.5.0**, Spring Security 6.5.x và **Servlet**. Đây là một ứng dụng API độc lập nhận access token do một **authorization server bên ngoài** phát hành. Ví dụ **không tự phát access/refresh token**, vì resource server không phải issuer theo mặc định.

Cấu trúc ba file:

~~~text
token-api/
├── pom.xml
└── src/main/
    ├── java/example/tokenapi/TokenApiApplication.java
    └── resources/application.yml
~~~

**`pom.xml`**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>token-api</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
    </dependency>
  </dependencies>
</project>
~~~

**`src/main/java/example/tokenapi/TokenApiApplication.java`**:

~~~java
package example.tokenapi;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class TokenApiApplication {
    public static void main(String[] args) {
        SpringApplication.run(TokenApiApplication.class, args);
    }

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/health").permitAll()
                .anyRequest().authenticated())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            // Chỉ dành cho API sử dụng Bearer trong Authorization header;
            // đánh giá CSRF riêng nếu thêm cookie/Basic vào cùng API.
            .csrf(AbstractHttpConfigurer::disable)
            .build();
    }

    @RestController
    static class Endpoints {
        @GetMapping("/health")
        String health() {
            return "ok";
        }

        @GetMapping("/api/me")
        Map<String, String> me(Authentication authentication) {
            return Map.of("subject", authentication.getName());
        }
    }
}
~~~

**`src/main/resources/application.yml`**:

~~~yaml
server:
  port: 8080
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/issuer
          audiences: https://api.example.org
~~~

Hai địa chỉ `idp.example.org` và `api.example.org` là ví dụ; để chạy, **thay bằng issuer thực và audience mà issuer đưa vào access token**. Spring Security dựa trên issuer metadata/JWKs để kiểm tra signature, `iss` và thời hạn; cấu hình `audiences` bổ sung kiểm tra token phải dành cho API này. Ứng dụng cần kết nối được tới metadata/JWKS của issuer. Không chạy độc lập hoàn toàn nếu chưa có AS và token hợp lệ.

Lệnh chạy và quan sát:

~~~bash
mvn spring-boot:run

# Endpoint công khai: HTTP 200, body: ok
curl -i http://localhost:8080/health

# Không có Bearer token: HTTP 401
curl -i http://localhost:8080/api/me

# Với token do issuer thật phát cho đúng audience, chưa hết hạn:
curl -i -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  http://localhost:8080/api/me
~~~

Nếu token hợp lệ, request cuối trả HTTP 200 và JSON dạng `{"subject":"user-123"}`; tên subject phụ thuộc issuer. Chuỗi `YOUR_ACCESS_TOKEN` là ký hiệu thay thế, **không phải** token thật. Token sai chữ ký, hết hạn, sai issuer/audience hoặc thiếu token sẽ bị từ chối theo cấu hình verifier.

**Giới hạn revoke của mẫu này:** nếu authorization server vừa thu hồi một access JWT nhưng resource server chỉ verify offline, JWT đó **có thể vẫn dùng được đến `exp`**. Spring Security không tự gọi introspection và không tự có denylist chỉ vì bạn bật `oauth2ResourceServer(...jwt(...))`.

## 10. Spring Security Resource Server: introspection để kiểm tra trạng thái

Nếu yêu cầu biết nhanh token đã bị revoke, cấu hình resource server để dùng introspection.

Giữ nguyên `pom.xml` và controller trong mục 9; **chỉ thay** dòng JWT của security chain bằng:

~~~java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
~~~

Đồng thời thay phần `spring.security.oauth2.resourceserver.jwt` trong `application.yml` bằng:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.org/oauth2/introspect
          client-id: token-api
          client-secret: YOUR_INTROSPECTION_CLIENT_SECRET
~~~

Lưu secret bằng secret manager hoặc environment/config injection phù hợp; **không commit secret thật vào file**. Địa chỉ endpoint và credentials phải được cấp bởi authorization server.

Spring Security sẽ gửi bearer token tới introspection endpoint và kiểm tra `active`. `active=false` hoặc introspection không xác nhận được token thì request không được xác thực. Nếu AS thực hiện revoke làm `active=false` và RS không dùng cache kết quả cũ, request tiếp theo có thể bị từ chối ngay.

**Lưu ý:** chế độ `opaqueToken()` là **cơ chế xác minh bằng introspection**; nó không bắt buộc token phải có dạng chuỗi ngẫu nhiên. Nếu AS hỗ trợ introspect JWT, RS có thể dùng cấu hình này với **JWT** và vẫn nhận được trạng thái revoke. Chọn cách này để ưu tiên xác nhận trạng thái ở AS, đồng thời đánh giá latency, timeout, availability và cache.

### 10.1. Quyết định tối ưu cho yêu cầu thu hồi

- **JWT offline:** phù hợp hệ phân tán cần xác minh nhanh, chấp nhận cửa sổ rủi ro tối đa bằng TTL ngắn hoặc đã thêm denylist/phiên bản quyền.
- **Introspection:** phù hợp khi cần phản ánh nhanh trạng thái revoke hoặc quyền từ AS, chấp nhận phụ thuộc trực tuyến và có phương án tránh bỏ qua xác minh khi AS lỗi.
- **Kết hợp:** JWT vẫn ký hợp lệ nhưng RS tra denylist, version hoặc introspection cho request nhạy cảm. Phải thống nhất policy giữa mọi service.

Đặt cache trong gateway, microservice hay Spring layer có thể tạo **cửa sổ tiếp tục chấp nhận token đã thu hồi**. TTL cache cần phù hợp RTO revoke; không chỉ quan sát kết quả AS mà bỏ qua cache tại RS.

## 11. Java 17 chạy độc lập: mô phỏng JWT denylist

Ví dụ nhỏ này minh họa quy tắc **expiry + revoke list**. Nó **không** tạo JWT, không xác minh chữ ký, không phải OAuth server và **không được dùng nguyên mã làm token verifier trong production**. Chức năng chính là chỉ ra hai điều kiện riêng biệt phải cùng đúng.

Tạo file **`RevocationWindowDemo.java`**:

~~~java
import java.time.Instant;
import java.util.HashMap;
import java.util.Map;

public class RevocationWindowDemo {
    static boolean mayUse(
            String verifiedJti,
            Instant tokenExpiresAt,
            Instant requestAt,
            Map<String, Instant> revoked) {

        // Giả định chữ ký, issuer, audience, scope đã được kiểm tra.
        return requestAt.isBefore(tokenExpiresAt)
            && !revoked.containsKey(verifiedJti);
    }

    public static void main(String[] args) {
        Instant start = Instant.parse("2026-01-01T00:00:00Z");
        Instant expires = start.plusSeconds(300);
        Map<String, Instant> denylist = new HashMap<>();

        System.out.println(mayUse(
            "issuer-A:jti-42", expires, start.plusSeconds(60), denylist));

        // AS / hệ thống bảo mật nhận yêu cầu revoke sau 90 giây.
        denylist.put("issuer-A:jti-42", expires);

        System.out.println(mayUse(
            "issuer-A:jti-42", expires, start.plusSeconds(120), denylist));

        System.out.println(mayUse(
            "issuer-A:jti-99", expires, start.plusSeconds(301), denylist));
    }
}
~~~

Chạy:

~~~bash
javac RevocationWindowDemo.java
java RevocationWindowDemo
~~~

**stdout chính xác:**

~~~text
true
false
false
~~~

Giải thích:

1. `jti-42` chưa hết hạn và chưa có trong denylist nên được chấp nhận **trong mô hình giả định**.
2. Sau khi denylist ghi nhận token đó, token còn hạn nhưng bị từ chối.
3. `jti-99` không có trong denylist nhưng đã quá `exp` nên cũng bị từ chối.

Mã dùng `Map` cục bộ để mô phỏng; khi triển khai thật, phải tra kho dùng chung (Redis/database...), bảo vệ key (kết hợp issuer + jti hoặc fingerprint), dọn record theo exp và chính sách clock skew, xử lý race, fail-closed và chi phí mỗi request. Đặc biệt, **đừng tự tin cậy `verifiedJti` lấy từ request**: nó phải được rút ra **sau khi Spring Security đã xác minh JWT**.

### 11.1. Tích hợp vào Spring Security ở đâu?

Với JWT, Spring Security cung cấp `JwtDecoder`, `NimbusJwtDecoder`, `OAuth2TokenValidator<Jwt>` và `DelegatingOAuth2TokenValidator` để ghép kiểm tra issuer/expiry/audience với chính sách thu hồi. Một validator có thể tra kho revoke theo (`iss`, `jti`) **sau khi chữ ký được giải mã/xác minh**, rồi trả lỗi `invalid_token` nếu đã bị revoke. Điều quan trọng là giữ **các validator tiêu chuẩn** khi thêm validator revoke; nếu bạn thay thế toàn bộ validator mà không giữ issuer/expiry, bạn có thể vô tình giảm mức bảo vệ.

Khi dùng opaque token, Spring Security hỗ trợ `OpaqueTokenIntrospector`; thông thường nên để AS trả `active` đúng thay vì tự xây một danh sách chặn thứ hai không đồng bộ.

Các quy tắc đều phải được thực thi trong **request authentication/authorization pipeline**, không chỉ trong trang logout hay phần JavaScript. Ghi nhận các trường hợp high-value action có chính sách bổ sung nếu cần.

## 12. Logout và phản ứng khi nghi ngờ token đã bị đánh cắp

Một thao tác “đăng xuất” đáng tin cần định nghĩa rõ phạm vi: **tab hiện tại**, **thiết bị hiện tại**, **tất cả thiết bị**, **authorization grant của ứng dụng**, hay **tài khoản bị khóa**.

### 12.1. Khi người dùng chủ động logout

1. Client ngừng sử dụng access token và xóa credential đang giữ.
2. Nếu có server session, vô hiệu hóa session ở backend và xóa cookie qua `Set-Cookie` tương ứng.
3. Với OAuth/OIDC client, cân nhắc revoke refresh token tại AS theo RFC 7009, hoặc kết thúc grant/session theo API của IdP khi hỗ trợ.
4. Nếu chính sách yêu cầu access token không dùng được trước `exp`, bổ sung revoke/denylist/introspection; không chỉ xóa dữ liệu client.
5. Đồng bộ thông tin tới các resource server nếu chúng dùng cache/kiểm tra state; xác nhận thời gian đến khi từ chối token cũ.

Không được hứa “Logout everywhere = tất cả JWT cũ lập tức không dùng được” nếu kiến trúc chỉ có JWT offline + TTL 15 phút. Phải mô tả trung thực cửa sổ token cũ còn hiệu lực.

### 12.2. Khi phát hiện token bị lộ

Phản ứng ưu tiên:

- Xác định loại credential bị lộ: access token, refresh token, session cookie, signing key, client secret hay cả kho dữ liệu.
- Thu hồi refresh token hoặc toàn bộ token family và những session/authorization grant liên quan; đánh giá việc block access token đang lưu hành.
- Với lộ signing key, thực hiện quy trình đổi/retire khóa khẩn cấp và ngăn verifier chấp nhận token mới giả mạo bằng khóa cũ.
- Sửa nguyên nhân gốc: XSS, log leak, URL leak, insecure storage, không xác minh audience/issuer, kênh truyền không TLS, thiết bị bị chiếm.
- Xem log có redaction để xác định hành động bất thường, thời điểm token sử dụng, user/issuer/audience liên quan; tránh tái lộ token trong quá trình điều tra.
- Thông báo cho chủ tài khoản, bắt buộc xác thực lại hoặc vô hiệu hóa phiên theo mức rủi ro; kiểm tra các thay đổi dữ liệu nhạy cảm.

**Số lượng token bị lộ và khả năng thu hồi** quyết định phạm vi ứng phó. Thu hồi một `jti` khác với vô hiệu hóa khóa ký dùng chung cho hàng triệu token.

## 13. Các lỗi triển khai thường gặp

**Lỗi 1: “JWT có chữ ký nên không thể bị thu hồi.”** Có thể chặn bằng denylist, introspection, allowlist, version/epoch hoặc thay khóa khi cần. Đổi lại, hệ thống phải duy trì state hay chấp nhận phụ thuộc trực tuyến.

**Lỗi 2: “Đã revoke refresh token thì access token cũ chết ngay.”** Access token tự chứa claims đã phát không tự biết refresh token vừa bị thu hồi. Cần chính sách từ chối ở resource server hoặc chờ access token hết hạn.

**Lỗi 3: “Xóa localStorage rồi thì attacker mất token.”** Bản sao đã bị lấy ra khỏi browser vẫn có giá trị cho tới khi bị từ chối ở RS hoặc hết hạn.

**Lỗi 4: “Đặt access token vào cookie HttpOnly là hết XSS và CSRF.”** XSS vẫn có thể chạy authenticated request; cookie tự gửi có thể tạo CSRF. Cần chống XSS, CSRF, session security và authorization tại server.

**Lỗi 5: “sessionStorage không bị XSS.”** JavaScript cùng origin có thể đọc dữ liệu. Chỉ có khác biệt về lifecycle/persistence so với localStorage.

**Lỗi 6: “CORS đã bật là API an toàn.”** CORS không thay xác thực/quyền; native/curl và attacker đã có token vẫn gọi được API. CORS cũng không giải quyết XSS ở origin hợp lệ.

**Lỗi 7: “Gửi JWT qua URL vẫn an toàn nếu HTTPS.”** HTTPS mã hóa đường truyền, nhưng query có thể đi vào logs, history và các hệ thống giám sát.

**Lỗi 8: “Introspection luôn revoke tức thời.”** Cache ở AS/RS/gateway và đồng bộ phân tán có thể tạo độ trễ. Cần đo thời gian thực tế tới khi `active=false` được mọi resource server áp dụng.

**Lỗi 9: “Chỉ kiểm tra signature và exp là đủ.”** Phải kiểm tra issuer, audience, algorithm/key, thời hạn, scope, quyền trên tài nguyên và trạng thái revoke nếu chính sách yêu cầu.

**Lỗi 10: “Refresh token rotation chỉ cần tạo chuỗi R2 mới.”** Phải vô hiệu R1, lưu quan hệ token family, phát hiện replay và xử lý cạnh tranh/đua request.

**Lỗi 11: “Đặt blacklist trong memory từng node là đủ.”** Request tới node khác có thể được chấp nhận. Dùng kho chung hoặc phương thức nhất quán theo kiến trúc.

**Lỗi 12: “Thay đổi signing key để logout một thiết bị.”** Đây là can thiệp diện rộng, có thể vô hiệu hóa nhiều người dùng. Dùng revoke theo token/session khi phù hợp.

**Lỗi 13: “Resource server chấp nhận ID token là bearer access token.”** ID token có audience/dự định sử dụng khác; không dùng ID token để gọi API trừ khi profile chuyên biệt quy định rõ.

**Lỗi 14: “Tắt CSRF vì dùng JWT.”** Cách browser **gửi credential** mới quyết định nguy cơ classic CSRF. JWT trong cookie tự gửi vẫn cần phòng chống CSRF; API chỉ nhận header bearer do client chủ động gắn có đánh giá khác.

## 14. Checklist thiết kế và kiểm thử

**Trước khi triển khai:**

1. Xác định client: browser/BFF, native, server-side hay service account. Ai giữ access/refresh token? Có tồn tại bản sao nào?
2. Chỉ định **access token format**, issuer, audience, scope, `exp`, `jti` và cơ chế verifier; tách rõ ID token/refresh token.
3. Đặt mục tiêu **thời gian thu hồi tối đa**. Nếu cần “vài giây”, JWT offline TTL dài không đáp ứng nếu thiếu state checking.
4. Chọn access revoke: introspection, denylist, version hoặc TTL ngắn; tính cache, multi-node và fail-closed.
5. Xác định chính sách refresh: rotation/sender binding, reuse detection, idle/absolute TTL, token family.
6. Chọn kênh gửi: TLS, Authorization header/BFF cookie, không query/fragment; cấu hình CSRF/CORS phù hợp.
7. Áp dụng logging redaction, secret storage, alerting, rate limit và audit bảo mật.

**Kiểm thử thực tế:**

| Thử nghiệm | Kết quả kỳ vọng |
| --- | --- |
| Không có access token | `401 Unauthorized` ở endpoint yêu cầu authentication |
| Access token sai chữ ký/issuer/audience hoặc hết hạn | Bị từ chối |
| Token hợp lệ nhưng không đủ scope/quyền | `403 Forbidden` hoặc từ chối theo policy |
| Token opaque bị revoke, RS introspect và `active=false` | Bị từ chối ở request tiếp theo không bị cache cũ |
| JWT offline bị revoke ở AS nhưng chưa hết hạn | Có thể còn được chấp nhận: đây là giới hạn cần ghi nhận |
| JWT + denylist, jti đã bị đánh dấu | Bị từ chối trên **mọi** instance |
| Refresh token R1 đã rotation, sau đó bị reuse | AS phát hiện replay theo policy và xử lý token family |
| Client logout nhưng gửi lại bản sao token bị đánh cắp | Phải đáp ứng đúng chính sách đã cam kết, không mặc định an toàn |
| Cookie thiếu CSRF token trên request thay đổi dữ liệu | Bị chặn nếu đang dùng cookie-based auth |
| API dùng Authorization bearer nhưng browser gặp XSS | Phải được kiểm tra tác động token theft/session riding, không kết luận chỉ nhờ CORS |
| AS introspection chậm hoặc mất kết nối | RS không tự chấp nhận token không xác minh được |
| Token không có audience hợp lệ | Không được phép dùng tại resource server khác |

Khi đo tính hiệu quả của revoke, ghi lại thời gian `T_revoke` tại AS và `T_first_reject` ở **từng** RS, đồng thời nêu rõ cache TTL và clock skew. Cửa sổ thực tế là độ trễ đến khi mọi đường vào API từ chối token, không chỉ lúc API revoke trả HTTP 200.

## 15. Câu hỏi tự kiểm tra

**Q1.** Người dùng logout và xóa token trong browser. Kẻ tấn công đang giữ bản sao JWT còn 4 phút hạn dùng. Có bị chặn ngay không?  
**A:** Không chắc. Nếu RS chỉ xác minh chữ ký/claims offline, JWT có thể vẫn hoạt động tới `exp`. Cần revoke enforcement ở RS để chặn trước hạn.

**Q2.** JWT có phải lúc nào cũng stateless không?  
**A:** Việc tự verify JWT có thể stateless; thêm denylist/version/introspection tạo phụ thuộc vào state. JWT là định dạng, không phải lời bảo đảm kiến trúc sẽ hoàn toàn stateless.

**Q3.** Vì sao không nên lưu refresh token trong localStorage?  
**A:** JavaScript cùng origin có thể đọc, nên XSS có thể lấy được token có khả năng duy trì truy cập lâu. Ưu tiên BFF/server-side hoặc secure storage phù hợp client.

**Q4.** Cookie `HttpOnly` có loại bỏ XSS không?  
**A:** Không. Nó ngăn JavaScript đọc trực tiếp cookie, nhưng XSS vẫn có thể gửi request được xác thực trong origin và thực hiện hành động.

**Q5.** Khác nhau cơ bản giữa revoke refresh token và revoke access token?  
**A:** Refresh revoke chặn việc lấy token mới; access revoke cần khiến resource server từ chối token đã phát. Hai thao tác có thể cần cơ chế khác nhau.

**Q6.** Vì sao introspection có thể không phản ánh revoke tức thì?  
**A:** Cache, độ trễ phân tán, chính sách backend và mạng có thể khiến RS vẫn dùng kết quả trước đó.

**Q7.** Password + browser token đặt trong cookie có làm API chống CSRF không?  
**A:** Không tự động. Browser có thể tự gửi cookie theo scope; cần CSRF defense cho thao tác thay đổi dữ liệu.

**Q8.** Refresh token rotation và sender-constrained tokens giảm rủi ro gì?  
**A:** Rotation giúp phát hiện reuse của refresh token; sender constraint khiến token bị lấy riêng lẻ khó replay từ một sender khác nếu không có private key/bằng chứng tương ứng.

## 16. Tài liệu chính thức

- [OAuth 2.0 Security Best Current Practice – RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html): refresh token rotation, replay prevention, sender-constrained access tokens và bảo vệ OAuth hiện đại.
- [OAuth 2.0 Token Revocation – RFC 7009](https://www.rfc-editor.org/rfc/rfc7009.html): semantics của token revocation endpoint.
- [OAuth 2.0 Token Introspection – RFC 7662](https://www.rfc-editor.org/rfc/rfc7662.html): `active` và metadata khi resource server kiểm tra với AS.
- [OAuth 2.0 Bearer Token Usage – RFC 6750](https://www.rfc-editor.org/rfc/rfc6750.html): cách gửi bearer token và rủi ro của bearer usage.
- [OAuth 2.0 Demonstrating Proof of Possession (DPoP) – RFC 9449](https://www.rfc-editor.org/rfc/rfc9449.html): sender constraint cho token.
- [Spring Security – OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): cấu hình JWT verification, issuer, audience và validators.
- [Spring Security – OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection, custom introspector và hành vi revoke.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session storage, cookies và bảo vệ phiên.
- [OWASP HTML5 Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html): rủi ro token trong Web Storage.
- [OWASP Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html): CSRF với browser credentials.
