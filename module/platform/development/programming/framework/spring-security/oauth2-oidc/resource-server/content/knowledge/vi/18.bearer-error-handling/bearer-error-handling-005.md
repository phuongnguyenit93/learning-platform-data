# BearerTokenAuthenticationEntryPoint và phản hồi khi chưa xác thực

Khi xây dựng **Spring Security OAuth 2.0/OIDC Resource Server**, API phải trả lời rõ ràng cho client trong những tình huống như: chưa gửi access token, gửi token sai, token hết hạn hoặc token không dành cho Resource Server. Với cơ chế **HTTP Bearer Authentication**, phần quan trọng của câu trả lời không chỉ là mã HTTP `401 Unauthorized` mà còn là header **`WWW-Authenticate`**. Spring Security cung cấp lớp **`BearerTokenAuthenticationEntryPoint`** để thực hiện vai trò này.

Bài học đi sâu vào những vấn đề sau:

- `BearerTokenAuthenticationEntryPoint` là gì và được gọi vào thời điểm nào.
- Vì sao thiếu token thường nhận `401` với challenge `WWW-Authenticate: Bearer`.
- Cách các tham số `realm`, `error`, `error_description`, `error_uri` liên quan đến RFC 6750.
- Vì sao lỗi Bearer malformed có thể là `400 invalid_request`, còn token không hợp lệ là `401 invalid_token`.
- Phân biệt **chưa xác thực** với **đã xác thực nhưng thiếu quyền**, trong đó trường hợp thứ hai thường là `403 Forbidden` và thuộc `BearerTokenAccessDeniedHandler`.
- Cách cấu hình `realm`, tùy chỉnh phản hồi JSON mà vẫn giữ Bearer challenge, theo dõi lỗi và thử hành vi qua MockMvc/curl.
- Những bẫy bảo mật khi ghi log token, làm lộ exception details, thay `401` bằng `200`, hoặc để client hiểu sai việc cần refresh token.

> **Nguyên tắc:** Khi một API được bảo vệ bằng bearer access token, việc trả `401` và Bearer challenge đúng chuẩn cho lỗi authentication giúp client biết yêu cầu chưa đủ điều kiện xác thực. Nhưng `401` **không có nghĩa mọi lỗi đều được sửa bằng refresh token**, và `BearerTokenAuthenticationEntryPoint` **không dùng để cấp quyền cho caller**.

## 1. Bearer token và HTTP Authentication

Trong OAuth 2.0, một client thường gửi access token trong header:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
Accept: application/json
```

Chuỗi token có thể là JWT hoặc opaque token. Dù loại nào, bearer token là **credential**: bên nào cầm được chuỗi token có thể thử dùng nó để gọi API. Resource Server phải xác thực token phù hợp theo cấu hình:

- **JWT Resource Server:** xác minh JWS signature, khóa công khai, issuer, thời gian, audience và những validators đã đặt.
- **Opaque Token Resource Server:** introspect token tại Authorization Server và áp các ràng buộc bổ sung theo hợp đồng.
- **Authorization sau xác thực:** kiểm tra scope/authority, role và quyền đối với tài nguyên cụ thể.

Nếu client không gửi token hoặc gửi token không hợp lệ, API cần từ chối trước khi xem caller là principal đã xác thực.

### 1.1. Vì sao có header `WWW-Authenticate`?

HTTP authentication dùng mô hình **challenge–response**. Server có thể gửi header `WWW-Authenticate` trong phản hồi để cho client biết phương thức xác thực được yêu cầu, chẳng hạn:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

`Bearer` là tên authentication scheme. Nó **không** phải là token, secret, scope, cookie hay phương pháp đăng nhập người dùng. Đây là tín hiệu Resource Server chấp nhận **Bearer credential** cho resource tương ứng.

Nếu server đặt `realm`:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
```

Client nhìn thấy realm như một mô tả protection space. Realm có thể hữu ích khi hệ thống có nhiều API/security domains nhưng không được dùng thay issuer, audience hoặc tenant validation.

### 1.2. Một response có thể không cần JSON body

Đối với authentication challenge, header là thành phần cần thiết. Một phản hồi:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Content-Length: 0
```

hoàn toàn có thể đủ theo hợp đồng Bearer của API. Một số sản phẩm muốn thêm body JSON để frontend hiển thị; đó là một lựa chọn tùy chỉnh, **không phải yêu cầu bắt buộc của RFC 6750**.

## 2. `BearerTokenAuthenticationEntryPoint` là gì?

Trong Spring Security Servlet, interface tổng quát `AuthenticationEntryPoint` có một phương thức chính:

```java
void commence(
    HttpServletRequest request,
    HttpServletResponse response,
    AuthenticationException authenticationException
) throws IOException, ServletException;
```

Ý tưởng của method `commence(...)` là **bắt đầu quy trình yêu cầu xác thực** khi request chưa có Authentication hợp lệ. Ở một ứng dụng web session truyền thống, entry point có thể redirect sang trang login. Ở Resource Server chỉ dùng Bearer token, redirect HTML login thường không phù hợp; client cần **HTTP status và challenge**.

`BearerTokenAuthenticationEntryPoint` là implementation dành cho Bearer authentication. Nó có khả năng:

1. Ghi header `WWW-Authenticate` cho scheme Bearer.
2. Tùy chọn công bố `realm` khi đã cấu hình.
3. Nếu exception mang `BearerTokenError`, đưa những error parameters phù hợp vào challenge.
4. Chọn HTTP status dựa trên lỗi Bearer phù hợp; nếu không có thông tin lỗi đặc thù, thường dùng `401 Unauthorized`.

Các import chính:

```java
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.security.core.AuthenticationException;
import jakarta.servlet.ServletException;
import java.io.IOException;
```

### 2.1. Entry point không phải nơi xác thực token

`BearerTokenAuthenticationEntryPoint` **không**:

- Tải JWKS hoặc xác minh JWT signature.
- Gọi introspection endpoint.
- Chọn issuer đáng tin.
- Đọc token rồi tạo principal.
- Cấp scope/role cho request.
- Kiểm tra quyền sở hữu đơn hàng.

Nó nhận **AuthenticationException** đã phát sinh trong luồng bảo mật và định dạng **HTTP response khi cần authentication**.

### 2.2. Entry point không tự xử lý mọi lỗi 403

Khi token hợp lệ nhưng caller thiếu authority, lỗi thường là **AccessDeniedException**, thuộc nhánh authorization. Spring Security Resource Server cung cấp `BearerTokenAccessDeniedHandler` để xử lý Bearer authorization failures phù hợp, thường là `403 Forbidden` và có thể có challenge `insufficient_scope`.

Vì vậy không nên gán nhầm trách nhiệm:

| Loại lỗi | Thành phần điển hình | HTTP thường gặp |
|---|---|---|
| Không có Authentication hợp lệ | `BearerTokenAuthenticationEntryPoint` | `401` |
| Access token không hợp lệ | `BearerTokenAuthenticationEntryPoint` | `401 invalid_token` |
| Bearer request sai định dạng | `BearerTokenAuthenticationEntryPoint` với `BearerTokenError` tương ứng | Có thể `400 invalid_request` |
| Caller đã xác thực, thiếu quyền | `BearerTokenAccessDeniedHandler` | `403 insufficient_scope` hoặc `403` |
| Token đúng scope nhưng không có quyền với order 42 | Service/method authorization | `403` hoặc `404` theo policy |
| Controller gặp lỗi nghiệp vụ | Business exception handler | Tùy loại lỗi, không tự thành Bearer challenge |

## 3. Luồng Spring Security Servlet: entry point được gọi ở đâu?

Với một JWT Resource Server, chuỗi xử lý logic thường là:

```mermaid
flowchart TD
    A["HTTP request"] --> B["SecurityFilterChain"]
    B --> C["BearerTokenAuthenticationFilter"]
    C --> D{"Bearer token có được giải quyết từ request?"}
    D -- "Có" --> E["AuthenticationManager / JwtAuthenticationProvider"]
    E --> F["JwtDecoder: signature + validators"]
    F --> G{"Decode và xác thực thành công?"}
    G -- "Không" --> H["Authentication failure"]
    H --> I["BearerTokenAuthenticationEntryPoint"]
    D -- "Không" --> J["Đi tiếp với anonymous/unauthenticated context"]
    J --> K["AuthorizationFilter: route protected?"]
    K -- "Có, cần authenticated" --> L["ExceptionTranslationFilter gọi AuthenticationEntryPoint"]
    L --> I
    G -- "Có" --> M["JwtAuthenticationToken / SecurityContext"]
    M --> N["AuthorizationFilter"]
    N --> O{"Đủ authority?"}
    O -- "Không" --> P["BearerTokenAccessDeniedHandler"]
    O -- "Có" --> Q["Controller / service"]
    I --> R["HTTP Bearer challenge"]
    P --> S["HTTP authorization denied"]
```

Sơ đồ thể hiện luồng khái niệm. Tên các filters, provider và nhánh xử lý exception có thể khác chi tiết tùy phiên bản/configuration, nhưng **hai tình huống chính** rất quan trọng:

- Token được gửi nhưng **authentication thất bại**: failure path kích hoạt entry point.
- **Không gửi token**: bearer filter có thể không tạo Authentication; khi route yêu cầu xác thực, authorization/exception translation kích hoạt entry point.

### 3.1. Khi không có token, Bearer filter không nhất thiết tự báo lỗi

Giả sử request:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Accept: application/json
```

Nếu `BearerTokenResolver` không tìm thấy token, `BearerTokenAuthenticationFilter` thường cho request đi tiếp thay vì lập tức báo lỗi. Sau đó:

1. Route `/api/orders/**` yêu cầu một Authentication phù hợp.
2. `AuthorizationFilter` phát hiện caller chưa đủ điều kiện.
3. Cơ chế exception translation bắt đầu authentication bằng entry point.
4. Server gửi challenge cho client.

Điều này giải thích vì sao endpoint `permitAll()` có thể truy cập được **không cần Authorization header**, trong khi endpoint protected trả `401`.

### 3.2. Gửi token sai là tình huống khác

Nếu client gửi một token nhưng decoder không thể xác thực:

```http
Authorization: Bearer invalid-token-value
```

thì AuthenticationProvider/decoder/introspector từ chối. Entry point có thể nhận exception chứa `BearerTokenError` và tạo challenge chi tiết hơn.

Không cần chờ tới controller, vì authentication là trách nhiệm security filter chain.

### 3.3. Tránh để controller tự trả `401` theo cách ngẫu hứng

Một controller trả:

```java
return ResponseEntity.status(401).body("Please log in");
```

chỉ là response do developer tự dựng; nó **không bảo đảm** chứa `WWW-Authenticate` hay tương thích với Bearer error semantics. Đối với protected endpoints, nên để Spring Security xử lý authentication ở filter layer; controller đảm nhiệm nghiệp vụ sau khi request được xác thực.

## 4. Thiếu token: challenge không cần báo “invalid_token”

Theo RFC 6750, nếu request **không gửi thông tin xác thực**, server nên đưa Bearer challenge nhưng **không nên tự gắn error code** cho trường hợp này.

Ví dụ phù hợp:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
```

Trong khi đây có thể là thông tin gây hiểu nhầm cho request chưa có token:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Vì **không có token nào để kết luận invalid**. Client đơn giản cần biết endpoint đòi Bearer authentication.

Một browser hoặc API client có thể dùng thông tin này để chuyển sang flow lấy access token thích hợp, hoặc thông báo người dùng đăng nhập. Resource Server **không cung cấp password login flow chỉ vì có Bearer challenge**.

### 4.1. Request thiếu token ở endpoint public

Giả sử:

```java
.requestMatchers(HttpMethod.GET, "/public/catalog").permitAll()
.requestMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
```

Kết quả thông thường:

| Request | Header Authorization | Quyết định |
|---|---|---|
| `GET /public/catalog` | Không có | Được phép qua HTTP authorization |
| `GET /api/orders/42` | Không có | Bị yêu cầu xác thực, thường `401` + Bearer challenge |
| `GET /api/orders/42` | Token hợp lệ có scope đọc | Đi tiếp vào business authorization |
| `GET /api/orders/42` | Token hợp lệ thiếu scope đọc | Thường `403` |
| `GET /api/orders/42` | Token sai/hết hạn | Thường `401 invalid_token` |

Chú ý: `permitAll()` **không có nghĩa bỏ qua mọi security filter**. Nếu client chủ động gửi một Bearer header bị malformed ngay cả vào route public, filter có thể xử lý token lỗi trước bước authorization và tạo error response tùy cấu hình.

## 5. HTTP Bearer error semantics theo RFC 6750

RFC 6750 mô tả các lỗi phổ biến khi truy cập protected resources.

| Bearer error code | Khi nào xuất hiện | HTTP status điển hình |
|---|---|---|
| `invalid_request` | Request sai dạng, trùng/không hợp lệ Bearer token transport hoặc các tham số không hợp lệ | `400 Bad Request` |
| `invalid_token` | Token hết hạn, bị thu hồi, sai định dạng, không thể được xác thực hoặc không được chấp nhận theo contract | `401 Unauthorized` |
| `insufficient_scope` | Token được xác thực nhưng không đủ scope cần cho resource | `403 Forbidden` |

Các status là hành vi quy định/điển hình của Bearer token usage; exception handlers, gateway hoặc policy tùy biến có thể tác động tới phản hồi thực tế. Khi thiết kế API, cần giữ sự phân biệt có ý nghĩa thay vì cưỡng ép mọi lỗi thành `401`.

### 5.1. Ví dụ: `invalid_request`

Một Bearer request bị coi là sai định dạng có thể nhận:

```http
HTTP/1.1 400 Bad Request
WWW-Authenticate: Bearer realm="orders-api", error="invalid_request"
```

Ví dụ các vấn đề có thể gây `invalid_request`: gửi nhiều phương thức mang token không hợp lệ theo resolver, Authorization header malformed, hoặc vi phạm cách truyền token được Resource Server chấp nhận.

**Không kết luận mọi Authorization header xấu đều phải ra đúng một mã:** `DefaultBearerTokenResolver` và cấu hình phiên bản cụ thể quyết định lỗi phát sinh. Nhưng `invalid_request` khác `invalid_token` về mặt ý nghĩa: một bên nói request mang credential sai cách, bên kia nói token không được chấp nhận.

### 5.2. Ví dụ: `invalid_token`

Token đã gửi nhưng chữ ký không hợp lệ hoặc hết hạn:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api", error="invalid_token"
```

Một số trường hợp có thêm mô tả:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api",
  error="invalid_token",
  error_description="The access token is invalid"
```

Đây là cách xuống dòng để người học đọc; **trên HTTP thực, header phải được gửi đúng cú pháp header value**, không đưa newline tùy ý vào giá trị.

Trạng thái token không hợp lệ có thể do JWT signature, issuer, audience, time validators hoặc opaque introspection failure. Đừng tiết lộ raw JWT, dữ liệu key, claims nhạy cảm hay cấu trúc hệ thống nội bộ qua `error_description`.

### 5.3. Ví dụ: `insufficient_scope`

Token hợp lệ có `orders.read` nhưng endpoint yêu cầu `orders.export`:

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer realm="orders-api",
  error="insufficient_scope",
  scope="orders.export"
```

Đoạn trên mô tả **một phản hồi có thể có**; Spring Security không tự suy ra và phát tên scope bắt buộc của mọi matcher rule trong mọi cấu hình. Tham số `scope` phải có căn cứ và chỉ được xuất khi biết rõ, không tự cho là framework sẽ tự bổ sung.

Thông thường `BearerTokenAccessDeniedHandler` là thành phần liên quan tới nhánh authorization denied. `BearerTokenAuthenticationEntryPoint` không phải nơi thiết kế API “thiếu quyền nhưng token đã hợp lệ”.

## 6. Những tham số của `WWW-Authenticate: Bearer`

Challenge Bearer có thể chứa các tham số:

| Tham số | Ý nghĩa | Lưu ý |
|---|---|---|
| `realm` | Protection space được server công bố | Không thay issuer/audience; không dùng tên chứa dữ liệu nhạy cảm |
| `error` | Mã lỗi như `invalid_token` | Thiếu credential thường không kèm error |
| `error_description` | Mô tả giúp hiểu lỗi | Tránh tiết lộ chi tiết nhạy cảm hoặc thông tin có thể bị lợi dụng |
| `error_uri` | URI dẫn tới tài liệu về lỗi | Không dùng URL do client tự đưa; có thể bỏ nếu không cần |
| `scope` | Scope cần thiết, thường liên quan `insufficient_scope` | Không nhất thiết có sẵn từ Spring authorization matcher |

Các giá trị được encode/escape theo cú pháp header, không được tự nối chuỗi từ input thiếu kiểm soát.

### 6.1. Realm khác issuer

Một cấu hình có thể có:

```text
Issuer:
  https://login.example.test/realms/shop

Audience:
  orders-api

Bearer realm:
  orders-api
```

Cả ba có ý nghĩa khác nhau:

- `iss` trong token: issuer mà Resource Server tin cậy.
- `aud`: token có được phát cho API này không.
- `realm`: cách mô tả protection space trong HTTP challenge.

**Không dùng Bearer realm để xác thực issuer hoặc audience**. Một attacker có thể gửi token sai issuer dù challenge của server đặt realm đẹp và đúng.

### 6.2. Header value không nên chứa user input

Ví dụ không an toàn:

```java
String realm = request.getParameter("realm");
entryPoint.setRealmName(realm);
```

Nếu realm đến từ request chưa xác thực, client có thể thao túng response header. Trong thực tế realm nên là **giá trị cấu hình server đáng tin cậy**, thường được xác định khi tạo bean và không thay đổi theo từng request.

## 7. Spring Security thực hiện challenge từ `BearerTokenError`

Trong Spring Security Resource Server, một exception authentication có thể là `OAuth2AuthenticationException` mang `OAuth2Error`. Với lỗi chuyên cho Bearer transport, Spring Security còn có `BearerTokenError`.

Ví dụ mã khái niệm:

```java
BearerTokenError error =
    BearerTokenErrors.invalidToken("The access token is invalid");

OAuth2AuthenticationException exception =
    new OAuth2AuthenticationException(error);
```

Các import tương ứng:

```java
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.BearerTokenError;
import org.springframework.security.oauth2.server.resource.BearerTokenErrors;
```

`BearerTokenAuthenticationEntryPoint` có thể đọc thông tin lỗi trong exception và xây dựng challenge Bearer phù hợp.

**Không cần tự tạo exception này trong controller thông thường.** Nó minh họa cách Spring Security biểu diễn lỗi ở lớp authentication.

### 7.1. Phân biệt error object và HTTP response

`BearerTokenError` mô tả lỗi: mã, HTTP status, description/URI và có thể có phạm vi scope liên quan. `BearerTokenAuthenticationEntryPoint` sử dụng thông tin đó để trả phản hồi.

Với authentication exception không mang thông tin Bearer chuyên biệt, entry point thường chỉ có thể tạo challenge tổng quát. Điều đó hợp lý hơn là bịa một lý do “token hết hạn” khi framework không có bằng chứng.

### 7.2. Không ép mọi exception thành `invalid_token`

Một request không mang token, một bearer header malformed và một token ký sai **không phải cùng một sự kiện**. Một entry point tùy biến nên để framework giữ cách phân loại chuẩn hoặc chủ động map có kiểm soát.

Không bắt `Exception` rồi luôn trả `invalid_token`; các lỗi hạ tầng như JWKS endpoint unavailable, DNS/TLS/introspection timeout có thể cần phân loại vận hành khác, dù authentication vẫn phải fail closed.

## 8. Cấu hình mặc định JWT Resource Server

Spring Boot có thể cấu hình issuer và audience:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/shop
          audiences:
            - orders-api
```

Property audience được hỗ trợ ở các phiên bản Spring Boot phù hợp; nếu dự án dùng decoder tùy biến hoặc phiên bản khác, phải gắn audience validation tương ứng.

SecurityFilterChain:

```java
@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/catalog")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .build();
    }
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
```

Với cấu hình này, Spring Security thiết lập cơ chế Bearer authentication và xử lý authentication failures theo nhánh Resource Server, thường có Bearer entry point phù hợp.

**Điểm ranh giới:** `audiences: orders-api` xác minh token dành cho API nào; `hasAuthority("SCOPE_orders.read")` kiểm tra quyền thao tác trên endpoint. Một token đúng issuer nhưng sai audience phải bị loại từ authentication, không cho qua chỉ vì có scope nhìn có vẻ đúng.

## 9. Cấu hình rõ `BearerTokenAuthenticationEntryPoint` và realm

Nếu API muốn challenge có realm nhất quán, có thể tạo entry point trực tiếp:

```java
@Configuration
public class BearerChallengeConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        BearerTokenAuthenticationEntryPoint entryPoint =
            new BearerTokenAuthenticationEntryPoint();

        entryPoint.setRealmName("orders-api");

        BearerTokenAccessDeniedHandler accessDeniedHandler =
            new BearerTokenAccessDeniedHandler();

        accessDeniedHandler.setRealmName("orders-api");

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/catalog")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> {
                oauth2.jwt(Customizer.withDefaults());
                oauth2.authenticationEntryPoint(entryPoint);
                oauth2.accessDeniedHandler(accessDeniedHandler);
            })
            .build();
    }
}
```

Imports:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.access.BearerTokenAccessDeniedHandler;
import org.springframework.security.web.SecurityFilterChain;
```

Cách đọc:

- `BearerTokenAuthenticationEntryPoint` chịu trách nhiệm cho challenge khi authentication chưa thành công.
- `setRealmName("orders-api")` mô tả protection space.
- `BearerTokenAccessDeniedHandler` xử lý AccessDeniedException trong Resource Server, không đánh đồng với thiếu token.
- `oauth2.jwt(...)` kích hoạt JWT Resource Server.
- `authorizeHttpRequests(...)` bảo vệ endpoint theo method/path/authority.

**Chỉ dùng một cấu hình SecurityFilterChain phù hợp cho cùng request**, hoặc cấu hình nhiều chains có phạm vi và thứ tự rõ ràng. Các snippets trong bài minh họa cách cấu hình; không dán nhiều bean `apiSecurity` trùng tên vào cùng application.

### 9.1. Realm là cấu hình mô tả, không cấp quyền

Ví dụ response khi thiếu token:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
```

Điều này không khiến Resource Server chấp nhận token có `aud=payments-api` hoặc `iss` từ issuer khác. Decoder/validator tiếp tục giữ ranh giới tin cậy riêng.

### 9.2. Bản chất stateless của Bearer Resource Server

Với API dựa trên bearer access token, không nên redirect user tới trang HTML login khi chỉ thiếu token. Trách nhiệm lấy token thường thuộc OAuth client. Resource Server bảo vệ dữ liệu và trả challenge có ý nghĩa HTTP.

Stateless authorization không nhất thiết loại bỏ mọi session/cookie ở một ứng dụng kết hợp web UI và API. Nếu có nhiều filter chains, phải đặt Bearer authentication cho đúng nhánh API, thay vì vô tình dùng form login entry point cho API.

## 10. Tùy chỉnh JSON body mà vẫn giữ `WWW-Authenticate`

Một số frontend muốn response dạng JSON thống nhất:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Content-Type: application/problem+json

{"type":"about:blank","title":"Unauthorized","status":401}
```

Nếu chỉ trả JSON và bỏ `WWW-Authenticate`, server có thể đánh mất thông tin Bearer challenge mà API clients dựa vào.

Cách triển khai an toàn hơn là **ủy quyền trước cho BearerTokenAuthenticationEntryPoint** để tạo status/header chuẩn, rồi thêm một JSON body trung tính nếu response chưa committed.

### 10.1. Ví dụ một custom `AuthenticationEntryPoint`

```java
public final class JsonBearerAuthenticationEntryPoint
        implements AuthenticationEntryPoint {

    private final BearerTokenAuthenticationEntryPoint delegate;
    private final ObjectMapper objectMapper;

    public JsonBearerAuthenticationEntryPoint(
            ObjectMapper objectMapper,
            String realm) {

        this.objectMapper = Objects.requireNonNull(objectMapper);
        this.delegate = new BearerTokenAuthenticationEntryPoint();
        this.delegate.setRealmName(realm);
    }

    @Override
    public void commence(
            HttpServletRequest request,
            HttpServletResponse response,
            AuthenticationException exception)
            throws IOException, ServletException {

        // Ghi Bearer challenge và HTTP status theo Spring Security.
        delegate.commence(request, response, exception);

        if (response.isCommitted()) {
            return;
        }

        int status = response.getStatus();
        String title = (status == 400)
            ? "Bad Request"
            : (status == 401)
                ? "Unauthorized"
                : "Authentication Error";

        Map<String, Object> problem = Map.of(
            "type", "about:blank",
            "title", title,
            "status", status
        );

        response.setCharacterEncoding(StandardCharsets.UTF_8.name());
        response.setContentType("application/problem+json");

        objectMapper.writeValue(response.getWriter(), problem);
    }
}
```

Imports:

```java
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import java.util.Objects;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.web.AuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
```

Cấu hình sử dụng:

```java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        ObjectMapper objectMapper) throws Exception {

    AuthenticationEntryPoint jsonEntryPoint =
        new JsonBearerAuthenticationEntryPoint(
            objectMapper, "orders-api");

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/**").authenticated()
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> {
            oauth2.jwt(Customizer.withDefaults());
            oauth2.authenticationEntryPoint(jsonEntryPoint);
        })
        .build();
}
```

Đoạn JSON body minh họa cách **giữ status/header do delegate tạo**, không ép mọi failure thành `401` và không lộ lỗi nội bộ. Trong API thật, các routes cần `hasAuthority(...)` thay vì chỉ `authenticated()` nếu chức năng có quyền cụ thể.

### 10.2. Những điều cần chú ý khi thêm body

- **Không overwrite** header `WWW-Authenticate` do delegate đã tạo.
- Không làm mất status `400` với `invalid_request` khi custom body.
- Không đưa raw token, JWT claims, introspection secret, stack trace hoặc thông tin key vào JSON.
- Không tự copy `exception.getMessage()` ra `detail` cho caller mà không có quy tắc làm sạch.
- Nếu response đã committed thì không viết thêm.
- Đảm bảo encoding, content type và error handling thống nhất.
- Nếu cần body riêng cho `403`, tùy chỉnh **AccessDeniedHandler** tương ứng, không cố dùng AuthenticationEntryPoint để xử lý cả hai.

### 10.3. Vì sao không phải mọi API đều cần JSON body?

HTTP clients có thể xử lý error dựa trên status và `WWW-Authenticate`. Thêm JSON body nghĩa là API có thêm contract về error format, versioning, localization và thông tin hiển thị. Nếu chưa có nhu cầu thực tế, challenge chuẩn đã là một đáp án rõ ràng.

## 11. Sự khác biệt giữa `ExceptionTranslationFilter` và `BearerTokenAuthenticationFilter`

Hai điểm giao nhau thường xuất hiện:

### 11.1. ExceptionTranslationFilter xử lý nhu cầu bắt đầu authentication

Khi authorization gặp request chưa được xác thực mà cần đăng nhập/token, `ExceptionTranslationFilter` có thể chuyển tình huống đó tới `AuthenticationEntryPoint` để trả challenge.

Ví dụ:

```text
GET /api/orders
Authorization: (không có)

authorizeHttpRequests:
  /api/orders cần SCOPE_orders.read

→ chưa có Authentication hợp lệ
→ gọi AuthenticationEntryPoint
→ 401 + WWW-Authenticate: Bearer
```

### 11.2. BearerTokenAuthenticationFilter xử lý token đã được gửi nhưng thất bại

Ví dụ:

```text
GET /api/orders
Authorization: Bearer expired-token

BearerTokenAuthenticationFilter:
  resolve token
  authenticate bằng JwtDecoder / introspector
  AuthenticationException
  failure handler gọi entry point tương ứng
→ Bearer challenge với error phù hợp
```

Điều này quan trọng khi custom error handling: một `@ControllerAdvice` thường **không đủ** để bắt mọi Spring Security exceptions xảy ra ở filter chain trước controller.

### 11.3. Không mặc định tất cả lỗi đều là AuthenticationException

Sau khi token hợp lệ, `AccessDeniedException` thuộc nhánh thiếu quyền. Nếu business service tự phát sinh lỗi nghiệp vụ, việc đó còn có thể thuộc MVC/controller exception handling. Cần hiểu lớp lỗi để trả status đúng.

## 12. Phân biệt `BearerTokenAuthenticationEntryPoint` và `BearerTokenAccessDeniedHandler`

Hai lớp thường được nhắc cùng nhau, nhưng chức năng khác.

| Thuộc tính | BearerTokenAuthenticationEntryPoint | BearerTokenAccessDeniedHandler |
|---|---|---|
| Nhóm exception | `AuthenticationException` | `AccessDeniedException` |
| Trạng thái nhận diện | Caller chưa được xác thực hợp lệ | Caller được xác thực nhưng không đủ quyền |
| HTTP thường gặp | `401`, đôi khi `400` tùy BearerTokenError | `403` |
| Header | `WWW-Authenticate: Bearer...` | Có thể Bearer challenge và `insufficient_scope` |
| Có `setRealmName`? | Có | Có |
| Kiểm tra JWT signature? | Không | Không |
| Cấp quyền vào Authentication? | Không | Không |
| Nên đặt policy object-level tại đây? | Không | Không |

### 12.1. Tình huống thiếu scope

Token hợp lệ:

```json
{
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
```

Route:

```java
.requestMatchers(HttpMethod.GET, "/api/orders/admin/export")
    .hasAuthority("SCOPE_orders.export")
```

Kết quả thường là `403 Forbidden`, không phải `401 invalid_token`. Token vẫn có thể dùng tại endpoint đọc bình thường, nên không nên hướng client refresh token vô hạn để cố có scope export.

### 12.2. Tình huống thiếu quyền trên bản ghi

Token có `orders.read`, endpoint GET cho qua, nhưng request nhắm vào order thuộc user khác. Business authorization có thể trả `403` hoặc cố ý `404` để không lộ sự tồn tại của bản ghi.

Đây là **object-level authorization**, không phải lỗi authentication. Đừng ném `BadJwtException` hoặc gắn `invalid_token` chỉ vì không có quyền với một order.

## 13. Khi nào dùng `401`, `403`, `400`?

Tóm theo hành vi API:

| Request | Token status | Authorization | HTTP nên kỳ vọng |
|---|---|---|---|
| Không có Bearer header vào protected API | Chưa xác thực | Không thể cấp quyền | `401` + Bearer challenge |
| Bearer header sai cấu trúc | Không có token hợp lệ để xác thực | Chưa xét quyền | Có thể `400 invalid_request` |
| JWT sai chữ ký | Không hợp lệ | Chưa xét quyền | Thường `401 invalid_token` |
| JWT hết hạn | Không hợp lệ | Chưa xét quyền | Thường `401 invalid_token` |
| JWT sai issuer/audience | Không phù hợp API | Chưa xét quyền | Thường `401 invalid_token` |
| Opaque introspection trả inactive | Không hợp lệ | Chưa xét quyền | Thường `401 invalid_token` |
| Token hợp lệ, thiếu `SCOPE_orders.read` | Đã xác thực | HTTP authorization từ chối | Thường `403` |
| Token hợp lệ, có scope, nhưng không owner | Đã xác thực | Object policy từ chối | `403`/`404` |
| Token hợp lệ, có quyền, domain state không cho xử lý | Đã xác thực | State constraint | Có thể `409` |
| Token hợp lệ, đủ quyền | Đã xác thực | Cho phép | HTTP success theo nghiệp vụ |

Không phải mọi lỗi hạ tầng trong decoder/introspection sẽ được ánh xạ giống lỗi token. Nếu JWKS hoặc introspection không truy cập được, server có thể trả lỗi 5xx tùy exception flow; **nhưng không được chấp nhận token chỉ vì hạ tầng lỗi**.

## 14. `BearerTokenResolver` ảnh hưởng tới lỗi nào?

Trước khi gọi decoder/introspector, Resource Server phải lấy token từ request. Spring Security thường dùng `DefaultBearerTokenResolver` để giải quyết bearer token từ `Authorization` header.

Ví dụ chuẩn:

```http
Authorization: Bearer <ACCESS_TOKEN>
```

Có một số cấu hình cho phép token từ form-encoded body hoặc query parameter; tuy nhiên truyền token qua URL **có rủi ro** bị ghi lại trong browser history, server logs, referrer, proxy và analytics. Với REST APIs hiện đại, **ưu tiên Authorization header**.

### 14.1. Header lỗi không đồng nghĩa token hết hạn

Ví dụ:

```http
Authorization: Bearer
```

Header không có token value có thể dẫn đến lỗi request hoặc resolver không lấy được token, tùy cách parser/filter hoạt động. Khi điều tra, phân biệt:

- Token thực sự sai/expired.
- Authorization header không đúng syntax.
- Client không gửi header do proxy/CORS/HTTP client lỗi.
- Gửi credential bằng vị trí không được resolver hỗ trợ.
- Gửi nhiều token/multiple transport methods trái contract.

Nếu request bị đánh giá là malformed, nhánh `invalid_request` có thể hợp lý hơn `invalid_token`.

### 14.2. Không log Authorization header

`Authorization: Bearer ...` chứa credential có thể dùng lại. Log nguyên header gây nguy cơ lộ quyền truy cập.

Thay vào đó, có thể log:

```text
request_id=req-123
http_path=/api/orders/{id}
authn_result=FAILED
reason=INVALID_BEARER_REQUEST
bearer_present=true
```

Không log token raw, query token hay payload nhạy cảm.

## 15. Kiểm tra issuer/audience trước khi coi token hợp lệ

Một JWT:

```json
{
  "iss": "https://login.example.test/realms/shop",
  "aud": ["payments-api"],
  "scope": "orders.read"
}
```

có thể được AS tin cậy ký, nhưng **không dành cho Orders API**. Nếu Orders API đòi audience `orders-api`, decoder/validator phải từ chối token trước HTTP authorization, dẫn đến Bearer authentication failure.

Đừng cấu hình entry point trả 403 để che việc decoder không kiểm tra audience. HTTP error formatting không thể sửa ranh giới tin cậy.

Với opaque token, introspection có thể trả `active=true`; Resource Server vẫn có thể cần kiểm tra audience/client/tenant theo hợp đồng qua `OpaqueTokenIntrospector` wrapper. Nếu fail, lỗi vẫn thuộc authentication/token contract.

### 15.1. OIDC ID token không phải access token của API

Một OIDC ID token có chữ ký hợp lệ thường dành cho **OIDC client** và có audience là client ID, không phải Resource Server. API không nên nhận ID token làm bearer access token chỉ vì cùng issuer. Kiểm tra token type/profile và expected audience ở decoder hoặc introspection contract.

Khi ID token bị gửi nhầm và không thỏa hợp đồng Resource Server, phản hồi thường là authentication failure, không phải cấp quyền vì `sub` giống user hợp lệ.

## 16. Request có token cũ: client có nên refresh ngay?

Một client có thể nhận:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Trường hợp này **có thể** do token hết hạn, và OAuth client có thể cần thực hiện token refresh flow phù hợp nếu nó sở hữu refresh token và AS hỗ trợ. Nhưng `invalid_token` cũng có thể do:

- Chữ ký sai.
- Issuer/audience không phù hợp.
- Token đã bị thu hồi.
- Token không dành cho Resource Server.
- Token malformed.
- Clock skew hoặc key rotation xảy ra sự cố.
- AS/Resource Server thay đổi hợp đồng validation.

Vì vậy:

- Không tự refresh token **vô hạn** mỗi khi thấy 401.
- Không gửi lại cùng một token vô hạn.
- Không suy luận `403 insufficient_scope` sẽ được sửa bằng refresh nếu không có flow cấp scope bổ sung.
- OAuth client nên xác định chính sách retry/refresh an toàn; Resource Server chỉ trả trạng thái đúng.
- Không đưa refresh token cho Resource Server trừ khi một protocol cụ thể và kiến trúc được thiết kế cho phép; thông thường refresh token thuộc về client/AS token endpoint.

### 16.1. Tránh biến challenge thành redirect login

Đối với máy–máy và SPA/mobile API clients, một `302 /login` chứa HTML thường không hữu ích khi resource được bảo vệ bằng Bearer token. Nếu ứng dụng kết hợp form login và Resource Server, nên có SecurityFilterChain đúng cho API để entry point trả HTTP Bearer challenge.

## 17. CORS, frontend và khả năng đọc `WWW-Authenticate`

Một web frontend chạy khác origin có thể gọi Orders API bằng Fetch:

```javascript
const response = await fetch("https://api.example.test/api/orders/42", {
  headers: {
    Authorization: "Bearer " + accessToken
  }
});

if (response.status === 401) {
  // Theo hợp đồng OAuth client: xử lý login/token refresh phù hợp.
}
```

Khi request cross-origin, CORS policy ảnh hưởng tới việc frontend đọc response:

- Resource Server cần cho phép origin/method/headers thích hợp.
- Browser có thể gửi **preflight OPTIONS** vì Authorization header.
- Nếu frontend cần đọc `WWW-Authenticate` bằng JavaScript, CORS response có thể cần `Access-Control-Expose-Headers: WWW-Authenticate`.
- Dù browser được phép đọc challenge, điều đó **không thay thế authentication/authorization** của API.

### 17.1. CORS preflight không phải Bearer authentication

Preflight thường không mang bearer token:

```http
OPTIONS /api/orders/42
Origin: https://app.example.test
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
```

Nếu bảo vệ preflight giống một request nghiệp vụ cần token, browser có thể không gửi được request thật. Cấu hình Spring Security CORS thường cần xử lý preflight trước khi yêu cầu Bearer auth.

Một CORS policy cần giới hạn origin, methods và headers theo contract; không đơn giản đặt `OPTIONS /** permitAll` cho mọi thứ mà không hiểu API.

### 17.2. Expose header có căn cứ

Minh họa một phần CORS config:

```java
CorsConfiguration cors = new CorsConfiguration();
cors.setAllowedOrigins(List.of("https://app.example.test"));
cors.setAllowedMethods(List.of("GET", "POST", "OPTIONS"));
cors.setAllowedHeaders(List.of("Authorization", "Content-Type"));
cors.setExposedHeaders(List.of("WWW-Authenticate"));
```

Import:

```java
import java.util.List;
import org.springframework.web.cors.CorsConfiguration;
```

Việc cấu hình `CorsConfigurationSource` và tích hợp `http.cors(...)` sẽ tùy cấu trúc ứng dụng. Chỉ expose header cho origin được phép; không coi CORS là cơ chế phân quyền user.

## 18. Khi có nhiều SecurityFilterChain

Một ứng dụng có thể có API với Bearer và web UI dùng form login:

```text
/api/**        -> JWT Resource Server, Bearer challenge
/web/**        -> Session/Form login
/public/**     -> Public routes
```

Nếu một chain catch-all với form login đứng trước chain API, request `/api/orders` có thể bị route sang HTML login thay vì trả Bearer challenge.

### 18.1. Phân biệt `securityMatcher` với `requestMatchers`

- `http.securityMatcher("/api/**")`: chọn request nào đi vào **cả filter chain**.
- `authorizeHttpRequests(...).requestMatchers(...)`: chọn authorization rule **trong chain đó**.

Ví dụ:

```java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults()))
        .build();
}
```

Import bổ sung:

```java
import org.springframework.core.annotation.Order;
```

Cần một chain khác bảo vệ phần còn lại khi phù hợp. Nếu request không match chain nào, Spring Security có thể không bảo vệ request đó. `anyRequest().denyAll()` ở chain chỉ match `/api/**` **không bảo vệ toàn bộ ứng dụng**.

### 18.2. Tránh dùng entry point web cho API

Nếu một API request thiếu bearer token nhận 302/HTML, hãy xem:

1. Request đi vào chain nào?
2. `@Order` giữa các chains có đúng không?
3. `securityMatcher` có match đúng servlet path không?
4. Có form login, HTTP Basic hoặc exception handler global override Bearer entry point không?
5. Reverse proxy có strip/chuyển đổi Authorization header không?

Không sửa bằng cách thêm một controller tùy biến trả 401 nếu filter chain đang được chọn sai.

## 19. Gateway, proxy và header propagation

Một Resource Server có thể đứng sau API gateway:

```text
OAuth client
    |
    v
API Gateway / reverse proxy
    |
    v
Spring Security Resource Server
```

Các vấn đề thường gặp:

- Gateway **xóa Authorization header** trước khi chuyển tới API.
- Gateway tự xác thực rồi gửi identity headers nhưng backend vẫn mong Bearer token.
- Gateway tự trả `401` không có `WWW-Authenticate`.
- Gateway rewrite body/status và làm mất Bearer challenge.
- Gateway cache nhầm 401/403 response.
- WAF chặn token hoặc coi header là payload bất thường.

Khi điều tra cần xác định **phản hồi nào do gateway tạo, phản hồi nào do Spring Security tạo**. Đừng chỉ nhìn status tại client rồi kết luận `BearerTokenAuthenticationEntryPoint` không hoạt động.

### 19.1. Không tin identity header không có trust boundary

Nếu gateway xác thực token và đưa `X-User-Id` vào backend, cần một cơ chế tin cậy giữa gateway và backend (mạng, mTLS, header sanitation và policy phù hợp). Không mặc nhiên lấy `X-User-Id` do Internet client gửi để bỏ qua Bearer authentication.

### 19.2. Không lộ bearer trong access logs

Tránh ghi `Authorization` ở gateway hoặc backend, và tránh truyền token trên query string. Error headers/JSON body không được phản chiếu token.

## 20. `WWW-Authenticate` và API error body là hai contract khác nhau

Giả sử tổ chức có JSON response:

```json
{
  "code": "AUTH_REQUIRED",
  "message": "Authentication is required",
  "requestId": "req-123"
}
```

Response có thể là:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer realm="orders-api"
Content-Type: application/json
```

Một client tuân HTTP Bearer authentication có thể dùng header; frontend có thể dùng JSON body. Cả hai cần được thiết kế **nhất quán về status**.

### 20.1. Tại sao không trả 200 với field error?

Sai:

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"error":"invalid_token"}
```

HTTP status 200 cho biết request thành công ở mức HTTP, dễ làm client, cache, monitoring hoặc retry logic hiểu sai. Authentication failure cần HTTP status phù hợp, không chỉ một field trong JSON.

### 20.2. Tại sao không trả 403 cho mọi request thiếu token?

`403 Forbidden` thường diễn đạt server từ chối thực hiện request dù caller đã được xác thực và thiếu quyền. Nếu **chưa có Authentication** tại protected API, challenge `401` là thông điệp đúng hơn để client biết cần trình bày credential.

### 20.3. Khi nào cần RFC 9457 Problem Details?

Nếu tổ chức chuẩn hóa lỗi API theo Problem Details, có thể dùng media type `application/problem+json` và các fields `type`, `title`, `status`. Nhưng body này vẫn **không thay thế `WWW-Authenticate`** trong Bearer authentication.

Bất kỳ custom entry point nào cũng nên giữ status/header trước, sau đó thêm thông tin JSON an toàn nếu có nhu cầu.

## 21. Logging, monitoring và không lộ thông tin

Một hệ thống Resource Server nên quan sát:

| Signal | Ý nghĩa |
|---|---|
| Tỷ lệ HTTP 401 theo route | Phát hiện caller thiếu/sai credentials |
| Tỷ lệ `invalid_request` | Dấu hiệu client gửi Bearer header sai hoặc transport lỗi |
| Tỷ lệ `invalid_token` | Có thể do token hết hạn, sai issuer/audience hoặc chữ ký |
| Tỷ lệ 403 | Token xác thực được nhưng thiếu quyền |
| Lỗi JWKS/introspection HTTP | Có thể là sự cố hạ tầng AS hoặc network |
| Thời gian xác thực JWT/introspection | Chỉ số latency/availability |
| Request ID và phiên bản API | Hỗ trợ liên kết trace mà không lộ bearer token |

Ví dụ log an toàn:

```text
request_id=req-74aa
route=GET /api/orders/{id}
authentication_result=FAILED
error_category=INVALID_TOKEN
bearer_present=true
http_status=401
```

Không ghi:

```text
Authorization: Bearer <RAW_ACCESS_TOKEN>
client_secret=<INTROSPECTION_SECRET>
jwt_payload=<SENSITIVE_CLAIMS>
```

Các thông tin trên có thể chứa credential hoặc dữ liệu cá nhân. Nếu cần debug issuer/audience, lấy thông tin từ decoder/log nội bộ có kiểm soát, không in token thô ra error response.

### 21.1. Tránh error_description quá chi tiết

Không đưa cho client những chi tiết như:

- Tên file private key hoặc key material.
- Danh sách đường dẫn hạ tầng nội bộ.
- Client secret hoặc credentials của introspection.
- Toàn bộ expected claims nhạy cảm của tenant.
- Raw exception/stack trace.
- Thông tin xác nhận một user/đối tượng không được phép có tồn tại.

Client thường chỉ cần biết token không được chấp nhận hoặc không đủ quyền. Chi tiết chẩn đoán có thể lưu trong logs bảo mật theo request ID.

## 22. MockMvc: kiểm tra Bearer challenge khi thiếu token

Có thể kiểm tra behavior HTTP bằng Spring Boot Test và Spring Security Test.

Ví dụ cấu hình ứng dụng bảo vệ `GET /api/orders/**`. Khi không gửi token:

```java
@SpringBootTest
@AutoConfigureMockMvc
class BearerChallengeTests {

    @Autowired
    MockMvc mockMvc;

    @Test
    void missingTokenReturnsBearerChallenge() throws Exception {
        mockMvc.perform(get("/api/orders/42"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                startsWith("Bearer")
            ));
    }
}
```

Imports:

```java
import static org.hamcrest.Matchers.startsWith;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.test.web.servlet.MockMvc;
```

Test này xác nhận việc thiếu Authentication trong route protected dẫn đến `401` và challenge phù hợp **nếu cấu hình Resource Server/SecurityFilterChain đã được load đúng**.

Nếu application có nhiều filter chains, thử đúng request/servlet path và đảm bảo chain Bearer đang được chọn.

### 22.1. Cần những test cases nào?

| Test case | HTTP kỳ vọng | Header |
|---|---|---|
| Không token, protected endpoint | `401` | Bearer challenge |
| Không token, public endpoint | Theo API public, thường `200` | Không cần Bearer challenge |
| Token hết hạn | Thường `401` | Có thể `error="invalid_token"` |
| JWT sai issuer/audience | Thường `401` | Bearer challenge phù hợp |
| Request Bearer malformed | Có thể `400` | Có thể `error="invalid_request"` |
| Token hợp lệ, thiếu scope | `403` | AccessDeniedHandler/Bearer semantics |
| Token hợp lệ, có scope, sai owner | `403` hoặc `404` | Theo business policy |
| Access token hợp lệ, đủ quyền | Status nghiệp vụ | Không cần authentication challenge |

Chỉ test thiếu token chưa đủ để chứng minh JWT signature/issuer/audience validation. Với những kịch bản đó cần cấu hình decoder/introspector phù hợp và token test thật hoặc mock có chủ đích.

### 22.2. Vì sao `jwt()` trong Spring Security Test chưa đủ?

Spring Security Test có thể giả lập Authentication:

```java
mockMvc.perform(get("/api/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )))
    .andExpect(status().isOk());
```

Đoạn này minh họa test authorization, nhưng `jwt()` **thường không đi qua chữ ký JWT thật**. Nếu muốn kiểm tra `BearerTokenAuthenticationEntryPoint` khi token sai chữ ký/expired, cần test request qua decoder thích hợp hoặc stub decoder ném exception như thiết kế.

Ngoài ra §status().isOk()§ chỉ hợp lệ nếu controller/service/test fixtures thực sự trả HTTP 200 sau authorization.

## 23. Test entry point trực tiếp: header và status

Có thể unit test entry point mà không chạy toàn Servlet filter chain.

Ví dụ với Spring mock servlet request/response:

```java
@Test
void entryPointSetsBearerRealmForMissingAuthentication()
        throws Exception {

    BearerTokenAuthenticationEntryPoint entryPoint =
        new BearerTokenAuthenticationEntryPoint();

    entryPoint.setRealmName("orders-api");

    MockHttpServletRequest request = new MockHttpServletRequest();
    MockHttpServletResponse response = new MockHttpServletResponse();

    AuthenticationException exception =
        new InsufficientAuthenticationException(
            "Authentication is required"
        );

    entryPoint.commence(request, response, exception);

    assertEquals(401, response.getStatus());
    assertEquals(
        "Bearer realm=\"orders-api\"",
        response.getHeader(HttpHeaders.WWW_AUTHENTICATE)
    );
}
```

Imports:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.security.authentication.InsufficientAuthenticationException;
import org.springframework.security.core.AuthenticationException;
import org.springframework.security.oauth2.server.resource.web.BearerTokenAuthenticationEntryPoint;
```

Đây là test response formatting của entry point. Nó **không chứng minh** API route đã match đúng filter chain, decoder xác thực token đúng hoặc RBAC/ABAC được triển khai đầy đủ.

### 23.1. Một test cho invalid_token

Có thể tạo exception chứa `BearerTokenError`:

```java
@Test
void invalidTokenProducesBearerError() throws Exception {
    BearerTokenAuthenticationEntryPoint entryPoint =
        new BearerTokenAuthenticationEntryPoint();

    MockHttpServletResponse response = new MockHttpServletResponse();

    OAuth2AuthenticationException exception =
        new OAuth2AuthenticationException(
            BearerTokenErrors.invalidToken("Invalid access token")
        );

    entryPoint.commence(
        new MockHttpServletRequest(),
        response,
        exception
    );

    assertEquals(401, response.getStatus());
    assertTrue(
        response.getHeader(HttpHeaders.WWW_AUTHENTICATE)
            .contains("error=\"invalid_token\"")
    );
}
```

Imports bổ sung:

```java
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.BearerTokenErrors;
```

Không test bằng cách so nguyên mọi ký tự của header nếu framework có thể thay đổi thứ tự các tham số không quan trọng theo phiên bản; ưu tiên kiểm tra status và sự xuất hiện của scheme/error code cần thiết.

## 24. Kiểm tra nhanh bằng curl

### 24.1. Không gửi token

```bash
curl -i "https://api.example.test/api/orders/42"
```

Kỳ vọng API protected:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

Có thể kèm `realm` nếu đã cấu hình.

### 24.2. Gửi token sai

```bash
curl -i \
  -H "Authorization: Bearer invalid-token" \
  "https://api.example.test/api/orders/42"
```

Thông thường:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Tùy decoder, resolver và exception flow, error description/header có thể khác. Không dùng bearer token production trong terminal history hoặc log.

### 24.3. Có token hợp lệ nhưng thiếu quyền

```bash
curl -i \
  -H "Authorization: Bearer <VALID_TOKEN_WITHOUT_orders.read>" \
  "https://api.example.test/api/orders/42"
```

Thông thường `403 Forbidden`. Dù nhận `403`, cũng cần xem token có thực sự được decoder xác thực và route policy có áp đúng rule không.

### 24.4. Phân biệt lỗi gateway với lỗi Spring Security

Nếu curl tới gateway nhận 401 nhưng curl nội bộ trong môi trường test tới Resource Server không nhận, cần xem gateway có rewrite/delete `WWW-Authenticate`, drop Authorization header hoặc trả challenge riêng không. Không đổ lỗi cho `BearerTokenAuthenticationEntryPoint` chỉ dựa vào một response bên ngoài.

## 25. Những lỗi thiết kế thường gặp

### Lỗi 1 — Cho mọi failure trả 200 với JSON

```http
HTTP/1.1 200 OK
{"error":"invalid_token"}
```

Làm client/cache/monitoring hiểu sai. Dùng HTTP status phù hợp.

### Lỗi 2 — Trả 401 nhưng quên `WWW-Authenticate`

Client Bearer không nhận được challenge. Dùng `BearerTokenAuthenticationEntryPoint` hoặc delegate tới nó khi thêm JSON body.

### Lỗi 3 — Trả `invalid_token` khi chưa có token

Nếu caller không gửi credential, `WWW-Authenticate: Bearer` thường là challenge phù hợp; không cần khẳng định token sai.

### Lỗi 4 — Biến thiếu scope thành token không hợp lệ

Token có `orders.read` nhưng thiếu `orders.export` có thể dùng các endpoints đọc khác. Trả `403` theo authorization thay vì gán `401 invalid_token`.

### Lỗi 5 — Bỏ validation audience để giảm 401

Một token của Payments API không được biến thành token hợp lệ của Orders API. Lỗi 401 do wrong audience phải giải quyết ở token request/AS config/Resource Server contract, không ở error handler.

### Lỗi 6 — Dùng `@ControllerAdvice` để bắt mọi security error

Nhiều security failures xảy ra ở filter chain trước MVC, nên controller advice không nhất thiết nhận được. Cấu hình `AuthenticationEntryPoint` và `AccessDeniedHandler` đúng.

### Lỗi 7 — Custom entry point làm mất status `invalid_request`

Nếu delegate xác định `400` nhưng custom code luôn `response.setStatus(401)`, API mất phân biệt malformed request với invalid token. Giữ status của delegate hoặc map có chủ đích theo contract.

### Lỗi 8 — Log Bearer header để “debug nhanh”

Access token là credential. Tránh đưa vào stdout, APM, exception message, HTTP access logs hoặc ticket.

### Lỗi 9 — Để HTML redirect từ form login thay Bearer challenge

Có thể do chain web đứng trước API chain. Tách security matchers và priorities.

### Lỗi 10 — Nhầm realm với issuer

`realm="orders-api"` không thể thay kiểm tra `iss`, `aud`, chữ ký hoặc introspection.

### Lỗi 11 — CORS preflight bị buộc Bearer authentication

Browser có thể không gửi được request thật. Cấu hình CORS xử lý preflight phù hợp.

### Lỗi 12 — Client refresh vô hạn sau 401

Không phải mọi `invalid_token` đều là expiration. Giới hạn retry/refresh và phân loại lỗi.

### Lỗi 13 — Tự phản chiếu exception details cho client

Đừng lộ expected private claims, key IDs nhạy cảm, network endpoints nội bộ, subject/tenant của object hoặc stack traces.

### Lỗi 14 — Cho phép token chỉ vì JWKS/introspection không sẵn sàng

Lỗi hạ tầng không chứng minh token hợp lệ. Phải fail closed; response vận hành có thể được xử lý riêng nhưng không tạo Authentication giả.

## 26. Mô hình quyết định thực tế cho Orders API

Giả sử Orders API phục vụ cả frontend và service integration.

Policy:

```text
Authentication contract:
  - Bearer access token required for /api/**
  - JWT signature or opaque introspection must pass
  - issuer must be trusted
  - audience must contain orders-api
  - token must be active/not expired

HTTP authorization:
  GET /api/orders/**  -> SCOPE_orders.read
  POST /api/orders    -> SCOPE_orders.write
  POST /api/orders/*/cancel -> SCOPE_orders.cancel

Object authorization:
  - Only orders visible by subject/tenant/ACL
  - Bulk list and export filtered to allowed resources

Error contract:
  - No token: 401 + WWW-Authenticate: Bearer realm="orders-api"
  - Invalid token: 401 + Bearer error="invalid_token"
  - Malformed Bearer request: use RFC 6750 error semantics
  - Valid token, missing authority: 403
  - Object not visible: 403 or 404 consistently
```

Cấu trúc này giúp phân biệt **authentication challenge**, **action permission** và **business object permission**. Việc thay đổi response format không làm thay đổi policy.

## 27. Tài liệu tham khảo

- [Spring Security — BearerTokenAuthenticationEntryPoint API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/BearerTokenAuthenticationEntryPoint.html): method `commence(...)`, Bearer challenge và realm.
- [Spring Security — BearerTokenAccessDeniedHandler API](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/access/BearerTokenAccessDeniedHandler.html): xử lý AccessDeniedException trong Bearer Resource Server.
- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): cấu hình JWT, Bearer authentication và ánh xạ scopes thành authorities.
- [Spring Security — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection và authentication cho opaque tokens.
- [Spring Security — Exception Handling](https://docs.spring.io/spring-security/reference/servlet/architecture.html): vị trí của Spring Security filters và xử lý exception.
- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer scheme, `WWW-Authenticate` và các error codes.
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110): mã trạng thái 401/403 và HTTP authentication challenge.
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457): phản hồi lỗi machine-readable khi API cần JSON error contract.

**Kết luận:** `BearerTokenAuthenticationEntryPoint` là thành phần quan trọng để Resource Server gửi **Bearer challenge khi request chưa có Authentication hợp lệ**, thông thường thông qua `401 Unauthorized` và `WWW-Authenticate: Bearer`. Khi exception mang `BearerTokenError`, nó có thể truyền các tham số Bearer error phù hợp như `invalid_token` hoặc `invalid_request`. **Thiếu quyền của token hợp lệ** thuộc nhánh authorization, thường do `BearerTokenAccessDeniedHandler` xử lý với `403`. Một API tốt giữ đúng HTTP status, header challenge, không lộ credentials và tách rõ authentication, scope authorization cùng quyền đối tượng nghiệp vụ.
