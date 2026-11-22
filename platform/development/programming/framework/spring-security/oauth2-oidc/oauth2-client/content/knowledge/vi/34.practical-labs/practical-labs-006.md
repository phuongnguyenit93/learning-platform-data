# 34.6. Job nền dùng client credentials và kho authorized client

Trong những bài tập OAuth2/OIDC Client dành cho **ứng dụng web**, người dùng thường đăng nhập qua `oauth2Login()`, ứng dụng nhận `Authentication` và dùng Access Token đã được cấp để gọi API thay mặt người dùng. **Job nền** lại có một tình huống khác: tác vụ tự chạy theo lịch, không có browser, không có phiên đăng nhập, không có authorization redirect, và không có `HttpServletRequest` mang principal của người dùng.

Ví dụ một dịch vụ Spring Boot cần thực hiện công việc sau mỗi năm phút:

> Đọc dữ liệu tồn kho từ Inventory API nội bộ, đồng bộ dữ liệu vào hệ thống của công ty, ghi số bản ghi thành công và phát cảnh báo khi tác vụ lỗi.

Inventory API yêu cầu **OAuth 2.0 Access Token**. OpenID Provider/Authorization Server đã đăng ký một **confidential client** dành riêng cho job, cho phép grant type **`client_credentials`** và scope `inventory.read`. Đây là **machine-to-machine (M2M)**: đối tượng được cấp quyền là **client application**, không phải một user đã OIDC login.

Bài thực hành này sẽ kết hợp:

- **Spring Boot Scheduling** với `@EnableScheduling` và `@Scheduled`.
- **Spring Security OAuth2 Client** với `ClientRegistration` cấu hình bằng properties.
- **`AuthorizedClientServiceOAuth2AuthorizedClientManager`** phù hợp xử lý OAuth2 ngoài HTTP request.
- **`OAuth2AuthorizedClientProvider`** cho `client_credentials`.
- **`OAuth2AuthorizedClientService`** để lưu và tra lại authorized client.
- **Stable technical principal** để dùng lại token của cùng một logical job.
- **`WebClient`** gửi Bearer Access Token tới Resource Server đúng đích.
- **Unit/integration tests**, xử lý expiration/401/403/5xx, nhiều replicas, lưu trữ lâu dài, quan sát và bảo vệ credentials.

Bài có một **đường triển khai tối thiểu chạy được khi được cung cấp Authorization Server và Inventory API đúng hợp đồng**, cùng những mở rộng dành cho production. Các địa chỉ `example.test`, client IDs, secrets và token trong ví dụ chỉ là **dữ liệu minh họa**, không phải dịch vụ thật.

> **Điểm mấu chốt:** Đối với job không có browser, **không dùng session-aware `DefaultOAuth2AuthorizedClientManager` như thể có `HttpServletRequest`**. Hãy dùng service-backed manager, xác định một technical principal ổn định và để manager/provider chịu trách nhiệm tìm token cũ hoặc yêu cầu token mới khi cần.

---

## 1. Mục tiêu học tập

Hoàn thành bài thực hành, bạn cần giải thích và triển khai được:

1. Sự khác nhau giữa **Authorization Code/OIDC login** và **Client Credentials grant**.
2. Cấu hình `registrationId`, `client-id`, `client-secret`, `token-uri`, `scope` cho một service client.
3. Tạo `OAuth2AuthorizedClientManager` không phụ thuộc request/session.
4. Dùng `OAuth2AuthorizeRequest` với **principal ổn định** cho tác vụ nền.
5. Tra `OAuth2AuthorizedClient` và lấy Access Token còn hiệu lực.
6. Gọi Resource Server bằng `Authorization: Bearer ...`.
7. Không gửi machine token tới API đòi quyền người dùng.
8. Lưu authorized client tại memory hoặc kho persistent theo policy.
9. Xử lý token hết hạn, token endpoint lỗi, API 401/403, rate limit và retry.
10. Tránh trùng job khi chạy nhiều pods/replicas.
11. Viết tests cô lập, không sử dụng secret/token production.
12. Biết giới hạn của bài demo và những điều phải bổ sung trước khi vận hành thật.

## 2. Kiến trúc cần xây dựng

```mermaid
sequenceDiagram
    autonumber
    participant S as Spring Scheduler
    participant J as InventorySyncJob
    participant M as AuthorizedClientServiceOAuth2AuthorizedClientManager
    participant R as OAuth2AuthorizedClientService
    participant AS as Authorization Server
    participant C as InventoryApiClient + WebClient
    participant API as Inventory Resource Server

    S->>J: Kích hoạt theo lịch
    J->>C: fetchSnapshot()
    C->>M: authorize(registration=inventory-job, principal=job:inventory-sync)
    M->>R: loadAuthorizedClient(registration, principal)
    alt Chưa có token hoặc token cần cấp lại
        M->>AS: POST /oauth2/token grant_type=client_credentials
        AS-->>M: Access Token + expires_in + scope
        M->>R: saveAuthorizedClient(...)
    else Token vẫn còn dùng được
        R-->>M: Authorized client hiện có
    end
    M-->>C: OAuth2AuthorizedClient
    C->>API: GET /v1/inventory/snapshot với Bearer Access Token
    API-->>C: 200 + JSON tồn kho
    C-->>J: InventorySnapshot
    J->>J: Xử lý/ghi dữ liệu theo nghiệp vụ
```

**Quan sát:** trong sơ đồ không có browser, `state`, `nonce`, ID Token hoặc callback `/login/oauth2/code/...`. Chúng thuộc luồng đăng nhập tương tác của người dùng, không thuộc `client_credentials`.

### 2.1. Các vai trò OAuth2

| Vai trò | Thành phần trong bài |
|---|---|
| **Client** | Spring Boot inventory-sync job. |
| **Authorization Server (AS)** | Dịch vụ cấp OAuth2 Access Token cho confidential client. |
| **Resource Server (RS)** | Inventory API xác minh Access Token, scope/audience và quyền. |
| **Resource Owner** | Không có user tương tác trực tiếp trong grant này; quyền được cấp cho client theo policy của AS. |
| **Authorized client store** | Kho phía Spring Boot lưu thông tin token đã được cấp. |

### 2.2. Mục tiêu khác nhau giữa client credentials và OIDC login

| Tiêu chí | Browser `oauth2Login()` | Background `client_credentials` |
|---|---|---|
| Có người dùng đăng nhập? | Có. | Không cần. |
| Dùng Authorization Code? | Có trong flow thông thường. | Không. |
| Có browser redirect và callback? | Có. | Không. |
| Có `state`/PKCE/`nonce`? | Có khi áp dụng. | Không phải thành phần của grant này. |
| Có ID Token để đăng nhập user? | Có với OIDC. | Thông thường không. |
| Token đại diện cho | User cho phép client thực hiện quyền đã được cấp. | Ứng dụng/service client. |
| Manager phù hợp | Context HTTP hoặc reactive web theo stack. | Service-backed manager không cần HTTP request. |
| Principal key | User identity phù hợp. | Một technical principal ổn định. |
| Scope điển hình | `openid`, `profile`, API scopes. | API scopes như `inventory.read`. |

**Không dùng scope `openid` chỉ để «biến» `client_credentials` thành OIDC user login.** Access Token máy không tạo `OidcUser`/session người dùng.

## 3. Hợp đồng giả định của bài thực hành

Ta giả định có một Authorization Server hỗ trợ OAuth2 Client Credentials Grant:

```http
POST /oauth2/token HTTP/1.1
Host: auth.example.test
Authorization: Basic <base64-client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=client_credentials&scope=inventory.read
```

Response minh họa:

```json
{
  "access_token": "synthetic-access-token",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "inventory.read"
}
```

Và Inventory API:

```http
GET /v1/inventory/snapshot HTTP/1.1
Host: api.example.test
Authorization: Bearer synthetic-access-token
Accept: application/json
```

Response minh họa:

```json
{
  "items": [
    {
      "sku": "SKU-001",
      "available": 25
    },
    {
      "sku": "SKU-002",
      "available": 0
    }
  ]
}
```

Các endpoint/token chỉ nhằm minh họa giao thức. Để chạy thật, thay bằng **AS và API thử nghiệm do bạn kiểm soát**, có client registration đã được cấp phép. Việc mô phỏng offline bằng stub server sẽ được trình bày ở phần kiểm thử.

### 3.1. Vì sao phải có scope chính xác?

`inventory.read` thể hiện quyền truy cập đọc tồn kho mà Authorization Server cấp. Ứng dụng không tự có quyền chỉ vì biết `client-id`/`client-secret`.

Resource Server có thể còn yêu cầu:

- Đúng **audience** hoặc resource indicator.
- Đúng issuer.
- Token chưa hết hạn và đúng loại.
- Client identity được cho phép.
- Scope cụ thể cho endpoint.
- Policy mTLS/private network hoặc tổ chức.

Thêm scope vào YAML **không bắt buộc** AS phải cấp scope đó. Policy quyết định cuối cùng nằm tại AS và RS.

### 3.2. Không dùng client credentials cho nghiệp vụ thay mặt người dùng

Nếu API trả «đơn hàng của người đang đăng nhập», việc dùng machine token chỉ vì job không có user sẽ làm sai mô hình authorization. Phải có thiết kế riêng cho delegated access, offline access hoặc một service/API contract dành cho machine.

Bài này giả định **Inventory API có endpoint M2M rõ ràng**, được AS và Resource Server cho phép.

## 4. Thiết lập project

Một cấu trúc nhỏ:

```text
inventory-sync/
├── build.gradle.kts
├── src/main/java/com/example/inventorysync/
│   ├── InventorySyncApplication.java
│   ├── config/
│   │   ├── OAuth2JobConfiguration.java
│   │   ├── InventoryHttpConfiguration.java
│   │   └── EndpointSecurityConfiguration.java
│   ├── client/
│   │   ├── InventoryApiClient.java
│   │   └── InventorySnapshot.java
│   └── job/
│       └── InventorySyncJob.java
├── src/main/resources/
│   └── application.yml
└── src/test/java/com/example/inventorysync/
    ├── InventoryApiClientTest.java
    ├── InventorySyncJobTest.java
    └── OAuth2ManagerIntegrationTest.java
```

Để demo vừa có scheduled job vừa có HTTP endpoint giám sát, ví dụ dùng **Spring MVC**. Thêm WebFlux starter **chỉ để dùng `WebClient`**, không chuyển server sang Reactive WebFlux nếu `spring-boot-starter-web` vẫn được chọn làm web application type. Manager service-backed vẫn phù hợp vì job chạy ngoài HTTP request.

Nếu triển khai **headless hoàn toàn** (`spring.main.web-application-type=none`), có thể không cần Spring MVC server, nhưng phải chủ động đảm bảo ClientRegistration repository/authorized client service được khởi tạo đúng cho loại application và Boot version đang dùng. Không giả định một Web-only auto-configuration tiếp tục tồn tại trong non-web context.

## 5. Gradle dependencies

Ví dụ `build.gradle.kts` của một project đã quản lý plugin Spring Boot/BOM và JDK tương thích:

```kotlin
dependencies {
    // Spring MVC + endpoint health/administration khi cần
    implementation("org.springframework.boot:spring-boot-starter-web")

    // Spring Security core và OAuth2 Client
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")

    // WebClient cho HTTP outbound
    implementation("org.springframework.boot:spring-boot-starter-webflux")

    // Health/metrics là phần mở rộng vận hành
    implementation("org.springframework.boot:spring-boot-starter-actuator")

    // Unit/integration tests
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
    testImplementation("io.projectreactor:reactor-test")
}

tasks.test {
    useJUnitPlatform()
}
```

Đây là **fragment dependencies**, không phải file Gradle tự đầy đủ. Chọn Spring Boot plugin/version qua build management của project, và để BOM quản lý các phiên bản Spring Security/Reactor tương thích.

### 5.1. Vì sao có cả Web và WebFlux starters?

- `starter-web` đưa vào Spring MVC/Servlet server; đủ cho Actuator HTTP endpoints và lựa chọn làm application web.
- `starter-webflux` đưa vào `WebClient` và Reactor Netty HTTP client.
- Job dùng `WebClient` làm **HTTP client**, nhưng bản thân scheduler không phải một WebFlux server.
- Nếu project không cần MVC endpoints, có thể giảm phụ thuộc và thiết kế worker headless rõ ràng.

Đừng copy config `SecurityWebFilterChain` vào một ứng dụng Servlet chỉ vì thấy `WebClient` trên classpath.

### 5.2. Maven tương đương

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
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.springframework.security</groupId>
        <artifactId>spring-security-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

Giả định `pom.xml` đã có Spring Boot parent/BOM. Nếu project Reactive-only, thiết kế dependencies/server configuration tương ứng.

## 6. Cấu hình client credentials bằng YAML

`src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-job:
            provider: inventory-authorization-server
            client-id: ${INVENTORY_CLIENT_ID}
            client-secret: ${INVENTORY_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope:
              - inventory.read
        provider:
          inventory-authorization-server:
            token-uri: https://auth.example.test/oauth2/token

inventory:
  api:
    base-url: https://api.example.test
  sync:
    initial-delay-ms: 10000
    fixed-delay-ms: 300000

management:
  endpoints:
    web:
      exposure:
        include: health,info
```

Đây là **mẫu cấu hình**. Cần thay domains bằng endpoints thật đã được phê duyệt. Biến môi trường `INVENTORY_CLIENT_ID` và `INVENTORY_CLIENT_SECRET` phải do secret management/deployment cung cấp; không commit secret thật vào repository.

### 6.1. Ý nghĩa từng trường

| Property | Vai trò |
|---|---|
| `registration.inventory-job` | Khóa registration nội bộ của Spring. |
| `provider` | Tham chiếu tới cấu hình AS metadata. |
| `client-id` | Định danh application tại AS. |
| `client-secret` | Credential bí mật của confidential client. |
| `client-authentication-method` | Cách client xác thực tại token endpoint. |
| `authorization-grant-type` | `client_credentials`, không phải `authorization_code`. |
| `scope` | Quyền API mà client yêu cầu. |
| `provider.*.token-uri` | Địa chỉ thực hiện OAuth2 token request. |
| `inventory.api.base-url` | URL Resource Server mà WebClient sẽ gọi. |
| `fixed-delay-ms` | Khoảng chờ sau khi một lần chạy hoàn tất, không phải cron timestamp. |

### 6.2. Vì sao không khai báo `redirect-uri`?

Client Credentials Grant không điều hướng browser nên **không có OAuth2 authorization callback**. Những trường thường thấy trong `oauth2Login()`, như:

```yaml
redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
authorization-grant-type: authorization_code
scope: [openid, profile]
```

không thuộc client credentials use case này.

### 6.3. Có cần `issuer-uri` hoặc OIDC discovery?

Không bắt buộc. Bài dùng explicit `token-uri` vì token endpoint đã được operator phê duyệt.

Nếu AS hỗ trợ OAuth2/OIDC discovery và app quản lý issuer một cách tin cậy, có thể dùng discovery theo version/configuration phù hợp. Nhưng **không lấy issuer URL động từ input của job hoặc một tenant không được duyệt**, vì metadata có thể chỉ token/JWKS/UserInfo tới host không đáng tin, dẫn tới SSRF/credential exfiltration.

### 6.4. Chọn phương thức xác thực client

Ví dụ dùng `client_secret_basic` — gửi client ID/secret tới token endpoint bằng HTTP Basic theo yêu cầu AS.

Các AS khác có thể yêu cầu `client_secret_post`, `private_key_jwt` hoặc mTLS. Không đổi authentication method chỉ để làm code compile; AS và policy quyết định phương thức hợp lệ.

Đặc biệt, không chuyển `client_secret` thành query parameter trong URL.

### 6.5. Môi trường và secret rotation

Production nên cấp credential bằng:

- Secret manager/Kubernetes Secret/CI secret injection phù hợp.
- Các quyền đọc hạn chế theo service account.
- Secret rotation có kế hoạch.
- TLS và CA trust đúng.
- Môi trường staging/test tách client registration khỏi production.

Không log `client-secret` trong debug properties/Actuator output.

## 7. Bật scheduling

`InventorySyncApplication.java`:

```java
package com.example.inventorysync;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableScheduling;

@SpringBootApplication
@EnableScheduling
public class InventorySyncApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            InventorySyncApplication.class,
            args
        );
    }
}
```

`@EnableScheduling` cho phép Spring xử lý `@Scheduled` trên các Spring-managed beans.

### 7.1. Vì sao không tạo `new InventorySyncJob(...)` bằng tay?

Một class không phải Spring Bean hoặc được tạo bằng `new` ngoài container sẽ không được framework đăng ký scheduling annotations theo cách thông thường.

Đảm bảo job được Spring quản lý, ví dụ `@Component`, rồi dùng dependency injection thay vì tạo thủ công.

### 7.2. `fixedDelay` khác `fixedRate`

| Lịch | Ý nghĩa |
|---|---|
| `fixedDelay` | Chờ một khoảng thời gian **sau khi lần chạy trước hoàn thành** rồi mới chạy lại. |
| `fixedRate` | Lên lịch theo khoảng cách giữa các lần bắt đầu, có thể tạo áp lực nếu lần chạy kéo dài. |
| `cron` | Chạy theo biểu thức lịch và timezone do cấu hình quy định. |

Bài chọn `fixedDelay` để dễ hiểu và hạn chế việc một method tự chồng lịch trong mô hình scheduler đơn giản. **Nó không bảo đảm chỉ có một job trên toàn cluster** khi chạy nhiều replicas.

## 8. Thành phần OAuth2 Client đã được Spring Boot tạo

Khi có starter OAuth2 Client và properties registration phù hợp trong một ứng dụng Servlet, Spring Boot thường có thể tạo `ClientRegistrationRepository` từ:

```yaml
spring.security.oauth2.client.registration.*
spring.security.oauth2.client.provider.*
```

Trong bài, ta dự kiến inject:

```java
ClientRegistrationRepository registrations
```

để manager có thể tìm `inventory-job`.

### 8.1. Không giả định custom Bean và Boot Bean cùng tồn tại

Nếu app tự khai báo:

```java
@Bean
ClientRegistrationRepository clientRegistrationRepository() {
    // custom registrations
}
```

Boot auto-configured repository từ YAML có thể **back off**. Nếu custom repository bỏ `inventory-job`, job không tìm thấy registration.

Trước khi vận hành, xác minh actual Bean và registration ID được load, không chỉ dựa trên việc YAML chứa trường đó.

### 8.2. Test registration không nên truy cập token endpoint

Khởi tạo registration từ explicit `token-uri` không cần thực hiện Client Credentials Grant tại thời điểm tạo bean. Token request chỉ xảy ra khi manager authorize phù hợp.

Test có thể xác minh cấu hình registration mà không gọi AS production.

## 9. Tạo `OAuth2AuthorizedClientService`

Ta chủ động khai báo một kho **in-memory** để bài demo rõ ràng:

```java
package com.example.inventorysync.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration(proxyBeanMethods = false)
public class AuthorizedClientStoreConfiguration {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
            ClientRegistrationRepository registrations) {

        return new InMemoryOAuth2AuthorizedClientService(
            registrations
        );
    }
}
```

**Đây là demo store**, phù hợp học tập và một số use cases rất nhỏ. Token sẽ mất khi process restart và không tự chia sẻ giữa nhiều instances.

### 9.1. Authorized client là gì?

Một `OAuth2AuthorizedClient` liên kết:

```text
registrationId = inventory-job
principalName = job:inventory-sync
accessToken = <opaque or JWT bearer token>
accessTokenExpiry = <Instant>
refreshToken = thường không có với client_credentials
```

Kho service có các chức năng chính:

```java
loadAuthorizedClient(registrationId, principalName)
saveAuthorizedClient(authorizedClient, principal)
removeAuthorizedClient(registrationId, principalName)
```

**`OAuth2AuthorizedClientService` không phải `ClientRegistrationRepository`**:

- Registration repository: metadata/config của **client**.
- Authorized client service: trạng thái **token đã được cấp** cho client và principal.

### 9.2. Vì sao cần principal trong M2M?

Interface của Spring Security dùng principal name như một phần **storage key**. Client credentials không có end-user, nhưng ta vẫn cung cấp một **technical principal** để phân vùng authorized client.

Tên này **không làm token trở thành token của người dùng**; nó chỉ là khóa logic ở phía ứng dụng để manager/store định danh authorization.

## 10. Chọn manager đúng cho job không có browser

Tạo `AuthorizedClientServiceOAuth2AuthorizedClientManager`:

```java
package com.example.inventorysync.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration(proxyBeanMethods = false)
public class OAuth2JobConfiguration {

    @Bean
    OAuth2AuthorizedClientManager jobAuthorizedClientManager(
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

Đây là component trọng tâm của bài.

### 10.1. Tại sao không dùng `DefaultOAuth2AuthorizedClientManager`?

Hai class được đặt tên gần giống nhưng giải quyết ngữ cảnh khác nhau:

| Manager | Ngữ cảnh phù hợp |
|---|---|
| `DefaultOAuth2AuthorizedClientManager` | Servlet HTTP request/response; thường dùng với `OAuth2AuthorizedClientRepository` và browser flow. |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | Ngoài `HttpServletRequest`, ví dụ scheduled job, service-layer automation hoặc command-line worker. |
| `ReactiveOAuth2AuthorizedClientManager` và implementations | Reactive/WebFlux, dùng Reactor `Mono` và reactive repositories/services. |

`DefaultOAuth2AuthorizedClientManager` thường liên quan đến HTTP request context, nên dùng nó trong job không có request dễ dẫn tới lỗi principal/repository hoặc thiết kế context sai.

### 10.2. Vì sao chỉ bật `clientCredentials()`?

Bài này chỉ có registration `authorization-grant-type: client_credentials`. Không cần:

```java
.authorizationCode()
.refreshToken()
.password()
```

chỉ để «hỗ trợ mọi grant».

Một **client credentials** Access Token thường **không được cấp Refresh Token** theo grant này. Khi token sắp hết hạn, client có thể xin **Access Token mới** bằng cùng grant và credential. Đừng mô tả đó là Refresh Token rotation.

### 10.3. Các defaults phụ thuộc phiên bản

Cơ chế lưu lại authorized client sau `authorize(...)`, failure handling, clock skew và token client được tạo nội bộ có thể có extension points khác nhau tùy Spring Security version.

Ví dụ trên **tường minh manager và provider**, giảm phụ thuộc implicit Boot manager default. Khi nâng cấp major version, xác minh behavior và APIs bằng tài liệu đúng phiên bản.

### 10.4. Khi có nhiều manager beans

Nếu app có cả request-scoped manager và job manager, nên inject bằng `@Qualifier`:

```java
@Qualifier("jobAuthorizedClientManager")
OAuth2AuthorizedClientManager manager
```

Không để Spring chọn nhầm browser manager cho scheduled job hoặc dùng `@Primary` một cách vô ý thức.

## 11. Chọn technical principal ổn định

Ta quy ước:

```java
private static final String PRINCIPAL = "job:inventory-sync";
private static final String REGISTRATION_ID = "inventory-job";
```

Trong mỗi lần chạy, manager sẽ nhận cùng cặp:

```text
(inventory-job, job:inventory-sync)
```

và có thể tìm lại token đã lưu.

### 11.1. Vì sao không đặt principal bằng UUID mỗi lần chạy?

Sai:

```java
String principal =
    "job:" + UUID.randomUUID();
```

Nếu mỗi invocation tạo một key mới, authorized client store có thể **không tìm thấy token từ lần trước**, khiến app liên tục request token mới và tạo nhiều records không cần thiết.

### 11.2. Vì sao không dùng tên user?

Job đang chạy bằng **ứng dụng**, không thay mặt user. Không sử dụng:

```text
principal = currentUsername
principal = emailFromLastLogin
principal = oidcSubFromSomeSession
```

nếu không có một delegated authorization design cụ thể.

### 11.3. Khi nào dùng nhiều technical principals?

Nếu cùng registration phục vụ nhiều tác vụ cần phân vùng storage hoặc audit:

```text
job:inventory-sync
job:pricing-rebuild
job:nightly-report
```

Nhưng nếu các tác vụ dùng **cùng client credentials và cùng scope**, việc dùng key khác chỉ tạo các authorized client records khác nhau; không tự cấp mức quyền thấp hơn.

Quyền thực tế phải được giới hạn bằng **client registration/scope/audience** tại AS/RS, không chỉ bởi principal name trong kho Spring.

### 11.4. Multi-tenant principal key

Nếu job chạy cho nhiều tenants mà mỗi tenant có authorization boundary riêng, identity key có thể cần bao gồm tenant ID **đã được xác minh**, registration và policy; không dùng raw tenant string từ input không tin cậy.

Tối ưu lưu trữ không được vượt qua sự cô lập token giữa tenants.

## 12. Tạo `OAuth2AuthorizeRequest`

Trong mỗi lần cần token, tạo request:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;

OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("inventory-job")
        .principal("job:inventory-sync")
        .build();
```

Sau đó:

```java
OAuth2AuthorizedClient authorized =
    manager.authorize(request);
```

### 12.1. `authorize(...)` làm gì?

Về mặt contract, manager có thể:

1. Tìm authorized client đã được lưu cho `registrationId` + principal.
2. Dùng provider phù hợp grant type.
3. Nếu token còn dùng được, trả lại authorized client hiện có.
4. Nếu chưa có/đã đến hạn cấp lại, gửi Client Credentials token request.
5. Lưu authorized client mới qua service.
6. Trả kết quả hoặc phát lỗi authorization.

Chi tiết chính xác phụ thuộc manager/provider/version/handlers của Spring Security. Điều quan trọng là **application không tự quản lý map token bằng static variable**.

### 12.2. `authorize(...)` có thể trả `null`

Spring Security manager contract cho phép kết quả `null` khi một provider không thể authorize request theo cấu hình/grant applicability. Vì thế, code nên xử lý tường minh, **không** lập tức gọi:

```java
manager.authorize(request)
    .getAccessToken();
```

trong mọi trường hợp.

### 12.3. Không gắn end-user `Authentication` giả

Một technical principal string dùng cho storage key không phải bằng chứng người dùng đã đăng nhập. Không tạo `UsernamePasswordAuthenticationToken` với quyền admin chỉ để Manager hoạt động.

## 13. Cấu hình WebClient gọi đúng Resource Server

`InventoryHttpConfiguration.java`:

```java
package com.example.inventorysync.config;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.client.WebClient;

@Configuration(proxyBeanMethods = false)
public class InventoryHttpConfiguration {

    @Bean("inventoryWebClient")
    WebClient inventoryWebClient(
            WebClient.Builder builder,
            @Value("${inventory.api.base-url}") String baseUrl) {

        return builder
            .baseUrl(baseUrl)
            .build();
    }
}
```

Trong ứng dụng có WebClient trên classpath, Spring Boot thường hỗ trợ inject `WebClient.Builder` nếu auto-configuration tương ứng active.

### 13.1. Dùng đúng API base URL

`inventory.api.base-url` phải là **Resource Server được phê duyệt**. Không lấy URL này từ:

- Query parameter của browser.
- Webhook payload chưa kiểm soát.
- OAuth2 token response.
- Bất kỳ `X-Forwarded-Host` inbound nào.
- Tenant metadata không có phê duyệt/allowlist.

Nếu destination do attacker chỉ định, Bearer token có thể bị gửi tới một host ngoài ý muốn.

### 13.2. Không cấu hình default bearer token trên shared WebClient

Sai:

```java
// Không dùng trong singleton/shared WebClient:
WebClient.builder()
    .defaultHeader("Authorization", "Bearer " + someToken)
    .build();
```

Một token được đặt từ lần chạy trước có thể hết hạn hoặc bị dùng sai khi client được tái sử dụng cho API khác.

Ta sẽ gắn token **cho từng request** ngay sau khi manager trả authorized client phù hợp.

## 14. DTO cho JSON Inventory API

`InventorySnapshot.java`:

```java
package com.example.inventorysync.client;

import java.util.List;

public record InventorySnapshot(
        List<InventoryItem> items) {

    public record InventoryItem(
            String sku,
            int available
    ) {}
}
```

Ví dụ response:

```json
{
  "items": [
    {"sku": "SKU-001", "available": 25},
    {"sku": "SKU-002", "available": 0}
  ]
}
```

Jackson được Spring Boot starter hỗ trợ trong project minh họa. Với production, cần thêm validation schema, giới hạn payload, khả năng pagination và kiểm tra dữ liệu nghiệp vụ trước khi ghi DB.

### 14.1. DTO không nên chứa Access Token

Token chỉ phục vụ HTTP Authorization header khi gọi API, không phải field của InventorySnapshot. Không expose token ra logs, JSON response hoặc database nghiệp vụ.

## 15. Client lấy token và gọi API

`InventoryApiClient.java`:

```java
package com.example.inventorysync.client;

import java.time.Duration;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;

@Component
public class InventoryApiClient {

    private static final String REGISTRATION_ID =
        "inventory-job";

    private static final String TECHNICAL_PRINCIPAL =
        "job:inventory-sync";

    private static final Duration API_TIMEOUT =
        Duration.ofSeconds(20);

    private final OAuth2AuthorizedClientManager manager;
    private final WebClient webClient;

    public InventoryApiClient(
            @Qualifier("jobAuthorizedClientManager")
            OAuth2AuthorizedClientManager manager,
            @Qualifier("inventoryWebClient")
            WebClient webClient) {

        this.manager = manager;
        this.webClient = webClient;
    }

    public InventorySnapshot fetchSnapshot() {

        OAuth2AuthorizeRequest authorizeRequest =
            OAuth2AuthorizeRequest
                .withClientRegistrationId(REGISTRATION_ID)
                .principal(TECHNICAL_PRINCIPAL)
                .build();

        OAuth2AuthorizedClient authorizedClient =
            manager.authorize(authorizeRequest);

        if (authorizedClient == null) {
            throw new IllegalStateException(
                "No authorized client for inventory job"
            );
        }

        String token =
            authorizedClient.getAccessToken().getTokenValue();

        InventorySnapshot response =
            webClient.get()
                .uri("/v1/inventory/snapshot")
                .headers(headers ->
                    headers.setBearerAuth(token)
                )
                .retrieve()
                .bodyToMono(InventorySnapshot.class)
                .block(API_TIMEOUT);

        if (response == null) {
            throw new IllegalStateException(
                "Inventory API returned an empty body"
            );
        }

        return response;
    }
}
```

Đây là lõi của bài thực hành.

### 15.1. Giải thích từng bước

1. Tạo `OAuth2AuthorizeRequest` với registration cố định.
2. Cung cấp technical principal ổn định.
3. Gọi service-backed manager để lấy authorized client hợp lệ.
4. Nếu manager không thể authorize, báo lỗi tường minh.
5. Lấy Access Token **chỉ trong phạm vi method**.
6. Đặt header `Authorization: Bearer ...` cho đúng API request.
7. Parse JSON thành DTO.
8. Giới hạn thời gian chờ API.
9. Không log token hoặc đưa token vào response.

### 15.2. Vì sao gọi `block(...)` ở đây?

`WebClient` trả reactive `Mono` nhưng `@Scheduled` trong ví dụ là **synchronous Java method**, chạy trong thread của scheduler. Blocking ở ranh giới này giúp ví dụ thực hành dễ hiểu và có timeout.

**Không gọi `block()` trực tiếp trong Reactor Netty event-loop hoặc trong một reactive security/request pipeline.** Nếu job được thiết kế fully reactive, trả/combine `Mono` đúng lifecycle hoặc subscribe ở một orchestrator/scheduler được quản lý phù hợp thay vì blocking event loop.

### 15.3. Timeout ở tầng API khác timeout ở tầng token

`block(Duration.ofSeconds(20))` giới hạn thời gian chờ reactive HTTP body ở đoạn API call. Nó **không bao trùm token request đồng bộ** xảy ra trước đó trong `manager.authorize(...)`.

Trong production phải cấu hình:

- HTTP connection timeout.
- Response/read timeout của token client.
- WebClient connect/response timeout.
- Job execution budget.
- Scheduler shutdown behavior.
- API retries có giới hạn.

Không coi một `block(Duration)` là timeout cho toàn bộ authorization pipeline.

### 15.4. Nếu API trả 204 No Content

Ví dụ coi body rỗng là lỗi vì hợp đồng API yêu cầu JSON. Với endpoint hợp lệ trả 204, nên thiết kế method trả `Mono<Void>`/`ResponseEntity` hoặc một response type khác, không dùng kiểm tra null như một quy tắc chung.

### 15.5. Không tự đổi token theo mỗi HTTP request

Chỉ gọi `manager.authorize(...)` mỗi lần cần token; **manager/provider quyết định** có cần lấy token mới hay không. Tự POST token endpoint ở đầu mọi job sẽ bỏ qua lợi ích của authorized client store.

## 16. Job được lập lịch

`InventorySyncJob.java`:

```java
package com.example.inventorysync.job;

import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import com.example.inventorysync.client.InventoryApiClient;
import com.example.inventorysync.client.InventorySnapshot;

@Component
public class InventorySyncJob {

    private static final Logger log =
        LoggerFactory.getLogger(InventorySyncJob.class);

    private final InventoryApiClient client;

    public InventorySyncJob(InventoryApiClient client) {
        this.client = client;
    }

    @Scheduled(
        initialDelayString =
            "${inventory.sync.initial-delay-ms:10000}",
        fixedDelayString =
            "${inventory.sync.fixed-delay-ms:300000}"
    )
    public void run() {

        InventorySnapshot snapshot = client.fetchSnapshot();

        List<InventorySnapshot.InventoryItem> items =
            snapshot.items() == null
                ? List.of()
                : snapshot.items();

        // Phần demo: xác nhận nhận được dữ liệu.
        // Production: validate và ghi idempotent vào DB.
        log.info(
            "inventory_sync_completed itemCount={}",
            items.size()
        );
    }
}
```

Khi ứng dụng khởi động, scheduling infrastructure sẽ gọi `run()` sau initial delay và tiếp tục theo fixed delay.

### 16.1. Vì sao không catch exception rồi bỏ qua?

Một đoạn như:

```java
try {
    client.fetchSnapshot();
} catch (Exception ignored) {
    // Không làm gì
}
```

che hết lỗi. Trong job production cần:

- Đưa failure vào metrics/alerts.
- Ghi error code/loại sự cố **không chứa token**.
- Quyết định retry hoặc chờ lần chạy tiếp theo.
- Không đánh dấu đồng bộ thành công khi dữ liệu chưa được ghi.
- Giữ khả năng truy vết bằng correlation ID.

Spring scheduling có error handling mặc định tùy cấu hình/version; không chỉ dựa vào console stack trace cho production monitoring.

### 16.2. Phần đồng bộ DB cần idempotent

Nếu một lần chạy bị retry hoặc có hai replicas chạy trùng, ghi dữ liệu phải tránh nhân đôi.

Ví dụ về các lựa chọn:

- Upsert theo `sku` + tenant/source.
- Dùng version/updatedAt của nguồn khi có.
- So sánh checkpoint hoặc snapshot ID.
- Transaction cho các đơn vị dữ liệu cần atomicity.
- Không tăng tồn kho bằng phép cộng mù khi API trả **giá trị tồn kho tuyệt đối**.
- Có chính sách xử lý delete/missing SKU.

Bài tập trọng tâm OAuth2 nên phần DB được giữ ở extension riêng để tránh che kiến trúc token.

## 17. Bảo vệ HTTP endpoints của worker

Do demo dùng `starter-web`, ứng dụng có thể mở HTTP server. Tuy job không yêu cầu login browser, ta không nên vô tình expose application endpoints.

Một security chain minh họa:

```java
package com.example.inventorysync.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class EndpointSecurityConfiguration {

    @Bean
    SecurityFilterChain workerEndpoints(
            HttpSecurity http) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .anyRequest().denyAll()
            )
            .build();
    }
}
```

Đây là **policy tối giản để demo**: chỉ health endpoint được phép, mọi HTTP route khác bị từ chối.

Trong production còn cần đặt actuator/management exposure, reverse proxy, network ACL và authentication cho các management endpoints nhạy cảm. `permitAll()` trên `/actuator/health` không có nghĩa công khai mọi health details ngoài mong muốn.

### 17.1. Vì sao không bật `oauth2Login()`?

Worker không có user browser. Việc bật browser OAuth2 Login chỉ để có Spring Security OAuth2 Client có thể khiến anonymous requests redirect tới OP mà không có nhu cầu.

`OAuth2AuthorizedClientManager` và `ClientRegistrationRepository` không đòi browser login để dùng client credentials.

### 17.2. HTTP security chain khác outbound OAuth2

`SecurityFilterChain` xử lý **HTTP inbound**. Manager và WebClient xử lý **outbound OAuth2 token và API requests**.

Không nhầm:

```text
anyRequest().denyAll()
```

với việc cấm Spring Boot gọi token endpoint/API outbound. Hai ranh giới khác nhau.

### 17.3. Worker không web

Nếu biến worker thành headless, có thể bỏ Servlet server hoàn toàn. Khi đó cần tự xem lại auto-configuration beans, scheduling lifecycle, health/status reporting và cách vận hành. Đừng giữ một HTTP server chỉ vì muốn có `ClientRegistrationRepository` nếu bạn có thể cấu hình repository rõ ràng cho headless architecture.

## 18. Luồng chạy lần đầu

Lần chạy đầu:

```text
(1) @Scheduled kích hoạt
    |
(2) manager.authorize(inventory-job, job:inventory-sync)
    |
(3) AuthorizedClientService chưa có authorized client
    |
(4) provider clientCredentials gọi AS token endpoint
    |
(5) AS xác thực client-id/client-secret và cấp scope
    |
(6) manager lưu OAuth2AuthorizedClient vào service
    |
(7) InventoryApiClient gọi Inventory API với Access Token
    |
(8) API trả dữ liệu
    |
(9) Job xử lý dữ liệu và ghi metrics/log metadata
```

Đây là hành vi mong đợi khi mọi thành phần đã được cấu hình và AS/RS khả dụng.

### 18.1. Không có Refresh Token trong luồng chuẩn

Client Credentials token response thường không có `refresh_token`. Khi token hết hạn, client dùng client credentials để xin Access Token mới. Vì vậy những thuật ngữ như «refresh token rotation» **không phải trung tâm của bài này**.

### 18.2. Token có thể là JWT hoặc opaque

Client không cần parse JWT để lấy token string gắn vào Bearer header. Resource Server chịu trách nhiệm validate token phù hợp.

Không cho job tự tin một claim `scope` chưa được xác minh bằng cách parse JWT payload base64 rồi coi đó là authorization proof.

## 19. Luồng chạy lần thứ hai: tái sử dụng token

Nếu lần trước đã lưu:

```text
registrationId = inventory-job
principalName = job:inventory-sync
accessToken = token-A
expiresAt = 11:00
```

và job chạy lại lúc 10:05, manager/provider có thể trả authorized client đang có, **không gọi token endpoint thêm** nếu token đủ hiệu lực theo expiry policy.

### 19.1. Kho authorized client giúp gì?

- Giảm số lần xin token không cần thiết.
- Giảm tải Authorization Server.
- Giữ token cùng logical principal/registration.
- Hỗ trợ manager quyết định reauthorization.
- Tạo điểm tập trung cho failure cleanup/observability.
- Có thể chia sẻ giữa instances nếu dùng storage phù hợp.

### 19.2. Không cam kết một token tồn tại đến đúng giây hết hạn

Manager/provider thường xét expiration với **clock skew** để tránh dùng token sát thời điểm hết hạn. Ví dụ token hết hạn 11:00 nhưng job có thể xin token mới trước 11:00 theo skew.

Ngoài ra, Resource Server có thể revoke token trước expiry. Token còn hạn theo timestamp **không đồng nghĩa chắc chắn RS sẽ chấp nhận**.

### 19.3. Cần đo số lần cấp token

Với demo, quan sát test stub token endpoint:

```text
Job run #1: token endpoint calls = 1
Job run #2 (token còn hạn): calls vẫn = 1
Job run #3 (token cần cấp lại): calls tăng
```

Đây là hành vi cần kiểm thử, thay vì chỉ quan sát API luôn trả 200.

## 20. Tại sao không giữ token trong một biến static?

Anti-pattern:

```java
private static String accessToken;
```

và:

```java
if (accessToken == null) {
    accessToken = callTokenEndpointManually();
}
```

Không đáp ứng:

- Token expiry/clock skew.
- Nhiều registrations.
- Isolation theo principal/tenant.
- Concurrent jobs/replicas.
- Refresh/re-authentication failures.
- Storage persistence.
- Cleanup/revocation.
- Token type/scope/expiry metadata.
- Testing rõ ràng.

Hãy dùng `OAuth2AuthorizedClient`/service/manager cho lifecycle phù hợp thay vì tự phát minh token cache.

## 21. So sánh các kho authorized client

| Kho | Ưu điểm | Giới hạn |
|---|---|---|
| `InMemoryOAuth2AuthorizedClientService` | Dễ cấu hình, nhanh, test/local tốt. | Mất khi restart, mỗi replica có cache riêng. |
| JDBC-backed service | Dữ liệu có thể bền qua restart, chia sẻ giữa replicas. | Cần schema, DB ACL/encryption, xử lý đồng thời. |
| Custom Redis-backed service | TTL/cache/distributed access linh hoạt. | Phải tự định nghĩa serialization, consistency, key/secret protection. |
| Custom encrypted store/KMS | Kiểm soát lưu credential theo policy tổ chức. | Phức tạp hơn, cần thiết kế key rotation/availability. |
| Không lưu token, xin lại mỗi lần | Đơn giản cho job rất hiếm. | Tăng token endpoint calls và có thể bị rate limit. |

**Không có lựa chọn duy nhất tốt nhất cho mọi hệ thống.** Một job chạy mỗi ngày có client credentials, nhận token ngắn hạn và chỉ một instance có thể không cần kho bền vững. Một nền tảng nhiều services/pods yêu cầu tiết kiệm token requests có thể cần shared store.

### 21.1. Không nhầm session repository với service repository

`OAuth2AuthorizedClientRepository` ở Servlet thường gắn với HTTP request/response và có thể dùng HttpSession.

`OAuth2AuthorizedClientService` lưu theo registration/principal name mà không đòi Servlet request.

Với scheduled job, service-backed manager phù hợp hơn.

## 22. Dùng JDBC Authorized Client Service

Spring Security có implementation **`JdbcOAuth2AuthorizedClientService`** trong các dòng phiên bản hỗ trợ.

Ví dụ Bean thay thế in-memory store:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcOperations;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Bean
OAuth2AuthorizedClientService authorizedClientService(
        JdbcOperations jdbc,
        ClientRegistrationRepository registrations) {

    return new JdbcOAuth2AuthorizedClientService(
        jdbc,
        registrations
    );
}
```

**Thay thế**, không giữ đồng thời Bean `authorizedClientService` in-memory trong mục 9 nếu không chủ động quản lý qualifiers/primary.

### 22.1. Những việc cần bổ sung

- `spring-boot-starter-jdbc` hoặc dependencies JDBC phù hợp.
- DataSource với credentials được quản lý bảo mật.
- Schema theo **SQL scripts của đúng Spring Security version và database dialect**.
- Migration tool như Flyway/Liquibase nếu tổ chức dùng.
- Transaction/locking và lỗi kết nối.
- Database backup/encryption/retention.
- Quyền DB tối thiểu cho service account.
- Cơ chế xử lý token cũ khi client registration hoặc principal key thay đổi.

**Đừng giả định Boot tự tạo bảng OAuth2 authorized client chỉ vì thêm `JdbcOAuth2AuthorizedClientService`.**

### 22.2. Authorized client store chứa credential nhạy cảm

Access Token là bearer credential. Nếu AS cấp Refresh Token trong trường hợp mở rộng riêng, độ nhạy có thể còn cao hơn.

Kho DB, snapshots, replicas, exports và admin consoles đều phải được bảo vệ. Encryption at rest ở storage layer hữu ích, nhưng không ngăn người có quyền query database đọc token plaintext; nếu threat model yêu cầu, cần encryption ở tầng ứng dụng/KMS và key access isolation.

### 22.3. Không tạo bảng theo trí nhớ

Schema JDBC service có thể thay đổi theo version/dialect. Dùng schema chính thức tương ứng và test migration, thay vì copy một câu lệnh CREATE TABLE từ phiên bản khác.

### 22.4. Khi đổi registration ID

Store có thể giữ records keyed bằng `inventory-job`. Nếu sau upgrade đổi thành `inventory-scheduler`, những records cũ không tự được tìm thấy.

Khi muốn đổi key, chọn chiến lược migration rõ ràng hoặc chấp nhận xin token mới và cleanup records cũ theo policy.

## 23. Redis/custom store khi có nhiều replicas

Một implementation custom `OAuth2AuthorizedClientService` có thể lưu authorized client ở Redis. Khi làm vậy phải xác định:

- Key format: registration ID + technical principal + optional trusted tenant.
- Serialization an toàn, versioned, không phụ thuộc tùy tiện vào Java object serialization.
- TTL liên quan Access Token expiry.
- Atomic update/cas/locking khi concurrent refresh/reissue.
- Quyền Redis, network isolation, TLS và encryption.
- Cleanup khi client bị revoke/secret rotate.
- Backup/retention theo chính sách.
- Test stale data và failover.

### 23.1. Không dùng cache key chỉ theo registration

Nếu một registration được dùng bởi nhiều principals/tenants, key:

```text
inventory-job
```

có thể gây nhầm authorized clients. Dùng key đầy đủ phù hợp `(registrationId,principalName)`, kèm trusted tenant boundary khi cần.

### 23.2. TTL không được làm hỏng manager logic

Nếu store tự xóa record trước khi token expiry, manager sẽ xin token sớm. Điều này có thể chấp nhận nhưng cần biết hiệu quả.

Nếu store giữ record **sau token expiry**, manager/provider vẫn phải phát hiện hết hạn và reauthorize; không tự gắn token cũ chỉ vì record còn trong Redis.

### 23.3. Shared token không tương đương distributed scheduling

Hai pods dùng chung authorized client store **vẫn có thể cùng chạy job đồng bộ tồn kho**. Store chia sẻ token không ngăn double execution nghiệp vụ.

Cần cơ chế orchestration/lock riêng.

## 24. Nhiều replicas và execution overlap

Giả sử triển khai ba replicas:

```text
Kubernetes deployment
  ├── pod A: @Scheduled InventorySyncJob
  ├── pod B: @Scheduled InventorySyncJob
  └── pod C: @Scheduled InventorySyncJob
```

Mỗi pod có scheduler riêng. Nếu không có điều phối, mỗi pod có thể chạy cùng một job.

### 24.1. Cách tránh trùng công việc

- Dùng một dedicated worker replica nếu phù hợp.
- Dùng Kubernetes CronJob với concurrency policy thích hợp.
- Dùng distributed lock (DB/Redis/coordination service).
- Dùng queue + consumer-group/lease pattern.
- Thiết kế idempotent upsert để chịu được chạy lại.
- Ghi checkpoint/lock lease và xử lý crash/retry.

### 24.2. Distributed lock không thay token security

Một lock chỉ bảo đảm (theo đặc tính implementation) một worker được thực hiện tác vụ. Nó không kiểm tra Access Token audience/scope, và cũng không phân vùng authorized client store.

### 24.3. Token reissuance race

Nếu ba pods cùng thấy token cần cấp lại:

```text
pod A -> token endpoint -> token-A
pod B -> token endpoint -> token-B
pod C -> token endpoint -> token-C
```

Với `client_credentials`, AS có thể cho nhiều Access Tokens đồng thời; điều này gây tải/rate-limit dù không nhất thiết sai giao thức.

Một shared store và coordination/locking thích hợp có thể giảm thundering herd. Không giả định một JDBC row lock được Spring Security tự cung cấp cho mọi deployment/version.

### 24.4. Vì sao điều này khác Refresh Token Rotation?

Trong browser/delegated client, concurrent refresh có thể gây race vì Refresh Token bị rotate/revoke. Với client credentials thông thường, client xin Access Token mới bằng credential, **không dùng Refresh Token**; race chủ yếu về hiệu quả, rate-limit và state consistency, tùy AS policy.

## 25. Expiration và clock skew

Access Token response có `expires_in`; Spring Security biểu diễn expiry dưới dạng `Instant` trong `OAuth2AccessToken`.

Ví dụ:

```text
issuedAt:  10:00:00
expiresAt: 11:00:00
clockSkew: 60 seconds

Authorize at 10:30 -> token likely reusable
Authorize at 10:59 -> manager/provider may reissue
```

### 25.1. Vì sao reissue trước expiry?

- Chênh đồng hồ giữa client và AS/RS.
- Network latency.
- Xử lý API mất thời gian.
- RS có leeway/validation khác.
- Một request bắt đầu trước expiry nhưng đến RS sau expiry.

Không chờ đến đúng giây hết hạn mới lấy token.

### 25.2. Không tự parse JWT để tính expiry nếu API đã có metadata

`authorizedClient.getAccessToken().getExpiresAt()` là metadata token manager sử dụng. Đừng tự decode JWT rồi tin claims chưa xác minh chỉ để quản lý caching.

### 25.3. Điều chỉnh skew theo API/version

Một số `OAuth2AuthorizedClientProvider` implementations cho phép cấu hình clock skew. Khi cần tùy chỉnh, xem builder/provider API đúng Spring Security version và test behavior.

Không copy một setter chưa tồn tại trong project hoặc thay mọi clocks của app chỉ vì expiry test fail.

## 26. Lỗi ở token endpoint

Token acquisition có thể thất bại do:

| Lỗi | Khả năng | Phản ứng |
|---|---|---|
| `invalid_client` | Client ID/secret/method sai hoặc secret hết hiệu lực. | Kiểm tra client registration và secret rotation, không retry vô hạn. |
| `unauthorized_client` | Grant không được phép. | Xác minh AS registration policy. |
| `invalid_scope` | Scope không có quyền. | Sửa scope contract, không tự cấp scope rộng. |
| HTTP 429 | AS rate limit. | Bounded backoff, giảm token requests, quan sát. |
| HTTP 5xx | AS unavailable. | Retry có giới hạn/circuit breaker, giữ job failure state. |
| TLS/certificate error | Trust/cert/proxy sai. | Khắc phục TLS, không tắt verification. |
| Timeout | AS/network chậm. | Bounded timeout, retry policy và alert. |
| Malformed JSON | Response/protocol mismatch. | Fail closed, log metadata an toàn. |
| Token thiếu expiry hoặc sai token_type | Contract/provider issue. | Xác minh AS behavior với OAuth2 client implementation. |

### 26.1. Không dùng catch-all fallback machine token

Sai:

```java
try {
    return manager.authorize(request);
} catch (Exception ex) {
    return cachedTokenFromAnotherClient;
}
```

Dùng token từ client/tenant khác có thể tạo cross-boundary authorization bug nghiêm trọng.

### 26.2. Không log client secret khi 401

Một số HTTP libraries có debug/wire logging. Khi chẩn đoán `invalid_client`, phải redact Basic Authorization header và form parameters.

### 26.3. Token request không được gửi qua HTTP plaintext

Production cần HTTPS với certificate/hostname validation đúng. Không tắt TLS verification để bypass staging certificate error.

## 27. Lỗi từ Inventory API: 401, 403 và 5xx

Sau khi lấy token, API có thể từ chối request. Phải phân biệt:

| Status | Ý nghĩa thường gặp | Hành động |
|---|---|---|
| **401 Unauthorized** | Token hết hiệu lực, sai token, sai audience/issuer hoặc cần authentication khác. | Kiểm tra `WWW-Authenticate`/error code an toàn; xem xét token eviction/reissue theo policy. |
| **403 Forbidden** | Token được nhận diện nhưng thiếu scope/permission. | Không retry token acquisition vô hạn; kiểm tra AS/RS policy. |
| **429 Too Many Requests** | Rate limit. | Backoff theo header/policy, giới hạn số lần. |
| **500/502/503/504** | Resource Server/gateway lỗi. | Retry bounded nếu request idempotent, alert khi kéo dài. |
| **400** | Request contract không hợp lệ. | Sửa payload/path; không tự xin token mới. |
| **404** | API route/snapshot không tồn tại. | Xác minh version/path; không suy ngay token lỗi. |

### 27.1. API 401 không phải `invalid_client`

`invalid_client` thường là lỗi khi xác thực client tại **token endpoint**. API 401 xảy ra sau đó ở Resource Server.

Không trộn hai trường hợp trong monitoring hoặc retry logic.

### 27.2. Hạn chế retry khi 401

Một hướng xử lý có điều kiện:

1. Nhận 401.
2. Phân loại xem có khả năng token bị revoke/expired hay không.
3. Nếu policy cho phép, xóa authorized client tương ứng **đúng registration + technical principal**.
4. Thử xin token mới ở lần chạy kế tiếp hoặc retry **tối đa một lần**.
5. Nếu vẫn 401, fail và phát alert thay vì lặp vô hạn.

Không tự mặc định xóa mọi tokens của mọi users/registrations khi một API trả 401.

### 27.3. 403 thường không hết khi đổi token

Nếu AS chỉ cấp `inventory.read` và API cần `inventory.write`, xin lại token cùng scope vẫn có thể trả 403.

Cần sửa contract/permission qua quy trình được duyệt, không thêm `inventory.write` tùy tiện nếu job không có nhu cầu.

### 27.4. Không ghi raw body/headers lỗi

API error response đôi khi chứa PII hoặc thông tin nhạy cảm. Logging nên giới hạn:

```text
event=inventory_api_failed
registration=inventory-job
httpStatus=401
operation=snapshot-read
correlationId=<non-secret>
```

không in Bearer token/Basic client secret.

## 28. Loại bỏ authorized client có kiểm soát

`OAuth2AuthorizedClientService` cung cấp:

```java
authorizedClientService.removeAuthorizedClient(
    "inventory-job",
    "job:inventory-sync"
);
```

Có thể dùng khi:

- Client bị thu hồi/revoked.
- API/AS trả lỗi xác nhận authorized client không còn hợp lệ.
- Client registration bị thay hoặc khóa.
- User/system operator yêu cầu invalidation theo policy.
- Token store có record bị hỏng.

### 28.1. Không gọi remove sau mỗi lần thành công

Nếu mỗi run đều xóa record:

```text
authorize -> call API -> remove authorized client
```

thì lần sau không có gì để reuse, mất ý nghĩa cache.

### 28.2. Xóa local record không nhất thiết revoke token tại AS

`removeAuthorizedClient(...)` xóa dữ liệu khỏi store phía ứng dụng. Access Token đã cấp có thể vẫn hợp lệ cho đến expiration hoặc khi bị revoke tại AS.

Nếu chính sách yêu cầu thu hồi token ngay, phải kiểm tra AS hỗ trợ revocation endpoint và quy trình tương ứng.

### 28.3. Không xóa sai technical principal

Nếu token store có nhiều technical principals, chỉ xóa record được xác định đúng. Không dùng key do người dùng nhập để xóa records khác.

## 29. Retry và idempotency

Retry có thể giúp vượt lỗi mạng tạm thời, nhưng phải giới hạn rõ:

- Số lần thử.
- Backoff/jitter.
- Timeout tổng.
- Các status được retry.
- Tính idempotent của HTTP operation.
- Token endpoint rate limit.
- Sự khác biệt giữa 401/403 và 5xx.
- Sự tương tác với scheduler lần chạy kế tiếp.

### 29.1. Đọc snapshot thường dễ retry hơn ghi mutation

`GET /v1/inventory/snapshot` là operation đọc; retry các lỗi kết nối/5xx phù hợp có thể chấp nhận nếu API contract và resource usage cho phép.

`POST /v1/inventory/adjust-stock` có thể tạo side effect, không được retry mù mà thiếu idempotency key hoặc transaction semantics.

### 29.2. Retry token request cần thận trọng

Client Credentials token endpoint có thể phát Access Token mới ở mỗi request. Retry do timeout sau khi AS đã phát token có thể tạo nhiều tokens, tiêu tốn quota.

Do đó phải có bounded retry/backoff, quan sát rate-limit và ưu tiên token reuse.

### 29.3. Không nuốt toàn bộ lỗi rồi báo success

Nếu API lỗi, job không được ghi metric:

```text
inventory_sync_completed=true
```

dù dữ liệu chưa được đồng bộ. Phân biệt `attempted`, `succeeded`, `failed` và `partial`.

## 30. Quan sát job và vòng đời token

Các metrics nên có:

| Metric/event | Mục đích |
|---|---|
| `inventory_sync_started` | Đếm lần bắt đầu theo lịch. |
| `inventory_sync_succeeded` | Job hoàn tất đầy đủ. |
| `inventory_sync_failed` | Job thất bại có phân loại. |
| `inventory_sync_duration` | Tổng thời gian thực hiện. |
| `oauth2_token_acquisition_failed` | Lỗi tại AS/token endpoint. |
| `oauth2_authorized_client_cache_hit` | Nếu có instrumentation phù hợp, phản ánh token reuse. |
| `inventory_api_http_status` | Nhóm response codes từ Resource Server. |
| `inventory_sync_items_processed` | Dữ liệu nghiệp vụ đã xử lý. |
| `inventory_sync_last_success_timestamp` | Phát hiện job bị dừng hoặc chạy trễ. |

### 30.1. Không dùng Access Token làm metric label

Sai:

```text
oauth2_token{token="eyJ..."} = 1
```

Metrics labels có thể lưu rất lâu và phân phối tới nhiều hệ thống. Chỉ dùng registration alias, environment, operation, status/error family và correlation ID an toàn.

### 30.2. Không log raw OAuth2AuthorizedClient

Một số object `toString()`/debuggers có thể biểu diễn token metadata hoặc credential. Không log nguyên object khi production incidents.

### 30.3. Cảnh báo theo SLO

Một job có lịch 5 phút có thể đặt cảnh báo khi không có lần thành công trong khoảng thời gian được thỏa thuận, thay vì cảnh báo ồn ào sau mỗi một lỗi tạm thời. Tuy nhiên, lỗi `invalid_client`/secret revoked có thể cần cảnh báo sớm hơn.

## 31. Phân quyền AS và Resource Server

Một machine token cần đáp ứng cả:

1. Authorization Server nhận diện đúng client.
2. Token được cấp đúng grant và scopes.
3. Resource Server xác minh token.
4. API business policy cho phép client/service truy cập tài nguyên.
5. Chỉ dữ liệu tenant/resource được phép được trả về.

### 31.1. Scope không tự là role người dùng

`inventory.read` là API permission của token. Không biến nó thành `ROLE_ADMIN` của browser login principal.

### 31.2. Audience có thể quan trọng hơn chỉ có scope

Một token có `scope=inventory.read` nhưng `aud=billing-api` không nên được Inventory API chấp nhận. Resource Server phải xác minh audience/resource phù hợp.

Việc yêu cầu audience/resource khi xin token phụ thuộc AS protocol extensions và policy; có thể dùng resource indicators hoặc các tham số đặc thù provider. Không tự thêm một form field `audience` giả định mọi AS đều hỗ trợ.

### 31.3. Least privilege

Dành riêng một client registration chỉ có `inventory.read` sẽ giới hạn blast radius hơn dùng một «super client» với tất cả scopes.

Nếu job cần thêm `inventory.write` trong tương lai, thay đổi qua security review thay vì xin sẵn từ đầu.

### 31.4. Network restrictions bổ trợ OAuth2

Với API nội bộ, có thể thêm private network routing, mTLS, ingress authentication và outbound egress allowlist. Không coi OAuth2 token là lý do bỏ network segmentation.

## 32. Bảo vệ client secret

`client_secret_basic` là một phương thức client authentication, không phải phương pháp che secret khỏi mọi thành phần.

### 32.1. Tránh hardcode trong source

Sai:

```yaml
client-secret: very-real-production-secret
```

Đúng hướng:

```yaml
client-secret: ${INVENTORY_CLIENT_SECRET}
```

Và secret đến từ environment/secret manager được kiểm soát.

### 32.2. Tránh lộ qua command line

Truyền secret trực tiếp trong command line args có thể lộ qua process listing, shell history hoặc CI logs. Ưu tiên secret manager/process environment theo policy, không dùng lệnh chứa plaintext credential khi không cần.

### 32.3. Secret rotation

Khi AS cho phép rotate client secrets:

1. Chuẩn bị secret mới.
2. Đảm bảo AS chấp nhận secret mới theo thời điểm cutover.
3. Cập nhật secret store/deployment.
4. Theo dõi token acquisition success.
5. Thu hồi secret cũ đúng kế hoạch.
6. Xem xét tác động tới authorized clients đang cache.
7. Không dump secret/token vào logs.

Token đang cache có thể vẫn dùng đến expiration theo AS policy, nhưng không nên giả định rotation secret tự thu hồi mọi Access Tokens đã cấp.

### 32.4. Secretless alternatives

Nếu hạ tầng hỗ trợ, có thể cân nhắc mTLS, workload identity federation hoặc private key JWT theo AS support/policy để giảm phụ thuộc static shared secret.

Đây là lựa chọn thiết kế riêng; không đổi authentication method bằng code mà không thay registration/AS contract.

## 33. Kiểm thử lớp API client không cần Authorization Server thật

Ta có thể unit-test `InventoryApiClient` bằng:

- Mock `OAuth2AuthorizedClientManager` để trả fixture authorized client.
- Một WebClient có `ExchangeFunction` giả lập.
- Assertion token đúng header và request đúng destination.
- Không mở HTTP socket.
- Không sử dụng credential thật.

### 33.1. Tạo fixture `ClientRegistration` và `OAuth2AuthorizedClient`

```java
import java.time.Instant;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;
import org.springframework.security.oauth2.core.OAuth2AccessToken;

ClientRegistration registration =
    ClientRegistration.withRegistrationId("inventory-job")
        .clientId("synthetic-test-client")
        .clientSecret("synthetic-test-secret")
        .authorizationGrantType(
            AuthorizationGrantType.CLIENT_CREDENTIALS
        )
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.CLIENT_SECRET_BASIC
        )
        .tokenUri("https://auth.example.test/oauth2/token")
        .scope("inventory.read")
        .build();

OAuth2AccessToken token = new OAuth2AccessToken(
    OAuth2AccessToken.TokenType.BEARER,
    "synthetic-access-token",
    Instant.parse("2026-01-01T00:00:00Z"),
    Instant.parse("2030-01-01T00:00:00Z")
);

OAuth2AuthorizedClient authorizedClient =
    new OAuth2AuthorizedClient(
        registration,
        "job:inventory-sync",
        token
    );
```

Fixture này **không gọi token endpoint** và không xác minh JWT; nó chỉ biểu diễn một authorized client mà manager có thể trả.

### 33.2. Test đầy đủ header và response

```java
package com.example.inventorysync;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.time.Instant;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.OAuth2AccessToken;
import org.springframework.web.reactive.function.client.ClientResponse;
import org.springframework.web.reactive.function.client.ExchangeFunction;
import org.springframework.web.reactive.function.client.WebClient;

import com.example.inventorysync.client.InventoryApiClient;

import reactor.core.publisher.Mono;

class InventoryApiClientTest {

    @Test
    void usesMachineTokenOnlyForApprovedInventoryApi() {

        ClientRegistration registration =
            ClientRegistration
                .withRegistrationId("inventory-job")
                .clientId("test-client")
                .clientSecret("synthetic-secret")
                .authorizationGrantType(
                    AuthorizationGrantType.CLIENT_CREDENTIALS
                )
                .tokenUri("https://auth.example.test/token")
                .build();

        OAuth2AccessToken token = new OAuth2AccessToken(
            OAuth2AccessToken.TokenType.BEARER,
            "fixture-access-token",
            Instant.parse("2026-01-01T00:00:00Z"),
            Instant.parse("2030-01-01T00:00:00Z")
        );

        OAuth2AuthorizedClient client =
            new OAuth2AuthorizedClient(
                registration,
                "job:inventory-sync",
                token
            );

        OAuth2AuthorizedClientManager manager =
            mock(OAuth2AuthorizedClientManager.class);

        when(manager.authorize(
            any(OAuth2AuthorizeRequest.class)
        )).thenReturn(client);

        ExchangeFunction fakeTransport = request -> {
            assertThat(request.url().toString()).isEqualTo(
                "https://api.example.test/v1/inventory/snapshot"
            );

            assertThat(request.headers().getFirst(
                HttpHeaders.AUTHORIZATION
            )).isEqualTo("Bearer fixture-access-token");

            return Mono.just(
                ClientResponse.create(HttpStatus.OK)
                    .header(
                        HttpHeaders.CONTENT_TYPE,
                        MediaType.APPLICATION_JSON_VALUE
                    )
                    .body(
                        "{\"items\":["
                        + "{\"sku\":\"SKU-001\",\"available\":25}"
                        + "]}"
                    )
                    .build()
            );
        };

        WebClient webClient = WebClient.builder()
            .baseUrl("https://api.example.test")
            .exchangeFunction(fakeTransport)
            .build();

        InventoryApiClient api =
            new InventoryApiClient(manager, webClient);

        var snapshot = api.fetchSnapshot();

        assertThat(snapshot.items()).hasSize(1);
        assertThat(snapshot.items().get(0).sku())
            .isEqualTo("SKU-001");
    }
}
```

Đây là một **unit test cô lập**: chứng minh code lấy authorized client từ manager, gắn đúng token và nhận JSON từ HTTP client abstraction.

### 33.3. Test này chưa chứng minh điều gì?

- AS đã cấp token thật.
- `client_credentials` request gửi đúng `grant_type`.
- Manager tái sử dụng token từ store.
- Token audience/scope được Resource Server thật chấp nhận.
- HTTP TLS/certificate tới AS/API đúng.
- Token endpoint có xử lý lỗi đúng.
- Distributed storage và scheduler concurrency.

Các phần đó cần tests ở ranh giới khác.

### 33.4. Test principal và registration parameters

Có thể dùng Mockito `ArgumentCaptor<OAuth2AuthorizeRequest>`:

```java
var captor =
    ArgumentCaptor.forClass(OAuth2AuthorizeRequest.class);

verify(manager).authorize(captor.capture());

assertThat(captor.getValue().getClientRegistrationId())
    .isEqualTo("inventory-job");

assertThat(captor.getValue().getPrincipal().getName())
    .isEqualTo("job:inventory-sync");
```

Đảm bảo technical principal **không đổi theo mỗi lần chạy**.

## 34. Test khi manager không trả authorized client

Một negative test nên tạo:

```java
when(manager.authorize(
    any(OAuth2AuthorizeRequest.class)
)).thenReturn(null);
```

Sau đó:

```java
assertThatThrownBy(api::fetchSnapshot)
    .isInstanceOf(IllegalStateException.class)
    .hasMessageContaining("No authorized client");
```

Điều này kiểm tra **fail closed**: không có token thì **không gọi API bằng session cookie của người dùng khác** hoặc gắn bearer header rỗng.

### 34.1. Không fallback sang access token cuối cùng

Nếu manager trả null, không giữ một static token từ request trước hoặc token thuộc registration khác để «cứ thử».

### 34.2. Không trả secret trong exception message

Nên thông báo registration alias/job operation, không đưa token string/client secret vào message/stack trace.

## 35. Test tái sử dụng token trong kho authorized client

Để kiểm tra manager/store, không cần gọi AS production. Có thể tạo một **fake `OAuth2AuthorizedClientProvider`** trả token mới khi chưa có authorized client:

```java
import java.time.Instant;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.security.oauth2.client.*;
import org.springframework.security.oauth2.client.registration.*;
import org.springframework.security.oauth2.core.*;

ClientRegistration registration =
    ClientRegistration.withRegistrationId("inventory-job")
        .clientId("test-client")
        .clientSecret("test-secret")
        .authorizationGrantType(
            AuthorizationGrantType.CLIENT_CREDENTIALS
        )
        .tokenUri("https://auth.example.test/token")
        .build();

ClientRegistrationRepository registrations =
    new InMemoryClientRegistrationRepository(registration);

OAuth2AuthorizedClientService store =
    new InMemoryOAuth2AuthorizedClientService(registrations);

AtomicInteger grants = new AtomicInteger();

OAuth2AuthorizedClientProvider fakeProvider = context -> {
    OAuth2AuthorizedClient old =
        context.getAuthorizedClient();

    if (old != null &&
        old.getAccessToken().getExpiresAt()
            .isAfter(Instant.now().plusSeconds(60))) {
        return null;
    }

    grants.incrementAndGet();

    var token = new OAuth2AccessToken(
        OAuth2AccessToken.TokenType.BEARER,
        "token-fixture-" + grants.get(),
        Instant.now(),
        Instant.now().plusSeconds(3600)
    );

    return new OAuth2AuthorizedClient(
        context.getClientRegistration(),
        context.getPrincipal().getName(),
        token
    );
};

var manager =
    new AuthorizedClientServiceOAuth2AuthorizedClientManager(
        registrations,
        store
    );

manager.setAuthorizedClientProvider(fakeProvider);

var request = OAuth2AuthorizeRequest
    .withClientRegistrationId("inventory-job")
    .principal("job:inventory-sync")
    .build();

var first = manager.authorize(request);
var second = manager.authorize(request);

assertThat(first).isNotNull();
assertThat(second).isNotNull();
assertThat(grants.get()).isEqualTo(1);
```

Đây là **test fragment** cần JUnit/AssertJ imports và setup tương ứng. Fake provider không gửi HTTP mà thể hiện chính sách "token còn hạn thì không cần cấp mới".

### 35.1. Test này giúp thấy sự khác biệt nào?

- Authorized client được lưu theo registration/principal.
- Lần thứ hai manager có thể load client đã lưu.
- Provider fake không phát token mới nếu token đủ hạn.
- Việc thay technical principal sẽ đổi storage key.

### 35.2. Nó không chứng minh token HTTP exchange thật

Fake provider bỏ qua việc gửi `grant_type=client_credentials` và client authentication. Cần thêm **integration test với token endpoint stub** nếu muốn kiểm tra serialization/authentication method.

### 35.3. Token expiry test cần thời gian kiểm soát

Để test hết hạn có thể cấp token fixture hết hạn hoặc inject `Clock` trong fake provider. Tránh phụ thuộc thời điểm thực trong assertion khiến test flaky.

## 36. Integration test với Authorization Server stub

Một bài thực hành nghiêm túc cần kiểm tra HTTP boundary mà không gọi production OP/AS.

Có thể dùng một mock HTTP server chạy localhost với dynamic port (ví dụ WireMock, MockWebServer hoặc một server test khác) có hợp đồng:

```text
POST http://127.0.0.1:<dynamic-port>/oauth2/token

Content-Type: application/x-www-form-urlencoded
Authorization: Basic <synthetic-client-credentials>

Body:
  grant_type=client_credentials
  scope=inventory.read
```

Stub response:

```json
{
  "access_token": "stub-inventory-token",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "inventory.read"
}
```

Cấu hình registration test trỏ tới dynamic token URL đã tạo. Sau đó gọi manager:

```java
var authorized = manager.authorize(
    OAuth2AuthorizeRequest
        .withClientRegistrationId("inventory-job")
        .principal("job:inventory-sync")
        .build()
);
```

Và assert:

- HTTP token request có `grant_type=client_credentials`.
- Client credentials được gửi qua phương thức AS test hỗ trợ.
- Scope chính xác.
- Không có browser/authorization code redirect.
- Authorized client lưu vào đúng service.
- Access Token có expiry metadata.
- Lần authorize thứ hai khi token còn hiệu lực không gọi token endpoint ngoài dự kiến.

### 36.1. Vì sao cần stub thay AS thật?

- Không dùng client secret thật.
- Không phụ thuộc Internet, MFA hoặc token quota của production.
- Tạo lỗi `invalid_client`, 429, 5xx deterministic.
- Kiểm tra count số token requests.
- Kiểm soát `expires_in` và response format.
- CI có thể chạy offline.

### 36.2. Đừng hardcode port test

Nếu chạy song song trên CI, port cố định dễ conflict. Stub nên bind localhost và lấy port do OS cấp.

### 36.3. Token client implementation có thể đổi theo version

Spring Security có các implementations để gửi Client Credentials token request bằng HTTP; extension points có thể thay đổi theo release line. Khi muốn thay HTTP client, timeout, proxy hoặc mTLS, dùng APIs đúng Spring Security version.

Không tự giả định một class `Default...TokenResponseClient` là API duy nhất cho mọi major version.

## 37. Integration test với Resource Server stub

Tiếp theo, đặt Inventory API stub:

```http
GET /v1/inventory/snapshot HTTP/1.1
Authorization: Bearer stub-inventory-token
```

Trả:

```json
{
  "items": [
    {"sku": "SKU-001", "available": 25}
  ]
}
```

Kiểm tra:

- URL phải là **API host được duyệt**.
- Đúng Authorization Bearer header.
- Không có client secret hoặc Refresh Token trong request.
- 200 JSON được parse đúng.
- 401/403/429/503 được phân loại.
- Không tự follow redirect tới host không tin cậy kèm token.
- Không công bố raw token qua logging.

### 37.1. Cần test request sang host khác

Nếu service vô tình nhận absolute URL do input chi phối, phải xác minh không thể gửi Bearer Token tới host không được duyệt. Có thể dùng client API chỉ nhận relative paths, fixed base URL và outbound destination allowlist.

### 37.2. Một stub không thay Resource Server validation

Stub có thể chấp nhận bất kỳ Bearer token fixture nào. Test token signature/audience/scope cần kiểm tra Resource Server JWT/introspection layer riêng.

## 38. Tại sao không dùng `@WithMockUser` hoặc `oidcLogin()`?

Các helper như:

```java
@WithMockUser
```

và:

```java
mockMvc.perform(get("/account")
    .with(oidcLogin()));
```

phục vụ **mô phỏng authentication trong một HTTP request**.

Job client credentials **không có browser login principal**. Dùng mock user để test job dễ che lỗi kiến trúc, vì code có thể vô tình phụ thuộc `SecurityContextHolder` hoặc token của người dùng.

Test nên gọi trực tiếp:

```java
inventoryApiClient.fetchSnapshot();
```

với fake manager/store/HTTP boundary.

### 38.1. Nếu job chạy từ một endpoint admin

Có hệ thống cho admin nhấn «Run now». Request của admin có authentication để cho phép kích hoạt job, nhưng **token mà job dùng để gọi M2M API vẫn là machine token** nếu contract của API yêu cầu machine auth.

Cần tách:

```text
Inbound: admin authenticated + authorized to start job
Outbound: job's client_credentials token
```

Không tự dùng token của admin cho background job chỉ vì request kích hoạt có SecurityContext.

## 39. Reactive variant: không dùng Servlet manager

Nếu worker được viết bằng Reactor/WebFlux hoàn toàn, cân nhắc:

- `ReactiveClientRegistrationRepository`.
- `ReactiveOAuth2AuthorizedClientService`.
- `ReactiveOAuth2AuthorizedClientManager` phù hợp.
- `ReactiveOAuth2AuthorizedClientProvider` với Client Credentials.
- Reactor `Mono<OAuth2AuthorizedClient>` và `WebClient`.

Ví dụ conceptual:

```java
ReactiveOAuth2AuthorizeRequest authorizeRequest =
    ReactiveOAuth2AuthorizeRequest
        .withClientRegistrationId("inventory-job")
        .principal("job:inventory-sync")
        .build();
```

**Chú ý:** API request class thực tế của reactive manager vẫn là `OAuth2AuthorizeRequest` theo những Spring Security versions phổ biến, còn manager trả `Mono<OAuth2AuthorizedClient>`. Không copy đoạn conceptual trên như code chạy mà chưa đối chiếu API của version; dưới đây là mẫu dùng type contract đúng hơn:

```java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("inventory-job")
        .principal("job:inventory-sync")
        .build();

Mono<OAuth2AuthorizedClient> result =
    reactiveAuthorizedClientManager.authorize(request);
```

Trong Spring Security Reactive, wiring repository/service/provider khác Servlet. Không dùng `DefaultOAuth2AuthorizedClientManager` và không `block()` trong reactive event loop.

### 39.1. Vì sao khác tên nhưng giống ý tưởng?

Dù stack khác nhau, logical key `(registrationId, principalName)`, token grant và isolation vẫn tương tự. Điểm khác là lifecycle/cancellation/context và reactive storage.

### 39.2. Kiểm thử bằng StepVerifier

```java
StepVerifier.create(
    reactiveAuthorizedClientManager.authorize(request)
)
.assertNext(client -> {
    assertThat(client.getClientRegistration()
        .getRegistrationId()).isEqualTo("inventory-job");
})
.verifyComplete();
```

Đây là fragment cần reactive manager Bean và fixture phù hợp. Không coi StepVerifier chạy trên fake manager là bằng chứng token endpoint HTTP thật đã được gọi.

## 40. Không gửi credential vào URL, logs hoặc exception

### 40.1. Những nơi tuyệt đối tránh

Không đặt:

```text
https://api.example.test/snapshot?access_token=...
https://auth.example.test/token?client_secret=...
```

Query string dễ rơi vào access logs, browser history, tracing hoặc Referer.

### 40.2. Không ghi HTTP wiretap mặc định trên production

Reactor Netty wiretap hoặc HTTP client debugging có thể ghi headers/body tùy cấu hình. Cần redaction cho:

- `Authorization`.
- `Proxy-Authorization`.
- `Cookie`/`Set-Cookie`.
- `client_secret`.
- `access_token`/`refresh_token`.
- Token responses.
- Sensitive API payloads.

### 40.3. Logging metadata an toàn

Ví dụ:

```text
event=inventory_sync_token_error
registrationId=inventory-job
grantType=client_credentials
errorCode=invalid_client
environment=staging
correlationId=job-run-opaque-id
```

Không ghi `OAuth2AuthorizedClient` object hoặc raw exception response body nếu nó có thể chứa credential.

## 41. Resource isolation và multi-tenant

Một hệ thống có thể chạy job cho:

```text
tenant alpha -> inventory-alpha client
tenant beta  -> inventory-beta client
```

Nếu mọi tenant dùng chung:

```text
registrationId = inventory-job
principal = job:inventory-sync
```

nhưng token được phát cho từng tenant khác nhau, có nguy cơ lưu/tái sử dụng sai token.

### 41.1. Hai chiến lược rõ ràng

**Chiến lược A — registration riêng:**

```text
inventory-alpha
inventory-beta
```

Mỗi registration có client credentials/AS policy riêng.

**Chiến lược B — cùng registration, isolation theo trusted principal/tenant:**

```text
registrationId = inventory-job
principal = job:inventory-sync:tenant-alpha
principal = job:inventory-sync:tenant-beta
```

Chỉ phù hợp khi AS/RS thực sự cấp token theo tenant context đáng tin và application kiểm soát mapping. Thay principal name **không tự đổi token audience/scope**; nếu dùng cùng client credentials và không thêm authorization semantics, hai tokens có thể có cùng quyền.

### 41.2. Không trust tenant ID từ input

Tenant/registration mapping phải đến từ catalog/internal authorization policy, không từ query parameter hoặc header tùy ý.

### 41.3. Avoid global default authorized client

Một client OAuth2 filter tự chọn token mặc định cho mọi request có thể gửi token tenant A tới API tenant B.

Trong bài, explicit registration + technical principal + fixed API base URL giảm rủi ro đó.

## 42. Job credentials và principle of least privilege

Các kiểm soát nên có:

1. Dedicated client ID cho inventory sync.
2. Chỉ grant `client_credentials` nếu không cần login tương tác.
3. Scope chỉ đọc tồn kho khi mục tiêu chỉ đọc.
4. Token audience dành riêng Inventory API khi AS hỗ trợ.
5. Expiry đủ ngắn theo policy.
6. AS rate limiting/bounded retries.
7. Không cấp admin roles của ứng dụng web.
8. Bảo vệ client secret bằng secret manager.
9. TLS/mTLS và destination allowlist.
10. Kho authorized client bảo vệ credential và không trộn tenants.
11. Audit/alert không log raw token.
12. Tách environments và service accounts.
13. Revoke/rotate credential khi job bị compromise.
14. Chỉ API endpoints đã được phê duyệt mới chấp nhận machine token.

### 42.1. Không cấp quyền theo tên principal trong store

`"job:inventory-sync"` là key phía client. Nó **không phải claim đã được Resource Server xác minh**.

Không viết Resource Server rule «nếu token đến từ job có string principal đúng thì là admin» khi token không chứa authority verified tương ứng.

### 42.2. AS service identity có thể khác technical principal

Authorization Server có thể biểu diễn client ID trong token bằng `client_id`, `sub`, `azp` hoặc claim khác tùy token profile/provider. Đừng mặc định tên principal Spring store xuất hiện trong JWT.

## 43. Triển khai bằng Kubernetes CronJob

Với công việc chỉ chạy theo lịch, một kiến trúc thay `@Scheduled` có thể là **Kubernetes CronJob** tạo một process/job run theo lịch.

Ưu điểm:

- Schedule thuộc control plane.
- Có concurrency policy.
- Có job history.
- Có thể chạy image worker không web.
- Không cần mỗi replica ứng dụng luôn có scheduler.

Tuy nhiên, cần cân nhắc:

- Mỗi CronJob execution thường khởi động process mới, nên in-memory authorized client **không tồn tại qua runs**.
- Một shared store chỉ hữu ích nếu giảm token requests hoặc phục vụ coordination policy.
- Nếu token có lifetime ngắn hơn khoảng cách giữa jobs, cache bền vững có thể không mang lại lợi ích lớn.
- Bảo vệ secrets/network/pod identity vẫn cần.
- Phải xử lý concurrency khi schedule overlap hoặc job bị retry.

### 43.1. Chọn scheduler ở đâu?

| Cách | Khi phù hợp |
|---|---|
| Spring `@Scheduled` trong một worker process | Service chạy liên tục, lịch đơn giản. |
| Kubernetes CronJob | Job theo thời điểm, container có thể tạo/hủy mỗi lần. |
| Queue + workers | Công việc lớn, nhiều partitions, cần durable retries. |
| Workflow orchestrator | Nhiều bước/điều kiện/approvals/dependencies. |

Chọn theo yêu cầu vận hành; cơ chế OAuth2 Client Credentials trong job vẫn tương tự.

### 43.2. Không chạy cả CronJob và `@Scheduled` trùng

Nếu Kubernetes CronJob tạo container mà container lại bật một `@Scheduled` lâu dài, execution behavior có thể khác mong đợi. Với one-shot worker, nên tạo một entrypoint thực hiện tác vụ một lần rồi thoát, thay vì để Spring scheduler chạy vô hạn.

## 44. Mô hình headless worker

Nếu không cần HTTP server:

```yaml
spring:
  main:
    web-application-type: none
```

Nhưng đây chỉ là **một property**, không tự tạo implementation cho `ClientRegistrationRepository` nếu auto-configuration của target Boot version phụ thuộc web application.

### 44.1. Hai lựa chọn cho headless

1. Xác nhận Boot vẫn auto-configure registration/service theo stack/version thực, rồi inject như ví dụ.
2. Tạo Bean `ClientRegistrationRepository` từ trusted configuration một cách tường minh, giữ không phụ thuộc Servlet hoặc WebFlux server lifecycle.

### 44.2. Không dùng HTTP request-bound manager

Headless worker không có `HttpServletRequest` hay browser session. Service-backed authorized client manager phù hợp.

### 44.3. Process exit

Một CLI/CronJob muốn chạy một lần nên có `ApplicationRunner`/`CommandLineRunner` thích hợp và stop Spring context sau khi hoàn tất. Đừng chỉ bật `@Scheduled` trong non-web app rồi mong nó tự thoát theo lịch orchestrator.

## 45. Bài tập mở rộng: phân tách token acquisition và API client

Hiện tại `InventoryApiClient` vừa xin authorized client, vừa gọi API. Với application lớn, có thể tách:

```text
MachineTokenProvider
  -> OAuth2AuthorizedClientManager
  -> authorized client service

InventoryApiClient
  -> MachineTokenProvider
  -> WebClient

InventorySyncJob
  -> InventoryApiClient
  -> InventoryRepository
```

Lợi ích:

- Unit test token lifecycle riêng.
- API client chỉ biết nhận token qua một interface.
- Job không biết AS registration internals.
- Mỗi API dùng registration/permission cụ thể.
- Cảnh báo/audit có vị trí tập trung.

### 45.1. Không tạo một token provider toàn quyền

Một lớp `MachineTokenProvider.getToken(String registrationId)` nhận registration bất kỳ từ user input có thể khiến caller dùng token không được phép.

Nên bọc từng use case hoặc kiểm tra allowlist/internal service authorization, ví dụ:

```java
inventoryTokenProvider.accessToken();
billingTokenProvider.accessToken();
```

thay vì công bố endpoint lấy token theo client ID.

### 45.2. Không expose machine token ra browser

Ngay cả khi có REST endpoint admin «Run inventory sync», response chỉ nên trả job ID/status, không trả Access Token.

## 46. Bộ test regression tối thiểu

| ID | Tình huống | Kỳ vọng |
|---|---|---|
| T01 | Registration `inventory-job` tồn tại | Đúng grant `client_credentials`, token URI, scope. |
| T02 | Không có authorized client | Manager xin token từ AS stub. |
| T03 | Token còn hạn | Tái sử dụng authorized client, không gọi token endpoint lại vô ích. |
| T04 | Token cần cấp lại | Xin Access Token mới bằng client credentials. |
| T05 | Principal thay đổi | Store key khác; phát hiện nếu không chủ ý. |
| T06 | Client secret sai | Token endpoint trả `invalid_client`; job fail rõ. |
| T07 | Scope không hợp lệ | AS từ chối, không fallback scope rộng. |
| T08 | AS 429 | Backoff giới hạn; không retry storm. |
| T09 | AS timeout/5xx | Job báo failure, không giữ thread vô hạn. |
| T10 | Manager trả null | Không gọi API bằng token rỗng/sai. |
| T11 | API GET 200 | Parse DTO và báo success. |
| T12 | API 401 | Xử lý invalid token theo policy; không retry vô hạn. |
| T13 | API 403 | Báo permission issue, không tự xin scope admin. |
| T14 | API 503 | Retry có giới hạn nếu idempotent. |
| T15 | API trả body sai | Fail/alert, không coi snapshot rỗng là success. |
| T16 | API host không được duyệt | Không gửi Bearer token. |
| T17 | Authorization header | Token đúng request, không xuất hiện trong response/log. |
| T18 | Job chạy hai lần | Ghi dữ liệu idempotent, không double-count. |
| T19 | Nhiều pods chạy đồng thời | Lock/orchestration được kiểm chứng. |
| T20 | Shared authorized client store | Không dùng chéo registration/principal/tenant. |
| T21 | App restart | Hành vi memory vs persistent store đúng mong đợi. |
| T22 | Secret rotation | AS/RS behavior và retry policy đúng. |
| T23 | Token expired nhưng DB record còn | Manager không gửi token hết hạn một cách mù. |
| T24 | Production logging | Không có client secret, access token hoặc Authorization header. |

### 46.1. Không cần một test duy nhất bao phủ tất cả

Tách tests:

- **Unit test**: manager mock, DTO, scheduler orchestration.
- **Manager/store test**: fake provider, persistence, principal key.
- **HTTP integration test**: AS/RS stubs, grant serialization, status handling.
- **Deployment test**: secrets, TLS, proxy/egress, multiple replicas.
- **Security regression**: least privilege và tenant isolation.

## 47. Sự cố phổ biến và cách khắc phục

| Triệu chứng | Nguyên nhân đáng xét | Hướng xử lý |
|---|---|---|
| `No qualifying bean of type ClientRegistrationRepository` | Auto-config không match hoặc headless config thiếu. | Kiểm tra dependencies, Boot application type, explicit Bean. |
| `No client registration for inventory-job` | Sai `registrationId` hoặc custom repo override properties. | Kiểm tra actual repository và key. |
| `manager.authorize(...)` trả null | Provider không hỗ trợ grant/registration mismatch. | Đảm bảo `clientCredentials()` và grant config đúng. |
| Token endpoint 401 `invalid_client` | ID/secret/client auth method sai. | Kiểm tra AS registration và secret rotation. |
| Token endpoint báo `invalid_scope` | Scope không được cấp. | Sửa quyền client theo policy. |
| Job khởi động nhưng không chạy | Thiếu `@EnableScheduling` hoặc Bean không được quản lý. | Xác nhận scheduling config và lifecycle. |
| Job chạy nhiều lần song song | Nhiều pods, nhiều scheduling instances. | Lock/CronJob/idempotency. |
| AS nhận rất nhiều token requests | Principal thay đổi hoặc store không reuse/TTL quá ngắn. | Stable technical principal, kiểm tra cache/provider. |
| Token không được chia sẻ giữa pods | InMemory store per replica. | Shared store hoặc chấp nhận reissue theo policy. |
| `block()` gây lỗi reactive thread | Gọi từ event loop. | Chuyển sang reactive composition, không blocking loop. |
| API 401 ngay sau khi cấp token | Audience/issuer/token type/config không phù hợp. | So contract AS/RS, không tự tăng scope mù. |
| API 403 | Scope/permission thiếu. | Kiểm tra resource authorization, không retry vô hạn. |
| API 429/503 | Rate limit/availability. | Bounded backoff và monitoring. |
| API token gửi sai host | WebClient dynamic destination/default bearer config. | Fixed base URL, request-level header, allowlist. |
| Memory leak token cache | Principal key luôn tạo UUID. | Stable keys, TTL/cleanup. |
| DB có record nhưng manager vẫn lấy token mới | Principal/registration mismatch, expiry/skew, serialization. | Inspect storage key và provider policy. |
| JDBC store lỗi | Thiếu schema/DB credentials/serialization. | Schema đúng version, migration tests. |
| Logout user không ảnh hưởng job | Machine token độc lập user session. | Đây là khác biệt đúng; revoke client credential theo policy riêng. |
| Không tìm thấy ID Token | Client Credentials không phải OIDC user login. | Không yêu cầu `OidcUser`/ID Token cho job. |
| Metrics có raw bearer tokens | Logging/interceptor sai. | Redaction và incident response. |
| Test pass, production fail TLS | Stub không mô phỏng CA/proxy network. | Deployment integration/TLS validation. |

### 47.1. Debug theo lớp

```mermaid
flowchart TD
    A["Job chạy nhưng API không cập nhật"] --> B{"@Scheduled được gọi?"}
    B -->|Không| C["@EnableScheduling, Bean, scheduler configuration"]
    B -->|Có| D{"Registration tồn tại?"}
    D -->|Không| E["Boot properties / ClientRegistrationRepository"]
    D -->|Có| F{"Manager có trả authorized client?"}
    F -->|Không| G["client_credentials provider, AS token endpoint, secret"]
    F -->|Có| H{"Token đúng registration và còn hiệu lực?"}
    H -->|Không| I["principal key, store, expiry, clock skew"]
    H -->|Có| J{"API request tới đúng host, Bearer?"}
    J -->|Không| K["WebClient config, URI, header selection"]
    J -->|Có| L{"API status?"}
    L -->|401| M["Audience/issuer/expiry/revocation"]
    L -->|403| N["Scopes, client permission, tenant policy"]
    L -->|429 hoặc 5xx| O["Retry policy, rate limit, uptime"]
    L -->|200| P["DTO parsing, idempotent DB write, checkpoint"]
```

Không sửa mọi lỗi bằng cách xóa cache hoặc xin lại token liên tục. Hãy phân định **scheduling, registration, authorization, token store, HTTP client, Resource Server và business write**.

## 48. Khi nào không cần authorized client store bền vững?

Một job chạy **một lần mỗi ngày** và nhận token có expiry 30 phút sẽ gần như luôn phải lấy token mới, dù có lưu DB. Khi ấy:

- In-memory store cho process lifetime có thể đủ.
- Shared persistent store có thể phức tạp hơn giá trị thực.
- CronJob one-shot có thể xin token ở mỗi run theo policy.
- Việc giữ token lâu hơn mức cần thiết tạo thêm rủi ro bảo mật.

Ngược lại, một dịch vụ chạy 10 requests/giây từ nhiều pods, token lifetime 1 giờ và AS có rate limits sẽ có lợi từ token reuse/coordinated storage.

**Chọn persistence theo tần suất, lifetime, concurrency, availability và threat model**, không theo giả định «càng lưu nhiều càng tốt».

## 49. Bài tập tự thực hiện

### Bài tập A — Quan sát token reuse

1. Cấu hình local token stub có response `expires_in=3600`.
2. Chạy `InventorySyncJob` hai lần liên tiếp trong test.
3. Assert token endpoint chỉ được gọi lần đầu.
4. Assert Inventory API nhận cùng token fixture.
5. Đổi principal name ở lần hai và quan sát store lookup khác.
6. Giải thích vì sao principal cần ổn định.

### Bài tập B — Xử lý token hết hạn

1. Cấp token fixture đã hết hạn hoặc gần expiry.
2. Gọi manager authorize.
3. Assert client credentials token endpoint được gọi lại.
4. Assert service lưu authorized client mới.
5. Kiểm tra Access Token cũ không được gửi tới API.

### Bài tập C — API 401 và 403

1. API stub trả 401, ghi metric lỗi.
2. Xây policy tối đa một lần eviction/reissue khi xác định token invalid.
3. API stub vẫn 401 sau retry: job fail, không lặp vô hạn.
4. Đổi stub thành 403.
5. Assert không retry token endpoint vô ích chỉ vì thiếu quyền.

### Bài tập D — Thay kho in-memory bằng JDBC

1. Thêm JDBC dependencies/DB test.
2. Khởi tạo schema đúng Spring Security version.
3. Thay Bean service bằng JDBC implementation.
4. Ghi authorized client fixture, restart application test context.
5. Assert dữ liệu có thể load theo principal/registration.
6. Kiểm tra quyền DB, encryption/retention và cleanup.
7. Đánh giá concurrent writes.

### Bài tập E — Multi-tenant isolation

1. Tạo hai registrations/tenants từ trusted catalog.
2. Gọi job cho alpha.
3. Gọi job cho beta.
4. Assert token alpha chỉ được gửi tới alpha API.
5. Assert token beta không bị lấy theo key alpha.
6. Assert cùng email hoặc cùng `sub` của hai issuers không tự tạo account linking.
7. Kiểm tra job không nhận arbitrary registration ID từ untrusted input.

## 50. Checklist trước khi chạy production

**OAuth2 registration và token**

- [ ] `client_credentials` được AS cho phép.
- [ ] Client ID/secret hoặc phương thức client authentication phù hợp.
- [ ] Token endpoint là host đã được phê duyệt, HTTPS/TLS hợp lệ.
- [ ] Scope và audience tối thiểu cho Inventory API.
- [ ] Registration ID thống nhất trong YAML, manager và code.
- [ ] Có phân biệt rõ machine token và user delegated token.
- [ ] Không phụ thuộc browser `SecurityContext`/`HttpSession`.

**Authorized client manager và store**

- [ ] Service-backed manager cho job không có HTTP request.
- [ ] `clientCredentials()` provider được bật.
- [ ] Technical principal ổn định, không dùng random UUID mỗi lần.
- [ ] Token được lưu/reuse theo đúng registration/principal.
- [ ] Token expiration/clock skew và reissue đã được test.
- [ ] Chọn in-memory vs persistent store theo nhu cầu.
- [ ] Nếu persistent, dữ liệu token được bảo vệ và có cleanup/rotation policy.
- [ ] Nếu nhiều instances, có chiến lược tránh duplicate token requests.

**Job và Inventory API**

- [ ] `@EnableScheduling` và `@Scheduled` được cấu hình đúng.
- [ ] Job không chạy trùng ngoài dự kiến trên cluster.
- [ ] API base URL cố định/allowlisted.
- [ ] Bearer token gắn riêng cho request cần thiết.
- [ ] Không expose token qua controller/DTO/log/URL.
- [ ] Timeout/retry có giới hạn; 401/403/429/5xx được phân loại.
- [ ] Business DB writes idempotent và có checkpoint khi cần.
- [ ] Có metrics/alert cho lần chạy lỗi và quá hạn lịch.
- [ ] Client secret rotation và failure runbook rõ ràng.

**Kiểm thử và vận hành**

- [ ] Unit test manager request và token header.
- [ ] Test token reuse với fake provider/store.
- [ ] Integration test token endpoint bằng synthetic AS stub.
- [ ] Integration test Resource Server API bằng stub.
- [ ] Có negative tests cho wrong registration/tenant/host.
- [ ] Không dùng production credentials trong CI/test fixtures.
- [ ] Logs và monitoring không chứa credential.
- [ ] Có kế hoạch rollback/restart khi đổi token-store schema.

## 51. Tài liệu tham khảo

- [OAuth 2.0 Authorization Framework — Client Credentials Grant, RFC 6749 `4.4](https://www.rfc-editor.org/rfc/rfc6749#section-4.4)
- [OAuth 2.0 Security Best Current Practice — RFC 9700](https://www.rfc-editor.org/rfc/rfc9700)
- [OAuth 2.0 Bearer Token Usage — RFC 6750](https://www.rfc-editor.org/rfc/rfc6750)
- [Spring Security Reference — OAuth2 Client (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html)
- [Spring Security Reference — Core Interfaces and Classes (OAuth2 Client)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/core.html)
- [Spring Security Reference — Client Credentials](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html)
- [Spring Security API — OAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientManager.html)
- [Spring Security API — AuthorizedClientServiceOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html)
- [Spring Security API — OAuth2AuthorizedClientService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientService.html)
- [Spring Security API — InMemoryOAuth2AuthorizedClientService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/InMemoryOAuth2AuthorizedClientService.html)
- [Spring Security API — JdbcOAuth2AuthorizedClientService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/JdbcOAuth2AuthorizedClientService.html)
- [Spring Security API — OAuth2AuthorizedClientProviderBuilder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientProviderBuilder.html)
- [Spring Security API — OAuth2AuthorizeRequest](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizeRequest.html)
- [Spring Boot Reference — OAuth2 Client](https://docs.spring.io/spring-boot/reference/web/spring-security.html)
- [Spring Boot Reference — Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html)
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework Reference — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Spring Security Reference — OAuth2 Client (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html)
- [Spring Security Reference — Testing](https://docs.spring.io/spring-security/reference/servlet/test/index.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html)
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html)

## 52. Tổng kết

Bài thực hành đã xây dựng một **Spring Boot scheduled job** dùng **OAuth 2.0 Client Credentials Grant** để gọi Inventory API mà **không cần browser hay user session**:

1. Cấu hình client registration `inventory-job` với `client_credentials` và scope `inventory.read`.
2. Dùng `AuthorizedClientServiceOAuth2AuthorizedClientManager` cùng `OAuth2AuthorizedClientProviderBuilder.clientCredentials()`.
3. Lưu token thông qua `OAuth2AuthorizedClientService`, trước tiên là `InMemoryOAuth2AuthorizedClientService`.
4. Gọi `manager.authorize(...)` với technical principal ổn định `job:inventory-sync`.
5. Gắn Access Token vào **đúng** `WebClient` request tới Inventory API.
6. Lập lịch bằng `@Scheduled` và giữ business write idempotent.
7. Phân biệt token reuse với token reissue khi hết hạn; **client_credentials thường không dùng Refresh Token**.
8. Mở rộng kho authorized client sang JDBC/Redis nếu tần suất, nhiều instances và chính sách yêu cầu.
9. Bổ sung giới hạn timeout/retry, monitoring, secret protection, scope/audience và anti-token-leak controls.
10. Test bằng fake manager/provider và local AS/API stubs, không đụng tới production credentials.

**Bài học quan trọng nhất:** `OAuth2AuthorizedClientManager` quản lý token cho một **client registration và principal context**, nhưng trong job M2M, principal là **khóa kỹ thuật do ứng dụng kiểm soát**, không phải một `OidcUser`. Hãy chọn manager không phụ thuộc HTTP request, lưu và tái sử dụng authorized client đúng phạm vi, không tự biến machine token thành user token và không đánh đồng **token cache**, **lịch thực thi job** và **authorization policy**. Khi ba trách nhiệm này được tách rõ, job nền có thể chạy bền vững, dễ kiểm thử và bảo vệ credentials đúng cách.
