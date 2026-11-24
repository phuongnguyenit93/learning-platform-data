# Kích thước token và giới hạn header

Một access token có thể hoàn toàn hợp lệ về chữ ký, `iss`, `aud`, `exp` và `scope`, nhưng request mang token đó vẫn bị từ chối **trước khi đến được API**. Nguyên nhân thường gặp là token quá dài, tổng cookie quá lớn, hoặc một thành phần trên đường đi (CDN, reverse proxy, API gateway, ingress, web server) giới hạn kích thước HTTP header. Khi đó, người dùng có thể gặp `431 Request Header Fields Too Large`, `400 Bad Request` hoặc lỗi do proxy phát sinh thay vì phản hồi xác thực `401`.

Trong chương **Token format**, bài học này giải thích **token chiếm bao nhiêu byte trên đường truyền, giới hạn được áp dụng ở đâu và cách thiết kế token vừa đủ nhỏ, đúng mục đích, có thể xác minh an toàn**. Kiến thức áp dụng cho JWT, opaque access token, ID token, refresh token, session cookie và các luồng OAuth 2.0/OpenID Connect (OIDC).

## 1. Vì sao kích thước token ảnh hưởng đến hệ thống?

Token thường được client gửi **lặp lại ở mỗi request**:

~~~http
GET /v1/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
Accept: application/json
~~~

Nếu token dài 12 KiB, mỗi lần gọi API có thể phải mang theo ít nhất 12 KiB dữ liệu xác thực, chưa kể tên header và các header khác. Với hàng trăm request, chi phí đường truyền, xử lý header, ghi nhận lỗi và giới hạn tài nguyên có thể trở thành vấn đề. Dù kết nối dùng HTTP/2 hoặc HTTP/3, **giới hạn kích thước header đã giải nén vẫn có thể khiến request bị từ chối**.

Nguyên nhân làm token phình to thường bao gồm:

- Nhúng quá nhiều `roles`, `groups`, `permissions`, thuộc tính người dùng hoặc dữ liệu tenant vào JWT.
- Dùng tên claim và cấu trúc JSON dài, lặp nhiều giá trị hoặc chứa dữ liệu vốn nên lấy từ API riêng.
- Chọn thuật toán ký có chữ ký dài; dùng JWE hoặc cơ chế mã hóa/gói token nhiều lớp.
- Gửi cùng lúc cookie đăng nhập, cookie phân tích, cookie ứng dụng và access token trong `Authorization`.
- Tạo nhiều token/credential riêng trong cookie rồi để trình duyệt tự gửi tất cả.

**Token dài không có nghĩa token an toàn hơn.** Điều quan trọng là entropy của opaque token, thuật toán/khóa bảo vệ JWT, đối tượng nhận, phạm vi quyền, thời hạn, lưu trữ và thu hồi. Không nên tăng dung lượng token chỉ để chứa thêm dữ liệu tiện cho UI.

## 2. Kích thước token nằm trong những phần nào của HTTP?

### 2.1. Request header, response header và body là các vùng khác nhau

| Vị trí | Ví dụ | Tác động của dung lượng |
| --- | --- | --- |
| **Request header** | `Authorization: Bearer ...` | Giới hạn một field hoặc tổng request headers; bị chặn ở edge/gateway/server |
| **Request header Cookie** | `Cookie: session=...; theme=...` | Nhiều cookie cộng dồn, trình duyệt tự gửi với request phù hợp |
| **Response header** | `Set-Cookie: session=...` | Giới hạn response headers/cookie của browser, proxy và upstream |
| **Response body** | JSON của token endpoint có `access_token` | Chủ yếu phụ thuộc giới hạn body và client parser; không bị giới hạn bởi request header của API ngay lúc nhận |
| **Request body** | Form `grant_type=...`, `refresh_token=...` tại token endpoint | Giới hạn body và chính sách token endpoint; không tự biến thành request header |
| **URL/query string** | `?access_token=...` | Có thể vượt giới hạn URI (`414`), đồng thời dễ lộ qua history, log, referrer |

Access token trong **phản hồi JSON** của authorization server chưa gây ra lỗi request header. Lỗi có thể xảy ra **ở request tiếp theo**, khi client đặt token đó vào `Authorization` hoặc cookie. Cần đo đúng bước đang thất bại.

Với **HTTP/1.1**, request header được biểu diễn bằng các dòng `Tên-Header: giá-trị\r\n`. Với **HTTP/2** và **HTTP/3**, headers được mã hóa thành block với cơ chế nén HPACK/QPACK; tuy nhiên các thành phần vẫn đánh giá **kích thước danh sách field sau giải mã** hoặc áp giới hạn triển khai tương đương. Vì thế không thể kết luận “đã chuyển HTTP/2 nên token 20 KiB luôn gửi được”.

### 2.2. Không có một “giới hạn header HTTP” duy nhất cho mọi hệ thống

Giới hạn phụ thuộc vào:

- HTTP server và phiên bản/cấu hình: ví dụ giới hạn từng field, một dòng, tổng request headers hoặc số lượng field.
- Reverse proxy, CDN, API gateway, load balancer, ingress và web application firewall (WAF).
- Giới hạn của HTTP client, trình duyệt, thư viện HTTP và số lượng cookie được gửi.
- Giao thức HTTP/1.1, HTTP/2, HTTP/3 cùng cách các thành phần công bố/áp giới hạn header list.

**Không nên mặc định “header tối đa luôn là 8 KB” hay “mọi proxy đều cho 16 KB”.** Một vài sản phẩm có giá trị mặc định cỡ nhiều KiB, nhưng cấu hình, phiên bản, nền tảng và hop cụ thể có thể khác. Nhiều trường hợp **một field lớn** bị từ chối dù tổng headers chưa chạm ngưỡng, hoặc **tổng headers** vượt ngưỡng dù từng field riêng lẻ vẫn nhỏ.

Lấy ví dụ đường đi:

~~~mermaid
flowchart LR
    B["Browser / mobile client"] -->|"Authorization + Cookie"| E["CDN / WAF"]
    E --> P["Reverse proxy / ingress"]
    P --> G["API gateway"]
    G --> A["Application server"]
    A -->|"Kiểm tra JWT / opaque token"| R["Authorization logic"]
~~~

Request chỉ tới được `Authorization logic` khi **mọi hop trước đó** chấp nhận kích thước header. Tăng giới hạn ở application server **không giải quyết** được lỗi đã xảy ra tại CDN hoặc ingress.

## 3. Vì sao JWT thường dài hơn opaque token?

### 3.1. Opaque token: giá trị ngẫu nhiên để tra cứu

Opaque token không buộc phải có định dạng hay kích thước cố định. Một hệ thống có thể tạo 32 byte ngẫu nhiên bằng bộ sinh số ngẫu nhiên mật mã rồi mã hóa Base64url **không padding**, tạo chuỗi dài **43 ký tự ASCII**:

~~~text
32 byte ngẫu nhiên
    -> Base64url không padding
    -> 43 ký tự ASCII (ví dụ độ dài, không phải token thật)
~~~

Client không tự giải mã ra user, role hoặc scope; resource server thường dùng lookup hoặc token introspection để nhận trạng thái và quyền. **43 ký tự chỉ là ví dụ**: opaque token có thể dài hơn nếu hệ thống dùng định dạng khác, nonce dài hơn hoặc thông tin đóng gói bổ sung.

Ưu điểm về dung lượng là **quyền và metadata được giữ phía issuer/store thay vì lặp trong token**. Đổi lại có thể cần introspection/lookup, cache và phương án duy trì độ sẵn sàng.

### 3.2. JWT dạng JWS compact: ba đoạn Base64url

JWT thường gặp là **JWS Compact Serialization**:

~~~text
BASE64URL(UTF8(protected-header))
.
BASE64URL(UTF8(payload))
.
BASE64URL(signature)
~~~

Ba đoạn cách nhau bằng **hai dấu chấm**, không chứa padding `=` khi dùng JOSE Base64url. Các dấu ngoặc, dấu phẩy, dấu nháy, tên claim, giá trị trong JSON và signature đều góp phần vào kích thước cuối.

Ví dụ cấu trúc có các claims của access token (chỉ minh họa payload, **không phải JWT hợp lệ**):

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "https://api.example.com/orders",
  "scope": "orders:read",
  "client_id": "orders-web",
  "iat": 1795410600,
  "exp": 1795411500
}
~~~

Một JWT đã ký **không tự mã hóa nội dung**: ai có token có thể đọc các claim được mã hóa Base64url. Không vì muốn giảm lượt gọi database mà nhét dữ liệu riêng tư/nhạy cảm vào payload.

### 3.3. Công thức tính Base64url không padding

Với `n` byte đầu vào, số ký tự Base64url **không padding** là:

\[
L(n) = 4\left\lfloor\frac{n}{3}\right\rfloor +
\begin{cases}
0 & n \bmod 3 = 0 \\
2 & n \bmod 3 = 1 \\
3 & n \bmod 3 = 2
\end{cases}
\]

Độ dài JWT compact dạng JWS:

\[
L_{\mathrm{JWT}} = L(H) + 1 + L(P) + 1 + L(S)
\]

Trong đó `H` là số byte UTF-8 của protected header JSON, `P` là số byte UTF-8 của payload JSON, `S` là số byte chữ ký nhị phân. Mỗi ký tự trong chuỗi Base64url chiếm **1 byte ASCII**. Cách nói “Base64 tăng kích thước khoảng 33%” là xấp xỉ; khi tính ngân sách, phải cộng cả **hai dấu chấm và phần chữ ký**.

Đặc biệt: nếu payload chứa chữ có dấu tiếng Việt, phải tính **số byte UTF-8**, không tính số ký tự Unicode. Chuỗi `"Đặng"` có ít ký tự nhưng chiếm nhiều byte hơn chuỗi ASCII có cùng số ký tự.

### 3.4. Chữ ký cũng có chi phí dung lượng

Giả sử protected header JSON có **48 byte**, payload JSON có **900 byte**. Khi đó `L(H)=64`, `L(P)=1.200`:

| Chữ ký JWS minh họa | Chữ ký nhị phân | Sau Base64url | JWT tổng cộng |
| --- | ---: | ---: | ---: |
| **HS256** | 32 byte | 43 ký tự | **1.309 byte** |
| **ES256** | 64 byte (dạng JOSE `R || S`) | 86 ký tự | **1.352 byte** |
| **RS256** với khóa RSA 2048 bit | 256 byte | 342 ký tự | **1.608 byte** |

Giả định ở bảng chỉ phục vụ **so sánh độ dài**. Không chuyển sang HS256 hoặc một thuật toán khác chỉ để rút ngắn token. Phải chọn thuật toán theo mô hình tin cậy, khả năng bảo vệ khóa, chính sách của issuer và resource server; **không lấy header `alg` từ token chưa tin cậy làm quyết định thuật toán cho phép**.

Với ví dụ RS256 1.608 byte, riêng dòng HTTP/1.1 này dài:

~~~text
Authorization: Bearer <1608 byte JWT>\r\n

Tiền tố "Authorization: Bearer " = 22 byte ASCII
Giá trị token                        = 1608 byte
CRLF                                 =    2 byte
Tổng một dòng                        = 1632 byte
~~~

Đây **chưa** gồm request line, `Host`, `Cookie`, `Accept`, `User-Agent`, `traceparent`, `baggage`, `x-request-id` và các headers khác.

### 3.5. JWT mã hóa JWE có thêm overhead

JWE Compact Serialization có **năm đoạn**, ngăn bởi **bốn dấu chấm**:

~~~text
protected-header.encrypted-key.iv.ciphertext.authentication-tag
~~~

Kích thước phụ thuộc thuật toán quản lý khóa và mã hóa nội dung, IV, authentication tag, ciphertext và header; có trường hợp `encrypted-key` rỗng nhưng dấu phân tách vẫn tồn tại. JWE có thể làm token lớn hơn JWS, trong khi **mã hóa nội dung** giải quyết yêu cầu bí mật khác với **chữ ký**.

Không nhầm JWT, JWS và JWE:

- **JWT** mô tả tập claims được biểu diễn dưới dạng JSON token.
- **JWS** cung cấp chữ ký/MAC bảo vệ tính toàn vẹn và xác thực nguồn ký.
- **JWE** mã hóa nội dung để giới hạn bên đọc được dữ liệu.

Nếu token vừa ký vừa mã hóa (nested JWT), kích thước có thể tăng đáng kể do nhiều lớp đóng gói.

## 4. Header bị tính tổng như thế nào?

### 4.1. Nhiều header nhỏ có thể cộng thành request lớn

Giả sử một request điển hình có:

| Thành phần | Kích thước minh họa |
| --- | ---: |
| `Authorization` chứa JWT | 2.500 byte |
| `Cookie` gồm session, phân tích và preferences | 3.500 byte |
| `User-Agent`, `Accept`, `Accept-Language`, `Origin` | 700 byte |
| Trace, correlation ID, forwarded headers | 1.500 byte |
| Tên header, dấu phân cách và overhead khác | 300 byte |
| **Tổng minh họa** | **8.500 byte** |

Các con số **không phải giới hạn mặc định** của sản phẩm nào. Chúng cho thấy token 2,5 KB vẫn có thể đi kèm một request vượt mức ngân sách header của một hop. HTTP/2/3 có cách tính header-list size khác HTTP/1.1, nên không dùng duy nhất số byte dòng HTTP/1.1 để kết luận chắc chắn request HTTP/2 sẽ được chấp nhận.

### 4.2. Cookie khiến tổng header phình lên âm thầm

Trình duyệt tự gửi các cookie phù hợp với host/domain, path, `Secure` và `SameSite` trong header `Cookie`. Một cookie được đặt riêng lẻ dưới ngưỡng hỗ trợ của trình duyệt **không bảo đảm tổng Cookie header nhỏ**:

~~~http
GET /dashboard HTTP/1.1
Host: app.example.com
Cookie: __Host-session=<id>; analytics=<value>; preferences=<value>; auth=<large-jwt>
~~~

Giới hạn tương thích thường gặp cho **một cookie** vào khoảng **4 KiB**, nhưng số cookie và giới hạn thực tế khác nhau giữa browser. Không xem “4 KiB” là quy tắc tối đa của toàn bộ `Cookie` header hoặc của mọi máy chủ.

Hai hướng đều cần được tính:

1. **Response `Set-Cookie`:** một ID token/JWT lớn đặt vào cookie có thể vượt chính sách browser hoặc giới hạn response header ở proxy.
2. **Request `Cookie`:** cùng cookie được tự gửi lặp lại trong nhiều request có phạm vi phù hợp, kể cả request không cần thông tin xác thực.

Thêm nhiều cookie để “chia nhỏ” một JWT lớn thường **không giải quyết** giới hạn tổng header, còn tăng chi phí quản lý thứ tự, tái lắp ghép, bảo mật và lỗi thiếu một phần. Nếu cookie lớn, nên xem lại cấu trúc token hoặc thiết kế session.

### 4.3. Client và các hop trên đường đi có giới hạn riêng

~~~mermaid
sequenceDiagram
    participant C as Browser / Client
    participant E as CDN / Ingress
    participant G as API Gateway
    participant A as API
    C->>E: Request + Authorization + Cookie
    alt Vượt giới hạn tại edge
        E-->>C: 431 / 400 (tùy triển khai)
    else Được chấp nhận tại edge
        E->>G: Forward request
        alt Vượt giới hạn tại gateway
            G-->>C: 431 / 400 hoặc lỗi proxy
        else Headers hợp lệ
            G->>A: Forward request
            A->>A: Xác minh token + phân quyền
            A-->>C: 200 / 401 / 403 theo kết quả
        end
    end
~~~

Khi request thất bại trước ứng dụng, **log controller có thể hoàn toàn không xuất hiện**. Cần có metric/log trạng thái ở edge và gateway, chỉ ghi **độ dài header**, route, request ID và mã lỗi; không ghi giá trị token.

## 5. Phân biệt lỗi kích thước với lỗi xác thực

| Tín hiệu | Nguyên nhân cần kiểm tra | Hành động |
| --- | --- | --- |
| **`431 Request Header Fields Too Large`** | Một hoặc nhiều field/tổng request headers vượt ngưỡng được chấp nhận | Đo kích thước và tìm hop trả lỗi; giảm payload/header |
| **`400 Bad Request`** | Có thể do header quá lớn hoặc sai cú pháp, tùy server/proxy | Đọc log tầng nhận request và kiểm tra cấu hình; không tự kết luận JWT sai |
| **`414 URI Too Long`** | Request target/URL quá dài, có thể do đưa token vào URL | Bỏ token khỏi query, dùng luồng/đường truyền được chuẩn cho credential |
| **`413 Content Too Large`** | Body request vượt ngưỡng; khác giới hạn request header | Kiểm tra payload body và endpoint tương ứng |
| **`401 Unauthorized`** | Token thiếu/hết hạn/sai hoặc không đáp ứng authentication challenge | Kiểm tra `WWW-Authenticate`, issuer, audience, hạn, loại token |
| **`403 Forbidden`** | Credential đã được chấp nhận nhưng không đủ quyền theo chính sách | Kiểm tra scope, role, tenant, quyền sở hữu tài nguyên |
| **`502 Bad Gateway` / lỗi proxy** | Có thể có vấn đề với upstream, đôi khi response header quá lớn | Kiểm tra log proxy/upstream trước khi kết luận |

**`431` không phải `invalid_token`.** Một access token hợp lệ về mật mã vẫn có thể không qua được giới hạn transport. Ngược lại, rút ngắn token cũng **không khiến token hết hạn hoặc sai audience trở thành hợp lệ**.

## 6. JWT nên chứa những claim nào?

JWT access token cần đủ thông tin để resource server xác thực và phân quyền theo **profile đã thống nhất**, nhưng không phải nơi lưu toàn bộ hồ sơ người dùng.

Một thiết kế thường cần:

- **Issuer (`iss`)** để API xác định bên phát hành được tin.
- **Audience (`aud`)** đúng API/resource được cấp token.
- **Subject/principal (`sub`)** và thông tin client khi profile sử dụng.
- **Thời gian (`exp`, `iat`, `nbf` khi có)** để kiểm soát vòng đời.
- **Scope/permissions tối thiểu cần thiết** để API biết token được cấp cho chức năng nào.
- **Các claims theo chuẩn/profile** của issuer và API, tránh tự đổi tên hoặc bỏ trường bắt buộc chỉ để tiết kiệm byte.

Ví dụ thiết kế dễ phình to:

~~~json
{
  "sub": "user-42",
  "groups": [
    "department-sales-apac-team-a",
    "department-sales-apac-team-b",
    "department-sales-eu-team-a"
  ],
  "permissions": [
    "orders.read.all",
    "orders.write.all",
    "reports.read.all",
    "users.manage.all"
  ],
  "full_profile": {
    "email": "user@example.com",
    "address": "Thông tin hồ sơ không cần cho API"
  }
}
~~~

Khi một user tham gia hàng trăm nhóm, chuỗi claims có thể vượt xa dung lượng dự kiến. Ngoài kích thước, dữ liệu role/group nhúng trong JWT có thể **cũ** sau khi quyền bị thu hồi trong khi token vẫn còn hiệu lực.

Thiết kế gọn hơn cho API chỉ đọc đơn hàng có thể giống:

~~~json
{
  "iss": "https://auth.example.com",
  "sub": "user-42",
  "aud": "https://api.example.com/orders",
  "scope": "orders.read",
  "iat": 1795410600,
  "exp": 1795411500
}
~~~

Đây là payload minh họa, **không phải token có chữ ký**. Việc rút gọn không được bỏ kiểm tra **quyền trên đối tượng**: `orders.read` không cho phép user đọc mọi đơn hàng nếu backend chưa xác minh ownership/tenant.

### 6.1. Những cách giảm dung lượng đúng hướng

| Cách làm | Lợi ích | Điều kiện/rủi ro cần quản lý |
| --- | --- | --- |
| Giảm số claims về mức cần cho API | Token nhỏ hơn, ít lộ dữ liệu | Vẫn giữ các trường bắt buộc theo profile |
| Dùng identifier ngắn, ổn định cho principal/tenant | Giảm dữ liệu lặp | API có cách giải quyết định danh đáng tin; không dùng ID đoán được làm credential |
| Tách profile sang UserInfo hoặc API riêng | Không gửi thông tin hiển thị trong mọi request | Auth và quyền truy cập UserInfo/API phải đúng |
| Dùng scope phù hợp cho từng audience | Tránh token “mọi quyền, mọi API” | API kiểm tra cả scope lẫn quyền trên đối tượng |
| Dùng opaque token + introspection/lookup | Client mang credential ngắn | Thêm lookup/caching, availability và giới hạn độ trễ thu hồi |
| Dùng BFF + session cookie ngắn | Browser gửi session ID, backend giữ token API | Quản lý session store, chống CSRF/XSS, bảo vệ token tại backend |
| Giảm TTL của token đặc quyền | Thu hẹp cửa sổ rủi ro replay | Có chiến lược cấp lại và xử lý step-up phù hợp |

Không nên rút gọn bằng cách **bỏ `aud`**, bỏ `iss`, bỏ kiểm tra signature, tăng quyền chung để tránh liệt kê scope, hoặc truyền thông tin phân quyền từ client chưa được xác minh. Tối ưu kích thước **không được đánh đổi mô hình tin cậy**.

### 6.2. Có nên nén JWT không?

Không xem nén là giải pháp mặc định cho token dài:

- **JWS compact thông thường không có cơ chế `zip` chuẩn để tự nén payload rồi giữ nguyên mọi semantics JWT/JWS.** Thay đổi encoding tùy tiện khiến token không tương thích với validator.
- **JWE** hỗ trợ tham số nén nội dung trong một số cấu hình, nhưng cần bảo đảm tương thích và đánh giá rủi ro **compression side channel** khi dữ liệu bí mật và đầu vào do attacker kiểm soát bị xử lý cùng nhau.
- **HPACK/QPACK** là nén header ở giao thức truyền tải, không loại bỏ giới hạn header-list sau giải nén và không giải quyết dữ liệu JWT quá lớn.
- **Chia token qua nhiều headers/cookies** thường vẫn chạm giới hạn tổng và có thể gây lỗi an toàn, đồng bộ, proxy.

Đường hướng ưu tiên là **giảm claims, dùng token tham chiếu hoặc điều chỉnh kiến trúc lưu trạng thái**, rồi mới xem xét thay đổi giới hạn transport nếu thực sự cần.

## 7. Đặt token vào đâu để tránh lỗi và rò rỉ?

### 7.1. Access token trong Authorization header

Với OAuth 2.0 Bearer token, cách điển hình:

~~~http
GET /v1/orders HTTP/1.1
Host: api.example.com
Authorization: Bearer <access-token>
~~~

Client chủ động gửi header; browser **không tự thêm** access token vào `Authorization` chỉ vì có phiên đăng nhập. API xác minh token đúng issuer, audience, hạn, scope và chính sách quyền.

Nếu token quá dài gây `431`, cần giảm token và kiểm tra ngân sách headers. **Không chuyển sang query parameter** chỉ để qua lỗi giới hạn mà không xét rò rỉ credential.

### 7.2. Token hoặc session ID trong cookie

Cookie có thể mang một session ID hoặc token. Ví dụ với session server-side:

~~~http
Set-Cookie: __Host-session=<random-session-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Một session ID ngẫu nhiên đủ entropy thường ngắn hơn JWT chứa nhiều claims. Backend tra session store để xác định trạng thái và quyền. Cần bảo vệ cookie, session fixation, CSRF, XSS và thu hồi khi logout.

Cookie không tự xác thực; **server vẫn phải kiểm tra giá trị nhận được**. Đặt JWT vào `HttpOnly` cookie hạn chế JavaScript đọc trực tiếp nhưng không làm JWT ngắn hơn và không tự ngăn CSRF do cookie được trình duyệt gửi tự động.

### 7.3. Token trong URL hoặc log

Không đưa bearer access token, refresh token hoặc session ID vào query string hoặc đường dẫn. URL có thể bị lưu trong browser history, reverse proxy log, monitoring, cache và các hệ thống trung gian khác. URL quá dài còn có thể gây `414 URI Too Long`.

Khi debug lỗi header, **không in token thật** vào logs, tracing, báo cáo lỗi, console screenshot hoặc ví dụ công khai. Chỉ log **kích thước, loại header, hop, mã lỗi, request ID** và thông tin cần thiết đã được lọc.

### 7.4. ID token và refresh token có vị trí riêng

- **ID token OIDC** dành cho client để xác nhận sự kiện đăng nhập. Không gửi ID token tới resource API như access token.
- **Refresh token** được gửi tới token endpoint theo luồng cấp mới token, không gửi tới API tài nguyên.
- **Opaque access token** có thể ngắn hơn JWT nhưng vẫn cần bảo vệ bearer credential và xác minh trạng thái/scope/audience.

Không giải quyết vấn đề kích thước bằng cách hoán đổi các loại token cho nhau: **mỗi token có mục đích và audience khác nhau**.

## 8. Đo dung lượng đúng cách trong Java

Đo **byte thực tế**, tránh đo số ký tự UI hoặc đo JSON chưa Base64url. Với JWT compact hoặc opaque token dạng ASCII, `token.length()` thường trùng số byte, nhưng cách an toàn cho header là dùng **UTF-8 bytes** của chuỗi được truyền.

Ví dụ Java 17, chỉ in số đo và **không in nội dung credential**:

~~~java
import java.nio.charset.StandardCharsets;

public final class HeaderBudget {
    private HeaderBudget() {}

    private static int utf8Bytes(String value) {
        return value.getBytes(StandardCharsets.UTF_8).length;
    }

    // Số ký tự Base64url không padding cho n byte thô.
    public static int base64UrlLength(int n) {
        if (n < 0) {
            throw new IllegalArgumentException("n must be non-negative");
        }
        int full = (n / 3) * 4;
        return switch (n % 3) {
            case 1 -> full + 2;
            case 2 -> full + 3;
            default -> full;
        };
    }

    // Token và cookieValue được truyền nội bộ; KHÔNG log các giá trị này.
    public static void measure(String accessToken, String cookieValue) {
        int tokenBytes = utf8Bytes(accessToken);
        int authValueBytes = utf8Bytes("Bearer ") + tokenBytes;

        // Dùng cách tính dòng HTTP/1.1; HTTP/2/3 có cách tính khác.
        int authLineBytes =
            utf8Bytes("Authorization: ") + authValueBytes + 2; // CRLF

        int cookieLineBytes =
            (cookieValue == null || cookieValue.isEmpty())
                ? 0
                : utf8Bytes("Cookie: ") + utf8Bytes(cookieValue) + 2;

        System.out.printf(
            "token_bytes=%d auth_value_bytes=%d " +
            "auth_line_h1_bytes=%d cookie_line_h1_bytes=%d%n",
            tokenBytes, authValueBytes, authLineBytes, cookieLineBytes
        );
    }
}
~~~

Ví dụ cách tự kiểm tra lý thuyết:

~~~text
Base64url unpadded:
  32 byte  -> 43 ký tự
  48 byte  -> 64 ký tự
  64 byte  -> 86 ký tự
  256 byte -> 342 ký tự
  900 byte -> 1200 ký tự

JWT với H=48, P=900, S=256 byte:
  64 + 1 + 1200 + 1 + 342 = 1608 byte

Dòng Authorization HTTP/1.1:
  22 + 1608 + 2 = 1632 byte
~~~

**Đây chỉ là phép đo một header.** Khi kiểm thử trên hệ thống thực, phải tính request đầy đủ theo giao thức/hop:

1. Đo số byte **access token, `Authorization` và tổng `Cookie`** bằng fixture/sandbox không có bí mật thật.
2. Đo request headers đầy đủ với `Host`, trace headers, proxy-added headers, cookies và CORS-related headers khi áp dụng.
3. Thử qua **đúng chuỗi CDN → ingress → gateway → API** với môi trường cấu hình tương đương production.
4. Ghi nhận kích thước ở các percentiles (ví dụ p50, p95, p99, max) và theo nhóm người dùng có nhiều role/group.
5. Kiểm tra cả request HTTP/1.1 và HTTP/2/3 nếu chúng thực sự được sử dụng trong production.

Nếu muốn kiểm thử bằng token giả, dùng các chuỗi có **độ dài tương đương** nhưng không phải bearer credential có hiệu lực. Khi đo nội bộ bằng credential thật, giữ dữ liệu trong memory và không ghi ra log, terminal history hoặc báo cáo.

## 9. Xây ngân sách header theo hệ thống

Không có một kích thước token “chuẩn cho mọi ứng dụng”. Có thể đặt mục tiêu kỹ thuật như **JWT ngắn trong khoảng 1–2 KiB khi thực tế cho phép**, nhưng đây **không phải yêu cầu của OAuth, JWT hay HTTP**. Ngân sách chính thức phải được suy ra từ **giới hạn nhỏ nhất của tất cả hop** và cộng cả headers khác.

Ví dụ một chính sách nội bộ (các ngưỡng đều là **giả định**):

~~~text
Giới hạn nhỏ nhất của các hop:       12 KiB cho tổng request headers
Ngân sách cho Cookie:                3 KiB
Ngân sách cho header/tracing khác:   3 KiB
Khoảng dự phòng vận hành:            2 KiB
Ngân sách còn lại cho Authorization: 4 KiB
~~~

Không nên đưa token đến đúng sát giới hạn vì headers và cookies có thể tăng theo thời gian, phiên bản browser hoặc cấu hình proxy. Cần giám sát biến động và có giới hạn phát hành token ngay ở AS.

### 9.1. Kiểm tra ba loại giới hạn

- **Per-header:** một `Authorization` hoặc `Cookie` field có vượt giới hạn riêng của hop không?
- **Aggregate:** toàn bộ danh sách headers có vượt giới hạn không, kể cả các field do proxy thêm vào?
- **Application-specific:** có giới hạn cookie của browser, request target, response headers, số field, hoặc cấu hình route riêng không?

Khi nhiều dịch vụ tham gia, AS cần có **token issuance contract**: những claim nào có thể xuất hiện, số lượng nhóm tối đa, đối tượng nhận, kiểu token, thuật toán và ngân sách byte. RS/gateway cần có **acceptance contract**: giới hạn header, nội dung validation, phạm vi resource và lỗi phản hồi.

### 9.2. Khi nào nên tăng giới hạn gateway?

Tăng giới hạn có thể phù hợp khi token và headers đã được tối ưu mà yêu cầu hợp lệ vẫn vượt ngưỡng; tuy nhiên cần:

- Xác nhận hop thực sự gây lỗi, tránh chỉ đổi cấu hình application server.
- Đồng bộ giới hạn giữa CDN, WAF, ingress, gateway, web server và HTTP client.
- Đánh giá **CPU, bộ nhớ, khả năng chống DoS**: các header lớn khiến parser, logging và buffering tốn tài nguyên.
- Đặt giới hạn có chủ đích, kiểm thử trường hợp vượt ngưỡng, theo dõi p95/p99 và có phương án rollback.

**Không tùy tiện nâng mọi giới hạn lên hàng trăm KiB** chỉ để chấp nhận JWT chứa quá nhiều dữ liệu phân quyền.

## 10. Các tình huống thực tế

### Tình huống A — Người dùng nhiều nhóm bị 431

Một user thuộc 350 nhóm nội bộ, AS nhúng toàn bộ tên nhóm vào JWT. Token tăng từ 2 KiB lên 18 KiB. Các request đến API bị `431` ở ingress, còn user có ít nhóm vẫn truy cập bình thường.

**Phân tích:** lỗi gắn với **độ lớn claim**, không nhất thiết là mật khẩu, signature hay scope sai. Cần đo JWT và headers qua ingress; giới hạn/sắp xếp lại group claims, chuyển sang quyền tối thiểu theo audience hoặc tra quyền server-side. Trước khi bỏ claim, bảo đảm RS có cách xác minh quyền chính xác và kịp thời.

### Tình huống B — JWT 2 KiB vẫn thất bại

Access token khoảng 2 KiB nhưng domain có nhiều cookie dài. Trình duyệt gửi hơn 7 KiB cookie cùng request. Gateway trả lỗi dù `Authorization` riêng lẻ không lớn.

**Phân tích:** cần tính **tổng headers**, đặc biệt `Cookie` và headers do proxy thêm. Có thể giảm cookie không cần thiết, điều chỉnh phạm vi cookie đúng ứng dụng, dùng session ID ngắn hoặc tách subdomain phù hợp. Không loại bỏ bảo vệ `Secure`/`HttpOnly`/`SameSite` để tiết kiệm vài byte.

### Tình huống C — Đổi RS256 thành HS256 để tiết kiệm token

Nhóm phát triển thấy chữ ký HS256 ngắn hơn RS256 và đề xuất đưa shared secret của AS cho tất cả microservice để chúng tự xác minh JWT.

**Phân tích:** điều đó thay đổi **mô hình tin cậy**: một service nắm secret HS256 có khả năng tự tạo MAC hợp lệ nếu secret bị lộ. Với chữ ký bất đối xứng, resource server chỉ cần khóa công khai để xác minh. Không đổi thuật toán chỉ vì độ dài; cân nhắc ES256/EdDSA theo chính sách và hệ sinh thái hỗ trợ, cùng việc tối ưu claims.

### Tình huống D — API không nhận ID token dù ID token ngắn hơn

Client có ID token 800 byte và access token 3 KiB. Người phát triển thử đưa ID token vào `Authorization` vì “cùng ký bởi một issuer và ngắn hơn”.

**Phân tích:** **Sai loại token/audience**. ID token được phát cho OIDC client để nhận định danh; API cần access token đúng `aud`, scope và profile. Cách giải quyết đúng là điều chỉnh access token hoặc mô hình ủy quyền, không hoán đổi token.

### Tình huống E — Token mới ngắn hơn nhưng quyền không còn đúng

AS bỏ toàn bộ claim nhóm khỏi JWT, API lại mặc định `role=user` và cho truy cập dữ liệu không đối chiếu tenant/ownership. Request không còn `431`, nhưng xuất hiện rủi ro vượt quyền.

**Phân tích:** tối ưu kích thước phải đi cùng **phân quyền chính xác**. Nếu quyền được tra cứu ngoài token, RS cần nguồn quyền tin cậy, cache hợp lý, chính sách khi hệ thống tra cứu lỗi và kiểm tra trên từng tài nguyên.

### Tình huống F — Token hợp lệ nhưng HTTP/2 vẫn bị từ chối

Ứng dụng chuyển từ HTTP/1.1 sang HTTP/2. Một số user vẫn lỗi khi gửi header `Cookie` và `Authorization` rất lớn.

**Phân tích:** HPACK nén các header trên dây, nhưng gateway vẫn có thể đặt ngưỡng **header list sau giải mã**. Phải kiểm tra giới hạn hop thực tế thay vì suy luận dựa trên hiệu quả nén mạng.

## 11. Checklist triển khai và vận hành

1. **Xác định nơi chứa token:** `Authorization`, `Cookie`, `Set-Cookie` hay body của token endpoint; đo đúng chiều request/response.
2. **Đo byte thực tế:** toàn JWT compact gồm header, payload, signature, Base64url và dấu chấm; đừng chỉ đo JSON hoặc số ký tự Unicode.
3. **Kiểm tra mọi hop:** CDN, WAF, reverse proxy, ingress, gateway, application server, browser và HTTP client.
4. **Tính tổng headers:** token, cookie, trace, forwarding và headers riêng, có khoảng dự phòng cho thay đổi.
5. **Theo dõi token lớn nhất:** test user có nhiều group, nhiều role, nhiều tenant và hồ sơ khác thường.
6. **Không bỏ security claims cần thiết:** issuer, audience, thời hạn, scope và loại token phải được xác minh đúng profile.
7. **Giảm payload dư thừa:** bỏ dữ liệu UI/profile không thiết yếu; cân nhắc opaque token, introspection hoặc BFF khi phù hợp.
8. **Giữ đúng loại token:** ID token cho OIDC client; access token cho RS; refresh token cho AS; session ID cho session store.
9. **Không dùng URL hoặc log để “tránh header”:** phòng credential leak/replay và tránh làm lộ thông tin riêng tư.
10. **Phân biệt lỗi:** `431`/header parsing, `414`/URL, `413`/body với `401` authentication và `403` authorization.
11. **Kiểm tra bảo mật khi đổi định dạng:** thuật toán ký, key management, claims validation, revocation và chính sách quyền sau khi tối ưu.
12. **Chốt hợp đồng AS–RS–gateway:** ngân sách token/headers, giới hạn phát hành, kiểm thử tải và cảnh báo p95/p99 trước khi release.

## 12. Tài liệu tham khảo

- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): HTTP fields, request handling và các mã `413`, `414`, `431`.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113): header fields, xử lý giới hạn và HTTP/2 header compression.
- [RFC 9204 — QPACK: Field Compression for HTTP/3](https://www.rfc-editor.org/rfc/rfc9204): nén field trong HTTP/3; không thay mục đích validation header.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515): JWS Compact Serialization và Base64url.
- [RFC 7516 — JSON Web Encryption (JWE)](https://www.rfc-editor.org/rfc/rfc7516): JWE compact năm thành phần, nén và mã hóa nội dung.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): cấu trúc JWT và claims.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): truyền bearer access token, đặc biệt qua `Authorization`.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access token theo JWT profile và yêu cầu xác minh ở resource server.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): khuyến nghị bảo vệ token, chống rò rỉ và giới hạn quyền.

**Ghi nhớ:** **Giới hạn header là điều kiện vận chuyển, khác với tính hợp lệ mật mã và quyền truy cập.** Token có thể hợp lệ nhưng request vẫn bị chặn trước API; JWT có thêm overhead Base64url/chữ ký, cookie và các header khác làm tổng dung lượng tăng. Hãy đo byte thật, xác định hop có ngưỡng nhỏ nhất, giảm claims dư thừa và giữ nguyên các kiểm tra `iss`, `aud`, `exp`, `scope` cùng quyền trên tài nguyên khi tối ưu.
