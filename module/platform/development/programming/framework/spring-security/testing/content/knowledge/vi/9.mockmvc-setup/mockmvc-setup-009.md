# defaultRequest và nguy cơ đặt sẵn danh tính cho mọi request

## Mục tiêu bài học

Trong mô-đun **SPRING_SECURITY_TESTING**, người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP bằng `spring-security-test` trên ứng dụng Servlet và Reactive. Bài này tập trung vào **MockMvc trong Spring MVC** và tùy chọn `defaultRequest(...)`: cách đặt những thuộc tính chung cho các request, đồng thời nhận diện rủi ro khi vô tình đặt một người dùng đã xác thực làm mặc định cho toàn bộ test.

Sau bài học, bạn có thể:

1. Giải thích `defaultRequest(...)` hoạt động như một request builder nền được merge vào mỗi request.
2. Phân biệt thuộc tính dùng chung như `Accept`, locale với danh tính bảo mật.
3. Nhận biết vì sao default user hoặc admin có thể làm test anonymous và authorization sai lệch.
4. Thiết kế MockMvc fixture chung mà không tự động xác thực tất cả request.
5. Dùng một MockMvc riêng có danh tính mặc định khi đó là mục đích có chủ ý, và tách nó khỏi các ca kiểm thử ẩn danh.

## 1. defaultRequest là gì?

`MockMvcBuilders` cho phép khai báo một `RequestBuilder` mặc định:

~~~java
MockMvc mockMvc = MockMvcBuilders.webAppContextSetup(context)
    .defaultRequest(get("/")
        .accept(MediaType.APPLICATION_JSON)
        .characterEncoding("UTF-8"))
    .apply(springSecurity())
    .build();
~~~

`defaultRequest(...)` cung cấp những thuộc tính nền được **merge vào mọi request** gửi qua MockMvc đó. Ví dụ có thể dùng nó để đặt `Accept: application/json`, encoding, locale hoặc header kiểm thử chung. Request cụ thể vẫn cung cấp method, path, body, parameter và các thuộc tính riêng của nó.

Điểm quan trọng là request mặc định không chỉ chứa header. Nếu bạn thêm request post-processor tạo người dùng, chẳng hạn `with(user("admin").roles("ADMIN"))`, danh tính đó cũng trở thành một phần của request builder nền và được áp dụng cho những request dùng MockMvc này.

~~~mermaid
flowchart TB
    A["defaultRequest(get('/').accept(JSON))"] --> C["MockMvc"]
    B["defaultRequest(...with(user('admin')))"] --> C
    D["perform(get('/api/public'))"] --> E["Merge default + request riêng"]
    F["perform(get('/api/admin'))"] --> G["Merge default + request riêng"]
    C --> E
    C --> G
    E --> H["Security filters"]
    G --> H
    H --> I["Controller / response"]
~~~

`defaultRequest(...)` là một tiện ích của MockMvc, không phải một cơ chế cấu hình toàn cục của Spring Security. Nó không sửa `SecurityFilterChain`; nó thay đổi những request được tạo ra qua **một instance MockMvc cụ thể**.

## 2. Dùng defaultRequest cho thuộc tính chung

Các thuộc tính giống nhau ở nhiều test có thể được đặt làm mặc định để giảm lặp:

~~~java
MockMvc mockMvc = MockMvcBuilders.webAppContextSetup(context)
    .defaultRequest(get("/")
        .accept(MediaType.APPLICATION_JSON)
        .characterEncoding("UTF-8")
        .header("X-Test-Client", "mvc-suite"))
    .apply(springSecurity())
    .build();
~~~

Các request cụ thể có thể tập trung vào điều đang kiểm tra:

~~~java
mockMvc.perform(get("/api/articles/42"))
    .andExpect(status().isOk());

mockMvc.perform(post("/api/articles")
        .contentType(MediaType.APPLICATION_JSON)
        .content("{\"title\":\"Spring Security\"}")
        .with(csrf()))
    .andExpect(status().isCreated());
~~~

Trong ví dụ này, cả hai request đều nhận `Accept`, encoding và header chung từ default builder. Request POST vẫn tự khai báo content type, body và CSRF token của nó.

Những giá trị thường hợp lý để đặt mặc định:

| Giá trị | Có phù hợp làm mặc định? | Lý do |
| --- | --- | --- |
| `Accept: application/json` | Có, nếu API test chủ yếu trả JSON | Tránh lặp header biểu diễn định dạng mong muốn |
| Character encoding | Có, nếu suite dùng cùng encoding | Làm rõ cách diễn giải request body |
| Header nhận diện test client | Có, nếu mọi request cần header đó | Dùng cho tracing hoặc logic test chung |
| Locale | Có, nếu cả suite cần cùng ngôn ngữ | Chuẩn hóa nội dung message |
| `Authorization` hoặc principal | Cần cân nhắc kỹ | Có thể khiến mọi request trở thành request đã xác thực |
| Role `ADMIN` | Rất dễ gây sai lệch | Có thể làm ca kiểm thử thiếu quyền trở thành ca đủ quyền |
| CSRF token | Không nên mặc định nếu cần kiểm tra CSRF | Có thể che khuất endpoint POST thiếu token |

## 3. Rủi ro khi đặt danh tính làm mặc định

Giả sử ứng dụng có ba endpoint:

- `GET /api/public`: cho phép mọi người truy cập.
- `GET /api/profile`: yêu cầu người dùng đã xác thực.
- `GET /api/admin`: yêu cầu role `ADMIN`.

Security policy:

~~~java
@Configuration
class SecurityConfiguration {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/admin").hasRole("ADMIN")
                .anyRequest().authenticated()
            )
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
~~~

Một builder như sau đặt admin làm mặc định:

~~~java
MockMvc adminMockMvc = MockMvcBuilders.webAppContextSetup(context)
    .defaultRequest(get("/")
        .with(user("test-admin").roles("ADMIN")))
    .apply(springSecurity())
    .build();
~~~

Khi dùng `adminMockMvc`, mỗi request được dựng qua instance này đều nhận danh tính admin từ default request, trừ khi request cụ thể được thiết kế để thay thế thuộc tính đó. Vì vậy:

~~~java
adminMockMvc.perform(get("/api/admin"))
    .andExpect(status().isOk());

adminMockMvc.perform(get("/api/profile"))
    .andExpect(status().isOk());
~~~

Hai phép thử trên hợp lệ nếu mục tiêu là xác minh hành vi của người dùng admin. Nhưng nếu một test có tên `anonymousCannotReadAdmin` lại dùng chính `adminMockMvc`, request không còn là anonymous nữa. Nó có thể nhận 200 và làm test thất bại, hoặc nếu assertion chỉ kiểm tra response chung, che giấu việc test chưa hề kiểm tra truy cập ẩn danh.

Nguy cơ không chỉ là sai tên test. Default admin có thể làm những test sau trở nên vô nghĩa:

- Test yêu cầu 401 cho người chưa đăng nhập.
- Test yêu cầu 403 cho người đã đăng nhập nhưng thiếu role.
- Test kiểm tra endpoint chỉ cho phép một nhóm authority cụ thể.
- Test kiểm tra principal hoặc tên người dùng hiện tại.
- Test kiểm tra luồng xác thực thật, vì request đã có authentication giả lập trước khi filter xác thực chạy.

**Một test có danh tính mặc định không phải test anonymous**, dù trong test method không thấy `@WithMockUser` hay `.with(user(...))`.

## 4. Ví dụ hoàn chỉnh: tách MockMvc chung và MockMvc có admin mặc định

### 4.1. Ứng dụng mẫu

Controller:

~~~java
@RestController
class AccessController {
    @GetMapping("/api/public")
    String publicData() {
        return "public";
    }

    @GetMapping("/api/profile")
    String profile(Principal principal) {
        return principal.getName();
    }

    @GetMapping("/api/admin")
    String admin() {
        return "admin";
    }
}
~~~

Cấu hình bảo mật dùng `SecurityFilterChain` ở mục 3. Tệp kiểm thử:

~~~java
package example;

import java.security.Principal;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.context.WebApplicationContext;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.webAppContextSetup;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
class DefaultRequestSecurityTest {
    @Autowired
    WebApplicationContext context;

    MockMvc commonMockMvc;
    MockMvc adminMockMvc;

    @BeforeEach
    void setUp() {
        // Chỉ đặt thuộc tính HTTP chung, không đặt danh tính.
        commonMockMvc = webAppContextSetup(context)
            .defaultRequest(get("/")
                .accept(MediaType.APPLICATION_JSON)
                .characterEncoding("UTF-8"))
            .apply(springSecurity())
            .build();

        // Fixture riêng dành cho những ca có chủ ý dùng admin.
        adminMockMvc = webAppContextSetup(context)
            .defaultRequest(get("/")
                .accept(MediaType.APPLICATION_JSON)
                .with(user("test-admin").roles("ADMIN")))
            .apply(springSecurity())
            .build();
    }

    @Test
    void anonymousCannotReadAdmin() throws Exception {
        commonMockMvc.perform(get("/api/admin"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void anonymousCannotReadProfile() throws Exception {
        commonMockMvc.perform(get("/api/profile"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void adminCanReadAdmin() throws Exception {
        adminMockMvc.perform(get("/api/admin"))
            .andExpect(status().isOk())
            .andExpect(content().string("admin"));
    }

    @Test
    void adminCanReadProfile() throws Exception {
        adminMockMvc.perform(get("/api/profile"))
            .andExpect(status().isOk())
            .andExpect(content().string("test-admin"));
    }

    @Test
    void viewerIsForbiddenWhenUsingCommonMockMvc() throws Exception {
        commonMockMvc.perform(get("/api/admin")
                .with(user("test-viewer").roles("VIEWER")))
            .andExpect(status().isForbidden());
    }
}
~~~

Ví dụ giả định `AccessController`, `SecurityConfiguration` và test nằm trong cùng package `example`; các import cho controller và security configuration cần có trong source tương ứng. Hai instance MockMvc có mục đích rõ ràng:

- `commonMockMvc` chỉ đặt header/encoding dùng chung, do đó có thể dùng để kiểm tra anonymous.
- `adminMockMvc` đặt admin mặc định và chỉ dùng trong test cần hành vi của admin.

Tách instance giúp người đọc nhận ra ngay test nào có danh tính nền. Một fixture đặt tên rõ ràng như `adminMockMvc` cũng giảm nguy cơ dùng nhầm trong test ẩn danh.

## 5. Nên ghi đè default user bằng anonymous() hay tạo instance riêng?

Spring Security Test có request post-processor `anonymous()`:

~~~java
commonMockMvc.perform(get("/api/admin")
        .with(anonymous()))
    .andExpect(status().isUnauthorized());
~~~

Cần static import `org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.anonymous` cho ví dụ trên.

Nó hữu ích khi muốn chỉ rõ request cần được xem là anonymous. Tuy nhiên, nếu builder nền đã đặt một authentication khác, việc kết hợp nhiều post-processor để thay thế danh tính làm test khó đọc và phụ thuộc vào thứ tự áp dụng/merge request processor. Hãy ưu tiên **không đặt user làm default cho instance dùng chung**; dùng instance không có default identity cho ca anonymous.

Nếu dự án có một fixture default user vì nhiều test thực sự cần danh tính đó, hãy đặt tên riêng và giới hạn cách dùng. Có thể dùng request processor rõ ràng để thay danh tính trong một request cụ thể, nhưng nên có một test nhỏ xác nhận kết quả override trên đúng phiên bản Spring/Spring Security của dự án trước khi dựa vào hành vi đó.

Quy tắc lựa chọn:

| Nhu cầu | Cách nên dùng |
| --- | --- |
| Phần lớn test cần anonymous mặc định | MockMvc không có default identity |
| Mọi request cần cùng `Accept`/locale/header | `defaultRequest(...)` chỉ đặt HTTP properties |
| Một test cần admin | `.with(user("admin").roles("ADMIN"))` trên request đó |
| Nhiều test chỉ dành cho admin | Instance riêng có tên `adminMockMvc` |
| Test cần so sánh anonymous, viewer và admin | Một MockMvc chung không có default identity; mỗi request khai báo user riêng |
| Test login/session thật | Gửi request qua login flow và dùng session/cookie phù hợp, không dùng default mock user |

## 6. Default user có thể làm sai lệch kiểm thử CSRF

CSRF là một lớp kiểm tra độc lập với role. Một request POST có admin mặc định nhưng không có CSRF token vẫn phải bị từ chối nếu CSRF đang bật. Tuy nhiên, nếu default request cũng đặt sẵn một CSRF token hoặc request post-processor khác thêm token vào mọi request, test có thể vô tình bỏ qua trường hợp thiếu token.

Ví dụ không nên dùng cho toàn bộ suite:

~~~java
MockMvc mockMvc = webAppContextSetup(context)
    .defaultRequest(post("/")
        .with(user("admin").roles("ADMIN"))
        .with(csrf()))
    .apply(springSecurity())
    .build();
~~~

Builder này đặt cả danh tính admin và CSRF token làm mặc định. Những request POST qua instance có thể đã mang token trước khi test method khai báo điều đó. Khi ấy, test không chứng minh endpoint từ chối request thiếu CSRF.

Hãy để CSRF được khai báo tại request cần token:

~~~java
mockMvc.perform(post("/api/articles")
        .with(user("editor").roles("EDITOR"))
        .with(csrf()))
    .andExpect(status().isCreated());

mockMvc.perform(post("/api/articles")
        .with(user("editor").roles("EDITOR")))
    .andExpect(status().isForbidden());
~~~

Hai request làm rõ khác biệt: cùng người dùng và cùng quyền, nhưng chỉ request đầu có CSRF token. Không đưa `csrf()` vào default request nếu suite cần kiểm tra token thiếu hoặc không hợp lệ.

## 7. DefaultRequest không phải đăng nhập hay session thật

`defaultRequest(get("/").with(user("admin").roles("ADMIN")))` áp dụng một authentication giả lập cho các request được tạo qua MockMvc instance đó. Nó không:

- Gửi username/password đến endpoint login.
- Kiểm tra `UserDetailsService`, `AuthenticationProvider` hoặc `PasswordEncoder`.
- Xác minh chữ ký JWT, issuer, audience hoặc thời hạn token.
- Chứng minh ứng dụng tạo và duy trì session/cookie như client thật.
- Tự tạo một phiên đăng nhập bền vững ngoài phạm vi request test được dựng.

Nếu cần xác minh login hoặc session, hãy kiểm thử login endpoint với credentials phù hợp, nhận session/cookie từ response rồi gửi request tiếp theo bằng session đó. `defaultRequest` phù hợp để tạo fixture request, không thay thế quy trình xác thực thực tế.

Tương tự, `with(jwt())` hoặc `with(oauth2Login())` có thể được đặt trên một request cụ thể để kiểm tra authorization sau xác thực. Không nên biến chúng thành danh tính mặc định cho cả suite nếu có ca cần kiểm tra bearer token thiếu/sai hoặc người dùng chưa đăng nhập.

## 8. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Test anonymous trả 200 | MockMvc có default user đủ quyền | Dùng instance không có default identity |
| Test viewer lại được phép vào admin | Default admin được merge vào request | Đừng dùng admin fixture cho test role thấp |
| Test kiểm tra thiếu CSRF vẫn trả 201 | CSRF token được đặt ở default request | Chỉ thêm `with(csrf())` trên request cần token |
| Test `@WithMockUser` khó hiểu khi dùng default user | Có nhiều nguồn identity cùng áp dụng | Chọn một cơ chế identity cho mỗi request |
| Test principal trả tên admin ở mọi nơi | User default được áp dụng toàn instance | Đưa user vào request cụ thể hoặc instance riêng |
| Test login luôn thành công | Request đã có mock authentication trước filter | Dùng instance không default identity và gửi credentials thật |
| Test public không chứng minh anonymous | `permitAll()` trả 200 dù request đã được xác thực | Kiểm tra endpoint cần authentication bằng anonymous request riêng |

Checklist khi review:

1. `defaultRequest(...)` có gọi `with(user(...))`, `with(jwt())`, `with(authentication(...))` hoặc `csrf()` không?
2. Instance MockMvc nào được dùng trong test anonymous và test thiếu quyền?
3. Test có đặt danh tính ngay tại request cần danh tính không?
4. Có request POST thực sự không có CSRF token không?
5. Test có đang nhầm mock authentication với login/session/token validation thật không?
6. Tên fixture có thể hiện rõ danh tính mặc định, ví dụ `adminMockMvc`, không?

## 9. Gợi ý tổ chức test fixture

Một cấu trúc dễ đọc là tạo factory method cho các loại MockMvc khác nhau:

~~~java
private MockMvc buildMockMvc(RequestPostProcessor... defaults) {
    MockHttpServletRequestBuilder defaultBuilder = get("/")
        .accept(MediaType.APPLICATION_JSON);

    for (RequestPostProcessor processor : defaults) {
        defaultBuilder.with(processor);
    }

    return webAppContextSetup(context)
        .defaultRequest(defaultBuilder)
        .apply(springSecurity())
        .build();
}
~~~

Ví dụ này cần import `MockHttpServletRequestBuilder`, `RequestPostProcessor` và static `get`, `springSecurity`. Có thể tạo:

~~~java
MockMvc anonymousByDefault = buildMockMvc();
MockMvc adminByDefault = buildMockMvc(user("admin").roles("ADMIN"));
~~~

Nhưng factory method chỉ hữu ích khi team thống nhất cách dùng. Với test bảo mật, nên ưu tiên fixture mặc định không có danh tính; đặt tên riêng cho instance đặc quyền và không truyền nó vào test anonymous.

Nếu suite lớn, có thể tạo helper rõ nghĩa:

- `buildUnauthenticatedMvc()` — không đặt user.
- `buildMvcWithAdmin()` — chỉ dùng cho test admin.
- `buildMvcWithDefaultHeaders()` — chỉ đặt header/encoding/locale, không gắn authentication.

Tránh một helper chung tên `buildMockMvc()` tự động gắn admin vì người viết test rất dễ bỏ qua tác động đó.

## 10. Bài tập thực hành

**Bài 1 — Tạo test false positive.** Cấu hình `defaultRequest(get("/").with(user("admin").roles("ADMIN")))`. Viết một test gọi `/api/admin` và quan sát vì sao request không còn anonymous dù test method không khai báo user.

**Bài 2 — Tách fixture.** Tạo `commonMockMvc` chỉ có header `Accept`, và `adminMockMvc` có default admin. Viết test anonymous bị 401 và test admin được 200 trên đúng instance.

**Bài 3 — So sánh role.** Dùng `commonMockMvc` để gửi lần lượt `VIEWER` và `ADMIN` bằng `.with(user(...))`. Xác minh kết quả 403 và 200.

**Bài 4 — Kiểm tra CSRF.** Đặt thử `csrf()` trong default request rồi quan sát tác động lên test thiếu token. Sau đó bỏ token mặc định và chỉ gắn `with(csrf())` cho request hợp lệ.

**Bài 5 — Phân biệt mock với login.** So sánh request có default mock user với một test đăng nhập thật dùng session/cookie. Ghi rõ hành vi nào mỗi test chứng minh.

## 11. Ghi nhớ

`defaultRequest(...)` giúp giảm lặp bằng cách merge thuộc tính của một request builder nền vào mọi request của một MockMvc instance. Điều này hữu ích cho header, locale hoặc encoding dùng chung. Nhưng khi đặt `user(...)`, `jwt()`, `authentication(...)` hay `csrf()` làm mặc định, mọi test dùng instance đó có thể bị thay đổi điều kiện đầu vào.

**Hãy để MockMvc dùng chung không có default identity.** Đặt danh tính và CSRF token ngay trên request cần chúng; nếu nhiều test thật sự cần cùng một role, tạo instance riêng có tên thể hiện rõ quyền đó. Nhờ vậy, các ca anonymous, thiếu quyền và thiếu CSRF vẫn kiểm tra đúng tình huống mà chúng mô tả.
