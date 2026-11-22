# SameSite hỗ trợ bảo vệ nhưng không thay thế mọi kiểm tra CSRF

## 1. Mục tiêu và tình huống mở đầu

Một ứng dụng ngân hàng dùng cookie phiên để nhận diện người dùng. Lập trình viên cấu hình:

~~~http
Set-Cookie: JSESSIONID=abc123; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Vì `SameSite=Lax` hạn chế việc gửi cookie trong nhiều yêu cầu từ trang web khác, nhóm phát triển cân nhắc bỏ kiểm tra CSRF token. Đó là kết luận nguy hiểm: **SameSite là một lớp giảm rủi ro CSRF ở trình duyệt, không tự thay thế toàn bộ chính sách kiểm tra yêu cầu thay đổi trạng thái.**

Hai trường hợp rất dễ bỏ sót:

- Kẻ tấn công khiến nạn nhân mở một liên kết `GET` từ site khác đến endpoint **có tác dụng thay đổi dữ liệu**. Với `Lax`, cookie thường vẫn được gửi trong điều hướng cấp cao nhất bằng phương thức an toàn như `GET`. Nếu server thay đổi dữ liệu ở `GET`, có thể xảy ra CSRF.
- Nội dung độc hại trên `https://evil.example.com` gửi `POST` tới `https://app.example.com`. Hai origin khác nhau nhưng trong nhiều tình huống lại **cùng site**, nên cả `SameSite=Strict` và `Lax` vẫn không cản cookie; chính sách CSRF token hoặc kiểm tra nguồn chặt chẽ ở server mới giúp chặn.

Sau bài này, bạn sẽ phân biệt site và origin; giải thích đúng ba chế độ `Strict`, `Lax`, `None`; biết lúc nào cookie được gửi; kiểm tra những giới hạn của SameSite; cấu hình session cookie và kiểm tra CSRF trong Spring Security Servlet, liên hệ WebFlux/SPA; và kiểm thử cả đường đi hợp lệ lẫn các yêu cầu do site khác tạo.

**Phạm vi:** Spring Security 6.x với Java 17+, Spring Boot 3.5 cho ví dụ Servlet. Một số hành vi cookie phụ thuộc phiên bản trình duyệt, ngữ cảnh điều hướng và chính sách chặn third-party cookie; không nên giả định mọi trình duyệt luôn giống nhau.

## 2. CSRF xảy ra như thế nào?

**Cross-Site Request Forgery (CSRF)** là việc một bên khiến trình duyệt của nạn nhân tạo một yêu cầu đến ứng dụng mà nạn nhân đã có trạng thái xác thực, với hành động mà nạn nhân không chủ ý cho phép.

Điều kiện thường gặp:

1. Nạn nhân đã đăng nhập `https://app.example.com`; trình duyệt có cookie phiên hợp lệ.
2. Nạn nhân truy cập `https://attacker.example.net` do kẻ tấn công điều khiển.
3. Trang độc hại kích hoạt một yêu cầu tới ứng dụng, ví dụ bằng biểu mẫu HTML.
4. Nếu trình duyệt tự gắn cookie xác thực và server chấp nhận yêu cầu không có kiểm chứng nguồn/challenge thích hợp, thao tác được thực hiện dưới quyền nạn nhân.

Ví dụ mô phỏng một form độc hại:

~~~html
<form method="post" action="https://app.example.com/profile/email">
  <input type="hidden" name="email" value="attacker@example.net">
</form>
<script>
  document.forms[0].submit();
</script>
~~~

Đây chỉ là minh họa cách browser có thể gửi một `POST` bằng HTML form. Nó **không bảo đảm thành công**: `SameSite=Lax/Strict` có thể không gửi cookie trong ngữ cảnh cross-site; và nếu server dùng CSRF token chính xác, request thiếu token sẽ bị từ chối ngay cả khi cookie vẫn được gửi.

**Same-Origin Policy (SOP)** thường ngăn JavaScript của trang khác **đọc phản hồi** từ ứng dụng nếu không có CORS cho phép. SOP **không ngăn tất cả yêu cầu được tạo**: cross-origin HTML form submission và điều hướng vẫn có thể diễn ra. Vì thế “JavaScript của attacker không đọc được response” không đồng nghĩa API không bị CSRF.

CSRF gắn với **credential mà browser tự gửi**, điển hình là cookie phiên, nhưng cũng phải xem xét HTTP Basic hoặc cơ chế client tự động xác thực khác. Với API chỉ chấp nhận bearer token trong `Authorization` được ứng dụng chủ động thêm từng request, bề mặt CSRF cổ điển thường khác; nguy cơ XSS/đánh cắp token vẫn còn.

## 3. SameSite kiểm soát điều gì?

`SameSite` là một thuộc tính `Set-Cookie` hướng dẫn **trình duyệt** khi nào được gửi cookie trong những request thuộc ngữ cảnh cùng site hoặc khác site. Nó không phải cơ chế kiểm chứng quyền truy cập ở server và không được mọi loại HTTP client ngoài browser tuân theo.

Ví dụ:

~~~http
Set-Cookie: __Host-session=s3ss10n; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- `__Host-session`: cookie name có tiền tố `__Host-`; browser hỗ trợ tiền tố này yêu cầu `Secure`, `Path=/` và **không có `Domain`. Tiền tố giúp hạn chế một số rủi ro cookie injection giữa subdomain, không tạo CSRF token.
- `Secure`: chỉ gửi cookie qua kết nối bảo mật, thông thường HTTPS. Không phải hàng rào CSRF.
- `HttpOnly`: JavaScript không thể trực tiếp đọc cookie qua `document.cookie`. Không ngăn XSS gửi các request đã xác thực.
- `Path=/`: phạm vi đường dẫn mà cookie áp dụng. Path không được xem là ranh giới bảo mật độc lập.
- `SameSite=Lax`: áp dụng chính sách gửi cookie theo quan hệ site và loại request.

Server không nhận được thuộc tính `SameSite` trong header `Cookie` của request; server thấy **giá trị cookie đã được browser quyết định gửi**. Vì vậy Spring Security vẫn cần kiểm tra credential, authorization và CSRF theo chính sách, không thể coi thuộc tính của cookie như một proof người dùng chủ ý thực hiện request.

### 3.1. Site không đồng nghĩa origin

**Origin** là bộ ba `scheme://host:port`. Hai URL khác cổng hoặc khác subdomain là **khác origin**.

**Site** trong cách tính SameSite hiện đại thường dựa trên **scheme + registrable domain** (site theo scheme), trong đó registrable domain xác định theo Public Suffix List. Nhiều subdomain cùng một tên miền đăng ký được xem là **cùng site** dù khác origin; cổng không phân chia site theo cùng cách origin.

| URL gửi yêu cầu → URL nhận | Same-origin? | Same-site trong ngữ cảnh thông thường? | Ý nghĩa |
| --- | --- | --- | --- |
| `https://app.example.com` → `https://app.example.com` | Có | Có | Cùng origin |
| `https://evil.example.com` → `https://app.example.com` | Không | Có | Sibling subdomain vẫn cùng site |
| `https://app.example.com:8443` → `https://app.example.com` | Không | Có | Khác port, cùng site |
| `https://attacker.example.net` → `https://app.example.com` | Không | Không | Cross-site |
| `http://app.example.com` → `https://app.example.com` | Không | Thông thường không (schemeful) | HTTP/HTTPS khác scheme |

Bảng giả định ví dụ tên miền thông thường. Với hostname đặc biệt, domain nằm trên Public Suffix List, localhost, IP, trình duyệt nhúng hoặc các chuỗi điều hướng, phải kiểm tra hành vi thực tế; không tự cắt chuỗi theo dấu chấm để suy ra site. Các redirect cũng có thể ảnh hưởng việc phân loại ngữ cảnh gửi cookie.

**Hệ quả:** kẻ tấn công chiếm một subdomain, nội dung do người dùng tự host trên sibling subdomain hoặc một dịch vụ bên thứ ba được CNAME về subdomain trong cùng site có thể tạo request tới ứng dụng mà browser xem là **same-site**. `SameSite=Strict` không chặn chỉ vì request đó khác origin. Cookie **host-only** của `app.example.com` vẫn được gửi **tới app.example.com** khi một trang sibling same-site khởi tạo request; host-only giới hạn **đích** cookie, không bảo đảm nguồn khởi tạo request cùng origin.

### 3.2. Các giá trị Strict, Lax và None

| Giá trị | Quy tắc cốt lõi | Lợi ích | Điều cần cân nhắc |
| --- | --- | --- | --- |
| `Strict` | Chỉ gửi cookie trong ngữ cảnh được xem là same-site | Hạn chế mạnh hơn các điều hướng cross-site | Liên kết đi từ site ngoài có thể không mang session cookie ở lần vào đầu; vẫn cho phép request từ origin khác nhưng cùng site |
| `Lax` | Gửi trong ngữ cảnh same-site; thêm trường hợp **cross-site top-level navigation bằng phương thức an toàn** như GET | Cân bằng giữa chống CSRF phổ biến và điều hướng từ site ngoài | GET gây thay đổi trạng thái vẫn nguy hiểm; sibling subdomain cùng site không bị chặn |
| `None` | Cho phép cookie trong ngữ cảnh cross-site; trình duyệt hiện đại yêu cầu đi cùng `Secure` | Hỗ trợ một số SSO/embed/cross-site flows hợp lệ | Ít phòng vệ CSRF nhờ SameSite; third-party cookie vẫn có thể bị trình duyệt chặn |

Các chính sách trên nói về **điều kiện gửi một cookie**, không phán quyết request có hợp lệ theo nghiệp vụ hay không. Cần kiểm tra đồng thời các thuộc tính `Domain`, `Path`, `Secure`, thời hạn, trình duyệt và bối cảnh iframe/navigation.

### 3.3. Bảng hành vi browser cần nhớ

Giả định cookie là cookie phiên có `Domain/Path/Secure` phù hợp với **đích** và không bị chính sách trình duyệt khác chặn:

| Ngữ cảnh tạo request | Strict | Lax (khai báo tường minh) | None; Secure |
| --- | --- | --- | --- |
| Same-site POST từ sibling subdomain tới app | Có thể gửi | Có thể gửi | Có thể gửi |
| Cross-site top-level GET navigation | Không gửi | **Có gửi** | Có thể gửi |
| Cross-site top-level POST form submission | Không gửi | Thông thường không gửi | Có thể gửi |
| Cross-site subresource GET (`img`/`script`) | Không gửi | Không gửi | Có thể gửi |
| Cross-site iframe navigation | Không gửi | Không gửi theo ngoại lệ top-level | Có thể gửi, tùy third-party cookie policies |

Bảng này mô tả chính sách SameSite theo trường hợp phổ biến, không phải yêu cầu bắt buộc mọi browser phiên bản đều hành xử y hệt. Cross-site requests có redirect chain, cookie được set ở response và môi trường trình duyệt khác nhau cần được kiểm thử riêng.

**Ngoại lệ quan trọng:** Khi **bỏ trống** thuộc tính `SameSite`, một số trình duyệt dùng **Lax-by-default** với biến thể dễ dãi hơn: cookie mới được tạo trong khoảng ngắn (chẳng hạn 2 phút) vẫn có thể được gửi trong một số **cross-site top-level POST**. Đây **không phải** quy tắc của cookie khai báo `SameSite=Lax` tường minh. Không dựa vào default bất định để thiết kế an ninh; hãy cấu hình tường minh và vẫn dùng CSRF protection.

## 4. Vì sao SameSite không thay thế kiểm tra CSRF?

### 4.1. Lax vẫn gửi cookie khi điều hướng GET cấp cao nhất

Giả sử ứng dụng viết sai quy tắc HTTP, dùng endpoint:

~~~http
GET /account/delete?confirm=true HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=...
~~~

Nếu người dùng nhấn liên kết tới URL đó từ site ngoài, `SameSite=Lax` có thể cho browser gửi cookie phiên. Spring Security CSRF mặc định **không yêu cầu CSRF token cho các HTTP method được xem là safe**, bao gồm `GET`. Vì vậy lỗi gốc là **server đã thay đổi trạng thái qua GET**.

**Cách sửa đúng:** chuyển thao tác sang `POST`/`DELETE` tương ứng, có xác thực và phân quyền, yêu cầu CSRF token khi credential được gửi tự động, dùng màn hình xác nhận hoặc bước xác thực lại khi cần. Không coi “đổi thành POST” là đủ nếu CSRF vẫn bị tắt.

Phải bảo đảm các method `GET`, `HEAD`, `OPTIONS`, `TRACE` không tự thực hiện thay đổi nghiệp vụ; URL có tên `/logout` hoặc `/delete` không làm method trở thành an toàn.

### 4.2. Same-site nhưng cross-origin: kẻ xấu ở subdomain

~~~text
Nạn nhân đã đăng nhập: https://app.example.com
Nội dung bị chiếm:     https://blog.example.com
Trang blog gửi:        POST https://app.example.com/profile/email

Cùng scheme và registrable domain -> same-site.
Khác host -> khác origin.
Cookie session của app có thể được gửi tới app.
~~~

`SameSite=Strict`/`Lax` chỉ xét **site**, không bắt nguồn phải **cùng origin**. Nếu blog hoặc một subdomain khác bị chiếm hoặc cho phép người dùng đăng nội dung HTML chủ động, attacker có thể tạo request gây thay đổi trạng thái mà cookie vẫn đi kèm.

Phòng vệ cần ở backend: CSRF token hợp lệ **không tự được gửi bởi browser**, kết hợp `Origin`/`Referer` checking theo origin tin cậy, `Sec-Fetch-Site` policy cẩn thận với `same-site`, và nguyên tắc không cho các subdomain không đáng tin kiểm soát cookie toàn domain.

### 4.3. CSRF ngay bên trong ứng dụng (client-side CSRF)

Một SPA có đoạn JavaScript nhận URL, path hoặc tham số từ input không tin cậy rồi dùng thông tin đó để tạo request thay đổi dữ liệu. Kẻ tấn công có thể điều khiển input khiến **JavaScript chính chủ** gửi request tới endpoint nhạy cảm.

Request lúc đó được tạo từ origin của ứng dụng, nên SameSite, Origin và Fetch Metadata có thể đều trông hợp lệ. Nếu JavaScript tự gắn CSRF header vào mọi request mà không giới hạn endpoint/phương thức theo cấu hình đáng tin, cơ chế token cũng có thể bị sử dụng gián tiếp.

**Cách phòng ngừa:** không để dữ liệu không tin cậy quyết định tự do URL/method/body cho authenticated request; dùng allowlist endpoint, schema validation, bất biến nghiệp vụ, authorization ở server; bảo vệ XSS và có bước xác nhận/transaction binding cho thao tác nhạy cảm. CSRF token không phải giải pháp cho mọi lỗi lập trình client-side.

### 4.4. XSS có thể vượt qua nhiều hàng rào CSRF

Nếu attacker chạy được script trong origin hợp lệ (XSS), script thường có thể gửi request cùng origin, truy cập DOM để lấy token được đưa ra trong form hoặc sử dụng session cookie được browser tự gửi. `HttpOnly` ngăn đọc trực tiếp cookie nhưng không ngăn script gửi yêu cầu đã xác thực.

Vì vậy phải chống XSS bằng output encoding, CSP phù hợp, xử lý HTML/user content và phụ thuộc thư viện an toàn. **CSRF protection và chống XSS là hai lớp khác nhau**; một lớp không làm mất nhu cầu của lớp kia.

### 4.5. Luồng SSO, iframe và third-party cookie

Ứng dụng có thể dùng identity provider bên ngoài rồi redirect về callback, hoặc cần iframe giữa các site. `Strict` có thể không gửi cookie phiên ở lần điều hướng đầu từ IdP. `Lax` thường hoạt động với cross-site top-level GET callback, nhưng có thể cản callback dùng form POST ở một số kiểu `response_mode=form_post`. `None; Secure` phục vụ cross-site cookie nhưng làm tăng nhu cầu CSRF defense và vẫn phụ thuộc chính sách chặn third-party cookie.

Với OAuth/OIDC, phải tiếp tục xác minh `state`, PKCE, `nonce` khi áp dụng, issuer/redirect URI, token và session binding. `SameSite` **không thay thế** `state` hoặc bảo vệ login CSRF/mix-up. Cần kiểm thử từng provider/callback cụ thể trước khi chọn chính sách cookie.

### 4.6. Cookie bị thiếu hoặc các client không giống browser

Các ứng dụng đã phát nhiều cookie (session ID, remember-me, OAuth state, CSRF cookie, app preference) có thể gán SameSite **khác nhau**. Đặt SameSite chỉ cho `JSESSIONID` không đảm bảo cookie xác thực khác cũng được bảo vệ. Một số ứng dụng xác thực bằng HTTP Basic hoặc cookie do reverse proxy cấp còn vượt ngoài cấu hình session của ứng dụng.

HTTP clients như `curl` có thể gửi Cookie header theo ý muốn và không thực thi mọi quy tắc browser về SameSite. Vì thế **không kiểm tra SameSite ở server bằng cách mong client phải tuân theo**; cần xác thực, phân quyền và cơ chế CSRF cho browser flows theo chính sách.

## 5. Cơ chế phòng thủ CSRF chính và vai trò từng lớp

Một ứng dụng cookie-based có thể kết hợp:

1. **Synchronizer CSRF token:** server cấp token khó đoán, lưu expected token phía server, đưa token vào HTML form hoặc JavaScript một cách an toàn, và kiểm tra token đi kèm mỗi request thay đổi trạng thái. Browser không tự thêm token từ form của ứng dụng vào một form tùy ý của attacker.
2. **Signed double-submit cookie:** phù hợp cho một số hệ không lưu CSRF state trong server session. Backend phát token được gắn bằng MAC với session đáng tin, browser gửi cookie và JS/form gửi **bản sao token trong header/field**; backend phải kiểm chứng chữ ký và ràng buộc session, không chỉ so hai chuỗi attacker có thể cùng điều khiển.
3. **`Origin`/`Referer` verification:** so sánh **origin đầy đủ** (scheme, host, port) của request với danh sách được phép/target origin. Không chỉ kiểm tra hậu tố tên miền bằng `endsWith("example.com")`.
4. **Fetch Metadata:** dùng `Sec-Fetch-Site`, `Sec-Fetch-Mode`, `Sec-Fetch-Dest` để từ chối các unsafe cross-site request rõ ràng; có fallback cho client/browsers thiếu header và xử lý `same-site` khác `same-origin`.
5. **SameSite cookie:** giảm trường hợp browser tự gửi session cookie từ cross-site contexts; nên cấu hình tường minh theo nhu cầu UX.
6. **HTTP method discipline và Content-Type policy:** thao tác thay đổi dữ liệu dùng unsafe method, không cho GET gây side effect; API JSON có thể kiểm tra `Content-Type: application/json` và custom header để buộc browser đi qua CORS preflight trong trường hợp thích hợp, nhưng đây không thay authorization và không phải hàng rào duy nhất.
7. **Kiểm tra quyền/ownership và xác thực lại:** CSRF token hợp lệ không chứng minh người dùng có quyền đổi tài khoản khác hay đủ xác thực để chuyển tiền. Các hành động nhạy cảm cần authorization và đôi khi reauthentication/step-up riêng.

**CSRF token nên có thuộc tính gì?** Khó đoán bằng nguồn ngẫu nhiên mật mã, ràng buộc với session thích hợp, kiểm tra bằng server-side code trước khi cập nhật dữ liệu, không lộ qua log/URL và được làm mới/invalidate theo vòng đời phiên nếu framework yêu cầu. Với form server-rendered, thường dùng token trong hidden field; với SPA, thường dùng header chuyên dụng trên request thay đổi dữ liệu.

**Bảo vệ phụ:** `SameSite`, `HttpOnly`, `Secure`, HTTPS, anti-XSS, CORS và rate limiting đóng góp các mục đích khác nhau. Không dùng một cờ cookie để thay toàn bộ kiểm tra tại endpoint.

## 6. Spring Security Servlet: CSRF được xử lý thế nào?

Trong Spring Security Servlet 6.x:

- `CsrfFilter` xử lý kiểm tra CSRF theo chính sách và từ chối request cần CSRF mà không có token hợp lệ.
- `CsrfTokenRepository` lưu và lấy expected token. Mặc định là `HttpSessionCsrfTokenRepository`.
- `CsrfTokenRequestHandler` đưa token cho view/controller và tìm token được submit từ request. Spring Security 6 dùng `XorCsrfTokenRequestAttributeHandler` theo mặc định để hỗ trợ masking chống BREACH khi xuất token.
- Theo mặc định, các HTTP method `GET`, `HEAD`, `TRACE`, `OPTIONS` không bị CSRF token guard; các method như `POST`, `PUT`, `PATCH`, `DELETE` được kiểm tra.
- Một token thường có thể truy cập qua request attribute `_csrf` hoặc `CsrfToken.class.getName()`; trong HTML form dùng `_csrf` hidden field và giá trị đã được request handler cung cấp.
- Bật form login, session hay Spring Security không có nghĩa SameSite đã thay CSRF. Spring Security **bật CSRF protection theo mặc định**; không tùy tiện gọi `csrf.disable()` chỉ vì cookie đã có `SameSite`.

### 6.1. Vì sao CSRF token cần nằm ngoài cookie tự gửi?

Nếu ứng dụng chỉ kiểm tra “browser đã gửi cookie phiên”, thì request do trang attacker tạo vẫn có thể được browser đính kèm cookie. Với synchronizer token, server yêu cầu thêm một giá trị trong **form field/header mà browser không tự động lấy từ cookie và đưa vào**. Kẻ tấn công từ origin không tin cậy thông thường không thể đọc trang/form của người dùng để lấy token qua SOP, nên request thiếu token bị từ chối.

Nếu dùng `CookieCsrfTokenRepository` cho SPA, token có thể nằm trong cookie `XSRF-TOKEN` **đọc được bằng JavaScript** và frontend tự gửi qua `X-XSRF-TOKEN`. Đây là cơ chế khác với một session cookie `HttpOnly`: session cookie vẫn phải giữ HttpOnly khi phù hợp, còn CSRF cookie được thiết kế cho JS đọc. Việc bật `withHttpOnlyFalse()` cho **CSRF cookie** không phải lời khuyên tắt HttpOnly cho **session/authentication cookie**.

Spring Security 6 còn có xử lý token **deferred** và **BREACH masking**. Khi SPA lấy raw CSRF token từ cookie rồi gửi header, cần dùng cấu hình `CsrfTokenRequestHandler` cho SPA theo tài liệu chính thức, và phát/cấp lại token khi login/logout làm token cũ bị xóa. Chỉ đổi repository rồi bỏ qua request handler hoặc cookie lifecycle có thể khiến POST hợp lệ nhận 403; không giải quyết bằng cách tắt CSRF.

## 7. Ví dụ thực hành Spring Boot 3.5 + Spring Security 6.5, Java 17

Ví dụ chạy một **ứng dụng Servlet riêng** có form server-rendered. Nó cố tình giữ cả `SameSite=Lax` **và** CSRF token mặc định. Một POST đổi counter chỉ thành công khi request đã đăng nhập và có CSRF token hợp lệ; GET chỉ đọc counter.

Cần JDK 17+, Maven và các file dưới đây:

~~~text
samesite-csrf-demo/
├── pom.xml
└── src/main/
    ├── java/example/csrf/CsrfSameSiteDemoApplication.java
    └── resources/application.yml
~~~

**`pom.xml`:**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.0</version>
    <relativePath/>
  </parent>
  <groupId>example</groupId>
  <artifactId>samesite-csrf-demo</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
  </dependencies>
</project>
~~~

**`src/main/resources/application.yml`:**

~~~yaml
server:
  port: 8080
  servlet:
    session:
      cookie:
        same-site: lax
~~~

Thuộc tính `server.servlet.session.cookie.same-site` được Spring Boot hỗ trợ cho session cookie trong các embedded Servlet container phù hợp. Với môi trường production chạy HTTPS, thêm cấu hình `secure: true` và cân nhắc tên cookie/`HttpOnly`, đường dẫn, TTL, reverse proxy. Mẫu giữ HTTP ở localhost để dễ thử nghiệm nên không ép `Secure` trong YAML minh họa; không triển khai production trên HTTP.

**`src/main/java/example/csrf/CsrfSameSiteDemoApplication.java`:**

~~~java
package example.csrf;

import java.util.concurrent.atomic.AtomicInteger;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class CsrfSameSiteDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(CsrfSameSiteDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login").permitAll()
                .anyRequest().authenticated())
            .formLogin(Customizer.withDefaults())
            // CSRF đang BẬT mặc định; không gọi csrf.disable().
            .build();
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
            User.withUsername("demo")
                // Chỉ dành cho demo: không lưu password rõ trong production.
                .password("{noop}demo123")
                .roles("USER")
                .build());
    }
}

@RestController
class DemoEndpoints {
    private final AtomicInteger changes = new AtomicInteger();

    @GetMapping("/")
    String home() {
        return "Open /form after login; GET /status to read changes";
    }

    @GetMapping("/status")
    String status() {
        return "changes=" + changes.get();
    }

    @GetMapping(value = "/form", produces = MediaType.TEXT_HTML_VALUE)
    String form(HttpServletRequest request) {
        CsrfToken csrf = (CsrfToken) request.getAttribute(
            CsrfToken.class.getName());

        // CsrfToken.getToken() kích hoạt deferred token khi cần.
        return """
            <!doctype html>
            <html lang="vi">
              <body>
                <h1>Thay đổi trạng thái thử nghiệm</h1>
                <form action="/change" method="post">
                  <input type="hidden" name="%s" value="%s">
                  <button type="submit">Thực hiện thay đổi</button>
                </form>
              </body>
            </html>
            """.formatted(csrf.getParameterName(), csrf.getToken());
    }

    @PostMapping("/change")
    String change() {
        return "changes=" + changes.incrementAndGet();
    }
}
~~~

**Giải thích code:** `@SpringBootApplication` quét controller trong cùng package. Mọi URL trừ `/` và `/login` đều cần đăng nhập. GET `/form` lấy CSRF token từ request attribute và đưa nó vào hidden field. Vì đây là giá trị do Spring Security sinh, nó không phải dữ liệu tùy ý đến từ người dùng. Khi trình duyệt submit, `CsrfFilter` kiểm tra token trước khi gọi method `change()`; method chỉ chạy nếu các bước kiểm tra thành công. `AtomicInteger` là trạng thái demo trong một process, không là kho dữ liệu thực.

Chạy ứng dụng:

~~~bash
mvn spring-boot:run
~~~

Kiểm thử bằng browser:

1. Mở `http://localhost:8080/status` khi chưa login: được chuyển tới trang login.
2. Đăng nhập bằng `demo` / `demo123` tại `http://localhost:8080/login`.
3. Mở `http://localhost:8080/form`, xem HTML có input ẩn `name="_csrf"` và value được sinh.
4. Nhấn nút: `POST /change` thành công, phản hồi đầu tiên trong phiên chạy mới là `changes=1`.
5. Mở `/status`: chỉ đọc trạng thái; không tự tăng số lần.
6. Dùng DevTools/HTTP client phát lại POST với **cookie phiên hợp lệ nhưng bỏ `_csrf`**: Spring Security trả **403 Forbidden**; counter không tăng.
7. Phát lại POST với `_csrf` sai hoặc hết hiệu lực sau thay đổi phiên: **403 Forbidden**. Khi đăng xuất, phải lấy token mới theo luồng login/session mới.

**Điểm đáng chú ý:** Spring Security yêu cầu token đúng **ngay cả khi browser gửi session cookie**. Việc đặt cookie `SameSite=Lax` chỉ thêm một lớp khiến một số request cross-site không mang cookie; nó không làm bộ lọc CSRF bỏ qua xác minh.

### 7.1. Kết quả curl nào là đáng tin?

~~~bash
# Không có phiên: chuyển tới trang login.
curl -i http://localhost:8080/status

# Khi đã có phiên được login, nhưng không gửi CSRF token:
# curl -i -b "JSESSIONID=<valid-session-id>" -X POST \
#   http://localhost:8080/change
# Kết quả: HTTP 403 (nếu phiên có quyền hợp lệ).
~~~

Giá trị `<valid-session-id>` là ký hiệu, phải thay bằng session ID của **chính phiên thử nghiệm**; không sử dụng cookie của người khác. Vì curl không mô phỏng đầy đủ chính sách SameSite của trình duyệt, bài test này dùng để **xác minh server-side CSRF guard**, không dùng để kết luận cách browser thực sự gửi cookie trong cross-site navigation.

**Không lấy token ở URL:** Mọi ví dụ cố ý tránh đặt CSRF token trong query string. Giá trị token trong URL có thể lộ vào history/log/analytics. Dùng form body hoặc header thích hợp.

## 8. Kiểm thử tự động với MockMvc

Spring Security Test cho phép giả lập một người dùng hợp lệ và tự thêm CSRF token vào request. Nếu muốn chạy bài kiểm thử, thêm hai test dependencies vào `pom.xml`:

~~~xml
<dependency>
  <groupId>org.springframework.boot</groupId>
  <artifactId>spring-boot-starter-test</artifactId>
  <scope>test</scope>
</dependency>
<dependency>
  <groupId>org.springframework.security</groupId>
  <artifactId>spring-security-test</artifactId>
  <scope>test</scope>
</dependency>
~~~

Tạo file **`src/test/java/example/csrf/CsrfSameSiteDemoApplicationTests.java`**:

~~~java
package example.csrf;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfSameSiteDemoApplicationTests {
    @Autowired
    MockMvc mvc;

    @Test
    void authenticatedPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/change").with(user("demo")))
            .andExpect(status().isForbidden());
    }

    @Test
    void authenticatedPostWithCsrfSucceeds() throws Exception {
        mvc.perform(post("/change")
                .with(user("demo"))
                .with(csrf()))
            .andExpect(status().isOk());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Hai phép thử mô tả logic kỳ vọng của `CsrfFilter`: request đã xác thực nhưng thiếu CSRF token bị từ chối, request đã xác thực và có token được chấp nhận. Bộ test này **không mô phỏng toàn bộ thuật toán cookie SameSite trong trình duyệt thật**; để kiểm tra `Strict/Lax/None` phải dùng browser, hostname/HTTPS và môi trường site khác nhau phù hợp.

## 9. Session cookie SameSite trong Spring Boot và các cookie khác

### 9.1. Cấu hình session cookie Servlet

~~~yaml
server:
  servlet:
    session:
      cookie:
        same-site: lax
        http-only: true
        # Môi trường production HTTPS: thêm secure: true
~~~

Hoặc trong `application.properties`:

~~~properties
server.servlet.session.cookie.same-site=lax
server.servlet.session.cookie.http-only=true
~~~

Đây là cấu hình cho session cookie của Servlet container/Spring Session tương ứng. **Nó không tự thay đổi mọi cookie khác** do ứng dụng, proxy, OIDC library hoặc dịch vụ ngoài cấp. Với cookie tự tạo, có thể cần `ResponseCookie`, `CookieSameSiteSupplier` (Servlet, Boot), hoặc cơ chế của framework để đặt SameSite. Kiểm tra header `Set-Cookie` thực tế sau login, refresh, logout và callback.

### 9.2. Domain và Path có ảnh hưởng bảo mật

~~~http
Set-Cookie: SESSION_ID=s1; Domain=example.com; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

Cookie `Domain=example.com` có thể được gửi tới nhiều subdomain trong phạm vi đó. Đây là quyết định phải cân nhắc khi có user-content hoặc third-party service trên subdomain. **Không đặt `Domain` nếu không thực sự cần chia sẻ cookie.** Host-only cookie cùng tiền tố `__Host-` giúp ngăn subdomain đặt cookie tương ứng cùng tên cho parent host trong các browser hỗ trợ tiền tố.

`Path` là giới hạn đích gửi cookie, không phải rào ngăn JavaScript hoặc các ứng dụng không tin cậy trên cùng origin. Không xem port hoặc path là security boundary thay cho authorization.

### 9.3. Strict, Lax và None: chọn theo luồng thật

- **Strict:** phù hợp cookie rất nhạy cảm nếu người dùng không cần cookie ở navigation bắt nguồn ngoài site. Có thể ảnh hưởng deep links, email links, SSO và trải nghiệm quay lại website.
- **Lax:** thường hợp lý cho session của web thông thường có liên kết/redirect từ site ngoài. Phải tiếp tục giữ CSRF filter cho unsafe methods và bảo đảm GET chỉ đọc.
- **None; Secure:** dành cho một số tương tác cross-site có chủ đích (embedded app, luồng callback nhất định) khi browser cho phép; cần CSRF token/Origin defenses phù hợp và lưu ý third-party cookie blocking.

Lựa chọn từng cookie theo mục đích. Một ứng dụng có thể dùng cookie phiên `Lax` nhưng một cookie phục vụ giao thức redirect khác có policy khác; đừng gán `None` cho mọi cookie để “chữa” lỗi SSO mà không đánh giá tấn công.

## 10. SPA, cookie CSRF token và vấn đề masked token

Các SPA dùng `fetch`/XHR thường không có HTML form do server render. Có hai mô hình phổ biến:

**SPA + backend session/BFF:** browser có session cookie `HttpOnly`; frontend lấy CSRF token thông qua trang bootstrap/endpoint hợp lệ hoặc CSRF cookie mà frontend có thể đọc, rồi gắn vào header cho `POST`/`PUT`/`PATCH`/`DELETE`. Server vẫn so token với expected token của request/session.

**SPA chỉ dùng bearer Authorization header:** nếu mọi request xác thực bắt buộc có `Authorization: Bearer ...` do JavaScript chủ động thêm và **không** có cookie/Basic tự động gửi được server chấp nhận, mô hình CSRF cổ điển có thể không còn là nguy cơ chính. Nhưng phải kiểm tra từng endpoint, cách token được lưu, XSS, CORS và token theft; đừng kết luận chỉ vì “API dùng JWT”.

Trong Spring Security 6, `CookieCsrfTokenRepository.withHttpOnlyFalse()` cho phép SPA đọc cookie `XSRF-TOKEN`, sau đó gửi `X-XSRF-TOKEN`. **Chỉ dùng cách này cho CSRF token cookie** và phải cấu hình đúng request handler theo tài liệu Spring Security 6 để giải quyết BREACH masking và deferred-token behavior. Nếu người dùng login/logout, CSRF token cũ có thể bị xóa và cần token mới.

Ví dụ phía client **sau khi hệ thống đã cấp CSRF token đúng cách**:

~~~javascript
const token = readCsrfTokenFromTrustedBootstrap();
await fetch("/profile/email", {
  method: "POST",
  credentials: "same-origin",
  headers: {
    "Content-Type": "application/json",
    "X-CSRF-TOKEN": token
  },
  body: JSON.stringify({ email: "me@example.com" })
});
~~~

Hàm `readCsrfTokenFromTrustedBootstrap()` là **ký hiệu cho lớp tích hợp frontend đã triển khai**, không phải API mặc định của browser hoặc Spring Security. Với cấu hình dùng cookie `XSRF-TOKEN`, tên header thường là `X-XSRF-TOKEN`; phải khớp `CsrfTokenRepository` và `CsrfTokenRequestHandler` thực sự đang sử dụng. Ví dụ này minh họa **cách đặt header**, không phải một ứng dụng JavaScript độc lập.

### 10.1. Vì sao không cho phép CORS tuỳ ý?

`Access-Control-Allow-Origin: *` kết hợp credentialed requests không phải cấu hình hợp lệ cho trình duyệt theo CORS; và khai báo origin quá rộng hoặc phản chiếu origin không có kiểm soát có thể cho phép trang ngoài đọc dữ liệu hoặc tăng khả năng khai thác. CORS là chính sách chia sẻ phản hồi giữa origin, không tự kiểm tra ai được phép thay đổi tài nguyên. Bật CORS phù hợp **không thay thế** CSRF token hoặc authorization cho cookie-based endpoints.

## 11. Origin, Referer và Fetch Metadata: bổ sung cách kiểm tra

### 11.1. Kiểm tra Origin/Referer

Với request thay đổi trạng thái, backend có thể so `Origin` (nếu hiện diện) với origin ứng dụng cho phép, ví dụ chính xác `https://app.example.com`. Nếu `Origin` vắng mặt theo ngữ cảnh, có thể dùng `Referer` theo chính sách; đừng lấy nguyên URL chứa query làm log để tránh rò dữ liệu.

- `https://app.example.com` là một origin.
- `https://evil.example.com` **không** phải origin đó, dù cùng site.
- `https://app.example.com.attacker.net` cũng **không** phải origin đó.
- `Origin: null` hoặc không có header cần được xử lý theo chính sách fallback; không mặc định coi là “same-origin”.
- Sau reverse proxy, phải biết target origin thực được client nhìn thấy; không tin tùy tiện `X-Forwarded-Host` do client có thể giả mạo nếu proxy không chuẩn hóa nó.

`Origin` không thay quyền truy cập hoặc CSRF token khi các trường hợp hợp pháp cần nhiều nguồn/legacy client. Nếu API cho phép nhiều origin, dùng allowlist đầy đủ và biết rõ origin nào có thể tạo thao tác thay đổi trạng thái.

### 11.2. Kiểm tra Fetch Metadata

Browser hiện đại có thể thêm:

~~~http
Sec-Fetch-Site: cross-site
Sec-Fetch-Mode: navigate
Sec-Fetch-Dest: document
~~~

`Sec-Fetch-Site` có thể là `same-origin`, `same-site`, `cross-site` hoặc `none`. Một chính sách phòng vệ có thể từ chối unsafe requests với `cross-site`, đồng thời yêu cầu kiểm tra bổ sung với `same-site` khi sibling subdomain không đáng tin. `none` thường xuất hiện trong một số ngữ cảnh người dùng tự điều hướng; xử lý theo method và workflow.

Không nên biến mọi request thiếu `Sec-Fetch-*` thành trusted request: client cũ và non-browser có thể không cung cấp header. Kết hợp fallback qua CSRF token/Origin/Referer theo chính sách. Một client không phải browser có thể tự tạo header, nên Fetch Metadata **không phải cơ chế xác thực danh tính**.

### 11.3. Với thao tác tài chính hoặc đổi thông tin đăng nhập

Ngoài CSRF guard, áp dụng reauthentication/step-up, transaction confirmation, kiểm soát số lần thử và kiểm tra quyền trên từng đối tượng. Một request có CSRF token hợp lệ vẫn có thể không đủ điều kiện đổi số điện thoại MFA hoặc chuyển tiền.

## 12. WebFlux: SameSite và CSRF vẫn là hai cấu hình khác nhau

Ứng dụng Spring WebFlux dùng `ServerHttpSecurity`, `SecurityWebFilterChain`, `WebSession` thay cho Servlet `HttpSession`. Spring Security WebFlux cũng bật CSRF protection mặc định khi cấu hình security phù hợp và theo mặc định lưu expected token trong `WebSessionServerCsrfTokenRepository`.

**Mảnh cấu hình minh họa** trong ứng dụng WebFlux có đăng nhập qua cookie:

~~~java
@Bean
SecurityWebFilterChain security(ServerHttpSecurity http) {
    return http
        .authorizeExchange(auth -> auth
            .anyExchange().authenticated())
        .formLogin(Customizer.withDefaults())
        // CSRF được giữ mặc định.
        .build();
}
~~~

Các import cần thiết: `org.springframework.context.annotation.Bean`, `org.springframework.security.config.Customizer`, `org.springframework.security.config.web.server.ServerHttpSecurity` và `org.springframework.security.web.server.SecurityWebFilterChain`. Đoạn trên **phải đặt trong một lớp @Configuration của ứng dụng WebFlux**, không phải chương trình Java chạy độc lập.

Spring Boot WebFlux có property `server.reactive.session.cookie.same-site` để cấu hình cookie WebSession, ví dụ:

~~~properties
server.reactive.session.cookie.same-site=lax
~~~

Để client SPA đọc CSRF token cookie có thể chọn `CookieServerCsrfTokenRepository.withHttpOnlyFalse()` và tích hợp token theo hướng dẫn của WebFlux. Đừng copy `HttpSecurity`, `CsrfTokenRepository` Servlet hoặc `server.servlet.session.cookie.same-site` nguyên xi sang WebFlux.

Mặc dù cả hai stack đều có SameSite cookie, server phải tự kiểm tra CSRF khi dùng credentials tự gửi. Reactive và non-blocking **không** có nghĩa ứng dụng tự miễn nhiễm CSRF.

## 13. Ma trận kiểm thử ứng dụng thực tế

Kiểm thử trên HTTPS với các hostname phù hợp, ví dụ `app.example.com`, `blog.example.com` và `attacker.example.net`; dùng môi trường thử nghiệm sở hữu hợp pháp thay vì dịch vụ người khác.

| Thử nghiệm | Mục tiêu | Kết quả đúng cần đánh giá |
| --- | --- | --- |
| POST cùng origin, có session và token | Luồng hợp lệ | Thành công nếu còn quyền và dữ liệu hợp lệ |
| POST cùng origin, có session nhưng thiếu token | CSRF filter | Bị từ chối, thường 403 |
| POST cùng origin với token sai | CSRF filter | Bị từ chối |
| Cross-site top-level GET tới trang chỉ đọc | SameSite=Lax | Cookie có thể được gửi và GET không được đổi state |
| Cross-site POST form, cookie Lax tường minh | SameSite | Browser thường không gửi cookie; nếu request đến server vẫn phải có CSRF guard |
| Same-site sibling subdomain POST | Phạm vi site vs origin | Cookie có thể được gửi, nhưng CSRF token/Origin policy vẫn chặn request giả |
| Cross-site iframe, cookie None; Secure | Embed/third-party policy | Cookie có thể được gửi nếu browser cho phép; unsafe request vẫn phải được kiểm tra |
| Cookie thiếu SameSite được browser default Lax | Behavior theo browser | Đánh giá ngoại lệ cookie mới và độ lệch giữa trình duyệt |
| OAuth/OIDC callback GET/POST | SSO | Callback không bị gãy ngoài ý muốn; `state`/nonce/PKCE vẫn được kiểm |
| Login/logout | Vòng đời phiên | Token được cấp/làm mới/xóa đúng; logout cần phương thức được bảo vệ |
| XSS trong origin | Khả năng vượt CSRF | Phải phòng XSS, không chỉ nhìn SameSite |
| Browser không gửi Fetch Metadata | Fallback | Không tự coi yêu cầu thiếu header là trusted |
| Request thiếu Origin hoặc Origin:null | Fallback policy | Xử lý theo luật rõ ràng, không mặc nhiên cho qua |
| API dùng header bearer duy nhất | Phạm vi CSRF | Kiểm chứng server không chấp nhận cookie/Basic tự gửi ở cùng route |

**Đo trong DevTools:** Kiểm tra `Set-Cookie` trên response; cookie thực sự có thuộc tính gì, browser có từ chối cookie không, request có header `Cookie` hay không, `Origin` và `Sec-Fetch-Site` thuộc trường hợp nào, request có `_csrf`/header CSRF không, mã phản hồi và dữ liệu server có thay đổi không. Đừng suy ra chỉ từ một screenshot cookie storage.

**Lưu ý phân biệt 302/401/403:** request không mang session có thể bị redirect tới login (302) hoặc trả 401; có session nhưng thiếu CSRF token thường bị chặn 403. Vì vậy test cross-site POST không nhất thiết luôn cho 403: nếu SameSite khiến session cookie vắng, ứng dụng có thể xử lý như chưa đăng nhập.

## 14. Lỗi thường gặp và cách sửa

**Lỗi 1 – “Đã SameSite=Strict thì không cần CSRF token”.** Sibling subdomain vẫn là same-site; XSS/client-side CSRF không được giải quyết. **Sửa:** giữ CSRF guard cho cookie-based unsafe requests và Origin/Fetch Metadata theo risk.

**Lỗi 2 – “Lax chặn toàn bộ yêu cầu từ site khác”.** Lax vẫn cho cookie ở cross-site top-level safe navigations như GET. **Sửa:** GET chỉ đọc; kiểm thử link/redirect thực tế.

**Lỗi 3 – “Bỏ SameSite nghĩa là cookie có default Lax an toàn”.** Hành vi default và ngoại lệ ngắn hạn khác giữa browser. **Sửa:** khai báo SameSite tường minh và dùng server CSRF guard.

**Lỗi 4 – “Cùng site có nghĩa cùng origin”.** `https://evil.example.com` và `https://app.example.com` khác origin. **Sửa:** dùng xác minh origin đầy đủ nếu policy yêu cầu cùng origin; không coi mọi subdomain là trusted.

**Lỗi 5 – “Đặt HttpOnly là chặn CSRF”.** HttpOnly ngăn JavaScript trực tiếp đọc cookie, browser vẫn tự gửi khi đủ điều kiện. **Sửa:** CSRF token, SameSite, kiểm tra nguồn; chống XSS riêng.

**Lỗi 6 – “Secure và HTTPS tự chống CSRF”.** HTTPS bảo vệ kênh truyền; request từ attacker vẫn có thể đi qua HTTPS tới ứng dụng. **Sửa:** kiểm tra sự chủ ý của request qua CSRF defense.

**Lỗi 7 – “Tắt CSRF cho tất cả API vì chúng trả JSON”.** Endpoint dùng session cookie/Basic vẫn có thể bị browser tự gửi credential. **Sửa:** kiểm kê từng security chain, loại credential và phương thức gửi; chỉ ngoại lệ có căn cứ.

**Lỗi 8 – “Tắt CSRF để chữa lỗi 403 của SPA”.** Spring Security 6 có deferred/masked token và rotation sau login/logout. **Sửa:** cấu hình SPA request handler, refresh token flow và header đúng.

**Lỗi 9 – “Dùng một CSRF token tĩnh trong HTML hardcode”.** Token như vậy không bảo vệ các phiên đúng cách và có thể bị dự đoán/lộ. **Sửa:** để framework sinh và xác minh token bằng repository thích hợp.

**Lỗi 10 – “Chỉ check Referer có chứa example.com”.** `https://example.com.attacker.net` có thể qua kiểm tra chuỗi ngây thơ. **Sửa:** parse và so origin chính xác; xử lý proxy/header thiếu rõ ràng.

**Lỗi 11 – “CORS chặn mọi CSRF”.** Cross-site form và navigation không phụ thuộc toàn bộ vào CORS; CORS không phải authorization. **Sửa:** bảo vệ server side.

**Lỗi 12 – “Dùng GET để logout/xóa tài khoản vì tiện link”.** GET được xem là safe và không CSRF-protected mặc định. **Sửa:** dùng POST/DELETE với token và các kiểm tra phù hợp.

**Lỗi 13 – “Cookie SameSite của session bảo vệ mọi cookie”.** Remember-me, OAuth state và cookie do proxy phát có thể có thuộc tính khác. **Sửa:** kiểm tra mọi `Set-Cookie` và cấu hình đúng nơi phát.

**Lỗi 14 – “SameSite=None luôn giúp SSO và iframe hoạt động”.** Các browser có thể hạn chế third-party cookie, trong khi CSRF risk vẫn còn. **Sửa:** kiểm tra luồng SSO và chuẩn OAuth, cân nhắc server-side/BFF hoặc các giải pháp được hỗ trợ trong từng môi trường.

## 15. Checklist triển khai

1. Liệt kê **mọi endpoint thay đổi trạng thái**, loại HTTP method, credential nhận vào và nguồn frontend được phép.
2. Không cho thay đổi nghiệp vụ trên `GET`/`HEAD`/`OPTIONS`/`TRACE`.
3. Với browser cookie-auth, bật CSRF protection của Spring Security và gửi token trong form field/header đúng quy ước.
4. Đặt `SameSite=Lax` hoặc `Strict` theo nhu cầu session; chỉ dùng `None; Secure` cho luồng cross-site thật sự cần.
5. Dùng HTTPS ở production, cookie `Secure`/`HttpOnly`, hạn chế Domain, cân nhắc tiền tố `__Host-`, timeout và đổi session ID.
6. Với SPA, kiểm tra `CsrfTokenRequestHandler`, repository, masked/deferred token và cách nhận token mới sau login/logout.
7. Kiểm tra ``Origin`/`Referer` và Fetch Metadata như lớp bổ sung; xử lý cả same-site nhưng cross-origin và browser thiếu header.
8. Không coi CORS, JWT, HttpOnly hoặc SameSite riêng lẻ là bằng chứng CSRF đã được giải quyết.
9. Tự động hóa test missing/invalid CSRF token, thêm browser tests cross-site GET/POST và sibling subdomain, kiểm tra callback OAuth.
10. Giữ authorization và input validation ở business layer; thao tác nhạy cảm cần thêm reauthentication/step-up khi thích hợp.

## 16. Câu hỏi tự kiểm tra

**Q1.** `SameSite=Lax` có ngăn site ngoài dẫn người dùng tới `GET /delete?id=123` không?  
**Đáp án:** Không chắc; trong top-level GET cross-site, Lax có thể gửi cookie. Bản thân server không được thay đổi dữ liệu bằng GET.

**Q2.** Một script ở `https://blog.example.com` gửi form tới `https://app.example.com`. `SameSite=Strict` có chắc chặn session cookie không?  
**Đáp án:** Không. Hai origin khác nhau nhưng cùng site trong ngữ cảnh thông thường. Cần server-side CSRF token/Origin policy.

**Q3.** Thêm `HttpOnly` cho session cookie có tự tạo CSRF token không?  
**Đáp án:** Không. HttpOnly chỉ ngăn JS đọc trực tiếp cookie, còn browser có thể tự gửi cookie.

**Q4.** Vì sao hai request POST cùng cookie lại cho kết quả 403 và 200 trong demo?  
**Đáp án:** CSRF filter kiểm tra thêm token phù hợp phiên; có cookie và authenticated chưa đủ.

**Q5.** Khi nào `SameSite=None` có ý nghĩa?  
**Đáp án:** Khi một luồng hợp lệ yêu cầu gửi cookie trong ngữ cảnh cross-site, kèm `Secure` và kiểm tra chính sách trình duyệt; vẫn cần CSRF defense theo credential và endpoint.

**Q6.** Spring Security dùng gì để lưu expected CSRF token của ứng dụng Servlet theo mặc định?  
**Đáp án:** `HttpSessionCsrfTokenRepository`. Với SPA có thể dùng cookie-based repository và request handler phù hợp.

**Q7.** Có nên tắt CSRF nếu API được gọi bằng bearer token?  
**Đáp án:** Chỉ cân nhắc khi xác định rõ mọi đường xác thực của API không dựa vào credentials browser tự gắn, có các phòng vệ khác và không bỏ sót endpoints cookie/Basic; việc dùng JWT tự nó không đủ lý do.

**Q8.** Vì sao Fetch Metadata không là lớp bảo mật duy nhất?  
**Đáp án:** Có browser thiếu header, client không phải browser có thể giả lập header; `same-site` không đồng nghĩa `same-origin`, và client-side CSRF có thể đến từ origin của ứng dụng.

## 17. Tài liệu tham khảo

- [Spring Security 6.5 – CSRF Protection (Servlet)](https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html) – `CsrfFilter`, `HttpSessionCsrfTokenRepository`, masked/deferred token và SPA integration.
- [Spring Security – CSRF Protection for WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html) – `WebSessionServerCsrfTokenRepository` và reactive CSRF.
- [Spring Boot 3.5 – SameSite Cookies](https://docs.spring.io/spring-boot/3.5/reference/web/servlet.html#web.servlet.embedded-container.customizing.samesite) – `server.servlet.session.cookie.same-site`.
- [Spring Boot 3.5 – Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/) – cấu hình session cookie Servlet/Reactive.
- [OWASP – Cross-Site Request Forgery Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html) – SameSite limitations, token, Origin và Fetch Metadata.
- [MDN – Set-Cookie header](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Set-Cookie) – Strict/Lax/None, default-Lax exception và cookie flags.
- [MDN – Cross-site request forgery (CSRF)](https://developer.mozilla.org/en-US/docs/Web/Security/Attacks/CSRF) – same-site vs same-origin và phương án phòng vệ.
- [OWASP – Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html) – bảo vệ session ID, cookie scope và session fixation.
