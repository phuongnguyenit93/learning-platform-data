# AccessDeniedHandler và phản hồi không đủ quyền

## 1. Khi người dùng đã đăng nhập nhưng không được phép

Một người dùng có thể đăng nhập thành công nhưng vẫn không được phép thực hiện mọi thao tác. Ví dụ, tài khoản **lan** có quyền **REPORT_READ** nên đọc được báo cáo, nhưng không có quyền **REPORT_DELETE** nên không được xóa báo cáo. Ứng dụng cần phản hồi nhất quán khi yêu cầu bị từ chối, đồng thời không làm lộ chi tiết bảo mật nội bộ.

Trong Spring Security Servlet, **AccessDeniedHandler** chịu trách nhiệm xử lý một yêu cầu bị từ chối do không đủ quyền. Đây là phần cuối quan trọng của luồng phân quyền HTTP: sau khi security filter hoặc method security phát hiện người gọi không được phép, handler có thể trả **403 Forbidden**, tạo response JSON hoặc chuyển hướng đến trang lỗi.

Bài học thuộc chương **Kiểm thử thành phần** của mô-đun **SPRING_SECURITY_TESTING**. Mô-đun hướng tới kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng **spring-security-test** trên ứng dụng Servlet và Reactive, với **MockMvc**, **WebTestClient**, **@WithMockUser**, **SecurityContext** và JWT/OAuth2/OIDC giả lập. Bài này tập trung vào phản hồi khi người gọi **đã được xác thực nhưng thiếu quyền**, đồng thời phân biệt trường hợp anonymous cần **AuthenticationEntryPoint**.

Sau khi học, bạn có thể:

- Giải thích hợp đồng **AccessDeniedHandler.handle(...)** và vị trí của nó trong filter chain.
- Phân biệt **AccessDeniedHandler**, **AuthenticationEntryPoint** và **AuthenticationFailureHandler**.
- Kiểm thử handler mặc định và handler JSON tùy chỉnh trực tiếp.
- Kiểm tra response **403**, nội dung JSON và header qua **MockMvc**.
- Phân biệt lỗi authorization với lỗi CSRF cũng trả **403**.
- Kiểm thử tương ứng trong WebFlux bằng **ServerAccessDeniedHandler** và **WebTestClient**.

## 2. AccessDeniedHandler làm gì?

Giao diện Servlet **org.springframework.security.web.access.AccessDeniedHandler** có phương thức:

~~~java
public interface AccessDeniedHandler {
    void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            AccessDeniedException accessDeniedException)
            throws IOException, ServletException;
}
~~~

Khi được gọi, handler nhận request, response và **AccessDeniedException**. Nó quyết định cách biểu diễn việc từ chối truy cập ra HTTP. Handler không cấp quyền, không xác thực lại mật khẩu và không tự thay đổi authorities của người dùng.

Triển khai mặc định phổ biến là **AccessDeniedHandlerImpl**. Nếu không cấu hình trang lỗi, nó gửi lỗi **403**. Nếu được cấu hình error page, nó đặt ngoại lệ vào request attribute rồi forward đến trang đó. Với REST API, nhiều ứng dụng dùng handler tùy chỉnh để trả JSON theo schema lỗi thống nhất.

| Thành phần | Khi nào được dùng | Phản hồi điển hình |
| --- | --- | --- |
| **AccessDeniedHandler** | Người gọi đã xác thực đầy đủ nhưng không có quyền | **403 Forbidden**, trang lỗi hoặc JSON |
| **AuthenticationEntryPoint** | Người gọi chưa xác thực và cần bắt đầu cơ chế đăng nhập | **401** challenge hoặc redirect login |
| **AuthenticationFailureHandler** | Một lần đăng nhập chủ động, ví dụ form login, thất bại | Redirect trang lỗi hoặc response theo cấu hình |
| **AuthorizationManager** | Đưa ra quyết định cho phép/từ chối truy cập | Cho phép hoặc ném/tạo quyết định từ chối; không trực tiếp định dạng response HTTP |

### Luồng ExceptionTranslationFilter

Trong Servlet, **ExceptionTranslationFilter** bắt các ngoại lệ bảo mật phát sinh ở phần filter chain phía sau nó. Khi gặp **AccessDeniedException**, nó kiểm tra trạng thái xác thực:

- Nếu người gọi là anonymous hoặc chưa được xác thực đầy đủ, filter thường gọi **AuthenticationEntryPoint** để yêu cầu đăng nhập.
- Nếu người gọi đã xác thực đầy đủ, filter gọi **AccessDeniedHandler** để trả phản hồi không đủ quyền.

~~~mermaid
flowchart TD
    A["Request tới tài nguyên được bảo vệ"] --> B["Authorization rule / method security"]
    B --> C{"Người gọi có đủ quyền?"}
    C -- "Có" --> D["Tiếp tục xử lý request"]
    C -- "Không" --> E["AccessDeniedException"]
    E --> F["ExceptionTranslationFilter"]
    F --> G{"Đã xác thực đầy đủ?"}
    G -- "Chưa / anonymous" --> H["AuthenticationEntryPoint"]
    H --> I["401 challenge hoặc redirect"]
    G -- "Rồi" --> J["AccessDeniedHandler.handle(...)"]
    J --> K["403 / JSON / trang lỗi"]
~~~

Đây là luồng phổ biến khi ngoại lệ đi qua **ExceptionTranslationFilter**. Một filter khác có thể tự xử lý từ chối trước đó. CSRF filter cũng có handler riêng để xử lý **AccessDeniedException** do token CSRF thiếu hoặc không hợp lệ. Vì vậy, nhận được **403** không tự động chứng minh rule role/authority đã từ chối request.

## 3. Kiểm thử AccessDeniedHandler mặc định

Có thể dùng trực tiếp **AccessDeniedHandlerImpl** khi ứng dụng chỉ cần phản hồi **403** hoặc forward đến trang lỗi:

~~~java
import org.springframework.security.web.access.AccessDeniedHandlerImpl;

AccessDeniedHandlerImpl handler = new AccessDeniedHandlerImpl();
~~~

Để kiểm thử hành vi mặc định không cấu hình error page:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.web.access.AccessDeniedHandlerImpl;

import static org.assertj.core.api.Assertions.assertThat;

class AccessDeniedHandlerImplTest {

    @Test
    void sendsForbiddenWhenNoErrorPageIsConfigured() throws Exception {
        AccessDeniedHandlerImpl handler = new AccessDeniedHandlerImpl();
        MockHttpServletRequest request = new MockHttpServletRequest();
        MockHttpServletResponse response = new MockHttpServletResponse();

        handler.handle(
                request,
                response,
                new AccessDeniedException("Insufficient authority"));

        assertThat(response.getStatus()).isEqualTo(403);
    }
}
~~~

Test trên xác minh status, không xác minh JSON body hay trang HTML. Nếu cấu hình **setErrorPage(...)**, handler sẽ forward đến trang đã chọn; khi đó cần kiểm thử hành vi forward và request attribute tương ứng, không kỳ vọng cùng cách xử lý như REST API.

## 4. Xây dựng AccessDeniedHandler trả JSON

REST API thường cần response lỗi ổn định để client xử lý. Ví dụ dưới đây trả **403**, content type JSON và một mã lỗi công khai. Nội dung ngoại lệ nội bộ không được trả trực tiếp cho client.

~~~java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;

import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.web.access.AccessDeniedHandler;

final class JsonAccessDeniedHandler implements AccessDeniedHandler {

    private final ObjectMapper objectMapper;

    JsonAccessDeniedHandler(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public void handle(
            HttpServletRequest request,
            HttpServletResponse response,
            AccessDeniedException exception)
            throws IOException, ServletException {

        response.setStatus(HttpServletResponse.SC_FORBIDDEN);
        response.setContentType(MediaType.APPLICATION_JSON_VALUE);
        response.setCharacterEncoding(StandardCharsets.UTF_8.name());

        objectMapper.writeValue(response.getOutputStream(), Map.of(
                "error", "forbidden",
                "message", "You do not have permission to access this resource",
                "path", request.getRequestURI()));
    }
}
~~~

Response ví dụ:

~~~json
{
  "error": "forbidden",
  "message": "You do not have permission to access this resource",
  "path": "/api/admin/reports"
}
~~~

Không đưa **exception.getMessage()** hoặc stack trace vào response công khai. Nội dung ngoại lệ có thể chứa tên tài nguyên, quy tắc nội bộ hoặc thông tin nhạy cảm. Nếu cần ghi log, hãy dùng logging có kiểm soát và không ghi token hay credentials.

### Kiểm thử JSON handler trực tiếp

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.access.AccessDeniedException;

import static org.assertj.core.api.Assertions.assertThat;

class JsonAccessDeniedHandlerTest {

    private final JsonAccessDeniedHandler handler =
            new JsonAccessDeniedHandler(new ObjectMapper());

    @Test
    void writesForbiddenJsonWithoutLeakingInternalMessage()
            throws Exception {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.setRequestURI("/api/admin/reports");
        MockHttpServletResponse response = new MockHttpServletResponse();

        handler.handle(
                request,
                response,
                new AccessDeniedException("internal rule id 987"));

        assertThat(response.getStatus()).isEqualTo(403);
        assertThat(response.getContentType())
                .isEqualTo(MediaType.APPLICATION_JSON_VALUE);

        String body = response.getContentAsString();
        assertThat(body).contains("\"error\":\"forbidden\"");
        assertThat(body).contains("\"path\":\"/api/admin/reports\"");
        assertThat(body).doesNotContain("internal rule id 987");
    }
}
~~~

Test xác nhận status, content type, các trường response ổn định và việc không rò rỉ thông báo nội bộ. Nếu thứ tự thuộc tính JSON không thuộc hợp đồng, tránh so sánh toàn bộ body như chuỗi; parse JSON rồi kiểm tra từng field.

## 5. Cấu hình handler trong SecurityFilterChain

Đăng ký handler cho các request HTTP bị từ chối:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.access.AccessDeniedHandler;

@Configuration
class ApiAuthorizationConfiguration {

    @Bean
    AccessDeniedHandler apiAccessDeniedHandler(ObjectMapper objectMapper) {
        return new JsonAccessDeniedHandler(objectMapper);
    }

    @Bean
    SecurityFilterChain apiSecurityFilterChain(
            HttpSecurity http,
            AccessDeniedHandler apiAccessDeniedHandler) throws Exception {

        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/reports/**")
                    .hasAuthority("REPORT_READ")
                .requestMatchers("/api/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated());

        http.exceptionHandling(exceptions -> exceptions
                .accessDeniedHandler(apiAccessDeniedHandler));

        return http.build();
    }
}
~~~

Đoạn cấu hình minh họa ứng dụng Servlet; cần có **Authentication** hợp lệ được tạo bởi cơ chế xác thực của ứng dụng. Khi người đã đăng nhập thiếu quyền, **ExceptionTranslationFilter** có thể gọi handler đã cấu hình. Nếu người gọi anonymous, entry point vẫn có thể được gọi thay vì handler này.

Một số filter như **CsrfFilter** có thể được cấu hình dùng **AccessDeniedHandler** riêng. Nếu muốn cùng schema JSON cho lỗi CSRF, cần kiểm tra cách cấu hình CSRF của ứng dụng và bảo đảm handler tương ứng được sử dụng. Không giả định **exceptionHandling().accessDeniedHandler(...)** tự động thay thế mọi handler bên trong tất cả filter.

## 6. Kiểm thử HTTP bằng MockMvc

Giả sử ứng dụng có:

- Endpoint **GET /api/reports/42** yêu cầu authority **REPORT_READ**.
- Endpoint **GET /api/admin/reports** yêu cầu role **ADMIN**.
- **JsonAccessDeniedHandler** được cấu hình như mục 5.
- Spring Boot test context đã bật Spring Security và controller tương ứng tồn tại.

Ta có thể dùng **@WithMockUser** để kiểm tra nhánh đã xác thực nhưng thiếu quyền:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AccessDeniedHttpTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    @WithMockUser(username = "lan", authorities = "REPORT_READ")
    void readerCanAccessReport() throws Exception {
        mockMvc.perform(get("/api/reports/42"))
                .andExpect(status().isOk());
    }

    @Test
    @WithMockUser(username = "lan", authorities = "REPORT_READ")
    void readerCannotAccessAdminAndReceivesJson403() throws Exception {
        mockMvc.perform(get("/api/admin/reports"))
                .andExpect(status().isForbidden())
                .andExpect(content().contentTypeCompatibleWith("application/json"))
                .andExpect(content().json("""
                        {
                          "error": "forbidden",
                          "message": "You do not have permission to access this resource",
                          "path": "/api/admin/reports"
                        }
                        """));
    }

    @Test
    @WithMockUser(username = "admin", roles = "ADMIN")
    void adminCanAccessAdminResource() throws Exception {
        mockMvc.perform(get("/api/admin/reports"))
                .andExpect(status().isOk());
    }
}
~~~

Các test giả định endpoint được triển khai và trả **200** khi controller chạy thành công. **@WithMockUser** dựng **Authentication** trong **SecurityContext**; nó không kiểm tra mật khẩu, **UserDetailsService**, **AuthenticationProvider** hay JWT signature. Mục tiêu của nhóm test này là chứng minh quy tắc phân quyền và handler phản hồi đúng khi user đã được xác thực.

### Kiểm tra anonymous đi qua entry point

Một request không đăng nhập đến endpoint yêu cầu quyền thường cần **AuthenticationEntryPoint**, không phải handler này. Nếu ứng dụng dùng HTTP Basic, có thể kiểm thử riêng:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.httpBasic;

@Test
void anonymousRequestGetsUnauthorizedResponse() throws Exception {
    mockMvc.perform(get("/api/admin/reports"))
            .andExpect(status().isUnauthorized());
}

@Test
void invalidCredentialsDoNotBecomeAccessDeniedResponse() throws Exception {
    mockMvc.perform(get("/api/admin/reports")
                    .with(httpBasic("lan", "wrong-password")))
            .andExpect(status().isUnauthorized());
}
~~~

Hai ca này kiểm tra nhánh xác thực và entry point. Mã **401** giả định ứng dụng cấu hình HTTP Basic với entry point phù hợp. Nếu dùng form login, response anonymous có thể là redirect **302**; nếu dùng JSON entry point, body có thể là JSON **401**. Không gộp các test này vào test **403** rồi kết luận cùng một handler tạo ra mọi response.

## 7. Phân biệt 403 do authorization với 403 do CSRF

Một trong những nguyên nhân phổ biến khiến test phân quyền sai là bỏ quên CSRF. Khi CSRF đang bật, request **POST**, **PUT**, **PATCH** hoặc **DELETE** có thể bị chặn trước khi đến controller hoặc quy tắc quyền nghiệp vụ.

Ví dụ, người dùng có quyền **REPORT_WRITE** nhưng request thiếu CSRF token:

~~~java
@Test
@WithMockUser(username = "minh", authorities = "REPORT_WRITE")
void postWithoutCsrfIsRejectedByCsrfProtection() throws Exception {
    mockMvc.perform(post("/api/reports"))
            .andExpect(status().isForbidden());
}
~~~

Để chứng minh người dùng **thiếu quyền ghi**, phải cung cấp CSRF token hợp lệ trước:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;

@Test
@WithMockUser(username = "lan", authorities = "REPORT_READ")
void readerWithoutWriteAuthorityIsDeniedAfterCsrfPasses()
        throws Exception {
    mockMvc.perform(post("/api/reports").with(csrf()))
            .andExpect(status().isForbidden());
}
~~~

Ở test đầu, **403** có thể được tạo bởi handler CSRF của **CsrfFilter**; test thứ hai mới cô lập quy tắc authorization sau khi CSRF hợp lệ. Nếu ứng dụng tắt CSRF cho API stateless, hành vi sẽ khác và test phải phản ánh cấu hình thực tế.

## 8. AccessDeniedHandler cho OAuth2 Resource Server

Với bearer token, Spring Security có **BearerTokenAccessDeniedHandler** để tạo phản hồi từ chối theo giao thức OAuth2. Khi token hợp lệ nhưng thiếu scope cần thiết, server thường trả **403** và header **WWW-Authenticate** có thông tin **insufficient_scope**.

Ví dụ cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ResourceServerSecurityConfiguration {

    @Bean
    SecurityFilterChain resourceServerChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/reports/**")
                    .hasAuthority("SCOPE_reports.read")
                .anyRequest().authenticated());

        http.oauth2ResourceServer(resourceServer ->
                resourceServer.jwt(org.springframework.security.config.Customizer
                        .withDefaults()));

        http.exceptionHandling(exceptions -> exceptions
                .accessDeniedHandler(new BearerTokenAccessDeniedHandler()));

        return http.build();
    }
}
~~~

Đây là cấu hình minh họa; resource server còn cần cấu hình decoder/issuer phù hợp. **BearerTokenAccessDeniedHandler** dành cho trường hợp đã xác thực bearer nhưng không đủ quyền. Token thiếu hoặc không hợp lệ thường đi qua **BearerTokenAuthenticationEntryPoint** và trả **401**.

Trong test authorization, **jwt()** của **spring-security-test** tạo ngữ cảnh JWT giả lập:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;

@Test
void validJwtWithoutRequiredScopeIsForbidden() throws Exception {
    mockMvc.perform(get("/api/reports/42")
                    .with(jwt().authorities(
                            new SimpleGrantedAuthority("SCOPE_profile.read"))))
            .andExpect(status().isForbidden());
}
~~~

Test này chứng minh người dùng giả lập đã xác thực nhưng thiếu scope **SCOPE_reports.read**. Nó không xác minh chữ ký, issuer, audience hoặc thời hạn của JWT thật. Muốn kiểm tra **BearerTokenAccessDeniedHandler** được gọi với token thật, cần test resource server/decoder phù hợp; đừng coi **jwt()** là bằng chứng cho bước xác minh token.

## 9. Kiểm thử method security và AccessDeniedException

Phân quyền không chỉ xuất hiện ở URL. Một service có thể dùng **@PreAuthorize** để bảo vệ hành động nghiệp vụ:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
class ReportService {

    @PreAuthorize("hasAuthority('REPORT_DELETE')")
    public void deleteReport(String reportId) {
        // Thực hiện thao tác xóa sau khi được cấp quyền.
    }
}
~~~

Để test annotation, ứng dụng cần bật method security (ví dụ **@EnableMethodSecurity**) và gọi bean thông qua Spring proxy. Nếu tự tạo **new ReportService()**, test sẽ bỏ qua proxy và không kích hoạt kiểm tra bảo mật.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest
class ReportServiceMethodSecurityTest {

    @Autowired
    ReportService reportService;

    @Test
    @WithMockUser(username = "lan", authorities = "REPORT_READ")
    void readerCannotDeleteReport() {
        assertThatThrownBy(() -> reportService.deleteReport("42"))
                .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    @WithMockUser(username = "minh", authorities = "REPORT_DELETE")
    void userWithDeleteAuthorityCanDeleteReport() {
        reportService.deleteReport("42");
    }
}
~~~

Test method trực tiếp khẳng định **AccessDeniedException** được ném khi thiếu quyền. Nó chưa khẳng định response HTTP JSON vì chưa có request đi qua servlet filter chain. Khi gọi service từ controller trong một request HTTP, ngoại lệ có thể được **ExceptionTranslationFilter** chuyển thành response **403**, trừ khi một lớp xử lý khác như exception resolver của MVC xử lý trước. Cần test HTTP nếu response cuối cùng là hợp đồng cần bảo vệ.

## 10. AccessDeniedHandler trong Spring WebFlux

Reactive stack sử dụng **ServerAccessDeniedHandler**, nhận **ServerWebExchange** và **AccessDeniedException**, rồi trả **Mono<Void>**:

~~~java
public interface ServerAccessDeniedHandler {
    Mono<Void> handle(
            ServerWebExchange exchange,
            AccessDeniedException denied);
}
~~~

Một handler mặc định là **HttpStatusServerAccessDeniedHandler**, thường trả **403**. Handler JSON tùy chỉnh có thể ghi response qua **ServerHttpResponse**:

~~~java
import java.util.Map;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.web.server.authorization.ServerAccessDeniedHandler;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

final class JsonServerAccessDeniedHandler
        implements ServerAccessDeniedHandler {

    private final ObjectMapper objectMapper;

    JsonServerAccessDeniedHandler(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public Mono<Void> handle(
            ServerWebExchange exchange,
            AccessDeniedException denied) {
        var response = exchange.getResponse();
        response.setStatusCode(HttpStatus.FORBIDDEN);
        response.getHeaders().setContentType(MediaType.APPLICATION_JSON);

        byte[] body;
        try {
            body = objectMapper.writeValueAsBytes(Map.of(
                    "error", "forbidden",
                    "message", "You do not have permission to access this resource",
                    "path", exchange.getRequest().getPath().value()));
        } catch (JsonProcessingException ex) {
            return Mono.error(ex);
        }

        var buffer = response.bufferFactory().wrap(body);
        return response.writeWith(Mono.just(buffer));
    }
}
~~~

Đây là ví dụ tối giản. Trong ứng dụng thực, cần bảo đảm response chưa được commit, chỉ ghi body một lần và có chính sách xử lý lỗi serialization rõ ràng.

### Kiểm thử Reactive handler

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.mock.web.server.MockServerWebExchange;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.security.access.AccessDeniedException;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class JsonServerAccessDeniedHandlerTest {

    @Test
    void writesForbiddenJsonResponse() {
        JsonServerAccessDeniedHandler handler =
                new JsonServerAccessDeniedHandler(new ObjectMapper());
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/api/admin/reports").build());

        StepVerifier.create(handler.handle(
                        exchange,
                        new AccessDeniedException("internal rule")))
                .verifyComplete();

        assertThat(exchange.getResponse().getStatusCode())
                .isEqualTo(HttpStatus.FORBIDDEN);
        assertThat(exchange.getResponse().getHeaders().getContentType())
                .isEqualTo(MediaType.APPLICATION_JSON);
    }
}
~~~

Test này kiểm tra status và header; nếu cần xác minh body, dùng response buffer được ghi trong exchange hoặc test tích hợp **WebTestClient**.

### Kiểm thử HTTP Reactive bằng WebTestClient

Giả sử ứng dụng WebFlux có **SecurityWebFilterChain** cấu hình **ServerAccessDeniedHandler** JSON, endpoint **/api/admin/reports** yêu cầu **ROLE_ADMIN**, và endpoint thực sự tồn tại:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;

@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveAccessDeniedHttpTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void authenticatedReaderGetsJson403ForAdminResource() {
        webTestClient.mutateWith(mockUser("lan").roles("READER"))
                .get()
                .uri("/api/admin/reports")
                .exchange()
                .expectStatus().isForbidden()
                .expectHeader().contentTypeCompatibleWith("application/json")
                .expectBody()
                .jsonPath("$.error").isEqualTo("forbidden");
    }
}
~~~

Test này giả lập người dùng đã xác thực trong Reactive Security context, nên tập trung vào authorization và handler. Nếu cần kiểm tra credentials thật, phải dùng cơ chế đăng nhập thực của ứng dụng và cấu hình provider tương ứng.

## 11. Các lỗi thường gặp

**Gọi AccessDeniedHandler cho anonymous.** Anonymous truy cập tài nguyên cần đăng nhập thường được chuyển đến **AuthenticationEntryPoint**. Handler từ chối quyền chủ yếu xử lý người đã xác thực đầy đủ nhưng không được phép.

**Nhầm 403 với 401.** **401** yêu cầu client xác thực hoặc cung cấp credentials hợp lệ; **403** cho biết danh tính đã được xác nhận nhưng không đủ quyền. Entry point và access denied handler có nhiệm vụ khác nhau.

**Coi mọi 403 là lỗi authorization.** CSRF, method security, URL rule hoặc handler tùy chỉnh đều có thể tạo **403**. Cần xác định lớp nào từ chối request trước khi viết assertion.

**Chỉ test handler trực tiếp.** Test **handle(...)** không chứng minh handler đã được cấu hình trong **SecurityFilterChain**. Thêm một test **MockMvc** với user đã xác thực và thiếu quyền.

**Dùng @WithMockUser để kiểm tra mật khẩu.** Annotation tạo sẵn **Authentication**, không chạy **UserDetailsService** hoặc **PasswordEncoder**. Dùng HTTP Basic/form login với provider thật khi cần kiểm tra xác thực.

**Trả exception message cho client.** Nội dung ngoại lệ có thể tiết lộ rule nội bộ hoặc dữ liệu nhạy cảm. Response nên dùng mã lỗi công khai ổn định.

**Dùng handler Servlet trong Reactive.** **AccessDeniedHandler** dùng servlet request/response; WebFlux cần **ServerAccessDeniedHandler** với **ServerWebExchange** và **Mono<Void>**.

**Không kiểm tra quyền ở method security.** URL có thể được bảo vệ nhưng một lời gọi nội bộ đến service vẫn thiếu kiểm soát. Dùng **@PreAuthorize** cho nghiệp vụ cần thiết và test bean qua Spring proxy.

**Không xác nhận response body/header.** Test chỉ kiểm tra status **403** có thể bỏ sót response HTML thay vì JSON hoặc thiếu header giao thức. Kiểm tra đúng hợp đồng client cần sử dụng.

## 12. Bài thực hành

1. Viết **JsonAccessDeniedHandler** trả **403** và JSON ổn định. Kiểm tra trực tiếp status, content type, path và việc không lộ thông báo ngoại lệ.
2. Cấu hình handler trong **SecurityFilterChain**. Dùng **MockMvc** với **@WithMockUser(authorities = "REPORT_READ")** gọi endpoint chỉ cho **ADMIN**; xác minh JSON **403**.
3. Gửi cùng request ở trạng thái anonymous và xác minh **AuthenticationEntryPoint** tạo phản hồi theo cấu hình. Giải thích vì sao handler từ chối quyền không được gọi.
4. Tạo request **POST** có CSRF và thiếu quyền ghi; so sánh với request không có CSRF để nhận diện hai nguyên nhân **403**.
5. Dùng **BearerTokenAccessDeniedHandler** cho resource server; kiểm tra trường hợp JWT giả lập hợp lệ nhưng thiếu scope. Sau đó mô tả test cần có để xác minh JWT thật.
6. Bật method security cho một service và kiểm tra lời gọi bị từ chối bằng **AccessDeniedException**; xác minh lời gọi HTTP trả response như hợp đồng API.
7. Viết **ServerAccessDeniedHandler** Reactive trả JSON, kiểm tra trực tiếp và qua **WebTestClient**.

Một bộ kiểm thử tốt xác minh được **đúng người gọi bị từ chối, đúng thành phần xử lý ngoại lệ và đúng response mà client nhận được**. Kết hợp test component của handler với test HTTP giúp phân biệt rõ lỗi thiếu quyền, lỗi chưa xác thực và lỗi CSRF trong Spring Security.
