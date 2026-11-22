# SockJS fallback và các ràng buộc khi đi qua proxy

## 1. Mục tiêu và phạm vi

WebSocket tạo kênh giao tiếp hai chiều, tồn tại lâu giữa trình duyệt và máy chủ. Tuy nhiên đường đi thực tế thường gồm trình duyệt → proxy của doanh nghiệp/CDN → load balancer hoặc reverse proxy → Spring application. Một proxy có thể không chuyển tiếp WebSocket Upgrade, đóng kết nối tưởng như rảnh, hoặc buffer phản hồi HTTP khiến dữ liệu streaming không đến được trình duyệt đúng lúc.

**SockJS** là giao thức mô phỏng trải nghiệm WebSocket, ưu tiên dùng WebSocket khi có thể, rồi chuyển sang các **HTTP transports** phù hợp (HTTP streaming hoặc long polling) khi cần. Spring Framework cung cấp server SockJS trên **Servlet stack** cùng khả năng tích hợp STOMP messaging. SockJS không sửa được mọi lỗi mạng, không tự cung cấp message broker và cũng không thay thế cấu hình reverse proxy đúng.

Sau bài này, bạn sẽ:
- Hiểu trình tự chọn transport: `/info` → WebSocket → streaming/polling, và vì sao fallback vẫn có thể thất bại.
- Phân biệt WebSocket Upgrade với các HTTP GET/POST của SockJS; biết những path và header proxy không được chặn.
- Cấu hình Spring MVC + STOMP + SockJS và client trình duyệt với ví dụ Java 17/Spring Boot 3.3.x có thể chạy.
- Đánh giá timeout, buffering, heartbeat, CORS, Origin, cookie, CSRF và security khi reverse proxy/LB đứng giữa.
- Hiểu sticky session và giới hạn của simple STOMP broker khi scale nhiều instance.
- Tái hiện lỗi và kiểm thử **đúng fallback transport**, không kết luận từ duy nhất một WebSocket handshake thành công.

### Có thật sự cần SockJS?

Trình duyệt hiện đại hầu hết hỗ trợ WebSocket. Nếu mạng, proxy và thiết bị client của hệ thống đều hỗ trợ WebSocket ổn định, **STOMP over native WebSocket thường đơn giản hơn**: ít đường truyền, ít request phụ, ít chi phí tương thích. Chỉ bật SockJS nếu cần hỗ trợ đường mạng không cho WebSocket hoạt động hoặc một nhóm client cũ được xác định. Đừng kích hoạt SockJS theo phản xạ chỉ vì ứng dụng sử dụng STOMP.

## 2. Các lớp giao thức cần phân biệt

| Lớp | Vai trò | Ví dụ |
| --- | --- | --- |
| TCP/TLS | Kết nối vận chuyển; HTTPS/WSS mã hóa đường truyền | Trình duyệt ↔ proxy |
| HTTP / WebSocket handshake | Upgrade từ HTTP sang WebSocket; hoặc request HTTP bình thường | GET + Upgrade, trạng thái 101 |
| SockJS | Chọn WebSocket hoặc mô phỏng qua HTTP, quản lý session/frames ở tầng transport | `/ws/info`, `/ws/{server}/{session}/xhr` |
| STOMP | Giao thức SEND/SUBSCRIBE/MESSAGE trên kênh đã mở | SUBSCRIBE `/topic/greetings` |
| Spring application | Xử lý message ở `@MessageMapping` và publish qua broker | `/app/hello` |

**SockJS không đồng nghĩa STOMP.** Có thể dùng SockJS cùng WebSocketHandler không có STOMP. Ngược lại có thể dùng STOMP trên WebSocket native không có SockJS. Khi ứng dụng cấu hình `registry.addEndpoint("/ws").withSockJS()`, `/ws` là **HTTP base URL của SockJS endpoint**, không phải địa chỉ STOMP destination. Client STOMP thường dùng `webSocketFactory` tạo SockJS rồi gửi STOMP frames qua connection đó.

### 2.1. Đường kết nối SockJS

Giả sử ứng dụng triển khai endpoint `/ws`:

1. Trình duyệt gọi `GET https://example.org/ws/info`. Response JSON cho biết một số khả năng của server, chẳng hạn `websocket`, `cookie_needed`, entropy. URL `/info` phải đến được server; status 404/403/502 tại đây có thể làm kết nối chết **trước khi** thử WebSocket.
2. Nếu điều kiện trình duyệt/mạng cho phép, SockJS thử WebSocket tại path có định danh session. Phía proxy phải chuyển handshake và sau đó duy trì kết nối hai chiều.
3. Nếu không thể dùng WebSocket, SockJS có thể dùng HTTP streaming: một request giữ mở để server đẩy dữ liệu xuống; HTTP POST khác gửi dữ liệu lên.
4. Nếu streaming không khả dụng, client có thể chuyển sang HTTP long polling: duy trì một request nhận dữ liệu, trả response khi có dữ liệu/timeout rồi mở request kế tiếp; request gửi dữ liệu vẫn riêng.
5. Khi kênh mở, STOMP client gửi CONNECT rồi SUBSCRIBE/SEND như bình thường. Đổi transport không đồng nghĩa đổi destination hoặc server-side `@MessageMapping`.

**Không đảm bảo** client nào cũng luôn “WebSocket hỏng thì thành công bằng polling”. CORS, cookies, streaming proxy, authentication, session affinity, policy mạng và giới hạn kết nối đều có thể làm fallback hỏng. Chính client SockJS quyết định danh sách transports được hỗ trợ; giới hạn transports trong test để xác định từng đường truyền.

### 2.2. Cấu trúc URL và session

Các request transport thường nằm dưới:

~~~text
https://example.org/ws/{server-id}/{session-id}/{transport}
~~~

Ví dụ URL ở cấp HTTP, minh họa chứ không phải session thật:

~~~text
GET  /ws/info
GET  /ws/123/sessionABC/websocket       # WebSocket Upgrade
POST /ws/123/sessionABC/xhr             # Nhận dữ liệu qua long polling
POST /ws/123/sessionABC/xhr_send        # Gửi dữ liệu qua HTTP
POST /ws/123/sessionABC/xhr_streaming   # Nhận dữ liệu streaming
~~~

Trong tên **transport của client SockJS** có thể thấy `xhr-polling` hoặc `xhr-streaming`, còn **đoạn path HTTP thực tế** của protocol có dạng `xhr`, `xhr_send`, `xhr_streaming`. Dựa vào tab Network để kiểm tra tên thực tế; đừng xây proxy chỉ cho phép duy nhất `/ws/websocket`.

- `server-id`: một thành phần URL có thể hỗ trợ quy tắc định tuyến ở load balancer; tự nó **không** đảm bảo cùng session sẽ luôn đến đúng backend.
- `session-id`: liên kết những request HTTP của cùng phiên SockJS. Một kết nối long polling cần gửi nhiều request với cùng định danh này.
- `transport`: cơ chế vận chuyển, ảnh hưởng method, thời gian mở kết nối và response framing.
- STOMP destinations như `/topic/greetings` **không phải URL HTTP để proxy rewrite**; chúng nằm trong nội dung frame STOMP.

SockJS frame có thể bắt đầu bằng `o` (mở), `h` (heartbeat), `a["..."]` (array messages), hoặc `c[...]` (đóng). Đây là tầng framing SockJS; bên trong payload có thể chứa STOMP frames. Nếu nhìn thấy `o` ở Network, mới chỉ biết SockJS session được mở, **chưa chứng minh STOMP CONNECT và SUBSCRIBE thành công**.

## 3. Spring server: bật SockJS đúng cách

Để dùng STOMP trên Spring MVC, cấu hình `@EnableWebSocketMessageBroker`, chọn endpoint HTTP và destinations. Mẫu tối thiểu:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {
    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
            .withSockJS();
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic");
    }
}
~~~

Đây là đoạn cấu hình tích hợp, import thuộc `org.springframework.context.annotation` và `org.springframework.web.socket.config.annotation`. `withSockJS()` bật transport fallback; nếu bỏ nó, dùng native WebSocket endpoint và tạo client bằng WebSocket URL `ws://`/`wss://` thay cho SockJS HTTP base URL.

Một controller:

~~~java
@Controller
public class GreetingController {
    @MessageMapping("/hello")
    @SendTo("/topic/greetings")
    public Greeting greet(HelloMessage message) {
        return new Greeting("Xin chào, " + message.name());
    }
}
~~~

`HelloMessage`/`Greeting` là DTO của ứng dụng. Client SEND `/app/hello` được route tới method `@MessageMapping("/hello")`; người đã SUBSCRIBE `/topic/greetings` nhận kết quả. Proxy không cần biết các destination STOMP đó.

**CORS/Origin:** mặc định Spring WebSocket/SockJS chỉ chấp nhận cùng origin. Nếu web UI ở `https://app.example.org` và backend ở `https://api.example.org`, phải chủ động thiết kế cross-origin, xác thực và cookies. Ví dụ endpoint:

~~~java
registry.addEndpoint("/ws")
    .setAllowedOrigins("https://app.example.org")
    .withSockJS();
~~~

Snippet trên chỉ minh họa **một origin được tin cậy**; không dùng `"*"` tùy tiện khi có credentials. Khi origin bị giới hạn cụ thể, một số SockJS iframe transports không thể kiểm tra Origin có thể bị vô hiệu hóa. Trình duyệt có thể hỗ trợ fallback XHR bình thường mà không cần iframe; cần test các client thật của sản phẩm.

### Vì sao SockJS server khác WebFlux reactive endpoint?

Tích hợp `withSockJS()` và STOMP broker trong ví dụ thuộc cơ chế **Servlet / Spring MVC** của Spring Framework. Đừng áp nguyên cấu hình này vào một WebFlux-only handler và kỳ vọng tự có SockJS fallback tương đương. Hãy chọn stack, starter và annotation tương ứng. Trong môi trường tải cao, HTTP long polling/streaming tiêu thụ tài nguyên khác WebSocket native; đo thread/connection và memory theo stack triển khai.

## 4. Reverse proxy: hai dạng traffic phải cùng hoạt động

### 4.1. WebSocket Upgrade

Handshake WebSocket trên HTTP/1.1 thường có:

~~~http
GET /ws/123/sessionABC/websocket HTTP/1.1
Host: example.org
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Key: ...
Sec-WebSocket-Version: 13
~~~

`101 Switching Protocols` là dấu hiệu server chấp nhận Upgrade. Các header `Upgrade` và `Connection` thuộc nhóm hop-by-hop; proxy cần cấu hình chuyển đúng sang upstream. Sau 101, proxy phải duy trì kênh hai chiều, không tiếp tục xử lý từng message như request HTTP độc lập.

**Không copy nguyên `Connection: Upgrade` cho mọi HTTP request.** Với GET `/info` hoặc POST polling bình thường, không có handshake Upgrade; một số proxy config nên dùng map để chọn giá trị theo `$http_upgrade`.

### 4.2. HTTP streaming và polling

Khi WebSocket không được phép, proxy vẫn phải:
- Cho phép `GET /ws/info`, `OPTIONS` CORS khi cần, và HTTP `POST` cho polling/streaming/send. Không định tuyến SockJS chỉ theo GET WebSocket.
- Chuyển đúng **toàn bộ sub-path của `/ws/`**, không rewrite mất `{server-id}/{session-id}`. Đặc biệt lưu ý `proxy_pass` có hoặc không có trailing slash sẽ ảnh hưởng URI forwarding trong NGINX.
- Không cache `/info`, session frames hoặc những response polling/streaming nhạy cảm theo trạng thái phiên.
- Tránh response buffering cho streaming vì buffer có thể giữ dữ liệu đến khi đủ lớn mới gửi khiến trình duyệt tưởng kết nối “im lặng”.
- Cho phép request/response có thời gian tồn tại dài hơn HTTP REST thông thường. Kiểm tra timeout của *mọi tầng*: CDN/LB, reverse proxy, backend, và client.
- Giữ nguyên query, method, cookies, Content-Type, Origin và các header cần cho CORS/authentication.
- Cho phép nhiều HTTP request trong cùng session đi qua cùng backend hoặc có chiến lược session routing phù hợp.

**Streaming** đặc biệt nhạy với proxy buffering; **polling** đặc biệt nhạy với số lượng request, sticky session, CORS và giới hạn concurrent connections. Cấu hình tốt cho 101 chưa chắc tốt cho `xhr_streaming`/`xhr`.

### 4.3. Ví dụ NGINX minh họa

Đây là fragment để đưa vào cấu hình NGINX có sẵn; giả sử đã có `server` phục vụ `example.org` và ứng dụng Spring lắng nghe tại `127.0.0.1:8080`. `map` đặt trong `http` context, `location` đặt trong `server` context:

~~~nginx
# Đặt trong http { ... }
map $http_upgrade $connection_upgrade {
    default upgrade;
    ''      close;
}

# Đặt trong server { ... } của example.org
location /ws/ {
    # Không đặt dấu / cuối proxy_pass: giữ nguyên /ws/... cho Spring.
    proxy_pass http://127.0.0.1:8080;
    proxy_http_version 1.1;

    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection $connection_upgrade;

    proxy_buffering off;       # Quan trọng với SockJS HTTP streaming
    proxy_cache off;
    proxy_read_timeout 75s;    # Ví dụ: phải kiểm tra thực tế với heartbeat
    proxy_send_timeout 75s;
}
~~~

Fragment này **không phải file NGINX standalone**; còn phải cấu hình listener, TLS/certificates, routes khác, security và load balancer theo hệ thống thật. Nếu route đặt dưới prefix khác (ví dụ public `/api/ws` còn Spring là `/ws`), phải thiết kế rewrite và các forwarded headers tương ứng; không thử ngẫu nhiên nhiều dấu `/` khi deploy.

Tại môi trường production HTTPS, trình duyệt sẽ truy cập SockJS qua `https://example.org/ws`; transport WebSocket nội bộ có thể dùng `wss://` ở browser và được TLS-terminate tại edge. Không được trộn trang HTTPS với endpoint `http://`/`ws://` không an toàn vì mixed-content policy. Đảm bảo upstream nhận thông tin scheme/host chuẩn nếu ứng dụng cần sinh absolute URLs; chỉ tin `X-Forwarded-*` từ reverse proxy được kiểm soát.

**Giá trị 75s** ở ví dụ không phải chuẩn bắt buộc. Một số môi trường cắt ở 30/60/120 giây; đặt timeout cao hơn nhịp dữ liệu/heartbeat có biên an toàn, nhưng vẫn có giới hạn tài nguyên và timeout ứng dụng. Kiểm tra cả idle timeout của LB trước NGINX, bởi NGINX không thể vượt qua giới hạn ở hop phía ngoài.

## 5. Heartbeat, session lifecycle và timeout

SockJS có heartbeat frame `h` để tránh một số proxy coi kết nối yên lặng là chết. Theo cấu hình mặc định phổ biến của Spring, heartbeat SockJS được phát khoảng **25 giây** nếu không có message. Có thể thay đổi bằng:

~~~java
registry.addEndpoint("/ws")
    .withSockJS()
    .setHeartbeatTime(25_000);
~~~

Đây là snippet để tích hợp vào `registerStompEndpoints`; thời gian tính bằng **milliseconds**. Khi STOMP client và server đàm phán heartbeat STOMP, Spring không tiếp tục phát SockJS heartbeats độc lập theo cách thường thấy. Vì thế **đừng giả định lúc nào cũng có một frame `h` mỗi 25 giây**. Khi phân tích timeout, phải xem **traffic thực tế** được gửi trên kết nối (STOMP heartbeat, SockJS heartbeat hoặc messages khác).

Các giới hạn liên quan:
- **Proxy read/idle timeout:** quá ngắn có thể cắt WebSocket hoặc streaming dù app đang hoạt động.
- **Heartbeat scheduler:** thread pool thiếu công suất có thể làm heartbeat trễ dưới tải lớn; cần metric và sizing.
- **Disconnect delay:** với HTTP polling, khoảng ngắt giữa các receiving requests không nên khiến server kết luận session mất quá sớm khi mạng chậm.
- **Stream bytes limit/message cache:** streaming có thể kết thúc và nối lại để quản lý buffer; polling có thể cần cache messages giữa các request.
- **Client reconnect delay:** reconnect tạo session mới, cần SUBSCRIBE lại và xét liệu thông điệp lúc mất mạng có cần replay/ack hay không.

SockJS không cung cấp exactly-once delivery hay bảo đảm history replay. Nếu ứng dụng chat/trading cần không mất message, tầng nghiệp vụ phải có sequence ID, ACK, snapshot/replay hoặc durable broker theo yêu cầu.

## 6. Load balancer, sticky session và cluster

SockJS HTTP fallback thường gồm nhiều request cho cùng `session-id`: request nhận message, request gửi message, request nhận tiếp. Các thành phần state của SockJS session nằm tại server xử lý nó. Nếu LB phân tán ngẫu nhiên request đến các Spring instances, instance B có thể không tìm thấy session do instance A tạo. Dấu hiệu hay gặp: kết nối thành công rồi `404` cho `xhr_send`, đóng bất thường hoặc reconnect lặp.

~~~mermaid
flowchart LR
    B[Browser SockJS] --> L[Load balancer]
    L -->|info / first request| A[Spring instance A]
    L -.->|xhr_send same session, sai route| C[Spring instance B]
    A --- M[Session tại A]
    C --- E[Không có session tại B]
~~~

**Sticky session/session affinity** là giải pháp thường dùng: các request cùng một SockJS session đi tới một instance. LB có thể dùng cookie phù hợp, hoặc route có cơ chế ánh xạ rõ ràng; thành phần `server-id` trong URL chỉ có tác dụng khi LB **thực sự cấu hình luật để dùng nó**. Đừng suy ra rằng SockJS tự giải quyết sticky session.

Hai vấn đề khác nhau cần giải quyết riêng:
1. **Routing transport/session:** cùng SockJS session tới đúng node. Sticky routing giúp giữ trạng thái session.
2. **Phân phối message giữa nhiều nodes:** `enableSimpleBroker` là broker trong bộ nhớ của một ứng dụng và **không là broker cluster dùng chung**. Khi cần cross-instance subscriptions và routing phức tạp, xem xét external STOMP broker/relay và kiến trúc phân phối message tương ứng. Thêm broker relay **không tự thay thế** yêu cầu xử lý các HTTP request thuộc cùng SockJS session tại một node.

Khi node chết, sticky session không cứu được socket/session đang kết nối với node đó. Client cần reconnect, xác thực lại, subscribe lại; ứng dụng phải tự thiết kế phục hồi dữ liệu chưa nhận.

## 7. Origin, CORS, cookie, CSRF và authentication khi qua proxy

### 7.1. Origin và CORS

WebSocket handshake có header `Origin`, nhưng WebSocket trong browser không tuân thủ toàn bộ chính sách same-origin giống XMLHttpRequest. Spring có kiểm soát allowed origins ở endpoint; Spring Security có thể bổ sung kiểm soát khi xử lý STOMP CONNECT.

SockJS fallback HTTP qua XHR/polling tuân theo CORS của trình duyệt. Khi cross-origin, **OPTIONS preflight** có thể chạy trước POST; proxy/WAF không được tùy tiện chặn. Spring SockJS có thể tự thêm CORS headers nếu ứng dụng chưa gắn headers. Nếu filter/gateway đã thêm headers, cần tránh trả hai giá trị `Access-Control-Allow-Origin` mâu thuẫn. Khi dùng cookie, `Access-Control-Allow-Origin: *` không thể đi với credentialed requests theo CORS.

Một số việc cần kiểm:
- `Origin` do trình duyệt gửi là origin của trang UI, không phải luôn giống `Host` của backend.
- `Access-Control-Allow-Credentials`, cookie `SameSite`/`Secure` và chính sách third-party cookies có thể khiến auth hoạt động với WebSocket nhưng hỏng trên polling.
- CORS là chính sách browser. Client ngoài browser có thể giả `Origin`; authorization phía server vẫn bắt buộc.
- Giữ danh sách origins ngắn và cụ thể, dùng HTTPS; hạn chế pattern quá rộng.

### 7.2. Cookie và thông tin phiên

Request `/info` có thể trả `cookie_needed`, liên quan quyết định transport của SockJS. Trong Java Servlet, `JSESSIONID` thường được sử dụng; điều này không đồng nghĩa mọi ứng dụng đều bắt buộc dùng session cookie. Nếu JWT được dùng, phải hiểu rõ token đi ở đâu: WebSocket browser API hạn chế tự đặt arbitrary HTTP headers; SockJS XHR và STOMP CONNECT cũng có giới hạn khác nhau. Không truyền token trong query string một cách tùy tiện vì URL dễ xuất hiện trong log, analytics và proxy.

Proxy phải chuyển tiếp cookie khi session/auth cần nó. Với load balancer cookie-based stickiness, kiểm tra cookie được browser gửi tới các HTTP request `/ws/.../xhr` và `/xhr_send` hay không. Header `JSESSIONID` có thể hỗ trợ affinity, nhưng không chứng minh LB đã bật sticky mode.

### 7.3. CSRF và iframe

Với Spring Security STOMP, CSRF protection cho `CONNECT` giúp chống kết nối cross-site dùng session cookie. Với SockJS HTTP fallback, `CONNECT` nằm trong dữ liệu transport; không thể đơn giản gắn CSRF token bằng tùy chọn header HTTP của SockJS như một REST call. Theo tài liệu Spring Security, cung cấp CSRF token trong **STOMP connect headers**, đồng thời nếu cần thì ngoại lệ CSRF phía HTTP nên **chỉ áp dụng cho các SockJS endpoint liên quan**, không tắt toàn site.

Các iframe transports cũ còn vướng `X-Frame-Options: DENY`/CSP `frame-ancestors`. Nếu thật sự cần iframe cùng origin, cần policy phù hợp như SAMEORIGIN và cân nhắc nguồn tải SockJS client library. Với cấu hình allowed origins hạn chế, Spring có thể vô hiệu hóa các iframe transports có nguy cơ không kiểm origin. **Không hạ security mặc định chỉ để giữ mọi browser quá cũ**; chọn danh sách browser được hỗ trợ và test.

## 8. Ví dụ hoàn chỉnh Java 17 + Spring Boot 3.3: WebSocket và ép xhr-polling

Ví dụ cung cấp một Spring Boot app, STOMP echo endpoint, HTML client dùng SockJS + STOMP và test `/ws/info`. Trên trang web có tham số URL để **ép XHR long polling**, nhờ đó ta chứng minh fallback HTTP thực sự hoạt động thay vì chỉ kiểm WebSocket native.

Yêu cầu: **JDK 17+**, Maven, browser có thể tải hai thư viện JS từ CDN. Phần backend có thể chạy khi dependencies Maven đã có sẵn; để chạy browser hoàn toàn offline, tải/cấp phát hai thư viện JS từ static assets của ứng dụng thay cho CDN theo chính sách bản quyền/vận hành của dự án. Mẫu ghim Spring Boot `3.3.13` để tương thích API Spring Framework 6.1 và Java 17; ứng dụng mới nên cân nhắc một dòng Spring Boot hiện còn hỗ trợ.

### 8.1. Thư mục

~~~text
sockjs-proxy-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/SockJsDemoApplication.java
    │   └── resources/static/index.html
    └── test/
        └── java/demo/SockJsInfoTest.java
~~~

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>sockjs-proxy-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-websocket</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

`spring-boot-starter-websocket` cung cấp Spring MVC WebSocket/STOMP support và Jackson phù hợp. Không cần cài WebFlux hoặc broker server bên ngoài cho demo một instance.

### 8.3. src/main/java/demo/SockJsDemoApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@SpringBootApplication
public class SockJsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(SockJsDemoApplication.class, args);
    }

    public record HelloMessage(String name) {}
    public record Greeting(String content) {}

    @Configuration
    @EnableWebSocketMessageBroker
    public static class WsConfig implements WebSocketMessageBrokerConfigurer {

        @Override
        public void registerStompEndpoints(StompEndpointRegistry registry) {
            // Cho cùng origin; cross-origin phải được cấu hình có chủ đích.
            registry.addEndpoint("/ws")
                .withSockJS()
                .setHeartbeatTime(25_000);
        }

        @Override
        public void configureMessageBroker(MessageBrokerRegistry registry) {
            registry.setApplicationDestinationPrefixes("/app");
            registry.enableSimpleBroker("/topic");
        }
    }

    @Controller
    public static class GreetingController {
        @MessageMapping("/hello")
        @SendTo("/topic/greetings")
        public Greeting greet(HelloMessage input) {
            return new Greeting("Xin chào, " + input.name());
        }
    }
}
~~~

Giải thích: `/ws` nhận SockJS/transport; `/app/hello` là STOMP SEND destination chuyển vào GreetingController; `/topic/greetings` là subscription qua simple broker. `Greeting` được Jackson serialize JSON từ Java record. Ví dụ cố ý không có authentication để tập trung vào vận chuyển trong môi trường localhost. **Không công khai endpoint demo như một production chat service** mà chưa bổ sung authentication, authorization và message validation.

### 8.4. src/main/resources/static/index.html

~~~html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SockJS transport demo</title>
</head>
<body>
  <h1>SockJS + STOMP</h1>
  <p id="state">Đang khởi tạo...</p>
  <button id="send" disabled>Gửi lời chào</button>
  <pre id="log"></pre>

  <script src="https://cdn.jsdelivr.net/npm/sockjs-client@1.6.1/dist/sockjs.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/@stomp/stompjs@7.2.0/bundles/stomp.umd.min.js"></script>
  <script>
    const status = document.getElementById("state");
    const button = document.getElementById("send");
    const log = document.getElementById("log");
    const forcePolling =
      new URLSearchParams(window.location.search).get("transport") === "polling";

    const client = new StompJs.Client({
      // SockJS nhận URL HTTP(S), không truyền ws:// như native WebSocket.
      webSocketFactory: () => new SockJS(
        "/ws",
        null,
        forcePolling ? { transports: ["xhr-polling"] } : {}
      ),
      reconnectDelay: 3000,
      heartbeatIncoming: 10000,
      heartbeatOutgoing: 10000,
      onConnect: () => {
        status.textContent = forcePolling
          ? "Đã kết nối STOMP bằng xhr-polling"
          : "Đã kết nối STOMP bằng SockJS";
        button.disabled = false;
        // Đặt SUBSCRIBE trong onConnect vì reconnect tạo session mới.
        client.subscribe("/topic/greetings", frame => {
          const body = JSON.parse(frame.body);
          log.textContent += body.content + "\n";
        });
      },
      onWebSocketClose: () => {
        button.disabled = true;
        status.textContent = "Kết nối đóng; thử reconnect...";
      },
      onStompError: frame => {
        status.textContent = "Broker báo lỗi: " + frame.headers.message;
      }
    });

    button.addEventListener("click", () => {
      client.publish({
        destination: "/app/hello",
        body: JSON.stringify({ name: "Spring" }),
        headers: { "content-type": "application/json" }
      });
    });

    client.activate();
  </script>
</body>
</html>
~~~

Hai JavaScript file từ CDN cần truy cập Internet ở lần tải đầu (hoặc tự host tương ứng). Chế độ mặc định SockJS tự chọn transport; chế độ query `?transport=polling` ép `xhr-polling`, hữu ích trong kiểm thử proxy. `reconnectDelay` và STOMP heartbeat chỉ là cấu hình demo; khi triển khai thật cần thiết kế reconnection, auth/CSRF và backoff theo tải.

### 8.5. Test kiểm tra info endpoint

**src/test/java/demo/SockJsInfoTest.java**:

~~~java
package demo;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class SockJsInfoTest {

    @LocalServerPort
    int port;

    @Test
    void sockJsInfoEndpointResponds() throws Exception {
        HttpRequest request = HttpRequest.newBuilder()
            .uri(URI.create("http://localhost:" + port + "/ws/info"))
            .GET()
            .build();

        HttpResponse<String> response = HttpClient.newHttpClient().send(
            request, HttpResponse.BodyHandlers.ofString());

        assertEquals(200, response.statusCode());
        assertTrue(response.body().contains("\"websocket\""));
    }
}
~~~

Test này khởi chạy Spring Boot trên cổng ngẫu nhiên, gửi HTTP request thật và xác minh có response `/ws/info` với trường `websocket`. Nó **không tự kiểm tra tất cả fallback transports**, STOMP subscription, proxy hoặc load balancer; các bước test riêng ở phần tiếp theo giải quyết những tầng đó.

### 8.6. Chạy ứng dụng và kết quả quan sát

Tại thư mục `sockjs-proxy-demo`:

~~~bash
mvn test
mvn spring-boot:run
~~~

Lệnh `mvn test` được kỳ vọng thành công (exit code 0) khi test `SockJsInfoTest` chạy qua. Lệnh sau khởi động server; terminal giữ tiến trình Spring Boot. Nếu không cấu hình port riêng, ứng dụng nghe tại `localhost:8080`. Mở trong browser:

~~~text
http://localhost:8080/
http://localhost:8080/?transport=polling
~~~

Ở mỗi trang, sau khi kết nối thành công bấm **Gửi lời chào**. Phần log hiển thị một dòng do ứng dụng tạo:

~~~text
Xin chào, Spring
~~~

Kết quả này xảy ra sau khi client CONNECT → SUBSCRIBE `/topic/greetings` → SEND `/app/hello` và nhận MESSAGE. Trang có thể hiển thị dòng trạng thái khác nhau tùy chế độ transport. Bật DevTools → Network:
- Trang mặc định: thường thấy `GET /ws/info` và request WebSocket `.../websocket` được Upgrade.
- Trang `?transport=polling`: thấy `GET /ws/info`, request `POST .../xhr` và `POST .../xhr_send`; **không cần 101 Upgrade** để trao đổi STOMP.
- Nếu phản hồi từ CDN bị chặn bởi chính sách browser/firewall, trang chưa thể thực hiện test; kiểm tra tải JS trong Console trước khi chẩn đoán backend.

Kiểm tra backend mà không cần browser:

~~~bash
curl -i http://localhost:8080/ws/info
~~~

Kỳ vọng status **HTTP 200** và JSON chứa thông tin SockJS như `"websocket": true`. Các field khác và giá trị `entropy` có thể khác mỗi lần; **không so khớp cả body JSON theo chuỗi cố định**.

## 9. Kiểm thử qua reverse proxy và tái hiện lỗi

Không kết luận proxy chạy tốt nếu test chỉ gọi trực tiếp `localhost:8080`: đường đó đi vòng qua NGINX/CDN/LB. Hãy chạy cùng hai URL **qua hostname công khai** (HTTPS) sau khi cấu hình proxy.

### Ma trận kiểm thử bắt buộc

| Tình huống | Cách thực hiện | Tín hiệu thành công |
| --- | --- | --- |
| SockJS info | GET `https://host/ws/info` | 200, JSON được phục vụ qua proxy |
| WebSocket preferred | Browser mặc định; xem WS tab | 101, STOMP CONNECT/SUBSCRIBE/SEND và nhận MESSAGE |
| Polling forced | `?transport=polling` qua proxy | POST xhr/xhr_send thành công, nhận MESSAGE |
| Streaming | Giới hạn client transports thành xhr-streaming ở test riêng | Data frame tới browser sớm, không đợi buffer đầy |
| Chặn WebSocket có chủ đích | Test trên môi trường có proxy không hỗ trợ Upgrade | Fallback thành công nếu mạng vẫn cho HTTP vận chuyển |
| Chờ idle | Giữ connection qua nhiều heartbeat intervals | Không bị proxy cắt vô cớ |
| Hai Spring instances | Qua LB có affinity được cấu hình | Các request của session nhất quán tới đúng node |
| Origin khác | UI ở origin được phép và một origin không được phép | Allowed origin hoạt động; origin lạ bị từ chối |
| Cookies/CSRF | Môi trường có Spring Security | STOMP CONNECT và HTTP fallback tuân thủ chính sách |
| Reconnect | Tạm dừng mạng rồi bật lại | Session mới được mở và SUBSCRIBE lại, dữ liệu có chiến lược phục hồi |

**Force `xhr-streaming`:** đổi dòng cấu hình client thành `{ transports: ["xhr-streaming"] }` trong bản test riêng; không cần làm điều này ở code production. Tab Network giúp phát hiện `xhr_streaming` chỉ trả dữ liệu sau thời gian dài do proxy buffering. Một transport bị chặn có thể khiến test fail; đó là bằng chứng về giới hạn của môi trường.

### Chẩn đoán theo hiện tượng

1. **`/ws/info` trả 404:** kiểm tra context path Spring, location/rewrite và đường proxy_pass; request chưa tới SockJS endpoint.
2. **`/ws/info` trả 403:** kiểm tra Origin, CORS filter, Spring Security, CSRF cho các HTTP methods; đừng vội mở `"*"` toàn site.
3. **101 Upgrade không xảy ra, chỉ WebSocket fail:** kiểm tra `Upgrade`/`Connection` và HTTP/1.1 ở upstream, CDN/LB có cho WebSocket và TLS scheme đúng không.
4. **WebSocket chạy nhưng polling fail:** kiểm tra HTTP POST/OPTIONS, CORS, cookie, `/ws/{server}/{session}/xhr*`, WAF rules, giới hạn body và affinity.
5. **Streaming nhận một loạt message trễ:** proxy buffering/caching có thể giữ bytes; thử tắt buffering chỉ trên route cần thiết và đo thời gian frame.
6. **Kết nối ngắt đều đặn mỗi ~30s hoặc ~60s:** so sánh proxy/LB idle timeout với heartbeat được gửi thực tế, không chỉ heartbeat cấu hình.
7. **Một node chạy, hai node lỗi lúc gửi message:** xem routing session-id, cookie affinity và broker state; không đổ lỗi cho SockJS client ngay.
8. **CONNECT thất bại sau HTTP 200:** SOCKJS open frame không đồng nghĩa STOMP auth/CSRF qua broker thành công; xem STOMP ERROR và Spring message security.
9. **Trang HTTPS tới endpoint HTTP:** mixed-content; phải dùng HTTPS SockJS URL/WSS native WebSocket.
10. **Reconnect lặp vô hạn và tải tăng:** giới hạn reconnect backoff, request rate và session timeout; tránh tạo reconnect storm khi upstream chết.

### Các chỉ số nên thu thập

- Count sessions mở/đóng, transport phân bố WebSocket/xhr_streaming/xhr, tỷ lệ fallback thành công.
- Status/error trên `/ws/info`, `.../websocket`, `.../xhr`, `.../xhr_send`; proxy 499/502/504 và thời gian chờ.
- Number of currently open WebSocket and long polling/streaming connections; queue/message buffer, memory và thread usage.
- STOMP CONNECT success/error, SUBSCRIBE count, message latency, reconnect attempts.
- Theo node trong cluster: session routes, sticky affinity hits/misses, lỗi session unknown.
- Tách metric **transport** (HTTP/SockJS) khỏi metric **application message** (STOMP); HTTP 200 cho `/info` không đảm bảo broadcast thành công.

## 10. Các hiểu nhầm và lỗi phổ biến

- **“Có SockJS thì khỏi cấu hình proxy WebSocket”:** SockJS có thể cứu một số đường mạng qua HTTP, nhưng đường ưu tiên vẫn có thể là WebSocket và phải hỗ trợ Upgrade nếu muốn tối ưu.
- **“WebSocket đã lên 101 nên SockJS polling cũng chạy”:** polling phụ thuộc POST, buffering, cookie, CORS, timeout và sticky session riêng.
- **“SockJS fallback chắc chắn giải quyết corporate proxy”:** proxy có thể chặn cả long-lived HTTP request hoặc các POST đặc biệt; không có đảm bảo chung.
- **“`/topic/x` là route NGINX”:** đó là STOMP destination, không phải endpoint HTTP.
- **“`server-id` của SockJS tự pin vào backend”:** chỉ là thành phần URL; LB phải được cấu hình routing cụ thể.
- **“Broker simple chạy cluster”:** broker nội bộ không phân phối subscription qua các instance; cần kiến trúc external broker nếu có cluster.
- **“Mọi 25 giây luôn có SockJS heartbeat `h`”:** STOMP heartbeat đã đàm phán có thể thay thế heartbeat SockJS.
- **“Bật CORS `*` giải quyết auth”:** credentialed cross-origin có ràng buộc nghiêm ngặt; wildcard dễ gây lỗi browser và mở rộng tấn công.
- **“Tắt toàn bộ CSRF cho SockJS”:** chỉ ngoại lệ HTTP endpoint cụ thể khi thật sự cần, còn STOMP CONNECT cần được bảo vệ phù hợp.
- **“Mặc định mọi browser cũ sẽ dùng iframe”:** allowed origins và X-Frame-Options/CSP có thể loại bỏ iframe transports.
- **“Không cần test client thật”:** một unit test Java không phát hiện cấu hình browser mixed-content, CSP, cookie, CDN, iframe hay proxy buffering.
- **“Reconnect tự động phát lại message”:** chỉ tạo kết nối mới; phải subscribe lại và xử lý missing messages theo contract nghiệp vụ.

## 11. Checklist triển khai thực tế

Trước khi bật SockJS trên production, xác định rõ *vì sao* cần fallback và những browser/network được hỗ trợ; thử WebSocket native trong môi trường đích trước khi thêm độ phức tạp.

Kiểm tra toàn chuỗi: `/ws/info` và mọi SockJS transport path không bị rewrite/chặn; NGINX chuyển WebSocket Upgrade đúng, tắt buffering cho streaming, định nghĩa timeouts dựa trên heartbeat thực tế, và có affinity khi nhiều application nodes. Đảm bảo scheme HTTPS/WSS, Origin/CORS/CSRF/cookies/auth, frame-options và CSP theo security policy.

Kiểm thử hai đường transport qua **hostname công khai**, đo reconnect/fallback, thử lỗi node và refresh phiên. Chỉ tuyên bố triển khai thành công khi client nhận được **STOMP MESSAGE thực**, cả với WebSocket và HTTP polling; status 200 từ `/info` là cần nhưng chưa đủ.

## 12. Tài liệu tham khảo

- Spring Framework Reference — SockJS Fallback: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/fallback.html
- Spring Framework Reference — Enable STOMP: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/enable.html
- Spring Framework 6.1 Javadoc — SockJsServiceRegistration: https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/web/socket/config/annotation/SockJsServiceRegistration.html
- Spring Security Reference — WebSocket Security, SockJS & CSRF: https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html
- NGINX official docs — ngx_http_proxy_module: https://nginx.org/en/docs/http/ngx_http_proxy_module.html
- StompJS guide — Using STOMP with SockJS: https://stomp-js.github.io/guide/stompjs/rx-stomp/ng2-stompjs/using-stomp-with-sockjs
- SockJS protocol definitions — HTTP paths and frame semantics: https://github.com/sockjs/sockjs-protocol
