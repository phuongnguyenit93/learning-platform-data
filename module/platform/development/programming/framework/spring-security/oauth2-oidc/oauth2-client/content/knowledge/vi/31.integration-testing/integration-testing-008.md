# 31.8. Kiểm thử client credentials và scope của downstream

Một ứng dụng Spring Boot không chỉ gọi OAuth2/OIDC Provider để **đăng nhập người dùng**. Nó còn có thể chạy một tác vụ tự động — ví dụ đồng bộ báo cáo, tải danh mục hoặc gửi hóa đơn — cần gọi **downstream API** bằng **quyền của chính ứng dụng**. Trong trường hợp đó, OAuth 2.0 **Client Credentials Grant** là một lựa chọn phổ biến.

Ví dụ:

```text
Reporting Worker (Spring Boot)
    |
    | POST /oauth2/token
    | grant_type=client_credentials
    | scope=reports.read
    | Client authentication: client_id/client_secret
    v
Authorization Server
    |
    | access_token = AT-123
    | token_type   = Bearer
    | expires_in   = 3600
    | scope        = reports.read
    v
Reporting Worker
    |
    | GET /api/reports
    | Authorization: Bearer AT-123
    v
Downstream Resource Server
    |
    +-- token hợp lệ + có reports.read -> 200
    +-- token không hợp lệ -> thường 401
    +-- token hợp lệ nhưng thiếu scope -> thường 403
```

Để **kiểm thử tích hợp** đúng, chúng ta cần chứng minh hai hành vi riêng biệt:

1. **Client credentials flow:** Spring Security dùng đúng `ClientRegistration`, xác thực với token endpoint, yêu cầu những scopes đã cấu hình, xử lý phản hồi token và quản lý token trong `OAuth2AuthorizedClient`.
2. **Downstream authorization:** lời gọi HTTP thực sự mang access token phù hợp; Resource Server (hoặc test double của nó) áp dụng chính sách **issuer/audience/scope** và trả kết quả tương ứng.

Không được dừng ở việc mock:

```java
when(oauth2AuthorizedClientManager.authorize(any()))
    .thenReturn(fakeAuthorizedClient);
```

rồi tuyên bố đã kiểm thử được Client Credentials Grant. Cách mock này hữu ích cho **unit test** của service nhưng **không kiểm tra HTTP token request, client authentication, scope hay cơ chế gắn Bearer token vào downstream request**.

Bài thuộc chương **31. Kiểm thử tích hợp** của module *Spring Security OAuth 2.0 OIDC Client*. Ví dụ chính sử dụng Spring Boot 3.x, Spring Security 6.x, Java 17+, `RestClient`, `OAuth2AuthorizedClientManager`, JUnit 5 và **MockWebServer**. Phần cuối đối chiếu WebClient/Reactive.

> **Phạm vi:** Đây là OAuth2 **Client Credentials**, không phải OIDC interactive login. Không có browser authorization redirect, authorization code, PKCE hay ID Token của end-user trong luồng chuẩn. Các URL, client secrets và access tokens trong bài đều là dữ liệu giả dùng cho môi trường test. Không sử dụng tài khoản thật hoặc tokens production.

---

## 1. Client Credentials Grant giải quyết bài toán gì?

Client Credentials Grant (RFC 6749, mục 4.4) cho phép một **confidential client** được Authorization Server xác thực và cấp access token dựa trên quyền của chính client.

Ứng dụng điển hình:
- Scheduled job đọc báo cáo từ Reporting API;
- Backend đồng bộ inventory giữa hai hệ thống;
- Dịch vụ xử lý sự kiện gọi downstream Audit API;
- Batch job cần truy cập dữ liệu được cấp riêng cho service account;
- Một internal service gọi API khác mà **không đại diện cho end-user cụ thể**.

### 1.1. Phân biệt với Authorization Code + OIDC Login

| Tiêu chí | `authorization_code` + OIDC | **`client_credentials`** |
| --- | --- | --- |
| Ai đang được xác thực? | End-user qua OP, đồng thời có client | **OAuth2 client/service identity** |
| Browser redirect đến AS | Có | **Không cần** |
| `/login/oauth2/code/{registrationId}` | Có trong login flow | Không có |
| `state` và PKCE | Dùng trong authorization redirect/code flow | Không dùng theo cơ chế đó |
| OIDC `nonce` / ID Token | Có thể có | **Không phải thành phần chuẩn của grant này** |
| Token endpoint | Đổi authorization code | Trực tiếp xin token bằng `grant_type=client_credentials` |
| Scope | Theo authorization/user/client policy | Theo **client registration/service permission** |
| Refresh token | Có thể được cấp theo OP policy | **Thông thường không cấp**; RFC 6749 khuyến nghị không cấp refresh token |
| Principal của authorized-client cache | Thường gắn người dùng | Nên dùng **service principal name ổn định** |
| Quyền downstream | Theo user/delegated token | Theo **application/service token** |

**Không dùng client credentials như cách “mượn quyền admin” để thay một user login thất bại.** Grant này không chứng minh user Alice đã xác thực và không cho phép tự gán quyền theo Alice.

### 1.2. Ba vai trò không thể trộn

- **OAuth2 Client:** Spring Boot Reporting Worker, cần lấy token.
- **Authorization Server (AS):** xác thực client và phát access token với scopes được cấp.
- **Resource Server (RS):** Reporting API nhận Bearer token, xác minh token và kiểm tra quyền truy cập.

Trong thực tế AS và RS có thể thuộc cùng sản phẩm/cluster nhưng **quyền và trách nhiệm giao thức khác nhau**.

---

## 2. Những gì một integration test tốt phải đo

```mermaid
sequenceDiagram
    autonumber
    participant Test as JUnit Test
    participant App as Spring OAuth2 Client/RestClient
    participant AS as Mock Token Endpoint
    participant API as Mock Downstream API

    Test->>AS: Enqueue token response (scopes granted)
    Test->>API: Enqueue 200 / 401 / 403 response
    Test->>App: Invoke downstream client/service
    App->>AS: POST /token, client auth, grant_type, scope
    AS-->>App: access_token + token_type + expires_in + scope
    App->>App: Save OAuth2AuthorizedClient
    App->>API: GET /reports with Bearer access token
    API-->>App: HTTP response
    App-->>Test: Return result / surface error
    Test->>AS: Assert token request form and client auth
    Test->>API: Assert Authorization header, path, method
    Test->>App: Assert granted scopes/cache/error handling
```

Một test end-to-end **giữa các thành phần của Spring Client và HTTP giả lập** cần quan sát:

| Giai đoạn | Assertion |
| --- | --- |
| Registration | Đúng `registrationId`, token URI và grant `client_credentials` |
| Client authentication | AS nhận client authentication đúng method, ví dụ `client_secret_basic` |
| Token request | HTTP POST `application/x-www-form-urlencoded`, `grant_type=client_credentials` |
| Requested scopes | Form gửi những scopes đúng policy của registration |
| Token response | Chấp nhận `Bearer` token, expiry và **granted scopes** |
| Authorized client | Token được gắn với registration và service principal thích hợp |
| Outbound downstream request | Bearer token được đặt trong `Authorization` header |
| API authorization | 200 nếu token được chấp nhận/đủ quyền; 401/403 theo contract |
| Token reuse | Không xin lại token vô lý khi token còn hạn và cache đúng |
| Failure isolation | Token endpoint lỗi khác downstream 401/403; không gửi token sang host lạ |

**Quan trọng:** Một MockWebServer chỉ trả HTTP 403 theo script **không chứng minh Resource Server production đang kiểm tra scopes thật**. Đây là **contract test** cho cách client phản ứng. Để kiểm tra Spring Resource Server thực thi scopes cần một test riêng đi qua SecurityFilterChain, JWT decoder/introspection và authorization rules phù hợp.

## 3. Scope: “yêu cầu”, “được cấp” và “được thực thi”

Trong OAuth2 có ba tập quyền dễ bị nhầm:

```text
REQUESTED:
  Client registration yêu cầu:
    reports.read reports.export

GRANTED:
  Authorization Server thực sự cấp:
    reports.read

ENFORCED:
  Resource Server endpoint /reports/export đòi:
    reports.export

Kết quả:
  Token hợp lệ nhưng thiếu reports.export -> 403 insufficient_scope
```

| Khái niệm | Nơi xác định | Vai trò |
| --- | --- | --- |
| **Requested scope** | `ClientRegistration.getScopes()` hoặc token request | Điều client mong muốn |
| **Granted scope** | Token response `scope`, token metadata/claims theo AS contract | Điều AS thực sự cấp |
| **Required scope** | Resource Server authorization policy | Điều endpoint đòi hỏi |

### 3.1. Client xin scope không có nghĩa chắc chắn được cấp

```yaml
scope:
  - reports.read
  - reports.export
```

chỉ là cấu hình **client muốn xin**. AS có thể từ chối bằng `invalid_scope` hoặc cấp tập scopes hẹp hơn theo policy.

Token response ví dụ:

```json
{
  "access_token": "TEST-ACCESS-TOKEN",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "reports.read"
}
```

Nếu ứng dụng vẫn cố gọi `/reports/export` đòi `reports.export`, kết quả nên bị Resource Server chặn.

### 3.2. Token response có thể không chứa scope

Theo RFC 6749, token response cần trả trường `scope` **nếu scope được cấp khác scope đã yêu cầu**; nếu giống nhau, trường này có thể được bỏ.

Điều đó có nghĩa:
- Đừng xây parser tự viết đòi `scope` luôn có mặt;
- Đừng suy luận một response thiếu `scope` có nghĩa “toàn quyền”;
- Đừng lấy nguyên `ClientRegistration.getScopes()` rồi tuyên bố đó là granted scopes nếu chưa xem contract của AS/client library;
- Khi kiểm thử reduction/scope narrowing, hãy trả **`scope` tường minh**.

### 3.3. JWT claims `scope` và `scp`

Nhiều AS phát JWT access token chứa:

```json
{
  "iss": "https://auth.example.test/issuer",
  "sub": "reporting-worker",
  "aud": ["https://reports-api.example.test"],
  "scope": "reports.read reports.export",
  "exp": 1893456000
}
```

Một số provider dùng `scp` (chuỗi hoặc collection theo contract). Spring Resource Server có thể map scopes được nhận diện sang `SCOPE_*` authorities.

Ví dụ:
- `reports.read` → `SCOPE_reports.read`;
- `reports.export` → `SCOPE_reports.export`.

**Đừng mặc định claim role, nhóm hoặc permissions nào cũng là OAuth2 scope**, và đừng coi `ROLE_ADMIN` tương đương `SCOPE_reports.export`.

### 3.4. Audience cũng là điều kiện quan trọng

Ngay cả khi token có `reports.read`, downstream phải xác minh token được cấp **cho Resource Server phù hợp**, ví dụ `aud=https://reports-api.example.test`.

Một token có scope trùng tên nhưng audience của Payments API **không được chấp nhận** bởi Reports API. Scope đúng **không thay** issuer, audience, signature, expiry hoặc token status validation.

---

## 4. Cấu hình Spring Boot cho client credentials

Giả sử ứng dụng cần gọi Reporting API:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-machine:
            provider: reports-as
            client-id: ${REPORTS_CLIENT_ID}
            client-secret: ${REPORTS_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read
              - reports.export
        provider:
          reports-as:
            token-uri: https://auth.example.test/oauth2/token
```

**Giải thích:**

- `reports-machine`: `registrationId` để service chọn client;
- `reports-as`: khóa cấu hình Authorization Server;
- `client-id` / `client-secret`: credential của confidential client;
- `client_secret_basic`: xác thực client bằng HTTP Basic tại token endpoint;
- `client_credentials`: client xin token trực tiếp, không login browser;
- `scope`: scopes client yêu cầu;
- `token-uri`: endpoint AS để nhận token.

Khác OIDC Login, registration client credentials **không cần** `redirect-uri` hoặc `authorization-uri` cho flow này.

### 4.1. Không gửi client secret đến Resource Server

```text
AS token request:
  Authorization: Basic base64(client-id:client-secret)
  grant_type=client_credentials

Downstream API request:
  Authorization: Bearer <access-token>
```

**Client secret không phải Bearer token của API**. Downstream chỉ nhận access token, không nhận `client_secret`.

### 4.2. Client authentication methods có thể khác

AS có thể yêu cầu:
- `client_secret_basic`;
- `client_secret_post`;
- `private_key_jwt`;
- mTLS client authentication;
- Method riêng được AS hỗ trợ theo tài liệu.

Đừng thay method trong test để “làm cho pass” nếu production sử dụng phương thức khác. Mỗi method có yêu cầu bảo vệ secrets/keys khác nhau. Ví dụ của bài dùng Basic vì dễ minh họa; test thực tế phải theo contract đúng AS.

### 4.3. Không cấu hình scope quá rộng

Một batch chỉ cần đọc báo cáo không nên xin:

```text
reports.read reports.write reports.export reports.delete admin
```

nếu không có nhu cầu. Cấu hình scopes tối thiểu giúp giảm tác động khi access token bị lộ.

---

## 5. Các thành phần Spring Security Client liên quan

| Component | Chức năng |
| --- | --- |
| `ClientRegistrationRepository` | Lưu metadata registration |
| `OAuth2AuthorizedClientProvider` | Strategy xử lý grant, ví dụ `clientCredentials()` |
| **`OAuth2AuthorizedClientManager`** | Điều phối lấy/làm mới token và lưu authorized client |
| `OAuth2AuthorizedClientService` | Lưu `OAuth2AuthorizedClient` theo registration/principal |
| `OAuth2AuthorizedClient` | Registration + access token, có thể refresh token |
| **`AuthorizedClientServiceOAuth2AuthorizedClientManager`** | Manager phù hợp tác vụ/background không có HttpServletRequest |
| `DefaultOAuth2AuthorizedClientManager` | Manager thiết kế cho servlet request context |
| `OAuth2ClientHttpRequestInterceptor` | Gắn Bearer token cho `RestClient` |
| `RequestAttributeClientRegistrationIdResolver` | Lấy registration ID từ RestClient request attributes |
| `RequestAttributePrincipalResolver` | Lấy service principal name từ RestClient request attributes |

### 5.1. Vì sao dùng AuthorizedClientServiceOAuth2AuthorizedClientManager?

Một scheduled job chạy:

```java
@Scheduled(fixedDelayString = "PT15M")
void syncReports() {
    // Không có HttpServletRequest của end-user ở đây.
}
```

`DefaultOAuth2AuthorizedClientManager` thường gắn với servlet request context. Khi không có HTTP request, Spring Security 6.x khuyến nghị **`AuthorizedClientServiceOAuth2AuthorizedClientManager`**, sử dụng `OAuth2AuthorizedClientService` để lưu token theo client/principal.

### 5.2. Bean manager chuyên client credentials

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
class MachineClientConfig {

    @Bean
    OAuth2AuthorizedClientManager machineAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService service) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, service);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

Manager này có thể:
- Xin token khi client chưa được cấp;
- Tái sử dụng token đang hợp lệ theo storage/cache;
- Xin access token mới khi token cũ hết hạn theo policy;
- Lưu thành công qua `OAuth2AuthorizedClientService`.

**Không nhầm việc xin access token mới của client credentials với refresh token grant**. Client Credentials thường không cần refresh token; khi token hết hạn, client lại xác thực với token endpoint để xin access token mới.

---

## 6. Principal name của machine client: không nên dùng user ngẫu nhiên

Trong Spring Security, `OAuth2AuthorizedClient` được lưu thường theo cặp:

```text
(clientRegistrationId, principalName)
```

Với user login:

```text
("google", "alice")
("google", "bob")
```

Với application-level client credentials, nên dùng một **service principal name ổn định**:

```text
("reports-machine", "reports-batch")
```

Nếu mỗi request dùng một principal ngẫu nhiên, cache có thể tạo nhiều access tokens cho cùng một service, làm tăng lưu trữ và token endpoint traffic.

### 6.1. Xin token tường minh trong service

```java
package example.reports;

import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;

@Service
public class MachineTokenService {

    private final OAuth2AuthorizedClientManager manager;

    public MachineTokenService(OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    public OAuth2AuthorizedClient reportsClient() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("reports-machine")
                .principal("reports-batch")
                .build();

        OAuth2AuthorizedClient client = manager.authorize(request);

        if (client == null) {
            throw new IllegalStateException(
                "Client credentials authorization was not completed");
        }
        return client;
    }
}
```

Kết quả `OAuth2AuthorizedClient` có access token và granted scope metadata từ token response theo Spring/AS contract. **Không trả `getTokenValue()` của client này cho browser dưới dạng debug API**.

### 6.2. Test cache phải giữ cùng principal

Nếu test đầu gọi `principal("reports-batch")` nhưng test sau dùng `principal("alice")`, token request có thể phát sinh thêm vì storage keys khác nhau. Đó không nhất thiết là bug cache.

### 6.3. Tách principal máy với OAuth2 end-user principal

Machine access token không chứa bằng chứng Alice đã đăng nhập. Nếu endpoint downstream có dữ liệu theo Alice, phải có business policy/identity propagation riêng được phê duyệt. **Không dùng client credentials token thay user token và tự gắn user ID từ raw HTTP header**.

---

## 7. RestClient: gắn Bearer token tự động

Spring Security 6.5 có `OAuth2ClientHttpRequestInterceptor` tích hợp `RestClient`.

```java
package example.http;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.security.oauth2.client.web.client.RequestAttributePrincipalResolver;
import org.springframework.web.client.RestClient;

@Configuration
class ReportsRestClientConfig {

    @Bean
    RestClient reportsRestClient(
            OAuth2AuthorizedClientManager machineAuthorizedClientManager) {

        OAuth2ClientHttpRequestInterceptor oauth2 =
            new OAuth2ClientHttpRequestInterceptor(
                machineAuthorizedClientManager);

        // Trong scheduled job không phụ thuộc SecurityContext
        // của một user web hiện tại.
        oauth2.setPrincipalResolver(
            new RequestAttributePrincipalResolver());

        return RestClient.builder()
            .baseUrl("https://reports-api.example.test")
            .requestInterceptor(oauth2)
            .build();
    }
}
```

Khi thực hiện request:

```java
import static org.springframework.security.oauth2.client.web.client
    .RequestAttributeClientRegistrationIdResolver.clientRegistrationId;
import static org.springframework.security.oauth2.client.web.client
    .RequestAttributePrincipalResolver.principal;

String response = reportsRestClient.get()
    .uri("/api/reports")
    .attributes(clientRegistrationId("reports-machine"))
    .attributes(principal("reports-batch"))
    .retrieve()
    .body(String.class);
```

Hai attributes có chức năng khác nhau:

- **`clientRegistrationId(...)`:** chọn **client registration**;
- **`principal(...)`:** chọn tên service principal để authorized-client manager/cache sử dụng.

Để chính xác với Java, static imports trên có thể viết trên một dòng:

```java
import static org.springframework.security.oauth2.client.web.client.RequestAttributeClientRegistrationIdResolver.clientRegistrationId;
import static org.springframework.security.oauth2.client.web.client.RequestAttributePrincipalResolver.principal;
```

### 7.1. Vì sao phải chỉ rõ principal resolver?

Theo Spring Security 6.5, `OAuth2ClientHttpRequestInterceptor` mặc định có thể lấy principal từ `SecurityContextHolder`. Với machine-to-machine background call, tốt hơn là chủ động cấu hình `RequestAttributePrincipalResolver` và truyền một tên ổn định.

Đừng phụ thuộc vào người dùng đang đăng nhập ở request khác để lấy application-level token.

### 7.2. Không gửi token đến URL do user kiểm soát

Một RestClient có OAuth2 interceptor có thể gắn Bearer token vào outbound HTTP request. Không cho caller tùy ý cung cấp `https://evil.example.test` làm URI và nhận token của reports-machine.

Nên:
- Dùng base URL đã allowlist;
- Giới hạn các paths được gọi;
- Không tự redirect sang host lạ với Bearer token;
- Kiểm tra SSRF/open redirect;
- Không bật một default registration có scope rộng cho mọi HTTP clients.

---

## 8. Dependencies phục vụ integration test

### 8.1. Maven

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-oauth2-client</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>com.squareup.okhttp3</groupId>
        <artifactId>mockwebserver</artifactId>
        <version>4.12.0</version>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Đây là ví dụ để học. Khi dùng Spring Boot BOM hoặc plugin quản lý phiên bản, cần xem xét compatibility và dependency management dự án thay vì mặc định copy mọi version vào production.

### 8.2. Gradle

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Bài đang soạn Markdown, không chạy Gradle hoặc thay đổi project build.** Các dependency snippets là hướng dẫn cho người học tự xây một dự án demo riêng.

### 8.3. Vì sao chọn MockWebServer?

`MockWebServer` cho phép:
- Mở HTTP server local với port ngẫu nhiên;
- Đưa response JSON token vào hàng đợi;
- Kiểm tra HTTP method, path, headers, body đã nhận;
- Stub downstream HTTP 200/401/403;
- Không kết nối OP production;
- Kiểm thử RestClient/Spring HTTP transport thật hơn một mocked manager.

WireMock, MockServer hoặc một fake Authorization Server đều có thể dùng; tên công cụ không quan trọng bằng **assertions trên HTTP contract**.

---

## 9. Integration test thực hành: token endpoint và downstream HTTP

Đây là ví dụ **self-contained** dùng JUnit 5, MockWebServer, Spring Security Client và RestClient. Nó không cần khởi động cả Spring Boot application context; tuy vậy nó thực thi **manager, OAuth2 token client HTTP call và outbound interceptor thật** — nhiều tầng hơn một unit test mock manager.

### 9.1. Lớp test hoàn chỉnh

```java
package example.reports;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.security.oauth2.client.web.client.RequestAttributePrincipalResolver;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.web.client.RestClient;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.security.oauth2.client.web.client.RequestAttributeClientRegistrationIdResolver.clientRegistrationId;
import static org.springframework.security.oauth2.client.web.client.RequestAttributePrincipalResolver.principal;

class MachineToMachineHttpIntegrationTest {

    private MockWebServer authorizationServer;
    private MockWebServer downstreamApi;

    private InMemoryOAuth2AuthorizedClientService authorizedClientService;
    private RestClient restClient;

    @BeforeEach
    void setUp() throws IOException {
        authorizationServer = new MockWebServer();
        downstreamApi = new MockWebServer();

        authorizationServer.start();
        downstreamApi.start();

        ClientRegistration registration =
            ClientRegistration.withRegistrationId("reports-machine")
                .clientId("test-reports-client")
                .clientSecret("test-only-secret")
                .clientAuthenticationMethod(
                    ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
                .authorizationGrantType(
                    AuthorizationGrantType.CLIENT_CREDENTIALS)
                .tokenUri(
                    authorizationServer.url("/oauth2/token").toString())
                .scope("reports.read", "reports.export")
                .build();

        InMemoryClientRegistrationRepository registrations =
            new InMemoryClientRegistrationRepository(registration);

        authorizedClientService =
            new InMemoryOAuth2AuthorizedClientService(registrations);

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, authorizedClientService);

        manager.setAuthorizedClientProvider(
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build());

        OAuth2ClientHttpRequestInterceptor interceptor =
            new OAuth2ClientHttpRequestInterceptor(manager);

        // Giữ service principal ổn định giữa các calls.
        interceptor.setPrincipalResolver(
            new RequestAttributePrincipalResolver());

        restClient = RestClient.builder()
            .requestInterceptor(interceptor)
            .build();
    }

    @AfterEach
    void tearDown() throws IOException {
        authorizationServer.shutdown();
        downstreamApi.shutdown();
    }

    private void grantReadOnlyToken() {
        authorizationServer.enqueue(
            new MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody("""
                    {
                      "access_token": "test-access-token",
                      "token_type": "Bearer",
                      "expires_in": 3600,
                      "scope": "reports.read"
                    }
                    """));
    }

    private String callReports() {
        return restClient.get()
            .uri(downstreamApi.url("/api/reports").toString())
            .attributes(clientRegistrationId("reports-machine"))
            .attributes(principal("reports-batch"))
            .retrieve()
            .body(String.class);
    }

    @Test
    void requestsScopesAndPassesAccessTokenToDownstream()
            throws InterruptedException {
        grantReadOnlyToken();

        downstreamApi.enqueue(
            new MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody("{\"items\":2}"));

        String body = callReports();

        assertThat(body).isEqualTo("{\"items\":2}");

        RecordedRequest tokenRequest =
            authorizationServer.takeRequest(3, TimeUnit.SECONDS);

        assertThat(tokenRequest).isNotNull();
        assertThat(tokenRequest.getMethod()).isEqualTo("POST");
        assertThat(tokenRequest.getPath())
            .isEqualTo("/oauth2/token");
        assertThat(tokenRequest.getHeader("Content-Type"))
            .startsWith("application/x-www-form-urlencoded");
        assertThat(tokenRequest.getHeader("Authorization"))
            .startsWith("Basic ");

        String form = tokenRequest.getBody().readUtf8();
        assertThat(form).contains("grant_type=client_credentials");
        assertThat(form).contains("scope=");
        assertThat(form).contains("reports.read");
        assertThat(form).contains("reports.export");

        RecordedRequest apiRequest =
            downstreamApi.takeRequest(3, TimeUnit.SECONDS);

        assertThat(apiRequest).isNotNull();
        assertThat(apiRequest.getMethod()).isEqualTo("GET");
        assertThat(apiRequest.getPath()).isEqualTo("/api/reports");
        assertThat(apiRequest.getHeader("Authorization"))
            .isEqualTo("Bearer test-access-token");

        // Token response chỉ cấp reports.read,
        // dù registration yêu cầu cả reports.export.
        var saved = authorizedClientService
            .loadAuthorizedClient("reports-machine", "reports-batch");

        assertThat(saved).isNotNull();
        assertThat(saved.getAccessToken().getScopes())
            .contains("reports.read")
            .doesNotContain("reports.export");
    }
}
```

### 9.2. Test trên thực sự xác minh điều gì?

1. `ClientRegistration` thực sự dùng grant `client_credentials`;
2. Authorized client manager sử dụng token endpoint HTTP giả;
3. HTTP token request là POST form, có grant type và requested scopes;
4. Client authentication dùng Authorization Basic header;
5. Token response được parse;
6. OAuth2AuthorizedClientService lưu token theo `reports-machine` và `reports-batch`;
7. RestClient interceptor gắn Bearer token lên downstream request;
8. Granted scope được phản ánh từ response tường minh, không mặc định toàn bộ requested scopes.

**Không chứng minh**:
- Secret ở môi trường thật đúng hay chưa;
- Authorization Server production thật chấp nhận client;
- JWT signature/issuer/audience;
- Reports API production thật thực thi `reports.read`;
- Phân quyền người dùng cuối;
- Token rotation/DPoP/mTLS.

### 9.3. Tại sao không assert full Basic credential trong log?

Trong test, secret là `test-only-secret`, nhưng thói quen tốt là chỉ xác minh client authentication method và, khi cần, decode/so sánh giá trị **trong memory của test** mà không đưa raw Authorization header vào test failure report.

Nếu cần kiểm tra chính xác client ID, có thể decode Basic header cẩn thận trong test rồi assert, nhưng không in credential nguyên văn vào log. Với production, tuyệt đối không ghi HTTP Authorization header ra telemetry.

### 9.4. Test chỉ dùng HTTP local nhưng vẫn là integration test

Test đi qua nhiều thành phần thật:
- `OAuth2AuthorizedClientManager`;
- `OAuth2AuthorizedClientProvider`;
- Token response client/HTTP transport;
- Authorized client storage;
- RestClient interceptor;
- HTTP client;
- Local token server và local downstream.

Nó không boot toàn Spring application context, do đó **không chứng minh application.yml đã bind đúng hay @Bean wiring production chính xác**. Đó là tầng integration test tiếp theo.

---

## 10. Bổ sung test: token cache và tái sử dụng

Trong cùng một authorized-client service, cùng `registrationId` và `principalName`, access token chưa hết hạn thường được tái sử dụng.

```java
@Test
void reusesUnexpiredMachineToken() throws InterruptedException {
    grantReadOnlyToken();

    downstreamApi.enqueue(new MockResponse()
        .setResponseCode(200).setBody("first"));
    downstreamApi.enqueue(new MockResponse()
        .setResponseCode(200).setBody("second"));

    assertThat(callReports()).isEqualTo("first");
    assertThat(callReports()).isEqualTo("second");

    // Hai API calls nhưng token endpoint chỉ nhận một request.
    assertThat(authorizationServer.getRequestCount()).isEqualTo(1);
    assertThat(downstreamApi.getRequestCount()).isEqualTo(2);
}
```

Ở đây token có `expires_in=3600` nên đủ xa thời điểm hết hạn để tránh clock-skew renewal.

### 10.1. Cảnh báo khi đọc getRequestCount()

`getRequestCount()` là số request **MockWebServer đã nhận**, không phải số authentication events hoặc số authorized clients trong toàn cluster.

Nếu dùng parallel tests/shared server, cần cô lập server fixture để assertions không bị ảnh hưởng bởi request của test khác.

### 10.2. Cache key và principal

Nếu đổi:

```java
.attributes(principal("reports-batch"))
```

thành:

```java
.attributes(principal("random-" + UUID.randomUUID()))
```

mỗi request có thể dùng cache key mới nên manager lại xin token. Đây là lý do dùng **stable service principal** thay vì random string.

### 10.3. Expiration và clock skew

Spring Security có thể xem token sắp hết hạn là cần renew **trước thời điểm `expiresAt` chính xác** theo clock skew của provider. Khi thiết kế test expiry:
- Đừng dùng `Thread.sleep(3600_000)`;
- Cân nhắc fake clock/provider phù hợp version;
- Test token sắp hết hạn hoặc token đã hết hạn bằng thời gian kiểm soát được;
- Assert có một token request mới và token mới được dùng;
- Không giả định mọi token endpoint đều cấp refresh token cho client credentials.

---

## 11. Downstream 403: thiếu scope phải được xử lý thế nào?

Giả sử token chỉ có `reports.read` nhưng endpoint `POST /reports/export` đòi `reports.export`.

Downstream có thể trả:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope", scope="reports.export"
Content-Type: application/json

{"error":"forbidden"}
```

Client nên:
- Nhận biết đây là **authorization failure** tại Resource Server;
- Không retry vô hạn bằng cùng token;
- Không tự “thêm scope” vào access token đã cấp;
- Không gọi lại với client registration khác có quyền rộng hơn nếu chưa có policy;
- Báo lỗi nghiệp vụ/telemetry phù hợp và yêu cầu cập nhật AS permission khi hợp lệ.

### 11.1. Contract test cho 403

```java
import org.springframework.web.client.HttpClientErrorException;

@Test
void propagatesInsufficientScopeFromDownstream() {
    grantReadOnlyToken();

    downstreamApi.enqueue(new MockResponse()
        .setResponseCode(403)
        .setHeader("WWW-Authenticate",
            "Bearer error=\"insufficient_scope\", scope=\"reports.export\"")
        .setHeader("Content-Type", "application/json")
        .setBody("{\"error\":\"forbidden\"}"));

    org.assertj.core.api.Assertions.assertThatThrownBy(
        () -> callReports())
        .isInstanceOf(HttpClientErrorException.Forbidden.class);

    assertThat(authorizationServer.getRequestCount()).isEqualTo(1);
    assertThat(downstreamApi.getRequestCount()).isEqualTo(1);
}
```

**Giới hạn:** MockWebServer không giải mã token để tự tính scopes. Test trên xác minh **client nhận và truyền lỗi 403**, không kiểm tra code Resource Server đã implement scope policy đúng.

### 11.2. Không trộn 403 với invalid_token

| HTTP result | Ý nghĩa phổ biến | Xử lý |
| --- | --- | --- |
| 200 OK | Resource Server chấp nhận | Xử lý response |
| **401 invalid_token** | Token sai/hết hạn/revoked hoặc RS không xác thực được | Xem token validity, có thể remove/re-authorize theo policy |
| **403 insufficient_scope** | Token được xác thực nhưng thiếu scope/quyền | Không cố refresh cùng scope như workaround quyền |
| 403 do business ACL | User/service thiếu quyền tenant/resource dù có scope | Kiểm tra domain authorization |
| 429 Too Many Requests | Rate limit | Backoff/quota, không giả định scope sai |
| 503 Service Unavailable | RS outage | Retry/backoff có giới hạn, không xoá token tùy tiện |

Một RS có thể tùy chỉnh status/error contract. Với OAuth2 Bearer chuẩn, 401/403 và `WWW-Authenticate` giúp phân biệt lỗi, nhưng test phải dựa vào contract thực tế.

---

## 12. Downstream 401: token không hợp lệ khác scope thiếu

Một response mẫu:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Nguyên nhân có thể:
- Access token đã hết hạn;
- Token bị revoke;
- Audience khác Resource Server;
- Issuer/algorithm/signature sai;
- AS/RS không đồng bộ keys;
- Token malformed;
- Resource Server introspection thất bại.

### 12.1. Không coi mọi 401 là token hết hạn

Một token có `exp` còn hạn vẫn có thể bị 401 do sai `aud` hoặc `iss`. Chỉ xin lại token với cùng audience/scopes có thể tiếp tục thất bại.

### 12.2. Authorized client failure handler

Spring Security RestClient interceptor hỗ trợ xử lý authorization failure để remove invalid authorized client khi phù hợp:

```java
OAuth2ClientHttpRequestInterceptor oauth2 =
    new OAuth2ClientHttpRequestInterceptor(manager);

oauth2.setPrincipalResolver(
    new RequestAttributePrincipalResolver());

oauth2.setAuthorizationFailureHandler(
    OAuth2ClientHttpRequestInterceptor
        .authorizationFailureHandler(authorizedClientService));
```

Cần kiểm tra phiên bản và semantics failure handler: nó không phải một “HTTP retry mọi lỗi” interceptor. Việc remove authorized client bị invalid và việc retry request **là hai quyết định khác nhau**.

### 12.3. Kiểm thử 401 có bounded recovery

Có thể thiết kế test:
1. AS cấp `AT-OLD`;
2. RS trả 401 invalid_token;
3. Failure handler remove saved client theo registration/principal khi policy cho phép;
4. Request **mới** xin `AT-NEW`;
5. RS nhận Bearer `AT-NEW`.

Nhưng cần **không tự replay non-idempotent POST** nếu chưa bảo đảm operation an toàn. Một 401 không tự cho phép gửi lại request ghi dữ liệu vô hạn.

---

## 13. Token endpoint failures: khác downstream failures

Authorization Server có thể trả:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "invalid_client",
  "error_description": "Client authentication failed"
}
```

hoặc:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{"error":"invalid_scope"}
```

Hoặc HTTP 503 khi AS outage.

### 13.1. Phân loại lỗi

| OAuth2/HTTP error | Tầng | Nguyên nhân thường gặp | Có nên retry? |
| --- | --- | --- | --- |
| `invalid_client` | AS token endpoint | Secret/auth method sai, client disabled | Không retry liên tục; sửa config |
| `unauthorized_client` | AS token endpoint | Client không được phép dùng grant | Cần grant registration/AS policy |
| `invalid_scope` | AS token endpoint | Xin scope không được cho phép | Sửa scope/permission |
| `unsupported_grant_type` | AS token endpoint | AS không hỗ trợ client_credentials | Sửa tích hợp |
| `invalid_request` | AS token endpoint | Sai form/parameter | Sửa request |
| 429 | AS token endpoint | Rate limit | Backoff/quota |
| 502/503/timeout | AS/network | Outage | Retry có giới hạn, circuit breaker phù hợp |
| 401 invalid_token | RS | Token validation failure | Kiểm tra audience/issuer/expiry |
| 403 insufficient_scope | RS | Token hợp lệ nhưng thiếu quyền | Sửa policy/consent/registration; không auto escalate |

### 13.2. Ví dụ negative token test

```java
@Test
void failsWhenClientCredentialsAreRejected() {
    authorizationServer.enqueue(new MockResponse()
        .setResponseCode(400)
        .setHeader("Content-Type", "application/json")
        .setBody("{\"error\":\"invalid_client\"}"));

    org.assertj.core.api.Assertions.assertThatThrownBy(
        () -> callReports())
        .isInstanceOf(
            org.springframework.security.oauth2.core.OAuth2AuthorizationException.class);

    assertThat(authorizationServer.getRequestCount()).isEqualTo(1);
    assertThat(downstreamApi.getRequestCount()).isZero();
}
```

Mục tiêu test: nếu **không lấy được token**, client **không được gọi downstream bằng một Bearer token rỗng/giả**. Kiểu exception cụ thể có thể được bọc tùy tầng RestClient/Spring Security; khi port sang service architecture khác, assert phần error contract thích hợp hơn là phụ thuộc stacktrace.

### 13.3. Không log error_description raw

`error_description` đến từ một HTTP response có thể chứa dữ liệu untrusted, request URL, credential hints hoặc PII. Hiển thị thông báo generic cho user/operator và ghi normalized error code, không log toàn bộ token response.

---

## 14. Test AS có giảm scope được cấp

Đây là một trong những test quan trọng nhất của chủ đề.

Registration:

```java
.scope("reports.read", "reports.export")
```

AS đáp:

```json
{
  "access_token": "AT-LIMITED",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "reports.read"
}
```

**Kết quả mong đợi:**
- Client không tự coi `reports.export` là đã cấp;
- `OAuth2AccessToken.getScopes()` trong fixture response tường minh phản ánh `reports.read`;
- Một downstream endpoint cần `reports.export` phải deny nếu nhận token thiếu quyền;
- Không retry cấp token với một client registration có scope rộng hơn không được phê duyệt.

### 14.1. Hai phương án kiểm tra scope

**Client-side contract:** assert requested scopes trong form + granted scopes trong token metadata.

**Resource-server integration:** chạy downstream security filter/JWT converter/introspection và thực sự kiểm tra 200/403 theo scope token.

Chỉ có phần đầu không chứng minh downstream authorization; chỉ có phần sau không chứng minh client gửi đúng token request.

### 14.2. Không “thêm” scope vào token

Sai:

```java
// Anti-pattern: biến requested scope thành authority của downstream.
String scope = "reports.read reports.export";
// Sau đó tự cho rằng token bearer đã có quyền đó.
```

Quyền của token là do **AS cấp** và **RS thực thi**, không do client tự sửa một Map/String.

---

## 15. Resource Server test: xác minh chính sách scope

Một Reporting API dùng Spring Security Resource Server có thể đặt policy:

```java
package example.api;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ReportsResourceSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/reports/export")
                    .hasAuthority("SCOPE_reports.export")
                .requestMatchers("/api/reports/**")
                    .hasAuthority("SCOPE_reports.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Ở đây:
- `reports.read` và `reports.export` được chuyển thành `SCOPE_reports.read` và `SCOPE_reports.export` nếu JWT mapping mặc định nhận diện scopes;
- Endpoint export đòi quyền cao hơn;
- Có JWT decoder thật trong production để xác minh chữ ký, issuer, expiry và audience theo config;
- Test không nên bypass `aud` validation nếu muốn chứng minh đúng resource boundary.

### 15.1. MockMvc security policy test

```java
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.springframework.security.core.authority.SimpleGrantedAuthority;

// Token giả được chuyển thành Authentication đã có reports.read.
mvc.perform(get("/api/reports")
    .with(jwt().authorities(
        new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());

// Token giả chỉ có read thì không được export.
mvc.perform(get("/api/reports/export")
    .with(jwt().authorities(
        new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isForbidden());

// Token giả có export.
mvc.perform(get("/api/reports/export")
    .with(jwt().authorities(
        new SimpleGrantedAuthority("SCOPE_reports.export"))))
    .andExpect(status().isOk());
```

Đây là **policy test**: nó tạo `JwtAuthenticationToken`/authorities giả trong MockMvc. Không có việc xác minh một JWT được ký thật.

Để chạy, test phải có:
- `spring-security-test`;
- MockMvc có Spring Security filter integration;
- ResourceServer SecurityFilterChain + controller endpoint tương ứng;
- Test context tạo được JwtDecoder bean/config cần thiết (nếu security configuration yêu cầu).

### 15.2. Muốn kiểm tra JWT thực sự bị từ chối vì thiếu scope?

Cần một integration test đi qua:
1. Một token JWT được ký bằng test private key;
2. Resource Server dùng test JWKS/decoder tin cậy;
3. Validation `iss`, `aud`, `exp` và signature;
4. Converter lấy `scope` hoặc `scp`;
5. SecurityFilterChain áp dụng `hasAuthority("SCOPE_reports.export")`;
6. Assert HTTP 200/403 và các invalid token 401.

Tại bước này cần phân biệt **valid token thiếu scope** (403) với **token không thể xác minh** (401).

### 15.3. Opaque token thì sao?

Với opaque access token, Resource Server có thể dùng introspection endpoint. Test phải kiểm tra:
- Introspection response `active` đúng/sai;
- Granted scopes;
- Audience/resource policy;
- TTL/cache nếu có;
- 401 khi inactive;
- 403 khi active nhưng thiếu quyền.

Không thể suy ra scope của opaque token chỉ từ chuỗi ký tự ngẫu nhiên của token.

---

## 16. Kết hợp hai tầng test để có độ tin cậy cao

Một suite thực tế nên tách:

```text
Layer A: OAuth2 Client integration
  RestClient + AuthorizedClientManager
     -> Mock AS token endpoint
     -> Mock downstream contract
  Assert token request, scope, Bearer header, errors, cache

Layer B: Downstream Resource Server integration
  SecurityFilterChain + JwtDecoder/Introspector
     -> Synthetic signed JWT/opaque introspection
  Assert 200/401/403, issuer, audience, scope mapping

Layer C: Environment contract/E2E (có kiểm soát)
  Test AS + Test Resource Server (không dùng production secrets)
  Assert toàn bộ machine-to-machine flow, networking, config
```

### 16.1. Vì sao một test giả lập hết mọi thứ là chưa đủ?

Nếu bạn mock manager trả `OAuth2AuthorizedClient` có scope `reports.read`, rồi mock downstream client trả 200, bạn đã bỏ qua:
- Token endpoint form;
- Client auth method;
- Access token parsing;
- Scope reduction;
- RestClient interceptor;
- Header Bearer;
- Actual HTTP status handling;
- Cache/expiry.

Nhưng nếu tất cả tests đều chạy với AS/RS thật trên môi trường staging, suite chậm và thiếu tính quyết định. **Phối hợp test layers** giúp coverage tốt mà không phải phụ thuộc OP live cho mọi commit.

---

## 17. Kiểm thử token expiry và reauthorization

Với client_credentials, khi access token không còn hợp lệ theo expiry/clock skew, manager có thể **xin token mới bằng cùng grant**.

```text
T0: OAuth2AuthorizedClient
    access_token=A1
    expiresAt=T0+3600s

T0+100s: downstream call
    -> reuse A1

T0+3590s (near expiration)
    -> manager may request new token A2

Downstream request
    -> Bearer A2
```

### 17.1. Test nên kiểm soát thời gian

- Không chờ thật một giờ;
- Dùng clock/test provider cấu hình được trong phiên bản hiện tại;
- Hoặc trả expiry rất ngắn và quan sát reauthorization có kiểm soát;
- Tránh flaky test phụ thuộc scheduler/system clock;
- Biết rằng provider có thể áp dụng **clock skew**, nên token gần expiry đã bị coi là cần renew.

### 17.2. Refresh token grant không tự được gọi

RFC 6749 khuyến nghị **không cấp refresh token** với client_credentials. Đừng viết test expecting `grant_type=refresh_token` chỉ vì access token đã hết hạn. Luồng phổ biến là **`grant_type=client_credentials` lần nữa**.

### 17.3. Reauthorization và cache storage

Nếu ứng dụng chạy nhiều replicas, `InMemoryOAuth2AuthorizedClientService` là per-instance. Các replicas có thể xin tokens riêng dù cùng service principal.

Khi dùng persistent storage/shared cache:
- Kiểm soát keys theo registration + principal;
- Xem xét concurrent renewal;
- Chống token leakage;
- Không giả định Spring Security tự cung cấp distributed lock;
- Không tự ghi raw token vào logs.

---

## 18. Kiểm thử concurrent requests khi token chưa có

Hai HTTP requests đến cùng thời điểm:

```text
Request A -> authorize("reports-machine","reports-batch")
Request B -> authorize("reports-machine","reports-batch")
              |
              v
   Cùng cache chưa có token
              |
              +-- token request A
              +-- token request B (có thể)
```

**Không nên mặc định** chỉ có đúng một token request khi concurrent cache miss nếu manager/service chưa có cơ chế single-flight hoặc locking. Thực tế có thể có hai requests hợp lệ.

Test concurrency nên xác định:
- AS có thể cấp hai tokens;
- Requests không dùng token của registration khác;
- Authorized client store không hỏng;
- Không có data race khi ghi cache;
- Token endpoint quota/rate limit được quản lý;
- Nếu business đòi strict single token request, cần single-flight/lock strategy có test riêng.

### 18.1. Phân biệt safety và efficiency

- **Safety:** mọi downstream request chỉ dùng token hợp lệ từ đúng AS/client registration;
- **Efficiency:** hạn chế xin trùng tokens không cần thiết.

Một test concurrency chỉ chứng minh không trộn token/ngữ cảnh không đủ để kết luận số token requests tối ưu; ngược lại số requests =1 cũng không chứng minh token được gắn đúng audience.

### 18.2. Không lưu token vào static global field

```java
// ANTI-PATTERN
static String currentAccessToken;
```

Nếu cùng ứng dụng có `reports-machine` và `payments-machine`, static field có thể gây token mix-up giữa audiences. Dùng manager/service theo registration và principal, không phải một biến toàn cục.

---

## 19. Nhiều downstream APIs và least privilege

Một ứng dụng có thể gọi Reports API và Billing API.

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reports-machine:
            provider: company-as
            client-id: ${REPORTS_CLIENT_ID}
            client-secret: ${REPORTS_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope: [reports.read]

          billing-machine:
            provider: company-as
            client-id: ${BILLING_CLIENT_ID}
            client-secret: ${BILLING_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            scope: [billing.write]

        provider:
          company-as:
            token-uri: https://auth.example.test/oauth2/token
```

**Nên tách clients/registrations khi policy hoặc trust boundary cần.**

Không gửi:
- Token Billing tới Reports API;
- Token Reports tới Billing API;
- Token scoped `reports.read` tới endpoint ghi Billing;
- Client secret của Billing tới token endpoint không đáng tin.

### 19.1. Test token audience isolation

Test phù hợp:
- Mock AS cấp token R cho Reports;
- Mock AS cấp token B cho Billing;
- RestClient cho Reports luôn gửi Bearer R;
- RestClient cho Billing luôn gửi Bearer B;
- Không có request nào gửi token R sang Billing host;
- Resource Server từ chối token sai audience nếu test validation thật.

### 19.2. Registration không đồng nghĩa endpoint

`ClientRegistration` mô tả OAuth2 client. `RestClient.baseUrl` mô tả downstream destination. Chúng cần được **liên kết bằng cấu hình tin cậy**.

Một test cần xác minh `clientRegistrationId("billing-machine")` không thể bị injected từ raw user query vào một arbitrary downstream URL để gây credential exfiltration.

### 19.3. Bảo vệ DNS/redirects

Nếu outbound HTTP client theo redirect từ Reports API đến hostname khác, phải bảo đảm không tự chuyển tiếp Bearer token ngoài destination được phép. Đây là chủ đề HTTP client hardening/SSRF không được giải quyết chỉ bằng scope.

---

## 20. Cấu hình Spring Boot integration test với dynamic token URI

Một @SpringBootTest kiểm tra **Spring Boot property binding và @Bean wiring** ngoài tầng HTTP client riêng lẻ có thể dùng local MockWebServer endpoint với `@DynamicPropertySource`.

Ví dụ khái niệm:

```java
@SpringBootTest
class ReportsClientApplicationIntegrationTest {

    static final MockWebServer as = new MockWebServer();

    static {
        try {
            as.start();
        } catch (IOException e) {
            throw new ExceptionInInitializerError(e);
        }
    }

    @DynamicPropertySource
    static void oauthProperties(DynamicPropertyRegistry registry) {
        registry.add(
            "spring.security.oauth2.client.provider.reports-as.token-uri",
            () -> as.url("/oauth2/token").toString());
    }

    @AfterAll
    static void stopServer() throws IOException {
        as.shutdown();
    }

    // @Autowired OAuth2AuthorizedClientManager manager;
    // @Test ... assert manager.authorize(...) thật qua mock endpoint
}
```

Đoạn này **chỉ là skeleton @SpringBootTest**. Cần bổ sung:
- Imports và dependencies;
- Registration `reports-machine` trong test properties (client_id, secret, grant, scope);
- Mock AS responses cho từng test;
- Không thêm `issuer-uri` nếu nó gây OIDC discovery startup không liên quan đến client credentials;
- Nếu có nhiều contexts/tests song song, cô lập mock server và lifecycle tránh race;
- Downstream base URL cũng dùng test property;
- Assertions giống mục 9.

### 20.1. Vì sao dynamic port?

`MockWebServer` dùng port ngẫu nhiên để tránh conflicts với những services trên máy CI. `@DynamicPropertySource` cho phép Spring tạo registration với URL chính xác trước khi context khởi tạo.

### 20.2. Không dùng localhost production trong YAML

Trong production:
- Token URI phải là HTTPS tin cậy;
- Test URI phải chỉ tới local server/testcontainer;
- Client secret test được nạp từ test-only config;
- Không để property override rò vào production profile.

### 20.3. Không gọi production AS trong CI

Các tests nên deterministic và offline/reproducible khi có thể. Test nào bắt buộc staging AS cần:
- Secrets riêng được kiểm soát;
- Network policy;
- Rate limits;
- Cleanup;
- Quy định không đụng dữ liệu thật;
- Cơ chế skip/isolated pipeline nếu staging unavailable.

---

## 21. Reactive WebFlux: kiểm thử client credentials với WebClient

Trên WebFlux, dùng `ReactiveOAuth2AuthorizedClientManager` thay vì Servlet manager.

Một cấu hình service-level:

```java
package example.reactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

@Configuration
class ReactiveMachineConfig {

    @Bean
    ReactiveOAuth2AuthorizedClientManager machineManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService service) {

        ReactiveOAuth2AuthorizedClientProvider provider =
            ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                registrations, service);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

**Khi không có `ServerWebExchange` (scheduled/background job), dùng service-level reactive manager.** `DefaultReactiveOAuth2AuthorizedClientManager` dành cho tình huống dựa vào WebFlux web request context.

### 21.1. WebClient OAuth2 filter

```java
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Bean
WebClient reportsWebClient(
        ReactiveOAuth2AuthorizedClientManager manager) {

    ServerOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
        new ServerOAuth2AuthorizedClientExchangeFilterFunction(manager);

    return WebClient.builder()
        .baseUrl("https://reports-api.example.test")
        .filter(oauth2)
        .build();
}
```

Một lời gọi:

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

Mono<String> result = reportsWebClient.get()
    .uri("/api/reports")
    .attributes(clientRegistrationId("reports-machine"))
    .retrieve()
    .bodyToMono(String.class);
```

**Lưu ý về principal:** Với service-level client credentials cần có service principal trong authorization request/context. Cách truyền phụ thuộc integration/version; một phương án không mơ hồ là **gọi manager tường minh** với `OAuth2AuthorizeRequest.principal("reports-batch")`, sau đó truyền authorized client đã nhận vào WebClient.

### 21.2. Gọi reactive manager tường minh

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import reactor.core.publisher.Mono;

OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("reports-machine")
        .principal("reports-batch")
        .build();

Mono<OAuth2AuthorizedClient> authorized =
    reactiveManager.authorize(request);
```

Trong test:

```java
StepVerifier.create(authorized)
    .assertNext(client -> {
        assertThat(client.getClientRegistration().getRegistrationId())
            .isEqualTo("reports-machine");
        assertThat(client.getAccessToken().getScopes())
            .contains("reports.read");
    })
    .verifyComplete();
```

**Không gọi `block()` trong reactive request-processing code**. Dùng `StepVerifier` ở test boundary và compose `Mono` trong service.

### 21.3. Đưa authorized client vào WebClient

```java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.oauth2AuthorizedClient;

Mono<String> response = reactiveManager.authorize(request)
    .flatMap(client ->
        reportsWebClient.get()
            .uri("/api/reports")
            .attributes(oauth2AuthorizedClient(client))
            .retrieve()
            .bodyToMono(String.class));
```

Cách này bảo đảm request sử dụng **đúng authorized client** mà manager đã tìm/cấp dưới service principal ổn định. Kiểm thử HTTP với mock token endpoint/downstream tương tự mục 9, nhưng dùng `StepVerifier`/WebClient và reactive dependencies.

### 21.4. Không nhầm WebTestClient mockOidcLogin

`mockOidcLogin()` tạo OIDC user cho **inbound WebFlux HTTP security test**. Nó **không phát client_credentials token thật** hay kiểm tra scope của downstream.

Với M2M integration test, cần mock token endpoint và kiểm tra outbound WebClient/manager thật, không chỉ gọi `mockOidcLogin()`.

---

## 22. Servlet WebClient là trường hợp riêng

Một ứng dụng Servlet MVC cũng có thể sử dụng `WebClient` cho outbound HTTP. Khi đó không dùng `ServerOAuth2AuthorizedClientExchangeFilterFunction` của WebFlux nếu app chạy trong Servlet context theo API Spring Security Servlet.

Dùng:

```java
import org.springframework.security.oauth2.client.web.reactive.function.client.ServletOAuth2AuthorizedClientExchangeFilterFunction;

ServletOAuth2AuthorizedClientExchangeFilterFunction oauth2 =
    new ServletOAuth2AuthorizedClientExchangeFilterFunction(manager);

WebClient client = WebClient.builder()
    .apply(oauth2.oauth2Configuration())
    .build();
```

Nếu muốn client credentials cho scheduled/background job, chọn manager/service principal rõ ràng, tránh phụ thuộc `HttpServletRequest` hiện tại.

### 22.1. Cảnh báo default token trên mọi request

Spring Security có các tùy chọn default authorized client/default registration ID cho WebClient. Dùng không cẩn thận có thể khiến mọi outbound calls đều mang access token, kể cả tới một URL không nên nhận token.

**Ưu tiên chỉ rõ registration/authorized client trên các requests cần bảo vệ** và hạn chế base URLs phù hợp. Đây cũng là assertion hữu ích trong integration test.

---

## 23. Scope theo RFC và định dạng request

Một request client credentials chuẩn có thể là:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic BASE64_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=reports.read+reports.export
```

Dấu `+` trong form encoding tương ứng với space giữa scopes. Không nên so sánh raw body chỉ theo một chuỗi cố định nếu thứ tự scope có thể thay đổi.

### 23.1. Parse form thay vì so sánh thứ tự

Khi cần strict assertion, có thể parse `application/x-www-form-urlencoded` thành Map bằng một helper test rồi so sánh **set** scopes thay vì byte-for-byte.

```java
String encodedForm = tokenRequest.getBody().readUtf8();

Map<String, String> form = java.util.Arrays.stream(
        encodedForm.split("&"))
    .map(part -> part.split("=", 2))
    .collect(java.util.stream.Collectors.toMap(
        part -> java.net.URLDecoder.decode(
            part[0], java.nio.charset.StandardCharsets.UTF_8),
        part -> java.net.URLDecoder.decode(
            part.length > 1 ? part[1] : "",
            java.nio.charset.StandardCharsets.UTF_8)));

assertThat(form.get("grant_type")).isEqualTo("client_credentials");

assertThat(java.util.Set.of(form.get("scope").split(" ")))
    .containsExactlyInAnyOrder("reports.read", "reports.export");
```

Đoạn helper giả định form hợp lệ và mỗi key chỉ xuất hiện một lần; với production-level parser cần xử lý URL encoded values, duplicate fields và error cases đầy đủ.

### 23.2. Client secret basic encoding

Client authentication bằng Basic có ràng buộc encoding của OAuth2. Đừng tự xây chuỗi `client_id:client_secret` và Base64 bằng logic không tuân thủ encoding nếu thư viện Spring Security đã hỗ trợ.

Test có thể xác minh `Authorization` header bắt đầu `Basic` và, khi muốn kiểm tra strict, decode với test-only secret để assert. Không bao giờ output raw Basic credential trong logs.

### 23.3. Requested scope có thể bị AS giới hạn

Một Authorization Server có thể cấp scope hẹp hơn, hoặc trả `invalid_scope` nếu xin quyền không hợp lệ. Test nên bao gồm cả hai, đặc biệt khi nâng cấp configuration thêm scope mới.

---

## 24. Security boundary: token cho đúng audience

Một Reports API yêu cầu:

```json
{
  "iss": "https://auth.example.test",
  "aud": ["reports-api"],
  "scope": "reports.read"
}
```

Một token Billing:

```json
{
  "iss": "https://auth.example.test",
  "aud": ["billing-api"],
  "scope": "reports.read"
}
```

Dù trùng `scope=reports.read`, token Billing **không được phép** truy cập Reports API nếu audience policy phân biệt hai resource servers.

### 24.1. Test audience mismatch

- Dựng JWT test với `aud=billing-api`;
- Đưa JWT đó tới Reports Resource Server với JWT decoder và audience validator thực;
- Assert 401 hoặc contract rejection thích hợp;
- Sau đó dựng JWT có `aud=reports-api`, scope đúng, signature hợp lệ → 200;
- Token đúng audience nhưng thiếu scope → 403.

### 24.2. Không suy ra audience từ scope

Một client có scopes được cấp nhưng không có resource/audience phù hợp vẫn cần được RS từ chối. Trong một số AS, cần `resource` parameter (RFC 8707) hoặc provider-specific audience/resource setting để xin token cho API. Cấu hình scope một mình **không đảm bảo token đúng audience**.

### 24.3. Token exchange là flow khác

Nếu ứng dụng đang giữ user token và muốn xin một token được giới hạn cho downstream audience, đó có thể là **token exchange (RFC 8693)** hoặc delegated authorization theo AS contract, không phải tự động gọi client_credentials rồi “gắn user” vào token.

---

## 25. Quản lý secrets trong test và production

### 25.1. Trong integration test

- Dùng client ID/secret giả `test-reports-client` / `test-only-secret`;
- Token URI trỏ tới localhost MockWebServer;
- Access token fixture `test-access-token`;
- Không lưu credentials staging/production trong source;
- Không in raw Authorization headers trong test failure logs;
- Reset mock servers và authorized client store mỗi test;
- Không chạy cùng test fixtures trên mạng công khai.

### 25.2. Trong production

- Secret lưu trong environment secret manager/secure vault;
- TLS cho token endpoint và API;
- Client authentication method đúng AS policy;
- Rotation secrets/certificates;
- Không tạo singleton global Map chứa token plaintext không được bảo vệ;
- Scopes và audiences tối thiểu;
- Quyền outbound network giới hạn;
- Cảnh báo abnormal token issuance;
- Không dùng M2M tokens thay end-user Authentication.

### 25.3. Không có ID Token trong client credentials chuẩn

Client Credentials thuộc **OAuth2**, không mặc định tạo một `OidcUser` hoặc ID Token. Vì vậy trong test:
- Không chờ `openid`, `nonce`, `id_token` nếu AS không có contract riêng;
- Không test `@AuthenticationPrincipal OidcUser` như bằng chứng machine identity;
- Dùng access token, client registration, resource authorization.

---

## 26. Observability cho Client Credentials

Một sự kiện an toàn:

```json
{
  "event": "m2m_oauth2_token_request",
  "registration_id": "reports-machine",
  "grant_type": "client_credentials",
  "result": "success",
  "requested_scope_category": "reporting-read-export",
  "latency_bucket_ms": "100-250",
  "trace_id": "test-safe-trace"
}
```

Đây là schema do ứng dụng tự định nghĩa, không phải log mặc định của Spring Security.

### 26.1. Nên ghi

- `registrationId` allowlisted;
- Token request success/failure;
- OAuth2 error code đã normalize;
- HTTP status category, latency;
- Requested scope category cố định, không chứa raw untrusted input;
- Downstream name/route category;
- 401/403/429/503 rates per API;
- Trace ID nội bộ không mang credential.

### 26.2. Không ghi

- `client_secret`;
- Full Basic authorization header;
- Access/refresh token;
- Full HTTP token response;
- Raw JWT claims nếu chứa PII;
- Raw URI query chứa bearer token;
- `error_description` không kiểm soát;
- Object `OAuth2AuthorizedClient` dump trực tiếp vào logs.

### 26.3. Metrics nên tách AS và RS

```text
oauth2_client_token_requests_total{registration="reports-machine",result="success"}
oauth2_client_token_failures_total{registration="reports-machine",error="invalid_scope"}
downstream_requests_total{service="reports",status="200"}
downstream_requests_total{service="reports",status="403"}
downstream_requests_total{service="reports",status="503"}
```

Nếu gộp một metric “OAuth error”, khó phân biệt client secret sai, token thiếu scope hay downstream outage.

---

## 27. Troubleshooting tổng hợp

| Triệu chứng | Nguyên nhân khả dĩ | Hướng điều tra |
| --- | --- | --- |
| Không có token request | Manager không hỗ trợ client_credentials hoặc không gọi authorize | Authorized client provider, registration ID |
| `authorize()` trả null | Registration/grant/provider không phù hợp | Xem manager và policy |
| Token endpoint 401/400 invalid_client | Client secret/auth method sai | Registration, AS config, Basic/private_key_jwt/mTLS |
| Token endpoint invalid_scope | Scopes không được AS cho phép | Client permissions, scope request |
| Unsupported grant_type | AS/client không hỗ trợ client_credentials | Grant registration và AS |
| Mock token response không parse | Thiếu token_type, expires_in/JSON không hợp lệ | Token endpoint contract, Content-Type |
| Test chỉ thấy một scope | AS trả reduced scope | Requested vs granted khác nhau |
| Token API gửi sai header | RestClient interceptor chưa gắn hoặc chọn sai registration | HTTP client wiring/attributes |
| RestClient không có principal | Default resolver phụ thuộc SecurityContextHolder | RequestAttributePrincipalResolver và service principal |
| Mỗi request lại xin token | Principal name thay đổi, cache disabled, token near-expiry | Cache key, storage, clock skew |
| Hai concurrent calls xin hai tokens | Cache miss race | Single-flight/locking nếu cần |
| 401 downstream dù token còn hạn | Audience/issuer/signature/revocation sai | Resource Server validation, AS contract |
| 403 insufficient_scope | Granted scope thiếu | Scope/permission, không retry mù |
| 403 business ACL | Tenant/resource access policy | Domain authorization |
| 429 token endpoint | Rate limit, quá nhiều token requests | Stable principal, caching/backoff |
| 503 AS | Authorization Server outage | Timeout/circuit breaker; không gọi API nếu không token |
| 503 RS | Downstream outage | Không coi AS token invalid |
| Token Reports gửi đến Billing | Registration/URI mapping sai | Dedicated clients/base URLs, SSRF controls |
| JWT scope test pass nhưng signature sai | Test dùng mockJwt bypass decoder | Signed JWT integration test |
| MockWebServer trả 403 nhưng không có scope check | Stub chỉ script status | Resource Server actual security test |
| Refresh token grant xuất hiện sai kỳ vọng | Đang dùng khác grant/cấu hình | Client Credentials thường reauthorize |
| Scheduled job hoạt động ở controller nhưng không ở background | Dùng servlet request manager | AuthorizedClientServiceOAuth2AuthorizedClientManager |
| Reactive job thiếu ServerWebExchange | Dùng reactive request-bound manager | AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager |
| WebClient gắn token mọi hosts | Default client registration/authorized client áp rộng | Explicit per-request client + allowed destinations |
| Client secret lộ CI logs | HTTP wire logging/token body dump | Redact Authorization & token responses |
| Boot test fail vì cố discovery OIDC | Có issuer-uri/network dependency không cần thiết | Explicit token-uri cho M2M |
| API báo thiếu authority dù JWT scope có | Converter claim/prefix tùy provider | JwtGrantedAuthoritiesConverter, scope/scp |
| Token issued nhưng không đúng audience | AS resource/audience config sai | RFC 8707/resource-specific issuance |

---

## 28. Bài thực hành

### Bài 1 — Request đúng grant

Client cần Reports token.

**Đề bài:** token endpoint phải nhận `grant_type` nào?

> **`client_credentials`**, HTTP POST form, xác thực client theo phương thức được AS cho phép. Không có authorization code hay PKCE verifier.

### Bài 2 — Requested vs granted scopes

Registration xin `reports.read reports.export`, token response chỉ có `reports.read`.

**Đề bài:** client có được gọi export endpoint và mong 200 không?

> Không. Token thiếu `reports.export`; Resource Server phải bảo vệ endpoint bằng quyền thực sự được cấp, thường trả 403 khi token hợp lệ nhưng thiếu scope.

### Bài 3 — scope field bị bỏ

Token response không có field `scope`.

**Đề bài:** có được tự kết luận token có tất cả quyền không?

> Không. Theo RFC scope có thể được bỏ khi không khác requested scope; cần tuân theo AS contract và không suy ra “toàn quyền”.

### Bài 4 — client_secret_basic

**Đề bài:** Basic credential được gửi tới đâu?

> Tới **Authorization Server token endpoint**, không phải downstream API. Downstream nhận **Bearer access token**.

### Bài 5 — Static service principal

Job chạy 100 lần; mỗi lần dùng `principal(UUID.randomUUID().toString())`.

**Vấn đề:** authorized client cache có thể lưu theo 100 principal khác nhau, làm tăng token requests. Dùng một principal ổn định theo service identity.

### Bài 6 — Manager chạy ngoài HTTP request

Scheduled job dùng `DefaultOAuth2AuthorizedClientManager` và gặp lỗi request context.

**Hướng sửa:** `AuthorizedClientServiceOAuth2AuthorizedClientManager` với OAuth2AuthorizedClientService.

### Bài 7 — Không có token mà API vẫn được gọi

AS trả `invalid_client`; code fallback gửi `Authorization: Bearer null` tới API.

**Đánh giá:** Sai. Token request thất bại thì không thực hiện authorized downstream call.

### Bài 8 — Token còn hạn nhưng downstream 401

**Đề bài:** có chắc token expired không?

> Không. Có thể wrong audience, wrong issuer, revoked token hoặc signature issue. Kiểm tra Resource Server validation và response challenge.

### Bài 9 — 403 insufficient_scope

Client lập tức retry bằng một client ID admin.

**Đánh giá:** Privilege escalation không được phê duyệt. Sửa registration/scope/AS policy nếu hợp lệ, không tự đổi sang credential mạnh hơn.

### Bài 10 — Token response không có refresh_token

**Đề bài:** có phải server thiếu chức năng?

> Không. Client Credentials thường không cấp refresh token. Khi token hết hạn, client có thể xin token mới bằng client_credentials.

### Bài 11 — Resource Server JWT mock tests

Test dùng `jwt().authorities(SCOPE_reports.read)` rồi nhận 200.

**Đề bài:** đã test signature của JWT chưa?

> Chưa. Mock JWT bỏ qua decoding/signature verification; cần signed JWT integration test hoặc JwtDecoder test.

### Bài 12 — Token đúng scope nhưng sai aud

Token có `reports.read` nhưng `aud=billing-api`.

**Kết quả mong đợi:** Reports API từ chối vì audience không hợp lệ. Scope không thay audience validation.

### Bài 13 — Mock downstream trả 403

Test script MockWebServer trả 403 cho request chứa token.

**Đề bài:** đã chứng minh authorization code RS production chưa?

> Chưa. Chỉ chứng minh client xử lý HTTP contract. Cần Resource Server security integration test riêng.

### Bài 14 — Concurrent cache miss

Hai requests cùng lúc đều xin token một lần.

**Đề bài:** có thể kết luận manager bị hỏng không?

> Không nhất thiết. Nếu không có single-flight/lock, cache miss song song có thể phát hai requests. Kiểm tra safety, quota và kỳ vọng efficiency riêng.

### Bài 15 — WebFlux background job

Reactive service chạy ngoài ServerWebExchange.

**Giải pháp:** `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` và `ReactiveOAuth2AuthorizedClientService`; test bằng StepVerifier.

### Bài 16 — Access token lộ trong logs

RestClient debug log in toàn bộ `Authorization: Bearer ...`.

**Giải pháp:** Redaction ở HTTP client/interceptor/proxy/APM, không log token values. Dùng only test tokens.

### Bài 17 — Hai APIs dùng cùng registration

Reports và Billing có requirements về scope/audience khác nhau nhưng share một token.

**Rủi ro:** Token bị dùng sai resource. Thiết kế registrations/AS audience/resource riêng theo policy và kiểm thử không gửi nhầm token.

### Bài 18 — Client muốn impersonate user

Business muốn “login thay Alice” bằng client_credentials token.

**Đánh giá:** Grant này xác thực client/service, không chứng minh Alice đã login. Cần delegated authorization/token exchange flow phù hợp và policy rõ.

### Bài 19 — Token endpoint chỉ chấp nhận private_key_jwt

Test client dùng Basic và nhận invalid_client.

**Đề bài:** có nên sửa test server để Basic pass?

> Không nếu production AS yêu cầu private_key_jwt. Đổi client configuration và test method phù hợp với contract thực tế.

### Bài 20 — M2M token được chấp nhận ngoài audience

Reports API tin token chỉ vì signature/issuer đúng, không kiểm `aud`.

**Rủi ro:** Token substitution giữa resource servers. Cần audience validator và negative integration test.

---

## 29. Ma trận kiểm thử đề xuất cho production

| ID | Mức test | Điều kiện | Expected |
| --- | --- | --- | --- |
| M2M-01 | Client HTTP | Token 200, scope full | Bearer header đúng |
| M2M-02 | Client HTTP | Token 200, scope reduced | Granted scopes chỉ subset |
| M2M-03 | Client HTTP | Token 400 invalid_client | Không gọi downstream |
| M2M-04 | Client HTTP | Token 400 invalid_scope | Không gọi downstream |
| M2M-05 | Client HTTP | AS timeout/503 | Failure category rõ, bounded retry |
| M2M-06 | Client HTTP | Token response malformed | Fail closed |
| M2M-07 | Client HTTP | Same principal, token valid | Reuse token |
| M2M-08 | Client HTTP | Token expired/near expiry | New client credentials request |
| M2M-09 | Client HTTP | Different registration | Không reuse token sai |
| M2M-10 | Client HTTP | Two concurrent calls | Không mix token, kiểm race |
| M2M-11 | Downstream contract | API 200 | Parse response |
| M2M-12 | Downstream contract | API 401 invalid_token | Failure handler/authorized client lifecycle |
| M2M-13 | Downstream contract | API 403 insufficient_scope | Không tự nâng quyền |
| M2M-14 | Downstream contract | API 429 | Rate limit handling |
| M2M-15 | Downstream contract | API 503 | Outage riêng RS |
| M2M-16 | RS security | JWT valid + required scope | HTTP 200 |
| M2M-17 | RS security | JWT valid + missing scope | HTTP 403 |
| M2M-18 | RS security | JWT wrong issuer | HTTP 401 |
| M2M-19 | RS security | JWT wrong audience | HTTP 401 |
| M2M-20 | RS security | JWT expired/invalid signature | HTTP 401 |
| M2M-21 | RS security | Opaque active=false | HTTP 401 |
| M2M-22 | Configuration | Boot registration token-uri binding | Đúng mock AS |
| M2M-23 | Security | User-supplied outbound host | Không gửi Bearer token ra host lạ |
| M2M-24 | Security | No real tokens in logs | Không lộ secrets |
| M2M-25 | Reactive | WebClient + reactive manager | Mono completes with correct token/header |
| M2M-26 | Lifecycle | After AS recovery | Có thể xin token mới |
| M2M-27 | Policy | Client token thiếu tenant permission | API bị deny theo ACL |
| M2M-28 | Separation | Browser OIDC user vs machine identity | Không tự impersonate user |

### 29.1. Các trường hợp không nên bỏ

Một suite chỉ có 200 happy path mà không có **invalid_client**, **reduced scope**, **downstream 403** và **audience mismatch** sẽ bỏ sót nhiều lỗi có rủi ro bảo mật cao.

### 29.2. Test phải xác định boundary rõ

- **Mock manager** → unit service test;
- **Real manager + mock AS** → client integration;
- **Real HTTP interceptor + mock RS** → outbound contract;
- **Real RS SecurityFilterChain + decoder** → downstream authorization;
- **Browser/mockOidcLogin** → interactive login testing, **không phải** M2M grant.

---

## 30. Quy trình điều tra khi integration test thất bại

1. Xác nhận registration `reports-machine` tồn tại và có grant `client_credentials`.
2. Xác nhận code chọn đúng `clientRegistrationId`.
3. Nếu job không có HTTP request, xác nhận manager là **service-level** thay vì request-bound.
4. Xác nhận service principal ổn định và đúng cache key.
5. Xác nhận test token URI trỏ tới local mock AS, không production.
6. Xác nhận POST token request có client authentication phù hợp, form encoded, `grant_type` đúng.
7. Xác nhận requested scopes và granted scopes **không bị nhầm**.
8. Xác nhận token response đầy đủ `access_token`, `token_type`, expiry và scope theo contract.
9. Kiểm tra RestClient/WebClient interceptor được gắn vào đúng client instance.
10. Kiểm tra outbound request chỉ đến allowlisted downstream host và mang Bearer header.
11. Nếu HTTP 401, xác nhận expiry/issuer/audience/token status/signature.
12. Nếu HTTP 403, xác nhận required scope hoặc business ACL.
13. Nếu error `invalid_scope` ở token endpoint, sửa client/AS policy chứ không sửa RS.
14. Nếu có nhiều token requests, kiểm tra cache principal, expiry/skew, concurrent miss.
15. Nếu dùng WebFlux, xác nhận `Mono` thực sự được subscribe và manager phù hợp WebExchange/background.
16. Nếu dùng Resource Server mockJwt, nhớ rằng signature validation **không được thực thi**.
17. Đảm bảo log/test artifacts đã che Authorization headers, secrets và tokens.
18. Chỉ sau khi xác định đúng tầng lỗi mới sửa code/config; không bỏ validation để “pass test”.

---

## 31. Tổng kết theo trách nhiệm của từng thành phần

```text
                   SPRING OAUTH2 CLIENT
                    (client_credentials)
                             |
                             | ClientRegistration:
                             |   id=reports-machine
                             |   grant=client_credentials
                             |   requested scopes=reports.read reports.export
                             v
              OAuth2AuthorizedClientManager
                             |
                             | POST /token
                             | Client authentication
                             | grant_type=client_credentials
                             | scope=...
                             v
                     AUTHORIZATION SERVER
                             |
                             | Access token, expiry,
                             | granted scope=reports.read
                             v
              OAuth2AuthorizedClientService
                key=(registration, service principal)
                             |
                             v
                    RestClient / WebClient
                             |
                             | Authorization: Bearer <access_token>
                             v
                     DOWNSTREAM API / RS
                             |
                  +----------+------------+
                  |          |            |
               200 OK      401         403
               scope ok    invalid     insufficient
                           token       scope/ACL

Integration tests:
  1. Assert token request + client auth + requested scope
  2. Assert token response + granted scopes + cache
  3. Assert downstream Bearer header and HTTP contract
  4. Assert actual Resource Server scope/issuer/audience policy separately
```

### Các điểm cần ghi nhớ

1. **Client Credentials là machine-to-machine OAuth2**, không phải OIDC end-user login.
2. **`grant_type=client_credentials`** phải được gửi tới token endpoint cùng client authentication phù hợp.
3. **Requested scopes, granted scopes và required downstream scopes là ba lớp khác nhau**.
4. **`AuthorizedClientServiceOAuth2AuthorizedClientManager`** phù hợp scheduled/service code ngoài servlet request.
5. **RestClient `OAuth2ClientHttpRequestInterceptor`** giúp tự lấy token và gắn Bearer header; test nên dùng service principal ổn định.
6. **Token cache key thường gắn registration và principal**; đổi principal có thể dẫn đến nhiều token requests.
7. **Downstream 401 khác 403**: invalid token khác insufficient scope; không retry hoặc nâng quyền mù quáng.
8. **Một mock downstream trả 403 không chứng minh scope enforcement thực tế**; cần Resource Server security test riêng.
9. **JWT scope/issuer/audience/signature/expiry** đều quan trọng; scope đúng không tự làm token hợp lệ cho mọi APIs.
10. **Reactive WebFlux dùng ReactiveOAuth2AuthorizedClientManager và WebClient**, không thay thế bằng Servlet manager.
11. **Client Credentials thường không cấp refresh token**; khi access token hết hạn thường xin token mới bằng cùng grant.
12. **Không lộ secrets/tokens, không chuyển Bearer token tới URL untrusted và không impersonate end-user** bằng machine credentials.

### Tài liệu tham khảo chính thức

- [Spring Security 6.5 — Servlet OAuth2 Client Core Interfaces](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/core.html)
- [Spring Security 6.5 — Authorized Client Features: RestClient, WebClient, principals](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/client/authorized-clients.html)
- [Spring Security 6.5 — Reactive OAuth2 Client Core](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/core.html)
- [Spring Security 6.5 — Reactive Authorized Client Features](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/client/authorized-clients.html)
- [Spring Security 6.5 — Resource Server JWT and Scope Authorities](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Security API — AuthorizedClientServiceOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html)
- [Spring Security API — OAuth2ClientHttpRequestInterceptor](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/client/web/client/OAuth2ClientHttpRequestInterceptor.html)
- [RFC 6749 — OAuth 2.0 Authorization Framework, Client Credentials](https://www.rfc-editor.org/rfc/rfc6749#section-4.4)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 8707 — Resource Indicators for OAuth 2.0](https://www.rfc-editor.org/rfc/rfc8707)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700)
- [MockWebServer — Square OkHttp](https://github.com/square/okhttp/tree/master/mockwebserver)
