# Same-origin policy và các thành phần tạo nên origin

## 1. Bài toán: API trả 200 nhưng JavaScript vẫn không đọc được

Ứng dụng giao diện ở `https://app.example.test` cần gọi REST API tại `https://api.example.test`. Server trả JSON thành công khi thử bằng Java HttpClient hoặc curl, nhưng trình duyệt báo lỗi **CORS**. Lý do không nhất thiết là endpoint hỏng: trình duyệt có một **mô hình bảo mật origin**, và JavaScript bị hạn chế truy cập nội dung từ origin khác.

**Same-origin policy (SOP)** là nguyên tắc bảo mật cốt lõi giới hạn cách mã chạy trong một origin tương tác với tài liệu và dữ liệu của origin khác. Nó giảm nguy cơ trang độc hại đọc dữ liệu riêng của trang người dùng đang đăng nhập. SOP có ngoại lệ được chuẩn hóa, chẳng hạn nhúng một số tài nguyên hoặc truy cập HTTP response được server cho phép qua **CORS (Cross-Origin Resource Sharing)**.

Trong module **INTEGRATION_API_REST**, hiểu origin là tiền đề để thiết kế URI, HTTP headers/status, API contract, authentication, CSRF, CORS, cookie, cache và kiểm thử Java/Spring. Bài tập trung vào **origin và hệ quả đối với browser API**, không đồng nhất SOP với “mọi HTTP request khác domain đều bị cấm”.

Sau bài học, người học có thể:

1. Tính đúng origin từ **scheme, host, port** và phân biệt origin với URL, site, domain, path.
2. Giải thích phần nào của DOM, fetch, iframe và storage bị SOP chặn; phần nào vẫn có thể gửi request hoặc nhúng.
3. Hiểu CORS, preflight, credentials và các header HTTP hai phía.
4. Nhận diện **opaque origin**, sandbox, `postMessage` và ranh giới trust.
5. Cấu hình Spring MVC/Spring Security cho frontend browser, không nhầm CORS với authentication/authorization hoặc CSRF.
6. Kiểm thử trên trình duyệt thật lẫn MockMvc/HTTP client, bao gồm các trường hợp bị từ chối.

> **Quy tắc quan trọng:** **CORS không phải cơ chế đăng nhập, phân quyền hoặc bảo vệ CSRF.** Nó cho trình duyệt biết JavaScript của *origin nào* có thể đọc response. Server vẫn phải kiểm token/session, scope, quyền từng resource và giới hạn truy cập.

## 2. Một origin được tạo bởi những gì?

Với một URL HTTP(S) thông thường, origin là bộ ba:

~~~text
origin = (scheme, host, effective port)

https://api.example.test:8443/v1/orders?limit=20#summary
└https┘ └──api.example.test──┘ └8443┘
 scheme            host           port
~~~

- **Scheme (giao thức):** `http` khác `https`. Nâng cấp từ HTTP sang HTTPS **thay đổi origin**.
- **Host:** tên miền hoặc địa chỉ IP sau khi URL được parse/canonicalize. `app.example.test` khác `api.example.test`; `localhost` khác `127.0.0.1`.
- **Effective port:** port tường minh hoặc port mặc định của scheme; `https` mặc định **443**, `http` mặc định **80**.

**Path, query string, fragment và thông tin userinfo của URL không phải thành phần của origin.** Việc thay `/orders` thành `/admin` không tạo biên bảo mật SOP mới. Browser dùng thuật toán origin của nền tảng web, không nên tự so origin bằng cách lấy chuỗi host tùy ý.

### 2.1. Bảng so sánh origin

Lấy `https://app.example.test/dashboard` làm URL gốc:

| URL được xét | Cùng origin? | Vì sao? |
|---|---|---|
| `https://app.example.test/orders` | **Có** | Cùng scheme, host, port |
| `https://app.example.test:443/v1` | **Có** | 443 là port mặc định HTTPS |
| `https://APP.example.test/path?q=1` | **Có** | Hostname được chuẩn hóa không phân biệt chữ hoa/thường |
| `http://app.example.test/dashboard` | **Không** | Scheme HTTP khác HTTPS |
| `https://app.example.test:8443/` | **Không** | Port 8443 khác 443 |
| `https://api.example.test/` | **Không** | Host khác dù cùng miền mẹ |
| `https://example.test/` | **Không** | Host gốc khác subdomain |
| `https://localhost:443/` | **Không** | Host khác |
| `https://127.0.0.1/` | **Không** | Host khác |

**Port chuẩn hóa** quan trọng: `https://app.example.test` và `https://app.example.test:443` có cùng origin. Nhưng `http://app.example.test:443` vẫn khác, bởi scheme là `http`. Origin không được tính bằng cách so “cùng IP backend”, “cùng công ty” hay “cùng chứng chỉ TLS”.

### 2.2. Thử trực tiếp bằng JavaScript

~~~javascript
const base = new URL("https://app.example.test/dashboard");
const other = new URL("https://api.example.test/v1/orders");

console.log(base.origin);  // "https://app.example.test"
console.log(other.origin); // "https://api.example.test"
console.log(base.origin === other.origin); // false

const defaultPort = new URL("https://app.example.test:443/a");
console.log(defaultPort.origin === base.origin); // true

const differentPath = new URL("https://app.example.test/admin");
console.log(differentPath.origin === base.origin); // true
~~~

Đối với tài liệu thực, `window.location.origin` phản ánh origin được serialize khi có thể. **Đừng dùng `split("/")` hoặc regex tự chế** để suy origin: URL parsing còn liên quan port mặc định, IPv6, Unicode hostname, ký tự escape và loại scheme. Một số nguồn không có origin dạng bộ ba, sẽ được giải thích ở mục 4.

### 2.3. Origin không đồng nghĩa với site

**Origin** so khớp chính xác scheme + host + port. **Site** trong nhiều cơ chế cookie/browser hiện đại dựa trên *schemeful site*: scheme cùng với *registrable domain* (ước tính từ Public Suffix List), hoặc host theo quy tắc riêng khi không có registrable domain.

~~~text
https://app.example.test    ┐
https://api.example.test    ├  Khác origin, nhưng cùng site theo schemeful site
https://shop.example.test   ┘

https://news.other.test         Khác site
http://app.example.test        Khác schemeful site với HTTPS
~~~

Vì vậy **same-site không đồng nghĩa same-origin**. Cookie với `SameSite=Lax` hay `SameSite=Strict` xét quan hệ *site*, không thay thế SOP/CORS. Hai subdomain cùng site vẫn là **cross-origin** khi gọi `fetch`, và muốn đọc response cross-origin vẫn phải đáp ứng CORS.

Thêm nữa, cookie `Domain=.example.test` có thể được gửi đến nhiều subdomain theo quy tắc cookie; `Path=/app` **không phải biên bảo mật** để cách ly JavaScript trên cùng origin. Trái lại, `localStorage` được phân tách chủ yếu theo origin (trình duyệt có thể áp thêm storage partitioning). Không suy rằng quyền truy cập cookie và quyền đọc DOM luôn cùng một ranh giới.

## 3. SOP bảo vệ những gì và không ngăn những gì?

Một trang ở `https://evil.example-other.test` có thể khiến trình duyệt gửi một số request tới `https://bank.example.test`; nhưng **không tự do đọc** nội dung HTML/JSON hoặc thao tác DOM của trang ngân hàng. Đây là sự khác biệt giữa **khả năng gửi request** và **khả năng đọc response**.

| Hoạt động từ origin A đến origin B | Thường được phép gửi/nhúng? | Đọc/truy cập qua JavaScript? |
|---|---|---|
| `<img src="https://B/image.png">` | Có, tùy chính sách tài nguyên | Không đọc tùy ý pixel vào canvas không bị taint nếu thiếu CORS |
| Classic `<script src="https://B/lib.js">` | Có, tùy CSP/MIME/chính sách | Script được chạy trong trang A; không có quyền tùy ý đọc response như `fetch` |
| HTML form POST sang B | Có thể gửi request/navigate | Trang A không được đọc DOM của response ở origin B |
| `fetch("https://B/api")` | Có thể gửi, đôi khi phải preflight | **Chỉ đọc response khi CORS cho phép** |
| `<iframe src="https://B/page">` | Có thể nhúng nếu không bị frame policy chặn | Không được đọc/sửa DOM iframe B trực tiếp |
| Truy cập `iframe.contentWindow.document` khác origin | Không liên quan gửi mạng | **Bị chặn** bởi SOP |
| `localStorage` của B từ trang A | Không | **Bị cô lập theo origin** |
| Chuyển hướng/navigate tới B | Thường có thể, với các hạn chế hiện hành | Không tạo quyền đọc DOM khác origin |

SOP không cam kết rằng **không có bất kỳ tín hiệu nào** vượt origin: kích thước, thời gian tải, hành vi của tài nguyên nhúng hoặc một số giao diện Window bị giới hạn có thể tạo kênh phụ. Các chính sách như **CSP, CORP, COEP, COOP, frame-ancestors, X-Frame-Options và Fetch Metadata** hỗ trợ thêm trong từng mục đích; chúng không định nghĩa lại bộ ba origin.

### 3.1. Cross-origin iframe và `postMessage`

Trang A không thể `iframe.contentWindow.document.body.innerText` của B. Muốn hai trang trao đổi dữ liệu có chủ đích, dùng **`window.postMessage`**:

~~~javascript
// Trang cha tại https://app.example.test
const frame = document.querySelector("#partner-widget");
frame.contentWindow.postMessage(
  {type: "GET_SELECTION"},
  "https://widget.partner.test" // targetOrigin chính xác
);

window.addEventListener("message", (event) => {
  if (event.origin !== "https://widget.partner.test") return;
  if (event.source !== frame.contentWindow) return;
  if (event.data?.type !== "SELECTION") return;

  // Validate schema của event.data trước khi sử dụng.
  renderSelection(event.data.value);
});
~~~

**Không dùng `targetOrigin: "*"`** cho dữ liệu nhạy cảm, không chỉ kiểm `event.data.type` rồi tin mọi nguồn, và không gửi token qua message nếu không có thiết kế bảo mật/định danh đối tác. `postMessage` **không vượt SOP một cách vô điều kiện**: nó tạo kênh trao đổi có chủ đích, cần xác minh cả origin lẫn nguồn gửi và shape dữ liệu.

## 4. Không phải origin nào cũng là bộ ba HTTP(S)

Trong mô hình bảo mật web, một số tài liệu có **opaque origin**: origin không cùng với bất kỳ origin dạng bộ ba nào khác, và khi serialize trong nhiều ngữ cảnh có thể cho kết quả chuỗi `null`. Vì vậy quy tắc “lấy scheme + host + port” áp dụng trực tiếp cho **URL HTTP(S) thông thường**, không cho mọi loại tài liệu.

| Trường hợp | Điều cần nhớ |
|---|---|
| `data:text/html,...` | Tài liệu thường có **opaque origin** riêng |
| `<iframe sandbox>` không có `allow-same-origin` | Iframe bị đặt vào **opaque origin**, kể cả URL trỏ về cùng host |
| `about:blank`, `about:srcdoc` | Thường **kế thừa origin** của tài liệu tạo/nhúng, trừ trường hợp sandbox hoặc ngữ cảnh đặc biệt |
| `blob:...` | Blob URL thường mang origin gắn với môi trường tạo nó; không coi mọi blob là public |
| `file://` | Hành vi origin và quyền đọc file có khác biệt giữa trình duyệt; không dựa vào file URL để kiểm CORS |

Ví dụ nhúng nội dung không đáng tin:

~~~html
<iframe
  src="https://widget.partner.test/embed"
  sandbox="allow-scripts"
  title="Partner widget">
</iframe>
~~~

Không có `allow-same-origin`, tài liệu iframe bị sandboxed origin, làm hạn chế truy cập storage và tương tác same-origin. **Không tùy tiện kết hợp `allow-scripts` + `allow-same-origin` cho tài liệu cùng origin do bạn quản lý**, vì trang bên trong có thể làm suy yếu các hạn chế sandbox. Để tích hợp, ưu tiên hostname riêng, sandbox được thiết kế rõ và `postMessage` xác minh nguồn.

**Origin: null** có thể xuất hiện ở các request từ opaque origin; không mặc định phản hồi `Access-Control-Allow-Origin: null` cho mọi caller. Nhiều nguồn khác nhau cùng serialize thành `null`, nên coi giá trị này là *allowlist an toàn* là sai lầm.

## 5. Từ SOP đến Fetch API: gửi được không có nghĩa đọc được

Giả sử JavaScript chạy tại `https://app.example.test`:

~~~javascript
const response = await fetch(
  "https://api.example.test/api/orders/ord-741",
  {method: "GET"}
);

if (!response.ok) throw new Error("HTTP " + response.status);
const order = await response.json();
console.log(order);
~~~

Đây là lời gọi **cross-origin**. Server có thể nhận GET, thậm chí trả 200 JSON, nhưng trình duyệt vẫn từ chối cho JS đọc nếu response thiếu CORS headers phù hợp. Lỗi JavaScript thường biểu hiện như **TypeError / network error của Fetch**, **không có status HTTP 403 được expose cho JS** chỉ vì CORS thất bại. DevTools Network có thể hiển thị request/response phục vụ debug, nhưng không chứng minh chương trình được đọc chúng.

### 5.1. Request mode và response type

| Cấu hình | Ý nghĩa thực hành |
|---|---|
| `mode: "cors"` | Chế độ thường dùng cho `fetch` cross-origin: browser thực thi CORS và trả readable response nếu hợp lệ |
| `mode: "same-origin"` | Không cho Fetch gửi request cross-origin |
| `mode: "no-cors"` | Chỉ dùng được request hạn chế; response cross-origin thường **opaque**, không đọc status/header/body |
| `credentials: "same-origin"` | Giá trị mặc định của Fetch: ambient credentials chỉ cho request cùng origin |
| `credentials: "include"` | Cho phép gửi/nhận credentials theo quy tắc cookie/browser; cần CORS credentials policy khi cross-origin |
| `credentials: "omit"` | Không gửi ambient credentials theo cơ chế Fetch; token được đặt tường minh trong header cần được xử lý theo contract |

**Không dùng `mode: "no-cors"` như mẹo “sửa lỗi CORS”.** Lời gọi có thể được phát đi nhưng response opaque không thể `response.json()`, không kiểm status 200/409 hay đọc Location; phương pháp này không phù hợp SDK REST API cần xử lý lỗi.

### 5.2. CORS là việc server cho phép đọc, không phải cho phép gọi API

Khi browser gửi request cross-origin có header `Origin`, server có thể trả:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example.test
Vary: Origin

{"id":"ord-741","status":"CONFIRMED"}
~~~

Khi origin caller khớp **Access-Control-Allow-Origin** và các điều kiện CORS liên quan, browser cho JavaScript đọc body. Nếu server bỏ header này, JS bị chặn đọc **dù server đã trả 200**. Với request có quyền, API vẫn cần xác thực token và kiểm tenant/order ACL; header CORS không cấp quyền tự động.

**Không tự gửi `Access-Control-Allow-Origin` từ JavaScript client**: đây là **response header do server quyết định**. `Origin` cũng do browser quản lý; API không được coi `Origin` là credential vì native clients có thể giả lập hoặc bỏ header này.

## 6. CORS preflight: tại sao trình duyệt gửi OPTIONS trước POST?

Không phải request cross-origin nào cũng có preflight. Một số request chỉ dùng **CORS-safelisted method/headers** có thể được gửi ngay, sau đó browser kiểm response để quyết định JS có đọc được hay không. Những request khác cần **preflight OPTIONS** để hỏi server trước.

Ví dụ POST JSON có `Authorization: Bearer ...` sẽ cần preflight, vì **Content-Type: application/json** không thuộc nhóm giá trị Content-Type được safelist và **Authorization** là request header không safelisted.

### 6.1. Sequence HTTP chuẩn bị và gửi request thật

~~~mermaid
sequenceDiagram
    participant B as Browser at app.example.test
    participant A as REST API at api.example.test
    B->>A: OPTIONS /api/orders (Origin, Access-Control-Request-Method/Headers)
    A-->>B: 200/204 + Access-Control-Allow-Origin/Methods/Headers
    B->>A: POST /api/orders + JSON + Authorization
    A-->>B: 201 + Location + CORS headers
    Note over B: JS chỉ đọc response nếu CORS hợp lệ
~~~

Preflight đi trước request thật, **không phải yêu cầu tạo resource**. Một preflight không được thực thi POST, ghi database hay cần bearer token của request thật để quyết định quyền nghiệp vụ. Nếu preflight bị Spring Security chặn 401 trước khi CORS xử lý, browser không gửi POST theo cách mong muốn.

**Preflight request:**

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type,idempotency-key
~~~

**Preflight response ví dụ:**

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: POST
Access-Control-Allow-Headers: Authorization, Content-Type, Idempotency-Key
Access-Control-Max-Age: 600
Vary: Origin, Access-Control-Request-Method, Access-Control-Request-Headers
~~~

**Request thật**, chỉ sau khi preflight hợp lệ:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.test
Origin: https://app.example.test
Authorization: Bearer <access-token>
Content-Type: application/json
Idempotency-Key: intent-741

{"customerId":"cus-17","items":[{"sku":"BOOK-01","quantity":2}]}
~~~

**Response thật** cũng cần CORS header nếu client cần đọc:

~~~http
HTTP/1.1 201 Created
Location: /api/orders/ord-741
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Expose-Headers: Location
Vary: Origin
Cache-Control: no-store

{"id":"ord-741","status":"PENDING_PAYMENT"}
~~~

Lưu ý **Idempotency-Key** trong preflight: đây là request header tùy biến nên phải có trong `Access-Control-Request-Headers` và được server chấp nhận qua `Access-Control-Allow-Headers`; nếu bỏ sót, browser không gửi POST. Danh sách request headers do trình duyệt tự tạo từ headers thực tế mà JavaScript đặt.

`Access-Control-Expose-Headers` cần thiết nếu JS muốn đọc `Location` hoặc `ETag`: đây không phải response headers safelisted được expose mặc định. Không nhầm **expose** (cho JS đọc response header) với **allow headers** (cho request gửi header).

### 6.2. Chỉ những request đáp ứng safelist mới tránh preflight

Các method được CORS safelist gồm **GET, HEAD, POST**; còn header/value phải đáp ứng những giới hạn safelist (chẳng hạn Content-Type thuộc nhóm `application/x-www-form-urlencoded`, `multipart/form-data`, `text/plain`, cùng các điều kiện khác). POST JSON hoặc thêm header Authorization thường gây preflight. GET với custom `X-Client-Version` cũng có thể preflight, dù method là GET.

**Tránh preflight không phải mục tiêu an toàn tuyệt đối.** Không đổi Content-Type JSON thành `text/plain` chỉ để né OPTIONS rồi làm sai contract. Preflight cache qua `Access-Control-Max-Age` giúp giảm số OPTIONS nhưng vẫn chịu giới hạn của browser; cache preflight không thay thế HTTP caching của GET response.

## 7. Credentials, cookie và cache: cấu hình CORS đúng nhưng API vẫn có thể không an toàn

### 7.1. Hai phương án xác thực browser thường gặp

**Phương án A — Bearer token đặt rõ trong Authorization header:**

~~~javascript
const accessToken = await acquireAccessTokenSecurely();
const response = await fetch("https://api.example.test/api/orders", {
  method: "POST",
  mode: "cors",
  credentials: "omit",
  headers: {
    "Authorization": "Bearer " + accessToken,
    "Content-Type": "application/json",
    "Idempotency-Key": intentKey
  },
  body: JSON.stringify(orderInput)
});

if (!response.ok) {
  // Chỉ đọc được status/body nếu CORS cho phép response.
  throw new Error("API HTTP " + response.status);
}
const location = response.headers.get("Location");
const created = await response.json();
~~~

Đây là fragment: cần cách lấy token an toàn, `intentKey` được sinh/lưu theo **một ý định**, `orderInput` được kiểm tra và API hỗ trợ Idempotency-Key. Header Authorization làm request cần preflight; không hard-code access token vào script, URL hoặc log. `Location` chỉ đọc được nếu server expose header đó trong CORS.

**Phương án B — Cookie phiên được trình duyệt gửi tự động:**

~~~javascript
const response = await fetch("https://api.example.test/api/me", {
  credentials: "include"
});
~~~

Đối với request cross-origin có credentials, server phải trả origin cụ thể và cho phép credentials:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

**Không sử dụng `Access-Control-Allow-Origin: *` cùng với `Access-Control-Allow-Credentials: true`** cho response cần credentials; browser không chấp nhận cặp cấu hình đó. Không phản chiếu mọi Origin client gửi vào Allow-Origin khi bật credentials. Phải có **allowlist origin đáng tin** chính xác, không chỉ kiểm chuỗi `endsWith("example.test")` dễ sai.

Lưu ý `credentials: "include"` **không buộc browser phải gửi cookie** nếu cookie bị chặn bởi Domain/Path/Secure/SameSite, third-party cookie policy hoặc phân vùng lưu trữ. Với cross-*site* cookie, `SameSite=None; Secure` thường cần thiết nhưng vẫn không bảo đảm cookie third-party được cho phép. Với hai subdomain cùng schemeful site, SameSite và CORS vẫn là **hai cơ chế riêng**.

### 7.2. Cookie không phải biên giới JavaScript theo Path/Domain

- **HttpOnly** hạn chế truy cập giá trị cookie qua JavaScript, nhưng browser vẫn có thể **gửi** cookie trong request phù hợp. HttpOnly **không tự chống CSRF**.
- **Secure** yêu cầu truyền cookie theo kết nối bảo mật phù hợp; không thay xác thực server hoặc quyền truy cập.
- **SameSite** giới hạn việc gửi cookie theo quan hệ site, không xác định cùng origin.
- **Domain** có thể làm cookie được gửi tới nhiều subdomain; host-only cookie giới hạn host hơn. Dùng prefix như `__Host-` khi chính sách cookie phù hợp để giảm rủi ro cấu hình sai.
- **Path** là điều kiện gửi cookie, **không phải cách ly bí mật** giữa các script chạy trong cùng origin.

Không lưu access token hoặc refresh token vào browser storage tùy tiện. JavaScript trên cùng origin có thể bị ảnh hưởng bởi **XSS**; cân nhắc kiến trúc token/session, CSP, HttpOnly cookie và cách đổi token theo threat model.

### 7.3. Vary, preflight cache và response riêng tư

Nếu server trả `Access-Control-Allow-Origin` khác nhau tùy `Origin`, cần **`Vary: Origin`** để cache trung gian không tái sử dụng nhầm response. Với **preflight** có quyết định thay đổi theo `Access-Control-Request-Method` hoặc `Access-Control-Request-Headers`, cân nhắc `Vary` trên các header tương ứng.

`Access-Control-Max-Age` điều khiển **cache kết quả preflight** theo giới hạn browser; nó **không** tương đương `Cache-Control: max-age=...` của JSON response. Đối với đơn hàng riêng tư hoặc dữ liệu nhạy cảm, `Cache-Control: no-store` có thể phù hợp; CORS headers không thay thế chính sách private cache.

Ngay cả nếu response là **401/403/409**, frontend vẫn cần CORS hợp lệ để đọc error code/Problem Details. Nếu CORS chỉ được thêm cho response 200, giao diện dễ báo “network error” cho lỗi nghiệp vụ, làm che khuất trạng thái thật.

Với **401 Unauthorized** của API dùng bearer token, server còn cần duy trì header **`WWW-Authenticate: Bearer`** (và các tham số thích hợp theo tình huống). Có CORS cho phép JS đọc 401 **không** có nghĩa JavaScript được xem token bí mật; nó chỉ cho client nhận biết request cần xác thực hoặc refresh token theo chính sách.

## 8. CORS, CSRF và phân quyền tài nguyên là ba bài toán khác nhau

**CORS** chủ yếu kiểm soát việc JavaScript cross-origin **đọc response**. Nó **không bảo đảm request có side effect không tới server**. Chẳng hạn HTML form có thể gửi POST dạng Content-Type được hỗ trợ mà không cần CORS preflight; cookie phù hợp có thể đi cùng. Nếu endpoint dùng **cookie authentication**, một trang độc hại có thể thử gửi request thay mặt người dùng: đó là **CSRF (Cross-Site Request Forgery)**.

Một thiết kế cookie/session cần phối hợp:

1. **CSRF token** hoặc cơ chế chống CSRF tương đương theo kiến trúc Spring Security.
2. Cookie **SameSite** phù hợp, Secure/HttpOnly và chính sách phiên.
3. Kiểm `Origin`/`Referer` trên các thao tác nhạy cảm khi thích hợp; có thể dùng **Fetch Metadata headers** như `Sec-Fetch-Site` để tăng phòng thủ.
4. Xác thực, phân quyền **theo đối tượng/tenant**, validation DTO và transaction/anti-replay.

**SameSite không bảo vệ đầy đủ mọi trường hợp:** hai origin cùng site vẫn có thể khác mức tin cậy (ví dụ subdomain bị chiếm quyền). Nếu API nhận cookie, **đừng tắt CSRF chỉ vì đã cấu hình CORS**.

Với API thuần bearer token **được client chủ động gắn vào Authorization header**, không có cookie tự mang chứng thực, CSRF risk khác đáng kể; có thể chọn cấu hình không dùng CSRF token **sau khi xác minh mô hình xác thực thực tế**. Nhưng endpoint vẫn có thể bị XSS, token theft, thiếu scope hoặc **BOLA/IDOR**; CORS không giải quyết các lỗi ấy.

**Phân quyền object-level:** một response CORS hợp lệ cho `https://app.example.test` không cấp quyền cho user A đọc `/api/orders/{id}` của tenant B. Server phải kiểm JWT/session/issuer/audience, scope, tenant và owner; nếu không có quyền, trả **403/404 theo policy**, không phải cấp quyền dựa trên Origin.

### 8.1. Những trường hợp CORS không trực tiếp áp dụng như Fetch

- **Java HttpClient, curl, Postman và backend-to-backend HTTP:** không thực thi CORS theo cách trình duyệt; client có thể đọc response nếu mạng/server cho phép. Vì vậy CORS **không thể là access-control cho API**.
- **WebSocket:** handshake và `Origin` có quy tắc riêng, không dựa vào preflight CORS của Fetch; server phải **kiểm Origin/authentication** và quyền từng message/room.
- **Server-side request forwarding:** proxy có thể truy cập upstream mà JS không được phép; proxy phải xác thực caller, chống SSRF, giới hạn destination và áp chính sách dữ liệu.
- **Same-origin reverse proxy:** phục vụ frontend và API dưới cùng scheme/host/port thường giảm nhu cầu CORS, nhưng không bỏ qua authentication, CSRF hoặc quyền resource.

Không vì CORS gây khó cấu hình mà mở `*` cho mọi credentialed request hay triển khai một proxy vô điều kiện có thể gọi mọi URL.

## 9. Spring MVC và Spring Security: cấu hình CORS có chủ đích

Giả sử frontend `https://app.example.test` gọi API `https://api.example.test` bằng **bearer Authorization header**, không dùng cookie phiên. Cấu hình sau minh họa với Spring Boot/Spring Security hiện đại:

~~~java
import java.util.List;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ApiCorsSecurityConfiguration {

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.test"));
        cors.setAllowedMethods(List.of("GET", "POST", "PATCH", "OPTIONS"));
        cors.setAllowedHeaders(List.of(
            "Authorization", "Content-Type", "Idempotency-Key", "If-Match"));
        cors.setExposedHeaders(List.of("Location", "ETag"));
        cors.setAllowCredentials(false); // API mẫu không dùng ambient cookie
        cors.setMaxAge(600L);

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }

    @Bean
    SecurityFilterChain security(HttpSecurity http) throws Exception {
        http
            .cors(Customizer.withDefaults())
            // Chỉ cho mô hình stateless bearer, KHÔNG áp dụng nếu
            // backend còn dùng cookie/session để xác thực.
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.create")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));
        return http.build();
    }
}
~~~

**Điều kiện của ví dụ:**

- Các dependencies Spring Web, Spring Security và OAuth2 Resource Server phải tương thích phiên bản Boot; cấu hình `JwtDecoder` kiểm **chữ ký, issuer, expiry và audience**. Code trên **không tự cấu hình** nguồn token.
- CORS được tích hợp vào **SecurityFilterChain**, giúp xử lý preflight **trước** kiểm bearer token của request thật. **Không buộc OPTIONS preflight mang Authorization** và không tắt toàn bộ security cho mọi OPTIONS ở mọi origin.
- Chỉ `https://app.example.test` được phép đọc cross-origin response theo CORS. Origin khác vẫn có thể gọi API từ non-browser client, nhưng **không vượt được authorization**.
- **`allowCredentials(false)`** dành cho mẫu bearer header không dùng ambient credentials; nếu dùng cookie, phải chọn **một cấu hình khác** với credentials thật và CSRF được bảo vệ. Không chỉ đổi mỗi flag thành true.
- Tên path/method và scope là **contract minh họa**, cần đồng bộ với OpenAPI. Với yêu cầu PATCH, bổ sung rule authorization/CSRF/If-Match tương ứng; ví dụ mặc định deny PATCH.

### 9.1. Controller vẫn phải kiểm quyền tài nguyên

~~~java
import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.*;

record OrderView(String id, String status, long totalAmount) {}
interface OrdersService {
    // Bắt buộc lọc tenant + chủ sở hữu theo principal đã xác minh.
    OrderView findVisible(String id, String subject, String tenant);
}

@RestController
@RequestMapping("/api/orders")
class OrdersController {
    private final OrdersService service;
    OrdersController(OrdersService service) { this.service = service; }

    @GetMapping("/{id}")
    ResponseEntity<OrderView> get(
            @PathVariable String id,
            @AuthenticationPrincipal Jwt jwt) {
        String tenant = jwt.getClaimAsString("tenant_id");
        if (tenant == null || tenant.isBlank()) {
            throw new org.springframework.security.access.AccessDeniedException(
                "Missing tenant");
        }
        OrderView order = service.findVisible(
            id, jwt.getSubject(), tenant);
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(order);
    }
}
~~~

Đây là **fragment**, cần service thực, xử lý 404/403 và test; không trả raw JWT/PII trong response hoặc log. Nếu subdomain app bị XSS, một origin allowlisted có thể bị dùng sai: vì vậy CORS **không thay kiểm tra user và tài nguyên**. Nhìn chung nên tách cấu hình CORS theo môi trường (dev/staging/prod) bằng danh sách origin được duyệt, không dựa vào phép so chuỗi mơ hồ hoặc host do request tùy ý khai.

## 10. Kiểm thử SOP/CORS đúng ở ba tầng

### 10.1. Kiểm tra HTTP headers bằng công cụ dòng lệnh

Để phân biệt lỗi server với lỗi browser, có thể quan sát preflight bằng curl:

~~~bash
curl -i -X OPTIONS "https://api.example.test/api/orders" \
  -H "Origin: https://app.example.test" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: authorization,content-type,idempotency-key"
~~~

Kỳ vọng preflight được phép trả **2xx với Access-Control-Allow-Origin, Access-Control-Allow-Methods, Access-Control-Allow-Headers** phù hợp. Với origin không được phép, không trả header cấp quyền cho origin đó. Kiểm tra thêm `Vary` và preflight cache policy nếu có proxy/CDN.

**Quan trọng:** curl hoặc Java HttpClient có thể tự đặt `Origin` và đọc response mà không thực thi SOP/CORS. Vì vậy lệnh curl chỉ kiểm **server CORS headers**, **không chứng minh JavaScript thật có thể đọc response**. Cần bài kiểm thử trên trình duyệt với hai origin khác nhau.

### 10.2. MockMvc và Spring Security Test

Fragment test Spring với `MockMvc`, cấu hình CORS/Security ở mục 9 và các static imports tương ứng:

~~~java
mockMvc.perform(options("/api/orders")
        .header("Origin", "https://app.example.test")
        .header("Access-Control-Request-Method", "POST")
        .header("Access-Control-Request-Headers",
                "authorization,content-type,idempotency-key"))
    .andExpect(status().isOk())
    .andExpect(header().string(
        "Access-Control-Allow-Origin",
        "https://app.example.test"))
    .andExpect(header().string(
        "Access-Control-Allow-Methods",
        org.hamcrest.Matchers.containsString("POST")));

mockMvc.perform(options("/api/orders")
        .header("Origin", "https://untrusted.test")
        .header("Access-Control-Request-Method", "POST"))
    .andExpect(status().isForbidden());
~~~

Đây là **test fragment**, không phải class hoàn chỉnh. Kết quả chặn origin lạ có thể phụ thuộc Spring CORS processor/phiên bản; mục tiêu cốt lõi là **browser không nhận được Access-Control-Allow-Origin cho origin bị từ chối**. Bổ sung test GET thật với JWT giả lập và Origin được phép, xác nhận có CORS headers **và** 200 khi resource thuộc tenant; 403/404 khi thiếu quyền tài nguyên.

Với request thật không có JWT:

~~~java
mockMvc.perform(get("/api/orders/ord-741")
        .header("Origin", "https://app.example.test"))
    .andExpect(status().isUnauthorized())
    .andExpect(header().string(
        "Access-Control-Allow-Origin",
        "https://app.example.test"));
~~~

Test này kỳ vọng CORS vẫn được gắn vào **401** khi origin thuộc allowlist. Nếu test thất bại, cần xem thứ tự CORS/Security filters thay vì mở public endpoint. **JWT mock trong MockMvc không chứng minh issuer/audience/signature thật được xác minh**; cần security integration test riêng.

### 10.3. Chỉ browser integration test mới chứng minh SOP được áp dụng

Chạy frontend test từ **`https://app.example.test`** và một origin không tin cậy như **`https://untrusted.test`** (môi trường thử nghiệm với DNS/TLS thích hợp). Dùng Playwright/Selenium hoặc mở DevTools:

1. Từ origin được phép, gọi API bằng `fetch` với header như contract; xác nhận POST preflight nếu có custom headers, body đọc được và `Location` expose đúng.
2. Từ origin không được phép, gọi cùng API; xác nhận mã JavaScript **không đọc được response** khi thiếu CORS permission. Tránh kết luận request chắc chắn không tới server.
3. Với credential mode `include`, kiểm `Access-Control-Allow-Credentials`, cookie policy, SameSite và browser blocking theo môi trường.
4. Tạo iframe cross-origin; thử truy cập `contentWindow.document` và xác nhận bị SOP chặn; sau đó thử `postMessage` với **targetOrigin và event.origin/source** kiểm chặt.
5. Với `mode: "no-cors"`, xác nhận response opaque không thể đọc JSON/status, không coi đó là giải pháp sửa CORS.

**Kiểm thử CORS không thay thế kiểm thử authorization:** cũng phải gửi request từ Java/curl với JWT của user A nhằm đọc order B để chứng minh service từ chối ngay cả khi không có browser kiểm soát.

### 10.4. Ma trận kiểm thử lỗi

| Trường hợp | Hành vi đúng |
|---|---|
| Same origin, path khác | Không cần CORS vì origin không đổi |
| Same site, subdomain khác | Cross-origin: cần CORS nếu `fetch` cần đọc response |
| HTTPS → HTTP hoặc port khác | Cross-origin; còn phải xét mixed-content/TLS policy |
| OPTIONS hợp lệ từ origin allowlisted | Preflight được xử lý không đòi JWT của POST |
| OPTIONS có header ngoài allowlist | Không cấp quyền, browser không gửi request thật theo flow CORS |
| Response 401/403 từ API cho origin allowlisted | JS vẫn đọc được status/problem nếu CORS hợp lệ |
| Origin lạ yêu cầu credentials | Không phản chiếu Origin, không cấp Allow-Credentials |
| Tenant khác với token hợp lệ | Service trả 403/404, dù CORS cho origin frontend |
| Cookie session và cross-site POST | CSRF/SameSite/Origin protections bảo vệ thao tác |
| Iframe sandbox có opaque origin | Không tự coi `Origin: null` là origin đáng tin |
| ETag/Location cần JS đọc | Có `Access-Control-Expose-Headers` thích hợp |

## 11. Bẫy thiết kế và cách chẩn đoán

**Bẫy 1 — “Postman gọi được, trình duyệt lỗi thì API chắc chắn hỏng.”** Không đúng. Postman không cưỡng chế SOP như browser. Xem request preflight, response CORS headers, credentials mode và console error, đồng thời kiểm server logs để biết request thật có tới không.

**Bẫy 2 — “Hai subdomain cùng công ty nên là same-origin.”** Không đúng: `https://app.example.test` và `https://api.example.test` khác host, dù có thể cùng site. Chúng cần CORS để JS đọc cross-origin response.

**Bẫy 3 — “Thêm Access-Control-Allow-Origin: * vào request.”** CORS do **response server** quyết định. Dùng wildcard với credentialed browser requests cũng không hoạt động và có thể làm lộ dữ liệu nếu chính sách sai.

**Bẫy 4 — “Dùng no-cors cho fetch để vượt CORS.”** Request có thể đi nhưng response opaque, không đọc JSON, status hay headers. API frontend cần tích hợp CORS hoặc phục vụ qua same-origin proxy đáng tin.

**Bẫy 5 — “CORS ngăn CSRF nên có thể tắt CSRF cho cookie session.”** Request side-effect dạng form có thể gửi được mà không cần CORS đọc response. Phải có CSRF defense theo mô hình session/cookie.

**Bẫy 6 — “Origin là danh tính user.”** Origin chỉ mô tả nguồn web trong ngữ cảnh browser, không phải token; non-browser client giả lập dễ dàng. API vẫn cần xác thực, phân quyền object và rate limiting.

**Bẫy 7 — “Chỉ đặt CORS trên controller là đủ.”** Preflight có thể bị auth filter chặn trước controller, và lỗi 401/403 có thể thiếu CORS header. Cần bảo đảm thứ tự xử lý và test cả success/error responses.

**Bẫy 8 — “Đặt frontend ở /ui và admin ở /admin là đã cách ly.”** Path không nằm trong origin. Script XSS ở một path có thể có nhiều khả năng trên cùng origin; cân nhắc host/origin riêng, CSP và sandbox theo threat model.

## 12. Bài tập và đáp án hướng dẫn

**Bài 1 — Tính origin.** So `https://shop.example.test/products` với (a) `https://shop.example.test:443/cart`, (b) `http://shop.example.test/cart`, (c) `https://api.example.test/cart`, (d) `https://shop.example.test:8443/cart`. **Đáp án:** (a) cùng origin; (b) khác scheme; (c) khác host; (d) khác port.

**Bài 2 — Site và origin.** Frontend `https://app.example.test` dùng `fetch` tới `https://api.example.test`; cả hai thuộc `example.test`. Có cần CORS để JS đọc response không? **Đáp án:** Có, vì khác host nên khác origin. SameSite cookie không thay SOP.

**Bài 3 — Preflight.** POST JSON có Authorization và Idempotency-Key nhưng server chỉ allow `Content-Type`. **Đáp án:** Browser có thể chặn trước POST; preflight phải allow cả `authorization`, `content-type`, `idempotency-key` và method, origin phù hợp.

**Bài 4 — Cookie và wildcard.** Frontend gọi `fetch` với `credentials: "include"`, server trả `Access-Control-Allow-Origin: *` và `Access-Control-Allow-Credentials: true`. **Đáp án:** Browser từ chối cho JS đọc response; cần origin cụ thể được duyệt, nhưng còn phải bảo vệ CSRF và kiểm cookie policy.

**Bài 5 — Opaque origin.** Một iframe sandbox gửi request có `Origin: null`; backend allow `null` cho mọi API private. **Đáp án:** Không an toàn: nhiều ngữ cảnh opaque origin cùng serialize thành `null`, không phải danh tính tin cậy. Không mở ACL dựa trên giá trị này.

**Bài 6 — SOP không cấp quyền.** API có CORS cho đúng frontend, nhưng user A biết order ID của B và gửi JWT của A. **Đáp án:** Server vẫn phải kiểm tenant/owner và từ chối. CORS không giải quyết BOLA/IDOR.

**Bài 7 — Cross-origin message.** Parent nhận `postMessage` mà chỉ kiểm `data.type === "PAYMENT_DONE"`. **Đáp án:** Phải kiểm `event.origin`, `event.source`, dữ liệu và quy tắc nghiệp vụ; tránh wildcard targetOrigin cho nội dung nhạy cảm.

## 13. Checklist vận hành và kết luận

- [ ] Xác định scheme, host, port của từng frontend/API; phân biệt **same-origin** và **same-site**?
- [ ] Xác nhận các request cần CORS, request nào gây preflight và các request headers phải được allow?
- [ ] Chỉ allow origin được duyệt; không phản chiếu Origin tùy ý hoặc allow `null`?
- [ ] Với credentials, dùng Allow-Origin cụ thể, Allow-Credentials phù hợp và cookie/session policy?
- [ ] CORS preflight được xử lý trước bearer authentication; actual request vẫn kiểm auth/ACL?
- [ ] `Access-Control-Expose-Headers` cho Location/ETag, Vary/Cache-Control đúng?
- [ ] Cookie authentication có CSRF defense; không dùng CORS như lá chắn CSRF?
- [ ] Iframe/sandbox/postMessage có kiểm origin, source, shape dữ liệu và trust boundary?
- [ ] Test bằng browser thật và MockMvc; dùng curl chỉ để xem HTTP headers?
- [ ] Negative tests xác minh tenant/owner/role và lỗi 401/403 không bị che thành “CORS error”?

**Kết luận:** Origin của URL HTTP(S) được quyết định bởi **scheme, host và port**, không phải path hay miền mẹ. **Same-origin policy** giới hạn khả năng JavaScript đọc và tương tác dữ liệu khác origin, nhưng không đồng nghĩa mọi request cross-origin đều bị chặn. **CORS** mở quyền đọc có điều kiện do server công bố; còn **authentication, authorization, CSRF, cookie policy và HTTP contract** phải được bảo vệ và kiểm thử độc lập.
