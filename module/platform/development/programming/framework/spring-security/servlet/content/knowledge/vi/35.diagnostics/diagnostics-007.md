# CSRF token không hợp lệ sau đăng nhập, hết phiên hoặc mở nhiều tab

> **Ngữ cảnh:** Spring Security 6.x, Spring Boot 3.x, Java 17+, **Servlet stack** (Spring MVC, session/cookie và giao diện server-rendered hoặc SPA). Mục tiêu là **chẩn đoán** lỗi CSRF 403 xảy ra sau đăng nhập, đăng xuất, hết phiên, khi giữ form lâu hoặc sử dụng nhiều tab; tìm đúng nguyên nhân và xử lý mà **không tắt bảo vệ CSRF**. Bài phân biệt token do server lưu, token được gửi từ browser, phiên xác thực, token bị xóa khi authentication đổi và cơ chế token trì hoãn/che token của Spring Security 6. Các ví dụ Java/Spring phải chạy trong dự án có dependency phù hợp; code HTTP/JS là minh họa tích hợp, không phải chương trình Java SE độc lập.

## 1. Triệu chứng thường gặp và kết luận cần nhớ

Người dùng có thể gặp những tình huống tưởng như ngẫu nhiên:

- Vừa đăng nhập thành công, bấm **Lưu** trên một form tải từ trước thì nhận **403 Forbidden**.
- Để tab mở quá lâu, nhập dữ liệu và POST sau khi session hết hạn: thao tác bị từ chối, đôi khi không được chuyển tới trang login như dự đoán.
- Mở hai tab cùng ứng dụng; đăng xuất hoặc đăng nhập bằng tài khoản khác ở tab B, quay sang tab A bấm **Gửi**, nhận lỗi token.
- Một SPA GET dữ liệu bình thường, nhưng POST/PUT/DELETE sau khi login, session refresh hoặc chuyển tab bị 403.
- Lỗi chỉ xảy ra khi request POST từ frontend, trong khi một MockMvc test sử dụng `.with(csrf())` vẫn pass.
- Lỗi 403 trùng với việc đổi node/load balancer hoặc cookie session bị thay đổi trên browser.

**Không phải cứ 403 là lỗi CSRF.** Spring Security cũng trả 403 khi user **đã xác thực nhưng thiếu quyền**; ngược lại một request chưa đăng nhập có thể bị 401/302 ở các luồng khác. Cần xác định request bị chặn bởi **`CsrfFilter`**, authorization filter, session policy hay handler khác.

**Mở nhiều tab tự nó không làm CSRF token hết hạn.** Các tab cùng origin/browser profile thường chia sẻ cookie session. Nếu cùng một session còn hiệu lực và token server không bị xóa/thay thế, các form của nhiều tab vẫn có thể dùng token hợp lệ. Lỗi phát sinh khi **trạng thái chia sẻ thay đổi** (login/logout/session timeout/session regeneration, phiên khác, request mang sai token), không phải vì số lượng tab.

## 2. CSRF và hai phía của một phép kiểm tra

CSRF (*Cross-Site Request Forgery*) lợi dụng việc browser **tự đính kèm credential** (ví dụ cookie đăng nhập) vào HTTP request. Một site độc hại có thể khiến browser gửi thao tác không mong muốn tới site ứng dụng. Spring Security CSRF protection yêu cầu request cần bảo vệ mang một giá trị token thích hợp mà nguồn tấn công không thể tùy ý lấy được từ ứng dụng nạn nhân.

Với Servlet stack và kiểu lưu trong session mặc định, có thể hình dung:

~~~text
Browser                 Spring Security Servlet
   | GET /form                 |
   |-------------------------->|
   |                  CsrfTokenRepository
   |                  get/generate expected token
   |<--- HTML form + token ---|
   |                          |
   | POST /transfer           |
   | Cookie: JSESSIONID=...   |
   | _csrf=token-sent         |
   |-------------------------->|
   |                          | CsrfFilter
   |                          | load expected token (from session)
   |                          | resolve actual token from form/header
   |                          | compare securely
   |                          |
   |<-- allowed or 403 -------|
~~~

Đây là **sơ đồ khái niệm**: trong Spring Security 6 token có thể được **nạp trì hoãn** và **che token (XOR/BREACH)** khi xuất ra client. Giá trị string HTML/JSON mà bạn quan sát **không nhất thiết bằng nguyên văn** token lưu trong session, dù chúng liên hệ với cùng token cơ sở.

Ba thứ phải phân biệt:

| Khái niệm | Nơi tồn tại | Vai trò |
| --- | --- | --- |
| **Expected token** | `CsrfTokenRepository` phía server, thường gắn với HTTP session hoặc cookie repository theo cấu hình. | Chuẩn để kiểm tra request. |
| **Actual/presented token** | Trường form `_csrf` hoặc HTTP header như `X-CSRF-TOKEN` được browser gửi. | Giá trị client trình bày cho request. |
| **HTTP session / authentication** | Browser dùng session cookie; server có session, SecurityContext và session lifecycle. | Xác định ngữ cảnh để nạp token và user, có thể thay đổi khi login/logout/timeout. |

**Token không phải chứng thực quyền của user.** CSRF check qua chưa có nghĩa user có `ROLE_ADMIN` hoặc được phép sửa bản ghi. Authorization vẫn phải kiểm tra danh tính, roles và quyền trên đối tượng.

### Những HTTP request thường cần CSRF?

Trong cấu hình Spring Security mặc định, các HTTP methods được coi là *unsafe* như `POST`, `PUT`, `PATCH`, `DELETE` thường phải qua CSRF check; các methods như `GET`, `HEAD`, `OPTIONS`, `TRACE` thường được coi là safe. Quy tắc này dựa vào **semantics của HTTP method**. Nếu ứng dụng dùng GET để thay đổi dữ liệu, đó là lỗi thiết kế cần sửa — không thể dựa vào CSRF mặc định để bảo vệ side effect ở GET.

**Chú ý:** một API chỉ nhận Bearer token gửi rõ ràng bằng `Authorization` và không dựa vào browser tự đính kèm credential có threat model khác với ứng dụng session/cookie. Không tắt CSRF chỉ vì route có tiền tố `/api`; phải xét **cơ chế xác thực thực tế** và khả năng browser gửi credential tự động.

## 3. Vòng đời mặc định của CSRF token trong Spring Security 6

Một cấu hình Servlet thông dụng sử dụng:

- `HttpSessionCsrfTokenRepository`: giữ expected token trong HTTP session.
- `CsrfFilter`: bảo vệ request cần CSRF bằng cách so actual token với expected token.
- `XorCsrfTokenRequestAttributeHandler`: trong Spring Security 6, handler mặc định thường tạo biểu diễn token **được che bằng dữ liệu ngẫu nhiên** khi đưa token ra request attribute để giảm rủi ro BREACH.
- `DeferredCsrfToken`: token được tải/tạo **theo nhu cầu** thay vì luôn tạo session/token cho mọi GET.
- `CsrfAuthenticationStrategy`: khi luồng xác thực thành công chạy strategy này, CSRF token hiện có được xóa để token mới được tạo cho session/trạng thái sau login.
- `CsrfLogoutHandler`: trong xử lý logout chuẩn, token có thể bị xóa để token cũ không được dùng lại.

Đừng hiểu “xóa token khi login” như một lỗi bất thường: đó là **hành vi chủ đích** nhằm không giữ lại token từ trạng thái anonymous hoặc một authentication khác sau khi danh tính thay đổi.

### Bảng timeline cần quan sát

| Thời điểm | Session / trạng thái | Token của form tab cũ | Rủi ro |
| --- | --- | --- | --- |
| Trước login | Session A hoặc một trạng thái anonymous đang có expected token T1. | Tab A đang giữ biểu diễn của T1. | T1 có thể hợp lệ trong trạng thái A. |
| Login thành công | Authentication strategy có thể rotate session ID và **xóa CSRF token**. | Tab A vẫn giữ T1 trong DOM/JS. | POST dùng T1 có thể bị 403. |
| GET trang/form mới | Token mới T2 được materialize khi view/controller cần. | Tab mới có biểu diễn T2. | Dùng đúng token được phát cho trạng thái hiện tại. |
| Hết session / session mới | Expected token T2 có thể không còn trong session. | Tab cũ giữ T2. | POST cũ có thể bị 403 trước khi xử lý nghiệp vụ. |
| Logout | Session/authentication bị xử lý; CSRF token thường bị xóa. | Tab còn mở giữ token cũ. | Phải lấy token mới cho login/POST tiếp theo. |
| Hai tab không login/logout/timeout | Cùng session, expected token không bị thay. | Mỗi tab có thể có chuỗi token khác nhau do XOR masking. | Cả hai token vẫn có thể hợp lệ. |

T1 và T2 ở đây là **ký hiệu minh họa**, không phải output định dạng thực của Spring Security.

**Một chi tiết quan trọng:** Spring Security session fixation protection có thể đổi `JSESSIONID` bằng cơ chế `changeSessionId`. Nhưng không nên kết luận “ID đổi là nguyên nhân duy nhất làm token sai”: cơ chế **`CsrfAuthenticationStrategy` xóa token** là một phần quan trọng của lifecycle login. Phân tích cả session và CSRF strategy thay vì sửa một property session fixation ngẫu nhiên.

## 4. Tại sao sau đăng nhập vừa thành công lại bị 403?

### 4.1 Form tải khi chưa đăng nhập

Kịch bản:

1. Người dùng mở một trang chứa form và nhận CSRF token anonymous T1.
2. App yêu cầu login; người dùng đăng nhập thành công.
3. Sau authentication success, CSRF token cũ được xóa/rotated theo Spring Security strategy.
4. Form chưa được render lại tiếp tục gửi T1.
5. `CsrfFilter` so với expected token hiện tại và từ chối request.

**Cách xử lý:** sau khi login thành công, ứng dụng **lấy lại CSRF token từ server** rồi mới gửi các request thay đổi trạng thái. Với trang server-rendered, redirect/GET render lại form là một cách phổ biến. Với SPA, gọi một endpoint `GET /csrf` chuyên dụng và cập nhật token trong memory.

### 4.2 Form login cũng cần CSRF token

Một nhầm lẫn khác: “Login xảy ra trước khi có session, vậy POST /login không cần CSRF”. Trong ứng dụng session/cookie-based dùng form login chuẩn, login CSRF cũng quan trọng để chống các dạng login CSRF. Token có thể được tạo khi hiển thị form login hoặc qua GET `/csrf`. Sau login, token này có thể đã bị xóa nên không dùng nó cho POST nghiệp vụ tiếp theo.

**Đừng khắc phục bằng `csrf.disable()` hoặc exempt toàn bộ `/login` nếu không có phân tích bảo mật riêng.** Hãy bảo đảm login form thực sự mang token hợp lệ và frontend refresh token sau authentication change.

### 4.3 Authentication không làm session “bất biến”

Đăng nhập có thể kéo theo session fixation protection, session attribute migration, SecurityContext persistence, session concurrency control và cookie update. Một trình duyệt/SPA giữ token trong JavaScript từ trước login có thể lệch trạng thái mới. Mục tiêu là **đồng bộ token với phiên hiện tại**, không tìm cách cố định JSESSIONID hoặc giữ mã CSRF cũ mãi mãi.

### 4.4 Redirect login thành công không tự refresh mọi tab

Tab A vẫn có HTML/JS snapshot cũ, kể cả khi tab B đã login và redirect tới trang mới. Browser không bắt buộc re-render tab A. Khi tab A bấm Submit, request có cookie session mới nhưng actual token cũ — trường hợp kinh điển của **token/session desynchronization**.

## 5. Vì sao session hết hạn dẫn tới CSRF 403 thay vì trang login?

Với `HttpSessionCsrfTokenRepository`, expected CSRF token gắn với session. Sau khi server xóa session do timeout, bị invalidate, hoặc session store mất dữ liệu:

~~~text
Tab mở trước lúc hết hạn:
  HTML có _csrf=T_old
  Browser còn cookie JSESSIONID=old...

Server:
  session old hết hạn / không tồn tại
  expected token cũ không còn

Browser POST:
  body _csrf=T_old
  request có thể được xem là unauthenticated
  CsrfFilter nhận token không khớp expected hiện tại
  --> HTTP 403 (trong cấu hình thông thường)
~~~

**Vì sao không phải luôn 302 tới login?** Thứ tự security filters và exception handling có thể khiến `CsrfFilter` từ chối unsafe request **trước khi** authentication entry point được dùng. Một request GET sau timeout có thể 302 về login, trong khi POST với token cũ trả 403. Tùy cấu hình, đó là hành vi phù hợp.

### Xử lý UX khi form tồn tại lâu

- Cảnh báo session sắp hết hạn nếu ứng dụng có thông tin thời gian đáng tin.
- Với form lớn, bảo vệ bản nháp ở client một cách phù hợp; **không tự lưu dữ liệu nhạy cảm vào localStorage** nếu threat model không cho phép.
- Khi gặp lỗi xác nhận session/CSRF, yêu cầu đăng nhập hoặc làm mới phiên và **lấy CSRF token mới**. Chỉ gửi lại thao tác sau khi xác nhận ý định người dùng và kiểm tra dữ liệu còn hợp lệ.
- Không tự động retry mọi POST nhận 403: 403 còn có thể là **thiếu quyền**. Tự retry thao tác thay đổi trạng thái cũng có thể gây **duplicate side effects** nếu phản hồi bị mất trong lúc server đã xử lý.
- Nếu app cần lưu tác vụ lớn, cân nhắc autosave có kiểm soát, idempotency keys và chính sách phục hồi riêng.

## 6. Nhiều tab: tình huống nào thực sự làm token sai?

Các tab cùng browser profile và origin thường chia sẻ cookies, nhưng **mỗi tab có DOM và JavaScript state riêng**. Vì vậy:

| Tình huống nhiều tab | CSRF token bị lỗi không? | Giải thích |
| --- | --- | --- |
| Tab A và B tải form dưới cùng session, không có authentication change. | **Không nhất thiết.** | Cả hai có thể dùng token hợp lệ; token biểu diễn khác do XOR mask không đồng nghĩa expected token đổi. |
| Tab B login, tab A giữ form cũ trước login. | **Có thể.** | Login xóa token cũ; tab A chưa nhận token mới. |
| Tab B logout, tab A giữ một form private. | **Có thể.** | Logout/session reset khiến token và authentication thay đổi; tab A đang stale. |
| Tab B đăng nhập thành user khác trong cùng cookie jar. | **Có thể và nhạy cảm hơn.** | Principal và CSRF token ở tab A không còn tương ứng trạng thái hiện tại; phải refresh và xác minh ý định. |
| Tab A mở lâu tới session timeout, tab B mở lại app. | **Có thể.** | Session mới có token mới; form tab A còn token cũ. |
| Tab B chỉ GET trang mới, session không đổi. | **Thông thường không.** | Một GET thông thường không mặc nhiên rotate expected CSRF token. |
| Hai profile trình duyệt/incognito độc lập. | Token không hoán đổi cho nhau. | Cookie jar và session khác nhau; lấy token của profile này gửi qua profile kia sẽ sai. |
| Hai node ứng dụng có session store không đồng bộ. | **Có thể.** | Request đọc expected token ở node không có session state đã tạo token. |

**Chẩn đoán đúng:** xác định request POST thuộc **session nào** và expected token đã được xóa/thay ở thời điểm nào. Đừng đổ lỗi cho “nhiều tab” rồi chuyển sang một token global dùng cho mọi user.

### Gợi ý đồng bộ tab mà không truyền bí mật

Frontend có thể dùng `BroadcastChannel` hoặc sự kiện đăng nhập/đăng xuất để thông báo **“trạng thái xác thực đã thay đổi”** cho các tab cùng origin. Mỗi tab tự gọi lại endpoint `/csrf` để lấy token cho session hiện hành. Không gửi token nhạy cảm hoặc cookie qua broadcast và không dùng broadcast làm bằng chứng authentication/authorization: browser state có thể bị sửa, còn server mới là nơi xác minh.

## 7. Deferred token và XOR mask trong Spring Security 6: dễ nhầm khi debug

Trong Spring Security 6 Servlet, CSRF xử lý có hai khía cạnh dễ gây nhầm:

1. **Deferred loading:** token repository không nhất thiết bị truy cập hoặc tạo token mới cho **mọi GET**. Token có thể được materialize khi trang/form/controller thực sự cần. Sau khi login/logout xóa token, SPA phải chủ động yêu cầu token mới nếu muốn thực hiện unsafe request ngay.
2. **BREACH/XOR masking:** `XorCsrfTokenRequestAttributeHandler` có thể biến token gốc thành **giá trị masked ngẫu nhiên** khi render ra HTML hoặc request attribute. Hai lần render có thể cho hai chuỗi khác nhau dù expected token underlying **không đổi**.

Ví dụ khái niệm:

~~~text
Expected raw token ở session: R
GET /form tab A: masked token = M1
GET /form tab B: masked token = M2

M1 != M2
Nhưng cả hai đều biểu diễn raw token R nếu còn trong session
POST với M1 hoặc M2 -> có thể hợp lệ
~~~

**Không so sánh string token trong HTML từ hai lần GET rồi kết luận Spring đã đổi expected token.** Spring Security handler có thể giải mã masked actual token trước khi so với raw expected token.

### Token từ cookie và token từ request attribute khác nhau

`HttpSessionCsrfTokenRepository` (mặc định thường gặp) lưu expected token trong session; `CookieCsrfTokenRepository` lưu token qua cookie phù hợp cấu hình. Với SPA, nhiều người đọc cookie `XSRF-TOKEN` và gửi header `X-XSRF-TOKEN`.

Tuy nhiên, khi `XorCsrfTokenRequestAttributeHandler` đang được dùng cho chống BREACH, **raw token lấy trực tiếp từ cookie** và **masked token lấy từ request attribute** không có cùng biểu diễn. Cấu hình SPA cần một `CsrfTokenRequestHandler` phù hợp để xử lý header raw và form masked, hoặc sử dụng endpoint trả masked token để gửi lên header theo cách mà handler mặc định hiểu.

Nếu dùng cookie repository, không tự động chuyển mọi cấu hình sang `CsrfTokenRequestAttributeHandler` đơn giản mà không đánh giá rủi ro BREACH. Hãy dựa trên mẫu SPA integration phù hợp **phiên bản Spring Security đang chạy** và kiểm thử cả form và XHR.

**Ghi nhớ:** cookie chứa CSRF token **không phải cookie đăng nhập**. CSRF token không thay cho session ID, password, OAuth2 access token hoặc quyền truy cập.

## 8. Cấu hình Spring Security 6 giữ CSRF mặc định

Ví dụ một ứng dụng Boot 3.x có form login và API sử dụng session, dùng cấu hình sau. Giữ các default CSRF protections; không disable vì các lỗi 403.

File `src/main/java/com/example/csrf/CsrfSecurityConfig.java`:

~~~java
package com.example.csrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class CsrfSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/csrf", "/error")
                    .permitAll()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .csrf(Customizer.withDefaults())
            .formLogin(form -> form.permitAll());

        return http.build();
    }
}
~~~

- `.csrf(Customizer.withDefaults())` ở đây nhấn mạnh dùng CSRF mặc định, **không** tạo token global, **không** disable `CsrfFilter`.
- `.formLogin(form -> form.permitAll())` bật form login (trang login mặc định do Spring Security tạo) và cho phép các endpoint login liên quan; form login POST cũng phải qua CSRF khi mặc định áp dụng.
- `GET /csrf` công khai để login page/SPA có thể lấy token trước login; đây là **token phiên** chứ không phải thông tin account. Cần hạn chế caching, CORS/credentials, và không gửi token sang origin lạ.
- `/api/**` yêu cầu authenticated, nhưng **chưa giới hạn quyền theo tài nguyên**. Trong ứng dụng thật cần thêm role/permission/owner/tenant authorization.
- Việc đăng nhập thành công có thể rotate session ID và xóa token cũ; controller `/csrf` phần tiếp theo cấp token hiện hành theo nhu cầu.
- `CsrfAuthenticationStrategy` và `CsrfLogoutHandler` hoạt động theo auth/logout lifecycle Spring Security phù hợp. Nếu bạn tự thay thế authentication filters/session strategies hoặc custom logout handling, phải kiểm tra thực tế token lifecycle, không tự giả định giống form login mặc định.

### Dependencies cho ví dụ Java

Trong một Spring Boot project dùng Maven parent/BOM và Java 17+, các dependency cần thiết:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
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
</dependencies>
~~~

Đây là **mảnh `pom.xml`**, không phải một POM đầy đủ; để Spring Boot quản lý phiên bản dependencies tương thích. Nếu dùng Thymeleaf cho phần 10, bổ sung `spring-boot-starter-thymeleaf`.

### Main class cho demo

File `src/main/java/com/example/csrf/CsrfDemoApplication.java`:

~~~java
package com.example.csrf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CsrfDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CsrfDemoApplication.class, args);
    }
}
~~~

## 9. Cấp lại token qua GET /csrf cho SPA và sau login

Một endpoint chuyên dụng có thể nhận `CsrfToken` từ request của Spring Security và trả thông tin để client gửi lại trong header/form.

File `src/main/java/com/example/csrf/CsrfController.java`:

~~~java
package com.example.csrf;

import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CsrfController {

    public record TokenView(
            String headerName, String parameterName, String token) {
    }

    @GetMapping("/csrf")
    public TokenView csrf(CsrfToken token) {
        return new TokenView(
                token.getHeaderName(),
                token.getParameterName(),
                token.getToken());
    }
}
~~~

**Điểm then chốt:** gọi `token.getToken()` khiến client nhận giá trị được handler xử lý trong ngữ cảnh request và có thể làm deferred token được materialize. Trong cấu hình mặc định có XOR masking, chuỗi trả ra có thể là **masked token**. Client phải gửi giá trị vừa nhận về đúng header/param mà handler đang mong đợi; không tự decode hoặc copy token từ một phiên khác.

Một phản hồi JSON **minh họa** có thể có dạng:

~~~json
{
  "headerName": "X-CSRF-TOKEN",
  "parameterName": "_csrf",
  "token": "gia-tri-do-server-phat-trong-phien-hien-tai"
}
~~~

Giá trị `token` trên chỉ là **chuỗi minh họa**, không phải token thực tế hoặc giá trị có thể sử dụng. Tên header/parameter thực tế lấy từ response; với `HttpSessionCsrfTokenRepository` mặc định thường là `X-CSRF-TOKEN` và `_csrf`.

### Không biến /csrf thành nơi phát token dùng chung

- Chỉ cấp token gắn với **request/session** đang xử lý; không cache token vào singleton bean, biến static hay một map chung theo application.
- Tránh CDN/browser cache trả JSON token của request khác; kiểm tra `Cache-Control` và các lớp reverse proxy. Có thể dùng `no-store` khi thiết kế endpoint.
- Không cho origin tùy ý đọc response có credential; hạn chế CORS và kiểm soát cookies.
- Bảo vệ khỏi XSS và rò rỉ HTML/JS. XSS có thể đọc dữ liệu/token same-origin, nên CSRF protection **không thay thế** output encoding/CSP và phòng chống XSS.
- Khi GET /csrf cho anonymous, endpoint cần thiết cho login vẫn có thể hoạt động, nhưng không gửi thêm user profile hoặc dữ liệu nhạy cảm trong cùng response.

## 10. Form server-rendered: render token cùng phiên hiện tại

Với Thymeleaf + Spring MVC tích hợp Spring Security, form POST được render qua `th:action` thường nhận hidden CSRF field do Spring Security `RequestDataValueProcessor` cung cấp.

Ví dụ `src/main/resources/templates/note-form.html`:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Ghi chú</title>
</head>
<body>
    <h1>Lưu ghi chú</h1>
    <form th:action="@{/api/notes}" method="post">
        <label for="text">Nội dung</label>
        <input id="text" name="text" required>
        <button type="submit">Lưu</button>
    </form>
</body>
</html>
~~~

Trong cấu hình Spring MVC/Thymeleaf chuẩn, `th:action` và Spring Security integration có thể tự thêm hidden field CSRF khi render form. **Hãy kiểm tra HTML đã render** để xác nhận thực sự có `input name="_csrf"` và giá trị phù hợp. Không thêm một hidden field thứ hai cùng tên nếu integration đã tự tạo, vì có thể làm request có nhiều giá trị khiến chẩn đoán khó hơn.

Nếu dùng JSP hoặc HTML tự dựng, bạn có thể xuất token từ request attribute `_csrf` và đưa vào hidden field. Ví dụ một phần template khi đã có `_csrf`:

~~~html
<input type="hidden"
       th:name="${_csrf.parameterName}"
       th:value="${_csrf.token}">
~~~

Đây là **mảnh Thymeleaf độc lập để minh họa**, không nên ghép thêm vào form `th:action` đã tự tiêm token mà không kiểm tra kết quả render. Trong template Thymeleaf thật, dùng cú pháp `th:name="${_csrf.parameterName}"` và `th:value="${_csrf.token}"` để engine thay bằng giá trị của request hiện tại; dấu `${...}` trong bản mẫu này được thay thành cú pháp Thymeleaf thực trước khi lưu bài.

**Khi form đã tồn tại lâu:** một page server-rendered chỉ chứa token **tại thời điểm render**. Nếu session đã đổi, không có cơ chế nào tự sửa hidden field trong DOM cũ. Sau login/logout hoặc timeout, redirect GET và render form lại; với UI muốn bảo toàn dữ liệu nhập, lưu draft cẩn thận rồi phục hồi **sau khi user reauthenticate**.

### Session timeout không nên được xử lý bằng việc giữ token cũ mãi mãi

Một số người muốn lưu CSRF token vào localStorage, rồi tái dùng bất chấp session mới. Cách đó **không** biến old token thành valid: expected token phía server được ràng buộc vào session/repository hiện tại. Lưu token lâu dài ngoài đời cũng tăng nguy cơ lộ thông tin và làm rối lifecycle. Hãy lấy token hiện tại theo đúng phiên, không tái sử dụng token từ phiên đã hết.

## 11. SPA/Fetch: refresh token sau authentication change

Một SPA thường giữ token trong memory và gửi token trong HTTP header. Với endpoint `GET /csrf` ở phần 9, có thể tránh phụ thuộc cookie/raw-token handling phức tạp bằng cách lấy token **đã được Spring Security handler phát cho request**.

~~~javascript
let csrfState = null;

async function refreshCsrf() {
  const response = await fetch("/csrf", {
    method: "GET",
    credentials: "same-origin",
    cache: "no-store"
  });

  if (!response.ok) {
    throw new Error("Không lấy được CSRF token cho phiên hiện tại");
  }

  const data = await response.json();
  if (!data.token || !data.headerName) {
    throw new Error("Phản hồi CSRF không hợp lệ");
  }
  csrfState = data;
}

async function createNote(text) {
  if (!csrfState) {
    await refreshCsrf();
  }

  const response = await fetch("/api/notes", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      [csrfState.headerName]: csrfState.token
    },
    body: JSON.stringify({ text })
  });

  if (response.status === 403) {
    // 403 có thể là CSRF hoặc thiếu quyền, không tự retry POST.
    throw new Error("Request bị từ chối; kiểm tra phiên và quyền");
  }

  if (!response.ok) {
    throw new Error("Lưu ghi chú thất bại");
  }

  return response.text();
}
~~~

Cách dùng đúng:

1. SPA khởi tạo `refreshCsrf()` trước các unsafe requests.
2. Sau **login thành công** và đã áp dụng session cookie hiện tại, gọi `refreshCsrf()` lại; không dùng token trước login.
3. Sau logout, nếu SPA cần render login form POST, gọi lại token endpoint trong ngữ cảnh anonymous **mới**.
4. Khi nhận tín hiệu session change từ tab khác, làm mới token, cập nhật UI và tài khoản đang hiển thị. Không tiếp tục gửi thao tác của user cũ dưới session user mới.
5. Nếu POST trả 403, phân loại lỗi bằng thiết kế server (log/error code không lộ bí mật). Không tự thử lại mọi 403, đặc biệt với payment, xóa, submit và thao tác không idempotent.

Đây là **JavaScript trình duyệt**, không phải code độc lập trong Node. `createNote` giả định app có endpoint xử lý POST `/api/notes`. Nếu backend nhận JSON, controller/service phải được cấu hình phù hợp và **vẫn phải kiểm tra authorization**.

### Khi dùng CookieCsrfTokenRepository và header X-XSRF-TOKEN

Spring Security có `CookieCsrfTokenRepository` cho các ứng dụng muốn đưa CSRF token qua cookie. Với JavaScript phải đọc cookie, một cấu hình thường được nhắc đến là:

~~~java
http.csrf(csrf -> csrf
        .csrfTokenRepository(
                CookieCsrfTokenRepository.withHttpOnlyFalse()));
~~~

Đây là **mảnh cấu hình** đặt bên trong cấu hình `HttpSecurity` và cần import `org.springframework.security.web.csrf.CookieCsrfTokenRepository`. Nó chỉ phù hợp nếu ứng dụng **thực sự cần JS đọc cookie CSRF**; để mặc định HttpOnly khi JavaScript không cần đọc cookie có thể an toàn hơn về mặt phơi bày token.

**Quan trọng trong Spring Security 6:** cookie thường chứa raw token, còn request attribute có thể được XOR-mask. Nếu frontend đọc raw cookie `XSRF-TOKEN` và gửi header `X-XSRF-TOKEN`, phải cấu hình `CsrfTokenRequestHandler` phù hợp với SPA (phân biệt raw header và masked form token), đồng thời xử lý deferred token và việc xóa token sau login/logout. **Chỉ đổi repository như snippet trên chưa đủ** để bảo đảm mọi flow SPA hoạt động.

Không chọn `CookieCsrfTokenRepository` chỉ để né lỗi session timeout; nó có lifecycle và nguy cơ riêng. CSRF token không được dùng như access token, không thay thế authentication và phải được kiểm thử khi thay đổi session/authentication.

## 12. Ví dụ ứng dụng để kiểm thử lifecycle thật

Phần này tạo ứng dụng Java 17+/Spring Boot 3.x nhỏ nhất có thể để kiểm tra cả login và CSRF. Các classes nằm trong `com.example.csrf`, có `CsrfSecurityConfig`, `CsrfDemoApplication` và `CsrfController` từ phần trước.

### User demo cho form login

File `src/main/java/com/example/csrf/DemoUsers.java`:

~~~java
package com.example.csrf;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;

@Configuration
public class DemoUsers {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                    .password(encoder.encode("local-demo-password"))
                    .roles("USER")
                    .build());
    }
}
~~~

`local-demo-password` chỉ là mật khẩu **minh họa cho test local**, không sử dụng cho production. Mật khẩu thật phải được quản trị bằng secret store/user store và chính sách xác thực phù hợp. Demo không có MFA, LDAP hoặc IdP.

### Endpoint cần CSRF và authentication

File `src/main/java/com/example/csrf/NoteController.java`:

~~~java
package com.example.csrf;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class NoteController {

    @PostMapping(value = "/api/notes",
            produces = MediaType.TEXT_PLAIN_VALUE)
    public ResponseEntity<String> create() {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body("saved");
    }
}
~~~

Đây là endpoint chỉ trả chuỗi để test, không xử lý dữ liệu nhạy cảm. Trong ứng dụng thật, nhận input hợp lệ, áp dụng authorization/owner/tenant checks tại server và tránh duplicate side effects khi client retry.

## 13. MockMvc test: token cũ sau login bị từ chối

Bộ test này **không dùng `@WithMockUser`** để mô phỏng login, vì mục đích là quan sát token bị xóa bởi authentication strategy trong **form-login filter chain thật** của ứng dụng mẫu.

File `src/test/java/com/example/csrf/CsrfLifecycleTest.java`:

~~~java
package com.example.csrf;

import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

@SpringBootTest
@AutoConfigureMockMvc
class CsrfLifecycleTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    ObjectMapper json;

    private record TokenData(
            String header, String parameter, String value) {
    }

    private TokenData fetchCsrf(MockHttpSession session)
            throws Exception {
        MvcResult response = mvc.perform(get("/csrf").session(session))
                .andExpect(status().isOk())
                .andReturn();

        JsonNode body =
                json.readTree(response.getResponse().getContentAsString());

        return new TokenData(
                body.path("headerName").asText(),
                body.path("parameterName").asText(),
                body.path("token").asText());
    }

    private void login(MockHttpSession session, TokenData before)
            throws Exception {
        mvc.perform(post("/login")
                .session(session)
                .param("username", "alice")
                .param("password", "local-demo-password")
                .param(before.parameter(), before.value()))
            .andExpect(status().is3xxRedirection());
    }

    @Test
    void oldTokenIsRejectedAfterSuccessfulLogin() throws Exception {
        MockHttpSession session = new MockHttpSession();
        TokenData anonymous = fetchCsrf(session);

        login(session, anonymous);

        // CSRF token phát trước login không còn hợp lệ.
        mvc.perform(post("/api/notes")
                .session(session)
                .header(anonymous.header(), anonymous.value()))
            .andExpect(status().isForbidden());

        // Lấy token mới trong session đã xác thực.
        TokenData current = fetchCsrf(session);
        mvc.perform(post("/api/notes")
                .session(session)
                .header(current.header(), current.value()))
            .andExpect(status().isCreated());
    }

    @Test
    void twoTabsWithSameSessionDoNotAutomaticallyInvalidateToken()
            throws Exception {
        MockHttpSession session = new MockHttpSession();
        login(session, fetchCsrf(session));

        TokenData tabA = fetchCsrf(session);
        TokenData tabB = fetchCsrf(session);

        // Hai biểu diễn XOR khác nhau vẫn có thể cùng hợp lệ.
        mvc.perform(post("/api/notes")
                .session(session)
                .header(tabA.header(), tabA.value()))
            .andExpect(status().isCreated());

        mvc.perform(post("/api/notes")
                .session(session)
                .header(tabB.header(), tabB.value()))
            .andExpect(status().isCreated());
    }

    @Test
    void oldTokenIsRejectedWhenItsSessionIsGone() throws Exception {
        MockHttpSession oldSession = new MockHttpSession();
        TokenData oldToken = fetchCsrf(oldSession);

        // Mô phỏng request xuất hiện trong một session mới/khác.
        MockHttpSession newSession = new MockHttpSession();

        mvc.perform(post("/api/notes")
                .session(newSession)
                .header(oldToken.header(), oldToken.value()))
            .andExpect(status().isForbidden());
    }
}
~~~

Điểm đọc test:

1. `fetchCsrf(session)` gửi GET để buộc token được materialize, đọc header/parameter/value đã được Spring Security cung cấp.
2. `login(...)` gửi POST thực qua Spring Security form-login filter với **token trước login hợp lệ**; sau authentication, CSRF strategy xóa token đã dùng.
3. `oldTokenIsRejectedAfterSuccessfulLogin` cho thấy việc gửi token cũ nhận 403, trong khi token được lấy lại sau login có thể thực hiện POST bình thường.
4. `twoTabsWithSameSessionDoNotAutomaticallyInvalidateToken` cố ý lấy hai token biểu diễn dưới cùng một session sau login rồi POST hai lần; không nên kết luận token tự sai chỉ vì thêm tab.
5. `oldTokenIsRejectedWhenItsSessionIsGone` mô phỏng token từ session A gửi trong session B; chỉ kiểm tra CSRF, **không phải** bài test thời gian hết hạn thật hoặc quản trị session store.

**Giới hạn:** MockMvc là mô phỏng Servlet request/response và sessions trong JVM test; nó không chạy browser thật, cookie SameSite, reverse proxy, TLS hoặc load balancer. Để kiểm thử timer/session timeout thật và browser back navigation, cần thêm browser/server integration tests trên môi trường cấu hình tương ứng.

Chạy trong dự án Maven đầy đủ:

~~~bash
mvn test
~~~

Kết quả pass/fail cuối cùng phải được quan sát trên dự án và phiên bản đang dùng; không bịa stdout Maven. Nếu test khác kỳ vọng do custom filters/CSRF repo/handler hoặc Spring Security version, điều tra cấu hình thay vì sửa assertion để che lỗi.

## 14. MockMvc hỗ trợ test CSRF, nhưng không tự chứng minh vòng đời token

Spring Security Test cung cấp post-processors:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;

mvc.perform(post("/api/notes").with(csrf()))
   .andExpect(status().isCreated());

mvc.perform(post("/api/notes").with(csrf().useInvalidToken()))
   .andExpect(status().isForbidden());
~~~

Đây là **đoạn test minh họa**: để request đầu thành công, còn phải có `Authentication` phù hợp (ví dụ `@WithMockUser`) và `MockMvc` đã tích hợp Spring Security. `csrf()` chuẩn bị CSRF token test hợp lệ; `csrf().useInvalidToken()` đặt token không hợp lệ để kiểm tra filter từ chối.

Công cụ này rất hữu ích để test **CSRF policy tại một endpoint**, nhưng không chứng minh login thật đã xóa token hoặc session timeout thực sự làm token lỗi. Muốn test lifecycle, phải tạo token qua **request flow thật trong context test** như phần 13.

### Chọn đúng câu hỏi test

| Loại test | Có thể chứng minh | Không chứng minh |
| --- | --- | --- |
| `@WithMockUser` + `csrf()` | Endpoint từ chối/cho phép khi có identity giả và CSRF hợp lệ. | Login/filter rotation, password, session timeout. |
| `csrf().useInvalidToken()` | Request với actual token sai bị CSRF filter từ chối. | Vì sao token user thực tế bị sai. |
| MockMvc GET /csrf → POST /login → POST token cũ | Token flow/strategy của cấu hình Servlet test. | Browser cookie policy hoặc cluster session replication. |
| Server integration test với timeout thực | Hành vi sau session expiration trên server. | Mọi biến thể browser nếu không dùng browser thật. |
| Browser E2E nhiều tab | Thao tác thực tế khi login/logout/tab cũ/back cache. | Mọi node/tenant/production topology nếu test môi trường khác. |

**Tránh test 403 sai lý do:** để kiểm tra authorization, cung cấp token CSRF hợp lệ. Để kiểm tra CSRF, cung cấp principal có quyền phù hợp; nếu không, cùng HTTP 403 có thể do nguyên nhân khác.

## 15. Chẩn đoán theo thứ tự: từ response đến session

Khi nhận một sự cố CSRF 403, thay vì disable security, hãy lần theo các câu hỏi:

### Bước 1 — Xác định chính xác request lỗi

Ghi lại **HTTP method, URL, status, thời điểm, tab và thao tác trước đó**. Request lỗi là POST login, submit form, XHR save, logout hay endpoint management? Đảm bảo route thực sự nằm trong Spring Security filter chain mà bạn nghĩ đang áp dụng.

Đừng gửi raw session cookies, password, CSRF token hoặc Authorization headers vào ticket công khai.

### Bước 2 — Xem 403 là CSRF hay authorization

Trong môi trường test/dev có log được kiểm soát, Spring Security có thể cho biết `CsrfFilter` từ chối vì missing/invalid token. Những loại exception liên quan là `MissingCsrfTokenException` và `InvalidCsrfTokenException` (phụ thuộc điều kiện request/repository/handler). Nếu là `AccessDeniedException` vì authority thì phải xử lý quyền, không refresh CSRF bừa.

Có thể tạm tăng log cho môi trường dev/test:

~~~properties
logging.level.org.springframework.security.web.csrf=DEBUG
logging.level.org.springframework.security=DEBUG
~~~

Không bật ghi verbose có dữ liệu nhạy cảm ở production mà không rà soát. Khi cần correlation, ghi request ID và session identifier **đã ẩn/hashed một chiều phù hợp**, không ghi raw JSESSIONID hoặc token.

### Bước 3 — Kiểm tra cookie session ở request lỗi

Trong DevTools Network (môi trường được phép), quan sát:

- Có cookie phiên được gửi không? `JSESSIONID` có bị thay sau login/logout không?
- Cookie `Path`, `Domain`, `Secure`, `SameSite` có phù hợp đường URL? Ứng dụng chạy sau reverse proxy có hostname/scheme thay đổi?
- Browser có chặn cookie vì `SameSite`/third-party-cookie policy không?
- Request tới đúng host, protocol, context path và node/cluster/session store không?
- Session đã timeout hoặc bị invalidated bởi logout/đăng nhập lại ở tab khác chưa?

**Không paste raw cookie vào log/chat.** Thay đổi session cookie có thể là dấu hiệu hợp lý của login/session fixation hoặc cookie scope sai, không tự động khẳng định tấn công.

### Bước 4 — Kiểm tra token thực sự được gửi

Với form server-rendered, xem hidden field `_csrf` đã được render chưa và form có gửi đúng name/value không. Với SPA, xem header `X-CSRF-TOKEN`/`X-XSRF-TOKEN` có xuất hiện trong request như dự kiến không.

Đừng tự so raw cookie và hidden token string: XOR handler có thể làm chúng khác biểu diễn dù vẫn hợp lệ. So sánh bằng cách tái hiện request qua Spring Security handler, không phải so chuỗi trực tiếp.

Các nguyên nhân kỹ thuật thường gặp:

- Frontend chỉ lấy token trước login, không refresh sau login.
- JS giữ token trong biến, nhưng tab khác logout/login đã làm phiên đổi.
- Server-rendered page được cache; browser quay lại form cũ qua back-forward cache.
- Form bị tạo bằng plain HTML mà không mang hidden token.
- Header name sai hoặc bị proxy loại bỏ.
- CORS/preflight hoặc credential mode khiến session cookie không được gửi.
- Cookie repository được dùng với raw token nhưng handler chỉ chấp nhận masked token.
- Session store mất state khi load balancer chuyển node, hoặc session serialization có vấn đề.
- CSRF repository bị thay/custom theo cấu hình của một chain mà frontend không biết.

### Bước 5 — Kiểm tra lifecycle authentication

Xác định có login/logout trong khoảng thời gian giữa GET form và POST không. Với Spring Security form-login mặc định, authentication success có thể xóa CSRF token; logout cũng có thể xóa token. Nếu app dùng custom OAuth2/SAML login, custom filter hoặc API login, kiểm tra **token clearing strategy thực tế** chứ không tự suy ra rằng mọi login đều giống nhau.

Nếu có nhiều tabs, xác định tab nào tạo authentication change. Một tab đăng nhập thành user B có thể làm tab A chuyển sang principal B; **không** cho phép thao tác của A tự động tiếp tục dưới B.

### Bước 6 — Xác nhận cách khắc phục bằng test âm/dương

Test token cũ bị từ chối **và** token mới thành công. Nếu chỉ test token mới 200, không chứng minh hệ thống ngăn token stale; nếu chỉ test token cũ 403, có thể do thiếu quyền hoặc CSRF request body sai. Kiểm tra cùng endpoint, cùng principal và status/body theo kịch bản cụ thể.

## 16. Các lỗi thường gặp và hướng sửa

| Triệu chứng | Khả năng nguyên nhân | Cách sửa/kiểm chứng |
| --- | --- | --- |
| POST ngay sau login trả 403, GET vẫn chạy | Token từ trước login bị xóa; SPA/form chưa refresh. | Sau login, GET token mới hoặc render lại form. Test token cũ 403/token mới thành công. |
| Form mở lâu bị 403 sau timeout | Expected token trong old session không còn. | Phát hiện phiên hết, reauthenticate, lấy token mới, bảo toàn draft an toàn. |
| Tab A lỗi sau khi tab B login/logout | Session/CSRF token chia sẻ đã thay đổi, tab A vẫn dùng stale DOM/token. | Thông báo session change, refresh token/form, xác nhận identity trước submit. |
| Hai tab có token string khác nhau | XOR masking tạo biến thể biểu diễn của cùng token. | Không xem khác string là token invalid; test cả hai request dưới cùng session. |
| SPA đọc cookie XSRF-TOKEN rồi gửi header nhưng vẫn 403 | Raw token vs masked handler mismatch hoặc thiếu token mới sau auth. | Dùng SPA-compatible request handler / endpoint cấp token; test GET/POST, login/logout. |
| POST /login báo 403 | Form login không gửi CSRF token, token thuộc session khác hoặc cookie không gửi. | GET login/token đúng session; không tắt CSRF login bừa. |
| 403 nhưng không thấy controller log | `CsrfFilter` hoặc URL authorization từ chối trước khi vào handler. | Debug filter chain và exception cause. |
| 403 dù CSRF đúng | User thiếu role/quyền/ownership; có thể từ `AuthorizationFilter` hoặc method security. | Chẩn đoán authorization riêng, không tự refresh/retry POST. |
| Session ID đổi sau login | Session fixation protection, không nhất thiết là lỗi. | Kiểm tra CSRF clearing và token refresh thay vì disable session fixation protection. |
| Chỉ lỗi sau đổi host/proxy | Cookie domain/path/scheme, forwarded headers hoặc header bị proxy loại. | Kiểm tra public URL, cookie scope và trusted proxy setup. |
| Chỉ lỗi khi cluster chuyển node | Session state không shared/sticky, repository mất expected token. | Dùng session store đồng bộ hoặc sticky session hợp lý; test failover. |
| GET /csrf trả token nhưng POST không thấy cookie | `fetch` credentials mode, SameSite/Secure, browser cookie policy. | Dùng credentials phù hợp, kiểm tra origin và session cookies, không mở CORS bừa. |
| Test MockMvc csrf() pass nhưng browser fail | Test tự đưa valid token, không kiểm tra lifecycle/cookies/browser behavior. | Thêm flow integration và browser nhiều tab. |
| CSRF lỗi sau logout | Token cũ đã bị xóa, nhưng frontend vẫn dùng khi login lại. | Fetch token mới trong anonymous session rồi mới POST login. |
| 403 “thỉnh thoảng” khi gửi nhiều request bất đồng bộ | Race giữa login/session refresh và POST đang dùng token cũ. | Serialize auth transition với requests cần bảo vệ; không gửi unsafe requests cho tới khi token mới sẵn sàng. |

## 17. Cách sửa sai cần tránh

**Không dùng các cách “chữa 403” sau đây nếu chưa có thiết kế bảo mật phù hợp:**

~~~java
// Anti-pattern cho ứng dụng dùng session/cookie:
http.csrf(csrf -> csrf.disable());
~~~

Tắt CSRF toàn app làm mất một lớp bảo vệ quan trọng. Những lựa chọn khác cũng có rủi ro:

- Exempt mọi `/api/**` mặc dù browser tự gửi session cookie tới API.
- Chấp nhận mọi token cũ từ session khác hoặc cất một token static cho toàn hệ thống.
- Tắt session fixation protection chỉ vì JSESSIONID thay sau login.
- Mở CORS cho mọi origin kết hợp credentials và expose token endpoint, thay vì sửa origin/cookie/handler đúng.
- Dùng GET thay POST cho thao tác ghi/xóa nhằm “né” CsrfFilter.
- Tự động retry mọi unsafe request sau 403 mà không xác minh CSRF/authorization và tránh duplicate side effects.
- Giữ CSRF token trong URL query hoặc redirect URL khiến nó lộ vào history/logs/referrer.
- Bỏ yêu cầu role/owner vì POST bị 403 “dù token đúng”.
- Ghi raw `CSRF token`, cookie, password, JWT, SAML Response hoặc session ID vào production logs.

**Sửa đúng là đồng bộ token của request với trạng thái session hiện tại, đồng thời giữ nguyên authorization và CSRF policy.**

## 18. Checklist chẩn đoán và phục hồi an toàn

1. Xác định 403 do **CSRF** hay **thiếu quyền** bằng filter/exception evidence, không chỉ status.
2. Kiểm tra route/method có được CsrfFilter bảo vệ không; thử đúng unsafe request.
3. Xác định expected token lưu ở **HttpSessionCsrfTokenRepository** hay **CookieCsrfTokenRepository**; có custom handler không.
4. Đọc timeline: GET form/token → login/logout → POST; token có bị xóa sau authentication success không?
5. Kiểm tra session timeout và state restore trong load-balanced/cluster setup.
6. Với nhiều tab, kiểm tra có login/logout/account switch ở tab khác không. **Không** giả định chỉ mở tab thứ hai là lỗi.
7. Với server-rendered form, bảo đảm hidden CSRF field có trong HTML thực và trang được re-render sau login/session change.
8. Với SPA, lấy token từ endpoint đáng tin sau login/logout, dùng header/parameter đúng; đừng gửi token raw khi handler đòi masked nếu chưa cấu hình SPA-compatible.
9. Kiểm tra cookie SessionID, Path/Domain/Secure/SameSite và fetch credentials; rà soát reverse proxy/ingress.
10. Không cho frontend tiếp tục request của user trước đó sau khi principal đã thay đổi.
11. Test **token cũ bị từ chối**, **token mới thành công** và **hai tab cùng session không bị invalid ngẫu nhiên**.
12. Tách riêng test CSRF với test role/owner bằng cách đảm bảo các điều kiện khác hợp lệ.
13. Không tự retry POST/DELETE/PAYMENT khi 403 chưa được phân loại; dùng idempotency/draft recovery khi cần.
14. Hạn chế log PII/secrets; kiểm tra cache-control của token endpoint và CORS/credentials đúng.
15. Sau khi sửa, test lại login, logout, timeout, back-button, reload, mở hai tab và cluster failover trong môi trường phù hợp.

## 19. Câu hỏi tự kiểm tra

**Câu 1:** Hai tab cùng session nhận hai chuỗi `_csrf` khác nhau nhưng cùng POST thành công. Có phải Spring đang thay expected token sau mọi GET?

**Trả lời:** Không nhất thiết. Với XOR masking, hai lần render có thể trả **hai biểu diễn khác nhau** của cùng raw expected token. Phải kiểm tra server repository/session lifecycle trước khi kết luận token bị rotate.

**Câu 2:** Sau login, SPA gửi header token trước login và bị 403. Có nên disable CSRF cho `/api/**`?

**Trả lời:** Không. Hãy lấy token mới sau authentication success, xác minh session cookie và request handler. Nếu API thực sự không sử dụng browser-autosent credentials, đánh giá threat model riêng trước khi thay policy.

**Câu 3:** User chỉ dùng GET sau session hết hạn và được redirect login, nhưng POST form cũ lại 403. Tại sao?

**Trả lời:** `CsrfFilter` có thể từ chối unsafe request mang token session cũ **trước khi** authentication entry point thực hiện redirect. Hai request đi qua các kiểm tra khác nhau.

**Câu 4:** MockMvc test `.with(csrf())` thành công nhưng thao tác trong tab cũ vẫn bị 403. Mâu thuẫn?

**Trả lời:** Không. `csrf()` cấp token hợp lệ cho request test hiện tại; nó không diễn lại việc token bị xóa lúc login/logout, session timeout hoặc browser giữ token cũ. Cần lifecycle/E2E tests.

**Câu 5:** Làm thế nào chứng minh không chỉ lỗi role?

**Trả lời:** Với cùng user và endpoint cần quyền, kiểm tra request có **token mới** thành công; sử dụng logs/exception context cho `CsrfFilter` và test quyền riêng. Một status 403 không đủ làm bằng chứng.

## 20. Tổng kết

Trong Spring Security Servlet, CSRF token phải **khớp với expected token hiện tại của repository/session**. Sau **đăng nhập** hoặc **đăng xuất**, các strategies của Spring Security có thể **xóa token cũ**; sau **timeout**, token gắn với session trước có thể biến mất. **Nhiều tab không tự gây lỗi**, nhưng tab có thể giữ HTML/JavaScript state cũ sau khi session chung thay đổi. Ngoài ra, Spring Security 6 có **deferred token** và **XOR masking**, vì vậy “hai chuỗi token nhìn khác nhau” không mặc nhiên đồng nghĩa hai expected tokens khác nhau.

**Chiến lược an toàn:** giữ CsrfFilter, xác định đúng repository/handler, refresh token sau authentication change, render lại form hoặc fetch token cho SPA, chẩn đoán CSRF tách biệt với authorization, và test cả stale-token rejection lẫn refreshed-token success. Không giải quyết lỗi 403 bằng cách vô hiệu hóa CSRF trên ứng dụng đang dùng cookie/session.

## Tài liệu tham khảo

- Spring Security — CSRF protection, Servlet: https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html
- Spring Security — CSRF testing with MockMvc: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html
- Spring Security API — CsrfFilter: https://docs.spring.io/spring-security/site/docs/6.5.11/api/org/springframework/security/web/csrf/CsrfFilter.html
- Spring Security API — CsrfAuthenticationStrategy: https://docs.spring.io/spring-security/site/docs/6.5.11/api/org/springframework/security/web/csrf/CsrfAuthenticationStrategy.html
- Spring Security API — XorCsrfTokenRequestAttributeHandler: https://docs.spring.io/spring-security/site/docs/6.5.11/api/org/springframework/security/web/csrf/XorCsrfTokenRequestAttributeHandler.html
