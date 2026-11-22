# 3.3. ID Token, Access Token và UserInfo: mục đích sử dụng

## 1. Bài toán: đăng nhập thành công có đồng nghĩa được gọi API?

Giả sử ứng dụng Spring Boot tích hợp OpenID Connect (OIDC) để nhân viên đăng nhập bằng tài khoản của một Identity Provider (IdP). Sau khi đăng nhập, ứng dụng cần biết **ai đang dùng hệ thống**, hiển thị tên và ảnh đại diện, rồi gọi một API quản lý công việc.

Ba nhu cầu đó sử dụng những thành phần khác nhau:

1. **Xác định người đã đăng nhập:** OIDC client xác minh **ID Token** do nhà cung cấp danh tính cấp.
2. **Lấy thêm thuộc tính hồ sơ:** OIDC client có thể gọi **UserInfo endpoint** với một access token được IdP chấp nhận.
3. **Được phép gọi API nghiệp vụ:** OAuth 2.0 client gửi **Access Token** thích hợp đến resource server; API tự quyết định có chấp nhận token và quyền được cấp hay không.

OIDC là một lớp xác thực danh tính xây trên OAuth 2.0. Vì vậy một lượt đăng nhập OIDC thường tạo ra cả ID Token và Access Token, nhưng chúng **không thể thay thế nhau**.

| Thành phần | Trả lời câu hỏi | Đối tượng sử dụng | Không dùng để |
| --- | --- | --- | --- |
| **ID Token** | “Người dùng nào vừa được IdP xác thực cho client này?” | OIDC client | Truy cập API nghiệp vụ thay access token |
| **Access Token** | “Client có quyền gọi tài nguyên nào trong phạm vi được cấp?” | Resource server tương ứng; OIDC UserInfo endpoint cũng là một tài nguyên được bảo vệ | Tự suy diễn rằng người dùng đã đăng nhập hoặc dùng như ID Token |
| **UserInfo** | “IdP cung cấp thêm thuộc tính nào về người dùng đã được xác thực?” | OIDC client, sau khi gọi UserInfo endpoint | Thay thế bước xác minh ID Token hoặc tự quyết định quyền API |

**Điểm mấu chốt:** ID Token cung cấp bằng chứng xác thực cho client; Access Token cho phép truy cập tài nguyên; UserInfo cung cấp các claim về hồ sơ, được lấy bằng Access Token.

## 2. ID Token, Access Token và UserInfo xuất hiện ở bước nào?

Với Authorization Code flow, browser đi qua authorization endpoint, còn backend Spring Boot đổi authorization code lấy token tại token endpoint. Sau đó client có thể gọi UserInfo:

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Browser / Người dùng
    participant C as Spring Boot OIDC Client
    participant I as OIDC Provider
    participant A as Resource Server nghiệp vụ
    U->>C: Truy cập trang yêu cầu đăng nhập
    C-->>U: Redirect đến authorization endpoint
    U->>I: Đăng nhập và chấp thuận quyền nếu cần
    I-->>U: Redirect về client với authorization code
    U->>C: Callback chứa code và state
    C->>I: POST token endpoint (code + PKCE)
    I-->>C: id_token + access_token (+ refresh_token nếu có)
    Note over C: Xác minh ID Token, tạo principal
    opt Có UserInfo endpoint và quyền phù hợp
        C->>I: GET UserInfo, Authorization: Bearer access_token
        I-->>C: JSON/JWT UserInfo chứa sub và các claim được cấp
        Note over C: So khớp UserInfo.sub với ID Token.sub
    end
    C-->>U: Tạo session đăng nhập
    opt Access token dành cho API nghiệp vụ
        C->>A: Gửi access_token phù hợp audience/scope
        A-->>C: Dữ liệu hoặc 401/403
    end
~~~

Token endpoint có thể trả về:

~~~json
{
  "access_token": "ACCESS_TOKEN_EXAMPLE",
  "token_type": "Bearer",
  "expires_in": 300,
  "scope": "openid profile email",
  "id_token": "HEADER.PAYLOAD.SIGNATURE",
  "refresh_token": "OPTIONAL_REFRESH_TOKEN"
}
~~~

Đây là ví dụ minh họa, không phải token thật. Trong Authorization Code flow của OIDC, **ID Token và Access Token** là hai trường riêng trong token response. **UserInfo không phải một token thứ ba** trong response này: đó là một endpoint và dữ liệu phản hồi khi client gọi endpoint ấy. Refresh Token là thành phần tùy chọn, dùng xin token mới khi được phép.

Không phải access token dùng cho UserInfo cũng được các API nghiệp vụ khác chấp nhận. Token phải có audience, scope và ràng buộc tương ứng với resource server đích; hệ thống có thể cần một token riêng cho API.

## 3. ID Token: bằng chứng xác thực dành cho OIDC client

### 3.1. ID Token là gì?

**ID Token** là JSON Web Token (JWT) do OpenID Provider phát hành, chứa các **claim** về sự kiện xác thực người dùng. ID Token có thể được ký và, theo cấu hình, được mã hóa. Trong luồng thông thường, Spring Security kiểm tra ID Token rồi tạo principal để ứng dụng sử dụng.

Một payload đã giải mã có thể trông như sau:

~~~json
{
  "iss": "https://id.example.com/realms/company",
  "sub": "c47a12f8-opaque-subject",
  "aud": "spring-web-client",
  "exp": 1925000300,
  "iat": 1925000000,
  "auth_time": 1924999900,
  "nonce": "nonce-from-authorization-request",
  "name": "Nguyen An",
  "email": "an@example.com",
  "email_verified": true
}
~~~

Các mốc thời gian trong ví dụ chỉ minh họa; thời gian thật là Unix time tính theo giây. Payload được giải mã **chưa đồng nghĩa JWT đáng tin**: client phải xác minh chữ ký, issuer, audience, hiệu lực và những ràng buộc liên quan trước khi dùng claim.

### 3.2. Những claim cần hiểu

| Claim | Vai trò | Lưu ý triển khai |
| --- | --- | --- |
| `iss` (issuer) | Định danh provider phát hành | Phải khớp issuer được cấu hình/tin cậy, so sánh chính xác |
| `sub` (subject) | Định danh người dùng do issuer cấp | Là định danh ổn định theo phạm vi issuer/client policy; không giả định trùng giữa các issuer |
| `aud` (audience) | Client được ID Token phát hành cho | Phải chứa `client_id` của ứng dụng; không mặc định là URL API |
| `exp` (expiration) | Thời điểm token hết hiệu lực | Phải kiểm tra token còn hiệu lực; xử lý sai lệch đồng hồ hợp lý |
| `iat` (issued at) | Thời điểm phát hành | Giúp kiểm tra ngữ cảnh và chính sách độ mới |
| `nonce` | Gắn token với yêu cầu OIDC đã gửi | Khi request gửi nonce thì cần xác minh nonce nhận về |
| `auth_time` | Thời điểm người dùng thực sự xác thực | Cần chú ý khi yêu cầu xác thực lại hoặc `max_age` |
| `azp` (authorized party) | Client được chỉ định trong trường hợp cần thiết | Đặc biệt liên quan đến trường hợp ID Token có nhiều audience |
| `acr`, `amr` | Ngữ cảnh / phương thức xác thực | Chỉ dùng khi provider và ứng dụng có hợp đồng về ý nghĩa |
| `name`, `picture`, `email` | Claim hồ sơ, có thể xuất hiện | Không bắt buộc phải nằm trong ID Token |

Các claim `iss`, `sub`, `aud`, `exp` và `iat` là nền tảng của ID Token theo OIDC Core. Claim hồ sơ như `name`, `email` hoặc `picture` phụ thuộc provider, scope và chính sách claim; **không mặc định luôn có**, kể cả khi client yêu cầu `profile` hoặc `email`.

### 3.3. Xác minh ID Token đúng mục đích

Trước khi chấp nhận ID Token, OIDC client phải thực hiện các bước kiểm tra phù hợp với luồng và provider, gồm:

1. **Tin cậy issuer:** `iss` đúng issuer đã đăng ký. Không lấy issuer bất kỳ từ token rồi tự động tin.
2. **Chữ ký / mã hóa:** xác minh chữ ký với khóa và thuật toán được phép của provider, lấy khóa đúng nguồn JWKS nếu dùng JWT ký; giải mã và xác thực đúng quy tắc nếu dùng JWT mã hóa.
3. **Audience:** `aud` phải chứa `client_id` của ứng dụng; xử lý `azp` theo yêu cầu OIDC khi thích hợp.
4. **Thời gian:** `exp` chưa hết, `iat` hợp lý; kiểm tra `auth_time` nếu ứng dụng yêu cầu xác thực gần đây.
5. **Ràng buộc giao dịch:** kiểm tra `nonce` khi được gửi, cùng những kiểm tra bắt buộc khác theo response type/flow.
6. **Không tin claim trước khi xác minh:** không quyết định tài khoản, vai trò hoặc tạo session dựa trên JWT chỉ mới Base64URL decode.

Spring Security OIDC login quản lý phần lớn những bước này khi cấu hình đúng `issuer-uri` và client registration. Ứng dụng không nên tự parse JWT không xác minh rồi lưu `sub` vào session.

### 3.4. Subject mới là khóa nhận diện, không phải email

Một người có thể đổi email, đổi tên hoặc có hai tài khoản khác nhau nhưng cùng địa chỉ email theo thời gian. Vì thế, khi ánh xạ tài khoản OIDC sang user nội bộ, nên dùng **cặp (`iss`, `sub`)** làm khóa nhận diện nhà cung cấp.

Ví dụ:

~~~text
issuer                                subject                 internal_user_id
https://id.example.com/realms/a      8a72bf...               103
https://login.partner.example.org    8a72bf...               855
~~~

Hai subject có chuỗi giống nhau nhưng từ issuer khác nhau **không được tự gộp**. Provider còn có thể dùng *pairwise subject identifier*, nghĩa là cùng một người dùng nhận `sub` khác nhau cho các client/sector khác nhau. Đừng mặc định `sub` là email, số nhân viên hoặc ID toàn cục dùng chung mọi hệ thống.

### 3.5. ID Token không phải giấy phép gọi API

Một API có thể nhận được ID Token dưới dạng chuỗi JWT hợp lệ về chữ ký, nhưng `aud` của ID Token thường là **OIDC client ID**, không phải API. API không được chấp nhận ID Token như Access Token chỉ vì nó là JWT.

~~~http
GET /orders HTTP/1.1
Host: api.example.com
Authorization: Bearer ID_TOKEN_VALUE
~~~

Request trên **sai mục đích** với API được thiết kế theo OAuth 2.0 Access Token. Bảo vệ API đòi hỏi token và kiểm tra authorization riêng.

## 4. Access Token: credential để gọi tài nguyên được bảo vệ

### 4.1. Access Token dùng cho ai?

Access Token được cấp trong một ngữ cảnh OAuth 2.0, có thể đại diện cho quyền của người dùng thông qua client hoặc quyền của chính client, tùy grant. Client đưa nó cho **resource server** được nhắm đến, thường dưới dạng Bearer token:

~~~http
GET /orders HTTP/1.1
Host: api.example.com
Authorization: Bearer ACCESS_TOKEN_FOR_ORDERS_API
~~~

Resource server kiểm tra liệu token có hợp lệ và đủ quyền hay không. Các điều kiện thường liên quan đến:

| Yếu tố | Tại sao quan trọng? |
| --- | --- |
| Issuer | API chỉ tin authorization server đã được cấu hình |
| Audience / resource | Token phải dành cho API đang nhận nó |
| Scope / authority | Token có quyền thực hiện thao tác yêu cầu, chẳng hạn `orders.read` |
| Expiration / revocation | Token có thể hết hạn hoặc bị thu hồi |
| Subject / client / token binding | API có thể cần biết yêu cầu thuộc người dùng, ứng dụng nào hoặc ràng buộc người gửi |

Access Token **không bắt buộc là JWT**. Nó có thể là chuỗi opaque mà client không hiểu được; resource server có thể xác minh bằng introspection hoặc phương thức được provider hỗ trợ. Cũng không nên giả định claim của Access Token JWT có cùng cấu trúc hoặc ý nghĩa với ID Token.

### 4.2. Vì sao không dùng Access Token thay ID Token?

Access Token có audience và tiêu chí kiểm tra phục vụ **resource server**, trong khi ID Token được cấp cho **OIDC client**. OAuth 2.0 không bảo đảm Access Token chứa tên, email hay bằng chứng hoàn tất xác thực người dùng theo các quy tắc của OIDC. Một token từ Client Credentials thậm chí có thể không đại diện cho một người dùng nào.

Do đó cách làm sau không an toàn:

~~~text
1. Nhận access_token.
2. Chỉ Base64URL-decode payload nếu thấy giống JWT.
3. Lấy "email" / "sub" rồi coi là người vừa đăng nhập.
~~~

Quy trình đăng nhập OIDC phải dựa trên ID Token đã được kiểm tra (và trạng thái OAuth login tương ứng). Khi cần thêm thuộc tính người dùng, dùng UserInfo đúng quy tắc hoặc các claim đáng tin do provider cung cấp qua ID Token.

### 4.3. Scope không đồng nghĩa vai trò nghiệp vụ

Ví dụ client xin:

~~~text
scope=openid profile email orders.read
~~~

`openid` yêu cầu OIDC; `profile` và `email` yêu cầu tập claim thông thường; `orders.read` là scope do hệ thống API định nghĩa. Các scope này không làm thay đổi bản chất từng token. Nếu tài nguyên không chấp nhận scope `orders.read` hoặc access token không có audience đúng, API có thể từ chối dù đăng nhập OIDC thành công.

Tương tự, scope `email` không tự chứng minh người dùng có quyền quản trị hệ thống. Quyền nghiệp vụ có thể cần chính sách RBAC/ABAC, kiểm tra dữ liệu thuộc sở hữu hoặc dữ liệu nội bộ khác.

## 5. UserInfo: lấy thông tin hồ sơ qua endpoint được bảo vệ

### 5.1. UserInfo endpoint là gì?

**UserInfo** là endpoint chuẩn của OpenID Connect để client nhận thêm claim về người dùng cuối đã được xác thực. Endpoint này do OIDC provider cung cấp; client gửi **Access Token** được provider chấp nhận, thông thường qua HTTPS:

~~~bash
curl --request GET "https://id.example.com/realms/company/protocol/openid-connect/userinfo" \
  --header "Authorization: Bearer ACCESS_TOKEN_FOR_USERINFO"
~~~

Địa chỉ trên chỉ là ví dụ minh họa cho một provider; ứng dụng thật nên lấy `userinfo_endpoint` từ OIDC discovery metadata (`.well-known/openid-configuration`) hoặc cấu hình provider tin cậy, không tự suy đoán endpoint.

Phản hồi JSON có thể là:

~~~json
{
  "sub": "c47a12f8-opaque-subject",
  "name": "Nguyen An",
  "given_name": "An",
  "family_name": "Nguyen",
  "preferred_username": "an.nguyen",
  "picture": "https://cdn.example.com/avatar/an.png",
  "email": "an@example.com",
  "email_verified": true,
  "locale": "vi-VN"
}
~~~

Không có bảo đảm mọi trường minh họa đều được trả. Theo cấu hình provider/client, UserInfo response có thể là JSON hoặc một JWT có chữ ký/mã hóa; nếu dùng JWT cần xử lý và xác minh theo các yêu cầu tương ứng.

**UserInfo không phải ID Token và cũng không phải “token mới”.** Đây là phản hồi chứa claim từ một resource được bảo vệ bằng OAuth Access Token.

### 5.2. Bắt buộc so khớp UserInfo.sub với ID Token.sub

Đây là ràng buộc bảo mật trọng tâm của OIDC:

~~~text
ID Token sau khi xác minh:
    iss = https://id.example.com/realms/company
    sub = c47a12f8-opaque-subject

UserInfo response:
    sub = c47a12f8-opaque-subject

=> Có thể sử dụng các claim UserInfo nếu các kiểm tra khác cũng đạt.
~~~

Nếu `sub` của UserInfo khác `sub` trong ID Token thì **phải từ chối sử dụng UserInfo response**, vì các claim có thể thuộc tài khoản khác. UserInfo response phải bao gồm `sub`; không được dùng tên, email hoặc hình đại diện để “đoán” rằng hai response thuộc một người.

Spring Security thường xử lý kiểm tra này trong thành phần OIDC user service khi nó tải UserInfo. Nếu ứng dụng chủ động gọi endpoint bằng HTTP client riêng, nó phải tự duy trì ràng buộc ấy.

### 5.3. Claim trong ID Token và UserInfo khác nhau thế nào?

OIDC cho phép cung cấp một số claim hồ sơ trong ID Token, UserInfo hoặc cả hai tùy nhà cung cấp. Không có quy tắc “email luôn nằm trong ID Token” hay “email luôn nằm trong UserInfo”. Cần dùng schema và chính sách đã thống nhất với provider.

| Phân loại claim | Ví dụ | Ghi chú |
| --- | --- | --- |
| Danh tính cốt lõi | `sub` | Bắt buộc trong ID Token và UserInfo response |
| Hồ sơ `profile` | `name`, `given_name`, `family_name`, `picture`, `locale`, `zoneinfo` | Chỉ trả các claim thực sự được cung cấp/cho phép |
| Email `email` | `email`, `email_verified` | `email_verified=true` thể hiện xác nhận theo chính sách provider, không tự cấp vai trò nghiệp vụ |
| Điện thoại `phone` | `phone_number`, `phone_number_verified` | Cần scope/policy tương ứng |
| Địa chỉ `address` | `address` | Là đối tượng chứa các thuộc tính địa chỉ theo OIDC |

Tham số `scope` là yêu cầu tập quyền/claim, **không phải cam kết tất cả thuộc tính sẽ tồn tại**. Có thể yêu cầu claim cụ thể với tham số `claims` theo OIDC khi provider hỗ trợ; vẫn cần xử lý trường hợp claim vắng mặt hoặc không được công bố.

### 5.4. Khi nào gọi UserInfo, khi nào dùng claim từ ID Token?

- **Chỉ cần định danh đăng nhập:** ID Token đã xác minh với cặp `iss` + `sub` thường đủ để tạo hoặc nhận diện user nội bộ.
- **Cần tên, avatar, ngôn ngữ hoặc email:** dùng claim hiện có từ principal OIDC; nếu thiếu và có UserInfo endpoint/quyền, có thể tải UserInfo.
- **Cần dữ liệu hồ sơ được làm mới:** gọi lại UserInfo khi phù hợp với chính sách, lưu ý nó không đảm bảo dữ liệu luôn cập nhật tức thời; không mặc nhiên coi claim của session là dữ liệu thời gian thực.
- **Cần quyền gọi API công việc:** dùng Access Token được cấp cho API ấy; UserInfo không thay cơ chế phân quyền của API.

Tránh gọi UserInfo ở mọi HTTP request nếu không có nhu cầu: điều này tăng độ trễ, phụ thuộc mạng và tải cho IdP. Quyết định cache/refresh dữ liệu hồ sơ phải cân bằng tính mới, thời gian sống và quyền riêng tư.

## 6. Bảng so sánh thực tế

| Tiêu chí | ID Token | Access Token | UserInfo response |
| --- | --- | --- | --- |
| Mục đích chính | Xác thực người dùng với OIDC client | Ủy quyền gọi resource server | Lấy thêm claim người dùng |
| Nguồn nhận | OIDC token endpoint (Authorization Code flow) | OAuth token endpoint | OIDC UserInfo endpoint |
| Định dạng | JWT, có thể ký/mã hóa | Opaque/JWT/định dạng tùy authorization server | Thường JSON; có thể là JWT theo cấu hình |
| Audience / đối tượng tin cậy | OIDC client (`client_id`) | Resource server đích | OIDC client nhận phản hồi từ endpoint tin cậy |
| Có chứa `sub`? | Bắt buộc | Tùy loại token và grant | Bắt buộc |
| Có nhất thiết chứa `email`? | Không | Không | Không |
| Gửi trong `Authorization: Bearer` đến API nghiệp vụ? | Không | Có, nếu token hợp lệ cho API đó | Không |
| Dùng để xác nhận login OIDC? | Có, sau khi client xác minh | Không, tự nó không đủ | Chỉ bổ sung sau khi xác minh ID Token và so khớp `sub` |
| Khi hết hiệu lực | Phụ thuộc xác thực lại/chính sách session | Cần token mới/refresh nếu được cấp | Dữ liệu có thể cần tải lại theo nhu cầu |

Một cách nhớ ngắn gọn:

~~~text
ID Token  -> "Ai đã xác thực cho client này?"
Access Token -> "Được truy cập resource nào?"
UserInfo -> "IdP chia sẻ thêm claim nào về người ấy?"
~~~

## 7. Tích hợp Spring Security OAuth 2.0 OIDC Client

### 7.1. Cấu hình OIDC client trong Spring Boot

Ví dụ ứng dụng web Servlet sử dụng Spring Security OAuth 2.0 Client và một OIDC provider hỗ trợ discovery:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          company:
            provider: company-oidc
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          company-oidc:
            issuer-uri: https://id.example.com/realms/company
~~~

Thay issuer, client ID và secret bằng dữ liệu provider thật; giữ secret trong môi trường bảo mật. Redirect URI phải khớp cấu hình đăng ký tại IdP. Scope `openid` là dấu hiệu yêu cầu OIDC; nếu chỉ có OAuth scopes mà không có `openid` thì không nên giả định nhận được ID Token.

Thiết lập `SecurityFilterChain`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/health").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Với cấu hình này, đường dẫn `/oauth2/authorization/company` có thể bắt đầu luồng login. Spring Security thực hiện Authorization Code flow, xác minh kết quả OIDC và đưa người dùng đã xác thực vào SecurityContext. `oauth2Client()` hỗ trợ sử dụng authorized client khi gọi tài nguyên.

### 7.2. Lấy ID Token và thông tin UserInfo từ OidcUser

Trong controller Servlet, có thể nhận principal bằng `@AuthenticationPrincipal OidcUser`:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MyProfileController {

    @GetMapping("/me")
    public Map<String, Object> me(@AuthenticationPrincipal OidcUser user) {
        var result = new LinkedHashMap<String, Object>();
        result.put("issuer", user.getIdToken().getIssuer().toString());
        result.put("subject", user.getSubject());
        result.put("displayName", user.getFullName());
        result.put("email", user.getEmail());
        result.put("userInfoAvailable", user.getUserInfo() != null);
        return result;
    }
}
~~~

**Giải thích:**

- `user.getIdToken()` truy cập ID Token đã đi qua xác minh OIDC của Spring Security; `getSubject()` phản ánh subject của principal. Ứng dụng dùng cặp issuer–subject để ánh xạ tài khoản.
- `user.getUserInfo()` trả về `OidcUserInfo` **nếu đã có** UserInfo được tải trong quá trình login. Giá trị có thể là `null`; không được giả định mọi IdP luôn cung cấp UserInfo.
- `user.getFullName()` / `getEmail()` là claim hợp nhất mà principal công bố; có thể vắng mặt, không phải dữ liệu bắt buộc.
- Ví dụ endpoint chỉ trả metadata cần dùng. **Không trả `getIdToken().getTokenValue()`, access token hoặc refresh token ra response cho browser** chỉ để hiển thị trang.

Spring Security sử dụng `OidcUserService` cho phần tải người dùng OIDC trong cấu hình đăng nhập thông thường. Nó có thể gọi UserInfo endpoint khi metadata, access token/scope và các điều kiện cần thiết cho phép; hành vi phụ thuộc phiên bản, provider và custom configuration. Nếu nghiệp vụ yêu cầu UserInfo trong một trường hợp cụ thể, hãy cấu hình/tùy biến rõ `OidcUserService` và kiểm tra claim có tồn tại.

Khi tổ chức nhiều IdP hoặc có profile mapping phức tạp, ứng dụng có thể dùng OIDC user service riêng để ánh xạ claim sang dữ liệu nội bộ, nhưng vẫn cần giữ kiểm tra xác minh ID Token và `UserInfo.sub == ID Token.sub`.

### 7.3. Lấy Access Token để gọi API nghiệp vụ

`OidcUser` biểu diễn người đã đăng nhập; token dùng gọi API được lưu trong **`OAuth2AuthorizedClient`** tương ứng với client registration và principal.

Ví dụ endpoint backend proxy một API được phép nhận token của registration `company`:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.client.RestClient;

@RestController
public class OrdersController {
    private final RestClient restClient = RestClient.create();

    @GetMapping("/my-orders")
    public String orders(
            @RegisteredOAuth2AuthorizedClient("company")
            OAuth2AuthorizedClient authorizedClient) {

        String token = authorizedClient.getAccessToken().getTokenValue();
        return restClient.get()
            .uri("https://api.example.com/orders")
            .headers(headers -> headers.setBearerAuth(token))
            .retrieve()
            .body(String.class);
    }
}
~~~

Đoạn mã minh họa chỉ đúng khi Access Token của registration `company` **được cấp cho** `https://api.example.com` và có scope thích hợp, ví dụ `orders.read`. **Đăng nhập OIDC với `openid profile email` không tự bảo đảm token dùng được cho API nghiệp vụ.** Phải cấu hình thêm scope/resource/audience theo hợp đồng của authorization server, hoặc sử dụng cơ chế cấp token phù hợp. Trong sản phẩm thực tế cần xử lý 401/403, timeout, lỗi kết nối, quyền nội bộ và việc refresh token qua authorized client manager.

### 7.4. Hiểu việc Spring Security tải UserInfo

Luồng OIDC của Spring Security bao gồm các phần:

~~~text
ClientRegistration (issuer, client_id, scopes, endpoints)
          |
          v
OAuth2 Login / Authorization Code
          |
          +--> ID Token --> OIDC token validation --> OidcUser
          |
          +--> Access Token --> OAuth2AuthorizedClient
                                 |
                                 +--> UserInfo endpoint (nếu áp dụng)
                                 |       |
                                 |       +--> OidcUserInfo; kiểm tra sub
                                 |
                                 +--> Resource server được ủy quyền
~~~

Các API chính:

| Kiểu | Trách nhiệm |
| --- | --- |
| `OidcIdToken` | Biểu diễn claim và giá trị ID Token |
| `OidcUserInfo` | Biểu diễn claim nhận từ UserInfo endpoint |
| `OidcUser` | Principal OIDC; cung cấp ID Token, UserInfo nếu có và claim người dùng |
| `OidcUserService` | Lấy/ánh xạ user OIDC, có thể lấy UserInfo theo cấu hình |
| `OAuth2AuthorizedClient` | Giữ Access Token/Refresh Token của một registration được ủy quyền |
| `OAuth2AuthorizedClientManager` | Điều phối cấp token hoặc refresh token theo provider cấu hình |

Phân biệt rõ việc **đọc claim người dùng** thông qua `OidcUser` với việc **lấy Access Token** thông qua `OAuth2AuthorizedClient`. Đây là ranh giới quan trọng khi viết controller, HTTP client hoặc tích hợp backend.

## 8. UserInfo có thể thiếu, lỗi hoặc trả claim không mong đợi

Một OIDC client không nên thiết kế dựa trên giả định “UserInfo chắc chắn trả tất cả claim”.

| Hiện tượng | Cách giải thích / xử lý |
| --- | --- |
| Provider không công bố `userinfo_endpoint` | Không tự dựng URL; dùng claim sẵn trong ID Token hoặc tích hợp khác được hỗ trợ |
| UserInfo trả `401 Unauthorized` | Access Token hết hạn, sai loại/token/audience hoặc không được endpoint chấp nhận; xin token hợp lệ theo quy trình |
| UserInfo trả `403 Forbidden` | Token không có phạm vi hoặc quyền cần thiết; kiểm tra scope và policy |
| Response không có `email` | Trường tùy chọn; vẫn có thể đăng nhập dựa trên `iss` + `sub` |
| Response có `email_verified=false` | Email chưa được xác nhận theo provider; không coi email đã xác minh |
| `sub` trong UserInfo khác ID Token | Từ chối sử dụng toàn bộ UserInfo response, kiểm tra nhầm người/token/provider |
| Claim `name` trong ID Token khác UserInfo | Chính sách claim và độ mới dữ liệu có thể khác; chọn nguồn hiển thị theo hợp đồng provider |
| Access Token gọi UserInfo được nhưng API nghiệp vụ từ chối | Hai resource server yêu cầu audience và scopes khác nhau |
| Access Token mới nhưng session vẫn cũ | Access Token lifecycle khác app session; xem lại chính sách cập nhật principal/claim |

Đối với UserInfo, API trả các claim liên quan người dùng đã xác thực, nhưng ứng dụng vẫn phải quyết định **có cần lưu, có cần đồng bộ và giữ trong bao lâu**. Dữ liệu hồ sơ có thể thay đổi; thông tin danh tính lâu dài nên dùng issuer–subject, không dùng tên hiển thị hay email làm khóa duy nhất.

## 9. Các lỗi thiết kế thường gặp

### Sai lầm 1: “ID Token là JWT, API phải chấp nhận được”

Sai vì API cần Access Token dành đúng API. Signature hợp lệ mới là một điều kiện; **audience** và **token purpose** vẫn phải đúng. Không biến ID Token thành credential cho API.

### Sai lầm 2: “Access Token có sub nên đủ để xác thực đăng nhập”

OAuth 2.0 không bắt buộc Access Token có `sub` hoặc thể hiện các bảo đảm OIDC cần cho login. Có cả token đại diện client chứ không có người dùng. OIDC login dựa trên ID Token đã kiểm tra.

### Sai lầm 3: “Có scope email thì ID Token/UserInfo luôn chứa email”

Không. Quyền yêu cầu không có nghĩa claim sẽ được tiết lộ; dữ liệu có thể thiếu hoặc không được provider công bố. Thiết kế model có trường tùy chọn và luồng bổ sung hồ sơ khi cần.

### Sai lầm 4: “UserInfo trả tên/email đúng nên không cần kiểm tra sub”

Không được bỏ qua **so khớp `sub`**. Email có thể trùng, đổi hoặc chưa xác minh. OIDC yêu cầu UserInfo subject khớp ID Token subject.

### Sai lầm 5: “UserInfo luôn mới hơn và là nguồn sự thật cho mọi quyền”

UserInfo chủ yếu chứa claim người dùng. Tính mới phụ thuộc hệ thống IdP; quyền thao tác của API vẫn phải do resource server và policy phù hợp quyết định.

### Sai lầm 6: “Đăng nhập được thì mọi API chấp nhận Access Token”

Access Token có thể chỉ sử dụng được cho UserInfo hoặc API được chỉ định. Cần audience, scope và cơ chế cấp token đúng cho từng resource server. Không gửi token sang hệ thống không nằm trong đối tượng nhận.

### Sai lầm 7: Log token để debug

ID Token, Access Token và Refresh Token đều có thể chứa hoặc cho phép truy cập thông tin nhạy cảm. Không ghi giá trị token, callback URL có code hoặc secret vào log, URL, analytics và exception. Chỉ ghi mã lỗi, request ID và metadata không nhạy cảm.

## 10. Ví dụ xuyên suốt: xây trang “Tài khoản của tôi”

Yêu cầu: người dùng đăng nhập tại IdP; ứng dụng hiển thị tên/email/ảnh, đồng thời cho phép đọc danh sách nhiệm vụ từ một API.

**Giai đoạn đăng nhập:**

1. Spring Security bắt đầu Authorization Code + PKCE khi người dùng truy cập trang yêu cầu xác thực.
2. Token endpoint trả ID Token và Access Token, có thể thêm Refresh Token.
3. OIDC client xác minh ID Token, lấy `iss` và `sub` để ánh xạ người dùng nội bộ.
4. Nếu UserInfo được hỗ trợ và cần thêm claim, client gọi UserInfo bằng Access Token được IdP chấp nhận; phải xác minh UserInfo `sub` khớp ID Token.
5. Ứng dụng lưu session nội bộ phù hợp và chỉ đưa các trường hồ sơ cần hiển thị cho frontend.

**Giai đoạn gọi API nhiệm vụ:**

1. Backend lấy authorized client tương ứng với người dùng.
2. Kiểm tra Access Token phù hợp audience/scope của Task API; nếu hết hạn, dùng cơ chế refresh/cấp token mới nếu được phép.
3. Gọi Task API với `Authorization: Bearer <access_token>`.
4. Task API xác minh token và thực thi quyền trên chính đối tượng nhiệm vụ; ứng dụng xử lý 401/403 phù hợp.

**Giai đoạn cập nhật hồ sơ:** khi cần cập nhật tên/ảnh, ứng dụng có thể tải lại UserInfo với token hợp lệ, đối chiếu `sub`, rồi thay dữ liệu hiển thị. Không thay khóa user nội bộ dựa trên email hoặc tên vừa nhận.

~~~mermaid
flowchart TD
    A["OIDC Login thành công"] --> B["ID Token đã xác minh"]
    B --> C["Khóa user: issuer + subject"]
    B --> D{"Cần thêm claim hồ sơ?"}
    D -->|Có| E["Access Token -> UserInfo endpoint"]
    E --> F{"UserInfo.sub = ID Token.sub?"}
    F -->|Có| G["Dùng claim được phép: name, email, picture..."]
    F -->|Không| H["Từ chối UserInfo response"]
    D -->|Không| I["Dùng claim có sẵn"]
    C --> J["Session/principal nội bộ"]
    G --> J
    I --> J
    J --> K{"Cần gọi API?"}
    K -->|Có| L["Access Token đúng audience/scope -> API"]
    K -->|Không| M["Hiển thị trang"]
~~~

## 11. Tự kiểm tra hiểu đúng mục đích

**Tình huống A:** nhận được ID Token hợp lệ có `sub=123` và `email=a@example.com`, API đơn hàng trả 401 khi dùng ID Token làm Bearer. Đây là hành vi có thể đúng: API mong Access Token dành cho nó, không phải ID Token.

**Tình huống B:** UserInfo trả `sub=456` còn ID Token có `sub=123`. Phải bỏ UserInfo response, kể cả khi hai response ghi cùng tên hoặc email.

**Tình huống C:** ứng dụng chỉ yêu cầu `openid` và muốn ảnh đại diện nhưng không có `picture`. Hãy kiểm tra scope `profile`, cấu hình claim và hỗ trợ UserInfo của provider; ngay cả khi xin `profile`, claim `picture` vẫn có thể vắng mặt.

**Tình huống D:** Access Token của IdP gọi UserInfo thành công nhưng gọi API nhiệm vụ thất bại. Kiểm tra audience, resource indicator, scope và policy API thay vì kết luận OIDC login hỏng.

**Tình huống E:** hệ thống có hai OIDC provider cùng phát `sub="123"`. Phải phân biệt bằng cặp (`iss`, `sub`), không gộp tài khoản tự động dựa trên `sub` đơn lẻ.

## 12. Ghi nhớ khi thiết kế Spring Security OIDC Client

Khi viết logic đăng nhập và gọi API, cần đặt đúng câu hỏi với đúng đối tượng:

~~~text
Xác minh đăng nhập:
  ID Token -> validate issuer, audience, signature, expiry, nonce...
           -> OidcUser / danh tính (iss, sub)

Đọc thêm hồ sơ:
  Access Token cho UserInfo -> UserInfo endpoint
                            -> nhận claims, bắt buộc so khớp sub

Gọi API nghiệp vụ:
  Access Token dành cho API -> Resource Server
                            -> kiểm tra audience, scope, thời hạn, policy
~~~

**ID Token xác thực người dùng cho OIDC client; Access Token ủy quyền truy cập resource server; UserInfo bổ sung claim hồ sơ trong ngữ cảnh của ID Token đã xác minh.** Spring Security giúp quản lý nhiều bước của giao thức, nhưng ứng dụng vẫn cần xác định đúng token, đúng nơi nhận, đúng khóa danh tính và đúng quy tắc phân quyền.
