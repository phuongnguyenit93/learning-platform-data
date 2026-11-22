# Kiểm thử behavior ở browser thật

## 1. Vì sao phải kiểm thử CORS trong browser thật?

Cross-Origin Resource Sharing (CORS) là cơ chế do browser thực thi để kiểm soát JavaScript ở một origin có được đọc response từ origin khác hay không. Cấu hình CORS ở backend có thể trông đúng trong unit test hoặc khi gọi bằng curl, nhưng hành vi thực tế còn phụ thuộc vào same-origin policy, preflight, credential mode, cookie policy, cache, redirect và browser engine.

Một API trả Access-Control-Allow-Origin đúng chưa chắc ứng dụng browser đọc được response. Ngược lại, browser có thể gửi request đến server nhưng chặn JavaScript đọc response. Hai tình huống này khác nhau về tác động bảo mật và cần được kiểm thử riêng.

Các lỗi thường gặp:

- Backend cho phép origin nhưng thiếu header trên response lỗi 401, 403, 429 hoặc 500.
- Request đơn giản được gửi tới server dù response sau đó bị browser chặn.
- Request có Authorization hoặc Content-Type: application/json cần preflight nhưng OPTIONS bị authentication middleware từ chối.
- CORS cho phép credentials nhưng dùng wildcard origin hoặc thiếu Access-Control-Allow-Credentials.
- Cookie bị browser chặn do SameSite, Secure hoặc third-party cookie policy dù CORS header hợp lệ.
- Response header có trong HTTP response nhưng JavaScript không được phép đọc vì thiếu Access-Control-Expose-Headers.
- Preflight cache khiến kết quả test khác nhau giữa browser context mới và context đã gọi API.
- Redirect hoặc proxy làm origin thực tế khác với origin được kiểm tra.
- Test dùng curl, Postman hoặc HTTP client nên không hề chạy same-origin policy.

Trong phạm vi SECURITY_API_SECURITY, CORS cần được kiểm thử ở nơi nó được thực thi: browser. Test phải xác nhận cả request có được gửi hay không, server nhận gì, browser cho JavaScript đọc response hay không và cookie/credential có thực sự được gửi hay không.

Sau bài học này, người học có thể:

1. Tạo test environment với hai origin thực sự khác nhau.
2. Kiểm tra same-origin policy, CORS-safelisted request và preflight.
3. Kiểm tra credentials, cookie, exposed response headers và cache.
4. Phân biệt CORS failure với authentication, authorization, network và application failure.
5. Kiểm thử Fetch, XMLHttpRequest, EventSource, WebSocket và browser resource APIs.
6. Viết browser automation bằng Playwright hoặc công cụ tương đương.
7. Thiết kế test matrix chạy trên nhiều browser engine và xác minh cấu hình production.

## 2. Browser thực thi CORS như thế nào?

Browser áp dụng same-origin policy để giới hạn việc một document hoặc script đọc tài nguyên từ origin khác. Origin được xác định bởi bộ ba:

- Scheme, ví dụ https.
- Host, ví dụ app.example.test.
- Port, ví dụ 443.

Ba URL sau có origin khác nhau:

| URL thứ nhất | URL thứ hai | Lý do khác origin |
|---|---|---|
| https://app.example.test | http://app.example.test | Khác scheme |
| https://app.example.test | https://api.example.test | Khác host |
| https://app.example.test | https://app.example.test:8443 | Khác port |

Path không tham gia vào origin. https://app.example.test/home và https://app.example.test/profile vẫn cùng origin.

CORS là cơ chế cho phép server nới lỏng một phần giới hạn đọc dữ liệu cross-origin. Server phản hồi bằng các HTTP response header; browser đọc các header đó và quyết định có trao response cho JavaScript hay không.

### 2.1. CORS không phải là firewall cho request

Với một số request đơn giản, browser gửi request cross-origin trước rồi mới kiểm tra response. Nếu response không có CORS header hợp lệ, JavaScript không đọc được response, nhưng request có thể đã tới server và gây side effect.

Ví dụ một form POST với content type được safelist có thể được gửi mà không cần preflight. Nếu server thực hiện chuyển tiền chỉ dựa vào việc browser có đọc được response hay không, thiết kế đó không an toàn.

Vì vậy:

- CORS kiểm soát khả năng JavaScript đọc response.
- Authentication xác minh caller hoặc credential.
- Authorization quyết định caller có quyền thực hiện hành động.
- CSRF protection bảo vệ endpoint dùng ambient credentials như cookie khỏi request được kích hoạt từ site khác.
- Rate limit và validation bảo vệ tài nguyên và dữ liệu.

Không dùng CORS thay cho authorization hoặc CSRF defense.

### 2.2. Phân biệt origin và site

Origin và site không giống nhau. app.example.test và api.example.test khác origin nhưng thường cùng site theo cách browser tính schemeful site. Điều này ảnh hưởng cookie SameSite.

Khi kiểm thử, cần tạo riêng tình huống:

- Cross-origin nhưng same-site: hai subdomain khác nhau.
- Cross-site: hai registrable domain khác nhau.
- Same-origin: cùng scheme, host và port.

Nếu chỉ test hai subdomain, bạn có thể kiểm tra CORS nhưng chưa kiểm tra đầy đủ hành vi cookie cross-site.

## 3. Chuẩn bị môi trường test có hai origin

Browser test phải chạy từ một trang được tải ở origin A và gọi API ở origin B. Không chỉ tạo hai URL giả trong test code; hai server phải thực sự lắng nghe và browser phải phân biệt chúng.

Ví dụ:

| Vai trò | Origin |
|---|---|
| Web application | https://app.example.test |
| API | https://api.other.test |
| Untrusted web origin | https://attacker.other.test |
| Same-site API variant | https://api.example.test |

Có thể ánh xạ các hostname test vào loopback trong môi trường local và dùng certificate phù hợp. Với test cookie Secure, SameSite=None và HTTPS behavior, nên dùng HTTPS local thay vì phụ thuộc vào ngoại lệ của localhost.

### 3.1. Không dùng file:// để kiểm thử CORS

Trang mở từ file:// có thể có origin opaque hoặc được browser biểu diễn thành null. Điều này không đại diện cho web application production thông thường và có thể tạo kết quả khó hiểu.

Dùng web server thực để phục vụ trang test. Không cấu hình allowlist production cho origin null chỉ để test file local.

### 3.2. Tách API test fixture khỏi API nghiệp vụ

API fixture nên cung cấp các endpoint có hành vi xác định:

- Endpoint trả JSON và CORS allow.
- Endpoint không có CORS header.
- Endpoint chỉ cho phép một origin cụ thể.
- Endpoint yêu cầu preflight.
- Endpoint cho phép credentials.
- Endpoint trả response header cần expose.
- Endpoint trả 401, 403, 429 và 500.
- Endpoint redirect sang cùng origin hoặc origin khác.
- Endpoint ghi lại request method/header để test xác nhận server đã nhận request nào.

Không dùng dữ liệu production hoặc credential thật trong fixture. Ghi log test nên có request ID và metadata cần thiết, không lưu raw secret.

### 3.3. Đảm bảo request thực sự đi qua browser

Dùng Playwright page.evaluate, thao tác trên UI hoặc Selenium/WebDriver để tạo request từ trang đã load. Không thay bằng:

- curl.
- Postman.
- Java HttpClient.
- Playwright APIRequestContext.
- Test gọi trực tiếp controller bằng MockMvc mà không có browser.

Các công cụ này hữu ích cho API contract hoặc integration test, nhưng không tự thực thi đầy đủ browser CORS behavior.

### 3.4. Không cố tự đặt Origin từ JavaScript

JavaScript trong browser không được tự do đặt Origin request header. Browser tự tạo giá trị này từ document origin. Đây là một lý do quan trọng để test bằng trang thật: test phải quan sát Origin do browser gửi, không giả lập bằng header do test code tự gán.

## 4. Request đơn giản và preflight

Browser có thể gửi một số CORS-safelisted request mà không gửi preflight. Những request khác cần gửi OPTIONS trước để hỏi server xem method và request header có được phép không.

### 4.1. CORS-safelisted request

Một request có thể không cần preflight nếu method, header và giá trị header thỏa điều kiện safelist. Những trường hợp phổ biến:

- Method là GET, HEAD hoặc POST.
- Request header chỉ gồm các header safelisted và các điều kiện giá trị tương ứng được đáp ứng.
- Content-Type nằm trong một số media type được safelist như application/x-www-form-urlencoded, multipart/form-data hoặc text/plain.

Không nên gọi mọi POST là simple request. Ví dụ POST với Content-Type: application/json thường cần preflight. Thêm header Authorization, X-Request-ID hoặc một application-specific header cũng thường khiến browser preflight.

### 4.2. Preflight request

Khi cần preflight, browser gửi request OPTIONS đến API. Ví dụ:

```http
OPTIONS /v1/orders HTTP/1.1
Host: api.other.test
Origin: https://app.example.test
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization, content-type
```

Server có thể trả:

```http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: Authorization, Content-Type
Access-Control-Max-Age: 300
Vary: Origin
```

Sau khi preflight thành công, browser mới gửi request thực tế. Nếu preflight thất bại, request method thực tế thường không được gửi.

### 4.3. Preflight không phải request nghiệp vụ

Preflight là request do browser tạo để kiểm tra quyền CORS. Server không nên yêu cầu user access token hoặc session cookie trên preflight như thể đó là request nghiệp vụ. Preflight thường không mang credential của request cross-origin; middleware authentication có thể chặn OPTIONS trước khi CORS middleware trả lời.

Cần cấu hình CORS xử lý preflight ở đúng vị trí trong middleware chain. Điều này không có nghĩa mở mọi OPTIONS operation cho anonymous access: preflight chỉ trả metadata CORS, còn request thực tế vẫn phải authentication và authorization.

### 4.4. Kiểm tra cả preflight và actual request

Khi test request cần preflight, ghi nhận hai sự kiện:

1. Browser gửi OPTIONS với Origin, requested method và requested headers đúng.
2. Chỉ khi preflight được chấp nhận, browser mới gửi method thực tế.

Không chỉ assert response của OPTIONS. Một server có thể trả preflight đúng nhưng response của POST lại thiếu Access-Control-Allow-Origin, khiến JavaScript vẫn không đọc được kết quả.

## 5. Kiểm thử Origin allowlist

Origin được browser gửi tự động và chứa scheme, host, port. Nó không chứa path. Server cần so sánh origin với allowlist có cấu trúc, không dùng substring hoặc regex quá rộng.

### 5.1. Các case phải có

| Origin gửi từ browser | Policy | Kết quả mong đợi |
|---|---|---|
| https://app.example.test | Được phép | JavaScript đọc được response nếu các điều kiện khác đúng |
| https://admin.example.test | Không được phép | Browser chặn JavaScript đọc response |
| http://app.example.test | Chỉ HTTPS được phép | Bị từ chối |
| https://app.example.test:8443 | Port không nằm trong allowlist | Bị từ chối |
| https://evil-app.example.test | Host gần giống nhưng không khớp | Bị từ chối |
| null | Không có policy riêng | Bị từ chối |

### 5.2. Không phản chiếu Origin tùy ý

Một cấu hình nguy hiểm là nhận mọi Origin rồi trả lại đúng giá trị đó trong Access-Control-Allow-Origin. Nếu kết hợp với credentials, một trang độc hại có thể đọc dữ liệu người dùng đang đăng nhập.

Nếu cần dynamic allowlist:

1. Parse Origin.
2. So sánh scheme, host và port với allowlist.
3. Chỉ phản hồi origin đã khớp.
4. Thêm Vary: Origin khi response phụ thuộc Origin.
5. Không chấp nhận giá trị null trừ khi có use case và threat model cụ thể.
6. Không dùng suffix check thiếu domain boundary.

### 5.3. Không trả nhiều Access-Control-Allow-Origin

Response không được ghép nhiều origin thành một giá trị comma-separated để browser chọn. Access-Control-Allow-Origin cần chứa một origin cụ thể hoặc wildcard trong trường hợp phù hợp. Nếu server hoặc proxy tạo duplicate header, browser có thể từ chối response.

Test phải kiểm tra cả header raw/response đã nhận và kết quả fetch trong browser.

## 6. Kiểm thử credentials và cookie

Credentials làm thay đổi yêu cầu CORS. Với Fetch API, credentials có các mode omit, same-origin và include. Mặc định là same-origin; muốn gửi credential trong request cross-origin thường phải chọn include.

### 6.1. CORS headers cho credentialed request

Khi browser gửi request cross-origin có credentials:

- Access-Control-Allow-Origin phải là origin cụ thể, không được là *.
- Server phải trả Access-Control-Allow-Credentials: true.
- Origin phải nằm trong allowlist.
- Response thực tế phải có các CORS header cần thiết.
- Cookie vẫn phải thỏa chính sách cookie của browser.

Ví dụ:

```http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
```

Giá trị true của Access-Control-Allow-Credentials phân biệt chữ hoa/thường theo quy tắc CORS. Không trả True hoặc TRUE.

### 6.2. Test Fetch credentials

```javascript
const response = await fetch("https://api.other.test/v1/profile", {
  method: "GET",
  mode: "cors",
  credentials: "include"
});

const profile = await response.json();
```

Test cần xác nhận cả hai phía:

- Browser có thực sự gửi cookie/credential không?
- Server có nhận đúng session/user dự kiến không?
- Response có exact allowed origin và Access-Control-Allow-Credentials: true không?
- JavaScript có đọc được body không?

Không chỉ kiểm tra response.ok, vì một response có thể không được browser expose do CORS.

### 6.3. SameSite và Secure

Cookie cross-site cần đáp ứng cookie policy độc lập với CORS. Ví dụ, cookie muốn được gửi trong cross-site context thường cần SameSite=None; Secure. Cookie Secure chỉ được gửi qua secure transport theo quy tắc browser.

Nếu cookie không được gửi, có thể nguyên nhân là:

- SameSite=Lax hoặc Strict.
- Thiếu Secure khi dùng SameSite=None.
- Domain hoặc Path không khớp.
- Cookie hết hạn hoặc bị xóa.
- Browser chặn third-party cookie.
- Privacy setting hoặc tracking protection của browser.
- Cookie partitioning policy.

CORS không thể ép browser gửi cookie đã bị cookie policy chặn. Test phải kiểm tra cookie jar và request thực tế trong browser context.

### 6.4. Third-party cookie restrictions

Ngay cả khi CORS header chính xác, browser có thể hạn chế third-party cookie theo cấu hình privacy hoặc chính sách trình duyệt. Do đó, test cross-site credential cần chạy trong browser version và privacy mode mà sản phẩm hỗ trợ.

Không tắt toàn bộ privacy protection trong CI rồi kết luận production cookie flow hoạt động. Nếu ứng dụng cần cookie cross-site, đánh giá thêm kiến trúc đăng nhập, top-level navigation, partitioned cookie và chính sách browser mục tiêu.

### 6.5. Không dùng wildcard với credentials

Cặp cấu hình sau không hợp lệ cho credentialed CORS:

```http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
```

Browser không cho JavaScript đọc response theo cấu hình này. Test cần xác nhận wildcard vẫn có thể hoạt động cho request không credential trong use case công khai, nhưng phải thất bại khi request dùng credentials.

## 7. Kiểm thử request header và method

Một API có thể cho phép origin nhưng chỉ cho một số method và header.

Test cần bao phủ:

- GET, HEAD, POST, PUT, PATCH, DELETE.
- Authorization.
- Content-Type: application/json.
- X-Request-ID, Idempotency-Key hoặc header ứng dụng.
- Header không được phép.
- Header có tên viết hoa/thường khác nhau.
- Nhiều header được yêu cầu trong cùng preflight.
- Method không được phép.

### 7.1. Access-Control-Allow-Methods

Header này cho browser biết các method được phép trong CORS. Nó không cấp quyền nghiệp vụ cho user và không thay thế method authorization.

Nếu preflight yêu cầu DELETE nhưng server chỉ cho phép GET, POST, browser không gửi actual DELETE. Nếu browser gửi một request đơn giản không cần preflight, server vẫn phải tự kiểm tra method và quyền.

### 7.2. Access-Control-Allow-Headers

Server cần cho phép các request header mà client cần dùng. Authorization nên được liệt kê rõ ràng khi API yêu cầu bearer token. Không giả định wildcard header sẽ bao phủ mọi header trong mọi trường hợp, đặc biệt khi request có credentials.

Test cần kiểm tra một header được phép và một header không được phép. Browser phải từ chối trước actual request khi preflight không cho phép header cần thiết.

### 7.3. Header không phải safelisted

Ví dụ:

```javascript
await fetch("https://api.other.test/v1/orders", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer test-token",
    "X-Request-ID": "test-123"
  },
  body: JSON.stringify({ itemId: "item-1" })
});
```

Request này cần preflight. Test nên xác nhận server trả allow headers tương ứng và actual POST chỉ xuất hiện khi preflight được chấp nhận.

## 8. Kiểm thử response headers được expose

Browser chỉ cho JavaScript đọc một tập response header safelisted theo mặc định. Header khác cần được liệt kê trong Access-Control-Expose-Headers.

Ví dụ server muốn client đọc X-Request-ID và Content-Disposition:

```http
Access-Control-Expose-Headers: X-Request-ID, Content-Disposition
```

Trong browser:

```javascript
const response = await fetch("https://api.other.test/v1/export");
const requestId = response.headers.get("X-Request-ID");
const disposition = response.headers.get("Content-Disposition");
```

Test nên xác nhận:

- Header safelisted đọc được theo mặc định.
- Header custom không đọc được khi chưa expose.
- Header custom đọc được khi đã expose.
- Set-Cookie không được expose cho JavaScript.
- Header có trong DevTools không đồng nghĩa JavaScript được phép đọc.

Không đưa token hoặc secret vào response header chỉ vì muốn client JavaScript đọc. Cookie HttpOnly được browser quản lý và không nên truy cập bằng JavaScript.

## 9. Kiểm thử lỗi và response không thành công

CORS phải được xử lý nhất quán trên response thành công và lỗi. Nếu chỉ response 200 có CORS header, frontend có thể nhận TypeError chung khi API trả 401 hoặc 500, khiến ứng dụng khó xử lý và khó debug.

Cần kiểm tra:

| HTTP response | Điều cần xác minh |
|---|---|
| 200 | Browser đọc được status, body và header được expose |
| 201 | Response tạo resource có CORS header |
| 204 | Không có body nhưng response vẫn được expose |
| 400 | Frontend đọc được error contract |
| 401 | CORS header có mặt; authentication error được phân biệt |
| 403 | Authorization error được expose đúng |
| 404 | Error behavior đúng theo contract |
| 413 | Payload limit error đọc được |
| 429 | Rate limit response và Retry-After được expose nếu cần |
| 500 | Không lộ stack trace nhưng frontend đọc được error code an toàn |

Nếu response bị browser chặn vì thiếu CORS header, JavaScript thường chỉ nhận một network-style error và không đọc được status/body. Điều này khác với response.status === 401 hoặc 403 mà browser đã cho phép expose.

## 10. Kiểm thử Fetch API

Fetch API là cách phổ biến để frontend gọi REST API. Cần test các mode và option ảnh hưởng tới CORS.

### 10.1. mode=cors

mode: cors cho phép request cross-origin theo CORS protocol. Browser có thể gửi preflight và chỉ expose response khi CORS check thành công.

Test:

- Origin được phép.
- Origin không được phép.
- Request cần preflight.
- Request không cần preflight.
- Credential omit, same-origin, include.
- Response header exposure.
- Redirect và error response.

### 10.2. mode=no-cors

mode: no-cors không phải cách bỏ qua CORS để đọc response. Response thường là opaque: JavaScript không đọc được status, headers hoặc body. Request cũng bị giới hạn method/header theo chế độ này.

Test cần xác nhận opaque response không thể dùng làm workaround cho API cần JSON. Không khuyến nghị chuyển sang no-cors chỉ để loại bỏ CORS error.

### 10.3. Abort và timeout

Fetch hỗ trợ AbortController; test có thể abort request để xác minh UI cleanup và behavior khi request bị hủy. Abort không phải CORS failure. Phân biệt:

- Browser chặn do CORS.
- Request bị abort từ application.
- DNS/TLS/network failure.
- Server trả HTTP error.
- Request timeout ở proxy hoặc backend.

### 10.4. Fetch và redirect mode

Fetch có redirect mode như follow, error và manual. Cần test redirect từ API đến:

- Cùng origin.
- Origin khác được phép.
- Origin khác không được phép.
- HTTPS sang HTTP.
- Endpoint trả redirect sau preflight.

Redirect trong CORS có các quy tắc và khác biệt tương thích theo browser/version. Với API cần behavior ổn định, tránh redirect không cần thiết và kiểm thử toàn bộ redirect chain bằng browser mục tiêu.

## 11. Kiểm thử XMLHttpRequest

Một số ứng dụng cũ hoặc thư viện vẫn dùng XMLHttpRequest (XHR). CORS credential behavior của XHR dùng withCredentials.

Ví dụ:

```javascript
const xhr = new XMLHttpRequest();
xhr.open("GET", "https://api.other.test/v1/profile");
xhr.withCredentials = true;

xhr.onload = () => {
  console.log(xhr.status);
  console.log(xhr.responseText);
};

xhr.onerror = () => {
  console.error("Network or CORS failure");
};

xhr.send();
```

Test cần xác nhận:

- withCredentials = true có gửi credential khi cookie policy cho phép.
- Response có Access-Control-Allow-Credentials: true.
- Origin response là origin cụ thể, không phải wildcard.
- withCredentials = false có behavior phù hợp.
- onerror không bị nhầm với HTTP 401 hoặc 403.
- Custom request header kích hoạt preflight như dự kiến.

Không giả định Fetch và XHR có cùng API surface hoặc cùng cách báo lỗi. Test các client API mà sản phẩm thực sự dùng.

## 12. EventSource, WebSocket và các browser API khác

Không phải mọi browser API đều sử dụng CORS giống Fetch.

### 12.1. EventSource

EventSource dùng để nhận server-sent events. Khi mở cross-origin stream, browser áp dụng CORS; API có tùy chọn withCredentials cho credential mode.

Test cần xác minh:

- Origin được phép/không được phép.
- Response có đúng media type text/event-stream.
- Credential mode và cookie policy.
- Stream giữ kết nối lâu nhưng vẫn có CORS header hợp lệ.
- Reconnect sau khi mất kết nối.
- Response lỗi khi stream bắt đầu hoặc khi reconnect.
- Cache/proxy không buffer hoặc làm sai stream theo cấu hình.

### 12.2. WebSocket không dùng CORS handshake như Fetch

WebSocket handshake không được bảo vệ bởi CORS response-header check theo cách Fetch/XHR dùng. Browser gửi Origin trong handshake; server cần tự kiểm tra Origin theo allowlist, xác thực session/token và authorization cho channel/subscription.

Đặc biệt với cookie authentication, kiểm tra Origin giúp giảm Cross-Site WebSocket Hijacking (CSWSH). Không dựa vào Access-Control-Allow-Origin để bảo vệ WebSocket.

Test WebSocket cần bao gồm:

- Origin hợp lệ.
- Origin không được phép.
- Origin null nếu có thể phát sinh trong môi trường hỗ trợ.
- Không có credential.
- Session hết hạn.
- User không có quyền subscribe channel.
- Origin hợp lệ nhưng user không có quyền trên resource.
- Reconnect và session revocation.

### 12.3. Image, canvas và font

Một ảnh cross-origin có thể hiển thị trong trang nhưng việc đọc pixel qua canvas bị hạn chế nếu resource không được tải với CORS mode phù hợp. Khi canvas bị taint, thao tác đọc pixel như getImageData hoặc export có thể bị chặn.

Font, module script và một số resource type có quy tắc cross-origin riêng. Test resource API cần kiểm tra hành vi browser thực tế thay vì áp một kết luận từ Fetch cho mọi loại resource.

### 12.4. Service worker

Service worker có thể thực hiện fetch thay mặt trang và can thiệp request/response trong phạm vi origin của nó. Test cần xác minh:

- Service worker có đang cache response cũ không.
- CORS failure được xử lý như thế nào.
- Cache Storage có giữ response không còn hợp lệ không.
- Update service worker có thay đổi request mode hoặc credential behavior không.
- Test context mới có cài service worker cũ hay không.

Khi kiểm thử, quyết định rõ có bật service worker thật hay dùng context sạch để cô lập CORS behavior.

## 13. Redirect và CORS behavior

Redirect là một nguồn lỗi khó chẩn đoán vì request có thể đi qua nhiều origin. Một API gateway có thể redirect HTTP sang HTTPS, route version cũ sang version mới hoặc chuyển tới CDN.

Cần test:

1. Request ban đầu có cần preflight không?
2. Browser có chấp nhận preflight response không?
3. Redirect response có CORS header cần thiết theo flow không?
4. Origin cuối cùng có được phép không?
5. Method và body có được giữ hay thay đổi theo status redirect?
6. Credential có bị gửi sang origin khác không?
7. Response cuối có CORS header phù hợp không?

Không chuyển tiếp bearer token hoặc cookie sang origin không được tin cậy. Redirect 301, 302, 303, 307, 308 có semantics khác nhau về method/body; test phải dùng đúng status mà API thực tế trả.

Nếu có thể, trả response trực tiếp từ canonical API origin và tránh redirect trong luồng XHR/Fetch cross-origin.

## 14. Preflight cache và HTTP cache

Browser có thể cache kết quả preflight theo Access-Control-Max-Age, trong giới hạn do browser áp dụng. Điều này khiến test liên tiếp có thể không gửi lại OPTIONS.

### 14.1. Test cold và warm preflight

- Context mới: xác minh browser gửi OPTIONS.
- Gọi lần thứ hai với cùng origin/method/header: kiểm tra preflight cache.
- Thay method: kiểm tra cache key/decision mới.
- Thay request header: kiểm tra preflight lại khi cần.
- Thay origin: xác minh origin policy được đánh giá đúng.
- Thay browser context: xác minh cache không bị chia sẻ ngoài dự kiến.

Không phụ thuộc một con số Access-Control-Max-Age cố định vì browser có thể áp trần riêng.

### 14.2. Vary: Origin

Nếu server phản hồi Access-Control-Allow-Origin theo Origin request, response cache cần phân biệt các Origin. Vary: Origin giúp cache HTTP biết response phụ thuộc header này.

Thiếu Vary: Origin có thể khiến response đã được cache cho origin A được phục vụ cho origin B với CORS header không phù hợp. Test cần đi qua cache/CDN thật hoặc test proxy tương đương, không chỉ gọi application trực tiếp.

### 14.3. Cache không được làm rò dữ liệu tenant

Nếu response phụ thuộc user, tenant hoặc cookie, CORS không bảo đảm cache isolation. Kiểm tra Cache-Control, cache key và Vary theo đúng auth/data semantics. Không cache response nhạy cảm một cách công khai chỉ vì CORS allow một origin.

## 15. Test origin null và sandboxed document

Một số context có thể tạo opaque origin được serialize thành null, ví dụ sandboxed iframe không có allow-same-origin, một số data URL hoặc file context.

Không nên allow null chung chung. Nhiều document khác nhau có thể cùng gửi Origin null, nên giá trị này không xác định một site tin cậy cụ thể.

Nếu có use case cần sandboxed document:

- Tạo test fixture đúng sandbox attributes.
- Xác minh origin được browser gửi.
- Không dùng null như danh tính tenant hoặc user.
- Dùng token capability riêng có scope và thời hạn nếu cần truy cập.
- Kiểm tra không thể đọc dữ liệu của session người dùng khác.
- Đánh giá lại threat model trước khi cho phép.

## 16. CORS và CSRF: kiểm thử hai cơ chế riêng

CORS và CSRF có quan hệ nhưng không thay thế nhau.

Một request form đơn giản có thể được browser gửi cross-site bằng cookie, dù JavaScript ở site nguồn không đọc được response. Nếu endpoint thay đổi trạng thái và dựa vào cookie session, cần CSRF defense phù hợp.

Các kiểm thử nên có:

- Request cross-site đơn giản với cookie session.
- Request có CSRF token hợp lệ.
- Request thiếu hoặc sai CSRF token.
- SameSite cookie behavior.
- Origin/Referer validation nếu hệ thống dùng.
- CORS response allow/deny.
- Authorization và business permission.

Một test CORS thành công không chứng minh endpoint chống CSRF. Một test CSRF token thất bại cũng không chứng minh CORS được cấu hình đúng.

## 17. Kiểm thử browser thật bằng Playwright

Playwright có thể chạy Chromium, Firefox và WebKit. Dùng page thật để browser tự tạo Origin, preflight và enforce CORS.

Ví dụ dưới đây giả định hai test server đang chạy ở hai origin khác nhau và API fixture có endpoint /cors/allow:

```typescript
import { test, expect } from "@playwright/test";

test("browser can read an allowed cross-origin response", async ({ page }) => {
  await page.goto("https://app.example.test");

  const result = await page.evaluate(async () => {
    const response = await fetch(
      "https://api.other.test/cors/allow",
      { mode: "cors" }
    );

    return {
      status: response.status,
      body: await response.json()
    };
  });

  expect(result.status).toBe(200);
  expect(result.body.message).toBe("allowed");
});
```

Test này chứng minh browser có thể đọc response từ origin được cho phép. Nó không thay thế test preflight, credentials hoặc negative cases.

### 17.1. Test CORS deny

```typescript
test("browser rejects an origin outside the allowlist", async ({ page }) => {
  await page.goto("https://attacker.other.test");

  const result = await page.evaluate(async () => {
    try {
      await fetch("https://api.other.test/cors/private");
      return "readable";
    } catch {
      return "blocked";
    }
  });

  expect(result).toBe("blocked");
});
```

Test này chỉ xác nhận JavaScript không đọc được response. Với request đơn giản, server vẫn có thể đã nhận request. Hãy kiểm tra fixture server log/counter để biết request có tới hay không.

### 17.2. Test preflight bằng custom header

```typescript
test("browser preflights a request with Authorization", async ({ page }) => {
  const methods: string[] = [];

  page.on("request", request => {
    if (request.url().includes("/cors/preflight")) {
      methods.push(request.method());
    }
  });

  await page.goto("https://app.example.test");

  await page.evaluate(async () => {
    const response = await fetch(
      "https://api.other.test/cors/preflight",
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": "Bearer test-token"
        },
        body: JSON.stringify({ value: 1 })
      }
    );

    return response.status;
  });

  expect(methods).toContain("OPTIONS");
  expect(methods).toContain("POST");
  expect(methods.indexOf("OPTIONS")).toBeLessThan(methods.indexOf("POST"));
});
```

Trong test thực tế, cần assert response và server-side request log nữa. Nếu preflight bị từ chối, POST không được gửi. Dùng test token giả, không đặt secret thật trong source hoặc trace.

### 17.3. Test preflight bị từ chối

```typescript
test("failed preflight prevents the actual method", async ({ page }) => {
  const methods: string[] = [];

  page.on("request", request => {
    if (request.url().includes("/cors/deny-preflight")) {
      methods.push(request.method());
    }
  });

  await page.goto("https://app.example.test");

  const result = await page.evaluate(async () => {
    try {
      await fetch("https://api.other.test/cors/deny-preflight", {
        method: "DELETE",
        headers: { "X-Admin-Action": "true" }
      });
      return "readable";
    } catch {
      return "blocked";
    }
  });

  expect(result).toBe("blocked");
  expect(methods).toContain("OPTIONS");
  expect(methods).not.toContain("DELETE");
});
```

Test này kiểm tra khác biệt quan trọng giữa preflight failure và simple request bị chặn ở response. Với preflight failure, browser không gửi actual DELETE.

### 17.4. Test credentials

```typescript
test("credentialed CORS response is readable with exact origin", async ({ page }) => {
  await page.goto("https://app.example.test");

  const result = await page.evaluate(async () => {
    const response = await fetch(
      "https://api.other.test/cors/session",
      {
        mode: "cors",
        credentials: "include"
      }
    );

    return {
      status: response.status,
      body: await response.json()
    };
  });

  expect(result.status).toBe(200);
  expect(result.body.authenticated).toBe(true);
});
```

Test này chỉ pass nếu cookie đã được thiết lập hợp lệ trong browser context, cookie policy cho phép gửi và server trả đúng CORS headers. Nên có test riêng xác minh request thực tế có cookie và test negative với origin không được phép.

### 17.5. Không dùng APIRequestContext để kết luận CORS

Playwright APIRequestContext là HTTP client phục vụ API testing, không phải page JavaScript chịu same-origin policy. Test qua APIRequestContext có thể xác minh status/header ở tầng HTTP nhưng không chứng minh browser CORS behavior.

Dùng page.goto để tạo document origin rồi gọi fetch trong page.evaluate hoặc thao tác qua UI.

## 18. Chạy test trên nhiều browser engine

Browser có thể khác nhau về preflight cache, redirect behavior, cookie privacy, error message và tính năng mới. Nên chạy test trên các engine mà sản phẩm hỗ trợ.

| Engine | Bộ kiểm thử |
|---|---|
| Chromium | CORS, credentials, cookie, preflight, redirect, cache |
| Firefox | CORS, credentials, cookie, preflight, redirect, cache |
| WebKit | CORS, credentials, cookie, preflight, redirect, cache |

Ví dụ cấu hình Playwright:

```typescript
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] }
    },
    {
      name: "firefox",
      use: { ...devices["Desktop Firefox"] }
    },
    {
      name: "webkit",
      use: { ...devices["Desktop Safari"] }
    }
  ]
});
```

Cấu hình này chỉ định project browser; cần cài browser binaries tương ứng trong CI. Ghi lại browser version để có thể giải thích thay đổi behavior sau khi nâng cấp.

### 18.1. Test browser context sạch

Mỗi test độc lập nên dùng context mới hoặc chủ động xóa cookie/cache/service worker. Nếu dùng lại context, preflight cache và cookie từ test trước có thể làm kết quả không ổn định.

Với test preflight cache, tạo hai lượt có chủ đích trong cùng context; với test cold preflight, dùng context mới. Không xóa cache giữa hai lượt nếu đang muốn xác minh cache behavior.

### 18.2. Test desktop và mobile browser

Nếu sản phẩm hỗ trợ browser mobile, cần test ít nhất các browser/version mục tiêu trên thiết bị hoặc emulator phù hợp. Cookie policy, WebView và embedded browser có thể khác desktop browser.

Không suy ra behavior của iOS WebView hoặc Android WebView chỉ từ Safari/Chrome desktop. Ghi rõ browser engine, OS và version trong kết quả.

## 19. Ma trận kiểm thử CORS toàn diện

Một test suite nên có các nhóm sau:

| Nhóm | Case dương | Case âm |
|---|---|---|
| Origin | Origin nằm trong allowlist | Origin lạ, scheme/port khác, null |
| Method | Method được cho phép | Method không được cho phép |
| Header | Header được cho phép | Custom header không được cho phép |
| Preflight | OPTIONS hợp lệ rồi actual request | OPTIONS deny, actual request không được gửi |
| Credentials | Exact origin + ACAC + cookie hợp lệ | Wildcard + credentials, thiếu ACAC |
| Cookie | SameSite/Secure đúng | Cookie bị chặn hoặc domain/path sai |
| Response headers | Exposed header đọc được | Header không expose không đọc được |
| Error | 401/403/429/500 có CORS header | Error response thiếu CORS header |
| Cache | Vary Origin đúng | Cache response của origin A phục vụ origin B |
| Redirect | Redirect chain được phép | Redirect sang origin không được phép |
| Fetch mode | CORS response đọc được | no-cors trả opaque response |
| XHR | withCredentials đúng | CORS error và HTTP error được phân biệt |
| EventSource | Stream được phép | Origin hoặc credential không hợp lệ |
| WebSocket | Origin và user hợp lệ | Origin lạ, user thiếu quyền |
| Resource API | Canvas đọc được khi CORS đúng | Canvas bị taint khi thiếu CORS |
| Browser engine | Behavior đúng trên engine hỗ trợ | Sai khác engine/version được phát hiện |

### 19.1. Ghi nhận cả browser và server

Mỗi case nên thu thập:

- Browser engine và version.
- Document origin.
- API origin.
- Request mode và credentials mode.
- Request method và request headers.
- Có preflight hay không.
- Response status và CORS headers.
- JavaScript result/error.
- Server-side request log.
- Cookie được gửi hay không.
- Redirect chain và cache behavior.

Không dùng mỗi screenshot console làm bằng chứng duy nhất. Kết hợp browser automation assertion, network event và server-side log.

## 20. Chẩn đoán CORS failure trong DevTools

Khi browser chặn response, JavaScript thường chỉ thấy một thông báo tổng quát. DevTools giúp phân biệt lỗi preflight, response header, network và cookie.

### 20.1. Kiểm tra Network panel

- Tìm request OPTIONS nếu request cần preflight.
- Kiểm tra Origin.
- Kiểm tra Access-Control-Request-Method.
- Kiểm tra Access-Control-Request-Headers.
- Xem status và response headers của preflight.
- Xác nhận actual request có được gửi không.
- Kiểm tra response headers của actual request.
- Xem redirect chain.
- Xem cookie request/blocked reason nếu DevTools hỗ trợ.

### 20.2. Các dấu hiệu thường gặp

| Dấu hiệu | Nguyên nhân có thể |
|---|---|
| OPTIONS trả 401/403 | Authentication middleware chặn preflight |
| OPTIONS thành công nhưng POST không gửi | Allow method/header không khớp |
| POST đã tới server nhưng JS báo CORS | Actual response thiếu hoặc sai CORS header |
| 200 trong Network nhưng fetch reject | Browser không cho expose response |
| Cookie không có trong request | SameSite, Secure, domain/path hoặc third-party cookie policy |
| response.headers.get() trả null | Header chưa được expose hoặc không có |
| Chỉ lỗi sau deploy/CDN | Cache thiếu Vary: Origin hoặc edge config khác |
| Chỉ lỗi khi redirect | Origin cuối hoặc preflight/redirect behavior không tương thích |
| Chỉ lỗi ở một browser | Khác biệt engine, privacy policy hoặc version |

### 20.3. Console không phải toàn bộ câu trả lời

CORS error message có thể khác nhau theo browser. Test automation nên assert behavior observable như fetch resolve/reject, status/body và server log; tránh assert nguyên văn console message vì nội dung không ổn định giữa phiên bản.

## 21. Private Network Access và browser policy thay đổi

Một số browser triển khai hoặc thử nghiệm các cơ chế bổ sung khi một trang public truy cập tài nguyên ở mạng private. Các thay đổi này có thể bổ sung preflight hoặc yêu cầu response header riêng tùy browser/version và cấu hình.

Nếu ứng dụng truy cập API trong mạng nội bộ từ một public origin:

- Kiểm tra browser/version thực tế được hỗ trợ.
- Test preflight liên quan đến private network nếu browser mục tiêu sử dụng.
- Cấu hình server theo tài liệu của browser và môi trường triển khai.
- Không xem browser permission là thay thế network segmentation hoặc authentication.
- Không dựa vào một browser feature đang thay đổi để làm ranh giới bảo mật duy nhất.

Ghi rõ version và flag trong CI khi test tính năng này. Tránh bật flag đặc biệt chỉ để test pass nếu production browser không có cùng cấu hình.

## 22. Tích hợp browser tests vào CI/CD

Browser CORS tests cần chạy như một phần của security regression suite.

Một pipeline tham khảo:

1. Khởi chạy frontend test origin và API fixture origin.
2. Cấu hình DNS/hosts và HTTPS certificate cho test domains.
3. Khởi chạy gateway/reverse proxy nếu production có sử dụng.
4. Seed dữ liệu test và credential giả.
5. Chạy unit/integration test cho policy và middleware.
6. Chạy Playwright trên Chromium, Firefox và WebKit.
7. Thu thập browser trace, screenshot và server request log khi fail.
8. Dọn context, cookie, storage và test data.
9. Chặn release nếu origin lạ đọc được dữ liệu hoặc preflight policy sai.

### 22.1. Giữ test deterministic

- Dùng fixture server có response cố định.
- Không phụ thuộc API Internet bên thứ ba.
- Đồng bộ clock khi test expiry.
- Tạo context mới cho test độc lập.
- Đợi server log bằng correlation ID thay vì sleep cố định.
- Không dùng browser cache chung giữa test nếu không kiểm soát.
- Ghi browser version và test environment.
- Retry test chỉ để điều tra flakiness, không che lỗi security.

### 22.2. Test qua gateway thật hoặc cấu hình tương đương

Nếu production CORS header được thêm ở CDN/API gateway, test chỉ gọi application port có thể bỏ sót cấu hình thực tế. Nên có ít nhất một suite qua cùng gateway configuration hoặc một deployment test tương đương.

Đảm bảo gateway và application không cùng thêm duplicate Access-Control-Allow-Origin, không ghi đè Vary và không bỏ CORS header trên error response.

## 23. Những lỗi thiết kế thường gặp

1. **Dùng curl để chứng minh CORS hoạt động.** curl không thực thi same-origin policy.
2. **Dùng Playwright APIRequestContext để test browser CORS.** Đây là HTTP client, không phải page context.
3. **Chỉ kiểm tra OPTIONS.** Actual response vẫn có thể thiếu CORS header.
4. **Chỉ kiểm tra fetch reject.** Không biết simple request đã tới server hay chưa.
5. **Cho phép mọi Origin bằng reflection.** Có thể cho website độc hại đọc dữ liệu.
6. **Dùng wildcard với credentials.** Browser từ chối expose response.
7. **Quên Vary: Origin.** Cache có thể phục vụ response với CORS header sai.
8. **Bắt authentication trên preflight.** OPTIONS bị 401/403 trước khi CORS middleware xử lý.
9. **Cho rằng CORS ngăn CSRF.** Simple request vẫn có thể tới server.
10. **Cho rằng CORS áp dụng cho WebSocket giống Fetch.** WebSocket cần kiểm tra Origin và authorization ở handshake/server.
11. **Nhầm origin với site.** Test subdomain không bao phủ cookie cross-site.
12. **Bỏ qua third-party cookie policy.** CORS đúng nhưng cookie vẫn không được gửi.
13. **Chỉ test response 200.** Error response thiếu CORS header làm frontend không đọc được lỗi.
14. **Không test preflight cache.** Test có thể pass do cache cũ.
15. **Dùng Origin null như trusted origin.** Opaque origin không xác định site tin cậy.
16. **Không test redirect.** Request có thể kết thúc ở origin khác.
17. **Chỉ chạy Chromium.** Khác biệt Firefox/WebKit không được phát hiện.
18. **Test qua controller mà bỏ gateway.** Header có thể bị thêm, xóa hoặc duplicate ở edge.
19. **Assert nguyên văn browser console message.** Test dễ vỡ khi browser đổi cách diễn đạt.
20. **Đưa credential production vào test.** Trace hoặc report có thể làm lộ secret.

## 24. Checklist kiểm thử browser CORS

Trước khi phát hành thay đổi CORS, hãy xác nhận:

- [ ] Test chạy từ một document origin thật và gọi một API origin khác.
- [ ] Có test same-origin, cross-origin same-site và cross-site.
- [ ] Test dùng browser page context, không chỉ curl hoặc APIRequestContext.
- [ ] Origin được browser tạo tự động; test không giả lập bằng header tự đặt.
- [ ] Có case origin allow, deny, scheme/port khác và null.
- [ ] Có case request safelisted không preflight.
- [ ] Có case request cần preflight do method/header/content type.
- [ ] Preflight được xử lý trước authentication middleware phù hợp.
- [ ] Test xác nhận actual request không gửi khi preflight thất bại.
- [ ] Test xác nhận simple request có thể tới server dù JS không đọc được response.
- [ ] Credentials test dùng exact allowed origin và ACAC true.
- [ ] Wildcard origin với credentials bị từ chối.
- [ ] Cookie test kiểm tra SameSite, Secure, domain, path và third-party policy.
- [ ] Custom response header chỉ đọc được khi được expose.
- [ ] Error response 4xx/5xx có CORS behavior đúng.
- [ ] Cache test kiểm tra Vary: Origin và cold/warm preflight.
- [ ] Redirect chain được kiểm tra qua browser thật.
- [ ] Fetch, XHR và EventSource được test nếu ứng dụng sử dụng.
- [ ] WebSocket có Origin validation và authorization riêng.
- [ ] Resource APIs như image/canvas được test nếu ứng dụng cần đọc dữ liệu cross-origin.
- [ ] Chạy trên browser engine/version mà sản phẩm hỗ trợ.
- [ ] Có server-side log để đối chiếu request thực tế.
- [ ] CI giữ trace/screenshot khi fail nhưng không ghi credential thật.
- [ ] Test qua gateway hoặc deployment tương đương production.
- [ ] CORS được xem là response-sharing policy, không thay authorization hoặc CSRF protection.

## 25. Kết luận

CORS là cơ chế browser thực thi, vì vậy một cấu hình chỉ được xem là đã kiểm chứng khi được thử từ một document origin thật trong browser. Test phải phân biệt request có preflight và không có preflight, xác nhận cả OPTIONS lẫn actual response, và đối chiếu kết quả JavaScript với request mà server thực sự nhận.

Credentials và cookie cần được kiểm tra cùng Access-Control-Allow-Origin, Access-Control-Allow-Credentials, SameSite, Secure và third-party cookie policy. Response header cần được expose đúng; cache phải phân biệt Origin; redirect, error response và browser API khác cũng cần test theo behavior thực tế.

Một suite tốt chạy trên các browser engine mục tiêu, dùng context sạch và fixture hai origin, lưu server-side evidence và kiểm thử qua gateway gần production. CORS không thay authorization hay CSRF defense. Khi kiểm thử đúng nơi browser thực thi policy, nhóm phát triển có thể phát hiện lỗi mà unit test hoặc HTTP client thông thường không nhìn thấy.

