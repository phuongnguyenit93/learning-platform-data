# CSRF khi trình duyệt tự gửi thông tin xác thực HTTP Basic

> Phạm vi: **Spring Security trên Servlet stack** (Spring MVC, `SecurityFilterChain`, `HttpSecurity`), HTTP Basic trong trình duyệt, Java 17+, Spring Boot 3.x và Spring Security 6.x. Trọng tâm là **rủi ro CSRF khi browser tự gắn thông tin xác thực**, không phải một hướng dẫn tổng quan về mọi kiểu authentication.

## 1. Ý chính: HTTP Basic không tự động loại bỏ CSRF

**Cross-Site Request Forgery (CSRF)** là tình huống website của kẻ tấn công khiến trình duyệt của nạn nhân gửi một yêu cầu tới website đích, trong khi website đích có thể coi yêu cầu đó là do nạn nhân đã xác thực thực hiện. Mấu chốt không chỉ là có cookie hay không, mà là **trình duyệt có tự mang theo credential mà website đích tin tưởng hay không**.

Với **HTTP Basic authentication**, trình duyệt có thể lưu/cache cặp thông tin đăng nhập sau khi người dùng đã nhập credential trước đó cho một origin và phạm vi bảo vệ (protection space). Trong các yêu cầu phù hợp tiếp theo, browser có thể **tự gửi header `Authorization: Basic ...`** mà JavaScript của trang độc hại không cần biết username/password. Hành vi cụ thể phụ thuộc browser, authentication cache, phạm vi URL và chính sách của user agent; **không được giả định mọi browser sẽ gửi Basic preemptively trong mọi tình huống**.

Tuy vậy, nếu browser **có khả năng tự đính kèm Basic credentials cho một yêu cầu cross-site**, website đích có thể phải đối mặt với CSRF tương tự ứng dụng dựa vào session cookie. Đó là lý do tài liệu và mặc định của Spring Security không xem "dùng HTTP Basic" là đủ để tuyên bố mọi POST đều an toàn khỏi CSRF.

**Quy tắc nhớ nhanh:**

- **Browser tự mang credential** (cookie session, HTTP Basic được cache, hoặc cơ chế ambient authority tương đương) → phải đánh giá CSRF nghiêm túc.
- **Client chuyên dụng tự gắn credential theo chủ đích trên từng request**, ví dụ một dịch vụ gọi API với header `Authorization` mà website độc hại không thể làm trình duyệt tự gắn → bề mặt CSRF có thể khác; chỉ miễn trừ khi **đã chứng minh** API không chấp nhận credential tự động được browser gửi.
- **Stateless không đồng nghĩa CSRF-safe**. CSRF nói về **cách browser tạo và xác thực request**, không đòi hỏi server phải dùng session cho đăng nhập.
- **CORS không phải cơ chế chống CSRF**. CORS chủ yếu kiểm soát quyền JavaScript ở origin khác đọc response và các điều kiện cross-origin fetch; một HTML form cross-site có thể vẫn gửi request, dù JavaScript không đọc được response.
- **SameSite cookie không giải quyết riêng HTTP Basic**: thuộc tính SameSite áp dụng cho cookie, không phải một chính sách vô hiệu header Authorization được browser tự gửi.

## 2. HTTP Basic chạy như thế nào trong Servlet?

HTTP Basic dùng cơ chế HTTP authentication challenge/response. Với một request thiếu thông tin xác thực cho tài nguyên được bảo vệ, server có thể trả:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Basic realm="example"
```

Trình duyệt có thể hiển thị hộp thoại nhập username/password, ghi nhớ chúng cho phạm vi phù hợp rồi gửi:

```http
GET /profile HTTP/1.1
Host: app.example
Authorization: Basic <base64-of-username-colon-password>
```

Chuỗi Base64 **chỉ là encoding, không phải encryption hoặc hashing**. Khi truyền HTTP Basic qua mạng, **HTTPS/TLS là bắt buộc trong triển khai thật** để bảo vệ credential. Không log raw Authorization header, không ghi Basic string vào URL, JavaScript telemetry hoặc file cấu hình công khai.

Trong Spring Security Servlet, luồng khái quát là:

```text
Browser HTTP request
        |
        v
Servlet FilterChainProxy chọn SecurityFilterChain
        |
        +--> SecurityContext và các filter liên quan
        |
        +--> CsrfFilter (nếu request thuộc phạm vi bảo vệ)
        |      |
        |      +--> POST/PUT/PATCH/DELETE thiếu hoặc sai CSRF token
        |                -> 403, có thể dừng trước xác thực Basic
        |
        +--> BasicAuthenticationFilter (khi chain bật httpBasic)
        |      |
        |      +--> trích Basic Authorization credentials nếu có
        |      +--> chuyển token chưa xác thực tới AuthenticationManager
        |      +--> AuthenticationProvider xác minh credential
        |      +--> lưu SecurityContext theo chính sách
        |
        +--> AuthorizationFilter
        |      |
        |      +--> rule authenticated()/hasRole(...)/...
        |
        v
Spring MVC controller (nếu được phép)
```

Đây là **sơ đồ ý niệm**, không phải danh sách tất cả các filter hoặc lời cam kết thứ tự bất biến trong mọi configuration. Spring Security có nhiều extension points và có thể chạy nhiều `SecurityFilterChain` theo matcher. Với CSRF được bật, một request POST thiếu token có thể bị từ chối **ngay cả khi** nó có HTTP Basic credential đúng.

Đặc biệt: `http.httpBasic(...)` cấu hình cách xác thực bằng Basic. Nó **không ngầm đồng nghĩa** `http.csrf(...disable...)`; hai quyết định khác nhau.

## 3. Cơ chế tấn công: browser làm trung gian mang danh tính

Giả sử ứng dụng `https://accounts.example` có:

- `GET /settings`: xem cấu hình.
- `POST /settings/email`: thay đổi địa chỉ email liên hệ của người dùng.
- Security chain chấp nhận HTTP Basic.
- Endpoint POST chỉ kiểm tra `authenticated()`, không có kiểm tra CSRF hoặc cơ chế ràng buộc nguồn gửi tương đương.

Người dùng đã xác thực với ứng dụng đích và browser còn lưu Basic credentials. Sau đó nạn nhân mở một trang `https://untrusted.example` do kẻ tấn công kiểm soát. Trang này có thể chứa một HTML form gửi POST tới website đích:

```html
<!-- Minh họa cơ chế gửi yêu cầu; địa chỉ và dữ liệu đều hư cấu. -->
<form action="https://accounts.example/settings/email" method="post">
  <input type="hidden" name="email" value="changed@example.invalid">
  <button type="submit">Tiếp tục</button>
</form>
```

Một trang cross-origin **có thể gửi HTML form** theo các giới hạn bình thường của browser; không bắt buộc có đặc quyền CORS đọc response để gây ra hành động thay đổi trạng thái. Trang xấu không được tự ý đọc Basic password của nạn nhân và không nhất thiết được tự đặt một `Authorization` header tùy chỉnh. Rủi ro xuất hiện khi **browser tự dùng lại Basic credentials đã cache cho request gửi tới origin đích**.

```text
        Người dùng đã đăng nhập Basic với accounts.example
                                |
                   Browser có thể cache credentials
                                |
                        Mở untrusted.example
                                |
                  Trang xấu tạo HTML form POST
                                |
                                v
Browser gửi request tới accounts.example
    [có thể tự đính kèm Authorization: Basic ...]
                                |
                                v
                 Backend thấy một principal hợp lệ
                                |
                    Nếu chỉ check authenticated()
                                |
                    Thao tác có thể bị thực hiện
```

Một **CSRF token** hợp lệ, không thể dự đoán và được ràng buộc với ngữ cảnh tin cậy mà website đích kiểm soát, giúp phân biệt POST phát sinh từ workflow hợp lệ với POST do trang ngoài tự phát động. Đây là một biện pháp phổ biến; thiết kế sản xuất còn cần kiểm soát Origin/Referer hoặc Fetch Metadata ở mức phù hợp và tránh XSS.

### Một ví dụ phản trực giác

Có người cho rằng:

> "Website tôi không dùng session cookie; mỗi request cần Basic header. CSRF chỉ xảy ra với cookie nên không cần CSRF token."

Lập luận ấy **thiếu điều kiện**. Câu đúng hơn là: "Nếu một attacker-controlled web origin không thể khiến browser tự mang theo credential mà API chấp nhận và không có dạng ambient credential nào khác, nguy cơ CSRF của đường gọi đó giảm đáng kể." Với **browser-cached Basic**, điều kiện này **có thể không đúng**.

## 4. Điều kiện, giới hạn và những điều không nên khẳng định tuyệt đối

Khả năng khai thác phụ thuộc vào nhiều yếu tố:

1. **Credential đã có trong browser chưa?** Browser có thể chưa biết thông tin đăng nhập hoặc đã quên cache sau khi đóng, logout hoặc đổi realm.
2. **Phạm vi HTTP authentication**: origin, scheme, port, realm và đường dẫn/protection space có thể ảnh hưởng việc browser dùng lại Basic credentials.
3. **Browser có tự gửi Basic header với yêu cầu cross-site đó không?** Các user agent có hành vi và chính sách bảo vệ khác nhau. Có trường hợp không đính kèm trước, có trường hợp yêu cầu lại challenge, và có những rào cản đối với third-party contexts.
4. **Request có thể phát từ HTML form không?** Các action chỉ cần một POST form thông thường có bề mặt khác action bắt buộc JSON + custom headers.
5. **Server có kiểm tra CSRF token hoặc ràng buộc nguồn gửi không?** Nếu kiểm tra đúng, credentials đúng vẫn không đủ để thực hiện thao tác.
6. **Action có hậu quả thật không?** Một GET chỉ đọc dữ liệu có độ nguy hiểm CSRF thấp hơn một POST thay đổi email, password, địa chỉ thanh toán hoặc quyền truy cập. Tuy nhiên GET **không được** dùng cho thao tác thay đổi trạng thái.

Không kết luận "mọi browser đều sẽ tự gửi Basic credential trong mọi cross-site POST"; cũng không kết luận ngược lại rằng browser hiện đại đã mặc nhiên loại trừ rủi ro. **Thiết kế chống CSRF không nên dựa vào may rủi hành vi cache authentication của một browser.**

## 5. CORS, SOP, preflight và SameSite không phải một thứ

### 5.1. Same-Origin Policy ngăn đọc response, không luôn ngăn gửi request

Same-Origin Policy (SOP) thường hạn chế script từ `untrusted.example` đọc nội dung response từ `accounts.example`. Nhưng trình duyệt hỗ trợ các thao tác cross-origin có từ lâu: submit form, điều hướng, tải hình ảnh và một số request khác. Vì CSRF **chỉ cần server thực hiện hành động**, attacker không nhất thiết cần thấy response.

Đặc biệt, một HTML form có `method="post"` và `application/x-www-form-urlencoded` có thể được gửi cross-site mà không cần CORS preflight như một `fetch()` dùng custom header. Do đó đặt header `Access-Control-Allow-Origin` chặt chẽ **không đủ** để bảo đảm một form POST không tới server.

### 5.2. Cross-origin fetch và preflight

Một `fetch` cross-origin gửi `Authorization` hoặc custom headers thường phải tuân theo quy tắc CORS/preflight tương ứng; JavaScript của trang xấu cũng **không đọc được** credential đã lưu ở origin khác chỉ vì biết URL. Nhưng đây **không phải** bảo đảm tổng quát cho HTML form hoặc browser ambient authentication.

Nếu API yêu cầu custom `X-CSRF-TOKEN` header và thực hiện CSRF token validation phía server, attacker website khác sẽ gặp thêm rào cản; tuy nhiên sức mạnh chính vẫn đến từ việc **token hợp lệ không được attacker nắm giữ**, không phải chỉ từ tên header. Nếu server mở CORS bừa bãi và cho phép các origin không tin cậy truy cập credentialed responses hoặc token endpoint, chính sách có thể bị phá vỡ.

### 5.3. SameSite không phải một thuộc tính của Basic Authorization

`SameSite=Lax`/`Strict` là thuộc tính của **cookie**. Chúng có thể giảm khả năng cookie được gửi cross-site, nhưng **không trực tiếp quy định** việc browser tự gửi `Authorization: Basic ...`. Vì vậy ứng dụng "không có cookie xác thực" không thể dựa vào SameSite như lý do duy nhất để tắt CSRF.

Nếu ứng dụng đồng thời dùng Basic và session cookie, hãy phân tích **cả hai** cơ chế. Việc dùng `SessionCreationPolicy.STATELESS` cũng không tự chứng minh không có ambient Basic credentials.

### 5.4. Origin, Referer và Fetch Metadata

Các request browser có thể mang `Origin`, `Referer` và các Fetch Metadata headers như `Sec-Fetch-Site`. Chúng là tín hiệu hữu ích để từ chối unsafe cross-site requests trong nhiều kiến trúc, nhưng cần tính tới browser hỗ trợ, redirect, proxy, privacy policy và các luồng hợp lệ. **Đừng chỉ kiểm tra rằng một header có tồn tại** rồi tin client ngoài browser không thể giả nó. Khi dùng chính sách này, triển khai validation ở server và viết test cho header thiếu, origin không hợp lệ, cross-origin/cross-site và các trường hợp hợp lệ.

## 6. Spring Security Servlet bảo vệ CSRF ra sao?

Trong cấu hình Spring Security Servlet thông dụng, `CsrfFilter` được bật mặc định. Cấu hình Java:

```java
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated())
        .httpBasic(Customizer.withDefaults())
        .build();
}
```

Đoạn trên là **fragment cấu hình**, cần import/`@Configuration`/`@Bean` phù hợp. Không có `csrf(...disable...)`: cơ chế CSRF vẫn tồn tại.

Quy tắc bảo vệ mặc định thường áp dụng với **mọi method không thuộc danh sách safe** `GET`, `HEAD`, `TRACE`, `OPTIONS` (ví dụ `POST`, `PUT`, `PATCH`, `DELETE`). Việc một method được coi là safe trong bộ lọc **không làm GET thay đổi dữ liệu trở nên an toàn**. Backend phải thực sự giữ GET/HEAD là các thao tác không gây side effect nghiệp vụ.

Thành phần liên quan:

- **`CsrfFilter`**: chặn yêu cầu thuộc diện bảo vệ khi không có token hợp lệ.
- **`CsrfTokenRepository`**: cung cấp/lưu/tải expected CSRF token. Trong cấu hình web thông dụng có thể dùng `HttpSessionCsrfTokenRepository`.
- **`CsrfTokenRequestHandler`**: đưa token vào request và giải quyết token người dùng gửi lên; Spring Security 6 có cơ chế deferred token, masking/BREACH protection cho việc render.
- **`CsrfToken`**: chứa header name, parameter name và token để form/JavaScript thực hiện submit đúng contract.
- **`AccessDeniedHandler`**: xử lý phản hồi cho một số từ chối truy cập như missing/invalid CSRF token, thông thường status 403.

**Điểm rất dễ nhầm:** HTTP Basic authentication có thể hoàn toàn hợp lệ, nhưng POST thiếu CSRF token vẫn nhận **403**. Đây không phải chứng cứ password sai hay lỗi `DaoAuthenticationProvider`.

### Đường đi của hai request đối lập

```text
GET /form + Basic credential
    -> không phải unsafe method
    -> có thể hiển thị HTML form cùng CSRF token
    -> status 200 nếu user hợp lệ

POST /change + Basic credential
    -> unsafe method
    -> thiếu CSRF token
    -> CsrfFilter từ chối (thường 403)
    -> thay đổi trạng thái KHÔNG được thực hiện

POST /change + Basic credential + CSRF token hợp lệ
    -> qua CsrfFilter
    -> Basic credential được kiểm tra
    -> authorization authenticated()
    -> controller xử lý và trả 200
```

Nếu request không có Basic credential và thiếu CSRF token, request có thể bị chặn bởi CSRF **trước khi** HTTP Basic entry point trả 401. Không suy luận rằng "không có 401" nghĩa HTTP Basic đã bị tắt.

## 7. Khi nào có thể cân nhắc tắt hoặc bỏ qua CSRF?

Không có quy tắc tốt nào nói "tất cả API dùng Basic đều tắt CSRF". Cần lập bảng **đường nào có thể được browser gọi với credential tự động**:

| Loại client/cơ chế | Credential tới request ra sao? | Cách nghĩ về CSRF |
| --- | --- | --- |
| Browser dùng HTTP Basic và có cache credentials | Browser có thể tự gửi credential cho protected origin | **Giữ CSRF protection** cho unsafe operations |
| Browser dùng session cookie | Cookie thường được browser gửi tự động theo policy | **Giữ CSRF protection** theo browser threat model |
| SPA dùng cookie-based auth | Browser tự gửi cookie khi hợp lệ; JS gửi body/header | Cần CSRF token + cookie/Origin/Fetch Metadata policy |
| API machine-to-machine chỉ nhận bearer token do client tự gắn | Attacker website không mặc nhiên có token để tự gửi | Có thể thiết kế không dùng CSRF token, nếu thực sự không chấp nhận ambient credentials |
| CLI/mobile native client gửi `Authorization: Basic` theo chủ đích | Client code cung cấp header cho từng request | CSRF browser có thể không phải threat chính, nhưng vẫn cần TLS/credential hygiene |
| Cùng endpoint chấp nhận cả browser Basic và machine token | Browser vẫn có đường credential tự động | **Không loại trừ CSRF chỉ vì có một loại client không-browser** |
| Request state-changing qua GET | Không nên có | Sửa thiết kế HTTP, đừng phụ thuộc GET không bị CSRF filter kiểm tra |

**Trước khi disable:** kiểm tra cả reverse proxy, client browser, login challenges, session cookies, basic-auth caches và các endpoint có thể nhận credential mặc định. Một chứng minh thiếu chặt "đây là REST API stateless" **không đủ**.

### Chỉ loại trừ route thực sự không dùng browser credentials

Spring Security có khả năng tùy biến matcher để bỏ qua CSRF cho một số endpoint. Ví dụ cú pháp:

```java
.csrf(csrf -> csrf.ignoringRequestMatchers("/machine/**"))
```

Đây là **fragment** để đặt trong `HttpSecurity`, không phải lời khuyên bật cho mọi ứng dụng. Chỉ cân nhắc khi `/machine/**` được bảo vệ độc lập bằng cơ chế **không chấp nhận ambient browser credentials**, có threat model và test khẳng định. Nếu route vẫn chấp nhận Basic cached của browser, bỏ qua CSRF có thể tạo lỗ hổng. Với nhiều filter chains, matcher còn phải bao phủ đúng chain và HTTP method.

Tránh `.csrf(csrf -> csrf.disable())` trên toàn bộ web chain chỉ để `curl -X POST` tiện hơn. Test client có thể tự cấp CSRF token thay vì làm suy yếu sản phẩm.

## 8. Ví dụ Spring Boot 3.x / Java 17+: HTTP Basic cộng CSRF form token

Để quan sát rõ ràng, ta xây dựng một ứng dụng Servlet nhỏ có:

- `GET /form`: trả HTML form có **hidden CSRF token** tạo bởi Spring Security.
- `POST /change`: tăng một bộ đếm demo, tượng trưng cho một thao tác **thay đổi trạng thái**; không phải nghiệp vụ thanh toán.
- `GET /status`: xem bộ đếm.
- Tất cả URL yêu cầu Basic-authenticated user.
- **Giữ nguyên CSRF protection mặc định** để POST thiếu token bị chặn.

### 8.1. Dependencies

Trong dự án Spring Boot 3.x có Gradle plugin/dependency management, cần:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Tạo tệp `src/main/java/example/basiccsrf/BasicCsrfApplication.java`:

```java
package example.basiccsrf;

import java.util.concurrent.atomic.AtomicInteger;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class BasicCsrfApplication {
    public static void main(String[] args) {
        SpringApplication.run(BasicCsrfApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            // Không disable CSRF.
            .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService users(PasswordEncoder encoder) {
        UserDetails learner = User.withUsername("learner")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }
}

@RestController
class DemoController {

    private final AtomicInteger changes = new AtomicInteger();

    @GetMapping(value = "/form", produces = MediaType.TEXT_HTML_VALUE)
    String form(HttpServletRequest request) {
        // CsrfFilter cung cấp request attribute khi CSRF được bật.
        CsrfToken token =
            (CsrfToken) request.getAttribute(CsrfToken.class.getName());

        if (token == null) {
            throw new IllegalStateException("CSRF token is unavailable");
        }

        // Spring Security 6 có thể dùng masked token cho HTML form.
        return """
            <!doctype html>
            <html lang="en">
            <body>
              <h1>Safe change form</h1>
              <form action="/change" method="post">
                <input type="hidden" name="%s" value="%s">
                <button type="submit">Record a change</button>
              </form>
            </body>
            </html>
            """.formatted(token.getParameterName(), token.getToken());
    }

    @GetMapping(value = "/status",
                produces = MediaType.TEXT_PLAIN_VALUE)
    String status() {
        return "change-count=" + changes.get();
    }

    @PostMapping(value = "/change",
                 produces = MediaType.TEXT_PLAIN_VALUE)
    String change() {
        return "change-count=" + changes.incrementAndGet();
    }
}
```

**Vì sao đoạn code có thể biên dịch:** tệp Java chứa một public top-level class trùng tên `BasicCsrfApplication.java`, hai class package-private và các import sử dụng đúng namespace `jakarta.servlet` dành cho Spring Boot 3. `AtomicInteger` chỉ làm trạng thái demo trong JVM, không phải persistent database và không mang nghiệp vụ thật.

**Vì sao GET /form có token?** `CsrfFilter` công bố một `CsrfToken` dưới request attribute tên class hoặc tên parameter tùy request handler. Đọc `token.getToken()` giúp materialize token khi cơ chế deferred loading được dùng. Hidden form input lấy đúng `token.getParameterName()` (mặc định thường là `_csrf`) và giá trị từ request, không tự đoán token trong JavaScript.

Cấu hình mặc định của Spring Security 6 có thể dùng token đã được mask khi render (liên quan BREACH mitigation). Bạn nên sử dụng **giá trị token Spring Security công bố cho request**, không tự Base64/URL-encode một token cố định, không giả định raw token và masked token là một chuỗi giống nhau.

Khi người dùng vào `/form` trong browser lần đầu, server có thể trả 401 Basic challenge; sau khi nhập credential, browser hiển thị form. Khi người dùng submit, token đi kèm body và browser có thể đính kèm Basic Authorization đã cache. Spring Security đòi hỏi **cả trạng thái xác thực hợp lệ lẫn token hợp lệ** cho POST.

Đây là ví dụ demo **chỉ để học**. Production phải bật HTTPS, xem xét header/cookie policies, bảo vệ credentials và không lưu mật khẩu demo trong config thật.

### 8.2. Chạy demo

Trong Gradle project có wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell: `./gradlew.bat bootRun`.

Sau khi server chạy trên `http://localhost:8080`, mở browser:

```text
http://localhost:8080/form
```

Browser có thể hiện Basic login dialog. Nhập `learner` và `demo-pass`. Sau khi form hiện, nhấn **Record a change**. Request POST có hidden CSRF token hợp lệ và browser có thể tự gửi Basic credential của origin đó. Kết quả dự kiến là body `change-count=1` cho lần thay đổi đầu tiên.

Để xem trạng thái:

```text
http://localhost:8080/status
```

Có thể hiển thị `change-count=1` sau lần POST hợp lệ đầu tiên; bộ đếm tiếp tục tăng theo số lần POST thành công trong cùng tiến trình server. Đây là **kỳ vọng của mã nguồn**, không phải kết quả đã chạy trong bài viết.

### 8.3. Tại sao không thể dùng ngay curl -u để làm một POST hợp lệ?

`curl -u` giúp gửi Basic credentials, nhưng **không tự có một CSRF token hợp lệ và ngữ cảnh lưu token**. Vì vậy:

```bash
curl -i -u learner:demo-pass -X POST http://localhost:8080/change
```

**Kỳ vọng:** HTTP 403 do thiếu CSRF token, ngay cả khi Basic password đúng. POST bị từ chối trước khi controller tăng bộ đếm; không nên thấy `change-count` thay đổi.

Một client muốn POST hợp lệ phải lấy CSRF token từ một endpoint/form do server cung cấp, bảo toàn cookie hoặc phiên lưu expected token khi được dùng và gửi token lại đúng vị trí. Browser form của demo thực hiện điều này; trong automated tests, `spring-security-test` có helper `.with(csrf())`.

Với basic-auth demo này, request GET form có thể tạo HTTP session **để chứa CSRF token** dù authentication chính là Basic. Cần phân biệt *session chứa CSRF state* với *session dùng làm bằng chứng login*. Không suy luận "dùng Basic thì chắc chắn không có JSESSIONID".

## 9. MockMvc: chứng minh Basic auth đúng vẫn không qua được CSRF

Tạo `src/test/java/example/basiccsrf/BasicCsrfSecurityTest.java`:

```java
package example.basiccsrf;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.startsWith;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BasicCsrfSecurityTest {

    @Autowired
    MockMvc mvc;

    @Test
    void missingCredentialsForProtectedGetRequiresBasicAuth()
            throws Exception {
        mvc.perform(get("/status"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void authenticatedGetIsAllowedWithoutCsrfToken()
            throws Exception {
        mvc.perform(get("/status")
                .with(httpBasic("learner", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string(startsWith("change-count=")));
    }

    @Test
    void basicCredentialsDoNotBypassCsrfOnPost()
            throws Exception {
        mvc.perform(post("/change")
                .with(httpBasic("learner", "demo-pass")))
            .andExpect(status().isForbidden());
    }

    @Test
    void validCsrfAndBasicCredentialsAllowPost()
            throws Exception {
        mvc.perform(post("/change")
                .with(httpBasic("learner", "demo-pass"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string(startsWith("change-count=")));
    }

    @Test
    void invalidCsrfIsRejectedEvenWithCorrectPassword()
            throws Exception {
        mvc.perform(post("/change")
                .with(httpBasic("learner", "demo-pass"))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());
    }

    @Test
    void htmlFormRendersCsrfParameter()
            throws Exception {
        mvc.perform(get("/form")
                .with(httpBasic("learner", "demo-pass")))
            .andExpect(status().isOk())
            .andExpect(content().string(containsString("name=\"_csrf\"")));
    }

    @Test
    void crossSiteOriginLabelDoesNotReplaceTokenValidation()
            throws Exception {
        mvc.perform(post("/change")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .header("Origin", "https://untrusted.example")
                .with(httpBasic("learner", "demo-pass")))
            .andExpect(status().isForbidden());
    }
}
```

Chạy:

```bash
./gradlew test
```

Các status và assertion là **kỳ vọng của cấu hình Spring Boot/Spring Security nêu trong bài**, không phải báo cáo test đã được thực thi. MockMvc không mô phỏng trình duyệt thật đang cache HTTP Basic credentials; `httpBasic(...)` **chủ động gắn Basic header** vào request test, để mô phỏng điều kiện một browser có thể tự mang credential. Test có `Origin: https://untrusted.example` không phải bằng chứng tự động rằng hệ thống có bộ lọc Origin riêng: chính **CSRF token validation** khiến POST thiếu token bị từ chối.

**Điều quan trọng khi kiểm thử CSRF:** giữ CSRF trong security chain và gửi token hợp lệ bằng `.with(csrf())`; không vô hiệu hóa CSRF chỉ để làm test POST trả 200. Test cả token thiếu và token sai, xác nhận state-changing controller **không bị chạy** ở nhánh bị từ chối.

## 10. Vì sao ví dụ trên dùng HTML form thay vì mở JSON API?

HTML form cho thấy điều browser có thể làm **mà không cần quyền đọc response cross-origin**. Với JSON API dùng `fetch`, browser có thêm CORS/same-origin, custom header và credential mode; nhưng không thể từ đó suy ra các endpoint `application/x-www-form-urlencoded` là an toàn.

Nếu sản phẩm muốn dùng một SPA gọi API, bạn cần quyết định **CSRF token contract** riêng:

- Nếu auth dựa trên cookie/session hoặc Basic auto-sent, giữ CSRF mitigation cho unsafe requests.
- Có thể expose CSRF token qua server-rendered page, endpoint cùng origin, hoặc repository/cookie phù hợp; chỉ nơi đáng tin được đọc token.
- Nếu dùng `CookieCsrfTokenRepository.withHttpOnlyFalse()` để JavaScript đọc token từ cookie, phải hiểu các ràng buộc XSS, SameSite, token refresh và Spring Security 6 `CsrfTokenRequestHandler`/BREACH handling. Cookie token readable-by-JS **không phải** mật khẩu, nhưng XSS vẫn có thể đánh cắp nó; cần bảo vệ frontend và chọn request handler đúng cho việc gửi lại raw token.
- Với HTTP Basic popup tự động, nếu browser không giữ session cookie chứa expected CSRF token hoặc SPA không gửi token đúng header/parameter, POST có thể bị 403 mặc dù Basic credential còn trong browser cache.
- Không dùng một CSRF token tĩnh hardcode cho mọi người dùng hoặc mọi phiên; không đưa token vào URL query string khiến log/history/referrer lưu lại.

### CSRF token và cookie token không giống cookie đăng nhập

Một session cookie có thể chỉ giữ thông tin nơi server lưu CSRF token; một cookie khác có thể được dùng làm repository cho token. Chúng không phải bằng chứng rằng Basic credential đã được chuyển sang cookie authentication. Hãy phân biệt **bảo vệ tính toàn vẹn thao tác** với **xác minh danh tính**.

## 11. Phòng vệ nhiều lớp khi HTTP Basic phục vụ browser

CSRF token là biện pháp nền tảng; triển khai thực tế cần một bộ kiểm soát hợp lý:

| Biện pháp | Mục tiêu | Không nên hiểu sai |
| --- | --- | --- |
| CSRF token đồng bộ với request/session hoặc repository hợp lệ | Từ chối unsafe cross-site actions không có secret hợp lệ | Không thay authentication, không chống hoàn toàn XSS |
| `Origin`/`Referer` validation | Ràng buộc nguồn gửi tại các request quan trọng | Cần xử lý header thiếu, redirect và proxy; không chỉ so một chuỗi tùy ý |
| Fetch Metadata policy (`Sec-Fetch-Site` v.v.) | Phân biệt same-origin/same-site/cross-site theo browser | Cần fallback và ngoại lệ hợp pháp |
| Không cho GET đổi trạng thái | Giảm lạm dụng qua links, images, navigation | GET không tự được token-check mặc định |
| HTTPS, HSTS | Bảo vệ credential Basic và dữ liệu trên đường truyền | TLS không ngăn CSRF từ trang độc hại |
| Giới hạn quyền bằng `authorizeHttpRequests` và method security | Chỉ user có quyền thực hiện action | Đã authenticated vẫn có thể bị CSRF |
| Rate limiting, audit | Chống brute force/abuse và hỗ trợ điều tra | Không thay CSRF token |
| Cookie `SameSite`, `Secure`, `HttpOnly` khi có cookie | Giảm một số bề mặt cookie/session | Không tự giới hạn browser Basic Authorization |
| CORS allowlist chặt | Giới hạn browser script truy cập tài nguyên/response | Không chặn mọi HTML form cross-origin |
| CSP, output encoding, XSS prevention | Hạn chế XSS có thể đánh cắp/chèn CSRF token | Không được bỏ qua chỉ vì đã có CSRF token |

Đặc biệt, nếu cùng một URL được cả web browser và API client gọi, cần **một security policy bảo vệ đúng client có rủi ro cao nhất**, hoặc phân tách các route và authentication mechanisms rõ ràng. Không đặt `/api/**` vào danh sách miễn CSRF rồi cho browser Basic chạy trên đó chỉ vì đường dẫn có chữ "api".

## 12. Phân biệt các mã phản hồi 401, 403 và 405

Một request trả lỗi không đủ để biết lỗi do password hay do CSRF:

| Request | Status thường gặp | Nguyên nhân/điểm xử lý |
| --- | --- | --- |
| GET protected URL, không có Basic credential | 401 + `WWW-Authenticate` | Basic `AuthenticationEntryPoint` mời xác thực |
| GET protected URL, Basic đúng | 200 nếu controller/rule cho phép | Basic authentication thành công; GET không cần CSRF theo default |
| POST protected URL, Basic đúng, **không** CSRF | 403 | `CsrfFilter` từ chối trước action |
| POST protected URL, Basic đúng, CSRF sai | 403 | `CsrfFilter` kiểm tra token thất bại |
| POST protected URL, Basic đúng, CSRF đúng | 200/2xx theo controller nếu được phép | Authentication + CSRF + authorization đều đạt |
| POST protected URL, Basic sai, CSRF đúng | 401 thường gặp | Authentication thất bại; chi tiết theo entry point |
| POST tới endpoint chỉ nhận GET, CSRF đúng | Có thể 405 hoặc phản hồi khác | Không có handler phù hợp, sau khi đi qua security filters |
| POST authenticated user thiếu role, CSRF đúng | 403 thường gặp | Authorization chặn, **không** phải CSRF |

Trong cấu hình tùy biến, status/response có thể khác. Quan sát status **cùng** log filter, rule, headers và test để định vị chính xác.

### Quy trình debug 403 khi có Basic

1. Xác nhận request vào đúng `SecurityFilterChain` bằng URL và matcher.
2. Xác nhận HTTP method; POST/PUT/PATCH/DELETE có thể cần CSRF.
3. Kiểm tra CSRF token có tồn tại, có gắn vào đúng parameter/header, cùng repository/session không.
4. Kiểm tra cookie/session liên quan token được browser gửi trong request phù hợp.
5. Kiểm tra Basic header chỉ ở môi trường development một cách **redacted**; không in credentials.
6. Nếu CSRF đã đạt, kiểm tra provider/password/locked account rồi authorities/authorization.
7. Nếu sau reverse proxy, kiểm tra `Origin`/scheme/host và đường dẫn public, không vội bật CORS toàn bộ hoặc disable CSRF.
8. Kiểm thử cùng tình huống ở browser và client non-browser, vì hành vi credential khác nhau.

## 13. `SessionCreationPolicy.STATELESS` có loại CSRF không?

Một cấu hình thường xuất hiện trong API:

```java
.sessionManagement(session ->
    session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
```

Đây chỉ là **fragment** cần import. Nó điều chỉnh cách Spring Security dùng HTTP session cho security context trong cấu hình tương ứng. Nó **không trực tiếp thay đổi** việc browser tự gắn `Authorization: Basic` trong phạm vi đã cache. Vì vậy nếu browser có thể gửi Basic credential tự động, API stateless **vẫn có thể phải đối mặt với CSRF**.

Khi yêu cầu CSRF protection trên ứng dụng stateless, cần chọn `CsrfTokenRepository` và cách client mang token phù hợp; không giả định session repository mặc định tương thích với mọi stateless design. Những câu hỏi tách biệt là:

- Authentication state nằm ở đâu?
- CSRF token expected state nằm ở đâu?
- Browser/client lấy token và gửi lại ra sao?
- API có thể chấp nhận credential tự động browser mang theo hay không?

Chỉ sau khi trả lời bốn câu hỏi này mới nên quyết định CSRF matcher/repository/chính sách.

## 14. Các sai lầm và điều chỉnh thường gặp

| Sai lầm | Hệ quả | Cách làm đúng |
| --- | --- | --- |
| "Basic không dùng cookie nên miễn nhiễm CSRF" | Bỏ qua browser-cached Basic credentials | Xét **ambient credentials**, không chỉ cookies |
| "Không có server session thì không có CSRF" | Nhầm session với hành vi browser | Đánh giá credential tự gửi ở mỗi request |
| "CORS đã chặn nên cross-site POST không tới server" | Quên HTML form có thể gửi request | Dùng CSRF mitigation phía server |
| "SameSite=Lax sẽ chặn Basic" | SameSite không áp dụng cho Authorization header | Áp CSRF policy riêng cho Basic |
| "Basic auth đúng thì request phải được chấp nhận" | POST vẫn có thể bị CSRF filter từ chối | Kiểm tra token và method |
| "POST 403 nghĩa password sai" | Debug sai filter | Phân biệt CSRF 403 với Basic 401 |
| "Tắt CSRF toàn chain để curl chạy" | Tạo đường cross-site state-changing attack | Dùng browser form/CSRF-aware client |
| "Có X-CSRF-TOKEN header bất kỳ là đủ" | Header có thể giả hoặc không có token binding | Server phải kiểm tra **giá trị token hợp lệ** |
| "JSON API luôn an toàn dù chấp nhận Basic browser" | Đánh giá sai content type, CORS, alternate routes | Phân tách mechanism và kiểm tra request format/policy |
| "Client có thể lấy CSRF token từ URL query string" | Token có thể lộ qua logs/referrer | Dùng form field/header qua HTTPS |
| "Chỉ cần Origin header" | Không có kế hoạch cho browser cũ/header thiếu | Dùng defense in depth và policy được test |
| "Đã có CSRF token thì XSS không nguy hiểm" | XSS có thể đọc token và gửi thao tác hợp lệ | Chống XSS độc lập |

## 15. Bài tập tự kiểm tra

**Câu 1.** Ứng dụng không dùng form login, chỉ có `.httpBasic()`. Browser đã cache Basic credentials; user mở một trang ngoài gửi POST form tới URL thay đổi cấu hình. Có cần xét CSRF không?

**Đáp án:** Có. Nếu browser tự gắn Basic credential cho POST tới ứng dụng, request có thể được xác thực như user. `httpBasic()` không tự chứng minh an toàn CSRF.

**Câu 2.** Một developer nói CORS không cấp quyền đọc response cho site xấu nên site đó không thể thay đổi dữ liệu bằng POST HTML form. Phát biểu sai ở đâu?

**Đáp án:** CORS/SOP thường ngăn việc đọc response từ origin khác, nhưng không nhất thiết ngăn gửi HTML form cross-site. CSRF chỉ cần hành động server được thực hiện; không cần đọc kết quả.

**Câu 3.** Một POST chứa `Authorization: Basic ...` đúng nhưng thiếu `_csrf` trên chain vẫn bật CSRF. Spring Security thường trả gì?

**Đáp án:** 403 do `CsrfFilter`, trước khi controller thực hiện thao tác. Authentication hợp lệ không thay thế CSRF token.

**Câu 4.** Vì sao `SameSite=Strict` trên session cookie không phải luận cứ để tắt CSRF cho HTTP Basic?

**Đáp án:** SameSite điều khiển cookie, không trực tiếp điều khiển Basic header mà browser có thể tự gửi. Phải xem từng dạng credential được backend chấp nhận.

**Câu 5.** Một service-to-service API chỉ nhận bearer token do service code cố ý gắn vào `Authorization`, không chấp nhận cookie hay browser Basic. Có nhất thiết bắt mọi POST mang CSRF token không?

**Đáp án:** Không nhất thiết. Nếu threat model chứng minh attacker web origin không thể làm browser tự mang credential hợp lệ và không có ambient authentication khác, có thể thiết kế CSRF exemption có phạm vi chặt. Vẫn cần authentication, authorization, TLS, input validation và các biện pháp chống tấn công khác.

**Câu 6.** Điều gì xảy ra nếu browser submit form của demo nhưng developer xóa hidden `_csrf` input?

**Đáp án:** POST tới `/change` có thể mang Basic credential hợp lệ nhưng `CsrfFilter` từ chối vì thiếu token. Bộ đếm không tăng.

**Câu 7.** Tại sao một test MockMvc với `httpBasic(...)` không chứng minh browser nào cũng tự gửi Basic trong cross-site form?

**Đáp án:** Test chỉ dựng một HTTP request có Basic header và kiểm tra Spring Security phản ứng khi request đó đến server. Hành vi cache/challenge/protection space thuộc browser thực tế, phải kiểm tra riêng khi đánh giá khai thác.

**Câu 8.** Nếu một tài nguyên thay đổi trạng thái qua GET, có thể chỉ dựa vào default CSRF filter để bảo vệ nó không?

**Đáp án:** Không. Spring Security mặc định coi GET là safe method và không yêu cầu CSRF token. Phải đổi endpoint sang unsafe method phù hợp và áp dụng CSRF/authorization.

## 16. Checklist thiết kế và nghiệm thu

- [ ] Liệt kê tất cả đường HTTP Basic được **trình duyệt** truy cập và liệu browser có thể auto-send credentials.
- [ ] Với POST/PUT/PATCH/DELETE thay đổi trạng thái, CSRF validation bật hoặc có mitigation tương đương đã được chứng minh.
- [ ] Không đổi dữ liệu khi GET, HEAD hoặc các safe methods.
- [ ] Không coi CORS hoặc SameSite là lý do duy nhất để miễn CSRF cho HTTP Basic.
- [ ] Xác định chính xác `CsrfTokenRepository`, request handler và vị trí gửi token (form parameter/header).
- [ ] Form/template gửi token thực do Spring Security cấp và đúng phiên/ngữ cảnh.
- [ ] Tests: Basic hợp lệ nhưng thiếu token → 403; token sai → 403; Basic + token hợp lệ → thao tác được phép.
- [ ] Tests: principal thiếu quyền vẫn bị chặn dù CSRF hợp lệ; user không xác thực không bypass Basic.
- [ ] Cấu hình nhiều `SecurityFilterChain` không bỏ sót đường state-changing hoặc login/challenge.
- [ ] Nếu có CSRF exclusions, chứng minh route đó **không** chấp nhận ambient browser credentials và scope đúng.
- [ ] Có biện pháp chống XSS, bảo vệ CSRF tokens khỏi rò rỉ, HTTPS và redaction credential trong logs.
- [ ] Đánh giá sự khác nhau giữa browser versions, HTTP auth cache, realm, protection space và cookie/third-party restrictions.
- [ ] Có regression tests cho cross-origin form, Origin/Fetch Metadata policy nếu được áp dụng.
- [ ] Tài liệu threat model ghi rõ loại client nào được phép và độ tin cậy của từng credential mechanism.

## Kết luận

**HTTP Basic không phải là ngoại lệ CSRF mặc định.** Điểm quyết định là browser có thể **tự mang theo Basic credentials đã cache** khi website bên ngoài kích hoạt request tới origin được bảo vệ. CORS giới hạn khả năng đọc response, SameSite chủ yếu áp dụng cho cookie, còn stateless chỉ nói một phần về trạng thái server; không yếu tố nào tự thay thế một chính sách chống CSRF.

Trong Spring Security Servlet, giữ `CsrfFilter` cho các unsafe browser requests, dùng token do `CsrfTokenRepository` và request handler cung cấp, kết hợp authorization, HTTPS, XSS prevention, và các kiểm soát Origin/Fetch Metadata phù hợp. Chỉ bỏ qua CSRF cho route được chứng minh không dùng credential tự động browser gửi. **Kiểm tra hành vi thực tế bằng test thiếu/sai/đúng token, không suy ra an toàn từ cái tên "HTTP Basic" hoặc "stateless API".**
