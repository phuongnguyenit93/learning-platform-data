# `opaqueToken()` tạo `BearerTokenAuthentication` cho `MockMvc`

## 1. Khi endpoint nhận opaque bearer token

Ứng dụng Spring Security Resource Server có thể nhận access token ở dạng JWT hoặc opaque token. Với JWT, resource server thường xác minh chữ ký và claims bằng `JwtDecoder`. Với opaque token, token thường là một chuỗi không mang claims có thể đọc trực tiếp; resource server hỏi một **introspection endpoint** hoặc một `OpaqueTokenIntrospector` để xác định token còn hiệu lực và lấy principal/attributes/authorities tương ứng.

Khi kiểm thử controller hoặc authorization rule, ta thường đã biết danh tính và quyền cần mô phỏng. Không cần gọi introspection server cho từng test chỉ để kiểm tra endpoint có cho phép `SCOPE_message:read` hay không. Spring Security Test cung cấp request post-processor `opaqueToken()` cho `MockMvc`; nó chuẩn bị một `BearerTokenAuthentication` cùng principal và authorities giả lập cho request.

Trong module **SPRING_SECURITY_TESTING**, mục tiêu là kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng `spring-security-test` trên ứng dụng Servlet và Reactive. Bài này tập trung vào `opaqueToken()` trong MockMvc: cách tạo principal opaque-token, tùy chỉnh attributes/authorities, kiểm tra request được phép/bị từ chối và phân biệt test authorization với kiểm thử introspection runtime.

Sau bài học, bạn có thể:

- Giải thích `opaqueToken()` tạo `BearerTokenAuthentication` cho request mock như thế nào.
- Dùng `attributes(...)` để cung cấp subject, tenant hoặc claims mà controller cần đọc.
- Dùng `authorities(...)` để kiểm tra các quyền `SCOPE_*` hoặc authority tùy biến.
- Phân biệt `opaqueToken()` với `jwt()`, `@WithMockUser` và `authentication(...)`.
- Kiểm tra `200`, `401`, `403` qua `MockMvc` và security filter chain.
- Viết test riêng cho `OpaqueTokenIntrospector` và bearer-token runtime flow khi cần xác minh token thực sự được introspect.

## 2. `opaqueToken()` đặt authentication nào vào request?

`SecurityMockMvcRequestPostProcessors.opaqueToken()` tạo một authentication phù hợp với Resource Server opaque-token support: `BearerTokenAuthentication`. Principal của nó triển khai `OAuth2AuthenticatedPrincipal`, chứa attributes và authorities. Vì vậy, controller có thể đọc principal qua `@AuthenticationPrincipal OAuth2AuthenticatedPrincipal`, hoặc code security có thể kiểm tra `Authentication`/authorities như khi nhận opaque token đã được xác thực.

```mermaid
flowchart TD
    A[MockMvc request] --> B[.with(opaqueToken())]
    B --> C[OAuth2AuthenticatedPrincipal giả lập]
    C --> D[Attributes + authorities]
    D --> E[BearerTokenAuthentication]
    E --> F[SecurityContext của request]
    F --> G[Authorization rules]
    G --> H[Controller / service]
```

Helper này được dùng để **cấp sẵn kết quả xác thực** cho request mock. Nó không gọi introspection endpoint và không xác minh chuỗi token opaque thật. Đây là điểm quan trọng khi diễn giải kết quả: test có thể chứng minh endpoint xử lý đúng một `BearerTokenAuthentication` với attributes/authorities đã chọn, nhưng không chứng minh introspection server hoạt động.

### Các kiểu dữ liệu cần phân biệt

| Thành phần | Vai trò | Ví dụ |
| --- | --- | --- |
| Opaque access token | Chuỗi bearer token client gửi trong HTTP header | `Authorization: Bearer opaque-value` |
| `OpaqueTokenIntrospector` | Kiểm tra token và trả về principal đã xác thực | `OAuth2AuthenticatedPrincipal` |
| `OAuth2AuthenticatedPrincipal` | Principal có tên, attributes và authorities | `sub=alice`, `tenant_id=tenant-a` |
| `BearerTokenAuthentication` | Authentication mà Resource Server tạo sau introspection | Principal + access token + authorities |
| `opaqueToken()` | Helper tạo authentication giả lập trong MockMvc | Không gọi introspection server |

## 3. Thiết lập dependency và security filter chain

Trong ứng dụng Spring Boot Servlet dùng opaque-token Resource Server, dependency thường là:

```gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-oauth2-resource-server")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
}
```

Một `SecurityFilterChain` tối giản có thể cấu hình opaque-token support như sau:

```java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            OpaqueTokenIntrospector introspector) throws Exception {

        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/api/**").authenticated()
                        .anyRequest().permitAll())
                .oauth2ResourceServer(resourceServer -> resourceServer
                        .opaqueToken(opaque -> opaque.introspector(introspector)))
                .build();
    }
}
```

Trong production, `OpaqueTokenIntrospector` có thể được cấu hình từ issuer/introspection URI và client credentials. Trong test tích hợp runtime, ta có thể thay bean này bằng một test double. Khi dùng `opaqueToken()` để kiểm thử authorization, request post-processor chuẩn bị authentication trực tiếp; không cần token introspection chỉ để cấp principal cho request mock.

## 4. Dùng `opaqueToken()` cho request đơn giản

Với endpoint chỉ cần một bearer authentication và authority mặc định của helper, test có thể viết ngắn:

```java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.opaqueToken;

@Test
void opaqueBearerCanAccessProtectedEndpoint() throws Exception {
    mvc.perform(get("/api/messages").with(opaqueToken()))
            .andExpect(status().isOk());
}
```

Đây là cách kiểm tra endpoint yêu cầu người dùng đã xác thực. Nếu endpoint còn yêu cầu một scope cụ thể, hãy cung cấp authority tương ứng một cách tường minh để test không phụ thuộc vào giá trị mặc định của helper.

`opaqueToken()` được import tĩnh từ `SecurityMockMvcRequestPostProcessors`. Nó là một `RequestPostProcessor`, nên được truyền vào `.with(...)` trên request builder của MockMvc.

## 5. Tùy chỉnh attributes của principal

Opaque token introspection thường trả về attributes như `sub`, `client_id`, `tenant_id`, `scope` hoặc các claim do authorization server định nghĩa. Khi controller đọc các attributes đó, dùng `attributes(...)` để tạo principal phù hợp.

Ví dụ endpoint đọc subject và tenant:

```java
package com.example.security;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MessageController {

    @GetMapping("/api/messages")
    public Map<String, String> messages(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        return Map.of(
                "subject", principal.getAttribute("sub"),
                "tenant", principal.getAttribute("tenant_id"));
    }
}
```

Test cung cấp attributes:

```java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.opaqueToken;

@Test
void principalAttributesAreAvailableToController() throws Exception {
    mvc.perform(get("/api/messages")
            .with(opaqueToken().attributes(attributes -> {
                attributes.put("sub", "alice");
                attributes.put("tenant_id", "tenant-a");
                attributes.put("client_id", "billing-client");
            })))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject").value("alice"))
            .andExpect(jsonPath("$.tenant").value("tenant-a"));
}
```

`attributes(...)` nhận một consumer thao tác trên map attributes của principal. Hãy cung cấp đúng tên và kiểu dữ liệu mà controller, converter hoặc policy đọc. Nếu production kỳ vọng `tenant_id` là chuỗi nhưng test lại đưa vào một object khác kiểu, test có thể không đại diện đúng hợp đồng runtime.

## 6. Tùy chỉnh authorities cho authorization

Với Resource Server opaque token, authorities thường được tạo từ attributes introspection hoặc mapper tùy chỉnh. Một quy ước phổ biến là scope `message:read` được biểu diễn thành authority `SCOPE_message:read`.

Nếu endpoint dùng:

```java
@PreAuthorize("hasAuthority('SCOPE_message:read')")
public List<Message> readMessages() {
    // ...
}
```

thì test nên cấp authority tương ứng:

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.opaqueToken;

@Test
void scopeMessageReadAllowsAccess() throws Exception {
    mvc.perform(get("/api/messages")
            .with(opaqueToken().authorities(
                    new SimpleGrantedAuthority("SCOPE_message:read"))))
            .andExpect(status().isOk());
}
```

Khi test cần nhiều authority, truyền collection hoặc nhiều `GrantedAuthority` theo overload mà API cung cấp. Ví dụ:

```java
.with(opaqueToken().authorities(
        new SimpleGrantedAuthority("SCOPE_message:read"),
        new SimpleGrantedAuthority("invoice:read")))
```

Authorities được so sánh theo chuỗi chính xác. `SCOPE_message:read`, `message:read` và `ROLE_MESSAGE_READER` là các authority khác nhau. `hasRole('MESSAGE_READER')` theo mặc định kiểm tra `ROLE_MESSAGE_READER`, không tự khớp scope.

### Attributes và authorities là hai phần riêng

`attributes(...)` mô tả dữ liệu principal; `authorities(...)` xác định quyền mà `Authentication` mang theo. Đặt attribute `scope` thành `message:read` không nên được hiểu là mọi test helper đều tự động chạy converter production để suy ra `SCOPE_message:read`. Khi mục tiêu là kiểm tra authorization, cấp authority rõ ràng. Khi mục tiêu là kiểm tra mapping attributes thành authorities, kiểm thử mapper/converter riêng hoặc đi qua runtime introspector/provider flow.

## 7. Ví dụ hoàn chỉnh: kiểm tra scope và tenant

Giả sử endpoint chỉ cho phép principal có scope `SCOPE_invoice:read` và `tenant_id` trùng tenant trên URL. Component kiểm tra tenant:

```java
package com.example.security;

import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import org.springframework.stereotype.Component;

@Component("opaqueTenantPolicy")
public class OpaqueTenantPolicy {

    public boolean matches(Authentication authentication, String requestedTenant) {
        if (!(authentication instanceof BearerTokenAuthentication bearer)) {
            return false;
        }
        String tenantId = bearer.getTokenAttributes().get("tenant_id") instanceof String value
                ? value : null;
        return tenantId != null && tenantId.equals(requestedTenant);
    }
}
```

Controller:

```java
package com.example.security;

import java.util.Map;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.parameters.P;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/tenants")
public class InvoiceController {

    @GetMapping("/{tenantId}/invoices")
    @PreAuthorize("hasAuthority('SCOPE_invoice:read') and "
            + "@opaqueTenantPolicy.matches(authentication, #tenantId)")
    public Map<String, String> invoices(
            @PathVariable("tenantId") @P("tenantId") String tenantId,
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        return Map.of("tenantId", tenantId,
                "subject", principal.getAttribute("sub"));
    }
}
```

Test cho trường hợp được phép, thiếu scope và sai tenant:

```java
package com.example.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.opaqueToken;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OpaqueInvoiceAuthorizationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void validScopeAndTenantAreAllowed() throws Exception {
        mvc.perform(get("/api/tenants/tenant-a/invoices")
                .with(opaqueToken()
                        .attributes(attrs -> {
                            attrs.put("sub", "alice");
                            attrs.put("tenant_id", "tenant-a");
                        })
                        .authorities(new SimpleGrantedAuthority("SCOPE_invoice:read"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.subject").value("alice"));
    }

    @Test
    void missingScopeIsForbidden() throws Exception {
        mvc.perform(get("/api/tenants/tenant-a/invoices")
                .with(opaqueToken()
                        .attributes(attrs -> {
                            attrs.put("sub", "alice");
                            attrs.put("tenant_id", "tenant-a");
                        })
                        .authorities()))
                .andExpect(status().isForbidden());
    }

    @Test
    void wrongTenantIsForbidden() throws Exception {
        mvc.perform(get("/api/tenants/tenant-a/invoices")
                .with(opaqueToken()
                        .attributes(attrs -> {
                            attrs.put("sub", "bob");
                            attrs.put("tenant_id", "tenant-b");
                        })
                        .authorities(new SimpleGrantedAuthority("SCOPE_invoice:read"))))
                .andExpect(status().isForbidden());
    }
}
```

Các test trên giả định `@EnableMethodSecurity`, `SecurityFilterChain` và controller/policy được nạp. Cần import `SimpleGrantedAuthority`. Ca thiếu scope dùng authentication đã được tạo nhưng không có authority nên bị `403`; ca sai tenant có đúng scope nhưng policy từ chối phạm vi. Nếu request không có bearer authentication, entry point của Resource Server thường trả `401`.

## 8. So sánh `opaqueToken()`, `jwt()`, `@WithMockUser` và `authentication()`

| Công cụ | Authentication được mô phỏng | Principal thường gặp | Khi nên dùng |
| --- | --- | --- | --- |
| `opaqueToken()` | `BearerTokenAuthentication` | `OAuth2AuthenticatedPrincipal` | Ứng dụng nhận opaque bearer token và code đọc token attributes/principal |
| `jwt()` | `JwtAuthenticationToken` | `Jwt` | Ứng dụng dùng JWT Resource Server, đọc claims JWT |
| `@WithMockUser` | `UsernamePasswordAuthenticationToken` | `UserDetails` mock | Chỉ cần username và role/authority đơn giản |
| `.with(authentication(auth))` | Chính authentication mà test truyền vào | Tùy token được tạo | Cần kiểm tra subtype hoặc principal tùy biến cụ thể |

Không thay `opaqueToken()` bằng `jwt()` chỉ vì cả hai đều là bearer token. Opaque-token Resource Server thường cung cấp `BearerTokenAuthentication`; JWT Resource Server thường cung cấp `JwtAuthenticationToken`. Nếu controller ép kiểu sang `Jwt` nhưng runtime đang dùng opaque token, code có thể lỗi dù test `jwt()` pass. Ngược lại, nếu code cần `OAuth2AuthenticatedPrincipal` hoặc `BearerTokenAuthentication`, hãy dùng helper đúng loại.

## 9. `opaqueToken()` không kiểm thử introspection runtime

Đây là giới hạn quan trọng nhất của bài. Request post-processor `opaqueToken()` tạo authentication cho request mock; nó không gửi HTTP `Authorization: Bearer ...` qua `BearerTokenAuthenticationFilter` để gọi `OpaqueTokenIntrospector`. Vì thế, nó không xác minh:

- Token có đang active hay không.
- Introspection endpoint có phản hồi đúng hoặc có thể truy cập không.
- Client credentials dùng gọi introspection có hợp lệ không.
- Claims trả về từ introspection có được ánh xạ đúng bởi introspector/mapper production không.
- Token hết hạn, bị revoke hoặc thiếu scope có bị từ chối trong runtime flow không.

Nếu muốn kiểm tra `OpaqueTokenIntrospector`, viết unit test trực tiếp cho implementation/mapper. Nếu muốn xác nhận filter chain gọi introspector, gửi bearer header trong `MockMvc` và cung cấp một introspector test double.

### 9.1. Test `OpaqueTokenIntrospector` riêng

Một implementation introspector tùy biến có thể được kiểm tra như một bean/service thông thường:

```java
@Test
void introspectorMapsActiveTokenToPrincipal() {
    OAuth2AuthenticatedPrincipal principal = introspector.introspect("opaque-test-token");

    assertThat(principal.getName()).isEqualTo("alice");
    assertThat(principal.getAttribute("tenant_id")).isEqualTo("tenant-a");
    assertThat(principal.getAuthorities())
            .extracting(GrantedAuthority::getAuthority)
            .contains("SCOPE_invoice:read");
}
```

Test này cần import `OAuth2AuthenticatedPrincipal`, `GrantedAuthority` và AssertJ. Nó kiểm tra kết quả introspector nhưng không nhất thiết gọi endpoint HTTP. Thêm ca token inactive/unknown và xác nhận implementation ném `BadOpaqueTokenException` theo hợp đồng của Spring Security.

### 9.2. Test bearer token qua filter chain với introspector test double

Để xác minh runtime path, cấu hình một `OpaqueTokenIntrospector` test double trả principal cố định:

```java
@TestConfiguration
class OpaqueTokenTestConfiguration {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector() {
        return token -> {
            if (!token.equals("opaque-test-token")) {
                throw new BadOpaqueTokenException("Token không hợp lệ");
            }

            Map<String, Object> attributes = Map.of(
                    "sub", "alice",
                    "tenant_id", "tenant-a");
            Collection<GrantedAuthority> authorities = List.of(
                    new SimpleGrantedAuthority("SCOPE_invoice:read"));

            return new DefaultOAuth2AuthenticatedPrincipal(
                    "alice", attributes, authorities);
        };
    }
}
```

Khi `SecurityFilterChain` nhận bean introspector này, test gửi header bearer token thật qua MockMvc:

```java
@SpringBootTest
@AutoConfigureMockMvc
@Import(OpaqueTokenTestConfiguration.class)
class OpaqueTokenRuntimeTests {

    @Autowired
    MockMvc mvc;

    @Test
    void bearerHeaderUsesIntrospector() throws Exception {
        mvc.perform(get("/api/tenants/tenant-a/invoices")
                .header(HttpHeaders.AUTHORIZATION, "Bearer opaque-test-token"))
                .andExpect(status().isOk());
    }

    @Test
    void invalidTokenIsUnauthorized() throws Exception {
        mvc.perform(get("/api/tenants/tenant-a/invoices")
                .header(HttpHeaders.AUTHORIZATION, "Bearer invalid-token"))
                .andExpect(status().isUnauthorized());
    }
}
```

Đoạn code cần import `OpaqueTokenIntrospector`, `BadOpaqueTokenException`, `DefaultOAuth2AuthenticatedPrincipal`, `OAuth2AuthenticatedPrincipal`, `GrantedAuthority`, `Collection`, `List`, `Map`, `HttpHeaders`, `@TestConfiguration`, `@Bean`, `@Import`, `MockMvc` và các matcher. Cấu hình `SecurityFilterChain` phải dùng `.opaqueToken(opaque -> opaque.introspector(introspector))` hoặc tự động lấy bean introspector theo cấu hình ứng dụng. Test này đi qua bearer filter, authentication provider và introspector test double; nó xác minh kết nối runtime, nhưng không gọi authorization server thật.

Để kiểm thử giao tiếp introspection thực, dùng test server hoặc môi trường identity provider chuyên dụng và credential test. Không đưa client secret production vào test hoặc log.

## 10. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Controller không nhận `OAuth2AuthenticatedPrincipal` | Test dùng `@WithMockUser` hoặc `jwt()` tạo sai loại principal | Dùng `opaqueToken()` hoặc `BearerTokenAuthentication` phù hợp |
| `hasAuthority('SCOPE_invoice:read')` bị từ chối | Authorities chưa được cấp hoặc sai prefix/chuỗi | Dùng `.authorities(new SimpleGrantedAuthority("SCOPE_invoice:read"))` |
| Attribute `tenant_id` trả `null` | Test không cấu hình attribute hoặc sai tên claim | Dùng `.attributes(attrs -> attrs.put("tenant_id", ...))` |
| Test `opaqueToken()` pass nhưng token thật bị `401` | Helper bỏ qua introspection runtime | Test `OpaqueTokenIntrospector` và bearer filter chain riêng |
| Token sai vẫn được chấp nhận trong test helper | `opaqueToken()` không nhận/kiểm tra token value thực | Dùng header bearer với introspector test double để test runtime |
| Test `jwt()` pass nhưng production opaque token lỗi kiểu principal | Hai helper tạo authentication subtype khác nhau | Dùng đúng `opaqueToken()` cho opaque-token resource server |
| Request trả `403` | Token đã được mô phỏng/xác thực nhưng thiếu quyền hoặc sai tenant | Kiểm tra authorities, attributes và policy |
| Request trả `401` | Không có authentication hoặc introspector từ chối token | Kiểm tra bearer header và kết quả introspection |

Khi debug, kiểm tra theo thứ tự: request đang dùng helper nào; `Authentication` có phải `BearerTokenAuthentication` không; principal có attributes cần thiết không; authorities có đúng chuỗi không; policy có so sánh tenant hoặc scope khác không. Đừng suy ra introspection hoạt động chỉ từ một test dùng `opaqueToken()`.

## 11. Bài thực hành

Với endpoint `GET /api/tenants/{tenantId}/invoices`, hoàn thành các ca sau:

1. Dùng `opaqueToken()` với `sub=alice`, `tenant_id=tenant-a` và `SCOPE_invoice:read`; request đến `tenant-a` được phép.
2. Giữ principal nhưng bỏ authority; request trả `403`.
3. Giữ authority nhưng đổi `tenant_id` thành `tenant-b`; request đến `tenant-a` trả `403`.
4. Thêm assertion controller nhận principal là `OAuth2AuthenticatedPrincipal` và đọc đúng `sub`.
5. Viết unit test cho introspector mapping attributes thành authorities.
6. Thay introspector bằng test double và gửi `Authorization: Bearer opaque-test-token` qua MockMvc; xác minh runtime filter chain gọi introspector.
7. Cho introspector từ chối token không hợp lệ và kiểm tra entry point trả `401`.
8. So sánh kết quả khi dùng `jwt()` hoặc `@WithMockUser` để thấy khác biệt authentication/principal type.

### Câu hỏi tự đánh giá

- `opaqueToken()` tạo loại `Authentication` nào và principal triển khai interface nào?
- Vì sao `attributes(...)` và `authorities(...)` là hai cấu hình riêng?
- Một test dùng `opaqueToken()` chứng minh được gì về authorization và không chứng minh được gì về introspection?
- Khi nào nên dùng `opaqueToken()` thay cho `jwt()`?
- Làm thế nào kiểm tra `BearerTokenAuthenticationFilter` và `OpaqueTokenIntrospector` được gọi trong runtime path?
- Vì sao token không tồn tại trong fixture khác với token tồn tại nhưng thiếu authority?

## Tài liệu tham khảo

- [Spring Security — Testing OAuth 2.0 Opaque Token](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — MockMvc Request Post Processors](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/request-post-processors.html)
- [Spring Security — Servlet Authentication Architecture](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html)

`opaqueToken()` là lựa chọn phù hợp khi cần kiểm thử một request như thể Resource Server đã introspect opaque token và tạo `BearerTokenAuthentication`. Hãy cấu hình attributes cùng authorities đúng với hợp đồng mà endpoint sử dụng. Khi cần chứng minh token thực sự được introspect, hãy kiểm thử `OpaqueTokenIntrospector` và gửi bearer header qua filter chain; hai lớp test này bổ sung cho nhau.
