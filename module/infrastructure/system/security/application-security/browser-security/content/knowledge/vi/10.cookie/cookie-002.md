# Cookie scope: phạm vi host, domain, path và ngữ cảnh gửi cookie

## 1. Cookie scope là gì?

**Cookie scope** là tập hợp quy tắc quyết định một cookie được lưu, được gửi kèm request nào và được JavaScript nào truy cập. Khi server gửi một header Set-Cookie, trình duyệt không chỉ lưu chuỗi name/value. Nó còn áp dụng các thuộc tính về host/domain, path, secure transport, quyền truy cập từ JavaScript, ngữ cảnh same-site và thời hạn. Những thuộc tính này xác định **cookie nào phù hợp với request hiện tại**.

Cookie là cơ chế trạng thái lâu đời của web, thường dùng cho session, tùy chọn giao diện, giỏ hàng và các định danh khác. Cookie được trình duyệt tự động đính kèm vào những request phù hợp, vì vậy phạm vi cookie ảnh hưởng trực tiếp đến bảo mật phiên và CSRF.

Bài học thuộc chương **Cookie** của module **SECURITY_APPLICATION_SECURITY_BROWSER_SECURITY**. Nội dung tập trung vào cách trình duyệt xác định cookie thuộc host nào, path nào, khi nào gửi cookie và các giới hạn của từng thuộc tính. Mục tiêu là thiết kế cookie phiên đủ hẹp, hiểu đúng sự khác nhau giữa cookie scope với origin/SOP, và tránh xem Domain, Path, SameSite hay HttpOnly như một cơ chế phân quyền hoàn chỉnh.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Phân biệt cookie **host-only** với cookie có thuộc tính **Domain**.
2. Giải thích cách **Path** xác định request path phù hợp và vì sao Path không phải ranh giới bảo mật mạnh.
3. Hiểu cookie không được cách ly theo port giống origin-based storage.
4. Phân biệt **Secure**, **HttpOnly**, **SameSite** và các thuộc tính về scope.
5. Hiểu prefix **__Host-**, **__Secure-** và cookie partitioned.
6. Phân tích cookie trùng tên, domain rộng, subdomain không tin cậy và cookie tossing.
7. Liên hệ cookie scope với SOP, CORS, authentication, authorization và CSRF.
8. Kiểm chứng hành vi qua DevTools, request headers và response Set-Cookie.

## 2. Cookie được lưu và gửi như thế nào?

Server tạo cookie bằng response header Set-Cookie:

~~~http
HTTP/1.1 200 OK
Set-Cookie: session=opaque-value; Path=/; Secure; HttpOnly; SameSite=Lax
Content-Type: text/html
~~~

Browser nhận header, kiểm tra cú pháp và chính sách cookie, rồi lưu cookie nếu hợp lệ. Ở request phù hợp sau đó, browser gửi các cặp name/value trong request header Cookie:

~~~http
GET /account HTTP/1.1
Host: app.example.test
Cookie: session=opaque-value
~~~

Điểm quan trọng:

- **Set-Cookie** dùng để thiết lập cookie.
- **Cookie** dùng để gửi những cookie phù hợp.
- Request header Cookie chỉ chứa các cặp name/value, không gửi lại Domain, Path, Secure, HttpOnly hoặc SameSite.
- Cookie không tự chứng minh user có quyền thực hiện hành động. Backend phải xác minh session và phân quyền.
- Browser quyết định cookie nào phù hợp theo URL, ngữ cảnh và chính sách của nó; client không nên tự dựng header Cookie bằng JavaScript.

## 3. Host-only cookie và Domain cookie

Đây là khác biệt nền tảng của cookie scope.

### 3.1. Host-only cookie: mặc định hẹp theo host đã tạo

Nếu Set-Cookie **không có thuộc tính Domain**, cookie là host-only cookie. Browser gửi nó tới đúng host đã đặt cookie, không tự mở rộng tới subdomain.

Ví dụ response từ https://app.example.test:

~~~http
Set-Cookie: app_session=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Cookie này phù hợp với request tới app.example.test. Nó không được gửi tới api.example.test hoặc admin.example.test chỉ vì chúng cùng registrable domain.

Host-only thường là lựa chọn tốt cho session cookie vì giảm phạm vi chia sẻ giữa các subdomain.

### 3.2. Domain cookie: mở rộng tới domain và subdomain phù hợp

Nếu server chỉ định Domain, cookie có thể được gửi tới domain đó và các subdomain phù hợp theo quy tắc domain-match.

~~~http
Set-Cookie: shared_pref=dark; Domain=example.test; Path=/; Secure; SameSite=Lax
~~~

Cookie có thể được gửi tới:

- example.test
- app.example.test
- api.example.test
- admin.example.test

Cookie không được gửi tới domain không khớp như example.test.attacker.test hoặc một domain khác.

Nếu chỉ muốn host app.example.test, không đặt Domain=example.test. Bỏ thuộc tính Domain để tạo host-only cookie.

### 3.3. Dấu chấm đầu Domain không mở rộng thêm quyền

Các dạng Domain=example.test và Domain=.example.test được browser hiện đại xử lý tương đương về domain matching; dấu chấm đầu không còn mang ý nghĩa tạo một phạm vi riêng. Không dựa vào dấu chấm để phân biệt cookie host-only với domain cookie. Điểm quyết định là **có hay không thuộc tính Domain**.

### 3.4. Không thể đặt cookie cho public suffix

Một host không thể đặt cookie có Domain là public suffix như com hoặc co.uk để cookie lan ra toàn bộ những website dưới suffix đó. Browser dùng Public Suffix List và các quy tắc cookie để từ chối các Domain không hợp lệ như vậy.

Ví dụ một website ở shop.example.co.uk có thể đặt cookie cho example.co.uk nếu hợp lệ, nhưng không thể đặt cookie cho co.uk.

Không tự viết kiểm tra public suffix bằng cách lấy hai nhãn cuối của hostname; quy tắc public suffix có nhiều ngoại lệ và thay đổi theo danh sách.

### 3.5. Domain cookie làm tăng phạm vi tin cậy

Nếu app.example.test đặt:

~~~http
Set-Cookie: session=secret; Domain=example.test; Path=/; Secure; HttpOnly
~~~

thì những subdomain phù hợp có thể cùng nhận cookie. Nếu một subdomain cũ bị chiếm quyền, có XSS hoặc cho phép nội dung do khách hàng kiểm soát, cookie dùng chung có thể tăng mức độ ảnh hưởng.

Cookie HttpOnly không đọc được bằng document.cookie, nhưng browser vẫn có thể gửi cookie tự động tới subdomain khớp Domain. Vì vậy cần thận trọng khi mở rộng Domain của session cookie.

## 4. Path: cookie được gửi tới những đường dẫn nào?

Thuộc tính Path giới hạn các request path mà browser xem là phù hợp với cookie.

Ví dụ:

~~~http
Set-Cookie: admin_pref=compact; Path=/admin; Secure; HttpOnly
~~~

Cookie có thể phù hợp với:

- /admin
- /admin/
- /admin/users
- /admin/reports/2026

Nhưng không phù hợp với:

- /administrator
- /admin-panel
- /account

Path matching không đơn giản là mọi chuỗi bắt đầu bằng /admin: nếu cookie path không kết thúc bằng dấu slash, ký tự tiếp theo trong request path cần là dấu slash để tạo ranh giới segment.

### 4.1. Default Path khi không khai báo Path

Nếu server không gửi thuộc tính Path, browser tính default-path dựa trên request path đã tạo cookie. Thông thường đó là thư mục chứa request path, bỏ phần segment cuối cùng.

Ví dụ response phát sinh từ:

~~~text
https://app.example.test/account/settings
~~~

Nếu không có Path, default-path thường là:

~~~text
/account
~~~

Cookie có thể được gửi cho /account và các path con phù hợp. Đừng giả định default-path luôn là /; nếu cần cookie dùng toàn ứng dụng, đặt Path=/ tường minh.

### 4.2. Path không phải ranh giới bảo mật cho ứng dụng

Path=/admin không tạo origin riêng hoặc sandbox JavaScript. API document.cookie chỉ hiển thị cookie phù hợp với URL/path của tài liệu hiện tại; tuy nhiên, script cùng origin có thể điều hướng hoặc tạo một tài liệu/iframe tại path /admin rồi đọc document.cookie ở ngữ cảnh đó nếu cookie không có HttpOnly. Vì thế Path không phải ranh giới bảo mật mạnh để cô lập các ứng dụng cùng host. Ngoài ra, server nhận Cookie header thường chỉ thấy name/value, không biết cookie được đặt với Path nào.

Do đó:

- Không dùng Path để tách session giữa hai ứng dụng có mức tin cậy khác nhau.
- Không dựa vào Path để phân quyền route quản trị.
- Dùng host-only cookie hoặc origin riêng nếu cần cách ly host.
- Backend vẫn phải kiểm tra quyền cho từng endpoint.

## 5. Cookie không được cách ly theo port

Origin web thông thường gồm scheme + host + port. Cookie scope không có thuộc tính Port tương ứng.

Ví dụ hai dịch vụ:

~~~text
https://app.example.test:443
https://app.example.test:8443
~~~

Hai URL này khác origin do khác port. Tuy nhiên, cookie phù hợp với host app.example.test không được tách thành hai vùng riêng chỉ vì cổng khác nhau. Browser có thể gửi cookie phù hợp tới cả hai cổng theo các quy tắc cookie và transport liên quan.

Tương tự khi thử local:

~~~text
http://localhost:3000
http://localhost:4000
~~~

Hai ứng dụng khác origin vì khác port, nhưng cookie không dùng port làm tiêu chí cách ly. Điều này có thể gây bất ngờ khi một server local đặt cookie và server khác cùng host nhận được cookie đó.

| Cơ chế | Có tách theo port? | Phạm vi chính |
| --- | --- | --- |
| SOP / origin | Có | Scheme, host, port. |
| localStorage | Có, theo origin | Origin của tài liệu (cùng các chính sách partitioning). |
| Cookie | **Không** | Host/domain, path, Secure, SameSite, expiry và các thuộc tính liên quan. |
| Cookie Domain | Không | Domain-match tới host/subdomain phù hợp. |

Không dùng cookie như thể nó có thể cô lập hai dịch vụ chạy ở hai port. Nếu hai ứng dụng trên cùng host nhưng có mức tin cậy khác nhau, cân nhắc host riêng và kiểm soát phiên phù hợp.

## 6. Secure: giới hạn truyền cookie qua kết nối không an toàn

Thuộc tính Secure yêu cầu browser chỉ gửi cookie qua kênh an toàn theo quy tắc cookie, thường là HTTPS.

~~~http
Set-Cookie: session=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Secure giúp giảm nguy cơ cookie bị gửi qua HTTP không mã hóa. Nó không:

- Mã hóa cookie khi lưu trong browser hoặc server log.
- Chống XSS.
- Chống CSRF một mình.
- Xác minh user có quyền truy cập tài nguyên.
- Biến một endpoint HTTP thành endpoint an toàn.

Cookie Secure vẫn cần HTTPS cho toàn bộ ứng dụng và cấu hình TLS đúng. HSTS có thể bổ sung chính sách ép browser dùng HTTPS cho host, nhưng không thay thuộc tính Secure trên cookie.

Một số browser coi localhost là ngữ cảnh đáng tin cậy đặc biệt cho phát triển, vì vậy thử nghiệm Secure cookie trên localhost có thể khác với hostname HTTP thông thường. Không suy từ hành vi localhost để cấu hình production.

## 7. HttpOnly: giới hạn truy cập từ JavaScript

HttpOnly khiến cookie không được expose qua các API JavaScript như document.cookie. Browser vẫn quản lý cookie và có thể gửi nó trong request phù hợp.

Ví dụ:

~~~http
Set-Cookie: session=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Trong trang cùng host:

~~~js
console.log(document.cookie);
~~~

Cookie session có HttpOnly không xuất hiện trong kết quả. Nhưng request phù hợp vẫn có thể mang:

~~~http
Cookie: session=opaque
~~~

### 7.1. HttpOnly không vô hiệu hóa XSS

Nếu trang bị XSS, script độc vẫn có thể gọi API trong phiên đang đăng nhập vì browser tự đính kèm cookie theo chính sách. Script cũng có thể đọc nội dung response cùng origin, thay đổi DOM hoặc thực hiện hành động mà user có quyền làm.

Vì vậy HttpOnly là lớp giảm khả năng đánh cắp cookie bằng JavaScript, không phải giải pháp loại bỏ tác động của XSS. Cần chống XSS bằng xử lý dữ liệu/DOM an toàn, CSP, Trusted Types khi phù hợp và phân quyền backend.

### 7.2. Cookie HttpOnly vẫn có thể chịu CSRF

Browser tự gửi cookie phù hợp. Một trang ngoài có thể tìm cách tạo request tới ứng dụng. HttpOnly không ngăn browser gửi cookie; cần SameSite, CSRF token, kiểm tra nguồn request và bảo vệ backend theo threat model.

## 8. SameSite: cookie được gửi theo ngữ cảnh site

SameSite điều khiển việc browser có gửi cookie trong những ngữ cảnh **same-site** hoặc **cross-site** hay không. Nó không phải thuộc tính thay thế host/domain/path và cũng không đồng nghĩa same-origin.

### 8.1. SameSite=Strict

~~~http
Set-Cookie: session=opaque; Path=/; Secure; HttpOnly; SameSite=Strict
~~~

Strict giới hạn cookie trong các ngữ cảnh same-site theo quy tắc cookie. Nó có thể làm cookie không được gửi khi user đi từ một trang ngoài vào ứng dụng qua liên kết top-level, ảnh hưởng trải nghiệm đăng nhập/điều hướng.

Dùng khi luồng nghiệp vụ phù hợp và đã kiểm tra tác động với link từ ngoài, SSO và redirect.

### 8.2. SameSite=Lax

~~~http
Set-Cookie: session=opaque; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Lax cho phép cookie trong các ngữ cảnh same-site và một số điều hướng top-level cross-site dùng phương thức an toàn theo định nghĩa của browser. Nó thường là lựa chọn cân bằng cho session cookie thông thường.

Không giả định mọi request cross-site đều bị chặn: điều hướng GET top-level có thể vẫn gửi cookie. Endpoint GET vì thế **không được thay đổi trạng thái nghiệp vụ nhạy cảm**.

### 8.3. SameSite=None

~~~http
Set-Cookie: widget_session=opaque; Path=/; Secure; HttpOnly; SameSite=None
~~~

None cho phép cookie được gửi trong ngữ cảnh cross-site nếu các điều kiện khác cho phép. Cookie SameSite=None cần có Secure theo yêu cầu của browser hiện đại.

Cookie cross-site còn có thể bị chặn hoặc partition theo chính sách quyền riêng tư của trình duyệt, cài đặt người dùng và bối cảnh. SameSite=None không đảm bảo cookie bên thứ ba sẽ luôn được gửi.

### 8.4. Same-site khác same-origin

Trong mô hình schemeful same-site, hai URL có thể khác origin nhưng cùng site:

~~~text
https://app.example.test
https://api.example.test
~~~

Khác host nên cross-origin, nhưng cùng scheme và registrable domain nên có thể same-site. SameSite không dùng port như thành phần origin.

| Thuộc tính | Câu hỏi |
| --- | --- |
| SOP / origin | Hai tài liệu có cùng scheme, host, port không? |
| SameSite | Request phát sinh trong ngữ cảnh site nào so với site cookie? |
| Domain | Host nào có thể nhận cookie? |
| Path | Request path nào phù hợp? |
| Secure | Kết nối có đáp ứng điều kiện truyền cookie an toàn? |

SameSite giúp giảm CSRF nhưng không thay thế CSRF token/kiểm tra backend trong mọi kiến trúc. Đặc biệt cần xem xét subdomain same-site nhưng không cùng mức tin cậy.

## 9. Prefix cookie: __Host- và __Secure-

Cookie prefix là quy ước tên mà browser hỗ trợ dùng để áp đặt điều kiện khi chấp nhận Set-Cookie.

### 9.1. Prefix __Secure-

Cookie bắt đầu bằng __Secure- cần được đặt từ secure origin và phải có thuộc tính Secure theo quy tắc prefix.

~~~http
Set-Cookie: __Secure-session=opaque; Secure; HttpOnly; Path=/; SameSite=Lax
~~~

Prefix này giúp browser từ chối một số cookie giả mạo không đáp ứng điều kiện Secure. Tuy nhiên, nó không tự yêu cầu host-only; cookie vẫn có thể khai báo Domain nếu không bị quy tắc khác cấm.

### 9.2. Prefix __Host-

Cookie có prefix __Host- có yêu cầu chặt hơn trong browser hỗ trợ:

- Phải có Secure.
- Phải có Path=/.
- Không được có thuộc tính Domain.
- Phải được đặt từ secure origin theo quy tắc prefix.

Ví dụ session cookie:

~~~http
Set-Cookie: __Host-session=opaque; Secure; HttpOnly; Path=/; SameSite=Lax
~~~

Nếu thêm Domain=example.test hoặc bỏ Path=/, browser hỗ trợ prefix sẽ từ chối cookie đó.

__Host- là lựa chọn tốt cho cookie phiên host-only khi tương thích browser. Prefix không thay authentication, authorization hoặc CSRF protection.

### 9.3. Prefix không thay thế kiểm tra cookie attributes

Không phải browser cũ nào cũng hỗ trợ mọi prefix giống nhau. Backend vẫn nên cấu hình thuộc tính rõ ràng và không dựa duy nhất vào prefix để suy ra cookie có thuộc tính gì. Kiểm tra Set-Cookie thực tế và hành vi browser mục tiêu.

## 10. Partitioned cookies và cookie bên thứ ba

Trình duyệt hiện đại có các cơ chế phân vùng storage để giảm theo dõi người dùng giữa các site. **Partitioned cookies** (CHIPS: Cookies Having Independent Partitioned State) cho phép một số cookie được lưu theo cả cookie host và **top-level site** đang nhúng.

Ví dụ:

~~~http
Set-Cookie: widget_state=opaque; Secure; HttpOnly; SameSite=None; Partitioned
~~~

Trong browser hỗ trợ, cookie Partitioned có partition key gắn với site top-level. Cùng widget bên thứ ba được nhúng trên hai website top-level khác nhau có thể nhận hai cookie partitioned riêng, thay vì dùng chung trạng thái cross-site.

Các điểm cần lưu ý:

- Partitioned không có nghĩa cookie được chia theo port.
- Cookie partitioned cần Secure theo yêu cầu hiện hành của cơ chế.
- Khi cần gửi cross-site, thường phải cấu hình SameSite=None và các điều kiện credentials phù hợp.
- Hỗ trợ và chính sách third-party cookie khác nhau theo browser, chế độ và cài đặt.
- Partitioning không thay thế xác thực, authorization hoặc kiểm tra nguồn request.

Không giả định mọi browser đều lưu và gửi cookie bên thứ ba theo một chính sách giống nhau. Kiểm thử tích hợp thực tế, đặc biệt với iframe đăng nhập, thanh toán, widget và SSO.

## 11. Cookie trùng tên và cookie tossing

Một request có thể chứa nhiều cookie cùng tên nhưng được lưu ở phạm vi khác nhau (ví dụ Path hoặc Domain khác nhau):

~~~http
Cookie: session=host-value; session=domain-value
~~~

Request Cookie không mang thông tin Domain/Path đi kèm từng cặp, nên server có thể khó biết giá trị đến từ cookie nào nếu chỉ nhìn header. Framework có thể chọn first, last hoặc tạo danh sách tùy parser.

**Cookie tossing** là một nhóm vấn đề xảy ra khi host/subdomain có thể đặt cookie cùng tên với cookie của ứng dụng chính ở phạm vi Domain rộng, tạo ra nhiều giá trị trùng tên hoặc làm server diễn giải nhầm.

Phòng vệ:

- Dùng tên session cookie có prefix __Host- khi phù hợp.
- Tránh Domain rộng cho session nếu không cần chia sẻ.
- Không tái sử dụng cùng tên cookie ở các Path/Domain khác nhau nếu backend không xử lý duplicate một cách rõ ràng.
- Xác định parser/framework xử lý duplicate như thế nào và từ chối trường hợp mơ hồ nếu cần.
- Khi thay đổi cookie name/scope, xóa cookie cũ bằng đúng Domain/Path tương ứng để tránh giá trị trùng còn tồn tại.

### 11.1. Xóa cookie cần đúng phạm vi

Để xóa cookie, server thường gửi lại cùng tên và phạm vi Domain/Path tương ứng với cookie cần xóa, kèm expiry đã qua hoặc Max-Age bằng 0:

~~~http
Set-Cookie: session=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Lax
~~~

Nếu cookie cũ được tạo với Domain=example.test hoặc Path=/admin, một header xóa host-only hoặc Path khác có thể không xóa đúng cookie cũ. Cần kiểm tra DevTools Application/Storage để xác nhận cookie thực sự biến mất.

## 12. Cookie scope khác với SOP và CORS

Cookie và origin có các phạm vi khác nhau:

- SOP so sánh origin gồm scheme, host, port.
- Cookie Domain/host scope không dùng port để tách cookie.
- Cookie Path giới hạn request path nhưng không tạo sandbox DOM.
- CORS quyết định JavaScript cross-origin có được đọc response theo chính sách không.
- Cookie được browser quản lý và tự gửi nếu request đáp ứng cookie policy; ACAH không cho JavaScript tự đặt Cookie.

Ví dụ frontend:

~~~js
const response = await fetch("https://api.example.test/profile", {
  credentials: "include"
});
~~~

Dù dùng credentials: include, cookie chỉ được gửi nếu host/domain, path, Secure, SameSite và browser policy phù hợp. Để JavaScript đọc response, API còn cần CORS cho phép origin cụ thể và cấu hình credentials tương ứng.

Với credentialed CORS, ví dụ response:

~~~http
Access-Control-Allow-Origin: https://app.example.test
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Không dùng Access-Control-Allow-Origin: * cho response credentialed. Và việc CORS cho phép frontend đọc response không tự chứng minh user có quyền xem bản ghi.

## 13. Cookie scope và CSRF

Cookie thường được browser tự động gửi. Đây là lý do cookie session tiện dụng, nhưng cũng tạo rủi ro **Cross-Site Request Forgery (CSRF)**: một trang ngoài có thể khiến browser gửi request tới ứng dụng trong một số ngữ cảnh, kèm cookie nếu cookie policy cho phép.

Các lớp phòng vệ nên kết hợp:

1. Dùng SameSite phù hợp; hiểu rõ điều hướng top-level và các ngữ cảnh cross-site.
2. Với thao tác thay đổi trạng thái, dùng CSRF token gắn với phiên hoặc cơ chế phòng vệ tương đương.
3. Kiểm tra Origin/Referer hoặc Fetch Metadata khi phù hợp; có chính sách rõ cho header thiếu.
4. Không thực hiện thay đổi trạng thái qua GET.
5. Kiểm tra authentication, authorization và ownership ở backend.
6. Yêu cầu xác thực lại hoặc xác nhận bổ sung cho hành động đặc biệt nhạy cảm.

HttpOnly không ngăn CSRF vì browser vẫn tự gửi cookie. Secure bảo vệ truyền tải, không xác nhận ý định người dùng. SameSite giảm một số request cross-site nhưng không thay thế mọi lớp kiểm soát.

### 13.1. Cùng site không đồng nghĩa đáng tin

Giả sử legacy.example.test bị chiếm quyền trong khi API ở api.example.test. Hai host khác origin nhưng có thể same-site. Một cookie SameSite vẫn có thể được gửi trong request same-site phù hợp.

Nếu ứng dụng tin rằng mọi subdomain cùng site đều đáng tin, kẻ tấn công có thể lợi dụng subdomain yếu để gửi request. Cần đánh giá subdomain, Domain cookie, CSRF token và authorization backend như các ranh giới riêng.

## 14. Cấu hình cookie phiên khuyến nghị

Một mẫu thường phù hợp cho session cookie chỉ dùng trên một host HTTPS:

~~~http
Set-Cookie: __Host-session=OPAQUE_RANDOM_VALUE; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Ý nghĩa:

| Thuộc tính | Lý do |
| --- | --- |
| __Host- | Browser hỗ trợ prefix sẽ yêu cầu Secure, Path=/ và không có Domain. |
| Secure | Chỉ gửi trên kết nối an toàn theo quy tắc cookie. |
| HttpOnly | Không expose cookie cho JavaScript. |
| Path=/ | Cookie phù hợp toàn bộ path trên host. |
| Không có Domain | Host-only, không chia sẻ tự động với subdomain. |
| SameSite=Lax | Giảm một số request cross-site nhưng vẫn hỗ trợ điều hướng top-level an toàn thường gặp. |

Tùy ứng dụng, cần cân nhắc thêm:

- Max-Age hoặc Expires cho tuổi thọ; session cookie không có expiry cố định vẫn có thể được browser khôi phục tùy cài đặt.
- Session rotation sau đăng nhập hoặc thay đổi quyền.
- Hủy session phía server khi logout, hết hạn hoặc phát hiện sự cố.
- CSRF token và xác minh nguồn request cho thao tác đổi trạng thái.
- HSTS và TLS cấu hình tốt.
- Giới hạn quyền session, thời hạn và cơ chế phát hiện bất thường.

Không có một cấu hình cookie duy nhất phù hợp cho mọi hệ thống. SSO, iframe cross-site, thanh toán, nhiều subdomain hoặc ứng dụng legacy có thể cần thiết kế riêng; hãy chọn scope nhỏ nhất đáp ứng chức năng.

## 15. Ví dụ các quyết định scope

| Nhu cầu | Cấu hình/thiết kế thường phù hợp | Rủi ro cần xem |
| --- | --- | --- |
| Session chỉ dùng ở app.example.test | Host-only, __Host-, Path=/, Secure, HttpOnly, SameSite phù hợp | XSS vẫn có thể thao tác qua session; cần CSRF/backend checks. |
| Chia sẻ cookie giữa app và api subdomain | Cân nhắc thiết kế domain/session hoặc token riêng theo kiến trúc | Domain rộng tăng tin cậy giữa subdomain; khác origin vẫn cần CORS. |
| Cookie chỉ dùng ở /admin | Có thể đặt Path=/admin để giảm gửi ngoài path | Path không phải biên authorization hay JavaScript isolation. |
| Widget bên thứ ba trong iframe cần trạng thái riêng theo site nhúng | Cân nhắc Partitioned cookie với Secure và cấu hình phù hợp | Browser có thể chặn third-party cookie; kiểm tra tương thích và fallback. |
| Cookie phải được gửi cross-site | SameSite=None; Secure nếu chính sách browser cho phép | Third-party cookie policy, partitioning, CSRF và credentials CORS. |
| Cookie chứa session nhạy cảm | Host-only, Secure, HttpOnly, SameSite phù hợp, thời hạn ngắn | Session management, rotation, revoke, CSRF, XSS vẫn cần bảo vệ. |

## 16. Thực hành A — Quan sát host-only và Domain cookie

Thực hiện trên môi trường local/staging bạn kiểm soát, hoặc một domain test có nhiều subdomain được cấu hình. Với localhost, việc kiểm tra domain/subdomain không đại diện đầy đủ cho production.

Giả sử có:

- https://app.example.test
- https://api.example.test

Từ response của app.example.test, thử đặt host-only cookie:

~~~http
Set-Cookie: host_only_demo=one; Path=/; Secure; SameSite=Lax
~~~

Sau đó đặt domain cookie:

~~~http
Set-Cookie: domain_demo=two; Domain=example.test; Path=/; Secure; SameSite=Lax
~~~

Trong DevTools → **Application/Storage → Cookies**, quan sát cột Domain/HostOnly nếu browser hiển thị. Gửi request tới cả app và api, xem tab Network → Request Headers.

Kết quả cần xác minh:

- host_only_demo chỉ gửi tới host đã đặt.
- domain_demo có thể gửi tới subdomain phù hợp.
- Hai host vẫn cross-origin; cookie Domain không làm SOP cho phép đọc DOM.

## 17. Thực hành B — Cookie không tách theo port

Trên localhost, chạy hai server cùng host:

- http://localhost:3000
- http://localhost:4000

Từ server cổng 3000 trả:

~~~http
Set-Cookie: port_demo=value; Path=/
~~~

Mở trang cổng 4000 và xem request header Cookie trong Network hoặc log server. Hành vi cookie có thể chịu ngoại lệ secure-context/local development và chính sách browser, nên ghi lại môi trường thử nghiệm cụ thể.

Đối chiếu location.origin tại hai trang: khác nhau do port. Điều đó chứng minh origin và cookie scope không cùng một bộ quy tắc. Không dùng cookie để cô lập hai dịch vụ chạy chung hostname.

## 18. Thực hành C — Path không phải sandbox

Trên host thử nghiệm, đặt:

~~~http
Set-Cookie: path_demo=value; Path=/admin
~~~

Truy cập:

~~~text
https://app.example.test/admin
https://app.example.test/admin/users
https://app.example.test/administrator
https://app.example.test/account
~~~

Trong Network, quan sát request nào mang path_demo. Sau đó mở một trang cùng host nhưng path khác và kiểm tra document.cookie nếu cookie không có HttpOnly.

Mục tiêu là phân biệt hai việc: Path quyết định cookie có được gửi với request path hay không; nó không tạo một origin mới hoặc vùng JavaScript độc lập. Không dùng dữ liệu/session thật trong bài thử.

## 19. Thực hành D — HttpOnly, Secure và SameSite

Tạo các cookie demo với thuộc tính khác nhau:

~~~http
Set-Cookie: demo_http_only=one; Path=/; HttpOnly; SameSite=Lax
Set-Cookie: demo_secure=two; Path=/; Secure; SameSite=Lax
Set-Cookie: demo_strict=three; Path=/; Secure; SameSite=Strict
Set-Cookie: demo_none=four; Path=/; Secure; SameSite=None
~~~

Quan sát:

1. Cookie HttpOnly không xuất hiện trong document.cookie, nhưng có thể xuất hiện trong request Cookie phù hợp.
2. Cookie Secure không được gửi qua HTTP thông thường, ngoại trừ các quy tắc secure context đặc biệt của browser như localhost.
3. So sánh SameSite khi điều hướng từ một site khác và khi request được tạo trong cùng site.
4. SameSite=None yêu cầu Secure trong browser hiện đại; third-party cookie policy có thể tiếp tục chặn hoặc partition cookie.

Không dùng trình duyệt hoặc tài khoản thật để thử request thay đổi dữ liệu.

## 20. Checklist review cookie scope

- [ ] Session cookie có thật sự cần Domain rộng không? Nếu không, bỏ Domain để dùng host-only.
- [ ] Có thể dùng prefix __Host- với Secure, Path=/ và không Domain không?
- [ ] Path có được hiểu đúng là bộ lọc request path, không phải authorization hoặc sandbox?
- [ ] Cookie có Secure trên production HTTPS không?
- [ ] Session cookie có HttpOnly nếu JavaScript không cần đọc không?
- [ ] SameSite được chọn theo luồng login, SSO, redirect, iframe và CSRF thực tế?
- [ ] Có cookie trùng tên ở Domain/Path khác nhau không? Backend parser xử lý thế nào?
- [ ] Cookie cũ có được xóa bằng đúng Path/Domain khi thay đổi scope không?
- [ ] Có subdomain không tin cậy nhưng nhận được Domain cookie không?
- [ ] Hệ thống có giả định cookie được tách theo port không? Nếu có, cần sửa kiến trúc.
- [ ] Cookie bên thứ ba/iframe có cần Partitioned không, và browser mục tiêu hỗ trợ thế nào?
- [ ] Backend xác thực và phân quyền độc lập với việc browser gửi cookie không?
- [ ] CSRF token/kiểm tra Origin hoặc Fetch Metadata có phù hợp với endpoint không?
- [ ] CORS credentialed response dùng origin cụ thể và ACA-Credentials đúng không?
- [ ] Session có rotation, expiry, revoke và logout server-side không?
- [ ] Không log giá trị cookie hoặc đưa session secret vào URL/telemetry.

## 21. Những ngộ nhận thường gặp

| Nhận định | Đánh giá | Giải thích |
| --- | --- | --- |
| “Không có Domain nghĩa là cookie dùng cho mọi subdomain.” | **Sai** | Không có Domain tạo host-only cookie. |
| “Domain=.example.test khác Domain=example.test.” | **Sai** | Dấu chấm đầu không tạo khác biệt domain-match trong browser hiện đại. |
| “Path=/admin ngăn JavaScript ở path khác đọc cookie.” | **Sai** | Path không phải sandbox JavaScript. |
| “Cookie được tách theo port giống SOP.” | **Sai** | Cookie không có scope port. |
| “HttpOnly ngăn mọi tác động XSS.” | **Sai** | XSS vẫn có thể gọi API trong phiên của user. |
| “Secure mã hóa cookie trong browser storage.” | **Sai** | Secure giới hạn truyền qua kết nối an toàn; không mã hóa storage/log. |
| “SameSite=Strict thay thế CSRF token trong mọi trường hợp.” | **Sai** | Cần xem site context, subdomain và thiết kế endpoint. |
| “Same-site đồng nghĩa same-origin.” | **Sai** | Subdomain có thể khác origin nhưng cùng site. |
| “Domain cookie luôn cần thiết để chia sẻ login.” | **Sai** | Có thể dùng SSO/token hoặc thiết kế riêng; Domain rộng tăng phạm vi tin cậy. |
| “Cookie request header cho server biết Path/Domain của từng cookie.” | **Sai** | Cookie header chỉ chứa name/value. |
| “Prefix __Host- tự xác thực session.” | **Sai** | Prefix ràng buộc thuộc tính cookie, không xác thực user. |
| “Partitioned cookie luôn được gửi trong mọi iframe.” | **Sai** | Còn phụ thuộc browser, Secure, SameSite và chính sách cookie. |

## 22. Tổng kết

Cookie scope quyết định **host nào, path nào và ngữ cảnh nào** có thể nhận cookie. Host-only cookie thường hẹp hơn domain cookie; Path lọc request path nhưng không phải ranh giới bảo mật mạnh; cookie không được cách ly theo port; Secure, HttpOnly và SameSite giải quyết các vấn đề khác nhau. Prefix __Host- có thể giúp ràng buộc cookie phiên vào một host khi browser hỗ trợ, còn Partitioned cookie phục vụ một số tích hợp cross-site có trạng thái riêng theo top-level site.

Hãy giữ ba nguyên tắc:

1. **Scope nhỏ nhất cần thiết:** ưu tiên host-only cho session, tránh Domain rộng, dùng Path và expiry rõ ràng, cân nhắc __Host-.
2. **Không nhầm thuộc tính:** Secure bảo vệ truyền tải, HttpOnly giới hạn JavaScript đọc cookie, SameSite kiểm soát ngữ cảnh site, Path/Domain quyết định request phù hợp; không thuộc tính nào thay thế authorization.
3. **Bảo vệ phiên ở backend:** cookie tự động đi cùng request nên cần CSRF protection, session management, xác thực và phân quyền cho từng thao tác.

Khi review một cookie, hãy hỏi: **host nào có thể nhận nó, path nào làm nó được gửi, request đang ở ngữ cảnh site nào, script có đọc được không, kết nối có an toàn không, và server xác minh quyền gì sau khi nhận cookie?** Trả lời rõ từng câu sẽ giúp đặt cookie scope đúng và tránh mở rộng ranh giới tin cậy ngoài nhu cầu.
