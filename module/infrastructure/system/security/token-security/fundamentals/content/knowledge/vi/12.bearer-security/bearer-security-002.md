# Không đưa bearer token vào URL

## 1. Vì sao đây là quy tắc bảo mật quan trọng?

Trong chương **Bearer security** của module **SECURITY_TOKEN_SECURITY_FUNDAMENTALS**, một nguyên tắc thực hành quan trọng là: **không đặt bearer access token vào URL** — bao gồm query string, path, thông tin userinfo và cả fragment mà trình duyệt có thể xử lý. Thay vào đó, khi gọi một API dùng OAuth 2.0 bearer access token, client thường gửi token trong HTTP header **`Authorization: Bearer ...`** qua kết nối HTTPS.

Hãy xét hai lời gọi đến Orders API.

**Không an toàn — token trong query string:**

~~~http
GET /api/orders/order-721?access_token=<SECRET_ACCESS_TOKEN> HTTP/1.1
Host: orders.example.com
~~~

**Đúng hướng — token trong Authorization header:**

~~~http
GET /api/orders/order-721 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <ACCESS_TOKEN>
~~~

Trong cả hai request, token có thể là JWT hoặc opaque token, còn hạn và được cấp đúng scope. **Sự khác biệt quan trọng nằm ở bề mặt bị lộ:** URL thường đi vào lịch sử trình duyệt, log truy cập, proxy, hệ thống giám sát, công cụ chia sẻ liên kết hoặc các bản ghi khác. Một người nhìn thấy URL chứa bearer token có thể sử dụng chính credential đó nếu không có kiểm soát ràng buộc bên gửi.

**Bearer token** có tính chất nền tảng: bên nào **chiếm hữu** giá trị token có thể trình nó để sử dụng quyền đã được cấp, miễn token còn hiệu lực và được resource server chấp nhận. Khác với mật khẩu gốc, một access token có thể chỉ sống ngắn và bị giới hạn audience/scope; tuy nhiên, **token bị lộ vẫn là credential có khả năng truy cập** trong phạm vi của nó.

### Mục tiêu bài học

Sau khi học, bạn có thể:

1. Giải thích vì sao đặt bearer token vào URL tạo thêm các đường rò rỉ, kể cả khi đã bật HTTPS.
2. Phân biệt rủi ro ở **query**, **path**, **fragment**, redirect và các liên kết dùng để tải file.
3. Sử dụng header Authorization đúng theo OAuth 2.0 và cấu hình resource server không nhận bearer token từ URL.
4. Thiết kế browser app, BFF, API, download và kết nối thời gian thực để không phải đưa access token vào liên kết.
5. Hiểu các ngoại lệ có kiểm soát như pre-signed URL là **capability nhạy cảm**, không phải lý do để đưa access token đa năng vào query.
6. Lập checklist kiểm thử, ghi log an toàn, xử lý lộ token và giảm khả năng bị phát lại.

## 2. Bearer token là gì, và tại sao vị trí truyền quan trọng?

OAuth 2.0 định nghĩa access token là credential để client truy cập một resource server. Trong mô hình **bearer token** (RFC 6750), việc chứng minh quyền sử dụng token **không đòi hỏi** người gửi phải chứng minh đang nắm một khóa mật mã riêng gắn với token ở mỗi request.

Ví dụ payload của một JWT access token:

~~~json
{
  "iss": "https://login.example.com",
  "sub": "alice-123",
  "aud": "https://orders.example.com",
  "client_id": "shop-web",
  "scope": "orders:read",
  "iat": 1893492000,
  "exp": 1893492900,
  "jti": "token-example-018"
}
~~~

Đây là **payload minh họa**, không phải JWT hoàn chỉnh đã ký và không phải token thật. Các claim vẫn phải được resource server xác minh đầy đủ. Nếu Alice có quyền đọc `order-721` và token bị lộ, bên khác có thể thử gọi API trong khoảng token còn hiệu lực.

### 2.1. Ba trục cần phân biệt

| Trục | Ví dụ | Ý nghĩa |
|---|---|---|
| **Mục đích token** | Access, ID, refresh token | Credential dùng gọi API, xác minh kết quả đăng nhập tại client hay làm mới quyền truy cập |
| **Cách biểu diễn** | JWT, opaque token | Resource server xác minh JWT có chữ ký hoặc tra trạng thái opaque token theo hợp đồng |
| **Cơ chế sử dụng** | Bearer, sender-constrained | Chỉ cần mang token, hoặc còn phải chứng minh quyền sở hữu khóa/chứng chỉ liên quan |

Một access token có thể là **JWT bearer token** hoặc **opaque bearer token**. JWT có chữ ký **không đồng nghĩa** token được ràng buộc với người cầm nó. Chữ ký chứng minh tính toàn vẹn/nguồn phát hành sau khi được xác minh; nó không ngăn bên khác dùng lại bearer token đã lấy cắp.

**ID token** trong OIDC hướng tới client xác minh thông tin đăng nhập và thường có audience là client; không dùng nó làm access token cho Orders API. **Refresh token** dùng tại token endpoint để lấy token mới, không gửi đến resource server. Đưa refresh token vào URL còn làm nghiêm trọng hơn rủi ro lộ credential vì nó có thể cho phép kéo dài quyền truy cập theo chính sách của Authorization Server.

### 2.2. Phạm vi token giới hạn tác động, không làm lộ token trở nên an toàn

Ngay cả khi token có:

- `exp` chỉ còn 5 phút;
- `aud` chỉ Orders API;
- `scope` chỉ `orders:read`;
- `sub` của một người dùng đã xác thực;

thì việc lộ token vẫn có thể cho phép truy cập các đơn hàng nằm trong quyền của principal cho tới khi token hết hiệu lực hoặc bị từ chối. Không có thời gian sống nào biến một bearer credential trong URL thành không nhạy cảm.

## 3. Những cách đưa token vào URL cần tránh

### 3.1. Query string

~~~text
https://orders.example.com/api/orders/721?access_token=eyJ...
https://files.example.com/download?token=eyJ...
https://api.example.com/data?bearer=<TOKEN>
~~~

Query string là phần sau dấu `?`. Dù đặt tên tham số là `access_token`, `auth`, `jwt`, `key` hay `session`, **nếu giá trị là một bearer credential thì rủi ro không thay đổi**.

RFC 6750 có mô tả phương thức truyền bearer token bằng **URI query parameter** vì lý do tương thích lịch sử, nhưng chính tài liệu nêu phương thức này **không được khuyến nghị** do các điểm yếu bảo mật. Khuyến nghị bảo mật OAuth hiện đại (RFC 9700) yêu cầu client không truyền access token trong URI query parameter. Trong thiết kế API mới, **không hỗ trợ cách này**.

### 3.2. Path segment

~~~text
https://orders.example.com/api/token/<ACCESS_TOKEN>/orders
https://files.example.com/private/<ACCESS_TOKEN>/report.pdf
~~~

Đổi từ query sang path **không giải quyết được** vấn đề. Path vẫn có thể xuất hiện trong access log, router, browser history, proxy log, telemetry, screenshot hoặc liên kết được chia sẻ.

### 3.3. Userinfo của URL

~~~text
https://<USERNAME_OR_TOKEN>@api.example.com/resource
~~~

Không đưa token vào phần userinfo trước ký hiệu `@`. Đây không phải cách truyền OAuth bearer access token chuẩn và dễ bị xử lý/ghi lại ngoài ý muốn. Không dùng URL chứa userinfo để thay thế header Authorization.

### 3.4. Fragment sau dấu `#`

~~~text
https://app.example.com/callback#access_token=<ACCESS_TOKEN>
~~~

**Khác biệt kỹ thuật quan trọng:** URL fragment **không được trình duyệt gửi lên máy chủ trong HTTP request thông thường**, và fragment cũng không được đưa vào HTTP Referer header theo cách định nghĩa chuẩn. Tuy nhiên, fragment vẫn nằm trong **địa chỉ hiển thị tại trình duyệt**, có thể vào lịch sử, bookmark, ảnh chụp màn hình, bản sao URL và bị JavaScript trên trang đọc qua `location.hash`. Script độc hại, XSS hoặc công cụ analytics thu thập URL có thể làm lộ nó.

Một số luồng OAuth cũ từng trả access token trong fragment (implicit flow), nhưng với các ứng dụng hiện đại nên dùng **Authorization Code + PKCE** thay vì thiết kế mới dựa vào implicit flow. **Fragment không phải nơi lưu bearer token an toàn chỉ vì server không nhận nó.**

### 3.5. Token trong redirect URL hoặc link được gửi qua email

~~~text
Location: https://partner.example.com/callback?access_token=<ACCESS_TOKEN>
<a href="https://api.example.com/export?token=<ACCESS_TOKEN>">Tải file</a>
~~~

Access token trong `Location`, email, thông báo chat hoặc QR code vẫn là **token trong URL**. Link có thể được mở bởi hệ thống quét bảo mật, trình tạo preview, trình duyệt khác hoặc người nhận ngoài dự kiến. Đừng dùng một bearer access token nhiều quyền như "mã tải file" gắn trong liên kết.

## 4. URL có thể làm lộ bearer token qua những đường nào?

| Kênh rò rỉ | Cơ chế | Vì sao HTTPS chưa đủ |
|---|---|---|
| **Access log của server** | Nhiều cấu hình ghi request line bao gồm path và query | Log được tạo sau khi kết nối TLS đã được giải mã |
| **Reverse proxy, API gateway, CDN, WAF** | Thành phần trung gian nhìn thấy và có thể log URI khi terminate TLS | Đây là hệ thống có quyền xử lý HTTP request, không phải kẻ nghe lén mạng |
| **Browser history, bookmark, đồng bộ** | URL được lưu hoặc sao chép để mở lại | HTTPS không kiểm soát việc browser lưu địa chỉ |
| **Referer/Referrer** | Trang mới hoặc tài nguyên cùng nguồn có thể nhận URL trang trước theo chính sách referrer | Chính sách referrer và trình duyệt quyết định phần URL được gửi, không phải TLS |
| **Analytics, session replay, error telemetry** | SDK thu thập full URL, query hay fragment từ trang | Dữ liệu có thể được gửi tới nhà cung cấp giám sát |
| **Chia sẻ link và link preview** | Người dùng gửi URL cho người khác hoặc dịch vụ preview tự mở | Người nhận biết cùng bearer credential |
| **Screenshot, ticket hỗ trợ, terminal history** | URL bị dán vào công cụ cộng tác hoặc lệnh dòng | Các hệ thống này có vòng đời lưu dữ liệu riêng |
| **Cache hoặc bản ghi kiểm thử** | Key cache, metric labels, HAR/trace chứa URL | Token có thể tồn tại sau khi request kết thúc |

### 4.1. Referer không phải lúc nào cũng chứa toàn bộ query

Cần hiểu đúng để tránh khái quát quá mức: nhiều trình duyệt hiện đại có chính sách mặc định gần với **`strict-origin-when-cross-origin`**, theo đó request **khác origin** thường chỉ gửi phần **origin** của trang trước chứ không gửi toàn bộ path/query. Nhưng với request **cùng origin**, URL chi tiết hơn có thể được gửi; các ứng dụng còn có thể chủ động cấu hình `Referrer-Policy` khác hoặc đang chạy trong trình duyệt/luồng cũ.

Vì vậy, nguy cơ từ Referer là **phụ thuộc vào trình duyệt, origin, redirect và chính sách**, không phải mọi lần mở trang ngoài đều tiết lộ toàn bộ token. Dù giảm được Referer, **server logs, lịch sử, analytics và chia sẻ liên kết vẫn tồn tại**.

### 4.2. HTTPS bảo vệ điều gì, không bảo vệ điều gì?

Với TLS được cấu hình đúng, đường dẫn/query được bảo vệ khỏi người nghe lén thụ động trên mạng giữa client và điểm kết thúc TLS. Nhưng:

- Máy chủ và proxy terminate TLS **đọc được URL** để xử lý request.
- Browser, ứng dụng client, SDK giám sát và log nội bộ có thể **lưu URL**.
- Người dùng có thể **sao chép hoặc chia sẻ** URL.
- URL có thể bị đưa vào một request khác qua redirect hoặc công cụ preview.

Do đó, **HTTPS là bắt buộc nhưng không phải lý do chấp nhận access token trong query**.

### 4.3. Minh họa chuỗi rò rỉ

~~~mermaid
sequenceDiagram
    actor U as Alice
    participant B as Trình duyệt
    participant P as Reverse proxy
    participant A as Orders API
    participant L as Log/giám sát
    participant X as Người truy cập log trái phép
    U->>B: Mở link chứa access_token trong query
    B->>P: HTTPS GET /orders?access_token=<SECRET>
    P->>L: Log request URI chứa token
    P->>A: Chuyển tiếp request
    A-->>B: Trả kết quả
    X->>L: Đọc URI từ log bị lộ
    L-->>X: Token trong URL
    X->>A: Gọi API khác bằng token còn hạn
    Note over A: Bearer token có thể được chấp nhận nếu không bị ràng buộc bên gửi
~~~

**Điểm thất bại:** token đã được đưa vào dữ liệu vốn thường được xem là metadata của request. Không cần phá chữ ký JWT hay giải mã TLS trên đường truyền; chỉ cần đọc được một bản ghi URL.

## 5. Truyền bearer access token đúng cách

Theo RFC 6750, cách chuẩn và được ưu tiên cho HTTP API là:

~~~http
GET /api/orders/order-721 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <ACCESS_TOKEN>
Accept: application/json
~~~

Client phải gửi request qua **HTTPS**. Resource server nên chỉ chấp nhận bearer token ở vị trí được cấu hình rõ ràng, thường là `Authorization` header, và từ chối các cách trình nhiều token mơ hồ.

### 5.1. Authorization header không phải nơi hoàn toàn miễn nhiễm rò rỉ

Header giảm nguy cơ token vô tình nằm trong URL, browser history, đường dẫn cache và nhiều dạng log mặc định. Nhưng `Authorization` header **vẫn là bí mật**:

- Reverse proxy có thể được cấu hình để log header.
- Debug logger, HTTP tracing, APM và exception report có thể ghi request headers.
- Trình duyệt có script độc hại/XSS có thể đọc access token nếu ứng dụng đưa token vào JavaScript hoặc kho lưu trữ dễ truy cập.
- Bất cứ client nào gửi header sang sai origin cũng có thể làm lộ credential.

Vì thế cần **redact Authorization ở toàn bộ tầng log**, bảo vệ token storage và chỉ gửi credential đến API đúng origin/audience.

### 5.2. Không đưa token vào URL bằng cách đổi tên header thành query parameter

Những dạng sau đều nên bị từ chối:

~~~text
GET /orders?Authorization=Bearer%20<TOKEN>
GET /orders?access_token=<TOKEN>
GET /orders?jwt=<TOKEN>
GET /orders/<TOKEN>
~~~

Không có tên tham số nào khiến chuỗi trở nên bí mật. API cần **hợp đồng transport** rõ ràng, kiểm tra request tại boundary và không tạo cơ chế fallback "không có header thì lấy token từ query".

### 5.3. Phản hồi lỗi và challenge

Khi request thiếu credential hoặc token không hợp lệ, resource server có thể trả HTTP 401 với `WWW-Authenticate` theo bearer scheme:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders", error="invalid_token"
Cache-Control: no-store
~~~

Nếu thiếu scope hoặc không đủ quyền, kết quả thường là HTTP 403, đôi khi có `insufficient_scope` theo RFC 6750. **Không phản chiếu giá trị token** vào header lỗi, body hoặc log. Chi tiết mã lỗi phải theo contract và ngữ cảnh request.

## 6. Browser app: không đặt token trong query để gọi API

Browser là môi trường đặc biệt vì:

1. JavaScript được phục vụ đến thiết bị người dùng, có thể bị xem và phân tích.
2. XSS có thể khiến code độc hại chạy dưới origin ứng dụng.
3. Các thao tác điều hướng như `<a href>`, `<img src>`, `<iframe src>` và `window.location` sử dụng URL.
4. Cookie, browser history, service worker và các SDK giám sát có cơ chế lưu/quan sát khác nhau.

### 6.1. SPA dùng Authorization Code + PKCE

Trong ứng dụng SPA hoặc mobile phù hợp, client có thể dùng **Authorization Code + PKCE** để lấy access token sau quá trình ủy quyền. Khi gọi API bằng `fetch`, gửi token qua header:

~~~javascript
// Ví dụ minh họa: accessToken phải đến từ luồng được xác minh,
// được lưu/bảo vệ theo kiến trúc, không đưa vào URL.
async function loadOrder(accessToken, orderId) {
  const response = await fetch(
    "https://orders.example.com/api/orders/" + encodeURIComponent(orderId),
    {
      method: "GET",
      headers: {
        Authorization: "Bearer " + accessToken,
        Accept: "application/json"
      }
    }
  );

  if (!response.ok) {
    throw new Error("Không thể đọc đơn hàng");
  }
  return response.json();
}
~~~

Ví dụ tập trung vào **vị trí truyền token**, không trình bày toàn bộ cơ chế OAuth, xử lý refresh, CSRF hoặc xác minh redirect. Không log `accessToken`, không gắn nó vào URL, không tự chuyển token giữa các origin.

**CORS không phải xác thực.** API cho phép một origin gọi bằng browser không có nghĩa mọi request từ origin đó đều được ủy quyền; API vẫn phải xác minh token và quyền resource/action. CORS cũng không ngăn client ngoài trình duyệt gửi HTTP request.

### 6.2. Backend-for-Frontend (BFF) và session cookie

Với ứng dụng web có backend kiểm soát được, một kiến trúc thường hữu ích là **BFF**:

~~~mermaid
sequenceDiagram
    actor U as Người dùng
    participant B as Browser
    participant F as BFF
    participant AS as Authorization Server
    participant API as Orders API
    U->>B: Đăng nhập và mở trang đơn hàng
    B->>F: Request bằng session cookie bảo vệ
    F->>AS: OAuth flow/token exchange theo kiến trúc
    AS-->>F: Access token dành cho Orders API
    F->>API: Authorization: Bearer <ACCESS_TOKEN>
    API-->>F: Dữ liệu đã được phân quyền
    F-->>B: Response nghiệp vụ, không gửi token API vào URL
~~~

Với BFF, browser có thể chỉ giữ **session cookie** được cấu hình `Secure`, `HttpOnly` và `SameSite` thích hợp; BFF giữ access token/refresh token phía server trong kho bảo vệ. Cách này có thể giảm việc JavaScript tiếp xúc với access token.

Tuy nhiên, **cookie cũng là credential** và có rủi ro CSRF, session fixation hoặc session hijacking nếu cấu hình kém. `HttpOnly` hạn chế JavaScript đọc cookie nhưng **không tự ngăn XSS thực hiện hành động bằng phiên người dùng**. BFF vẫn phải bảo vệ phiên, CSRF, cookie scope, logout và authorization ở backend.

### 6.3. Không lấy token từ localStorage để dán vào URL

Ví dụ sai:

~~~javascript
// SAI: token bị đưa lên thanh địa chỉ và nhiều nơi lưu URL.
window.location.href = "/api/export?access_token=" + accessToken;
~~~

Ngay cả khi token nằm trong memory hoặc localStorage trước đó, chuyển nó sang URL vẫn làm tăng bề mặt lộ. Việc chọn memory hay một kho lưu trữ khác phải dựa trên kiến trúc và threat model; **đừng xem localStorage là nơi tự động an toàn cho bearer access token/refresh token**.

## 7. Download file, ảnh, EventSource và WebSocket

Một câu hỏi thực tế: nếu HTML `<a>` hoặc `<img>` không tự thêm `Authorization` header, làm sao tải tài nguyên cần bearer token?

### 7.1. Download file qua fetch + Authorization header

Trong ứng dụng SPA được phép đọc file:

~~~javascript
async function downloadReport(accessToken) {
  const response = await fetch("/api/reports/weekly.pdf", {
    headers: { Authorization: "Bearer " + accessToken }
  });

  if (!response.ok) {
    throw new Error("Không có quyền tải báo cáo");
  }

  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = "weekly.pdf";
  document.body.appendChild(link);

  try {
    link.click();
  } finally {
    link.remove();
    // Trong ứng dụng thật, revoke khi không còn sử dụng object URL.
    URL.revokeObjectURL(objectUrl);
  }
}
~~~

`blob:` object URL ở đây **không chứa bearer access token trong chuỗi URL**; nó tham chiếu đến dữ liệu blob do trình duyệt quản lý. Tuy nhiên, dữ liệu đã tải vẫn nhạy cảm và cần chính sách bảo vệ nội dung, bộ nhớ, quyền chia sẻ và vòng đời URL. Với file lớn, nên cân nhắc giải pháp tải theo luồng hoặc BFF để tránh đưa toàn bộ file vào memory.

### 7.2. Tải bằng link với BFF/session

Nếu ứng dụng dùng BFF, `<a href="/downloads/weekly">` có thể gửi **session cookie** đúng origin. BFF xác thực phiên, chống CSRF khi cần, kiểm tra quyền tài liệu rồi gọi API/storage bằng credential phía server. Access token OAuth không xuất hiện trong link.

Endpoint tải file phải kiểm tra **resource ID, tenant và action** tương ứng; session hợp lệ không đồng nghĩa có quyền tải mọi báo cáo.

### 7.3. Pre-signed URL và link có quyền sử dụng hạn chế

Một số hệ thống lưu trữ cấp **pre-signed URL** để client tải đối tượng trực tiếp. URL đó thường chứa chữ ký/giá trị bí mật đủ để truy cập **một tài nguyên trong một phạm vi và thời hạn cụ thể**. Đây là một dạng **bearer-like capability** — ai có URL có thể sử dụng khả năng đã cấp theo điều kiện của nó.

Pre-signed URL **không tương đương** việc gắn **OAuth access token nhiều quyền** vào query. Dù vậy nó **vẫn là secret nhạy cảm và có nguy cơ rò rỉ URL**.

Khi buộc phải dùng một URL dạng capability:

- Chỉ cấp sau khi **đã xác minh quyền** người yêu cầu trên đối tượng.
- Giới hạn **đúng một tài nguyên**, hành động (ví dụ GET), thời gian sống ngắn và các điều kiện có thể ràng buộc.
- Nếu hạ tầng hỗ trợ, cân nhắc token dùng một lần, giới hạn lượt dùng, kiểm soát tải xuống và revoke.
- Tránh ghi query chứa chữ ký vào log/analytics, tránh đưa liên kết vào email hoặc chat công khai khi dữ liệu nhạy cảm.
- Cấu hình `Referrer-Policy`, cache và chính sách chia sẻ phù hợp; không kỳ vọng những biện pháp đó thay thế giới hạn quyền của URL.

**Không sử dụng pre-signed URL như lý do để chuyển bearer access token OAuth vào query.** Pre-signed link là một khả năng có phạm vi hẹp phải được thiết kế và quản lý rủi ro riêng.

### 7.4. EventSource, SSE và WebSocket

API JavaScript **EventSource** và **WebSocket** của browser không hỗ trợ tùy ý đặt mọi HTTP header trong cùng cách như `fetch`. Đây là lý do một số hệ thống truyền bearer token trong query, nhưng lựa chọn đó làm lộ token.

Các giải pháp nên xem xét:

- Dùng **session cookie bảo vệ** với kết nối cùng origin và kiểm tra origin/CSRF theo mô hình của giao thức.
- Dùng **BFF/reverse proxy** để bổ sung Authorization header ở phía server sau khi xác thực phiên.
- Dùng streaming qua **fetch** khi kiến trúc và trình duyệt hỗ trợ header tùy chỉnh.
- Khi thực sự cần một **one-time connection ticket** riêng, cấp ticket ngẫu nhiên, TTL rất ngắn, ràng buộc đúng client/tài nguyên, dùng một lần, tránh log và có cơ chế thu hồi. Ticket đó vẫn là secret; không phải access token OAuth đa năng và vẫn có rủi ro nếu đặt trong URL.

Không gửi refresh token hoặc access token dài hạn vào URL WebSocket/SSE. Đừng bỏ qua kiểm tra quyền mỗi lần mở kết nối chỉ vì trước đó có một kết nối hợp lệ.

## 8. Authorization Code trong redirect khác bearer access token trong URL

OAuth 2.0 Authorization Code flow thường trả **authorization code** trong query của redirect URI:

~~~http
HTTP/1.1 302 Found
Location: https://app.example.com/callback?code=<AUTHORIZATION_CODE>&state=<OPAQUE_STATE>
~~~

Điều này **không đồng nghĩa** giao thức khuyến nghị gửi **access token** trong query. Authorization code là một grant tạm thời; nó không phải bearer access token dùng trực tiếp để gọi resource server. Luồng an toàn dựa trên các ràng buộc:

1. Code có TTL ngắn và **chỉ được đổi một lần**.
2. AS ràng buộc code với client và redirect URI theo quy tắc OAuth.
3. **PKCE S256** ràng buộc code với `code_verifier`, ngăn bên chỉ chiếm code đổi token khi không có verifier.
4. Client xác minh `state`/liên kết request-response và xử lý issuer để chống mix-up theo profile.
5. Token được trả từ **token endpoint**, không được đặt vào URL callback của Orders API.

**Authorization code vẫn là dữ liệu nhạy cảm** và cần chống log, replay, open redirect và rò rỉ. Client có thể xóa code khỏi thanh địa chỉ sau khi xử lý bằng `history.replaceState` theo kiến trúc ứng dụng, nhưng **xóa khỏi history không thay thế bảo vệ code**. Một số profile hỗ trợ `response_mode=form_post`; phải tuân thủ đặc tả và client registration tương ứng.

### 8.1. Không nhầm OIDC ID token với access token

OIDC ID token có audience thường là client. Nếu một luồng trả ID token cho client, token đó **không được dùng để gọi resource server**. Browser không nên chuyển ID token hoặc refresh token sang URL chỉ vì không có access token trong header.

### 8.2. Legacy implicit flow

Implicit flow từng cho access token đi qua fragment trong redirect từ Authorization Server. Dù fragment không gửi đến server qua HTTP, nó vẫn ở môi trường browser/script và có thể bị lộ. Thiết kế hiện đại nên ưu tiên **Authorization Code + PKCE**, kết hợp bảo vệ callback và phiên theo best current practice.

## 9. Thiết kế resource server: chỉ chấp nhận Bearer header

Một API an toàn không nên có logic kiểu:

~~~text
Nếu Authorization header có token -> xác minh token.
Nếu không -> lấy access_token trong query.
Nếu vẫn không -> lấy jwt trong path.
~~~

Logic fallback như vậy khuyến khích client gửi credential vào URL, tạo đường rò rỉ và có thể gây **credential confusion** khi request mang nhiều token khác nhau.

Thiết kế đề xuất:

~~~text
request
  |
  v
HTTPS / trusted reverse proxy
  |
  v
Extract bearer token từ Authorization header
  |
  v
JWT validation hoặc opaque token introspection
  |
  v
Kiểm tra issuer, audience, thời gian, scope, token type
  |
  v
Authorization theo principal, action, resource và tenant
  |
  v
ALLOW hoặc DENY
~~~

Nếu một request chỉ có `?access_token=...` mà không có Authorization header, API bảo vệ bằng bearer token nên **không coi query token là credential**. Có thể chủ động trả 400 cho request cố truyền token trong URL theo hợp đồng hệ thống, hoặc trả 401 vì thiếu credential hợp lệ; điều quan trọng là **không cấp quyền dựa vào URL**.

### 9.1. Java/Spring Security Resource Server

Trong Spring Security, **`DefaultBearerTokenResolver`** mặc định không cho phép URI query parameter và form body làm nguồn bearer token; có thể cấu hình rõ điều này để làm chủ hợp đồng vận chuyển.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {
    @Bean
    BearerTokenResolver bearerTokenResolver() {
        DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
        resolver.setAllowUriQueryParameter(false);
        resolver.setAllowFormEncodedBodyParameter(false);
        return resolver;
    }

    @Bean
    SecurityFilterChain api(
            HttpSecurity http,
            BearerTokenResolver bearerTokenResolver) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth -> oauth
                .bearerTokenResolver(bearerTokenResolver)
                .jwt(Customizer.withDefaults()));
        return http.build();
    }
}
~~~

Đoạn cấu hình minh họa resource server nhận **JWT access token** qua header. Trong dự án thực tế cần cấu hình issuer đáng tin cậy, **audience validator**, xử lý lỗi và policy quyền trên từng API endpoint. Nếu dùng opaque token, cấu hình introspection phù hợp thay JWT. Các loại import/API cụ thể phụ thuộc phiên bản Spring Security đang sử dụng.

**Không dùng `resolver.setAllowUriQueryParameter(true)` chỉ để xử lý một client không gửi được header.** Hãy sửa kiến trúc client/BFF hoặc thiết kế capability URL có phạm vi riêng nếu thực sự cần.

### 9.2. Không phải cứ tắt resolver query là mọi URL đều sạch

API không chấp nhận query bearer token mới giải quyết **điều kiện cấp quyền**; nếu client vẫn gửi `?access_token=...`, reverse proxy có thể đã log URL trước khi Spring Security từ chối.

Vì vậy phải áp dụng cả:

- Kiểm thử để client **không tạo URL chứa token**.
- Redaction ở CDN/load balancer/API gateway/reverse proxy/access log/application log.
- Cảnh báo request cố gửi query parameter nhạy cảm mà **không ghi giá trị**.
- Review các endpoint legacy, download, WebSocket, redirect và health/debug tools.

### 9.3. Xác minh token còn cần gì?

Không có token trong URL chỉ loại bỏ một đường rò rỉ. Resource server vẫn phải:

- Xác minh JWT đúng chữ ký, thuật toán được phép, issuer, audience, thời gian `iat`/`nbf`/`exp` theo profile, token type và claims cần thiết; hoặc xác minh opaque token qua introspection đáng tin cậy.
- Giới hạn scope và quyền ở cấp action.
- Kiểm tra principal/owner/tenant trên resource cụ thể, không chỉ `authenticated()`.
- Phân biệt user-delegated token với client-credentials token.
- Xử lý thu hồi/trạng thái và cache theo chính sách.

Đừng để một service account trở thành **confused deputy**: dù token gửi qua header, dịch vụ có quyền rộng vẫn không được dùng quyền của mình đáp ứng yêu cầu user trên tài nguyên ngoài phạm vi user.

## 10. Logging, proxy và thiết bị quan sát

### 10.1. Kiểm tra log thực tế

Một access log thường có thể ghi:

~~~text
GET /api/orders/721?access_token=<SECRET> HTTP/1.1
~~~

Ví dụ cấu hình Nginx ở mức nguyên tắc:

~~~nginx
# Minh họa: $uri không bao gồm query string; cần kiểm tra
# mọi field, upstream log và đường dẫn có token trước khi dùng.
log_format api_safe '$remote_addr $request_method $uri $status';
access_log /var/log/nginx/access.log api_safe;
~~~

**Lưu ý:** `$uri` vẫn có thể chứa giá trị nhạy cảm nếu credential bị đặt vào **path**. Đổi `$request_uri` thành `$uri` chỉ loại bỏ query string khỏi **một log field**, không tự đảm bảo mọi log an toàn. Các thành phần CDN, WAF, gateway, framework và APM có thể ghi URI ở nơi khác.

Tốt nhất là **không đưa token vào URL ngay từ đầu**, kết hợp chỉ log tên route đã chuẩn hóa, không log path nhạy cảm và có quy tắc redaction. Nếu cần ghi query params phục vụ chẩn đoán, chỉ ghi **allowlist các tham số không nhạy cảm**; tránh lộ giá trị không biết trước.

### 10.2. Quan sát hệ thống không cần token thô

Có thể log:

~~~text
traceId
requestMethod
routeTemplate=/api/orders/{id}
clientId hoặc principalId theo chính sách bảo vệ dữ liệu
issuerId
audienceId
authDecision=ALLOW hoặc DENY
denialReasonCategory
responseStatus
tokenType và tokenAgeBucket (nếu cần)
~~~

Không log raw `Authorization` header, bearer token, refresh token, API key, authorization code hoặc toàn bộ URL chứa secret. Nếu cần liên kết sự kiện, có thể dùng request ID hoặc token ID đã được xử lý bảo mật; **không tự coi chuỗi jti hoặc hash token là vô hại** nếu nó tạo khả năng theo dõi người dùng hay bị dùng để suy đoán.

### 10.3. Referrer-Policy và Cache-Control là lớp bổ sung

`Referrer-Policy: no-referrer` hoặc chính sách chặt chẽ có thể giảm thông tin URL được gửi trong Referer. `Cache-Control: no-store` có thể hạn chế lưu response nhạy cảm trong cache. Nhưng **không một header nào xóa token khỏi browser history, log đã ghi hoặc liên kết đã được chia sẻ**.

Ngay cả khi cấm cache, URL chứa token vẫn là credential bị đặt sai vị trí. **Đừng dùng những header này để hợp thức hóa truyền bearer access token trong URL.**

## 11. Bị lộ URL chứa bearer token thì xử lý thế nào?

Quy trình ứng cứu cần xem token trong URL là **credential có thể đã bị lộ**, không đơn thuần là lỗi thẩm mỹ của link.

1. **Ngừng tạo và chấp nhận cách truyền sai:** sửa client, endpoint và redirect; triển khai chặn/fail-fast thích hợp.
2. **Xác định loại credential:** access token, refresh token, ID token, API key hay một one-time capability; mỗi loại có phạm vi rủi ro khác.
3. **Đánh giá mức ảnh hưởng:** issuer, client, audience, scope, subject/tenant, thời điểm, TTL, resource đã truy cập, các dịch vụ/log có bản sao.
4. **Thu hồi hoặc giới hạn quyền:** dùng revocation/introspection, session/token version, denylist, khóa key hoặc phương án khả thi theo kiến trúc.
5. **Kiểm tra bản sao:** access log, gateway, CDN, APM, telemetry, email/chat, ticket hỗ trợ, backup/retention và dịch vụ analytics.
6. **Giảm khả năng tái lộ:** redaction, chính sách retention, cảnh báo và test hồi quy.
7. **Điều tra hành vi sử dụng trái phép:** phân biệt request của chủ thể thật và replay bất thường khi có dữ kiện, báo cáo theo chính sách sự cố.

### 11.1. JWT access token bị lộ có thu hồi ngay được không?

**Không nhất thiết.** Với JWT được resource server xác minh offline, token có thể được chấp nhận đến `exp` nếu không có cơ chế thu hồi bổ sung. Đổi mật khẩu hoặc thu hồi refresh token **không tự vô hiệu hóa** access token đã ký trong mọi hệ thống. Nếu cần chặn tức thời, phải có biện pháp trạng thái hoặc policy tại resource server.

Với opaque access token và introspection, trạng thái `active` có thể thay đổi nhanh hơn nhưng phụ thuộc cache. Dù token chỉ còn hạn vài phút, dữ liệu đã truy cập trong khoảng bị lộ không được "thu hồi ngược".

### 11.2. Vì sao sender-constrained token hữu ích nhưng không đủ?

**DPoP** và **mTLS certificate-bound access token** có thể yêu cầu client chứng minh quyền sở hữu khóa/chứng chỉ tương ứng khi dùng token. Bên chỉ đọc được chuỗi token từ log có thể **không đủ khả năng replay** nếu không giữ khóa cần thiết.

Tuy nhiên:

- Không phải mọi API/client đều hỗ trợ sender constraint.
- Nếu cả token **và** khóa của client bị lộ, vẫn có rủi ro.
- URL vẫn có thể tiết lộ thông tin và phát tán credential.
- Chính sách scope, audience, owner/tenant và vòng đời token vẫn phải đúng.

**Sender constraint giảm khả năng dùng lại token bị đánh cắp, không phải sự cho phép đưa token vào URL.**

## 12. Ma trận kiểm thử bảo mật

### 12.1. Kiểm thử transport và parsing

| Kịch bản | Kỳ vọng |
|---|---|
| Bearer access token hợp lệ trong `Authorization` header qua HTTPS | Có thể vượt bước authentication, tiếp tục kiểm tra quyền |
| Chỉ có `?access_token=...`, không có Authorization header | **Không xác thực bằng query**, trả lỗi theo contract |
| Chỉ có token trong path | Không coi path là bearer credential |
| Chỉ có token trong URL fragment của trang browser | API không dựa vào fragment để xác thực |
| Request có cả header và query token khác nhau | Không sử dụng query token; có thể từ chối request mơ hồ theo policy |
| Header Authorization sai bearer scheme hoặc chứa nhiều credential mơ hồ | Từ chối/không chấp nhận theo parser và contract |
| Token đúng chữ ký nhưng sai audience | Từ chối |
| JWT hết hạn hoặc opaque token inactive | Từ chối |
| ID token hoặc refresh token gửi vào API | Từ chối vì sai loại/mục đích |
| Access token có scope đọc nhưng truy cập đối tượng tenant khác | Từ chối theo authorization nghiệp vụ |

### 12.2. Kiểm thử chống rò rỉ ở các tầng

- Trình duyệt điều hướng, refresh, back/forward và bookmark: **không có access token trong thanh địa chỉ/history**.
- Redirect OAuth: chỉ có code/state theo luồng được thiết kế, **không có access token** trong URL callback.
- Server/access log: không chứa `access_token`, raw Authorization hoặc giá trị credential ở query/path.
- Gateway, CDN, WAF, load balancer, APM và crash reports: chỉ có metadata đã redact, không lưu token.
- Referrer: chính sách được đặt phù hợp; không dựa vào chính sách referrer để bù cho token trong URL.
- Download/ảnh: quyền được kiểm tra ở backend/BFF hoặc qua ticket hẹp, không dùng access token đa năng làm URL.
- WebSocket/SSE: không gửi refresh token hoặc bearer token dài hạn trong query.
- Error response: không phản chiếu token trong body, redirect `Location` hoặc header.
- Dev tools, screenshot, support ticket và monitoring export: không vô tình sao chép credential thật.

### 12.3. Kiểm thử khi token đã lộ

| Kịch bản | Điều cần kiểm tra |
|---|---|
| JWT lộ nhưng chưa hết hạn | Chính sách revoke/denylist hoặc giới hạn TTL có hiệu lực đúng thiết kế |
| Opaque token được revoke | Introspection và cache phản ánh trạng thái trong giới hạn đã công bố |
| Refresh token bị lộ | Rotation, reuse detection và ứng cứu token family/grant hoạt động |
| Token bị gửi sang origin không tin cậy | Client từ chối chuyển tiếp credential ngoài allowlist |
| Replay bearer token từ IP/thiết bị khác | Có giám sát, giảm phạm vi quyền, sender constraint nếu hỗ trợ |
| Link tải có quyền hẹp bị chia sẻ | TTL, resource/method binding và kiểm soát truy cập hạn chế tác động |

Các test phải chạy bằng **credential thử nghiệm**, không dùng token production thật trong URL, test report hoặc log CI/CD.

## 13. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| "Đã dùng HTTPS nên token trong query an toàn." | URL vẫn có thể vào log, history, telemetry và liên kết chia sẻ sau khi TLS kết thúc |
| "Chuyển token từ query vào path thì không bị log." | Path cũng thường bị ghi log |
| "Dùng fragment thì không ai đọc được." | JavaScript, browser history, bookmark và analytics có thể truy cập fragment |
| "JWT đã ký nên token lộ cũng không dùng lại được." | Bearer JWT còn hạn có thể replay; chữ ký không ràng buộc người cầm token |
| "Để token sống 60 giây thì có thể đưa vào URL." | Rủi ro vẫn tồn tại trong 60 giây và bản sao URL có thể lưu lâu |
| "Referrer-Policy giải quyết hoàn toàn." | Chỉ giảm một số đường rò qua Referer, không sửa URL/log đã chứa token |
| "Tắt query token ở Spring là xong." | Client có thể vẫn gửi token; proxy/log trước Spring vẫn thấy URL |
| "Pre-signed URL cũng có token nên OAuth access token trong URL không sao." | Pre-signed URL là capability riêng, thường hẹp hơn, nhưng vẫn cần bảo vệ khỏi lộ |
| "CORS bảo vệ token khỏi kẻ ngoài." | CORS không phải cơ chế xác thực và không hạn chế HTTP client ngoài trình duyệt |
| "Có scope đúng thì có quyền xem mọi dữ liệu." | Scope không thay thế ownership, tenant hoặc policy resource/action |
| "Thu hồi refresh token sẽ lập tức chặn mọi JWT access token." | Access token offline có thể còn hiệu lực tới exp nếu thiếu kiểm tra trạng thái |

## 14. Tình huống suy luận

### Tình huống A: frontend muốn mở tab tải PDF

Ứng dụng lưu access token trong memory và muốn đặt `window.open('/pdf?access_token=' + token)` để mở tab tải file.

**Có nên làm không?** Không. Access token sẽ nằm trong URL, có nguy cơ bị lưu ở history/log và bị chia sẻ. Ưu tiên `fetch` với header rồi tải Blob, hoặc BFF/session cookie, hoặc cơ chế tải file có phạm vi hẹp.

### Tình huống B: chỉ log request URI ở proxy

Đội vận hành bật HTTPS và không log Authorization header, nhưng Nginx ghi toàn bộ `$request_uri`. Client gửi token trong query.

**Có an toàn không?** Không. `$request_uri` chứa query string và có thể ghi nguyên token. Cần sửa client và không chấp nhận query token, đồng thời rà soát mọi tầng logging.

### Tình huống C: fragment không đến server

Một SPA đặt access token sau dấu `#` trong callback vì "server sẽ không thấy".

**Có nên dùng không?** Không cho thiết kế OAuth hiện đại. Fragment vẫn ở browser và có thể bị JavaScript đọc; dùng Authorization Code + PKCE và chỉ truyền access token đến API qua header/kiến trúc được bảo vệ.

### Tình huống D: OAuth redirect có code trong query

AS redirect tới `https://app.example.com/callback?code=abc&state=xyz`.

**Điều này có vi phạm quy tắc không đưa bearer access token vào URL không?** Đây là authorization code, không phải access token gửi tới resource server. Luồng hợp lệ phải bảo vệ code bằng PKCE, client/redirect binding, TTL, single-use, state và kiểm tra issuer thích hợp. Code vẫn là dữ liệu nhạy cảm không nên log.

### Tình huống E: pre-signed URL của object storage

Backend cấp một link tải duy nhất, chỉ cho GET đối tượng báo cáo A, hết hạn nhanh và sau khi kiểm tra quyền user.

**Có giống đưa bearer token OAuth toàn quyền vào query không?** Không. Link đó là **capability hẹp cho một tài nguyên**, khác với access token có thể gọi nhiều API. Nhưng URL vẫn nhạy cảm; cần kiểm soát TTL, chia sẻ, logs, referrer và thu hồi khi khả thi.

### Tình huống F: API chỉ kiểm tra header nhưng vẫn lộ token

Spring Resource Server đã từ chối query token, nhưng APM có request URL và các token xuất hiện trong dashboard.

**Điểm thiếu ở đâu?** Hành vi xác thực API đã đúng hơn, nhưng client vẫn tạo URL chứa secret và tầng quan sát vẫn ghi nó. Cần sửa transport từ nguồn, giảm dữ liệu ghi tại ingress/APM và xử lý các bản sao đã lộ.

### Tình huống G: sender-constrained token bị đặt trong URL

Một token DPoP-bound bị đưa vào query. Kẻ tấn công chỉ có token nhưng không có khóa DPoP.

**Đã chấp nhận được cách truyền này chưa?** Không. Ràng buộc khóa có thể giảm replay bởi bên chỉ giữ token, nhưng không loại bỏ các đường rò URL, nguy cơ lộ thêm metadata hoặc việc token/khóa cùng bị đánh cắp. Vẫn truyền access token qua phương thức được thiết kế, thường là Authorization header.

## 15. Tóm tắt quy tắc áp dụng

Trước khi gửi bearer access token, hãy tự kiểm tra:

1. **Token nằm ở đâu?** Chỉ trong header Authorization hoặc kênh được chuẩn/profile cho phép; không nằm trong query, path, fragment hoặc link chia sẻ.
2. **Gửi cho ai?** Đúng HTTPS origin/resource server với audience được cấp, không tự chuyển tiếp qua redirect sang miền khác.
3. **Client giữ token thế nào?** Browser/BFF/backend có cách lưu secret phù hợp; không đưa token vào URL để tải ảnh, PDF hay mở WebSocket.
4. **API xác minh gì?** Chữ ký hoặc introspection, issuer, audience, token type, thời hạn, scope và quyền theo principal/resource/action/tenant.
5. **Hạ tầng ghi gì?** Proxy, CDN, gateway, logs, analytics, APM và báo lỗi không được lưu raw token.
6. **Nếu token lộ thì sao?** Có phương án thu hồi, giới hạn TTL, phát hiện replay, bảo vệ refresh token và ứng cứu sự cố.

**Ghi nhớ:** đưa bearer token vào URL biến credential thành một phần của địa chỉ vốn dễ được lưu, sao chép và quan sát. HTTPS không giải quyết toàn bộ đường rò đó. Hãy dùng **Authorization header qua HTTPS**, bảo vệ token ở client và server, không chấp nhận URL token ở API, và luôn kiểm tra **scope, audience, vòng đời và quyền trên tài nguyên**. Những biện pháp như BFF, cookie phiên an toàn, pre-signed link hẹp hoặc sender-constrained token là công cụ có điều kiện riêng, không phải sự thay thế cho quy tắc cơ bản.

## Tài liệu tham khảo

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): cách truyền bearer access token, rủi ro của URI query parameter, header Authorization và thông báo lỗi.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): khuyến nghị bảo mật OAuth hiện đại, phòng tránh token leakage và các luồng kém an toàn.
- [RFC 7636 — Proof Key for Code Exchange by OAuth Public Clients](https://www.rfc-editor.org/rfc/rfc7636): bảo vệ authorization code với PKCE.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access token, authorization code và vai trò của Authorization Server/resource server.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): issuer, audience, scope và JWT access token.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): xác minh opaque token và trạng thái active.
- [RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP)](https://www.rfc-editor.org/rfc/rfc9449): sender-constrained access token giúp giảm token replay.
- [RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens](https://www.rfc-editor.org/rfc/rfc8705): mTLS và access token ràng buộc chứng chỉ.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID token, authorization code và OIDC.
- [MDN — Referer header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referer): thông tin URL trong Referer và giới hạn fragment.
- [MDN — Referrer-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy): các chính sách giảm dữ liệu URL trong Referer.
- [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): thực hành an toàn cho ứng dụng OAuth 2.0.
- [Spring Security Reference — Bearer Token Resolution](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html): nhận bearer token qua header và cấu hình resolver.
