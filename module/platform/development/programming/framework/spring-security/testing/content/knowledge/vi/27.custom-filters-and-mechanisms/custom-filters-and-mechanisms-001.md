# Unit test một filter với request, response và chuỗi xử lý được kiểm soát

## 1. Vì sao cần kiểm thử filter độc lập?

Filter Servlet nằm giữa request từ client và phần xử lý phía sau. Một filter có thể đọc header, chuẩn hóa dữ liệu, tạo `Authentication`, ghi response, hoặc quyết định request có được chuyển tiếp đến filter tiếp theo hay không. Lỗi trong filter có thể làm request bị chặn sai, bỏ qua bước xác thực, giữ `SecurityContext` của request trước hoặc ghi response không đúng.

Kiểm thử trực tiếp một filter giúp xác minh hành vi của nó với request/response được kiểm soát. Ta có thể tạo `MockHttpServletRequest`, `MockHttpServletResponse` và một `FilterChain` giả để quan sát filter gọi tiếp hay kết thúc sớm. Cách này chạy nhanh, không cần khởi động toàn bộ Spring context và giúp khoanh vùng lỗi trong logic của filter.

Bài học thuộc chương **Filter và cơ chế tùy biến** của mô-đun **SPRING_SECURITY_TESTING**. Mô-đun tập trung kiểm chứng xác thực, phân quyền và bảo vệ HTTP trên ứng dụng Servlet và Reactive bằng `spring-security-test`, `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext` và JWT/OAuth2/OIDC giả lập. Bài này tập trung vào unit test cho filter Servlet với request, response và chuỗi xử lý được kiểm soát; test qua `FilterChainProxy`/`MockMvc` sẽ được dùng ở mức tích hợp khi cần kiểm chứng thứ tự và cấu hình thực.

Sau bài học, bạn có thể:

- Phân biệt gọi filter trực tiếp với gửi request qua toàn bộ security filter chain.
- Dùng mock request/response để kiểm tra header, status, body và request attribute.
- Dùng `FilterChain` giả hoặc `MockFilterChain` để kiểm tra request được chuyển tiếp.
- Kiểm thử nhánh tiếp tục, nhánh từ chối, nhánh bỏ qua và xử lý ngoại lệ.
- Kiểm tra `SecurityContext` được đặt trong lúc xử lý và được dọn sau request.
- Kiểm thử filter kế thừa `OncePerRequestFilter`, bao gồm `shouldNotFilter(...)`.
- Nhận biết các trường hợp cần integration test với `MockMvc`.

## 2. Ranh giới của unit test filter

Một unit test filter thường gọi trực tiếp `filter.doFilter(request, response, chain)`. Nó kiểm tra logic bên trong filter và cách filter tương tác với chuỗi được truyền vào.

~~~mermaid
flowchart TD
    A["MockHttpServletRequest"] --> B["Custom Filter"]
    B --> C{"Nhánh xử lý"}
    C -- "Cho đi tiếp" --> D["Controlled FilterChain"]
    D --> E["Quan sát trạng thái trong chain"]
    C -- "Từ chối" --> F["Response / AuthenticationEntryPoint"]
    E --> G["Assert request, response và SecurityContext"]
    F --> G
~~~

Unit test trực tiếp có thể xác minh:

- Filter đọc đúng header, parameter, method hoặc path.
- Filter tạo đúng dữ liệu/token để chuyển sang thành phần kế tiếp.
- Filter gọi `FilterChain.doFilter(...)` đúng nhánh.
- Filter tạo status/header/body đúng khi tự kết thúc request.
- Filter xử lý `AuthenticationException` theo chính sách đã chọn.
- Filter không để lại `SecurityContext` hoặc trạng thái thread-local sau khi hoàn tất.

Unit test trực tiếp **không** tự chứng minh:

- Filter đã được đăng ký trong `SecurityFilterChain`.
- Filter nằm đúng vị trí so với `SecurityContextHolderFilter`, `AnonymousAuthenticationFilter`, `ExceptionTranslationFilter` hoặc `AuthorizationFilter`.
- `FilterChainProxy` chọn đúng chain cho URL.
- CSRF, CORS, session management và các filter khác phối hợp đúng.
- Filter hoạt động đúng trong ứng dụng Spring Boot thực tế.

Đó là lý do nên kết hợp unit test filter với ít nhất một integration test phù hợp khi thay đổi cấu hình bảo mật.

## 3. Ví dụ xuyên suốt: filter xác thực API key theo từng request

Giả sử ứng dụng hỗ trợ một cơ chế API key riêng. Request có header `X-API-Key` sẽ được chuyển thành token chưa xác thực và đưa cho `AuthenticationManager`. Provider được đăng ký với manager chịu trách nhiệm kiểm tra key và trả về `Authentication` đã xác thực.

Filter trong ví dụ này chỉ minh họa việc điều phối:

1. Nếu không có API key, request tiếp tục để cơ chế xác thực khác hoặc authorization rule xử lý.
2. Nếu có API key, filter tạo token chưa xác thực và gọi `AuthenticationManager`.
3. Nếu manager xác thực thành công, filter đặt kết quả vào `SecurityContext` trong phạm vi request rồi gọi chain.
4. Nếu manager ném `AuthenticationException`, filter gọi `AuthenticationEntryPoint` và kết thúc request.
5. Sau khi chain hoàn tất, filter xóa context request-local để không làm rò danh tính sang request khác.

**Lưu ý về thiết kế:** API key không được xem là hợp lệ chỉ vì header tồn tại. Việc so sánh key phải do provider/manager thực hiện bằng nguồn dữ liệu tin cậy. Ví dụ dưới đây dùng `AuthenticationManager` để giữ ranh giới xác thực rõ ràng. Với giao thức thông thường, ưu tiên các filter có sẵn của Spring Security; chỉ viết filter tùy chỉnh khi giao thức hoặc luồng request thực sự cần.

### Token đầu vào chưa xác thực

~~~java
import java.util.List;

import org.springframework.security.authentication.AbstractAuthenticationToken;

final class ApiKeyAuthenticationToken extends AbstractAuthenticationToken {

    private final String apiKey;

    ApiKeyAuthenticationToken(String apiKey) {
        super(List.of());
        this.apiKey = apiKey;
        setAuthenticated(false);
    }

    @Override
    public Object getPrincipal() {
        return null;
    }

    @Override
    public Object getCredentials() {
        return this.apiKey;
    }
}
~~~

Token giữ API key trong credentials và bắt đầu ở trạng thái chưa xác thực. Filter không gọi `setAuthenticated(true)` trên token đầu vào. Một provider đáng tin cậy phải kiểm tra key và trả về token thành công riêng có principal cùng authorities.

### Filter cần kiểm thử

~~~java
import java.io.IOException;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.util.StringUtils;
import org.springframework.web.filter.OncePerRequestFilter;

final class ApiKeyAuthenticationFilter extends OncePerRequestFilter {

    private final AuthenticationManager authenticationManager;
    private final AuthenticationEntryPoint authenticationEntryPoint;

    ApiKeyAuthenticationFilter(
            AuthenticationManager authenticationManager,
            AuthenticationEntryPoint authenticationEntryPoint) {
        this.authenticationManager = authenticationManager;
        this.authenticationEntryPoint = authenticationEntryPoint;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        return request.getServletPath().startsWith("/public/");
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {

        String apiKey = request.getHeader("X-API-Key");
        if (!StringUtils.hasText(apiKey)) {
            filterChain.doFilter(request, response);
            return;
        }

        Authentication authenticated;
        try {
            authenticated = authenticationManager.authenticate(
                    new ApiKeyAuthenticationToken(apiKey));
        } catch (AuthenticationException exception) {
            SecurityContextHolder.clearContext();
            authenticationEntryPoint.commence(
                    request, response, exception);
            return;
        }

        if (authenticated == null || !authenticated.isAuthenticated()) {
            SecurityContextHolder.clearContext();
            authenticationEntryPoint.commence(
                    request,
                    response,
                    new BadCredentialsException("API key was not authenticated"));
            return;
        }

        SecurityContext context = SecurityContextHolder.createEmptyContext();
        context.setAuthentication(authenticated);
        SecurityContextHolder.setContext(context);

        try {
            filterChain.doFilter(request, response);
        } finally {
            SecurityContextHolder.clearContext();
        }
    }
}
~~~

Filter này minh họa một cơ chế stateless: client gửi API key trên từng request, filter không lưu `SecurityContext` vào HTTP session. Vì thế, test cần chứng minh context chỉ tồn tại khi chain đang xử lý. Trong ứng dụng session-based, cách lưu context phải tuân theo `SecurityContextRepository` và lifecycle của Spring Security; không sao chép nguyên mẫu stateless này sang ứng dụng cần duy trì session.

Trong cấu hình Servlet, filter có thể được đặt sau bước nạp context và trước anonymous authentication/authorization, ví dụ dùng `addFilterBefore(apiKeyFilter, AnonymousAuthenticationFilter.class)`. Unit test bên dưới không xác minh vị trí đăng ký; điều đó thuộc integration test.

## 4. Tạo request, response và FilterChain được kiểm soát

Các lớp mock của Spring Test giúp tạo đối tượng Servlet mà không cần container:

| Thành phần | Công dụng |
| --- | --- |
| `MockHttpServletRequest` | Tạo method, URI, header, parameter, session, servlet path và request attribute |
| `MockHttpServletResponse` | Quan sát status, header, redirect, content type và body |
| `MockHttpSession` | Kiểm tra session attribute và trạng thái invalidation |
| `FilterChain` giả | Quan sát filter có gọi tiếp hay không; kiểm tra context trong lúc chain chạy |
| `MockFilterChain` | Chạy một servlet mock ở cuối chuỗi và giữ request/response đã nhận |

Một `FilterChain` có thể được tạo bằng lambda vì nó chỉ có một phương thức:

~~~java
FilterChain chain = (request, response) -> {
    // Mã chạy sau filter.
};
~~~

Đây thường là lựa chọn đơn giản nhất khi cần quan sát điều gì xảy ra trong chain. Có thể dùng `AtomicBoolean`, `AtomicReference` hoặc assertion trực tiếp bên trong lambda.

Ví dụ tạo request:

~~~java
MockHttpServletRequest request =
        new MockHttpServletRequest("GET", "/api/reports");
request.setServletPath("/api/reports");
request.addHeader("X-API-Key", "test-key");

MockHttpServletResponse response = new MockHttpServletResponse();
~~~

Khi test `shouldNotFilter(...)`, đặt `servletPath` rõ ràng để nhánh matcher không phụ thuộc cách mock request suy ra path.

## 5. Unit test nhánh không có API key

Theo thiết kế của filter, request không có header `X-API-Key` sẽ đi tiếp. Filter không gọi manager vì có thể một filter xác thực khác xử lý request này.

~~~java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.AuthenticationEntryPoint;

import java.util.concurrent.atomic.AtomicBoolean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;

class ApiKeyAuthenticationFilterTest {

    private final AuthenticationManager manager =
            mock(AuthenticationManager.class);
    private final AuthenticationEntryPoint entryPoint =
            mock(AuthenticationEntryPoint.class);
    private final ApiKeyAuthenticationFilter filter =
            new ApiKeyAuthenticationFilter(manager, entryPoint);

    @AfterEach
    void clearSecurityContext() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void continuesChainWhenApiKeyHeaderIsMissing() throws Exception {
        var request = new MockHttpServletRequest("GET", "/api/reports");
        request.setServletPath("/api/reports");
        var response = new MockHttpServletResponse();
        AtomicBoolean chainCalled = new AtomicBoolean(false);

        filter.doFilter(request, response, (req, res) -> {
            chainCalled.set(true);
            ((MockHttpServletResponse) res).setStatus(202);
        });

        assertThat(chainCalled).isTrue();
        assertThat(response.getStatus()).isEqualTo(202);
        verifyNoInteractions(manager, entryPoint);
    }
}
~~~

Test này chứng minh filter không tự xác thực khi không có API key và request được chuyển tiếp. Nó không chứng minh request anonymous sẽ được phép truy cập endpoint; authorization filter phía sau vẫn phải quyết định điều đó.

## 6. Unit test nhánh xác thực thành công

Ở test này, manager giả lập kết quả xác thực đã được tin cậy. Chain kiểm tra `SecurityContext` trong lúc xử lý và ghi status để ta xác nhận request đi tiếp.

~~~java
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.AuthenticationEntryPoint;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class ApiKeyAuthenticationSuccessTest {

    @Test
    void authenticatesApiKeyAndExposesPrincipalToDownstreamChain()
            throws Exception {
        AuthenticationManager manager = mock(AuthenticationManager.class);
        AuthenticationEntryPoint entryPoint =
                mock(AuthenticationEntryPoint.class);
        Authentication authenticated =
                UsernamePasswordAuthenticationToken.authenticated(
                        "report-client",
                        null,
                        AuthorityUtils.createAuthorityList("REPORT_READ"));
        when(manager.authenticate(any(ApiKeyAuthenticationToken.class)))
                .thenReturn(authenticated);

        var filter = new ApiKeyAuthenticationFilter(manager, entryPoint);
        var request = new MockHttpServletRequest("GET", "/api/reports");
        request.setServletPath("/api/reports");
        request.addHeader("X-API-Key", "test-key");
        var response = new MockHttpServletResponse();
        AtomicReference<Authentication> observed =
                new AtomicReference<>();

        filter.doFilter(request, response, (req, res) -> {
            observed.set(
                    SecurityContextHolder.getContext().getAuthentication());
            ((MockHttpServletResponse) res).setStatus(204);
        });

        assertThat(observed.get()).isSameAs(authenticated);
        assertThat(observed.get().getName()).isEqualTo("report-client");
        assertThat(response.getStatus()).isEqualTo(204);
        assertThat(SecurityContextHolder.getContext().getAuthentication())
                .isNull();
        verify(manager).authenticate(any(ApiKeyAuthenticationToken.class));
    }
}
~~~

Test này có ba assertion quan trọng:

1. Manager nhận token API key và trả `Authentication` đã xác thực.
2. Downstream chain nhìn thấy principal cùng authorities trong `SecurityContext`.
3. Sau khi chain hoàn tất, context đã được dọn khỏi thread hiện tại.

Việc mock `AuthenticationManager` là có chủ đích: unit test filter không cần kiểm tra cách provider so sánh key. Hãy viết component test riêng cho provider và integration test để xác minh filter cùng provider thật được gắn vào security chain.

## 7. Unit test nhánh xác thực thất bại và short-circuit

Khi manager ném `AuthenticationException`, filter gọi entry point và không gọi chain. Điều này bảo đảm request có credentials sai không thể tiếp tục tới controller như request đã xác thực.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.http.HttpStatus;

import java.util.concurrent.atomic.AtomicBoolean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class ApiKeyAuthenticationFailureTest {

    @Test
    void rejectsInvalidKeyAndDoesNotInvokeDownstreamChain()
            throws Exception {
        AuthenticationManager manager = mock(AuthenticationManager.class);
        when(manager.authenticate(any(ApiKeyAuthenticationToken.class)))
                .thenThrow(new BadCredentialsException("Invalid API key"));
        AuthenticationEntryPoint entryPoint =
                new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED);
        var filter = new ApiKeyAuthenticationFilter(manager, entryPoint);

        var request = new MockHttpServletRequest("GET", "/api/reports");
        request.setServletPath("/api/reports");
        request.addHeader("X-API-Key", "wrong-key");
        var response = new MockHttpServletResponse();
        AtomicBoolean chainCalled = new AtomicBoolean(false);

        filter.doFilter(request, response, (req, res) ->
                chainCalled.set(true));

        assertThat(response.getStatus()).isEqualTo(401);
        assertThat(chainCalled).isFalse();
        assertThat(SecurityContextHolder.getContext().getAuthentication())
                .isNull();
    }
}
~~~

`HttpStatusEntryPoint` được dùng để làm response dễ quan sát trong unit test. Nếu ứng dụng cần `WWW-Authenticate`, JSON error body hoặc challenge OAuth2, hãy kiểm thử entry point cụ thể của ứng dụng. Unit test filter chỉ cần chứng minh nó chuyển ngoại lệ đến đúng entry point và kết thúc chain.

## 8. Kiểm thử filter bỏ qua URL công khai

`OncePerRequestFilter` cung cấp `shouldNotFilter(HttpServletRequest)` để bỏ qua những request không thuộc phạm vi filter. Trong ví dụ, URL bắt đầu bằng `/public/` không dùng API key filter.

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.web.AuthenticationEntryPoint;

import java.util.concurrent.atomic.AtomicBoolean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verifyNoInteractions;

class ApiKeyAuthenticationFilterMatcherTest {

    @Test
    void skipsPublicPathAndContinuesChain() throws Exception {
        AuthenticationManager manager = mock(AuthenticationManager.class);
        AuthenticationEntryPoint entryPoint =
                mock(AuthenticationEntryPoint.class);
        var filter = new ApiKeyAuthenticationFilter(manager, entryPoint);
        var request = new MockHttpServletRequest("GET", "/public/status");
        request.setServletPath("/public/status");
        request.addHeader("X-API-Key", "ignored-key");
        var response = new MockHttpServletResponse();
        AtomicBoolean chainCalled = new AtomicBoolean(false);

        filter.doFilter(request, response, (req, res) ->
                chainCalled.set(true));

        assertThat(chainCalled).isTrue();
        verifyNoInteractions(manager, entryPoint);
    }
}
~~~

Test này kiểm tra chính sách matcher của filter. Nếu ứng dụng dùng context path hoặc servlet mapping khác, cần tạo request với `contextPath` và `servletPath` tương ứng. Không nên kiểm tra path bằng chuỗi `requestURI` một cách tùy tiện nếu URL có context path.

## 9. Kiểm thử ngoại lệ từ filter chain

Filter chỉ nên bắt `AuthenticationException` phát sinh trong bước xác thực mà nó quản lý. Ngoại lệ từ controller hoặc filter phía sau phải tiếp tục truyền theo cơ chế Servlet/Spring Security, không bị biến thành lỗi API key.

~~~java
import jakarta.servlet.ServletException;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.web.authentication.HttpStatusEntryPoint;
import org.springframework.http.HttpStatus;

import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class ApiKeyAuthenticationChainExceptionTest {

    @Test
    void propagatesDownstreamServletException() {
        AuthenticationManager manager = mock(AuthenticationManager.class);
        when(manager.authenticate(any(ApiKeyAuthenticationToken.class)))
                .thenReturn(UsernamePasswordAuthenticationToken.authenticated(
                        "report-client", null,
                        AuthorityUtils.createAuthorityList("REPORT_READ")));
        AuthenticationEntryPoint entryPoint =
                new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED);
        var filter = new ApiKeyAuthenticationFilter(manager, entryPoint);
        var request = new MockHttpServletRequest("GET", "/api/reports");
        request.setServletPath("/api/reports");
        request.addHeader("X-API-Key", "valid-key");
        var response = new MockHttpServletResponse();

        assertThatThrownBy(() -> filter.doFilter(
                request,
                response,
                (req, res) -> {
                    throw new ServletException("downstream failed");
                }))
                .isInstanceOf(ServletException.class)
                .hasMessage("downstream failed");
    }
}
~~~

Filter trong ví dụ dùng `finally` để dọn `SecurityContext`, nên việc downstream ném ngoại lệ cũng không để context tồn tại trên thread. Có thể thêm assertion `SecurityContextHolder.getContext().getAuthentication()` là null sau `assertThatThrownBy(...)` nếu muốn kiểm tra cleanup trong cùng test.

## 10. MockFilterChain và khi nào dùng nó

`MockFilterChain` hữu ích khi muốn thực thi một servlet cuối chuỗi thay vì chỉ dùng lambda. Ví dụ:

~~~java
import java.io.IOException;
import jakarta.servlet.http.HttpServlet;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.mock.web.MockFilterChain;

var terminalServlet = new HttpServlet() {
    @Override
    protected void doGet(
            HttpServletRequest request,
            HttpServletResponse response) throws IOException {
        response.setStatus(202);
    }
};

MockFilterChain chain = new MockFilterChain(terminalServlet);
filter.doFilter(request, response, chain);

assertThat(response.getStatus()).isEqualTo(202);
assertThat(chain.getRequest()).isSameAs(request);
~~~

Đây là cách kiểm tra filter chuyển request đến servlet cuối chuỗi. `MockFilterChain` thường chỉ chạy một lần; tạo instance mới cho mỗi test/request. Khi cần quan sát `SecurityContext` trong thời gian chain đang chạy, `FilterChain` lambda thường dễ dùng hơn vì có thể đặt assertion ngay bên trong callback.

## 11. Các lưu ý riêng với OncePerRequestFilter

`OncePerRequestFilter` quản lý một request attribute để tránh thực thi lặp trong cùng một request dispatch theo chính sách mặc định. Khi viết test:

- Gọi `filter.doFilter(...)` để đi qua logic đánh dấu và dọn attribute; không gọi trực tiếp `doFilterInternal(...)`.
- Đặt method, URI và servlet path đúng với điều kiện filter dùng.
- Nếu override `shouldNotFilterAsyncDispatch()` hoặc `shouldNotFilterErrorDispatch()`, viết test riêng cho dispatch đó.
- Không giả định một lần gọi filter trên hai request khác nhau sẽ dùng chung marker; marker được quản lý theo lifecycle request.

Ví dụ filter mặc định không chạy lại ở async dispatch, trừ khi được override. Với filter ghi audit hoặc thiết lập context cần chạy ở async thread, phải quyết định rõ semantics và kiểm thử bằng request dispatch tương ứng. Unit test request thường không đủ để chứng minh toàn bộ async lifecycle của container.

## 12. Unit test filter và integration test qua MockMvc

Unit test trực tiếp không gọi `FilterChainProxy`. Nếu filter được đăng ký vào Spring Security, cần có integration test để xác minh filter thật nằm trong chain và chạy theo thứ tự đúng.

Ví dụ cấu hình:

~~~java
http.addFilterBefore(
        apiKeyAuthenticationFilter,
        AnonymousAuthenticationFilter.class);
~~~

Integration test có thể khởi động Spring context và gửi request bằng `MockMvc`:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ApiKeyFilterIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void validApiKeyCanReachProtectedEndpoint() throws Exception {
        mockMvc.perform(get("/api/reports")
                        .header("X-API-Key", "valid-test-key"))
                .andExpect(status().isOk());
    }

    @Test
    void invalidApiKeyIsRejectedByConfiguredEntryPoint()
            throws Exception {
        mockMvc.perform(get("/api/reports")
                        .header("X-API-Key", "invalid-test-key"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

Đây là khung test tích hợp; ứng dụng phải có provider/manager thật hoặc test fixture được cấu hình, endpoint thật và filter được đăng ký. Nếu `AuthenticationManager` mock trong context, test vẫn kiểm tra vị trí filter và đường đi HTTP nhưng không kiểm tra việc xác minh API key thật. Hãy mô tả chính xác phụ thuộc nào là thật và phụ thuộc nào được thay thế.

Integration test nên xác minh thêm:

- Filter có chạy trước authorization rule cần nó hay không.
- Request thiếu API key có được cơ chế khác xử lý hoặc bị từ chối theo đúng chính sách hay không.
- Request đến `/public/**` có thực sự bỏ qua filter.
- `SecurityContext` được lưu/dọn đúng với stateless hay session-based repository.
- CSRF/CORS/exception translation không làm thay đổi response ngoài dự kiến.

## 13. Những lỗi thường gặp

**Chỉ gọi doFilterInternal(...) trong test.** Cách đó bỏ qua lifecycle `OncePerRequestFilter`, gồm marker và nhánh skip. Gọi `doFilter(...)` công khai.

**Không kiểm tra chain có được gọi hay không.** Test chỉ kiểm tra response có thể bỏ sót việc request vẫn đi tới controller sau khi credentials sai. Dùng cờ hoặc fake chain để xác nhận short-circuit.

**Bắt quá rộng ngoại lệ của downstream.** Chỉ xử lý `AuthenticationException` từ bước authenticate; để ngoại lệ từ filter/controller phía sau truyền tiếp.

**Không dọn SecurityContext.** Thread-local có thể làm test khác nhận principal cũ. Dọn context trong `finally` và dùng `@AfterEach` để cô lập test.

**Đánh dấu token đầu vào là authenticated.** Dữ liệu từ header chưa được tin cậy. Provider phải xác minh credentials và trả kết quả authenticated.

**Xem sự hiện diện của API key là xác thực thành công.** Header có thể chứa key giả. Luôn đưa token đến manager/provider tin cậy.

**Nhầm unit test với test thứ tự filter.** Gọi filter trực tiếp không chứng minh vị trí đăng ký. Dùng `MockMvc` qua `FilterChainProxy` để kiểm tra wiring/order.

**Dùng MockFilterChain cho nhiều request liên tiếp.** Mock chain có trạng thái và thường chỉ thực thi một lần. Tạo chain mới cho mỗi lần gọi.

**Bỏ qua async/error dispatch.** `OncePerRequestFilter` có chính sách dispatch riêng. Nếu filter cần xử lý async/error, viết test tương ứng.

**Kiểm tra sai path trong shouldNotFilter.** `requestURI`, `contextPath` và `servletPath` khác nhau. Tạo request mock với mapping tương ứng và kiểm tra đúng thuộc tính mà filter sử dụng.

## 14. Bài thực hành

1. Viết một `OncePerRequestFilter` đọc header `X-Trace-Id`, lưu giá trị vào request attribute và gọi chain. Kiểm tra header có/không có và request path công khai được bỏ qua.
2. Viết filter API key theo mẫu. Dùng `AuthenticationManager` fake trả `Authentication` thành công; xác minh chain nhìn thấy principal và authority.
3. Làm manager ném `BadCredentialsException`. Xác minh entry point trả 401 và chain không được gọi.
4. Làm downstream chain ném `ServletException`. Xác minh ngoại lệ truyền ra ngoài và `SecurityContext` được dọn.
5. Dùng `MockFilterChain` với servlet cuối chuỗi để xác minh request thực sự được chuyển tiếp.
6. Đăng ký filter bằng `addFilterBefore(...)`. Viết integration test `MockMvc` để xác minh filter chạy đúng vị trí và authorization nhận được `Authentication` mong đợi.
7. Nếu filter override async/error dispatch, viết test riêng cho mỗi chính sách dispatch và giải thích vì sao unit test request đồng bộ không đủ.

Một unit test filter tốt kiểm tra **đầu vào, response, quyết định chuyển tiếp và trạng thái bảo mật trong suốt vòng đời request**. Kết hợp test trực tiếp với một số test `MockMvc` giúp phân biệt lỗi logic của filter với lỗi đăng ký hoặc thứ tự trong security filter chain.
