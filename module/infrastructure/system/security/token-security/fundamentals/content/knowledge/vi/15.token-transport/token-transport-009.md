# CORS và token transport

Một Single-Page Application (SPA) chạy tại `https://app.example.test` muốn gọi Invoice API tại `https://api.example.test`. Ứng dụng có access token hợp lệ và gửi:

~~~http
GET /api/invoices/42 HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Authorization: Bearer <access-token-redacted>
~~~

API có thể xác minh chữ ký JWT, issuer, audience, thời hạn và scope thành công, nhưng **trình duyệt vẫn báo lỗi CORS** nếu response không có header chia sẻ tài nguyên thích hợp. Ngược lại, **API bật CORS cho mọi origin không khiến access token bị lộ một cách tự động**, nhưng có thể mở đường cho trang không đáng tin đọc những response mà trình duyệt gửi kèm credential, đặc biệt khi ứng dụng dùng cookie.

**CORS (Cross-Origin Resource Sharing) là chính sách trình duyệt kiểm soát JavaScript của origin này được phép truy cập response của origin khác đến đâu. CORS không phải giao thức xác thực token, không phải OAuth grant, không phải cơ chế phân quyền và không thể thay thế HTTPS.**

Trong chương **Token transport** của module **Security Token Security Fundamentals**, bài này tập trung vào cách bearer access token, refresh token và cookie/session được vận chuyển giữa browser, Authorization Server (AS), gateway và Resource Server (RS). Ta sẽ phân biệt CORS với CSRF/XSS, cấu hình preflight cho `Authorization` header, nhận diện lỗi chính sách origin, và thiết kế đường truyền phù hợp cho JWT, opaque token, OAuth 2.0/OIDC và token ràng buộc người gửi.

**Sau bài học, bạn cần trả lời được:** Khi nào trình duyệt gửi preflight? Vì sao bật CORS không thay thế kiểm `aud`/`scope`? Khi nào dùng `Access-Control-Allow-Credentials`? Vì sao cookie cần CSRF defense? Và token nào **không nên** xuất hiện trong URL, log hoặc request đến sai API?

## 1. Hiểu đúng origin, site và ranh giới CORS

**Origin** gồm ba thành phần: **scheme + host + port**. Hai URL là cùng origin khi cả ba thành phần bằng nhau (với port mặc định được chuẩn hóa theo URL).

| Trang đang chạy | Đích request | Quan hệ origin |
|---|---|---|
| `https://app.example.test` | `https://app.example.test/api` | **Cùng origin** |
| `https://app.example.test` | `https://api.example.test` | **Khác origin**, dù có thể cùng site |
| `https://app.example.test` | `http://app.example.test` | **Khác origin** vì khác scheme |
| `https://app.example.test` | `https://app.example.test:8443` | **Khác origin** vì khác port |
| `http://localhost:5173` | `http://localhost:8080` | **Khác origin** |

**Same-origin** không giống **same-site**. Khái niệm site (dùng trong chính sách cookie như `SameSite`) thường dựa trên scheme và registrable domain; `app.example.test` và `api.example.test` có thể **khác origin nhưng cùng site**. Một request có thể cần CORS dù cookie `SameSite=Lax` không bị chặn bởi quan hệ same-site. Ngoài ra, việc cookie có thực sự được gửi còn phụ thuộc domain/path, `Secure`, phương thức request, chính sách trình duyệt và `fetch.credentials`.

### Same-Origin Policy và CORS

Trình duyệt áp dụng **Same-Origin Policy** để hạn chế một trang đọc dữ liệu từ origin khác. **CORS** cho phép server đích khai báo **những origin nào được phép đọc response trong ngữ cảnh web**, với một số quy tắc riêng cho request có credential.

~~~text
Browser tab:
  origin = https://app.example.test

JavaScript:
  fetch("https://api.example.test/api/invoices/42")

API:
  Access-Control-Allow-Origin: https://app.example.test

Browser:
  cho phép JavaScript đọc response nếu các điều kiện CORS khác đạt
~~~

Điểm dễ nhầm: **CORS không phải firewall phổ quát chặn mọi request**. Một số cross-origin request có thể **được gửi và làm thay đổi trạng thái server** dù JavaScript của trang gọi không được đọc response. Những request không thuộc loại CORS-safelisted thường phải được **preflight** trước và có thể không được gửi nếu preflight thất bại. Vì vậy không thể dùng CORS thay cho CSRF defense, token validation hoặc authorization tại API.

### CORS có tác dụng với ai?

| Bên gọi | Có bị chính sách CORS của trình duyệt ràng buộc không? |
|---|---|
| `fetch` / `XMLHttpRequest` trong trang web | **Có**, đối với request/response cross-origin |
| Trình duyệt xử lý EventSource/SSE cross-origin | **Có**, theo cơ chế CORS của API đó |
| `curl`, Postman, script Python, ứng dụng backend Java | **Không**: chúng không thực thi Same-Origin Policy của browser |
| Native mobile app | Thông thường **không** chịu browser CORS như web page |
| WebSocket API trong browser | **Không dùng quy trình CORS preflight HTTP thông thường**; server cần kiểm `Origin` và xác thực theo cơ chế riêng |

Vì vậy, API **không được coi request “không có Origin” là đã xác thực**; ngược lại, `Origin` có thể bị client không phải browser tự khai. CORS là lớp phối hợp giữa browser và server, **không phải bằng chứng danh tính**.

## 2. Bearer token đi qua đâu trong một request?

Trong OAuth 2.0, bearer access token thường được gửi bằng `Authorization` header theo RFC 6750:

~~~http
GET /api/invoices/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer <access-token-redacted>
Accept: application/json
~~~

Trình tự xử lý cần tách biệt:

~~~mermaid
flowchart TD
    A["JavaScript ở app.example.test"] --> B{"Khác origin?"}
    B -- "Có" --> C["Browser áp dụng CORS; có thể preflight"]
    B -- "Không" --> D["Gửi request theo chính sách browser"]
    C --> E{"CORS có cho phép request?"}
    E -- "Không" --> X["Browser ngăn request tiếp hoặc chặn JS đọc response"]
    E -- "Có" --> D
    D --> F["API/Gateway nhận token"]
    F --> G{"Token đúng issuer, aud, thời hạn, mục đích?"}
    G -- "Không" --> H["401 / invalid_token"]
    G -- "Có" --> I{"Scope và quyền trên tài nguyên hợp lệ?"}
    I -- "Không" --> J["403/404 theo policy"]
    I -- "Có" --> K["Xử lý nghiệp vụ và trả response"]
    H --> L["Browser vẫn kiểm CORS của response"]
    J --> L
    K --> L
~~~

Sơ đồ rút gọn: quá trình preflight và kiểm response có những điều kiện chi tiết được trình bày bên dưới; API có thể thực thi kiểm token **chỉ trên request thực**, còn OPTIONS preflight không mang bearer token.

**Hai câu hỏi độc lập:**

1. **Browser:** JavaScript thuộc `app.example.test` có được đọc response từ `api.example.test` không?
2. **Resource Server:** Access token này có đúng issuer, audience, token profile, expiry, scope và quyền đối tượng không?

Trả lời **có** ở câu 1 không tự biến câu 2 thành có. Trả lời **có** ở câu 2 cũng không bảo đảm JavaScript được browser đọc response nếu server cấu hình CORS sai.

## 3. Vì sao `Authorization` header thường tạo CORS preflight?

Một cross-origin `fetch` sử dụng `Authorization` header **không thuộc nhóm request chỉ dùng CORS-safelisted headers**. Browser sẽ thực hiện **preflight** để hỏi server có cho phép method và headers của request hay không. Preflight thường là một request `OPTIONS`.

### Bước 1: browser gửi OPTIONS, chưa gửi bearer token của request thật

~~~http
OPTIONS /api/invoices/42 HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Thông điệp nói rằng trang `app.example.test` muốn gửi request `GET` với header `Authorization` đến API. Theo mô hình CORS của Fetch, preflight được gửi **không kèm credentials của request thực**; đừng yêu cầu preflight phải có bearer token hoặc session cookie mới trả CORS headers. Một số đặc điểm trình duyệt/cấu hình mTLS có ngoại lệ triển khai, nên không dựa vào preflight như cơ chế xác thực người dùng.

### Bước 2: API/gateway chấp thuận preflight theo origin/method/header

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET, POST, OPTIONS
Access-Control-Allow-Headers: Authorization, Content-Type
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

- `Access-Control-Allow-Origin`: origin được phép đọc response, phải khớp chính sách.
- `Access-Control-Allow-Methods`: các method mà chính sách CORS cho phép thực hiện theo request.
- `Access-Control-Allow-Headers`: cho phép header `Authorization` và những header cần thiết. **Authorization cần được cho phép rõ ràng**, không dựa vào wildcard để thay nó.
- `Access-Control-Max-Age`: thời gian browser có thể cache kết quả preflight theo quy tắc/giới hạn browser; **không phải TTL access token**.
- `Vary`: giúp các cache HTTP xử lý response theo Origin và các thuộc tính preflight, tránh dùng nhầm kết quả giữa origin/header/method.

**Quan trọng:** `Access-Control-Allow-Headers` do **server** trả, không phải header JavaScript tự thêm vào request để vượt chính sách. Nếu method hoặc header không được cho phép, browser sẽ chặn request thực; backend có thể không nhìn thấy `GET` đó.

### Bước 3: browser gửi GET thật với access token

~~~http
GET /api/invoices/42 HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Authorization: Bearer <access-token-redacted>
Accept: application/json
~~~

Sau khi API xác minh token và quyền trên hóa đơn:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin
Cache-Control: no-store
Content-Type: application/json

{"id":"INV-42","total":125000}
~~~

Response **của request thực** cũng phải có CORS headers phù hợp để trình duyệt cho JavaScript đọc. Chỉ gắn CORS headers trên `OPTIONS` mà quên gắn vào response `200`, `401` hoặc `403` sẽ làm frontend khó xử lý chính xác trạng thái.

### Mã JavaScript phía SPA

~~~javascript
async function loadInvoice(accessToken, invoiceId) {
  const response = await fetch(
    "https://api.example.test/api/invoices/" +
      encodeURIComponent(invoiceId),
    {
      method: "GET",
      headers: {
        Authorization: "Bearer " + accessToken,
        Accept: "application/json"
      },
      credentials: "same-origin"
    }
  );

  if (response.status === 401) {
    throw new Error("Access token không hợp lệ hoặc đã hết hạn");
  }
  if (response.status === 403) {
    throw new Error("Không đủ quyền truy cập tài nguyên");
  }
  if (!response.ok) {
    throw new Error("Yêu cầu API thất bại");
  }
  return response.json();
}
~~~

Với `credentials: "same-origin"`, browser không tự gửi cookie tới **origin khác** trong ví dụ; header `Authorization` do ứng dụng đặt được xử lý riêng. Token phải được lấy qua một luồng OAuth hợp lệ và lưu an toàn; đoạn code **không minh họa** việc cấp phát hoặc nơi lưu token. Việc hiển thị lỗi 401/403 chỉ diễn ra khi response **vượt qua kiểm tra CORS**; nếu CORS thất bại, `fetch` thường reject với lỗi mạng/CORS và JavaScript không đọc được status HTTP thật.

## 4. Các header CORS nào có ý nghĩa với token transport?

| Header | Do bên nào gửi | Ý nghĩa thực tế |
|---|---|---|
| `Origin` | Browser/request | Origin của trang khởi tạo request; **không phải bằng chứng người dùng** |
| `Access-Control-Request-Method` | Browser preflight | Method dự định của request thật |
| `Access-Control-Request-Headers` | Browser preflight | Danh sách non-safelisted headers muốn gửi, ví dụ `authorization,content-type` |
| `Access-Control-Allow-Origin` | Server response | Origin được phép đọc response theo chính sách CORS |
| `Access-Control-Allow-Methods` | Server preflight response | Những method được phép theo CORS |
| `Access-Control-Allow-Headers` | Server preflight response | Những request headers được phép theo CORS |
| `Access-Control-Allow-Credentials` | Server response | Cho phép browser expose response khi cross-origin request dùng credentials mode `include` và chính sách khác hợp lệ |
| `Access-Control-Expose-Headers` | Server response | Những **response headers** không safelisted mà JavaScript được đọc |
| `Access-Control-Max-Age` | Server preflight response | Cache kết quả preflight, không liên quan `exp`/`expires_in` |
| `Vary: Origin` | Server/proxy response | Ngăn HTTP cache dùng nhầm response CORS cho origin khác |

### Có được đặt nhiều origin trong một header không?

Không dùng:

~~~http
Access-Control-Allow-Origin: https://app.example.test, https://admin.example.test
~~~

Đó không phải cách biểu diễn danh sách origin hợp lệ của header này. Nếu có nhiều origin được phép, server cần **xác minh `Origin` chính xác với allowlist** rồi phản hồi **một** origin phù hợp cho từng request, đồng thời gửi `Vary: Origin` nếu response thay đổi theo Origin.

Nếu không có Origin được phép, không phản chiếu origin đó. Đừng dùng `Access-Control-Allow-Origin: null` làm shortcut cho các trang có origin `null`, vì origin `null` có thể phát sinh trong nhiều ngữ cảnh không đáng tin (sandboxed iframe, file, data URL...).

### `Access-Control-Allow-Credentials` có phải luôn cần cho bearer?

**Không.** Với SPA **tự gắn bearer token vào `Authorization` header** nhưng không yêu cầu gửi cookie cross-origin, có thể thiết kế CORS **không bật credentials**. Ngược lại, nếu frontend phải gửi **session cookie cross-origin** bằng `fetch(..., { credentials: "include" })`, server cần các điều kiện CORS dành cho credentialed requests, bao gồm:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Khi dùng credentials mode `include`, **không thể** dùng `Access-Control-Allow-Origin: *` để trình duyệt expose response. Giá trị `*` không được phối hợp với credentialed CORS theo cách này. Ngoài CORS, cookie vẫn phải thỏa `Domain`/`Path`/`Secure`/`SameSite` và hạn chế của browser.

**Không gắn `Access-Control-Allow-Credentials: true` vào mọi endpoint theo thói quen.** Chỉ bật cho các API/origin thực sự cần credentialed cross-origin requests, kết hợp CSRF defense khi browser tự gắn cookie.

### Nếu frontend cần đọc `WWW-Authenticate` hoặc `Retry-After`?

Một số response headers không được JavaScript đọc mặc định. Khi ứng dụng thực sự cần đọc `Retry-After` để backoff sau HTTP 429, hoặc `WWW-Authenticate` để xử lý challenge, API có thể cấu hình allowlist:

~~~http
Access-Control-Expose-Headers: Retry-After, WWW-Authenticate
~~~

Chỉ expose những headers cần thiết; không nhầm **`Access-Control-Expose-Headers` (response headers)** với **`Access-Control-Allow-Headers` (request headers)**. Không dùng expose headers để vô tình đưa token/secret vào một response không đáng tin.

## 5. Bearer Authorization header, cookie session và BFF khác nhau thế nào?

Ba kiến trúc đều có thể được browser gọi, nhưng **cách credential đi theo request** khác nhau.

| Tiêu chí | SPA cầm bearer access token | SPA gọi API bằng cookie | SPA + Backend For Frontend (BFF) |
|---|---|---|---|
| Credential browser sử dụng | JavaScript chủ động đặt header `Authorization` | Cookie được browser đính kèm khi đủ điều kiện | Cookie phiên giữa browser và BFF |
| Access token OAuth ở đâu? | Có trong runtime JavaScript | Tùy thiết kế; không nhất thiết lộ cho JavaScript | Thường giữ phía server/BFF |
| Khi gọi cross-origin | `Authorization` thường tạo preflight | Tùy method/headers; credentialed CORS khi `credentials: include` | Nếu browser–BFF cùng origin thì không cần CORS; khác origin thì vẫn cần |
| Rủi ro nổi bật | XSS đánh cắp token hoặc thao tác với quyền client | CSRF nếu cookie tự đính kèm và thiếu biện pháp phòng vệ; XSS vẫn gây hại | CSRF/session hijack, XSS có thể thao tác qua BFF dù không đọc được access token |
| Phòng vệ bổ sung | XSS defense, token TTL/scope/audience, PKCE và storage policy | Cookie flags, Origin/CSRF token, CORS allowlist, session policy | Session cookie bảo vệ, CSRF defense, BFF giữ token server-side, quyền tại backend |

### Mô hình A — SPA chủ động gửi Bearer token

~~~mermaid
sequenceDiagram
    participant W as SPA app.example.test
    participant AS as Authorization Server
    participant B as Browser CORS engine
    participant API as Invoice API
    W->>AS: Authorization Code + PKCE (qua điều hướng phù hợp)
    AS-->>W: Quy trình hoàn thành; access token theo flow
    W->>B: fetch API với Authorization Bearer
    B->>API: OPTIONS preflight (không mang bearer request)
    API-->>B: Cho phép Origin + Authorization
    B->>API: GET với access token
    API->>API: Kiểm token, aud, scope, quyền đối tượng
    API-->>B: Response + CORS headers
    B-->>W: Cho JS đọc response nếu CORS hợp lệ
~~~

Sơ đồ giản lược các bước tương tác của Authorization Code + PKCE, không phải sequence đầy đủ của OAuth. Access token thường được cấp từ **token endpoint** sau khi client đổi code; cách trao đổi cần tuân thủ browser-based app profile của AS. CORS dành cho request JavaScript đến endpoint phù hợp, **không thay thế việc browser điều hướng đến authorization endpoint để người dùng đăng nhập**.

Nếu có XSS trong SPA, attacker có thể lấy bearer token mà JavaScript truy cập được, hoặc thực hiện request qua ứng dụng. **CORS không sửa XSS** vì script độc hại chạy trong chính một origin đã được allowlist.

### Mô hình B — Browser tự gửi session cookie

~~~javascript
async function readProfileWithCookie() {
  const response = await fetch(
    "https://api.example.test/api/profile",
    { method: "GET", credentials: "include" }
  );
  if (!response.ok) throw new Error("Request failed");
  return response.json();
}
~~~

Browser chỉ gửi cookie nếu chính sách cookie và môi trường cho phép. Server phải cấu hình CORS cho origin đáng tin và credentialed request, nhưng **cần cả cơ chế chống CSRF**, đặc biệt với các method làm thay đổi trạng thái. CORS không bảo đảm kẻ tấn công không thể kích hoạt một request mà browser tự mang cookie.

### Mô hình C — BFF giữ access/refresh token ở server

~~~mermaid
sequenceDiagram
    participant W as Browser app.example.test
    participant F as BFF (session endpoint)
    participant AS as OAuth Authorization Server
    participant API as Invoice API
    W->>F: Cookie phiên + thao tác ứng dụng
    F->>AS: OAuth client flow/refresh khi cần
    AS-->>F: Access token, refresh token nếu được cấp
    Note over F: Token giữ server-side; không trả raw token cho JS
    F->>API: Authorization: Bearer access token
    API->>API: Xác minh token và quyền đối tượng
    API-->>F: Kết quả
    F-->>W: Dữ liệu cần thiết, không kèm raw token
~~~

Khi browser và BFF có cùng origin, browser không cần CORS để gọi BFF, giúp đơn giản hóa chính sách. BFF nên quản lý session bằng cookie `Secure`, `HttpOnly`, `SameSite` phù hợp, kết hợp CSRF token/kiểm Origin và bảo vệ XSS theo threat model. Dịch vụ BFF còn phải cất refresh token an toàn, triển khai rotation/single-flight và không forward bearer token sai audience xuống API.

**HttpOnly** ngăn JavaScript đọc trực tiếp cookie, **không** ngăn hoàn toàn JavaScript độc hại thực hiện các yêu cầu có cookie qua chính trình duyệt. CORS cũng không tự bảo vệ session khỏi XSS.

## 6. CORS khác CSRF và XSS thế nào?

| Vấn đề | Kẻ tấn công muốn gì? | CORS bảo vệ được đến đâu? | Phòng vệ chính |
|---|---|---|---|
| **CORS đọc response trái phép** | Website khác đọc dữ liệu từ API trong trình duyệt | Có, khi origin policy được cấu hình đúng | CORS allowlist chính xác, credential policy |
| **CSRF** | Khiến browser của nạn nhân gửi request tự mang cookie làm thay đổi trạng thái | **Không đủ**, vì nhiều request có thể được gửi dù response không đọc được | CSRF token, kiểm Origin, SameSite phù hợp, không có state-changing GET |
| **XSS** | Chạy JavaScript độc hại trong origin của ứng dụng | **Không**, vì script chạy từ origin hợp lệ | Output encoding, tránh HTML injection, CSP lớp bổ trợ, review dependency |
| **Bearer token theft** | Lấy token rồi gọi API từ công cụ/host khác | **Không**, vì `curl`/backend không chịu browser CORS | Chặn lộ token, TTL ngắn, scope/aud tối thiểu, DPoP/mTLS khi phù hợp |
| **Broken object-level authorization** | Dùng token đúng nhưng xem dữ liệu tenant khác | **Không** | Kiểm ownership/tenant/role tại RS |
| **Token substitution** | Dùng token dành cho API A tại API B | **Không** | Kiểm issuer, token type/profile, audience, scope |

### Vì sao “đã có CORS thì không cần CSRF” là sai?

Ví dụ một website ác ý chèn form tạo giao dịch đến API dùng session cookie. Một request gửi qua biểu mẫu HTML có thể được browser gửi **mà không cần CORS preflight kiểu `Authorization`**, dù website ác ý không được đọc response. Nếu server chỉ kiểm cookie và không có phòng vệ CSRF, hành động thay đổi trạng thái có thể thành công.

Cookie `SameSite` giúp giảm một số đường CSRF cross-site nhưng không phải điều kiện đủ trong mọi hệ thống, đặc biệt khi có **subdomain cùng site nhưng không cùng mức tin cậy**. Cần kiểm Origin cho thao tác nhạy cảm, CSRF token/biện pháp tương đương, HTTP method semantics và xác thực phiên đúng cách.

### Vì sao “chỉ nhận Authorization header thì không cần lo gì thêm” cũng sai?

Một API thuần bearer do JavaScript chủ động thêm header thường **ít bị CSRF truyền thống bằng cookie tự gửi hơn**, nhưng vẫn chịu:

- **XSS** trong SPA lấy token hoặc dùng token thực hiện thao tác.
- **Bearer token bị log/đánh cắp** rồi sử dụng ngoài browser.
- **CORS cấu hình sai** gây lỗi frontend hoặc lộ dữ liệu của những endpoint khác có cookie.
- **Sai issuer/audience/scope/owner** nếu backend chỉ nhìn thấy header `Authorization` rồi mặc định tin.
- **Cookie hoặc HTTP auth được thêm vào cùng API** về sau làm threat model CSRF thay đổi.

Không tắt CSRF protection trên toàn hệ thống chỉ vì **một** endpoint dùng bearer; phải phân loại từng security filter chain và loại credential được trình duyệt tự gửi.

## 7. Cấu hình CORS sai nguy hiểm như thế nào?

### Lỗi A — Phản chiếu `Origin` tùy ý và bật credentials

Ví dụ **không an toàn**:

~~~text
request Origin = https://attacker.example

server response:
  Access-Control-Allow-Origin: https://attacker.example
  Access-Control-Allow-Credentials: true
~~~

Nếu API sử dụng cookie và browser thực sự đính kèm cookie hợp lệ, website ác ý có thể được phép **đọc response gắn với phiên của nạn nhân**. Rủi ro phụ thuộc `SameSite`, chính sách cookie và khả năng gửi credential cụ thể, nhưng việc phản chiếu Origin không kiểm soát là lỗi thiết kế nghiêm trọng.

**Sửa:** Dùng allowlist origin được kiểm soát, không lấy trực tiếp từ input chưa xác minh. Chỉ bật `Access-Control-Allow-Credentials: true` ở những endpoint/nguồn cần credentialed requests thực sự.

### Lỗi B — Cho tất cả origin nhưng tưởng đó là authentication

~~~http
Access-Control-Allow-Origin: *
~~~

Wildcard `*` có thể có chỗ dùng ở **resource công khai không có credential**, nhưng **không** là cơ chế xác thực. Nó không cho phép cross-origin **credentialed response** theo quy tắc browser và cũng không tạo ra quyền sử dụng access token. Với API yêu cầu bearer, backend vẫn cần xác minh token như cũ. Không dùng wildcard như mẹo chữa lỗi CORS khi chưa xác định rõ token được truyền bằng cơ chế nào.

### Lỗi C — Allowlist origin bằng so khớp chuỗi yếu

~~~text
ALLOWED = "https://app.example.test"

BAD CHECK:
  origin.includes("app.example.test")
  origin.endsWith("example.test")  // có thể nhận evil-example.test

BETTER:
  parsed origin khớp chính xác allowlist đã định nghĩa
~~~

Cũng cần cân nhắc subdomain takeover, DNS và các origin phát triển không được tin. Origin `https://app.example.test.evil.invalid` **không phải** `https://app.example.test`. Không thêm mọi `localhost` hoặc `*.example.test` vào allowlist production nếu không có chính sách rõ.

### Lỗi D — Preflight bị security middleware từ chối 401

Browser gửi `OPTIONS` không kèm bearer token request thật. Nếu middleware yêu cầu bearer trước khi xử lý CORS, preflight bị `401`, khiến `GET` thật không được gửi. **Sửa:** Cho CORS/preflight chạy đúng thứ tự trước các rule yêu cầu xác thực, nhưng **không** mở `GET/POST` nghiệp vụ cho anonymous chỉ để preflight đi qua.

### Lỗi E — Chỉ thêm CORS vào response 200

API trả `401` khi token hết hạn nhưng quên `Access-Control-Allow-Origin` trên lỗi. Browser che status và response khiến frontend nhầm thành lỗi kết nối. **Sửa:** Bảo đảm CORS headers thích hợp cho cả phản hồi thành công và lỗi, kể cả ở gateway và reverse proxy chịu trách nhiệm trả lỗi.

### Lỗi F — Cache phản hồi CORS qua origin

CDN/proxy cache response có `Access-Control-Allow-Origin` động nhưng bỏ `Vary: Origin`. Kết quả có thể gây lỗi origin hoặc cấp sai quyền đọc phản hồi ở browser; riêng dữ liệu cá nhân còn cần `Cache-Control` theo chính sách. **Sửa:** cache key/Vary đúng, không cache response chứa token hoặc dữ liệu riêng tư một cách vô ý.

## 8. OAuth 2.0/OIDC token endpoint có cần CORS?

**Tùy loại client và cách gọi.** Cần phân biệt **authorization endpoint** (trình duyệt điều hướng để người dùng xác thực/đồng ý) với **token endpoint** (đổi authorization code hoặc refresh token để nhận token).

### SPA public client với Authorization Code + PKCE

Một SPA hoạt động hoàn toàn trong browser có thể cần gửi `fetch` từ origin ứng dụng tới **token endpoint của AS**. Nếu token endpoint khác origin, AS phải **có chính sách CORS phù hợp với client browser được phép**. AS vẫn phải kiểm:

- Client ID và redirect URI theo registration.
- Authorization code đã cấp, còn hạn, không dùng lại; PKCE `code_verifier` đúng.
- Scope và resource/audience được phép theo grant/chính sách.
- Token response đúng loại, thời hạn và cơ chế bảo vệ đối với refresh token nếu có.

**CORS tại token endpoint không thay thế PKCE**, không cho SPA quyền giữ một confidential client secret an toàn, và không xác định client có được cấp refresh token hay không. Public browser client không có nơi tin cậy để giữ một secret dùng chung mà attacker không thể lấy từ mã.

### Tại authorization endpoint

Thông thường, browser **điều hướng** tới AS để người dùng đăng nhập, thay vì gọi `/authorize` bằng `fetch` rồi đọc HTML đăng nhập bằng JavaScript của một origin khác. Việc bật CORS cho authorization endpoint **không bắt buộc** để thực hiện redirect-based login và có thể làm lẫn lộn boundary đăng nhập. Phải dùng đúng flow AS hỗ trợ.

### Với BFF/confidential backend

BFF hoặc backend gọi token endpoint **server-to-server**. Lúc đó **browser CORS không áp dụng** cho cuộc gọi backend–AS; phải bảo vệ client authentication, TLS, PKCE khi flow đòi, secret/khóa và phạm vi grant. Không bật CORS ở AS chỉ để “cho server Java gọi được token endpoint”.

### Trả token cho browser an toàn đến đâu?

Phản hồi token thường chứa credential và cần `Cache-Control: no-store` (cùng header cache phù hợp theo profile). Không đặt access/refresh token trong:

- URL query hoặc fragment tự thiết kế để chuyển tiếp giữa các domain.
- Redirect URL của ứng dụng nếu flow/profile không yêu cầu; tránh rò qua history, referrer, analytics, log.
- `Access-Control-Expose-Headers` mở rộng một cách vô ý cho những response header chứa secret.
- Log, tracing, error telemetry, crash dump hoặc HTML/console không cần thiết.

AS có quyền quyết định có hỗ trợ CORS tại token endpoint không; nếu không hỗ trợ browser calls, cần chọn **luồng/kiến trúc thích hợp**, ví dụ BFF, thay vì dùng proxy tùy tiện để che điều kiện bảo mật của AS.

## 9. HTTPS, gateway, redirect và các điểm có thể làm lộ token

CORS kiểm **origin của JavaScript**, còn TLS kiểm **bảo mật kênh truyền**. Một API CORS cấu hình hoàn hảo nhưng cho phép token qua HTTP plaintext vẫn có rủi ro bị nghe lén hoặc sửa đổi trên đường truyền.

### Các lớp bảo vệ khi vận chuyển

1. **Dùng HTTPS/TLS** từ browser/client tới endpoint đáng tin; bảo đảm chứng chỉ và hostname được kiểm đúng.
2. **Bảo vệ gateway–backend** theo trust boundary: mTLS/service identity hoặc kênh mạng được thiết kế có bảo mật, không mặc định “mạng nội bộ là an toàn”.
3. **Không đưa bearer/refresh token vào URL:** URL thường đi vào proxy/CDN log, browser history, bookmark, analytics hoặc referrer.
4. **Che header `Authorization` và token response:** audit metadata như request ID/status/scope class khi cần, không ghi nguyên credential.
5. **Không relay token sai audience:** proxy đổi host/path không làm claim `aud` của JWT thay đổi; downstream API phải kiểm token dành cho mình.
6. **Hạn chế redirect qua origin khác:** không thiết kế gửi token đến endpoint có thể chuyển hướng sang host ngoài trust boundary và trông đợi mọi client giữ/loại bỏ `Authorization` giống nhau.
7. **Cache an toàn:** dùng `Cache-Control: no-store` cho token response và dữ liệu nhạy cảm theo policy; xử lý `Vary: Origin` khi response CORS thay đổi.
8. **Không tin `X-Forwarded-Host`/`Origin` từ nguồn lạ** để suy audience, xây redirect URI hoặc định nghĩa caller; chỉ dùng proxy metadata đã được thiết lập và kiểm nguồn.

### Redirect cross-origin và header Authorization

Trong Fetch, request được redirect sang origin khác có các quy tắc bảo vệ `Authorization`; các client HTTP/proxy khác nhau có thể xử lý redirect khác. **Đừng dựa vào redirect để vận chuyển bearer token giữa các dịch vụ.** Client nên gọi đúng endpoint được cấu hình tin cậy và có chính sách redirect rõ ràng; AS/RS không nên chuyển token sang một origin không được tin.

**Chữ ký JWT bảo vệ tính toàn vẹn token, không mã hóa payload:** ai đọc được JWT dạng JWS vẫn có thể giải mã phần claims để xem dữ liệu không được mã hóa. Không nhét dữ liệu nhạy cảm không cần thiết vào payload chỉ vì request đi qua HTTPS.

## 10. Spring Security: cấu hình CORS cho API dùng Bearer token

Ví dụ Java/Spring Security 6.x dưới đây dùng một allowlist origin **cố định** cho Invoice API. Giả định browser gắn access token vào `Authorization` và **không gửi cross-origin session cookie**; chính sách `allowCredentials=false` phù hợp với giả định đó.

~~~java
@Configuration
@EnableWebSecurity
public class InvoiceApiSecurityConfig {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.test"));
        cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
        cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
        cors.setExposedHeaders(List.of("Retry-After", "WWW-Authenticate"));
        cors.setAllowCredentials(false);
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        http.cors(Customizer.withDefaults());
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/invoices/**")
                .hasAuthority("SCOPE_invoice:read")
            .anyRequest().denyAll()
        );
        http.oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()));
        return http.build();
    }
}
~~~

Đây là **khung minh họa**, chưa phải cấu hình production đầy đủ. Các imports/dependencies và cấu hình `JwtDecoder` phải được bổ sung; API phải xác minh **issuer, chữ ký/khóa tin cậy, audience `invoice-api`, thời gian và token type/profile**, không chỉ scope. Dữ liệu hóa đơn cần kiểm owner/tenant riêng tại service. Một số header/behavior có thể do gateway đảm nhận; phải tránh nhiều lớp CORS trả header chồng chéo hoặc mâu thuẫn.

**Điểm cần lưu ý:**

- `http.cors(...)` giúp xử lý CORS theo cơ chế Spring trước những kiểm soát bảo mật khiến preflight thất bại; không cần mở endpoint nghiệp vụ cho mọi origin.
- `setAllowedOrigins` nhận **origin chính xác**, không phải danh sách chuỗi con hay wildcard tùy ý.
- `setAllowedHeaders` cần `Authorization` cho bearer request; thêm `DPoP` nếu endpoint thực sự dùng DPoP proof.
- `setAllowCredentials(false)` dựa trên việc không dùng cookie cross-origin; nếu thiết kế thay đổi sang cookie, phải thay đổi cả **CORS, session và CSRF defense**, không chỉ đổi boolean.
- Ví dụ chỉ cấp quyền **GET**. Với POST/PUT/PATCH/DELETE cần rule scope/CSRF/business policy tương ứng, không dùng `anyRequest().permitAll()` để chữa lỗi frontend.
- Nếu cấu hình Spring Security còn xử lý CSRF cho endpoint state-changing, cần đánh giá security filter chain thực tế; **không blanket-disable CSRF** nếu có bất kỳ đường nào dùng cookie hoặc credential browser tự gửi.
- Backend có thể được gọi bằng `curl` không có Origin; nó vẫn phải kiểm token. CORS không phải authorization layer cho client không phải browser.

### Nếu frontend chuyển sang session cookie cross-origin

Cấu hình `allowCredentials=true` và origin cố định chỉ là **một phần**. Browser còn phải gọi với `credentials: "include"`, cookie phải có các thuộc tính thích hợp và API/BFF cần phòng chống **CSRF**. Không cho phép wildcard origin với credentialed responses. Khi có cả bearer và cookie trong cùng service, hãy phân loại filter chain/endpoints rõ ràng, tránh vô tình cho một loại credential đi vòng qua chính sách của loại kia.

## 11. DPoP/mTLS và những API transport khác

### DPoP: không chỉ là một header tùy ý

**DPoP (RFC 9449)** cho phép client tạo proof JWT ký bằng khóa riêng, ràng buộc việc sử dụng access token với phương thức/URI HTTP và thông tin token theo profile. Một request đến RS có thể có:

~~~http
GET /api/invoices/42 HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Authorization: DPoP <sender-bound-access-token-redacted>
DPoP: <signed-proof-jwt-redacted>
~~~

Với request từ browser cross-origin, header `DPoP` cũng cần được policy CORS cho phép:

~~~http
Access-Control-Allow-Headers: Authorization, DPoP, Content-Type
~~~

**Cho phép header DPoP trong CORS không có nghĩa RS đã xác minh proof.** RS còn phải kiểm chữ ký proof, public key/binding tới access token, `htm`, `htu`, `iat`, `ath`, và cơ chế chống replay/nonce theo chuẩn. Nếu proxy rewrite URL, phải thiết kế đúng **URI bên ngoài đã được xác thực**; không tin header forwarded do client tự khai.

DPoP giảm rủi ro khi attacker **chỉ đánh cắp chuỗi token**; nếu attacker có thể dùng private key hoặc chạy code độc hại trong chính browser client, vẫn có nguy cơ. CORS không ngăn được XSS có quyền ký proof trong một origin hợp lệ.

### mTLS: chứng chỉ ở hop nào?

Với **certificate-bound access token** (RFC 8705), RS phải kiểm token ràng buộc với chứng chỉ client theo profile. Khi gateway kết thúc mTLS và mở kết nối mới đến backend bằng chứng chỉ của gateway, **certificate của kết nối backend không tự chứng minh chứng chỉ client ban đầu**. Phải xác định điểm thực hiện token binding check và cơ chế chuyển ngữ cảnh downstream đáng tin.

**CORS và mTLS giải quyết hai vấn đề khác nhau:** CORS hạn chế việc JavaScript cross-origin đọc response; mTLS có thể xác thực kênh/khóa client và ràng buộc token ở tầng vận chuyển. Một cái không thay cái kia.

### WebSocket: không kỳ vọng preflight CORS giống Fetch

Trình duyệt dùng `WebSocket` API có handshake HTTP và header `Origin`, nhưng **không theo cùng cơ chế CORS preflight `OPTIONS` của `fetch`**. Server WebSocket phải:

- Xác thực phiên/token theo thiết kế, kiểm origin cho browser clients như **lớp bảo vệ bổ sung**.
- Không coi `Origin` là danh tính (client ngoài browser có thể tự đặt).
- Tránh truyền access token dài hạn trong URL/query vì URL có thể bị ghi log.
- Cân nhắc session cookie có CSRF/cross-site WebSocket hijacking defense, hoặc cơ chế ticket **ngắn hạn, một lần, ràng buộc ngữ cảnh** khi phù hợp.
- Không giả định browser WebSocket constructor cho phép đặt `Authorization` header tùy ý như `fetch`; giao thức xác thực cần được thiết kế riêng.

### Server-Sent Events (SSE)

API `EventSource` gốc của browser không cho JavaScript tự cấu hình tùy ý `Authorization` header như `fetch`. Với SSE cross-origin, cần CORS phù hợp; nếu dùng cookie thì cân nhắc `withCredentials`/`credentials` theo API và CSRF/session policy. Có thể dùng BFF cùng origin hoặc stream qua `fetch` nếu cần header, nhưng không nên đưa bearer token vào query URL chỉ để “đơn giản hóa” SSE.

## 12. Cách chẩn đoán lỗi CORS mà không phá bảo mật

Khi frontend thấy `TypeError: Failed to fetch` hoặc thông báo CORS, không nên ngay lập tức thêm `Access-Control-Allow-Origin: *`. Hãy kiểm từng chặng:

1. **Xác định origin thật:** scheme, host, port của trang; không nhầm URL backend nội bộ với public origin.
2. **Quan sát Network tab:** browser có gửi `OPTIONS` không, URL/method/header preflight là gì, có response không?
3. **Kiểm preflight response:** `Access-Control-Allow-Origin` có khớp origin, `Allow-Methods` và `Allow-Headers` có cho phép `Authorization`/`Content-Type`/`DPoP` khi cần không?
4. **Kiểm request thật:** nếu OPTIONS qua, API có nhận GET/POST với bearer/cookie đúng cấu hình không?
5. **Kiểm response thật và lỗi:** response `200`, `401`, `403`, `429` và lỗi gateway có headers CORS phù hợp không?
6. **Kiểm credential mode:** SPA gửi Bearer header hay dựa cookie? Nếu cookie, `credentials: include`, origin cụ thể, `ACAC: true` và cookie flags có phù hợp không?
7. **Kiểm gateway/CDN/cache:** header CORS có bị mất/chồng lặp, `Vary: Origin` có đúng, redirect sang origin khác có làm request thay đổi không?
8. **Tách lỗi token khỏi lỗi CORS:** Nếu API trả 401 vì `aud` sai, **không sửa bằng cách mở rộng CORS**; sửa token/profile/AS và giữ API fail closed.
9. **Kiểm trình duyệt thật:** `curl` hoặc Postman có thể xem response nhưng **không mô phỏng cơ chế enforcement của browser**.
10. **Giữ bí mật khi debug:** không paste access token/refresh token vào issue, ảnh chụp Network, console hay công cụ bên thứ ba.

### Ba tình huống dễ chẩn đoán nhầm

| Quan sát | Nguyên nhân có thể | Cách kiểm đúng |
|---|---|---|
| `OPTIONS` trả 401, GET không xuất hiện | Middleware auth chặn preflight | Cho CORS filter xử lý preflight trước auth, không mở GET/POST |
| GET có response 401 trong server logs, SPA chỉ thấy CORS error | Thiếu CORS headers trên error response | Sửa error/gateway CORS; **vẫn giữ 401** cho token sai |
| GET 200 trong Postman, SPA fail CORS | Postman không thực thi browser CORS; Origin/header khác | Thử từ browser đúng origin, kiểm preflight và response |

Nếu muốn thử preflight bằng command-line trong môi trường phát triển:

~~~bash
curl -i -X OPTIONS 'https://api.example.test/api/invoices/42' \
  -H 'Origin: https://app.example.test' \
  -H 'Access-Control-Request-Method: GET' \
  -H 'Access-Control-Request-Headers: authorization'
~~~

Lệnh này hữu ích để **xem các header server trả**, không chứng minh browser chắc chắn cho phép request: còn các quy tắc Fetch, credential mode, redirect, cache và chính sách trình duyệt thực tế. Không đưa bearer token thật vào lệnh dùng để chia sẻ log.

## 13. Ma trận kiểm thử cho CORS và token transport

Giả sử hệ thống có:

~~~text
SPA allowed:    https://app.example.test
SPA untrusted:  https://attacker.invalid
Invoice API:    https://api.example.test
Issuer:         https://auth.example.test
JWT audience:   invoice-api
Required scope: invoice:read
~~~

| Kịch bản | Thiết lập | Kết quả mong đợi |
|---|---|---|
| **Bearer CORS đúng** | SPA allowed gửi GET với `Authorization` | Browser preflight được phép; API xác minh token, JS đọc dữ liệu nếu đúng quyền |
| **Origin không tin cậy** | Script từ `attacker.invalid` gọi Invoice API | Browser không được đọc response nếu CORS không cho phép; API vẫn kiểm token độc lập |
| **Thiếu `Authorization` trong Allow-Headers** | Preflight yêu cầu `authorization` | Browser chặn request thực; sửa policy header chứ không tắt auth |
| **Preflight bị 401** | API auth filter bắt cả `OPTIONS` | Cấu hình thứ tự CORS/preflight đúng, GET vẫn đòi bearer |
| **Error thiếu CORS** | Token hết hạn, API trả 401 nhưng thiếu ACAO | Bổ sung CORS trên response 401; không biến lỗi thành 200 |
| **Token sai issuer** | Bearer JWT của AS lạ | Resource Server từ chối 401 dù CORS hợp lệ |
| **Token sai audience** | `aud=profile-api` gọi Invoice API | 401, không dùng CORS để bỏ kiểm audience |
| **Token thiếu scope** | `aud=invoice-api`, chỉ có `invoice:write` | 403 nếu endpoint yêu cầu `invoice:read` |
| **Sai tenant/owner** | Token hợp lệ yêu cầu hóa đơn tenant khác | 403/404 theo chính sách, không rò dữ liệu |
| **Credentialed cookie với wildcard origin** | `credentials: include` và ACAO `*` | Browser không expose credentialed response |
| **Cookie + reflect origin tùy ý** | Request từ website ác ý, server trả đúng Origin và ACAC true | Test phải phát hiện cấu hình nguy hiểm, chặn origin không được phép |
| **CSRF với cookie** | Cross-site form gây POST đổi trạng thái | API chống CSRF độc lập với việc browser đọc response |
| **XSS trên SPA allowed** | Script độc hại chạy trong origin được phép | CORS không chặn XSS; các lớp XSS/token protection phải hoạt động |
| **Backend/curl từ origin bất kỳ** | Non-browser gửi bearer token | Không được coi Origin/CORS là authentication; API kiểm token |
| **CORS cache** | Response theo Origin được cache ở CDN | Cache key/Vary đúng, không lộ dữ liệu giữa người dùng/origin |
| **Token response ở AS** | SPA public client đổi code bằng PKCE qua fetch cross-origin | AS CORS theo client origin và vẫn kiểm PKCE/grant; token response no-store |
| **DPoP proof** | Header `DPoP` gửi qua browser cross-origin | CORS cho phép header đúng; RS **vẫn phải** kiểm proof và token binding |
| **mTLS qua proxy** | Gateway kết thúc TLS client trước backend | Không coi certificate backend hop là bằng chứng client gốc nếu chưa có contract |
| **WebSocket cookie session** | Trang không tin cậy thử mở socket | Server kiểm Origin, session và chống cross-site hijacking; không trông chờ OPTIONS CORS |
| **SSE cross-origin** | Native EventSource cần auth | Có phương án session/BFF/stream phù hợp, không đẩy token dài hạn vào query |
| **Token lộ trong log** | Kiểm proxy, APM, error report | Không có bearer/refresh token nguyên bản |

## 14. Bài tập tình huống: từ lỗi CORS đến thiết kế an toàn

Đội phát triển có hệ thống:

~~~text
Frontend:  https://app.example.test
API:       https://api.example.test
AS:        https://login.example.test

API security:
  aud   = invoice-api
  scope = invoice:read
  token = JWT Bearer, TTL 15 phút
~~~

Frontend gửi `fetch` với `Authorization: Bearer ...`. Chrome báo lỗi preflight; server log ghi `OPTIONS /api/invoices/42 -> 401`. Một developer đề xuất sửa bằng cách cho mọi origin, bật `Access-Control-Allow-Credentials: true` và tắt Spring Security trên `/api/**`.

**Câu 1: Vấn đề gốc là gì?**

**Preflight `OPTIONS` bị lớp xác thực từ chối**, dù preflight không mang bearer token của request thật. CORS handler cần được chạy đúng vị trí, có allowlist origin, method và `Authorization` header. Không phải access token sai chỉ vì preflight bị 401.

**Câu 2: Có nên tắt auth cho `/api/**` không?**

**Không.** Chỉ xử lý `OPTIONS` theo policy CORS; các request `GET/POST` thực vẫn cần JWT/opaque validation, audience, scope và quyền hóa đơn. Cho phép tất cả API anonymous sẽ tạo lỗ hổng lớn hơn lỗi frontend ban đầu.

**Câu 3: Có cần `Access-Control-Allow-Credentials: true` không?**

Nếu SPA chỉ **chủ động gửi bearer access token** bằng `Authorization` và không dùng cross-origin session cookie, thường **không cần**. Nếu thêm cookie, phải xem lại credentials mode, cookie policy và CSRF. Không bật ACAC chỉ vì có chữ “token”.

**Câu 4: Vì sao không thể sửa bằng `Access-Control-Allow-Origin: *`?**

Wildcard không giải quyết đúng bài toán preflight thiếu `Authorization` hoặc auth middleware chặn `OPTIONS`, không xác thực token, và không hợp lệ cho credentialed CORS responses. Dùng allowlist origin đáng tin thay vì mở rộng vô điều kiện.

**Câu 5: Sau khi sửa CORS, API trả 401 cho token `aud=profile-api`. Có cần cho qua vì người dùng đã đăng nhập không?**

**Không.** Token không dành cho Invoice API; phải xin access token đúng resource/audience từ AS theo grant, không bỏ kiểm audience.

**Câu 6: Một trang attacker gửi form POST với cookie của người dùng; CORS chặn nó đọc response. Tài khoản đã an toàn chưa?**

**Chưa.** Nếu browser đính kèm cookie và API không kiểm CSRF, request có thể gây thay đổi trạng thái dù response không đọc được. Cần CSRF defense và kiểm nghiệp vụ.

**Câu 7: Nếu access token bị lộ trong browser console, bật CORS chỉ cho app origin có chặn attacker dùng `curl` không?**

**Không.** `curl` không áp dụng CORS. Cần xử lý lộ token, thu hồi khi có thể, giới hạn TTL/scope/audience và bảo vệ API; cân nhắc DPoP/mTLS theo rủi ro.

## 15. Checklist trước khi triển khai CORS và token transport

1. **Xác định origin thật:** SPA, BFF, API, AS có scheme/host/port nào? Cái nào khác origin nhưng cùng site?
2. **Chọn mô hình credential:** JavaScript chủ động gửi Bearer, browser tự gửi cookie, hay BFF giữ token server-side? Có trộn nhiều cơ chế trên cùng endpoint không?
3. **Cấu hình preflight:** `OPTIONS`, `Access-Control-Request-Method` và `Access-Control-Request-Headers` được xử lý **trước auth phù hợp**, không đòi bearer?
4. **Giới hạn origin:** Có allowlist chính xác, không phản chiếu origin bừa bãi, không tin origin `null` hoặc wildcard ở endpoint nhạy cảm?
5. **Đúng request/response headers:** `Authorization`, `Content-Type`, `DPoP` nếu cần; `Access-Control-Allow-Origin` trên cả thành công và lỗi; `Vary: Origin` đúng?
6. **Credential policy rõ:** Có dùng `credentials: include` không? Nếu có, ACAC đúng, cookie `Secure`/`HttpOnly`/`SameSite` phù hợp và có chống CSRF?
7. **Không nhầm CORS với authentication:** Resource Server vẫn kiểm `iss`, chữ ký/introspection, `aud`, `exp`, token type/profile, scope, tenant và owner?
8. **Không nhầm CORS với XSS/CSRF:** Có output encoding, CSP lớp bổ trợ, Origin/CSRF-token policy và state-changing methods an toàn?
9. **Chọn OAuth flow đúng:** SPA public client dùng Authorization Code + PKCE theo AS; token endpoint CORS nếu browser thực sự cần; không đặt client secret vào SPA?
10. **Bảo vệ token trên đường đi:** HTTPS/TLS, trust boundary gateway–backend, không token trong URL/log/analytics/redirect không tin cậy?
11. **Chăm sóc token vòng đời:** Access token TTL/scope/audience tối thiểu, refresh token bảo vệ/rotation/sender-constraining theo profile; revocation được RS thực thi khi cần?
12. **Giao thức đặc biệt được xem xét:** DPoP/mTLS proxy, WebSocket, SSE có cơ chế xác thực riêng, không dựa vào OPTIONS preflight?
13. **Vận hành và cache đúng:** CORS headers không bị gateway/CDN làm sai, `Vary` và `Cache-Control` phù hợp, log không chứa bí mật?
14. **Kiểm thử âm tính:** Disallowed origin, thiếu ACAH Authorization, preflight 401, response 401 thiếu ACAO, sai audience/scope, cookie CSRF, XSS và token dùng từ công cụ ngoài browser?

**Ghi nhớ:** **CORS trả lời câu hỏi “JavaScript từ origin nào được đọc response này trong browser?”**; **OAuth token validation trả lời “token có hợp lệ, dành cho API này và có phạm vi quyền nào?”**; **authorization trả lời “chủ thể/client được làm gì trên đối tượng cụ thể?”**; còn **TLS và cơ chế bảo vệ token** giảm rủi ro bị đánh cắp trên đường đi hoặc trong quá trình sử dụng. Để vận chuyển token an toàn, phải thiết kế **đúng cả bốn lớp**, không bật wildcard CORS hoặc tắt authentication chỉ để hết lỗi frontend.

### Chuẩn và tài liệu tham khảo

- **WHATWG Fetch Standard — CORS protocol:** Origin, preflight, credentials mode, response checks và các header CORS.
- **RFC 6454 — The Web Origin Concept:** khái niệm origin và quy tắc same-origin.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage:** gửi access token bằng `Authorization` header và mối đe dọa bearer transport.
- **RFC 6749 — The OAuth 2.0 Authorization Framework:** token endpoint, access/refresh token và grant.
- **RFC 7636 — Proof Key for Code Exchange (PKCE):** bảo vệ authorization code exchange của public client.
- **RFC 9700 — Best Current Practice for OAuth 2.0 Security:** các kiểm soát bảo mật OAuth và token.
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** token profile, issuer, audience, scope và token type.
- **RFC 7662 — OAuth 2.0 Token Introspection:** trạng thái opaque/reference token.
- **RFC 9449 — OAuth 2.0 Demonstrating Proof of Possession (DPoP):** sender-constrained token và DPoP proof.
- **RFC 8705 — OAuth 2.0 Mutual-TLS Client Authentication and Certificate-Bound Access Tokens:** client-certificate binding.
- **OWASP Cross-Origin Resource Sharing (CORS) / Cross-Site Request Forgery / HTML5 Security Cheat Sheets:** cách cấu hình origin, cookie, CSRF và bảo vệ token trong ứng dụng web.
