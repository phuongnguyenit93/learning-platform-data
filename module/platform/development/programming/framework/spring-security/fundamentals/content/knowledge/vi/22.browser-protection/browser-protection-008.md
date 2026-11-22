# Cookie bảo mật và giới hạn của HttpOnly, Secure, SameSite

## 1. Câu hỏi trọng tâm: một cookie “có đủ ba cờ” đã an toàn tuyệt đối chưa?

Trong ứng dụng web dùng Spring Security, trình duyệt có thể nhận một cookie phiên:

~~~http
Set-Cookie: __Host-SESSION=opaque-session-id; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Ba thuộc tính **HttpOnly**, **Secure** và **SameSite** giúp giảm những nhóm rủi ro **khác nhau**, nhưng không biến cookie thành một cơ chế xác thực hoàn chỉnh và không loại bỏ mọi cách chiếm phiên.

- **HttpOnly**: hạn chế JavaScript truy cập giá trị cookie bằng các API như document.cookie.
- **Secure**: yêu cầu browser gửi cookie qua kết nối HTTPS (có ngoại lệ và cách xử lý riêng đối với localhost ở một số browser).
- **SameSite**: giới hạn thời điểm browser gửi cookie trong những request **cross-site**, giúp giảm một số tình huống Cross-Site Request Forgery (CSRF).

**Điểm cần nhớ:** Cookie là phương tiện lưu/truyền một giá trị. Cookie phiên thường chứa **mã định danh phiên**, còn trạng thái đăng nhập được quản lý ở server. HttpOnly không xóa lỗ hổng XSS, Secure không cài đặt TLS hay mã hóa giá trị cookie khi lưu ở máy client, SameSite không thay CSRF token.

Mục tiêu sau bài:
1. Đọc chính xác **Set-Cookie** và request **Cookie**.
2. Giải thích ba flag HttpOnly/Secure/SameSite cùng **giới hạn bảo vệ** của từng flag.
3. Phân biệt **origin** và **site**, hiểu Strict/Lax/None và các trường hợp cookie được/không được gửi.
4. Hiểu **Domain, Path, Max-Age/Expires, prefix __Host-/__Secure-**, thời gian sống và nguy cơ session fixation/cookie tossing.
5. Cấu hình cookie phiên trong **Spring Boot 3.x + Spring Security 6.x**, Java 17+, tách rõ HTTP local với HTTPS production.
6. Kiểm chứng qua browser DevTools, curl và MockMvc, không in bí mật session ra màn hình API.
7. Nêu được vì sao vẫn cần **CSRF, XSS defense, logout, session expiry, HTTPS/HSTS, authorization và bảo vệ server-side session**.

> Tài liệu này thuộc **Bảo vệ trình duyệt**. Ví dụ tập trung vào **Spring MVC/Servlet và HttpSession**. Cookie dùng cho OAuth/BFF, JWT trong cookie hoặc Spring WebFlux có yêu cầu riêng; nguyên tắc browser giống nhau nhưng mã Java/cấu hình khác.

## 2. HTTP cookie làm việc như thế nào?

HTTP không tự nhớ danh tính qua nhiều request. Server thường dùng cookie để liên kết trình duyệt với một phiên.

~~~text
Request A: browser chưa có session
   Browser -------------------------------> Server
             GET /api/csrf

             Set-Cookie: JSESSIONID=xyz...
   Browser <------------------------------- Server
   Browser lưu cookie theo Domain/Path/...
   
Request B: browser có cookie phiên hợp lệ
   Browser -------------------------------> Server
             Cookie: JSESSIONID=xyz...
             GET /api/me

   Server tìm HttpSession từ session ID;
   Spring Security nạp lại Authentication nếu có.
   Browser <------------------------------- Server
             200 JSON / hoặc redirect login
~~~

**Set-Cookie** là **response header** do server gửi để yêu cầu browser lưu cookie. **Cookie** là **request header** mà browser gửi tới server khi URL/request thỏa điều kiện tương ứng. Cookie request **không gửi lại các attribute HttpOnly, Secure hay SameSite**. Browser đã lưu và áp dụng các attribute ở phía mình.

### 2.1. Những trường thường gặp trong Set-Cookie

~~~http
Set-Cookie: SESSION_ID=example-only; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

| Phần | Ý nghĩa | Có phải thành phần của Cookie request? |
| --- | --- | --- |
| **SESSION_ID** | Tên cookie | Có, tên được gửi trong request |
| **example-only** | Giá trị cookie; ví dụ không phải session ID thật | Có, giá trị được gửi trong request |
| **Path=/** | Phạm vi URL path browser gửi cookie | **Không**, browser tự xét |
| **Secure** | Chỉ gửi cookie trong kết nối secure theo browser policy | Không |
| **HttpOnly** | Không cho JavaScript đọc/ghi cookie qua các API tương ứng | Không |
| **SameSite=Lax** | Giới hạn gửi cookie theo quan hệ site và loại request | Không |

Ví dụ request sau sẽ chỉ chứa tên/giá trị:

~~~http
GET /api/me HTTP/1.1
Host: app.example.com
Cookie: SESSION_ID=example-only
~~~

Đừng kiểm tra việc cookie có HttpOnly bằng cách tìm chữ “HttpOnly” trong request header. Nó chỉ xuất hiện trong **Set-Cookie** response header hoặc bảng Cookies của DevTools.

### 2.2. Cookie phiên khác HttpSession, Authentication và JWT

Một cookie phiên Servlet thường chứa mã định danh **JSESSIONID** (có thể đổi tên). Ở phía server, HttpSession có thể chứa SecurityContext hoặc các session attributes. Browser không nhận toàn bộ UserDetails hoặc authority chỉ vì có JSESSIONID.

| Đối tượng | Phía sở hữu/chức năng | Điều không được suy ra |
| --- | --- | --- |
| **Cookie phiên** | Browser lưu ID, tự gửi khi đủ điều kiện | Có cookie không có nghĩa đã authenticated |
| **HttpSession** | Trạng thái server-side qua nhiều request | Không bắt buộc có Authentication; session có thể chỉ lưu CSRF token |
| **SecurityContext** | Authentication hiện hành hoặc trạng thái đã lưu qua repository | Không phải một cookie hoặc JWT |
| **JWT access token** | Credential chứa claims theo profile, có thể đặt trong header/cookie | Dùng JWT không có nghĩa không cần suy nghĩ về CSRF |
| **CSRF token** | Giá trị kiểm tra request thay đổi trạng thái hợp lệ | Không phải session ID, password hoặc access token |

Ví dụ khi GET /api/csrf tạo HttpSession, browser có thể nhận session cookie **trước khi đăng nhập**. Vì vậy cookie hiện diện không chứng minh đã xác thực. Sau POST login, session identifier có thể đổi do session fixation protection.

## 3. HttpOnly: giúp giữ giá trị cookie khỏi JavaScript

Ví dụ:

~~~http
Set-Cookie: JSESSIONID=abc123; Path=/; HttpOnly
~~~

Khi browser lưu cookie có **HttpOnly**, những JavaScript API như **document.cookie** không được đọc hoặc tự sửa trực tiếp cookie đó. Một đoạn JS độc hại do lỗ hổng XSS sẽ khó lấy chuỗi session ID bằng cách chỉ thực hiện document.cookie rồi gửi giá trị đi nơi khác.

### 3.1. HttpOnly *có* tác dụng gì?

- Giảm nguy cơ kẻ tấn công chiếm cookie bằng cách đọc document.cookie trong một tình huống XSS.
- Giúp tách **session credential** khỏi script hợp lệ và script bị chèn vào trang.
- Hỗ trợ nguyên tắc lưu token phiên quan trọng ở nơi mà JavaScript không cần đọc.
- Là defense-in-depth cho cookie đăng nhập, cookie BFF và những credential mà backend nhận tự động.

**Nếu có thể dùng HttpOnly cho session/authentication cookie, nên dùng.** Session cookie không cần để JavaScript đọc ID; browser tự gửi nó theo chính sách.

### 3.2. HttpOnly *không* làm được điều gì?

**HttpOnly không ngăn browser gửi cookie trong request.** Ngay cả khi JavaScript không đọc được giá trị, lệnh fetch cùng origin vẫn có thể kích hoạt request mà browser tự gắn cookie thích hợp:

~~~javascript
// Chạy trên trang cùng origin với ứng dụng.
fetch("/api/profile", {credentials: "same-origin"})
    .then(response => response.json())
    .then(data => console.log(data));
~~~

Nếu attacker đã thực thi JavaScript trong origin thông qua **XSS**, attacker có thể:
- Gửi request cùng origin với cookie đã có.
- Thực hiện thao tác thay đổi dữ liệu nếu backend không kiểm quyền/quy tắc bổ sung.
- Đọc response cùng origin mà script có quyền đọc và lấy dữ liệu nhạy cảm.
- Lấy CSRF token từ DOM hoặc endpoint nếu script có cùng quyền truy cập như ứng dụng.
- Tạo UI giả để lừa người dùng nhập thông tin.

**Vì vậy HttpOnly không “chữa XSS” và không ngăn attacker hành động trong phiên đang mở.** Nó chỉ giảm một kênh **đọc cookie value**. Cần tiếp tục chống XSS bằng output encoding, tránh unsafe DOM APIs, CSP thích hợp và kiểm soát phụ thuộc JS.

### 3.3. HttpOnly và DevTools không mâu thuẫn

Trong DevTools > Application/Storage > Cookies, người phát triển có thể thấy cookie và flag của nó. HttpOnly được thiết kế để hạn chế **web-page JavaScript**, không phải cấm người dùng/chủ thiết bị có toàn quyền debug trình duyệt của họ. Các extension hoặc malware có quyền cao, thiết bị bị chiếm, proxy/log bị lộ và các kênh khác vẫn là rủi ro.

Cookie với HttpOnly **vẫn được gửi** trong request đủ điều kiện; HttpOnly không thay Secure, SameSite, CSRF hay xác thực server.

### 3.4. Đừng tắt HttpOnly chỉ để SPA “đọc session”

Một sai lầm là cấu hình session cookie **http-only=false** chỉ vì JavaScript cần biết đã đăng nhập hay chưa. Cách phù hợp hơn:
- Giữ session cookie **HttpOnly**.
- Cung cấp endpoint đã bảo vệ **GET /api/me** hoặc endpoint session status trả **thông tin không nhạy cảm**.
- Khi frontend cần biết user name/quyền hiển thị, trả JSON đã lọc; không trả session ID.
- Nếu backend cần cấp CSRF token cho SPA, dùng cơ chế **CSRF token riêng**, không dùng JSESSIONID làm token CSRF.

Bảo vệ authorization luôn ở server, không dựa vào việc SPA ẩn hiện nút.

## 4. Secure: hạn chế cookie bị gửi qua HTTP

Ví dụ:

~~~http
Set-Cookie: JSESSIONID=abc123; Path=/; Secure; HttpOnly
~~~

**Secure** là chỉ thị browser chỉ gửi cookie qua **HTTPS** theo chính sách browser và điều kiện hỗ trợ. Mục tiêu là tránh để session ID bị truyền rõ ràng trên kết nối HTTP không mã hóa.

### 4.1. Secure không tạo HTTPS

Nếu server chỉ hỗ trợ HTTP, bật Secure không tự sinh chứng chỉ hoặc chuyển mạng sang TLS. Trong môi trường thật, cần:
1. Cấu hình HTTPS và chứng chỉ TLS hợp lệ.
2. Redirect HTTP sang HTTPS theo thiết kế.
3. Bật **Secure** cho session cookie.
4. Sử dụng **HSTS** khi hạ tầng và phạm vi domain đã sẵn sàng.
5. Bảo vệ luồng giữa reverse proxy và backend theo network trust boundary.
6. Không gửi token/password trong URL, response logs hoặc HTTP.

Nếu browser gửi request qua HTTP tới production host, nó sẽ không đính kèm cookie Secure phù hợp. Ứng dụng có thể coi user chưa đăng nhập, **đúng với mục đích phòng vệ**.

### 4.2. Secure không bảo vệ điều gì?

- Không mã hóa riêng **giá trị cookie khi lưu trên ổ đĩa/memory** của browser.
- Không ngăn script đọc cookie nếu **HttpOnly không bật**.
- Không ngăn CSRF hoặc XSS gửi request tới **HTTPS** endpoint.
- Không bảo đảm session ID có đủ entropy hoặc chưa bị lộ qua log.
- Không đảm bảo chứng chỉ TLS, cấu hình reverse proxy và HSTS đều đúng.
- Không tự làm cookie hết hiệu lực khi logout.
- Không phân biệt quyền ADMIN/USER.

### 4.3. Ngoại lệ localhost khi học tập

MDN ghi nhận một số browser có **cách xử lý đặc biệt với localhost** đối với Secure. Điều này không phải lý do để triển khai production bằng HTTP. Hãy phân biệt:
- **Local demo** có thể dùng HTTP + cookie không có Secure, với mật khẩu thử nghiệm, giới hạn máy phát triển.
- **Production** phải phục vụ qua HTTPS + cookie Secure và chính sách hostname/domain đúng.
- Không dựa vào ngoại lệ localhost để kết luận cookie Secure sẽ hoạt động trên staging HTTP hoặc IP/hostname thật.

Trong ví dụ Spring Boot bên dưới, hai profile **local** và **default/production** được cấu hình khác nhau có chủ đích.

### 4.4. Secure sau reverse proxy

Một hệ thống thường có:

~~~text
Browser --HTTPS--> Reverse proxy/load balancer
                           |
                           | HTTP nội bộ (hoặc HTTPS)
                           v
                       Spring Boot
~~~

Nếu backend không biết browser truy cập bằng HTTPS, một số logic có thể tạo redirect/cookie sai hoặc cấu hình HSTS không như mong đợi. Ngược lại, tin mọi **X-Forwarded-Proto** do client Internet tự đặt cũng nguy hiểm.

Cần xác định rõ **proxy tin cậy**, loại bỏ/ghi đè forwarded headers ở edge, cấu hình Spring Boot nhận forwarding phù hợp (ví dụ server.forward-headers-strategy theo môi trường) và kiểm tra **Set-Cookie ở public HTTPS endpoint**, không chỉ HTTP nội bộ.

## 5. SameSite: giảm cookie bị gửi trong request cross-site

**SameSite** điều khiển khi nào browser gửi cookie trong request có quan hệ **same-site** hoặc **cross-site** so với ngữ cảnh trang khởi tạo. Nó hỗ trợ giảm nhiều kiểu CSRF vì trang attacker ở một site khác không dễ khiến browser gửi session cookie đến ứng dụng đích trong những request nhất định.

Các giá trị phổ biến:

~~~http
Set-Cookie: SID=example; Secure; HttpOnly; SameSite=Strict
Set-Cookie: SID=example; Secure; HttpOnly; SameSite=Lax
Set-Cookie: SID=example; Secure; HttpOnly; SameSite=None
~~~

**SameSite=None phải đi kèm Secure** để được các browser hiện đại chấp nhận. Dòng trên chỉ minh họa tổ hợp hợp lệ khi set từ ngữ cảnh HTTPS; không dùng nguyên ID mẫu làm credential.

### 5.1. Strict

**SameSite=Strict** cho phép gửi cookie trong **same-site contexts** và giới hạn gửi trong **cross-site contexts**, kể cả điều hướng top-level từ một site khác đến.

Thí dụ: người dùng đang đăng nhập **https://bank.example** rồi nhấp link dẫn đến bank.example từ một website bên ngoài. Với Strict, request điều hướng đầu tiên có thể **không** mang cookie; user có thể thấy trạng thái chưa đăng nhập ở lượt đầu cho đến khi quay vào các trang cùng site hoặc thực hiện luồng phù hợp.

**Ưu:** giảm nhiều tình huống cross-site gửi credential.  
**Nhược:** có thể ảnh hưởng UX khi người dùng đến từ email, search result, hệ thống hỗ trợ khách hàng hoặc link ngoài.

Nếu ứng dụng yêu cầu mức độ bảo vệ cao và UX phù hợp, Strict có thể là lựa chọn tốt; cần thử chính những hành trình sản phẩm.

### 5.2. Lax

**SameSite=Lax** cho phép cookie trong same-site requests và **một số top-level cross-site navigations dùng safe method**, điển hình nhấp link dẫn tới một trang GET. Nó thường **không gửi cookie cho cross-site POST** hoặc request lấy tài nguyên bên thứ ba theo ngữ cảnh không được phép.

| Request từ site khác tới app | Lax thường được gửi? | Vì sao |
| --- | --- | --- |
| Người dùng nhấp link top-level tới HTTPS GET của app | **Có** | Top-level navigation + safe method |
| JavaScript fetch cross-site GET có credentials | **Không**, nếu thực sự cross-site | Không phải top-level navigation |
| Form POST cross-site | **Không**, với SameSite=Lax tường minh | Unsafe method |
| img/script/iframe subresource từ site khác | Thường **không** | Không phải top-level safe navigation |
| Các request same-site có đường dẫn phù hợp | **Có** | SameSite không chặn same-site |

**Quan trọng:** Header không có SameSite có thể được browser mặc định diễn giải như Lax, nhưng ở một số browser chế độ **Lax-by-default** có ngoại lệ khoảng hai phút cho một số POST mới nhận cookie. **SameSite=Lax được khai báo tường minh** không nên bị đánh đồng với hoàn toàn không khai báo. Vì hành vi mặc định có thể thay đổi, đặt SameSite một cách chủ động.

### 5.3. None

**SameSite=None** cho phép cookie được gửi ở những ngữ cảnh cross-site mà các điều kiện browser khác cho phép, bao gồm khi ứng dụng cần iframe hoặc tích hợp giữa những site khác nhau.

Điều kiện tối thiểu:

~~~http
Set-Cookie: widget_session=example; Path=/; SameSite=None; Secure; HttpOnly
~~~

Nhưng **None không bắt browser buộc phải lưu/gửi third-party cookie**. Browser có thể chặn third-party cookies, có partitioning hoặc các privacy protections khác. **SameSite=None không tự bật CORS** và không bảo đảm phiên đăng nhập chạy được trong mọi iframe.

Vì phạm vi gửi rộng hơn, khi cookie đóng vai trò xác thực, cần bảo vệ **CSRF** và đánh giá tích hợp cross-site, Content Security Policy/frame embedding, clickjacking, cookie lifetime và origin trust.

### 5.4. Chọn Strict, Lax hay None?

| Policy | Phù hợp khi nào? | Cái giá/giới hạn |
| --- | --- | --- |
| **Strict** | Trang nhạy cảm và UX không phụ thuộc cross-site navigation mang phiên ngay lượt đầu | Có thể gây friction khi mở link từ ngoài |
| **Lax** | Nhiều web app truyền thống cần đăng nhập giữ khi user nhấp link đến từ site khác | Không thay CSRF; top-level GET vẫn nhận cookie |
| **None; Secure** | Tích hợp cross-site thực sự cần gửi cookie | Phơi bày thêm bề mặt CSRF, bị third-party-cookie policy hạn chế |
| **Không khai báo** | Không nên dựa vào đây như lựa chọn thiết kế mặc định | Browser defaults và ngoại lệ có thể khác nhau |

**Quyết định SameSite phải dựa trên hành vi thực của client** và threat model, không chỉ tiêu chí “Strict luôn tốt nhất”.

## 6. Phân biệt same-origin và same-site

Một trong những nguồn hiểu lầm nguy hiểm nhất là đồng nhất **origin** với **site**.

- **Origin** dùng **scheme + host + port**.
- **Schemeful same-site** xét scheme và **registrable domain** (ví dụ eTLD+1 theo quy tắc Public Suffix List); port thường không dùng để phân biệt site.
- Hai subdomain của cùng registrable domain có thể **cross-origin nhưng same-site**. Các đường dẫn khác nhau cùng host cũng có thể same-origin và same-site.

Ví dụ với trang đang mở ở **https://app.example.com**:

| Đích | Same-origin? | Same-site? | Chú ý |
| --- | --- | --- | --- |
| https://app.example.com/api | Có | Có | Cùng scheme/host/port |
| https://app.example.com:8443/api | Không | Có theo site | Khác port, site không phân biệt port như origin |
| https://api.example.com/api | Không | Có | Khác subdomain nhưng cùng registrable domain/scheme |
| http://app.example.com/api | Không | Không theo schemeful site | Khác scheme |
| https://other.example.org/api | Không | Không | Khác registrable domain |

Ví dụ này dựa vào domain minh họa dưới example.com/other.example.org; quy tắc site thực tế còn xét Public Suffix List. Với domain nội bộ hoặc suffix đặc biệt, hãy kiểm browser thay vì tự tách chuỗi bằng dấu chấm.

### 6.1. Vì sao same-site subdomain vẫn đáng lo?

Giả sử **app.example.com** giữ cookie session SameSite=Lax hoặc Strict, còn **uploads.example.com** cho người ngoài lưu HTML/JavaScript. Hai trang có thể **same-site** theo browser, mặc dù **khác origin**. Nếu subdomain kém tin cậy có thể tạo request tới app, **SameSite không tự tạo ranh giới bảo vệ giữa hai origin này**.

Bảo mật thực tế vẫn cần:
- CSRF token cho unsafe methods khi dùng cookie xác thực.
- Không cho các sibling subdomains không tin cậy ghi/chiếm cookie qua Domain rộng.
- CORS chỉ allowlist những origin thực sự tin cậy.
- Authentication, Authorization và kiểm tra quyền sở hữu tài nguyên.
- Cách ly nội dung user upload sang domain độc lập khi cần.

**Không coi same-site là same-trust.** Đây là một giới hạn quan trọng của SameSite.

### 6.2. CORS không thay đổi SameSite

CORS trả lời liệu JavaScript tại origin A có được browser **đọc response** của origin B không. SameSite trả lời browser có **gửi cookie** trong ngữ cảnh site tương ứng không. Cookie còn có Secure, Domain, Path, browser privacy policy và fetch credentials mode.

Một response được server cho CORS có thể vẫn không kèm cookie vì SameSite/third-party-cookie policy. Ngược lại, một simple cross-origin POST có thể được gửi trước khi browser quyết định script được đọc response hay không. Vì vậy **không dùng CORS như CSRF protection**.

## 7. Vì sao SameSite không thay thế CSRF token?

Mục tiêu CSRF là ngăn trang attacker điều khiển browser gửi thao tác thay đổi dữ liệu ngoài ý muốn trong khi cookie hoặc credential khác được gắn tự động.

**SameSite giúp giảm nhiều kịch bản, nhưng có giới hạn**:
1. **Same-site cross-origin**: sibling subdomain không đáng tin có thể vẫn thuộc cùng site.
2. **Lax và top-level GET**: request GET được cho phép trong các top-level navigation phù hợp; nếu developer dùng GET để xóa hoặc cập nhật dữ liệu, SameSite không bảo vệ.
3. **Browser/clients khác nhau**: cookie policy có khác biệt và legacy browsers có hành vi hạn chế hỗ trợ.
4. **Các luồng cần None**: embedding, federated integrations hoặc cross-site cookies có phạm vi gửi rộng hơn.
5. **XSS cùng origin**: script độc hại trong app vẫn có thể gửi request với cookie được browser gắn.
6. **Đánh cắp cookie bằng cách khác**: SameSite không ngăn attacker sử dụng ID hợp lệ nếu đã có nó, chẳng hạn một HTTP client trực tiếp.
7. **Web clients không chịu chính sách browser**: curl/backend client có thể tự gửi Cookie header; SameSite không phải server authorization.

Với session cookie trên Servlet stack, Spring Security **bật CSRF protection theo mặc định**. Đừng tắt nó chỉ vì đã đặt SameSite=Strict/Lax.

### 7.1. CSRF token và cookie phiên có chức năng khác nhau

~~~text
POST /api/theme/toggle
Cookie: JSESSIONID=<session-id>   -> server tìm đúng session/user
X-CSRF-TOKEN: <csrf-token>        -> server kiểm request hợp lệ
                                      với expected token

Sau đó:
  AuthorizationManager kiểm user có được phép không
  Controller mới cập nhật dữ liệu
~~~

Đây là sơ đồ khái niệm, không phải header thực tế với credential được cấp. CSRF token có thể được đưa qua hidden form field **_csrf** hoặc header thích hợp. Không sử dụng session ID như CSRF token.

### 7.2. POST login và logout

Đăng nhập và đăng xuất cũng là thay đổi trạng thái. Với **form login** Spring Security Servlet, POST /login thường phải có CSRF token. Sau login, CSRF token có thể bị xóa/rotate và client cần lấy token mới. POST /logout cũng cần token theo cấu hình mặc định phù hợp.

Nếu demo curl trả 403 trước khi đăng nhập, kiểm **CSRF token** trước khi kết luận password sai. Không sửa bằng cách tắt CSRF toàn ứng dụng.

## 8. Domain và Path: giảm phạm vi cookie nhưng không tạo cùng một bảo vệ như origin

Ngoài ba cờ chính, cần kiểm:

~~~http
Set-Cookie: SID=example; Domain=example.com; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

### 8.1. Domain

- **Không khai báo Domain**: cookie thường là **host-only cookie**, chỉ gửi tới host đã set cookie.
- **Domain=example.com**: cookie có thể được gửi tới example.com và các subdomain phù hợp.
- Domain rộng làm cookie xuất hiện trong request của nhiều host hơn, tăng bề mặt rủi ro nếu có subdomain kém tin cậy hoặc bị takeover.
- Server không được tùy ý set cookie cho registrable domains không thuộc quyền theo browser rules; Public Suffix List hạn chế những trường hợp như set Domain=.com.

**Khuyến nghị cho session cookie:** tránh **Domain** nếu không thực sự cần chia sẻ trên các subdomains. Trong ví dụ production dùng **__Host-** để browser áp thêm ràng buộc host-only.

### 8.2. Path

**Path=/app** thường khiến browser gửi cookie tới đường dẫn phù hợp dưới **/app**. Path giúp hạn chế phạm vi request nhận cookie, nhưng **không phải hàng rào bảo mật tương đương origin**. JS tại các path khác trong cùng origin hoặc những điều kiện cookie collision có thể còn gây tác động.

Không tách ứng dụng nhạy cảm và ứng dụng không tin cậy trên cùng origin rồi chỉ dựa vào Path khác nhau để cách ly bảo mật. Dùng origin độc lập khi cần trust boundary thật.

### 8.3. Cookie name collision, cookie tossing và session fixation

Nếu nhiều cookie cùng tên nhưng khác Domain hoặc Path, request có thể mang các giá trị khác nhau cùng tên trong một Cookie header. Server/framework có thể chọn/diễn giải không đúng như bạn nghĩ. Sibling subdomain có quyền set Domain cookie rộng còn có thể gây ra **cookie tossing** hoặc một số kiểu session fixation nếu kiến trúc dễ tổn thương.

Để giảm rủi ro:
- Dùng tên cookie rõ ràng và tránh Domain rộng.
- Dùng cookie prefix **__Host-** cho session host-only khi đáp ứng HTTPS/Secure/Path.
- Regenerate/change session ID khi login để giảm session fixation.
- Không chấp nhận session ID attacker tự đặt như authenticated session hợp lệ.
- Tách nội dung upload/third-party khỏi origin và cookie scope của tài khoản.

## 9. Prefix __Secure- và __Host-: ràng buộc thuộc tính ngay ở browser

Tên cookie có thể mang prefix mà các browser hỗ trợ dùng để **kiểm tra ràng buộc khi lưu cookie**.

### 9.1. __Secure-

Cookie có tên bắt đầu **__Secure-** phải được set từ ngữ cảnh HTTPS phù hợp và có attribute **Secure**.

~~~http
Set-Cookie: __Secure-Session=example; Secure; HttpOnly; SameSite=Lax; Path=/
~~~

Nó **không** bắt buộc host-only hoặc Path=/. Nếu cần chia sẻ cookie hợp lệ giữa subdomains, có thể cân nhắc __Secure- cùng Domain có chủ đích, nhưng vẫn phải rà soát trust boundary.

### 9.2. __Host-

Cookie có prefix **__Host-** phải thỏa:
1. **Secure**.
2. Được set từ HTTPS/secure origin được browser chấp nhận.
3. **Không có Domain**.
4. **Path=/**.

Ví dụ:

~~~http
Set-Cookie: __Host-SESSION=example; Secure; HttpOnly; SameSite=Lax; Path=/
~~~

Đây là một mặc định tốt cho session cookie **chỉ thuộc host hiện hành**. Browser hỗ trợ prefix có thể từ chối cookie nếu thiếu Secure, Path khác / hoặc có Domain. Vì vậy chọn prefix phải đi cùng cấu hình server thực, không chỉ đổi chuỗi tên cookie.

**HttpOnly không tự được ràng buộc bởi __Host-.** Bạn vẫn phải thêm HttpOnly nếu muốn ngăn JavaScript đọc cookie. Một số browser còn hỗ trợ prefix **__Http-** và **__Host-Http-** với điều kiện HttpOnly; khả năng tương thích cần kiểm tra theo target browsers.

### 9.3. Prefix không thay session lifecycle

Ngay cả __Host-SESSION có Secure, HttpOnly, SameSite=Strict vẫn có thể:
- Bị sử dụng khi script XSS cùng origin tạo request.
- Bị mất hiệu lực khi session server hết hạn.
- Bị đánh cắp qua malware/thiết bị bị chiếm.
- Không đáp ứng quyền API nếu authentication đã bị thu hồi.
- Không có khả năng “tự đăng xuất” mọi thiết bị khi user nhấn Logout ở một phiên khác.

Cookie prefix là lớp kiểm soát scope/attribute ở browser, **không phải chữ ký số hoặc phép mã hóa session ID**.

## 10. Expires, Max-Age, session timeout và thời hạn của credential

Các thuộc tính thời gian cookie:
- **Expires**: mốc thời gian cookie có thể hết hạn trong browser.
- **Max-Age**: thời lượng tương đối (giây) tính từ lúc cookie được nhận; khi có cả hai, browser ưu tiên Max-Age theo quy tắc.
- **Session cookie**: không có Expires/Max-Age thông thường tồn tại đến khi browser session kết thúc theo browser policy; trình duyệt có thể **khôi phục session qua tính năng session restore**, không bảo đảm đóng cửa sổ là xóa cookie ngay.
- **HttpSession timeout**: hạn server-side của phiên, không bị kéo dài vô hạn chỉ vì browser vẫn giữ cookie ID.

Ví dụ:

~~~http
Set-Cookie: SID=example; Max-Age=900; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Cookie ở browser được yêu cầu có lifetime 900 giây, nhưng **server vẫn phải kiểm HttpSession/token expiration**. Không đặt Max-Age rất dài rồi coi đó là cơ chế giữ phiên an toàn. Sau logout hoặc account compromise, cần vô hiệu session/credential phía server, không chỉ yêu cầu browser xóa cookie.

### 10.1. Cookie còn nhưng session server đã hết hạn

Browser có thể gửi cookie ID cũ trong khi session ở server đã hết hạn, bị invalidate hoặc không có trong shared store. Server không được coi user đã authenticated chỉ vì Cookie header có tên JSESSIONID. Spring Security phải tìm SecurityContext hợp lệ; nếu không có, request protected cần xác thực lại.

### 10.2. Xóa cookie cần khớp scope

Ví dụ trả:

~~~http
Set-Cookie: SID=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Có thể yêu cầu browser xóa cookie SID với name, domain và path tương ứng. Nếu cookie gốc có Domain/Path khác hoặc prefix khác, lệnh xóa không đúng scope có thể để lại cookie cũ.

**Logout không chỉ là xóa cookie phía browser.** Phải invalidate HttpSession hoặc vô hiệu credential trên server; với JWT access token/refresh token cần chiến lược expiry/revocation thích hợp.

### 10.3. Session fixation và thay session ID sau login

Một attacker có thể cố khiến user sử dụng session identifier có thể đoán trước hoặc attacker biết rồi mới đăng nhập. **Session fixation protection** yêu cầu thay/rotate session ID ở thời điểm xác thực theo cơ chế phù hợp.

Spring Security Servlet hỗ trợ và mặc định áp dụng bảo vệ session fixation cho form authentication trên những container hiện đại, thường bằng **changeSessionId()**. Vì vậy:
- Set-Cookie/session ID **trước login** và **sau login** có thể khác.
- Client như curl cần cập nhật cookie jar sau POST /login.
- Không giả định session ID không đổi là test pass.
- Nếu tự viết custom login controller/filter, phải bảo đảm session authentication strategy và SecurityContext persistence được xử lý đúng.

## 11. Ví dụ Spring Boot 3.x, Java 17+: session cookie được cấu hình rõ ràng

Ta xây ứng dụng:
- **GET /**: endpoint public.
- **GET /api/csrf**: cấp CSRF token cho request cùng session.
- **GET /api/me**: chỉ user đã đăng nhập mới xem được.
- **POST /api/theme/toggle**: thay đổi trạng thái theo session, yêu cầu **Authentication và CSRF token**.
- **POST /login / POST /logout**: do Spring Security form login và logout filters chuẩn xử lý.

Mục tiêu: xem hai thuộc tính khác nhau:
1. **Cookie response flags** được cấu hình bằng properties.
2. **Kiểm soát nghiệp vụ** vẫn yêu cầu auth và CSRF, dù cookie có các cờ tốt.

Có hai profile:
- **local**: HTTP localhost:8080, dùng JSESSIONID không Secure để quan sát bằng curl. Chỉ chạy local, không có bí mật thật.
- **Mặc định cho môi trường triển khai HTTPS**: __Host-SESSION; Secure; HttpOnly; SameSite=Lax; Path=/; không khai báo Domain. Yêu cầu TLS thực và proxy an toàn.

### 11.1. Tạo project

Qua Spring Initializr:
- **Spring Boot 3.x**, Java **17+**, build **Gradle**.
- Group **com.example**, artifact **demo**, package **com.example.demo**.
- Dependencies **Spring Web** và **Spring Security**.

Đường dẫn file:

~~~text
src/main/java/com/example/demo/CookieSecurityDemoApplication.java
src/main/resources/application.yml
src/main/resources/application-local.yml
~~~

Không tạo lớp/form login tự viết, vì mục tiêu là **cookie/session flags**, không phải tạo lại AuthenticationFilter.

### 11.2. Toàn bộ Java backend

**src/main/java/com/example/demo/CookieSecurityDemoApplication.java**

~~~java
package com.example.demo;

import java.util.Map;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.annotation.SessionScope;

@SpringBootApplication
public class CookieSecurityDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CookieSecurityDemoApplication.class, args);
    }
}

@Configuration
@EnableWebSecurity
class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http)
            throws Exception {
        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.IF_REQUIRED))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/", "/api/csrf")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .authenticated()
                .requestMatchers(HttpMethod.POST, "/api/theme/toggle")
                    .authenticated()
                .anyRequest().denyAll())
            .formLogin(form -> form
                .defaultSuccessUrl("/api/me", true)
                .permitAll())
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
                .permitAll())
            // CSRF protection mặc định vẫn được bật.
            .build();
    }

    @Bean
    UserDetailsService users() {
        UserDetails learner = User.withUsername("learner")
            .password("{noop}demo123")
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }
}

@Component
@SessionScope
class ThemePreference {

    private boolean darkMode;

    public synchronized boolean isDarkMode() {
        return darkMode;
    }

    public synchronized boolean toggle() {
        darkMode = !darkMode;
        return darkMode;
    }
}

@RestController
class BrowserCookieController {

    private final ThemePreference preference;

    BrowserCookieController(ThemePreference preference) {
        this.preference = preference;
    }

    @GetMapping("/")
    Map<String, String> home() {
        return Map.of("message", "open");
    }

    public record CsrfView(
            String headerName,
            String parameterName,
            String token) {
    }

    @GetMapping("/api/csrf")
    CsrfView csrf(CsrfToken csrfToken) {
        return new CsrfView(
            csrfToken.getHeaderName(),
            csrfToken.getParameterName(),
            csrfToken.getToken());
    }

    @GetMapping("/api/me")
    Map<String, Object> me(Authentication authentication) {
        return Map.of(
            "username", authentication.getName(),
            "darkMode", preference.isDarkMode());
    }

    @PostMapping("/api/theme/toggle")
    Map<String, Boolean> toggle() {
        return Map.of("darkMode", preference.toggle());
    }
}
~~~

**Lưu ý về mã:**
- Chỉ CookieSecurityDemoApplication là public top-level class và tên trùng file Java.
- Các class khác package-private, được component scan trong cùng package.
- **@SessionScope** dùng scoped proxy mặc định để inject ThemePreference vào singleton controller. Giá trị darkMode tồn tại theo session, không theo static/global variable.
- **formLogin** và **logout** mặc định của Spring Security điều khiển POST /login và POST /logout, với CSRF protection.
- **GET /api/csrf** làm token được nạp/sinh khi code gọi getToken(), có thể tạo session cookie **kể cả trước login**.
- SessionCreationPolicy.IF_REQUIRED cho phép Spring Security tạo session khi cần; nó không có nghĩa “mọi GET đều tạo session”.
- Password **{noop}demo123** chỉ phục vụ ví dụ học cục bộ, không dành cho production.
- Demo không echo session cookie, HttpSession.getId(), refresh token hay mật khẩu ra JSON.

### 11.3. Cấu hình cookie cho HTTPS (mặc định)

**src/main/resources/application.yml**

~~~yaml
server:
  servlet:
    session:
      timeout: 20m
      tracking-modes: cookie
      cookie:
        name: __Host-SESSION
        http-only: true
        secure: true
        same-site: lax
        path: /
~~~

Giải thích:
- **__Host-SESSION** dùng prefix yêu cầu Secure, host-only và Path=/.
- **secure: true** buộc cookie được đánh dấu Secure; môi trường công khai phải chạy HTTPS.
- **http-only: true** bảo vệ session cookie khỏi JavaScript đọc trực tiếp.
- **same-site: lax** tương thích nhiều luồng điều hướng; vẫn giữ CSRF cho POST.
- **path: /** đáp ứng tiền tố __Host-.
- **Không khai báo domain** để server tạo host-only cookie.
- **tracking-modes: cookie** hướng container dùng cơ chế session tracking bằng cookie thay vì dựa vào URL rewriting.
- **timeout: 20m** thiết lập idle timeout cho server-side session; không phải browser cookie Max-Age cố định.

**Cần triển khai thực sự qua HTTPS**. Nếu bật các properties này trên HTTP public host, cookie Secure có thể không được browser chấp nhận hoặc gửi lại; với prefix __Host- điều kiện HTTPS càng quan trọng. Không đổi sang insecure chỉ để “sửa login không nhớ”.

### 11.4. Cấu hình local chỉ để thực hành bằng HTTP

**src/main/resources/application-local.yml**

~~~yaml
server:
  servlet:
    session:
      cookie:
        name: JSESSIONID
        secure: false
~~~

Với Spring Boot, profile local ghi đè hai property này trong cấu hình chung; **HttpOnly, SameSite=Lax và Path=/** vẫn giữ nguyên.

Đây là ngoại lệ có chủ đích cho máy phát triển. Không bật profile local trên production và không chấp nhận credential thật qua HTTP. Nếu chạy local có TLS đáng tin, bạn có thể dùng secure=true như production và kiểm tiếp browser behavior.

### 11.5. Khởi chạy

Trong thư mục project Gradle:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=local'
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=local"
~~~

Ứng dụng chạy trên **http://localhost:8080** nếu chưa thay đổi server.port.

Có thể dùng browser mở **http://localhost:8080/login** và đăng nhập learner/demo123. Sau đó GET /api/me cho kết quả gồm username và darkMode.

### 11.6. Quan sát Set-Cookie bằng curl

Trong terminal khác, dùng curl và cookie jar riêng (không chia sẻ file cookie thật):

~~~bash
curl -i -c cookies.txt \
  http://localhost:8080/api/csrf
~~~

Dự kiến có JSON CSRF token và **có thể có Set-Cookie** cho session mới được tạo, ví dụ hình thức:

~~~http
Set-Cookie: JSESSIONID=<random-value>; Path=/; HttpOnly; SameSite=Lax
~~~

Giá trị ID thật được server sinh và không cố định. Vì chạy local với **secure:false**, response local **không yêu cầu Secure**, không phải mẫu cho production. Trên HTTPS với default config, mong đợi thấy cookie tên __Host-SESSION và **Secure; HttpOnly; SameSite=Lax; Path=/** (thứ tự attributes có thể khác).

**Không in/copy session ID thực vào chat, repository, screenshot hoặc logs công khai.** Trên terminal, dùng curl -i chỉ trong lab để quan sát header; ở môi trường thật nên tránh xuất hoặc lưu secret vào công cụ giám sát.

### 11.7. POST login và giữ cookie qua nhiều request

Dùng **Bash + Python 3** để tách CSRF token từ JSON:

~~~bash
curl -sS -c cookies.txt \
  http://localhost:8080/api/csrf > csrf-before.json

CSRF=$(python3 -c \
  "import json; print(json.load(open('csrf-before.json'))['token'])")

curl -i -b cookies.txt -c cookies.txt \
  --data-urlencode "username=learner" \
  --data-urlencode "password=demo123" \
  --data-urlencode "_csrf=$CSRF" \
  http://localhost:8080/login

# Request mới có cookie phiên sau khi login.
curl -i -b cookies.txt http://localhost:8080/api/me
~~~

Dự kiến form login trả **302 redirect** sang /api/me và GET tiếp theo có session đã đăng nhập nên trả **200** với JSON dạng:

~~~json
{"username":"learner","darkMode":false}
~~~

Lệnh cookie jar dùng cả **-b** và **-c** vì session ID có thể đổi khi login để chống session fixation. Nếu GET /api/me trả 302 /login, kiểm xem curl có gửi cookie mới đúng hostname/path và server đã lưu session hay chưa.

### 11.8. SameSite không tự thay CSRF: thử thay đổi dữ liệu

POST thiếu CSRF token sau login:

~~~bash
curl -i -X POST -b cookies.txt \
  http://localhost:8080/api/theme/toggle
~~~

Dự kiến **403**, và darkMode vẫn **false**. Sau đó lấy token mới của phiên đã đăng nhập:

~~~bash
curl -sS -b cookies.txt -c cookies.txt \
  http://localhost:8080/api/csrf > csrf-after.json

CSRF=$(python3 -c \
  "import json; print(json.load(open('csrf-after.json'))['token'])")

curl -i -X POST -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $CSRF" \
  http://localhost:8080/api/theme/toggle

curl -i -b cookies.txt \
  http://localhost:8080/api/me
~~~

Dự kiến POST hợp lệ trả **200** với **{"darkMode":true}**, GET /api/me cũng phản ánh true. Nếu tiếp tục POST với token sai, CsrfFilter phải chặn mà không thay đổi state.

**Vì sao lấy token mới sau login?** Luồng xác thực chuẩn có thể xóa/rotate CSRF token cũ. Không giả định csrf-before.json còn dùng được sau POST /login.

### 11.9. Logout

Lấy token hiện tại của session rồi POST logout:

~~~bash
curl -sS -b cookies.txt -c cookies.txt \
  http://localhost:8080/api/csrf > csrf-logout.json

CSRF=$(python3 -c \
  "import json; print(json.load(open('csrf-logout.json'))['token'])")

curl -i -X POST -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $CSRF" \
  http://localhost:8080/logout

curl -i -b cookies.txt \
  http://localhost:8080/api/me
~~~

Dự kiến logout trả **302** tới /login?logout; request GET protected sau đó không còn session bảo mật hợp lệ và thường redirect tới login. Cookie cũ có thể vẫn tồn tại ở browser/cookie jar dù server đã invalidate session. Đừng suy ra logout thất bại chỉ vì tên cookie còn xuất hiện; kiểm hiệu lực server-side và response protected.

### 11.10. Những kết quả trên chỉ là dự kiến

Ví dụ dùng chuẩn Java/Spring Boot 3.x nhưng **chưa chạy Gradle/curl thật trong nội dung tài liệu này**. Response headers, thứ tự cookie attributes, thời điểm server tạo session và redirect có thể thay đổi bởi Spring Boot/Tomcat version, hạ tầng proxy, browser và customizations. Đối với cookie attributes, ưu tiên đọc **Set-Cookie của hệ thống đang chạy** và DevTools của browser mục tiêu.

## 12. Kiểm thử tích hợp bằng Spring Security Test và MockMvc

Cookie flags là **đặc tính của response tới browser**, trong khi MockMvc thường kiểm filter chain ở môi trường giả lập. Ta dùng MockMvc để chứng minh auth + CSRF, sau đó dùng HTTP thật/browser để kiểm cookie flag.

Trong **build.gradle**, nếu thiếu:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đây là fragment cho Gradle Groovy DSL, không phải file build.gradle hoàn chỉnh. Spring Initializr thường đã thêm starter-test; không khai báo trùng.

Tạo file **src/test/java/com/example/demo/CookieSecurityDemoApplicationTest.java**:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CookieSecurityDemoApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void loginPersistsAndCsrfStillProtectsMutation()
            throws Exception {
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "demo123"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session = (MockHttpSession)
            login.getRequest().getSession(false);
        assertNotNull(session);

        mvc.perform(get("/api/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.username").value("learner"))
            .andExpect(jsonPath("$.darkMode").value(false));

        // Session đúng nhưng thiếu CSRF vẫn không được thay đổi.
        mvc.perform(post("/api/theme/toggle").session(session))
            .andExpect(status().isForbidden());

        // Token sai cũng phải bị chặn.
        mvc.perform(post("/api/theme/toggle")
                .session(session)
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/me").session(session))
            .andExpect(jsonPath("$.darkMode").value(false));

        // Có CSRF hợp lệ: request mới được thực thi.
        mvc.perform(post("/api/theme/toggle")
                .session(session)
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.darkMode").value(true));
    }
}
~~~

Chạy:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

**Test trên kiểm Authentication, lưu session và CSRF filter**. Nó không chứng minh browser thực thi Strict/Lax/None hoặc cookie **Secure/HttpOnly**. Muốn kiểm cookie flags, dùng:
- HTTP integration test chạy embedded servlet container thật.
- Browser DevTools Application > Cookies và Network > Set-Cookie.
- E2E browser test ở HTTPS staging/production-like environment.
- Test cross-site với hai registrable domains phù hợp; chỉ đổi port trên localhost **không** mô phỏng một site khác theo SameSite.

### 12.1. Checklist kiểm cookie flags trên HTTPS

Trên HTTPS public host sau reverse proxy, quan sát **Set-Cookie** khi ứng dụng thật tạo session:

| Điều cần thấy | Vì sao |
| --- | --- |
| Cookie name **__Host-SESSION** | Prefix đòi Secure, Path=/, host-only |
| **Secure** | Chỉ gửi qua kết nối HTTPS phù hợp |
| **HttpOnly** | Không thể đọc session ID bằng document.cookie |
| **SameSite=Lax** | Cân bằng navigation UX và giảm CSRF theo thiết kế |
| **Path=/** | Điều kiện của __Host- |
| **Không có Domain** | Tránh phạm vi subdomain ngoài ý muốn |
| Không có session ID trong query/log | Giảm lộ credential |
| Session ID thay sau login | Bảo vệ session fixation mặc định |
| Logout/timeout làm mất authenticated session | Credential đã hết hiệu lực phía server |

Nếu browser **không lưu** cookie, xem tab Issues/Network để tìm lý do bị chặn: prefix sai điều kiện, Secure trên host không hợp lệ, SameSite=None thiếu Secure, Domain không hợp lệ, third-party-cookie policy hoặc certificate/TLS lỗi.

## 13. Cookie authentication so với Bearer token

### 13.1. Session cookie

~~~text
POST /login + form + CSRF
  -> Xác thực credentials
  -> Lưu SecurityContext trong HttpSession
  -> Browser nhận session cookie

GET /api/me
  -> Browser gửi cookie (nếu thỏa Secure/SameSite/Domain/Path)
  -> Server nạp session và kiểm Authentication
~~~

Trong mô hình này, browser thường tự gắn cookie; CSRF là vấn đề cần xử lý cho unsafe methods.

### 13.2. Bearer token trong Authorization header

~~~http
GET /api/me HTTP/1.1
Authorization: Bearer <access-token>
~~~

Client chủ động thêm header. Nếu không có cookie xác thực tự gửi, threat model CSRF khác. Nhưng token cần bảo vệ khỏi XSS, đánh cắp, replay và phải được xác minh cryptographically/introspection, issuer, audience, time, scope/authority.

### 13.3. JWT nằm trong cookie thì sao?

~~~http
Set-Cookie: access_token=jwt-value; Secure; HttpOnly; SameSite=Lax; Path=/
~~~

Vẫn là **cookie** do browser có thể tự gửi; cần đánh giá CSRF dựa trên cách backend lấy token từ cookie. Việc payload là JWT **không miễn trừ SameSite hoặc CSRF**. Đồng thời, backend vẫn phải xác minh chữ ký và claims của JWT. Khi token không được lưu server-side, logout/revocation còn có thể cần cơ chế riêng.

Không kết luận “HttpOnly JWT cookie = session” hay “JWT cookie = stateless hoàn toàn”: đó là các tầng lựa chọn khác nhau.

## 14. CORS, fetch credentials, third-party cookies và CHIPS

### 14.1. credentials: include không đủ để browser gửi cookie

Ví dụ frontend ở **https://app.example.com** gọi API ở **https://api.example.com**:

~~~javascript
const response = await fetch("https://api.example.com/api/me", {
    credentials: "include"
});
~~~

Browser còn phải xét:
- SameSite giữa top-level site và cookie target.
- Secure và HTTPS.
- Domain/Path.
- Cookie tồn tại, còn hạn, không bị block.
- Third-party-cookie policy, partitioning và privacy settings.
- CORS của server cho phép origin cụ thể và credentials khi muốn JavaScript đọc response.

**CORS response** cho credentialed request cần Access-Control-Allow-Origin là origin cụ thể được tin cậy và **Access-Control-Allow-Credentials: true** nếu phù hợp; không dùng wildcard *. CORS không tự cấp quyền API và không buộc browser gửi cookie bị SameSite/third-party-cookie policy chặn.

### 14.2. Cross-origin không nhất thiết cross-site

https://app.example.com và https://api.example.com **khác origin** nhưng có thể **same-site**. Nếu cookie host-only của api.example.com tồn tại, request tới api.example.com có thể gửi cookie khi URL/path/protocol và fetch credentials mode cho phép, dù CORS vẫn cần cho JS đọc response.

Đừng đặt **SameSite=None** chỉ vì frontend/backend khác subdomain; trước tiên xác minh chúng có thật sự **cross-site** hay không. Ngược lại, hai host với registrable domains khác nhau cần cân nhắc SameSite=None; Secure và browser privacy policies nếu bắt buộc cookie cross-site.

### 14.3. Partitioned cookies (CHIPS)

Một số browser hỗ trợ **Partitioned** cookie, nhằm tách cookie theo top-level site và host lưu cookie cho những bối cảnh third-party. Ví dụ:

~~~http
Set-Cookie: __Host-widget=example; Path=/; Secure; SameSite=None; Partitioned; HttpOnly
~~~

**Partitioned** yêu cầu **Secure** và có các ràng buộc/phạm vi hỗ trợ browser. Đây là công cụ cho thiết kế embedded widgets có nhu cầu cụ thể, **không phải thay thế Authentication, CSRF hay CORS** và không bảo đảm mọi third-party-cookie restriction tự biến mất.

Spring Boot có property cookie partitioned trong các phiên bản có hỗ trợ, nhưng bài tập này không bật mặc định vì không có luồng third-party widget. Kiểm phiên bản/container/browser thực tế trước khi áp dụng.

## 15. Những hiểu lầm phổ biến

| Nhận định | Vì sao sai? | Cách hiểu đúng |
| --- | --- | --- |
| “HttpOnly chặn mọi XSS.” | XSS vẫn có thể tạo request với cookie | Chống XSS ở code và CSP; HttpOnly chỉ hạn chế đọc cookie |
| “HttpOnly chặn fetch gửi cookie.” | Browser tự gắn cookie khi đủ điều kiện | HttpOnly không ngăn browser networking |
| “Secure nghĩa là cookie đã được mã hóa trong browser.” | Secure chủ yếu hạn chế vận chuyển qua HTTPS | Bảo vệ thiết bị/storage và dùng TLS thật |
| “Secure cho phép ứng dụng HTTP public an toàn.” | Nó không sinh chứng chỉ TLS | Deploy HTTPS, HSTS khi phù hợp |
| “SameSite=Strict miễn CSRF.” | Same-site subdomain/XSS/GET side effects còn tồn tại | Giữ CSRF token cho browser cookie auth |
| “SameSite=Lax không gửi cookie ở mọi cross-site request.” | Top-level safe navigation vẫn được gửi | Hiểu method và browsing context |
| “Không ghi SameSite tương đương Lax tường minh.” | Lax-by-default có ngoại lệ và browser khác nhau | Set explicit SameSite |
| “SameSite=None luôn cho cookie ở iframe.” | Third-party-cookie policies có thể chặn | Test target browsers, cân nhắc partitioning/BFF |
| “Khác port là cross-site.” | Origin tính port, site thường không | Phân biệt origin và schemeful site |
| “CORS pass nghĩa là cookie đã được gửi.” | Cookie policy độc lập | Kiểm Network Cookie và credentials mode |
| “Có JSESSIONID nghĩa là đã đăng nhập.” | Session có thể chỉ chứa CSRF/attributes | Kiểm SecurityContext/Authentication |
| “Cookie Secure nghĩa là không cần HSTS.” | Chưa giải quyết downgrade/lần kết nối ban đầu | HTTPS+HSTS và hardening đầy đủ |
| “Domain=.example.com an toàn hơn host-only.” | Scope mở ra mọi subdomain phù hợp | Chỉ khai Domain khi cần, ưu tiên host-only |
| “Path bảo vệ cookie khỏi mọi JS khác path.” | Path không phải security boundary mạnh | Cách ly bằng origin/host và kiểm soát XSS |
| “Xóa cookie là logout hoàn chỉnh.” | Phiên/token server có thể vẫn còn hiệu lực | Invalidate session/revoke credential |
| “Max-Age hết là server tự biết mọi token hết hạn.” | Browser expiry khác server validation | TTL/idle/absolute session expiration server-side |
| “__Host- tự bật HttpOnly.” | Prefix không bắt buộc HttpOnly | Vẫn set HttpOnly rõ ràng |
| “Set-Cookie xuất hiện trong fetch response.headers.” | Set-Cookie là forbidden response header với JS | Quan sát Network/DevTools hoặc server test |
| “JWT có trong cookie nên không cần kiểm chữ ký.” | Cookie transport không tạo trust | JWT validation đầy đủ và CSRF nếu browser tự gửi |
| “Tắt CSRF để login cookie hoạt động.” | Tạo lỗ hổng khi credentials tự gửi | Phối hợp form/header CSRF token đúng |

## 16. Hướng dẫn kiểm tra lỗi session cookie tại hiện trường

### 16.1. Đăng nhập trả 302/200 nhưng request kế tiếp mất session

Kiểm lần lượt:
1. Browser có nhận **Set-Cookie** không? Có bị từ chối do prefix/domain/Secure/SameSite không?
2. Request kế tiếp có header **Cookie** phù hợp không?
3. Đường dẫn, hostname, port, HTTPS và redirect có thay đổi không?
4. Session server có còn và có Authentication đã lưu không?
5. Session fixation protection có đổi ID nhưng client không lưu ID mới không?
6. Có nhiều replica mà không có shared session store/affinity không?
7. Cookie Max-Age và server idle timeout có lệch nhau không?
8. Frontend cross-origin có credentials mode/CORS đúng không?

Không tắt Secure/HttpOnly/SameSite một cách ngẫu nhiên để giải quyết 401/redirect; tìm đúng tầng gây lỗi.

### 16.2. Cookie không có Secure trên production HTTPS

Kiểm cấu hình **server.servlet.session.cookie.secure**, profile được kích hoạt, header thực sau proxy và forwarding metadata. Nếu proxy là nơi phát session cookie (không phải Spring Boot), cần sửa tại proxy. Bảo đảm edge chỉ tin forwarded headers của proxy tin cậy; không tin input của Internet client.

### 16.3. Cookie HttpOnly nhưng XSS vẫn thực hiện được thao tác

Đây là kết quả có thể xảy ra: XSS không cần đọc cookie để gọi API cùng origin. Tập trung sửa injection, DOM sinks, CSP, response access và kiểm tra authorization/transaction/CSRF phù hợp; không cố giải quyết bằng cách nâng tên cookie từ JSESSIONID thành __Host-SESSION mà không sửa XSS.

### 16.4. SameSite làm hỏng luồng thanh toán hoặc SSO

Kiểm:
- Luồng redirect top-level hay iframe/cross-site fetch?
- Redirect GET, POST binding hoặc form_post từ Identity Provider?
- Strict/Lax/None và schemeful site thực tế?
- Cookie thuộc host nào, Domain/Path và Secure đúng không?
- Có third-party cookie blocking hoặc partitioned cookie không?
- Có thể dùng **state parameter, PKCE, server-side session, BFF** hay cách tổ chức luồng khác thay vì nới cookie toàn hệ thống?

Không đổi toàn bộ session cookie sang SameSite=None chỉ vì một nhánh luồng lỗi; xem xét riêng login/callback cookie và kết cấu protocol với nhóm bảo mật.

## 17. Checklist production cho Spring Security cookie auth

1. **HTTPS bắt buộc** với chứng chỉ đáng tin cậy, không truyền credential qua HTTP.
2. Session cookie dùng **HttpOnly + Secure**, cùng **SameSite=Strict/Lax** phù hợp, có thử UX.
3. Ưu tiên **host-only** và **__Host-** khi có thể; không khai Domain rộng không cần thiết.
4. **Path=/** khi dùng __Host-, kiểm context path/reverse proxy.
5. Chỉ dùng **SameSite=None; Secure** khi có nhu cầu cross-site thực và đã đánh giá CSRF, third-party-cookie policies.
6. Bật **CSRF protection** cho browser session flows, có negative tests cho POST/PUT/PATCH/DELETE.
7. **Session fixation protection** được bật; ID thay khi login theo cơ chế chuẩn.
8. Có **server-side idle timeout/absolute lifetime** và chiến lược invalidate/revoke phù hợp.
9. **Không log session ID, Cookie/Set-Cookie, password, bearer token** hoặc key thật.
10. Xử lý **logout** thực sự invalidate HttpSession/credentials; xóa cookie đúng Name/Domain/Path nếu muốn dọn browser.
11. Kiểm **XSS và CSP**; HttpOnly không chống việc script ác ý gọi API cùng origin.
12. Bảo vệ **authorization, ownership, tenant** độc lập với cookie flags.
13. Rà soát **third-party subdomains**, DNS takeover, cookie tossing và trust boundary.
14. Kiểm **CORS, fetch credentials, SameSite/Secure** đồng thời nếu frontend/backend khác origin.
15. Test **response public HTTPS sau reverse proxy**, không chỉ ứng dụng local HTTP.
16. Kiểm mọi **SecurityFilterChain**, static hosting/gateway và session store trong môi trường nhiều replica.
17. Đánh giá browser support của SameSite/Partitioned/prefixes, không chỉ một browser version.
18. Kiểm lại chính sách khi thay đổi domain, CDN, login provider hoặc browser embedding.

## 18. Câu hỏi tự đánh giá

1. HttpOnly có bảo đảm một script XSS không thể gửi fetch tới API cùng origin bằng session hiện hành không? Vì sao?
2. Secure làm điều gì với cookie và không làm điều gì với chứng chỉ TLS?
3. Vì sao localhost HTTP có thể có hành vi Secure cookie khác production HTTP trên một hostname thật?
4. SameSite=Lax khác Strict ở top-level navigation từ website khác ra sao?
5. SameSite=None cần attribute nào và có bảo đảm third-party cookie luôn được gửi không?
6. Vì sao http://app.example.com và https://app.example.com được coi khác site theo schemeful same-site?
7. app.example.com và api.example.com là same-origin hay same-site? Những tác động nào đến CORS và cookie?
8. Khi có subdomain không tin cậy, SameSite=Strict có đủ ngăn mọi CSRF không?
9. Domain=example.com khác cookie host-only như thế nào? Vì sao Domain rộng có rủi ro?
10. Prefix __Host- đòi những điều kiện gì? Nó có tự bật HttpOnly không?
11. Browser cookie hết hạn và HttpSession hết hạn là cùng một biến cố không?
12. Vì sao phải đổi session ID sau login và giữ cookie jar mới trong curl?
13. Nếu POST login thành công nhưng GET /api/me lại redirect login, cần kiểm những bước nào?
14. Khi logout, chỉ xóa cookie ở browser có bảo đảm credential đã bị thu hồi không?
15. Khi JWT được đựng trong cookie HttpOnly, có còn cần đánh giá CSRF không?
16. MockMvc có thể chứng minh browser thật sẽ chặn SameSite cross-site không? Cần test gì thêm?
17. Vì sao **Set-Cookie** không được JavaScript đọc qua fetch response.headers?
18. CSRF token có phải session ID hay password khác tên không?
19. Một ứng dụng React ở localhost:5173 và API ở localhost:8080 khác origin. Có phải luôn khác site không?
20. Nếu phải dùng iframe tích hợp trên site khác, sẽ cân nhắc SameSite, third-party cookie restrictions, CSP và session model thế nào?

**Ghi nhớ:** **HttpOnly** hạn chế JavaScript trực tiếp đọc cookie; **Secure** hạn chế cookie bị gửi qua HTTP; **SameSite** giới hạn gửi cookie ở một số request cross-site. Chúng hoạt động ở **các ranh giới khác nhau** và không thay thế **CSRF, XSS protection, HTTPS, authorization hoặc session lifecycle**. Trên Spring Boot, hãy đặt cookie flags phù hợp và **kiểm chứng Set-Cookie thực tế trên HTTPS sau proxy**, không chỉ đọc properties.

## Tài liệu chính thức để nghiên cứu tiếp

- MDN — Set-Cookie, HttpOnly/Secure/SameSite/prefixes: https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie
- MDN — HTTP Cookies: https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Cookies
- MDN — Third-party cookies: https://developer.mozilla.org/en-US/docs/Web/Privacy/Guides/Third-party_cookies
- MDN — Document.cookie và HttpOnly: https://developer.mozilla.org/en-US/docs/Web/API/Document/cookie
- Spring Boot 3.5 — Common Application Properties (server.servlet.session.cookie.*): https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html
- Spring Security 6.5 — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security — CSRF protection: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
- OWASP — CSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
