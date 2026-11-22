# JwtAuthenticationProvider và OpaqueTokenAuthenticationProvider

Trong **Spring Security OAuth 2.0 Resource Server** dành cho ứng dụng Servlet, hai thành phần **`JwtAuthenticationProvider`** và **`OpaqueTokenAuthenticationProvider`** chịu trách nhiệm xác thực **Bearer access token** của request. Cả hai đều triển khai cơ chế `AuthenticationProvider`, nhưng sử dụng hai cách kiểm tra token khác nhau:

- **`JwtAuthenticationProvider`** dùng **`JwtDecoder`** để giải mã, xác minh và chuyển đổi một JWT access token thành một đối tượng `Authentication` đã xác thực.
- **`OpaqueTokenAuthenticationProvider`** dùng **`OpaqueTokenIntrospector`** để xác minh token qua cơ chế **token introspection** rồi tạo một đối tượng `Authentication` từ các thuộc tính và quyền được trả về.

Hiểu được hai provider này giúp giải thích tại sao cùng một HTTP header `Authorization: Bearer ...` lại có thể đi qua những cơ chế xác thực khác nhau, vì sao `401 Unauthorized` khác `403 Forbidden` và nên tùy biến điểm nào nếu Authorization Server phát hành các claim hoặc scope đặc thù.

> **Phạm vi:** Bài tập trung vào chuỗi xử lý **Servlet** của Spring Security Resource Server: request → filter → authentication manager/provider → security context → authorization → controller. Cấu hình JWT và opaque token được minh họa như **hai lựa chọn riêng** cho một API.

## 1. Vai trò của provider trong kiến trúc Resource Server

Xét ứng dụng Orders API, một **Resource Server** không tự phát hành access token mà nhận token do **Authorization Server** phát hành cho client:

~~~text
Client                    Authorization Server                  Orders API
   |                               |                                |
   |--- Xin access token --------->|                                |
   |<-- Access token --------------|                                |
   |                                                                |
   |--- GET /api/orders ------------------------------------------->|
   |    Authorization: Bearer <access-token>                        |
   |                                                                |
   |                            BearerTokenAuthenticationFilter    |
   |                                        |                       |
   |                               AuthenticationManager            |
   |                                        |                       |
   |                        AuthenticationProvider đã cấu hình       |
   |                          /                     \               |
   |          JwtAuthenticationProvider      OpaqueTokenAuthenticationProvider
   |                   |                         |                  |
   |               JwtDecoder             OpaqueTokenIntrospector   |
   |                   |                         |                  |
   |           Kiểm tra JWT             Introspect access token      |
   |                          \                     /               |
   |                           Authentication hợp lệ?               |
   |                                      |                         |
   |                         Authorization (quyền API)              |
   |                                      |                         |
   |<--------------------- 200 / 401 / 403 -------------------------|
~~~

**Hai nhánh được biểu diễn cạnh nhau để so sánh:** một request thông thường đi vào nhánh provider được chọn bởi cấu hình `AuthenticationManager` của chuỗi filter. Không nên hiểu Spring Security mặc định thử JWT rồi tự động đổi sang introspection nếu JWT không hợp lệ.

### Mỗi thành phần chịu trách nhiệm gì?

| Thành phần | Nhiệm vụ |
| --- | --- |
| `FilterChainProxy` và `SecurityFilterChain` | Chọn, sắp xếp các security filter áp dụng cho request |
| `BearerTokenAuthenticationFilter` | Tìm bearer token trong request và đưa yêu cầu xác thực tới `AuthenticationManager` |
| `BearerTokenAuthenticationToken` | Đối tượng `Authentication` **chưa xác thực**, mang chuỗi bearer token từ request |
| `AuthenticationManager` / `ProviderManager` | Điều phối việc xác thực tới `AuthenticationProvider` phù hợp |
| `JwtAuthenticationProvider` | Xác thực JWT bằng `JwtDecoder` và chuyển JWT sang `Authentication` |
| `OpaqueTokenAuthenticationProvider` | Xác thực bằng `OpaqueTokenIntrospector` và dựng `Authentication` từ kết quả introspection |
| `SecurityContextHolder` / `SecurityContext` | Cung cấp thông tin xác thực đã được chấp nhận cho phần xử lý tiếp theo của request |
| `AuthorizationFilter` và cơ chế method security | Dùng `Authentication` cùng chính sách quyền để cho phép hoặc từ chối truy cập |

Đây là hai giai đoạn khác nhau:

1. **Authentication** hỏi “Token này có được tin cậy để nhận diện chủ thể và quyền đi kèm không?”
2. **Authorization** hỏi “Chủ thể đã xác thực có được thực hiện thao tác trên endpoint hoặc tài nguyên cụ thể không?”

Một JWT có chữ ký hợp lệ hoặc một token introspection trả `active: true` **không tự động cấp quyền** để đọc mọi bản ghi của API.

## 2. Chuỗi xử lý Servlet trước khi tới provider

Khi request đi vào ứng dụng có Spring Security Servlet:

1. Servlet container gọi chuỗi filter có Spring Security, thông qua `DelegatingFilterProxy` và `FilterChainProxy`.
2. Spring Security xác định `SecurityFilterChain` phù hợp request. Một ứng dụng có thể định nghĩa nhiều chain với `securityMatcher(...)` và thứ tự `@Order`.
3. Trong chain cấu hình OAuth 2.0 Resource Server, `BearerTokenAuthenticationFilter` dùng `BearerTokenResolver` (thường là `DefaultBearerTokenResolver`) để lấy bearer token, chủ yếu từ header `Authorization`.
4. Nếu có token, filter tạo `BearerTokenAuthenticationToken`, rồi gọi `AuthenticationManager.authenticate(...)`.
5. Manager chuyển yêu cầu tới provider đã đăng ký. Provider kiểm tra token, dựng một `Authentication` hợp lệ hoặc ném ngoại lệ xác thực.
6. Khi thành công, filter thiết lập `SecurityContext` cho request và tiếp tục chuỗi filter. Sau đó cơ chế authorization đánh giá quyền.
7. Khi xác thực thất bại, Resource Server thường trả phản hồi **401** theo cơ chế Bearer. Khi token hợp lệ nhưng không đủ quyền, tầng authorization thường trả **403**.

Sơ đồ trình tự:

~~~mermaid
sequenceDiagram
    autonumber
    participant Client
    participant F as BearerTokenAuthenticationFilter
    participant M as AuthenticationManager
    participant P as AuthenticationProvider
    participant A as AuthorizationFilter
    participant C as Controller

    Client->>F: GET /api/orders với Authorization: Bearer ...
    F->>F: BearerTokenResolver trích xuất token
    F->>M: authenticate(BearerTokenAuthenticationToken)
    M->>P: authenticate(...)
    alt Token hợp lệ
        P-->>M: Authentication đã xác thực
        M-->>F: Authentication
        F->>F: Gán Authentication vào SecurityContext
        F->>A: Tiếp tục chain
        alt Đủ quyền
            A->>C: Cho request đi tiếp
            C-->>Client: 200 OK + dữ liệu
        else Không đủ quyền
            A-->>Client: 403 Forbidden
        end
    else Token không hợp lệ
        P-->>M: AuthenticationException
        M-->>F: Lỗi xác thực
        F-->>Client: 401 Unauthorized
    end
~~~

**Nếu request không mang bearer token**, filter có thể tiếp tục chain mà chưa tạo `Authentication` từ bearer token. Sau đó, nếu endpoint yêu cầu xác thực, cơ chế bảo vệ endpoint vẫn sẽ từ chối. Điều này khác với việc token **có mặt nhưng sai** và provider từ chối trong bước xác thực.

Ngoài ra, lỗi phân tích bearer token từ header có thể phát sinh ngay tại `BearerTokenResolver`, trước khi bất kỳ provider nào được gọi.

### Vì sao cùng một `BearerTokenAuthenticationToken`?

`BearerTokenAuthenticationToken` là đối tượng bao bọc **chuỗi bearer token ban đầu**. Nó không phải `JwtAuthenticationToken` và cũng không phải `BearerTokenAuthentication` đã được xác thực.

Điểm dễ nhầm là **cả `JwtAuthenticationProvider` lẫn `OpaqueTokenAuthenticationProvider` đều có thể hỗ trợ đầu vào `BearerTokenAuthenticationToken`**. Vì vậy:

- Spring Security không lựa chọn giữa hai provider chỉ bằng `supports(...)` dựa trên việc token trông giống JWT hay opaque.
- Việc chọn kiểu xác thực cần được thiết kế qua cấu hình Resource Server, chain hoặc `AuthenticationManagerResolver` phù hợp.
- Không nên biến câu hỏi “JWT hay opaque?” thành phép thử tùy tiện dựa trên số dấu chấm trong chuỗi; cấu trúc token không thay thế hợp đồng và chính sách của issuer.

## 3. `JwtAuthenticationProvider`: xác thực token JWT

`JwtAuthenticationProvider` nhận `BearerTokenAuthenticationToken` rồi dùng `JwtDecoder` để chuyển chuỗi token thành đối tượng `Jwt` **đã qua xác minh**.

Một chuỗi JWT ký theo JWS compact thường có dạng:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

Payload minh họa:

~~~json
{
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "scope": "orders.read orders.export"
}
~~~

Payload trên chỉ là **ví dụ claim JSON**; riêng việc Base64URL-decode và đọc được payload không khiến token được tin cậy.

### 3.1. Những bước bên trong JWT provider

~~~mermaid
flowchart TD
    A["BearerTokenAuthenticationToken"] --> B["JwtAuthenticationProvider"]
    B --> C["JwtDecoder.decode(token)"]
    C --> D{"JWT hợp lệ?"}
    D -- "Không" --> E["AuthenticationException / Bearer 401"]
    D -- "Có" --> F["Jwt: header + claims đã xác minh"]
    F --> G["JwtAuthenticationConverter"]
    G --> H["JwtAuthenticationToken"]
    H --> I["AuthenticationManager trả Authentication"]
    I --> J["SecurityContext, rồi kiểm tra quyền API"]
~~~

Thành phần chính:

**`JwtDecoder`** chịu trách nhiệm giải mã và xác minh token theo cấu hình. Với `NimbusJwtDecoder` phổ biến, điều này bao gồm việc xác minh chữ ký JWS bằng khóa phù hợp cùng các token validator; API còn cần cấu hình xác thực **issuer, thời hạn, audience** và các điều kiện cần thiết với issuer của mình.

**`JwtAuthenticationConverter`** nhận `Jwt` hợp lệ để tạo `AbstractAuthenticationToken`. Cấu hình mặc định thường tạo `JwtAuthenticationToken`, ánh xạ `scope` hoặc `scp` sang `GrantedAuthority` có tiền tố `SCOPE_`.

**`JwtAuthenticationToken`** thường chứa:

- **Principal:** đối tượng `Jwt`.
- **Authorities:** các quyền đã chuyển đổi, ví dụ `SCOPE_orders.read`.
- **Name:** mặc định thường lấy từ `sub`, trừ khi converter được tùy chỉnh.
- **Token attributes:** có thể truy cập qua API của lớp token authentication.

Ví dụ trong controller:

~~~java
import java.time.Instant;
import java.util.List;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class JwtProfileController {

    @GetMapping("/api/profile")
    String currentProfile(
            org.springframework.security.core.annotation.AuthenticationPrincipal
            Jwt jwt) {

        String subject = jwt.getSubject();
        Instant expiresAt = jwt.getExpiresAt();
        List<String> audiences = jwt.getAudience();
        return "Subject: " + subject;
    }
}
~~~

Ví dụ sử dụng `@AuthenticationPrincipal Jwt` **phù hợp khi ứng dụng chọn JWT Resource Server**. Nếu API chuyển sang opaque token, principal có thể không còn là `Jwt`, nên cần thay hợp đồng controller hoặc dùng abstraction chung.

### 3.2. Kiểm tra chữ ký, thời gian và issuer

JWT provider không chỉ tách chuỗi theo dấu chấm. Trong luồng thông thường:

1. Decoder đọc JOSE header và payload có cấu trúc hợp lệ.
2. Decoder xác minh thuật toán/chữ ký bằng khóa tin cậy được cấu hình. Với issuer hỗ trợ JWKS, khóa công khai có thể được lấy từ JWKS endpoint và làm mới khi cần.
3. Các validator kiểm tra điều kiện liên quan, chẳng hạn `exp`, `nbf` và `iss`; chính sách ứng dụng cần quy định rõ `aud` và claim khác phải kiểm tra.
4. Khi xác minh thành công, `JwtAuthenticationConverter` mới chuyển claim đã được chấp nhận thành danh tính/quyền.

`exp` và `nbf` thường dùng giá trị **NumericDate (giây Unix epoch)** trong JWT JSON. Cơ chế Java có thể đưa chúng về `Instant` để kiểm tra thời gian. Biên dung sai clock skew nếu được cấu hình là khoảng sai lệch đồng hồ chấp nhận được, **không phải thao tác gia hạn JWT**.

Chữ ký hợp lệ chưa đủ nếu token:

- Đã hết hạn.
- Được phát hành bởi issuer khác.
- Dành cho audience khác (ví dụ Payments API thay vì Orders API).
- Thiếu scope/claim cần cho endpoint hoặc không được phép truy cập đối tượng cụ thể.

### 3.3. Chuyển đổi scope và principal name

Ví dụ issuer phát hành claim:

~~~json
{
  "sub": "user-42",
  "preferred_username": "alice",
  "scope": "orders.read orders.write"
}
~~~

Mặc định, Spring Security thường tạo các authorities như:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

Nếu issuer dùng claim `permissions` thay vì `scope`, ứng dụng cần định nghĩa bộ chuyển đổi tương ứng. Khi cần thay tên principal thành `preferred_username`, có thể cấu hình `JwtAuthenticationConverter`.

Ví dụ:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;

@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter grantedAuthorities =
        new JwtGrantedAuthoritiesConverter();
    grantedAuthorities.setAuthoritiesClaimName("permissions");
    grantedAuthorities.setAuthorityPrefix("PERMISSION_");

    JwtAuthenticationConverter converter = new JwtAuthenticationConverter();
    converter.setJwtGrantedAuthoritiesConverter(grantedAuthorities);
    converter.setPrincipalClaimName("preferred_username");
    return converter;
}
~~~

Ở ví dụ này, claim `permissions` cần có kiểu dữ liệu phù hợp với converter, chẳng hạn danh sách tên quyền:

~~~json
{
  "permissions": ["orders.read", "orders.export"]
}
~~~

Khi ấy authority có thể là `PERMISSION_orders.read` và `PERMISSION_orders.export`. Nếu bạn chuyển từ `SCOPE_` sang `PERMISSION_` thì phải cập nhật cả biểu thức `hasAuthority(...)`; không được coi hai tiền tố tương đương.

Để dùng converter trên, đưa nó vào cấu hình `jwtAuthenticationConverter(...)` trong Resource Server DSL. Một bean converter do bạn khai báo **không nên bị mặc định là tự gắn vào mọi SecurityFilterChain** nếu không thấy cấu hình sử dụng cụ thể.

## 4. `OpaqueTokenAuthenticationProvider`: xác thực bằng introspection

**Opaque token** là access token mà Resource Server không dựa vào việc đọc JWT claims và tự kiểm tra chữ ký để xác thực. API thường gửi token tới **token introspection endpoint** được Authorization Server hỗ trợ. Cơ chế introspection cũng có thể được dùng cho JWT **nếu issuer hỗ trợ** và API được thiết kế như vậy; tên “opaque token support” mô tả cách API **xác minh** token, không phải lệnh cấm issuer cấp JWT.

### 4.1. Các bước bên trong opaque provider

~~~mermaid
flowchart TD
    A["BearerTokenAuthenticationToken"] --> B["OpaqueTokenAuthenticationProvider"]
    B --> C["OpaqueTokenIntrospector.introspect(token)"]
    C --> D["Authorization Server introspection endpoint"]
    D --> E{"Token active / được chấp nhận?"}
    E -- "Không" --> F["Lỗi xác thực / Bearer 401"]
    E -- "Có" --> G["OAuth2AuthenticatedPrincipal"]
    G --> H["GrantedAuthority từ scope / thuộc tính"]
    H --> I["BearerTokenAuthentication"]
    I --> J["AuthenticationManager trả Authentication"]
    J --> K["SecurityContext, rồi kiểm tra quyền API"]
~~~

Trong cách triển khai introspection thông thường:

1. `OpaqueTokenIntrospector` gửi chuỗi access token đến introspection endpoint với thông tin xác thực của Resource Server, khi endpoint yêu cầu.
2. Authorization Server kiểm tra trạng thái token và chính sách liên quan rồi trả metadata.
3. Nếu token hợp lệ, introspector dựng `OAuth2AuthenticatedPrincipal` với attributes và authorities được diễn giải theo cấu hình.
4. Provider tạo `BearerTokenAuthentication` đã xác thực để chuỗi filter sử dụng.

Request mang token đến API không giống request introspection:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.com
Authorization: Bearer <access-token>
~~~

Request introspection minh họa từ Resource Server tới Authorization Server:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Basic <resource-server-credentials>
Content-Type: application/x-www-form-urlencoded

token=<access-token>
~~~

Header credentials và đường dẫn trong ví dụ chỉ mang tính **minh họa**. API dùng thông tin xác thực riêng được Authorization Server cấp để gọi introspection. Credentials này không phải mật khẩu người dùng hay `client_secret` của ứng dụng đang gửi API request.

Phản hồi introspection có thể như sau:

~~~json
{
  "active": true,
  "sub": "user-42",
  "client_id": "orders-frontend",
  "scope": "orders.read orders.export",
  "exp": 1893456000,
  "aud": ["orders-api"],
  "iss": "https://auth.example.com/realms/shop"
}
~~~

Khi token không còn hoạt động, endpoint thường trả:

~~~json
{
  "active": false
}
~~~

Trong thực tế, response phụ thuộc Authorization Server và quyền của client introspection. `active: true` là điều kiện quan trọng, nhưng API vẫn phải bảo đảm thông tin issuer, audience, scope và chính sách quyền phù hợp với yêu cầu bảo vệ tài nguyên. Đặc biệt khi sử dụng **introspector tùy chỉnh**, không nên coi bất kỳ JSON response nào chứa `sub` là đủ để xác thực.

### 4.2. `OAuth2AuthenticatedPrincipal` và `BearerTokenAuthentication`

Khác với nhánh JWT, principal của opaque token thường là `OAuth2AuthenticatedPrincipal`; kết quả `Authentication` thường là `BearerTokenAuthentication`.

Ví dụ đọc principal:

~~~java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OpaqueProfileController {

    @GetMapping("/api/profile")
    String currentProfile(
            @AuthenticationPrincipal OAuth2AuthenticatedPrincipal principal) {
        String subject = principal.getAttribute("sub");
        String clientId = principal.getAttribute("client_id");
        return "Subject: " + subject;
    }
}
~~~

Attributes của principal đến từ introspection và các bước chuyển đổi được cấu hình. Không giả định mọi issuer trả đủ `client_id`, `aud` hay claim tùy chỉnh; cần kiểm tra hợp đồng của Authorization Server.

### 4.3. Introspection không phải làm mới token

Khi API introspect token, nó hỏi **token đang có còn hợp lệ không**. Một kết quả `active: false` không khiến provider lấy được access token mới. Việc xin mới hoặc refresh token thuộc trách nhiệm của **OAuth2 Client và Authorization Server**, không thuộc hai AuthenticationProvider của Resource Server.

## 5. So sánh trực tiếp hai provider

| Tiêu chí | `JwtAuthenticationProvider` | `OpaqueTokenAuthenticationProvider` |
| --- | --- | --- |
| Đầu vào từ filter | `BearerTokenAuthenticationToken` | `BearerTokenAuthenticationToken` |
| Thành phần xác thực chính | `JwtDecoder` | `OpaqueTokenIntrospector` |
| Nguồn bằng chứng | Chữ ký/khóa và claims trong JWT, các validator | Trạng thái/attributes token được introspection endpoint xác nhận |
| Kết quả `Authentication` thường gặp | `JwtAuthenticationToken` | `BearerTokenAuthentication` |
| Principal thường gặp | `Jwt` | `OAuth2AuthenticatedPrincipal` |
| Authorities | Chuyển từ JWT claims bằng converter | Lấy/chuyển từ attributes của introspection theo cấu hình |
| Liên hệ Authorization Server mỗi request | Thường không, nếu có khóa tin cậy để xác minh tại chỗ | Thường có HTTP call introspection mỗi lần xác thực nếu không triển khai cache |
| Thu hồi token | Khó có hiệu lực tức thời nếu chỉ xác minh JWT offline | Có thể phản ánh trạng thái thu hồi qua introspection, tùy issuer/caching |
| Phụ thuộc mạng ở lúc xác thực | Có thể cần cho metadata/JWKS hoặc thay khóa; không nhất thiết mỗi request | Thường phụ thuộc introspection endpoint ở mỗi lần xác thực |
| Tùy chỉnh | `JwtDecoder`, token validators, `JwtAuthenticationConverter` | `OpaqueTokenIntrospector`, chuyển đổi authorities/principal theo API phiên bản |
| Có cấp hoặc làm mới token không? | **Không** | **Không** |

**Hiệu năng:** JWT cho phép API xác minh nhiều request cục bộ sau khi có khóa tin cậy, giảm lời gọi mạng. Introspection thường thêm độ trễ và phụ thuộc trạng thái Authorization Server, nhưng giúp Resource Server thấy được trạng thái token do issuer quản lý. Caching introspection có thể giảm tải nhưng cần cân bằng với nhu cầu thu hồi token nhanh.

**Bảo mật:** JWT offline đòi hỏi kiểm tra issuer, audience, chữ ký, algorithm/key và thời hạn thật chặt. Introspection đòi hỏi kết nối TLS tin cậy, bảo vệ client credentials của Resource Server và xác minh chính xác endpoint/response. Không giải pháp nào thay thế quyền nghiệp vụ như “user A được xem order 123 hay không”.

## 6. Cấu hình Spring Security Servlet dùng JWT provider

Đối với ứng dụng Spring Boot dùng Servlet stack, thêm dependency Resource Server:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Khai báo issuer hợp lệ trong `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

Ví dụ `SecurityFilterChain` cho JWT:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class JwtResourceServerSecurity {

    @Bean
    SecurityFilterChain jwtApiChain(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

Trong cấu hình này:

- `oauth2ResourceServer(...jwt(...))` lắp xử lý Bearer token theo cơ chế JWT và thành phần JWT provider.
- `issuer-uri` cho phép khám phá cấu hình issuer/JWKS theo chuẩn được hỗ trợ, đồng thời kiểm tra issuer theo cách cấu hình của Spring Security.
- API cần bảo đảm **audience** của access token phù hợp API; không nên ngầm hiểu `issuer-uri` đã cung cấp mọi quy tắc audience mong muốn.
- Khi scope token là `orders.read`, mapping mặc định thông dụng tạo `SCOPE_orders.read` cho `hasAuthority(...)`.
- Kiểm tra scope ở filter chain **chưa thay thế** kiểm tra đối tượng/tenant trong service/controller.

Đoạn `csrf(...disable())` chỉ phù hợp trong **API stateless xác thực qua Bearer token và không dùng cookie trình duyệt tự động gửi để xác thực**. Nếu ứng dụng có cookie/session làm cơ chế đăng nhập, cần thiết kế bảo vệ CSRF thích hợp.

Ví dụ có thể thay `jwt(Customizer.withDefaults())` bằng cấu hình converter:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt ->
    jwt.jwtAuthenticationConverter(jwtAuthenticationConverter())
))
~~~

Đoạn code phía trên chỉ là **đoạn nối cấu hình** bên trong builder; nó dùng bean/helper `jwtAuthenticationConverter()` đã được định nghĩa trước đó. Nếu ánh xạ sang `PERMISSION_`, cần đổi `hasAuthority(...)` tương ứng.

## 7. Cấu hình Spring Security Servlet dùng opaque provider

Nếu token được xác minh qua introspection, thay cấu hình JWT bằng cấu hình opaque token:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: YOUR_RESOURCE_SERVER_INTROSPECTION_SECRET
~~~

Các giá trị trên chỉ để minh họa. Trong hệ thống thực tế, giữ thông tin xác thực introspection trong secret manager hoặc cơ chế cấu hình an toàn; dùng URL do Authorization Server công bố.

Ví dụ `SecurityFilterChain` riêng cho opaque token:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OpaqueResourceServerSecurity {

    @Bean
    SecurityFilterChain opaqueApiChain(HttpSecurity http) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.opaqueToken(Customizer.withDefaults()))
            .build();
    }
}
~~~

**Lưu ý:** Hai lớp cấu hình JWT và opaque ở hai mục là **hai ví dụ thay thế nhau cho cùng một API**, không phải hai file nên sao chép đồng thời vào một ứng dụng với hai chain mặc định cùng áp dụng cho mọi đường dẫn. Nếu ứng dụng cần nhận cả hai cơ chế, hãy thiết kế việc chọn chain/manager có chủ đích.

### 7.1. Tùy chỉnh introspector

Tùy phiên bản Spring Security và kiểu Authorization Server, API có thể khai báo `OpaqueTokenIntrospector` riêng để:

- Gọi endpoint introspection bằng cơ chế xác thực HTTP được issuer yêu cầu.
- Chuyển đổi attributes, ví dụ tên scope hoặc tenant.
- Bổ sung hoặc giới hạn `GrantedAuthority` theo chính sách được xác định.
- Từ chối token không đúng audience hoặc không thuộc các client/issuer mà API tin cậy, nếu response cung cấp thông tin để kiểm tra.
- Kiểm soát timeout và lỗi kết nối khi gọi issuer; cân nhắc cache nếu chính sách cho phép.

Điểm quan trọng là introspector tùy chỉnh phải **giữ nguyên nguyên tắc xác minh**: không dựng một `OAuth2AuthenticatedPrincipal` được tin cậy từ các dữ liệu mà chưa được issuer chứng thực và không bỏ qua trạng thái token đã bị vô hiệu hóa.

### 7.2. Lỗi kết nối introspection khác lỗi token không hợp lệ

Nếu introspection trả `active: false`, token bị từ chối. Nếu introspection endpoint không thể kết nối, timeout hoặc trả lỗi máy chủ, đó là sự cố của **hạ tầng xác minh**, không chứng minh được token hợp lệ. Resource Server phải xử lý an toàn và không cho request đi qua chỉ vì dịch vụ xác minh gặp lỗi.

Mã HTTP cuối cùng cho lỗi kết nối phụ thuộc thành phần, phiên bản, handler và chính sách ứng dụng. Vì thế không nên gán cứng rằng **mọi lỗi introspection đều là `401 invalid_token`**. Log cần có thông tin chẩn đoán phù hợp nhưng tuyệt đối tránh ghi thẳng access token, client secret hoặc response nhạy cảm.

## 8. Chọn provider phù hợp với hệ thống

Một số tiêu chí thiết kế:

| Nhu cầu | Hướng thường được cân nhắc | Giải thích |
| --- | --- | --- |
| Nhiều request, cần giảm độ trễ mỗi request | JWT provider | Token có thể được xác minh cục bộ khi đã có khóa tin cậy |
| Yêu cầu trạng thái thu hồi token được áp dụng sớm | Introspection/opaque provider | Authorization Server có thể kiểm tra trạng thái token hiện tại |
| Issuer cấp token opaque, có introspection endpoint | Opaque provider | Không thể tự xác minh chữ ký JWT vì token không mang cấu trúc JWT phù hợp |
| Issuer cấp JWT với chữ ký và JWKS chuẩn | JWT provider | Resource Server xác minh chữ ký và claim theo hợp đồng |
| JWT nhưng tổ chức yêu cầu introspection mọi request | Opaque/introspection approach, nếu issuer hỗ trợ | Cơ chế xác minh phụ thuộc lựa chọn hợp đồng và chính sách |
| Resource Server cần hoạt động khi issuer tạm thời không nhận introspection | JWT provider có thể giúp | Sau khi có khóa tin cậy, thường không cần gọi issuer mỗi request |

Không nên chọn provider chỉ vì tên gọi “JWT tốt hơn” hoặc “opaque an toàn hơn”. Hãy dựa vào kiểu token issuer thực sự phát hành, endpoint hỗ trợ, latency chấp nhận được, cách thu hồi token và tính nhất quán chính sách giữa các API.

### Nhận nhiều loại token hoặc nhiều issuer

Nếu hệ thống có các API/đường dẫn sử dụng cách xác minh khác nhau, có thể dùng **nhiều `SecurityFilterChain`** với `securityMatcher(...)` và thứ tự phù hợp để áp dụng từng cấu hình.

Nếu cần định tuyến theo issuer hoặc từng tenant, có thể dùng **`AuthenticationManagerResolver<HttpServletRequest>`** và các authentication manager đã cấu hình; chẳng hạn mô hình multi-tenant JWT có thể dùng các issuer được **allowlist**. Không lấy `iss` chưa xác minh từ token rồi tin tưởng bất kỳ issuer hay JWKS URL nào do client tự đưa vào.

Một điểm tinh tế: cả hai provider đều có thể `supports(BearerTokenAuthenticationToken.class)`. Nếu đăng ký đồng thời vào cùng một `ProviderManager`, việc chọn và thứ tự provider không phải giải pháp “tự động thử đúng loại token” đáng tin cậy. Cần xác định chính sách định tuyến hoặc chọn đúng một cách xác thực trên chain.

## 9. Lấy thông tin Authentication trong controller/service

Khi dùng JWT provider:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;

void inspectJwt(Authentication authentication) {
    if (authentication instanceof JwtAuthenticationToken jwtAuth) {
        String subject = jwtAuth.getToken().getSubject();
        String name = jwtAuth.getName();
        var authorities = jwtAuth.getAuthorities();
    }
}
~~~

Khi dùng opaque provider:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;

void inspectOpaque(Authentication authentication) {
    if (authentication instanceof BearerTokenAuthentication bearerAuth) {
        String subject = bearerAuth.getTokenAttributes().get("sub").toString();
        String name = bearerAuth.getName();
        var authorities = bearerAuth.getAuthorities();
    }
}
~~~

Trong ứng dụng hỗ trợ nhiều phương thức xác thực, mã nghiệp vụ thường nên phụ thuộc vào **thông tin cần thiết** như `Authentication.getName()`, `getAuthorities()` hoặc một abstraction/identity service chung, thay vì ép kiểu provider-specific ở mọi controller.

Ví dụ đơn giản chỉ dùng interface chung:

~~~java
import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CurrentUserController {

    @GetMapping("/api/me")
    Map<String, String> me(Authentication authentication) {
        return Map.of("principal", authentication.getName());
    }
}
~~~

Trả `authentication.getName()` cho client chỉ là ví dụ. Một hệ thống đa tenant cần xác định rõ `sub` là duy nhất trong phạm vi issuer nào, tránh dùng mỗi `sub` để truy cập dữ liệu xuyên tenant hoặc xuyên issuer.

## 10. Các tình huống chẩn đoán lỗi trong Resource Server

### Tình huống A: JWT đã hết hạn

Request:

~~~http
GET /api/orders HTTP/1.1
Authorization: Bearer <expired-jwt>
~~~

`JwtDecoder` phát hiện token không còn thỏa điều kiện thời gian; provider không tạo `JwtAuthenticationToken` được chấp nhận. Client thường nhận **401** và Bearer challenge liên quan. **JwtAuthenticationProvider không làm mới JWT**; client phải xin token mới từ Authorization Server khi được phép.

### Tình huống B: JWT đúng chữ ký nhưng `aud` dành cho API khác

Nếu Orders API chỉ kiểm tra chữ ký/issuer mà không áp dụng chính sách audience phù hợp, có thể vô tình chấp nhận token được phát hành cho Payments API. Cần xác minh `aud` đúng với Orders API tại bước xác thực. Một scope cùng tên không thay thế điều kiện audience.

### Tình huống C: Opaque token bị thu hồi

Resource Server introspect token và Authorization Server trả `active: false`. `OpaqueTokenAuthenticationProvider` không được tạo một `Authentication` hợp lệ để tiếp tục gọi controller. Đây là một lợi thế của introspection khi cần phản ánh trạng thái thu hồi và issuer thực hiện chính sách tương ứng.

### Tình huống D: Introspection endpoint chậm hoặc không truy cập được

Người dùng thấy request lỗi/timeout dù bearer token trước đó được chấp nhận. Cần kiểm tra kết nối đến issuer, TLS, credentials, timeout và giới hạn tải introspection. Không được “cho qua request” để tránh lỗi vì như vậy bỏ mất lớp xác thực.

### Tình huống E: Token hợp lệ nhưng API vẫn trả 403

Provider đã xác thực token, nhưng `AuthorizationFilter` hoặc bảo mật ở service từ chối thao tác. Ví dụ token mang `SCOPE_orders.read` nhưng endpoint đòi `SCOPE_orders.write`, hoặc chủ thể không được truy cập đơn hàng của người khác. Đổi từ JWT provider sang opaque provider **không tự cấp thêm quyền**.

### Tình huống F: Token có `roles` nhưng `hasRole("ADMIN")` không hoạt động

Với JWT provider, mặc định có thể chỉ ánh xạ `scope` hoặc `scp` thành `SCOPE_...`; claim `roles` tùy chỉnh không tự trở thành `ROLE_ADMIN`. Cần cấu hình mapping claim/authorities phù hợp. Tương tự, introspection provider chỉ sử dụng các authorities theo metadata và mapping được cấu hình.

### Tình huống G: Client gửi ID token thay access token

Trong OIDC, **ID token** phục vụ xác thực người dùng cho **OIDC Client**. Resource Server phải đòi **access token dành cho API của mình**. Một ID token cũng có thể có hình dạng JWT, nhưng điều đó không có nghĩa nó được chấp nhận làm token truy cập API. Kiểm tra audience, loại/mục đích token và các chính sách liên quan giúp tránh nhầm lẫn.

## 11. Ranh giới bảo mật và vận hành

Hai provider là thành phần **xác thực access token**, không phải nơi:

- Cấp access token hoặc refresh token cho client.
- Quyết định người dùng được phép truy cập tất cả bản ghi nghiệp vụ.
- Xác thực lại password/OTP trực tiếp tại Orders API.
- Tự tạo phiên đăng nhập OIDC cho browser.
- Tự động xử lý refresh grant khi API trả 401.

Với JWT, cần quản lý các mối quan tâm như khóa ký/JWKS, khóa xoay vòng, issuer đáng tin, audience, thuật toán cho phép, thời hạn và khả năng thu hồi token. Với introspection, cần quản lý endpoint tin cậy, chứng chỉ TLS, client credentials, độ trễ, thời gian chờ, trạng thái endpoint và cách xử lý sự cố.

Đối với cả hai, API phải phân quyền sau xác thực và áp dụng **object-level authorization**. Chẳng hạn, `orders.read` có nghĩa client có quyền thực hiện thao tác đọc trong một phạm vi nhất định, **không có nghĩa** token hợp lệ được xem mọi đơn hàng của mọi người.

Khi ghi log phục vụ chẩn đoán, có thể log request ID, kết quả xác thực, issuer đã được kiểm chứng hoặc danh tính đã được xác thực ở mức cần thiết. **Không log nguyên bearer token, refresh token, introspection client secret** hoặc dữ liệu xác thực nhạy cảm.

## 12. Tóm tắt luồng xử lý

| Câu hỏi | JWT Resource Server | Opaque Resource Server |
| --- | --- | --- |
| Filter nào lấy token từ HTTP request? | `BearerTokenAuthenticationFilter` | `BearerTokenAuthenticationFilter` |
| Token ban đầu được bọc trong gì? | `BearerTokenAuthenticationToken` | `BearerTokenAuthenticationToken` |
| Provider nào thực hiện xác thực? | `JwtAuthenticationProvider` | `OpaqueTokenAuthenticationProvider` |
| Thành phần nào xác minh? | `JwtDecoder` | `OpaqueTokenIntrospector` |
| Authentication thành công thường là gì? | `JwtAuthenticationToken` | `BearerTokenAuthentication` |
| Ai kiểm tra quyền endpoint? | Cơ chế authorization của Spring Security | Cơ chế authorization của Spring Security |
| Ai cấp hoặc làm mới token? | Authorization Server theo yêu cầu của Client | Authorization Server theo yêu cầu của Client |

Khi đọc mã Spring Security, hãy lần theo hai tuyến:

~~~text
JWT:
BearerTokenAuthenticationFilter
  -> AuthenticationManager
  -> JwtAuthenticationProvider
  -> JwtDecoder
  -> JwtAuthenticationConverter
  -> JwtAuthenticationToken
  -> SecurityContext
  -> Authorization

Opaque token / introspection:
BearerTokenAuthenticationFilter
  -> AuthenticationManager
  -> OpaqueTokenAuthenticationProvider
  -> OpaqueTokenIntrospector
  -> OAuth2AuthenticatedPrincipal
  -> BearerTokenAuthentication
  -> SecurityContext
  -> Authorization
~~~

**Điểm cần nhớ:** `JwtAuthenticationProvider` và `OpaqueTokenAuthenticationProvider` đều kết nối **Bearer token authentication** với hệ thống bảo vệ API của Spring Security Servlet, nhưng khác nhau ở **cách kiểm tra token và dạng principal kết quả**. Xác thực token thành công chỉ là bước đầu; quyết định được truy cập endpoint và từng tài nguyên vẫn do lớp authorization của Resource Server thực hiện.
