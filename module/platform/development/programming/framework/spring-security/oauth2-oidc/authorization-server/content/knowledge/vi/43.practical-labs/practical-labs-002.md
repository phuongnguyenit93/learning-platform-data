# Bổ sung JDBC, custom login và consent page

Trong bài thực hành này, bạn sẽ chuyển dữ liệu client và authorization của Spring Authorization Server từ bộ nhớ sang JDBC, xác thực người dùng bằng tài khoản lưu trong database, rồi thay trang đăng nhập và trang xin consent mặc định bằng giao diện Thymeleaf. Khi hoàn thành, client có thể bắt đầu authorization code flow, người dùng đăng nhập, xem các scope được yêu cầu, chấp thuận quyền và quay về callback để đổi authorization code lấy token.

Các phần được kết nối với nhau theo ba loại dữ liệu:

| Dữ liệu | Thành phần lưu trữ | Vai trò |
|---|---|---|
| Client registration | JdbcRegisteredClientRepository | Client ID, secret đã mã hóa, grant type, redirect URI, scope và client settings |
| Authorization và token state | JdbcOAuth2AuthorizationService | Authorization code, access token, refresh token, ID token và trạng thái của chúng |
| Consent | JdbcOAuth2AuthorizationConsentService | Các quyền người dùng đã chấp thuận cho từng client |
| Tài khoản người dùng | JdbcUserDetailsManager | Username, password đã mã hóa, trạng thái tài khoản và authorities |

Spring Authorization Server cung cấp các implementation JDBC cho ba loại dữ liệu OAuth đầu tiên. Spring Security cung cấp JdbcUserDetailsManager cho tài khoản người dùng. Flyway quản lý schema theo migration để cấu trúc database có thể được triển khai lặp lại ở các môi trường.

## 1. Chuẩn bị project và database

Ví dụ sử dụng Spring Boot 3, Spring Security 6, Spring Authorization Server tương thích với phiên bản Spring Security đang dùng, Java 17 trở lên, PostgreSQL và Thymeleaf. Không trộn các phiên bản Spring Security hoặc Spring Authorization Server không tương thích. Kiểm tra release notes và dependency management của phiên bản đã chọn trước khi bắt đầu.

Các dependency chính trong Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-thymeleaf'
    implementation 'org.springframework.security:spring-security-oauth2-authorization-server'
    implementation 'org.flywaydb:flyway-core'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Dependency Spring Authorization Server cần phiên bản được chọn tương thích với Spring Security của Spring Boot. Nếu BOM của project không quản lý artifact này, khai báo version trong Gradle version catalog hoặc dependency constraint; không chọn một version độc lập với Spring Security. Nếu phiên bản Flyway đang dùng tách database support thành module riêng, thêm module PostgreSQL tương ứng theo tài liệu của phiên bản Flyway đó.

Khởi động PostgreSQL cục bộ bằng Docker:

~~~yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_DB: authserver
      POSTGRES_USER: authserver
      POSTGRES_PASSWORD: local-dev-password
    ports:
      - "5432:5432"
    volumes:
      - authserver-data:/var/lib/postgresql/data

volumes:
  authserver-data:
~~~

Lưu nội dung này thành docker-compose.yml trong project lab rồi chạy:

~~~bash
docker compose up -d
~~~

Cấu hình ứng dụng trong application.yml:

~~~yaml
server:
  port: 9000

spring:
  datasource:
    url: jdbc:postgresql://localhost:5432/authserver
    username: authserver
    password: local-dev-password
    driver-class-name: org.postgresql.Driver
  flyway:
    enabled: true
    locations: classpath:db/migration
  thymeleaf:
    cache: false
~~~

Credential trong ví dụ chỉ dành cho database cục bộ. Ở môi trường dùng chung, lấy URL và credential từ secret manager hoặc biến môi trường, giới hạn quyền của database user và bật TLS cho kết nối database.

## 2. Tạo schema bằng Flyway

Tạo thư mục src/main/resources/db/migration. Migration đầu tiên tạo bảng tài khoản và authorities mà JdbcUserDetailsManager sử dụng theo mặc định:

~~~sql
-- V1__user_tables.sql
CREATE TABLE users (
    username VARCHAR(100) PRIMARY KEY,
    password VARCHAR(500) NOT NULL,
    enabled BOOLEAN NOT NULL
);

CREATE TABLE authorities (
    username VARCHAR(100) NOT NULL,
    authority VARCHAR(100) NOT NULL,
    CONSTRAINT fk_authorities_users
        FOREIGN KEY (username) REFERENCES users(username)
);

CREATE UNIQUE INDEX ix_auth_username
    ON authorities (username, authority);
~~~

Migration tiếp theo cần tạo ba bảng của Spring Authorization Server:

- oauth2_registered_client
- oauth2_authorization
- oauth2_authorization_consent

Không tự tạo ba bảng này bằng một schema rút gọn. Lấy đúng các script schema đi kèm phiên bản Spring Authorization Server đang sử dụng, rồi đưa nội dung vào migration Flyway:

~~~text
org/springframework/security/oauth2/server/authorization/client/oauth2-registered-client-schema.sql
org/springframework/security/oauth2/server/authorization/oauth2-authorization-schema.sql
org/springframework/security/oauth2/server/authorization/consent/oauth2-authorization-consent-schema.sql
~~~

Đặt các câu lệnh tương ứng vào V2__authorization_server_tables.sql. Script gốc có thể cần điều chỉnh kiểu dữ liệu cho PostgreSQL hoặc database vendor khác, đặc biệt với các cột lưu dữ liệu lớn và serialized attributes. Giữ nguyên tên bảng, tên cột và độ dài tương thích với JDBC implementation. Không lấy schema từ một phiên bản thư viện khác với dependency đang chạy.

Sau khi ứng dụng khởi động, Flyway phải ghi nhận V1 và V2 trong flyway_schema_history. Nếu migration thất bại, sửa migration trong database dùng riêng cho lab rồi chạy lại theo quy trình Flyway; không xóa hoặc sửa lịch sử migration ở môi trường dùng chung để che lỗi.

## 3. Kết nối các JDBC service

Spring Boot tự cấu hình DataSource và JdbcTemplate từ application.yml. Khai báo repository và service JDBC:

~~~java
@Configuration
public class AuthorizationPersistenceConfiguration {

    @Bean
    RegisteredClientRepository registeredClientRepository(
            JdbcTemplate jdbcTemplate) {
        return new JdbcRegisteredClientRepository(jdbcTemplate);
    }

    @Bean
    OAuth2AuthorizationService authorizationService(
            JdbcTemplate jdbcTemplate,
            RegisteredClientRepository registeredClientRepository) {
        return new JdbcOAuth2AuthorizationService(
                jdbcTemplate, registeredClientRepository);
    }

    @Bean
    OAuth2AuthorizationConsentService authorizationConsentService(
            JdbcTemplate jdbcTemplate,
            RegisteredClientRepository registeredClientRepository) {
        return new JdbcOAuth2AuthorizationConsentService(
                jdbcTemplate, registeredClientRepository);
    }
}
~~~

Ba bean này có trách nhiệm riêng. RegisteredClientRepository đọc và ghi cấu hình client. OAuth2AuthorizationService lưu trạng thái authorization và token. OAuth2AuthorizationConsentService lưu quyền đã được người dùng chấp thuận. Nếu chỉ chuyển client registration sang JDBC nhưng vẫn dùng service lưu authorization trong bộ nhớ, code hoặc token có thể biến mất khi ứng dụng restart.

Không tạo schema tự động ở mỗi lần chạy production. Flyway chịu trách nhiệm thay đổi schema; JDBC service chỉ đọc và ghi dữ liệu theo schema tương ứng với phiên bản thư viện.

## 4. Cấu hình password encoder và tài khoản JDBC

Tạo PasswordEncoder dùng chung cho mật khẩu đăng nhập và client secret. DelegatingPasswordEncoder lưu prefix thuật toán trong chuỗi đã mã hóa, giúp server nhận diện encoder khi xác minh:

~~~java
@Configuration
public class IdentityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    JdbcUserDetailsManager userDetailsService(DataSource dataSource) {
        return new JdbcUserDetailsManager(dataSource);
    }
}
~~~

JdbcUserDetailsManager mặc định sử dụng bảng users và authorities đã tạo ở migration V1. Nếu schema tổ chức khác tên hoặc cấu trúc mặc định, phải cấu hình các query tương ứng bằng API của JdbcUserDetailsManager và kiểm thử lại việc đọc user cùng authorities.

Tạo một tài khoản demo idempotent để chạy lab:

~~~java
@Bean
ApplicationRunner seedDemoUser(
        JdbcUserDetailsManager users,
        PasswordEncoder passwordEncoder) {

    return args -> {
        if (!users.userExists("alice")) {
            users.createUser(User.withUsername("alice")
                    .password(passwordEncoder.encode("local-only-password"))
                    .roles("USER")
                    .build());
        }
    };
}
~~~

Tài khoản demo chỉ dùng trên database cục bộ. Không giữ mật khẩu cố định trong source code hoặc tạo tài khoản mặc định có quyền cao khi triển khai production. Trong ứng dụng thật, tài khoản nên được tạo qua quy trình quản trị hoặc identity provider phù hợp.

## 5. Lưu RegisteredClient trong JDBC

Tạo một client dành cho authorization code flow. Client yêu cầu PKCE và consent để bài lab có thể kiểm tra cả hai bước:

~~~java
@Bean
ApplicationRunner seedRegisteredClient(
        RegisteredClientRepository clients,
        PasswordEncoder passwordEncoder) {

    return args -> {
        if (clients.findByClientId("portal-client") == null) {
            RegisteredClient client = RegisteredClient
                    .withId(UUID.randomUUID().toString())
                    .clientId("portal-client")
                    .clientName("Portal Lab")
                    .clientSecret(passwordEncoder.encode("local-only-secret"))
                    .clientAuthenticationMethod(
                            ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                    .authorizationGrantType(
                            AuthorizationGrantType.AUTHORIZATION_CODE)
                    .authorizationGrantType(
                            AuthorizationGrantType.REFRESH_TOKEN)
                    .redirectUri("http://localhost:9000/callback")
                    .scope(OidcScopes.OPENID)
                    .scope(OidcScopes.PROFILE)
                    .scope("orders.read")
                    .clientSettings(ClientSettings.builder()
                            .requireProofKey(true)
                            .requireAuthorizationConsent(true)
                            .build())
                    .build();

            clients.save(client);
        }
    };
}
~~~

Client ID là định danh giao thức mà client gửi trong request. id truyền cho withId là khóa nội bộ của bản ghi RegisteredClient; hai giá trị này không thể thay thế cho nhau. Client secret phải được mã hóa bằng PasswordEncoder tương thích với client authentication provider. Không lưu raw secret trong cột client_secret.

Client secret authentication có PasswordEncoder riêng trong ClientSecretAuthenticationProvider. Với cấu hình mặc định, dùng DelegatingPasswordEncoder tương thích; nếu ứng dụng tùy chỉnh provider, cấu hình cùng PasswordEncoder bean để giá trị đã lưu và giá trị nhận được được so sánh theo cùng thuật toán.

Nếu ứng dụng có nhiều instance, seed runner phải an toàn khi chạy đồng thời. Với môi trường production, quản lý client registration qua migration dữ liệu hoặc quy trình quản trị có kiểm soát; tránh để mọi instance cùng tạo client mới bằng UUID khi khởi động.

## 6. Cấu hình Authorization Server và application filter chain

Authorization Server cần một chain dành cho endpoint giao thức và một chain dự phòng cho trang đăng nhập, consent page cùng các route ứng dụng. Endpoint matcher nên lấy từ configurer để không bỏ sót endpoint khi bật thêm OIDC:

~~~java
@Configuration
public class SecurityConfiguration {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerChain(HttpSecurity http)
            throws Exception {

        OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
                OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(
                    authorizationServerConfigurer.getEndpointsMatcher())
            .with(authorizationServerConfigurer, authorizationServer ->
                    authorizationServer
                        .oidc(Customizer.withDefaults())
                        .authorizationEndpoint(endpoint ->
                                endpoint.consentPage("/oauth2/consent"))
            )
            .authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated())
            .exceptionHandling(exceptions ->
                    exceptions.defaultAuthenticationEntryPointFor(
                            new LoginUrlAuthenticationEntryPoint("/login"),
                            new MediaTypeRequestMatcher(MediaType.TEXT_HTML)
                    ));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain applicationChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                    .requestMatchers(
                            "/login", "/error", "/css/**").permitAll()
                    .anyRequest().authenticated()
            )
            .formLogin(form -> form
                    .loginPage("/login")
                    .loginProcessingUrl("/login")
                    .failureUrl("/login?error")
                    .permitAll()
            );

        return http.build();
    }
}
~~~

Chain Authorization Server đứng trước chain ứng dụng. Chain ứng dụng không khai báo securityMatcher nên nhận các request còn lại, bao gồm /login, /oauth2/consent và /callback. Trang consent GET yêu cầu người dùng đã đăng nhập. Form đăng nhập được xử lý trong application chain với CSRF protection. Form consent POST quay về endpoint giao thức /oauth2/authorize và được xử lý bởi configurer của Authorization Server; giữ nguyên chính sách CSRF dành cho endpoint này theo phiên bản đang dùng, không tắt CSRF toàn ứng dụng. Template có gửi CSRF token để tương thích với cấu hình kiểm thử có bật bộ lọc CSRF cho route đó.

Ví dụ sử dụng API configurer hiện đại của Spring Authorization Server. Nếu dự án dùng phiên bản cũ, cách khởi tạo configurer có thể khác; giữ nguyên hai nguyên tắc: matcher lấy từ configurer và Authorization Server chain có thứ tự trước chain dự phòng.

## 7. Cấu hình issuer và khóa ký cho môi trường lab

Đặt issuer công khai mà client sẽ tin cậy:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("http://localhost:9000")
            .build();
}
~~~

Authorization Server cần JWKSource để ký token. Với lab cục bộ, có thể sinh RSA key trong bộ nhớ:

~~~java
@Bean
JWKSource<SecurityContext> jwkSource() throws Exception {
    KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
    generator.initialize(2048);
    KeyPair pair = generator.generateKeyPair();

    RSAKey rsaKey = new RSAKey.Builder(
            (RSAPublicKey) pair.getPublic())
            .privateKey((RSAPrivateKey) pair.getPrivate())
            .keyID(UUID.randomUUID().toString())
            .build();

    JWKSet jwkSet = new JWKSet(rsaKey);
    return (selector, context) -> selector.select(jwkSet);
}

@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

Khóa sinh trong bộ nhớ sẽ thay đổi sau mỗi lần restart. Đây chỉ là cách đơn giản để chạy lab; token cũ có thể không còn xác minh được sau khi ứng dụng khởi động lại. Production phải dùng khóa bền vững được quản lý bằng keystore, KMS hoặc HSM, có kế hoạch rotation và backup. Không lưu private key trong database authorization hoặc log.

## 8. Tạo custom login page bằng Thymeleaf

Spring Security vẫn xử lý POST đăng nhập tại /login. Controller chỉ cung cấp trang GET:

~~~java
@Controller
public class LoginPageController {

    @GetMapping("/login")
    public String login(
            @RequestParam(name = "error", required = false) String error,
            Model model) {
        model.addAttribute("loginFailed", error != null);
        return "login";
    }
}
~~~

Tạo src/main/resources/templates/login.html:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Đăng nhập</title>
</head>
<body>
<main>
    <h1>Đăng nhập Portal Lab</h1>
    <p th:if="${loginFailed}" role="alert">
        Tên đăng nhập hoặc mật khẩu không hợp lệ.
    </p>

    <form th:action="@{/login}" method="post">
        <input type="hidden"
               th:name="${_csrf.parameterName}"
               th:value="${_csrf.token}">

        <label for="username">Tên đăng nhập</label>
        <input id="username" name="username"
               type="text" autocomplete="username" required>

        <label for="password">Mật khẩu</label>
        <input id="password" name="password"
               type="password" autocomplete="current-password" required>

        <button type="submit">Đăng nhập</button>
    </form>
</main>
</body>
</html>
~~~

Tên field username và password phải khớp với form login processing mặc định hoặc được cấu hình lại trong formLogin. CSRF token được đưa vào form bằng request attribute do Spring Security cung cấp. Thông báo lỗi không tiết lộ username có tồn tại hay không. Không tự xử lý mật khẩu trong controller; để AuthenticationManager và DaoAuthenticationProvider xác minh qua UserDetailsService cùng PasswordEncoder.

## 9. Tạo consent controller

Khi client yêu cầu scope chưa được người dùng chấp thuận, Authorization Server chuyển trình duyệt đến /oauth2/consent với client_id, state và các scope đang yêu cầu. Controller tra client và consent đã lưu để hiển thị tên ứng dụng cùng trạng thái quyền hiện có:

~~~java
@Controller
public class ConsentPageController {

    private final RegisteredClientRepository clients;
    private final OAuth2AuthorizationConsentService consents;

    public ConsentPageController(
            RegisteredClientRepository clients,
            OAuth2AuthorizationConsentService consents) {
        this.clients = clients;
        this.consents = consents;
    }

    @GetMapping("/oauth2/consent")
    public String consent(
            @RequestParam("client_id") String clientId,
            @RequestParam("state") String state,
            @RequestParam(name = "scope", required = false)
                    List<String> requestedScopes,
            Principal principal,
            Model model) {

        RegisteredClient client = clients.findByClientId(clientId);
        if (client == null) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST);
        }

        Set<String> approvedScopes = new HashSet<>();
        OAuth2AuthorizationConsent existing = consents.findById(
                client.getId(), principal.getName());

        if (existing != null) {
            existing.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .filter(authority -> authority.startsWith("SCOPE_"))
                    .map(authority -> authority.substring("SCOPE_".length()))
                    .forEach(approvedScopes::add);
        }

        model.addAttribute("clientId", clientId);
        model.addAttribute("clientName", client.getClientName());
        model.addAttribute("state", state);
        model.addAttribute("requestedScopes",
                requestedScopes == null ? List.of() : requestedScopes);
        model.addAttribute("approvedScopes", approvedScopes);

        return "consent";
    }
}
~~~

Consent được tra theo registered client ID nội bộ và username đã xác thực. Principal phải đến từ SecurityContext của phiên đăng nhập, không nhận username từ query parameter hoặc hidden field. Controller chỉ hiển thị consent; việc ghi nhận lựa chọn được Authorization Server xử lý khi form POST về authorization endpoint.

## 10. Tạo custom consent page

Tạo src/main/resources/templates/consent.html:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Chấp thuận quyền truy cập</title>
</head>
<body>
<main>
    <h1>Chấp thuận quyền truy cập</h1>
    <p>
        Ứng dụng
        <strong th:text="${clientName}">Portal Lab</strong>
        yêu cầu các quyền sau:
    </p>

    <form th:action="@{/oauth2/authorize}" method="post">
        <input type="hidden" name="client_id" th:value="${clientId}">
        <input type="hidden" name="state" th:value="${state}">
        <input type="hidden"
               th:name="${_csrf.parameterName}"
               th:value="${_csrf.token}">

        <fieldset>
            <legend>Quyền được yêu cầu</legend>
            <label th:each="scope : ${requestedScopes}">
                <input type="checkbox" name="scope"
                       th:value="${scope}" checked>
                <span th:text="${scope}">profile</span>
                <small th:if="${approvedScopes.contains(scope)}">
                    Đã chấp thuận trước đó
                </small>
            </label>
        </fieldset>

        <button type="submit"
                name="user_oauth_approval" value="true">
            Chấp thuận
        </button>
        <button type="submit"
                name="user_oauth_approval" value="false">
            Từ chối
        </button>
    </form>
</main>
</body>
</html>
~~~

Các checkbox gửi những scope người dùng thực sự chọn. Nút Chấp thuận gửi user_oauth_approval=true; nút Từ chối gửi false. Authorization Server xử lý POST tại /oauth2/authorize, đối chiếu client và state với request ban đầu rồi cập nhật consent service. Không tạo controller POST riêng để tự ghi consent nếu không có yêu cầu mở rộng giao thức; việc đó dễ bỏ qua xác thực state, client và quy trình authorization của framework.

Trong giao diện production, giải thích rõ ý nghĩa từng scope, tránh chỉ hiển thị tên kỹ thuật khó hiểu. Scope nhạy cảm cần mô tả dữ liệu hoặc hành động mà ứng dụng sẽ được phép truy cập. Không mặc định chấp thuận mọi scope mà không cho người dùng lựa chọn.

## 11. Thêm callback lab để quan sát authorization code

Để hoàn thành luồng trong cùng ứng dụng, tạo một callback chỉ dành cho lab. Route này được chain ứng dụng bảo vệ bằng phiên đăng nhập:

~~~java
@Controller
public class LabCallbackController {

    @GetMapping("/callback")
    public String callback(
            @RequestParam("code") String code,
            @RequestParam("state") String state,
            Model model) {
        model.addAttribute("code", code);
        model.addAttribute("state", state);
        return "callback";
    }
}
~~~

Template callback.html có thể hiển thị code và state để người học copy sang bước đổi token:

~~~html
<!DOCTYPE html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
    <meta charset="UTF-8">
    <title>Authorization callback</title>
</head>
<body>
<h1>Authorization thành công</h1>
<p>Code: <code th:text="${code}"></code></p>
<p>State: <code th:text="${state}"></code></p>
</body>
</html>
~~~

Đây là callback phục vụ quan sát trong lab, không phải cách lưu authorization code cho ứng dụng thật. Client production phải kiểm tra state, xử lý callback an toàn và đổi code ở backend hoặc trong public client theo mô hình bảo mật phù hợp. Không ghi code vào application log hoặc analytics.

## 12. Chạy thử authorization code flow với PKCE

Khởi động database, chạy Flyway và khởi động ứng dụng. Kiểm tra các điều kiện sau trước khi mở trình duyệt:

- Database có các bảng users, authorities và ba bảng OAuth.
- Tài khoản alice được tạo với password đã mã hóa.
- portal-client được lưu trong oauth2_registered_client.
- JWK Set endpoint có thể trả public key.
- Issuer là http://localhost:9000.

Sử dụng test vector RFC 7636 để chạy lab lặp lại:

~~~text
code_verifier:
dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk

code_challenge_method:
S256

code_challenge:
E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM
~~~

Mở authorization request sau trong trình duyệt:

~~~text
http://localhost:9000/oauth2/authorize?response_type=code&client_id=portal-client&redirect_uri=http%3A%2F%2Flocalhost%3A9000%2Fcallback&scope=openid%20profile%20orders.read&state=lab-state-001&code_challenge=E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM&code_challenge_method=S256
~~~

Trình duyệt được chuyển đến trang login. Đăng nhập bằng tài khoản alice và mật khẩu local-only-password. Sau đăng nhập, server tiếp tục authorization request và chuyển đến consent page. Chọn scope muốn cấp rồi nhấn Chấp thuận. Server redirect về /callback với authorization code và state. Xác nhận state nhận lại bằng lab-state-001.

Đổi code lấy token bằng curl:

~~~bash
curl --user portal-client:local-only-secret \
  --header "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "grant_type=authorization_code" \
  --data-urlencode "code=PASTE_AUTHORIZATION_CODE_HERE" \
  --data-urlencode "redirect_uri=http://localhost:9000/callback" \
  --data-urlencode "code_verifier=dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk" \
  http://localhost:9000/oauth2/token
~~~

Trên Windows PowerShell, gọi curl.exe để tránh alias curl của PowerShell 5.1:

~~~powershell
curl.exe --user "portal-client:local-only-secret" --header "Content-Type: application/x-www-form-urlencoded" --data-urlencode "grant_type=authorization_code" --data-urlencode "code=PASTE_AUTHORIZATION_CODE_HERE" --data-urlencode "redirect_uri=http://localhost:9000/callback" --data-urlencode "code_verifier=dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk" http://localhost:9000/oauth2/token
~~~

Response thành công có access_token và, với scope openid, ID token. Tùy cấu hình token, response cũng có thể chứa refresh_token. Không đưa response token vào ticket, log hoặc ảnh chụp chia sẻ.

## 13. Xác minh dữ liệu JDBC

Kiểm tra client registration:

~~~sql
SELECT client_id,
       client_authentication_methods,
       authorization_grant_types,
       redirect_uris,
       scopes
FROM oauth2_registered_client
WHERE client_id = 'portal-client';
~~~

Kiểm tra consent đã được lưu cho alice:

~~~sql
SELECT principal_name, authorities
FROM oauth2_authorization_consent
WHERE registered_client_id = (
    SELECT id
    FROM oauth2_registered_client
    WHERE client_id = 'portal-client'
)
AND principal_name = 'alice';
~~~

Kiểm tra metadata authorization mà không đọc các cột chứa giá trị token:

~~~sql
SELECT principal_name,
       authorization_grant_type,
       authorized_scopes,
       authorization_code_issued_at,
       authorization_code_expires_at
FROM oauth2_authorization
WHERE principal_name = 'alice'
  AND authorization_code_issued_at IS NOT NULL
ORDER BY authorization_code_issued_at DESC;
~~~

Schema OAuth2Authorization có các cột chứa authorization code, access token, refresh token và ID token. Không SELECT hoặc xuất các cột *_value trong báo cáo vận hành. Khi kiểm tra persistence, chỉ cần metadata như principal, grant type, scope và thời gian phát hành/hết hạn.

Khởi động lại ứng dụng rồi xác nhận portal-client và consent vẫn còn trong database. Nếu dùng JWKSource sinh khóa trong bộ nhớ của lab, token đã phát hành trước khi restart có thể không xác minh được vì khóa ký đã thay đổi; điều đó không có nghĩa JDBC authorization hoặc consent bị mất.

## 14. Các bài kiểm tra bổ sung

Sau luồng thành công, thực hiện các tình huống sau:

| Tình huống | Thao tác | Kết quả cần quan sát |
|---|---|---|
| Sai mật khẩu | Đăng nhập alice bằng mật khẩu sai | Trang login hiển thị thông báo chung, không tiết lộ tài khoản |
| Từ chối consent | Chọn Từ chối | Không phát authorization code; client nhận lỗi authorization |
| Consent đã lưu | Gửi lại authorization request với cùng client và scope đã chấp thuận | Server có thể bỏ qua consent page cho các scope đã được chấp thuận |
| Scope mới | Thêm một scope chưa được chấp thuận vào request | Consent page yêu cầu người dùng xem và chấp thuận quyền mới |
| Sai PKCE verifier | Đổi code với verifier khác | Token endpoint trả invalid_grant |
| Replay code | Gửi lại authorization code đã đổi | Token endpoint từ chối lần đổi tiếp theo |
| Restart server | Khởi động lại ứng dụng | Client và consent vẫn tồn tại trong JDBC |
| User chưa đăng nhập | Mở authorization request trong phiên mới | Server chuyển đến custom login page |

Để chạy lại consent từ đầu trong database lab, dùng một user thử nghiệm mới hoặc xóa consent của đúng client và user bằng thao tác quản trị có kiểm soát. Không xóa toàn bộ bảng authorization hoặc consent ở môi trường dùng chung.

## 15. Lỗi thường gặp và cách xử lý

**Không tìm thấy bảng khi khởi động:** Xác nhận Flyway đã chạy migration và schema đúng với phiên bản Spring Authorization Server. Kiểm tra datasource đang trỏ đến database/schema nào. Không chữa lỗi bằng cách bật tạo bảng tùy ý khi ứng dụng chạy.

**Không xác thực được client secret:** Kiểm tra client_id, phương thức CLIENT_SECRET_BASIC, prefix encoder và secret đã mã hóa trong RegisteredClient. Đảm bảo client không gửi secret đồng thời ở header và body.

**Không đăng nhập được người dùng:** Kiểm tra bảng users và authorities, PasswordEncoder, cột enabled và query của JdbcUserDetailsManager. Không lưu mật khẩu raw.

**Consent page không được gọi:** Kiểm tra client có requireAuthorizationConsent(true), configurer đã đặt consentPage("/oauth2/consent") và request đã đến Authorization Server chain. Nếu consent đã được lưu cho các scope, server có thể không yêu cầu người dùng chấp thuận lại.

**POST consent bị 403:** Kiểm tra CSRF token trong form, session cookie và chain xử lý POST /oauth2/authorize. Không tắt CSRF toàn ứng dụng. Xác nhận endpoint POST được xử lý bởi Authorization Server configurer.

**Consent không được lưu:** Kiểm tra OAuth2AuthorizationConsentService bean có phải JdbcOAuth2AuthorizationConsentService và bảng oauth2_authorization_consent đã được migration. Kiểm tra principal trong phiên đăng nhập có đúng user đã chấp thuận.

**Authorization code không đổi được:** Kiểm tra client authentication, redirect_uri giống hệt, code chưa hết hạn hoặc đã được sử dụng, và code_verifier đúng với challenge. Không dùng lại code từ lần chạy trước.

## 16. Hoàn thành lab

- [ ] PostgreSQL chạy và Flyway áp dụng schema user cùng ba bảng OAuth.
- [ ] RegisteredClientRepository dùng JdbcRegisteredClientRepository.
- [ ] OAuth2AuthorizationService dùng JdbcOAuth2AuthorizationService.
- [ ] OAuth2AuthorizationConsentService dùng JdbcOAuth2AuthorizationConsentService.
- [ ] UserDetailsService dùng JdbcUserDetailsManager và mật khẩu được mã hóa.
- [ ] Người dùng đăng nhập qua custom Thymeleaf login page.
- [ ] Client yêu cầu consent và hiển thị custom consent page.
- [ ] Người dùng có thể chấp thuận hoặc từ chối scope.
- [ ] Authorization code flow với PKCE đổi được code lấy token.
- [ ] Client registration và consent còn tồn tại sau khi restart ứng dụng.

Trong production, thay khóa ký tạm bằng khóa bền vững, quản lý secret bên ngoài source code, bật HTTPS, cấu hình cookie phiên an toàn, kiểm soát quyền truy cập database, backup và giám sát migration. Lab này hoàn tất phần kết nối JDBC, đăng nhập tùy chỉnh và consent page; các chính sách vận hành khóa và bảo vệ hạ tầng cần được triển khai theo môi trường thực tế.
