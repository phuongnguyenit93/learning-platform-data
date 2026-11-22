# 17.3. RefreshTokenOAuth2AuthorizedClientProvider trong Servlet

## 1. Đặt vấn đề: access token hết hạn nhưng người dùng không nên đăng nhập lại liên tục

Một ứng dụng **Spring Security OAuth 2.0/OIDC Client** thường nhận access token sau khi người dùng hoàn tất **Authorization Code** hoặc **OIDC Login**. Access token có thời hạn; khi backend cần gọi một Resource Server sau một khoảng thời gian, access token ban đầu có thể đã hết hiệu lực.

Nếu Authorization Server đồng thời cấp **refresh token**, OAuth2 Client có thể dùng refresh token đó để yêu cầu một access token mới tại **Token Endpoint** mà không cần đưa trình duyệt quay lại Authorization Endpoint trong mỗi lần sử dụng API.

Trong ngăn xếp **Servlet/non-reactive** của Spring Security, thành phần chịu trách nhiệm thực hiện grant làm mới này là:

```java
org.springframework.security.oauth2.client.RefreshTokenOAuth2AuthorizedClientProvider
```

Tên class khá dài nhưng có thể đọc như sau:

- **`RefreshToken`**: xử lý **OAuth 2.0 Refresh Token Grant** (`grant_type=refresh_token`).
- **`OAuth2AuthorizedClient`**: làm việc với một authorized client đã có, gồm `ClientRegistration`, access token và refresh token nếu được cấp.
- **`Provider`**: một chiến lược được `OAuth2AuthorizedClientManager` gọi khi cần cấp mới/cấp lại quyền.

**Điểm mấu chốt:** `RefreshTokenOAuth2AuthorizedClientProvider` **không tự tạo refresh token** cho client. Nó chỉ có thể làm mới khi đã có một `OAuth2AuthorizedClient` chứa refresh token hợp lệ, token hiện tại cần được làm mới và Token Endpoint chấp nhận refresh request.

### 1.1. Mục tiêu sau bài học

Sau bài học, bạn cần hiểu:

1. Provider được manager gọi ở bước nào và khi nào trả `null`.
2. Mối quan hệ giữa `ClientRegistration`, `OAuth2AuthorizedClient`, `OAuth2AuthorizedClientService`/`Repository` và provider.
3. Cách bật `refreshToken()` trong `OAuth2AuthorizedClientProviderBuilder`.
4. Cách dùng `DefaultOAuth2AuthorizedClientManager` trong HTTP Servlet request, và khi nào dùng manager cho background job.
5. Cách refresh token được gửi tới Token Endpoint và authorized client mới được lưu.
6. Ảnh hưởng của `clockSkew`, expiry, refresh token rotation, logout và concurrency.
7. Cách chẩn đoán `invalid_grant`, thiếu refresh token, sai client authentication và các lỗi API sau refresh.
8. Sự khác biệt với API reactive/WebFlux.

### 1.2. Giới hạn phạm vi

Bài học tập trung vào **OAuth2 Client với Servlet**. Đây không phải bài triển khai Authorization Server cấp refresh token, không phải cơ chế làm mới phiên đăng nhập bằng `JSESSIONID`, và không phải chức năng tự động làm mới mọi JWT do Resource Server nhận.

Trong một hệ thống dùng `client_credentials`, access token thông thường được cấp lại bằng **`client_credentials` grant**, không phải bằng refresh token. Do đó, đừng thêm `refreshToken()` rồi nghĩ rằng mọi registration đều có refresh token.

## 2. Phân biệt access token, refresh token, ID Token và web session

| Thành phần | Dùng để làm gì? | Bên thường sử dụng | Thời hạn và lưu trữ |
| --- | --- | --- | --- |
| **Access token** | Trình tới Resource Server để gọi API | OAuth2 Client gửi; Resource Server xác minh | Thường ngắn hạn; nằm trong `OAuth2AuthorizedClient` |
| **Refresh token** | Xin access token mới từ Token Endpoint | OAuth2 Client và Authorization Server | Thường sống lâu hơn access token; là credential nhạy cảm |
| **ID Token (OIDC)** | Truyền thông tin về lần xác thực danh tính cho client | OIDC Client | Xác minh theo OIDC; **không phải** refresh token |
| **Web session** | Giữ authentication của browser tại ứng dụng web | Browser và Spring Security app | Theo session policy; có thể tồn tại khác thời hạn token |
| **Authorization code** | Đổi lấy token sau callback của Authorization Code | OAuth2 Client và Token Endpoint | Dùng một lần, ngắn hạn; không dùng để refresh về sau |
| **`OAuth2AuthorizedClient`** | Gói registration và token đã cấp cho một principal | Spring Security OAuth2 Client | Được lưu bởi service/repository theo chính sách |

Một người dùng có thể vẫn truy cập website vì **session cookie còn hợp lệ** trong khi access token để gọi một API đã hết hạn. Ngược lại, access token có thể còn hạn khi session ứng dụng đã logout.

**Refresh token grant chỉ nói về việc lấy token mới**; nó không tự bảo đảm người dùng còn session, không tự cập nhật quyền nghiệp vụ, và không mặc nhiên tạo `OidcUser`/ID Token mới.

## 3. Vòng đời refresh trong một luồng OAuth2/OIDC Login

Giả sử người dùng đã đăng nhập bằng OIDC:

```text
Client registration: corporate
Principal name:     user-123
Access token A:     expiresAt = 10:30
Refresh token R1:   đã được Authorization Server cấp
```

Lúc 10:15, backend gọi API và manager có thể trả access token A vì nó vẫn được xem là dùng được theo policy.

Khi backend gọi API gần hoặc sau mốc hết hạn, manager có thể gọi refresh provider để gửi:

```http
POST /oauth2/token HTTP/1.1
Host: idp.example.com
Authorization: Basic <client-authentication-if-required>
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=<R1>
```

Sau thành công, Authorization Server trả access token B; có thể trả refresh token R2 mới, hoặc không trả refresh token mới tùy chính sách. Spring Security xây một `OAuth2AuthorizedClient` mới và manager có thể **lưu lại** nó qua authorized-client repository/service.

Sơ đồ:

```mermaid
sequenceDiagram
    autonumber
    participant API as Spring MVC Service / Gateway
    participant M as DefaultOAuth2AuthorizedClientManager
    participant S as OAuth2AuthorizedClientRepository
    participant P as RefreshTokenOAuth2AuthorizedClientProvider
    participant AS as Authorization Server
    participant RS as Resource Server

    API->>M: authorize(registration=corporate, principal=user-123)
    M->>S: load(corporate, user-123, request)
    S-->>M: AuthorizedClient(access A, refresh R1)
    M->>P: authorize(context with authorized client)
    alt Access A chưa cần refresh
        P-->>M: null - không phải thay token
        M-->>API: AuthorizedClient hiện tại
    else Access A đã đến thời điểm refresh
        P->>AS: POST /token grant_type=refresh_token, refresh_token=R1
        AS->>AS: Xác thực client và kiểm tra refresh token
        AS-->>P: access token B; có thể refresh token R2
        P-->>M: AuthorizedClient mới
        M->>S: save(corporate, user-123, B, R2 hoặc R1 theo response)
        M-->>API: AuthorizedClient mới
    end
    API->>RS: Bearer access token hiện hành
    RS-->>API: Kết quả hoặc lỗi 401/403
```

Sơ đồ biểu diễn trách nhiệm ở mức logic. Thứ tự cụ thể của các provider trong chain, cách manager lưu, success/failure handlers và thời điểm cấp lại phụ thuộc cấu hình/phiên bản Spring Security.

### 3.1. Không có refresh token thì sao?

Nếu authorized client không có refresh token, `RefreshTokenOAuth2AuthorizedClientProvider` **không thể thực hiện grant refresh token**. Khi đó provider trả `null`, thể hiện không thực hiện được việc re-authorize theo chiến lược này.

Tùy registration/manager/provider chain, ứng dụng có thể:

- Dùng access token hiện tại khi còn hợp lệ.
- Yêu cầu người dùng khởi tạo lại Authorization Code/OIDC Login để có token mới.
- Với `client_credentials`, xin một access token mới bằng client credentials thông qua provider dành cho grant đó.
- Trả lỗi API/user-facing phù hợp nếu không thể xin token.

**Không tạo refresh token từ access token, không dùng ID Token làm refresh token, và không giả định `scope=offline_access` luôn khiến provider cấp refresh token.**

## 4. Hợp đồng `OAuth2AuthorizedClientProvider`

`RefreshTokenOAuth2AuthorizedClientProvider` thực thi interface:

```java
org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider
```

Method trung tâm:

```java
OAuth2AuthorizedClient authorize(
    OAuth2AuthorizationContext context);
```

`OAuth2AuthorizationContext` cung cấp các thành phần cần thiết như:

- `ClientRegistration` đã được chọn.
- `Authentication`/principal gắn với authorized client.
- `OAuth2AuthorizedClient` hiện tại nếu đã được cấp quyền trước đó.
- Các attributes liên quan nếu manager/ứng dụng đưa vào ngữ cảnh.

Với refresh token provider, logic khái niệm là:

```text
authorize(context):
    current = context.authorizedClient

    nếu current không tồn tại:
        return null

    refresh = current.refreshToken
    nếu refresh không tồn tại:
        return null

    access = current.accessToken
    nếu access chưa đến ngưỡng cần refresh:
        return null

    gửi Refresh Token Grant Request đến Token Endpoint
    nếu thành công:
        return OAuth2AuthorizedClient mới với token mới
    nếu thất bại:
        ném lỗi OAuth2 authorization tương ứng
```

Đây là **pseudocode giải thích**, không phải source code nguyên văn của Spring Security. Điều kiện cụ thể để tính token “expired”, clock skew và validation phụ thuộc phiên bản/config.

### 4.1. Ý nghĩa khi `authorize(...)` trả `null`

Một điểm rất dễ hiểu sai: `null` từ một **provider** không nhất thiết đồng nghĩa toàn bộ chức năng gọi API thất bại.

Trong kiến trúc provider chain, `null` có thể nghĩa là:

- Provider hiện tại **không hỗ trợ/không áp dụng** cho ngữ cảnh này.
- Access token **chưa cần làm mới**.
- Authorized client không có refresh token.

Manager có thể giữ authorized client đang tồn tại hoặc thử provider khác trong chain theo quy tắc của nó.

Vì vậy, nếu muốn biết có refresh thật hay không, hãy quan sát **token request**, giá trị token/expiry đã làm sạch và success handler, không suy luận chỉ từ việc một provider trả `null`.

### 4.2. Khi nào class này thực hiện HTTP request?

Provider chỉ thực hiện token request khi manager đưa cho nó đủ ngữ cảnh và điều kiện refresh. Nó **không chạy background timer** và cũng không liên tục kiểm tra mọi token trong kho lưu trữ.

Ví dụ:

```text
10:00 Token A được cấp, expiresAt=10:30.
10:20 Không có code gọi authorizedClientManager.authorize(...).
10:31 Token A đã hết hạn nhưng provider không tự “thức dậy”.
10:35 Có lời gọi authorize(...), refresh mới có cơ hội diễn ra.
```

Nếu hệ thống cần chủ động refresh theo lịch, đó là một **workflow riêng** phải gọi manager phù hợp, có chính sách retry, concurrency và không cần người dùng đang mở trình duyệt.

## 5. Những class liên quan trong Servlet

| Thành phần | Vai trò | Có tự lưu token không? |
| --- | --- | --- |
| `ClientRegistrationRepository` | Tìm cấu hình client theo registration ID | Không |
| `OAuth2AuthorizedClient` | Chứa access token và refresh token (nếu có) | Là đối tượng dữ liệu |
| `OAuth2AuthorizedClientRepository` | Load/save/remove authorized client theo Servlet request/response và principal | Có |
| `OAuth2AuthorizedClientService` | Load/save/remove theo registration ID/principal, độc lập Servlet request | Có |
| `DefaultOAuth2AuthorizedClientManager` | Điều phối authorize trong **HTTP Servlet request** | Dùng repository |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | Điều phối authorize ngoài HTTP Servlet request | Dùng service |
| `OAuth2AuthorizedClientProvider` | Chiến lược cấp/cấp lại token | Không tự là store |
| `RefreshTokenOAuth2AuthorizedClientProvider` | Thực hiện Refresh Token Grant | Không |
| `OAuth2AuthorizedClientProviderBuilder` | Tạo/delegate chain các provider theo grants | Không |
| `OAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>` | Thực hiện HTTP Token Request và parse response | Không phải store |

Đặc biệt, **`AuthorizationRequestRepository`** là repository khác, giữ `OAuth2AuthorizationRequest` với `state`/PKCE trước callback. Nó không phải kho authorized client sau khi có token.

### 5.1. Vì sao phải qua manager?

Nếu gọi provider trực tiếp ở mọi business service, ứng dụng phải tự quyết định:

- Registration và principal nào đang được sử dụng?
- Lấy authorized client cũ từ đâu?
- Khi nào provider trả `null`?
- Ai ghi token mới về storage?
- Nếu `invalid_grant`, ai loại entry không còn dùng được?
- Ai xử lý các grant khác, như authorization code hoặc client credentials?

`OAuth2AuthorizedClientManager` là abstraction phù hợp hơn vì nó kết nối provider với repository/service và success/failure handling. Provider riêng lẻ chỉ là **một chiến lược**.

## 6. Cấu hình Spring Boot cho OIDC Login có thể cấp refresh token

### 6.1. Dependency

Ví dụ Gradle cho ứng dụng Spring MVC:

```gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
}
```

### 6.2. `application.yml`

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: company-oidc
            client-id: ${CORPORATE_CLIENT_ID}
            client-secret: ${CORPORATE_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
              - offline_access

        provider:
          company-oidc:
            issuer-uri: https://idp.example.com/realms/employees
```

**Lưu ý về `offline_access`:**

- Đây là scope OIDC liên quan quyền truy cập ngoại tuyến, nhưng **không bảo đảm** mọi provider sẽ cấp refresh token chỉ vì có scope này.
- IdP có thể yêu cầu consent, một policy riêng, loại client phù hợp hoặc tham số đăng nhập khác.
- Có provider cấp refresh token cho Authorization Code ngay cả khi không yêu cầu `offline_access`, tùy hợp đồng của họ.
- Một số provider giới hạn refresh token theo client, thiết bị, session, tenant, thời gian nhàn rỗi hoặc vòng đời tuyệt đối.
- Không sao chép tùy tiện `prompt=consent`, `access_type=offline` hay tham số mở rộng của một nhà cung cấp sang provider khác.

**Không lưu client secret thực trong Git.** Các biến `${CORPORATE_CLIENT_ID}`/`${CORPORATE_CLIENT_SECRET}` lấy từ cấu hình môi trường hoặc secret manager.

### 6.3. SecurityFilterChain tối thiểu

```java
@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/assets/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());

        return http.build();
    }
}
```

Với cấu hình hợp lệ, Spring Security đảm nhiệm Authorization Code/OIDC Login, kiểm tra ID Token và quản lý authorized client qua các thành phần thích hợp. **Không cần tự viết callback controller chỉ để lấy refresh token**.

Cần hiểu provider có thực sự cấp refresh token hay không và authorized client đang được lưu ở repository/service nào.

## 7. Bật Refresh Token provider trong Servlet manager

### 7.1. Cách cấu hình phổ biến: `OAuth2AuthorizedClientProviderBuilder`

Một `DefaultOAuth2AuthorizedClientManager` có thể nhận chain gồm `authorizationCode()` và `refreshToken()`:

```java
@Configuration
class OAuth2ClientManagerConfiguration {

    @Bean
    OAuth2AuthorizedClientManager authorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientRepository authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .build();

        var manager = new DefaultOAuth2AuthorizedClientManager(
            registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

Các class sử dụng ở ví dụ thuộc Spring Security, `@Bean` và `@Configuration` thuộc Spring Framework. Phần import được lược bớt để tập trung vào ý tưởng.

Ở đây:

- `authorizationCode()` dành cho grant Authorization Code khi phù hợp.
- `refreshToken()` thêm chiến lược `RefreshTokenOAuth2AuthorizedClientProvider`.
- `DefaultOAuth2AuthorizedClientManager` làm việc với HTTP Servlet request và `OAuth2AuthorizedClientRepository`.
- Manager giữ trách nhiệm kết nối việc **lấy authorized client hiện có**, **gọi provider**, **lưu token mới** và xử lý thành công/thất bại theo cấu hình.

**Không cần bật `clientCredentials()` nếu ứng dụng chỉ dùng interactive OIDC Login.** Nếu cùng backend có thêm machine-to-machine registrations, cần xây provider chain/manager cho từng bối cảnh đúng grant và đúng storage.

### 7.2. Có cần tự đăng ký provider không?

Các cấu hình tự động của Spring Boot/Spring Security có thể cung cấp manager/provider phù hợp cho các use case phổ biến. **Không nên tự tạo manager trùng chức năng chỉ vì muốn “bật refresh” mà chưa xác định hệ thống đang dùng bean nào.**

Khi cần thay đổi clock skew, token response client hoặc success/failure handler, nên cấu hình một manager tường minh ở đúng điểm sử dụng và kiểm tra rằng HTTP client/controller thực tế gọi manager đó.

### 7.3. Dùng `@RegisteredOAuth2AuthorizedClient` trong Controller

Spring Security có annotation giúp resolve một authorized client trong MVC handler:

```java
@RestController
class ReportsController {

    @GetMapping("/reports/token-status")
    Map<String, Object> tokenStatus(
            @RegisteredOAuth2AuthorizedClient("corporate")
            OAuth2AuthorizedClient client) {

        OAuth2AccessToken accessToken = client.getAccessToken();

        return Map.of(
            "registrationId",
                client.getClientRegistration().getRegistrationId(),
            "expiresAt",
                accessToken.getExpiresAt() == null
                    ? "unknown"
                    : accessToken.getExpiresAt().toString()
        );
    }
}
```

Annotation thuộc `org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient`. Tùy cấu hình, resolver/manager có thể trả authorized client hiện có hoặc authorize lại theo provider chain.

Ví dụ chỉ trả **metadata**, không xuất token value. Endpoint tương tự phải được bảo vệ theo đúng quyền. Ngoài ra, annotation được xử lý trong bối cảnh HTTP request; đối với background job, dùng service-based manager thay vì trông đợi có MVC method argument.

### 7.4. Gọi manager tường minh trong HTTP Servlet request

Ví dụ một service được gọi từ controller có authenticated user:

```java
@Service
class CorporateApiClient {

    private final OAuth2AuthorizedClientManager manager;
    private final RestClient api;

    CorporateApiClient(
            OAuth2AuthorizedClientManager manager,
            RestClient.Builder builder) {

        this.manager = manager;
        this.api = builder
            .baseUrl("https://hr-api.example.com")
            .build();
    }

    String currentProfile(Authentication authentication) {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("corporate")
                .principal(authentication)
                .build();

        OAuth2AuthorizedClient authorizedClient =
            manager.authorize(request);

        if (authorizedClient == null) {
            throw new IllegalStateException(
                "OAuth2 authorization unavailable");
        }

        return api.get()
            .uri("/api/profile")
            .headers(headers -> headers.setBearerAuth(
                authorizedClient.getAccessToken().getTokenValue()))
            .retrieve()
            .body(String.class);
    }
}
```

Đoạn này minh họa khi service được gọi **trong HTTP Servlet request đã xác thực**, nơi `DefaultOAuth2AuthorizedClientManager` có thể sử dụng request/response context phù hợp. Nếu gọi từ một thread/tác vụ không có Servlet request, cần truyền context đúng hợp đồng manager hoặc chọn **service-based manager**.

Sử dụng **base URL cố định và đáng tin cậy** cho API đích; không nhận một URL bất kỳ từ input rồi gắn access token, tránh làm lộ token qua redirect/SSRF.

`RestClient` thuộc Spring Framework 6.1+. Với phiên bản khác, có thể sử dụng `WebClient` hoặc HTTP client phù hợp mà vẫn tuân thủ cùng nguyên tắc.

## 8. Cấu hình `RefreshTokenOAuth2AuthorizedClientProvider` trực tiếp

Đôi khi cần thay đổi clock skew hoặc truyền một token response client tùy chỉnh. Khi đó có thể khởi tạo provider trực tiếp:

```java
RefreshTokenOAuth2AuthorizedClientProvider refreshProvider =
    new RefreshTokenOAuth2AuthorizedClientProvider();

refreshProvider.setClock(Clock.systemUTC());
refreshProvider.setClockSkew(Duration.ofSeconds(90));
```

Các API cấu hình được hỗ trợ tùy phiên bản Spring Security, vì vậy khi nâng cấp cần đối chiếu phiên bản thư viện dự án. Ở những phiên bản Servlet phổ biến, provider cho phép điều chỉnh clock/clock skew và HTTP token response client.

### 8.1. Gắn provider trực tiếp vào chain

Nếu cần cùng hỗ trợ `authorization_code` và custom refresh provider:

```java
OAuth2AuthorizedClientProvider provider =
    new DelegatingOAuth2AuthorizedClientProvider(
        new AuthorizationCodeOAuth2AuthorizedClientProvider(),
        refreshProvider
    );

DefaultOAuth2AuthorizedClientManager manager =
    new DefaultOAuth2AuthorizedClientManager(
        clientRegistrations, authorizedClientRepository);

manager.setAuthorizedClientProvider(provider);
```

Ví dụ giả định `clientRegistrations`, `authorizedClientRepository` đã được inject hợp lệ; mục đích là cho thấy **refresh provider không cần đứng một mình**. Sử dụng builder khi không cần tùy biến sâu thường đơn giản và dễ bảo trì hơn.

Một cách cấu hình khác có thể dùng customizer của `OAuth2AuthorizedClientProviderBuilder` nếu phiên bản Spring Security hiện tại cung cấp API tương ứng; không sao chép tên phương thức giữa các phiên bản nếu chưa kiểm tra.

### 8.2. `Clock` và `clockSkew` có tác dụng gì?

Access token có `expiresAt`. Nếu một token chỉ còn vài giây nhưng backend phải gọi API qua nhiều hop, token có thể hết hạn trước khi Resource Server nhận được request. Do đó provider có thể **coi token đã đến hạn làm mới sớm hơn thời điểm hết hạn thực tế**.

Ví dụ:

```text
Access token expiresAt: 10:30:00
clockSkew:             90 giây

10:28:00 → chưa đến ngưỡng refresh
10:28:30 → bắt đầu coi token cần refresh theo ngưỡng dự phòng
10:30:00 → token thực sự hết hạn theo expiresAt
```

Đây là mô hình đơn giản hóa phép so thời gian. Giá trị `90 giây` chỉ là **ví dụ thiết kế**, không phải một default bắt buộc cho mọi phiên bản.

Quyết định `clockSkew` cần xét:

- Đồng hồ các hệ thống có đồng bộ không?
- Độ trễ trung bình và p99 khi gọi Resource Server.
- Độ dài tối thiểu/đặc điểm access token do provider cấp.
- Tần suất API call và tỷ lệ refresh không cần thiết.
- Thời gian xử lý request và retry của Token Endpoint.

**Không đặt clock skew quá lớn so với token lifetime**, vì có thể dẫn đến xin token thường xuyên không cần thiết. Và clock skew không chữa được đồng hồ hệ thống lệch nhiều phút hoặc token bị provider revoke.

### 8.3. `OAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>`

Provider sử dụng một HTTP client chuyên trách để tạo **Refresh Token Grant Request** và đọc token response:

```java
OAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>
```

Ví dụ cấu trúc cấu hình:

```java
RefreshTokenOAuth2AuthorizedClientProvider provider =
    new RefreshTokenOAuth2AuthorizedClientProvider();

provider.setAccessTokenResponseClient(customRefreshTokenResponseClient);
```

Ở đây `customRefreshTokenResponseClient` là một implementation **đã được cung cấp và cấu hình riêng**, không phải bean mặc định được tạo bởi đoạn code trên.

Có thể cần custom response client khi:

- Token Endpoint nằm sau proxy, cần SSL context/timeout riêng.
- Provider có form parameter mở rộng được tài liệu hóa.
- Hệ thống dùng client authentication nâng cao như mTLS/private-key JWT.
- Token response có đặc điểm tương thích cần xử lý qua API được hỗ trợ.

Các implementation và API mở rộng của Token Response Client có thể thay đổi theo phiên bản Spring Security, ví dụ giữa các client sử dụng `RestOperations` và `RestClient`. **Không tự thay thế HTTP client bằng một đoạn `POST` thủ công nếu làm vậy bỏ qua client authentication, lỗi OAuth2 hoặc logic cập nhật refresh token.**

## 9. Nội dung HTTP Refresh Token Request

Về mặt giao thức, Token Endpoint thường nhận:

```http
POST /oauth2/token HTTP/1.1
Host: idp.example.com
Authorization: Basic <client-credentials-if-required>
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=refresh_token&refresh_token=<refresh-token-value>
```

Nếu chính sách provider cho phép yêu cầu scope hẹp hơn, token request có thể chứa `scope` phù hợp. Theo OAuth2, refresh grant không phải cách để **mở rộng quyền** vượt phạm vi ban đầu.

Token response thành công minh họa:

```json
{
  "access_token": "REDACTED_ACCESS_TOKEN_B",
  "token_type": "Bearer",
  "expires_in": 3600,
  "scope": "reports.read",
  "refresh_token": "REDACTED_REFRESH_TOKEN_R2"
}
```

Một provider khác có thể không cấp `refresh_token` mới trong response. Cách client giữ refresh token cũ hoặc thay bằng token mới phải tuân thủ hợp đồng/thư viện và **không làm mất refresh token còn hiệu lực** khi response không có field đó.

**Không có ID Token bắt buộc trong Refresh Token Grant** như trong OIDC Authorization Code token response. OIDC có quy định riêng về trường hợp Token Endpoint trả ID Token khi refresh; không giả định việc refresh access token tự động cập nhật `OidcUser` hoặc toàn bộ `Authentication` trong session.

### 9.1. Client authentication vẫn quan trọng khi refresh

Nếu original client registration dùng confidential client (`client_secret_basic`, `client_secret_post`, private-key JWT, mTLS...), Token Endpoint có thể yêu cầu **xác thực lại client** khi dùng refresh token.

Lỗi `invalid_client` khi refresh có thể do:

- Client secret đã rotate nhưng ứng dụng chưa cập nhật.
- Authentication method không đúng với đăng ký.
- `ClientRegistration` trỏ tới sai realm/tenant/token endpoint.
- Certificate/key của client không còn hợp lệ.

Không khắc phục bằng cách bỏ client authentication hoặc truyền refresh token qua browser URL. Refresh token phải được gửi qua **back-channel HTTPS** từ backend tới Token Endpoint.

### 9.2. Scope mới có tự động xuất hiện không?

Nếu ứng dụng vừa sửa YAML từ `scope: reports.read` sang `scope: reports.read, reports.admin`, việc refresh token cũ **không bảo đảm** provider sẽ cấp thêm `reports.admin`.

Scopes được cấp ban đầu, consent và chính sách Authorization Server có thể giới hạn grant. Khi cần quyền mới, ứng dụng có thể phải khởi tạo lại Authorization Code/consent hoặc đăng ký quyền mới tại provider.

## 10. Lưu refresh token và authorized client ở đâu?

### 10.1. Theo HTTP request: `OAuth2AuthorizedClientRepository`

Trong Servlet web app, `DefaultOAuth2AuthorizedClientManager` sử dụng `OAuth2AuthorizedClientRepository` để load/save/remove authorized client trong bối cảnh request/response.

Một implementation có thể sử dụng `OAuth2AuthorizedClientService` bên dưới. Cụ thể, `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` thường ủy quyền việc lưu authorized clients của principal đã xác thực cho service và có thể dùng session repository cho ngữ cảnh khác.

Do đó, khi refresh không tìm thấy token đã lưu, phải kiểm tra **repository nào đang được dùng**, chứ không chỉ nhìn một service bean bất kỳ.

### 10.2. Cho background task: `OAuth2AuthorizedClientService`

Một background task không có `HttpServletRequest` thường nên dùng:

```java
AuthorizedClientServiceOAuth2AuthorizedClientManager
```

Ví dụ:

```java
@Configuration
class BackgroundOAuth2ClientConfig {

    @Bean
    OAuth2AuthorizedClientManager backgroundAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .refreshToken()
                .clientCredentials()
                .build();

        var manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations, authorizedClients);

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

Ở đây:

- `refreshToken()` phục vụ **những authorized clients đã có refresh token**.
- `clientCredentials()` phục vụ những registrations `client_credentials` theo policy.
- **Authorization Code/Login khởi tạo bằng browser không được thực hiện tự động từ background job**; nếu user-specific authorized client đã mất hoặc refresh token không còn dùng được, job không thể tạo một browser login thay người dùng.

Một background job dùng refresh token của người dùng còn đặt ra vấn đề consent, lifetime, lưu trữ và thu hồi quyền. Không dùng user refresh token lâu dài cho batch nếu service-to-service client credentials đã đáp ứng nghiệp vụ.

### 10.3. RAM, session, JDBC và kho chia sẻ

| Storage | Lợi ích | Giới hạn/rủi ro |
| --- | --- | --- |
| In-memory authorized-client service | Đơn giản, nhanh | Mất qua restart, không chia sẻ nhiều pod, không tự TTL |
| HTTP session repository | Gắn theo phiên browser | Session expire/logout, nhiều instance cần session management |
| JDBC authorized-client service | Bền vững, chia sẻ khi cấu hình đúng | Cần schema, security, transaction, cleanup |
| Custom Redis/database | Có thể thêm TTL, index và concurrency control | Phải bảo toàn token/refresh token, binding và atomic update |

**Refresh token là credential nhạy cảm**. Khi lưu trong database/Redis, cần bảo vệ bằng TLS, kiểm soát truy cập tối thiểu, mã hóa khi chính sách yêu cầu và retention/cleanup rõ ràng.

**Không log raw refresh token.** Không gửi nó cho frontend chỉ để “tiện refresh”, khi kiến trúc backend đang giữ token.

## 11. Refresh token rotation: vì sao concurrency rất quan trọng?

Nhiều Authorization Servers sử dụng **refresh token rotation**. Sau khi client dùng R1, server có thể cấp R2 và vô hiệu hóa R1.

Ví dụ:

```text
Thời điểm T0:
  access = A1
  refresh = R1

Request X:
  refresh bằng R1
  -> nhận A2 + R2
  -> lưu A2/R2

Request Y:
  gần đồng thời cũng refresh bằng R1
  -> có thể nhận invalid_grant
```

Một số server có cơ chế **refresh token reuse detection**: tái sử dụng R1 có thể dẫn tới thu hồi cả nhóm token liên quan. Policy cụ thể tùy provider.

### 11.1. Những race condition cần nghĩ tới

- Hai HTTP requests cùng thấy access token gần hết hạn.
- Hai pod cùng đọc bản authorized client cũ từ shared store.
- Cả hai cùng gọi Token Endpoint bằng một refresh token.
- Một response thành công với R2 bị một write chậm chứa R1 ghi đè.
- Một failure handler xóa entry vừa được request khác refresh thành công.
- Một request đọc token trước khi logout/revocation, rồi ghi lại entry sau sự kiện logout.

**`InMemoryOAuth2AuthorizedClientService` có thể có thao tác map thread-safe nhưng không tự bảo đảm refresh token rotation chỉ chạy một lần trên toàn cluster.**

### 11.2. Hướng xử lý

Tùy hệ thống, cân nhắc:

1. **Single-flight** theo `(registrationId, principalName)` trong một process.
2. **Distributed lock/CAS/version** nếu nhiều process dùng chung refresh token.
3. **Atomic update** để chỉ ghi token mới nếu phiên bản record vẫn là bản đã đọc.
4. **Failure handling có điều kiện**, tránh xóa dữ liệu mới thành công vì lỗi của một refresh song song.
5. **Timeout/backoff có giới hạn** cho sự cố mạng; không retry vô hạn trên `invalid_grant`.
6. **Giới hạn parallel API calls** trong thời điểm token chuẩn bị hết hạn nếu provider rất nghiêm về rotation.
7. **Theo dõi refresh failures và reuse detection** từ IdP để cải thiện kiến trúc.

Không mặc định mọi ứng dụng phải tự viết distributed lock. Trước hết cần hiểu concurrency của manager, provider, storage và IdP hiện tại; chỉ thêm cơ chế phối hợp đúng mức cần thiết.

## 12. Những lỗi refresh thường gặp

### 12.1. `invalid_grant` tại Token Endpoint

Ví dụ:

```json
{
  "error": "invalid_grant"
}
```

Nguyên nhân có thể:

- Refresh token hết hạn.
- Refresh token đã bị revoke khi user logout/revoke consent.
- Token đã được sử dụng trước đó và bị vô hiệu do rotation.
- Refresh token thuộc client khác.
- Chính sách IdP yêu cầu reauthentication.
- Request gửi sai refresh token hoặc sai client context.

**Không xem `invalid_grant` là lỗi mạng tạm thời để retry vô hạn cùng token.** Manager có thể được cấu hình failure handler loại authorized client không còn hợp lệ; với user-specific Authorization Code, ứng dụng có thể cần đưa người dùng vào luồng login/consent mới.

### 12.2. `invalid_client`

Thường liên quan xác thực client ở Token Endpoint: secret sai/hết hiệu lực, client authentication method không khớp hoặc certificate/JWT assertion không hợp lệ.

Giải pháp là sửa cấu hình client/secret, không tạo refresh token mới và không tắt TLS.

### 12.3. Provider trả thành công nhưng API vẫn 401/403

Cần phân biệt:

- **401 ở Token Endpoint:** vấn đề client authentication/token grant.
- **401 ở Resource Server:** token sai/hết hạn/bị revoke, audience hoặc chữ ký không được chấp nhận.
- **403 ở Resource Server:** token có thể được xác thực nhưng thiếu scopes/roles/policy permission.

Làm mới access token **không tự tạo thêm quyền** cho API nếu provider không cấp scope/audience mới.

### 12.4. Refresh token biến mất sau restart hoặc đổi pod

Nếu authorized client chỉ nằm trong **RAM của một JVM**, pod mới không có bản lưu cũ. Session web có thể vẫn tồn tại qua một shared session store, nhưng token store không tự trở thành shared nếu đang dùng in-memory service.

Cần kiểm tra thực tế repository/service wiring và yêu cầu persistence. Chuyển sang JDBC/custom shared store nếu phải giữ refresh token qua deployment.

## 13. Quan sát lifecycle một cách an toàn

Một số metadata có thể dùng để theo dõi:

```text
registrationId=corporate
principalRef=<internal-correlation-id>
grantAttempt=refresh_token
accessTokenExpiresAt=...
refreshAttemptStartedAt=...
refreshOutcome=success
```

Không log:

```text
refresh_token=...
access_token=...
Authorization: Basic ...
client_secret=...
Cookie: JSESSIONID=...
```

Với hệ thống nhiều tenant, không đưa full user ID, raw token, email hoặc `principalName` nhạy cảm vào metric labels có cardinality lớn.

Các tín hiệu vận hành đáng quan sát:

| Chỉ số/sự kiện | Ý nghĩa |
| --- | --- |
| `oauth2_refresh_attempt` | Số lần manager thực sự gọi refresh grant |
| `oauth2_refresh_success` | Đã nhận token response hợp lệ |
| `oauth2_refresh_failure{error=invalid_grant}` | Refresh token hết hạn/rotate/revoked |
| `oauth2_refresh_failure{error=invalid_client}` | Cấu hình/xác thực client sai |
| `oauth2_token_endpoint_latency` | Độ trễ Token Endpoint |
| `oauth2_authorized_client_missing` | Không tìm thấy record đã lưu |
| `oauth2_access_token_expiry_remaining` | Thời gian còn lại trước khi cần refresh |
| `oauth2_api_401` / `oauth2_api_403` | Resource Server từ chối request sau khi gửi token |

Đây là **tên sự kiện gợi ý**, không phải metrics mặc định được Spring Security bảo đảm phát ra.

## 14. Các lỗi về thời gian, session và refresh

### 14.1. Clock skew khác token lifetime

Provider dùng `accessToken.getExpiresAt()` với clock skew để tránh gửi access token sắp hết hạn. Clock skew không biến token hết hạn thành hợp lệ và không kéo dài lifetime của refresh token.

Nếu máy chạy backend lệch giờ nghiêm trọng, hãy đồng bộ đồng hồ hệ thống. Đừng tăng clock skew tùy ý để che lỗi NTP.

### 14.2. Session của người dùng hết hạn

Trong web app, người dùng có thể bị logout vì session timeout trong khi authorized-client store vẫn giữ refresh token. Điều đó **không tự chứng minh** user được phép tiếp tục thực hiện nghiệp vụ có yêu cầu authenticated session.

Cần tách hai chính sách:

- **Web authentication session**: còn cho browser truy cập website hay không.
- **OAuth2 token authorization**: có thể lấy access token mới để gọi API hay không.

Một refresh token còn hiệu lực không phải lý do tự động cho browser tái đăng nhập mà không qua chính sách session/reauthentication của ứng dụng.

### 14.3. Logout và revocation

| Hành động | Hệ quả |
| --- | --- |
| Xóa SecurityContext/session | Browser không còn phiên authenticated theo cấu hình |
| `removeAuthorizedClient` | Xóa bản token local theo registration/principal |
| Refresh Token Revocation Endpoint | Authorization Server nhận yêu cầu thu hồi refresh token theo policy |
| OIDC RP-Initiated Logout | Xử lý phiên SSO phía IdP, không mặc định revoke mọi token |
| Rotation R1 -> R2 | Cập nhật chuỗi refresh token theo policy của provider |

Logout session **không bảo đảm** mọi authorized clients đã bị xóa. Local removal **không bảo đảm** refresh token đã revoke ở IdP. Khi yêu cầu bảo mật cao, cần thiết kế logout, revocation và session invalidation đồng bộ theo chính sách.

## 15. Tùy biến token response client: lưu ý về TLS và proxy

Token Endpoint thường nằm trong mạng doanh nghiệp hoặc qua egress proxy. Các lỗi có thể xuất hiện khi provider cố refresh:

| Hiện tượng | Nguyên nhân có thể | Hướng điều tra |
| --- | --- | --- |
| `UnknownHostException` | DNS trong pod không phân giải Token Endpoint | DNS/service discovery của container |
| Connect timeout | Firewall, NAT, NetworkPolicy, proxy | Kiểm tra tuyến egress |
| `PKIX path building failed` | JVM/HTTP client không tin CA | Truststore, certificate chain |
| Hostname verification failed | TLS certificate không khớp hostname | SAN, SNI, proxy interception |
| HTTP 407 | Proxy yêu cầu xác thực | Proxy credentials/chính sách |
| HTTP 429 | Rate limit Token Endpoint | Throttle, backoff, token reuse |
| HTTP 503 | Provider tạm không khả dụng | Retry bounded, circuit breaker, incident |
| Token response parse error | Nhận HTML/WAF page hoặc JSON sai chuẩn | URL thực tế và HTTP response đã ẩn dữ liệu |

Cần biết **HTTP client thực sự được `RefreshTokenOAuth2AuthorizedClientProvider` dùng để gọi Token Endpoint**, không chỉ `RestClient`/`WebClient` do ứng dụng tự dùng để gọi API. Tùy phiên bản Spring Security, điểm mở rộng của token response client khác nhau.

Không vô hiệu certificate validation để vượt lỗi TLS. Refresh token và client credentials đều là dữ liệu nhạy cảm cần HTTPS.

## 16. Kiểm tra hành vi khi refresh: các tình huống đáng có

Những trường hợp dưới đây giúp hiểu thiết kế provider và manager. Đây là **tình huống học tập**, không phải kết quả một bộ test đã chạy.

| Ca | Authorized client hiện tại | Kết quả mong đợi của provider/manager |
| --- | --- | --- |
| Không có authorized client | `null` | Refresh provider không tự xin token bằng refresh grant |
| Có access token, không có refresh token | Chỉ access token A | Không thể dùng refresh token grant |
| Có refresh token, access token còn hạn | A còn thời gian | Không refresh khi chưa đến ngưỡng |
| Có refresh token, access token gần hết hạn | A sắp hết hạn | Có thể refresh theo clock skew |
| Token Endpoint cấp access token B | A + R1 | Tạo authorized client mới với B |
| Token Endpoint trả R2 mới | A + R1 | Lưu token mới theo response, không tiếp tục dùng R1 nếu đã rotate |
| Token Endpoint không trả refresh token mới | A + R1 | Áp dụng logic giữ/diễn giải refresh token theo thư viện và provider |
| Token Endpoint `invalid_grant` | A + R1 không hợp lệ | Không retry vô hạn; xử lý lỗi và policy cleanup |
| Token Endpoint timeout | A + R1 | Không giả thành successful refresh; lỗi mạng theo policy |
| Session mất nhưng token store còn | Có refresh token local | Không bypass session authentication |
| Hai request refresh cùng R1 | Shared authorized client | Phải xét concurrency/rotation |
| Restart JVM với in-memory service | Mất record | Không thể refresh nếu không còn refresh token |
| API trả 403 sau refresh | B vẫn tồn tại | Kiểm tra scope/permission ở Resource Server |

### 16.1. Ví dụ định hướng test bằng `Clock`

Để kiểm thử ngưỡng thời gian một cách tái lập, cấu hình provider bằng clock có thể điều khiển:

```java
Clock fixedClock = Clock.fixed(
    Instant.parse("2026-11-16T02:00:00Z"),
    ZoneOffset.UTC);

var provider = new RefreshTokenOAuth2AuthorizedClientProvider();
provider.setClock(fixedClock);
provider.setClockSkew(Duration.ofSeconds(60));
```

Đoạn này chỉ **đặt thời gian đầu vào**. Để test logic provider, cần một `OAuth2AuthorizationContext` chứa authorized client và một `OAuth2AccessTokenResponseClient<OAuth2RefreshTokenGrantRequest>` test double/mocked phù hợp, sau đó xác nhận có/không có token request khi thay `expiresAt` tương ứng.

Đừng dùng `Thread.sleep(...)` nhiều phút chỉ để chờ access token hết hạn; dùng clock kiểm soát được giúp test nhanh và ổn định.

## 17. Tình huống thực hành

### Tình huống A — Access token hết hạn trong khi user vẫn còn session

Người dùng đã login OIDC từ sáng. Buổi chiều website vẫn nhận `JSESSIONID`, nhưng backend gọi Reports API bằng access token A đã hết hạn.

**Hướng xử lý:** kiểm tra `OAuth2AuthorizedClient` của user có refresh token không; đảm bảo manager đã cấu hình `refreshToken()`, dùng đúng repository và gọi `authorize(...)` trước khi gửi access token. Không yêu cầu browser login lại nếu refresh grant hợp lệ và policy cho phép.

### Tình huống B — Manager không refresh dù có access token đã hết hạn

Code lấy `OAuth2AuthorizedClientService.loadAuthorizedClient(...)` rồi gắn token vào HTTP header trực tiếp.

**Nguyên nhân:** `loadAuthorizedClient` chỉ là phép đọc; nó không gọi provider. Cần sử dụng manager/HTTP client OAuth2 integration được cấu hình đúng.

### Tình huống C — Có `offline_access` nhưng refresh token là null

Provider không cấp refresh token vì policy, consent hoặc cấu hình client.

**Hướng xử lý:** kiểm tra token response, allowed scopes/grants, provider documentation và thời điểm xin consent. `offline_access` không tự bảo đảm issuance. Không tự suy ra refresh token từ ID Token.

### Tình huống D — Hai request đồng thời làm refresh token bị revoke

Provider dùng rotation; hai request cùng refresh bằng R1. Một request nhận R2, request còn lại trả `invalid_grant`, đôi khi khiến phiên token mới bị xóa theo failure handling.

**Hướng xử lý:** phân tích manager/storage concurrency, sử dụng coordination/atomic update nếu cần; không vô hiệu lỗi `invalid_grant` hoặc retry vô hạn R1.

### Tình huống E — Restart pod làm mất refresh token

Ứng dụng lưu authorized clients trong RAM, không có persistent storage. Sau deployment, login session có thể khôi phục từ shared session nhưng authorized client không còn.

**Hướng xử lý:** xác định token store thực tế; nếu cần persistence, dùng JDBC/shared store và bảo vệ refresh token. Không trông đợi in-memory service tự chia sẻ qua pod.

### Tình huống F — Token mới nhưng API vẫn trả `403`

Refresh thành công, access token B có hạn mới, nhưng API báo thiếu `reports.admin`.

**Hướng xử lý:** kiểm tra scopes đã cấp và chính sách Resource Server. Refresh grant không mở rộng quyền so với grant ban đầu hoặc tự phê duyệt scope admin.

### Tình huống G — Client secret đã rotate

Refresh request báo `invalid_client` dù R1 chưa hết hạn.

**Hướng xử lý:** kiểm tra client authentication method, secret version, issuer/realm và cách Token Response Client dùng credential mới. Không coi mọi lỗi refresh là refresh token hết hạn.

### Tình huống H — Muốn refresh access token của client_credentials

Backend registration `client_credentials` có access token A nhưng **không có refresh token**; developer chỉ thêm `refreshToken()` vào provider chain.

**Hướng xử lý:** dùng `.clientCredentials()` với manager phù hợp để **xin access token mới bằng client credentials**. Grant này khác với `refresh_token`.

## 18. Những hiểu nhầm cần tránh

**“Cứ có `RefreshTokenOAuth2AuthorizedClientProvider` là mọi access token tự được refresh theo lịch.”** Sai. Provider chỉ được gọi khi manager/ứng dụng thực hiện authorize phù hợp; nó không có scheduler nội bộ.

**“Provider có thể tự lấy refresh token từ ID Token.”** Sai. Refresh token là credential riêng do Authorization Server cấp theo chính sách.

**“Access token hết hạn thì `loadAuthorizedClient(...)` tự refresh.”** Sai. Storage chỉ load record.

**“Có `offline_access` là chắc chắn nhận refresh token.”** Sai. Provider có thể yêu cầu consent, policy và cấu hình riêng.

**“`refreshToken()` cũng giúp client_credentials xin token mới.”** Không đúng bản chất. Với `client_credentials`, cần provider cho chính grant đó; refresh token thường không được cấp.

**“Refresh trả 200 nên session người dùng tự cập nhật mọi quyền.”** Không. Token mới và Authentication/session/authorities là những vòng đời có thể khác nhau.

**“Token Endpoint trả `invalid_grant` thì retry liên tục là được.”** Không. Refresh token có thể đã hết hạn, revoke hoặc rotate; retry có thể làm sự cố nặng hơn.

**“Map thread-safe đủ để giải quyết refresh token rotation giữa nhiều pod.”** Không. Cần xét concurrency/atomic update ở cả provider và store.

**“Xóa authorized client local là đã revoke refresh token tại IdP.”** Không. Phải dùng cơ chế revocation phù hợp nếu chính sách yêu cầu.

**“Access token mới chắc chắn có quyền gọi mọi API.”** Không. Resource Server còn kiểm tra audience/scopes và chính sách nghiệp vụ.

## 19. Câu hỏi ôn tập

**1. `RefreshTokenOAuth2AuthorizedClientProvider` có nhiệm vụ gì?**

Nó là provider thực hiện **Refresh Token Grant** khi authorized client đã có refresh token, access token cần làm mới và Token Endpoint chấp nhận request.

**2. Ai thường gọi provider này?**

`OAuth2AuthorizedClientManager` thông qua provider chain đã cấu hình, ví dụ với `OAuth2AuthorizedClientProviderBuilder.builder().authorizationCode().refreshToken().build()`.

**3. Trả `null` từ provider có chắc là lỗi?**

Không. Có thể token chưa cần refresh hoặc không đủ điều kiện dùng refresh grant. Manager xử lý kết quả theo ngữ cảnh và chain.

**4. Vì sao không thể refresh khi `OAuth2AuthorizedClient.getRefreshToken()` là null?**

Vì refresh grant cần refresh token được Authorization Server cấp trước đó; provider không thể tự tạo credential.

**5. Refresh có cần browser redirect hoặc authorization code mới không?**

Không khi refresh token hợp lệ. Đây là **back-channel Token Request** tới Token Endpoint.

**6. `clockSkew` ảnh hưởng điều gì?**

Giúp coi access token đến ngưỡng cần refresh **trước** expiry thực tế để giảm nguy cơ token hết hạn trong lúc gọi API.

**7. `DefaultOAuth2AuthorizedClientManager` thích hợp khi nào?**

Khi sử dụng OAuth2 Client trong **HTTP Servlet request** cùng `OAuth2AuthorizedClientRepository`.

**8. Background job muốn dùng refresh token của authorized client đã lưu thì manager nào phù hợp?**

`AuthorizedClientServiceOAuth2AuthorizedClientManager`, với provider chain thích hợp và `OAuth2AuthorizedClientService`.

**9. Refresh token rotation có thể gây lỗi gì khi hai request chạy song song?**

Cả hai dùng R1; một request được cấp R2, request khác có thể nhận `invalid_grant`, thậm chí kích hoạt chính sách reuse detection. Cần xem xét coordination và lưu token nhất quán.

**10. Tại sao xóa local token không đồng nghĩa revoke tại IdP?**

Vì local storage và Authorization Server là hai hệ thống khác nhau; revocation cần quy trình/endpoint riêng.

**11. Refresh token có thuộc OIDC ID Token không?**

Không. ID Token xác thực danh tính, refresh token dùng xin access token mới tại Token Endpoint.

**12. Vì sao API vẫn có thể trả `403` sau refresh thành công?**

Vì access token mới có thể thiếu scope/role/quyền phù hợp với API đích. Refresh không bảo đảm mở rộng quyền.

**13. Nếu app dùng `client_credentials`, provider nào cần được bật?**

`clientCredentials()` trong provider builder cho grant đó; không dựa vào `refreshToken()` khi không có refresh token.

**14. Có thể dựa vào `@RegisteredOAuth2AuthorizedClient` ở một scheduled job không?**

Không. Annotation dành cho cơ chế resolve argument trong web handler; tác vụ ngoài request nên dùng manager/service-based API phù hợp.

**15. Khi nào cần chọn storage bền vững thay in-memory?**

Khi phải giữ refresh token qua restart/rolling deployment, chia sẻ giữa nhiều instance, hoặc cần coordination, audit, cleanup và revocation theo chính sách.

## 20. Tài liệu tham khảo

- [Spring Security Reference — OAuth 2.0 Client (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html)
- [Spring Security Reference — Authorized Clients (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html)
- [Spring Security API — RefreshTokenOAuth2AuthorizedClientProvider](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/RefreshTokenOAuth2AuthorizedClientProvider.html)
- [Spring Security API — OAuth2AuthorizedClientProvider](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/OAuth2AuthorizedClientProvider.html)
- [Spring Security API — OAuth2AuthorizedClientProviderBuilder](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/OAuth2AuthorizedClientProviderBuilder.html)
- [Spring Security API — DefaultOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizedClientManager.html)
- [Spring Security API — AuthorizedClientServiceOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html)
- [Spring Security API — OAuth2AuthorizedClient](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/client/OAuth2AuthorizedClient.html)
- [Spring Security Reference — OAuth 2.0 Client (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html)
- [RFC 6749 — Refreshing an Access Token](https://www.rfc-editor.org/rfc/rfc6749#section-6)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700)
- [OpenID Connect Core 1.0 — Refresh Token Flow](https://openid.net/specs/openid-connect-core-1_0.html#RefreshTokens)

**Ghi nhớ:** `RefreshTokenOAuth2AuthorizedClientProvider` là **chiến lược Refresh Token Grant trong Spring Security Servlet**, không phải timer hoặc token store. Nó chỉ làm mới khi authorized client đã có refresh token và access token đến ngưỡng cần refresh. Manager điều phối provider và lưu authorized client sau khi cấp lại; repository/service giữ dữ liệu, còn Authorization Server quyết định token mới có được cấp hay không. Bảo vệ refresh token, chọn đúng manager cho request/background task, xử lý `invalid_grant` và refresh token rotation thận trọng, đồng thời nhớ rằng **refresh access token không thay thế OIDC Login, web session hay phân quyền của Resource Server**.
