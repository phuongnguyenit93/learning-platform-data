# Web origin: ranh giới danh tính và quyền truy cập trong trình duyệt

## 1. Vì sao cần hiểu web origin?

Giả sử bạn đã đăng nhập vào ứng dụng ngân hàng tại `https://bank.example`, rồi mở một trang khác do kẻ tấn công kiểm soát. Hai trang cùng chạy trong trình duyệt, nhưng trang của kẻ tấn công không được tự do đọc số dư, mã phiên hoặc nội dung DOM của ứng dụng ngân hàng. Trình duyệt cần một cách xác định **trang nào thuộc cùng phạm vi tin cậy** để áp dụng giới hạn này.

**Web origin** (nguồn gốc web) là danh tính bảo mật cơ bản mà trình duyệt gắn với tài liệu và nhiều tài nguyên web. Đối với URL HTTP(S) thông thường, origin là bộ ba **scheme (giao thức) + host (tên máy chủ) + port (cổng)**. Origin giúp trình duyệt quyết định những trường hợp nào script được đọc DOM, đọc phản hồi mạng và truy cập dữ liệu lưu trữ.

Trong module bảo mật ứng dụng web, web origin là mắt xích nối các chủ đề: **Same-Origin Policy (SOP)**, **CORS**, cơ chế cách ly của trình duyệt, cookie/CSRF, giao tiếp giữa iframe và cửa sổ, cũng như các biện pháp chống XSS, clickjacking bằng CSP, Trusted Types và security headers.

Sau bài học, bạn có thể:

1. Xác định chính xác khi nào hai URL cùng origin, kể cả port mặc định.
2. Phân biệt **origin**, **site** và **phạm vi cookie**.
3. Dự đoán quyền truy cập giữa document, iframe, storage và API.
4. Nhận diện origin đặc biệt như `data:`, `about:blank` và sandbox.
5. Kiểm tra hành vi SOP/CORS thực tế bằng Developer Tools và thiết kế kiểm tra origin an toàn.

## 2. Định nghĩa chính xác: scheme, host, port

Đối với URL dùng HTTP hoặc HTTPS:

```text
https://app.example.com:8443/account?tab=info#profile
└https┘ └app.example.com┘ └8443┘
 scheme          host          port

origin = (https, app.example.com, 8443)
```

**Đường dẫn (path), query string và fragment không tham gia xác định origin.** Origin cũng không phụ thuộc vào nội dung HTML, tài khoản người dùng hay cùng địa chỉ IP. Hai tên miền có thể trỏ về cùng máy chủ nhưng vẫn khác origin.

Origin thường được biểu diễn dưới dạng chuỗi như `https://app.example.com:8443`. Với cổng mặc định, cách biểu diễn thường bỏ cổng:

- `http://example.com:80` tương đương `http://example.com`.
- `https://example.com:443` tương đương `https://example.com`.
- `https://example.com:8443` khác `https://example.com`.

Xét document đang mở tại `https://app.example.com/dashboard`:

| URL được so sánh | Cùng origin? | Giải thích |
| --- | --- | --- |
| `https://app.example.com/settings` | Có | Chỉ khác path. |
| `https://app.example.com:443/api` | Có | `443` là cổng mặc định của HTTPS. |
| `https://app.example.com/?q=1#top` | Có | Query và fragment không làm đổi origin. |
| `http://app.example.com/` | Không | Scheme khác. |
| `https://api.example.com/` | Không | Host khác. |
| `https://app.example.com:9443/` | Không | Port khác. |
| `https://example.com/` | Không | Subdomain và apex domain là hai host khác nhau. |
| `https://app.example.net/` | Không | Host khác. |

Việc phân tích origin nên dùng bộ phân tích URL của nền tảng, tránh tự tách chuỗi:

```javascript
const current = new URL("https://app.example.com/dashboard");
const api = new URL("https://api.example.com/v1/me");
const settings = new URL("/settings", current);

console.log(current.origin);  // "https://app.example.com"
console.log(api.origin);      // "https://api.example.com"
console.log(settings.origin); // "https://app.example.com"
console.log(current.origin === api.origin);      // false
console.log(current.origin === settings.origin); // true
```

Tại một trang web thực tế, `window.location.origin` cho biết origin của URL hiện tại. Tuy vậy, với origin đặc biệt (opaque origin), kết quả có thể là chuỗi `"null"`: chuỗi này **không đại diện cho một domain đáng tin cậy**.

## 3. Origin, site và cookie: ba ranh giới khác nhau

Hai khái niệm dễ bị đồng nhất:

- **Same-origin**: cùng scheme, host và port. Đây là cơ sở của SOP và nhiều API lưu trữ.
- **Same-site**: theo mô hình *schemeful same-site*, cùng scheme và cùng miền đăng ký (*registrable domain*, xác định dựa trên Public Suffix List). Nhiều subdomain có thể thuộc cùng site.

Ví dụ với `https://shop.example.com`:

| URL khác | Same-origin | Same-site | Lý do |
| --- | --- | --- | --- |
| `https://shop.example.com/cart` | Có | Có | Cùng origin. |
| `https://api.example.com/orders` | Không | Có | Khác host, cùng scheme và miền đăng ký `example.com`. |
| `http://shop.example.com/` | Không | Không | Scheme HTTP khác HTTPS. |
| `https://shop.example.com:8080/` | Không | Có | Khác port; site thường không xét port. |
| `https://seller.example.net/` | Không | Không | Khác miền đăng ký. |

**Cookie không bị chia vùng theo port như origin.** Phạm vi cookie phụ thuộc chủ yếu vào domain/host, path, scheme đối với `Secure`, `SameSite` và các chính sách của trình duyệt:

```http
Set-Cookie: session=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
```

Cookie không có thuộc tính `Domain` ở ví dụ này là **host-only**: được gửi tới host đã thiết lập nó theo các quy tắc cookie. Nếu server cấu hình `Domain=example.com`, cookie có thể được gửi tới các subdomain phù hợp, tạo phạm vi rộng hơn. `HttpOnly` ngăn JavaScript đọc cookie qua `document.cookie`, nhưng không ngăn trình duyệt tự đính kèm cookie vào request phù hợp.

Vì thế:

- `https://app.example.com` và `https://api.example.com` là **same-site nhưng cross-origin**. Không được suy từ `SameSite` rằng chúng có quyền đọc DOM lẫn nhau.
- Hai ứng dụng cùng host nhưng khác port có thể **khác origin** trong khi vẫn cùng nhận một số cookie do cookie không phân tách theo port.
- `SameSite=Lax` hay `Strict` là biện pháp giảm rủi ro CSRF trong những tình huống phù hợp; chúng không thay thế xác thực, phân quyền hoặc CSRF token khi ứng dụng cần.

## 4. Origin quyết định điều gì trong trình duyệt?

Sơ đồ sau tóm tắt các vùng quyền:

```text
┌──────────────────────────────────┐    ┌──────────────────────────────────┐
│ https://app.example.com          │    │ https://api.example.com          │
│ Document A + Window + DOM        │    │ Document B / API                 │
│ localStorage / IndexedDB theo A  │    │ dữ liệu và chính sách origin B   │
└───────────────┬──────────────────┘    └──────────────────────────────────┘
                │                                  ▲
                ├── Đọc DOM B ─────── SOP chặn ────┤
                ├── fetch API B ──── CORS quyết định quyền đọc phản hồi
                ├── postMessage ────> trao đổi dữ liệu có kiểm tra nguồn
                └── cookie ─────────> quy tắc domain/site/credentials riêng
```

| Khả năng | Origin liên quan như thế nào? | Điều kiện/ngoại lệ đáng nhớ |
| --- | --- | --- |
| Đọc hoặc sửa DOM của cửa sổ/iframe khác | SOP thường chỉ cho phép truy cập đầy đủ giữa các document cùng origin. | Cross-origin window vẫn có một tập API giới hạn, chẳng hạn `postMessage`. |
| `fetch` hoặc XHR đến API | Trình duyệt kiểm tra CORS trước khi cho JavaScript đọc phản hồi cross-origin. | Request có thể đã được gửi ngay cả khi script không đọc được phản hồi. |
| `localStorage` và IndexedDB | Về cơ bản được phân vùng theo origin. | Trình duyệt có thể áp dụng thêm giới hạn hoặc phân vùng theo ngữ cảnh bên thứ ba. |
| Cookie | Dựa trên domain/host, path, `Secure`, `SameSite` và chính sách cookie. | Không được giả định cookie phân vùng đúng như DOM hoặc `localStorage`. |
| Tải ảnh, CSS, script, nhúng iframe | Nhiều kiểu nhúng cross-origin vẫn được cho phép có điều kiện. | CSP, CORS, CORP, COEP và giới hạn từng loại tài nguyên có thể thay đổi hành vi. |
| Script được nhúng qua `<script src>` | Script chạy trong ngữ cảnh bảo mật của document **nhúng script**. | CDN bên thứ ba không tạo sandbox tự động cho script. |

**Ví dụ quan trọng:** trang `https://app.example.com` tải thư viện từ `https://cdn.example.net/lib.js` qua thẻ `script`. Nếu thư viện chạy, nó có thể thao tác DOM và các API được phép của trang `app.example.com`. Vị trí lưu mã JavaScript không làm mã tự động mang quyền của origin CDN. Vì vậy một tệp script bị thay thế hoặc một lỗ hổng XSS có thể thực hiện hành động với quyền của ứng dụng.

Same-Origin Policy là giới hạn phía **trình duyệt**, không phải cơ chế phân quyền của server. Một client ngoài trình duyệt vẫn có thể gửi HTTP request; backend bắt buộc tự kiểm tra session, vai trò và quyền đối với từng tài nguyên.

## 5. Origin của tài liệu đặc biệt và các thay đổi trong vòng đời

Không phải mọi tài liệu đều mang origin đơn giản suy trực tiếp từ URL nhìn thấy:

| Trường hợp | Hành vi origin điển hình | Hệ quả bảo mật |
| --- | --- | --- |
| Tài liệu HTTP(S) thông thường | Bộ ba scheme, host, port của URL sau điều hướng. | Cùng host nhưng HTTP/HTTPS khác origin. |
| `about:blank` được tạo bởi document khác | Thường kế thừa origin của document tạo nó. | Không được xem `about:blank` tự động là vùng cô lập. |
| `iframe srcdoc` | Thường kế thừa origin của document nhúng khi không có sandbox cô lập. | HTML không tin cậy trong `srcdoc` cần sandbox phù hợp. |
| `data:text/html,...` | Thông thường nhận **opaque origin** riêng. | Không thể suy là cùng origin với trang chứa URL. |
| `blob:` | Thường mang origin gắn với môi trường đã tạo blob URL. | Không coi mọi `blob:` là một origin độc lập và an toàn. |
| `iframe sandbox` không có `allow-same-origin` | Document bị gán opaque origin. | Giảm quyền truy cập dữ liệu cùng origin; một số API bị hạn chế. |
| `file:` | Cách xử lý origin có thể khác nhau theo trình duyệt. | Dùng HTTP server cục bộ để thử nghiệm ổn định. |

**Opaque origin** là origin không khớp với origin tuple thông thường. Giá trị serialization thường là `"null"`; **hai opaque origin khác nhau có thể cùng hiển thị `"null"` nhưng không vì thế trở thành same-origin**. Đây cũng là lý do không nên chấp nhận `Origin: null` trong chính sách CORS chỉ vì trông giống một giá trị cố định.

Một `iframe` có thể điều hướng từ URL đáng tin cậy sang URL khác sau khi tải. Bất kỳ code nào dùng tham chiếu `contentWindow` phải giả định tài liệu bên trong có thể đã thay đổi; phải kiểm tra origin của từng thông điệp và không dựa vào trạng thái ban đầu của iframe.

API `document.domain` từng được dùng để nới lỏng một số giới hạn giữa subdomain, nhưng hiện đã lỗi thời và không giải quyết các ranh giới bảo mật hiện đại. Thiết kế mới nên dùng API giao tiếp rõ ràng như `postMessage` hoặc backend API có CORS phù hợp.

## 6. CORS: cách API cho phép đọc dữ liệu từ origin khác

Giả sử frontend tại `https://app.example.com` cần gọi API tại `https://api.example.com`. Hai URL này **khác origin**. Trong trình duyệt:

```javascript
const response = await fetch("https://api.example.com/account", {
  credentials: "include"
});
if (!response.ok) throw new Error("API request failed");
const account = await response.json();
```

Để JavaScript tại `app.example.com` đọc phản hồi của request dùng credentials, API có thể trả:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
```

Server cần xác định origin nào được phép từ một **allowlist chính xác**; không phản chiếu mọi giá trị `Origin` nhận được. `Vary: Origin` cần thiết khi server trả `Access-Control-Allow-Origin` động theo request, để cache phân biệt phản hồi theo origin.

### Preflight không phải tường lửa

Với một số request, chẳng hạn request dùng phương thức `PUT` hoặc header `Content-Type: application/json`, trình duyệt có thể gửi **CORS preflight** (OPTIONS) trước:

```http
OPTIONS /account HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: PUT
Access-Control-Request-Headers: content-type
```

API có thể đáp lại:

```http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, PUT
Access-Control-Allow-Headers: Content-Type
Access-Control-Allow-Credentials: true
Vary: Origin
```

Tuy nhiên, nhiều request thông thường **không cần preflight**. Trình duyệt có thể đã gửi request và server đã xử lý tác động của nó dù script bị chặn đọc response vì CORS. CORS không phải cơ chế chống CSRF.

### Các lỗi cấu hình CORS hay gặp

1. **Cho phép quá rộng:** đặt `Access-Control-Allow-Origin: *` cho API chứa dữ liệu không công khai. Dấu sao không dùng được khi trình duyệt đọc phản hồi với chế độ credentials, nhưng API công khai vẫn cần cân nhắc phạm vi dữ liệu trả về.
2. **Phản chiếu Origin vô điều kiện:** trả lại bất kỳ `Origin` nào client gửi, kèm `Access-Control-Allow-Credentials: true`, làm mất giới hạn truy cập dự kiến.
3. **Kiểm tra domain bằng chuỗi con/hậu tố sai:** `origin.includes("example.com")` có thể chấp nhận `https://example.com.attacker.test`.
4. **Nhầm CORS với xác thực:** server trả header CORS đúng không có nghĩa request đã được phân quyền.
5. **Cho phép `Origin: null` không kiểm soát:** opaque origins khác nhau có thể cùng serialization `"null"`.

Đối với endpoint nhạy cảm, hãy xác thực và phân quyền từng request độc lập với CORS; nếu dùng cookie, kiểm tra thêm `SameSite` và phương pháp chống CSRF phù hợp.

## 7. Trao đổi giữa document khác origin với postMessage

Hai cửa sổ khác origin có thể giữ tham chiếu tới nhau trong những trường hợp được phép, nhưng không thể tùy ý đọc DOM của nhau. `window.postMessage` cung cấp một kênh trao đổi dữ liệu. An toàn của kênh phụ thuộc vào **cả bên gửi lẫn bên nhận**.

Giả sử ứng dụng `https://app.example.com` nhúng iframe đăng nhập ở `https://login.example.net`:

**Document cha**:

```javascript
const iframe = document.querySelector("#login-frame");
const loginOrigin = "https://login.example.net";

iframe.addEventListener("load", () => {
  iframe.contentWindow.postMessage(
    { type: "REQUEST_STATUS", requestId: "status-1" },
    loginOrigin // targetOrigin cụ thể, không dùng "*" cho dữ liệu nhạy cảm
  );
});

window.addEventListener("message", (event) => {
  if (event.origin !== loginOrigin) return;
  if (event.source !== iframe.contentWindow) return;
  if (event.data?.type !== "LOGIN_STATUS") return;
  if (event.data.requestId !== "status-1") return;
  if (typeof event.data.loggedIn !== "boolean") return;

  console.log("Đã xác minh trạng thái:", event.data.loggedIn);
});
```

**Document trong iframe**:

```javascript
window.addEventListener("message", (event) => {
  if (event.origin !== "https://app.example.com") return;
  if (event.source !== window.parent) return;
  if (event.data?.type !== "REQUEST_STATUS") return;
  if (typeof event.data.requestId !== "string") return;

  event.source.postMessage(
    {
      type: "LOGIN_STATUS",
      requestId: event.data.requestId,
      loggedIn: true // Chỉ là dữ liệu minh họa; trạng thái thực cần nguồn xác thực
    },
    event.origin
  );
});
```

Trong sản phẩm thật, giá trị trạng thái cần được tính từ phiên/nguồn dữ liệu đã xác thực. `postMessage` chỉ vận chuyển thông điệp; **nó không tự xác thực người dùng**. Bên nhận kiểm tra chính xác `event.origin`, `event.source`, kiểu thông điệp và kiểu dữ liệu. Không đưa `event.data` trực tiếp vào `innerHTML`. Khi cần bảo vệ khỏi thông điệp cũ hoặc nhầm phiên, cân nhắc correlation ID/nonce gắn với yêu cầu hiện tại.

## 8. Những tình huống tấn công gắn với origin

### 8.1 XSS: chạy mã với quyền của origin hợp lệ

Nếu ứng dụng đưa chuỗi từ URL vào DOM bằng `innerHTML`, dữ liệu không tin cậy có thể trở thành markup có khả năng thực thi mã. Khi xảy ra XSS, mã tấn công chạy trong origin ứng dụng, có thể đọc DOM, gọi API được phép và thao tác dữ liệu mà nạn nhân có quyền truy cập.

```javascript
const displayName = new URLSearchParams(location.search).get("name") ?? "";

// Không an toàn nếu displayName do người dùng kiểm soát:
// document.querySelector("#hello").innerHTML = displayName;

// An toàn hơn khi chỉ cần hiển thị văn bản:
document.querySelector("#hello").textContent = displayName;
```

Ngoài xử lý dữ liệu đúng ngữ cảnh, có thể áp dụng **Content Security Policy (CSP)** để hạn chế mã script được phép chạy, và **Trusted Types** để quản lý các điểm đưa HTML/script động vào DOM ở trình duyệt hỗ trợ. Những cơ chế này hỗ trợ giảm tác động XSS, không thay việc kiểm soát đầu vào/đầu ra đúng cách.

### 8.2 CSRF: origin khác vẫn có thể kích hoạt request

Một trang của kẻ tấn công không thể đọc DOM ngân hàng nhờ SOP, nhưng có thể tìm cách làm trình duyệt gửi form/request tới endpoint thay đổi dữ liệu. Nếu cookie phiên được gửi kèm và server không kiểm tra CSRF, thao tác trái ý người dùng vẫn có thể xảy ra.

Phòng vệ gồm: xác thực và phân quyền phía server; CSRF token phù hợp cho hành động thay đổi trạng thái; kiểm tra `Origin` hoặc `Referer` theo chính sách; cookie `SameSite` thích hợp; không dùng GET cho thao tác cập nhật. Header request `Origin` là **tín hiệu do trình duyệt cung cấp trong ngữ cảnh phù hợp**, không phải chứng cứ danh tính người dùng hay biện pháp bảo vệ duy nhất.

### 8.3 Clickjacking: nhúng document vào giao diện lừa đảo

SOP không tự ngăn một origin khác nhúng trang trong iframe. Nếu trang nhạy cảm bị phủ lớp hoặc đặt lệch, người dùng có thể bị đánh lừa nhấp vào thao tác mà họ không nhận ra.

Với trang không cần được nhúng, server có thể trả:

```http
Content-Security-Policy: frame-ancestors 'none'
X-Frame-Options: DENY
```

`frame-ancestors` quy định những ancestor nào được phép nhúng document. Chỉ thị này phải nằm trong **HTTP response header**, không hoạt động khi đặt trong thẻ `meta`. Nếu có nghiệp vụ nhúng hợp lệ, hãy khai báo những origin được phép thay vì cấm toàn bộ.

### 8.4 Lỗi kiểm tra origin và subdomain

Ví dụ server chỉ muốn cho phép frontend `https://app.example.com` nhưng viết kiểm tra `requestOrigin.endsWith("example.com")`. Kiểm tra kiểu này có thể nhận nhầm domain `https://evil-example.com`. Nên so sánh **origin chuẩn hóa chính xác** với allowlist tin cậy.

Ngoài ra, quyền kiểm soát một subdomain cũng ảnh hưởng đến bề mặt tấn công: nếu subdomain bị chiếm quyền, nó vẫn khác origin với ứng dụng chính nhưng có thể cùng site và tương tác với cookie được cấu hình quá rộng. Vì vậy không tự động tin tưởng mọi subdomain chỉ vì cùng miền đăng ký.

## 9. Cơ chế cách ly bổ sung và security headers

Origin là điểm bắt đầu, nhưng các ứng dụng phức tạp có thể cần nhiều lớp cách ly:

| Cơ chế | Mục tiêu | Mối liên hệ với origin |
| --- | --- | --- |
| **SOP** | Hạn chế truy cập DOM/dữ liệu cross-origin. | Chính sách nền tảng theo origin. |
| **CORS** | Cho phép JavaScript đọc phản hồi cross-origin khi server cho phép. | Kiểm tra origin được chấp thuận bằng HTTP header. |
| **CSP** | Giới hạn nguồn script, tài nguyên và hành vi; có `frame-ancestors`. | Danh sách nguồn có thể gồm `'self'` hoặc origin cụ thể. |
| **Trusted Types** | Hạn chế việc truyền chuỗi tùy ý vào một số DOM sink có nguy cơ XSS. | Kiểm soát thao tác JavaScript trong document. |
| **iframe sandbox** | Hạn chế quyền tài liệu nhúng; có thể tạo opaque origin. | Không cấp `allow-same-origin` nếu muốn cô lập origin nhúng. |
| **CORP** | Cho phép tài nguyên quyết định các ngữ cảnh cross-origin/no-CORS nào được tải. | Dùng `Cross-Origin-Resource-Policy`, thường là `same-origin`, `same-site` hoặc `cross-origin`. |
| **COEP** | Yêu cầu tài liệu nhúng tài nguyên cross-origin đáp ứng điều kiện CORS/CORP hoặc chế độ phù hợp. | Hỗ trợ tăng cách ly tài nguyên. |
| **COOP** | Điều khiển quan hệ browsing context với các cửa sổ cấp cao khác. | Giảm liên hệ giữa cửa sổ cross-origin, ví dụ qua `window.opener`. |

Một cấu hình có thể được cân nhắc cho trang nhạy cảm, tùy chức năng thực tế:

```http
Content-Security-Policy: default-src 'self'; script-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
X-Frame-Options: DENY
```

Đây chỉ là **ví dụ định hướng**, không phải cấu hình áp dụng nguyên trạng cho mọi dự án. Chẳng hạn CSP `script-src 'self'` có thể không phù hợp với ứng dụng đang dùng script inline; việc triển khai cần nonce/hash hoặc thiết kế lại cách tải script. Những ứng dụng cần mở iframe cũng phải điều chỉnh `frame-ancestors`.

Khi cần **cross-origin isolation** cho một số API trình duyệt nhạy cảm, ứng dụng có thể thiết lập COOP và COEP thích hợp, ví dụ:

```http
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```

Cấu hình này có thể khiến tài nguyên hoặc luồng đăng nhập popup không còn hoạt động như trước. Cần đánh giá mọi script, ảnh, iframe và redirect; kiểm tra `window.crossOriginIsolated` tại secure context để biết document đáp ứng trạng thái cần thiết hay chưa. **Cross-origin isolation là cơ chế bổ sung, không thay SOP, CORS hoặc xác thực backend.**

## 10. Thực hành trên hai origin localhost

Bạn có thể dùng hai HTTP server tĩnh trên máy để phục vụ các trang:

- Trang A: `http://localhost:3000/index.html`.
- Trang B: `http://localhost:4000/child.html`.

Hai địa chỉ có cùng scheme và host nhưng **khác port**, nên là cross-origin. Hãy mở DevTools tại trang A.

**Thí nghiệm 1 — so sánh URL.** Dán vào Console:

```javascript
const a = new URL("http://localhost:3000/index.html");
const b = new URL("http://localhost:4000/child.html");
const c = new URL("http://localhost:3000/other?x=1");

console.table([
  { url: a.href, origin: a.origin },
  { url: b.href, origin: b.origin },
  { url: c.href, origin: c.origin }
]);
console.log(a.origin === b.origin); // false
console.log(a.origin === c.origin); // true
```

**Thí nghiệm 2 — ranh giới DOM.** Trang A có iframe tải B:

```html
<iframe id="other-app" src="http://localhost:4000/child.html"></iframe>
```

Sau khi iframe tải xong, tại Console của A:

```javascript
const frame = document.querySelector("#other-app");
console.log(frame.contentDocument); // null với document khác origin

try {
  console.log(frame.contentWindow.document.body.textContent);
} catch (error) {
  console.log(error.name); // thường là "SecurityError"
}
```

Nhận xét: A có thể tham chiếu `contentWindow` nhưng không có quyền đọc toàn bộ DOM của B. Bạn có thể thử tự triển khai `postMessage` với `targetOrigin`/`event.origin` đúng để trao đổi dữ liệu hợp lệ mà không vượt SOP.

**Thí nghiệm 3 — CORS và kiểm tra response.** Tại Console của A, gọi một endpoint HTTP ở port `4000` (endpoint này phải có sẵn trên server của bạn):

```javascript
fetch("http://localhost:4000/data.json")
  .then(response => response.text())
  .then(console.log)
  .catch(error => console.error("Không đọc được phản hồi:", error));
```

Trong thẻ **Network**, quan sát request và header response. Nếu server B không gửi CORS header phù hợp, script ở A bị chặn đọc response, dù Network có thể cho thấy request đã tới server. Sau đó cấu hình server B gửi:

```http
Access-Control-Allow-Origin: http://localhost:3000
Vary: Origin
```

Tải lại và quan sát thay đổi. Ví dụ này dùng `fetch` mặc định (`credentials: "same-origin"`), không yêu cầu cookie cross-origin.

**Thí nghiệm 4 — phân biệt same-site và same-origin.** So sánh hai địa chỉ `https://app.example.com` và `https://api.example.com`. Hãy trả lời: chúng có cùng site không; script của app có mặc nhiên đọc API không; cookie `Domain=example.com` có thể áp dụng ở những host nào? Giải thích riêng từng lớp thay vì đưa ra một kết luận chung.

### Câu hỏi kiểm tra hiểu bài

1. Vì sao `https://shop.example.com:443` và `https://shop.example.com` là cùng origin, trong khi `http://shop.example.com` là khác origin?
2. Một trang cross-origin gửi được request chuyển tiền nhưng không đọc được response: SOP/CORS có loại bỏ được nguy cơ CSRF không?
3. Một iframe `srcdoc` chứa nội dung do người dùng cung cấp có tự động bị cách ly origin không? Nên dùng cơ chế nào?
4. Tại sao không nên coi mọi giá trị `Origin: null` là một origin duy nhất đáng tin?
5. Khi nhận `message`, việc chỉ kiểm tra `event.data.type` còn thiếu những yếu tố xác minh nào?
6. Cấu hình `Access-Control-Allow-Origin` sai có thể làm lộ dữ liệu trong tình huống nào, và backend vẫn phải kiểm tra điều gì?

## 11. Kết luận

**Origin là bộ ba scheme–host–port**, dùng để diễn đạt danh tính bảo mật cơ bản của tài liệu HTTP(S) trong trình duyệt. **Site** là ranh giới khác, thường phục vụ chính sách cookie; **cookie** có phạm vi riêng và không được chia theo port như origin. Nắm vững ba khái niệm này giúp hiểu vì sao SOP chặn đọc DOM chéo nguồn nhưng không tự ngăn mọi request, CORS kiểm soát quyền đọc phản hồi, và `postMessage` cần xác minh nguồn gửi.

Trong thiết kế ứng dụng an toàn, hãy duy trì kiểm tra xác thực/phân quyền và chống CSRF ở server, chỉ định allowlist origin chính xác khi dùng CORS, xử lý dữ liệu DOM an toàn để chống XSS, và dùng sandbox, CSP, Trusted Types, `frame-ancestors` cùng các security headers phù hợp để bảo vệ document. Mọi quyết định nên được xác minh bằng hành vi trình duyệt thực tế ở những origin khác nhau.
