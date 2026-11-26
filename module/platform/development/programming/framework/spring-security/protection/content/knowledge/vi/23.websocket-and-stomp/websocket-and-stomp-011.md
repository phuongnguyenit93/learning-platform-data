# Miễn trừ CSRF lớp HTTP cho transport trong phạm vi có bảo vệ thay thế

## 1. Bối cảnh: vì sao SockJS POST bị 403 dù ứng dụng không cố gửi một lệnh nghiệp vụ HTTP?

Một website quản lý đơn hàng dùng Spring Security với đăng nhập bằng session cookie, Spring WebSocket Message Broker với STOMP và SockJS để hỗ trợ các môi trường mà native WebSocket không hoạt động. Browser tại `https://app.example.com` đã đăng nhập, mở SockJS endpoint `/ws`. Khi SockJS chọn XHR fallback, DevTools ghi nhận:

~~~http
POST /ws/173/abcXYZ/xhr_send HTTP/1.1
Host: app.example.com
Cookie: SESSION=<session-id>
Content-Type: text/plain;charset=UTF-8

["<encoded-STOMP-frame>"]
~~~

Response:

~~~http
HTTP/1.1 403 Forbidden
~~~

Lý do có thể không phải lệnh `STOMP SEND` sai quyền. **Servlet `CsrfFilter` của Spring Security kiểm tra HTTP POST** trước khi request vào hạ tầng SockJS. Một số SockJS transport không đưa HTTP CSRF token vào request POST bằng cách ứng dụng REST thông thường làm; token được STOMP client truyền bên trong **STOMP `CONNECT` frame**.

Có nhóm chọn cách “sửa nhanh”:

~~~java
// KHÔNG dùng cách này để sửa một đường vận chuyển SockJS.
http.csrf(csrf -> csrf.disable());
~~~

Kết quả là cả các REST/form POST/PUT/PATCH/DELETE dựa vào cookie có thể mất phòng vệ CSRF. Bài này giới thiệu cách **miễn trừ có giới hạn ở lớp HTTP cho những request transport thực sự cần**, đồng thời giữ **những lớp kiểm soát thay thế đủ mạnh**, đặc biệt là Origin, authentication, CSRF tại STOMP CONNECT và message authorization.

Đây là bài của chương **WebSocket và STOMP** trong mô-đun **SPRING_SECURITY_HTTP_PROTECTION**. Mô-đun áp dụng các lớp phòng vệ HTTP/trình duyệt của Spring Security — CSRF, CORS, security headers, CSP, HSTS, HTTP firewall, bảo vệ session — trên Servlet lẫn Reactive. Trọng tâm ở đây là **ngoại lệ CSRF HTTP đúng phạm vi**, không phải bỏ bảo vệ CSRF nói chung.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt HTTP CSRF của SockJS fallback POST với CSRF ở STOMP `CONNECT` và quyền ở `SEND`/`SUBSCRIBE`.
2. Nhận diện chính xác request transport nào bị `CsrfFilter` chặn, thay vì nới mọi `/ws/**` theo cảm tính.
3. Viết `RequestMatcher` ràng buộc **HTTP method + đường dẫn transport** và gắn vào `csrf.ignoringRequestMatchers(...)` trên Servlet.
4. Giữ HTTP CSRF cho những endpoints thay đổi trạng thái như REST API, form và business operations.
5. Kết hợp Origin allowlist, authenticated session, CSRF CONNECT, deny-by-default message ACL, object/tenant ACL và rate limits.
6. Hiểu tại sao Origin hoặc CORS đơn lẻ không đủ thay mọi yêu cầu CSRF.
7. Phân biệt SockJS XHR POST, legacy iframe, native WebSocket và HTTP REST.
8. Thiết kế kiểm thử âm/dương cho matcher, HTTP transport và STOMP end-to-end, bao gồm **không có side effect trái quyền**.
9. Xử lý reverse proxy, context path, cookie scope, multi-node và fallback browser.
10. Biết giới hạn khi chuyển sang WebFlux native; không copy nguyên Servlet request matcher sang Reactive security.

Đường dẫn `/ws`, domain và ví dụ payload chỉ để minh họa. Chính xác URL, method, transport có thể thay đổi theo phiên bản SockJS và runtime; cần xác minh trong hệ thống thực trước khi tạo exception.

## 2. Ranh giới security: bốn lần ra quyết định khác nhau

Một ứng dụng SockJS + STOMP dùng session cookie có thể trải qua bốn lớp:

| Lớp | Đầu vào | Thành phần bảo vệ | Câu hỏi bảo mật |
| --- | --- | --- | --- |
| HTTP transport | `GET /ws/info`, `POST /ws/{server}/{session}/xhr_send`, handshake | Servlet `SecurityFilterChain`, `CsrfFilter`, HTTP auth, CORS | HTTP request này có được tiếp nhận không? |
| WebSocket/SockJS Origin | `Origin` từ browser khởi tạo request | `StompEndpointRegistry#setAllowedOrigins` và cơ chế same-origin tương ứng | Website nào được browser kết nối? |
| STOMP CONNECT | `CONNECT` frame bên trong transport | CSRF CONNECT, principal, optional verified bearer interceptor | Messaging session có đủ điều kiện để hình thành không? |
| STOMP SEND/SUBSCRIBE | Frames sau CONNECTED | `AuthorizationManager<Message<?>>`, `@MessageMapping`, service ACL | User được làm gì và nghe dữ liệu nào? |

**Miễn CSRF ở lớp HTTP cho một POST vận chuyển không đồng nghĩa miễn authentication, Origin check hoặc CSRF CONNECT.** Nó chỉ nói rằng HTTP `CsrfFilter` không yêu cầu HTTP CSRF parameter/header trên đúng request đã được chọn.

### 2.1. Sơ đồ kiểm tra

~~~mermaid
flowchart TD
    A["Browser / SockJS client"] --> B{"HTTP request tới /ws/**"}
    B --> C["Authentication và HTTP authorization"]
    C --> D{"HTTP method + transport path?"}
    D -- "POST xhr_send được phê duyệt" --> E["Bỏ yêu cầu HTTP CSRF token cho transport"]
    D -- "HTTP state-changing khác" --> F["Servlet CsrfFilter kiểm tra token"]
    E --> G["SockJS transport xử lý payload"]
    F --> G
    G --> H{"STOMP CONNECT đã hợp lệ?"}
    H -- "Chưa / token sai" --> I["Từ chối messaging; không xử lý lệnh"]
    H -- "Có" --> J["MESSAGE/SUBSCRIBE authorization"]
    J --> K["Service kiểm tra object/tenant, validation"]
    K --> L["Publish đến đúng user/subscription"]
~~~

Sơ đồ giả định mọi transport requests vẫn đi qua authentication, Origin control và HTTP security được cấu hình phù hợp. HTTP `GET` thường không bị mặc định CSRF protection yêu cầu token, nhưng vẫn cần authentication và Origin nếu ứng dụng không public.

### 2.2. Không có một “CSRF” duy nhất trên mọi giao thức

| Tình huống | HTTP `CsrfFilter` có xử lý không? | Messaging CSRF có xử lý không? |
| --- | --- | --- |
| REST `POST /api/orders` | Có theo HTTP CSRF policy | Không |
| HTTP `POST /ws/.../xhr_send` | Có, trừ khi có exception hẹp | STOMP CONNECT bên trong request có thể còn phải qua kiểm tra riêng |
| Native WebSocket `GET /ws` Upgrade | GET thông thường không đòi HTTP CSRF token | CONNECT tiếp theo được kiểm tra riêng |
| STOMP `CONNECT` trên WebSocket | Không phải một HTTP request riêng | Có khi `@EnableWebSocketSecurity` tích hợp yêu cầu |
| STOMP `SEND` trên socket | Không chạy lại HTTP `CsrfFilter` | Kiểm tra message authorization/service ACL |
| STOMP `SUBSCRIBE` | Không chạy lại HTTP `CsrfFilter` | Kiểm tra subscription authorization |

Nhầm hai cột sẽ dẫn tới “tắt nhầm tầng”: vô hiệu HTTP CSRF toàn hệ thống hoặc gửi token sai chỗ.

## 3. Vì sao SockJS fallback làm xuất hiện POST transport?

### 3.1. Native WebSocket

Trong native WebSocket phổ biến, HTTP handshake là request GET Upgrade:

~~~http
GET /ws/123/xyz/websocket HTTP/1.1
Host: app.example.com
Connection: Upgrade
Upgrade: websocket
Origin: https://app.example.com
Cookie: SESSION=<session-id>
~~~

Sau `101 Switching Protocols`, dữ liệu đi qua WebSocket frames. STOMP `CONNECT`, `SEND` và `SUBSCRIBE` **không tạo HTTP POST mới** cho từng frame.

### 3.2. XHR fallback

Khi browser/network không dùng được native WebSocket, SockJS có thể dùng HTTP XHR streaming/polling:

~~~text
GET  /ws/info
GET  /ws/123/xyz/xhr_streaming
POST /ws/123/xyz/xhr_send
GET  /ws/123/xyz/xhr
...
~~~

Trong ví dụ, HTTP `POST /ws/123/xyz/xhr_send` mang dữ liệu STOMP đã được SockJS encode. Đây là **vận chuyển dữ liệu cho giao thức realtime**, không phải `POST /api/orders` do controller nghiệp vụ xử lý.

Tuy nhiên, với browser cookie-authenticated, nó vẫn là một HTTP POST và vì vậy `CsrfFilter` có thể áp dụng bộ quy tắc mặc định cho unsafe methods. Một số SockJS clients/transports không thể đặt custom HTTP CSRF header theo cùng cách một `fetch` của ứng dụng làm; token dành cho Spring Security Messaging được gửi trong **STOMP CONNECT native header**.

### 3.3. POST không có nghĩa là lệnh nghiệp vụ được ủy quyền

Lớp SockJS nhận POST có thể chứa:

~~~text
["CONNECT\nX-CSRF-TOKEN:<valid-token>\n\n\u0000"]
~~~

hoặc một `SEND` frame từ phiên STOMP đã CONNECTED. **Server phải từ chối mọi lệnh nghiệp vụ chưa qua authentication và policy STOMP**, dù HTTP transport POST đã được `CsrfFilter` bỏ qua.

Không bao giờ để một controller nghiệp vụ như `POST /ws/admin/delete` nằm chung namespace được exempt mà không cần kiểm tra CSRF riêng. Một exception dành cho transport là điều kiện rất hẹp.

### 3.4. Không phải mọi fallback là POST

| Đường đi quan sát | HTTP method thường gặp | Có cần miễn HTTP CSRF mặc định không? |
| --- | --- | --- |
| `/ws/info` | GET | Thông thường không; GET là safe method trong HTTP CSRF policy |
| `/ws/123/xyz/websocket` | GET Upgrade | Thông thường không |
| `/ws/123/xyz/xhr_streaming` | GET | Thông thường không |
| `/ws/123/xyz/xhr` | GET | Thông thường không |
| `/ws/123/xyz/xhr_send` | POST | Có thể cần exception nếu không có HTTP CSRF token |
| Legacy `jsonp_send` hoặc các transport khác | Tùy phiên bản | Chỉ đánh giá sau khi xác định transport thực tế |
| `/api/orders` | POST/PUT/DELETE | **Phải giữ HTTP CSRF** khi dùng cookie credentials |

Không làm ngoại lệ cho tất cả HTTP methods chỉ vì tất cả URL đều bắt đầu bằng `/ws`. Với transport không có trong danh sách, hãy kiểm tra phiên bản và browser trước khi mở thêm.

## 4. Threat model trước khi miễn trừ

### 4.1. Kẻ tấn công có thể làm gì?

Giả sử Alice đăng nhập và browser có cookie phiên. Website không tin cậy `https://evil.example.net` thử tạo một cross-origin request đến `/ws/.../xhr_send`. Tùy cookie `SameSite`, browser policy và HTTP method/content-type, một request cross-site có thể **được gửi** ngay cả khi JavaScript không được đọc response vì CORS.

Nếu HTTP CSRF bị miễn mà server còn cho Origin lạ và nhận STOMP data chưa xác thực, attacker có thể thử gửi lệnh thay Alice. Vì vậy một ngoại lệ HTTP phải được ghép với phòng vệ bù thật sự.

### 4.2. Những bảo vệ bù quan trọng

Một thiết kế cookie/session STOMP có thể dựa vào:

1. **HTTP authentication**: transport requests vẫn phải thuộc một session hợp lệ; không `permitAll("/ws/**")` vì đang exempt CSRF.
2. **Origin policy**: chỉ frontend browser tin cậy được dùng endpoint. Với same-origin deployment, giữ origin mặc định chặt; khi khác origin, allowlist cụ thể.
3. **STOMP CONNECT CSRF**: backend chỉ chấp nhận messaging session có native CSRF token hợp lệ theo security integration.
4. **Message authorization**: từ chối SEND/SUBSCRIBE không được allowlist, đặc biệt client SEND thẳng broker.
5. **Object/tenant ACL**: service/broker subscriptions không cấp quyền dựa chỉ trên `ROLE_USER`.
6. **Không side effect trước CONNECT**: transport POST không tự trở thành business mutation; business message chỉ được xử lý khi giao thức và policy cho phép.
7. **Session lifecycle + rate limits**: chống spam transport/CONNECT, tài nguyên tồn tại lâu và quyền bị thu hồi.
8. **Logging redaction/TLS**: không lộ cookie/CSRF/bearer token qua logs hoặc URL.

**Bảo vệ bù không đồng nghĩa hai cơ chế có hiệu lực hoàn toàn tương đương.** Khi bỏ CSRF ở HTTP transport POST, lớp HTTP không còn chứng minh client có token trên từng request đó. Chính sách còn lại phải chứng minh **không có thao tác nhạy cảm nào diễn ra trước khi STOMP CONNECT và authorization được kiểm tra**.

### 4.3. Origin không thay authentication

Một non-browser HTTP client có thể tự khai `Origin: https://app.example.com`. Vì thế Origin allowlist rất hữu ích chống browser-based cross-origin abuse, nhưng không phải bằng chứng ai là user hoặc admin. CORS cũng không phải server-side authorization.

### 4.4. CSRF ở CONNECT không thay quyền object

Alice gửi CONNECT hợp lệ rồi `SEND /app/orders.lookup` với `{"orderId":2002}` của Bob. Nếu application trả dữ liệu Bob vì chỉ kiểm tra role USER, đó vẫn là lỗ hổng BOLA/IDOR. HTTP CSRF, STOMP CSRF và Object ACL giải quyết các câu hỏi khác nhau.

## 5. Điều kiện tiên quyết: endpoint SockJS được tách biệt

Ví dụ đặt toàn bộ SockJS ở:

~~~text
/ws                  -- SockJS base endpoint
/ws/info             -- transport discovery
/ws/{server}/{id}/...-- SockJS transport paths
~~~

REST API được đặt ở namespace khác:

~~~text
/api/orders
/api/users
/api/admin
/api/csrf
~~~

Không đặt endpoint nghiệp vụ `POST /ws/payment` hoặc `POST /ws/admin/approve` bên trong namespace dự kiến sẽ có HTTP CSRF exception.

### 5.1. Phạm vi ngoại lệ nên được xác định bằng những gì?

Một ngoại lệ chất lượng cần xác định:

- **HTTP method**: ví dụ chính xác `POST`.
- **Đường dẫn SockJS transport**: ví dụ `/ws/{server-id}/{session-id}/xhr_send`.
- **URL normalization và context path**: dùng đúng representation path theo servlet mapping, không so khớp chuỗi thô thiếu kiểm soát.
- **Version và transport set**: chỉ các transport được client/server thực sự hỗ trợ.
- **Không có business side effects ở handler transport** trước khi STOMP security xác minh.
- **Audit/test cho các đường dẫn gần giống** để bảo đảm không miễn nhầm REST hoặc admin.

Một exception `/ws/**` có thể chấp nhận trong một số hướng dẫn framework khi namespace đó được dành **riêng** cho SockJS. Nhưng với yêu cầu hardening, một **method+path matcher hẹp hơn** dễ đánh giá phạm vi và tránh nới bảo vệ không cần thiết.

### 5.2. Biến URL không phải chứng cứ bảo mật

Các `server-id` và `session-id` trong đường dẫn SockJS là **routing identifiers**, không phải JWT hay CSRF tokens. Không tin một session ID trong URL như bằng chứng user đã authenticated. Browser có thể đoán/gửi URL; session/Origin/STOMP checks vẫn cần thiết.

## 6. Cấu hình SockJS endpoint và Origin trên Servlet

### 6.1. WebSocketMessageBrokerConfigurer

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class RealtimeSocketConfiguration implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
            // Ví dụ frontend được triển khai cùng public origin:
            // chính sách same-origin mặc định là lựa chọn cơ sở.
            .withSockJS();
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Với frontend khác origin, chỉ thêm một allowlist chính xác **sau khi xác minh transport set**:

~~~java
registry.addEndpoint("/ws")
    .setAllowedOrigins("https://app.example.com")
    .withSockJS();
~~~

**Không đặt hai registrations này đồng thời cho cùng endpoint**; đây là hai phương án triển khai. Các policy allowed origins cụ thể có thể khiến một số SockJS legacy iframe transports bị vô hiệu do giới hạn kiểm tra Origin. Hãy kiểm thử browser thật và chỉ hỗ trợ transports cần thiết.

### 6.2. Đừng tắt toàn bộ Origin checking

Phản ví dụ:

~~~java
// Không nên dùng để chữa HTTP CSRF hoặc fallback 403.
registry.addEndpoint("/ws")
    .setAllowedOrigins("*")
    .withSockJS();
~~~

Mở wildcard tăng bề mặt CSWSH trong ứng dụng session-cookie, không làm STOMP CONNECT CSRF tự hoạt động và cũng không sửa sự cố iframe CSP/X-Frame-Options.

### 6.3. HTTP transport ≠ STOMP destination

`/ws/.../xhr_send` là **HTTP transport URL**. `/app/orders.lookup` là **STOMP message destination**. Chúng được kiểm tra ở các tầng khác nhau. Một HTTP `RequestMatcher` theo `/ws` không thể thay `simpDestMatchers("/app/**")` trong messaging security.

## 7. Tạo một RequestMatcher HTTP CSRF exception hẹp

### 7.1. Vì sao cần method và path?

Nếu chỉ viết:

~~~java
// Quá rộng nếu namespace /ws/** có thêm các endpoint khác.
.csrf(csrf -> csrf.ignoringRequestMatchers("/ws/**"))
~~~

thì mọi HTTP unsafe methods khớp `/ws/**` đều có thể được bỏ kiểm tra token. Dù namespace đang riêng cho SockJS, người bảo trì sau này có thể thêm endpoint nghiệp vụ dưới `/ws` mà không nhận ra ngoại lệ đã tồn tại.

Để giảm phạm vi, ví dụ dưới đây miễn **chỉ POST đến một dạng route SockJS XHR send đã được kiểm tra**. Đây là mã minh họa cho app Spring Security Servlet với namespace `/ws` và SockJS URL pattern đã xác minh.

### 7.2. Java RequestMatcher kiểm tra chặt

~~~java
import java.util.regex.Pattern;

import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.web.util.matcher.RequestMatcher;

final class SockJsXhrSendPostMatcher implements RequestMatcher {

    // Ví dụ đặt giả định rõ:
    // /ws/{3-digit-server-id}/{session-id}/xhr_send
    private static final Pattern SOCKJS_SEND = Pattern.compile(
        "^/ws/[0-9]{3}/[A-Za-z0-9_-]{1,128}/xhr_send$"
    );

    @Override
    public boolean matches(HttpServletRequest request) {
        if (!"POST".equals(request.getMethod())) {
            return false;
        }

        // Servlet mapping thông thường; một số setup có pathInfo.
        String path = request.getServletPath();
        if (request.getPathInfo() != null) {
            path += request.getPathInfo();
        }

        return SOCKJS_SEND.matcher(path).matches();
    }
}
~~~

Các giới hạn intentional:

- Không miễn `PUT`, `PATCH` hoặc `DELETE`.
- Không miễn `POST /api/orders`, `POST /ws/admin` hay `POST /ws/123/abc/anything_else`.
- Không miễn `POST /ws/123/abc/xhr_send/extra`.
- Không khớp đường dẫn nếu server/session id vi phạm pattern.
- Giả định `server-id` là 3 chữ số và session id dùng các ký tự phù hợp; **phải xác minh thực tế**. Nếu SockJS version hoặc custom setup có format khác, matcher có thể **quá hẹp** và gây 403 chứ không phải tự mở rộng. Điều chỉnh có kiểm chứng.

**Đừng copy matcher này và mặc định mọi deployment đều có `getServletPath()` bằng toàn bộ request path.** Với context path, custom servlet mapping hoặc gateway rewrite, cần test đúng `servletPath`/`pathInfo` mà Servlet container đưa vào security chain.

### 7.3. Tại sao không dùng getRequestURI().startsWith("/ws")?

Ví dụ:

~~~java
// Anti-pattern: chỉ nhìn prefix, không xét method, context path hoặc
// các đường dẫn tương tự như /ws-admin.
return request.getRequestURI().startsWith("/ws");
~~~

Hạn chế:

- `getRequestURI()` bao gồm context path, dễ match sai.
- Prefix `/ws` có thể vô tình match `/ws-admin`.
- Mở mọi methods nếu không kiểm tra method.
- Path encodings, matrix parameters, proxy rewrites và servlet mappings có thể gây sai khác khi so khớp.
- Không chứng minh đã giới hạn vào một SockJS transport được hỗ trợ.

Giữ `StrictHttpFirewall`/path normalization policy an toàn và kiểm thử đường dẫn biến thể. Không tự decode đường dẫn nhiều lần hoặc cho encoded slash để một URL được hiểu theo hai cách.

### 7.4. Nếu thực tế có nhiều POST transports?

Không nới tất cả `/ws/**` ngay lập tức. Trước tiên xem DevTools hoặc trace staging xem request nào có HTTP POST và do SockJS tạo. Nếu có một legacy transport POST khác được sản phẩm chính thức hỗ trợ, hãy tạo **một matcher cụ thể riêng** và test negative cases cho transport đó.

Một số URL dạng `jsonp_send` có thể xuất hiện trong mô hình cũ; không cấp exception chỉ vì từng thấy tên transport trong tài liệu lịch sử. Việc mở legacy transports còn đòi đánh giá browser support, CORS, Origin, framing và cookie risks.

## 8. Gắn ngoại lệ vào HTTP SecurityFilterChain, giữ CSRF ở nơi khác

### 8.1. Cấu hình Servlet Security

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;

@Configuration
class HttpTransportSecurityConfiguration {

    @Bean
    SecurityFilterChain applicationSecurity(HttpSecurity http)
            throws Exception {
        return http
            .csrf(csrf -> csrf
                .csrfTokenRepository(
                    new HttpSessionCsrfTokenRepository()
                )
                // Chỉ miễn HTTP token cho transport đã xác minh.
                .ignoringRequestMatchers(
                    new SockJsXhrSendPostMatcher()
                )
            )
            .cors(Customizer.withDefaults())
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login").permitAll()
                .requestMatchers("/ws", "/ws/**").authenticated()
                .requestMatchers("/api/csrf").authenticated()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll()
            )
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
~~~

### 8.2. Điểm cần hiểu từ cấu hình

1. `ignoringRequestMatchers(...)` chỉ làm **HTTP CSRF validation không áp dụng** cho request khớp matcher; nó **không đặt `permitAll()`** hay bỏ authentication.
2. `/ws` và `/ws/**` vẫn được `authenticated()` bảo vệ theo mô hình session login.
3. `POST /api/orders` vẫn phải trình HTTP CSRF token hợp lệ nếu không có exception khác.
4. `HttpSessionCsrfTokenRepository` được nêu tường minh để minh họa token theo session; không có nghĩa mọi app phải override repository mặc định.
5. `cors(Customizer.withDefaults())` sử dụng CORS configuration thích hợp của ứng dụng; không tự cho mọi Origin.
6. Form login chỉ là một lựa chọn cho ví dụ; project thực cần user store, session strategy và API/login behavior tương ứng.
7. CSRF CONNECT của Spring Security Messaging là một **kiểm tra khác**, không bị bỏ chỉ vì `CsrfFilter` miễn POST vận chuyển.

### 8.3. Khi có nhiều SecurityFilterChains

Nếu app có nhiều chains cho `/api/**`, `/ws/**` và form login, **chỉ chain khớp đầu tiên** được dùng cho mỗi HTTP request. Exception phải nằm trong chain **thực sự xử lý SockJS POST**; các API business chains vẫn giữ CSRF nếu chúng dùng cookie credentials.

Không đặt một chain kiểu:

~~~java
// Sai với hệ thống chưa có thiết kế auth thay thế:
.securityMatcher("/ws/**")
.authorizeHttpRequests(auth -> auth.anyRequest().permitAll())
.csrf(csrf -> csrf.disable())
~~~

rồi tin rằng `@EnableWebSocketSecurity` đã làm mọi HTTP endpoints dưới `/ws/**` an toàn. Trước messaging còn có handshake, transport state, session cookie, Origin, resource consumption và có thể những routes khác.

### 8.4. RequestMatcher hay đường dẫn wildcard?

Có thể dùng `.ignoringRequestMatchers("/ws/**")` trong hệ thống mà namespace `/ws/**` **chỉ** dành cho SockJS, toàn bộ side effects đều diễn ra qua STOMP security và scope được bảo vệ/kiểm thử. Tuy nhiên, đây vẫn là một quyết định **rộng hơn** ví dụ matcher chỉ `POST xhr_send`. Người đọc cần nêu rõ tradeoff: dễ triển khai, nhưng bề mặt được miễn CSRF lớn hơn và dễ ảnh hưởng khi routes thay đổi.

## 9. CSRF STOMP CONNECT là một lớp bảo vệ bù thiết yếu

### 9.1. Token được gửi trong STOMP frame, không phải HTTP POST header

Sau khi SockJS tạo transport, client STOMP có thể gửi:

~~~text
CONNECT
accept-version:1.2
host:app.example.com
X-CSRF-TOKEN:<current-session-token>

^@
~~~

`^@` biểu diễn byte NUL kết thúc frame. `X-CSRF-TOKEN` là **native STOMP header** bên trong SockJS message, không phải header HTTP của `POST /ws/.../xhr_send`.

Khi `@EnableWebSocketSecurity` bật và tích hợp Spring Security Messaging phù hợp, `CsrfChannelInterceptor` có thể đối chiếu giá trị native CONNECT token với expected token/ngữ cảnh HTTP/handshake. Thiếu hoặc sai token phải làm CONNECT không được chấp nhận theo policy.

### 9.2. Bản chất khác nhau của hai token checks

| Kiểm tra | Khi nào chạy? | Token đến từ đâu? | Sau khi miễn transport POST còn không? |
| --- | --- | --- | --- |
| HTTP `CsrfFilter` | Mỗi HTTP unsafe request được CSRF policy bao phủ | HTTP header/parameter theo handler/repository | **Không** với đúng request POST exempt |
| STOMP `CsrfChannelInterceptor` | Inbound STOMP CONNECT | Native STOMP header + expected token/context | **Có**, nếu Messaging security được bật/đấu nối đúng |
| AuthorizationManager | Inbound MESSAGE/SUBSCRIBE/controls | Principal/authorities/destination | **Có** nếu message security configured |
| Business ACL | Trong handler/service/publisher | Principal + object/tenant data | **Phải tự triển khai** |

**Tránh lời khẳng định sai:** “Bỏ CSRF HTTP cho transport tương đương bảo vệ CSRF y hệt trên mọi POST”. Lớp bù hoạt động ở **điểm khác** trong protocol; test phải chứng minh không có business mutations trước CONNECT và không bypass khi tạo nhiều POST transport requests.

### 9.3. HTTP endpoint cấp token cho frontend

Một controller minh họa:

~~~java
import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CsrfTokenEndpoint {

    @GetMapping("/api/csrf")
    ResponseEntity<Map<String, String>> token(
        @RequestAttribute("_csrf") CsrfToken csrf
    ) {
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                "headerName", csrf.getHeaderName(),
                "token", csrf.getToken()
            ));
    }
}
~~~

`/api/csrf` **do ứng dụng tạo**; Spring Boot không tự có URL này. Endpoint cần authentication/session đúng mô hình, không cache response chứa token ở shared CDN, và HTTP CORS chỉ cho frontend được phép đọc token khi khác origin.

Nếu dùng custom `CsrfTokenRepository`, deferred generation hoặc masked token request handler, phải test đúng giá trị được endpoint expose so với giá trị STOMP CONNECT cần trình bày. Không giả định mọi repository có session binding giống `HttpSessionCsrfTokenRepository`.

### 9.4. Gửi native token qua @stomp/stompjs

~~~javascript
import SockJS from "sockjs-client";
import { Client } from "@stomp/stompjs";

async function startRealtime() {
  const response = await fetch("/api/csrf", {
    credentials: "same-origin"
  });

  if (!response.ok) {
    throw new Error("Không lấy được CSRF token của phiên");
  }

  const { headerName, token } = await response.json();

  const client = new Client({
    webSocketFactory: () =>
      new SockJS("/ws"),

    // Đây là STOMP CONNECT header, không phải HTTP xhr_send header.
    connectHeaders: {
      [headerName]: token
    },

    onConnect: () => {
      client.subscribe(
        "/user/queue/order-results",
        message => console.log(message.body)
      );
    },

    onStompError: frame => {
      console.error("STOMP ERROR:", frame.headers.message);
    }
  });

  client.activate();
  return client;
}
~~~

Mã dùng public same-origin proxy như một giả định. `new SockJS("/ws")` và `fetch("/api/csrf")` cùng public origin nên cookie session thường được gửi theo browser cookie policy. Nếu deployment khác origin, cần URL đầy đủ, `credentials: "include"` cho token endpoint, CORS cho HTTP token response, SockJS allowed-origin policy và cookie configuration tương ứng.

### 9.5. Nguyên tắc khi reconnect/logout

Một client lấy token một lần có thể auto-reconnect sau khi session bị rotate, user logout/login lại hoặc token expected bị thay đổi. Dùng hook `beforeConnect` để fetch token lại theo phiên hiện tại nếu thư viện hỗ trợ, và dừng/re-auth khi HTTP endpoint trả 401.

Không dùng `CSRF token` như access token; không gửi token qua query string; không log raw CONNECT headers.

## 10. Message authorization vẫn bắt buộc trên CONNECTED sessions

### 10.1. @EnableWebSocketSecurity và deny-by-default

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

@Configuration
@EnableWebSocketSecurity
class RealtimeMessageSecurity {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
        MessageMatcherDelegatingAuthorizationManager.Builder messages
    ) {
        return messages
            // CONNECT và control messages thiếu destination.
            .nullDestMatcher().authenticated()

            // Không SUBSCRIBE vào application destinations.
            .simpSubscribeDestMatchers("/app/**").denyAll()

            // Chỉ cho các destinations được công bố rõ.
            .simpSubscribeDestMatchers(
                "/user/queue/order-results",
                "/topic/public"
            ).authenticated()

            // Inbound SEND thường map thành SimpMessageType.MESSAGE.
            .simpDestMatchers("/app/orders.lookup").hasRole("USER")

            // Chặn SEND tới broker /topic, /queue và các
            // SUBSCRIBE khác chưa được phê duyệt.
            .simpTypeMatchers(
                SimpMessageType.MESSAGE,
                SimpMessageType.SUBSCRIBE
            ).denyAll()

            .anyMessage().denyAll()
            .build();
    }
}
~~~

`@EnableWebSocketSecurity` và `AuthorizationManager<Message<?>>` là **messaging security**, khác `SecurityFilterChain`. Không cài trùng CSRF interceptor của framework chỉ để “bù”; dùng đúng tích hợp được hỗ trợ và kiểm thử CONNECT.

### 10.2. Vì sao chặn client SEND tới broker?

Nếu client được phép:

~~~text
SEND
destination:/topic/admin
content-type:application/json

{"message":"Thông báo hệ thống giả mạo"}
^@
~~~

một broker có thể phát payload cho subscribers mà không đi qua `@MessageMapping`/service. Rule trên chỉ cho SEND tới `/app/orders.lookup` theo role, còn direct SEND tới `/topic/**` bị fallback deny.

### 10.3. SUBSCRIBE không có quyền mặc định với object

Một user Alice có thể thử `SUBSCRIBE /topic/orders/2002` dù order 2002 thuộc Bob. `authenticated()` hoặc `hasRole("USER")` không đủ kiểm tra quyền với từng ID. Nếu mở topic riêng theo object, cần dynamic authorization theo principal/order/tenant và thu hồi subscriptions khi quyền thay đổi. Có thể ưu tiên user destinations cho phản hồi riêng.

### 10.4. Không xử lý business frames trước CONNECT hợp lệ

Nếu một SockJS POST được miễn HTTP CSRF, rồi client gửi STOMP SEND trước khi có STOMP CONNECTED, backend phải **không xử lý** lệnh nghiệp vụ. Đây là một bất biến bảo mật cần kiểm thử, không chỉ một kỳ vọng từ thứ tự frame mà client “ngoan” thường gửi.

## 11. Service ACL: ngoại lệ HTTP không cho phép business mutation trái quyền

Ví dụ lệnh:

~~~text
SEND
destination:/app/orders.lookup
content-type:application/json

{"orderId":2002}
^@
~~~

Handler:

~~~java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Controller;

record OrderLookup(long orderId) {}
record OrderView(long orderId, String state) {}

interface OrderQueryService {
    // Implementation phải kiểm tra quyền trên orderId/tenant thật.
    OrderView findVisibleOrder(String username, long orderId);
}

@Controller
class OrderRealtimeController {

    private final OrderQueryService orders;
    private final SimpMessagingTemplate messaging;

    OrderRealtimeController(
        OrderQueryService orders,
        SimpMessagingTemplate messaging
    ) {
        this.orders = orders;
        this.messaging = messaging;
    }

    @MessageMapping("/orders.lookup")
    void lookup(@Payload OrderLookup input, Principal principal) {
        OrderView order = orders.findVisibleOrder(
            principal.getName(), input.orderId()
        );

        messaging.convertAndSendToUser(
            principal.getName(),
            "/queue/order-results",
            order
        );
    }
}
~~~

Service phải tra dữ liệu server-side và xác nhận Alice có quyền truy cập order được yêu cầu. Không lấy `username` hay `tenantId` trong JSON từ client làm bằng chứng quyền.

**Ba lần kiểm tra khác nhau:**

1. HTTP POST vận chuyển có đúng endpoint, Origin/auth/session và exception hẹp?
2. STOMP CONNECT có token/principal hợp lệ và SEND có destination/role được phép?
3. Object/tenant ACL có cho Alice nhìn thấy order ID 2002 không?

Một request có thể vượt (1), (2) rồi vẫn phải bị từ chối ở (3). Đó là hành vi an toàn.

## 12. Origin, CORS và cookie chính sách thay thế cần xác minh

### 12.1. Origin allowlist là một phần phòng vệ chống CSWSH

Trong browser, script từ một origin lạ có thể thử tạo WebSocket/SockJS requests. Nếu browser tự gắn session cookie và backend cho phép kết nối cross-origin, nguy cơ Cross-Site WebSocket Hijacking tăng.

Giữ same-origin policy mặc định khi frontend và backend cùng public origin, hoặc explicit allowlist đúng frontend tin cậy khi khác origin. Không mở wildcard chỉ vì POST transport đã được miễn HTTP CSRF.

### 12.2. CORS của XHR fallback khác native WebSocket

- SockJS XHR POST/GET khi cross-origin có thể chịu HTTP CORS, preflight và credentialed requests.
- Native WebSocket handshake không dùng Fetch CORS preflight OPTIONS theo cách XHR dùng.
- `Access-Control-Allow-Origin: *` không hợp lệ để browser đọc credentialed HTTP responses; phải có allowlist origin cụ thể và ACAC nếu dùng cookies.
- CORS không thay authentication và không làm request cross-origin không thể được **gửi** trong mọi trường hợp.
- Nhiều nơi cùng tự thêm ACAO (gateway, SockJS, CorsFilter) có thể khiến response trùng header hoặc sai `Vary`.

Một “CORS error” ở DevTools trước CONNECT phải được phân biệt với STOMP `ERROR` sau khi transport đã mở.

### 12.3. SameSite không phải same-origin

`https://app.example.com` và `https://api.example.com` khác origin dù có thể cùng site. Cookie `SameSite=Lax` có thể được gửi trong các ngữ cảnh same-site, và những subdomains kém tin cậy vẫn đáng xem xét.

Giữ `Secure`, `HttpOnly`, `SameSite`/Domain/Path phù hợp; không nới cookie policy bừa bãi chỉ để SockJS gửi được transport requests.

### 12.4. HTTP Origin thiếu hoặc bị giả

Non-browser clients có thể tự khai Origin. Nếu sản phẩm chỉ phục vụ browser, có thể từ chối các Origin không hợp lệ/không có theo policy. Nếu có non-browser clients chính thức, cần authentication và allowance riêng, không coi Origin là danh tính.

Một HTTP POST đơn giản từ site lạ có thể tới server dù browser không cho script đọc response. **Vì vậy không dựa vào CORS như lớp bù duy nhất cho HTTP CSRF exemption.**

## 13. SockJS iframe fallback và security headers

Một số legacy SockJS transports cần iframe. Điều đó tạo thêm ranh giới với `X-Frame-Options` và Content Security Policy (CSP).

### 13.1. X-Frame-Options DENY và SAMEORIGIN

Spring Security thường mặc định:

~~~http
X-Frame-Options: DENY
~~~

Chính sách này chống clickjacking, nhưng cũng chặn legacy SockJS iframe document được nhúng. Nếu phải dùng iframe fallback và frontend + tài liệu iframe cùng origin, có thể cần `SAMEORIGIN` trên đúng response:

~~~http
X-Frame-Options: SAMEORIGIN
~~~

**SAMEORIGIN xét scheme + host + port**, không phải cùng registrable domain. Trang `https://app.example.com` không được frame iframe `https://api.example.com` chỉ nhờ SAMEORIGIN; CORS cũng không biến chúng thành cùng origin.

### 13.2. CSP phải được xét ở cả parent và iframe

- CSP `frame-src` trên parent: parent được nhúng URL iframe nào?
- CSP `frame-ancestors` trên iframe response: origin parent nào được phép frame document?
- CSP `script-src` trong iframe: thư viện SockJS client có tải được không?
- CSP `connect-src` trên trang tạo kết nối: URL HTTP/WSS có được phép không?

Nếu sản phẩm cần legacy iframe, ưu tiên phục vụ SockJS iframe qua **cùng public origin/reverse proxy**, giữ XFO/CSP cho các trang khác nghiêm ngặt. Một `SecurityFilterChain` riêng cho SockJS có thể sử dụng `headers.frameOptions(frame -> frame.sameOrigin())` đúng phạm vi; nhưng **không nới toàn bộ admin pages** chỉ vì SockJS.

### 13.3. Allowed origins có thể vô hiệu iframe transports

Khi Spring SockJS có explicit allowed-origin restrictions, một số iframe-based transports không thể xác minh Origin như yêu cầu và có thể bị framework loại bỏ. Không giả định `setAllowedOrigins("https://app.example.com")` sẽ làm mọi iframe legacy hoạt động; kiểm tra phiên bản và transport được hỗ trợ. Việc HTTP CSRF exception **không tự bật** iframe.

### 13.4. Không nhầm framing với HTTP CSRF exemption

Nếu browser báo “Refused to frame due to X-Frame-Options: DENY”, điều đó xảy ra trước STOMP CONNECT. Chỉnh `csrf.ignoringRequestMatchers(...)` **không sửa được** XFO/CSP. Ngược lại, `frameOptions.sameOrigin()` **không sửa được** HTTP `CsrfFilter` từ chối `POST /xhr_send`.

## 14. Khi dùng bearer token ở STOMP CONNECT

Một SPA không có HTTP session cookie có thể gửi:

~~~text
CONNECT
Authorization:Bearer <access-token>

^@
~~~

Nhưng đây là kiến trúc **khác** session-based + CSRF token:

- HTTP `/ws authenticated()` sẽ chặn handshake nếu browser không có credentials ở HTTP layer.
- Bearer native header **không được Spring tự xác minh** nếu không có custom interceptor/token verifier.
- `@EnableWebSocketSecurity` có thể vẫn yêu cầu CSRF token tại STOMP CONNECT; bearer access token **không tự tắt** CSRF.
- Nếu không có ambient session cookies, threat model CSRF khác; chính sách cho CONNECT cần được thiết kế rõ theo framework version, không suy luận từ tên “JWT”.
- HTTP transport POST được exempt **không** cấp quyền cho một anonymous connection.
- Cần rate limit/timeout cho những sockets mở handshake nhưng chưa CONNECT authenticated.

### 14.1. Skeleton authentication trên CONNECT

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageHeaderAccessor;
import org.springframework.security.core.Authentication;

interface VerifiedTokenService {
    // Verifier phải kiểm tra signature, iss, aud, exp, scopes, revoke.
    Authentication authenticateBearer(String nativeHeader);
}

final class BearerConnectInterceptor implements ChannelInterceptor {

    private final VerifiedTokenService verifier;

    BearerConnectInterceptor(VerifiedTokenService verifier) {
        this.verifier = verifier;
    }

    @Override
    public Message<?> preSend(Message<?> message, MessageChannel channel) {
        StompHeaderAccessor accessor =
            MessageHeaderAccessor.getAccessor(
                message, StompHeaderAccessor.class
            );

        if (accessor != null
                && StompCommand.CONNECT.equals(accessor.getCommand())) {
            Authentication verified = verifier.authenticateBearer(
                accessor.getFirstNativeHeader("Authorization")
            );

            if (verified == null || !verified.isAuthenticated()) {
                throw new org.springframework.security.authentication
                    .BadCredentialsException("Invalid token");
            }

            accessor.setUser(verified);
        }
        return message;
    }
}
~~~

Đây là skeleton, chưa có registration/order, duplicate header handling, expiry/revocation hoặc verification implementation. Nếu dùng custom CONNECT authentication interceptor, nó phải được đăng ký **trước Spring Security message authorization** cần principal và phải test với CONNECT đúng/sai. Bài không khuyên áp dụng bearer-only để “tránh” HTTP CSRF exemption khi hệ thống vốn có session cookie.

## 15. Kiểm thử unit cho RequestMatcher: chặn ngoại lệ lan rộng

### 15.1. Những ca matcher phải pass

Với `SockJsXhrSendPostMatcher` ở mục 7, test trực tiếp `matches(...)` bằng mock HTTP request. Mã minh họa:

~~~java
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;

class SockJsXhrSendPostMatcherTest {

    private final SockJsXhrSendPostMatcher matcher =
        new SockJsXhrSendPostMatcher();

    private MockHttpServletRequest request(
        String method, String servletPath
    ) {
        MockHttpServletRequest req =
            new MockHttpServletRequest();
        req.setMethod(method);
        req.setServletPath(servletPath);
        return req;
    }

    @Test
    void matchesOnlyApprovedSockJsPost() {
        assertTrue(matcher.matches(
            request("POST", "/ws/173/abcXYZ/xhr_send")
        ));
        assertFalse(matcher.matches(
            request("GET", "/ws/173/abcXYZ/xhr_send")
        ));
        assertFalse(matcher.matches(
            request("POST", "/ws/173/abcXYZ/xhr_streaming")
        ));
        assertFalse(matcher.matches(
            request("POST", "/ws/173/abcXYZ/xhr_send/extra")
        ));
        assertFalse(matcher.matches(
            request("POST", "/ws/admin/delete")
        ));
        assertFalse(matcher.matches(
            request("POST", "/api/orders")
        ));
        assertFalse(matcher.matches(
            request("DELETE", "/ws/173/abcXYZ/xhr_send")
        ));
        assertFalse(matcher.matches(
            request("POST", "/ws-admin/173/abcXYZ/xhr_send")
        ));
        assertFalse(matcher.matches(
            request("POST", "/ws/173/abcXYZ/jsonp_send")
        ));
    }
}
~~~

Đây là unit test của matcher logic **trong điều kiện servletPath giả định**. Khi deploy sau context path/custom Servlet mapping/proxy, cần kiểm thử integration path extraction thật. Một mock đúng không chứng minh SockJS session transport vận hành được.

### 15.2. Test format route khác

Thử các case:

- Một URL không có session id.
- Server id không đúng 3 số (nếu policy quy định 3 số).
- Session id có slash, dấu chấm hoặc ký tự encoding bất thường.
- Một path có double slash hoặc semicolon/matrix params.
- Một path rewrite sau gateway.
- `contextPath` và `pathInfo` khác nhau giữa môi trường.
- HTTP method viết khác chuẩn hoặc method spoofing.
- Request có trailing slash ngoài dự kiến.

Mục đích là đảm bảo **fail closed** khi URL không thuộc transport được nhận diện. Nếu một legitimate client bị 403 do route format thực sự khác giả định, mở thêm **một pattern đã kiểm chứng** và test âm tương ứng, không mở wildcard vô điều kiện.

## 16. Kiểm thử HTTP SecurityFilterChain: các API khác vẫn có CSRF

### 16.1. Ma trận HTTP request

| Ca | HTTP request | Cookie/user | CSRF HTTP token | Mong đợi |
| --- | --- | --- | --- | --- |
| H1 | `POST /ws/173/abcXYZ/xhr_send` | Alice authenticated | Thiếu | Không bị **CsrfFilter** từ chối chỉ vì thiếu token; handler SockJS có thể trả lỗi khác nếu session/frames sai |
| H2 | `POST /api/orders` | Alice authenticated | Thiếu | **403 bởi HTTP CSRF** |
| H3 | `POST /api/orders` | Alice authenticated | Đúng | Qua CSRF layer, tiếp tục authorization/business |
| H4 | `PUT /api/orders/1001` | Alice authenticated | Thiếu | 403 theo HTTP CSRF |
| H5 | `DELETE /api/orders/1001` | Alice authenticated | Thiếu | 403 theo HTTP CSRF |
| H6 | `POST /ws/admin/delete` | Alice authenticated | Thiếu | Không được exempt, tiếp tục HTTP CSRF |
| H7 | `POST /ws/173/abcXYZ/other_transport` | Alice | Thiếu | Không được exempt |
| H8 | `POST /ws/173/abcXYZ/xhr_send` | Không authenticated | Bất kỳ | Không được tự có quyền transport/business do exemption |
| H9 | `GET /ws/info` | Theo auth policy | Không cần | HTTP GET thường không bị CSRF check, nhưng auth và Origin vẫn áp dụng |
| H10 | `POST /ws/173/abcXYZ/xhr_send/extra` | Alice | Thiếu | Không được exempt |

**H1 cần diễn giải chính xác:** request có thể trả 404/400/403 vì **SockJS session chưa tồn tại**, Origin sai, auth, routing hoặc content malformed. Đừng assert “phải HTTP 200” chỉ để chứng minh CsrfFilter exemption; test matcher riêng và một kịch bản SockJS POST hợp lệ end-to-end.

### 16.2. MockMvc kiểm tra REST còn được bảo vệ

Ví dụ skeleton:

~~~java
import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

// Với MockMvc đã được @AutoConfigureMockMvc gắn Spring Security:
mockMvc.perform(
        post("/api/orders")
            .with(user("alice").roles("USER"))
            .contentType("application/json")
            .content("{}")
    )
    .andExpect(status().isForbidden());
~~~

Trong test suite thật, cần controller/API route phù hợp và exception handling rõ. Nếu request cũng bị authorization deny hoặc validation 403, một assertion status 403 **chưa chứng minh CSRF là nguyên nhân**. Nên kết hợp unit matcher tests, test với/không có token và logs/filter diagnostics trong môi trường test.

### 16.3. Đừng dùng trạng thái 200 làm điều kiện bảo mật duy nhất

Một HTTP POST SockJS transport được miễn CSRF layer không nhất thiết cần trả 200 trong mọi hoàn cảnh. Nếu session ID không tồn tại, server từ chối là đúng. Điều quan trọng là:

1. Chỉ đúng request transport được exempt khỏi **HTTP CSRF validation**.
2. HTTP authentication/Origin policy vẫn chạy.
3. STOMP CONNECT vẫn đòi token và principal.
4. SEND/SUBSCRIBE trái quyền không tạo side effects/dữ liệu lộ.
5. Không có đường vòng qua raw POST đến một controller nghiệp vụ.

## 17. Kiểm thử end-to-end SockJS và STOMP

### 17.1. Không dùng native WebSocket test thay cho fallback

Một `WebSocketStompClient` dùng `StandardWebSocketClient` có thể kiểm tra STOMP qua native WebSocket. Nhưng nó không tự chứng minh XHR `POST /xhr_send` được xử lý đúng. Để kiểm thử ngoại lệ HTTP, cần một test client/browser thực sự chọn **XHR fallback**.

Với SockJS JavaScript client, một cách thử có điều kiện theo phiên bản thư viện:

~~~javascript
import SockJS from "sockjs-client";
import { Client } from "@stomp/stompjs";

const client = new Client({
  webSocketFactory: () =>
    new SockJS("/ws", null, {
      transports: ["xhr-polling"]
    }),
  connectHeaders: {
    "X-CSRF-TOKEN": csrfToken
  }
});

client.activate();
~~~

`csrfToken` cần được lấy đúng phiên trước CONNECT. Tùy browser/SockJS version, transport option có thể khác; xác minh qua DevTools rằng **POST `/xhr_send` thực sự xuất hiện**. Test ở Chrome với native WebSocket thành công không kiểm thử exception đó.

### 17.2. Kịch bản E2E positive

~~~text
Given:
  - Frontend và SockJS endpoint qua public same-origin proxy.
  - HTTP session Alice đã đăng nhập.
  - GET /api/csrf cấp token hợp lệ cho session Alice.
  - SockJS client được ép/chọn xhr-polling có support.
  - HTTP CSRF chỉ ignore POST .../xhr_send đã xác minh.
  - @EnableWebSocketSecurity và message AuthorizationManager đang bật.

When:
  1) Client GET /ws/info và tạo SockJS transport.
  2) DevTools ghi nhận POST /ws/{server}/{session}/xhr_send.
  3) HTTP request transport được xử lý mà không đòi
     HTTP X-CSRF-TOKEN header ở riêng POST đó.
  4) Client gửi STOMP CONNECT kèm native X-CSRF-TOKEN hợp lệ.
  5) Nhận STOMP CONNECTED.
  6) SUBSCRIBE /user/queue/order-results.
  7) SEND /app/orders.lookup với order của Alice.

Then:
  - STOMP CONNECTED với đúng principal Alice.
  - Lệnh nghiệp vụ chỉ thực hiện sau CONNECT.
  - Dữ liệu nhận đúng user và object đã được phép.
  - /api/orders vẫn cần HTTP CSRF cho unsafe methods.
~~~

### 17.3. Negative E2E quan trọng

| Ca | Thay đổi so với positive | Kết quả cần xác minh |
| --- | --- | --- |
| N1 | Bỏ native CSRF token ở CONNECT | Không CONNECTED; không business side effect |
| N2 | Token CONNECT sai hoặc token phiên Bob | Không CONNECTED theo expected token/session policy |
| N3 | HTTP POST xhr_send không có Cookie/auth | Không được xử lý như một authenticated STOMP session |
| N4 | Origin từ website không tin cậy với Cookie hợp lệ | HTTP/SockJS Origin policy chặn theo thiết kế |
| N5 | STOMP SEND trực tiếp `/topic/admin` | Bị message authorization từ chối |
| N6 | Alice lookup order Bob | Service/object ACL từ chối, không data leak |
| N7 | SUBSCRIBE topic riêng của Bob | Bị subscription ACL từ chối |
| N8 | POST giả ở `/api/orders` thiếu HTTP CSRF | REST CSRF vẫn từ chối |
| N9 | POST giả gần giống `/ws/173/abcXYZ/xhr_send/extra` | Không được CSRF exception match |
| N10 | POST `/ws/admin/delete` thiếu CSRF | Không lọt vào ngoại lệ transport |
| N11 | CONNECT trước rồi logout/thu hồi quyền | Không tiếp tục nhận dữ liệu nhạy cảm trái quyền |
| N12 | Spam nhiều CONNECT/POST transport malformed | Rate limit/timeout/quotas có hiệu lực |

**Test âm cần chứng minh không rò rỉ dữ liệu và không có side effect**, không chỉ quan sát STOMP `ERROR`. Một lỗi xuất hiện sau khi server đã publish dữ liệu Bob vẫn là thất bại bảo mật.

### 17.4. Kiểm tra client ngoài browser

Non-browser clients có thể tự đặt HTTP Origin/Cookie headers và gửi malformed payloads. Đây là lý do không dùng “Origin trông đúng” hoặc “CORS đã bật” làm authentication. Test còn phải kiểm tra Spring Security principal, token verifier hoặc session authentication và message ACL.

## 18. HTTP CORS/CSRF và iframe fallback trong cùng một ứng dụng

SockJS chọn nhiều transports, nên có thể gặp các lỗi bảo mật ở **những nơi khác nhau**.

### 18.1. XHR fallback

XHR HTTP `POST /xhr_send` có thể chịu:

- HTTP authentication.
- HTTP `CsrfFilter` nếu không exempt.
- HTTP CORS/OPTIONS nếu khác origin.
- Cookie SameSite/credentials rules.
- Reverse proxy path rewrites.

Exception chỉ dành cho HTTP CSRF không sửa CORS hoặc cookie.

### 18.2. Legacy iframe fallback

Iframe transport có thể cần tài liệu iframe từ SockJS endpoint. Browser kiểm tra:

- `X-Frame-Options: DENY` hoặc `SAMEORIGIN` trên iframe response.
- CSP `frame-ancestors` trên iframe.
- CSP `frame-src` trên trang cha.
- CSP `script-src` cho SockJS client library.
- Same-origin relation giữa parent và iframe.

Đừng nới `X-Frame-Options` toàn cục chỉ vì một lỗi XHR POST 403; đây là hai lỗi ở hai tầng. Nếu iframe thật sự cần SAMEORIGIN, scope headers hẹp theo resource và giữ DENY cho trang nhạy cảm. Một số explicit allowed-origins policies trong Spring SockJS có thể vô hiệu legacy iframe transports; cần test version/transport.

### 18.3. Native WebSocket

Một HTTP GET Upgrade bị chặn bởi TLS, CSP `connect-src`, proxy hoặc Origin không liên quan `POST /xhr_send` CSRF exception. Nếu native WebSocket chạy tốt nhưng XHR fallback 403, thường cần kiểm tra HTTP transport/request matcher chứ không sửa message authorization trước.

## 19. Reverse proxy, context path, load balancer và URL matching

### 19.1. Proxy có thể đổi public path

Ví dụ:

~~~text
Browser: POST https://app.example.com/realtime/ws/173/abc/xhr_send
Proxy:   POST http://spring:8080/ws/173/abc/xhr_send
Spring:  servletPath="/ws/173/abc/xhr_send"
~~~

Matcher trong ví dụ `SockJsXhrSendPostMatcher` dùng **Servlet path sau proxy**, không phải browser URL. Nếu proxy không strip `/realtime`, servletPath có thể khác và matcher không khớp. Điều đó nên dẫn tới **403 fail closed**, nhưng sản phẩm sẽ bị lỗi fallback. Hãy xác minh actual request attributes trên staging và sửa matcher có kiểm soát.

Không tự ghép `X-Forwarded-Prefix` do client gửi vào path matcher nếu không có trusted proxy boundary.

### 19.2. Shared session store và affinity

SockJS HTTP transports có thể tạo nhiều requests cho cùng phiên. Khi load balancer phân phối chúng qua các backend nodes, cần session/transport state nhất quán theo architecture, hoặc sticky routing phù hợp. Sai state có thể tạo 404/403 không liên quan HTTP CSRF.

Nếu CSRF repository theo HTTP session, request lấy token và SockJS handshake phải dùng ngữ cảnh session tương thích. Không “sửa” mismatch bằng wildcard exception cho toàn API.

### 19.3. Giới hạn tài nguyên đặc biệt quan trọng khi miễn transport POST

Dù STOMP CONNECT CSRF ngăn business actions, attacker vẫn có thể cố dùng HTTP transport layer để:

- Tạo nhiều phiên SockJS chưa CONNECT.
- Spam POST malformed và chiếm CPU/parser memory.
- Duy trì streaming connections lâu.
- Tạo hàng nghìn subscriptions sau khi CONNECT nếu thiếu quotas.
- Flood backend bằng retries hoặc reconnect storm.

Áp dụng limits về concurrent sessions, payload size, headers, heartbeat/idle timeout, rate per origin/user/IP và quotas của message broker. Logging raw frames có thể lộ CSRF/bearer token, nên cần redact.

## 20. Khi dùng Reactive/WebFlux: không sao chép Servlet exception

Spring WebFlux native WebSocket sử dụng `WebSocketHandler`/`WebSocketSession` và Spring Security reactive `ServerHttpSecurity`. Nó **không mặc nhiên** có Spring Servlet SockJS `withSockJS()`/`@EnableWebSocketMessageBroker` và `CsrfChannelInterceptor` cho STOMP CONNECT.

### 20.1. Nếu chỉ dùng native WebFlux WebSocket

Có thể bảo vệ HTTP handshake:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveHandshakeSecurity {

    @Bean
    SecurityWebFilterChain securityChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/ws").authenticated()
                .anyExchange().denyAll())
            .build();
    }
}
~~~

Code trên không tạo SockJS XHR POST transport, không kiểm tra Origin thay app và không tự phân quyền native WebSocket text/binary messages. Không có lý do miễn HTTP CSRF cho một `/xhr_send` route không tồn tại.

### 20.2. Nếu có Reactive HTTP fallback tự thiết kế

Nếu một giải pháp khác dùng HTTP POST để vận chuyển realtime messages trên WebFlux:

- Dùng **Reactive `ServerWebExchangeMatcher`/`ServerHttpSecurity`** đúng phiên bản, không copy Servlet `RequestMatcher`.
- Xác định chính xác POST transport paths và side effects.
- Có authentication, Origin/same-site policy, token/first-message security và message ACL tương ứng.
- Không cho business actions trước khi xác thực protocol.
- Test với `WebTestClient` và client transport thật.
- Đánh giá CSP/framing và cookie rules nếu có iframe.

Không tuyên bố framework tự có STOMP CONNECT CSRF cho một JSON-first-message protocol.

### 20.3. Per-message authorization trong native WebFlux

~~~java
import java.security.Principal;

import reactor.core.publisher.Mono;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.reactive.socket.WebSocketHandler;

interface NativeRealtimeService {
    Mono<Void> authorizeAndHandle(
        Principal principal, String messageText
    );
}

class SecureReactiveHandler {

    static WebSocketHandler create(NativeRealtimeService service) {
        return session -> session.getHandshakeInfo()
            .getPrincipal()
            .switchIfEmpty(Mono.error(
                new AccessDeniedException("Unauthenticated")))
            .flatMap(principal ->
                session.receive()
                    .concatMap(frame ->
                        service.authorizeAndHandle(
                            principal, frame.getPayloadAsText()
                        ))
                    .then()
            );
    }
}
~~~

Đây là skeleton minh họa, chưa có origin guard, handler mapping, outbound sending, backpressure hoặc JSON schema validation. Điểm cần nhớ là **bảo vệ từng message** không tự có chỉ vì HTTP handshake được authenticated.

## 21. Những lỗi triển khai thường gặp

| Triệu chứng | Nguyên nhân khả dĩ | Cách chẩn đoán |
| --- | --- | --- |
| Native WebSocket hoạt động, XHR fallback POST 403 | HTTP CsrfFilter chặn transport POST | Network method/path, CSRF logs, matcher |
| Thêm exception `/ws/**` rồi API mới dưới `/ws/admin` mất CSRF | Scope quá rộng | Đổi matcher method+exact transport path, regression tests |
| Matcher POST xhr_send không bao giờ match | Proxy/context path/servletPath khác giả định | In request test, xem servletPath/pathInfo thật |
| Matcher match route business | Namespace bị dùng chung/pattern sai | Tách namespaces, tăng negative tests |
| XHR POST qua HTTP CSRF nhưng CONNECT vẫn lỗi | CSRF STOMP CONNECT thiếu/sai | Native STOMP headers và expected-token context |
| CONNECTED nhưng user xem order khác | Thiếu business object ACL | Kiểm tra principal, tenant, order ownership |
| HTTP POST xhr_send thiếu Cookie vẫn được handler xử lý | Auth chain chưa đúng | Kiểm tra SecurityFilterChain order và authenticated rule |
| Site lạ kết nối được | Origin allowlist rộng/missing | Test với session hợp lệ từ origin không tin cậy |
| Browser báo CORS trên XHR | ACAO/ACAC/OPTIONS/gateway | HTTP CORS response, không sửa CSRF matcher trước |
| Browser báo frame blocked | XFO/CSP legacy iframe | Iframe response và parent CSP |
| CONNECT native thiếu CSRF nhưng pass | Security Messaging chưa bật/không đúng context | Kiểm tra @EnableWebSocketSecurity và test negative |
| JWT CONNECT bearer đúng nhưng principal null | Custom interceptor sai thứ tự | setUser sau verify, order trước message authorization |
| SockJS /info trả 302 login | HTTP auth chưa có cookie hoặc chain phù hợp | Login, cookie scope, session |
| GET /ws/info OK, POST xhr_send 404 | Session ID/transport state không tồn tại | Dùng SockJS client thật, multi-node routing |
| REST POST thiếu CSRF nhưng vẫn 200 | CSRF bị disable toàn cục hoặc exception rộng | Regression test REST POST không token |
| Token trả bởi /api/csrf nhưng CONNECT mismatch | Session đổi/repository/handler khác | Kiểm tra đúng session, masking/deferred token |
| Reconnect liên tục POST với token cũ | Session/token rotation | beforeConnect refresh, stop retry khi revoked |
| Gateway xóa/đổi Origin | Proxy config/header ownership | Kiểm tra received Origin và trusted proxy |
| HTTP logs chứa tokens | Raw headers/frames được ghi | Redact Cookie/Authorization/X-CSRF-TOKEN |
| WebFlux không có xhr_send | Dùng native WebFlux, không có Servlet SockJS fallback | Không áp dụng exception theo bài |
| Sau logout socket vẫn nhận message | Missing session revocation/ACL revalidation | Close connections, kiểm tra quyền trước publish |

### 21.1. Luồng debug

~~~mermaid
flowchart TD
    A["Realtime thất bại"] --> B{"Transport được chọn?"}
    B -- "Native WebSocket" --> C["HTTP Upgrade / Origin / Cookie / CSP / TLS"]
    B -- "SockJS XHR" --> D{"HTTP POST xhr_send có bị CSRF chặn?"}
    B -- "Legacy iframe" --> E["XFO/CSP framing và library"]
    D -- "Có" --> F["So matcher method+path; giữ REST CSRF"]
    D -- "Không" --> G["Auth, Origin, CORS, SockJS session state"]
    C --> H{"STOMP CONNECTED?"}
    E --> H
    F --> H
    G --> H
    H -- "Không" --> I["Native CSRF CONNECT, Principal, token verifier"]
    H -- "Có" --> J["SEND/SUBSCRIBE ACL, object ownership, outbound routing"]
~~~

Chỉ thực hiện exemption khi xác định rõ HTTP `CsrfFilter` đang từ chối một SockJS transport POST hợp lệ. Nếu vấn đề là handshake auth hoặc Origin, exception CSRF không phải lời giải.

## 22. Checklist review trước khi mở ngoại lệ

- [ ] Xác nhận SockJS thực tế chọn HTTP POST fallback, không chỉ native WebSocket.
- [ ] Xác nhận request bị Servlet `CsrfFilter` từ chối, không phải CORS/auth/proxy/handler.
- [ ] Chỉ exempt **HTTP method + transport path** đã được quan sát và hỗ trợ.
- [ ] Namespace SockJS tách biệt hoàn toàn với REST/form/business actions.
- [ ] Matcher fail closed với malformed paths, path encoding, prefix collisions và context path.
- [ ] Không dùng `http.csrf().disable()` cho toàn ứng dụng.
- [ ] `POST /api/**` và các unsafe methods vẫn bị HTTP CSRF kiểm tra khi dùng cookie credentials.
- [ ] SockJS transport requests vẫn phải qua HTTP authentication và authorization thích hợp.
- [ ] WebSocket/SockJS Origin allowlist hẹp, không dùng wildcard để che lỗi CSRF.
- [ ] Không dựa vào CORS đơn lẻ để ngăn mọi cross-origin POST được gửi.
- [ ] Session cookie có `Secure`, `HttpOnly`, `SameSite`, Domain/Path thích hợp.
- [ ] `@EnableWebSocketSecurity` bật đúng stack Servlet/STOMP; CSRF CONNECT được kiểm tra.
- [ ] Frontend gửi CSRF token bằng **native STOMP CONNECT header**, lấy từ đúng session.
- [ ] Không có business side effect nào trước STOMP CONNECT và authentication hợp lệ.
- [ ] `AuthorizationManager<Message<?>>` deny-by-default cho SEND/SUBSCRIBE.
- [ ] Không cho client SEND trực tiếp broker destinations chứa thông báo server.
- [ ] Private subscriptions và service có object/tenant ACL.
- [ ] Publisher/outbound routing không phát dữ liệu riêng lên public topic.
- [ ] Token expiry/logout/role revocation có close/revalidate sessions/subscriptions.
- [ ] Iframe transports nếu cần có XFO/CSP đúng phạm vi, không mở trang admin.
- [ ] Reverse proxy/path rewrite, multi-node session store và cookie scope được test.
- [ ] Có rate limits, frame size, timeout, connection quotas và logging redaction.
- [ ] Unit tests cho matcher chứng minh chỉ đúng POST transport được exempt.
- [ ] HTTP integration tests chứng minh REST CSRF vẫn hoạt động.
- [ ] Browser/SockJS E2E test dùng **XHR transport thật** và chứng minh CONNECT token vẫn cần.
- [ ] Negative tests xác minh **không data leak và không side effect**.
- [ ] Nếu dùng WebFlux native, không copy Servlet matcher hoặc STOMP assumption.

## 23. Tình huống vận dụng và lời giải

**Tình huống 1 — HTTP 403 ở xhr_send.** Browser đã login, native WS OK, nhưng SockJS `POST /ws/123/abc/xhr_send` bị 403. Bước đầu nên làm gì?

**Lời giải:** Xem request method/path và HTTP filter diagnostics để xác định `CsrfFilter` có thật sự chặn vì thiếu token không. Nếu đúng, cân nhắc ngoại lệ đúng transport route và giữ các lớp bù; đừng tắt CSRF toàn app.

**Tình huống 2 — Bỏ CSRF toàn hệ thống.** Dev dùng `http.csrf(csrf -> csrf.disable())` để SockJS chạy. Nguy cơ gì?

**Lời giải:** Các REST/form unsafe requests dùng cookie có thể mất phòng vệ CSRF. Chỉ exempt request transport đã chứng minh cần thiết, giữ CSRF cho API.

**Tình huống 3 — Matcher wildcard.** App dùng `.ignoringRequestMatchers("/ws/**")` rồi thêm `POST /ws/admin/delete`. Điều gì có thể sai?

**Lời giải:** Endpoint mới nằm trong scope miễn CSRF dù là business mutation. Tách namespace và dùng method+exact transport matcher, kèm regression tests.

**Tình huống 4 — Exemption có mở anonymous?** `POST /ws/.../xhr_send` bị miễn CSRF. Một user chưa login có tự được quyền tạo STOMP session không?

**Lời giải:** Không. `ignoringRequestMatchers` không bằng `permitAll`; HTTP authentication và STOMP CONNECT authentication/CSRF policy vẫn phải được thực thi.

**Tình huống 5 — Token ở HTTP POST.** Client có thể gửi token qua STOMP CONNECT nhưng không có HTTP `X-CSRF-TOKEN` ở `xhr_send`. Hai token checks có giống nhau không?

**Lời giải:** Không. HTTP CsrfFilter kiểm tra HTTP request; Spring Security Messaging kiểm tra native STOMP CONNECT. Miễn HTTP transport không phải bỏ CONNECT CSRF.

**Tình huống 6 — CONNECT thiếu token.** HTTP POST transport đã qua nhưng STOMP CONNECT thiếu CSRF. Có nên nhận CONNECTED không?

**Lời giải:** Không khi CONNECT CSRF policy yêu cầu. Đây là lớp bù trọng yếu; phải test không business side effects khi thiếu token.

**Tình huống 7 — Phía client chỉ dùng native.** Một integration test WebSocketStompClient native CONNECTED. Có chứng minh `xhr_send` CSRF exemption đúng không?

**Lời giải:** Chưa. Phải dùng SockJS XHR fallback thật để tạo HTTP POST đúng transport, đồng thời unit test matcher.

**Tình huống 8 — HTTP POST transport không trả 200.** Matcher matches true nhưng request trả 404 vì SockJS session không tồn tại. Matcher có sai không?

**Lời giải:** Không thể kết luận. CSRF exemption chỉ ảnh hưởng filter; SockJS transport handler có thể từ chối session/path/payload. Test đúng transport flow thay vì gọi POST đơn lẻ.

**Tình huống 9 — WebSocket Origin khác frontend.** Một site lạ gửi Cookie Alice và `Origin` khác. CSRF transport đã exempt, có được cho qua không?

**Lời giải:** Không với browser-only policy. Origin allowlist phải chặn website không tin cậy, cùng với STOMP CONNECT CSRF/authentication và ACL.

**Tình huống 10 — CORS wildcard là đủ?** Dev cho `Access-Control-Allow-Origin: *` ở XHR fallback, cho rằng CSRF bù đã xong. Đúng không?

**Lời giải:** Không. CORS không là authentication; simple cross-origin requests có thể được gửi mà không đọc response. Phải giữ Origin/credentials security, CONNECT CSRF và ACL.

**Tình huống 11 — Session cookie SameSite.** Frontend và API khác subdomain nhưng cùng site. Có thể chỉ tin SameSite để bỏ Origin/CONNECT CSRF không?

**Lời giải:** Không. Same-site không phải same-origin; cookie có thể được gửi trong bối cảnh same-site. Cần Origin allowlist và token kiểm tra đúng phiên.

**Tình huống 12 — Proxy có prefix.** Browser POST `/realtime/ws/.../xhr_send`, Spring matcher đợi `/ws/.../xhr_send` và trả 403. Sửa thế nào?

**Lời giải:** Kiểm tra `servletPath`/`pathInfo` thực tế sau proxy, context path và servlet mapping; sửa pattern có kiểm chứng. Không mở `/**` để chữa tạm.

**Tình huống 13 — Dynamic order.** Alice CONNECTED, SEND lookup order Bob và được service trả dữ liệu. CSRF transport exemption có phải nguyên nhân duy nhất?

**Lời giải:** Không. Lỗi chính là thiếu object-level authorization; mọi lệnh phải kiểm tra principal/tenant/ownership ở service.

**Tình huống 14 — Direct broker SEND.** Client SEND thẳng `/topic/admin` và broker phát thông báo. Lớp nào cần tăng cường?

**Lời giải:** Inbound MESSAGE authorization phải deny direct broker destinations, chỉ cho client gửi application commands qua handler/service.

**Tình huống 15 — SUBSCRIBE của user khác.** Alice SUBSCRIBE vào topic order Bob sau CONNECTED. CSRF CONNECT có bảo vệ không?

**Lời giải:** CSRF không cấp subscription ACL. Cần quyền theo topic/object/tenant tại SUBSCRIBE hoặc trước publish và cơ chế thu hồi.

**Tình huống 16 — Iframe bị DENY.** Legacy browser báo `X-Frame-Options: DENY`. Có nên sửa CSRF matcher không?

**Lời giải:** Không. Đó là framing issue; chỉ nới XFO/CSP đúng iframe resource nếu cần và cùng origin, vẫn giữ clickjacking protection cho trang khác.

**Tình huống 17 — Multiple SecurityFilterChains.** Matcher exception được cấu hình ở API chain nhưng SockJS POST chạy trong chain khác. Kết quả?

**Lời giải:** Exception có thể không áp dụng. Xác minh security matcher precedence; đặt policy trong chain thực sự xử lý transport, bảo vệ API riêng.

**Tình huống 18 — Token-only CONNECT.** SPA gửi JWT chỉ trong STOMP CONNECT, HTTP `/ws authenticated()` trả 401. Có phải exempt CSRF chưa đủ rộng?

**Lời giải:** Không. HTTP handshake cần auth trước khi JWT native tới. Chọn kiến trúc token-only phù hợp, verifier ở CONNECT và CSRF strategy được review; không mở REST CSRF.

**Tình huống 19 — Logout.** Alice logout nhưng WebSocket cũ vẫn nhận message. Exemption có tạo quyền vĩnh viễn?

**Lời giải:** Không, nhưng CONNECT/CSRF chỉ là kiểm tra ban đầu. Cần session revocation, đóng socket hoặc revalidate subscriptions/outbound data khi quyền thay đổi.

**Tình huống 20 — WebFlux native.** Một app chỉ dùng `WebSocketHandler` của WebFlux không có SockJS XHR routes. Có nên tạo Servlet `SockJsXhrSendPostMatcher`?

**Lời giải:** Không. Không có transport POST tương ứng; bảo vệ handshake và native frames theo Reactive stack. Nếu có Reactive HTTP fallback tự thiết kế, dùng `ServerWebExchangeMatcher` và policy riêng.

---

**Ghi nhớ:** **Miễn trừ HTTP CSRF cho SockJS transport là một ngoại lệ có điều kiện, không phải vô hiệu hóa bảo vệ CSRF toàn ứng dụng.** Chỉ những HTTP POST transport đã xác minh (ví dụ `/ws/{server}/{session}/xhr_send`) mới nên được exempt bằng matcher kiểm tra **method và path**; REST/form unsafe requests vẫn cần HTTP CSRF. Điều kiện bảo vệ bù phải có **Origin allowlist, HTTP authentication, CSRF tại STOMP CONNECT, message authorization deny-by-default, object/tenant ACL và kiểm soát tài nguyên/vòng đời**. Ngoại lệ HTTP không bảo vệ tương đương từng POST, nên phải chứng minh bằng negative E2E tests rằng không có business mutation trước CONNECT và không có data leak sau đó. Với SockJS legacy iframe, CSP/XFO là một tầng khác; với WebFlux native, không sao chép policy Servlet khi không có SockJS transport tương ứng.
