# Ranh giới giữa Spring Security Servlet, WebFlux, Authorization Server và hệ thống quản lý danh tính

Trong một ứng dụng web Java, nhiều thành phần đều được gọi chung là “bảo mật”: Spring Security, OAuth 2.0, OpenID Connect (OIDC), nhà cung cấp danh tính (IdP), máy chủ cấp quyền và hệ thống quản lý người dùng. Chúng giải quyết những vấn đề khác nhau. Hiểu ranh giới giúp chọn đúng cấu hình, xác định nơi kiểm tra quyền và tránh thiết kế một ứng dụng phải gánh trách nhiệm của cả hệ thống danh tính.

**Phạm vi bài học:** góc nhìn của ứng dụng **Spring MVC chạy trên Servlet stack**. Bài so sánh các ranh giới kiến trúc với Spring WebFlux, OAuth 2.0 Authorization Server và Identity Management; không triển khai một máy chủ cấp quyền hoặc một hệ thống IAM đầy đủ.

## 1. Spring Security Servlet thực sự chịu trách nhiệm gì?

Spring Security tích hợp vào **Servlet filter chain** của ứng dụng. Với Spring MVC, một HTTP request đi qua các Servlet filter bảo mật trước khi đến `DispatcherServlet` và controller.

- **Xác thực (authentication):** xác định danh tính hoặc xác thực bằng chứng do client gửi, chẳng hạn session hiện có, username/password, hay bearer access token.
- **Phân quyền (authorization):** quyết định request hoặc lời gọi method có được thực thi không, theo principal, authorities, đường dẫn và quy tắc nghiệp vụ.
- **Bảo vệ tương tác HTTP:** quản lý/khai thác security context, session khi áp dụng, CSRF, CORS integration, security headers, xử lý lỗi bảo mật và các cơ chế đăng nhập/đăng xuất tùy cấu hình.
- **Tích hợp với hệ thống ngoài:** chuyển hướng sang IdP để đăng nhập OIDC, hoặc kiểm tra access token do Authorization Server cấp.

Spring Security **không tự động** trở thành kho lưu trữ mọi tài khoản, hệ thống cấp phát nhân sự, máy chủ OAuth phát token hay nơi duy nhất quyết định mọi quyền nghiệp vụ. Một ứng dụng có thể sử dụng dịch vụ khác để xác thực nhưng vẫn phải kiểm soát các hành động trên dữ liệu của chính nó.

```text
HTTP request
   |
Servlet container (Tomcat/Jetty/...)
   |
Servlet FilterChain
   +-- Spring Security: DelegatingFilterProxy
   |      -> FilterChainProxy -> SecurityFilterChain phù hợp
   |      -> xác thực / nạp SecurityContext / phân quyền / xử lý lỗi
   |
DispatcherServlet -> Controller -> Service -> dữ liệu nghiệp vụ
```

Các tên quan trọng trong Servlet stack là `HttpServletRequest`, `HttpServletResponse`, `HttpSecurity`, `SecurityFilterChain`, `Authentication` và `SecurityContextHolder`. Theo chiến lược mặc định phổ biến, `SecurityContextHolder` gắn context với thread hiện tại; không được giả định context tự đi theo mọi thread hoặc tác vụ bất đồng bộ. Việc lưu context giữa các request còn tùy cơ chế như HTTP session hoặc bearer token, không phải thuộc tính cố định của mọi ứng dụng Spring Security.

**Điểm chặn đúng:** Spring Security kiểm tra quyền ở ranh giới HTTP và có thể thêm kiểm tra ở service/method; các ràng buộc như “chỉ được sửa đơn hàng thuộc tenant hiện tại” vẫn cần được thực thi tại tầng nghiệp vụ hoặc truy cập dữ liệu.

## 2. Ranh giới Servlet và WebFlux

Spring MVC/Servlet và Spring WebFlux là **hai mô hình xử lý web khác nhau**. Cả hai đều có thể dùng Spring Security nhưng không dùng chung nguyên xi bộ filter, API cấu hình hay cách mang security context.

| Khía cạnh | Spring MVC + Servlet | Spring WebFlux |
|---|---|---|
| Nền web | Servlet API, request/response | Reactive HTTP, `ServerWebExchange` |
| Chuỗi bảo mật | Servlet `Filter`, `FilterChainProxy` | Reactive `WebFilter`, `WebFilterChainProxy` |
| Cấu hình HTTP | `HttpSecurity` → `SecurityFilterChain` | `ServerHttpSecurity` → `SecurityWebFilterChain` |
| Context | `SecurityContextHolder`, thường dựa trên thread; có tích hợp truyền context khi cần | Reactor `Context` / `ReactiveSecurityContextHolder` |
| Hướng lập trình | Controller MVC, xử lý servlet | `Mono`/`Flux`, chuỗi reactive |
| Session | `HttpSession` khi có session | `WebSession` khi có session |

Không chuyển đoạn mã dùng `HttpSecurity`, `HttpServletRequest`, `OncePerRequestFilter` sang WebFlux rồi kỳ vọng nó bảo vệ reactive route; chiều ngược lại cũng vậy. Khi tích hợp nghiệp vụ dùng `WebClient` trong một ứng dụng MVC, ứng dụng **vẫn là Servlet application**. Chỉ có thư viện Reactor/WebClient trong classpath không làm filter chain tự biến thành WebFlux.

Với Spring Boot, khi có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, cấu hình tự động web thông thường **ưu tiên Spring MVC**. Cần kiểm tra loại ứng dụng và bộ starter thay vì suy từ tên lớp đang import. Chủ động chạy reactive web server là một quyết định kiến trúc riêng.

**Điểm giống nhau về nguyên tắc:** cả hai đều có thể bảo vệ route, xác thực bearer token, làm OAuth2 client hoặc resource server và áp dụng method security. Điểm khác là ngữ cảnh request, API cấu hình và cơ chế lan truyền context.

## 3. Ranh giới giữa ứng dụng, OAuth2 Authorization Server và Resource Server

OAuth 2.0 phân tách vai trò. Một sản phẩm thực tế có thể đảm nhận nhiều vai trò, nhưng không được nhập nhằng trách nhiệm:

| Vai trò | Nhiệm vụ | Ví dụ trong hệ thống |
|---|---|---|
| **OAuth2 Client** | Xin quyền và nhận token theo flow phù hợp; dùng token để gọi resource | Web application/backend hoặc ứng dụng mobile |
| **Authorization Server (AS)** | Xác thực/ủy quyền theo chính sách, cấp access token, có thể cấp refresh token, cung cấp metadata/JWK/introspection tùy triển khai | Dịch vụ cấp token trung tâm |
| **Resource Server (RS)** | Nhận request kèm access token, kiểm tra token và thực thi quyền truy cập tài nguyên | REST API Spring MVC |
| **Resource Owner** | Chủ thể có thể cấp quyền truy cập tài nguyên trong flow tương ứng | Thường là người dùng |

**Spring Security Servlet là thư viện tích hợp phía ứng dụng**: có thể làm OAuth2 Client (`oauth2Login`/`oauth2Client`), hoặc cấu hình ứng dụng làm Resource Server (`oauth2ResourceServer`). Việc bật Resource Server **không** tạo ra endpoint cấp token `/token`, cấp mã ủy quyền `/authorize` hay quản lý client. Nếu cần tự vận hành Authorization Server thì đó là thành phần/sản phẩm được thiết kế và cấu hình riêng.

### Luồng A: ứng dụng MVC đăng nhập qua OpenID Connect

```text
[Browser] -- mở trang --> [Ứng dụng MVC: OIDC Client]
    |                              |
    | <- redirect tới IdP/AS ------|
    | -- xác thực và đồng ý (nếu cần) --> [IdP / Authorization Server]
    | <- redirect với code --------|
    |                              |-- đổi code lấy token --> [AS]
    |                              |-- xác minh ID token/user info theo OIDC
    |                              |-- thiết lập authentication/session ứng dụng
    | -- request + cookie ứng dụng -> [MVC + Spring Security]
```

OIDC xây dựng trên OAuth 2.0 để cung cấp thông tin xác thực danh tính. `ID token` dành cho **client/relying party** xác nhận sự kiện đăng nhập và danh tính theo OIDC; không dùng ID token như access token để bảo vệ API. Người dùng đăng nhập một lần với IdP cũng không có nghĩa mọi ứng dụng chia sẻ cùng một `HttpSession`: mỗi ứng dụng thường quản lý session riêng.

### Luồng B: client gọi REST API bằng access token

```text
[Client] -- xin token bằng flow phù hợp --> [Authorization Server]
[Client] <-- access token ---------------- [Authorization Server]
[Client] -- Authorization: Bearer ... --> [Servlet Resource Server]
[Servlet Resource Server] -- kiểm chứng token + quyền --> [REST API]
```

Đối với JWT, Resource Server cần kiểm tra chữ ký dựa trên key tin cậy, issuer, hạn dùng và các điều kiện thích hợp khác; **audience phải được kiểm tra theo tài nguyên/API mong đợi** nếu đó là một ràng buộc của hệ thống, không mặc định cho rằng mọi cấu hình đều tự kiểm tra `aud`. Với opaque token, Resource Server thường dùng introspection endpoint của Authorization Server. Sau khi token hợp lệ, ứng dụng vẫn kiểm tra scope/authority và quyền nghiệp vụ. Không tự tin mọi claim do client tự gửi nếu chưa xác minh token và nguồn cấp tin cậy.

**Ba loại token không thay thế nhau:**

- **Access token:** trình cho Resource Server; có scope/audience/thời hạn phù hợp với API.
- **ID token (OIDC):** cung cấp sự kiện và claim xác thực cho OIDC Client; không dùng để gọi API như access token.
- **Refresh token:** được client đủ điều kiện giữ an toàn để xin access token mới; không trình trực tiếp cho Resource Server như bearer access token.

## 4. Ranh giới với Identity Provider và Identity Management

Ba thuật ngữ gần nhau nhưng không hoàn toàn trùng nhau:

- **Identity Provider (IdP):** xác thực người dùng, cung cấp phiên đăng nhập tập trung, giao thức như OIDC hoặc SAML; một IdP thường đồng thời có khả năng làm OAuth2 Authorization Server nhưng về mặt khái niệm hai vai trò khác nhau.
- **Identity Management / IAM / hệ thống quản lý danh tính:** quản lý vòng đời tài khoản, tổ chức, nhóm, chính sách mật khẩu/MFA, cấp phát/thu hồi tài khoản, kết nối HR/directory hoặc đồng bộ provisioning (ví dụ SCIM). Một số chức năng quản trị có thể nằm trong cùng sản phẩm IdP.
- **Spring Security của ứng dụng:** dùng kết quả xác thực, ánh xạ authorities, duy trì security context trong ứng dụng và quyết định truy cập endpoint/method/dữ liệu.

Ví dụ: hệ thống HR tạo nhân sự; IAM cấp tài khoản và nhóm; IdP xác thực MFA; AS cấp access token; API Servlet kiểm tra token và quyền `SCOPE_orders.read`; service chỉ trả về đơn hàng thuộc tenant và người dùng được phép xem. Không thành phần nào trong chuỗi đó tự động làm thay toàn bộ các bước còn lại.

**Các ranh giới dễ bỏ sót:**

1. **Đăng nhập tập trung ≠ phân quyền nghiệp vụ tập trung.** Nhóm “sales” từ IdP có thể giúp ánh xạ một authority, nhưng điều kiện sở hữu đơn hàng hoặc trạng thái phê duyệt phải được xác thực trong ứng dụng.
2. **Khóa tài khoản ≠ JWT đã phát hành lập tức vô hiệu.** JWT tự kiểm chứng có thể còn hiệu lực tới khi hết hạn, trừ khi kiến trúc có thu hồi/kiểm tra bổ sung; cần cân nhắc TTL ngắn, introspection hoặc chính sách thu hồi khi yêu cầu nghiệp vụ đòi hỏi.
3. **Logout ứng dụng ≠ logout toàn bộ SSO.** Xóa local session/cookie không nhất thiết chấm dứt phiên IdP hoặc hủy mọi access token. Muốn single logout/back-channel logout cần thiết kế giao thức và vận hành tương ứng.
4. **Đồng bộ user/group ≠ đồng bộ quyền tức thời.** Claim trong token là ảnh chụp tại thời điểm cấp; quyền có thể thay đổi sau đó. Thiết kế thời hạn token, cập nhật mapping và kiểm tra quyền nhạy cảm phù hợp.
5. **Một tổ chức có nhiều issuer/tenant.** Không chấp nhận token chỉ vì chữ ký hợp lệ; cần ràng buộc issuer, audience, token type và tenant theo cấu hình tin cậy, đặc biệt ở API đa khách hàng.

## 5. Ví dụ cấu hình: Servlet Resource Server bảo vệ API

Giả sử một **ứng dụng Spring Boot MVC chỉ phục vụ REST API**. Client đã lấy OAuth2 access token từ Authorization Server ngoài. Ứng dụng này không cấp token, không triển khai trang đăng nhập và không tự vận hành kho danh tính.

Dependencies tiêu biểu: `spring-boot-starter-web` và `spring-boot-starter-oauth2-resource-server`. Với Java 17+ và phiên bản Spring Boot/Spring Security tương thích, tạo tệp `src/main/java/example/security/ServletApiSecurityConfig.java`:

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ServletApiSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public").permitAll()
                .requestMatchers("/api/**").hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(AbstractHttpConfigurer::disable)
            .build();
    }
}
```

Ví dụ cấu hình issuer trong `application.yml` (URL chỉ là địa chỉ mẫu; phải thay bằng issuer tin cậy thực tế):

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/issuer
```

Ý nghĩa:

- `oauth2ResourceServer(...jwt(...))` xác thực JWT access token theo cấu hình issuer/JWK; **không cấp** JWT.
- `hasAuthority("SCOPE_orders.read")` minh họa mapping thông thường từ scope `orders.read` thành authority có tiền tố `SCOPE_`. Quyền nghiệp vụ như sở hữu tài nguyên phải kiểm tra thêm.
- `STATELESS` không lưu security context cho các request sau trong HTTP session của cơ chế này; mỗi request mang token cần thiết.
- `csrf(...disable)` **chỉ phù hợp với giả định của ví dụ**: API không dựa vào cookie/session do trình duyệt tự gửi để xác thực, mà dùng bearer token do client chủ động đặt trong `Authorization`. Nếu API còn dùng cookie/session hoặc kiểu credential tự động gửi, phải đánh giá và cấu hình CSRF phù hợp thay vì sao chép lệnh tắt này.
- `denyAll()` chặn các đường dẫn ngoài API được minh họa; thay đổi routing theo yêu cầu hệ thống, tránh vô tình để lộ endpoint.

Đây là một **lớp cấu hình dùng trong dự án Spring Boot**, không phải chương trình Java độc lập chạy chỉ với `javac`. Để chạy cần project, dependency, cấu hình issuer hoạt động và controller phù hợp. Ví dụ không tạo ra stdout cố định: kết quả quan sát là HTTP `200`/`401`/`403` tùy controller, token và quyền.

**Cẩn thận với HTTP status:** request không có bằng chứng xác thực hợp lệ thường nhận `401 Unauthorized`; request đã xác thực nhưng thiếu quyền thường nhận `403 Forbidden`. Với public endpoint, controller vẫn tự quyết định mã kết quả; không phải mọi request hợp lệ đều là `200`.

## 6. Cùng mục tiêu trên WebFlux: cấu hình khác

Đoạn sau **chỉ là ví dụ đối chiếu ở ứng dụng WebFlux riêng**, không thêm vào dự án Servlet ở mục 5. Với `spring-boot-starter-webflux` và starter Resource Server tương ứng, dùng `ServerHttpSecurity` và `SecurityWebFilterChain`:

```java
package example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveApiSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/api/public").permitAll()
                .pathMatchers("/api/**").hasAuthority("SCOPE_orders.read")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .build();
    }
}
```

Quy tắc về CSRF và audience của mục 5 **vẫn áp dụng**. Không sao chép kiểu mã này vào Servlet security filter chain. Reactive service có cơ chế lưu truyền authentication bằng Reactor context; tránh xử lý như thể mọi bước chạy trên một thread cố định.

## 7. Chọn vai trò đúng cho tình huống

| Nhu cầu thực tế | Thành phần chính | Phần việc vẫn thuộc Spring Security Servlet |
|---|---|---|
| Website MVC cho người dùng đăng nhập qua SSO | OIDC IdP/AS + ứng dụng làm OIDC Client | Login callback, security context, session, CSRF, phân quyền route/method |
| REST API nhận `Authorization: Bearer ...` | AS phát token + ứng dụng làm Resource Server | Xác thực token, kiểm tra scope/authority, quyền dữ liệu |
| Tự xây dịch vụ cấp access/refresh token | Authorization Server chuyên trách | Nếu AS chạy bằng Servlet vẫn cần bảo vệ các endpoint của AS; không giải quyết được bằng cấu hình Resource Server đơn lẻ |
| Quản lý nhân sự, MFA, lifecycle user, nhóm | IAM/IdP/directory/SCIM | Tích hợp danh tính và ánh xạ claim đáng tin sang quyền ứng dụng |
| Xử lý HTTP hoàn toàn reactive | Spring WebFlux + Spring Security reactive | Dùng `SecurityWebFilterChain`, `ServerHttpSecurity`, Reactor context |
| Ứng dụng MVC chỉ cần gọi API reactive bằng `WebClient` | Spring MVC/Servlet, WebClient là HTTP client | Giữ `SecurityFilterChain`; xử lý token khi gọi downstream đúng trách nhiệm OAuth2 client |

Một ứng dụng cũng có thể vừa là **OIDC Client** (đăng nhập người dùng), vừa là **OAuth2 Client** (gọi API downstream), hoặc đồng thời có API làm **Resource Server**. Điều này là tổ hợp vai trò trong cùng ứng dụng, không xóa ranh giới giao thức và trách nhiệm.

## 8. Các sai lầm thường gặp và cách kiểm tra

**Sai lầm 1 — “Dùng OAuth2 thì ứng dụng tự có máy chủ cấp token.”**  
Không đúng. `oauth2Login` và `oauth2ResourceServer` là khả năng phía client/resource server của Spring Security. Kiểm tra hệ thống thực sự nào sở hữu authorization endpoint, token endpoint, khóa ký và chính sách phát hành.

**Sai lầm 2 — “WebFlux và MVC chỉ khác return type `Mono`.”**  
Không đúng. Khác cả HTTP runtime và security filter chain. Kiểm tra starter, loại web application và bean cấu hình. Khi dùng Servlet hãy tìm `SecurityFilterChain`; khi dùng WebFlux hãy tìm `SecurityWebFilterChain`.

**Sai lầm 3 — “JWT hợp lệ nghĩa là user làm được mọi thao tác.”**  
Không đúng. Cần kiểm tra issuer/audience đúng resource, hạn dùng, scope/authority, và quyền với object cụ thể. Một người có scope đọc đơn hàng không đương nhiên đọc được đơn của tenant khác.

**Sai lầm 4 — “ID token có thể gửi tới mọi API thay access token.”**  
Không đúng. ID token phục vụ OIDC Client; API nhận access token hướng tới resource tương ứng. Tách validation và audience theo vai trò.

**Sai lầm 5 — “SSO đã bật thì không cần bảo vệ session/CSRF trong website.”**  
Không đúng. Web MVC vẫn có cookie/session và những request thay đổi trạng thái. SSO là nguồn xác thực danh tính, không thay thế cơ chế bảo vệ HTTP của ứng dụng.

**Sai lầm 6 — “Quyền từ IAM luôn chính xác tức thời.”**  
Không chắc. Token có TTL, cache, mapping và độ trễ provisioning. Xác định SLA thu hồi truy cập và vị trí kiểm tra quyền nhạy cảm.

**Sai lầm 7 — “API báo 302 về trang đăng nhập là xác thực bearer đúng.”**  
Với API thuần JSON/bearer, redirect đến form login thường là dấu hiệu chọn sai entry point hoặc phối hợp filter chain chưa phù hợp. Xác định API dùng bearer token hay browser session; cấu hình response khi chưa xác thực cho đúng loại client.

## 9. Quy trình xác định ranh giới trước khi triển khai

1. **Xác định HTTP stack:** Servlet/Spring MVC hay WebFlux, có dùng kết hợp WebClient không; chọn đúng security chain và starter.
2. **Xác định ai xác thực người dùng:** tài khoản nội bộ, IdP OIDC/SAML, hay token đã có; vẽ luồng browser redirect hoặc bearer.
3. **Xác định ai cấp token:** Authorization Server nào, issuer, JWK, audience, scope, expiry và cơ chế thu hồi.
4. **Xác định vai trò ứng dụng:** OIDC/OAuth Client, Resource Server, hay có nhiều vai trò; tránh vô tình trộn ID token/access token.
5. **Xác định nơi ra quyết định quyền:** endpoint/method policy ở Spring Security, ownership/tenant/state ở service hoặc data layer.
6. **Xác định trạng thái bảo mật của trình duyệt:** cookie/session, CSRF, CORS, local logout và SSO logout; đừng tắt cơ chế bảo vệ chỉ để request chạy được.
7. **Kiểm thử ranh giới âm tính:** thiếu token, sai issuer, sai audience, hết hạn, thiếu scope, sai tenant, user bị vô hiệu hóa và token cũ; quan sát đúng HTTP status và hành vi thu hồi theo thiết kế.

### Tự kiểm tra

- API Servlet nhận JWT từ một IdP: **ai cấp token, ai kiểm chứng, ai quyết định người dùng được xem đơn hàng số 42?** AS cấp, Resource Server kiểm chứng, ứng dụng kiểm tra scope và quyền trên đơn hàng.
- Một dự án MVC gọi API bằng `WebClient`: **có phải đổi sang `ServerHttpSecurity`?** Không; HTTP server vẫn dùng Servlet stack.
- Người dùng logout khỏi một web app OIDC: **mọi API bearer token và mọi phiên SSO đã bị hủy chưa?** Chưa thể kết luận; phụ thuộc cơ chế session, token revocation và logout liên ứng dụng đã triển khai.
- Một token JWT chữ ký đúng nhưng `aud` thuộc API khác: **có chấp nhận không?** Không; Resource Server cần ràng buộc token với tài nguyên mong đợi theo chính sách validation.

**Ghi nhớ:** Spring Security Servlet bảo vệ **request và thao tác của ứng dụng Servlet**; WebFlux có security runtime riêng; Authorization Server **phát hành/ủy quyền token**; IdP/IAM **xác thực và quản lý danh tính**. Chúng phối hợp qua giao thức và trust boundary rõ ràng, còn phân quyền cuối cùng trên dữ liệu nghiệp vụ vẫn phải được kiểm soát bởi ứng dụng sở hữu dữ liệu.