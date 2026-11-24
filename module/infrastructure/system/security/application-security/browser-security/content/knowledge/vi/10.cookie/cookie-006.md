# Secure attribute: chỉ gửi cookie qua kết nối an toàn

## 1. Secure attribute bảo vệ điều gì?

Cookie thường lưu session ID, trạng thái đăng nhập hoặc dữ liệu mà ứng dụng dùng để nhận diện người dùng. Nếu trình duyệt gửi cookie qua kết nối HTTP không mã hóa, người có khả năng quan sát đường truyền có thể đọc giá trị cookie và sử dụng lại nó để chiếm phiên đăng nhập.

Thuộc tính **`Secure`** yêu cầu trình duyệt chỉ gửi cookie trên kênh truyền tải được xem là an toàn, thông thường là HTTPS. Đây là một thuộc tính quan trọng để bảo vệ cookie phiên khỏi việc bị gửi qua HTTP không mã hóa.

Ví dụ:

```http
Set-Cookie: session=opaque-random-value; Path=/; Secure; HttpOnly; SameSite=Lax
```

Trình duyệt lưu cookie cùng các thuộc tính của nó. Khi request sau này khớp phạm vi cookie, trình duyệt chỉ đính kèm cookie Secure nếu request đi qua kết nối an toàn. Nếu người dùng truy cập cùng host bằng HTTP, cookie Secure không được gửi trong request đó.

Trong module bảo mật ứng dụng web, Secure cần được hiểu cùng với HTTPS/TLS, cookie scope, `HttpOnly`, `SameSite`, HSTS, SOP, CSRF và cách kiểm chứng header thực tế. Mỗi thuộc tính xử lý một khía cạnh riêng; không có một flag nào thay thế toàn bộ mô hình bảo mật phiên.

Sau bài học, bạn có thể:

- Giải thích hành vi gửi cookie có và không có `Secure`.
- Cấu hình cookie phiên an toàn trên HTTPS.
- Phân biệt Secure với `HttpOnly`, `SameSite` và HSTS.
- Hiểu giới hạn về domain, path, port và subdomain.
- Sử dụng các prefix `__Secure-` và `__Host-` để ràng buộc cookie.
- Kiểm chứng việc gửi cookie bằng DevTools.

## 2. Cách trình duyệt xử lý cookie Secure

Cookie thường được server tạo bằng response header `Set-Cookie`:

```http
HTTP/1.1 200 OK
Set-Cookie: session=abc123; Path=/; Secure; HttpOnly; SameSite=Lax
```

Khi trình duyệt gửi request tới host và path phù hợp qua HTTPS, cookie có thể xuất hiện trong request header:

```http
GET /account HTTP/1.1
Host: app.example.com
Cookie: session=abc123
```

Khi request tới cùng host qua HTTP:

```http
GET /account HTTP/1.1
Host: app.example.com
```

Cookie `session` có thuộc tính Secure sẽ không được đính kèm. Thuộc tính Secure **không xuất hiện trong request header Cookie**; trình duyệt chỉ gửi cặp tên/giá trị cookie. Server biết cookie đã được gửi, còn chính sách Secure được trình duyệt áp dụng ở phía client.

### 2.1 Secure không phải là mã hóa giá trị cookie trong kho lưu trữ

Secure kiểm soát **kênh truyền tải khi gửi cookie**. Nó không có nghĩa cookie được mã hóa trong cookie store của trình duyệt, cũng không làm cho giá trị cookie trở nên vô nghĩa nếu bị lộ qua một kênh khác.

Ứng dụng nên dùng session ID ngẫu nhiên, khó đoán và không chứa dữ liệu nhạy cảm trực tiếp. Server lưu trạng thái phiên và có thể thu hồi session. Không dùng cookie Secure như một nơi lưu mật khẩu, access token dài hạn hoặc dữ liệu bí mật ở dạng rõ.

### 2.2 Secure áp dụng cho request phù hợp, không chỉ trang đăng nhập

Nếu cookie có `Path=/` và host scope phù hợp, cookie có thể được gửi tới nhiều endpoint HTTPS trên host đó. Ví dụ trang đăng nhập và API tài khoản cùng host có thể nhận cookie. Thuộc tính Secure không giới hạn cookie chỉ cho một endpoint hoặc một route.

## 3. Cấu hình cookie phiên an toàn

Một cấu hình khởi đầu thường gặp cho cookie session:

```http
Set-Cookie: __Host-session=opaque-random-id; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=1800
```

Ý nghĩa:

| Thuộc tính | Tác dụng |
| --- | --- |
| `Secure` | Chỉ gửi cookie qua kênh an toàn như HTTPS. |
| `HttpOnly` | JavaScript không thể đọc cookie qua `document.cookie`. |
| `SameSite=Lax` | Hạn chế gửi cookie trong nhiều ngữ cảnh cross-site, giúp giảm một số rủi ro CSRF. |
| `Path=/` | Cookie áp dụng cho các path phù hợp trên host. |
| `Max-Age=1800` | Thời hạn tồn tại tối đa được yêu cầu là 1.800 giây, nếu không bị xóa/ghi đè sớm hơn. |
| Prefix `__Host-` | Ràng buộc thêm điều kiện Secure, Path và Domain. |

Các giá trị cụ thể cần phù hợp với luồng đăng nhập. Ví dụ, một ứng dụng nhúng trong ngữ cảnh cross-site có thể cần `SameSite=None; Secure`, nhưng còn chịu chính sách cookie bên thứ ba và partitioning của trình duyệt. Không đổi SameSite sang None chỉ để “sửa lỗi cookie” nếu chưa đánh giá mô hình CSRF và quyền truy cập.

### 3.1 Không bỏ Secure trên cookie phiên trong production

Một lỗi cấu hình phổ biến là server đặt cookie phiên không có Secure:

```http
Set-Cookie: session=opaque-random-id; Path=/; HttpOnly; SameSite=Lax
```

Nếu ứng dụng hoặc người dùng còn truy cập được qua HTTP, trình duyệt có thể gửi cookie qua kết nối không mã hóa. Kẻ tấn công có khả năng quan sát mạng có thể đánh cắp session ID.

Nên cấu hình Secure cho cookie phiên và chuyển toàn bộ website sang HTTPS. Trong môi trường phát triển, hãy dùng HTTPS cục bộ nếu có thể; một số trình duyệt có ngoại lệ cho localhost được xem là secure context, nhưng không nên dựa vào ngoại lệ đó để suy ra hành vi production.

## 4. Secure và phạm vi cookie: domain, host, path, port

Secure chỉ quyết định cookie có được gửi qua kênh truyền tải an toàn hay không. Nó không thay đổi các quy tắc chọn cookie theo host/domain và path.

| Thành phần | Vai trò | Secure có thay đổi không? |
| --- | --- | --- |
| Host-only cookie | Nếu không có `Domain`, cookie chỉ áp dụng cho host đã đặt nó. | Không. |
| `Domain` | Mở rộng cookie tới domain và các subdomain phù hợp. | Không. |
| `Path` | Giới hạn request path phù hợp để gửi cookie. | Không. |
| Port | Cookie không được phân vùng theo port như origin. | Không. |
| Scheme/transport | Secure yêu cầu kênh an toàn khi gửi cookie. | Có; đây là mục đích chính. |

### 4.1 Secure không tách cookie theo port

Hai ứng dụng ở `https://app.example.com:443` và `https://app.example.com:8443` có thể là hai origin khác nhau vì port khác nhau, nhưng cookie không được phân chia theo port. Cookie phù hợp có thể được gửi tới request HTTPS trên cùng host ở các port khác nhau, tùy phạm vi và chính sách cookie.

Vì vậy, không dùng port để cô lập session giữa nhiều ứng dụng trên cùng hostname. Nếu các ứng dụng cần ranh giới cookie riêng, cân nhắc dùng hostname riêng và cookie host-only với prefix `__Host-`.

### 4.2 Domain rộng làm tăng phạm vi tin cậy

Cookie sau có thể được gửi tới nhiều subdomain phù hợp:

```http
Set-Cookie: session=abc123; Domain=example.com; Path=/; Secure; HttpOnly
```

Nếu một subdomain cũ, ứng dụng thử nghiệm hoặc dịch vụ do bên thứ ba quản lý bị chiếm quyền, phạm vi Domain rộng có thể làm tăng rủi ro cho cookie. Khi không cần chia sẻ cookie giữa subdomain, nên bỏ thuộc tính Domain để tạo **host-only cookie**.

`Secure` không biến cookie Domain rộng thành cookie chỉ dành cho một host. Prefix `__Host-` giúp ràng buộc cookie với host đã đặt nó.

## 5. Prefix __Secure- và __Host-

Cookie prefix là quy ước được trình duyệt hiện đại thực thi để ràng buộc cách cookie được tạo. Prefix có phân biệt chữ hoa/thường và phải được viết đúng.

### 5.1 Prefix __Secure-

Cookie có tên bắt đầu bằng `__Secure-` phải được đặt với thuộc tính `Secure` và từ một origin được xem là secure theo quy tắc trình duyệt:

```http
Set-Cookie: __Secure-session=opaque-id; Secure; HttpOnly; Path=/; SameSite=Lax
```

Prefix này giúp trình duyệt từ chối một số trường hợp cookie cùng tên được tạo không đáp ứng điều kiện Secure. Nó không tự yêu cầu cookie host-only, nên cookie vẫn có thể có `Domain` nếu được cấu hình.

### 5.2 Prefix __Host-

Cookie có tên bắt đầu bằng `__Host-` có các điều kiện chặt hơn:

- Phải có `Secure`.
- Phải có `Path=/`.
- Không được có thuộc tính `Domain`.
- Phải được đặt từ secure origin theo quy tắc trình duyệt.

Ví dụ:

```http
Set-Cookie: __Host-session=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
```

Trình duyệt sẽ từ chối cookie `__Host-session` nếu response cố đặt `Domain=example.com` hoặc dùng `Path=/account`. Nhờ không có Domain, cookie chỉ thuộc host đã thiết lập nó. Điều này giảm khả năng một subdomain khác tạo cookie cùng tên để gây nhầm lẫn hoặc can thiệp cookie scope.

### 5.3 So sánh hai prefix

| Điều kiện | `__Secure-` | `__Host-` |
| --- | --- | --- |
| Phải có Secure | Có | Có |
| Phải từ secure origin | Có | Có |
| Bắt buộc Path=/ | Không | Có |
| Cấm Domain | Không | Có |
| Ràng buộc host-only | Không bắt buộc | Có |

Với session cookie chỉ dành cho một host, `__Host-` thường là lựa chọn tốt nếu ứng dụng và các trình duyệt mục tiêu hỗ trợ. Nếu cần cookie chia sẻ giữa subdomain, prefix này không phù hợp vì nó cấm Domain.

## 6. Secure kết hợp với HttpOnly và SameSite

Ba thuộc tính thường được cấu hình cùng nhau nhưng giải quyết các vấn đề khác nhau:

| Thuộc tính | Bảo vệ chính | Không tự bảo vệ khỏi |
| --- | --- | --- |
| `Secure` | Ngăn cookie được gửi qua HTTP không an toàn. | JavaScript đọc cookie, XSS, CSRF hoặc lộ cookie qua log. |
| `HttpOnly` | Ngăn JavaScript đọc cookie qua API như `document.cookie`. | Trình duyệt tự gửi cookie trong request; CSRF; XSS thao tác DOM/API. |
| `SameSite` | Hạn chế gửi cookie trong một số ngữ cảnh cross-site. | Mọi CSRF, XSS hoặc truy cập cross-origin cùng site. |

Một cookie session thường nên có cả ba thuộc tính:

```http
Set-Cookie: __Host-session=opaque-id; Path=/; Secure; HttpOnly; SameSite=Lax
```

### 6.1 SameSite=None yêu cầu Secure

Nếu cookie cần được gửi trong ngữ cảnh cross-site, ví dụ một số luồng đăng nhập/nhúng đối tác, cấu hình có thể cần:

```http
Set-Cookie: widget-session=opaque-id; SameSite=None; Secure; HttpOnly; Path=/
```

Các trình duyệt hiện đại yêu cầu cookie `SameSite=None` phải có `Secure`; cookie thiếu Secure thường bị từ chối. Tuy nhiên, `SameSite=None; Secure` không bảo đảm cookie bên thứ ba luôn được chấp nhận: trình duyệt có thể chặn cookie bên thứ ba, phân vùng cookie hoặc áp dụng chính sách quyền riêng tư khác.

### 6.2 HttpOnly không ngăn XSS thực hiện hành động

Nếu trang có XSS, script độc hại có thể không đọc được cookie HttpOnly, nhưng vẫn có thể gọi API trong phiên người dùng vì trình duyệt tự gửi cookie phù hợp. Do đó, cần phòng vệ XSS bằng output encoding, DOM API an toàn, CSP và Trusted Types; đồng thời bảo vệ endpoint nhạy cảm ở server.

### 6.3 Secure không chống CSRF

Cookie Secure vẫn có thể được gửi trong request HTTPS cross-site nếu các quy tắc cookie và credentials cho phép. Secure chỉ kiểm soát transport. Hãy dùng `SameSite` phù hợp, CSRF token hoặc cơ chế xác minh Origin/Referer theo mô hình ứng dụng, và không dùng GET để thay đổi trạng thái.

## 7. Secure và HSTS: hai lớp bảo vệ bổ sung

Secure cookie yêu cầu trình duyệt chỉ gửi cookie qua kết nối an toàn. Nhưng nếu người dùng bắt đầu truy cập website bằng HTTP, họ có thể vẫn gặp một lần điều hướng không mã hóa trước khi được chuyển sang HTTPS. **HTTP Strict Transport Security (HSTS)** giúp trình duyệt ghi nhớ rằng host phải được truy cập bằng HTTPS.

Server có thể gửi header qua một phản hồi HTTPS:

```http
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

- `max-age` là thời gian (giây) trình duyệt ghi nhớ chính sách.
- `includeSubDomains` áp dụng cho subdomain; chỉ bật khi mọi subdomain phù hợp đều hỗ trợ HTTPS.
- `preload` chỉ có ý nghĩa khi domain đáp ứng điều kiện và được đưa vào danh sách preload của trình duyệt; thêm token vào header không tự đăng ký domain.

So sánh:

| Cơ chế | Vai trò |
| --- | --- |
| Cookie `Secure` | Không gửi cookie qua HTTP không an toàn. |
| HSTS | Yêu cầu trình duyệt nâng cấp truy cập tới host sang HTTPS trong thời gian chính sách còn hiệu lực. |
| HTTPS/TLS | Mã hóa và xác thực kết nối tới server, bảo vệ dữ liệu truyền trên đường truyền. |

Secure không tự chuyển URL HTTP thành HTTPS và HSTS không thay thế việc gắn Secure cho cookie. Nên dùng cả hai trong hệ thống production chỉ chạy HTTPS.

## 8. Những điều Secure không làm

### 8.1 Không ngăn JavaScript đọc cookie

Cookie có `Secure` nhưng không có `HttpOnly` vẫn có thể được JavaScript đọc từ document HTTPS nếu các điều kiện khác cho phép:

```javascript
// Cookie Secure nhưng không HttpOnly có thể đọc được
// qua document.cookie trong document phù hợp.
console.log(document.cookie);
```

Không đặt token phiên có giá trị cao trong cookie có thể bị script đọc. Với cookie session, thường dùng `HttpOnly`.

### 8.2 Không mã hóa cookie trong mọi nơi

Secure không mã hóa giá trị trong log ứng dụng, bản dump, công cụ giám sát hoặc kho lưu trữ. Không log session ID; che dữ liệu cookie trong hệ thống observability; bảo vệ quyền truy cập vào máy chủ và cookie store.

### 8.3 Không thay thế xác thực và quản lý phiên

Cookie Secure chỉ là một phần của vận chuyển phiên. Backend vẫn cần:

- Session ID ngẫu nhiên, khó đoán.
- Hết hạn idle/absolute phù hợp và thu hồi khi logout.
- Đổi session ID sau đăng nhập hoặc thay đổi đặc quyền.
- Kiểm tra quyền trên từng request.
- Phát hiện và xử lý phiên bị thu hồi hoặc có dấu hiệu bất thường.

### 8.4 Không tách biệt các ứng dụng cùng host

Cookie không phân vùng theo port. Secure không giới hạn cookie cho một ứng dụng hoặc một process. Nếu nhiều ứng dụng không tin cậy nhau dùng chung host, cần thiết kế hostname/cookie scope riêng.

## 9. Tạo và cập nhật cookie trong ứng dụng

### 9.1 Tạo cookie bằng response header

Server nên phát cookie phiên qua HTTPS:

```http
HTTP/1.1 200 OK
Set-Cookie: __Host-session=opaque-random-id; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=1800
Cache-Control: no-store
```

`Cache-Control: no-store` ở response đăng nhập là một ví dụ hữu ích để tránh cache response có nội dung liên quan phiên; chính sách thực tế cần theo dữ liệu trả về. Giá trị session ID nên là dữ liệu opaque, không chứa thông tin cá nhân ở dạng rõ.

### 9.2 JavaScript có thể đặt Secure nhưng không thể đặt HttpOnly

JavaScript trong document phù hợp có thể tạo cookie bằng `document.cookie`:

```javascript
document.cookie =
  "theme=dark; Path=/; Secure; SameSite=Lax";
```

Nhưng JavaScript **không thể tạo cookie HttpOnly**. Thuộc tính HttpOnly phải được server đặt trong `Set-Cookie`. Ngoài ra, header `Set-Cookie` không được expose cho JavaScript thông qua `fetch` response headers; đây là header bị cấm truy cập từ frontend.

Với session cookie, nên để server quản lý cookie và gắn đầy đủ thuộc tính thay vì dựa vào JavaScript.

### 9.3 Reverse proxy và TLS termination

Một hệ thống có thể kết thúc TLS ở load balancer hoặc reverse proxy rồi chuyển tiếp request nội bộ tới ứng dụng qua HTTP. Ở kiến trúc này, ứng dụng vẫn cần phát cookie có Secure vì kết nối **từ trình duyệt tới public endpoint** là HTTPS.

Nếu framework suy luận scheme từ header như `X-Forwarded-Proto`, chỉ tin header này khi request đến từ proxy được cấu hình tin cậy. Không bật trust proxy rộng tùy tiện; nếu client có thể giả mạo header, logic redirect, secure cookie hoặc nhận diện HTTPS có thể bị ảnh hưởng.

Ưu tiên cấu hình cookie Secure tường minh trong production. Kiểm tra response `Set-Cookie` thực tế tại điểm kết thúc TLS thay vì chỉ nhìn cấu hình trong code.

## 10. Kiểm chứng Secure attribute bằng DevTools

Thực hiện trong môi trường thử nghiệm do bạn kiểm soát, không dùng session thật.

### 10.1 Quan sát cookie được lưu

1. Mở website thử nghiệm qua HTTPS.
2. Mở DevTools → **Application** (Chrome/Chromium) → **Storage → Cookies**.
3. Chọn host thử nghiệm và tìm cookie session.
4. Kiểm tra cột **Secure**, **HttpOnly**, **SameSite**, **Domain** và **Path**.
5. Nếu cookie dùng prefix `__Host-`, xác nhận Secure được bật, Path là `/` và Domain không được đặt.

### 10.2 So sánh request HTTPS và HTTP

Trong Network panel:

1. Gửi request tới endpoint HTTPS phù hợp với domain/path cookie. Xem request header `Cookie`; cookie Secure có thể xuất hiện.
2. Thử endpoint HTTP cùng host trong môi trường lab. Cookie Secure không được gửi qua request HTTP.
3. Nếu browser tự nâng cấp URL HTTP vì HSTS hoặc localhost policy, hãy ghi nhận rằng request thực tế đã được nâng cấp; không kết luận Secure bị bỏ qua.

Không dùng DevTools để copy session ID vào nơi khác. Khi chia sẻ ảnh chụp hoặc log, che giá trị cookie.

### 10.3 Kiểm tra prefix

Thử phát các response Set-Cookie trong môi trường lab:

```http
Set-Cookie: __Host-demo=one; Path=/; Secure; HttpOnly
Set-Cookie: __Host-invalid=two; Path=/account; Secure
Set-Cookie: __Host-invalid-domain=three; Domain=example.com; Path=/; Secure
```

Cookie đầu tiên đáp ứng các điều kiện chính của prefix `__Host-`. Hai cookie sau vi phạm Path hoặc Domain nên trình duyệt hiện đại hỗ trợ prefix sẽ từ chối. Quan sát Console/Storage để kiểm tra kết quả.

## 11. Các lỗi cấu hình thường gặp

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Cookie session thiếu Secure | Cookie có thể được gửi qua HTTP. | Bật Secure trên cookie phiên production; triển khai HTTPS toàn site. |
| Chỉ bật Secure mà thiếu HttpOnly | Script có thể đọc cookie nếu có XSS. | Dùng HttpOnly cho session cookie. |
| Cho cookie Domain quá rộng | Cookie được chia sẻ tới nhiều subdomain hơn cần thiết. | Dùng host-only cookie; cân nhắc prefix __Host-. |
| Dùng SameSite=None nhưng thiếu Secure | Trình duyệt hiện đại thường từ chối cookie. | Kết hợp SameSite=None; Secure khi thật sự cần cross-site. |
| Cho rằng Secure thay HSTS | Lần truy cập HTTP đầu tiên vẫn có thể bị downgrade. | Triển khai HSTS sau khi HTTPS và subdomain đã sẵn sàng. |
| Tin localhost tương đương production | Hành vi ngoại lệ của môi trường dev có thể khác production. | Kiểm tra bằng HTTPS và xác minh trên browser mục tiêu. |
| Đặt Secure bằng JavaScript rồi cho rằng có HttpOnly | JS không thể đặt HttpOnly. | Phát session cookie bằng Set-Cookie từ server. |
| Dùng chung host cho nhiều app và kỳ vọng port cô lập cookie | Cookie có thể được gửi tới nhiều port cùng host. | Tách hostname và scope cookie. |

## 12. Bài tập tự kiểm tra

1. Nếu cookie có `Secure` nhưng thiếu `HttpOnly`, JavaScript trên trang HTTPS có thể đọc cookie không? Giải thích.
2. Vì sao cookie Secure không được gửi qua HTTP nhưng vẫn có thể được gửi tới nhiều port HTTPS trên cùng host?
3. Sự khác nhau giữa prefix `__Secure-` và `__Host-` là gì?
4. Vì sao `SameSite=None` cần đi cùng Secure trên trình duyệt hiện đại?
5. Cookie Secure có ngăn CSRF không? Cần bổ sung cơ chế nào?
6. HSTS và Secure giải quyết hai vấn đề gì khác nhau?
7. Một ứng dụng đặt cookie `Domain=example.com` có thể làm tăng rủi ro gì nếu subdomain bị chiếm quyền?
8. Vì sao reverse proxy TLS termination vẫn cần response Set-Cookie có Secure?

## 13. Tổng kết

**Secure attribute yêu cầu trình duyệt chỉ gửi cookie qua kết nối an toàn như HTTPS.** Nó giảm nguy cơ session cookie bị truyền qua HTTP không mã hóa, nhưng không mã hóa cookie trong mọi nơi, không ngăn JavaScript đọc cookie nếu thiếu HttpOnly, không tự chống CSRF và không phân tách cookie theo port.

Với session cookie, cấu hình thường nên có `Secure`, `HttpOnly` và `SameSite` phù hợp. Prefix `__Host-` bổ sung ràng buộc host-only bằng cách yêu cầu Secure, Path=/ và không có Domain. Kết hợp Secure với HTTPS toàn site và HSTS; đồng thời giữ quản lý phiên, xác thực, phân quyền, chống XSS/CSRF và kiểm thử thực tế bằng DevTools.
