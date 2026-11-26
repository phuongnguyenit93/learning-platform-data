# Kết hợp annotation người dùng và request post-processor có chủ ý

Trong kiểm thử Spring Security với `MockMvc`, có hai cách thường dùng để chuẩn bị danh tính: annotation như `@WithMockUser` thiết lập một `SecurityContext` mặc định cho test method hoặc test class; request post-processor như `.with(user(...))`, `.with(anonymous())` và `.with(authentication(...))` chuẩn bị danh tính cho một request cụ thể. Kết hợp hai cơ chế có chủ ý giúp một test method kiểm tra được nhiều tình huống: người dùng mặc định được phép, một người khác bị từ chối, quản trị viên được phép và khách chưa đăng nhập bị chặn.

Bài học thuộc chương **Danh tính trên yêu cầu** của module `SPRING_SECURITY_TESTING`, nơi người học kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng `spring-security-test` trên ứng dụng Servlet và Reactive. Trọng tâm ở đây là **cách phối hợp annotation người dùng với request post-processor** để điều khiển danh tính đầu vào chính xác, đọc đúng nguyên nhân của kết quả `200`/`401`/`403` và tránh nhầm lẫn về phạm vi tác động.

## 1. Hai lớp chuẩn bị danh tính trong một bài test

### Annotation thiết lập danh tính mặc định

`@WithMockUser` tạo một `SecurityContext` cho test method hoặc test class thông qua Spring Security Test listener. Ví dụ:

```java
@Test
@WithMockUser(username = "reader", roles = "READER")
void readerCanReadReports() throws Exception {
    mockMvc.perform(get("/api/reports"))
           .andExpect(status().isOk());
}
```

Trong method trên, request không cần khai báo `.with(user(...))` vì danh tính mặc định đã được annotation chuẩn bị. Principal thường là `org.springframework.security.core.userdetails.User` do Spring Security Test tạo, username là `reader` và authority tương ứng là `ROLE_READER`.

Annotation phù hợp khi phần lớn request trong một method có chung một danh tính. Đặt annotation ở cấp class tạo mặc định cho các test method trong class; annotation ở method thể hiện rõ điều kiện riêng của method đó. Đây là **context của test**, không phải quá trình đăng nhập thật hoặc một tài khoản vừa được tạo trong database.

### Request post-processor thay đổi danh tính cho một request

Khi một request cần danh tính khác với mặc định, dùng `.with(...)`:

```java
mockMvc.perform(get("/api/reports")
        .with(user("admin").roles("ADMIN")))
    .andExpect(status().isOk());

mockMvc.perform(get("/api/reports")
        .with(anonymous()))
    .andExpect(status().isUnauthorized());
```

Request post-processor đặt dữ liệu bảo mật cho request được xây dựng bởi lần `perform(...)` đó. Khi kết hợp với `@WithMockUser`, danh tính được khai báo tường minh tại request sẽ **ghi đè context mặc định cho request tương ứng**. Các request khác trong cùng method tiếp tục dùng context mặc định của annotation nếu không có processor ghi đè.

Có thể hình dung:

```mermaid
flowchart TD
    A["@WithMockUser: reader / ROLE_READER"] --> B["MockMvc test method"]
    B --> C{"Request có .with(...)?"}
    C -->|Không| D["Dùng danh tính mặc định reader"]
    C -->|user(admin)| E["Request này dùng admin"]
    C -->|user(writer)| F["Request này dùng writer"]
    C -->|anonymous()| G["Request này là khách vô danh"]
    D --> H["SecurityFilterChain"]
    E --> H
    F --> H
    G --> H
```

**Quy tắc thực hành:** annotation mô tả trạng thái mặc định của test; request post-processor mô tả ngoại lệ hoặc danh tính cần thử tại đúng request. Không cần gán annotation và processor cho mọi request nếu chúng đã có chung một mặc định rõ ràng.

## 2. Các API thường phối hợp

| Công cụ | Phạm vi và tác động | Khi nào dùng |
| --- | --- | --- |
| `@WithMockUser` | Context mặc định cho method/class; principal chuẩn, role/authority giả lập | Nhiều request cùng một người dùng |
| `@WithUserDetails` | Context mặc định lấy `UserDetails` từ `UserDetailsService` | Cần principal do service của ứng dụng tải |
| `.with(user("name").roles(...))` | Danh tính `UserDetails` cho một request | Thử một role khác với annotation |
| `.with(user(customUserDetails))` | Principal `UserDetails` tùy chỉnh cho một request | Controller cần dữ liệu principal nghiệp vụ |
| `.with(authentication(auth))` | Đối tượng `Authentication` cụ thể cho một request | Cần kiểu token/principal/authority tùy chỉnh |
| `.with(securityContext(context))` | `SecurityContext` dựng sẵn cho một request | Cần điều khiển trực tiếp context |
| `.with(anonymous())` | Request vô danh | Kiểm tra khách chưa đăng nhập |
| `.with(csrf())` | CSRF token hợp lệ cho request | Kiểm tra phân quyền của POST/PUT/PATCH/DELETE mà không bị thiếu CSRF che khuất |

Các processor có thể kết hợp trên cùng một request khi chúng điều khiển các phần khác nhau, ví dụ danh tính và CSRF:

```java
mockMvc.perform(post("/api/reports")
        .with(user("admin").roles("ADMIN"))
        .with(csrf()))
    .andExpect(status().isCreated());
```

Ở đây `user(...)` chuẩn bị authentication, còn `csrf()` chuẩn bị token CSRF. Một processor không thay thế chức năng của processor kia. Với các processor cùng thay đổi `SecurityContext`, chỉ nên chọn **một cách đặt danh tính cho mỗi request** để ý định và kết quả không phụ thuộc thứ tự ghép.

## 3. Ví dụ chính sách truy cập cho báo cáo

Giả sử API có hai thao tác:

- `GET /api/reports` chỉ cho phép role `READER` hoặc `ADMIN`.
- `POST /api/reports` chỉ cho phép role `ADMIN`; CSRF vẫn bật theo mặc định.

Cấu hình Servlet:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableWebSecurity
class ReportSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAnyRole("READER", "ADMIN")
                .requestMatchers(HttpMethod.POST, "/api/reports")
                    .hasRole("ADMIN")
                .anyRequest().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
    }
}
```

Controller tối giản để quan sát response:

```java
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ReportController {

    @GetMapping("/api/reports")
    String reports() {
        return "reports";
    }

    @PostMapping("/api/reports")
    @ResponseStatus(HttpStatus.CREATED)
    String createReport() {
        return "created";
    }
}
```

Trong project Maven, thêm dependency test nếu chưa có:

```xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
```

Dùng Spring Boot để tạo `MockMvc` có filter chain:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ReportAccessTests {

    @Autowired
    MockMvc mockMvc;
}
```

Nếu tự dựng `MockMvc` bằng `MockMvcBuilders`, hãy tích hợp Spring Security bằng `.apply(springSecurity())`. Không tắt filter bằng `@AutoConfigureMockMvc(addFilters = false)` khi mục tiêu là kiểm tra authorization HTTP.

## 4. Một test method: annotation làm mặc định, processor ghi đè từng request

Đây là tình huống chính của bài. Test method bắt đầu với `reader` do `@WithMockUser` thiết lập. Sau đó từng request chủ động thử các danh tính khác nhau:

```java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.anonymous;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ReportAccessTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    @WithMockUser(username = "reader", roles = "READER")
    void annotationProvidesDefaultAndRequestProcessorsOverrideIt()
            throws Exception {

        // Không chỉ định .with(...): dùng reader từ @WithMockUser.
        mockMvc.perform(get("/api/reports"))
            .andExpect(status().isOk())
            .andExpect(content().string("reports"));

        // Request này dùng writer; annotation không cấp quyền READER.
        mockMvc.perform(get("/api/reports")
                .with(user("writer").roles("WRITER")))
            .andExpect(status().isForbidden());

        // Request này dùng admin, được phép theo rule.
        mockMvc.perform(get("/api/reports")
                .with(user("admin").roles("ADMIN")))
            .andExpect(status().isOk());

        // Request này được xử lý như khách chưa đăng nhập.
        mockMvc.perform(get("/api/reports")
                .with(anonymous()))
            .andExpect(status().isUnauthorized());

        // Danh tính mặc định của annotation vẫn dùng cho request mới.
        mockMvc.perform(get("/api/reports"))
            .andExpect(status().isOk());
    }
}
```

Kết quả cần đọc theo từng request:

| Thứ tự | Danh tính hiệu lực | Cách chuẩn bị | Kết quả với HTTP Basic |
| --- | --- | --- | --- |
| 1 | reader / `ROLE_READER` | `@WithMockUser` | `200` |
| 2 | writer / `ROLE_WRITER` | `.with(user(...))` | `403` |
| 3 | admin / `ROLE_ADMIN` | `.with(user(...))` | `200` |
| 4 | anonymous | `.with(anonymous())` | `401` |
| 5 | reader / `ROLE_READER` | Trở lại context mặc định | `200` |

Ca thứ hai chứng minh request processor ghi đè danh tính mặc định ở request đó. Ca thứ năm chứng minh việc ghi đè không biến annotation thành một trạng thái writer/anonymous cho toàn bộ method. Cách viết này rất hữu ích khi muốn so sánh nhiều principal trong cùng một kịch bản nghiệp vụ.

**Lưu ý về response:** các mã `401` và `403` trong bảng dựa trên cấu hình HTTP Basic. Nếu ứng dụng dùng form login, request anonymous có thể nhận redirect `302`. Một người dùng đã xác thực nhưng thiếu quyền thường nhận `403`. Hãy kiểm tra `AuthenticationEntryPoint` và `AccessDeniedHandler` thực tế của ứng dụng.

## 5. Kết hợp annotation và processor cho request thay đổi trạng thái

Khi kiểm tra `POST`, `PUT`, `PATCH` hoặc `DELETE`, cần tách quyết định phân quyền khỏi kiểm tra CSRF. Trong cấu hình ví dụ, `POST /api/reports` yêu cầu `ADMIN` và CSRF đang bật.

```java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
@WithMockUser(username = "reader", roles = "READER")
void adminOverrideMustAlsoHaveValidCsrf() throws Exception {

    // Đã ghi đè reader thành admin, nhưng request thiếu CSRF.
    mockMvc.perform(post("/api/reports")
            .with(user("admin").roles("ADMIN")))
        .andExpect(status().isForbidden());

    // Cùng danh tính admin, thêm CSRF token hợp lệ.
    mockMvc.perform(post("/api/reports")
            .with(user("admin").roles("ADMIN"))
            .with(csrf()))
        .andExpect(status().isCreated());

    // Request không ghi đè vẫn dùng reader mặc định; CSRF hợp lệ
    // nhưng reader không có quyền ADMIN.
    mockMvc.perform(post("/api/reports")
            .with(csrf()))
        .andExpect(status().isForbidden());
}
```

Ba kết quả có ba cách giải thích:

1. Admin thiếu CSRF: `403` do CSRF filter chặn request.
2. Admin có CSRF: `201` vì vượt qua CSRF và có `ROLE_ADMIN`.
3. Reader có CSRF: `403` do thiếu quyền `ROLE_ADMIN`.

Test thứ ba rất quan trọng: nếu chỉ kiểm tra một response `403`, ta không biết request bị chặn bởi CSRF hay authorization. Thêm token hợp lệ giúp cô lập điều kiện phân quyền. Ngược lại, test thiếu token phải giữ danh tính đủ quyền để xác nhận CSRF đang bảo vệ endpoint.

## 6. Kết hợp `@WithUserDetails` với request post-processor

`@WithUserDetails` phù hợp khi ứng dụng có một `UserDetailsService` thực sự tạo principal tùy chỉnh và bài test muốn dùng principal được service tải làm mặc định:

```java
@Test
@WithUserDetails("alice")
void userDetailsServiceProvidesDefaultPrincipal() throws Exception {
    mockMvc.perform(get("/api/profile"))
           .andExpect(status().isOk());
}
```

Annotation này tải `UserDetails` từ bean `UserDetailsService` trong test context để tạo `SecurityContext`. Nó **không gửi mật khẩu của Alice qua HTTP** và không thực hiện xác thực login. Nếu cần kiểm tra một request với người dùng khác, có thể dùng `.with(user(otherUserDetails))` trên request tương ứng, miễn là principal đó triển khai `UserDetails` và phù hợp với controller.

Ví dụ khái niệm:

```java
@Test
@WithUserDetails("alice")
void loadedPrincipalIsDefaultButOneRequestUsesBob() throws Exception {

    // Dùng UserDetails được tải cho Alice.
    mockMvc.perform(get("/api/profile"))
           .andExpect(status().isOk());

    UserDetails bob = User.withUsername("bob")
            .password("unused")
            .authorities("ROLE_USER")
            .build();

    // Request này dùng Bob thay cho Alice.
    mockMvc.perform(get("/api/profile")
            .with(user(bob)))
           .andExpect(status().isOk());

    // Request mới không override quay lại principal mặc định Alice.
    mockMvc.perform(get("/api/profile"))
           .andExpect(status().isOk());
}
```

Đoạn trên giả định ứng dụng có bean `UserDetailsService` trả về Alice và endpoint hồ sơ cho phép cả Alice lẫn Bob. Nếu endpoint yêu cầu principal domain tùy chỉnh, fixture Bob phải dùng đúng implementation mà controller cần.

## 7. Khi nào nên dùng `authentication(...)` hoặc `securityContext(...)`?

Annotation người dùng thường đủ cho các test role đơn giản. Nhưng có trường hợp controller hoặc service phụ thuộc loại authentication cụ thể, chẳng hạn `JwtAuthenticationToken` hoặc principal không triển khai `UserDetails`. Khi đó, request processor có thể ghi đè danh tính mặc định bằng đối tượng chính xác:

```java
Authentication customAuth =
        UsernamePasswordAuthenticationToken.authenticated(
                new TenantPrincipal("alice", "acme"),
                null,
                List.of(new SimpleGrantedAuthority("reports:read"))
        );

mockMvc.perform(get("/api/tenant-reports")
        .with(authentication(customAuth)))
    .andExpect(status().isOk());
```

Nếu đã chuẩn bị sẵn cả context, dùng `.with(securityContext(context))`:

```java
SecurityContext requestContext = SecurityContextHolder.createEmptyContext();
requestContext.setAuthentication(customAuth);

mockMvc.perform(get("/api/tenant-reports")
        .with(securityContext(requestContext)))
    .andExpect(status().isOk());
```

Khi request có `authentication(...)` hoặc `securityContext(...)`, đó là danh tính tường minh của request, thay cho danh tính mặc định từ annotation. Tránh ghép nhiều processor cùng ghi context trong một request; hãy chọn một cách duy nhất để kết quả dễ đọc và không phụ thuộc thứ tự.

## 8. Phạm vi và vòng đời của annotation cùng request processor

Để kết hợp chính xác, cần phân biệt các phạm vi:

| Thành phần | Phạm vi | Vòng đời |
| --- | --- | --- |
| `@WithMockUser` ở class | Mặc định cho các test method của class | Spring Security Test thiết lập trước từng method và dọn context theo test lifecycle |
| `@WithMockUser` ở method | Test method đó | Được chuẩn bị trước khi method chạy |
| `@WithUserDetails` | Test method/class tương tự annotation người dùng | Tải principal qua `UserDetailsService` của test context |
| `.with(user(...))` | Request `MockMvc.perform(...)` cụ thể | Chỉ áp dụng cho request được xây dựng |
| `.with(anonymous())` | Request cụ thể | Tạo trạng thái khách cho request đó |
| `.with(csrf())` | Request cụ thể | Thêm CSRF token test vào request |

Annotation không tạo ra session đăng nhập production. Request processor cũng không tự ghi một tài khoản vào database hay bảo đảm context sẽ tồn tại cho HTTP request kế tiếp. Nếu muốn kiểm tra lưu/khôi phục `SecurityContext` qua session, cần test luồng login/session thật và dùng cùng `MockHttpSession` theo cấu hình ứng dụng.

Cũng không nên sửa trực tiếp `SecurityContextHolder.getContext()` để thay đổi danh tính giữa các request trong cùng test nếu mục tiêu là kiểm tra request-specific identity. Việc đó thay đổi context trên thread hiện hành, làm test khó đọc và có nguy cơ ảnh hưởng test khác nếu dọn dẹp không đúng. `.with(...)` biểu đạt rõ danh tính nào thuộc request nào.

## 9. Các lỗi thường gặp khi kết hợp hai cơ chế

### Gắn annotation nhưng quên request cần override

Nếu method có `@WithMockUser(roles = "ADMIN")` thì một request không có `.with(...)` sẽ dùng quyền ADMIN. Đừng dùng cấu hình mặc định quá mạnh cho test kiểm tra quyền hạn chế mà quên override bằng người dùng thường hoặc anonymous. Chọn một default gần với tình huống thông thường của method.

### Dùng `user("alice")` để mô phỏng khách vô danh

`user("anonymousUser")` vẫn tạo một authentication người dùng giả lập; tên principal trùng với chuỗi mặc định của anonymous không biến nó thành `AnonymousAuthenticationToken`. Dùng `.with(anonymous())` để kiểm tra khách chưa đăng nhập.

### Nghĩ request processor thay đổi annotation cho cả method

`.with(user(...))` chỉ chuẩn bị danh tính cho request được gọi. Nó không thay đổi annotation hoặc `TestSecurityContextHolder` làm mặc định cho các request tiếp theo. Có thể kiểm chứng bằng cách gửi một request override rồi gửi request không override trong cùng method.

### Ghép nhiều processor cùng đặt danh tính

Không nên ghép `.with(user(...))` và `.with(authentication(...))` trên cùng một request rồi dựa vào thứ tự để quyết định danh tính. Chọn một processor danh tính. Có thể ghép nó với processor độc lập như `csrf()`.

### Đọc `403` mà không xác định bộ lọc đã từ chối

`403` có thể do thiếu role, CSRF, hoặc logic nghiệp vụ. Với request thay đổi trạng thái, thêm CSRF token hợp lệ khi kiểm tra authorization và giữ một test riêng cho CSRF bị thiếu/sai. Với tenant hoặc ownership rule, kiểm tra body hoặc tương tác controller để xác định tầng từ chối.

### Dùng `@WithMockUser` với principal không đúng kiểu

`@WithMockUser` cung cấp principal chuẩn. Nếu controller dùng `@AuthenticationPrincipal CustomPrincipal`, annotation này có thể không đáp ứng kiểu dữ liệu. Hãy dùng `@WithUserDetails` nếu service trả về custom `UserDetails`, hoặc `.with(user(customUserDetails))`/`.with(authentication(customAuth))` để cung cấp đúng principal.

### Tắt filter chain khi muốn kiểm tra authorization

`@AutoConfigureMockMvc(addFilters = false)` hoặc `standaloneSetup(...)` thiếu Spring Security filter có thể khiến request không đi qua quy tắc thật. Bảo đảm `MockMvc` tích hợp Spring Security, rồi kiểm tra cả trường hợp được phép và bị từ chối.

## 10. Ranh giới Servlet và Reactive

Các ví dụ `@WithMockUser` kết hợp `.with(...)` trong bài sử dụng Spring Security Test cho Servlet và `MockMvc`. Với WebFlux, request được gửi bằng `WebTestClient` và request-specific security configurers qua `mutateWith(...)`, chẳng hạn `mockUser()` hoặc `mockJwt()`:

```java
WebTestClient securedClient = WebTestClient
        .bindToApplicationContext(applicationContext)
        .apply(SecurityMockServerConfigurers.springSecurity())
        .configureClient()
        .build();

securedClient
    .mutateWith(SecurityMockServerConfigurers.mockUser("admin")
            .roles("ADMIN"))
    .get()
    .uri("/api/reports")
    .exchange()
    .expectStatus().isOk();
```

Đoạn code trên minh họa request Reactive có người dùng ADMIN được giả lập. Nó không sử dụng `SecurityMockMvcRequestPostProcessors`. Khi cần danh tính mặc định hoặc context test trong WebFlux, sử dụng các hỗ trợ test Reactive tương ứng và kiểm tra cách chúng được truyền qua Reactor Context. Không giả định Servlet thread-local context tự động được WebFlux sử dụng.

## 11. Bài tập: lập ma trận danh tính trong một test method

Giả sử `GET /api/invoices` cho phép `ACCOUNTANT` và `ADMIN`; `POST /api/invoices` chỉ cho phép `ADMIN` và có CSRF bật. Hãy viết một test method với `@WithMockUser(username = "accountant", roles = "ACCOUNTANT")` rồi thêm request processor để kiểm tra:

1. Request GET không override: accountant được phép.
2. Request GET với `user("clerk").roles("CLERK")`: bị `403`.
3. Request GET với `user("admin").roles("ADMIN")`: được phép.
4. Request GET với `anonymous()`: bị yêu cầu xác thực theo entry point.
5. Request POST với `user("admin").roles("ADMIN")` nhưng thiếu CSRF: bị `403` do CSRF.
6. Request POST với cùng danh tính admin và `csrf()` hợp lệ: được phép.
7. Request POST có `csrf()` nhưng không override danh tính mặc định accountant: bị `403` do thiếu quyền ADMIN.
8. Request GET cuối cùng không override: vẫn dùng accountant từ annotation.

Khi đọc kết quả, ghi lại **danh tính mặc định**, **processor đã áp dụng**, **authority hiệu lực**, **CSRF token** và **tầng tạo response**. Annotation giúp giảm lặp lại fixture chung; request post-processor cho phép kiểm tra các ngoại lệ có chủ đích ngay trên từng request. Phối hợp hai cơ chế như vậy tạo ra test dễ đọc, xác định rõ danh tính và có thể phân biệt nguyên nhân được phép hoặc bị từ chối.
