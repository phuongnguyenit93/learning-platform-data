# Hoàn thiện tài liệu kiến trúc, cấu hình, vận hành và xử lý sự cố

Bài thực hành này kết nối các phần của module thành một hệ thống Spring Authorization Server có thể triển khai và vận hành. Mục tiêu là hoàn thiện một bộ tài liệu kỹ thuật đủ để đội phát triển, bảo mật và vận hành cùng hiểu kiến trúc, biết cấu hình các thành phần, thực hiện các thao tác thường ngày và xử lý sự cố theo bằng chứng.

Kịch bản xuyên suốt là một Authorization Server phát hành OAuth 2.0 access token và OpenID Connect ID Token cho các ứng dụng web. Máy chủ chạy sau reverse proxy kết thúc TLS, dùng PostgreSQL để lưu client, authorization và consent, dùng khóa ký ổn định được quản lý riêng, và có thể mở rộng thành nhiều instance. Client dùng Authorization Code Flow với PKCE. Các tính năng như refresh token, revocation, introspection, UserInfo và logout được bật theo nhu cầu của hệ thống.

Tài liệu hoàn chỉnh cần có bốn phần liên kết chặt chẽ:

1. **Kiến trúc:** các thành phần, ranh giới tin cậy, luồng request và phụ thuộc dữ liệu.
2. **Cấu hình:** issuer, client, endpoint, database, khóa ký, proxy, TLS và quản lý secret.
3. **Vận hành:** triển khai, migration, health check, giám sát, backup, rotation và rollout.
4. **Xử lý sự cố:** triệu chứng, bằng chứng cần thu thập, nguyên nhân thường gặp và cách khôi phục an toàn.

## 1. Xác định mục tiêu và phạm vi hệ thống

Trước khi viết tài liệu, ghi rõ hệ thống phục vụ ai và hỗ trợ những giao thức nào. Một bộ tài liệu vận hành không nên ngầm hiểu rằng mọi tính năng OAuth/OIDC đều được bật.

Ví dụ phạm vi cho lab:

| Hạng mục | Quyết định của lab |
|---|---|
| Vai trò | OAuth 2.0 Authorization Server và OpenID Provider |
| Issuer | https://auth.example.com |
| Grant chính | Authorization Code |
| Bảo vệ authorization code | PKCE, ưu tiên S256 |
| Client | Confidential web client và public client nếu có |
| Token | JWT access token; ID Token khi OIDC được bật |
| Persistence | PostgreSQL cho RegisteredClient, OAuth2Authorization và consent |
| Session | HTTP session; Redis khi cần chia sẻ session giữa nhiều instance |
| Khóa ký | RSA hoặc EC theo thuật toán đã chọn, private key lưu trong secret manager/KMS |
| Ingress | Reverse proxy/load balancer kết thúc TLS |
| Quan sát | Application log, audit event, health check và metrics |
| Triển khai | Một instance ban đầu; có thể mở rộng ngang khi state được chia sẻ |

Đây là một profile minh họa. Khi hoàn thiện tài liệu cho môi trường thực, thay mọi giá trị ví dụ bằng domain, grant, database, token format, thuật toán, client type và chính sách thật. Nếu hệ thống không bật một endpoint, ghi rõ endpoint đó không thuộc phạm vi vận hành.

### Các câu hỏi cần trả lời trong tài liệu

- Issuer chính thức là gì? Có một issuer cố định hay nhiều issuer theo tenant?
- Client nào được đăng ký? Ai có quyền tạo, sửa, vô hiệu hóa hoặc xoay secret?
- Grant type, scope, redirect URI và client authentication method nào được cho phép?
- Access token và refresh token có thời hạn bao lâu? Có rotation hay reuse refresh token?
- Token là JWT hay opaque? Resource server xác minh chữ ký hay gọi introspection?
- Authorization, consent và client được lưu ở đâu? Có cần chia sẻ session giữa instance?
- Khóa ký được tạo, lưu, phân phối, rotation và thu hồi như thế nào?
- Ai được truy cập actuator, audit log, database và secret manager?
- Khi database, key store, Redis hoặc ingress lỗi, hệ thống degrade hoặc fail như thế nào?
- Bằng chứng nào cần giữ lại khi có sự cố bảo mật?

## 2. Mô tả kiến trúc và ranh giới tin cậy

Một topology triển khai tham khảo:

~~~text
                    Internet
                       |
              HTTPS auth.example.com
                       |
              +------------------+
              | Reverse Proxy /  |
              | Load Balancer    |
              | TLS termination  |
              +------------------+
                       |
             private network only
                       |
          +------------+------------+
          |                         |
  +---------------+         +---------------+
  | Authorization |         | Authorization |
  | Server node A |         | Server node B |
  +---------------+         +---------------+
          |                         |
          +------------+------------+
                       |
             +-------------------+
             | PostgreSQL        |
             | clients, grants,  |
             | consent, tokens   |
             +-------------------+
                       |
             +-------------------+
             | Secret Manager /  |
             | KMS / Key Store   |
             +-------------------+

       Optional shared session: Redis
       Monitoring: metrics, logs, audit events
~~~

Các thành phần có trách nhiệm khác nhau:

| Thành phần | Trách nhiệm | Ranh giới cần bảo vệ |
|---|---|---|
| Reverse proxy | TLS, host allowlist, header normalization, routing | Chỉ proxy được phép gọi backend; header client gửi phải bị xóa/ghi đè |
| Authorization Server | Authorization endpoint, token endpoint, metadata, OIDC | Security filter chain, client policy, issuer, token signing |
| PostgreSQL | Registered client, authorization, consent | Network isolation, credential riêng, backup và migration |
| Key store/KMS | Private signing key và key lifecycle | Least privilege, audit, rotation, khôi phục |
| Redis (nếu có) | Shared HTTP session hoặc cache | ACL, network isolation, TTL, failover |
| Resource Server | Xác minh access token và kiểm tra quyền | Issuer, audience, signature, expiry, scope |
| Monitoring | Health, metrics, logs, audit | Không thu thập token, secret hoặc dữ liệu cá nhân không cần thiết |

Không nên xem PostgreSQL là kho khóa ký mặc định. Dữ liệu authorization và private signing key có vòng đời, quyền truy cập và phương án khôi phục khác nhau. Tách quyền đọc/ghi dữ liệu ứng dụng khỏi quyền sử dụng private key giúp giới hạn tác động khi một thành phần bị xâm nhập.

### Luồng Authorization Code Flow

~~~text
Browser / OAuth2 Client
       |
       | 1. Authorization request + state + PKCE S256
       v
Authorization Server
       |
       | 2. Authenticate user / collect consent
       |
       | 3. Redirect with authorization code
       v
Registered redirect URI
       |
       | 4. Token request + code_verifier
       v
Token Endpoint
       |
       | 5. Validate client, code, redirect and PKCE
       | 6. Persist authorization and issue tokens
       v
Access Token + ID Token (+ refresh token by policy)
       |
       v
Resource Server / OIDC Client
~~~

Tài liệu phải làm rõ state và nonce được kiểm tra ở phía client/OIDC relying party; PKCE được ràng buộc với authorization code; redirect URI phải khớp cấu hình client; access token và ID Token có mục đích khác nhau. Không đưa token, code hoặc secret vào sơ đồ hoặc ví dụ log.

## 3. Hoàn thiện cấu hình Spring Authorization Server

Cấu hình được quản lý theo môi trường, với giá trị không nhạy cảm trong application configuration và secret được cấp qua secret manager hoặc cơ chế bảo mật của nền tảng. Không commit password database, client secret hoặc private key vào repository.

### Cấu hình ứng dụng

Ví dụ application-prod.yml:

~~~yaml
server:
  port: 9000
  forward-headers-strategy: framework
  shutdown: graceful

spring:
  datasource:
    url: jdbc:postgresql://postgres:5432/authorization
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 3000
      validation-timeout: 1000
  lifecycle:
    timeout-per-shutdown-phase: 30s

management:
  endpoint:
    health:
      probes:
        enabled: true
  endpoints:
    web:
      exposure:
        include: health,info,prometheus
~~~

Username và password datasource được cấp qua biến môi trường SPRING_DATASOURCE_USERNAME và SPRING_DATASOURCE_PASSWORD hoặc secret injection. Các con số pool chỉ là giá trị khởi đầu cho lab. Sizing thực tế phải dựa trên số instance, số kết nối tối đa của PostgreSQL, concurrency, thời gian query và giới hạn connection của nền tảng. Nếu có N instance với pool tối đa P, tổng kết nối lý thuyết có thể tiến gần N × P, chưa tính job và ứng dụng khác.

Không public toàn bộ actuator endpoint ra Internet. Chỉ expose endpoint cần thiết, bảo vệ bằng network policy hoặc authentication phù hợp, và giới hạn quyền đọc health detail. Health endpoint nên phục vụ nền tảng điều phối; metrics endpoint nên chỉ cho hệ thống giám sát nội bộ truy cập.

### Cấu hình issuer ổn định

Với Authorization Server có một domain công khai, cấu hình issuer tường minh:

~~~java
@Bean
AuthorizationServerSettings authorizationServerSettings() {
    return AuthorizationServerSettings.builder()
            .issuer("https://auth.example.com")
            .build();
}
~~~

Issuer là định danh của Authorization Server. Nó phải nhất quán trong metadata và token có claim iss. Không lấy Host hoặc X-Forwarded-Host tùy ý từ request làm issuer. Với multi-tenant, ánh xạ host đã được xác thực qua proxy vào một issuer nằm trong allowlist và kiểm tra tính nhất quán giữa metadata, token và endpoint.

Sau khi triển khai, xác minh discovery từ góc nhìn client:

~~~bash
curl -fsS https://auth.example.com/.well-known/openid-configuration
~~~

Nếu OIDC được bật, đối chiếu issuer, authorization_endpoint, token_endpoint, jwks_uri và userinfo_endpoint nếu có. Nếu hệ thống chỉ dùng OAuth metadata, xác minh endpoint metadata phù hợp với cấu hình.

### Cấu hình RegisteredClient

Đăng ký client bằng một quy trình quản trị có kiểm soát. Mỗi client cần có:

- Client ID ổn định và duy nhất.
- Client authentication method phù hợp với loại client.
- Grant type được phép.
- Redirect URI chính xác.
- Scope được cấp.
- Yêu cầu PKCE và consent theo chính sách.
- Token lifetime và refresh token policy.
- Chủ sở hữu, môi trường, ngày tạo, ngày hết hạn hoặc lịch review.

Ví dụ cấu hình client web confidential:

~~~java
RegisteredClient webClient = RegisteredClient
        .withId(UUID.randomUUID().toString())
        .clientId("web-portal")
        .clientSecret(passwordEncoder.encode(clientSecret))
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
                AuthorizationGrantType.AUTHORIZATION_CODE)
        .authorizationGrantType(
                AuthorizationGrantType.REFRESH_TOKEN)
        .redirectUri(
                "https://portal.example.com/login/oauth2/code/auth")
        .scope(OidcScopes.OPENID)
        .scope(OidcScopes.PROFILE)
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(true)
                .build())
        .tokenSettings(TokenSettings.builder()
                .accessTokenTimeToLive(Duration.ofMinutes(5))
                .refreshTokenTimeToLive(Duration.ofHours(8))
                .reuseRefreshTokens(false)
                .build())
        .build();
~~~

Đây là ví dụ tạo object để minh họa chính sách. Trong production, lưu RegisteredClient bằng repository bền vững như JdbcRegisteredClientRepository và thực hiện provisioning qua migration hoặc quy trình quản trị idempotent. Không tạo client ID ngẫu nhiên mới mỗi lần ứng dụng khởi động. Không dùng client_secret_basic cho public client; public client không có khả năng giữ secret bí mật và cần PKCE.

Một số repository và service JDBC có thể được cấu hình như sau:

~~~java
@Bean
RegisteredClientRepository registeredClientRepository(
        JdbcTemplate jdbcTemplate) {
    return new JdbcRegisteredClientRepository(jdbcTemplate);
}

@Bean
OAuth2AuthorizationService authorizationService(
        JdbcTemplate jdbcTemplate,
        RegisteredClientRepository registeredClients) {
    return new JdbcOAuth2AuthorizationService(
            jdbcTemplate, registeredClients);
}

@Bean
OAuth2AuthorizationConsentService authorizationConsentService(
        JdbcTemplate jdbcTemplate,
        RegisteredClientRepository registeredClients) {
    return new JdbcOAuth2AuthorizationConsentService(
            jdbcTemplate, registeredClients);
}
~~~

Các schema phải được cài đặt bằng migration được quản lý phiên bản. Dùng đúng schema tương ứng với phiên bản Spring Authorization Server đang chạy. Kiểm tra migration trên database trống và trên schema của phiên bản trước trước khi đưa vào production.

### Cấu hình SecurityFilterChain

Authorization Server endpoints và ứng dụng đăng nhập người dùng có thể cần hai filter chain với thứ tự rõ ràng. Mẫu sau minh họa cấu hình hiện đại; API configurer có thể khác theo phiên bản Spring Authorization Server đang pin, vì vậy cần đối chiếu với dependency đang dùng:

~~~java
@Bean
@Order(1)
SecurityFilterChain authorizationServerSecurityFilterChain(
        HttpSecurity http) throws Exception {

    OAuth2AuthorizationServerConfigurer authorizationServerConfigurer =
            OAuth2AuthorizationServerConfigurer.authorizationServer();

    http.securityMatcher(authorizationServerConfigurer.getEndpointsMatcher())
            .with(authorizationServerConfigurer, authorizationServer ->
                    authorizationServer.oidc(Customizer.withDefaults()))
            .authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated());

    return http.build();
}

@Bean
@Order(2)
SecurityFilterChain applicationSecurityFilterChain(
        HttpSecurity http) throws Exception {

    http.authorizeHttpRequests(authorize ->
                    authorize.anyRequest().authenticated())
            .formLogin(Customizer.withDefaults());

    return http.build();
}
~~~

Đây là khung minh họa, không phải cấu hình đầy đủ cho mọi hệ thống. Cần tích hợp authentication provider, user store, CSRF policy, exception handling và các endpoint public theo yêu cầu. Không vô hiệu hóa CSRF toàn ứng dụng chỉ để làm authorization request chạy được. Kiểm tra filter matcher để endpoint đăng nhập, error, static resource và health probe được xử lý theo chính sách.

### Khóa ký và JWKS

Tài liệu khóa cần ghi:

- Thuật toán và kích thước khóa được chấp nhận.
- Nơi private key được lưu và service identity được phép sử dụng.
- Cách public key được công bố qua JWKS.
- Quy tắc đặt kid, trạng thái active/next/retired.
- Thời gian overlap khi rotation.
- Thời gian giữ khóa cũ đủ để xác minh token còn hiệu lực.
- Quy trình emergency rotation và thu hồi khóa bị lộ.
- Quy trình backup/restore hoặc tái tạo khóa theo chính sách.

Không tạo RSA/EC key pair ngẫu nhiên mới mỗi lần ứng dụng khởi động. Việc đó làm token được ký trước đó không còn xác minh được sau restart. Trong production, lấy khóa từ KMS, HSM hoặc secret manager; giới hạn quyền sử dụng private key và audit mọi thao tác nhạy cảm. Chỉ public key mới được công bố trong JWKS.

## 4. Cấu hình reverse proxy và mạng

Giả sử Nginx là điểm nhận HTTPS trực tiếp từ client:

~~~nginx
server {
    listen 443 ssl;
    server_name auth.example.com;

    location / {
        proxy_pass http://authorization-server:9000;

        proxy_set_header Host auth.example.com;
        proxy_set_header Forwarded "";
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Host auth.example.com;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Forwarded-Port 443;
    }
}
~~~

Ví dụ giả định Nginx là proxy biên trực tiếp. Nếu có load balancer hoặc CDN phía trước, chỉ cấu hình real IP sau khi xác định CIDR của các hop được phép và header mà chúng tạo. Proxy biên phải xóa hoặc ghi đè forwarded headers do client gửi. Backend chỉ được phép nhận traffic từ proxy nội bộ đã xác định.

Các kiểm tra mạng cần ghi vào runbook:

- Security group/firewall chỉ cho phép ingress từ proxy.
- PostgreSQL chỉ cho phép kết nối từ application subnet.
- Redis chỉ cho phép kết nối từ các service cần dùng.
- Management port không mở ra Internet.
- TLS certificate có hostname phù hợp và được gia hạn trước hạn.
- DNS, load balancer health check và routing cùng trỏ đến endpoint dự kiến.

Nếu proxy rewrite path, mô tả chính xác prefix bên ngoài và context path bên trong. Kiểm tra discovery, redirect và JWKS để tránh URL bị thiếu hoặc lặp prefix.

## 5. Quản lý cấu hình theo môi trường

Tách cấu hình thành ba nhóm:

| Nhóm | Ví dụ | Nơi quản lý |
|---|---|---|
| Không nhạy cảm | Port, issuer, pool size, endpoint path, feature flag | Versioned config hoặc deployment config |
| Bí mật | DB password, client secret, API credential | Secret manager hoặc secret injection |
| Khóa mật mã | Private signing key, encryption key | KMS/HSM/keystore có kiểm soát quyền |

Không dùng cùng client secret, signing key hoặc database password giữa dev, test, staging và production. Không đưa secret vào Docker image, source control, command line có thể lưu trong shell history hoặc log pipeline.

Khi thay đổi cấu hình, ghi lại:

- Giá trị cũ và mới (secret chỉ ghi version/fingerprint, không ghi giá trị).
- Môi trường và instance bị ảnh hưởng.
- Người/automation thực hiện.
- Thời điểm hiệu lực.
- Kế hoạch rollback.
- Kiểm tra sau thay đổi.

Cấu hình issuer, signing algorithm, token lifetime, client redirect URI và grant type là cấu hình có tác động bảo mật. Chúng cần review và regression test tương ứng.

## 6. Triển khai và khởi động ứng dụng

Quy trình triển khai có thể chia thành các bước:

1. Kiểm tra image, commit SHA, dependency version và SBOM theo quy trình của tổ chức.
2. Xác minh secret reference và quyền truy cập KMS/secret manager.
3. Kiểm tra database connectivity và trạng thái migration.
4. Chạy migration theo một bước có kiểm soát trước khi rollout instance mới.
5. Khởi động instance và chờ readiness.
6. Xác minh discovery, JWKS và endpoint công khai.
7. Chạy smoke test với client kiểm thử.
8. Tăng traffic theo rollout strategy.
9. Theo dõi lỗi token, login, database pool, latency và audit event.
10. Hoàn tất rollout hoặc rollback theo tiêu chí đã định.

### Readiness và liveness

Liveness trả lời ứng dụng còn sống để tiếp tục chạy hay cần restart. Readiness trả lời instance có thể nhận traffic hay chưa. Không nên để một lỗi phụ thuộc tạm thời khiến liveness liên tục restart tất cả instance nếu restart không giải quyết được vấn đề.

Readiness có thể kiểm tra những dependency thiết yếu như datasource, tùy chính sách. Nếu PostgreSQL không sẵn sàng và Authorization Server không thể xử lý authorization/token, instance không nên nhận traffic. Tuy nhiên, thiết kế health indicator phải tránh tạo hiệu ứng dây chuyền khi database đang phục hồi.

Với Spring Boot Actuator, cấu hình health probes và endpoint phù hợp với orchestration platform. Giới hạn chi tiết health response để không tiết lộ host, schema, username hoặc cấu trúc nội bộ.

### Graceful shutdown

Bật graceful shutdown và đặt thời gian drain phù hợp. Trước khi dừng instance:

- Load balancer ngừng gửi request mới đến node.
- Request đang xử lý được phép hoàn tất trong giới hạn thời gian.
- Connection pool được đóng theo lifecycle của ứng dụng.
- Không xóa authorization/session dùng chung khi dừng node.
- Node mới phải sẵn sàng và có cùng issuer, database schema tương thích và signing key set cần thiết.

Authorization code và token phải dùng chung persistence/issuer/key configuration theo kiến trúc. Không phụ thuộc sticky session để che giấu việc trạng thái authorization chỉ lưu trong memory nếu hệ thống cần scale ngang.

## 7. Vận hành thường ngày

Runbook cần phân biệt thao tác thường ngày, thay đổi có rủi ro và sự cố.

| Tác vụ | Thực hiện | Xác minh sau thao tác |
|---|---|---|
| Kiểm tra dịch vụ | Health, readiness, synthetic login | Instance nhận traffic và endpoint hoạt động |
| Kiểm tra metadata | Đọc discovery và JWKS | Issuer, endpoint và public key đúng |
| Provision client | Quy trình quản trị đã review | Grant, redirect, scope và authentication method đúng |
| Vô hiệu hóa client | Disable/rotate credential theo quy trình | Client không thể lấy token mới |
| Kiểm tra database | Connection pool, slow query, replication/backup status | Không có connection exhaustion hoặc migration drift |
| Kiểm tra khóa | Active kid, JWKS, expiry và KMS audit | Token mới ký bằng key dự kiến; key cũ còn trong overlap |
| Kiểm tra audit | Login, consent, token failure và admin change | Sự kiện có correlation ID và không chứa secret |
| Kiểm tra capacity | CPU, memory, request rate, DB connections | Có headroom và không vượt quota |

### Provision và thu hồi client

Quy trình tạo client cần xác nhận danh tính chủ sở hữu, loại client, redirect URI, grant type, scope, phương thức xác thực, thời hạn và môi trường. Với confidential client, phát secret qua kênh an toàn một lần hoặc secret delivery mechanism. Chỉ lưu hash secret theo cơ chế được Spring Authorization Server hỗ trợ và chính sách nội bộ.

Khi thu hồi client:

1. Xác nhận client ID và chủ sở hữu.
2. Vô hiệu hóa hoặc xóa credential theo chính sách.
3. Thu hồi authorization/refresh token liên quan nếu yêu cầu.
4. Xác minh token mới không thể được cấp.
5. Xác minh resource server phản ánh revocation theo mô hình token (JWT hay opaque) và cache.
6. Lưu audit event, người thực hiện và lý do.

Với JWT access token đã phát hành, xóa client không tự động làm chữ ký token mất hiệu lực. Resource server có thể tiếp tục chấp nhận JWT cho đến khi token hết hạn nếu không có cơ chế revocation/denylist phù hợp. Tài liệu phải nêu rõ ranh giới này.

## 8. Giám sát, logging và audit

Giám sát cần trả lời ba câu hỏi: dịch vụ có sẵn sàng không, giao thức có hoạt động đúng không, và có hành vi bất thường nào cần điều tra không.

### Metrics

Theo dõi các nhóm chỉ số:

- HTTP request rate, latency và error rate theo endpoint.
- Số lượng authorization request thành công/thất bại.
- Token issuance và token endpoint failure theo error category.
- Login/consent failure và số lần client authentication thất bại.
- JVM heap, garbage collection, thread pool và CPU.
- HikariCP active/idle/pending connections và connection timeout.
- Database query latency, connection count, lock wait và replication lag nếu có.
- Redis latency, connection và eviction nếu dùng.
- KMS/key service latency và lỗi truy cập.
- Readiness, restart count và rollout status.

Tránh đưa client ID, username, token hoặc authorization code có cardinality cao vào metric label. Dùng metric tổng hợp và correlation ID trong log để điều tra chi tiết.

### Structured logging

Log nên có timestamp, severity, service name, environment, instance ID, trace/correlation ID, endpoint category và outcome. Ví dụ:

~~~json
{
  "timestamp": "2026-11-16T10:15:30Z",
  "level": "WARN",
  "service": "authorization-server",
  "environment": "production",
  "event": "token_request_rejected",
  "error": "invalid_grant",
  "client_id": "web-portal",
  "correlation_id": "req-7f2a"
}
~~~

Ví dụ không chứa code, token, secret hoặc cookie. Trong thực tế, chỉ log client ID nếu chính sách cho phép; username và subject thường cần giảm thiểu hoặc pseudonymize.

### Audit event

Audit tập trung vào sự kiện có ý nghĩa bảo mật:

- Client được tạo, cập nhật, vô hiệu hóa hoặc xoay secret.
- Người dùng đăng nhập thành công/thất bại.
- Consent được chấp thuận, từ chối hoặc thu hồi.
- Authorization code hoặc token request bị từ chối theo nhóm lỗi.
- Refresh token rotation/replay và revocation.
- Khóa ký chuyển trạng thái hoặc được rotation.
- Thay đổi issuer, endpoint hoặc security policy.
- Truy cập quản trị và thay đổi cấu hình.

Audit event cần có actor/service identity, action, target reference, outcome, timestamp và correlation ID. Không lưu token nguyên vẹn hoặc private key. Thiết lập retention, quyền truy cập, integrity protection và quy trình export theo chính sách.

## 9. Backup, phục hồi và tính sẵn sàng

Backup phải bao phủ dữ liệu cần để khôi phục hành vi của Authorization Server. Backup PostgreSQL mà không có kế hoạch khôi phục signing key có thể làm các token hiện hữu không xác minh được. Backup key mà không có authorization/client data cũng không đủ để khôi phục toàn bộ dịch vụ.

| Dữ liệu/phụ thuộc | Cần bảo vệ | Kiểm tra khôi phục |
|---|---|---|
| Registered clients | Client ID, grant, redirect, scope, secret hash và settings | Client được tìm lại và policy đúng |
| Authorizations | Code/token state và metadata còn hiệu lực | Token/introspection/revocation theo chính sách |
| Consents | Scope được người dùng chấp thuận | Consent được đọc lại và áp dụng |
| Signing key | Private key qua KMS/HSM backup policy; public key/JWKS metadata | Token cũ còn xác minh được khi key còn trusted |
| Application config | Issuer, endpoint, token policy và security settings | Instance mới có cấu hình nhất quán |
| Session store | Session còn hiệu lực nếu yêu cầu khôi phục | Người dùng được xử lý theo chính sách sau restore |
| Audit/log | Sự kiện cần điều tra và compliance | Có thể truy xuất theo retention |

Xác định RPO (mức mất dữ liệu chấp nhận được) và RTO (thời gian khôi phục mục tiêu). Chạy restore drill định kỳ trên môi trường cô lập. Kiểm tra migration, quyền database, issuer, key access, JWKS và smoke test sau khi khôi phục.

Không khôi phục snapshot production vào môi trường kém bảo vệ hơn mà không có quy trình xử lý dữ liệu nhạy cảm. Kiểm soát quyền truy cập và mã hóa backup tương đương dữ liệu gốc.

## 10. Rotation và thay đổi bảo mật

### Signing key rotation

Một quy trình rotation an toàn có overlap:

1. Tạo key mới trong KMS/HSM hoặc key manager.
2. Công bố public key mới trong JWKS với kid duy nhất.
3. Chờ các client/resource server refresh JWKS hoặc hết cache window.
4. Chuyển Authorization Server sang ký bằng key mới.
5. Giữ public key cũ đủ lâu để xác minh token cũ còn hiệu lực.
6. Sau khi hết token lifetime và overlap, ngừng công bố key cũ theo chính sách.
7. Xác minh token mới dùng key mới và token cũ được xử lý đúng.
8. Cập nhật audit record và tài liệu key inventory.

Nếu private key bị lộ, đây là emergency response: đánh giá token đã ký, ngừng sử dụng key bị ảnh hưởng, công bố trạng thái key mới, phối hợp resource server/client cập nhật trust và cân nhắc thu hồi token/session. Quy trình cụ thể phụ thuộc khả năng cache JWKS và token format.

### Client secret rotation

- Tạo secret mới và phát đến client qua kênh an toàn.
- Xác minh client đã chuyển sang secret mới.
- Vô hiệu hóa secret cũ sau thời gian overlap đã định.
- Kiểm tra authentication thất bại của secret cũ.
- Ghi nhận thời gian, chủ sở hữu và credential version.

Không giữ hai secret hợp lệ vô thời hạn nếu chính sách không cho phép. Nếu nền tảng không hỗ trợ hai secret đồng thời cho một client, lập lịch cutover và rollback cụ thể.

### Database migration và rolling deployment

Migration cần tương thích với phiên bản ứng dụng đang chạy trong giai đoạn rollout. Ưu tiên expand-and-contract:

1. Thêm schema mới theo cách phiên bản hiện tại vẫn hoạt động.
2. Deploy code có thể đọc/ghi schema cũ và mới khi cần.
3. Backfill dữ liệu và xác minh.
4. Chuyển traffic hoặc feature flag.
5. Sau khi không còn instance cũ, loại bỏ schema cũ trong release sau.

Không chạy migration phá hủy trước khi có backup và rollback plan. Với bảng authorization lớn, đánh giá lock duration, index build, transaction log và ảnh hưởng đến token endpoint.

## 11. Xử lý sự cố theo triệu chứng

Khi có incident, trước tiên xác định phạm vi: tất cả client hay một client, tất cả instance hay một node, authorization endpoint hay token endpoint, user login hay machine-to-machine. Ghi lại thời điểm bắt đầu, deployment/config change gần nhất, correlation ID và error category. Không thu thập token/secret nguyên vẹn.

| Triệu chứng | Nguyên nhân có thể | Bằng chứng cần xem | Hướng xử lý |
|---|---|---|---|
| Discovery trả issuer hoặc URL nội bộ | Issuer sai, forwarded header không được tin đúng, proxy rewrite sai | Metadata, AuthorizationServerSettings, ingress config | Khôi phục issuer công khai; sửa proxy header; xác minh từ mạng client |
| Redirect dùng HTTP | TLS termination hoặc forwarded proto sai | Location, X-Forwarded-Proto, proxy log | Chuẩn hóa header tại proxy tin cậy; kiểm tra TLS và filter strategy |
| invalid_client tăng đột ngột | Secret rotation lệch thời điểm, client auth method đổi | Client config version, auth failure category, rollout timeline | Đồng bộ credential; kiểm tra method; rotate theo cutover |
| invalid_grant tăng | Code hết hạn/replay, PKCE mismatch, redirect URI thay đổi | Error category, client fixture, token request metadata đã scrub | Kiểm tra client flow và clock; không log code/verifier |
| Token signature invalid | Key mismatch, JWKS cache, kid không tồn tại, thuật toán đổi | JWT header đã scrub payload, JWKS, key inventory | Kiểm tra key overlap và cache; phục hồi public key đúng |
| ID Token issuer mismatch | Issuer config thay đổi hoặc nhiều node khác config | Discovery, claim iss, instance config version | Đồng bộ issuer; rollback config không nhất quán |
| User không giữ được phiên | Cookie/SameSite, session store, session fixation hoặc proxy | Set-Cookie, browser trace, Redis/session metrics | Sửa cookie policy; kiểm tra shared session và domain/path |
| Consent lặp lại liên tục | Consent persistence không lưu/đọc được hoặc scope liên tục thay đổi | Consent row/service, client scope config | Khôi phục persistence; kiểm tra scope và client identity |
| Token endpoint timeout | DB pool cạn, lock, KMS latency hoặc thread starvation | Hikari metrics, DB slow query, KMS latency, thread dump | Giảm tải, khôi phục dependency; điều chỉnh pool sau khi tìm nguyên nhân |
| Một node phát token lỗi | Key/config/schema khác node còn lại | Instance version, active kid, migration level | Drain node lệch cấu hình; đồng bộ rollout |
| Revoked token vẫn được API chấp nhận | JWT self-contained còn hạn hoặc cache chưa hết TTL | Token type, resource server cache, revocation path | Áp dụng TTL ngắn/denylist/introspection theo threat model; không giả định JWT tự thu hồi |
| Health check flapping | Readiness phụ thuộc quá nhiều hoặc probe timeout | Probe response, dependency health, restart count | Tách liveness/readiness; điều chỉnh timeout và dependency policy |

### Quy trình triage

1. Xác định endpoint và nhóm người dùng/client bị ảnh hưởng.
2. Đối chiếu correlation ID với log của proxy, Authorization Server và dependency.
3. Kiểm tra release/config/key version tại thời điểm sự cố.
4. Xác minh issuer, metadata và JWKS từ góc nhìn bên ngoài.
5. Kiểm tra PostgreSQL pool, query latency, lock và migration.
6. Kiểm tra KMS/secret manager và trạng thái key.
7. Kiểm tra session store, cookie và proxy nếu sự cố liên quan browser login.
8. Chọn mitigation nhỏ nhất có thể đảo ngược: drain node lỗi, rollback config, khôi phục dependency hoặc tạm vô hiệu hóa client bị ảnh hưởng.
9. Chạy smoke test và xác nhận hành vi với client kiểm thử.
10. Ghi timeline, tác động, nguyên nhân gốc và hành động ngăn tái diễn.

Không xóa authorization hoặc consent hàng loạt để xử lý lỗi đăng nhập nếu chưa xác định nguyên nhân. Không rotate signing key tùy tiện khi token cũ còn hiệu lực; thay đổi này có thể làm mọi resource server không xác minh được token.

## 12. Thực hành capstone: hoàn thiện một bản triển khai

Thực hiện lab theo thứ tự. Dùng môi trường local hoặc staging cô lập, domain test và credential giả. Không thực hiện thao tác tạo/xóa dữ liệu trên production.

### Lab A — Viết architecture decision record

Tạo một ADR ngắn với:

- Mục tiêu và phạm vi OAuth/OIDC.
- Topology proxy, application, database, key manager và optional Redis.
- Issuer, grant type, token format và client type.
- Nơi lưu RegisteredClient, authorization, consent và session.
- Threat boundary và các giả định tin cậy.
- Quyết định về key rotation, refresh token và revocation.
- Những giới hạn còn lại và lý do chấp nhận.

**Kết quả mong đợi:** một sơ đồ kiến trúc và bảng quyết định có thể review, mỗi quyết định có lý do và tác động vận hành.

### Lab B — Chuẩn hóa cấu hình

1. Đặt issuer công khai cố định.
2. Cấu hình datasource qua environment/secret injection.
3. Cấu hình JDBC repository và migration.
4. Đăng ký một confidential client dùng Authorization Code + PKCE.
5. Đăng ký một public client nếu có nhu cầu.
6. Cấu hình JWKSource lấy khóa ổn định từ key provider.
7. Cấu hình filter chain theo phiên bản Spring Authorization Server đang dùng.
8. Bật health probes và giới hạn actuator access.

**Kết quả mong đợi:** ứng dụng khởi động với database thật, client được đọc lại sau restart, issuer và JWKS ổn định qua nhiều lần khởi động.

### Lab C — Hoàn thiện ingress

1. Đưa ứng dụng sau Nginx hoặc ingress controller.
2. Chỉ cho phép backend nhận traffic từ ingress.
3. Xóa/ghi lại Forwarded và X-Forwarded-* tại proxy biên.
4. Cấu hình TLS và certificate cho domain test.
5. Xác minh redirect, discovery và cookie dùng URL công khai.

**Kết quả mong đợi:** client không thể giả mạo host/proto bằng header; metadata và redirect không lộ địa chỉ backend.

### Lab D — Chạy luồng OAuth/OIDC

1. Tạo user và client fixture.
2. Gửi authorization request với state, nonce và PKCE S256.
3. Đăng nhập và consent.
4. Đổi code bằng verifier đúng.
5. Xác minh access token ở resource server và ID Token ở OIDC client.
6. Thử verifier sai và code replay.
7. Thử refresh/revocation nếu được bật.
8. Kiểm tra audit event và persistence.

**Kết quả mong đợi:** luồng hợp lệ thành công; các trường hợp âm bị từ chối đúng; không có token hoặc secret trong log.

### Lab E — Kiểm tra vận hành

1. Khởi động hai instance với cùng issuer, database và key set.
2. Cấp code qua node A và đổi code qua node B.
3. Dừng một node theo graceful shutdown.
4. Kiểm tra readiness, liveness và load balancer drain.
5. Chạy backup/restore drill trên môi trường cô lập.
6. Thực hiện key rotation theo quy trình overlap.
7. Giả lập database mất kết nối trong môi trường test và quan sát readiness/error behavior.

**Kết quả mong đợi:** không phụ thuộc state cục bộ ngoài thiết kế; rollout không làm mất khả năng xác minh token; đội vận hành có thể phục hồi theo runbook.

### Lab F — Diễn tập sự cố

Chọn một kịch bản:

- Issuer trong metadata bị đổi sai.
- Secret của một client hết hạn.
- JWKS không có kid của token đang được phát.
- PostgreSQL connection pool cạn.
- Redis session store không truy cập được.
- Một node chạy key set hoặc config cũ.

Với mỗi kịch bản, ghi: triệu chứng, phát hiện, bằng chứng, phạm vi ảnh hưởng, mitigation, rollback, xác minh phục hồi và hành động phòng ngừa.

**Kết quả mong đợi:** một incident runbook có thể thực hiện được bởi người trực vận hành mà không cần đoán hoặc thao tác phá hủy.

## 13. Bộ tài liệu bàn giao tối thiểu

Một bộ tài liệu hoàn chỉnh nên có các artifact sau:

| Tài liệu | Nội dung bắt buộc | Người dùng chính |
|---|---|---|
| Architecture overview | Sơ đồ, component, trust boundary, luồng OAuth/OIDC | Developer, architect, security |
| Configuration reference | Issuer, endpoint, client policy, DB, key, proxy, secret | Developer, platform |
| Deployment runbook | Prerequisite, migration, rollout, readiness, rollback | SRE/operations |
| Client onboarding guide | Client type, redirect, grant, scope, PKCE, credential delivery | Application team |
| Key management runbook | Key inventory, access, rotation, emergency revocation | Security, platform |
| Monitoring and audit guide | Metrics, logs, event, alert và retention | SRE, security |
| Backup and recovery plan | RPO/RTO, backup, restore drill, key recovery | Operations |
| Incident playbooks | Symptom, evidence, mitigation, validation | On-call |
| Test and release checklist | Conformance, regression, smoke test, release gate | QA, developer, release manager |

Mỗi tài liệu phải có owner, phiên bản, ngày review gần nhất, môi trường áp dụng và liên kết đến cấu hình nguồn. Không chép secret vào tài liệu; tham chiếu tên secret hoặc resource ID trong secret manager. Định nghĩa lịch review sau thay đổi lớn về framework, OAuth/OIDC profile, issuer, key, database schema hoặc topology.

## 14. Checklist sẵn sàng vận hành

- [ ] Issuer được cấu hình tường minh và nhất quán với metadata/token.
- [ ] Grant, scope, redirect URI và client authentication method có owner.
- [ ] PKCE S256 được áp dụng theo policy cho Authorization Code clients.
- [ ] RegisteredClient, authorization và consent được lưu bền vững.
- [ ] Database migration có version, review và rollback strategy.
- [ ] Signing key ổn định, private key được bảo vệ và JWKS có kế hoạch rotation.
- [ ] Proxy xóa/ghi lại forwarded headers và backend chỉ nhận traffic tin cậy.
- [ ] TLS certificate, DNS, ingress và URL công khai được kiểm tra.
- [ ] Session/cookie/CSRF/CORS phù hợp với luồng browser.
- [ ] Health probes, metrics, logs và audit được cấu hình.
- [ ] Không log token, code, secret, cookie hoặc private key.
- [ ] Backup bao gồm dữ liệu và có kế hoạch phục hồi key.
- [ ] RPO/RTO và restore drill đã được xác định.
- [ ] Graceful shutdown, readiness và rollout nhiều instance đã được thử.
- [ ] Runbook xử lý lỗi issuer, client, token, JWKS, DB, session và proxy đã có.
- [ ] Smoke test và regression gate chạy trước khi release.

Một bộ tài liệu tốt phải dẫn được từ quyết định kiến trúc đến cấu hình thật, từ cấu hình đến thao tác vận hành, và từ triệu chứng đến hành động khôi phục có thể xác minh. Khi issuer, client policy, persistence, khóa ký, proxy và quy trình vận hành được mô tả nhất quán, Spring Authorization Server có thể được bàn giao và vận hành mà không phụ thuộc vào kiến thức ngầm của một cá nhân.

