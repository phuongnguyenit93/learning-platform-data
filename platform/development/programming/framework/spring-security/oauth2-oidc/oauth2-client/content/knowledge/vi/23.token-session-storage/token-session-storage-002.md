# 23.2. Lựa chọn lưu token trong bộ nhớ, session hoặc cơ sở dữ liệu

Trong **Spring Security OAuth 2.0/OIDC Client**, đăng nhập thành công chỉ là một phần của bài toán. Ứng dụng còn cần quyết định **lưu trạng thái xác thực, access token và refresh token ở đâu**, lưu trong bao lâu, ai có thể đọc chúng và điều gì xảy ra khi người dùng đăng xuất, ứng dụng restart hoặc một instance khác tiếp tục xử lý công việc.

Một ứng dụng thử nghiệm chạy một JVM có thể hoạt động tốt với `InMemoryOAuth2AuthorizedClientService`. Nhưng khi triển khai ba pods sau load balancer, dùng refresh token rotation, hoặc cần đồng bộ dữ liệu nhiều ngày sau khi người dùng đóng trình duyệt, lựa chọn đó có thể không còn phù hợp. Ngược lại, lưu mọi token vào database không phải lúc nào cũng tối ưu: nó tăng trách nhiệm bảo vệ thông tin nhạy cảm, quản lý schema, mã hóa, đồng bộ và dọn dữ liệu.

Bài học này giải thích và so sánh ba hướng **lưu trong bộ nhớ**, **lưu theo HTTP session/WebSession** và **lưu bằng cơ sở dữ liệu**. Trọng tâm là **token phía server của OAuth2/OIDC Client**, không phải cách Resource Server xác minh JWT. Nội dung bao gồm mô hình Spring Security, ví dụ cấu hình Java, quản lý multi-instance, refresh token rotation, logout, bảo mật, chiến lược migration và các tình huống chọn giải pháp.

> **Nguyên tắc quan trọng:** Trước khi hỏi “token được lưu ở đâu?”, phải xác định **đang lưu loại dữ liệu nào**: `OAuth2AuthorizationRequest` trước callback, `Authentication/SecurityContext` sau đăng nhập, hay `OAuth2AuthorizedClient` chứa access/refresh token để gọi API. Chúng có vòng đời và cơ chế lưu khác nhau.

## 1. Bức tranh toàn cảnh: không chỉ có một “token store”

Trong hệ thống OAuth2/OIDC Login, nhiều trạng thái xuất hiện ở các thời điểm khác nhau:

| Dữ liệu | Mục đích | Ví dụ | Thời điểm cần tồn tại |
|---|---|---|---|
| `ClientRegistration` | Cấu hình Client ID, grant, endpoint, scopes | `company-login` | Theo cấu hình ứng dụng |
| `OAuth2AuthorizationRequest` | Ghi nhớ authorization flow trước callback | `state`, PKCE verifier, redirect URI | Từ lúc redirect tới khi callback hoàn tất |
| `SecurityContext` / `Authentication` | Đại diện người dùng đã xác thực trong ứng dụng | `OAuth2AuthenticationToken`, `OidcUser` | Theo chính sách đăng nhập/session |
| **`OAuth2AuthorizedClient`** | Mang access token và có thể refresh token cùng registration/principal | Token dùng gọi Calendar API | Đến khi token/ủy quyền không còn cần hoặc không hợp lệ |
| Business connection | Liên kết tài khoản nội bộ với external provider | `account_id`, `connection_status` | Theo vòng đời nghiệp vụ |
| Audit record | Ghi nhận thao tác login/link/refresh/revoke | Thời gian, mã kết quả | Theo retention policy |

Một ví dụ đầy đủ:

```text
ClientRegistration
  registrationId = calendar
  grant = authorization_code
  provider = company-op

Authorization Request (tạm thời)
  state = random...
  redirectUri = https://portal.example.test/login/oauth2/code/calendar
  PKCE verifier / OIDC nonce nếu áp dụng

SecurityContext
  Authentication = user đã xác minh
  Principal = OidcUser

OAuth2AuthorizedClient
  registrationId = calendar
  principalName = user-782
  accessToken = AT-1
  refreshToken = RT-1 (nếu được cấp)

Business Connection
  internalAccountId = a9e...
  externalIdentity = (verified iss, sub)
  status = CONNECTED
```

**Các trạng thái này không nhất thiết nằm cùng một nơi.** Ví dụ:

- Authorization request lưu tạm trong `HttpSession`.
- SecurityContext lưu theo session.
- Authorized client lưu trong JDBC database.
- Business connection nằm trong bảng nghiệp vụ riêng.
- ClientRegistration lấy từ `application.yml` hoặc một cấu hình đáng tin.

Do đó “chuyển toàn bộ session sang Redis” không tự động đồng nghĩa “mọi authorized client token đã được chuyển sang Redis”.

## 2. Access token, refresh token và ID Token có vai trò khác nhau

### 2.1. Access token

Access token dùng gọi **Resource Server**:

```http
GET /v1/calendars HTTP/1.1
Host: api.example.test
Authorization: Bearer EXAMPLE_ACCESS_TOKEN
```

Access token thường có thời hạn ngắn. Với Bearer token, bên nào có token có thể sử dụng nó trong phạm vi quyền mà API chấp nhận, nên phải bảo vệ cả ở memory, database, session store và log.

### 2.2. Refresh token

Refresh token dùng tại **Token Endpoint** để xin access token mới, nếu Authorization Server đã cấp. Nó có thể có thời hạn dài hơn và có giá trị bảo mật cao.

```http
POST /oauth2/token HTTP/1.1
Host: login.example.test
Authorization: Basic EXAMPLE_CLIENT_CREDENTIALS
Content-Type: application/x-www-form-urlencoded

grant_type=refresh_token&refresh_token=EXAMPLE_REFRESH_TOKEN
```

Refresh token có thể **hết hạn, bị thu hồi, rotation hoặc reuse detection**. Lưu nó bền vững không đảm bảo nó tiếp tục hợp lệ mãi mãi.

### 2.3. ID Token

ID Token là thành phần OIDC dùng Client xác minh danh tính người dùng, chứa các claim như `iss`, `sub`, `aud` và thời gian. **Không dùng ID Token làm Bearer token cho downstream API**, trừ khi một giao thức/hợp đồng API riêng quy định rõ điều khác — không nên coi đó là mặc định OAuth2/OIDC.

### 2.4. Token không đồng nhất với phiên đăng nhập

```text
HTTP Session / SecurityContext:
  "Người dùng đang được ứng dụng xác thực"

OAuth2AuthorizedClient:
  "Ứng dụng có token để gọi Resource Server theo một grant"
```

Một người dùng vẫn có session đăng nhập portal nhưng refresh token cho Calendar API đã bị thu hồi. Ngược lại, một tác vụ đồng bộ đã được người dùng ủy quyền trước đó có thể có refresh token hợp lệ dù phiên trình duyệt hiện tại đã hết hạn — **nếu chính sách offline access/consent cho phép**.

Hai vòng đời phải được xác định độc lập, không lấy session timeout làm thời hạn mặc định của mọi refresh token.

## 3. Vòng đời OAuth2/OIDC Login và các điểm lưu

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser
    participant App as Spring OAuth2/OIDC Client
    participant Sess as Session Store
    participant Authz as Authorized Client Store
    participant AS as Authorization Server
    participant API as Resource Server

    U->>B: Bắt đầu đăng nhập
    B->>App: GET /oauth2/authorization/company
    App->>Sess: Lưu OAuth2AuthorizationRequest (state/PKCE/nonce)
    App-->>B: Redirect tới Authorization Endpoint
    B->>AS: User login / consent
    AS-->>B: Callback code + state
    B->>App: GET /login/oauth2/code/company
    App->>Sess: Tải và tiêu thụ authorization request
    App->>AS: POST Token Endpoint (authorization_code)
    AS-->>App: Access token, ID token, refresh token?
    App->>App: Xác minh OIDC / xây Authentication
    App->>Sess: Lưu SecurityContext theo cấu hình
    App->>Authz: Lưu OAuth2AuthorizedClient
    App-->>B: Login thành công
    B->>App: GET /calendar
    App->>Authz: Tìm token của user/registration
    App->>API: Bearer access token
    API-->>App: Kết quả
```

Có ba vị trí rõ ràng:

1. **Trước callback:** authorization request cần tồn tại ngắn hạn và bị ràng buộc với trình duyệt.
2. **Sau callback:** SecurityContext giữ trạng thái người dùng đã đăng nhập theo chính sách.
3. **Khi gọi API:** authorized client chứa access token và, nếu có, refresh token để manager sử dụng.

Mỗi loại có repository riêng; tránh trộn dữ liệu chỉ vì chúng đều liên quan OAuth2.

## 4. Các abstraction lưu token trong Spring Security Servlet

Trong ứng dụng Spring MVC/Servlet, những interface thường gặp:

| API | Công việc chính | Đặc điểm |
|---|---|---|
| `ClientRegistrationRepository` | Tra cấu hình các Clients | Không phải token store |
| `OAuth2AuthorizedClient` | Dữ liệu authorized client đã có token | Chứa credential nhạy cảm |
| **`OAuth2AuthorizedClientService`** | Lưu/tra/xóa authorized client theo registration và principal | Không cần `HttpServletRequest` |
| **`OAuth2AuthorizedClientRepository`** | Lưu/tra authorized client gắn với HTTP request và principal | Có `HttpServletRequest` và `HttpServletResponse` |
| `InMemoryOAuth2AuthorizedClientService` | Lưu authorized clients trong memory của JVM | Dễ dùng, không bền vững |
| `JdbcOAuth2AuthorizedClientService` | Lưu authorized clients qua JDBC | Bền vững khi database được quản lý đúng |
| `HttpSessionOAuth2AuthorizedClientRepository` | Lưu authorized clients bằng Servlet `HttpSession` | Gắn token với session trình duyệt |
| `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` | Repository có thể ủy quyền tới service với principal đã xác thực, dùng repository cho principal chưa xác thực | Cầu nối web request và service |
| `DefaultOAuth2AuthorizedClientManager` | Điều phối token trong Servlet request | Thường dùng repository |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | Điều phối token ngoài Servlet request | Thường dùng service |

Điểm dễ nhầm:

**`InMemoryOAuth2AuthorizedClientService` không phải `HttpSessionOAuth2AuthorizedClientRepository`.** Dù cả hai có thể dùng RAM, chúng có **phạm vi dữ liệu và lifecycle khác nhau**.

### 4.1. Service và repository có chữ ký khác nhau

`OAuth2AuthorizedClientService` có các phương thức tiêu biểu:

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

Đây là cách trình bày chữ ký trọng tâm; nullability annotations và chi tiết API phụ thuộc version.

`OAuth2AuthorizedClientRepository` có thêm context request/response:

```java
<T extends OAuth2AuthorizedClient> T loadAuthorizedClient(
    String clientRegistrationId,
    Authentication principal,
    HttpServletRequest request
);

void saveAuthorizedClient(
    OAuth2AuthorizedClient authorizedClient,
    Authentication principal,
    HttpServletRequest request,
    HttpServletResponse response
);

void removeAuthorizedClient(
    String clientRegistrationId,
    Authentication principal,
    HttpServletRequest request,
    HttpServletResponse response
);
```

**Service** phù hợp cho scheduled job và hoạt động không có browser request. **Repository** phù hợp khi quyền truy cập authorized client phụ thuộc HTTP session/request.

### 4.2. Khóa dữ liệu thường là `(registrationId, principalName)`

Ví dụ:

```text
("google", "user-782")   -> AT-1, RT-1
("calendar", "user-782") -> AT-2, RT-2
("google", "user-996")   -> AT-3, RT-3
```

Hai authorized clients của cùng user có thể thuộc hai providers khác nhau. Cùng registration nhưng principal khác thì phải tách token.

**Không dùng chỉ `registrationId` làm khóa** cho access token theo user: làm vậy có thể khiến user B nhận token của user A.

### 4.3. Principal name không phải email mặc định của toàn hệ thống

`Authentication#getName()` có thể được xác định từ `OidcUser`, `OAuth2User` hoặc custom principal name. Nếu hệ thống nhiều providers/tenants, cần xác định danh tính bền vững và phân vùng tenant đúng cách.

Việc mapping tài khoản nội bộ nên dựa trên external identity đã xác minh như `(iss, sub)` trong OIDC, không tự động ghép theo email. Nhưng **khóa của authorized client service** vẫn phải nhất quán với principal name mà framework đã dùng khi lưu token, tránh đổi tên không kiểm soát.

## 5. So sánh ba lựa chọn: memory, session, database

| Tiêu chí | Memory của JVM | HTTP Session / WebSession | Database |
|---|---|---|---|
| Ví dụ Servlet | `InMemoryOAuth2AuthorizedClientService` | `HttpSessionOAuth2AuthorizedClientRepository` | `JdbcOAuth2AuthorizedClientService` |
| Phạm vi | Theo process/instance | Theo phiên trình duyệt/ngữ cảnh session | Theo kho dùng chung, thường registration + principal |
| Qua nhiều requests | Có, nếu instance và key phù hợp | Có, nếu cùng session còn tồn tại | Có |
| Qua restart | Không | Có thể không; tùy session store bền vững | Thường có |
| Multi-instance | Mỗi JVM riêng | Cần shared session store hoặc affinity | Có thể dùng chung database |
| Không có HTTP request | Có, qua service manager | Không phù hợp với thuần session repository | Có, qua service manager |
| Tự đăng xuất/xóa session có xóa token? | Không mặc định | Token session thường mất theo session | Không mặc định |
| Tốt cho user-delegated offline jobs | Không lý tưởng nếu cần restart durability | Thường không | Thường phù hợp hơn, nếu provider cấp refresh token |
| Dễ cấu hình | Rất dễ | Trung bình | Cao hơn: schema, DB, security |
| Rủi ro cần chú ý | Mất state, per-node token, memory | Cookie theft/session fixation, expiry, session replication | Tập trung nhiều credential, DB breach, rotation/race |
| Dọn dẹp | Theo vòng đời process hoặc explicit remove | Theo session expiry/logout + explicit remove | Cần retention/cleanup rõ ràng |
| Chi phí truy cập | Thấp | Thấp đến trung bình, tùy store | DB I/O, connection pool, schema ops |
| Khi mở rộng | Dễ phát sinh token requests trùng | Cần session architecture | Cần concurrency và capacity planning |

Bảng là **định hướng**, không phải định luật. Một memory store có thể được bọc bằng cache phân tán, và một session có thể được lưu trong Redis. Khi ấy phải phân biệt **abstraction API** với **hạ tầng vật lý**.

## 6. Lựa chọn 1: lưu authorized client trong bộ nhớ

### 6.1. `InMemoryOAuth2AuthorizedClientService` hoạt động thế nào?

`InMemoryOAuth2AuthorizedClientService` là implementation của `OAuth2AuthorizedClientService` lưu authorized clients trong RAM của tiến trình Spring Boot.

Đặc điểm:

- Token sống qua nhiều HTTP requests nếu cùng JVM và principal/registration mapping nhất quán.
- Không đòi database, migration hay Redis.
- Token bị mất khi JVM/process restart hoặc instance bị thay thế.
- Hai pods có hai memory stores khác nhau.
- Không tự liên kết token với một browser session cụ thể.
- Service có thể được dùng ngoài HTTP request thông qua service-based manager.

Điểm cuối cùng đặc biệt quan trọng: **memory service vẫn có thể lưu token sau khi user đã đóng tab**, nếu process còn chạy và code giữ record; không suy ra nó tự xóa khi cookie/session hết hạn.

### 6.2. Ví dụ cấu hình Servlet

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.InMemoryOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class InMemoryTokenStorageConfig {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
            ClientRegistrationRepository registrations) {

        return new InMemoryOAuth2AuthorizedClientService(registrations);
    }
}
```

Cấu hình này tạo một **service** lưu token trong process. Khi Spring Boot đã tự tạo service tương ứng, không nên khai báo thêm bean trùng hoặc gây inject ambiguity. Tùy phiên bản Boot và cách bạn đăng ký bean, auto-configuration có thể back off khi thấy bean do ứng dụng cung cấp.

### 6.3. Dùng qua authorized client manager ngoài HTTP request

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Bean
OAuth2AuthorizedClientManager serviceClientManager(
        ClientRegistrationRepository registrations,
        OAuth2AuthorizedClientService authorizedClients) {

    var manager = new AuthorizedClientServiceOAuth2AuthorizedClientManager(
        registrations, authorizedClients
    );

    manager.setAuthorizedClientProvider(
        OAuth2AuthorizedClientProviderBuilder.builder()
            .clientCredentials()
            .build()
    );

    return manager;
}
```

Với grant `client_credentials`, đây là một cách triển khai đơn giản cho job hệ thống. Token mất sau restart thường không nghiêm trọng nếu job vẫn có Client credentials an toàn để xin token mới và Authorization Server không giới hạn quá chặt.

### 6.4. Khi nào memory là lựa chọn hợp lý?

- Ứng dụng học tập, demo, integration test.
- Một instance phát triển.
- Client Credentials Grant có thể cấp lại dễ dàng và token không cần durability.
- Hệ thống không cần tiếp tục user-delegated sync sau restart.
- Một tính năng không giữ refresh token lâu dài, và session/consent lifecycle được thiết kế riêng.

### 6.5. Khi nào memory không phù hợp?

- Cần giữ refresh token của user sau deploy/restart.
- Chạy nhiều pods với tải phân tán.
- Job background phải tiếp tục đồng bộ hàng ngày.
- Token Endpoint có rate limit thấp, mỗi instance xin token lại quá nhiều.
- Cần audit/lifecycle token rõ ràng hoặc quản trị thu hồi trên các node.
- Muốn session logout lập tức xóa mọi token nhưng không có cơ chế cleanup.

### 6.6. Đừng tạo “token cache String” thay service của Spring

```java
// KHÔNG NÊN:
private static String accessToken;
```

Một biến toàn cục không mang theo `registrationId`, principal, scope, expiresAt, refresh token hay metadata. Nó tạo nguy cơ trộn user, token hết hạn và race condition. Nếu cần lưu trong memory, hãy dùng abstraction `OAuth2AuthorizedClientService` hoặc một implementation tương thích có đầy đủ lifecycle.

## 7. Lựa chọn 2: lưu authorized client theo Servlet HTTP session

### 7.1. `HttpSessionOAuth2AuthorizedClientRepository`

Trong Servlet MVC, `HttpSessionOAuth2AuthorizedClientRepository` lưu authorized client gắn với `HttpSession` của HTTP request.

```text
Browser A:
  SESSION=A
  -> AuthorizedClient(company) của ngữ cảnh session A

Browser B:
  SESSION=B
  -> AuthorizedClient(company) của ngữ cảnh session B
```

Nếu Browser A mất cookie hoặc session hết hạn, repository thường không còn tìm được token đã lưu trong session đó. Đây là behavior khác với `InMemoryOAuth2AuthorizedClientService` vốn tồn tại độc lập với session.

### 7.2. Ví dụ bean và cấu hình OAuth2 Login

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.web.HttpSessionOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class HttpSessionTokenStorageConfig {

    @Bean
    OAuth2AuthorizedClientRepository authorizedClientRepository() {
        return new HttpSessionOAuth2AuthorizedClientRepository();
    }

    @Bean
    SecurityFilterChain securityFilterChain(
            HttpSecurity http,
            OAuth2AuthorizedClientRepository authorizedClientRepository)
            throws Exception {

        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(login -> login
                .authorizedClientRepository(authorizedClientRepository)
            )
            .oauth2Client(client -> client
                .authorizedClientRepository(authorizedClientRepository)
            );

        return http.build();
    }
}
```

Đây là **mẫu lựa chọn session repository tường minh**. Với cấu hình thực tế có nhiều `SecurityFilterChain` hoặc nhiều bean repositories, cần đảm bảo cùng repository được dùng ở bước login và các bước gọi API. Không dán code này cùng một security chain khác có cùng matcher mà không xét thứ tự.

### 7.3. Session cookie có chứa access token không?

Với mô hình **server-side HttpSession** thông thường:

- Browser giữ một cookie chứa **session identifier**.
- Token và authorized client nằm trong **server-side session store**, không được nhúng trực tiếp vào cookie.
- Cookie không phải một access token OAuth2.

Nhưng session ID vẫn là credential nhạy cảm: nếu bị đánh cắp, kẻ xấu có thể chiếm phiên. Vì vậy cần `Secure`, `HttpOnly`, `SameSite` phù hợp, HTTPS, session fixation protection và chính sách timeout.

**Không coi cookie session là an toàn tuyệt đối** chỉ vì không chứa token trực tiếp.

### 7.4. Khi nào session repository phù hợp?

- Portal chủ yếu gọi API **trong khi người dùng đang online**.
- Không có yêu cầu background processing sau khi session kết thúc.
- Muốn token liên kết với vòng đời session.
- Từng user/browser session có token riêng và UX yêu cầu login lại sau session timeout.
- Có session store nhất quán và được bảo vệ trong môi trường multi-instance.

### 7.5. Những giới hạn cần biết

- Session hết hạn có thể làm mất authorized client ngay cả khi refresh token vẫn còn hiệu lực tại OP.
- Tác vụ `@Scheduled` không có `HttpServletRequest`; session repository không phải abstraction tự nhiên cho background jobs.
- Nhiều browser sessions của cùng user có thể có những authorized clients khác nhau.
- Nếu dùng local in-memory sessions với load balancing không sticky, callback/request sau có thể tới node không có session.
- Nếu lưu session phân tán, vẫn phải xét serialization, mạng, TTL và bảo mật Redis/database session store.

### 7.6. Đăng xuất có tự revoke token tại Authorization Server không?

**Không mặc định.** Khi logout:

- Ứng dụng có thể invalidate local HttpSession.
- Token trong session store có thể bị xóa theo session.
- Authorization Server **có thể vẫn coi access/refresh token đã cấp là hợp lệ**.
- Resource Server có thể tiếp tục chấp nhận một access token đã cấp cho tới khi nó hết hạn hoặc bị thu hồi theo cơ chế provider.

Nếu yêu cầu ngắt quyền ở IdP, cần thực hiện **token revocation** khi provider hỗ trợ, theo chính sách và RFC 7009. Session logout, OIDC RP-Initiated Logout và OAuth2 token revocation là **ba cơ chế khác nhau**.

## 8. `AuthenticatedPrincipalOAuth2AuthorizedClientRepository`: cầu nối dễ bị hiểu nhầm

Trong nhiều cấu hình Spring Security Servlet, `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` đóng vai trò điều phối:

- Với **principal đã xác thực**, nó có thể ủy quyền lưu/tìm authorized client cho `OAuth2AuthorizedClientService`.
- Với **principal chưa xác thực**, nó có thể dùng một `OAuth2AuthorizedClientRepository` dự phòng, thường liên quan session.

Minh họa:

```text
HTTP request
  -> AuthenticatedPrincipalOAuth2AuthorizedClientRepository
      |
      +-- principal đã authenticated
      |     -> OAuth2AuthorizedClientService
      |         -> InMemory hoặc JDBC
      |
      +-- principal chưa authenticated
            -> HttpSessionOAuth2AuthorizedClientRepository
```

### 8.1. Vì sao điều này quan trọng?

Giả sử:

```java
@Bean
OAuth2AuthorizedClientService authorizedClientService(
        ClientRegistrationRepository registrations) {
    return new InMemoryOAuth2AuthorizedClientService(registrations);
}
```

Và framework sử dụng một repository ủy quyền tới service cho principal đã xác thực. Khi đó token của user **có thể được lưu trong memory service**, không phải chỉ trong HttpSession, dù ứng dụng đăng nhập bằng HTTP session.

Tương tự, nếu service là JDBC và repository của web login dùng service đó, token sau login có thể nằm ở database.

**Đừng suy luận token storage chỉ bằng việc nhìn thấy `HttpSession` hoặc cấu hình session cookie.** Cần kiểm tra bean `OAuth2AuthorizedClientRepository` thực tế đã được nối với `OAuth2AuthorizedClientService` nào.

### 8.2. Ví dụ cấu hình cầu nối

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.web.AuthenticatedPrincipalOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.OAuth2AuthorizedClientRepository;

@Bean
OAuth2AuthorizedClientRepository authorizedClientRepository(
        OAuth2AuthorizedClientService service) {

    return new AuthenticatedPrincipalOAuth2AuthorizedClientRepository(
        service
    );
}
```

Khi muốn chắc chắn bean này được dùng trong OAuth2 Login và các OAuth2 Client components, gắn repository vào các cấu hình liên quan. Tránh khai báo cùng lúc thêm `HttpSessionOAuth2AuthorizedClientRepository` cùng type mà không có qualifier hoặc explicit wiring.

### 8.3. Khi nào nên dùng cầu nối này?

- Có OAuth2 Login cho browser nhưng muốn lưu token của authenticated users bằng service.
- Cần một storage service chung cho cả web calls và background jobs.
- Muốn thay in-memory bằng JDBC mà không sửa toàn bộ controller dùng authorized client.
- Muốn cấu hình một fallback repository cho các flow chưa authenticated.

Không có nghĩa constructor mặc định của mọi framework version chọn cùng một storage: luôn kiểm tra bean thực tế và dependency version.

## 9. Lựa chọn 3: lưu authorized client trong cơ sở dữ liệu

### 9.1. `JdbcOAuth2AuthorizedClientService`

Spring Security cung cấp `JdbcOAuth2AuthorizedClientService` để triển khai `OAuth2AuthorizedClientService` bằng JDBC.

Khác với memory:

- Token có thể tồn tại qua ứng dụng restart.
- Nhiều instances có thể dùng cùng database.
- Background worker có thể tìm authorized client theo registration/principal.
- Việc lưu refresh token lâu dài làm **tăng yêu cầu bảo mật** của database.
- Phải triển khai schema, migration, housekeeping, monitoring và khóa truy cập đúng.

### 9.2. Ví dụ cấu hình JDBC

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.oauth2.client.JdbcOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;

@Configuration
public class JdbcTokenStorageConfig {

    @Bean
    OAuth2AuthorizedClientService authorizedClientService(
            JdbcTemplate jdbcTemplate,
            ClientRegistrationRepository registrations) {

        return new JdbcOAuth2AuthorizedClientService(
            jdbcTemplate,
            registrations
        );
    }
}
```

Cần có Spring JDBC, `DataSource` và schema tables tương thích. Để demo, bean có thể dùng JDBC store trực tiếp; trong production, nên quản lý schema bằng Flyway/Liquibase hoặc migration pipeline của tổ chức.

**Không khai báo cả `InMemoryOAuth2AuthorizedClientService` và `JdbcOAuth2AuthorizedClientService` cùng là ứng viên injection mặc định**, trừ khi chủ ý dùng nhiều stores với `@Qualifier` hoặc cấu hình phân vùng.

### 9.3. Schema cần chứa những gì?

Schema JDBC chính thức của Spring Security có các thành phần khái niệm:

```text
oauth2_authorized_client
  client_registration_id
  principal_name
  access_token_type
  access_token_value
  access_token_issued_at
  access_token_expires_at
  access_token_scopes
  refresh_token_value (nullable)
  refresh_token_issued_at (nullable)
  created_at
```

Thường khóa định danh là `(client_registration_id, principal_name)`.

Các cột token value chứa **dữ liệu nhạy cảm**, không phải chỉ metadata. Lưu ý:

- Chọn schema chính thức **đúng phiên bản Spring Security và database dialect**.
- JDBC types cho token bytes, timestamp, timezone cần phù hợp driver.
- Có thể phải điều chỉnh BLOB/BYTEA/VARBINARY theo database.
- Không tự tạo schema tối giản rồi mặc định `JdbcOAuth2AuthorizedClientService` sẽ đọc/ghi được.
- Dùng migration versioned, không bật auto-drop bảng token trong production.
- Không cấp quyền `SELECT *` bảng token cho nhân viên/ứng dụng không cần thiết.

### 9.4. SQL minh họa ở mức mô hình

Ví dụ **mô hình khái niệm**, không phải DDL chính thức có thể áp trực tiếp cho mọi dialect:

```sql
-- PSEUDOCODE / SCHEMA Ý TƯỞNG
CREATE TABLE oauth2_authorized_client (
    client_registration_id VARCHAR(100) NOT NULL,
    principal_name VARCHAR(200) NOT NULL,
    access_token_value BLOB NOT NULL,
    access_token_expires_at TIMESTAMP NOT NULL,
    refresh_token_value BLOB NULL,
    created_at TIMESTAMP NOT NULL,
    PRIMARY KEY (client_registration_id, principal_name)
);
```

Nếu chỉ tạo các cột trên, repository JDBC chuẩn **có thể không hoạt động** vì còn thiếu các cột/kiểu mà implementation mong đợi. Dùng schema tài liệu/source theo version thư viện và kiểm thử migration với database mục tiêu.

### 9.5. Có phải JDBC tự mã hóa token khi lưu không?

Không nên mặc định vậy. `JdbcOAuth2AuthorizedClientService` là abstraction persistence; yêu cầu **mã hóa token** cần được kiểm tra độc lập với:

- Encryption at rest của database/disk/backup.
- Cơ chế KMS/key management của hạ tầng.
- Khả năng mã hóa ở tầng ứng dụng trước khi ghi token.
- Khả năng giải mã đúng khi manager cần dùng refresh token.
- Chính sách rotate encryption keys và truy cập vận hành.

Một database bật encryption at rest vẫn có thể trả plaintext token cho database account được cấp quyền đọc. Do đó cần nguyên tắc **least privilege**, audit, secret management và hạn chế truy vấn trực tiếp.

### 9.6. Khi nào JDBC phù hợp?

- Cần user-delegated API connections có refresh token tồn tại sau restart.
- Background workers chạy ngoài phiên trình duyệt.
- Multi-instance cần cùng kho authorized clients.
- Cần kiểm soát retention, revocation và trạng thái kết nối.
- Có sẵn database được quản trị tốt, backup, migration và monitoring.
- Dùng Authorization Code Grant với offline access khi provider thực sự cấp token phù hợp.

**Lưu bền vững không tự kéo dài hiệu lực token.** Sau thời hạn hoặc khi user revoke, JDBC record vẫn có thể tồn tại nhưng refresh grant trả `invalid_grant`.

## 10. Cách liên kết JDBC service với ứng dụng web

Chỉ khai báo JDBC service chưa đủ nếu mọi web calls đang dùng một session repository tách rời.

Một mô hình cấu hình có chủ đích:

```mermaid
flowchart TD
    Web["Servlet OAuth2 Login / WebClient"] --> Repo["OAuth2AuthorizedClientRepository"]
    Repo --> Bridge["AuthenticatedPrincipalOAuth2AuthorizedClientRepository"]
    Bridge --> Service["JdbcOAuth2AuthorizedClientService"]
    Job["@Scheduled / background"] --> Manager["AuthorizedClientServiceOAuth2AuthorizedClientManager"]
    Manager --> Service
    Service --> DB["Shared database"]
```

Với authenticated principals, repository có thể ủy quyền authorized-client storage sang JDBC service. Background manager cũng dùng service đó, nên có khả năng tra **cùng record**, miễn là đúng registration/principal và user đã được ủy quyền.

### 10.1. Chú ý `principalName` khi web login và worker truy xuất

Một rủi ro:

```text
Web login lưu:
  registrationId = calendar
  principalName  = "user-oidc-782"

Worker tìm:
  registrationId = calendar
  principalName  = "account-42"

=> Không tìm thấy authorized client.
```

Không tự sửa bằng cách đưa một principal ngẫu nhiên tới manager. Cần thiết kế mapping nhất quán từ internal account/connection tới **principalName thực tế đã được lưu**.

Nếu user thay đổi `principalName` vì custom `OidcUserService`, migration phải được cân nhắc. Không tự lấy email làm unique identity khi liên kết nhiều OpenID Providers.

### 10.2. Những token nào nên nằm trong database?

Không bắt buộc mọi token đều phải lưu:

- Access token ngắn hạn có thể nằm trong authorized client record cùng refresh token để tiện manager.
- Refresh token có thể cần bền vững nếu worker phải tiếp tục sau restart.
- ID Token có thể có mặt trong OIDC authentication state, nhưng không phải thành phần bắt buộc của `OAuth2AuthorizedClient` API.
- Authorization code không nên được lưu dài hạn; nó là one-time short-lived credential.
- Client secret/private key là **Client authentication credential** và nên được quản lý riêng bởi secret manager, không trộn vào bảng authorized client.
- Cookie session identifiers là cơ chế quản lý session, không phải token API.

Cần phân loại dữ liệu theo mục đích, thay vì tạo một “all_tokens” table lưu mọi loại token như plaintext.

## 11. Reactive WebFlux: bộ nhớ, WebSession và reactive persistence

Nếu ứng dụng dùng **Spring WebFlux**, các API storage và manager thuộc nhánh reactive:

| Servlet | Reactive WebFlux |
|---|---|
| `OAuth2AuthorizedClientService` | `ReactiveOAuth2AuthorizedClientService` |
| `OAuth2AuthorizedClientRepository` | `ServerOAuth2AuthorizedClientRepository` |
| `HttpSessionOAuth2AuthorizedClientRepository` | `WebSessionServerOAuth2AuthorizedClientRepository` |
| `InMemoryOAuth2AuthorizedClientService` | `InMemoryReactiveOAuth2AuthorizedClientService` |
| `DefaultOAuth2AuthorizedClientManager` | `DefaultReactiveOAuth2AuthorizedClientManager` |
| `AuthorizedClientServiceOAuth2AuthorizedClientManager` | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` |
| `HttpServletRequest` | `ServerWebExchange` |
| `HttpSession` | `WebSession` |

Không đưa `HttpSessionOAuth2AuthorizedClientRepository` vào `SecurityWebFilterChain` của WebFlux; các contract giữa Servlet và Reactive khác nhau.

### 11.1. WebSession token repository

Một ví dụ tạo repository dựa trên WebSession:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.web.server.ServerOAuth2AuthorizedClientRepository;
import org.springframework.security.oauth2.client.web.server.WebSessionServerOAuth2AuthorizedClientRepository;

@Bean
ServerOAuth2AuthorizedClientRepository webSessionAuthorizedClients() {
    return new WebSessionServerOAuth2AuthorizedClientRepository();
}
```

Repository này gắn authorized clients với WebSession. Khi WebSession hết hạn hoặc không truy xuất được, token trong đó không còn sẵn cho request tiếp theo qua repository.

### 11.2. Reactive service trong memory

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.client.InMemoryReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientService;
import org.springframework.security.oauth2.client.registration.ReactiveClientRegistrationRepository;

@Bean
ReactiveOAuth2AuthorizedClientService reactiveAuthorizedClientService(
        ReactiveClientRegistrationRepository registrations) {

    return new InMemoryReactiveOAuth2AuthorizedClientService(registrations);
}
```

Khái niệm vẫn giống Servlet: in-memory service không đòi HTTP WebSession nhưng state mất khi process restart. Với reactive service lưu bền vững, hãy chọn implementation hỗ trợ database/backend phù hợp với **phiên bản Spring Security** và mô hình non-blocking I/O. Một ứng dụng có thể tự triển khai `ReactiveOAuth2AuthorizedClientService` với cơ chế bảo vệ token, nhưng không nên gọi JDBC blocking trực tiếp trên Reactor event-loop.

### 11.3. Authorized client manager Reactive ngoài HTTP request

`AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` dùng reactive service mà không buộc có một `ServerWebExchange` browser.

Đây là lựa chọn phù hợp khi:

- Consumer xử lý queue.
- Job chạy theo định kỳ.
- Tác vụ service-to-service dùng Client Credentials Grant.
- Job user-delegated dùng một authorized client đã được người dùng cấp và lưu theo đúng policy.

Nó **không tự hiển thị màn hình OIDC consent** trong background. Nếu refresh token hết hạn hoặc bị thu hồi, cần reauthorization có sự tham gia của user khi provider yêu cầu.

## 12. Spring Session và lưu session phân tán

Khi cần multi-instance, một hướng là **Spring Session** với Redis hoặc backend hỗ trợ. Ví dụ:

```text
Browser
  └── SESSION cookie
       |
       v
Load Balancer
  ├── Pod A
  ├── Pod B
  └── Pod C
       |
       v
Shared Redis / session store
```

Nếu cả ba pods dùng một shared session store tương thích, callback OAuth2 Login và các requests tiếp theo có thể đọc cùng session dù load balancer chuyển request sang pod khác.

### 12.1. Spring Session Redis giúp gì?

- Chia sẻ Servlet `HttpSession` hoặc Reactive `WebSession` theo tích hợp tương ứng.
- Giảm phụ thuộc vào session affinity khi pods thay đổi.
- Hỗ trợ TTL và session lifecycle tập trung.
- Có thể lưu security context và những session attributes được framework đưa vào session.
- Nếu authorized client repository **thực sự lưu trong session**, authorized client cũng có thể được lưu theo session đó khi serialization/configuration hoạt động.

### 12.2. Spring Session Redis **không** tự làm gì?

- Không tự chuyển `InMemoryOAuth2AuthorizedClientService` trong từng JVM thành store Redis.
- Không tự lưu token mà ứng dụng đã đưa vào một static map khác.
- Không tự thu hồi token tại Authorization Server khi session bị xóa.
- Không tự giải quyết refresh token rotation race.
- Không thay database-backed `OAuth2AuthorizedClientService` nếu web/worker vẫn cần tokens sau session expiry.
- Không làm cookie/session an toàn nếu Redis không có ACL/TLS/secret management.

### 12.3. Ví dụ dependencies/session config

Với ứng dụng Spring Boot dùng Spring Session Redis:

```kotlin
dependencies {
    implementation("org.springframework.session:spring-session-data-redis")
}
```

Cấu hình kết nối **minh họa**:

```yaml
spring:
  data:
    redis:
      host: redis.internal.example.test
      port: 6379
```

Cần thêm Redis authentication, TLS, namespace, connection settings, session timeout, serialization và retention theo môi trường. Với Spring Boot version khác, cấu hình Redis/Session có thể thay đổi; dùng tài liệu version đang chạy.

### 12.4. Sticky session hay distributed session?

| Lựa chọn | Ưu điểm | Giới hạn |
|---|---|---|
| Sticky sessions | Đơn giản khi khởi đầu, ít I/O shared store | Restart/failover làm mất session; affinity không bảo đảm tuyệt đối |
| Shared session store | Nhiều pods đọc session nhất quán theo cấu hình | Cần Redis/network/serializer/TTL và security |
| Token JDBC service | Token bền vững độc lập session | Không tự thay session store cho authorization request/SecurityContext |
| Kết hợp session store + token DB | Phân biệt login state và API credentials | Nhiều thành phần hơn, cần lifecycle coordination |

Một kiến trúc **có thể cần cả session store và token database**. Chúng giải quyết hai lớp trạng thái khác nhau, không phải chọn duy nhất một trong mọi hoàn cảnh.

## 13. Chọn lưu token theo yêu cầu nghiệp vụ

### 13.1. Trường hợp A: demo chạy một instance

```text
Single Spring Boot instance
  + OAuth2 Login demo
  + call API khi người dùng đang online
  + không cần token sau restart
```

Một in-memory authorized client service hoặc session repository có thể đủ. Ưu tiên đơn giản để tập trung vào flow OIDC.

Rủi ro cần chấp nhận: restart có thể mất token/session và buộc đăng nhập/cấp quyền lại.

### 13.2. Trường hợp B: portal web có session ngắn hạn

```text
Spring MVC portal
  + user đăng nhập
  + gọi API khi browser còn phiên
  + logout/session expiry chấm dứt việc sử dụng token
```

Session repository có thể phù hợp, đặc biệt khi sản phẩm không hỗ trợ offline jobs. Nếu scale-out, cần shared session store hoặc một giải pháp session architecture tương đương.

**Kiểm tra kỹ:** user logout local không tự revoke provider refresh token. Nếu mục tiêu là chấm dứt authorization tại OP, phải xử lý revocation riêng.

### 13.3. Trường hợp C: đồng bộ lịch mỗi đêm theo quyền user

```text
User kết nối Calendar bằng authorization_code + offline consent
  -> app lưu authorized client với refresh token
  -> @Scheduled mỗi đêm đồng bộ
  -> user có thể đã đóng trình duyệt
```

Thường cần một **service-backed persistent store** cho authorized client, và service-based manager cho worker. JDBC hoặc một kho phân tán an toàn có thể phù hợp.

Đồng thời:

- Chỉ dùng token user đã thực sự ủy quyền.
- Có trạng thái `RECONNECT_REQUIRED` khi refresh token bị từ chối.
- Có cơ chế consent/permission, unlink, retention và audit.
- Không biến logout session thành mặc định xóa mọi kết nối offline nếu sản phẩm đã xin quyền offline riêng; nhưng phải truyền đạt rõ quyền tiếp tục hoạt động.

### 13.4. Trường hợp D: service-to-service bằng `client_credentials`

```text
Job hệ thống
  -> OAuth2 Token Endpoint client_credentials
  -> Reporting API
```

Nếu token có thể xin mới bằng Client credential khi hết hạn, memory service có thể là lựa chọn hợp lý, kể cả một số production services có một pod hoặc pods độc lập, miễn là rate limit và policy cho phép.

Persistent JDBC không tự cần thiết trong mọi trường hợp, vì không có refresh token user phải giữ qua restart.

### 13.5. Trường hợp E: nhiều pods và user sessions

Nếu browser login phải hoạt động khi load balancer chuyển qua các pods, cần thiết kế session sharing hoặc routing. JDBC token store **không đủ** để phục hồi `OAuth2AuthorizationRequest` đã lưu trong session nếu callback không tìm được phiên ban đầu.

Dùng shared session store cho login state; dùng token service store phù hợp cho authorized clients.

## 14. Sơ đồ quyết định chọn kho lưu

```mermaid
flowchart TD
    A["Bạn đang cần lưu gì?"] --> B{"Loại trạng thái?"}
    B -->|AuthorizationRequest / SecurityContext| S["Thiết kế HTTP/WebSession + session lifecycle"]
    B -->|OAuth2AuthorizedClient| C{"Cần sử dụng token ngoài browser session?"}
    C -->|Không| D{"Token có cần tồn tại sau session expiry?"}
    D -->|Không| E["Session repository là một lựa chọn"]
    D -->|Có| F["Service-backed store phù hợp"]
    C -->|Có| G{"Cần tồn tại qua restart/multi-node?"}
    G -->|Không| H["InMemory service có thể phù hợp"]
    G -->|Có| I["Persistent/shared service: JDBC hoặc backend phù hợp"]
    S --> J{"Nhiều instances?"}
    J -->|Có| K["Shared session store / routing policy"]
    J -->|Không| L["Local session có thể đủ"]
    F --> M["Xác định TTL, refresh, revocation và cleanup"]
    E --> M
    H --> M
    I --> M
    K --> M
    L --> M
```

Sơ đồ mang tính định hướng. Trước khi chọn cuối cùng, kiểm tra các yêu cầu về bảo mật, vận hành, tuân thủ, hiệu năng và khả năng phục hồi.

## 15. Refresh token rotation là yếu tố quyết định kiến trúc

Một trong những thách thức lớn nhất khi lưu token ở database/shared service là **refresh token rotation**.

Giả sử authorized client chứa:

```text
registration = calendar
principal    = user-782
accessToken  = AT-1 (sắp hết hạn)
refreshToken = RT-1
```

Khi refresh:

```text
Client gửi RT-1
Authorization Server trả AT-2 + RT-2
Client phải cập nhật authorized client:
  accessToken  = AT-2
  refreshToken = RT-2
```

Nếu database vẫn lưu RT-1, lần refresh tiếp theo có thể bị `invalid_grant`.

### 15.1. Nhiều instances cùng refresh một token

```mermaid
sequenceDiagram
    autonumber
    participant A as Pod A
    participant B as Pod B
    participant DB as Token Database
    participant AS as Authorization Server

    A->>DB: Load calendar/user-782: RT-1
    B->>DB: Load calendar/user-782: RT-1
    A->>AS: POST refresh_token=RT-1
    AS-->>A: AT-2, RT-2
    A->>DB: Save AT-2, RT-2
    B->>AS: POST refresh_token=RT-1
    AS-->>B: invalid_grant
    Note over A,B: Có thể kích hoạt reuse detection
```

**JDBC lưu chung không đồng nghĩa “refresh chỉ thực hiện một lần trên toàn cluster”.** Cần cân nhắc:

- Single-flight refresh theo `(registrationId, principalName)`.
- Distributed lock khi dùng cùng refresh token.
- Version/optimistic locking để tránh stale write.
- Cơ chế reload token mới nhất trước khi kết luận kết nối đã hỏng.
- Chính sách xử lý token family revocation khi provider phát hiện reuse.
- Retry có giới hạn; **không retry `invalid_grant` bằng cùng refresh token vô hạn**.

### 15.2. In-memory có tránh được race không?

Không hoàn toàn. Cùng JVM vẫn có thể có hai HTTP requests/concurrent jobs refresh đồng thời. In-memory storage giảm một số vấn đề distributed, nhưng không tự bảo đảm single-flight refresh.

### 15.3. Session store có tránh được race không?

Cũng không mặc định. Hai requests từ cùng một browser session hoặc hai tabs có thể cùng refresh. Nếu session được chia sẻ Redis, các nodes còn có thể xử lý token đồng thời.

### 15.4. Retry sau network timeout có nguy hiểm không?

Có. Authorization Server có thể đã xử lý RT-1 và phát hành RT-2, nhưng Client timeout trước khi nhận response. Gửi lại RT-1 có thể bị coi là reuse.

Không xem refresh token grant là operation idempotent. Cần chiến lược phù hợp với provider; trong một số trường hợp không thể phục hồi token mới một cách an toàn và phải yêu cầu người dùng cấp quyền lại.

## 16. Xử lý token bị thu hồi và `invalid_grant`

Token lưu bền vững vẫn có thể bị Authorization Server từ chối vì:

- User thu hồi consent.
- Quản trị viên disable account/revoke sessions.
- Refresh token hết hạn tuyệt đối hoặc theo idle timeout.
- Refresh token rotation đã thay token cũ.
- Client ID/credential/registration thay đổi không tương thích.
- Provider phát hiện token replay.

Theo OAuth2, Token Endpoint có thể trả:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "error": "invalid_grant"
}
```

**Không đồng nhất `invalid_grant` với “database mất token”.** Có thể database giữ đúng token, nhưng chính IdP đã không còn chấp nhận nó.

### 16.1. Spring Security failure handlers

Các `OAuth2AuthorizedClientManager` có cơ chế failure handlers. Với nhiều cấu hình mặc định của Servlet managers:

- Khi authorization thành công, authorized client mới được lưu qua repository/service.
- Khi refresh thất bại vì `invalid_grant`, authorized client đã lưu có thể được loại bỏ để tránh tái sử dụng refresh token hỏng.

Nếu ứng dụng thay `setAuthorizationFailureHandler(...)` chỉ để log một dòng, có thể vô tình **mất hành vi cleanup** mặc định. Khi custom, phải hiểu hợp đồng của manager và thiết kế cleanup an toàn, đặc biệt với concurrency.

### 16.2. Resource Server 401/403 khác lỗi refresh

| Lỗi | Nguồn | Ý nghĩa điển hình |
|---|---|---|
| `invalid_grant` | Token Endpoint | Refresh grant/code không còn hợp lệ |
| `invalid_client` | Token Endpoint | Client ID/secret/auth method không hợp lệ |
| `invalid_scope` | Token Endpoint | Scope xin không được phép |
| HTTP 401 `invalid_token` | Resource Server | Access token bị từ chối |
| HTTP 403 `insufficient_scope` | Resource Server | Token thiếu quyền API |

Không xóa mọi refresh token vì API trả 403 thiếu scope; refresh theo cùng scope cũng không tự cấp quyền mới.

### 16.3. Tách trạng thái kết nối nghiệp vụ

Ví dụ:

```text
oauth_connection:
  id = connection-42
  internal_account_id = account-7
  registration_id = calendar
  principal_name = user-782
  status = RECONNECT_REQUIRED
```

Khi refresh token đã lỗi, ứng dụng có thể:

1. Không tiếp tục retry cùng refresh token.
2. Dọn authorized client lỗi qua cơ chế an toàn.
3. Giữ **business connection metadata** để UI biết người dùng từng liên kết.
4. Đánh dấu `RECONNECT_REQUIRED`.
5. Yêu cầu user bắt đầu một Authorization Code/OIDC flow mới nếu cần.
6. Sau callback hợp lệ, lưu token mới và chuyển lại `CONNECTED`.

Không xóa toàn bộ internal account chỉ vì một kết nối API bên ngoài bị thu hồi.

## 17. Session timeout, logout và token expiry không trùng nhau

| Sự kiện | SecurityContext/session | OAuth2AuthorizedClient | Authorization Server |
|---|---|---|---|
| Access token hết hạn | Session có thể còn | Có thể refresh nếu có credential | Quyết định có cấp token mới |
| Refresh token bị revoke | Session có thể còn | Credential không còn dùng được | Từ chối refresh |
| Browser đóng tab | Session có thể còn | Service-backed client có thể còn | Không tự revoke |
| Local logout/invalidate session | Local Authentication bị xóa | Tùy store và cleanup | Không mặc định revoke |
| App restart | Local in-memory session có thể mất | In-memory service mất; JDBC còn | Token tại AS vẫn theo policy |
| User chọn Disconnect | Tùy chính sách app | Nên xóa đúng authorized client | Có thể cần gọi revocation endpoint |
| OP session hết hạn | Local app session có thể còn | Refresh có thể hoạt động hoặc không theo policy | OP quy định |
| Internal account bị disable | App phải chặn theo authorization | Token store có thể còn cho audit cho tới cleanup | OP không nhất thiết biết ngay |

**Tách ba trục thời gian:** local authentication/session, access/refresh token validity, và trạng thái ủy quyền ở OP.

### 17.1. Logout không đồng nghĩa revocation

- Xóa cookie/session không thu hồi access token mà API đã nhận.
- Xóa authorized client trong database không tự gọi Authorization Server.
- Gọi OIDC RP-Initiated Logout chủ yếu xử lý phiên tại OP; behavior token revocation tùy provider.
- Token Revocation RFC 7009 là cơ chế riêng, thường áp dụng khi Client chủ động ngắt quyền theo policy.

Nếu sản phẩm yêu cầu “đăng xuất mọi thiết bị”, phải thiết kế session invalidation, token revocation và Resource Server enforcement phù hợp, không chỉ xóa một row trong bảng token.

## 18. Bảo mật dữ liệu token ở từng vị trí

### 18.1. Memory: ưu tiên bảo vệ process

Token trong memory có thể bị lộ qua:

- Heap dump trong môi trường debug.
- Core dump/crash report.
- APM hoặc log serialization.
- Debug endpoint không được bảo vệ.
- Lỗ hổng remote code execution trong JVM.
- Quyền truy cập process/container quá rộng.

Biện pháp:

- Không in token khi debug.
- Hạn chế quyền truy cập heap dump.
- Tắt hoặc bảo vệ công cụ remote diagnostics.
- Không mở actuator endpoints nhạy cảm ra Internet.
- Áp dụng chính sách process/container isolation.
- Không lưu token trong static maps tùy tiện với TTL vô hạn.

### 18.2. Session: bảo vệ cookie và session store

- `Secure` và HTTPS cho session cookie.
- `HttpOnly` hạn chế JavaScript đọc cookie.
- `SameSite` phù hợp với OIDC redirect/callback, kể cả `form_post` nếu dùng.
- Chống session fixation và quản lý session ID rotation.
- Giới hạn session timeout hợp lý.
- Bảo vệ session store như Redis, không cho public access.
- Không ghi `JSESSIONID`/`SESSION` thật vào log.
- Không chia sẻ session namespace giữa environments/tenants nếu không được thiết kế.

Với server-side session, trình duyệt thường giữ ID cookie, không giữ raw access/refresh token. Nhưng nếu cookie bị chiếm, kẻ tấn công vẫn có thể lạm dụng quyền của phiên.

### 18.3. Database: bảo vệ token ở trạng thái lưu

- Principle of least privilege cho database credentials.
- Encryption at rest của disk/DB/backup.
- Xem xét application-level encryption/KMS cho refresh token.
- Tách tài khoản DB của app với read-only analytics/admin.
- Giới hạn ai được query các cột `access_token_value` và `refresh_token_value`.
- Audit quyền truy cập và thay đổi schema.
- Backup encryption và chính sách xóa dữ liệu phù hợp.
- Secret rotation cho Client credentials và database credentials.
- Không đẩy token vào tracing, SQL logs hoặc CDC topics không được bảo vệ.

Nếu cần tìm kiếm token theo một khóa, nên truy vấn bằng **metadata registration/principal/connection ID**, không tìm theo raw token value.

### 18.4. Có nên hash refresh token trước khi lưu?

Nếu Client cần gửi lại **giá trị refresh token nguyên vẹn** tới Token Endpoint, chỉ lưu hash một chiều không đủ: không thể khôi phục token để sử dụng. Vì vậy:

- Hash một chiều phù hợp cho một số cơ chế **xác minh credential do chính hệ thống phát hành**.
- Với **OAuth2 Client phải sử dụng refresh token do OP cấp**, cần bảo vệ khả năng đọc token bằng mã hóa/kiểm soát truy cập.
- Không nhầm chính sách lưu hashed password với quy trình lưu refresh token dùng để tiếp tục grant.

### 18.5. Có cần mã hóa token ở tầng ứng dụng?

Tùy threat model. Nếu database administrator hoặc bản dump DB bị lộ là mối đe dọa quan trọng, application-level encryption có thể giúp giảm rủi ro, nhưng tạo thêm trách nhiệm:

- KMS/key rotation.
- Envelope encryption.
- Lưu version/kid của key.
- Đảm bảo decrypt trước khi manager dùng token.
- Không đưa key và ciphertext vào cùng một nơi dễ truy cập.
- Xử lý quá trình migration/re-encryption.
- Kiểm tra performance và failure modes.

Không tự nhận định rằng class JDBC mặc định của Spring Security đã cung cấp toàn bộ cơ chế encryption cần thiết.

## 19. Lưu token tại client/browser có phải lựa chọn thứ tư?

Bài này tập trung vào **OAuth2 Client backend**, nhưng cần phân biệt với kiến trúc SPA/public client:

- Token có thể được giữ tại browser memory hoặc một cơ chế khác theo threat model.
- Lưu Bearer token/refresh token trong `localStorage` có rủi ro đặc biệt từ XSS.
- Cookie HttpOnly dùng trong BFF/session architecture thường chứa session identifier, không nhất thiết chứa OAuth access token.
- Public client không thể bảo vệ Client secret như confidential backend.
- Refresh token cho browser cần ràng buộc bảo mật theo OAuth2 Best Current Practice/provider policy.

Không dùng lý do “session store nặng” để chuyển refresh token backend sang JavaScript localStorage mà không đánh giá kiến trúc và bảo mật. Nếu sản phẩm là BFF, backend có thể giữ tokens server-side và browser chỉ giữ cookie session.

## 20. Thiết kế BFF: session ở browser, token ở server

Một kiến trúc **Backend for Frontend (BFF)** điển hình:

```mermaid
flowchart LR
    Browser["SPA / Browser"] -->|"HttpOnly Secure session cookie"| BFF["Spring BFF"]
    BFF -->|"Auth state"| Session["Session store"]
    BFF -->|"OAuth2AuthorizedClient"| Tokens["Token service / DB"]
    BFF -->|"Bearer access token"| API["Resource Server"]
    BFF -->|"Token Endpoint"| AS["Authorization Server"]
```

Trình duyệt không cần trực tiếp nắm refresh token của OP. BFF:

1. Thực hiện OAuth2/OIDC Login.
2. Giữ session người dùng.
3. Tra authorized client cho đúng principal.
4. Gọi API bằng Bearer access token.
5. Làm mới token nếu được phép.
6. Chỉ trả dữ liệu nghiệp vụ cần thiết về browser.

Session store và token store có thể cùng nằm trong RAM ở demo, hoặc tách Redis + database trong production. Điều quan trọng là định nghĩa đúng ownership và lifecycle.

### 20.1. BFF không tự tránh được mọi CSRF

Nếu browser dùng cookie tự gửi theo request, BFF vẫn phải áp dụng CSRF protection cho thao tác thay đổi trạng thái theo policy, cùng SameSite/Origin checks khi phù hợp. Cookie HttpOnly không loại bỏ CSRF.

### 20.2. Không biến BFF thành open proxy

Nếu BFF cho browser chỉ định arbitrary API URL, sau đó tự gắn access token và gửi đi, có thể dẫn tới SSRF và token exfiltration. Hãy dùng allowlist origins, route cố định và kiểm soát redirect.

## 21. Multi-tenant, multi-provider và khóa principal

Một hệ thống có thể phục vụ nhiều tenants và nhiều OPs:

```text
Tenant A:
  issuer = https://id.example.test/realms/a
  user sub = 100

Tenant B:
  issuer = https://id.example.test/realms/b
  user sub = 100
```

Hai identities có cùng `sub` nhưng khác issuer **không phải một danh tính OIDC duy nhất**. Nếu stored token lookup dùng một principal key thiếu tenant/issuer, có nguy cơ truy xuất sai token.

Một thiết kế có thể:

- Liên kết `(verified iss, sub)` vào internal account.
- Dùng internal account/connection ID đáng tin để quản lý ownership.
- Đảm bảo `principalName` trong `OAuth2AuthorizedClientService` nhất quán với identity mapping.
- Không để tenant A truy vấn principal của tenant B.
- Với mỗi provider/ClientRegistration, kiểm soát issuer, audience và scopes.

### 21.1. Không lấy principal từ query parameter

Thiết kế nguy hiểm:

```java
// KHÔNG ĐƯỢC chọn token người khác dựa trên input trực tiếp:
String principal = request.getParameter("user");
OAuth2AuthorizedClient token =
    service.loadAuthorizedClient("calendar", principal);
```

Khi cần lấy token của một kết nối, phải kiểm tra user hiện tại **sở hữu connection** ấy; service từ đó mới truy vấn registration/principal được lưu và cấp quyền.

### 21.2. Dùng connection ID cho nghiệp vụ

Một mô hình có thể lưu:

```text
business_connection:
  id                   = connection-42
  account_id           = internal-account-7
  registration_id      = calendar
  authorized_principal = oidc-user-782
  external_issuer      = https://id.example.test/realms/a
  external_subject     = subject-A
  status               = CONNECTED
```

Token value không cần xuất hiện trong bảng nghiệp vụ này. Khi user ngắt kết nối, backend giải quyết đúng authorized client, xóa token theo policy và cập nhật connection status.

## 22. Chuyển từ memory/session sang database

Một dự án thường bắt đầu với memory store, sau đó muốn thêm background jobs/multi-instance. Đây là **migration về quyền truy cập và dữ liệu nhạy cảm**, không chỉ thay một bean.

### 22.1. Lộ trình triển khai an toàn

1. Xác định những ClientRegistrations đang được dùng.
2. Xác định authorized clients hiện lưu trong memory, session hay service.
3. Chọn một service store bền vững và migration schema tương thích.
4. Cấu hình repository/manager dùng store mới.
5. Xác định cách xử lý các sessions/tokens đã được lưu theo cơ chế cũ.
6. Đối chiếu principal names và internal account mapping.
7. Kiểm tra refresh token rotation khi user chuyển instance.
8. Kiểm thử callback OAuth2 Login vẫn khôi phục authorization request đúng.
9. Kiểm thử refresh lỗi, revoke/logout, reconnect và multi-node.
10. Có telemetry mà không log token, rollback plan không làm lộ credential.

### 22.2. Có thể migrate token đang nằm trong RAM không?

Có thể về mặt kỹ thuật nếu triển khai một migration an toàn ngay trong process, nhưng **không mặc định cần thiết hoặc dễ thực hiện**. Nhiều dự án chọn:

- Triển khai JDBC cho mọi login/authorization mới.
- Cho authorized clients cũ hết hạn theo policy.
- Yêu cầu user kết nối lại khi token cũ mất, với UX rõ ràng.
- Không cố dump toàn bộ refresh token vào file CSV hoặc log để chuyển thủ công.

Với khách hàng cần duy trì background integrations liên tục, có thể phải xây kế hoạch migration được kiểm thử riêng và xử lý rotation/ownership cẩn thận.

### 22.3. Đừng đổi principal key im lặng

Nếu trước đây token được lưu theo `principalName=user-782` và sau migration manager tra `account-id-7`, có thể báo “không tìm thấy token” dù row JDBC vẫn tồn tại. Hãy thống nhất schema/identity mapping và xử lý chuyển đổi có audit.

### 22.4. Token store mới không khắc phục lỗi authorization request session

Nếu callback OAuth2 Login bị `authorization_request_not_found` do cookie/session mất, việc chuyển authorized client sang JDBC không tự chữa được. Authorization request cần tồn tại **trước khi token được cấp**. Xử lý đúng nơi lưu `state`/PKCE/nonce và session routing.

## 23. Thiết kế dọn dẹp, TTL và retention

Một hệ thống cần chính sách dọn state ở nhiều lớp:

| Dữ liệu | Dọn khi nào? | Rủi ro nếu không dọn |
|---|---|---|
| Authorization request pending | Sau callback hoặc timeout | Lưu state/PKCE verifier quá lâu, nhầm flow |
| Local SecurityContext/session | Logout, timeout, revoke nội bộ theo policy | Session vẫn được dùng ngoài ý muốn |
| Access token record | Khi authorized client không còn cần, invalid hoặc cleanup policy | Token dư, dữ liệu nhạy cảm tích tụ |
| Refresh token record | Khi unlink/revoke/invalid_grant, theo consent/retention | Credential dài hạn tồn tại không cần thiết |
| Business connection | Disconnect, account deletion, policy retention | Trạng thái UI sai, dangling links |
| Audit | Theo chính sách tuân thủ | Lưu dữ liệu cá nhân vô thời hạn |
| Cached principal/role | Khi quyền thay đổi hoặc TTL | Quyền bị thu hồi nhưng cache còn |

### 23.1. Không xóa “mọi token hết hạn” quá đơn giản

Access token hết hạn nhưng authorized client có **refresh token còn hợp lệ** có thể cần được giữ để manager làm mới. Nếu housekeeping query xóa mọi row với `access_token_expires_at < now()`, nó có thể vô tình xóa luôn refresh token user cần cho offline jobs.

Cần phân biệt:

- Access token expired.
- Refresh token absent/expired/invalid.
- Business connection revoked/disconnected.
- Authorized client còn cần hay không.
- Chính sách provider và mốc thời gian có thể không được phản ánh đầy đủ trong DB.

### 23.2. Không giả định refresh token có TTL giống access token

OAuth2 token response `expires_in` thường mô tả access token. Thời hạn refresh token có thể do provider chính sách riêng, không phải lúc nào cũng trả explicit expiry. Lưu `refresh_token_issued_at` không đủ để tự tính tuổi thọ chính xác nếu provider không công bố policy.

### 23.3. Retention của database backup

Ngay cả sau khi xóa token khỏi bảng production, bản backup cũ có thể vẫn chứa credential nếu chưa hết thời hạn giữ backup. Cần bảo vệ backup, thiết kế expiration/rotation và quy trình incident response phù hợp.

## 24. Hiệu năng và chi phí vận hành

### 24.1. Memory nhanh nhưng không miễn phí

- Mỗi authorized client chiếm RAM.
- Số users/connections tăng có thể làm memory store lớn.
- Không có TTL tự nhiên cho mọi record trừ khi application/storage xử lý.
- Sau restart có thể gây nhiều token grants đồng thời.
- Mỗi pod có token riêng và tần suất xin token cao.

### 24.2. Session store có chi phí network/serialization

Nếu dùng Redis/session DB:

- Mỗi lần đọc/ghi session có thể tạo network I/O.
- Object session có thể gồm OAuth2Authentication/authorized clients cần serialize.
- Session payload lớn làm tăng latency và storage.
- Session expiry có thể mất state đang chờ callback.
- Serialization có thể không tương thích khi rolling deployment giữa versions.

### 24.3. JDBC service có chi phí database

- Query theo registration/principal.
- Update khi refresh access token/refresh token.
- Connection pool và throughput.
- Migration/indexes và backup.
- Encryption/decryption nếu có.
- Lock/contention khi refresh đồng thời.
- Dọn rows và bảo vệ dữ liệu nhạy cảm.

Không mặc định token DB là nút thắt cổ chai: hãy đo workload thực tế. Nhiều OAuth2 Clients gọi API ít lần có thể dùng JDBC rất hiệu quả. Hệ thống nhiều calls/s nên cân nhắc caching có invalidation, nhưng không tạo cơ chế token reuse không an toàn.

### 24.4. Không đo hiệu năng bằng cách log token

Theo dõi:

```text
registrationId
principalCategory = user/service
tokenAcquisitionCount
tokenRefreshSuccessCount
tokenRefreshFailureCount
tokenEndpointLatency
authorizedClientStoreLatency
api401Count
api403Count
retryCount
```

Không ghi `access_token_value`, `refresh_token_value`, cookies, authorization code hoặc raw OAuth error responses có credential.

## 25. Kiểm thử cho từng phương án

### 25.1. Test memory service

- Sau authorization thành công, cùng registration/principal lấy được client.
- Hai principals không thấy token của nhau.
- Hai registrations không ghi đè nhau.
- Xóa đúng `(registrationId, principalName)` không làm mất user khác.
- Restart/recreate service khiến data mất (đây là behavior mong đợi).
- Không kỳ vọng memory state giữa các pods khác nhau.

### 25.2. Test session repository

- Browser giữ cùng session nhận lại token.
- Browser session khác không nhận token của session A.
- Session hết hạn làm token session không còn truy cập được.
- Logout/invalidated session có behavior phù hợp.
- Cookie `Secure`/`HttpOnly`/`SameSite` hoạt động với callback OIDC.
- Multi-node callback hoạt động khi dùng shared session store.
- Authorization request trước callback không bị mất do proxy/cookie.

### 25.3. Test JDBC service

- Authorized client lưu được và load lại sau restart.
- Token được đọc đúng principal/registration.
- Refresh token rotation cập nhật token mới.
- Hai workers refresh đồng thời được xử lý theo policy.
- Refresh `invalid_grant` dẫn đến cleanup đúng.
- Không có token plaintext trong logs/backups không được bảo vệ.
- Database unavailable có đường xử lý phù hợp (không tự tạo user-token sai).
- Version/schema migration được kiểm thử với database thật.

### 25.4. Test security và ownership

- User A không thể đọc token của user B bằng cách thay `principalName`.
- Tenant A không đọc authorized client của tenant B.
- Token của API A không được gửi tới host API B.
- Logout/revoke chỉ xóa đúng token/session theo policy.
- Người dùng có thể reconnect nếu refresh token bị thu hồi.
- Background worker không dùng token user khi chưa có consent.
- Backup/logging không để lộ token có giá trị.

## 26. Troubleshooting: nhận diện sai cơ chế lưu

| Triệu chứng | Nguyên nhân thường gặp | Kiểm tra và khắc phục |
|---|---|---|
| Sau restart user phải kết nối lại | Token nằm trong in-memory service | Nếu cần durability, dùng shared/persistent service |
| Login chập chờn trên nhiều pods | Session cục bộ, callback vào node khác | Shared session store hoặc routing phù hợp |
| Có JDBC table nhưng user token không xuất hiện | Web repository vẫn lưu session/in-memory service khác | Kiểm tra wiring của repository và service |
| Job không thấy token web login | PrincipalName khác hoặc dùng store khác | Đồng bộ key/storage, xác minh ownership |
| Logout rồi background job vẫn gọi API | Token trong JDBC service không bị xóa/revoked | Xác định logout vs disconnect policy |
| Session hết hạn nhưng JDBC token vẫn còn | Hai vòng đời độc lập | Dọn connection/token theo chính sách |
| API 401 mặc dù DB có access token | Token revoked/sai audience/hết hạn | Kiểm tra Resource Server và token lifecycle |
| Refresh trả `invalid_grant` | Token bị revoke/expired/rotated | Không retry mãi; cleanup/reconnect |
| Hai pods cùng refresh làm token mất hiệu lực | Refresh rotation race | Lock/version/single-flight, provider policy |
| Database migration xong báo lỗi JDBC | Thiếu cột/kiểu/schema không đúng version | Dùng schema Spring Security chính thức |
| DB token đọc được ở môi trường khác | Tách tenant/environment chưa đúng | Cách ly databases/credentials/config |
| Redis chứa session nhưng token vẫn mất khi restart | Authorized client thực ra nằm trong in-memory service | Phân biệt session store với token service |
| Token leak trong logs | In raw object/HTTP headers/JDBC bind parameters | Redaction và hạn chế logging |
| Không có refresh token sau OAuth2 Login | AS không cấp offline access hoặc Client không đủ điều kiện | Kiểm tra consent/grant/provider |
| API 403 thiếu scope | Quyền token không đủ | Xin đúng scope; không refresh vô hạn |
| Background worker yêu cầu `HttpServletRequest` | Dùng request-based manager/repository | Service-based manager cho job |
| Cookie bị mất khi callback từ IdP | SameSite/domain/path/proxy/timeout | Kiểm tra cookie, Redirect URI và WebSession |
| Authenticated user principal thay đổi sau update | Custom principal mapping khác | Migration mapping có kiểm chứng |
| Cleanup xóa refresh token dù AT chỉ hết hạn | Retention query sai | Phân biệt access expiry và connection lifecycle |

### 26.1. Quy trình debug có thứ tự

1. **Xác định token thuộc loại nào:** access, refresh, ID Token hay session cookie?
2. **Xác định class lưu thực tế:** service hay repository, in-memory/JDBC/session?
3. **Xác định key:** `registrationId`, `principalName`, tenant và session.
4. **Xác định thời điểm mất:** restart, session timeout, logout, refresh, deploy hay scale-out?
5. **Xác định error source:** Token Endpoint, Resource Server hoặc callback OIDC?
6. **Xem trạng thái connection nội bộ:** active, disabled, reconnect required?
7. **Xem concurrency:** nhiều pods/request có cập nhật cùng token không?
8. **Xem bảo mật:** storage encryption, ACL, cookie, logs, backups.
9. **Xem schema/provider version:** các bean/repositories có khớp contract không?
10. **Chỉ sau đó chọn giải pháp:** chuyển storage, đổi TTL, xử lý refresh/reauthorization hoặc sửa wiring.

Không khắc phục bằng cách tắt `state`, PKCE, nonce, signature verification hoặc dùng raw token trong URL.

## 27. Các bài tập tình huống

### Bài 1: Token mất sau restart

Ứng dụng dùng `InMemoryOAuth2AuthorizedClientService`, user login và gọi API thành công. Sau restart không tìm thấy authorized client.

**Gợi ý:** Đây là behavior của in-memory service. Nếu cần dùng token qua restart, chọn persistent service và xử lý migration/onboarding phù hợp.

### Bài 2: Session khác vẫn thấy token

Developer dùng in-memory service theo principal name. User logout local session rồi login bằng session khác nhưng cùng principal, và service vẫn còn authorized client.

**Gợi ý:** In-memory service không bị gắn vào một session nhất định. Muốn xóa token khi logout phải có cleanup cụ thể hoặc chọn session-scoped repository theo policy.

### Bài 3: Redis có session nhưng token vẫn mất

App dùng Spring Session Redis và `InMemoryOAuth2AuthorizedClientService`. Sau deploy, session còn trong Redis nhưng API connection biến mất.

**Gợi ý:** Redis lưu session, không tự lưu dữ liệu của in-memory service. Cần xem repository/service thực tế và chọn persistent service nếu token cần durability.

### Bài 4: Job chạy sau khi browser đóng

User đã consent offline Calendar sync. Job mỗi đêm cần refresh token dù browser không còn phiên.

**Gợi ý:** Service-backed persistent store phù hợp hơn session repository; background manager dùng đúng authorized client đã được user cấp.

### Bài 5: Hai users cùng registration

```text
registrationId = google
principalName  = user-A / user-B
```

Có nên dùng một record duy nhất theo registration không?

**Gợi ý:** Không. Token theo user cần phân vùng registration + principal/ownership để ngăn cross-user access.

### Bài 6: Token hết hạn nhưng refresh còn hợp lệ

Một housekeeping job xóa tất cả `oauth2_authorized_client` rows có access token expiresAt ở quá khứ.

**Gợi ý:** Có thể vô tình xóa refresh token vẫn hợp lệ. Dùng retention theo connection lifecycle/policy, không chỉ access token expiry.

### Bài 7: JDBC có tự mã hóa token không?

Nhóm bảo mật cho rằng token trong database đã được mã hóa ở tầng ứng dụng vì đang dùng `JdbcOAuth2AuthorizedClientService`.

**Gợi ý:** Không nên mặc định. Phải đánh giá encryption at rest, quyền đọc DB, backup, và custom encryption/KMS nếu cần.

### Bài 8: Logout có tự revoke không?

Người dùng bấm Logout, app xóa session. Refresh token ở database vẫn còn.

**Gợi ý:** Logout local không mặc định đồng nghĩa token revocation tại OP. Cần chính sách rõ: logout, disconnect và revoke là các hành động khác nhau.

### Bài 9: Rotation trên hai pods

Pod A và B đọc cùng RT-1. A refresh thành công nhận RT-2; B dùng RT-1 nhận `invalid_grant`.

**Gợi ý:** Database chia sẻ không tự giải quyết concurrency. Thiết kế single-flight/lock/version và xử lý token family reuse theo provider.

### Bài 10: Reactive vs Servlet

Một dự án `SecurityWebFilterChain` cố inject `HttpSessionOAuth2AuthorizedClientRepository`.

**Gợi ý:** Sai stack. Dùng `ServerOAuth2AuthorizedClientRepository`/`WebSessionServerOAuth2AuthorizedClientRepository` hoặc reactive service phù hợp.

### Bài 11: ID Token và API token

Một developer lưu `OidcUser#getIdToken()` vào bảng authorized client rồi dùng làm Bearer token gọi API.

**Gợi ý:** Sai mục đích. `OAuth2AuthorizedClient` quản lý access/refresh token; ID Token dùng cho xác minh danh tính OIDC.

### Bài 12: Phương án tối thiểu cho service account

Một job dùng `client_credentials`, chạy độc lập trên từng instance, có thể xin access token mới sau restart và không có user refresh tokens.

**Gợi ý:** In-memory service có thể phù hợp nếu AS rate limit/policy và vận hành cho phép. Không bắt buộc JDBC chỉ vì production.

### Bài 13: Session và callback

Người dùng bắt đầu OAuth2 Login tại pod A, callback chuyển tới pod B không có session state.

**Gợi ý:** Lỗi authorization request trước token exchange, không phải thiếu JDBC authorized client. Shared session store hoặc session routing phù hợp.

### Bài 14: Principal user đổi sau upgrade

Phiên bản mới dùng internal ID thay cho `OidcUser.getName()` làm principalName, nhưng JDBC tokens cũ lưu theo tên trước.

**Gợi ý:** Phải có migration/mapping có kiểm chứng. Không bỏ qua ownership hay đoán theo email.

### Bài 15: Revocation và backup

Người dùng disconnect; app xóa token trong DB hiện tại. Backup tháng trước vẫn có refresh token.

**Gợi ý:** Cần bảo vệ backup, policy retention và cân nhắc thu hồi token tại Authorization Server để giảm rủi ro credential cũ.

## 28. Checklist chọn kho lưu khi triển khai

- [ ] Phân biệt `OAuth2AuthorizationRequest`, `SecurityContext` và `OAuth2AuthorizedClient`.
- [ ] Biết service/repository **thực tế được framework sử dụng**, không đoán từ tên bean.
- [ ] Nếu memory: chấp nhận mất data khi restart và riêng biệt giữa các pods?
- [ ] Nếu session: lifecycle user session phù hợp và cookie được bảo vệ?
- [ ] Nếu JDBC: schema, migration, encryption, DB credentials và retention đầy đủ?
- [ ] Nếu dùng Redis session: hiểu rằng in-memory authorized client service là kho khác?
- [ ] Background jobs có được phép dùng user-delegated credentials sau session expiry không?
- [ ] Access token/refresh token có đúng audience, scope, grant và consent không?
- [ ] Principal/registration/tenant ownership được xác minh?
- [ ] Có cơ chế refresh, rotation, invalid_grant và reauthorization?
- [ ] Có kiểm soát đồng thời refresh trên nhiều nodes?
- [ ] Có policy logout khác disconnect/revoke?
- [ ] Có cơ chế dọn token không xóa nhầm refresh token còn cần?
- [ ] Không lưu raw token trong frontend/localStorage ngoài thiết kế được đánh giá?
- [ ] Không đưa access/refresh token vào logs, traces, backups thiếu bảo vệ?
- [ ] Đã kiểm thử multi-instance, restart, session expiry, database outage và recovery?
- [ ] Đã giới hạn outbound HTTP origins nhận Bearer token?
- [ ] Có khả năng thông báo `RECONNECT_REQUIRED` khi quyền user hết hiệu lực?

## 29. Tài liệu tham khảo

1. [Spring Security Reference — OAuth2 Client (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): mô hình ClientRegistration, authorized clients, managers.
2. [Spring Security API — OAuth2AuthorizedClientService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientService.html): lưu/tìm/xóa authorized clients ngoài request.
3. [Spring Security API — OAuth2AuthorizedClientRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/OAuth2AuthorizedClientRepository.html): quản lý authorized clients trong Servlet request.
4. [Spring Security API — InMemoryOAuth2AuthorizedClientService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/InMemoryOAuth2AuthorizedClientService.html): token store trong memory.
5. [Spring Security API — JdbcOAuth2AuthorizedClientService](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/JdbcOAuth2AuthorizedClientService.html): JDBC persistence.
6. [Spring Security API — HttpSessionOAuth2AuthorizedClientRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/HttpSessionOAuth2AuthorizedClientRepository.html): session-based storage.
7. [Spring Security API — AuthenticatedPrincipalOAuth2AuthorizedClientRepository](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/AuthenticatedPrincipalOAuth2AuthorizedClientRepository.html): repository ủy quyền lưu theo authenticated principal.
8. [Spring Security API — DefaultOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizedClientManager.html): manager cho Servlet request.
9. [Spring Security API — AuthorizedClientServiceOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html): manager cho service tier/background.
10. [Spring Security Reference — Reactive OAuth2 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html): reactive token store và manager.
11. [Spring Session Reference](https://docs.spring.io/spring-session/reference/): quản lý session phân tán, Redis và session lifecycle.
12. [RFC 6749 — OAuth 2.0](https://www.rfc-editor.org/rfc/rfc6749): access token, refresh token, Authorization Code Flow.
13. [RFC 7009 — Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): chủ động thu hồi OAuth2 token.
14. [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): refresh token security, rotation/reuse và các khuyến nghị.
15. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, OIDC session-related semantics và authorization flow.

## 30. Tổng kết

Lựa chọn lưu token trong **bộ nhớ, session hay cơ sở dữ liệu** phụ thuộc trước hết vào **loại trạng thái được lưu** và **vòng đời mong muốn**:

- **Memory service:** đơn giản, ít phụ thuộc, phù hợp học tập hoặc token có thể xin lại dễ; không bền vững qua restart, không chia sẻ giữa pods.
- **Session repository:** gắn authorized client với vòng đời browser session, phù hợp portal chỉ dùng token khi user đang online; cần cookie và session store đúng nếu multi-instance.
- **Database-backed service:** phù hợp user-delegated connections và background jobs cần token sau restart, nhưng đòi schema, bảo vệ credential, cleanup và kiểm soát refresh concurrency.

Trên Spring Security Servlet, hãy phân biệt **`OAuth2AuthorizedClientService`** với **`OAuth2AuthorizedClientRepository`** và hiểu tác dụng của `AuthenticatedPrincipalOAuth2AuthorizedClientRepository`. Trên WebFlux, dùng các interface Reactive/Server tương ứng. **Spring Session Redis chỉ giải quyết session data được lưu trong WebSession/HttpSession; nó không tự biến mọi in-memory OAuth2 client service thành kho Redis.**

Cuối cùng, chọn đúng storage **không tự động giải quyết refresh token rotation, revocation, account ownership và authorization**. Cần một kiến trúc đồng bộ giữa session lifecycle, token lifecycle, business connection state, bảo mật và vận hành để ứng dụng giữ quyền truy cập đúng người, đúng tài nguyên và đúng thời điểm.
