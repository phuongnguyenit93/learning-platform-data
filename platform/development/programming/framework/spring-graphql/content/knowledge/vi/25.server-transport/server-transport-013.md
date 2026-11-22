# CORS và transport

Spring for GraphQL có thể tiếp nhận GraphQL operation qua nhiều transport. Với ứng dụng web, HTTP thường dùng cho query và mutation; WebSocket hoặc một transport streaming phù hợp được dùng cho subscription. Mỗi transport có quy tắc kết nối, bảo mật và cách xử lý khác nhau. CORS là một phần quan trọng khi browser gọi GraphQL API từ origin khác, nhưng CORS không thay thế authentication, authorization hay CSRF protection.

Khi triển khai, cần xác định rõ frontend được phép gọi từ origin nào, endpoint GraphQL nằm ở path nào, transport nào được bật, header xác thực được gửi ra sao và proxy phía trước chuyển tiếp request như thế nào. Cấu hình quá rộng có thể mở API cho website không mong muốn; cấu hình thiếu có thể khiến preflight bị chặn trước khi request GraphQL đến server.

## 1. CORS và same-origin policy

Browser áp dụng same-origin policy để giới hạn cách một trang web đọc tài nguyên từ origin khác. Một origin được xác định bởi bộ ba:

- Scheme, ví dụ http hoặc https.
- Host, ví dụ app.example.com.
- Port, ví dụ 443 hoặc 8443.

Vì vậy, các URL sau là những origin khác nhau:

~~~text
https://app.example.com
https://api.example.com
http://app.example.com
https://app.example.com:8443
~~~

Khi frontend ở https://app.example.com gọi GraphQL endpoint tại https://api.example.com/graphql, browser kiểm tra chính sách CORS của server. Server phải trả các response header phù hợp để browser cho phép JavaScript đọc response.

CORS là cơ chế do browser thực thi. Nó không phải authentication và cũng không ngăn một chương trình backend, curl hoặc ứng dụng native gọi trực tiếp endpoint. Vì vậy, endpoint GraphQL vẫn cần xác thực và authorization cho mọi request, bất kể CORS được cấu hình thế nào.

## 2. Preflight request

Với một số cross-origin request, browser gửi request preflight bằng method OPTIONS trước request thực tế. Preflight hỏi server xem origin, method và header dự kiến có được phép hay không.

Ví dụ frontend gửi POST với Content-Type application/json và Authorization header. Browser có thể gửi:

~~~http
OPTIONS /graphql HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: authorization,content-type
~~~

Server cần trả các header cho phép phù hợp:

~~~http
HTTP/1.1 204 No Content
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Methods: GET,POST,OPTIONS
Access-Control-Allow-Headers: Authorization,Content-Type
Access-Control-Max-Age: 3600
Vary: Origin
~~~

Nếu preflight không được xử lý đúng, browser sẽ không gửi request GraphQL thực tế. Vì vậy, khi debug lỗi CORS, hãy kiểm tra request OPTIONS trong browser developer tools trước khi xem resolver hoặc schema.

Preflight thường không mang cookie hoặc bearer token giống request thực tế. Nếu Spring Security yêu cầu authentication cho mọi request trước khi CORS xử lý, OPTIONS có thể bị trả 401/403. Cần để CORS được xử lý trước security authorization cho preflight.

## 3. Cấu hình CORS bằng Spring Boot properties

Spring Boot cung cấp nhóm cấu hình CORS cho GraphQL endpoint. Một cấu hình minh họa trong application.yml:

~~~yaml
spring:
  graphql:
    path: /graphql
    cors:
      allowed-origins:
        - https://app.example.com
        - https://admin.example.com
      allowed-methods:
        - GET
        - POST
        - OPTIONS
      allowed-headers:
        - Authorization
        - Content-Type
        - X-Correlation-Id
      exposed-headers:
        - X-Correlation-Id
      allow-credentials: true
      max-age: 1h
~~~

Các property CORS của GraphQL endpoint cho phép cấu hình origin, method, request headers, response headers được expose, credentials và thời gian cache preflight. Tên property và kiểu giá trị cụ thể có thể thay đổi theo phiên bản Spring Boot; hãy dùng metadata/configuration reference của phiên bản mà dự án đang chạy.

Không nên bật wildcard origin một cách tùy tiện trong production. Hãy khai báo chính xác origin frontend cần dùng, gồm scheme và host. Nếu frontend có nhiều môi trường, quản lý allowlist theo profile hoặc cấu hình triển khai thay vì hard-code một danh sách rộng trong mọi môi trường.

## 4. Cấu hình CORS bằng Spring MVC

Nếu ứng dụng dùng Spring MVC và muốn quản lý CORS ở tầng MVC, có thể đăng ký mapping cho GraphQL endpoint:

~~~java
@Configuration
public class GraphQlCorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/graphql")
            .allowedOrigins(
                "https://app.example.com",
                "https://admin.example.com")
            .allowedMethods("GET", "POST", "OPTIONS")
            .allowedHeaders(
                "Authorization",
                "Content-Type",
                "X-Correlation-Id")
            .exposedHeaders("X-Correlation-Id")
            .allowCredentials(true)
            .maxAge(3600);
    }
}
~~~

Mapping ở đây chỉ áp dụng cho path /graphql. Nếu GraphQL endpoint được đổi sang path khác, CORS mapping phải được cập nhật đồng bộ. Không cần mở CORS cho toàn bộ ứng dụng nếu chỉ frontend cần gọi GraphQL.

Chọn một nơi cấu hình làm nguồn chính. Nếu đồng thời cấu hình CORS ở Spring Boot GraphQL properties, MVC config, reverse proxy và gateway mà không có chủ đích, các lớp có thể trả header trùng hoặc policy không nhất quán. Khi response có hai Access-Control-Allow-Origin khác nhau, browser sẽ từ chối.

## 5. Cấu hình CORS bằng Spring WebFlux

Với ứng dụng WebFlux, có thể cấu hình CORS ở tầng WebFlux:

~~~java
@Configuration
public class GraphQlCorsConfiguration implements WebFluxConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/graphql")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET", "POST", "OPTIONS")
            .allowedHeaders(
                "Authorization",
                "Content-Type",
                "X-Correlation-Id")
            .exposedHeaders("X-Correlation-Id")
            .allowCredentials(true)
            .maxAge(3600);
    }
}
~~~

WebFlux dùng reactive web stack; không thêm cấu hình WebMvcConfigurer vào một ứng dụng WebFlux thuần. Hãy dùng đúng cấu hình tương ứng với web application type mà Spring Boot đã chọn.

Nếu dự án dùng Spring Security reactive, cần bảo đảm CORS được bật trong SecurityWebFilterChain và CORS configuration được đăng ký đúng nguồn. Cấu hình MVC và WebFlux không thể thay thế lẫn nhau chỉ bằng cách đổi tên interface.

## 6. CORS và Spring Security

Trong ứng dụng có Spring Security, CORS phải được xử lý trước bước authorization thông thường để preflight OPTIONS không bị yêu cầu đăng nhập. Với Spring Security servlet, cấu hình thường có dạng:

~~~java
@Bean
SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
    return http
        .cors(Customizer.withDefaults())
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers(HttpMethod.OPTIONS, "/graphql").permitAll()
            .anyRequest().authenticated())
        .build();
}
~~~

Đoạn trên giả định ứng dụng đã cung cấp CorsConfigurationSource hoặc cấu hình CORS tương ứng để Spring Security sử dụng. Chỉ permitAll cho OPTIONS không tự tạo các Access-Control-Allow-* header; CORS policy vẫn phải được khai báo.

Với WebFlux Security, dùng ServerHttpSecurity và bật cors ở SecurityWebFilterChain theo API của phiên bản Spring Security. Không trộn filter chain servlet với reactive.

Không nên permitAll toàn bộ /graphql chỉ để giải quyết lỗi CORS. Request thực tế vẫn phải đi qua authentication và authorization. Chỉ preflight OPTIONS cần được xử lý mà không đòi credential của người dùng.

## 7. allowedOrigins, allowedOriginPatterns và credentials

Hai cấu hình origin thường gặp:

- allowedOrigins nhận các origin cụ thể.
- allowedOriginPatterns hỗ trợ pattern để khớp origin theo quy tắc cấu hình.

Với allowCredentials(true), không thể trả Access-Control-Allow-Origin: * theo chuẩn CORS. Browser không chấp nhận wildcard origin khi response cho phép credential. Server phải trả về origin cụ thể đã được allowlist.

Ví dụ:

~~~java
configuration.setAllowedOrigins(List.of(
    "https://app.example.com",
    "https://admin.example.com"));
configuration.setAllowCredentials(true);
~~~

Nếu cần pattern cho các subdomain do tổ chức kiểm soát, dùng allowedOriginPatterns với pattern chặt chẽ. Không dùng pattern quá rộng như mọi host hoặc mọi scheme trong production. Pattern chỉ là cách khớp origin; nó không xác minh người dùng hoặc tenant.

Khi dùng cookie/session authentication, browser cần gửi request với credentials mode phù hợp. Server cũng phải bật allowCredentials và trả origin cụ thể. Ngoài CORS, cookie cần thuộc tính Secure, HttpOnly và SameSite phù hợp với kiến trúc frontend/backend. CORS không tự làm cookie được gửi cross-site.

## 8. allowedHeaders và exposedHeaders

Hai thuộc tính này có chiều truyền khác nhau:

| Cấu hình | Ý nghĩa |
| --- | --- |
| allowedHeaders | Những request header mà browser được phép gửi trong cross-origin request |
| exposedHeaders | Những response header mà JavaScript được phép đọc |

Ví dụ, frontend gửi Authorization và X-Correlation-Id thì hai header này phải được cho phép. Nếu server trả X-Correlation-Id và frontend muốn đọc giá trị đó để báo lỗi cho support, header cần nằm trong exposedHeaders.

Không cần cho phép mọi header bằng wildcard nếu frontend chỉ dùng một tập nhỏ. Hãy liệt kê chính xác header cần thiết, chẳng hạn Authorization, Content-Type, X-Correlation-Id và các header CSRF nếu ứng dụng sử dụng cookie authentication.

Header custom có thể làm phát sinh preflight. Khi thêm header mới ở frontend, hãy cập nhật CORS policy và kiểm thử OPTIONS.

## 9. HTTP transport cho GraphQL

HTTP là transport phổ biến nhất cho query và mutation. Spring for GraphQL cung cấp HTTP handler tích hợp với Spring MVC hoặc WebFlux. Spring Boot thường cấu hình endpoint ở path /graphql, nhưng có thể thay đổi bằng property spring.graphql.path.

Một GraphQL HTTP request thường chứa document và metadata:

~~~http
POST /graphql HTTP/1.1
Content-Type: application/json
Accept: application/graphql-response+json, application/json

{
  "query": "query Book($id: ID!) { bookById(id: $id) { id title } }",
  "operationName": "Book",
  "variables": {
    "id": "book-01"
  }
}
~~~

Các trường request thường dùng:

| Trường | Ý nghĩa |
| --- | --- |
| query | GraphQL document |
| operationName | Chọn operation khi document có nhiều operation |
| variables | Giá trị runtime cho variable |
| extensions | Metadata mở rộng theo client/server contract, ví dụ persisted query |

Với POST, request body thường là JSON. Server cần giới hạn kích thước body và kiểm tra content type; không nên chấp nhận payload tùy ý không giới hạn.

## 10. GET và POST semantics

GraphQL over HTTP cho phép GET cho query operation phù hợp với transport contract. GET không được dùng để thực thi mutation vì GET có semantics đọc an toàn và có thể bị browser, proxy hoặc cache tự động lặp lại.

Các nguyên tắc:

- Dùng POST cho mutation.
- Dùng POST cho query nếu document/variables lớn hoặc cần tránh đưa dữ liệu vào URL.
- Dùng GET cho query khi cần cache/CDN và dữ liệu phù hợp với URL semantics.
- Không đưa secret, token hoặc dữ liệu cá nhân vào query string.
- Server phải từ chối GET operation có loại mutation thay vì thực thi side effect.

GET request thường mã hóa query, operationName và variables thành query parameters. URL có thể xuất hiện trong browser history, proxy log và analytics; vì vậy không truyền password, access token hoặc dữ liệu nhạy cảm qua GET.

Nếu dùng persisted queries, client có thể gửi hash/extension theo protocol đã thống nhất. Persisted query không tự thay thế authorization hoặc query complexity limit.

## 11. HTTP response và GraphQL errors

HTTP status và GraphQL execution result là hai lớp khác nhau. Một request có thể hợp lệ ở transport nhưng một hoặc nhiều field gặp lỗi trong execution. Khi đó response có thể chứa cả data và errors.

Client nên:

- Kiểm tra status và content type ở HTTP layer.
- Parse GraphQL response theo contract.
- Kiểm tra errors ngay cả khi data có giá trị.
- Dùng extensions.code để xử lý lỗi nghiệp vụ.
- Không chỉ dựa vào HTTP 200 để kết luận mọi field thành công.

Các quy tắc HTTP status cho GraphQL phụ thuộc GraphQL over HTTP specification, loại lỗi và cách Spring for GraphQL phiên bản dự án xử lý request/execution errors. Hãy kiểm tra hành vi thực tế bằng integration test thay vì giả định mọi GraphQL error đều trả 400 hoặc 500.

## 12. WebSocket transport cho subscription

Subscription cần một cơ chế stream lâu dài. Spring for GraphQL hỗ trợ WebSocket transport với GraphQL WebSocket protocol. Client và server cần thống nhất subprotocol, thường là graphql-transport-ws.

Kết nối thường diễn ra như sau:

1. Browser mở WebSocket đến endpoint GraphQL.
2. Client và server thương lượng subprotocol.
3. Client gửi connection_init, có thể chứa thông tin xác thực theo contract.
4. Server xác thực connection và gửi connection_ack nếu chấp nhận.
5. Client gửi subscription operation.
6. Server phát next payload cho từng event và complete/error khi stream kết thúc.

WebSocket connection thường dùng cùng path hoặc path riêng so với HTTP GraphQL endpoint, tùy cấu hình ứng dụng. Cần công bố path và protocol rõ ràng cho frontend.

WebSocket không sử dụng CORS preflight giống fetch/XHR. Browser gửi Origin trong handshake; server cần kiểm tra origin được phép theo cấu hình WebSocket. Không được suy luận rằng CORS đã bật cho HTTP thì WebSocket tự động an toàn.

## 13. WebSocket Origin, authentication và CSRF

Với WebSocket, kiểm tra Origin đặc biệt quan trọng khi dùng cookie/session authentication. Nếu server chấp nhận kết nối từ mọi website, một trang độc hại có thể tìm cách mở WebSocket bằng cookie của người dùng đang đăng nhập. Đây là một dạng Cross-Site WebSocket Hijacking.

Các biện pháp cần có:

- Allowlist origin cụ thể cho WebSocket handshake.
- Xác thực principal trong handshake hoặc connection initialization theo thiết kế.
- Không tin userId/role do client gửi trong payload.
- Kiểm tra authorization cho từng subscription operation và resource.
- Quản lý token expiry, logout và thu hồi quyền trong stream dài hạn.
- Giới hạn số connection và subscription đồng thời theo principal/IP khi phù hợp.

Origin validation không thay thế authentication. Một request có Origin hợp lệ vẫn có thể không được xác thực; một token hợp lệ cũng không có nghĩa origin bất kỳ đều được phép.

Nếu dùng cookie authentication, hãy xem xét CSRF protection cho HTTP mutation và bảo vệ WebSocket chống cross-site hijacking. Không tắt CSRF toàn ứng dụng chỉ để WebSocket hoặc GraphQL POST hoạt động. Thiết kế token/header/cookie và origin policy theo đúng transport.

## 14. Cấu hình WebSocket endpoint

Trong Spring MVC hoặc WebFlux, WebSocket handler được đăng ký tại một path và có thể cấu hình origin allowlist ở lớp WebSocket registration. Hình dạng cấu hình phụ thuộc web stack và cách Spring Boot auto-configure GraphQL WebSocket handler.

Ví dụ minh họa với Spring WebSocket handler registration:

~~~java
@Configuration
@EnableWebSocket
public class GraphQlWebSocketConfiguration implements WebSocketConfigurer {

    private final WebSocketHandler graphQlWebSocketHandler;

    public GraphQlWebSocketConfiguration(
            WebSocketHandler graphQlWebSocketHandler) {
        this.graphQlWebSocketHandler = graphQlWebSocketHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(graphQlWebSocketHandler, "/graphql")
            .setAllowedOrigins("https://app.example.com");
    }
}
~~~

Đây là ví dụ về vị trí cấu hình origin trên Spring WebSocket registry; kiểu handler và bean thực tế cần lấy từ cấu hình GraphQL WebSocket mà ứng dụng đang sử dụng. Nếu Spring Boot đã tự đăng ký endpoint, không đăng ký handler thứ hai cùng path. Hãy tùy chỉnh registration hiện có hoặc dùng extension point được phiên bản Spring for GraphQL cung cấp.

Không dùng allowedOrigins("*") cho endpoint có cookie/session authentication. Nếu cần nhiều môi trường, cấu hình allowlist theo deployment profile.

## 15. RSocket và transport khác

Spring for GraphQL còn có tích hợp RSocket. RSocket phù hợp với giao tiếp reactive giữa các service hoặc client hỗ trợ protocol, có các interaction model như request-response và request-stream. Query/mutation thường tương ứng request-response; subscription/streaming có thể dùng request-stream theo cách tích hợp.

RSocket không phải HTTP fetch từ browser nên CORS không phải cơ chế bảo vệ chính. Thay vào đó, cần cấu hình authentication metadata, authorization, TLS, route và giới hạn kết nối theo môi trường triển khai. Không cho rằng việc dùng RSocket tự động làm API riêng tư hoặc an toàn hơn HTTP.

Nếu ứng dụng chỉ phục vụ browser frontend, HTTP cho query/mutation và WebSocket cho subscription thường đủ. Không thêm transport chỉ vì framework hỗ trợ; mỗi transport làm tăng số cấu hình, test và bề mặt bảo mật cần duy trì.

## 16. Reverse proxy, TLS và path forwarding

Production thường đặt API sau ingress, load balancer hoặc reverse proxy. Cần bảo đảm:

- TLS được dùng từ browser đến edge; nếu có nhiều hop nội bộ, xác định rõ nơi kết thúc TLS và bảo vệ hop tiếp theo.
- Proxy chuyển tiếp đúng path /graphql hoặc path đã cấu hình.
- Header Origin, Authorization và các header cần thiết không bị xóa hoặc ghi đè ngoài ý muốn.
- Forwarded headers được xử lý từ proxy đáng tin cậy; không tin X-Forwarded-Host do client gửi trực tiếp.
- WebSocket upgrade headers được proxy hỗ trợ.
- Idle timeout của proxy đủ dài cho subscription nhưng vẫn có heartbeat/keepalive phù hợp.
- Request body size, connection count và rate limit được cấu hình.

Nếu proxy rewrite /api/graphql thành /graphql, frontend phải gọi URL public và server/proxy phải thống nhất path. Lỗi 404 có thể là path mismatch; lỗi 502/504 có thể là upstream timeout hoặc proxy không giữ kết nối.

Không đặt timeout quá ngắn cho WebSocket subscription dài hạn. Ngược lại, không để kết nối treo vô hạn mà không có giới hạn connection, heartbeat hoặc cleanup khi client mất mạng.

## 17. Cấu hình và kiểm thử nhiều transport

Nên có integration test riêng cho từng transport được bật:

| Transport | Kiểm thử cần có |
| --- | --- |
| HTTP POST | Query, mutation, variables, content type, auth và GraphQL errors |
| HTTP GET | Query được phép, mutation bị từ chối, query string không chứa secret |
| CORS | Preflight OPTIONS, origin hợp lệ/không hợp lệ, allowed headers và credentials |
| WebSocket | Handshake, subprotocol, connection_init, authentication, subscription event và cancellation |
| RSocket (nếu dùng) | Route, authentication metadata, request-response và request-stream |
| Reverse proxy | Path, TLS, forwarded headers, WebSocket upgrade và timeout |

Ví dụ kiểm tra CORS preflight bằng WebTestClient:

~~~java
webTestClient.options()
    .uri("/graphql")
    .header("Origin", "https://app.example.com")
    .header("Access-Control-Request-Method", "POST")
    .header("Access-Control-Request-Headers", "authorization,content-type")
    .exchange()
    .expectStatus().is2xxSuccessful()
    .expectHeader().valueEquals(
        "Access-Control-Allow-Origin", "https://app.example.com");
~~~

Nên có thêm test origin không được phép và xác nhận browser không nhận policy cho phép. Với allowCredentials(true), kiểm tra server trả origin cụ thể, không trả wildcard.

Với WebSocket, dùng test client hỗ trợ WebSocket và xác nhận origin không hợp lệ bị từ chối ở handshake. Sau khi kết nối thành công, test connection_init và operation authorization; chỉ kiểm tra handshake là chưa đủ.

## 18. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Browser báo CORS nhưng curl chạy được | CORS do browser thực thi, curl không áp dụng same-origin policy | Kiểm tra OPTIONS và response CORS headers |
| OPTIONS trả 401/403 | Spring Security chặn preflight trước CORS | Bật CORS trong security chain và cho phép xử lý OPTIONS |
| CORS header bị lặp | Nhiều lớp cùng thêm Access-Control-Allow-Origin | Chọn một nguồn cấu hình chính |
| Credential request bị browser chặn | Dùng wildcard origin với allowCredentials | Trả origin cụ thể đã allowlist |
| Custom header không gửi được | Thiếu header trong allowedHeaders | Bổ sung header cần thiết vào preflight policy |
| JavaScript không đọc được response header | Header chưa nằm trong exposedHeaders | Expose đúng response header cần đọc |
| WebSocket handshake bị từ chối | Origin hoặc subprotocol không được phép | Kiểm tra Origin allowlist và graphql-transport-ws |
| WebSocket bị mở từ website lạ | Không kiểm tra Origin hoặc cookie-based auth thiếu bảo vệ | Giới hạn origin và xử lý CSWSH/CSRF |
| GET mutation bị thực thi | Server không enforce HTTP method semantics | Chỉ cho phép GET query; mutation dùng POST |
| Subscription ngắt sau một khoảng cố định | Proxy idle timeout hoặc thiếu keepalive | Điều chỉnh timeout và heartbeat theo transport |
| Endpoint 404 sau deploy | Path proxy và spring.graphql.path không khớp | Kiểm tra path rewrite và route public |

## 19. Nguyên tắc thiết kế CORS và transport

Chỉ allowlist origin frontend thực sự cần gọi API. Chỉ mở method và header cần thiết; bật credentials khi mô hình xác thực yêu cầu cookie/session và luôn trả origin cụ thể. Để CORS xử lý preflight trước authorization của Spring Security, nhưng vẫn yêu cầu authentication cho GraphQL request thực tế.

Dùng HTTP cho query/mutation theo semantics GET/POST phù hợp. Dùng WebSocket cho subscription khi cần stream và kiểm tra Origin, subprotocol, connection authentication cùng authorization theo operation/event. Chọn RSocket khi có nhu cầu giao tiếp phù hợp với protocol, đồng thời cấu hình metadata authentication và TLS.

Đặt transport path, CORS policy, proxy rewrite, TLS, body size, rate limit và timeout thành cấu hình triển khai có thể kiểm thử. CORS chỉ quyết định browser có được đọc response cross-origin; quyền truy cập dữ liệu vẫn phải được thực thi ở Spring Security và application service.

Trong Spring for GraphQL, schema và resolver mô tả API nghiệp vụ, còn transport quyết định request đi vào server bằng cách nào. Một cấu hình tốt giữ các ranh giới này rõ ràng để frontend gọi được API, subscription hoạt động ổn định và endpoint vẫn được bảo vệ đúng cách.
