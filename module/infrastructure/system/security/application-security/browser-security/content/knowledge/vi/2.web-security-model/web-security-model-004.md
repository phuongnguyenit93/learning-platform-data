# Network request trong mô hình bảo mật web

> **Phạm vi học phần:** SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY — phân tích ranh giới bảo mật giữa trình duyệt, origin, cookie và ứng dụng web để hiểu Same-Origin Policy (SOP), CORS và các cơ chế cách ly; từ đó phòng vệ XSS, CSRF, clickjacking bằng CSP, Trusted Types, security headers và kiểm chứng hành vi thực tế.

Một **network request** là yêu cầu do trình duyệt tạo ra khi tải trang, lấy ảnh, gọi API, gửi biểu mẫu hoặc mở kết nối. Với bảo mật web, câu hỏi không chỉ là “máy chủ có trả dữ liệu không?”, mà còn là **ai được phép gửi yêu cầu, cookie nào đi kèm, ai được đọc phản hồi, và phản hồi được phép làm gì trong trang**. Những quyết định này thuộc các lớp khác nhau: trình duyệt, giao thức HTTP, ứng dụng và máy chủ.

## Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt **origin**, **site**, request cùng origin, request khác origin và request khác site.
2. Mô tả vòng đời của một request: khởi tạo → kiểm tra chính sách → gửi HTTP → nhận phản hồi → quyết định quyền truy cập từ JavaScript.
3. Dự đoán khi nào SOP, CORS, preflight, cookie và thuộc tính SameSite tác động đến request.
4. Giải thích vì sao **CORS không thay thế xác thực, phân quyền hoặc chống CSRF**.
5. Dùng DevTools và một demo hai origin để kiểm chứng request thực sự được gửi hay bị chặn, cùng nguyên nhân.

## 1. Ranh giới cần nhận diện trước khi phân tích request

### 1.1 Origin là gì?

Một **origin** là bộ ba **scheme + hostname + port**. Hai URL chỉ **same-origin** khi cả ba thành phần bằng nhau; đường dẫn, query và fragment không quyết định origin.

Giả sử trang hiện tại là **https://shop.example.com/cart**:

| URL đích | So với trang hiện tại | Vì sao? |
|---|---|---|
| https://shop.example.com/api/cart | Same-origin | Cùng HTTPS, host và cổng mặc định 443 |
| https://shop.example.com:8443/api | Cross-origin | Khác cổng |
| https://api.example.com/cart | Cross-origin | Khác hostname |
| http://shop.example.com/cart | Cross-origin | Khác scheme |
| https://shop.example.com/cart?view=short | Same-origin | Chỉ khác query |

**Same-Origin Policy** là tập các giới hạn trình duyệt áp dụng cho tương tác giữa các origin. Ví dụ: JavaScript ở một origin thông thường không thể đọc DOM của iframe khác origin hay đọc body của response từ API khác origin nếu API không cho phép qua CORS. SOP **không đồng nghĩa** với việc trình duyệt cấm mọi request đi sang origin khác.

### 1.2 Site khác origin như thế nào?

**Site** thường được xác định bằng scheme và *registrable domain* (được tính theo Public Suffix List); cổng và subdomain không quyết định site. Đây là khái niệm liên quan trực tiếp đến cookie **SameSite**.

Với trang **https://shop.example.com**:

- **https://api.example.com**: khác **origin**, nhưng cùng **site**.
- **https://shop.example.com:8443**: khác **origin**, nhưng cùng **site**.
- **http://shop.example.com**: khác **origin** và khác **site** theo cách xác định *schemeful same-site*.
- **https://payments.example.net**: khác **origin** và khác **site**.

Vì vậy, **cross-origin không nhất thiết là cross-site**. CORS chủ yếu xét origin; SameSite của cookie xét site. Nhầm lẫn hai khái niệm dễ dẫn đến cấu hình API và CSRF sai.

### 1.3 Các loại request thường gặp

| Cách khởi tạo | Ví dụ | Điểm cần chú ý |
|---|---|---|
| Điều hướng | Nhấp liên kết, đổi location | Trang được điều hướng sang origin khác; không phải đọc API bằng JavaScript |
| Tài nguyên nhúng | Ảnh, CSS, classic script, iframe | Có thể tải từ origin khác theo quy tắc từng loại; SOP, CSP, CORP và MIME vẫn có thể giới hạn |
| API | fetch, XMLHttpRequest | Cross-origin thông thường chịu cơ chế CORS nếu JavaScript muốn đọc response |
| Biểu mẫu HTML | form GET/POST | Có thể tạo cross-origin request mà không cần CORS; đây là đầu vào quan trọng khi phân tích CSRF |
| Kết nối lâu dài | WebSocket, EventSource | Có quy tắc origin riêng; WebSocket không dựa vào CORS và máy chủ cần kiểm tra Origin |
| Request nền | sendBeacon, service worker | Vẫn chịu chính sách và ngữ cảnh trình duyệt tương ứng; service worker không vượt được mọi ranh giới bảo mật |

**Lưu ý:** Tải ảnh cross-origin bằng phần tử HTML có thể thành công dù API không gửi header CORS. Nhưng nếu vẽ ảnh đó lên canvas mà không có điều kiện CORS phù hợp, canvas có thể bị **tainted**, khiến JavaScript không được đọc pixel.

## 2. Một network request đi qua các bước nào?

~~~mermaid
sequenceDiagram
    participant J as Trang / JavaScript
    participant B as Trình duyệt
    participant S as Máy chủ
    J->>B: fetch / form / tải tài nguyên
    Note over B: Xác định origin, mode, credentials, CSP, mixed content
    opt CORS preflight cần thiết
        B->>S: OPTIONS + Origin + Access-Control-Request-*
        S-->>B: Access-Control-Allow-*
        Note over B: Kiểm tra cho phép trước khi gửi request chính
    end
    B->>S: Request chính + headers + cookie nếu đủ điều kiện
    S-->>B: HTTP response + security headers
    Note over B: Kiểm tra CORS, MIME, CORP/CSP, loại tài nguyên...
    B-->>J: Response đọc được hoặc lỗi/opaque response
~~~

### Bước 1: Trang yêu cầu một hành động

Xét đoạn mã:

~~~js
const response = await fetch('https://api.example.com/me', {
  method: 'GET',
  mode: 'cors',
  credentials: 'include'
});
const profile = await response.json();
console.log(profile);
~~~

Trình duyệt xác định URL đích, request **mode**, **credentials**, phương thức, headers, chính sách redirect, origin của trang gọi và loại tài nguyên. Cấu hình **credentials: 'include'** cho phép trình duyệt cân nhắc gửi cookie kể cả cross-origin, **nhưng không vượt qua** SameSite, Secure, chính sách chặn cookie của trình duyệt hoặc điều kiện CORS để đọc response.

Ba giá trị **mode** thường gặp của Fetch:

| Mode | Ý nghĩa thực tế |
|---|---|
| **same-origin** | Request đến origin khác sẽ thất bại |
| **cors** | Có thể gửi cross-origin; JavaScript chỉ đọc response khi kiểm tra CORS thành công |
| **no-cors** | Chỉ cho phép request với những giới hạn nghiêm ngặt; response cross-origin thường là **opaque**, JavaScript không đọc được status thực, headers hay body |

**Không dùng mode: 'no-cors' để “sửa lỗi CORS”.** Đó là cách làm mất khả năng đọc dữ liệu, không phải cách cấp quyền đọc.

### Bước 2: Trình duyệt kiểm tra chính sách trước hoặc trong quá trình tải

Tùy ngữ cảnh, trình duyệt có thể xét:

- **Content Security Policy (CSP):** ví dụ **connect-src** giới hạn đích mà fetch, XHR, WebSocket được phép kết nối; **img-src**, **script-src**, **frame-src** giới hạn loại tài nguyên tương ứng.
- **Mixed content:** trang HTTPS có thể bị ngăn tải nội dung HTTP không an toàn, tùy loại request và các quy tắc nâng cấp/chặn.
- **Sandbox / permission / request destination:** iframe sandbox và từng API có những giới hạn riêng.
- **Service worker:** nếu một service worker hợp lệ kiểm soát trang và request thuộc phạm vi xử lý, nó có thể tham gia xử lý request; nó vẫn chịu ràng buộc bảo mật của nền tảng.

Một request bị CSP chặn có thể **không được gửi ra mạng**. Lỗi này khác lỗi CORS: CORS có thể thất bại **sau khi** máy chủ đã nhận và trả lời request.

### Bước 3: Trình duyệt chuẩn bị HTTP headers và cookie

Ví dụ request có thể mang:

~~~http
GET /me HTTP/1.1
Host: api.example.com
Origin: https://shop.example.com
Accept: application/json
Cookie: session=...
Sec-Fetch-Site: same-site
Sec-Fetch-Mode: cors
Sec-Fetch-Dest: empty
~~~

Đây là ví dụ minh họa, **không phải** mọi request đều có đủ các header trên. Header **Origin** do trình duyệt gắn theo quy tắc của request; **Sec-Fetch-\*** cho biết ngữ cảnh để máy chủ áp dụng chính sách *Fetch Metadata*. Với HTTP client ngoài trình duyệt, các header này có thể bị giả mạo nên **không thay thế xác thực**.

Cookie có được gửi hay không còn tùy phạm vi Domain/Path, Secure, SameSite, thời hạn, chính sách cookie và thiết lập credentials. **HttpOnly** chỉ ngăn JavaScript đọc cookie; nếu request hợp lệ, trình duyệt vẫn có thể tự gửi cookie HttpOnly.

### Bước 4: Có thể có CORS preflight

Một số cross-origin request phải được kiểm tra trước bằng **OPTIONS**. Ví dụ request **PATCH**, thêm header **X-CSRF-Token**, hoặc gửi **Content-Type: application/json** thường không nằm trong nhóm request CORS được miễn preflight.

~~~http
OPTIONS /profile HTTP/1.1
Host: api.example.com
Origin: https://shop.example.com
Access-Control-Request-Method: PATCH
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Máy chủ có thể phản hồi:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://shop.example.com
Access-Control-Allow-Methods: GET, PATCH
Access-Control-Allow-Headers: Content-Type, X-CSRF-Token
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Trình duyệt kiểm tra phản hồi trước khi gửi **PATCH**. Khi preflight bị từ chối, request chính sẽ **không được gửi**. Preflight CORS thông thường **không kèm cookie xác thực**, nên không nên bắt đăng nhập chỉ để trả lời OPTIONS. Cơ chế lưu kết quả preflight có cache riêng, không nên suy luận từ HTTP cache thông thường.

### Bước 5: Máy chủ xử lý request chính

Khi request chính được gửi, máy chủ vẫn phải tự thực hiện **xác thực, phân quyền, kiểm tra CSRF khi phù hợp, xác thực dữ liệu và quy tắc nghiệp vụ**. Việc preflight thành công chỉ có nghĩa chính sách CORS cho phép kiểu request đó; không chứng minh người dùng có quyền sửa dữ liệu.

Với API chứa dữ liệu cá nhân, cần kiểm soát cache thích hợp, ví dụ **Cache-Control: private, no-store** khi dữ liệu không được lưu ở cache.

### Bước 6: Trình duyệt quyết định phản hồi có đọc/hiển thị được không

Response có thể đã đến máy khách nhưng JavaScript vẫn nhận lỗi kiểu **TypeError: Failed to fetch** do CORS. HTTP **403** từ API và **CORS error** là hai sự kiện khác nhau: nếu CORS cho phép đọc một response 403, fetch vẫn trả về một đối tượng Response với **ok = false**; fetch không tự biến mọi mã 4xx/5xx thành lỗi mạng.

Khi đọc phản hồi, còn có các lớp kiểm tra khác: MIME và **X-Content-Type-Options**, CSP, chính sách nhúng **Cross-Origin-Resource-Policy (CORP)**, chính sách cô lập trang **COOP/COEP**, quyền đọc DOM theo SOP. Đừng gom mọi trường hợp “bị trình duyệt chặn” thành lỗi CORS.

## 3. CORS cấp quyền đọc response, không cấp quyền vào hệ thống

### 3.1 CORS hoạt động như thế nào?

**Cross-Origin Resource Sharing (CORS)** là cơ chế HTTP để máy chủ chủ động cho phép trang ở một origin cụ thể truy cập response cross-origin thông qua các API chịu CORS.

Ví dụ trang **https://shop.example.com** gọi **https://api.example.com/me**. Để JavaScript đọc response có credentials, máy chủ cần trả đúng các header, chẳng hạn:

~~~http
Access-Control-Allow-Origin: https://shop.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Nếu dùng **Access-Control-Allow-Origin: \***, response **không thể** được đọc trong request có credentials mode **include**. Không trả nhiều origin phân tách bằng dấu phẩy trong cùng một header; hãy kiểm tra Origin với **allowlist chính xác** và phản hồi đúng một origin được chấp thuận. **Vary: Origin** cần thiết khi phản hồi CORS khác nhau theo Origin và có thể qua cache dùng chung.

Ví dụ middleware Express minh họa kiểm soát CORS:

~~~js
const allowedOrigins = new Set([
  'https://shop.example.com'
]);

app.use('/api', (req, res, next) => {
  const origin = req.get('Origin');

  res.vary('Origin');

  if (origin && allowedOrigins.has(origin)) {
    res.set('Access-Control-Allow-Origin', origin);
    res.set('Access-Control-Allow-Credentials', 'true');
    res.set('Access-Control-Allow-Methods', 'GET, POST, PATCH');
    res.set('Access-Control-Allow-Headers', 'Content-Type, X-CSRF-Token');
  }

  if (req.method === 'OPTIONS') {
    return res.sendStatus(204);
  }

  next();
});

app.patch('/api/profile', authenticate, verifyCsrf, updateProfile);
~~~

**Lưu ý triển khai:** Đây là đoạn minh họa trong ứng dụng Express đã khai báo các hàm middleware. Các endpoint vẫn cần xác thực và phân quyền thật; không tự động tin tưởng mọi request chỉ vì Origin nằm trong allowlist. Phải thống nhất chính sách cho cả phản hồi preflight và phản hồi chính. Không phản chiếu tùy ý Origin người gửi, đặc biệt không coi giá trị **null** như origin đáng tin.

### 3.2 Khi nào request được gửi dù không có CORS?

- **Liên kết và form:** trình duyệt có thể điều hướng hoặc gửi form cross-origin; không cần response cho JavaScript đọc.
- **Ảnh và một số tài nguyên nhúng:** có thể tải theo quy tắc của loại tài nguyên, dù JavaScript không được đọc nội dung thô.
- **Fetch GET cross-origin không preflight:** máy chủ có thể nhận request và xử lý; sau đó trình duyệt chặn mã JavaScript đọc response nếu không có header CORS.
- **Fetch cross-origin cần preflight:** nếu preflight không được duyệt, trình duyệt thường không gửi request chính.

Điểm mấu chốt: **“JavaScript không đọc được phản hồi” khác hoàn toàn với “máy chủ không nhận request”.** Đây là lý do CORS không thể thay thế bảo vệ CSRF.

### 3.3 CORS không phải tường lửa API

Các ứng dụng **curl**, ứng dụng mobile, backend service và client tùy biến không phải triển khai quy tắc bảo vệ web của trình duyệt. Chúng có thể gửi HTTP đến API ngay cả khi API không bật CORS. Máy chủ cần tự bảo vệ endpoint bằng session/token, authorization, rate limit, validation và logging thích hợp.

## 4. Cookies, credentials và nguy cơ CSRF

### 4.1 Cookie là trạng thái mà trình duyệt tự gắn vào request

Ví dụ session cookie ưu tiên cho ứng dụng cùng site:

~~~http
Set-Cookie: __Host-session=RANDOM_VALUE; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- **Secure:** chỉ gửi qua kết nối an toàn theo quy tắc trình duyệt.
- **HttpOnly:** JavaScript không đọc trực tiếp cookie qua document.cookie; XSS vẫn có thể tạo các request mang session của nạn nhân.
- **SameSite=Strict:** hạn chế gửi cookie trong ngữ cảnh cross-site chặt chẽ hơn.
- **SameSite=Lax:** thường gửi cho yêu cầu same-site và một số điều hướng top-level cross-site dùng phương thức an toàn, như GET; không nên xem là lớp phòng vệ CSRF duy nhất.
- **SameSite=None; Secure:** cho phép dùng cookie ở ngữ cảnh cross-site khi trình duyệt/chính sách quyền riêng tư cho phép; cookie bên thứ ba vẫn có thể bị chặn.
- **__Host-** prefix: yêu cầu Secure, Path=/ và không có Domain; giúp thu hẹp rủi ro liên quan đến phạm vi cookie.

Hai origin khác nhau nhưng cùng site vẫn có thể chia sẻ ngữ cảnh SameSite. Cookie **host-only** không tự động được gửi đến mọi subdomain, vì phạm vi Domain của cookie là một quy tắc khác.

### 4.2 Ví dụ tấn công CSRF

Giả sử người dùng đăng nhập vào một ứng dụng chuyển tiền, server chỉ dựa vào cookie session và chấp nhận form POST thay đổi trạng thái. Trang độc hại có thể dụ trình duyệt gửi:

~~~html
<form action="https://bank.example.com/transfer" method="POST">
  <input type="hidden" name="to" value="attacker">
  <input type="hidden" name="amount" value="1000">
  <button>Tiếp tục</button>
</form>
~~~

Trình duyệt có thể gửi form cross-origin **mà không cần CORS**. Tấn công thành công hay không còn phụ thuộc cookie có được gửi theo SameSite và chính sách trình duyệt hay không, và máy chủ có yêu cầu token hay xác minh Origin hay không. Kẻ tấn công **không cần đọc response** để thao tác thay đổi trạng thái gây hại.

### 4.3 Phòng vệ nhiều lớp cho request thay đổi trạng thái

1. **Không thay đổi dữ liệu bằng GET**; chọn method theo ngữ nghĩa, nhưng nhớ POST/PATCH cũng cần phòng vệ.
2. **CSRF token** liên kết đúng session và được kiểm tra ở máy chủ, hoặc một thiết kế xác thực tương đương không phụ thuộc cookie gửi tự động.
3. **Kiểm tra Origin** cho các endpoint nhạy cảm; cân nhắc Referer khi phù hợp, nhưng header có thể vắng và phải có chính sách fallback rõ ràng.
4. **SameSite=Lax/Strict** khi luồng sản phẩm cho phép; hiểu giới hạn từ request same-site ở subdomain khác.
5. **Fetch Metadata** (như Sec-Fetch-Site) có thể dùng để từ chối request cross-site không phù hợp; phải xử lý client không gửi những header này và các luồng hợp lệ từ bên thứ ba.
6. **Xác thực, phân quyền và xác nhận giao dịch quan trọng** vẫn cần độc lập với CSRF.

Nếu frontend và API **khác origin nhưng cùng site**, có thể cần CORS để frontend đọc response, trong khi cookie SameSite vẫn được xét là same-site. Nếu thực sự **cross-site**, sử dụng cookie phụ thuộc **SameSite=None; Secure**, khả năng chặn third-party cookie và chính sách riêng tư hiện hành; cân nhắc proxy cùng origin hoặc cơ chế đăng nhập phù hợp thay vì dựa hoàn toàn vào third-party cookie.

## 5. Các lớp phòng vệ có liên quan trực tiếp đến request

| Lớp | Bảo vệ chính | Không tự giải quyết |
|---|---|---|
| **TLS/HTTPS + HSTS** | Bảo mật đường truyền và giảm nguy cơ truy cập HTTP không an toàn | XSS, lỗi phân quyền |
| **SOP** | Giới hạn mã trang đọc dữ liệu/DOM khác origin | Chặn mọi cross-origin request |
| **CORS** | Máy chủ cấp quyền cho origin khác đọc response của API chịu CORS | CSRF, xác thực, phân quyền |
| **SameSite + cookie flags** | Kiểm soát việc trình duyệt gửi/cho JS đọc cookie | Mọi dạng CSRF/XSS |
| **CSP** | Hạn chế nguồn script, kết nối, frame và một số hành vi nguy hiểm | Thay thế encode/sanitize đầu vào, đầu ra |
| **Trusted Types** | Giảm DOM XSS bằng kiểm soát dữ liệu đi vào một số DOM sink nguy hiểm (ở trình duyệt hỗ trợ) | Tự sửa mọi XSS, nhất là XSS phía server |
| **frame-ancestors / X-Frame-Options** | Giới hạn trang nào được nhúng ứng dụng, chống clickjacking | Ngăn iframe ngoài ý muốn được tạo từ phía chính ứng dụng |
| **CORP/COEP/COOP** | Kiểm soát tải tài nguyên cross-origin và cách ly browsing context | Thay thế quyền API hoặc CORS |
| **Fetch Metadata** | Cho server biết ngữ cảnh nguồn request để từ chối request không mong muốn | Xác minh danh tính người dùng |

### 5.1 CSP và Trusted Types

Ví dụ chính sách được trả về dưới dạng **HTTP response header**:

~~~http
Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-PER_RESPONSE_RANDOM'; connect-src 'self' https://api.example.com; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; require-trusted-types-for 'script'
X-Content-Type-Options: nosniff
Referrer-Policy: strict-origin-when-cross-origin
~~~

Giá trị nonce ở trên chỉ là chỗ giữ chỗ: ứng dụng thực tế phải **tạo nonce khó đoán, mới cho mỗi response** và gắn đúng vào script được phép. CSP phải được điều chỉnh theo tài nguyên thực tế; một chính sách quá rộng như **script-src 'unsafe-inline'** có thể làm suy yếu phòng vệ XSS.

**Trusted Types** hỗ trợ kiểm soát một số DOM sink như việc gán HTML động. Cần kết hợp với code an toàn, encode theo ngữ cảnh và sanitization đáng tin cậy; chính sách có tác dụng tùy trình duyệt hỗ trợ. Nếu sử dụng, cần kiểm thử khả năng tương thích trước khi bật chặn toàn bộ.

### 5.2 Clickjacking và chính sách nhúng

Trang giao dịch nhạy cảm có thể đặt:

~~~http
Content-Security-Policy: frame-ancestors 'none'
X-Frame-Options: DENY
~~~

**frame-ancestors** kiểm soát những trang được phép nhúng trang hiện tại; nó **không phải** là **frame-src** (kiểm soát iframe mà trang hiện tại được phép tải). Chỉ thị frame-ancestors phải được gửi trong **HTTP header**, không có hiệu lực khi đặt trong CSP của thẻ meta. X-Frame-Options là cơ chế tương thích cũ; nên dùng nhất quán với frame-ancestors.

### 5.3 CORP, COEP và COOP

- **Cross-Origin-Resource-Policy: same-origin / same-site / cross-origin** thể hiện chính sách tài nguyên đối với một số trường hợp tải cross-origin ở chế độ no-cors.
- **Cross-Origin-Embedder-Policy: require-corp** yêu cầu tài nguyên cross-origin nhúng phải thỏa điều kiện CORS/CORP thích hợp; cấu hình thiếu có thể khiến ảnh, font hoặc script của bên thứ ba không tải.
- **Cross-Origin-Opener-Policy: same-origin** giúp tách browsing context khỏi một số trang mở qua window; có thể ảnh hưởng luồng popup/đăng nhập và cần thử nghiệm trước khi triển khai.

Các header này phục vụ **cách ly và giảm rò rỉ giữa các origin**. Chúng không có nghĩa “bật lên thì toàn bộ API được bảo vệ”.

### 5.4 WebSocket cần kiểm tra Origin riêng

WebSocket dùng một HTTP handshake để nâng cấp kết nối, nhưng **không được bảo vệ bằng CORS theo cách fetch/XHR được bảo vệ**. Nếu WebSocket dựa trên cookie session, máy chủ phải kiểm tra **Origin**, xác thực và quyền sử dụng kết nối; chỉ dựa vào cookie có thể dẫn tới *Cross-Site WebSocket Hijacking*. Không xem header Access-Control-Allow-Origin là cơ chế chặn WebSocket.

## 6. Thực hành: kiểm chứng request bằng hai origin trên localhost

Bài thực hành này dùng hai máy chủ HTTP đơn giản, không cần package ngoài Node.js:

- **http://localhost:3000** phục vụ trang web.
- **http://localhost:4000** phục vụ API. Hai địa chỉ khác **origin** vì khác cổng.

Lưu đoạn mã dưới đây thành **network-request-demo.mjs**, sau đó chạy **node network-request-demo.mjs** và mở **http://localhost:3000** trong trình duyệt. Đây là demo kỹ thuật trên localhost, không phải cấu hình production.

~~~js
import { createServer } from 'node:http';

const page = [
  '<!doctype html>',
  '<html lang="vi"><meta charset="utf-8">',
  '<title>Network request demo</title>',
  '<h1>Thử CORS trên hai origin</h1>',
  '<button id="get-blocked">GET thiếu CORS</button>',
  '<button id="get-ok">GET có CORS</button>',
  '<button id="post-blocked">POST JSON thiếu CORS</button>',
  '<button id="post-ok">POST JSON có CORS</button>',
  '<pre id="result"></pre>',
  '<script>',
  'async function run(method, cors) {',
  '  const url = "http://localhost:4000/api?cors=" + cors;',
  '  const options = method === "POST"',
  '    ? { method: "POST", headers: { "Content-Type": "application/json" },',
  '        body: JSON.stringify({ message: "hello" }) }',
  '    : { method: "GET" };',
  '  try {',
  '    const response = await fetch(url, options);',
  '    document.querySelector("#result").textContent =',
  '      "HTTP " + response.status + ": " + await response.text();',
  '  } catch (error) {',
  '    document.querySelector("#result").textContent = String(error);',
  '  }',
  '}',
  'document.querySelector("#get-blocked").onclick = () => run("GET", "off");',
  'document.querySelector("#get-ok").onclick = () => run("GET", "on");',
  'document.querySelector("#post-blocked").onclick = () => run("POST", "off");',
  'document.querySelector("#post-ok").onclick = () => run("POST", "on");',
  '</script></html>'
].join('\n');

createServer((_req, res) => {
  res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8' });
  res.end(page);
}).listen(3000, () => console.log('Page: http://localhost:3000'));

createServer((req, res) => {
  const url = new URL(req.url, 'http://localhost:4000');
  if (url.pathname !== '/api') {
    res.writeHead(404);
    return res.end('Not found');
  }

  console.log(req.method, url.pathname, url.search);
  const allowed = url.searchParams.get('cors') === 'on';

  if (allowed) {
    res.setHeader('Access-Control-Allow-Origin', 'http://localhost:3000');
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST');
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
    res.setHeader('Vary', 'Origin');
  }

  if (req.method === 'OPTIONS') {
    res.writeHead(204);
    return res.end();
  }

  res.writeHead(200, { 'Content-Type': 'application/json' });
  res.end(JSON.stringify({ receivedMethod: req.method, cors: allowed }));
}).listen(4000, () => console.log('API: http://localhost:4000'));
~~~

**Cách quan sát:** mở **DevTools → Network**, giữ tab **Console** và thực hiện lần lượt bốn nút. Có thể lọc theo **Fetch/XHR** và xem request headers, response headers, phương thức OPTIONS, trạng thái cùng thông báo CORS. Không cần extension để tắt bảo vệ trình duyệt.

| Thao tác | API nhận được gì? | JavaScript đọc response? | Điều cần kết luận |
|---|---|---|---|
| GET thiếu CORS | GET tới /api | Không | Request đã gửi; response bị CORS chặn với script |
| GET có CORS | GET tới /api | Có | Origin của trang được API cấp quyền đọc |
| POST JSON thiếu CORS | OPTIONS; **không có POST chính** | Không | Preflight không hợp lệ nên trình duyệt dừng trước POST |
| POST JSON có CORS | OPTIONS rồi POST (hoặc sử dụng cache preflight phù hợp) | Có | Preflight và phản hồi chính đều hợp lệ |

**Quan sát thêm:**

1. Xem header **Origin: http://localhost:3000** trong request cross-origin.
2. Với POST JSON, kiểm tra **Access-Control-Request-Method: POST** và **Access-Control-Request-Headers: content-type** trên OPTIONS.
3. Thử sửa header **Access-Control-Allow-Origin** thành origin sai rồi tải lại; giải thích sự thay đổi.
4. Thử thêm **mode: 'no-cors'** vào một GET và quan sát loại response **opaque**; đừng mong đọc được body.
5. Trong terminal dùng **curl http://localhost:4000/api?cors=off**. curl vẫn nhận JSON vì CORS là chính sách truy cập dữ liệu ở trình duyệt, không phải kiểm soát quyền cho mọi HTTP client.

Ví dụ thực hành trên **localhost** không dùng cookie/session. Khi thử CSRF thực tế, hãy xây dựng **môi trường kiểm thử riêng**, dùng dữ liệu giả, chủ động đối chiếu **Origin**, **SameSite**, **Sec-Fetch-Site** và token CSRF; tránh kiểm thử trên tài khoản hoặc hệ thống của người khác.

## 7. Chẩn đoán theo triệu chứng

| Triệu chứng | Nên kiểm tra trước | Cách xử lý đúng bản chất |
|---|---|---|
| Console báo lỗi CORS, Network vẫn thấy GET | Origin, Access-Control-Allow-Origin của response chính | Cấu hình allowlist origin ở API, không tắt CORS trong browser |
| Chỉ thấy OPTIONS, không thấy POST/PATCH | Access-Control-Allow-Methods/Headers/Origin của preflight | Sửa đáp ứng preflight theo method và header thực tế |
| CORS đúng nhưng cookie không được gửi | Fetch credentials, Domain/Path, Secure, SameSite, third-party cookie policy | Sửa thiết kế session và phạm vi cookie tương ứng |
| CORS được phép nhưng API trả 401/403 | Cookie/token, phân quyền ở server | Xử lý xác thực và authorization, không nới CORS |
| Request không xuất hiện trong Network | CSP, mixed content, code chưa chạy, extension/chính sách browser | Kiểm tra Console và CSP violation |
| Ảnh hiển thị nhưng canvas không đọc pixel | CORS của ảnh và thuộc tính crossOrigin | Cấu hình tải ảnh theo CORS từ cả client và server khi cần đọc pixel |
| Trang không được nhúng trong iframe | frame-ancestors, X-Frame-Options | Cho phép origin nhúng một cách có chủ đích, nếu nghiệp vụ cần |
| Tài nguyên bên thứ ba lỗi sau khi bật cô lập | CORP, COEP, CORS, loại tài nguyên | Chọn header thích hợp và thử lại luồng tích hợp |
| WebSocket kết nối trái phép từ trang khác | Origin và xác thực tại handshake | Kiểm tra Origin bằng allowlist và bảo vệ session phía server |

## 8. Tự kiểm tra kiến thức

**Tình huống A.** Trang **https://app.example.com** gọi **https://api.example.com** bằng fetch. Hai host cùng site nhưng khác origin. API trả JSON 200 mà không có Access-Control-Allow-Origin. JavaScript có đọc được JSON không?

**Đáp án:** Không, với request fetch theo cơ chế CORS thông thường. Cùng site không có nghĩa là same-origin. Máy chủ vẫn có thể đã xử lý và trả request.

**Tình huống B.** Một API bật **Access-Control-Allow-Origin: \***. Người dùng gọi fetch cross-origin với **credentials: 'include'**. JavaScript có được đọc phản hồi không?

**Đáp án:** Không; wildcard không được dùng cho response mà trình duyệt cần chia sẻ với credentials mode include. Cần trả một origin chính xác được cho phép cùng header credentials phù hợp. Cookie thực tế có được gửi còn phụ thuộc chính sách cookie.

**Tình huống C.** Một endpoint chuyển tiền POST không có CSRF token. Đội phát triển tắt CORS trên server. Endpoint đã an toàn trước CSRF chưa?

**Đáp án:** Chưa. Cross-origin form vẫn có thể gửi request, không cần đọc response. Cần kiểm tra CSRF, Origin/Fetch Metadata khi phù hợp, SameSite và các biện pháp bảo vệ nghiệp vụ.

**Tình huống D.** DevTools báo request bị **connect-src** chặn. Thêm Access-Control-Allow-Origin ở API có giúp không?

**Đáp án:** Không. CSP của trang gọi đã giới hạn đích kết nối. Phải đánh giá và sửa CSP ở nơi phục vụ trang, nếu đích thực sự đáng tin và cần thiết.

**Tình huống E.** Bật HttpOnly cho session cookie đã chặn mọi hậu quả của XSS chưa?

**Đáp án:** Chưa. HttpOnly hạn chế đọc trực tiếp giá trị cookie, nhưng script độc hại chạy trong origin của ứng dụng vẫn có thể thao tác DOM và khởi tạo request mà trình duyệt tự đính kèm session hợp lệ. Cần phòng XSS bằng encode/sanitize, CSP, Trusted Types khi được hỗ trợ và kiểm soát quyền phía server.

## Ghi nhớ

Phân tích một network request theo **bốn câu hỏi riêng biệt**:

1. **Request có được trình duyệt khởi tạo và gửi không?** Kiểm tra CSP, mixed content, preflight, loại tài nguyên.
2. **Thông tin xác thực nào đi kèm?** Kiểm tra credentials, cookie flags, SameSite, Origin, chính sách trình duyệt.
3. **Máy chủ có chấp nhận thao tác không?** Kiểm tra authentication, authorization, CSRF, validation.
4. **Mã JavaScript có được đọc hoặc sử dụng response không?** Kiểm tra SOP, CORS, response type, MIME và chính sách cách ly.

Chỉ khi tách được bốn câu hỏi này, ta mới phân biệt đúng **“request bị chặn”**, **“request đã tới server nhưng bị từ chối”** và **“server đã trả dữ liệu nhưng trình duyệt không cho script đọc”**.
