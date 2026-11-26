# Tùy chỉnh principal, attributes và authorities

## 1. Vì sao cần tùy chỉnh principal của opaque token?

Opaque token thường không chứa claims có thể đọc trực tiếp từ chuỗi token. Sau khi introspection thành công, Resource Server nhận được một principal với tên, attributes và authorities. Trong ứng dụng, controller hoặc policy có thể cần các dữ liệu như `user_id`, `tenant_id`, `client_id`, nhóm người dùng hoặc scope cụ thể.

Khi kiểm thử bằng MockMvc, `opaqueToken()` tạo sẵn một `BearerTokenAuthentication` và một `OAuth2AuthenticatedPrincipal`. Giá trị mặc định hữu ích cho ca đơn giản, nhưng không đại diện mọi cấu trúc principal mà ứng dụng có thể nhận. Spring Security Test cho phép tùy chỉnh ba phần riêng biệt:

- `attributes(...)`: thêm hoặc thay đổi các thuộc tính trên principal mặc định.
- `authorities(...)`: thay danh sách quyền của authentication giả lập.
- `principal(...)`: cung cấp toàn bộ `OAuth2AuthenticatedPrincipal` do test tạo, bao gồm tên, attributes và authorities.

Trong module **SPRING_SECURITY_TESTING**, ta dùng `spring-security-test` để kiểm chứng xác thực, phân quyền và bảo vệ HTTP trên Servlet và Reactive. Bài này tập trung vào principal opaque-token trong `MockMvc`, cách chọn giữa chỉnh sửa attributes và thay toàn bộ principal, cũng như cách xác minh controller/policy tiêu thụ đúng dữ liệu.

Sau bài học, bạn có thể:

1. Phân biệt `BearerTokenAuthentication`, `OAuth2AuthenticatedPrincipal`, token attributes và authorities.
2. Tùy chỉnh attributes với `opaqueToken().attributes(...)`.
3. Cấp authorities tường minh bằng `opaqueToken().authorities(...)`.
4. Tạo principal riêng bằng `DefaultOAuth2AuthenticatedPrincipal` và `opaqueToken().principal(...)`.
5. Kiểm tra principal name khác `sub`, tenant và quyền trong controller hoặc method security.
6. Biết phần nào được giả lập trong MockMvc và phần nào cần kiểm thử ở `OpaqueTokenIntrospector` runtime.

## 2. Cấu trúc authentication được tạo bởi `opaqueToken()`

`opaqueToken()` là request post-processor của Spring Security Test. Nó gắn vào request mock một `BearerTokenAuthentication`. Principal của authentication triển khai `OAuth2AuthenticatedPrincipal`; interface này cung cấp tên principal, map attributes và danh sách `GrantedAuthority`.

```mermaid
flowchart TD
    A[MockMvc request] --> B[opaqueToken()]
    B --> C[BearerTokenAuthentication]
    C --> D[OAuth2AuthenticatedPrincipal]
    D --> E[getName()]
    D --> F[getAttributes()]
    D --> G[getAuthorities()]
    C --> H[getTokenAttributes()]
    E --> I[Controller / authorization]
    F --> I
    G --> I
```

Một request dùng `opaqueToken()` mặc định có:

- Attribute `sub` với giá trị `user`.
- Một authority `SCOPE_read`.
- Một `OAuth2AuthenticatedPrincipal` đơn giản được dùng làm principal.

Những giá trị này đủ để thử endpoint bảo vệ bằng `SCOPE_read`, nhưng ứng dụng thực tế có thể dùng principal name khác, claim `user_id` hoặc `tenant_id`, và các quyền như `SCOPE_invoice:read`. Ta cần tùy chỉnh fixture sao cho khớp hợp đồng mà controller và policy thực sự sử dụng.

### Những API cần nhớ

| API | Thay đổi phần nào? | Dùng khi |
| --- | --- | --- |
| `opaqueToken()` | Tạo authentication opaque-token mặc định | Cần một bearer authentication cơ bản |
| `.attributes(consumer)` | Sửa map attributes của principal mặc định | Cần thêm `user_id`, `tenant_id`, `client_id` hoặc claim khác |
| `.authorities(...)` | Cấp danh sách `GrantedAuthority` | Cần kiểm tra scope/permission cụ thể |
| `.principal(principal)` | Thay toàn bộ principal | Cần principal name tùy biến hoặc implementation riêng |
| `BearerTokenAuthentication#getTokenAttributes()` | Đọc attributes của principal từ authentication | Controller nhận trực tiếp `BearerTokenAuthentication` |
| `Authentication#getAuthorities()` | Đọc quyền dùng cho authorization | Kiểm tra `hasAuthority`/`hasAnyAuthority` |

`attributes(...)` và `authorities(...)` là hai phần độc lập. Đưa `scope=invoice:read` vào attributes không đồng nghĩa helper sẽ tự chạy mapper production để sinh `SCOPE_invoice:read`; khi test authorization, hãy cấp authority tường minh.

## 3. Dùng attributes để bổ sung dữ liệu nghiệp vụ

Giả sử controller nhận `BearerTokenAuthentication` và đọc `user_id`, `tenant_id` từ token attributes:

```java
package com.example.api;

import java.util.Map;

import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ProfileController {

    @GetMapping("/api/profile")
    public Map<String, Object> profile(BearerTokenAuthentication authentication) {
        return Map.of(
                "subject", authentication.getName(),
                "userId", authentication.getTokenAttributes().get("user_id"),
                "tenantId", authentication.getTokenAttributes().get("tenant_id"));
    }
}
```

Test có thể sửa attributes của principal mặc định:

```java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.opaqueToken;

@Test
void customAttributesAreVisibleToController() throws Exception {
    mvc.perform(get("/api/profile")
            .with(opaqueToken().attributes(attrs -> {
                attrs.put("sub", "alice");
                attrs.put("user_id", "u-42");
                attrs.put("tenant_id", "tenant-a");
            })))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.subject").value("alice"))
            .andExpect(jsonPath("$.userId").value("u-42"))
            .andExpect(jsonPath("$.tenantId").value("tenant-a"));
}
```

Consumer nhận map attributes để thay đổi trực tiếp. Trong ví dụ, `sub` cũng được đổi để principal mặc định có tên `alice`; các trường `user_id` và `tenant_id` là attributes bổ sung. Nếu ứng dụng dùng một attribute khác làm principal name, cân nhắc dùng `principal(...)` để quy định tên một cách rõ ràng.

### 3.1. Kiểm tra kiểu dữ liệu của attributes

Attributes là map `String` sang `Object`, do đó giá trị có thể là chuỗi, số, boolean, danh sách hoặc cấu trúc lồng nhau tùy hợp đồng introspection. Test nên cấp đúng kiểu dữ liệu mà code production kỳ vọng.

```java
.with(opaqueToken().attributes(attrs -> {
    attrs.put("sub", "alice");
    attrs.put("tenant_id", "tenant-a");
    attrs.put("account_active", true);
    attrs.put("region_ids", List.of("north", "south"));
}))
```

Nếu production gọi `getAttribute("account_active")` rồi ép kiểu `Boolean`, đừng đưa chuỗi `"true"` trong test. Nếu claim là một danh sách, dùng collection có phần tử đúng kiểu. Những sai lệch kiểu dữ liệu thường làm test giả lập không phản ánh đúng response introspection.

## 4. Gán authorities tường minh

Resource Server thường chuyển scope thành authority có tiền tố `SCOPE_`. Ví dụ scope `invoice:read` có thể được biểu diễn thành `SCOPE_invoice:read`, tùy mapper được cấu hình. Khi controller hoặc method security yêu cầu quyền đó, test cần cấp đúng chuỗi:

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.opaqueToken;

@Test
void invoiceReadScopeAllowsRequest() throws Exception {
    mvc.perform(get("/api/invoices")
            .with(opaqueToken().authorities(
                    new SimpleGrantedAuthority("SCOPE_invoice:read"))))
            .andExpect(status().isOk());
}
```

`authorities(...)` có overload nhận một `Collection<GrantedAuthority>` hoặc một hay nhiều đối số `GrantedAuthority`. Khi gọi phương thức này, danh sách quyền của principal được thay bằng danh sách cung cấp cho test. Vì vậy, có thể dùng `authorities()` không đối số để tạo authentication đã xác thực nhưng không có quyền, hoặc truyền một tập quyền nhỏ để kiểm tra nguyên tắc least privilege.

Ví dụ cấp nhiều quyền:

```java
.with(opaqueToken().authorities(
        new SimpleGrantedAuthority("SCOPE_invoice:read"),
        new SimpleGrantedAuthority("invoice:export")))
```

Không nhầm scope với role:

| Policy | Authority cần có |
| --- | --- |
| `hasAuthority('SCOPE_invoice:read')` | `SCOPE_invoice:read` |
| `hasAuthority('invoice:export')` | `invoice:export` |
| `hasRole('FINANCE')` theo prefix mặc định | `ROLE_FINANCE` |
| `hasAnyAuthority('SCOPE_invoice:read', 'SCOPE_invoice:write')` | Một trong hai authority được nêu |

Một test chỉ xác minh quyền nếu fixture cấp đúng authority. Nếu muốn xác minh scope trong response introspection được ánh xạ thành authority, hãy test mapper hoặc `OpaqueTokenIntrospector` riêng; `.authorities(...)` không tự gọi mapper production.

## 5. Thay toàn bộ principal bằng `principal(...)`

Đôi khi chỉnh `sub` và thêm attributes vẫn chưa đủ. Ứng dụng có thể dùng `user_name` làm tên principal, có custom implementation của `OAuth2AuthenticatedPrincipal`, hoặc cần một tập attributes/authorities được tạo từ một fixture khác. `OpaqueTokenRequestPostProcessor` cung cấp `principal(OAuth2AuthenticatedPrincipal)` để đặt toàn bộ principal.

Spring có sẵn `DefaultOAuth2AuthenticatedPrincipal`, phù hợp cho phần lớn test:

```java
import java.util.Map;

import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;

OAuth2AuthenticatedPrincipal principal = new DefaultOAuth2AuthenticatedPrincipal(
        "alice",
        Map.of(
                "user_name", "alice",
                "user_id", "u-42",
                "tenant_id", "tenant-a"),
        AuthorityUtils.createAuthorityList("SCOPE_invoice:read"));

mvc.perform(get("/api/profile")
        .with(opaqueToken().principal(principal)))
        .andExpect(status().isOk());
```

Constructor nhận tên principal, attributes và authorities. `getName()` sẽ trả về `alice`, dù map không có attribute `sub`. Đây là cách phù hợp khi authorization server dùng `user_name` hoặc một trường riêng làm tên người dùng. Nếu controller đọc `authentication.getName()`, nó sẽ nhận principal name đã truyền; nếu controller đọc `getTokenAttributes()`, các thuộc tính lấy từ principal tùy biến sẽ được cung cấp qua authentication.

### 5.1. Khi nào chọn `attributes(...)`, khi nào chọn `principal(...)`?

| Nhu cầu | Cách chọn | Lý do |
| --- | --- | --- |
| Chỉ thêm `tenant_id` hoặc `user_id`, vẫn dùng tên principal mặc định từ `sub` | `attributes(...)` | Giữ principal mặc định và chỉnh map |
| Đổi `sub` để principal mặc định có tên khác | `attributes(...)` có thể đủ | Nếu quy tắc mặc định lấy tên từ `sub` |
| Principal name đến từ `user_name`, không phải `sub` | `principal(...)` | Quy định rõ `getName()` |
| Cần implementation `OAuth2AuthenticatedPrincipal` riêng | `principal(...)` | Đưa object principal hoàn chỉnh vào request |
| Cần attributes và authorities cố định, dùng lại nhiều test | Tạo `DefaultOAuth2AuthenticatedPrincipal`, rồi `principal(...)` | Gom hợp đồng principal vào một fixture có thể tái sử dụng |

Không cần tạo custom class chỉ để đổi tên principal. `DefaultOAuth2AuthenticatedPrincipal` đã hỗ trợ tên tùy chỉnh, attributes và authorities. Chỉ triển khai `OAuth2AuthenticatedPrincipal` riêng khi ứng dụng thực sự phụ thuộc vào hành vi hoặc cấu trúc đặc thù.

## 6. Controller có thể nhận principal trực tiếp

Ngoài việc nhận `BearerTokenAuthentication`, controller cũng có thể nhận `OAuth2AuthenticatedPrincipal` qua `@AuthenticationPrincipal`:

```java
package com.example.api;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentUserController {

    @GetMapping("/api/current-user")
    public Map<String, Object> currentUser(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        return Map.of(
                "name", principal.getName(),
                "userId", principal.getAttribute("user_id"),
                "tenantId", principal.getAttribute("tenant_id"));
    }
}
```

Test kết hợp principal tùy biến và authorities:

```java
@Test
void controllerReceivesCustomPrincipalNameAndAttributes() throws Exception {
    Map<String, Object> attributes = Map.of(
            "user_name", "alice",
            "user_id", "u-42",
            "tenant_id", "tenant-a");

    OAuth2AuthenticatedPrincipal principal =
            new DefaultOAuth2AuthenticatedPrincipal(
                    "alice", attributes,
                    AuthorityUtils.createAuthorityList("SCOPE_profile:read"));

    mvc.perform(get("/api/current-user")
            .with(opaqueToken().principal(principal)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.name").value("alice"))
            .andExpect(jsonPath("$.userId").value("u-42"))
            .andExpect(jsonPath("$.tenantId").value("tenant-a"));
}
```

Trong test này, authorities nằm trên principal được truyền vào. Không cần gọi thêm `.authorities(...)`; nếu muốn thay quyền, hãy tạo principal mới với danh sách authority mong muốn. Cách này bảo đảm principal name, attributes và authorities được kiểm soát trong cùng một fixture.

## 7. Kiểm tra authorization với attributes và authorities

Giả sử endpoint đọc hóa đơn cần scope `SCOPE_invoice:read` và tenant trong principal phải trùng tenant trên URL. Policy:

```java
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import org.springframework.stereotype.Component;

@Component("opaqueTenantPolicy")
public class OpaqueTenantPolicy {

    public boolean matches(BearerTokenAuthentication authentication,
                           String requestedTenant) {
        Object value = authentication.getTokenAttributes().get("tenant_id");
        return value instanceof String tenantId
                && tenantId.equals(requestedTenant);
    }
}
```

Method security trên controller:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.parameters.P;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;

@GetMapping("/api/tenants/{tenantId}/invoices")
@PreAuthorize("hasAuthority('SCOPE_invoice:read') and "
        + "@opaqueTenantPolicy.matches(authentication, #tenantId)")
public Map<String, String> invoices(@PathVariable("tenantId") @P("tenantId") String tenantId,
        BearerTokenAuthentication authentication) {
    return Map.of("tenantId", tenantId, "subject", authentication.getName());
}
```

Đảm bảo ứng dụng bật `@EnableMethodSecurity` và security filter chain cho Resource Server. Trong ví dụ, tenant là dữ liệu principal; authority là quyền thực hiện hành động. Hai điều kiện được đánh giá độc lập.

Test ma trận:

```java
import org.springframework.security.core.authority.SimpleGrantedAuthority;

@Test
void rightPrincipalAndAuthorityAreAllowed() throws Exception {
    mvc.perform(get("/api/tenants/tenant-a/invoices")
            .with(opaqueToken()
                    .attributes(attrs -> attrs.put("tenant_id", "tenant-a"))
                    .authorities(new SimpleGrantedAuthority("SCOPE_invoice:read"))))
            .andExpect(status().isOk());
}

@Test
void missingAuthorityIsForbidden() throws Exception {
    mvc.perform(get("/api/tenants/tenant-a/invoices")
            .with(opaqueToken()
                    .attributes(attrs -> attrs.put("tenant_id", "tenant-a"))
                    .authorities()))
            .andExpect(status().isForbidden());
}

@Test
void wrongTenantIsForbidden() throws Exception {
    mvc.perform(get("/api/tenants/tenant-a/invoices")
            .with(opaqueToken()
                    .attributes(attrs -> attrs.put("tenant_id", "tenant-b"))
                    .authorities(new SimpleGrantedAuthority("SCOPE_invoice:read"))))
            .andExpect(status().isForbidden());
}
```

Các ca trên phân biệt ba trạng thái: đủ quyền và đúng tenant; authentication tồn tại nhưng thiếu quyền; đủ quyền nhưng tenant không khớp. Request không dùng `opaqueToken()` sẽ đi qua authentication entry point của Resource Server và thường trả `401` nếu không có bearer token hợp lệ.

## 8. Tái sử dụng principal fixture trong nhiều test

Nếu nhiều test cần cùng một cấu trúc principal, tạo helper trả về `OAuth2AuthenticatedPrincipal` mới cho mỗi lần gọi:

```java
static OAuth2AuthenticatedPrincipal invoiceReader(
        String username, String userId, String tenantId) {

    Map<String, Object> attributes = Map.of(
            "user_name", username,
            "user_id", userId,
            "tenant_id", tenantId);

    return new DefaultOAuth2AuthenticatedPrincipal(
            username,
            attributes,
            AuthorityUtils.createAuthorityList("SCOPE_invoice:read"));
}
```

Sử dụng:

```java
mvc.perform(get("/api/tenants/tenant-a/invoices")
        .with(opaqueToken().principal(
                invoiceReader("alice", "u-42", "tenant-a"))))
    .andExpect(status().isOk());
```

Helper chỉ lắp ráp fixture, không gọi introspection server hoặc lưu principal mutable vào biến static. Có thể truyền thêm danh sách authority nếu từng test cần kiểm tra least privilege. Tránh một principal dùng chung bị sửa attributes giữa nhiều request hoặc test song song.

## 9. Phân biệt attributes, principal và authorities ở runtime

Khi introspection thành công, `OpaqueTokenIntrospector` trả về một `OAuth2AuthenticatedPrincipal`. `BearerTokenAuthentication` sử dụng principal này và authorities của nó. Vì vậy, cấu trúc principal trong test cần tương ứng với kết quả introspection mà ứng dụng mong đợi.

| Thành phần runtime | Nơi được truy cập | Ví dụ |
| --- | --- | --- |
| Principal name | `authentication.getName()` hoặc `principal.getName()` | `alice` |
| Attributes | `principal.getAttribute("tenant_id")` hoặc `authentication.getTokenAttributes().get("tenant_id")` | `tenant-a` |
| Authorities | `authentication.getAuthorities()` hoặc `principal.getAuthorities()` | `SCOPE_invoice:read` |
| Opaque access token | `authentication.getToken()` | Đối tượng access token, không phải map attributes |

Không nhầm `getToken()` với `getTokenAttributes()`. Token là đối tượng biểu diễn bearer access token; attributes là dữ liệu principal nhận từ introspection. Nếu controller cần `tenant_id`, hãy đọc từ principal/token attributes theo API phù hợp, không ép token thành map.

## 10. `opaqueToken()` không chạy mapper/introspector production

Các tùy chỉnh `attributes(...)`, `authorities(...)` và `principal(...)` cung cấp trực tiếp dữ liệu cho authentication giả lập. Chúng không tự gọi `OpaqueTokenIntrospector`, không gửi token đến authorization server và không tự chạy mapper production.

Do đó:

- Dùng `opaqueToken()` để kiểm tra controller, method security và authorization với principal/authorities đã biết.
- Test mapper hoặc introspector riêng nếu muốn kiểm tra attributes từ response introspection được chuyển thành principal/authorities đúng.
- Gửi `Authorization: Bearer ...` qua `MockMvc` với một `OpaqueTokenIntrospector` test double nếu muốn chứng minh bearer filter chain gọi introspector.
- Dùng test server/identity provider chuyên dụng nếu cần xác minh giao tiếp introspection thật, client credentials, token active/inactive hoặc revoke.

Một test dùng `.authorities(new SimpleGrantedAuthority("SCOPE_invoice:read"))` không chứng minh claim scope trong introspection response được ánh xạ đúng. Nó chỉ chứng minh endpoint cho phép authentication đã được cấp authority ấy.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| `authentication.getName()` không phải username mong muốn | Principal name mặc định lấy từ thuộc tính mặc định hoặc test chỉ thêm `user_name` | Dùng `principal(...)` với tên tường minh |
| Controller đọc `tenant_id` thành `null` | Test chưa thêm attribute hoặc sai key | Dùng `attributes(attrs -> attrs.put("tenant_id", ...))` hoặc custom principal |
| Có attribute `scope` nhưng `hasAuthority` bị từ chối | Attributes không tự động trở thành authorities trong helper | Cấp `authorities(...)` hoặc test mapper runtime riêng |
| `hasRole('FINANCE')` không khớp `SCOPE_invoice:read` | Role và scope là hai authority khác nhau | Cấp `ROLE_FINANCE` hoặc sửa policy theo yêu cầu thực tế |
| Principal tùy biến có authorities nhưng endpoint vẫn bị từ chối | Principal được tạo với authority không đúng chuỗi hoặc policy yêu cầu thêm điều kiện | Assert `principal.getAuthorities()` và kiểm tra policy |
| Controller ép kiểu principal bị lỗi | Dùng helper khác loại authentication hoặc principal | Dùng `opaqueToken()`/`principal(...)` với `OAuth2AuthenticatedPrincipal` |
| Test helper pass nhưng token thật không được chấp nhận | Helper không gọi introspection | Test `OpaqueTokenIntrospector` và runtime bearer filter chain riêng |
| Test chạy không có security context | MockMvc thiếu security filter/context integration | Dùng `@AutoConfigureMockMvc` hoặc `.apply(springSecurity())` |

Khi debug, kiểm tra lần lượt `authentication.getClass()`, `authentication.getName()`, `authentication.getPrincipal().getClass()`, attributes và authorities. Những assertion này xác nhận test đã dựng đúng loại danh tính trước khi kiểm tra kết quả authorization.

## 12. Bài thực hành

Với API hóa đơn đa tenant, hoàn thành các ca sau:

1. Dùng `attributes(...)` để thêm `user_id=u-42` và `tenant_id=tenant-a`; xác nhận controller đọc đúng giá trị.
2. Dùng `authorities(...)` để cấp `SCOPE_invoice:read`; request đọc tenant đúng được phép.
3. Bỏ authority nhưng giữ attributes; request trả `403`.
4. Giữ authority nhưng đổi `tenant_id` thành `tenant-b`; request đến `tenant-a` trả `403`.
5. Dùng `DefaultOAuth2AuthenticatedPrincipal` với principal name `alice` và attribute `user_name`; xác nhận `authentication.getName()` trả `alice` dù không có `sub`.
6. Tạo helper principal fixture và xác nhận mỗi test nhận principal/attributes độc lập.
7. Viết test riêng cho `OpaqueTokenIntrospector` để xác nhận response introspection được ánh xạ thành principal và authorities.
8. Gửi bearer header qua MockMvc với introspector test double để phân biệt runtime authentication với authentication được `opaqueToken()` cài trực tiếp.

### Câu hỏi tự đánh giá

- `attributes(...)` thay đổi dữ liệu nào trong principal mặc định?
- `authorities(...)` có tự đọc attribute `scope` và chạy converter production không?
- Khi nào nên dùng `principal(...)` thay cho `attributes(...)`?
- `BearerTokenAuthentication#getTokenAttributes()` khác `getToken()` như thế nào?
- Vì sao principal name có thể khác giá trị `sub`?
- Một test `opaqueToken()` có thể chứng minh điều gì về authorization và điều gì cần test introspector riêng?

## Tài liệu tham khảo

- [Spring Security — Testing Opaque Token Authentication](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
- [Spring Security — `OpaqueTokenRequestPostProcessor` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/test/web/servlet/request/SecurityMockMvcRequestPostProcessors.OpaqueTokenRequestPostProcessor.html)
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — MockMvc Setup](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/setup.html)

`attributes(...)` phù hợp khi cần bổ sung dữ liệu cho principal mặc định; `authorities(...)` phù hợp khi cần kiểm tra quyền cụ thể; `principal(...)` phù hợp khi cần kiểm soát toàn bộ principal, đặc biệt là tên principal và implementation. Hãy chọn API theo đúng phần hợp đồng mà endpoint tiêu thụ, rồi kiểm tra riêng introspector runtime nếu mục tiêu là xác minh cách token thật được chuyển thành danh tính.
