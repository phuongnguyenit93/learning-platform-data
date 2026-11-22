# `BearerTokenAuthenticationToken` trước khi được xác thực trong chuỗi xử lý Servlet

## 1. Bối cảnh và ý nghĩa của trạng thái “chưa xác thực”

Trong **Spring Security OAuth 2.0 Resource Server** chạy trên **Servlet stack** (chẳng hạn ứng dụng Spring MVC), client thường gửi một access token trong header HTTP:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6ImsxIn0.payload.signature
```

Tại thời điểm HTTP request vừa đến, giá trị sau chữ `Bearer` mới là **một chuỗi do phía client cung cấp**. Chưa có bằng chứng rằng token này được Authorization Server tin cậy phát hành, còn hạn, dành cho API, hoặc chứa quyền truy cập phù hợp.

Spring Security đại diện cho yêu cầu xác thực sơ bộ đó bằng đối tượng:

```java
org.springframework.security.oauth2.server.resource.authentication
    .BearerTokenAuthenticationToken
```

Đây là một **`Authentication` chưa được xác thực**, thường được tạo bởi `BearerTokenAuthenticationFilter` rồi chuyển cho `AuthenticationManager`. Nó là phương tiện trao đổi dữ liệu giữa **bộ lọc HTTP** và **cơ chế xác thực**, không phải kết quả thành công hay danh tính đáng tin cậy để phân quyền.

Cần phân biệt rõ:

- **Bearer credential:** chuỗi access token xuất hiện trong request, chưa qua validation.
- **`BearerTokenAuthenticationToken`:** đối tượng `Authentication` chứa chuỗi token vừa tách khỏi HTTP request, có `isAuthenticated() == false` khi mới tạo.
- **Authenticated `Authentication`:** kết quả được provider tạo ra sau khi kiểm tra token; thường là `JwtAuthenticationToken` hoặc `BearerTokenAuthentication`, tùy JWT/opaque token.
- **`SecurityContext`:** nơi Spring Security gắn kết quả xác thực để các thành phần xử lý tiếp theo dùng cho authorization.

> **Nguyên tắc:** “Đã có token” chỉ có nghĩa request cung cấp một credential. “Đã được xác thực” là kết luận do cơ chế xác thực tin cậy đưa ra sau khi kiểm tra credential đó.

## 2. Vị trí của `BearerTokenAuthenticationToken` trong chuỗi xử lý Servlet

Trong ứng dụng Spring MVC, request đi qua các tầng filter trước khi đến controller:

```text
Client / HTTP request
        |
        v
Servlet container (Tomcat, Jetty, ...)
        |
        v
DelegatingFilterProxy ("springSecurityFilterChain")
        |
        v
FilterChainProxy
        |
        v
SecurityFilterChain áp dụng cho đường dẫn request
        |
        +--> SecurityContextHolderFilter (quản lý context đầu request)
        |           |
        |           v
        +--> BearerTokenAuthenticationFilter
        |       |
        |       +-- BearerTokenResolver tách token từ request
        |       |
        |       +-- new BearerTokenAuthenticationToken(rawToken)
        |       |       isAuthenticated = false
        |       |
        |       +-- AuthenticationManager.authenticate(requestToken)
        |               |
        |               +-- JwtAuthenticationProvider / OpaqueTokenAuthenticationProvider
        |                       |
        |                       +-- xác minh token + chuyển đổi authorities
        |                       |
        |                       +-- Authentication đã xác thực
        |
        +--> SecurityContext chứa Authentication đã được xác thực
        |
        +--> Các filter tiếp theo (ví dụ AnonymousAuthenticationFilter,
        |    ExceptionTranslationFilter, AuthorizationFilter)
        |
        v
DispatcherServlet -> Controller -> Service -> Response
```

Sơ đồ mô tả **luồng điển hình** của Spring Security Servlet Resource Server. Thứ tự/filter thực tế có thể khác theo phiên bản, số lượng `SecurityFilterChain` và các filter bổ sung. Điều bất biến cần hiểu là **yêu cầu chưa xác thực phải đi qua AuthenticationManager/Provider trước khi được dùng như một danh tính đáng tin**.

### Ai tạo đối tượng này?

Trong cấu hình Resource Server thông thường, chính **`BearerTokenAuthenticationFilter`** thực hiện:

```java
BearerTokenAuthenticationToken authenticationRequest =
        new BearerTokenAuthenticationToken(token);
```

Filter có thể gán thêm `details` của request, rồi gửi đối tượng này cho `AuthenticationManager`. Controller hoặc service nghiệp vụ không cần tự tạo và “đăng nhập” bằng đối tượng này.

### Vì sao phải tạo một `Authentication` chưa xác thực?

Spring Security thống nhất việc xác thực qua hợp đồng:

```java
Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
```

Đầu vào và đầu ra đều là `Authentication` nhưng **vai trò hoàn toàn khác nhau**:

1. **Đầu vào:** mô tả client đã trình bày credential gì, chưa bảo đảm đúng.
2. **Bộ xác thực:** chọn provider phù hợp và kiểm tra credential.
3. **Đầu ra thành công:** mô tả principal, token đã được kiểm tra, quyền đã được ánh xạ và trạng thái authenticated.
4. **Thất bại:** ném `AuthenticationException`; không tạo kết quả authenticated để đưa vào `SecurityContext`.

Đây là lý do tên lớp `BearerTokenAuthenticationToken` nghe giống “token đã đăng nhập”, nhưng thực tế nó là **authentication request object**.

## 3. Cấu trúc của `BearerTokenAuthenticationToken`

`BearerTokenAuthenticationToken` là một implementation của `Authentication` thông qua `AbstractAuthenticationToken`.

Các đặc điểm khi mới tạo:

| Thành phần | Giá trị hoặc ý nghĩa trước xác thực |
|---|---|
| `getToken()` | Chuỗi bearer token thô đã tách từ request |
| `getPrincipal()` | Trong lớp này, trả về chính **chuỗi token thô**, chưa phải `UserDetails` hay `Jwt` đã xác minh |
| `getCredentials()` | Cũng là **chuỗi token thô**; nó được dùng như credential để xác thực |
| `getAuthorities()` | Ban đầu không có authorities được tin cậy, thường là tập rỗng |
| `isAuthenticated()` | **`false`** khi khởi tạo |
| `getDetails()` | Có thể được filter gắn thông tin liên quan đến request thông qua `AuthenticationDetailsSource` |
| `getName()` | Không dùng làm tên người dùng đáng tin tại giai đoạn này; principal còn là credential |

Ví dụ tạo đối tượng ngoài HTTP để quan sát ý nghĩa API:

```java
import org.springframework.security.oauth2.server.resource.authentication
        .BearerTokenAuthenticationToken;

String rawAccessToken = "opaque-or-jwt-token-value";
BearerTokenAuthenticationToken request =
        new BearerTokenAuthenticationToken(rawAccessToken);

// Chưa xác thực, chưa có quyền truy cập API.
boolean authenticated = request.isAuthenticated(); // false
String presentedToken = request.getToken();          // token raw
Object principal = request.getPrincipal();           // token raw
Object credentials = request.getCredentials();       // token raw
int authorityCount = request.getAuthorities().size();// 0
```

Ví dụ trên giải thích kiểu dữ liệu; **không phải hướng dẫn tạo token giả, cũng không phải cách đăng nhập người dùng trong controller**. Trong luồng thật, Spring Security tự tạo object sau khi đọc Bearer credential.

### Đừng hiểu nhầm `principal`

Ở nhiều cơ chế đăng nhập, `principal` có thể là username, `UserDetails` hoặc một identity đã xác thực. Nhưng với **`BearerTokenAuthenticationToken` đầu vào**, `getPrincipal()` trả về token thô. Nếu code tự đọc `authenticationRequest.getPrincipal()` rồi kết luận đó là user ID, ứng dụng đã nhầm **credential** với **identity**.

Danh tính được xác nhận sẽ xuất hiện **sau** khi provider xác thực thành công, ví dụ JWT claim `sub` đã kiểm chứng hoặc principal trả về từ introspection.

### Vì sao đối tượng không chứa scope/role ngay khi tạo?

JWT access token có thể được decode để thấy `scope` hoặc `roles`, nhưng trước bước xác minh, chúng là dữ liệu do client có thể sửa đổi. Bởi vậy `BearerTokenAuthenticationToken` không tự giải mã JWT hoặc tự ánh xạ quyền ngay từ constructor. Những việc đó thuộc **`JwtDecoder` / token introspection / provider** và bộ chuyển đổi authorities sau khi token được kiểm tra.

Đưa authorities chưa xác thực vào `Authentication` và dùng nó để authorization là sai ranh giới tin cậy.

## 4. Từ HTTP header đến authentication request

### 4.1. `BearerTokenResolver` tìm bearer token

`BearerTokenAuthenticationFilter` nhờ một `BearerTokenResolver` đọc request. Implementation mặc định trong Servlet là `DefaultBearerTokenResolver`, chủ yếu lấy token từ:

```http
Authorization: Bearer ACCESS_TOKEN
```

Resolver chịu trách nhiệm nhận biết scheme và cấu trúc credential. Mặc định, query parameter và form-body parameter `access_token` không được bật làm kênh truyền token. Các thiết lập thay đổi cách đọc token thuộc chính sách riêng của ứng dụng.

Giá trị được trả về khi có Bearer token phù hợp về mặt cấu trúc là **`String` raw token**. Resolver chưa kiểm tra chữ ký JWT, `exp`, audience hay scope.

### 4.2. Trường hợp không có Bearer token

Ví dụ:

```http
GET /api/orders HTTP/1.1
Host: api.example.com
```

Khi resolver không tìm thấy Bearer credential, nó thường trả về `null`. `BearerTokenAuthenticationFilter` **không tạo** `BearerTokenAuthenticationToken` trong trường hợp này và tiếp tục filter chain.

Sau đó:

- Endpoint được đánh dấu `permitAll()` có thể tiếp tục xử lý mà không có bearer authentication.
- Endpoint yêu cầu `authenticated()` hoặc một authority cụ thể thường dẫn đến challenge 401 khi không có cơ chế xác thực khác hợp lệ.
- Một filter khác như `AnonymousAuthenticationFilter` có thể cung cấp anonymous authentication để biểu diễn request chưa đăng nhập; anonymous không đồng nghĩa một access token đã được xác thực.

Không có token khác với token có giá trị sai.

### 4.3. Trường hợp Bearer header sai cú pháp

Ví dụ:

```http
Authorization: Bearer
```

Hoặc:

```http
Authorization: Bearer abc def
```

Resolver có thể ném `OAuth2AuthenticationException` vì credential Bearer sai cấu trúc. Filter xử lý lỗi theo cơ chế Resource Server; **không tạo được đối tượng `BearerTokenAuthenticationToken` hợp lệ để gửi provider**.

Vì thế cần phân biệt hai điểm lỗi:

- **Trước khi có `BearerTokenAuthenticationToken`:** HTTP Bearer credential không thể trích xuất hợp lệ.
- **Sau khi có `BearerTokenAuthenticationToken`:** chuỗi token đã lấy được nhưng JWT decoder/introspector xác nhận token không hợp lệ.

Hai tình huống có thể cùng trả 401 nhưng cần chẩn đoán ở hai thành phần khác nhau.

### 4.4. Trường hợp token có cú pháp Bearer phù hợp nhưng giả

```http
Authorization: Bearer abc.def.ghi
```

Resolver có thể tách ra `abc.def.ghi` rồi tạo `BearerTokenAuthenticationToken` dù giá trị đó không phải JWT hợp lệ. **Không thể kết luận request xác thực thành công chỉ vì object đã được tạo**. `JwtDecoder` sẽ kiểm tra định dạng JWS, chữ ký, issuer, hiệu lực và các validator đã cấu hình.

### 4.5. Trường hợp một request có nhiều credential

Nếu có hai header `Authorization` hoặc vừa header vừa query/form token, cách resolver và proxy nhìn thấy chúng phụ thuộc cấu hình và tầng HTTP. Nguyên tắc an toàn là quy định một nguồn bearer credential rõ ràng và từ chối request mơ hồ. Việc tạo **một `BearerTokenAuthenticationToken` từ token đầu tiên** không chứng minh request gốc chỉ có một token.

Cần đặt chính sách phát hiện duplicate/multiple sources tại gateway hoặc lớp xử lý request có đủ thông tin đầu vào, thay vì chọn token theo thứ tự bất kỳ.

## 5. Chuyển sang `AuthenticationManager`: điểm bắt đầu xác thực thật sự

Sau khi tạo authentication request, filter nhờ `AuthenticationManager` xử lý. Mô tả đơn giản:

```java
// Pseudocode phản ánh trách nhiệm logic của framework.
String token = bearerTokenResolver.resolve(request);

if (token == null) {
    filterChain.doFilter(request, response);
    return;
}

BearerTokenAuthenticationToken authenticationRequest =
        new BearerTokenAuthenticationToken(token);

authenticationRequest.setDetails(
        authenticationDetailsSource.buildDetails(request));

Authentication authenticationResult =
        authenticationManager.authenticate(authenticationRequest);

// Chỉ kết quả đã được xác thực mới được đưa vào SecurityContext.
SecurityContext context = securityContextHolderStrategy.createEmptyContext();
context.setAuthentication(authenticationResult);
securityContextHolderStrategy.setContext(context);

filterChain.doFilter(request, response);
```

Đây là **pseudocode giảng giải**, không sao chép toàn bộ mã nguồn filter: phiên bản thực tế còn xử lý `AuthenticationManagerResolver<HttpServletRequest>`, `SecurityContextRepository`, các exception và failure handler. Không đưa đoạn pseudocode vào ứng dụng để thay filter có sẵn.

### `AuthenticationManager` chọn provider thế nào?

Với Spring Security, một `AuthenticationManager` như `ProviderManager` có thể lần lượt tìm `AuthenticationProvider` hỗ trợ loại authentication request. Trong Resource Server điển hình:

| Provider | Nhận request | Phương pháp xác thực | Kết quả khi thành công |
|---|---|---|---|
| `JwtAuthenticationProvider` | `BearerTokenAuthenticationToken` | Dùng `JwtDecoder` kiểm tra JWT access token đã ký và áp dụng validators | `JwtAuthenticationToken` |
| `OpaqueTokenAuthenticationProvider` | `BearerTokenAuthenticationToken` | Dùng `OpaqueTokenIntrospector` hỏi AS về token và metadata | `BearerTokenAuthentication` |
| Custom provider | Tùy thiết kế và `supports(...)` | Phải thực thi đầy đủ các yêu cầu xác thực của hệ thống | `Authentication` đã xác thực phù hợp |

Cả JWT và opaque đều có thể bắt đầu từ **cùng một loại object chưa xác thực**. Loại `Authentication` đầu vào không nói token bên trong là JWT hay opaque; **provider/decoder được cấu hình** quyết định cách kiểm tra.

Spring Security hỗ trợ dùng `AuthenticationManagerResolver<HttpServletRequest>` để chọn manager theo request trong một số mô hình nhiều issuer/tenant, nhưng việc lựa chọn phải tuân theo **nguồn tin cậy được cấu hình trước**. Không chọn một issuer hoặc JWKS bất kỳ chỉ dựa vào claim chưa xác thực.

## 6. Đường đi khi API chấp nhận JWT access token

Giả sử Resource Server dùng JWT:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com/realms/demo
```

Và cấu hình một security chain:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain api(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers(HttpMethod.GET, "/api/orders/**")
                            .hasAuthority("SCOPE_orders.read")
                        .anyRequest().authenticated())
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }
}
```

Đây là cấu hình ứng dụng Resource Server theo Spring Security DSL. Nó cho phép framework tự gắn filter và provider cần thiết. Trong thực tế, Resource Server còn phải kiểm tra **audience của API** theo hợp đồng token; chỉ cấu hình issuer không mặc nhiên hoàn tất mọi chính sách audience/loại access token.

### 6.1. Từng bước từ token thô sang JWT đã xác thực

1. Client gửi `Authorization: Bearer <jwt>`.
2. `BearerTokenAuthenticationFilter` dùng resolver lấy chuỗi token.
3. Filter tạo `BearerTokenAuthenticationToken`, `isAuthenticated() == false`, chưa có authorities.
4. `AuthenticationManager` đưa request cho `JwtAuthenticationProvider` phù hợp.
5. Provider gọi `JwtDecoder.decode(rawToken)`.
6. Decoder phân tích JWS, xác minh chữ ký bằng khóa và thuật toán đáng tin, thực thi các validators về issuer, thời gian và những ràng buộc được cấu hình (như audience, token profile).
7. `JwtAuthenticationConverter` chuyển `Jwt` thành `JwtAuthenticationToken` với principal và authorities tương ứng.
8. Provider trả về kết quả authenticated; filter gắn kết quả vào `SecurityContext`.
9. `AuthorizationFilter` và các chính sách quyền tiếp tục kiểm tra endpoint và tài nguyên.

Sơ đồ tuần tự:

```mermaid
sequenceDiagram
    participant Client
    participant Filter as BearerTokenAuthenticationFilter
    participant Resolver as BearerTokenResolver
    participant Manager as AuthenticationManager
    participant Provider as JwtAuthenticationProvider
    participant Decoder as JwtDecoder
    participant Context as SecurityContextHolder

    Client->>Filter: HTTP Authorization: Bearer JWT
    Filter->>Resolver: resolve(request)
    Resolver-->>Filter: raw JWT String
    Note over Filter: Tạo BearerTokenAuthenticationToken\nauthenticated=false, authorities rỗng
    Filter->>Manager: authenticate(authenticationRequest)
    Manager->>Provider: authenticate(authenticationRequest)
    Provider->>Decoder: decode(raw JWT)
    Decoder-->>Provider: Jwt đã kiểm tra chữ ký/claims
    Note over Provider: Chuyển Jwt thành JwtAuthenticationToken
    Provider-->>Manager: authenticated Authentication
    Manager-->>Filter: authenticationResult
    Filter->>Context: Gắn kết quả vào SecurityContext
    Filter-->>Client: Tiếp tục các filter và xử lý endpoint
```

Nếu decoder ném lỗi do chữ ký sai, token hết hạn hoặc không đạt validator, provider sẽ làm thất bại authentication. Không có `JwtAuthenticationToken` đáng tin được tạo để authorization chấp nhận request.

### 6.2. So sánh object trước và sau khi provider xử lý JWT

| Đặc điểm | Trước: `BearerTokenAuthenticationToken` | Sau: `JwtAuthenticationToken` |
|---|---|---|
| Vai trò | Authentication request | Authentication result |
| Trạng thái | Chưa xác thực | Được xác thực khi provider trả về thành công |
| Principal | Chuỗi bearer token raw | `Jwt` đã được decoder kiểm tra |
| Credentials | Chuỗi bearer token raw | Theo implementation, biểu diễn token đã xác thực |
| Authorities | Không có quyền được xác nhận | Ánh xạ từ claims như `scope`/`scp`, theo converter |
| Identity | Không được suy từ token thô | Thường từ claim `sub` hoặc tên principal được cấu hình |
| Có thể dùng cho authorization? | **Không** | Có, sau khi kiểm tra scope và chính sách nghiệp vụ |

Ví dụ một JWT sau khi xác minh:

```json
{
  "iss": "https://id.example.com/realms/demo",
  "sub": "user-123",
  "aud": "orders-api",
  "scope": "orders.read",
  "iat": 1909996400,
  "exp": 1910000000
}
```

Các giá trị trên chỉ là **claims minh họa**, không phải access token có chữ ký. Nếu `scope=orders.read`, cấu hình mặc định có thể ánh xạ thành authority `SCOPE_orders.read`. Nhưng scope cũng không mặc nhiên cho phép user đọc **mọi** order; tầng nghiệp vụ vẫn kiểm tra quyền đối với order `42`.

### 6.3. Vì sao không lấy trực tiếp `scope` từ BearerTokenAuthenticationToken?

`BearerTokenAuthenticationToken` chưa xác minh token. Một kẻ tấn công có thể sửa phần payload trong JWT, tạo chuỗi JSON trông có `scope=admin`, nhưng không có chữ ký hợp lệ. Nếu application decode Base64URL để đọc claims rồi cấp quyền *trước* `JwtDecoder`, chữ ký trở nên vô nghĩa.

Chỉ `Jwt` đã đi qua một `JwtDecoder` tin cậy và validators của API mới phù hợp làm dữ liệu đầu vào cho converter và authorization.

## 7. Đường đi khi access token là opaque

Resource Server cũng có thể nhận opaque access token, nghĩa là chuỗi token không có cấu trúc mà API tự diễn giải được. Ví dụ:

```http
Authorization: Bearer XoU6DkL3p9v2opaqueToken
```

Filter **vẫn tạo**:

```java
BearerTokenAuthenticationToken requestToken =
        new BearerTokenAuthenticationToken("XoU6DkL3p9v2opaqueToken");
```

Khác biệt xuất hiện ở provider:

1. `OpaqueTokenAuthenticationProvider` nhận `BearerTokenAuthenticationToken`.
2. Provider gọi `OpaqueTokenIntrospector` để kiểm tra token qua introspection hoặc cơ chế tin cậy của Authorization Server.
3. AS trả lời token còn `active` hay không và các metadata có liên quan.
4. Khi xác thực thành công, provider tạo `BearerTokenAuthentication`, với principal/authorities từ dữ liệu đã được xác thực.
5. Kết quả authenticated được filter đưa vào `SecurityContext`; tầng authorization kiểm tra các quyền tiếp theo.

Ví dụ cấu hình:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.com/oauth2/introspect
          client-id: orders-api-introspection
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
```

Cấu hình này minh họa khả năng introspection, không phải lời cam kết rằng `active=true` tự xác nhận đầy đủ **audience/resource** của API. Resource Server cần chính sách kiểm tra metadata theo hợp đồng với issuer, bao gồm quyền, loại token và đối tượng nhận.

### Trước và sau xác thực opaque

| Đặc điểm | `BearerTokenAuthenticationToken` | `BearerTokenAuthentication` |
|---|---|---|
| Token | Chuỗi raw chưa kiểm chứng | OAuth2 access token được provider xử lý |
| Principal | Chuỗi credential | `OAuth2AuthenticatedPrincipal` với attributes từ introspection |
| Authorities | Rỗng | Được ánh xạ từ scope/metadata đáng tin |
| Authenticated | `false` | `true` khi provider hoàn tất |
| Được đặt vào context? | Không nên | Có, khi xác thực thành công |

Điểm chung giữa JWT và opaque: **đối tượng request ban đầu không được xem là một danh tính đã xác thực**.

## 8. Khi nào `SecurityContext` được cập nhật?

Sau khi `AuthenticationManager.authenticate(...) ` trả về một `Authentication` thành công, `BearerTokenAuthenticationFilter` mới có cơ sở đưa nó vào `SecurityContext`. Trong các phiên bản Spring Security Servlet hiện đại, filter quản lý việc tạo context và tương tác với `SecurityContextRepository` theo cấu hình.

Sơ đồ trạng thái:

```text
Trước Bearer filter:
    SecurityContext có thể rỗng hoặc chứa context từ cơ chế khác;
    chưa có kết quả xác thực Bearer của request này.

BearerTokenResolver -> raw token:
    Chưa có kết quả authenticated.

new BearerTokenAuthenticationToken(rawToken):
    isAuthenticated = false
    Không được dùng làm authenticated principal trong context.

AuthenticationManager.authenticate(...):
    Thành công -> Authentication đã xác thực
    Thất bại   -> AuthenticationException

Bearer filter sau thành công:
    SecurityContext.authentication = authenticated result
    Các filter tiếp theo có thể kiểm tra quyền của request.
```

### `SecurityContextHolder` và phạm vi request

`SecurityContextHolder` là điểm truy cập security context của luồng xử lý hiện tại. Trong Servlet application, framework có các cơ chế quản lý, nạp và dọn context phù hợp với request.

Không tự giả định `SecurityContextHolder` giữ trạng thái token vô hạn sau khi response kết thúc. Trong API stateless, một bearer access token thường được xác thực **mỗi request** và context được dọn theo vòng đời xử lý HTTP, không phải session đăng nhập kiểu form login.

Nếu dùng servlet async, thread pool hoặc reactive stack, việc truyền security context có quy tắc riêng. Bài này chỉ xét đường đi **Servlet Resource Server**; không lấy filter Servlet áp dụng nguyên cho WebFlux Security.

### Vì sao không đặt đối tượng chưa xác thực vào context?

Ví dụ cách dùng cần tránh:

```java
// KHÔNG thực hiện trong filter tự viết:
BearerTokenAuthenticationToken requestToken =
        new BearerTokenAuthenticationToken(rawToken);

// Không gán nó vào context rồi cố cho request đi tiếp như đã đăng nhập:
SecurityContextHolder.getContext().setAuthentication(requestToken);
```

Ngay cả khi `isAuthenticated()` hiện là `false`, việc gắn object thô vào context làm mờ ranh giới giữa credential và identity. Nguy hiểm hơn, nếu custom code tự đặt cờ authenticated hoặc tự tạo `Authentication` với authorities mà chưa qua provider xác minh, tầng authorization có thể tin nhầm kết quả.

**Nguyên tắc triển khai:** chỉ đưa kết quả do cơ chế xác thực đáng tin tạo ra vào context; để `BearerTokenAuthenticationFilter` và `AuthenticationManager` quản lý quy trình này.

## 9. `isAuthenticated()` thực sự nói gì?

Interface `Authentication` có phương thức:

```java
boolean isAuthenticated();
```

Giá trị `false` của `BearerTokenAuthenticationToken` mới tạo nói rằng Spring Security **chưa chấp nhận** credential đó làm bằng chứng xác thực. Nó không diễn đạt “token đã hết hạn”; hết hạn chỉ được xác định khi decoder/introspector kiểm tra.

Các khẳng định cần phân biệt:

| Khẳng định | Đúng hay sai? | Giải thích |
|---|---|---|
| “Có BearerTokenAuthenticationToken tức là đã xác thực thành công.” | **Sai** | Object là yêu cầu xác thực |
| “Object này có raw token trong `getCredentials()`.” | **Đúng** | Credential cần được kiểm tra |
| “`isAuthenticated=false` chứng minh token giả.” | **Sai** | Chưa kiểm tra thì chưa thể kết luận |
| “Provider có thể trả một Authentication khác với đầu vào.” | **Đúng** | JWT/opaque thông thường cho kết quả kiểu khác |
| “Scope đọc từ raw JWT có thể dùng để cấp quyền ngay.” | **Sai** | Claims chưa kiểm tra chữ ký/issuer/audience |
| “Kết quả JWT đã xác thực luôn được phép truy cập mọi endpoint.” | **Sai** | Cần authorization theo endpoint và tài nguyên |

Một số implementation của `Authentication` có cơ chế cho phép đánh dấu `authenticated`, nhưng **không tự gọi `setAuthenticated(true)` để bỏ qua AuthenticationManager**. Đó không phải bước kiểm chứng credential; thay đổi flag không làm chữ ký JWT hợp lệ hay token opaque trở nên active.

### `getName()` trước và sau khác nhau

`Authentication.getName()` thường được dùng làm tên principal khi ghi audit log hoặc hiển thị identity. Ở giai đoạn `BearerTokenAuthenticationToken`, principal còn là raw token nên **không gọi `getName()` để ghi user ID hoặc để quyết định quyền**.

Sau khi xác thực JWT, principal name mặc định thường dựa trên `sub`, hoặc có thể được cấu hình qua converter. Với opaque token, principal name phụ thuộc attributes do introspector trả về và cách ánh xạ. Không lấy `BearerTokenAuthenticationToken.getPrincipal()` làm người dùng hiện tại.

## 10. Ví dụ đầy đủ một request thành công

Giả sử hệ thống dùng JWT access token cho API đọc đơn hàng. Chuỗi xử lý:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer VALID_ACCESS_TOKEN
```

Trong request này:

1. Servlet container giao request cho `springSecurityFilterChain`.
2. `FilterChainProxy` chọn `SecurityFilterChain` phù hợp.
3. `BearerTokenAuthenticationFilter` nhận request và gọi resolver.
4. Resolver trích xuất chuỗi `VALID_ACCESS_TOKEN`.
5. Filter tạo `BearerTokenAuthenticationToken` chứa chuỗi raw và chưa có authorities.
6. `AuthenticationManager` chuyển nó đến `JwtAuthenticationProvider`.
7. `JwtDecoder` xác minh chữ ký JWT, issuer, thời hạn và các validators của ứng dụng (ví dụ audience `orders-api`, profile `at+jwt` nếu sử dụng RFC 9068).
8. Provider chuyển JWT đã kiểm tra thành `JwtAuthenticationToken`; converter có thể ánh xạ `scope=orders.read` thành `SCOPE_orders.read`.
9. Filter gắn authenticated result vào security context.
10. `AuthorizationFilter` kiểm tra `hasAuthority("SCOPE_orders.read")`.
11. Controller/service kiểm tra quyền xem order `42`, ví dụ order thuộc tài khoản hoặc tenant của principal.
12. Nếu mọi điều kiện đều đạt, endpoint mới trả dữ liệu.

Kết quả hợp lệ không đồng nghĩa với việc Resource Server đã phát hành token; **Authorization Server là thành phần phát hành**, Resource Server chỉ xác thực và áp dụng quyền truy cập theo hợp đồng.

### Dấu mốc quan sát trong debugger

| Dấu mốc | Kiểu object dễ thấy | Ý nghĩa |
|---|---|---|
| Ngay sau `resolve` | `String` | Credential thô tách từ HTTP |
| Ngay sau constructor | `BearerTokenAuthenticationToken` | Authentication request chưa xác thực |
| Bên trong `JwtAuthenticationProvider` | `BearerTokenAuthenticationToken` | Provider đang dùng token string để gọi decoder |
| Sau `JwtDecoder.decode(...)` | `Jwt` | JWT đã được decoder kiểm tra theo validator cấu hình |
| Sau `JwtAuthenticationConverter` | `JwtAuthenticationToken` | Đã có principal và authorities từ token xác thực |
| Trong controller sau filter chain thành công | `Authentication` trong `SecurityContext` | Dùng cho authorization và thông tin principal |

Những đối tượng trên có thể khác khi dùng opaque token, custom converter hoặc nhiều security chain.

## 11. Ví dụ khi xác thực thất bại

### 11.1. JWT hết hạn

Request có header Bearer đúng khuôn dạng, resolver vẫn tạo `BearerTokenAuthenticationToken`. Khi provider gọi decoder, `exp` hết hạn dẫn đến authentication failure. Filter xử lý lỗi xác thực, thường trả **401 Unauthorized** với Bearer challenge. Không cập nhật context bằng một Authentication “gần đúng”.

### 11.2. JWT sai issuer hoặc audience

Giả sử một ID token OIDC do cùng nhà cung cấp ký, nhưng dành cho client `web-client`:

```json
{
  "iss": "https://id.example.com/realms/demo",
  "sub": "user-123",
  "aud": "web-client",
  "exp": 1910000000
}
```

Request bearer có thể tạo `BearerTokenAuthenticationToken` bình thường. Chữ ký đúng cũng không làm ID token biến thành access token cho `orders-api`. Decoder/validators phải áp dụng **token-purpose và audience contract** để từ chối token sai mục đích. Nếu không kiểm tra đúng audience/profile, API có nguy cơ chấp nhận nhầm token do cùng issuer phát hành.

### 11.3. Opaque token không active

Resolver tạo authentication request từ chuỗi token, nhưng introspection trả `active=false` hoặc từ chối theo hợp đồng issuer. Provider không tạo authenticated result; API từ chối credential.

### 11.4. Token hợp lệ nhưng không đủ scope

Provider xác thực JWT thành công và trả về `JwtAuthenticationToken` với authorities. Tuy nhiên, request `POST /api/orders` cần `orders.write`, còn token chỉ có `orders.read`. Đây là **authorization failure**, thường trả **403 Forbidden**, khác với `BearerTokenAuthenticationToken` bị từ chối ngay trong bước authentication.

### 11.5. Một token bị thu hồi trước khi hết hạn

Với JWT tự xác minh chữ ký và thời hạn, Resource Server thường không tự biết token đã bị thu hồi nếu không có cơ chế bổ sung (introspection, danh sách thu hồi, short TTL, cơ chế ràng buộc phiên...). `BearerTokenAuthenticationToken` cũng không thể biết thông tin này. Bảo đảm revocation là phần của **hợp đồng token và cơ chế xác thực**, không phải constructor của authentication request.

## 12. Xử lý lỗi và trạng thái HTTP

Trong Resource Server, các lỗi thường chia thành:

| Điểm phát sinh | Ví dụ | Kết quả HTTP thường gặp |
|---|---|---|
| Resolver không thấy Bearer token | Không có `Authorization` | Endpoint public có thể chạy; endpoint bảo vệ thường trả 401 |
| Resolver thấy Bearer credential malformed | `Authorization: Bearer ` | Lỗi ở bước trích xuất, thường 401 theo handler mặc định |
| Provider/decoder từ chối token | Chữ ký sai, hết hạn, audience sai | Thường **401 Unauthorized** và `invalid_token` |
| Provider xác thực thành công, authorization từ chối | Thiếu scope/quyền đối tượng | Thường **403 Forbidden**, có thể kèm `insufficient_scope` |

Ví dụ response:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Một response kiểu:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

biểu thị tình huống token có thể hợp lệ về xác thực nhưng request thiếu quyền. Header thực tế và `error_description` phụ thuộc cấu hình `BearerTokenAuthenticationEntryPoint`, `BearerTokenAccessDeniedHandler`, exception và chính sách endpoint.

Lưu ý: RFC 6750 phân biệt `invalid_request` (thường 400), `invalid_token` (401) và `insufficient_scope` (403); Spring Security có những quy tắc mapping cụ thể, nên không suy ra mọi malformed bearer đều chắc chắn 400.

**Không ghi nguyên token vào response lỗi**. Chẩn đoán nên xác định điểm lỗi (resolver, decoder, introspection, authorization) mà không để lộ credential.

## 13. Giao diện của lớp và các lớp dễ bị nhầm lẫn

Tên các lớp trong Spring Security có thể gần giống nhau:

| Lớp | Dùng ở đâu? | Trạng thái và mục đích |
|---|---|---|
| `BearerTokenAuthenticationToken` | Đầu vào của `AuthenticationManager` khi request có bearer token | Chưa xác thực; chứa raw token |
| `JwtAuthenticationToken` | Kết quả xác thực JWT Resource Server | Đã xác thực; mang `Jwt` và authorities |
| `BearerTokenAuthentication` | Kết quả xác thực opaque token Resource Server | Đã xác thực; mang principal và access token được xử lý |
| `OAuth2AuthenticationToken` | Thường gặp trong OAuth2 Login/OIDC Client | Authentication của người dùng đăng nhập qua OAuth2/OIDC client |
| `UsernamePasswordAuthenticationToken` | Xác thực username/password | Có thể ở dạng chưa xác thực hoặc kết quả đã xác thực tùy constructor/factory |
| `AnonymousAuthenticationToken` | Cơ chế anonymous trong filter chain | Biểu diễn request không có user authentication theo ngữ cảnh anonymous |
| `OAuth2AccessToken` | Mô hình dữ liệu access token trong Spring Security | **Không** phải một implementation thay thế cho authentication request |

Phân biệt quan trọng:

- **`BearerTokenAuthenticationToken`** không phải OIDC ID token.
- **`BearerTokenAuthentication`** là lớp khác và thường đại diện **kết quả opaque-token authentication thành công**.
- **`JwtAuthenticationToken`** là kết quả Resource Server xác thực JWT; cùng chữ “Jwt” không có nghĩa đây là kết quả `oauth2Login()`.
- **`OAuth2AuthenticationToken`** thường mô tả authentication từ OAuth2 Login; không sử dụng nó để bỏ qua kiểm tra Bearer access token cho REST API.

## 14. Ví dụ quan sát đối tượng trong ứng dụng

Trong controller, Spring Security có thể tiêm đối tượng `Authentication` **sau khi request đi qua filter chain**. Ví dụ:

```java
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PrincipalController {

    @GetMapping("/api/me")
    String me(Authentication authentication) {
        if (authentication instanceof JwtAuthenticationToken jwtAuth) {
            // authentication này đã qua JWT Resource Server validation.
            return jwtAuth.getName();
        }
        return "Authenticated with another supported mechanism";
    }
}
```

Ví dụ giả định endpoint `/api/me` được cấu hình `authenticated()`. Trường hợp không có authentication hoặc ứng dụng hỗ trợ nhiều cơ chế cần xử lý theo yêu cầu thực tế; không dùng ví dụ này như chính sách quyền hoàn chỉnh.

Nếu muốn xem luồng internal trong debugger, có thể đặt breakpoint ở:

- `BearerTokenAuthenticationFilter#doFilterInternal` khi resolver trả token.
- Constructor hoặc getter của `BearerTokenAuthenticationToken` để xem trạng thái request.
- `ProviderManager#authenticate` để quan sát provider được chọn.
- `JwtAuthenticationProvider#authenticate` hoặc `OpaqueTokenAuthenticationProvider#authenticate`.
- `NimbusJwtDecoder#decode` khi API dùng JWT/JWS.
- Chỗ filter gắn authenticated result vào `SecurityContextHolder`.
- `AuthorizationFilter` để xem kiểm tra quyền endpoint.

Đây là các **điểm quan sát kiến trúc**, tên lớp và vị trí phương thức có thể thay đổi giữa phiên bản Spring Security. Với token thật, debugger có thể hiển thị raw token trong bộ nhớ, nên hạn chế chia sẻ screenshot, dump hoặc output debug có chứa credential.

### Logging an toàn

Nên log:

- Request ID/tracing ID và endpoint (không kèm bearer token ở URL).
- Bước xử lý `resolution`, `jwt_validation`, `opaque_introspection`, `authorization`.
- Kết quả ngắn gọn như `invalid_signature`, `expired`, `wrong_audience`, `insufficient_scope` nếu hệ thống chuẩn hóa được.

Không nên log:

- `getToken()`, `getCredentials()`, raw header `Authorization`.
- Toàn bộ `BearerTokenAuthenticationToken` qua serialize/log object tự động.
- Refresh token, ID token, opaque token hoặc JWT payload nhạy cảm.

Bearer token là credential có thể bị dùng lại bởi bên chiếm được, nên việc log raw value tạo rủi ro ngoài phạm vi của một lỗi lập trình thông thường.

## 15. Sai lầm triển khai và cách tránh

### Sai lầm 1: Tin object vì nó triển khai `Authentication`

```java
// Không dùng logic này để cấp quyền:
Authentication request = new BearerTokenAuthenticationToken(rawToken);
if (request != null) {
    // "Có Authentication" không có nghĩa đã xác thực!
}
```

`Authentication` là một **giao diện cho cả yêu cầu và kết quả**. Kiểu object và trạng thái được xác thực mới quyết định nó có thể dùng cho authorization hay chưa, đồng thời quyền vẫn phải được kiểm tra ở tầng phù hợp.

### Sai lầm 2: Tự đặt `isAuthenticated=true`

```java
// Không biến credential raw thành identity bằng cách bật cờ.
BearerTokenAuthenticationToken request =
        new BearerTokenAuthenticationToken(rawToken);
// request.setAuthenticated(true); // Không được làm như một cơ chế xác thực.
```

Flag không kiểm tra signature, issuer, audience, scope hoặc trạng thái introspection. Cần gọi AuthenticationManager và tin **kết quả provider trả về**, không tự chế kết quả khi chưa xác minh.

### Sai lầm 3: Dùng raw token làm user ID

```java
// Không làm với một authentication request chưa xác thực:
// String userId = request.getPrincipal().toString();
```

Ở lớp này `principal` là raw token, không phải user ID đã xác thực. Thao tác đó còn có thể khiến token bị ghi vào database hoặc log như một tên người dùng. Dùng principal đã xác thực (ví dụ `JwtAuthenticationToken`) với claims đã được decoder kiểm tra.

### Sai lầm 4: Coi “đã decode JWT” là “đã xác minh JWT”

Có thể decode Base64URL để đọc JSON payload, nhưng bước đó không chứng minh chữ ký đúng. `BearerTokenAuthenticationToken` chỉ giữ chuỗi raw. Mọi quyền `scope`, `roles`, `tenant` phải được lấy từ nguồn **đã được xác minh**, thông qua JWT decoder/introspector đáng tin.

### Sai lầm 5: Bỏ qua audience vì token do issuer quen thuộc ký

Một OIDC Provider có thể ký ID token dành cho `web-client` và access token cho `orders-api` bằng cùng khóa. Nếu API không kiểm tra audience và token profile, nó có thể nhận nhầm ID token làm bearer access token. Phân loại và xác thực token không được ủy quyền cho việc “JWT nhìn hợp lệ”.

### Sai lầm 6: Tự viết filter thứ hai làm lại cơ chế Bearer

Một custom servlet filter tự tách header rồi đẩy object chưa xác thực vào context có thể xung đột với filter chuẩn, xử lý lỗi thiếu nhất quán và làm mờ ranh giới trust. Thường nên cấu hình `oauth2ResourceServer().jwt()` hoặc `opaqueToken()`, bổ sung `JwtDecoder`, `BearerTokenResolver` hay converter ở đúng extension point.

Nếu bắt buộc tùy biến `AuthenticationProvider`, phải giữ đầy đủ quy tắc xác thực, error handling và authorization, không bỏ qua bước kiểm tra ở provider.

## 16. Những câu hỏi giúp đọc đúng luồng trong debugger

Khi bắt gặp `BearerTokenAuthenticationToken`, có thể xác định giai đoạn request theo các câu hỏi:

1. **Đối tượng được tạo ở đâu?** Nếu tại `BearerTokenAuthenticationFilter`, tức Bearer credential mới được trích xuất từ HTTP.
2. **`isAuthenticated()` đã là `true` chưa?** Khi mới tạo, nó là `false`; không suy diễn token sai hay đúng.
3. **`getPrincipal()` là gì?** Ở bước này là raw token, chưa phải user.
4. **Provider nào đang xử lý?** `JwtAuthenticationProvider` cho JWT, `OpaqueTokenAuthenticationProvider` cho opaque token.
5. **JWT decoder/introspector có xác minh thành công chưa?** Đây là ranh giới giữa dữ liệu không tin cậy và authenticated result.
6. **Authentication object cuối cùng là lớp gì?** JWT thường là `JwtAuthenticationToken`; opaque thường là `BearerTokenAuthentication`.
7. **Kết quả có được đặt vào `SecurityContext` chưa?** Chỉ sau thành công mới dùng cho authorization.
8. **Audience, profile và scope đã được kiểm tra ở đâu?** Chữ ký đúng không tự chấp thuận request API.
9. **Nếu endpoint bị từ chối, lỗi ở authentication hay authorization?** 401 thường là lỗi credential; 403 thường là thiếu quyền sau xác thực.
10. **Có thông tin nhạy cảm đang bị log?** Raw bearer token là credential và cần được bảo vệ.

## 17. Kết luận về vai trò của authentication request

Có thể ghi nhớ ngắn gọn:

```text
Authorization: Bearer <raw-token>
            |
            v
    BearerTokenResolver
            |
            v
BearerTokenAuthenticationToken
  principal      = raw token string
  credentials    = raw token string
  authorities    = []
  authenticated  = false
            |
            v
 AuthenticationManager
            |
            v
       Provider
       /      \
      /        \
 JwtDecoder   OpaqueTokenIntrospector
      \        /
       \      /
     Authentication đã xác thực
       (JwtAuthenticationToken /
        BearerTokenAuthentication)
            |
            v
   SecurityContextHolder
            |
            v
 Authorization + business rules
```

**`BearerTokenAuthenticationToken` là lời đề nghị xác thực dựa trên bearer credential**, không phải bằng chứng danh tính hay quyết định cho phép truy cập. Filter tạo nó, AuthenticationManager/Provider kiểm tra token, và chỉ **kết quả đã xác thực** mới được gắn vào SecurityContext để các quy tắc phân quyền xử lý tiếp.

## 18. Tài liệu tham khảo

- **Spring Security Reference — OAuth 2.0 Resource Server (Servlet)**: các thành phần filter, JWT/opaque token và authentication. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html
- **Spring Security Reference — JWT Resource Server**: JWT decoder, claim validation và quyền từ scope. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- **Spring Security API — `BearerTokenAuthenticationToken`**: đối tượng Authentication cho bearer token chưa xác thực. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/BearerTokenAuthenticationToken.html
- **Spring Security API — `BearerTokenAuthenticationFilter`**: nơi trích xuất bearer credential và gọi AuthenticationManager. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/authentication/BearerTokenAuthenticationFilter.html
- **Spring Security API — `JwtAuthenticationProvider`**: xác thực JWT từ bearer authentication request. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationProvider.html
- **Spring Security API — `OpaqueTokenAuthenticationProvider`**: xử lý opaque access token qua introspection. https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/authentication/OpaqueTokenAuthenticationProvider.html
- **RFC 6750 — OAuth 2.0 Bearer Token Usage**: cách gửi Bearer credential và xử lý lỗi. https://www.rfc-editor.org/rfc/rfc6750
- **RFC 7519 — JSON Web Token**: định dạng và các claim JWT. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 7662 — OAuth 2.0 Token Introspection**: kiểm tra trạng thái token opaque. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens**: ràng buộc JWT access token với đúng resource và mục đích. https://www.rfc-editor.org/rfc/rfc9068
