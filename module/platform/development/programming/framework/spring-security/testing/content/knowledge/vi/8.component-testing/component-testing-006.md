# Bộ chuyển đổi Authentication hoặc authorities từ dữ liệu đầu vào

## 1. Vì sao cần kiểm thử bộ chuyển đổi?

Một ứng dụng Spring Security có thể nhận dữ liệu xác thực từ nhiều nguồn: header HTTP, form đăng nhập, bearer token JWT hoặc thông tin người dùng do nhà cung cấp OAuth2/OIDC trả về. Trước khi hệ thống kiểm tra danh tính hoặc quyền, dữ liệu đầu vào thường phải được **chuyển đổi sang kiểu mà Spring Security hiểu**.

Ví dụ:

- Header `X-API-Key` có thể được chuyển thành một token `Authentication` chưa xác thực để `AuthenticationManager` xử lý.
- Một JWT đã được giải mã và xác minh có thể được chuyển thành `JwtAuthenticationToken`.
- Claim `scope` hoặc `permissions` có thể được chuyển thành danh sách `GrantedAuthority`.
- Authorities từ người dùng OAuth2/OIDC có thể được chuẩn hóa qua `GrantedAuthoritiesMapper`.

Lỗi chuyển đổi thường khó nhận ra nếu chỉ kiểm thử controller: một claim hợp lệ có thể bị bỏ sót, tên quyền có thể bị thêm sai prefix, hoặc dữ liệu đầu vào không đáng tin cậy có thể bị gán thành quyền cao. Kiểm thử component giúp xác định chính xác dữ liệu nào tạo ra `Authentication` nào và quyền nào.

Bài thuộc chương **Kiểm thử thành phần** của mô-đun **SPRING_SECURITY_TESTING**. Mục tiêu chung của mô-đun là kiểm chứng xác thực, phân quyền và bảo vệ HTTP thực tế bằng `spring-security-test` trên ứng dụng Servlet và Reactive, sử dụng `MockMvc`, `WebTestClient`, `@WithMockUser`, `SecurityContext` và JWT/OAuth2/OIDC giả lập. Bài này tập trung vào các bộ chuyển đổi, đồng thời chỉ ra ranh giới giữa chuyển đổi, xác thực và phân quyền.

Sau bài học, bạn có thể:

- Phân biệt `AuthenticationConverter`, `JwtAuthenticationConverter`, `JwtGrantedAuthoritiesConverter` và `GrantedAuthoritiesMapper`.
- Kiểm thử việc chuyển request HTTP thành `Authentication` chưa xác thực.
- Kiểm tra claim JWT được chuyển thành authorities và principal đúng cách.
- Viết converter tùy chỉnh, kiểm tra dữ liệu thiếu/sai định dạng và tránh cấp quyền từ đầu vào không đáng tin cậy.
- Kiểm thử tương ứng trên Servlet và Reactive, hiểu giới hạn của `jwt()`/`@WithMockUser`.

## 2. Ba ranh giới cần phân biệt

Từ dữ liệu đầu vào đến quyết định cho phép truy cập thường có ba bước:

1. **Chuyển đổi:** diễn giải request, token hoặc claims thành đối tượng `Authentication` và/hoặc `GrantedAuthority`.
2. **Xác thực:** kiểm tra bằng chứng như mật khẩu, API key hoặc chữ ký/claim của token. Kết quả thành công tạo ra `Authentication` đã xác thực.
3. **Phân quyền:** dùng danh tính và authorities đã được tin cậy để quyết định người gọi có được truy cập tài nguyên hay không.

~~~mermaid
flowchart TD
    A["Dữ liệu đầu vào: HTTP header / JWT / OAuth2 attributes"] --> B["Converter"]
    B --> C["Authentication chưa xác thực hoặc authorities đã ánh xạ"]
    C --> D["AuthenticationManager / Provider / Resource Server"]
    D --> E{"Bằng chứng hợp lệ?"}
    E -- "Không" --> F["Authentication failure"]
    E -- "Có" --> G["Authentication đã xác thực"]
    G --> H["AuthorizationManager / access rule"]
    H --> I{"Được phép?"}
    I -- "Có" --> J["Thực thi endpoint"]
    I -- "Không" --> K["Access denied"]
~~~

Không phải mọi converter đều đứng trước `AuthenticationManager` theo cùng một cách. `JwtAuthenticationConverter` thường chạy **sau khi** resource server đã giải mã/xác minh JWT để tạo principal và authorities. Trong khi đó, `AuthenticationConverter` gắn với một filter có thể tạo token chưa xác thực từ request rồi chuyển token cho manager. Cần xác định đúng loại converter trước khi viết test.

| Thành phần | Dữ liệu đầu vào | Kết quả | Có xác thực bằng chứng không? |
| --- | --- | --- | --- |
| `AuthenticationConverter` (Servlet) | `HttpServletRequest` | `Authentication` hoặc `null` | Thông thường không; chỉ trích xuất/diễn giải dữ liệu |
| `ServerAuthenticationConverter` (Reactive) | `ServerWebExchange` | `Mono<Authentication>` | Thông thường không; chỉ trích xuất/diễn giải dữ liệu |
| `JwtGrantedAuthoritiesConverter` | `Jwt` đã được tạo bởi resource server/test | Collection `GrantedAuthority` | Không; ánh xạ claim thành quyền |
| `JwtAuthenticationConverter` | `Jwt` | `AbstractAuthenticationToken` (thường là `JwtAuthenticationToken`) | Không xác minh chữ ký; chuyển claims thành principal/authorities |
| `GrantedAuthoritiesMapper` | Collection `GrantedAuthority` | Collection `GrantedAuthority` đã chuẩn hóa | Không; biến đổi danh sách quyền |

**Nguyên tắc:** converter không nên tự đánh dấu một thông tin xác thực do client gửi đến là đã được tin cậy. Việc xác minh phải do `AuthenticationManager`, provider hoặc resource server đảm nhiệm.

## 3. AuthenticationConverter: chuyển request thành token chưa xác thực

Trong Servlet, `org.springframework.security.web.authentication.AuthenticationConverter` có hợp đồng đơn giản:

~~~java
public interface AuthenticationConverter {
    Authentication convert(HttpServletRequest request);
}
~~~

Một converter có thể đọc header `X-API-Key` rồi tạo token dành cho API key. Nếu request không mang dữ liệu thuộc cơ chế này, converter trả `null` để filter không bắt đầu xác thực theo cách đó.

Ví dụ token API key tối giản:

~~~java
import java.util.List;

import org.springframework.security.authentication.AbstractAuthenticationToken;

final class ApiKeyAuthenticationToken extends AbstractAuthenticationToken {

    private final String apiKey;

    ApiKeyAuthenticationToken(String apiKey) {
        super(List.of());
        this.apiKey = apiKey;
    }

    @Override
    public Object getCredentials() {
        return this.apiKey;
    }

    @Override
    public Object getPrincipal() {
        return null;
    }
}
~~~

Token này giữ API key ở vị trí credentials và chưa được xác thực. Sau đó một `AuthenticationProvider` chuyên biệt phải kiểm tra key với nguồn dữ liệu tin cậy, rồi trả token thành công có principal và authorities thích hợp. Converter không được gán `ROLE_ADMIN` chỉ vì request gửi kèm một header tự khai báo role.

Converter cho Servlet:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.core.Authentication;
import org.springframework.security.web.authentication.AuthenticationConverter;

final class ApiKeyAuthenticationConverter implements AuthenticationConverter {

    @Override
    public Authentication convert(HttpServletRequest request) {
        String apiKey = request.getHeader("X-API-Key");
        if (apiKey == null || apiKey.isBlank()) {
            return null;
        }
        return new ApiKeyAuthenticationToken(apiKey);
    }
}
~~~

Đây là ví dụ trích xuất đầu vào. Ứng dụng thực cần quyết định chính sách đối với header lặp, khoảng trắng, kích thước key, encoding và nguồn gửi; không ghi API key vào log.

### Kiểm thử converter trực tiếp

`MockHttpServletRequest` cho phép kiểm tra converter mà không cần khởi động server:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.core.Authentication;

import static org.assertj.core.api.Assertions.assertThat;

class ApiKeyAuthenticationConverterTest {

    private final ApiKeyAuthenticationConverter converter =
            new ApiKeyAuthenticationConverter();

    @Test
    void convertsApiKeyHeaderIntoUnauthenticatedToken() {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("X-API-Key", "test-key-only");

        Authentication result = converter.convert(request);

        assertThat(result).isInstanceOf(ApiKeyAuthenticationToken.class);
        assertThat(result.isAuthenticated()).isFalse();
        assertThat(result.getCredentials()).isEqualTo("test-key-only");
    }

    @Test
    void returnsNullWhenApiKeyHeaderIsMissing() {
        MockHttpServletRequest request = new MockHttpServletRequest();

        assertThat(converter.convert(request)).isNull();
    }

    @Test
    void returnsNullWhenApiKeyHeaderIsBlank() {
        MockHttpServletRequest request = new MockHttpServletRequest();
        request.addHeader("X-API-Key", "   ");

        assertThat(converter.convert(request)).isNull();
    }
}
~~~

Ba ca trên kiểm tra ba điều: dữ liệu hợp lệ được chuyển thành đúng kiểu token; token vẫn chưa xác thực; và request không có dữ liệu phù hợp không tạo token. Chúng chưa kiểm tra API key có hợp lệ hay không. Phần đó cần test provider hoặc test HTTP đi qua filter.

### Kết hợp converter với AuthenticationFilter

Trong ứng dụng Servlet, `AuthenticationFilter` có thể dùng một `AuthenticationConverter` cùng `AuthenticationManager`. Cấu hình minh họa:

~~~java
AuthenticationFilter apiKeyFilter =
        new AuthenticationFilter(authenticationManager, apiKeyConverter);

http.addFilterBefore(apiKeyFilter, UsernamePasswordAuthenticationFilter.class);
~~~

Đoạn trên giả định `authenticationManager` và `apiKeyConverter` đã được tạo và filter được cấu hình success/failure handler, security context repository, matcher phù hợp. Một ứng dụng có nhiều filter xác thực phải xác định rõ filter nào xử lý request nào. Khi kiểm thử tích hợp, cần kiểm tra cả request không có API key để chắc rằng các cơ chế đăng nhập khác vẫn hoạt động như thiết kế.

## 4. JWT và việc chuyển claims thành authorities

Trong OAuth2 Resource Server, JWT được decoder xử lý trước khi converter ánh xạ principal và authorities. Hai lớp thường gặp:

- `JwtGrantedAuthoritiesConverter`: chuyển claim scope/scp thành `GrantedAuthority`. Mặc định, các scope được chuyển thành quyền có prefix `SCOPE_`.
- `JwtAuthenticationConverter`: tạo `JwtAuthenticationToken`, sử dụng converter authorities và chọn claim làm tên principal. Mặc định tên principal thường lấy từ claim `sub`.

Ví dụ token đã được tạo trong test:

~~~java
import java.time.Instant;
import org.springframework.security.oauth2.jwt.Jwt;

Jwt jwt = Jwt.withTokenValue("fake-token-for-test")
        .header("alg", "none")
        .subject("lan")
        .claim("scope", "reports.read reports.write")
        .issuedAt(Instant.now())
        .expiresAt(Instant.now().plusSeconds(300))
        .build();
~~~

`Jwt` trong test là một đối tượng Java đã có claims; tạo nó bằng builder **không xác minh chữ ký JWT**. Nó phù hợp để kiểm tra logic chuyển đổi. Việc xác minh token thật cần kiểm thử `JwtDecoder`/validator hoặc resource server được cấu hình với cơ chế xác minh thật.

### Kiểm thử JwtGrantedAuthoritiesConverter mặc định

~~~java
import java.util.Collection;
import java.util.List;
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
                .subject("lan")
                .claim("scope", "reports.read reports.write")
                .build();

        Collection<GrantedAuthority> result = converter.convert(jwt);

        assertThat(result)
                .extracting(GrantedAuthority::getAuthority)
                .containsExactlyInAnyOrder(
                        "SCOPE_reports.read",
                        "SCOPE_reports.write");
    }

    @Test
    void supportsScpClaimWhenScopeClaimIsAbsent() {
        Jwt jwt = Jwt.withTokenValue("test-token")
                .header("alg", "none")
                .subject("lan")
                .claim("scp", List.of("reports.read", "reports.write"))
                .build();

        Collection<GrantedAuthority> result = converter.convert(jwt);

        assertThat(result)
                .extracting(GrantedAuthority::getAuthority)
                .containsExactlyInAnyOrder(
                        "SCOPE_reports.read",
                        "SCOPE_reports.write");
    }

    @Test
    void returnsNoAuthoritiesWhenScopeClaimsAreAbsent() {
        Jwt jwt = Jwt.withTokenValue("test-token")
                .header("alg", "none")
                .subject("lan")
                .build();

        assertThat(converter.convert(jwt)).isEmpty();
    }
}
~~~

`JwtGrantedAuthoritiesConverter` nhận các dạng claim scope phổ biến: `scope` dạng chuỗi phân tách bằng khoảng trắng hoặc `scp` dạng collection. Nếu ứng dụng dùng tên claim khác, prefix khác hoặc định dạng khác, phải cấu hình converter và viết test theo hợp đồng dữ liệu thực tế.

### Ánh xạ claim tùy chỉnh

Nhiều hệ thống phát hành claim riêng như:

~~~json
{
  "sub": "lan",
  "permissions": ["REPORT_READ", "REPORT_EXPORT"]
}
~~~

Không nên giả định `permissions` tự động được Spring Security hiểu giống `scope`. Có thể tạo converter riêng:

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;

import org.springframework.core.convert.converter.Converter;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

final class PermissionsClaimConverter
        implements Converter<Jwt, Collection<GrantedAuthority>> {

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        Object raw = jwt.getClaims().get("permissions");
        if (!(raw instanceof Collection<?> values)) {
            return List.of();
        }

        List<GrantedAuthority> authorities = new ArrayList<>();
        for (Object value : values) {
            if (value instanceof String permission
                    && !permission.isBlank()) {
                authorities.add(
                        new SimpleGrantedAuthority("PERM_" + permission));
            }
        }
        return authorities;
    }
}
~~~

Converter này chỉ chấp nhận collection chuỗi và bỏ qua phần tử sai kiểu hoặc rỗng. Quy tắc prefix `PERM_` là lựa chọn minh họa của ứng dụng; nếu `AuthorizationManager` yêu cầu `REPORT_READ` thì converter phải ánh xạ đúng tên đó, không tự thêm prefix không tương thích.

Kiểm thử:

~~~java
import java.util.Collection;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;

import static org.assertj.core.api.Assertions.assertThat;

class PermissionsClaimConverterTest {

    private final PermissionsClaimConverter converter =
            new PermissionsClaimConverter();

    @Test
    void mapsKnownPermissionStringsToAuthorities() {
        Jwt jwt = Jwt.withTokenValue("test-token")
                .header("alg", "none")
                .subject("lan")
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
    void ignoresUnexpectedTypesAndBlankValues() {
        Jwt jwt = Jwt.withTokenValue("test-token")
                .header("alg", "none")
                .subject("lan")
                .claim("permissions",
                        List.of("REPORT_READ", "", 123))
                .build();

        Collection<GrantedAuthority> result = converter.convert(jwt);

        assertThat(result)
                .extracting(GrantedAuthority::getAuthority)
                .containsExactly("PERM_REPORT_READ");
    }

    @Test
    void returnsEmptyCollectionWhenClaimIsMissingOrWrongType() {
        Jwt missing = Jwt.withTokenValue("test-token")
                .header("alg", "none")
                .subject("lan")
                .build();
        Jwt wrongType = Jwt.withTokenValue("test-token")
                .header("alg", "none")
                .subject("lan")
                .claim("permissions", "REPORT_READ")
                .build();

        assertThat(converter.convert(missing)).isEmpty();
        assertThat(converter.convert(wrongType)).isEmpty();
    }
}
~~~

Test trên thể hiện chính sách rõ ràng: claim không đúng kiểu không được tự diễn giải thành quyền. Nếu dữ liệu sai định dạng phải làm xác thực thất bại thay vì trả collection rỗng, hãy thay đổi converter để ném ngoại lệ phù hợp và bổ sung test cho hành vi đó.

### Ghép converter authorities vào JwtAuthenticationConverter

Để converter JWT tạo principal và token hoàn chỉnh:

~~~java
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;

JwtAuthenticationConverter authenticationConverter =
        new JwtAuthenticationConverter();
authenticationConverter.setJwtGrantedAuthoritiesConverter(
        new PermissionsClaimConverter());
authenticationConverter.setPrincipalClaimName("sub");

Authentication authentication = authenticationConverter.convert(jwt);
~~~

Test cần xác minh cả tên principal và authorities:

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
    void createsJwtAuthenticationWithMappedPermissions() {
        Jwt jwt = Jwt.withTokenValue("test-token")
                .header("alg", "none")
                .subject("lan")
                .claim("permissions", List.of("REPORT_READ"))
                .build();

        JwtAuthenticationConverter converter =
                new JwtAuthenticationConverter();
        converter.setJwtGrantedAuthoritiesConverter(
                new PermissionsClaimConverter());

        Authentication result = converter.convert(jwt);

        assertThat(result).isNotNull();
        assertThat(result.getName()).isEqualTo("lan");
        assertThat(result.getAuthorities())
                .extracting(GrantedAuthority::getAuthority)
                .containsExactly("PERM_REPORT_READ");
    }
}
~~~

`JwtAuthenticationConverter` chỉ chuyển một `Jwt` có sẵn thành token xác thực ở tầng resource server. Không dùng test này để kết luận JWT được ký bởi issuer tin cậy hoặc chưa hết hạn; các kiểm tra đó diễn ra ở decoder/validator trước bước chuyển đổi.

## 5. GrantedAuthoritiesMapper cho OAuth2/OIDC

Khi đăng nhập qua OAuth2/OIDC, Spring Security có thể nhận authorities từ các đối tượng `OAuth2User` hoặc `OidcUser`. `GrantedAuthoritiesMapper` cho phép chuẩn hóa collection authorities, chẳng hạn thêm role nội bộ hoặc loại bỏ authority không phù hợp với chính sách ứng dụng.

Hợp đồng:

~~~java
public interface GrantedAuthoritiesMapper {
    Collection<? extends GrantedAuthority> mapAuthorities(
            Collection<? extends GrantedAuthority> authorities);
}
~~~

Ví dụ mapper chỉ giữ các quyền nội bộ đã được cho phép:

~~~java
import java.util.Collection;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.authority.mapping.GrantedAuthoritiesMapper;

final class ExternalAuthoritiesMapper implements GrantedAuthoritiesMapper {

    private static final Set<String> ALLOWED = Set.of(
            "REPORT_READ", "REPORT_EXPORT");

    @Override
    public Collection<? extends GrantedAuthority> mapAuthorities(
            Collection<? extends GrantedAuthority> authorities) {
        return authorities.stream()
                .map(GrantedAuthority::getAuthority)
                .filter(ALLOWED::contains)
                .map(name -> new SimpleGrantedAuthority("PERM_" + name))
                .collect(Collectors.toSet());
    }
}
~~~

Ở đây mapper chỉ chấp nhận hai quyền đã cho phép. Trong thực tế, không nên tin tất cả authority do provider bên ngoài gửi đến: cần xác định rõ claim/attribute nào được tin cậy, quyền nào được ánh xạ và quyền nào bị loại bỏ.

Test:

~~~java
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;

import static org.assertj.core.api.Assertions.assertThat;

class ExternalAuthoritiesMapperTest {

    private final ExternalAuthoritiesMapper mapper =
            new ExternalAuthoritiesMapper();

    @Test
    void mapsOnlyAuthoritiesWhitelistedByApplication() {
        var input = List.of(
                new SimpleGrantedAuthority("REPORT_READ"),
                new SimpleGrantedAuthority("REPORT_EXPORT"),
                new SimpleGrantedAuthority("ROLE_ADMIN"),
                new SimpleGrantedAuthority("UNKNOWN"));

        var result = mapper.mapAuthorities(input);

        assertThat(result)
                .extracting(GrantedAuthority::getAuthority)
                .containsExactlyInAnyOrder(
                        "PERM_REPORT_READ",
                        "PERM_REPORT_EXPORT");
    }

    @Test
    void emptyInputProducesNoAuthorities() {
        assertThat(mapper.mapAuthorities(List.of())).isEmpty();
    }
}
~~~

Mapper có thể được đăng ký với cấu hình OAuth2 Login/OIDC qua thuộc tính `userAuthoritiesMapper(...)` của cấu hình đăng nhập tương ứng. Kiểm thử mapper trực tiếp chứng minh quy tắc biến đổi; test tích hợp OAuth2/OIDC vẫn cần xác nhận đúng mapper được cấu hình và đúng authorities đến được `SecurityContext`.

## 6. Kiểm thử chuyển đổi trong ứng dụng Reactive

Trong WebFlux, converter nhận `ServerWebExchange` và trả `Mono<Authentication>` thông qua `ServerAuthenticationConverter`. Ví dụ API key tương tự Servlet:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.web.server.authentication.ServerAuthenticationConverter;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

final class ReactiveApiKeyAuthenticationConverter
        implements ServerAuthenticationConverter {

    @Override
    public Mono<Authentication> convert(ServerWebExchange exchange) {
        String apiKey = exchange.getRequest()
                .getHeaders()
                .getFirst("X-API-Key");

        if (apiKey == null || apiKey.isBlank()) {
            return Mono.empty();
        }
        return Mono.just(new ApiKeyAuthenticationToken(apiKey));
    }
}
~~~

Converter Reactive dùng lại token chưa xác thực ở mục 3. Có thể kiểm tra nó bằng `MockServerWebExchange` và `StepVerifier`:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.mock.http.server.reactive.MockServerHttpRequest;
import org.springframework.mock.web.server.MockServerWebExchange;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class ReactiveApiKeyAuthenticationConverterTest {

    private final ReactiveApiKeyAuthenticationConverter converter =
            new ReactiveApiKeyAuthenticationConverter();

    @Test
    void convertsHeaderToUnauthenticatedToken() {
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/")
                        .header("X-API-Key", "test-key-only")
                        .build());

        StepVerifier.create(converter.convert(exchange))
                .assertNext(authentication -> {
                    assertThat(authentication)
                            .isInstanceOf(ApiKeyAuthenticationToken.class);
                    assertThat(authentication.isAuthenticated()).isFalse();
                    assertThat(authentication.getCredentials())
                            .isEqualTo("test-key-only");
                })
                .verifyComplete();
    }

    @Test
    void emitsEmptyWhenHeaderIsMissing() {
        var exchange = MockServerWebExchange.from(
                MockServerHttpRequest.get("/").build());

        StepVerifier.create(converter.convert(exchange))
                .verifyComplete();
    }
}
~~~

`MockServerWebExchange`, `MockServerHttpRequest` và `StepVerifier` đến từ các dependency test của Spring WebFlux/Reactor. Bài test này kiểm tra việc trích xuất header và tạo token. Để kiểm tra xác thực thật, phải nối converter vào `AuthenticationWebFilter`/`ReactiveAuthenticationManager` và dùng `WebTestClient` gắn với chuỗi filter của ứng dụng.

Với JWT Reactive, việc chuyển `Jwt` thành authorities có thể dùng converter đồng bộ được bọc sang dạng Reactive hoặc một converter Reactive phù hợp với phiên bản Spring Security. Hợp đồng cần giữ nguyên: mapping claim phải cho kết quả giống chính sách ứng dụng; không bỏ qua xác minh chữ ký/issuer/audience của resource server.

## 7. Kiểm thử HTTP và giới hạn của các tiện ích giả lập

### Servlet với MockMvc

Khi cấu hình converter vào `AuthenticationFilter` hoặc resource server, `MockMvc` có thể kiểm chứng request đi qua toàn bộ filter chain. Ví dụ nếu API key filter đã được đăng ký và API key hợp lệ được provider xác minh, một request có header có thể nhận `200`; key sai hoặc thiếu có thể bị từ chối theo entry point/handler của ứng dụng.

~~~java
mockMvc.perform(get("/api/private/report")
                .header("X-API-Key", "test-key-only"))
        .andExpect(status().isOk());

mockMvc.perform(get("/api/private/report")
                .header("X-API-Key", "invalid-test-key"))
        .andExpect(status().isUnauthorized());
~~~

Đây là phần thân minh họa của test cần có `MockMvc`, endpoint, filter, manager và provider tương ứng. Nếu converter trả `null` khi thiếu header, request có thể tiếp tục qua cơ chế xác thực khác hoặc bị từ chối; kết quả phụ thuộc `SecurityFilterChain`.

### JWT giả lập không kiểm tra converter mặc định

`spring-security-test` có `jwt()` cho MockMvc và tiện ích tương ứng cho WebTestClient. Các tiện ích này tạo sẵn `JwtAuthenticationToken`/ngữ cảnh đã xác thực để kiểm tra rule phân quyền. Nếu cần chứng minh `JwtGrantedAuthoritiesConverter` tùy chỉnh đang được gọi, hãy:

- Kiểm thử converter trực tiếp như mục 4; và/hoặc
- Cấu hình resource server dùng converter tùy chỉnh, gửi request qua filter chain và kiểm tra quyền được ánh xạ.

Không kết luận converter hoạt động chỉ vì test `jwt().authorities(...)` được phép: test có thể đã cung cấp authorities trực tiếp mà không chạy bước chuyển claim.

### OAuth2/OIDC giả lập

`oauth2Login()` và `oidcLogin()` hỗ trợ tạo principal/authorities cho kiểm thử ứng dụng sau đăng nhập. Nếu ứng dụng có `GrantedAuthoritiesMapper`, cần có test mapper trực tiếp và một test tích hợp xác nhận mapper được áp dụng. Các tiện ích giả lập không xác minh redirect, callback, chữ ký ID token hoặc giao tiếp với Identity Provider thực.

## 8. Các lỗi thường gặp khi viết converter

**Đánh dấu token là authenticated trong converter.** Dữ liệu đến từ request vẫn chưa được tin cậy. Converter chỉ trích xuất thông tin và tạo token chưa xác thực; provider hoặc manager mới kiểm tra credentials rồi tạo kết quả thành công.

**Gán authorities từ header client tự khai báo.** Một header như `X-Role: ADMIN` không phải bằng chứng quyền. Authorities cần đến từ dữ liệu đã xác minh, chẳng hạn bản ghi tài khoản tin cậy hoặc claims của JWT đã được decoder xác minh.

**Nhầm JwtAuthenticationConverter với JwtDecoder.** Converter ánh xạ một `Jwt` đã có; decoder xác minh và tạo JWT từ token. Test builder tạo `Jwt` không chứng minh chữ ký, issuer, audience hoặc thời hạn được xác minh.

**Dùng sai claim hoặc prefix.** `scope: "reports.read"` thường thành `SCOPE_reports.read`. Nếu access rule dùng `hasAuthority("reports.read")`, nó không khớp. Hãy kiểm tra giá trị authority cuối cùng bằng assertion cụ thể.

**Giả định mọi claim đều là chuỗi.** Claim có thể thiếu, sai kiểu hoặc chứa phần tử không hợp lệ. Converter cần định nghĩa chính sách rõ: bỏ qua, trả danh sách rỗng hay báo lỗi; test phải bao phủ từng nhánh.

**Bỏ qua dữ liệu trùng lặp.** Một claim có thể chứa cùng permission nhiều lần. Nếu kết quả dùng collection, hãy quyết định có khử trùng lặp không và viết test theo hợp đồng đó.

**Làm rơi principal name.** Một converter có thể ánh xạ đúng quyền nhưng chọn sai claim làm `Authentication.getName()`. Điều này ảnh hưởng audit, kiểm tra chủ sở hữu và log nghiệp vụ. Test cả principal và authorities.

**Dùng tiện ích mock để kết luận converter chạy.** `@WithMockUser`, `jwt()` hoặc `oauth2Login()` có thể tạo sẵn danh tính/quyền. Chúng phù hợp để kiểm tra authorization; muốn kiểm tra conversion phải gọi converter hoặc chạy đúng luồng filter.

**Không phân biệt Servlet và Reactive.** `AuthenticationConverter` trả `Authentication`; `ServerAuthenticationConverter` trả `Mono<Authentication>`. Test Reactive phải kiểm tra cả giá trị phát ra và completion/error của publisher.

**Để credentials lộ trong kết quả hoặc log.** Token đầu vào chỉ nên tồn tại ở nơi cần thiết để xác thực. Không in API key/bearer token, không đưa chúng vào assertion message hoặc log chẩn đoán.

## 9. Bài thực hành

1. Viết một `AuthenticationConverter` đọc header `X-Client-Token`, trả `null` nếu thiếu và tạo token chưa xác thực nếu có. Kiểm tra token không có authority trước khi provider xác minh.
2. Viết provider kiểm tra API key giả lập từ một map tin cậy. Test key hợp lệ trả principal và authority; key sai bị từ chối. Ghép converter với provider để kiểm tra toàn luồng.
3. Thay claim `scope` bằng claim `permissions` dạng collection. Dùng `PermissionsClaimConverter` để tạo authority và kiểm tra claim thiếu, sai kiểu, chuỗi rỗng, quyền trùng.
4. Cấu hình `JwtAuthenticationConverter` dùng claim `preferred_username` làm principal. Test rằng `Authentication.getName()` là username mong đợi và authorities khớp.
5. Thêm `GrantedAuthoritiesMapper` cho OAuth2/OIDC, chỉ giữ các quyền nội bộ được phép. Kiểm tra authority ngoài danh sách không thể tự biến thành role quản trị.
6. Chạy một test `jwt()` để xác minh endpoint phân quyền và so sánh với test resource server thật có converter tùy chỉnh. Giải thích vì sao hai test cung cấp bằng chứng khác nhau.
7. Viết test `ServerAuthenticationConverter` cho WebFlux với header có/không có, sau đó dùng `WebTestClient` xác nhận request qua filter chain.

Một bộ kiểm thử converter tốt xác minh **đầu vào nào được chấp nhận, đối tượng Authentication/authorities nào được tạo ra và dữ liệu nào vẫn chưa được tin cậy**. Khi kết hợp test component với test filter/HTTP, bạn có thể phát hiện cả lỗi ánh xạ quyền lẫn lỗi tích hợp trước khi chúng làm sai quyết định truy cập.
