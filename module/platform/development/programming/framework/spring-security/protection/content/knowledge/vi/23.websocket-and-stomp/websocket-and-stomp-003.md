# Allowed origins trong cấu hình WebSocket hoặc SockJS

## Mở đầu: kết nối realtime phải có ranh giới origin riêng

Giả sử một ứng dụng Spring Security phục vụ thông báo và cập nhật trạng thái đơn hàng theo thời gian thực. Frontend chính thức chạy tại `https://app.example.com`, frontend quản trị ở `https://admin.example.com`, còn WebSocket/STOMP server được công bố tại `wss://api.example.com/ws`. Người dùng thường đăng nhập bằng session cookie. Một trang không tin cậy tại `https://evil.example.org` cũng có thể thử mở kênh tới endpoint đó:

~~~javascript
const socket = new WebSocket("wss://api.example.com/ws");
~~~

Nếu server mở kết nối cho bất cứ website nào và browser gửi cookie phiên, kênh realtime có thể bị dùng sai ngữ cảnh, dẫn tới **Cross-Site WebSocket Hijacking (CSWSH)**. Ngược lại, việc chỉ cho phép cùng origin có thể làm frontend hợp lệ tại subdomain khác không kết nối được.

Spring cung cấp `setAllowedOrigins(...)` và `setAllowedOriginPatterns(...)` để xác định web origins được chấp nhận khi bắt tay. Với SockJS, policy còn tác động đến các HTTP/XHR fallback transports và cách xử lý CORS. Bài học cần phân biệt **Origin trong handshake**, **CORS của HTTP Fetch**, **authentication**, **CSRF tại STOMP CONNECT** và **phân quyền SEND/SUBSCRIBE**.

Đây là phần **WebSocket và STOMP** trong `SPRING_SECURITY_HTTP_PROTECTION` — mô-đun bảo vệ HTTP và trình duyệt qua CSRF, CORS, security headers, CSP, HSTS, HTTP firewall, session, Servlet và Reactive. Nội dung dùng ví dụ Spring WebSocket Messaging trên Servlet, đồng thời đối chiếu native WebSocket của WebFlux. Các hostname `example.com` chỉ là minh họa.

### Mục tiêu học tập

Sau bài này, người học có thể:

1. Giải thích Origin là scheme, host và port của **trang chạy script**, không phải URL của WebSocket server.
2. Cấu hình `setAllowedOrigins` tường minh và đánh giá rủi ro của `setAllowedOriginPatterns`.
3. Hiểu tác động của cấu hình same-origin mặc định và wildcard đối với native WebSocket.
4. Phân biệt native WebSocket với SockJS XHR/iframe fallback, kể cả CORS và HTTP CSRF.
5. Bảo vệ handshake và STOMP CONNECT/SEND/SUBSCRIBE bằng cơ chế đúng tầng.
6. Kiểm thử origin được phép, origin bị chặn, pattern quá rộng, client không phải browser và cookies.
7. Chẩn đoán sự cố gateway, `X-Frame-Options`, CSP, CSRF và cấu hình bảo mật chồng chéo.
8. Đối chiếu giải pháp Servlet/STOMP với Origin validation của WebFlux native.

## 1. Hiểu đúng Origin trong WebSocket handshake

### 1.1. Same-origin và same-site không giống nhau

Một origin của trang web HTTP(S) được xác định bằng **scheme + host + port**. Path không phải một phần origin.

| Trang thứ nhất | Trang thứ hai | Same-origin? |
| --- | --- | --- |
| `https://app.example.com/a` | `https://app.example.com/b` | Có |
| `https://app.example.com` | `https://api.example.com` | Không: khác host |
| `https://app.example.com` | `http://app.example.com` | Không: khác scheme |
| `https://app.example.com` | `https://app.example.com:8443` | Không: khác port |
| `https://app.example.com` | `https://app.example.com.evil.example.org` | Không: hostname khác |
| `http://localhost:5173` | `http://localhost:8080` | Không: khác port |

**Same-site** là khái niệm khác, thường dựa vào scheme và registrable domain khi browser áp dụng cookie `SameSite`. Hai origin `https://app.example.com` và `https://api.example.com` thường same-site. Một subdomain chứa nội dung do user kiểm soát cũng có thể same-site, nhưng **không nhất thiết đáng tin cậy**.

Do đó:

- Cookie `SameSite=Lax` không tự chứng minh Origin đáng tin.
- `HttpOnly` ngăn JavaScript đọc cookie, **không ngăn browser tự gửi cookie** khi hợp lệ.
- Origin allowlist vẫn cần nếu backend dùng cookie phiên và chấp nhận WebSocket từ browser.
- Authentication và authorization không thể dựa vào việc hai địa chỉ cùng site.

### 1.2. Browser gửi Origin nào?

Từ trang `https://app.example.com`:

~~~javascript
const ws = new WebSocket("wss://api.example.com/ws");
~~~

Handshake WebSocket qua HTTP/1.1 điển hình:

~~~http
GET /ws HTTP/1.1
Host: api.example.com
Connection: Upgrade
Upgrade: websocket
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Origin: https://app.example.com
Cookie: SESSION=<session-id-if-browser-allows>
~~~

**`Origin: https://app.example.com`** là origin của frontend, không phải `wss://api.example.com` và không phải đường dẫn `/ws`. Nếu được chấp nhận, server có thể trả:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: <server-generated-value>
~~~

Response `101` chỉ xác nhận handshake, **chưa** xác nhận STOMP CONNECT hợp lệ hay user có quyền subscribe bất kỳ topic nào. Một số hạ tầng hiện đại có thể hỗ trợ WebSocket qua HTTP/2 với cơ chế handshake khác; ví dụ trên mô tả cách HTTP/1.1 phổ biến.

### 1.3. Browser WebSocket không thực hiện Fetch CORS preflight

So sánh:

| Khía cạnh | HTTP Fetch/XHR | Native WebSocket |
| --- | --- | --- |
| API browser | `fetch(url, options)` | `new WebSocket(url)` |
| Cross-origin | Bị SOP/CORS chi phối khi đọc response | Có thể thử handshake cross-origin |
| Preflight `OPTIONS` | Có khi cần theo method/headers | **Không dùng Fetch CORS preflight** |
| `Access-Control-Allow-Origin` | Browser đánh giá ACAO khi CORS | **Không là điều kiện đọc WebSocket frames** |
| Nơi áp đặt allowlist | CORS processor và browser | **WebSocket handshake server** |
| Từ sau khi kết nối | Nhiều HTTP requests độc lập | Nhiều messages trong một connection |
| Authentication | Theo từng HTTP request/session | Handshake hoặc giao thức ứng dụng/CONNECT |
| Authorization | Endpoint/object checks | Message destination và quyền object checks |

Vì vậy bật `http.cors(...)` cho REST API **không đủ** để chống browser từ website lạ mở native WebSocket. Và việc thêm ACAO vào response HTTP 101 không phải biện pháp thay thế `setAllowedOrigins`.

### 1.4. Origin là tín hiệu nguồn trang, không phải identity

JavaScript trình duyệt không được tùy ý đặt header `Origin` cho `new WebSocket(...)`. Điều này khiến Origin hữu ích để chặn các trang không tin cậy.

Nhưng WebSocket client không phải browser có thể giả `Origin`; user đã đăng nhập ở frontend chính thức cũng có thể gửi dữ liệu trái quyền. Do đó Origin **không chứng minh** principal, role, scope hay ownership.

## 2. API `setAllowedOrigins` và mặc định Spring

Spring WebSocket Messaging trên Servlet cho phép đăng ký STOMP endpoint bằng `StompEndpointRegistry`:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws")
        .setAllowedOrigins("https://app.example.com");
}
~~~

Giá trị cần cung cấp là **origin của trang được tin cậy**, không phải đích WebSocket.

### 2.1. Chính sách same-origin mặc định

Các endpoint Spring WebSocket/SockJS thông thường **giới hạn same-origin theo mặc định** khi không có cấu hình cho phép cross-origin mở rộng. Đó là điểm xuất phát an toàn nhưng có thể chặn frontend và API nằm ở hai subdomain khác nhau.

Ví dụ:

~~~text
Trang frontend: https://app.example.com
URL WebSocket : wss://api.example.com/ws
Origin header : https://app.example.com
Kết quả       : khác origin với server api.example.com
~~~

Nếu nhu cầu nghiệp vụ hợp lệ, hãy thêm đúng origin `https://app.example.com` thay vì mở mọi origin. Cần kiểm tra hành vi thực tế theo framework version, SockJS options và các tầng proxy.

### 2.2. Cho phép chính xác hai frontend

~~~java
registry.addEndpoint("/ws")
    .setAllowedOrigins(
        "https://app.example.com",
        "https://admin.example.com"
    );
~~~

Điều này mở quyền **thử handshake** cho hai origin. Nó không tự cấp quyền quản trị cho bất kỳ user nào ở `admin.example.com`, và không tự làm `/topic/admin` trở thành một subscription được phép.

**Quy tắc cấu hình:**

- Không ghi path như `https://app.example.com/dashboard`.
- Không ghi `wss://api.example.com/ws` vào allowlist.
- Đánh giá scheme và port riêng biệt; HTTP dev origin không được mặc nhiên là production origin.
- Kiểm toán origin nào do nhóm phát triển kiểm soát, origin nào có nội dung do người khác điều khiển.
- Kiểm tra thêm Origin `null` hoặc Origin vắng mặt theo policy dành cho browser/non-browser của ứng dụng.

### 2.3. Wildcard là mở rộng ranh giới tin cậy

Phản ví dụ với API có session cookie:

~~~java
registry.addEndpoint("/ws")
    .setAllowedOrigins("*");
~~~

Một policy cho phép mọi origin mở handshake có thể tạo cơ hội cho trang không tin cậy dùng phiên mà browser đính kèm và giao tiếp hai chiều với server. **Native WebSocket không được browser cứu bằng ràng buộc ACAO wildcard của Fetch.**

Không sử dụng wildcard để khắc phục sự cố cookie, CSP hoặc gateway. Nếu API realtime thực sự phục vụ anonymous/public clients, cần đánh giá cụ thể giới hạn tài nguyên, read/write permissions và hệ quả mỗi origin có thể gửi/nhận frame.

## 3. `setAllowedOriginPatterns`: linh hoạt nhưng dễ mở quá rộng

Ở những phiên bản Spring hỗ trợ API này, có thể đăng ký patterns:

~~~java
registry.addEndpoint("/ws")
    .setAllowedOriginPatterns(
        "https://*.trusted-ui.example.com"
    );
~~~

Nó hữu ích khi **toàn bộ namespace frontend** nằm dưới quyền kiểm soát đáng tin cậy. Nhưng pattern không tự bảo đảm:

- Mọi subdomain đều do cùng nhóm vận hành.
- Preview deployments không cho user tự xuất bản JavaScript.
- Không có subdomain takeover do CNAME/DNS cũ.
- Không có tenant/user-content hosting.
- Không có domain staging/dev cấu hình yếu.
- Từng site khớp pattern có cùng mức độ tin cậy với production app.

### 3.1. So sánh cách cấp quyền

| Cách cấu hình | Lợi ích | Nguy cơ |
| --- | --- | --- |
| Không mở cross-origin | Hạn chế nguồn trang theo mặc định | Frontend hợp lệ khác origin không kết nối được |
| `setAllowedOrigins("https://app.example.com")` | Rõ ràng, dễ kiểm toán | Phải cập nhật khi frontend đổi host |
| Nhiều origins tường minh | Tương thích app và admin | Mỗi origin được thêm làm tăng phạm vi tin cậy |
| `setAllowedOriginPatterns("https://*.trusted-ui.example.com")` | Hỗ trợ nhiều frontend trong namespace | Một subdomain không an toàn có thể mở đường CSWSH |
| `setAllowedOrigins("*")` | Ít cấu hình | Mọi trang có thể thử handshake; rất nguy hiểm với cookie |
| Custom validation | Chính sách động theo domain | Dễ sai do prefix/host spoofing/canonicalization |

### 3.2. Tránh so khớp bằng startsWith/contains

Hai cách tự viết sau dễ bị hostname giả vượt qua:

~~~java
// KHÔNG an toàn:
boolean allowed = origin.startsWith("https://app.example.com");

// KHÔNG an toàn:
boolean allowed2 = origin.contains("example.com");
~~~

Ví dụ `https://app.example.com.evil.example.org` không phải frontend chính thức. Hãy dùng API allowlist chuẩn, giới hạn pattern và các phép thử âm: khác scheme, khác port, hậu tố giả, `Origin: null`.

### 3.3. So sánh `setAllowedOriginPatterns` với CORS HTTP patterns

Cả CORS HTTP và WebSocket endpoint đều có khái niệm origins/patterns, nhưng **áp dụng tại hai đường xử lý khác nhau**.

- `CorsConfiguration#setAllowedOriginPatterns` có vai trò khi HTTP response cần CORS.
- `StompEndpointRegistry#addEndpoint(...).setAllowedOriginPatterns(...)` quy định origin của WebSocket/SockJS endpoint.
- Không mặc định một cấu hình MVC `WebMvcConfigurer#addCorsMappings` tự thay thế policy WebSocket.
- Không coi `Access-Control-Allow-Credentials: true` của HTTP API là điều kiện cho native WebSocket frames.

Nếu sử dụng cùng allowlist frontend, nên có quy trình cấu hình thống nhất về **dữ liệu policy**, nhưng mỗi stack phải thực thi ranh giới riêng của nó.

## 4. Cấu hình đầy đủ cho STOMP-over-WebSocket Servlet

Ví dụ Spring WebSocket Message Broker chỉ cho hai frontend:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class SecureStompEndpointConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
            .setAllowedOrigins(
                "https://app.example.com",
                "https://admin.example.com"
            );
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

**Phân biệt trách nhiệm:**

1. `addEndpoint("/ws")` tạo điểm vào cho HTTP WebSocket handshake.
2. `setAllowedOrigins(...)` giới hạn origin của trang browser được phép mở kênh.
3. `/app` định tuyến client SEND tới các `@MessageMapping` phù hợp.
4. `/topic`/`/queue` là destinations của broker; **không tự áp dụng phân quyền**.
5. `/user` hỗ trợ user destinations; server vẫn phải phát đúng principal và kiểm tra object ownership.

Mã trên **không phải security configuration hoàn chỉnh**: nó chưa xác thực session hoặc phân quyền STOMP. Cần các phần tiếp theo.

### 4.1. Tách endpoint theo mức độ tin cậy

Có thể khai báo hai endpoint với origins độc lập:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws/app")
        .setAllowedOrigins("https://app.example.com");

    registry.addEndpoint("/ws/admin")
        .setAllowedOrigins("https://admin.example.com");
}
~~~

Nhưng endpoint URL **không phải role**: user thường có thể biết hoặc gọi `/ws/admin` nếu auth chưa chặn. Khi có nhiều endpoints cùng chung broker, cần message authorization và role/tenant checks tách biệt; HTTP security chains phải match đúng các handshake paths.

## 5. SockJS: cùng origin policy nhưng nhiều transports

SockJS cho frontend một giao diện tương tự WebSocket và có thể chọn fallback khi native WebSocket bị chặn/không khả dụng.

Bật SockJS trên endpoint:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws")
        .setAllowedOrigins("https://app.example.com")
        .withSockJS();
}
~~~

**Đây là phương án thay thế cho endpoint native-only**, không đăng ký hai endpoint có cùng path một cách tùy tiện.

### 5.1. SockJS có thể dùng HTTP requests

Một SockJS session có thể thực hiện những URL theo cấu trúc sau (tùy transport/version):

~~~text
GET  /ws/info
GET  /ws/<server-id>/<session-id>/websocket
POST /ws/<server-id>/<session-id>/xhr_send
GET  /ws/<server-id>/<session-id>/xhr_streaming
GET  /ws/<server-id>/<session-id>/xhr
...
~~~

Khi dùng native WebSocket transport, browser thực hiện WebSocket handshake. Khi dùng **XHR streaming/polling**, browser thực hiện các **HTTP requests**, nên còn phải xét:

- CORS và `Access-Control-Allow-Origin` của HTTP response.
- Preflight OPTIONS nếu method/request headers yêu cầu.
- `Access-Control-Allow-Credentials` nếu transport dùng cookie ở credentials mode thích hợp.
- HTTP CSRF protection trên những POST transport paths.
- Cookie/SameSite, HTTP authentication và gateway forwarding.
- HTTP security headers ảnh hưởng iframe/script-based legacy transports.

### 5.2. Origin restrictions có thể hạn chế một số fallback transports

Một số transports cũ không có khả năng xác thực Origin restrictions đáng tin cậy. Vì vậy khi Spring SockJS chỉ cho **same-origin** hoặc một **tập origins cụ thể**, framework có thể vô hiệu hóa các transports không đáp ứng chính sách này, chẳng hạn iframe-based transports trong những cấu hình/version nhất định.

Điều này có nghĩa thay `setAllowedOrigins` có thể làm thay đổi **transport matrix**, chứ không chỉ trạng thái HTTP handshake. Đừng kết luận rằng một trình duyệt legacy sẽ dùng được mọi fallback sau khi đặt allowlist.

Hãy xác định loại browser/SockJS client thật sự cần hỗ trợ và kiểm tra tài liệu phiên bản Spring/SockJS tương ứng. Không mở `*` chỉ để giữ hỗ trợ một fallback cũ khi điều đó làm mất ranh giới tin cậy.

### 5.3. SockJS HTTP fallback có CORS, native WebSocket không

Ví dụ một SockJS `GET /ws/info` khác origin có thể nhận response HTTP cùng header CORS phù hợp:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin
~~~

Với một XHR fallback khác, nếu request cần preflight, browser có thể gửi:

~~~http
OPTIONS /ws/123/session1/xhr_send HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: POST
Access-Control-Request-Headers: content-type
~~~

URL ở đây chỉ minh họa transport path; cần dùng một SockJS session/route **đang tồn tại** để test thật. Phản hồi hợp lệ tùy policy của SockJS server và gateway.

**Điểm khác cốt lõi:** ACAO/ACAC ở đây dùng cho **HTTP fallback transport**. Chúng không là cơ chế native WebSocket yêu cầu browser kiểm tra trước khi trao đổi frames.

### 5.4. CORS headers có thể bị xử lý trùng

Một ứng dụng có thể đồng thời khai báo:

- Origin policy ở STOMP/SockJS endpoint.
- CORS mapping của Spring MVC.
- `HttpSecurity.cors(...)` hoặc một Servlet `CorsFilter` độc lập.
- CORS rule tại reverse proxy/CDN/API gateway.

Spring SockJS có khả năng thêm những CORS headers cần thiết cho HTTP transports, và một số xử lý tránh thêm trùng khi headers đã có. Nhưng nếu nhiều tầng phát policies khác nhau, response cuối có thể sai hoặc chứa **nhiều giá trị ACAO**, làm browser từ chối.

Giải pháp không phải “càng nhiều CORS filters càng an toàn”. Cần xác định tầng chịu trách nhiệm xử lý `/ws/**` và đồng bộ policy/gateway, đặc biệt với response 401/403 và OPTIONS.

## 6. CSRF của SockJS HTTP transport và STOMP CONNECT là hai vấn đề khác

### 6.1. Một XHR POST có thể vướng CSRF HTTP

SockJS fallback có thể phát HTTP POST đến `/ws/.../xhr_send`. Nếu Spring Security HTTP CSRF protection áp dụng cho request này và không có token theo cơ chế HTTP, response có thể là 403, dù native WebSocket chạy được.

Phản ứng sai là tắt toàn bộ CSRF:

~~~java
// Phản ví dụ: KHÔNG dùng làm cách sửa chung cho SockJS.
http.csrf(csrf -> csrf.disable());
~~~

Nếu transport thực sự đòi một ngoại lệ, phải giới hạn **đúng nhóm SockJS HTTP URLs được kiểm soát**, giữ CSRF cho những POST/PUT nghiệp vụ khác và tiếp tục bảo vệ STOMP CONNECT. Thiết kế ngoại lệ cần test security matcher thực tế, không giả định tất cả `/ws/**` đều là request an toàn trong mọi ứng dụng.

### 6.2. STOMP CONNECT xảy ra sau transport

Sau khi có một đường vận chuyển WebSocket/SockJS, STOMP client gửi một frame:

~~~text
CONNECT
accept-version:1.2
host:api.example.com
X-CSRF-TOKEN:<csrf-token>

^@
~~~

Đây là **STOMP native header**, không phải header HTTP của GET Upgrade hay XHR POST. Khi Spring Security WebSocket Messaging yêu cầu CSRF ở inbound CONNECT, token cần gắn với phiên/ngữ cảnh xác thực hợp lệ.

Đừng nhầm:

1. HTTP CSRF ở các yêu cầu POST fallback của SockJS.
2. CSRF token của STOMP CONNECT bên trong transport.
3. CSRF của các HTTP REST API độc lập.

Một exception HTTP cho SockJS transport **không** nên biến thành việc tắt bảo vệ CONNECT hoặc REST API.

### 6.3. Iframe fallback và security headers

Một số SockJS iframe-based transports cũ chịu tác động của:

~~~http
X-Frame-Options: DENY
Content-Security-Policy: frame-ancestors 'none'
~~~

Đây là những biện pháp chống framing/clickjacking. Nếu trình duyệt legacy không dùng được iframe transport vì policy này, đừng nới lỏng `X-Frame-Options`/CSP trên **toàn bộ ứng dụng**. Hãy xác minh transport nào thật sự cần, và nếu phải hỗ trợ thì thiết kế giới hạn/phòng vệ phù hợp với version và browser.

`X-Frame-Options: SAMEORIGIN` không đồng nghĩa sẽ cho iframe từ mọi origin được liệt kê trong WebSocket `setAllowedOrigins`. HTTP framing policy và WebSocket Origin policy là hai ranh giới khác nhau.

## 7. Cookie, SameSite và CSWSH

### 7.1. WebSocket browser không có `credentials: "include"` option

Fetch có thể dùng:

~~~javascript
fetch("https://api.example.com/api/me", {
  credentials: "include"
});
~~~

Nhưng WebSocket constructor của browser không có một object `credentials` hoặc arbitrary `headers` như Fetch:

~~~javascript
// KHÔNG phải cú pháp WebSocket API chuẩn:
new WebSocket("wss://api.example.com/ws", {
  credentials: "include",
  headers: { Authorization: "Bearer <token>" }
});
~~~

Cookie của handshake do browser quản lý theo Domain/Path, `Secure`, `SameSite` và chính sách browser. Khi cookie vắng mặt, không được sửa bằng một WebSocket option không tồn tại.

### 7.2. SameSite không thay Origin allowlist

Cookie ví dụ:

~~~http
Set-Cookie: SESSION=<opaque-id>; Path=/; Secure; HttpOnly; SameSite=Lax
~~~

- `HttpOnly` cấm JavaScript đọc cookie trực tiếp, không cấm browser gửi cookie.
- `Secure` giúp giới hạn gửi cookie theo kết nối bảo mật.
- `SameSite=Lax` giảm một số cross-site request, nhưng `https://app.example.com` và `https://api.example.com` thường same-site.
- Một trang do user kiểm soát tại `https://usercontent.example.com` cũng có thể same-site với API, dù không đáng tin.
- Cookie cross-site có thể bị browser chặn dù server allowed origin đã cấu hình đúng.

**Không coi một subdomain same-site là origin tin cậy mặc định.** Đặc biệt, `setAllowedOriginPatterns("https://*.example.com")` dễ mở rộng quá mức nếu namespace chứa user content hoặc preview apps.

### 7.3. Cross-Site WebSocket Hijacking

Một trang không tin cậy có thể thử:

~~~javascript
const socket = new WebSocket("wss://api.example.com/ws");

socket.onopen = () => {
  // Trang lạ cố trao đổi message nếu server chấp nhận handshake.
};
~~~

Nếu browser gửi cookie của nạn nhân, server cho phép mọi origin và message layer không kiểm soát, attacker có thể lợi dụng connection để truy cập dữ liệu realtime.

Để chặn theo nhiều lớp:

1. Origin allowlist hẹp ngay ở handshake.
2. HTTP authentication hoặc token verification rõ ràng.
3. CSRF token hợp lệ trong STOMP CONNECT khi Spring Security yêu cầu.
4. MESSAGE/SUBSCRIBE authorization theo principal và destination.
5. Object/tenant checks trước khi đọc/ghi/phát dữ liệu.
6. Logout/revocation, message rate limits và connection quotas.

## 8. Spring Security HTTP handshake: xác thực là ranh giới riêng

Một Servlet `SecurityFilterChain` có thể yêu cầu authentication cho WebSocket endpoint:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class RealtimeHandshakeSecurity {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/ws", "/ws/**").authenticated()
                .requestMatchers("/api/**").authenticated()
                .anyRequest().denyAll())
            .build();
    }
}
~~~

- HTTP auth kiểm tra **principal/session** ở handshake.
- WebSocket allowed origins kiểm tra **nguồn trang**.
- Message security kiểm tra **destination và action** sau handshake.
- Business service kiểm tra **role, object ownership, tenant**.

`authenticated()` trên `/ws` **không** tự phân quyền STOMP messages. Nó cũng có thể chặn một kiến trúc dự định xác thực bearer token **chỉ tại STOMP CONNECT**, vì ở HTTP handshake chưa có principal. Nếu dùng CONNECT-token, phải thiết kế handshake/CONNECT và interceptor theo một mô hình nhất quán, không mở toàn bộ endpoints vô điều kiện.

### 8.1. Origin không phải role

Phản ví dụ:

~~~java
// SAI: Origin hợp lệ không cấp quyền quản trị.
if ("https://admin.example.com".equals(origin)) {
    grantRole("ADMIN");
}
~~~

Client ngoài browser có thể giả Origin, và user trên frontend admin vẫn có thể không có role admin. Mọi role phải bắt nguồn từ authentication/authorization server-side.

## 9. Spring Security Messaging: không dừng ở HTTP 101

Với STOMP trên Spring WebSocket Message Broker, `@EnableWebSocketSecurity` và `AuthorizationManager<Message<?>>` cho phép kiểm soát inbound messages:

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
            .nullDestMatcher().authenticated()
            .simpSubscribeDestMatchers("/app/**").denyAll()
            .simpSubscribeDestMatchers(
                "/user/queue/updates",
                "/topic/public"
            ).authenticated()
            .simpDestMatchers("/app/commands.submit")
                .hasRole("USER")
            .simpTypeMatchers(
                SimpMessageType.MESSAGE,
                SimpMessageType.SUBSCRIBE
            ).denyAll()
            .anyMessage().denyAll()
            .build();
    }
}
~~~

Đọc policy từ trên xuống:

- CONNECT và các message không có destination có thể yêu cầu principal từ HTTP/CONNECT authentication.
- Client không subscribe vào application destinations `/app/**`.
- Chỉ một vài user/broker destinations được subscribe.
- Chỉ SEND tới application command được phê duyệt.
- SEND thẳng tới `/topic/**` không được tự do đi vào broker.
- Mọi message không được khai báo rõ ràng đều bị từ chối.

**Lưu ý:** Spring Security Messaging tập trung bảo vệ client inbound channel. Không dựa vào giả định cùng ACL sẽ tự kiểm tra tất cả outbound broker messages. Khi server phát dữ liệu, business logic phải chọn đúng user/topic và quyền tương ứng.

### 9.1. CSRF ở STOMP CONNECT

Khi dùng Spring Security WebSocket Messaging với yêu cầu bảo vệ CONNECT, STOMP client phải gửi token hợp lệ trong **native header**:

~~~text
CONNECT
accept-version:1.2
host:api.example.com
X-CSRF-TOKEN:<valid-token>

^@
~~~

`^@` biểu diễn byte NUL kết thúc STOMP frame. Header STOMP này **không phải** HTTP header của `GET /ws`.

Nếu frontend cần lấy token từ HTTP API khác origin, ứng dụng có thể cung cấp endpoint `/api/csrf` qua HTTPS, yêu cầu principal và HTTP CORS riêng cho origin tin cậy. Cách tạo/đọc token cần tương thích `CsrfTokenRepository`, deferred/masked tokens và session lifecycle của Spring Security đang sử dụng. Không mặc định framework có sẵn endpoint `/api/csrf`.

### 9.2. Ví dụ SockJS + STOMP client

~~~javascript
import SockJS from "sockjs-client";
import { Client } from "@stomp/stompjs";

async function connectRealtime() {
  const response = await fetch(
    "https://api.example.com/api/csrf",
    { credentials: "include" }
  );
  if (!response.ok) {
    throw new Error("Không lấy được CSRF token");
  }

  const { token, headerName } = await response.json();

  const client = new Client({
    webSocketFactory: () =>
      new SockJS("https://api.example.com/ws"),
    connectHeaders: {
      [headerName]: token
    },
    reconnectDelay: 3000,
    onConnect: () => {
      client.subscribe("/user/queue/updates", frame => {
        console.log("Realtime:", frame.body);
      });
    },
    onStompError: frame => {
      console.error("STOMP ERROR:", frame.headers.message);
    }
  });

  client.activate();
  return client;
}
~~~

**Đúng loại URL:** SockJS client dùng `https://api.example.com/ws`, còn native WebSocket dùng `wss://api.example.com/ws`. `connectHeaders` là STOMP headers nằm **bên trong transport**, không tự thêm HTTP `Authorization` hay `X-CSRF-TOKEN` vào browser WebSocket handshake. Ví dụ giả định có HTTP endpoint lấy CSRF token do ứng dụng triển khai và cookie phiên hợp lệ.

### 9.3. Object-level authorization

Giả sử Alice có role USER và được SEND tới `/app/commands.submit` nhưng payload yêu cầu order của Bob. Role USER và origin app đều hợp lệ; service vẫn phải từ chối:

~~~java
// Pseudocode nghiệp vụ:
Order order = orderRepository.findById(command.orderId())
    .orElseThrow(NotFoundException::new);

if (!order.belongsTo(authenticatedPrincipal)) {
    throw new AccessDeniedException("Forbidden");
}

publishToAuthorizedUser(authenticatedPrincipal, order);
~~~

Một `SUBSCRIBE /topic/orders/2002` cũng có thể làm rò rỉ dữ liệu nếu chỉ xét authenticated mà không xét order 2002 thuộc quyền ai. Phân quyền theo destination/object và routing của server là các yêu cầu **khác** Origin allowlist.

## 10. WebFlux native WebSocket: áp dụng cùng nguyên tắc theo API khác

`setAllowedOrigins(...)` từ `StompEndpointRegistry` là API của Spring WebSocket Message Broker, thường dùng với stack Servlet. Ứng dụng **WebFlux native** có `WebSocketHandler`/`WebSocketSession`, không mặc định mang STOMP broker và message security giống Servlet.

Với WebFlux:

- `ServerHttpSecurity` bảo vệ HTTP handshake route.
- Origin cần được kiểm tra tại handshake bằng adapter/handler/WebFilter phù hợp.
- `CorsWebFilter` xử lý HTTP CORS ở các request tương ứng, **không phân quyền từng WebSocket message**.
- Service kiểm tra nội dung và quyền của **mỗi message**.
- Nếu thật sự dùng một giải pháp STOMP Reactive, cần xác minh API và bảo mật chính giải pháp đó.

### 10.1. HTTP security Reactive

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveHandshakeSecurity {

    @Bean
    SecurityWebFilterChain chain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/ws").authenticated()
                .anyExchange().denyAll())
            .build();
    }
}
~~~

Rule này yêu cầu authentication ở **HTTP handshake**, chưa kiểm tra Origin/message.

### 10.2. WebFilter Origin guard mẫu

~~~java
import java.util.Set;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.WebFilter;

@Configuration
class ReactiveOriginGuard {

    private static final Set<String> ALLOWED =
        Set.of("https://app.example.com");

    @Bean
    @Order(Ordered.HIGHEST_PRECEDENCE)
    WebFilter websocketOriginGuard() {
        return (exchange, chain) -> {
            if (!"/ws".equals(
                    exchange.getRequest().getPath().value())) {
                return chain.filter(exchange);
            }

            String origin = exchange.getRequest()
                .getHeaders().getOrigin();

            if (origin == null || !ALLOWED.contains(origin)) {
                exchange.getResponse()
                    .setStatusCode(HttpStatus.FORBIDDEN);
                return exchange.getResponse().setComplete();
            }

            return chain.filter(exchange);
        };
    }
}
~~~

Đây là policy minh họa cho route dành cho browser, **cố ý từ chối cả Origin vắng mặt**. Nếu non-browser clients được phép, phải thiết kế authentication và Origin policy riêng cho họ. Trong ứng dụng thật, kiểm tra request handshake, path rewrite, canonicalization và thứ tự WebFilters.

### 10.3. Message validation trong handler

~~~java
import java.security.Principal;

import reactor.core.publisher.Mono;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.reactive.socket.WebSocketHandler;

interface RealtimeCommandService {
    Mono<Void> validateAndAuthorize(
        Principal principal,
        String payload
    );
}

class SecureReactiveSocketHandler {

    static WebSocketHandler create(RealtimeCommandService service) {
        return session -> session.getHandshakeInfo()
            .getPrincipal()
            .switchIfEmpty(Mono.error(
                new AccessDeniedException("Unauthenticated")))
            .flatMap(principal ->
                session.receive()
                    .concatMap(message ->
                        service.validateAndAuthorize(
                            principal, message.getPayloadAsText()
                        ))
                    .then()
            );
    }
}
~~~

`RealtimeCommandService` phải parse input, giới hạn kích thước/tốc độ, kiểm tra principal, object/tenant ACL và chỉ phát response cho session đúng quyền. Ví dụ chưa bao gồm handler registration, `session.send(...)` hoặc các chính sách backpressure.

## 11. Ma trận kiểm thử origins và transports

### 11.1. Origin handshake test

| Ca | Origin | Authentication | Kỳ vọng |
| --- | --- | --- | --- |
| W1 | `https://app.example.com` | Hợp lệ | Cho phép nếu đáp ứng toàn bộ policy |
| W2 | `https://admin.example.com` | Hợp lệ | Chỉ cho nếu nằm trong endpoint allowlist |
| W3 | `https://evil.example.org` | Hợp lệ | Từ chối |
| W4 | `http://app.example.com` | Hợp lệ | Từ chối vì khác scheme |
| W5 | `https://app.example.com:8443` | Hợp lệ | Từ chối nếu port không được liệt kê |
| W6 | `https://app.example.com.evil.example.org` | Hợp lệ | Từ chối hostname giả |
| W7 | `null` | Hợp lệ | Không mặc nhiên cho phép opaque origin |
| W8 | Origin hợp lệ | Không có session/token | Authentication từ chối |
| W9 | Non-browser giả Origin hợp lệ | Không có auth | Vẫn bị authentication từ chối |
| W10 | Origin không có trên non-browser request | Có auth | Theo policy đã thiết kế; không suy ra role từ Origin |

**Quan trọng:** để test chắc chắn **Origin validation**, thử origin lạ với **session kiểm thử hợp lệ**. Nếu thiếu cookie và nhận 401 từ HTTP authentication, chưa chứng minh WebSocket allowlist đã hoạt động.

### 11.2. SockJS transport test

| Transport | Request kiểu gì? | Cần kiểm tra |
| --- | --- | --- |
| Native WebSocket | GET Upgrade hoặc handshake WebSocket tương đương | Origin, HTTP auth, TLS/proxy |
| SockJS WebSocket transport | WS handshake theo SockJS URL | Origin, cookie, message security |
| XHR streaming/polling | HTTP GET/POST | CORS, preflight khi có, HTTP CSRF, cookies |
| Legacy iframe/script transports | Iframe/script + HTTP | Transport availability, X-Frame-Options/CSP, origin policy |
| STOMP trên transport bất kỳ | CONNECT/SEND/SUBSCRIBE frames | CSRF CONNECT, destination/object ACL |

### 11.3. Bất biến bảo mật cần test

- Origin không tin cậy **không** được mở kênh browser có quyền đọc dữ liệu.
- Preflight/XHR SockJS khác origin không nhận ACAO sai hoặc wildcard credentials.
- HTTP 101 không đồng nghĩa STOMP CONNECT đã thành công.
- CONNECT hợp lệ chưa cho phép SUBSCRIBE topic admin.
- Client không SEND trực tiếp vào broker destinations.
- User A không nghe được dữ liệu của user B.
- Session/logout/role revocation có hiệu lực theo thiết kế ngay cả khi connection đã mở.

## 12. Thử bằng browser từ hai origins

Tạo hai trang kiểm thử trên những domain tổ chức sở hữu:

- `https://app.example.com/ws-test.html` — origin được phép.
- `https://evil.example.org/ws-test.html` — origin không được phép.

Cùng mã:

~~~html
<button id="connect">Mở WebSocket</button>
<pre id="out"></pre>

<script>
  document.querySelector("#connect")
    .addEventListener("click", () => {
      const out = document.querySelector("#out");
      const socket = new WebSocket("wss://api.example.com/ws");

      socket.onopen = () => {
        out.textContent += "Opened\n";
      };
      socket.onerror = () => {
        out.textContent += "Connection error\n";
      };
      socket.onclose = (event) => {
        out.textContent += "Closed: " + event.code + "\n";
      };
      socket.onmessage = (event) => {
        out.textContent += "Message: " + event.data + "\n";
      };
    });
</script>
~~~

Mã này kiểm tra **native handshake**, không gửi STOMP CONNECT. Socket có thể mở rồi đóng vì server mong đợi CONNECT và client không gửi. Muốn kiểm thử end-to-end STOMP, dùng client `@stomp/stompjs` với token thích hợp.

### 12.1. Quan sát DevTools

1. Trình duyệt có phát request WebSocket hay bị CSP `connect-src` chặn trước?
2. Header `Origin` là gì? Có đúng scheme, host, port không?
3. HTTP handshake nhận 101, 401, 403 hay lỗi TLS/proxy?
4. Có Cookie trên request nếu session-based auth yêu cầu không?
5. Nếu nhận 101, tab Frames/Messages có STOMP `CONNECT`, `CONNECTED`, `ERROR` không?
6. Với SockJS, transport nào được chọn? Có `/ws/info`, XHR requests và preflight OPTIONS không?
7. Có dữ liệu riêng tư xuất hiện ở một origin/session/subscription không có quyền không?

Không dùng session của người dùng thật hay dữ liệu production khi thử origin không tin cậy.

## 13. Curl, non-browser WebSocket và giới hạn kiểm thử

### 13.1. Curl kiểm tra một phần handshake

~~~bash
curl -i --http1.1 "https://api.example.com/ws" \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==" \
  -H "Origin: https://evil.example.org"
~~~

Lệnh trên **không phải** một STOMP/WebSocket client hoàn chỉnh. Nếu không có phiên, 401 có thể đến trước Origin check. Nếu gateway/handshake thấy request không hợp lệ, server cũng có thể trả 400/403. Đừng xem HTTP 101 là bằng chứng message authorization.

Trên Windows PowerShell cũ, có thể dùng `curl.exe` để tránh alias `curl`.

### 13.2. Kiểm tra SockJS info endpoint

Nếu endpoint bật SockJS:

~~~bash
curl -i "https://api.example.com/ws/info" \
  -H "Origin: https://app.example.com"
~~~

Và origin lạ:

~~~bash
curl -i "https://api.example.com/ws/info" \
  -H "Origin: https://evil.example.org"
~~~

Kết quả chịu ảnh hưởng HTTP authentication, SockJS service và gateway. Cần xem status **lẫn CORS response headers**. Một request `/ws/info` không có cookie có thể nhận 401 vì Security chặn, chưa chứng minh policy Origin đúng/sai.

Nếu debug XHR POST, cần dùng **session/transport URL đang tồn tại** do SockJS client chọn, không tạo một URL giả rồi coi 404 là kết quả CORS.

### 13.3. Non-browser client giả Origin

Một công cụ WebSocket chuyên dụng có thể đặt Origin tùy ý. Hãy thử:

- Origin app hợp lệ, **không có authentication** → phải bị từ chối theo auth.
- Origin evil, session thử nghiệm hợp lệ → phải bị từ chối theo Origin policy.
- Origin app, auth hợp lệ, CONNECT thiếu CSRF → bị STOMP security từ chối nếu yêu cầu.
- Origin app, CONNECT hợp lệ, SEND tới `/topic/admin` → bị chặn.
- Origin app, Alice thử subscription hoặc object ID của Bob → không phát dữ liệu Bob.

Như vậy mới chứng minh Origin **không bị dùng thay authentication**.

## 14. Kế hoạch kiểm thử tích hợp Spring

Với Servlet/STOMP, dùng test server thật và một WebSocket/STOMP client như `WebSocketStompClient` kết hợp `StandardWebSocketClient`. Kịch bản cần ít nhất:

~~~text
Given:
  - Spring Boot test server chạy trên random port.
  - Tài khoản thử nghiệm authenticated, session hợp lệ.
  - Endpoint /ws đã cấu hình setAllowedOrigins.
  - CSRF token hợp lệ theo cùng session.

Test dương:
  A) Handshake từ Origin https://app.example.com được chấp nhận.
  B) STOMP CONNECT với token đúng trả CONNECTED.
  C) SUBSCRIBE và SEND đúng destination/ownership nhận message đúng.

Test âm:
  D) Cùng session, Origin https://evil.example.org bị chặn handshake.
  E) Origin khác scheme/port, hostname giả, Origin null bị từ chối.
  F) CONNECT thiếu/sai CSRF token bị từ chối.
  G) Client SEND trực tiếp /topic/** hoặc SUBSCRIBE private topic trái quyền.
  H) User Alice không nhận được object data của Bob.
  I) Sau logout/thu hồi role, session cũ không tiếp tục nhận data trái quyền.
~~~

Đây là **thiết kế kiểm thử**, chưa chạy trong project. Code test thực cần xử lý handshake headers, cookie/session, timeout, asynchronous STOMP frames, ERROR và connection close.

### 14.1. Không dùng MockMvc như phép thử toàn bộ WebSocket

`MockMvc` rất hữu ích cho HTTP authentication, CSRF endpoints và request matcher, nhưng một `GET /ws` qua MockMvc không thay thế một kết nối WebSocket upgrade thực và luồng STOMP frames. Phải có integration test qua WebSocket client hoặc browser.

### 14.2. Phân biệt test origin và test authentication

Nếu request Origin evil không cookie nhận 401, chưa thể kết luận Origin policy đã chặn evil; auth có thể đã từ chối trước. Dùng **cùng session hợp lệ** cho origin được phép và bị cấm, rồi so kết quả handshake. Sau đó test thêm request Origin đúng nhưng thiếu session để kiểm chứng authentication độc lập.

### 14.3. Thử những SockJS fallback thật sự hỗ trợ

Một SockJS test chỉ dùng WebSocket transport không chứng minh XHR streaming/polling hoạt động. Trong browser hỗ trợ và test harness phù hợp, thử những transport ứng dụng yêu cầu, quan sát CORS/preflight, cookie, CSRF HTTP, STOMP CONNECT và dữ liệu nhận. Đừng ép hỗ trợ legacy iframe bằng wildcard nếu rủi ro vượt lợi ích.

## 15. Bảng lỗi và hướng xử lý

| Triệu chứng | Nguyên nhân có thể | Cách chẩn đoán |
| --- | --- | --- |
| REST Fetch có CORS đúng nhưng WebSocket từ origin lạ mở được | Đang thiếu Origin policy ở WebSocket | Kiểm tra `setAllowedOrigins` |
| App origin bị từ chối | App và API khác origin, chưa khai báo đúng | Thêm đúng HTTP(S) frontend Origin |
| Dùng `wss://api.example.com` trong allowlist | Nhầm server URL với frontend origin | Đọc header `Origin` từ browser |
| Một host giả gần giống được chấp nhận | Custom validator dùng prefix/contains sai | Test lookalike hostname, dùng allowlist chuẩn |
| Cookie không đến WS handshake | SameSite, Secure, Domain/Path hoặc browser policy | DevTools request Cookie, session |
| Handshake 401 | HTTP authentication thiếu/không hợp lệ | Kiểm tra SecurityFilterChain và principal |
| Handshake 403 | Origin không hợp lệ, proxy/security chặn hoặc request malformed | So Origin, logs và tầng trả response |
| HTTP 101 nhưng CONNECT bị chặn | CSRF token trong STOMP CONNECT thiếu/sai | Xem STOMP native headers và session |
| CONNECTED nhưng SEND/SUBSCRIBE lỗi | Inbound authorization | Kiểm tra type/destination rules |
| User nhận dữ liệu người khác | Thiếu object/tenant ACL hoặc route sai | Test dữ liệu không bị phát, không chỉ status |
| Native WebSocket hoạt động, SockJS XHR fail | CORS/HTTP CSRF/transport policy | Đọc `/info`, XHR/OPTIONS và response headers |
| Iframe fallback bị chặn | X-Frame-Options/CSP hoặc transport bị disabled | Kiểm tra nhu cầu legacy, không nới chung |
| Browser báo CSP `connect-src` | Frontend chặn kết nối | Cho đúng `https://`/`wss://` đích tin cậy |
| Trang HTTPS mở `ws://` thất bại | TLS/mixed content | Sử dụng `wss://` |
| Gateway 400/426 trước Spring | Proxy chưa hỗ trợ Upgrade/routing | Kiểm tra Upgrade/Connection/TLS |
| Duplicated ACAO trên SockJS HTTP | Nhiều CORS filters/gateway thêm headers | Thống nhất policy và nơi phát |
| `setAllowedOriginPatterns("https://*.example.com")` lọt user-content | Namespace quá rộng | Rà soát subdomains và thu hẹp pattern |
| Non-browser giả Origin và lấy dữ liệu | Origin bị dùng thay auth/ACL | Xác thực token/session, phân quyền object |
| Logout nhưng WS vẫn nhận message | Connection/subscription không được thu hồi | Đóng hoặc revalidate |
| XHR POST trả CSRF 403 | HTTP CSRF áp cho SockJS transport | Thiết kế ngoại lệ hẹp, giữ CONNECT CSRF |

## 16. Checklist trước production

- [ ] Origin allowlist của WebSocket/STOMP endpoint đã được khai báo rõ.
- [ ] Giá trị Origin là frontend `https://...`, không phải URL `wss://...`.
- [ ] Scheme/host/port được kiểm tra chính xác, không dùng so khớp tiền tố tùy tiện.
- [ ] Không dùng wildcard cho endpoint chứa dữ liệu riêng hoặc session cookie nếu không có lý do/kiểm soát đặc biệt.
- [ ] Mọi subdomain khớp pattern thuộc cùng phạm vi tin cậy; đã xét subdomain takeover/user-content.
- [ ] Test origin hợp lệ, origin lạ, khác scheme/port, hostname giả và `null`.
- [ ] HTTP handshake authentication không dựa trên Origin; session/token được xác minh.
- [ ] Native WebSocket và SockJS HTTP fallback được kiểm thử riêng.
- [ ] SockJS XHR có CORS/preflight/credentials response headers đúng, không trùng ACAO.
- [ ] CSRF HTTP transport SockJS được xử lý theo phạm vi hẹp, không tắt toàn bộ CSRF.
- [ ] STOMP CONNECT có token phù hợp khi Spring Security Messaging yêu cầu.
- [ ] Inbound SEND/SUBSCRIBE deny by default và không cho client publish thẳng broker destinations.
- [ ] Object/tenant ACL được kiểm tra trước khi phát dữ liệu.
- [ ] Browser cookie `Secure`, `HttpOnly`, `SameSite`, Domain/Path phù hợp.
- [ ] CSP `connect-src` cho phép đúng API HTTP/WSS; TLS/HSTS/proxy không bị nới lỏng bừa.
- [ ] Iframe fallback legacy không ép mở X-Frame-Options/CSP toàn hệ thống.
- [ ] Có chiến lược hết hạn/thu hồi connection, session và subscription.
- [ ] Có giới hạn payload, tốc độ SEND, subscriptions và thời gian chờ.
- [ ] Thử non-browser client giả Origin mà không thể bypass auth/authorization.
- [ ] Kiểm thử negative không có side effect hoặc rò rỉ dữ liệu, không chỉ có HTTP 403.

## 17. Câu hỏi vận dụng và đáp án

**Tình huống 1.** Frontend ở `https://app.example.com`, WebSocket URL `wss://api.example.com/ws`. Cần đặt `setAllowedOrigins` bằng giá trị nào?

**Đáp án:** `https://app.example.com`, là Origin của trang chạy JavaScript; không phải WSS server URL.

**Tình huống 2.** Spring REST API có `http.cors(...)` đúng. WebSocket từ `evil.example.org` vẫn mở được. Có mâu thuẫn không?

**Đáp án:** Không. Native WebSocket không dùng Fetch CORS preflight/ACAO; phải kiểm tra Origin ở WebSocket handshake.

**Tình huống 3.** Một nhóm dùng `setAllowedOrigins("*")` cho hệ thống có session cookie và dữ liệu cá nhân để “tránh lỗi CORS”. Rủi ro?

**Đáp án:** Có thể cho trang không tin cậy mở WebSocket bằng cookie phiên nếu browser gửi, dẫn đến CSWSH khi message security yếu. Dùng allowlist cụ thể.

**Tình huống 4.** Dùng `setAllowedOriginPatterns("https://*.example.com")` khi tổ chức có các subdomains user tự tạo. Có an toàn không?

**Đáp án:** Không thể coi là an toàn mặc định. Pattern có thể khớp trang không tin cậy; cần thu hẹp namespace hoặc allowlist đã xác minh.

**Tình huống 5.** Native WebSocket chạy nhưng SockJS XHR trả ACAO mismatch. Cần kiểm tra gì?

**Đáp án:** CORS của HTTP fallback transport, header do SockJS/Security/gateway tạo và Origin thực tế. Native WebSocket không cần ACAO theo cùng cơ chế.

**Tình huống 6.** SockJS XHR POST bị 403 bởi HTTP CSRF. Có nên tắt CSRF toàn hệ thống?

**Đáp án:** Không. Nếu cần ngoại lệ transport, giới hạn đúng URL, giữ HTTP CSRF cho API nghiệp vụ và STOMP CONNECT protection.

**Tình huống 7.** Browser legacy báo iframe SockJS bị chặn bởi `X-Frame-Options: DENY`. Nên mở frame cho toàn ứng dụng?

**Đáp án:** Không. Xác minh còn cần iframe transport; đánh giá transport hiện đại và ngoại lệ an toàn hẹp nếu thật sự bắt buộc.

**Tình huống 8.** Non-browser WebSocket client giả `Origin: https://admin.example.com`. Có được cấp quyền admin?

**Đáp án:** Không. Origin không xác thực danh tính, phải kiểm tra principal và role/ACL phía server.

**Tình huống 9.** HTTP handshake trả 101, nhưng STOMP CONNECT bị từ chối. Vì sao?

**Đáp án:** 101 chỉ xác nhận WebSocket transport. STOMP CONNECT còn có CSRF token và principal/message security riêng.

**Tình huống 10.** Origin hợp lệ, STOMP CONNECT hợp lệ, nhưng Alice SUBSCRIBE topic của Bob. Ai phải chặn?

**Đáp án:** Message authorization và business/object ACL phải kiểm tra SUBSCRIBE/ownership/tenant, Origin không phân quyền dữ liệu.

**Tình huống 11.** Origin app đúng nhưng handshake không có cookie. Có thể thêm `credentials: "include"` vào `new WebSocket` không?

**Đáp án:** Không. Browser WebSocket không hỗ trợ option đó. Kiểm tra cookie attributes và authentication architecture.

**Tình huống 12.** Ứng dụng WebFlux native WebSocket dùng `ServerHttpSecurity.pathMatchers("/ws").authenticated()`. Có tự bảo vệ Origin và từng message không?

**Đáp án:** Không. Cần Origin guard ở handshake và kiểm tra từng message trong handler/service theo principal và quyền dữ liệu.

---

**Ghi nhớ:** `setAllowedOrigins(...)` giới hạn **nguồn trang browser** được Spring WebSocket chấp nhận khi bắt tay; `setAllowedOriginPatterns(...)` tiện hơn nhưng có thể mở rộng ranh giới tin cậy. Với SockJS, policy còn ảnh hưởng HTTP/XHR fallback và transport availability, nên cần kiểm tra CORS, HTTP CSRF và security headers bên cạnh native WebSocket. **Allowed origin không phải authentication, HTTP 101 không phải STOMP authorization, và CORS của REST không tự bảo vệ WebSocket.** Hãy kết hợp allowlist chính xác, session/token, CSRF STOMP CONNECT, inbound message ACL, business ownership, CSP, TLS và kiểm thử từ cả browser lẫn client ngoài browser.
