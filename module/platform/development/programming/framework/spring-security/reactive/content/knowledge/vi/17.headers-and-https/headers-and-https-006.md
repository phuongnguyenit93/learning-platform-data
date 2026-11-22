# Referrer-Policy, Permissions-Policy và giảm rò rỉ dữ liệu trình duyệt

## 1. Mục tiêu và bối cảnh

Khi người dùng truy cập một trang bảo mật qua trình duyệt, dữ liệu có thể rời khỏi ứng dụng theo những con đường không hiển nhiên: URL của trang trước được browser đưa vào header `Referer` khi đi tới trang tiếp theo; script và iframe có thể xin dùng camera, microphone hoặc vị trí; tài nguyên từ bên thứ ba có thể thu thập thông tin; cache, log và công cụ phân tích có thể giữ lại URL chứa query nhạy cảm.

Hai HTTP response headers giúp kiểm soát một phần bề mặt này:

- **`Referrer-Policy`**: cho trình duyệt biết có được gửi thông tin trang nguồn trong header request `Referer` hay không, và nếu được thì gửi bao nhiêu.
- **`Permissions-Policy`**: giới hạn những khả năng của trình duyệt mà document và iframe được phép sử dụng, chẳng hạn `geolocation`, `camera`, `microphone`.

Bài học thuộc nhóm **Header và HTTPS** của module **Spring Security - reactive**. Các ví dụ hướng tới **Spring WebFlux**, Java 17+, Spring Boot 3.x và Spring Security 6.5.x.

Sau bài, bạn có thể:

1. Phân biệt chính xác **response header `Referrer-Policy`** với **request header `Referer`**, gồm cả lỗi chính tả lịch sử trong tên `Referer`.
2. Lựa chọn giữa `no-referrer`, `same-origin`, `strict-origin-when-cross-origin` và các directive khác dựa trên yêu cầu riêng tư; dự đoán trường hợp cross-origin, same-origin và HTTPS → HTTP.
3. Phân biệt **browser default `strict-origin-when-cross-origin`** với **Spring Security WebFlux 6.5 mặc định phát `Referrer-Policy: no-referrer`**, và biết trường hợp nào cấu hình lại làm chính sách bớt nghiêm ngặt.
4. Hiểu cú pháp `Permissions-Policy: geolocation=(), camera=(), microphone=()`; ý nghĩa `()`, `(self)` và danh sách origin.
5. Nắm sự tương tác giữa header của document cha, thuộc tính `allow` của iframe và quyền cấp bởi người dùng; không xem Permissions Policy là một hệ thống authentication.
6. Cấu hình header bằng `ServerHttpSecurity.headers(...)` và `SecurityWebFilterChain`, không dùng nhầm `HttpSecurity` của Servlet.
7. Chạy một ứng dụng WebFlux Java 17+ với các response headers đúng, và viết kiểm thử `WebTestClient` cho các đường dẫn công khai, có xác thực và bị từ chối.
8. Dùng browser DevTools kiểm chứng **hành vi thực tế**; biết vì sao kiểm tra header bằng curl/WebTestClient chưa chứng minh browser đã chặn API hoặc đã không gửi Referer.
9. Kết hợp HTTPS/HSTS, CSP, CSRF, CORS, URL design, cache control, chống XSS và log redaction để giảm rò rỉ dữ liệu trên nhiều lớp.

**Phạm vi:** chính sách trên response của **inbound Spring WebFlux web application**. Không tự hiểu rằng server chỉ cần thêm hai header là chặn được mọi tracking, browser extension, screenshot, JavaScript độc hại hoặc dữ liệu lộ qua request URL khác.

## 2. Dữ liệu rò rỉ từ trình duyệt như thế nào?

### 2.1. Ví dụ trang có URL nhạy cảm

Giả sử người dùng mở:

```text
https://app.example/account/recovery?ticket=SECRET_VALUE
```

Sau đó trang này có link hoặc tải tài nguyên từ:

```text
https://partner.example/help
https://cdn.example/widget.js
```

Khi trình duyệt đi theo link hoặc gửi request tài nguyên, nó có thể gửi header `Referer` biểu thị trang nguồn, tùy **Referrer-Policy**, loại request, browser và ngữ cảnh HTTPS.

Một giá trị `Referer` nguy hiểm nếu chứa cả đường dẫn/query:

```http
GET /help HTTP/1.1
Host: partner.example
Referer: https://app.example/account/recovery?ticket=SECRET_VALUE
```

Đây là **HTTP minh họa rủi ro**, không phải điều sẽ xảy ra dưới mọi policy. Chính sách mạnh giúp cắt hoặc rút gọn URL trang nguồn. Quan trọng hơn, ứng dụng không nên đặt **mật khẩu, session ID, access token, reset token, khóa API hoặc PII** trong URL nếu có cách an toàn hơn, vì Referrer-Policy không xóa dữ liệu khỏi browser history, server log hay analytics.

### 2.2. Rò rỉ qua API trình duyệt

Một trang quảng cáo/iframe hoặc script có thể thử dùng:

- `navigator.geolocation.getCurrentPosition(...)` để xin vị trí.
- `navigator.mediaDevices.getUserMedia({ video: true })` để xin camera.
- `navigator.mediaDevices.getUserMedia({ audio: true })` để xin microphone.
- Những tính năng khác mà browser hỗ trợ và Permissions Policy có directive tương ứng.

Permissions Policy cho phép website định nghĩa **giới hạn tối đa** của các khả năng đó theo document/embedded context. Nhưng nếu policy cho phép geolocation, **user permission và yêu cầu secure context** vẫn có thể tiếp tục áp dụng. Nó không cấp phép camera/vị trí cho script, và không thay kiểm soát quyền của ứng dụng ở backend.

### 2.3. Đường rò rỉ khác mà hai header không xử lý

| Nguồn rò rỉ | Ví dụ | Biện pháp bổ sung |
|---|---|---|
| URL được gửi trực tiếp đến server | `GET /account?token=...` | Không dùng secret trong URL, kiểm soát log và cache |
| `Referer` tới origin khác | Link/tài nguyên bên ngoài mang URL trang nguồn | `Referrer-Policy`, `rel="noreferrer"`, thiết kế URL |
| Browser feature APIs | Iframe xin camera/vị trí | `Permissions-Policy`, `iframe allow`, user permissions |
| JavaScript bên thứ ba | Script đọc DOM rồi gửi dữ liệu bằng fetch | CSP, supply-chain controls, tránh script không tin cậy, chống XSS |
| Cookie bị script đọc | Session cookie thiếu HttpOnly | `HttpOnly`, `Secure`, `SameSite`, XSS prevention |
| Local/shared cache | Trang account lưu trong browser/CDN | `Cache-Control: no-store`, phân vùng cache |
| Logs, telemetry | Query/headers chứa token | Redaction/allowlist fields, retention policy |
| Cross-origin response đọc được | CORS cho origin không tin cậy | CORS allowlist, credentials policy |
| Transport không mã hóa | HTTP và mixed content | HTTPS, HSTS, Secure cookies |
| HTTP request giả mạo | Website khác dụ browser POST có cookie | CSRF protection và SameSite |

## 3. Referrer-Policy: tên đúng và ý nghĩa

### 3.1. Hai header không cùng một hướng

**Request header** có tên chính thức `Referer` (thiếu chữ r trong “referrer” do lỗi chính tả lịch sử). Browser có thể gửi nó khi điều hướng hoặc tải tài nguyên.

**Response header** là `Referrer-Policy` (đúng chính tả hai chữ r), do trang nguồn hoặc resource gửi để chỉ dẫn browser về mức độ referrer được phép tiết lộ khi trang tiếp tục tạo request.

Ví dụ:

```http
HTTP/1.1 200 OK
Referrer-Policy: same-origin
Content-Type: text/html;charset=UTF-8
```

Response trên **không xóa/sửa `Referer` của chính HTTP request đã tới server**. Nó hướng dẫn user agent cho các request liên quan về sau theo phạm vi policy. Browser tự tính giá trị `Referer` dựa trên document, destination, referrer policy và ngữ cảnh.

Không dùng `Referrer-Policy` làm cơ chế lọc server-side credential hoặc một WebFilter xóa header Referer client gửi vào; hai trách nhiệm khác nhau.

### 3.2. “Origin” là gì?

Một **origin** gồm **scheme + host + port**. Ví dụ:

```text
https://app.example/account/profile?tab=security
               |                 |
               |                 +-- path + query: thông tin chi tiết URL
               +-- origin: https://app.example

https://app.example:8443 là origin khác do port khác.
http://app.example là origin khác do scheme khác.
```

`Referer` thường không bao gồm fragment `#section`, nhưng path và query có thể được đưa vào tùy policy. Chỉ gửi origin giúp tránh lộ URL chi tiết, nhưng vẫn tiết lộ website nguồn. Nếu origin riêng đã nhạy cảm, `no-referrer` là lựa chọn mạnh hơn.

### 3.3. Bảng so sánh các directive quan trọng

Ví dụ nguồn: `https://app.example/account?ticket=abc`.

| Policy | Tới same-origin HTTPS | Tới cross-origin HTTPS | Từ HTTPS tới HTTP |
|---|---|---|---|
| `no-referrer` | Không gửi Referer | Không gửi | Không gửi |
| `same-origin` | Gửi URL nguồn (path/query có thể có) | Không gửi | Không gửi (khác origin) |
| `origin` | Chỉ origin | Chỉ origin | Có thể gửi origin theo directive này; không chọn cho secret-sensitive flow |
| `strict-origin` | Chỉ origin | Chỉ origin | Không gửi |
| `strict-origin-when-cross-origin` | URL nguồn | Chỉ origin | Không gửi |
| `origin-when-cross-origin` | URL nguồn | Chỉ origin | Có thể chỉ gửi origin khi đi HTTP theo directive |
| `no-referrer-when-downgrade` | URL nguồn | URL nguồn | Không gửi |
| `unsafe-url` | URL nguồn | URL nguồn | Có thể gửi URL nguồn, rất rủi ro |

“URL nguồn” trong bảng hiểu là URL do browser cho phép truyền, không tự bao gồm username/password, fragment và những phần bị browser loại theo quy tắc. Không dựa vào các directive yếu nếu nguồn có reset token, auth code hoặc PII.

**Khuyến nghị:** với trang đăng nhập, account, callback, recovery và các nghiệp vụ riêng tư, chọn `no-referrer` nếu không thực sự cần referrer. Nếu cần referrer nội bộ nhưng không muốn tiết lộ ra origin khác, `same-origin` phù hợp. Nếu cần analytics nguồn cấp site khi đi cross-origin HTTPS, `strict-origin-when-cross-origin` là một mức thỏa hiệp, nhưng vẫn tiết lộ origin.

### 3.4. Browser default khác Spring Security default

MDN mô tả mặc định hiện đại của browser khi **không có policy** là `strict-origin-when-cross-origin`. **Nhưng tài liệu chính thức Spring Security WebFlux 6.5 ghi rằng Spring Security thêm `Referrer-Policy: no-referrer` theo mặc định.**

Hai câu không mâu thuẫn:

```text
Browser không nhận Referrer-Policy:
  -> thường dùng strict-origin-when-cross-origin (browser default)

Response đi qua Spring Security WebFlux 6.5 default header setup:
  -> thường nhận Referrer-Policy: no-referrer
  -> browser theo response policy nghiêm hơn
```

Trong **Spring Security Servlet**, default được tài liệu mô tả khác; đừng áp quy tắc WebFlux cho mọi stack hoặc version. Và khi một reverse proxy/gateway thay/ghi đè response header, **giá trị browser thật nhận** mới là nguồn phải kiểm tra.

Tài liệu: [Spring Security 6.5 WebFlux Header Reference](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html) và [MDN Referrer-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy).

### 3.5. Lựa chọn chính sách theo dữ liệu

**Website nhạy cảm nhất:**

```http
Referrer-Policy: no-referrer
```

Không gửi Referer trong các tình huống policy chi phối. Tốt cho ngân hàng, patient portal, trang auth/reset, dashboard dữ liệu kín, nhưng có thể giảm số liệu referral/cách hoạt động dựa trên Referer.

**Ứng dụng nội bộ cần referrer cho điều hướng cùng origin:**

```http
Referrer-Policy: same-origin
```

Không gửi Referer tới các origin khác, vẫn có thể gửi URL chi tiết giữa các route cùng origin. **Đừng đặt secret vào URL nội bộ** chỉ vì `same-origin`.

**Website thông tin/marketing cần đo nguồn cấp origin bên ngoài:**

```http
Referrer-Policy: strict-origin-when-cross-origin
```

Gửi URL đầy đủ ở same-origin, chỉ origin khi đi cross-origin HTTPS và không gửi khi downgrade HTTPS → HTTP. Mức này thường là browser default nếu không khai báo header, nhưng **ít riêng tư hơn WebFlux Spring Security default no-referrer**.

**Tránh:**

```http
Referrer-Policy: unsafe-url
```

Directive này có thể rò path và query trên cross-origin và downgrade; gần như không nên dùng với ứng dụng xử lý dữ liệu nhạy cảm.

## 4. Cơ chế áp dụng Referrer-Policy trên browser

### 4.1. Điều hướng link

Một document nguồn nhận header `Referrer-Policy`. Khi người dùng nhấn link đến origin khác, browser tính `Referer` theo policy của nguồn.

Ví dụ với `same-origin`:

```text
Trang nguồn:
https://app.example/account/settings?tab=privacy

Click tới:
https://app.example/help
-> Referer có thể gồm URL nguồn cùng origin

Click tới:
https://support.vendor.example/help
-> Không gửi Referer do khác origin
```

Một `302`/`303` redirect hoặc request phát sinh từ tài nguyên khác có thể khiến policy của nhiều response tham gia; dùng Browser DevTools để xác minh hành vi thật, không suy luận quá mức từ một response trung gian.

### 4.2. Tải image, script, stylesheet, iframe

Referrer policy còn ảnh hưởng tới request subresource trong các điều kiện tương ứng: `img`, `script`, CSS, `iframe`, fetch. CSS được tải từ origin khác có quy tắc referrer policy riêng của stylesheet trong những tình huống nhất định; đừng nghĩ chỉ có click link mới tạo Referer.

Dưới `no-referrer` của document, browser sẽ tránh gửi referrer theo policy đó cho request thuộc phạm vi. **Điều đó không ngăn request subresource được gửi**; tracking script vẫn có thể gọi endpoint riêng nếu được phép. Muốn giảm việc kết nối bên thứ ba cần CSP (ví dụ `connect-src`, `img-src`, `script-src`) và quản lý dependency, không chỉ Referrer-Policy.

### 4.3. Ghi đè theo phần tử khi thật cần

HTML cho phép một số điều khiển cục bộ:

```html
<!-- Link nhạy cảm: không để URL nguồn thành Referer -->
<a href="https://outside.example/help"
   rel="noreferrer noopener">External help</a>

<!-- Chỉ dẫn cục bộ về referrer cho image -->
<img src="https://images.example/banner.png"
     referrerpolicy="no-referrer"
     alt="Banner">

<!-- Referrer policy cho link cụ thể -->
<a href="https://docs.example/"
   referrerpolicy="no-referrer">Documentation</a>
```

`rel="noreferrer"` không gửi Referer cho link đó; `noopener` giảm khả năng tab đích tác động đến window opener ở các tình huống hỗ trợ. Với nội dung HTML giàu link do người dùng cung cấp, còn phải sanitize URL, chống `javascript:` injection và mở tab an toàn.

Một document HTML có thể đặt:

```html
<meta name="referrer" content="no-referrer">
```

Tuy nhiên, **HTTP response header là biện pháp mặc định dễ kiểm soát nhất cho toàn ứng dụng**, vì meta chỉ có tác dụng trong những ngữ cảnh/điểm thời gian mà browser đọc được nó. Không dùng meta thay một chính sách response thống nhất khi HTML có sẵn third-party resources tải sớm.

### 4.4. JavaScript fetch có lựa chọn riêng

```javascript
fetch("/api/account", {
  method: "GET",
  referrerPolicy: "no-referrer"
});
```

Đây là mảnh JS phía browser, không phải code server. Nó chỉ tác động referrer behavior của request đó; **không thay CORS, cookie, authentication, authorization hoặc CSRF**. Web app vẫn cần policy mặc định phù hợp vì không thể tin mọi script luôn gọi fetch với đúng options.

### 4.5. Không dùng Referer làm authentication hoặc CSRF guard duy nhất

Header `Referer` có thể bị browser cố ý lược bỏ theo chính sách hoặc bị client không phải browser tự đặt; không phải bằng chứng mạnh cho user identity. Cần authentication từ Spring Security và CSRF protection theo đúng threat model. Việc server thiếu Referer **không** đủ để kết luận request là tấn công, và Referer có vẻ same-origin **không** chứng minh user đã có quyền.

## 5. Permissions-Policy: giới hạn khả năng của document/iframe

### 5.1. Cơ chế feature gating

`Permissions-Policy` là HTTP response header cho trình duyệt biết **feature API nào được phép** trong document và trong những embedded browsing contexts, theo danh sách origin. Ví dụ:

```http
Permissions-Policy: geolocation=(), camera=(), microphone=()
```

Trong các browser hỗ trợ directive tương ứng, policy này ngăn document và các nested contexts dùng geolocation, camera, microphone. Việc JavaScript gọi API có thể nhận lỗi như `PERMISSION_DENIED` hoặc `NotAllowedError`, thay vì mở permission prompt cho feature bị cấm.

Đây là **một lớp giới hạn**. Browser nào không hỗ trợ directive có thể bỏ qua nó, và Permissions Policy không kiểm soát trực tiếp việc backend trả dữ liệu gì, những request fetch nào được gửi, hoặc hệ điều hành có thiết bị nào.

### 5.2. Cú pháp cơ bản

Một `Permissions-Policy` header chứa các directive **phân cách bằng dấu phẩy**. Mỗi directive đi với một allowlist:

```http
Permissions-Policy: geolocation=(), camera=(), microphone=()
```

| Allowlist | Ý nghĩa |
|---|---|
| `()` | Empty allowlist: chặn feature cho document và những context con phù hợp |
| `(self)` | Cho phép origin hiện tại và các context same-origin phù hợp, trong phạm vi parent policy |
| `("https://maps.example")` | Chỉ định một origin được phép theo chính sách/browser |
| `(self "https://maps.example")` | Kết hợp same-origin và một origin được nêu rõ |
| `*` | Wildcard, cho phép rộng; thường không cần cho feature nhạy cảm |

Lưu ý: origin bên trong allowlist được đặt trong **ngoặc kép**; token `self` không có dấu nháy trong cú pháp HTTP header. Dấu `()` không phải chuỗi rỗng tùy ý để cho phép tất cả — nó biểu thị **cấm feature**.

Một ví dụ có nhu cầu thật:

```http
Permissions-Policy: geolocation=(self), camera=(), microphone=()
```

Nó cho origin của ứng dụng dùng geolocation (vẫn cần quyền người dùng và secure context nếu API yêu cầu) nhưng chặn camera/microphone. Hãy chọn mức hẹp nhất mà sản phẩm cần.

### 5.3. Parent policy và iframe allow

Giả sử trang chính chỉ cho origin của itself sử dụng geolocation:

```http
Permissions-Policy: geolocation=(self)
```

Trang nhúng từ một domain khác:

```html
<iframe src="https://maps.partner.example/"
        allow="geolocation">
</iframe>
```

**Không tự kết luận iframe được phép geolocation**. Parent policy đã hạn chế tập origin được phép. Thuộc tính `allow` của iframe không thể “nới” vượt ngoài giới hạn header của parent; các chính sách được áp theo cơ chế kế thừa/intersection và browser support.

Nếu thật sự cần cho iframe partner một feature, phải:
1. Đánh giá quyền của origin partner và risk.
2. Cấu hình parent `Permissions-Policy` chứa origin partner trong allowlist.
3. Cấu hình `iframe allow` tương ứng theo yêu cầu.
4. Kiểm thử trên browsers được hỗ trợ, vì directive/iframe behavior còn phụ thuộc tính năng và platform.

Ví dụ mô tả:

```http
Permissions-Policy: geolocation=(self "https://maps.partner.example")
```

```html
<iframe src="https://maps.partner.example/"
        allow="geolocation">
</iframe>
```

Dù tất cả policy cho phép, browser vẫn có thể yêu cầu user consent. Không cho `*` nếu chỉ có một iframe cần sử dụng feature.

### 5.4. Khác với user permission prompt

Một số browser API vốn yêu cầu user cấp quyền qua permission prompt. Permissions Policy **chỉ có thể hạn chế** khả năng gọi API trong document; nó không cấp quyền để bỏ qua prompt.

Ví dụ với policy `camera=()`:

```javascript
navigator.mediaDevices.getUserMedia({video: true})
  .then(stream => {
    // Nếu browser cho phép và user đã cấp quyền,
    // stream mới tồn tại. Policy camera=() thông thường ngăn điều này.
    stream.getTracks().forEach(track => track.stop());
  })
  .catch(error => console.log(error.name));
```

Trong môi trường hỗ trợ, camera bị policy chặn có thể trả `NotAllowedError`. Nhưng `NotAllowedError` cũng có thể vì user từ chối, thiếu HTTPS, browser settings hoặc nguyên nhân khác; muốn xác minh policy phải xem response header/browser diagnostics.

Với geolocation:

```javascript
navigator.geolocation.getCurrentPosition(
  position => console.log(position.coords.latitude),
  error => console.log(error.code)
);
```

Một policy chặn feature thường dẫn tới error `PERMISSION_DENIED`. Không lấy tọa độ thật trong bài demo hoặc gửi dữ liệu vị trí qua network mà chưa có sự đồng ý.

### 5.5. Feature Policy cũ khác Permissions Policy mới

Header cũ:

```http
Feature-Policy: geolocation 'self'; camera 'none'
```

Header mới:

```http
Permissions-Policy: geolocation=(self), camera=()
```

Hai header có **cú pháp khác nhau**. Không viết `Permissions-Policy: geolocation 'none'` rồi kỳ vọng trình duyệt áp policy. Một directive không được browser nhận diện có thể bị bỏ qua. Một số directive chỉ hỗ trợ trên một số browser/phiên bản; luôn xem browser compatibility.

### 5.6. Permissions Policy không phải Content Security Policy

- **Permissions Policy**: điều khiển **tính năng browser** (camera/microphone/geolocation, một số APIs khác).
- **CSP**: kiểm soát **nguồn nội dung/script/style/connect/img/frame** theo policy.
- **CORS**: kiểm soát JS cross-origin có đọc được response/sử dụng credential ở một số trường hợp hay không.
- **X-Frame-Options / frame-ancestors**: giới hạn ai được nhúng trang của bạn.
- **Authentication/authorization**: xác định principal/role/resource quyền tại server.

Chẳng hạn `camera=()` không ngăn script gửi dữ liệu DOM bằng `fetch`. Muốn giảm exfiltration qua network, phải có CSP, chống XSS, quản lý script và không cho data nhạy cảm tới bên thứ ba không tin cậy.

## 6. Chiến lược chọn policy cho từng loại sản phẩm

| Loại ứng dụng | Referrer-Policy đề xuất | Permissions-Policy ví dụ | Lý do |
|---|---|---|---|
| Trang tài khoản/khách hàng nhạy cảm | `no-referrer` | `geolocation=(), camera=(), microphone=()` | Giảm tiết lộ origin/URL và khóa tính năng không dùng |
| Cổng quản trị nội bộ cần referrer trong site | `same-origin` | `geolocation=(), camera=(), microphone=()` | Chỉ cho URL referrer cùng origin; không phát ra ngoài |
| Website public cần số liệu referral mức origin | `strict-origin-when-cross-origin` | Chỉ bật feature thật sự cần | Cân bằng analytics và private path/query |
| Ứng dụng bản đồ tự dùng vị trí | `no-referrer` hoặc `same-origin` | `geolocation=(self), camera=(), microphone=()` | Cho phép chỉ geolocation tại origin |
| Video call dùng camera/microphone | Chính sách phù hợp dữ liệu | `camera=(self), microphone=(self)` | Không vô hiệu hóa feature cốt lõi |
| App nhúng trusted iframe dùng tính năng đặc thù | Chính sách theo data classification | Explicit allowlist partner + `iframe allow` | Giảm quyền cross-origin tùy ý |

Các giá trị chỉ là **điểm khởi đầu**. Feature policy có thể làm hỏng tính năng sản phẩm nếu đặt quá chặt. Test theo use case, browser, CDN/reverse proxy, iframe, thiết bị và accessibility. Browser support của từng directive không đồng nhất.

## 7. Cấu hình đúng trong Spring Security WebFlux

### 7.1. WebFlux khác Servlet

Với ứng dụng inbound **Spring WebFlux**, dùng:

- `ServerHttpSecurity` builder.
- `SecurityWebFilterChain`.
- `@EnableWebFluxSecurity` hoặc Spring Boot auto configuration phù hợp.
- Enum `org.springframework.security.web.server.header.ReferrerPolicyServerHttpHeadersWriter.ReferrerPolicy`.

Không sao chép `HttpSecurity`/`SecurityFilterChain` của Servlet vào WebFlux. Dù WebFlux có dùng `WebClient`, loại security inbound vẫn phụ thuộc framework đang xử lý HTTP request.

### 7.2. DSL cấu hình Referrer Policy

Theo Spring Security 6.5 WebFlux docs:

```java
// Snippet trong @Bean SecurityWebFilterChain:
return http
    .headers(headers -> headers
        .referrerPolicy(referrer -> referrer
            .policy(ReferrerPolicy.SAME_ORIGIN)))
    .build();
```

Import `ReferrerPolicy` từ `org.springframework.security.web.server.header.ReferrerPolicyServerHttpHeadersWriter.ReferrerPolicy`.

Khi dùng `SAME_ORIGIN`, browser có thể gửi full URL nội bộ trong Referer, nên đây là **customization nới hơn mặc định `no-referrer` của Spring Security WebFlux 6.5**. Chỉ chọn nếu analytics/UX cần referrer trong site và trang không chứa URL secret nhạy cảm.

Để giữ mức privacy cao:

```java
.referrerPolicy(referrer -> referrer
    .policy(ReferrerPolicy.NO_REFERRER))
```

Chính sách này tương ứng `Referrer-Policy: no-referrer`. Nếu cấu hình WebFlux 6.5 mặc định đã phát no-referrer, không bắt buộc thêm dòng này; nhưng khai báo tường minh có thể hữu ích khi muốn chính sách được review rõ và test không phụ thuộc default tương lai.

### 7.3. DSL cấu hình Permissions Policy

Spring Security WebFlux **không tự thêm Permissions-Policy theo mặc định**. Khai báo:

```java
// Snippet trong @Bean SecurityWebFilterChain:
return http
    .headers(headers -> headers
        .permissionsPolicy(permissions -> permissions
            .policy("geolocation=(), camera=(), microphone=()")))
    .build();
```

`policy(String)` nhận **cú pháp header value**. Spring Security gửi header theo giá trị này; **nó không đảm bảo mọi browser đều hỗ trợ/tuân theo mọi directive**. Không điền Feature-Policy syntax cũ hoặc ngẫu nhiên sửa dấu phẩy thành dấu chấm phẩy giữa directives.

### 7.4. Ghép hai policy mà giữ các header bảo mật mặc định khác

```java
// Mảnh cấu hình bên trong SecurityWebFilterChain
.headers(headers -> headers
    .referrerPolicy(referrer -> referrer
        .policy(ReferrerPolicy.SAME_ORIGIN))
    .permissionsPolicy(permissions -> permissions
        .policy("geolocation=(), camera=(), microphone=()")))
```

DSL này bổ sung/tùy chỉnh các writer thích hợp mà **không cần `headers.disable()`**. Nếu bạn gọi `headers(headers -> headers.disable())`, những header mặc định khác như `X-Content-Type-Options`, HSTS (trên HTTPS), X-Frame-Options và cache controls có thể mất; tránh tắt toàn bộ chỉ để sửa một directive.

### 7.5. Chính sách thuộc những security chains nào?

Khi có nhiều `SecurityWebFilterChain`, một request chỉ đi qua những chain được chọn theo `securityMatcher` và order của security chain. Nếu chỉ đặt header trong chain match `/api/**`, trang HTML `/account` đi qua chain khác có thể không có policy đó. Với gateway/CDN, response header còn có thể bị thêm, bỏ hoặc ghi đè phía ngoài ứng dụng.

Kiểm tra **response cuối cùng browser nhận**, không chỉ class cấu hình Java. Error pages, static resources, redirect và response sinh ở gateway cũng cần chính sách phù hợp. Tránh giả định mọi response không đi qua Spring Security đều tự có headers giống nhau.

## 8. Ví dụ Spring Boot Java 17+ chạy được

Chúng ta tạo ứng dụng có:

- `GET /` và `GET /public` công khai.
- `GET /features` trả HTML để thử browser feature policy.
- `GET /account` yêu cầu HTTP Basic và cho thấy principal.
- Default deny cho URL/HTTP methods không được khai báo.
- Response headers `Referrer-Policy: same-origin` và `Permissions-Policy: geolocation=(), camera=(), microphone=()`.

**Vì sao chọn same-origin trong demo?** Để minh họa việc cấu hình khác default của Spring Security WebFlux 6.5. Với trang có dữ liệu đặc biệt nhạy cảm, ví dụ recovery/identity portal, thay bằng `NO_REFERRER` như mục 7.2. Không đưa secret vào query dù dùng `same-origin`.

### 8.1. Khởi tạo project

Tạo project từ [Spring Initializr](https://start.spring.io/) với Java 17+, Spring Boot 3.5.x, Gradle Groovy DSL và dependencies:

- Spring Reactive Web: `spring-boot-starter-webflux`.
- Spring Security: `spring-boot-starter-security`.
- Spring Boot Starter Test, Spring Security Test.

Giữ cấu hình plugins, repositories, toolchain và Gradle wrapper do Initializr sinh. Phần `dependencies` của `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

Đây là **một block Gradle**, không phải toàn bộ file build độc lập. Không thêm `spring-boot-starter-web` nếu muốn inbound WebFlux: khi cùng có MVC và WebFlux starters, Spring Boot 3.x thường chọn Servlet MVC mặc định.

Cấu trúc:

```text
src/main/java/demo/browserheaders/
  BrowserHeadersApplication.java
  SecurityConfig.java
  PagesController.java
src/test/java/demo/browserheaders/
  BrowserHeadersTests.java
```

### 8.2. BrowserHeadersApplication.java

```java
package demo.browserheaders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BrowserHeadersApplication {
    public static void main(String[] args) {
        SpringApplication.run(BrowserHeadersApplication.class, args);
    }
}
```

### 8.3. SecurityConfig.java

```java
package demo.browserheaders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.header.ReferrerPolicyServerHttpHeadersWriter.ReferrerPolicy;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    public static final String PERMISSIONS =
        "geolocation=(), camera=(), microphone=()";

    @Bean
    public SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET,
                    "/", "/public", "/features").permitAll()
                .pathMatchers(HttpMethod.GET, "/account")
                    .authenticated()
                .anyExchange().denyAll())
            .headers(headers -> headers
                .referrerPolicy(referrer -> referrer
                    .policy(ReferrerPolicy.SAME_ORIGIN))
                .permissionsPolicy(permissions -> permissions
                    .policy(PERMISSIONS)))
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
    }

    @Bean
    public MapReactiveUserDetailsService users() {
        PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

        UserDetails alice = User.withUsername("alice")
            .password(encoder.encode("alice-pass"))
            .roles("USER")
            .build();

        return new MapReactiveUserDetailsService(alice);
    }
}
```

Phân tích cấu hình:

1. `@EnableWebFluxSecurity` cùng `ServerHttpSecurity` bảo vệ inbound WebFlux.
2. Ba GET routes public; `GET /account` authenticated. Các request còn lại bị deny theo policy demo.
3. `ReferrerPolicy.SAME_ORIGIN` tạo header `Referrer-Policy: same-origin`.
4. `permissionsPolicy(...policy(PERMISSIONS))` gửi đúng chuỗi `geolocation=(), camera=(), microphone=()`.
5. HTTP Basic dùng làm phương thức xác thực dễ test; `formLogin` tắt để API không redirect HTML khi thiếu credential.
6. CSRF mặc định không bị tắt; demo không có POST nghiệp vụ. Nếu bạn thêm form/POST, thiết kế token và cookie đúng.
7. User `alice` với password `alice-pass` chỉ để học, được băm bởi DelegatingPasswordEncoder; **không** lưu mật khẩu như thế trong source sản phẩm.
8. HTTP Basic gửi credential base64 trong Authorization, không mã hóa. Production phải dùng HTTPS.
9. Hai response headers là **browser policies**, không thay backend authorization: user chưa xác thực vẫn không được vào `/account`.

### 8.4. PagesController.java

```java
package demo.browserheaders;

import org.springframework.http.MediaType;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class PagesController {

    @GetMapping("/")
    public Mono<String> home() {
        return Mono.just("home");
    }

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public");
    }

    @GetMapping("/account")
    public Mono<String> account() {
        return ReactiveSecurityContextHolder.getContext()
            .map(context ->
                "account:" + context.getAuthentication().getName());
    }

    @GetMapping(value = "/features",
                produces = MediaType.TEXT_HTML_VALUE)
    public Mono<String> features() {
        return Mono.just("""
            <!doctype html>
            <html lang="vi">
            <head>
              <meta charset="utf-8">
              <title>Permissions Policy test</title>
            </head>
            <body>
              <h1>Browser feature permission test</h1>
              <button id="geo">Try geolocation</button>
              <button id="camera">Try camera</button>
              <pre id="result">Ready</pre>
              <script>
                const output = document.getElementById("result");
                document.getElementById("geo").addEventListener(
                  "click", () => {
                    if (!navigator.geolocation) {
                      output.textContent = "Geolocation unavailable";
                      return;
                    }
                    navigator.geolocation.getCurrentPosition(
                      pos => output.textContent = "Position granted",
                      err => output.textContent =
                        "Geolocation error code: " + err.code
                    );
                  });
                document.getElementById("camera").addEventListener(
                  "click", async () => {
                    try {
                      const stream =
                        await navigator.mediaDevices.getUserMedia(
                          { video: true });
                      stream.getTracks().forEach(t => t.stop());
                      output.textContent = "Camera granted";
                    } catch (err) {
                      output.textContent =
                        "Camera error: " + err.name;
                    }
                  });
              </script>
            </body>
            </html>
            """);
    }
}
```

`/features` chỉ là trang **thử feature policy**. Với browser hỗ trợ `geolocation=()`/`camera=()`, thao tác tương ứng thường bị chặn, nhưng chi tiết lỗi phụ thuộc browser, device, secure context và user settings. Không gọi API vị trí/camera tự động khi tải trang: chỉ thử sau khi user bấm nút.

Mặc định Spring Security có các header khác, ví dụ `X-Frame-Options: DENY`; trang này không minh họa iframe. Nếu sản phẩm cần embed trusted iframe, hãy thiết kế cả frame policy lẫn Permissions Policy, không chỉ thêm `allow`.

### 8.5. Chạy demo

```bash
./gradlew bootRun
```

Trên Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Kiểm tra response headers bằng curl:

```bash
curl -i http://localhost:8080/public
```

Phần quan trọng dự kiến:

```http
HTTP/1.1 200 OK
Referrer-Policy: same-origin
Permissions-Policy: geolocation=(), camera=(), microphone=()
Content-Type: text/plain;charset=UTF-8

public
```

Header ordering, case, Content-Type charset và các default security headers khác có thể thay đổi theo server/version; đây là **ví dụ minh họa các giá trị chính**, không phải bản sao toàn bộ response byte-for-byte.

Kiểm tra authenticated resource:

```bash
curl -i http://localhost:8080/account
curl -i -u alice:alice-pass http://localhost:8080/account
```

Dự kiến:
- Không credential: thường **401 Unauthorized** do HTTP Basic challenge.
- Credential đúng: **200 OK**, body `account:alice` và hai policy headers.

Không dùng mật khẩu thật trên dòng lệnh/histories/logs. Lệnh curl chạy với HTTP localhost chỉ dành cho demo; production cần HTTPS và cấu hình secure cookies.

## 9. WebTestClient integration tests

Các test sau **kiểm tra server có xuất response headers đúng** trên những route được bảo vệ bởi `SecurityWebFilterChain`. Chúng không tự kiểm tra browser có áp dụng referrer policy hoặc camera policy như mong đợi; mục 10 hướng dẫn kiểm thử thực tế trên browser.

Tạo file `src/test/java/demo/browserheaders/BrowserHeadersTests.java`:

```java
package demo.browserheaders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class BrowserHeadersTests {

    @Autowired
    WebTestClient client;

    private void expectHeaders(
            WebTestClient.ResponseSpec response) {
        response.expectHeader()
            .valueEquals("Referrer-Policy", "same-origin");
        response.expectHeader()
            .valueEquals("Permissions-Policy",
                SecurityConfig.PERMISSIONS);
    }

    @Test
    void homeIncludesPolicyHeaders() {
        var response = client.get().uri("/").exchange()
            .expectStatus().isOk();

        expectHeaders(response);
        response.expectBody(String.class).isEqualTo("home");
    }

    @Test
    void publicPageIncludesBothHeaders() {
        var response = client.get().uri("/public").exchange()
            .expectStatus().isOk();

        expectHeaders(response);
        response.expectBody(String.class).isEqualTo("public");
    }

    @Test
    void htmlFeaturesPageIncludesPolicies() {
        var response = client.get().uri("/features").exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(
                MediaType.TEXT_HTML);

        expectHeaders(response);
        response.expectBody(String.class)
            .value(body ->
                org.junit.jupiter.api.Assertions.assertTrue(
                    body.contains("Try geolocation")));
    }

    @Test
    void accountWithoutCredentialsNeedsAuthentication() {
        client.get().uri("/account")
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedAccountStillGetsBothHeaders() {
        var response = client.get().uri("/account")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isOk();

        expectHeaders(response);
        response.expectBody(String.class).isEqualTo("account:alice");
    }

    @Test
    void authenticatedUnknownRouteIsDenied() {
        client.get().uri("/unknown")
            .headers(h -> h.setBasicAuth("alice", "alice-pass"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void incomingRefererIsNotAuthorizationCredential() {
        var response = client.get().uri("/public")
            .header("Referer",
                "https://outside.example/page?hint=demo")
            .exchange()
            .expectStatus().isOk();

        expectHeaders(response);
        response.expectBody(String.class).isEqualTo("public");
    }
}
```

Giải thích:

- `expectHeaders` kiểm tra **hai response headers** chứ không phải incoming request header.
- `homeIncludesPolicyHeaders` và `publicPageIncludesBothHeaders` chứng minh public pages vẫn phát policies.
- `htmlFeaturesPageIncludesPolicies` xác minh HTML document nhận header; hiệu lực feature restriction cần browser test.
- `accountWithoutCredentialsNeedsAuthentication` chứng minh header chính sách không cấp authentication.
- `authenticatedAccountStillGetsBothHeaders` xác minh trang protected với principal thật có headers.
- `authenticatedUnknownRouteIsDenied` chứng minh default-deny vẫn vận hành.
- `incomingRefererIsNotAuthorizationCredential` minh họa client có thể tự gửi header Referer tới server; response Referrer-Policy không phải logic tin header này để phân quyền.

Test này dùng `WebTestClient` gọi qua server RANDOM_PORT, kiểm tra response thực tế do Spring Security chain viết ra. Hành vi headers trên 401/403 cũng nên kiểm tra với proxy/gateway trong staging, nhưng không phải giả định tất cả error responses sẽ mang header nếu do một tầng khác trả về.

Chạy:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

**7 test methods** được thiết kế cho project trên. Đây là **kỳ vọng từ mã**, không phải xác nhận test Gradle đã chạy thực tế. Nếu test lỗi, xem dependency versions, loại web stack, security chain matching, actual headers và browser/gateway policy trước khi sửa expected value.

### 9.1. Vì sao không test Referer bằng WebTestClient?

`WebTestClient` là HTTP test client, không phải browser engine. Nó có thể:
- Gửi một header `Referer` do test định nghĩa.
- Xác minh server trả `Referrer-Policy`.
- Xác minh server trả `Permissions-Policy`.

Nó **không tự thực hiện browser navigation, tính Referer theo document policy, hoặc block camera/geolocation**. Vì vậy một test tự gắn `Referer: https://outside.example/...` rồi thấy header ấy xuất hiện **không** chứng minh `Referrer-Policy` mất hiệu lực: server đã nhận một header do client tự tạo.

## 10. Kiểm chứng bằng browser DevTools

### 10.1. Referrer Policy

Một bài test hiệu quả cần hai origin (ví dụ app và một trang thu nhận request do bạn kiểm soát), browser thật và HTTPS tương ứng. Không cần ghi dữ liệu khách hàng thật vào URL.

1. Mở app demo trong Chrome/Firefox/Edge, DevTools → Network.
2. Chọn response `GET /features` hoặc trang HTML cần kiểm tra, xem `Response Headers` có `Referrer-Policy: same-origin`.
3. Trên một trang có link nội bộ hoặc external link của **test environment**, điều hướng link rồi xem **request headers của request đích**. Với `same-origin`, referrer được gửi cho same-origin request theo browser policy và không được gửi cho cross-origin request theo policy đó.
4. Đổi configuration sang `NO_REFERRER`, reload và kiểm tra cả same-origin và cross-origin request không gửi Referer.
5. Đổi sang `STRICT_ORIGIN_WHEN_CROSS_ORIGIN` ở môi trường test, kiểm tra HTTP→HTTPS/HTTPS→HTTPS/HTTPS→HTTP và chỉ origin vs full URL khi phù hợp.
6. Dùng network logs của endpoint test do bạn sở hữu; **không dùng URL thật chứa reset token, mã thanh toán hoặc email cá nhân**.

Khi kiểm tra redirect chains và resource stylesheet, cần nhìn request cụ thể; browser và cache có thể khiến request không được gửi lại nếu asset lấy từ cache.

### 10.2. Permissions Policy

Mở `http://localhost:8080/features` trong browser. Localhost thường được browser coi là secure context cho các API yêu cầu secure context, nhưng điều này tùy browser/setup. Bấm “Try geolocation” và “Try camera”.

Với browser hỗ trợ policy:
- `geolocation=()` thường khiến callback báo lỗi quyền, hay `PERMISSION_DENIED`.
- `camera=()` thường khiến `getUserMedia` reject, có thể với `NotAllowedError`.
- Không kỳ vọng permission prompt mở ra rồi cho phép dùng feature khi policy đã cấm.
- Nếu API không có trên browser/device hoặc page không ở secure context, cần phân biệt nguyên nhân không hỗ trợ với policy deny.

Trong DevTools Console, một số browser có:

```javascript
document.permissionsPolicy?.allowsFeature("geolocation")
```

Giá trị `false` (nếu API này được hỗ trợ và tên directive có hiệu lực) gợi ý feature bị policy cấm. Không phụ thuộc duy nhất vào API này vì mức hỗ trợ khác nhau; có thể gặp `undefined`. Xem response header và thực hiện API call, browser console diagnostics và compatibility table.

### 10.3. Các case iframe

Nếu sản phẩm dùng iframe, test:
- Parent header policy với `geolocation=()` và child iframe có `allow="geolocation"`.
- Parent header `geolocation=(self "https://maps.partner.example")` và iframe `allow` phù hợp.
- Child origin khác/không match.
- Browser không hỗ trợ directive/feature.

Không dùng iframe test ngoài môi trường có quyền kiểm soát origin và người dùng; nhất là với API camera/microphone/vị trí thật.

## 11. HTTPS, HSTS và reverse proxy

### 11.1. Response headers không thay HTTPS

`Referrer-Policy` chỉ kiểm soát một kiểu thông tin trang nguồn; `Permissions-Policy` giới hạn browser features. Chúng không mã hóa kết nối hay ngăn attacker trên đường truyền chỉnh sửa response nếu đang dùng HTTP không an toàn. **Production phải dùng HTTPS** và cấu hình TLS đúng tại gateway/reverse proxy.

### 11.2. HSTS có điều kiện

Spring Security WebFlux cung cấp HSTS theo cấu hình mặc định thích hợp cho **HTTPS responses**, nhưng thường không gửi HSTS trên HTTP request không bảo mật. Đừng test với `curl -i http://localhost` rồi kết luận HSTS của production không tồn tại; hãy test endpoint HTTPS thực và response qua proxy.

HSTS không thay Referrer Policy. HSTS giúp browser ghi nhớ chỉ kết nối HTTPS tới site theo thời hạn/policy; nó không ngăn camera API hay xóa query secret khỏi URL.

### 11.3. TLS termination và forwarded headers

Nếu TLS kết thúc ở load balancer nhưng Spring WebFlux nhìn kết nối nội bộ HTTP, có thể ảnh hưởng scheme, redirect URL, HSTS/cookie security behavior. Chỉ tin `Forwarded` hoặc `X-Forwarded-*` từ reverse proxy đáng tin và cấu hình Spring Boot/Framework cho hạ tầng thực.

Proxy/CDN cũng có thể ghi đè `Referrer-Policy` hoặc `Permissions-Policy`. Trong staging, so sánh:
- Header tại ứng dụng.
- Header tại gateway.
- Header browser cuối cùng nhận.
- Browser behavior sau redirect/static assets/error pages.

### 11.4. Mixed content và external endpoints

Một trang HTTPS tải script/http image không an toàn có thể bị browser chặn hoặc mở ra những nguy cơ khác. Giữ resource HTTPS, CSP phù hợp (như `upgrade-insecure-requests` khi thích hợp), quản lý third-party dependencies và không đặt token vào URL. Referrer Policy mạnh không tự giải quyết mixed content hoặc JavaScript exfiltration.

## 12. Những lớp giảm rò rỉ dữ liệu phải triển khai cùng nhau

### 12.1. Không đưa bí mật vào URL

Tránh:
- `/reset?token=LONG_SECRET` trong các flow không buộc phải dùng link token; nếu cần link, thiết kế token TTL ngắn, dùng một lần, exchange rồi làm sạch URL, policy no-referrer, không cache/log.
- `/api?access_token=...`, `/login?password=...`.
- Session ID đặt trong URL path/query.
- Query PII không cần thiết, ví dụ tên đầy đủ, số căn cước, mã hồ sơ bệnh án.

Trong OAuth2 Authorization Code, callback thường nhận code trong query theo chuẩn flow; bảo vệ bằng state/PKCE, xử lý code ngắn hạn an toàn, giảm log/referrer exposure và không nhầm code với access token. Sau khi xử lý, có thể điều hướng tới URL sạch phù hợp để tránh để lại code trên address bar lâu hơn cần thiết.

### 12.2. Kiểm soát cache

Trang account và response có thông tin nhạy cảm thường dùng:

```http
Cache-Control: no-store
```

Spring Security WebFlux có cache-control defaults cho các response trong chain, nhưng static resources/gateway/custom controller có thể thay chúng. Dữ liệu cần phân vùng cache theo identity/tenant và tuyệt đối tránh shared caching không phân biệt user. `Referrer-Policy` không ngăn browser/cache lưu URL hoặc response body.

### 12.3. CSP và chống XSS

Một `Permissions-Policy: camera=()` không ngăn script đọc text trong DOM rồi gửi bằng `fetch`. Để hạn chế script/exfiltration:
- Dùng CSP chặt, cân nhắc `script-src` nonce/hash, `connect-src`, `img-src`, `frame-src` và `frame-ancestors` theo use case.
- Escape/sanitize output, không đưa untrusted HTML/JS vào DOM.
- Hạn chế third-party scripts, theo dõi supply-chain/SRI khi phù hợp.
- Không ghi credential/tokens vào localStorage hoặc DOM nếu không cần, giảm quyền của script.

Spring Security không thể tự đoán CSP phù hợp cho mọi ứng dụng nên CSP không được thêm như một universal default; cần chính sách rõ và test tính năng thật.

### 12.4. Cookie flags và CSRF

`HttpOnly` giảm nguy cơ JavaScript đọc session cookie; `Secure` yêu cầu HTTPS; `SameSite` hạn chế một số request cross-site. Chúng **bổ sung** nhưng không thay CSRF token. `Referer` không phải chứng cứ user có quyền, nên không dùng `Referrer-Policy` hoặc incoming Referer làm authentication/authorization mechanism.

Nếu app dùng session cookie, vẫn cần CSRF protection trên các phương thức unsafe theo threat model. Referrer Policy được cấu hình `no-referrer` sẽ khiến một số request thiếu Referer một cách hợp lệ; đừng viết CSRF guard tự chế yêu cầu Referer luôn phải có.

### 12.5. Không tin tính năng chặn browser ở backend

Permissions Policy không thay:
- Role/authority trong Spring Security.
- Quyền tenant/resource tại service/database.
- Rate limiting/abuse prevention.
- Quyền truy cập endpoints trên server.
- Kiểm tra form input hoặc API authorization.

Client không phải browser có thể bỏ qua Permissions Policy. Do đó backend phải bảo vệ dữ liệu độc lập, không nghĩ “đã chặn microphone ở browser thì không ai có thể upload audio”.

### 12.6. Quan sát và redaction

Không đưa URL đầy đủ chứa secret vào log/trace/span attributes/analytics. Thiết kế allowlist:
- HTTP method và normalized route template, không raw query nhạy cảm.
- Status code, latency và request ID.
- Security policy version, header name/value không nhạy cảm để audit.
- Origin đã chuẩn hóa nếu business thật sự cần.

Mask hoặc loại bỏ `Authorization`, `Cookie`, `Set-Cookie`, query credentials, reset code và session ID trước khi ghi log, kể cả ở gateway/APM/CDN.

## 13. Cảnh báo và tình huống debug

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Curl thấy `Referrer-Policy` nhưng browser vẫn gửi URL query | Browser nhận header khác ở trang nguồn, policy override, cùng origin cho phép full URL, hoặc response bị gateway thay | Kiểm tra document nguồn, network request đích và policy thực |
| Browser không gửi Referer tới cross-origin | `same-origin` hoặc `no-referrer` đang áp dụng | Đây có thể là hành vi đúng, không phải lỗi navigation |
| Browser vẫn gửi origin tới cross-origin | Dùng `strict-origin-when-cross-origin` | Policy này cho phép origin ở HTTPS cross-origin; chọn `same-origin`/`no-referrer` nếu cần kín hơn |
| Hệ thống analytics mất số liệu referral | Policy quá nghiêm `no-referrer` | Đánh giá nhu cầu, dùng campaign IDs không chứa PII, không mở `unsafe-url` |
| Browser API camera không bị chặn | Browser/feature không hỗ trợ directive, header không tới document, hoặc syntax sai | Kiểm tra compatibility, response headers, document/iframe context |
| Iframe không dùng được geolocation dù có `allow` | Parent policy không allowlist origin | Cập nhật parent policy theo trusted origin và test |
| Header `Permissions-Policy` thiếu | Spring Security không thêm mặc định, hoặc request đi qua chain khác | Cấu hình `headers(...permissionsPolicy(...))` đúng chain |
| Policy viết `camera 'none'` nhưng không tác dụng | Dùng Feature-Policy syntax cũ | Dùng `camera=()` trong Permissions-Policy |
| User vẫn có permission prompt | Feature/policy chưa áp dụng đúng, hoặc yêu cầu API khác | Test browser supported, header, secure context và document |
| Test chỉ bằng WebTestClient luôn pass nhưng browser không chặn | Test chỉ xác minh string header | Thêm browser manual/automation tests trên browser hỗ trợ |
| HSTS không xuất hiện trên `http://localhost` | HSTS chỉ có ý nghĩa trên secure request theo Spring defaults | Test HTTPS qua proxy đáng tin |
| Security headers thiếu trên 404/gateway response | Response không đi qua chain/writer hoặc bị proxy override | Đo final response, cấu hình ở boundary phù hợp |
| `Referrer-Policy` làm server không nhận Referer | Server nhìn request **đã được client gửi**; policy của response chỉ áp dụng browser behavior sau đó | Không dùng response policy để sửa incoming header |
| Có header nhưng token vẫn lộ trong server log | Referrer Policy không xóa request URL/logs | Thiết kế URL và log redaction |
| CSP cấm camera mà Permissions Policy không đổi | CSP không điều khiển mọi feature API giống Permissions Policy | Dùng đúng cơ chế cho từng mục tiêu |
| Camera bị chặn nhưng dữ liệu vẫn bị gửi bằng fetch | Permissions Policy không phải network exfiltration firewall | CSP, chống XSS, bảo vệ dữ liệu và authorization |
| Nhiều response headers trùng/ghi đè | App và gateway cùng cấu hình | Xác định precedence, thống nhất policy, test giá trị cuối |

### 13.1. Debug theo tuyến response

```text
ServerHttpSecurity.headers(...) cấu hình writer
       |
       v
SecurityWebFilterChain xử lý request
       |
       v
Ứng dụng/gateway/CDN viết response
       |
       v
Browser nhận Referrer-Policy + Permissions-Policy
       |
       v
Browser áp dụng policy theo context và mức hỗ trợ
       |
       v
Request kế tiếp / feature API call
       |
       v
Quan sát Referer thật hoặc lỗi feature API
```

Đừng chỉ quan sát một dòng log phía server rồi kết luận browser đã tuân policy. Muốn xác nhận gửi referrer, phải quan sát **request mà browser tạo ra sau đó**. Muốn xác nhận Permissions Policy, phải quan sát browser feature gate thật ở đúng top-level document/iframe.

## 14. Bài tập có đáp án

### Bài 1 — Hai tên header

Một kỹ sư thêm `Referrer-Policy: same-origin` rồi dùng curl gửi `Referer: https://outside.example/path`. Server vẫn nhìn thấy incoming Referer. Config sai không?

**Đáp án:** Không. `Referrer-Policy` trong response chỉ hướng dẫn browser gửi Referer trong các request tiếp theo. Curl tự gửi header do người gọi chỉ định, không thực thi document policy như browser.

### Bài 2 — URL nhạy cảm và strict-origin-when-cross-origin

Trang nguồn `https://app.example/reset?ticket=abc` chuyển tới `https://docs.example/help`. Với `strict-origin-when-cross-origin`, trình duyệt thông thường gửi gì?

**Đáp án:** Chỉ origin `https://app.example/`, không gửi path/query đến cross-origin HTTPS. Tuy nhiên vẫn nên tránh secret trong URL, vì browser history, logs và same-origin links còn có thể thấy nó.

### Bài 3 — Same-origin có ẩn mọi query không?

Trang `https://app.example/account?token=abc` điều hướng tới `https://app.example/help` với `same-origin`. Token có thể đi trong Referer không?

**Đáp án:** Có thể, vì policy cho phép gửi URL nguồn trong request **cùng origin**. Nếu query chứa secret, chọn `no-referrer` và sửa thiết kế URL để không mang secret.

### Bài 4 — Browser default và Spring Security default

Tại sao một website không dùng Spring Security có thể gửi origin cross-site, trong khi WebFlux 6.5 mặc định lại không gửi Referer?

**Đáp án:** Browser thường dùng `strict-origin-when-cross-origin` khi không nhận header. Spring Security WebFlux 6.5 ghi trong tài liệu rằng nó phát `Referrer-Policy: no-referrer` mặc định, làm policy chặt hơn.

### Bài 5 — Geolocation trong iframe

Parent response gửi `Permissions-Policy: geolocation=()`. Iframe bên dưới có `allow="geolocation"`. Có thể tự nới để iframe lấy vị trí không?

**Đáp án:** Không. Iframe allow không vượt được hạn chế của parent policy. Muốn cho trusted iframe dùng geolocation cần parent policy cho origin và iframe allow tương ứng, đồng thời vẫn cần user permission và browser support.

### Bài 6 — Dấu ngoặc của Permissions Policy

`Permissions-Policy: microphone 'none'` có phải cú pháp mới?

**Đáp án:** Không. Đó giống Feature-Policy syntax cũ. Header mới dùng `Permissions-Policy: microphone=()` để cấm.

### Bài 7 — Không có header có phải camera mặc nhiên bị chặn?

**Đáp án:** Không. Từng directive có default allowlist riêng, browser support khác nhau. Ví dụ camera/geolocation thường có default `self` ở một số browser; phải khai báo policy phù hợp nếu muốn khóa.

### Bài 8 — Có policy camera=() nhưng JS vẫn đọc được số dư tài khoản

Permissions Policy có đảm bảo không có exfiltration qua JavaScript không?

**Đáp án:** Không. Nó hạn chế feature camera, không hạn chế mọi network request hay quyền truy cập DOM. Cần CSP, chống XSS, authorization, data minimization và không đưa dữ liệu nhạy cảm vào script untrusted.

### Bài 9 — Phải test gì ngoài header string?

**Đáp án:** Browser request Referer ở same/cross origin, HTTPS downgrade behavior, blocked API calls, iframe delegation, browsers cần hỗ trợ, redirect/gateway/static resources và error responses. WebTestClient chỉ kiểm tra response headers.

### Bài 10 — Policy cho web video call

Nếu app thực sự dùng video call, có nên `camera=(), microphone=()`?

**Đáp án:** Không. Nó phá tính năng cốt lõi. Dùng `camera=(self), microphone=(self)` hoặc allowlist origin được xác minh nếu cần iframe; test prompts/user consent thực tế.

### Bài 11 — Vì sao không dùng Referer để xác thực?

**Đáp án:** Referer có thể bị browser bỏ hợp lệ và client bất kỳ có thể tự tạo. Nó không xác minh identity hoặc quyền. Dùng Spring Security authentication, authorization và CSRF protection đúng thiết kế.

### Bài 12 — Vì sao URL không nên chứa secret dù no-referrer?

**Đáp án:** Referrer-Policy chỉ điều khiển một header khi browser gửi request. Secret trong URL vẫn có thể nằm trong logs, history, browser extensions, crash reports, screenshots, analytics và cache.

### Bài 13 — HSTS không có trên HTTP

Test curl `http://localhost` không thấy `Strict-Transport-Security`. Có nên tắt headers để “fix” không?

**Đáp án:** Không. HSTS thường chỉ được phát cho secure request và có ý nghĩa trên HTTPS. Kiểm tra HTTPS staging/production, proxy TLS termination và forwarded headers trước.

### Bài 14 — Same-origin telemetry có xứng đáng không?

App có nhiều tài liệu nội bộ cùng origin và analytics muốn biết trang nguồn. Có thể chọn `same-origin` thay no-referrer không?

**Đáp án:** Có thể khi business cần và URL không chứa dữ liệu nhạy cảm; chấp nhận rằng path/query trong cùng origin có thể được gửi. Nếu có recovery/auth/payment flows, giữ `no-referrer` hoặc tách policy cho vùng nhạy cảm, nhưng kiểm tra override/gateway và nhất quán trên mọi response.

### Bài 15 — Iframe feature khác backend role

Một iframe được policy cho phép geolocation nhưng HTTP API server yêu cầu role ADMIN. Iframe có tự truy cập API admin được không?

**Đáp án:** Không. Browser feature permission không tạo `Authentication` hay `ROLE_ADMIN`. Backend vẫn phải xác thực và phân quyền độc lập.

## 15. Checklist triển khai production

- [ ] Phân loại các trang/URL nhạy cảm, tránh credential/PII trong path/query.
- [ ] Biết browser default referrer policy và giá trị Spring Security WebFlux thực sự gửi.
- [ ] Chọn `no-referrer` cho trang nhạy cảm trừ khi có lý do rõ để nới; không dùng `unsafe-url`.
- [ ] Nếu dùng `same-origin`, chấp nhận khả năng URL nguồn cùng origin gồm path/query.
- [ ] Header `Referrer-Policy` có trên đúng HTML document/response cần bảo vệ, kể cả qua proxy/CDN.
- [ ] Chọn Permissions Policy theo tính năng sản phẩm, không cấm camera/location khi app thật sự cần.
- [ ] Dùng cú pháp mới `feature=()`, `feature=(self)`, `feature=("https://trusted...")` và phân cách directives bằng dấu phẩy.
- [ ] Parent policy và `iframe allow` có giới hạn nhất quán; không cấp wildcard không cần thiết.
- [ ] Test browser compatibility và quyền người dùng; header support không đồng đều.
- [ ] Không nhầm Permissions Policy với CSP, CORS, authentication hoặc CSRF.
- [ ] Dùng `ServerHttpSecurity.headers(...)`/`SecurityWebFilterChain` đúng WebFlux, không nhầm Servlet.
- [ ] Không vô hiệu toàn bộ default security headers khi chỉ cần thêm một directive.
- [ ] HTTPS, HSTS, TLS termination/forwarded headers/cookie Secure cấu hình đúng môi trường.
- [ ] CSP, XSS prevention, hạn chế script bên thứ ba và `frame-ancestors` theo threat model.
- [ ] Trang account/data riêng có cache control thích hợp; tránh shared CDN cache data nhạy cảm.
- [ ] Log/trace/analytics redaction cho query, Authorization, Cookie và tokens.
- [ ] Không dùng incoming Referer làm credential hoặc duy nhất xác minh CSRF.
- [ ] Unit/integration test server header values và browser test hành vi thực.
- [ ] Kiểm tra redirect, 401/403, 404, static assets, multiple security chains và error response ở gateway.
- [ ] Theo dõi khi nới/siết policy để tránh phá tính năng hợp lệ và privacy regressions.

## 16. Tóm tắt kỹ thuật

```text
Referrer-Policy (response header):
  Điều khiển Referer (request header) mà browser tạo sau đó.

no-referrer:
  Không tiết lộ trang nguồn qua Referer.

same-origin:
  Cho Referer nội bộ cùng origin, không gửi cross-origin.

strict-origin-when-cross-origin:
  Full URL same-origin, chỉ origin cross-origin HTTPS,
  không gửi khi downgrade HTTPS -> HTTP.

Browser default:
  thường strict-origin-when-cross-origin nếu không có policy.

Spring Security WebFlux 6.5 default:
  tài liệu nêu Referrer-Policy: no-referrer.

Permissions-Policy:
  geolocation=()     -> cấm
  camera=()          -> cấm
  microphone=()      -> cấm
  geolocation=(self) -> cho origin của app trong phạm vi policy

Spring WebFlux config:
  ServerHttpSecurity.headers(...)
    .referrerPolicy(...policy(...))
    .permissionsPolicy(...policy("..."))

Không tự suy ra:
  Header xuất ra == browser đã thực thi mọi directive.
  No Referer == request hợp pháp / bất hợp pháp.
  Permissions Policy == backend authentication/authorization.
  Header policy == không có rò rỉ URL/log/DOM/script.
```

**Thông điệp chính:** `Referrer-Policy` giảm lộ **thông tin trang nguồn**, `Permissions-Policy` giảm quyền dùng **browser capabilities**. Chúng là hai phần của phòng vệ nhiều lớp: HTTPS/HSTS, URL không mang secret, CSP, chống XSS, cookie flags, cache control, log redaction và Spring Security authorization phải được thiết kế cùng nhau.

## 17. Tài liệu chính thức

- [Spring Security 6.5 — WebFlux Security Response Headers](https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/headers.html)
- [Spring Security 6.5 — ServerHttpSecurity API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security — HeaderSpec Referrer Policy](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HeaderSpec.ReferrerPolicySpec.html)
- [Spring Security — HeaderSpec Permissions Policy](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.HeaderSpec.PermissionsPolicySpec.html)
- [Spring Security 6.5 — ReferrerPolicyServerHttpHeadersWriter.ReferrerPolicy](https://docs.spring.io/spring-security/site/docs/6.5.x/api/org/springframework/security/web/server/header/ReferrerPolicyServerHttpHeadersWriter.ReferrerPolicy.html)
- [MDN — Referrer-Policy](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referrer-Policy)
- [MDN — Referer request header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Referer)
- [MDN — Permissions-Policy header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy)
- [MDN — Permissions Policy Guide](https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Permissions_Policy)
- [MDN — Geolocation directive](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy/geolocation)
- [MDN — Camera directive](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Permissions-Policy/camera)
- [OWASP — Secure Headers Project](https://owasp.org/www-project-secure-headers/)
- [OWASP — HTTP Security Response Headers Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/HTTP_Headers_Cheat_Sheet.html)
