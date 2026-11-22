# opaqueToken() và mô phỏng principal của token được introspect

Khi kiểm thử một **Spring Security OAuth 2.0 Resource Server dùng opaque access token**, ta thường muốn xác minh controller, HTTP authorization và cách ứng dụng sử dụng principal do quá trình introspection trả về. Không phải test nào cũng cần gọi Authorization Server (AS) thật hoặc gửi một access token thật qua mạng. Spring Security Test cung cấp request post-processor **opaqueToken()** để dựng một authentication có hình dạng tương ứng với kết quả xác thực opaque token.

Điểm quan trọng là hiểu đúng phạm vi của công cụ:

- **opaqueToken()** giúp test nhanh phần xử lý **sau khi authentication đã thành công**: authorities, principal attributes, controller arguments, method security và HTTP authorization.
- Nó tạo authentication giả lập trong request test; **không gọi OpaqueTokenIntrospector**, không gửi Bearer token tới AS, không xác minh token có active hay không và không kiểm tra client credentials/introspection endpoint.
- Muốn kiểm tra toàn bộ Bearer filter và introspection integration, hãy gửi header **Authorization: Bearer ...** qua MockMvc và dùng một OpaqueTokenIntrospector test/stub hoặc AS test thật.

Hai loại test này bổ sung cho nhau. Một test dùng opaqueToken() không chứng minh introspection hoạt động; một integration test introspection không nhất thiết phải lặp lại mọi test controller/authorization. Chọn đúng công cụ cho câu hỏi cần trả lời.

## 1. Opaque token authentication hoạt động như thế nào?

Opaque access token thường là chuỗi không mang claims có thể đọc hoặc kiểm chữ ký tại Resource Server. Khi client gọi API:

~~~mermaid
sequenceDiagram
    participant C as OAuth Client
    participant API as Spring Resource Server
    participant AS as Authorization Server
    C->>API: Authorization: Bearer opaque-token
    API->>API: BearerTokenAuthenticationFilter
    API->>AS: Token introspection (RFC 7662)
    AS-->>API: active + claims + scope
    API->>API: OpaqueTokenAuthenticationProvider
    API->>API: Build BearerTokenAuthentication
    API->>API: Authorization rules
    API-->>C: Response
~~~

Trong Servlet stack, các thành phần chính:

| Thành phần | Trách nhiệm |
|---|---|
| **BearerTokenAuthenticationFilter** | Đọc Bearer credential từ HTTP request và khởi tạo authentication request |
| **AuthenticationManager / OpaqueTokenAuthenticationProvider** | Điều phối xác thực opaque token |
| **OpaqueTokenIntrospector** | Gửi token tới AS introspection endpoint và trả principal đã xác thực |
| **OAuth2AuthenticatedPrincipal** | Biểu diễn subject, attributes và authorities mà introspector trả về |
| **BearerTokenAuthentication** | Authentication thành công cho opaque bearer token |
| **HTTP/method authorization** | Kiểm tra authorities sau authentication |

AS thường trả metadata theo RFC 7662, ví dụ:

~~~json
{
  "active": true,
  "sub": "alice",
  "scope": "orders.read orders.write",
  "client_id": "orders-web",
  "aud": ["orders-api"],
  "tenant_id": "tenant-a"
}
~~~

Khi introspection thành công, Spring Security tạo principal từ attributes và ánh xạ scope thành authorities. Theo cấu hình mặc định phổ biến, scope **orders.read** được chuyển thành authority **SCOPE_orders.read**. Nếu token inactive, introspector không tạo principal authenticated thành công.

## 2. opaqueToken() là gì?

**opaqueToken()** là một **MockMvc request post-processor** trong module **spring-security-test**. Nó cho phép một test gắn một authentication dạng opaque-token đã được xác thực vào request để Security filter chain xử lý phần authorization và controller như thể principal đã được introspection xác minh.

Static import thường dùng:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.opaqueToken;
~~~

Dependency cần có cùng dòng version với Spring Security trong ứng dụng:

~~~groovy
dependencies {
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Với Maven:

~~~xml
<dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Nếu dự án dùng Spring Boot dependency management, để BOM quản lý version phù hợp; tránh tự ghim một version spring-security-test khác version runtime.

### 2.1. Test đơn giản

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.opaqueToken;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@Test
void requestWithMockOpaqueTokenIsAuthenticated() throws Exception {
    mockMvc.perform(get("/api/orders").with(opaqueToken()))
        .andExpect(status().isOk());
}
~~~

Ví dụ giả định endpoint chấp nhận authority mặc định của post-processor hoặc có rule chỉ yêu cầu authenticated. Trong test thực tế, nên cấu hình **authority cụ thể mà endpoint cần** để test phản ánh đúng policy, không dựa vào default authorities của helper.

### 2.2. Authentication được dựng sẵn

Khi dùng opaqueToken(), test không phải cung cấp một chuỗi token có định dạng opaque thật. Post-processor chuẩn bị security context cho request với một principal/Authentication mô phỏng opaque token. Điều đó giúp test không phụ thuộc AS và không cần lưu token thật trong fixture.

Thông tin mặc định của helper được thiết kế để có một principal cơ bản và authority đọc mẫu. Chi tiết default có thể thay đổi theo phiên bản Spring Security; **đừng dựa vào default trong test nghiệp vụ**. Hãy đặt attributes và authorities tường minh để test tự mô tả điều kiện nó cần.

### 2.3. Nó không chạy introspection

Đây là ranh giới cần nhớ:

~~~text
mockMvc.perform(get(...).with(opaqueToken()))
    |
    +-- Tạo Authentication mock
    +-- SecurityContext có Authentication
    +-- Authorization rules
    +-- Controller / method security
    |
    X Không gọi OpaqueTokenIntrospector
    X Không gọi token introspection endpoint
    X Không kiểm active=true
    X Không kiểm client_id/secret của Resource Server
~~~

Vì vậy, test này không thể phát hiện lỗi URL introspection, lỗi Basic authentication tới AS, timeout, JSON mapping hoặc cache introspection. Những phần đó cần test khác.

## 3. Mô phỏng principal attributes và authorities

Một principal opaque thường là **OAuth2AuthenticatedPrincipal**. Nó chứa:

- Tên principal, thường dựa trên claim **sub** theo introspector.
- Attributes được AS trả về, ví dụ **sub**, **client_id**, **aud**, **tenant_id**.
- Authorities, thường được ánh xạ từ **scope** hoặc cấu hình custom.

### 3.1. Tùy chỉnh attributes

opaqueToken() cho phép đặt attributes của principal:

~~~java
mockMvc.perform(get("/api/orders")
        .with(opaqueToken().attributes(attributes -> {
            attributes.put("sub", "alice");
            attributes.put("tenant_id", "tenant-a");
            attributes.put("client_id", "orders-web");
        })))
    .andExpect(status().isOk());
~~~

Ở đây sub là subject và tenant_id là custom claim theo contract của hệ thống. Các giá trị này chỉ là **test fixture**. Việc đưa tenant_id=tenant-a vào map không chứng minh AS thật sự phát claim đó hoặc token thật có quyền tenant A.

### 3.2. Tùy chỉnh authorities

Để test scope-based authorization, đặt authority mà ứng dụng thực sự kiểm:

~~~java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

mockMvc.perform(get("/api/orders")
        .with(opaqueToken()
            .authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

Nếu endpoint yêu cầu **hasAuthority("SCOPE_orders.read")**, test cần authority chính xác này. Các chuỗi sau không tương đương:

| Authority | Có thỏa hasAuthority("SCOPE_orders.read")? |
|---|---|
| **SCOPE_orders.read** | Có |
| **orders.read** | Không |
| **ROLE_orders.read** | Không |
| **SCOPE_orders.write** | Không |
| **ROLE_ADMIN** | Không, trừ khi rule khác cho phép |

**hasRole("ADMIN")** mặc định tìm **ROLE_ADMIN**; scope và role có prefix khác nhau. Đừng đổi production authorization rule chỉ để một test dùng authority không đúng.

### 3.3. Đặt attributes và authorities cùng lúc

Một test thường cần principal đúng tenant và scope:

~~~java
mockMvc.perform(get("/api/orders")
        .with(opaqueToken()
            .attributes(attributes -> {
                attributes.put("sub", "alice");
                attributes.put("tenant_id", "tenant-a");
                attributes.put("client_id", "orders-web");
            })
            .authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

Tách hai khái niệm:

- **Attributes** mô tả principal/token metadata.
- **Authorities** là quyền mà Security authorization engine kiểm.

Đặt claim scope trong attributes không nhất thiết tự làm test helper ánh xạ authority từ claim ấy. Khi dùng opaqueToken(), hãy đặt authorities rõ ràng. Nếu muốn test scope-to-authority mapping của production introspector/provider, dùng integration test qua Bearer filter với introspector thật hoặc stub.

### 3.4. Test principal name

Controller có thể lấy principal:

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CurrentPrincipalController {

    @GetMapping("/api/me")
    String me(@AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        return principal.getAttribute("sub");
    }
}
~~~

Test:

~~~java
mockMvc.perform(get("/api/me")
        .with(opaqueToken().attributes(attributes ->
            attributes.put("sub", "alice"))))
    .andExpect(status().isOk())
    .andExpect(content().string("alice"));
~~~

Đối với opaque token, principal có kiểu tổng quát **OAuth2AuthenticatedPrincipal**; không ép nó thành **Jwt**. Một controller nhận **@AuthenticationPrincipal Jwt** phù hợp JWT Resource Server, không phù hợp opaque principal.

### 3.5. Đọc BearerTokenAuthentication

Nếu controller/service cần xem metadata của authentication:

~~~java
import org.springframework.security.oauth2.server.resource.authentication
    .BearerTokenAuthentication;

@GetMapping("/api/token-info")
Map<String, Object> tokenInfo(BearerTokenAuthentication authentication) {
    return authentication.getTokenAttributes();
}
~~~

Trong production, tránh trả toàn bộ token attributes cho client nếu có claim nội bộ/PII. Test có thể xác minh một field cần thiết:

~~~java
mockMvc.perform(get("/api/token-info")
        .with(opaqueToken().attributes(attributes -> {
            attributes.put("sub", "alice");
            attributes.put("tenant_id", "tenant-a");
        })))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.tenant_id").value("tenant-a"));
~~~

BearerTokenAuthentication chứa token attributes và principal đã được dựng; helper không chứng minh các attributes đó đến từ AS thật.

## 4. Cấu hình Resource Server trong ứng dụng được kiểm thử

Một security chain Servlet dùng opaque token có thể cấu hình:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
~~~

Với Spring Boot, introspection URI và client credentials có thể được cung cấp qua:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://identity.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: INTROSPECTION_CLIENT_SECRET_FROM_SECRET_STORE
~~~

Đây là cấu hình production-style để Spring tạo introspector. Test dùng opaqueToken() không cần endpoint thật vì authentication được dựng sẵn. Nếu test cần đi qua introspector, phải cung cấp một introspector test riêng hoặc AS test.

### 4.1. CSRF trong test

Ví dụ trên là API stateless dùng Bearer header, giả định credential không tự động được browser gửi như cookie. Nếu ứng dụng dùng session cookie hoặc có browser authentication trong cùng chain, không sao chép việc disable CSRF một cách máy móc. Khi test POST/PUT/DELETE với session-based security, dùng CSRF test post-processor phù hợp và giữ policy production.

### 4.2. Đảm bảo test thực sự nạp SecurityFilterChain

MockMvc cần chạy với Spring Security filter chain để kiểm tra authorization. Trong Spring Boot, **@AutoConfigureMockMvc** cùng application context thường tự cấu hình filter. Nếu tự dựng MockMvc, cần tích hợp Spring Security bằng cấu hình tương ứng (ví dụ **springSecurity()** khi dùng webAppContextSetup).

Nếu test chỉ gọi controller trực tiếp hoặc dựng MockMvc không có security filters, kết quả 200 không chứng minh opaqueToken()/authorization rules đang hoạt động.

## 5. Ví dụ đầy đủ: controller, authority và principal

Giả sử API có endpoint trả danh sách đơn hàng của tenant trong principal:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrdersController {

    @GetMapping("/api/orders")
    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    String list(@AuthenticationPrincipal
                OAuth2AuthenticatedPrincipal principal) {
        String subject = principal.getAttribute("sub");
        String tenant = principal.getAttribute("tenant_id");
        return subject + ":" + tenant;
    }
}
~~~

Nếu dùng method security, bật:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfiguration {
}
~~~

Test:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.opaqueToken;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class OrdersControllerTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void returnsPrincipalAttributesForAuthorizedOpaquePrincipal()
            throws Exception {

        mockMvc.perform(get("/api/orders")
                .with(opaqueToken()
                    .attributes(attributes -> {
                        attributes.put("sub", "alice");
                        attributes.put("tenant_id", "tenant-a");
                    })
                    .authorities(
                        new SimpleGrantedAuthority("SCOPE_orders.read"))))
            .andExpect(status().isOk())
            .andExpect(content().string("alice:tenant-a"));
    }
}
~~~

Ví dụ minh họa tập trung vào contract controller/security. Dự án thực tế cần cấu hình MockMvc, component scanning, method security và dependencies theo ứng dụng. Nếu Spring context khởi tạo production introspector cần property, hãy cung cấp test property hoặc thay introspector trong test context; request post-processor sẽ không gọi nó.

## 6. Kiểm thử 401, 403 và quyền tối thiểu

Ba trạng thái nên được tách:

- **401 Unauthorized:** request không có Authentication hợp lệ (ví dụ không có Bearer token hoặc token không được xác thực).
- **403 Forbidden:** Authentication đã tồn tại nhưng không có authority cần thiết hoặc bị policy từ chối.
- **2xx:** Authentication và authorization đủ cho request (còn có thể bị business logic từ chối).

### 6.1. Thiếu token: 401

~~~java
@Test
void missingBearerTokenIsUnauthorized() throws Exception {
    mockMvc.perform(get("/api/orders"))
        .andExpect(status().isUnauthorized());
}
~~~

Test này yêu cầu security chain bảo vệ endpoint và Resource Server entry point được cấu hình. Nó không dùng opaqueToken() vì đang kiểm trường hợp **không có Authentication**.

### 6.2. Có principal nhưng thiếu scope: 403

~~~java
@Test
void authenticatedPrincipalWithoutReadScopeIsForbidden()
        throws Exception {
    mockMvc.perform(get("/api/orders")
            .with(opaqueToken()
                .attributes(attributes ->
                    attributes.put("sub", "alice"))
                .authorities(
                    new SimpleGrantedAuthority("SCOPE_profile.read"))))
        .andExpect(status().isForbidden());
}
~~~

Đây là trường hợp điển hình cho opaqueToken(): principal được xem là đã authenticated, nhưng thiếu SCOPE_orders.read.

### 6.3. Đúng scope không đồng nghĩa quyền trên mọi object

Nếu user có SCOPE_orders.read nhưng truy cập order của tenant khác, service/domain policy vẫn phải từ chối. Có thể test với principal tenant:

~~~java
mockMvc.perform(get("/api/tenants/tenant-b/orders")
        .with(opaqueToken()
            .attributes(attributes -> {
                attributes.put("sub", "alice");
                attributes.put("tenant_id", "tenant-a");
            })
            .authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isForbidden());
~~~

Kết quả phụ thuộc implementation tenant authorization thực tế. Mục tiêu test là đảm bảo claim tenant được dùng theo policy, không chỉ vì test helper đã thêm attribute. Nếu logic tenant nằm trong service, mock repository/service để xác minh service nhận đúng verified principal và tenant; thêm integration test với database khi cần chứng minh query giới hạn tenant.

### 6.4. Đừng dùng authenticated() thay scope

Một test có thể pass vì rule chỉ yêu cầu:

~~~java
.anyRequest().authenticated()
~~~

nhưng production endpoint cần:

~~~java
.requestMatchers(GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

Hãy test đúng rule mà endpoint sử dụng. Nếu test chỉ dùng principal mặc định và status 200, có thể bạn chưa chứng minh scope mapping hay least privilege.

## 7. So sánh opaqueToken() với @WithMockUser

**@WithMockUser** tạo một user authentication tổng quát (thường là UsernamePasswordAuthenticationToken) cho test. **opaqueToken()** mô phỏng authentication dạng OAuth2 opaque Resource Server.

| Khía cạnh | @WithMockUser | opaqueToken() |
|---|---|---|
| Kiểu Authentication | Username/password-style mock user | Bearer/opaque-token authentication |
| Principal | UserDetails-like principal | OAuth2AuthenticatedPrincipal |
| Attributes sub, tenant_id, client_id | Không có sẵn theo opaque-token contract | Có thể tùy chỉnh |
| Authorities | Có thể khai báo roles/authorities | Có thể khai báo scope authorities |
| Phù hợp kiểm tra | Controller/security chỉ cần user/role tổng quát | Resource Server opaque-token authorization và principal |
| Gọi introspector | Không | Không |
| Kiểm token active | Không | Không |

Nếu code có:

~~~java
@AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal
~~~

thì opaqueToken() phản ánh kiểu principal phù hợp hơn @WithMockUser. Nếu endpoint chỉ dùng hasRole("ADMIN") và không quan tâm Authentication type, cả hai có thể dùng được, nhưng test opaque token vẫn mô tả đúng loại credential của API hơn.

Không nên thay toàn bộ test bằng @WithMockUser chỉ vì tiện khi production là OAuth2 Resource Server. Điều đó có thể bỏ sót lỗi khi controller/service kỳ vọng OAuth2AuthenticatedPrincipal hoặc BearerTokenAuthentication.

## 8. Phân biệt mock principal với test introspection thật

Đây là ranh giới quan trọng nhất khi chọn công cụ.

### 8.1. Test A: dùng opaqueToken() để kiểm tra phần sau authentication

~~~text
MockMvc request
  .with(opaqueToken().attributes(...).authorities(...))
          |
          v
Mock Authentication / SecurityContext
          |
          v
Authorization + Controller + Method Security
~~~

Phù hợp để kiểm tra:

- URL yêu cầu scope nào.
- Principal attributes được controller đọc ra sao.
- Method security có chặn đúng không.
- Tenant/owner policy có dùng principal đúng không.
- HTTP 401/403/2xx theo Authentication fixture.

Không phù hợp để kiểm tra:

- Header Bearer được parse ra sao.
- OpaqueTokenIntrospector có nhận đúng token không.
- AS có trả active=true không.
- Scope trong introspection response được map ra authority ra sao.
- Client authentication, TLS, timeout, error mapping hoặc cache.

### 8.2. Test B: gửi Bearer header và stub introspector

Để kiểm tra filter/provider/introspector wiring, gửi token qua HTTP header:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer test-opaque-token
~~~

Trong test context, cung cấp một OpaqueTokenIntrospector stub trả principal:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection
    .BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection
    .OpaqueTokenIntrospector;

final class StubOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        if (!"test-opaque-token".equals(token)) {
            throw new BadOpaqueTokenException("Unknown test token");
        }

        return new DefaultOAuth2AuthenticatedPrincipal(
            "alice",
            Map.of(
                "sub", "alice",
                "tenant_id", "tenant-a",
                "scope", "orders.read"
            ),
            List.of(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )
        );
    }
}
~~~

Stub chỉ chấp nhận một token test cụ thể và trả principal do test định nghĩa; nó không liên lạc AS. Có thể inject stub bằng @TestConfiguration/test bean hoặc cơ chế bean override phù hợp với version Spring Boot.

Test:

~~~java
mockMvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION,
            "Bearer test-opaque-token"))
    .andExpect(status().isOk());
~~~

Request đi qua Bearer authentication filter và gọi stub introspector. Cách này kiểm tra **wiring và mapping qua provider**, nhưng vẫn chưa kiểm HTTP request tới AS thật.

### 8.3. Test C: introspection endpoint giả lập qua HTTP

Một test integration có thể chạy mock HTTP server (ví dụ MockWebServer/WireMock) làm introspection endpoint:

1. Cấu hình introspection-uri tới mock server.
2. Gửi Authorization: Bearer opaque-test-token tới API bằng MockMvc.
3. Mock server nhận POST /introspect.
4. Mock server trả JSON active=true, sub, scope, aud.
5. Xác minh API tạo Authentication và trả response theo policy.
6. Trả active=false hoặc lỗi server ở test khác và xác minh request bị từ chối.

Đây là test tốt để kiểm tra HTTP introspection client, request form, client authentication, response parsing và error mapping. Nó vẫn không phải kiểm thử với nhà phát hành production thật; nhưng cho phép kiểm soát response deterministic.

### 8.4. Test D: AS thật trong môi trường integration

Một số dự án cần test contract với AS thật ở môi trường staging/identity sandbox:

- Lấy token từ flow test được quản lý.
- Gửi Bearer token qua API.
- Kiểm audience/scope/active.
- Revoke token và thử lại.
- Đo cache/propagation.

Không đưa access token/refresh token production vào test source, CI logs hoặc fixture repository. Ưu tiên credentials/tenant test, cleanup sau test và secret injection từ CI.

## 9. Test scope-to-authority mapping của introspection

Với opaque token, provider thường dùng OpaqueTokenIntrospector trả principal và authorities. Nếu AS trả:

~~~json
{
  "active": true,
  "sub": "alice",
  "scope": "orders.read orders.write"
}
~~~

thì ứng dụng thường mong đợi:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Nếu custom introspector hoặc authority converter thay đổi mapping, hãy test đúng mapping thực tế.

### 9.1. Kiểm tra authority converter qua introspector

Test post-processor:

~~~java
.with(opaqueToken().authorities(
    new SimpleGrantedAuthority("SCOPE_orders.read")))
~~~

chỉ gắn authority được chỉ định. Nó **không chạy converter production**. Để test converter, gọi converter trực tiếp bằng principal fixture hoặc gửi Bearer header qua OpaqueTokenAuthenticationProvider được cấu hình với introspector test.

### 9.2. Không cấp quyền từ claim không tin cậy

Nếu introspection response chứa:

~~~json
{
  "active": true,
  "sub": "alice",
  "scope": "orders.read",
  "admin": true
}
~~~

thì admin=true không tự động thành ROLE_ADMIN. Chỉ map claim đó nếu issuer contract quy định ý nghĩa, audience/resource đúng và ứng dụng có policy rõ. Trong opaqueToken() test, việc thêm ROLE_ADMIN trực tiếp vào authorities có thể kiểm nhánh admin, nhưng không chứng minh production converter chỉ cấp quyền khi AS đã xác minh claim tương ứng.

### 9.3. Phân biệt scope thiếu và introspection inactive

| Introspection result | Authentication | Authorization |
|---|---|---|
active=false | Thất bại | Không chạy tới rule quyền |
active=true, không có scope read | Thành công | GET read bị 403 |
active=true, có scope read | Thành công | Có thể qua scope check |
active=true, audience sai | Phải bị policy từ chối | Không được cho qua chỉ vì scope đúng |
AS timeout/5xx | Không xác minh được | Không tạo principal authenticated |

opaqueToken() chủ yếu giúp test hai hàng giữa (principal authenticated có/không có authority). Các trường hợp inactive/audience/timeout cần introspector test/integration.

## 10. Test controller dùng principal attributes

### 10.1. Subject và tenant

Một endpoint có thể lấy subject và tenant từ principal:

~~~java
@GetMapping("/api/tenant/orders")
String tenantOrders(
        @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
    String subject = principal.getAttribute("sub");
    String tenant = principal.getAttribute("tenant_id");
    return subject + ":" + tenant;
}
~~~

Test hai tenant:

~~~java
@Test
void principalAttributesAreAvailableToController() throws Exception {
    mockMvc.perform(get("/api/tenant/orders")
            .with(opaqueToken()
                .attributes(attributes -> {
                    attributes.put("sub", "alice");
                    attributes.put("tenant_id", "tenant-a");
                })
                .authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read"))))
        .andExpect(status().isOk())
        .andExpect(content().string("alice:tenant-a"));
}
~~~

### 10.2. Principal name và attribute sub

Đừng mặc định principal name luôn là email hoặc username. Opaque introspector có thể đặt tên dựa trên sub hoặc custom principal name attribute. Khi code cần identity ổn định, hãy dựa trên issuer + subject theo contract, không dùng email display name làm primary key.

Trong test, nếu controller dùng principal.getName() thay vì getAttribute("sub"), hãy kiểm tra behavior của principal test fixture ở version Spring Security đang dùng. Có thể cần tạo custom principal/introspector fixture để đặt principal name rõ ràng thay vì giả định mọi helper default giống production.

### 10.3. Không lấy tenant từ request làm danh tính

Nếu endpoint là /api/tenants/{tenantId}/orders, path variable là dữ liệu caller yêu cầu truy cập, không phải claim đã xác minh. Test cần chứng minh:

- Principal tenant claim đến từ Authentication.
- Requested tenant được so với principal/membership.
- Service query giới hạn tenant.
- Không thể đổi path variable để truy cập dữ liệu tenant khác.

opaqueToken().attributes(...) giúp dựng principal tenant trong test; domain service vẫn cần test riêng cho allow/deny. Nếu logic tenant nằm trong service, mock repository/service để xác minh service nhận đúng verified principal và tenant; thêm integration test với database khi cần chứng minh query giới hạn tenant.

## 11. @WebMvcTest và @SpringBootTest

Hai kiểu test có phạm vi khác nhau.

### 11.1. @WebMvcTest

Phù hợp khi muốn test controller và MVC/security slice:

~~~java
@WebMvcTest(OrdersController.class)
class OrdersControllerWebTest {
    @Autowired
    MockMvc mockMvc;
}
~~~

@WebMvcTest không nhất thiết tự nạp mọi security configuration hoặc custom bean của ứng dụng. Nếu cần security chain, import cấu hình tương ứng:

~~~java
@Import(ApiSecurityConfiguration.class)
~~~

Nếu cấu hình Resource Server cần OpaqueTokenIntrospector, cung cấp test bean hoặc dùng opaqueToken() để kiểm phần sau authentication. Khi chỉ dùng request post-processor, introspector bean có thể không cần cho request đó, nhưng application context vẫn có thể yêu cầu bean tùy cấu hình auto-configuration.

### 11.2. @SpringBootTest + @AutoConfigureMockMvc

Phù hợp khi muốn nạp gần như toàn bộ application context:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OrdersSecurityIntegrationTest {
    @Autowired
    MockMvc mockMvc;
}
~~~

Có thể kiểm tra nhiều filter chains, method security, service wiring và exception handlers. Đổi lại, test khởi tạo nhiều thành phần hơn và có thể cần cấu hình test cho datasource, introspector hoặc external dependencies.

### 11.3. Không để test gọi AS ngoài ý muốn

Nếu test dùng:

~~~java
mockMvc.perform(get("/api/orders").with(opaqueToken()))
~~~

thì request post-processor đã cung cấp Authentication; không cần gọi AS. Nhưng một test khác gửi:

~~~java
mockMvc.perform(get("/api/orders")
    .header(HttpHeaders.AUTHORIZATION, "Bearer some-token"))
~~~

sẽ đi qua Resource Server authentication và có thể gọi introspector thật nếu không override. Để CI ổn định, cung cấp test introspector hoặc mock HTTP endpoint tường minh; không để test vô tình gọi IdP development/production.

## 12. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
opaqueToken() test trả 403 | Helper không có authority endpoint yêu cầu | Set SCOPE_... đúng bằng authorities(...) |
Controller nhận principal null | Security filters không chạy hoặc request chưa authenticated | Kiểm tra MockMvc security integration và request post-processor |
@AuthenticationPrincipal Jwt không bind | Opaque principal không phải Jwt | Dùng OAuth2AuthenticatedPrincipal hoặc BearerTokenAuthentication |
Test pass nhưng AS không nhận request | Dùng mock post-processor nên không introspect | Viết integration test với Bearer header và introspector |
Test active=false không hoạt động | opaqueToken() dựng principal authenticated sẵn | Test qua stub/HTTP introspector trả inactive |
Scope trong attributes không tạo authority | Post-processor đặt attributes và authorities riêng | Set authority rõ; test converter ở integration layer |
@WithMockUser pass nhưng production lỗi | Mock user khác principal/Authentication type | Dùng opaqueToken() cho Resource Server tests |
Tenant test luôn 200 | Test chỉ kiểm scope, chưa có domain rule | Test owner/tenant authorization |
Test gọi IdP thật trong CI | Bearer header đi qua introspector production | Inject stub/mock server test |
MockMvc không trả 401 khi thiếu token | Security chain không được load hoặc rule permitAll | Kiểm tra filter chain và matcher |
POST trả 403 trong test | CSRF bật và request thiếu token, hoặc thiếu scope | Phân biệt CSRF với authorization; thêm csrf() khi đúng ngữ cảnh |
Test dựa vào default scope helper | Default có thể thay đổi hoặc không đúng endpoint | Đặt authorities tường minh |
Introspection converter lỗi nhưng test vẫn pass | opaqueToken() bỏ qua converter | Gửi Bearer token qua provider/introspector test |
Custom attributes không khớp production | Test map claim tùy ý, không theo issuer contract | Dùng fixture phản ánh response schema của AS |

## 13. Ma trận chọn cách kiểm thử

| Câu hỏi cần trả lời | Công cụ phù hợp |
|---|---|
GET /api/orders có yêu cầu SCOPE_orders.read không? | opaqueToken().authorities(...) |
Controller đọc sub và tenant_id đúng không? | opaqueToken().attributes(...) |
@PreAuthorize có chặn principal thiếu scope không? | opaqueToken() với authorities đủ/thiếu |
Controller có nhận đúng OAuth2AuthenticatedPrincipal không? | opaqueToken() |
Không có Bearer token có trả 401 không? | MockMvc request không có authentication |
Bearer header có được parse không? | MockMvc với Authorization: Bearer ... |
OpaqueTokenIntrospector nhận đúng token không? | Bearer header + stub/mock introspector |
scope từ response được map thành SCOPE_... không? | Test provider/introspector pipeline |
active=false có bị từ chối không? | Stub/HTTP introspection test |
Audience/issuer contract có được kiểm không? | Introspector policy integration test |
AS timeout/5xx được xử lý thế nào? | Mock HTTP server + Bearer integration test |
Introspection cache có hoạt động không? | Test cache-aware introspector và clock/TTL |
Token bị revoke có bị từ chối không? | Test introspection/denylist sau revocation |
Production AS có tương thích không? | Staging contract test có kiểm soát |

## 14. Quy trình viết test Servlet với opaqueToken()

Một trình tự ngắn gọn:

1. **Nạp Spring Security:** xác nhận MockMvc chạy đúng SecurityFilterChain.
2. **Chọn endpoint:** xác định HTTP matcher và authority cần có.
3. **Dựng principal:** dùng opaqueToken().attributes(...) cho sub, tenant và metadata controller cần.
4. **Dựng authorities:** dùng authorities(new SimpleGrantedAuthority("SCOPE_...")) khớp production rule.
5. **Kiểm response:** status/body/controller argument/method security.
6. **Test negative:** thiếu authentication, thiếu scope, sai tenant.
7. **Test introspection riêng:** gửi Bearer header và inject stub introspector.
8. **Test provider/AS contract:** mock HTTP introspection response cho active, inactive, malformed và error.
9. **Test cache/revocation riêng:** chứng minh TTL/invalidation theo policy nếu ứng dụng có cache.

Không gom tất cả vào một test duy nhất. Test càng tập trung, lỗi càng dễ định vị: authorization sai, principal mapping sai hay introspection integration sai.

## 15. Kết luận

~~~text
opaqueToken()
  = mock an already-authenticated opaque-token principal
  = set principal attributes + authorities
  = test MockMvc authorization/controller/method security

opaqueToken()
  != call OpaqueTokenIntrospector
  != send Bearer token to Authorization Server
  != test active/inactive response
  != test introspection credentials, HTTP mapping or cache

REAL INTROSPECTION TEST
  Authorization: Bearer test-token
       |
       v
  BearerTokenAuthenticationFilter
       |
       v
  OpaqueTokenAuthenticationProvider
       |
       v
  OpaqueTokenIntrospector (stub / mock HTTP / test AS)
       |
       v
  Authentication + authorities
       |
       v
  Authorization + Controller
~~~

**opaqueToken()** là công cụ tiện lợi để mô phỏng một principal opaque token đã authenticated trong **Servlet MockMvc tests**. Hãy dùng attributes để dựng sub, tenant_id và metadata mà controller cần; dùng authorities để kiểm tra chính xác scope/role mà HTTP rules yêu cầu. Nó đặc biệt hữu ích cho test 403, method security, principal injection và domain authorization.

Nhưng helper này không chạy OpaqueTokenIntrospector. Khi cần kiểm tra token thực được gửi qua Bearer filter, scope mapping, active=false, audience policy, timeout hoặc cache, hãy gửi Authorization: Bearer ... và inject một introspector test hoặc mock introspection endpoint. Giữ hai lớp test riêng sẽ giúp chứng minh đúng cả **ứng dụng xử lý principal ra sao** lẫn **nhà phát hành đã xác minh token thế nào**.

## Tài liệu tham khảo

- [Spring Security Reference — Testing OAuth 2.0](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): MockMvc post-processors cho OAuth2 Resource Server, opaqueToken() và principal customization.
- [Spring Security API — SecurityMockMvcRequestPostProcessors](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.html): opaqueToken() request post-processor.
- [Spring Security Reference — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): OpaqueTokenIntrospector, provider và principal.
- [Spring Security API — OpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html): contract introspection.
- [Spring Security API — OAuth2AuthenticatedPrincipal](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/OAuth2AuthenticatedPrincipal.html): principal attributes và authorities.
- [Spring Security API — BearerTokenAuthentication](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/BearerTokenAuthentication.html): authentication được tạo từ opaque bearer token.
- [Spring Security Reference — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): @PreAuthorize và method authorization.
- [Spring Security Reference — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html): kiểm thử method security.
- [Spring Security Reference — MockMvc Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html): tích hợp Spring Security filters vào MockMvc.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): introspection request/response, active và token metadata.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer authentication scheme và error semantics.
