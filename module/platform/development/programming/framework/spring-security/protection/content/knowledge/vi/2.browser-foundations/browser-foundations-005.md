# Yêu cầu cùng nguồn, khác nguồn và khác site

## Mục tiêu bài học

Trong bảo mật web, một yêu cầu HTTP không chỉ được mô tả bằng **method** và **URL**. Trình duyệt còn xem xét **ngữ cảnh tạo yêu cầu**: trang nào khởi tạo, URL đích thuộc origin/site nào, request được thực hiện bằng fetch, form, điều hướng hay tài nguyên nhúng. Những thông tin này ảnh hưởng trực tiếp đến **Same-Origin Policy (SOP)**, **CORS**, cookie **SameSite**, **CSRF** và các header **Fetch Metadata**.

Bài thuộc chương **Nền tảng trình duyệt** của module **SPRING_SECURITY_HTTP_PROTECTION**. Người học áp dụng kiến thức vào các lớp bảo vệ HTTP và trình duyệt trong **Spring Security**, bao gồm CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và session, trên cả **Servlet** và **Reactive (WebFlux)**.

Sau bài học, bạn có thể:

1. Phân loại request là **same-origin**, **cross-origin nhưng same-site** hoặc **cross-site** với các URL HTTP/HTTPS thông thường.
2. Giải thích vì sao request **đã gửi đến server** nhưng JavaScript **không đọc được phản hồi**, hoặc vì sao request bị chặn từ bước **preflight**.
3. Phân biệt điều kiện trình duyệt **gửi cookie** với điều kiện **CORS cho đọc response**, và xác định nguy cơ CSRF trong từng loại request.
4. Phân tích header **Origin**, **Sec-Fetch-Site**, **Sec-Fetch-Mode**, **Sec-Fetch-Dest**, cùng các trường hợp thiếu header hoặc request điều hướng.
5. Dùng DevTools và cấu hình Spring Security Servlet/WebFlux để kiểm thử ba nhóm request, xử lý CORS và giữ các kiểm tra CSRF, authentication, authorization.

## 1. Một request được xét từ đâu đến đâu?

Giả sử người dùng mở trang:

~~~text
Trang nguồn: https://app.example.com/dashboard
~~~

JavaScript trong trang có thể gọi API, trang có thể tải ảnh, hoặc người dùng bấm liên kết. Khi đó ta cần tách hai thành phần:

- **Nguồn/initiator**: ngữ cảnh khởi tạo request, thường là trang hoặc tài liệu đang chạy mã.
- **Đích/target**: URL HTTP/HTTPS mà trình duyệt đang định truy cập.

Ví dụ:

~~~text
┌─────────────────────────────────┐
│ https://app.example.com         │
│ JavaScript / HTML / navigation  │
└───────────────┬─────────────────┘
                │
          Khởi tạo request
                │
      ┌─────────┼────────────────────┐
      ▼         ▼                    ▼
  /api/me   https://api...      https://news...
 same-      cross-origin         cross-site
 origin     nhưng same-site      (nếu khác site)
~~~

Để xác định quan hệ, **trước tiên so origin**, sau đó **so site**. Tuy nhiên, không phải mọi request đều có một trang nguồn đơn giản: URL người dùng nhập trên thanh địa chỉ, bookmark, điều hướng từ trình duyệt hoặc tài liệu có opaque origin có thể có ngữ cảnh đặc biệt. Khi phân tích, hãy dùng dữ liệu request thực tế thay vì suy ra từ địa chỉ máy chủ.

## 2. Quy tắc xác định origin và site

### 2.1. Origin: scheme + host + port

Với HTTP/HTTPS thông thường:

**Origin = (scheme, host, port)**

~~~text
https://api.example.com:8443/orders?status=new#latest
^^^^^   ^^^^^^^^^^^^^^^ ^^^^
scheme        host        port

Origin: https://api.example.com:8443
~~~

Các thành phần **path, query, fragment** không thuộc origin. Cổng mặc định **80** với HTTP và **443** với HTTPS được chuẩn hóa khi so sánh.

~~~text
https://app.example.com          = https://app.example.com:443
https://app.example.com          ≠ http://app.example.com
https://app.example.com          ≠ https://api.example.com
https://app.example.com          ≠ https://app.example.com:8443
~~~

Tên host HTTP/HTTPS không phân biệt chữ hoa/chữ thường sau khi chuẩn hóa. **Hai tên host cùng trỏ về một IP vẫn có thể khác origin**. Tương tự, localhost và 127.0.0.1 không trở thành một host chỉ vì cùng chỉ về máy đang chạy.

**SOP và CORS xét ranh giới origin**. Đối với việc đọc phản hồi cross-origin từ JavaScript, trình duyệt phải áp dụng CORS khi API hoặc kiểu request yêu cầu cơ chế đó.

### 2.2. Site: scheme + miền có thể đăng ký

Trong cách xét **schemeful same-site** hiện đại, đối với tên miền HTTP/HTTPS thông thường:

**Site = (scheme, registrable domain)**

**Registrable domain** được xác định theo hậu tố công cộng (Public Suffix List), thường diễn đạt là **eTLD+1**. Port không tham gia phép so sánh site; subdomain có thể khác mà site vẫn giống nhau.

~~~text
https://app.example.com      → site https://example.com
https://api.example.com:8443 → site https://example.com
https://billing.example.net  → site https://example.net
http://app.example.com       → site http://example.com
~~~

Với miền như **shop.example.co.uk**, hậu tố công cộng là **co.uk**, nên miền có thể đăng ký thường là **example.co.uk**. Không viết phép tính site bằng cách “lấy hai nhãn cuối của hostname”: quy tắc này sai với nhiều hậu tố công cộng và dịch vụ nhiều người thuê.

Với host đặc biệt hoặc IP không có registrable domain, trình duyệt dùng quy tắc phù hợp dựa trên host. Trong ví dụ phát triển thông thường, **http://localhost:3000** và **http://localhost:8080** là same-site nhưng khác origin.

**Same-site chỉ là quan hệ địa chỉ, không phải bằng chứng hai hệ thống cùng đáng tin.** Subdomain do một đối tác vận hành hoặc bị chiếm quyền có thể cùng site với API nhạy cảm.

### 2.3. Ba loại yêu cầu quan trọng

| Loại request | Quan hệ origin | Quan hệ site | Ý nghĩa |
| --- | --- | --- | --- |
| **Same-origin** | Cùng scheme, host, port | Thường same-site | JavaScript thường không cần CORS để đọc response của request cùng origin. |
| **Cross-origin, same-site** | Khác ít nhất một thành phần origin | Cùng schemeful site | JavaScript cần CORS để đọc response cross-origin; SameSite cookie có thể được gửi trong ngữ cảnh phù hợp. |
| **Cross-site** | Khác origin với URL thông thường | Khác schemeful site | JavaScript cần CORS để đọc response; cookie SameSite thường giới hạn nhiều loại request. |

Cách phân loại này không thay thế các chính sách khác: ngay cả same-origin request vẫn có thể bị CSP, kiểm tra quyền, session hoặc CSRF từ chối.

### 2.4. Bảng phân loại với URL nguồn cố định

Giả sử request được khởi tạo từ **https://app.example.com/dashboard**, cổng HTTPS mặc định 443:

| URL đích | Kết luận | Lý do |
| --- | --- | --- |
| https://app.example.com/api/me | **Same-origin** | Trùng scheme, host, port. |
| https://app.example.com:443/api/me | **Same-origin** | 443 là cổng mặc định của HTTPS. |
| https://app.example.com:8443/api/me | **Cross-origin, same-site** | Port khác, site không xét port. |
| https://api.example.com/orders | **Cross-origin, same-site** | Khác subdomain, cùng scheme và registrable domain. |
| https://example.com/account | **Cross-origin, same-site** | Host khác nhưng cùng site https://example.com. |
| http://app.example.com/api/me | **Cross-site** | Scheme khác; schemeful site tính scheme. |
| https://app.example.net/api/me | **Cross-site** | Registrable domain khác. |
| https://app.example.com.evil.test/api/me | **Cross-site** | Miền có thể đăng ký là evil.test, không phải example.com. |
| https://app.example.com/profile?tab=1#top | **Same-origin** | Path, query, fragment không đổi origin. |

Với ứng dụng SPA đặt tại **http://localhost:5173** và Spring Boot API tại **http://localhost:8080**, request từ SPA đến API là **cross-origin, same-site**. Đó là lý do trình duyệt vẫn có thể hiển thị lỗi CORS dù cả hai dịch vụ chạy trên cùng máy.

## 3. Cùng một URL đích, kiểu request khác nhau thì hành vi khác nhau

Không chỉ quan hệ nguồn–đích, **cách khởi tạo request** cũng quyết định các hạn chế bảo mật:

| Cách khởi tạo | Ví dụ | Có thể gửi cross-origin? | Script có đọc được response? |
| --- | --- | --- | --- |
| **fetch / XMLHttpRequest** | JavaScript lấy JSON API | Có, tùy CORS mode, preflight và các chính sách khác | Chỉ khi đáp ứng SOP/CORS hoặc cơ chế cho phép tương ứng. |
| **Form HTML** | Form POST sang URL ngoài | Thường có thể gửi theo quy tắc form và browser | Script nguồn không tự được đọc nội dung phản hồi của trang đích. |
| **Điều hướng cấp cao nhất** | Bấm liên kết, nhập URL | Thường có thể điều hướng theo quy tắc trình duyệt | Trang nguồn không được đọc DOM trang đích cross-origin. |
| **Ảnh/video/tài nguyên nhúng** | img, video, stylesheet | Nhiều loại có thể tải cross-origin | Hiển thị được không có nghĩa đọc được mọi pixel/body. |
| **iframe** | Nhúng trang từ host khác | Có thể nhúng nếu trang đích và trình duyệt cho phép | Đọc DOM iframe cross-origin bị SOP hạn chế. |
| **Script từ CDN** | script src ở host khác | Có thể tải/thực thi nếu chính sách cho phép | Mã nhúng thường chạy trong origin của trang **nhúng**, nên cần tin cậy nguồn script. |

Một POST có tác dụng phụ có thể **đến server mà không cho website nguồn đọc phản hồi**. Đây là nền tảng giải thích nguy cơ CSRF. Ngược lại, fetch có header không nằm trong CORS safelist có thể bị dừng ở **OPTIONS preflight**, lúc đó POST thực tế chưa được gửi.

### 3.1. Request same-origin

Trang nguồn **https://app.example.com** gọi:

~~~javascript
const response = await fetch("/api/me");
if (!response.ok) {
  throw new Error("HTTP " + response.status);
}
const profile = await response.json();
~~~

URL tương đối được giải quyết thành URL cùng origin (giả sử base URL của tài liệu không bị thay đổi). Trình duyệt không cần API công bố chính sách CORS để JavaScript đọc JSON same-origin.

Nhưng request này vẫn có thể bị **401** (chưa xác thực), **403** (không đủ quyền hoặc CSRF với thao tác thay đổi trạng thái), **CSP connect-src**, hoặc cơ chế bảo vệ khác. Same-origin không đồng nghĩa “luôn được phép”.

### 3.2. Request cross-origin nhưng same-site

Trang nguồn **https://app.example.com** gọi:

~~~javascript
const response = await fetch("https://api.example.com/api/me");
const profile = await response.json();
~~~

Host khác nhau nên request **cross-origin**; JavaScript cần cơ chế CORS để đọc body. Hai host có thể **same-site**, nhưng quan hệ same-site **không mở khóa SOP**.

Nếu API chỉ nhận cookie phiên, cần xem thêm **credentials** của fetch: mặc định fetch là **same-origin**, nên request cross-origin không tự đưa cookie API vào dù hai host cùng site.

### 3.3. Request cross-site

Trang nguồn **https://app.example.com** gọi:

~~~javascript
const response = await fetch("https://partner.example.net/api/public");
const data = await response.json();
~~~

Đây là **cross-site** vì khác registrable domain. Mã JavaScript vẫn có thể đọc dữ liệu nếu API chủ đích cho phép CORS phù hợp, chẳng hạn dữ liệu công khai. Nhưng cookie SameSite=Strict/Lax của đích có các giới hạn cross-site; muốn dùng credential trong ngữ cảnh khác site cần cân nhắc cookie, fetch mode và chính sách bên thứ ba.

Không được suy ra “cross-site” nghĩa là API luôn phải từ chối. Có những tích hợp cross-site hợp pháp: dữ liệu công khai, đăng nhập liên kết hoặc widget nhúng. Điều cần làm là quyết định rõ **request nào được cho phép, với loại credential nào và để thực hiện hành động gì**.

## 4. Same-Origin Policy và CORS: quyền đọc khác với quyền gửi

**Same-Origin Policy (SOP)** hạn chế khả năng mã từ origin A đọc và tương tác với dữ liệu origin B trong trình duyệt. **Cross-Origin Resource Sharing (CORS)** là cách server B cấp quyền đọc phản hồi cho các origin phù hợp khi dùng những API như fetch/XHR.

Giả sử request:

~~~http
GET /api/catalog HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
~~~

Để cho JavaScript từ app.example.com đọc JSON, API có thể trả:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Vary: Origin
Content-Type: application/json

{"products":[]}
~~~

Những điểm cần nhớ:

- Header **Origin** chứa **scheme, host, port**, không kèm path hoặc query.
- Nếu server chỉ cho phép một số origin, **Access-Control-Allow-Origin** phải phản hồi đúng chính sách đó.
- **Vary: Origin** hữu ích khi nội dung header CORS phụ thuộc Origin và có cache trung gian.
- API công khai, không dùng credentials có thể cân nhắc wildcard **Access-Control-Allow-Origin: *** trong phạm vi phù hợp. API dùng cookie phiên không nên mở bừa bãi cho mọi origin.
- CORS không thay thế xác thực và phân quyền. HTTP client ngoài trình duyệt như curl không bị SOP/CORS chặn việc đọc phản hồi.

### 4.1. Khi nào cần preflight?

Một số request cross-origin phải qua **OPTIONS preflight**. Ví dụ frontend gửi POST JSON có header chống CSRF:

~~~javascript
// csrfToken được ứng dụng cấp hợp lệ qua luồng riêng.
await fetch("https://api.example.com/api/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ productId: 42 })
});
~~~

Trình duyệt thường gửi:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Máy chủ cho phép có thể trả:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET, POST
Access-Control-Allow-Headers: Content-Type, X-CSRF-TOKEN
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Khi preflight được trình duyệt chấp nhận, POST thực tế mới được gửi. POST vẫn phải qua authentication, authorization và kiểm tra CSRF của Spring Security.

**Preflight không phải bước xác thực** và thường không kèm cookie/session. Nếu middleware yêu cầu đăng nhập trước khi xử lý OPTIONS, có thể khiến request hợp lệ bị lỗi CORS.

### 4.2. Không phải mọi POST cross-origin đều preflight

Một form HTML có thể gửi POST với kiểu nội dung được hỗ trợ như **application/x-www-form-urlencoded** mà không phải thực hiện một CORS preflight giống request JSON có header tùy chỉnh:

~~~html
<form action="https://api.example.com/transfer" method="POST">
  <input type="hidden" name="amount" value="100">
  <button type="submit">Gửi</button>
</form>
~~~

Trong môi trường thử nghiệm, request này có thể đến server; việc cookie được gửi còn tùy **SameSite** và các thuộc tính khác. CORS không phải tấm khiên chống CSRF. Endpoint thay đổi trạng thái cần kiểm tra CSRF phù hợp, **kể cả khi trang khác origin không đọc được response**.

### 4.3. mode: no-cors không phải giải pháp lấy JSON

~~~javascript
const response = await fetch("https://api.example.com/api/catalog", {
  mode: "no-cors"
});

console.log(response.type);   // Thường là "opaque"
console.log(response.status); // 0 đối với opaque response
~~~

Một opaque response không cho JavaScript truy cập body hoặc status HTTP thực như phản hồi thông thường. **no-cors không tắt SOP** và không phải cách hợp lệ để đọc dữ liệu API khi server thiếu cấu hình CORS.

### 4.4. Redirect có thể thay đổi origin cuối cùng

Một fetch bắt đầu ở cùng origin nhưng server trả **302/307/308** chuyển tới origin khác. Khi đó, cách browser xử lý chuỗi redirect và response cuối có thể đưa request qua ranh giới CORS; preflight và redirect còn có các điều kiện riêng.

Ví dụ:

~~~text
https://app.example.com/api/report
    └─ HTTP 302 → https://reports.example.net/export
                         └─ phản hồi cuối cross-origin
~~~

Khi DevTools báo lỗi CORS, **kiểm tra toàn bộ redirect chain**, không chỉ URL đầu tiên mà ứng dụng gọi. Nếu một request có cookie/session bị redirect sang host khác, hãy kiểm tra URL mới, chính sách gửi cookie và nguy cơ để lộ token qua tham số URL hoặc header.

### 4.5. CSP, mixed content và security headers vẫn có thể chặn request

CORS không phải chính sách duy nhất ảnh hưởng request. Chẳng hạn:

- **Content-Security-Policy: connect-src** có thể giới hạn các đích fetch, XHR, WebSocket hoặc các kết nối liên quan.
- **Mixed Content** có thể khiến trình duyệt chặn một số request không an toàn từ trang HTTPS sang HTTP.
- **Content-Security-Policy: frame-ancestors** hoặc **X-Frame-Options** có thể ngăn nhúng một trang vào iframe, tách biệt với quyền đọc DOM.
- **HSTS** giúp trình duyệt dùng HTTPS cho host có chính sách được biết, nhưng không khiến HTTP và HTTPS thành cùng origin.
- Một số chính sách về tài nguyên khác origin như **Cross-Origin-Resource-Policy (CORP)** có thể giới hạn việc tải một số tài nguyên theo kiểu no-cors, trong khi **CORS** tập trung vào quyền truy cập phản hồi cho những API liên quan.

Vì vậy lỗi “bị chặn bởi trình duyệt” cần được chẩn đoán dựa trên **thông báo cụ thể và HTTP headers thực tế**.

## 5. Cookie và credentials: gửi được không có nghĩa đọc được response

Trình duyệt có thể tự gắn cookie session vào request khi URL đích, thuộc tính cookie và ngữ cảnh khởi tạo phù hợp. Nhưng **fetch credentials**, **SameSite cookie** và **CORS** là ba bước đánh giá khác nhau.

### 5.1. Cookie được chọn theo URL và ngữ cảnh

Một cookie ví dụ do **https://api.example.com** tạo:

~~~http
Set-Cookie: __Host-session=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Trình duyệt cân nhắc:

| Điều kiện | Tác động |
| --- | --- |
| **Host-only / Domain** | Cookie có áp dụng cho host đích không? |
| **Path** | Đường dẫn đích có khớp phạm vi cookie không? |
| **Secure** | URL có dùng kênh được xem là an toàn theo chính sách cookie không? |
| **SameSite** | Request trong ngữ cảnh same-site hay cross-site nào? |
| **Expires/Max-Age** | Cookie có còn hiệu lực phía browser không? |
| **Third-party cookie/partitioning** | Cookie có bị chặn hoặc phân vùng trong ngữ cảnh nhúng không? |
| **Credentials mode** | API fetch/XHR có cho phép gửi credentials của request này không? |

**HttpOnly không cấm browser gửi cookie**: thuộc tính này chặn JavaScript thông thường đọc giá trị cookie qua document.cookie. Session cookie HttpOnly vẫn có thể được browser gửi khi các điều kiện phù hợp; đó cũng là lý do HttpOnly không tự chống CSRF.

Cookie **không được phân vùng theo port** như origin. Một cookie của host localhost có thể được gửi tới các port khác nhau trên localhost nếu các điều kiện khác phù hợp, trong khi hai URL vẫn cross-origin.

### 5.2. fetch credentials = same-origin, include và omit

| Lựa chọn | Hành vi đối với request do fetch thực hiện |
| --- | --- |
| **same-origin** (mặc định) | Gửi credentials cho request same-origin khi phù hợp; không tự gửi credentials cross-origin. |
| **include** | Cho phép gửi credentials cả với request cross-origin, nhưng vẫn tuân theo chính sách cookie và browser. |
| **omit** | Không gửi credentials của request; cũng không xử lý Set-Cookie theo luồng credentials thông thường của fetch. |

Ví dụ **https://app.example.com** gọi **https://api.example.com**:

~~~javascript
// Cross-origin: mặc định không mang cookie API trong fetch.
await fetch("https://api.example.com/api/me");

// Đề nghị browser gửi cookie nếu các điều kiện khác cho phép.
await fetch("https://api.example.com/api/me", {
  credentials: "include"
});
~~~

Với response CORS có credentials, server cần cho phép origin cụ thể:

~~~http
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

**Không dùng** tổ hợp Allow-Origin wildcard và Allow-Credentials true. Trình duyệt sẽ không cho JavaScript đọc phản hồi CORS có credentials với wildcard origin.

Dù đã đặt credentials: include, cookie **SameSite=Strict/Lax** vẫn có thể bị từ chối trong ngữ cảnh cross-site và cookie bên thứ ba có thể bị chặn. CORS cũng không phải điều kiện duy nhất quyết định một cookie có được lưu từ response Set-Cookie hay không.

### 5.3. SameSite theo loại request

Giả sử cookie hợp lệ của **https://bank.example** đã được lưu; trang khác site **https://outside.test** khởi tạo request. Bảng sau mô tả xu hướng khi các điều kiện cookie khác đều thỏa:

| Hành động cross-site | SameSite=Strict | SameSite=Lax | SameSite=None; Secure |
| --- | --- | --- | --- |
| Người dùng bấm liên kết **GET điều hướng top-level** | Thường không gửi | Thường gửi | Có thể gửi |
| Form **POST** từ trang khác site | Không gửi | Thường không gửi với Lax tường minh | Có thể gửi |
| Nhúng **img** từ site đích | Không gửi | Không gửi | Có thể gửi |
| **fetch** cross-site với credentials: include | Không gửi | Không gửi | Có thể gửi |

Với cookie không khai báo SameSite, một số trình duyệt áp dụng mặc định kiểu Lax và có thể có ngoại lệ tương thích cho cookie mới tạo; không dựa vào ngoại lệ này khi thiết kế bảo mật. SameSite=None không vượt qua chính sách chặn cookie bên thứ ba.

Đặc biệt, **ngữ cảnh iframe** có thể liên quan site của trang cấp cao nhất và các ancestor, nên không tính SameSite chỉ bằng hai URL ở trong iframe. Một iframe của app.example.com bị nhúng tại outside.test có thể chịu quy tắc cross-site khi iframe gọi API cùng registrable domain.

### 5.4. Authorization do JavaScript thêm khác với cookie tự gửi

~~~javascript
const accessToken = getTokenFromApplication();

await fetch("https://api.example.com/api/me", {
  headers: {
    Authorization: "Bearer " + accessToken
  }
});
~~~

Hàm **getTokenFromApplication()** là hàm minh họa, không phải API có sẵn. Trình duyệt **không tự lấy Bearer token từ localStorage** rồi gắn vào header Authorization cho mọi request. Ứng dụng phải chủ động thực hiện thao tác này.

Trong khi đó, cookie session có thể được browser tự gửi cho những request phù hợp. Sự khác biệt ảnh hưởng đáng kể đến phân tích **CSRF**. Tuy nhiên, **HTTP authentication** hoặc **TLS client certificate** có thể là credential browser tự sử dụng trong một số bối cảnh; không suy ra hệ thống không dùng cookie thì chắc chắn không tồn tại request mang credential tự động.

## 6. Header Origin và Fetch Metadata: server nhìn thấy gì?

Trình duyệt có thể gửi nhiều header giúp server hiểu ngữ cảnh request. Hai nhóm hữu ích là **Origin** và **Sec-Fetch-***.

### 6.1. Origin cho biết một origin nguồn, nhưng có thể vắng mặt

Ví dụ request cross-origin từ frontend:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Content-Type: application/json
~~~

Header **Origin** thường xuất hiện trong request CORS và nhiều request POST, nhưng **không bắt buộc hiện diện với mọi GET, điều hướng hay loại tài nguyên**. Một số request có thể mang **Origin: null**, chẳng hạn ngữ cảnh có opaque origin.

Server không nên kiểm tra nguồn request bằng phép:

~~~text
Origin chứa chuỗi "example.com" → đáng tin
~~~

Vì **https://example.com.evil.test** cũng chứa chuỗi đó. Khi cần xác định origin được phép, phải đối chiếu **giá trị origin chính xác, đã xác định rõ scheme/host/port**, với chính sách đã thiết kế.

**Origin header không phải chứng minh người gọi đã đăng nhập**. HTTP client ngoài browser có thể tự đặt header Origin. Do đó CORS và Origin validation không thay thế authentication, authorization hay kiểm tra nghiệp vụ.

### 6.2. Sec-Fetch-Site: quan hệ của nguồn với đích

Trình duyệt hiện đại thường gửi header **Sec-Fetch-Site**:

| Giá trị | Diễn giải điển hình |
| --- | --- |
| **same-origin** | Request được khởi tạo trong ngữ cảnh cùng origin với đích. |
| **same-site** | Khác origin nhưng cùng site với đích. |
| **cross-site** | Ngữ cảnh khởi tạo và đích khác site. |
| **none** | Không có site khởi tạo thông thường, ví dụ điều hướng trực tiếp do người dùng. |

Ví dụ request từ trang **https://app.example.com** tới API **https://api.example.com**:

~~~http
GET /api/me HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Sec-Fetch-Site: same-site
Sec-Fetch-Mode: cors
Sec-Fetch-Dest: empty
~~~

Đây là **cross-origin nhưng same-site**, không phải same-origin. **Sec-Fetch-Site** biểu diễn quan hệ của ngữ cảnh request; **Origin** là origin nguồn khi header được gửi. Không phải mọi request đều có cả hai header.

### 6.3. Sec-Fetch-Mode, Sec-Fetch-Dest và Sec-Fetch-User

| Header | Ví dụ giá trị | Ý nghĩa khái quát |
| --- | --- | --- |
| **Sec-Fetch-Mode** | cors, no-cors, navigate, same-origin | Browser đang khởi tạo request theo mode nào. |
| **Sec-Fetch-Dest** | empty, document, image, script, iframe | Loại tài nguyên/đích mà request nhắm tới. |
| **Sec-Fetch-User** | ?1 | Xuất hiện trong một số điều hướng có kích hoạt bởi người dùng; không phải header có ở mọi request. |

So sánh hai ngữ cảnh đến cùng endpoint:

~~~http
GET /dashboard HTTP/1.1
Host: app.example.com
Sec-Fetch-Site: none
Sec-Fetch-Mode: navigate
Sec-Fetch-Dest: document
Sec-Fetch-User: ?1
~~~

~~~http
GET /api/me HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Sec-Fetch-Site: same-site
Sec-Fetch-Mode: cors
Sec-Fetch-Dest: empty
~~~

Các giá trị trên là **ví dụ**, không bảo đảm mọi phiên bản browser luôn gửi toàn bộ header theo cùng cách.

**Sec-Fetch-Site: none không có nghĩa request đáng tin tuyệt đối**: đó là một loại ngữ cảnh khởi tạo, thường liên quan hành vi người dùng như nhập URL hoặc bookmark. Nó không chứng minh user đã đăng nhập hoặc request có quyền thay đổi dữ liệu.

### 6.4. Fetch Metadata là lớp bổ sung chống request ngoài ý muốn

Server có thể dùng Fetch Metadata để triển khai **resource isolation policy**: hạn chế request cross-site không mong muốn đến endpoint nội bộ, đồng thời cho phép các kiểu điều hướng hoặc tài nguyên công khai đã thiết kế.

Một chính sách ở mức khái niệm:

~~~text
Nếu yêu cầu đến endpoint nhạy cảm:
  - Xác thực người dùng và kiểm tra phân quyền theo endpoint.
  - Kiểm tra CSRF token đối với thao tác thay đổi trạng thái dựa trên session.
  - Nếu có Fetch Metadata, có thể từ chối thêm một số request
    cross-site không được hỗ trợ.
  - Nếu thiếu header, dùng chính sách fallback được thiết kế rõ.
  - Cho phép ngoại lệ hợp pháp đối với điều hướng hoặc tích hợp đã duyệt.
~~~

Không nên áp dụng máy móc “chỉ cho phép same-site” vì:

- **Subdomain cùng site có thể không đáng tin**, nên same-site không chứng minh request an toàn.
- Nhiều luồng hợp lệ là **cross-site**, như đăng nhập liên kết, điều hướng từ email hoặc tài nguyên công khai.
- Một số client/trình duyệt thiếu Fetch Metadata; client ngoài browser có thể giả lập header.
- Header này không thay thế **CSRF token, authentication, authorization**.

Với yêu cầu theo chuỗi redirect, ngữ cảnh Fetch Metadata có thể phản ánh các site đã tham gia; khi kiểm tra redirect, cần xem **giá trị header thực tế** thay vì chỉ suy ra từ URL cuối cùng.

## 7. CSRF: nguy cơ từ việc trình duyệt tự gửi cookie

Một website khác có thể thử yêu cầu người dùng đã đăng nhập thực hiện thao tác ngoài ý muốn:

~~~text
Người dùng đăng nhập: https://bank.example
Trang do kẻ tấn công kiểm soát: https://outside.test
API thay đổi trạng thái: https://bank.example/transfer
~~~

Nếu cookie phiên đủ điều kiện gửi và endpoint chỉ dựa vào cookie để chấp nhận thao tác, request có thể gây tác dụng phụ dù outside.test không được CORS cấp quyền đọc phản hồi.

Các lớp phòng vệ có vai trò riêng:

| Cơ chế | Vai trò trong ví dụ |
| --- | --- |
| **SOP** | Giới hạn trang ngoài đọc DOM/response từ bank.example. |
| **CORS** | Ngân hàng quyết định origin nào được JavaScript đọc phản hồi API. |
| **SameSite cookie** | Giảm khả năng cookie gửi trong nhiều request cross-site. |
| **CSRF token** | Server kiểm tra bằng chứng request thay đổi trạng thái có nguồn khởi tạo hợp lệ theo thiết kế ứng dụng. |
| **Authentication/authorization** | Server xác thực phiên và quyền thực hiện thao tác. |
| **Origin/Referer/Fetch Metadata** | Có thể bổ sung các tín hiệu về nguồn/ngữ cảnh request. |

**Một request same-site nhưng cross-origin cũng có thể không đáng tin**. Ví dụ subdomain **https://untrusted.example.com** bị chiếm quyền vẫn thường same-site với **https://api.example.com**. Nếu server chỉ dựa vào SameSite hoặc Sec-Fetch-Site: same-site mà bỏ CSRF, rủi ro còn tồn tại.

Ngược lại, với request đến từ mã chạy cùng origin do **XSS**, SOP cũng không ngăn script độc hại dùng quyền của trang. Cần CSP phù hợp, bảo vệ XSS và phòng vệ đầu vào riêng.

### 7.1. GET phải an toàn về tác dụng phụ

Cookie **SameSite=Lax** thường được gửi khi người dùng điều hướng top-level GET từ website khác. Vì vậy một endpoint thực hiện thao tác nguy hiểm bằng GET có thể bị kích hoạt qua liên kết ngoài.

Hãy dùng GET/HEAD cho thao tác đọc và các HTTP method phù hợp cho thay đổi trạng thái, kết hợp CSRF token khi sử dụng cookie/session. Chỉ đổi POST thành GET để “né CSRF” là lỗi thiết kế.

## 8. Tình huống Spring Security: frontend và API khác origin

Giả sử:

~~~text
Frontend: https://app.example.com
API:      https://api.example.com
Session:  cookie host-only của api.example.com
Phạm vi endpoint: /api/**
~~~

Yêu cầu từ frontend đến API là **cross-origin, same-site**. Chúng ta cần đồng thời:

1. Cho phép đúng origin frontend đọc phản hồi API qua **CORS**.
2. Để browser có thể gửi cookie khi URL, SameSite và fetch credentials phù hợp.
3. Yêu cầu API thực thi **authentication, authorization** và **CSRF protection** cho thao tác thay đổi trạng thái.

### 8.1. Servlet: Spring Security 6.x

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
                // Giữ bảo vệ CSRF mặc định khi dùng cookie/session.
                .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(
                List.of("Content-Type", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

Chính sách CORS này **chỉ áp dụng cho /api/**. Danh sách allowed methods/headers phải phản ánh nhu cầu thực tế; GET/POST ở đây chỉ là ví dụ. CORS phải được xử lý trước các bước có thể từ chối OPTIONS preflight, vì preflight thường không có cookie.

**Không tắt CSRF chỉ để POST hết lỗi 403** khi ứng dụng dùng session cookie. Thay vào đó thiết kế cách frontend nhận token và gửi token hợp lệ.

### 8.2. Reactive: Spring WebFlux

Ở stack Reactive, dùng **ServerHttpSecurity** và CORS classes trong gói **org.springframework.web.cors.reactive**:

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
                // Giữ bảo vệ CSRF mặc định với WebSession/cookie.
                .build();
    }

    @Bean
    CorsConfigurationSource corsConfigurationSource() {
        CorsConfiguration cors = new CorsConfiguration();
        cors.setAllowedOrigins(List.of("https://app.example.com"));
        cors.setAllowedMethods(List.of("GET", "POST"));
        cors.setAllowedHeaders(
                List.of("Content-Type", "X-CSRF-TOKEN"));
        cors.setAllowCredentials(true);

        UrlBasedCorsConfigurationSource source =
                new UrlBasedCorsConfigurationSource();
        source.registerCorsConfiguration("/api/**", cors);
        return source;
    }
}
~~~

**Không trộn** CorsConfigurationSource của Servlet và WebFlux. Hai ví dụ được dùng riêng tùy stack; cơ chế xác định origin/site của browser không đổi theo backend.

Với request POST có CSRF token, Spring Security còn cần cấu hình cách cấp token, cookie/session và các phần liên quan theo ứng dụng thực tế. Các đoạn code trên minh họa xử lý CORS, **không phải một cấu hình xác thực và cấp token hoàn chỉnh**.

### 8.3. Gửi POST qua browser từ SPA

~~~javascript
// Giá trị csrfToken phải được ứng dụng cấp hợp lệ.
const response = await fetch("https://api.example.com/api/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ productId: 42 })
});

if (!response.ok) {
  throw new Error("Request thất bại: HTTP " + response.status);
}
~~~

Trong thực tế, cần một cơ chế cấp và làm mới CSRF token phù hợp. Dù OPTIONS preflight trả thành công, POST vẫn có thể nhận 401/403 nếu session, CSRF token hoặc quyền không hợp lệ.

## 9. Kiểm thử ba loại request trong trình duyệt

Một quy trình kiểm tra đáng tin phải quan sát **cả request lẫn response** trong DevTools, phân biệt trình duyệt có gửi request và JavaScript có đọc được dữ liệu hay không.

### 9.1. Chuẩn bị ba đích thử nghiệm

Ví dụ trên môi trường phát triển được phép:

| Trường hợp | Trang nguồn | API đích | Quan hệ |
| --- | --- | --- | --- |
| A | https://app.example.com | https://app.example.com/api/me | Same-origin |
| B | https://app.example.com | https://api.example.com/api/me | Cross-origin, same-site |
| C | https://app.example.com | https://partner.example.net/api/me | Cross-site |

Có thể sử dụng các host thử nghiệm do bạn kiểm soát; các URL trong bảng là **địa chỉ minh họa**, không phải endpoint được bảo đảm tồn tại.

### 9.2. Kiểm tra fetch GET

Trong Console của trang nguồn:

~~~javascript
async function probe(url) {
  try {
    const response = await fetch(url, { credentials: "include" });
    console.log(url, response.status, await response.text());
  } catch (error) {
    console.error(url, error);
  }
}

await probe("/api/me");
await probe("https://api.example.com/api/me");
await probe("https://partner.example.net/api/me");
~~~

**Không dùng credentials: include tùy tiện với dữ liệu nhạy cảm ở origin ngoài phạm vi tin cậy**. Đây là minh họa phục vụ môi trường kiểm thử; trong ứng dụng thật chỉ gửi credentials tới các endpoint được phép.

Quan sát:

- Header **Sec-Fetch-Site** và **Origin** có hiện diện không?
- Network hiển thị request, response và redirect thế nào?
- Cookie có được gửi theo từng request không?
- Response có CORS header phù hợp để JavaScript đọc không?
- Request bị 401/403 do ứng dụng hay lỗi bị browser chặn trước khi đọc?

### 9.3. Kiểm tra POST có preflight

Trong môi trường thử nghiệm với API và tài khoản bạn được phép sử dụng:

~~~javascript
// Dùng token test hợp lệ nếu muốn kiểm tra luồng thành công.
await fetch("https://api.example.com/api/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": "invalid-token-for-negative-test"
  },
  body: JSON.stringify({ productId: 42 })
});
~~~

Token trên **cố ý không hợp lệ** để quan sát lỗi CSRF khi OPTIONS đã thành công. Chỉ chạy với endpoint thử nghiệm không gây tác dụng phụ ngoài ý muốn. Kiểm tra trong Network: **OPTIONS** được trả lời ra sao, **POST** có được gửi không, và nếu POST bị 403 thì do CSRF hay authorization.

### 9.4. Đọc header preflight bằng curl

~~~bash
curl -i -X OPTIONS "https://api.example.com/api/orders" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-csrf-token"
~~~

Lệnh curl giúp xem phản hồi HTTP và header do server công bố, **không tự thực thi SOP/CORS** như trình duyệt. Trên PowerShell, dùng **curl.exe** để tránh bí danh curl nếu có. Hãy thử thêm một origin không được phép trong môi trường kiểm thử để xác minh server không cấp CORS tùy tiện.

### 9.5. Ma trận chẩn đoán

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| GET same-origin trả 401. | Chưa có session/token hoặc phiên hết hạn. | Kiểm tra cookie/Authorization và cấu hình authentication. |
| Fetch cross-origin báo lỗi CORS dù Network có GET 200. | Response không cấp quyền đọc cho Origin hoặc credentials không phù hợp. | Kiểm tra Allow-Origin, Allow-Credentials, Vary. |
| OPTIONS trả 401/403. | Xử lý CORS sau bộ lọc chặn preflight, hoặc method/header không được phép. | Kiểm tra cấu hình CORS và thứ tự filter. |
| OPTIONS đạt, POST trả 403. | CSRF token không hợp lệ hoặc thiếu quyền. | Kiểm tra log CSRF và authorization, không mở CORS bừa bãi. |
| Cookie không có trong cross-origin fetch same-site. | credentials mặc định same-origin hoặc cookie không khớp. | Kiểm tra credentials: include và Domain/Path/Secure/SameSite. |
| Cross-site fetch không mang cookie dù đã include. | SameSite Strict/Lax hoặc chính sách cookie bên thứ ba. | Kiểm tra request context, cookie attributes và trình duyệt. |
| API chạy trong curl nhưng fetch bị chặn. | curl không áp dụng SOP/CORS như browser. | Dùng Network/Console và CORS header thực tế. |
| Request HTTPS bị lỗi trước CORS khi đi tới HTTP. | Mixed Content, TLS hoặc redirect. | Xem URL, chính sách HTTPS và toàn bộ redirect chain. |
| Ứng dụng đọc được iframe? | Phụ thuộc origin và sandbox; cross-origin bị hạn chế DOM. | Dùng postMessage có kiểm tra origin khi cần giao tiếp. |
| Sec-Fetch-Site là same-site nhưng request không đáng tin. | Nguồn có thể là subdomain bị kiểm soát. | Bảo vệ CSRF, phân quyền và allowlist origin riêng. |

## 10. Bài tập phân loại và xử lý

### Tình huống 1 — Khác đường dẫn

Trang nguồn **https://app.example.com/cart** gọi **https://app.example.com/api/orders**. Đây là same-origin hay cross-origin? Browser có yêu cầu CORS để script đọc JSON không?

**Đáp án:** Same-origin, vì chỉ khác path; không cần CORS chỉ để đọc phản hồi cùng origin. Request vẫn cần quyền và CSRF khi thích hợp.

### Tình huống 2 — Khác cổng

SPA **http://localhost:3000** gọi Spring API **http://localhost:8080**. Hai URL có same-site không, có same-origin không?

**Đáp án:** Với ngữ cảnh HTTP localhost thông thường, chúng **same-site** nhưng **cross-origin** do khác port. Fetch cross-origin muốn đọc JSON cần CORS; credentials mặc định của fetch không tự gửi cookie API.

### Tình huống 3 — Hai subdomain

Frontend **https://app.example.com** gọi **https://api.example.com**. API dùng cookie host-only HttpOnly, SameSite=Strict. Cookie có thể được gửi không?

**Đáp án:** Có thể nếu ngữ cảnh same-site, URL đích khớp cookie và frontend đặt credentials: include. HttpOnly không cản browser gửi cookie, nhưng fetch cross-origin vẫn cần CORS để JavaScript đọc response.

### Tình huống 4 — Đổi HTTPS sang HTTP

Trang **https://app.example.com** yêu cầu **http://app.example.com/api/me**. Hai URL có cùng site theo schemeful same-site không? Yêu cầu có thể gặp loại chặn nào ngoài CORS?

**Đáp án:** Không; khác scheme nên **cross-site** và cross-origin. Trình duyệt còn có thể áp dụng **Mixed Content** hoặc chính sách nâng cấp HTTPS/HSTS; cần kiểm tra URL thực tế.

### Tình huống 5 — Form POST không có JavaScript

Một website khác site gửi form POST đến endpoint thay đổi trạng thái dùng cookie phiên. CORS của server không cho website ngoài. Có thể kết luận request không thể tới server không?

**Đáp án:** Không. Form POST có thể được gửi theo cơ chế biểu mẫu mà không cần preflight CORS như một số fetch JSON. Việc cookie có đi kèm phụ thuộc SameSite và các điều kiện khác; server phải có chống CSRF.

### Tình huống 6 — Sec-Fetch-Site: same-site

Request đến **https://api.example.com** mang **Sec-Fetch-Site: same-site** và **Origin: https://blog.example.com**. Có thể bỏ qua CSRF token không?

**Đáp án:** Không. Blog có thể là subdomain bên thứ ba hoặc bị chiếm quyền. Same-site không chứng minh đây là thao tác hợp lệ, và Origin header không thay thế authentication.

### Tình huống 7 — Preflight qua rồi POST bị 403

POST JSON từ frontend cần X-CSRF-TOKEN. OPTIONS trả 204 với CORS header phù hợp, POST lại trả 403. Đây chắc chắn là lỗi CORS?

**Đáp án:** Không. Có thể token CSRF không hợp lệ, session không đúng hoặc user không đủ quyền. Preflight đạt không xác nhận POST được phép về nghiệp vụ.

### Tình huống 8 — Redirect đổi origin

Frontend gọi **/api/export** cùng origin, server redirect sang **https://files.example.net/export**. DevTools báo lỗi CORS. Nên xem URL nào?

**Đáp án:** Xem toàn bộ redirect chain và origin/headers của response cuối, cùng các điều kiện preflight/redirect. Một URL đầu tiên cùng origin không bảo đảm response cuối vẫn same-origin.

### Tình huống 9 — Thiếu Origin

Một GET điều hướng trực tiếp đến API không mang Origin header. Có nên tự động coi request độc hại hoặc coi request đáng tin vì thiếu Origin?

**Đáp án:** Không kết luận bằng một header duy nhất. Cần phân biệt loại request, phương thức, trạng thái đăng nhập, CSRF và Fetch Metadata/Referer nếu có; chính sách phải xử lý trường hợp header vắng mặt một cách có chủ đích.

### Tình huống 10 — Request từ mã ngoài browser

Một script backend tự gửi **Origin: https://app.example.com** đến API. CORS có thể ngăn script đó đọc dữ liệu không?

**Đáp án:** Không. CORS do trình duyệt thực thi; một HTTP client backend có thể tự đặt Origin và đọc phản hồi HTTP. Server phải xác thực, phân quyền và bảo vệ endpoint độc lập.

## 11. Những nguyên tắc cần nhớ

1. **Origin = scheme + host + port** với URL HTTP/HTTPS thông thường. **Schemeful site = scheme + registrable domain** với host có miền đăng ký; port không làm thay đổi site.
2. **Same-origin**, **cross-origin same-site** và **cross-site** là ba nhóm có ý nghĩa thực tiễn khác nhau. **Same-site không kéo theo same-origin**.
3. **SOP/CORS quyết định quyền JavaScript đọc phản hồi cross-origin**. Browser vẫn có thể gửi một số request cross-origin hoặc cross-site, nên phải phân biệt hành vi mạng với quyền đọc.
4. **Cookie được gửi theo Domain/Path/Secure/SameSite và ngữ cảnh request**, thêm điều kiện credentials khi dùng fetch/XHR; **HttpOnly không cản browser gửi cookie**.
5. **CORS không thay thế CSRF, authentication hoặc authorization.** Một request có cookie hợp lệ vẫn phải được kiểm tra CSRF khi thay đổi trạng thái theo mô hình session.
6. **Origin** và **Fetch Metadata** giúp chẩn đoán/phòng vệ theo ngữ cảnh, nhưng header có thể vắng mặt và không phải bằng chứng danh tính.
7. Khi cấu hình **Spring Security Servlet/WebFlux**, cho preflight được xử lý đúng, giới hạn origin CORS thực sự được phép và giữ các lớp phòng vệ session/CSRF phù hợp.
