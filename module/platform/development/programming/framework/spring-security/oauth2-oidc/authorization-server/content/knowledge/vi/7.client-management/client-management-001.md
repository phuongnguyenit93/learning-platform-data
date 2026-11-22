# Khai báo client bằng builder và repository

> **Chương: Quản lý client.** Bài thuộc module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER**, hướng dẫn thiết kế, cấu hình, bảo mật, kiểm thử và vận hành OAuth 2.0/OpenID Connect Authorization Server bằng Spring Security và Spring Authorization Server trong ứng dụng Spring Boot. Trọng tâm là mô hình `RegisteredClient`, cách tạo client bằng builder và cách quản lý chúng qua `RegisteredClientRepository`.

## 1. Vì sao Authorization Server phải đăng ký client?

Trong OAuth 2.0, **client** là ứng dụng yêu cầu quyền truy cập tài nguyên thay mặt người dùng hoặc nhân danh chính ứng dụng đó. Authorization Server cần biết client nào được phép tham gia, bằng cách nào client tự xác thực, có thể dùng grant type nào, được chuyển hướng tới URI nào và được yêu cầu scope gì.

Giả sử hệ thống gồm:

- **Authorization Server (AS/OP):** `https://login.example.vn`, cấp authorization code, access token và ID Token khi có OIDC.
- **Web client:** `portal-web` tại `https://portal.example.vn`, người dùng đăng nhập qua Authorization Code + PKCE; callback `https://portal.example.vn/login/oauth2/code/portal`.
- **Backend worker:** `billing-job`, chạy theo lịch và gọi API bằng Client Credentials, không có màn hình đăng nhập người dùng.
- **Public client:** `mobile-app` hoặc SPA, không thể bảo vệ một client secret dài hạn như server; cần Authorization Code + PKCE và redirect URI phù hợp nền tảng.
- **Resource Server:** `https://api.example.vn`, kiểm tra access token và quyền truy cập API.

Đây là ba kiểu client có rủi ro và yêu cầu khác nhau; **không nên dùng một cấu hình chung cho mọi client**.

| Câu hỏi Authorization Server cần trả lời | Thành phần cấu hình |
|---|---|
| Client được nhận diện bằng giá trị nào? | `clientId` (OAuth `client_id`); `id` là khóa định danh nội bộ của bản ghi |
| Client được chứng minh danh tính ra sao? | `clientAuthenticationMethods`, `clientSecret` hoặc phương thức khác phù hợp |
| Client có thể thực hiện luồng cấp quyền nào? | `authorizationGrantTypes` |
| Trình duyệt có thể quay về đâu? | `redirectUris`; với OIDC logout là `postLogoutRedirectUris` |
| Client được phép xin những quyền nào? | `scopes` |
| Có yêu cầu PKCE và consent không? | `ClientSettings` |
| Token sống bao lâu, định dạng nào? | `TokenSettings` |
| Tra cứu và lưu các bản ghi này ở đâu? | `RegisteredClientRepository` |

**Đăng ký client** là điều kiện để Authorization Server áp dụng chính sách đầu vào. Nó không tự cấp quyền sử dụng từng API cho người dùng; Resource Server vẫn cần kiểm tra scope/audience/authorization. Cũng không nên nhầm client registration với việc đăng ký **tài khoản người dùng**.

## 2. Mô hình `RegisteredClient`: ba lớp cấu hình

Spring Authorization Server cung cấp `RegisteredClient` như một đối tượng bất biến thể hiện một client đã đăng ký. Ta tạo đối tượng bằng **builder**, rồi lưu vào repository.

~~~mermaid
flowchart TB
    Inputs["Thông tin do quản trị viên/tenant provisioning<br/>client_id, loại client, URI, scope, grant"] --> Builder["RegisteredClient.withId(id)<br/>builder"]
    Secrets["Credential đã xác minh chính sách<br/>hash client secret hoặc public key metadata"] --> Builder
    Builder --> Client["RegisteredClient<br/>identity + auth methods + grants + redirects + scopes"]
    Builder --> Settings["ClientSettings<br/>PKCE, consent, chính sách client"]
    Builder --> Tokens["TokenSettings<br/>TTL, format, rotation policy"]
    Client --> Repo["RegisteredClientRepository"]
    Settings --> Repo
    Tokens --> Repo
    Repo --> AS["Authorization Server<br/>/oauth2/authorize và /oauth2/token"]
~~~

Ba nhóm nên được hiểu riêng:

1. **Thuộc tính đăng ký** của `RegisteredClient`: `clientId`, `clientName`, `clientSecret`, phương thức xác thực, grant, redirect URI và scopes.
2. **`ClientSettings`**: chính sách áp dụng cho client như bắt buộc PKCE (`requireProofKey`) và yêu cầu consent (`requireAuthorizationConsent`). Một số cơ chế chứng thực nâng cao có setting riêng.
3. **`TokenSettings`**: chính sách cấp token như thời hạn authorization code/access token/refresh token, reuse refresh token và định dạng access token.

**Builder không phải repository.** `RegisteredClient.withId(...).build()` tạo một object; phải `save(...)` hoặc truyền cho repository thì Authorization Server mới tra cứu được bản ghi tương ứng. `RegisteredClient` cũng không phải Spring Security `UserDetails`: client đại diện ứng dụng, còn `UserDetails` mô tả người dùng.

### 2.1. Các field thường gặp của builder

| Builder API | Công dụng và lưu ý |
|---|---|
| `.withId(String)` | Đặt `id` nội bộ của bản ghi; giữ ổn định khi cập nhật cùng một client |
| `.clientId(String)` | Giá trị `client_id` do OAuth Client gửi; phải duy nhất trong phạm vi Authorization Server |
| `.clientIdIssuedAt(Instant)` | Thời điểm cấp `client_id`, hữu ích khi quản lý vòng đời/metadata |
| `.clientName(String)` | Tên mô tả phục vụ vận hành; không dùng làm credential |
| `.clientSecret(String)` | Thông thường lưu **chuỗi hash có prefix thuật toán** như `{bcrypt}...` của confidential client |
| `.clientSecretExpiresAt(Instant)` | Thời điểm secret hết hạn nếu chính sách áp dụng; cần luồng đổi secret trước hạn |
| `.clientAuthenticationMethod(...)` | Ví dụ `CLIENT_SECRET_BASIC`, `CLIENT_SECRET_POST`, `NONE`; lựa chọn theo loại client |
| `.authorizationGrantType(...)` | Ví dụ `AUTHORIZATION_CODE`, `REFRESH_TOKEN`, `CLIENT_CREDENTIALS` |
| `.redirectUri(String)` | URI callback dùng tại authorization endpoint; chỉ đăng ký URI đáng tin |
| `.postLogoutRedirectUri(String)` | URI sau OIDC RP-Initiated Logout; kiểm soát riêng callback đăng nhập |
| `.scope(String)` | Scope client được phép yêu cầu, như `openid`, `profile`, `orders.read` |
| `.clientSettings(ClientSettings)` | PKCE, consent và một số policy gắn client |
| `.tokenSettings(TokenSettings)` | Thời gian sống, format và chính sách token |

Một client có thể có nhiều grant type, redirect URI, scope... bằng cách gọi builder nhiều lần. **Được đăng ký không có nghĩa mọi cách kết hợp đều hợp lệ:** ví dụ Client Credentials không có tương tác người dùng và không cấp ID Token OIDC; authorization code yêu cầu callback, state/PKCE và xác thực phù hợp.

## 3. Ví dụ khai báo confidential web client bằng builder

### 3.1. Thiết kế đăng ký

Client `portal-web` là ứng dụng Spring Boot chạy trên server, có thể bảo vệ client secret. Người dùng được chuyển tới OP để đăng nhập. Cấu hình đề xuất:

| Thiết lập | Giá trị minh họa |
|---|---|
| `client_id` | `portal-web` |
| Client authentication | `client_secret_basic` |
| Grant types | `authorization_code`, `refresh_token` |
| Redirect URI | `https://portal.example.vn/login/oauth2/code/portal` |
| OIDC post-logout redirect | `https://portal.example.vn/signed-out` |
| Scopes | `openid`, `profile`, `orders.read` |
| Client settings | Bắt buộc PKCE, yêu cầu consent |
| Token settings | Authorization code 5 phút, access token 10 phút, refresh token 8 giờ (ví dụ policy) |

Phần Java dưới đây minh họa Spring Authorization Server API 1.x và Spring Security 6.x. Dùng phiên bản dependency tương thích với Spring Boot của dự án; đối chiếu API thực tế nếu dự án đang ở major version khác.

~~~java
import java.time.Duration;

import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.oidc.OidcScopes;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClient;
import org.springframework.security.oauth2.server.authorization.settings.ClientSettings;
import org.springframework.security.oauth2.server.authorization.settings.TokenSettings;

static RegisteredClient webClient(String encodedClientSecret) {
    return RegisteredClient.withId("registration-portal-web")
            .clientId("portal-web")
            .clientName("Portal Web")
            .clientSecret(encodedClientSecret)
            .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .authorizationGrantType(AuthorizationGrantType.REFRESH_TOKEN)
            .redirectUri(
                    "https://portal.example.vn/login/oauth2/code/portal")
            .postLogoutRedirectUri("https://portal.example.vn/signed-out")
            .scope(OidcScopes.OPENID)
            .scope(OidcScopes.PROFILE)
            .scope("orders.read")
            .clientSettings(ClientSettings.builder()
                    .requireProofKey(true)
                    .requireAuthorizationConsent(true)
                    .build())
            .tokenSettings(TokenSettings.builder()
                    .authorizationCodeTimeToLive(Duration.ofMinutes(5))
                    .accessTokenTimeToLive(Duration.ofMinutes(10))
                    .refreshTokenTimeToLive(Duration.ofHours(8))
                    .reuseRefreshTokens(false)
                    .build())
            .build();
}
~~~

Đây là một **phương thức factory** để đặt trong class Java, chưa phải file tự chạy độc lập. Các TTL là quyết định chính sách minh họa, cần điều chỉnh theo độ nhạy API, session và khả năng thu hồi. `reuseRefreshTokens(false)` yêu cầu cấp token mới theo chính sách khi dùng refresh token; client phải lưu và thay refresh token đúng cách, không giả định một refresh token cũ dùng được vô hạn.

**Vì sao `requireProofKey(true)` dù client có secret?** PKCE ràng buộc authorization code với bên khởi tạo giao dịch, bổ sung bảo vệ nếu code bị chặn. Secret xác thực client tại token endpoint nhưng không thay thế PKCE, `state` hay đối chiếu redirect URI.

### 3.2. Client Spring Security tương ứng

Cấu hình này thuộc **ứng dụng `portal-web`** chạy tại `https://portal.example.vn`, không thuộc Authorization Server:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          portal:
            provider: company-oidc
            client-id: portal-web
            client-secret: ${PORTAL_WEB_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - orders.read
        provider:
          company-oidc:
            issuer-uri: https://login.example.vn
~~~

Khi `{baseUrl} = https://portal.example.vn` và `{registrationId} = portal`, client tạo callback `https://portal.example.vn/login/oauth2/code/portal`. Redirect URI gửi trong authorization request phải khớp chính xác giá trị đã đăng ký; reverse proxy phải cung cấp public scheme/host chính xác. `issuer-uri` cho phép Spring Security tìm metadata/endpoint OIDC qua discovery nếu OP đã bật OIDC.

Bí mật `PORTAL_WEB_CLIENT_SECRET` là **bản rõ mà phía client giữ**; Authorization Server lưu bản **hash** của chính giá trị đó (mục 5). Không trộn lẫn secret được cấp cho client này với secret của client khác.

## 4. Khai báo client dành cho giao tiếp service-to-service

Worker `billing-job` là **confidential client** gọi API bằng Client Credentials. Nó xác thực bằng một credential riêng, không có redirect từ trình duyệt và không dùng scope `openid`.

~~~java
static RegisteredClient machineClient(String encodedClientSecret) {
    return RegisteredClient.withId("registration-billing-job")
            .clientId("billing-job")
            .clientName("Billing background job")
            .clientSecret(encodedClientSecret)
            .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
            .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
            .scope("invoices.read")
            .scope("invoices.write")
            .tokenSettings(TokenSettings.builder()
                    .accessTokenTimeToLive(Duration.ofMinutes(5))
                    .build())
            .build();
}
~~~

Yêu cầu lấy token tương ứng (giá trị Base64/credential được công cụ HTTP tạo từ `client_id:client_secret`; không đặt secret thật trong lệnh hoặc log):

~~~http
POST /oauth2/token HTTP/1.1
Host: login.example.vn
Authorization: Basic BASE64_CLIENT_CREDENTIALS_REDACTED
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=invoices.read
~~~

Authorization Server xác thực client, đối chiếu grant type và scope, rồi cấp access token theo policy. **Không có authorization code, redirect URI, consent của người dùng hoặc ID Token** trong Client Credentials. Resource Server vẫn phải giới hạn hành động theo scope, audience và chính sách nghiệp vụ của API; việc client được phép xin `invoices.write` không tự cho mọi request ghi dữ liệu.

Đối với workload có thể dùng khóa công khai hoặc chứng chỉ thay secret chia sẻ, cân nhắc phương thức xác thực client mạnh hơn (ví dụ `private_key_jwt`/mTLS với hỗ trợ giao thức và hạ tầng phù hợp). Cách khai báo sẽ khác ví dụ `CLIENT_SECRET_BASIC`.

## 5. Mã hóa client secret và tạo repository trong bộ nhớ

### 5.1. Bảo vệ secret đúng mục đích

`RegisteredClient.clientSecret` trong Spring Authorization Server nên là chuỗi **đã băm** bằng `PasswordEncoder` hỗ trợ đối chiếu, ví dụ `{bcrypt}...`. Authorization Server không cần giải mã client secret để cấp token: nó chỉ kiểm tra secret được client gửi có khớp hash không. Bản rõ cần nằm ở nơi client có quyền truy cập (secret manager/biến môi trường được kiểm soát), không lưu trong Git hay artifact.

Tránh `{noop}my-secret`, secret có thể đoán được, một secret dùng chung cho tất cả client hoặc in `RegisteredClient`/HTTP Authorization header vào log. Secret của client và private signing key JWT/ID Token là **hai loại credential khác nhau**.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.oauth2.server.authorization.client.InMemoryRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;
import org.springframework.util.StringUtils;

@Configuration(proxyBeanMethods = false)
class ClientRegistryConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    RegisteredClientRepository registeredClientRepository(
            PasswordEncoder passwordEncoder,
            @Value("${PORTAL_WEB_CLIENT_SECRET}") String webSecret,
            @Value("${BILLING_JOB_CLIENT_SECRET}") String workerSecret) {

        // Chỉ kiểm tra điều kiện; không ghi giá trị secret vào thông báo lỗi.
        if (!StringUtils.hasText(webSecret)
                || !StringUtils.hasText(workerSecret)) {
            throw new IllegalStateException("Missing mandatory client credentials");
        }

        RegisteredClient portal = webClient(passwordEncoder.encode(webSecret));
        RegisteredClient billing = machineClient(passwordEncoder.encode(workerSecret));

        return new InMemoryRegisteredClientRepository(portal, billing);
    }

    // Đặt hai factory webClient(...) và machineClient(...) ở mục 3, 4
    // vào bên trong class này.
}
~~~

**Lưu ý về phạm vi mã:** Các phương thức `webClient(...)` và `machineClient(...)` ở mục trước phải được đưa vào cùng class (hoặc một utility class) để cấu hình ví dụ biên dịch. Một Authorization Server đầy đủ còn cần `SecurityFilterChain`, issuer, cơ chế xác thực người dùng (với Authorization Code), JWKSource và authorization/consent service. Đoạn này chỉ minh họa **đăng ký client**.

Bộ ghi nhớ in-memory phù hợp demo, local development và test tích hợp đơn giản. Dữ liệu không bền vững qua restart, không tự đồng bộ giữa nhiều instance, và trong ví dụ này giá trị hash được tạo lại mỗi khi khởi động. Client secret gốc không đổi nhưng `{bcrypt}` hash có thể khác vì salt ngẫu nhiên — đó là hành vi bình thường. Không dựa vào repository này làm nguồn dữ liệu client production.

### 5.2. `ClientAuthenticationMethod.NONE` cho public client

Ứng dụng SPA/native không thể giữ một client secret bí mật dài hạn, vì mã ứng dụng và cấu hình có thể bị đọc. Có thể đăng ký public client như sau:

~~~java
RegisteredClient spa = RegisteredClient.withId("registration-frontend-spa")
        .clientId("frontend-spa")
        .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
        .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri("https://spa.example.vn/oauth2/callback")
        .scope(OidcScopes.OPENID)
        .scope(OidcScopes.PROFILE)
        .clientSettings(ClientSettings.builder()
                .requireProofKey(true)
                .requireAuthorizationConsent(true)
                .build())
        .build();
~~~

Với public client, `clientSecret` được **bỏ trống**, không dùng một secret hardcoded rồi coi là confidential. Client phải dùng PKCE; quản lý token trong trình duyệt/native app cần bổ sung biện pháp bảo vệ XSS, session, redirect, lưu token và refresh token theo threat model. Nếu ứng dụng web có thể dùng **Backend for Frontend (BFF)**, cân nhắc giữ token ở backend và dùng cookie phiên được bảo vệ.

## 6. `RegisteredClientRepository` hoạt động ra sao?

Repository là điểm tra cứu/lưu đăng ký client được tích hợp vào Authorization Server. Giao diện cốt lõi:

~~~java
public interface RegisteredClientRepository {
    void save(RegisteredClient registeredClient);
    RegisteredClient findById(String id);
    RegisteredClient findByClientId(String clientId);
}
~~~

Đây là **hình thức API rút gọn để giải thích**, không phải tuyên bố lớp trong thư viện chỉ có đúng ba thành viên ở mọi phiên bản. Trong giao thức:

- Request `/oauth2/authorize` hoặc `/oauth2/token` gửi `client_id`; Authorization Server tra cứu bằng `findByClientId(clientId)`.
- Công cụ quản trị có thể dùng `findById(id)` để truy cập bản ghi theo khóa nội bộ.
- Quy trình provisioning/rotation có kiểm soát gọi `save(RegisteredClient)` để lưu bản ghi mới hoặc cập nhật theo cơ chế của implementation.

~~~mermaid
sequenceDiagram
    participant Admin as Provisioning / Admin
    participant Repo as RegisteredClientRepository
    participant Client as OAuth Client
    participant AS as Authorization Server

    Admin->>Repo: save(RegisteredClient)
    Note over Repo: id nội bộ, client_id, hash secret, grant, scope, settings
    Client->>AS: /oauth2/authorize hoặc /oauth2/token, client_id
    AS->>Repo: findByClientId(client_id)
    Repo-->>AS: RegisteredClient hoặc null
    AS->>AS: Kiểm tra client authentication, grant, URI, scopes và policy
    AS-->>Client: Cấp token / authorization code hoặc lỗi giao thức
~~~

**Không nhầm repository đăng ký client với các kho khác:**

| Thành phần | Lưu gì? | Chức năng |
|---|---|---|
| `RegisteredClientRepository` | Định danh, phương thức xác thực, secret hash, redirect, scopes, client/token settings | Chính sách và danh tính **client** |
| `OAuth2AuthorizationService` | Authorization, authorization code, token và trạng thái liên quan | Vòng đời **ủy quyền/token** |
| `OAuth2AuthorizationConsentService` | Consent của người dùng với client và các quyền được chấp thuận | Quản lý **sự đồng ý** |
| `UserDetailsService` / identity provider | Người dùng và credential/claims theo hạ tầng xác thực | Xác thực **end user** |

Một dự án có `JdbcRegisteredClientRepository` **chưa đồng nghĩa** authorization code/token/consent đã được lưu bền vững: cần cấu hình các service tương ứng. Điều này rất quan trọng khi chạy nhiều pod.

## 7. Chọn in-memory, JDBC hay custom repository

| Repository | Khi nào phù hợp | Lưu ý |
|---|---|---|
| `InMemoryRegisteredClientRepository` | Tutorial, unit/integration test, demo một instance | Không tồn tại qua restart; thay đổi không chia sẻ giữa các instance |
| `JdbcRegisteredClientRepository` | Sản phẩm có RDBMS và nhu cầu quản trị client bền vững | Cần tạo schema/migration, backup, truy cập DB an toàn, cơ chế provisioning |
| Custom `RegisteredClientRepository` | Đã có client registry riêng, multi-tenant, policy phức tạp hoặc nguồn dữ liệu khác | Phải giữ đúng hợp đồng truy xuất, phân tách tenant, kiểm soát cache/concurrency và bảo mật dữ liệu |

### 7.1. Sử dụng JDBC trong ứng dụng Spring Boot

Một bean phù hợp với dự án đã có `DataSource`:

~~~java
import javax.sql.DataSource;

import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.server.authorization.client.JdbcRegisteredClientRepository;
import org.springframework.security.oauth2.server.authorization.client.RegisteredClientRepository;

@Bean
RegisteredClientRepository registeredClientRepository(DataSource dataSource) {
    return new JdbcRegisteredClientRepository(new JdbcTemplate(dataSource));
}
~~~

**Đây là biến thể thay thế bean in-memory ở mục 5.** Không đăng ký cả hai `RegisteredClientRepository` làm ứng viên mặc định nếu chưa có quy tắc chọn bean rõ ràng. Với JDBC cần:

1. Thêm Spring JDBC và driver cơ sở dữ liệu phù hợp.
2. Tạo schema cho bảng đăng ký client bằng **migration được kiểm soát** (Flyway/Liquibase hoặc công cụ tương đương). Dùng tài liệu/SQL schema tương thích **chính phiên bản Spring Authorization Server** đang chạy; kiểm tra kiểu cột, độ dài, JSON/LOB và SQL dialect.
3. Cấu hình DataSource qua secret store, quyền DB tối thiểu, TLS và backup theo chính sách.
4. Tạo bản ghi client bằng công cụ provisioning/migration quản trị với `clientId` duy nhất, `id` nội bộ ổn định và secret hash thích hợp.
5. Cấu hình riêng dịch vụ lưu authorization và consent nếu cần hoạt động nhiều instance/khôi phục sau restart.

Không nên chạy mã “seed lại tất cả client” ở **mỗi startup** rồi ghi đè secret, redirect và token settings hiện có. Trong môi trường nhiều pod, hành vi đó có thể làm client không đăng nhập được hoặc thay đổi quyền ngoài ý muốn.

### 7.2. Provision client một lần bằng repository

Giả sử `repository` là JDBC và `client` là object xây dựng từ quy trình cấp client đã được quản trị:

~~~java
RegisteredClient existing = repository.findByClientId("portal-web");

if (existing == null) {
    repository.save(client); // Chỉ dùng trong lệnh provisioning có kiểm soát.
} else {
    // Không tự overwrite một bản ghi đang được sử dụng.
    // Đối chiếu owner, policy và version trước khi quyết định cập nhật.
}
~~~

Mã trên chỉ diễn tả **idempotent intent** cơ bản, không tự giải quyết race condition nếu hai tiến trình provisioning chạy đồng thời. Dùng unique constraint trên `client_id`, transaction và quy trình quản lý phiên bản/đồng bộ phù hợp; không dùng check-then-insert như giải pháp đầy đủ cho cạnh tranh ghi.

Với bản ghi hiện có, `RegisteredClient` là immutable: dùng `RegisteredClient.from(existing)` tạo builder để chỉnh field có chủ đích, sau đó `repository.save(updated)`. Cần xem xét dữ liệu đang được sử dụng, quy tắc thay đổi URI, scope, secret và hoạt động đồng thời.

### 7.3. Tính chất quan trọng của custom repository

Nếu lưu từ một bảng riêng hoặc từ secret/config service, implementation phải:

- Trả chính xác RegisteredClient theo `id` và `clientId`, xử lý không tìm thấy đúng hợp đồng, không suy ID từ request thiếu tin cậy.
- Bảo đảm uniqueness của `clientId`, isolation giữa tenant và môi trường; tránh truy xuất client của tenant khác khi cùng ID cục bộ.
- Duy trì persistence/consistency và khả năng nhìn thấy thay đổi giữa các instance; nếu có cache thì có TTL/invalidation phù hợp khi thu hồi client.
- Bảo toàn toàn bộ grant types, authentication methods, redirect URIs, scopes, `ClientSettings` và `TokenSettings`, không làm rơi field khi serialize/deserialize.
- Không lưu client secret bản rõ khi chỉ cần so khớp hash. Bảo vệ nội dung repository, audit thay đổi và hạn chế log dữ liệu nhạy cảm.

## 8. Xây dựng quy trình cấp phát và quản trị client

Một quy trình cấp client thực tế nên đi từ **yêu cầu nghiệp vụ** đến **policy được xét duyệt**, rồi mới đưa vào builder. Ví dụ:

~~~mermaid
flowchart LR
    Request["Đội ứng dụng yêu cầu<br/>client type + use case"] --> Review["Xét policy<br/>grants, authentication,<br/>redirect, scope"]
    Review --> Credentials["Cấp client ID và credential<br/>qua kênh an toàn"]
    Credentials --> Build["RegisteredClient builder<br/>ClientSettings + TokenSettings"]
    Build --> Repo["RegisteredClientRepository.save"]
    Repo --> Test["Kiểm thử OAuth2/OIDC flow<br/>positive + negative"]
    Test --> Audit["Ghi audit owner, version,<br/>ngày cấp, lịch rotation"]
~~~

### 8.1. Các trường cần quản lý ở cấp tổ chức

Ngoài `RegisteredClient`, hệ thống quản trị nên quản lý owner/application, môi trường, mục đích sử dụng, ticket phê duyệt, lần đăng ký và trạng thái hoạt động, lịch rotation. Các field đó có thể ở một bảng quản trị riêng nếu API chuẩn không chứa đủ metadata. **Không thêm tùy tiện field vào `RegisteredClient` trong ví dụ rồi kỳ vọng JDBC repository chuẩn tự lưu được.**

Quy tắc phê duyệt thường gồm:

- Chỉ cho phép `authorization_code` với các ứng dụng có tương tác trình duyệt và callback đã kiểm soát; dùng PKCE.
- Chỉ cấp `client_credentials` cho machine client có danh tính và chủ sở hữu rõ ràng; scope tối thiểu, TTL phù hợp.
- Dành `ClientAuthenticationMethod.NONE` cho public client hợp lệ; không chấp nhận secret hardcoded trong SPA/native app là cơ chế xác thực an toàn.
- Chỉ cho yêu cầu những scope cần thiết; định nghĩa rõ scope được Resource Server kiểm tra.
- Hạn chế `redirect_uri` và `post_logout_redirect_uri` theo môi trường, scheme/host/path chính xác; tránh wildcard/open redirect.
- Xem xét chính sách consent, refresh token, token lifetime và thu hồi client phù hợp threat model.

### 8.2. Cập nhật client secret

Khi cần thay secret, phía confidential client phải nhận bản rõ mới qua kênh bảo mật; Authorization Server thay **hash** tương ứng tại repository.

~~~java
RegisteredClient existing = repository.findByClientId("portal-web");
if (existing == null) {
    throw new IllegalArgumentException("Unknown client");
}

// newSecret được lấy từ quy trình quản trị/secret store; không hardcode và không log.
RegisteredClient updated = RegisteredClient.from(existing)
        .clientSecret(passwordEncoder.encode(newSecret))
        .build();

repository.save(updated);
~~~

Đây là minh họa cập nhật trong một **quy trình quản trị đã được bảo vệ quyền**, không phải endpoint REST công khai. Mặc định một `RegisteredClient` có **một** trường `clientSecret`; đừng giả định server sẽ chấp nhận đồng thời cả secret cũ và secret mới. Cần kế hoạch rollout phía client và server, hoặc cơ chế overlap được thiết kế thêm nếu không thể cắt đổi đồng thời. Xoay vòng client secret **không** tự thu hồi mọi access token đã phát trước đó và không phải thao tác thay private signing key.

### 8.3. Vô hiệu hóa, xóa và thu hồi

Giao diện `RegisteredClientRepository` chuẩn tập trung vào `save`/find, không định nghĩa chung một API `delete`/disable cho mọi implementation. Hệ thống quản trị muốn vô hiệu hóa client cần thiết kế chính sách riêng (ví dụ trạng thái active tại lớp quản lý, thay đổi cơ chế xác thực, chặn tại luồng token), đồng thời đánh giá các authorization/token đã phát.

Các trường hợp cần xét:

- Vô hiệu hóa **client** ngăn phát token mới theo chính sách, nhưng access token tự chứa (JWT) còn hạn có thể tiếp tục được Resource Server chấp nhận cho đến khi hết hạn hoặc có kiểm tra thu hồi riêng.
- Thu hồi refresh token/authorization cần thao tác qua cơ chế dữ liệu/endpoint thu hồi được hỗ trợ, không chỉ sửa một field của `RegisteredClient`.
- Xóa thô dòng DB khi các authorization/consent còn tham chiếu client có thể tạo dữ liệu mồ côi và khó audit. Cần quy trình kết thúc vòng đời có kiểm soát.

## 9. Cấu hình có tính an toàn và dễ vận hành

### 9.1. Sai lầm dễ gặp khi dùng builder

| Sai lầm | Hậu quả | Cách làm phù hợp |
|---|---|---|
| `.clientSecret("{noop}secret")` trong production | Bí mật bản rõ hoặc yếu bị lộ khi truy xuất DB/log | Tạo secret ngẫu nhiên đủ mạnh, hash bằng `PasswordEncoder`, bảo vệ bản rõ phía client |
| Dùng một `client_id` cho cả web, mobile và batch job | Không phân quyền và thu hồi từng workload | Đăng ký client riêng theo ứng dụng và trust level |
| Đăng ký `authorization_code` nhưng thiếu redirect URI hoặc callback sai | Lỗi authorization/redirect, tăng rủi ro nếu nới validation | Đăng ký callback chính xác, dùng HTTPS public URI |
| Bỏ PKCE cho client thực hiện code flow | Tăng nguy cơ sử dụng authorization code bị chặn | `requireProofKey(true)` và triển khai code challenge/verifier |
| Đăng ký client public với secret hardcoded | Kẻ tấn công đọc secret từ app phân phối cho người dùng | Dùng `ClientAuthenticationMethod.NONE` và PKCE |
| Đăng ký mọi scope cho mọi client | Quyền truy cập quá rộng nếu API thiếu policy chặt | Cấp scope theo nhu cầu và kiểm tra lại ở Resource Server |
| Dùng `openid` cho client credentials | Nhầm danh tính người dùng với danh tính ứng dụng | Dùng scope nghiệp vụ và access token cho M2M |
| Nhầm `id` và `clientId` | Không tra cứu/định danh client đúng | `id` là định danh bản ghi, `clientId` là giao thức OAuth |
| Tạo RegisteredClient bằng builder nhưng không save | Authorization Server không tìm được client | Truyền vào InMemory repository hoặc `save()` vào repository bền vững |
| Seed client mỗi lần startup bằng secret mới | Các client đang chạy lỗi xác thực ngắt quãng | Provision một lần, rotate có phê duyệt và migration rõ ràng |
| Chỉ triển khai JDBC repository cho client | Token/consent không tồn tại qua restart nếu service khác vẫn in-memory | Cấu hình persistence toàn hệ thống theo nhu cầu |

### 9.2. Bảo vệ môi trường và secret

- Giữ giá trị client secret bản rõ trong secret store hoặc cơ chế inject runtime an toàn, phân quyền theo client và môi trường; không commit vào `application.yml`, Git, CI artifact hoặc Docker image.
- Cấu hình DB/JDBC bằng credentials khác với client secret; dùng TLS, quyền DB tối thiểu, backup và audit thay đổi client registration.
- Không log Authorization header, token request body, client secret hay `RegisteredClient` đầy đủ. Giới hạn Actuator `/env`, `/configprops`, debug logs và quyền truy cập kho client.
- Tách local/staging/production bằng issuer, redirect URI, secret và policy độc lập. `https://portal.example.vn/callback` không thể thay tùy ý bằng `http://localhost:8080/callback` ở môi trường khác.
- Với nhiều pod, repository và các kho authorization/consent phải nhất quán; kiểm tra cache khi cập nhật hoặc thu hồi client.

## 10. Kiểm thử client registration

Chỉ tạo builder hợp lệ trong unit test **không đủ**. Cần kiểm tra Authorized/Unauthorized Flow trên Authorization Server thật hoặc integration test. Các ca dưới đây có thể dùng client và secret **giả** trong môi trường test.

| Ca kiểm thử | Đầu vào/tình huống | Kỳ vọng |
|---|---|---|
| Lưu/tra cứu client | Save `portal-web`; `findByClientId("portal-web")` | Trả đúng RegisteredClient với grants/scopes/settings |
| Lookup không tồn tại | `findByClientId("unknown")` | Không tìm thấy; giao thức từ chối yêu cầu không đăng ký |
| Confidential authentication | `portal-web` gửi đúng/ sai client secret tại token endpoint | Đúng: tiếp tục kiểm tra grant; sai: `invalid_client` |
| Authorization Code + PKCE | Yêu cầu `portal-web` với `code_challenge=S256` hợp lệ | Có thể cấp code và đổi token khi state, redirect, PKCE, client auth đều hợp lệ |
| Thiếu/sai PKCE | Yêu cầu client bắt buộc PKCE mà không có challenge hoặc dùng verifier sai | Bị từ chối ở bước thích hợp |
| Redirect URI sai | Đổi scheme/host/trailing slash khỏi URI đã đăng ký | Không redirect authorization code tới URI không tin cậy |
| Scope vượt quyền | Xin scope chưa thuộc client registration | Yêu cầu bị từ chối/thu hẹp theo xử lý giao thức và chính sách |
| Client Credentials | `billing-job` xin `invoices.read` | Có access token phù hợp; không có tương tác đăng nhập hoặc ID Token |
| Sai grant | `billing-job` gửi `grant_type=authorization_code` | Bị từ chối `unauthorized_client`/lỗi phù hợp |
| Public client | `frontend-spa` dùng `ClientAuthenticationMethod.NONE` và PKCE | Code flow được chấp nhận theo policy; không yêu cầu secret |
| Bền vững | Lưu `portal-web` trong JDBC, restart instance | Truy vấn lại thấy cùng ID, URI, grants và settings |
| Rotation | Thay client secret của `portal-web` qua quy trình quản trị | Secret mới hoạt động, secret cũ bị từ chối theo thời điểm chuyển đổi |
| Multi-instance | Ghi client từ một node, đọc từ node khác | Cùng phiên bản client, không xảy ra lỗi xác thực bất thường |
| OIDC | `portal-web` xin scope `openid` và đổi code hợp lệ | Nhận ID Token, RP xác minh `iss`, `aud`, chữ ký, `exp`, `nonce` khi áp dụng |

### 10.1. Kiểm tra repository trong Spring test

Đoạn sau là ý tưởng unit test ngắn cho registry, không phải bài test đầy đủ của giao thức:

~~~java
@Test
void storesClientWithPkceAndExpectedGrant() {
    PasswordEncoder encoder =
            PasswordEncoderFactories.createDelegatingPasswordEncoder();

    RegisteredClientRepository repository =
            new InMemoryRegisteredClientRepository(
                    webClient(encoder.encode("test-only-secret")));

    RegisteredClient found = repository.findByClientId("portal-web");

    assertNotNull(found);
    assertEquals("registration-portal-web", found.getId());
    assertTrue(found.getAuthorizationGrantTypes()
            .contains(AuthorizationGrantType.AUTHORIZATION_CODE));
    assertTrue(found.getClientSettings().isRequireProofKey());
    assertTrue(encoder.matches("test-only-secret", found.getClientSecret()));
}
~~~

Thêm imports JUnit 5, Spring Security và các factory/helper tương ứng vào test class. `test-only-secret` ở đây chỉ là **dữ liệu giả của unit test**, không dùng trong deployment. Unit test này kiểm tra mapping và lưu registry; nó **không** chứng minh token endpoint, user login, PKCE validation, consent hay JWT signing thực sự hoạt động.

### 10.2. Xử lý lỗi thường gặp

| Triệu chứng | Nguyên nhân hay gặp | Cách kiểm tra |
|---|---|---|
| `invalid_client` tại `/oauth2/token` | Secret sai, cách xác thực sai, hash thiếu prefix encoder, client chưa đăng ký | So sánh `client_id`, authentication method, secret provisioning và password encoder |
| `unauthorized_client` | Grant type không thuộc client registration | Kiểm tra `authorizationGrantTypes` và `grant_type` thực tế |
| `invalid_redirect_uri` hoặc lỗi authorization request | Redirect URI khác chính xác giá trị đăng ký | Đối chiếu scheme, host, port, path, dấu `/`, query và cấu hình proxy |
| Thiếu ID Token | Client/request không dùng scope `openid` hoặc flow OIDC chưa bật | Kiểm tra scope được cấp, OIDC configurer và signing key |
| Scope bị từ chối | Scope chưa nằm trong `scopes` hoặc chính sách consent không cho phép | Kiểm tra RegisteredClient, request và Resource Server policy |
| Client biến mất sau restart | Dùng repository in-memory | Chuyển sang JDBC/custom persistence và provisioning bền vững |
| Sau rotation lúc được lúc không | Các instance cache/seed secret khác nhau hoặc client rollout lệch | Kiểm tra nguồn dữ liệu chung, cập nhật cache và thời điểm đổi secret |
| Client được cấp token nhưng gọi API 403 | Scope/audience/authorization API không đáp ứng | Kiểm tra access token với Resource Server, không chỉ registry |

## 11. Checklist thiết kế client registration trước production

- [ ] Phân loại client thành web confidential, machine client hoặc public client và có owner rõ ràng.
- [ ] Mỗi client có `client_id` duy nhất và `RegisteredClient.id` ổn định; tránh dùng chung ID/credential giữa môi trường.
- [ ] Chọn authentication method và grant types phù hợp, không cấp grant dư thừa.
- [ ] Bật PKCE cho authorization code, giữ redirect URI chính xác, đăng ký logout URI riêng nếu dùng OIDC.
- [ ] Cấp scope tối thiểu; đối chiếu chính sách audience và authorization ở Resource Server.
- [ ] Lưu hash của client secret confidential, giữ bản rõ trong secret store phía client, có lịch rotation.
- [ ] Thiết lập `ClientSettings` và `TokenSettings` theo yêu cầu bảo mật, trải nghiệm và khả năng thu hồi.
- [ ] Production sử dụng repository bền vững, migrations có kiểm soát và cơ chế provisioning/rollback/audit.
- [ ] Lưu authorization và consent bền vững khi kiến trúc nhiều instance yêu cầu.
- [ ] Kiểm thử lookup, secret sai, grant sai, scope sai, redirect sai, PKCE, OIDC, restart và rotation.

**Câu hỏi tự kiểm tra**

1. Trong `RegisteredClient`, `id` khác `clientId` thế nào? Authorization Server thường tra bằng giá trị nào khi nhận token request?
2. Builder tạo client khác với `RegisteredClientRepository.save(...)` ở đâu?
3. Vì sao `client_credentials` không cần `redirectUri` nhưng `authorization_code` cần URI callback?
4. Nếu SPA có một `client_secret` ghi cứng trong bundle JavaScript, tại sao nó vẫn là public client?
5. `ClientSettings.requireProofKey(true)` và `TokenSettings.accessTokenTimeToLive(...)` tác động đến các bước nào?
6. Vì sao một `JdbcRegisteredClientRepository` không đủ để bảo đảm mọi authorization code/token/consent được lưu sau restart?
7. Khi đổi client secret, vì sao cần quan tâm cả thời điểm rollout và token đã phát trước đó?

## Tài liệu tham khảo

- [Spring Authorization Server — Core Model / Components](https://docs.spring.io/spring-authorization-server/reference/core-model-components.html), đặc biệt `RegisteredClient`, `RegisteredClientRepository`, `OAuth2AuthorizationService` và `OAuth2AuthorizationConsentService`.
- [Spring Authorization Server — Configuration Model](https://docs.spring.io/spring-authorization-server/reference/configuration-model.html), cấu hình endpoint và các service liên quan.
- [Spring Authorization Server — Getting Started](https://docs.spring.io/spring-authorization-server/reference/getting-started.html), ví dụ tạo client và bean căn bản.
- [Spring Security — OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html), cấu hình client và authentication.
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749), client registration, client authentication và grant types.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700), PKCE, redirect URI và quản lý an toàn các luồng cấp quyền.
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252), public native clients và callback.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html), scope `openid`, ID Token và kiểm tra danh tính.
