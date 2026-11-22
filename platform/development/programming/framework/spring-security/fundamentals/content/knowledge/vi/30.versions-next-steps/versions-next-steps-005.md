# Đọc hướng dẫn di chuyển và kiểm thử thay đổi hành vi mặc định trong Spring Security

## Mục tiêu học tập

Sau bài này, bạn có thể: (1) chọn đúng tài liệu migration theo phiên bản nguồn và đích; (2) phân biệt thay đổi API, cấu hình và **hành vi mặc định**; (3) chuyển mỗi thay đổi liên quan thành giả thuyết và kiểm thử hồi quy có thể chạy lại; (4) đánh giá kết quả nâng cấp dựa trên bảo mật thực tế của ứng dụng, thay vì chỉ dựa vào việc biên dịch thành công.

Phạm vi là **cách đọc hướng dẫn và kiểm chứng khi nâng cấp Spring Security**. Các ví dụ tập trung vào nền tảng Spring Security, chủ yếu là ứng dụng Servlet/Spring MVC; với WebFlux, dùng tài liệu migration Reactive và `WebTestClient` tương ứng.

## 1. Vì sao phải đọc migration guide, kể cả khi build đã xanh?

Nâng cấp dependency có thể làm ứng dụng khởi động và toàn bộ controller vẫn tồn tại, nhưng một endpoint đổi từ cho phép sang từ chối, một đường dẫn không còn khớp rule, hoặc header `Location` khi chuyển hướng đăng nhập thay đổi. Đó là **thay đổi hợp đồng bảo mật** dù không có lỗi biên dịch.

Phân biệt ba loại thay đổi:

| Loại | Ví dụ | Cách phát hiện |
| --- | --- | --- |
| API/source compatibility | Cách cấu hình DSL cũ bị loại bỏ | Biên dịch, kiểm tra deprecation, sửa mã |
| Cấu hình và mặc định | Kiểu `RequestMatcher` được dùng theo mặc định đổi | Đọc migration guide, thử URL biên và so hành vi |
| Runtime/security contract | 401, 403, 302; CSRF; quyền truy cập; session/cookie | Integration test thực sự đi qua security filter chain |

Không nên coi một bài migration là danh sách lệnh tìm và thay thế. Câu hỏi quan trọng nhất là: **sau nâng cấp, người dùng/ứng dụng gọi cùng một request sẽ nhận cùng quyền, trạng thái HTTP và hiệu ứng phụ như trước chứ?**

## 2. Xác định đúng nguồn tài liệu và đường nâng cấp

1. Ghi lại phiên bản **đang chạy** của Java, Spring Boot, Spring Framework, Spring Security, `spring-security-test` và các module OAuth2/SAML nếu có. Ưu tiên dependency tree hoặc BOM thực tế thay vì suy từ một dòng cấu hình.
2. Xác định **phiên bản mục tiêu** và kiểm tra compatibility/support tương ứng. Nếu dùng Spring Boot, cần nâng theo bộ phiên bản được Boot quản lý; không tự ghép các major version không tương thích.
3. Mở tài liệu của **đúng nhánh nguồn** (phần *Preparing for ...*), sau đó tài liệu của **nhánh đích** (phần *Migrating to ...*). Đọc thêm *What's New*, release notes và changelog cho các bản vá có liên quan.
4. Chọn đúng nhánh **Servlet** hoặc **Reactive**. Chỉ đi sâu vào Authentication, Authorization, OAuth 2.0, SAML, LDAP, method security… nếu ứng dụng đang sử dụng chúng.
5. Với từng mục, xác nhận nó nói về thay đổi chắc chắn đã áp dụng, lựa chọn opt-in thử trước hay API sắp bị bỏ; không suy diễn tất cả nhánh đều bị ảnh hưởng như nhau.

**Ví dụ đường nâng cấp 6.x → 7.x:** Tài liệu Spring Security khuyến nghị sử dụng nhánh 6.5 để chuẩn bị các thay đổi trước khi nâng lên 7.0. Hướng dẫn 7.0 nhắc kiểm tra Spring Boot 4.0 và các bước riêng cho Servlet/Reactive. Đây là ví dụ về một đường nâng cấp cụ thể; dự án ở phiên bản khác phải tra tài liệu ứng với chính đường đi đó.

Lưu ý: nội dung "Preparing for 7.0" được viết trong bối cảnh trước khi 7.0 phát hành. Hãy đối chiếu với hướng dẫn 7.x và release notes hiện hành; không coi trạng thái "sắp thay đổi" trong tài liệu chuẩn bị là thông tin mới nhất về phiên bản đã phát hành.

## 3. Biến một mục migration thành kế hoạch kiểm chứng

Đọc từng mục bằng sáu câu hỏi cố định:

1. **Áp dụng cho ai?** Servlet/Reactive, loại xác thực nào, component nào, phạm vi URL/method nào?
2. **Trước và sau khác gì?** Ghi rõ hành vi cũ, hành vi mới; phân biệt quy định trong tài liệu với giả thuyết cần xác nhận.
3. **Điều kiện kích hoạt là gì?** Dùng cấu hình mặc định, bean tùy chỉnh, nhiều `SecurityFilterChain`, servlet path, reverse proxy, session hay token?
4. **Mã hoặc cấu hình nào cần đổi?** API được thay thế, cấu hình cần khai báo tường minh hay feature cần bật trước?
5. **Bằng chứng gì chứng minh an toàn?** Request cụ thể, identity/role, HTTP method, URL, CSRF token, expected status/header/body, tác dụng ghi dữ liệu.
6. **Nếu không đạt, xử lý thế nào?** Sửa rule/matcher/flow theo ý định nghiệp vụ; chỉ dùng cơ chế tương thích tạm thời khi tài liệu cho phép, có test và kế hoạch bỏ nó.

Mẫu ghi nhận cho một thay đổi:

| Trường | Nội dung ví dụ |
| --- | --- |
| Tham chiếu | URL đến đúng trang migration và phiên bản |
| Thành phần | `authorizeHttpRequests`, URL `/api/admin/reports` |
| Rủi ro | Matcher thay đổi, request không còn đi vào rule dự kiến |
| Hợp đồng cần giữ | Khách vô danh bị từ chối; USER không có quyền; ADMIN được phép |
| Test trước nâng cấp | Ba request với ba danh tính, lưu status |
| Test sau nâng cấp | Chạy lại chính ba request, đối chiếu và xem xét khác biệt |
| Kết luận | PASS hoặc tạo công việc sửa cấu hình có lý do rõ ràng |

Không "chấp nhận" một thay đổi làm endpoint rộng quyền hơn chỉ vì migration guide nói về cơ chế mới. Ý định cấp quyền của hệ thống vẫn phải được kiểm chứng độc lập.

## 4. Những thay đổi đáng học cách phát hiện

### 4.1. DSL cấu hình: lỗi biên dịch và hành vi là hai việc khác nhau

Trong quá trình chuẩn bị lên Spring Security 7, tài liệu yêu cầu dùng **Lambda DSL** thay cho kiểu chain cũ với `.and()`. Mẫu cấu hình theo Lambda DSL:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/public/**").permitAll()
            .requestMatchers("/admin/**").hasRole("ADMIN")
            .anyRequest().authenticated()
        )
        .httpBasic(Customizer.withDefaults());
    return http.build();
}
~~~

Đây là **đoạn trong lớp `@Configuration`**, cần import tương ứng; không phải một tệp Java chạy độc lập. `Customizer.withDefaults()` chọn mặc định của module được cấu hình, không có nghĩa mặc định qua hai major version luôn giống nhau. Sau khi sửa DSL cho biên dịch được, vẫn phải thử quyền truy cập.

### 4.2. Cách khớp đường dẫn có thể thay đổi

Hướng dẫn chuẩn bị 6.5 → 7 nêu chuyển sang `PathPatternRequestMatcher` làm cơ chế mặc định; các matcher kiểu cũ như `AntPathRequestMatcher` và `MvcRequestMatcher` không còn là con đường dùng trong 7.x. Rà soát cả `securityMatcher` (chọn filter chain) và `requestMatchers` (chọn quy tắc ủy quyền).

Đặc biệt kiểm tra:

- `/api/admin`, `/api/admin/`, `/api/admin/1` và đường dẫn có ký tự được encode; không mặc nhiên cho rằng các pattern có hành vi cũ.
- Request theo các phương thức `GET`, `POST`, `PUT`, `DELETE`; quy tắc giới hạn HTTP method.
- Ứng dụng có nhiều Servlet hoặc servlet path như `/mvc`. `PathPatternRequestMatcher` nhận pattern tương đối với **context path**, còn servlet prefix cần được tính riêng khi thích hợp.
- Thứ tự rule: rule cụ thể phải được xét trước `anyRequest()`; trường hợp nhiều `SecurityFilterChain` cần kiểm tra thứ tự và phạm vi của từng chain.

Ví dụ có servlet mapping `/mvc`, một controller ở `/orders` có URL thực tế `/mvc/orders`. Không tự lấy `/orders` làm giả định cho mọi matcher; đối chiếu `basePath("/mvc")` theo hướng dẫn và thử cả trường hợp được phép, bị chặn.

### 4.3. Redirect login: hợp đồng về URL thay đổi

Tài liệu Web Migrations cho 7.0 nêu `LoginUrlAuthenticationEntryPoint` ưu tiên đường dẫn tương đối ở `Location` thay vì URL tuyệt đối trong trường hợp được mô tả, ví dụ:

~~~http
HTTP/1.1 302 Found
Location: /my-login
~~~

Trước đó ứng dụng có thể thấy `Location: https://example.test/my-login`. Nếu frontend/proxy/test đang so chuỗi tuyệt đối, phải xét lại điều gì là hợp đồng thật: có chuyển tới **đúng trang đăng nhập** và không redirect ra host không mong muốn hay không. Test cần ghi rõ scheme/host/forwarded headers nếu chúng liên quan. Không tự sửa assertion chỉ để làm test xanh khi URL đã bị chuyển sang nơi khác.

### 4.4. Các vùng rủi ro khác theo tính năng đang dùng

| Vùng | Cần kiểm tra |
| --- | --- |
| Method security | `@PreAuthorize`, `@PostAuthorize`, tên tham số dùng trong SpEL; biên dịch với `-parameters` khi biểu thức dựa vào tên tham số |
| Authentication | Login/logout, xử lý sai thông tin đăng nhập, principal/authorities, remember-me và session |
| CSRF | Các request thay đổi trạng thái có token hợp lệ/thiếu token/không hợp lệ; CSRF không tự nhiên biến mất vì nâng version |
| Exception handling | Khi chưa đăng nhập: 401 hay 302 tùy entry point; khi đã đăng nhập nhưng thiếu quyền: thường 403 |
| OAuth2/OIDC/JWT/SAML | Luồng redirect/callback, issuer/audience/signature, scopes/claims, session và logout nếu ứng dụng sử dụng |
| Serialization | Ở đường 6.5 → 7.0, hướng dẫn nêu việc chuyển tích hợp Jackson 2 sang Jackson 3; kiểm tra cách đọc dữ liệu persisted token/session nếu hệ thống dùng |
| HTTP headers, CORS, cookies, HTTPS | Test header/cookie/redirect quan trọng với môi trường proxy và trình duyệt thực tế |

Các mục trên là **danh mục cần đối chiếu**, không khẳng định tất cả đều đổi mặc định trong mọi phiên bản. Lọc theo thay đổi được chính tài liệu của đường nâng cấp chỉ ra.

## 5. Chụp baseline trước khi sửa mã

Một baseline có giá trị bao gồm: commit và dependency lock/BOM; cấu hình `SecurityFilterChain` và method security; ma trận endpoint–method–vai trò; cấu hình session, CSRF, CORS, exception handling; các integration test hiện có. Trên môi trường kiểm thử, lưu kết quả HTTP quan trọng (status, `Location`, `WWW-Authenticate`, `Set-Cookie`, response body và hiệu ứng ghi dữ liệu). Không ghi token, mật khẩu thật hoặc session ID vào log/artifact dùng để chia sẻ.

**Ma trận tối thiểu cần có** (giá trị là ví dụ cho một API dùng HTTP Basic và CSRF):

| Request | Danh tính và điều kiện | Kỳ vọng |
| --- | --- | --- |
| `GET /public` | Chưa đăng nhập | 200 |
| `GET /private` | Chưa đăng nhập | 401 + HTTP Basic challenge |
| `GET /private` | Credentials đúng | 200 |
| `GET /private` | Credentials sai | 401 |
| `POST /orders` | Đăng nhập, thiếu CSRF token | 403 |
| `POST /orders` | Đăng nhập, CSRF token hợp lệ | 201 |
| `GET /admin` | USER thường | 403 nếu route yêu cầu ADMIN |
| `GET /admin` | ADMIN | 200 nếu resource tồn tại |

Với **form login**, request chưa đăng nhập tới URL được bảo vệ thường trả **302** sang login; với API chỉ dùng HTTP Basic thường trả **401**. Đừng hardcode "mọi anonymous luôn 401" hoặc "mọi thiếu quyền luôn 403" mà không kiểm tra cấu hình entry point, filter chain và HTTP method.

## 6. Ví dụ chạy được: JUnit 5 + MockMvc kiểm chứng HTTP Basic và CSRF

Ví dụ này cố ý sử dụng **Servlet/Spring MVC và các API Spring Security Test phổ biến ở 6.5/7.x**. Nó là một test class độc lập trong dự án đã cấu hình Spring/Gradle, không yêu cầu Spring Boot test annotation. Tên tệp: `src/test/java/example/security/MigrationContractTest.java`.

Trong một dự án **Spring Boot 4.0 + Spring Security 7.x** đã có plugin Boot, khai báo dependency dưới đây trong `build.gradle` (Groovy). Dự án Boot 3.x cần dùng starter web tương ứng với nhánh 3.x và dependency versions được BOM của nhánh đó quản lý:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Mã nguồn test đầy đủ:

~~~java
package example.security;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpStatus;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;
import org.springframework.test.context.web.WebAppConfiguration;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.context.WebApplicationContext;
import org.springframework.web.servlet.config.annotation.EnableWebMvc;

@ExtendWith(SpringExtension.class)
@WebAppConfiguration
@ContextConfiguration(classes = MigrationContractTest.AppConfig.class)
class MigrationContractTest {
    @Autowired
    WebApplicationContext context;

    MockMvc mvc;

    @BeforeEach
    void setUp() {
        mvc = MockMvcBuilders.webAppContextSetup(context)
                .apply(springSecurity())
                .build();
    }

    @Test
    void publicRequestIsAllowed() throws Exception {
        mvc.perform(get("/public"))
                .andExpect(status().isOk())
                .andExpect(content().string("public"));
    }

    @Test
    void anonymousRequestRequiresAuthentication() throws Exception {
        mvc.perform(get("/private"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void validCredentialsAllowProtectedGet() throws Exception {
        mvc.perform(get("/private").with(httpBasic("alice", "password")))
                .andExpect(status().isOk())
                .andExpect(content().string("private"));
    }

    @Test
    void invalidCredentialsAreRejected() throws Exception {
        mvc.perform(get("/private").with(httpBasic("alice", "wrong")))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void postWithoutCsrfTokenIsForbidden() throws Exception {
        mvc.perform(post("/orders").with(httpBasic("alice", "password")))
                .andExpect(status().isForbidden());
    }

    @Test
    void postWithCsrfTokenIsCreated() throws Exception {
        mvc.perform(post("/orders")
                        .with(httpBasic("alice", "password"))
                        .with(csrf()))
                .andExpect(status().isCreated())
                .andExpect(content().string("created"));
    }

    @Configuration
    @EnableWebMvc
    @EnableWebSecurity
    @Import(DemoController.class)
    static class AppConfig {
        @Bean
        SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
            http.authorizeHttpRequests(auth -> auth
                            .requestMatchers("/public").permitAll()
                            .anyRequest().authenticated())
                    .httpBasic(Customizer.withDefaults());
            return http.build();
        }

        @Bean
        UserDetailsService users() {
            return new InMemoryUserDetailsManager(
                    User.withUsername("alice")
                            .password("{noop}password")
                            .roles("USER")
                            .build());
        }
    }

    @RestController
    static class DemoController {
        @GetMapping("/public")
        String publicEndpoint() {
            return "public";
        }

        @GetMapping("/private")
        String privateEndpoint() {
            return "private";
        }

        @PostMapping("/orders")
        @ResponseStatus(HttpStatus.CREATED)
        String createOrder() {
            return "created";
        }
    }
}
~~~

Chạy từ root của dự án Gradle:

~~~bash
./gradlew test --tests "example.security.MigrationContractTest"
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "example.security.MigrationContractTest"
~~~

**Kết quả mong đợi:** 6 test PASS, Gradle kết thúc với `BUILD SUCCESSFUL`; các request có status tương ứng 200, 401, 200, 401, 403, 201 theo thứ tự các test. Đây là **kết quả kỳ vọng khi chạy với bộ dependency và cấu hình đã nêu**, không phải log thực nghiệm đã thu từ một dự án cụ thể.

Giải thích các thành phần quan trọng:

- `springSecurity()` gắn Spring Security vào `MockMvc`; bỏ nó có thể làm test chạy qua controller mà không đi qua filter, tạo kết quả 200 giả.
- `httpBasic("alice", "password")` thêm header Authorization của HTTP Basic, giúp kiểm tra **xác thực thật qua filter**. `@WithMockUser` hữu ích để cô lập kiểm tra phân quyền nhưng không kiểm chứng password hay giao thức đăng nhập.
- `csrf()` tạo token hợp lệ cho request kiểm thử. `POST` không có token bị chặn trước khi chạy controller; request có token được phép tạo resource.
- `{noop}` trong mật khẩu chỉ phù hợp ví dụ test với dữ liệu giả; hệ thống thật phải dùng password encoder an toàn.
- Khi chuyển sang app thật, thay `DemoController` và `AppConfig` bằng context/config thực tế, rồi mở rộng test vai trò, matcher, session và endpoint nghiệp vụ.

## 7. Từ thay đổi trong tài liệu tới test hồi quy cụ thể

### Tình huống A: matcher URL đổi hành vi

Giả sử chính sách là chỉ ADMIN được đọc `GET /admin/reports`. Trước nâng cấp, chụp kết quả với anonymous/USER/ADMIN; sau nâng cấp chạy lại cả ba. Thêm biên: `/admin/reports/`, `/admin/reports/2026`, request khác method, URL có context/servlet prefix. Một trạng thái **404** có thể do không có handler, chưa đủ chứng minh rule cấp quyền đúng. Để chứng minh authorization, test nên nhắm tới endpoint thực sự tồn tại và kết hợp kiểm tra bên được phép/không được phép.

Nếu rule không khớp, kiểm tra lần lượt: request thực tế → chain được chọn bởi `securityMatcher` → matcher trong `authorizeHttpRequests` → thứ tự rule → controller mapping. Không lập tức thêm `permitAll()` hay tắt filter.

### Tình huống B: redirect sang login thay đổi

Với app có `formLogin`, test anonymous GET vào tài nguyên bảo vệ và kiểm tra mã redirect, đích đến và host hợp lệ. Khi guide nêu URL từ tuyệt đối sang tương đối, assertion nào ép toàn chuỗi `https://...` cần được xem xét có thật sự phản ánh yêu cầu sản phẩm không. Nếu hệ thống đòi absolute URL do client legacy, cấu hình khả năng tương thích theo đúng phiên bản API và bổ sung test cho host/proxy; tránh gán mặc định mới thành lỗi bảo mật một cách máy móc.

### Tình huống C: method security sử dụng tên tham số

Nếu `@PreAuthorize("@policy.canRead(#id, authentication)")` phụ thuộc tên `id`, rà soát compiler flag `-parameters` và test gọi method với chủ sở hữu/không phải chủ sở hữu. Test HTTP thành công không thay thế test method security khi logic được bảo vệ ở service; cần bảo đảm proxy method-security thực sự được bật.

### Tình huống D: CSRF và browser session

Đối với request ghi dữ liệu từ trình duyệt dùng cookie/session, kiểm tra ít nhất: không có token → bị chặn; token sai → bị chặn; token đúng → được xử lý (nếu đã xác thực và có quyền). Việc dùng bearer token trong header và cấu hình stateless có thể dẫn tới chính sách CSRF khác, nhưng phải dựa vào mô hình threat thực tế; **không tắt CSRF chỉ để chữa test đỏ**.

## 8. Chạy nâng cấp theo các cổng kiểm soát nhỏ

1. **Baseline:** test trước thay đổi, ghi chính sách bảo mật và các status/header quan trọng; biết rõ test nào đã fail từ trước.
2. **Chuẩn bị:** nâng lên nhánh trung gian được migration guide khuyên dùng, xử lý deprecation và thử opt-in hành vi mới khi tài liệu cho phép.
3. **Nâng core:** cập nhật Boot/Framework/Security và các starter/module liên quan theo dependency management, sửa lỗi API và startup.
4. **So hợp đồng:** chạy lại bộ test với **cùng dữ liệu, role, URL và profile**; chỉ chấp nhận chênh lệch có phân tích và được xác nhận bởi yêu cầu nghiệp vụ.
5. **Kiểm thử tích hợp:** thử database, reverse proxy, CORS/CSRF, TLS, IdP OAuth/OIDC/SAML và browser thật nếu các thành phần đó tồn tại trong ứng dụng.
6. **Quan sát và rollback:** kiểm tra log 401/403/redirect bất thường, vòng lặp login, lỗi phân quyền; chuẩn bị cách quay lại bản triển khai trước nếu phát hiện mở quyền hoặc chặn nhầm nghiêm trọng.

Ưu tiên chạy test trên môi trường staging giống production về context path, reverse proxy/forwarded headers, cấu hình session và identity provider. Một MockMvc test đúng là cần thiết nhưng không thể chứng minh mọi tương tác của trình duyệt hoặc proxy ngoài quy trình.

## 9. Chẩn đoán test đỏ đúng nguyên nhân

| Hiện tượng | Những nơi cần kiểm tra trước |
| --- | --- |
| 200 không mong đợi trên endpoint bảo vệ | Filter có được gắn vào test? `securityMatcher` có bắt request không? Có rule `permitAll` rộng hơn dự định? |
| 401 thay cho 200 | Credentials/token không hợp lệ, `AuthenticationManager`/provider, entry point, hoặc user/role giả lập không khớp |
| 302 thay cho 401 | Có `formLogin`/entry point chuyển tới login, cần xác nhận flow cấu hình |
| 403 thay cho 200 | Đã xác thực nhưng thiếu quyền, CSRF trên method không an toàn, hoặc method security từ chối |
| 404 thay cho 200 | Controller mapping/context path/servlet path; đừng tự kết luận authorization đã từ chối |
| Redirect sai đích/vòng lặp | `Location` tương đối/tuyệt đối, saved request, base URL và forwarded headers |
| Test PASS dù app thật bị chặn | Test chưa gắn `springSecurity()`, đang dùng mock identity bỏ qua xác thực, thiếu proxy/IdP hoặc sai profile |

Phân biệt **expected change** (tài liệu mô tả và sản phẩm chấp nhận), **security regression** (mở quyền hoặc bỏ bảo vệ ngoài ý muốn), và **test assumption lỗi thời** (assertion quá cụ thể về cách biểu diễn mà không phản ánh hợp đồng sản phẩm). Đổi assertion chỉ sau khi đã phân loại.

## 10. Bài tự luyện

Cho ứng dụng có `/public`, `/orders/**` cho USER/ADMIN và `/admin/**` chỉ ADMIN, kèm đăng nhập form. Hãy chọn một major-version migration guide phù hợp và:

1. Lập bảng ít nhất 8 request bao trùm anonymous, USER, ADMIN; GET/POST; token CSRF thiếu/đúng; URL có và không có dấu `/` cuối.
2. Trích dẫn chính xác mục nào trong tài liệu dự báo thay đổi matcher, redirect hoặc DSL; ghi trường hợp nào không liên quan vì app không dùng tính năng đó.
3. Viết test trước nâng cấp, lưu kết quả; áp dụng migration; chạy lại. Nếu nhận 403/404/302 ngoài dự kiến, điều tra theo filter chain, matcher, controller và entry point trước khi sửa.
4. Viết quyết định PASS/FAIL: mọi endpoint nhạy cảm vẫn bị chặn đúng vai trò, login/logout hoạt động, request thay đổi trạng thái vẫn đáp ứng chính sách CSRF, không có truy cập trái phép.

**Tiêu chí hoàn thành:** bạn giải thích được *vì sao* từng assertion tồn tại, chỉ ra bằng chứng cho hành vi trước/sau, và biết phân biệt sửa mã để build với bảo toàn security contract khi chạy.

## 11. Checklist đưa thay đổi vào nhánh chính

- [ ] Đã xác định đúng version nguồn/đích, BOM và nhánh Servlet/Reactive.
- [ ] Đã đọc *Preparing*, *Migrating*, *What's New* và release notes liên quan; lọc các mục ứng dụng thực sự dùng.
- [ ] Đã ghi baseline cho authentication, authorization, method security, CSRF, redirect, session và matcher tương ứng.
- [ ] Không còn API bị loại bỏ; config khởi động được bằng dependency set tương thích.
- [ ] Test `spring-security-test` đi qua filter chain thật khi cần; mock identity không bị lạm dụng để kiểm tra login.
- [ ] Anonymous/đủ quyền/thiếu quyền/CSRF/các URL biên đều đã được kiểm tra.
- [ ] Các khác biệt 401/403/302, header và URL redirect được giải thích và chấp nhận có chủ đích.
- [ ] Test tích hợp môi trường phù hợp và cơ chế giám sát/rollback đã sẵn sàng.

## 12. Tài liệu tham khảo chính thức

- [Spring Security — Migrating to 7.0](https://docs.spring.io/spring-security/reference/migration/)
- [Spring Security 6.5 — Preparing for 7.0](https://docs.spring.io/spring-security/reference/6.5/migration-7/index.html)
- [Configuration Migrations — Lambda DSL](https://docs.spring.io/spring-security/reference/6.5/migration-7/configuration.html)
- [Web Migrations — RequestMatcher và relative redirect](https://docs.spring.io/spring-security/reference/6.5/migration-7/web.html)
- [Spring Security — Servlet Testing / MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/index.html)
- [Spring Security — Testing CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/csrf.html)
- [Spring Security — Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html)
- [Spring Boot 4.0 — Build Systems](https://docs.spring.io/spring-boot/4.0/reference/using/build-systems.html)

Khi đọc tài liệu trực tuyến, luôn chọn **version selector** đúng với dependency thực tế. Link hướng dẫn 6.5 → 7.0 ở trên là ví dụ học quy trình, không thay thế hướng dẫn cho mọi bản nâng cấp sau này.
