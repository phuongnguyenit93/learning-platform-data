# Đối chiếu unit test với ít nhất một ca đi qua cấu hình tích hợp thực

## 1. Vì sao cần cả unit test và integration test?

Một unit test có thể chứng minh một lớp xử lý đúng khi nhận đầu vào đã biết. Ví dụ, policy cho phép người dùng có authority `REPORT_READ` đọc báo cáo và từ chối người không có quyền đó. Nhưng test riêng policy không chứng minh ứng dụng đã gắn policy vào đúng URL, filter chain đang được sử dụng, `AuthenticationProvider` được cấu hình với đúng `PasswordEncoder`, hay request HTTP thực sự đi qua các thành phần đó.

Ngược lại, integration test khởi động Spring context và gửi request qua `MockMvc` có thể kiểm tra nhiều thành phần cùng phối hợp: `SecurityFilterChain`, authentication filter, provider, `UserDetailsService`, `PasswordEncoder`, authorization rule và controller. Test này phát hiện lỗi wiring và cấu hình, nhưng thường chậm hơn và khó khoanh vùng nguyên nhân hơn unit test.

Trong mô-đun **SPRING_SECURITY_TESTING**, ta cần cả hai mức bằng chứng. Mô-đun kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng `spring-security-test` trên ứng dụng Servlet và Reactive; các công cụ như `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext` và JWT/OAuth2/OIDC giả lập hỗ trợ những mục tiêu khác nhau. Bài này dùng một API đọc báo cáo làm ví dụ xuyên suốt để so sánh unit test với ít nhất một ca đi qua cấu hình tích hợp thực.

Sau bài học, bạn có thể:

- Chọn đúng ranh giới cho unit test, component test và integration test.
- Viết unit test cho policy hoặc service mà không khởi động Spring context.
- Cấu hình một `SecurityFilterChain` thực với `DaoAuthenticationProvider` và `PasswordEncoder`.
- Dùng `MockMvc` gửi HTTP Basic credentials để kiểm tra request được cho phép, bị từ chối và chưa xác thực.
- Giải thích bằng chứng mà `@WithMockUser` cung cấp và những bước nó bỏ qua.
- Giảm thời gian chạy test bằng cách phân tầng bộ kiểm thử thay vì lặp lại mọi trường hợp ở tầng tích hợp.

## 2. Ba mức kiểm thử và bằng chứng tương ứng

Các tên unit, component và integration đôi khi được dùng khác nhau giữa các nhóm. Trong bài này, ta dùng cách phân biệt theo phạm vi phụ thuộc:

| Mức | Phạm vi chạy | Ví dụ Spring Security | Bằng chứng nhận được |
| --- | --- | --- | --- |
| Unit test | Một lớp hoặc một hàm, phụ thuộc ngoài được thay bằng fake/mock | Kiểm tra policy quyết định dựa trên `Authentication` | Logic riêng của lớp đúng với đầu vào đã cho |
| Component test | Một nhóm bean hoặc thành phần bảo mật được kiểm tra cùng nhau | `JwtAuthenticationConverter`, `DaoAuthenticationProvider` với encoder thật | Các thành phần trong phạm vi nhỏ phối hợp đúng |
| Integration test | Spring context và cấu hình thực của ứng dụng, gửi request qua filter chain | `@SpringBootTest` + `MockMvc` + `SecurityFilterChain` thật | Cấu hình, wiring, filter và response HTTP phối hợp đúng |

~~~mermaid
flowchart TD
    A["Unit test: policy / service"] --> B["Component test: provider / converter"]
    B --> C["Integration test: Spring context + filter chain"]
    C --> D["MockMvc / WebTestClient"]
    D --> E["HTTP status + body + headers"]
~~~

Không phải mọi test đều cần khởi động cả ứng dụng. Unit test phù hợp để kiểm tra nhiều tổ hợp đầu vào nhanh chóng. Integration test nên tập trung vào một số luồng đại diện có rủi ro cấu hình cao: credentials đúng, credentials sai, thiếu quyền và endpoint công khai.

Một test có tên `@SpringBootTest` chưa tự động chứng minh mọi thứ là “thực”. Nếu test thay `AuthenticationManager`, `JwtDecoder`, `SecurityFilterChain` hoặc handler bằng mock, nó không kiểm tra hành vi thật của thành phần đã thay thế. Hãy ghi rõ test đang dùng bean thật, bean giả lập hay một phần cấu hình được thay thế.

## 3. Kịch bản xuyên suốt: API đọc báo cáo

Giả sử ứng dụng có endpoint `GET /api/reports/{id}`. Quy tắc bảo mật:

- Tài khoản `lan` có authority `REPORT_READ`, được phép đọc báo cáo.
- Tài khoản `minh` có authority `REPORT_WRITE`, không có `REPORT_READ`, nên không được đọc endpoint này.
- Request anonymous phải xác thực trước khi đọc.

Ma trận kỳ vọng:

| Người gọi | Credentials | Authority | Kết quả |
| --- | --- | --- | --- |
| `lan` | Đúng | `REPORT_READ` | `200 OK` |
| `minh` | Đúng | `REPORT_WRITE` | `403 Forbidden` |
| `lan` | Sai password | Không tạo được Authentication thành công | `401 Unauthorized` với HTTP Basic |
| Anonymous | Không gửi credentials | Chưa xác thực | `401 Unauthorized` với HTTP Basic |

Ở đây, `401` và `403` giả định ứng dụng dùng HTTP Basic với entry point phù hợp. Form login có thể redirect; API tùy chỉnh có thể trả JSON. Điều quan trọng của bài test là phân biệt request không xác thực với request đã xác thực nhưng thiếu authority.

Controller tối giản:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ReportController {

    @GetMapping("/api/reports/{id}")
    ReportResponse getReport(@PathVariable String id) {
        return new ReportResponse(id, "Quarterly report");
    }

    record ReportResponse(String id, String title) {
    }
}
~~~

Controller chỉ mô phỏng response để bài học tập trung vào security. Trong ứng dụng thực, phần truy cập dữ liệu và xử lý nghiệp vụ có thể được kiểm thử riêng bằng unit test/service test.

## 4. Unit test: kiểm tra policy độc lập

Đầu tiên, tách quy tắc kiểm tra quyền thành một lớp thuần Java. Lớp này không cần Spring context, HTTP request hay MockMvc:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;

final class ReportReadPolicy {

    boolean allows(Authentication authentication) {
        if (authentication == null || !authentication.isAuthenticated()) {
            return false;
        }

        return authentication.getAuthorities().stream()
                .map(GrantedAuthority::getAuthority)
                .anyMatch("REPORT_READ"::equals);
    }
}
~~~

Unit test tạo `Authentication` trực tiếp:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;

import static org.assertj.core.api.Assertions.assertThat;

class ReportReadPolicyTest {

    private final ReportReadPolicy policy = new ReportReadPolicy();

    private Authentication user(String name, String... authorities) {
        return UsernamePasswordAuthenticationToken.authenticated(
                name,
                null,
                AuthorityUtils.createAuthorityList(authorities));
    }

    @Test
    void allowsUserWithReportReadAuthority() {
        assertThat(policy.allows(user("lan", "REPORT_READ"))).isTrue();
    }

    @Test
    void deniesUserWithDifferentAuthority() {
        assertThat(policy.allows(user("minh", "REPORT_WRITE"))).isFalse();
    }

    @Test
    void deniesAnonymousOrMissingAuthentication() {
        assertThat(policy.allows(null)).isFalse();
    }

    @Test
    void doesNotTreatSimilarAuthorityAsExactMatch() {
        assertThat(policy.allows(user("lan", "REPORT_READER"))).isFalse();
    }
}
~~~

Các test này nhanh và chỉ tập trung vào hợp đồng của `ReportReadPolicy`. Chúng không chứng minh rằng Spring Security gọi policy này cho `/api/reports/**`, không kiểm tra credentials, và cũng không chứng minh filter chain trả status HTTP nào.

Trong ứng dụng thực, nếu policy được dùng bởi một `AuthorizationManager` tùy chỉnh, hãy unit test cả adapter manager nếu nó có logic riêng. Nếu DSL dùng trực tiếp `hasAuthority("REPORT_READ")`, unit test policy là một quy tắc nghiệp vụ riêng; integration test bên dưới mới chứng minh DSL đang bảo vệ đúng endpoint.

## 5. Cấu hình tích hợp thực cho Servlet

Để integration test có ý nghĩa, cấu hình cần có bean thật cho encoder, user store, provider và filter chain. Ví dụ dưới đây dùng `InMemoryUserDetailsManager` để không phụ thuộc database; `DaoAuthenticationProvider` và `BCryptPasswordEncoder` vẫn là triển khai thật của Spring Security.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationProvider;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.InMemoryUserDetailsManager;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ReportSecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        return new InMemoryUserDetailsManager(
                User.withUsername("lan")
                        .password(encoder.encode("lan-password"))
                        .authorities("REPORT_READ")
                        .build(),
                User.withUsername("minh")
                        .password(encoder.encode("minh-password"))
                        .authorities("REPORT_WRITE")
                        .build());
    }

    @Bean
    AuthenticationProvider authenticationProvider(
            UserDetailsService users,
            PasswordEncoder encoder) {
        DaoAuthenticationProvider provider =
                new DaoAuthenticationProvider(users);
        provider.setPasswordEncoder(encoder);
        return provider;
    }

    @Bean
    SecurityFilterChain reportSecurityFilterChain(
            HttpSecurity http,
            AuthenticationProvider authenticationProvider)
            throws Exception {
        http.authenticationProvider(authenticationProvider);

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers(HttpMethod.GET, "/api/reports/**")
                    .hasAuthority("REPORT_READ")
                .anyRequest().authenticated());

        http.httpBasic(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Các điểm cần quan sát:

- `PasswordEncoder` mã hóa password lúc tạo user và xác minh password khi đăng nhập.
- `DaoAuthenticationProvider` dùng `UserDetailsService` để tìm tài khoản và encoder để kiểm tra credentials.
- `SecurityFilterChain` áp dụng rule cho HTTP GET `/api/reports/**`.
- HTTP Basic cho phép `MockMvc` gửi credentials qua header theo đúng cơ chế filter.

`InMemoryUserDetailsManager` ở đây là kho người dùng thật trong phạm vi test, nhưng không phải database production. Nếu ứng dụng dùng JDBC/JPA, hãy giữ repository/user service thực của ứng dụng hoặc dùng test database để kiểm tra wiring tương ứng.

Constructor `DaoAuthenticationProvider(UserDetailsService)` có trong các phiên bản Spring Security hiện đại. Với phiên bản cũ hơn, cách khởi tạo provider có thể khác; hãy điều chỉnh theo phiên bản dependency của dự án, nhưng vẫn giữ provider và encoder thật trong integration test.

## 6. Integration test: đi qua SecurityFilterChain bằng MockMvc

Test dưới đây khởi động Spring Boot context và dùng `MockMvc` để gửi HTTP Basic request. Không dùng `@WithMockUser`: request phải cung cấp credentials để `BasicAuthenticationFilter`, `AuthenticationManager` và provider thực hiện xác thực.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReportSecurityIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void readerWithValidPasswordCanReadReport() throws Exception {
        mockMvc.perform(get("/api/reports/42")
                        .with(httpBasic("lan", "lan-password")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.id").value("42"))
                .andExpect(jsonPath("$.title").value("Quarterly report"));
    }

    @Test
    void authenticatedWriterWithoutReadAuthorityGetsForbidden()
            throws Exception {
        mockMvc.perform(get("/api/reports/42")
                        .with(httpBasic("minh", "minh-password")))
                .andExpect(status().isForbidden());
    }

    @Test
    void invalidPasswordIsRejectedBeforeAuthorization() throws Exception {
        mockMvc.perform(get("/api/reports/42")
                        .with(httpBasic("lan", "wrong-password")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void anonymousRequestRequiresAuthentication() throws Exception {
        mockMvc.perform(get("/api/reports/42"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

Đây là integration test quan trọng nhất của bài. Nó chứng minh:

1. Credentials đúng được xử lý bởi cơ chế HTTP Basic.
2. `UserDetailsService` tìm được người dùng và `PasswordEncoder` xác minh password.
3. `AuthenticationProvider` tạo `Authentication` đã xác thực.
4. Rule `hasAuthority("REPORT_READ")` trong filter chain cho phép hoặc từ chối request.
5. Response HTTP và controller được thực thi theo kết quả bảo mật.

Các status `401` giả định entry point mặc định của HTTP Basic. Nếu ứng dụng cấu hình entry point JSON, test có thể bổ sung assertion về content type và body. Nếu controller trả response khác, điều chỉnh assertion thành hợp đồng API thực tế.

## 7. Đối chiếu hai bài test

| Khía cạnh | `ReportReadPolicyTest` | `ReportSecurityIntegrationTest` |
| --- | --- | --- |
| Khởi động Spring context | Không | Có |
| Gửi HTTP request | Không | Có, qua MockMvc |
| Chạy filter chain | Không | Có |
| Kiểm tra password | Không | Có |
| Dùng `UserDetailsService` thật | Không cần | Có |
| Kiểm tra `PasswordEncoder` | Không | Có |
| Kiểm tra rule URL trong DSL | Không | Có |
| Kiểm tra status/body HTTP | Không | Có |
| Tốc độ và khả năng khoanh vùng | Nhanh, tập trung | Chậm hơn, bao phủ nhiều tích hợp |

Một unit test xanh không thay thế integration test. Nếu rule trong `SecurityFilterChain` bị xóa hoặc matcher bị đổi sang URL khác, `ReportReadPolicyTest` vẫn xanh vì nó không chạy cấu hình đó. Ngược lại, nếu integration test thất bại, nguyên nhân có thể nằm ở nhiều lớp; unit test giúp khoanh vùng policy hoặc service nhanh hơn.

## 8. @WithMockUser: khi nào nên dùng?

`@WithMockUser` đặt một `Authentication` giả lập vào `SecurityContext` cho test. Ví dụ:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ReportAuthorizationWithMockUserTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    @WithMockUser(username = "lan", authorities = "REPORT_READ")
    void readerCanAccessReport() throws Exception {
        mockMvc.perform(get("/api/reports/42"))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "minh", authorities = "REPORT_WRITE")
    void writerCannotReadReport() throws Exception {
        mockMvc.perform(get("/api/reports/42"))
                .andExpect(status().isForbidden());
    }
}
~~~

Các test này vẫn đi qua `MockMvc` và filter chain, nên hữu ích để kiểm tra authorization rule. Tuy nhiên, danh tính và authority đã được tạo sẵn; test bỏ qua:

- Đọc username từ `UserDetailsService`.
- Kiểm tra password bằng `PasswordEncoder`.
- `AuthenticationProvider` xác thực credentials.
- Chuyển đổi claims/token thật thành `Authentication`.

Do đó, hãy dùng `@WithMockUser` cho nhiều tổ hợp quyền nhanh, còn giữ một số ca HTTP Basic/form login hoặc bearer token đi qua cơ chế xác thực thực để kiểm tra wiring.

## 9. Khi nào dùng @WebMvcTest thay cho @SpringBootTest?

`@WebMvcTest` tạo một MVC slice, chỉ nạp một phần bean web. Nó phù hợp để kiểm tra controller, MVC binding, validation và một phần cấu hình web khi import security config rõ ràng. Nhưng slice test có thể thiếu service, provider, decoder hoặc bean cấu hình cần thiết; nhiều nhóm thay chúng bằng mock.

Nếu mục tiêu là kiểm tra controller cùng authorization filter chain nhưng không cần toàn bộ ứng dụng, có thể dùng `@WebMvcTest` và import `SecurityFilterChain` cùng các bean cần thiết. Cần xác nhận filter chain thực sự được bật trong slice, không bị `@AutoConfigureMockMvc(addFilters = false)` hoặc cấu hình test vô hiệu hóa.

Nếu mục tiêu là chứng minh `UserDetailsService`, `PasswordEncoder`, `AuthenticationProvider` và `SecurityFilterChain` của ứng dụng phối hợp thật, `@SpringBootTest` thường rõ ràng hơn. Chi phí khởi động context cao hơn nên chỉ dùng cho số lượng luồng đại diện.

## 10. Một test tích hợp không nhất thiết phải dùng database production

Từ “cấu hình tích hợp thực” nghĩa là dùng các thành phần và wiring thực mà test muốn kiểm tra; không có nghĩa phải kết nối database production hoặc Identity Provider bên ngoài.

| Phụ thuộc | Lựa chọn kiểm thử |
| --- | --- |
| `UserDetailsService` | `InMemoryUserDetailsManager`, repository thật với test database hoặc test fixture |
| `PasswordEncoder` | Encoder thật như BCrypt với test password |
| `AuthenticationProvider` | Provider thật, không mock |
| `SecurityFilterChain` | Bean thật của ứng dụng |
| `JwtDecoder` | Decoder thật với test key/JWK hoặc decoder stub nếu chỉ kiểm tra wiring sau decode |
| External OAuth2/OIDC provider | Mock server hoặc test provider; không gọi tài khoản production |
| Database | Testcontainers, embedded database hoặc repository test phù hợp |

Nếu dùng mock cho một phụ thuộc, hãy mô tả rõ giới hạn. Ví dụ, `JwtDecoder` mock giúp chứng minh bearer filter gọi converter và authorization rule, nhưng không chứng minh chữ ký JWT thật được xác minh. Một test decoder riêng cần xác minh issuer, audience, thời hạn và chữ ký theo cấu hình.

## 11. Reactive: đối chiếu unit test và WebTestClient integration test

Với WebFlux, cùng nguyên tắc áp dụng nhưng stack khác:

- Unit test policy/service vẫn có thể chạy thuần Java.
- Integration test cần `SecurityWebFilterChain` thật và `WebTestClient`.
- Dùng `mockUser(...)` để kiểm tra authorization với danh tính dựng sẵn.
- Dùng cơ chế xác thực Reactive thật nếu cần kiểm tra password/token và converter.

Ví dụ test authorization Reactive với user giả lập:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveReportAuthorizationTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void readerCanAccessReport() {
        webTestClient.mutateWith(mockUser("lan")
                        .authorities(new SimpleGrantedAuthority("REPORT_READ")))
                .get()
                .uri("/api/reports/42")
                .exchange()
                .expectStatus().isOk();
    }

    @Test
    void writerCannotAccessReport() {
        webTestClient.mutateWith(mockUser("minh")
                        .authorities(new SimpleGrantedAuthority("REPORT_WRITE")))
                .get()
                .uri("/api/reports/42")
                .exchange()
                .expectStatus().isForbidden();
    }
}
~~~

Đoạn code minh họa việc tạo authorities tùy chỉnh cho `mockUser`; cú pháp builder có thể khác giữa các phiên bản Spring Security. Dùng overload nhận `GrantedAuthority` theo API phiên bản dự án. Những test này kiểm tra authorization Reactive; chúng không chứng minh password hoặc bearer token thật được xác minh.

Khi cần kiểm tra xác thực Reactive thật, dùng `WebTestClient` gửi credentials qua endpoint/cơ chế đăng nhập đã cấu hình, hoặc gửi bearer token qua Resource Server với decoder phù hợp. Không dùng `MockMvc` để kiểm tra `SecurityWebFilterChain`.

## 12. Tổ chức bộ kiểm thử hiệu quả

Một bộ test cân bằng có thể được tổ chức như sau:

| Nhóm | Ví dụ số lượng | Mục tiêu |
| --- | ---: | --- |
| Unit test policy/service | Nhiều | Bao phủ biên logic, authority, dữ liệu sai và nhánh nghiệp vụ |
| Component test provider/encoder/converter | Vừa phải | Xác minh tương tác bảo mật chuyên biệt |
| Integration test filter chain | Một số luồng đại diện | Chứng minh cấu hình và wiring thực |
| End-to-end với hệ thống ngoài | Ít, chọn lọc | Xác minh tích hợp thật với database/IdP/gateway khi cần |

Không cần nhân bản mọi tổ hợp authority ở cả bốn tầng. Ví dụ, có thể kiểm tra 10 tổ hợp quyền bằng unit test policy, rồi chỉ giữ ba ca integration quan trọng: quyền đúng, thiếu quyền và credentials sai. Nếu thay đổi cấu hình matcher hoặc provider, mở rộng integration test đúng phạm vi bị ảnh hưởng.

### Đặt tên test theo bằng chứng

Tên test nên nói rõ điều kiện và kết quả:

- `allowsUserWithReportReadAuthority`
- `deniesWriterWithoutReportReadAuthority`
- `readerWithValidPasswordCanReadReport`
- `authenticatedWriterWithoutReadAuthorityGetsForbidden`
- `invalidPasswordIsRejectedBeforeAuthorization`

Tránh tên chung như `securityWorks()` vì không cho reviewer biết test chứng minh điều gì.

### Dùng dữ liệu test ổn định

Hash BCrypt có salt ngẫu nhiên; không assert hash tạo ra bằng một chuỗi cố định. Tạo hash bằng encoder trong fixture và kiểm tra hành vi `matches(...)`. Nếu integration test dùng password encoder thật, dùng password giả dành riêng cho test và không ghi credentials vào log.

### Kiểm tra đúng response

Một test status `403` có thể được tạo bởi authorization, CSRF hoặc handler khác. Khi cần chứng minh rule quyền, hãy dùng GET hoặc cung cấp CSRF token hợp lệ cho request thay đổi trạng thái. Khi test chưa xác thực, kiểm tra entry point và status `401` theo cơ chế đăng nhập. Khi test người dùng thiếu quyền, bảo đảm `Authentication` đã xác thực.

## 13. Những lỗi thường gặp

**Chỉ viết unit test rồi kết luận filter chain đúng.** Unit test không chạy matcher, filter hoặc cấu hình provider. Bổ sung ít nhất một integration test qua `MockMvc` hoặc `WebTestClient`.

**Chỉ viết integration test cho mọi nhánh.** Test context khởi động chậm và lỗi khó khoanh vùng. Dùng unit test cho logic thuần và component test cho thành phần chuyên biệt.

**Dùng @WithMockUser để kiểm tra PasswordEncoder.** Annotation bỏ qua xác thực credentials. Dùng HTTP Basic/form login với provider và encoder thật.

**Mock SecurityFilterChain trong test cần xác minh cấu hình.** Mock filter chain loại bỏ chính thành phần cần kiểm tra. Giữ bean thật và gửi request qua filter.

**Tắt filter trong MockMvc.** `@AutoConfigureMockMvc(addFilters = false)` làm request bỏ qua Spring Security filter chain. Chỉ dùng khi chủ đích test MVC không liên quan bảo mật; không dùng trong integration test bảo mật.

**Dùng @WebMvcTest nhưng quên import security config.** Slice test có thể không nạp bean cấu hình thật. Xác minh bean chain hiện diện hoặc chuyển sang `@SpringBootTest` nếu mục tiêu là toàn bộ wiring.

**Dùng JWT mock để kết luận chữ ký hợp lệ.** `jwt()` tạo authentication giả lập. Dùng decoder/validator thật hoặc test riêng để chứng minh xác minh token.

**Nhầm 401 và 403.** `401` là chưa xác thực/credentials không hợp lệ trong cấu hình Basic; `403` là đã xác thực nhưng thiếu quyền. Hãy kiểm tra trạng thái authentication trước khi kết luận.

**Không gửi CSRF token cho POST trong test authorization.** Request có thể bị chặn trước khi đến rule quyền. Gửi CSRF hợp lệ nếu muốn kiểm tra authorization của POST.

**Integration test phụ thuộc hệ thống ngoài không ổn định.** Không cần gọi production IdP hoặc database dùng chung để chứng minh filter chain. Dùng test fixture, test database hoặc mock server có kiểm soát và mô tả giới hạn.

## 14. Bài thực hành

1. Viết `ReportReadPolicyTest` với ít nhất bốn trường hợp: có quyền, thiếu quyền, authentication null và authority gần giống nhưng không khớp.
2. Cấu hình `SecurityFilterChain` với HTTP Basic, `DaoAuthenticationProvider`, `UserDetailsService` và BCrypt thật. Viết `MockMvc` integration test cho user có quyền đọc.
3. Thêm user đã xác thực nhưng chỉ có `REPORT_WRITE`; xác minh request đọc báo cáo nhận `403`.
4. Gửi password sai và request anonymous; xác minh chúng nhận `401` trong cấu hình HTTP Basic.
5. Thay một test `httpBasic(...)` bằng `@WithMockUser`. Ghi rõ các bước xác thực nào bị bỏ qua và test nào nên giữ lại để chứng minh provider hoạt động.
6. Thử thay matcher `/api/reports/**` thành một URL khác. Quan sát unit test policy vẫn xanh trong khi integration test phát hiện lỗi cấu hình.
7. Với WebFlux, viết unit test cho policy và một test `WebTestClient` qua `SecurityWebFilterChain`. So sánh bằng chứng với test `mockUser(...)`.

Một chiến lược kiểm thử Spring Security vững chắc dùng **unit test để chứng minh logic riêng, component test để chứng minh thành phần bảo mật và integration test để chứng minh cấu hình thật hoạt động qua HTTP**. Một số ca tích hợp đại diện, kết hợp nhiều unit test nhanh, tạo bằng chứng rõ ràng mà vẫn giữ bộ test dễ bảo trì.
