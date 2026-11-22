# Vai trò Resource Server và phân biệt với ứng dụng đăng nhập OAuth2 trong Spring Security Servlet

## 1. Mục tiêu: hai vai trò dễ bị nhầm

Trong hệ thống sử dụng OAuth 2.0, một ứng dụng có thể làm **Resource Server**, **OAuth2 Client** hoặc đồng thời cả hai. Khi nói “ứng dụng dùng OAuth2”, phải hỏi nó đang **bảo vệ API nhận access token** hay đang **đăng nhập người dùng qua một nhà cung cấp danh tính**. Đây là hai trách nhiệm khác nhau, dùng các thành phần Spring Security và luồng HTTP khác nhau.

**Resource Server** cung cấp tài nguyên được bảo vệ như JSON API, kiểm tra **access token** do client gửi, xác minh token có thể tin cậy rồi quyết định client có quyền truy cập hay không. **Ứng dụng đăng nhập OAuth2/OIDC (OAuth2 Login application)** thường là một **OAuth2 Client**: nó chuyển hướng trình duyệt đến Authorization Server, nhận authorization code, đổi code lấy token và thiết lập phiên đăng nhập cho người dùng trong ứng dụng.

| Câu hỏi | OAuth2 Resource Server | Ứng dụng OAuth2/OIDC Login |
| --- | --- | --- |
| Vai trò OAuth2 | **Resource Server**, chủ sở hữu API được bảo vệ | **OAuth2 Client**, đại diện ứng dụng cần đăng nhập người dùng |
| Request đi vào | **GET /api/orders** với **Authorization: Bearer ...** | **GET /dashboard**, **GET /oauth2/authorization/provider**, callback login |
| Xác thực bằng gì? | Access token hợp lệ của đúng hệ thống phát hành và đúng API | Authorization Code flow với provider; OIDC dùng ID token/claims xác nhận danh tính |
| Khi chưa xác thực | API thường trả **401** và **WWW-Authenticate: Bearer** | Trình duyệt thường được **redirect 302** đến nhà cung cấp đăng nhập |
| Trạng thái | REST API thuần Bearer thường **stateless** | Web application truyền thống thường tạo **HttpSession** và cookie |
| Principal trong Spring Security | Thường **Jwt** trong **JwtAuthenticationToken**, hoặc OAuth2AuthenticatedPrincipal nếu opaque | Thường **OAuth2User** / **OidcUser** trong **OAuth2AuthenticationToken** |
| Cấu hình chủ đạo | **http.oauth2ResourceServer(...)** | **http.oauth2Login(...)** |
| Dữ liệu quyền | Scopes, claims, authorities được xác minh và ánh xạ thành quyền API | Danh tính/claims và authorities của user; token có thể dùng để gọi API khác |
| Có nhiệm vụ phát token? | **Không**; chủ yếu nhận và xác minh token | **Không nhất thiết**; client xin token từ Authorization Server |

**Điểm mấu chốt:** Resource Server không tự trở thành OAuth2 Login application chỉ vì cả hai cùng liên quan access token. Ngược lại, bật **oauth2Login()** cho web UI không tự cấu hình API chấp nhận Bearer JWT.

## 2. Bốn vai trò OAuth2 và ví dụ gần thực tế

Một kiến trúc có thể gồm:

- **Resource Owner:** người dùng có dữ liệu cần truy cập.
- **OAuth2 Client:** ứng dụng web, mobile app hoặc service muốn truy cập tài nguyên thay mặt người dùng hoặc danh tính máy.
- **Authorization Server (AS):** phát hành access token sau khi xác thực/ủy quyền theo grant thích hợp. Có thể hỗ trợ OpenID Connect (OIDC) để cung cấp thông tin đăng nhập.
- **Resource Server (RS):** API nhận token và phục vụ tài nguyên khi token hợp lệ, có đủ quyền.

Ví dụ:

~~~text
                            +-------------------------------+
                            | Authorization Server / IdP    |
                            | phát hành access token        |
                            +---------------+---------------+
                                            |
                                        access token
                                            |
+-------------------------+                 v
| Frontend / OAuth2 Client| -- Bearer --> [Orders API]
| hoặc một backend client |             [Resource Server]
+-------------------------+                    |
                                               v
                                            database
~~~

Authorization Server và Resource Server có thể do hai đội/hệ thống khác nhau quản lý. Resource Server **tin vào những issuer cụ thể và keys/introspection contract được cấu hình**, nhưng không mặc nhiên tin mọi JWT được gửi đến.

Một ứng dụng có thể thực hiện nhiều vai trò ở các request khác nhau. Ví dụ: cổng web là OAuth2 Client để đăng nhập, rồi dùng access token đã lấy để gọi Orders API là Resource Server. Cổng web **không cần nhận Bearer** cho trang giao diện chỉ vì nó đang gọi API bằng Bearer ở phía backend.

## 3. Luồng số 1: client gọi Resource Server

Giả sử một client đã có access token hợp lệ do Authorization Server cấp. Khi gọi API:

~~~http
GET /api/invoices HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJ...token...
~~~

Diễn biến ở phía Spring Security Servlet:

~~~text
1. Request đến API
    |
2. BearerTokenAuthenticationFilter lấy bearer token từ request
    |
3. AuthenticationManager dùng JwtAuthenticationProvider
   (JWT) hoặc OpaqueTokenAuthenticationProvider (opaque)
    |
4. Kiểm tra token: chữ ký/issuer/thời hạn,
   hoặc introspection tùy loại và cấu hình
    |
5. Ánh xạ scopes/claims -> Authentication + GrantedAuthority
    |
6. AuthorizationFilter kiểm tra quyền trên endpoint
    |
7. Controller thực thi và trả dữ liệu
~~~

Nếu **không có token** hoặc **token không hợp lệ**, endpoint được bảo vệ thường trả **401 Unauthorized**. Nếu token xác thực được nhưng **không đủ authority/scope** cho tài nguyên, thường trả **403 Forbidden**. Các exception handler và cách cấu hình có thể thay đổi chi tiết response, nhưng không nên biến một API Bearer thành redirect trình duyệt như login UI nếu đó không phải yêu cầu.

Ví dụ access token JWT có thể chứa claims:

~~~json
{
  "iss": "https://idp.example.com/realms/training",
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "invoices.read invoices.write",
  "exp": 1893456000
}
~~~

Đây là **payload minh họa**; riêng phần JSON đọc được **không chứng minh token đáng tin**. Resource Server phải xác minh chữ ký hoặc kết quả introspection, thời hạn, issuer và các ràng buộc quan trọng như audience đúng API. **sub** là chủ thể, có thể là user hoặc service account; không mặc nhiên là một người dùng đã đăng nhập qua browser.

## 4. Luồng số 2: ứng dụng web đăng nhập bằng OAuth2/OIDC

Một web application dùng **oauth2Login()** có luồng điển hình:

~~~text
User mở /dashboard
       |
       v
Ứng dụng web (OAuth2 Client) chưa có phiên đăng nhập
       |
       +-- 302 redirect tới Authorization Endpoint của IdP
                   |
                   v
         User đăng nhập/chấp thuận tại IdP
                   |
                   +-- Redirect về redirect_uri với authorization code
                                       |
                                       v
                    Web app xác minh state và đổi code lấy tokens
                                       |
                                       v
                    Tạo Authentication cho user, lưu SecurityContext
                    trong session theo cấu hình ứng dụng
                                       |
                                       v
                    Browser tiếp tục /dashboard với session cookie
~~~

Ứng dụng login là **client** trong authorization code flow. Với **OIDC**, scope **openid** yêu cầu lớp danh tính bổ sung; ứng dụng xác minh ID token và lấy **OidcUser**. **OAuth2** là framework ủy quyền; **OIDC** bổ sung cơ chế xác thực danh tính tiêu chuẩn. Vì vậy không nên gọi mọi access token là “ID token”.

Một trang đã đăng nhập ở web app có thể sử dụng **session cookie** cho các request tới chính web app. Web app có thể dùng **OAuth2AuthorizedClient** để quản lý access token khi gọi downstream API. **Session cookie của web app** và **Bearer access token gửi đến API** là hai bằng chứng khác nhau, với vòng đời và trách nhiệm bảo vệ khác nhau.

**Không tự viết callback đổi authorization code nếu Spring Security đã cung cấp oauth2Login()**. Cấu hình client registration và security chain rõ ràng sẽ giúp các bước state, login callback và token handling đi qua cơ chế được framework hỗ trợ. Tùy client/public client, PKCE là một cơ chế quan trọng; OIDC còn có nonce và ID token validation.

## 5. Phân biệt access token, ID token, refresh token và cookie

| Vật mang thông tin | Dành cho ai? | Công dụng | Không nên dùng để... |
| --- | --- | --- | --- |
| **Access token** | Resource Server/API đúng audience | Xin quyền truy cập tài nguyên | Thay ID token để chứng minh user đã đăng nhập cho client |
| **ID token (OIDC)** | OAuth2/OIDC Client đúng client_id | Cho client xác minh sự kiện xác thực và danh tính user | Dùng như Bearer access token cho API nếu API không được thiết kế/ủy quyền như vậy |
| **Refresh token** | OAuth2 Client được cấp refresh token | Xin access token mới theo chính sách AS | Gửi cho Resource Server như token gọi API |
| **Session cookie** | Web app quản lý session | Tìm phiên đăng nhập phía server | Giả định có thể thay Bearer token cho API độc lập |
| **Authorization code** | OAuth2 Client ở redirect URI | Đổi lấy token theo code flow | Gửi trực tiếp đến API để lấy tài nguyên |

JWT là **định dạng token** có thể dùng cho access token hoặc ID token; chữ “JWT” **không cho biết token thuộc loại nào**. Một token có chữ ký hợp lệ nhưng **audience không dành cho API** vẫn phải bị từ chối theo chính sách Resource Server. API không nên tin vào email/role/claims chỉ vì chúng xuất hiện trong payload chưa được xác minh.

Một Resource Server không cần xử lý login form hoặc đổi authorization code. Nó có thể được gọi bởi service theo client credentials flow, mobile application, browser SPA dùng flow thích hợp, hoặc web server đã đăng nhập người dùng. **Authorization Server cấp quyền; Resource Server thực thi quyền đó trên tài nguyên thực tế**.

## 6. Spring Security Servlet: cấu hình Resource Server JWT

Trong dự án **Spring Boot 3.4.5**, **Java 17** và **Spring Security 6**, để bảo vệ API nhận Bearer JWT, cần module **spring-boot-starter-oauth2-resource-server**. Ví dụ dưới đây cấu hình một API stateless và scope-based authorization, không có chức năng login redirect.

Cấu trúc Maven:

~~~text
resource-server-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/resource/ResourceServerApplication.java
    │   └── resources/application.yml
    └── test/java/demo/resource/ResourceServerApplicationTests.java
~~~

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>resource-server-demo</artifactId>
    <version>1.0.0</version>
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
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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

**src/main/resources/application.yml**:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/training
~~~

**Thay issuer-uri bằng issuer URI thật của IdP được tin cậy trước khi khởi động để xác minh token thực.** Giá trị **example.com** chỉ minh họa và không phải nhà cung cấp token hoạt động. Cấu hình **issuer-uri** cho phép Spring Security dùng metadata của issuer để tìm các khóa công khai/JWK và kiểm tra issuer; khả năng kết nối và thời điểm truy vấn metadata phụ thuộc phiên bản/cấu hình. Không bật xác minh token giả khi triển khai thật.

**src/main/java/demo/resource/ResourceServerApplication.java**:

~~~java
package demo.resource;

import java.util.List;
import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ResourceServerApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResourceServerApplication.class, args);
    }
}

@Configuration
class ApiSecurityConfiguration {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/invoices")
                            .hasAuthority("SCOPE_invoices.read")
                        .anyRequest().denyAll())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .sessionManagement(session -> session
                        .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                .csrf(AbstractHttpConfigurer::disable)
                .build();
    }
}

@RestController
class InvoiceController {
    @GetMapping("/api/invoices")
    Map<String, Object> invoices(@AuthenticationPrincipal Jwt jwt) {
        return Map.of(
                "owner", jwt.getSubject(),
                "items", List.of("INV-001"));
    }
}
~~~

**Giải thích lựa chọn trong code:**

- **oauth2ResourceServer(...jwt(...))** kích hoạt xử lý Bearer JWT. Không có **oauth2Login()**, nên API không tạo luồng redirect đăng nhập.
- **requestMatchers(...).hasAuthority("SCOPE_invoices.read")** yêu cầu scope cụ thể để đọc hóa đơn. Mặc định Spring Security có thể ánh xạ **scope** hoặc **scp** trong JWT thành GrantedAuthority với prefix **SCOPE_**. Nếu issuer dùng claim khác, phải cấu hình converter riêng.
- **@AuthenticationPrincipal Jwt jwt** lấy token đã được Spring Security xác thực trước khi controller thực thi. Không tự parse chuỗi Authorization rồi đọc claims chưa xác minh.
- **SessionCreationPolicy.STATELESS** chọn mô hình không dựa vào HttpSession để lưu trạng thái SecurityContext cho API Bearer.
- **csrf(...disable())** được dùng **chỉ vì ví dụ này nhận token qua Authorization header do client chủ động gắn, không sử dụng session/cookie để xác thực**. Nếu API còn dùng cookie hoặc hỗ trợ browser login cùng chain thì phải đánh giá CSRF lại, không sao chép tắt CSRF máy móc.
- **anyRequest().denyAll()** đảm bảo endpoint mới không vô tình mở public. Quy tắc cuối cùng là một lựa chọn bảo thủ trong bài học, không phải mọi API đều phải cấm tất cả đường dẫn khác.

Đây là một Resource Server minh họa đầy đủ mã Java. Để chạy **end-to-end với token thật**, phải cấu hình issuer có thể truy cập, khóa xác minh phù hợp và token có **scope invoices.read** dành cho API. Việc viết một token giả trong command line không làm token đó hợp lệ.

### 6.1. Kiểm tra bằng curl sau khi cấu hình IdP thật

Tại thư mục dự án:

~~~bash
mvn spring-boot:run
~~~

Khi API chạy và đã cấu hình issuer thật:

~~~bash
# Không có token: thường HTTP 401.
curl -i http://localhost:8080/api/invoices

# Thay ACCESS_TOKEN_HOP_LE bằng access token thật do IdP cấp.
curl -i http://localhost:8080/api/invoices \
  -H "Authorization: Bearer ACCESS_TOKEN_HOP_LE"
~~~

Nếu token hợp lệ, đúng issuer, chưa hết hạn và có scope **invoices.read**, response ví dụ:

~~~json
{"items":["INV-001"],"owner":"alice"}
~~~

Thứ tự các key JSON không được bảo đảm. **alice** ở đây chỉ là subject minh họa; thực tế phụ thuộc claim **sub** của token. Nếu token hợp lệ nhưng thiếu scope thì thường **403**. Với token sai chữ ký/hết hạn thì thường **401**. Khi test một issuer thực, cần kiểm tra thêm audience đúng API: ví dụ Java chưa khai báo audience validator tùy chỉnh, vì audience và giá trị cụ thể phải lấy từ hợp đồng của IdP/API.

## 7. Kiểm thử API không phụ thuộc IdP bên ngoài

**spring-security-test** có **jwt()** để giả lập Authentication JWT ở tầng MVC. Để test không phải gọi discovery endpoint của IdP, dùng **@MockitoBean** cho **JwtDecoder** trong Spring Boot 3.4.x/Spring Framework 6.2. Test này chứng minh luật **401/403/200 và kiểm soát scope**, nhưng không thay thế test thực với chữ ký và issuer.

**src/test/java/demo/resource/ResourceServerApplicationTests.java**:

~~~java
package demo.resource;

import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class ResourceServerApplicationTests {
    @Autowired
    MockMvc mvc;

    @MockitoBean
    JwtDecoder jwtDecoder;

    @Test
    void noTokenReturns401() throws Exception {
        mvc.perform(get("/api/invoices"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void validIdentityWithoutRequiredScopeReturns403()
            throws Exception {
        mvc.perform(get("/api/invoices")
                        .with(jwt().jwt(token -> token.subject("alice"))
                                .authorities(new SimpleGrantedAuthority(
                                        "SCOPE_other.read"))))
                .andExpect(status().isForbidden());
    }

    @Test
    void requiredScopeAllowsRequest() throws Exception {
        mvc.perform(get("/api/invoices")
                        .with(jwt().jwt(token -> token.subject("alice"))
                                .authorities(new SimpleGrantedAuthority(
                                        "SCOPE_invoices.read"))))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.owner").value("alice"))
                .andExpect(jsonPath("$.items[0]").value("INV-001"));
    }

    @Test
    void otherEndpointIsDeniedEvenWithValidIdentity()
            throws Exception {
        mvc.perform(get("/api/unknown")
                        .with(jwt().authorities(new SimpleGrantedAuthority(
                                "SCOPE_invoices.read"))))
                .andExpect(status().isForbidden());
    }
}
~~~

Chạy:

~~~bash
mvn test
~~~

Trong test, **jwt()** gắn principal JWT và authorities vào request kiểm thử; nó **không xác minh chữ ký thực**. Vì vậy bốn test trên kiểm tra authorization rules và controller; riêng logic chọn JWK, issuer, hạn sử dụng, audience cần **integration tests với decoder và token thực hoặc fixture được ký đúng**.

### Khi nào cần kiểm thử bổ sung?

- **JWT validation:** token sai chữ ký, sai issuer, hết hạn, chưa đến **nbf**, sai audience và key rotation.
- **Authority mapping:** một JWT thật có **scope: "invoices.read"** phải được chuyển thành **SCOPE_invoices.read**; claim khác chuẩn cần converter tường minh.
- **Authorization:** hai users có cùng scope nhưng không cùng quyền xem từng hóa đơn; phải kiểm tra sở hữu dữ liệu ở service layer.
- **Backend/network:** timeouts khi lấy metadata/JWK, JWK caching, rollover, clock skew, log bảo mật không lộ access token.
- **HTTP:** status 401, 403, **WWW-Authenticate**, CORS trong browser, gateway có forward đúng Authorization header.

Không lấy kết quả từ **.with(jwt())** làm bằng chứng rằng production đã xác minh JWT thành công.

## 8. Nếu access token là opaque token?

Không phải mọi access token đều là JWT. Với **opaque token**, token có thể là chuỗi không thể giải mã thành claims ở phía API. Resource Server thường gọi **token introspection endpoint** của Authorization Server (hoặc cơ chế được cấu hình tương đương) để biết token còn active và thông tin quyền.

Ví dụ cấu hình cơ bản theo OAuth2 Resource Server opaque tokens:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaque-token:
          introspection-uri: https://idp.example.com/oauth2/introspect
          client-id: resource-api
          client-secret: replace-with-real-secret
~~~

Đây là cú pháp minh họa và phải thay bằng endpoint/credentials thật; **không commit secret vào repository**. Khi dùng opaque thay JWT, filter chain phải bật cơ chế opaque tương ứng:

~~~java
// Chỉ là cấu hình thay thế phần oauth2ResourceServer(...) ở ví dụ.
http.oauth2ResourceServer(oauth2 ->
        oauth2.opaqueToken(Customizer.withDefaults()));
~~~

**Không bật cả JWT và opaque mà không thiết kế rõ cách phân loại token.** Với introspection, thời gian phản hồi/khả dụng của AS và cache có thể ảnh hưởng API. Với JWT, nhiều kiểm tra có thể thực hiện cục bộ theo JWK đã lấy/cached, nhưng việc thu hồi ngay lập tức khó hơn nếu hệ thống không có cơ chế bổ sung. Quyết định thuộc kiến trúc token của tổ chức, không phải thứ Resource Server tự suy từ độ dài chuỗi token.

## 9. Spring Security Servlet: cấu hình ứng dụng OAuth2/OIDC Login

Nếu ứng dụng là website cho user đăng nhập qua IdP, dependency cần quan tâm là **spring-boot-starter-oauth2-client**, thay cho hoặc thêm vào resource-server starter tùy vai trò. Cấu hình web login điển hình:

~~~java
@Bean
SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
    return http
            .authorizeHttpRequests(auth -> auth
                    .requestMatchers("/", "/assets/**").permitAll()
                    .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
}
~~~

**Đoạn trên là một trích đoạn cấu hình OAuth2 Client**, không thêm trực tiếp vào file SecurityFilterChain của ví dụ API ở mục 6. Nó chỉ chạy khi có dependency OAuth2 client, client registration và IdP hỗ trợ flow phù hợp.

Ví dụ client registration cho OIDC:

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          course-idp:
            provider: course-idp
            client-id: web-ui-client
            client-secret: replace-with-real-secret
            authorization-grant-type: authorization_code
            scope: openid,profile
        provider:
          course-idp:
            issuer-uri: https://idp.example.com/realms/training
~~~

Các giá trị là placeholder; cung cấp secret bằng secret manager/environment ở môi trường thật. Web app điều hướng user đến login endpoint của provider, xử lý callback (thường dạng **/login/oauth2/code/{registrationId}**), tạo Authentication cho user và duy trì session theo cấu hình. **oauth2Login()** xử lý đăng nhập người dùng; nó không chứng minh API đã bảo vệ Bearer JWT.

Để web app gọi API khác bằng access token, có thể cấu hình **oauth2Client()**, một **OAuth2AuthorizedClientManager** hoặc cơ chế quản lý authorized client tương ứng. Đó là một luồng **outbound** từ client đến resource server, không phải bộ lọc xác thực Bearer cho chính web UI.

## 10. Có thể cùng lúc là OAuth2 Client và Resource Server không?

**Có.** Một web application có thể:

1. Dùng **oauth2Login()** cho đường dẫn giao diện, đăng nhập user và tạo session.
2. Dùng **oauth2ResourceServer()** cho **/api/** để nhận Bearer access token từ client khác.
3. Dùng **oauth2Client()** khi gọi downstream API với token phù hợp.

Khi kết hợp, cách thiết kế phổ biến là **nhiều SecurityFilterChain**, áp dụng theo phạm vi và thứ tự rõ ràng. Ví dụ sơ đồ cấu hình minh họa (không phải file hoàn chỉnh đã khai báo mọi registration/decoder):

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http.securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(Customizer.withDefaults()))
            .sessionManagement(session -> session
                    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(AbstractHttpConfigurer::disable)
            .build();
}

@Bean
@Order(2)
SecurityFilterChain webChain(HttpSecurity http) throws Exception {
    return http.authorizeHttpRequests(auth -> auth
                    .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
}
~~~

Phải bổ sung các import như **@Order**, **Customizer**, **SessionCreationPolicy**, **AbstractHttpConfigurer**, và cấu hình client registration/issuer thực tế. Mọi chain cần được kiểm tra qua test với URL đúng: **/api/** phải đi qua Bearer auth, còn trang UI có thể redirect login. Quy tắc authorization API ở ví dụ này chỉ yêu cầu authenticated để minh họa chain selection; production phải kiểm tra scopes/permissions cụ thể.

**Cảnh báo khi dùng nhiều chain:** Spring Security chọn chain đầu tiên có **securityMatcher** phù hợp, không gộp tất cả các chain. Nếu một chain rộng đứng trước **/api/**, request API có thể rơi vào login redirect hoặc quy tắc phân quyền sai. Cần kiểm thử 401/403 cho API và 302 cho web UI riêng biệt.

**CSRF khác nhau theo mô hình:** các form và browser session của web app thường vẫn cần CSRF protection. API chỉ nhận Bearer header và không dùng cookie auth có thể xem xét tắt CSRF ở chain API. Không tắt toàn cục khi một ứng dụng hỗn hợp còn dùng session cookie cho các endpoint thay đổi trạng thái.

## 11. JWT validation và giới hạn quyền của Resource Server

Resource Server tin cậy token **chỉ sau khi** kiểm tra đầy đủ các điều kiện áp dụng:

| Hạng mục | Cần làm gì? |
| --- | --- |
| Chữ ký và thuật toán | Xác minh chữ ký bằng key tin cậy/đúng thuật toán, tránh chấp nhận “alg=none” hoặc một thuật toán không được phép |
| Issuer (**iss**) | So với issuer được cấu hình/đăng ký tin cậy |
| Thời gian (**exp**, **nbf**) | Từ chối token đã hết hạn hoặc chưa có hiệu lực theo clock/clock skew hợp lý |
| Audience (**aud**) | Kiểm tra token **dành cho API này**; cấu hình validator nếu API yêu cầu audience cụ thể |
| Subject (**sub**) | Liên kết danh tính; không mặc định sub là email hoặc quyền |
| Scopes/permissions | Ánh xạ claim của issuer sang authorities; kiểm tra quyền theo endpoint và tài nguyên thực |
| Key rotation | Theo dõi key ID, JWK và thời gian cache; kiểm tra đổi khóa an toàn |
| Thu hồi token | JWT tự xác minh có độ trễ thu hồi tùy thiết kế; cần expiry ngắn hoặc cơ chế bổ sung nếu nghiệp vụ yêu cầu |
| Log/transport | Dùng HTTPS; không đưa Bearer token vào URL, query string, log, trace public hoặc shared cache |

**Spring Security mặc định không thể đoán audience đúng cho mọi API.** Khi dùng issuer-uri, validation mặc định xử lý các điều kiện tiêu chuẩn như issuer và thời hạn, nhưng audience theo nghiệp vụ phải được khai báo/kiểm thử phù hợp. Một token hợp lệ nhưng dành cho **payments-api** không nên dùng để truy cập **invoices-api**, ngay cả khi cùng AS cấp.

JWT roles/scopes cũng không thay thế authorization theo đối tượng. Có **SCOPE_invoices.read** không có nghĩa được đọc hóa đơn của **mọi tài khoản**. Controller/service vẫn phải kiểm tra resource ownership hoặc policy cấp tài nguyên.

**Không cần mọi API dùng cùng claim authorities.** Mặc định Spring Security ánh xạ **scope/scp** sang **SCOPE_...**; nếu nhà phát hành dùng **roles**, **realm_access** hoặc claim tùy biến, cần cấu hình **JwtAuthenticationConverter** và xác minh test riêng. Không nên cho phép tất cả request chỉ vì JWT “hợp lệ về chữ ký”.

## 12. Lỗi thường gặp và cách phân biệt khi debug

| Hiện tượng | Kiểm tra |
| --- | --- |
| Gọi API không có token lại bị **302** tới login | Có thể request đi qua chain **oauth2Login()** thay vì resource-server chain |
| Gọi API trả **401** | Header Bearer thiếu/sai, issuer/JWK/signature/expiry không hợp lệ, token không được công nhận |
| API trả **403** dù token đã hợp lệ | Scope/authority thiếu hoặc rule phân quyền từ chối; cũng cần xem CSRF nếu dùng cookie |
| JWT trông “giải mã được” nhưng vẫn 401 | Base64 decode không phải signature validation; kiểm tra iss/aud/exp/algorithm/JWK |
| Web login thành công nhưng API 401 | Web app có session cookie, nhưng API cần access token đúng audience qua Authorization |
| Truyền ID token đến API như access token | Sai mục đích/audience, cần lấy **access token** dành cho API |
| Client có access token nhưng web page vẫn redirect | Web chain chưa có phiên đăng nhập; access token outbound không tự thiết lập web session |
| Đổi authorities trong test JWT nhưng production vẫn 403 | Test **.with(jwt())** không chứng minh converter thực tế; cần test claim mapping |
| API chạy được bằng curl nhưng browser gặp CORS | CORS browser độc lập với token validation; kiểm tra preflight/allowed headers |
| Session cookie hoạt động nhưng POST web 403 | Kiểm tra CSRF token và web session; không dùng CORS làm giải pháp thay CSRF |
| Token hết hạn và API 401 | Client phải xin token mới qua cơ chế được cấp; Resource Server không tự refresh cho client |
| Issuer không truy cập được/JWK bị lỗi | Xem discovery/JWK URL, proxy, TLS, key rotation, log đã che token và thời điểm load |

**Cách debug có thứ tự:** xác nhận request rơi đúng SecurityFilterChain → nhìn request có Bearer header hay cookie → xác định đây là Resource Server hay OAuth2 Login → nếu là API thì kiểm tra issuer/token validation → xem authorities/scope/audience → cuối cùng kiểm tra quyền theo resource và các chính sách CORS/CSRF áp dụng. Đừng sửa nhầm bằng cách bật cả hai login modes trên một chain mà chưa có contract rõ ràng.

## 13. Tự kiểm tra

1. Một mobile app có access token và gọi GET **/api/invoices**. Spring app cung cấp endpoint này làm vai trò gì? **Resource Server**.
2. Spring web app redirect user đến IdP, nhận authorization code và tạo session. Vai trò OAuth2 chính của app đó là gì? **OAuth2 Client**, có **OAuth2 Login**.
3. **ID token** và **access token** có thay thế nhau được không? **Không**; chúng có audience và mục đích khác nhau.
4. OAuth2 Resource Server có phải tự đưa user đến trang đăng nhập không? **Thông thường không**; API Bearer trả 401 khi thiếu token.
5. JWT hợp lệ nhưng thiếu **SCOPE_invoices.read** thường nhận gì? **403**, khi endpoint yêu cầu scope đó.
6. API có session cookie và POST từ browser. Có thể tắt CSRF vì đã bật Resource Server không? **Không được mặc định**; phải phân tích cơ chế xác thực được browser tự gửi.
7. Một web app vừa làm login UI vừa mở API cho mobile có thể cấu hình thế nào? **Hai SecurityFilterChain** với matcher và thứ tự rõ ràng, kiểm thử riêng.
8. Vì sao một token ký đúng vẫn có thể không được phép truy cập API? Vì có thể **sai issuer, audience, hết hạn hoặc thiếu quyền**.

**Ghi nhớ:** **OAuth2 Resource Server** nhận và xác minh **access token** của request để bảo vệ API; **OAuth2/OIDC Login application** dùng **authorization code flow** để đăng nhập user và thường giữ phiên web. Authorization Server phát hành token; Client yêu cầu token; Resource Server thực thi quyền. Khi thiết kế Spring Security Servlet, chọn đúng vai trò, token, SecurityFilterChain và kiểm tra audience/scope theo API.
