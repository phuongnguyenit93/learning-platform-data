# Header do trình duyệt quản lý và dữ liệu client có thể cung cấp

## Mục tiêu bài học

Trong một request HTTP, có những header do **trình duyệt tự xây dựng và kiểm soát**, những header mã JavaScript **có thể chủ động đặt**, và những header do **proxy hoặc server trung gian** thêm vào. Sự khác biệt này quan trọng khi thiết kế phòng vệ **CORS**, **CSRF**, bảo vệ cookie/session, xử lý HTTPS và quyết định tin cậy thông tin nguồn request.

Bài thuộc chương **Nền tảng trình duyệt** của module **SPRING_SECURITY_HTTP_PROTECTION**. Phạm vi ứng dụng là Spring Security với các lớp bảo vệ HTTP và trình duyệt — từ CSRF, CORS, security headers, CSP, HSTS tới HTTP firewall và bảo vệ session — trên cả **Servlet** và **Reactive (WebFlux)**.

Sau bài học, bạn có thể:

1. Phân biệt request header browser quản lý, request header JavaScript có thể cung cấp, và response header server kiểm soát.
2. Giải thích vì sao JavaScript thông thường không thể tự đặt **Cookie**, **Host**, **Origin**, **Content-Length**, **Sec-Fetch-*** bằng Fetch API, nhưng có thể đặt **Authorization**, **Content-Type** và custom headers theo điều kiện.
3. Đọc đúng vai trò của **Referer**, **Origin**, **Sec-Fetch-Site/Mode/Dest/User**, **Access-Control-Request-*** và các header CORS ở response.
4. Hiểu ranh giới tin cậy: **header browser quản lý không phải bằng chứng xác thực**, vì client ngoài trình duyệt hoặc proxy không đáng tin vẫn có thể tạo các header tương tự.
5. Thiết kế phòng vệ CSRF/CORS, session, HTTPS và xử lý reverse proxy hợp lý trong Spring Security Servlet/WebFlux.
6. Dùng DevTools, Fetch API và curl để xác minh request thực, preflight, cookie và header bị bỏ qua.

## 1. Header xuất hiện trong request bằng cách nào?

Khi một trang ở **https://app.example.com** thực hiện:

~~~javascript
const response = await fetch("https://api.example.com/api/me", {
  credentials: "include",
  headers: {
    "Accept": "application/json",
    "X-Client-Request-Id": "req-demo-42"
  }
});
~~~

Trình duyệt có thể xây dựng request HTTP tương tự:

~~~http
GET /api/me HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Accept: application/json
X-Client-Request-Id: req-demo-42
Cookie: __Host-session=opaque-value
Sec-Fetch-Site: same-site
Sec-Fetch-Mode: cors
Sec-Fetch-Dest: empty
~~~

Đây là **ví dụ minh họa**, không phải cam kết rằng mọi browser, mọi phiên bản HTTP và mọi request đều có chính xác những header đó. Cookie chỉ xuất hiện khi nó đã tồn tại và đủ điều kiện gửi; request với custom header có thể còn **OPTIONS preflight** trước GET thực.

Trong ví dụ:

- **Accept** và **X-Client-Request-Id** do mã ứng dụng khai báo trong đối tượng headers.
- **Host** (hoặc **:authority** trong HTTP/2/HTTP/3), **Origin** và **Sec-Fetch-*** do browser hoặc tầng mạng xây dựng theo ngữ cảnh.
- **Cookie** do cơ chế cookie của browser quản lý theo URL, chính sách cookie và credentials mode.
- Server nhận kết quả request nhưng không nên tự suy ra rằng tất cả các header đều được sinh ra từ một browser trung thực.

### 1.1. Ba nhóm dữ liệu cần tách biệt

| Nhóm | Ví dụ | Ai thường quyết định? | Điểm an toàn cần nhớ |
| --- | --- | --- | --- |
| **Browser / giao thức quản lý** | Host, Cookie, Origin, Sec-Fetch-Site, Content-Length, Connection | Browser và tầng giao thức khi dùng trang web thông thường | JavaScript không thể tùy ý gán chúng qua Fetch; server vẫn không được coi chúng là danh tính đã xác thực. |
| **JavaScript ứng dụng có thể cung cấp** | Accept, Content-Type, Authorization, X-CSRF-TOKEN, X-Client-Request-Id | Mã trang hoặc thư viện fetch/XHR, chịu các hạn chế API/CORS | Giá trị mang tính dữ liệu client, phải được kiểm tra đúng mục đích. |
| **Server / proxy bổ sung** | X-Forwarded-For, Forwarded, X-Forwarded-Proto; response CSP/HSTS/CORS | Proxy tin cậy hoặc server, nếu được cấu hình đúng | Chỉ tin header chuyển tiếp do proxy được tin cậy làm sạch và thiết lập; không tin mặc định chuỗi do client gửi. |

Tên header không chứng minh nguồn gốc. Ví dụ, một client dòng lệnh có thể tạo **Origin** hoặc **Sec-Fetch-Site** với giá trị do chính nó chọn. Đây là lý do server cần phân biệt **tín hiệu hỗ trợ bảo vệ trong mô hình trình duyệt** và **bằng chứng xác thực thực sự**.

### 1.2. Request header khác response header

- **Request header** đi từ client tới server, ví dụ **Cookie**, **Authorization**, **Content-Type**, **Origin**.
- **Response header** do server/proxy trả về, ví dụ **Set-Cookie**, **Access-Control-Allow-Origin**, **Content-Security-Policy**, **Strict-Transport-Security**.

Ví dụ:

~~~http
HTTP/1.1 200 OK
Set-Cookie: __Host-session=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Content-Security-Policy: default-src 'self'
Strict-Transport-Security: max-age=31536000
Vary: Origin
~~~

**Access-Control-Allow-Origin là response header**; JavaScript không thể tự cấp quyền CORS cho chính mình bằng cách thêm header đó vào request. Tương tự, **Set-Cookie** có ý nghĩa khi xuất hiện ở response hợp lệ; không phải một cách mã frontend tự đặt cookie thông qua request header.

## 2. Forbidden request headers: tên nào JavaScript không được đặt trực tiếp?

Trong Fetch API, trình duyệt hạn chế mã trang sửa một số request header vì chúng ảnh hưởng trực tiếp đến **kết nối, cookie, định tuyến hoặc ngữ cảnh bảo mật**. Chúng thường được gọi là **forbidden request-header names**.

Những ví dụ quan trọng:

| Header hoặc nhóm | Mã JavaScript trong trình duyệt đặt trực tiếp qua fetch/XHR? | Vì sao cần do browser quản lý? |
| --- | --- | --- |
| **Cookie** | Không | Browser chọn cookie theo domain/path, Secure, SameSite, thời hạn và credentials. |
| **Host** | Không | Host/authority phải phù hợp URL và giao thức kết nối. |
| **Origin** | Không | Browser tính origin nguồn theo ngữ cảnh request. |
| **Content-Length** | Không | Tầng HTTP tính kích thước/truyền body thích hợp. |
| **Accept-Encoding** | Không | Tầng mạng quyết định encoding có thể giải mã. |
| **Connection**, **Transfer-Encoding**, **Upgrade** | Không | Thuộc quản lý kết nối/giao thức; ý nghĩa còn phụ thuộc HTTP version. |
| **Access-Control-Request-Method / Headers** | Không | Browser tạo khi gửi CORS preflight. |
| **Referer** | Không được gán như request header tùy ý | Browser tính theo referrer policy; Fetch có các tùy chọn kiểm soát hạn chế. |
| **Sec-*** | Không | Tiền tố dành riêng cho header do nền tảng kiểm soát, ví dụ Sec-Fetch-*. |
| **Proxy-*** | Không | Tiền tố bị bảo vệ để tránh mã trang điều khiển các cơ chế proxy. |

Danh sách đầy đủ được định nghĩa bởi các quy tắc Fetch và có thể thay đổi theo tiêu chuẩn/triển khai. Đây là **những ví dụ nổi bật**, không phải bản sao đầy đủ của đặc tả.

Một số header có xử lý riêng giữa các trình duyệt, ví dụ **User-Agent**: thường do browser tạo nhưng không nên dựa vào khẳng định đơn giản rằng nó luôn bị cấm theo cùng một cách ở mọi phiên bản Fetch. Browser có thể bỏ qua giá trị được script gán; trong mọi trường hợp **User-Agent không phải bằng chứng người gọi đáng tin**.

### 2.1. Không thể tự gán Cookie header trong fetch

Ví dụ mã không nên sử dụng:

~~~javascript
await fetch("/api/me", {
  headers: {
    Cookie: "session=some-value"
  }
});
~~~

Browser có thể bỏ qua hoặc từ chối nỗ lực đặt forbidden header, tùy API và hoàn cảnh. Đừng kỳ vọng request trên sẽ mang cookie do JavaScript tự chọn.

Để request dùng cookie browser đã lưu, hãy dựa vào **credentials mode**:

~~~javascript
// Request cùng origin: credentials mặc định "same-origin".
await fetch("/api/me");

// API khác origin: cho phép browser cân nhắc credentials.
await fetch("https://api.example.com/api/me", {
  credentials: "include"
});
~~~

Việc dùng include **không ép browser gửi mọi cookie**. Cookie vẫn phải thỏa điều kiện Domain, Path, Secure, SameSite, thời hạn và chính sách cookie bên thứ ba.

### 2.2. Không thể tự khai báo Origin hoặc Sec-Fetch-Site

Ví dụ có ý định đánh lừa chính sách nguồn:

~~~javascript
await fetch("https://api.example.com/api/me", {
  headers: {
    Origin: "https://trusted.example.com",
    "Sec-Fetch-Site": "same-origin"
  }
});
~~~

Mã trang thông thường **không thể dùng những thuộc tính này để giả mạo ngữ cảnh origin**. Trình duyệt tự tính header thích hợp theo ngữ cảnh và có thể bỏ qua các giá trị giả lập trong headers.

Tuy nhiên, server nhận request trực tiếp từ curl, script backend hoặc một proxy không tin cậy **không có bảo đảm tương tự**. Nếu server chỉ kiểm tra Sec-Fetch-Site: same-origin để cho phép truy cập dữ liệu mật, một HTTP client tùy ý vẫn có thể gửi chuỗi đó. Header bảo vệ theo ngữ cảnh browser **không thay thế authentication**.

### 2.3. Content-Length, Host và giao thức

Browser kiểm soát việc biểu diễn request body và định tuyến tới URL:

~~~text
URL trong fetch:
  https://api.example.com/orders

HTTP/1.1:
  Host: api.example.com

HTTP/2 hoặc HTTP/3:
  :authority: api.example.com
~~~

Bên gửi không được tùy tiện sửa Host hoặc Content-Length từ script để làm request đi tới địa chỉ khác URL hoặc khiến browser gửi kích thước body sai.

**Không tin Host tuyệt đối ở server**: một HTTP client trực tiếp vẫn có thể tạo Host tùy ý. Cần cấu hình trusted hosts, proxy, redirect target và URL tuyệt đối đúng, nhất là với ứng dụng tạo liên kết email, callback hoặc URL bảo mật.

## 3. Header JavaScript được quyền thêm không có nghĩa server được tin

JavaScript có thể tạo nhiều header ứng dụng:

~~~javascript
const response = await fetch("https://api.example.com/api/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "Accept": "application/json",
    "X-Client-Request-Id": "req-42",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ productId: 42 })
});
~~~

Trong ví dụ này **csrfToken phải được ứng dụng cấp hợp lệ**; nó không phải biến browser tự sinh. Tất cả các giá trị request header do mã client cung cấp đều cần được server xử lý như dữ liệu đầu vào.

### 3.1. Phân biệt ba nhóm header JavaScript có thể gửi

| Header | Mục đích hợp lệ | Rủi ro nếu server tin mù quáng |
| --- | --- | --- |
| **Accept** | Đề nghị định dạng response. | Client có thể yêu cầu định dạng không mong muốn; server phải kiểm soát nội dung được hỗ trợ. |
| **Content-Type** | Khai báo kiểu body request. | Client có thể khai sai; server cần parser và media type validation. |
| **Authorization** | Gửi credential do ứng dụng chủ động gắn. | Chuỗi Bearer không tự đúng; phải kiểm tra token, hiệu lực, đối tượng và quyền. |
| **X-CSRF-TOKEN** | Cung cấp token chống CSRF được server cấp. | Không chỉ kiểm tra header tồn tại; phải kiểm tra **giá trị token**. |
| **X-Client-Request-Id** | Liên kết log và trace. | ID có thể chứa giá trị giả hoặc payload log injection nếu không giới hạn/ký tự hóa. |
| **X-Tenant-Id** | Gợi ý tenant được client chọn, nếu hợp đồng cho phép. | Không dùng riêng header này để xác định quyền truy cập tenant. |
| **X-Requested-With** | Gợi ý request từ một thư viện AJAX. | Client có thể tự đặt; không phải chứng chỉ hợp lệ của browser hoặc user. |

**Authorization là request header mà JavaScript có thể chủ động thêm**, khác với Cookie và Origin. Với API khác origin, Authorization thường khiến request **cần CORS preflight**, nhưng preflight không xác minh token.

### 3.2. Quyền truy cập không được quyết định bằng custom header đơn độc

Giả sử API hỗ trợ:

~~~http
GET /api/tenant/orders HTTP/1.1
Host: api.example.com
X-Tenant-Id: tenant-b
~~~

Giá trị X-Tenant-Id là **dữ liệu client cung cấp**. Server có thể dùng nó để xác định tenant mà người dùng muốn làm việc, nhưng phải kiểm tra **người dùng đã xác thực có thuộc hoặc được phép truy cập tenant-b hay không**.

Không nên viết logic tương đương:

~~~java
// Sai về bảo mật: giá trị header tự cấp quyền tenant.
String tenant = request.getHeader("X-Tenant-Id");
return orderRepository.findAllByTenantId(tenant);
~~~

Thay vào đó, cần liên kết tenant được yêu cầu với danh tính đã xác thực, quyền hiện tại và phạm vi dữ liệu được phép. Đây là nguyên tắc phân quyền, không phải vấn đề CORS.

### 3.3. X-CSRF-TOKEN khác sự hiện diện của custom header

Một mô hình chống CSRF phổ biến là server cấp token và frontend gửi lại trong header:

~~~http
POST /api/orders HTTP/1.1
Content-Type: application/json
X-CSRF-TOKEN: token-issued-by-server
~~~

Spring Security cần **so khớp token** theo CSRF repository và request handler được cấu hình. Nếu server chỉ kiểm tra “có X-CSRF-TOKEN” mà không xác minh token, phòng vệ có thể không có ý nghĩa.

Thực tế, việc thêm custom header X-CSRF-TOKEN vào fetch cross-origin thường làm phát sinh preflight. Nhưng **preflight không phải bằng chứng CSRF token hợp lệ**.

### 3.4. Header custom ảnh hưởng CORS preflight

Ví dụ:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token,x-client-request-id
~~~

Các giá trị trong Access-Control-Request-Headers là **tên header request**, không phải giá trị của X-CSRF-TOKEN hoặc X-Client-Request-Id. Server có thể công bố những header cho phép:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: Content-Type, X-CSRF-TOKEN, X-Client-Request-Id
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

**Cho phép header qua CORS không có nghĩa giá trị header được server tin.** Tầng CORS, authentication, authorization và CSRF giải quyết những câu hỏi riêng.

## 4. Origin, Referer và Fetch Metadata: tín hiệu ngữ cảnh browser

Server có thể sử dụng một số header browser quản lý để hỗ trợ xác định nguồn/ngữ cảnh request. Trong mô hình tấn công từ một website bên ngoài chạy trong browser, các header này có giá trị bảo vệ nhất định vì **JavaScript của trang ngoài không tùy ý gán chúng**.

Tuy nhiên, cần hai giới hạn:

1. Header có thể **vắng mặt**, có giá trị **null**, bị ảnh hưởng bởi privacy policy, loại request, redirect hoặc browser.
2. Bất kỳ client ngoài browser nào cũng có thể tạo HTTP request và **tự đặt các chuỗi header tương tự**. Chúng không phải chứng chỉ danh tính.

### 4.1. Origin: so sánh chính xác scheme, host và port

Header Origin ở request CORS và một số request khác có thể là:

~~~http
Origin: https://app.example.com
~~~

Origin chứa **scheme, host, port** theo quy tắc origin; không chứa path, query, fragment.

Không dùng logic chứa chuỗi:

~~~text
Nếu Origin chứa "example.com" → cho phép
~~~

Vì **https://example.com.attacker.test** cũng chứa chuỗi example.com. Thay vào đó, khi xác định một origin đáng tin, hãy so sánh **đúng giá trị origin** với allowlist như:

~~~text
https://app.example.com
https://admin.example.com
~~~

Nếu cần nhiều môi trường, liệt kê chính xác origin theo cấu hình. Tránh phản chiếu mọi Origin một cách không kiểm soát rồi trả **Access-Control-Allow-Credentials: true**.

Một số request có thể có **Origin: null** do opaque origin, ví dụ các tài liệu sandbox hoặc ngữ cảnh riêng; đừng coi null là “origin nội bộ” hoặc một domain đáng tin. Một số request hợp lệ cũng không có Origin; chính sách phải có cách xử lý phù hợp với từng endpoint/method.

### 4.2. Referer: có thể chứa URL nguồn nhưng không bảo đảm luôn có

Header **Referer** (đúng tên HTTP lịch sử là Referer) có thể cho biết URL nguồn:

~~~http
Referer: https://app.example.com/dashboard
~~~

Khác Origin, Referer có thể chứa path theo referrer policy của browser và ngữ cảnh. Trình duyệt có thể giảm chi tiết chỉ còn origin hoặc không gửi Referer, ví dụ do chính sách quyền riêng tư, liên kết có noreferrer, chuyển từ kết nối an toàn sang không an toàn, hoặc trường hợp khác.

Trong JavaScript, không thể tùy ý tạo request header Referer qua đối tượng headers. Fetch cung cấp những tùy chọn **referrer** và **referrerPolicy** trong phạm vi các ràng buộc, nhưng không có nghĩa trang được tự ý mạo danh một URL cross-origin bất kỳ.

Nếu sử dụng Referer làm tín hiệu bổ trợ chống CSRF, phải xử lý **thiếu header**, chuẩn hóa giá trị và không dựa trên so khớp substring.

### 4.3. Sec-Fetch-Site

Trình duyệt hiện đại thường gửi **Sec-Fetch-Site** với những giá trị:

| Giá trị | Ý nghĩa thường gặp |
| --- | --- |
| **same-origin** | Request khởi tạo từ ngữ cảnh cùng origin với đích. |
| **same-site** | Khác origin nhưng cùng site (theo cách browser xác định). |
| **cross-site** | Nguồn và đích khác site. |
| **none** | Không có site khởi tạo thông thường, như một số điều hướng do người dùng khởi phát trực tiếp. |

Ví dụ frontend **https://app.example.com** gọi API **https://api.example.com**:

~~~http
GET /api/me HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Sec-Fetch-Site: same-site
Sec-Fetch-Mode: cors
Sec-Fetch-Dest: empty
~~~

Đây là yêu cầu **same-site nhưng cross-origin**, do app và api khác host. **Sec-Fetch-Site: same-site không chứng minh request đáng tin**, vì subdomain cùng site có thể bị chiếm quyền hoặc vận hành bởi bên không đáng tin.

### 4.4. Sec-Fetch-Mode, Dest và User

| Header | Ví dụ | Công dụng hỗ trợ |
| --- | --- | --- |
| **Sec-Fetch-Mode** | cors, no-cors, navigate, same-origin | Cho biết cách browser thực hiện request. |
| **Sec-Fetch-Dest** | empty, document, image, script, iframe | Nêu loại tài nguyên mà request nhắm tới. |
| **Sec-Fetch-User** | ?1 | Xuất hiện trong một số điều hướng có kích hoạt bởi người dùng, không phải mọi request. |

Một request điều hướng tài liệu có thể khác một request fetch API:

~~~http
GET /account HTTP/1.1
Host: app.example.com
Sec-Fetch-Mode: navigate
Sec-Fetch-Dest: document
Sec-Fetch-Site: none
Sec-Fetch-User: ?1
~~~

Đây là **ví dụ có thể xảy ra**, không bảo đảm mọi browser luôn gửi toàn bộ header đúng như vậy. Sec-Fetch-User không phải chứng cứ cho biết người dùng đồng ý với một giao dịch; nó chỉ giúp mô tả một loại ngữ cảnh khởi tạo request.

### 4.5. Dùng Fetch Metadata như một lớp bổ sung

Một ứng dụng có thể áp dụng **Fetch Metadata resource isolation policy** để từ chối một số request **cross-site** không được hỗ trợ, ví dụ request ghi dữ liệu từ website ngoài hệ thống. Nhưng cần lưu ý:

- Không từ chối mù quáng tất cả cross-site: điều hướng từ email, thanh toán, đăng nhập liên kết hoặc tài nguyên công khai có thể hợp lệ.
- Không cho mọi same-site đi qua như request đáng tin tuyệt đối: subdomain cùng site có thể không đáng tin.
- Header có thể thiếu với một số client/browser, và có thể bị giả bởi client ngoài browser.
- **Authentication, authorization và CSRF token** vẫn là lớp bắt buộc theo mô hình session/credential.

Một chính sách an toàn nên xác định rõ những endpoint cần bảo vệ, những ngoại lệ hợp lệ và cách xử lý fallback khi các header Fetch Metadata vắng mặt.

## 5. Cookie, Set-Cookie và những gì JavaScript nhìn thấy

Cookie là ví dụ quan trọng nhất về **thông tin do trình duyệt quản lý**. API có thể gửi:

~~~http
HTTP/1.1 200 OK
Set-Cookie: __Host-session=opaque-session-id; Secure; HttpOnly; Path=/; SameSite=Lax
~~~

Browser quyết định lưu cookie theo chính sách, và tự chọn những cookie đủ điều kiện cho các request tiếp theo:

~~~http
GET /api/me HTTP/1.1
Host: api.example.com
Cookie: __Host-session=opaque-session-id
~~~

Không cần JavaScript đọc hoặc chèn session ID để browser gửi cookie. Trên thực tế, dùng **HttpOnly** chính là cách ngăn script thông thường đọc trực tiếp mã phiên qua document.cookie.

### 5.1. Cookie và Set-Cookie có hai hướng truyền khác nhau

| Header / API | Hướng sử dụng | JavaScript nhìn thấy hoặc thao tác được gì? |
| --- | --- | --- |
| **Set-Cookie** response header | Server yêu cầu browser lưu/cập nhật cookie | Bị lọc khỏi những response header mà JavaScript đọc qua fetch Response.headers; browser vẫn có thể xử lý theo policy. |
| **Cookie** request header | Browser gửi tên=giá trị cookie phù hợp cho server | JavaScript không được tự gán Cookie header qua Fetch API. |
| **document.cookie** | API JavaScript quản lý một phần cookie của origin/tài liệu | Có thể đọc/ghi cookie không HttpOnly trong phạm vi chính sách; không xem được cookie HttpOnly. |
| **HttpOnly** | Thuộc tính Set-Cookie của server | JavaScript không thể bỏ qua HttpOnly để đọc cookie phiên. |
| **credentials: include** | Tùy chọn Fetch API | Cho phép browser xét gửi credentials cross-origin, không vượt qua chính sách cookie. |

Ví dụ:

~~~javascript
const response = await fetch("https://api.example.com/api/login", {
  method: "POST",
  credentials: "include",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ username: "demo", password: "example-only" })
});

// Không dùng response.headers.get("set-cookie") để lấy mã phiên.
console.log(response.headers.get("set-cookie")); // Thường là null
~~~

Đoạn code chỉ minh họa API đọc header, **không phải luồng đăng nhập hoàn chỉnh**: trong hệ thống session, POST đăng nhập có thể cần CSRF token theo cấu hình, và response cross-origin cần CORS thích hợp để JavaScript đọc. Mã phiên nên được bảo vệ bằng cookie HttpOnly thay vì trả trực tiếp cho mã frontend không cần thiết.

### 5.2. Cookie đủ điều kiện gửi phụ thuộc nhiều yếu tố

Các thuộc tính và điều kiện quan trọng:

- **Domain hoặc host-only:** xác định host nào có thể nhận cookie.
- **Path:** xác định phạm vi đường dẫn.
- **Secure:** yêu cầu kênh được browser xem là an toàn theo quy tắc cookie, thông thường HTTPS.
- **SameSite:** giới hạn gửi cookie trong các ngữ cảnh cross-site; Strict, Lax và None có ý nghĩa khác nhau.
- **Max-Age/Expires:** quyết định thời hạn của cookie.
- **Cookie partitioning và chính sách third-party:** có thể tiếp tục hạn chế cookie khi nhúng tài nguyên.
- **Fetch/XHR credentials mode:** quyết định request do API JavaScript tạo có được sử dụng credentials cross-origin hay không.

**HttpOnly không chặn browser gửi cookie.** Cookie có HttpOnly vẫn tham gia yêu cầu hợp lệ và vẫn có thể bị lợi dụng trong CSRF nếu server không có phòng vệ phù hợp.

Một cookie dành cho **api.example.com** có thể được gửi đến API khi frontend ở **app.example.com** tạo request có credentials: include, bởi cookie được chọn theo **host đích** và ngữ cảnh. Điều đó không trao cho JavaScript ở app.example.com quyền đọc cookie HttpOnly của api.example.com.

### 5.3. JavaScript có thể ghi một số cookie nhưng không thay browser quản lý

Tại origin phù hợp, JavaScript có thể tạo một cookie không HttpOnly:

~~~javascript
document.cookie = "theme=dark; Path=/; Secure; SameSite=Lax";
~~~

Browser vẫn kiểm tra phạm vi cookie, Secure, SameSite và các ràng buộc khác. JavaScript không thể tự tạo cookie **HttpOnly** bằng document.cookie. Browser không cho script của một origin tùy ý đặt cookie cho mọi domain khác.

Đừng dùng một cookie JavaScript tự đặt để làm bằng chứng danh tính. Giá trị cookie phía client là đầu vào cần xác minh, không phải quyền do browser cấp.

### 5.4. CORS có credentials không chấp nhận Allow-Origin wildcard

Với fetch cross-origin có cookie:

~~~javascript
await fetch("https://api.example.com/api/me", {
  credentials: "include"
});
~~~

API thường cần trả:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Không dùng:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

trong phản hồi CORS muốn được đọc với credentials. Browser không chấp nhận wildcard Allow-Origin cho ngữ cảnh đó. Mặt khác, **CORS không ép cookie phải được gửi**; nó điều chỉnh quyền đọc response và cơ chế preflight, còn cookie policy quyết định credential.

### 5.5. Response header được phơi bày cũng có giới hạn

Với API cross-origin, JavaScript không nhất thiết đọc được mọi response header ngay cả khi response được CORS cho phép. Server có thể dùng **Access-Control-Expose-Headers** cho các response header ứng dụng cần công bố, ví dụ X-Request-Id:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Expose-Headers: X-Request-Id
X-Request-Id: backend-trace-42
~~~

Frontend có thể đọc X-Request-Id khi CORS và expose policy phù hợp:

~~~javascript
const response = await fetch("https://api.example.com/api/me");
console.log(response.headers.get("x-request-id"));
~~~

**Set-Cookie là response header bị cấm phơi bày cho frontend (forbidden response-header name)**; không dùng Access-Control-Expose-Headers để kỳ vọng script đọc giá trị Set-Cookie. Không nhầm **request header bị cấm JavaScript đặt** với **response header bị cấm JavaScript đọc**.

## 6. Preflight: những header JavaScript cung cấp được hỏi trước khi gửi

Một request khác origin có thể cần **OPTIONS preflight** nếu có method hoặc header không thuộc CORS safelist. Ví dụ:

~~~javascript
await fetch("https://api.example.com/api/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken,
    "X-Client-Request-Id": "req-42"
  },
  body: JSON.stringify({ productId: 42 })
});
~~~

Ở đây csrfToken phải do ứng dụng cấp hợp lệ. **Content-Type application/json** và các custom headers khiến request CORS thông thường cần preflight.

Browser tạo:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token,x-client-request-id
~~~

Lưu ý: browser gửi **tên** các header dự kiến, **không gửi giá trị CSRF token**, không gửi JSON body của POST, và thông thường **không mang cookie phiên** ở preflight.

API có thể trả:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: Content-Type, X-CSRF-TOKEN, X-Client-Request-Id
Access-Control-Allow-Credentials: true
Access-Control-Max-Age: 600
Vary: Origin
~~~

Sau preflight hợp lệ, browser mới gửi POST thực. **POST vẫn phải được Spring Security kiểm tra CSRF token, authentication và authorization**. Response POST thực còn cần CORS header hợp lệ để JavaScript đọc kết quả.

### 6.1. Những request headers thuộc safelist

Các CORS-safelisted request headers phổ biến là **Accept**, **Accept-Language**, **Content-Language**, **Content-Type** với MIME type essence giới hạn và **Range** với cú pháp phù hợp. Tên được safelist chưa đủ: **giá trị và một số điều kiện bổ sung** cũng phải phù hợp.

CORS-safelisted methods thường gồm **GET, HEAD và POST**. POST với Content-Type request là **application/json** thường preflight, trong khi POST truyền form dạng **application/x-www-form-urlencoded**, **multipart/form-data** hoặc **text/plain** có thể không preflight nếu không có yếu tố khác.

**Không cần preflight không có nghĩa an toàn trước CSRF.** Một form POST có thể tới server mà website ngoài không cần đọc response. Bảo vệ CSRF không được phụ thuộc vào việc browser có gửi OPTIONS hay không.

### 6.2. Không dùng request header Access-Control-Allow-Origin để “sửa CORS”

Ví dụ sai về phía frontend:

~~~javascript
await fetch("https://api.example.com/api/me", {
  headers: {
    "Access-Control-Allow-Origin": "*"
  }
});
~~~

**Access-Control-Allow-Origin có hiệu lực trong response của server**, không phải một phép cấp quyền do client tự khai báo. Request header được JavaScript thêm vào có thể còn kích hoạt preflight không cần thiết; nó không khiến browser bỏ qua CORS.

Cách đúng: server hoặc proxy được phép cấu hình response CORS và giới hạn origin, method, headers theo hợp đồng API.

### 6.3. Authorization và việc gửi token

JavaScript có thể chủ động thêm Bearer:

~~~javascript
await fetch("https://api.example.com/api/me", {
  headers: {
    Authorization: "Bearer " + accessToken
  }
});
~~~

Header Authorization **không thuộc CORS safelist**, nên một GET cross-origin có thể vẫn phải preflight:

~~~http
OPTIONS /api/me HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Server cấp quyền gửi header Authorization qua CORS **không xác thực token**. Token phải được xác thực ở request thực, với kiểm tra hiệu lực, chữ ký nếu áp dụng, scope và quyền truy cập.

## 7. Cơ chế tin cậy ở reverse proxy và header chuyển tiếp

Trong hệ thống production, Spring Boot có thể chạy sau CDN, reverse proxy, load balancer hoặc API gateway:

~~~text
Browser → HTTPS reverse proxy → HTTP nội bộ → Spring Boot
           (public host)          (backend)
~~~

Các header như:

~~~http
Forwarded: for=198.51.100.10;proto=https;host=app.example.com
X-Forwarded-For: 198.51.100.10
X-Forwarded-Proto: https
X-Forwarded-Host: app.example.com
~~~

có thể được tầng proxy tin cậy bổ sung để backend biết host, scheme và client IP bên ngoài. Nhưng nếu proxy chỉ **chuyển nguyên** những header X-Forwarded-* do client tự gửi mà không làm sạch, backend có thể nhận giá trị giả.

**Không nên tin mặc định Forwarded/X-Forwarded-* chỉ vì tên header có chữ Forwarded.**

### 7.1. Ranh giới tin cậy phải được thiết lập tại hạ tầng

Các nguyên tắc:

1. Định nghĩa rõ **proxy nào được tin cậy** và kết nối nào có thể đến trực tiếp backend.
2. Cấu hình proxy **loại bỏ/ghi đè** những header chuyển tiếp do client ngoài tin cậy cung cấp, rồi thiết lập thông tin chính xác.
3. Chỉ bật cơ chế xử lý forwarded headers trên Spring Boot khi có **chuỗi proxy và chính sách tin cậy phù hợp**.
4. Giới hạn các host public hợp lệ để tránh Host header poisoning, redirect sai host hoặc sinh URL callback độc hại.
5. Kiểm tra phản hồi redirect, cookie Secure và absolute URL khi triển khai HTTPS ở proxy.

Một thiết lập Spring Boot liên quan là:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

**Đây không phải một nút “tin mọi proxy an toàn”.** Cấu hình trên cần được dùng cùng cách ly backend và chính sách làm sạch header chuyển tiếp ở hạ tầng. Cách cấu hình cụ thể tùy servlet container, WebFlux, proxy và môi trường.

### 7.2. IP client không nên lấy từ X-Forwarded-For tùy ý

Không dùng logic:

~~~java
// Không an toàn khi header do client bất kỳ cung cấp.
String userIp = request.getHeader("X-Forwarded-For");
if ("trusted-ip".equals(userIp)) {
    // Cấp quyền nhạy cảm.
}
~~~

X-Forwarded-For có thể do client ngoài tự gửi hoặc có nhiều địa chỉ qua các proxy. Kiểm tra IP nếu có phải dựa trên chuỗi proxy đáng tin, cách phân tích địa chỉ đúng và chính sách bổ sung; **không thay authentication/authorization bằng một request header tự khai**.

Tương tự, header X-User-Id hoặc X-Authenticated-User chỉ được coi là bằng chứng danh tính khi nó là một phần của **kiến trúc xác thực gateway được bảo vệ rõ ràng**, có loại bỏ header giả từ client, xác thực kết nối và giới hạn quyền truy cập trực tiếp backend. Nếu không, đó chỉ là dữ liệu client.

## 8. Spring Security Servlet: CORS, CSRF và header không đáng tin

Ví dụ API servlet dùng cookie/session và được frontend tại **https://app.example.com** truy cập cross-origin. Cấu hình dưới đây dành cho Spring Security 6.x.

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.CorsConfigurationSource;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;

@Configuration
class ServletSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .cors(Customizer.withDefaults())
                .authorizeHttpRequests(auth ->
                        auth.anyRequest().authenticated())
                // Giữ bảo vệ CSRF mặc định cho ứng dụng session.
                .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of(
                "Content-Type", "Authorization",
                "X-CSRF-TOKEN", "X-Client-Request-Id"));
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Cấu hình này:

- Giới hạn CORS cho origin cụ thể; không tự tin mọi subdomain có chuỗi example.com.
- Cho phép các header ứng dụng phù hợp với API; việc cho phép header không có nghĩa server tin giá trị.
- Để CORS được xử lý trước khi preflight không có cookie bị cơ chế xác thực chặn.
- Giữ CSRF protection mặc định cho những method thay đổi trạng thái thuộc phạm vi bảo vệ.
- Không cấp quyền tài nguyên chỉ dựa vào Origin, User-Agent, X-Client-Request-Id hoặc Sec-Fetch-Site.

Đây là ví dụ chính sách CORS, không chứa toàn bộ cơ chế đăng nhập, phân quyền từng nghiệp vụ hoặc endpoint cấp CSRF token. Với SPA dùng cookie/session, cần thiết kế luồng cấp và gửi CSRF token thật.

### 8.1. Đọc header trong Servlet chỉ là nhận dữ liệu

Một endpoint minh họa quan sát request:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class RequestContextController {

    record RequestInfo(String origin, String fetchSite, String clientId) {}

    @GetMapping("/api/diagnostics/request")
    RequestInfo inspect(HttpServletRequest request) {
        return new RequestInfo(
                request.getHeader("Origin"),
                request.getHeader("Sec-Fetch-Site"),
                request.getHeader("X-Client-Request-Id"));
    }
}
~~~

Chỉ dùng endpoint như trên **trong môi trường chẩn đoán được bảo vệ và cấp quyền thích hợp**, không mở công khai ở production để phơi bày chi tiết request không cần thiết. Kể cả khi getHeader trả giá trị Sec-Fetch-Site: same-origin, nó chỉ là một chuỗi HTTP tại server; không phải principal đã được xác thực.

Nếu muốn xác định người dùng, lấy **Authentication/Principal đã được Spring Security xác thực**, rồi kiểm tra authorization. Không dùng request.getHeader("X-User-Id") thay cho danh tính thực.

### 8.2. Không tắt CSRF chỉ vì frontend dùng custom header

Một SPA có thể gửi X-CSRF-TOKEN khi POST và khiến browser preflight. Nhưng Spring Security cần xác minh token qua CSRF repository/handler thích hợp.

CORS preflight có thể đạt trong khi POST vẫn bị 403 do token sai. Đây là kết quả cần thiết, không phải bằng chứng CORS hỏng. Không sửa bằng cách tắt CSRF trên toàn bộ /api/** khi API vẫn dựa vào cookie/session.

## 9. Spring Security Reactive/WebFlux: cùng ranh giới tin cậy

Trong WebFlux, dùng **ServerHttpSecurity** và CORS classes thuộc gói **org.springframework.web.cors.reactive**.

~~~java
import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .cors(cors -> cors.configurationSource(corsConfigurationSource()))
                .authorizeExchange(auth ->
                        auth.anyExchange().authenticated())
                // Giữ CSRF mặc định cho WebSession/cookie.
                .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(List.of(
                "Content-Type", "Authorization",
                "X-CSRF-TOKEN", "X-Client-Request-Id"));
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Phía WebFlux có thể đọc request headers thông qua **ServerWebExchange**:

~~~java
import org.springframework.web.server.ServerWebExchange;

String origin = exchange.getRequest()
        .getHeaders().getFirst("Origin");
String fetchSite = exchange.getRequest()
        .getHeaders().getFirst("Sec-Fetch-Site");
String clientId = exchange.getRequest()
        .getHeaders().getFirst("X-Client-Request-Id");
~~~

Đoạn thứ hai chỉ minh họa việc đọc bên trong một handler/filter đã có biến **exchange**; không phải hàm hoàn chỉnh. Các giá trị trên **không tự trao quyền**. Trong code reactive, danh tính và quyền phải đến từ cơ chế **ReactiveSecurityContext/Principal** do Spring Security xác thực phù hợp.

**Không trộn** CorsConfigurationSource của Servlet với WebFlux. Hai đoạn cấu hình tương ứng **hai stack riêng**, chọn đoạn phù hợp với ứng dụng thực tế.

## 10. Kiểm thử: browser tự đặt gì, JavaScript đặt được gì?

### 10.1. Kiểm tra browser bằng DevTools

Với trang thử nghiệm ở **https://app.example.com** và API tại **https://api.example.com**, mở **DevTools → Network** rồi thực hiện:

~~~javascript
const response = await fetch("https://api.example.com/api/me", {
  credentials: "include",
  headers: {
    Accept: "application/json",
    "X-Client-Request-Id": "browser-probe-42"
  }
});

console.log(response.status);
~~~

Quan sát:

1. Browser có tự thêm **Origin** hay **Sec-Fetch-Site/Mode/Dest** không?
2. Có OPTIONS preflight vì **X-Client-Request-Id** là custom header không thuộc safelist không?
3. OPTIONS có **Access-Control-Request-Headers: x-client-request-id** không?
4. Request GET thực có mang Cookie không? Nếu không, kiểm tra credentials và cookie policy.
5. Response thực có Allow-Origin/Allow-Credentials phù hợp không?
6. X-Client-Request-Id có xuất hiện đúng không, nhưng server có **giới hạn độ dài/ký tự** khi ghi log không?

Ví dụ **không nên dựa vào**:

~~~javascript
await fetch("https://api.example.com/api/me", {
  headers: {
    Cookie: "session=fake",
    Origin: "https://app.example.com",
    "Sec-Fetch-Site": "same-origin"
  }
});
~~~

Trong trình duyệt, các header đó không thể được script gán tùy ý. Không nên dùng Console ở client làm nguồn duy nhất để xác nhận: **Network request thực tế** mới cho thấy browser đã gửi gì.

### 10.2. Thử bằng curl để thấy ranh giới tin cậy server

Trong **môi trường kiểm thử do bạn kiểm soát**, client ngoài browser có thể tự đặt:

~~~bash
curl -i "https://api.example.com/api/diagnostics/request" \
  -H "Origin: https://app.example.com" \
  -H "Sec-Fetch-Site: same-origin" \
  -H "X-Client-Request-Id: fake-client-id"
~~~

Điều này chứng minh các chuỗi header **không phải bằng chứng không thể giả mạo từ phía server**. API phải tiếp tục yêu cầu authentication/authorization ngay cả khi Origin hoặc Sec-Fetch-Site trông hợp lệ.

Nếu endpoint được bảo vệ, curl không có credentials có thể nhận 401/403 và bạn không cần tắt bảo mật để quan sát hiện tượng. Có thể dùng một endpoint kiểm thử riêng hoặc log đã được kiểm soát quyền phù hợp. Không thử trên hệ thống của bên thứ ba khi chưa được cho phép.

### 10.3. Kiểm tra OPTIONS preflight

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/orders" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Kết quả cần kiểm tra:

- HTTP status của OPTIONS.
- Access-Control-Allow-Origin có đúng **origin cụ thể** không.
- Allow-Methods có bao gồm POST không.
- Allow-Headers có cho phép Content-Type và X-CSRF-TOKEN không.
- Phản hồi có cho phép credentials nếu API thực sự dùng cookie/session không.

Dùng thêm một **Origin không được phép** trong môi trường test để kiểm tra API không phản chiếu tùy ý origin. **curl không thực thi SOP hoặc CORS như browser**, nên sau đó phải kiểm tra tiếp bằng DevTools.

### 10.4. Kiểm tra Origin vắng mặt hoặc null

Không phải mọi request đều có Origin; một số có thể có **Origin: null**. Hãy thiết kế test cho:

~~~text
Origin: https://app.example.com  → origin được phép cho tích hợp hợp lệ
Origin: https://evil.test        → origin không được phép
Origin: null                     → nguồn opaque/null, không mặc định tin
Không có Origin                  → dùng chính sách fallback theo endpoint
~~~

Nếu server triển khai kiểm tra Origin để phòng vệ CSRF, phải xác định rõ khi nào thiếu header được chấp nhận và cần kiểm tra bổ sung nào. Không suy ra request không có Origin là “chắc chắn từ browser an toàn”, cũng không mặc định mọi client hợp lệ đều có Origin.

## 11. Ma trận chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng kiểm tra |
| --- | --- | --- |
| JavaScript cố thêm Cookie nhưng Network không có giá trị đó. | Cookie là forbidden request header. | Dùng cookie jar/credentials, kiểm tra Domain/Path/SameSite/Secure. |
| JavaScript gán Sec-Fetch-Site giả nhưng browser gửi giá trị khác. | Tiền tố Sec- do browser quản lý. | Kiểm tra ngữ cảnh request thực, không cố ghi đè. |
| GET cross-origin có X-Client-Request-Id xuất hiện OPTIONS. | Custom header không thuộc CORS safelist. | Cho phép header qua CORS khi cần và xử lý preflight. |
| OPTIONS trả 401/403. | CORS chưa được xử lý trước auth, hoặc Origin/method/header bị từ chối. | Kiểm tra security filter chain, gateway và policy CORS. |
| OPTIONS đạt, POST trả 403. | CSRF token hoặc authorization không hợp lệ. | Kiểm tra POST thực, token và quyền, không chỉ CORS. |
| POST chạy ở server nhưng frontend báo CORS. | Actual response thiếu Allow-Origin/Allow-Credentials. | Kiểm tra response thực; tránh retry tạo tác dụng phụ. |
| Response có Set-Cookie nhưng response.headers.get không thấy. | Set-Cookie bị lọc khỏi API đọc response headers. | Kiểm tra cookie bằng DevTools Storage/Network, không đọc trực tiếp header từ JS. |
| Fetch credentials: include nhưng cookie không gửi. | Cookie không đủ điều kiện hoặc bị chặn bởi browser. | Kiểm tra host, Domain/Path/Secure/SameSite, site ngữ cảnh và policy browser. |
| Backend nhìn thấy X-Forwarded-Proto giả dẫn đến redirect sai. | Proxy không làm sạch header, hoặc backend tin header không đúng nguồn. | Kiểm tra trusted proxy, chiến lược forwarded headers và direct access. |
| Dùng X-Tenant-Id để truy cập tài nguyên người khác. | Server coi header client khai là quyền truy cập. | Xác thực principal và phân quyền tenant/tài nguyên. |
| User-Agent có vẻ là browser đáng tin, nhưng API bị gọi từ script backend. | User-Agent dễ giả từ client HTTP. | Không cấp quyền dựa trên User-Agent; dùng auth và bảo vệ endpoint. |
| Browser báo lỗi trước request do CSP connect-src. | CSP chặn đích trước/sát giai đoạn fetch. | Kiểm tra CSP và Console, không sửa CORS khi nguyên nhân ở CSP. |

## 12. Bài tập tình huống

### Tình huống A — Thêm Cookie bằng fetch

SPA cố truyền Cookie: session=abc trong headers của fetch. Có thể dựa vào cách này để gửi cookie phiên không?

**Đáp án:** Không. Cookie là forbidden request header đối với JavaScript trong browser. Browser tự quyết định gửi cookie đã lưu theo URL, credentials mode và chính sách cookie.

### Tình huống B — Mạo danh Origin

Mã ở **https://attacker.test** cố truyền Origin: https://app.example.com trong request fetch. Có thay đổi được Origin browser tính ra không?

**Đáp án:** Không theo cách gán header trực tiếp qua Fetch API trong browser. Nhưng client ngoài browser có thể tự đặt header Origin nên server vẫn phải xác thực người dùng độc lập.

### Tình huống C — Sec-Fetch-Site là same-site

API thấy Sec-Fetch-Site: same-site đến từ một subdomain không đáng tin. Có thể bỏ qua CSRF token không?

**Đáp án:** Không. Same-site khác same-origin và không chứng minh subdomain đáng tin. Với session cookie và hành động thay đổi trạng thái, vẫn cần CSRF protection thích hợp.

### Tình huống D — GET có Authorization

SPA gọi GET API khác origin và chủ động thêm Authorization: Bearer token. Browser có thể gửi OPTIONS dù method là GET không?

**Đáp án:** Có. Authorization không thuộc CORS safelist; preflight hỏi server có cho phép header này không. Token vẫn phải được server xác minh ở request GET thực.

### Tình huống E — X-Tenant-Id do frontend gửi

Client tự gán X-Tenant-Id: tenant-admin. Backend chỉ dựa vào header để truy xuất dữ liệu tenant đó. Có an toàn không?

**Đáp án:** Không. Header là dữ liệu do client khai. Backend phải đối chiếu tenant được yêu cầu với danh tính đã xác thực và quyền của user.

### Tình huống F — Referer trống

Một request hợp lệ không có Referer do referrer policy hoặc ngữ cảnh browser. Có thể coi thiếu Referer là chứng cứ xác thực thất bại không?

**Đáp án:** Không thể kết luận chỉ dựa vào Referer. Chính sách cần quy định fallback rõ ràng theo endpoint, có thể kết hợp Origin và CSRF token; authentication vẫn độc lập.

### Tình huống G — Origin null

Một request mang Origin: null từ tài liệu có opaque origin. Server có nên tự coi đây là origin nội bộ đáng tin không?

**Đáp án:** Không. null không đại diện cho một domain nội bộ được xác thực. Nếu ứng dụng không có nhu cầu đặc biệt đã được đánh giá, không nên đưa null vào allowlist có credentials.

### Tình huống H — Set-Cookie không đọc được bằng JavaScript

Browser lưu cookie từ response nhưng response.headers.get("set-cookie") trả null. Có phải server chưa gửi Set-Cookie?

**Đáp án:** Không nhất thiết. Set-Cookie là forbidden response-header name với API đọc response headers của browser. Cần kiểm tra Network và Storage; việc cookie có được lưu còn phụ thuộc chính sách của browser.

### Tình huống I — X-Forwarded-For bị giả

API lấy IP từ X-Forwarded-For của mọi request trực tiếp và cấp quyền quản trị nếu IP nằm trong allowlist. Vấn đề gì?

**Đáp án:** Client có thể tự đặt X-Forwarded-For. Chỉ tin dữ liệu do proxy đã được xác thực/giới hạn và làm sạch, đồng thời không thay thế phân quyền quản trị bằng header do client gửi.

### Tình huống J — Preflight đạt nhưng CSRF token sai

OPTIONS trả 204 với Allow-Origin và Allow-Headers đúng, POST có X-CSRF-TOKEN nhưng giá trị sai. Có nên cho POST thực hiện để “phù hợp CORS” không?

**Đáp án:** Không. CORS chỉ cho phép một loại request cross-origin. CSRF token phải được kiểm tra ở POST thực; giá trị sai cần bị từ chối.

### Tình huống K — Allow-Origin trong request

Frontend tự thêm Access-Control-Allow-Origin: * vào request để chữa lỗi CORS. Có đúng không?

**Đáp án:** Không. Browser quyết định quyền đọc phản hồi từ **Access-Control-Allow-Origin ở response** do server trả. Gắn header đó vào request không sửa được policy.

### Tình huống L — Header log bị chèn dòng

Một client đặt X-Client-Request-Id bằng giá trị dài, chứa ký tự điều khiển hoặc chuỗi giả dạng log. Nếu backend ghi nguyên giá trị này vào log thì sao?

**Đáp án:** Có thể gây nhiễu hoặc log injection tùy hệ thống ghi log. Hãy giới hạn độ dài, ký tự hợp lệ và dùng logging có escaping/structured fields; không tin custom header chỉ vì nó đến từ frontend được CORS cho phép.

## 13. Ghi nhớ

- **Browser quản lý một số request header** như Cookie, Host, Origin, Content-Length và Sec-Fetch-*. Mã JavaScript trang web không được tùy ý ghi đè chúng qua fetch/XHR.
- **JavaScript có thể đặt nhiều request header khác** như Accept, Content-Type, Authorization, X-CSRF-TOKEN và custom X-*; các giá trị này vẫn là đầu vào không đáng tin của server.
- **Header browser quản lý không phải bằng chứng xác thực ở server**: HTTP client ngoài browser hoặc proxy không đáng tin có thể tự tạo các chuỗi Origin, User-Agent, Sec-Fetch-Site và X-Forwarded-*.
- **Referer có thể thiếu hoặc bị rút gọn**; **Origin có thể vắng mặt hoặc null**; **Sec-Fetch-*** mô tả ngữ cảnh request trong những browser hỗ trợ, không chứng minh quyền thao tác.
- **Cookie có thể tự được browser gửi**, kể cả khi HttpOnly ngăn JavaScript đọc nó. CORS không thay thế SameSite hoặc CSRF token.
- **Set-Cookie là response header browser có thể xử lý nhưng JavaScript không đọc trực tiếp qua Fetch Response.headers**; Access-Control-Expose-Headers không làm Set-Cookie trở thành header được đọc tự do.
- **CORS preflight** xin phép method/header trước request thực; thành công ở preflight không có nghĩa token hợp lệ, người dùng đủ quyền hoặc frontend chắc chắn đọc được response thực.
- Trong **Spring Security Servlet và Reactive**, cấu hình CORS chính xác, giữ CSRF khi dùng session/cookie, lấy danh tính từ SecurityContext/Principal và phân quyền server-side.
- **Chỉ tin Forwarded/X-Forwarded-*** sau khi đã thiết lập chuỗi proxy đáng tin và làm sạch header từ client, nhất là với HTTPS, redirect, Host và IP.
