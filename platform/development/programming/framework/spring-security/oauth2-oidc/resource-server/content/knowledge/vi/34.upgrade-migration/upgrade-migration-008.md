# Tùy chỉnh principal, authority converter và hành vi phân quyền khi nâng cấp

## 1. Vì sao nâng cấp Resource Server dễ làm thay đổi quyền truy cập?

Khi nâng cấp Spring Security, một Resource Server có thể vẫn khởi động và xác minh được chữ ký JWT nhưng hành vi của ứng dụng đã thay đổi. Controller có thể nhận principal khác kiểu trước đây, Authentication có tên khác, authority bị đổi prefix, hoặc rule phân quyền không còn khớp với các authority được tạo từ token.

Những thay đổi này thường xuất hiện ở ba điểm liên quan chặt chẽ:

- **Principal mapping:** xác định danh tính mà ứng dụng nhìn thấy qua Authentication, ví dụ subject, username hoặc một principal domain riêng.
- **Authority conversion:** chuyển scope, role, group và claim tùy chỉnh thành GrantedAuthority.
- **Authorization behavior:** dùng authority đó trong request matcher, method security, role hierarchy và policy kiểm tra tài nguyên.

Ví dụ, Resource Server mặc định có thể biến scope orders.read thành authority SCOPE_orders.read. Nếu code cũ kiểm tra hasRole("orders.read"), request sẽ bị từ chối vì hasRole tìm ROLE_orders.read. Token vẫn hợp lệ; lỗi nằm ở hợp đồng giữa converter và authorization rule.

Tương tự, nếu code cũ cast Authentication.getPrincipal() thành UserDetails nhưng phiên bản mới dùng JwtAuthenticationToken, lỗi có thể chỉ xuất hiện khi controller hoặc service truy cập principal.

Khi nâng cấp, cần xem principal và authority như một hợp đồng ứng dụng. Hợp đồng này bao gồm tên principal, kiểu object principal, tập authority, prefix, cách đọc claim, thứ tự authorization rule và hành vi 401/403.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Hiểu principal, Authentication và GrantedAuthority trong Resource Server.
2. Nắm hành vi mặc định của JwtAuthenticationConverter và JwtGrantedAuthoritiesConverter.
3. Tùy chỉnh principal name từ claim phù hợp.
4. Kết hợp scope và role trong một authority converter.
5. Tạo principal domain riêng khi ứng dụng thực sự cần.
6. Chuyển converter đồng bộ sang reactive converter cho WebFlux.
7. Phân biệt scope authority với role authority.
8. Bảo toàn hành vi request authorization và method security khi nâng cấp.
9. Kiểm thử các thay đổi bằng unit test và MockMvc/WebTestClient.
10. Lập kế hoạch migration có thể rollback mà không mở rộng quyền ngoài ý muốn.

---

## 2. Các khái niệm cần thống nhất trước khi sửa converter

### 2.1. Authentication chứa những gì?

Sau khi Resource Server xác thực access token, Spring Security tạo một đối tượng Authentication. Với JWT Resource Server, lớp thường gặp là JwtAuthenticationToken.

Một Authentication đã xác thực thường cung cấp:

| Thuộc tính | Ý nghĩa |
|---|---|
| getPrincipal() | Đối tượng đại diện cho principal |
| getName() | Tên định danh principal mà Spring Security sử dụng |
| getAuthorities() | Các GrantedAuthority được phép dùng trong authorization |
| getCredentials() | Thông tin credential gắn với Authentication |
| isAuthenticated() | Trạng thái Authentication |

Đừng giả định getPrincipal() và getName() trả cùng một kiểu dữ liệu. Với JwtAuthenticationToken, principal là đối tượng Jwt; getName() là chuỗi định danh được chọn từ claim principal.

Ví dụ:

~~~java
Authentication authentication = ...;

String name = authentication.getName();

Object principal = authentication.getPrincipal();

Collection<? extends GrantedAuthority> authorities =
    authentication.getAuthorities();
~~~

Nếu code cũ dùng getPrincipal() để lấy username hoặc cast sang UserDetails, hãy kiểm tra lại contract. Với JWT Resource Server, cách phổ biến là inject Jwt qua @AuthenticationPrincipal hoặc đọc Authentication.getName().

### 2.2. Principal không đồng nghĩa với user profile

Principal biểu diễn danh tính trong security context. Nó không nhất thiết là toàn bộ hồ sơ người dùng.

Ví dụ JWT:

~~~json
{
  "iss": "https://id.example.com/realms/shop",
  "sub": "user-417",
  "preferred_username": "phuong",
  "email": "user@example.test",
  "tenant_id": "tenant-a",
  "scope": "orders.read"
}
~~~

Các claim có ý nghĩa khác nhau:

- sub thường là định danh ổn định trong phạm vi issuer.
- preferred_username có thể thay đổi theo thời gian.
- email có thể được cập nhật hoặc tái cấp cho người khác.
- tenant_id chỉ có ý nghĩa nếu Authorization Server phát hành claim này theo hợp đồng tin cậy.
- scope biểu diễn quyền truy cập được cấp cho token.

Đối với audit, ownership và cache key, ưu tiên định danh ổn định. Trong hệ thống nhiều issuer, subject có thể chỉ duy nhất trong phạm vi issuer; định danh nội bộ nên tính đến cả issuer và subject nếu cần phân biệt hai namespace.

### 2.3. GrantedAuthority là chuỗi quyền đã chuẩn hóa

GrantedAuthority biểu diễn quyền mà authorization layer có thể kiểm tra:

~~~java
new SimpleGrantedAuthority("SCOPE_orders.read");
new SimpleGrantedAuthority("ROLE_ORDER_ADMIN");
~~~

Authority không tự động có ý nghĩa chỉ vì tên claim trong JWT giống tên role. Converter quyết định claim nào được ánh xạ và prefix nào được thêm.

Nên thống nhất quy ước:

- Scope: SCOPE_orders.read, SCOPE_orders.write.
- Role: ROLE_ORDER_READER, ROLE_ORDER_ADMIN.
- Permission tùy chỉnh: PERM_orders:approve nếu tổ chức chọn convention đó.

Không dùng lẫn ROLE_ và SCOPE_ cho cùng một loại quyền. Quy ước nhất quán giúp authorization rule dễ đọc và dễ kiểm thử.

---

## 3. Hành vi mặc định của JWT converter

### 3.1. JwtAuthenticationConverter

Trong Servlet Resource Server, JwtAuthenticationConverter chuyển Jwt đã được xác minh thành AbstractAuthenticationToken. Mặc định nó tạo JwtAuthenticationToken.

Hai phần chính có thể tùy chỉnh:

- Principal name claim thông qua setPrincipalClaimName(...).
- Authority converter thông qua setJwtGrantedAuthoritiesConverter(...).

Ví dụ cấu hình tối giản:

~~~java
JwtAuthenticationConverter converter =
    new JwtAuthenticationConverter();

converter.setPrincipalClaimName("sub");

converter.setJwtGrantedAuthoritiesConverter(
    new JwtGrantedAuthoritiesConverter()
);
~~~

sub là principal claim mặc định trong cấu hình phổ biến. Nếu đổi sang preferred_username, Authentication.getName() sẽ phản ánh claim đó khi claim có giá trị. Kiểu object từ getPrincipal() vẫn là Jwt.

### 3.2. JwtGrantedAuthoritiesConverter

JwtGrantedAuthoritiesConverter là converter mặc định cho authority từ JWT. Nó đọc scope hoặc scp theo convention được hỗ trợ và tạo authority với prefix mặc định SCOPE_.

Ví dụ:

~~~json
{
  "sub": "user-417",
  "scope": "orders.read orders.write"
}
~~~

Các authority được tạo:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Một số Authorization Server dùng claim scp thay cho scope hoặc biểu diễn scopes dưới dạng danh sách. Hãy xác nhận schema token thật của hệ thống và kiểm thử đúng kiểu dữ liệu. Không suy luận rằng mọi issuer đều phát hành cùng một claim format.

### 3.3. Prefix là một phần của hợp đồng

Giả sử converter tạo SCOPE_orders.read. Các rule sau không tương đương:

~~~java
.hasAuthority("SCOPE_orders.read")
.hasRole("orders.read")
.hasAuthority("ROLE_orders.read")
~~~

hasAuthority so sánh chính xác chuỗi authority.

hasRole("ORDER_ADMIN") là shortcut cho role check với prefix ROLE_ mặc định, tức tìm ROLE_ORDER_ADMIN. Không truyền prefix vào tham số nếu framework đã tự thêm prefix.

Ví dụ:

~~~java
.requestMatchers("/api/orders/**")
    .hasAuthority("SCOPE_orders.read")

.requestMatchers("/api/admin/**")
    .hasRole("ORDER_ADMIN")
~~~

Khi nâng cấp, hãy so sánh authority thực tế với chuỗi mà rule đang kiểm tra. Không chỉ nhìn claim gốc trong JWT.

### 3.4. Đổi claim name không đồng nghĩa kết hợp nhiều claim

Có thể cấu hình JwtGrantedAuthoritiesConverter đọc một claim tùy chỉnh:

~~~java
JwtGrantedAuthoritiesConverter converter =
    new JwtGrantedAuthoritiesConverter();

converter.setAuthoritiesClaimName("permissions");
converter.setAuthorityPrefix("PERM_");
~~~

Cấu hình trên yêu cầu converter đọc claim permissions và tạo authority với prefix PERM_. Nó không tự động kết hợp scope mặc định với roles hoặc permissions.

Nếu cần cả scope và role, hãy viết converter kết hợp rõ ràng. Nếu chỉ đổi authoritiesClaimName sang roles, scope có thể không còn được đưa vào Authentication.

### 3.5. Default converter không tự biến mọi claim thành role

Một token có claim:

~~~json
{
  "roles": ["ORDER_ADMIN"],
  "groups": ["finance"],
  "permissions": ["orders:approve"]
}
~~~

không có nghĩa mọi giá trị trên tự trở thành GrantedAuthority. Ứng dụng phải định nghĩa mapping cụ thể.

Đây là điểm cần chú ý khi nâng cấp từ một hệ thống từng có custom converter sang cấu hình Resource Server mặc định. Nếu bỏ custom converter trong lúc migration, authority có thể biến mất dù token vẫn giữ nguyên claim.

---

## 4. Tùy chỉnh principal name

### 4.1. Chọn claim định danh phù hợp

Có thể chọn preferred_username làm Authentication name:

~~~java
JwtAuthenticationConverter converter =
    new JwtAuthenticationConverter();

converter.setPrincipalClaimName("preferred_username");
~~~

Khi token có preferred_username, lời gọi authentication.getName() sử dụng giá trị claim đó. Tuy nhiên, username có thể thay đổi và có thể được tái sử dụng. Đối với định danh lưu trữ, audit hoặc ownership, sub thường phù hợp hơn.

Một lựa chọn phổ biến:

- Dùng sub làm định danh ổn định.
- Dùng preferred_username để hiển thị.
- Dùng email cho mục đích liên lạc khi claim được phát hành và xác minh theo policy.
- Dùng tenant_id như context đã được xác minh, nhưng vẫn kiểm tra quyền truy cập tenant/resource theo nghiệp vụ.

### 4.2. Cấu hình principal claim trong bean

~~~java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();

    converter.setPrincipalClaimName("sub");

    return converter;
}
~~~

Gắn vào Servlet Resource Server:

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        JwtAuthenticationConverter converter) throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt
                .jwtAuthenticationConverter(converter)
            )
        )
        .build();
}
~~~

Converter chỉ chạy sau khi decoder xác minh access token. Không dùng converter để thay thế signature, issuer, audience hoặc timestamp validation.

### 4.3. Sử dụng principal trong controller

Với JWT Resource Server, có thể inject Jwt:

~~~java
@RestController
@RequestMapping("/api/profile")
public class ProfileController {

    @GetMapping
    Map<String, String> profile(@AuthenticationPrincipal Jwt jwt) {
        return Map.of(
            "subject", jwt.getSubject(),
            "username", jwt.getClaimAsString("preferred_username")
        );
    }
}
~~~

Hoặc dùng Authentication:

~~~java
@GetMapping("/identity")
String identity(Authentication authentication) {
    return authentication.getName();
}
~~~

Cách thứ hai ít phụ thuộc vào kiểu principal cụ thể hơn nếu ứng dụng chỉ cần tên định danh. Nếu cần claim chi tiết, inject Jwt rõ ràng để người đọc biết endpoint đang phụ thuộc vào JWT.

### 4.4. Không dùng email làm khóa chính của principal nếu không cần

Email có thể thay đổi, có thể không duy nhất theo issuer, hoặc có thể được tái sử dụng sau khi tài khoản bị xóa. Nếu dùng email làm getName(), các hệ thống audit, cache và ownership có thể gặp vấn đề khi email thay đổi.

Nếu cần một display name, hãy đọc claim đó riêng. Không cần thay identity key chỉ để hiển thị tên đẹp hơn.

### 4.5. Nhiều issuer và subject collision

Hai issuer có thể cùng phát hành sub=user-417 cho hai người khác nhau. Nếu ứng dụng hợp nhất nhiều issuer, chỉ dùng sub có thể tạo collision.

Một principal identity nội bộ có thể là cặp:

~~~text
issuer = https://login.alpha.example
subject = user-417
~~~

Có thể chuẩn hóa cặp này thành account key theo quy ước của ứng dụng. Không nối chuỗi tùy tiện nếu delimiter có thể xuất hiện trong dữ liệu; dùng record/value object hoặc encoding không mơ hồ ở tầng domain.

---

## 5. Kết hợp scope và role trong authority converter

### 5.1. Token contract mẫu

Giả sử Authorization Server phát hành access token:

~~~json
{
  "iss": "https://id.example.com/realms/shop",
  "sub": "user-417",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "roles": ["ORDER_READER", "ORDER_ADMIN"]
}
~~~

Ứng dụng muốn tạo:

~~~text
SCOPE_orders.read
SCOPE_orders.write
ROLE_ORDER_READER
ROLE_ORDER_ADMIN
~~~

Scopes và roles có thể đến từ các claim khác nhau. Converter cần map từng loại theo convention riêng.

### 5.2. Viết converter kết hợp

~~~java
public final class OrdersAuthoritiesConverter
        implements Converter<Jwt, Collection<GrantedAuthority>> {

    private static final Set<String> ALLOWED_ROLES = Set.of(
        "ORDER_READER",
        "ORDER_ADMIN"
    );

    private final JwtGrantedAuthoritiesConverter scopes =
        new JwtGrantedAuthoritiesConverter();

    @Override
    public Collection<GrantedAuthority> convert(Jwt jwt) {
        Set<GrantedAuthority> authorities = new LinkedHashSet<>();

        Collection<GrantedAuthority> scopeAuthorities =
            this.scopes.convert(jwt);

        if (scopeAuthorities != null) {
            authorities.addAll(scopeAuthorities);
        }

        Object rawRoles = jwt.getClaims().get("roles");

        if (rawRoles instanceof Collection<?> roles) {
            for (Object rawRole : roles) {
                if (rawRole instanceof String role
                        && ALLOWED_ROLES.contains(role)) {
                    authorities.add(
                        new SimpleGrantedAuthority("ROLE_" + role)
                    );
                }
            }
        }

        return authorities;
    }
}
~~~

Ví dụ chỉ chấp nhận roles là JSON array và chỉ map hai role đã khai báo. Nếu issuer dùng roles dạng chuỗi hoặc claim khác, hãy viết parser theo token contract thật. Không tự chuyển một chuỗi bất kỳ thành role bằng cách thêm ROLE_ vào đầu.

Dùng LinkedHashSet để loại bỏ authority trùng lặp và giữ thứ tự ổn định cho log/test. Authority không được cấp từ claim chưa được kiểm soát.

### 5.3. Gắn converter vào JwtAuthenticationConverter

~~~java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();

    converter.setPrincipalClaimName("sub");
    converter.setJwtGrantedAuthoritiesConverter(
        new OrdersAuthoritiesConverter()
    );

    return converter;
}
~~~

Khi converter này được sử dụng, Authentication sẽ có cả scope authorities và role authorities. Rule có thể kiểm tra riêng:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .requestMatchers(HttpMethod.POST, "/api/orders/**")
        .hasAuthority("SCOPE_orders.write")
    .requestMatchers("/api/admin/**")
        .hasRole("ORDER_ADMIN")
    .anyRequest().denyAll()
)
~~~

Không cấp role chỉ vì tên scope có vẻ giống role. Scope và role có semantics khác nhau, và thường được quản lý ở các lớp khác nhau.

### 5.4. Nếu roles nằm trong claim lồng nhau

Một số issuer phát hành:

~~~json
{
  "realm_access": {
    "roles": ["ORDER_ADMIN"]
  },
  "resource_access": {
    "orders-api": {
      "roles": ["ORDER_READER"]
    }
  }
}
~~~

Converter cần đọc đúng cấu trúc và đúng namespace. Không lấy toàn bộ roles từ mọi client/resource trong token rồi cấp cho API hiện tại.

Ví dụ, role trong resource_access.orders-api có thể phù hợp với Orders API hơn role thuộc billing-api. Hãy giới hạn mapping theo resource identifier.

### 5.5. Kiểm soát role ngoài allowlist

Một token đã được ký bởi issuer tin cậy không có nghĩa mọi chuỗi trong claim roles đều nên được biến thành quyền ứng dụng. Claim có thể chứa role của hệ thống khác, role cũ hoặc dữ liệu do issuer cấu hình nhầm.

Allowlist role giúp phát hiện contract drift và ngăn tên role không được hỗ trợ lọt vào authorization layer. Khi thêm role mới, cập nhật mapping và test cùng với thay đổi ở Authorization Server.

---

## 6. Principal domain riêng khi ứng dụng cần kiểu dữ liệu riêng

### 6.1. Khi nào nên giữ JwtAuthenticationToken?

Nếu controller/service chỉ cần:

- Authentication.getName().
- Jwt claims.
- GrantedAuthority.

thì JwtAuthenticationToken thường đủ. Có thể inject Jwt bằng @AuthenticationPrincipal. Việc tạo custom Authentication cho mọi ứng dụng sẽ tăng code và tạo thêm contract cần duy trì khi nâng cấp.

### 6.2. Khi nào cần principal domain?

Một số ứng dụng có API/service cũ phụ thuộc vào AccountPrincipal hoặc UserDetails. Khi đó có thể cần một Authentication tùy chỉnh để getPrincipal() trả domain object.

Ví dụ domain principal:

~~~java
public record AccountPrincipal(
    String subject,
    String username,
    String tenantId
) {}
~~~

Custom Authentication token:

~~~java
public final class AccountPrincipalAuthenticationToken
        extends AbstractAuthenticationToken {

    private final AccountPrincipal principal;
    private Jwt credentials;

    public AccountPrincipalAuthenticationToken(
            AccountPrincipal principal,
            Jwt credentials,
            Collection<? extends GrantedAuthority> authorities) {

        super(authorities);
        this.principal = principal;
        this.credentials = credentials;
        super.setAuthenticated(true);
    }

    @Override
    public Object getPrincipal() {
        return this.principal;
    }

    @Override
    public Object getCredentials() {
        return this.credentials;
    }

    @Override
    public String getName() {
        return this.principal.subject();
    }

    @Override
    public void eraseCredentials() {
        super.eraseCredentials();
        this.credentials = null;
    }
}
~~~

Trong ví dụ, token JWT được giữ như credentials để có thể được xóa khỏi Authentication khi framework gọi eraseCredentials(). Principal domain chỉ giữ các trường ứng dụng cần. Tránh sao chép toàn bộ access token hoặc claim nhạy cảm vào principal object.

### 6.3. Converter tạo custom Authentication

~~~java
public final class AccountJwtAuthenticationConverter
        implements Converter<Jwt, AbstractAuthenticationToken> {

    private final Converter<Jwt, Collection<GrantedAuthority>>
        authoritiesConverter;

    public AccountJwtAuthenticationConverter(
            Converter<Jwt, Collection<GrantedAuthority>>
                authoritiesConverter) {
        this.authoritiesConverter = authoritiesConverter;
    }

    @Override
    public AbstractAuthenticationToken convert(Jwt jwt) {
        String subject = jwt.getSubject();

        if (subject == null || subject.isBlank()) {
            throw new IllegalArgumentException(
                "JWT subject is required"
            );
        }

        String username =
            jwt.getClaimAsString("preferred_username");

        String tenantId =
            jwt.getClaimAsString("tenant_id");

        AccountPrincipal principal = new AccountPrincipal(
            subject,
            username,
            tenantId
        );

        Collection<GrantedAuthority> authorities =
            this.authoritiesConverter.convert(jwt);

        return new AccountPrincipalAuthenticationToken(
            principal,
            jwt,
            authorities == null ? List.of() : authorities
        );
    }
}
~~~

Trong hệ thống thật, claim bắt buộc nên được xác thực bằng validator trước bước conversion. Converter không nên là nơi duy nhất phát hiện issuer, audience hoặc claim profile không hợp lệ. Ví dụ ném exception ở đây chỉ minh họa contract; có thể thay bằng validator chuyên biệt để lỗi được phân loại rõ ràng.

### 6.4. Hệ quả với controller và method security

Sau khi đổi custom Authentication, code:

~~~java
@AuthenticationPrincipal Jwt jwt
~~~

sẽ không còn phù hợp vì principal bây giờ là AccountPrincipal. Controller cần đổi theo contract mới:

~~~java
@GetMapping("/profile")
AccountPrincipal profile(
        @AuthenticationPrincipal AccountPrincipal principal) {
    return principal;
}
~~~

Hoặc tiếp tục dùng Authentication.getName() nếu chỉ cần subject.

Không thực hiện thay đổi principal type âm thầm. Hãy tìm mọi nơi dùng @AuthenticationPrincipal, Authentication.getPrincipal(), casts sang UserDetails, audit name và cache key trước khi triển khai.

---

## 7. Cấu hình Servlet Resource Server

### 7.1. Cấu hình converter trong SecurityFilterChain

Ví dụ cấu hình đầy đủ với scope và role:

~~~java
@Configuration
@EnableWebSecurity
public class ApiSecurityConfig {

    @Bean
    JwtAuthenticationConverter jwtAuthenticationConverter() {
        JwtAuthenticationConverter converter =
            new JwtAuthenticationConverter();

        converter.setPrincipalClaimName("sub");
        converter.setJwtGrantedAuthoritiesConverter(
            new OrdersAuthoritiesConverter()
        );

        return converter;
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            JwtAuthenticationConverter converter)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers("/api/admin/**")
                    .hasRole("ORDER_ADMIN")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt
                    .jwtAuthenticationConverter(converter)
                )
            )
            .build();
    }
}
~~~

Thứ tự request matcher có ý nghĩa: rule cụ thể phải đứng trước rule tổng quát. anyRequest() là rule cuối. Khi nâng cấp, hãy giữ nguyên thứ tự và kiểm tra matcher có còn bao phủ đúng path/context path như trước không.

### 7.2. Lambda DSL và nâng cấp cấu hình

Các cấu hình Spring Security hiện đại dùng lambda DSL:

~~~java
http
    .authorizeHttpRequests(auth -> auth
        .requestMatchers("/api/orders/**")
            .hasAuthority("SCOPE_orders.read")
        .anyRequest().authenticated()
    )
    .oauth2ResourceServer(oauth2 -> oauth2
        .jwt(jwt -> jwt
            .jwtAuthenticationConverter(converter)
        )
    );
~~~

Trong code cũ có thể gặp chained configurer style:

~~~java
http
    .authorizeRequests()
        .antMatchers("/api/orders/**")
            .hasAuthority("SCOPE_orders.read")
        .and()
    .oauth2ResourceServer()
        .jwt()
            .jwtAuthenticationConverter(converter);
~~~

Khi chuyển sang API mới, không chỉ đổi tên method. Cần xác nhận matcher semantics, thứ tự rule, default behavior và converter đang thực sự được gắn vào decoder chain.

---

## 8. Cấu hình WebFlux Resource Server

### 8.1. Reactive converter có kiểu khác Servlet converter

Servlet converter có contract:

~~~java
Converter<Jwt, AbstractAuthenticationToken>
~~~

Reactive converter cần phát Authentication qua Mono:

~~~java
Converter<Jwt, Mono<AbstractAuthenticationToken>>
~~~

Spring Security cung cấp ReactiveJwtAuthenticationConverterAdapter để bọc converter đồng bộ:

~~~java
Converter<Jwt, AbstractAuthenticationToken> delegate =
    jwtAuthenticationConverter();

Converter<Jwt, Mono<AbstractAuthenticationToken>> reactiveConverter =
    new ReactiveJwtAuthenticationConverterAdapter(delegate);
~~~

Adapter chỉ bọc kết quả đồng bộ thành Mono. Nó không biến database call hoặc HTTP call blocking trong delegate thành non-blocking.

### 8.2. Cấu hình converter cho WebFlux

~~~java
@Bean
Converter<Jwt, Mono<AbstractAuthenticationToken>>
reactiveJwtAuthenticationConverter(
        JwtAuthenticationConverter delegate) {

    return new ReactiveJwtAuthenticationConverterAdapter(delegate);
}

@Bean
SecurityWebFilterChain apiSecurity(
        ServerHttpSecurity http,
        Converter<Jwt, Mono<AbstractAuthenticationToken>> converter) {

    return http
        .authorizeExchange(exchange -> exchange
            .pathMatchers("/api/public/**").permitAll()
            .pathMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .pathMatchers("/api/admin/**")
                .hasRole("ORDER_ADMIN")
            .anyExchange().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt
                .jwtAuthenticationConverter(converter)
            )
        )
        .build();
}
~~~

Đây là WebFlux configuration. Không đưa JwtAuthenticationConverter đồng bộ trực tiếp vào vị trí yêu cầu reactive converter.

### 8.3. Converter thật sự bất đồng bộ

Nếu cần tra cứu thêm authority từ một service reactive, có thể viết converter trả Mono trực tiếp:

~~~java
public final class DirectoryJwtAuthenticationConverter
        implements Converter<Jwt, Mono<AbstractAuthenticationToken>> {

    private final RoleDirectory roleDirectory;

    public DirectoryJwtAuthenticationConverter(
            RoleDirectory roleDirectory) {
        this.roleDirectory = roleDirectory;
    }

    @Override
    public Mono<AbstractAuthenticationToken> convert(Jwt jwt) {
        return this.roleDirectory
            .findAuthorities(jwt.getSubject())
            .map(authorities ->
                new JwtAuthenticationToken(jwt, authorities)
            );
    }
}
~~~

Interface dependency:

~~~java
public interface RoleDirectory {
    Mono<Collection<GrantedAuthority>> findAuthorities(String subject);
}
~~~

Không gọi block() bên trong converter. Nếu directory lỗi, không cấp Authentication với quyền mặc định. Hãy quyết định rõ empty result có nghĩa là user không có quyền hay là lỗi contract; thường service nên phát collection rỗng thay vì Mono.empty() nếu user hợp lệ nhưng không có authority.

### 8.4. SecurityContext trong WebFlux

Servlet thường sử dụng SecurityContextHolder gắn với thread context. WebFlux dùng reactive security context được truyền trong Reactor Context.

Trong reactive code, không dựa vào:

~~~java
SecurityContextHolder.getContext()
~~~

để lấy principal trong mọi callback. Dùng ReactiveSecurityContextHolder hoặc nhận Authentication từ reactive method security/API phù hợp.

Không chuyển pipeline sang blocking code rồi kỳ vọng SecurityContextHolder có cùng semantics. Khi nâng cấp Servlet application sang WebFlux, đây là một thay đổi kiến trúc, không chỉ là đổi converter type.

---

## 9. Opaque token và principal/authority mapping

### 9.1. Opaque token không dùng JwtAuthenticationConverter

Với opaque token, Resource Server introspect token và nhận OAuth2AuthenticatedPrincipal. JwtAuthenticationConverter chỉ dành cho JWT.

Spring Security có OpaqueTokenIntrospector ở Servlet và ReactiveOpaqueTokenIntrospector ở WebFlux. Nếu cần tùy chỉnh principal hoặc authority cho opaque token, hãy tùy chỉnh introspector hoặc converter tương ứng theo API của phiên bản đang dùng.

### 9.2. Mapping scope từ introspection response

Introspection response có thể chứa:

~~~json
{
  "active": true,
  "sub": "user-417",
  "scope": "orders.read orders.write"
}
~~~

Resource Server thường map scope thành authority có prefix SCOPE_. Nếu custom introspector, giữ semantics này hoặc thay bằng convention mới một cách có chủ đích.

### 9.3. Bọc introspector để thêm authority

Mẫu khái niệm:

~~~java
public final class CustomOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;

    public CustomOpaqueTokenIntrospector(
            OpaqueTokenIntrospector delegate) {
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        OAuth2AuthenticatedPrincipal principal =
            this.delegate.introspect(token);

        Collection<GrantedAuthority> authorities =
            new LinkedHashSet<>(principal.getAuthorities());

        Object rawRoles = principal.getAttribute("roles");

        if (rawRoles instanceof Collection<?> roles) {
            for (Object rawRole : roles) {
                if (rawRole instanceof String role
                        && Set.of("ORDER_READER", "ORDER_ADMIN")
                            .contains(role)) {
                    authorities.add(
                        new SimpleGrantedAuthority("ROLE_" + role)
                    );
                }
            }
        }

        return new DefaultOAuth2AuthenticatedPrincipal(
            principal.getName(),
            principal.getAttributes(),
            authorities
        );
    }
}
~~~

Ví dụ minh họa cho Servlet introspector. Với WebFlux, dùng ReactiveOpaqueTokenIntrospector và trả Mono principal. Không dùng một implementation đồng bộ trong reactive event loop nếu nó thực hiện blocking I/O.

### 9.4. Giữ token format độc lập với authorization contract

Dù API nhận JWT hay opaque token, ứng dụng nên cố gắng giữ một convention authority thống nhất:

~~~text
SCOPE_orders.read
SCOPE_orders.write
ROLE_ORDER_ADMIN
~~~

Nếu cùng một endpoint nhận cả hai token format, test phải xác nhận chúng tạo ra quyền tương đương theo policy. Nếu không, người dùng có thể có quyền khác nhau chỉ vì AS phát hành token theo format khác.

---

## 10. Nâng cấp hành vi authorization

### 10.1. hasAuthority và hasRole

Hai matcher thường bị nhầm:

| API | Kiểm tra |
|---|---|
| hasAuthority("SCOPE_orders.read") | Authority chính xác SCOPE_orders.read |
| hasRole("ORDER_ADMIN") | Role authority ROLE_ORDER_ADMIN theo prefix mặc định |
| hasAnyAuthority(...) | Một trong các authority chính xác |
| hasAnyRole(...) | Một trong các role sau khi áp dụng prefix |
| access(...) | Authorization decision theo expression/manager được cung cấp |

Nếu converter trước đây phát ROLE_ADMIN còn converter mới phát SCOPE_admin, các rule cũ sẽ thay đổi hành vi.

Không giải quyết bằng cách nới rule thành authenticated() nếu endpoint vốn yêu cầu quyền cụ thể. Hãy sửa converter hoặc rule theo contract đã thống nhất.

### 10.2. Role prefix tùy chỉnh

Spring Security mặc định dùng ROLE_ cho các helper role-based. Có thể cấu hình GrantedAuthorityDefaults nếu ứng dụng cần prefix khác:

~~~java
@Bean
GrantedAuthorityDefaults grantedAuthorityDefaults() {
    return new GrantedAuthorityDefaults("APPROLE_");
}
~~~

Nếu thay prefix, mọi nơi dùng hasRole/hasAnyRole và method security phải được kiểm tra. Đồng thời, converter phải phát authority tương thích với prefix mới nếu role helper được dùng.

Đổi prefix có thể làm mất quyền trên diện rộng. Hãy xem đây là migration behavior có tác động bảo mật.

### 10.3. Request matcher và thứ tự rule

Ví dụ:

~~~java
.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/admin/**")
        .hasRole("ORDER_ADMIN")
    .requestMatchers("/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyRequest().denyAll()
)
~~~

Rule cụ thể cần đứng trước rule tổng quát. Khi nâng cấp, hãy kiểm tra:

- Path pattern có khớp như trước không.
- Context path/servlet path có thay đổi không.
- HTTP method có được giới hạn đúng không.
- Matcher nào được áp dụng đầu tiên.
- Endpoint mới có vô tình rơi vào authenticated() thay vì denyAll() không.

Không giả định các matcher cũ và mới có semantics hoàn toàn giống nhau chỉ vì pattern string giống nhau. Hãy kiểm tra theo stack và version.

### 10.4. Method security

Cấu hình method security hiện đại dùng @EnableMethodSecurity:

~~~java
@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
~~~

Các annotation như @PreAuthorize, @PostAuthorize, @PreFilter và @PostFilter có thể bảo vệ service method. Khi nâng cấp từ cấu hình cũ, kiểm tra:

- Annotation nào được bật.
- Proxy có bao phủ bean và method đó không.
- Self-invocation có bypass proxy không.
- Expression có dùng đúng authority prefix không.
- Custom PermissionEvaluator/AuthorizationManager còn được wiring không.
- Các method nhạy cảm có test allow/deny tương ứng không.

Với WebFlux, bật reactive method security bằng @EnableReactiveMethodSecurity và giữ security context trong reactive execution model.

### 10.5. Scope và object-level authorization

Scope orders.read có thể cho phép gọi chức năng đọc đơn hàng, nhưng không có nghĩa user được đọc mọi đơn hàng.

Một authorization flow có thể gồm:

1. Request matcher kiểm tra scope.
2. Method security kiểm tra role hoặc permission nghiệp vụ.
3. Service kiểm tra tenant membership.
4. Repository giới hạn bản ghi theo owner/tenant.
5. Audit ghi nhận hành động theo principal identity.

Không thay object-level authorization bằng một authority tổng quát. Converter chỉ tạo quyền từ token; service vẫn phải kiểm tra quyền trên resource cụ thể.

---

## 11. Những thay đổi thường gặp khi nâng cấp Spring Security

### 11.1. Chuyển từ chained DSL sang lambda DSL

Code cũ có thể dùng authorizeRequests/antMatchers và chained configurer. Code hiện đại dùng authorizeHttpRequests/requestMatchers và lambda DSL.

Khi migrate, giữ lại ý nghĩa của từng rule:

| Cấu hình cũ | Cấu hình mới thường dùng |
|---|---|
| authorizeRequests() | authorizeHttpRequests(...) |
| antMatchers(...) | requestMatchers(...) |
| chained jwtAuthenticationConverter(...) | jwt(jwt -> jwt.jwtAuthenticationConverter(...)) |
| @EnableGlobalMethodSecurity | @EnableMethodSecurity |
| Servlet SecurityFilterChain | Vẫn là SecurityFilterChain |
| Reactive SecurityWebFilterChain | Vẫn là SecurityWebFilterChain |

Đây là hướng chuyển đổi khái quát. API cụ thể và deprecation/removal phụ thuộc phiên bản Spring Security. Hãy kiểm tra migration guide/Javadoc của đúng major version.

### 11.2. Converter không còn được gắn đúng chỗ

Một lỗi phổ biến là tạo custom JwtAuthenticationConverter bean nhưng không truyền bean đó vào Resource Server configurer. Bean tồn tại không có nghĩa framework tự động dùng nó.

Kiểm tra DSL:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt
        .jwtAuthenticationConverter(jwtAuthenticationConverter)
    )
)
~~~

Sau nâng cấp, test Authentication thực tế được tạo bởi request HTTP. Đừng chỉ unit test bean rồi kết luận security chain đã dùng converter.

### 11.3. Scope claim hoặc role claim đổi schema

Authorization Server có thể đổi từ:

~~~json
{
  "scope": "orders.read"
}
~~~

sang:

~~~json
{
  "scp": ["orders.read"]
}
~~~

Hoặc chuyển role vào claim lồng nhau. Converter cần phản ánh token contract mới. Không để migration framework và migration token schema diễn ra cùng lúc mà thiếu test đối chiếu, vì khi lỗi xảy ra khó biết nguyên nhân nằm ở đâu.

### 11.4. Principal name thay đổi

Nếu code trước dùng username còn converter mới dùng sub, audit record, cache key, tenant lookup và service logs có thể thay đổi identity. Xác định các consumer của Authentication.getName() trước khi thay claim.

Nếu cần thay đổi, có thể hỗ trợ một giai đoạn chuyển tiếp bằng field riêng hoặc adapter domain. Không thay đổi identity key giữa một release mà không đánh giá dữ liệu lịch sử.

### 11.5. Servlet và WebFlux bị trộn API

Một số lớp có tên gần giống nhau nhưng contract khác:

| Servlet | WebFlux |
|---|---|
| HttpSecurity | ServerHttpSecurity |
| SecurityFilterChain | SecurityWebFilterChain |
| JwtDecoder | ReactiveJwtDecoder |
| Converter<Jwt, AbstractAuthenticationToken> | Converter<Jwt, Mono<AbstractAuthenticationToken>> |
| JwtAuthenticationConverter | ReactiveJwtAuthenticationConverterAdapter hoặc converter reactive tùy chỉnh |
| SecurityContextHolder | ReactiveSecurityContextHolder |
| OpaqueTokenIntrospector | ReactiveOpaqueTokenIntrospector |

Không dùng blocking converter trong reactive event loop. Không dùng reactive converter trong Servlet DSL. Nếu ứng dụng chuyển stack, hãy thiết kế lại integration boundary thay vì chỉ sửa import.

---

## 12. Kiểm thử converter và principal contract

### 12.1. Tạo Jwt fixture

~~~java
static Jwt testJwt() {
    Instant now = Instant.now();

    return Jwt.withTokenValue("test-token")
        .header("alg", "RS256")
        .issuer("https://id.example.test")
        .subject("user-417")
        .audience(List.of("orders-api"))
        .issuedAt(now.minusSeconds(10))
        .expiresAt(now.plusSeconds(300))
        .claim("preferred_username", "phuong")
        .claim("tenant_id", "tenant-a")
        .claim("scope", "orders.read orders.write")
        .claim("roles", List.of("ORDER_READER", "ORDER_ADMIN"))
        .build();
}
~~~

Fixture này phù hợp để test converter. Nó không chứng minh signature validation; test decoder cần JWT compact được ký bằng key test.

### 12.2. Test principal name và authorities

~~~java
@Test
void mapsPrincipalAndAuthorities() {
    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();

    converter.setPrincipalClaimName("preferred_username");
    converter.setJwtGrantedAuthoritiesConverter(
        new OrdersAuthoritiesConverter()
    );

    AbstractAuthenticationToken authentication =
        converter.convert(testJwt());

    assertEquals("phuong", authentication.getName());

    Set<String> authorities = authentication.getAuthorities().stream()
        .map(GrantedAuthority::getAuthority)
        .collect(Collectors.toSet());

    assertTrue(authorities.contains("SCOPE_orders.read"));
    assertTrue(authorities.contains("SCOPE_orders.write"));
    assertTrue(authorities.contains("ROLE_ORDER_READER"));
    assertTrue(authorities.contains("ROLE_ORDER_ADMIN"));
}
~~~

Kiểm tra authority bằng set giúp test không phụ thuộc thứ tự. Nếu thứ tự có ý nghĩa trong ứng dụng, hãy định nghĩa rõ; phần lớn authorization checks chỉ cần membership.

### 12.3. Test role không nằm trong allowlist

~~~java
@Test
void ignoresUnknownRole() {
    Jwt jwt = Jwt.withTokenValue("test-token")
        .header("alg", "RS256")
        .subject("user-417")
        .claim("roles", List.of("ORDER_ADMIN", "SUPERUSER"))
        .build();

    Collection<GrantedAuthority> authorities =
        new OrdersAuthoritiesConverter().convert(jwt);

    Set<String> names = authorities.stream()
        .map(GrantedAuthority::getAuthority)
        .collect(Collectors.toSet());

    assertTrue(names.contains("ROLE_ORDER_ADMIN"));
    assertFalse(names.contains("ROLE_SUPERUSER"));
}
~~~

Test này bảo vệ mapping contract khi issuer thêm role ngoài dự kiến. Tùy policy, có thể bỏ qua role lạ và phát metric cảnh báo, hoặc từ chối token nếu schema yêu cầu nghiêm ngặt.

### 12.4. Test principal claim thiếu

Nếu ứng dụng yêu cầu preferred_username, test token thiếu claim đó. Quyết định fallback phải rõ ràng:

- Dùng sub làm fallback.
- Từ chối Authentication nếu claim bắt buộc thiếu.
- Dùng custom principal chứa null cho display field nhưng vẫn giữ subject.

Không để hành vi phụ thuộc vào implicit fallback mà không có test.

### 12.5. Test custom principal type

Nếu dùng custom Authentication, xác nhận:

~~~java
assertInstanceOf(
    AccountPrincipal.class,
    authentication.getPrincipal()
);

AccountPrincipal principal =
    (AccountPrincipal) authentication.getPrincipal();

assertEquals("user-417", principal.subject());
assertEquals("tenant-a", principal.tenantId());
~~~

Cũng kiểm tra eraseCredentials() nếu custom token giữ JWT trong credentials. Đừng giữ access token trong object sống lâu hơn cần thiết.

---

## 13. Kiểm thử authorization behavior sau nâng cấp

### 13.1. Phân biệt 401 và 403

| Tình huống | Kết quả mong đợi |
|---|---|
| Không có token | 401 |
| Token sai chữ ký/issuer/audience | 401 |
| Token hết hạn | 401 |
| Authentication thành công nhưng thiếu scope | 403 |
| Có scope nhưng thiếu role admin | 403 |
| Có scope/role nhưng không thuộc tenant | 403 hoặc 404 theo policy |
| Có đủ quyền và đúng resource | 2xx |

Nếu converter mất authority, request sẽ thường chuyển từ 2xx sang 403. Nếu decoder không còn được cấu hình, token có thể bị từ chối 401. Đây là hai lỗi migration khác nhau và cần được test riêng.

### 13.2. MockMvc cho Servlet authorization

Spring Security test hỗ trợ JWT request postprocessor:

~~~java
mockMvc.perform(get("/api/orders")
        .with(jwt()
            .jwt(jwt -> jwt
                .subject("user-417")
                .claim("scope", "orders.read")
            )
            .authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )
        ))
    .andExpect(status().isOk());
~~~

Helper jwt() thường tạo Authentication test để kiểm tra authorization rule. Nó không chạy chữ ký JWT decoder. Nếu mục tiêu là test converter, hãy gọi converter thật hoặc cấu hình test phù hợp; nếu mục tiêu là signature/issuer/audience validation, gửi compact JWT được ký thật.

### 13.3. WebTestClient cho WebFlux authorization

~~~java
webTestClient
    .mutateWith(mockJwt()
        .jwt(jwt -> jwt
            .subject("user-417")
            .claim("scope", "orders.read")
        )
        .authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )
    )
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

Tương tự MockMvc, mockJwt giúp test route authorization. Để kiểm tra converter thật, cần để Resource Server xử lý token theo security chain và quan sát Authentication được tạo.

### 13.4. Test converter reactive bằng StepVerifier

Khi dùng adapter:

~~~java
Converter<Jwt, Mono<AbstractAuthenticationToken>> converter =
    new ReactiveJwtAuthenticationConverterAdapter(
        jwtAuthenticationConverter
    );

StepVerifier.create(converter.convert(testJwt()))
    .assertNext(authentication -> {
        assertEquals("user-417", authentication.getName());
        assertTrue(authentication.getAuthorities().stream()
            .anyMatch(authority ->
                authority.getAuthority().equals("SCOPE_orders.read")));
    })
    .verifyComplete();
~~~

Với converter có async role lookup, test cả success, empty result, timeout và upstream failure. Không chuyển lỗi directory thành Authentication với quyền mặc định.

### 13.5. Migration contract test

Trước khi nâng cấp, ghi lại contract hiện tại:

~~~text
Principal name:
  user-417

Principal type:
  UserDetails hoặc Jwt

Authorities:
  SCOPE_orders.read
  ROLE_ORDER_ADMIN

GET /api/orders:
  200 khi có SCOPE_orders.read
  403 khi thiếu scope

POST /api/orders:
  200 khi có SCOPE_orders.write
  403 khi chỉ có orders.read

GET /api/admin:
  200 khi có ROLE_ORDER_ADMIN
  403 khi chỉ có SCOPE_orders.read
~~~

Sau nâng cấp, chạy cùng bộ test trên cấu hình mới. Nếu khác biệt là chủ đích, cập nhật contract và migration note. Nếu không, sửa converter hoặc rule trước khi rollout.

---

## 14. Quy trình nâng cấp an toàn

### Bước 1: Lập bản đồ principal consumers

Tìm mọi nơi dùng:

- Authentication.getName().
- Authentication.getPrincipal().
- @AuthenticationPrincipal.
- Cast sang Jwt, UserDetails hoặc principal custom.
- Principal trong audit, cache key, tenant lookup và database ownership.
- ReactiveSecurityContextHolder hoặc SecurityContextHolder.

Ghi lại kiểu và semantics hiện tại.

### Bước 2: Ghi lại authority contract

Liệt kê claim nguồn và authority kết quả:

| Claim nguồn | Kiểu dữ liệu | Authority |
|---|---|---|
| scope | String hoặc list theo AS contract | SCOPE_* |
| roles | JSON array | ROLE_* |
| permissions | JSON array | PERM_* |
| groups | issuer-specific | Chỉ map khi policy yêu cầu |

Ghi rõ prefix, role allowlist, cách xử lý claim thiếu và role lạ.

### Bước 3: Giữ nguyên token validation

Tách migration converter khỏi migration trust policy nếu có thể. Giữ issuer, audience, signature algorithm, expiry và key source validation. Không nới decoder để làm test authorization pass.

### Bước 4: Tạo converter tường minh

Đưa principal name và authority mapping vào bean có thể unit test. Không dựa vào default mapping nếu token schema của ứng dụng có claim custom.

### Bước 5: Cập nhật authorization DSL

Chuyển matcher sang API version mới, giữ thứ tự và semantics. Kiểm tra hasRole/hasAuthority, prefix, method security và role hierarchy.

### Bước 6: Chọn đúng Servlet hoặc WebFlux adapter

Servlet dùng converter đồng bộ. WebFlux dùng reactive converter hoặc adapter cho converter thuần đồng bộ. Không gọi blocking service trong reactive converter.

### Bước 7: Chạy contract và integration tests

Kiểm tra principal name/type, authority set, 401/403, request matchers, method security và object-level authorization.

### Bước 8: Rollout có quan sát

Triển khai theo canary hoặc nhóm instance nhỏ nếu hạ tầng hỗ trợ. Theo dõi 401/403, authority mapping failures, principal type errors, method security denials và exception khi cast principal.

### Bước 9: Rollback theo contract

Giữ phiên bản converter và cấu hình cũ có thể khôi phục. Nếu token schema cũng thay đổi, bảo đảm cả hai phiên bản ứng dụng tương thích với thời gian overlap hoặc có kế hoạch phát hành token tương ứng.

---

## 15. Những lỗi thường gặp khi nâng cấp

| Sai lầm | Hậu quả | Cách xử lý |
|---|---|---|
| Đổi principal claim mà không tìm consumer | Audit/cache/ownership thay đổi identity | Tìm mọi nơi gọi getName() |
| Cast getPrincipal() sang UserDetails | ClassCastException | Dùng Jwt hoặc custom Authentication rõ ràng |
| Chỉ đọc roles và bỏ scope | API mất quyền scope | Kết hợp converter có chủ đích |
| Dùng hasRole cho SCOPE_ authority | Request bị 403 | Dùng hasAuthority đúng chuỗi |
| Dùng hasAuthority("ADMIN") với ROLE_ADMIN | Rule không khớp | Dùng hasRole hoặc exact ROLE_ authority |
| Thay scope prefix | Mất hoặc cấp nhầm quyền | Test authority contract |
| Map mọi chuỗi role thành authority | Role ngoài policy lọt vào | Allowlist role và namespace |
| Tạo custom principal chứa raw token lâu dài | Tăng rủi ro lộ credential | Giữ dữ liệu tối thiểu và erase credentials |
| Tạo converter bean nhưng không gắn vào DSL | Bean không được sử dụng | Kiểm tra SecurityFilterChain wiring |
| Dùng converter Servlet trong WebFlux | Sai generic contract hoặc blocking | Dùng reactive adapter/converter |
| Dùng SecurityContextHolder trong reactive callback | Không thấy context hoặc sai thread | Dùng ReactiveSecurityContextHolder |
| Bỏ method security khi đổi annotation | Service mất lớp bảo vệ | Kiểm tra @EnableMethodSecurity |
| Đổi matcher mà không giữ thứ tự | Rule rộng che rule hẹp | Đặt matcher cụ thể trước |
| Dùng mockJwt để kiểm tra chữ ký | Test bỏ qua decoder | Dùng signed JWT integration test |
| Chỉ test 200 | Bỏ sót đường 403/401 | Test đủ allow/deny/error |
| Dùng email làm principal key | Identity thay đổi khi email đổi | Dùng subject ổn định |
| Tin role claim từ issuer khác schema | Quyền không đúng resource | Kiểm tra issuer/resource namespace |
| Fail-open khi authority lookup lỗi | Cấp Authentication thiếu căn cứ | Truyền lỗi hoặc fail closed theo policy |

---

## 16. Câu hỏi tự kiểm tra

**Câu 1.** JwtAuthenticationToken.getPrincipal() và getName() có giống nhau không?

**Trả lời:** Không. getPrincipal() thường trả đối tượng Jwt; getName() trả chuỗi định danh được chọn từ principal claim, mặc định thường là sub.

**Câu 2.** JwtAuthenticationConverter dùng để làm gì?

**Trả lời:** Chuyển Jwt đã được xác minh thành Authentication, đồng thời xác định principal name và authority collection.

**Câu 3.** JwtGrantedAuthoritiesConverter mặc định đọc claim nào?

**Trả lời:** Nó hỗ trợ convention scope/scp của Spring Security và tạo authority với prefix mặc định SCOPE_.

**Câu 4.** Vì sao hasRole("ORDER_ADMIN") không khớp SCOPE_orders.read?

**Trả lời:** hasRole dùng role prefix ROLE_ mặc định. Scope authority dùng prefix SCOPE_ và là một loại quyền khác.

**Câu 5.** setAuthoritiesClaimName("roles") có tự kết hợp scope không?

**Trả lời:** Không. Nó cấu hình claim mà converter đó đọc. Muốn cả scope và role, cần converter kết hợp.

**Câu 6.** Đổi principal claim sang preferred_username có đổi kiểu getPrincipal() không?

**Trả lời:** Không. JwtAuthenticationToken vẫn giữ Jwt làm principal; tên từ getName() được lấy theo claim được cấu hình.

**Câu 7.** Khi nào cần custom Authentication?

**Trả lời:** Khi ứng dụng thực sự cần getPrincipal() trả domain principal/UserDetails riêng. Nếu chỉ cần tên và claims, JwtAuthenticationToken thường đủ.

**Câu 8.** ReactiveJwtAuthenticationConverterAdapter làm gì?

**Trả lời:** Bọc converter đồng bộ thành converter trả Mono. Nó không biến blocking I/O trong delegate thành non-blocking.

**Câu 9.** Opaque token có dùng JwtAuthenticationConverter không?

**Trả lời:** Không. Opaque token dùng introspector để tạo OAuth2AuthenticatedPrincipal; tùy chỉnh qua introspector/converter tương ứng.

**Câu 10.** Vì sao cần test cả 401 và 403?

**Trả lời:** 401 phản ánh authentication thất bại; 403 phản ánh Authentication đã thành công nhưng thiếu quyền. Hai lỗi chỉ ra hai phần khác nhau của migration.

**Câu 11.** MockMvc jwt() có xác minh chữ ký token không?

**Trả lời:** Không. Nó tạo Authentication test để kiểm tra authorization. Cần JWT ký thật để test decoder.

**Câu 12.** Có nên map mọi role trong JWT thành GrantedAuthority không?

**Trả lời:** Không nên nếu issuer phát nhiều namespace hoặc role không thuộc API. Map role theo resource và allowlist rõ ràng.

**Câu 13.** Khi chuyển từ Servlet sang WebFlux, có thể dùng SecurityContextHolder không?

**Trả lời:** Không nên dựa vào ThreadLocal trong reactive flow. Dùng ReactiveSecurityContextHolder và giữ context trong Reactor pipeline.

**Câu 14.** Vì sao thứ tự requestMatchers quan trọng?

**Trả lời:** Authorization DSL áp dụng rule theo thứ tự match. Rule rộng đặt trước có thể che rule cụ thể phía sau.

**Câu 15.** Thay đổi authority prefix có phải refactor nhỏ không?

**Trả lời:** Không. Nó có thể làm mọi request thay đổi kết quả authorization. Cần contract tests, rollout có quan sát và kế hoạch rollback.

---

## 17. Tài liệu tham khảo

- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT authentication, JwtAuthenticationConverter và authority mapping.
- [Spring Security API — JwtAuthenticationConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationConverter.html): principal claim và authority converter.
- [Spring Security API — JwtGrantedAuthoritiesConverter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtGrantedAuthoritiesConverter.html): scope claim và authority prefix.
- [Spring Security — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): reactive JWT converter và WebFlux Resource Server.
- [Spring Security API — ReactiveJwtAuthenticationConverterAdapter](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/ReactiveJwtAuthenticationConverterAdapter.html): adapter cho converter đồng bộ trong reactive stack.
- [Spring Security — Authorization](https://docs.spring.io/spring-security/reference/servlet/authorization/index.html): request authorization và AuthorizationManager.
- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): @EnableMethodSecurity và method authorization.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): reactive method security và Reactor context.
- [Spring Security — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html): MockMvc security test support.
- [Spring Security — WebFlux Testing](https://docs.spring.io/spring-security/reference/reactive/test/index.html): WebTestClient và reactive security test support.

API có thể thay đổi giữa các major/minor version. Hãy kiểm tra migration guide và Javadoc đúng phiên bản đang nâng cấp, đặc biệt với DSL, converter generic và method security.

---

## 18. Ghi nhớ

Khi nâng cấp Spring Security Resource Server, principal mapping, authority conversion và authorization rules phải được xem như một hợp đồng thống nhất.

- **Principal:** mặc định JWT principal là Jwt; getName() thường dùng sub. Đổi claim name không tự đổi kiểu principal.
- **Authorities:** JwtGrantedAuthoritiesConverter mặc định map scope/scp thành SCOPE_*. Role cần mapping riêng và prefix ROLE_ theo convention.
- **Custom mapping:** kết hợp scope và role rõ ràng; giới hạn namespace/role được phép; không biến mọi claim thành quyền.
- **Custom principal:** chỉ tạo Authentication domain riêng khi ứng dụng thực sự cần kiểu principal khác, đồng thời quản lý credentials và mọi consumer.
- **Servlet/WebFlux:** Servlet dùng converter đồng bộ; WebFlux cần converter trả Mono hoặc ReactiveJwtAuthenticationConverterAdapter.
- **Authorization:** kiểm tra hasRole/hasAuthority, matcher order, method security, tenant và object-level permission.
- **Migration:** giữ token validation, ghi lại contract cũ, test principal/authority và 401/403, rollout có quan sát và chuẩn bị rollback.

Một bản nâng cấp hoàn tất khi ứng dụng tạo đúng principal, phát đúng authority và giữ đúng quyết định phân quyền cho từng request hợp lệ hoặc không hợp lệ.
