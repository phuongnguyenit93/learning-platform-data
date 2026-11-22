# Opaque token và OpaqueTokenIntrospector trong Spring Security Resource Server

**Module:** Spring Security – Servlet  
**Chủ đề cha:** Resource Server

## 1. Học gì trong bài này?

Một **OAuth2 Resource Server** là API nhận access token từ client và chỉ cung cấp tài nguyên khi token được chấp nhận cùng với quyền truy cập phù hợp. Access token thường xuất hiện trong request:

~~~http
GET /api/reports HTTP/1.1
Authorization: Bearer <access-token>
~~~

Trong thực tế, access token có thể là **JWT** hoặc **opaque token**. Nếu token opaque, API thường không thể tự giải mã các claim và xác minh chữ ký như JWT. Resource Server hỏi **Authorization Server (AS)** qua **token introspection endpoint** để biết token đang hoạt động không, do ai hoặc client nào sử dụng, có scope gì, hết hạn khi nào.

Spring Security Servlet cung cấp giao diện **`OpaqueTokenIntrospector`** để thực hiện bước này. Bài học hướng dẫn:

1. Nhận diện opaque token và phân biệt với JWT, refresh token, ID Token.
2. Hiểu RFC 7662, response `active` và cách Resource Server quyết định 401/403.
3. Bật `oauth2ResourceServer().opaqueToken()` trong Spring Boot / Spring Security 6.
4. Hiểu `OAuth2AuthenticatedPrincipal`, authority `SCOPE_...` và cách dùng `hasAuthority`.
5. Tùy biến `OpaqueTokenIntrospector` khi cần chuyển claim đã xác minh thành authority ứng dụng.
6. Viết kiểm thử không phải gọi Authorization Server thật và vận hành an toàn khi introspection lỗi, token bị thu hồi hoặc nhiều API cùng dùng IdP.

**Điểm cốt lõi:** introspection chứng minh token theo chính sách của Authorization Server; **authentication không thay thế authorization**. Token active chưa chắc được phép gọi endpoint cụ thể.

## 2. Opaque token là gì?

**Opaque token** là chuỗi token mà bên sử dụng không được dựa vào cấu trúc bên trong để hiểu ý nghĩa. Nó có thể trông như một chuỗi ngẫu nhiên:

~~~text
8opqC33hLtRna7Ftm9p4
~~~

Chuỗi trên chỉ là **dữ liệu minh họa**, không phải token thật. Không phải opaque token nào cũng có chiều dài, ký tự hoặc tiền tố giống nhau; định dạng là chi tiết của Authorization Server.

**Bản chất không phải là “token không có dấu chấm”**. Một Authorization Server có thể phát JWT làm access token; một hệ thống khác có thể tạo giá trị opaque được lưu trong kho token. Một Resource Server không nên tự đoán chiến lược xác minh bằng cách đếm dấu chấm hoặc decode Base64 rồi tin nội dung. Quan trọng là **hợp đồng token giữa issuer và Resource Server**.

| Thuộc tính | Opaque access token (introspection) | JWT access token (local validation) |
| --- | --- | --- |
| Resource Server kiểm tra | Hỏi Authorization Server qua introspection hoặc một cơ chế tin cậy tương đương. | Thường kiểm tra chữ ký/JWK, issuer, audience, thời hạn và claims cục bộ. |
| Token chứa claim đọc được bởi API? | Không được giả định. Metadata nhận từ introspection. | Payload JWT có claim; base64url **không** phải mã hóa bí mật. |
| Thu hồi token | AS có thể trả `active:false` ngay khi trạng thái thu hồi được cập nhật; cache có thể tạo độ trễ. | JWT tự xác minh thường còn dùng được đến `exp` nếu không có cơ chế revocation/denylist khác. |
| Chi phí mỗi request | Có thể thêm network call, latency, phụ thuộc AS. | Không cần gọi AS trên mỗi request nếu đã có JWKS hợp lệ. |
| Quyền riêng tư | Claim chi tiết không bắt buộc lộ trong chuỗi token gửi qua nhiều bên. | Claim nằm trong payload có thể đọc được bởi bên sở hữu token. |
| Điều kiện triển khai | Introspection endpoint đáng tin, TLS, client credential, timeout và chính sách lỗi. | JWK/issuer/audience, thuật toán cho phép, kiểm tra chữ ký và claims. |

**Opaque không đồng nghĩa mã hóa.** Hình thức không đọc được chỉ là một thuộc tính của token. Nếu token bị lộ, bearer token vẫn có thể bị kẻ khác sử dụng trong thời gian còn hợp lệ. Luôn bảo vệ access token như bí mật: HTTPS, tránh log, query string, analytics, clipboard công khai và kho lưu không cần thiết.

**Phân biệt token:**

- **Access token:** dùng để client gọi Resource Server theo quyền được cấp.
- **Refresh token:** dùng với Authorization Server để lấy access token mới theo luồng cho phép; không gửi như bearer token đến API thông thường.
- **ID Token (OIDC):** dùng cho client xác minh sự kiện đăng nhập và danh tính; **không** lấy ID Token thay access token để gọi Resource Server.
- **Session cookie:** biểu diễn phiên đăng nhập web app; một Resource Server stateless nhận bearer token có mô hình bảo vệ khác.

## 3. Luồng request và vị trí của OpaqueTokenIntrospector

~~~text
Client app
   |
   | GET /api/reports
   | Authorization: Bearer opaque-value
   v
Spring Security Servlet
   |
   v
BearerTokenAuthenticationFilter
   | trích Bearer token từ request
   v
AuthenticationManager / OpaqueTokenAuthenticationProvider
   |
   | introspector.introspect(token)
   v
OpaqueTokenIntrospector
   |
   | HTTPS POST tới AS introspection endpoint
   v
Authorization Server
   |-- xác thực Resource Server client credentials
   |-- tìm token, kiểm tra active/exp/revocation/policy
   |-- trả metadata phù hợp
   v
OAuth2AuthenticatedPrincipal + authorities
   |
   v
BearerTokenAuthentication / SecurityContext
   |
   v
AuthorizationManager
   |-- đủ authority => gọi Controller
   |-- thiếu quyền => 403
   v
Response
~~~

Các thành phần quan trọng:

- **`BearerTokenAuthenticationFilter`**: tìm bearer token trong request và khởi động xác thực. Không viết filter tự parse token nếu cấu hình framework đã đáp ứng.
- **`OpaqueTokenAuthenticationProvider`**: gọi introspector và tạo kết quả authentication. Nếu token không hợp lệ thì authentication thất bại.
- **`OpaqueTokenIntrospector`**: hợp đồng có phương thức `OAuth2AuthenticatedPrincipal introspect(String token)`. Nó không quyết định mọi luật nghiệp vụ của API; nhiệm vụ chính là xác nhận token và tạo principal/authorities phù hợp.
- **`OAuth2AuthenticatedPrincipal`**: mang `name`, attributes và `GrantedAuthority` thu được từ introspection.
- **`BearerTokenAuthentication`**: authentication thường được đưa vào SecurityContext cho opaque bearer token.
- **Authorization**: matcher như `hasAuthority("SCOPE_reports.read")` quyết định endpoint có được gọi không.

**Lưu ý:** API có thể chỉ nhận token từ `Authorization: Bearer`, không cần tự đọc JSON body hay cookie rồi coi đó là bearer token. Các cơ chế custom token resolver cần được đánh giá tránh rò token qua URL hoặc nhầm lẫn token từ nguồn không tin cậy.

## 4. RFC 7662: introspection request và response

RFC 7662 mô tả cách một Resource Server hỏi Authorization Server về trạng thái token. Một request **minh họa**:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: identity.example.test
Authorization: Basic <resource-server-client-credentials>
Content-Type: application/x-www-form-urlencoded

token=<opaque-access-token>&token_type_hint=access_token
~~~

`token_type_hint` là **gợi ý tùy chọn**, không quyết định thành công hay thất bại; Authorization Server vẫn phải kiểm tra token. Cách xác thực client đến introspection endpoint phụ thuộc hợp đồng triển khai; ví dụ phổ biến dùng HTTP Basic với `client-id` và `client-secret`. Không nhúng client secret thật trong tài liệu hoặc source code.

**Ví dụ response của một token đang hoạt động:**

~~~json
{
  "active": true,
  "sub": "user-42",
  "client_id": "report-client",
  "scope": "reports.read reports.write",
  "token_type": "Bearer",
  "exp": 1794000000,
  "iss": "https://identity.example.test"
}
~~~

Không phải claim nào cũng luôn có; `sub` có thể vắng mặt trong một số luồng, `scope` có thể khác nhau, `aud`/tenant/client policy có thể cần kiểm tra riêng. Những giá trị trên là ví dụ, không phải response bắt buộc của mọi IdP.

**Ví dụ response khi token không còn được chấp nhận:**

~~~json
{"active": false}
~~~

Token có thể không hoạt động vì đã hết hạn, bị thu hồi, không tồn tại hoặc không được tiết lộ cho Resource Server đang hỏi. Hệ thống không nên suy đoán trạng thái chi tiết từ mỗi `active:false`, cũng không gửi nguyên nhân nội bộ về cho client.

Các điểm cần nhớ:

1. `active:true` là thông tin từ **introspection endpoint đã xác thực**, không phải một claim `active` trong request mà client có thể tự sửa.
2. Resource Server phải chỉ tin endpoint AS đã cấu hình; phải xác thực TLS, endpoint và cơ chế client authentication. Không nhận URL introspection tùy ý từ bearer token hoặc request.
3. `active:true` **chưa bảo đảm** token được cấp cho đúng **resource/audience/tenant**; nếu AS trả claim `aud`, `iss`, `client_id`, `token_type` hoặc claim custom, chính sách ứng dụng có thể cần kiểm tra bổ sung.
4. Access token bị thu hồi thường dẫn đến `active:false`, nhưng hiệu quả tức thời còn phụ thuộc AS và **caching** ở Resource Server / gateway.
5. Phản hồi HTTP lỗi, timeout, response không hợp lệ hoặc AS không khả dụng **không** được chuyển thành authentication thành công để “giữ trải nghiệm”.

### 4.1. So sánh 401 và 403

| Tình huống | Kết quả API thường có |
| --- | --- |
| Endpoint yêu cầu authentication nhưng **không có token** | `401 Unauthorized` với bearer challenge phù hợp. |
| Token malformed, không tồn tại, `active:false` | `401 Unauthorized` khi bị coi là bearer token không hợp lệ. |
| Token hợp lệ nhưng thiếu scope/authority cần thiết | `403 Forbidden` (`insufficient_scope` có thể xuất hiện trong challenge). |
| Introspection service mất kết nối hoặc trả dữ liệu lỗi | Không cấp quyền; mã HTTP cụ thể có thể phụ thuộc error handling và hạ tầng, **không được bảo đảm luôn là 401**. |
| Token active và có quyền, nhưng truy cập tài nguyên không thuộc sở hữu/tenant | Phải từ chối ở lớp authorization nghiệp vụ, bất kể scope chung. |

Đừng dùng `403` để che mọi lỗi authentication: việc phân biệt 401/403 giúp client và hệ thống giám sát hiểu vấn đề, nhưng **không đưa nội dung token/secret** vào body lỗi.

## 5. Cấu hình chạy được: Spring Boot 3 + Spring Security 6 + opaque token

Ví dụ dùng **Java 17+** và **Spring Boot 3.3.5**, tương ứng Spring Security 6.x trong BOM của bản Boot này. Dùng phiên bản được hỗ trợ và cập nhật bản vá trong hệ thống thật.

Ứng dụng này là **API Servlet**: GET public, GET đòi scope đọc, POST đòi scope ghi, và một endpoint xem thông tin principal tối thiểu. Nó cần Authorization Server hỗ trợ RFC 7662 để gọi thật.

**Cấu trúc thư mục:**

~~~text
opaque-demo/
├── pom.xml
└── src/
    ├── main/java/demo/OpaqueDemoApplication.java
    ├── main/resources/application.yml
    └── test/java/demo/OpaqueDemoApplicationTests.java
~~~

### 5.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>opaque-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

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
            <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.2. `src/main/resources/application.yml`

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: ${INTROSPECTION_URI}
          client-id: ${INTROSPECTION_CLIENT_ID}
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

Đây là **Spring environment placeholders**, không phải chuỗi ID/secret viết cứng. Khi chạy, đặt ba biến môi trường thật:

- `INTROSPECTION_URI`: URL HTTPS cố định của endpoint introspection do IdP cung cấp.
- `INTROSPECTION_CLIENT_ID`: client mà Authorization Server cho phép introspect.
- `INTROSPECTION_CLIENT_SECRET`: secret tương ứng, nạp từ môi trường/secret manager.

**Không** dùng `http://...` ngoài môi trường test nội bộ không chứa bí mật; không đưa client secret vào Git, ảnh chụp log hoặc tham số URL. Một số IdP chỉ cho introspection với một dạng client authentication đặc thù; ví dụ này giả định kiểu được cấu hình qua `client-id`/`client-secret` của Spring Security.

### 5.3. `src/main/java/demo/OpaqueDemoApplication.java`

~~~java
package demo;

import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class OpaqueDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(OpaqueDemoApplication.class, args);
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .requestMatchers(HttpMethod.POST, "/api/reports")
                    .hasAuthority("SCOPE_reports.write")
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()))
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            // Chỉ thích hợp cho API stateless xác thực bằng bearer token
            // trong Authorization header, KHÔNG xác thực bằng cookie.
            .csrf(AbstractHttpConfigurer::disable);

        return http.build();
    }

    @RestController
    static class ApiController {

        @GetMapping("/public")
        Map<String, String> publicEndpoint() {
            return Map.of("status", "public");
        }

        @GetMapping("/api/reports")
        Map<String, String> readReport() {
            return Map.of("status", "read-ok");
        }

        @PostMapping("/api/reports")
        Map<String, String> writeReport() {
            // Minh họa authority check; không ghi dữ liệu thật.
            return Map.of("status", "write-ok");
        }

        @GetMapping("/api/me")
        Map<String, Object> currentUser(Authentication authentication) {
            Set<String> authorities = authentication.getAuthorities()
                .stream()
                .map(GrantedAuthority::getAuthority)
                .collect(Collectors.toSet());

            // Chỉ trả dữ liệu tối thiểu để quan sát.
            return Map.of(
                "principal", authentication.getName(),
                "authorities", authorities
            );
        }
    }
}
~~~

Giải thích cấu hình:

- `oauth2ResourceServer(...opaqueToken(...))` yêu cầu Spring Security xử lý bearer token qua introspection. Với các thuộc tính `opaquetoken` ở trên, Spring Boot tạo introspector mặc định phù hợp khi không có bean tùy biến.
- `hasAuthority("SCOPE_reports.read")` và `hasAuthority("SCOPE_reports.write")` là các quy tắc phân quyền endpoint. `scope` từ introspection thường được Spring Security chuyển thành authority tiền tố **`SCOPE_`**.
- `SessionCreationPolicy.STATELESS` tránh tạo session bảo mật dùng làm nơi xác thực cho API này. Bảo mật bearer token **vẫn cần HTTPS** và bảo vệ token khỏi lộ.
- `csrf.disable()` ở đây **chỉ cho API thuần stateless nhận token ở Authorization header và không dựa vào cookie tự động gửi**. Nếu ứng dụng còn trang web đăng nhập session/cookie hoặc browser tự gửi credential cho endpoint, phải đánh giá CSRF riêng, không copy cấu hình này một cách máy móc.
- Ví dụ `GET /public` đi qua security filter chain nhưng được `permitAll`; `/api/me` cần bearer token hợp lệ và chỉ trả thông tin quan sát. Production nên cân nhắc không public danh sách authority không cần thiết.
- Ví dụ chỉ phân quyền theo scope chung. Ứng dụng thật có thể cần **audience, tenant, owner, trạng thái** và kiểm tra object-level authorization.

### 5.4. Chạy và gọi API

Từ thư mục dự án, sau khi cấu hình ba biến môi trường:

~~~bash
mvn spring-boot:run
~~~

Thử public endpoint:

~~~bash
curl -i http://localhost:8080/public
~~~

Kỳ vọng HTTP 200, JSON `{"status":"public"}`. Localhost có thể dùng HTTP để thực hành không chứa token thật; triển khai và thử với **token thật cần HTTPS**.

Thử endpoint yêu cầu quyền:

~~~bash
# ACCESS_TOKEN phải được phát bởi Authorization Server phù hợp.
curl -i -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/reports
~~~

Kỳ vọng phụ thuộc kết quả introspection: token active với scope `reports.read` → HTTP 200; không token/không hợp lệ → thường 401; token active nhưng không có scope đọc → 403. Cách thay biến môi trường trên Windows/PowerShell khác Bash; cú pháp `$ACCESS_TOKEN` trong ví dụ là Bash.

Đừng đưa token thật vào ảnh chụp lệnh, shell history có thể bị thu thập, công cụ logging hoặc ticket. Dùng bộ công cụ lưu secret phù hợp với môi trường.

## 6. OpaqueTokenIntrospector: giao diện và dữ liệu trả về

Spring Security 6 có interface ở package:

~~~java
org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector
~~~

Phương thức cốt lõi:

~~~java
OAuth2AuthenticatedPrincipal introspect(String token);
~~~

Đây là **chữ ký API để giải thích**, không phải một file Java độc lập. Một implementation có thể:

1. Nhận token string từ authentication provider.
2. Gửi yêu cầu tới introspection endpoint được cấu hình.
3. Xử lý `active`, lỗi xác thực, dữ liệu thiếu hoặc metadata phản hồi.
4. Chuyển metadata thành `OAuth2AuthenticatedPrincipal` và tập `GrantedAuthority`.
5. Trả principal khi token được chấp nhận hoặc ném lỗi phù hợp nếu không chấp nhận.

Ví dụ truy cập thông tin từ authentication tại controller/service:

~~~java
// Đoạn minh họa nằm trong phương thức có tham số Authentication.
if (authentication.getPrincipal() instanceof
        org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal p) {
    String subject = p.getAttribute("sub");
    Object audience = p.getAttribute("aud");
    // Chỉ dùng thuộc tính sau khi xét chính sách issuer/audience/tenant.
}
~~~

Không nên tin `authentication.getName()` là email cố định hoặc là duy nhất trên tất cả issuer. Với nhiều IdP, định danh ổn định có thể là cặp **`issuer + subject`**, nhưng phải xác nhận metadata và trust boundary. `username` có thể đổi, `sub` có thể mang ý nghĩa khác nhau ở từng issuer.

## 7. Tùy biến introspector để chuyển claim thành quyền

Một API đôi khi nhận response hợp lệ dạng:

~~~json
{
  "active": true,
  "sub": "user-42",
  "scope": "reports.read",
  "app_roles": ["auditor", "manager"]
}
~~~

Resource Server muốn tạo thêm:

- `app_roles: ["auditor"]` → `ROLE_AUDITOR`
- `app_roles: ["manager"]` → `ROLE_MANAGER`
- Bất kỳ giá trị lạ, kiểu sai hoặc thiếu claim → **không cấp role tương ứng**

Trước khi map, phải thỏa thuận rằng **chính Authorization Server đáng tin đã đưa `app_roles` vào introspection response**, và API này được phép dựa vào claim đó. Không đọc `app_roles` từ request body/URL/header do client điều khiển.

### 7.1. Bean tùy biến (chỉ bổ sung khi thực sự cần)

Tạo class tùy chọn **`src/main/java/demo/IntrospectionAuthoritiesConfiguration.java`**. Class này dùng `NimbusOpaqueTokenIntrospector` làm delegate gọi introspection thực, giữ authorities mặc định và bổ sung một **allowlist** role:

~~~java
package demo;

import java.util.Collection;
import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Set;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Configuration
public class IntrospectionAuthoritiesConfiguration {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.introspection-uri}")
            String uri,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-id}")
            String clientId,
            @Value("${spring.security.oauth2.resourceserver.opaquetoken.client-secret}")
            String clientSecret) {

        OpaqueTokenIntrospector delegate =
            new NimbusOpaqueTokenIntrospector(uri, clientId, clientSecret);

        return token -> {
            OAuth2AuthenticatedPrincipal principal =
                delegate.introspect(token);

            Set<GrantedAuthority> mapped =
                new LinkedHashSet<>(principal.getAuthorities());

            Object raw = principal.getAttribute("app_roles");
            if (raw instanceof Collection<?> roles) {
                for (Object item : roles) {
                    if (!(item instanceof String role)) {
                        continue;
                    }

                    switch (role.trim().toLowerCase(Locale.ROOT)) {
                        case "auditor" ->
                            mapped.add(new SimpleGrantedAuthority("ROLE_AUDITOR"));
                        case "manager" ->
                            mapped.add(new SimpleGrantedAuthority("ROLE_MANAGER"));
                        default -> {
                            // Unknown role: không cấp quyền.
                        }
                    }
                }
            }

            return new DefaultOAuth2AuthenticatedPrincipal(
                principal.getName(),
                principal.getAttributes(),
                mapped
            );
        };
    }
}
~~~

**Cách dùng:** thêm file class này nếu cần custom mapping; **không cần thêm** khi chỉ dùng scope mặc định. Bean `OpaqueTokenIntrospector` tự định nghĩa được Spring Security sử dụng cho resource server tương ứng. Class custom được đặt trong package `demo` để `@SpringBootApplication` quét thấy.

**Điểm an toàn:**

- Delegate luôn gọi introspection trước khi cấp role; **không** thay bằng `token -> principal` tin mọi token client gửi.
- Chỉ cấp `ROLE_AUDITOR` / `ROLE_MANAGER` từ allowlist; không tạo `ROLE_` từ chuỗi claim tùy ý.
- Claim thiếu/sai kiểu không tạo role; đây là **fail closed cho quyền nghiệp vụ bổ sung**.
- Giữ `SCOPE_...` và các authority gốc do delegate tạo, tránh vô tình làm mất quyền đọc/ghi đã được kiểm chứng.
- Nếu role quan trọng cần dựa vào audience/tenant/issuer, bổ sung các kiểm tra này **trước khi cấp role**.
- Với hệ thống dùng Spring Security khác phiên bản nêu trên, kiểm tra constructors/deprecations của introspector theo phiên bản; đừng sao chép API từ tutorial cũ mà không biên dịch.

Ví dụ cấp quyền theo role:

~~~java
// Dòng minh họa trong authorizeHttpRequests của SecurityFilterChain:
.requestMatchers("/api/audit").hasRole("AUDITOR")
~~~

`hasRole("AUDITOR")` mặc định kiểm tra `ROLE_AUDITOR`, còn `hasAuthority("SCOPE_reports.read")` kiểm tra đúng authority scope; hai khái niệm không thể dùng thay nhau một cách tùy ý.

### 7.2. Khi cần validation bổ sung của introspection response

Ngoài roles, app có thể cần giới hạn token **đúng audience/resource**, đúng `iss`/tenant, hoặc token type phù hợp. Giao diện `OpaqueTokenIntrospector` cho phép thêm logic sau khi delegate xác thực introspection, nhưng cần làm chặt chẽ:

- Từ chối token nếu claim bắt buộc thiếu hoặc không thuộc tập cho phép.
- Không so sánh substring với audience hoặc issuer; dùng kiểu dữ liệu/schema rõ ràng.
- Nếu `aud` có thể là chuỗi hoặc mảng, đặc tả API phải nói rõ cách xử lý.
- Không tin `client_id` tương đương quyền của người dùng nếu business policy không cho phép.
- Cần đánh giá metadata theo từng kiểu grant: `sub` không phải lúc nào cũng biểu diễn cùng một loại chủ thể.

**Ví dụ chính sách:** Resource Server này chỉ nhận token mà AS xác nhận dành cho audience `reports-api`. Nếu introspection trả `aud` không chứa audience đó, **từ chối dù active=true**. Phần mã cụ thể tùy kiểu dữ liệu claim và cơ chế authorization của AS; ví dụ ở mục 7.1 chỉ demo role mapping, **chưa cài đặt audience checking**. Không nên kết luận chỉ nhờ hoạt động của class 7.1 rằng audience đã được ràng buộc.

## 8. Kiểm thử bảo mật không phụ thuộc AS đang chạy

Có hai cấp kiểm thử cần phân biệt:

- **Security test dùng mock `OpaqueTokenIntrospector`:** kiểm tra Spring Security đọc bearer token, gắn authorities và quyết định 401/403/200; không phát HTTP introspection thật.
- **Integration test với AS/introspection endpoint giả lập:** kiểm tra HTTP Basic client authentication, body `token`, parse JSON, `active:false`, timeout và secret rotation. Có thể dùng mock HTTP server phù hợp với test framework; cần bảo đảm không chấp nhận token giả trong production.

### 8.1. MockMvc test cho cấu hình mục 5

**`src/test/java/demo/OpaqueDemoApplicationTests.java`:**

~~~java
package demo;

import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.HttpHeaders;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
    "spring.security.oauth2.resourceserver.opaquetoken.introspection-uri=https://idp.example.test/introspect",
    "spring.security.oauth2.resourceserver.opaquetoken.client-id=test-client",
    "spring.security.oauth2.resourceserver.opaquetoken.client-secret=test-secret"
})
@AutoConfigureMockMvc
class OpaqueDemoApplicationTests {

    @Autowired
    MockMvc mvc;

    @MockBean
    OpaqueTokenIntrospector introspector;

    @BeforeEach
    void setUp() {
        var reader = new DefaultOAuth2AuthenticatedPrincipal(
            "user-reader",
            Map.of("sub", "user-reader", "scope", "reports.read"),
            List.of(new SimpleGrantedAuthority("SCOPE_reports.read"))
        );
        var writer = new DefaultOAuth2AuthenticatedPrincipal(
            "user-writer",
            Map.of("sub", "user-writer", "scope", "reports.write"),
            List.of(new SimpleGrantedAuthority("SCOPE_reports.write"))
        );
        when(introspector.introspect("reader-token")).thenReturn(reader);
        when(introspector.introspect("writer-token")).thenReturn(writer);
        when(introspector.introspect("revoked-token"))
            .thenThrow(new BadOpaqueTokenException("Inactive token"));
    }

    @Test
    void publicEndpointDoesNotRequireToken() throws Exception {
        mvc.perform(get("/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("public"));
    }

    @Test
    void missingOrRevokedTokenIsUnauthorized() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized());

        mvc.perform(get("/api/reports")
                .header(HttpHeaders.AUTHORIZATION, "Bearer revoked-token"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void readScopeCanReadButCannotWrite() throws Exception {
        mvc.perform(get("/api/reports")
                .header(HttpHeaders.AUTHORIZATION, "Bearer reader-token"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("read-ok"));

        mvc.perform(post("/api/reports")
                .header(HttpHeaders.AUTHORIZATION, "Bearer reader-token"))
            .andExpect(status().isForbidden());
    }

    @Test
    void writeScopeCanWriteButCannotRead() throws Exception {
        mvc.perform(post("/api/reports")
                .header(HttpHeaders.AUTHORIZATION, "Bearer writer-token"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("write-ok"));

        mvc.perform(get("/api/reports")
                .header(HttpHeaders.AUTHORIZATION, "Bearer writer-token"))
            .andExpect(status().isForbidden());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

**Kỳ vọng:** bốn test pass. Đây là kỳ vọng với mã ví dụ, không phải log đã được lấy từ một môi trường chạy thật. Mock bean thay thế introspection network: test chứng minh Spring Security **sử dụng kết quả của introspector** và kiểm tra authority, chứ **không** chứng minh Authorization Server thật trả đúng metadata.

**Lưu ý khi bật class tùy chọn mục 7.1:** vì class đó tự khai báo bean introspector, bộ test cũng cần thiết kế theo hướng thay thế/mock bean thích hợp. Khi kiểm tra riêng logic mapping ở class tùy biến, nên tách delegate thành dependency để dùng unit test với principal giả, test cả unknown role, sai kiểu claim và quyền không được nâng ngoài allowlist.

### 8.2. Những test khác nên có

| Test case | Mục đích |
| --- | --- |
| AS trả `active:false` | Đảm bảo API không tạo authentication hợp lệ. |
| AS trả lỗi 401/403 cho client introspection | Phát hiện sai `client-id`/`secret`, không coi token là active. |
| AS timeout, TLS error, 5xx, JSON thiếu `active` | Fail closed, giám sát và xử lý lỗi phù hợp. |
| Scope string trống, claim sai kiểu | Không tự tạo quyền; trả kết quả theo policy. |
| User có `SCOPE_reports.read` nhưng truy cập tài nguyên tenant khác | Authorization theo đối tượng từ chối nếu không được phép. |
| Claim roles chứa `superadmin` không nằm trong allowlist | Không tự cấp `ROLE_SUPERADMIN`. |
| Token bị thu hồi khi cache bật | Xác nhận cửa sổ stale-cache nằm trong rủi ro chấp nhận. |
| Token được cấp cho API khác | Từ chối nếu policy yêu cầu audience/resource cụ thể. |
| Nhiều security filter chain | Đảm bảo matcher của Resource Server áp đúng endpoint. |
| HTTPS qua reverse proxy/CDN | Token, client secret không lộ ở log hoặc liên kết HTTP ngoài ý muốn. |

## 9. Cache, độ trễ và revocation: đánh đổi quan trọng nhất của introspection

Nếu Resource Server hỏi Authorization Server cho **mọi request**, tổng tải có thể lớn. Ví dụ 500 request/giây nghĩa là tối đa xấp xỉ 500 introspection call/giây nếu không có cache và không có tầng giảm tải khác. Tất nhiên số thật tùy chiến lược hệ thống.

### 9.1. Khi nào cache?

Một số hệ thống cache kết quả introspection theo token để giảm latency/tải AS. Tuy nhiên:

- Cache một token `active:true` quá lâu có thể tiếp tục cho phép token đã bị **revoke**.
- TTL không được vượt quá thời hạn `exp` và phải xét yêu cầu thu hồi gần như tức thì; với chính sách rất chặt có thể **không cache**.
- Không cache vô thời hạn; cần xử lý đồng bộ khi cấu hình role/scope thay đổi, deploy nhiều node, clock skew và tenant.
- Cache key chứa token (bí mật). Nếu cần cache, cần bảo vệ key/dữ liệu, phân vùng hoặc băm an toàn theo thiết kế và tránh log token.
- Negative caching cho token không hợp lệ cũng có rủi ro DoS/memory nếu client gửi vô hạn token lạ; cần giới hạn dung lượng và eviction.
- Cache kết quả `active:true` mà không xem `audience`, scope hoặc policy cập nhật có thể gây lỗi phân quyền dù token vẫn còn hạn.

**Không nên** tự thêm cache bằng một `Map<String, OAuth2AuthenticatedPrincipal>` toàn cục không TTL, không giới hạn bộ nhớ và không chính sách revocation.

### 9.2. Trạng thái AS và xử lý lỗi

Introspection phụ thuộc mạng. Cần:

1. **Timeout kết nối và đọc** hợp lý, không để một request API chờ vô hạn.
2. Connection pooling / reuse / circuit-breaker phù hợp, nhưng nếu service lỗi **không chuyển thành allow-all**.
3. Retry có kiểm soát, tránh nhân tải khi AS đang gặp sự cố; phân biệt lỗi mạng với token không hợp lệ.
4. Theo dõi tỷ lệ 401, 403, độ trễ introspection, lỗi TLS, lỗi 5xx và tỷ lệ cache hit/miss nếu có.
5. Thiết kế degradation có chủ đích: endpoint nhạy cảm nên **từ chối khi không thể xác minh**; nếu có endpoint công khai, cho phép nó hoạt động độc lập với token.

**Fail closed:** khi không thể chứng minh token hợp lệ, **không cấp authority** chỉ để tăng availability. Cần thông báo lỗi vận hành phù hợp cho client mà không tiết lộ token hoặc client secret.

## 10. Các lỗi triển khai thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| API trả 401 dù token vừa phát hành | URL introspection sai, token thuộc issuer khác, AS không nhận client credentials, token chưa active hoặc đã hết hạn. | Kiểm tra issuer/endpoint/credential phía server, log an toàn, so sánh response của AS ở môi trường test. |
| API trả 403 với token active | Không có `SCOPE_...` cần thiết hoặc token không thỏa policy resource. | Xem scopes/authorities, matcher, audience và quyền theo tài nguyên. |
| Token JSON trông như JWT nhưng config opaque | Hệ thống chọn chiến lược introspection bất kể định dạng token. | Xác nhận hợp đồng với issuer; không tự chuyển decoder theo hình thức token. |
| `scope` là `reports.read` nhưng dùng `hasRole("reports.read")` | Role prefix khác scope authority. | Dùng `hasAuthority("SCOPE_reports.read")` theo mapping mặc định. |
| AS trả `app_roles` nhưng `ROLE_AUDITOR` không tồn tại | Mặc định không map mọi claim thành role nghiệp vụ. | Viết custom introspector allowlist có xác thực nguồn. |
| Endpoint public vẫn có network introspection khi gửi bearer token không hợp lệ | Filter xử lý bearer token được gửi ngay cả ở request có `permitAll`. | Không gửi bearer token không cần thiết đến public endpoint; hiểu `permitAll` không bỏ filter. |
| AS outage khiến toàn bộ endpoint protected lỗi | Introspection nằm trên đường xử lý authentication. | Timeout, monitoring, kiến trúc HA, cache có chính sách; không fail open. |
| Sau khi revoke token vẫn được chấp nhận | Cache còn hiệu lực hoặc trạng thái AS cập nhật chậm. | Giảm TTL, thiết kế purge/revocation và test SLA thu hồi. |
| 401 sau khi rotate secret | Resource Server vẫn dùng credential cũ. | Secret manager, phân phối/rotate an toàn, quan sát lỗi client authentication. |
| Token hiển thị trong logs | Ghi đầy đủ Authorization header, query parameter hoặc exception payload. | Redact Authorization, vô hiệu logging nhạy cảm, quản lý log access. |
| API 200 với scope nhưng dữ liệu của tenant khác | Chỉ kiểm tra scope, không kiểm tra đối tượng. | Kiểm tra ownership, tenant, policy từng resource trong service layer. |

## 11. Bảo mật và vận hành production

### 11.1. Bảo vệ đầu cuối của bearer token

- Dùng **HTTPS** từ client đến API và từ API đến introspection endpoint; xác minh certificate/hostname đúng.
- Không gửi bearer token trong query parameter, không đưa token vào log, analytics hay thông báo lỗi.
- Cân nhắc tuổi thọ token ngắn, scope tối thiểu, rotation và thu hồi.
- Xác định ai được phép introspect, AS trả metadata tối thiểu cần thiết cho API đó.
- Credential introspection là **secret của Resource Server**, không phải token người dùng; quản lý bằng secret store và rotate.
- CORS không phải cơ chế xác minh token hay ngăn mọi request đến API. Không dùng `Access-Control-Allow-Origin: *` để “giải quyết” lỗi authentication.

### 11.2. Scope, role và object-level authorization

Chỉ `active:true` **không đủ**. Mỗi endpoint cần một chính sách:

~~~text
1. Bearer token có hợp lệ không?
2. Được phát cho đúng API / audience / issuer / tenant không?
3. Có scope/role cần thiết không?
4. Chủ thể có quyền với đúng resource ID và trạng thái dữ liệu không?
5. Luồng nghiệp vụ có cần điều kiện bổ sung, transaction hoặc audit không?
~~~

Nếu API dùng `/api/accounts/{id}`, token có `SCOPE_accounts.read` vẫn không tự bảo đảm chủ thể được xem **mọi** tài khoản. Phải liên kết user/client với resource ID, tenant hoặc policy hệ thống.

### 11.3. Resource Server và ứng dụng web chung một backend

Nếu một hệ thống vừa là **OAuth2 Client** đăng nhập người dùng qua session/cookie vừa là **Resource Server** nhận bearer token, có thể cần **nhiều SecurityFilterChain** theo đường dẫn và thứ tự `@Order`. Cấu hình `csrf.disable()` của API thuần bearer token **không được áp bừa** cho form session/cookie. Xác thực bằng bearer token và cookie có mô hình CSRF khác nhau.

### 11.4. Introspection và tính riêng tư của metadata

Response có thể có `sub`, `username`, `client_id`, `scope`, `aud` và custom claims. Chỉ giữ/hiển thị dữ liệu cần thiết. Nếu nhiều IdP cùng cấp token, cần xác định issuer đáng tin và namespace định danh; đừng gộp `sub` từ hai issuer khác nhau thành một người chỉ vì giá trị chuỗi trùng.

## 12. Quy trình xác minh theo từng bước

**Bước 1 — Xác định loại access token.** Hỏi AS có hỗ trợ token introspection, URI, kiểu xác thực client và chuẩn schema/claim nào. Không tự đoán từ chuỗi token.

**Bước 2 — Cấu hình tối thiểu.** Dùng starter resource server, ba thuộc tính `opaquetoken` và `oauth2ResourceServer().opaqueToken()`. Không tự viết token parser.

**Bước 3 — Kiểm tra một token test hợp lệ.** Xác nhận `active:true`, scope đúng và endpoint đủ quyền trả 200. Không dùng token thật trong tài liệu công khai.

**Bước 4 — Kiểm tra thất bại.** Không token, token sai/đã thu hồi, AS lỗi, token thiếu scope, audience sai, resource thuộc tenant khác.

**Bước 5 — Xác nhận mapping.** In/log **tên authority** an toàn trong môi trường test (không log token), kiểm tra `SCOPE_reports.read` và các role allowlist nếu có.

**Bước 6 — Hiệu năng và revocation.** Đo độ trễ network thực, đặt timeout, kiểm tra hiệu lực thu hồi và cache TTL theo mức rủi ro.

**Bước 7 — Giám sát và vận hành.** Audit và metrics với dữ liệu tối thiểu; kiểm tra secret rotation, HA của AS, chứng chỉ HTTPS và chính sách fail closed.

## 13. Câu hỏi tự kiểm tra

**Câu 1:** Opaque token có phải luôn là một chuỗi random không có thông tin bên trong?

**Trả lời:** Không bắt buộc. “Opaque” nghĩa là Resource Server **không dựa vào cấu trúc token để giải thích và xác minh cục bộ**. AS quyết định cách sinh/lưu token và trả metadata thông qua introspection.

**Câu 2:** Introspection trả `active:true` thì có nên cho mọi endpoint 200 không?

**Trả lời:** Không. API vẫn phải kiểm tra scopes/roles, audience/resource, tenant và authorization theo đối tượng.

**Câu 3:** Khi nào 401 và khi nào 403?

**Trả lời:** Thông thường không có token hoặc token không hợp lệ → 401; token hợp lệ nhưng không đủ quyền → 403. Lỗi hạ tầng introspection có thể đi qua cơ chế xử lý lỗi riêng, không nên gán cứng luôn là 401.

**Câu 4:** `OpaqueTokenIntrospector` có cần đọc JWT payload để lấy role không?

**Trả lời:** Không. Nó nhận token và dựa vào kết quả introspection/nguồn xác thực phù hợp. Nếu Resource Server sử dụng JWT local validation, hướng cấu hình tương ứng là `jwt()`/JWT converter.

**Câu 5:** Tại sao không cache kết quả `active:true` trong một giờ cho mọi token?

**Trả lời:** Token có thể hết hạn hoặc bị revoke trước một giờ; cache cũ tạo cửa sổ chấp nhận token không còn hợp lệ. TTL, kích thước, bảo vệ key và revocation SLA phải được thiết kế rõ ràng.

**Câu 6:** Khi Authorization Server tạm mất mạng, có nên tự xem token là hợp lệ không?

**Trả lời:** Không. Không thể xác minh thì không cấp quyền theo đường tắt; xử lý lỗi, timeout, availability và quan sát vận hành một cách có kiểm soát.

---

**Kết luận:** Với Spring Security Servlet Resource Server, opaque token được xác minh thông qua **`OpaqueTokenIntrospector`** và introspection endpoint đáng tin. **`active` chứng minh trạng thái token chứ không cấp phép mọi thao tác**. Sau authentication, hãy kiểm tra `SCOPE_...`/role theo allowlist, ràng buộc audience/tenant/resource, xử lý revocation/caching hợp lý, bảo vệ credential và **không fail open** khi không thể introspect.