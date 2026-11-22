# Kiểm thử phản hồi từ filter thay vì chỉ kiểm thử ngoại lệ trong controller

Trong **Spring Security OAuth 2.0/OIDC Resource Server**, nhiều lỗi liên quan đến access token được phát hiện **trước khi request tới controller**. Một Bearer token hết hạn, sai chữ ký, không được Authorization Server công nhận, hoặc thiếu scope có thể khiến **Spring Security filter chain** tạo phản hồi HTTP với mã **401/403** và header **`WWW-Authenticate`**. Vì thế, chỉ kiểm thử ngoại lệ do controller ném ra hoặc `@RestControllerAdvice` xử lý **chưa chứng minh** API trả đúng phản hồi OAuth 2.0 Bearer.

Ví dụ, khi client gọi:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer invalid-access-token
~~~

Resource Server có thể từ chối token tại `BearerTokenAuthenticationFilter` mà **không hề gọi `OrdersController`**. Nếu unit test chỉ gọi `controller.getOrder(123L)`, nó sẽ không chạy filter, resolver, provider, decoder, entry point hoặc quy tắc HTTP authorization. Test ấy có thể pass trong khi request ngoài thực tế trả sai status hoặc thiếu Bearer challenge.

Bài này trình bày cách **kiểm tra phản hồi tại ranh giới HTTP** với Spring Security Servlet Resource Server: phân biệt authentication và authorization, các bộ xử lý lỗi `AuthenticationEntryPoint`/`AccessDeniedHandler`, header `WWW-Authenticate` theo RFC 6750, MockMvc với **SecurityFilterChain thực**, cách mock `JwtDecoder` hoặc `OpaqueTokenIntrospector`, và những bẫy khi dùng test helper tạo sẵn Authentication.

## 1. Vì sao lỗi Bearer không nhất thiết đi qua controller?

Với một cấu hình Resource Server điển hình, luồng xử lý có dạng:

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["FilterChainProxy chọn SecurityFilterChain"]
    B --> C["BearerTokenAuthenticationFilter"]
    C --> D{"Có Bearer token?"}
    D -- "Có" --> E["AuthenticationManager"]
    E --> F["JwtAuthenticationProvider hoặc OpaqueTokenAuthenticationProvider"]
    F --> G{"Token hợp lệ?"}
    G -- "Không" --> H["AuthenticationEntryPoint"]
    H --> I["HTTP 401/response lỗi"]
    G -- "Có" --> J["Authentication trong SecurityContext"]
    D -- "Không" --> K["Tiếp tục chuỗi filter"]
    J --> K
    K --> L["AuthorizationFilter"]
    L --> M{"Đủ quyền truy cập?"}
    M -- "Không" --> N["AccessDeniedHandler hoặc AuthenticationEntryPoint"]
    N --> O["HTTP 403 hoặc 401 theo trạng thái"]
    M -- "Có" --> P["DispatcherServlet -> Controller"]
    P --> Q["HTTP response nghiệp vụ"]
~~~

Đây là **sơ đồ các trách nhiệm logic**, không phải cam kết vị trí của mọi filter ở mọi phiên bản. `ExceptionTranslationFilter` thường nằm trước `AuthorizationFilter` và xử lý `AuthenticationException`/`AccessDeniedException` phát sinh ở các thành phần phía sau nó. Riêng `BearerTokenAuthenticationFilter` có thể **tự xử lý lỗi authentication thông qua `AuthenticationEntryPoint`**. Không nên khẳng định mọi exception bảo mật đều đi qua `ExceptionTranslationFilter`.

| Thành phần | Trách nhiệm |
| --- | --- |
| `FilterChainProxy` | Chọn `SecurityFilterChain` đầu tiên phù hợp request |
| `BearerTokenResolver` | Phân tích vị trí/cú pháp Bearer token |
| `BearerTokenAuthenticationFilter` | Khởi tạo xác thực Bearer nếu nhận diện token |
| `JwtAuthenticationProvider` | Gọi `JwtDecoder` xác minh chữ ký, claims và token profile |
| `OpaqueTokenAuthenticationProvider` | Gọi `OpaqueTokenIntrospector` xác minh trạng thái token |
| `AuthenticationEntryPoint` | Bắt đầu phản hồi khi request cần authentication hoặc authentication thất bại |
| `AuthorizationFilter` | Áp dụng `permitAll`, `authenticated`, scope/authority rules... |
| `AccessDeniedHandler` | Xử lý request không đủ quyền sau authentication theo chính sách |
| `DispatcherServlet` | Chỉ nhận request khi các filter cho đi tiếp; ở đây MVC controller/advice hoạt động |

**Hệ quả khi viết test:** muốn khẳng định một request Bearer token sai trả 401 và không chạy controller, test phải bắt đầu từ **HTTP request đi qua filter**, không bắt đầu bằng cách gọi thẳng controller method.

## 2. Authentication khác Authorization và khác lỗi nghiệp vụ

Một API Orders yêu cầu `SCOPE_orders.read` có thể gặp các trường hợp:

| Request | Giai đoạn quyết định | Response thường gặp |
| --- | --- | --- |
| Không gửi Bearer token đến endpoint bảo vệ | Authorization không có Authentication phù hợp, entry point được kích hoạt | **401 Unauthorized**, Bearer challenge |
| Gửi JWT hết hạn, sai chữ ký, sai issuer hoặc audience | `JwtDecoder`/provider từ chối | **401 Unauthorized**, thường `invalid_token` |
| Gửi opaque token nhưng introspection trả `active: false` | Introspector/provider từ chối | **401 Unauthorized**, thường `invalid_token` |
| Gửi Bearer theo cú pháp/phương thức không hợp lệ | Resolver/filter phát hiện `invalid_request` | Có thể **400 Bad Request**, tùy cấu hình và dạng lỗi |
| Gửi token hợp lệ, thiếu `SCOPE_orders.read` | HTTP authorization hoặc method security | **403 Forbidden**, có thể `insufficient_scope` |
| Token hợp lệ, đủ scope nhưng không sở hữu order | Business object authorization | **403 hoặc 404** theo chính sách |
| Token hợp lệ, controller không tìm thấy order | MVC/controller/business exception handling | **404** hoặc response nghiệp vụ được thiết kế |

Một lỗi **401** có nghĩa request chưa có authentication đạt yêu cầu. Một lỗi **403** thường có nghĩa đã xác định được chủ thể hoặc bối cảnh nhưng quyền không đủ. Trong ứng dụng thực tế, các handler tùy chỉnh và lỗi filter khác có thể tạo response khác, vì vậy test cần khẳng định **hợp đồng cụ thể** của API.

Không nên sửa lỗi 403 do thiếu scope bằng cách tắt JwtDecoder hoặc bỏ kiểm tra audience. Cũng không nên chuyển mọi lỗi thành 200 chỉ để controller có thể trả JSON thống nhất.

## 3. Header WWW-Authenticate theo RFC 6750

**RFC 6750** định nghĩa cơ chế Bearer authentication và phản hồi lỗi để OAuth 2.0 Client hiểu vấn đề.

Một request hoàn toàn không có token đến endpoint bắt buộc xác thực có thể nhận:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

Token được gửi nhưng không hợp lệ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Token đã được xác thực nhưng thiếu scope:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Bearer challenge có thể có thêm `realm`, `error_description`, `error_uri` hoặc `scope`:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api", error="insufficient_scope"
~~~

| Bearer error code | Tình huống | Status gắn với RFC 6750 |
| --- | --- | --- |
| `invalid_request` | Request bị coi là malformed theo cơ chế Bearer, ví dụ dùng nhiều cách truyền token không hợp lệ | Thường **400** |
| `invalid_token` | Token hết hạn, bị thu hồi hoặc không vượt qua kiểm tra | Thường **401** |
| `insufficient_scope` | Access token hợp lệ nhưng không đủ scope | Thường **403** |

**Không phải mọi 401 đều phải có `error="invalid_token"`.** Khi client không cung cấp credentials, Bearer challenge thông thường có thể **không mang error code**. Một test thiếu token nên kiểm tra status 401 và scheme Bearer; chỉ test token đã gửi nhưng bị từ chối mới cần `invalid_token` nếu contract yêu cầu.

Các ví dụ trên là hình thức hợp lệ, **không phải chuỗi header bất biến** cho mọi bản Spring Security. Thứ tự tham số, realm, error description và body phụ thuộc entry point/denied handler đã cấu hình. Đừng assert nguyên chuỗi header nếu hợp đồng chỉ yêu cầu scheme và error code.

### Kiểm tra status và Bearer challenge bằng MockMvc

~~~java
import static org.hamcrest.Matchers.startsWith;
import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import org.springframework.http.HttpHeaders;

// Không có token: thường chỉ cần Bearer challenge.
mockMvc.perform(get("/api/orders/123"))
    .andExpect(status().isUnauthorized())
    .andExpect(header().string(
        HttpHeaders.WWW_AUTHENTICATE, startsWith("Bearer")));

// Decoder từ chối Bearer token: có invalid_token khi dùng handler chuẩn.
mockMvc.perform(get("/api/orders/123")
        .header(HttpHeaders.AUTHORIZATION, "Bearer invalid-token"))
    .andExpect(status().isUnauthorized())
    .andExpect(header().string(
        HttpHeaders.WWW_AUTHENTICATE,
        containsString("error=\"invalid_token\"")));
~~~

Đoạn minh họa giả định một MockMvc đã được cấu hình **chạy filter chain**, và decoder mock/real sẽ từ chối `invalid-token`. Không thể tự kết luận từ việc chỉ gửi một chuỗi bất kỳ rằng code test đã được cấu hình đúng.

**Không đưa access token, secret, stack trace hoặc lỗi nội bộ nhạy cảm vào `error_description`.** Một error description thân thiện phải được lựa chọn có chủ đích, không in toàn bộ exception do thư viện trả về.

## 4. AuthenticationEntryPoint và AccessDeniedHandler thuộc tầng filter

Đối với Servlet Resource Server, hai thành phần quan trọng là:

- **`BearerTokenAuthenticationEntryPoint`** xử lý lúc cần bắt đầu/challenge Bearer authentication; thường trả 401 và `WWW-Authenticate` thích hợp.
- **`BearerTokenAccessDeniedHandler`** xử lý access denied trong nhánh OAuth2 Bearer authentication; thường trả 403 và có thể thêm `insufficient_scope`.

`ExceptionTranslationFilter` có thể phân biệt một `AccessDeniedException` của người chưa xác thực với lỗi của người đã có Authentication. Trong trường hợp người chưa xác thực, entry point có thể được gọi, tạo 401. Với người đã được xác thực nhưng thiếu quyền, access-denied handler thường trả 403.

Ví dụ SecurityFilterChain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/info").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationEntryPoint(
                    new BearerTokenAuthenticationEntryPoint())
                .accessDeniedHandler(
                    new BearerTokenAccessDeniedHandler())
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Với Resource Server, các handler Bearer phù hợp thường đã có sẵn trong cấu hình mặc định; khai báo tường minh ở đây nhằm **minh họa thành phần tạo response**.

**Giả định của ví dụ:** đây là API stateless xác thực bằng Bearer token, không sử dụng cookie phiên được browser tự động gửi. Khi dùng cookie/session, việc tắt CSRF cần xem lại. Đặc biệt, POST bị `CsrfFilter` từ chối 403 **không chứng minh** thiếu `SCOPE_orders.write`.

## 5. @RestControllerAdvice không tự bắt lỗi phát sinh trước DispatcherServlet

Giả sử API dùng:

~~~java
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiErrorAdvice {

    @ExceptionHandler(OrderNotFoundException.class)
    ResponseEntity<Map<String, String>> notFound(OrderNotFoundException ex) {
        return ResponseEntity
            .status(HttpStatus.NOT_FOUND)
            .body(Map.of("error", "order_not_found"));
    }
}
~~~

Một test controller ném `OrderNotFoundException` và assert 404 chỉ chứng minh **MVC exception handling**. Nó không chứng minh:

1. Token hết hạn hoặc chữ ký sai bị chặn.
2. `WWW-Authenticate` được sinh đúng.
3. Scope thiếu bị `AuthorizationFilter` chặn.
4. Request không token được chuyển tới authentication entry point.
5. Controller không bị gọi khi authentication thất bại.

`@ControllerAdvice` được Spring MVC dùng trong ngữ cảnh `DispatcherServlet`. Filter chạy **bên ngoài, trước lớp MVC**, nên exception do filter xử lý không tự được chuyển đến `@ControllerAdvice`. Ứng dụng có thể tự gắn `HandlerExceptionResolver` từ filter, nhưng đó là tùy chỉnh, không phải luồng mặc định của Spring Security OAuth2 Resource Server.

### Hai bài test bổ sung cho nhau

~~~text
Controller/unit test:
  controller/service throws OrderNotFoundException
  -> @RestControllerAdvice
  -> 404 nghiệp vụ

Filter integration test:
  GET + Authorization: Bearer invalid-token
  -> BearerTokenAuthenticationFilter
  -> JwtDecoder từ chối
  -> AuthenticationEntryPoint
  -> 401 + WWW-Authenticate
  -> Controller KHÔNG được gọi
~~~

Hãy giữ cả hai nhóm test, không dùng nhóm thứ nhất thay cho nhóm thứ hai.

## 6. Dựng controller nhỏ để quan sát filter

Ví dụ controller phục vụ test:

~~~java
import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
class OrdersController {

    @GetMapping("/{id}")
    Map<String, String> read(@PathVariable String id) {
        return Map.of("orderId", id);
    }
}
~~~

Một public controller riêng:

~~~java
@RestController
class PublicController {

    @GetMapping("/public/info")
    Map<String, String> info() {
        return Map.of("service", "orders-api");
    }
}
~~~

Với `OrdersSecurity` ở mục 4:

~~~text
GET /public/info           -> permitAll()
GET /api/orders/{id}      -> SCOPE_orders.read
POST /api/orders/...      -> SCOPE_orders.write
Các route còn lại         -> authenticated()
~~~

Những request test phải đi qua **SecurityFilterChain chứa các matcher này**. Nếu MockMvc chỉ dựng controller trực tiếp mà không có filter, cả request không token lẫn token hỏng đều có thể vào controller và trả 200.

## 7. MockMvc với security chain thật và mocked JwtDecoder

Đối với mục tiêu **kiểm tra response của filter**, có thể giữ nguyên Spring Security filter/provider/entry point/authorization và chỉ mock **`JwtDecoder`**. Điều này giúp chọn được nhánh lỗi và nhánh thành công mà không phải dựng Authorization Server/JWKS ở mỗi test.

Cấu hình test thường dùng:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class BearerResponseTest {
    @Autowired MockMvc mvc;
    @MockitoBean JwtDecoder jwtDecoder;
}
~~~

`@SpringBootTest` nạp context ứng dụng, `@AutoConfigureMockMvc` thiết lập MockMvc với các filter phù hợp. `@MockitoBean` thay decoder bean bằng Mockito mock trong các dòng Spring Test mới (ví dụ Spring Framework 6.2+). Với Spring Boot cũ hơn có thể dùng `@MockBean` tương thích. **Không sao chép một annotation không có trong dependency hiện tại.**

### Bộ test HTTP minh họa

~~~java
import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.startsWith;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidationException;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class BearerResponseTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    JwtDecoder jwtDecoder;

    @Test
    void missingBearerOnProtectedEndpointReturns401() throws Exception {
        mvc.perform(get("/api/orders/123"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                startsWith("Bearer")));

        verifyNoInteractions(jwtDecoder);
    }

    @Test
    void invalidJwtReturns401FromSecurityFilter() throws Exception {
        when(jwtDecoder.decode("invalid-token"))
            .thenThrow(new BadJwtException("Invalid JWT"));

        mvc.perform(get("/api/orders/123")
                .header(HttpHeaders.AUTHORIZATION, "Bearer invalid-token"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                containsString("error=\"invalid_token\"")));
    }

    @Test
    void expiredJwtReportedByDecoderReturns401() throws Exception {
        when(jwtDecoder.decode("expired-token"))
            .thenThrow(new JwtValidationException(
                "JWT expired",
                List.of(new OAuth2Error(
                    "invalid_token", "expired", null))
            ));

        mvc.perform(get("/api/orders/123")
                .header(HttpHeaders.AUTHORIZATION, "Bearer expired-token"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                containsString("error=\"invalid_token\"")));
    }

    @Test
    void validJwtButMissingReadScopeReturns403() throws Exception {
        when(jwtDecoder.decode("token-without-scope"))
            .thenReturn(fakeJwt("token-without-scope", "profile.read"));

        mvc.perform(get("/api/orders/123")
                .header(HttpHeaders.AUTHORIZATION,
                    "Bearer token-without-scope"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validJwtWithReadScopeCanReachController() throws Exception {
        when(jwtDecoder.decode("token-with-read-scope"))
            .thenReturn(fakeJwt("token-with-read-scope", "orders.read"));

        mvc.perform(get("/api/orders/123")
                .header(HttpHeaders.AUTHORIZATION,
                    "Bearer token-with-read-scope"))
            .andExpect(status().isOk());
    }

    private static Jwt fakeJwt(String token, String scope) {
        Instant issued = Instant.parse("2026-01-01T00:00:00Z");
        return Jwt.withTokenValue(token)
            .header("alg", "RS256")
            .issuer("https://auth.example.com/realms/shop")
            .subject("user-42")
            .issuedAt(issued)
            .expiresAt(issued.plusSeconds(31_536_000L * 5))
            .claim("aud", List.of("orders-api"))
            .claim("scope", scope)
            .build();
    }
}
~~~

**Giới hạn của test:** helper `fakeJwt(...)` tạo đối tượng `Jwt` được **mock decoder trả về**, không phải JWT ký hợp lệ. Test nhánh expired cũng **giả lập ngoại lệ từ decoder**, không thực sự chạy `JwtTimestampValidator`. Bộ test này xác minh **Bearer filter/provider, response 401/403, Bearer challenge và scope authorization**, chứ không chứng minh chữ ký, issuer, audience hay thời hạn đã được decoder production xác minh đúng.

Để kiểm tra thực sự chính sách chữ ký/claims, cần thêm test với **`NimbusJwtDecoder` thật**, khóa ký/JWKS thử nghiệm và validator đầy đủ. Hai lớp kiểm thử có mục tiêu khác nhau.

### Test thêm WWW-Authenticate với insufficient_scope

Nếu Resource Server dùng `BearerTokenAccessDeniedHandler` theo RFC 6750:

~~~java
when(jwtDecoder.decode("token-without-scope"))
    .thenReturn(fakeJwt("token-without-scope", "profile.read"));

mvc.perform(get("/api/orders/123")
        .header(HttpHeaders.AUTHORIZATION, "Bearer token-without-scope"))
    .andExpect(status().isForbidden())
    .andExpect(header().string(
        HttpHeaders.WWW_AUTHENTICATE,
        containsString("error=\"insufficient_scope\"")));
~~~

Đoạn này áp dụng khi handler được cấu hình để phát Bearer challenge tương ứng. Một custom `AccessDeniedHandler` có thể trả body/header khác; lúc đó test cần theo **contract thực tế của API**.

### Chứng minh controller không chạy

Một test 401 chỉ khẳng định status. Để chứng minh filter chặn request **trước controller**, hãy spy/mock một service được controller gọi và xác minh số lần gọi:

~~~java
// Minh họa khi fixture có bean orderApplicationService phù hợp.
// @MockitoSpyBean OrderApplicationService orderApplicationService;
//
// mvc.perform(get("/api/orders/123")
//         .header(HttpHeaders.AUTHORIZATION, "Bearer invalid-token"))
//     .andExpect(status().isUnauthorized());
//
// verifyNoInteractions(orderApplicationService);
~~~

Chỉ kiểm tra tương tác khi fixture bảo đảm service không bị gọi bởi quá trình khởi động context hoặc test khác. Cách khác là dùng test-only controller với counter, hoặc test có một side effect quan sát được. **Điểm phải chứng minh** là controller không thực hiện logic nghiệp vụ sau lỗi authentication.

## 8. Với opaque token: mock OpaqueTokenIntrospector

Nhánh opaque token có luồng:

~~~text
BearerTokenAuthenticationFilter
    -> OpaqueTokenAuthenticationProvider
    -> OpaqueTokenIntrospector
    -> OAuth2AuthenticatedPrincipal
    -> BearerTokenAuthentication
    -> AuthorizationFilter
~~~

Khi introspector từ chối access token, filter/provider tạo lỗi authentication; khi token được chấp nhận nhưng thiếu scope, request có thể bị authorization từ chối.

Với ứng dụng dùng:

~~~java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
~~~

có thể kiểm thử:

~~~java
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OpaqueBearerResponseTest {

    @Autowired MockMvc mvc;
    @MockitoBean OpaqueTokenIntrospector introspector;

    @Test
    void inactiveTokenReturns401() throws Exception {
        when(introspector.introspect("inactive-token"))
            .thenThrow(new BadOpaqueTokenException("Token inactive"));

        mvc.perform(get("/api/orders/123")
                .header(HttpHeaders.AUTHORIZATION,
                    "Bearer inactive-token"))
            .andExpect(status().isUnauthorized());
    }
}
~~~

Đây là test cho **ứng dụng có cấu hình opaque-token Resource Server**, không phải thêm cùng lúc vào test app chỉ bật JWT rồi kỳ vọng provider tự chuyển mode. Mock introspector giúp kiểm tra filter response nhưng **không gọi endpoint introspection HTTP thật**. Muốn kiểm tra RFC 7662 response `active: false`, TLS, client authentication, timeout và mapping attributes/authorities, cần mock HTTP introspection server hoặc test issuer phù hợp.

## 9. Vì sao MockMvc jwt() hoặc opaqueToken() chưa đủ?

Spring Security Test có các request post-processors tạo Authentication thử nghiệm:

~~~java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;

mockMvc.perform(get("/api/orders/123")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

Test này hữu ích để xác nhận **authorization rules** khi request đã có `JwtAuthenticationToken`. Nhưng nó thường **bỏ qua việc trích Bearer header và gọi JwtDecoder thật**. Tương tự, `opaqueToken()` tạo opaque principal giả lập mà không nhất thiết gọi introspection.

| Cách kiểm thử | Có kiểm tra Bearer parsing/filter và decoder thật không? | Giá trị chính |
| --- | --- | --- |
| Gọi trực tiếp controller | Không | Logic đơn vị của controller |
| MockMvc với `jwt()` | Không theo nhánh Bearer decoding thông thường | Scope và method/URL authorization |
| MockMvc với `opaqueToken()` | Không theo nhánh introspection thông thường | Authorization với opaque principal |
| MockMvc gửi `Authorization: Bearer X` và mock decoder | Có filter/provider thật, decoder giả lập | HTTP error/challenge + filter orchestration |
| MockMvc gửi JWT ký thật và decoder/JWKS thật | Có khi fixture được cấu hình đúng | Signature/claims validation và HTTP response |
| HTTP test opaque token với introspection test server | Có khi client/endpoint thật được cấu hình | Introspection protocol + filter response |

Nếu test “không token” mà bạn lại đặt `@WithMockUser` hoặc gọi `.with(jwt())`, request đã có Authentication giả. Test không còn đại diện cho HTTP request của khách ẩn danh.

## 10. Bẫy: MockMvc không chạy SecurityFilterChain

Một test có thể dựng MockMvc theo cách:

~~~java
MockMvc mvc = MockMvcBuilders
    .standaloneSetup(new OrdersController())
    .build();
~~~

Đây là lựa chọn hợp lý để test MVC/controller nhưng **không tự mang theo Spring Security filters** của ứng dụng. Không nên dùng kết quả từ `standaloneSetup` mặc định để kết luận Bearer authentication trả 401/403 đúng.

Khi cần test cả ứng dụng web và filter chain, có thể:

~~~java
import static org.springframework.security.test.web.servlet.setup.SecurityMockMvcConfigurers.springSecurity;
import static org.springframework.test.web.servlet.setup.MockMvcBuilders.webAppContextSetup;

@Autowired
WebApplicationContext context;

MockMvc mvc = webAppContextSetup(context)
    .apply(springSecurity())
    .build();
~~~

Hoặc dùng `@SpringBootTest @AutoConfigureMockMvc` với Spring Security đã được tích hợp. Test phải bảo đảm filter chain trong context khớp với route được kiểm tra.

### WebMvcTest và các slice test

`@WebMvcTest` có thể đưa một phần Spring Security vào MVC slice, nhưng không bảo đảm tự động nạp mọi `SecurityFilterChain`, decoder, custom filter, exception handler như production. Nếu dùng slice test, cần import cấu hình thích hợp và cung cấp mock beans thiếu; nếu muốn kiểm tra luồng lỗi gần với runtime thật, `@SpringBootTest @AutoConfigureMockMvc` thường là điểm khởi đầu rõ ràng hơn.

Một sanity test nên là:

~~~text
GET /api/orders/123 (không token)
   -> 401 Unauthorized, Bearer challenge

GET /public/info (không token)
   -> được phép nếu controller trả thành công
~~~

Nếu protected endpoint không token trả 200, hãy kiểm tra filter chain có được nạp, matcher có khớp, hoặc test helper đã vô tình gắn Authentication.

## 11. Nhiều SecurityFilterChain và permitAll

Một ứng dụng có thể phân chia:

~~~text
@Order(1) publicChain
  securityMatcher("/public/**")
  permitAll(), không bật OAuth2 Resource Server

@Order(2) apiChain
  securityMatcher("/api/**")
  oauth2ResourceServer().jwt()
  scope rules

@Order(3) fallbackChain
  denyAll()
~~~

Spring Security chọn **chain đầu tiên khớp request**, không cộng gộp filter từ tất cả chain. Vì vậy test phải kiểm tra các route đại diện của từng chain.

**`permitAll()` không tự bỏ qua BearerTokenAuthenticationFilter.** Khi endpoint public nằm **trong cùng chain đã bật Resource Server**, request có token sai vẫn có thể trả 401 trước bước authorization:

~~~text
Public trong cùng JWT chain:
  Không token      -> có thể 200
  Bearer hợp lệ    -> có thể 200
  Bearer sai/hết hạn -> thường 401

Public trong chain riêng không bật Bearer Resource Server:
  Không token      -> có thể 200
  Bearer sai       -> không bị Bearer filter của chain ấy xử lý
~~~

Nếu sản phẩm yêu cầu route public **bỏ qua mọi Bearer token được gửi đến**, phải thiết kế chain riêng hoặc một `BearerTokenResolver` theo matcher có chủ đích. Chỉ khai báo `.requestMatchers("/public/**").permitAll()` là chưa đủ để đạt yêu cầu này.

Đừng quên **fallback chain** cho các route không khớp; nếu không có chain nào bảo vệ, endpoint có thể vô tình nằm ngoài Spring Security.

## 12. Filter khác có thể tạo 401/403: CORS, CSRF và custom filters

Khi test 403 hoặc request không vào controller, đừng mặc định nguyên nhân luôn là thiếu scope.

### CORS preflight

Browser có thể gửi:

~~~http
OPTIONS /api/orders/123 HTTP/1.1
Origin: https://frontend.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

Preflight thường **không chứa Bearer token**, dù GET tiếp theo có. Nếu CORS xử lý sai, browser có thể không gửi request thật.

Test ví dụ khi app **đã cho phép** origin/method/header tương ứng:

~~~java
mockMvc.perform(options("/api/orders/123")
        .header(HttpHeaders.ORIGIN,
            "https://frontend.example.com")
        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_METHOD, "GET")
        .header(HttpHeaders.ACCESS_CONTROL_REQUEST_HEADERS,
            "authorization"))
    .andExpect(status().isOk());
~~~

Nếu chưa cấu hình CORS đúng, test này có thể fail và **đó không nhất thiết là lỗi Bearer authentication**. Resource Server cần cấu hình CORS cho origin, method, header hợp lệ, ví dụ thông qua `.cors(Customizer.withDefaults())` cùng nguồn cấu hình CORS.

### CSRF

Một POST có thể bị `CsrfFilter` chặn với 403 **trước khi** quy tắc scope là yếu tố quyết định. Với API Bearer-only stateless, có thể cấu hình CSRF phù hợp kiểu ứng dụng; với cookie/session, không vô hiệu hóa CSRF tùy tiện.

Để test thiếu scope một cách rõ ràng, nên dùng GET có scope rule phù hợp hoặc đảm bảo test đã xử lý CSRF đúng theo cấu hình.

### Custom filters và gateway

Rate limiting, tenant filter, security header filter hoặc gateway có thể tạo response trước controller. Khi debug hãy xác định **filter nào thực sự tạo lỗi**, security chain nào được chọn và có custom entry point hay access-denied handler không.

## 13. Kiểm tra JSON error body ở đúng tầng

Giả sử API muốn mọi lỗi 401 dùng Problem Details:

~~~json
{
  "type": "https://api.example.com/problems/invalid-token",
  "title": "Unauthorized",
  "status": 401,
  "detail": "A valid access token is required"
}
~~~

Nếu lỗi phát sinh từ Bearer filter, một `@RestControllerAdvice` thông thường **không đủ** để bảo đảm body này. Cần viết hoặc cấu hình **`AuthenticationEntryPoint`** cho lỗi xác thực và **`AccessDeniedHandler`** cho lỗi quyền; MVC advice vẫn xử lý lỗi nghiệp vụ.

~~~text
Bearer token sai
    -> AuthenticationEntryPoint
    -> 401 + WWW-Authenticate + JSON body (nếu cấu hình)

Access token hợp lệ, thiếu scope
    -> AccessDeniedHandler
    -> 403 + Bearer challenge phù hợp + JSON body (nếu cấu hình)

Order không tồn tại trong controller
    -> @RestControllerAdvice
    -> 404 + JSON body nghiệp vụ
~~~

Nếu app đã có custom entry point trả `application/problem+json`, test có thể:

~~~java
mockMvc.perform(get("/api/orders/123")
        .header(HttpHeaders.AUTHORIZATION, "Bearer invalid-token"))
    .andExpect(status().isUnauthorized())
    .andExpect(header().string(
        HttpHeaders.WWW_AUTHENTICATE,
        containsString("invalid_token")))
    .andExpect(content().contentTypeCompatibleWith(
        "application/problem+json"))
    .andExpect(jsonPath("$.status").value(401));
~~~

Đây là kỳ vọng **chỉ áp dụng khi app thực sự có handler trả JSON**. Spring Security mặc định có thể để body rỗng. Nếu tự xây handler, không được quên Bearer challenge theo RFC 6750 hoặc ghi response hai lần sau khi nó đã committed.

## 14. Chọn boundary cần mock

Một nguyên tắc thực hành: **giữ thật thành phần bạn muốn kiểm tra, mock ở ranh giới nằm bên ngoài trách nhiệm của test**.

| Mục tiêu | Giữ thành phần thật | Có thể mock |
| --- | --- | --- |
| 401 + WWW-Authenticate khi JWT hỏng | Bearer filter, provider, entry point | `JwtDecoder` ném exception |
| 403 khi JWT thiếu scope | Bearer filter, authority converter, authorization rules, denied handler | `JwtDecoder` trả Jwt hợp lệ nhưng ít scope |
| Missing token | Filter chain, authorization, entry point | Decoder không nên được gọi |
| Xác minh exp/iss/aud/signature | `NimbusJwtDecoder` và validators | JWKS/issuer test server |
| Opaque token inactive | Filter/provider và (nếu cần protocol) introspector thật | HTTP introspection test server hoặc mock introspector |
| Quyền trên order/tenant | Business policy, repository, method security | Identity fixture hoặc token test phù hợp |
| @ControllerAdvice nghiệp vụ | MVC advice, handler mapping | Service ném exception nghiệp vụ |

Không mock chính `AuthenticationEntryPoint` khi mục tiêu là kiểm tra HTTP response do entry point tạo. Không mock toàn bộ filter chain rồi coi response là bằng chứng cấu hình bảo mật đúng.

## 15. Ma trận kiểm thử phản hồi Bearer

Với endpoint GET `/api/orders/123` yêu cầu `SCOPE_orders.read`:

| Kịch bản | Kết quả mong đợi |
| --- | --- |
| Không có Authorization header | Thường **401**, Bearer challenge |
| Authorization: Basic ... trong ứng dụng chỉ bật Bearer | Thường bị coi là không có Bearer authentication |
| Bearer token sai chữ ký | Thường **401**, `invalid_token` |
| JWT hết hạn hoặc chưa có hiệu lực | Thường **401**, `invalid_token` |
| JWT sai issuer hoặc audience | Từ chối xác thực theo token validators |
| Opaque token active=false | Thường **401**, `invalid_token` |
| Request Bearer malformed | Có thể **400** + `invalid_request` theo resolver và tình huống |
| Token hợp lệ, thiếu scope | Thường **403**, có thể `insufficient_scope` |
| Token hợp lệ, có scope | Vào controller; response nghiệp vụ |
| Token hợp lệ, đủ scope nhưng thiếu quyền trên order | Thường **403/404** theo business policy |
| Public route, không token | Có thể **200** |
| Public route, token hỏng, cùng resource-server chain | Có thể **401** trước `permitAll` |
| Public route có chain riêng không bật Bearer filter | Token hỏng không bị Resource Server filter ở chain đó xử lý |
| Preflight CORS được cho phép | Phản hồi theo CORS policy, không nhất thiết dùng Bearer token |
| POST bị CSRF từ chối | Có thể 403 do CSRF, không phải do thiếu scope |
| JWKS/introspection không truy cập được | Không được cấp quyền nếu không xác thực token; status cụ thể tùy handler |

Test nên assert **status, WWW-Authenticate, body và việc controller không chạy** khi những yếu tố đó thuộc hợp đồng. Tránh dùng một kỳ vọng status cứng cho các lỗi hạ tầng không được tiêu chuẩn hóa bởi chính ứng dụng.

## 16. Những lỗi thường gặp khi thiết kế test

**“Test @RestControllerAdvice ra 401 thì Bearer filter cũng trả 401.”** Không. MVC advice không tự nhận exception xảy ra trước DispatcherServlet.

**“MockMvc standaloneSetup(controller) là đủ để test security.”** Không. Cách dựng này không tự đăng ký Spring Security filter chain.

**“Dùng jwt() với token hết hạn mà được 200 chứng tỏ decoder lỗi.”** Không chắc. Test helper tạo Authentication giả, không bắt buộc chạy decoder/timestamp validators.

**“401 và 403 chỉ khác response body.”** Không. Hai mã phản ánh authentication so với authorization, có thể khác Bearer error code.

**“Không gửi token mà không thấy invalid_token trong WWW-Authenticate là sai.”** Không. Một Bearer challenge do thiếu credentials có thể không mang error code.

**“403 trên POST chứng minh token thiếu scope.”** Chưa chắc: cần loại trừ CSRF, method security và business policy.

**“Mock JwtDecoder đủ chứng minh xác minh chữ ký.”** Không. Nó chỉ điều khiển outcome trong test.

**“Chỉ test status là đủ.”** Nếu API theo RFC 6750, header `WWW-Authenticate` và các tham số quan trọng cũng cần được kiểm tra.

**“Được phép trả raw access token trong JSON error để debug.”** Không. Bearer token là credential; tránh đưa vào response, exception description, log hoặc metrics.

**“permitAll có nghĩa filter không kiểm tra token được gửi.”** Không. `permitAll` là authorization rule, không tự loại `BearerTokenAuthenticationFilter`.

## 17. Quy trình thực hành khi kiểm thử lỗi filter

1. **Xác định chain thực tế** cho route: Bearer JWT, opaque token, public hay fallback; chú ý `securityMatcher` và `@Order` nếu có nhiều chain.
2. **Viết rõ contract phản hồi** cho missing token, invalid token, thiếu scope, lỗi quyền đối tượng và lỗi nghiệp vụ.
3. **Bật filter chain trong test** bằng `@SpringBootTest @AutoConfigureMockMvc` hoặc `webAppContextSetup(...).apply(springSecurity())` phù hợp.
4. **Mock đúng ranh giới**: `JwtDecoder`/`OpaqueTokenIntrospector` khi kiểm tra filter response, không mock entry point cần kiểm thử.
5. **Gửi HTTP Authorization header thật** bằng `.header(HttpHeaders.AUTHORIZATION, "Bearer ...")`; không thay bằng helper `jwt()` cho tình huống token malformed/expired.
6. **Assert status và Bearer challenge**; kiểm tra body/content type khi API có handler tùy chỉnh.
7. **Kiểm tra controller không chạy** khi lỗi phải dừng tại filter, dùng spy/service fixture khi cần.
8. **Tách test authentication và authorization**: invalid token → 401, authenticated thiếu scope → 403, đủ scope nhưng sai owner/tenant → policy 403/404.
9. **Bổ sung decoder/integration test thật** để kiểm tra JWS signature, issuer/audience/time hoặc introspection response/TLS/client authentication.
10. **Giữ regression suite cho public/CORS/CSRF/multiple chains**, vì các filter khác cũng có thể quyết định response trước controller.

**Điểm cần nhớ:** lỗi Bearer trong Spring Security Resource Server rất thường được phát hiện và trả về **trước controller**. Muốn chắc chắn client thực sự nhận đúng phản hồi, hãy kiểm thử **HTTP request đi qua SecurityFilterChain** và quan sát **status, `WWW-Authenticate`, body và việc request bị dừng đúng tầng**. Controller unit test và `@RestControllerAdvice` vẫn cần cho lỗi nghiệp vụ, nhưng **không thay thế kiểm thử `BearerTokenAuthenticationFilter`, `AuthenticationEntryPoint` và `AccessDeniedHandler`**.
