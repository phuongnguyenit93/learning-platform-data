# 15.3. `AuthorizedClientServiceOAuth2AuthorizedClientManager` ngoài HTTP request

Trong **Spring Security OAuth 2.0/OIDC Client**, nhiều ví dụ đăng nhập và gọi API bắt đầu từ một HTTP request do trình duyệt gửi tới Spring MVC. Tuy nhiên, hệ thống thực tế còn có các tác vụ **không chạy trong vòng đời `HttpServletRequest`**: job định kỳ, message consumer, command-line runner, xử lý queue, sự kiện nghiệp vụ hoặc service-to-service background task.

Những tác vụ đó vẫn có thể cần access token OAuth 2.0 để gọi API. Nếu dùng sai manager, ứng dụng có thể phụ thuộc vào HTTP request/session không tồn tại hoặc vô tình lấy token của người dùng đang đăng nhập. Spring Security giải quyết nhu cầu này bằng **`AuthorizedClientServiceOAuth2AuthorizedClientManager`** — một triển khai `OAuth2AuthorizedClientManager` được thiết kế cho **service tier và tác vụ chạy ngoài HTTP request**.

Bài này giải thích mô hình authorized client, cách lựa chọn manager, cấu hình grant `client_credentials` cho tác vụ nền, cơ chế tái sử dụng/làm mới token, lưu trữ `OAuth2AuthorizedClientService`, nhận diện `principal`, xử lý lỗi và những giới hạn khi muốn làm việc theo quyền của người dùng.

## 1. Tình huống thực tế: job gọi API mà không có trình duyệt

Giả sử ứng dụng Spring Boot chạy job mỗi 15 phút:

```text
@Scheduled
    -> lấy danh sách báo cáo từ Reporting API
    -> xử lý/tổng hợp
    -> lưu kết quả nội bộ
```

Reporting API yêu cầu:

```http
GET /v1/reports HTTP/1.1
Host: api.example.test
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
```

Token phải được lấy từ Authorization Server qua **Token Endpoint**. Nhưng bên trong phương thức `@Scheduled`:

- Không có người dùng gửi một request tới controller.
- Không có `HttpServletRequest` và `HttpServletResponse` của thread hiện tại.
- Không có session đăng nhập browser cần thiết để thực thi một job hệ thống.
- `SecurityContextHolder` có thể rỗng hoặc không chứa một user authentication.
- Không thể chuyển trình duyệt sang Authorization Endpoint để người dùng đăng nhập.

Vì vậy, với tác vụ gọi API bằng quyền của **chính ứng dụng**, grant phù hợp thường là **`client_credentials`**, và manager phù hợp là **`AuthorizedClientServiceOAuth2AuthorizedClientManager`**.

Cấu trúc mong muốn:

```mermaid
flowchart TD
    A["@Scheduled / Message Consumer / Service"] --> B["OAuth2AuthorizeRequest"]
    B --> C["AuthorizedClientServiceOAuth2AuthorizedClientManager"]
    C --> D["OAuth2AuthorizedClientService"]
    D --> E{"Đã có authorized client còn phù hợp?"}
    E -->|Có| F["Trả về access token hiện có"]
    E -->|Chưa có hoặc cần cấp lại| G["OAuth2AuthorizedClientProvider"]
    G --> H["Authorization Server / Token Endpoint"]
    H --> I["Access token mới"]
    I --> D
    F --> J["Gọi downstream API với Bearer token"]
    I --> J
```

Sơ đồ mô tả cơ chế tổng quát. Manager/provider quyết định có cấp lại token hay trả client đã lưu, tùy grant, token hiện tại và khả năng reauthorization.

## 2. Các thành phần quan trọng của Spring OAuth2 Client

Trước khi viết code, cần hiểu rõ những interface/lớp sẽ xuất hiện.

| Thành phần | Vai trò | Lưu ý |
|---|---|---|
| `ClientRegistration` | Cấu hình Client đã đăng ký: client ID, secret, grant, scopes và Token Endpoint | Không phải token |
| `ClientRegistrationRepository` | Tra `ClientRegistration` bằng `registrationId` | Spring Boot thường tạo từ YAML/properties |
| `OAuth2AuthorizedClient` | Một Client đã được cấp quyền, gắn với principal name và access/refresh token | Đại diện cho **kết quả authorization** |
| `OAuth2AuthorizedClientService` | Lưu, tìm và xóa `OAuth2AuthorizedClient` | Không cần HTTP request |
| `OAuth2AuthorizedClientManager` | Điều phối cấp/tái cấp quyền để có authorized client phù hợp | Giao diện chung |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | Manager dùng **service** để lưu authorized client, hoạt động ngoài Servlet request | Thích hợp cho background/service tier |
| `DefaultOAuth2AuthorizedClientManager` | Manager dùng repository gắn với Servlet request | Dùng trong HTTP request |
| `OAuth2AuthorizedClientProvider` | Thực thi một hoặc nhiều grant như client credentials, refresh token | Chọn bằng builder |
| `OAuth2AuthorizeRequest` | Yêu cầu manager authorize một registration với principal cụ thể | Có thể cấp principal name dạng String |

Điểm quan trọng là **`ClientRegistration` và `OAuth2AuthorizedClient` khác nhau**:

```text
ClientRegistration("reporting-job")
    clientId
    clientSecret
    grantType = client_credentials
    tokenUri
    scopes = reports.read

OAuth2AuthorizedClient
    clientRegistration = "reporting-job"
    principalName = "service:reporting-job"
    accessToken = (token value, type, issuedAt, expiresAt, scopes)
    refreshToken = null (thường gặp với client_credentials)
```

Một registration có thể tồn tại trước khi token được cấp. `OAuth2AuthorizedClient` chỉ xuất hiện sau một lần authorize thành công hoặc sau khi được khôi phục từ kho lưu.

## 3. Chọn đúng manager: trong và ngoài Servlet HTTP request

Spring Security cung cấp hai triển khai thường được nhắc cùng nhau:

| Tiêu chí | `DefaultOAuth2AuthorizedClientManager` | `AuthorizedClientServiceOAuth2AuthorizedClientManager` |
|---|---|---|
| Ngữ cảnh chính | Servlet request có `HttpServletRequest`/`HttpServletResponse` | Scheduler, worker, queue consumer, service tier |
| Cơ chế lưu | `OAuth2AuthorizedClientRepository` | `OAuth2AuthorizedClientService` |
| Phụ thuộc request/session web | Có thể cần | Không cần |
| Ví dụ | Controller gọi downstream API theo user đang đăng nhập | Job gọi API bằng client credentials |
| Principal | Thường là Authentication hiện tại | Có thể cung cấp principal name tường minh |
| Khởi tạo | `(ClientRegistrationRepository, OAuth2AuthorizedClientRepository)` | `(ClientRegistrationRepository, OAuth2AuthorizedClientService)` |
| Thực hiện grant | Qua `OAuth2AuthorizedClientProvider` | Qua `OAuth2AuthorizedClientProvider` |

**Không chọn manager dựa riêng vào việc ứng dụng có dùng Spring MVC hay không.** Một ứng dụng MVC vẫn có thể có scheduled task; tác vụ nền đó nên dùng service-based manager.

### 3.1. Vì sao dùng `DefaultOAuth2AuthorizedClientManager` trong `@Scheduled` có thể lỗi?

Manager dành cho Servlet request có cơ chế lấy HTTP request/response theo request context. Trong background thread, thread-bound request attributes thường không tồn tại.

Một số triệu chứng:

```text
No thread-bound request found
No current ServletRequestAttributes
Cannot find HttpServletRequest / HttpServletResponse
```

Thông báo cụ thể phụ thuộc phiên bản và đường đi của code. Cố giả lập `HttpServletRequest` chỉ để manager hoạt động thường là sai hướng: job không cần phiên browser, và lưu token dưới session giả có thể làm mất token giữa các lần chạy.

### 3.2. Tại sao `AuthorizedClientServiceOAuth2AuthorizedClientManager` hoạt động được?

Service manager:

1. Nhận `registrationId` và `principal` từ `OAuth2AuthorizeRequest`.
2. Tìm `ClientRegistration` trong repository cấu hình.
3. Tìm authorized client cũ qua `OAuth2AuthorizedClientService` khi thích hợp.
4. Gọi `OAuth2AuthorizedClientProvider` để cấp/tái cấp quyền nếu cần.
5. Lưu authorized client sau khi authorize thành công theo success handler mặc định.
6. Trả về `OAuth2AuthorizedClient` cho caller hoặc `null` khi không hỗ trợ authorization theo hợp đồng.

Không cần một `HttpServletRequest` giả. Khi tác vụ tự động gọi `authorize(...)`, manager có thể lấy và tái sử dụng token theo grant đã cấu hình.

## 4. Phân biệt hai flow: `client_credentials` và quyền người dùng

Một lựa chọn thiết kế rất quan trọng: tác vụ nền đang hành động **nhân danh ai**?

### 4.1. Service-to-service bằng `client_credentials`

Ví dụ job đồng bộ báo cáo:

```text
Spring job (Client A)
  -> client_id + client_secret / private key
  -> Token Endpoint
  -> access token đại diện cho Client A
  -> Reporting API
```

Không có người dùng tương tác, không có ID Token OIDC đại diện cho user đăng nhập, và thường không có refresh token. Nếu access token hết hạn, Client dùng credential của chính nó để **xin token mới**.

Đây là lựa chọn thường phù hợp nhất cho service account hoặc tác vụ có quyền ứng dụng.

### 4.2. Background task cần quyền người dùng

Một tình huống khác: người dùng đã đăng nhập OIDC bằng authorization code, đồng ý cấp quyền offline, và ứng dụng muốn tiếp tục đồng bộ một tài nguyên **đúng theo quyền đã cấp của người dùng ấy**.

Lúc này:

- Token ban đầu được cấp qua flow tương tác **`authorization_code`**.
- Authorized client được gắn với **principal của người dùng cụ thể**.
- Nếu Authorization Server cấp `refresh_token`, backend có thể dùng `refresh_token` để lấy access token mới khi được phép.
- Tác vụ nền cần truy xuất **đúng authorized client đã lưu** và tuân theo consent, scope, audience, expiry, revocation.
- Nếu không có refresh token hoặc provider từ chối, job phải xử lý bằng một flow tương tác lại; không tự chuyển sang quyền của người khác.

**Không thay `principal("username")` trong `OAuth2AuthorizeRequest` để mạo danh một user chưa từng cấp token.** Chuỗi principal là khóa tra cứu/lưu authorized client, không phải một “chứng chỉ xác thực” để Authorization Server cấp quyền của người đó.

### 4.3. Tóm tắt cách chọn

| Nhu cầu | Grant/nguồn token | Principal cho manager |
|---|---|---|
| Job hệ thống đọc API dữ liệu chung | `client_credentials` | Tên hệ thống ổn định như `service:reporting-job` |
| Worker gửi event bằng quyền ứng dụng | `client_credentials` | Tên service hoặc tenant rõ ràng |
| Job tiếp tục xử lý dữ liệu user đã ủy quyền | Authorized client từ `authorization_code` + `refresh_token` nếu có | **Đúng principal của user** đã được lưu |
| Browser OIDC Login | `authorization_code` và `oauth2Login` | Principal đăng nhập trong request |
| Frontend chưa đăng nhập, muốn đi qua trang consent | Flow authorization code qua browser | Không khởi tạo tương tác từ background thread |

## 5. Cấu hình Spring Boot cho Client Credentials

Giả sử một Authorization Server cấp Client `reporting-job` để truy cập `https://api.example.test/v1/reports`, với scope `reports.read`.

Trong `application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          reporting-job:
            provider: reporting-api
            client-id: ${REPORT_CLIENT_ID}
            client-secret: ${REPORT_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - reports.read

        provider:
          reporting-api:
            token-uri: https://id.example.test/oauth2/token
```

Giải thích:

- `registration.reporting-job` là khóa nội bộ **`registrationId`**.
- `provider: reporting-api` trỏ tới cấu hình Token Endpoint.
- `authorization-grant-type: client_credentials` nói rõ không cần browser redirect.
- `client-authentication-method: client_secret_basic` minh họa cách Client xác thực với Token Endpoint; provider có thể yêu cầu phương thức khác.
- `scope: reports.read` là phạm vi ứng dụng muốn xin; nó phải được Authorization Server cho phép.
- Không cần `redirect-uri` cho chính grant client credentials.
- Không cần `authorization-uri` khi chỉ dùng client credentials; token request đi trực tiếp tới Token Endpoint.
- Không mặc định xin `openid` vì đây **không phải OIDC đăng nhập người dùng**.

Tên miền `example.test` và các biến môi trường là placeholder. Trong hệ thống thật, đăng ký Client tại Authorization Server, sử dụng Token Endpoint chính xác và bảo vệ credentials bằng biến môi trường, secret manager hoặc giải pháp quản lý khóa phù hợp.

### 5.1. Token request diễn ra như thế nào?

Khi chưa có access token phù hợp, manager gọi provider client credentials, tạo một request dạng:

```http
POST /oauth2/token HTTP/1.1
Host: id.example.test
Authorization: Basic EXAMPLE_CLIENT_AUTH_HEADER
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=client_credentials&scope=reports.read
```

Token Endpoint có thể trả:

```json
{
  "access_token": "EXAMPLE_SERVICE_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 1800,
  "scope": "reports.read"
}
```

Không có authorization code, browser callback hay ID Token. `refresh_token` cũng thường không có trong client credentials response; Authorization Server thường cho phép Client dùng credentials của chính nó để xin access token mới khi cần.

### 5.2. Dependency cần thiết

Ứng dụng Spring Boot cần starter OAuth2 Client tương thích với phiên bản Boot đang dùng. Ví dụ với một nhánh Spring Boot 3.x:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
```

Tên starter/artifact có thể khác ở những nhánh Spring Boot mới, vì vậy hãy dùng dependency/BOM của dự án và tham khảo tài liệu chính thức của đúng version. Ví dụ Java sau tập trung vào API của Spring Security OAuth2 Client.

Không cần bật `oauth2Login` để lấy token bằng `client_credentials` cho một job hệ thống. Nếu ứng dụng cũng có OIDC Login cho người dùng, đó là cấu hình flow riêng.

## 6. Tạo `AuthorizedClientServiceOAuth2AuthorizedClientManager`

Một bean cấu hình điển hình:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class OAuth2ServiceClientConfig {

    @Bean
    OAuth2AuthorizedClientManager serviceAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        var manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations,
                authorizedClients
            );

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

Phân tích lần lượt:

1. `ClientRegistrationRepository` lấy registration `reporting-job` đã khai báo trong YAML.
2. `OAuth2AuthorizedClientService` cung cấp kho authorized client không phụ thuộc HTTP session.
3. `OAuth2AuthorizedClientProviderBuilder.builder().clientCredentials().build()` cho phép manager dùng Client Credentials Grant.
4. `AuthorizedClientServiceOAuth2AuthorizedClientManager` kết hợp registration, lưu trữ và provider.
5. `OAuth2AuthorizedClientManager` là interface để code nghiệp vụ phụ thuộc vào abstraction thay vì tạo manager trong mỗi job.

Spring Boot có thể auto-configure repository/service mặc định phù hợp với cấu hình Client. Nếu ứng dụng có nhiều bean `OAuth2AuthorizedClientManager`, cần dùng `@Qualifier` hoặc tên bean rõ ràng để inject đúng service manager cho background task.

### 6.1. Vì sao phải đặt `setAuthorizedClientProvider`?

Manager điều phối một hoặc nhiều `OAuth2AuthorizedClientProvider`. Provider quyết định grant nào được xử lý khi `authorize(...)` được gọi.

Nếu muốn chỉ cho job sử dụng client credentials, cấu hình:

```java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build();
```

là đủ và rõ ràng. Không thêm `authorizationCode()` chỉ vì ứng dụng có OIDC Login ở một nơi khác.

Nếu manager không có provider phù hợp với grant trong ClientRegistration, `authorize(...)` có thể trả `null`. Điều này phải được xử lý thay vì giả định luôn nhận access token.

### 6.2. Có cần tạo bean `OAuth2AuthorizedClientService` không?

Nếu Spring Boot đã cung cấp một bean thích hợp, không cần tự tạo. Khi muốn chỉ rõ kho lưu cho ví dụ phát triển, có thể dùng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Bean
OAuth2AuthorizedClientService authorizedClientService(
        ClientRegistrationRepository registrations) {

    return new InMemoryOAuth2AuthorizedClientService(registrations);
}
```

**Chỉ chọn một** cơ chế tạo bean để tránh trùng lặp. `InMemoryOAuth2AuthorizedClientService` dễ dùng trong demo/test, nhưng token mất khi ứng dụng restart và không được chia sẻ giữa nhiều instance. Phần lưu bền vững được trình bày ở mục sau.

## 7. Gọi `authorize(...)` trong một job `@Scheduled`

Điểm quan trọng: **phải cung cấp một principal name ổn định** ngay cả khi không có người dùng đăng nhập.

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;

public final class ServiceTokenProvider {

    private final OAuth2AuthorizedClientManager manager;

    public ServiceTokenProvider(OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    public String requireAccessToken() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("reporting-job")
                .principal("service:reporting-job")
                .build();

        OAuth2AuthorizedClient authorizedClient =
            manager.authorize(request);

        if (authorizedClient == null) {
            throw new IllegalStateException(
                "OAuth2 authorization is not supported for reporting-job"
            );
        }

        return authorizedClient.getAccessToken().getTokenValue();
    }
}
```

Ý nghĩa:

- `withClientRegistrationId("reporting-job")` tìm đúng `ClientRegistration`.
- `principal("service:reporting-job")` gán **khóa logic** để manager/service lưu và tìm authorized client.
- `authorize(...)` có thể trả client đã có hoặc cấp lại khi provider thấy cần.
- Chỉ sau khi kết quả khác `null` mới lấy `getAccessToken()`.
- Giá trị access token chỉ dùng nội bộ để tạo HTTP `Authorization` header; không log/hiển thị cho frontend.

**`principal("service:reporting-job")` không tạo ra một tài khoản người dùng thật.** Nó giúp xác định không gian lưu token của job. Với `client_credentials`, token đại diện cho Client theo chính sách Authorization Server, không đại diện cho user có tên String đó.

### 7.1. Một job hoàn chỉnh gọi API bằng `RestClient`

Ví dụ dưới đây sử dụng `RestClient` có trong Spring Framework hiện đại (Spring Framework 6.1+). Với dự án cũ hơn, có thể dùng HTTP client mà phiên bản hỗ trợ, giữ nguyên cách lấy token bằng manager.

```java
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Service;
import org.springframework.web.client.RestClient;

@Service
public class ReportingSyncJob {

    private static final String REGISTRATION_ID = "reporting-job";
    private static final String SERVICE_PRINCIPAL = "service:reporting-job";

    private final OAuth2AuthorizedClientManager manager;
    private final RestClient reportingApi;

    public ReportingSyncJob(
            OAuth2AuthorizedClientManager manager,
            RestClient.Builder restClientBuilder) {

        this.manager = manager;
        this.reportingApi = restClientBuilder
            .baseUrl("https://api.example.test")
            .build();
    }

    @Scheduled(cron = "0 */15 * * * *")
    public void synchronize() {
        OAuth2AuthorizeRequest authorizeRequest =
            OAuth2AuthorizeRequest
                .withClientRegistrationId(REGISTRATION_ID)
                .principal(SERVICE_PRINCIPAL)
                .build();

        OAuth2AuthorizedClient authorized =
            manager.authorize(authorizeRequest);

        if (authorized == null) {
            throw new IllegalStateException(
                "No authorized client for " + REGISTRATION_ID
            );
        }

        String accessToken = authorized.getAccessToken().getTokenValue();

        String reportsJson = reportingApi.get()
            .uri("/v1/reports")
            .headers(headers -> headers.setBearerAuth(accessToken))
            .retrieve()
            .body(String.class);

        // Thay bằng logic lưu/xử lý nghiệp vụ của ứng dụng.
        processReports(reportsJson);
    }

    private void processReports(String reportsJson) {
        // Minh họa: parse và lưu báo cáo trong service riêng.
    }
}
```

Bật scheduler trong một class cấu hình:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableScheduling;

@Configuration
@EnableScheduling
public class SchedulerConfig {
}
```

Cần đảm bảo project có Spring Web/RestClient và OAuth2 Client dependencies phù hợp; code ví dụ dùng injection `OAuth2AuthorizedClientManager` và `RestClient.Builder` mà Spring Boot cung cấp. Nếu nhiều manager cùng type, inject theo qualifier.

**Không nên log biến `accessToken` hoặc `reportsJson` khi nó chứa dữ liệu nhạy cảm.** Ví dụ `processReports(...)` chỉ là chỗ giữ cho logic nghiệp vụ, không phải triển khai production.

### 7.2. Chỉ tạo token khi cần gọi API

Một nhầm lẫn thường gặp là lấy token một lần trong constructor rồi giữ mãi:

```java
// KHÔNG NÊN:
class Job {
    private final String token = fetchAtStartup();
}
```

Access token có thời hạn. Nếu job chạy nhiều giờ, token từ lúc startup có thể đã hết hạn. Thay vào đó, **gọi manager tại mỗi lần thực hiện thao tác cần token** để nó có cơ hội tra cứu/tái cấp token phù hợp.

### 7.3. Vì sao không kiểm tra expiry thủ công khắp nơi?

`OAuth2AuthorizedClientProvider` đã có nhiệm vụ quyết định khi nào cần reauthorization theo grant/authorized client hiện tại, bao gồm thời hạn token và chính sách clock skew phù hợp. Nếu controller/job tự lưu `expiresAt` rồi viết thêm mười cơ chế refresh khác nhau, dễ có race condition và logic mâu thuẫn.

Có thể dùng `getExpiresAt()` cho telemetry hoặc chẩn đoán đã lọc, nhưng **không thay thế manager bằng lịch gọi Token Endpoint tự xây** nếu không có lý do rõ ràng.

## 8. Bản chất của `principal` trong service manager

### 8.1. Principal name là khóa của authorized client

`OAuth2AuthorizedClientService` thường tìm token bằng cặp:

```text
(clientRegistrationId, principalName)
```

Ví dụ:

```text
("reporting-job", "service:reporting-job")
    -> access token đã cấp cho job

("billing-job", "service:billing-job")
    -> access token của Client khác

("company-login", "user-782")
    -> authorized client theo một người dùng đã đăng nhập (nếu được lưu)
```

Nếu cùng registration nhưng dùng một principal name khác ở mỗi lần chạy:

```java
// KHÔNG NÊN cho token Client Credentials được chia sẻ ổn định:
.principal("service:job:" + UUID.randomUUID())
```

manager có thể coi đó là những authorized clients khác nhau, làm tăng số lần xin token và số record lưu không cần thiết.

### 8.2. Khi nào dùng một principal dùng chung?

Nếu mọi lần chạy của cùng job đều đại diện cho **chính Client** với `client_credentials`, một principal ổn định như `"service:reporting-job"` thường hợp lý. Nó không phụ thuộc thread, session hoặc username của người dùng.

Với multi-tenant, cần xác định mỗi tenant dùng ClientRegistration/credential/scope nào. Không dùng một principal chung để chia sẻ authorized client giữa những tenant có trust boundary khác nhau.

### 8.3. Không dùng `principal` để mạo danh user

Ví dụ nguy hiểm:

```java
// KHÔNG PHẢI CƠ CHẾ XIN TOKEN CHO BẤT KỲ NGƯỜI DÙNG:
OAuth2AuthorizeRequest request = OAuth2AuthorizeRequest
    .withClientRegistrationId("company-user-login")
    .principal(requestedUserIdFromQueue)
    .build();
```

Nếu một record trong kho chứa authorized client của người dùng nào đó, việc caller chọn `principalName` có thể khiến manager tìm token tương ứng. Do đó mã truy cập kho token phải được kiểm soát, đặc biệt trong các tác vụ multi-user.

**Một `principal(String)` không làm Authorization Server xác thực user mới.** Nó chỉ định định danh được dùng khi quản lý authorized client; quyền dùng token phải được bảo vệ bằng authorization nội bộ và chính sách consent của người dùng.

### 8.4. `Authentication` và tên principal String khác nhau thế nào?

`OAuth2AuthorizeRequest.Builder` hỗ trợ truyền `Authentication` hoặc principal name dạng `String`.

- Với request web theo user, việc truyền `Authentication` hợp lệ có thể giúp dùng ngữ cảnh người dùng đã xác thực.
- Với background job dùng `client_credentials`, một String ổn định đủ để phân vùng authorized client.
- Với job làm việc nhân danh user, phải dùng định danh user đã liên kết đúng authorized client và kiểm tra ai được phép chạy tác vụ đó.

Không tự tạo `UsernamePasswordAuthenticationToken` “đã authenticated” bằng tay chỉ để lấy token user. Nó không phải bằng chứng người dùng vừa đăng nhập tại IdP.

## 9. Vòng đời authorized client: cấp, tái sử dụng, cấp lại

`authorize(...)` không có nghĩa mỗi lần gọi sẽ luôn gửi HTTP request tới Token Endpoint.

Một vòng đời khái quát với `client_credentials`:

```mermaid
sequenceDiagram
    autonumber
    participant J as Scheduled Job
    participant M as Service AuthorizedClientManager
    participant S as OAuth2AuthorizedClientService
    participant P as ClientCredentialsProvider
    participant AS as Authorization Server

    J->>M: authorize(registrationId, service principal)
    M->>S: loadAuthorizedClient(registrationId, principalName)
    alt Chưa có token hoặc cần cấp lại
        M->>P: authorize(context)
        P->>AS: POST /token grant_type=client_credentials
        AS-->>P: access_token + expires_in
        P-->>M: OAuth2AuthorizedClient
        M->>S: saveAuthorizedClient(...)
        M-->>J: Authorized client mới
    else Token vẫn phù hợp
        S-->>M: Authorized client đã lưu
        M-->>J: Authorized client hiện tại
    end
```

Nếu token còn hiệu lực theo chính sách provider, manager có thể trả authorized client đang lưu. Khi hết hạn hoặc cần cấp lại theo quy tắc, Client Credentials Provider dùng Client authentication để xin token mới.

### 9.1. `authorize(...)` có thể trả `null`

Theo hợp đồng `OAuth2AuthorizedClientManager`, `authorize(...)` có thể trả `null` nếu không hỗ trợ authorization cho Client yêu cầu, ví dụ grant trong `ClientRegistration` không được các configured providers hỗ trợ.

Do đó:

```java
OAuth2AuthorizedClient client = manager.authorize(request);

if (client == null) {
    // Không có authorized client hợp lệ do manager cấp/tra được
    // theo tình huống không được hỗ trợ; xử lý lỗi cấu hình.
}
```

**Không** gọi ngay `manager.authorize(...).getAccessToken()` mà bỏ qua nhánh `null`.

Khi reauthorization không cần thiết hoặc không được hỗ trợ nhưng **đã có authorized client**, manager có thể trả về authorized client hiện tại theo hợp đồng. Vì vậy `null` không đồng nghĩa mọi lần lỗi token đều biểu diễn bằng `null`; nhiều lỗi thực sự phát sinh exception.

### 9.2. Kết quả không phải bảo đảm API sẽ chấp nhận

Manager quản lý token theo thông tin OAuth2 mà Client có. API vẫn có thể từ chối token vì:

- Token bị thu hồi ngoài luồng.
- Audience không hướng tới đúng Resource Server.
- Scope không đủ.
- Resource Server policy thay đổi.
- Clock skew hoặc thời hạn token khác cách Client tính.
- Client dùng nhầm token của một registration/tenant.

Do đó cần phân biệt **lỗi xin token từ Token Endpoint** với **lỗi API khi sử dụng token**. Không cứ gặp HTTP 403 là xóa token và xin lại vô hạn.

## 10. `OAuth2AuthorizedClientService` và các lựa chọn lưu trữ

### 10.1. Interface dùng làm gì?

`OAuth2AuthorizedClientService` thường cung cấp các thao tác:

```java
<T extends OAuth2AuthorizedClient> T loadAuthorizedClient(
    String clientRegistrationId,
    String principalName
);

void saveAuthorizedClient(
    OAuth2AuthorizedClient authorizedClient,
    Authentication principal
);

void removeAuthorizedClient(
    String clientRegistrationId,
    String principalName
);
```

Đây là chữ ký khái niệm của các phương thức chính; hãy dùng Javadoc của phiên bản thư viện để kiểm tra annotation nullable và generic cụ thể.

Khác với `OAuth2AuthorizedClientRepository` trong web, service này **không yêu cầu HTTP request/response** để truy cập authorized client.

### 10.2. `InMemoryOAuth2AuthorizedClientService`

Ưu điểm:

- Cấu hình đơn giản.
- Phù hợp học tập, thử nghiệm hoặc service một instance có thể xin token mới khi restart.
- Không đòi database hoặc migration.

Giới hạn:

- Token mất khi process restart.
- Không chia sẻ state giữa nhiều instance.
- Không phù hợp nếu phải bảo toàn refresh token của user qua restart.
- Một số tình huống không có cơ chế coordination giữa các worker.

Với `client_credentials`, việc mất token khi restart có thể chấp nhận vì job có thể xin lại bằng client credentials. Nhưng nếu hệ thống có rate limit chặt hoặc nhiều instance, vẫn phải cân nhắc chiến lược lưu trữ và retry.

### 10.3. `JdbcOAuth2AuthorizedClientService`

Spring Security cung cấp một lựa chọn JDBC để lưu authorized client vào database. Ví dụ wiring **thay thế** in-memory:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Bean
OAuth2AuthorizedClientService authorizedClientService(
        JdbcTemplate jdbcTemplate,
        ClientRegistrationRepository registrations) {

    return new JdbcOAuth2AuthorizedClientService(
        jdbcTemplate,
        registrations
    );
}
```

Để chạy, cần dependency Spring JDBC, `DataSource` và **schema bảng authorized client** tương thích với phiên bản Spring Security sử dụng. Không chỉ thêm bean là database tự có bảng.

Một số điểm vận hành:

- Chạy schema migration theo tài liệu Spring Security tương ứng.
- Hạn chế tài khoản database truy cập bảng token.
- Bảo vệ dữ liệu lưu, sao lưu và quy trình restore.
- Xem xét encryption at rest và, nếu có yêu cầu cao, mã hóa token ở tầng ứng dụng.
- Dọn authorized client đã không còn cần thiết theo retention policy.
- Thiết kế refresh token rotation và concurrency khi nhiều instance cùng cập nhật.

**JDBC không tự giải quyết mọi race condition refresh.** Nó chia sẻ dữ liệu bền vững, nhưng nếu hai process cùng lấy refresh token cũ rồi gửi tới Token Endpoint, vẫn có thể phát sinh tranh chấp.

### 10.4. Service và repository có thể liên quan với nhau

Trong một ứng dụng web, `OAuth2AuthorizedClientRepository` có thể được triển khai theo cách dựa trên `OAuth2AuthorizedClientService` cho principal đã xác thực. Tuy nhiên, không nên mặc định mọi cấu hình web đều lưu authorized client của user vào đúng service mà background manager đang dùng.

Khi muốn job làm việc với **user-delegated authorized client** được cấp từ browser login, cần xác minh kiến trúc lưu trữ cụ thể:

- OAuth2 Login đã lưu authorized client vào đâu?
- Principal name dùng lúc browser login là gì?
- Service manager sẽ tra cùng `registrationId` và principal name đó chứ?
- Refresh token có được cấp và lưu bền vững đúng chính sách không?
- Token có được phép sử dụng offline sau khi user rời ứng dụng không?

Việc không tìm thấy authorized client sau khi user login thường là vấn đề **khác kho lưu hoặc khác principal key**, không có nghĩa Authorization Server tự mất token.

## 11. Sự khác biệt giữa làm mới token bằng refresh token và xin token mới

Hai trường hợp thường bị gộp nhầm:

### 11.1. `client_credentials`: dùng Client authentication xin token khác

```text
Job cần token
  -> manager / ClientCredentialsProvider
  -> POST /token grant_type=client_credentials
  -> access token mới
```

Không cần user login, không cần `refresh_token`. Authorization Server thường không trả refresh token trong Client Credentials Grant.

### 11.2. `authorization_code` + `refresh_token`: tiếp tục quyền user đã cấp

```text
Người dùng đã login và consent
  -> authorized client đã được lưu kèm refresh token (nếu provider cấp)
  -> job dùng đúng user principal
  -> RefreshTokenProvider
  -> POST /token grant_type=refresh_token
  -> access token mới
```

Với flow này, background manager chỉ có thể **tái cấp quyền dựa trên trạng thái đã tồn tại**. Nó không tự mở browser để khởi tạo authorization code flow.

### 11.3. Một manager có thể hỗ trợ nhiều grant

Nếu hạ tầng cần dùng cả client credentials và refresh token:

```java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .refreshToken()
        .build();

manager.setAuthorizedClientProvider(provider);
```

Nhưng mỗi `ClientRegistration` vẫn có grant type và chính sách riêng. Đừng nghĩ thêm `.refreshToken()` nghĩa là Client Credentials Grant tự nhận refresh token.

Việc trộn user-granted tokens với service tokens trong một manager/kho lưu cần **kiểm soát tenant, principal và quyền truy cập** rất chặt để tránh token của user A bị dùng cho job của user B.

## 12. Tình huống user-delegated background processing

Giả sử người dùng kết nối một ứng dụng quản lý lịch và chấp thuận cho backend đồng bộ lịch theo định kỳ. Quy trình tổng quát:

1. Người dùng chủ động kết nối qua browser bằng Authorization Code Flow.
2. Authorization Server cấp access token và, nếu được phép, refresh token.
3. Ứng dụng lưu `OAuth2AuthorizedClient` vào storage an toàn, liên kết với **định danh user nội bộ** và registration phù hợp.
4. Job được lập lịch theo đúng kết nối đã được người dùng đồng ý.
5. Background manager tra authorized client đúng user + registration.
6. Nếu access token gần hết hạn và có refresh token hợp lệ, provider refresh.
7. API được gọi bằng token user có audience/scope phù hợp.
8. Nếu refresh thất bại/revoked, dừng đồng bộ và đưa kết nối sang trạng thái `RECONNECT_REQUIRED`; không tự dùng token của user khác.

### 12.1. Mã minh họa lookup token theo principal đã ủy quyền

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;

public final class CalendarTokenService {

    private final OAuth2AuthorizedClientManager manager;

    public CalendarTokenService(OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    public OAuth2AuthorizedClient requireUserAuthorizedClient(
            String trustedUserPrincipalName) {

        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("calendar-connection")
                .principal(trustedUserPrincipalName)
                .build();

        OAuth2AuthorizedClient client = manager.authorize(request);

        if (client == null) {
            throw new IllegalStateException(
                "No usable calendar authorization for this user"
            );
        }

        return client;
    }
}
```

Đoạn code **chỉ minh họa** cách manager nhận principal, chưa phải một workflow cấp quyền hoàn chỉnh. `trustedUserPrincipalName` phải đến từ record kết nối **đã xác minh ownership** của account hiện tại, không phải query parameter tự do.

Nếu registration có grant `authorization_code` nhưng background manager chỉ có `refreshToken()` provider, một authorized client đã tồn tại và có refresh token mới có cơ hội được refresh. Nếu chưa có authorized client hoặc refresh token, nó không thể tự đưa người dùng tới màn hình consent.

### 12.2. Không nhầm refresh token với phiên đăng nhập

HTTP session OIDC có thể đã hết hạn trong khi người dùng vẫn cho phép offline access. Điều ngược lại cũng có thể xảy ra: session còn nhưng refresh token đã bị thu hồi.

Vì vậy:

- Quyền offline access cần consent và policy riêng.
- Logout ứng dụng không tự mặc định là revoke mọi refresh token.
- Người dùng cần giao diện ngắt kết nối/thu hồi quyền khi sản phẩm hỗ trợ.
- Khi refresh token rotation được bật, token mới phải được lưu thay token cũ theo hợp đồng provider.
- Không đưa refresh token ra frontend hoặc lưu nó trong job arguments/logs.

### 12.3. Vì sao không đưa `authorizationCode()` vào background manager để tự đăng nhập?

Authorization Code Grant là flow cần tương tác với user agent và callback để nhận code. Job không có browser/session nên không thể tự “bật login” chỉ vì provider builder có `authorizationCode()`.

`OAuth2AuthorizedClientProviderBuilder` mô tả **grant được phép xử lý**, không tự tạo một kênh đăng nhập người dùng ngoài request. Cần thiết kế bước connect/reauthorize tương tác riêng và để job chỉ dùng authorized client đã được cấp.

## 13. Xử lý lỗi ở Token Endpoint và trong manager

Manager có thể gặp lỗi trong lúc cấp/làm mới token. Một số lỗi OAuth2 thường thấy:

| Lỗi | Ý nghĩa thường gặp | Hướng xử lý |
|---|---|---|
| `invalid_client` | Client ID/secret hoặc phương thức xác thực Client không đúng | Kiểm tra registration, secret rotation và cấu hình AS |
| `unauthorized_client` | Client không được phép sử dụng grant | Kiểm tra grant được đăng ký ở Authorization Server |
| `unsupported_grant_type` | Token Endpoint không hỗ trợ grant yêu cầu | Kiểm tra `authorization-grant-type` và endpoint |
| `invalid_scope` | Scope không hợp lệ hoặc chưa được cấp | Chỉ xin scope phù hợp hợp đồng API |
| `invalid_grant` | Refresh token/code không hợp lệ, hết hạn, đã dùng hoặc bị thu hồi | Với refresh: bỏ trạng thái không hợp lệ và yêu cầu reauthorization khi cần |
| HTTP 429 | Provider giới hạn tần suất gọi | Backoff phù hợp, giảm số lần xin token, không tạo vòng lặp |
| HTTP 5xx/network timeout | Lỗi tạm thời ở IdP hoặc đường truyền | Retry có giới hạn, quan sát, circuit breaker nếu phù hợp |
| `null` từ `authorize(...)` | Provider không hỗ trợ grant của registration hoặc không có kết quả authorization | Kiểm tra provider builder/registration/context |
| API 401 `invalid_token` | Resource Server không chấp nhận token dùng gọi API | Kiểm tra audience, expiry, revocation và chính sách retry |
| API 403 `insufficient_scope` | Token thiếu quyền API yêu cầu | Xin quyền đúng theo consent/policy, không refresh vô hạn |

### 13.1. Default success/failure handlers của service manager

Theo Javadoc Spring Security, `AuthorizedClientServiceOAuth2AuthorizedClientManager` mặc định:

- Khi authorization thành công, lưu `OAuth2AuthorizedClient` vào `OAuth2AuthorizedClientService`.
- Khi authorization thất bại do **`invalid_grant`**, xóa authorized client đã lưu trước đó khỏi service để tránh tiếp tục dùng trạng thái lỗi.

Có thể thay đổi bằng các hook:

```java
manager.setAuthorizationSuccessHandler(customSuccessHandler);
manager.setAuthorizationFailureHandler(customFailureHandler);
```

Nhưng **không ghi đè handler chỉ để log một dòng rồi bỏ qua hành vi lưu/xóa mặc định**. Nếu có handler riêng, cần chủ động giữ hành vi persistence và cleanup cần thiết. Không nên tùy tiện nuốt `invalid_grant` để manager trả về token không còn đáng tin.

### 13.2. Phân biệt lỗi token và lỗi downstream API

Giả sử manager lấy được token, nhưng API trả 401. Đây là **lỗi ở Resource Server**, xảy ra **sau** khi manager.authorize đã hoàn tất.

Không mặc định rằng failure handler của manager sẽ được gọi khi `RestClient` thấy API 401, vì lỗi đó không nhất thiết đi qua manager. Nếu dùng HTTP client có tích hợp OAuth2 interceptor, có thể có cơ chế chuyển tiếp authorization failure tới handler theo cấu hình. Nếu tự ghép Bearer header như ví dụ `RestClient`, cần tự xác định chiến lược xử lý 401/403 tại HTTP client.

Đặc biệt:

- Với 401 `invalid_token`, có thể cần bỏ token cache/reauthorize hoặc xác định audience sai.
- Với 403 `insufficient_scope`, xin lại token bằng cùng registration và scope cũ thường không giải quyết vấn đề.
- Với 429/5xx, xóa token không liên quan nguyên nhân; retry token vô hạn có thể làm hệ thống tệ hơn.

### 13.3. Cách xử lý exception trong job

Một job production nên phân loại lỗi để không để scheduler crash vô nghĩa:

```java
try {
    OAuth2AuthorizedClient client = manager.authorize(authorizeRequest);

    if (client == null) {
        // Lỗi cấu hình/grant không được hỗ trợ.
        return;
    }

    // Gọi API theo quyền đã được cấp.
} catch (org.springframework.security.oauth2.core.OAuth2AuthorizationException ex) {
    // Chỉ log mã lỗi/registrationId đã lọc.
    String errorCode = ex.getError().getErrorCode();

    // Không log raw token request, Authorization header hoặc credentials.
    // Phân loại invalid_client, invalid_scope, invalid_grant, ...
}
```

Đây là một mảnh logic minh họa, không phải chính sách retry hoàn chỉnh. Trong thực tế, nên có alert và cơ chế xử lý thất bại tương ứng với business impact: một lần đồng bộ báo cáo thất bại có thể retry an toàn; một hành động thanh toán có thể cần idempotency key và thiết kế chặt hơn.

## 14. Token caching và expiration

### 14.1. Vì sao nên dùng manager thay vì luôn POST Token Endpoint?

Nếu job 10 giây chạy một lần nhưng token sống 30 phút, việc luôn gọi Token Endpoint sẽ tạo hàng trăm request không cần thiết.

Manager + authorized client service có thể:

- Giữ token đã cấp cho cùng registration/principal.
- Tái sử dụng token khi provider xác định nó còn phù hợp.
- Tái cấp token theo cơ chế grant khi cần.
- Cập nhật token mới vào service sau authorization thành công.

Điều này giảm tải Token Endpoint, giảm rate limit và tập trung chính sách token.

### 14.2. Clock skew và token hết hạn

`OAuth2AccessToken` trong Spring Security chứa `issuedAt` và `expiresAt`. Tùy provider/configuration, việc đánh giá hết hạn có thể có khoảng đệm clock skew.

Một tình huống:

```text
expiresAt = 10:00:00 UTC
API request bắt đầu = 09:59:59 UTC
Request tới Resource Server = 10:00:01 UTC
```

Token có thể bị API từ chối ở thời điểm đến. Vì vậy provider quản lý token thường refresh/tái cấp sớm hơn hạn đúng một khoảng dung sai được cấu hình; không nên tự gửi token sát hạn chỉ vì `now < expiresAt` trên một node.

Không có **một giá trị clock skew chung duy nhất cho mọi phiên bản/flow**. Đọc API/tài liệu của provider tương ứng và đồng bộ đồng hồ host/VM/container bằng NTP hoặc dịch vụ tương đương. Không tăng skew quá lớn để che lỗi thời gian hệ thống.

### 14.3. Đừng lưu access token vào static field

```java
// Sai hướng: token sẽ lỗi khi hết hạn/thu hồi.
private static String sharedAccessToken;
```

Cách đó bỏ qua vòng đời theo registration/principal, không giữ metadata expiry và khó cập nhật giữa nhiều process. Dùng authorized client service + manager để quản lý trạng thái, không tự tạo một cache String chung.

## 15. Multi-instance, nhiều job và đồng thời

Một service chạy trên ba Kubernetes pods có thể cùng kích hoạt scheduler theo cùng cron. Nếu ba pod sử dụng `InMemoryOAuth2AuthorizedClientService` riêng, mỗi pod có token riêng và có thể cùng xin token khi hết hạn.

Điều này không nhất thiết sai với Client Credentials Grant, nhưng cần xem:

- Authorization Server rate limit cho Token Endpoint.
- Số token đồng thời được phép.
- Job có được chạy nhiều bản sao hay phải chỉ có một leader.
- Chi phí gọi API/trùng công việc.
- Chính sách token revocation/rotation.
- Môi trường secret rotation, các instance có nhận credential mới nhất hay không.

### 15.1. Khi dùng service lưu chung

Một `JdbcOAuth2AuthorizedClientService` có thể cung cấp authorized client chung cho nhiều instance. Tuy nhiên, nó không tự là **distributed lock** hay transaction điều phối mọi lần refresh.

Ví dụ race:

```text
Pod A đọc token hết hạn
Pod B đọc cùng token hết hạn
Pod A xin token mới AT-2
Pod B đồng thời xin token mới AT-3
Pod A lưu AT-2
Pod B lưu AT-3
```

Với Client Credentials Grant, cả hai access token có thể hợp lệ hoặc một token có thể bị vô hiệu hóa tùy provider. Với **refresh token rotation**, tình huống còn nghiêm trọng hơn vì một refresh token cũ có thể chỉ dùng được một lần.

Các hướng thiết kế tùy yêu cầu:

- Chấp nhận token riêng theo instance khi `client_credentials` và rate limit cho phép.
- Dùng job leader election/single scheduler instance để tránh chạy lặp.
- Dùng cơ chế lock hoặc distributed coordination khi refresh token phải được xoay vòng an toàn.
- Lưu token mới nhất có kiểm soát version/optimistic locking nếu kho lưu/logic hỗ trợ.
- Xử lý HTTP 401/`invalid_grant` theo chính sách thay vì retry vô hạn.
- Chỉ truy xuất token được cấp cho đúng tenant/user/registration.

Không khẳng định “dùng JDBC là token sẽ chỉ được refresh đúng một lần trên toàn cluster” nếu chưa có lớp đồng bộ riêng.

### 15.2. Multi-tenant

Nếu mỗi tenant có Client ID/secret/scope/issuer riêng, nên có registration hoặc cách chọn credential được kiểm soát cho mỗi tenant. Principal key cũng cần được thiết kế để không làm hai tenant dùng chung authorized client ngoài ý muốn.

Ví dụ:

```text
Tenant A -> registration reporting-a -> principal service:reporting-a
Tenant B -> registration reporting-b -> principal service:reporting-b
```

Không lấy tenant ID trực tiếp từ message chưa tin cậy để chọn một registration có đặc quyền cao. Worker phải xác minh tenant/resource ownership và chỉ gọi API trong trust boundary hợp lệ.

## 16. Bảo mật secret, access token và refresh token

### 16.1. Bảo vệ client credentials

`client_credentials` thường được dùng bởi confidential client. `client_secret` hoặc khóa riêng của Client là credential quan trọng:

- Lưu trong secret manager hoặc cấu hình runtime an toàn.
- Không hard-code trong Git, Docker image hoặc log.
- Giới hạn quyền đọc secret trong pod/service account.
- Lập kế hoạch secret rotation và cập nhật các instance.
- Chỉ sử dụng phương thức Client authentication mà Authorization Server cho phép.
- Ưu tiên cơ chế xác thực Client mạnh hơn như `private_key_jwt` hoặc mTLS khi yêu cầu bảo mật và provider hỗ trợ.

Không đưa `client_secret` lên Authorization URL, query string hoặc downstream API.

### 16.2. Bảo vệ access/refresh token

- Access token Bearer thường là credential có thể sử dụng trực tiếp; không in `getTokenValue()`.
- Refresh token, khi có, phải được bảo vệ nghiêm ngặt vì có thể lấy access token mới.
- Chỉ gửi access token tới API đúng audience/host.
- Không trả token cho frontend nếu backend có thể gọi API thay.
- Không đưa token vào message queue payload hoặc job arguments nếu không cần thiết.
- Kho lưu authorized client phải có access control, encryption/retention theo yêu cầu.
- Với per-user tokens, kiểm soát principal ownership: background worker không được tra token người khác tùy ý.

### 16.3. Không nhầm client credentials với user session

Token client credentials đại diện cho quyền ứng dụng; nó **không chứng minh** có một nhân viên cụ thể đã đăng nhập. Nếu API yêu cầu audit theo người dùng, đừng giả tên user vào principal manager để cố tạo bằng chứng.

Đối với tác vụ thay đổi dữ liệu nhạy cảm, Resource Server có thể cần mô hình authorization riêng theo client, service identity, token exchange hoặc cơ chế ủy quyền phù hợp. Không dùng quyền service account rộng để lách yêu cầu consent của người dùng.

## 17. Quan sát và log an toàn

Các chỉ số hữu ích:

| Chỉ số/Log đã lọc | Mục đích |
|---|---|
| `registrationId` | Biết Client nào đang được dùng |
| Principal category (service/user) | Biết loại credential, không cần ghi danh tính nhạy cảm |
| Lần xin token thành công/thất bại | Đo độ ổn định Token Endpoint |
| Thời gian lấy token | Quan sát latency |
| Số lần dùng lại token | Kiểm tra có xin token lặp bất thường không |
| `expiresAt` hoặc thời gian còn lại đã làm tròn | Giám sát vòng đời token |
| HTTP status của Resource Server | Phân biệt 401/403/429/5xx |
| Mã lỗi OAuth2 như `invalid_client` | Chẩn đoán đăng ký/credential |
| Count retry/backoff | Phát hiện vòng lặp cấp token |

Không ghi:

```text
client_secret
access_token
refresh_token
Authorization: Bearer <token>
Authorization: Basic <client-credentials>
token request body chứa secret
JWT payload chứa PII
```

Có thể log:

```text
oauth2_client_registration=reporting-job
authorization_result=success
token_reused=true
api_status=200
```

Dữ liệu log ở trên chỉ minh họa. Nếu theo dõi user-specific authorized clients, cần bảo vệ tên người dùng, subject OIDC và tenant identifiers theo chính sách riêng tư.

### 17.1. Vì sao metrics nên tách token grant và API call?

Ví dụ job thất bại vì Reporting API trả `503` nhưng token đã được cấp hợp lệ. Nếu metrics chỉ có “OAuth2 job failed”, nhóm vận hành có thể thay Client secret vô ích.

Phân lớp:

```text
registration lookup
  -> token acquisition/reauthorization
  -> HTTP API call
  -> business processing
```

giúp xác định lỗi thuộc Client configuration, Authorization Server, Resource Server hay nghiệp vụ.

## 18. Mẫu thiết kế để code dễ bảo trì

Một dự án thường nên tránh gọi `manager.authorize(...)` rải khắp controller/service. Có thể tạo một lớp chuyên trách **Access Token Provider** dựa trên manager, có chính sách:

- Chỉ cho phép những `registrationId` được phê duyệt.
- Đặt principal name ổn định, rõ ngữ cảnh.
- Xử lý `null` và exception thống nhất.
- Không log giá trị token.
- Phân biệt user-delegated token với service token.
- Không tự mở rộng quyền hoặc thêm scope vào token.

Ví dụ abstraction:

```java
public interface ServiceAccessTokenProvider {
    String requireTokenForReporting();
}
```

Triển khai:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Component;

@Component
public class DefaultServiceAccessTokenProvider
        implements ServiceAccessTokenProvider {

    private final OAuth2AuthorizedClientManager manager;

    public DefaultServiceAccessTokenProvider(
            OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    @Override
    public String requireTokenForReporting() {
        var request = OAuth2AuthorizeRequest
            .withClientRegistrationId("reporting-job")
            .principal("service:reporting-job")
            .build();

        OAuth2AuthorizedClient client = manager.authorize(request);

        if (client == null) {
            throw new IllegalStateException(
                "Reporting OAuth2 client could not be authorized"
            );
        }

        return client.getAccessToken().getTokenValue();
    }
}
```

Lớp này chỉ dùng bên trong backend, không phải endpoint trả token cho frontend. Nếu có nhiều manager, khai báo `@Qualifier("serviceAuthorizedClientManager")` để tránh Spring inject nhầm web manager.

### 18.1. Khi nào nên dùng HTTP interceptor thay vì tự set Bearer header?

Spring Security có cơ chế tích hợp OAuth2 Client với các HTTP client hiện đại, chẳng hạn `OAuth2ClientHttpRequestInterceptor` cho `RestClient` ở những phiên bản hỗ trợ. Interceptor có thể lấy authorized client qua manager và gắn Bearer token tự động.

Ưu điểm:

- Không tự ghép header tại mọi nơi.
- Có điểm cấu hình thống nhất cho registration/principal.
- Có thể liên kết cơ chế xử lý authorization failure phù hợp.

Nhưng cần chú ý:

- Version Spring Security/Framework phải hỗ trợ interceptor được dùng.
- Chọn đúng manager (service manager cho background).
- Cấu hình principal resolver dành cho job, không phụ thuộc `SecurityContextHolder` của một HTTP user bất kỳ.
- Không áp interceptor ra HTTP client gọi host ngoài allowlist, tránh gửi Bearer token nhầm nơi.
- Nếu dùng retry/redirect tự động của HTTP client, phải kiểm soát việc chuyển Authorization header sang host khác.

Với một ví dụ học tập đơn giản, `headers.setBearerAuth(token)` thể hiện rõ token đi đâu. Với dự án lớn, interceptor thường dễ bảo trì hơn nếu được cấu hình đúng.

## 19. Các trường hợp lỗi do chọn nhầm ngữ cảnh

### 19.1. Dùng request-based manager trong worker

```text
@Scheduled
  -> DefaultOAuth2AuthorizedClientManager.authorize(...)
  -> không có Servlet request
  -> lỗi request context
```

**Cách xử lý:** dùng `AuthorizedClientServiceOAuth2AuthorizedClientManager` và `OAuth2AuthorizedClientService`. Không tạo request giả nếu công việc không cần phiên trình duyệt.

### 19.2. Dùng `@AuthenticationPrincipal` trong job

`@AuthenticationPrincipal` thường dùng trong controller/Servlet request sau khi Spring Security đã xác thực người dùng. Background job không có principal browser mặc định.

**Cách xử lý:** với `client_credentials`, chọn principal service ổn định. Với token theo user, lấy principal name từ record authorized connection đáng tin đã được lưu, sau khi kiểm tra quyền.

### 19.3. Dùng principal UUID mới mỗi lần job chạy

`OAuth2AuthorizedClientService` tìm authorized client theo principal name. Nếu tên thay đổi liên tục, manager có thể tạo nhiều authorized clients và xin token nhiều hơn cần thiết.

**Cách xử lý:** chọn một principal ổn định theo service/registration/tenant boundary.

### 19.4. Thêm `refreshToken()` rồi mong có refresh token

Authorization Server quyết định có cấp refresh token hay không. `client_credentials` thường dùng lại chính credential để xin token mới; thêm provider refresh token không làm thay đổi response của Token Endpoint.

**Cách xử lý:** dùng grant đúng mục tiêu và hiểu vòng đời access token/refresh token của provider.

### 19.5. Không tìm thấy authorized client sau OIDC Login

Nếu web login lưu ở request/session repository nhưng background manager tra trong một service khác, hoặc principal name không trùng, job sẽ không thấy authorized client.

**Cách xử lý:** thiết kế kho lưu chung phù hợp cho flow được ủy quyền, xác định tên principal và việc cấp offline access. Không tự copy raw refresh token sang bảng nghiệp vụ tùy tiện.

### 19.6. API 403 thì liên tục xin access token mới

`403 insufficient_scope` thường do thiếu quyền, không phải token hết hạn.

**Cách xử lý:** xem scope/audience/authorization, cập nhật Client permission hoặc consent theo provider. Retry token không giới hạn chỉ gây tải cao.

### 19.7. Chạy nhiều pod cùng sử dụng refresh token rotating

Hai pod lấy một refresh token và cùng gửi refresh request. Một request có thể làm token cũ mất hiệu lực trước khi request còn lại hoàn tất.

**Cách xử lý:** có cơ chế coordination, cập nhật refresh token mới nhất và xử lý conflict; không xem lưu JDBC là distributed lock.

## 20. Bảng chẩn đoán nhanh

| Biểu hiện | Nơi nên kiểm tra | Hướng xử lý |
|---|---|---|
| `No thread-bound request` | Manager implementation | Đổi sang service-based manager cho worker |
| `authorize(...)` trả `null` | Provider builder, grant của registration | Thêm provider thích hợp hoặc xác định flow cần interaction |
| `invalid_client` | Client ID/secret/auth method | Kiểm tra credentials và Token Endpoint |
| `unsupported_grant_type` | `authorization-grant-type`, AS policy | Dùng grant được cho phép |
| `invalid_scope` | Scope trong registration | Chỉ xin quyền đã được cấp |
| Job lấy token mới mỗi lần chạy | Principal key thay đổi/kho không lưu/token TTL | Kiểm tra `(registrationId, principalName)` |
| Job sau restart không còn user refresh token | In-memory service | Dùng storage bền vững và onboarding/consent đúng |
| Job không thấy token user đã login | Web repository khác service hoặc principal sai | Kiểm tra cơ chế persistence và principal mapping |
| Token còn hạn nhưng API 401 | Audience, revocation, đồng hồ, host/API | Kiểm tra Resource Server và token target |
| API 403 | Scope/role/permission | Không tự refresh vô hạn |
| Token Endpoint bị gọi dồn dập | Nhiều instance, expiry gần nhau, principal không ổn định | Theo dõi caching, coordination/backoff |
| Refresh trả `invalid_grant` | Refresh token bị revoke/expired/rotated | Loại trạng thái cũ và yêu cầu kết nối lại |
| Token response bị ghi vào log | Logging/observability quá rộng | Redact token, giảm verbosity, xử lý lộ thông tin |
| Không có bean `OAuth2AuthorizedClientService` | Thiếu OAuth2 Client configuration hoặc auto-config không phù hợp | Tạo service bean rõ ràng |
| Có hai bean `OAuth2AuthorizedClientManager` | Dependency injection không rõ manager nào | Dùng `@Qualifier` |

## 21. Bài tập thực hành

### Bài tập 1: Chọn manager

Một ứng dụng MVC có controller cho người dùng đăng nhập và một `@Scheduled` chạy hằng giờ để gọi API hệ thống. Nên dùng manager nào cho scheduled job?

**Gợi ý đáp án:** `AuthorizedClientServiceOAuth2AuthorizedClientManager`, vì job không có `HttpServletRequest`. Controller chạy trong Servlet request có thể dùng `DefaultOAuth2AuthorizedClientManager` khi phù hợp.

### Bài tập 2: Chọn grant

Một service không đại diện cho người dùng, chỉ cần token để đọc `reports.read` từ API.

**Gợi ý đáp án:** `client_credentials` nếu Authorization Server cho phép, với ClientRegistration phù hợp và service-based manager dùng provider `.clientCredentials()`.

### Bài tập 3: Principal trong background

Developer gọi:

```java
OAuth2AuthorizeRequest.withClientRegistrationId("reporting-job")
    .principal(UUID.randomUUID().toString())
    .build();
```

Mỗi lần scheduler chạy lại tạo principal khác. Có vấn đề gì?

**Gợi ý đáp án:** token được lưu theo registration + principal, nên không tái sử dụng cùng authorized client ổn định; có thể gây xin token và record dư. Với job đại diện cho cùng một Client, dùng principal service ổn định.

### Bài tập 4: OAuth2 Login của user và job nền

Người dùng login `company-login` qua browser. Job có manager chỉ hỗ trợ `.clientCredentials()` nhưng muốn gọi API theo token của người dùng.

**Gợi ý đáp án:** đó là hai flow khác nhau. Muốn job chạy theo quyền user đã cấp, cần authorized client của user được lưu an toàn và có khả năng refresh/offline access khi provider cho phép; principal phải khớp và manager provider phải xử lý refresh token. Không dùng Client Credentials Grant để giả quyền người dùng.

### Bài tập 5: Lưu trữ sau restart

Ứng dụng dùng `InMemoryOAuth2AuthorizedClientService`. Sau restart, job `client_credentials` vẫn chạy được nhưng phải xin token mới; còn job user-delegated bị mất authorized client.

**Gợi ý đáp án:** điều này phù hợp với in-memory storage. Client Credentials có thể xin lại bằng credential của ứng dụng; với user-delegated access cần thiết kế storage bền vững, consent và token lifecycle.

### Bài tập 6: Resource Server trả 403

Job có access token hợp lệ, nhưng API báo `insufficient_scope`. Có nên xóa authorized client và retry mãi?

**Gợi ý đáp án:** không. Cần kiểm tra scope, audience và permission được Authorization Server/Resource Server cấp. Refresh với cùng quyền thường không giải quyết thiếu scope.

### Bài tập 7: Client Credentials và refresh token

Token response:

```json
{
  "access_token": "EXAMPLE_ACCESS_TOKEN",
  "token_type": "Bearer",
  "expires_in": 1800,
  "scope": "reports.read"
}
```

Không có `refresh_token`. Có phải provider sai không?

**Gợi ý đáp án:** không. Với `client_credentials`, Authorization Server thường không cấp refresh token. Khi cần token khác, Client dùng credentials để xin lại qua Token Endpoint.

### Bài tập 8: Hai instance cùng chạy job

Hai pod dùng một token service lưu JDBC. Đúng 10:00 token hết hạn, cả hai cùng xin token mới. Dùng JDBC đã đảm bảo chỉ có một lần token request chưa?

**Gợi ý đáp án:** chưa. Kho lưu chung không tự thay thế distributed coordination/lock. Tùy nguy cơ, cần chấp nhận cạnh tranh có kiểm soát hoặc thiết kế leader/locking; với refresh token rotation càng phải chú ý.

### Bài tập 9: Xử lý `authorize(...) == null`

Một job viết:

```java
String token = manager.authorize(request)
    .getAccessToken()
    .getTokenValue();
```

Cần thay đổi gì?

**Gợi ý đáp án:** tách bước nhận `OAuth2AuthorizedClient`, kiểm tra `null` và phân loại lỗi cấu hình/grant; xử lý exceptions riêng. Không coi `authorize` luôn thành công hoặc luôn cấp token mới.

## 22. Checklist thiết kế cho ứng dụng production

Trước khi đưa background OAuth2 client vào vận hành, cần trả lời được:

- [ ] Tác vụ chạy **ngoài HTTP request** đã dùng service-based manager chưa?
- [ ] Mỗi registration dùng grant thật sự được Authorization Server cho phép?
- [ ] Với service-to-service, Client Credentials Grant có scope/audience tối thiểu?
- [ ] `principalName` của job ổn định và không trộn lẫn user/tenant?
- [ ] `OAuth2AuthorizedClientService` được chọn phù hợp với yêu cầu restart/scale out?
- [ ] Access/refresh token và Client secret được bảo vệ, không log?
- [ ] `authorize(...)` có xử lý `null` và exception?
- [ ] Có phân biệt lỗi Token Endpoint với 401/403 của API?
- [ ] Retry/backoff và rate limiting không tạo vòng lặp xin token vô hạn?
- [ ] Tác vụ nhiều instance có chiến lược tránh trùng việc/refresh race?
- [ ] Với user-delegated job, đã có consent, authorized client đúng user và reauthorization policy?
- [ ] Có cách ngắt kết nối/thu hồi quyền và invalidation trạng thái khi cần?
- [ ] Có metrics phân loại authorization, downstream API và nghiệp vụ?
- [ ] Các HTTP client chỉ gửi Bearer token tới host/resource tin cậy?
- [ ] Có chính sách xử lý secret rotation, token revocation và clock skew?

Danh sách trên phục vụ lựa chọn thiết kế; không thay thế việc kiểm tra cấu hình thực tế của Authorization Server, Resource Server và phiên bản thư viện.

## 23. Tài liệu tham khảo chính thức

1. [Spring Security Reference — OAuth2 Client Core Interfaces and Classes](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html): `OAuth2AuthorizedClientManager`, service manager, các provider và ví dụ `client_credentials`.
2. [Spring Security API — AuthorizedClientServiceOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html): ngữ cảnh ngoài Servlet request, persistence và xử lý `invalid_grant`.
3. [Spring Security API — DefaultOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizedClientManager.html): manager cho `HttpServletRequest` và `OAuth2AuthorizedClientRepository`.
4. [Spring Security API — OAuth2AuthorizeRequest.Builder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizeRequest.Builder.html): `withClientRegistrationId` và `principal(String)` / `principal(Authentication)`.
5. [Spring Security API — OAuth2AuthorizedClientService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientService.html): `loadAuthorizedClient`, `saveAuthorizedClient`, `removeAuthorizedClient`.
6. [Spring Security API — OAuth2AuthorizedClient](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClient.html): ClientRegistration, access token và refresh token.
7. [Spring Security API — OAuth2AuthorizedClientProviderBuilder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientProviderBuilder.html): cách chọn `clientCredentials`, `refreshToken` và grant providers.
8. [Spring Security Reference — Authorized Client Features](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html): tích hợp OAuth2 Client với HTTP client và chính sách principal.
9. [RFC 6749 — OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749): Client Credentials Grant, Refresh Token Grant và mô hình token response.
10. [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): thực hành bảo mật token, Client và grant.

## 24. Tổng kết

**`AuthorizedClientServiceOAuth2AuthorizedClientManager` là manager dành cho việc sử dụng OAuth2 Client ngoài `HttpServletRequest`**, như scheduled task, queue consumer hoặc service-to-service background job. Nó kết hợp **`ClientRegistrationRepository`**, **`OAuth2AuthorizedClientService`** và **`OAuth2AuthorizedClientProvider`** để tìm, cấp, lưu và tái cấp authorized client theo grant được hỗ trợ.

Đối với job độc lập với người dùng, lựa chọn thường đúng là **`client_credentials`**, một principal service name ổn định và cơ chế lưu token phù hợp. Đối với job chạy theo quyền user, chỉ được dùng authorized client đã được người dùng ủy quyền, đúng principal và chính sách refresh/offline access; một String principal không phải phép mạo danh user hay cách tự khởi động OIDC Login.

Khi triển khai, hãy phân biệt rõ **manager cho web request** và **manager cho background**, lưu token đúng chỗ, xử lý `authorize(...) == null`, giữ grant/scope theo nguyên tắc tối thiểu và tránh lộ Client secret hay refresh token. Đó là nền tảng để các tác vụ nền sử dụng OAuth2 an toàn, tái sử dụng được token và vận hành ổn định khi hệ thống mở rộng.
