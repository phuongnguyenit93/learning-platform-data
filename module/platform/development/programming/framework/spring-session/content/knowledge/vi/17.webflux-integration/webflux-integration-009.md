# WebSessionIdResolver và tùy chỉnh cookie hoặc header

Trong ứng dụng Spring WebFlux, định danh phiên được trao đổi qua HTTP bằng hợp đồng WebSessionIdResolver. Resolver đọc session ID từ request và gửi session ID hoặc chỉ thị hết hạn trong response. Nhờ đó, client có thể nhận diện cùng một WebSession qua nhiều request, trong khi Spring Session lưu dữ liệu phiên trong một repository reactive dùng chung.

Có hai cách trao đổi thường gặp: cookie và HTTP header. CookieWebSessionIdResolver phù hợp với trình duyệt tự động gửi cookie; HeaderWebSessionIdResolver phù hợp với API client hoặc ứng dụng di động chủ động quản lý header. Cả hai chỉ vận chuyển định danh phiên. Chúng không lưu dữ liệu phiên, không xác thực người dùng và không cấp quyền truy cập.

Bài học tập trung vào WebFlux và Spring Session reactive. Đây là mô hình WebSession và ReactiveSessionRepository, khác với Servlet HttpSession và SessionRepository. Ứng dụng cần chọn resolver theo loại client, cấu hình thuộc tính bảo mật phù hợp và kiểm thử cả hai chiều request/response.

## 1. WebSessionIdResolver giải quyết việc gì?

Mỗi request HTTP cần mang theo một định danh để server tìm lại phiên của client. Trong WebFlux, Spring Framework định nghĩa giao diện WebSessionIdResolver trong package org.springframework.web.server.session. Giao diện này làm việc với ServerWebExchange, là đối tượng đại diện cho request và response trong luồng reactive.

Ba phương thức chính:

| Phương thức | Vai trò |
|---|---|
| resolveSessionIds(exchange) | Đọc danh sách session ID từ request hiện tại |
| setSessionId(exchange, sessionId) | Gửi session ID về client qua response |
| expireSession(exchange) | Thông báo cho client loại bỏ định danh phiên hiện tại |

Các implementation chuẩn thường dùng:

- CookieWebSessionIdResolver: đọc và ghi session ID bằng cookie.
- HeaderWebSessionIdResolver: đọc và ghi session ID bằng HTTP header.

Resolver không truy cập Redis hoặc database. Nó chỉ cung cấp ID cho WebSessionManager. WebSessionManager phối hợp với WebSessionStore và ReactiveSessionRepository để khôi phục hoặc tạo WebSession.

Cần phân biệt API reactive với Servlet:

| WebFlux | Servlet |
|---|---|
| WebSessionIdResolver | HttpSessionIdResolver |
| WebSession | HttpSession |
| WebSessionManager | SessionRepositoryFilter |
| ReactiveSessionRepository | SessionRepository |
| ServerWebExchange | HttpServletRequest/HttpServletResponse |

Không cấu hình CookieHttpSessionIdResolver hoặc HeaderHttpSessionIdResolver của Servlet cho ứng dụng WebFlux. Tên lớp gần giống nhau nhưng thuộc hai API và vòng đời request khác nhau.

## 2. Resolver nằm ở đâu trong luồng WebFlux?

Spring Session thay WebSession mặc định của WebFlux bằng một implementation dựa trên ReactiveSessionRepository. Cấu hình reactive đăng ký WebSessionManager để điều phối việc tải, tạo và lưu phiên.

Luồng xử lý khái quát:

    Client gửi HTTP request
             |
             | Cookie hoặc header chứa session ID
             v
    WebSessionManager
             |
             | WebSessionIdResolver đọc ID
             v
    ReactiveSessionRepository
             |
             | Tải phiên từ kho dữ liệu
             v
    WebSession
             |
             v
    WebFilter / Handler / Controller
             |
             | Đọc hoặc thay đổi thuộc tính
             v
    WebSessionManager lưu phiên
             |
             | Resolver ghi ID hoặc xóa ID
             v
    HTTP response trả về client

Với Redis, ứng dụng reactive thường dùng ReactiveRedisSessionRepository và cấu hình @EnableRedisWebSession. Nếu tự cung cấp repository, @EnableSpringWebSession có thể đăng ký WebSessionManager dựa trên một ReactiveSessionRepository bean.

Ví dụ bật Redis-backed WebSession:

~~~java
@Configuration
@EnableRedisWebSession(maxInactiveIntervalInSeconds = 1800)
public class ReactiveSessionConfiguration {

    @Bean
    public WebSessionIdResolver webSessionIdResolver() {
        CookieWebSessionIdResolver resolver =
                new CookieWebSessionIdResolver();

        resolver.setCookieName("SESSION");
        resolver.addCookieInitializer(builder -> builder
                .path("/")
                .httpOnly(true)
                .secure(true)
                .sameSite("Lax"));

        return resolver;
    }
}
~~~

Đây là cấu hình cho Servlet-free WebFlux application dùng Redis reactive session. Cần có dependency Spring Session Redis và cấu hình kết nối Redis reactive phù hợp. Không dùng @EnableRedisHttpSession trong ví dụ này vì annotation đó dành cho Servlet HttpSession.

Khi dùng repository tự xây dựng hoặc một kho reactive khác, cấu hình có thể dùng @EnableSpringWebSession và cung cấp đúng một ReactiveSessionRepository. Repository phải thực hiện thao tác không blocking; không bọc JDBC blocking trong Mono/Flux rồi xem đó là repository reactive thực sự.

## 3. CookieWebSessionIdResolver và cookie mặc định

Spring Session dùng CookieWebSessionIdResolver làm resolver mặc định cho WebFlux khi không có resolver tùy chỉnh. Tên cookie mặc định là SESSION. Khi client chưa có phiên, WebFlux có thể tạo WebSession; resolver ghi session ID vào response cookie. Các request tiếp theo gửi lại cookie đó.

Ví dụ response:

~~~http
HTTP/1.1 200 OK
Set-Cookie: SESSION=<session-id>; Path=/; HttpOnly; Secure; SameSite=Lax
Content-Type: application/json
~~~

Giá trị session-id chỉ là placeholder. Session ID thực tế do Spring Session tạo ra. Trình duyệt lưu cookie và tự gửi lại theo domain, path, Secure và SameSite đã cấu hình.

Cookie resolver có các thao tác:

- setCookieName(String): thay tên cookie.
- setCookieMaxAge(Duration): đặt thời gian tồn tại phía trình duyệt.
- addCookieInitializer(...): bổ sung thuộc tính cookie như path, domain, HttpOnly, Secure và SameSite.
- resolveSessionIds(...): đọc session ID từ cookie trong request.
- setSessionId(...): ghi cookie chứa ID mới.
- expireSession(...): gửi cookie hết hạn để client loại bỏ ID.

Cookie là lựa chọn thuận tiện cho ứng dụng trình duyệt vì trình duyệt tự quản lý việc gửi cookie. Cấu hình cần tính đến domain, path, HTTPS, SameSite và cách triển khai frontend/backend trên cùng hay khác origin.

## 4. Tùy chỉnh thuộc tính cookie

Có thể dùng addCookieInitializer để tùy chỉnh ResponseCookie builder. Ví dụ:

~~~java
@Bean
public WebSessionIdResolver webSessionIdResolver() {
    CookieWebSessionIdResolver resolver =
            new CookieWebSessionIdResolver();

    resolver.setCookieName("APP_SESSION");
    resolver.addCookieInitializer(builder -> builder
            .path("/")
            .httpOnly(true)
            .secure(true)
            .sameSite("Lax"));

    return resolver;
}
~~~

Ý nghĩa các thuộc tính:

| Thuộc tính | Ý nghĩa | Gợi ý |
|---|---|---|
| Name | Tên cookie chứa session ID | Dùng tên riêng nếu cần phân biệt ứng dụng |
| Path | Phạm vi đường dẫn mà trình duyệt gửi cookie | "/" nếu cookie cần dùng trên toàn ứng dụng |
| Domain | Phạm vi host/subdomain được gửi cookie | Chỉ đặt khi thật sự cần chia sẻ giữa subdomain |
| HttpOnly | Ngăn JavaScript đọc cookie qua document.cookie | Bật cho session cookie của trình duyệt |
| Secure | Chỉ gửi cookie qua HTTPS | Bật trong production |
| SameSite | Kiểm soát gửi cookie trong ngữ cảnh cross-site | Chọn Lax, Strict hoặc None theo luồng đăng nhập |
| Max-Age | Thời gian cookie tồn tại trên client | Chọn theo trải nghiệm và chính sách phiên |

SameSite=Strict hạn chế cookie trong các điều hướng cross-site; điều này có thể ảnh hưởng luồng đăng nhập đi qua nhà cung cấp định danh bên ngoài. SameSite=Lax thường cân bằng giữa tiện dụng và hạn chế request cross-site. SameSite=None cho phép cookie trong ngữ cảnh cross-site nhưng trình duyệt hiện đại yêu cầu Secure. Hãy kiểm thử luồng OAuth/OIDC, thanh toán hoặc redirect nếu ứng dụng có sử dụng.

Không đặt Domain rộng hơn phạm vi cần thiết. Cookie domain rộng có thể khiến nhiều subdomain cùng nhận session credential. Nếu không cần chia sẻ cookie, để trình duyệt áp dụng host-only cookie.

## 5. Phân biệt cookie Max-Age và thời hạn WebSession

Cookie Max-Age và session timeout ở repository là hai giới hạn khác nhau.

- Cookie Max-Age quy định trình duyệt giữ cookie trong bao lâu.
- Thời gian không hoạt động của WebSession quy định repository xem phiên hết hạn sau bao lâu không có hoạt động.

Ví dụ cấu hình repository với thời hạn 30 phút:

~~~java
@EnableRedisWebSession(maxInactiveIntervalInSeconds = 1800)
~~~

Cookie có thể được cấu hình với Max-Age 30 phút:

~~~java
resolver.setCookieMaxAge(Duration.ofMinutes(30));
~~~

Hai giá trị có thể giống nhau, nhưng không tự động đồng nghĩa. Nếu cookie tồn tại lâu hơn session ở repository, trình duyệt có thể gửi một ID không còn phiên tương ứng. Server phải từ chối hoặc tạo phiên mới theo cách endpoint xử lý. Nếu cookie hết hạn sớm hơn repository, phiên vẫn có thể còn trong Redis nhưng client không còn ID để khôi phục.

Mặc định Max-Age của CookieWebSessionIdResolver là -1, nghĩa là cookie dạng session cookie được trình duyệt loại bỏ khi phiên trình duyệt kết thúc. Đây không phải TTL của dữ liệu server. Repository vẫn có thời hạn riêng để dọn dữ liệu.

Không dùng cookie Max-Age làm cơ chế thu hồi bảo mật. Khi logout hoặc khóa tài khoản, ứng dụng phải invalidate WebSession ở server. Xóa cookie chỉ loại bỏ định danh phía client.

## 6. HeaderWebSessionIdResolver và trao đổi ID bằng header

Với API client, ứng dụng di động hoặc SPA tự quản lý credential, có thể truyền session ID trong HTTP header. HeaderWebSessionIdResolver là implementation của Spring Framework để đọc và ghi ID qua header.

Header mặc định của HeaderWebSessionIdResolver là SESSION. Có thể đặt tên riêng, ví dụ X-Session-Id:

~~~java
@Bean
public WebSessionIdResolver webSessionIdResolver() {
    HeaderWebSessionIdResolver resolver =
            new HeaderWebSessionIdResolver();

    resolver.setHeaderName("X-Session-Id");
    return resolver;
}
~~~

Client gửi session ID trong request:

~~~http
GET /api/profile HTTP/1.1
Host: api.example.test
X-Session-Id: <session-id>
~~~

Khi server tạo hoặc thay đổi phiên, response có thể chứa:

~~~http
HTTP/1.1 200 OK
X-Session-Id: <session-id>
Content-Type: application/json
~~~

Client phải đọc giá trị response header, lưu ID theo chính sách bảo mật của nền tảng và gửi lại trong mọi request cần dùng phiên. Nếu client không gửi lại ID, server không thể liên kết request mới với phiên trước.

Khác với cookie resolver, header resolver không đặt cookie. Vì vậy, các thuộc tính HttpOnly, Secure, SameSite, Path và Domain không áp dụng cho header. Việc truyền qua HTTPS và bảo vệ nơi client lưu ID trở nên đặc biệt quan trọng.

## 7. Client phải xử lý vòng đời header

Một client dùng header cần thực hiện đủ các bước:

1. Gửi request đầu tiên không có session ID.
2. Đọc session ID từ response header khi server tạo phiên.
3. Lưu ID trong bộ nhớ hoặc kho credential bảo mật.
4. Gửi lại ID trong header ở các request tiếp theo.
5. Thay ID nếu server phát ID mới sau thao tác bảo mật.
6. Xóa ID ở client khi nhận thông báo hết hạn hoặc khi logout.
7. Xử lý trường hợp response bị mất, ID không hợp lệ hoặc phiên đã hết hạn.

Ví dụ JavaScript với Fetch API:

~~~javascript
let sessionId = null;

async function callProfile() {
    const headers = {};

    if (sessionId) {
        headers["X-Session-Id"] = sessionId;
    }

    const response = await fetch("/api/profile", {
        method: "GET",
        headers
    });

    const returnedId = response.headers.get("X-Session-Id");

    if (returnedId !== null) {
        sessionId = returnedId.length === 0 ? null : returnedId;
    }

    if (!response.ok) {
        throw new Error("Profile request failed");
    }

    return response.json();
}
~~~

Ví dụ chỉ giữ ID trong bộ nhớ trang để minh họa. Ứng dụng thực tế cần chọn kho lưu trữ phù hợp. Không ghi session ID vào URL, query string, analytics hoặc log. Nếu lưu trong localStorage, bất kỳ script cùng origin nào chạy được đều có thể đọc ID; XSS vì thế có thể dẫn đến chiếm quyền phiên.

## 8. CORS khi dùng header từ origin khác

Nếu frontend và WebFlux API ở hai origin khác nhau, custom header thường khiến trình duyệt gửi CORS preflight request. Server phải cho phép header trong request và cho phép JavaScript đọc header trong response.

Ví dụ cấu hình reactive CORS:

~~~java
@Bean
public CorsWebFilter corsWebFilter() {
    CorsConfiguration config = new CorsConfiguration();
    config.setAllowedOrigins(List.of("https://app.example.test"));
    config.setAllowedMethods(List.of("GET", "POST", "PUT", "DELETE", "OPTIONS"));
    config.setAllowedHeaders(List.of("Content-Type", "X-Session-Id"));
    config.setExposedHeaders(List.of("X-Session-Id"));
    config.setAllowCredentials(false);

    UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();
    source.registerCorsConfiguration("/api/**", config);

    return new CorsWebFilter(source);
}
~~~

Hai cấu hình quan trọng:

| CORS setting | Tác dụng |
|---|---|
| allowedHeaders | Cho phép trình duyệt gửi X-Session-Id trong request |
| exposedHeaders | Cho phép JavaScript đọc X-Session-Id trong response |

Nếu thiếu allowedHeaders, preflight có thể bị từ chối. Nếu thiếu exposedHeaders, server có thể trả ID nhưng JavaScript không đọc được. Chỉ cho phép origin, method và header cần thiết; không bật wildcard một cách tùy tiện.

Nếu dùng cookie cross-origin thay vì header, chính sách CORS và credentials khác: frontend cần gửi request với credentials, server phải cho phép credentials và chỉ định origin cụ thể. Cookie SameSite cũng phải phù hợp. Không trộn hai mô hình mà không xác định credential nào thực sự được dùng.

## 9. Xử lý hết hạn và logout

Resolver chỉ thông báo cho client về định danh phiên. Để logout đúng, ứng dụng phải invalidate WebSession phía server và để resolver loại bỏ cookie hoặc header.

Ví dụ controller WebFlux:

~~~java
@PostMapping("/api/logout")
public Mono<ResponseEntity<Void>> logout(WebSession session) {
    return session.invalidate()
            .thenReturn(ResponseEntity.noContent().build());
}
~~~

Khi WebSession bị invalidate, WebFlux/Spring Session xử lý xóa dữ liệu phiên theo repository và gọi resolver để client loại bỏ định danh. Với CookieWebSessionIdResolver, response gửi cookie hết hạn. Với HeaderWebSessionIdResolver, response dùng header tương ứng để thông báo client xóa ID.

Client vẫn có thể giữ ID cũ nếu response logout bị mất hoặc không được xử lý. Điều đó không được làm phiên cũ hợp lệ trở lại: request gửi ID đã invalidate phải không thể khôi phục phiên đã xóa. Vì vậy, server-side invalidation là bước thu hồi chính; xóa credential phía client là bước đồng bộ bổ sung.

Trong ứng dụng Spring Security reactive, nên dùng logout flow của Spring Security để xóa SecurityContext và invalidate WebSession theo cấu hình. Không tự xóa header/cookie ở client rồi xem đó là logout hoàn tất.

## 10. Đổi session ID sau xác thực

Sau khi người dùng đăng nhập, Spring Security có thể đổi session ID để phòng session fixation. Với WebFlux, WebSession cung cấp changeSessionId() trả về Mono<Void>. Việc thay đổi ID phải được lưu và gửi lại cho client qua resolver.

Ví dụ minh họa thao tác reactive:

~~~java
public Mono<Void> rotateSessionId(WebSession session) {
    return session.changeSessionId();
}
~~~

Không tự tạo ID mới trong client hoặc sửa header bằng một chuỗi ngẫu nhiên. ID phải do session repository/framework quản lý. Client cần cập nhật ID mới nhận từ response để request tiếp theo tiếp tục dùng phiên hiện tại.

Nếu response bị proxy loại bỏ header hoặc cookie mới, client có thể tiếp tục gửi ID cũ và mất phiên. Vì vậy, hãy kiểm thử login, ID rotation và request kế tiếp qua toàn bộ proxy/gateway thực tế.

## 11. Bảo mật session ID trong cookie và header

Session ID là bearer credential: người có ID còn hiệu lực có thể có khả năng sử dụng phiên. Hãy bảo vệ nó như mật khẩu tạm thời.

Với cookie:

- Bật Secure trong production và chỉ phục vụ qua HTTPS.
- Bật HttpOnly để JavaScript không đọc cookie.
- Chọn SameSite theo luồng đăng nhập và yêu cầu cross-site.
- Giới hạn Path và Domain.
- Không ghi cookie vào log hoặc trace.
- Invalidate session phía server khi logout.

Với header:

- Chỉ truyền qua HTTPS.
- Không ghi header session vào access log, trace, WAF log hoặc telemetry.
- Bảo vệ kho lưu trữ credential phía client.
- Giới hạn CORS origin và header.
- Không để XSS có thể đọc ID nếu có thể dùng cookie HttpOnly.
- Thu hồi phiên phía server khi logout, khóa tài khoản hoặc phát hiện lộ ID.

Header tùy chỉnh không tự tạo cơ chế chống CSRF hoàn chỉnh. Nó có thể khiến form HTML đơn giản khó gửi credential hơn, nhưng XSS có thể sử dụng credential và CORS quá rộng có thể cho trang khác tương tác với API. Cấu hình CSRF phải dựa trên cách trình duyệt giữ và gửi session credential. Không tắt CSRF chỉ vì resolver dùng header.

## 12. Không nhầm resolver với repository và xác thực

Các thành phần của WebFlux session có trách nhiệm riêng:

| Thành phần | Trách nhiệm |
|---|---|
| WebSessionIdResolver | Đọc/ghi session ID qua cookie hoặc header |
| WebSessionManager | Điều phối truy xuất WebSession trong request |
| WebSessionStore | Chiến lược tạo và lưu WebSession |
| ReactiveSessionRepository | Lưu, tải, cập nhật và xóa Session theo cách reactive |
| Spring Security reactive | Khôi phục Authentication, xác thực và phân quyền |
| Controller/service | Xử lý nghiệp vụ sau khi quyền truy cập được xác nhận |

Một request có header X-Session-Id không mặc nhiên được xác thực. ID có thể sai, hết hạn hoặc đã bị thu hồi. Sau khi khôi phục WebSession, Spring Security vẫn phải xác định Authentication và kiểm tra quyền cho endpoint.

Tương tự, CookieWebSessionIdResolver không phải cookie serializer của Servlet. Nó làm việc với ResponseCookie và ServerWebExchange trong WebFlux. Các cấu hình DefaultCookieSerializer của Servlet không áp dụng cho WebSessionIdResolver.

## 13. Repository reactive và giới hạn của JDBC

WebFlux yêu cầu luồng xử lý không blocking. Spring Session reactive dùng ReactiveSessionRepository, chẳng hạn ReactiveRedisSessionRepository cho Redis. JDBC repository tiêu chuẩn là SessionRepository dùng JdbcOperations, dành cho mô hình Servlet/blocking; không thể cắm trực tiếp vào WebSessionManager như một ReactiveSessionRepository.

Nếu ứng dụng cần WebFlux với kho dữ liệu quan hệ, phải chọn implementation reactive thực sự hoặc tự xây dựng repository dựa trên driver reactive phù hợp. Không chạy JDBC blocking trên event-loop thread, vì thao tác đó có thể làm nghẽn xử lý nhiều request và phá lợi ích của WebFlux.

Khi đánh giá repository reactive, hãy xác minh:

- Các thao tác load/save/delete có trả về Publisher và không block.
- Timeout và expiration được xử lý ở server side.
- Session ID rotation được hỗ trợ.
- Nhiều instance dùng chung cùng kho phiên.
- Serialization tương thích giữa các phiên bản.
- Hành vi cập nhật đồng thời được kiểm thử.
- Sự kiện vòng đời có được hỗ trợ và có thể bị trễ/mất hay không.

Resolver cookie/header có thể dùng với nhiều loại ReactiveSessionRepository. Tuy nhiên, khả năng lưu trữ, TTL, index và event phụ thuộc repository cụ thể.

## 14. Kiểm thử cookie và header bằng WebTestClient

Nên kiểm thử resolver qua HTTP thay vì chỉ kiểm tra bean được tạo. WebTestClient có thể xác nhận cookie/header trong response và gửi lại định danh trong request tiếp theo.

Các trường hợp kiểm thử:

1. Request đầu tiên không có ID và endpoint tạo WebSession.
2. Response có cookie SESSION hoặc header tùy resolver.
3. Request thứ hai gửi lại ID và đọc được thuộc tính phiên đã lưu.
4. Cookie có đúng tên, Path, Secure, HttpOnly và SameSite.
5. Header resolver dùng đúng tên header tùy chỉnh.
6. Logout invalidate phiên và response thông báo client xóa ID.
7. Gửi lại ID cũ sau logout không khôi phục được phiên.
8. Session ID rotation sau login phát ID mới và client dùng ID mới ở request tiếp theo.
9. CORS preflight cho phép request header và response expose header.
10. Hai instance dùng chung repository có thể khôi phục cùng WebSession.
11. Repository timeout và từ chối phiên hết hạn.
12. Log/proxy không ghi giá trị session ID.

Ví dụ kiểm tra header với WebTestClient có thể theo mẫu:

~~~java
webTestClient.get()
        .uri("/api/profile")
        .exchange()
        .expectStatus().isOk()
        .expectHeader().exists("X-Session-Id");
~~~

Đây là ví dụ kiểm tra response header; cần có endpoint thực sự tạo session để header được phát. Với cookie resolver, kiểm tra Set-Cookie và các thuộc tính riêng thay vì chỉ kiểm tra status code.

## 15. Lỗi thường gặp và cách điều tra

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Mỗi request tạo phiên mới | Client không gửi lại cookie/header hoặc resolver đọc sai tên | Kiểm tra request thực tế và resolver bean |
| Response không có cookie | Endpoint chưa start/tạo session hoặc response đã commit | Kiểm tra việc sử dụng WebSession và response headers |
| JavaScript không đọc được header ID | Thiếu Access-Control-Expose-Headers | Kiểm tra CORS response |
| Preflight bị từ chối | Header chưa nằm trong allowedHeaders | Kiểm tra OPTIONS và CORS policy |
| Cookie không được gửi ở cross-site | SameSite, Secure, Domain hoặc credentials không phù hợp | Kiểm tra browser cookie policy |
| Logout xong ID cũ vẫn được gửi | Client chưa xóa credential hoặc response logout bị mất | Kiểm tra expireSession và server-side invalidation |
| Một instance không tìm được phiên | Các node không dùng cùng reactive repository/namespace | Kiểm tra connection, namespace và cấu hình |
| Event-loop bị nghẽn | Repository hoặc code gọi thao tác blocking | Tìm JDBC/blocking call trong reactive chain |
| Login xong mất phiên | Client không cập nhật session ID sau rotation | Kiểm tra response login và request kế tiếp |

Khi điều tra, quan sát cả request và response. Response có session ID không chứng minh client đã lưu và gửi lại; request có ID cũng không chứng minh repository còn phiên hợp lệ.

## 16. Chọn cookie hay header?

| Tình huống | Lựa chọn thường phù hợp |
|---|---|
| Web app trình duyệt truyền thống | CookieWebSessionIdResolver |
| SPA cùng site, muốn HttpOnly cookie | Cookie resolver với cookie policy phù hợp |
| Mobile app tự quản lý credential | HeaderWebSessionIdResolver |
| API client không có cookie jar | Header resolver |
| Browser SPA khác origin | Cả hai đều có thể dùng; cần thiết kế CORS, SameSite và credential storage |
| Hệ thống muốn tránh JavaScript đọc session ID | Cookie HttpOnly thường phù hợp hơn |
| Backend dùng JWT stateless | Không cần WebSessionIdResolver chỉ để chuyển JWT |

Cookie thường giúp trình duyệt tự quản lý session credential và có thể đặt HttpOnly. Header phù hợp khi client chủ động kiểm soát request. Không lựa chọn nào tự động an toàn hơn; quyết định cần dựa trên rủi ro XSS/CSRF, CORS, mô hình domain, client platform và yêu cầu vận hành.

## 17. Checklist triển khai

Trước khi đưa resolver vào production, xác nhận:

- WebFlux dùng WebSession và ReactiveSessionRepository.
- WebSessionManager được cấu hình qua @EnableRedisWebSession hoặc @EnableSpringWebSession phù hợp.
- Chỉ có một WebSessionIdResolver rõ ràng.
- Cookie resolver dùng tên, Path, Secure, HttpOnly, SameSite và Domain phù hợp.
- Cookie Max-Age không bị nhầm với repository session timeout.
- Header resolver dùng tên header thống nhất giữa client, proxy và server.
- CORS cho phép gửi header và đọc header response khi cần.
- Logout invalidate phiên ở server và xóa định danh ở client.
- Login/session fixation cập nhật ID mới.
- Không ghi session ID vào log, URL hoặc telemetry.
- Mọi instance dùng cùng repository, namespace và serializer tương thích.
- Kiểm thử WebTestClient bao gồm tạo, đọc, đổi ID, logout, hết hạn và request qua nhiều instance.
- Không đưa repository JDBC blocking vào reactive event loop.

## Kết luận

WebSessionIdResolver là hợp đồng của Spring Framework để WebFlux đọc session ID từ request và gửi ID hoặc chỉ thị hết hạn trong response. CookieWebSessionIdResolver dùng cookie SESSION mặc định và cho phép tùy chỉnh thuộc tính qua addCookieInitializer; HeaderWebSessionIdResolver dùng HTTP header mặc định SESSION và có thể đổi tên header. Resolver chỉ vận chuyển định danh, còn WebSessionManager và ReactiveSessionRepository quản lý dữ liệu phiên. Hãy phân biệt cookie Max-Age với TTL repository, cấu hình CORS khi dùng header, bảo vệ session ID như credential, invalidate phiên phía server khi logout và kiểm thử toàn bộ vòng đời qua WebTestClient trong môi trường nhiều instance.

## Tài liệu tham khảo

- Spring Session WebSession Integration: https://docs.spring.io/spring-session/reference/web-session.html
- Spring Session Common Configurations: https://docs.spring.io/spring-session/reference/configuration/common.html
- Spring Session WebFlux Custom Cookie Guide: https://docs.spring.io/spring-session/reference/guides/boot-webflux-custom-cookie.html
- Spring Framework WebSessionIdResolver API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/session/WebSessionIdResolver.html
- CookieWebSessionIdResolver API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/session/CookieWebSessionIdResolver.html
- HeaderWebSessionIdResolver API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/session/HeaderWebSessionIdResolver.html
