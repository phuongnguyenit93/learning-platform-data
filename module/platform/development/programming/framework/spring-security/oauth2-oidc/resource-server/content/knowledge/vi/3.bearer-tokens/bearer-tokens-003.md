# BearerTokenResolver và DefaultBearerTokenResolver trong Servlet

Trong ứng dụng **Spring Security OAuth 2.0 Resource Server** sử dụng **Servlet stack** (Spring MVC, `HttpServletRequest`), một client thường gửi access token bằng HTTP header:

```http
GET /api/orders HTTP/1.1
Host: orders.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

Để Resource Server xác thực token, trước hết Spring Security phải **tìm đúng chuỗi token trong HTTP request**. Nhiệm vụ đó thuộc về `BearerTokenResolver`. Lớp `DefaultBearerTokenResolver` là cách triển khai sẵn thường được sử dụng, hỗ trợ cách truyền chuẩn qua header `Authorization` và có thể bật thêm một số cách truyền theo RFC 6750.

Điểm cần nắm từ đầu: **resolver chỉ trích xuất bearer token**. Nó không kiểm tra chữ ký JWT, không gọi token introspection, không kiểm tra audience/scope và không quyết định quyền đọc hoặc sửa tài nguyên. Các công việc đó diễn ra ở những thành phần phía sau trong chuỗi xử lý bảo mật.

## 1. Bearer token nằm ở bước nào của quá trình xác thực?

Trong OAuth 2.0, *bearer token* là credential mà bên nắm giữ có thể trình ra để truy cập Resource Server, tùy điều kiện hiệu lực và chính sách phân quyền. Spring Security tiếp nhận credential đó qua bộ lọc của Servlet:

```mermaid
flowchart TD
    A["HTTP request\nAuthorization: Bearer ..."] --> B["Spring Security FilterChainProxy"]
    B --> C["BearerTokenAuthenticationFilter"]
    C --> D["BearerTokenResolver.resolve(request)"]
    D --> E{"Có token?"}
    E -->|"Không / null"| F["Tiếp tục filter chain\nEndpoint bảo vệ có thể từ chối"]
    E -->|"Có / String"| G["BearerTokenAuthenticationToken"]
    E -->|"Lỗi / exception"| H["AuthenticationEntryPoint\nPhản hồi lỗi phù hợp"]
    G --> I["AuthenticationManager"]
    I --> J["JWT decoder hoặc opaque-token introspector"]
    J --> K{"Xác thực thành công?"}
    K -->|"Có"| L["SecurityContext / Authentication\nKiểm tra authorization"]
    K -->|"Không"| H
```

`BearerTokenAuthenticationFilter` gọi resolver để lấy chuỗi bearer token. Khi tìm thấy token, filter tạo một `BearerTokenAuthenticationToken` rồi chuyển tới cơ chế xác thực đã cấu hình:

- **JWT Resource Server:** thông thường sử dụng `JwtDecoder` để xác minh JWT theo thuật toán/khóa, thời hạn và các validator được cấu hình.
- **Opaque token Resource Server:** thông thường sử dụng `OpaqueTokenIntrospector` để hỏi Authorization Server hoặc bộ xử lý introspection phù hợp.

Sau khi xác thực thành công, Spring Security đặt `Authentication` phù hợp vào ngữ cảnh bảo mật để các quy tắc `authorizeHttpRequests`, `@PreAuthorize` và nghiệp vụ ứng dụng có thể sử dụng.

Thay resolver có nghĩa là **thay nguồn đọc credential trong request**; nó **không** biến JWT thành opaque token, không thay IdP và không tự cấp quyền cho người gọi.

## 2. Interface BearerTokenResolver

Trong Spring Security Servlet, interface nằm ở package:

```java
org.springframework.security.oauth2.server.resource.web.BearerTokenResolver
```

Hợp đồng cốt lõi có dạng:

```java
public interface BearerTokenResolver {
    String resolve(HttpServletRequest request);
}
```

Ở đây `HttpServletRequest` là `jakarta.servlet.http.HttpServletRequest` trong các ứng dụng dùng Spring Security 6/Spring Boot 3. Với các nhánh cũ hơn dùng Java EE, namespace Servlet có thể là `javax.servlet`; không trộn import giữa hai thế hệ.

Kết quả của `resolve`:

| Kết quả | Ý nghĩa trong hệ thống |
|---|---|
| Chuỗi token khác `null` | Resolver đã tìm được một bearer token cần gửi tới cơ chế xác thực |
| `null` | Không tìm thấy bearer token theo cách resolver hỗ trợ; filter tiếp tục chuỗi xử lý |
| `OAuth2AuthenticationException` | Request chứa biểu diễn bearer credential không hợp lệ hoặc xung đột theo quy tắc của resolver |

`null` **không đồng nghĩa yêu cầu được phép**. Chẳng hạn một URL public có thể tiếp tục xử lý không cần token, nhưng URL được bảo vệ sẽ bị từ chối khi chưa xác thực. Tương tự, trả về một chuỗi từ resolver **không đồng nghĩa token đã được kiểm chứng**.

### Interface nhỏ nhưng nằm trên đường đi nhạy cảm

Một bearer token là thông tin bí mật. Resolver cần tránh:

- Ghi nguyên token vào log, exception, URL hoặc thông tin quan sát hệ thống.
- Trả về token từ header do phía ngoài có thể giả mạo mà chưa có hợp đồng trust rõ ràng.
- Tự giải mã payload JWT để quyết định chấp nhận nguồn token; JWT chưa xác thực không đáng tin.
- Nuốt lỗi xung đột nguồn token hoặc chọn ngầm một token trong nhiều credential mà người gọi gửi.

Ứng dụng thường **không cần tự viết** `BearerTokenResolver` nếu client đã truyền `Authorization: Bearer` đúng chuẩn.

## 3. DefaultBearerTokenResolver: hành vi mặc định

`DefaultBearerTokenResolver` nằm trong cùng package với interface:

```java
org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver
```

Mặc định, resolver tìm access token tại header **`Authorization`**, với authentication scheme **`Bearer`**:

```http
Authorization: Bearer <access-token>
```

Ví dụ:

```http
GET /api/profile HTTP/1.1
Host: api.example.com
Authorization: Bearer abc.def-123_XYZ
```

Resolver lấy chuỗi `abc.def-123_XYZ` để đưa cho bộ xác thực. Chuỗi ví dụ này có thể là một bearer credential về mặt cú pháp nhưng chưa chắc là JWT hợp lệ; bước xác thực token diễn ra sau đó.

### 3.1. Các vị trí truyền token

RFC 6750 mô tả ba phương thức truyền bearer token phổ biến. `DefaultBearerTokenResolver` ưu tiên cách truyền qua header theo thiết lập mặc định:

| Cách truyền | Ví dụ | Trạng thái mặc định | Ghi chú |
|---|---|---|---|
| Header `Authorization` | `Authorization: Bearer <token>` | **Bật** | Cách nên dùng cho API |
| Form body kiểu `application/x-www-form-urlencoded` | `access_token=<token>` trong POST body | **Tắt** | Chỉ bật khi thực sự tương thích với client đặc thù |
| URI query | `GET /api?access_token=<token>` | **Tắt** | Dễ rò rỉ qua log, history, referrer, telemetry |

Trong trạng thái mặc định, resolver **không** lấy chuỗi token từ:

```http
GET /api/orders?access_token=some-token HTTP/1.1
```

hoặc:

```http
POST /api/orders HTTP/1.1
Content-Type: application/x-www-form-urlencoded

access_token=some-token
```

Do đó, nếu client chỉ truyền token qua query hoặc form body, Resource Server sẽ không tự tìm thấy bearer token khi giữ cấu hình mặc định.

### 3.2. Những tình huống ở header

| Header đầu vào | Ý nghĩa xử lý |
|---|---|
| `Authorization: Bearer abc123` | Trích xuất `abc123` |
| `authorization: bearer abc123` | Header và scheme không phân biệt hoa thường theo chuẩn; resolver chuẩn xử lý Bearer scheme |
| Không có `Authorization` | Không thấy bearer token → `null` |
| `Authorization: Basic Zm9vOmJhcg==` | Không phải Bearer → không trích xuất bearer token |
| `Authorization: Bearer` hoặc chuỗi Bearer sai cú pháp | Trường hợp Bearer malformed → lỗi xác thực thích hợp |
| `Authorization: Bearer abc def` | Không phải cách trình bày một bearer token hợp lệ → lỗi |

Header chính xác có thể bị normalize qua HTTP server/proxy; không cần tự phân tích dấu cách hoặc dùng `substring` trên raw header để thay thế resolver. Sử dụng resolver chuẩn giúp giữ đúng quy tắc định dạng Bearer và xử lý lỗi của Spring Security.

### 3.3. Không nhận đồng thời nhiều phương thức truyền bearer token

Khi bật truyền token bằng tham số, một request có thể mang token ở cả header và form/query:

```http
POST /api/checkout HTTP/1.1
Authorization: Bearer token-from-header
Content-Type: application/x-www-form-urlencoded

access_token=token-from-body
```

Theo nguyên tắc của RFC 6750, client **không được dùng nhiều phương thức truyền bearer token trong cùng một request**. `DefaultBearerTokenResolver` kiểm soát trường hợp xung đột giữa header và tham số token đã được cho phép; khi phát hiện nhiều token, resolver báo lỗi thay vì tùy tiện chọn một nguồn.

Việc “header thắng query” hay “lấy token đầu tiên” là một chính sách dễ tạo sai lệch giữa proxy, framework và ứng dụng. Vì thế, khi viết resolver riêng, cần nêu rõ và thường nên từ chối credential nhập nhằng.

## 4. Cấu hình mặc định trong Spring Security Servlet

Ví dụ ứng dụng Resource Server nhận JWT qua header chuẩn:

```yaml
# application.yml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
```

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ResourceServerSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/public/status").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Khi không thay resolver, Spring Security sử dụng cách giải quyết bearer token mặc định phù hợp với `DefaultBearerTokenResolver`.

Giả sử token JWT hợp lệ có scope `orders.read` và đủ điều kiện xác thực theo decoder, request sau có thể tới bước xử lý phân quyền:

```bash
curl --request GET 'https://orders.example.com/api/orders/123' \
  --header 'Authorization: Bearer ACCESS_TOKEN'
```

`ACCESS_TOKEN` ở đây chỉ là chỗ giữ chỗ, không phải token có thể dùng thật. Các validator JWT như issuer, thời hạn và audience phải được cấu hình theo bảo đảm cần thiết của API; **resolver không thay thế kiểm tra audience**.

Một lưu ý về Servlet: nếu ứng dụng dùng session/cookie cho thao tác thay đổi trạng thái, phải cấu hình CSRF phù hợp. Việc dùng Resource Server cho bearer API không có nghĩa mọi luồng HTTP của cùng ứng dụng đều nên tắt CSRF.

## 5. Đổi header mà resolver đọc

Một số hệ thống có proxy/gateway gửi bearer token bằng header khác, ví dụ `Proxy-Authorization`. `DefaultBearerTokenResolver` có API:

```java
setBearerTokenHeaderName(String headerName)
```

Ví dụ cấu hình đầy đủ trên Servlet stack:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ProxyBearerSecurityConfig {

    @Bean
    BearerTokenResolver bearerTokenResolver() {
        DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
        resolver.setBearerTokenHeaderName(HttpHeaders.PROXY_AUTHORIZATION);
        return resolver;
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            BearerTokenResolver bearerTokenResolver) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                .bearerTokenResolver(bearerTokenResolver)
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
```

Khi cấu hình trên, một request sử dụng:

```http
GET /api/orders/123 HTTP/1.1
Proxy-Authorization: Bearer some-token
```

Chức năng của `setBearerTokenHeaderName` là **thay tên header cần đọc**, vẫn sử dụng định dạng `Bearer <token>`. Nó không tự thêm fallback sang header `Authorization`, không tự xác minh rằng proxy được tin cậy và không sửa điều kiện xác thực của `JwtDecoder`.

Để tránh sự nhập nhằng, không nên bật nhận từ nhiều header chỉ vì muốn “dễ tương thích”. Nếu kiến trúc bắt buộc hỗ trợ nhiều nguồn, cần một hợp đồng rõ ràng về nguồn nào được tin, xử lý xung đột ra sao và đường nào có thể gửi header đó.

### 5.1. Đổi header có làm tăng quyền hay giảm an toàn?

Bản thân tên header không làm token hợp lệ hơn hoặc kém đi. Rủi ro xuất hiện từ **ranh giới tin cậy**:

- Nếu `Proxy-Authorization` do proxy tin cậy tạo ra, proxy phải xóa/ghi đè bản do client gửi và đường từ proxy đến API phải được bảo vệ.
- Nếu client bên ngoài có thể tự gửi header rồi API tưởng đó là thông tin đáng tin từ proxy, header trở thành điểm giả mạo.
- Khi đổi tên header, phải đồng bộ cấu hình client/gateway, CORS nếu request từ browser, luật lọc log và quan sát hạ tầng.
- Nếu gateway thực hiện xác thực và chuyển kết quả thành danh tính (thay vì chuyển bearer token), đó là **một hợp đồng tin cậy khác**, không giải quyết bằng cách chỉ đổi header trong resolver.

## 6. Bật token từ form body

`DefaultBearerTokenResolver` cung cấp:

```java
setAllowFormEncodedBodyParameter(boolean allowFormEncodedBodyParameter)
```

Thiết lập mặc định là `false`. Nếu thực sự phải hỗ trợ một client gửi token ở body dạng `application/x-www-form-urlencoded`, có thể bật:

```java
@Bean
BearerTokenResolver bearerTokenResolver() {
    DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
    resolver.setAllowFormEncodedBodyParameter(true);
    return resolver;
}
```

Ví dụ kiểu request phù hợp:

```http
POST /api/legacy HTTP/1.1
Host: api.example.com
Content-Type: application/x-www-form-urlencoded

access_token=example-token
```

RFC 6750 chỉ cho phép cách truyền form body trong các điều kiện cụ thể, bao gồm request có body phù hợp để truyền form và sử dụng `application/x-www-form-urlencoded`; trong Spring Security, cách bật này hướng đến request POST form-encoded theo quy tắc resolver. Không áp dụng nó như cơ chế lấy token từ JSON body:

```http
POST /api/orders HTTP/1.1
Content-Type: application/json

{"access_token":"example-token"}
```

`DefaultBearerTokenResolver` không được thiết kế để parse JSON tùy ý thành access token. Cố tình đọc token từ DTO nghiệp vụ làm lẫn lớp xác thực với lớp xử lý ứng dụng, khiến token dễ rò rỉ qua log body, validation error hoặc hệ thống tracing.

**Khi nào cân nhắc bật form body?** Chỉ khi đang tích hợp client cũ theo RFC 6750 và thật sự không thể chuyển sang `Authorization` header. Khi đó phải cân nhắc logging, gateway, content type, kích thước body và việc không được gửi token đồng thời trong nhiều vị trí. Với API mới, ưu tiên header chuẩn.

## 7. Bật token từ URI query

Resolver cũng cung cấp:

```java
setAllowUriQueryParameter(boolean allowUriQueryParameter)
```

Mặc định là `false`. Nếu bật:

```java
@Bean
BearerTokenResolver bearerTokenResolver() {
    DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
    resolver.setAllowUriQueryParameter(true);
    return resolver;
}
```

Khi đó resolver có thể đọc:

```http
GET /api/orders?access_token=example-token HTTP/1.1
Host: api.example.com
```

Đây là khả năng phục vụ trường hợp tương thích đặc biệt, **không phải khuyến nghị sử dụng token trong URL**. URL thường xuất hiện trong:

- access log của load balancer, reverse proxy, WAF và application server;
- browser history, bookmark, link được copy hoặc chia sẻ;
- các công cụ analytics, APM, telemetry, tracing và hệ thống giám sát;
- một số tình huống điều hướng hoặc ghi nhận referrer tùy trình duyệt/chính sách;
- screenshot, tài liệu hỗ trợ vận hành hoặc bản ghi lỗi chứa full request URI.

Vì bearer token có thể được dùng bởi bất kỳ ai sở hữu nó, để lộ `access_token` trên URL có thể đồng nghĩa để lộ credential. Nếu đã có một client cũ dùng query, cần kế hoạch chuyển sang header và bảo đảm log/telemetry che giấu token trong thời gian chuyển đổi.

Không bật `setAllowUriQueryParameter(true)` chỉ để khắc phục việc frontend bị lỗi CORS hoặc không thiết lập được `Authorization` header. Những vấn đề đó cần được xử lý ở lớp client/CORS/API gateway.

## 8. Có thể bật cả form và query không?

Về mặt API, các phương thức thiết lập có thể được gọi trên cùng một resolver:

```java
DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
resolver.setAllowFormEncodedBodyParameter(true);
resolver.setAllowUriQueryParameter(true);
```

Điều này mở rộng các nơi token có thể xuất hiện. Tuy nhiên, client vẫn phải **chọn một cách truyền token cho mỗi request**; request mang token ở nhiều nơi có thể bị từ chối là `invalid_request`. Việc bật hai chế độ không có nghĩa resolver trộn hoặc ghép các credential.

Trong một hệ thống công khai, càng nhiều nơi được phép chứa bearer token, càng nhiều lớp hạ tầng phải xử lý và che giấu dữ liệu nhạy cảm. Vì vậy, cấu hình dễ bảo trì và dễ kiểm toán thường là chỉ nhận `Authorization: Bearer`.

## 9. Tự viết BearerTokenResolver: khi nào cần?

Tự triển khai interface có ích khi hệ thống có một **giao thức truyền credential do hạ tầng kiểm soát** mà `DefaultBearerTokenResolver` không biểu diễn được, ví dụ một API chỉ nhận token từ header do một gateway đáng tin cậy tiêm vào theo hợp đồng riêng.

Hãy phân biệt hai trường hợp:

1. **Đổi tên header nhưng vẫn dùng cú pháp Bearer**: dùng `DefaultBearerTokenResolver#setBearerTokenHeaderName`; chưa cần custom class.
2. **Định dạng khác hoặc nguồn khác có chính sách tin cậy riêng**: cân nhắc `BearerTokenResolver` tự viết, nhưng cần kiểm soát rất kỹ nguồn dữ liệu.

Ví dụ dưới đây minh họa cách **bao bọc resolver chuẩn** để ghi nhận trạng thái request ở mức không chứa credential. Nó không thay đổi nguồn lấy token và chỉ nhằm trình bày contract của interface:

```java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

public final class ObservedBearerTokenResolver implements BearerTokenResolver {

    private final DefaultBearerTokenResolver delegate =
        new DefaultBearerTokenResolver();

    @Override
    public String resolve(HttpServletRequest request) {
        String token = delegate.resolve(request);

        // Có thể cập nhật metric đếm "có/không có credential" ở đây.
        // Không log hoặc gắn nhãn metric bằng chính token.

        return token;
    }
}
```

Cách đăng ký tương tự ví dụ cấu hình ở trên:

```java
http.oauth2ResourceServer(oauth2 -> oauth2
    .bearerTokenResolver(new ObservedBearerTokenResolver())
    .jwt(Customizer.withDefaults()));
```

Ví dụ này cho thấy resolver có thể được truyền trực tiếp vào `oauth2ResourceServer`. Trong ứng dụng thực tế, thường đăng ký resolver dạng Spring bean để quản lý cấu hình, kiểm thử và tái sử dụng nhất quán.

### 9.1. Không làm mất cơ chế báo lỗi chuẩn

Nếu custom resolver đọc từ nhiều nguồn, phải phân biệt:

- **Không có credential**: trả về `null`.
- **Có credential hợp lệ về định dạng**: trả về chuỗi token để Spring Security xác thực.
- **Credential bị lỗi/xung đột**: ném `OAuth2AuthenticationException` có mã lỗi phù hợp; không biến trường hợp lỗi thành `null` một cách im lặng.

Trong nhiều trường hợp có thể ủy quyền việc parse header Bearer cho `DefaultBearerTokenResolver` trước khi thêm logic riêng, thay vì tự viết regex. Nếu đọc header nội bộ, nên giới hạn bằng cấu hình mạng, xác thực gateway và loại bỏ header do client tự đặt tại biên. Resolver không phải nơi phù hợp để tự xây dựng một cơ chế proxy trust chỉ bằng việc kiểm tra tên header.

### 9.2. Không tùy tiện chuyển tiếp credential giữa dịch vụ

Ví dụ:

```text
Browser ── Authorization: Bearer token-A ──▶ Orders API
Orders API ── ? ──▶ Payments API
```

`BearerTokenResolver` của Orders API chỉ giúp đọc `token-A`. Nó không trao quyền gửi `token-A` đến Payments API. API phía sau phải tự xác thực token được cấp cho audience của mình, với scope và chính sách cần thiết. Khi phù hợp, Orders API cần dùng token exchange hoặc credentials của dịch vụ thay vì relay token sai audience.

Không dùng custom resolver để “chấp nhận cho qua” token có audience hoặc issuer khác; điều đó thuộc bước xác minh token và chính sách bảo mật của mỗi Resource Server.

## 10. BearerTokenAuthenticationFilter và xử lý lỗi

Luồng xử lý có thể chia thành bốn tình huống:

| Tình huống | Kết quả ở resolver | Phản ứng của hệ thống bảo mật |
|---|---|---|
| Không có bearer token | `null` | Tiếp tục filter chain; endpoint public có thể hoạt động, endpoint protected cần xác thực |
| Có bearer token nhưng token sai chữ ký/hết hạn | Chuỗi token | Cơ chế xác thực JWT/opaque từ chối |
| Bearer token biểu diễn sai cú pháp | `OAuth2AuthenticationException` | Authentication entry point xử lý lỗi ở lớp bearer |
| Có hai nguồn token bị xung đột | `OAuth2AuthenticationException` | Từ chối request theo chính sách bearer |

Theo RFC 6750, phản hồi thường sử dụng header `WWW-Authenticate` với scheme Bearer. Một số lỗi tiêu biểu:

| Tình huống lỗi | OAuth bearer error thường dùng | HTTP status thường gặp |
|---|---|---|
| Không có credential cho endpoint yêu cầu xác thực | Bearer challenge, có thể không kèm mã lỗi | 401 |
| Access token hết hạn, không hợp lệ hoặc không xác thực được | `invalid_token` | 401 |
| Request có nhiều cách truyền token hoặc biểu diễn yêu cầu không hợp lệ | `invalid_request` | 400 |
| Token hợp lệ nhưng thiếu scope bắt buộc | `insufficient_scope` | 403 |

Ví dụ phản hồi minh họa:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Mã phản hồi cụ thể phụ thuộc loại lỗi và cấu hình `AuthenticationEntryPoint`/`AccessDeniedHandler` của ứng dụng. Nếu thay exception handling mặc định, cần giữ ý nghĩa HTTP và Bearer challenge phù hợp để client có thể xử lý.

Đừng nhầm:

- `BearerTokenResolver` đọc token.
- `BearerTokenAuthenticationFilter` đưa token vào luồng xác thực.
- `JwtDecoder` hoặc `OpaqueTokenIntrospector` xác thực token.
- `AuthorizationManager`/method security quyết định thao tác được phép.

## 11. Hành vi Servlet cần lưu ý

### 11.1. Đừng nhầm Servlet với Reactive WebFlux

Trong Spring Security Servlet, resolver nhận `HttpServletRequest`. Trong WebFlux, việc chuyển đổi token từ request sử dụng API reactive riêng (như `ServerBearerTokenAuthenticationConverter`). Không mang `BearerTokenResolver` Servlet vào một ứng dụng `SecurityWebFilterChain` rồi kỳ vọng nó được gọi tự động.

### 11.2. Content type, POST body và request parameter

Servlet có API `getParameter` và cơ chế parse form/query parameter phụ thuộc vào request và container. Vì vậy, việc bật đọc `access_token` từ form body kéo theo cách xử lý request parameter của Servlet stack. Không coi bất kỳ JSON/XML/multipart body nào có field tên `access_token` là bearer credential chuẩn.

Nếu một controller cũng dùng tham số tên `access_token` cho mục đích nghiệp vụ, nó có thể tạo nhầm lẫn lớn. Nên dành tên tham số đó cho bearer credential theo hợp đồng giao thức và ưu tiên header chuẩn.

### 11.3. Public endpoint và bearer token bị lỗi

Một route được khai báo `permitAll()` không có nghĩa filter xác thực sẽ bỏ qua mọi bearer token gửi vào route đó. Nếu client gửi một `Authorization: Bearer ...` malformed tới endpoint public, bộ lọc vẫn có thể phát hiện và báo lỗi trước khi đến controller. Điều này khác với việc **không gửi token** đến một route public.

Nếu phải bỏ qua bộ lọc Resource Server cho một nhóm endpoint cụ thể, có thể thiết kế các `SecurityFilterChain` với `securityMatcher` phù hợp. Không nên tạo custom resolver trả `null` tùy ý cho đường dẫn để che vấn đề route/filter chain.

### 11.4. CORS, reverse proxy và header

Browser cần được CORS cho phép gửi header `Authorization` trong các request cross-origin có preflight. CORS phải cấu hình cho origin, method và header cần thiết. Thay token sang query chỉ để tránh preflight là lựa chọn không an toàn.

Nếu reverse proxy loại bỏ header `Authorization`, hãy kiểm tra cấu hình chuyển tiếp header và xác minh proxy đang bảo vệ credential đúng cách. Không nên mặc định đổi sang một header tự đặt khi nguyên nhân là sai cấu hình proxy.

## 12. Quan sát hành vi bằng ví dụ HTTP

Giả sử một endpoint `GET /api/orders/123` yêu cầu scope `orders.read` và Resource Server dùng `DefaultBearerTokenResolver` mặc định.

### Trường hợp A: header chuẩn

```bash
curl -i 'https://orders.example.com/api/orders/123' \
  -H 'Authorization: Bearer VALID_ACCESS_TOKEN'
```

Resolver tìm token và chuyển sang bước xác thực. Nếu token đã được xác thực, có scope phù hợp và người gọi được phép xem đơn `123`, request được xử lý bình thường.

### Trường hợp B: token đặt ở query

```bash
curl -i 'https://orders.example.com/api/orders/123?access_token=EXAMPLE_TOKEN'
```

Resolver mặc định không lấy token từ query. Endpoint bảo vệ sẽ coi yêu cầu là chưa xác thực nếu không có credential khác phù hợp.

### Trường hợp C: dùng Basic thay vì Bearer

```bash
curl -i 'https://orders.example.com/api/orders/123' \
  -H 'Authorization: Basic Zm9vOmJhcg=='
```

`DefaultBearerTokenResolver` không trích xuất Bearer token từ Basic header. Kết quả xử lý còn phụ thuộc các cơ chế xác thực khác mà SecurityFilterChain có thể đã cấu hình.

### Trường hợp D: chỉ có header được thay tên

```bash
curl -i 'https://orders.example.com/api/orders/123' \
  -H 'Proxy-Authorization: Bearer VALID_ACCESS_TOKEN'
```

Nếu ứng dụng vẫn dùng resolver mặc định, token không được đọc từ header này. Nếu ứng dụng đã gọi `setBearerTokenHeaderName(HttpHeaders.PROXY_AUTHORIZATION)`, token được tìm thấy và chuyển sang bước xác thực.

### Trường hợp E: gửi cả header và query sau khi bật query

```bash
curl -i 'https://orders.example.com/api/orders/123?access_token=TOKEN_B' \
  -H 'Authorization: Bearer TOKEN_A'
```

Nếu bật query parameter token, request có hai cách truyền bearer token và cần bị từ chối thay vì chọn `TOKEN_A` hoặc `TOKEN_B` tùy ý.

## 13. Kiểm chứng resolver riêng trong Servlet bằng unit test

Có thể dùng `MockHttpServletRequest` từ `spring-test` để minh họa hợp đồng của resolver mà không cần chạy HTTP server:

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpHeaders;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.oauth2.core.OAuth2AuthenticationException;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

class BearerResolverExamples {

    private final DefaultBearerTokenResolver resolver =
        new DefaultBearerTokenResolver();

    @Test
    void readsAuthorizationHeader() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/orders");
        request.addHeader(HttpHeaders.AUTHORIZATION, "Bearer abc.def-123");

        assertThat(resolver.resolve(request)).isEqualTo("abc.def-123");
    }

    @Test
    void returnsNullWhenBearerTokenIsMissing() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/orders");

        assertThat(resolver.resolve(request)).isNull();
    }

    @Test
    void ignoresQueryTokenByDefault() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/orders");
        request.setQueryString("access_token=abc");
        request.addParameter("access_token", "abc");

        assertThat(resolver.resolve(request)).isNull();
    }

    @Test
    void detectsMultipleTokenSourcesWhenQueryIsEnabled() {
        DefaultBearerTokenResolver withQuery =
            new DefaultBearerTokenResolver();
        withQuery.setAllowUriQueryParameter(true);

        MockHttpServletRequest request =
            new MockHttpServletRequest("GET", "/api/orders");
        request.setQueryString("access_token=token-b");
        request.addParameter("access_token", "token-b");
        request.addHeader(HttpHeaders.AUTHORIZATION, "Bearer token-a");

        assertThatThrownBy(() -> withQuery.resolve(request))
            .isInstanceOf(OAuth2AuthenticationException.class);
    }
}
```

Đây là ví dụ kiểm tra **quy tắc trích xuất**, không phải bài kiểm tra chữ ký JWT hay quyền truy cập. Để kiểm thử thực sự chuỗi lọc trong một ứng dụng MVC, có thể gửi HTTP request với header `Authorization` qua `MockMvc` và dùng một `JwtDecoder` thử nghiệm theo cấu hình test. Lưu ý `SecurityMockMvcRequestPostProcessors.jwt()` chủ yếu thiết lập ngữ cảnh xác thực phục vụ test authorization và có thể **không đi qua nhánh đọc bearer token từ raw HTTP header**; vì vậy đừng dùng riêng cách đó để kết luận một resolver tùy biến hoạt động chính xác.

## 14. Cách chọn cấu hình cho từng hệ thống

| Tình huống | Lựa chọn đề xuất | Lý do |
|---|---|---|
| SPA/mobile/backend client gửi `Authorization: Bearer` | Giữ `DefaultBearerTokenResolver` mặc định | Tương thích chuẩn, ít nguồn rò rỉ |
| Proxy chuyển token bằng `Proxy-Authorization: Bearer` | `setBearerTokenHeaderName` với nguồn proxy được bảo vệ | Đổi header mà vẫn giữ parser chuẩn |
| Client legacy chỉ gửi form body chuẩn | Cân nhắc `setAllowFormEncodedBodyParameter(true)` | Tương thích có kiểm soát, lên kế hoạch chuyển về header |
| Client muốn đưa token vào query | Ưu tiên sửa client; chỉ bật `setAllowUriQueryParameter(true)` trong ngoại lệ có kiểm soát | URL dễ rò rỉ credential |
| Gateway dùng giao thức truyền credential riêng | Custom `BearerTokenResolver` sau khi xác định rõ trust boundary | Cần kiểm tra nguồn, định dạng và xung đột |
| API trả 401 vì token JWT sai issuer/audience | Kiểm tra cấu hình decoder/validator, không đổi resolver | Resolver không chịu trách nhiệm kiểm chứng claim |
| API trả 403 vì thiếu scope/quyền đối tượng | Kiểm tra authorization và chính sách nghiệp vụ | Resolver đã hoàn tất công việc khi trích xuất token |

### Câu hỏi thiết kế nên trả lời

Trước khi thay mặc định, hãy xác định:

1. Credential đi vào từ header, form hay query? Ai có thể điều khiển nguồn đó?
2. Có khả năng client/gateway gửi đồng thời hai credential không? Hệ thống phải từ chối thế nào?
3. Token có thể xuất hiện ở URL, body log, trace hoặc error message không?
4. Proxy/gateway nào được tin để tiêm header? Có đường truy cập trực tiếp bỏ qua proxy không?
5. Token sau khi được trích xuất sẽ được decoder/introspector xác thực bằng issuer, audience và cơ chế phân quyền nào?

## 15. Tóm lược vai trò của từng thành phần

```text
HttpServletRequest
  |
  v
BearerTokenResolver / DefaultBearerTokenResolver
  |  đọc credential theo quy tắc nguồn / định dạng
  v
BearerTokenAuthenticationFilter
  |  tạo BearerTokenAuthenticationToken
  v
AuthenticationManager + JWT / Opaque Token provider
  |  xác thực token, tạo Authentication
  v
SecurityContext
  |
  v
Authorization rules + Business policy
  |  quyết định có cho thao tác với tài nguyên hay không
  v
Controller / Service
```

**`BearerTokenResolver` trả lời “token đang ở đâu trong request?”**.  
**`DefaultBearerTokenResolver` trả lời câu đó bằng quy tắc Bearer chuẩn, ưu tiên `Authorization` header.**  
**JWT validation, token introspection và authorization trả lời những câu hỏi độc lập về tính hợp lệ và quyền sử dụng token.**

Khi mở rộng nguồn lấy token, hãy chủ động thiết kế ranh giới tin cậy và xử lý xung đột. Với phần lớn REST API, cấu hình mặc định — nhận đúng một bearer token qua `Authorization` header — là điểm xuất phát phù hợp nhất.

## Tài liệu tham khảo

- [Spring Security Reference — OAuth 2.0 Resource Server, Servlet](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html)
- [Spring Security Reference — Bearer Token Resolution](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html)
- [Spring Security API — BearerTokenResolver](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/BearerTokenResolver.html)
- [Spring Security API — DefaultBearerTokenResolver](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/web/DefaultBearerTokenResolver.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
