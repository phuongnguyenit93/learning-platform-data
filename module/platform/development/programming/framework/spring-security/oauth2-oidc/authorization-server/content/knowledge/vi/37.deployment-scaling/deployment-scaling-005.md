# Chia sẻ dữ liệu client, authorization và consent giữa các instance

> **Chương: Triển khai và mở rộng.** Bài học thuộc module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, tập trung vào việc triển khai nhiều instance Spring Authorization Server cùng phục vụ một issuer OAuth 2.0/OpenID Connect. Mục tiêu là lưu trữ và chia sẻ nhất quán cấu hình OAuth client, trạng thái authorization, token và consent để request có thể đi qua bất kỳ instance nào mà vẫn giữ đúng hành vi bảo mật.

Một Authorization Server chạy trên một máy có thể bắt đầu với dữ liệu trong bộ nhớ. Khi triển khai nhiều máy sau load balancer, mỗi JVM có bộ nhớ riêng. Nếu instance A tạo authorization code nhưng request đổi code được chuyển sang instance B, B sẽ không tìm thấy dữ liệu nếu hai instance dùng kho lưu trữ độc lập. Cùng vấn đề xuất hiện với client mới đăng ký, consent vừa được người dùng chấp thuận, refresh token vừa bị thu hồi và trạng thái token cần introspection.

Giải pháp cốt lõi là dùng kho lưu trữ dùng chung làm nguồn dữ liệu có thẩm quyền. Spring Authorization Server cung cấp các implementation JDBC cho ba abstraction quan trọng: **RegisteredClientRepository**, **OAuth2AuthorizationService** và **OAuth2AuthorizationConsentService**.

## 1. Mục tiêu và tình huống triển khai

Giả sử một Authorization Server có hai instance sau load balancer:

- Instance A nhận authorization request, xác thực client và tạo authorization code.
- Instance B nhận token request do client gửi để đổi authorization code.
- Người dùng có thể đăng nhập ở A nhưng request tiếp theo được chuyển tới B.
- Quản trị viên có thể cập nhật redirect URI, scope hoặc secret của client trong khi cả hai instance đang chạy.
- Một resource server có thể gọi introspection endpoint để kiểm tra trạng thái opaque token.

Các thao tác này phải nhìn thấy cùng một trạng thái nghiệp vụ. Cả hai instance phải đọc và ghi vào cùng kho dữ liệu, dùng cùng quy tắc issuer và có quyền truy cập cùng bộ khóa ký token.

~~~mermaid
flowchart TD
    U[Browser / OAuth Client] --> LB[Load Balancer]
    LB --> A[Authorization Server A]
    LB --> B[Authorization Server B]
    A --> DB[(Shared relational database)]
    B --> DB
    A --> KMS[Shared signing keys / KMS]
    B --> KMS
    A -. optional .-> S[(Shared user session store)]
    B -. optional .-> S
    RS[Resource Server] -->|JWT validation or introspection| A
    RS -->|JWT validation or introspection| B
~~~

Database trong sơ đồ là nguồn dữ liệu chung cho client, authorization và consent. Kho khóa ký và kho session có thể là các hệ thống riêng vì chúng quản lý loại trạng thái khác nhau.

Sau bài học, người học có thể:

1. Phân biệt dữ liệu client, authorization, consent, user session và signing key.
2. Chọn implementation JDBC phù hợp của Spring Authorization Server.
3. Cấu hình nhiều instance dùng cùng DataSource.
4. Tổ chức schema, migration, seed dữ liệu client và bảo vệ credential.
5. Kiểm thử luồng authorization code, PKCE, refresh, revoke và consent qua nhiều instance.
6. Phát hiện các lỗi nhất quán, cache stale, race condition và cấu hình lệch giữa các node.

## 2. Ba nhóm dữ liệu cần được chia sẻ

Spring Authorization Server tách việc lưu trữ thành các abstraction. Mỗi abstraction có vòng đời và ý nghĩa bảo mật riêng.

| Abstraction | Implementation JDBC | Dữ liệu được quản lý | Hệ quả nếu mỗi node lưu riêng |
|---|---|---|---|
| **RegisteredClientRepository** | **JdbcRegisteredClientRepository** | Client ID, secret, redirect URI, grant type, scope, client settings và token settings | Client được tạo hoặc cập nhật ở node A có thể không tồn tại hoặc khác cấu hình ở node B |
| **OAuth2AuthorizationService** | **JdbcOAuth2AuthorizationService** | Authorization request, principal, authorization code, access token, refresh token, ID token và metadata liên quan | Node B không thể tìm authorization code hoặc không nhìn thấy trạng thái token do A tạo hay thu hồi |
| **OAuth2AuthorizationConsentService** | **JdbcOAuth2AuthorizationConsentService** | Các authority/scope mà người dùng đã chấp thuận cho một client | Người dùng có thể bị hỏi consent lặp lại hoặc node khác áp dụng quyết định consent cũ |

### 2.1. Registered client

RegisteredClient mô tả một OAuth client được Authorization Server tin cậy. Dữ liệu thường gồm:

- **id**: định danh nội bộ ổn định của bản ghi.
- **clientId**: định danh client dùng trong protocol.
- **clientSecret**: secret đã được mã hóa bằng PasswordEncoder nếu client sử dụng shared secret.
- **clientAuthenticationMethods**: cách client xác thực tại token endpoint.
- **authorizationGrantTypes**: các grant type được phép.
- **redirectUris** và **postLogoutRedirectUris**: URI đích được đăng ký.
- **scopes**: quyền client có thể yêu cầu.
- **clientSettings**: các chính sách như yêu cầu PKCE hoặc consent.
- **tokenSettings**: thời hạn access token, refresh token và chính sách tái sử dụng refresh token.

Client là cấu hình có vòng đời dài hơn một authorization transaction. Thay đổi client cần được quản trị có kiểm soát, có audit và được nhìn thấy nhất quán trên tất cả instance.

### 2.2. Authorization

OAuth2Authorization đại diện cho một lần cấp quyền và các token được tạo ra từ lần cấp quyền đó. Tùy flow, bản ghi có thể chứa:

- Principal và thông tin client liên quan.
- Authorization code cùng metadata và thời điểm hết hạn.
- Access token, refresh token, ID token và metadata của từng token.
- Các attribute phục vụ việc tiếp tục hoặc kiểm tra authorization flow.
- Trạng thái token như invalidated hoặc expired.

Authorization code thường có thời hạn ngắn và chỉ được sử dụng một lần. Refresh token có thể sống lâu hơn và có thể bị xoay vòng hoặc thu hồi. Việc chia sẻ bản ghi authorization giúp một instance khác tiếp tục xử lý đúng trạng thái do instance đầu tạo.

Với JWT access token tự chứa, resource server thường xác minh chữ ký và claim mà không cần truy vấn bản ghi authorization ở mỗi request. Tuy vậy, Authorization Server vẫn cần lưu authorization để xử lý refresh, revoke, introspection và các thao tác quản trị. Nếu resource server cần thấy việc thu hồi gần như tức thời, phải có cơ chế kiểm tra trạng thái như introspection hoặc denylist phù hợp; một JWT đã ký hợp lệ không tự biến mất khỏi mọi resource server chỉ vì bản ghi phía Authorization Server đã được đánh dấu revoked.

### 2.3. Consent

OAuth2AuthorizationConsent lưu quyết định của người dùng về quyền mà một client được phép sử dụng. Khóa logic thường gắn với registeredClientId và principalName. Nội dung consent có thể gồm các authority đại diện cho scope đã chấp thuận.

Consent khác authorization transaction:

- Consent thể hiện lựa chọn đã lưu của người dùng cho client.
- Authorization thể hiện một lần cấp quyền và token cụ thể.
- Một người dùng có thể có consent tồn tại qua nhiều lần đăng nhập hoặc authorization request.
- Một authorization có thể hết hạn hoặc bị thu hồi trong khi consent vẫn còn hiệu lực theo policy.

Không nên suy luận rằng xóa một access token đồng nghĩa người dùng đã rút consent, hoặc xóa consent đồng nghĩa mọi token đã cấp tự động bị thu hồi. Hai thao tác cần được xử lý theo chính sách sản phẩm và có audit rõ ràng.

## 3. Vì sao implementation trong bộ nhớ không phù hợp với nhiều instance?

Các implementation như InMemoryRegisteredClientRepository, InMemoryOAuth2AuthorizationService và InMemoryOAuth2AuthorizationConsentService lưu dữ liệu trong bộ nhớ của tiến trình Java. Mỗi instance có một tập dữ liệu riêng.

Ví dụ:

1. Người dùng gửi authorization request đến node A.
2. A tạo authorization code và lưu trong memory của A.
3. Client gửi token request; load balancer chuyển request đến node B.
4. B tìm authorization code trong memory của B và không tìm thấy.
5. Token exchange thất bại dù authorization code vẫn còn hợp lệ ở A.

Sticky session có thể làm một số request quay lại cùng node, nhưng không giải quyết được mất dữ liệu khi node restart, autoscaling, failover hoặc khi request được chuyển sang node khác. Sticky session cũng không đồng bộ client configuration hay consent.

Implementation trong bộ nhớ vẫn hữu ích cho demo, test đơn giản hoặc một tiến trình không cần lưu trạng thái lâu dài. Với production nhiều instance, hãy dùng persistence dùng chung.

## 4. Kiến trúc lưu trữ dùng chung

Một kiến trúc thường gặp là các instance dùng chung một relational database có tính nhất quán mạnh:

~~~mermaid
flowchart LR
    C[Clients and users] --> LB[Load balancer]
    LB --> N1[AS instance 1]
    LB --> N2[AS instance 2]
    LB --> N3[AS instance N]
    N1 --> DS[(Shared DataSource)]
    N2 --> DS
    N3 --> DS
    DS --> T1[(Registered clients)]
    DS --> T2[(Authorizations)]
    DS --> T3[(Consents)]
~~~

Nguyên tắc cấu hình:

- Mọi instance dùng cùng database/schema và cùng bộ migration.
- Mỗi instance có connection pool riêng nhưng cùng trỏ tới database cluster.
- Các instance dùng cùng issuer URL công khai.
- Các instance có thể truy cập cùng bộ khóa ký hoặc cùng KMS/HSM.
- Cấu hình protocol, token settings, clock và trusted proxy phải tương thích.
- Dữ liệu không được chuyển sang local memory khi database lỗi.

Một database trung tâm là lựa chọn dễ hiểu và thường phù hợp cho Authorization Server. Nếu dùng Redis hoặc kho NoSQL thay thế, cần tự triển khai đầy đủ contract, transaction/atomicity, TTL, truy vấn và tính nhất quán mà các service yêu cầu. Không thể thay JDBC bằng một cache key-value đơn giản rồi giả định mọi semantics vẫn được giữ.

## 5. Chuẩn bị schema và database

Spring Authorization Server cung cấp SQL schema mẫu cho ba JDBC implementation. Dùng các script đi kèm đúng phiên bản dependency đang triển khai, sau đó chuyển chúng thành migration được quản lý bằng Flyway, Liquibase hoặc công cụ migration của tổ chức.

Các resource schema thường có tên:

- **oauth2-registered-client-schema.sql**
- **oauth2-authorization-schema.sql**
- **oauth2-authorization-consent-schema.sql**

Chúng nằm trong package resource tương ứng với client repository và authorization service của Spring Authorization Server. Vị trí chính xác cần được kiểm tra trong artifact của phiên bản đang dùng; không sao chép schema từ một phiên bản khác mà chưa đối chiếu.

Các bảng mặc định thường là:

| Bảng | Nội dung |
|---|---|
| **oauth2_registered_client** | Cấu hình client đã đăng ký |
| **oauth2_authorization** | Authorization và token state |
| **oauth2_authorization_consent** | Consent của principal đối với client |

Schema JDBC có thể cần điều chỉnh kiểu dữ liệu theo PostgreSQL, MySQL, Oracle hoặc SQL Server, đặc biệt với cột văn bản dài và dữ liệu nhị phân. Hãy giữ nguyên các cột, độ dài và kiểu dữ liệu mà mapper của implementation đang cần. Khi nâng cấp Spring Authorization Server, kiểm tra release note và schema mới trước khi chạy migration.

### 5.1. Cấu hình DataSource

Ví dụ cấu hình Spring Boot dùng biến môi trường để cấp thông tin kết nối:

~~~yaml
spring:
  datasource:
    url: ${AUTH_DB_URL}
    username: ${AUTH_DB_USERNAME}
    password: ${AUTH_DB_PASSWORD}
    hikari:
      maximum-pool-size: 20
      minimum-idle: 5
      connection-timeout: 3000
~~~

Các giá trị trên chỉ minh họa cách cấu hình. Pool size phải được tính theo tổng số instance, giới hạn connection của database, số request đồng thời và thời gian truy vấn thực tế. Nếu mỗi node mở 20 connection và triển khai 10 node, database có thể phải phục vụ tới 200 connection từ service này.

Không ghi credential database trực tiếp vào source control. Dùng secret manager hoặc cơ chế cấp secret của nền tảng triển khai; bật TLS khi kết nối database nếu môi trường yêu cầu.

### 5.2. Migration và dữ liệu khởi tạo

Thực hiện migration như một bước triển khai có kiểm soát:

1. Xác định đúng phiên bản Spring Authorization Server.
2. So sánh schema mẫu với schema hiện có.
3. Tạo migration có version và review.
4. Chạy migration bằng deployment job hoặc một tiến trình được chọn.
5. Xác minh bảng, index, constraint và quyền database.
6. Khởi động các instance ứng dụng sau khi schema tương thích.

Không để mỗi instance tự chạy một đoạn DDL không kiểm soát khi cùng khởi động. Nhiều node cùng triển khai migration có thể gây tranh chấp hoặc làm rollout khó dự đoán.

Dữ liệu client ban đầu nên được provision bằng migration dữ liệu, admin workflow có xác thực hoặc job idempotent. Không tạo client ngẫu nhiên mới ở mỗi lần khởi động. Các node phải tham chiếu cùng clientId và cùng bản ghi client.

## 6. Cấu hình ba JDBC service

Khi Spring Boot đã cung cấp DataSource và JdbcTemplate, có thể cấu hình ba implementation JDBC như sau:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.server.authorization.JdbcOAuth2AuthorizationConsentService;
import org.springframework.security.oauth2.server.authorization.JdbcOAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationConsentService;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationService;
import org.springframework.security.oauth2.server.authorization.client.JdbcRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;

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

JdbcTemplate triển khai JdbcOperations, là kiểu mà các JDBC service sử dụng. Cả ba bean được tạo trong từng JVM nhưng đều truy cập cùng database. Đó là điểm làm cho dữ liệu được chia sẻ giữa các instance.

Kiểm tra cấu hình ứng dụng để bảo đảm chỉ có một bean phù hợp cho mỗi abstraction. Nếu còn cấu hình cũ tạo implementation in-memory, hãy loại bỏ cấu hình đó khỏi profile production hoặc bảo đảm bean JDBC được inject vào đúng Authorization Server configuration.

Không tạo một JdbcTemplate trỏ tới database khác cho từng service nếu mục tiêu là cùng một nguồn dữ liệu. Nếu kiến trúc buộc phải dùng nhiều database, phải thiết kế rõ đồng bộ, transaction boundary và cách xử lý lỗi giữa chúng; đây là một bài toán phân tán khác.

## 7. Provision và quản lý RegisteredClient

Ví dụ tạo một public web client dùng authorization code và PKCE:

~~~java
import java.time.Duration;
import java.util.UUID;

import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

public class ClientProvisioning {

    public void provisionWebClient(
            RegisteredClientRepository repository) {

        RegisteredClient client = RegisteredClient
                .withId(UUID.randomUUID().toString())
                .clientId("web-portal")
                .clientName("Web Portal")
                .clientAuthenticationMethod(
                        ClientAuthenticationMethod.NONE)
                .authorizationGrantType(
                        AuthorizationGrantType.AUTHORIZATION_CODE)
                .authorizationGrantType(
                        AuthorizationGrantType.REFRESH_TOKEN)
                .redirectUri("https://app.example.com/login/oauth2/code/portal")
                .scope("openid")
                .scope("profile")
                .clientSettings(ClientSettings.builder()
                        .requireProofKey(true)
                        .requireAuthorizationConsent(true)
                        .build())
                .tokenSettings(TokenSettings.builder()
                        .accessTokenTimeToLive(Duration.ofMinutes(5))
                        .refreshTokenTimeToLive(Duration.ofDays(14))
                        .reuseRefreshTokens(false)
                        .build())
                .build();

        repository.save(client);
    }
}
~~~

Đây là ví dụ public client nên không có client secret. Với confidential client dùng shared secret, hãy mã hóa secret bằng PasswordEncoder trước khi lưu:

~~~java
String encodedSecret = passwordEncoder.encode(rawClientSecret);
RegisteredClient client = RegisteredClient.withId(UUID.randomUUID().toString())
        .clientId("orders-service")
        .clientSecret(encodedSecret)
        .clientAuthenticationMethod(
                ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("orders.read")
        .build();
~~~

Không log raw secret, không commit secret vào repository và không trả secret đã lưu qua API quản trị. Password encoder được cấu hình trong Authorization Server phải tương thích với cách secret được mã hóa. Khi rotate secret, cần có quy trình thời gian chuyển tiếp và thu hồi credential cũ phù hợp.

### 7.1. Tránh seed trùng lặp khi scale out

Nếu cả ba instance đều chạy code provision khi khởi động, có thể xảy ra:

- Nhiều bản ghi client giống nhau nhưng có id khác nhau.
- Xung đột unique constraint trên client_id.
- Một node ghi đè cấu hình mà node khác vừa cập nhật.
- Secret được tạo lại hoặc khác nhau giữa các lần restart.

Hãy quản lý client bằng một quy trình provisioning riêng. Nếu dùng job tự động, job phải có khóa định danh ổn định, có kiểm tra tồn tại và có hành vi cập nhật được review. Không dùng UUID mới mỗi lần khởi động cho cùng một client logic.

### 7.2. Cập nhật client trong môi trường nhiều node

Khi thay đổi redirect URI, scope, grant type hoặc client settings:

1. Xác minh thay đổi theo quy trình quản trị.
2. Ghi bản cập nhật vào nguồn dữ liệu dùng chung.
3. Bảo đảm cache của các node được làm mới nếu có cache.
4. Kiểm thử authorization request mới trên nhiều node.
5. Theo dõi lỗi redirect URI, invalid client hoặc grant không được phép.

Client configuration có ảnh hưởng trực tiếp đến ranh giới bảo mật. Không cho phép client tự sửa redirect URI hay scope nếu không có policy và authorization quản trị tương ứng.

## 8. Lưu và chia sẻ consent

Authorization Server sử dụng OAuth2AuthorizationConsentService khi cần đọc hoặc lưu quyết định consent. Với implementation JDBC, consent được ghi vào bảng dùng chung.

Một consent đã được node A lưu sẽ được node B đọc thông qua cùng service và database. Ví dụ minh họa việc tạo một consent record:

~~~java
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationConsent;
import org.springframework.security.oauth2.server.authorization.OAuth2AuthorizationConsentService;

public class ConsentProvisioning {

    public void grantReadConsent(
            OAuth2AuthorizationConsentService consentService,
            String registeredClientId,
            String principalName) {

        OAuth2AuthorizationConsent consent =
                OAuth2AuthorizationConsent.withId(
                                registeredClientId, principalName)
                        .authority("SCOPE_orders.read")
                        .build();

        consentService.save(consent);
    }
}
~~~

Trong ứng dụng thực tế, consent thường được lưu thông qua authorization flow và consent page do ứng dụng cấu hình. Đoạn code trên chỉ minh họa API persistence; không nên tự cấp consent thay người dùng nếu chưa có căn cứ policy và authorization hợp lệ.

Khi người dùng rút consent, ứng dụng phải xác định rõ có cần thu hồi các authorization/token đã phát hành dựa trên consent đó hay không. Nếu cần, thao tác thu hồi phải cập nhật authorization tương ứng theo một workflow có audit. Xóa consent đơn thuần không bảo đảm JWT đang được resource server chấp nhận lập tức bị vô hiệu.

## 9. Authorization code và PKCE qua nhiều instance

Authorization code flow là phép thử rõ nhất cho persistence dùng chung:

1. Browser gửi authorization request tới issuer.
2. Load balancer chuyển request tới node A.
3. A tìm RegisteredClient, xác thực người dùng và kiểm tra consent.
4. A tạo authorization code cùng metadata của request, bao gồm dữ liệu PKCE cần thiết.
5. OAuth2AuthorizationService lưu authorization vào database.
6. Browser/client nhận redirect chứa authorization code.
7. Client gửi token request; load balancer có thể chuyển request tới node B.
8. B tìm authorization trong cùng database, kiểm tra client, redirect URI, PKCE verifier, thời hạn và trạng thái code.
9. Nếu hợp lệ, B đánh dấu code đã sử dụng và phát token theo flow.

~~~mermaid
sequenceDiagram
    participant U as Browser
    participant LB as Load Balancer
    participant A as AS node A
    participant DB as Shared DB
    participant B as AS node B
    participant C as OAuth Client
    U->>LB: Authorization request
    LB->>A: Route to A
    A->>DB: Read RegisteredClient / Consent
    A->>DB: Save OAuth2Authorization + code
    A-->>U: Redirect with authorization code
    U->>C: Deliver callback
    C->>LB: POST token request + code + verifier
    LB->>B: Route to B
    B->>DB: Find authorization by code
    B->>DB: Validate and update code/token state
    B-->>C: Access token / ID token
~~~

PKCE không thay thế persistence. PKCE ràng buộc token request với client đã tạo code verifier/challenge; Authorization Server vẫn phải tìm đúng authorization và kiểm tra verifier khi đổi code. Nếu code chỉ tồn tại trong memory của A, B không thể thực hiện kiểm tra này.

Authorization code cần được tiêu thụ đúng một lần. Với request đồng thời hoặc retry do mạng, cần xác minh implementation và database bảo đảm không phát hành token hai lần cho cùng code. Hãy kiểm thử race condition thực tế; không chỉ kiểm tra happy path tuần tự.

## 10. Refresh token, revoke và introspection

### 10.1. Refresh token rotation

Khi refresh token được dùng để lấy access token mới, Authorization Server cần đọc authorization hiện tại, kiểm tra trạng thái và cập nhật token state. Nếu cấu hình không tái sử dụng refresh token, token cũ được invalidated và token mới được lưu.

Với nhiều instance, node nhận refresh request phải thấy bản ghi mới nhất. Nếu node A đã rotate refresh token nhưng node B đọc dữ liệu cũ từ replica trễ hoặc cache stale, hệ thống có thể chấp nhận token cũ hoặc từ chối nhầm token mới.

### 10.2. Token revocation

Revocation endpoint cần cập nhật trạng thái token trong authorization store. Các instance khác phải đọc trạng thái cập nhật đó khi xử lý refresh hoặc introspection. Nếu dùng JWT access token và resource server chỉ xác minh chữ ký cục bộ, việc cập nhật database ở Authorization Server không tự động buộc resource server từ chối JWT trước thời điểm hết hạn.

### 10.3. Token introspection

Với opaque token, resource server có thể gọi introspection endpoint. Authorization Server tra cứu token trong OAuth2AuthorizationService và trả về trạng thái active theo protocol. Các node phải cùng nhìn thấy trạng thái token để kết quả introspection không phụ thuộc node nhận request.

| Tình huống | Yêu cầu với kho dùng chung |
|---|---|
| Token vừa được phát hành ở A, introspection ở B | B tìm thấy token và trả trạng thái đúng |
| Refresh token bị rotate ở A, request tiếp theo tới B | B thấy token cũ đã invalidated và token mới |
| Token bị revoke ở A, introspection tới B | B đọc trạng thái revoked |
| Node A restart | Authorization và token state vẫn còn trong database |
| Resource server xác minh JWT offline | Chữ ký, issuer, audience và thời hạn phải hợp lệ; trạng thái revoke cần cơ chế bổ sung nếu yêu cầu thu hồi tức thời |

## 11. Nhất quán dữ liệu và xử lý đồng thời

Chia sẻ cùng database là điều kiện cần, nhưng chưa đủ. Cần xem xét consistency model, cache và các thao tác đồng thời.

### 11.1. Ưu tiên đọc nhất quán cho dữ liệu bảo mật

Authorization code, refresh token và trạng thái revoke có yêu cầu đọc sau ghi rất rõ. Sau khi node A cập nhật token state, node B cần nhìn thấy thay đổi đó khi xử lý request kế tiếp.

Nếu database dùng primary/replica:

- Ghi vào primary.
- Các thao tác cần read-your-writes hoặc trạng thái mới nhất nên đọc từ primary hoặc một đường đọc có bảo đảm consistency phù hợp.
- Không dùng replica có replication lag cho quyết định chấp nhận authorization code hoặc refresh token nếu điều đó có thể làm token cũ được chấp nhận.
- Đo và cảnh báo replication lag.

Không dùng eventual consistency một cách mặc định cho mọi bảng chỉ vì hệ thống cần mở rộng. Một số dữ liệu thống kê có thể chấp nhận trễ; quyết định cấp quyền và trạng thái token cần semantics chặt chẽ hơn.

### 11.2. Race condition khi dùng authorization code hoặc refresh token

Hai request có thể đến hai instance gần như cùng lúc với cùng authorization code hoặc refresh token. Nếu cả hai cùng đọc trạng thái chưa sử dụng trước khi một request ghi trạng thái đã sử dụng, có nguy cơ xử lý trùng.

Hãy:

- Kiểm tra hành vi của phiên bản Spring Authorization Server và database đang triển khai.
- Kiểm thử hai request đồng thời trên hai instance.
- Xác minh update/consume có tính atomic theo yêu cầu one-time token.
- Nếu custom persistence, dùng transaction, row-level lock hoặc thao tác compare-and-set có điều kiện để chỉ một request thắng.
- Có test đảm bảo request thứ hai bị từ chối sau khi token đã được tiêu thụ.

Không giả định sticky session sẽ loại bỏ race condition; hai request vẫn có thể đồng thời tới cùng một node.

### 11.3. Transaction boundary

Các JDBC implementation sử dụng JdbcOperations và tham gia transaction Spring đang hoạt động thông qua cơ chế quản lý connection của Spring. Với workflow quản trị do ứng dụng tự viết, dùng @Transactional khi một thao tác logic cần cập nhật nhiều bản ghi liên quan.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class ClientAdministrationService {

    private final RegisteredClientRepository clients;

    public ClientAdministrationService(RegisteredClientRepository clients) {
        this.clients = clients;
    }

    @Transactional
    public void updateClient(RegisteredClient replacement) {
        clients.save(replacement);
        // Ghi audit hoặc cập nhật dữ liệu liên quan trong cùng transaction
        // nếu các thao tác đó dùng cùng transaction manager.
    }
}
~~~

Ví dụ trên minh họa transaction cho một workflow quản trị. Không nên bọc toàn bộ HTTP request hoặc toàn bộ authorization flow trong một transaction dài. Transaction kéo dài giữ connection và lock lâu, làm tăng contention và giảm khả năng phục vụ.

Nếu audit nằm ở một hệ thống khác hoặc gửi event ra broker, transaction database không tự động bao trùm hệ thống ngoài. Cần thiết kế outbox hoặc cơ chế nhất quán phù hợp thay vì giả định một transaction phân tán tồn tại.

## 12. Cache và vô hiệu hóa cache

Cache có thể giảm truy vấn đọc RegisteredClient, nhưng cache local của từng JVM có thể tạo ra cấu hình khác nhau giữa các node.

Ví dụ:

1. Node A cache redirect URI cũ.
2. Quản trị viên cập nhật redirect URI trong database.
3. Node B đọc URI mới.
4. Node A tiếp tục dùng URI cũ cho tới khi cache hết hạn.

Nếu cần cache:

- Xác định dữ liệu nào được cache và thời gian sống tối đa.
- Dùng distributed cache hoặc cơ chế publish invalidation event tới tất cả node.
- Có cách xử lý event bị mất, node restart và cache warm-up.
- Không cache trạng thái authorization/token theo cách làm chậm việc nhìn thấy revoke hoặc refresh rotation.
- Theo dõi cache hit, miss, invalidation delay và dữ liệu stale.

Không coi database là nguồn đúng nhưng lại cho phép cache cục bộ ghi đè quyết định bảo mật bằng dữ liệu cũ. Với quy mô vừa phải, đọc trực tiếp từ JDBC có thể là lựa chọn đơn giản và dễ vận hành hơn.

## 13. Những trạng thái khác cũng cần được đồng bộ

Ba JDBC service giải quyết client, authorization và consent. Chúng không tự động chia sẻ mọi trạng thái khác của Authorization Server.

### 13.1. Signing key và JWK Set

Nếu mỗi node tự tạo một RSA key khi khởi động, node A có thể ký JWT bằng key A trong khi node B công bố hoặc sử dụng key B. Resource server có thể không xác minh được token tùy node phát hành.

Các instance cần dùng cùng tập khóa phù hợp:

- Lưu private key trong KMS, HSM hoặc kho bí mật được bảo vệ.
- Chia sẻ public key/JWK Set nhất quán giữa các node.
- Giữ kid ổn định cho từng key.
- Thiết kế rotation có giai đoạn công bố key mới và giữ key cũ đủ lâu để xác minh token còn hạn.
- Không đưa private key vào log, image container hoặc source control.

Kho khóa là một miền dữ liệu riêng; không cần đặt private key trực tiếp trong ba bảng authorization.

### 13.2. Issuer và cấu hình protocol

Mọi node phải công bố cùng issuer URL, ví dụ https://auth.example.com. Token do A phát hành và metadata do B công bố phải cùng xác định một issuer.

Các node cũng cần tương thích về:

- Authorization Server settings và endpoint path.
- Grant type, authentication method và client policy.
- Token format, thời hạn và claim mapping.
- Trusted proxy và cách tạo redirect URL.
- Phiên bản ứng dụng trong giai đoạn rolling deployment.

Không để từng node tự suy ra issuer từ hostname nội bộ hoặc header do client tùy ý gửi. Nếu chạy sau reverse proxy, chỉ tin forwarded header từ proxy được cấu hình tin cậy.

### 13.3. Phiên đăng nhập người dùng

User authentication session trong Spring Security là trạng thái khác với OAuth2 authorization. Khi người dùng đăng nhập tại A, cookie/session có thể được gửi tới B; B chỉ khôi phục được phiên nếu session store được chia sẻ hoặc thiết kế xác thực cho phép.

Nếu cần session dùng chung, có thể xem xét Spring Session với Redis hoặc JDBC. Cần cấu hình cookie, session serialization, timeout và bảo vệ session fixation phù hợp. Không nhầm bảng oauth2_authorization với kho lưu HTTP session.

Sticky session có thể hỗ trợ một số ứng dụng session-local, nhưng không thay thế persistence cho client, authorization và consent.

## 14. Bảo vệ database và dữ liệu OAuth

Database chứa thông tin có thể quyết định ai được cấp token và token nào còn hiệu lực. Cần bảo vệ như một thành phần bảo mật trọng yếu.

- Dùng tài khoản database riêng cho Authorization Server, chỉ cấp quyền cần thiết trên schema.
- Bật TLS cho kết nối database khi phù hợp với môi trường.
- Mã hóa dữ liệu lưu trữ và backup theo policy.
- Không log password, client secret dạng thô, authorization code, access token, refresh token hoặc session cookie.
- Hạn chế quyền truy cập trực tiếp vào bảng authorization và consent.
- Audit thay đổi client, redirect URI, scope, consent và thao tác thu hồi.
- Đặt retention policy cho authorization/token record đã hết hạn.
- Backup database và kiểm thử restore định kỳ.
- Bảo vệ secret dùng để kết nối database bằng secret manager.

Không sửa trực tiếp token state bằng SQL thủ công trong incident nếu chưa hiểu mapper và lifecycle của Spring Authorization Server. Hãy dùng service/API quản trị có audit hoặc runbook đã được kiểm thử.

Nếu database không khả dụng, Authorization Server cần xử lý theo hướng fail closed đối với thao tác cần đọc hoặc ghi authorization state. Không tự động chuyển sang in-memory store rồi tiếp tục cấp token; điều đó tạo ra trạng thái phân tách giữa các node và có thể làm mất khả năng thu hồi.

## 15. Triển khai và mở rộng

### 15.1. Rolling deployment

Trong rolling deployment, phiên bản cũ và mới có thể chạy đồng thời. Vì vậy:

- Migration phải tương thích với cả hai phiên bản trong khoảng rollout.
- Tránh đổi tên hoặc xóa cột khi node cũ vẫn đang hoạt động.
- Ưu tiên expand-migrate-contract: thêm cấu trúc mới, triển khai code tương thích, chuyển dữ liệu, rồi mới xóa cấu trúc cũ ở lần phát hành sau.
- Kiểm tra khả năng đọc/ghi của các phiên bản trên cùng schema.
- Không để node mới ghi format mà node cũ không thể đọc nếu cả hai còn phục vụ traffic.

### 15.2. Connection pool và database capacity

Tăng số Authorization Server instance làm tăng số connection pool. Tính tổng connection tối đa từ tất cả node, job quản trị và công cụ vận hành. Theo dõi:

- Active, idle và pending connection.
- Connection acquisition timeout.
- Query latency và slow query.
- Lock wait, deadlock và transaction duration.
- CPU, IOPS, storage growth và replication lag.

Pool lớn không đồng nghĩa throughput cao hơn. Khi database đã bão hòa, thêm connection có thể làm contention nặng hơn.

### 15.3. Database failover

Khi database failover, connection đang mở có thể bị ngắt. Cấu hình pool cần kiểm tra connection hợp lệ và có khả năng reconnect theo nền tảng. Request đang xử lý có thể thất bại; client cần xử lý retry an toàn.

Không retry mù quáng một token request nếu không biết server đã commit phát hành token hay chưa. Thiết kế client và server phải tính đến kết quả không xác định do mất kết nối sau khi commit. Quan sát log/audit và trạng thái authorization để xử lý trường hợp này.

## 16. Kiểm thử multi-instance

Một bài test chỉ khởi tạo một Spring context không đủ chứng minh dữ liệu được chia sẻ. Hãy chạy hai application context hoặc hai instance độc lập cùng kết nối một database test.

| # | Tình huống | Kết quả mong đợi |
|---|---|---|
| 1 | Tạo client qua node A, tìm client qua node B | B tìm thấy cùng clientId và settings |
| 2 | Cập nhật redirect URI qua A, đọc qua B | B thấy giá trị mới theo consistency policy |
| 3 | Tạo authorization code qua A, đổi code qua B | B tìm thấy authorization và xử lý code hợp lệ |
| 4 | Dùng code đã đổi lần đầu để đổi lần hai ở B | Request thứ hai bị từ chối |
| 5 | Tạo consent qua A, gửi authorization request tới B | B đọc đúng consent |
| 6 | Rút consent theo policy | Các node áp dụng cùng trạng thái consent mới |
| 7 | Refresh token qua A, dùng refresh token cũ qua B | Token cũ bị từ chối khi rotation đã hoàn tất |
| 8 | Revoke token qua A, introspection qua B | B trả trạng thái inactive theo protocol |
| 9 | Restart A sau khi lưu authorization | B vẫn đọc được dữ liệu |
| 10 | Database unavailable | Không fallback sang cấp token bằng local memory |
| 11 | Hai request đồng thời dùng cùng authorization code | Chỉ một request được xử lý thành công |
| 12 | Hai request đồng thời dùng cùng refresh token | Kết quả phù hợp với chính sách rotation và replay detection |
| 13 | Node A và B phát hành JWT | Resource server xác minh được token từ cả hai node |
| 14 | Rotate signing key | JWK Set và các node có thể xác minh token trong giai đoạn chuyển tiếp |
| 15 | Rolling deployment qua hai phiên bản | Cả hai phiên bản đọc/ghi schema tương thích |

### 16.1. Integration test với hai service instance

Ví dụ sau minh họa cách kiểm tra RegisteredClientRepository dùng chung database. Hai repository được tạo độc lập nhưng nhận cùng JdbcTemplate/database:

~~~java
@Test
void clientSavedByOneRepositoryCanBeReadByAnother() {
    RegisteredClientRepository nodeA =
            new JdbcRegisteredClientRepository(jdbcTemplate);
    RegisteredClientRepository nodeB =
            new JdbcRegisteredClientRepository(jdbcTemplate);

    RegisteredClient client = RegisteredClient
            .withId("test-client-id")
            .clientId("test-client")
            .clientAuthenticationMethod(
                    ClientAuthenticationMethod.NONE)
            .authorizationGrantType(
                    AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("https://client.example.test/callback")
            .scope("openid")
            .build();

    nodeA.save(client);

    RegisteredClient loaded = nodeB.findByClientId("test-client");

    assertThat(loaded).isNotNull();
    assertThat(loaded.getId()).isEqualTo("test-client-id");
}
~~~

Trong test thực tế, cần dọn dữ liệu giữa các test, dùng database engine tương thích production và không để test chạy song song với cùng clientId cố định nếu có thể xung đột. Đối với authorization, consent, refresh và revoke, hãy viết integration test ở mức service/HTTP với hai instance để xác minh đầy đủ serialization, transaction và token lifecycle.

Không dùng H2 làm bằng chứng duy nhất nếu production dùng PostgreSQL hoặc MySQL. Khác biệt về kiểu dữ liệu, locking, isolation và SQL dialect có thể chỉ xuất hiện trên database production. Testcontainers là một lựa chọn để chạy integration test với engine tương ứng.

## 17. Troubleshooting

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Authorization code tạo ở A nhưng B báo không tìm thấy | A và B dùng store khác nhau hoặc B trỏ database/schema khác | Kiểm tra DataSource, schema và bean OAuth2AuthorizationService |
| Client tồn tại ở A nhưng không tồn tại ở B | Dùng in-memory repository hoặc cache riêng | Dùng JdbcRegisteredClientRepository, kiểm tra cache invalidation |
| Consent bị hỏi lại trên node khác | Consent service chưa dùng database chung hoặc principal/client ID khác nhau | Kiểm tra OAuth2AuthorizationConsentService, registeredClientId và principal |
| Refresh token cũ vẫn được chấp nhận ở một node | Replica lag, cache stale hoặc xử lý đồng thời không atomic | Đọc nhất quán, bỏ cache token state và kiểm thử race condition |
| Revoke ở A nhưng introspection qua B vẫn active | Node B đọc dữ liệu stale hoặc không dùng cùng authorization store | Kiểm tra routing database, transaction commit và read path |
| JWT từ A không xác minh được khi metadata/JWK lấy từ B | Key pair hoặc JWK Set khác nhau | Dùng signing key chung và kiểm tra kid |
| Người dùng bị đăng nhập lại khi request sang node khác | HTTP session không được chia sẻ | Cấu hình Spring Session hoặc session architecture phù hợp |
| Restart node làm mất client hoặc consent | Dữ liệu vẫn nằm trong memory | Chuyển sang persistence bền vững |
| Lỗi SQL khi lưu authorization | Schema lệch phiên bản hoặc kiểu cột không phù hợp | Đối chiếu schema đi kèm dependency và migration |
| Pool cạn khi tăng số node | Tổng connection vượt khả năng database | Tính lại pool, giới hạn rollout và tối ưu query |
| Hai lần đổi cùng authorization code đều thành công | Consume không được bảo vệ khỏi race condition | Kiểm tra atomic update/locking và bổ sung test đồng thời |
| Node mới lỗi khi đọc bản ghi do node cũ tạo | Không tương thích schema hoặc serialized data trong rolling deploy | Dùng migration tương thích ngược và kiểm tra format dữ liệu |

### 17.1. Checklist trước production

- [ ] Ba abstraction client, authorization và consent đều dùng JDBC/shared persistence.
- [ ] Tất cả instance trỏ cùng database/schema.
- [ ] Schema được tạo bằng migration đúng phiên bản Spring Authorization Server.
- [ ] Không còn in-memory implementation trong profile production.
- [ ] Client được provision có kiểm soát, không tạo bản ghi ngẫu nhiên ở mỗi lần khởi động.
- [ ] Client secret được mã hóa bằng PasswordEncoder phù hợp.
- [ ] Database credential được quản lý bằng secret manager.
- [ ] Read path của authorization code, refresh và revoke đáp ứng yêu cầu read-your-writes.
- [ ] Có kiểm thử concurrent authorization code và refresh token.
- [ ] Cache client có invalidation; token state không bị stale.
- [ ] Signing key/JWK Set được chia sẻ và có kế hoạch rotation.
- [ ] Mọi node dùng cùng issuer và cấu hình protocol tương thích.
- [ ] HTTP session được chia sẻ nếu flow đăng nhập yêu cầu.
- [ ] Có backup, restore test, monitoring connection pool và query latency.
- [ ] Có runbook khi database failover hoặc không khả dụng.
- [ ] Resource server có chiến lược phù hợp với yêu cầu thu hồi JWT.
- [ ] Có audit cho thay đổi client, consent và thao tác thu hồi.

## 18. Câu hỏi tự đánh giá

1. Vì sao InMemoryOAuth2AuthorizationService không phù hợp khi authorization request và token request có thể tới hai instance khác nhau?
2. RegisteredClientRepository, OAuth2AuthorizationService và OAuth2AuthorizationConsentService quản lý ba loại dữ liệu nào?
3. Vì sao consent không đồng nghĩa với authorization hoặc token?
4. Ba JDBC implementation mặc định sử dụng những bảng nào?
5. Vì sao mọi instance cần dùng chung DataSource?
6. Sticky session có giải quyết được dữ liệu mất khi node restart không?
7. Vì sao authorization code và refresh token cần read-after-write consistency?
8. Replication lag có thể gây lỗi bảo mật nào khi xử lý token?
9. Vì sao cache local cho client settings có thể làm hai node áp dụng policy khác nhau?
10. Khi dùng authorization code đồng thời trên hai node, cần kiểm thử điều gì?
11. Vì sao signing key và JWK Set cũng cần nhất quán giữa các instance?
12. HTTP session khác OAuth2Authorization ở điểm nào?
13. JWT access token có tự động bị vô hiệu ngay khi bản ghi authorization bị revoke không?
14. Cần làm gì để schema tương thích trong rolling deployment?
15. Khi database unavailable, vì sao không nên fallback sang in-memory persistence?

## Tài liệu tham khảo

- [Spring Authorization Server — Core Model Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html): các abstraction RegisteredClient, OAuth2Authorization, consent và service/repository.
- [Spring Authorization Server — Getting Started](https://docs.spring.io/spring-authorization-server/reference/getting-started.html): cấu hình Authorization Server và các thành phần nền tảng.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): authorization, token, introspection và revocation endpoint.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html): cấu hình các thành phần Authorization Server.
- [Spring Framework — JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html): JdbcTemplate, JdbcOperations và truy cập database.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): transaction boundary và @Transactional.
- [Spring Session](https://docs.spring.io/spring-session/reference/): chia sẻ HTTP session khi triển khai nhiều instance.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): xác minh JWT và JWK Set.
