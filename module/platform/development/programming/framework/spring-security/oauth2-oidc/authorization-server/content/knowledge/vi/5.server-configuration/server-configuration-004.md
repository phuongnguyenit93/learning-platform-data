# Cấu hình theo Java DSL và thuộc tính Spring Boot

## 1. Mục tiêu và phạm vi

Khi triển khai **OAuth 2.0/OpenID Connect Authorization Server** bằng **Spring Security** và **Spring Authorization Server** trong ứng dụng **Spring Boot**, hai cách cấu hình thường xuất hiện cạnh nhau:

- **Java DSL**: mô tả cách bảo vệ HTTP request, gắn các bộ lọc giao thức OAuth 2.0/OIDC, định nghĩa security filter chain, bật OIDC và mở rộng hành vi của Authorization Server.
- **Thuộc tính Spring Boot** trong <code>application.yml</code>/<code>application.properties</code>: cung cấp giá trị cấu hình theo môi trường, chẳng hạn HTTP port, thông tin client đăng ký và một số thiết lập được Spring Boot hỗ trợ tự động cấu hình.

Hai cách phục vụ những phần khác nhau của hệ thống. Hiểu ranh giới này giúp tránh các lỗi: đã khai báo client nhưng token endpoint không hoạt động, đã bật filter OAuth nhưng thiếu kho client, thay đổi issuer nhưng metadata không nhất quán, hoặc tạo bean thủ công làm cấu hình từ YAML không còn có hiệu lực như dự định.

Sau bài học, bạn có thể:

1. Chọn đúng chỗ cấu hình cho filter chain, OAuth/OIDC endpoints, registered clients, token service, khóa ký và issuer.
2. Đọc một cấu hình Spring Boot và biết thuộc tính nào thực sự dành cho Authorization Server.
3. Lắp ghép ví dụ chạy bằng **Java DSL + Boot properties** với luồng Authorization Code/OIDC.
4. Thay cấu hình minh họa trong bộ nhớ bằng thành phần lưu trữ bền vững và quản lý khóa ở production.
5. Kiểm thử cấu hình sau khi thay đổi profile, URL công khai, client hoặc phiên bản framework.

**Ví dụ xuyên suốt:** Một Authorization Server được công bố tại <code>https://auth.example.com</code>; ứng dụng web <code>portal-web</code> dùng Authorization Code để đăng nhập OIDC và xin scope <code>orders.read</code> khi gọi Orders API. Phần minh họa dùng quy ước API của **Spring Boot 3.x và các phiên bản Spring Authorization Server tương thích với <code>HttpSecurity.with(...)</code>**. Các thuộc tính và phương thức có thể thay đổi theo phiên bản; khi nâng cấp phải đối chiếu tài liệu và metadata cấu hình của đúng bản đang chạy.

## 2. Bản đồ trách nhiệm của các lớp cấu hình

~~~mermaid
flowchart TB
    ENV["application.yml / environment / secret manager"]
    BOOT["Spring Boot property binding và auto-configuration"]
    JAVA["Java @Configuration / SecurityFilterChain / DSL"]
    AS["Spring Authorization Server filters và services"]
    DATA["RegisteredClientRepository / AuthorizationService / ConsentService"]
    KEY["JWKSource / JwtDecoder / AuthorizationServerSettings"]
    WEB["HTTP request đến OAuth 2.0 / OIDC endpoints"]
    ENV --> BOOT
    BOOT --> JAVA
    BOOT --> DATA
    JAVA --> AS
    DATA --> AS
    KEY --> AS
    WEB --> AS
~~~

Sơ đồ mô tả **các quan hệ cấu hình**, không có nghĩa toàn bộ bean đều được Spring Boot tạo tự động từ YAML. Trong nhiều dự án, nhóm phát triển phải tự định nghĩa khóa ký, kho dữ liệu và chính sách bảo mật phù hợp.

| Nhu cầu | Nơi nên cấu hình | Ghi chú |
| --- | --- | --- |
| Chọn những URL thuộc Authorization Server | <code>OAuth2AuthorizationServerConfigurer</code> trong Java DSL | Ưu tiên <code>getEndpointsMatcher()</code>. |
| Đăng ký endpoint bảo mật và đăng nhập | <code>SecurityFilterChain</code> với <code>HttpSecurity</code> | Có thể tách chain AS và chain Web. |
| Bật các endpoint OIDC | <code>authorizationServer.oidc(...)</code> | Không mặc nhiên được bật chỉ vì có scope <code>openid</code>. |
| Đăng ký client, grant, redirect URI, scope | Boot properties **hoặc** bean <code>RegisteredClientRepository</code> | Không duy trì hai nguồn đăng ký độc lập vô tình trùng client. |
| Chọn issuer URL và tùy chỉnh endpoint path | <code>AuthorizationServerSettings</code> (hoặc cơ chế thuộc tính được phiên bản Boot hỗ trợ) | Giá trị phải phù hợp URL công khai. |
| Tạo, bảo quản, xoay khóa ký | <code>JWKSource&lt;SecurityContext&gt;</code> / kho khóa | Không để private key trong YAML công khai hoặc sinh khóa mới mỗi lần restart ở production. |
| Lưu authorization code, refresh token, consent | <code>OAuth2AuthorizationService</code>, <code>OAuth2AuthorizationConsentService</code> | Nên dùng lưu trữ bền vững khi vận hành thực tế. |
| Tùy chỉnh claim, audience, thời hạn/token format | Java beans như <code>OAuth2TokenCustomizer</code>, <code>TokenSettings</code> | Áp dụng chính sách phát hành token rõ ràng. |
| Port, TLS/proxy, profile, mức logging | Thuộc tính Spring Boot và hạ tầng | Phải phối hợp proxy và cấu hình issuer. |

## 3. Chuẩn bị ứng dụng và các dependency

Trong Spring Boot, dự án cần có thư viện Spring Security và Spring Authorization Server tương thích. Với các bản Spring Boot 3.x cung cấp starter tương ứng, có thể bắt đầu bằng:

~~~xml
<!-- Maven: Boot dependency management quản lý version tương thích. -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-authorization-server</artifactId>
</dependency>
~~~

Nếu dùng Gradle:

~~~groovy
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-oauth2-authorization-server")
}
~~~

Không trộn version Spring Security/Spring Authorization Server một cách tùy ý với dependency management của Boot: sai phiên bản có thể dẫn đến lỗi phương thức DSL hoặc thiếu bean. Một số phiên bản Boot/framework có cách đóng gói starter và API khác nhau; ví dụ trong bài dùng nhóm API Java DSL nêu ở phần 1.

Tối thiểu cần có các thành phần:

- **SecurityFilterChain cho Authorization Server** và chain xử lý đăng nhập tương tác.
- **RegisteredClientRepository**: nơi tìm client hợp lệ, grant, redirect URI và scope.
- **OAuth2AuthorizationService**: lưu trạng thái authorization, authorization code và token liên quan.
- **OAuth2AuthorizationConsentService**: lưu consent nếu dùng tính năng này.
- **JWKSource** và các thành phần JWT phù hợp để ký/kiểm tra ID Token hoặc JWT access token.
- **AuthorizationServerSettings** cho issuer và endpoint settings.
- **User authentication** nếu có Authorization Code/OIDC với người dùng đăng nhập.

Một số bean có thể được framework/Boot cung cấp tùy classpath và các điều kiện auto-configuration; không giả định mọi hệ thống sẽ tự có đủ thành phần chỉ nhờ thêm dependency.

## 4. Cấu hình client bằng thuộc tính Spring Boot

### 4.1. Ví dụ <code>application.yml</code>

Một số dòng <code>spring.security.oauth2.authorizationserver.client</code> có thể giúp Boot tạo cấu hình registered client khi điều kiện auto-configuration được thỏa mãn:

~~~yaml
server:
  port: 9000
  forward-headers-strategy: framework

spring:
  security:
    oauth2:
      authorizationserver:
        client:
          portal-web:
            registration:
              client-id: portal-web
              # Giá trị môi trường là hash đã mã hóa dạng {bcrypt}...
              client-secret: "${PORTAL_CLIENT_SECRET_HASH}"
              client-authentication-methods:
                - client_secret_basic
              authorization-grant-types:
                - authorization_code
                - refresh_token
              redirect-uris:
                - https://portal.example.com/login/oauth2/code/portal-web
              post-logout-redirect-uris:
                - https://portal.example.com/
              scopes:
                - openid
                - profile
                - orders.read
            require-authorization-consent: true
~~~

Đây là ví dụ **confidential web client** có khả năng bảo vệ client secret ở backend. Với ứng dụng trình duyệt hoặc mobile là **public client**, không nhúng client secret vào frontend; cần đăng ký phương thức xác thực và chính sách PKCE phù hợp thay vì dùng cấu hình confidential client này.

Ý nghĩa của những nhánh quan trọng:

| Thuộc tính | Vai trò |
| --- | --- |
| <code>client.portal-web</code> | Khóa đăng ký trong cấu hình Boot; không nhất thiết là giá trị <code>client-id</code>. |
| <code>registration.client-id</code> | Định danh client gửi tới OAuth 2.0 endpoint. |
| <code>registration.client-secret</code> | Secret **đã được mã hóa phù hợp PasswordEncoder**, ví dụ chuỗi có tiền tố <code>{bcrypt}</code>. Client thực gửi secret gốc. |
| <code>registration.client-authentication-methods</code> | Cách xác thực client được chấp nhận, ví dụ <code>client_secret_basic</code>. |
| <code>registration.authorization-grant-types</code> | Những grant client được phép dùng; không cấp phép mọi loại grant chỉ vì client gửi yêu cầu. |
| <code>registration.redirect-uris</code> | Danh sách redirect URI được đăng ký chính xác; tránh wildcard hoặc chuyển hướng tùy ý. |
| <code>registration.scopes</code> | Phạm vi client có thể xin; scope thực tế được cấp còn phụ thuộc chính sách/consent. |
| <code>require-authorization-consent</code> | Yêu cầu user consent khi phù hợp với luồng và chính sách server. |

**Lưu ý về version:** Đây là hình dạng thuộc tính thường gặp trong Spring Boot có tích hợp Spring Authorization Server. Hãy kiểm tra metadata cấu hình của đúng phiên bản để xác nhận tên, vị trí và phạm vi hỗ trợ của từng thuộc tính, đặc biệt các tùy chọn nâng cao như client settings và token settings. Không suy rằng mọi setter trong <code>RegisteredClient</code> đều có một khóa YAML tương đương.

### 4.2. Thế nào là một client secret an toàn?

<code>PORTAL_CLIENT_SECRET_HASH</code> phải là giá trị đã mã hóa theo bộ mã hóa password mà Authorization Server dùng, chẳng hạn <code>{bcrypt}$2a$...</code>. Từ <code>{bcrypt}</code> giúp một <code>DelegatingPasswordEncoder</code> phổ biến biết cách đối chiếu. Không đưa client secret thô, secret sản xuất hoặc khóa ký private vào Git.

Đối với local demo, có thể thấy ví dụ <code>{noop}dev-secret</code> trong tài liệu hướng dẫn. Cách đó **chỉ thích hợp để học trong môi trường cô lập**, không dùng với client sản xuất. Với production, quản lý secret bằng môi trường triển khai, secret manager, phân quyền đọc tối thiểu và quy trình xoay vòng.

### 4.3. Nhận biết ba namespace OAuth trong Spring Boot

Các khóa dưới đây nghe giống nhau nhưng phục vụ **vai trò khác nhau**:

| Namespace | Ứng dụng đang đóng vai gì? |
| --- | --- |
| <code>spring.security.oauth2.authorizationserver.client...</code> | **Authorization Server**: đăng ký các client được cấp token. |
| <code>spring.security.oauth2.client.registration...</code> | **OAuth 2.0/OIDC Client**: ứng dụng đăng nhập bằng/ủy quyền với nhà cung cấp bên ngoài. |
| <code>spring.security.oauth2.resourceserver.jwt...</code> | **Resource Server**: API nhận và xác minh access token JWT. |

Ví dụ, thêm <code>spring.security.oauth2.client.registration.portal-web</code> vào Authorization Server không có nghĩa đã đăng ký client đó trong <code>RegisteredClientRepository</code>. Tương tự, khai báo <code>resourceserver.jwt.issuer-uri</code> chỉ giúp API tiêu thụ JWT theo cấu hình tương ứng, không tự dựng token endpoint.

## 5. Cấu hình SecurityFilterChain bằng Java DSL

### 5.1. Chain riêng cho endpoint OAuth 2.0/OIDC

Java DSL quyết định **request nào được xử lý bằng các OAuth2/OIDC filter**. Dưới đây là mẫu cấu hình cho phiên bản Spring Authorization Server hỗ trợ <code>OAuth2AuthorizationServerConfigurer.authorizationServer()</code> và <code>HttpSecurity.with(...)</code>:

~~~java
@Configuration
@EnableWebSecurity
public class AuthorizationServerSecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain authorizationServerSecurityFilterChain(HttpSecurity http)
            throws Exception {
        OAuth2AuthorizationServerConfigurer authorizationServer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

        http
            .securityMatcher(authorizationServer.getEndpointsMatcher())
            .with(authorizationServer, server ->
                server.oidc(Customizer.withDefaults()))
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated())
            .exceptionHandling(exceptions -> exceptions
                .defaultAuthenticationEntryPointFor(
                    new LoginUrlAuthenticationEntryPoint("/login"),
                    new MediaTypeRequestMatcher(MediaType.TEXT_HTML)))
            .oauth2ResourceServer(resourceServer ->
                resourceServer.jwt(Customizer.withDefaults()));

        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webSecurityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(authorize ->
                authorize.anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());
        return http.build();
    }
}
~~~

Các import được lược bỏ. Đoạn mã tập trung vào **bố trí DSL**; cần bổ sung những bean và dependency phù hợp với version dự án trước khi chạy.

**Giải thích:**

1. <code>@Order(1)</code> đặt chain Authorization Server trước chain Web. Spring Security chọn **chain khớp đầu tiên**; chain Web không có <code>securityMatcher</code> là fallback.
2. <code>getEndpointsMatcher()</code> bao phủ các endpoint do configurer Authorization Server quản lý. Không thay thế bằng <code>"/oauth2/**"</code> vì OIDC metadata/UserInfo/logout có thể nằm ngoài prefix đó.
3. <code>.with(authorizationServer, ...)</code> gắn những bộ lọc và thành phần giao thức vào chain; <code>.oidc(...)</code> bật hỗ trợ OIDC theo các điều kiện/configurer tương ứng.
4. <code>.authorizeHttpRequests(...authenticated())</code> là **quy tắc phân quyền HTTP**; kiểm tra client, authorization code, PKCE, token, consent vẫn do các bộ phận OAuth2/OIDC chuyên trách thực hiện. Không tự ý mở <code>/oauth2/token</code> bằng <code>permitAll()</code> để “sửa” lỗi client authentication.
5. Entry point chuyển **request HTML cần đăng nhập** sang <code>/login</code>; route này được chain Web xử lý bằng <code>formLogin</code>.
6. <code>oauth2ResourceServer().jwt()</code> có thể cần cho những endpoint OIDC dùng Bearer token như UserInfo. Nó đòi hỏi <code>JwtDecoder</code> phù hợp; không đồng nghĩa ứng dụng này đã có đầy đủ một business API.

Đoạn cấu hình không cố ý tắt CSRF toàn ứng dụng. Authorization Server configurer có xử lý CSRF thích hợp cho endpoint giao thức; chain Web vẫn cần bảo vệ CSRF khi dùng biểu mẫu đăng nhập dựa trên cookie/session.

### 5.2. Cấu hình một issuer cố định, nhất quán

~~~java
@Configuration
class AuthorizationServerMetadataConfig {
    @Bean
    AuthorizationServerSettings authorizationServerSettings() {
        return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .build();
    }
}
~~~

<code>issuer</code> là định danh phát hành token, được client và Resource Server dùng để xác minh <code>iss</code>, thường cũng xuất hiện trong discovery metadata. Nó **không phải** một địa chỉ tùy ý để đổi theo từng HTTP request.

Ví dụ hạ tầng:

~~~text
Browser / OAuth Client
      |
      | https://auth.example.com (TLS)
      v
Trusted reverse proxy / load balancer
      |
      | http://authorization-server:9000 (private network)
      v
Spring Boot Authorization Server
~~~

Ứng dụng có thể nghe cổng 9000 nội bộ nhưng công bố issuer <code>https://auth.example.com</code>. Khi chạy sau proxy:

- Dùng URL issuer **công khai và ổn định**; không để host nội bộ <code>localhost</code>, container name hoặc port riêng lẻ trở thành issuer sản xuất.
- Forwarded headers chỉ được tin tưởng khi proxy/hạ tầng **loại bỏ header giả từ client và tự đặt header đáng tin**; thiết lập <code>server.forward-headers-strategy</code> phải đi kèm cấu hình proxy.
- Đối chiếu <code>issuer</code> trong discovery metadata, <code>iss</code> của JWT, issuer URI cấu hình ở client/Resource Server và URL thực tế. Thay đổi issuer là một thay đổi về danh tính nhà phát hành, cần kế hoạch tương thích và chuyển đổi.
- Nếu tùy chỉnh đường dẫn endpoint, nên dùng cấu hình tập trung của <code>AuthorizationServerSettings</code> thay vì hard-code URL rải rác ở nhiều filter và client.

### 5.3. Cấu hình JWT decoder và JWKSource

Authorization Server phải có nguồn khóa ký phù hợp khi phát hành token dạng JWT. Khi bật OIDC, cấu hình <code>JwtDecoder</code> từ JWKSource là một mẫu phổ biến:

~~~java
@Bean
JwtDecoder jwtDecoder(JWKSource<SecurityContext> jwkSource) {
    return OAuth2AuthorizationServerConfiguration.jwtDecoder(jwkSource);
}
~~~

Bean trên **không tạo khóa**; dự án phải cung cấp <code>JWKSource&lt;SecurityContext&gt;</code> từ kho khóa hoặc cấu hình ký đáng tin cậy. Trong local demo, đôi khi có ví dụ tạo RSA key pair bằng <code>KeyPairGenerator</code> lúc ứng dụng khởi động. Không áp dụng cách đó nguyên trạng cho production: restart sẽ thay khóa, có thể khiến token đã phát hành không còn kiểm tra được. Nên lưu khóa an toàn, dùng <code>kid</code> rõ ràng, dự trù giai đoạn chồng lấn khóa cũ/mới khi xoay và chỉ công bố khóa **public** qua JWKS endpoint.

Không chèn private key dưới dạng literal trong ví dụ tài liệu, log hoặc nguồn cấu hình được commit. Token format, thuật toán ký và tập khóa được hỗ trợ phải được lựa chọn nhất quán với Resource Server.

### 5.4. Bật OIDC khác với bật OAuth 2.0 cơ bản

OAuth 2.0 Authorization Server có thể cấp access token mà không cung cấp tính năng đăng nhập OIDC. Khi bật <code>oidc(Customizer.withDefaults())</code>, hệ thống bổ sung các khả năng OIDC tương ứng như ID Token và các endpoint được hỗ trợ theo phiên bản, song vẫn phải:

- Đăng ký <code>openid</code> trong danh sách scope của client thích hợp.
- Chuẩn bị nguồn xác thực End-User và cách xác định subject (<code>sub</code>).
- Có khóa ký/decoder và các dịch vụ hỗ trợ endpoint OIDC cần thiết.
- Kiểm thử discovery metadata, authorization response và ID Token; không suy rằng “đã khai báo scope openid” là đủ để OIDC hoạt động.

OIDC chỉ nên mở những tính năng/endpoint thực sự dùng; ví dụ dynamic client registration không nên tự bật công khai nếu chưa có chính sách đăng ký và xác thực phù hợp.

## 6. Khi nào nên khai báo RegisteredClient bằng Java thay vì YAML?

Boot properties phù hợp cho **số ít client tĩnh**, thường ở môi trường thử nghiệm hoặc triển khai nhỏ. Khi hệ thống có nhiều client, quản trị theo tenant, tự động onboarding, thay đổi scope/redirect URI có kiểm soát hoặc cần lưu trữ bền vững, nên dùng <code>RegisteredClientRepository</code> rõ ràng.

Ví dụ cùng client <code>portal-web</code> được tạo bằng Java (đây là **phương án thay thế** cho đăng ký bằng YAML, không phải khai báo thêm song song):

~~~java
@Bean
RegisteredClientRepository registeredClientRepository(
        @Value("${PORTAL_CLIENT_SECRET_HASH}") String secretHash) {

    RegisteredClient portal = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("portal-web")
        .clientSecret(secretHash)
        .clientAuthenticationMethod(ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri("https://portal.example.com/login/oauth2/code/portal-web")
        .postLogoutRedirectUri("https://portal.example.com/")
        .scope(OidcScopes.OPENID)
        .scope(OidcScopes.PROFILE)
        .scope("orders.read")
        .clientSettings(ClientSettings.builder()
            .requireAuthorizationConsent(true)
            .build())
        .build();

    return new InMemoryRegisteredClientRepository(portal);
}
~~~

Các trường client ở trên tương ứng với phần <code>registration</code> của ví dụ YAML. Không lưu bản sao độc lập của cùng client ở nhiều nguồn dữ liệu vì khó xác định nơi nào là nguồn sự thật.

**Cảnh báo về vòng đời:** <code>InMemoryRegisteredClientRepository</code> phù hợp để demo. <code>UUID.randomUUID()</code> được tạo mỗi khi khởi động khiến ID bản ghi client thay đổi; trong hệ thống thật cần dùng ID bền vững, cấu hình/migration xác định và repository dùng database. Với ứng dụng có nhiều instance, dữ liệu client phải nhất quán giữa các node.

### 6.1. Các repository sử dụng JDBC

Spring Authorization Server cung cấp các triển khai JDBC cho phần dữ liệu cốt lõi:

~~~java
@Bean
RegisteredClientRepository registeredClientRepository(JdbcTemplate jdbc) {
    return new JdbcRegisteredClientRepository(jdbc);
}

@Bean
OAuth2AuthorizationService authorizationService(
        JdbcTemplate jdbc,
        RegisteredClientRepository registeredClients) {
    return new JdbcOAuth2AuthorizationService(jdbc, registeredClients);
}

@Bean
OAuth2AuthorizationConsentService authorizationConsentService(
        JdbcTemplate jdbc,
        RegisteredClientRepository registeredClients) {
    return new JdbcOAuth2AuthorizationConsentService(jdbc, registeredClients);
}
~~~

Đây là khung đăng ký bean, **chưa phải cấu hình database hoàn chỉnh**. Trước khi chạy phải chuẩn bị schema tương ứng với phiên bản thư viện và cơ chế migration; đăng ký bản ghi client ban đầu; cấu hình pool kết nối, index, transaction, backup, dọn dữ liệu hết hạn và quyền truy cập database. Hệ thống đa node phải chia sẻ trạng thái cần thiết và cùng tin cậy nguồn khóa, issuer, dữ liệu client.

Nếu đã tự khai báo một bean <code>RegisteredClientRepository</code>, cấu hình Boot tự động tạo repository từ properties **có thể back off theo các điều kiện auto-configuration**. Do đó, không tự kết luận rằng client trong YAML đã được đăng ký. Luôn kiểm tra repository thực tế trong runtime và bằng một yêu cầu OAuth 2.0 hợp lệ.

### 6.2. Cấu hình token bằng Java

Chính sách token thường thay đổi theo client và loại token, ví dụ:

~~~java
TokenSettings tokens = TokenSettings.builder()
    .accessTokenTimeToLive(Duration.ofMinutes(10))
    .refreshTokenTimeToLive(Duration.ofDays(7))
    .reuseRefreshTokens(false)
    .build();

RegisteredClient client = RegisteredClient.withId("stable-client-record-id")
    .clientId("portal-web")
    // Các trường xác thực/grant/redirect URI/scope cần thiết khác...
    .tokenSettings(tokens)
    .build();
~~~

Đây chỉ là đoạn trích minh họa: một <code>RegisteredClient</code> thực sự phải có các trường hợp lệ khác. Với hệ thống thực tế, thời hạn access/refresh token, việc xoay refresh token, thu hồi, replay detection và yêu cầu đăng nhập lại là **chính sách bảo mật**, không chỉ là thông số tùy tiện. Một thay đổi thời hạn token có thể ảnh hưởng tải dịch vụ, trải nghiệm người dùng và thời gian tồn tại của quyền truy cập bị lộ.

## 7. Auto-configuration và bean thủ công: phối hợp thế nào?

**Spring Boot auto-configuration hoạt động theo điều kiện**, gồm dependency có mặt, kiểu bean đã tồn tại và các property tương ứng. Việc thêm một bean do ứng dụng tự định nghĩa có thể khiến một bean mặc định từ Boot không còn được tạo. Điều này đặc biệt quan trọng khi kết hợp Java DSL với thuộc tính Boot.

### 7.1. Ba cách tổ chức thường gặp

| Cách tổ chức | Ưu điểm | Giới hạn/phù hợp |
| --- | --- | --- |
| Boot properties làm nguồn client tĩnh; Java DSL cấu hình chain/issuer/keys | Ngắn gọn, dễ đọc theo profile | Phải xác minh các điều kiện auto-configuration; phù hợp client ít biến động. |
| Java <code>RegisteredClientRepository</code> + Java DSL | Kiểm soát rõ đối tượng client và chính sách | Dễ phát sinh mã cấu hình thủ công; cần quản lý vòng đời ID và secret. |
| JDBC repository + Java DSL + properties môi trường | Phù hợp đa instance, quản trị client và vận hành dài hạn | Phải quản trị schema, migration, khóa, kết nối DB và dữ liệu nhạy cảm. |

Không có quy tắc “Java DSL luôn ghi đè toàn bộ YAML” hoặc “thuộc tính luôn ghi đè bean”. **Từng auto-configuration có điều kiện riêng.** Khi nghi ngờ, kiểm tra condition evaluation report (ví dụ bật debug khi chẩn đoán trong môi trường dev), danh sách bean thực tế và kết quả kiểm thử HTTP. Không dùng thử sai bằng cách tạo nhiều bean cùng loại rồi để Spring chọn ngẫu nhiên.

### 7.2. Ưu tiên thuộc tính theo môi trường

Spring Boot hỗ trợ cấu hình từ file, profile, biến môi trường, command-line arguments và nguồn cấu hình khác, với quy tắc ưu tiên riêng. Một cấu hình chia theo môi trường có thể:

~~~yaml
# application.yml: phần chung, không chứa secret.
server:
  port: 9000

logging:
  level:
    org.springframework.security: INFO
~~~

~~~yaml
# application-dev.yml: chỉ bật khi làm việc trên máy dev.
logging:
  level:
    org.springframework.security: DEBUG
~~~

Không nhúng dữ liệu nhạy cảm vào các profile được commit. Với issuer public và client registration, nên quản lý cấu hình từ nguồn thống nhất, tránh để profile hoặc biến môi trường làm lệch metadata, redirect URI và khóa ký giữa các instance.

## 8. Ranh giới giữa Java DSL, endpoint settings và application properties

Ba nhóm cấu hình dưới đây rất dễ bị trộn:

1. **<code>HttpSecurity</code>**: cấu hình bảo vệ một tập request, xác thực, exception handling, session, CSRF và filter chain.
2. **<code>AuthorizationServerSettings</code>**: cấu hình định danh issuer và đường dẫn endpoint của Authorization Server theo các API framework cung cấp.
3. **Spring Boot properties**: truyền giá trị môi trường và một số cấu hình được Boot hỗ trợ bind/auto-configure, trong đó có thông tin client registration ở những phiên bản tương ứng.

Ví dụ, thay đường dẫn token endpoint bằng <code>AuthorizationServerSettings</code> không đồng nghĩa chỉ cần sửa matcher hard-code ở chain. Khi dùng <code>getEndpointsMatcher()</code>, chain AS thường có thể theo sát cấu hình endpoint của AS hơn. Nhưng client vẫn phải gọi đúng URL mới và metadata phải phản ánh cấu hình chính thức.

Một ví dụ tùy chỉnh settings (chỉ dùng khi có yêu cầu sản phẩm rõ ràng):

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
        .issuer("https://auth.example.com")
        .tokenEndpoint("/oauth2/token")
        .build();
}
~~~

Trong ví dụ, <code>.tokenEndpoint("/oauth2/token")</code> là giá trị mặc định thường dùng, được ghi để minh họa API settings. Đổi thành đường dẫn khác cần cập nhật cả cấu hình proxy, client, discovery, monitoring và kiểm thử; không nên tùy chỉnh endpoint chỉ vì tiện đặt tên.

## 9. Xác minh ứng dụng đã được cấu hình đúng

### 9.1. Kiểm tra discovery và JWKS

Khi cấu hình OIDC và triển khai ở URL công khai, có thể kiểm tra:

~~~bash
# OIDC discovery; endpoint phải được bật và công bố đúng issuer.
curl -i https://auth.example.com/.well-known/openid-configuration

# JWKS: chỉ chứa thông tin khóa công khai.
curl -i https://auth.example.com/oauth2/jwks
~~~

Trong JSON discovery, kiểm tra <code>issuer</code>, <code>authorization_endpoint</code>, <code>token_endpoint</code>, <code>jwks_uri</code> và các khả năng khác. Những URL này phải dùng hostname/scheme công khai hợp lệ; issuer trong metadata phải trùng giá trị mà client/Resource Server tin cậy. Nếu đổi endpoint bằng <code>AuthorizationServerSettings</code>, kiểm tra lại metadata tương ứng.

Nếu JWKS trả 404, cần xác minh <code>JWKSource</code>, endpoint settings, filter chain và cấu hình framework. Nếu OIDC discovery trả 404, kiểm tra OIDC đã bật, chain AS có matcher đúng và phiên bản thư viện hỗ trợ endpoint mong muốn hay chưa.

### 9.2. Kiểm tra client registration bằng hành vi giao thức

Với web client <code>portal-web</code>, hãy thực hiện **Authorization Code + PKCE** từ một OAuth/OIDC client thật đã đăng ký hoặc bằng integration test:

~~~text
GET /oauth2/authorize
    ?response_type=code
    &client_id=portal-web
    &redirect_uri=https%3A%2F%2Fportal.example.com%2Flogin%2Foauth2%2Fcode%2Fportal-web
    &scope=openid%20orders.read
    &state=<secure-random-state>
    &code_challenge=<base64url-sha256-pkce-challenge>
    &code_challenge_method=S256
~~~

Đoạn trên **chỉ mô tả cấu trúc request**: các dấu xuống hàng để dễ đọc, giá trị state và PKCE phải được sinh thực, kiểm tra đúng, và client phải đáp ứng chính sách xác thực tương ứng. Luồng thành công cho thấy nhiều thành phần hoạt động cùng nhau: request vào AS chain, client được tra trong repository, redirect URI hợp lệ, người dùng đăng nhập, grant được chấp thuận và token được phát hành.

Nếu server trả <code>invalid_client</code>, <code>invalid_request</code>, <code>invalid_scope</code> hoặc lỗi redirect, đừng vội “nới” rule <code>permitAll()</code>. Đối chiếu trước client ID, phương thức xác thực, redirect URI, grant, scope, PKCE và chính sách đăng ký.

### 9.3. Ma trận kiểm thử cấu hình

| Trường hợp | Kết quả mong đợi |
| --- | --- |
| <code>/oauth2/authorize</code> với client đã đăng ký | AS chain xử lý, chuyển đăng nhập/consent khi phù hợp. |
| <code>/oauth2/token</code> với client secret sai | Trả lỗi giao thức/xác thực client thích hợp, không phát token. |
| Client xin scope không đăng ký | Không cấp quyền ngoài đăng ký/chính sách. |
| Redirect URI bị thay host/path | Yêu cầu bị từ chối theo quy tắc redirect URI. |
| Client dùng grant chưa được đăng ký | Yêu cầu không được chấp nhận. |
| OIDC discovery khi OIDC bật | Cung cấp metadata nhất quán với issuer/endpoint công khai. |
| JWKS endpoint | Công bố public keys phù hợp; không lộ private key. |
| JWT access/ID Token | Được ký bằng khóa hiện hành; <code>iss</code>, <code>aud</code>, thời hạn phù hợp. |
| Restart một instance | Khóa ký, repository và trạng thái cần thiết không bị thay đổi ngoài ý muốn. |
| Chạy nhiều instance | Client, authorization/consent và khóa có dữ liệu/nguồn thống nhất. |
| Đổi profile hoặc secret | Cấu hình runtime đúng nguồn ưu tiên, không log giá trị nhạy cảm. |
| Truy cập <code>/login</code> | Được chain đăng nhập xử lý, không bị chain AS “nuốt” request. |

Trong Spring Security Test, mock JWT authentication có thể **bỏ qua** xác minh chữ ký/issuer/audience; muốn kiểm thử decoder và khóa thật phải thực hiện integration test đi qua đường xác thực thực tế.

## 10. Chẩn đoán lỗi cấu hình thường gặp

### Lỗi A: Khai báo client trong YAML nhưng server báo <code>invalid_client</code>

**Triệu chứng:** <code>application.yml</code> có <code>spring.security.oauth2.authorizationserver.client...</code>, song token endpoint không nhận client.

**Kiểm tra:** Có bean <code>RegisteredClientRepository</code> thủ công khiến Boot back off không? Có đúng profile đang hoạt động? Thuộc tính có được bind theo phiên bản không? <code>client-id</code>, phương thức xác thực và secret đã khớp chưa? Client đã được lưu thực tế vào repository nào?

**Hướng xử lý:** Chọn một nguồn đăng ký authoritative, kiểm tra bean và bản ghi client runtime, sau đó thực hiện một request xác thực client thật. Không sửa bằng cách tắt client authentication.

### Lỗi B: <code>/oauth2/token</code> trả 404 hoặc HTML login page

**Nguyên nhân có thể:** Authorization Server chain chưa được gắn configurer, có chain bắt mọi request đặt trước, endpoint path đã đổi hoặc request rơi vào Web chain.

**Hướng xử lý:** Kiểm tra <code>@Order</code>, <code>securityMatcher(authorizationServer.getEndpointsMatcher())</code>, cấu hình endpoint và debug log của <code>FilterChainProxy</code>; giữ cấu hình AS và Web có trách nhiệm riêng.

### Lỗi C: Phát hành token được, nhưng OIDC discovery hoặc UserInfo không hoạt động

**Nguyên nhân có thể:** Chưa bật <code>oidc(...)</code>, thiếu bean JWT cần thiết, thiếu endpoint matcher, thiếu token phù hợp hoặc endpoint chưa được bật trong phiên bản/framework hiện tại.

**Hướng xử lý:** Kiểm tra OIDC configurer, metadata, JWKSource/JwtDecoder, scope <code>openid</code>, loại token và endpoint được cấu hình. Không giả định mọi endpoint OIDC luôn xuất hiện mặc định.

### Lỗi D: JWT có issuer là địa chỉ nội bộ thay vì URL công khai

**Nguyên nhân có thể:** Thiếu issuer cố định hoặc cấu hình proxy/forwarded headers không nhất quán.

**Hướng xử lý:** Thiết lập issuer công khai ổn định trong <code>AuthorizationServerSettings</code>; cấu hình proxy đáng tin và kiểm tra discovery + claim <code>iss</code> của JWT.

### Lỗi E: Sau khi restart, client báo token cũ không hợp lệ

**Nguyên nhân có thể:** Tạo cặp khóa mới mỗi lần khởi động; token ký bằng khóa cũ không còn được công bố.

**Hướng xử lý:** Lưu khóa an toàn và triển khai quy trình rotation với giai đoạn tồn tại song song public key cũ/mới. Kết hợp lưu trữ authorization/consent bền vững cho những luồng cần trạng thái qua restart.

### Lỗi F: Secret từ YAML không xác thực được

**Nguyên nhân có thể:** Nhập plaintext trực tiếp, thiếu tiền tố encoder phù hợp hoặc nhầm giữa secret gốc và secret đã hash.

**Hướng xử lý:** Xác định <code>PasswordEncoder</code> thực tế của Authorization Server; lưu hash có định dạng phù hợp, chuyển secret gốc cho confidential client qua cơ chế bí mật an toàn, kiểm tra cách gửi secret theo <code>client_authentication_method</code> đã đăng ký.

### Lỗi G: Bật CSRF disable trên toàn hệ thống để sửa lỗi token request

**Rủi ro:** Chain Web chứa form login dựa trên session/cookie có thể mất bảo vệ CSRF; lỗi token endpoint có thể đến từ client registration hoặc matcher, không phải CSRF.

**Hướng xử lý:** Dùng configurer AS xử lý endpoint OAuth2 phù hợp; giữ CSRF cho web login, chỉ miễn trừ có mục tiêu cho endpoint/mô hình xác thực được xác định rõ.

## 11. Chuyển từ demo sang production

Một phiên bản demo có thể dùng <code>InMemoryRegisteredClientRepository</code>, user giả lập và cặp khóa được tạo khi khởi động. Để vận hành thực tế:

1. **Issuer và URL công khai:** cố định qua cấu hình chính thức, dùng HTTPS, metadata nhất quán, bảo vệ cấu hình proxy và forwarded headers.
2. **Client lifecycle:** lưu client có ID ổn định; quản lý việc thêm/sửa redirect URI, grant, scope, trạng thái client và xoay secret bằng quy trình được kiểm soát.
3. **Token và consent persistence:** dùng database hoặc backend phù hợp, có backup/migration và xử lý dữ liệu hết hạn. Kiểm tra giao dịch và nhiều node.
4. **Ký token:** dùng private key được bảo vệ, hỗ trợ <code>kid</code>, rotation, thời gian chồng lấn khóa và kế hoạch khôi phục; không thay khóa chỉ vì restart.
5. **Xác thực người dùng:** kết nối kho người dùng/MFA/chính sách phiên đăng nhập; không đưa demo user/secret vào production.
6. **Giới hạn quyền:** hạn chế grant và scope theo client; Resource Server xác minh issuer, audience, thời hạn và quyền trên dữ liệu.
7. **Giám sát và audit:** theo dõi lỗi xác thực/issuance, độ trễ, trạng thái cơ sở dữ liệu và khóa; log an toàn, không ghi authorization code, access token, refresh token hoặc client secret nguyên văn.
8. **Nâng cấp:** khóa các phiên bản dependency tương thích, chạy integration tests khi đổi Boot/Security/Authorization Server và kiểm tra lại property binding cùng DSL.

## 12. Bài tập thực hành

Một công ty muốn triển khai Authorization Server dùng chung cho <code>customer-portal</code> và <code>billing-backend</code>:

1. <code>customer-portal</code> là confidential web client, cần Authorization Code và <code>openid profile invoices.read</code>. Hãy viết phần Boot properties tương ứng.
2. <code>billing-backend</code> là service client cần Client Credentials và <code>invoices.generate</code>. Hãy giải thích vì sao không nên thêm <code>openid</code> hoặc trông đợi End-User từ grant này.
3. Viết hai <code>SecurityFilterChain</code>: một chain cho các OAuth2/OIDC endpoints dùng <code>getEndpointsMatcher()</code>; một chain dành cho trang login.
4. Quyết định chuyển danh sách client từ YAML sang JDBC. Hãy chỉ ra bean repository cần tạo, dữ liệu cần migration và cách xác minh không còn hai nguồn client song song.
5. Ứng dụng chạy sau reverse proxy. Hãy xác minh issuer, discovery, JWKS và thông tin URL trong JWT đúng với <code>https://identity.example.com</code>.
6. Xây dựng ma trận kiểm thử cho client sai secret, sai redirect URI, thiếu scope, sai grant, khóa bị xoay, restart và hai instance dùng chung database.

**Gợi ý kiểm tra thiết kế:** Một giải pháp tốt giải thích rõ **cái gì được bind từ properties**, **cái gì phải tạo bằng bean/Java DSL**, **một request đi vào chain nào** và **cấu hình nào tồn tại bền vững qua restart**.

## 13. Tài liệu đối chiếu

- [Spring Authorization Server — Getting Started](https://docs.spring.io/spring-authorization-server/reference/getting-started.html): thành phần cấu hình tối thiểu và thiết lập Authorization Server.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): <code>OAuth2AuthorizationServerConfigurer</code>, các endpoint và tùy biến DSL.
- [Spring Authorization Server — Core Model / RegisteredClient](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): <code>RegisteredClient</code>, repository, authorization và consent.
- [Spring Boot — OAuth2 Authorization Server](https://docs.spring.io/spring-boot/reference/web/spring-security.html): tích hợp và auto-configuration của Spring Security/Authorization Server theo phiên bản Boot.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): nguồn thuộc tính, profile và thứ tự ưu tiên.
- [Spring Security — Servlet Configuration](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): <code>SecurityFilterChain</code>, <code>HttpSecurity</code> và nhiều chain.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): kiểm tra access token ở Resource Server.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): metadata và issuer của Authorization Server.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): discovery metadata dành cho OIDC.
