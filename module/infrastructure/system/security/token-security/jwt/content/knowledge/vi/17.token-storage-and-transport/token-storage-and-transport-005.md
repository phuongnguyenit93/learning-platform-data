# Cookie HttpOnly, Secure, SameSite và phạm vi Domain, Path

## 1. Cookie đóng vai trò gì khi lưu trữ và truyền JWT?

Cookie là cơ chế lưu cặp tên/giá trị trong trình duyệt và tự động gửi cookie phù hợp theo request tới máy chủ. Một ứng dụng có thể đặt JWT trong cookie để trình duyệt tự gửi token khi gọi API. Cách này thuận tiện cho ứng dụng web, nhưng thay đổi mô hình bảo mật: **trình duyệt tự động đính kèm cookie**, nên hệ thống phải kiểm soát phạm vi gửi cookie và nguy cơ Cross-Site Request Forgery (CSRF).

Các thuộc tính thường gặp có vai trò khác nhau:

- `HttpOnly` hạn chế JavaScript đọc cookie qua API như `document.cookie`.
- `Secure` yêu cầu trình duyệt chỉ gửi cookie qua kênh an toàn, thông thường là HTTPS.
- `SameSite` kiểm soát việc cookie có được gửi trong ngữ cảnh same-site hay cross-site.
- `Domain` xác định host hoặc nhóm host được phép nhận cookie.
- `Path` giới hạn các đường dẫn request mà trình duyệt gửi cookie tới.

Các thuộc tính này không thay thế chữ ký JWT, kiểm tra claims hoặc phân quyền. Chúng kiểm soát cách trình duyệt lưu và gửi cookie. Server vẫn phải xác minh JWT theo issuer, audience, thời hạn, loại token và chính sách truy cập.

Bài thuộc chương **Lưu trữ và truyền** của module **Security - JSON Web Token (JWT)**. Phạm vi tập trung vào cookie trong trình duyệt và cách dùng cookie để truyền JWT; nội dung áp dụng chung, không phụ thuộc Java hoặc framework.

## 2. Cookie được tạo và gửi như thế nào?

### 2.1. Server gửi Set-Cookie

Server tạo cookie qua header phản hồi `Set-Cookie`:

~~~http
HTTP/1.1 200 OK
Set-Cookie: __Host-access_token=<JWT>; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=900
Content-Type: application/json
~~~

Trình duyệt xử lý header và lưu cookie. Khi request tiếp theo phù hợp với host, path, thời hạn, Secure và SameSite, trình duyệt tự thêm header:

~~~http
GET /api/profile HTTP/1.1
Host: app.example.com
Cookie: __Host-access_token=<JWT>
~~~

Header `Cookie` chỉ mang tên và giá trị. Các thuộc tính `HttpOnly`, `Secure`, `SameSite`, `Domain` và `Path` không được gửi lại trong request; đó là metadata trình duyệt dùng để quyết định có gửi cookie hay không.

### 2.2. Thuộc tính nên được thiết lập ở phía server

Các thuộc tính bảo mật nên được server thiết lập trong `Set-Cookie`. Không dựa vào JavaScript để nâng cấp cookie sau khi đã lưu:

- JavaScript không thể thêm `HttpOnly` cho một cookie đã được tạo bằng script.
- Cookie được tạo bằng JavaScript không thể có thuộc tính `HttpOnly`.
- `Secure` và `SameSite` có thể được khai báo trong một số API phía client, nhưng chính sách bảo mật nên được server kiểm soát nhất quán.
- Client không thể tự đặt cookie cho một domain tùy ý.

### 2.3. Cookie không xác minh JWT

Trình duyệt chỉ lưu và vận chuyển giá trị. Nó không xác minh chữ ký, issuer, audience hoặc quyền của JWT. Cookie có thể bị xóa, hết hạn, gửi lại hoặc bị thay đổi bởi client.

Nếu cookie chứa JWT đã bị sửa, server phải từ chối sau bước xác minh chữ ký. Không được tin claims chỉ vì giá trị đến từ cookie có tên quen thuộc.

## 3. HttpOnly: hạn chế JavaScript đọc cookie

### 3.1. Ý nghĩa của HttpOnly

Khi cookie có thuộc tính `HttpOnly`, trình duyệt không cho API truy cập cookie từ JavaScript như `document.cookie` đọc giá trị đó:

~~~http
Set-Cookie: __Host-access_token=<JWT>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Mục tiêu là giảm khả năng mã JavaScript lấy trực tiếp bearer token từ cookie. Điều này đặc biệt hữu ích khi ứng dụng có lỗ hổng Cross-Site Scripting (XSS).

### 3.2. HttpOnly không ngăn XSS thực hiện hành động

HttpOnly **không loại bỏ XSS** và không ngăn mã độc đang chạy trong origin của ứng dụng gửi request tới server. Trình duyệt vẫn tự động đính kèm cookie phù hợp, kể cả khi request được khởi tạo bởi JavaScript cùng origin.

Nếu attacker thực thi JavaScript trong trang:

- Có thể không đọc trực tiếp được cookie HttpOnly.
- Vẫn có thể gọi API dưới danh nghĩa người dùng trong trình duyệt bị xâm nhập.
- Có thể đọc dữ liệu API trả về mà trang hiện tại có quyền truy cập.
- Có thể thực hiện thao tác người dùng được phép nếu API thiếu biện pháp bảo vệ bổ sung.

HttpOnly giúp hạn chế đánh cắp token trực tiếp, nhưng vẫn cần chống XSS bằng output encoding, sanitization phù hợp, Content Security Policy và kiểm soát nguồn script.

### 3.3. HttpOnly không chống CSRF

CSRF khai thác việc trình duyệt tự gửi cookie, không cần attacker đọc giá trị cookie. Một trang bên ngoài có thể tìm cách khiến trình duyệt nạn nhân gửi request tới ứng dụng đang đăng nhập; cookie phù hợp có thể được đính kèm tự động.

Vì vậy, cookie JWT nên kết hợp SameSite phù hợp và cơ chế chống CSRF cho thao tác thay đổi trạng thái. Không xem HttpOnly là biện pháp chống CSRF.

### 3.4. Khi nào dùng HttpOnly?

Đối với cookie chứa access token hoặc refresh token dùng để xác thực, thông thường nên bật HttpOnly. Nếu frontend cần đọc token bằng JavaScript để tự đặt header Authorization, cookie HttpOnly không phù hợp với cách sử dụng đó; cần cân nhắc lại kiến trúc lưu trữ và mô hình rủi ro thay vì tắt HttpOnly mặc định.

## 4. Secure: chỉ gửi cookie qua kênh an toàn

### 4.1. Ý nghĩa của Secure

Cookie có thuộc tính `Secure` chỉ được trình duyệt gửi qua kênh được coi là an toàn, thông thường là HTTPS:

~~~http
Set-Cookie: __Host-access_token=<JWT>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Điều này giảm nguy cơ token bị truyền dưới dạng rõ qua HTTP. Với cookie xác thực, production nên dùng HTTPS xuyên suốt, bao gồm kết nối giữa proxy và ứng dụng theo threat model.

### 4.2. Secure không mã hóa cookie trong mọi nơi lưu trữ

Secure kiểm soát điều kiện truyền từ trình duyệt, không phải cơ chế mã hóa giá trị cookie tại mọi lớp:

- Không biến JWT thành dữ liệu bí mật trong trình duyệt.
- Không ngăn người có quyền truy cập thiết bị hoặc profile trình duyệt đọc dữ liệu lưu trữ bằng công cụ phù hợp.
- Không bảo vệ token nếu server ghi nó vào log.
- Không thay thế TLS, quản lý khóa hoặc chữ ký JWT.

JWT dạng JWS vẫn có thể được giải mã payload vì Base64URL không phải mã hóa. Không đưa mật khẩu, khóa bí mật hoặc dữ liệu nhạy cảm không cần thiết vào claims.

### 4.3. Không dùng cookie xác thực qua HTTP

Không cấu hình cookie xác thực thiếu Secure trong production chỉ để hỗ trợ HTTP. Hãy chuyển hướng HTTP sang HTTPS ở biên, bật HSTS phù hợp và bảo đảm cookie xác thực chỉ được thiết lập qua kết nối an toàn.

Trong local development, hành vi đặc biệt của trình duyệt với localhost có thể khác production. Không suy ra từ việc cookie hoạt động trên localhost rằng production có thể bỏ Secure.

### 4.4. Secure và reverse proxy

Nếu TLS kết thúc ở reverse proxy/load balancer, cần bảo đảm:

- Trình duyệt kết nối HTTPS tới proxy.
- Proxy chuyển tiếp tới upstream qua kênh được bảo vệ phù hợp với threat model.
- Ứng dụng chỉ tin header báo scheme/HTTPS từ proxy đáng tin cậy.
- Client không thể giả mạo forwarded header khiến ứng dụng phát hành cookie không Secure.
- Kiểm thử header Set-Cookie thực tế mà trình duyệt nhận được.

## 5. SameSite: kiểm soát cookie trong ngữ cảnh cross-site

### 5.1. SameSite kiểm soát điều gì?

`SameSite` cho biết trình duyệt có gửi cookie khi request được khởi tạo từ ngữ cảnh site khác hay không. Thuộc tính này là một lớp giảm thiểu CSRF vì attacker ở site khác thường không thể khiến trình duyệt gửi cookie trong mọi loại request.

Ba giá trị phổ biến:

- `Strict`: chỉ gửi cookie trong ngữ cảnh same-site theo quy tắc trình duyệt.
- `Lax`: cho phép một số điều hướng top-level cross-site an toàn; hạn chế cookie trong nhiều request cross-site khác.
- `None`: cho phép cookie được gửi trong ngữ cảnh cross-site; trình duyệt hiện đại yêu cầu kèm `Secure`.

### 5.2. So sánh Strict, Lax và None

| Giá trị | Same-site request | Cross-site top-level navigation | Cross-site subresource/XHR/fetch | Yêu cầu Secure |
| --- | --- | --- | --- | --- |
| Strict | Gửi nếu các điều kiện cookie khác đạt | Thông thường không gửi trong lần điều hướng từ site khác | Không gửi | Không bắt buộc bởi giá trị này; cookie xác thực production vẫn nên Secure |
| Lax | Gửi nếu các điều kiện khác đạt | Có thể gửi với phương thức an toàn theo quy tắc Lax | Thông thường không gửi | Không bắt buộc bởi giá trị này |
| None | Gửi nếu các điều kiện khác đạt | Có thể gửi | Có thể gửi | Bắt buộc trong trình duyệt hiện đại |

Quy tắc cụ thể phụ thuộc chuẩn và triển khai trình duyệt. Hành vi mặc định khi không khai báo SameSite và các ngoại lệ tương thích của một số trình duyệt không nên được dùng làm chính sách ứng dụng. Hãy khai báo rõ giá trị cần dùng.

### 5.3. SameSite Strict

Strict hạn chế tối đa việc gửi cookie khi người dùng đi từ một site khác sang ứng dụng. Ví dụ, người dùng bấm liên kết từ trang tìm kiếm tới ứng dụng; cookie Strict có thể không được gửi trong request điều hướng ban đầu.

Điều này có thể ảnh hưởng:

- Luồng đăng nhập qua identity provider.
- Callback hoặc redirect từ hệ thống bên ngoài.
- Liên kết email mở tới trang cần trạng thái đăng nhập.
- Các trải nghiệm điều hướng cross-site.

Strict phù hợp khi yêu cầu hạn chế cross-site rất cao và ứng dụng chấp nhận ảnh hưởng UX/tích hợp, hoặc cookie chỉ dùng cho luồng same-site.

### 5.4. SameSite Lax

Lax thường là lựa chọn cân bằng cho cookie phiên hoặc cookie xác thực của ứng dụng web first-party. Cookie được gửi trong ngữ cảnh same-site và một số điều hướng top-level cross-site dùng phương thức an toàn, nhưng thường không gửi trong iframe, subresource hoặc request fetch cross-site.

Không dựa vào Lax như biện pháp CSRF duy nhất cho mọi endpoint. Thao tác thay đổi trạng thái phải dùng phương thức HTTP phù hợp và có biện pháp CSRF bổ sung theo threat model.

Một số trình duyệt có hành vi mặc định Lax khi cookie không khai báo SameSite và có thể có ngoại lệ tương thích. Ứng dụng nên đặt `SameSite=Lax` tường minh thay vì phụ thuộc mặc định.

### 5.5. SameSite None

None cho phép cookie được gửi trong ngữ cảnh cross-site nếu các điều kiện khác đạt. Đây có thể là yêu cầu của ứng dụng được nhúng trong iframe trên site khác, một số kiến trúc đăng nhập liên miền hoặc tích hợp cần cookie trong request cross-site.

~~~http
Set-Cookie: __Secure-session=<value>; Path=/; Secure; HttpOnly; SameSite=None
~~~

Trình duyệt hiện đại yêu cầu cookie SameSite=None phải có Secure. Một số trình duyệt hoặc chế độ riêng tư có thể chặn cookie bên thứ ba theo chính sách riêng; SameSite=None không bảo đảm cookie bên thứ ba luôn được lưu hoặc gửi.

Khi chọn None, cần đánh giá CSRF nghiêm ngặt hơn và bổ sung token chống CSRF, kiểm tra Origin/Referer hoặc biện pháp phù hợp khác.

### 5.6. Same-site không đồng nghĩa same-origin

Origin gồm scheme, host và port. Site được xác định theo quy tắc schemeful site và miền đăng ký (registrable domain) của trình duyệt. Hai subdomain như `app.example.com` và `api.example.com` có thể là same-site nhưng vẫn là hai origin khác nhau.

Điều này quan trọng vì:

- SameSite có thể cho phép cookie trong request giữa các subdomain cùng site.
- Chính sách same-origin/CORS vẫn áp dụng riêng theo origin.
- Một subdomain bị kiểm soát hoặc bị chiếm quyền có thể tạo rủi ro cho subdomain khác nếu cookie được chia sẻ qua Domain.

Không coi SameSite là ranh giới cô lập giữa các subdomain thuộc cùng site.

## 6. Domain: cookie được gửi tới host nào?

### 6.1. Host-only cookie khi không khai báo Domain

Nếu server không đặt thuộc tính `Domain`, trình duyệt tạo **host-only cookie**. Cookie chỉ được gửi tới đúng host đã thiết lập nó.

~~~http
Set-Cookie: __Host-session=<value>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Cookie host-only được gửi tới host đã thiết lập, ví dụ `app.example.com`, không tự động gửi tới `api.example.com` hoặc `admin.example.com`.

Đây thường là lựa chọn an toàn hơn vì giảm số host có thể nhận cookie. Nếu không có yêu cầu chia sẻ cookie giữa subdomain, hãy bỏ thuộc tính Domain.

### 6.2. Domain cookie chia sẻ cho subdomain

Nếu đặt `Domain=example.com`, cookie có thể được gửi tới domain đó và các subdomain phù hợp:

~~~http
Set-Cookie: shared-session=<value>; Domain=example.com; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Cookie có thể được gửi tới `example.com`, `app.example.com`, `api.example.com` và `admin.example.com`. Nó không được gửi tới domain không khớp như `example.net` hoặc một domain cha không hợp lệ.

### 6.3. Rủi ro khi mở rộng Domain

Chia sẻ cookie trên toàn bộ subdomain làm tăng phạm vi tin cậy. Nếu một subdomain có lỗ hổng, bị chiếm quyền DNS, có nội dung do người dùng kiểm soát hoặc có ứng dụng bảo mật yếu, cookie domain-wide có thể làm tăng tác động.

Các rủi ro gồm:

- Cookie được gửi tới nhiều host hơn nhu cầu thực tế.
- Subdomain không tin cậy có thể nhận cookie domain-wide qua request.
- Subdomain có thể cố thiết lập cookie cùng tên ở phạm vi domain/host khác, gây cookie tossing hoặc va chạm tên.
- Một subdomain bị chiếm quyền có thể ảnh hưởng luồng đăng nhập hoặc phiên của ứng dụng khác.

Không đặt `Domain=.example.com` với hy vọng tạo thêm bảo vệ. Dấu chấm đầu không tạo cơ chế bảo mật riêng; trình duyệt hiện đại xử lý giá trị domain theo quy tắc chuẩn hóa và domain-match.

### 6.4. Giới hạn của Domain

Trình duyệt không cho một host tùy ý đặt cookie cho domain không phải domain cha phù hợp của nó. Cookie cũng không được đặt cho public suffix như `com` hoặc public suffix khác theo danh sách của trình duyệt.

Thuộc tính Domain không giới hạn theo port. Các ứng dụng trên những port khác nhau của cùng host có thể chia sẻ cookie phù hợp; không dùng port để tạo ranh giới bảo mật cookie.

### 6.5. Khi nào cần Domain?

Chỉ dùng Domain khi có yêu cầu cụ thể để chia sẻ cookie giữa các subdomain và đã đánh giá mọi host nhận cookie. Nếu nhiều ứng dụng cần cùng trạng thái đăng nhập, cân nhắc luồng SSO/redirect qua identity provider thay vì mở rộng một cookie nhạy cảm cho toàn bộ domain.

## 7. Path: cookie được gửi tới đường dẫn nào?

### 7.1. Path matching

Thuộc tính `Path` giới hạn các đường dẫn request mà trình duyệt gửi cookie:

~~~http
Set-Cookie: access_token=<JWT>; Path=/api/; Secure; HttpOnly; SameSite=Lax
~~~

Cookie có thể được gửi tới các path phù hợp như `/api/profile` hoặc `/api/orders`, nhưng không được gửi tới path không khớp như `/admin`.

Nếu không chỉ định Path, trình duyệt xác định default-path từ đường dẫn request đã tạo cookie. Vì vậy, nên khai báo Path tường minh để tránh phạm vi phụ thuộc ngữ cảnh tạo cookie.

### 7.2. Path không phải ranh giới bảo mật

Không dùng Path để cô lập các ứng dụng hoặc ngăn một script cùng origin truy cập tài nguyên khác:

- Path không phải cơ chế same-origin isolation.
- JavaScript trong cùng origin có thể truy cập tài nguyên ở path khác; Path chủ yếu kiểm soát việc gửi cookie.
- Một ứng dụng khác cùng host không nên được coi là an toàn chỉ vì cookie có Path riêng.
- Server vẫn phải xác minh và phân quyền cho từng endpoint.

RFC cookie cảnh báo Path không phải biện pháp bảo mật đáng tin cậy để cô lập cookie. Nếu cần cách ly ứng dụng, dùng host/origin riêng và cookie host-only phù hợp.

### 7.3. Chọn Path như thế nào?

Với cookie phiên toàn ứng dụng, `Path=/` thường phù hợp. Với cookie chỉ dùng cho một khu vực, có thể giới hạn Path để giảm việc trình duyệt gửi cookie tới endpoint không cần nó, nhưng không dựa vào đó như biện pháp bảo mật duy nhất.

Tiền tố `__Host-` bắt buộc Path=/, nên không thể kết hợp với Path hẹp. Đây là đánh đổi có chủ đích để tăng bảo đảm host-only.

## 8. Cookie prefixes: __Host- và __Secure-

### 8.1. Tiền tố __Secure-

Cookie có tên bắt đầu bằng `__Secure-` phải được thiết lập từ ngữ cảnh an toàn và có thuộc tính Secure theo quy tắc prefix của trình duyệt hỗ trợ:

~~~http
Set-Cookie: __Secure-session=<value>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Prefix giúp trình duyệt áp dụng thêm điều kiện khi chấp nhận cookie. Nó không tự yêu cầu host-only và vẫn có thể dùng Domain nếu cấu hình cho phép.

### 8.2. Tiền tố __Host-

Cookie `__Host-` phải đáp ứng các điều kiện:

- Có thuộc tính `Secure`.
- Có `Path=/`.
- Không có thuộc tính `Domain`.
- Được thiết lập từ secure origin theo quy tắc cookie prefix.

Ví dụ:

~~~http
Set-Cookie: __Host-access_token=<JWT>; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=900
~~~

Prefix này giúp ngăn cookie bị thiết lập từ subdomain với Domain rộng hoặc Path khác trong các trình duyệt thực thi prefix. Đây là lựa chọn mạnh cho cookie xác thực host-only nếu ứng dụng chấp nhận Path=/.

### 8.3. Prefix không thay thế policy

Prefix chỉ là một lớp kiểm tra bổ sung ở trình duyệt hỗ trợ. Server vẫn phải xác minh JWT, kiểm tra issuer/audience/expiry/token type, áp dụng CSRF protection và kiểm soát nguồn phát hành cookie. Không dựa vào tên cookie để kết luận giá trị đáng tin.

## 9. Kết hợp các thuộc tính cho JWT

### 9.1. Cookie first-party cho ứng dụng web

Một cấu hình thường gặp cho access token ngắn hạn:

~~~http
Set-Cookie: __Host-access_token=<JWT>; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=900
~~~

Ý nghĩa:

- __Host-: yêu cầu Secure, host-only và Path=/.
- HttpOnly: JavaScript không đọc trực tiếp cookie.
- Secure: trình duyệt chỉ gửi qua kênh an toàn.
- SameSite=Lax: hạn chế nhiều request cross-site nhưng vẫn hỗ trợ một số điều hướng top-level.
- Max-Age=900: trình duyệt giữ cookie tối đa 15 phút kể từ lúc nhận, trừ khi bị xóa hoặc thay thế.

Đây là ví dụ định hướng, không phải cấu hình phù hợp cho mọi luồng đăng nhập. Cần kiểm tra callback, SSO, cross-site navigation và chính sách CSRF thực tế.

### 9.2. Cookie cần gửi cross-site

Nếu kiến trúc thực sự cần cookie trong request cross-site:

~~~http
Set-Cookie: __Secure-session=<value>; Path=/; Secure; HttpOnly; SameSite=None
~~~

Ví dụ dùng `__Secure-` để thể hiện cookie Secure nhưng vẫn cho phép Domain nếu cần. Trình duyệt có thể chặn third-party cookie theo chính sách quyền riêng tư, vì vậy phải kiểm thử trên các trình duyệt và chế độ mà sản phẩm hỗ trợ.

SameSite=None yêu cầu biện pháp CSRF rõ ràng, chẳng hạn synchronizer token hoặc double-submit cookie được triển khai đúng cách, kết hợp kiểm tra Origin/Referer khi phù hợp và không cho phép state-changing request bằng GET.

### 9.3. Access token và refresh token

Nếu lưu access token và refresh token trong cookie:

- Dùng tên cookie khác nhau.
- Cân nhắc host-only và Path phù hợp với endpoint cần nhận từng token.
- Refresh token thường có thời hạn dài hơn và quyền nhạy cảm hơn; cần rotation, reuse detection và thu hồi theo thiết kế.
- Không để refresh token được gửi tới mọi endpoint nếu không cần.
- Không coi Path là biện pháp cô lập bảo mật; endpoint vẫn phải kiểm tra đúng loại token.
- Xóa cookie khi logout hoặc thu hồi phiên, với Domain/Path khớp cookie đã tạo.

Ví dụ minh họa:

~~~http
Set-Cookie: __Host-access=<access-jwt>; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=900
Set-Cookie: refresh_token=<refresh-jwt>; Path=/auth/refresh; Secure; HttpOnly; SameSite=Strict; Max-Age=2592000
~~~

Cookie refresh ở ví dụ có Path hẹp và không có Domain, nhưng không có prefix __Host- vì Path không phải /. Nếu cần prefix __Host-, phải dùng Path=/; khi đó endpoint server vẫn phải giới hạn nơi chấp nhận refresh token. Lựa chọn SameSite cần phù hợp với luồng đăng nhập/refresh thực tế.

## 10. Cookie và CSRF

### 10.1. Vì sao cookie tạo ra nguy cơ CSRF?

Trình duyệt tự động đính kèm cookie khi request phù hợp. Attacker không cần biết JWT để khiến browser gửi request. Nếu server chỉ dựa vào cookie để xác thực và không kiểm tra nguồn request, attacker có thể tìm cách kích hoạt thao tác dưới danh nghĩa nạn nhân.

Ví dụ endpoint thay đổi email nhận request POST. Nếu trình duyệt gửi cookie phiên cùng request cross-site và server không có CSRF protection, hành động có thể được thực hiện dù attacker không đọc được phản hồi.

### 10.2. SameSite là lớp bảo vệ, không phải toàn bộ giải pháp

SameSite giảm một số dạng CSRF, nhưng không nên là cơ chế duy nhất vì có luồng same-site giữa các subdomain khác origin, cookie None được gửi cross-site, một số luồng nghiệp vụ cần redirect/callback, và XSS cùng origin vẫn có thể gửi request với cookie.

### 10.3. Biện pháp bổ sung

Tùy kiến trúc, kết hợp:

1. CSRF synchronizer token gắn với phiên.
2. Double-submit cookie được thiết kế chống cookie injection, thường dùng biến thể signed hoặc bound-to-session.
3. Kiểm tra Origin và/hoặc Referer cho state-changing request.
4. Fetch Metadata headers như `Sec-Fetch-Site` để bổ sung tín hiệu.
5. Không dùng GET cho thao tác thay đổi trạng thái.
6. SameSite phù hợp với nhu cầu nghiệp vụ.
7. Xác thực lại hoặc xác nhận bổ sung cho hành động nhạy cảm.

Không xem CORS là biện pháp chống CSRF hoàn chỉnh. CORS chủ yếu kiểm soát việc JavaScript đọc phản hồi cross-origin; nó không tự ngăn mọi request cross-site được gửi.

## 11. Vòng đời cookie: tạo, gia hạn và xóa

### 11.1. Max-Age và Expires

Hai thuộc tính thời hạn phổ biến:

- `Max-Age`: thời lượng cookie tồn tại tính bằng giây.
- `Expires`: thời điểm hết hạn theo ngày giờ HTTP.

Nếu cả hai cùng xuất hiện, `Max-Age` có mức ưu tiên theo quy tắc cookie hiện đại:

~~~http
Set-Cookie: __Host-access=<JWT>; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=900; Expires=Wed, 16 Dec 2026 10:00:00 GMT
~~~

Không dùng thời hạn cookie dài hơn thời hạn JWT một cách vô tình. Dù cookie còn được trình duyệt lưu, server vẫn phải từ chối JWT hết hạn.

### 11.2. Xóa cookie

Để xóa cookie, server gửi lại cookie cùng tên và cùng phạm vi Domain/Path, với thời hạn đã hết:

~~~http
Set-Cookie: __Host-access=; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=0
~~~

Nếu cookie ban đầu có Domain hoặc Path khác, cần gửi lệnh xóa khớp phạm vi đó. Cookie cùng tên nhưng khác Path hoặc Domain có thể vẫn còn tồn tại.

### 11.3. Cookie trùng tên

Trình duyệt có thể lưu nhiều cookie cùng tên với các Path hoặc Domain khác nhau. Header Cookie có thể chứa nhiều cặp trùng tên; thứ tự gửi không nên được dùng làm cơ chế lựa chọn bảo mật.

Server cần tránh cấu hình cookie trùng tên ở nhiều phạm vi. Nếu nhận được tên cookie trùng lặp mà parser không thể xử lý rõ ràng, nên từ chối xác thực thay vì tùy tiện chọn giá trị đầu tiên hoặc cuối cùng.

## 12. Kích thước cookie và vận chuyển JWT

### 12.1. JWT có thể làm cookie lớn

JWT gồm header, payload và chữ ký; khi đưa vào cookie, giá trị được gửi trong header Cookie của mỗi request phù hợp. Cookie quá lớn có thể vượt giới hạn lưu trữ trình duyệt, làm tăng request header, bị proxy/CDN/server từ chối hoặc làm tăng băng thông vì token được gửi lặp lại.

Giới hạn kích thước cookie khác nhau theo trình duyệt và hạ tầng. Không dựa vào một con số cố định; hãy kiểm thử end-to-end và giữ JWT nhỏ.

### 12.2. Không lưu quá nhiều dữ liệu trong JWT

Chỉ đưa claims cần thiết cho việc xác minh và quyết định truy cập. Tránh nhúng hồ sơ người dùng, dữ liệu lớn, dữ liệu bí mật hoặc danh sách quyền quá dài.

Nếu JWT lớn do chứa nhiều claims, cân nhắc token tham chiếu/introspection hoặc lưu trạng thái phiên phía server thay vì cố tăng giới hạn cookie.

### 12.3. Header Cookie không mang thuộc tính

Khi browser gửi request, server nhận header dạng:

~~~http
Cookie: __Host-access=<JWT>; preference=compact
~~~

Server không thể suy ra từ header này rằng cookie ban đầu có HttpOnly, Secure, SameSite, Domain hoặc Path. Những thuộc tính đó không được gửi trong request. Vì vậy phải cấu hình chúng ở nơi phát hành cookie và kiểm tra header Set-Cookie tại trình duyệt khi cần chẩn đoán.

## 13. Quy trình lựa chọn cookie attributes

### 13.1. Câu hỏi thiết kế

Trước khi phát hành JWT trong cookie, trả lời:

1. Cookie chỉ cần cho một host hay phải chia sẻ giữa subdomain?
2. Có thực sự cần cookie trong ngữ cảnh cross-site không?
3. Frontend có cần đọc trực tiếp token bằng JavaScript không?
4. Cookie áp dụng cho toàn ứng dụng hay chỉ một nhóm endpoint?
5. Có cơ chế CSRF nào đang được sử dụng?
6. Token có ngắn và nhỏ đủ để truyền trong request header không?
7. Có rotation, logout, revocation và xóa cookie đúng phạm vi không?

### 13.2. Cây quyết định

~~~mermaid
flowchart TD
    A[Chọn cách lưu JWT bằng cookie] --> B{JavaScript có cần đọc token?}
    B -->|Không| C[Đặt HttpOnly]
    B -->|Có| D[Đánh giá lại kiến trúc và XSS exposure]
    C --> E{Cookie chỉ dùng trên một host?}
    E -->|Có| F[Host-only, bỏ Domain; cân nhắc __Host-]
    E -->|Không| G[Đặt Domain hẹp nhất cần thiết và đánh giá subdomain]
    F --> H{Có cần gửi cross-site?}
    G --> H
    H -->|Không| I[Chọn Strict hoặc Lax]
    H -->|Có| J[SameSite=None; Secure và CSRF protection]
    I --> K[Chọn Path và thời hạn]
    J --> K
    K --> L[Kiểm thử browser, gateway và verifier]
~~~

### 13.3. Cấu hình tham khảo

| Nhu cầu | Cấu hình thường cân nhắc | Điều kiện cần kiểm tra |
| --- | --- | --- |
| Ứng dụng first-party, một host | Host-only, HttpOnly, Secure, SameSite=Lax, Path=/ | CSRF cho state-changing request |
| Yêu cầu hạn chế cross-site mạnh | SameSite=Strict | Có chấp nhận ảnh hưởng redirect/SSO không |
| Cookie cần cross-site | SameSite=None; Secure; HttpOnly | CSRF, third-party cookie policy và browser support |
| Cookie xác thực host-only mạnh | Prefix __Host-, Secure, HttpOnly, Path=/, không Domain | Path phải là / |
| Cookie chỉ cần cho một endpoint | Path hẹp hơn nếu hữu ích | Path không phải ranh giới bảo mật |
| Chia sẻ cookie subdomain | Domain=parent domain | Tất cả subdomain đều thuộc trust boundary phù hợp |

## 14. Ví dụ hoàn chỉnh và phân tích

### 14.1. Cookie access token first-party

~~~http
HTTP/1.1 200 OK
Set-Cookie: __Host-access_token=<JWT>; Path=/; Secure; HttpOnly; SameSite=Lax; Max-Age=900
Cache-Control: no-store
Content-Type: application/json

{"authenticated":true}
~~~

Phân tích:

- Cookie host-only, không chia sẻ sang subdomain.
- JavaScript không đọc trực tiếp JWT.
- Browser chỉ gửi cookie qua kênh an toàn.
- Lax giảm nhiều tình huống gửi cookie cross-site.
- Thời hạn cookie 15 phút; JWT vẫn phải có `exp` và server phải kiểm tra.
- Cache-Control no-store giúp tránh lưu phản hồi chứa dữ liệu nhạy cảm theo cách không cần thiết; đây là chính sách cache phản hồi, không thay thế cookie flags.

### 14.2. Cookie cho luồng cross-site

~~~http
HTTP/1.1 200 OK
Set-Cookie: __Secure-sso_state=<opaque-value>; Path=/; Secure; HttpOnly; SameSite=None; Max-Age=300
Cache-Control: no-store
~~~

Ví dụ này minh họa cookie cần được gửi trong luồng cross-site. Giá trị `sso_state` có thể là trạng thái ngẫu nhiên ràng buộc với giao dịch đăng nhập, không nhất thiết là JWT. Khi dùng None, phải có CSRF/state/nonce validation phù hợp và kiểm tra chính sách third-party cookie của trình duyệt.

### 14.3. Cookie domain-wide

~~~http
Set-Cookie: shared_session=<value>; Domain=example.com; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Cookie này được mở rộng tới các subdomain phù hợp. Trước khi dùng, phải xác nhận mọi host nhận cookie đều nằm trong cùng ranh giới tin cậy. Nếu chỉ một ứng dụng cần cookie, bỏ Domain để tạo host-only cookie.

## 15. Những hiểu lầm phổ biến

**“HttpOnly ngăn XSS.”** Sai. Nó hạn chế JavaScript đọc cookie, nhưng XSS vẫn có thể gửi request dưới danh nghĩa người dùng.

**“Secure mã hóa JWT trong cookie.”** Sai. Secure kiểm soát việc gửi cookie qua kênh an toàn; nó không mã hóa payload JWT hay dữ liệu lưu trữ ở mọi nơi.

**“SameSite=Lax loại bỏ hoàn toàn CSRF.”** Sai. Nó giảm nhiều request cross-site nhưng không thay thế CSRF protection cho mọi ứng dụng và luồng.

**“Same-site nghĩa là same-origin.”** Sai. Hai subdomain có thể same-site nhưng khác origin.

**“Domain càng rộng càng tiện và không ảnh hưởng bảo mật.”** Sai. Cookie được gửi tới nhiều subdomain hơn, mở rộng phạm vi tin cậy.

**“Path=/admin ngăn script ở path khác dùng cookie.”** Sai. Path chủ yếu kiểm soát việc browser gửi cookie, không tạo ranh giới bảo mật giữa các path.

**“Cookie có HttpOnly thì server có thể tin giá trị.”** Sai. Client vẫn có thể gửi cookie cũ, giả mạo hoặc bị sửa; JWT vẫn phải được xác minh.

**“SameSite=None có thể dùng mà không cần Secure.”** Sai trong các trình duyệt hiện đại; None yêu cầu Secure.

**“Cookie hết hạn thì JWT chắc chắn hết hạn.”** Sai. Cookie lifetime và JWT `exp` là hai cơ chế độc lập; server luôn phải kiểm tra `exp`.

## 16. Câu hỏi tự kiểm tra

1. HttpOnly ngăn được điều gì và không ngăn được điều gì khi trang có XSS?
2. Secure kiểm soát việc truyền cookie như thế nào? Vì sao nó không phải mã hóa JWT?
3. SameSite Strict, Lax và None khác nhau ra sao?
4. Vì sao SameSite=None cần Secure?
5. Phân biệt same-site và same-origin bằng ví dụ hai subdomain.
6. Bỏ thuộc tính Domain tạo ra loại cookie nào? Cookie đó được gửi tới host nào?
7. Domain=example.com mở rộng phạm vi cookie tới những host nào và tạo ra rủi ro gì?
8. Vì sao Path không phải cơ chế cô lập bảo mật?
9. Prefix __Host- yêu cầu những điều kiện nào?
10. Vì sao cookie JWT cần CSRF protection dù đã có HttpOnly và SameSite=Lax?
11. Khi xóa cookie, vì sao cần khớp Domain và Path ban đầu?
12. Server có thể biết cookie ban đầu có HttpOnly hoặc SameSite chỉ từ request Cookie header không?

## 17. Tiêu chuẩn và tài liệu tham khảo

- [RFC 6265 — HTTP State Management Mechanism](https://www.rfc-editor.org/rfc/rfc6265), cookie, Domain, Path, Secure, HttpOnly và vòng đời cookie.
- [RFC 6265bis — Cookies: HTTP State Management Mechanism (Internet-Draft)](https://datatracker.ietf.org/doc/draft-ietf-httpbis-rfc6265bis/), các cập nhật hiện đại về SameSite, cookie prefixes và xử lý cookie.
- [MDN — Set-Cookie](https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Set-Cookie), tham khảo cách trình duyệt xử lý thuộc tính cookie.
- [OWASP Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html), biện pháp chống CSRF và giới hạn của SameSite.
- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html), quản lý cookie phiên và thuộc tính bảo mật.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725), xác minh JWT và các rủi ro trong quá trình sử dụng token.
