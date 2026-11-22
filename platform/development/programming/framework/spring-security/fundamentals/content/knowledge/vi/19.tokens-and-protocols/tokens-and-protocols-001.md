# Token là gì và phân biệt Bearer token với thông tin mật khẩu

Khi người dùng đăng nhập một ứng dụng web, họ có thể dùng **mật khẩu** để chứng minh quyền kiểm soát tài khoản. Sau khi xác thực, một hệ thống khác có thể cấp **access token**, và client sử dụng token đó để truy cập API mà không gửi lại mật khẩu trong mỗi request. Cách sử dụng phổ biến là HTTP header `Authorization: Bearer <access-token>`.

Sự khác biệt này rất quan trọng với Spring Security. Bộ lọc xác thực bằng mật khẩu phải kiểm tra một loại credential; bộ lọc OAuth2 Resource Server phải kiểm tra một loại credential khác. Một mật khẩu không tự trở thành Bearer token chỉ vì được đặt sau chữ `Bearer`. Ngược lại, Bearer token vẫn là một bí mật nguy hiểm nếu rò rỉ: người sở hữu token hợp lệ có thể dùng những quyền mà token còn cho phép.

Bài thuộc nhóm **Token và giao thức** của **Spring Security - fundamentals**. Ta sẽ tìm hiểu định nghĩa token, HTTP Basic so với Bearer, OAuth2 access token, JWT/opaque token, scope/issuer/audience, cách Spring Security xác minh token và các thực hành bảo mật. Ví dụ sử dụng Java 17+, Spring Boot 3.3.x, Spring Security 6.3.x với Spring MVC/Servlet.

## 1. Token là gì?

**Token** trong bảo mật là một giá trị đại diện cho thông tin xác thực, phiên, quyền truy cập hoặc một sự kiện/ủy quyền theo giao thức của hệ thống phát hành. Không phải mọi token đều giống nhau:

- **Session ID** thường giúp máy chủ tìm trạng thái phiên đã lưu, chẳng hạn sau form login.
- **OAuth2 access token** được client gửi cho Resource Server để gọi tài nguyên được bảo vệ.
- **Refresh token** được dùng với Authorization Server để yêu cầu access token mới.
- **OpenID Connect ID token** truyền thông tin về việc xác thực người dùng cho OIDC client.
- **CSRF token** được dùng để bảo vệ request có tác dụng thay đổi trạng thái trong một số ứng dụng trình duyệt.

Từ “token” tự nó **không** chứng minh token có dạng JWT, không chứng minh token có thể đăng nhập, và không chứng minh token được phép truy cập API bất kỳ.

Trong OAuth2, ba vai trò thường thấy:

~~~text
Người dùng / chủ sở hữu tài nguyên
             |
             | xác thực/cấp phép qua flow thích hợp
             v
Authorization Server (hệ thống cấp token)
             |
             | access token
             v
Client (ứng dụng)
             |
             | Authorization: Bearer <access-token>
             v
Resource Server (API)
             |
             | xác thực token + kiểm tra quyền
             v
Tài nguyên được bảo vệ
~~~

Luồng thực tế phụ thuộc OAuth2 grant. Với `client_credentials`, access token có thể đại diện một ứng dụng/dịch vụ chứ không phải một người dùng cuối. Hệ thống có token cũng không mặc nhiên phải sử dụng mật khẩu; có thể dùng passkey, đăng nhập liên kết hoặc một hình thức xác thực khác.

## 2. Khác nhau giữa mật khẩu và Bearer access token

| Tiêu chí | Mật khẩu người dùng | Bearer access token |
| --- | --- | --- |
| Vai trò | Một bí mật dùng để chứng minh danh tính trong quy trình xác thực | Credential dùng để gọi API trong phạm vi quyền được cấp |
| Nơi thường được xử lý | Hệ thống đăng nhập/Identity Provider | Resource Server được phép nhận token |
| Ai có thể tạo? | Người dùng/hệ thống định danh theo quy trình thiết lập mật khẩu | Authorization Server hoặc bên cấp token được tin cậy |
| Chu kỳ sống | Thường tồn tại đến khi đổi/đặt lại hoặc bị vô hiệu | Thường có thời hạn giới hạn và có thể có cơ chế thu hồi |
| Phạm vi quyền | Bản thân mật khẩu không mô tả scope của API | Token hoặc kết quả tra cứu có thể gắn scope, audience, resource |
| Khi bị lộ | Kẻ xấu có thể cố dùng để đăng nhập tại nơi còn chấp nhận mật khẩu | Kẻ xấu có thể dùng token theo quyền còn hiệu lực |
| Thay đổi/hủy | Đổi mật khẩu, khóa tài khoản, xử lý phiên liên quan | Hết hạn, thu hồi, introspection, thay khóa hoặc chính sách khác |
| Kiểm tra ở Spring Security | `PasswordEncoder` trong cơ chế mật khẩu phù hợp | `JwtDecoder` hoặc `OpaqueTokenIntrospector` trong Resource Server |

**Mật khẩu và Bearer token đều cần được bảo vệ.** Bearer token là credential theo mô hình *ai cầm được token thì dùng được quyền gắn với nó*, không có bước bắt buộc chứng minh thêm quyền sở hữu khóa như một token *proof-of-possession*. Nếu token bị đánh cắp, server không tự biết request đến từ thiết bị/người sở hữu ban đầu.

### Token có thay thế hoàn toàn mật khẩu không?

Không nhất thiết. Một ứng dụng có thể dùng mật khẩu khi đăng nhập tại IdP, nhưng dùng access token khi gọi API. Các ứng dụng khác không yêu cầu mật khẩu truyền thống. Điều quan trọng là **giao thức và endpoint**: hệ thống đăng nhập nhận credential để xác thực; API Resource Server nhận access token theo hợp đồng của chính nó.

### Có cần gửi username/password mỗi lần gọi API?

Không đối với một API thiết kế theo access token: client dùng Bearer token ở request truy cập API. Với HTTP Basic thì username/password có thể được trình bày lại ở mỗi request; đó là cơ chế riêng và cần HTTPS. Không tự xây giải pháp “gửi password ở mọi request rồi tự sinh token” khi đã có những thành phần xác thực và giao thức chuẩn.

## 3. Authorization: Basic và Authorization: Bearer

HTTP header `Authorization` chứa **authentication scheme** cùng credential. Cùng một header nhưng tiền tố khác nhau dẫn đến cách giải mã/kiểm tra khác nhau.

~~~http
GET /api/profile HTTP/1.1
Host: api.example.test
Authorization: Basic bGFuOmRlbW8xMjM=
~~~

Với HTTP Basic, chuỗi trên thường là dạng Base64 của `username:password`, ở đây là `lan:demo123`. **Base64 không phải mã hóa bảo mật**. Người đọc header có thể giải mã lấy lại tên và mật khẩu.

~~~http
GET /api/profile HTTP/1.1
Host: api.example.test
Authorization: Bearer example-access-token
~~~

Với Bearer, chuỗi sau từ `Bearer` là token đã được hệ thống phù hợp phát hành. Nó không mặc nhiên chứa username/password và không thể được Resource Server xem là hợp lệ chỉ vì có tiền tố Bearer.

| Header | Cách hiểu |
| --- | --- |
| `Authorization: Basic <base64(user:password)>` | Credential của HTTP Basic, phải được bộ xử lý Basic kiểm tra |
| `Authorization: Bearer <token>` | Bearer token được bộ xử lý Resource Server kiểm tra |
| Không có Authorization | Request không mang credential tại header này; có thể anonymous hoặc dùng session/cơ chế khác |
| `Authorization: Bearer demo123` với `demo123` là mật khẩu | Không phải một access token hợp lệ nếu token issuer không thực sự cấp chuỗi đó |
| `Authorization: Basic ...` tới API chỉ cấu hình Bearer | Không được tự động chuyển thành Bearer và thường không xác thực được |

### Ví dụ Java 17+ chạy độc lập: Base64 không phải mã hóa

Lưu tệp `Base64BasicDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class Base64BasicDemo {
    public static void main(String[] args) {
        String demoCredentials = "lan:demo123";

        String encoded = Base64.getEncoder().encodeToString(
                demoCredentials.getBytes(StandardCharsets.UTF_8)
        );

        String decoded = new String(
                Base64.getDecoder().decode(encoded),
                StandardCharsets.UTF_8
        );

        System.out.println(encoded);
        System.out.println(decoded);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac Base64BasicDemo.java
java Base64BasicDemo
~~~

Stdout chính xác của chương trình mẫu:

~~~text
bGFuOmRlbW8xMjM=
lan:demo123
~~~

Đây là **bí mật giả để học**, không phải credential thật. Đừng log thông tin đăng nhập trong ứng dụng sản xuất. Mục đích của ví dụ là chứng minh Base64 có thể đảo ngược, không chứng minh HTTP Basic là cách lưu mật khẩu an toàn. Giao thức cần HTTPS và lưu mật khẩu phía server bằng bộ băm thích hợp, ví dụ BCrypt thông qua `PasswordEncoder`.

## 4. “Bearer” mô tả cách dùng, không mô tả định dạng token

Theo RFC 6750, Bearer token được sử dụng bằng cách trình bày giá trị token để nhận quyền truy cập, **không buộc bên sử dụng chứng minh đang giữ một khóa mật mã tương ứng**. Vì vậy, một bản sao token bị lộ có thể bị phát lại trong thời hạn còn hợp lệ.

Ba khái niệm thường bị trộn:

1. **Bearer**: mô hình sử dụng token, người có token có thể sử dụng nó theo quyền được cấp.
2. **JWT**: một định dạng token có cấu trúc claims, thường được ký số; không phải mọi JWT là access token.
3. **Opaque token**: token mà Resource Server không suy ra thông tin tin cậy chỉ bằng cách đọc chuỗi; thường cần tra cứu/introspection.

Một **JWT được ký** có thể được gửi như Bearer token. Một **opaque token** cũng có thể được gửi theo Bearer. Ngoài ra, có những cơ chế token gắn khóa/thiết bị (mTLS-bound, DPoP) nhằm chống phát lại bằng cách yêu cầu thêm bằng chứng sở hữu khóa; đó không còn là Bearer thuần túy.

### Vì sao HTTPS vẫn cần dù JWT đã có chữ ký?

Chữ ký JWT giúp phát hiện token bị sửa trái phép; **chữ ký không ngăn kẻ tấn công tái sử dụng nguyên token** nếu đã đánh cắp được. TLS/HTTPS bảo vệ kênh truyền; ngoài TLS còn phải tránh rò rỉ từ log, browser script, extension, malware và nơi lưu trữ token.

## 5. Access token, refresh token và ID token

| Loại token | Đối tượng xử lý chính | Mục tiêu |
| --- | --- | --- |
| **Access token** | Resource Server/API | Cho phép gọi tài nguyên theo quyền/phạm vi được cấp |
| **Refresh token** | Authorization Server | Xin cấp access token mới theo chính sách |
| **ID token** (OpenID Connect) | OIDC client | Chứa thông tin về sự kiện xác thực người dùng |

**Không gửi ID token thay access token để gọi API chỉ vì cả hai ở dạng JWT.** JWT có thể có chữ ký và `sub` hợp lệ nhưng được phát hành cho một audience/mục đích khác. Resource Server cần xác định token dành cho mình và được phép dùng làm credential truy cập tài nguyên.

Refresh token thường nhạy cảm vì có thể được dùng để nhận access token mới. Nó không nên được đưa vào header Authorization gửi cho API tài nguyên thông thường. Một token hết hạn cũng không nên được chấp nhận chỉ vì client đang giữ refresh token ở chỗ khác; client phải đi qua quy trình refresh hợp lệ.

### Dùng password để lấy token có phải là cách chuẩn cho mọi ứng dụng?

Không. Các luồng hiện đại như **Authorization Code + PKCE** cho phép người dùng xác thực tại hệ thống định danh mà client không phải trực tiếp thu thập mật khẩu người dùng. Với service-to-service, có thể dùng `client_credentials`. Luồng Resource Owner Password Credentials, nơi client thu thập password rồi xin token trực tiếp, không được khuyến nghị cho thiết kế mới. Không tự phát minh giao thức đổi password lấy token nếu có thể sử dụng IdP và OAuth2/OIDC phù hợp.

## 6. JWT và opaque token được kiểm tra thế nào?

### 6.1. JWT

Một JWT JWS compact thường có ba phần:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Payload minh họa, **không phải token đã được phát hành hay ký**:

~~~json
{
  "iss": "https://id.example.test/issuer",
  "sub": "lan",
  "aud": ["profile-api"],
  "scope": "profile.read",
  "iat": 1730000000,
  "exp": 1730003600
}
~~~

Ý nghĩa những claims phổ biến:

- `iss`: tổ chức hoặc máy chủ phát hành.
- `sub`: chủ thể được token đề cập; không mặc định là người dùng cuối.
- `aud`: hệ thống đích mà token được phát hành cho.
- `exp`: thời điểm hết hạn.
- `nbf`: thời điểm không được sử dụng trước đó.
- `iat`: thời điểm phát hành.
- `scope`/`scp`: phạm vi quyền, tùy cách Authorization Server biểu diễn.

**Giải mã JWT thành JSON không có nghĩa là JWT hợp lệ.** Phải xác minh chữ ký với khóa/thuật toán được tin cậy, xác minh các claims và quyền. JWT ký số dạng JWS thông thường **không mã hóa payload**: ai cầm chuỗi token thường có thể đọc nội dung sau khi giải mã Base64URL. Không lưu bí mật như mật khẩu, mã OTP hay khóa API vào payload JWT.

### 6.2. Opaque token

Một opaque token có thể là chuỗi không có cấu trúc công khai:

~~~text
T0k3n-opaque-random-example-12ab34
~~~

Resource Server thường cần gọi **introspection endpoint** hoặc một dịch vụ/kho được tin cậy để biết token còn hiệu lực và nó có những quyền gì. Spring Security hỗ trợ `OpaqueTokenIntrospector` cho hướng này.

| Tiêu chí | JWT được ký | Opaque token |
| --- | --- | --- |
| Hình dạng thường gặp | Có payload và chữ ký theo cấu trúc | Chuỗi khó suy ra ý nghĩa |
| Kiểm tra phổ biến | `JwtDecoder` xác minh chữ ký, claims | `OpaqueTokenIntrospector` tra cứu/introspection |
| Truy cập mạng mỗi request | Có thể không cần cho kiểm tra chữ ký nếu đã có khóa | Có thể cần introspection, tùy cache/hạ tầng |
| Thu hồi trước hạn | Cần chiến lược ngoài chữ ký/exp nếu xác thực offline | Có thể phản ánh qua introspection theo chính sách |
| Có thể làm Bearer token? | Có | Có |
| Có cần giữ bí mật? | Có | Có |

Không có loại nào tự động an toàn hơn chỉ nhờ định dạng. TTL, scope, audience, chiến lược khóa, hạ tầng kiểm tra và nơi lưu trữ quyết định nhiều rủi ro thực tế.

## 7. Resource Server xác thực token khác cơ chế password

Hãy tách hai tuyến:

~~~text
ĐĂNG NHẬP BẰNG MẬT KHẨU               GỌI API BẰNG BEARER
username/password                      Authorization: Bearer <access-token>
       |                                            |
       v                                            v
AuthenticationManager                   BearerTokenAuthenticationFilter
       |                                            |
Password-based AuthenticationProvider                v
       |                                JwtAuthenticationProvider
UserDetailsService + PasswordEncoder                 |
       |                                         JwtDecoder
       v                                            |
Authentication thành công                           v
                                        JwtAuthenticationToken
                                                   |
                                                   v
                                           AuthorizationManager
                                                   |
                                           Kiểm tra scope/quyền
~~~

Với HTTP Basic hay form login, password provider thường lấy thông tin tài khoản và sử dụng `PasswordEncoder` để so khớp mật khẩu với bản băm được lưu. API Resource Server sử dụng Bearer token thì kiểm tra token bằng `JwtDecoder` hoặc introspection; nó không tự kiểm mật khẩu người dùng.

Các bước Spring Security thường thực hiện với JWT Resource Server:

1. `BearerTokenAuthenticationFilter` trích token từ header `Authorization`.
2. Token được chuyển đến `AuthenticationManager` và `JwtAuthenticationProvider` phù hợp.
3. `JwtDecoder` xác minh token theo cấu hình tin cậy, chẳng hạn chữ ký, thời hạn, issuer.
4. `JwtAuthenticationConverter` ánh xạ claims như `scope` thành authorities, mặc định thường có tiền tố `SCOPE_`.
5. `AuthorizationFilter` xét đường dẫn, HTTP method, authority và các chính sách khác.
6. Controller chỉ được chạy nếu request vượt qua các lớp kiểm tra cần thiết.

Ví dụ JWT mang scope `profile.read` thường tạo authority `SCOPE_profile.read`. Quy tắc:

~~~java
.requestMatchers(HttpMethod.GET, "/api/profile")
    .hasAuthority("SCOPE_profile.read")
~~~

khác quy tắc:

~~~java
.requestMatchers(HttpMethod.POST, "/api/profile")
    .hasAuthority("SCOPE_profile.write")
~~~

Một token đã xác thực nhưng chỉ có scope đọc vẫn không được phép ghi. Cùng người dùng có quyền đọc và quyền ghi cũng chưa mặc định được phép sửa hồ sơ của người khác; phải kiểm tra quyền theo tài nguyên.

### Chữ ký đúng chưa đủ

Một JWT có chữ ký hợp lệ nhưng issuer không tin cậy, đã hết hạn hoặc audience hướng đến một API khác **không nên được chấp nhận**. Spring Security có kiểm tra mặc định về các thuộc tính nhất định, nhưng **không được mặc định audience luôn được kiểm tra chỉ vì đã khai báo issuer-uri**. Hãy thêm audience validator/cấu hình tương ứng với phiên bản Spring Boot và yêu cầu của API.

## 8. Ví dụ Spring Boot 3.3: API chỉ nhận Bearer JWT

Ví dụ gồm một ứng dụng có `GET /api/profile` và `POST /api/profile`. API dùng Bearer token và không bật HTTP Basic/form login. Resource Server **chỉ xác minh token**, không cấp access token hay tạo trang đăng nhập.

Cấu trúc:

~~~text
bearer-token-demo/
├── settings.gradle
├── build.gradle
├── src/main/resources/application.yml
├── src/main/java/example/bearer/
│   ├── BearerDemoApplication.java
│   ├── SecurityConfig.java
│   └── ProfileController.java
└── src/test/java/example/bearer/
    └── BearerSecurityTest.java
~~~

### 8.1. Gradle

Tệp `settings.gradle`:

~~~groovy
rootProject.name = 'bearer-token-demo'
~~~

Tệp `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Starter OAuth2 Resource Server của Spring Boot mang các dependency được quản lý phù hợp để giải mã và kiểm tra JWT. Đừng tự trộn các phiên bản Spring Security khác nhau vào project.

### 8.2. application.yml

Tệp `src/main/resources/application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/issuer
~~~

`https://id.example.test/issuer` là **placeholder minh họa**, không phải IdP thật. Khi triển khai, phải thay bằng issuer URI được hệ thống phát hành công bố, có metadata và JWK endpoint phù hợp. Không thể gọi API thành công bằng JWT thật nếu ứng dụng không thể xác minh chữ ký với khóa tin cậy.

### 8.3. BearerDemoApplication.java

~~~java
package example.bearer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BearerDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(BearerDemoApplication.class, args);
    }
}
~~~

Lưu tại `src/main/java/example/bearer/BearerDemoApplication.java`. Các class sau đặt trong cùng package.

### 8.4. SecurityConfig.java

~~~java
package example.bearer;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/profile")
                    .hasAuthority("SCOPE_profile.read")
                .requestMatchers(HttpMethod.POST, "/api/profile")
                    .hasAuthority("SCOPE_profile.write")
                .anyRequest().denyAll()
            )
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Giải thích cẩn thận:

- `oauth2ResourceServer(...jwt(...))` cho Spring Security nhận Bearer JWT. Nó **không cấp token** và **không lấy mật khẩu từ Authorization header**.
- `STATELESS` nghĩa là không sử dụng phiên HTTP làm nơi lưu SecurityContext cho các request API; client trình bày token ở mỗi request.
- `csrf.disable()` trong **ví dụ API thuần Bearer header không dùng cookie phiên** được chọn vì request trình duyệt từ site khác không tự động có Bearer token trong header. **Không áp dụng dòng này cho ứng dụng có form login, session cookie hoặc credential tự động được browser gửi** nếu chưa đánh giá nguy cơ CSRF.
- `hasAuthority("SCOPE_profile.read")` và `SCOPE_profile.write` phân biệt đọc/ghi.
- `anyRequest().denyAll()` từ chối mọi request khác, kể cả khi đã có token hợp lệ.

### 8.5. ProfileController.java

~~~java
package example.bearer;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/profile")
public class ProfileController {

    @GetMapping
    public String read(Authentication auth) {
        return "profile:" + auth.getName();
    }

    @PostMapping
    public ResponseEntity<String> update() {
        return ResponseEntity.status(HttpStatus.ACCEPTED).body("updated");
    }
}
~~~

Controller là mẫu, không ghi dữ liệu thật. Với JWT có claim `sub=lan` và converter mặc định, tên authentication thường là `lan`.

### 8.6. Gọi API

Sau khi có một access token thật được IdP của hệ thống phát hành:

~~~bash
curl -i -H "Authorization: Bearer ACCESS_TOKEN_FROM_IDP" \
  http://localhost:8080/api/profile
~~~

`ACCESS_TOKEN_FROM_IDP` là ký hiệu, không phải token đã ký. Trong sản phẩm, không ghi token vào chat, tài liệu công khai, shell history hoặc log. Ví dụ chỉ chạy với IdP/key/token phù hợp; phần test tiếp theo **mock decoder** nên không cần IdP thật để kiểm tra đường đi qua filter và quy tắc quyền.

## 9. Kiểm thử HTTP Bearer và phạm vi quyền bằng MockMvc

Tệp `src/test/java/example/bearer/BearerSecurityTest.java`. Ví dụ dùng `@MockBean` có trong Spring Boot 3.3.x để thay decoder thật bằng decoder giả, cho phép tập trung kiểm tra `Authorization: Bearer` và authorization rules.

~~~java
package example.bearer;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BearerSecurityTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    JwtDecoder decoder;

    private Jwt token(String value, String subject, String scope) {
        return Jwt.withTokenValue(value)
                .header("alg", "RS256")
                .claim("sub", subject)
                .claim("scope", scope)
                .build();
    }

    @BeforeEach
    void prepare() {
        when(decoder.decode("read-token"))
                .thenReturn(token("read-token", "lan", "profile.read"));
        when(decoder.decode("write-token"))
                .thenReturn(token("write-token", "lan", "profile.write"));
        when(decoder.decode("invalid-token"))
                .thenThrow(new BadJwtException("Invalid token"));
        when(decoder.decode("demo123"))
                .thenThrow(new BadJwtException("Password is not an access token"));
    }

    @Test
    void missingBearerReturns401() throws Exception {
        mvc.perform(get("/api/profile"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void readTokenCanRead() throws Exception {
        mvc.perform(get("/api/profile")
                .header(HttpHeaders.AUTHORIZATION, "Bearer read-token"))
                .andExpect(status().isOk())
                .andExpect(content().string("profile:lan"));
    }

    @Test
    void readTokenCannotWrite() throws Exception {
        mvc.perform(post("/api/profile")
                .header(HttpHeaders.AUTHORIZATION, "Bearer read-token"))
                .andExpect(status().isForbidden());
    }

    @Test
    void writeTokenCanWrite() throws Exception {
        mvc.perform(post("/api/profile")
                .header(HttpHeaders.AUTHORIZATION, "Bearer write-token"))
                .andExpect(status().isAccepted())
                .andExpect(content().string("updated"));
    }

    @Test
    void writeTokenCannotReadWithoutReadScope() throws Exception {
        mvc.perform(get("/api/profile")
                .header(HttpHeaders.AUTHORIZATION, "Bearer write-token"))
                .andExpect(status().isForbidden());
    }

    @Test
    void invalidTokenReturns401() throws Exception {
        mvc.perform(get("/api/profile")
                .header(HttpHeaders.AUTHORIZATION, "Bearer invalid-token"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void passwordAfterBearerKeywordIsNotAutomaticallyValid()
            throws Exception {
        mvc.perform(get("/api/profile")
                .header(HttpHeaders.AUTHORIZATION, "Bearer demo123"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void basicCredentialsDoNotAuthenticateWithBearerOnlyConfig()
            throws Exception {
        mvc.perform(get("/api/profile")
                .header(HttpHeaders.AUTHORIZATION,
                        "Basic bGFuOmRlbW8xMjM="))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void validTokenDoesNotPermitUnlistedPath() throws Exception {
        mvc.perform(get("/api/unknown")
                .header(HttpHeaders.AUTHORIZATION, "Bearer read-token"))
                .andExpect(status().isForbidden());
    }
}
~~~

Chạy:

~~~bash
./gradlew test --tests '*BearerSecurityTest'
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test --tests "*BearerSecurityTest"
~~~

**Kết quả kỳ vọng:** 9 phép thử hoàn thành thành công nếu dependency và phiên bản phù hợp. Đây là **kỳ vọng từ mã**, không phải bản ghi đã chạy test thật. Giới hạn quan trọng: `@MockBean JwtDecoder` không xác minh chữ ký RS256, thời hạn hoặc issuer/audience thật. Nó giả lập kết quả decoder để thử filter và quyền. Để kiểm tra mật mã, phải bổ sung test với JWT ký thật, khóa phù hợp và trường hợp chữ ký/claims không hợp lệ.

Trong các phiên bản Spring Boot mới hơn, API thay thế `@MockBean` có thể khác; kiểm tra dependency thực tế trước khi chuyển ví dụ.

## 10. Token hợp lệ chưa đồng nghĩa có quyền

Hai bước phải tách bạch:

1. **Authentication**: token được Resource Server chấp nhận và ánh xạ thành đối tượng `Authentication` hợp lệ.
2. **Authorization**: người dùng/client/token có authority, scope và quyền trên bản ghi phù hợp với request.

| Request | Credential | Điều kiện | Kết quả thường gặp |
| --- | --- | --- | --- |
| GET /api/profile | Không token | Cần đăng nhập | 401 |
| GET /api/profile | Token sai/hết hạn | Không vượt qua xác thực | 401 |
| GET /api/profile | Token có `profile.read` | Có `SCOPE_profile.read` | 200 nếu controller thành công |
| POST /api/profile | Token có `profile.read` | Thiếu `SCOPE_profile.write` | 403 |
| POST /api/profile | Token có `profile.write` | Có `SCOPE_profile.write` | 202 theo Controller ví dụ |
| GET /api/unknown | Token `profile.read` hợp lệ | `denyAll` | 403 |

Phản hồi Bearer thường có thể chứa `WWW-Authenticate`:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Nếu token hợp lệ nhưng thiếu scope, có thể là 403 và `error="insufficient_scope"`. Các header cụ thể phụ thuộc Spring Security config, loại lỗi và chính sách. Đừng hardcode mọi sự kiện thành một mã HTTP duy nhất.

Khi kiểm thử status, cần xem request đã bị chặn bởi lớp **authentication**, **authorization**, **CSRF**, **CORS** hay Controller. Với ví dụ bearer-only ở trên, CSRF đã được tắt có chủ đích cho API stateless; trường hợp có cookie sẽ khác.

## 11. Khóa ký, issuer, audience, exp và việc thu hồi

Một JWT hợp lệ không chỉ là chuỗi ba phần được giải mã:

- **Chữ ký** phải được kiểm tra bằng khóa tin cậy và thuật toán cho phép.
- **Issuer** (`iss`) phải là bên phát hành mà API tin tưởng.
- **Audience** (`aud`) phải phù hợp API nhận token; token dành cho dịch vụ khác không nên được chấp nhận.
- **Thời gian** như `exp` và `nbf` phải hợp lệ theo đồng hồ/độ lệch cho phép.
- **Scope** phải được chuyển thành quyền phù hợp với từng endpoint.
- **Chủ thể/tài nguyên** có thể cần kiểm tra thêm, chẳng hạn ID đơn hàng thuộc người dùng nào.
- **Thay khóa và thu hồi** phải tuân thủ chính sách của tổ chức.

Đổi mật khẩu **không mặc nhiên hủy ngay mọi JWT đã phát hành** nếu Resource Server chỉ xác minh chữ ký/exp mà không tra cứu trạng thái tài khoản. Muốn thu hồi trước hạn phải có chiến lược: token ngắn hạn, danh sách chặn, token version, introspection, thu hồi refresh token hoặc cơ chế tương đương. JWT không tự biết người dùng vừa đổi mật khẩu.

Với opaque token, introspection có thể phản ánh trạng thái thu hồi từ Authorization Server; hiệu lực còn phụ thuộc caching và vận hành. Không nói “JWT không thể thu hồi” theo nghĩa tuyệt đối; nó **cần thiết kế bổ sung** nếu phải vô hiệu hóa trước khi hết hạn.

## 12. Bảo vệ token trong hệ thống thật

### 12.1. Luôn dùng HTTPS và bảo vệ chứng chỉ

TLS bảo vệ kênh khi truyền password/Bearer. Không gửi Bearer token trong URL query như:

~~~http
GET /api/profile?access_token=SECRET_TOKEN HTTP/1.1
~~~

URL có thể xuất hiện trong history, access log, proxy log hoặc Referrer. Ưu tiên header `Authorization: Bearer` qua HTTPS. Tránh ghi Authorization, cookie, refresh token hoặc password vào log hay công cụ theo dõi lỗi.

### 12.2. Token bị rò thường bị dùng lại

Bearer token không tự gắn với trình duyệt/thiết bị. Một kẻ lấy được token có thể gọi API theo phạm vi còn hiệu lực. Giảm thiểu bằng token ngắn hạn, scope hẹp, audience hẹp, kênh truyền bảo mật, không công khai token, kiểm soát thu hồi và phát hiện bất thường.

### 12.3. Lưu token trên trình duyệt

Không có lời giải “luôn đúng” cho mọi ứng dụng:

- Token trong JavaScript memory thường biến mất khi tải lại trang, nhưng mã độc chạy trong cùng origin (XSS) vẫn có thể truy cập.
- `localStorage`/`sessionStorage` có nguy cơ khi XSS hoặc script cùng origin có quyền đọc.
- `HttpOnly` cookie làm giảm khả năng JavaScript trực tiếp đọc cookie, nhưng browser tự gửi cookie nên phải xử lý CSRF và `SameSite`/`Secure` phù hợp.
- Mô hình Backend for Frontend (BFF) có thể giữ access/refresh token phía server và chỉ dùng cookie phiên phù hợp ở browser.

**Không kết luận HttpOnly cookie loại bỏ mọi nguy cơ XSS/CSRF.** Quyết định dựa trên kiến trúc xác thực và đe dọa thực tế.

### 12.4. Bảo vệ refresh token và logout

Refresh token có thể nhận access token mới nên cần được bảo vệ nghiêm ngặt. Client không nên gửi refresh token tới Resource Server như một access token. Đăng xuất ở phía UI chỉ xóa token khỏi client; API có tiếp tục chấp nhận access token chưa hết hạn hay không tùy chính sách thu hồi ở server.

## 13. Những lỗi phổ biến cần tránh

1. **Nhầm Bearer token với mật khẩu mã hóa.** Bearer token là credential được cấp, không phải `password` bọc Base64.
2. **Nhầm JWT với Bearer.** JWT là định dạng; Bearer là mô hình sử dụng; opaque token cũng có thể là Bearer.
3. **Tin rằng Base64 của Basic là mã hóa.** Dễ giải mã, phải dùng HTTPS.
4. **Chỉ decode JWT rồi cho phép request.** Phải kiểm tra chữ ký và claims.
5. **Chỉ kiểm tra chữ ký mà bỏ qua audience.** Token có thể thuộc API khác.
6. **Xem token hợp lệ là có quyền ADMIN.** Vẫn cần scope/authority và quyền tài nguyên.
7. **Dùng ID token để gọi API thay access token.** Hai mục đích khác nhau.
8. **Gửi refresh token cho API tài nguyên.** Refresh token dành cho hệ thống cấp token theo hợp đồng.
9. **Đổi mật khẩu rồi tin mọi JWT biến mất.** Phải có chính sách thu hồi.
10. **Đưa token vào query string/log/ảnh chụp.** Có nguy cơ phát lại token bị lộ.
11. **Hardcode token hoặc password trong source.** Credential phải được quản lý như bí mật.
12. **Tắt CSRF vô điều kiện.** Chỉ quyết định theo cách browser/client thực sự gửi credential.
13. **Nhầm test mock decoder với xác minh mật mã.** Mock chỉ kiểm thử flow và quyền.
14. **Tin Bearer token được ràng buộc thiết bị.** Bearer thuần không tự có bằng chứng sở hữu khóa.
15. **Mặc định mọi token là token người dùng.** Client credentials có thể đại diện một dịch vụ.
16. **Dựa vào thông tin từ token không đúng issuer.** API phải có chính sách tin cậy rõ ràng.

## 14. Câu hỏi tự kiểm tra

**1.** HTTP header `Authorization: Basic bGFuOmRlbW8xMjM=` có phải là Bearer token không?

**Đáp án:** Không. Đó là HTTP Basic credentials được Base64, tương ứng `lan:demo123`. Base64 không bảo mật chuỗi nếu bị đọc.

**2.** API chỉ cấu hình Bearer JWT, client gửi `Authorization: Bearer demo123` với `demo123` là mật khẩu. Có thể đăng nhập không?

**Đáp án:** Không, trừ khi một hệ thống thực sự đã cấp chính chuỗi đó làm token hợp lệ theo hợp đồng; tiền tố Bearer không chuyển mật khẩu thành access token.

**3.** JWT có thể decode payload mà không có khóa. Vậy token đã hợp lệ chưa?

**Đáp án:** Chưa. Phải xác minh chữ ký, issuer, audience, thời gian và quyền.

**4.** Token có scope `profile.read` gọi POST `/api/profile` yêu cầu `profile.write` thì sao?

**Đáp án:** Bị từ chối theo policy vì thiếu `SCOPE_profile.write`, thường là 403 nếu token đã xác thực.

**5.** Một token được ký đúng bởi IdP nhưng `aud` dành cho `billing-api`. `profile-api` nên xử lý gì?

**Đáp án:** Không chấp nhận như access token dành cho mình; cần xác minh audience.

**6.** Người dùng thay mật khẩu, token JWT vẫn còn hiệu lực 10 phút. Nó có tự bị hủy ngay không?

**Đáp án:** Không mặc định. Phụ thuộc cơ chế thu hồi/kiểm tra trạng thái.

**7.** Có nên ghi `Authorization: Bearer ...` vào log để debug không?

**Đáp án:** Không ghi raw credential. Chỉ log loại lỗi, request ID và metadata đã được thiết kế an toàn.

**8.** `@MockBean JwtDecoder` trong test có chứng minh chữ ký RS256 của token thật được kiểm tra không?

**Đáp án:** Không. Nó giả lập kết quả xác minh để kiểm tra filter/policy; cần test chữ ký và claims bằng decoder thật riêng.

## 15. Checklist áp dụng với Spring Security

- Đã phân biệt rõ endpoint **đăng nhập bằng mật khẩu** với API **nhận access token** chưa?
- Đã chọn đúng HTTP scheme Basic/Bearer hoặc cơ chế khác và xác định chain áp dụng chưa?
- Đã cấu hình issuer tin cậy, khóa, thuật toán, exp, nbf và audience cho JWT chưa?
- Đã hiểu mapping `scope` sang `SCOPE_...` và kiểm tra quyền theo endpoint chưa?
- Đã có kiểm tra tài nguyên thuộc user/tổ chức phù hợp ngoài scope chưa?
- Đã tránh dùng ID token/refresh token ở sai nơi chưa?
- Đã có chính sách hết hạn, thu hồi, thay khóa, refresh token và đổi mật khẩu chưa?
- Đã có HTTPS, không ghi token trong URL/log và lưu token an toàn chưa?
- Nếu dùng browser cookie, đã đánh giá CSRF/XSS và cookie flags chưa?
- Đã kiểm thử token thiếu/sai, thiếu scope, audience sai, chữ ký sai và token hết hạn với decoder thật chưa?
- Đã xác nhận `oauth2ResourceServer` chỉ kiểm tra access token, không tự phát hành token/login bằng mật khẩu chưa?

**Nguyên tắc cần nhớ:** **Mật khẩu** thường dùng để xác thực tài khoản tại hệ thống đăng nhập; **Bearer access token** là credential để truy cập tài nguyên theo quyền được phát hành. **JWT/opaque** là những hình thức token; **Bearer** là cách trình bày và sử dụng chúng. Spring Security phải xác thực token theo issuer/key/thời gian/audience, sau đó kiểm tra scope, quyền và tài nguyên cho từng request.

## Tài liệu đối chiếu

- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://datatracker.ietf.org/doc/html/rfc6750): định nghĩa Bearer và bảo vệ token khi truyền HTTP.
- [RFC 9700 — OAuth 2.0 Security Best Current Practice](https://datatracker.ietf.org/doc/html/rfc9700): khuyến nghị về các nguy cơ OAuth2 hiện đại.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `JwtDecoder`, issuer URI và ánh xạ scope.
- [Spring Security — OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection.
- [Spring Security — Bearer Token Usage](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html): cách lấy Bearer token từ request.
- [Spring Security — HTTP Basic](https://docs.spring.io/spring-security/reference/servlet/authentication/passwords/basic.html): username/password và Basic.
- [Spring Security — OAuth2 MockMvc Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): mock decoder và kiểm thử scope.
