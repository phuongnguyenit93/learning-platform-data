# CsrfWebFilter, ServerCsrfTokenRepository và vòng đời CSRF token trong Spring Security Reactive

## 1. Bài toán, phạm vi và mục tiêu

**Cross-Site Request Forgery (CSRF)** xảy ra khi một trang web không đáng tin tìm cách khiến trình duyệt của nạn nhân gửi request thay đổi trạng thái tới một ứng dụng mà nạn nhân đã đăng nhập. Trình duyệt có thể tự động đính kèm cookie phiên hoặc một số loại credential đã được lưu, khiến server nhìn request như thể đến từ người dùng hợp lệ dù người đó không chủ động thực hiện thao tác.

Trong ứng dụng **Spring WebFlux**, Spring Security cung cấp **CsrfWebFilter** để kiểm tra một CSRF token đối với các request cần bảo vệ. Token kỳ vọng được quản lý qua hợp đồng **ServerCsrfTokenRepository**; token gửi cho trình duyệt hoặc JavaScript được đưa ra từ request theo cách phù hợp thông qua **ServerCsrfTokenRequestHandler**.

Bài học trả lời các câu hỏi:

1. CSRF khác **authentication**, **authorization**, **CORS**, **XSS** và session fixation như thế nào?
2. **CsrfWebFilter** lọc request ở đâu, áp dụng cho HTTP method nào, và khi nào trả 403?
3. **ServerCsrfTokenRepository.generateToken**, **saveToken**, **loadToken** làm gì? Vì sao trả Mono?
4. Token được tạo và lưu như thế nào; token được đọc, đưa vào form/header và so sánh ra sao?
5. **WebSessionServerCsrfTokenRepository** và **CookieServerCsrfTokenRepository** khác gì nhau?
6. Vì sao Spring Security 6+ mặc định dùng **XorServerCsrfTokenRequestAttributeHandler**, liên quan đến BREACH?
7. Khi nào token được tạo theo nhu cầu (deferred/lazy) và tại sao GET thường không cần đọc token?
8. Cách viết một demo **Java 17+ WebFlux** có GET /csrf và POST được CSRF bảo vệ, giữ session cookie bằng curl.
9. Cách kiểm thử vòng đời repository bằng StepVerifier và kiểm thử HTTP thực tế bằng WebTestClient.
10. Điều gì xảy ra khi phiên hết hạn, người dùng login/logout, token không khớp hoặc SPA dùng cookie token?

**Trọng tâm:** CSRF token phải được **ràng buộc với ngữ cảnh tin cậy phù hợp**, không phải chỉ một chuỗi ngẫu nhiên được client tự khai. Phải kiểm tra cả token do client gửi và token kỳ vọng do server quản lý, đồng thời không mở ngoại lệ CSRF quá rộng.

## 2. CSRF là gì: ví dụ theo trình duyệt

Giả sử Alice đã đăng nhập vào trang ngân hàng và có cookie SESSION. Website ngân hàng cho phép chuyển tiền qua POST /transfers. Một trang độc hại có thể dựng form tự gửi:

~~~html
<form action="https://bank.example/transfers" method="post">
  <input type="hidden" name="to" value="attacker-account">
  <input type="hidden" name="amount" value="100">
</form>
<script>
  document.forms[0].submit();
</script>
~~~

Nếu browser gửi cookie phiên đến bank.example trong bối cảnh request đó, và server chỉ kiểm tra cookie mà không có ràng buộc CSRF khác, thao tác có thể bị thực hiện trái ý người dùng. Cookie có thể bị giới hạn bởi SameSite và chính sách trình duyệt, nhưng **không nên coi SameSite là sự thay thế tuyệt đối cho CSRF token** trong mọi mô hình triển khai.

Biện pháp **synchronizer token pattern**:

- Khi ứng dụng đáng tin phục vụ trang/form, nó cung cấp một token mà site độc hại không thể tự đọc theo Same-Origin Policy nếu không có lỗ hổng cấu hình hoặc XSS.
- Browser gửi token trong **form field** hoặc **header do JavaScript cùng origin chủ động thêm**.
- CsrfWebFilter so sánh token được trình duyệt cung cấp với token kỳ vọng từ repository.
- Khi thiếu hoặc sai token, request không được đưa tới handler thay đổi trạng thái.

~~~text
Browser của Alice                      WebFlux server
      |                                       |
      | GET /csrf hoặc trang có form           |
      +-------------------------------------->|
      |                                       | load token, hoặc generate + save
      |<---------- token + cookie phiên ------+
      |                                       |
      | POST /api/notes                       |
      | Cookie: SESSION=...                   |
      | X-CSRF-TOKEN: token đã được cấp       |
      +-------------------------------------->|
      |                                       | CsrfWebFilter:
      |                                       |  load expected token
      |                                       |  resolve submitted token
      |                                       |  đối chiếu
      |<------------------- 200 hoặc 403 -----+
~~~

Một trang khác origin không được tự đọc response GET /csrf nếu hệ thống không mở CORS cho nó; nó cũng không tự biết token phải gửi trong custom header. **CORS không phải cơ chế thay thế CSRF**, và XSS trên chính origin đáng tin có thể đánh cắp hoặc sử dụng token. Vì thế phòng chống XSS và chính sách cookie vẫn cần thiết.

### 2.1. CSRF khác authentication và authorization

| Kiểm tra | Câu hỏi | Ví dụ |
| --- | --- | --- |
| Authentication | Caller sở hữu credential hợp lệ? | Login cookie/HTTP Basic |
| Authorization | Caller được phép làm gì? | ROLE_ADMIN, owner/tenant |
| CSRF | Request thay đổi trạng thái có ý định hợp lệ từ frontend của người dùng không, trong mô hình credential tự gửi? | POST có CSRF token hợp lệ |
| CORS | Browser origin nào được phép đọc hoặc gửi các request cross-origin có kiểm soát? | Access-Control-Allow-Origin |
| XSS | Có script độc hại chạy trong origin đáng tin không? | Script đọc token, thực hiện action |
| Session fixation | ID phiên trước và sau login có được đổi phù hợp? | WebSession.changeSessionId |

Một POST có password đúng và role đủ vẫn có thể nhận **403 do thiếu CSRF**. Ngược lại, có CSRF token đúng **không** có nghĩa caller đã xác thực hoặc có quyền; authentication/authorization vẫn tiếp tục quyết định.

## 3. Kiến trúc WebFlux: CsrfWebFilter đứng ở đâu?

Đối với Spring Security Reactive, **SecurityWebFilterChain** chứa các WebFilter thực hiện authentication, authorization, CSRF và các cơ chế khác. CsrfWebFilter triển khai **org.springframework.web.server.WebFilter**, tức là làm việc với **ServerWebExchange**, **WebFilterChain** và **Mono<Void>**.

Đừng nhầm với CsrfFilter của servlet:

| Servlet Spring Security | Reactive Spring Security |
| --- | --- |
| CsrfFilter | **CsrfWebFilter** |
| CsrfTokenRepository | **ServerCsrfTokenRepository** |
| HttpServletRequest/HttpServletResponse | **ServerWebExchange** |
| HttpSessionCsrfTokenRepository | **WebSessionServerCsrfTokenRepository** |
| CookieCsrfTokenRepository | **CookieServerCsrfTokenRepository** |
| CsrfTokenRequestHandler | **ServerCsrfTokenRequestHandler** |
| HttpSecurity.csrf(...) | **ServerHttpSecurity.csrf(...)** |

Luồng đơn giản:

~~~text
HTTP request
    |
    v
SecurityWebFilterChain
    |
    +--> CsrfWebFilter
    |      |
    |      +--> Xác định request có cần CSRF không
    |      |
    |      +--> Expose Mono<CsrfToken> thành exchange attribute
    |      |
    |      +--> Nếu safe method: không yêu cầu submitted token
    |      |
    |      +--> Nếu unsafe method:
    |             load token kỳ vọng
    |             lấy token từ header/form parameter
    |             so sánh, thiếu/sai -> 403
    |
    +--> Authentication / Authorization
    |
    v
Controller hoặc RouterFunction -> service
~~~

Thứ tự chính xác các filter và đường xử lý exception phụ thuộc cấu hình/phiên bản, không nên suy luận rằng một 403 luôn đến từ authorization rule. CsrfWebFilter có thể từ chối trước khi controller được gọi; vì thế **@RestControllerAdvice không phải nơi thay thế CsrfWebFilter**.

### 3.1. Safe và unsafe HTTP methods

Theo mặc định, bảo vệ CSRF được áp dụng cho các HTTP method không an toàn. Các method được xem là safe theo matcher mặc định:

- GET
- HEAD
- TRACE
- OPTIONS

Các method như POST, PUT, PATCH, DELETE phải gửi token phù hợp khi CSRF đang áp dụng.

| Request | Có cần CSRF theo matcher mặc định? | Ghi chú |
| --- | --- | --- |
| GET /catalog | Không | GET phải chỉ đọc |
| HEAD /catalog | Không | HEAD không được đổi dữ liệu |
| OPTIONS /catalog | Không | Có thể là CORS preflight |
| POST /api/notes | **Có** | Ghi dữ liệu |
| PUT /api/notes/42 | **Có** | Thay đổi dữ liệu |
| PATCH /api/notes/42 | **Có** | Thay đổi một phần |
| DELETE /api/notes/42 | **Có** | Xóa dữ liệu |

**Không đưa side effect quan trọng vào GET** chỉ vì GET được miễn CSRF. Ví dụ GET /logout/now hoặc GET /transfer-money là thiết kế nguy hiểm: kẻ tấn công có thể kích hoạt GET bằng link, hình ảnh, navigation hoặc crawler. Nên dùng phương thức unsafe đúng ngữ nghĩa và áp dụng CSRF khi dùng credential dựa trên browser.

### 3.2. 403 do CSRF nghĩa là gì?

Nếu POST thiếu token, CsrfWebFilter có thể trả **403 Forbidden**. Điều này không đủ để kết luận user thiếu ROLE_ADMIN. Cần tách riêng các trạng thái:

1. **Không có CSRF token**: request bị từ chối ở CSRF, không nên cập nhật dữ liệu.
2. **Token không trùng repository**: request bị từ chối ở CSRF.
3. **Token đúng nhưng không có credential**: CSRF cho qua, authentication/authorization vẫn có thể trả 401 hoặc chuyển hướng login.
4. **Token đúng, credential đúng, thiếu role**: authorization có thể trả 403.
5. **Token đúng, credential đúng, đủ quyền**: handler có thể xử lý và trả mã nghiệp vụ.

Một test POST chỉ có header Authorization nhưng thiếu CSRF thường nhận 403; điều này **không chứng minh** authentication hoặc role policy của endpoint đã đúng.

## 4. Hợp đồng ServerCsrfTokenRepository

Interface **org.springframework.security.web.server.csrf.ServerCsrfTokenRepository** mô tả ba thao tác reactive:

~~~java
Mono<CsrfToken> generateToken(ServerWebExchange exchange);
Mono<Void> saveToken(ServerWebExchange exchange, CsrfToken token);
Mono<CsrfToken> loadToken(ServerWebExchange exchange);
~~~

Đây là chữ ký minh họa, không phải class Java độc lập. **CsrfToken** mang ít nhất ba giá trị:

~~~java
String headerName = token.getHeaderName();
String parameterName = token.getParameterName();
String value = token.getToken();
~~~

Mỗi phương thức có trách nhiệm riêng:

| Phương thức | Vai trò | Khi sử dụng |
| --- | --- | --- |
| generateToken(exchange) | Tạo token mới | Chưa có token kỳ vọng hoặc đang cần token mới |
| saveToken(exchange, token) | Lưu token vào repository | Sau generate hoặc khi lifecycle yêu cầu |
| loadToken(exchange) | Đọc token kỳ vọng | Hiển thị token hoặc kiểm tra submitted token |
| saveToken(exchange, null) | Xóa token được lưu | Invalidate/clear token theo chiến lược |

Trong hợp đồng reactive:

- **generateToken** trả **Mono<CsrfToken>**; không tự suy diễn rằng gọi method sẽ lập tức sinh dữ liệu nếu publisher chưa được subscribe.
- **saveToken** trả **Mono<Void>**, phải được compose và chờ hoàn tất trong reactive chain; không gọi **subscribe()** thủ công trong request handler.
- **loadToken** trả Mono có thể **complete rỗng** khi chưa có token.
- **saveToken(exchange, null)** mang nghĩa xóa token đã lưu theo hợp đồng repository.
- Token là **giá trị nhạy cảm với CSRF protection**, không đưa vào application log, URL, analytics hoặc cache công khai.

Nếu cần thay repository mặc định, implementation tự tạo phải lưu và đọc đúng cùng giá trị, không blocking event loop, có entropy đủ mạnh, expiration/rotation và cơ chế từ chối khi backend không khả dụng. Đừng viết repository “luôn trả một token cố định” hoặc chỉ so sánh submitted token với chính nó.

### 4.1. CsrfToken có phải Authentication hay session ID?

Không. Một CSRF token **không chứng minh người dùng là Alice**, không cung cấp ROLE_USER và không cấp quyền truy cập. Nó cũng không phải ID của WebSession hay mật khẩu. Cần giữ riêng:

- **Authentication**: danh tính do framework xác minh.
- **SecurityContext**: ngữ cảnh authentication cho request/session.
- **CSRF token**: bằng chứng phòng request giả mạo theo thiết kế.
- **SESSION cookie**: ID giúp server tìm trạng thái phiên.

Kẻ tấn công biết hoặc đoán một username không thể tự tạo CSRF token hợp lệ cho session nạn nhân bằng cách gọi generateToken trên một session khác.

## 5. Vòng đời CSRF token từ lúc chưa có đến khi hết hạn

### 5.1. Trạng thái chưa có token

Khi một trình duyệt vừa mở ứng dụng, repository có thể chưa có token kỳ vọng trong session. Việc **không có token** là trạng thái hợp lệ trước khi token được yêu cầu.

Với WebSessionServerCsrfTokenRepository, token được lưu trong **WebSession**; nếu chưa có thì loadToken trả empty. CsrfWebFilter có thể sắp xếp publisher **load-or-generate**, để token mới được sinh và lưu **khi thực sự cần**.

Một GET thông thường như /public/ping không đọc token có thể tránh phải tạo/lưu token chỉ để phục vụ một request read-only.

### 5.2. Token được yêu cầu để render form hoặc trả API

Ví dụ GET /csrf:

1. CsrfWebFilter cho phép safe method đi qua bước kiểm tra submitted token.
2. Request attribute **CsrfToken.class.getName()** chứa **Mono<CsrfToken>** do bộ xử lý request token công bố.
3. Controller hoặc view **subscribe thông qua reactive chain** bằng cách trả về Mono tương ứng.
4. Repository tìm token kỳ vọng; nếu chưa có, token mới được sinh và lưu.
5. Client nhận giá trị cần gửi lại cùng session cookie.

Với Spring Security 6+, **XorServerCsrfTokenRequestAttributeHandler** thường đưa ra token đã **mask**; giá trị này có thể khác giữa hai lần render ngay cả khi raw token kỳ vọng trong repository không đổi.

### 5.3. Unsafe request gửi token

Ví dụ POST /api/notes từ client cùng origin:

1. Trình duyệt gửi **SESSION cookie** cho biết WebSession tương ứng.
2. JavaScript lấy giá trị token trước đó từ GET /csrf hoặc form.
3. Client thêm header mà **CsrfToken.getHeaderName()** công bố, thông thường **X-CSRF-TOKEN** với WebSession repository.
4. CsrfWebFilter dùng request handler để lấy submitted token từ header hoặc form parameter phù hợp.
5. Khi dùng XOR masking, handler giải mã giá trị đã mask thành raw token để so sánh.
6. Repository cung cấp expected token từ WebSession của request.
7. Nếu khớp và không bị từ chối bởi các filter khác, request có thể đi tới handler.
8. Authentication, authorization, validation và business logic vẫn là các hàng rào riêng.

Nếu client gửi **token của một session khác**, hoặc cookie bị hết hạn làm server không còn expected token, request bị từ chối theo chính sách CSRF.

### 5.4. Sau POST thành công token có dùng lại được không?

Trong synchronizer token pattern, **raw token lưu trong session có thể được sử dụng cho nhiều unsafe requests**, cho đến khi lifecycle/rotation/expiry thay đổi nó. CSRF token **không nhất thiết là one-time token**, và không nên tự yêu cầu token mới sau mỗi POST trừ khi chính sách của ứng dụng quy định vậy.

Với XOR masking, giá trị được render ra client có thể khác giữa hai lần GET trong khi cùng ánh xạ tới một raw token lưu trong WebSession. Vì thế **không so sánh trực tiếp hai chuỗi token đã mask để kết luận repository đã đổi token**.

### 5.5. Token hết hạn hoặc phiên bị hủy

Khi WebSession hết hạn, ứng dụng mất token kỳ vọng gắn với phiên đó. Một POST dùng cookie/token cũ có thể nhận 403. UX thích hợp:

- Báo session đã hết hạn hoặc yêu cầu người dùng tải lại form.
- Lấy **CSRF token mới** từ backend theo quy trình hợp lệ.
- Không tự động replay thao tác ghi nhiều lần nếu có nguy cơ tạo side effect trùng.
- Với ứng dụng có đăng nhập, xác minh lại authentication/session.
- Test việc mất session và logout theo deployment thực tế.

### 5.6. Login và logout

Form login POST và logout POST thường cũng là **unsafe requests** được CSRF bảo vệ. Khi authentication hoặc logout làm đổi/xóa session, hoặc cơ chế ứng dụng làm mới token, **client cần lấy token mới** trước lần POST tiếp theo.

Không được áp dụng máy móc toàn bộ chi tiết **CsrfAuthenticationStrategy/CsrfLogoutHandler của servlet** sang WebFlux: reactive sử dụng các thành phần riêng và hành vi cuối cùng phụ thuộc phiên bản, logout handler, session repository. Hãy kiểm thử rằng token cũ không vô tình dùng được sau khi session bị revoke, và token mới được cấp đúng cách cho phiên mới.

Không dùng **GET /logout** như một endpoint thay đổi trạng thái để “né CSRF”, trừ khi sản phẩm hiểu và chấp nhận rõ rủi ro; POST logout được bảo vệ vẫn là lựa chọn thông thường.

## 6. CsrfWebFilter và ServerCsrfTokenRequestHandler

CsrfWebFilter không chỉ biết cách lấy token từ repository; nó còn cần công bố token cho view/controller và **resolve submitted value** từ request. Vai trò này thuộc **ServerCsrfTokenRequestHandler** và bộ resolver tương ứng.

Các class đáng biết:

- **ServerCsrfTokenRequestAttributeHandler**: đưa token vào request attribute và lấy token từ request (header/form parameter) theo cấu hình.
- **XorServerCsrfTokenRequestAttributeHandler**: lớp mở rộng có thể mask token khi render và giải mã khi nhận lại; được dùng mặc định từ Spring Security 6.0 để hỗ trợ giảm rủi ro BREACH trong các response có nén.
- **CsrfWebFilter.DEFAULT_CSRF_MATCHER**: matcher mặc định xác định method nào phải kiểm tra CSRF.
- **ServerHttpSecurity.CsrfSpec**: DSL dùng để chỉ định repository, request handler hoặc matcher.

Một cấu hình thường đủ:

~~~java
return http
        .csrf(csrf -> csrf
                .csrfTokenRepository(
                        new WebSessionServerCsrfTokenRepository()))
        .build();
~~~

Đoạn trên phải nằm **bên trong phương thức @Bean SecurityWebFilterChain** của một ứng dụng và có các rule authentication/authorization phù hợp; đây không phải file chạy độc lập.

### 6.1. Exchange attribute chứa Mono<CsrfToken>

Spring Security WebFlux tài liệu hóa attribute với key:

~~~java
CsrfToken.class.getName()
~~~

Có thể truy cập trong controller:

~~~java
Mono<CsrfToken> csrfToken =
        exchange.getAttribute(CsrfToken.class.getName());

if (csrfToken == null) {
    return Mono.error(
            new IllegalStateException("CSRF filter not configured"));
}

return csrfToken.map(token -> Map.of(
        "headerName", token.getHeaderName(),
        "token", token.getToken()));
~~~

Mã minh họa này là nội dung một method có tham số ServerWebExchange exchange và kiểu trả Mono<Map<String,String>>. Chương trình đầy đủ ở mục 9.

**Quan trọng:** đọc request attribute **không được đồng nhất** với việc đọc raw token trực tiếp từ session. Giá trị CsrfToken mà request handler đưa cho view có thể là **XOR-masked**. Khi muốn form hoạt động với default handler, hãy gửi lại đúng giá trị đã được render, không lấy một raw token trong repository rồi tự nghĩ mã hóa/giải mã.

### 6.2. Vì sao masking liên quan BREACH?

Trong ứng dụng trả HTML nén, nếu token bí mật xuất hiện lặp lại trong response, một số tấn công đo độ dài nén có thể suy diễn dữ liệu nhạy cảm. XOR token request handler đưa thêm randomness vào token giá trị được render, giảm nguy cơ rò token qua cơ chế nén phản hồi.

Bảng:

| Giá trị | Nằm ở đâu? | Ý nghĩa |
| --- | --- | --- |
| Raw expected token | WebSession/token repository | Giá trị gốc cần xác thực |
| Masked token | HTML/form/GET /csrf qua request handler | Giá trị client gửi lại |
| Header/form value | HTTP request tiếp theo | Handler resolve/unmask để so với raw |
| SESSION cookie | Trình duyệt | Chọn phiên dùng để tìm raw token |

**Không tắt BREACH protection chỉ để client có thể copy token raw trong cookie.** Nếu chuyển sang CookieServerCsrfTokenRepository cho SPA, cần thiết kế tương thích giữa cookie token (có thể raw) và request handler (mặc định chờ masked token). Cấu hình mismatch dễ làm mọi POST trả 403 hoặc khiến developer tắt bảo vệ sai cách.

## 7. Hai repository phổ biến

### 7.1. WebSessionServerCsrfTokenRepository — mặc định

Đây là lựa chọn chuẩn khi ứng dụng dùng **WebSession**:

- Expected token lưu ở server-side session, gắn với trạng thái phiên.
- Token gửi cho client không phải bằng chứng login.
- Request phải giữ cookie session phù hợp để server đọc expected token.
- Nếu session mất/hết hạn, token cũ không còn hợp lệ cho phiên đó.
- Không cần cho JavaScript đọc cookie token; có thể cung cấp masked token trong HTML hoặc endpoint GET /csrf.
- Với nhiều replica, cần session store dùng chung tương thích WebFlux khi yêu cầu session cross-node.

Ví dụ rõ ràng hóa mặc định:

~~~java
.csrf(csrf -> csrf.csrfTokenRepository(
        new WebSessionServerCsrfTokenRepository()))
~~~

**Không dùng HttpSessionCsrfTokenRepository của servlet trong WebFlux.** Mặc dù tên gần giống, chúng phục vụ hợp đồng khác nhau.

### 7.2. CookieServerCsrfTokenRepository — một lựa chọn cho SPA

**CookieServerCsrfTokenRepository** lưu expected token ở cookie **XSRF-TOKEN** theo convention thường gặp ở Angular, và mặc định đọc token gửi lại từ header **X-XSRF-TOKEN** hoặc parameter **_csrf**.

~~~java
.csrf(csrf -> csrf.csrfTokenRepository(
        CookieServerCsrfTokenRepository.withHttpOnlyFalse()))
~~~

**withHttpOnlyFalse()** cho JavaScript đọc cookie, nhưng làm token trong cookie dễ bị đọc qua XSS hơn. Khi JavaScript **không cần đọc trực tiếp cookie**, ưu tiên dùng constructor mặc định và giữ HttpOnly.

Quan trọng với Spring Security 6+:

- **Cookie token** và **XOR-masked token** có thể có dạng khác nhau.
- Việc copy trực tiếp giá trị raw XSRF-TOKEN cookie vào X-XSRF-TOKEN header cần **request handler phù hợp**, nếu không default XOR handler có thể giải mã thất bại.
- Đừng mặc định cấu hình cookie repository một dòng là đủ cho mọi SPA.
- Cần kiểm thử thực tế với browser, CORS, SameSite, Secure và session/credential policy.
- Cookie không tương đương bảo đảm một raw token độc lập, được ký, hoặc chống subdomain cookie injection; phải hiểu threat model.

Demo tiếp theo cố ý dùng **WebSessionServerCsrfTokenRepository** và GET /csrf để tránh lẫn lộn token raw trong cookie với giá trị masked trong request.

### 7.3. Tự viết repository có nên không?

Chỉ nên nếu có yêu cầu rõ, ví dụ dữ liệu phân tán/không thể dùng WebSession hoặc cookie thông thường. Phải giữ:

1. Sinh token khó đoán bằng nguồn entropy mật mã thích hợp.
2. Lưu token có ràng buộc với đúng phiên/định danh tin cậy.
3. Không để client tự xác lập expected token tùy ý.
4. Xóa token đúng khi invalidation.
5. Dùng API Mono không blocking event loop.
6. Chống lộ token qua log, URL, analytics và CDN.
7. Thử concurrent requests, session rotation, expiration, multi-instance.
8. Tương thích với request handler được cấu hình.

Không nên tự viết repository chỉ để “có code reactive” khi Spring Security đã có bản chuẩn.

## 8. Cấu hình mặc định, các lựa chọn và ranh giới trust

Theo tài liệu Spring Security WebFlux:

- **CSRF được bật mặc định** khi dùng cấu hình security thông thường.
- **WebSessionServerCsrfTokenRepository** là repository mặc định.
- **XorServerCsrfTokenRequestAttributeHandler** là request handler mặc định từ Spring Security 6.
- CSRF token được đưa ra dưới dạng **Mono<CsrfToken>** ở exchange attribute.
- Method GET/HEAD/TRACE/OPTIONS không cần submitted token theo default matcher; unsafe methods cần.
- Form POST và Ajax/JSON POST có cách truyền token khác nhau nhưng cùng cần khớp expected token.

### 8.1. Khi nào có thể cấu hình ngoại lệ CSRF?

Không có câu trả lời “REST API thì luôn disable CSRF”. Quyết định phụ thuộc việc **browser tự động gửi credential** hay không:

| Hình thức client/authentication | CSRF có thể liên quan? | Ghi chú |
| --- | --- | --- |
| Browser + session cookie | **Có** | Trình duyệt có thể tự gửi cookie |
| Browser + HTTP Basic đã lưu credential | **Có thể có** | Trình duyệt có thể tự gửi lại credential |
| Browser + cookie chứa token auth/JWT | **Có** | JWT trong cookie vẫn là credential tự gửi |
| API chỉ nhận bearer token trong Authorization do client chủ động thêm, không dùng cookie | Thường giảm rủi ro CSRF truyền thống | Vẫn cần đánh giá CORS, XSS, token storage và kiến trúc |
| Backend-to-backend không dùng browser cookie | Thường không theo mô hình CSRF của trình duyệt | Vẫn phải xác thực và phân quyền |
| Website dùng GET để đổi trạng thái | Thiết kế lỗi | Sửa HTTP semantics thay vì chỉ bật/tắt CSRF |

Khi có nhiều SecurityWebFilterChain, mỗi chain cần đánh giá CSRF riêng theo endpoint và cơ chế credential. Nếu exempt một tập path, chỉ exempt **đúng method/route cần thiết** và test rằng những đường ghi khác vẫn được bảo vệ.

### 8.2. CORS preflight không phải hành động kinh doanh

OPTIONS có thể xuất hiện trong CORS preflight, thường không có credential. Nếu CORS không được cấu hình trước lớp authentication, frontend có thể báo lỗi trước khi gửi POST thật. Không sửa bằng cách permitAll mọi unsafe method; hãy cấu hình CORS, origins, headers và credential policy dựa trên threat model.

### 8.3. CSRF không thay thế SameSite, Origin check hay XSS defense

CSRF token mạnh nhất khi kết hợp:

- HTTPS/TLS, cookie Secure và HttpOnly phù hợp.
- SameSite có chủ đích, giới hạn cookie Domain và Path.
- Không mở CORS credentials cho origin không đáng tin.
- Escape HTML, Content Security Policy và chống XSS.
- Authentication và authorization thực sự.
- Giới hạn rate, giám sát bất thường và session invalidation.
- Với một số tác vụ nhạy cảm, kiểm tra Origin/Referer ở lớp phù hợp để bổ sung.

Không nên log token hoặc session ID trong request/response logging. Header có thể chứa bí mật, cần masking.

## 9. Dự án Java 17+ chạy được: WebFlux + WebSession CSRF

Demo này dùng **Spring Boot 3.5.16**, Java 17+, Gradle 8.4+ (có thể dùng Gradle 8.14) và Spring Security reactive do Spring Boot quản lý.

Tài khoản thử nghiệm: **alice / alice-pass** có ROLE_USER. Mật khẩu mẫu chỉ để thử localhost.

Mục đích demo:

- GET **/public/ping**: public, không cần CSRF.
- GET **/csrf**: public, cung cấp token để same-origin frontend sử dụng.
- GET **/api/notes/count**: cần authentication, chỉ đọc.
- POST **/api/notes**: cần authentication **và** CSRF token hợp lệ; tăng bộ đếm in-memory để chứng minh một thao tác đổi trạng thái đã xảy ra.

Một request POST bị CsrfWebFilter từ chối **không được tăng bộ đếm**.

Cấu trúc:

~~~text
webflux-csrf-lifecycle/
├── settings.gradle
├── build.gradle
├── src/main/java/example/csrf/CsrfLifecycleApplication.java
├── src/main/java/example/csrf/SecurityConfig.java
├── src/main/java/example/csrf/CsrfController.java
├── src/test/java/example/csrf/CsrfHttpTest.java
└── src/test/java/example/csrf/CsrfRepositoryTest.java
~~~

### 9.1. settings.gradle

~~~groovy
rootProject.name = 'webflux-csrf-lifecycle'
~~~

### 9.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Không thêm spring-boot-starter-web đồng thời nếu muốn quan sát chính xác WebFlux WebFilter pipeline. Spring Boot BOM giữ các phiên bản Spring Security, Reactor và Spring Framework tương thích. Dùng Gradle Wrapper đã pin version khi đưa vào dự án đội nhóm.

### 9.3. CsrfLifecycleApplication.java

~~~java
package example.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfLifecycleApplication {

    public static void main(String[] args) {
        SpringApplication.run(CsrfLifecycleApplication.class, args);
    }
}
~~~

### 9.4. SecurityConfig.java

~~~java
package example.csrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("alice-pass"))
                .roles("USER")
                .build();

        return new MapReactiveUserDetailsService(alice);
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/ping", "/csrf").permitAll()
                        .pathMatchers("/api/**").authenticated()
                        .anyExchange().denyAll())
                // Giữ CSRF bật và làm rõ kho token mặc định.
                .csrf(csrf -> csrf.csrfTokenRepository(
                        new WebSessionServerCsrfTokenRepository()))
                .httpBasic(Customizer.withDefaults())
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .build();
    }
}
~~~

**Giải thích:**

1. WebFlux SecurityWebFilterChain áp dụng cả cho Controller và RouterFunction nếu cùng đi qua chain.
2. GET /csrf được permitAll để client có thể lấy token trước login, nhưng **permitAll không bỏ qua CsrfWebFilter**.
3. /api/** cần Authentication hợp lệ.
4. CsrfWebFilter dùng repository trong WebSession, không có ngoại lệ CSRF cho POST /api/notes.
5. Không cấu hình custom request handler nên vẫn giữ **XOR/BREACH protection mặc định**.
6. Demo dùng HTTP Basic để tránh phải trình bày thêm form login; session cookie trong bài dùng để giữ expected **CSRF token**, không phải để thay thế xác thực username/password.
7. Một request POST thiếu/nhầm CSRF token sẽ bị chặn ngay cả khi HTTP Basic credential hợp lệ.
8. **Không disable CSRF** để làm ví dụ dễ chạy; các bài test sẽ cấp token đúng theo cơ chế thật.
9. PasswordEncoder băm BCrypt khi xây UserDetails. Password mẫu trong code chỉ dành cho học tập, không dùng production.

### 9.5. CsrfController.java

~~~java
package example.csrf;

import java.security.Principal;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import reactor.core.publisher.Mono;

@RestController
public class CsrfController {

    private final AtomicInteger savedCount = new AtomicInteger();

    @GetMapping("/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/csrf")
    public Mono<Map<String, String>> csrf(ServerWebExchange exchange) {
        // GET /csrf không được cache token.
        exchange.getResponse().getHeaders()
                .setCacheControl("no-store");

        Mono<CsrfToken> token =
                exchange.getAttribute(CsrfToken.class.getName());

        if (token == null) {
            return Mono.error(new IllegalStateException(
                    "CSRF filter not configured"));
        }

        // Subscribe gián tiếp khi Spring WebFlux subscribe response Mono.
        return token.map(value -> Map.of(
                "headerName", value.getHeaderName(),
                "parameterName", value.getParameterName(),
                "token", value.getToken()));
    }

    @GetMapping("/api/notes/count")
    public Mono<Map<String, Integer>> count() {
        return Mono.just(Map.of("count", savedCount.get()));
    }

    @PostMapping("/api/notes")
    public Mono<Map<String, String>> create(Mono<Principal> principal) {
        return principal.map(actor -> Map.of(
                "owner", actor.getName(),
                "id", Integer.toString(savedCount.incrementAndGet())));
    }
}
~~~

**Vì sao /csrf trả token trong response?** Client cùng origin cần lấy token đã được request handler chuẩn chuẩn bị. Nó không phải authentication credential để login; GET /csrf được permitAll không có nghĩa website bất kỳ origin nào tự đọc được JSON do Same-Origin Policy/CORS. **Không cấu hình Access-Control-Allow-Origin: * cùng credential** cho một API như vậy.

**Vì sao không gọi repository.generateToken() trong controller?** Làm vậy dễ tạo token tách rời khỏi token kỳ vọng đã được CsrfWebFilter quản lý, nhất là khi XOR masking có mặt. Dùng Mono<CsrfToken> đã được đưa vào exchange bởi filter để giữ đồng bộ.

**Vì sao dùng AtomicInteger?** Đây chỉ là dữ liệu giả trong RAM để chứng minh POST làm thay đổi trạng thái; production cần repository, transaction, quyền theo tài nguyên và cơ chế chống request replay phù hợp.

**Vì sao trả Map có headerName/parameterName/token?** Demo giúp người học không phải hard-code tên header. Với WebSessionServerCsrfTokenRepository, tên mặc định thường là **X-CSRF-TOKEN** và **_csrf**. Token trả về được masked theo request handler; client phải gửi lại đúng giá trị này.

### 9.6. Khởi động

~~~bash
gradle bootRun
~~~

Yêu cầu JDK 17+ và Gradle tương thích với Spring Boot 3.5.16. Mặc định Spring Boot chạy ở http://localhost:8080 nếu không có cấu hình port khác.

**Chỉ thử HTTP Basic qua localhost để học.** Production phải dùng HTTPS/TLS, secret quản lý đúng, cookie an toàn và authentication mechanism phù hợp. HTTP Basic Base64 không mã hóa bảo mật password.

## 10. Thực hành curl: cùng cookie, cùng CSRF token

Ví dụ dùng Bash, curl và Python 3 để đọc JSON. Nếu môi trường có jq, có thể dùng jq -r để lấy giá trị token thay Python.

### 10.1. GET /csrf tạo hoặc nạp expected token

~~~bash
curl -sS \
  -c session.cookies \
  http://localhost:8080/csrf \
  -o csrf.json

cat csrf.json
~~~

Body có dạng:

~~~json
{
  "headerName": "X-CSRF-TOKEN",
  "parameterName": "_csrf",
  "token": "gia-tri-token-da-mask-theo-phien"
}
~~~

Chuỗi token thực tế **không có giá trị cố định**, và thường có randomness của XOR masking. Không đưa token thực vào log, ticket, ảnh hoặc version control.

File session.cookies chứa cookie của session tương ứng, thường tên **SESSION** với WebFlux mặc định; một ứng dụng thật có thể tùy chỉnh tên, path, SameSite, Secure hoặc dùng một resolver khác.

Tạo biến:

~~~bash
CSRF_TOKEN="$(python3 -c 'import json; print(json.load(open("csrf.json"))["token"])')"
CSRF_HEADER="$(python3 -c 'import json; print(json.load(open("csrf.json"))["headerName"])')"
~~~

### 10.2. Thiếu token → 403 dù có password đúng

~~~bash
curl -i -sS \
  -b session.cookies \
  -u alice:alice-pass \
  -X POST \
  http://localhost:8080/api/notes
~~~

Kết quả dự kiến: **403 Forbidden**. Không phải vì Alice thiếu role; request không cung cấp token để CsrfWebFilter so sánh.

### 10.3. Token sai → 403

~~~bash
curl -i -sS \
  -b session.cookies \
  -u alice:alice-pass \
  -H "$CSRF_HEADER: invalid-token-value" \
  -X POST \
  http://localhost:8080/api/notes
~~~

Kết quả dự kiến: **403 Forbidden**. Giá trị bất kỳ không khớp raw token kỳ vọng. Trong một số phiên bản, request handler cũng từ chối token không đúng cấu trúc masking; điều quan trọng là **không được xử lý thao tác ghi**.

### 10.4. Token và cookie đúng → thành công

~~~bash
curl -i -sS \
  -b session.cookies \
  -u alice:alice-pass \
  -H "$CSRF_HEADER: $CSRF_TOKEN" \
  -X POST \
  http://localhost:8080/api/notes
~~~

Body dự kiến:

~~~json
{"owner":"alice","id":"1"}
~~~

Giá trị id là 1 nếu đây là lần POST hợp lệ đầu tiên kể từ khi chạy server; nếu server đã có POST khác, id tăng theo bộ đếm. Vì vậy test tự động chỉ nên assert owner và status, không gắn cứng ID nếu có nhiều test song song.

### 10.5. Kiểm tra dữ liệu đã thay đổi

~~~bash
curl -sS -u alice:alice-pass \
  http://localhost:8080/api/notes/count
~~~

Nếu mới chỉ có một POST hợp lệ sau khi khởi động, body sẽ là:

~~~json
{"count":1}
~~~

Hai request POST trước đó bị từ chối ở CSRF không được tăng count. Đây là khác biệt giữa request đi qua security filter và request thực sự tới controller.

### 10.6. Token đúng nhưng sai password

~~~bash
curl -i -sS \
  -b session.cookies \
  -u alice:wrong-pass \
  -H "$CSRF_HEADER: $CSRF_TOKEN" \
  -X POST \
  http://localhost:8080/api/notes
~~~

Kết quả dự kiến: **401 Unauthorized** từ HTTP Basic, vì CSRF đã thỏa nhưng authentication không thành công. Điều này chứng minh **CSRF token không thay thế password**.

### 10.7. Không gửi cookie đúng phiên

~~~bash
curl -i -sS \
  -u alice:alice-pass \
  -H "$CSRF_HEADER: $CSRF_TOKEN" \
  -X POST \
  http://localhost:8080/api/notes
~~~

Kết quả dự kiến: **403 Forbidden** do server không tìm được expected token của session đã phát token trước đó. Token một mình không đủ để xác thực CSRF khi dùng WebSession token repository.

**Lưu ý:** file session.cookies và csrf.json là dữ liệu nhạy cảm của phiên demo; xóa sau khi thử, không commit, không đăng công khai.

### 10.8. Kiểm tra giá trị masked biến đổi

Có thể GET /csrf lần thứ hai với cùng cookie:

~~~bash
curl -sS \
  -b session.cookies \
  -c session.cookies \
  http://localhost:8080/csrf
~~~

Một giá trị token được trả về có thể khác do **XOR masking**, nhưng chưa đủ để kết luận raw token trong WebSession đã bị xoay. Để xem raw token kỳ vọng trong test, dùng test repository nội bộ và tránh lộ cho client.

## 11. Kiểm thử HTTP thật với WebTestClient

Bài test tích hợp cần quan sát cả **session cookie** lẫn **token JSON** và cho request POST chạy qua security filters. Không chỉ unit test Controller trực tiếp.

Tệp **src/test/java/example/csrf/CsrfHttpTest.java**:

~~~java
package example.csrf;

import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.ResponseCookie;
import org.springframework.test.web.reactive.server.EntityExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class CsrfHttpTest {

    @Autowired
    WebTestClient client;

    private record Ticket(
            String sessionId,
            String headerName,
            String token) {
    }

    private Ticket newTicket() {
        EntityExchangeResult<Map> result =
                client.get().uri("/csrf")
                        .exchange()
                        .expectStatus().isOk()
                        .expectBody(Map.class)
                        .returnResult();

        Map body = result.getResponseBody();
        assertNotNull(body);

        ResponseCookie sessionCookie =
                result.getResponseCookies().getFirst("SESSION");
        assertNotNull(sessionCookie);

        String header = (String) body.get("headerName");
        String token = (String) body.get("token");
        assertNotNull(header);
        assertNotNull(token);

        return new Ticket(sessionCookie.getValue(), header, token);
    }

    @Test
    void publicGetDoesNotRequireCsrf() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void protectedGetNeedsAuthenticationNotCsrf() {
        client.get().uri("/api/notes/count")
                .exchange()
                .expectStatus().isUnauthorized();

        client.get().uri("/api/notes/count")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isOk();
    }

    @Test
    void postWithoutCsrfIsForbidden() {
        Ticket t = newTicket();

        client.post().uri("/api/notes")
                .cookie("SESSION", t.sessionId())
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void tokenFromOtherSessionIsForbidden() {
        Ticket a = newTicket();
        Ticket b = newTicket();

        client.post().uri("/api/notes")
                .cookie("SESSION", a.sessionId())
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .header(a.headerName(), b.token())
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void sameSessionAndTokenAllowPost() {
        Ticket t = newTicket();

        client.post().uri("/api/notes")
                .cookie("SESSION", t.sessionId())
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .header(t.headerName(), t.token())
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.owner").isEqualTo("alice");
    }

    @Test
    void csrfDoesNotReplaceAuthentication() {
        Ticket t = newTicket();

        client.post().uri("/api/notes")
                .cookie("SESSION", t.sessionId())
                .headers(h -> h.setBasicAuth("alice", "wrong-pass"))
                .header(t.headerName(), t.token())
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void tokenWithoutSessionCookieCannotBeReused() {
        Ticket t = newTicket();

        client.post().uri("/api/notes")
                .headers(h -> h.setBasicAuth("alice", "alice-pass"))
                .header(t.headerName(), t.token())
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

Chạy sau khi nhập đúng project:

~~~bash
gradle test
~~~

**Kết quả kỳ vọng:** bảy test trong CsrfHttpTest PASS khi WebFlux session resolver mặc định dùng cookie tên SESSION và dependencies tương thích. Không cố định token hoặc session ID, vì đây là giá trị ngẫu nhiên.

Giải thích **newTicket()**:

1. Gọi GET /csrf để **subscribe** Mono<CsrfToken> trong response.
2. Dùng WebTestClient đọc JSON token và Set-Cookie của WebSession.
3. Tạo Ticket giữ đúng session ID và tên header được token báo.
4. Gửi lại cả **cookie** lẫn **header** ở request POST tiếp theo.
5. Khi token xuất phát từ session B nhưng cookie là session A, test kỳ vọng 403.

**Giới hạn:** test tích hợp này giả định session cookie mặc định. Trong hệ thống dùng Spring Session, custom WebSessionIdResolver, proxy hoặc cookie name khác, sửa bộ test theo cấu hình deployment thật. Đừng thay đổi production cookie name chỉ để test đơn giản hơn.

### 11.1. SecurityMockServerConfigurers.csrf() là lựa chọn khác

Thư viện **spring-security-test** có hỗ trợ:

~~~java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;
~~~

Khi WebTestClient được bind và cấu hình đúng với **springSecurity()** trong mock exchange, có thể dùng **mutateWith(csrf())** để cấp một CSRF token hợp lệ cho test. Điều này tiện kiểm tra rule URL/controller riêng lẻ mà không cần cookie jar.

Tuy nhiên, nếu đề bài là **vòng đời thực tế của CSRF token và session cookie**, không nên chỉ dùng mock csrf(): nó có thể bỏ qua việc client lấy token thật từ GET /csrf, giữ cookie và gửi lại đúng session. Bởi vậy bài dùng kiểm thử end-to-end ở trên, không thêm dependency spring-security-test cho phần code chính.

### 11.2. Test POST sai token có thể trả 403 trước khi kiểm tra role

Một lưu ý khi tự viết test phân quyền POST: muốn khẳng định ROLE_USER thiếu quyền ghi, phải **cấp token CSRF hợp lệ** trước, nếu không 403 có thể do token chứ không phải rule role. Có thể chia test như sau:

| Test | Token | Authentication | Kỳ vọng |
| --- | --- | --- | --- |
| POST thiếu token | Thiếu | alice đúng | 403 CSRF |
| POST sai token | Token B + cookie A | alice đúng | 403 CSRF |
| POST token đúng + credential sai | Token A + cookie A | alice sai | 401 authentication |
| POST token đúng + credential đúng | Token A + cookie A | alice đúng | 200 |
| GET /api/notes/count | Không cần | alice đúng | 200 |

Đây là cách phân biệt ba hàng rào CSRF, authentication và authorization thay vì chỉ nhìn thấy 403 rồi đoán nguyên nhân.

## 12. Kiểm thử trực tiếp vòng đời repository bằng StepVerifier

Để hiểu chính xác **generate → save → load → delete**, có thể kiểm thử ServerCsrfTokenRepository độc lập với HTTP server. Dùng **MockServerWebExchange** và **MockWebSession** từ spring-test.

Tệp **src/test/java/example/csrf/CsrfRepositoryTest.java**:

~~~java
package example.csrf;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.mock.web.server.MockWebSession;
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.security.web.server.csrf.WebSessionServerCsrfTokenRepository;

import reactor.test.StepVerifier;

class CsrfRepositoryTest {

    @Test
    void generateSaveLoadAndDelete() {
        WebSessionServerCsrfTokenRepository repository =
                new WebSessionServerCsrfTokenRepository();

        MockWebSession session = new MockWebSession();

        MockServerWebExchange exchange = MockServerWebExchange
                .builder(MockServerHttpRequest.get("/csrf"))
                .session(session)
                .build();

        // Ban đầu session chưa có expected token.
        StepVerifier.create(repository.loadToken(exchange))
                .verifyComplete();

        AtomicReference<CsrfToken> created = new AtomicReference<>();

        StepVerifier.create(
                repository.generateToken(exchange)
                        .doOnNext(created::set)
                        .flatMap(token ->
                                repository.saveToken(exchange, token)
                                        .then(repository.loadToken(exchange))))
                .assertNext(loaded -> {
                    assertNotNull(created.get());
                    assertEquals(
                            created.get().getToken(),
                            loaded.getToken());
                    assertEquals(
                            created.get().getHeaderName(),
                            loaded.getHeaderName());
                    assertEquals(
                            created.get().getParameterName(),
                            loaded.getParameterName());
                })
                .verifyComplete();

        // saveToken(null) là yêu cầu xóa expected token.
        StepVerifier.create(
                repository.saveToken(exchange, null)
                        .then(repository.loadToken(exchange)))
                .verifyComplete();
    }
}
~~~

Chạy:

~~~bash
gradle test
~~~

**Kết quả kỳ vọng:** CsrfRepositoryTest PASS. Khi chạy cả project, có tổng cộng **8 test**: 7 kiểm thử HTTP và 1 kiểm thử repository. Gradle in BUILD SUCCESSFUL nếu mã được lưu đúng vị trí, runtime/dependencies hợp lệ.

**Điều test này chứng minh:**

- Không có token → loadToken hoàn thành rỗng.
- generateToken tạo một CsrfToken.
- saveToken và loadToken làm việc với cùng WebSession.
- saveToken(exchange, null) xóa token khỏi repository.
- Các thao tác cần được compose trong Mono và subscribe bằng StepVerifier.

**Điều test này không chứng minh:** XOR-masked token trong HTML, cookie mới được browser nhận, CSRF filter từ chối một HTTP request thật, CORS hoặc gateway behavior. Đây là lý do phải kết hợp CsrfHttpTest.

### 12.1. Vì sao không gọi block() trong WebFlux?

Trong reactive request handler, gọi **block()** để lấy token có thể chặn event loop hoặc làm lỗi scheduler. Đúng là:

~~~java
return tokenMono.map(value -> Map.of(
        "token", value.getToken()));
~~~

Không nên:

~~~java
// Sai trong WebFlux handler: chặn luồng, dễ lỗi dưới tải.
CsrfToken csrf = tokenMono.block();
return Mono.just(Map.of("token", csrf.getToken()));
~~~

Trong unit test có thể dùng StepVerifier để kiểm tra Mono; không cần block hoặc subscribe() thủ công. Trong application code, framework sẽ subscribe publisher được trả về theo vòng đời request.

## 13. Lỗi thường gặp và cách khắc phục

| Lỗi | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng HttpSessionCsrfTokenRepository trong WebFlux | Nhầm stack servlet/reactive | Dùng WebSessionServerCsrfTokenRepository |
| Gọi generateToken nhưng không save | Server không có expected token tương ứng | Để CsrfWebFilter quản lý hoặc compose save |
| Gọi saveToken nhưng bỏ Mono | Side effect có thể không xảy ra | Compose publisher, không subscribe thủ công |
| Chỉ gửi token mà không gửi cookie phiên | Server không tìm thấy expected token của client | Giữ cookie cùng session |
| Dùng token của session khác | CSRF mismatch | Token + session phải đi đôi |
| Lấy raw token từ repository rồi gửi vào XOR handler mặc định | Có thể không khớp định dạng masked | Lấy token từ request attribute/form |
| Copy raw XSRF-TOKEN cookie vào header khi handler đòi masked | 403, hoặc phải custom handler | Thiết kế SPA token request handler thích hợp |
| Nghĩ mọi GET đều tạo/lưu token | Tốn session không cần thiết | Hiểu deferred/lazy Mono và chỉ lấy khi cần |
| Nghĩ token thay sau mỗi POST | Client refresh liên tục không cần | Phân biệt raw token và masked representation |
| Nghĩ cùng masked token sau logout luôn hợp lệ | Session/expected token có thể đã mất | Fetch token mới khi thay session |
| Nghĩ permitAll bỏ CSRF cho POST public | Endpoint public vẫn có thể bị CsrfWebFilter kiểm tra | Cấu hình CSRF theo method/threat model |
| Tắt csrf.disable() toàn API vì test POST bị 403 | Mở nguy cơ khi browser gửi cookie | Giữ CSRF và test gửi token đúng |
| Dùng GET để thực hiện thao tác ghi | Né matcher CSRF mặc định | Chuyển sang POST/PUT/PATCH/DELETE |
| Không kiểm tra CSRF trên login/logout | Login CSRF, logout CSRF | Giữ bảo vệ form và logout POST |
| Nhầm CSRF 403 với ROLE_ADMIN 403 | Debug sai nguyên nhân | Tách test token và authority |
| Log token/session cookie trong debug | Rò credential phiên | Mask log, không xuất token thật |
| Coi SameSite/CORS là bảo đảm chống CSRF tuyệt đối | Có thể còn đường tấn công | Threat model và nhiều lớp bảo vệ |
| Đặt cookie token HttpOnly=false dù JS không cần đọc | Tăng bề mặt đọc token | Giữ HttpOnly nếu không cần SPA cookie reading |
| Dùng repository session in-memory sau load balancer nhiều node | POST sang node khác không tìm thấy token | Spring Session/shared session store |
| Tắt BREACH masking để dễ lấy raw token | Giảm bảo vệ ở response nén | Giữ XOR và dùng request handler tương thích |
| Chỉ dùng mutateWith(csrf()) để test lifecycle | Bỏ qua cookie/token thật | Thêm end-to-end test qua GET /csrf |

## 14. Lưu ý cho sản xuất: SPA, session timeout, nhiều instance

### 14.1. SPA lấy token ở đâu?

Có hai mô hình phổ biến:

**Mô hình A: session repository + GET /csrf**

- Token kỳ vọng trong WebSession.
- SPA cùng origin gọi GET /csrf và nhận masked token, tên header.
- SPA gửi token trong header của unsafe request và browser gửi cookie session tương ứng.
- Khi phiên hết hạn hoặc bị revoke, SPA yêu cầu lấy token mới theo flow an toàn.
- Không cấp CORS credential tùy tiện cho origin không đáng tin.

**Mô hình B: cookie repository + JavaScript đọc XSRF-TOKEN**

- CookieServerCsrfTokenRepository cung cấp cookie token.
- JS cần đọc cookie → có thể dùng withHttpOnlyFalse(), chấp nhận tradeoff.
- Với Spring Security 6+, xem lại request handler để header raw token được xử lý tương thích với XOR masking.
- Cookie Domain, SameSite, Secure, path, subdomain trust và CORS có ý nghĩa lớn.
- Nếu dùng authentication trong cookie, vẫn phải bảo vệ unsafe requests.

Đừng chuyển từ A sang B chỉ để bỏ một GET /csrf nếu không có đánh giá về threat model, XSS và cookie injection.

### 14.2. Session timeout

Ví dụ token được render trong form mở lâu: sau 30 phút session hết hạn, người dùng nhấn Save. Server có thể trả 403 vì expected token không còn. UX tốt:

- Không âm thầm gửi lại request ghi nhiều lần.
- Hiển thị rằng phiên đã hết hạn và yêu cầu tải lại/đăng nhập.
- Lấy token mới từ session mới hoặc theo trình tự auth thích hợp.
- Với biểu mẫu quan trọng, có chiến lược lưu nháp ở client an toàn, không gửi lại ngay khi chưa xác minh danh tính.

### 14.3. Nhiều instance và Spring Session

WebSession lưu trong bộ nhớ mỗi node không bảo đảm token dùng được trên node khác. Nếu load balancer gửi GET /csrf đến replica A và POST /api/notes đến replica B, repository có thể không tìm thấy token.

Cần:

- Dùng session store chia sẻ có hỗ trợ reactive, ví dụ cấu hình Spring Session tương thích Redis khi phù hợp.
- Đồng bộ secret/cookie configuration.
- Kiểm tra session expiry, TTL, invalidation và CSRF token persistence.
- Không dùng sticky session như cách duy nhất để che sự thiếu nhất quán dài hạn.
- Test thật qua nhiều replica với cùng cookie và token.

### 14.4. File upload/multipart

Đối với upload multipart, nếu token chỉ nằm trong body thì hệ thống có thể phải xử lý body trước khi thực sự xác nhận CSRF. Cách có lợi là gửi token trong **HTTP header**, cho phép kiểm tra trước khi đọc/upload lượng dữ liệu lớn ở mức handler. Vẫn cần giới hạn upload size và content-type.

### 14.5. Không public hóa token ngoài phạm vi tin cậy

GET /csrf trong demo được permitAll để client cùng origin có thể chuẩn bị một form, nhưng token không được gửi vào third-party analytics, referrer URL, cache CDN công khai hay CORS response cho website không đáng tin. Session cookie cũng phải hạn chế Domain/Path, Secure/HttpOnly/SameSite thích hợp.

Nếu nghi ngờ XSS, **CSRF token không giúp chống script đang chạy trong origin tin cậy**. Chống XSS bằng output escaping, template/DOM an toàn và CSP là yêu cầu riêng.

## 15. Câu hỏi và bài tập tự kiểm tra

1. CsrfWebFilter là loại filter của servlet hay WebFlux? Chữ ký xử lý request dùng loại exchange nào?
2. ServerCsrfTokenRepository có ba phương thức chính nào? Kiểu Mono của từng phương thức?
3. saveToken(exchange, null) có nghĩa gì?
4. WebSessionServerCsrfTokenRepository lưu expected token ở đâu?
5. Vì sao GET /public/ping có thể không tạo token dù CSRF protection đang bật?
6. Trong Spring Security 6+, vì sao token render ở form có thể khác nhau giữa hai request?
7. Nếu token đúng của session A được gửi kèm cookie của session B, kết quả bảo mật mong đợi?
8. Vì sao chỉ thêm token đúng nhưng không gửi credential phù hợp vẫn không đủ để POST protected endpoint?
9. Tại sao POST thiếu CSRF có thể trả 403 dù user có role đúng?
10. CookieServerCsrfTokenRepository.withHttpOnlyFalse() giải quyết nhu cầu gì và có tradeoff nào?
11. Tại sao không nên dùng CSRF token ở URL query hoặc ghi trong log?
12. Có nên tắt CSRF cho mọi REST API không? Câu trả lời phụ thuộc điều gì?
13. Token trong WebSession có được giữ qua nhiều POST hay luôn bị đổi sau một request?
14. Khi WebSession hết hạn, form cũ có thể gặp lỗi gì?
15. Vì sao chỉ dùng mutateWith(csrf()) chưa đủ để kiểm tra lifecycle cookie?
16. Khi GET /csrf và POST /api/notes đi vào hai server instance, điều kiện hạ tầng nào phải thỏa?
17. Vì sao login/logout POST cũng cần CSRF?
18. CSRF, CORS và XSS có thể thay thế nhau không?

**Đáp án gợi ý:**

1. WebFlux WebFilter, dùng ServerWebExchange/WebFilterChain/Mono<Void>.
2. generateToken → Mono<CsrfToken>, saveToken → Mono<Void>, loadToken → Mono<CsrfToken>.
3. Xóa expected token khỏi repository theo hợp đồng.
4. WebSession của request.
5. Token deferred, không ai subscribe/request token.
6. XorServerCsrfTokenRequestAttributeHandler mask bằng randomness để giảm rủi ro BREACH; raw expected token có thể chưa đổi.
7. Mismatch/403 nếu session B có token khác.
8. CSRF không phải authentication; vẫn cần credential và authorization.
9. CsrfWebFilter có thể chặn trước hoặc độc lập với kiểm tra role.
10. Cho JS đọc XSRF-TOKEN cookie nhưng giảm lợi ích HttpOnly, cần cân nhắc XSS.
11. URL/log có thể bị lộ/caching/referrer.
12. Không; phụ thuộc browser credential có tự gửi không và threat model.
13. Raw token thường dùng lại trong cùng phiên cho đến khi lifecycle thay đổi; không mặc định one-time.
14. Expected token không tồn tại, POST cũ bị từ chối; lấy token/phiên mới.
15. Mock token không bảo đảm session cookie và repository hoạt động end-to-end.
16. Shared session store hoặc cách lưu nhất quán giữa các replica.
17. Chống login CSRF/logout CSRF.
18. Không; chúng giải quyết các loại rủi ro khác nhau.

## 16. Tài liệu tham khảo

- Spring Security — CSRF for WebFlux (6.5): https://docs.spring.io/spring-security/reference/6.5/reactive/exploits/csrf.html
- Spring Security — CsrfWebFilter Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/CsrfWebFilter.html
- Spring Security — ServerCsrfTokenRepository Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/ServerCsrfTokenRepository.html
- Spring Security — WebSessionServerCsrfTokenRepository Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/WebSessionServerCsrfTokenRepository.html
- Spring Security — CookieServerCsrfTokenRepository Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/CookieServerCsrfTokenRepository.html
- Spring Security — XorServerCsrfTokenRequestAttributeHandler Javadoc: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/web/server/csrf/XorServerCsrfTokenRequestAttributeHandler.html
- Spring Security — Reactive CSRF Testing: https://docs.spring.io/spring-security/reference/reactive/test/web/csrf.html
- Spring Framework — MockServerWebExchange.Builder Javadoc: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/mock/web/server/MockServerWebExchange.Builder.html
- OWASP — CSRF Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html

**Kết luận:** Trong Spring Security WebFlux, **CsrfWebFilter** quyết định request nào cần CSRF và từ chối unsafe requests không có token hợp lệ; **ServerCsrfTokenRepository** đảm nhiệm sinh/lưu/đọc expected token; **ServerCsrfTokenRequestHandler** công bố/giải mã giá trị token mà client gửi. Với thiết kế WebSession mặc định, vòng đời là **GET cần token → load hoặc generate/save → render masked token → client gửi header/form kèm đúng session cookie → CsrfWebFilter validate → xử lý nghiệp vụ**. Giữ bảo vệ mặc định khi browser tự gửi credential, hiểu sự khác biệt giữa raw token và XOR masking, và kiểm thử cả publisher lẫn HTTP request thực thay vì chỉ tắt CSRF để một POST thành công.