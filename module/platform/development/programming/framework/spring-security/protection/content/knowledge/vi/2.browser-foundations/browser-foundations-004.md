# Cách trình duyệt gửi cookie và thông tin xác thực tự động

## Mục tiêu bài học

Trong một ứng dụng web, người dùng có thể đã đăng nhập mà không cần tự nhập mã phiên cho từng yêu cầu. Trình duyệt thường lưu cookie rồi **tự quyết định có gửi cookie theo HTTP request tiếp theo hay không**. Cơ chế này giúp duy trì session, nhưng cũng tạo tiền đề cho **Cross-Site Request Forgery (CSRF)** nếu server tin mọi request có cookie là hành động có chủ ý của người dùng.

Bài học thuộc chương **Nền tảng trình duyệt** của module **SPRING_SECURITY_HTTP_PROTECTION**: vận dụng các lớp bảo vệ HTTP và trình duyệt trong Spring Security, bao gồm CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và bảo vệ session trên **Servlet** lẫn **Reactive (WebFlux)**.

Sau bài học, bạn có thể:

1. Mô tả vòng đời **Set-Cookie → lưu cookie → chọn cookie phù hợp → gửi Cookie header → server kiểm tra session**.
2. Phân tích chính xác tác động của **Domain, Path, Secure, HttpOnly, SameSite, Expires/Max-Age**, tiền tố cookie và cookie phân vùng.
3. Phân biệt **same-origin** với **same-site**, đồng thời hiểu trường hợp request khác origin vẫn có cookie.
4. Giải thích sự khác nhau giữa cookie tự gửi, **HTTP authentication**, **client certificate** và **Bearer token được mã JavaScript chủ động thêm**.
5. Sử dụng **fetch credentials** và **XMLHttpRequest.withCredentials** đúng cách; phân biệt điều kiện **gửi cookie** với điều kiện **đọc phản hồi CORS**.
6. Lý giải vì sao cookie phiên tự động tạo rủi ro CSRF, thực hành kiểm tra với DevTools và cấu hình mẫu Spring Security Servlet/WebFlux.

## 1. Vì sao nói trình duyệt gửi thông tin xác thực “tự động”?

Giả sử người dùng đăng nhập thành công tại **https://app.example.com**. Server xác thực tài khoản rồi tạo một session ở phía server, trả về một cookie chứa mã phiên:

~~~http
HTTP/1.1 200 OK
Set-Cookie: __Host-session=abc123opaque; Path=/; Secure; HttpOnly; SameSite=Lax
Content-Type: text/html
~~~

Trình duyệt xử lý header **Set-Cookie** và lưu cookie nếu đáp ứng chính sách cookie hiện hành. Lần sau người dùng truy cập một URL phù hợp, trình duyệt có thể tự gắn **Cookie** vào yêu cầu:

~~~http
GET /account HTTP/1.1
Host: app.example.com
Cookie: __Host-session=abc123opaque
~~~

Server đọc mã phiên, tìm trạng thái session rồi quyết định người dùng có được truy cập hay không. Người dùng không cần viết **Cookie: ...** vào request hay nhập lại mật khẩu cho mỗi lần chuyển trang.

~~~mermaid
sequenceDiagram
    participant U as Người dùng
    participant B as Trình duyệt
    participant S as Spring Security / Server
    U->>B: Đăng nhập
    B->>S: POST /login với thông tin đăng nhập
    S->>S: Xác thực và tạo session
    S-->>B: Set-Cookie: __Host-session=...; Secure; HttpOnly; SameSite=Lax
    B->>B: Lưu cookie theo chính sách
    U->>B: Mở /account
    B->>B: Chọn cookie phù hợp với request
    B->>S: GET /account và Cookie: __Host-session=...
    S->>S: Kiểm tra phiên và quyền
    S-->>B: Nội dung tài khoản hoặc 401/403
~~~

**Điểm quan trọng:** Cookie được gửi theo **quy tắc của trình duyệt** và **ngữ cảnh request**. Server không nên suy ra rằng “có cookie hợp lệ” đồng nghĩa request được tạo ra bởi thao tác mà người dùng thực sự mong muốn.

### 1.1. Set-Cookie và Cookie không giống nhau

| Header | Ai thường tạo? | Hướng truyền | Mục đích |
| --- | --- | --- | --- |
| **Set-Cookie** | Server | Response về trình duyệt | Yêu cầu trình duyệt lưu, cập nhật hoặc xóa cookie. |
| **Cookie** | Trình duyệt | Request đến server | Gửi tên và giá trị các cookie phù hợp với request. |

Khi gửi **Cookie**, trình duyệt chỉ gửi các cặp **tên=giá trị**; nó không gửi lại các thuộc tính như HttpOnly, SameSite, Secure hoặc Path dưới dạng một phần của Cookie header.

Ví dụ:

~~~http
Set-Cookie: theme=dark; Path=/; Secure; SameSite=Lax
Set-Cookie: __Host-session=xyz; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Request về sau có thể chứa:

~~~http
Cookie: theme=dark; __Host-session=xyz
~~~

Giá trị trong cookie chỉ là dữ liệu client gửi. Server phải kiểm tra tính hợp lệ của mã phiên/chữ ký và quyền; **không tin một cookie chỉ vì nó xuất hiện trong header**.

## 2. Trình duyệt quyết định có gửi cookie theo những điều kiện nào?

Việc browser lưu cookie **không** có nghĩa cookie đó sẽ xuất hiện trong mọi request. Trước khi gửi, trình duyệt xét các điều kiện tương ứng với cookie, URL đích và ngữ cảnh request.

| Thuộc tính / quy tắc | Vai trò khi gửi cookie | Ví dụ |
| --- | --- | --- |
| **Domain / host-only** | Xác định host nào có thể nhận cookie. | Cookie host-only của api.example.com không gửi cho app.example.com. |
| **Path** | Giới hạn đường dẫn URL đủ điều kiện nhận cookie. | Path=/admin thường không khớp /api/orders. |
| **Secure** | Chỉ gửi trên kết nối được coi là an toàn theo quy tắc trình duyệt, chủ yếu HTTPS. | Cookie Secure không được gửi qua HTTP thông thường. |
| **SameSite** | Giới hạn cookie trong những ngữ cảnh cross-site cụ thể. | Lax có thể cho phép điều hướng GET cấp cao nhất từ site khác. |
| **Expires / Max-Age** | Kiểm soát thời điểm hết hạn cookie. | Cookie đã hết hạn không được gửi. |
| **Partitioned / chính sách bên thứ ba** | Có thể giới hạn cookie theo top-level site hoặc chặn cookie bên thứ ba. | Widget nhúng có thể cần cookie phân vùng. |
| **Fetch credentials mode** | Ảnh hưởng việc gửi credentials của các yêu cầu thực hiện bằng fetch. | Fetch cross-origin mặc định không gửi cookie. |

**HttpOnly không nằm trong bảng điều kiện ngăn gửi**: thuộc tính này chủ yếu ngăn mã JavaScript đọc cookie qua **document.cookie**, nhưng browser vẫn có thể gửi cookie HttpOnly khi request phù hợp. Điều này quan trọng đối với cả bảo vệ phiên lẫn CSRF.

### 2.1. Domain và host-only: cookie thuộc về host nào?

Nếu response của **https://api.example.com** gửi:

~~~http
Set-Cookie: session=xyz; Path=/; Secure; HttpOnly
~~~

và **không có Domain**, cookie thường là **host-only**: chỉ những request đến đúng host **api.example.com** mới đủ điều kiện nhận cookie này. Mã frontend tại app.example.com vẫn có thể khiến trình duyệt gửi request đến api.example.com, nhưng **không** vì vậy được trực tiếp đọc một cookie HttpOnly của API.

Nếu server gửi:

~~~http
Set-Cookie: preference=dark; Domain=example.com; Path=/; Secure
~~~

cookie có thể đủ điều kiện gửi cho **example.com**, **app.example.com**, **api.example.com** và các subdomain phù hợp khác. Dấu chấm đứng trước Domain trong cú pháp cookie cũ không còn là điều kiện bắt buộc để áp dụng cho subdomain.

Cần chú ý:

- Một response không thể tùy ý đặt cookie cho một domain hoàn toàn không liên quan; browser kiểm tra mối quan hệ giữa host response và Domain.
- Domain trỏ tới một **public suffix** (như com hoặc co.uk trong trường hợp thông thường) sẽ bị trình duyệt từ chối theo quy tắc cookie, nhằm tránh chia sẻ cookie cho mọi website.
- **Cookie không được cô lập bằng port**. Một cookie dành cho host localhost có thể đủ điều kiện gửi đến cả **http://localhost:3000** và **http://localhost:8080** nếu các điều kiện khác phù hợp. Tuy nhiên hai URL này vẫn **cross-origin** vì port khác nhau.
- Domain rộng hơn mức cần thiết tạo thêm bề mặt tấn công từ subdomain bị xâm nhập hoặc không được quản lý.

Đối với cookie session nhạy cảm, ưu tiên **host-only** khi kiến trúc cho phép.

### 2.2. Path giới hạn URL, không phải ranh giới phân quyền

Ví dụ:

~~~http
Set-Cookie: adminPref=compact; Path=/admin; Secure
~~~

Cookie có thể được gửi với request tới **/admin** và những đường dẫn khớp theo quy tắc Path của cookie, như **/admin/settings**; không tự áp dụng cho **/api/orders**.

Nhưng **Path không phải cơ chế cách ly bảo mật đáng tin cậy giữa các ứng dụng cùng host**. Đừng dùng Path để thay thế xác thực hoặc phân quyền; mã chạy trên cùng origin và các cơ chế URL/cookie liên quan có thể khiến cách ly dựa vào Path yếu hơn kỳ vọng.

### 2.3. Secure bảo vệ đường truyền của cookie

~~~http
Set-Cookie: __Host-session=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

**Secure** khiến cookie chỉ được gửi trên kênh được trình duyệt xem là an toàn theo quy tắc cookie, chủ yếu HTTPS. Một số trình duyệt có ngoại lệ phát triển cho localhost; không dựa vào ngoại lệ đó để thiết kế môi trường production.

Secure **không mã hóa giá trị cookie ở phía client**, **không bảo đảm session không bị đánh cắp** và không thay thế TLS, xác thực hay bảo vệ trước XSS. Nó ngăn cookie đi qua HTTP không an toàn trong những điều kiện thông thường.

Trong Spring Boot triển khai sau reverse proxy, cần bảo đảm URL HTTPS và cấu hình proxy tin cậy phản ánh đúng kết nối bên ngoài, tránh tình trạng ứng dụng tạo cookie sai thuộc tính. Chỉ tin header **Forwarded/X-Forwarded-*** từ proxy thực sự đáng tin cậy.

### 2.4. HttpOnly: mã JavaScript không đọc được nhưng browser vẫn gửi

Với cookie:

~~~http
Set-Cookie: session=xyz; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

JavaScript thông thường không lấy được giá trị session bằng:

~~~javascript
console.log(document.cookie);
// Không hiển thị giá trị cookie HttpOnly.
~~~

Tuy nhiên, nếu URL và ngữ cảnh request phù hợp, browser **vẫn tự thêm Cookie: session=xyz**. Vì vậy:

- HttpOnly giúp giảm nguy cơ script đánh cắp trực tiếp mã phiên qua document.cookie.
- HttpOnly không ngăn script đang chạy trong trang hợp lệ gọi API bằng session hiện có.
- HttpOnly **không chặn CSRF**; kẻ tấn công có thể cố kích hoạt một request mang cookie mà không cần biết giá trị cookie.

Có thể đặt cookie không-HttpOnly để phục vụ một số cơ chế trao đổi dữ liệu giữa JavaScript và server, nhưng **cookie session nhạy cảm thường nên có HttpOnly**.

### 2.5. Expires, Max-Age và tuổi thọ session

~~~http
Set-Cookie: reminder=on; Path=/; Max-Age=3600; Secure; SameSite=Lax
~~~

**Max-Age=3600** yêu cầu cookie tồn tại tối đa khoảng 3600 giây kể từ thời điểm tính theo quy tắc cookie. **Expires** chỉ thời điểm hết hạn tuyệt đối. Nếu cả hai được cung cấp, **Max-Age có ưu tiên** khi trình duyệt hỗ trợ đúng chuẩn.

Cookie không có Expires hoặc Max-Age thường là **session cookie của trình duyệt**, nhưng trình duyệt có thể khôi phục session giữa các lần mở lại; không nên xem “đóng cửa sổ” là bằng chứng chắc chắn cookie đã bị xóa.

**Tuổi thọ cookie và tuổi thọ session phía server là hai khái niệm khác nhau.** Cookie còn trên trình duyệt không có nghĩa session id còn hiệu lực tại server. Đăng xuất an toàn cần làm mất hiệu lực session/token tại server theo cơ chế ứng dụng; chỉ xóa cookie phía browser là chưa đủ trong mọi mô hình.

Để yêu cầu xóa cookie, server thường gửi giá trị hết hạn như:

~~~http
Set-Cookie: session=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax
~~~

Khi xóa, các thuộc tính định danh phạm vi cookie như **Domain** (nếu có) và **Path** cần khớp với cookie đã tạo để xóa đúng bản ghi. Đừng kỳ vọng một Set-Cookie với Path khác tự động xóa mọi cookie cùng tên.

## 3. SameSite: kiểm tra ngữ cảnh request thuộc site nào

**SameSite** điều chỉnh việc trình duyệt gửi cookie trong các ngữ cảnh **same-site** hoặc **cross-site**, bổ sung cho Domain/Path/Secure.

Với HTTP/HTTPS thông thường, cách xét **schemeful site** dựa trên **scheme + registrable domain** (miền có thể đăng ký dựa trên Public Suffix List), không dùng port.

~~~text
https://app.example.com  và https://api.example.com
=> Same-site, cross-origin (khác host).

http://app.example.com   và https://app.example.com
=> Cross-site theo schemeful same-site; cross-origin.

http://localhost:3000    và http://localhost:8080
=> Same-site theo host localhost và scheme http; cross-origin vì port khác.
~~~

Bởi vậy, **SameSite cookie không đồng nghĩa CORS hay Same-Origin Policy (SOP)**. SOP/CORS sử dụng origin; SameSite sử dụng site và ngữ cảnh request.

### 3.1. Strict, Lax và None

| Thuộc tính | Hành vi gửi cookie điển hình | Điều cần lưu ý |
| --- | --- | --- |
| **SameSite=Strict** | Chỉ gửi trong các ngữ cảnh same-site phù hợp. | Có thể không gửi cookie khi người dùng điều hướng đến website từ liên kết cross-site. |
| **SameSite=Lax** | Gửi trong ngữ cảnh same-site; có thể gửi khi điều hướng **cấp cao nhất** cross-site bằng phương thức an toàn như GET. | Không phải mọi request GET cross-site đều được gửi cookie; ảnh, iframe và fetch có quy tắc khác. |
| **SameSite=None** | Bản thân SameSite không cấm gửi trong ngữ cảnh cross-site. | Trong trình duyệt hiện đại phải đi cùng **Secure**; vẫn có thể bị chặn bởi chính sách cookie bên thứ ba. |

Ví dụ:

~~~http
Set-Cookie: session=xyz; Secure; HttpOnly; Path=/; SameSite=Strict
Set-Cookie: session=xyz; Secure; HttpOnly; Path=/; SameSite=Lax
Set-Cookie: session=xyz; Secure; HttpOnly; Path=/; SameSite=None
~~~

Ba dòng trên minh họa **ba lựa chọn thay thế**, không phải hướng dẫn thiết lập cùng một tên cookie ba lần.

Trong nhiều trình duyệt hiện đại, cookie không khai báo SameSite được xử lý theo mặc định tương tự **Lax**. Có thể tồn tại ngoại lệ tương thích ngắn hạn cho một số cookie mới tạo và phương thức POST; **không phụ thuộc vào hành vi mặc định này để bảo vệ endpoint**. Nên đặt SameSite tường minh và kiểm thử trình duyệt mục tiêu.

### 3.2. Ma trận request cross-site

Giả sử người dùng đã có cookie session của **https://bank.example**, và một trang ở **https://outside.test** khởi tạo hoạt động sau. Cookie không hết hạn, khớp Domain/Path, có Secure và các điều kiện khác đều thỏa. Bảng tập trung **riêng vào tác động của SameSite**, chưa xét các hạn chế cookie bên thứ ba khác.

| Hành động từ outside.test đến bank.example | Strict | Lax | None; Secure |
| --- | --- | --- | --- |
| Người dùng bấm liên kết điều hướng **tab chính** bằng GET. | Thường **không gửi** | Thường **gửi** | Có thể gửi |
| Trang ngoài gửi **form POST** cross-site. | Không gửi | Không gửi với SameSite=Lax tường minh trong trường hợp thông thường | Có thể gửi |
| Trang ngoài nhúng **img** từ bank.example. | Không gửi | Không gửi | Có thể gửi |
| JavaScript thực hiện **fetch cross-site** tới bank.example với credentials: include. | Không gửi | Không gửi | Có thể gửi |
| Một trang same-site hợp lệ gọi API same-site. | Có thể gửi | Có thể gửi | Có thể gửi |

Với fetch cross-site, việc đặt **credentials: include** chỉ đề nghị trình duyệt đưa credentials vào request nếu các quy tắc khác cho phép. Nó **không vượt qua SameSite**.

Trong ngữ cảnh iframe, việc xác định “site của request” còn phụ thuộc **site của trang cấp cao nhất và chuỗi ancestor**. Một iframe được nhúng trong website khác có thể bị xem là ở ngữ cảnh cross-site ngay cả khi URL bên trong iframe và URL API cùng registrable domain.

### 3.3. Hạn chế của SameSite trong chống CSRF

Một ứng dụng có ba host:

~~~text
https://app.example.com        Frontend chính
https://api.example.com        API có cookie phiên
https://untrusted.example.com  Subdomain có mã bên thứ ba
~~~

Cả ba thường thuộc site **https://example.com**. Script trên untrusted.example.com có thể tạo request tới api.example.com trong ngữ cảnh **same-site**, dù hai host **cross-origin**.

Nếu server chỉ dựa vào SameSite=Strict/Lax để chống CSRF, request từ subdomain không đáng tin cậy có thể vẫn mang cookie phiên theo chính sách. **SameSite không thay thế CSRF token, authentication hoặc authorization**.

Ngược lại, không vì SameSite=Lax có thể gửi cookie khi điều hướng GET cross-site mà mặc định coi GET an toàn cho tác vụ thay đổi trạng thái. HTTP GET/HEAD phải được thiết kế là phương thức đọc, không thực hiện chuyển tiền, đổi mật khẩu hay xóa dữ liệu.

## 4. Fetch credentials: khác origin có thể được gửi cookie hay không?

**Fetch API** cho phép frontend quy định chính sách credentials của request thông qua tùy chọn **credentials**. Đây là một lớp điều kiện bổ sung cho các quy tắc cookie ở trên.

| credentials | Hành vi chung |
| --- | --- |
| **same-origin** (mặc định) | Bao gồm credentials cho request **same-origin**; không tự bao gồm credentials của request **cross-origin**. |
| **include** | Cho phép bao gồm credentials cả khi request **cross-origin**, tùy chính sách cookie, HTTP authentication và trình duyệt. |
| **omit** | Không gửi credentials của fetch request; không xử lý Set-Cookie theo chế độ credentials thông thường của fetch response. |

“Credentials” ở đây có thể bao gồm **cookie, thông tin HTTP authentication và TLS client certificate**, tùy cơ chế và nền tảng. Không nên suy ra credentials chỉ là cookie.

### 4.1. Same-origin fetch: mặc định thường đủ

Một trang tại **https://app.example.com** gọi API cùng origin:

~~~javascript
const response = await fetch("/api/me");
// credentials mặc định = "same-origin".
~~~

Nếu có cookie hợp lệ dành cho app.example.com, browser có thể tự gửi nó. Không cần đặt **credentials: include** chỉ để gọi API same-origin, trừ khi muốn ghi tường minh lựa chọn.

Nếu muốn tránh dùng credentials trong một request fetch:

~~~javascript
const response = await fetch("/api/public-info", {
  credentials: "omit"
});
~~~

Điều này có ích trong một số yêu cầu công khai, nhưng server vẫn phải xác thực và phân quyền đúng với endpoint cần bảo vệ.

### 4.2. Cross-origin nhưng same-site: mặc định fetch vẫn không gửi cookie

Trang frontend:

~~~text
https://app.example.com
~~~

API:

~~~text
https://api.example.com
~~~

Hai host thường **same-site nhưng cross-origin**. Nếu API thiết lập cookie **host-only** dành cho api.example.com, cookie này có thể phù hợp với URL API và ngữ cảnh SameSite. Nhưng request sau dùng credentials mặc định:

~~~javascript
await fetch("https://api.example.com/api/me");
~~~

Fetch **không tự đưa cookie của API vào request cross-origin** theo credentials mặc định.

Để yêu cầu gửi cookie khi chính sách cookie cho phép:

~~~javascript
const response = await fetch("https://api.example.com/api/me", {
  credentials: "include"
});
~~~

Sau đó, JavaScript **chỉ đọc được phản hồi** nếu CORS được server cấu hình phù hợp.

### 4.3. Gửi được cookie khác với đọc được response

Xét request frontend **https://app.example.com** đến API **https://api.example.com**:

~~~http
GET /api/me HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Cookie: __Host-session=abc123opaque
~~~

Để JavaScript đọc được phản hồi cross-origin có credentials, API thường phải trả:

~~~http
HTTP/1.1 200 OK
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
Content-Type: application/json

{"name":"An"}
~~~

Nếu thiếu CORS header phù hợp, request **vẫn có thể đã gửi Cookie và đến server**, nhưng trình duyệt không cho script đọc body của phản hồi. Với request cần **preflight**, nếu preflight bị từ chối, request thực tế có thể chưa được gửi.

Không sử dụng tổ hợp sau cho response muốn đọc với credentials:

~~~http
Access-Control-Allow-Origin: *
Access-Control-Allow-Credentials: true
~~~

Trình duyệt không chấp nhận wildcard Allow-Origin cho request CORS có credentials. Cũng không phản chiếu tùy ý mọi Origin rồi trả Allow-Credentials: true; chính sách đó có thể cho trang không đáng tin cậy quyền đọc dữ liệu đã xác thực khi cookie được gửi.

**Lưu ý:** CORS là chính sách trình duyệt cho việc đọc phản hồi, **không phải cơ chế xác thực người dùng**.

### 4.4. XMLHttpRequest và các cách tạo request khác

Với API XMLHttpRequest, một request cross-origin cần credentials có thể đặt:

~~~javascript
const xhr = new XMLHttpRequest();
xhr.open("GET", "https://api.example.com/api/me");
xhr.withCredentials = true;

xhr.onload = () => {
  console.log(xhr.status, xhr.responseText);
};

xhr.send();
~~~

Giống fetch, điều kiện cookie và CORS vẫn áp dụng. Đối với XHR cross-origin, nên đặt withCredentials trước khi gọi send.

Các cơ chế khác như **điều hướng, gửi form HTML, tải ảnh hoặc iframe** không được điều khiển trực tiếp bằng giá trị mặc định credentials: "same-origin" của một lời gọi fetch. Chúng có những quy tắc gửi cookie riêng, vẫn chịu SameSite, Secure, Domain/Path và chính sách trình duyệt. Vì thế:

> Không thể kết luận “trình duyệt không bao giờ gửi cookie cross-origin” chỉ vì fetch mặc định là same-origin.

### 4.5. JavaScript không được tự ý đặt Cookie header

Ví dụ sau **không phải phương pháp hợp lệ** để vượt chính sách cookie:

~~~javascript
await fetch("/api/me", {
  headers: {
    Cookie: "session=fake-value"
  }
});
~~~

**Cookie** là tên request header bị giới hạn đối với JavaScript trong Fetch API; trình duyệt quản lý việc đưa Cookie vào yêu cầu. Khi cần xác thực bằng cookie, ứng dụng phải dựa vào Set-Cookie và browser credentials/cookie policy thay vì cố gán Cookie header.

Tương tự, **Set-Cookie** là response header không được phơi bày cho JavaScript qua **response.headers.get("set-cookie")** trong trình duyệt. Trình duyệt có thể xử lý Set-Cookie để lưu cookie trong khi mã frontend không được đọc trực tiếp header đó.

## 5. Thông tin xác thực nào thực sự được gửi tự động?

**Cookie chỉ là một loại credential.** Các ứng dụng web có thể sử dụng nhiều cơ chế xác thực khác nhau, với mức độ tự động khác nhau.

| Cơ chế | Nơi quản lý chính | Có thể tự gửi theo request? | Điều cần hiểu |
| --- | --- | --- | --- |
| **Session cookie** | Cookie jar của trình duyệt | **Có**, khi mọi điều kiện cookie/request phù hợp. | Có thể tạo nguy cơ CSRF khi server chỉ tin cookie. |
| **HTTP Basic/Digest/Negotiate authentication** | Browser hoặc lớp xác thực HTTP, sau challenge/cấu hình | **Có thể**, khi thông tin xác thực đã được browser lưu/cache hoặc xác thực môi trường hỗ trợ. | Hành vi tùy cơ chế và trình duyệt; không có quy tắc SameSite cookie áp dụng trực tiếp. |
| **TLS client certificate (mTLS)** | TLS stack / certificate store | **Có thể**, nếu hệ thống và người dùng đã cấu hình/chọn chứng chỉ phù hợp. | Bị chi phối bởi quá trình bắt tay TLS, không phải Cookie header. |
| **Bearer token trong Authorization do JavaScript gắn** | Mã ứng dụng hoặc nơi ứng dụng cất giữ token | **Không tự gửi chỉ vì token tồn tại trong localStorage hoặc biến JavaScript.** | Mã frontend phải chủ động đính kèm Authorization cho các request cần thiết. |

### 5.1. HTTP authentication

Server có thể yêu cầu xác thực HTTP bằng phản hồi:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="Members"
~~~

Sau khi trình duyệt có thông tin đăng nhập phù hợp, request về sau có thể mang:

~~~http
Authorization: Basic <base64-credentials>
~~~

Chuỗi Basic là mã hóa Base64, **không phải mã hóa bảo mật**; phải bảo vệ bằng HTTPS và tránh triển khai thiếu kiểm soát.

Trình duyệt có thể tự tái sử dụng credential theo cơ chế HTTP authentication, tùy phạm vi bảo vệ và chính sách. **Không nên coi HTTP authentication là không liên quan đến CSRF chỉ vì ứng dụng không dùng cookie**: một số dạng credential do browser tự gửi vẫn có thể được lợi dụng trong request ngoài ý muốn.

Các cơ chế như **Negotiate/Kerberos** còn phụ thuộc thiết lập doanh nghiệp, hệ điều hành, browser và origin được cho phép. Không suy ra browser nào cũng tự đăng nhập mọi website.

### 5.2. Bearer token không phải cookie tự gửi

Một SPA nhận access token và giữ trong bộ nhớ:

~~~javascript
const accessToken = obtainAccessTokenFromApplication();

await fetch("https://api.example.com/api/me", {
  headers: {
    Authorization: "Bearer " + accessToken
  }
});
~~~

**obtainAccessTokenFromApplication()** là hàm minh họa, không phải API tích hợp sẵn của trình duyệt.

Khác với cookie session, browser **không tự lấy access token từ localStorage và thêm Bearer Authorization** cho mọi request. Mã ứng dụng hoặc thư viện HTTP phải làm điều đó.

Phân biệt này quan trọng khi đánh giá CSRF:

- Với session cookie được gửi tự động, trang ngoài có thể cố kích hoạt request mang cookie mà không biết giá trị cookie.
- Với một Bearer token chỉ nằm trong bộ nhớ ứng dụng và được mã hợp lệ chủ động thêm vào Authorization, trang ngoài thường không có token để tự tạo request có Authorization tương ứng.
- Nhưng hệ thống dùng Bearer vẫn phải chống **XSS, lộ token, cấp quyền sai và các dạng tấn công khác**. Nếu token được lưu trong cookie rồi tự gửi, nguy cơ CSRF quay trở lại theo mô hình cookie.
- Không sử dụng “Bearer token” như bằng chứng chắc chắn hệ thống miễn nhiễm CSRF; hãy kiểm tra **credential thực tế được gắn vào request như thế nào**.

Header Authorization do frontend chủ động thêm thường khiến request CORS cần preflight vì không thuộc danh sách header được safelist. CORS trên server cần cho phép **Authorization** khi giao diện cross-origin thực sự gửi header này.

### 5.3. Đừng nhầm thông tin xác thực với quyền truy cập

Có cookie phiên hợp lệ hoặc một Authorization header hợp lệ nghĩa là server có dữ liệu để **xác thực danh tính**, nhưng request vẫn cần **phân quyền** và kiểm tra điều kiện nghiệp vụ. Một người dùng đã đăng nhập không mặc nhiên có quyền sửa dữ liệu của người khác.

Các lớp HTTP firewall và security headers cũng không thay thế phân quyền. Spring Security phải kiểm soát các endpoint và thao tác nghiệp vụ theo chính sách cụ thể.

## 6. CSRF: hệ quả bảo mật của credential tự gửi

**Cross-Site Request Forgery (CSRF)** xảy ra khi bên tấn công lợi dụng trình duyệt của một người dùng đã đăng nhập để kích hoạt request ngoài ý muốn đến ứng dụng đích, thường dùng **credential được tự động đính kèm** như session cookie.

Một ví dụ đơn giản:

1. Người dùng đăng nhập tại **https://bank.example**, trình duyệt giữ cookie session hợp lệ.
2. Người dùng mở trang **https://outside.test** do kẻ tấn công kiểm soát.
3. Trang ngoài cố tạo một form POST tới **https://bank.example/transfer**.
4. Nếu các quy tắc cookie cho phép, trình duyệt có thể đính kèm cookie session.
5. Nếu server chấp nhận thao tác dựa trên cookie mà không xác minh bằng chứng chống CSRF thích hợp, tác dụng phụ không mong muốn có thể xảy ra.

~~~html
<form action="https://bank.example/transfer" method="POST">
  <input type="hidden" name="to" value="unwanted-recipient">
  <input type="hidden" name="amount" value="100">
  <button type="submit">Continue</button>
</form>
~~~

Đây là mô phỏng cơ chế để hiểu phòng vệ, không dùng đối với hệ thống ngoài phạm vi kiểm thử.

**Same-Origin Policy** và **CORS** thường hạn chế website bên ngoài đọc phản hồi, nhưng **không bảo đảm form hoặc request chưa đến server**. Một form POST với Content-Type được hỗ trợ có thể được gửi mà không cần CORS preflight như fetch JSON có custom header. Chính vì thế, “CORS không cho phép outside.test” không phải bằng chứng endpoint đã được bảo vệ trước CSRF.

### 6.1. Các lớp phòng vệ cần phối hợp

| Lớp phòng vệ | Vai trò | Giới hạn |
| --- | --- | --- |
| **CSRF token** | Liên kết request thay đổi trạng thái với bằng chứng do ứng dụng cấp và kiểm tra. | Cần thiết kế cách cấp/gửi/token validation đúng; không tự ngăn XSS cùng origin. |
| **SameSite cookie** | Giảm khả năng cookie được gửi trong nhiều ngữ cảnh cross-site. | Không loại trừ request same-site từ subdomain không đáng tin. |
| **Secure, HttpOnly, phạm vi cookie hẹp** | Giảm rủi ro cookie đi qua HTTP, bị đọc trực tiếp bằng JS hoặc rò qua subdomain. | Không tự xác minh ý định của người dùng. |
| **Origin/Referer validation** | Hỗ trợ xác định nguồn của request trong những ngữ cảnh phù hợp. | Header có thể thiếu trong một số trường hợp; không thay thế xác thực. |
| **Fetch Metadata (Sec-Fetch-Site)** | Hỗ trợ nhận diện request cùng origin, cùng site hay khác site. | Không phải bằng chứng danh tính; same-site vẫn có thể không đáng tin. |
| **Authentication và authorization** | Kiểm tra danh tính và quyền của request. | Cookie hợp lệ không chứng minh thao tác được chủ ý khởi tạo. |

Đối với Spring Security dùng cookie/session, **CSRF protection nên được giữ và tích hợp với frontend** cho các thao tác thay đổi trạng thái. Một endpoint đổi trạng thái bằng GET là lỗi thiết kế đáng chú ý, vì ngay cả cookie SameSite=Lax cũng có thể được gửi trong điều hướng GET cross-site cấp cao nhất.

### 6.2. CSRF token khác cookie phiên

Session cookie giúp server xác định phiên nào đang gửi request. CSRF token là **bằng chứng bổ sung**, được tạo và kiểm tra theo cơ chế bảo vệ chống CSRF, thường gắn với session hoặc quy trình token riêng.

Một frontend hợp lệ có thể gửi request:

~~~http
POST /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Cookie: __Host-session=abc123opaque
Content-Type: application/json
X-CSRF-TOKEN: valid-token-from-application

{"productId":42}
~~~

Header **X-CSRF-TOKEN** chỉ minh họa cách chuyển token. Token phải được ứng dụng cấp và kiểm tra thật; frontend không được tự bịa ra một chuỗi cố định. Một số kiến trúc dùng token trong form, cookie riêng hoặc header khác theo cách Spring Security được cấu hình.

**HttpOnly của session cookie không mâu thuẫn với việc JavaScript cần nhận CSRF token**. Có thể cấp token qua HTML render hoặc endpoint JSON chuyên biệt; không nhất thiết cho JavaScript đọc chính session cookie.

## 7. Prefix cookie và cookie phân vùng

### 7.1. Tiền tố __Secure- và __Host-

Các trình duyệt hỗ trợ những tiền tố cookie nhằm áp dụng thêm điều kiện khi chấp nhận cookie.

~~~http
Set-Cookie: __Secure-pref=dark; Secure; Path=/; SameSite=Lax
Set-Cookie: __Host-session=opaque; Secure; HttpOnly; Path=/; SameSite=Lax
~~~

Thông thường:

- Cookie có tiền tố **__Secure-** phải được đặt từ nguồn an toàn và có **Secure**.
- Cookie có tiền tố **__Host-** phải có **Secure**, **Path=/** và **không có Domain**, cùng điều kiện chấp nhận từ nguồn an toàn.

**__Host-** hữu ích với cookie session vì ngăn việc cố ý khai báo Domain để mở rộng cookie sang nhiều subdomain, đồng thời gắn cookie với host và toàn bộ đường dẫn. Nó giúp giảm một số rủi ro cookie bị subdomain khác tác động, nhưng **không thay thế CSRF, XSS protection hoặc xác thực**.

Khi dùng tên cookie có tiền tố, phải bảo đảm cấu hình ứng dụng và proxy thực sự tạo ra các thuộc tính bắt buộc; nếu sai, browser có thể **từ chối lưu cookie**.

### 7.2. Cookie Partitioned (CHIPS)

Trong một số ngữ cảnh nhúng bên thứ ba, trình duyệt hiện đại có thể hỗ trợ **partitioned cookies** (CHIPS): cookie được phân vùng theo **top-level site** thay vì chia sẻ một trạng thái bên thứ ba chung giữa mọi site nhúng.

Ví dụ cookie phục vụ một widget được nhúng:

~~~http
Set-Cookie: __Host-widget=opaque; Secure; HttpOnly; Path=/; SameSite=None; Partitioned
~~~

Cookie Partitioned cần tuân thủ các điều kiện hỗ trợ của browser, bao gồm **Secure**. Ví dụ trên còn dùng tiền tố __Host- để giữ phạm vi host hẹp. Cookie phân vùng không mặc nhiên được hỗ trợ và gửi trong mọi browser hay mọi ngữ cảnh; chính sách chặn cookie bên thứ ba và các hạn chế riêng tư vẫn có thể ảnh hưởng.

Không nên ép mọi ứng dụng Spring Boot thông thường dùng Partitioned. Đây là lựa chọn dành cho trường hợp có nhu cầu thực sự, chẳng hạn thành phần được nhúng trên nhiều site, và cần được kiểm thử với trình duyệt mục tiêu.

## 8. Ví dụ thực tế: SPA, API và cookie phiên trên hai origin

Giả sử hệ thống có:

~~~text
Frontend: https://app.example.com
API:      https://api.example.com
Session:  Cookie host-only do api.example.com đặt
~~~

Hai URL **same-site** nhưng **cross-origin**. Người dùng đăng nhập qua API, API tạo session và gửi cookie:

~~~http
HTTP/1.1 200 OK
Set-Cookie: __Host-session=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Frontend thực hiện fetch:

~~~javascript
const response = await fetch("https://api.example.com/api/me", {
  credentials: "include"
});

if (!response.ok) {
  throw new Error("HTTP " + response.status);
}

const user = await response.json();
~~~

Với chính sách phù hợp, browser có thể gửi session cookie của api.example.com. Nhưng nếu API chỉ định sai Origin trong Access-Control-Allow-Origin, script **không đọc được dữ liệu** dù server có thể đã xử lý request.

### 8.1. POST JSON kèm CSRF token

~~~javascript
// Ứng dụng đã nhận CSRF token hợp lệ bằng một luồng được thiết kế trước.
const csrfToken = getApplicationCsrfToken();

const response = await fetch("https://api.example.com/api/orders", {
  method: "POST",
  credentials: "include",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": csrfToken
  },
  body: JSON.stringify({ productId: 42 })
});
~~~

**getApplicationCsrfToken()** là hàm giả định của ứng dụng, không phải API có sẵn của trình duyệt. Khi dùng JSON và header tùy chỉnh như trên, browser thường gửi **OPTIONS preflight** trước POST:

~~~http
OPTIONS /api/orders HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type,x-csrf-token
~~~

Máy chủ cần xử lý preflight trước các bộ lọc xác thực có thể chặn OPTIONS, vì **preflight thường không mang cookie phiên**. Khi preflight hợp lệ, request POST thực tế vẫn phải vượt qua CSRF và authorization.

Điều này minh họa ba quyết định độc lập:

1. **Cookie policy + credentials** quyết định browser có đưa session cookie vào POST không.
2. **CORS** quyết định frontend cross-origin có được đọc phản hồi không và liệu preflight có đạt không.
3. **Spring Security** xác thực session, kiểm tra CSRF token và phân quyền endpoint.

## 9. Cấu hình Spring Security trên Servlet

Ví dụ dành cho **Spring Security 6.x** trong ứng dụng Spring MVC/Servlet. Frontend được phép tại **https://app.example.com**, API có endpoint dưới **/api/**:

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
                // Giữ CSRF protection mặc định cho hệ thống session.
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

Ví dụ **Spring Boot 3.x** (Servlet) cấu hình cookie session qua application.yml, khi ứng dụng chạy HTTPS:

~~~yaml
server:
  servlet:
    session:
      cookie:
        name: __Host-session
        path: /
        secure: true
        http-only: true
        same-site: lax
~~~

Với tiền tố **__Host-**, không đặt **Domain**. Tên cookie này chỉ minh họa lựa chọn phiên; kiểm tra tương thích với hệ thống session, cổng proxy và phiên bản Spring Boot thực tế khi triển khai.

**Lưu ý:**

- CORS example chỉ đăng ký cho **/api/** và hai method GET/POST; phải khai báo thêm method/header theo API hợp lệ.
- Chính sách CORS không tự cấp quyền truy cập: request không xác thực vẫn có thể bị 401/403.
- Giữ CSRF protection trong ứng dụng dựa trên cookie và thiết kế cách cấp CSRF token để SPA thực sự gửi được yêu cầu thay đổi trạng thái.
- Không đưa session cookie vào JavaScript chỉ để “dễ debug”; cấu hình **HttpOnly** cho cookie phiên nhạy cảm.
- Cần kiểm tra việc cấp mới hoặc đổi session id sau đăng nhập để phòng rủi ro **session fixation**, theo cơ chế Spring Security và session management thực tế.

## 10. Cấu hình Spring Security trên Reactive/WebFlux

Với stack WebFlux, sử dụng **ServerHttpSecurity** và các API CORS thuộc gói **org.springframework.web.cors.reactive**:

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
                // Giữ CSRF protection mặc định.
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

Cơ chế chọn và gửi cookie nằm ở **trình duyệt**, nên không đổi vì server dùng Servlet hay Reactive. Nhưng **lớp cấu hình và cơ chế session** trên hai stack khác nhau:

- Servlet thường dùng **HttpSession**, SecurityFilterChain và hệ thống session/cookie của servlet container hoặc Spring Session.
- WebFlux thường dùng **WebSession**, SecurityWebFilterChain và cách cấu hình cookie session thích hợp với WebFlux hoặc Spring Session Reactive.
- Không trộn hai loại CorsConfigurationSource của Servlet và Reactive.
- Kiểm tra tên cookie, Domain, Path, Secure, HttpOnly, SameSite và cách quản lý thời gian sống phiên **trên stack thực tế**; không sao chép máy móc thuộc tính Servlet sang cấu hình Reactive.
- Với WebFlux dùng cookie/session, vẫn cần thiết kế luồng cấp và kiểm tra CSRF token. Nếu SPA dùng X-CSRF-TOKEN, phải bảo đảm WebFlux bảo vệ và xử lý token theo cấu hình của ứng dụng.

## 11. Chẩn đoán cookie có được gửi thật không

Giả sử frontend báo “đăng nhập thành công nhưng gọi API sau đó lại 401”. Trước khi sửa Spring Security, kiểm tra trình duyệt đã lưu cookie và gửi cookie tới API hay chưa.

### 11.1. Các bước trong DevTools

1. Mở **Application/Storage → Cookies**. Kiểm tra cookie được lưu trên host nào, tên, Domain, Path, Secure, HttpOnly, SameSite, thời hạn và trạng thái phân vùng nếu trình duyệt hiển thị.
2. Mở **Network**, chọn response của request đăng nhập, kiểm tra **Set-Cookie** và phần cảnh báo cookie bị chặn. Không chỉ nhìn thấy Set-Cookie là kết luận browser đã lưu cookie.
3. Chọn request API tiếp theo, kiểm tra **Request Headers → Cookie** hoặc mục **Cookies** để biết cookie có thực sự được gửi hay bị loại do chính sách.
4. Nếu frontend dùng fetch cross-origin, xác nhận đã đặt **credentials: "include"** và server trả **Access-Control-Allow-Origin** cụ thể cùng **Access-Control-Allow-Credentials: true** khi cần đọc phản hồi.
5. Nếu có **OPTIONS preflight**, kiểm tra nó trước, sau đó mới kiểm tra request thực. Preflight thiếu cookie thường là bình thường, không mặc nhiên là lỗi.
6. Nếu cookie có trong request mà server vẫn trả 401, kiểm tra session còn hiệu lực không, session store có chia sẻ giữa instance không, cơ chế xác thực và session fixation/rotation sau đăng nhập.
7. Nếu request trả 403, phân biệt **CSRF token không hợp lệ** với **không đủ quyền**; xem log/trace server và phương thức HTTP thực tế.

### 11.2. Ma trận triệu chứng

| Triệu chứng | Giả thuyết cần kiểm tra | Kiểm tra cụ thể |
| --- | --- | --- |
| Response có Set-Cookie nhưng storage không có cookie. | Domain không hợp lệ, thiếu Secure, tiền tố __Host- sai, chính sách cookie chặn. | DevTools Issues/Cookies, giá trị attributes và URL HTTPS. |
| Cookie có trong storage nhưng không gửi khi fetch API khác subdomain. | Fetch mặc định same-origin hoặc URL API không khớp Domain/Path. | credentials: include, URL đích, host-only vs Domain. |
| Cookie không gửi khi gọi API cross-site từ iframe. | SameSite=Strict/Lax, cookie bên thứ ba bị chặn hoặc ngữ cảnh ancestor. | Top-level site, iframe context, chính sách cookie browser. |
| Cookie có trong POST nhưng server trả 403. | CSRF token không có/sai hoặc không đủ quyền. | Security logs, X-CSRF-TOKEN và cấu hình CSRF. |
| OPTIONS không có Cookie. | Preflight CORS thường không mang credentials. | Kiểm tra phản hồi CORS của OPTIONS, tránh yêu cầu login trước preflight. |
| Network có response nhưng script báo lỗi CORS. | CORS không cho phép đọc response có credentials. | Access-Control-Allow-Origin, Allow-Credentials, Vary. |
| GET chạy khi mở tab nhưng POST từ trang ngoài không gửi session. | SameSite=Lax có thể cho phép điều hướng GET cấp cao nhất nhưng giới hạn POST cross-site. | Site nguồn, method, SameSite và loại navigation. |
| Chạy với curl được nhưng browser không gửi cookie. | Curl không có cookie jar/giới hạn SameSite giống browser hoặc request không cùng ngữ cảnh. | Dùng DevTools làm nguồn kiểm chứng browser; tự kiểm tra Cookie header ở curl. |
| Session mất sau deploy nhiều instance. | Server-side session store không chia sẻ hoặc session hết hạn. | Session repository, sticky session nếu dùng và thời gian sống server-side. |
| Cookie bị ghi đè hoặc trùng tên. | Cookie cùng tên khác Domain/Path hoặc subdomain mở rộng scope. | Kiểm tra đầy đủ tên, Domain và Path; dùng host-only/__Host- khi thích hợp. |

### 11.3. curl chỉ quan sát HTTP, không mô phỏng đầy đủ trình duyệt

Ví dụ xem response tạo cookie trong môi trường thử nghiệm:

~~~bash
curl -i "https://app.example.com/login"
~~~

Một cookie jar của curl có thể lưu/gửi cookie theo cách được công cụ hỗ trợ, nhưng **curl không áp dụng đầy đủ SOP/CORS, hành vi same-site của trang cấp cao nhất, các quy tắc nhúng và chặn cookie bên thứ ba như browser**. Vì vậy không dựa vào kết quả curl để khẳng định một lời gọi fetch trong Chrome/Firefox/Safari chắc chắn gửi cookie hay đọc được response.

Với PowerShell, có thể sử dụng **curl.exe** để tránh bí danh curl trỏ tới lệnh PowerShell khác.

## 12. Bài tập tình huống

### Tình huống A — Cookie HttpOnly có được tự gửi?

Server gửi cookie session có **Secure; HttpOnly; SameSite=Lax; Path=/**. JavaScript không đọc được cookie qua document.cookie. Khi người dùng mở /account cùng origin, cookie có thể xuất hiện trong HTTP request không?

**Đáp án:** Có, nếu cookie chưa hết hạn và các điều kiện còn lại phù hợp. HttpOnly ngăn JavaScript đọc trực tiếp, **không ngăn browser gửi cookie**.

### Tình huống B — Khác port trong localhost

Frontend ở **http://localhost:3000**, API ở **http://localhost:8080**. Một cookie không có Secure, host-only của localhost và Path=/ có thể được gửi tới cả hai port không? Vì sao fetch API vẫn không mang cookie theo mặc định?

**Đáp án:** Cookie không phân biệt port, nên có thể khớp cả hai URL khi các quy tắc khác cho phép. Nhưng **origin có phân biệt port**: fetch từ 3000 đến 8080 là cross-origin và credentials mặc định same-origin không tự gửi cookie. Cần credentials: include nếu đúng mô hình và CORS thích hợp để đọc phản hồi.

### Tình huống C — Same-site khác origin

Trang **https://app.example.com** gọi **https://api.example.com** bằng fetch kèm credentials: include. API có cookie HttpOnly với SameSite=Strict do chính api.example.com tạo. Cookie có chắc chắn bị chặn chỉ vì hai host khác nhau không?

**Đáp án:** Không. Hai host thường **same-site** theo https://example.com. Cookie có thể được gửi tới host API khi các điều kiện cookie, ngữ cảnh site và credentials phù hợp. Nhưng hai URL **cross-origin**, nên cần CORS để script đọc response.

### Tình huống D — Cookie Lax và liên kết từ trang ngoài

Người dùng đang có cookie session SameSite=Lax cho **https://bank.example** và bấm một liên kết GET trên **https://outside.test** để mở trang tài khoản ngân hàng ở tab chính. Cookie có thể được gửi không? Có nên triển khai thao tác chuyển tiền qua GET?

**Đáp án:** Cookie Lax thường có thể gửi trong **top-level navigation GET** cross-site. Do đó tuyệt đối không dùng GET cho chuyển tiền hoặc thao tác thay đổi trạng thái; đây là một lý do cần phân biệt **safe method** với các request tạo tác dụng phụ.

### Tình huống E — CORS chặn nhưng cookie đã gửi

API khác origin trả HTTP 200, và Network cho thấy request có Cookie. Mã fetch vẫn nhận lỗi CORS. Hệ thống có chắc không xác thực người dùng không?

**Đáp án:** Không. Browser có thể đã gửi cookie và server xử lý request; lỗi CORS cho biết script không được phép đọc response. Cần kiểm tra Access-Control-Allow-Origin, Allow-Credentials và cách cache/proxy xử lý header; xác thực/phân quyền là chuyện riêng.

### Tình huống F — Bearer token trong localStorage

SPA lưu một access token ở localStorage nhưng chưa thêm Authorization cho request. Khi người dùng mở một URL API trong tab mới, browser có tự lấy token đó gắn vào header Authorization: Bearer không?

**Đáp án:** Không. Token lưu trong localStorage không tự biến thành Authorization header. Phải có mã ứng dụng hoặc cơ chế khác chủ động gắn token; đồng thời cần bảo vệ token trước XSS.

### Tình huống G — CSRF từ subdomain

Một blog không đáng tin ở **https://blog.example.com** cố gửi request tới API phiên ở **https://api.example.com**. Cookie API có SameSite=Strict. Có thể coi request chắc chắn không mang cookie không?

**Đáp án:** Không. Hai URL thường **same-site** dù khác origin. SameSite=Strict không đảm bảo chặn request cùng site từ subdomain không đáng tin. Duy trì CSRF protection, authentication, authorization và chính sách CORS chặt chẽ.

### Tình huống H — Xóa session trên client

Ứng dụng xóa cookie session bằng Set-Cookie Max-Age=0 nhưng mã phiên phía server vẫn còn trong session store. Có thể khẳng định mã phiên đã bị vô hiệu hóa hoàn toàn không?

**Đáp án:** Không. Lệnh xóa cookie chủ yếu tác động cookie tại browser với phạm vi tên/Domain/Path tương ứng; việc **invalidating session phía server** mới ngăn sử dụng lại một session id còn hợp lệ từ nguồn khác.

### Tình huống I — Preflight và thông tin đăng nhập

Trang khác origin gửi POST JSON với X-CSRF-TOKEN. OPTIONS preflight không có Cookie và bị Spring Security yêu cầu đăng nhập nên trả 401. Có nên buộc preflight phải có session cookie?

**Đáp án:** Không. Preflight thường được gửi **không kèm cookie/session**. Cấu hình CORS phải được xử lý trước các bước chặn OPTIONS; POST thực vẫn phải có credentials phù hợp, CSRF token và quyền hợp lệ.

## 13. Ghi nhớ

- **Trình duyệt có thể tự lưu và gửi cookie** sau Set-Cookie; request Cookie chỉ chứa tên=giá trị, không gửi lại các thuộc tính cookie.
- Quyết định gửi cookie phụ thuộc **host/Domain, Path, Secure, SameSite, thời hạn, ngữ cảnh browser và chính sách request**. Cookie **không cô lập theo port**.
- **HttpOnly ngăn mã JavaScript đọc cookie**, nhưng browser vẫn gửi cookie hợp lệ; đây là lý do HttpOnly không tự chống CSRF.
- **Same-site khác same-origin**. Hai subdomain hoặc hai port có thể cùng site nhưng khác origin; fetch cross-origin mặc định không gửi credentials.
- **credentials: include** cho phép browser xử lý credentials cross-origin nhưng **không vượt qua SameSite, Secure, Domain/Path hoặc chính sách cookie bên thứ ba**.
- **CORS quản lý quyền đọc response cross-origin**; việc gửi được request có cookie không bảo đảm mã frontend được đọc response.
- **HTTP authentication có thể tự tái sử dụng credentials**, còn Bearer token lưu trong bộ nhớ/localStorage không tự được gắn vào Authorization nếu ứng dụng không thực hiện.
- **CSRF protection, authentication và authorization** phải được thiết kế độc lập với cookie và CORS. Spring Security Servlet/Reactive có thể giúp thực thi các kiểm tra này, nhưng frontend và cấu hình session cũng phải tương thích.
