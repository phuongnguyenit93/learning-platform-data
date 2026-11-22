# client_secret_basic và client_secret_post

Trong OAuth 2.0/OpenID Connect (OIDC), **client authentication** là quá trình Authorization Server xác minh một ứng dụng khách đang tự nhận là ai khi gọi những endpoint yêu cầu xác thực client, điển hình là **token endpoint**. Hai phương thức phổ biến sử dụng bí mật dùng chung (shared secret) là **`client_secret_basic`** và **`client_secret_post`**. Chúng khác nhau ở **vị trí truyền `client_id` và `client_secret` trong HTTP request**, chứ không khác nhau ở việc bí mật được cấp cho loại client nào.

Bài học thuộc chương **Xác thực client** của module **SPRING_SECURITY_OAUTH2_OIDC_AUTHORIZATION_SERVER** giải thích cú pháp chuẩn, cách Spring Authorization Server nhận diện và xác thực từng phương thức, đăng ký `RegisteredClient`, cấu hình Spring Security OAuth2 Client, quản lý bí mật, xử lý lỗi và kiểm thử. Đây là một phần quan trọng khi học thiết kế, cấu hình, bảo mật và vận hành Authorization Server bằng Spring Boot.

> **Phạm vi:** Hai phương thức này dành cho các client có khả năng giữ bí mật, thường là **confidential client** ở backend. Các đoạn HTTP/Java/YAML minh họa nguyên lý và cần dependencies, cấu hình AS, phiên bản Spring và dữ liệu thử nghiệm phù hợp để chạy.

## 1. Xác thực client trả lời câu hỏi gì?

OAuth 2.0 có những chủ thể khác nhau: **người dùng** (resource owner trong nhiều luồng), **OAuth2 Client** (ứng dụng xin token), **Authorization Server** (bên cấp token) và **Resource Server** (API bảo vệ tài nguyên).

Xác thực client trả lời: **“Ứng dụng gửi request có thật sự sở hữu credential được đăng ký cho `client_id` này không?”** Đây không phải câu hỏi “Người dùng đã đăng nhập chưa?”.

Ví dụ hệ thống có ứng dụng nền `batch-reports` gọi token endpoint bằng grant `client_credentials`:

1. Quản trị viên đăng ký `client_id=batch-reports` cùng phương thức xác thực và credential tại Authorization Server.
2. Ứng dụng nền gửi `POST /oauth2/token` kèm `grant_type=client_credentials` và credential theo phương thức đã đăng ký.
3. Authorization Server xác minh **danh tính client**, grant và scope được phép.
4. Nếu yêu cầu hợp lệ, AS phát hành access token để ứng dụng gọi API đã được bảo vệ.

Trong ví dụ trên **không có người dùng cuối đăng nhập**, nên cũng không có ID Token OIDC đại diện cho việc người dùng vừa xác thực.

Với Authorization Code flow, người dùng có thể đăng nhập và chấp thuận quyền trước đó, nhưng **confidential client vẫn phải xác thực chính mình khi đổi authorization code lấy token** nếu AS yêu cầu. Cơ chế này không thay thế việc kiểm tra authorization code, redirect URI hoặc PKCE.

## 2. So sánh nhanh hai phương thức

| Tiêu chí | `client_secret_basic` | `client_secret_post` |
|---|---|---|
| Nơi truyền credential | HTTP header `Authorization: Basic ...` | HTTP body dạng `application/x-www-form-urlencoded` |
| Tham số `client_id`/`client_secret` trong body | Thường **không** có; credential nằm trong Basic header | **Có** cả `client_id` và `client_secret` |
| Thuật toán mã hóa trên request | Form URL-encode mỗi thành phần, ghép bằng dấu `:` rồi Base64 | Form URL-encode thành các field trong body |
| Base64 có bảo mật bí mật không? | **Không.** Base64 chỉ là encoding, ai đọc header đều có thể giải mã | Không dùng Base64 ở tầng này; ai đọc được body vẫn có thể thấy secret |
| Hỗ trợ theo OAuth 2.0 RFC 6749 | AS **MUST support** HTTP Basic khi cấp client password | AS **MAY support**, nhưng RFC 6749 **không khuyến nghị** trừ client không thể dùng Basic |
| Rủi ro log thường gặp | Proxy/APM hoặc HTTP client ghi `Authorization` header | Proxy/APM/framework ghi request body/form parameter |
| Thiết lập trong Spring | `ClientAuthenticationMethod.CLIENT_SECRET_BASIC` | `ClientAuthenticationMethod.CLIENT_SECRET_POST` |
| Điều kiện quan trọng | Client có secret, AS cho phép Basic, **HTTPS** | Client có secret, AS cho phép Post, **HTTPS** |

**Lựa chọn mặc định hợp lý khi AS và client đều hỗ trợ:** sử dụng `client_secret_basic`. Chỉ chọn `client_secret_post` khi có yêu cầu tương thích đã được đánh giá, kiểm soát rủi ro ghi log request body và xác nhận AS hỗ trợ. Với yêu cầu an ninh cao, có thể cần phương thức xác thực bất đối xứng như `private_key_jwt` hoặc mTLS thay cho shared secret; đó là cơ chế khác, không phải biến thể của Basic/Post.

### 2.1. “client_secret” không có nghĩa là “client-side”

Tên `client_secret` dễ gây hiểu nhầm rằng secret nên nằm trong code JavaScript của browser. Điều đó **không đúng**: client secret chỉ có ý nghĩa xác thực khi ứng dụng có thể giữ nó kín, ví dụ một backend được kiểm soát. Nếu nhúng secret vào bundle SPA, ứng dụng mobile, source code công khai hoặc đường dẫn URL, người khác có thể trích xuất và giả mạo client.

Một **public client** thông thường sử dụng `ClientAuthenticationMethod.NONE` và Authorization Code + PKCE, không dùng `client_secret_basic` hay `client_secret_post` bằng một secret được hardcode trong browser.

## 3. Luồng `client_secret_basic`: credential nằm trong HTTP Basic header

Theo **RFC 6749 $2.3.1**, Authorization Server phải hỗ trợ HTTP Basic để xác thực các client đã được cấp client password. Trong yêu cầu tới token endpoint, client gửi:

```http
POST /oauth2/token HTTP/1.1
Host: identity.example.com
Authorization: Basic BASE64_OF_ENCODED_CLIENT_ID_COLON_ENCODED_CLIENT_SECRET
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=client_credentials&scope=documents.read
```

Chuỗi dài sau `Basic` là **placeholder**, không phải credential thật. Các bước chuẩn để tạo phần payload của Basic:

1. URL-encode `client_id` theo quy tắc `application/x-www-form-urlencoded` (UTF-8).
2. URL-encode `client_secret` theo cùng quy tắc.
3. Ghép hai chuỗi đã encode bằng **một dấu hai chấm `:`**.
4. Base64-encode chuỗi ghép và đặt vào `Authorization: Basic <base64>`.

Biểu thức minh họa:

```text
header = "Basic " + Base64(
  formUrlEncode(client_id) + ":" + formUrlEncode(client_secret)
)
```

**Chi tiết quan trọng:** RFC 6749 không đơn thuần yêu cầu Base64 của chuỗi `client_id:client_secret` thô khi credential chứa ký tự đặc biệt. Mỗi thành phần phải được **form URL-encode trước khi ghép**. Ví dụ giả định `client_id` là `report:agent` và secret minh họa là `demo+value`:

```text
client_id gốc       = report:agent
client_secret gốc   = demo+value
client_id đã encode = report%3Aagent
secret đã encode    = demo%2Bvalue
chuỗi trước Base64  = report%3Aagent:demo%2Bvalue
```

Ký tự `:` trong ID được encode thành `%3A` để tránh nhầm với dấu ngăn cách Basic; dấu `+` trong secret được encode thành `%2B`. Giá trị `demo+value` chỉ dành cho giải thích encoding, **không phải secret nên dùng trong môi trường thực**.

### 3.1. Ví dụ Java tạo header để hiểu định dạng

```java
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

// Minh họa encoding RFC 6749, không phải lý do để tự viết OAuth2 Client.
String clientId = "report:agent";
String clientSecret = System.getenv("REPORT_AGENT_CLIENT_SECRET");

String encodedId = URLEncoder.encode(
    clientId, StandardCharsets.UTF_8);
String encodedSecret = URLEncoder.encode(
    clientSecret, StandardCharsets.UTF_8);

String credentials = encodedId + ":" + encodedSecret;
String authorizationHeader = "Basic " +
    Base64.getEncoder().encodeToString(
        credentials.getBytes(StandardCharsets.UTF_8));
```

Ví dụ chưa xử lý trường hợp biến môi trường vắng mặt và không nên log `authorizationHeader`. Trong ứng dụng thực, dùng **Spring Security OAuth2 Client hoặc HTTP client có hỗ trợ OAuth** để chuẩn hóa encoding, retry và bảo mật. Việc dùng `String` ở Java cũng không làm credential tự biến mất khỏi bộ nhớ.

### 3.2. Header Basic được bảo vệ như thế nào?

HTTP Basic **không mã hóa** secret; Base64 có thể giải mã dễ dàng. **TLS/HTTPS là bắt buộc** để chống nghe lén trên đường truyền. Nhưng ngay cả khi kết nối đã dùng HTTPS, các điểm kết thúc TLS như reverse proxy và chính ứng dụng vẫn có thể đọc header. Do đó phải **che/loại bỏ header `Authorization` khỏi log, trace và error reporting**.

Tại token endpoint, header `Authorization: Basic ...` dùng để **xác thực client với Authorization Server**. Đừng nhầm với header `Authorization: Bearer <access_token>` mà Client gửi tới **Resource Server** để truy cập API.

## 4. Luồng `client_secret_post`: credential nằm trong form body

Với `client_secret_post`, client gửi `client_id` và `client_secret` dưới dạng các tham số **HTTP POST body**, theo `application/x-www-form-urlencoded`:

```http
POST /oauth2/token HTTP/1.1
Host: identity.example.com
Content-Type: application/x-www-form-urlencoded
Accept: application/json

grant_type=client_credentials&scope=documents.read&client_id=batch-reports&client_secret=REDACTED_SECRET
```

`REDACTED_SECRET` chỉ là placeholder. Credential thật phải được form URL-encode đúng cách và chỉ gửi qua HTTPS. Một HTTP client chuyên dụng sẽ tự xử lý encoding form field; không nối chuỗi secret thô vào URL hoặc query.

Những điểm cần nhớ:

- Đây là **POST body**, **không phải** `/oauth2/token?client_secret=...` trong query string.
- Body phải mang đúng `Content-Type: application/x-www-form-urlencoded` và các field được encode theo form.
- Client **không gửi thêm** `Authorization: Basic ...` cho chính request đó. RFC 6749 quy định client **không được sử dụng nhiều hơn một phương thức client authentication trong cùng request**.
- AS chỉ nên chấp nhận `client_secret_post` nếu phương thức đó được hỗ trợ và registration của client cho phép.
- Secret vẫn có thể bị ghi bởi HTTP body logging, reverse proxy, APM hoặc middleware; không coi body là nơi cất giữ an toàn.

### 4.1. Vì sao OAuth 2.0 không khuyến nghị client_secret_post?

RFC 6749 cho phép AS hỗ trợ việc gửi client credentials qua form body **nhưng không khuyến nghị**, chỉ nên giới hạn ở client không thể sử dụng HTTP Basic. Body có xu hướng đi qua những thành phần thu thập payload phục vụ debug, validation và observability; việc truyền secret trong form field cũng dễ bị vô tình đưa vào log hoặc telemetry. Tuy nhiên **Basic cũng không miễn nhiễm với lộ secret**, vì reverse proxy có thể ghi raw header.

Không kết luận “`client_secret_post` luôn bị tấn công” hoặc “Basic luôn an toàn”. Hai phương thức đều dựa trên **shared secret**; sự an toàn phụ thuộc TLS, môi trường giữ secret, đăng ký client, kiểm soát log, hạn chế truy cập và quy trình rotation.

## 5. Luồng xử lý ở Spring Authorization Server

Spring Authorization Server sử dụng các thành phần thuộc Spring Security filter chain để xác thực client rồi mới thực hiện token grant. Với hai phương thức đang học, luồng logic có thể được mô tả như sau:

```mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client backend
    participant F as OAuth2ClientAuthenticationFilter
    participant R as RegisteredClientRepository
    participant P as ClientSecretAuthenticationProvider
    participant T as OAuth2TokenEndpointFilter
    participant G as Grant AuthenticationProvider

    C->>F: POST /oauth2/token (Basic header hoặc form body)
    F->>F: Nhận diện client authentication method
    F->>P: Authentication request
    P->>R: findByClientId(clientId)
    R-->>P: RegisteredClient hoặc null
    P->>P: Kiểm tra method, secret, thời hạn/chính sách
    alt Client authentication thất bại
        P-->>F: OAuth2AuthenticationException (invalid_client)
        F-->>C: OAuth2 error response
    else Client authentication thành công
        P-->>F: Authenticated client principal
        F->>T: Chuyển tiếp xử lý token request
        T->>G: Xác minh grant_type, scope và điều kiện grant
        alt Grant hợp lệ
            G-->>T: Token response
            T-->>C: 200 JSON access_token
        else Grant sai
            G-->>T: OAuth2 error
            T-->>C: JSON lỗi phù hợp
        end
    end
```

Đây là **sơ đồ logic**, không diễn tả mọi chi tiết filter/handler của từng phiên bản Spring. `OAuth2ClientAuthenticationFilter` có thể sử dụng các `AuthenticationConverter` chuyên biệt cho Basic hoặc Post; `ClientSecretAuthenticationProvider` là thành phần xử lý client secret. Sau khi client được xác thực, `OAuth2TokenEndpointFilter` mới xử lý yêu cầu grant. **Client authentication thành công chưa bảo đảm token được cấp**: client còn phải được phép dùng grant, scope và đáp ứng các kiểm tra khác.

### 5.1. RegisteredClient quyết định phương thức nào được chấp nhận

Spring lưu metadata client dưới dạng `RegisteredClient`. Các trường liên quan gồm:

| Trường | Vai trò |
|---|---|
| `clientId` | Định danh client trong giao thức |
| `clientSecret` | Secret đã được mã hóa/lưu ở định dạng tương thích `PasswordEncoder` |
| `clientSecretExpiresAt` | Thời hạn secret nếu áp dụng |
| `clientAuthenticationMethods` | **Danh sách phương thức được phép**: Basic, Post, private_key_jwt... |
| `authorizationGrantTypes` | Client được phép dùng grant nào |
| `scopes` | Các scope client được phép yêu cầu |
| `clientSettings` và `tokenSettings` | Chính sách client và token, độc lập với vị trí gửi secret |

Nếu client đã đăng ký **chỉ Basic** nhưng gửi `client_secret_post`, AS phải từ chối client authentication. **Biết đúng secret không đủ** nếu phương thức gửi secret khác với phương thức được cho phép.

### 5.2. Một client có thể đăng ký cả Basic và Post?

`RegisteredClient` có thể chứa nhiều `clientAuthenticationMethod(...)` nếu AS cho phép theo cấu hình. Điều đó có nghĩa client có **các lựa chọn trong những request riêng biệt**, **không** cho phép trộn cả header Basic và form secret trong **cùng một request**.

Khi thiết kế bảo mật, nên chỉ bật các phương thức client thực sự cần. Nếu bật cả hai để di trú từ Post sang Basic, cần có kế hoạch hạn chế thời gian, quan sát usage và loại bỏ phương thức không còn dùng.

## 6. Ví dụ đăng ký hai confidential clients

Đoạn cấu hình sau minh họa hai client dùng grant `client_credentials`, mỗi client chỉ được phép dùng **một** phương thức:

```java
@Bean
PasswordEncoder clientSecretPasswordEncoder() {
    return PasswordEncoderFactories.createDelegatingPasswordEncoder();
}

@Bean
RegisteredClientRepository registeredClientRepository(
        PasswordEncoder clientSecretPasswordEncoder) {

    String basicSecret = requiredEnv("BATCH_REPORTS_CLIENT_SECRET");
    String postSecret = requiredEnv("LEGACY_IMPORT_CLIENT_SECRET");

    RegisteredClient batchReports = RegisteredClient.withId(
            "batch-reports-internal-id")
        .clientId("batch-reports")
        .clientSecret(clientSecretPasswordEncoder.encode(basicSecret))
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
            AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("documents.read")
        .build();

    RegisteredClient legacyImport = RegisteredClient.withId(
            "legacy-import-internal-id")
        .clientId("legacy-import")
        .clientSecret(clientSecretPasswordEncoder.encode(postSecret))
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.CLIENT_SECRET_POST)
        .authorizationGrantType(
            AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("documents.write")
        .build();

    return new InMemoryRegisteredClientRepository(
        batchReports, legacyImport);
}

private static String requiredEnv(String name) {
    String value = System.getenv(name);
    if (value == null || value.isBlank()) {
        throw new IllegalStateException("Missing required secret: " + name);
    }
    return value;
}
```

**Ý nghĩa của ví dụ:**

- `batch-reports` chỉ cho phép `client_secret_basic`; `legacy-import` chỉ cho phép `client_secret_post`.
- Secret được đọc từ cấu hình môi trường khi chạy và lưu ở dạng được `PasswordEncoder` mã hóa một chiều trong `RegisteredClient`. Sử dụng secret manager được kiểm soát là lựa chọn phù hợp hơn cho nhiều môi trường production.
- `PasswordEncoderFactories.createDelegatingPasswordEncoder()` tạo chuỗi hash có tiền tố thuật toán, ví dụ `{bcrypt}...`. Provider xác thực secret phải dùng encoder tương thích. Đừng lưu raw secret hoặc dùng `{noop}` cho production.
- Các `id` trong ví dụ cố định để minh họa định danh nội bộ **ổn định**. Trong hệ thống thật chúng phải duy nhất; không tạo ID khác mỗi lần restart khi authorization/consent được lưu bền vững.
- `InMemoryRegisteredClientRepository` phù hợp học tập/thử nghiệm. Để lưu client qua restart và chia sẻ giữa nhiều AS instance, cân nhắc `JdbcRegisteredClientRepository` hoặc custom persistence với migration và bảo vệ dữ liệu.
- Đây **chưa phải Authorization Server đầy đủ**: cần cấu hình `SecurityFilterChain`, `AuthorizationServerSettings`/issuer, key/JWK, `OAuth2AuthorizationService`, token generator và các bean khác theo flow.

Một ứng dụng thực không cần bật `client_secret_post` chỉ vì thư viện hỗ trợ phương thức đó. Nên ưu tiên Basic cho confidential clients có shared secret khi phù hợp, và lên kế hoạch nâng cấp cơ chế xác thực nếu yêu cầu bảo mật cao hơn.

### 6.1. Không dùng Registration để phát hành toàn bộ quyền

Việc lưu `scope("documents.write")` nghĩa là client **được phép yêu cầu** scope này theo cấu hình, không chứng minh client có quyền vô điều kiện trên mọi bản ghi nghiệp vụ. Authorization Server còn xem xét grant và chính sách phát hành; Resource Server vẫn phải xác minh token, issuer, audience, scope và quyền tài nguyên.

Trong `client_credentials`, access token có thể đại diện cho chính client; không nên giả định mọi token có `sub` là người dùng cuối. `openid` và OIDC ID Token **không phải kết quả mặc định** của client credentials.

## 7. Cấu hình Spring Security OAuth2 Client để dùng Basic hoặc Post

**Phía ứng dụng OAuth2 Client** sử dụng cấu hình `spring.security.oauth2.client.registration` để biết cách xác thực với AS. Đây là cấu hình **khác** với `RegisteredClientRepository` ở phía Authorization Server.

Ví dụ client `batch-reports` dùng Basic:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          batch-reports:
            provider: company-auth
            client-id: batch-reports
            client-secret: "${BATCH_REPORTS_CLIENT_SECRET}"
            client-authentication-method: client_secret_basic
            authorization-grant-type: client_credentials
            scope: documents.read
        provider:
          company-auth:
            token-uri: https://identity.example.com/oauth2/token
```

Để cấu hình một client khác sử dụng Post, trường khác biệt là:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          legacy-import:
            provider: company-auth
            client-id: legacy-import
            client-secret: "${LEGACY_IMPORT_CLIENT_SECRET}"
            client-authentication-method: client_secret_post
            authorization-grant-type: client_credentials
            scope: documents.write
        provider:
          company-auth:
            token-uri: https://identity.example.com/oauth2/token
```

Spring Boot dùng thông tin đăng ký để tạo `ClientRegistration` ở **OAuth2 Client**. Khi một `OAuth2AuthorizedClientManager` hoặc thành phần tương ứng thực hiện client credentials flow, token request sẽ sử dụng phương thức authentication được cấu hình. Với các API Spring Security, cần chọn đúng client provider/authorized client manager và cách lưu authorized client theo ngữ cảnh ứng dụng.

**Cấu hình trên client không tự đăng ký client tại AS.** AS phải có `RegisteredClient` tương ứng với cùng `client_id`, phương thức, secret, grant và scope. Nếu một trong các thành phần không khớp, xác thực hoặc token grant sẽ thất bại.

### 7.1. Một số sai khác cấu hình thường thấy

| Cấu hình ở OAuth2 Client | Cấu hình tại AS | Kết quả |
|---|---|---|
| Basic | Chỉ Basic | Có thể xác thực nếu ID/secret đúng và còn hiệu lực |
| Post | Chỉ Post | Có thể xác thực nếu ID/secret đúng và còn hiệu lực |
| Post | Chỉ Basic | Bị từ chối vì sai phương thức, dù secret đúng |
| Basic | Chỉ Post | Bị từ chối vì sai phương thức, dù secret đúng |
| Basic/Post | Client ID không tồn tại | `invalid_client` trong ngữ cảnh client authentication |
| Basic/Post | Secret không khớp/hết hạn | Không xác thực được client |
| Basic/Post hợp lệ | Client không được dùng `client_credentials` | Client authentication có thể thành công nhưng token grant bị từ chối |

Không dựa vào thông báo lỗi cụ thể để đoán chính sách. Hãy kiểm tra registration của hai phía và logs **đã che secret**.

## 8. Không nhầm client authentication với PKCE, user login và Bearer token

| Cơ chế | Bảo vệ hoặc chứng minh điều gì? | Có thay client secret được không? |
|---|---|---|
| `client_secret_basic` / `client_secret_post` | Client sở hữu shared secret đã đăng ký với AS | Đây chính là hai phương thức client authentication |
| `Authorization Code + PKCE` | Ràng buộc code với `code_verifier` để chống việc đổi code bị đánh cắp | **Không mặc nhiên thay client authentication** của confidential client |
| Đăng nhập người dùng tại AS | Xác thực danh tính resource owner | Không chứng minh OAuth2 Client sở hữu secret |
| OIDC ID Token | Ràng buộc sự kiện xác thực người dùng với RP | Không phải client secret/token request credential |
| `Authorization: Bearer <access_token>` | Quyền truy cập API của token holder | Không dùng để thay Basic/Post ở token request thông thường |
| `private_key_jwt` hoặc mTLS | Xác thực client bằng khóa bất đối xứng hoặc chứng chỉ | Có thể là phương thức thay thế khi AS/client hỗ trợ |

**PKCE và client authentication bổ sung cho nhau** trong confidential Authorization Code flow. PKCE giảm nguy cơ kẻ chiếm được authorization code có thể đổi code; client secret giúp AS xác minh ứng dụng confidential client tại endpoint yêu cầu authentication. Chúng bảo vệ các mối đe dọa khác nhau.

## 9. Lỗi thường gặp và hợp đồng phản hồi

Khi client authentication thất bại, Spring Authorization Server thường biểu diễn kết quả dưới dạng lỗi OAuth 2.0 như `invalid_client`. Mã lỗi này đến từ **client authentication layer**, trước khi token grant thành công.

### 9.1. Ví dụ lỗi do secret hoặc phương thức không hợp lệ

Một phản hồi minh họa:

```http
HTTP/1.1 401 Unauthorized
Content-Type: application/json;charset=UTF-8
WWW-Authenticate: Basic realm="oauth2"
Cache-Control: no-store
Pragma: no-cache

{
  "error": "invalid_client"
}
```

Đây là **ví dụ trường hợp request cố xác thực qua Basic**. Theo RFC 6749, nếu client thử xác thực qua header `Authorization`, AS phải phản hồi `401` và `WWW-Authenticate` tương ứng khi thất bại. Với `client_secret_post`, HTTP status/header có thể khác tùy hợp đồng của endpoint và implementation (thường là `400` kèm `invalid_client`). **Không mặc định mọi lỗi `invalid_client` đều có cùng status hoặc Basic challenge**.

Các tình huống cần phân biệt:

| Điều kiện | Lỗi điển hình | Chẩn đoán |
|---|---|---|
| `client_id` không tồn tại | `invalid_client` | Registration và định danh client |
| Secret không khớp | `invalid_client` | Credential đã cấp/đang được sử dụng |
| Secret hết hạn (nếu được cấu hình) | `invalid_client` | `clientSecretExpiresAt` và quy trình rotation |
| Client chỉ cho Basic nhưng gửi Post | `invalid_client` | `clientAuthenticationMethods` |
| Client gửi cả Basic và Post trong một request | Request không hợp lệ hoặc client auth bị từ chối theo xử lý endpoint | Chỉ dùng **một** phương thức mỗi request |
| Client được xác thực nhưng grant bị cấm | `unauthorized_client` | `authorizationGrantTypes` |
| Client được xác thực nhưng scope sai | `invalid_scope` | `scopes` và token grant |
| Authorization code/refresh token không hợp lệ | `invalid_grant` | Token grant, code/PKCE/binding; **khác** lỗi client secret |

Không đưa raw secret, token, Basic credential hoặc chi tiết kiểm tra mật khẩu vào `error_description`. Phản hồi lỗi an toàn nên ngắn và tránh giúp kẻ tấn công phân biệt thông tin nhạy cảm ngoài mức giao thức cần thiết.

### 9.2. Vì sao đổi sang Post không sửa được secret sai?

Cả hai phương thức đều dùng **cùng loại shared secret**. Nếu secret client đang gửi khác secret mà AS đã đăng ký, chuyển từ Basic sang Post không giúp xác thực thành công, trừ khi lỗi ban đầu thật sự nằm ở **encoding hoặc phương thức không tương thích**. Khi debug, kiểm tra lần lượt:

1. `client_id` nào được gửi và được AS đăng ký?
2. AS cho phép Basic, Post hay phương thức nào khác?
3. Raw secret phía client có đúng và đã hết hạn không?
4. Mã hóa Basic có form URL-encode các ký tự đặc biệt trước Base64 không?
5. Request có đúng `Content-Type` và đúng body/header không, có gửi trùng phương thức không?
6. Có proxy, gateway hoặc cấu hình bảo mật làm mất/sửa `Authorization` header hay form body không?

Không giải quyết bằng cách bật cả hai phương thức vĩnh viễn hoặc tắt xác thực client.

## 10. Bảo vệ client secret trên toàn tuyến

### 10.1. TLS và ranh giới tin cậy

HTTP Basic Base64 chỉ encode; form body cũng là dữ liệu có thể đọc được ở nơi HTTP request được giải mã. **HTTPS là yêu cầu tối thiểu** trong các môi trường triển khai thực tế. Nếu reverse proxy kết thúc TLS rồi chuyển request nội bộ, cần xác định rõ ai có quyền đọc request, cách TLS được duy trì theo kiến trúc và chính sách forwarding header/host.

### 10.2. Logging, tracing và metrics

| Bề mặt | Basic | Post | Kiểm soát |
|---|---|---|---|
| Gateway/proxy access log | Có thể ghi `Authorization` header | Có thể ghi request body/form field | Tắt/che dữ liệu nhạy cảm ở cả hai bề mặt |
| APM/distributed tracing | Có thể thu thập header | Có thể thu thập payload | Redaction tại nguồn, giới hạn retention/quyền truy cập |
| Exception/error response | Dễ vô tình echo header | Dễ vô tình echo request parameter | Không trả credential/stack trace về client |
| Tool debug và HTTP history | Có thể lưu Basic credential | Có thể lưu form body | Chỉ dùng credential thử, không commit session/capture |
| Monitoring dashboards | Tránh nhãn chứa secret | Tránh nhãn chứa secret | Chỉ ghi mã lỗi, client ID được phép và correlation ID phù hợp |

Để chẩn đoán `invalid_client`, nên ghi **mã lỗi, endpoint, method, request/correlation ID và client ID ở mức phù hợp**. Không ghi giá trị `client_secret`, `Authorization`, mã authorization hoặc token.

### 10.3. Lưu trữ, phân phối và xoay vòng

- Dùng secret có entropy cao, được tạo từ nguồn ngẫu nhiên an toàn; không dùng mật khẩu dễ đoán.
- Lưu plaintext secret tại **secret manager** hoặc cơ chế tương đương với quyền truy cập giới hạn; bên AS nên dùng giá trị hash/phù hợp `PasswordEncoder` để kiểm tra khi áp dụng client-secret authentication.
- Không commit secret vào source, `application.yml` dùng chung, Docker image, CI output hay tài liệu ví dụ.
- Xoay vòng theo quy trình: cấp credential mới, phân phối an toàn, cập nhật registration, theo dõi lỗi, vô hiệu hóa credential cũ theo chính sách.
- Kiểm tra mô hình hỗ trợ xoay vòng: một `RegisteredClient` mặc định lưu một `clientSecret`, **không mặc nhiên hỗ trợ hai secret song song** trong giai đoạn chuyển tiếp. Nếu cần zero-downtime rotation, phải thiết kế cách chuyển tiếp và kiểm thử trước.
- Đối với hệ thống nhiều AS instance hoặc có cache `RegisteredClient`, bảo đảm cập nhật secret/method có hiệu lực nhất quán; tránh node này nhận secret cũ trong khi node khác nhận secret mới.

### 10.4. Chọn phương thức mạnh hơn khi phù hợp

Shared secret có nhược điểm: client và AS đều cần tham gia quy trình quản lý credential, và credential có thể bị copy để giả mạo client. Nếu yêu cầu bảo mật cao hoặc số lượng hệ thống lớn, đánh giá **`private_key_jwt` hoặc mutual TLS** dựa trên hỗ trợ của cả hai phía. Không tự coi việc đổi nơi truyền từ header sang body là nâng cấp mật mã.

## 11. Kiểm thử tích hợp hai phương thức

Kiểm thử thực sự có giá trị phải đi qua **Spring Security filter chain** tại `/oauth2/token`. Test trực tiếp `RegisteredClientRepository` có thể xác nhận metadata, nhưng chưa chứng minh converter/provider và failure handler xử lý đúng.

### 11.1. Ma trận các trường hợp nên có

| Tình huống | Registration | Request | Kết quả mong đợi |
|---|---|---|---|
| Basic hợp lệ | Chỉ Basic | Basic header, secret đúng | Client auth thành công, token có thể được cấp nếu grant/scope hợp lệ |
| Post hợp lệ | Chỉ Post | Form body có `client_id` và `client_secret` | Tương tự, theo policy của client |
| Post gửi tới Basic-only | Chỉ Basic | Credential trong body | Không được cấp token, lỗi client authentication |
| Basic gửi tới Post-only | Chỉ Post | Basic header | Không được cấp token, lỗi client authentication |
| Secret sai | Đúng method | Secret giả | `invalid_client` |
| Client không tồn tại | Không có | Basic/Post | Không được cấp token |
| Thiếu `client_secret` ở Post | Post | Body chỉ có `client_id` | Không xác thực được client |
| Header Basic sai định dạng | Basic | Base64/cặp credential sai | Không được cấp token |
| Ký tự đặc biệt trong ID/secret | Basic/Post hợp lệ | Dùng encoding đúng RFC | Authentication vẫn thành công |
| Cả Basic và Post cùng request | Cả hai hoặc chỉ một | Gửi cả header lẫn credential body | Bị từ chối theo xử lý request; không được coi là cách xác thực kép |
| Secret hết hạn | Đúng method nhưng secret expired | Secret trước đây hợp lệ | Không cấp token |
| Secret đúng nhưng grant sai | Đúng method | `grant_type` không được phép | Token grant bị từ chối, phân biệt `invalid_client` và `unauthorized_client` |
| Secret đúng nhưng scope sai | Đúng method | Scope ngoài registration | Không được cấp scope trái policy |

### 11.2. Ví dụ MockMvc cho client_secret_basic

Giả định môi trường test đã có `batch-reports` đăng ký `CLIENT_SECRET_BASIC`, `client_credentials` và `documents.read`; secret chỉ dùng trong fixture thử nghiệm:

```java
@SpringBootTest
@AutoConfigureMockMvc
class ClientSecretAuthenticationTests {
    @Autowired
    MockMvc mvc;

    @Test
    void basicClientCanObtainToken() throws Exception {
        mvc.perform(post("/oauth2/token")
                .with(httpBasic("batch-reports", "test-basic-secret"))
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("grant_type", "client_credentials")
                .param("scope", "documents.read"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(
                MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$.access_token").isNotEmpty())
            .andExpect(jsonPath("$.token_type").value("Bearer"));
    }
}
```

Ví dụ lược bỏ imports và cấu hình fixture/token signing cần thiết. `httpBasic(...)` giúp tạo Basic authentication request theo Spring Test; với client ID/secret có ký tự đặc biệt, **nên có test bổ sung xác minh đúng quy tắc form-encoding của RFC 6749** tại client request converter đang sử dụng. Test `200` ở đây còn phụ thuộc token endpoint, grant, scope và các bean AS đã được cấu hình hợp lệ.

### 11.3. Ví dụ MockMvc cho client_secret_post

Với registration `legacy-import` chỉ hỗ trợ `CLIENT_SECRET_POST`:

```java
@Test
void postClientCanObtainToken() throws Exception {
    mvc.perform(post("/oauth2/token")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("grant_type", "client_credentials")
            .param("scope", "documents.write")
            .param("client_id", "legacy-import")
            .param("client_secret", "test-post-secret"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.access_token").isNotEmpty());
}
```

Phương thức test giả định được đặt trong cùng class có trường `mvc` và fixture tương ứng. **Không thêm Basic header vào request Post**. Các giá trị `test-...` chỉ để kiểm thử, không phải secret để đưa vào production.

### 11.4. Kiểm tra phương thức sai và credential sai

Ví dụ request Post tới một registration chỉ cho Basic:

```java
@Test
void postMethodIsRejectedForBasicOnlyClient() throws Exception {
    mvc.perform(post("/oauth2/token")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("grant_type", "client_credentials")
            .param("client_id", "batch-reports")
            .param("client_secret", "test-basic-secret"))
        .andExpect(jsonPath("$.error").value("invalid_client"))
        .andExpect(result ->
            assertThat(result.getResponse().getStatus()).isBetween(400, 401));
}
```

Đây là test **từ chối do phương thức**, không phải test grant: secret đúng nhưng không gửi bằng phương thức registration cho phép. Status/challenge chính xác nên được assert theo hợp đồng mà phiên bản Spring Authorization Server đang triển khai, thay vì chỉ dùng khoảng 400–401 trong bộ test production.

Ngoài response, cần kiểm tra trong môi trường test rằng **request/response logging và tracing không chứa credential**, và client dùng mã lỗi để dừng hoặc xử lý lại theo hướng đúng.

## 12. Vận hành và khắc phục sự cố

Khi thấy `invalid_client`, không nên ngay lập tức thay cơ chế xác thực. Hãy chẩn đoán lần lượt:

1. **Đối chiếu registration hai phía:** `client_id`, `ClientAuthenticationMethod`, endpoint, grant và scope.
2. **Kiểm tra nơi đặt credential:** Basic cần header `Authorization`; Post cần `client_id`/`client_secret` trong form body. Tránh gửi trùng.
3. **Kiểm tra encoding:** đặc biệt với `+`, `:`, `%`, `&` và ký tự Unicode trong secret. Basic cần form URL-encode **từng thành phần trước khi Base64**.
4. **Kiểm tra phương thức HTTP và Content-Type:** token endpoint là POST, body `application/x-www-form-urlencoded`.
5. **Kiểm tra thời hạn/rotation secret:** raw secret phía client có đồng bộ với hash/registration phía AS không, đã hết hạn hay bị thay chưa?
6. **Kiểm tra reverse proxy:** proxy có xóa `Authorization` header, đổi path/host, từ chối request body hoặc giới hạn kích thước header không?
7. **Phân biệt lớp lỗi:** `invalid_client` là lỗi client authentication; `unauthorized_client` hoặc `invalid_scope` có thể xảy ra sau khi client được xác thực.
8. **Kiểm tra log an toàn:** dùng correlation ID và mã lỗi; không mở log raw secret hoặc token để debug.

### 12.1. Di trú từ client_secret_post sang client_secret_basic

Đối với client cũ buộc dùng Post, nếu thư viện client nay đã hỗ trợ Basic, có thể lập kế hoạch di trú:

1. Xác nhận hệ thống client có khả năng tạo Basic header **theo đúng RFC 6749** và kết nối HTTPS tới AS.
2. Đăng ký thêm Basic cho client **tạm thời** nếu cần giai đoạn chuyển tiếp, hoặc lên lịch chuyển đổi đồng bộ hai phía.
3. Thử nghiệm đầy đủ các grant và hoạt động production-like bằng secret thử; theo dõi lỗi `invalid_client` mà không lưu credential.
4. Cập nhật client sang Basic, xác nhận traffic qua phương thức mới.
5. Loại bỏ Post khỏi `clientAuthenticationMethods` khi không còn yêu cầu tương thích, cập nhật tài liệu vận hành và test hồi quy.

**Không cần xoay secret chỉ vì thay vị trí truyền**, nhưng có thể kết hợp secret rotation theo chính sách. Nếu cần chuyển đổi không gián đoạn, tính đến cache registration và môi trường nhiều AS instance; không giả định cập nhật repository có hiệu lực cùng lúc ở tất cả các node.

## 13. Những nhận định dễ nhầm

| Nhận định | Điều đúng |
|---|---|
| “Basic mã hóa client secret an toàn vì có Base64” | Base64 là encoding, **phải dùng HTTPS** và bảo vệ header/log |
| “Post an toàn hơn vì secret không nằm trong header” | Body cũng có thể bị ghi log hoặc thu thập bởi proxy/APM |
| “Đưa secret lên query string cũng là client_secret_post” | **Sai**: Post sử dụng **form body**, không phải URL query |
| “Client có thể gửi cả Basic và Post để chắc chắn hơn” | **Sai**: không dùng nhiều phương thức client auth trên cùng request |
| “Có client secret là có quyền gọi mọi API” | Secret chỉ xác thực client; AS xét grant/scope, Resource Server xét access token/quyền |
| “PKCE thay thế client secret ở confidential web app” | PKCE và client auth giải quyết các mối đe dọa khác nhau |
| “SPA nên dùng client_secret_post vì dễ gửi form” | SPA không giữ secret an toàn; sử dụng public client/PKCE |
| “Đúng secret nhưng sai method thì AS vẫn nên cho qua” | AS phải kiểm tra phương thức **được đăng ký** cho client |
| “invalid_client luôn trả HTTP 400” | Với authentication qua Basic header, RFC yêu cầu **401 + WWW-Authenticate** khi client authentication thất bại |
| “Lỗi client_credentials không liên quan tới đăng ký client” | AS vẫn kiểm tra client ID, credential, grant và scope |
| “Chỉ cần đổi từ Basic sang Post để sửa mọi lỗi token” | Phải xác định đúng lỗi encoding, registration, secret, grant hoặc chính sách |

## 14. Checklist áp dụng trước khi triển khai

1. **Loại client đã đúng?** Confidential backend hay public browser/mobile? Không cấp shared secret cho public client.
2. **Phương thức có khớp hai bên?** `client_secret_basic` hay `client_secret_post` được AS đăng ký rõ ràng.
3. **Token request đúng chuẩn?** POST form body cho grant; Basic header hoặc form `client_id`/`client_secret`, không trộn.
4. **Encoding đúng?** Với Basic, từng credential được form URL-encode trước khi ghép và Base64; với Post, body được URL-encode đúng.
5. **TLS và proxy an toàn?** HTTPS, không chuyển secret qua query, không mất header, không ghi raw credential.
6. **Secret được quản lý an toàn?** Giá trị có entropy cao, lưu trong secret manager, hash ở AS, rotation và hết hạn có quy trình.
7. **Grant và scope tối thiểu?** Client credentials chỉ khi phù hợp, scope hạn chế và Resource Server kiểm tra quyền.
8. **Có test cả phương thức đúng và sai?** Basic success, Post success, wrong method, wrong secret, expired secret, bad grant và special characters.
9. **Có giám sát an toàn?** Đếm `invalid_client`, theo dõi sự cố xác thực mà không phơi lộ secret.
10. **Có kế hoạch thay đổi?** Di trú phương thức, cập nhật multi-node/cache và rollback theo yêu cầu vận hành.

## 15. Tổng kết

- **`client_secret_basic`** truyền credential trong `Authorization: Basic ...`; client ID và secret cần được form URL-encode trước khi ghép rồi Base64. RFC 6749 yêu cầu AS hỗ trợ Basic khi cấp client password.
- **`client_secret_post`** truyền `client_id` và `client_secret` trong **HTTP POST form body**. Đây là lựa chọn tương thích tùy chọn và **không được RFC 6749 khuyến nghị** khi có thể dùng Basic.
- Cả hai đều là **shared-secret client authentication**, cần HTTPS, secret được giữ ở backend, PasswordEncoder phù hợp, redaction log và quy trình rotation.
- Trong **Spring Authorization Server**, `RegisteredClient.clientAuthenticationMethods` xác định method được chấp nhận; `OAuth2ClientAuthenticationFilter` và authentication providers kiểm tra client trước khi token grant được xử lý.
- **Client authentication không phải user authentication**, không thay PKCE, và không tự đảm bảo access token có thể truy cập một API cụ thể.

Hiểu chính xác hai phương thức giúp cấu hình Spring Security OAuth2 Client và Spring Authorization Server thống nhất, xác định đúng điểm lỗi `invalid_client`, thực hiện kiểm thử tích hợp có ý nghĩa và vận hành credential an toàn.

## 16. Tài liệu tham khảo

- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): **$2.3.1 Client Password** (Basic và form body), $3.2.1 (client authentication), $4.4 (client credentials), $5.2 (token error).
- [RFC 7617 — The 'Basic' HTTP Authentication Scheme](https://www.rfc-editor.org/rfc/rfc7617): cấu trúc HTTP Basic; lưu ý quy tắc form-encoding bổ sung từ RFC 6749 với OAuth client secret.
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700): khuyến nghị bảo mật OAuth 2.0 hiện đại.
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): PKCE và quan hệ với việc bảo vệ Authorization Code flow.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): token endpoint authentication và metadata liên quan tới OIDC client.
- [Spring Authorization Server Reference](https://docs.spring.io/spring-authorization-server/reference/): `RegisteredClient`, client authentication, các endpoint và cấu hình bảo mật.
- [Spring Security OAuth2 Client Reference](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): `ClientRegistration`, token requests và cấu hình client authentication.
