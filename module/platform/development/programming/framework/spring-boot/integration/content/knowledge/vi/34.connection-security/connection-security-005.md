# Basic authentication, API key và OAuth2 Client Credentials

## Mục tiêu và bối cảnh

Trong module **SPRING_BOOT_INTEGRATION**, Spring Boot tổ chức các luồng tích hợp qua HTTP client, cơ sở dữ liệu, cache, message broker và các adapter của Spring Integration. Khi Order Service gọi Inventory API, Pricing API hoặc một ERP, luồng xử lý không chỉ cần đúng JSON/XML: nó còn phải **xác thực danh tính của service gọi**, kiểm tra quyền, bảo vệ credential và phản ứng đúng khi kết nối thất bại.

Ba phương án xác thực HTTP service-to-service phổ biến:

- **HTTP Basic Authentication:** gửi cặp username/password trong HTTP `Authorization` header.
- **API key:** gửi một khóa theo hợp đồng của nhà cung cấp, thường trong HTTP header riêng.
- **OAuth2 Client Credentials:** dùng client identity để xin **access token có thời hạn** từ Authorization Server, rồi gửi token tới Resource Server.

Bài thuộc chương **Bảo mật kết nối**, đề mục **Basic authentication, API key và OAuth2 Client Credentials**. Bài tập trung cách dùng với `RestClient`, `WebClient` và HTTP Interfaces trong Spring Boot, đồng thời kết nối bảo mật với transaction, retry, idempotency, kiểm thử và observability.

Sau bài này, bạn có thể:

1. Phân biệt ba cơ chế và chọn theo hợp đồng của đối tác.
2. Cấu hình Basic và API key cho một outbound HTTP client, tránh rò qua client khác.
3. Thiết lập OAuth2 client registration, `client_credentials`, `scope` và `token-uri`.
4. Dùng `OAuth2AuthorizedClientManager` phù hợp với Quartz jobs, broker consumers và outbox workers.
5. Tự động gửi Bearer token bằng Spring Security hoặc một interceptor được giới hạn phạm vi.
6. Hiểu cách token được lưu/tái sử dụng, hết hạn, cấp lại và xoay vòng secrets.
7. Phân biệt lỗi 401, 403, 429, TLS, token endpoint và business rejection.
8. Thiết kế kiểm thử nhiều lớp và giám sát mà không để lộ credentials.

> **Nguyên tắc:** Xác thực thành công không đồng nghĩa có quyền trên mọi tài nguyên; kết nối đã bảo vệ bằng HTTPS và nhận HTTP 200 cũng không tự bảo đảm giao dịch ở downstream đã commit đúng một lần.

## 1. Xác thực nằm ở lớp nào của tích hợp?

~~~mermaid
flowchart LR
    O["Order Service"] --> B["HTTP Basic"]
    O --> K["API key"]
    O --> T["OAuth2 client_credentials"]
    B --> R["Partner Resource API"]
    K --> R
    T --> AS["Authorization Server"]
    AS -->|"Access token"| O
    O -->|"Bearer token"| R
    R --> P["Validate identity, scope, resource policy"]
~~~

Một tích hợp an toàn có nhiều lớp:

| Lớp | Ví dụ | Trách nhiệm |
| --- | --- | --- |
| Kênh truyền | HTTPS, TLS, mTLS | Mã hóa và xác minh peer theo certificate |
| HTTP authentication | Basic, API key, Bearer token | Nhận diện client |
| Application authorization | Scope, role, tenant, resource ownership | Quyết định operation được phép |
| Hợp đồng dữ liệu | JSON Schema, XML/XSD, DTO validation | Ngăn dữ liệu sai |
| Tính nhất quán | SQL transaction, outbox/inbox, idempotency | Bảo vệ business side effect |
| Vận hành | Logging, metrics, alert, key rotation | Phát hiện và khôi phục sự cố |

**Không nhầm mTLS với ba cơ chế trên:** mTLS chứng minh peer sở hữu private key/certificate ở tầng TLS. Basic/API key/OAuth2 là cơ chế application-level. Hệ thống có thể yêu cầu **mTLS cùng OAuth2** nếu threat model cần.

### 1.1. Bảng so sánh

| Tiêu chí | Basic | API key | OAuth2 Client Credentials |
| --- | --- | --- | --- |
| HTTP credential | `Authorization: Basic ...` | Header riêng theo vendor | `Authorization: Bearer ...` |
| Secret gốc | Password | API key | Client secret, private key hoặc mTLS credential |
| Có token endpoint? | Không | Không mặc định | Có |
| Credential ở resource API | Username/password dạng Base64 | API key | Access token do AS cấp |
| Expiration | Theo chính sách password | Theo chính sách key | Access token thường ngắn hạn |
| Scope và audience | Theo vendor nếu có | Theo vendor nếu có | Authorization Server/Resource Server có cơ chế chuẩn |
| Rotation | Đổi password | Đổi API key | Đổi client secret và cấp lại access token |
| User identity | Không mặc định | Không mặc định | Thường đại diện ứng dụng, không phải người dùng |
| Lỗi thường thấy | Sai password, realm | Key bị revoke, quota | invalid_client, invalid_scope, invalid_token |

API key không có một wire format bắt buộc chung cho mọi nhà cung cấp. OAuth2 phức tạp hơn nhưng có lợi khi cần cấp quyền theo scopes, phát hành token có thời hạn và tách Authentication Server khỏi Resource Server.

## 2. Chuẩn bị project Spring Boot

Với Spring Boot 3.2+ và Java 17+, `RestClient` là HTTP client đồng bộ thuận tiện. Thêm OAuth2 client starter khi cần OAuth2:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    // Chỉ khi cần OAuth2 Client:
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    // Chỉ khi sử dụng WebClient/reactive:
    implementation 'org.springframework.boot:spring-boot-starter-webflux'

    // Giám sát, nếu cần:
    implementation 'org.springframework.boot:spring-boot-starter-actuator'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Không phải ứng dụng nào cũng cần cả MVC và WebFlux. Với Boot 4/Spring Security 7, tên starter hoặc vị trí package của một số API có thể thay đổi; dùng BOM và kiểm tra dependency/Javadoc thực của dự án.

Spring Boot cấu hình sẵn `RestClient.Builder` và `WebClient.Builder` khi starter phù hợp. Thay vì một client global chứa mọi credentials, tạo **một bean outbound client theo partner**.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class PartnerHttpConfiguration {

    @Bean
    RestClient partnerClient(RestClient.Builder builder) {
        return builder
                .baseUrl("https://partner.example.org")
                .build();
    }
}
~~~

`https://partner.example.org` là địa chỉ minh họa; production đưa vào cấu hình theo môi trường. Một `RestClient.Builder` có state: khi tạo nhiều clients từ cùng builder, cần hiểu cấu hình có thể tiếp tục tích lũy; dùng builder do Boot inject riêng hoặc clone khi phù hợp.

## 3. HTTPS là điều kiện nền tảng

Base64 của Basic không phải encryption; API key và Bearer token cũng là các credentials có thể bị người khác dùng lại nếu bị lộ. Vì vậy:

- Gọi resource API và OAuth2 token endpoint bằng HTTPS.
- Xác minh certificate chain và hostname SAN.
- Không dùng trust-all TrustManager hoặc HostnameVerifier luôn đúng.
- Không đưa secrets vào URL/query params, stack traces, access logs.
- Chặn redirects sang domain không được phê duyệt với Authorization header.
- Tách credentials và truststores của dev/staging/production.
- Đặt network egress allowlist, timeouts, concurrency limits.
- Có quy trình revoke/rotate nếu key bị lộ.

TLS bảo vệ kênh, nhưng server phải kiểm tra credential hợp lệ và quyền của principal. Nếu Inventory API dùng token có `scope=inventory.read`, không nên cho phép gọi `POST /reservations` chỉ vì chữ ký token đúng.

## 4. HTTP Basic Authentication

HTTP Basic dùng header:

~~~http
GET /v1/products/P-100 HTTP/1.1
Host: catalog.example.org
Authorization: Basic <redacted>
~~~

Giá trị phía sau `Basic` là Base64 của username/password theo encoding và quy tắc Basic scheme. **Base64 không che giấu mật khẩu khỏi người đọc header**.

### 4.1. Cấu hình secret

~~~yaml
integrations:
  catalog:
    base-url: ${CATALOG_BASE_URL:https://catalog.example.org}
    username: ${CATALOG_USERNAME}
    password: ${CATALOG_PASSWORD}
~~~

Các biến môi trường phải được cấp bởi secret management. Không commit password thật vào source hoặc YAML.

### 4.2. Gắn Basic vào riêng RestClient

~~~java
// CatalogClientConfiguration.java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class CatalogClientConfiguration {

    @Bean
    RestClient catalogRestClient(
            RestClient.Builder builder,
            @Value("${integrations.catalog.base-url}")
            String baseUrl,
            @Value("${integrations.catalog.username}")
            String username,
            @Value("${integrations.catalog.password}")
            String password) {

        return builder
                .baseUrl(baseUrl)
                .defaultHeaders(headers ->
                        headers.setBasicAuth(username, password))
                .build();
    }
}
~~~

Đây là Basic **preemptive**: header được thêm ngay ở request đầu. Một số HTTP stacks có challenge/response với `401 WWW-Authenticate`, hoặc dùng credential provider của transport. Chọn cách phù hợp đối tác và HTTP client đang sử dụng.

Chỉ dùng bean này để gọi Catalog API. Nếu có nhiều `RestClient` beans, tiêm rõ bằng `@Qualifier("catalogRestClient")`, không cho Payment code vô tình dùng Catalog credentials.

### 4.3. Gọi API

~~~java
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;

@Component
public class CatalogGateway {

    private final RestClient client;

    public CatalogGateway(
            @Qualifier("catalogRestClient") RestClient client) {
        this.client = client;
    }

    public ProductDto find(String sku) {
        return client.get()
                .uri("/v1/products/{sku}", sku)
                .retrieve()
                .body(ProductDto.class);
    }
}
~~~

`ProductDto` là DTO do ứng dụng định nghĩa. Client phải có request timeouts và error mapping phù hợp; dùng `retrieve()` mặc định có thể ném exception trên HTTP 4xx/5xx.

### 4.4. Những giới hạn của Basic

| Tình huống | Kết luận/biện pháp |
| --- | --- |
| 401 sau đổi password | Secret tại workload có thể đã cũ; không retry vô hạn |
| 403 | Client có thể đã xác thực nhưng thiếu quyền |
| Password chứa non-ASCII | Xác nhận charset/challenge policy của server |
| Dùng cùng password cho nhiều API | Tăng blast radius nếu một nơi bị lộ |
| Thay password khi client đang chạy | Bean đã dựng có thể vẫn giữ credential cũ |
| Log HTTP headers để debug | Nguy cơ lộ password dạng Base64 |
| Redirect sang host khác | Phải bảo đảm credentials không bị gửi sang host lạ |

Không dùng tài khoản quản trị hoặc mật khẩu người dùng cuối cho một integration worker nếu có thể cấp service account quyền tối thiểu.

## 5. API key

API key là một credential do provider định nghĩa. Có nhiều dạng:

~~~http
GET /v1/quotes HTTP/1.1
Host: pricing.example.org
X-API-Key: <redacted>
~~~

Hoặc một vendor khác:

~~~http
Authorization: ApiKey <redacted>
~~~

Không có chuẩn duy nhất bắt buộc tên header `X-API-Key` hoặc prefix `ApiKey`. Phải lấy tên header, cách tính signature nếu có, quota, quyền và lịch rotation từ tài liệu/hợp đồng của provider.

### 5.1. Cấu hình API key qua RestClient

~~~yaml
integrations:
  pricing:
    base-url: ${PRICING_BASE_URL:https://pricing.example.org}
    api-key: ${PRICING_API_KEY}
~~~

~~~java
// PricingClientConfiguration.java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class PricingClientConfiguration {

    @Bean
    RestClient pricingRestClient(
            RestClient.Builder builder,
            @Value("${integrations.pricing.base-url}")
            String baseUrl,
            @Value("${integrations.pricing.api-key}")
            String apiKey) {

        return builder
                .baseUrl(baseUrl)
                .defaultHeader("X-API-Key", apiKey)
                .build();
    }
}
~~~

Nếu đối tác dùng header `Authorization: ApiKey ...`, thay dòng `defaultHeader(...)` theo contract. Không gửi **cả hai** dạng header chỉ vì không chắc dạng nào đúng.

### 5.2. Tránh key trong query string

~~~text
https://pricing.example.org/v1/quotes?api_key=SECRET
~~~

Một URL như vậy dễ bị lưu vào reverse proxy logs, client telemetry, history, error reports và cache keys. Ưu tiên API key ở header qua HTTPS. Nếu vendor chỉ hỗ trợ query parameter, phải có redaction và kiểm soát redirects/retention nghiêm ngặt.

### 5.3. API key, rate limit và quyền

Một API key hợp lệ vẫn có thể bị HTTP 429 do vượt quota; đây không nhất thiết là lỗi xác thực. Key cũng có thể bị giới hạn IP, endpoint, environment hoặc tenant. Không coi mọi lỗi 403 là key sai và cũng không tăng retries khiến quota bị vượt nặng hơn.

Các thực hành tốt:

1. Cấp key riêng cho từng ứng dụng/môi trường.
2. Giới hạn endpoints/roles/quota.
3. Không chia sẻ qua broker payload hoặc outbox.
4. Rotate qua cửa sổ dual-active nếu vendor hỗ trợ.
5. Theo dõi key expiry/revocation và fallback theo policy.
6. Không đưa key làm metric label hoặc log field.

## 6. OAuth2 Client Credentials: hai lần trao đổi

OAuth2 Client Credentials Grant phù hợp với confidential client, ví dụ service hoặc job nền gọi API nhân danh **chính ứng dụng**. Nó không có browser redirect và không mặc định chứa danh tính người dùng cuối.

~~~mermaid
sequenceDiagram
    participant O as Order Service
    participant A as Authorization Server
    participant I as Inventory Resource Server
    O->>A: POST /oauth2/token grant_type=client_credentials
    Note over O,A: Client authenticates using client secret/private key/mTLS
    A-->>O: Bearer access token, expires_in, scope
    O->>I: HTTPS Authorization: Bearer access-token
    I->>I: Validate token, audience, scope and business policy
    I-->>O: Protected resource response
~~~

**Phân biệt credentials:**

| Thành phần | Gửi tới đâu? | Dùng để làm gì? |
| --- | --- | --- |
| Client ID | Authorization Server | Nhận diện OAuth2 client |
| Client secret | Authorization Server, qua phương thức đã cấu hình | Chứng minh client identity |
| Access token | Resource Server | Cho phép truy cập resources theo claims/policy |
| Token URI | Authorization Server | Endpoint phát token |
| API base URL | Resource Server | Endpoint nghiệp vụ |
| Scope | Yêu cầu AS cấp quyền | Resource Server kiểm tra scope |
| Audience | Xác định API nhận token | Chống dùng token sai đích |

### 6.1. Token request

Ví dụ đã che credential:

~~~http
POST /oauth2/token HTTP/1.1
Host: auth.example.org
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-credential-redacted>

grant_type=client_credentials&scope=inventory.read%20inventory.reserve
~~~

`Authorization: Basic` ở đây dùng để **xác thực OAuth2 client tại token endpoint** theo `client_secret_basic`, khác với Basic gửi trực tiếp tới Inventory Resource API.

Một AS khác có thể yêu cầu `client_secret_post`, `private_key_jwt` hoặc mTLS client authentication. Không tự gửi client secret vào cả body lẫn Authorization nếu hợp đồng không yêu cầu.

Response ví dụ:

~~~json
{
  "access_token": "<redacted>",
  "token_type": "Bearer",
  "expires_in": 900,
  "scope": "inventory.read inventory.reserve"
}
~~~

Access token có thể là JWT **hoặc opaque token**. Không assume client có thể decode/verify mọi token; Resource Server phải validate theo issuer/signature hoặc introspection, audience, expiry, scope và authorization rules.

### 6.2. Client credentials khác authorization_code

| Đặc tính | client_credentials | authorization_code |
| --- | --- | --- |
| Tài khoản đại diện | Ứng dụng/service | User và ủy quyền của user |
| Cần browser redirect? | Không | Có |
| Quartz/outbox worker | Phù hợp | Không nên phụ thuộc user HTTP session |
| Refresh token | Thường không cấp | Có thể được cấp |
| Xin lại token | Gửi client credentials khi cần | Refresh/authorize lại |
| Tính bảo mật | Service credential và scoped access token | User consent/session/token policy |

Một event tồn trong outbox nhiều giờ không nên mang theo Bearer token của người dùng vừa gọi HTTP: token có thể hết hạn, sai audience và có nguy cơ lộ trong database/broker.

## 7. Spring Boot OAuth2 registration

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-client:
            provider: inventory-idp
            client-id: ${INVENTORY_OAUTH_CLIENT_ID}
            client-secret: ${INVENTORY_OAUTH_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope:
              - inventory.read
              - inventory.reserve
        provider:
          inventory-idp:
            token-uri: ${INVENTORY_TOKEN_URI:https://auth.example.org/oauth2/token}

integrations:
  inventory:
    base-url: ${INVENTORY_API_URL:https://inventory.example.org}
~~~

| Cấu hình | Ý nghĩa |
| --- | --- |
| `registration.inventory-client` | ID của client trong Spring Security |
| `provider: inventory-idp` | Tham chiếu thông tin Authorization Server |
| `client-id` | Danh tính đăng ký với AS |
| `client-secret` | Secret nhạy cảm, không commit vào repository |
| `authorization-grant-type` | Chỉ định `client_credentials` |
| `client-authentication-method` | Cách gửi client credential tới AS |
| `scope` | Quyền yêu cầu, không chắc AS cấp toàn bộ |
| `provider.inventory-idp.token-uri` | Endpoint cấp access token |
| `integrations.inventory.base-url` | Resource API, độc lập token URI |

Với OAuth2 client dependency và registration hợp lệ, Boot cung cấp hạ tầng `ClientRegistrationRepository` và authorized client service tương ứng. **Chỉ khai báo YAML không tự thêm Authorization header vào mọi `RestClient`**: phải nối manager/interceptor/filter đúng.

### 7.1. Không lẫn client registration và principal

`inventory-client` là **client registration ID** để chọn credentials và token endpoint. Một `principal` dùng trong authorized client cache xác định phạm vi lưu token. Background service thường dùng principal ổn định như `order-integration-service`, không dùng `orderId` hoặc random UUID mỗi lần.

Khi nhiều partners cần audience/scope riêng, dùng registration riêng theo partner. Không áp dụng global token cho mọi URL.

## 8. Manager cho service nền, không có user session

Spring Security hỗ trợ `OAuth2AuthorizedClientManager` để xin và quản lý token. Một integration worker chạy Quartz, Kafka listener hoặc outbox relay thường **không có HttpServletRequest**, nên dùng `AuthorizedClientServiceOAuth2AuthorizedClientManager`.

### 8.1. Tạo manager

~~~java
// ServiceOAuth2Configuration.java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration(proxyBeanMethods = false)
public class ServiceOAuth2Configuration {

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
                        registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

Manager có thể lưu/tái sử dụng access token trong `OAuth2AuthorizedClientService` cho cùng registration + principal. Khi hết hạn, client credentials provider xin **token mới** theo chính sách (không mặc định có refresh token).

Không tự cache token string vô thời hạn trong static field. Cần kiểm soát expiry, clock skew, 401 invalid_token và concurrent acquisition.

### 8.2. Provider lấy token

~~~java
// InventoryAccessTokenProvider.java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Component;

@Component
public class InventoryAccessTokenProvider {

    private final OAuth2AuthorizedClientManager manager;

    public InventoryAccessTokenProvider(
            OAuth2AuthorizedClientManager serviceAuthorizedClientManager) {
        this.manager = serviceAuthorizedClientManager;
    }

    public String accessToken() {
        var request = OAuth2AuthorizeRequest
                .withClientRegistrationId("inventory-client")
                .principal("order-integration-service")
                .build();

        OAuth2AuthorizedClient client = manager.authorize(request);

        if (client == null) {
            throw new IllegalStateException(
                    "Không thể authorize inventory-client");
        }

        return client.getAccessToken().getTokenValue();
    }
}
~~~

`principal("order-integration-service")` là tên logic ổn định cho service-level authorized client, **không phải user thực**. Nếu có nhiều manager beans, dùng `@Qualifier` để tiêm đúng bean.

**Tuyệt đối không log** `client.getAccessToken().getTokenValue()`, dù ở level DEBUG.

## 9. OAuth2 với RestClient

### 9.1. Một cách tường minh: interceptor giới hạn đúng client

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class InventoryOAuthHttpConfiguration {

    @Bean
    RestClient inventoryOAuthRestClient(
            RestClient.Builder builder,
            InventoryAccessTokenProvider tokenProvider,
            @Value("${integrations.inventory.base-url}")
            String baseUrl) {

        return builder
                .baseUrl(baseUrl)
                .requestInterceptor((request, body, execution) -> {
                    request.getHeaders().setBearerAuth(
                            tokenProvider.accessToken());
                    return execution.execute(request, body);
                })
                .build();
    }
}
~~~

Đoạn này dành riêng cho Inventory API. Khi token chưa có, interceptor có thể phát sinh request tới AS và làm tăng latency; giới hạn timeout/token endpoint retry riêng. Tránh một client dùng nhiều dynamic URL mà gắn Bearer token mặc định, vì redirect/cross-origin có thể làm lộ token.

### 9.2. OAuth2ClientHttpRequestInterceptor của Spring Security

Ở Spring Security 6.4+ và 7.x có `OAuth2ClientHttpRequestInterceptor` cho `RestClient`. Có thể để Spring Security đưa Bearer token và quản lý authorized-client lifecycle.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.client.OAuth2ClientHttpRequestInterceptor;
import org.springframework.security.oauth2.client.web.client.RequestAttributePrincipalResolver;
import org.springframework.web.client.RestClient;

@Configuration(proxyBeanMethods = false)
public class ManagedOAuthClientConfiguration {

    @Bean
    RestClient inventoryManagedClient(
            RestClient.Builder builder,
            OAuth2AuthorizedClientManager serviceAuthorizedClientManager) {

        var interceptor =
                new OAuth2ClientHttpRequestInterceptor(
                        serviceAuthorizedClientManager);
        interceptor.setPrincipalResolver(
                new RequestAttributePrincipalResolver());

        return builder
                .baseUrl("https://inventory.example.org")
                .requestInterceptor(interceptor)
                .build();
    }
}
~~~

Khi gọi:

~~~java
import static org.springframework.security.oauth2.client.web.client.RequestAttributeClientRegistrationIdResolver.clientRegistrationId;
import static org.springframework.security.oauth2.client.web.client.RequestAttributePrincipalResolver.principal;

InventoryResponse response = inventoryManagedClient.post()
        .uri("/v1/reservations")
        .attributes(clientRegistrationId("inventory-client"))
        .attributes(principal("order-integration-service"))
        .body(request)
        .retrieve()
        .body(InventoryResponse.class);
~~~

`request` và `InventoryResponse` là DTO của ứng dụng. Dùng **một trong hai cách**: custom token interceptor hoặc Spring Security interceptor, không xếp cả hai trên cùng client.

**Version note:** API Spring Security trên không có ở mọi bản Boot/Security cũ. Với Boot 3.2/Security 6.2, có thể dùng manager + custom interceptor hoặc WebClient OAuth2 filter thay thế.

### 9.3. Cảnh báo scope của default token

Đừng đặt `setDefaultOAuth2AuthorizedClient(true)` trong một client phục vụ nhiều partner hoặc dùng token của user đang đăng nhập. Cấu hình default có thể tự mang token vào **mọi request**; nên chọn registration/principal tường minh hoặc tạo client riêng theo downstream.

## 10. OAuth2 trong WebClient/reactive

Với Spring WebFlux, dùng `ReactiveOAuth2AuthorizedClientManager` để không block event loop khi xin token.

### 10.1. Reactive manager cho background service

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

@Configuration(proxyBeanMethods = false)
public class ReactiveOAuth2Configuration {

    @Bean
    ReactiveOAuth2AuthorizedClientManager reactiveManager(
            ReactiveClientRegistrationRepository registrations,
            ReactiveOAuth2AuthorizedClientService authorizedClients) {

        ReactiveOAuth2AuthorizedClientProvider provider =
                ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
                        .clientCredentials()
                        .build();

        var manager =
                new AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager(
                        registrations, authorizedClients);
        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
~~~

### 10.2. WebClient filter

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction;
import org.springframework.web.reactive.function.client.WebClient;

@Bean
WebClient inventoryWebClient(
        WebClient.Builder builder,
        ReactiveOAuth2AuthorizedClientManager reactiveManager) {

    var oauth2 = new ServerOAuth2AuthorizedClientExchangeFilterFunction(
            reactiveManager);

    return builder
            .baseUrl("https://inventory.example.org")
            .filter(oauth2)
            .build();
}
~~~

Request có registration ID tường minh:

~~~java
import static org.springframework.security.oauth2.client.web.reactive.function.client.ServerOAuth2AuthorizedClientExchangeFilterFunction.clientRegistrationId;

Mono<InventoryResponse> result = inventoryWebClient.post()
        .uri("/v1/reservations")
        .attributes(clientRegistrationId("inventory-client"))
        .bodyValue(request)
        .retrieve()
        .bodyToMono(InventoryResponse.class);
~~~

Ví dụ reactive giả định principal/context ổn định được quản lý theo cấu hình service-tier; cần kiểm tra scope authorized-client cache trong môi trường sử dụng. Không gọi blocking `manager.authorize(...)` trực tiếp trên Netty event loop.

## 11. HTTP Interface client và Spring Integration

Với `@HttpExchange` / `@GetExchange`, bảo mật vẫn do underlying `RestClient`/`WebClient` cung cấp. Không có annotation interface nào tự lấy OAuth2 token nếu transport chưa được cấu hình.

~~~java
import org.springframework.web.service.annotation.GetExchange;
import org.springframework.web.service.annotation.HttpExchange;
import org.springframework.web.bind.annotation.PathVariable;

@HttpExchange("/v1")
public interface InventoryHttpApi {

    @GetExchange("/products/{sku}")
    InventoryProduct find(@PathVariable String sku);
}
~~~

Proxy dùng đúng RestClient đã gắn OAuth2:

~~~java
import org.springframework.web.client.support.RestClientAdapter;
import org.springframework.web.service.invoker.HttpServiceProxyFactory;

HttpServiceProxyFactory factory =
        HttpServiceProxyFactory.builderFor(
                RestClientAdapter.create(inventoryOAuthRestClient))
                .build();

InventoryHttpApi api =
        factory.createClient(InventoryHttpApi.class);
~~~

`InventoryProduct` là DTO ví dụ. API `HttpServiceProxyFactory` có những thay đổi theo Spring Framework version; đối chiếu chữ ký khi tích hợp vào dự án thực.

Spring Integration HTTP outbound gateway cũng cần HTTP client/message sender riêng: chỉ khai báo OAuth2 registration trong YAML không có nghĩa mọi outbound adapter tự lấy Bearer token. Với SOAP, HTTP Basic/Bearer ở transport **khác WS-Security UsernameToken** trong SOAP Header.

Kafka, RabbitMQ, PostgreSQL và Redis sử dụng authentication/TLS của transport/driver tương ứng; không dùng API key header HTTP để xác thực Kafka broker hoặc Redis ACL.

## 12. Resource Server phải xác minh token và quyền

Một access token do OAuth2 AS cấp có thể mang các claims như:

~~~json
{
  "iss": "https://auth.example.org",
  "aud": ["inventory-api"],
  "scope": "inventory.read inventory.reserve",
  "client_id": "order-integration-service"
}
~~~

Đây là payload minh họa, **không phải JWT đã được ký**. Resource Server phải xác minh signature/JWKS hoặc token introspection, expiry, issuer, audience, scopes và business resource permissions.

Với multi-tenant API:

- `scope=inventory.reserve` chỉ cho biết loại quyền.
- Caller vẫn phải có quyền với tenant/warehouse cụ thể.
- Không tin `tenantId` do client khai báo nếu không qua authorization.
- Tránh dùng một client credential chung cho tất cả tenants khi có thể tách policy theo identity.
- Không forward access token Inventory sang Payment API dù hai API cùng một Authorization Server.

### 12.1. Client credentials không thay user delegation

Client Credentials thường đại diện chính service, không phải user hiện tại. Nếu yêu cầu “thay mặt user” hoặc audit user identity, cần flow delegation phù hợp hệ thống (ví dụ token exchange/authorization-code theo chính sách), chứ không nhét email/userId vào header rồi coi là OAuth2 user claim.

## 13. Token cache, expiry và lỗi

~~~mermaid
flowchart TD
    A["Outbound call"] --> B{"Có access token hợp lệ?"}
    B -->|"Có"| C["Gửi Bearer token tới API"]
    B -->|"Không"| D["Gọi token endpoint"]
    D --> E{"AS cấp token?"}
    E -->|"Có"| F["Lưu authorized client"]
    F --> C
    E -->|"Không"| G["Auth acquisition error"]
    C --> H["Validate result 2xx/401/403/429/5xx"]
~~~

Token cache phải đúng phạm vi application principal + registration, có expiry safety margin và xử lý concurrent token acquisition. **Không tạo token mới cho từng message** khi một token còn hạn dùng được; việc đó tăng tải AS và có thể gặp rate limit.

Client Credentials thường không có refresh token: khi access token sắp hết hạn, client xin token mới theo grant, không assume AS sẽ trả `refresh_token`.

### 13.1. Ma trận lỗi

| Phản hồi | Nguyên nhân thường gặp | Hướng xử lý |
| --- | --- | --- |
| Token endpoint `invalid_client` | Sai secret/client auth method | Sửa cấu hình, không retry liên tục |
| Token endpoint `invalid_scope` | Scope chưa được AS cấp | Sửa registration/policy |
| Token endpoint 429/503 | AS quá tải hoặc tạm lỗi | Retry giới hạn, backoff/circuit breaker |
| Resource 401 `invalid_token` | Token expired/invalid/audience | Có thể bỏ cached token và xin lại theo policy |
| Resource 403 `insufficient_scope` | Token hợp lệ nhưng thiếu quyền | Sửa scope/authorization |
| Resource 429 | Quota/rate limit | Backoff, bulkhead |
| Resource 503 | Downstream unavailable | Retry khi side effect an toàn |
| HTTPS PKIX error | Thiếu CA/intermediate | Sửa truststore/cert |
| Hostname verification failure | Sai SAN/DNS | Sửa host hoặc certificate |

Đặc biệt: **Lỗi token endpoint và lỗi Resource API là hai downstream riêng**. Nếu không lấy được token, chưa có bằng chứng Inventory API đã nhận request. Nếu token hợp lệ nhưng Inventory POST bị timeout sau khi gửi, business side effect có thể đã xảy ra.

### 13.2. Clock skew và concurrency

Authorization Server, Resource Server và client phải đồng bộ đồng hồ. Clock skew có thể làm một token bị resource server từ chối trước khi client coi nó hết hạn. Sử dụng margin phù hợp; không kéo dài token lifetime bằng cách bỏ kiểm tra expiry ở server.

Một service có hàng trăm concurrent calls khi token hết hạn có thể cùng cố xin token. Kiểm tra token manager/cache implementation và tải AS thực tế, dùng backpressure/locking/cache coordination khi cần, không tự xây cache thiếu kiểm thử.

## 14. Quản lý secrets và credential rotation

### 14.1. Secrets đặt ở đâu?

Nên dùng Vault/Secret Manager/Kubernetes Secrets/External Secrets hoặc cơ chế workload identity có kiểm soát. Yêu cầu:

- Không commit client secret/API key/Basic password vào Git.
- Không gửi secrets qua message payload hoặc outbox.
- Không log access token, Authorization header, token response body.
- Giới hạn quyền đọc theo workload.
- Có audit người/service đã đổi secret.
- Có quy trình revoke và rotation khi credential lộ.

### 14.2. Rotation Basic/API key

1. Cấp credential mới từ provider; nếu có dual-active, giữ cũ trong cửa sổ chuyển đổi.
2. Cập nhật secret manager.
3. Rollout client, kiểm tra requests bằng credential mới.
4. Thu hồi credential cũ.
5. Xác minh error rate và không có stale clients.

Nếu `RestClient` đã được tạo với `defaultHeader`, thay giá trị secret trên disk/env **không tự thay header** của client đang chạy. Cần restart/rebuild client hoặc triển khai cơ chế dynamic secret lookup có kiểm soát.

### 14.3. Rotation OAuth2

Rotate `client-secret` ảnh hưởng khả năng xin token mới. Các access tokens đã cấp có thể vẫn còn hiệu lực đến khi hết hạn tùy AS policy. Cần:

- Chuẩn bị secret/certificate mới.
- Cập nhật client registration và triển khai.
- Xác minh xin token mới và audience/scope đúng.
- Thu hồi secret cũ sau cửa sổ chuyển đổi.
- Nếu token cũ phải bị vô hiệu hóa ngay, dùng revoke/introspection/policy của AS.

Với hệ bảo mật cao, AS có thể hỗ trợ `private_key_jwt` hoặc mTLS client authentication thay shared secret. Cơ chế đó cũng cần certificate/key lifecycle và policy chống replay.

## 15. Timeout, retry và idempotency

Một request OAuth2 có thể bao gồm **token acquisition + API call + retry**:

~~~text
Token endpoint connect/read
       ↓
Resource API connect/read
       ↓
Retry delay + additional attempts
       ↓
Business deadline
~~~

Phân biệt timeout:

| Timeout | Ảnh hưởng |
| --- | --- |
| Pool acquisition | Chờ một HTTP connection rảnh |
| TCP connect | Mở connection tới AS/API |
| TLS handshake | Xác thực server/client và thiết lập kênh |
| Response/read | Chờ dữ liệu từ AS/API |
| Total operation deadline | Tổng thời gian qua nhiều bước và retries |
| Business deadline | SLA từ event/command tới kết quả nghiệp vụ |

**Auth config errors thường không retryable.** `invalid_client` và thiếu scope không thể sửa bằng exponential retry mãi mãi. Với 429/503 có thể retry có giới hạn và jitter theo contract.

### 15.1. Timeout sau khi gửi là kết quả chưa xác định

~~~mermaid
sequenceDiagram
    participant O as Order Service
    participant I as Inventory API
    participant D as Inventory Database
    O->>I: POST reserve operationId=R-100, Bearer token
    I->>D: COMMIT reservation
    I--xO: Response lost
    O->>O: Timeout, outcome UNKNOWN
    O->>I: Retry with same operationId
    I->>D: Check idempotency key
    I-->>O: Return original result
~~~

Basic/API key/OAuth2 chỉ xác thực; **không ngăn duplicate side effect**. Với command có tác động, cần operationId/idempotency key ổn định, partner status lookup hoặc reconciliation.

### 15.2. Outbox và ranh giới transaction

~~~mermaid
flowchart LR
    A["Order command"] --> B["SQL transaction"]
    B --> C["Update business state"]
    B --> D["Insert outbox intent"]
    D --> E["Outbox worker"]
    E --> F["Obtain credential/token"]
    F --> G["HTTP partner"]
    G --> H["Confirmed / Rejected / Unknown"]
~~~

Ghi SQL state và outbox intent trong cùng local transaction, sau commit mới gọi API. Nếu HTTP timeout, không kết luận đã failed; relay giữ intent cho retry/reconciliation. Token không nằm trong outbox payload. Broker consumer chỉ ACK sau khi business processing hoặc durable handoff đạt chính sách.

Không để RestClient tự retry POST ba lần, Spring Retry retry ba lần và broker redeliver ba lần mà không có retry budget/monitoring tổng.

## 16. Kiểm thử Basic và API key

### 16.1. Header test với MockRestServiceServer

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestClient;

import static org.springframework.test.web.client.match.MockRestRequestMatchers.*;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;
import static org.junit.jupiter.api.Assertions.assertEquals;

class BasicClientTest {

    @Test
    void includesBasicHeader() {
        RestClient.Builder builder = RestClient.builder();
        MockRestServiceServer mock =
                MockRestServiceServer.bindTo(builder).build();

        RestClient client = builder
                .baseUrl("https://catalog.test")
                .defaultHeaders(h ->
                        h.setBasicAuth("svc-test", "test-password"))
                .build();

        String raw = "svc-test:test-password";
        String expected = "Basic " +
                Base64.getEncoder().encodeToString(
                        raw.getBytes(StandardCharsets.ISO_8859_1));

        mock.expect(requestTo("https://catalog.test/v1/ping"))
                .andExpect(method(org.springframework.http.HttpMethod.GET))
                .andExpect(header(HttpHeaders.AUTHORIZATION, expected))
                .andRespond(withSuccess("ok", MediaType.TEXT_PLAIN));

        String body = client.get()
                .uri("/v1/ping")
                .retrieve()
                .body(String.class);

        assertEquals("ok", body);
        mock.verify();
    }
}
~~~

Test dùng **credential giả** và không tạo TLS socket. Nó chứng minh Authorization header đúng; không chứng minh HTTPS trust/SAN. Với API key, assert `X-API-Key` đúng trên Pricing client và **không có** trên Catalog/Inventory client.

### 16.2. Test không rò credential

- Assert HTTP redirects sang host khác không mang credential.
- Assert wire logging/error messages/metrics không chứa Authorization/API key.
- Kiểm tra secret không xuất hiện trong SQL outbox row hoặc broker payload.
- Kiểm tra startup không fail vì env secret bị thiếu/malformed.
- Test rotation giữa old/new key và quan sát lỗi 401/403 theo policy.

## 17. Kiểm thử OAuth2 Client Credentials

Một bài test đủ tốt có **Authorization Server stub** và **Resource API stub**:

~~~text
Order Service
  ├─ AS token stub: /oauth2/token
  └─ Inventory API stub: /v1/reservations
~~~

Các assertions quan trọng:

1. Token request dùng `grant_type=client_credentials`.
2. Client ID/auth method đúng token endpoint contract.
3. Secret không xuất hiện trong Resource API request.
4. Resource API nhận `Authorization: Bearer test-access-token`.
5. Token được dùng lại khi chưa hết hạn.
6. Token hết hạn thì xin mới theo policy.
7. Token endpoint `invalid_client` không tạo retry storm.
8. API 401 invalid_token và 403 insufficient_scope được phân loại khác nhau.
9. Token Inventory không bị gửi đến Payment API.
10. Principal của app ổn định qua nhiều Quartz/broker messages.

Mock `OAuth2AuthorizedClientManager` giúp kiểm tra interceptor gắn Bearer token, nhưng không chứng minh **token acquisition/expiry/persistence**. Dùng WireMock/MockWebServer hoặc test fixture phù hợp để kiểm tra cả hai hop.

### 17.1. TLS test thật

Mock HTTP test không kiểm chứng CA chain/hostname. Khi môi trường đòi mTLS hoặc TLS trust đặc biệt, chạy integration test với TLS-enabled test server:

| Trường hợp | Kỳ vọng |
| --- | --- |
| CA và SAN đúng | HTTPS pass |
| CA không tin | SSL handshake fail |
| URL host không khớp SAN | Hostname verification fail |
| Thiếu client cert khi server `need` | Handshake fail |
| TLS pass, scope thiếu | API 403 |
| OAuth2 Bearer token sai audience | Resource Server reject |

Không làm TLS test pass bằng trust-all manager.

## 18. Observability và runbook

### 18.1. Đo đúng loại lỗi

| Tín hiệu | Ý nghĩa |
| --- | --- |
| `integration.auth.token.request` | Số lần gọi token endpoint |
| `integration.auth.token.failure` | Token acquisition errors |
| `integration.http.client.duration` | API latency |
| `integration.http.client.unauthorized` | Resource API trả 401 |
| `integration.http.client.forbidden` | Resource API trả 403 |
| `integration.http.client.throttled` | Resource API 429 |
| TLS handshake failures | CA/SAN/client certificate |
| `integration.outbox.oldest.age` | Business intent chưa hoàn tất |
| `integration.operation.unknown` | Kết quả remote chưa xác định |

Đừng gộp AS token endpoint latency và Inventory API latency thành một “Inventory request duration” không thể chẩn đoán. Khi token được cache, request không cần gọi AS; khi AS outage, downstream API có thể vẫn hoạt động cho tới khi token hết hạn.

Metric tags nên ít giá trị như `downstream=inventory`, `auth_scheme=oauth2`, `outcome=success/error`. Không dùng raw token/key, orderId, certificate serial, email hoặc full URL có query làm tags.

### 18.2. Log redaction

Cần che các giá trị:

~~~text
Authorization: Basic ****
Authorization: Bearer ****
X-API-Key: ****
client_secret=****
access_token=****
refresh_token=****
~~~

Log được phép tập trung vào partner logical name, method, route template, status, error category, duration và trace ID, không hiển thị secrets hoặc payload nhạy cảm.

### 18.3. Runbook

| Triệu chứng | Nguyên nhân khả dĩ | Hành động |
| --- | --- | --- |
| Basic 401 sau deploy | Secret/bean vẫn dùng password cũ | Kiểm tra secret mount và rotation |
| API key 403 | Key revoked hoặc thiếu quyền | Kiểm tra vendor policy |
| OAuth2 `invalid_client` | Sai secret/client auth method | Sửa registration/credential |
| OAuth2 `invalid_scope` | Scope chưa được AS cấp | Sửa quyền |
| Có token nhưng API 401 | Token expired/sai audience | Kiểm tra resource validation/invalidation |
| API 403 | Scope hoặc business permission không đủ | Kiểm tra policy |
| Token requests tăng bất thường | Token cache/principal sai hoặc expiry rất ngắn | Kiểm tra manager và concurrency |
| TLS PKIX path building failed | Thiếu CA/intermediate | Sửa trust material |
| TLS hostname mismatch | SAN không khớp URL | Sửa endpoint/certificate |
| 429/503 | Rate-limit hoặc outage | Backoff/bulkhead/circuit breaker |
| POST timeout sau write | Remote có thể đã commit | Idempotency/status lookup |
| Token xuất hiện trong logs | Wire logging không redact | Ngừng log, revoke/rotate theo incident |

**Không sửa** 401/403 bằng việc cấp quyền toàn cục, không sửa TLS lỗi bằng trust-all và không retry vô hạn trên một client secret bị revoke.

## 19. Checklist triển khai

- [ ] Đã chọn cơ chế theo API contract: Basic, API key hoặc OAuth2 Client Credentials.
- [ ] Resource và token endpoints đều dùng HTTPS, xác minh certificate chain/hostname.
- [ ] Secrets được inject bởi secret manager/env, không hardcode hoặc log.
- [ ] Mỗi partner có outbound client và credential scope riêng.
- [ ] Basic dùng service account least privilege, có rotation policy.
- [ ] API key ở header theo vendor contract khi có thể, tránh query string.
- [ ] OAuth2 registration đúng client ID, secret/method, token URI, scopes.
- [ ] Với Quartz/outbox/broker worker, manager hỗ trợ service-tier không phụ thuộc user session.
- [ ] Authorized-client cache dùng principal ổn định, không theo event/order ID.
- [ ] Resource Server kiểm tra issuer, audience, expiry, scopes và quyền nghiệp vụ.
- [ ] Có timeout, retry budget và phân loại invalid_client/401/403/429/503 rõ.
- [ ] Đã test token expiry/renewal, rotation và credential leak.
- [ ] Không gửi Bearer token/API key qua redirects, logs hoặc outbox/broker payload.
- [ ] HTTP POST side effect có business idempotency/reconciliation.
- [ ] Có tests header, AS + API, TLS và failure windows.
- [ ] Observability tách auth acquisition, HTTP downstream và business outcome.

**Ghi nhớ:** Basic gửi username/password, API key gửi credential theo vendor contract, còn OAuth2 Client Credentials dùng service identity để xin **access token có thời hạn**. Cả ba đều cần HTTPS, bảo vệ secrets, client scope rõ ràng, kiểm soát quyền, retry/idempotency và kiểm thử thực tế. Trong Spring Boot, `RestClient`/`WebClient` chỉ gửi đúng credential khi ta cấu hình **đúng adapter và HTTP transport**; không nên trộn authentication của một downstream vào toàn bộ ứng dụng.

## Tài liệu tham khảo

- [Spring Boot — OAuth2 Client](https://docs.spring.io/spring-boot/reference/security/oauth2.html): client registration, provider và auto-configuration.
- [Spring Security — OAuth2 Client Core](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html): manager, service-tier client credentials và provider.
- [Spring Security — Authorized Client Features](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html): RestClient interceptor và application principal.
- [Spring Security — Reactive Authorized Clients](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/authorized-clients.html): WebClient filter/reactive manager.
- [Spring Boot — Calling REST Services](https://docs.spring.io/spring-boot/reference/io/rest-client.html): RestClient.Builder và HTTP configuration.
- [Spring Framework — REST Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): HTTP Interfaces và client APIs.
- [RFC 7617 — HTTP Basic Authentication](https://www.rfc-editor.org/rfc/rfc7617): Basic scheme, encoding và challenges.
- [RFC 6749 — OAuth 2.0 Client Credentials](https://www.rfc-editor.org/rfc/rfc6749#section-4.4): grant type.
- [RFC 6750 — OAuth2 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer token và error semantics.
- [RFC 8705 — OAuth2 Mutual-TLS Authentication](https://www.rfc-editor.org/rfc/rfc8705): mTLS token endpoint/client authentication.
- [OWASP — Secrets Management](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): lưu trữ và rotation.
- [OWASP — REST Security](https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html): HTTPS, tokens, API protection.
