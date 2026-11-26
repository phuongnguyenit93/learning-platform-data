# JwtAuthenticationConverter hoặc bộ chuyển đổi quyền tùy chỉnh

## 1. Từ JWT đã xác minh đến Authentication của ứng dụng

Trong một ứng dụng OAuth2 Resource Server, client gửi access token dạng JWT trong header `Authorization: Bearer ...`. Spring Security giải mã và xác minh token trước, sau đó chuyển các claim của JWT thành đối tượng `Authentication` để dùng trong `SecurityContext`. Bước chuyển đổi này quyết định principal có tên gì và người dùng nhận được những `GrantedAuthority` nào.

Ví dụ, một token có thể chứa:

~~~json
{
  "sub": "user-42",
  "preferred_username": "lan",
  "scope": "reports.read reports.export",
  "permissions": ["REPORT_READ", "REPORT_EXPORT"],
  "roles": ["REPORT_ANALYST"]
}
~~~

Ứng dụng có thể muốn principal name là `lan`, scope trở thành `SCOPE_reports.read`, và permission trở thành `PERM_REPORT_READ`. Nếu converter ánh xạ sai claim hoặc prefix, người dùng hợp lệ có thể bị từ chối truy cập; nếu converter vô tình cấp quyền quá rộng, hệ thống có thể cho phép thao tác ngoài ý muốn.

Spring Security cung cấp `JwtAuthenticationConverter` để chuyển một `Jwt` thành `JwtAuthenticationToken`, và `JwtGrantedAuthoritiesConverter` để ánh xạ scope thành authorities. Khi claim của hệ thống có cấu trúc riêng, ta có thể cài đặt một converter quyền tùy chỉnh rồi gắn vào `JwtAuthenticationConverter`.

Bài học thuộc chương **Kiểm thử thành phần** của mô-đun **SPRING_SECURITY_TESTING**. Mô-đun kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng `spring-security-test` trên ứng dụng Servlet và Reactive, với `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext` và các cơ chế JWT/OAuth2/OIDC giả lập. Bài này đi sâu vào việc chuyển claim JWT thành principal và authorities, đồng thời phân biệt kiểm thử converter với kiểm thử xác minh chữ ký token.

Sau bài học, bạn có thể:

- Mô tả vị trí của `JwtAuthenticationConverter` trong luồng Resource Server.
- Cấu hình principal claim và authorities claim mặc định.
- Viết `Converter<Jwt, Collection<GrantedAuthority>>` cho claim `permissions` hoặc `roles`.
- Kết hợp scope mặc định với quyền nghiệp vụ tùy chỉnh mà không tạo quyền trùng.
- Kiểm thử dữ liệu thiếu, sai kiểu, rỗng và quyền không được hỗ trợ.
- Gắn converter vào `SecurityFilterChain` Servlet hoặc `SecurityWebFilterChain` Reactive.
- Hiểu vì sao test dùng `jwt()` có thể bỏ qua converter đang cấu hình.

## 2. Vị trí của converter trong luồng xác thực JWT

`JwtAuthenticationConverter` không phải bộ giải mã JWT. Nó nhận một đối tượng `Jwt` đã được tạo bởi `JwtDecoder`, rồi chuyển đổi thông tin bên trong token thành `Authentication`.

~~~mermaid
flowchart TD
    A["HTTP Authorization: Bearer token"] --> B["BearerTokenAuthenticationFilter"]
    B --> C["JwtDecoder"]
    C --> D{"Chữ ký, issuer, audience, thời hạn hợp lệ?"}
    D -- "Không" --> E["Authentication failure / 401"]
    D -- "Có" --> F["Jwt đã được xác minh"]
    F --> G["JwtAuthenticationConverter"]
    G --> H["Principal + GrantedAuthority"]
    H --> I["JwtAuthenticationToken"]
    I --> J["SecurityContext"]
    J --> K["AuthorizationManager / method security"]
    K --> L["Cho phép hoặc từ chối request"]
~~~

Các bước có trách nhiệm riêng:

| Thành phần | Trách nhiệm | Điều cần kiểm thử |
| --- | --- | --- |
| `JwtDecoder` | Giải mã và xác minh token, chữ ký, issuer, thời hạn và validator đã cấu hình | Token hợp lệ được chấp nhận; token sai chữ ký/issuer/hết hạn bị từ chối |
| `JwtAuthenticationConverter` | Chuyển `Jwt` thành `AbstractAuthenticationToken` | Principal name và danh sách authorities |
| `JwtGrantedAuthoritiesConverter` | Chuyển claim scope thành authorities | Tên claim, delimiter và prefix |
| Converter tùy chỉnh | Chuyển claim riêng như `permissions`, `roles`, `groups` | Dữ liệu thiếu/sai kiểu và mapping theo chính sách |
| `AuthorizationManager` | Dùng authorities đã tạo để quyết định quyền truy cập | Endpoint được phép hoặc bị từ chối |

**Một test tạo `Jwt` bằng builder chỉ kiểm tra bước chuyển đổi.** Nó không kiểm tra chữ ký hoặc issuer vì test đã có sẵn một đối tượng JWT. Để xác minh token thật, cần test decoder/validator hoặc gửi bearer token qua Resource Server có decoder phù hợp.

## 3. JwtAuthenticationConverter mặc định

`JwtAuthenticationConverter` thường dùng hai thiết lập:

- Principal claim mặc định là `sub`.
- Authorities được lấy từ `scope` hoặc `scp` thông qua `JwtGrantedAuthoritiesConverter`; prefix mặc định là `SCOPE_`.

Ví dụ:

~~~java
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

JwtGrantedAuthoritiesConverter authoritiesConverter =
        new JwtGrantedAuthoritiesConverter();

JwtAuthenticationConverter authenticationConverter =
        new JwtAuthenticationConverter();
authenticationConverter.setJwtGrantedAuthoritiesConverter(
        authoritiesConverter);
~~~

Với token:

~~~json
{
  "sub": "user-42",
  "scope": "reports.read reports.export"
}
~~~

Authorities mặc định sẽ tương ứng với:

| Claim | GrantedAuthority |
| --- | --- |
| `reports.read` | `SCOPE_reports.read` |
| `reports.export` | `SCOPE_reports.export` |

Vì vậy, luật truy cập có thể dùng:

~~~java
http.authorizeHttpRequests(authorize -> authorize
        .requestMatchers("/api/reports/**")
            .hasAuthority("SCOPE_reports.read")
        .requestMatchers("/api/exports/**")
            .hasAuthority("SCOPE_reports.export")
        .anyRequest().authenticated());
~~~

Tên authority phải khớp chính xác. `hasAuthority("reports.read")` không tương đương `hasAuthority("SCOPE_reports.read")`. `hasRole("ADMIN")` mặc định kiểm tra `ROLE_ADMIN`, không tự động khớp với `SCOPE_ADMIN`.

### Đổi claim làm principal name

Nếu Identity Provider phát hành `preferred_username`, ứng dụng có thể dùng claim đó làm tên principal:

~~~java
JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
converter.setPrincipalClaimName("preferred_username");
~~~

Khi đó `Authentication.getName()` sẽ lấy giá trị `preferred_username` thay vì `sub`. Cần bảo đảm claim này có mặt trong token và có ý nghĩa ổn định trong ứng dụng. Nếu hệ thống dùng `sub` làm định danh duy nhất để audit hoặc kiểm tra chủ sở hữu, không nên đổi principal name chỉ vì username dễ đọc hơn.

## 4. Kiểm thử JwtGrantedAuthoritiesConverter mặc định

Test trực tiếp với `Jwt.withTokenValue(...)` để kiểm tra scope được chuyển thành authority đúng prefix:

~~~java
import java.util.Collection;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

import static org.assertj.core.api.Assertions.assertThat;

class JwtGrantedAuthoritiesConverterTest {

    private final JwtGrantedAuthoritiesConverter converter =
            new JwtGrantedAuthoritiesConverter();

    @Test
    void mapsSpaceDelimitedScopeClaimToScopeAuthorities() {
        Jwt jwt = Jwt.withTokenValue("test-token")
                .header("alg", "none")
                .subject("user-42")
                .claim("scope", "reports.read reports.export")
                .build();

        Collection<GrantedAuthority> result = converter.convert(jwt);

        assertThat(result)
                .extracting(GrantedAuthority::getAuthority)
                .containsExactlyInAnyOrder(
                        "SCOPE_reports.read",
                        "SCOPE_reports.export");
    }

    @Test
    void supportsScpClaimWhenScopeClaimIsAbsent() {
        Jwt jwt = Jwt.withTokenValue("test-token")
                .header("alg", "none")
                .subject("user-42")
                .claim("scp", java.util.List.of(
                        "reports.read", "reports.export"))
                .build();

        Collection<GrantedAuthority> result = converter.convert(jwt);

        assertThat(result)
                .extracting(GrantedAuthority::getAuthority)
                .containsExactlyInAnyOrder(
                        "SCOPE_reports.read",
                        "SCOPE_reports.export");
    }

    @Test
    void returnsNoAuthoritiesWhenScopeClaimsAreMissing() {
        Jwt jwt = Jwt.withTokenValue("test-token")
                .header("alg", "none")
                .subject("user-42")
                .build();

        assertThat(converter.convert(jwt)).isEmpty();
    }
}
~~~

Các test này kiểm tra hành vi của converter mặc định. Nếu dự án thay đổi claim name hoặc prefix, hãy tạo converter theo đúng cấu hình và điều chỉnh assertion. Không kiểm tra toàn bộ chuỗi JWT vì token test không đại diện cho một token đã ký.

## 5. Converter tùy chỉnh cho claim permissions

Nhiều Identity Provider phát hành quyền nghiệp vụ trong claim riêng thay vì `scope`. Ví dụ:

~~~json
{
  "sub": "user-42",
  "preferred_username": "lan",
  "permissions": [
    "REPORT_READ",
    "REPORT_EXPORT"
  ]
}
~~~

Ta có thể triển khai `Converter<Jwt, Collection<GrantedAuthority>>`:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.List;

import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

final class PermissionsClaimAuthoritiesConverter
        implements Converter<Jwt, Collection<GrantedAuthority>> {

    private static final String CLAIM_NAME = "permissions";
    private static final String AUTHORITY_PREFIX = "PERM_";

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        Object claim = jwt.getClaims().get(CLAIM_NAME);
        if (!(claim instanceof Collection<?> values)) {
            return List.of();
        }

        LinkedHashSet<GrantedAuthority> authorities = new LinkedHashSet<>();
        for (Object value : values) {
            if (value instanceof String permission
                    && !permission.isBlank()) {
                authorities.add(new SimpleGrantedAuthority(
                        AUTHORITY_PREFIX + permission));
            }
        }
        return new ArrayList<>(authorities);
    }
}
~~~

Converter này có hợp đồng rõ:

- Claim không có hoặc không phải collection thì không tạo quyền.
- Chỉ nhận phần tử chuỗi không rỗng.
- Không tự chuyển một object hoặc số thành tên quyền.
- Thêm prefix `PERM_` để phân biệt quyền nghiệp vụ với scope.
- Loại bỏ quyền trùng lặp và giữ thứ tự đầu vào.

Ví dụ:

| Giá trị `permissions` | Kết quả |
| --- | --- |
| `["REPORT_READ", "REPORT_EXPORT"]` | `PERM_REPORT_READ`, `PERM_REPORT_EXPORT` |
| `["REPORT_READ", "", 123]` | Chỉ `PERM_REPORT_READ` |
| Không có claim | Collection rỗng |
| `"REPORT_READ"` (chuỗi đơn thay vì collection) | Collection rỗng |

Nếu schema của Identity Provider quy định claim sai kiểu phải làm xác thực thất bại, có thể ném ngoại lệ thay vì trả collection rỗng. Chọn một chính sách tường minh và kiểm thử nó. Không tự diễn giải dữ liệu sai định dạng thành quyền có đặc quyền cao.

### Kiểm thử converter tùy chỉnh

~~~java
import java.util.Collection;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

import static org.assertj.core.api.Assertions.assertThat;

class PermissionsClaimAuthoritiesConverterTest {

    private final PermissionsClaimAuthoritiesConverter converter =
            new PermissionsClaimAuthoritiesConverter();

    @Test
    void mapsPermissionNamesToApplicationAuthorities() {
        Jwt jwt = Jwt.withTokenValue("test-token")
                .header("alg", "none")
                .subject("user-42")
                .claim("permissions",
                        List.of("REPORT_READ", "REPORT_EXPORT"))
                .build();

        Collection<GrantedAuthority> result = converter.convert(jwt);

        assertThat(result)
                .extracting(GrantedAuthority::getAuthority)
                .containsExactly(
                        "PERM_REPORT_READ",
                        "PERM_REPORT_EXPORT");
    }

    @Test
    void ignoresBlankAndUnexpectedElements() {
        Jwt jwt = Jwt.withTokenValue("test-token")
                .header("alg", "none")
                .subject("user-42")
                .claim("permissions",
                        List.of("REPORT_READ", "", 123, "  "))
                .build();

        assertThat(converter.convert(jwt))
                .extracting(GrantedAuthority::getAuthority)
                .containsExactly("PERM_REPORT_READ");
    }

    @Test
    void removesDuplicatePermissions() {
        Jwt jwt = Jwt.withTokenValue("test-token")
                .header("alg", "none")
                .subject("user-42")
                .claim("permissions",
                        List.of("REPORT_READ", "REPORT_READ"))
                .build();

        assertThat(converter.convert(jwt))
                .extracting(GrantedAuthority::getAuthority)
                .containsExactly("PERM_REPORT_READ");
    }

    @Test
    void returnsEmptyWhenClaimIsMissingOrHasWrongType() {
        Jwt missing = Jwt.withTokenValue("test-token")
                .header("alg", "none")
                .subject("user-42")
                .build();
        Jwt wrongType = Jwt.withTokenValue("test-token")
                .header("alg", "none")
                .subject("user-42")
                .claim("permissions", "REPORT_READ")
                .build();

        assertThat(converter.convert(missing)).isEmpty();
        assertThat(converter.convert(wrongType)).isEmpty();
    }
}
~~~

Các assertion kiểm tra chính xác authorities được tạo ra, không phụ thuộc vào chuỗi token hoặc chữ ký. Trong dự án thực, claim `permissions` phải đến từ token được xác minh bởi decoder tin cậy; converter không tự xác minh nguồn phát hành claim.

## 6. Kết hợp scope mặc định với quyền tùy chỉnh

Một ứng dụng có thể cần cả OAuth2 scopes lẫn permissions nghiệp vụ. Ta có thể ghép hai converter và loại bỏ authority trùng:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.LinkedHashSet;

import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

final class CombinedJwtAuthoritiesConverter
        implements Converter<Jwt, Collection<GrantedAuthority>> {

    private final Converter<Jwt, Collection<GrantedAuthority>> scopes =
            new JwtGrantedAuthoritiesConverter();
    private final Converter<Jwt, Collection<GrantedAuthority>> permissions =
            new PermissionsClaimAuthoritiesConverter();

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        LinkedHashSet<GrantedAuthority> result = new LinkedHashSet<>();
        Collection<GrantedAuthority> scopeAuthorities = scopes.convert(jwt);
        Collection<GrantedAuthority> permissionAuthorities =
                permissions.convert(jwt);

        if (scopeAuthorities != null) {
            result.addAll(scopeAuthorities);
        }
        if (permissionAuthorities != null) {
            result.addAll(permissionAuthorities);
        }
        return new ArrayList<>(result);
    }
}
~~~

Kiểm thử:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;

import static org.assertj.core.api.Assertions.assertThat;

class CombinedJwtAuthoritiesConverterTest {

    @Test
    void combinesScopeAndBusinessPermissions() {
        Jwt jwt = Jwt.withTokenValue("test-token")
                .header("alg", "none")
                .subject("user-42")
                .claim("scope", "reports.read")
                .claim("permissions", java.util.List.of("REPORT_EXPORT"))
                .build();

        var result = new CombinedJwtAuthoritiesConverter().convert(jwt);

        assertThat(result)
                .extracting(authority -> authority.getAuthority())
                .containsExactlyInAnyOrder(
                        "SCOPE_reports.read",
                        "PERM_REPORT_EXPORT");
    }
}
~~~

Tách prefix `SCOPE_` và `PERM_` giúp luật truy cập thể hiện rõ loại quyền cần thiết. Ví dụ endpoint có thể yêu cầu cả scope của API và permission nghiệp vụ qua một manager kết hợp hoặc method security expression. Đừng tự động coi một scope chung là quyền nghiệp vụ quản trị nếu hợp đồng token không quy định như vậy.

## 7. Gắn converter vào JwtAuthenticationConverter

Sau khi có converter quyền, cấu hình `JwtAuthenticationConverter` để tạo token hoàn chỉnh:

~~~java
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;

JwtAuthenticationConverter authenticationConverter =
        new JwtAuthenticationConverter();
authenticationConverter.setPrincipalClaimName("preferred_username");
authenticationConverter.setJwtGrantedAuthoritiesConverter(
        new CombinedJwtAuthoritiesConverter());
~~~

Kiểm thử cả principal và authorities:

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;

import static org.assertj.core.api.Assertions.assertThat;

class JwtAuthenticationConverterComponentTest {

    @Test
    void createsAuthenticationWithExpectedPrincipalAndAuthorities() {
        Jwt jwt = Jwt.withTokenValue("test-token")
                .header("alg", "none")
                .subject("user-42")
                .claim("preferred_username", "lan")
                .claim("scope", "reports.read")
                .claim("permissions", List.of("REPORT_EXPORT"))
                .build();

        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();
        converter.setPrincipalClaimName("preferred_username");
        converter.setJwtGrantedAuthoritiesConverter(
                new CombinedJwtAuthoritiesConverter());

        Authentication result = converter.convert(jwt);

        assertThat(result).isNotNull();
        assertThat(result.getName()).isEqualTo("lan");
        assertThat(result.getAuthorities())
                .extracting(GrantedAuthority::getAuthority)
                .containsExactlyInAnyOrder(
                        "SCOPE_reports.read",
                        "PERM_REPORT_EXPORT");
    }
}
~~~

Đây là test component cốt lõi của bài: nó kiểm tra `Jwt` đầu vào được chuyển thành principal và authorities đúng. Nó chưa kiểm tra việc Resource Server có dùng đúng instance converter hay không; cần thêm test cấu hình/HTTP.

## 8. Gắn converter vào Resource Server Servlet

Trong `SecurityFilterChain`, có thể cung cấp converter cho DSL JWT:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class JwtResourceServerConfiguration {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();
        converter.setPrincipalClaimName("preferred_username");
        converter.setJwtGrantedAuthoritiesConverter(
                new CombinedJwtAuthoritiesConverter());
        return converter;
    }

    @Bean
    SecurityFilterChain resourceServerChain(
            HttpSecurity http,
            JwtAuthenticationConverter jwtAuthenticationConverter)
            throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/reports/**")
                    .hasAuthority("SCOPE_reports.read")
                .requestMatchers("/api/export/**")
                    .hasAuthority("PERM_REPORT_EXPORT")
                .anyRequest().authenticated());

        http.oauth2ResourceServer(resourceServer -> resourceServer
                .jwt(jwt -> jwt
                        .jwtAuthenticationConverter(
                                jwtAuthenticationConverter)));

        return http.build();
    }
}
~~~

Ứng dụng vẫn cần `JwtDecoder` được cấu hình bằng issuer URI, JWK Set URI hoặc khóa phù hợp. Converter chỉ chạy sau khi decoder tạo `Jwt`. Trong test tích hợp, hãy kiểm tra token có scope `reports.read` truy cập endpoint đọc được và token thiếu scope bị từ chối.

### Test jwt() không nhất thiết kiểm tra converter tùy chỉnh

`spring-security-test` cung cấp request postprocessor `jwt()` để tạo `JwtAuthenticationToken` giả lập. Đây là công cụ rất hữu ích để kiểm tra authorization:

~~~java
mockMvc.perform(get("/api/reports/42")
        .with(jwt().authorities(
                new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());
~~~

Tuy nhiên, khi test cung cấp authorities trực tiếp qua `jwt().authorities(...)`, các authorities đã được dựng sẵn. Test không chứng minh `CombinedJwtAuthoritiesConverter` đã đọc claim và tạo ra chúng. Tùy cách dùng postprocessor, `jwt()` có thể tự tạo authentication giả lập thay vì đi qua toàn bộ quá trình decode và converter của Resource Server.

Hãy dùng `jwt()` để kiểm tra rule authorization, và kiểm thử converter trực tiếp như mục 4–7. Nếu cần xác minh converter được gọi trong filter chain, hãy gửi bearer token qua Resource Server với decoder test phù hợp, hoặc dùng một `JwtDecoder` test trả về `Jwt` có claims cần thiết. Khi mock decoder, test xác minh đường tích hợp filter/converter nhưng không xác minh chữ ký JWT.

## 9. Kiểm thử cấu hình qua HTTP với decoder test

Một test tích hợp có thể giữ nguyên `BearerTokenAuthenticationFilter` và `JwtAuthenticationConverter`, trong khi cung cấp decoder test trả về JWT đã biết. Ý tưởng:

1. Cấu hình một `JwtDecoder` test để nhận token test và trả về `Jwt` chứa `sub`, `preferred_username`, `scope`, `permissions`.
2. Gửi request với header `Authorization: Bearer test-token`.
3. Để Resource Server thực hiện chuỗi filter và gọi converter đã cấu hình.
4. Xác minh endpoint được phép hoặc bị từ chối dựa trên authorities tạo ra.

Ví dụ phần test setup với Mockito (cần một bean decoder test trong context):

~~~java
@MockBean
JwtDecoder jwtDecoder;

@BeforeEach
void stubDecoder() {
    Jwt jwt = Jwt.withTokenValue("test-token")
            .header("alg", "none")
            .subject("user-42")
            .claim("preferred_username", "lan")
            .claim("scope", "reports.read")
            .claim("permissions", List.of("REPORT_EXPORT"))
            .build();
    given(jwtDecoder.decode("test-token")).willReturn(jwt);
}

@Test
void bearerRequestUsesConfiguredJwtAuthenticationConverter()
        throws Exception {
    mockMvc.perform(get("/api/export/report")
                    .header("Authorization", "Bearer test-token"))
            .andExpect(status().isOk());
}
~~~

Đoạn này là mẫu minh họa, cần import Mockito BDD (`given`), `JwtDecoder`, `List` và cấu hình mock bean theo phiên bản Spring Boot của dự án. Nếu dùng Spring Boot mới, annotation mock bean có thể đã được thay bằng API test bean tương ứng. Điểm quan trọng là request phải đi qua bearer filter với decoder được stub; khi đó converter trong resource server được gọi. Vì decoder đang mock, test này không chứng minh chữ ký token thật hợp lệ.

## 10. Reactive Resource Server

Trong WebFlux, converter đồng bộ `JwtAuthenticationConverter` có thể được bọc thành converter Reactive bằng `ReactiveJwtAuthenticationConverterAdapter`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverterAdapter;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveJwtResourceServerConfiguration {

    @Bean
    SecurityWebFilterChain reactiveResourceServerChain(
            ServerHttpSecurity http) {
        JwtAuthenticationConverter delegate =
                new JwtAuthenticationConverter();
        delegate.setPrincipalClaimName("preferred_username");
        delegate.setJwtGrantedAuthoritiesConverter(
                new CombinedJwtAuthoritiesConverter());

        var reactiveConverter =
                new ReactiveJwtAuthenticationConverterAdapter(delegate);

        return http.authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/api/reports/**")
                            .hasAuthority("SCOPE_reports.read")
                        .pathMatchers("/api/export/**")
                            .hasAuthority("PERM_REPORT_EXPORT")
                        .anyExchange().authenticated())
                .oauth2ResourceServer(resourceServer -> resourceServer
                        .jwt(jwt -> jwt
                                .jwtAuthenticationConverter(
                                        reactiveConverter)))
                .build();
    }
}
~~~

Adapter đưa kết quả converter đồng bộ vào pipeline Reactive. Ứng dụng vẫn cần decoder Reactive/issuer phù hợp theo cấu hình. Không dùng `SecurityFilterChain` Servlet hoặc `MockMvc` để thay thế kiểm thử `SecurityWebFilterChain`.

Với `WebTestClient`, có thể dùng JWT giả lập để kiểm tra authorization Reactive. Tương tự Servlet, khi authorities được cung cấp trực tiếp, test đó không chứng minh converter tùy chỉnh đã ánh xạ claim. Để kiểm tra mapping, gọi converter trực tiếp hoặc gửi bearer token qua Reactive Resource Server với decoder test phù hợp.

## 11. Những lỗi thường gặp

**Nhầm converter với decoder.** `JwtAuthenticationConverter` không xác minh chữ ký hoặc issuer. Nó chỉ chuyển một `Jwt` đã có thành `Authentication`.

**Dùng claim không đúng schema.** Identity Provider có thể phát hành `scope` dưới dạng chuỗi, `scp` dưới dạng danh sách, hoặc claim quyền riêng. Xác định kiểu dữ liệu thật và kiểm thử trường hợp thiếu/sai kiểu.

**Quên prefix authority.** `JwtGrantedAuthoritiesConverter` mặc định thêm `SCOPE_`. Rule yêu cầu `reports.read` sẽ không khớp với `SCOPE_reports.read`.

**Đổi principal claim nhưng không kiểm tra dữ liệu thiếu.** Nếu cấu hình `preferred_username` mà token không có claim đó, tên principal có thể không đáp ứng yêu cầu audit hoặc business. Hãy kiểm tra token contract và quyết định fallback rõ ràng.

**Gộp role và scope thành cùng một namespace.** Scope API và role/permission nghiệp vụ có ý nghĩa khác nhau. Dùng prefix phân biệt giúp tránh việc một scope vô tình thỏa mãn rule role.

**Chấp nhận mọi chuỗi claim làm quyền.** Converter tùy chỉnh cần kiểm tra kiểu, giá trị rỗng, quyền trùng và tập quyền được hệ thống hỗ trợ. Token đã được ký vẫn cần ánh xạ theo chính sách của ứng dụng.

**Dùng jwt().authorities(...) để kết luận custom converter chạy.** Authorities đã được dựng sẵn trong test postprocessor. Kiểm thử converter riêng hoặc đi qua bearer filter với decoder test.

**Chỉ test converter, không test authorization.** Mapping đúng chưa đảm bảo endpoint dùng đúng authority. Bổ sung test cho endpoint cho phép và endpoint bị từ chối.

**Chỉ test authorization, không test mapping.** `@WithMockUser` hoặc `jwt()` có thể bỏ qua claim mapping. Giữ test component cho converter.

**Nhầm Servlet và Reactive.** WebFlux cần adapter/converter Reactive và `SecurityWebFilterChain`; `MockMvc` chỉ dành cho Servlet.

## 12. Bài thực hành

1. Tạo JWT test có `sub`, `preferred_username` và `scope`. Cấu hình `JwtAuthenticationConverter` dùng `preferred_username`; xác minh `Authentication.getName()`.
2. Viết converter cho claim `permissions` dạng collection. Kiểm thử quyền hợp lệ, claim thiếu, claim sai kiểu, phần tử rỗng và giá trị trùng.
3. Ghép `JwtGrantedAuthoritiesConverter` với converter permission. Xác minh kết quả có cả `SCOPE_...` và `PERM_...` mà không có quyền trùng.
4. Cấu hình Resource Server Servlet dùng converter tùy chỉnh. Viết test component cho mapping và test HTTP cho endpoint được phép/bị từ chối.
5. Viết một test `jwt()` có authorities truyền trực tiếp, rồi giải thích vì sao test đó không chứng minh claim mapping.
6. Cấu hình `ReactiveJwtAuthenticationConverterAdapter` cho WebFlux và kiểm tra cùng chính sách quyền bằng `WebTestClient`.
7. Tách test decoder xác minh chữ ký/issuer/expiration khỏi test converter. Nêu rõ mỗi test cung cấp bằng chứng nào.

Một bộ kiểm thử JWT đầy đủ cần chứng minh **token được xác minh đúng, claim được chuyển thành principal/authorities đúng và authorization sử dụng đúng authorities đó**. Tách ba lớp kiểm tra giúp phát hiện lỗi cấu hình Resource Server mà vẫn giữ test component nhanh, rõ và ổn định.
