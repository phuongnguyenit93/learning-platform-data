# 10.6. Public client, phương thức none và điều kiện sử dụng

> **Module:** Spring Security OAuth 2.0 OIDC Client  
> **Chương:** 10. Token Endpoint  
> **Trọng tâm:** Phân biệt public client và confidential client; hiểu `client-authentication-method: none` khi đổi authorization code lấy token; kết hợp PKCE, cấu hình Spring Security và chính sách Authorization Server để triển khai an toàn.

Khi Spring Security OAuth 2.0 Client gọi **Token Endpoint**, Authorization Server cần biết Client nào đang yêu cầu token và có cần xác thực Client đó hay không. Với ứng dụng server-side có thể giữ bí mật, Client thường được đăng ký là **confidential client** và xác thực bằng `client_secret_basic`, `client_secret_post` hoặc cơ chế mạnh hơn. Nhưng không phải mọi loại ứng dụng đều giữ được client secret.

Single-page application (SPA) chạy JavaScript trên trình duyệt, ứng dụng native trên điện thoại hay ứng dụng desktop phân phối tới máy người dùng thường là **public client**. Mã ứng dụng, network traffic và những giá trị đóng gói kèm ứng dụng có thể bị người dùng hoặc kẻ tấn công kiểm tra. Một “client secret” nhúng trong mã vì vậy không thực sự là bí mật có thể dùng để chứng minh danh tính Client.

OAuth 2.0 cho phép sử dụng phương thức xác thực Client **`none`**: Client không trình bí mật hay chữ ký xác thực Client ở Token Endpoint. Điều đó **không** có nghĩa Token Endpoint chấp nhận yêu cầu tùy ý. Authorization Server vẫn phải xác định client ID, xác minh authorization code, redirect URI, PKCE code verifier và các điều kiện của grant; Client còn phải xử lý bảo mật OIDC, session và token phù hợp với kiến trúc.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **public client** và **confidential client** bằng khả năng bảo vệ thông tin xác thực của chính Client.
2. Giải thích `none` ở Token Endpoint nghĩa là gì và những kiểm tra nào vẫn bắt buộc.
3. Cấu hình `client-authentication-method: none` cho một registration Spring Security OAuth 2.0 Client.
4. Phân tích Authorization Code + **PKCE S256** khi public client đổi code lấy token.
5. Xác định vì sao `client_id` vẫn được sử dụng dù không có client secret.
6. Chọn kiến trúc phù hợp cho SPA, native app, desktop app, Spring MVC server-side và Backend for Frontend (BFF).
7. Phân biệt token request của public client với token request dùng `client_secret_basic` hoặc phương thức confidential khác.
8. Nhận biết điều kiện phải được Authorization Server hỗ trợ trước khi dùng `none`.
9. Chẩn đoán các lỗi như `invalid_client`, `invalid_grant`, PKCE không khớp hoặc redirect URI không hợp lệ.
10. Tránh dùng `none` như cách “tắt bảo mật” để chữa lỗi client secret.

## 2. Public client và confidential client là gì?

Trong OAuth 2.0, phân loại Client dựa trên **khả năng giữ an toàn thông tin xác thực dùng để xác thực chính Client**.

| Phân loại | Đặc điểm | Ví dụ điển hình |
|---|---|---|
| **Confidential client** | Có thể lưu giữ thông tin xác thực Client ngoài tầm truy cập của người dùng cuối | Ứng dụng Spring Boot chạy trên backend do tổ chức quản lý |
| **Public client** | Không thể bảo đảm giữ bí mật thông tin xác thực Client trước người dùng cuối hoặc người có khả năng phân tích mã chạy trên thiết bị | SPA JavaScript, native mobile app, ứng dụng desktop phân phối tới người dùng |

**Đừng phân loại theo ngôn ngữ lập trình.** Cùng một hệ thống “viết bằng Java” có thể là backend bảo vệ được secret hoặc desktop application không bảo vệ được secret. Tương tự, việc một website có JavaScript không tự biến **backend** Spring Boot của website thành public client.

### 2.1. Ví dụ đối chiếu

**Tình huống A — Spring Boot MVC trên máy chủ:** Browser gửi request tới backend; backend giữ client secret trong secret manager, thực hiện token exchange qua kết nối server-to-server. Đây thường là kiến trúc **confidential client**.

**Tình huống B — SPA chạy hoàn toàn trong browser:** JavaScript nhận authorization code ở redirect URI thuộc ứng dụng và trực tiếp gọi Token Endpoint. Toàn bộ mã và giá trị cấu hình được gửi tới browser. Đây thường là **public client**.

**Tình huống C — Mobile app:** Ứng dụng cài trên điện thoại và dùng system browser để đăng nhập. Bất kỳ secret nào đóng gói trong APK/IPA đều có thể bị trích xuất. Đây thường là **public client**.

**Tình huống D — BFF (Backend for Frontend):** Browser chỉ giữ cookie phiên của backend; BFF thực hiện OAuth token exchange và lưu token ở phía server. BFF có thể đăng ký làm **confidential client** nếu nó quản lý được thông tin xác thực Client một cách an toàn.

Việc nhà cung cấp cấp một chuỗi gọi là “secret” cho phần mềm mobile không khiến nó trở thành confidential client nếu chuỗi ấy phải phân phối tới mọi thiết bị của người dùng.

### 2.2. Phân loại là thuộc tính của registration và môi trường

Một hệ thống có thể có nhiều OAuth 2.0 Client registrations:

- `web-server` được đăng ký confidential cho backend.
- `mobile-app` được đăng ký public cho ứng dụng di động.
- `browser-spa` được đăng ký public cho SPA.

Chúng có thể dùng cùng Authorization Server và cùng người dùng, nhưng **không được mặc định dùng chung client secret hoặc cùng chính sách xác thực Client**. Mỗi registration cần loại Client, redirect URI, grant types, scopes và cơ chế bảo vệ phù hợp.

## 3. Phương thức none có nghĩa gì?

Spring Security biểu diễn phương thức xác thực Client qua `ClientAuthenticationMethod`. Một số giá trị quen thuộc là:

| Phương thức | Bên thực hiện xác thực Client | Cách thể hiện thường thấy tại Token Endpoint |
|---|---|---|
| `client_secret_basic` | Confidential client | HTTP Basic Authentication với client ID và client secret |
| `client_secret_post` | Confidential client | Gửi client ID và client secret trong form body theo chuẩn/hợp đồng AS |
| `private_key_jwt` | Confidential client có khóa riêng | Ký client assertion JWT rồi gửi đến Token Endpoint |
| `client_secret_jwt` | Confidential client có secret | Ký client assertion JWT bằng secret chia sẻ |
| `none` | Public client | **Không trình credential để xác thực Client**; vẫn gửi dữ liệu xác định Client/grant cần thiết |

Cụm “none” có nghĩa chính xác là **không có client authentication tại Token Endpoint**. Nó không có nghĩa:

- Client không cần đăng ký với Authorization Server.
- Client không cần `client_id`.
- Authorization Server không kiểm tra authorization code.
- Client được bỏ PKCE.
- Người dùng không cần xác thực ở Authorization Server.
- Redirect URI có thể tùy ý.
- Access token có thể dùng cho API bất kỳ.
- Resource Server không cần kiểm tra token.

Đây là khác biệt giữa **client identification** và **client authentication**:

- `client_id` là một định danh công khai, cho biết request đề cập tới registration nào.
- Client authentication chứng minh bên gửi request sở hữu thông tin xác thực của Client; public client dùng `none` **không có bằng chứng bí mật như vậy**.
- PKCE giúp liên kết authorization code với phía đã khởi tạo authorization request, nhưng **không biến public client thành confidential client**.

### 3.1. Client ID không phải secret

Trong một SPA hoặc mobile app, người dùng có thể nhìn thấy `client_id` trong mã, cấu hình hoặc authorization URL. Điều đó là bình thường: OAuth 2.0 không coi client ID là thông tin bí mật.

Ví dụ:

```text
client_id=mobile-learning-app
client_authentication_method=none
```

Client ID cần đúng registration mà Authorization Server biết, nhưng bản thân nó không chứng minh người gửi request là ứng dụng chính chủ. Không bảo vệ API chỉ dựa trên việc request tự khai báo một client ID có tên quen thuộc.

## 4. Token Endpoint của public client vẫn làm gì?

Đối với Authorization Code grant, một Token Endpoint được cấu hình đúng phải xử lý các ràng buộc của **authorization grant** trước khi phát hành token.

Các điều kiện quan trọng gồm:

1. **Client registration tồn tại và được phép dùng grant** `authorization_code`.
2. **Authorization code hợp lệ**, còn thời hạn, chưa bị sử dụng và được cấp cho Client phù hợp.
3. **Client ID đúng** với code/client registration khi public client không xác thực Client bằng credential.
4. **Redirect URI phù hợp** với authorization request ban đầu và chính sách đăng ký; khi yêu cầu theo giao thức, giá trị trong token request phải trùng khớp.
5. **PKCE code verifier đúng** với code challenge đã lưu từ authorization request; ưu tiên S256 và tuân chính sách AS.
6. **Token issuance policy** được thực thi, gồm scopes, audience/resource, consent, thời hạn và ràng buộc khác của AS.
7. **Kết nối bảo mật:** dùng TLS/HTTPS trong môi trường thực; không gửi code/verifier/token qua HTTP công khai.
8. **Không phát hành token khi kiểm tra thất bại**, đồng thời trả lỗi OAuth phù hợp.

Đáng chú ý, public client **vẫn có thể nhận access token và ID token OIDC** sau một Authorization Code flow hợp lệ. `none` chỉ mô tả cách xác thực **chính Client** tại Token Endpoint; nó không làm mất khả năng OP xác thực **người dùng** và phát hành thông điệp OIDC.

## 5. Authorization Code + PKCE là nền tảng quan trọng

PKCE (Proof Key for Code Exchange, RFC 7636) được thiết kế để giảm rủi ro **authorization code bị chặn hoặc bị sử dụng bởi bên khác**. PKCE đặc biệt quan trọng với public clients vì chúng không có client secret được giữ an toàn để xác thực ở Token Endpoint.

### 5.1. Hai giá trị cần hiểu

- **`code_verifier`:** chuỗi ngẫu nhiên khó đoán do Client tạo cho **một authorization transaction**.
- **`code_challenge`:** giá trị dẫn xuất từ `code_verifier` và được gửi trong authorization request.

Với phương thức `S256`:

```text
code_challenge = BASE64URL-ENCODE(
    SHA256(ASCII(code_verifier))
)
```

Thông số `code_challenge_method=S256` cho Authorization Server biết cách kiểm tra. Khi Token Endpoint nhận `code_verifier`, nó tự tính challenge và so với giá trị đã lưu cho authorization code.

**Không gửi `code_verifier` trong authorization request qua browser.** Authorization request chỉ mang `code_challenge`. Verifier được giữ cho tới token request; người chặn được authorization code nhưng không biết verifier sẽ không đổi code thành token thành công nếu AS cưỡng chế PKCE đúng.

### 5.2. Luồng đầy đủ

```mermaid
sequenceDiagram
    autonumber
    actor U as Người dùng
    participant B as Browser / Native App
    participant C as Public Client
    participant AS as Authorization Server / OP
    U->>C: Chọn đăng nhập
    C->>C: Sinh code_verifier bí mật theo từng giao dịch
    C->>C: Tính code_challenge = BASE64URL(SHA256(verifier))
    C-->>B: Mở authorization URL
    B->>AS: client_id, redirect_uri, state, code_challenge, method=S256
    AS->>U: Xác thực / consent nếu cần
    AS-->>B: Redirect về client với code và state
    B->>C: Chuyển authorization code
    C->>AS: POST token: code, client_id, redirect_uri, code_verifier; không client secret
    AS->>AS: Đối chiếu code, Client, redirect URI và PKCE
    AS-->>C: Access token và kết quả tương ứng nếu hợp lệ
    C->>C: Nếu OIDC, xác minh ID token và thiết lập phiên phù hợp
```

### 5.3. PKCE không thay thế những cơ chế khác

PKCE không chứng minh ứng dụng đang chạy trên thiết bị là “ứng dụng chính chủ”. Nó cũng không tự thay:

- `state`/các cơ chế chống CSRF và đối chiếu callback;
- kiểm tra redirect URI;
- OIDC `nonce` và quy tắc xác minh ID token khi áp dụng;
- giới hạn scopes và phân quyền Resource Server;
- bảo vệ access/refresh token sau khi phát hành;
- các biện pháp chống chiếm đoạt redirect hoặc deep link trên mobile.

Một ứng dụng mạnh dùng **nhiều lớp kiểm tra phù hợp**, thay vì coi PKCE là phương án thay thế cho toàn bộ OAuth/OIDC security.

## 6. Public client gửi token request như thế nào?

Sau khi nhận một authorization code hợp lệ, public client gửi HTTP request dạng `application/x-www-form-urlencoded` đến Token Endpoint. Ví dụ minh họa:

```http
POST /realms/training/protocol/openid-connect/token HTTP/1.1
Host: id.example.test
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code
&client_id=mobile-learning-app
&code=<one-time-authorization-code>
&redirect_uri=com.example.learning%3A%2Foauth2redirect
&code_verifier=<per-request-secret-verifier>
```

Trong HTTP thực, các cặp form được mã hóa URL và nằm trên một dòng body; phần trên ngắt dòng để dễ đọc. Ví dụ `com.example.learning:/oauth2redirect` là redirect URI minh họa cho native application; scheme/URI được hỗ trợ thực tế phải phù hợp đăng ký và chính sách của AS.

**Điểm nhận diện phương thức none:**

- Không có header `Authorization: Basic ...` chứa client secret.
- Không có trường `client_secret` trong body.
- Không có `client_assertion` được dùng để xác thực Client.
- Có `client_id` để định danh Client khi không có client authentication.
- Có `code_verifier` nếu authorization request trước đó sử dụng PKCE; với public clients hiện đại, AS nên yêu cầu và kiểm tra PKCE.

Đây không phải yêu cầu “không có Authorization header thì luôn hợp lệ”; Authorization Server vẫn cần xác minh toàn bộ ràng buộc authorization code.

### 6.1. So sánh với confidential client

Ví dụ confidential client dùng HTTP Basic:

```http
POST /realms/training/protocol/openid-connect/token HTTP/1.1
Host: id.example.test
Authorization: Basic <redacted-client-credentials>
Content-Type: application/x-www-form-urlencoded

grant_type=authorization_code
&code=<one-time-authorization-code>
&redirect_uri=https%3A%2F%2Fapp.example.test%2Flogin%2Foauth2%2Fcode%2Fweb
```

Với public client, request gửi `client_id` và không trình client secret; với confidential client, Authorization Server có thể yêu cầu cơ chế client authentication đã đăng ký. Cả hai có thể dùng PKCE; **confidential client cũng được khuyến nghị sử dụng PKCE** trong các thiết kế Authorization Code hiện đại.

### 6.2. Vì sao client_id vẫn cần ở token request?

Authorization code phải gắn với Client được cấp phép. Khi không có cơ chế client authentication, Token Endpoint cần biết **client registration nào** đang yêu cầu đổi code. `client_id` giúp AS tìm registration và đối chiếu code. Đây là **định danh**, không phải bằng chứng sở hữu Client.

Một hệ thống sai có thể chấp nhận mọi code cùng Client ID do bất kỳ ai cung cấp mà bỏ kiểm tra PKCE; hệ thống đúng phải cưỡng chế các điều kiện của grant để ngăn code interception.

### 6.3. Không đăng nhập bằng access token trả về một cách tùy ý

Nếu request OIDC có scope `openid`, OP trả ID token theo quy tắc OIDC Code flow. Client dùng ID token đã được xác minh để xác lập danh tính. Access token có mục đích truy cập Resource Server; không tự giải mã access token rồi sử dụng như ID token.

Phương thức `none` chỉ tác động tới **client authentication** tại Token Endpoint. Nó không thay đổi sự khác biệt giữa xác thực người dùng, cấp quyền API và quản lý phiên.

## 7. Sinh code_verifier và code_challenge

Thực tế nên để thư viện OAuth 2.0 được duy trì tốt sinh và quản lý PKCE. Để hiểu thuật toán, có thể xem ví dụ Java độc lập:

```java
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.SecureRandom;
import java.util.Base64;

public final class PkceExample {

    public static void main(String[] args) throws Exception {
        byte[] randomBytes = new byte[32];
        new SecureRandom().nextBytes(randomBytes);

        String codeVerifier = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(randomBytes);

        byte[] digest = MessageDigest.getInstance("SHA-256")
            .digest(codeVerifier.getBytes(StandardCharsets.US_ASCII));

        String codeChallenge = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(digest);

        System.out.println("challenge method: S256");
        System.out.println("challenge length: " + codeChallenge.length());

        // Không in codeVerifier trong ứng dụng thật:
        // giá trị này phải được giữ bí mật cho đúng một transaction.
    }
}
```

32 byte ngẫu nhiên sau mã hóa Base64url không padding tạo chuỗi verifier dài 43 ký tự, phù hợp giới hạn độ dài của RFC 7636. Verifier không phải mật khẩu người dùng hoặc client secret dài hạn; nó là giá trị bí mật **riêng cho giao dịch authorization**.

Khi thiết kế implementation riêng:

1. Sử dụng nguồn ngẫu nhiên mật mã như `SecureRandom`.
2. Sinh verifier mới cho mỗi authorization attempt.
3. Dùng `S256` thay vì dựa vào `plain`, trừ khi có lý do tương thích thực sự đã được đánh giá.
4. Gắn verifier với đúng authorization transaction và chống trộn lẫn các callback đồng thời.
5. Không đưa verifier vào authorization URL hoặc log.
6. Xóa/ngừng dùng verifier sau khi hoàn tất hoặc thất bại theo chính sách.

Một lỗi hay gặp là sinh lại verifier khi callback xuất hiện. Giá trị đó sẽ **không khớp** challenge của request ban đầu, khiến token exchange thất bại. Framework cần giữ verifier từ lúc tạo authorization request cho tới lúc nhận code và gọi Token Endpoint.

## 8. Điều kiện ở Authorization Server trước khi sử dụng none

Cấu hình trong Client chỉ là một nửa của hợp đồng. Authorization Server phải biết registration đó là public client và cho phép dùng phương thức `none`.

| Điều kiện | Lý do |
|---|---|
| Client đã đăng ký với loại **public** hoặc token endpoint auth method `none` | AS cần nhận biết Client không xác thực bằng credential |
| Có client ID riêng | AS xác định registration, scopes và chính sách cho Client |
| Authorization Code flow được cho phép | Client cần grant hợp lệ để đổi code |
| PKCE S256 được bật và cưỡng chế | Giảm rủi ro code interception khi không có client secret |
| Redirect URIs được đăng ký chính xác | Ngăn tùy ý chuyển code sang địa chỉ không kiểm soát |
| Các scopes/resources được giới hạn | Token không được trao quyền vượt chính sách |
| Thời hạn/sử dụng một lần của authorization code được kiểm soát | Giảm khả năng replay |
| TLS và chính sách token phù hợp | Bảo vệ code, verifier và token trên đường truyền |
| Cấu hình refresh token cho public client được đánh giá | Giới hạn rủi ro lộ refresh token và replay |

**Không thể** chuyển một Client đang được đăng ký confidential sang `none` chỉ bằng việc xóa `client-secret` trong Spring Boot. Nếu Authorization Server yêu cầu client authentication, token request không có credential sẽ bị từ chối.

### 8.1. Token Endpoint hỗ trợ none không có nghĩa mọi Client được dùng none

Một Authorization Server có thể hỗ trợ nhiều phương thức xác thực Client đồng thời, nhưng **mỗi registration** có cơ chế được phép sử dụng. Ví dụ một AS hỗ trợ cả public mobile app và confidential backend.

Nếu token endpoint metadata có công bố `token_endpoint_auth_methods_supported`, đó là khả năng chung mà OP hỗ trợ, **không thay thế cấu hình thực tế của từng Client**. Chỉ vì có `none` trong danh sách không có nghĩa một Client có secret đã đăng ký có thể tự ý bỏ secret.

### 8.2. Phải tách client authentication khỏi user authentication

Người dùng vẫn có thể phải đăng nhập, xác minh MFA, chấp thuận scope và chịu kiểm tra chính sách tại OP trong authorization flow. `none` không bỏ những bước này.

Ví dụ một mobile client dùng `none` nhưng Authorization Server yêu cầu MFA khi đăng nhập nhân viên. Sau khi xác thực, nó vẫn có thể phát ID token biểu diễn sự kiện xác thực người dùng theo OIDC. Hai câu hỏi “Ai là người dùng?” và “Client có tự xác thực bằng secret không?” được xử lý riêng.

## 9. Cấu hình public client trong Spring Boot / Spring Security

Xét một ứng dụng Spring Boot MVC trong lab được đăng ký với Authorization Server như một public client. Mặc dù backend **có thể** bảo vệ client secret, ví dụ này chủ ý dùng registration không có secret để minh họa Token Endpoint behavior. Trong hệ thống sản phẩm, chọn public hay confidential dựa trên kiến trúc và khả năng giữ secret thực tế, không dùng `none` chỉ để làm cấu hình ngắn hơn.

### 9.1. Dependencies

Ứng dụng Servlet web dùng các starter phù hợp:

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
</dependencies>
```

### 9.2. application.yml

Giả sử OP thử nghiệm công bố issuer `http://localhost:9000/realms/training` và registration có client ID `learning-public`:

```yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      client:
        registration:
          learning-public:
            provider: training
            client-id: learning-public
            client-authentication-method: none
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope:
              - openid
              - profile
        provider:
          training:
            issuer-uri: http://localhost:9000/realms/training
```

**Điểm cần nhận diện:**

- `client-authentication-method: none` mô tả việc Client không dùng client authentication credential tại Token Endpoint.
- **Không có** `client-secret` cho registration này.
- `client-id: learning-public` vẫn phải trùng Client đăng ký tại OP.
- `authorization-grant-type: authorization_code` dùng Authorization Code, không phải password hoặc implicit grant.
- `scope: openid` yêu cầu OIDC Login; Spring Security sẽ xử lý ID token khi nhà cung cấp hỗ trợ.
- `redirect-uri` phải khớp URI đã đăng ký ở OP, ví dụ `http://localhost:8080/login/oauth2/code/learning-public`.
- `issuer-uri` phải trùng issuer thực sự do OP công bố.

HTTP localhost trong lab chỉ để minh họa; ở môi trường thật cần HTTPS và TLS phù hợp. Đừng sao chép URL của một realm/OP cụ thể nếu dự án không thực sự sử dụng nó.

### 9.3. Cấu hình SecurityFilterChain

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class SecurityConfig {

    @Bean
    SecurityFilterChain webSecurityChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
```

Với registration `learning-public`, người dùng có thể bắt đầu bằng:

```text
http://localhost:8080/oauth2/authorization/learning-public
```

`oauth2Login()` cung cấp luồng Authorization Code/OIDC cho Servlet Client; chỉ khai báo `client-authentication-method: none` trong YAML chưa đủ nếu bạn tự định nghĩa HTTP Security nhưng bỏ quên `oauth2Login()`.

### 9.4. Spring Security và PKCE

`DefaultOAuth2AuthorizationRequestResolver` có cơ chế hỗ trợ PKCE trong Authorization Code flow; ở những phiên bản Spring Security 6.x phổ biến, nó áp dụng PKCE khi client authentication method là `none`. Vì vậy, khi sử dụng các thành phần mặc định phù hợp, bạn thường **không cần tự sinh code_verifier hoặc tự ghép code_challenge vào URL**.

Tuy nhiên, cần hiểu đúng ranh giới:

- Client tạo challenge và lưu verifier.
- Authorization Server phải **cưỡng chế** PKCE theo chính sách public client và so sánh verifier đúng cách.
- Nếu bạn thay custom `OAuth2AuthorizationRequestResolver` hoặc token response client, phải giữ cơ chế PKCE gốc.
- Khi nâng phiên bản framework, đối chiếu hành vi PKCE trong chính nhánh Spring Security đang dùng.
- Browser redirect chỉ thấy `code_challenge`, còn verifier được dùng khi gọi Token Endpoint.

Mã Spring MVC trên minh họa **server-side OAuth2 Client** dùng `none`, không tự biến browser thành direct-to-token SPA. Trong ứng dụng này, token exchange vẫn được thực hiện ở phía Spring Boot.

## 10. Public client trong Java configuration

Khi ứng dụng không dùng properties để tạo registration, có thể tạo `ClientRegistration` bằng API Java. Ví dụ dùng metadata của một OP có OIDC discovery:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.client.registration.ClientRegistration;
import org.springframework.security.oauth2.client.registration.ClientRegistrationRepository;
import org.springframework.security.oauth2.client.registration.ClientRegistrations;
import org.springframework.security.oauth2.client.registration.InMemoryClientRegistrationRepository;
import org.springframework.security.oauth2.core.AuthorizationGrantType;
import org.springframework.security.oauth2.core.ClientAuthenticationMethod;

@Configuration
class ClientRegistrationConfig {

    @Bean
    ClientRegistrationRepository clientRegistrationRepository() {
        ClientRegistration publicClient = ClientRegistrations
            .fromIssuerLocation("http://localhost:9000/realms/training")
            .registrationId("learning-public")
            .clientId("learning-public")
            .clientAuthenticationMethod(ClientAuthenticationMethod.NONE)
            .authorizationGrantType(AuthorizationGrantType.AUTHORIZATION_CODE)
            .redirectUri("{baseUrl}/login/oauth2/code/{registrationId}")
            .scope("openid", "profile")
            .build();

        return new InMemoryClientRegistrationRepository(publicClient);
    }
}
```

Ví dụ này chỉ minh họa một registration; cần OP thực tế có metadata OIDC hợp lệ và public client registration đúng. `ClientRegistrations.fromIssuerLocation(...)` dùng discovery để lấy endpoint phù hợp và có thể cần OP sẵn sàng lúc tạo bean.

**Lưu ý khi tự tạo repository:** nếu ứng dụng tự cung cấp bean `ClientRegistrationRepository`, Spring Boot có thể nhường quyền tạo repository từ `application.yml`. Khi đó cần bảo đảm mọi registration của ứng dụng vẫn được thêm vào repository do bạn quản lý; không chỉ tạo một public registration rồi vô tình làm mất các Client khác.

## 11. So sánh public và confidential bằng hai registrations

Để nhìn rõ Token Endpoint behavior, cấu hình hai Client registrations trỏ tới cùng issuer nhưng có cách xác thực Client khác nhau.

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          demo-public:
            provider: training
            client-id: learning-public
            client-authentication-method: none
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]

          demo-server:
            provider: training
            client-id: learning-confidential
            client-secret: ${DEMO_SERVER_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]

        provider:
          training:
            issuer-uri: http://localhost:9000/realms/training
```

Đăng ký **hai Clients** ở OP:

| Thuộc tính | `demo-public` | `demo-server` |
|---|---|---|
| Loại Client phía OP | Public | Confidential |
| Client ID | `learning-public` | `learning-confidential` |
| Client secret trong Spring | Không | Có, qua secret store |
| `client-authentication-method` | `none` | `client_secret_basic` |
| PKCE | Cần được bật/cưỡng chế | Nên dùng theo thực hành hiện đại |
| Redirect URI | `/login/oauth2/code/demo-public` | `/login/oauth2/code/demo-server` |
| Browser login URL | `/oauth2/authorization/demo-public` | `/oauth2/authorization/demo-server` |
| Token Endpoint | Không trình Client secret | Có client authentication theo cấu hình |

Cùng OP không có nghĩa hai Clients dùng chung token, quyền hoặc cơ chế xác thực. Registration ID còn ảnh hưởng callback và việc lưu `OAuth2AuthorizedClient` trong Spring Security.

### 11.1. So sánh tại Token Endpoint

Với `demo-public`:

- Token request dựa vào authorization code và PKCE verifier.
- Không có Client secret hoặc Basic credentials.
- Authorization Server đối chiếu client ID, code, redirect và PKCE.

Với `demo-server`:

- Client trình Client authentication credential được yêu cầu, ví dụ HTTP Basic.
- Token request vẫn phải có authorization code hợp lệ và redirect phù hợp.
- PKCE có thể tiếp tục được dùng để bảo vệ code.

**Không nên** kết luận “confidential client không cần PKCE” hoặc “public client dùng PKCE thì đã được xác thực như confidential client”. Chúng là hai cơ chế có mục tiêu khác nhau.

## 12. Spring MVC web app và SPA: cùng OAuth 2.0 nhưng khác nơi giữ token

Một lỗi thiết kế thường gặp là cấu hình Spring Boot backend với `none` rồi gọi hệ thống đó là “SPA public client”, dù browser không trực tiếp chạy OAuth Client.

### 12.1. Mô hình Spring MVC truyền thống

```text
Browser
  |
  | cookie session
  v
Spring Boot MVC (OAuth2 Client)
  |                       ^
  | authorization code     | tokens
  v                       |
Authorization Server / OP
```

Trong mô hình này:

- Spring Boot tạo authorization request và xử lý callback.
- Spring Boot gọi Token Endpoint qua kết nối server-to-server.
- Browser thường chỉ giữ session cookie của ứng dụng.
- Nếu backend giữ được secret an toàn, thường dùng confidential client.
- Nếu AS cho phép registration public và Spring Boot dùng `none`, đó vẫn là server-side token exchange, nhưng không dùng client authentication.

### 12.2. Mô hình browser-based public client

```text
Browser SPA
  |  \
  |   \ direct token request with code_verifier
  |    \
  v     v
Authorization Endpoint / Token Endpoint
  |
  v
Resource API (nhận access token theo chính sách)
```

Trong mô hình này:

- JavaScript chạy trong browser thực hiện phần OAuth Client.
- Client secret không thể được bảo vệ như secret server-side.
- Authorization Code + PKCE là cách phù hợp hơn implicit flow.
- OP phải hỗ trợ các yêu cầu browser phù hợp, bao gồm **CORS tại Token Endpoint** khi SPA gọi trực tiếp từ origin khác.
- Ứng dụng phải bảo vệ token khỏi XSS và quyết định chiến lược lưu trữ/phiên phù hợp.

**Chỉ cấu hình `client-authentication-method: none` trong backend Spring MVC không tự bật CORS cho Token Endpoint bên OP**, cũng không biến Spring Security Servlet login thành một JavaScript OAuth SDK.

### 12.3. Khi nào cân nhắc BFF?

Với sản phẩm có backend đáng tin cậy, BFF giúp trình duyệt chỉ dùng cookie phiên, còn backend giữ token và thực hiện những request OAuth 2.0/Resource Server cần thiết. Khi BFF có khả năng lưu credential an toàn, confidential registration là lựa chọn hợp lý.

BFF vẫn cần bảo vệ cookie, CSRF, session fixation, logout, authorization rules và XSS. Public client không tự kém an toàn trong mọi hoàn cảnh; điều quan trọng là **đúng mô hình đe dọa và chính sách token**.

## 13. Các loại ứng dụng và điều kiện dùng none

| Mô hình | Khả năng giữ Client credential | Có thể dùng `none`? | Những điều cần chuẩn bị |
|---|---|---|---|
| SPA JavaScript thuần | Không đáng tin cậy | Thường có | Authorization Code + PKCE, OP hỗ trợ CORS/token endpoint cho SPA, redirect chính xác, bảo vệ token và XSS |
| Native iOS/Android | Không thể giữ secret phân phối trong app | Thường có | External/system browser, PKCE, redirect phù hợp RFC 8252, kiểm tra điều hướng deep link |
| Desktop app phân phối cho người dùng | Không đáng tin cậy | Thường có | PKCE, loopback/URI redirect theo chính sách, bảo vệ token cục bộ |
| CLI public dùng browser/device flow | Không thể giữ shared secret | Có thể | Grant được AS hỗ trợ, PKCE với authorization code hoặc quy tắc riêng của device grant |
| Spring Boot MVC backend | Thường giữ được secret | Có thể về mặt kỹ thuật nếu AS đăng ký public, nhưng thường cân nhắc confidential | Rõ lý do sử dụng none; PKCE, session/cookie, đúng AS policy |
| BFF có server-side token storage | Thường giữ được secret | Thường không cần | Confidential client auth, cookie/session security, API proxy |
| Service-to-service daemon | Thường có danh tính máy chủ | Không phải lựa chọn điển hình để dùng `client_credentials` | Confidential client authentication phù hợp |

Public client không đồng nghĩa với “ứng dụng không đáng tin ở mọi phương diện”: người dùng vẫn có thể tin ứng dụng và OP vẫn thực hiện đăng nhập. Nó chỉ nói rằng **Client không thể chứng minh danh tính của chính nó bằng một secret tĩnh được giữ kín**.

### 13.1. Native app và redirect URI

Ứng dụng native thường dùng:

- URI scheme riêng;
- app-claimed HTTPS redirect URI (universal/app link);
- loopback redirect tới localhost trên thiết bị, theo kiểu ứng dụng.

Chọn kiểu redirect theo hệ điều hành, SDK và chính sách của Authorization Server, tham khảo RFC 8252. URI scheme riêng có thể bị ứng dụng khác đăng ký cạnh tranh; PKCE giúp giảm hậu quả khi code bị chặn nhưng không loại bỏ mọi nguy cơ. Ưu tiên system browser/external user agent thay vì nhúng WebView để đăng nhập nếu không có yêu cầu đặc biệt được hỗ trợ.

### 13.2. Device Authorization Grant

Một thiết bị không có browser tiện dụng có thể dùng OAuth 2.0 Device Authorization Grant nếu AS hỗ trợ. Public client vẫn thường không có client secret, nhưng **token request của device flow có tham số và cơ chế riêng**, không phải Authorization Code + PKCE như ví dụ chính. Đừng sao chép `grant_type=authorization_code` sang device grant.

## 14. none và các grant types khác

### 14.1. Authorization Code

Đây là trường hợp trọng tâm. Public client dùng `none` với Authorization Code + PKCE khi Authorization Server cho phép.

### 14.2. Client Credentials

Grant `client_credentials` thông thường dành cho Clients xác thực danh tính của chính mình với Authorization Server. **Không nên** coi `none` là phương thức phổ biến để dùng `client_credentials` vì public client không có bằng chứng xác thực Client đáng tin.

Nếu cần service-to-service authentication, sử dụng confidential client authentication phù hợp, chẳng hạn secret được quản lý an toàn, private key JWT hoặc mutual TLS theo chính sách AS.

### 14.3. Refresh Token

Public client có thể được phát refresh token nếu AS cho phép; `none` **không tự cấm** refresh token. Tuy nhiên, vì public client không có client secret, AS phải xử lý rủi ro refresh token bị sao chép/sử dụng lại.

Theo OAuth 2.0 Security Best Current Practice (RFC 9700), khi phát refresh token cho public clients, AS cần cơ chế **sender-constraining** hoặc **refresh token rotation** để phát hiện/ngăn replay theo quy định. Cũng cần ràng buộc refresh token với phạm vi/resources và chính sách thời hạn/thu hồi phù hợp.

Ở phía Client:

- Không để refresh token trong URL hoặc log.
- Tránh lưu token bền vững ở nơi có thể bị JavaScript độc hại đọc nếu kiến trúc cho phép lựa chọn an toàn hơn.
- Trên native app, dùng cơ chế lưu trữ an toàn được nền tảng hỗ trợ, không xem nó là biện pháp chống mọi loại tấn công.
- Phải xử lý `invalid_grant` khi refresh token hết hạn, bị thu hồi hoặc bị quay vòng.
- Không giả định có refresh token chỉ vì xin scope `offline_access`; chính sách và tham số tương ứng phụ thuộc OP.

### 14.4. OIDC và offline_access

Trong OIDC, `offline_access` có ngữ nghĩa riêng khi yêu cầu offline access, nhưng việc OP có cấp refresh token hay không còn phụ thuộc consent, grant, loại Client và chính sách của nhà cung cấp. Client authentication method `none` không bảo đảm có hoặc không có refresh token.

### 14.5. Implicit grant và Resource Owner Password Credentials

Không chọn implicit flow chỉ để né Token Endpoint, và không dùng Resource Owner Password Credentials làm cách chuyển password người dùng vào public client. Với ứng dụng hiện đại cần đăng nhập tương tác, ưu tiên Authorization Code + PKCE và những khuyến nghị bảo mật đang áp dụng. Việc một provider còn hỗ trợ grant cũ không làm nó thành phương án nên chọn cho thiết kế mới.

## 15. Token Endpoint trả lỗi: hiểu đúng nguyên nhân

Hai hệ thống có thể trả các mã lỗi khác nhau cho một tình huống tùy cấu hình. Khi thực hành, cần phân biệt **lỗi xác thực Client** với **lỗi grant/PKCE**.

| Biểu hiện | Nguyên nhân có thể | Hướng kiểm tra |
|---|---|---|
| `invalid_client` | AS đang yêu cầu confidential client auth, nhưng request dùng `none` | Loại registration ở AS, `client-authentication-method` trong Spring |
| `invalid_grant` | Authorization code hết hạn, đã dùng, sai Client, redirect URI hoặc PKCE verifier | Toàn bộ grant binding và PKCE transaction |
| `invalid_request` | Thiếu tham số, duplicate, sai kiểu dữ liệu | Form body, grant_type, client_id, code_verifier |
| `unauthorized_client` | Client không được phép sử dụng grant này | Chính sách grants của registration trên AS |
| `unsupported_grant_type` | AS không hỗ trợ grant được yêu cầu | Kiểm tra grant type và Token Endpoint |
| Redirect bị OP từ chối trước callback | Authorization request dùng redirect URI không đăng ký | Scheme/host/port/path và policy của AS |
| Callback thất bại vì `state` | Yêu cầu và callback không tương ứng | Session, lưu authorization request, multiple tabs, CSRF/correlation |
| Token request thiếu `code_verifier` | PKCE không được áp dụng/lưu đúng hoặc custom resolver làm mất attribute | Authorization request có challenge không; token exchange có verifier không |
| Token response không có `id_token` khi yêu cầu OIDC | OP không đáp ứng OIDC Code flow hoặc cấu hình sai | Scope `openid`, provider capability và token response contract |
| API trả 401 sau login | Access token sai/hết hạn/audience không đúng API | Resource Server verifier; khác với Client auth method ở Token Endpoint |

Các lỗi `invalid_grant` do PKCE thường không tiết lộ chính xác code hay verifier nào sai, để giảm rò rỉ thông tin. Tập trung kiểm tra cấu hình ở cả Client và Authorization Server, cùng trình tự request đã được làm sạch.

### 15.1. Đừng “sửa” invalid_client bằng cách tắt kiểm tra

Nếu một backend đã đăng ký confidential và Token Endpoint từ chối vì secret sai, việc đổi sang:

```yaml
client-authentication-method: none
```

không phải là sửa lỗi hợp lệ. Trước hết kiểm tra credential, cách gửi `client_secret_basic`/`client_secret_post` hoặc phương thức đã được đăng ký. Chỉ dùng `none` sau khi **thay đổi thiết kế Client** và đăng ký tương ứng tại AS với những bảo vệ cần thiết.

### 15.2. Không nhầm authentication của Token Endpoint với login của người dùng

Một lỗi `invalid_client` báo vấn đề xác thực Client/registration; nó không tự chứng minh người dùng nhập sai mật khẩu. Một lỗi `invalid_grant` có thể là code replay, verifier không khớp hoặc redirect URI sai dù người dùng đã đăng nhập thành công tại OP.

Phân tách các bước giúp chẩn đoán:

```text
Browser authorization request
    |
    v
OP xác thực người dùng và cấp code
    |
    v
Client gửi code + code_verifier tới Token Endpoint
    |
    +--> AS kiểm tra Client registration/auth method
    +--> AS kiểm tra code, redirect URI, PKCE
    |
    v
Token response
    |
    v
OIDC ID token validation / user principal / session
```

## 16. Quan sát request mà không để lộ bí mật

Do Token Endpoint có thể xử lý credentials, codes, verifiers và tokens, log phải được hạn chế.

**Được phép ghi vào tài liệu lab sau khi đã làm sạch:**

- registration ID và client authentication method;
- tên grant type;
- có/không có HTTP Basic authentication;
- có/không có `client_id`, `code_verifier`, `redirect_uri`;
- thông tin code challenge method `S256`;
- HTTP status hoặc OAuth error code đã rút gọn;
- issuer URI công khai của OP và URL endpoint demo khi phù hợp.

**Không ghi nguyên văn:**

- authorization code;
- code verifier;
- client secret hoặc Basic Authorization header;
- access token, refresh token, ID token;
- cookie phiên, state thực và những dữ liệu liên kết giao dịch khác;
- thông tin đăng nhập người dùng.

Với Spring Security, có thể bật DEBUG ở môi trường phát triển để quan sát filter và flow, nhưng không để log HTTP request/response bodies hoặc token-bearing headers trong môi trường có dữ liệu thật. Một số HTTP client logging/interceptor có thể ghi full form body; phải đánh giá chúng khi dùng Token Endpoint.

## 17. Thực hành A — Public client và PKCE S256

**Mục tiêu:** quan sát một registration `none` thực hiện Authorization Code + PKCE.

**Chuẩn bị:**

1. Một OP/AS chạy trong lab, hỗ trợ Authorization Code + PKCE S256.
2. Client đăng ký kiểu public với client ID `learning-public`.
3. Callback được đăng ký chính xác cho ứng dụng Spring Boot MVC ở `http://localhost:8080`.
4. Cấu hình `application.yml` ở mục 9.
5. Tài khoản người dùng thử nghiệm không chứa dữ liệu nhạy cảm.

**Các bước:**

1. Khởi động OP rồi khởi động Spring Boot.
2. Mở cửa sổ trình duyệt riêng tư, truy cập `/oauth2/authorization/learning-public`.
3. Quan sát redirect tới authorization endpoint và ghi nhận **sự có mặt** của `code_challenge` và `code_challenge_method=S256`; không sao chép giá trị thực.
4. Hoàn tất đăng nhập tại OP.
5. Quan sát callback và Token Endpoint request thông qua tracing an toàn trong môi trường lab, chỉ ghi `grant_type`, `client_id`, `redirect_uri`, việc có `code_verifier` và không có Client secret.
6. Kiểm tra ứng dụng hoàn tất OIDC login và có principal tương ứng.
7. Trở lại trang sau đăng nhập, xác nhận thao tác thông thường dùng phiên của ứng dụng, không yêu cầu đổi authorization code lần nữa cho mỗi HTTP request.

**Kết quả mong đợi:** Authorization Server chấp nhận token request không có client secret khi Client được đăng ký public và authorization code/PKCE hợp lệ. Nếu dùng OIDC, Client tiếp tục xác minh ID token trước khi xác lập danh tính người dùng.

**Câu hỏi:** Tại sao `client_id` không được coi là bí mật? Giá trị nào giúp Token Endpoint xác định bên đổi code biết verifier của giao dịch ban đầu?

## 18. Thực hành B — So sánh none và client_secret_basic

**Mục tiêu:** hiểu public/confidential khác nhau ở bước xác thực Client, không nhầm với sự kiện đăng nhập người dùng.

**Chuẩn bị:** hai registrations `demo-public` và `demo-server` trong cùng OP, đúng như mục 11.

**Các bước:**

1. Đăng nhập bằng `/oauth2/authorization/demo-public` và ghi nhận loại thông tin xác thực Client được gửi tại Token Endpoint.
2. Mở browser riêng tư mới, đăng nhập bằng `/oauth2/authorization/demo-server`.
3. Ghi nhận lần token request thứ hai sử dụng Client authentication method `client_secret_basic`.
4. So sánh scopes và ID token của hai luồng ở mức claim công khai an toàn, nếu cả hai đều dùng OIDC.
5. Kiểm tra mỗi registration có callback và Client ID riêng; không chia sẻ token qua lại.
6. Không lưu credentials thật vào ghi chép.

**Kết quả mong đợi:** cả hai có thể đăng nhập cùng một người dùng tại OP, nhưng cách Client chứng minh/không chứng minh danh tính Client ở Token Endpoint khác nhau. Trong cả hai trường hợp, authorization code phải hợp lệ và gắn với đúng registration.

## 19. Thực hành C — PKCE verifier không khớp

**Mục tiêu:** thấy Token Endpoint vẫn có cơ chế từ chối một request dùng `none` mà không sở hữu verifier đúng.

**Chuẩn bị:** Authorization Server thử nghiệm cho phép quan sát request/response đã làm sạch hoặc công cụ mock OAuth2 được kiểm soát; chỉ dùng code/token giả hoặc phát hành riêng cho lab.

**Các bước:**

1. Tạo một authorization attempt hợp lệ với PKCE S256 và ghi nhận rằng AS đã lưu challenge.
2. Trong môi trường mock/lab, thực hiện token request có verifier **khác** verifier ban đầu.
3. Quan sát token endpoint từ chối bằng lỗi grant/PKCE phù hợp, thường là `invalid_grant`.
4. Thử trường hợp thiếu verifier khi challenge đã được đăng ký; quan sát AS từ chối.
5. Thực hiện luồng mới hoàn chỉnh bằng verifier đúng thông qua framework để so sánh.
6. Không gửi raw verifier hoặc authorization code vào log dùng chung.

**Kết quả mong đợi:** AS không phát token cho code bị trình kèm verifier sai. Giá trị `client_id` đúng đơn thuần không đủ để vượt qua PKCE.

**Câu hỏi:** Vì sao code bị chặn không tự đủ để lấy token khi PKCE được cưỡng chế? Vì sao phải tạo verifier mới cho mỗi lần ủy quyền?

## 20. Thực hành D — Public client đăng ký nhầm kiểu

**Mục tiêu:** chẩn đoán lỗi contract giữa Client và Authorization Server.

**Các bước:**

1. Đăng ký một Client lab dạng confidential, yêu cầu `client_secret_basic`.
2. Cấu hình Spring registration cho đúng loại confidential và chạy baseline thành công.
3. Tạm đổi **chỉ phía Spring** thành `client-authentication-method: none` và bỏ secret.
4. Thực hiện login mới; ghi nhận Token Endpoint từ chối theo chính sách AS.
5. Khôi phục cấu hình confidential ban đầu.
6. Tạo **registration mới** dạng public ở AS; cấu hình Spring dùng `none` và PKCE, sau đó thực hiện một luồng hợp lệ.

**Kết quả mong đợi:** thay đổi một property ở Spring không sửa được loại Client đã đăng ký ở AS. Phương thức Client authentication phải nhất quán giữa hai bên.

## 21. Thực hành E — Thiết kế theo kiến trúc

**Mục tiêu:** chọn cách dùng `none` theo loại ứng dụng thực tế.

Hãy phân tích bốn yêu cầu:

| Bài toán | Phương án nên cân nhắc | Lý do |
|---|---|---|
| Ứng dụng mobile đăng nhập nhân viên | Public Client + Authorization Code + PKCE | Secret phân phối trong app không đáng tin |
| Website chỉ có Spring MVC backend và server-side session | Confidential Client + Authorization Code, nên dùng PKCE | Backend có thể bảo vệ credential và token |
| SPA trực tiếp trao đổi code tại Token Endpoint | Public Client + PKCE, CORS/phòng chống XSS phù hợp | Browser không bảo vệ secret; token exchange trực tiếp cần OP hỗ trợ |
| Backend scheduler gọi API không có người dùng | Confidential client với grant và client authentication phù hợp, ví dụ client_credentials | Không phải tương tác đăng nhập người dùng |

**Câu hỏi phân tích:**

1. Code và token được giữ tại đâu?
2. Bí mật Client có thể được bảo vệ khỏi người dùng cuối hay không?
3. Authorization Server hỗ trợ loại registration và grant nào?
4. PKCE được tạo, lưu, truyền và kiểm tra bởi thành phần nào?
5. Browser có trực tiếp gọi Token Endpoint hay dùng backend?
6. Token được lưu ở đâu, có cần refresh token và cơ chế chống replay nào?
7. Khi nào cần cookie/session, CSRF, XSS và CORS protection?

Không chọn `none` chỉ vì “ít trường cấu hình hơn”; chọn nó khi kiến trúc phù hợp và Authorization Server thực thi các điều kiện tương ứng.

## 22. Các nhầm lẫn phổ biến

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| “none nghĩa là không có bảo mật.” | Chỉ là không xác thực **Client bằng credential** tại Token Endpoint; grant, PKCE, redirect, scopes và token validation vẫn cần. |
| “Có client_id là đã xác thực Client.” | Client ID là định danh công khai, không phải bằng chứng sở hữu secret. |
| “PKCE biến public client thành confidential.” | PKCE bảo vệ authorization code exchange, không làm mã được phân phối giữ được client secret. |
| “Public client không bao giờ có refresh token.” | Có thể được cấp theo chính sách AS; cần cơ chế chống replay phù hợp. |
| “Spring Boot có none nên token endpoint sẽ không yêu cầu PKCE.” | PKCE là biện pháp phải được hai phía dùng và AS cưỡng chế; none không thay PKCE. |
| “Một backend Spring Boot luôn phải dùng none nếu SPA có JavaScript.” | Nếu backend là OAuth Client và bảo vệ được secret, có thể là confidential; tùy nơi thực hiện token exchange. |
| “Client secret nhúng trong mobile app là an toàn vì được obfuscate.” | Secret tĩnh được phân phối tới thiết bị có thể bị trích xuất; obfuscation không biến public thành confidential. |
| “Token Endpoint nhận code thì không cần redirect URI hoặc Client ID.” | Các ràng buộc Client, redirect và grant phải được kiểm tra đúng giao thức. |
| “none dùng được cho client_credentials thông thường.” | Grant máy–máy cần xác thực danh tính Client theo chính sách; none không phải lựa chọn mặc định. |
| “Không có Basic Authorization header nghĩa là token request sai.” | Với public client được đăng ký none, token request không có Basic credential là đúng. |
| “CORS thay cho PKCE.” | CORS là chính sách browser cross-origin; PKCE bảo vệ authorization code exchange. |
| “ID token và access token có thể dùng thay nhau.” | ID token xác nhận danh tính với Client; access token cấp quyền truy cập Resource Server. |

## 23. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao một APK chứa client secret không được xem là confidential client chỉ vì secret được mã hóa hoặc obfuscate?

*Gợi ý:* người cài ứng dụng có thể phân tích mã và trích xuất dữ liệu phân phối cùng ứng dụng.

**Câu 2.** Với `client-authentication-method: none`, Token Endpoint có phải bỏ qua `client_id` không?

*Gợi ý:* không; AS cần định danh Client registration và kiểm tra authorization code được cấp cho đúng Client.

**Câu 3.** PKCE gửi `code_challenge` hay `code_verifier` trong authorization request?

*Gợi ý:* chỉ challenge đi qua browser; verifier dùng ở token request.

**Câu 4.** Tại sao `code_verifier` phải gắn với từng authorization transaction?

*Gợi ý:* Token Endpoint phải so khớp với challenge của đúng code; dùng chung hoặc sinh lại có thể gây rủi ro/không khớp.

**Câu 5.** Một Spring Boot backend có thể giữ Client secret trong secret manager. Có nên chuyển ngay sang `none` chỉ vì Token Endpoint báo `invalid_client`?

*Gợi ý:* không; kiểm tra registration và cơ chế xác thực Client trước, chỉ chuyển public khi thiết kế và AS policy phù hợp.

**Câu 6.** Khi SPA gọi Token Endpoint trực tiếp, còn điều kiện browser nào ngoài OAuth PKCE?

*Gợi ý:* OP phải hỗ trợ CORS cần thiết; ứng dụng phải giảm XSS/token exposure và quản lý redirect/origin an toàn.

**Câu 7.** Refresh token cho public client có bị cấm hoàn toàn không?

*Gợi ý:* không; nhưng AS phải áp dụng chống replay như rotation hoặc sender-constraining theo khuyến nghị/chuẩn hiện hành.

**Câu 8.** `none` ở Token Endpoint có nghĩa người dùng không phải đăng nhập tại OP không?

*Gợi ý:* không; client authentication và user authentication là hai bước khác nhau.

**Câu 9.** Ứng dụng dùng `openid` và `none`, sau token exchange phải làm gì với ID token?

*Gợi ý:* xác minh issuer, audience, chữ ký, thời hạn và các điều kiện OIDC cần thiết trước khi tạo danh tính.

**Câu 10.** Một public client dùng grant `client_credentials` mà không trình credentials có phải kiến trúc máy–máy phù hợp điển hình không?

*Gợi ý:* không; thiết kế service-to-service cần xác thực Client theo cơ chế mà AS tin cậy.

## 24. Tài liệu tham khảo

- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): phân loại Client, Authorization Code Grant, Token Endpoint và nghĩa của client authentication.
- [RFC 7636 — Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): cách sinh `code_verifier`, `code_challenge` và kiểm tra PKCE.
- [RFC 8252 — OAuth 2.0 for Native Apps](https://www.rfc-editor.org/rfc/rfc8252): public native clients, redirect URI và khuyến nghị dùng browser ngoài ứng dụng.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://www.rfc-editor.org/rfc/rfc9700): bảo vệ authorization code, PKCE, refresh token và các biện pháp chống replay.
- [OAuth 2.0 for Browser-Based Applications](https://datatracker.ietf.org/doc/draft-ietf-oauth-browser-based-apps/): hướng dẫn kiến trúc SPA và BFF; cần kiểm tra trạng thái phiên bản tiêu chuẩn đang áp dụng.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): OIDC Authorization Code flow, ID token và client authentication considerations.
- [Spring Security — OAuth 2.0 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html): `ClientRegistration` và cơ chế OAuth 2.0 Client trên Servlet.
- [Spring Security — OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): redirect, callback và OIDC login.
- [Spring Security — Advanced OAuth 2.0 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): cấu hình authorization endpoint, token endpoint và PKCE customization.
- [Spring Security API — ClientAuthenticationMethod](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/core/ClientAuthenticationMethod.html): các giá trị method, bao gồm `NONE`.
- [Spring Security API — DefaultOAuth2AuthorizationRequestResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/client/web/DefaultOAuth2AuthorizationRequestResolver.html): resolver mặc định tạo authorization request và PKCE.

**Điểm cần ghi nhớ:** public client dùng `client-authentication-method: none` vì nó không thể bảo vệ một Client credential dùng chung. Authorization Server vẫn phải nhận biết Client và kiểm tra chặt chẽ authorization code, redirect URI và PKCE. Với Spring Security, cấu hình `none` phải đi cùng registration public tương ứng tại OP và luồng Authorization Code + PKCE được bảo vệ. Khi backend có thể giữ Client secret an toàn, hãy cân nhắc confidential client theo kiến trúc thực tế; không dùng `none` như một lối tắt vượt qua lỗi xác thực Client.
