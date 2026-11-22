# Allowed origins, triển khai qua reverse proxy và TLS

WebSocket tạo một kết nối hai chiều tồn tại lâu dài giữa trình duyệt và server. Trong môi trường production, kết nối thường đi qua reverse proxy hoặc load balancer, còn website được phục vụ bằng HTTPS. Ứng dụng Spring cần kiểm soát origin ở bước handshake, proxy phải chuyển tiếp yêu cầu nâng cấp giao thức, và TLS phải được cấu hình nhất quán từ trình duyệt tới điểm kết thúc bảo mật.

Ba phần này có vai trò riêng:

- **Allowed origins** giới hạn website được phép khởi tạo WebSocket từ trình duyệt.
- **Reverse proxy** chuyển tiếp HTTP Upgrade tới ứng dụng và truyền thông tin host/protocol gốc.
- **TLS** mã hóa kết nối trên mạng; khi website chạy HTTPS, trình duyệt cần dùng `wss://`.

Bài này tập trung vào Spring Framework trên Servlet stack, cấu hình `WebSocketConfigurer`, NGINX reverse proxy và một ứng dụng Java 17 chạy được để thử handshake.

## 1. WebSocket handshake và Origin

WebSocket bắt đầu bằng một HTTP request yêu cầu server nâng cấp giao thức:

~~~http
GET /ws/echo HTTP/1.1
Host: app.example.com
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Sec-WebSocket-Version: 13
Origin: https://app.example.com
~~~

Nếu server chấp nhận handshake, nó trả về `101 Switching Protocols`. Từ thời điểm đó, kết nối TCP được giữ mở để hai phía gửi và nhận frame WebSocket.

`Origin` mô tả origin của trang đã khởi tạo kết nối. Một origin gồm scheme, host và port:

- `https://app.example.com`
- `https://admin.example.com`
- `http://localhost:8080`

Path không thuộc origin. `https://app.example.com/app` và `https://app.example.com/other` có cùng origin. Đổi scheme, hostname hoặc port sẽ tạo origin khác.

### Vì sao phải kiểm tra Origin?

Trình duyệt tự gửi cookie hoặc thông tin xác thực gắn với website khi tạo kết nối. Nếu một website bên ngoài có thể mở WebSocket tới ứng dụng của người dùng đang đăng nhập, website đó có thể lợi dụng phiên đăng nhập để gửi lệnh hoặc đọc dữ liệu. Tình huống này thường được gọi là Cross-Site WebSocket Hijacking.

WebSocket không được bảo vệ bởi Same-Origin Policy theo cùng cách mà JavaScript truy cập tài nguyên HTTP thông thường được bảo vệ. Vì vậy, server phải kiểm tra `Origin` của handshake.

Spring WebSocket mặc định chỉ chấp nhận request cùng origin. Có thể mở rộng danh sách cho frontend hợp lệ khác, nhưng nên giữ danh sách cụ thể và có chủ đích.

Kiểm tra Origin chủ yếu bảo vệ browser client. Một chương trình native hoặc script tự tạo HTTP request có thể tự đặt header `Origin`; vì vậy, Origin không phải cơ chế xác thực người dùng. Ứng dụng vẫn phải xác thực danh tính và phân quyền các thao tác WebSocket.

## 2. Cấu hình allowed origins trong Spring

Với raw WebSocket handler, triển khai `WebSocketConfigurer` và gọi `setAllowedOrigins()` trên endpoint registration:

~~~java
@Configuration
@EnableWebSocket
public class WebSocketConfiguration implements WebSocketConfigurer {

    private final WebSocketHandler echoHandler;

    public WebSocketConfiguration(WebSocketHandler echoHandler) {
        this.echoHandler = echoHandler;
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(echoHandler, "/ws/echo")
                .setAllowedOrigins(
                        "https://app.example.com",
                        "https://admin.example.com"
                );
    }
}
~~~

Trình duyệt từ hai origin đã khai báo có thể khởi tạo handshake. Origin khác bị từ chối trước khi phiên WebSocket được thiết lập.

### setAllowedOrigins và setAllowedOriginPatterns

`setAllowedOrigins(...)` nhận danh sách origin cụ thể. Đây là lựa chọn dễ kiểm soát nhất cho production:

~~~java
registry.addHandler(echoHandler, "/ws/echo")
        .setAllowedOrigins("https://app.example.com");
~~~

`setAllowedOriginPatterns(...)` hỗ trợ pattern khi có nhiều subdomain cần cho phép:

~~~java
registry.addHandler(echoHandler, "/ws/echo")
        .setAllowedOriginPatterns("https://*.example.com");
~~~

`setAllowedOriginPatterns` có từ Spring Framework 5.3.5. Pattern cần được giới hạn trong miền mà tổ chức kiểm soát.

Nếu cần nhiều môi trường, hãy đưa danh sách origin vào cấu hình theo profile hoặc environment variable. Ví dụ:

~~~properties
app.websocket.allowed-origins=https://app.example.com,https://admin.example.com
~~~

Có thể đọc property bằng Spring Environment:

~~~java
public WebSocketConfiguration(
        EchoHandler echoHandler,
        Environment environment) {

    this.echoHandler = echoHandler;
    this.allowedOrigins = environment.getRequiredProperty(
            "app.websocket.allowed-origins", String[].class);
}
~~~

Sau đó truyền mảng này vào `setAllowedOrigins(allowedOrigins)`. Với local development, có thể override thành `http://localhost:8080`. Không đưa localhost vào allowlist production nếu không có yêu cầu cụ thể.

Spring cho phép cấu hình `*` để chấp nhận mọi origin. Cách này tiện cho thử nghiệm nhưng rất rộng đối với ứng dụng có cookie hoặc session đăng nhập. Không dùng nó như mặc định production. Nếu kết hợp với credentials của CORS/SockJS, wildcard `*` không tương thích với `allowCredentials=true`.

## 3. Allowed origins khác CORS như thế nào?

Cả CORS và WebSocket origin validation đều liên quan đến header `Origin`, nhưng không phải cùng một cơ chế.

Handshake WebSocket là HTTP Upgrade request. Trình duyệt không thực hiện CORS preflight theo cách thông thường trước khi mở WebSocket. Spring kiểm tra `Origin` trong quá trình handshake thông qua origin handshake interceptor.

Với SockJS, ngoài WebSocket transport còn có thể dùng XHR streaming hoặc polling fallback. Các transport HTTP này có thể cần CORS response headers. Spring SockJS tự bổ sung các header cần thiết nếu chưa có cấu hình CORS khác xử lý request.

Do đó:

- Cấu hình CORS cho REST API không tự động thay thế `setAllowedOrigins` trên WebSocket endpoint.
- Cấu hình allowed origins cho WebSocket không có nghĩa mọi REST endpoint đã được cấu hình CORS.
- Nếu dùng SockJS, kiểm tra cả allowed origins, CORS headers và chính sách frame của Spring Security.

Khi giới hạn allowed origins cho SockJS, một số transport dựa trên iframe không thể kiểm tra origin sẽ bị tắt. Đây là hạn chế cần tính đến nếu phải hỗ trợ trình duyệt rất cũ.

## 4. Áp dụng cho STOMP endpoint

Nếu ứng dụng dùng STOMP trên WebSocket thay vì raw WebSocket handler, allowed origins được cấu hình trên STOMP endpoint:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class StompWebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOrigins("https://app.example.com");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setApplicationDestinationPrefixes("/app");
    }
}
~~~

Client kết nối tới `/ws`, sau đó trao đổi STOMP frame qua WebSocket. Kiểm tra origin vẫn diễn ra ở handshake. Quyền truy cập destination và message cần được kiểm soát ở tầng STOMP/Spring Security.

Nếu dùng Spring Security với STOMP, cấu hình xác thực người dùng và phân quyền message destination. Spring Security có cơ chế CSRF cho STOMP CONNECT; client cần gửi CSRF token theo cấu hình. Allowed origins không thay thế xác thực, CSRF protection hoặc authorization.

Với raw WebSocket, xác thực thường được thực hiện trong HTTP handshake bằng session/cookie hoặc cơ chế xác thực phù hợp. Sau khi kết nối được thiết lập, handler vẫn phải kiểm tra người dùng có quyền thực hiện hành động được gửi trong message hay không.

## 5. Reverse proxy phải chuyển tiếp WebSocket Upgrade

Trong triển khai phổ biến, trình duyệt kết nối tới NGINX hoặc load balancer ở cổng HTTPS. Proxy chuyển request tới Spring Boot đang chạy ở cổng nội bộ.

~~~text
Browser
  |
  | wss://app.example.com/ws/echo
  | TLS + HTTP Upgrade
  v
NGINX reverse proxy :443
  |
  | HTTP/1.1 Upgrade
  | mạng nội bộ
  v
Spring application :8080
  |
  v
WebSocketHandler
~~~

HTTP `Upgrade` và `Connection` là hop-by-hop headers. Reverse proxy không tự chuyển tiếp chúng như các header thông thường. Proxy phải cấu hình chuyển tiếp tường minh để server phía sau biết client muốn nâng cấp giao thức.

Handshake thành công thường có phản hồi `101 Switching Protocols`. Nếu proxy không chuyển tiếp Upgrade, ứng dụng có thể trả về 400/404/426 hoặc kết nối bị đóng trước khi WebSocket được thiết lập.

## 6. Cấu hình NGINX cho WebSocket

Giả sử public hostname là `app.example.com`, NGINX lắng nghe HTTPS tại cổng 443, Spring Boot lắng nghe HTTP nội bộ tại `127.0.0.1:8080` và endpoint là `/ws/echo`. TLS được kết thúc tại NGINX.

Đặt `map` trong khối `http` của cấu hình NGINX:

~~~nginx
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}
~~~

Cấu hình server:

~~~nginx
upstream spring_websocket_backend {
    server 127.0.0.1:8080;
}

server {
    listen 443 ssl;
    server_name app.example.com;

    ssl_certificate     /etc/letsencrypt/live/app.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/app.example.com/privkey.pem;

    location /ws/ {
        proxy_pass http://spring_websocket_backend;

        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;

        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_set_header X-Forwarded-For $remote_addr;

        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
~~~

`map` tạo giá trị Connection phù hợp khi request có hoặc không có Upgrade. Nếu chỉ có endpoint WebSocket, cấu hình `Connection "upgrade"` trực tiếp cũng có thể hoạt động; cách dùng map dễ tái sử dụng hơn khi location xử lý nhiều loại request.

Các directive quan trọng:

- `proxy_pass` chuyển request tới Spring application.
- `proxy_http_version 1.1` dùng HTTP/1.1 cho upstream handshake.
- `proxy_set_header Upgrade` chuyển tiếp yêu cầu nâng cấp WebSocket.
- `proxy_set_header Connection` chuyển tiếp ý định upgrade.
- `proxy_set_header Host` giữ hostname public.
- `X-Forwarded-Proto` cho biết client kết nối tới proxy bằng HTTP hay HTTPS.
- `X-Forwarded-Port` cho biết cổng public mà client sử dụng.
- `X-Forwarded-For` chuyển thông tin địa chỉ client theo chính sách proxy.
- `proxy_read_timeout` giới hạn khoảng thời gian NGINX chờ dữ liệu từ upstream.

NGINX mặc định đóng kết nối proxied nếu upstream không gửi dữ liệu trong 60 giây. Với WebSocket ít message, hãy tăng `proxy_read_timeout` hoặc cấu hình heartbeat/ping để duy trì kết nối và phát hiện kết nối chết.

`proxy_pass` trong ví dụ không thêm URI phía sau hostname, vì vậy đường dẫn `/ws/echo` được giữ khi chuyển tới upstream. Nếu proxy thay đổi prefix, hãy kiểm tra quy tắc rewrite để Spring nhận đúng endpoint mapping.

### Lưu ý về X-Forwarded-For

Ví dụ dùng `$remote_addr` vì giả định NGINX là proxy biên trực tiếp. Nếu phía trước NGINX còn có load balancer đáng tin cậy, cần cấu hình trusted proxy và cách xây dựng chuỗi địa chỉ client phù hợp. Không giữ nguyên giá trị `X-Forwarded-For` tùy ý do client bên ngoài gửi lên rồi coi nó là danh tính đáng tin.

Header `Origin` của browser cần được giữ nguyên để Spring kiểm tra. Không thay `Origin` bằng `Host` hoặc `X-Forwarded-Host`; chúng biểu diễn thông tin khác nhau.

## 7. Forwarded headers trong Spring

Khi TLS kết thúc tại proxy, request từ proxy tới Spring có thể là HTTP nội bộ dù trình duyệt dùng HTTPS. Nếu ứng dụng chỉ nhìn request nội bộ, nó có thể thấy scheme `http`, port `8080` và host nội bộ. Người dùng thực tế truy cập `https://app.example.com`.

Sự khác biệt này ảnh hưởng tới URL tuyệt đối, redirect, secure-cookie logic và kiểm tra same-origin trong một số tình huống.

Spring cung cấp `ForwardedHeaderFilter` để đọc `Forwarded` hoặc `X-Forwarded-*`, sau đó bọc request/response để chúng phản ánh host, port và scheme từ góc nhìn client.

Với Spring Boot Servlet application, có thể đăng ký filter như bean:

~~~java
@Bean
public ForwardedHeaderFilter forwardedHeaderFilter() {
    return new ForwardedHeaderFilter();
}
~~~

Nếu tự đăng ký filter trong Servlet container, đặt filter ở vị trí sớm trước các filter cần đọc scheme, host hoặc port đã được điều chỉnh.

Spring Boot cũng có tùy chọn `server.forward-headers-strategy`. Chọn `framework` nếu muốn dùng Spring `ForwardedHeaderFilter`, hoặc `native` nếu container/server đã có cơ chế xử lý tương ứng. Không bật nhiều cơ chế xử lý cùng một bộ header mà chưa hiểu thứ tự và kết quả.

### Ranh giới tin cậy của forwarded headers

Ứng dụng không thể tự biết header `Forwarded` hoặc `X-Forwarded-*` đến từ proxy đáng tin cậy hay do client giả mạo. Proxy biên phải loại bỏ header forwarded do client bên ngoài gửi vào và tự ghi lại giá trị chuẩn.

Chỉ bật xử lý forwarded headers khi ứng dụng chỉ nhận request từ proxy đáng tin cậy hoặc khi mạng đã có cơ chế xác thực proxy. Nếu backend vẫn có thể truy cập trực tiếp từ Internet, client có thể giả mạo scheme/host/port mà ứng dụng tin tưởng.

`ForwardedHeaderFilter` có chế độ `removeOnly` nếu muốn xóa forwarded headers khỏi request mà không sử dụng chúng để thay đổi request wrapper. Chọn chế độ phù hợp với kiến trúc proxy.

## 8. TLS: ws:// và wss://

WebSocket có hai scheme:

- `ws://` là WebSocket không mã hóa bằng TLS.
- `wss://` là WebSocket chạy trên TLS.

Nếu website được tải qua HTTPS, browser nên kết nối WebSocket bằng `wss://`. Một trang HTTPS mở `ws://` có thể bị trình duyệt chặn như mixed content.

Ví dụ JavaScript:

~~~javascript
const socket = new WebSocket("wss://app.example.com/ws/echo");

socket.addEventListener("open", () => {
    console.log("WebSocket connected");
    socket.send("hello");
});

socket.addEventListener("message", (event) => {
    console.log("Server:", event.data);
});

socket.addEventListener("close", (event) => {
    console.log("WebSocket closed:", event.code, event.reason);
});

socket.addEventListener("error", (event) => {
    console.error("WebSocket error", event);
});
~~~

`Origin` trong handshake vẫn là origin của trang, ví dụ `https://app.example.com`. Không đặt `wss://app.example.com` vào allowed origins; allowed origin là HTTP origin gồm scheme, host và port của trang.

### TLS termination tại reverse proxy

Đây là mô hình phổ biến:

1. Browser tạo TLS connection tới NGINX bằng `wss://`.
2. NGINX kiểm tra certificate và giải mã kết nối.
3. NGINX chuyển tiếp WebSocket qua mạng nội bộ tới Spring bằng HTTP Upgrade.
4. Spring xử lý WebSocket frame.
5. NGINX chuyển frame hai chiều qua kết nối TLS đã mở với browser.

Khi dùng mô hình này, certificate public được cài tại proxy; backend Spring chỉ nên lắng nghe trên mạng nội bộ hoặc interface không public; firewall chỉ cho proxy truy cập backend; proxy gửi forwarded headers đúng; client luôn dùng `wss://` ở phía public.

TLS kết thúc tại proxy nghĩa là đoạn proxy tới backend không được mã hóa bằng TLS trong ví dụ này. Đặt backend trong mạng riêng và giới hạn quyền truy cập. Nếu cần mã hóa cả đoạn nội bộ, cấu hình TLS re-encryption: proxy dùng HTTPS tới backend và xác minh certificate backend.

### TLS trực tiếp tại Spring

Cũng có thể cấu hình Servlet container hoặc embedded server để nhận TLS trực tiếp. Với Spring Boot, ví dụ cấu hình keystore:

~~~properties
server.port=8443
server.ssl.enabled=true
server.ssl.key-store=classpath:server.p12
server.ssl.key-store-type=PKCS12
server.ssl.key-store-password=KEYSTORE_PASSWORD_FROM_ENV
~~~

Trong cấu hình thật, đặt password bằng biến môi trường hoặc secret manager; không lưu secret trực tiếp trong file cấu hình được commit. Keystore cần chứa certificate và private key phù hợp hostname.

Nếu đặt reverse proxy phía trước backend đã bật TLS, NGINX cần dùng `proxy_pass https://...` và cấu hình xác minh certificate upstream. Không tắt xác minh certificate trong production chỉ để xử lý lỗi trust.

## 9. Timeout và heartbeat cho kết nối dài hạn

HTTP request thông thường kết thúc sau khi server trả response. WebSocket giữ kết nối mở trong thời gian dài, nên timeout của proxy, load balancer, firewall và NAT có thể đóng kết nối khi không có traffic.

NGINX `proxy_read_timeout` mặc định là 60 giây giữa các lần đọc dữ liệu từ upstream. Đây không phải thời lượng tối đa tuyệt đối của phiên WebSocket. Nếu server gửi dữ liệu định kỳ, timer được làm mới.

Có thể duy trì kết nối bằng:

- WebSocket Ping/Pong frame ở tầng protocol.
- STOMP heart-beat nếu dùng STOMP.
- Message heartbeat ở tầng ứng dụng nếu phù hợp.
- Timeout proxy/load balancer đủ dài so với chu kỳ heartbeat.

Browser JavaScript WebSocket API không cung cấp phương thức trực tiếp để gửi Ping control frame. Server hoặc thư viện WebSocket có thể quản lý ping/pong. Với STOMP, hai phía có thể thương lượng heart-beat trong STOMP CONNECT/CONNECTED.

Không nên chỉ tăng timeout lên vài giờ rồi bỏ qua heartbeat. Heartbeat giúp phát hiện kết nối đã chết, giải phóng session và tài nguyên server sớm hơn.

## 10. Reverse proxy, load balancing và nhiều instance

Sau khi handshake thành công, một kết nối WebSocket được giữ trên cùng tunnel proxy tới một backend trong suốt vòng đời kết nối. Proxy không thể chuyển một kết nối TCP đang mở sang instance khác như cách cân bằng từng HTTP request ngắn.

Nếu có nhiều Spring instance:

- Mỗi WebSocket connection được định tuyến tới một instance khi handshake.
- Kết nối đó tiếp tục dùng instance đã chọn cho tới khi đóng.
- Khi client reconnect, proxy có thể chọn instance khác.
- State chỉ lưu trong bộ nhớ của một instance sẽ không tự xuất hiện ở instance mới.

Nếu ứng dụng dùng STOMP simple broker trong bộ nhớ, dữ liệu subscription và routing có phạm vi của từng instance. Khi cần nhiều node, cân nhắc STOMP broker relay hoặc kiến trúc chia sẻ state/message broker phù hợp.

Sticky session có thể giúp các HTTP fallback request của SockJS được đưa tới cùng instance, tùy kiến trúc. Tuy nhiên, sticky session không thay thế broker chia sẻ hoặc cơ chế phục hồi state khi instance bị lỗi.

## 11. SockJS khi triển khai qua proxy

SockJS bổ sung các transport fallback khi WebSocket không khả dụng. Các request fallback có thể là HTTP streaming hoặc polling, do đó proxy cần xử lý cả request HTTP thông thường bên cạnh WebSocket Upgrade.

Khi triển khai SockJS:

- Proxy phải chuyển tiếp đúng path prefix của SockJS endpoint.
- Cấu hình timeout phù hợp với streaming/polling.
- Nếu proxy buffer response, kiểm tra độ trễ của streaming transport; có thể cần tắt buffering ở location SockJS theo yêu cầu triển khai.
- Spring có thể tự thêm CORS headers cho transport XHR nếu chưa có filter khác xử lý.
- Nếu allowed origins bị giới hạn, một số iframe-based fallback transport sẽ bị vô hiệu hóa.
- Kiểm tra `X-Frame-Options` nếu ứng dụng thực sự dùng transport dựa trên iframe; không nới lỏng header bảo vệ clickjacking trên toàn website một cách tùy tiện.

Nếu tất cả client hiện đại đều hỗ trợ WebSocket, có thể không cần SockJS. Chỉ bật fallback khi có yêu cầu tương thích cụ thể.

## 12. Bảo mật kết nối WebSocket

Một handshake thành công chỉ chứng minh server chấp nhận kết nối ở thời điểm bắt đầu. Nó không tự bảo đảm mọi message sau đó đều hợp lệ.

Các lớp bảo vệ cần được phối hợp:

**Origin allowlist:** giới hạn website được phép khởi tạo kết nối từ browser.

**Authentication:** xác định người dùng từ session/cookie, OAuth2 access token hoặc cơ chế xác thực phù hợp. Đừng coi `Origin` là danh tính.

**Authorization:** kiểm tra user có quyền subscribe, publish hoặc gọi hành động tương ứng. Với STOMP, phân quyền destination và message type; với raw WebSocket, kiểm tra quyền trong handler/service.

**CSRF:** nếu dùng cookie-based authentication, đánh giá nguy cơ Cross-Site WebSocket Hijacking. Với STOMP và Spring Security, cấu hình CSRF token cho CONNECT theo hướng dẫn bảo mật.

**TLS:** dùng `wss://` cho traffic public, quản lý certificate, private key và chu kỳ gia hạn.

**Proxy trust:** chỉ tin forwarded headers do proxy biên ghi lại. Chặn truy cập trực tiếp tới backend nếu thiết kế yêu cầu mọi request phải đi qua proxy.

**Resource limits:** giới hạn kích thước message, số kết nối, tốc độ gửi, thời gian idle và hàng đợi outbound để tránh một client chiếm tài nguyên quá mức.

## 13. Ví dụ hoàn chỉnh: Spring Boot WebSocket echo

Ví dụ dùng Java 17, Spring Boot 3.4.4 và `spring-boot-starter-websocket`. Ứng dụng tạo raw WebSocket endpoint `/ws/echo`, chỉ chấp nhận origin cấu hình trong property `app.websocket.allowed-origins`, rồi phản hồi nội dung client gửi.

Cấu trúc:

~~~text
websocket-origin-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       ├── WebSocketApplication.java
        │       ├── WebSocketConfiguration.java
        │       └── EchoHandler.java
        └── resources/
            └── application.properties
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>websocket-origin-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.4</version>
        <relativePath/>
    </parent>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-websocket</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/WebSocketApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebSocketApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebSocketApplication.class, args);
    }
}
~~~

### src/main/java/demo/EchoHandler.java

~~~java
package demo;

import org.springframework.stereotype.Component;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

@Component
public class EchoHandler extends TextWebSocketHandler {

    @Override
    protected void handleTextMessage(
            WebSocketSession session,
            TextMessage message) throws Exception {

        session.sendMessage(
                new TextMessage("echo: " + message.getPayload()));
    }
}
~~~

### src/main/java/demo/WebSocketConfiguration.java

~~~java
package demo;

import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class WebSocketConfiguration implements WebSocketConfigurer {

    private final EchoHandler echoHandler;
    private final String[] allowedOrigins;

    public WebSocketConfiguration(
            EchoHandler echoHandler,
            Environment environment) {

        this.echoHandler = echoHandler;
        this.allowedOrigins = environment.getRequiredProperty(
                "app.websocket.allowed-origins", String[].class);
    }

    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(echoHandler, "/ws/echo")
                .setAllowedOrigins(allowedOrigins);
    }
}
~~~

### src/main/resources/application.properties

~~~properties
server.port=8080
app.websocket.allowed-origins=https://app.example.com
~~~

Chạy ứng dụng:

~~~shell
mvn spring-boot:run
~~~

Để thử trên máy local, override origin bằng:

~~~shell
mvn spring-boot:run -Dspring-boot.run.arguments=--app.websocket.allowed-origins=http://localhost:8080
~~~

Mở trang web từ `http://localhost:8080` rồi chạy JavaScript:

~~~javascript
const socket = new WebSocket("ws://localhost:8080/ws/echo");

socket.addEventListener("open", () => {
    console.log("connected");
    socket.send("hello");
});

socket.addEventListener("message", (event) => {
    console.log(event.data);
});
~~~

Output trong browser console:

~~~text
connected
echo: hello
~~~

Nếu mở trang từ một origin khác không có trong allowlist, handshake sẽ bị từ chối. Khi triển khai public qua NGINX với TLS, client đổi URL thành `wss://app.example.com/ws/echo` và cấu hình allowed origin thành `https://app.example.com`.

Ví dụ này xác nhận cấu hình Spring handler và origin allowlist. Để xác nhận toàn bộ production path, cần thử handshake qua NGINX, certificate thật, forwarded headers, timeout và authentication của môi trường triển khai.

## 14. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| HTTP 400/404/426 khi mở WebSocket | Sai path hoặc proxy không chuyển Upgrade | Kiểm tra `Upgrade`, `Connection`, `proxy_http_version` và mapping endpoint |
| HTTP 403 ở handshake | Origin không nằm trong allowlist hoặc bị security filter từ chối | Kiểm tra request `Origin`, allowed origins và security log |
| Chạy local được nhưng qua proxy thất bại | Sai path rewrite, host hoặc forwarded headers | So sánh URL public với upstream path và request metadata |
| Browser báo mixed content | Trang HTTPS đang mở `ws://` | Dùng `wss://` |
| Kết nối tự đóng sau khoảng một phút | Proxy/load balancer idle timeout | Kiểm tra `proxy_read_timeout` và heartbeat |
| Redirect hoặc URL tạo ra dùng http | Ứng dụng chỉ thấy scheme nội bộ sau TLS termination | Gửi forwarded headers và cấu hình xử lý trusted forwarded headers |
| SockJS polling hoạt động nhưng WebSocket không hoạt động | Proxy chỉ hỗ trợ HTTP fallback, thiếu Upgrade forwarding | Kiểm tra NGINX location và handshake 101 |
| Client kết nối được nhưng gọi API bị từ chối | Authentication/authorization ở tầng message hoặc HTTP chưa phù hợp | Kiểm tra principal, token, CSRF và destination authorization |
| Kết nối reconnect nhưng mất subscription/state | Reconnect vào instance khác hoặc state chỉ ở bộ nhớ local | Dùng broker/state chia sẻ và thiết kế khôi phục subscription |

Khi chẩn đoán, xem cả log browser, access/error log của proxy và log Spring. Một handshake đi qua nhiều lớp; status code ở proxy có thể khác lỗi gốc của backend nếu proxy tự từ chối hoặc timeout.

## 15. Checklist triển khai production

- Endpoint chỉ mở trên path cần thiết.
- Allowed origins liệt kê scheme, host và port chính xác.
- Không dùng wildcard origin cho ứng dụng có session/credentials.
- Authentication và authorization được cấu hình độc lập với Origin.
- STOMP CONNECT có CSRF protection khi dùng Spring Security theo cấu hình tương ứng.
- NGINX chuyển tiếp `Upgrade` và `Connection`.
- Upstream dùng HTTP/1.1 cho handshake theo cấu hình tương thích.
- `Host`, `X-Forwarded-Host`, `X-Forwarded-Proto` và port phản ánh URL public.
- Proxy biên xóa forwarded headers không đáng tin từ client.
- Backend chỉ được truy cập từ proxy hoặc mạng nội bộ được phép.
- Certificate có hostname đúng, còn hạn và được gia hạn tự động.
- Browser dùng `wss://` khi website chạy HTTPS.
- Idle timeout và heartbeat được thống nhất giữa proxy, load balancer và ứng dụng.
- SockJS fallback, CORS và X-Frame-Options được kiểm thử nếu sử dụng.
- Concurrency, giới hạn message size, rate limit và số kết nối có giới hạn phù hợp.
- Có giám sát số session đang mở, handshake failure, close code, idle timeout và reconnect rate.
- Kiểm thử qua đúng đường đi public, không chỉ gọi thẳng backend localhost.

## 16. Ghi nhớ

- WebSocket handshake bắt đầu bằng HTTP Upgrade và thành công khi server trả `101 Switching Protocols`.
- Spring WebSocket mặc định chỉ cho phép same-origin; dùng `setAllowedOrigins` hoặc `setAllowedOriginPatterns` để mở rộng có kiểm soát.
- Origin gồm scheme, host và port; không gồm path và không dùng scheme `ws://`/`wss://`.
- Origin validation chủ yếu bảo vệ browser; client ngoài browser có thể giả mạo header, nên vẫn cần authentication và authorization.
- WebSocket origin validation khác với CORS; SockJS fallback có thể cần CORS cho XHR transports.
- Reverse proxy phải chuyển tiếp `Upgrade` và `Connection`, đồng thời giữ đúng path.
- TLS termination tại NGINX cho phép client dùng `wss://` trong khi proxy chuyển tiếp `ws://` trên mạng nội bộ.
- `ForwardedHeaderFilter` giúp Spring hiểu scheme/host/port public, nhưng chỉ được tin forwarded headers do proxy đáng tin cậy tạo.
- WebSocket là kết nối dài hạn; cấu hình timeout và heartbeat cho proxy/load balancer.
- Khi chạy nhiều instance, connection gắn với một backend trong suốt phiên; state cần được chia sẻ hoặc khôi phục khi reconnect.

## Tài liệu tham khảo

- [Spring Framework 6.2 — WebSocket Server Configuration and Allowed Origins](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/server.html)
- [Spring Framework 6.2 — WebSocket Overview and Handshake](https://docs.spring.io/spring-framework/reference/6.2/web/websocket.html)
- [Spring Framework 6.2 — SockJS Fallback and CORS](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/fallback.html)
- [Spring Framework 6.2 — Forwarded Headers and ForwardedHeaderFilter](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/filters.html)
- [Spring Security — WebSocket Same Origin and CSRF](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html)
- [NGINX — WebSocket Proxying](https://nginx.org/en/docs/http/websocket.html)
- [RFC 6455 — The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455)
