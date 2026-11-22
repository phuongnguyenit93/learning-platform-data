# Token là dữ liệu nhạy cảm: tránh URL, log và thông báo lỗi

Trong hệ thống **Spring Security OAuth 2.0 / OIDC Resource Server**, một **Bearer Access Token** là thông tin nhạy cảm vì bên nào nắm được token hợp lệ thường có thể dùng nó để gọi API trong phạm vi quyền đã được cấp. Cơ chế Bearer dựa trên việc **sở hữu token**: nếu token bị sao chép, người khác có thể gửi lại token để yêu cầu tài nguyên cho đến khi token hết hiệu lực hoặc bị vô hiệu hóa, trừ khi hệ thống có thêm cơ chế ràng buộc token với bên sử dụng như DPoP hoặc mutual TLS.

Vì vậy, dù Resource Server có kiểm tra chữ ký JWT, issuer, audience, thời hạn và scope chính xác, ứng dụng vẫn có thể gặp sự cố nếu **đưa token vào URL, ghi token vào log, hoặc đưa token và chi tiết nội bộ vào thông báo lỗi**.

## 1. Vì sao phải coi token như bí mật?

Các loại token liên quan có mục đích khác nhau nhưng đều cần xử lý cẩn thận:

| Loại thông tin | Mục đích | Rủi ro khi lộ |
| --- | --- | --- |
| **Access Token** | Client dùng để truy cập Resource Server. | Người khác có thể gọi API với các quyền của token khi nó còn hiệu lực. |
| **Refresh Token** | Client dùng để yêu cầu Access Token mới khi được phép. | Có thể giúp duy trì quyền truy cập lâu hơn một Access Token; thường đặc biệt nhạy cảm. |
| **ID Token** | OIDC Client dùng để xác nhận thông tin đăng nhập của người dùng. | Có thể làm lộ định danh và claims cá nhân; không được dùng thay Access Token để gọi API. |
| **Client Secret / API Key** | Xác thực client hoặc truy cập dịch vụ theo cơ chế riêng. | Có thể cho phép giả mạo client hoặc gọi dịch vụ trái phép. |

**JWT không phải là dữ liệu đã được mã hóa chỉ vì có ba phần phân cách bằng dấu chấm.** JWT thông dụng được ký số (JWS): chữ ký giúp xác minh tính toàn vẹn và nhà phát hành, nhưng payload Base64url có thể được giải mã để đọc claims. Không nên nhét mật khẩu, khóa bí mật hoặc dữ liệu không cần thiết vào claims.

Một JWT được cắt ngắn trên màn hình (ví dụ **eyJ...**) vẫn không nên bị ghi toàn bộ ở bất kỳ đầu vào hoặc đầu ra nào khác. Không có “một nơi log an toàn” chỉ vì chỉ nhân viên nội bộ có quyền xem; log thường được sao chép đến công cụ quan sát, sao lưu, hệ thống phân tích và yêu cầu hỗ trợ.

## 2. Không truyền Bearer Access Token qua URL

### 2.1. Ví dụ sai

Các mẫu sau tạo rủi ro:

~~~http
GET /api/orders?access_token=eyJhbGciOi... HTTP/1.1
Host: api.example.test
~~~

~~~http
GET /api/download/eyJhbGciOi... HTTP/1.1
Host: api.example.test
~~~

Token xuất hiện trong **query string** hoặc **path** của URL có thể bị thu thập ở nhiều vị trí:

1. **Access log của reverse proxy, gateway, load balancer và web server.** Nhiều log ghi nguyên request target, bao gồm đường dẫn và query.
2. **Lịch sử trình duyệt, bookmark, gợi ý địa chỉ và ảnh chụp màn hình.** Người dùng có thể vô tình chia sẻ URL chứa token.
3. **Monitoring, APM và distributed tracing.** Thuộc tính như URL đầy đủ có thể được ghi vào span hoặc sự kiện.
4. **Header Referer khi trình duyệt điều hướng đến nơi khác.** Chính sách referrer có thể làm thay đổi mức độ rò rỉ; không nên dựa vào chính sách này để bảo vệ token đặt trong URL.
5. **Cache, công cụ phân tích, hệ thống quản lý lỗi và ticket hỗ trợ.** URL thường được xem là dữ liệu “không bí mật” nên dễ được sao chép.
6. **Redirect, email, tin nhắn và tài liệu hướng dẫn.** Một đường dẫn được dán để nhờ hỗ trợ có thể tiết lộ credential.

**Fragment** sau dấu **#** thường không được browser gửi lên server trong HTTP request, nhưng vẫn có thể xuất hiện trong lịch sử, bị JavaScript truy cập hoặc bị chia sẻ. Đây cũng không phải nơi phù hợp để cất token trong URL.

OAuth 2.0 có các cách mang Bearer token bằng form parameter hoặc URI query parameter trong RFC 6750 với ràng buộc riêng; **đối với API hiện đại, cách thông thường và được ưu tiên là Authorization header**. Tránh thiết kế API mới yêu cầu Bearer Access Token trong URL.

### 2.2. Ví dụ đúng: header Authorization

~~~http
GET /api/orders HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN
Accept: application/json
~~~

Với API, truyền token bằng:

**Authorization: Bearer ACCESS_TOKEN**

Header tách credential khỏi URL nên giảm nguy cơ đi vào lịch sử browser, access log URL và công cụ phân tích đường dẫn. Nhưng **header không tự động an toàn tuyệt đối**: nếu proxy hoặc ứng dụng ghi toàn bộ headers, token vẫn bị lộ. API cần chạy qua **HTTPS/TLS** để bảo vệ credential trên đường truyền.

Ví dụ phía client JavaScript:

~~~javascript
const response = await fetch("https://api.example.test/api/orders", {
  headers: {
    Authorization: "Bearer " + accessToken,
    Accept: "application/json"
  }
});

if (!response.ok) {
  throw new Error("Không thể tải danh sách đơn hàng");
}

const orders = await response.json();
~~~

Trong ví dụ này, **accessToken** là giá trị client đã nhận và quản lý hợp lệ. Không dùng **console.log(accessToken)**, không gắn token vào query string, và không hiển thị token trong lỗi gửi cho người dùng. Thiết kế quản lý token phía browser còn phải xét nguy cơ XSS, phạm vi lưu trữ và thời hạn token; một mô hình BFF giữ token ở server có thể phù hợp với ứng dụng web.

### 2.3. Trường hợp đường dẫn tải xuống hoặc chia sẻ

Một số hệ thống muốn tạo URL bấm được để tải tệp. **Không dùng OAuth Access Token dài hạn như một tham số tải xuống**. Có thể cân nhắc một trong các thiết kế sau tùy hệ thống:

- Tải qua endpoint đã xác thực bằng header hoặc session phù hợp.
- Backend for Frontend nhận session cookie, kiểm tra quyền rồi truy xuất tài nguyên bằng token ở phía server.
- Nếu bắt buộc phải dùng một URL truy cập tạm thời, cấp **vé/ticket ký riêng, phạm vi rất hẹp, thời gian ngắn hoặc một lần sử dụng**, và xử lý đường dẫn đó như một credential nhạy cảm: giảm ghi log, hạn chế cache, không đưa vào công cụ analytics và áp chính sách referrer thích hợp.

Một URL có chữ ký vẫn có thể là **Bearer credential**: ai sở hữu URL có thể dùng được nó trong thời hạn cho phép. Việc đặt thời hạn ngắn không biến URL thành dữ liệu công khai.

## 3. Log là nơi token dễ bị lộ ngoài ý muốn

Trong quá trình vận hành, token có thể bị ghi vào log dù lập trình viên chưa từng viết câu lệnh “log token” trực tiếp.

| Nơi phát sinh | Mẫu gây rủi ro | Hướng xử lý |
| --- | --- | --- |
| **Reverse proxy / API gateway** | Ghi URL đầy đủ, tất cả request headers. | Không ghi credential; cấu hình log theo các trường được phép. |
| **Spring filter / interceptor** | Ghi toàn bộ HttpServletRequest hoặc Authorization header. | Chỉ log method, mã trạng thái, route template và correlation ID an toàn. |
| **Exception handler** | Ghi nguyên request hoặc exception chứa credential. | Ghi loại lỗi đã chuẩn hóa, dùng cơ chế xử lý ngoại lệ kiểm soát dữ liệu. |
| **HTTP client gọi dịch vụ khác** | Wire logging hoặc debug in request headers. | Tắt/bịt thông tin nhạy cảm ở request/response logging. |
| **Distributed tracing / APM** | Ghi **url.full**, request headers, payload vào span. | Lọc dữ liệu ở nguồn, collector và exporter theo cấu hình thực tế. |
| **Metrics** | Dùng token, URL có query hoặc subject làm metric label. | Dùng tên route/operation cố định và nhãn có số lượng giá trị giới hạn. |
| **Alert, email, ticket, crash report** | Sao chép stack trace và raw request chứa token. | Sanitization trước khi phát hành hoặc chia sẻ nội dung. |

### 3.1. Mẫu code không nên sử dụng

~~~java
// KHÔNG LÀM: ghi credential vào log.
String authorization = request.getHeader("Authorization");
log.info("Authorization header: {}", authorization);

// KHÔNG LÀM: URL có thể chứa token hoặc dữ liệu nhạy cảm.
log.info("Request URL: {}", request.getRequestURL());
log.info("Query: {}", request.getQueryString());

// KHÔNG LÀM: đẩy exception thô về client.
return ResponseEntity.status(401).body(exception.getMessage());
~~~

Ngoài Authorization, các header như **Cookie**, **Set-Cookie**, **Proxy-Authorization**, **X-API-Key** và các header credential tùy biến cũng cần được bảo vệ. Tránh ghi toàn bộ request body: body có thể chứa mật khẩu, authorization code, refresh token, khóa API hoặc dữ liệu cá nhân.

Đặc biệt, **request.getRequestURI()** cũng không được coi là chắc chắn an toàn nếu hệ thống cho phép secret nằm trong path. **request.getQueryString()** càng dễ chứa secret. Tốt nhất là dùng tên **route template** cố định lấy từ router hoặc mã nghiệp vụ đã biết, ví dụ **GET /api/orders/{orderId}**, sau khi bảo đảm không lấy giá trị tham số động.

### 3.2. Mẫu log với dữ liệu được chọn lọc

Ví dụ filter Spring MVC chỉ ghi HTTP method và mã trạng thái:

~~~java
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
public class SafeRequestLogFilter extends OncePerRequestFilter {

    private static final Logger log =
        LoggerFactory.getLogger(SafeRequestLogFilter.class);

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain chain)
            throws ServletException, IOException {
        try {
            chain.doFilter(request, response);
        } finally {
            log.info(
                "http_request method={} status={}",
                request.getMethod(),
                response.getStatus());
        }
    }
}
~~~

Mẫu trên có chủ đích **không log URL, query, Authorization, Cookie, body hoặc token**. Đây là ví dụ tối thiểu về chọn trường log; hệ thống thật có thể thêm mã yêu cầu do server sinh, route template đã kiểm soát, latency hoặc mã lỗi nghiệp vụ đã chuẩn hóa. Không đưa token, raw JWT claims hoặc dữ liệu nhạy cảm vào **MDC** để tự động đi theo tất cả log.

Không nên in cả đối tượng **Jwt**, **Authentication**, **OAuth2AuthorizedClient** hoặc **TokenResponse** bằng **toString()** nếu chưa biết chính xác nội dung sẽ bị ghi. Một object log có thể mang claims, token value hoặc thông tin cá nhân.

### 3.3. Cấu hình Spring Boot để hạn chế lộ chi tiết lỗi

Ví dụ cấu hình dành cho production:

~~~yaml
logging:
  level:
    root: INFO
    org.springframework.security: INFO

server:
  error:
    include-message: never
    include-binding-errors: never
    include-stacktrace: never
    include-exception: false
~~~

Các thuộc tính **server.error** giúp hạn chế dữ liệu đưa vào error response mặc định của Spring Boot; mức log **INFO** tránh nhiều thông tin debug không cần thiết. Nhưng **đây không phải cơ chế tự xóa token trong mọi log**. Logger tùy biến, access log của proxy, bộ lọc log headers, APM và error tracker phải được kiểm soát riêng.

Khi gỡ lỗi, tránh bật **TRACE/DEBUG** kéo dài cho Spring Security, HTTP clients, servlet container hoặc proxy trong môi trường có token thật. Nếu cần điều tra ở môi trường kiểm soát, dùng dữ liệu thử không có hiệu lực, log theo allowlist và dọn dữ liệu sau khi kết thúc.

### 3.4. Ví dụ reverse proxy

Một số cấu hình access log mặc định của Nginx dùng biến **$request**: giá trị này chứa request line, bao gồm query string. Nếu client gửi Access Token trong query, token sẽ đi thẳng vào access log.

Ví dụ dạng log tối giản có chủ đích **không đưa URL hoặc header vào log**:

~~~nginx
log_format api_safe
    'method=$request_method status=$status '
    'request_time=$request_time';

access_log /var/log/nginx/api-access.log api_safe;
~~~

Đây chỉ là một ví dụ cấu hình Nginx. Cần xem xét các tầng khác như ingress controller, CDN, WAF, gateway và hệ thống thu thập log; thay đổi một access log không loại bỏ được tất cả nơi có thể ghi token. Những trường như **$request_uri**, **$args** hoặc request headers phải được kiểm soát riêng.

### 3.5. Không coi “che vài ký tự” là bảo vệ toàn diện

Các cách như “chỉ in 10 ký tự đầu của JWT” hoặc “dùng token làm correlation ID” vẫn có thể tạo thông tin theo dõi không cần thiết, tăng nguy cơ lộ định danh và gây nhầm lẫn về mức an toàn. Thông thường, log nên dùng **request ID riêng do server sinh** và loại lỗi, không dùng một phần token.

Nếu nghiệp vụ có yêu cầu đặc biệt phải liên kết các sự kiện với cùng một token, giải pháp phải được thiết kế riêng về bảo mật, quyền truy cập, thời gian lưu, rủi ro suy đoán và việc tránh khôi phục token từ dữ liệu đã ghi. Không tự động đưa hash của Access Token vào mọi log.

## 4. Thông báo lỗi xác thực phải đủ hữu ích nhưng không tiết lộ credential

Resource Server cần phân biệt ít nhất hai tình huống:

- **401 Unauthorized:** Không có credential phù hợp hoặc Access Token không thể được chấp nhận (hết hạn, sai chữ ký, sai issuer, sai audience...).
- **403 Forbidden:** Yêu cầu đã được xác thực, nhưng không có đủ quyền để truy cập tài nguyên.

API có thể trả trạng thái và mã lỗi chuẩn để client quyết định yêu cầu đăng nhập lại, làm mới token theo chính sách client, hoặc thông báo thiếu quyền. **Không cần trả lại token, một phần token, chuỗi JWT, chi tiết khóa ký, stack trace hoặc thông điệp nội bộ từ thư viện xác thực.**

### 4.1. Phản hồi HTTP nên ở mức nào?

Ví dụ khi thiếu credential:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
Content-Type: application/json

{"code":"unauthorized","message":"Yêu cầu xác thực không hợp lệ."}
~~~

Ví dụ khi Access Token không hợp lệ:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
Content-Type: application/json

{"code":"invalid_token","message":"Không thể xác thực yêu cầu."}
~~~

Ví dụ khi đã xác thực nhưng không đủ quyền:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
Content-Type: application/json

{"code":"forbidden","message":"Không đủ quyền truy cập tài nguyên."}
~~~

**WWW-Authenticate** là header challenge được OAuth 2.0 Bearer Token sử dụng. Tùy trường hợp, chuẩn cho phép cung cấp thêm các thuộc tính như **realm**, **scope** hoặc **error_description**; chỉ gửi thông tin thật sự cần cho client và đã được kiểm soát. Không phản chiếu token hoặc exception nội bộ vào **error_description**.

Thông báo như sau là không phù hợp:

~~~json
{
  "error": "JWT eyJhbGciOi... failed: expected issuer https://internal-idp.example.test, stack trace ..."
}
~~~

Ví dụ trên minh họa một **phản hồi cần tránh**, vì nó tiết lộ credential và chi tiết hệ thống. Mô tả lỗi ở phía client nên ổn định, ngắn, không chứa dữ liệu gắn với request cụ thể.

### 4.2. Spring Security Resource Server xử lý lỗi ở filter chain

Với cấu hình JWT Resource Server:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Spring Security dùng **BearerTokenAuthenticationFilter** để lấy Bearer token, sau đó xác thực bằng **JwtDecoder** và các validator theo cấu hình. Khi xác thực thất bại hoặc thiếu quyền, **AuthenticationEntryPoint** và **AccessDeniedHandler** của security chain quyết định phản hồi phù hợp.

**Không nên chỉ dựa vào @RestControllerAdvice** để xử lý lỗi JWT tại filter chain, vì những lỗi này có thể xảy ra **trước khi request vào controller**. Với Resource Server mặc định, Spring Security có **BearerTokenAuthenticationEntryPoint** và **BearerTokenAccessDeniedHandler** để xử lý các tình huống chuẩn. Nếu sản phẩm muốn chuẩn hóa JSON lỗi, hãy cấu hình xử lý lỗi tại lớp security phù hợp.

Đoạn **csrf(...disable)** trong ví dụ chỉ phù hợp với API thuần Bearer header, không sử dụng session cookie làm cơ chế xác thực. Nếu backend còn phục vụ web đăng nhập bằng cookie, cần thiết kế CSRF và các security chain riêng phù hợp với kiến trúc.

### 4.3. Ví dụ tùy biến lỗi không lộ token

Trong trường hợp API yêu cầu body JSON ổn định, có thể dùng entry point và access-denied handler chỉ xuất thông tin tổng quát:

~~~java
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiErrorSecurityConfig {

    @Bean
    SecurityFilterChain protectedApi(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults())
                .authenticationEntryPoint((request, response, ex) -> {
                    response.setStatus(HttpServletResponse.SC_UNAUTHORIZED);
                    response.setHeader(HttpHeaders.WWW_AUTHENTICATE, "Bearer");
                    response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                    response.getWriter().write(
                        "{\"code\":\"unauthorized\"}");
                })
                .accessDeniedHandler((request, response, ex) -> {
                    response.setStatus(HttpServletResponse.SC_FORBIDDEN);
                    response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                    response.getWriter().write(
                        "{\"code\":\"forbidden\"}");
                }));

        return http.build();
    }
}
~~~

Ví dụ này là **một cấu hình thay thế** cho cấu hình ở mục 4.2, không khai báo đồng thời cả hai bean cùng matcher **/api/** trong một ứng dụng. Nó trả lỗi JSON tối giản và tránh sử dụng **ex.getMessage()**, **request.getHeader("Authorization")** hoặc token trong response.

Trong môi trường thực, nếu cần **WWW-Authenticate** với chi tiết **invalid_token**, **insufficient_scope** hoặc scope bị thiếu theo RFC 6750, sử dụng hoặc tùy biến các handler của Spring Security sao cho giữ ngữ nghĩa chuẩn nhưng không lộ thông tin nhạy cảm. Mức chi tiết phản hồi là quyết định thiết kế, không phải lý do để đưa exception thô về client.

## 5. Kiểm soát vị trí Resource Server chấp nhận Bearer token

Spring Security Servlet sử dụng **DefaultBearerTokenResolver** để trích token từ request. Theo cấu hình mặc định thông dụng, nó đọc Bearer token từ **Authorization header** và **không bật nhận token bằng URI query parameter**. Đừng tự bật nhận token qua URL chỉ để thuận tiện tích hợp.

Nếu cần thể hiện chính sách trong cấu hình một cách tường minh:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.security.oauth2.server.resource.web.BearerTokenResolver;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

@Bean
BearerTokenResolver bearerTokenResolver() {
    DefaultBearerTokenResolver resolver = new DefaultBearerTokenResolver();
    resolver.setAllowUriQueryParameter(false);
    resolver.setAllowFormEncodedBodyParameter(false);
    return resolver;
}
~~~

Và đăng ký resolver trong **SecurityFilterChain** của API:

~~~java
.oauth2ResourceServer(oauth -> oauth
    .bearerTokenResolver(bearerTokenResolver())
    .jwt(Customizer.withDefaults()))
~~~

Đây là hai đoạn minh họa cách đặt bean và cách sử dụng bean trong cấu hình Java đầy đủ. Không đặt đoạn gọi **.oauth2ResourceServer(...)** đứng riêng trong file Java.

Các cấu hình này chỉ kiểm soát **đầu vào được chấp nhận**. Chúng không xóa URL đã được log ở tầng proxy, và cũng không bảo vệ header nếu ứng dụng đang ghi toàn bộ request.

## 6. Thiết kế xử lý lỗi và logging ở các lớp khác nhau

Để tránh bỏ sót, hãy nhìn vào toàn bộ đường đi của một request:

~~~text
Client
  |
  | Authorization: Bearer <token>
  | HTTPS
  v
CDN / Load Balancer / WAF
  |      Access log: tránh URL có secret, tránh headers nhạy cảm
  v
API Gateway / Reverse Proxy
  |      Audit/trace: chỉ chọn trường an toàn
  v
Spring Security Resource Server
  |      Bearer token resolver -> JWT validation / introspection
  |      Error handler: 401 / 403, không trả token
  v
Controller / Service
  |      Business log: không ghi Jwt, Authentication, request thô
  v
Database / Downstream API
         HTTP client tracing: không log Authorization hoặc refresh token

Log collector / APM / Error tracker
         Nhận dữ liệu đã loại bỏ credential ngay từ đầu
~~~

Nếu ứng dụng gọi API downstream, không chuyển tiếp **Authorization** của client một cách mù quáng đến dịch vụ khác. Access Token phải phù hợp **audience** của API đích và chính sách ủy quyền. Dù chuyển tiếp hợp lệ, hệ thống logging của HTTP client cũng phải tránh xuất token.

**Cache-Control: no-store** trên phản hồi nhạy cảm và **Referrer-Policy** hạn chế chia sẻ URL có thể là biện pháp phòng thủ bổ sung. Chúng không thay thế nguyên tắc **không đặt Bearer Access Token trong URL**.

## 7. Tình huống thực tế và cách nhận diện

### Tình huống A — API báo lỗi bằng cách hiển thị JWT

Một client gửi JWT hết hạn. Developer viết:

~~~java
log.warn("JWT invalid: {}", token);
return ResponseEntity.status(401)
    .body(Map.of("error", "Invalid token: " + token));
~~~

Kết quả: token bị ghi vào log và trả lại trong body. Dù token đã hết hạn, thói quen này cũng sẽ làm lộ token còn hiệu lực trong những trường hợp lỗi khác.

**Cách xử lý:** sử dụng mã lỗi **invalid_token** hoặc **unauthorized** đã chuẩn hóa. Log loại lỗi/operation an toàn và mã yêu cầu riêng; không ghi token. Với lỗi xác thực trong Spring Security filter chain, thực hiện xử lý tại entry point thay vì kỳ vọng controller tự bắt lỗi.

### Tình huống B — Copy một URL để nhờ hỗ trợ

Frontend có URL:

~~~text
https://api.example.test/api/export?access_token=eyJ...
~~~

Nhân viên copy URL vào chat nội bộ. Dù trang chat riêng tư, token đã bị sao chép sang hệ thống khác, có thể xuất hiện trong email thông báo, lịch sử và hệ thống tìm kiếm.

**Cách xử lý:** thay API bằng Bearer header, loại URL chứa token khỏi luồng hỗ trợ. Nếu cần mô tả request, cung cấp **method, route template, timestamp, mã yêu cầu**, không cung cấp credential thật.

### Tình huống C — Bật trace để xem lỗi 401

Để điều tra 401, nhóm vận hành bật HTTP wire logging trên gateway. Gateway ghi Authorization header của mọi request vào hệ thống lưu trữ tập trung.

**Cách xử lý:** chỉ thu các trường cần thiết như mã trạng thái và loại lỗi đã phân loại; đảm bảo tính năng redaction thực sự hoạt động trước khi bật capture. Tắt capture sau khi xử lý và bảo vệ log đã thu thập.

### Tình huống D — Metrics chứa toàn bộ URL

Hệ thống đo thời gian xử lý dùng **url.full** làm metric label. Các request đến URL có token tạo ra nhiều label riêng, làm tăng cardinality và có thể ghi token vào dữ liệu metrics.

**Cách xử lý:** dùng **route template** và method làm nhãn, ví dụ **GET /api/orders/{id}**, sau khi kiểm tra tham số động không được đưa vào label. Không dùng nguyên URL, JWT hoặc user-supplied token làm tên metric.

## 8. Nếu nghi ngờ token đã bị lộ

Xử lý token bị lộ như một sự cố credential, tùy mức độ và hệ thống phát hành:

1. **Dừng nguồn rò rỉ:** loại token khỏi tham số URL, log statement, tracing, thông báo lỗi hoặc dashboard đang ghi nó.
2. **Xác định phạm vi:** token loại gì, quyền nào, audience nào, thời điểm và thời gian hiệu lực, vị trí đã bị sao chép, ai có thể truy cập; tránh nhân bản token trong quá trình điều tra.
3. **Vô hiệu hóa khi có thể:** thu hồi token, thu hồi session/refresh token có liên quan, vô hiệu hóa client credentials hoặc giới hạn truy cập theo cơ chế thực tế của Authorization Server. JWT tự xác minh có thể **không thể bị thu hồi ngay** ở mọi hệ thống nếu không có cơ chế revocation, denylist hoặc thời hạn ngắn.
4. **Kiểm tra dấu hiệu lạm dụng:** xem hoạt động API bất thường bằng dữ liệu audit an toàn, quyền hạn và thời điểm sử dụng, thay vì chia sẻ credential thô.
5. **Giới hạn tồn tại dữ liệu đã lộ:** xử lý theo quy trình bảo mật đối với log, trace, snapshot, báo cáo lỗi và bản sao mà tổ chức kiểm soát được; cân nhắc tác động của backup và retention.
6. **Ngăn tái diễn:** dùng bộ lọc log allowlist, response lỗi chuẩn hóa, cấu hình gateway an toàn và kiểm thử với token giả trong môi trường phát triển.

**Giảm thời hạn Access Token và cấp scope tối thiểu** giúp thu hẹp tác động nếu token bị lộ, nhưng không thay thế việc ngăn token đi vào log hoặc URL.

## 9. Nguyên tắc có thể áp dụng ngay

| Vấn đề | Không nên | Nên |
| --- | --- | --- |
| Gửi token tới API | **?access_token=...** hoặc path chứa token. | **Authorization: Bearer ...** qua HTTPS. |
| Logging | Log toàn bộ request, headers, JWT hoặc exception thô. | Log các trường được phép, route template và mã yêu cầu độc lập. |
| HTTP 401 | Trả token, stack trace, chi tiết khóa ký hoặc exception message. | Trả status, challenge và mã lỗi ngắn gọn, ổn định. |
| HTTP 403 | Trả toàn bộ claims, nội dung policy nội bộ. | Trả mã lỗi thiếu quyền phù hợp, không tiết lộ secret. |
| Debugging | Bật wire log trên môi trường có credential thật. | Dùng dữ liệu thử, redaction và điều tra theo mã yêu cầu. |
| Monitoring | Dùng URL đầy đủ hoặc token làm metrics label. | Dùng operation, route template và nhãn hữu hạn. |
| OAuth token trong URL tải tệp | Dùng Access Token dài hạn. | Endpoint bảo vệ bằng header/session, hoặc ticket riêng giới hạn chặt chẽ. |
| Token bị rò rỉ | Chỉ xóa dòng log ở một ứng dụng. | Xác định các bản sao, thu hồi/giới hạn token và xử lý sự cố theo phạm vi. |

## 10. Ghi nhớ trong Spring Security Resource Server

1. **Bearer Access Token là credential.** Người sở hữu token thường có thể dùng nó; không xem JWT là dữ liệu công khai.
2. **Authorization header qua HTTPS là vị trí gửi token thông thường cho HTTP API.** Tránh query string, path, fragment hoặc redirect URL để mang Access Token.
3. **Không ghi credential ở bất kỳ tầng nào.** Spring application log, proxy access log, HTTP client, APM, error tracker và metric label đều có thể làm lộ token.
4. **Không phản chiếu lỗi thư viện xác thực ra client.** Resource Server phải trả lỗi 401/403 và challenge phù hợp mà không tiết lộ token hoặc thông tin nội bộ.
5. **Thiết kế ngăn rò rỉ từ đầu.** Chỉ chọn trường log được phép, quản lý quyền xem log, giới hạn thời gian lưu, sử dụng token ngắn hạn và scope tối thiểu.

Khi gặp lỗi xác thực, hệ thống cần trả lời **“yêu cầu có được xác thực và cấp quyền hay không?”** mà không tiết lộ **“credential thực tế của yêu cầu là gì?”**. Đây là ranh giới bảo mật quan trọng giữa cơ chế xác thực và hệ thống quan sát, hỗ trợ, xử lý lỗi.

## Tài liệu tham khảo

- [RFC 6750 — The OAuth 2.0 Authorization Framework: Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750).
- [RFC 9700 — Best Current Practice for OAuth 2.0 Security](https://www.rfc-editor.org/rfc/rfc9700).
- [Spring Security — OAuth 2.0 Resource Server: Bearer Tokens](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/bearer-tokens.html).
- [Spring Security — OAuth 2.0 Resource Server: JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [OWASP Cheat Sheet — Logging](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html).
