# CSRF token và cách máy chủ kiểm tra yêu cầu thay đổi dữ liệu

## 1. CSRF token giải quyết vấn đề gì?

**Cross-Site Request Forgery (CSRF)** là tình huống một trang web không đáng tin khiến trình duyệt của người dùng gửi yêu cầu tới ứng dụng khác, trong khi trình duyệt có thể **tự đính kèm credential** mà ứng dụng đích đang tin cậy: ví dụ session cookie, một số dạng cookie xác thực hoặc HTTP Basic credentials đã được trình duyệt lưu.

Giả sử người dùng đã đăng nhập vào **https://bank.example**, và tại đó có chức năng chuyển tiền bằng POST. Khi người dùng đang mở phiên đăng nhập, một trang độc hại ở origin khác cố khiến browser gửi POST tới ngân hàng. Nếu server chỉ kiểm tra cookie phiên thì request có thể được hiểu là hành động của chủ tài khoản, dù chủ tài khoản chưa cố ý thực hiện giao dịch.

**CSRF token** là một giá trị khó đoán mà server hoặc cơ chế tin cậy liên quan dùng để chứng minh request thay đổi trạng thái đã xuất phát từ ứng dụng/client hợp lệ, không chỉ là request có cookie tự động đi kèm. Theo **synchronizer token pattern**, server lưu **token kỳ vọng** gắn với trạng thái thích hợp, còn trang/form hợp lệ lấy token và phải chủ động gửi lại trong **form field** hoặc **HTTP header**. Một trang khác origin thông thường không thể tự đọc token từ ứng dụng đích do giới hạn same-origin policy và thiết kế endpoint.

~~~text
Trình duyệt đã đăng nhập
       |
       +--> Yêu cầu hợp lệ từ trang ứng dụng
       |      Cookie phiên + CSRF token trong header/form
       |      -> Server kiểm token -> xử lý nghiệp vụ
       |
       +--> Yêu cầu giả mạo từ trang ngoài
              Cookie phiên có thể được gửi tự động
              Nhưng không có token đúng
              -> Server từ chối trước controller
~~~

**Chỉ kiểm tra CSRF token không đủ để xác thực hoặc phân quyền.** Một request POST có token đúng vẫn phải được kiểm tra Authentication, GrantedAuthority, ownership/tenant, input validation và quy tắc nghiệp vụ. Ngược lại, đã đăng nhập/đủ role không có nghĩa được bỏ qua CSRF.

### Mục tiêu bài học

Sau bài này, bạn có thể:
1. Mô tả nơi CSRF token được tạo, lưu, xuất ra form/client, gửi lại và xác minh.
2. Giải thích cơ chế Spring Security **CsrfFilter**, **CsrfTokenRepository**, **CsrfTokenRequestHandler**, cùng **MissingCsrfTokenException / InvalidCsrfTokenException**.
3. Phân biệt các method thường **không yêu cầu** CSRF và method **phải được bảo vệ** theo mặc định.
4. Tích hợp CSRF token với form login, request AJAX/JSON và ứng dụng JavaScript.
5. Chạy ví dụ Spring Boot 3.x / Spring Security 6.x / Java 17+ có endpoint tăng bộ đếm, thấy request thiếu/sai token bị chặn và dữ liệu không thay đổi.
6. Viết kiểm thử MockMvc để xác nhận cả trường hợp hợp lệ và trường hợp bị từ chối.
7. Không nhầm CSRF với CORS, XSS, SameSite cookie hoặc Bearer token.

> Phạm vi ví dụ: **Spring MVC/Servlet**. WebFlux có bộ lọc và kiểu API reactive khác. Ví dụ dùng credential dạng session cookie để thấy nguy cơ CSRF rõ ràng, không đưa ra khuyến nghị tắt CSRF cho mọi API.

## 2. Bản chất cuộc tấn công và điều kiện cần để xảy ra

Một kịch bản CSRF có các yếu tố:

- **Victim** đã có một credential mà browser có thể đính kèm tự động khi gửi request tới ứng dụng đích.
- **Attacker** điều khiển hoặc dụ victim truy cập một trang, link, form hay nội dung có khả năng tạo request không mong muốn.
- **Target application** có endpoint làm thay đổi dữ liệu/trạng thái hoặc gây hậu quả nhạy cảm.
- **Server** chấp nhận request chỉ dựa vào credential được gửi tự động mà không có cơ chế bổ sung phân biệt ý định của client.

Ví dụ về một form khác origin có khả năng được trình duyệt gửi đi, **chỉ nhằm minh họa rủi ro**, không phải một request hợp lệ trong demo:

~~~html
<form method="post" action="https://bank.example/transfer">
    <input type="hidden" name="to" value="attacker-account">
    <input type="hidden" name="amount" value="1000">
    <button type="submit">Gửi</button>
</form>
~~~

Tùy chính sách **SameSite** của cookie, loại request, trình duyệt và cách application nhận dữ liệu, credential có thể hoặc không được gửi. Không nên lập luận “browser chắc chắn luôn gửi mọi cookie”; cần kiểm chứng cookie policy trong môi trường thật. Tuy nhiên, **không dựa vào SameSite như thay thế duy nhất cho CSRF token** khi ứng dụng có browser credential tự gửi và endpoint nhạy cảm.

Điểm đáng chú ý: attacker **không nhất thiết đọc được response** của API để gây tác hại. CORS/same-origin policy hạn chế khả năng đọc response hoặc gửi một số kiểu cross-origin request, nhưng nếu hành động được thực hiện và server không kiểm CSRF đúng cách, việc không đọc được response vẫn không làm hành động biến mất.

### CSRF khác XSS

| Khía cạnh | CSRF | XSS |
| --- | --- | --- |
| Ý tưởng | Làm browser của victim gửi hành động ngoài ý muốn tới ứng dụng đã đăng nhập | Chèn/chạy JavaScript không đáng tin trong origin của ứng dụng |
| Thứ attacker muốn lợi dụng | Credential tự đi kèm request | Quyền chạy script cùng origin, DOM, dữ liệu truy cập được |
| Cách giảm rủi ro | CSRF token, SameSite, Origin/Referer checks phù hợp, thiết kế API | Escaping/output encoding, CSP, sanitize input đúng ngữ cảnh, tránh DOM sinks |
| Quan hệ | CSRF token giúp ngăn nhiều yêu cầu giả mạo cross-site | **XSS có thể làm vô hiệu nhiều giả định CSRF**, vì script chạy cùng origin có thể lấy hoặc gửi token |

**CSRF token không chữa XSS.** Ngược lại, chống XSS tốt cũng không bảo đảm ứng dụng đã xử lý đúng mọi tình huống CSRF.

## 3. Một CSRF token có những đặc điểm gì?

Với synchronizer token pattern, các đặc tính thường cần:

1. **Khó đoán**: tạo bằng nguồn ngẫu nhiên mật mã thích hợp, đủ entropy, không tự ghép timestamp/username rồi coi là secret.
2. **Có nguồn kỳ vọng đáng tin**: server có thể nạp giá trị từ repository gắn đúng bối cảnh; không tin token do client vừa đề xuất làm giá trị kỳ vọng.
3. **Không tự động gửi chỉ vì browser có cookie xác thực**: client phải lấy token từ nội dung/endpoint ứng dụng được phép đọc, rồi chủ động đưa vào header hoặc form field.
4. **Được xác minh trước khi thực hiện thay đổi dữ liệu**: sai hoặc thiếu token phải ngăn handler nghiệp vụ.
5. **Có vòng đời hợp lý**: token có thể bị thay/loại bỏ khi login, logout, hết phiên hoặc theo yêu cầu bảo mật. Client phải có cách lấy token mới.
6. **Không lộ qua URL**: query string có thể xuất hiện trong browser history, server logs, Referer hoặc công cụ giám sát. Nên dùng header hoặc form body.

Token không phải password của user, không phải session identifier và **không đại diện quyền ADMIN/USER**. Nó chứng minh một điều kiện hợp lệ của request trong ngữ cảnh chống CSRF. Token đúng **không thể thay** cho Authentication hoặc Authorization.

### Vì sao cookie phiên không đủ?

Nếu browser tự gửi cookie JSESSIONID trên request tương thích với cookie policy, server có thể tìm đúng HttpSession của victim. Đây là tác dụng của session cookie, không phải bằng chứng user đã bấm nút trên trang ngân hàng. CSRF token phải có nguồn mà trang attacker thông thường **không thể đọc và tự đưa vào** request. Đó là khác biệt quan trọng giữa cookie gửi tự động và form/header token được client cung cấp chủ động.

## 4. Spring Security xử lý CSRF ở tầng nào?

Trong **Spring Security Servlet**, thành phần chính là **CsrfFilter**. CsrfFilter là một filter trong Spring Security filter chain; nó thực hiện kiểm tra yêu cầu cần CSRF **trước khi controller xử lý logic nghiệp vụ**.

Sơ đồ tổng quát:

~~~text
HTTP request
   |
   v
SecurityFilterChain / CsrfFilter
   |
   +--> CsrfTokenRepository
   |       +--> Tìm/tạo token kỳ vọng (có thể deferred)
   |
   +--> CsrfTokenRequestHandler
   |       +--> Cho ứng dụng truy cập token của request
   |       +--> Đọc token client gửi qua header/parameter
   |
   +--> RequestMatcher: method này cần CSRF?
            |
            +--> KHÔNG (GET/HEAD/OPTIONS/TRACE mặc định)
            |       -> đi tiếp trong filter chain
            |
            +--> CÓ (POST/PUT/PATCH/DELETE...)
                    |
                    +--> Lấy expected token từ repository
                    +--> Lấy actual token từ request
                    +--> So sánh theo request handler
                              |
                              +--> Đúng -> tiếp tục filter chain
                              |            -> authorization -> controller
                              |
                              +--> Thiếu/sai -> AccessDeniedHandler
                                               -> thông thường HTTP 403
                                               -> controller không chạy
~~~

### 4.1. Trách nhiệm của từng thành phần

| Thành phần | Chức năng | Ghi nhớ |
| --- | --- | --- |
| **CsrfFilter** | Chọn request cần CSRF và kiểm actual token so với expected token | Có thể chặn POST trước khi tới controller |
| **CsrfToken** | Đối tượng chứa tên header, tên parameter và chuỗi token | Ví dụ parameter **_csrf**, header **X-CSRF-TOKEN** |
| **CsrfTokenRepository** | Sinh, lưu, nạp hoặc xóa token kỳ vọng | Mặc định sử dụng **HttpSessionCsrfTokenRepository** |
| **DeferredCsrfToken** | Trì hoãn việc tải/tạo token đến khi cần | Tránh truy cập session không cần thiết trên nhiều request |
| **CsrfTokenRequestHandler** | Làm token khả dụng cho ứng dụng và đọc actual token từ request | Mặc định Spring Security 6 sử dụng XOR request handler để chống BREACH |
| **AccessDeniedHandler** | Quyết định response khi bị từ chối | Thường 403 cho thiếu/sai CSRF token |

**Không tự viết lại so sánh token trong controller** khi đã có CsrfFilter, trừ khi kiến trúc có yêu cầu đặc biệt và đã phân tích security đầy đủ. Với cấu hình mặc định, filter kiểm token trước business handler.

### 4.2. Thứ tự thực hiện quan trọng

Trong Spring Security 6, CsrfFilter thường:
1. Lấy **DeferredCsrfToken** liên kết với repository.
2. Chuyển supplier của token cho **CsrfTokenRequestHandler**, nhờ đó controller/template có thể truy cập token.
3. Xác định request method có yêu cầu CSRF hay không.
4. Nếu không yêu cầu, tiếp tục filter chain; chưa nhất thiết phải nạp session/token.
5. Nếu yêu cầu, lấy token kỳ vọng từ repository.
6. Đọc token do client cung cấp qua header hoặc request parameter theo handler.
7. Kiểm tra và cho qua, hoặc xử lý AccessDeniedException nếu thiếu/sai.

Vì vậy, **GET /csrf** có thể làm token được nạp/tạo nếu controller thực sự gọi CsrfToken.getToken(); còn một GET công khai khác không tự buộc session/token được sinh ra chỉ vì CsrfFilter có mặt.

### 4.3. MissingCsrfTokenException và InvalidCsrfTokenException

Theo API Spring Security:
- **MissingCsrfTokenException** thể hiện tình trạng thiếu expected token khi cần xác minh.
- **InvalidCsrfTokenException** có thể xuất hiện khi expected token đã có nhưng actual token thiếu hoặc không khớp.

Đừng xây dashboard dựa trên giả định mọi request không có header đều tạo chính xác một loại exception bất biến. Các trường hợp khác nhau tùy repository, session, request handler và vòng đời token. Ở phía client, hai tình huống này thường thể hiện bằng **403**, nhưng log bảo mật mới giúp phân biệt nguyên nhân.

## 5. HTTP method nào cần CSRF?

Mặc định, Spring Security Servlet xem những method sau là **safe methods** đối với CSRF:

- **GET**
- **HEAD**
- **OPTIONS**
- **TRACE**

Các method còn lại, ví dụ **POST, PUT, PATCH, DELETE**, được coi là cần kiểm tra CSRF theo matcher mặc định. Đây là **quy ước bảo mật**, dựa vào giả định ứng dụng thực sự tuân thủ semantics của HTTP.

| Request | CSRF theo mặc định? | Điều cần tránh |
| --- | --- | --- |
| GET /products | Không | Không sửa dữ liệu bằng GET |
| HEAD /products | Không | Không tạo giao dịch phụ như một side effect |
| OPTIONS /products | Không | CORS/preflight không phải quyền thực hiện POST |
| POST /orders | Có | Không chỉ dựa vào session cookie |
| PUT /profile | Có | Không cho cập nhật nếu thiếu token |
| PATCH /settings | Có | Không cho cập nhật nếu thiếu token |
| DELETE /documents/42 | Có | Không cho xóa nếu thiếu token |

**Tuyệt đối không xây endpoint như GET /delete-account để thực hiện xóa tài khoản**, rồi mong CsrfFilter bảo vệ nó. GET mặc định không kiểm CSRF; một link hoặc hình ảnh được browser tải có thể kích hoạt GET. Hãy đặt thao tác thay đổi trạng thái đúng method và áp dụng authorization/CSRF.

CSRF protection cũng **không bảo đảm mọi POST hợp lệ về nghiệp vụ**; nó chỉ loại bỏ một loại request thiếu tính hợp lệ. Server vẫn phải kiểm quyền, giới hạn tài nguyên và validation.

### Cần làm gì với HTTP method override?

Nếu ứng dụng hỗ trợ chuyển **POST + _method=DELETE** bằng filter hoặc framework khác, cần kiểm thứ tự filter và bảo đảm request được CSRF bảo vệ trước khi thao tác DELETE có thể diễn ra. Không cho phép đường tắt đổi method rồi bỏ qua lớp bảo vệ. Cần test thực tế vì filter registration/order khác nhau giữa ứng dụng.

## 6. CsrfTokenRepository: token kỳ vọng được lưu ở đâu?

### 6.1. HttpSessionCsrfTokenRepository (mặc định)

Spring Security Servlet thường dùng **HttpSessionCsrfTokenRepository**:

~~~text
Browser                         Server
    | GET /csrf
    |--------------------------->
    |                            Tạo/tải expected CSRF token
    |                            Lưu trong HttpSession (khi cần)
    |<---------------------------
    | JSON chứa token và cookie phiên phù hợp
    |
    | POST /api/counter/increment
    | Cookie: JSESSIONID=...
    | X-CSRF-TOKEN: <token>
    |--------------------------->
    |                            Tìm session theo cookie
    |                            Lấy expected token
    |                            Đọc actual token từ header
    |                            So sánh -> hợp lệ?
    |<---------------------------
    | 200 nếu hợp lệ và đủ quyền
~~~

Token của phiên A không được coi là hợp lệ cho phiên B chỉ vì hai phiên có cùng username. **Token lấy được từ phiên này không nên dùng để xác nhận request của một phiên độc lập khác**.

Khi session hết hạn hoặc bị hủy, token kỳ vọng gắn với session cũng không còn trong phạm vi đó. Form mở từ lâu có thể gửi token cũ rồi nhận 403; ứng dụng nên có UX giúp lấy token mới mà không thực hiện lại thao tác nhạy cảm ngoài ý muốn.

### 6.2. CookieCsrfTokenRepository

Spring Security cũng hỗ trợ **CookieCsrfTokenRepository**. Cách này đặt token kỳ vọng vào cookie, thường theo mô hình **double-submit cookie**, trong đó client gửi token tương ứng qua header.

Khác biệt:
- Repository bằng session lưu expected token phía server trong HttpSession.
- Repository bằng cookie có thể không phụ thuộc session để lưu expected token, nhưng phải thiết kế cách cookie/header được tạo, gửi và kiểm đúng.
- **Cookie xác thực** và **cookie CSRF** có mục đích khác nhau. Không dùng việc có cookie CSRF như bằng chứng user đã đăng nhập.
- Nếu cho JavaScript đọc cookie CSRF (ví dụ cấu hình withHttpOnlyFalse), điều này là một tradeoff có chủ đích; session/auth cookie nên giữ HttpOnly.
- Double-submit cần xét cookie injection, domain/path, SameSite, HTTPS, origin và integrity; không tạo một cookie attacker dễ ghi rồi xem là token đáng tin.

### 6.3. Không tự chuyển sang CookieCsrfTokenRepository nếu chưa hiểu SPA

Trong Spring Security 6.x, **XorCsrfTokenRequestAttributeHandler** mặc định cung cấp **BREACH protection** bằng cách thêm ngẫu nhiên vào token được trình bày cho client. Header lấy trực tiếp từ một **cookie chứa raw token** có thể cần **request handler cho SPA** để resolve token đúng cách. Vì vậy, chỉ đổi:

~~~java
http.csrf(csrf ->
    csrf.csrfTokenRepository(
        CookieCsrfTokenRepository.withHttpOnlyFalse()));
~~~

là một **fragment cấu hình**, không nhất thiết là cách tích hợp SPA đầy đủ trên Spring Security 6. Hãy dựa trên hướng dẫn chính thức cho SPA (bao gồm request handler giải mã/ủy quyền phù hợp và token refresh sau login/logout) và kiểm thử thực tế, thay vì tắt BREACH protection một cách tùy tiện.

Trong demo của bài, ta dùng **repository mặc định trên session** và trả token biểu diễn phù hợp qua **GET /csrf**, nên không cần tự sửa request handler.

## 7. BREACH protection và deferred token trong Spring Security 6

Spring Security 6 có hai chi tiết dễ làm developer nhầm:

### 7.1. Deferred CSRF token

Token được tải theo cơ chế trì hoãn. Với GET thuần chỉ đọc dữ liệu, Spring Security có thể không cần tạo/đọc HttpSession chỉ để xử lý CSRF. Nhưng khi một request dùng unsafe method hoặc controller/template cần xuất token, token được tải/khởi tạo.

Tác dụng chính là tránh session lookup không cần thiết. Việc token được deferred **không có nghĩa POST được bỏ qua kiểm tra**: tới unsafe request, CsrfFilter phải lấy token kỳ vọng để xác minh.

### 7.2. XorCsrfTokenRequestAttributeHandler và BREACH

Để giảm nguy cơ BREACH (một loại tấn công liên quan nén nội dung và giá trị phản hồi), Spring Security 6 mặc định cung cấp token được **mask với randomness** khi xuất ra request attribute. Giá trị token hiển thị ở hai lần render có thể khác dù raw token lưu trong repository vẫn tương ứng cùng phiên.

~~~text
Raw CSRF token trong repository:       T
Request 1, token được trình bày:       mask(T, random1)
Request 2, token được trình bày:       mask(T, random2)

Client gửi lại token được trình bày.
Request handler giải mã về T.
CsrfFilter so sánh với expected T.
~~~

Điều này giải thích tại sao nhìn thấy chuỗi token trên hai GET khác nhau không nhất thiết chứng minh session bị thay. **Không tự bỏ masking hay so sánh thủ công chuỗi masked với raw token**. Hãy để CsrfTokenRequestHandler xử lý theo hợp đồng của Spring Security.

## 8. Ví dụ Spring Boot 3.x hoàn chỉnh: quan sát POST bị chặn trước khi dữ liệu đổi

Chúng ta tạo một bộ đếm theo **HTTP session**:

- **GET /csrf**: trả CSRF token và tên header/parameter cho client; được phép truy cập chưa đăng nhập.
- **GET /api/counter**: xem giá trị hiện tại; yêu cầu người dùng đã xác thực.
- **POST /api/counter/increment**: tăng giá trị; yêu cầu **đã xác thực** và **CSRF token hợp lệ**.
- **GET /login, POST /login**: sử dụng **form login mặc định của Spring Security**; không viết controller xác thực riêng.

Để thấy điều CSRF thực sự bảo vệ, ta kiểm tra POST thiếu token trả 403 và sau đó đọc lại giá trị vẫn bằng 0. Ở lần POST có token đúng, giá trị tăng lên 1.

### 8.1. Chuẩn bị dự án

Tạo Spring Boot **3.x**, Java **17+**, Gradle, group **com.example**, artifact **demo**, package **com.example.demo** bằng Spring Initializr. Chọn:

- **Spring Web** → spring-boot-starter-web.
- **Spring Security** → spring-boot-starter-security.

Ứng dụng không cần template engine vì form login mặc định có sẵn trong Spring Security và các endpoint API trả JSON. Trong Gradle project đã sinh, tạo tệp:

~~~text
src/main/java/com/example/demo/CsrfTokenDemoApplication.java
~~~

### 8.2. Mã Java đầy đủ

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
public class CsrfTokenDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CsrfTokenDemoApplication.class, args);
    }
}

@Configuration
@EnableWebSecurity
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(
                    SessionCreationPolicy.IF_REQUIRED))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/csrf")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/counter")
                    .authenticated()
                .requestMatchers(HttpMethod.POST,
                    "/api/counter/increment")
                    .authenticated()
                .anyRequest().denyAll())
            // Không tắt CSRF: mặc định Spring Security bảo vệ
            // các HTTP method thay đổi trạng thái.
            .formLogin(form -> form
                .defaultSuccessUrl("/api/counter", true)
                .permitAll())
            .logout(logout -> logout
                .logoutSuccessUrl("/login?logout")
                .permitAll())
            .build();
    }

    @Bean
    UserDetailsService userDetailsService() {
        UserDetails learner = User.withUsername("learner")
            .password("{noop}demo123")
            .roles("USER")
            .build();
        return new InMemoryUserDetailsManager(learner);
    }
}

@Component
@SessionScope
class CounterState {
    private int value;

    public synchronized int get() {
        return value;
    }

    public synchronized int increment() {
        return ++value;
    }
}

@RestController
class CounterController {

    private final CounterState state;

    CounterController(CounterState state) {
        this.state = state;
    }

    public record CsrfInfo(
            String headerName,
            String parameterName,
            String token) {
    }

    @GetMapping("/csrf")
    CsrfInfo csrf(CsrfToken csrfToken) {
        return new CsrfInfo(
            csrfToken.getHeaderName(),
            csrfToken.getParameterName(),
            csrfToken.getToken());
    }

    @GetMapping("/api/counter")
    Map<String, Integer> counter() {
        return Map.of("count", state.get());
    }

    @PostMapping("/api/counter/increment")
    Map<String, Integer> increment() {
        return Map.of("count", state.increment());
    }
}
~~~

**Giải thích những điểm quan trọng:**

1. **@EnableWebSecurity** và SecurityFilterChain cấu hình bảo vệ endpoint trên Servlet. Chính sách default của Spring Security 6.x vẫn có CSRF protection; không gọi **csrf.disable()**.
2. **@SessionScope** lưu CounterState theo HttpSession để quan sát trạng thái. Controller singleton nhận **scoped proxy** của CounterState; mỗi session có instance riêng. Hai request cùng session dùng cùng bộ đếm.
3. **GET /csrf** được permitAll nhưng vẫn đi qua Spring Security filter chain để có CsrfToken. Gọi getToken() khiến token deferred được thực sự nạp/tạo khi cần.
4. **formLogin** sinh trang đăng nhập mặc định và cho phép các URL phục vụ flow login. POST /login được **form authentication filter** xử lý, không phải do CounterController.
5. **POST /api/counter/increment** chỉ chạy controller nếu request đã qua CSRF filter và có Authentication phù hợp. Thiếu token có thể nhận **403 trước khi Spring Security quyết định redirect login**.
6. **CounterState.increment()** dùng synchronized chỉ để phép tăng số trong demo không bị lost update khi cùng session gửi request đồng thời. Không coi HttpSession là transaction store trong production.
7. **{noop}demo123** là mật khẩu thử nghiệm cục bộ; không lưu mật khẩu theo kiểu noop trong sản phẩm thật. Dùng PasswordEncoder và user store phù hợp.

**Không có token CSRF cố định trong bài.** Mỗi lần chạy có giá trị được tạo ngẫu nhiên; không sao chép token mẫu từ tài liệu để gửi vào server của bạn.

### 8.3. Chạy ứng dụng

Từ thư mục project có Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows: **gradlew.bat bootRun**. Mặc định, ứng dụng ở **http://localhost:8080** nếu không thay đổi server.port.

Bạn có thể dùng browser mở **/login** để đăng nhập bằng learner/demo123, sau đó mở **/api/counter** và quan sát JSON. Tuy nhiên, để kiểm chứng thiếu/sai CSRF, dùng curl theo từng bước có cookie jar là rõ ràng hơn.

### 8.4. Thử với Bash, curl và Python 3

Lệnh dưới đây giả định terminal kiểu Bash có **curl** và **python3**, không phải cú pháp PowerShell nguyên bản. Tạo cookie jar **trong thư mục thử nghiệm cá nhân**; không commit hoặc chia sẻ nó. Lưu ý dùng **-b** để gửi cookie và **-c** để ghi cookie mới, vì session ID có thể thay đổi sau login.

**Bước 1: lấy token trước khi đăng nhập**

~~~bash
curl -sS -c cookies.txt \
  http://localhost:8080/csrf > csrf-before.json

python3 -m json.tool csrf-before.json
~~~

JSON trả về sẽ có dạng:

~~~json
{
  "headerName": "X-CSRF-TOKEN",
  "parameterName": "_csrf",
  "token": "gia-tri-ngau-nhien-do-server-tra-ve"
}
~~~

Chuỗi token ở trên chỉ là nhãn minh họa; token thực do server tạo. Browser/curl lưu **JSESSIONID** khi repository phải tạo phiên để ghi token.

**Bước 2: POST /login cần token và cookie cùng phiên**

~~~bash
CSRF=$(python3 -c \
  "import json; print(json.load(open('csrf-before.json'))['token'])")

curl -i -b cookies.txt -c cookies.txt \
  --data-urlencode "username=learner" \
  --data-urlencode "password=demo123" \
  --data-urlencode "_csrf=$CSRF" \
  http://localhost:8080/login
~~~

Theo cấu hình, Spring Security xác thực learner, áp dụng cơ chế quản lý session phù hợp, rồi thường trả **HTTP 302** đến **/api/counter**. Không dùng **-L** thì curl không tự đi theo redirect.

**Bước 3: kiểm tra trạng thái đầu tiên**

~~~bash
curl -i -b cookies.txt \
  http://localhost:8080/api/counter
~~~

Dự kiến HTTP 200 với JSON:

~~~json
{"count":0}
~~~

**Bước 4: gửi POST không có CSRF token**

~~~bash
curl -i -X POST -b cookies.txt \
  http://localhost:8080/api/counter/increment

curl -i -b cookies.txt \
  http://localhost:8080/api/counter
~~~

Dự kiến POST trả **403**, lần GET sau vẫn:

~~~json
{"count":0}
~~~

Đây là bằng chứng từ góc nhìn người dùng: POST bị chặn **trước khi CounterController.increment() tăng bộ đếm**.

**Bước 5: lấy token mới sau khi login rồi POST hợp lệ**

Trong Spring Security 6, **CsrfAuthenticationStrategy** có thể xóa token cũ sau khi đăng nhập thành công. Vì vậy hãy lấy token mới sau login; không giả định token trong csrf-before.json vẫn dùng được:

~~~bash
curl -sS -b cookies.txt -c cookies.txt \
  http://localhost:8080/csrf > csrf-after.json

CSRF=$(python3 -c \
  "import json; print(json.load(open('csrf-after.json'))['token'])")

curl -i -X POST -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $CSRF" \
  http://localhost:8080/api/counter/increment
~~~

Dự kiến HTTP 200 với JSON:

~~~json
{"count":1}
~~~

Sau đó:

~~~bash
curl -i -b cookies.txt \
  http://localhost:8080/api/counter
~~~

Dự kiến:

~~~json
{"count":1}
~~~

**Bước 6: thử token cố tình sai**

~~~bash
curl -i -X POST -b cookies.txt \
  -H 'X-CSRF-TOKEN: definitely-not-the-session-token' \
  http://localhost:8080/api/counter/increment
~~~

Dự kiến **403**, và GET /api/counter vẫn là **{"count":1}**.

### 8.5. Bảng đối chiếu hành vi

| Request | Token / authentication | HTTP dự kiến | Giá trị counter |
| --- | --- | --- | --- |
| GET /csrf | Chưa login | 200 | Không thay đổi |
| POST /login | Cookie + CSRF token đúng, username/password đúng | 302 | Không thay đổi |
| GET /api/counter | Cookie sau login | 200 | 0 |
| POST /api/counter/increment | Cookie sau login, **không CSRF token** | **403** | Vẫn 0 |
| POST /api/counter/increment | Cookie sau login, CSRF token **sai** | **403** | Không tăng |
| POST /api/counter/increment | Cookie sau login, token **đúng** | **200** | Tăng lên 1 |
| GET /api/counter | Cùng cookie sau POST hợp lệ | 200 | 1 |
| GET /api/counter | Chưa login | 302 tới /login | Không lộ số liệu |
| POST /api/counter/increment | Chưa login, không token | Thường **403** do CSRF trước authorization | Không thay đổi |

Các giá trị này là **kết quả dự kiến từ mã nguồn**, không phải bản ghi thực thi trên máy của người học. Nếu request bị 403 vì thiếu token nhưng bạn sửa client bằng cách thêm username/password mà vẫn không gửi CSRF, vấn đề không được giải quyết.

**Chú ý:** trường hợp không có token có thể bị CSRF chặn trước, nên không áp đặt quy tắc “chưa login luôn trả 401” hoặc “chưa login luôn 302”. Kết quả tùy filter và authentication mechanism; trong demo form login, một GET protected khi chưa đăng nhập thường redirect 302.

### 8.6. Logout và việc thay token

Với logout mặc định, Spring Security xử lý POST /logout có CSRF hợp lệ. Token cũ và session/security state có thể bị xóa hoặc làm mất hiệu lực sau logout.

Lấy token khi đang login rồi POST logout:

~~~bash
curl -sS -b cookies.txt -c cookies.txt \
  http://localhost:8080/csrf > csrf-logout.json

CSRF=$(python3 -c \
  "import json; print(json.load(open('csrf-logout.json'))['token'])")

curl -i -X POST -b cookies.txt -c cookies.txt \
  -H "X-CSRF-TOKEN: $CSRF" \
  http://localhost:8080/logout
~~~

Theo cấu hình, logout thành công thường trả **302** tới **/login?logout** và phiên đã đăng nhập không còn hiệu lực. Nếu client cần tiếp tục gửi unsafe requests trước khi đăng nhập lại, hãy **lấy CSRF token mới** theo chính sách ứng dụng. Không tái sử dụng token từ một session đã logout.

## 9. Tự động kiểm thử bằng Spring Security Test và MockMvc

Chỉ kiểm tra trường hợp POST có CSRF token trả 200 là chưa đủ. Bạn cần chứng minh **POST thiếu token không được tới logic nghiệp vụ** và **POST có token sai cũng bị từ chối**.

Thêm dependency vào **build.gradle** nếu chưa có:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Đây là **fragment của Gradle Groovy DSL**, không phải toàn bộ file. Spring Initializr thường đã thêm spring-boot-starter-test; không khai báo trùng.

Tạo file:

~~~text
src/test/java/com/example/demo/CsrfTokenDemoApplicationTest.java
~~~

Nội dung:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

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
class CsrfTokenDemoApplicationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void csrfRejectsMissingAndInvalidTokenBeforeMutation()
            throws Exception {
        // Đăng nhập qua Spring Security form filter, có token cho POST.
        MvcResult login = mvc.perform(post("/login")
                .with(csrf())
                .param("username", "learner")
                .param("password", "demo123"))
            .andExpect(status().is3xxRedirection())
            .andReturn();

        MockHttpSession session = (MockHttpSession)
                login.getRequest().getSession(false);

        mvc.perform(get("/api/counter").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.count").value(0));

        // Không có CSRF token -> 403, không gọi controller.
        mvc.perform(post("/api/counter/increment")
                .session(session))
            .andExpect(status().isForbidden());

        mvc.perform(get("/api/counter").session(session))
            .andExpect(jsonPath("$.count").value(0));

        // Token cố tình không hợp lệ -> 403.
        mvc.perform(post("/api/counter/increment")
                .session(session)
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());

        // Token hợp lệ -> controller mới được tăng giá trị.
        mvc.perform(post("/api/counter/increment")
                .session(session)
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.count").value(1));

        mvc.perform(get("/api/counter").session(session))
            .andExpect(jsonPath("$.count").value(1));
    }
}
~~~

Chạy test:

~~~bash
./gradlew test
~~~

Windows: **gradlew.bat test**.

**Giải thích kiểm thử:**
- **csrf()** là test helper từ spring-security-test để cung cấp CSRF token hợp lệ, không phải client production tự có token.
- **csrf().useInvalidToken()** cố tình gửi token sai để kiểm tra đường bị chặn.
- Ta giữ cùng **MockHttpSession** để việc so sánh expected token và bộ đếm có ý nghĩa.
- Kiểm tra bộ đếm trước và sau 403 giúp chứng minh business mutation không xảy ra.
- Test thực hiện form login để có authenticated session, không chỉ dựng @WithMockUser. Tuy nhiên, nếu muốn kiểm tra cookie flags, redirect, token rotation hoặc CORS thực tế, còn cần integration/e2e test ở trình duyệt hoặc HTTP client đầy đủ.

**Lưu ý:** các đoạn code/lệnh là tài liệu để chạy trong project tương thích; kết quả nêu ra là expected behavior, không khẳng định đã chạy Gradle ngay trong tài liệu.

## 10. Tích hợp HTML form và Thymeleaf

Với ứng dụng server-rendered, thường gửi CSRF token qua hidden form field.

Ví dụ fragment HTML tương ứng với một form thay đổi thông tin:

~~~html
<form action="/settings" method="post">
    <input type="hidden" name="_csrf"
           value="token-from-server">
    <button type="submit">Lưu</button>
</form>
~~~

Dòng **value** chỉ mô tả nơi token cần được gắn; **không dùng chuỗi cố định** như trong snippet cho ứng dụng thật. Nếu dùng **Thymeleaf + Spring Security** đúng cách, form với **th:action** có thể được tích hợp **RequestDataValueProcessor** để chèn CSRF field tương ứng:

~~~html
<form th:action="@{/settings}" method="post">
    <button type="submit">Lưu</button>
</form>
~~~

Template fragment trên cần dùng trong project có Spring MVC và Thymeleaf, không phải file HTML standalone; controller cần có endpoint POST /settings và authorization tương ứng. Xem HTML đã render trong DevTools để chắc chắn trường **_csrf** tồn tại.

Khi server nhận form:
1. Browser gửi cookie phiên theo chính sách.
2. Browser gửi form field **_csrf** do ứng dụng đã render.
3. CsrfFilter đọc token từ form parameter.
4. Token được kiểm trước khi business handler chạy.
5. Nếu token sai hoặc thiếu, handler không được thực thi.

**Form login và logout cũng là những thao tác thay đổi trạng thái.** Trong cấu hình Servlet phổ biến, POST /login và POST /logout phải có token hợp lệ. Đừng thêm csrf.ignoringRequestMatchers("/login") hoặc bỏ bảo vệ logout chỉ để khỏi cập nhật form/client mà chưa đánh giá nguy cơ login CSRF.

## 11. Tích hợp fetch/JSON từ browser và ứng dụng SPA

Khi frontend gọi API bằng JavaScript, cách dễ quan sát là:

~~~javascript
// Ví dụ chạy ở cùng origin với server.
// Server phải cung cấp GET /csrf trả JSON tương thích.
async function csrfInfo() {
    const response = await fetch("/csrf", {
        credentials: "same-origin"
    });
    if (!response.ok) {
        throw new Error("Không lấy được CSRF token");
    }
    return response.json();
}

async function increment() {
    const csrf = await csrfInfo();
    const response = await fetch("/api/counter/increment", {
        method: "POST",
        credentials: "same-origin",
        headers: {
            [csrf.headerName]: csrf.token
        }
    });
    if (!response.ok) {
        throw new Error("Request bị từ chối: " + response.status);
    }
    return response.json();
}
~~~

Đây là **đoạn JavaScript frontend**, không tự chạy khi chỉ đặt trong source Java. Nó lấy token từ endpoint cùng origin và gửi lại trong một header chủ động. Với ứng dụng khác origin, phải cấu hình CORS/credentials/cookie/SameSite đúng threat model; không chuyển **Access-Control-Allow-Origin: \*** kết hợp credentials thành lời giải chung.

### SPA và token rotation

Với Spring Security 6:
- Token có thể được load deferred.
- BREACH masking làm token được biểu diễn theo request khác nhau.
- **CsrfAuthenticationStrategy** xóa token cũ khi xác thực thành công.
- **CsrfLogoutHandler** xóa token khi logout thành công.
- SPA muốn tiếp tục POST/PUT/DELETE sau login/logout có thể cần gọi lại endpoint /csrf để lấy token mới.

Nếu frontend lưu CSRF token vô thời hạn trong memory mà không refresh sau login, một POST tiếp theo có thể trả **403** dù session đã đăng nhập. Đây không phải dấu hiệu server ngẫu nhiên từ chối quyền; có thể là token hết hiệu lực.

### Có thể gửi token qua cookie rồi đưa vào header không?

Có, với cấu hình **CookieCsrfTokenRepository** và SPA request handler phù hợp theo hướng dẫn Spring Security. Client đọc cookie CSRF được phép đọc rồi gửi một header như **X-XSRF-TOKEN**. Tuy nhiên, cần phân biệt raw token từ cookie với token được masked trong request attribute; không tự cấu hình raw-vs-masked một cách thiếu kiểm chứng.

Việc browser tự gửi cookie CSRF **mà client không chủ động đưa giá trị tương ứng vào header/form không đủ** cho một double-submit implementation đúng. Mục tiêu là buộc client cung cấp một giá trị mà trang attacker không thể tự nêu ra, đồng thời server kiểm tra nó theo chính sách đáng tin.

## 12. CSRF, CORS, SameSite và Bearer token có quan hệ ra sao?

| Cơ chế | Nó bảo vệ/định nghĩa điều gì? | Nó **không** thay thế |
| --- | --- | --- |
| **CSRF token** | Chống yêu cầu thay đổi trạng thái giả mạo trong bối cảnh có browser credentials tự gửi | Authentication, Authorization, input validation, XSS defense |
| **SameSite cookie** | Giới hạn một số trường hợp browser gửi cookie cross-site | CSRF token cho mọi tình huống |
| **CORS** | Quy tắc browser chia sẻ tài nguyên cross-origin và một số request được JS gửi | Xác thực người dùng hoặc phân quyền server-side |
| **HttpOnly** | Hạn chế JavaScript truy cập cookie | CSRF; browser vẫn có thể tự gửi cookie |
| **Secure** | Yêu cầu cookie được gửi qua HTTPS | Toàn bộ bảo mật ứng dụng |
| **Bearer token trong Authorization header** | Credential được client gửi chủ động theo HTTP request | Bảo vệ token khỏi XSS, replay hoặc lộ lọt |
| **JWT** | Định dạng token/claims | Quyết định CSRF bằng chính cái tên JWT |

### Dùng Bearer token có cần CSRF không?

**Không trả lời chỉ bằng nhãn "JWT" hay "stateless".** Hãy hỏi: **browser có tự đính kèm credential dùng để xác thực khi website khác tạo request không?**

- Browser web app dùng **session cookie**: cần đánh giá/bật CSRF; đây là mô hình demo.
- API chỉ dành cho **non-browser clients**, bearer token được gửi do client chủ động đặt vào header Authorization và không có cookie tự xác thực: threat model CSRF khác; có thể không cần CsrfFilter cho những đường được thiết kế như vậy.
- JWT đặt trong **cookie** tự gửi: vẫn cần đánh giá CSRF tương tự cookie authentication.
- HTTP Basic lưu trong browser: cũng có thể chịu rủi ro CSRF bởi browser tự gửi credentials trong một số tình huống.

Tắt CSRF có phạm vi phải dựa trên thiết kế credential và client thực tế, không chỉ vì API nhận JSON. Nếu chỉ một số endpoint thực sự stateless, Spring Security có thể dùng **requireCsrfProtectionMatcher** hoặc **ignoringRequestMatchers** có kiểm soát để điều chỉnh đúng phạm vi; nên test rằng các đường còn dùng session vẫn được bảo vệ.

### Origin/Referer có dùng được không?

Kiểm **Origin** hoặc **Referer** theo trusted origins và đặc điểm request có thể bổ sung phòng vệ. Tuy nhiên, header có thể thiếu trong những tình huống hợp lệ và có các điều kiện proxy/client khác nhau; không giả định mọi request đều có Referer chính xác. Với ứng dụng dựa trên session cookie, CSRF token thường là cơ chế chính để xác nhận request trong bối cảnh cần thiết; các kiểm tra origin là defense-in-depth phù hợp.

## 13. Phân biệt các loại HTTP 403

Một request trả **403** không nhất thiết chỉ vì CSRF. Tùy cấu hình và luồng xử lý:

| Tình huống | Status thường gặp | Vùng cần kiểm tra |
| --- | --- | --- |
| POST có cookie login nhưng thiếu CSRF token | **403** | CsrfFilter, expected token, actual header/parameter |
| POST có token sai, cùng session | **403** | Token kỳ vọng, session, request handler |
| POST có token cũ sau login/logout | **403** | Token rotation, CsrfAuthenticationStrategy/CsrfLogoutHandler |
| POST có CSRF đúng nhưng thiếu authority | **403** | AuthorizationManager, GrantedAuthority, resource ownership |
| GET protected chưa login với form login | Thường **302** đến /login | AuthenticationEntryPoint |
| GET protected chưa login với Basic/Bearer | Thường **401** | Authentication entry point/token |
| POST chưa login, đồng thời thiếu CSRF | Có thể **403** trước khi trả 302/401 | Thứ tự filter và việc request bị chặn ở CSRF layer |
| POST thành công sau mọi kiểm tra | **200/201/204...** tùy controller | Nghiệp vụ, response contract |

Khi phát hiện 403, hãy kiểm đủ: method, path, cookie/session hiện tại, token nhận từ endpoint nào, token được gửi ở header hay field, có login/logout xảy ra giữa hai request không, role/authority và quy tắc nghiệp vụ. Không “sửa 403” bằng cách tắt toàn bộ CSRF nếu nguyên nhân là client chưa gửi token.

### Bật log khi cần

Trong **application.properties** dành cho development:

~~~properties
logging.level.org.springframework.security=DEBUG
~~~

Không log nguyên CSRF token, Cookie header, session ID, password hoặc Authorization header lên hệ thống giám sát chung. Để xác minh logic, dùng **status + số lượng counter** thay vì in secret/token.

## 14. Những lỗi triển khai phổ biến

| Lỗi | Hậu quả | Cách sửa |
| --- | --- | --- |
| Dùng GET để xóa/cập nhật dữ liệu | GET mặc định không kiểm CSRF | Chuyển sang POST/PUT/PATCH/DELETE, áp dụng CSRF và quyền |
| Chỉ kiểm user đã login | Request giả mạo có session cookie hợp lệ vẫn đi qua | Yêu cầu CSRF token cho unsafe methods |
| Chỉ gửi cookie phiên trong POST | Không chứng minh request đến từ UI được phép | Gửi thêm token qua header/form field |
| Lấy token từ phiên A, gửi với cookie phiên B | Expected/actual không khớp | Giữ đúng cookie jar và lấy token cho phiên hiện tại |
| Dùng token trước login cho mọi request sau login | Token cũ có thể bị xóa trong lúc xác thực | Refresh token sau login |
| Lưu token trong URL | Dễ bị lộ qua logs, history, Referer | Đưa trong header hoặc body form |
| Bật CookieCsrfTokenRepository nhưng vẫn dùng request handler không phù hợp | Header raw token từ cookie không được resolve đúng | Cấu hình SPA theo docs và test raw/masked |
| Tắt BREACH protection không có lý do | Mất phòng vệ cho token được render | Giữ mặc định nếu không có nhu cầu đặc biệt |
| Cho phép mọi POST bằng csrf.ignoringRequestMatchers("/**") | Bỏ qua toàn bộ CSRF | Chỉ loại trừ endpoint thật sự không chịu rủi ro theo threat model |
| Nghĩ application/json tự chống CSRF | Có thể có edge cases hoặc endpoint cấu hình sai Content-Type | Đánh giá thực tế, giữ CSRF khi credentials tự gửi |
| Dùng CORS như cơ chế phân quyền | Server vẫn có thể xử lý request dù browser không đọc được kết quả | Thực thi Authentication/Authorization/CSRF |
| Nghĩ SameSite là giải pháp hoàn chỉnh | Phụ thuộc site, method, browser, cấu hình | Dùng defense-in-depth và token khi cần |
| Token đúng nhưng người dùng vẫn không được phép | CSRF không cấp quyền nghiệp vụ | Kiểm role/authority, owner, tenant |
| Test chỉ với .with(csrf()) | Không chứng minh đường từ chối hoạt động | Test thiếu token, token sai và không thay đổi dữ liệu |
| Không quản lý hết hạn phiên | Form cũ gửi token không hợp lệ, UX khó hiểu | Có cách refresh token và xử lý timeout thân thiện |
| Log CSRF token thật để debug | Tăng nguy cơ lộ giá trị bí mật | Log status/loại lỗi/trace ID không nhạy cảm |

## 15. Kiểm thử E2E cho ứng dụng thực tế

Ngoài MockMvc, khi review một endpoint nhạy cảm như **POST /transfer**, **DELETE /account**, **PUT /profile**, cần kiểm tra:

1. **Đăng nhập hợp lệ** và có HttpSession/cookie theo thiết kế.
2. **Form được render có CSRF field** hoặc JS lấy token từ endpoint chính thức.
3. **POST với token đúng và đúng quyền** được xử lý chính xác.
4. **POST không có token** bị chặn; dữ liệu trong database hoặc store không đổi.
5. **POST có token bị sửa** bị chặn; dữ liệu không đổi.
6. **POST có token phiên khác** bị chặn.
7. **POST với token cũ sau login/logout/session timeout** được xử lý theo chính sách rotation/refresh.
8. **POST với token đúng nhưng thiếu permission** vẫn bị từ chối ở authorization layer.
9. **GET** không vô tình thay đổi dữ liệu nhạy cảm.
10. **Cookie settings**: Secure, HttpOnly, SameSite, Domain/Path, HTTPS và proxy configuration.
11. **CORS** và cách client gửi credential khi frontend khác origin.
12. **Không có token/credential bị lộ trong logs, URLs hoặc analytics**.

Không cho test “CSRF pass” chỉ vì response có 200. Với nghiệp vụ tiền bạc hoặc tài khoản, phải test rằng **không có side effect** trong mọi trường hợp bị từ chối.

### Kiểm thử với những cấu hình khác

Nếu dùng **multiple SecurityFilterChain**, hãy xác nhận request khớp đúng chain chứa CSRF policy mong muốn. Một chain riêng cho API Bearer stateless có thể có chính sách khác với chain cho browser session; đừng để browser-authenticated POST rơi vào chain đã tắt CSRF theo giả định API-only.

Nếu dùng **Spring WebFlux**, dùng **CsrfWebFilter**, **ServerCsrfTokenRepository** và **ServerCsrfTokenRequestHandler** (không phải CsrfFilter và HttpServletRequest). Tư duy chọn safe/unsafe methods và kiểm tra expected/actual vẫn tương tự, nhưng code reactive cần được viết và test theo API/ Reactor context của WebFlux.

## 16. Bài tập tự đánh giá

1. CSRF là gì? Vì sao browser có thể vô tình gửi credential của một ứng dụng khác khi truy cập trang attacker?
2. CSRF token có phải session ID, password hoặc quyền ADMIN không?
3. Nêu vai trò riêng của **CsrfFilter**, **CsrfTokenRepository** và **CsrfTokenRequestHandler**.
4. Khi POST thiếu token, controller có được gọi trước khi Spring Security trả 403 không?
5. Vì sao request **GET** mặc định không cần CSRF? Điều gì xảy ra nếu developer lại dùng GET để xóa tài khoản?
6. Token CSRF lưu trong session khác gì với token gửi qua header?
7. Vì sao **CookieCsrfTokenRepository** cần được thiết kế cẩn thận khi client đọc raw cookie và Spring Security 6 bật XOR masking mặc định?
8. Token hiển thị khác nhau trên hai GET có nhất thiết chứng minh đó là hai phiên khác nhau không?
9. Một SPA đăng nhập xong nhưng POST lập tức bị 403 dù trước login đã lấy token. Bạn sẽ điều tra điều gì?
10. Vì sao **SameSite** và **CORS** không tự thay thế tất cả kiểm tra CSRF?
11. Nếu API dùng JWT đặt trong **cookie tự gửi**, CSRF còn đáng quan tâm không?
12. Trong MockMvc, làm sao xác minh POST thiếu token bị chặn **và counter vẫn giữ nguyên**?
13. Nếu POST có CSRF token hợp lệ nhưng user không có permission, server có bắt buộc cho phép không?
14. Với endpoint upload file, tại sao đặt CSRF token trong header có thể dễ xử lý hơn parse toàn bộ multipart body trước security check?
15. Khi triển khai nhiều server hoặc shared session store, cơ chế lấy expected CSRF token cần nhất quán theo request/session ra sao?

**Ghi nhớ:** CSRF token là một giá trị server/client đáng tin phải **được cung cấp chủ động trong request thay đổi trạng thái**. Trong Spring Security Servlet, **CsrfFilter** tải expected token qua **CsrfTokenRepository**, đọc actual token qua **CsrfTokenRequestHandler**, so sánh và từ chối request thiếu/sai **trước khi controller đổi dữ liệu**. Cần giữ CSRF cho các browser flows dùng credential tự gửi, xử lý token mới sau login/logout và kiểm thử cả đường bị chặn lẫn tác động tới dữ liệu.

## 17. Tài liệu tham khảo chính thức

- Spring Security 6.5 — CSRF for Servlet Applications: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security — Understanding CSRF protection (CSRF vs JSON/stateless/basic): https://docs.spring.io/spring-security/reference/features/exploits/csrf.html
- Spring Security 6.5 — Testing CSRF protection with MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/csrf.html
- Spring Security 6.5 — Exploit Protection Migrations, deferred CSRF và BREACH: https://docs.spring.io/spring-security/reference/6.5/migration/servlet/exploits.html
- Spring Security — CSRF for WebFlux: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
- OWASP Cross-Site Request Forgery Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
