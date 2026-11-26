# Bảo vệ yêu cầu đăng nhập và đăng xuất

## Mục tiêu học tập

Sau bài học thuộc chương **Cơ chế CSRF**, người học có thể:

- Giải thích vì sao **đăng nhập** và **đăng xuất** là những thao tác cần bảo vệ CSRF, dù đăng nhập có thể xảy ra khi người dùng chưa có phiên xác thực.
- Phân tích **login CSRF** (ép trình duyệt đăng nhập vào tài khoản do kẻ tấn công kiểm soát) và **logout CSRF** (ép người dùng rời khỏi phiên hiện tại), cùng tác động thực tế của từng trường hợp.
- Hiểu hành vi mặc định với `POST /login`, `POST /logout` và `GET /logout` trong Spring Security khi CSRF đang bật; phân biệt **trang xác nhận đăng xuất** với thao tác đăng xuất thật.
- Tạo form login/logout đúng cách, gửi token qua hidden field hoặc header và dùng các cơ chế chuẩn của Spring Security **Servlet** và **Reactive/WebFlux**.
- Mô tả việc CSRF token có thể bị xóa hoặc thay sau xác thực, đăng xuất, thay phiên; thiết kế luồng **lấy lại token** cho trang server-rendered và SPA.
- Kiểm thử các request thiếu/sai CSRF token, login/logout thành công, phiên cũ và xung đột bảo mật khi triển khai qua nhiều filter chain hoặc reverse proxy.
- Phân biệt logout phiên của ứng dụng với **thu hồi access/refresh token**, phiên tại Identity Provider và luồng OAuth2/OIDC.

## 1. Vì sao đăng nhập và đăng xuất thuộc phạm vi CSRF?

Khi nói đến CSRF, nhiều người nghĩ ngay đến chuyển tiền hoặc đổi email. Tuy nhiên **đăng nhập cũng tạo ra trạng thái bảo mật mới**, còn **đăng xuất làm thay đổi trạng thái phiên hiện tại**. Vì vậy, cả hai cần được đánh giá như những thao tác có tác động, thường thực hiện bằng **HTTP POST kèm CSRF token**.

Ví dụ ứng dụng `https://app.example.com` dùng form login và cookie phiên:

~~~http
POST /login HTTP/1.1
Host: app.example.com
Content-Type: application/x-www-form-urlencoded

username=alice&password=secret
~~~

Request không nhất thiết có cookie phiên đã xác thực: đây là bước **tạo ngữ cảnh đăng nhập**. Nếu server tiếp nhận POST từ bất kỳ trang nào mà không kiểm tra CSRF, một website ngoài có thể cố tình gửi thông tin đăng nhập của **một tài khoản do attacker sở hữu** tới endpoint đó.

Với đăng xuất:

~~~http
POST /logout HTTP/1.1
Host: app.example.com
Cookie: JSESSIONID=session-of-alice
~~~

Trình duyệt có thể tự gắn cookie phiên vào request nếu chính sách cookie cho phép. Nếu server không kiểm tra nguồn hợp lệ của yêu cầu, người dùng có thể bị **ép đăng xuất** chỉ vì họ mở trang độc hại.

> **Nguyên tắc:** CSRF kiểm tra tính hợp lệ của **yêu cầu thay đổi trạng thái bảo mật**. Một endpoint không tự an toàn chỉ vì nó không chuyển tiền, và việc người dùng chưa đăng nhập không đồng nghĩa POST đăng nhập không cần CSRF.

Trong module **SPRING_SECURITY_HTTP_PROTECTION**, bảo vệ login/logout là một phần của phòng vệ HTTP/trình duyệt cùng CORS, security headers, CSP, HSTS, HTTP firewall và bảo vệ session. Spring Security cung cấp cơ chế cho cả **Servlet** và **Reactive**; trách nhiệm của người triển khai là giữ các luồng login/logout đi qua chain phù hợp và cấp CSRF token đúng cách.

## 2. Login CSRF: ép nạn nhân đăng nhập vào tài khoản do attacker kiểm soát

### 2.1. Diễn tiến của một cuộc login CSRF

Giả sử attacker có tài khoản `attacker-account` trong hệ thống mua sắm. Họ muốn nạn nhân sử dụng phiên của tài khoản ấy rồi vô tình lưu lịch sử hoạt động, thông tin tìm kiếm hoặc dữ liệu cá nhân vào nơi attacker có thể xem.

Nếu endpoint login không kiểm tra CSRF, trang attacker có thể dựng form:

~~~html
<!-- Minh họa kịch bản tấn công: không dùng trong hệ thống thật. -->
<form id="forced-login" method="post"
      action="https://shop.example.com/login">
  <input type="hidden" name="username" value="attacker-account">
  <input type="hidden" name="password" value="attacker-controlled-password">
</form>
<script>
  document.getElementById("forced-login").submit();
</script>
~~~

Nếu trình duyệt gửi request và ứng dụng xử lý login, server có thể tạo hoặc thay đổi ngữ cảnh xác thực, rồi trả cookie phiên tương ứng tài khoản của attacker. Nạn nhân tiếp tục thao tác trên website tưởng rằng mình đang ở tài khoản của mình.

~~~mermaid
sequenceDiagram
    actor U as Nạn nhân
    participant B as Trình duyệt
    participant X as Trang attacker
    participant S as Ứng dụng đích

    U->>B: Mở trang do attacker điều khiển
    B->>X: Tải HTML
    X-->>B: Form POST /login có credential của attacker
    B->>S: POST /login
    alt Login không có CSRF protection
        S->>S: Xác thực tài khoản attacker
        S-->>B: Phản hồi login/cookie phiên theo policy
        U->>S: Tiếp tục hoạt động dưới tài khoản attacker
    else Login yêu cầu CSRF token hợp lệ
        S-->>B: Từ chối request thiếu/sai token
    end
~~~

**Kết quả cần hiểu đúng:** Login CSRF thường **không trực tiếp cấp cho attacker quyền đăng nhập vào tài khoản nạn nhân**. Nguy cơ là làm nạn nhân tương tác trong **tài khoản attacker**, từ đó làm rò rỉ dữ liệu người dùng nhập, liên kết không đúng tài khoản hoặc sai lệch quy trình.

Tác động cụ thể phụ thuộc thiết kế sản phẩm. Ví dụ:

- Lịch sử duyệt, tìm kiếm, nội dung được lưu trong tài khoản attacker.
- Người dùng vô tình đưa địa chỉ, tài liệu hoặc dữ liệu cá nhân vào tài khoản không thuộc mình.
- Một chức năng **liên kết tài khoản** tin vào ngữ cảnh đăng nhập không phù hợp, gây nhầm lẫn hoặc liên kết ngoài ý muốn.
- Ứng dụng hiển thị trạng thái đăng nhập mới nhưng người dùng không nhận ra danh tính hiện tại.

### 2.2. Vì sao login CSRF vẫn đáng quan tâm khi chưa có session đăng nhập?

Đây là điểm khác với CSRF thay đổi hồ sơ. Trong login CSRF, **request POST có thể chính là request tạo session đã xác thực**. Vì vậy attacker không nhất thiết cần browser tự gửi cookie xác thực đã tồn tại.

Cookie `SameSite=Lax` có thể loại cookie hiện có khỏi một cross-site POST, nhưng điều đó **không tự ngăn server xử lý một POST login và phát một session cookie mới**, nếu trình duyệt và ngữ cảnh điều hướng chấp nhận. Cần quan sát chính sách cookie và hành vi browser thật thay vì kết luận chỉ bằng một thuộc tính.

Để bảo vệ, trang login hợp lệ có thể cấp **CSRF token cho phiên chưa xác thực** (anonymous/pre-authentication session). Khi người dùng POST credentials, server kiểm chứng token **trước khi xác thực**. Token không cần được phát sau login mới có tác dụng; nếu đợi đến lúc đăng nhập xong mới kiểm tra, đã bỏ sót chính request cần bảo vệ.

### 2.3. Một request login hợp lệ

Trang `GET /login` cung cấp token:

~~~html
<form action="/login" method="post">
  <label for="username">Tên đăng nhập</label>
  <input id="username" name="username" autocomplete="username" required>

  <label for="password">Mật khẩu</label>
  <input id="password" name="password" type="password"
         autocomplete="current-password" required>

  <input type="hidden" name="_csrf" value="CSRF_TOKEN_FROM_APPLICATION">
  <button type="submit">Đăng nhập</button>
</form>
~~~

`CSRF_TOKEN_FROM_APPLICATION` là ký hiệu; thực tế phải là token được Spring Security phát hành và đưa vào form. **Token CSRF không phải mật khẩu** và **không thay thế kiểm tra credentials**. Request có CSRF token hợp lệ nhưng username/password sai vẫn phải thất bại ở bước xác thực.

## 3. Logout CSRF: ép người dùng rời phiên

### 3.1. Hậu quả của logout CSRF

Một attacker có thể dụ nạn nhân truy cập một URL nhằm kích hoạt logout. Nếu ứng dụng cho phép `GET /logout` **thực hiện đăng xuất ngay**, một điều hướng đơn giản có thể gây tác động.

~~~html
<!-- Trang ngoài có thể khiến browser điều hướng tới URL này. -->
<a href="https://app.example.com/logout">
  Xem nội dung ưu đãi
</a>
~~~

Nếu thao tác logout được kích hoạt qua GET, browser có thể gửi cookie trong một số điều hướng cấp cao, kể cả khi cookie dùng `SameSite=Lax`. Đây là một trong các lý do không dùng GET cho thao tác có tác động.

Với endpoint POST logout không kiểm tra CSRF, attacker có thể thử auto-submit form. Việc có thành công hay không phụ thuộc cookie, `SameSite`, tình huống cross-origin/cross-site và cấu hình server.

Logout CSRF thường gây **gián đoạn phiên**, mất dữ liệu form chưa lưu, trải nghiệm kém hoặc buộc người dùng thực hiện lại một luồng xác thực. Nó cũng có thể được dùng phối hợp với kỹ thuật giả mạo giao diện, lừa người dùng nhập lại thông tin ở nơi không đáng tin cậy. Không vì thiệt hại có thể nhỏ hơn chuyển tiền mà bỏ bảo vệ.

### 3.2. POST logout kèm token: cách làm khuyến nghị

~~~html
<form action="/logout" method="post">
  <input type="hidden" name="_csrf" value="CSRF_TOKEN_FROM_APPLICATION">
  <button type="submit">Đăng xuất</button>
</form>
~~~

Hành vi cần đạt:

1. Trình duyệt nhận form có token thật từ ứng dụng.
2. Khi người dùng bấm **Đăng xuất**, browser gửi `POST /logout` kèm cookie phiên nếu đủ điều kiện **và** giá trị `_csrf`.
3. Spring Security kiểm chứng CSRF trước khi tiến hành logout.
4. Nếu token hợp lệ, các handler đăng xuất thực hiện việc dọn trạng thái tương ứng.
5. Sau logout, token gắn với ngữ cảnh cũ thường không được tiếp tục chấp nhận.

Không nên dùng một thẻ `<a href="/logout">` rồi sửa server để **GET tự động đăng xuất**. Nếu cần giao diện trông giống liên kết, có thể dùng một nút trong form POST, hoặc JavaScript kích hoạt form POST có token. Nếu người dùng tắt JavaScript, vẫn có thể dùng form POST thuần HTML.

## 4. Hành vi mặc định Spring Security khi bật CSRF

Với cấu hình web dựa trên form login thông dụng, Spring Security mặc định bật CSRF protection. Các yêu cầu dùng phương thức có tác động như `POST` thường cần token; các phương thức được coi là an toàn như `GET` thường không bị kiểm tra token. Điều đó đặt yêu cầu thiết kế: **không dùng GET để thay đổi trạng thái**.

| URL + phương thức | Vai trò điển hình | Khi CSRF bật và form login/logout được cấu hình chuẩn |
|---|---|---|
| `GET /login` | Hiển thị trang đăng nhập | Cho phép xem form và nhận token; nếu dùng trang login tùy biến, ứng dụng phải render trang này |
| `POST /login` | Gửi username/password để xác thực | **Yêu cầu CSRF token** trước khi xử lý login |
| `GET /logout` | Trang xác nhận đăng xuất trong cấu hình mặc định có hỗ trợ | **Không thực hiện logout ngay**; cung cấp giao diện xác nhận có thể gửi POST kèm token |
| `POST /logout` | Thực hiện logout | **Yêu cầu CSRF token**, rồi xử lý logout nếu phù hợp |
| `GET /profile` | Đọc thông tin | Không đòi CSRF theo mặc định; vẫn cần kiểm tra truy cập |
| `POST /profile` | Thay đổi thông tin | Đòi CSRF nếu thuộc phạm vi bảo vệ |

**Phân biệt rất quan trọng:** Spring Security **có thể phản hồi `GET /logout` bằng một trang xác nhận**. Điều này **không có nghĩa** nó cho phép GET để đăng xuất. Chỉ khi người dùng xác nhận bằng **POST có token** thì logout mới được thực thi theo luồng mặc định.

Nếu vô hiệu hóa CSRF hoặc tự cấu hình matcher logout nhận GET, hành vi này có thể thay đổi: GET có thể trực tiếp kích hoạt logout. Đừng kết luận từ tên endpoint rằng GET đã được bảo vệ; hãy kiểm tra cấu hình thực tế.

### 4.1. Vì sao `permitAll()` không bỏ kiểm tra CSRF?

Một login page cần cho người chưa đăng nhập truy cập, nên cấu hình thường cho phép `/login`. Nhưng **authorization** và **CSRF** là hai cơ chế khác nhau:

- `permitAll()` cho phép request đi qua điều kiện **phân quyền** mà không yêu cầu người dùng đã đăng nhập.
- `CsrfFilter` hoặc `CsrfWebFilter` vẫn có thể yêu cầu token cho POST tương ứng.

Nói cách khác, **POST login có thể vừa được phép truy cập bởi anonymous user, vừa bắt buộc có CSRF token hợp lệ**. Điều này không mâu thuẫn.

## 5. Cấu hình và giao diện đăng nhập/đăng xuất cho Servlet

### 5.1. Giữ cơ chế mặc định khi dùng form login

Trong Spring Security Servlet, các thành phần thường gặp gồm:

- `UsernamePasswordAuthenticationFilter`: xử lý form login theo matcher đã cấu hình.
- `CsrfFilter`: kiểm tra CSRF trên POST login/logout và các unsafe request thuộc phạm vi bảo vệ.
- `LogoutFilter`: nhận request logout hợp lệ theo matcher.
- `SecurityContextLogoutHandler`: dọn security context, session khi cấu hình chuẩn.
- `CsrfAuthenticationStrategy` và `CsrfLogoutHandler`: quản lý việc xóa token CSRF ở các ranh giới bảo mật thích hợp.

Ví dụ cấu hình Servlet chọn form login và để CSRF hoạt động:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ServletSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults())
            .csrf(Customizer.withDefaults());

        return http.build();
    }
}
~~~

Đoạn này dùng trang login/logout được Spring Security cung cấp theo cấu hình thông dụng; cần có cơ chế xác thực user phù hợp (ví dụ `UserDetailsService`) và dependency thực tế. `csrf(Customizer.withDefaults())` **làm rõ ý định giữ CSRF**; nhiều cấu hình web mặc định đã bật mà không cần dòng này.

### 5.2. Tạo trang login tùy biến cho Servlet

Nếu muốn giao diện riêng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class CustomLoginSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/assets/**").permitAll()
                .anyRequest().authenticated()
            )
            .formLogin(login -> login
                .loginPage("/login")
                .loginProcessingUrl("/login")
                .permitAll()
            )
            .logout(logout -> logout
                .logoutUrl("/logout")
                .logoutSuccessUrl("/login?logout")
                .permitAll()
            );

        // Không disable hoặc ignore CSRF ở /login và /logout.
        return http.build();
    }
}
~~~

Với `loginPage("/login")`, chính ứng dụng phải cung cấp **GET /login**. Không tạo controller POST `/login` để tự gọi xác thực lần hai: bộ lọc Spring Security xử lý URL POST theo `loginProcessingUrl("/login")`.

~~~java
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
class LoginPageController {

    @GetMapping("/login")
    String loginPage() {
        return "auth/login"; // templates/auth/login.html
    }
}
~~~

Template Thymeleaf hiển thị token do Spring Security cung cấp:

~~~html
<!-- templates/auth/login.html -->
<form action="/login" method="post">
  <label for="username">Tên đăng nhập</label>
  <input id="username" name="username" required autocomplete="username">

  <label for="password">Mật khẩu</label>
  <input id="password" name="password" type="password"
         required autocomplete="current-password">

  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">

  <button type="submit">Đăng nhập</button>
</form>
~~~

Form gửi tên trường mặc định `username` và `password` cho cơ chế form login; nếu đã tùy chỉnh `usernameParameter` hoặc `passwordParameter` thì cần sửa form tương ứng. Thuộc tính `action` ở đây được viết trực tiếp cho dễ thấy; ứng dụng có context path cần tạo URL đúng.

Tích hợp Spring MVC/Thymeleaf có thể tự thêm hidden CSRF field khi dùng `th:action`. Hãy kiểm tra HTML render cuối cùng để tránh hai trường `_csrf` trùng nhau. Nếu tự render token, **không hardcode một giá trị cố định**.

### 5.3. Form đăng xuất tùy biến

Một trang đã xác thực có thể đặt nút:

~~~html
<form action="/logout" method="post">
  <input type="hidden"
         th:name="${_csrf.parameterName}"
         th:value="${_csrf.token}">
  <button type="submit">Đăng xuất</button>
</form>
~~~

Việc logout theo form mặc định do `LogoutFilter` xử lý, không cần tự tạo `@PostMapping("/logout")`. Một logout handler tùy biến quá mức có thể bỏ sót việc xóa `SecurityContext`, session, token CSRF hoặc remember-me. Nếu cần bổ sung dọn dữ liệu, ưu tiên tích hợp qua cấu hình logout/handlers của Spring Security.

### 5.4. GET /logout trong ứng dụng có giao diện riêng

Với trang xác nhận mặc định, `GET /logout` có thể trả giao diện yêu cầu người dùng xác nhận và cung cấp CSRF token cho POST. Nếu đã tùy biến login page, UI hoặc security chain, **không nên mặc định trang logout xác nhận luôn được sinh tự động như trước**. Ứng dụng có thể tự render một trang xác nhận logout, trong đó **nút xác nhận dùng POST có token**.

Nếu product chỉ cần nút Đăng xuất ngay trong thanh điều hướng, đặt trực tiếp form POST là đủ; không nhất thiết phải qua một trang GET xác nhận.

## 6. Cấu hình Reactive/WebFlux

### 6.1. CSRF áp dụng cho login/logout ở WebFlux

Với WebFlux, các thành phần tương ứng gồm `CsrfWebFilter`, `LogoutWebFilter`, `ServerHttpSecurity` và cơ chế `WebSession`/`ServerSecurityContextRepository`. Spring Security WebFlux bật CSRF theo cấu hình mặc định và bảo vệ login/logout trong luồng form tương ứng. Logout mặc định được kích hoạt bằng **POST**, không phải một GET thực hiện thay đổi trạng thái.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(authorize -> authorize
                .pathMatchers("/assets/**").permitAll()
                .anyExchange().authenticated()
            )
            .formLogin(Customizer.withDefaults())
            .logout(Customizer.withDefaults())
            .csrf(Customizer.withDefaults())
            .build();
    }
}
~~~

Ví dụ dùng các trang mặc định; ứng dụng thực tế cần cấu hình nguồn người dùng (ví dụ `ReactiveUserDetailsService`). Với trang login tùy biến, dùng `formLogin(login -> login.loginPage("/login"))` rồi **tự render GET /login**, tương tự Servlet.

### 6.2. Hiển thị CSRF token trong một view WebFlux

Khi request đã đi qua `CsrfWebFilter`, một `Mono<CsrfToken>` có thể được cung cấp qua exchange attribute để controller giải quyết khi render view:

~~~java
import org.springframework.security.web.server.csrf.CsrfToken;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.reactive.result.view.Rendering;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Controller
class ReactiveLoginPage {

    @GetMapping("/login")
    Mono<Rendering> login(ServerWebExchange exchange) {
        Mono<CsrfToken> csrf = exchange.getAttribute(
                CsrfToken.class.getName());

        return csrf.map(token ->
            Rendering.view("auth/login")
                .modelAttribute("_csrf", token)
                .build());
    }
}
~~~

Ví dụ giả định exchange attribute chứa `Mono<CsrfToken>` theo cơ chế filter/version được dùng. Cần bảo đảm route đã được security web filter xử lý; nếu tích hợp view cung cấp sẵn token, có thể dùng trực tiếp cách tích hợp đó. Template gửi token qua hidden field như ví dụ Servlet nhưng xử lý bởi stack WebFlux.

### 6.3. WebFlux logout có thể cần chủ động hủy WebSession

Tài liệu Spring Security Reactive mô tả việc logout mặc định dọn security context và kho CSRF token, **nhưng hủy toàn bộ WebSession có thể cần cấu hình thêm** khi ứng dụng yêu cầu semantics đó. Điều này khác với hành vi mặc định thường thấy ở Servlet, nơi `SecurityContextLogoutHandler` có thể vô hiệu hóa `HttpSession`.

Nếu ứng dụng cần hủy WebSession khi logout, có thể kết hợp các handler được cung cấp:

~~~java
import org.springframework.security.web.server.authentication.logout.DelegatingServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.SecurityContextServerLogoutHandler;
import org.springframework.security.web.server.authentication.logout.WebSessionServerLogoutHandler;

// Đưa vào cấu hình .logout(...) của ServerHttpSecurity:
.logout(logout -> logout.logoutHandler(
    new DelegatingServerLogoutHandler(
        new SecurityContextServerLogoutHandler(),
        new WebSessionServerLogoutHandler()
    )
))
~~~

Đây là **đoạn cấu hình thay thế** cho `.logout(Customizer.withDefaults())` khi có yêu cầu hủy session rõ ràng; không đặt hai cấu hình logout cạnh nhau. Các handler có thể cần điều chỉnh nếu ứng dụng dùng custom session store hoặc cơ chế đăng xuất khác. Quan trọng là giữ **POST logout có CSRF token** và kiểm thử được sự thay đổi trạng thái xác thực thực tế.

## 7. Vòng đời CSRF token trước và sau đăng nhập/đăng xuất

### 7.1. Token trước đăng nhập

Trang login thường cần lấy token khi người dùng **chưa đăng nhập**. Với mẫu synchronizer token, repository có thể lưu một giá trị theo phiên chưa xác thực. Token này giúp server xác minh POST login đến từ luồng đã được ứng dụng phát hành.

Không nhầm **phiên chưa xác thực** với **phiên đã xác thực**. Một anonymous session có thể được tạo chỉ để lưu CSRF token hoặc các dữ liệu cần thiết cho luồng bảo mật; sự tồn tại của session chưa đồng nghĩa user đã login.

### 7.2. Khi xác thực thành công

Trong Spring Security Servlet, `CsrfAuthenticationStrategy` có thể xóa CSRF token cũ tại ranh giới xác thực. Theo cấu hình thông dụng, Spring Security cũng có cơ chế bảo vệ **session fixation**, có thể thay session ID khi đăng nhập.

Mục đích:

- Không tiếp tục tái sử dụng một token đã phát trước khi danh tính được xác thực trong những ngữ cảnh không phù hợp.
- Cho phép token mới được cấp theo phiên/ngữ cảnh sau đăng nhập.
- Giữ ranh giới giữa **CSRF token** và **session identifier**: hai giá trị có thể được thay đổi theo những cơ chế khác nhau.

Với trang server-rendered, GET trang sau khi login có thể render một token mới ngay khi cần. Với SPA, **token đang lưu ở memory hoặc cookie có thể trở nên lỗi thời**.

### 7.3. Khi đăng xuất

Khi logout thành công, ứng dụng xóa/trả về trạng thái không đăng nhập theo cấu hình. Các thành phần như `CsrfLogoutHandler` ở Servlet tham gia xóa token CSRF đã lưu.

Client không nên tiếp tục sử dụng token trước logout như thể đang ở cùng một phiên xác thực. Nếu ứng dụng sau logout vẫn cho phép hiển thị form login, nó cần đảm bảo **token mới phù hợp** được phát cho request login tiếp theo.

### 7.4. Token được tải/sinh theo yêu cầu

Spring Security Servlet hiện đại có cơ chế **deferred CSRF token**, nghĩa là token không nhất thiết được tải hoặc tạo ở mọi GET. Nó thường được cần đến khi render một form hoặc kiểm tra một request unsafe.

Hệ quả với SPA:

1. SPA có token `T0` trước đăng nhập.
2. POST login kèm `T0` thành công.
3. Cơ chế authentication xóa token cũ.
4. SPA muốn gửi ngay POST nghiệp vụ nhưng vẫn giữ `T0`.
5. POST có thể trả `403` vì `T0` không còn hợp lệ.

**Cách xử lý:** client nhận/khởi tạo token mới sau login, rồi mới gửi unsafe request tiếp theo. Tương tự, sau logout hoặc khi chuyển ngữ cảnh phiên, client cần làm mới token khi thao tác tiếp theo đòi CSRF.

Không xử lý bằng cách vô hiệu hóa CSRF trên các endpoint hậu đăng nhập.

### 7.5. Bảng vòng đời

| Thời điểm | Phiên/xác thực | CSRF token | Hành động của UI |
|---|---|---|---|
| Trước login, mở trang login | Chưa xác thực; có thể có anonymous session | Cấp token cho form khi cần | Render hidden field/header đúng |
| Gửi POST login | Chưa xác thực trước request | Phải gửi token hợp lệ | Gửi credentials **và** token |
| Login thành công | Ngữ cảnh xác thực mới | Token cũ có thể bị xóa/rotate | Lấy token mới trước unsafe request tiếp |
| Đã login | Session xác thực hợp lệ | Token theo session/ngữ cảnh hiện hành | Gửi token với POST/PUT/PATCH/DELETE |
| Gửi POST logout | Phiên xác thực đang hoạt động | Gửi token hiện hành | Submit form/header có token |
| Logout thành công | Xóa ngữ cảnh xác thực; hủy session tùy stack/cấu hình | Token cũ bị xóa/vô hiệu theo policy | Xóa trạng thái UI, khi cần tạo form login với token mới |
| Phiên timeout | Phiên/token cũ hết hiệu lực | Token trên form cũ có thể sai | Thông báo và tải lại form/token |

## 8. Login/logout bằng SPA hoặc ứng dụng dùng JSON

### 8.1. Dùng header CSRF thay hidden field

Với SPA, client có thể gửi token qua header:

~~~javascript
// Hàm minh họa: token và headerName phải được cấp từ ứng dụng.
async function submitLogin(username, password, token, headerName) {
  const data = new URLSearchParams({ username, password });

  const response = await fetch("/login", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      [headerName]: token,
      "Content-Type": "application/x-www-form-urlencoded"
    },
    body: data,
    redirect: "manual"
  });

  return response;
}
~~~

Form login chuẩn của Spring Security thường nhận `application/x-www-form-urlencoded` với các trường `username` và `password`; **không mặc nhiên nhận JSON**. Nếu backend định nghĩa endpoint JSON login riêng, cần dùng authentication filter/handler phù hợp và giữ CSRF nếu có credential trình duyệt tự gửi.

`redirect: "manual"` trong ví dụ chỉ minh họa việc client tự quyết định xử lý kết quả điều hướng. Trong browser thật, response redirect có thể được biểu diễn theo cơ chế opaque redirect và không dễ đọc `Location`; ứng dụng SPA cần thiết kế hành vi điều hướng/nhận kết quả rõ ràng. Với form login truyền thống, để browser tự xử lý redirect thường đơn giản hơn.

### 8.2. POST logout qua fetch

~~~javascript
async function submitLogout(token, headerName) {
  const response = await fetch("/logout", {
    method: "POST",
    credentials: "same-origin",
    headers: { [headerName]: token }
  });

  if (!response.ok) {
    throw new Error("Logout chưa hoàn thành");
  }

  // Ứng dụng cần cập nhật UI và trạng thái client theo kết quả thực tế.
  window.location.assign("/login?logout");
}
~~~

Đoạn này chỉ hợp với frontend và backend cùng origin, và token đã được lấy hợp lệ. `fetch` có thể tự theo redirect logout; kiểm tra `response.ok`/URL và cách xử lý giao diện phải phù hợp với ứng dụng. Với các API logout trả `204`, handler và cách điều hướng có thể khác.

Đừng chỉ xóa một biến `accessToken` ở JavaScript rồi coi là đã logout khỏi cookie session của server; client-side state và server-side session/token revocation là các bước khác nhau.

### 8.3. CookieCsrfTokenRepository và token raw sau login

Ứng dụng có thể dùng `CookieCsrfTokenRepository` (Servlet) hoặc `CookieServerCsrfTokenRepository` (Reactive) cho SPA đọc token từ cookie và gửi qua header. Khi đó cần lưu ý:

- Cookie CSRF đọc được từ JavaScript **khác** cookie xác thực nên đặt `HttpOnly`.
- Cookie CSRF được đọc là **raw token**; handler trong một số cấu hình Spring Security có thể dùng **XOR/masked token** khi render HTML. Cần request handler phù hợp cho header raw hoặc form masked.
- Sau xác thực/đăng xuất, cookie chứa token cũ có thể bị xóa. Với deferred token, **phải có bước cấp lại** để request tiếp theo có token hợp lệ.
- `CookieCsrfTokenRepository` đơn thuần không tự triển khai **signed double-submit HMAC gắn phiên**. Nếu mô hình đe dọa cần giải pháp đó, phải thiết kế và kiểm chứng riêng.

Các công cụ như browser DevTools giúp xác nhận token có thực sự xuất hiện trong header trước khi POST và response nào đã xóa hoặc cấp cookie mới.

## 9. Vì sao không nên tắt CSRF cho /login và /logout?

Khi gặp `403` trong login/logout, một giải pháp dễ làm nhưng sai mô hình thường là:

~~~java
// Ví dụ cấu hình nguy hiểm nếu dùng để "sửa" login/logout 403:
http.csrf(csrf -> csrf
    .ignoringRequestMatchers("/login", "/logout")
);
~~~

Hoặc tắt toàn bộ:

~~~java
// Không dùng làm giải pháp mặc định cho web dựa trên cookie/session:
http.csrf(csrf -> csrf.disable());
~~~

**Hậu quả:** POST login không còn lớp kiểm soát login CSRF; POST logout có thể bị kích hoạt mà không có token. Nếu cùng lúc matcher logout được mở cho GET, một điều hướng có thể trực tiếp logout.

Thay vì loại bỏ bảo vệ, hãy xác định nguyên nhân:

- Trang login tùy biến đã render hidden token chưa?
- Form có submit đến đúng `loginProcessingUrl` và security chain tương ứng không?
- SPA gửi header đúng tên/token chưa, đã lấy token mới sau login/logout chưa?
- Session cookie có đúng host/path/protocol và còn hiệu lực không?
- Request bị chặn bởi CSRF hay bởi authentication/authorization/CORS?
- Ứng dụng có nhiều `SecurityFilterChain` hoặc `SecurityWebFilterChain` với matcher chồng lấn không?

Với API **thực sự chỉ nhận bearer token do client chủ động gắn vào `Authorization`**, không dùng cookie/credential browser tự gửi, có thể có quyết định CSRF khác cho **phạm vi API riêng biệt**. Điều đó không phải lý do miễn CSRF cho form login/logout của ứng dụng session.

## 10. Cần dọn những gì khi logout?

Bảo vệ CSRF cho POST logout chỉ giải quyết **request có hợp lệ hay không**. Khi request hợp lệ, còn phải xử lý đầy đủ trạng thái xác thực.

| Loại trạng thái | Điều thường cần thực hiện | Lưu ý |
|---|---|---|
| `SecurityContext` | Xóa ngữ cảnh xác thực ở request/kho lưu phù hợp | Không chỉ chuyển hướng UI |
| `HttpSession` Servlet | Thường vô hiệu hóa phiên trong logout handler mặc định | Có thể tùy chỉnh; cần test phiên thật |
| `WebSession` Reactive | Có thể cần cấu hình thêm handler để vô hiệu hóa toàn bộ WebSession | Không mặc định áp hành vi Servlet cho WebFlux |
| Remember-me cookie/token | Dọn theo cơ chế remember-me đã cấu hình | Không quên đường đăng nhập tự động |
| CSRF token | Xóa/vô hiệu token thuộc ngữ cảnh cũ | Phát lại token mới khi cần form/login |
| Access token/refresh token | Thu hồi hoặc để hết hạn theo chính sách token riêng | Logout web không tự thu hồi mọi token ở các thiết bị |
| Session tại Identity Provider | Phải dùng luồng logout phối hợp nếu ứng dụng yêu cầu single sign-out | Local logout không đồng nghĩa SSO logout |
| UI/browser cache | Cập nhật trạng thái user, dữ liệu cache, điều hướng | Không coi đây là thay thế server logout |

**Trường hợp OAuth2/OIDC:** Tham số `state` và PKCE bảo vệ luồng đăng nhập qua chuyển hướng/authorization code; chúng **không thay thế** CSRF token cho các POST nghiệp vụ của phiên ứng dụng. OAuth2 login callback có thể là GET theo giao thức và cần bảo vệ bằng state/nonce và cơ chế phù hợp với luồng đó, không phải cứ GET là phải nhét `_csrf`.

Logout tại ứng dụng (RP/local logout), logout tại Identity Provider và thu hồi token có thể là **ba hoạt động riêng**. Kiểm tra yêu cầu dự án và các endpoint được áp dụng tương ứng; không giả định `POST /logout` đã thu hồi mọi phiên SSO hoặc refresh token.

## 11. Kiểm thử login/logout với Spring Security Servlet

### 11.1. Ma trận hành vi kỳ vọng

| Tình huống | CSRF token | Kỳ vọng |
|---|---|---|
| `POST /login` với credentials đúng, token thiếu | Thiếu | Bị từ chối trước bước login, thường `403` |
| `POST /login` với credentials đúng, token sai | Sai | Bị từ chối |
| `POST /login` với credentials sai, token đúng | Hợp lệ | Qua bước CSRF nhưng thất bại xác thực (ví dụ redirect `/login?error`) |
| `POST /login` với credentials đúng, token đúng | Hợp lệ | Đăng nhập thành công theo cấu hình |
| `GET /logout` trên cấu hình mặc định có CSRF | Không yêu cầu token cho GET | Hiển thị bước xác nhận, **không logout trực tiếp** |
| `POST /logout` của người đã login, token thiếu | Thiếu | Bị từ chối, session còn hợp lệ |
| `POST /logout` của người đã login, token đúng | Hợp lệ | Đăng xuất, dọn trạng thái và trả response theo cấu hình |
| `POST /logout` dùng token từ phiên khác | Không khớp phiên | Bị từ chối nếu repository token gắn theo phiên |
| Form mở trước khi phiên hết hạn | Token cũ | Phải xử lý hết hạn phiên, không thực hiện thao tác dưới session cũ |

Bảng giả định bảo vệ CSRF đang bật và các endpoint thực sự chạy qua filter chain tiêu chuẩn. Response cụ thể phụ thuộc authentication entry point, success/failure handler hoặc cấu hình ứng dụng.

### 11.2. MockMvc: kiểm tra token thiếu/sai trước khi login

Ví dụ dùng `spring-security-test`, `MockMvc` được cấu hình dùng security filter chain. `POST /login` do form login xử lý; với credentials cố ý sai, một token đúng sẽ cho phép request tới bước **xác thực thất bại**, thay vì bị chặn ở CSRF:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LoginCsrfServletTests {

    @Autowired MockMvc mvc;

    @Test
    void loginWithoutCsrfTokenIsForbidden() throws Exception {
        mvc.perform(post("/login")
                .param("username", "not-a-real-user")
                .param("password", "incorrect-password"))
            .andExpect(status().isForbidden());
    }

    @Test
    void loginWithInvalidCsrfTokenIsForbidden() throws Exception {
        mvc.perform(post("/login")
                .with(csrf().useInvalidToken())
                .param("username", "not-a-real-user")
                .param("password", "incorrect-password"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfTokenReachesAuthenticationFailure() throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "not-a-real-user")
                .param("password", "incorrect-password"))
            .andExpect(status().is3xxRedirection());
    }
}
~~~

Test cuối dựa trên giả định form login chuẩn **chuyển hướng khi credentials sai**. Nó chứng minh POST đã qua CSRF để đến bước xác thực, **không chứng minh login thành công**. Test login thành công cần user test hợp lệ và xác minh `SecurityContext`/session sau đăng nhập.

### 11.3. MockMvc: xác minh POST logout

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class LogoutCsrfServletTests {

    @Autowired MockMvc mvc;

    @Test
    void logoutWithoutCsrfTokenIsForbidden() throws Exception {
        mvc.perform(post("/logout").with(user("alice")))
            .andExpect(status().isForbidden());
    }

    @Test
    void logoutWithCsrfTokenPassesCsrfCheck() throws Exception {
        mvc.perform(post("/logout")
                .with(user("alice"))
                .with(csrf()))
            .andExpect(status().is3xxRedirection());
    }
}
~~~

`with(user("alice"))` mô phỏng authentication để kiểm tra filter. Để chứng minh logout **thật sự vô hiệu hóa session**, hãy bổ sung test tích hợp: login thật, lưu cookie/session trước logout, POST logout với token thật, rồi truy cập endpoint bảo vệ bằng cookie cũ và xác nhận không còn phiên xác thực.

## 12. Kiểm thử Reactive/WebFlux bằng WebTestClient

Dùng `springSecurity()` để WebTestClient đi qua security web filter chain. Ví dụ với form login/logout và xử lý redirect mặc định:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.csrf;

@SpringBootTest
class LoginLogoutCsrfReactiveTests {

    @Autowired ApplicationContext context;

    private WebTestClient client() {
        return WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void loginWithoutCsrfTokenIsForbidden() {
        client().post().uri("/login")
            .body(BodyInserters.fromFormData(
                "username", "not-a-real-user")
                .with("password", "incorrect-password"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void loginWithCsrfTokenReachesAuthFlow() {
        client().mutateWith(csrf())
            .post().uri("/login")
            .body(BodyInserters.fromFormData(
                "username", "not-a-real-user")
                .with("password", "incorrect-password"))
            .exchange()
            .expectStatus().is3xxRedirection();
    }

    @Test
    void logoutWithoutCsrfTokenIsForbidden() {
        client().mutateWith(mockUser("alice"))
            .post().uri("/logout")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void logoutWithCsrfTokenReachesLogoutFilter() {
        client().mutateWith(mockUser("alice"))
            .mutateWith(csrf())
            .post().uri("/logout")
            .exchange()
            .expectStatus().is3xxRedirection();
    }
}
~~~

Ví dụ giả định Spring Security WebFlux sử dụng các endpoint form/login/logout chuẩn và các luồng success/failure trả redirect. `mutateWith(csrf())` kiểm tra bước CSRF trong môi trường test; nó **không thay** test browser thật về cookie, giá trị token lấy qua GET và kết quả hủy WebSession.

Để kiểm chứng WebSession bị vô hiệu hóa sau logout, dùng một luồng tích hợp thật với cookie từ POST login rồi xác nhận POST logout và request có cookie cũ không còn được xem là đã xác thực. Nếu yêu cầu hủy WebSession, bảo đảm đã cấu hình handler tương ứng.

## 13. Chẩn đoán những lỗi thường gặp

| Triệu chứng | Nguyên nhân cần kiểm tra | Hướng xử lý |
|---|---|---|
| Trang `GET /login` hoạt động nhưng POST trả `403` | Form không có hidden CSRF field hoặc token sai | Kiểm tra HTML cuối, request body, nơi lưu expected token |
| Trang login tùy biến submit nhưng không vào luồng xác thực | `loginProcessingUrl` khác `action` hoặc security chain khác nhận request | Đồng bộ URL và matcher, không tạo POST controller trùng filter |
| Login hợp lệ nhưng POST ngay sau đó `403` | Token cũ bị xóa sau xác thực, deferred token chưa cấp lại | Fetch/render token mới sau login |
| Logout bằng link GET không xảy ra | Cấu hình mặc định yêu cầu POST có CSRF; GET chỉ xác nhận | Dùng form POST; không mở GET logout để “sửa” |
| GET /logout làm logout ngay | CSRF bị tắt hoặc matcher logout đã mở GET | Rà soát CSRF và logout matcher, đưa về POST có token |
| POST logout thiếu token, user vẫn đăng nhập | Bộ lọc đã từ chối trước khi logout | Cấp token hợp lệ cho form/header |
| POST logout trả redirect nhưng cookie cũ vẫn truy cập được | Dọn session/security context chưa đủ, có cơ chế remember-me hoặc WebSession riêng | Kiểm tra handler, cơ chế xác thực thực tế và test session thật |
| WebFlux logout rồi vẫn thấy WebSession tồn tại | Default logout có thể không vô hiệu hóa toàn bộ WebSession | Cân nhắc `WebSessionServerLogoutHandler` |
| SPA gọi /logout trả CORS/preflight error | Frontend/API khác origin, header/credentials/CORS chưa phù hợp | Phân biệt CORS với CSRF, sửa policy hợp lệ |
| Sau logout form login mới tiếp tục `403` | Client giữ token CSRF cũ, cookie token bị xóa | Nhận token mới sau logout |
| Test với `csrf()` pass nhưng browser thật fail | Test helper không mô phỏng đầy đủ cookie/DOM/redirect | Thêm test tích hợp lấy token từ GET và dùng cookie thật |
| Nhiều node xảy ra lỗi ngẫu nhiên | Session store hoặc khóa/cookie không nhất quán | Kiểm tra replication/affinity, proxy và cookie scope |

**Quan sát có kiểm soát:** Khi phân tích `403`, xác định nó xảy ra ở CSRF filter hay authorization. Không log giá trị thực của session ID, CSRF token hoặc access token. Có thể ghi nhận **đường dẫn, phương thức, token có/không, tên header/field, chain áp dụng và loại lỗi**.

Một lỗi `401`, một redirect tới trang login hoặc một lỗi CORS có thể xuất phát từ nguyên nhân khác; không coi tất cả là CSRF. Với Servlet, một số dấu hiệu liên quan là `MissingCsrfTokenException`/`InvalidCsrfTokenException`; với Reactive cần kiểm tra `CsrfWebFilter` và request handler/configuration.

## 14. Tình huống tự kiểm tra

**Tình huống A — chưa đăng nhập thì không cần CSRF?** Ứng dụng bỏ CSRF ở `POST /login` vì user chưa có session xác thực.

**Giải thích:** Không phù hợp với form login trên browser. Login CSRF có thể ép user vào tài khoản attacker; trang GET login nên cấp token ngay cả trước khi user được xác thực.

**Tình huống B — GET logout tiện hơn.** Nhóm chuyển `GET /logout` thành thao tác logout trực tiếp để dùng thẻ link trong menu.

**Giải thích:** GET là phương thức an toàn, có thể được kích hoạt qua điều hướng/đường dẫn. Thực hiện logout qua GET mở đường logout CSRF; nên dùng POST có token.

**Tình huống C — CSRF token đúng nhưng mật khẩu sai.** POST login chứa `_csrf` hợp lệ và sai password.

**Giải thích:** Token chỉ giúp vượt bước kiểm tra CSRF. Bước authentication vẫn phải từ chối; không được coi token CSRF là bằng chứng đăng nhập.

**Tình huống D — SPA login xong POST đầu tiên thất bại.** Login có token hợp lệ, sau đó SPA tiếp tục dùng token trước login.

**Giải thích:** CSRF token cũ có thể bị xóa khi xác thực thành công. SPA phải nhận token mới theo cách repository/handler đang dùng, đặc biệt với deferred token.

**Tình huống E — logout WebFlux không vô hiệu hóa WebSession.** Ứng dụng đã gọi POST logout thành công nhưng vẫn có dữ liệu WebSession còn sống.

**Giải thích:** Logout reactive mặc định có thể dọn security context/CSRF token mà không hủy toàn bộ WebSession. Nếu chính sách yêu cầu vô hiệu hóa WebSession, cấu hình và kiểm thử thêm handler phù hợp.

**Tình huống F — logout khỏi ứng dụng có nghĩa đã logout khỏi Identity Provider?** Người dùng đã POST `/logout` của ứng dụng, nhưng đăng nhập lại qua SSO không hỏi mật khẩu.

**Giải thích:** Local logout và phiên SSO tại Identity Provider là hai ngữ cảnh khác nhau. Cần luồng RP-initiated logout/single logout phù hợp nếu sản phẩm yêu cầu, bên cạnh bảo vệ CSRF của các endpoint liên quan.

## Tổng kết

**Đăng nhập và đăng xuất đều cần được xem là những yêu cầu thay đổi trạng thái bảo mật.** Login CSRF có thể khiến nạn nhân sử dụng tài khoản attacker; logout CSRF có thể ép nạn nhân rời phiên hoặc gây gián đoạn. Vì vậy form login/logout trong ứng dụng dựa vào trình duyệt nên gửi **POST có CSRF token hợp lệ**, kể cả khi người dùng chưa xác thực trước login.

Spring Security **Servlet** sử dụng `CsrfFilter`, cơ chế form login/logout, session và các handler liên quan; Spring Security **Reactive/WebFlux** dùng `CsrfWebFilter`, `LogoutWebFilter` và WebSession/security context tương ứng. Trong cấu hình chuẩn có CSRF, `GET /logout` là bước xác nhận thay vì hành động đăng xuất, còn `POST /logout` là thao tác cần token. Sau login/logout, token cũ có thể không còn hợp lệ và SPA cần lấy token mới. Kiểm thử thực tế phải bao gồm tính hợp lệ của request, trạng thái xác thực sau logout, tính toàn vẹn phiên và những tương tác với CORS, cookie, SSO và các lớp HTTP protection khác.

## Tham khảo tài liệu Spring Security

- [CSRF protection — Servlet](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html): logging in/out, token, form, SPA, deferred token.
- [Handling Logouts — Servlet](https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html): POST logout, GET confirmation, logout handlers.
- [CSRF protection — WebFlux](https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html): bảo vệ login/logout trong reactive.
- [Logout — Reactive](https://docs.spring.io/spring-security/reference/reactive/authentication/logout.html): logout filters, security context, WebSession logout handler.
