# Kiểm thử HTTP: `csrf()` và phân biệt CSRF với quy tắc quyền

Trong Spring Security cho ứng dụng **Servlet / Spring MVC**, một yêu cầu `POST` có thể nhận **HTTP 403 Forbidden** dù người dùng đã đăng nhập và có đúng role. Nguyên nhân có thể là **CSRF token thiếu hoặc sai**, **quy tắc phân quyền từ chối**, hoặc một cơ chế khác. Vì vậy, một bài kiểm thử chỉ so sánh mã trạng thái `403` chưa đủ để khẳng định phần phân quyền đang hoạt động đúng.

Bài này tập trung vào `csrf()` trong **Spring Security Test + MockMvc**, cách kết hợp nó với người dùng giả lập, và cách thiết kế ca kiểm thử để xác định rõ tầng nào chặn request.

## 1. Hai câu hỏi bảo mật độc lập

**CSRF (Cross-Site Request Forgery)** hỏi: *Yêu cầu thay đổi trạng thái có mang bằng chứng chống giả mạo phù hợp với phiên/ngữ cảnh hiện tại không?* Trình duyệt có thể tự gửi cookie phiên tới website đích khi bị trang khác dụ gửi yêu cầu; token CSRF là một biện pháp để website kiểm tra ý định của yêu cầu. CSRF không quyết định người dùng được phép chuyển tiền hay sửa tài nguyên nào.

**Authorization (phân quyền)** hỏi: *Người dùng đã được xác thực có đủ quyền truy cập hành động/tài nguyên này không?* Quyết định thường dựa trên `Authentication`, role/authority, HTTP method, đường dẫn, hoặc kiểm tra ở tầng method và dữ liệu. Quy tắc `hasRole("ADMIN")` không tự xác minh CSRF token.

**Authentication (xác thực)** là câu hỏi thứ ba: *Người gửi là ai?* Trong MockMvc, `user("alice").roles("ADMIN")` tạo người dùng giả lập cho request. Nó không tạo CSRF token; ngược lại, `.with(csrf())` không đăng nhập hay cấp thêm role.

| Khía cạnh | Bảo vệ CSRF | Phân quyền HTTP |
| --- | --- | --- |
| Cấu hình tiêu biểu | `http.csrf(...)` / mặc định được bật | `http.authorizeHttpRequests(...)` |
| Câu hỏi cần trả lời | Request cần token hợp lệ và đã cung cấp đúng chưa? | Principal có đúng quyền với request chưa? |
| Chịu ảnh hưởng bởi | HTTP method, `RequestMatcher` CSRF, token repository, token hiện diện/hợp lệ | HTTP method, URL, role/authority, rule order, `Authentication` |
| Dụng cụ MockMvc | `.with(csrf())`, `.with(csrf().asHeader())`, `.with(csrf().useInvalidToken())` | `.with(user(...))`, `@WithMockUser`, các assertion trạng thái |
| Khi bị từ chối | Thường là `403` | Có thể `403` khi đã xác thực nhưng thiếu quyền; yêu cầu chưa xác thực có thể là `401`, redirect đăng nhập hoặc kết quả khác tùy cấu hình |

**Không suy ra nguyên nhân chỉ từ `403`.** Nếu không cấp CSRF token cho một `POST`, request có thể bị `CsrfFilter` từ chối trước khi phép kiểm tra role được thực hiện. Một test “USER phải nhận 403 khi gọi endpoint ADMIN” mà quên `.with(csrf())` có thể vượt qua dù quy tắc quyền bị cấu hình sai.

## 2. `csrf()` trong MockMvc thực sự làm gì?

Nhập tĩnh helper từ thư viện `spring-security-test`:

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
```

Cách dùng phổ biến:

```java
mvc.perform(post("/transfers").with(csrf()));
mvc.perform(post("/transfers").with(csrf().asHeader()));
mvc.perform(post("/transfers").with(csrf().useInvalidToken()));
```

- `.with(csrf())`: gắn **CSRF token hợp lệ** vào request giả lập, theo mặc định qua request parameter. Nó giúp request vượt qua bước kiểm tra CSRF để ta có thể kiểm chứng lớp phân quyền hoặc hành vi controller.
- `.with(csrf().asHeader())`: đưa token hợp lệ vào HTTP header; hữu ích khi client gửi token bằng header thay cho form parameter.
- `.with(csrf().useInvalidToken())`: cố tình gắn token không hợp lệ để kiểm tra request bị từ chối.
- Không `.with(csrf())`: với request mà cấu hình CSRF yêu cầu token, request sẽ thiếu token; đây là ca thử riêng để xác nhận CSRF đang được thực thi.

Đây là helper **của request trong bài test**, khác với phương thức cấu hình `HttpSecurity#csrf(...)`. Helper không bật/tắt tính năng CSRF toàn hệ thống, không tự xác thực người dùng và không làm thay đổi `authorizeHttpRequests`.

Theo cấu hình Servlet mặc định, Spring Security áp dụng CSRF cho các HTTP method **không được xem là an toàn**, điển hình `POST`, `PUT`, `PATCH`, `DELETE`. Những method `GET`, `HEAD`, `OPTIONS`, `TRACE` không bị CSRF chặn theo matcher mặc định; ứng dụng phải giữ đúng nguyên tắc rằng các method an toàn không làm thay đổi trạng thái có ý nghĩa. Matcher tùy biến có thể làm tập request cần CSRF khác đi.

Token thông thường được lưu bằng `HttpSessionCsrfTokenRepository`; có thể thay bằng `CookieCsrfTokenRepository` hoặc repository khác. Việc nhận token từ parameter/header và cách lưu token phụ thuộc cấu hình thực tế. Helper MockMvc mô phỏng request hợp lệ trong test; nó **không** thay thế kiểm thử toàn bộ luồng trình duyệt lấy token, gửi cookie và làm mới token sau đăng nhập/đăng xuất.

## 3. Ví dụ hoàn chỉnh: CSRF và role ADMIN trong cùng một test

Giả sử chính sách nghiệp vụ như sau:

- `POST /transfers` và `GET /transfers` chỉ dành cho role `ADMIN`.
- `POST /public-submit` cho phép truy cập không cần đăng nhập bằng `permitAll()`, nhưng **vẫn cần CSRF token** theo cấu hình mặc định.
- Các endpoint còn lại bị `denyAll()`.

Ví dụ dành cho **Java 17+, Spring Boot 3.x, Spring Security 6.x, JUnit Jupiter**. Trong một dự án Spring Boot Gradle đã quản lý phiên bản dependency bằng Spring Boot BOM, cần các dependency sau:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

Tạo file `src/test/java/demo/CsrfVsAuthorizationTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(classes = CsrfVsAuthorizationTest.TestApp.class)
@AutoConfigureMockMvc
class CsrfVsAuthorizationTest {

    @Autowired
    MockMvc mvc;

    @Test
    void adminWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/transfers")
                .with(user("alice").roles("ADMIN")))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminWithInvalidCsrfIsForbidden() throws Exception {
        mvc.perform(post("/transfers")
                .with(user("alice").roles("ADMIN"))
                .with(csrf().useInvalidToken()))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminWithValidCsrfCanCreate() throws Exception {
        mvc.perform(post("/transfers")
                .with(user("alice").roles("ADMIN"))
                .with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("created"));
    }

    @Test
    void adminWithHeaderCsrfCanCreate() throws Exception {
        mvc.perform(post("/transfers")
                .with(user("alice").roles("ADMIN"))
                .with(csrf().asHeader()))
            .andExpect(status().isOk())
            .andExpect(content().string("created"));
    }

    @Test
    void userWithValidCsrfIsStillForbidden() throws Exception {
        mvc.perform(post("/transfers")
                .with(user("bob").roles("USER"))
                .with(csrf()))
            .andExpect(status().isForbidden());
    }

    @Test
    void adminGetWithoutCsrfIsOk() throws Exception {
        mvc.perform(get("/transfers")
                .with(user("alice").roles("ADMIN")))
            .andExpect(status().isOk())
            .andExpect(content().string("listed"));
    }

    @Test
    void userGetWithoutCsrfIsForbiddenByAuthorization() throws Exception {
        mvc.perform(get("/transfers")
                .with(user("bob").roles("USER")))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousPublicPostWithoutCsrfIsForbidden() throws Exception {
        mvc.perform(post("/public-submit"))
            .andExpect(status().isForbidden());
    }

    @Test
    void anonymousPublicPostWithCsrfIsOk() throws Exception {
        mvc.perform(post("/public-submit").with(csrf()))
            .andExpect(status().isOk())
            .andExpect(content().string("public-accepted"));
    }

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import({SecurityConfig.class, TestController.class})
    static class TestApp {
    }

    @Configuration(proxyBeanMethods = false)
    static class SecurityConfig {
        @Bean
        SecurityFilterChain securityFilterChain(HttpSecurity http)
                throws Exception {
            http
                .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers(HttpMethod.POST, "/public-submit")
                        .permitAll()
                    .requestMatchers("/transfers").hasRole("ADMIN")
                    .anyRequest().denyAll()
                )
                .csrf(Customizer.withDefaults());

            return http.build();
        }
    }

    @RestController
    static class TestController {
        @GetMapping("/transfers")
        String listTransfers() {
            return "listed";
        }

        @PostMapping("/transfers")
        String createTransfer() {
            return "created";
        }

        @PostMapping("/public-submit")
        String submit() {
            return "public-accepted";
        }
    }
}
```

Chạy trong dự án Gradle đã cấu hình Java 17 và JUnit Platform:

```bash
./gradlew test --tests demo.CsrfVsAuthorizationTest
```

Trên Windows có thể dùng `.\gradlew.bat test --tests demo.CsrfVsAuthorizationTest`. Kỳ vọng **cả 9 test đạt** với các mã HTTP đã assert; ví dụ này không tạo kết nối mạng, database hay chuyển tiền thật. Các class cấu hình/controller nằm ngay trong test để mô tả độc lập; khi kiểm thử dự án thực tế, thường thay bằng `SecurityFilterChain` và controller của chính ứng dụng.

### Đọc kết quả đúng theo từng lớp

| Ca thử | Người dùng | CSRF | Kết quả kỳ vọng | Điều chứng minh trong cấu hình ví dụ |
| --- | --- | --- | --- | --- |
| `POST /transfers` | ADMIN | Thiếu | `403` | Đúng role vẫn bị CSRF chặn |
| `POST /transfers` | ADMIN | Sai | `403` | Token giả không được chấp nhận |
| `POST /transfers` | ADMIN | Hợp lệ | `200` | Token hợp lệ **và** đủ quyền |
| `POST /transfers` qua header | ADMIN | Hợp lệ | `200` | Đường gửi token bằng header hoạt động |
| `POST /transfers` | USER | Hợp lệ | `403` | CSRF đã thỏa; chính sách role tiếp tục từ chối |
| `GET /transfers` | ADMIN | Không gửi | `200` | GET mặc định không cần CSRF, role đúng |
| `GET /transfers` | USER | Không gửi | `403` | Không có yêu cầu CSRF, nhưng thiếu quyền |
| `POST /public-submit` | Ẩn danh | Thiếu | `403` | `permitAll()` **không** miễn CSRF |
| `POST /public-submit` | Ẩn danh | Hợp lệ | `200` | Public endpoint không yêu cầu login, vẫn cần token |

Điểm mấu chốt là các cặp test có **chỉ một biến thay đổi**. Ví dụ cùng `POST /transfers` và cùng `ADMIN`, thay token thiếu → token hợp lệ thì kết quả `403` → `200`. Giữ token hợp lệ, thay `ADMIN` → `USER` thì `200` → `403`. Đây là bằng chứng rõ hơn nhiều so với một test `isForbidden()` riêng lẻ.

## 4. Vì sao `403` không đủ để kết luận nguyên nhân?

Với cấu hình ví dụ, luồng đơn giản hóa của một request `POST /transfers` là:

```text
MockMvc POST /transfers
       |
       v
Spring Security filter chain
       |
       +--> CsrfFilter: request có cần CSRF?
       |        |
       |        +--> Có, nhưng token thiếu/sai --> 403 (dừng)
       |        |
       |        +--> Có, token hợp lệ -------+
       |                                   |
       v                                   v
Xác thực / SecurityContext        AuthorizationFilter
                                           |
                              +------------+-------------+
                              |                          |
                         role ADMIN                    role USER
                              |                          |
                             cho qua                    403
                              |
                       MVC controller
                              |
                             200
```

Sơ đồ chỉ diễn đạt các quyết định liên quan bài học, không phải toàn bộ thứ tự filter trong mọi cấu hình. Đặc biệt, kiểm soát ở mức method như `@PreAuthorize` hoặc logic nghiệp vụ sau controller vẫn có thể từ chối dù request đã qua lớp quyền URL.

**Cách viết test phân quyền đáng tin cậy:** cấp `.with(csrf())` cho request unsafe trước, rồi thay đổi đúng biến đang kiểm thử (role, authority, người dùng, URL, HTTP method). **Cách viết test CSRF đáng tin cậy:** giữ nguyên người dùng đủ quyền và URL, rồi thay token giữa thiếu, sai và hợp lệ. Với endpoint `permitAll()` cũng nên có cặp thiếu token/hợp lệ nếu CSRF vẫn áp dụng.

Với request ẩn danh ở endpoint đòi quyền, đừng mặc định kết quả luôn là `403`: cơ chế entry point có thể trả `401 Unauthorized` (ví dụ HTTP Basic), `302` tới trang đăng nhập (form login), hoặc `403` theo cấu hình. Hai cơ chế cần được kiểm thử theo chính xác security chain hiện tại.

## 5. Dùng `@WithMockUser` hoặc `user()` như thế nào?

Trong ví dụ, `.with(user("alice").roles("ADMIN"))` chỉ áp dụng cho **một request**, giúp kiểm soát rõ người dùng ở từng phép thử. Thư viện `spring-security-test` cũng hỗ trợ annotation:

```java
@WithMockUser(roles = "ADMIN")
@Test
void adminMayPostWithValidCsrf() throws Exception {
    mvc.perform(post("/transfers").with(csrf()))
        .andExpect(status().isOk());
}
```

Đoạn trên là **minh họa trích từ ngữ cảnh test đã có `mvc` và endpoint**, cần thêm import `org.springframework.security.test.context.support.WithMockUser`; nó không phải một class độc lập. Annotation thiết lập user cho cả test method, nhưng **không tự gắn CSRF token** cho `POST`.

Về role, `.roles("ADMIN")` và `@WithMockUser(roles = "ADMIN")` tạo authority `ROLE_ADMIN` theo quy ước mặc định; `.hasRole("ADMIN")` cũng kiểm tra `ROLE_ADMIN`. Nếu dùng `.authorities("ADMIN")`, đó là authority literal `ADMIN`, khác với `ROLE_ADMIN`. Đừng chẩn đoán nhầm một `403` do sai tiền tố role thành lỗi CSRF.

## 6. Chẩn đoán khi MockMvc trả `403` ngoài dự kiến

1. **Xác định request:** HTTP method, URL thực tế, `SecurityFilterChain` khớp request, bộ filter có được áp dụng trong test hay không. `GET` và `POST` trên cùng URL có thể có quy tắc khác nhau.
2. **Tách CSRF ra trước:** với `POST`/`PUT`/`PATCH`/`DELETE`, chạy một phép thử có `.with(csrf())` và một phép thử thiếu token. Nếu cấu hình dùng repository/handler riêng, kiểm tra cách test cung cấp token tương ứng. Đừng dùng `csrf()` một cách máy móc khi ứng dụng cố tình có matcher ngoại lệ.
3. **Giữ token hợp lệ và kiểm tra quyền:** truyền `user(...).roles(...)` hoặc `@WithMockUser`, so khớp `hasRole`, `hasAuthority`, thứ tự các `requestMatchers`, rule `denyAll`, và các kiểm tra method security.
4. **Xem nguồn từ chối:** bật log `org.springframework.security=DEBUG` (khi cần có thể dùng `TRACE` trong môi trường test), kiểm tra thông tin `MissingCsrfTokenException`, `InvalidCsrfTokenException` hoặc quyết định access denied. Không suy luận duy nhất từ status.
5. **Xác minh kiểm thử đang chạy với security filters thật:** `@SpringBootTest` kết hợp `@AutoConfigureMockMvc` thường tự đăng ký filter. Nếu tạo MockMvc thủ công từ context, tích hợp `.apply(springSecurity())`. `MockMvcBuilders.standaloneSetup(...)` không tự bảo đảm chạy security chain ứng dụng. Tránh `@AutoConfigureMockMvc(addFilters = false)` khi mục tiêu là kiểm thử CSRF/authorization.
6. **Đối chiếu hành vi controller:** token hợp lệ và role đúng chỉ cho request đi qua các bước bảo mật trên; validation, exception handler, `@PreAuthorize` hoặc logic nghiệp vụ vẫn có thể trả lỗi khác. Không ép mọi bài test thành `200` nếu endpoint thực tế có đáp ứng khác.

Một cách đọc nhanh:

```text
POST + ADMIN + không có csrf()  -> 403
POST + ADMIN + có csrf()        -> 200
=> Đã cô lập được ảnh hưởng của CSRF trong ca này.

POST + ADMIN + có csrf()        -> 200
POST + USER  + có csrf()        -> 403
=> Đã cô lập được tác động của quy tắc role trong ca này.
```

Trong dự án thực tế, hai dấu suy ra ở trên chỉ hợp lệ khi giữ các điều kiện khác ổn định và đã biết response từ controller không tự đổi vì nguyên nhân khác.

## 7. Những ngộ nhận và giới hạn cần nhớ

**`permitAll()` không đồng nghĩa `csrf().disable()`.** Cấp quyền public là một quyết định authorization; CSRF vẫn kiểm tra các request unsafe nằm trong phạm vi bảo vệ. Test `POST /public-submit` ở trên minh họa điều này.

**Thêm `.with(csrf())` không phải “sửa lỗi 403” trong production.** Đây là cách cung cấp token hợp lệ cho request giả lập trong test. Ứng dụng thật phải cấp token cho client và gửi token trở lại đúng cách; đừng bỏ CSRF chỉ để test xanh.

**Không tắt CSRF hàng loạt để đơn giản hóa test.** Cấu hình như `http.csrf(csrf -> csrf.disable())` làm thay đổi cơ chế bảo vệ cần kiểm tra. Nếu một endpoint thật sự cần loại trừ CSRF, hãy thiết kế phạm vi matcher cụ thể dựa trên loại client và nguồn credential, rồi thêm test riêng xác nhận đúng phạm vi đó.

**“REST/stateless/JWT” không tự động giải quyết vấn đề CSRF.** Rủi ro phụ thuộc việc trình duyệt có tự gắn credential (cookie phiên, cookie chứa token, HTTP auth, v.v.) khi gửi request hay không. API chỉ chấp nhận Bearer token được JavaScript/chương trình chủ động đặt trong `Authorization` header có mô hình rủi ro khác; phải đánh giá cách client thực sự xác thực trước khi quyết định miễn CSRF.

**`csrf().asHeader()` không chứng minh mọi frontend tích hợp đúng.** Header thực, tên cookie, SameSite, CORS, token sau đăng nhập/đăng xuất, session hết hạn và việc browser gửi credential cần kiểm thử tích hợp thích hợp. `MockMvc` chạy trong môi trường giả lập Servlet, hữu ích để kiểm chứng quy tắc server nhưng không mô phỏng đầy đủ trình duyệt.

**Không dùng status của request thiếu token để “chứng minh” authorization.** Một phép thử phân quyền âm tính nên cấp token hợp lệ trước để loại trừ nhánh CSRF, đồng thời có phép thử dương tính với cùng endpoint và principal được phép.

## 8. Checklist cho mỗi endpoint ghi dữ liệu

- [ ] Xác nhận HTTP method và security chain đang áp dụng.
- [ ] Có test người dùng **đủ quyền + CSRF hợp lệ** đạt kết quả thành công mong đợi.
- [ ] Có test cùng người dùng **thiếu CSRF** bị chặn khi CSRF bắt buộc.
- [ ] Có test cùng người dùng **token CSRF sai** bị chặn.
- [ ] Có test người dùng **thiếu quyền + CSRF hợp lệ** bị từ chối theo chính sách.
- [ ] Nếu endpoint là `permitAll()`, xác nhận rõ CSRF vẫn cần hay đã loại trừ có chủ đích.
- [ ] Nếu dùng form/header/cookie riêng, có test cho đúng cách client thực sự gửi token.
- [ ] MockMvc thực sự chạy Spring Security filters; không vô tình tắt filter trong cấu hình test.

## Tài liệu tham khảo chính thức

- [Spring Security — Testing with CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Security — Cross-Site Request Forgery](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Security — Setting Up MockMvc and Spring Security](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html)
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
