# 1.1. Vai trò OAuth 2.0 Client và OpenID Connect Relying Party

## Mục tiêu bài học

Sau bài học, bạn có thể:

- Phân biệt **OAuth 2.0 Client** (ứng dụng xin quyền truy cập tài nguyên) và **OpenID Connect Relying Party — RP** (ứng dụng dựa vào kết quả xác thực danh tính).
- Xác định vai trò của người dùng, Authorization Server, OpenID Provider và Resource Server trong một hệ thống đăng nhập và gọi API.
- Giải thích vì sao `access token`, `ID token` và `refresh token` không thể dùng thay thế cho nhau.
- Nhận diện các thành phần của Spring Security tương ứng với từng vai trò, từ `oauth2Login()` đến `oauth2Client()`.
- Đọc một cấu hình Spring Boot OIDC Client và mô tả luồng đăng nhập bằng Authorization Code.

## 1. Bài toán thực tế: một ứng dụng, hai nhu cầu

Giả sử ứng dụng quản lý đơn hàng được xây dựng bằng Spring Boot. Doanh nghiệp dùng một hệ thống định danh tập trung như Keycloak, Microsoft Entra ID hoặc một nhà cung cấp tương thích OpenID Connect.

Ứng dụng cần giải quyết hai vấn đề khác nhau:

1. **Người đang mở ứng dụng là ai?** Khi truy cập trang đơn hàng, người dùng được chuyển đến hệ thống định danh để đăng nhập. Sau khi đăng nhập thành công, ứng dụng cần biết danh tính người dùng và tạo phiên đăng nhập của riêng mình.
2. **Ứng dụng được phép làm gì tại API khác?** Khi cần lấy lịch sử đơn hàng từ một dịch vụ riêng, ứng dụng phải có quyền gọi API đó, thường được thể hiện bằng một access token.

Trong tình huống này, cùng một ứng dụng Spring Boot có thể đồng thời đảm nhận hai vai trò:

- **OpenID Connect Relying Party (RP):** tiếp nhận và kiểm tra thông tin xác thực do nhà cung cấp danh tính phát hành, từ đó đăng nhập người dùng.
- **OAuth 2.0 Client:** yêu cầu và sử dụng access token để gọi API được bảo vệ.

Hai vai trò có quan hệ chặt chẽ nhưng giải quyết hai câu hỏi khác nhau: **“Ai đã đăng nhập?”** và **“Client được cấp quyền truy cập tài nguyên nào?”**.

## 2. OAuth 2.0 Client là gì?

OAuth 2.0 là một framework **ủy quyền truy cập** (authorization). Nó cho phép một ứng dụng, gọi là *client*, nhận quyền truy cập giới hạn đến tài nguyên được bảo vệ mà không cần thu thập mật khẩu của người dùng để tự gọi API.

Ví dụ: ứng dụng quản lý đơn hàng xin quyền đọc danh sách đơn hàng của nhân viên tại một hệ thống khác. Người dùng được đưa đến Authorization Server để đăng nhập và chấp thuận quyền, nếu nhà cung cấp yêu cầu. Client nhận **access token** và dùng token đó để gọi API.

### 2.1. Các vai trò trong OAuth 2.0

| Vai trò | Trách nhiệm | Ví dụ |
|---|---|---|
| **Resource Owner** | Chủ thể có quyền đối với tài nguyên; trong luồng tương tác thường là người dùng | Nhân viên có quyền xem đơn hàng |
| **Client** | Ứng dụng yêu cầu quyền truy cập và sử dụng token | Ứng dụng Spring Boot quản lý đơn hàng |
| **Authorization Server (AS)** | Xử lý yêu cầu cấp quyền và phát hành access token | Máy chủ ủy quyền của doanh nghiệp |
| **Resource Server (RS)** | Lưu trữ/cung cấp tài nguyên, kiểm tra access token trước khi trả API | Dịch vụ REST quản lý đơn hàng |

**Client không đồng nghĩa với trình duyệt.** Trong một ứng dụng web chạy phía server, chính backend Spring Boot là OAuth 2.0 Client; trình duyệt chỉ tham gia chuyển hướng người dùng. Một ứng dụng di động hoặc SPA cũng có thể là OAuth 2.0 Client, với yêu cầu bảo mật phù hợp loại client đó.

### 2.2. OAuth 2.0 Client thực hiện những việc gì?

Tùy grant type và kiến trúc, client:

1. Được đăng ký tại Authorization Server bằng `client_id`, redirect URI, phạm vi quyền (`scope`) và cơ chế xác thực client nếu có.
2. Bắt đầu luồng ủy quyền tương ứng, ví dụ Authorization Code với PKCE cho đăng nhập tương tác.
3. Nhận authorization code rồi đổi code lấy token tại token endpoint, hoặc trực tiếp xin token trong một grant phù hợp như `client_credentials`.
4. Lưu và quản lý access token theo ngữ cảnh người dùng/client; sử dụng refresh token khi có và được phép.
5. Gửi access token đến Resource Server, thường qua header HTTP:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.com
Authorization: Bearer <access_token>
~~~

Resource Server kiểm tra token và các yêu cầu quyền truy cập trước khi xử lý request. Client **không gửi ID token để thay thế access token** khi gọi API.

### 2.3. Client bí mật và client công khai

- **Confidential client** có khả năng bảo vệ thông tin xác thực của chính nó, ví dụ backend Spring Boot giữ client secret phía server.
- **Public client** không thể giữ bí mật client secret một cách đáng tin cậy, ví dụ ứng dụng chạy hoàn toàn trong trình duyệt hoặc ứng dụng di động được cài trên thiết bị người dùng.

`client_id` là định danh của ứng dụng, **không phải mật khẩu**. Với public client, không nhúng client secret vào JavaScript hoặc ứng dụng di động. **PKCE** giúp bảo vệ Authorization Code khỏi bị chặn và sử dụng sai; việc client là confidential không phải lý do để bỏ qua các biện pháp chống tấn công thích hợp.

### 2.4. OAuth 2.0 không tự định nghĩa cơ chế xác thực danh tính cho ứng dụng

Khi một người dùng đăng nhập vào Authorization Server để chấp thuận quyền, hành động đăng nhập đó phục vụ quá trình cấp quyền tại máy chủ ủy quyền. Đặc tả OAuth 2.0 **không quy định một ID token tiêu chuẩn để client xác thực người dùng cuối**.

Một ứng dụng có thể tích hợp đăng nhập dựa trên dữ liệu người dùng từ OAuth provider theo cách riêng, nhưng không nên suy luận danh tính chỉ từ sự hiện diện của access token hoặc từ cấu trúc token mà ứng dụng tự đoán. Bài toán xác thực danh tính có một lớp giao thức riêng: **OpenID Connect**.

## 3. OpenID Connect Relying Party là gì?

**OpenID Connect (OIDC)** là lớp giao thức định danh xây dựng trên OAuth 2.0. Nó chuẩn hóa cách client yêu cầu xác thực người dùng, nhận kết quả xác thực và lấy thông tin người dùng đã được chuẩn hóa.

Trong OIDC:

| Thành phần | Ý nghĩa |
|---|---|
| **End-User** | Người dùng cần được xác thực |
| **OpenID Provider (OP)** | Hệ thống xác thực người dùng và phát hành ID token; đồng thời cung cấp các endpoint OAuth 2.0 liên quan |
| **Relying Party (RP)** | Ứng dụng tin cậy kết quả xác thực hợp lệ do OP phát hành, sau khi tự thực hiện các bước kiểm tra bắt buộc |
| **ID Token** | Token chứa các claim mô tả sự kiện xác thực và danh tính người dùng để RP tiêu thụ |
| **UserInfo Endpoint** | Endpoint OIDC có thể trả thêm thông tin người dùng khi được gọi bằng access token thích hợp |

Một RP về mặt giao thức cũng là OAuth 2.0 Client đã đăng ký với OP. Tuy nhiên, **không phải OAuth 2.0 Client nào cũng là RP**. Ví dụ một tác vụ nền xin token bằng `client_credentials` để gọi API: nó là OAuth client, nhưng không thực hiện đăng nhập người dùng cuối theo OIDC.

### 3.1. Khi nào client trở thành OIDC Relying Party?

Trong một yêu cầu OIDC, client yêu cầu scope **`openid`**. Đây là dấu hiệu quan trọng để OP xử lý yêu cầu theo OpenID Connect và phát hành ID token theo luồng thích hợp.

Ví dụ phạm vi quyền:

~~~text
scope=openid profile email
~~~

- `openid`: yêu cầu chức năng OIDC và định danh người dùng.
- `profile`: yêu cầu một nhóm claim hồ sơ chuẩn, tùy khả năng và quyết định trả claim của OP.
- `email`: yêu cầu các claim email như `email` và `email_verified` nếu được cung cấp.

Không nên mặc định rằng yêu cầu scope nào thì mọi claim tương ứng luôn có mặt trong ID token. OP có thể cung cấp một số claim qua UserInfo Endpoint hoặc không cấp theo chính sách.

### 3.2. ID token là bằng chứng để RP xác thực người dùng

ID token là một JWT theo định dạng OIDC, thường được ký bởi OP. Một payload minh họa có thể trông như sau:

~~~json
{
  "iss": "https://idp.example.com/realms/acme",
  "sub": "8f61c2b4-3b72-4b26-b22c-93f165b2c9a0",
  "aud": "orders-web",
  "iat": 1760000000,
  "exp": 1760003600,
  "nonce": "random-request-binding"
}
~~~

*Giá trị trên là dữ liệu minh họa, không phải token thật.*

Các claim quan trọng:

| Claim | Ý nghĩa | RP cần chú ý |
|---|---|---|
| `iss` | Issuer phát hành token | Phải khớp OP mà RP đã cấu hình |
| `sub` | Định danh người dùng tại issuer | Nên kết hợp `iss` + `sub` làm khóa định danh bền vững |
| `aud` | Đối tượng nhận token, bao gồm client ID của RP | RP phải là audience hợp lệ |
| `exp`, `iat` | Thời gian hết hạn và phát hành | Kiểm tra hiệu lực thời gian theo quy tắc OIDC |
| `nonce` | Giá trị gắn token với yêu cầu xác thực | Kiểm tra khi có sử dụng nonce trong yêu cầu |
| `auth_time` | Thời điểm người dùng được xác thực | Hữu ích khi yêu cầu xác thực lại và chính sách OIDC áp dụng |

RP phải xác thực chữ ký hoặc cơ chế bảo vệ token tương ứng, issuer, audience, thời gian hiệu lực và các điều kiện khác theo chuẩn và theo luồng đã sử dụng. Chỉ giải mã JWT thành JSON rồi tin nội dung **không phải kiểm tra ID token**.

Email hoặc tên hiển thị chỉ là thuộc tính hồ sơ và có thể thay đổi. **`sub` trong phạm vi `iss` mới là cơ sở thích hợp hơn để liên kết tài khoản nội bộ**. Một số OP sử dụng *pairwise subject identifier*, nên `sub` có thể khác nhau giữa các client.

### 3.3. RP “tin cậy” điều gì?

Từ *relying* không có nghĩa là tin bất kỳ dữ liệu nào browser gửi đến. Nó có nghĩa là sau khi hoàn thành kiểm tra giao thức, RP dựa vào khẳng định xác thực của một **OP đã cấu hình và được tin cậy trước**.

RP không trực tiếp kiểm tra mật khẩu của người dùng tại OP. Sau khi xác thực thành công, RP có thể tạo `Authentication` và phiên đăng nhập trong ứng dụng riêng. Việc **phân quyền nghiệp vụ** vẫn thuộc ứng dụng: đăng nhập thành công không tự động có nghĩa người dùng được phép duyệt mọi đơn hàng.

## 4. Phân biệt authorization code, access token, ID token và refresh token

| Giá trị | Ai phát hành/tiếp nhận | Mục đích chính | Có dùng gọi API nghiệp vụ? |
|---|---|---|---|
| **Authorization code** | AS/OP trả về redirect URI của client | Giá trị ngắn hạn, dùng một lần để đổi lấy token | Không |
| **Access token** | AS phát hành cho client; RS tiếp nhận | Mang quyền truy cập tài nguyên, theo scope/audience/chính sách | Có, nếu API chấp nhận token |
| **ID token** | OP phát hành cho RP | Xác thực và truyền đạt danh tính/sự kiện đăng nhập của người dùng | Không dùng thay access token |
| **Refresh token** | AS/OP có thể phát hành cho client | Xin access token mới theo chính sách máy chủ | Không |

Những điểm dễ nhầm:

- ID token có audience hướng đến **RP/client**; access token dành cho **API/Resource Server** và có cách biểu diễn riêng. Access token có thể là JWT hoặc chuỗi opaque: không được giả định luôn giải mã được.
- Access token chứng minh quyền gọi API trong phạm vi được cấp; không có nghĩa nó là một chứng thư đăng nhập người dùng dành cho client.
- ID token giúp RP xác thực người dùng; không cấp phép đọc hoặc ghi tài nguyên tại API.
- Refresh token có thể không được cấp, kể cả khi đã đăng nhập thành công, và phải được lưu giữ rất cẩn thận.
- Cùng một yêu cầu OIDC Authorization Code có thể trả về cả ID token và access token: hai token cùng xuất hiện nhưng có **đối tượng tiêu thụ và trách nhiệm kiểm tra khác nhau**.

## 5. Luồng Authorization Code khi Spring Boot đóng cả hai vai trò

Với ứng dụng web Spring Boot phía server, luồng thông dụng là **OIDC Authorization Code**. OP vừa xác thực người dùng vừa đóng vai Authorization Server cấp access token.

~~~mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Trình duyệt
    participant S as Spring Boot (Client và RP)
    participant OP as OpenID Provider / Authorization Server
    participant API as Resource Server
    U->>B: Mở trang cần đăng nhập
    B->>S: GET /orders
    S-->>B: Chuyển hướng đến OP
    B->>OP: Authorization request (openid, state, nonce, PKCE nếu dùng)
    OP->>U: Xác thực và xin đồng ý nếu cần
    OP-->>B: Redirect với code và state
    B->>S: GET /login/oauth2/code/corp?code=...&state=...
    S->>OP: Đổi code lấy token tại token endpoint
    OP-->>S: ID token, access token (refresh token nếu cấp)
    Note over S: Kiểm tra ID token và tạo Authentication / session
    S->>API: Gọi API với access token
    API-->>S: Dữ liệu đã được phép truy cập
    S-->>B: Trang hoặc dữ liệu của người dùng
~~~

Các bước cần hiểu:

1. **Bảo vệ tài nguyên:** Spring Security phát hiện request cần xác thực và điều hướng browser bắt đầu đăng nhập.
2. **Tạo authorization request:** Client đưa `client_id`, `redirect_uri`, scope có `openid` và dữ liệu bảo vệ request vào URL ủy quyền. `state` giúp liên kết phản hồi với yêu cầu và chống CSRF trong luồng; `nonce` liên kết ID token với yêu cầu OIDC; PKCE, nếu áp dụng, dùng `code_challenge`.
3. **Xác thực tại OP:** Người dùng đăng nhập trên OP. Client không cần nhận mật khẩu của họ.
4. **Nhận authorization code:** Browser được chuyển về redirect URI đã đăng ký kèm `code` và `state`. Code chưa phải access token.
5. **Trao đổi qua back channel:** Backend Spring gửi code đến token endpoint, kèm thông tin xác thực client và/hoặc `code_verifier` theo cấu hình.
6. **Kiểm tra kết quả OIDC:** Spring Security xử lý, kiểm tra ID token và xây dựng principal OIDC. Ứng dụng có thể nhận thêm claim từ UserInfo Endpoint khi phù hợp.
7. **Thiết lập trạng thái ứng dụng:** Người dùng được xác thực trong `SecurityContext`; ứng dụng servlet thường duy trì đăng nhập qua HTTP session/cookie.
8. **Gọi API:** Khi cần, OAuth client sử dụng access token hợp lệ của registration và người dùng tương ứng để gọi Resource Server. API tự kiểm tra token và quyền truy cập.

**Lưu ý:** Đăng nhập trên OP và đăng nhập tại ứng dụng là hai phiên/trạng thái liên quan nhưng không đồng nhất. Hết phiên Spring Boot không nhất thiết đăng xuất khỏi OP; đăng xuất phía OP cũng không tự động vô hiệu hóa mọi phiên ứng dụng nếu chưa tích hợp cơ chế logout phù hợp.

## 6. Spring Security biểu diễn những vai trò này thế nào?

Spring Security cung cấp các khái niệm khác nhau để xử lý cấu hình client, trạng thái OAuth và danh tính đã đăng nhập.

| Thành phần / API | Vai trò |
|---|---|
| `ClientRegistration` | Thông tin đăng ký client: `clientId`, scopes, grant type, redirect URI, endpoint và provider |
| `ClientRegistrationRepository` | Tra cứu đăng ký theo `registrationId`, ví dụ `corp` |
| `oauth2Login()` | Bật cơ chế đăng nhập dựa trên OAuth 2.0 Authorization Code; khi provider hỗ trợ OIDC và yêu cầu `openid`, xử lý đăng nhập OIDC |
| `OidcUser` / `OidcIdToken` | Principal OIDC và ID token đã được Spring Security xử lý sau đăng nhập |
| `SecurityContext` / `Authentication` | Thể hiện trạng thái người dùng được xác thực trong ứng dụng |
| `OAuth2AuthorizedClient` | Ghép `ClientRegistration` với access token và refresh token (nếu có) đã cấp cho một principal/client |
| `OAuth2AuthorizedClientRepository` / `OAuth2AuthorizedClientService` | Lưu và tra cứu authorized client/token theo ngữ cảnh thích hợp |
| `oauth2Client()` | Bật hỗ trợ client OAuth 2.0 để ủy quyền và sử dụng token cho lời gọi đi |
| `OAuth2AuthorizedClientManager` | Điều phối authorize/reauthorize, ví dụ lấy và làm mới token theo grant hỗ trợ |
| `oauth2ResourceServer()` | Cấu hình **vai trò khác**: ứng dụng nhận bearer token để bảo vệ API của chính nó |

Một ứng dụng có thể đồng thời là RP, OAuth 2.0 Client và Resource Server. Tuy nhiên, cấu hình `oauth2Login()` **không tự động biến API của ứng dụng thành Resource Server**; chức năng nhận và xác minh bearer token cần cấu hình riêng.

### 6.1. Ví dụ cấu hình OIDC Client trong Spring Boot

Dependency tối thiểu cho tính năng client khi dùng Spring Boot Maven:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
</dependency>
~~~

Ví dụ `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: \${OIDC_CLIENT_ID}
            client-secret: \${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
              - email
        provider:
          corp:
            issuer-uri: https://idp.example.com/realms/acme
~~~

Trong ví dụ:

- `corp` là **registrationId** dùng để chọn cấu hình client, không phải tên chuẩn bắt buộc của OIDC.
- `client-id` xác định ứng dụng tại OP; `client-secret` là bí mật của confidential client phía backend. Các giá trị nhạy cảm được cấp qua biến môi trường/secret manager.
- `issuer-uri` chỉ ra nhà phát hành OIDC mà ứng dụng tin cậy. Spring Security có thể dùng cơ chế discovery theo metadata của provider để lấy authorization endpoint, token endpoint, JWK Set URI và những thông tin liên quan, tùy provider.
- Redirect URI mặc định trong ví dụ đưa người dùng về `/login/oauth2/code/corp`. URI thực tế phải được đăng ký khớp tại OP.
- `openid` khiến đây là yêu cầu đăng nhập OIDC, còn `profile`, `email` yêu cầu thêm claim thích hợp.

Cấu hình này giả định OP hỗ trợ OIDC discovery và Authorization Code, đồng thời client đã được đăng ký tại OP. Domain `idp.example.com` chỉ là địa chỉ ví dụ.

### 6.2. Bật đăng nhập và hỗ trợ OAuth 2.0 Client

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(requests -> requests
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .oauth2Client(Customizer.withDefaults())
            .build();
    }
}
~~~

Ý nghĩa:

- `oauth2Login()` phục vụ bước **đăng nhập của người dùng**; khi nhận được ID token hợp lệ, Spring tạo principal OIDC cho request.
- `oauth2Client()` hỗ trợ bước **ứng dụng sử dụng quyền truy cập API**, gồm truy xuất authorized client và tích hợp với cơ chế quản lý token.
- Phần `authorizeHttpRequests(...)` xác định tài nguyên nào của ứng dụng phải đăng nhập. Quyền vào từng hành động nghiệp vụ cần được áp chính sách riêng; không suy ra từ việc người dùng có ID token.

Tùy phiên bản, Spring Boot có thể tự cấu hình một phần tính năng nếu chỉ có một cấu hình client; ví dụ trên viết tường minh hai chức năng để dễ phân biệt vai trò.

### 6.3. Đọc danh tính OIDC sau đăng nhập

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class CurrentUserController {

    @GetMapping("/me")
    public UserView currentUser(@AuthenticationPrincipal OidcUser user) {
        return new UserView(
            user.getIdToken().getIssuer().toString(),
            user.getIdToken().getSubject(),
            user.getFullName()
        );
    }

    record UserView(String issuer, String subject, String fullName) {}
}
~~~

Ở đây `OidcUser` cho phép ứng dụng lấy danh tính đã được xử lý bởi hệ thống đăng nhập OIDC. `fullName` có thể không có nếu OP không trả claim tương ứng. Việc chọn `issuer` + `subject` làm định danh phù hợp hơn dùng email hoặc tên hiển thị.

Controller trên dành cho endpoint cần đăng nhập OIDC. Nếu cùng ứng dụng còn hỗ trợ một cơ chế đăng nhập khác, principal không nhất thiết luôn thuộc kiểu `OidcUser`; mã ứng dụng cần xử lý đúng các loại authentication được cho phép.

### 6.4. Lấy access token để gọi API

Trong servlet application, có thể truy xuất authorized client đã được cấp cho registration và người dùng:

~~~java
import org.springframework.security.oauth2.client.OAuth2AuthorizedClient;
import org.springframework.security.oauth2.client.annotation.RegisteredOAuth2AuthorizedClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrdersController {

    @GetMapping("/orders/access-status")
    public String accessStatus(
            @RegisteredOAuth2AuthorizedClient("corp")
            OAuth2AuthorizedClient authorizedClient) {

        return authorizedClient.getAccessToken() != null
                ? "Access token is available for an API request"
                : "No access token is available";
    }
}
~~~

Đây là ví dụ minh họa cách nhận `OAuth2AuthorizedClient`, **không trả token ra HTTP response**. Trong nghiệp vụ thật, ứng dụng sẽ gửi token qua header `Authorization: Bearer ...` đến đúng Resource Server, thường bằng HTTP client được tích hợp với `OAuth2AuthorizedClientManager` để quản lý việc lấy/làm mới token.

Việc có token **không bảo đảm** token đó dùng được cho mọi API. Resource Server còn xem xét issuer, audience, scope, thời hạn, chính sách phân quyền và hình thức token mà nó hỗ trợ. Nếu cần gọi API khác với scope/audience khác, có thể phải đăng ký hoặc xin cấp quyền thích hợp.

## 7. Các trường hợp triển khai: khi nào là Client, khi nào là RP?

| Tình huống | OAuth 2.0 Client? | OIDC RP? | Diễn giải |
|---|---|---|---|
| Web app đăng nhập bằng OIDC qua OP | Có | Có | Xin token qua OAuth, kiểm tra ID token để đăng nhập |
| Web app dùng access token của người dùng để gọi API | Có | Có thể | Là Client; là RP nếu đồng thời dùng OIDC xác thực người dùng |
| Backend chạy tác vụ nền với `client_credentials` | Có | Không | Quyền cấp cho client/service, không có người dùng cuối cần xác thực bằng ID token |
| REST API chỉ nhận/kiểm tra bearer token | Không nhất thiết | Không nhất thiết | Chủ yếu là Resource Server; chỉ là Client/RP nếu nó còn có các chức năng tương ứng |
| Ứng dụng chỉ nhận callback OIDC và tạo session, chưa gọi API riêng | Có | Có | RP vẫn là một OAuth/OIDC Client dù access token không được dùng để gọi API nghiệp vụ |

**Ví dụ đối chiếu:** “Ứng dụng A cho phép nhân viên đăng nhập qua Keycloak, sau đó dùng access token để đọc `/employees` từ Service B.” A là RP **và** OAuth 2.0 Client. Keycloak là OP/Authorization Server. Service B là Resource Server. Người dùng là End-User và, trong luồng ủy quyền thích hợp, là Resource Owner.

## 8. Những ranh giới bảo mật cần giữ rõ

### 8.1. Ba cơ chế không thay thế nhau

- **`state`** gắn kết authorization response với yêu cầu ban đầu và hỗ trợ chống CSRF trong luồng chuyển hướng.
- **`nonce`** liên kết ID token với phiên yêu cầu OIDC nhằm chống tình huống phát lại hoặc tráo đổi token theo cơ chế của OIDC.
- **PKCE** liên kết authorization code với bên khởi tạo yêu cầu thông qua `code_challenge` và `code_verifier`, giảm nguy cơ code bị chặn rồi đổi lấy token bởi bên khác.

Các biện pháp này có mục đích riêng. Hãy để thư viện OIDC/OAuth đã được kiểm chứng thực hiện luồng và kiểm tra đúng chuẩn; không tự tạo callback handler rồi bỏ qua xác minh để đơn giản hóa code.

### 8.2. Token phải đến đúng nơi nhận

- Không dùng **ID token** để gọi API thay cho access token.
- Không dùng **access token** nhận từ browser như bằng chứng duy nhất để đăng nhập RP mà bỏ qua OIDC.
- Không ghi access token, refresh token, authorization code hay client secret vào log hoặc response.
- Dùng HTTPS và redirect URI được đăng ký chặt chẽ; tránh redirect mở hoặc xử lý callback tại URL tùy ý.
- Hạn chế scope theo nhu cầu, bảo vệ nơi lưu token/secret và xây dựng chính sách hết hạn/thu hồi phù hợp.

### 8.3. Xác thực và phân quyền vẫn khác nhau

OIDC cho biết người dùng đã được OP xác thực theo ngữ cảnh mà ID token mô tả. Để quyết định “nhân viên này có được duyệt đơn hàng số 123 không?”, ứng dụng cần kiểm tra **quyền nghiệp vụ**. Có thể ánh xạ claim, group hoặc role từ OP vào authorities của Spring Security nếu chính sách yêu cầu, nhưng không mặc định mọi claim từ OP đều cấp toàn quyền cho người dùng.

Nếu application cung cấp API cho client khác, Spring Security còn cần cấu hình Resource Server để nhận và xác minh access token tại API đó. Hãy đánh giá riêng cả **đăng nhập web** và **bảo vệ API**.

### 8.4. Đăng xuất ở nhiều nơi

`logout()` của ứng dụng Spring Security thường xử lý trạng thái đăng nhập cục bộ. Nếu muốn người dùng đăng xuất cả tại OP, cần tích hợp cơ chế tương ứng của OIDC (ví dụ RP-Initiated Logout khi nhà cung cấp hỗ trợ). Ngược lại, phiên OP vẫn tồn tại có thể khiến lần đăng nhập tiếp theo diễn ra mà người dùng không phải nhập lại mật khẩu.

## 9. Các hiểu nhầm thường gặp

**“Có access token tức là đã biết người dùng là ai?”**  
Không. Access token dành cho việc truy cập tài nguyên và có thể đại diện cho client, cho người dùng hoặc ngữ cảnh khác tùy grant và chính sách. RP cần cơ chế xác thực danh tính phù hợp, thông thường qua ID token OIDC.

**“Có scope `openid` thì mọi thông tin hồ sơ sẽ luôn nằm trong ID token?”**  
Không. `openid` kích hoạt yêu cầu OIDC; các claim như tên, email phụ thuộc scope, khả năng và chính sách OP. Một số claim có thể đến từ UserInfo Endpoint.

**“`oauth2Login()` và `oauth2Client()` có cùng nhiệm vụ?”**  
Không. Chức năng thứ nhất phục vụ luồng đăng nhập; chức năng thứ hai phục vụ quản lý ủy quyền/token cho client. Chúng có thể cùng sử dụng một client registration và có thể cùng bật trong một ứng dụng.

**“Ứng dụng chỉ gọi API bằng `client_credentials` có phải RP?”**  
Không. Nó là OAuth 2.0 Client thực hiện ủy quyền giữa các dịch vụ; không xác thực End-User bằng OIDC.

**“Ứng dụng Spring Boot có `spring-boot-starter-oauth2-client` thì tự động bảo vệ REST API bằng JWT?”**  
Không. Bảo vệ endpoint theo bearer access token là vai trò Resource Server, thường dùng `spring-boot-starter-oauth2-resource-server` và cấu hình xác thực token phù hợp.

**“ID token là JWT thì access token cũng bắt buộc là JWT?”**  
Không. OIDC quy định ID token ở dạng JWT, nhưng định dạng access token do Authorization Server/Resource Server quyết định theo giao thức và sản phẩm liên quan.

## 10. Tình huống tự kiểm tra

Hãy xác định vai trò của từng thành phần trong hệ thống:

> Ứng dụng **Portal** chạy Spring Boot chuyển người dùng đến **Identity Server** để đăng nhập. Portal nhận ID token và access token. Sau đó Portal dùng access token gọi **Inventory API** để xem danh sách tồn kho.

- **Portal**: OAuth 2.0 Client khi xin và dùng access token; OIDC RP khi xác thực kết quả đăng nhập bằng ID token.
- **Identity Server**: OpenID Provider và Authorization Server.
- **Inventory API**: Resource Server, kiểm tra access token và quyền truy cập.
- **Người dùng**: End-User; cũng có thể là Resource Owner trong luồng ủy quyền tài nguyên của họ.

Nếu Portal về sau mở endpoint REST cho ứng dụng di động gửi bearer token, Portal còn có thể kiêm **Resource Server**. Vai trò được xác định theo **hành vi tại từng giao tiếp**, không chỉ theo tên hoặc số lượng ứng dụng triển khai.

## Ghi nhớ

**OAuth 2.0 Client** giúp ứng dụng nhận và sử dụng quyền truy cập tài nguyên bằng access token. **OpenID Connect RP** giúp ứng dụng xác thực người dùng dựa trên ID token hợp lệ do OP phát hành. Trong Spring Security, hai trách nhiệm này thường cùng xuất hiện trong một ứng dụng web, nhưng cần phân biệt rõ đối tượng của token, thành phần xử lý và quy tắc bảo mật của mỗi vai trò.
