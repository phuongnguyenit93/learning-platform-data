# Authorization header

## 1. Authorization header trong vòng đời token

Trong chương **Token transport** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, bài học này trả lời câu hỏi: **sau khi client nhận access token hợp lệ, client phải trình token đến API như thế nào để hạn chế lộ credential và để resource server xác minh đúng quyền?**

Với OAuth 2.0 bearer access token, client thường gửi credential trong HTTP **Authorization header** qua HTTPS:

~~~http
GET /api/orders/order-721 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
~~~

Trong khi đó, cách sau **không nên dùng**:

~~~http
GET /api/orders/order-721?access_token=<ACCESS_TOKEN> HTTP/1.1
Host: orders.example.com
~~~

URL dễ xuất hiện ở access log, reverse proxy, lịch sử trình duyệt, bookmark, liên kết được chia sẻ và hệ thống analytics. HTTPS bảo vệ nội dung trên đường truyền giữa các điểm TLS nhưng **không ngăn proxy hoặc server sau khi giải mã TLS ghi lại URL**.

**Nguyên tắc:** đối với OAuth bearer access token, ưu tiên `Authorization: Bearer <token>` qua HTTPS; không đặt token vào query, path, fragment hoặc link. Tuy nhiên, **header vẫn chứa secret**, nên phải bảo vệ nơi lưu token, logging, redirect và forwarding.

### Mục tiêu học tập

Người học cần:

1. Hiểu cấu trúc Authorization header, auth-scheme và credential.
2. Phân biệt Bearer, Basic, DPoP, Proxy-Authorization và cookie phiên.
3. Hiểu xác minh JWT/opaque token, issuer, audience, scope, thời gian và quyền trên resource.
4. Gửi Authorization đúng qua browser, backend, Spring Security, proxy và CORS.
5. Xử lý HTTP 401, 403 và WWW-Authenticate đúng ngữ nghĩa.
6. Nhận diện token leakage, header injection, sai parser, duplicate headers và replay.

## 2. Cú pháp HTTP Authorization

HTTP Semantics (RFC 9110) mô tả trường Authorization mang thông tin xác thực gửi đến **origin server**:

~~~http
Authorization: <auth-scheme> <credentials>
~~~

Các ví dụ **độc lập**, không phải ba header gửi cùng một request:

~~~http
Authorization: Bearer <OAUTH_ACCESS_TOKEN>
Authorization: Basic <BASE64_ENCODED_CLIENT_CREDENTIALS>
Authorization: DPoP <DPOP_BOUND_ACCESS_TOKEN>
~~~

**Auth-scheme** cho biết cách kiểm tra credential. Phần credential không có cùng ngữ nghĩa ở mọi scheme. Không thể xem chuỗi sau dấu hai chấm như một JWT chung rồi thử giải mã.

### 2.1. Bearer scheme của OAuth 2.0

Với RFC 6750, Bearer được trình theo mẫu:

~~~http
Authorization: Bearer <ACCESS_TOKEN>
~~~

Bearer token có tính chất: **bên chiếm hữu chuỗi token có thể trình token** trong phạm vi, thời gian và các điều kiện còn hợp lệ, trừ khi có ràng buộc bổ sung. Access token có thể là:

- **JWT access token:** có thể xác minh cục bộ bằng chữ ký và các claims đã được kiểm tra.
- **Opaque access token:** không cần cấu trúc đọc được ở phía client; resource server thường dùng token introspection hoặc cơ chế tin cậy đã thỏa thuận.

Tên cú pháp `b64token` trong RFC 6750 **không bắt buộc mọi bearer token phải là một chuỗi Base64 có payload cần decode**. Một JWT thường chứa dấu chấm, nhưng **chuỗi có ba phần cũng chưa tự chứng minh là token JWT hợp lệ**.

### 2.2. Chữ hoa, chữ thường và khoảng trắng

| Thành phần | Nguyên tắc |
|---|---|
| Tên field `Authorization` | Không phân biệt chữ hoa/chữ thường theo HTTP |
| Auth-scheme `Bearer` | Không phân biệt chữ hoa/chữ thường |
| **Giá trị access token** | Phải giữ nguyên; không chuyển chữ hoa/chữ thường tùy tiện |
| Khoảng trắng | Client phát dạng chuẩn có dấu cách giữa scheme và credential; server dùng parser đúng grammar |
| Nhiều credential hoặc header trùng | Không tự hợp nhất hay chọn một credential tùy ý |

Ví dụ sai:

~~~javascript
// SAI: làm hỏng giá trị token dù tên scheme không phân biệt hoa/thường.
const normalized = authorizationHeader.toLowerCase();
~~~

Không tự xóa dấu chấm trong token, không URL-decode nhiều lần hoặc dùng parser chỉ dựa vào tách chuỗi ở dấu cách đầu tiên.

### 2.3. Authorization và Proxy-Authorization

~~~http
Authorization: Bearer <API_ACCESS_TOKEN>
Proxy-Authorization: Basic <PROXY_CREDENTIALS>
~~~

`Authorization` hướng đến **origin/resource server**. `Proxy-Authorization` dùng để xác thực với HTTP proxy khi giao thức yêu cầu. Không gửi token dành cho Orders API trong Proxy-Authorization hoặc dùng credential proxy thay access token.

## 3. Luồng từ Authorization Server đến Resource Server

~~~mermaid
sequenceDiagram
    actor U as Alice
    participant C as Client
    participant AS as Authorization Server
    participant RS as Orders API
    U->>C: Muốn xem đơn hàng
    C->>AS: OAuth authorization/token flow
    AS->>AS: Xác thực grant, client và chính sách cấp quyền
    AS-->>C: Access token cho Orders API
    C->>RS: Authorization: Bearer token
    RS->>RS: Xác minh token, issuer, audience, scope
    RS->>RS: Kiểm tra quyền Alice với order-721
    alt Được phép
        RS-->>C: 200, dữ liệu được phép
    else Token thiếu hoặc không hợp lệ
        RS-->>C: 401 và Bearer challenge
    else Quyền không đủ
        RS-->>C: 403 hoặc 404 theo chính sách
    end
~~~

**Authorization Server** phát hành token, **client** giữ và trình token, **resource server** kiểm tra credential rồi ra quyết định quyền trên resource/action cụ thể. Header Authorization là **kênh chuyên chở**, không tự định nghĩa principal được đọc đối tượng nào.

### 3.1. Ví dụ claims của JWT access token

~~~json
{
  "iss": "https://login.example.com",
  "sub": "alice-123",
  "aud": ["https://orders.example.com"],
  "client_id": "shop-web",
  "scope": "orders:read",
  "iat": 1893492000,
  "nbf": 1893492000,
  "exp": 1893492900,
  "jti": "example-at-73"
}
~~~

Đây chỉ là **payload minh họa**, không phải JWT có chữ ký. Resource server cần:

1. Xác minh chữ ký JWT bằng khóa/thuật toán đáng tin cậy, hoặc kiểm tra opaque token qua introspection.
2. So khớp `iss`, `aud`, token type/profile với hệ thống hiện tại.
3. Kiểm tra `exp`, `nbf`, các điều kiện `iat` và TTL theo profile.
4. Kiểm tra scope/permission phù hợp với action.
5. Kiểm tra principal, tenant, ownership hoặc relation với resource cụ thể.
6. Kiểm tra trạng thái/revocation nếu kiến trúc yêu cầu.

**Không tin claims chỉ vì decode được payload JWT.** Token của Inventory API không tự hợp lệ tại Orders API dù cùng issuer.

### 3.2. Scope không tự chứng minh quyền với object

~~~text
Access token:
    sub = alice-123
    aud = https://orders.example.com
    scope = orders:read

GET /api/orders/order-999

order-999 thuộc Bob và không được chia sẻ cho Alice.
=> DENY theo resource authorization, dù bearer token hoàn toàn hợp lệ.
~~~

Lỗi bỏ kiểm tra đối tượng có thể dẫn đến **BOLA/IDOR**. Cách vận chuyển đúng credential không thể sửa một policy sai.

## 4. Basic ở token endpoint khác Bearer tại resource server

### 4.1. Confidential client dùng Basic để xin access token

Một confidential client có thể xác thực với Authorization Server qua HTTP Basic theo OAuth 2.0:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Authorization: Basic <ENCODED_CLIENT_ID_AND_CLIENT_SECRET>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=inventory%3Aread
~~~

Giá trị Basic chỉ là placeholder. **Base64 là encoding, không phải mã hóa**, vì thế client secret phải được giữ trong kho bí mật của backend và truyền qua TLS. Authorization Server cần xác thực client, kiểm tra grant type, scope và resource/audience trước khi cấp token.

Sau khi nhận access token dành cho Inventory API, client gọi API:

~~~http
GET /api/inventory/items HTTP/1.1
Host: inventory.example.com
Authorization: Bearer <ACCESS_TOKEN_FOR_INVENTORY>
~~~

**Client secret** dùng để xác thực client tại token endpoint; **access token** dùng để gọi resource server. Việc cả hai có thể xuất hiện trong HTTP Authorization header không khiến chúng có cùng mục đích.

### 4.2. Refresh token nằm ở token endpoint

Một refresh token thông thường được gửi đến **token endpoint** trong POST body của OAuth 2.0:

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.com
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<REFRESH_TOKEN>&client_id=shop-web
~~~

Đây là **request public client minh họa**. Confidential client phải xác thực đúng phương thức đã đăng ký. Authorization Server phải kiểm tra refresh token thuộc đúng client/grant, còn hạn, chưa thu hồi, scope không vượt grant và cơ chế rotation hoặc sender constraint khi thích hợp.

Không dùng refresh token làm credential của Orders API:

~~~http
GET /api/orders/order-721 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <REFRESH_TOKEN>
~~~

Orders API phải từ chối token sai loại/mục đích. Refresh token bị lộ có thể cho phép xin access token mới trong vòng đời grant, vì thế thường cần bảo vệ nghiêm ngặt hơn.

### 4.3. ID token cũng không thay access token

OIDC **ID token** dành cho client xác minh kết quả đăng nhập và thường có audience là client. Một ID token có chữ ký đúng cũng **không phải** bearer access token được cấp cho Orders API. Resource server phải kiểm tra token type/profile và audience, không chỉ chữ ký.

## 5. Vì sao Authorization header được ưu tiên hơn URL hoặc body?

RFC 6750 mô tả việc trình bearer token bằng Authorization header, form-encoded body trong điều kiện hạn chế và URI query parameter vì lý do tương thích. **Header là cách ưu tiên**; truyền bearer access token trong query không được khuyến nghị và cần tránh ở thiết kế hiện đại.

| Vị trí | Ví dụ | Đánh giá |
|---|---|---|
| **Authorization header** | Bearer access token | **Ưu tiên** qua HTTPS |
| **Query string** | Query parameter tên access_token | **Không dùng** vì dễ rò qua URL |
| **Path** | Path chứa giá trị token | **Không dùng**, path thường được log |
| **Fragment** | Dấu # rồi access token | Không gửi tới server qua HTTP nhưng browser/JS có thể thấy |
| **Form body** | access_token là tham số form | RFC 6750 mô tả tương thích có giới hạn; không khuyến khích thay header |
| **Cookie/session** | Session cookie | Cơ chế session khác với Bearer header; cần chống CSRF |

### 5.1. URL bị ghi lại ở đâu?

~~~text
https://orders.example.com/api/orders/721?access_token=<SECRET>
https://orders.example.com/api/token/<SECRET>/orders
~~~

Các chuỗi trên có thể xuất hiện trong:

- Reverse proxy, CDN, WAF, API gateway và web server access log.
- Browser history, bookmark, ảnh chụp màn hình và URL được sao chép.
- Công cụ APM, error reporting, analytics và distributed tracing.
- Ticket hỗ trợ, chat, phần mềm preview link và shell history.
- Một số trường hợp Referer tùy origin, chính sách và trình duyệt.

**HTTPS không chặn hệ thống terminate TLS đọc URL và ghi log.** Mọi tầng quan sát cần được bảo vệ, nhưng việc đầu tiên phải làm là không gửi access token trong URL.

### 5.2. Fragment và Referer: phân biệt kỹ thuật

~~~text
https://app.example.com/callback#access_token=<SECRET>
~~~

Browser thông thường **không gửi fragment trong HTTP request** và fragment cũng không nằm trong Referer header theo quy tắc HTTP. Tuy nhiên, JavaScript, history, bookmark, ảnh chụp màn hình và các SDK thu thập URL vẫn có thể tiếp cận fragment.

Một số luồng OAuth cũ từng đặt access token trong fragment. Ứng dụng hiện đại nên ưu tiên **Authorization Code + PKCE** thay vì thiết kế mới dựa trên implicit flow.

Với Referer, nhiều trình duyệt hiện đại dùng chính sách tương tự **strict-origin-when-cross-origin**, nên cross-origin request thường chỉ mang origin. Không nên nói mọi click đều chuyển toàn bộ query. **Dù vậy, referrer policy không loại bỏ rủi ro từ log, history, bookmark và link-sharing.**

### 5.3. Không trình nhiều token bằng nhiều cách cùng lúc

~~~http
GET /api/orders/order-721?access_token=<TOKEN_B> HTTP/1.1
Host: orders.example.com
Authorization: Bearer <TOKEN_A>
~~~

RFC 6750 yêu cầu client không dùng nhiều phương thức trình bearer token trong cùng một request. Nếu server tự chọn token A hoặc B, có thể phát sinh credential confusion. API nên công bố một đường nhận credential rõ ràng và không fallback sang query khi thiếu header.

## 6. Parser Authorization header phải nghiêm ngặt

### 6.1. Bảng hành vi gợi ý

| Request | Cách xử lý |
|---|---|
| Không có Authorization | 401/challenge khi endpoint yêu cầu bearer |
| Bearer token đúng cú pháp | Chuyển sang token validation |
| Header chỉ có Bearer, thiếu token | Từ chối |
| Basic ở endpoint chỉ chấp nhận Bearer | Không lấy Basic làm bearer token |
| Credential malformed | Từ chối; không tự sửa |
| Hai Authorization headers với các giá trị khác nhau | Từ chối mơ hồ; không tự gộp và chọn |
| Nhiều scheme hoặc token phân tách bằng dấu phẩy | Không nhận như một bearer credential |
| Header có kích thước quá lớn | Giới hạn ở gateway/server |
| JWT có cấu trúc đúng nhưng chữ ký sai | Từ chối ở bước validation |

Tên header có thể được mã hóa dạng chữ thường trong HTTP/2, HTTP/3. Điều đó không làm thay đổi ý nghĩa Bearer, nhưng **giá trị token vẫn phải giữ nguyên chính xác**.

### 6.2. Tránh split chuỗi thủ công

~~~java
// SAI: dễ lỗi với null, thiếu token, scheme sai hoặc header mơ hồ.
String token = request.getHeader("Authorization").split(" ")[1];
~~~

Một parser tự viết đơn giản còn có thể bỏ qua duplicate headers, khoảng trắng, token quá dài và giá trị không đúng grammar. **Nên dùng resolver của framework đã được kiểm thử** thay vì xử lý thủ công.

### 6.3. Hệ thống có nhiều proxy

~~~text
Client
  |
  | Authorization: Bearer <TOKEN>
  v
CDN / WAF / API Gateway
  |
  | Header forwarding theo policy
  v
Ingress / Reverse Proxy
  |
  | Header và identity context đã bảo vệ
  v
Orders API
~~~

Không tự tin header **X-User-Id**, **X-Tenant-Id**, **X-Role** hoặc **X-Forwarded-Authorization** do caller internet gửi. Nếu gateway chuyển identity context vào nội bộ, cần xóa giá trị giả mạo từ client, bảo vệ tính toàn vẹn và ngăn API bị truy cập bypass gateway.

## 7. HTTP 401, 403 và WWW-Authenticate

**WWW-Authenticate** là HTTP response header mô tả challenge. Với OAuth bearer:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders"
Cache-Control: no-store
~~~

Nếu access token được trình nhưng không hợp lệ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders", error="invalid_token"
~~~

Nếu token hợp lệ nhưng scope không đủ:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders", error="insufficient_scope", scope="orders:write"
~~~

### 7.1. Phân biệt lỗi

| Tình huống | Kết quả thông dụng |
|---|---|
| Không có credential ở endpoint bảo vệ | **401** cùng challenge thích hợp |
| Token hết hạn, sai chữ ký, sai issuer/audience, opaque inactive | **401**, invalid_token khi phù hợp |
| Header sai cấu trúc, dùng nhiều phương thức mâu thuẫn | **400** hoặc invalid_request theo contract |
| Token có hiệu lực nhưng thiếu scope | **403**, insufficient_scope khi phù hợp |
| Token đủ scope nhưng không có quyền với object | **403**, hoặc **404** nếu policy cần che tồn tại |
| Vượt hạn mức request | **429** theo rate limiting |

Tên HTTP **401 Unauthorized** mang tính lịch sử, trên thực tế thường liên quan đến yêu cầu credential hợp lệ. Không dùng **WWW-Authenticate: Basic** nếu API chỉ hỗ trợ Bearer, vì browser có thể hiển thị hộp thoại Basic ngoài ý muốn.

Không phản chiếu raw token, client secret hoặc metadata nhạy cảm vào error_description, body hay log. **401 và 403 đều không được biến thành đường dò thông tin tài nguyên của tenant khác.**

## 8. Browser Fetch và CORS khi gửi Authorization

Browser JavaScript có thể gọi resource server bằng Fetch API và thêm Bearer header:

~~~javascript
async function loadOrder(accessToken, orderId) {
  const baseUrl = "https://orders.example.com";
  const url = baseUrl + "/api/orders/" + encodeURIComponent(orderId);

  const response = await fetch(url, {
    method: "GET",
    headers: {
      Authorization: "Bearer " + accessToken,
      Accept: "application/json"
    },
    redirect: "error"
  });

  if (response.status === 401) {
    throw new Error("Token không hợp lệ hoặc đã hết hạn");
  }
  if (response.status === 403) {
    throw new Error("Không có quyền với đơn hàng này");
  }
  if (!response.ok) {
    throw new Error("Không thể đọc đơn hàng");
  }
  return response.json();
}
~~~

Đoạn code tập trung vào **cách truyền credential**. Access token phải đến từ luồng OAuth hợp lệ và được lưu theo kiến trúc client; việc cấp token, refresh và xử lý redirect không trình bày trong ví dụ này.

**Không gắn token vào request đến origin tùy ý.** Interceptor hoặc wrapper HTTP chỉ nên dùng token với resource server đúng audience/allowlist. Việc một input có vẻ là URL hợp lệ không chứng minh đó là điểm nhận token đáng tin cậy.

### 8.1. Preflight OPTIONS của CORS

Authorization không phải một CORS-safelisted request header. Với cross-origin Fetch có header Authorization, browser thường gửi **OPTIONS preflight**:

~~~http
OPTIONS /api/orders/order-721 HTTP/1.1
Host: orders.example.com
Origin: https://shop.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Nếu origin, method và header được cho phép:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://shop.example.com
Access-Control-Allow-Methods: GET
Access-Control-Allow-Headers: Authorization
Vary: Origin
~~~

**Preflight thông thường không mang bearer access token.** Nếu gateway yêu cầu mọi OPTIONS đều có Authorization mới cho qua, browser có thể không gửi được request chính. Cần xử lý preflight theo origin/route phù hợp, nhưng **vẫn bắt buộc xác thực request GET/POST thật**.

### 8.2. CORS không phải authentication

CORS chủ yếu điều chỉnh việc JavaScript trong browser có được đọc response cross-origin hay không. Client HTTP ngoài browser không bị CORS chặn. Dù origin shop.example.com nằm trong allowlist, resource server vẫn phải xác minh token và quyền resource/action.

Khi request còn mang cookie hoặc session credential, cần quy định **Access-Control-Allow-Credentials**, origin cụ thể và thuộc tính cookie theo threat model. Không xem một Origin header hợp lệ là bằng chứng quyền.

### 8.3. Redirect có thể làm lộ credential

Giả sử HTTP client dùng Bearer token gọi:

~~~text
GET https://orders.example.com/api/orders/721
Authorization: Bearer <ORDERS_TOKEN>

302 Location: https://other.example.net/collect
~~~

Browser và các HTTP library khác nhau có quy tắc giữ/bỏ Authorization khi redirect, đặc biệt giữa các origin. **Không giả định mọi client luôn loại bỏ hoặc luôn giữ header**. Với request nhạy cảm, nên giới hạn redirect, kiểm tra destination và bảo đảm không chuyển token đến origin ngoài allowlist.

Không gửi access token trong response Location hoặc một link URL khác để giải quyết vấn đề client không thêm được header.

## 9. BFF, session và các trường hợp browser không thêm header trực tiếp

### 9.1. Backend-for-Frontend

Trong ứng dụng web có backend, kiến trúc **BFF** có thể giữ OAuth access/refresh token phía server, còn browser dùng session cookie bảo vệ để gọi BFF:

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Browser
    participant F as Backend-for-Frontend
    participant AS as Authorization Server
    participant API as Orders API
    U->>B: Xem đơn hàng
    B->>F: Request bằng session cookie
    F->>F: Kiểm tra session và CSRF khi áp dụng
    opt Cần lấy hoặc làm mới access token
        F->>AS: OAuth token request đúng grant
        AS-->>F: Access token đúng audience
    end
    F->>API: Authorization: Bearer <ACCESS_TOKEN>
    API->>API: Validate token và resource authorization
    API-->>F: Dữ liệu được phép
    F-->>B: Business response không chứa OAuth token
~~~

Cookie phiên cần cấu hình **Secure**, **HttpOnly**, **SameSite** và phạm vi domain/path phù hợp. BFF vẫn phải chống CSRF, session fixation và XSS gây hành động bằng session. `HttpOnly` ngăn JavaScript trực tiếp đọc cookie nhưng **không tự ngăn script độc hại gửi request dưới phiên hiện có**.

### 9.2. Download file và hình ảnh

Thẻ HTML anchor/image thường không cho lập trình viên tùy ý thêm Authorization header giống Fetch API. Không nên giải quyết bằng cách đưa access token vào URL:

~~~javascript
// SAI: tạo URL chứa bearer token.
window.open("/api/reports/monthly.pdf?access_token=" + accessToken);
~~~

Các cách tiếp cận:

1. **Fetch với Authorization:** nhận response Blob, tạo object URL của dữ liệu được phép tải. Blob URL không chứa trực tiếp bearer token, nhưng dữ liệu vẫn cần bảo vệ.
2. **BFF/session cookie:** browser mở URL cùng origin, BFF xác thực phiên và kiểm tra quyền rồi gọi service/storage bằng token phía server.
3. **Pre-signed URL hạn chế:** nếu storage cần link trực tiếp, cấp capability sau khi xác thực quyền, gắn với một tài nguyên, action cụ thể và thời hạn ngắn.

**Pre-signed URL cũng là một loại secret mang quyền trong URL**; nó có rủi ro log, share, preview, history và cần bảo vệ. Nó khác với việc đưa **OAuth access token nhiều quyền** vào query. Không xem sự tồn tại của pre-signed URLs là lý do chấp nhận bearer token trong URL.

### 9.3. SSE và WebSocket

Browser EventSource và WebSocket không cho thêm mọi HTTP header tùy ý theo cùng cách như Fetch. Những lựa chọn cần đánh giá:

- BFF/session cùng origin và chính sách origin/CSRF phù hợp.
- Streaming qua Fetch API nếu client/server hỗ trợ.
- Connection ticket dùng một lần, TTL ngắn, ràng buộc đúng channel/client, chống log và replay.

Không dùng refresh token hoặc access token dài hạn trong WebSocket/SSE URL. Kết nối đã được xác thực vẫn cần authorization trên message/channel và giới hạn tenant phù hợp.

## 10. Java/Spring Security: nhận bearer từ Authorization header

Với Spring Security OAuth2 Resource Server, một **BearerTokenResolver** có thể lấy token đúng transport. Ví dụ cấu hình Servlet cho JWT access token:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OrdersApiSecurity {

    @Bean
    BearerTokenResolver bearerTokenResolver() {
        DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
        resolver.setAllowUriQueryParameter(false);
        resolver.setAllowFormEncodedBodyParameter(false);
        return resolver;
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            BearerTokenResolver bearerTokenResolver) throws Exception {

        http.authorizeHttpRequests(registry -> registry
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth -> oauth
                .bearerTokenResolver(bearerTokenResolver)
                .jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Đây là ví dụ theo phong cách Spring Security hiện đại, **không phải cấu hình production đầy đủ**. Cần dependencies, cấu hình issuer/JWKS, JWT audience validator, CORS, phương án logout/revocation và method security theo phiên bản/hệ thống đang dùng. Với opaque token, cấu hình introspection thay cho JWT.

### 10.1. Không nhận access token qua URI query

Hai phương thức:

~~~java
resolver.setAllowUriQueryParameter(false);
resolver.setAllowFormEncodedBodyParameter(false);
~~~

đảm bảo resolver không lấy token từ query hoặc form body. Đây cũng là hành vi mặc định thường gặp của DefaultBearerTokenResolver; ghi rõ giúp bảo vệ hợp đồng khi cấu hình thay đổi.

Không bật **setAllowUriQueryParameter(true)** chỉ để chiều theo một client cũ gửi token sai vị trí. Nên sửa client, áp BFF hoặc dùng một cơ chế capability riêng nếu trường hợp tải file thực sự cần.

**Lưu ý:** Spring từ chối query token không có nghĩa proxy phía trước chưa log URI. Phải sửa từ phía client và kiểm tra các tầng nhận request trước Spring.

### 10.2. Scope authority không thay quyền object

Với scope được converter map thành granted authority dạng **SCOPE_orders:read**, một endpoint có thể chặn sơ bộ:

~~~java
// Pseudocode: cần bật method security, converter phù hợp.
@PreAuthorize("hasAuthority('SCOPE_orders:read')")
@GetMapping("/api/orders/{id}")
public OrderDto getOrder(
        @PathVariable String id,
        Authentication authentication) {

    VerifiedPrincipal caller =
        principalFactory.fromVerifiedAuthentication(authentication);
    return orderService.readAuthorized(caller, id);
}
~~~

**VerifiedPrincipal**, **principalFactory** và **readAuthorized** là thành phần do ứng dụng định nghĩa, không phải API Spring có sẵn. Service vẫn phải kiểm tra owner, tenant, quan hệ chia sẻ và trạng thái của order ID cụ thể.

Việc chỉ đặt issuer-uri trong resource server **không bảo đảm mọi audience nghiệp vụ đã được xác minh theo mọi cấu hình/phiên bản**. API phải quy định rõ expected audience và cấu hình validator thích hợp.

### 10.3. Java client gửi đúng bearer header

Trong Spring Framework có hỗ trợ RestClient:

~~~java
// baseUrl cố định, đúng resource server đã được cấp trong aud.
RestClient ordersClient = RestClient.builder()
    .baseUrl("https://orders.example.com")
    .build();

OrderDto order = ordersClient.get()
    .uri("/api/orders/{id}", orderId)
    .headers(h -> h.setBearerAuth(accessToken))
    .retrieve()
    .body(OrderDto.class);
~~~

Header được thư viện tạo ở đúng vị trí. Trong ứng dụng thật còn cần TLS validation, timeout, retry và chính sách redirect; không tái sử dụng token Orders API ở RestClient dùng cho arbitrary URL.

## 11. DPoP và mTLS: Authorization không phải lúc nào cũng là Bearer thuần

### 11.1. DPoP-bound access token

Với **DPoP (RFC 9449)**, client có thể trình access token ràng buộc khóa kèm một proof JWT:

~~~http
GET /api/orders/order-721 HTTP/1.1
Host: orders.example.com
Authorization: DPoP <DPOP_BOUND_ACCESS_TOKEN>
DPoP: <SIGNED_DPOP_PROOF_JWT>
~~~

**Authorization: DPoP** không đồng nghĩa **Authorization: Bearer**. Resource server phải kiểm tra access token, token-to-key binding và DPoP proof theo profile, gồm chữ ký proof, **htm**, **htu**, **iat**, **jti**, **ath** và nonce khi áp dụng.

Chỉ nhìn thấy DPoP header mà không xác minh proof không tạo sender constraint. DPoP proof không thay access token và cũng không thay authorization theo resource/action.

### 11.2. mTLS certificate-bound token

Một access token được ràng buộc với chứng chỉ theo RFC 8705 có thể vẫn được gửi theo **Bearer scheme**, nhưng resource server còn phải kiểm tra chứng chỉ client và token binding:

~~~text
HTTPS + mutual TLS
Authorization: Bearer <CERTIFICATE_BOUND_ACCESS_TOKEN>

Resource Server:
    validate token
    verify client certificate
    verify token-to-certificate binding
~~~

**TLS thông thường không tự ràng buộc token với khóa riêng của client.** Sender constraint chỉ có giá trị khi server thực thi đúng quan hệ giữa token và credential của bên gửi.

### 11.3. Header không ngăn token replay tự thân

Authorization header giảm những đường rò URL, nhưng bearer access token bị đánh cắp vẫn có thể bị dùng lại khi còn hạn. Các lớp bổ sung gồm:

- Access token có scope/audience tối thiểu, TTL phù hợp.
- Refresh token rotation và phát hiện reuse khi thích hợp.
- Revocation, token introspection, session version hoặc denylist theo threat model.
- DPoP/mTLS sender constraint khi client và RS hỗ trợ.
- Bảo vệ token storage, phòng chống XSS, không ghi raw credential vào log.

Claim **jti** trong JWT chỉ là định danh; **không tự ngăn replay** nếu không có cơ chế kiểm tra trạng thái/nonce phù hợp.

## 12. Reverse proxy, redirect và bảo vệ log

### 12.1. Authorization qua nhiều lớp hạ tầng

Một request thường đi qua CDN, Web Application Firewall, API Gateway hoặc reverse proxy trước khi vào API. Mỗi hop cần có hợp đồng rõ:

1. HTTPS được dùng trên biên mạng; nếu TLS kết thúc ở proxy, đường kết nối nội bộ và quyền truy cập cũng cần được bảo vệ.
2. Header Authorization được forward **đúng resource server**, hoặc gateway chuyển identity context đã xác minh thông qua kênh đáng tin theo kiến trúc.
3. Header người dùng tự đưa như X-User-Id, X-Tenant-Id hoặc X-Authenticated-User không được tự coi là principal đã xác thực.
4. Không để client gọi trực tiếp backend và bỏ qua gateway/PEP cần thiết.
5. Hạ tầng không ghi raw Authorization ở access log, error log, debug log, trace hoặc APM.

Nếu API Gateway xác minh JWT rồi chuyển danh tính tới service downstream, service đó phải biết **ai được quyền phát hành identity context**, làm sao xác thực nguồn và tính toàn vẹn, cũng như cách bảo vệ ranh giới tenant. Một request đến từ mạng nội bộ không tự đáng tin.

### 12.2. Logging cần phân biệt route template với URI thô

Ví dụ log có thể vô tình chứa:

~~~text
GET /api/orders/721?access_token=<SECRET> HTTP/1.1
Authorization: Bearer <SECRET>
~~~

Để quan sát vận hành, có thể ưu tiên metadata:

~~~text
traceId
routeTemplate=/api/orders/{id}
httpMethod=GET
clientId
issuerId
principalType
audienceId
authorizationDecision=ALLOW|DENY
denialReasonCategory
responseStatus
~~~

**Không ghi giá trị bearer token, refresh token, ID token, client secret, API key, DPoP private key hoặc cookie phiên**. Ngay cả principal ID, client ID, scope, IP và jti cũng có thể là dữ liệu cá nhân hoặc nhạy cảm, cần được xử lý theo chính sách truy cập và lưu giữ.

Nếu một API từ chối token ở query nhưng proxy đã ghi request URI trước khi chuyển tiếp, vẫn có thể đã xảy ra rò rỉ. Phải sửa client và kiểm tra **toàn bộ các hệ thống đã lưu URL/header**, không chỉ application logger.

### 12.3. Cache-Control với tài nguyên riêng tư

Một request dùng Bearer header có thể trả dữ liệu của người dùng hoặc tenant cụ thể. Thiết kế cache cần xem xét:

- Dữ liệu được phép lưu trong browser cache hay không.
- CDN/shared cache có thể lưu hoặc tái sử dụng response giữa hai principal hay không.
- Cache key có phản ánh tenant, principal và dữ liệu quyền nếu thực sự cần caching không.
- Khi nào dùng **Cache-Control: private** hoặc **no-store** cho dữ liệu nhạy cảm.
- Khi quyền bị thu hồi hoặc resource thay đổi, dữ liệu cũ còn được phục vụ từ cache không.

Không suy rằng mọi shared cache luôn được cấu hình an toàn chỉ vì request chứa Authorization header. Cần kiểm tra HTTP caching semantics và cấu hình cụ thể.

### 12.4. Header injection và giới hạn độ dài

Authorization header là dữ liệu do caller gửi. Hệ thống cần:

- Giới hạn kích thước header/request ở gateway và application server.
- Từ chối giá trị có định dạng không hợp lệ và credential trùng/mơ hồ.
- Không nhúng nguyên giá trị header vào response hoặc structured log mà không redaction.
- Không dùng chuỗi token làm tên file, query SQL hoặc shell command.
- Không cho phép một service nội bộ tự thay Authorization header của caller bằng token có quyền rộng mà không kiểm tra delegation.

Khi gateway thay bearer credential bằng service token ở downstream, phải giữ được bối cảnh và quyền caller hoặc dùng token exchange/on-behalf-of phù hợp. Nếu không, service có thể trở thành **confused deputy**.

## 13. Ma trận kiểm thử Authorization header

### 13.1. Header parsing và token validation

| Kịch bản | Kỳ vọng |
|---|---|
| Bearer access token hợp lệ qua HTTPS | Tiếp tục authorization theo resource/action |
| Không có Authorization ở API cần bảo vệ | 401 và Bearer challenge phù hợp |
| Header chỉ có Bearer, không có credential | Từ chối |
| Header Basic ở endpoint chỉ nhận Bearer | Từ chối; không dùng Basic làm access token |
| Duplicate Authorization headers hoặc nhiều token trong một header | Từ chối trường hợp mơ hồ |
| Token trong query nhưng không có Authorization | Không xác thực bằng URL |
| Token trong path hoặc fragment | Không dùng làm bearer credential |
| Header malformed hoặc vượt kích thước giới hạn | Từ chối theo parser/HTTP contract |
| JWT đúng cấu trúc nhưng sai chữ ký | Từ chối |
| JWT đúng chữ ký nhưng sai issuer hoặc audience | Từ chối |
| JWT hết hạn, chưa tới nbf, opaque token inactive | Từ chối |
| ID token hoặc refresh token gửi tới Orders API | Từ chối sai loại/mục đích |
| Token đúng scope nhưng đọc resource của tenant khác | Từ chối theo quyền resource |

### 13.2. Browser, proxy và redirect

- Cross-origin Fetch có Authorization tạo preflight theo điều kiện CORS; OPTIONS được xử lý đúng origin/method/header mà không yêu cầu bearer không cần thiết.
- Request API thực sau preflight vẫn cần access token và kiểm tra quyền.
- Browser không đưa token vào URL, fragment, history, bookmark hoặc link tải file.
- HTTP client không chuyển Authorization sang origin không thuộc allowlist khi gặp redirect.
- Proxy forwarding giữ đúng trust boundary; backend không nhận identity header giả từ caller.
- CDN, WAF, gateway, ingress, APM, tracing và server logs đều redact token.
- Error response/WWW-Authenticate không phản chiếu raw credential.
- Cache không đưa response của Alice cho Bob hay tenant khác.
- SSE/WebSocket/download dùng cơ chế riêng phù hợp, không đưa refresh token vào URL.

### 13.3. DPoP, mTLS và replay

| Kịch bản | Kỳ vọng |
|---|---|
| Bearer token bị sử dụng lại khi còn hiệu lực | Có thể thành công nếu không có sender constraint/chặn trạng thái; phải phù hợp threat model |
| DPoP-bound token thiếu DPoP proof | Từ chối |
| DPoP proof sai chữ ký hoặc khóa không khớp binding | Từ chối |
| DPoP proof sai htm, htu, ath, iat hoặc yêu cầu nonce | Từ chối theo profile |
| DPoP proof bị phát lại | Từ chối theo cơ chế anti-replay |
| mTLS-bound token dùng chứng chỉ client không khớp | Từ chối |
| DPoP token bị hạ cấp xử lý như Bearer thuần | Từ chối |
| Refresh token bị thu hồi nhưng JWT access token offline còn hạn | Kiểm tra đúng hành vi TTL/chặn trạng thái đã thiết kế, không giả định access token tự mất hiệu lực tức thì |

Chỉ dùng **credential thử nghiệm** khi kiểm tra URL leakage; không gửi token production vào query hay báo cáo kiểm thử.

## 14. Những sai lầm phổ biến

| Sai lầm | Vì sao nguy hiểm? | Hướng sửa |
|---|---|---|
| Đưa bearer token vào query vì đã có HTTPS | URL vào log, history, link | Dùng Authorization header, rà soát URI logs |
| Chuyển token sang path | Path vẫn bị log | Không truyền bearer token qua URL |
| Cất token trong fragment | Browser/JS có thể đọc | Authorization Code + PKCE và bảo vệ client |
| Dùng Basic client secret gọi OAuth resource server | Nhầm client authentication với access token | Basic cho token endpoint khi phù hợp, Bearer cho API |
| Dùng ID token hoặc refresh token làm access token | Sai mục đích/audience | RS chỉ nhận access token đúng profile |
| Chỉ cần decode JWT rồi đọc scope | Claims có thể bị giả mạo | Xác minh signature/issuer/audience/time |
| Chỉ kiểm tra scope | Lỗ hổng BOLA/IDOR | Policy theo principal, action, resource, tenant |
| Parser split trên dấu cách mà không kiểm tra scheme | Có thể crash hoặc nhận sai credential | Dùng resolver chuẩn |
| Tự gộp nhiều Authorization headers | Credential confusion | Từ chối request mơ hồ |
| Fallback sang query khi thiếu header | Tạo đường rò URL | Tắt URI query resolution |
| CORS cho origin đúng là đủ bảo mật | CORS không phải xác thực | Vẫn validate token và quyền |
| Bật DPoP nhưng bỏ qua proof và binding | Không chống được replay | Xác minh proof đúng RFC/profile |
| Gắn token cho arbitrary URL/redirect | Token chảy ra origin khác | Base URL allowlist và redirect policy |
| Đã redact app log là xong | Gateway/APM vẫn ghi headers | Redact ở mọi hop |
| Thu hồi refresh token thì mọi JWT access token lập tức mất hiệu lực | JWT offline có thể còn sống tới exp | TTL và cơ chế trạng thái/revoke tại RS |

## 15. Tình huống tự kiểm tra

### Tình huống A: token trong URL có TLS

Mobile app gọi Orders API bằng query access_token nhưng đã bật HTTPS. **Cách này có an toàn không?**

**Đáp án:** Không. URI có thể được lưu tại proxy, log, history và hệ thống quan sát. Chuyển bearer token sang Authorization header, tắt query resolution và đánh giá bản sao URL đã lưu.

### Tình huống B: nhầm Basic với Bearer

Backend dùng client secret qua Basic tại token endpoint, rồi gửi cùng Basic header đến Orders API. **Đúng không?**

**Đáp án:** Sai vai trò. Basic có thể chỉ xác thực client để xin access token. Sau khi nhận token đúng audience, resource server thường nhận Authorization Bearer.

### Tình huống C: token đúng chữ ký nhưng audience sai

Access token do issuer tin cậy ký, còn hạn và có scope read, nhưng audience dành cho Inventory API. Client gửi token tới Orders API. **Có cho phép không?**

**Đáp án:** Không. Orders API phải kiểm tra aud dành cho chính mình trước khi đánh giá scope/resource.

### Tình huống D: preflight bị yêu cầu token

SPA từ shop.example.com gọi Orders API bằng Bearer header. Browser gửi OPTIONS không có Authorization, gateway trả 401. **Lỗi nằm ở đâu?**

**Đáp án:** CORS/preflight chưa được phối hợp đúng với authentication. OPTIONS hợp lệ cần được xử lý mà không bắt Bearer vô lý, còn request GET thật vẫn cần token và quyền.

### Tình huống E: mở tab tải báo cáo

Frontend muốn đặt access_token vào URL PDF vì thẻ anchor không thiết lập được Authorization header. **Có nên làm không?**

**Đáp án:** Không. Dùng Fetch + Blob, BFF/session hoặc một capability URL hẹp có TTL ngắn và policy riêng.

### Tình huống F: hai Authorization headers

Proxy nhận hai Authorization fields và nối vào một chuỗi bằng dấu phẩy. **API nên xử lý thế nào?**

**Đáp án:** Không tự chọn một credential. Từ chối trường hợp mơ hồ, kiểm tra cấu hình proxy và dùng parser rõ ràng.

### Tình huống G: DPoP thiếu proof

Client có DPoP-bound access token nhưng gửi Authorization Bearer mà không kèm DPoP proof. **Có thể hạ cấp thành bearer token không?**

**Đáp án:** Không. Resource server phải áp scheme, proof và token binding của DPoP đúng profile.

### Tình huống H: vẫn lộ token dù ứng dụng đã sửa

Spring đã redact Authorization, nhưng API Gateway debug log ghi toàn bộ headers. **Bảo mật đã đạt chưa?**

**Đáp án:** Chưa. Token vẫn bị lộ ở gateway. Cần bảo vệ credential qua tất cả các lớp vận chuyển và nơi lưu logs/telemetry.

## 16. Checklist vận hành

Trước khi đưa API OAuth bearer vào production:

1. **Transport:** chỉ nhận Bearer trong Authorization header qua HTTPS, không có query/path/form fallback tùy tiện.
2. **Loại token:** dùng access token đúng profile; từ chối ID token, refresh token và client secret gửi sai endpoint.
3. **Validation:** JWT signature/algorithm/issuer/audience/time hoặc opaque introspection, scope và trạng thái theo chính sách.
4. **Authorization:** kiểm tra principal, action, resource và tenant cụ thể; không chỉ authenticated.
5. **Parser:** kiểm tra thiếu, sai scheme, malformed, duplicate, header quá lớn và credential mâu thuẫn.
6. **Browser:** CORS preflight đúng, origin allowlist, không tự gắn token cho URL hoặc redirect ngoài đích tin cậy.
7. **Proxy/log:** redact Authorization và các secret ở CDN, WAF, ingress, gateway, app, distributed tracing và APM.
8. **Transport đặc biệt:** BFF/session hoặc capability/ticket hẹp cho download, SSE và WebSocket khi cần.
9. **Replay/thu hồi:** TTL, refresh rotation, revoke và sender constraint khi thích hợp.
10. **Kiểm thử:** positive/negative cases cho 401/403, JWT/opaque, Basic/Bearer/DPoP, CORS, redirect, resource policy và log leakage.

**Ghi nhớ:** Authorization header là **nơi trình credential**, không phải bản thân quyết định cấp quyền. Với OAuth bearer access token, hãy dùng **Authorization: Bearer token qua HTTPS**, bảo vệ token khỏi URL và log, xác minh đúng **issuer, audience, thời gian, scope, loại token**, rồi quyết định **principal có được thực hiện action trên resource cụ thể hay không**.

## Tài liệu tham khảo

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): Authorization, Proxy-Authorization, WWW-Authenticate và HTTP authentication.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer header, token transport và error responses.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ token, chống leakage và replay.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): token endpoint, client authentication, access/refresh token và scope.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): issuer, audience, claims và token typing.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): active state và opaque access token.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): xác minh JWT và kiểm soát ranh giới tin cậy.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): DPoP scheme, proof và sender-constrained token.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): mTLS và certificate-bound token.
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): PKCE bảo vệ authorization code.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): phân biệt ID token và access token.
- [MDN — Authorization HTTP header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Authorization): cú pháp, auth-scheme và ví dụ.
- [MDN — Cross-Origin Resource Sharing](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/CORS): preflight, Allow-Headers và Origin.
- [Spring Security Reference — Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html): DefaultBearerTokenResolver và resource server.
- [OWASP REST Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html): API security, HTTPS và token validation.
