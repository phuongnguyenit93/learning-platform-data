# 15.4. OAuth2AuthorizedClientProvider và cơ chế ghép provider

## 1. Bối cảnh: Client Manager lấy token bằng cách nào?

Trong **Spring Security OAuth 2.0/OIDC Client**, một ứng dụng có thể cần access token trong nhiều tình huống:

- Người dùng đăng nhập bằng Authorization Code Grant, sau đó ứng dụng gọi API thay mặt họ.
- Access token của người dùng hết hạn và ứng dụng muốn **refresh** mà không bắt đăng nhập lại, nếu Authorization Server đã cấp refresh token.
- Một tác vụ backend gọi API bằng **Client Credentials Grant**, không đại diện cho người dùng cụ thể.
- Ứng dụng cần áp dụng một grant mở rộng được Authorization Server hỗ trợ, hoặc một chính sách lựa chọn grant theo loại client.

Thành phần trung tâm để quản lý các tình huống này là **`OAuth2AuthorizedClientManager`**. Manager làm việc với client registration, principal, nơi lưu `OAuth2AuthorizedClient` và các cơ chế cấp/mở rộng token.

Nhưng manager không nên tự chứa toàn bộ logic của từng OAuth2 grant. Spring Security tách phần đó qua:

**`OAuth2AuthorizedClientProvider` — một chiến lược có thể thử cấp quyền hoặc cấp lại quyền cho một OAuth2 client theo ngữ cảnh hiện tại.**

Để hỗ trợ nhiều grant, Spring Security có thể **ghép nhiều provider thành một chuỗi**. Khi manager muốn authorize, nó gọi provider tổng hợp; provider này thử các thành phần theo thứ tự và quyết định kết quả.

Bài học tập trung vào **cách provider hoạt động, cách ghép provider và cách lựa chọn chính sách khi cấu hình manager**.

### Mục tiêu

Sau bài học, bạn có thể:

1. Hiểu quan hệ giữa `OAuth2AuthorizedClientManager`, `OAuth2AuthorizedClientProvider` và `OAuth2AuthorizedClient`.
2. Hiểu ý nghĩa kết quả **non-null**, **`null`** và **exception** từ `authorize(...)`.
3. Phân biệt các chiến lược `authorization_code`, `refresh_token` và `client_credentials`.
4. Dùng `OAuth2AuthorizedClientProviderBuilder` để ghép nhiều provider.
5. Hiểu **thứ tự thực thi**, quy tắc dừng và lý do composite không phải cơ chế retry/failover.
6. Cấu hình manager phù hợp cho **Servlet HTTP request** và **background service**.
7. Biết các điểm tùy chỉnh token response client, clock skew, success/failure handling và nơi lưu token.
8. Nắm cách mở rộng bằng provider tùy chỉnh khi thực sự cần.
9. Hiểu những khác biệt tương ứng trong Spring WebFlux/reactive.
10. Chẩn đoán các lỗi thường gặp mà không nhầm lỗi cấp token với lỗi lưu token.

Các URL, registration ID và token trong bài chỉ là dữ liệu ví dụ. Đoạn mã minh họa Spring Security hiện đại; cần chọn API phù hợp với phiên bản đang sử dụng.

## 2. Những lớp tham gia quản lý Authorized Client

Trước khi tìm hiểu provider, cần phân biệt các thành phần:

| Thành phần | Trách nhiệm |
|---|---|
| `ClientRegistration` | Mô tả một OAuth2 client: client ID, token URI, grant type, scopes, phương thức xác thực client... |
| `ClientRegistrationRepository` | Tìm `ClientRegistration` theo `registrationId`. |
| `OAuth2AuthorizedClient` | Kết hợp client registration, principal name, access token và refresh token nếu có. |
| `OAuth2AuthorizedClientService` | Lưu/đọc authorized clients theo `registrationId` và principal name, không cần HTTP request. |
| `OAuth2AuthorizedClientRepository` | Lưu/đọc authorized clients theo ngữ cảnh Servlet web request và principal. |
| `OAuth2AuthorizedClientManager` | Điều phối việc tìm client, authorize/re-authorize và lưu/xóa kết quả theo chính sách. |
| **`OAuth2AuthorizedClientProvider`** | **Quyết định có thể/đang cần authorize hoặc re-authorize bằng một cơ chế cụ thể hay không.** |
| `OAuth2AccessTokenResponseClient` | Gửi token request của một grant cụ thể tới Authorization Server và đọc phản hồi. |

Sơ đồ khái niệm:

```mermaid
flowchart TD
    A["Ứng dụng cần OAuth2AuthorizedClient"] --> B["OAuth2AuthorizedClientManager"]
    B --> C["ClientRegistrationRepository"]
    B --> D["OAuth2AuthorizedClientRepository / Service"]
    B --> E["OAuth2AuthorizedClientProvider"]
    E --> F["authorization_code strategy"]
    E --> G["refresh_token strategy"]
    E --> H["client_credentials strategy"]
    E --> I["custom strategy nếu cần"]
    G --> J["Token Endpoint"]
    H --> J
    D --> K["Session / InMemory / JDBC / custom store"]
```

Điều cần phân biệt:

> **Manager** quyết định cách phối hợp; **Provider** quyết định cách thử cấp/cấp lại quyền; **Token Response Client** thực hiện token request; **Repository/Service** quyết định nơi lưu kết quả.

Một `OAuth2AuthorizedClientProvider` **không phải** nhà cung cấp danh tính như Google, Keycloak hay một OpenID Provider. Trong bài này, *provider* nghĩa là **strategy xử lý OAuth2 grant**, không phải Authorization Server/IdP.

## 3. Hợp đồng OAuth2AuthorizedClientProvider

Interface thuộc package:

```java
org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider
```

Dạng khái niệm:

```java
public interface OAuth2AuthorizedClientProvider {

    OAuth2AuthorizedClient authorize(
        OAuth2AuthorizationContext context
    );
}
```

Phương thức `authorize(...)` nhận một `OAuth2AuthorizationContext` chứa thông tin cần thiết, ví dụ:

- `ClientRegistration` đang được authorize.
- `Authentication` hoặc principal tương ứng.
- `OAuth2AuthorizedClient` hiện có, nếu từng được authorize.
- Attributes bổ sung theo yêu cầu của một grant/implementation.
- Các dữ liệu ngữ cảnh khác do manager cung cấp.

### 3.1. Ba kết quả quan trọng

| Kết quả | Ý nghĩa | Manager/provider tổng hợp xử lý thế nào? |
|---|---|---|
| Trả **`OAuth2AuthorizedClient`** | Provider đã thực hiện authorization/reauthorization thành công hoặc trả kết quả theo contract. | Được coi là kết quả của lần thử; manager có thể lưu lại theo success handling. |
| Trả **`null`** | Provider không hỗ trợ ngữ cảnh/grant này, hoặc chưa cần re-authorize. | Provider tổng hợp có thể thử provider tiếp theo; manager có thể tiếp tục dùng authorized client hiện có nếu phù hợp. |
| Ném **`OAuth2AuthorizationException`** hoặc exception liên quan | Quá trình authorization gặp lỗi thực sự hoặc cần bước tương tác đặc biệt. | Thường làm dừng chuỗi và chuyển quyền xử lý lỗi cho manager/web infrastructure. |

**`null` không đồng nghĩa với token invalid**, và cũng không đồng nghĩa authorize thất bại. Một access token hiện tại vẫn còn hợp lệ có thể khiến provider không cần làm gì, nên trả `null`.

Ngược lại, **exception không phải tín hiệu “hãy thử grant kế tiếp”**. Khi AS trả lỗi xác thực client hoặc refresh token không hợp lệ, việc âm thầm chuyển sang grant khác có thể vi phạm chính sách bảo mật.

### 3.2. OAuth2AuthorizationContext không phải ClientRegistration

`ClientRegistration` là cấu hình tĩnh của client. `OAuth2AuthorizationContext` là **ngữ cảnh của lần cần authorize hiện tại**.

Ví dụ cùng một registration:

```text
registrationId = corporate
authorizationGrantType = authorization_code

Lần 1:
    chưa có authorized client
    -> có thể cần interactive authorization

Lần 2:
    authorized client đã có, access token còn hạn
    -> không cần token request mới

Lần 3:
    access token hết hạn, refresh token có
    -> refresh_token provider có thể xử lý

Lần 4:
    refresh token bị thu hồi
    -> cần xử lý lỗi và có thể yêu cầu authorization mới
```

Chỉ nhìn vào `authorizationGrantType` của registration chưa đủ để quyết định tất cả hành vi. Cần biết **authorized client đã có hay chưa**, token còn hiệu lực không và có refresh token hay không.

## 4. Provider tổng hợp: ghép nhiều chiến lược bằng thứ tự

Spring Security có một implementation ghép:

```java
org.springframework.security.oauth2.client.DelegatingOAuth2AuthorizedClientProvider
```

Ý tưởng:

```text
Composite Provider
    |
    +-- Provider A
    |      -> trả null? Thử B
    |      -> trả authorized client? Kết thúc
    |      -> throw exception? Dừng và báo lỗi
    |
    +-- Provider B
    |      -> trả null? Thử C
    |      -> trả authorized client? Kết thúc
    |      -> throw exception? Dừng và báo lỗi
    |
    +-- Provider C
           -> ...
```

Sơ đồ:

```mermaid
flowchart TD
    A["authorize(context)"] --> B["Provider 1"]
    B --> C{"Kết quả?"}
    C -->|Authorized Client| Z["Trả kết quả"]
    C -->|Exception| X["Dừng và báo lỗi"]
    C -->|null| D["Provider 2"]
    D --> E{"Kết quả?"}
    E -->|Authorized Client| Z
    E -->|Exception| X
    E -->|null| F["Provider 3"]
    F --> G{"Kết quả?"}
    G -->|Authorized Client| Z
    G -->|Exception| X
    G -->|null| N["Trả null"]
```

### 4.1. Quy tắc “provider đầu tiên trả non-null”

Nếu provider đầu tiên trả một authorized client, những provider phía sau **không được gọi** cho lượt đó.

Vì thế thứ tự có thể tác động tới hành vi khi:

- Một provider tùy chỉnh nhận nhiều loại registration.
- Hai providers đều có thể áp dụng với cùng context.
- Provider đầu tiên chủ động quyết định authorization cần được thực hiện.
- Một provider có cơ chế báo lỗi đặc biệt thay vì trả `null`.

### 4.2. Composite không phải load balancer hay fallback API

Không nên hiểu:

```text
refresh_token lỗi -> thử lại client_credentials -> thử authorization_code
```

như một chính sách fallback mặc định.

Trong luồng OAuth2, mỗi grant đại diện cho **một cơ chế cấp quyền có ý nghĩa riêng**. `client_credentials` cấp token cho client/service, không thể tùy ý thay token đại diện cho người dùng. Một lỗi `invalid_grant` khi refresh token không cho phép ứng dụng âm thầm lấy service token rồi giả định vẫn đang đại diện người dùng.

**Chỉ kết quả `null` khiến composite xét provider kế tiếp; lỗi thực sự không phải lời mời chuyển quyền sang grant khác.**

## 5. OAuth2AuthorizedClientProviderBuilder

Cách cấu hình phổ biến nhất là builder:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;

OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .clientCredentials()
        .build();
```

Builder tạo một provider tổng hợp có các chiến lược được đăng ký.

Đọc đoạn này như sau:

- `authorizationCode()` bổ sung xử lý liên quan Authorization Code Grant.
- `refreshToken()` bổ sung khả năng refresh access token nếu đã có refresh token phù hợp.
- `clientCredentials()` bổ sung khả năng lấy/cấp lại token bằng Client Credentials Grant.
- `build()` tạo một provider để manager sử dụng.

Đây là **cấu hình khả năng của manager**, không phải yêu cầu rằng mỗi lần gọi manager sẽ sử dụng cả ba grant.

### 5.1. Vì sao nên dùng builder?

- Cấu hình rõ các grant đang được ứng dụng hỗ trợ.
- Dễ đọc hơn việc tự tạo và kết nối nhiều strategy objects.
- Có thể bổ sung provider tùy chỉnh hoặc cấu hình riêng cho một grant tùy API phiên bản.
- Dễ gắn cùng một provider đã cấu hình vào các manager phù hợp.
- Giảm rủi ro viết lại logic giao thức OAuth2 bằng HTTP client tự chế.

### 5.2. Không bật mọi grant theo phản xạ

Một số ứng dụng chỉ cần:

```java
OAuth2AuthorizedClientProvider serviceProvider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build();
```

Một portal tương tác với người dùng có thể cần:

```java
OAuth2AuthorizedClientProvider userProvider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .build();
```

Điều quan trọng là grant thực sự đã được Authorization Server cấp cho registration và phục vụ đúng ngữ cảnh.

**Không tự bật Resource Owner Password Credentials (password grant)** như một lựa chọn tiện lợi cho ứng dụng mới. Grant này đã bị loại khỏi các định hướng OAuth2 hiện đại và API hỗ trợ trong Spring Security thay đổi/deprecate theo phiên bản. Bài học dùng Authorization Code + PKCE hoặc Client Credentials đúng mô hình thay vì khuyến khích password grant.

## 6. authorizationCode(): khi nào cần người dùng tương tác?

Authorization Code Grant thường cần browser redirect, đăng nhập và consent:

```mermaid
sequenceDiagram
    autonumber
    actor U as User/Browser
    participant C as Spring OAuth2 Client
    participant AS as Authorization Server

    U->>C: Yêu cầu tài nguyên/ủy quyền
    Note over C: Chưa có authorized client
    C-->>U: Redirect đến Authorization Endpoint
    U->>AS: Authorization request
    AS-->>U: Login/consent
    AS-->>U: Callback chứa code
    U->>C: Callback
    C->>AS: Token request đổi code (và PKCE verifier)
    AS-->>C: Tokens
    Note over C: Lưu OAuth2AuthorizedClient
```

Trong OAuth2 Client Manager, `authorizationCode()` không phải một “máy tự tạo authorization code” trong tác vụ backend. Khi chưa có authorized client thích hợp, chiến lược này có thể **báo cần interactive authorization** thông qua cơ chế exception/tín hiệu của Spring Security.

Phần redirect, callback, `state`, PKCE và code exchange được phối hợp bởi **OAuth2 Login/Client filters và authorization request infrastructure** trong ngữ cảnh web thích hợp.

### 6.1. Không có browser thì không thể tự hoàn thành Authorization Code Grant

Một scheduled job gọi:

```java
manager.authorize(request);
```

với registration `authorization_code` nhưng chưa có user authorization, không thể kỳ vọng manager tự đăng nhập thay người dùng. Job không có browser, cookie, consent hay quyền đại diện user chưa được cấp.

Nếu tác vụ nền cần gọi API thay mặt người dùng, phải thiết kế trước một luồng authorization tương tác, lưu token hợp lệ (nếu được phép), rồi sử dụng authorized client/service đúng principal. Nếu chỉ cần quyền ứng dụng, cân nhắc `client_credentials`.

### 6.2. PKCE không do provider chain tự sinh thay toàn bộ luồng

PKCE là cơ chế ràng buộc authorization code giữa authorize và token request. Spring Security xử lý nó tại các thành phần authorization request/Token Endpoint tương ứng.

Chỉ thêm `.authorizationCode()` vào provider builder **không bảo đảm** mọi client có PKCE S256 trong mọi phiên bản/cấu hình. Cần kiểm tra chính sách provider và cấu hình Spring Security tương ứng, nhất là với confidential client.

### 6.3. OIDC vẫn dùng Authorization Code Grant

Một OIDC client với scope `openid` có thể sử dụng:

```yaml
authorization-grant-type: authorization_code
scope: [openid, profile, email]
```

`authorizationCode()` là chiến lược **OAuth2 grant**; việc xác minh ID Token thuộc luồng **OIDC authentication**, không phải nhiệm vụ của provider tổng hợp.

## 7. refreshToken(): gia hạn quyền đã được cấp

Một `OAuth2AuthorizedClient` có thể chứa:

```text
access token:  AT1, gần hết hạn
refresh token: RT1
```

Nếu Authorization Server đã cấp refresh token và registration phù hợp, provider `refreshToken()` có thể thực hiện:

```http
POST /oauth2/token HTTP/1.1
Host: id.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_CLIENT_ID_COLON_CLIENT_SECRET

grant_type=refresh_token&refresh_token=RT1
```

Provider đọc token response và tạo authorized client mới hoặc cập nhật token information để manager lưu lại.

### 7.1. Những điều kiện thông thường để refresh

- Có một authorized client hiện hữu.
- Access token đã hết hạn hoặc sắp hết hạn theo **clock skew**.
- Authorized client có refresh token phù hợp.
- Client được phép sử dụng refresh token grant.
- Token Endpoint chấp nhận refresh token cùng client authentication yêu cầu.

Nếu access token vẫn còn đủ thời hạn, refresh provider thường **trả `null`** để không tạo token request không cần thiết.

Nếu không có refresh token, refresh provider cũng không thể tự phát minh một refresh token. Việc client yêu cầu `offline_access` không bảo đảm mọi provider sẽ cấp refresh token; còn phụ thuộc policy, consent và loại client.

### 7.2. Refresh Token Rotation

Một provider có thể trả:

```text
Trước:
  access_token = AT1
  refresh_token = RT1

Sau refresh:
  access_token = AT2
  refresh_token = RT2
```

Ứng dụng phải lưu **refresh token mới** nếu AS rotate token. Việc giữ RT1 và dùng lại có thể bị từ chối hoặc kích hoạt reuse detection.

Trong môi trường nhiều instances, hai request cùng lấy RT1 để refresh có thể gây race condition. Provider builder không tự giải quyết toàn bộ concurrency của token storage; cần chính sách locking/update phù hợp với `OAuth2AuthorizedClientService` hoặc repository.

### 7.3. Lỗi refresh không đồng nghĩa nên thử client credentials

Ví dụ AS trả:

```json
{
  "error": "invalid_grant",
  "error_description": "Refresh token is invalid or revoked"
}
```

Manager/failure handler phải xử lý theo ngữ nghĩa OAuth2 và policy ứng dụng. Không lấy `client_credentials` token rồi dùng như token của người dùng. Nếu quyền user cần được cấp lại, cần một authorization flow hợp lệ.

## 8. clientCredentials(): token cho service/backend

Client Credentials Grant phù hợp khi một dịch vụ cần gọi API **bằng quyền của chính client**, không thay mặt người dùng.

Ví dụ registration:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          inventory-api:
            provider: internal-as
            client-id: ${INVENTORY_CLIENT_ID}
            client-secret: ${INVENTORY_CLIENT_SECRET}
            authorization-grant-type: client_credentials
            client-authentication-method: client_secret_basic
            scope: [inventory.read]
        provider:
          internal-as:
            token-uri: https://auth.internal.example/oauth2/token
```

Token request khái niệm:

```http
POST /oauth2/token HTTP/1.1
Host: auth.internal.example
Content-Type: application/x-www-form-urlencoded
Authorization: Basic BASE64_CLIENT_ID_COLON_CLIENT_SECRET

grant_type=client_credentials&scope=inventory.read
```

Khi chưa có authorized client, `ClientCredentialsOAuth2AuthorizedClientProvider` có thể xin token. Khi access token còn hiệu lực, nó không cần cấp lại. Khi hết hạn, nó có thể thực hiện token request mới.

Client Credentials Grant thường **không dùng refresh token**; khi access token hết hạn, client lại dùng grant này để xin token mới.

### 8.1. Token có quyền của client, không phải của user

Nếu backend phục vụ cả Alice và Bob, cần phân biệt:

```text
Access token của Alice:
    authorization_code / refresh_token
    đại diện authorization được cấp trong ngữ cảnh Alice

Access token của inventory service:
    client_credentials
    đại diện chính ứng dụng inventory
```

Không dùng token service để bỏ qua authorization của người dùng trong business logic. Resource Server vẫn cần kiểm tra scope, audience và chính sách truy cập tương ứng với loại principal/service.

### 8.2. Principal name dùng làm khóa lưu, không biến token thành user token

Khi gọi authorized client manager cho service, có thể chọn principal name ổn định như `inventory-batch`. Tên này phục vụ **khóa lưu/cache authorized client**; nó không khiến access token của Client Credentials Grant trở thành token đại diện cho một con người.

## 9. Thứ tự ghép provider: nhìn vào một tình huống cụ thể

Giả sử cấu hình:

```java
OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .authorizationCode()
        .refreshToken()
        .clientCredentials()
        .build();
```

Các tình huống:

| Ngữ cảnh | `authorizationCode()` | `refreshToken()` | `clientCredentials()` | Kết quả dự kiến |
|---|---|---|---|---|
| Registration `authorization_code`, chưa có authorized client | Có thể yêu cầu interactive authorization | Không có token để refresh | Không hỗ trợ grant này | Web infrastructure xử lý login/redirect nếu có. |
| Registration `authorization_code`, token còn hạn | Không cần authorize mới | Không cần refresh | Không hỗ trợ grant | Manager tiếp tục sử dụng authorized client hiện tại theo contract. |
| Registration `authorization_code`, token hết hạn, có refresh token | Không tạo authorization flow mới cho client đã được cấp quyền | Thử refresh | Không hỗ trợ grant | Token được refresh khi AS chấp nhận. |
| Registration `client_credentials`, chưa có token | Không hỗ trợ grant | Không có authorized client/refresh token | Thử cấp token mới | Client Credentials Token Request. |
| Registration `client_credentials`, token còn hạn | Không hỗ trợ | Thông thường không có refresh token/cần refresh | Không cấp lại | Dùng token còn hạn. |
| Registration không được các provider hỗ trợ | Trả `null`/không áp dụng | Trả `null`/không áp dụng | Trả `null`/không áp dụng | Không có cơ chế tự authorize từ chuỗi này. |

Bảng mô tả kết quả khái niệm, không thay thế việc đọc contract và kiểm tra framework theo phiên bản. Khi Authorization Server trả lỗi hoặc flow cần tương tác, kết quả có thể là exception thay vì `null`.

### 9.1. Vì sao `authorizationCode()` ở trước `refreshToken()` vẫn hợp lý?

Nếu authorized client **đã có**, provider authorization code không nên buộc một phiên đăng nhập mới chỉ vì access token gần hết hạn; provider refresh có thể tiếp tục làm việc.

Nếu authorized client **chưa có**, authorization code có thể cần khởi tạo luồng tương tác, thay vì cố refresh một token không tồn tại.

### 9.2. Chuyện gì xảy ra khi một custom provider đứng đầu?

Giả sử bạn ghép một custom provider mà nó trả **một authorized client non-null** cho mọi request, kể cả khi không xử lý đúng grant. Những providers sau sẽ không chạy. Manager có thể nghĩ authorization thành công và lưu kết quả chưa đúng.

Quy tắc viết custom provider:

- **Chỉ trả non-null khi có kết quả hợp lệ theo contract.**
- Trả `null` khi **không hỗ trợ** ngữ cảnh hoặc **không cần** re-authorize.
- Ném lỗi khi giao dịch thật sự thất bại hoặc chính sách yêu cầu từ chối.
- Không trả một dummy authorized client để “giữ chỗ”.

## 10. Cấu hình Manager trong Spring Security Servlet

Với ứng dụng Servlet/MVC đang xử lý HTTP request, manager phù hợp thường là:

```java
org.springframework.security.oauth2.client.web.DefaultOAuth2AuthorizedClientManager
```

Constructor cần:

- `ClientRegistrationRepository`.
- `OAuth2AuthorizedClientRepository`.

Ví dụ Java:

```java
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
            OAuth2AuthorizedClientRepository authorizedClients) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .authorizationCode()
                .refreshToken()
                .clientCredentials()
                .build();

        DefaultOAuth2AuthorizedClientManager manager =
            new DefaultOAuth2AuthorizedClientManager(
                registrations,
                authorizedClients
            );

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

Cấu hình rõ ràng ở đây:

1. Manager tra registration theo `registrationId`.
2. Manager đọc authorized client hiện có trong repository theo ngữ cảnh HTTP/principal.
3. Manager gọi provider tổng hợp.
4. Provider quyết định có thể/đang cần authorize không.
5. Nếu nhận kết quả, manager xử lý lưu hoặc cập nhật theo success handler.
6. Nếu có lỗi, manager chuyển cho failure handling và caller theo contract.

Đoạn mã chỉ tạo **manager cho Servlet**. Những OAuth2 Login filters, session và redirect vẫn phải được cấu hình cho web application.

### 10.1. Bảo mật Servlet để người dùng đăng nhập

Ví dụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults());

        return http.build();
    }
}
```

`oauth2Login()` phục vụ authentication cho người dùng. `oauth2Client()` hỗ trợ chức năng OAuth2 Client khi ứng dụng cần token để gọi API. Một số ứng dụng chỉ cần một trong hai tùy mục tiêu.

Nếu ứng dụng đã có `SecurityFilterChain`, tích hợp cấu hình vào chain đang dùng, không sao chép thêm một chain trùng matcher một cách tình cờ.

### 10.2. Manager không thay thế đăng ký OAuth2 client

Bạn vẫn cần `ClientRegistrationRepository`, thường được Spring Boot xây từ `application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          portal-login:
            provider: company-oidc
            client-id: ${PORTAL_CLIENT_ID}
            client-secret: ${PORTAL_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
          inventory-api:
            provider: company-oidc
            client-id: ${INVENTORY_CLIENT_ID}
            client-secret: ${INVENTORY_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: [inventory.read]
        provider:
          company-oidc:
            issuer-uri: https://id.example.com
```

Giả định provider minh họa hỗ trợ cả hai grants và có các client registrations được cấp phép tương ứng. Một registration `client_credentials` không được mặc nhiên dùng để đăng nhập người dùng bằng `oauth2Login()`.

## 11. Gọi Manager từ code ứng dụng

Interface:

```java
org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager
```

Phương thức chính:

```java
OAuth2AuthorizedClient authorize(
    OAuth2AuthorizeRequest authorizeRequest
);
```

`OAuth2AuthorizeRequest` cho biết:

- Registration ID hoặc authorized client đang yêu cầu sử dụng.
- Principal làm ngữ cảnh authorization.
- Attributes bổ sung khi cần.

Ví dụ:

```java
import org.springframework.security.oauth2.client.OAuth2AuthorizeRequest;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientManager;

public final class InventoryTokenService {

    private final OAuth2AuthorizedClientManager manager;

    public InventoryTokenService(
            OAuth2AuthorizedClientManager manager) {
        this.manager = manager;
    }

    public OAuth2AuthorizedClient getAuthorizedClient() {
        OAuth2AuthorizeRequest request =
            OAuth2AuthorizeRequest
                .withClientRegistrationId("inventory-api")
                .principal("inventory-worker")
                .build();

        OAuth2AuthorizedClient client = manager.authorize(request);

        if (client == null) {
            throw new IllegalStateException(
                "No authorized client available for inventory-api"
            );
        }

        return client;
    }
}
```

Đoạn mã cho thấy cách gọi manager, nhưng **trong background job** nên dùng `AuthorizedClientServiceOAuth2AuthorizedClientManager` theo phần tiếp theo. Nếu injection có nhiều manager beans, cần chọn manager chính xác.

Không trả `OAuth2AuthorizedClient` nguyên bản ra REST API vì nó chứa access token và có thể có refresh token. Nếu cần gọi API, lấy token ở server và chỉ sử dụng token cho đúng resource server đã đăng ký.

### 11.1. Phân biệt `authorize()` của manager và provider

- `OAuth2AuthorizedClientManager.authorize(request)` là API mà **ứng dụng** thường gọi.
- `OAuth2AuthorizedClientProvider.authorize(context)` là API **manager** dùng để thực thi chiến lược.

Trong code nghiệp vụ, đa số trường hợp **không gọi trực tiếp `OAuth2AuthorizedClientProvider`**, vì làm như vậy bạn phải tự lo context, repository, success/failure handling và token lifecycle.

## 12. Manager cho background jobs: không phụ thuộc Servlet HTTP request

`DefaultOAuth2AuthorizedClientManager` được thiết kế cho ngữ cảnh Servlet web request. Trong scheduled job, batch process hoặc service-to-service backend không có `HttpServletRequest`, nên lựa chọn phù hợp là:

```java
org.springframework.security.oauth2.client.AuthorizedClientServiceOAuth2AuthorizedClientManager
```

Constructor:

```java
AuthorizedClientServiceOAuth2AuthorizedClientManager(
    ClientRegistrationRepository clientRegistrationRepository,
    OAuth2AuthorizedClientService authorizedClientService
)
```

Ví dụ **Client Credentials**:

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
public class ServiceTokenManagerConfig {

    @Bean("serviceAuthorizedClientManager")
    OAuth2AuthorizedClientManager serviceAuthorizedClientManager(
            ClientRegistrationRepository registrations,
            OAuth2AuthorizedClientService authorizedClientService) {

        OAuth2AuthorizedClientProvider provider =
            OAuth2AuthorizedClientProviderBuilder.builder()
                .clientCredentials()
                .build();

        AuthorizedClientServiceOAuth2AuthorizedClientManager manager =
            new AuthorizedClientServiceOAuth2AuthorizedClientManager(
                registrations,
                authorizedClientService
            );

        manager.setAuthorizedClientProvider(provider);
        return manager;
    }
}
```

Nếu ứng dụng có cả Servlet manager và background manager, đặt tên/qualifier rõ ràng để injection không mơ hồ. Có thể cấu hình **hai bộ providers khác nhau** cho hai manager thay vì một composite duy nhất cho mọi trường hợp.

### 12.1. PrincipalName dùng làm khóa lưu

Với service manager:

```java
OAuth2AuthorizeRequest request =
    OAuth2AuthorizeRequest
        .withClientRegistrationId("inventory-api")
        .principal("inventory-worker")
        .build();
```

Chuỗi `"inventory-worker"` là **principal name dùng để tra/lưu authorized client**, không tự làm access token có quyền của một người dùng tên như vậy.

Khi dùng `client_credentials`, token đại diện cho client/service. Nếu những công việc khác nhau cần cách ly token, chọn các principal names/registrations và security boundaries thích hợp.

### 12.2. Background job muốn dùng token của user

Nếu job cần gọi API thay mặt Alice, hệ thống phải có authorization đã được cấp cho Alice, lưu token/refresh token theo chính sách và chọn đúng principal khi authorize.

Không dùng `client_credentials` token của service để thay token của Alice. Không dùng token của Alice cho Bob do trùng registration ID.

## 13. Clock skew và điều kiện hết hạn

Token có thời gian hết hạn thường biểu diễn qua `OAuth2AccessToken.getExpiresAt()`. Provider có thể xem token là **gần hết hạn** trước thời điểm thực tế bằng một độ lệch **clock skew**.

Ví dụ:

```text
Bây giờ = 10:00:00
Access token expiresAt = 10:00:40
Clock skew = 60 giây

Provider có thể xem token là cần gia hạn
ngay vì chỉ còn 40 giây sử dụng an toàn.
```

Lợi ích:

- Hạn chế gọi API bằng token sắp hết hạn trong khi request đang chạy.
- Giảm ảnh hưởng khi đồng hồ giữa client và AS có sai lệch nhỏ.
- Tạo khoảng đệm cho kết nối mạng và xử lý token.

### 13.1. Tùy chỉnh clock skew

Builder ở những dòng Spring Security hỗ trợ các customizer tương ứng, ví dụ:

```java
import java.time.Duration;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProviderBuilder;

OAuth2AuthorizedClientProvider provider =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .refreshToken(refresh -> refresh
            .clockSkew(Duration.ofSeconds(45))
        )
        .clientCredentials(clientCredentials -> clientCredentials
            .clockSkew(Duration.ofSeconds(45))
        )
        .build();
```

Hoặc tùy chỉnh các provider instances trực tiếp theo API đang dùng, như `RefreshTokenOAuth2AuthorizedClientProvider.setClockSkew(...)` và `ClientCredentialsOAuth2AuthorizedClientProvider.setClockSkew(...)`.

Không đặt skew quá lớn so với lifetime khiến mỗi request lại xin token mới. Không lấy skew làm giải pháp cho AS trả token hết hạn ngay từ đầu hoặc đồng hồ máy chủ lệch nhiều giờ.

### 13.2. Không nhầm clock skew với refresh token expiry

Clock skew ở đây chủ yếu liên quan tới **access token** và quyết định có nên re-authorize sớm. Refresh token có lifecycle và policy khác; một số provider không công bố thời điểm hết hạn refresh token trong token response.

Nếu refresh token bị thu hồi, không có phép tính skew nào khiến nó hợp lệ trở lại.

## 14. Tùy chỉnh HTTP client của từng grant

Các chiến lược khác nhau có thể dùng **token response clients khác nhau**:

| Grant | Client Servlet hiện đại | Khi sử dụng |
|---|---|---|
| Authorization Code | `RestClientAuthorizationCodeTokenResponseClient` | Đổi authorization code sau callback. |
| Refresh Token | `RestClientRefreshTokenTokenResponseClient` | Gửi refresh token request. |
| Client Credentials | `RestClientClientCredentialsTokenResponseClient` | Xin service token từ Token Endpoint. |

API và class cụ thể phụ thuộc phiên bản Spring Security. Ở các bản trước Spring Security 6.4, một số grant sử dụng token response clients dựa trên `RestTemplate`; trong các bản mới có `RestClient` tương ứng.

### 14.1. Vì sao phải cấu hình theo grant?

Một ứng dụng có thể:

- Đổi authorization code thành công qua proxy.
- Nhưng refresh token không đi qua proxy vì refresh token response client vẫn dùng HTTP transport mặc định.
- Hoặc client credentials bị timeout vì phần timeout chỉ được cấu hình cho authorization code grant.

Khi tùy chỉnh provider builder, các API dạng:

```java
.refreshToken(refresh -> refresh
    .accessTokenResponseClient(customRefreshClient)
)
.clientCredentials(clientCredentials -> clientCredentials
    .accessTokenResponseClient(customClientCredentialsClient)
)
```

cho phép truyền token response clients tương ứng nếu phiên bản hỗ trợ overload đó.

`customRefreshClient` và `customClientCredentialsClient` ở đây là **instances đã được tạo với đúng generic grant request type**, không phải tên class có sẵn.

### 14.2. Không viết lại token request chỉ để thay timeout

Nếu cần proxy, TLS, connect/read timeout, hãy tùy chỉnh `RestClient`/request factory của token response client thay vì tự POST JSON/form rồi parse token thủ công.

OAuth2 token response clients đã xử lý những chi tiết như client authentication, body form, token response, OAuth2 errors và phần mở rộng của grant. Tự thay chúng bằng HTTP request tự chế dễ làm mất các ràng buộc giao thức.

## 15. Lưu authorized client sau khi provider trả kết quả

Provider trả `OAuth2AuthorizedClient` không có nghĩa token đã được lưu ở nơi mà mọi request sau có thể tìm thấy. Manager thường kết hợp **success handler** và **repository/service** để lưu kết quả.

Mối quan hệ:

```text
Provider authorize(context)
    |
    +-- Trả null:
    |      Manager có thể giữ authorized client hiện tại
    |
    +-- Trả OAuth2AuthorizedClient:
    |      Manager xử lý success
    |      |
    |      +-- Repository / Service lưu token mới
    |
    +-- Ném lỗi:
           Manager xử lý failure theo policy
           Có thể xóa authorized client trong một số trường hợp
```

### 15.1. InMemory, JDBC và session khác nhau thế nào?

| Store | Đặc điểm |
|---|---|
| `InMemoryOAuth2AuthorizedClientService` | Dễ thử nghiệm, lưu trong RAM, không tự chia sẻ giữa nodes, mất khi restart. |
| `JdbcOAuth2AuthorizedClientService` | Có persistence trong DB, cần schema, TLS, encryption, backup và lifecycle policy. |
| `HttpSessionOAuth2AuthorizedClientRepository` | Lưu trong HTTP session, phù hợp các flow gắn phiên; phụ thuộc session lifecycle. |
| `AuthenticatedPrincipalOAuth2AuthorizedClientRepository` | Định tuyến authenticated sang service, anonymous mặc định sang session. |
| Custom store | Có thể gắn Redis/DB/token vault, nhưng phải tự đảm bảo correctness, confidentiality, concurrency. |

**Provider chain quyết định chiến lược cấp token, không quyết định nơi lưu token.** Chọn storage là nhiệm vụ của manager và các implementation repository/service.

### 15.2. Khi thay store, phải kiểm tra manager có dùng đúng store

Một dự án có thể đã khai báo JDBC service nhưng một custom manager vẫn sử dụng một InMemory service khác. Kết quả: sau restart không thấy token dù đã có bảng DB.

Cần đảm bảo wiring theo cùng một nguồn cấu hình. Đừng nhầm `ClientRegistrationRepository` (metadata) với `OAuth2AuthorizedClientService` (tokens đã được cấp).

## 16. Success handler và failure handler

Các manager có thể cung cấp điểm mở rộng cho **authorization success** và **authorization failure**.

### 16.1. Success

Khi provider thành công, manager thường lưu authorized client tương ứng. Nếu bạn thay success handler, cần bảo đảm:

- Token mới được lưu đúng registration ID và principal.
- Refresh token rotation được cập nhật.
- Không ghi token nhạy cảm vào logs.
- Không vô tình lưu token người dùng dưới service principal khác.

### 16.2. Failure

Khi token endpoint trả lỗi, một số lỗi cho thấy token/authorization hiện tại không còn sử dụng được. Ví dụ `invalid_grant` với refresh token bị thu hồi có thể dẫn tới việc xóa authorized client khỏi store theo failure handling phù hợp.

Nhưng không phải mọi lỗi đều là dấu hiệu nên xóa vĩnh viễn:

| Lỗi | Ý nghĩa thường gặp | Cần làm |
|---|---|---|
| `invalid_grant` khi refresh | Refresh token không hợp lệ/hết hạn/đã dùng lại | Xem chính sách xóa authorized client và reauthorization. |
| `invalid_client` | Client authentication sai | Sửa client ID, secret, assertion hoặc method. |
| HTTP 503/timeout | AS/proxy/network tạm thời không khả dụng | Không tự coi mọi token là bị thu hồi. |
| `insufficient_scope` khi gọi API | Access token không đủ quyền | Cấp đúng scope/consent; không phải lỗi provider chain trực tiếp. |
| API 401 do audience không phù hợp | Token không dành cho resource đó | Kiểm tra API, registration, audience/resource. |

**Không đặt một exception handler nuốt mọi lỗi rồi xin `client_credentials` token thay token của user.** Đây là lỗi bảo mật về loại principal.

## 17. Thứ tự provider không thay thế quy tắc bảo mật

Một composite theo thứ tự có thể tạo cảm giác như một policy engine. Nhưng cần phân biệt:

- Provider quyết định có thể authorize trong ngữ cảnh nào.
- Authorization Server kiểm tra client credentials, grant types, scopes, PKCE và policy.
- Resource Server kiểm tra token, audience, scopes và quyền truy cập API.
- Ứng dụng còn phải kiểm tra business authorization.

Ví dụ một request từ Alice không được phép xem dữ liệu đơn hàng của Bob. Dù provider trả access token hợp lệ, điều đó **không đồng nghĩa** Alice được phép xem mọi đơn hàng.

### 17.1. Không ghép user grant và service grant để lách quyền

Một thiết kế nguy hiểm:

```text
Thử token của Alice
    |
    +-- access token thiếu quyền?
    |
    +-- tự chuyển sang client_credentials token của backend
    |
    +-- gọi API với quyền rộng hơn
```

Provider chain **không phải** phương án để nâng quyền khi user thiếu scope hoặc token hết hạn. Nếu API hỗ trợ một kiến trúc delegated access/token exchange đúng chuẩn, phải thiết kế rõ trust, audience và authorization policies.

## 18. Custom OAuth2AuthorizedClientProvider: khi nào cần?

Bạn nên dùng built-in providers trước. Một custom provider có thể hợp lý khi:

- Authorization Server hỗ trợ grant mở rộng hoặc cơ chế trao đổi token được Spring Security version hiện tại chưa cung cấp trực tiếp.
- Cần áp đặt một lớp policy đặc thù trước khi sử dụng built-in provider.
- Cần một chiến lược đặc biệt theo tenant hoặc registration và không thể biểu diễn bằng manager/builder mặc định.
- Cần quan sát/cấu trúc metrics quanh lần authorize mà vẫn giữ nguyên logic chuẩn.

**Không nên viết custom provider chỉ để đặt connect timeout hoặc proxy.** Những thay đổi đó thuộc token response client/HTTP transport.

### 18.1. Nguyên tắc implement

Một custom provider phải tuân thủ:

1. Trả `null` nếu context không thuộc phạm vi xử lý của provider.
2. Không thao tác token của registration/tenant khác.
3. Không cấp token mới nếu authorized client còn hợp lệ mà contract không yêu cầu.
4. Không trả dummy authorized client.
5. Propagate lỗi giao thức phù hợp để manager xử lý.
6. Không tự lưu/xóa token trong provider nếu manager đang quản lý persistence, trừ khi có thiết kế rõ.
7. Không log token/secret.
8. Không thực hiện retry mù quáng với grants có dữ liệu dùng một lần.
9. Không tự biến token service thành token user.
10. Kiểm thử theo từng nhánh `null`/success/failure.

### 18.2. Một provider lọc registration bằng delegation

Ví dụ muốn một chiến lược chỉ được thử với một nhóm registrations:

```java
import java.util.Set;

import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizationContext;

public final class RegistrationScopedProvider
        implements OAuth2AuthorizedClientProvider {

    private final Set<String> registrations;
    private final OAuth2AuthorizedClientProvider delegate;

    public RegistrationScopedProvider(
            Set<String> registrations,
            OAuth2AuthorizedClientProvider delegate) {
        this.registrations = Set.copyOf(registrations);
        this.delegate = delegate;
    }

    @Override
    public OAuth2AuthorizedClient authorize(
            OAuth2AuthorizationContext context) {

        String registrationId = context
            .getClientRegistration()
            .getRegistrationId();

        if (!registrations.contains(registrationId)) {
            return null;
        }

        return delegate.authorize(context);
    }
}
```

Giả sử sử dụng:

```java
OAuth2AuthorizedClientProvider builtIn =
    OAuth2AuthorizedClientProviderBuilder.builder()
        .clientCredentials()
        .build();

OAuth2AuthorizedClientProvider scoped =
    new RegistrationScopedProvider(
        Set.of("inventory-api"),
        builtIn
    );
```

Nếu `scoped` là **provider duy nhất** của manager dành cho service-token use case, manager chỉ thử grant được delegate hỗ trợ với registration allowlist.

**Cảnh báo:** trả `null` không phải cơ chế chặn quyền nếu sau đó bạn tiếp tục ghép một provider khác có thể authorize cùng registration. Provider tiếp theo vẫn có thể chạy. Nếu mục tiêu là **từ chối tuyệt đối** một registration, cần thực thi policy ở ranh giới có quyền quyết định, hoặc ném một lỗi policy thích hợp từ wrapper bao phủ toàn chuỗi, và phải có authorization policy ở các tầng liên quan.

### 18.3. Ghép trực tiếp với DelegatingOAuth2AuthorizedClientProvider

Ngoài builder, có thể ghép các provider instances tường minh:

```java
import org.springframework.security.oauth2.client.DelegatingOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.OAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.RefreshTokenOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ClientCredentialsOAuth2AuthorizedClientProvider;

OAuth2AuthorizedClientProvider provider =
    new DelegatingOAuth2AuthorizedClientProvider(
        new RefreshTokenOAuth2AuthorizedClientProvider(),
        new ClientCredentialsOAuth2AuthorizedClientProvider()
    );
```

Cách này hữu ích khi cần cấu hình instance chi tiết hoặc lồng một custom provider. Chỉ sử dụng những grant thật sự phù hợp với manager và registration.

## 19. Tùy chỉnh grant khác với viết grant mới

Có nhiều mức độ mở rộng:

| Nhu cầu | Cách tiếp cận |
|---|---|
| Hỗ trợ authorization code + refresh + client credentials | `OAuth2AuthorizedClientProviderBuilder`. |
| Thay timeout, proxy, TLS của token HTTP request | Token response client/RestClient/WebClient. |
| Thêm tham số token request theo hợp đồng provider | Converter/customizer của token response client. |
| Thay clock skew | Builder grant customizer hoặc provider setter. |
| Chọn storage cho authorized client | Repository/Service của manager. |
| Xử lý token refresh thất bại | Failure handler/policy ở manager. |
| Hỗ trợ grant hoàn toàn riêng | Custom `OAuth2AuthorizedClientProvider` và token response client tương ứng. |
| Đổi cách gọi resource API | HTTP client của API, không phải provider chain. |

### 19.1. Không tự thêm một grant chưa được AS hỗ trợ

Ví dụ OAuth2 token exchange hoặc JWT bearer assertion chỉ có ý nghĩa khi Authorization Server đã triển khai grant đó và client đã được cấp quyền sử dụng. Tùy Spring Security version, có thể có built-in support hoặc cần custom extension.

Không thể thay đổi một `authorizationGrantType` trong Java rồi mặc định AS sẽ chấp nhận. Phải đối chiếu metadata, policy và registration phía AS.

### 19.2. Test custom grant với contract rõ ràng

Một custom provider nên được test ở các tình huống:

```text
Registration không hỗ trợ -> trả null.
Registration phù hợp, token còn hiệu lực -> không reauthorize.
Registration phù hợp, cần token -> gọi đúng token client.
Token response hợp lệ -> trả OAuth2AuthorizedClient.
Token endpoint invalid_client -> ném lỗi, không chuyển grant ngẫu nhiên.
Network timeout -> lỗi có thông tin phù hợp, không log credential.
```

Bảo đảm principal name, audience/scope và refresh token lifecycle đúng contract.

## 20. Reactive/WebFlux có cùng ý tưởng ghép provider

Trong **Spring Security WebFlux**, họ API tương ứng:

```java
ReactiveOAuth2AuthorizedClientProvider
ReactiveOAuth2AuthorizedClientProviderBuilder
DefaultReactiveOAuth2AuthorizedClientManager
AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager
```

Khác biệt chính là kết quả reactive, thường là:

```java
Mono<OAuth2AuthorizedClient>
```

Ý tưởng tương đương:

- `Mono` phát ra authorized client: provider xử lý thành công.
- `Mono.empty()`: provider không áp dụng hoặc không cần reauthorize.
- `Mono.error(...)`: có lỗi; không tự động coi như một fallback grant.

### 20.1. Ví dụ reactive provider builder

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProvider;
import org.springframework.security.oauth2.client.ReactiveOAuth2AuthorizedClientProviderBuilder;

@Configuration
public class ReactiveProviderConfig {

    @Bean
    ReactiveOAuth2AuthorizedClientProvider reactiveAuthorizedClientProvider() {
        return ReactiveOAuth2AuthorizedClientProviderBuilder.builder()
            .authorizationCode()
            .refreshToken()
            .clientCredentials()
            .build();
    }
}
```

Để sử dụng, gắn provider vào reactive manager đã chọn. Đối với request web, manager thường dùng `ReactiveClientRegistrationRepository` và `ServerOAuth2AuthorizedClientRepository`. Với tác vụ ngoài web, dùng `ReactiveOAuth2AuthorizedClientService` cùng service-oriented reactive manager.

### 20.2. Không đưa Servlet provider vào reactive manager

Các kiểu:

```text
OAuth2AuthorizedClientProvider
ReactiveOAuth2AuthorizedClientProvider
```

không giống nhau. Servlet provider có kết quả đồng bộ, trong khi reactive provider dùng reactive publisher. Không gọi blocking token HTTP client bên trong event loop WebFlux rồi kỳ vọng có non-blocking behavior.

## 21. Chọn manager và provider theo từng kiến trúc

| Ứng dụng | Manager phù hợp | Provider chain thường dùng | Store |
|---|---|---|---|
| MVC portal login OAuth2/OIDC | `DefaultOAuth2AuthorizedClientManager` cho web request; OAuth2 Login infrastructure | `authorizationCode` + `refreshToken` | Servlet repository/session/service |
| MVC portal gọi thêm service API | Có thể kết hợp manager cho user và manager riêng cho service | User: `authorizationCode`/`refreshToken`; Service: `clientCredentials` | Tách principal namespace và store nếu cần |
| Scheduled backend job | `AuthorizedClientServiceOAuth2AuthorizedClientManager` | `clientCredentials` | `OAuth2AuthorizedClientService` |
| Background job thay mặt user đã consent | Service-oriented manager với policy/authorization đã có | `refreshToken` và cơ chế cấp lại hợp lệ | Persistent service khi được phép |
| WebFlux web application | `DefaultReactiveOAuth2AuthorizedClientManager` | Reactive authorizationCode/refreshToken... | Reactive repositories |
| Reactive background job | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` | Reactive clientCredentials hoặc grant phù hợp | Reactive authorized client service |

Không có lý do bắt buộc phải tạo một composite chứa toàn bộ grants cho mọi ứng dụng. **Ưu tiên cấu hình nhỏ nhất đáp ứng đúng các loại authorization cần thiết.**

## 22. Troubleshooting: ghép provider nhưng không cấp được token

| Triệu chứng | Khả năng nguyên nhân | Hướng kiểm tra |
|---|---|---|
| Manager trả `null` | Không có provider hỗ trợ context, chưa có authorized client hoặc thiếu điều kiện | Registration grant type, provider chain, context |
| Manager ném `ClientAuthorizationRequiredException` | Authorization Code Grant cần browser interaction | Luồng login/redirect, HTTP request context |
| Client credentials không chạy | Chain thiếu `.clientCredentials()` hoặc registration dùng grant khác | Builder và `authorization-grant-type` |
| Không refresh | Thiếu `.refreshToken()`, không có refresh token, hoặc token còn hạn | Existing authorized client, refresh token, clock skew |
| Refresh bị `invalid_grant` | Refresh token hết hạn/bị revoke/đã rotate, binding sai | AS logs theo policy, refresh token lifecycle |
| OAuth2 `invalid_client` | Client secret/method/assertion sai | Client registration và token HTTP client |
| Token endpoint timeout | Proxy/TLS/connect/read timeout | Grant-specific token response client |
| Token mất sau restart | InMemory service hoặc session local | Repository/service persistence |
| Refresh nhiều pods lỗi ngẫu nhiên | Race do rotation | Shared storage và concurrency control |
| User token bị thay bằng service token | Ghép grants/sử dụng principal sai | Tách manager và ngữ cảnh ủy quyền |
| Có token nhưng API 403 | Scope/role/business authorization không đủ | Resource Server policy, scope, audience |
| Có token nhưng API 401 | Token expired/audience/issuer sai | API validation, token lifecycle |
| Custom provider trả non-null quá sớm | Thứ tự chain và return semantics sai | Trả null khi không xử lý, test provider chain |
| Custom provider throw rồi fallback không chạy | Composite dừng khi exception | Phân biệt no-op và failure, không nuốt lỗi |
| OIDC login lỗi chữ ký ID Token | JWKS/issuer/audience/nonce | OIDC validation, không phải chain provider |
| Tác vụ nền lỗi do thiếu HTTP request | Dùng Servlet manager ngoài request context | Chọn service-oriented manager |

### 22.1. `null` của provider và `null` của manager không phải điều giống hệt

Provider trả `null` có thể đơn giản nghĩa **không cần đổi token**, ví dụ token hiện tại còn hạn. Manager có thể tiếp tục trả authorized client đã có.

Nếu **manager trả `null`**, caller không có authorized client dùng được theo kết quả hiện tại. Cần xét client registration, existing authorized client, provider chain và flow đang dùng, không lập tức kết luận Authorization Server lỗi.

### 22.2. Provider chain không có nghĩa token sẽ tự được refresh trong mọi trường hợp

`refreshToken()` chỉ có thể làm việc nếu manager có một authorized client với refresh token phù hợp. Nếu custom code không lưu authorized client, lần gọi tiếp theo có thể không tìm thấy token cũ để refresh.

Phải cấu hình repository/service và success/failure handling phù hợp.

### 22.3. Không log secret khi debug

Token request/response có thể chứa:

```text
client_secret
client_assertion
authorization_code
code_verifier
access_token
refresh_token
id_token
```

Hãy log registration ID được phép, grant type, timing, HTTP status và error code đã lọc. Không in token, Basic Authorization header hoặc signed assertion.

## 23. Các tình huống vận dụng

### Tình huống A: Portal OIDC có authorizationCode + refreshToken

Người dùng đăng nhập bằng `portal-login`, token hết hạn sau một giờ và provider có cấp refresh token.

**Cấu hình:** manager hỗ trợ `authorizationCode()` và `refreshToken()`. Đảm bảo authorized client được lưu theo đúng user/principal, và refresh token response client kết nối được Token Endpoint. Không yêu cầu browser đăng nhập lại nếu refresh thành công theo policy.

### Tình huống B: Service lấy token bằng clientCredentials

Một inventory scheduler không có user session.

**Cấu hình:** service-oriented manager và `.clientCredentials()`. Sử dụng principal name ổn định phục vụ cache token của service, không giả danh user.

### Tình huống C: Dùng `.clientCredentials()` để chữa token user hết hạn

Một team thêm `.clientCredentials()` sau `.refreshToken()` và kỳ vọng nếu refresh user token lỗi thì service token sẽ tự động thay thế.

**Kết luận:** Sai mô hình. Refresh lỗi thường là exception; provider chain không tự động fallback. Hơn nữa service token không thể đại diện người dùng nếu authorization/policy không cho phép.

### Tình huống D: Custom provider luôn trả authorized client cũ

Một provider tùy chỉnh nhận context, thấy existing client và trả lại nó dù access token đã hết hạn.

**Kết luận:** Trả non-null quá sớm có thể khiến providers tiếp theo không chạy. Với tình huống không cần xử lý hoặc không hỗ trợ, trả `null` theo contract, để manager quyết định về existing client.

### Tình huống E: Background job dùng authorizationCode khi chưa có token

Job chạy không có browser và manager báo cần authorization.

**Cách giải quyết:** cần thiết kế luồng cấp quyền tương tác trước đó hoặc sử dụng grant đúng mô hình như client credentials khi quyền service phù hợp. Không tự nhập username/password người dùng vào job.

### Tình huống F: API của đối tác yêu cầu refresh token rotation

Hai nodes cùng refresh token RT1.

**Cách giải quyết:** token storage và concurrency policy phải xử lý rotation. Provider builder không tự khóa distributed refresh.

### Tình huống G: Đã cấu hình builder nhưng manager khác đang được dùng

Ứng dụng có hai `OAuth2AuthorizedClientManager` beans; controller inject nhầm manager không hỗ trợ refresh token.

**Cách giải quyết:** đặt tên/qualifier rõ, cấu hình provider chain trên đúng manager được sử dụng.

### Tình huống H: Custom token response client mất OAuth2 error handler

Lúc refresh trả HTTP 400, code tự chế chỉ đọc JSON và nuốt lỗi.

**Cách giải quyết:** sử dụng token response clients của Spring Security và tùy chỉnh transport/converter đúng API để giữ protocol error handling.

### Tình huống I: Một application có hai registration khác grant

`portal-login` là authorization code, `inventory-api` là client credentials.

**Cách hiểu:** chain có thể có cả hai grant, nhưng mỗi request authorize phải chọn đúng registration/principal. Cân nhắc hai managers riêng để giảm rủi ro sử dụng sai token.

### Tình huống J: OIDC login thành công, API gọi thất bại

Provider chain tạo authorized client thành công nhưng API trả 403.

**Cách xử lý:** kiểm tra access token scope/audience và policy Resource Server. Cấp token thành công không mặc nhiên cấp mọi quyền nghiệp vụ.

## 24. Câu hỏi tự kiểm tra

**Câu 1.** `OAuth2AuthorizedClientProvider` và `OAuth2AuthorizedClientManager` khác nhau ra sao?

**Trả lời:** Manager phối hợp registration, context, persistence và authorization lifecycle; provider quyết định có thể/cần authorize hoặc reauthorize theo một chiến lược OAuth2.

**Câu 2.** Provider trả `null` có nghĩa authorization thất bại không?

**Trả lời:** Không nhất thiết. Provider có thể không hỗ trợ grant hoặc token hiện tại vẫn hợp lệ nên chưa cần làm gì.

**Câu 3.** Composite làm gì nếu provider đầu tiên trả authorized client?

**Trả lời:** Trả kết quả ngay; không tiếp tục gọi các providers sau.

**Câu 4.** Composite làm gì nếu provider đầu tiên ném OAuth2AuthorizationException?

**Trả lời:** Lỗi thường lan ra theo contract và chuỗi không tự động thử provider tiếp như một cơ chế failover.

**Câu 5.** Thêm `.refreshToken()` có bảo đảm luôn refresh được access token không?

**Trả lời:** Không. Cần existing authorized client, refresh token hợp lệ, grant/policy phù hợp và Authorization Server chấp nhận.

**Câu 6.** Vì sao `client_credentials` không thể dùng để thay token người dùng?

**Trả lời:** Nó đại diện cho client/service, không mang authorization của người dùng.

**Câu 7.** Khi nào dùng `AuthorizedClientServiceOAuth2AuthorizedClientManager`?

**Trả lời:** Khi authorization được quản lý ngoài Servlet request, chẳng hạn scheduled jobs hoặc service backend.

**Câu 8.** Vì sao đổi provider builder nhưng token vẫn mất sau restart?

**Trả lời:** Builder không quyết định storage; cần kiểm tra authorized client repository/service.

**Câu 9.** Nên thay class nào để cấu hình HTTP proxy của refresh token request?

**Trả lời:** Token response client/HTTP transport dùng bởi refresh token provider, không phải `ClientRegistrationRepository`.

**Câu 10.** Custom provider nên trả gì khi không hỗ trợ registration?

**Trả lời:** `null`, để composite có thể xét provider tiếp theo nếu được thiết kế như vậy.

**Câu 11.** Có thể dùng một principal name cố định cho mọi user trong service manager không?

**Trả lời:** Không nếu token đại diện các users khác nhau; cách đó có thể dẫn tới token sharing chéo tài khoản. Với client credentials, một service principal ổn định có thể phù hợp nếu thật sự cùng một service authorization.

**Câu 12.** Clock skew dùng để làm gì?

**Trả lời:** Xem access token là sắp hết hạn sớm hơn một khoảng để giảm rủi ro hết hạn trong lúc sử dụng và bù sai lệch đồng hồ nhỏ.

## 25. Ghi nhớ trọng tâm

| Khái niệm | Điều cần nhớ |
|---|---|
| **`OAuth2AuthorizedClientProvider`** | Strategy thực hiện authorization/reauthorization theo context. |
| **`authorize(context)` trả authorized client** | Có kết quả xử lý; manager có thể lưu. |
| **`authorize(context)` trả `null`** | Provider không áp dụng hoặc không cần reauthorize. |
| **`authorize(context)` ném exception** | Lỗi/tình huống yêu cầu xử lý đặc biệt; không phải fallback grant. |
| **`DelegatingOAuth2AuthorizedClientProvider`** | Ghép providers theo thứ tự; dừng tại kết quả non-null hoặc lỗi. |
| **`OAuth2AuthorizedClientProviderBuilder`** | Tạo composite dễ cấu hình cho các grants được chọn. |
| **`authorizationCode()`** | Tương tác với luồng authorization code, có thể cần browser redirect. |
| **`refreshToken()`** | Reauthorize bằng refresh token nếu có và cần thiết. |
| **`clientCredentials()`** | Token cho client/service, không đại diện user. |
| **`DefaultOAuth2AuthorizedClientManager`** | Manager dành cho Servlet web request, dùng authorized client repository. |
| **`AuthorizedClientServiceOAuth2AuthorizedClientManager`** | Manager dành cho tác vụ ngoài Servlet request, dùng authorized client service. |
| **`OAuth2AuthorizedClientService` / Repository** | Quyết định cách truy xuất/lưu token; độc lập với provider chain. |
| **Clock skew** | Khoảng đệm khi xác định access token gần hết hạn. |
| **Refresh token rotation** | Cần lưu token mới và quản lý concurrency giữa nodes. |
| **Token response client** | Nơi tùy chỉnh HTTP transport/parameters theo từng grant. |
| **OIDC ID Token validation** | Thuộc luồng xác thực OIDC riêng, không phải một provider của builder. |

**Kết luận:** `OAuth2AuthorizedClientProvider` là lớp **chiến lược** mà `OAuth2AuthorizedClientManager` dùng để cấp hoặc cấp lại authorized client theo nhu cầu. `OAuth2AuthorizedClientProviderBuilder` tạo một chuỗi providers như `authorizationCode`, `refreshToken` và `clientCredentials`; chuỗi đó **không phải failover tùy ý giữa các grants**. Hiểu đúng `null`, non-null, exception, thứ tự provider và ngữ cảnh principal giúp ứng dụng quản lý token an toàn, rõ ràng. Hãy chọn provider chain theo loại authorization thực sự được phép, chọn manager theo HTTP/background context, và cấu hình storage/token response client riêng theo yêu cầu vận hành.

## Tài liệu tham khảo

- [Spring Security — OAuth2 Client Authorized Clients (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html): authorized client manager, provider, service và repository.
- [Spring Security — OAuth2 Client Authorization Grants (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorization-grants.html): các grants và token response client customization.
- [Spring Security API — OAuth2AuthorizedClientProvider](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientProvider.html): contract của `authorize(...)`.
- [Spring Security API — OAuth2AuthorizedClientProviderBuilder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/OAuth2AuthorizedClientProviderBuilder.html): cấu hình provider chain.
- [Spring Security API — DefaultOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizedClientManager.html): quản lý OAuth2 clients trong Servlet request.
- [Spring Security API — AuthorizedClientServiceOAuth2AuthorizedClientManager](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/AuthorizedClientServiceOAuth2AuthorizedClientManager.html): quản lý clients ngoài HTTP request.
- [Spring Security — Reactive OAuth2 Client](https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html): reactive manager và provider tương ứng.
