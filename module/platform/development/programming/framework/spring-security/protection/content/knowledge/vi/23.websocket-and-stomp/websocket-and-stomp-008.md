# CsrfChannelInterceptor và thông tin token theo phiên

## 1. Bài toán: vì sao HTTP 101 thành công nhưng STOMP CONNECT vẫn bị từ chối?

Một hệ thống quản lý đơn hàng dùng Spring Security để đăng nhập trên HTTPS và dùng Spring WebSocket Message Broker để cung cấp thông báo thời gian thực. Alice đăng nhập qua `https://api.example.com`, trình duyệt giữ session cookie. Giao diện `https://app.example.com` mở:

~~~javascript
const socket = new WebSocket("wss://api.example.com/ws");
~~~

Backend nhận request HTTP handshake, xác thực session Alice và trả `101 Switching Protocols`. Tuy nhiên, STOMP client gửi `CONNECT` không kèm CSRF token, nên Spring Security Messaging từ chối phiên STOMP. Điều này **không mâu thuẫn**: WebSocket transport và STOMP security là hai lớp khác nhau.

Trong Spring Security WebSocket Messaging, thành phần `CsrfChannelInterceptor` có nhiệm vụ kiểm tra CSRF token khi nhận **STOMP CONNECT** trên **client inbound channel**. Giá trị client trình bày phải phù hợp với thông tin token mà server đã thiết lập cho ngữ cảnh HTTP/handshake. Kẻ tấn công chỉ lợi dụng cookie do browser tự gửi không nên được phép mở messaging session có quyền của nạn nhân.

Bài này tập trung vào **`CsrfChannelInterceptor` và thông tin token theo phiên** trong chương **WebSocket và STOMP** của mô-đun **SPRING_SECURITY_HTTP_PROTECTION**. Phạm vi lớn của mô-đun là triển khai phòng vệ HTTP và trình duyệt với CSRF, CORS, security headers, CSP, HSTS, HTTP firewall và session, trên Servlet lẫn Reactive. Ở bài này, mô hình chính là **Spring MVC/Servlet + Spring WebSocket/STOMP + Spring Security Messaging**; WebFlux native sẽ được đối chiếu để tránh nhầm cơ chế.

**Ý chính cần nhớ ngay từ đầu:** server cần có một **expected CSRF token** gắn với ngữ cảnh thích hợp, client cần gửi **presented CSRF token** trong **native STOMP CONNECT header**, và messaging interceptor phải kiểm tra hai giá trị đó trước khi cấp quyền dùng phiên STOMP.

### Mục tiêu học tập

Kết thúc bài, người học có thể:

1. Phân biệt HTTP handshake, STOMP CONNECT, HTTP `CsrfFilter` và messaging `CsrfChannelInterceptor`.
2. Mô tả cách thông tin `CsrfToken` từ HTTP request được dùng tại WebSocket handshake và client inbound messaging.
3. Giải thích vai trò của `CsrfTokenRepository`, `CsrfTokenRequestHandler`, session attributes và cách token được trình bày.
4. Cấu hình `@EnableWebSocketSecurity` mà không đăng ký trùng những security interceptors framework đã cung cấp.
5. Cấp token bằng một HTTP endpoint có authentication, CORS và cache policy đúng.
6. Gửi token bằng `@stomp/stompjs.connectHeaders` trên native WebSocket hoặc SockJS.
7. Phân biệt token theo phiên với token một lần/connection, token masked/deferred và rotation khi login/logout.
8. Nhận diện lỗi token sai phiên, token mất trong handshake, mismatch repository và interceptor order.
9. Thiết kế negative tests cho CONNECT thiếu/sai token và cho quyền SEND/SUBSCRIBE sau CONNECT.
10. Hiểu giới hạn của cơ chế này trong token-only authentication và trong WebFlux native WebSocket.

Tên miền `example.com`, đường dẫn `/api/csrf` và các entity được dùng làm ví dụ, không phải thành phần được Spring tạo tự động.

## 2. Ranh giới bảo vệ: HTTP, WebSocket và STOMP

### 2.1. Ba sự kiện khác nhau

Một client STOMP chạy qua WebSocket thường trải qua:

1. **HTTP WebSocket handshake**: client gửi GET Upgrade, browser có thể mang cookie phiên; Spring Security HTTP xác thực và WebSocket endpoint kiểm tra Origin.
2. **STOMP CONNECT**: sau khi transport mở, client gửi frame CONNECT với các native headers, trong đó có thể có CSRF token.
3. **STOMP SEND/SUBSCRIBE**: sau CONNECTED, client phát các lệnh nghiệp vụ và đăng ký nhận dữ liệu; phải phân quyền từng message.

~~~mermaid
sequenceDiagram
    participant UI as Browser/STOMP client
    participant HTTP as Spring Security HTTP
    participant WS as WebSocket handshake
    participant MSG as Client inbound channel
    participant APP as Application/Broker
    UI->>HTTP: GET /api/csrf + cookie phiên
    HTTP-->>UI: CSRF token cho ngữ cảnh hiện tại
    UI->>HTTP: GET /ws + Upgrade + Origin + cookie
    HTTP->>HTTP: Xác thực HTTP principal
    HTTP->>WS: Handshake với token context và Principal
    WS-->>UI: 101 Switching Protocols
    UI->>MSG: STOMP CONNECT + native X-CSRF-TOKEN
    MSG->>MSG: CsrfChannelInterceptor kiểm tra token
    alt CONNECT bị từ chối
        MSG-->>UI: ERROR / close
    else CONNECT hợp lệ
        MSG-->>UI: CONNECTED
        UI->>MSG: SEND hoặc SUBSCRIBE
        MSG->>MSG: Message authorization
        MSG->>APP: Principal + destination + payload
        APP->>APP: Kiểm tra object/tenant ACL
        APP-->>UI: MESSAGE theo user/subscription hợp lệ
    end
~~~

Sơ đồ thể hiện luồng logic. Thứ tự nội bộ của các interceptors, thời điểm materialize token và chi tiết đặt token vào handshake/session attributes có thể khác theo phiên bản/cấu hình Spring Security. Không dựa vào sơ đồ để suy đoán tên một session attribute nội bộ khi chưa đối chiếu API đang sử dụng.

### 2.2. So sánh trách nhiệm

| Lớp | Thành phần điển hình | Điều nó kiểm tra | Điều không kiểm tra thay |
| --- | --- | --- | --- |
| HTTP authentication | `SecurityFilterChain`, HTTP authentication filters | Session/JWT/credentials trên HTTP handshake | CSRF token trên STOMP CONNECT |
| HTTP CSRF | Servlet `CsrfFilter` | HTTP requests cần CSRF theo request matcher | Từng STOMP frame sau Upgrade |
| Origin validation | `setAllowedOrigins` / `setAllowedOriginPatterns` | Browser page origin của handshake | User identity, role hoặc object ACL |
| STOMP CONNECT CSRF | `CsrfChannelInterceptor` trong messaging integration | Presented token phù hợp expected token/ngữ cảnh | Authentication và authorization nghiệp vụ |
| Message authorization | `AuthorizationManager<Message<?>>` | Principal, message type, destination, role | Token repository và object ownership nếu matcher chỉ xét destination |
| Business authorization | Controller/service/ACL | Quyền thực trên order, tenant, room | WebSocket Origin và kết nối TLS |
| Outbound routing | Broker/user destination/publisher | Gửi dữ liệu đúng session/topic | Tự đảm bảo dữ liệu hợp quyền chỉ từ rule inbound |

**HTTP 101 không chứng minh STOMP CONNECT đã vượt qua CSRF.** Tương tự, `CONNECTED` không chứng minh mọi `SEND`/`SUBSCRIBE` được phép.

## 3. Native STOMP CONNECT khác HTTP GET Upgrade thế nào?

### 3.1. Handshake HTTP thường thấy

Một trình duyệt mở WebSocket từ `https://app.example.com`:

~~~http
GET /ws HTTP/1.1
Host: api.example.com
Connection: Upgrade
Upgrade: websocket
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Origin: https://app.example.com
Cookie: SESSION=<session-if-browser-allows>
~~~

Nếu server chấp nhận:

~~~http
HTTP/1.1 101 Switching Protocols
Connection: Upgrade
Upgrade: websocket
Sec-WebSocket-Accept: <server-generated-value>
~~~

Đây là handshake HTTP/1.1 thường gặp. Hạ tầng WebSocket qua HTTP/2 có thể khác về cách bắt tay, nhưng ranh giới **HTTP transport** và **STOMP CONNECT** vẫn không bị đánh đồng.

### 3.2. CONNECT frame có native token header

Sau 101, client gửi:

~~~text
CONNECT
accept-version:1.2
host:api.example.com
X-CSRF-TOKEN:<session-csrf-token>

^@
~~~

`^@` biểu diễn byte NUL kết thúc frame STOMP. `X-CSRF-TOKEN` ở đây là **STOMP native header** nằm trong WebSocket message, không phải HTTP request header của `GET /ws`.

Nếu token đúng theo policy và các rule khác hợp lệ, client có thể nhận:

~~~text
CONNECTED
version:1.2

^@
~~~

Khi sai/thiếu token, client có thể nhận STOMP `ERROR` hoặc connection bị đóng. Đừng kỳ vọng HTTP 403 xuất hiện **sau** HTTP 101 vì STOMP CONNECT không phải request HTTP mới.

### 3.3. Browser WebSocket không cho tùy ý đặt HTTP headers

Fetch hỗ trợ:

~~~javascript
fetch("https://api.example.com/api/command", {
  method: "POST",
  headers: {
    "X-CSRF-TOKEN": csrfToken
  },
  credentials: "include"
});
~~~

Nhưng không có API browser WebSocket chuẩn với:

~~~javascript
// Sai: object headers này không được WebSocket constructor hỗ trợ.
new WebSocket("wss://api.example.com/ws", {
  headers: {
    "X-CSRF-TOKEN": csrfToken
  }
});
~~~

STOMP client cung cấp `connectHeaders` **để gửi STOMP headers**, không để browser thêm tùy ý HTTP headers. Đây là lý do token cần được gửi đúng lớp.

### 3.4. Fetch CORS không phải STOMP CSRF

Một HTTP Fetch khác origin có thể yêu cầu CORS headers và đôi khi preflight OPTIONS. Native WebSocket **không chạy Fetch CORS preflight**; server WebSocket phải kiểm soát Origin tại handshake.

`CsrfChannelInterceptor` kiểm tra token CONNECT; nó không thay CORS processor cho `GET /api/csrf`, không tự chặn toàn bộ website lạ tại handshake và không kiểm tra REST POST/PUT.

## 4. CsrfChannelInterceptor bảo vệ điều gì?

### 4.1. Interceptor ở client inbound channel

`CsrfChannelInterceptor` là thành phần messaging security được dùng để kiểm tra CSRF token trên **inbound CONNECT**. Về mặt thiết kế, khi server nhận CONNECT:

1. Lấy thông tin token mà server đã chuẩn bị/lưu trong ngữ cảnh thích hợp, liên quan đến HTTP request/handshake/session.
2. Đọc giá trị client trình bày từ native header tương ứng của STOMP CONNECT.
3. Đánh giá token phù hợp expected value và chính sách bảo vệ của framework.
4. Khi token không hợp lệ, từ chối tiến trình STOMP CONNECT thay vì cho client dùng authenticated messaging session.
5. Nếu qua được CSRF, vẫn cần principal/authorization và các bước xử lý STOMP còn lại.

**Không** mô tả bước 1 bằng cách giả định một khóa `sessionAttributes` không công khai cụ thể nếu phiên bản chưa xác minh. Đây là chi tiết framework; cách an toàn nhất là sử dụng integration `@EnableWebSocketSecurity` được hỗ trợ và kiểm thử từ HTTP token endpoint tới STOMP CONNECT.

### 4.2. Phạm vi kiểm tra là CONNECT, không phải tất cả frames

Ví dụ:

~~~text
CONNECT           -> CSRF CONNECT validation
SEND /app/orders  -> Message authorization + business logic
SUBSCRIBE /topic  -> Subscription authorization
DISCONNECT        -> Session lifecycle/authorization policy
~~~

`CsrfChannelInterceptor` **không phải** một token verifier JWT cho mọi `SEND`. Nó cũng không tự kiểm tra Alice có quyền xem đơn hàng của Bob hay không.

Nếu client gắn `X-CSRF-TOKEN` trên `SEND` nhưng bỏ trên `CONNECT`, client đã gửi token **sai thời điểm** đối với chính sách CONNECT CSRF.

### 4.3. Tại sao cần nó khi HTTP session đã authenticated?

Khi browser dùng session cookie, HTTP handshake có thể tự mang credential dù script ở một trang khác origin. Nếu server cho phép handshake, một website không tin cậy có thể cố mở kênh hai chiều thay mặt nạn nhân. Đó là **Cross-Site WebSocket Hijacking (CSWSH)**.

Yêu cầu CSRF token CONNECT buộc script phải có giá trị được ứng dụng cấp theo cách được kiểm soát, thay vì chỉ lợi dụng cookie do browser tự gửi. Origin allowlist bổ sung một rào cản ở handshake. Cả hai **không thay** authentication hoặc quyền truy cập dữ liệu.

### 4.4. Interceptor không phải bằng chứng login

Một token CSRF hợp lệ **không** chứng minh caller là ADMIN. Nó giúp chứng minh client có thể trình bày token phù hợp expected token trong ngữ cảnh của kết nối. Authentication còn phải xác thực user bằng session, bearer token hoặc cơ chế khác; message authorization phải kiểm tra quyền role/destination và business ACL.

## 5. Thông tin CSRF token “theo phiên” có nghĩa gì?

### 5.1. Ba giá trị cần tách riêng

| Thành phần | Ví dụ | Vai trò |
| --- | --- | --- |
| **Session identity** | Session cookie `SESSION` hoặc `JSESSIONID` | Cho HTTP security tìm phiên và principal |
| **Expected CSRF token** | Giá trị `CsrfToken` theo repository/ngữ cảnh | Đối chiếu với token do client trình bày |
| **Presented CSRF token** | `X-CSRF-TOKEN` trong STOMP CONNECT | Dữ liệu client nộp để qua kiểm tra CSRF |

Không lấy session ID làm CSRF token. Không lấy username/role trong frame làm expected token. Không nhầm CSRF token với access token.

### 5.2. Với HttpSessionCsrfTokenRepository

Trong mô hình Servlet session-based sử dụng `HttpSessionCsrfTokenRepository` hoặc repository có ý nghĩa tương đương, token được duy trì theo **HTTP session**. Điều này có các hệ quả:

- Nhiều WebSocket/STOMP connections từ **cùng phiên** có thể dùng token cùng nguồn theo policy hiện hành.
- Token không mặc nhiên là giá trị **dùng một lần cho mỗi CONNECT**.
- CONNECT từ một session khác không được xem là hợp lệ chỉ vì nó trình bày token của Alice trong cơ chế token gắn session đúng.
- Khi HTTP session bị invalidated, token expected cũ có thể không còn đúng trong phiên mới.
- Sau login/logout, Spring Security có thể xóa/đổi token theo CSRF/authentication strategies; token mới có thể được tạo **lazy** khi client yêu cầu.
- Kiểm tra expected token ở CONNECT phụ thuộc integration của handshake và repository, không phải client tự khai session ID.

**Lưu ý:** đây là hành vi của repository session-based. Không khẳng định mọi `CsrfTokenRepository` đều gắn token cứng với server session.

### 5.3. Với CookieCsrfTokenRepository

Một ứng dụng khác có thể dùng `CookieCsrfTokenRepository` hoặc custom repository. Với mô hình lưu token trong cookie:

- Token có thể được tạo/lưu và đọc theo chiến lược cookie, **không đồng nghĩa** token sẽ được ràng buộc với session phía server.
- Client JavaScript có thể cần cách đọc/phát token phù hợp `HttpOnly`/masked-token handler, thay vì dùng nguyên quy trình của session repository.
- Giá trị token có thể có semantics khác khi browser thay cookie hoặc khi có nhiều phiên.
- Không viết test “token của Bob chắc chắn bị từ chối ở session Alice” mà không đối chiếu **repository + binding policy** thật.
- Không dùng một custom repository yếu hoặc phản chiếu giá trị cookie không được kiểm chứng để tuyên bố đã chống mọi CSRF.

Bài lấy `HttpSessionCsrfTokenRepository` làm ví dụ chính để phân tích “theo phiên”, nhưng mọi assertion phải xét repository đang dùng.

### 5.4. Token là theo ngữ cảnh, không nhất thiết theo mỗi socket

Một sai lầm thường thấy:

> “Mỗi lần mở WebSocket, Spring luôn cấp một CSRF token mới chỉ dùng một lần.”

Không nên khẳng định như vậy. Trong mô hình session repository, token có thể được tái sử dụng qua các CONNECT còn cùng ngữ cảnh cho đến khi repository/strategy tạo hoặc rotate giá trị mới. Token có thể được materialize lazily ở HTTP request, không mặc nhiên sinh mới vì HTTP 101.

Điều quan trọng là **token client gửi khớp expected token tại thời điểm CONNECT**, với chính sách security đã triển khai.

## 6. Đường đi của token từ HTTP request sang handshake/session attributes

### 6.1. Nguồn expected token phải được server kiểm soát

Spring Security HTTP có thể đưa `CsrfToken` vào request thông qua CSRF filter/repository/handler. Khi WebSocket handshake được tích hợp đúng, thông tin cần thiết cho messaging CSRF có thể được chuyển sang ngữ cảnh handshake/WebSocket session để interceptor CONNECT kiểm tra.

Về mặt khái niệm:

~~~text
HTTP request, đã qua Spring Security:
  authentication -> Principal
  CSRF infrastructure -> CsrfToken / expected-token context
                         |
                         v
WebSocket handshake:
  kiểm tra Origin; tạo WebSocket session
  giữ principal và các attributes cần cho messaging
                         |
                         v
Client inbound STOMP CONNECT:
  native X-CSRF-TOKEN được đọc
  CsrfChannelInterceptor dùng expected-token context
  so khớp và chấp nhận/từ chối CONNECT
~~~

Không phải mọi `CsrfTokenRepository` đều lưu token giống nhau; không nên tạo một custom handshake attribute tên tùy ý rồi giả định Spring Security tự đọc nó.

### 6.2. Vai trò của CsrfTokenHandshakeInterceptor

Trong hệ sinh thái Spring Security WebSocket có thành phần handshake hỗ trợ chuyển thông tin CSRF cần thiết vào ngữ cảnh WebSocket, thường được nhắc đến dưới tên `CsrfTokenHandshakeInterceptor`. Nó không phải bộ lọc authentication và cũng không nên được xem là nơi tạo role/claims.

Điểm thiết kế quan trọng:

- **Handshake interceptor** liên quan đến thông tin HTTP request/attributes và WebSocket session context.
- **CsrfChannelInterceptor** liên quan đến inbound STOMP CONNECT và native CSRF header.
- **CsrfTokenRepository/handler** quyết định expected token và cách lấy/trình bày token.
- **Message authorization** kiểm tra Principal, destination và role sau đó.

Khi ứng dụng đã bật tích hợp Spring Security Messaging chính thức, đừng tự đăng ký thêm nhiều bản của các CSRF interceptors mà không hiểu framework auto-wiring. Tích hợp trùng có thể gây xung đột thứ tự hoặc khó debug. Chỉ tùy biến thủ công khi framework version và kiến trúc thật yêu cầu, có integration test chứng minh luồng end-to-end.

### 6.3. Không dựa vào map attributes do client gửi

Client có thể gửi:

~~~text
CONNECT
simpSessionId:alice-session
csrfExpected:anything
X-CSRF-TOKEN:anything

^@
~~~

Các giá trị do client tự khai **không được biến thành expected token** hoặc server session attributes đáng tin. Expected token phải xuất phát từ server-side security context/repository/handshake, không phải một header request mang tên giống thuộc tính nội bộ.

### 6.4. Khi custom handshake làm mất CSRF context

Các nguyên nhân có thể:

- Handshake bị xử lý bởi endpoint/adapter không tích hợp đầy đủ với Spring Security Messaging.
- Custom `HandshakeHandler` hoặc `HandshakeInterceptor` chỉ copy một phần attributes và bỏ thông tin security cần thiết.
- Nhiều SecurityFilterChains khiến handshake không đi qua HTTP CSRF infrastructure như token endpoint.
- Ứng dụng sử dụng custom repository/handler không tương thích với cách token được expose cho WebSocket.
- `SockJS` transport path đi qua HTTP filter/proxy khác với native handshake.
- HTTP session store/affinity lệch giữa các backend nodes.

Nếu CONNECT không tìm được expected token, phải điều tra **tầng phát sinh token và handshake context**, không tự cho phép CONNECT anonymous hoặc bỏ token validation.

## 7. Token deferred, masked và vòng đời token

### 7.1. Lazy/deferred token generation

Spring Security hiện đại có khả năng **trì hoãn** việc materialize token. Khi một request GET thông thường không cần sử dụng CSRF token, token có thể chưa được tạo/lưu ngay.

Nếu frontend mở WebSocket trước khi token được lấy/sinh đúng cách, một số cấu hình tùy biến có thể khiến thông tin cần cho CONNECT không có hoặc không khớp. Cách dễ kiểm soát là **truy cập endpoint cấp token bằng cùng phiên trước CONNECT**; endpoint phải thực sự gọi `csrf.getToken()` để buộc cần giá trị token.

Đừng chỉ trả metadata như tên header mà không lấy token rồi giả định session repository đã lưu expected token.

### 7.2. Masked token và XOR request handler

Trong một số cấu hình Spring Security, CSRF token có thể được **mask** khi trình bày để giảm nguy cơ lộ qua các side channels như BREACH. Giá trị được expose cho view/HTTP response có thể khác dạng raw được lưu trong repository. Đây không có nghĩa một token masked là không hợp lệ; ý nghĩa phụ thuộc request handler và cơ chế validation.

Với STOMP CONNECT, token được gửi trong native header **không phải** HTTP request parameter thông thường. Nếu dùng custom `CsrfTokenRequestHandler`, `CookieCsrfTokenRepository` hoặc biến thể masked/deferred, hãy kiểm tra:

1. Token `GET /api/csrf` expose được lấy từ đâu?
2. Expected token nào được WebSocket/Messaging layer đọc?
3. Token presented trong STOMP CONNECT cần raw hay masked representation theo integration/version?
4. Có cùng repository/secret/context cho GET token và handshake không?
5. Integration test qua WebSocket thật có CONNECTED với token được cấp không?

**Không tự bỏ masking hoặc đổi repository chỉ từ một lỗi 403**. Xác định rõ token representation/handler mismatch trước khi thay đổi bảo mật.

### 7.3. Khi login hoặc logout

Một hệ thống session-based có thể thay đổi token sau khi authentication thành công hoặc logout. Ví dụ:

~~~text
Anonymous HTTP session:
  token A
     |
     | Login + session fixation/CSRF strategies
     v
Authenticated session:
  token B hoặc expected-token state mới
     |
     | Logout / session invalidation
     v
Session/token state bị thu hồi, token cũ không còn phù hợp
~~~

Sơ đồ mang tính khái niệm, **không khẳng định mọi application sẽ luôn đổi A thành B đúng lúc login**; hành vi phụ thuộc security version, `CsrfAuthenticationStrategy`, repository và cách session được quản lý.

Thực hành an toàn: sau login, fetch lại CSRF token theo phiên hiện hành; khi logout, dừng STOMP client; khi đăng nhập user khác, không dùng lại token của user cũ.

### 7.4. Token theo phiên không thay kiểm tra token expiry ngoài CONNECT

Nếu session/token bị thu hồi sau khi CONNECTED, một WebSocket cũ có thể vẫn đang mở và giữ principal cũ. CSRF kiểm tra **CONNECT** không tự chạy lại trên từng SEND, không đóng mọi socket khi HTTP logout và không cập nhật authorities tự động.

Cần thiết kế revocation/close/revalidate cho những ứng dụng nhạy cảm.

## 8. Cấu hình Spring WebSocket STOMP endpoint trên Servlet

Ví dụ register endpoint và broker:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
class RealtimeWebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
            .setAllowedOrigins("https://app.example.com");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Ý nghĩa:

- `/ws` là endpoint HTTP handshake; frontend app ở `https://app.example.com` được phép theo Origin policy.
- `/app` dành cho client SEND commands tới `@MessageMapping`.
- `/topic` và `/queue` là broker destinations, **không mặc định có ACL riêng tư**.
- `/user` giúp route messages theo principal/session.
- Cấu hình endpoint này **không tự tạo authentication/authorization/CSRF endpoint**; các tầng còn lại phải được kết hợp rõ.

### 8.1. Origin allowlist khác CORS HTTP

Frontend `https://app.example.com` và API `https://api.example.com` khác origin. Khi browser Fetch `GET /api/csrf`, HTTP response cần CORS policy cho app frontend. Khi browser mở native `wss://api.example.com/ws`, WebSocket handshake kiểm tra `Origin`, nhưng **không dùng Fetch CORS preflight OPTIONS/ACAO** như điều kiện đọc WebSocket frames.

Hai allowlists có thể dùng cùng tập frontend tin cậy nhưng phải được cấu hình đúng **từng endpoint/cơ chế**.

### 8.2. Không dùng Origin để xác thực principal

Một HTTP client ngoài browser có thể tự khai `Origin: https://app.example.com`. Một script XSS trên frontend chính thức cũng chạy dưới origin được phép. Origin check có giá trị chống những trang browser lạ, không thay session authentication hay object authorization.

## 9. HTTP SecurityFilterChain và CSRF repository

### 9.1. Mẫu dùng HTTP session

Một ứng dụng Servlet chọn session-based login:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.web.csrf.HttpSessionCsrfTokenRepository;

@Configuration
class ServletHttpSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .csrf(csrf -> csrf
                .csrfTokenRepository(
                    new HttpSessionCsrfTokenRepository()
                ))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/login").permitAll()
                .requestMatchers("/api/csrf").authenticated()
                .requestMatchers("/ws", "/ws/**").authenticated()
                .anyRequest().denyAll())
            .formLogin(Customizer.withDefaults())
            .build();
    }
}
~~~

Đây là ví dụ **một mô hình** dùng HTTP session. `HttpSessionCsrfTokenRepository` được nêu tường minh để người học hiểu token theo session, không có nghĩa mọi ứng dụng cần override mặc định. Một project thật còn cần user store, authentication entry points, CORS cho `/api/csrf` và các HTTP endpoints nghiệp vụ khác.

**Cảnh báo:** nếu SPA chỉ có bearer token trong STOMP CONNECT nhưng HTTP `/ws` yêu cầu `authenticated()`, handshake có thể bị từ chối **trước** khi native bearer token đến. Mô hình token-only phải thiết kế HTTP handshake riêng và giải quyết CONNECT CSRF một cách rõ ràng, không trộn đoạn config session-based trên.

### 9.2. Quyền HTTP không thay quyền messaging

`authorizeHttpRequests().requestMatchers("/ws").authenticated()` chỉ bảo vệ handshake. Nó không kiểm tra mỗi `STOMP SEND` hay `SUBSCRIBE` trong connection đã nâng cấp. `CsrfFilter` cũng không trở thành CSRF filter cho mọi WebSocket message.

Với session-based STOMP, cần phối hợp:

~~~text
HTTP SecurityFilterChain -> xác thực cookie/session
WebSocket Origin policy  -> kiểm tra trusted browser origins
CsrfChannelInterceptor   -> CSRF token tại STOMP CONNECT
Message Authorization    -> SEND/SUBSCRIBE type + destination + role
Business ACL             -> object/tenant ownership và outbound routing
~~~

### 9.3. Đừng disable HTTP CSRF để “sửa” lỗi CONNECT

Phản ví dụ:

~~~java
// KHÔNG dùng như lời giải chung.
http.csrf(csrf -> csrf.disable());
~~~

Tắt HTTP CSRF có thể mở lỗ hổng ở form/REST POST dùng cookie, **không bảo đảm** STOMP CONNECT CSRF của Spring Security Messaging biến mất theo cách dự kiến. Nếu SockJS transport cần ngoại lệ hẹp, xử lý đúng đường dẫn transport; không bỏ bảo vệ nghiệp vụ.

## 10. @EnableWebSocketSecurity và CsrfChannelInterceptor

### 10.1. Kích hoạt Messaging Security chuẩn

Một cấu hình bảo vệ client inbound STOMP messages:

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
class StompMessageSecurityConfiguration {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
        MessageMatcherDelegatingAuthorizationManager.Builder messages
    ) {
        return messages
            .nullDestMatcher().authenticated()

            .simpSubscribeDestMatchers("/app/**")
                .denyAll()

            .simpSubscribeDestMatchers(
                "/user/queue/notifications",
                "/topic/public"
            ).authenticated()

            .simpDestMatchers("/app/notifications.markRead")
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

### 10.2. CSRF CONNECT là một kiểm tra riêng

Khi Spring Security WebSocket Messaging được cấu hình qua `@EnableWebSocketSecurity`, yêu cầu CSRF token tại STOMP CONNECT là một phần bảo vệ của tích hợp tương ứng. `CsrfChannelInterceptor` thực hiện việc kiểm tra CSRF riêng; `AuthorizationManager<Message<?>>` xử lý quyền.

Rule `.nullDestMatcher().authenticated()` yêu cầu principal cho các messages không có destination nhưng **không thay** bước đối chiếu token. Ngược lại, một CSRF token đúng cũng **không** cấp role USER hoặc cho phép subscribe private destinations.

### 10.3. Tránh đăng ký interceptor trùng

Nếu ứng dụng đã sử dụng tích hợp `@EnableWebSocketSecurity`, không tự chèn thêm `CsrfChannelInterceptor`/handshake CSRF components thứ hai chỉ để “chắc ăn”, khi chưa kiểm tra framework đã đăng ký gì.

Nguy cơ của wiring trùng:

- Kiểm tra token hai lần trong các ngữ cảnh khác nhau.
- Interceptor order khiến một token hợp lệ bị từ chối.
- Expected token được lấy từ repository khác với nơi cấp token.
- Logs và lỗi CONNECT khó quy nguyên nhân.
- Vô tình tạo đường bypass do custom interception xử lý sai.

Chỉ tự quản lý pipeline khi tài liệu Spring Security của phiên bản được dùng yêu cầu, với kiểm thử xác minh mỗi CONNECT chỉ đi qua policy được dự kiến.

### 10.4. Thứ tự với token-authentication ChannelInterceptor

Nếu ứng dụng có custom bearer-authentication trên STOMP CONNECT, interceptor phải xác minh token và gắn `Authentication` **trước** Spring Security messaging authorization cần principal. Song song, CSRF CONNECT cần expected-token context phù hợp.

Không đổi thứ tự theo cảm giác. Kiểm thử:

- Token bearer hợp lệ + CSRF phù hợp → CONNECTED.
- Bearer sai → bị từ chối.
- Bearer đúng + CSRF thiếu/sai → bị từ chối khi protection bật.
- Không có SEND/SUBSCRIBE được xử lý trước CONNECT thành công.

Một hệ thống chỉ dùng bearer token trong CONNECT nhưng không có HTTP session/repository tương ứng cần **thiết kế CSRF strategy có chủ đích**. JWT không tự làm `@EnableWebSocketSecurity` bỏ CONNECT CSRF.

## 11. Cấp token cho frontend qua HTTP endpoint

### 11.1. Controller trả token hiện hành

Ứng dụng có thể tạo HTTP endpoint được bảo vệ, ví dụ:

~~~java
import java.util.Map;

import org.springframework.http.CacheControl;
import org.springframework.http.ResponseEntity;
import org.springframework.security.web.csrf.CsrfToken;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestAttribute;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CsrfTokenController {

    @GetMapping("/api/csrf")
    ResponseEntity<Map<String, String>> csrf(
        @RequestAttribute("_csrf") CsrfToken csrfToken
    ) {
        return ResponseEntity.ok()
            .cacheControl(CacheControl.noStore())
            .body(Map.of(
                "headerName", csrfToken.getHeaderName(),
                "token", csrfToken.getToken()
            ));
    }
}
~~~

**Quan trọng:**

- `/api/csrf` là controller **do ứng dụng tự tạo**; không phải endpoint mặc định Spring Boot luôn có.
- Trong ví dụ session-based, HTTP `/api/csrf` phải yêu cầu authentication và được gọi bằng **đúng session** dùng cho handshake.
- `csrfToken.getToken()` giúp materialize giá trị token nếu repository/handler có lazy generation.
- Token trả về cần tương thích với cách `CsrfChannelInterceptor`/messaging integration xác minh trong version đang dùng; custom masked/deferred handler có thể cần điều chỉnh theo tài liệu/framework.
- `Cache-Control: no-store` giảm nguy cơ proxy/shared cache giữ response nhạy cảm.
- Không log token trong access logs, tracing hoặc client console.
- Nếu frontend/API khác origin, HTTP CORS của endpoint cấp token phải cho chính xác frontend đáng tin cậy đọc dữ liệu.

### 11.2. HTTP request/response minh họa

~~~http
GET /api/csrf HTTP/1.1
Host: api.example.com
Origin: https://app.example.com
Cookie: SESSION=<alice-session>
~~~

Response có thể có:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Access-Control-Allow-Origin: https://app.example.com
Access-Control-Allow-Credentials: true
Vary: Origin

{"headerName":"X-CSRF-TOKEN","token":"<token-for-current-context>"}
~~~

Đây là HTTP JSON, **không** tự thêm token vào WebSocket CONNECT. JavaScript phải lấy `headerName`/`token` rồi chuyển chúng vào `connectHeaders`.

### 11.3. CORS cho HTTP token endpoint

Một cấu hình Spring MVC chỉ dành cho token endpoint:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.CorsRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
class CsrfApiCorsConfiguration implements WebMvcConfigurer {

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/api/csrf")
            .allowedOrigins("https://app.example.com")
            .allowedMethods("GET")
            .allowCredentials(true)
            .maxAge(600);
    }
}
~~~

Với `credentials: "include"` của Fetch, HTTP CORS response phải có ACAO phù hợp origin cụ thể và ACAC cho credentialed requests. `Access-Control-Allow-Origin: *` không hợp lệ để chia sẻ response có credentials cho browser.

**Không nhầm** policy trên với `setAllowedOrigins` của native WebSocket endpoint. Một cái bảo vệ **HTTP response chia sẻ token**, cái kia bảo vệ **browser Origin tại handshake**.

### 11.4. Vì sao một CSRF endpoint không nên public vô điều kiện?

Nếu GET token được trả cho bất kỳ origin nào kèm CORS credentials rộng, một website lạ có thể dễ đọc token trong ngữ cảnh user đang đăng nhập. Điều đó làm suy giảm phòng vệ CONNECT.

Một GET token endpoint có thể cần cho khách anonymous trong một số mô hình login/form, nhưng phải thiết kế CORS, session và quyền đọc thật cẩn thận. Ví dụ bài dùng `authenticated()` để đơn giản hóa mô hình session login.

## 12. Frontend @stomp/stompjs gửi token đúng chỗ

### 12.1. Lấy token trước CONNECT

Ví dụ native STOMP over WebSocket:

~~~javascript
import { Client } from "@stomp/stompjs";

async function connectRealtime() {
  // GET token của chính session đang đăng nhập.
  const response = await fetch(
    "https://api.example.com/api/csrf",
    { credentials: "include" }
  );

  if (!response.ok) {
    throw new Error("Không lấy được CSRF token của phiên hiện tại");
  }

  const { headerName, token } = await response.json();

  const client = new Client({
    brokerURL: "wss://api.example.com/ws",

    // Native STOMP CONNECT headers, không phải HTTP headers.
    connectHeaders: {
      [headerName]: token
    },

    reconnectDelay: 3000,

    onConnect: () => {
      client.subscribe(
        "/user/queue/notifications",
        message => {
          console.log("Notification:", message.body);
        }
      );

      client.publish({
        destination: "/app/notifications.markRead",
        body: JSON.stringify({ notificationId: 1001 })
      });
    },

    onStompError: frame => {
      console.error("STOMP rejected:", frame.headers.message);
    },

    onWebSocketClose: event => {
      console.log("WebSocket closed:", event.code);
    }
  });

  client.activate();
  return client;
}
~~~

**Điều kiện của ví dụ:** session cookie hợp lệ cho API, CORS của `/api/csrf` chính xác, WebSocket Origin allowlist đã mở frontend, và message security có các rules tương ứng. Code không tự tạo HTTP login, token repository hoặc business service.

### 12.2. Trên wire, token chỉ đi vào STOMP CONNECT

~~~text
HTTP GET /ws:
  Origin: https://app.example.com
  Cookie: SESSION=...
  KHÔNG có arbitrary X-CSRF-TOKEN do browser JS thêm.

STOMP CONNECT:
  X-CSRF-TOKEN: <token-for-current-context>
  Được gửi bên trong WebSocket data frame.

STOMP SUBSCRIBE:
  destination:/user/queue/notifications

STOMP SEND:
  destination:/app/notifications.markRead
  payload business được message/service authorization.
~~~

Nếu DevTools chỉ cho thấy HTTP `GET /ws` không có header `X-CSRF-TOKEN` thì **đó chưa phải lỗi**. Cần kiểm tra WebSocket Frames/Messages để thấy CONNECT.

### 12.3. Khi dùng SockJS

Server:

~~~java
registry.addEndpoint("/ws")
    .setAllowedOrigins("https://app.example.com")
    .withSockJS();
~~~

Frontend:

~~~javascript
import SockJS from "sockjs-client";
import { Client } from "@stomp/stompjs";

function connectSockJs(csrfHeaderName, csrfValue) {
  const client = new Client({
    webSocketFactory: () =>
      new SockJS("https://api.example.com/ws"),
    connectHeaders: {
      [csrfHeaderName]: csrfValue
    }
  });

  client.activate();
  return client;
}
~~~

SockJS dùng URL `https://api.example.com/ws`, không phải `wss://api.example.com/ws` của native WebSocket constructor. Các `connectHeaders` vẫn là native STOMP headers, **không phải** HTTP headers tự gắn vào từng XHR POST fallback.

### 12.4. Không đưa token vào WebSocket URL

Tránh:

~~~javascript
const url = "wss://api.example.com/ws?csrf=" + csrfToken;
const socket = new WebSocket(url);
~~~

URL dễ bị ghi vào access logs/gateway/tracing. Ngoài ra, `CsrfChannelInterceptor` không mặc nhiên lấy query parameter đó làm native CONNECT token. Hãy dùng cơ chế được framework hỗ trợ, bảo vệ token khỏi logs và không lưu trong URL.

## 13. Reconnect, token rotation và đồng bộ phiên

### 13.1. Lỗi tái sử dụng token sau logout/login

Một luồng sai thường gặp:

~~~text
09:00 Alice login -> session A, token A
09:05 STOMP CONNECT token A -> CONNECTED
09:30 Alice logout -> session A bị invalidated
09:35 Bob login -> session B, token B
09:36 STOMP client auto-reconnect dùng token A
      -> CONNECT bị từ chối hoặc ngữ cảnh không khớp
~~~

Không nên tái sử dụng token của một session cho tất cả lần CONNECT về sau. Kể cả session fixation protection thay đổi session ID, cách repository xử lý token phải được kiểm tra đúng phiên bản. **Nguồn sự thật là expected token/context của server**, không phải một token còn nằm trong biến JavaScript cũ.

### 13.2. Làm mới token trước mỗi CONNECT

Với `@stomp/stompjs` hỗ trợ hook `beforeConnect`:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
  brokerURL: "wss://api.example.com/ws",
  reconnectDelay: 3000
});

client.beforeConnect = async () => {
  const response = await fetch(
    "https://api.example.com/api/csrf",
    { credentials: "include" }
  );

  if (!response.ok) {
    throw new Error("Không có phiên hoặc CSRF token hợp lệ");
  }

  const { headerName, token } = await response.json();
  client.connectHeaders = {
    [headerName]: token
  };
};

client.onConnect = () => {
  client.subscribe("/user/queue/notifications", frame => {
    console.log(frame.body);
  });
};

client.activate();
~~~

Cần đối chiếu hook bất đồng bộ với **phiên bản thư viện đang dùng**. Trong production, nếu lấy token thất bại vì logout/401, nên dừng hoặc điều khiển reconnect thay vì tạo vòng lặp vô hạn.

### 13.3. Reconnect không tự tạo một login mới

Khi HTTP session hết hạn, `GET /api/csrf` có thể trả 401 hoặc redirect login. Client không nên coi một HTML login page là JSON token. Kiểm tra status/content-type và chuyển người dùng qua login flow hợp lệ trước khi mở STOMP mới.

Đừng tự động cho unauthenticated CONNECT hay bỏ CSRF validation để tránh retry errors.

### 13.4. Nhiều tab, nhiều WebSocket sessions

Nếu Alice mở hai tab dùng cùng HTTP session, chúng có thể lấy expected token từ cùng repository/session. Token **không nhất thiết** được tạo mới cho từng socket. Nhưng mỗi tab có thể reconnect ở thời điểm khác nhau; khi logout một tab, connection ở tab còn lại có thể còn mở nếu server chưa thu hồi.

Cần thiết kế:

- Đóng các connections liên quan khi session bị invalidated nếu yêu cầu.
- Kiểm tra quyền hiện thời trước khi phát dữ liệu riêng.
- Xử lý token refresh/reconnect độc lập mà không thay nhầm principal giữa tabs.
- Bảo vệ cache/local storage không giữ token của user cũ sau logout.

## 14. Phân biệt session-based CSRF và bearer-token CONNECT

### 14.1. Mô hình session-based

~~~text
Browser:
  HTTP session cookie gửi vào GET /ws.
Server HTTP:
  xác thực Alice -> Principal Alice.
CSRF repository:
  expected token theo session/context.
Frontend:
  fetch token từ HTTP API cùng phiên.
STOMP CONNECT:
  gửi native X-CSRF-TOKEN.
Messaging:
  CSRF CONNECT + message authorization.
~~~

Đây là trường hợp điển hình giải thích **“thông tin token theo phiên”**.

### 14.2. Mô hình token-only

Một SPA có thể không có session cookie mà giữ bearer token, và gửi:

~~~text
CONNECT
Authorization:Bearer <access-token>

^@
~~~

Header này **không phải CSRF token** và Spring không tự xác thực chỉ nhờ có dòng chữ. Cần một custom `ChannelInterceptor` xác minh bearer thật, gắn `Authentication` bằng `StompHeaderAccessor#setUser(...)`, chạy đúng thứ tự trước message authorization.

Vấn đề thiết kế:

- HTTP handshake chưa có token, nên rule `/ws authenticated()` có thể chặn trước CONNECT.
- Không có HTTP session/CSRF repository tương ứng, nên cơ chế expected token của `CsrfChannelInterceptor` cần được xử lý theo **framework version và policy được hỗ trợ**.
- `@EnableWebSocketSecurity` không tự phát hiện JWT và tắt CSRF CONNECT.
- Nếu môi trường thật sự không có ambient browser credentials, threat model CSRF khác session-cookie model; việc thay đổi CSRF policy phải được review, không dựa vào một giả định chung.
- Nếu cho anonymous handshake để chờ CONNECT token, phải từ chối mọi SEND/SUBSCRIBE trước verified CONNECT, giới hạn resource và Origin.

### 14.3. Authentication interceptor và CSRF interceptor là hai nhiệm vụ

| Thành phần | Input | Đầu ra/kết luận |
| --- | --- | --- |
| Custom bearer `ChannelInterceptor` | STOMP native Authorization | Xác minh access token; tạo `Authentication`/`Principal` |
| `CsrfChannelInterceptor` | Presented token + expected token/context | Cho/từ chối CONNECT theo CSRF policy |
| Message `AuthorizationManager` | Message type/destination + principal/authorities | Cho/từ chối MESSAGE/SUBSCRIBE |
| Application service | Principal, payload, tenant, object ID | Cho/từ chối thao tác nghiệp vụ |

**Không dùng CSRF token làm bearer token** và không dùng bearer token để “điền đại” vào CSRF header. Hai phép kiểm tra có giá trị bảo mật khác nhau.

### 14.4. Thứ tự của custom authentication

Nếu một token-authentication interceptor chạy sau messaging authorization, policy có thể kiểm tra principal khi còn null/anonymous. Muốn dùng bearer CONNECT, interceptor phải chạy trước security components cần principal; thứ tự `WebSocketMessageBrokerConfigurer`/`@Order` tùy integration cụ thể.

Thay vì copy một giá trị order không được kiểm thử, cần integration tests chứng minh:

1. Bearer hợp lệ được xác minh rồi principal xuất hiện trong message handler.
2. Bearer sai không tạo principal.
3. CSRF đúng/sai có hành vi rõ theo policy.
4. Không có inbound SEND/SUBSCRIBE được xử lý trước verified CONNECT.
5. Quyền service theo object vẫn được áp dụng.

## 15. SockJS HTTP fallback: HTTP CSRF và CONNECT CSRF có thể cùng xuất hiện

### 15.1. Những request của SockJS

SockJS có thể sử dụng:

~~~text
GET  /ws/info
GET  /ws/<server-id>/<session-id>/websocket
POST /ws/<server-id>/<session-id>/xhr_send
GET  /ws/<server-id>/<session-id>/xhr_streaming
...
~~~

Những URL minh họa cho cấu trúc transport, không phải mọi client luôn dùng từng path. Browser có thể chọn native WebSocket hoặc fallback XHR, tùy khả năng.

### 15.2. Tại sao một SockJS POST 403 khác CONNECT 403?

Khi fallback dùng HTTP POST, Spring Security Servlet `CsrfFilter` có thể từ chối request transport vì nó không chứa token HTTP theo request matcher. Khi đó STOMP CONNECT chưa tới hoặc chưa hoàn tất.

Nếu WebSocket/SockJS transport đã mở rồi CONNECT bị từ chối, lỗi nằm ở messaging CSRF, principal hoặc message authorization. **Đừng chỉ nhìn số 403 để kết luận.**

So sánh:

| Sự kiện | Giao thức | Thành phần có thể từ chối |
| --- | --- | --- |
| `POST /ws/.../xhr_send` | HTTP | HTTP CSRF, authentication, CORS/gateway |
| `CONNECT` trong SockJS payload | STOMP | `CsrfChannelInterceptor`, message security |
| `SEND /app/...` | STOMP | Message authorization, business service |
| `SUBSCRIBE /topic/...` | STOMP | Subscription ACL |

### 15.3. Không tắt toàn bộ HTTP CSRF

Phản ví dụ:

~~~java
// Không nên dùng chung chỉ vì SockJS fallback bị lỗi.
http.csrf(csrf -> csrf.disable());
~~~

Nếu một SockJS transport thực sự cần ngoại lệ HTTP CSRF, giới hạn chính xác request matcher của transport paths, giữ CSRF cho form/REST POST/PUT nghiệp vụ và **không loại bỏ STOMP CONNECT CSRF**. Luôn kiểm thử đúng transport routes dưới reverse proxy.

### 15.4. CORS, cookies và iframe transports

SockJS XHR fallback có thể cần HTTP ACAO/ACAC và preflight OPTIONS; native WebSocket thì không dùng Fetch CORS preflight. Các iframe-based transports cũ còn có thể bị `X-Frame-Options` hoặc CSP `frame-ancestors` chặn.

Không sửa một lỗi XHR bằng cách cho mọi origin truy cập WebSocket, nới toàn bộ framing headers hoặc tắt session authentication. Hãy xác định transport thực tế và tầng từ chối.

## 16. Phân quyền SEND/SUBSCRIBE sau CONNECT

Một CSRF token đúng chỉ giúp CONNECT vượt qua CSRF policy. Nó **không** cấp quyền thực hiện mọi business action.

### 16.1. Ví dụ nhận Principal ở @MessageMapping

~~~java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Controller;

record MarkReadCommand(long notificationId) {}
record NotificationStatus(long notificationId, boolean read) {}

interface NotificationService {
    // Cần kiểm tra Principal có quyền đối với notificationId.
    NotificationStatus markReadAuthorized(
        String username, long notificationId
    );
}

@Controller
class NotificationMessageController {

    private final NotificationService notifications;
    private final SimpMessagingTemplate messaging;

    NotificationMessageController(
        NotificationService notifications,
        SimpMessagingTemplate messaging
    ) {
        this.notifications = notifications;
        this.messaging = messaging;
    }

    @MessageMapping("/notifications.markRead")
    void markRead(
        @Payload MarkReadCommand command,
        Principal principal
    ) {
        NotificationStatus result =
            notifications.markReadAuthorized(
                principal.getName(), command.notificationId()
            );

        messaging.convertAndSendToUser(
            principal.getName(),
            "/queue/notifications",
            result
        );
    }
}
~~~

Nếu Alice gửi `notificationId` của Bob, service phải từ chối dù CSRF CONNECT hợp lệ và Alice có `ROLE_USER`. Không lấy `username`/`role` từ payload để thay principal.

### 16.2. Không cho client gửi thẳng vào broker

Ví dụ nguy hiểm:

~~~text
SEND
destination:/topic/public

{"message":"SYSTEM: tài khoản của bạn đã bị khóa"}
^@
~~~

Nếu message authorization quá rộng, client có thể giả mạo thông báo của server. Nên chỉ cho SEND vào `/app/**` đã phê duyệt, nơi server chạy validation/auth, rồi server mới phát `/topic/**`.

### 16.3. Protected SUBSCRIBE cũng cần ACL

Một user đã CONNECTED có thể cố:

~~~text
SUBSCRIBE
id:orders-of-bob
destination:/topic/orders/2002

^@
~~~

Nếu policy chỉ kiểm tra `authenticated()` cho mọi `/topic/orders/**`, Alice có thể nghe dữ liệu Bob. Cần object/tenant subscription authorization hoặc chọn user destinations, đồng thời kiểm tra quyền trước khi phát dữ liệu nhạy cảm.

### 16.4. Outbound không tự được bảo vệ bởi inbound rules

Spring Security Messaging tập trung vào **client inbound channel**. Một server-side publisher phát nhầm thông tin cá nhân lên `/topic/public` là lỗi khác, không tự được ngăn chỉ vì client SEND bị chặn. Phải kiểm soát dữ liệu, đích phát và thời điểm quyền thay đổi.

## 17. Test token theo phiên: những bất biến bắt buộc

Thiết kế test nên kiểm tra **HTTP session identity**, **expected token source**, **STOMP CONNECT** và **message authorization** như những biến độc lập.

### 17.1. Ma trận handshake

| Ca | HTTP/Origin/session | Kỳ vọng |
| --- | --- | --- |
| H1 | Origin app + session Alice hợp lệ | Handshake được phép theo policy |
| H2 | Origin lạ + **cùng session Alice hợp lệ** | Origin policy chặn handshake |
| H3 | Origin app + không có session, route yêu cầu login | HTTP Security từ chối |
| H4 | Origin app + session hết hạn | Không có authenticated principal |
| H5 | Non-browser giả Origin app nhưng thiếu authentication | Không vượt HTTP auth |
| H6 | Browser bị CSP `connect-src` chặn | Không được dùng lỗi đó làm bằng chứng CsrfChannelInterceptor sai |

**Để chứng minh Origin check hoạt động**, cần gửi origin lạ với một session kiểm thử hợp lệ. Một HTTP 401 khi không có cookie chưa chứng minh Origin policy đúng.

### 17.2. Ma trận CONNECT CSRF theo session-based repository

| Ca | HTTP principal | Token trình bày ở CONNECT | Kỳ vọng |
| --- | --- | --- | --- |
| C1 | Alice | Token lấy đúng ngữ cảnh Alice | CONNECTED nếu các policy khác cho phép |
| C2 | Alice | Thiếu native header | CONNECT bị từ chối |
| C3 | Alice | Token ngẫu nhiên | CONNECT bị từ chối |
| C4 | Alice | Token của session Bob | Bị từ chối với repository/validation gắn session đúng |
| C5 | Alice | Token đã bị rotate/invalidated | Bị từ chối nếu expected token hiện hành khác |
| C6 | Alice | Token đúng nhưng gửi trong `SEND`, không ở CONNECT | CONNECT thiếu token bị từ chối |
| C7 | Alice | Token đúng nhưng sai header name | Bị từ chối nếu server không tìm thấy header yêu cầu |
| C8 | Alice | Token trả từ HTTP endpoint nhưng khác session cookie của handshake | CONNECT không hợp lệ theo expected-token context |
| C9 | Alice | Token đúng nhưng client khai `login:admin` | Không tự cấp role ADMIN |
| C10 | Anonymous với handshake policy yêu cầu authenticated | Bất kỳ token | Không thay authentication |
| C11 | Alice | Token đúng nhưng message role không đủ | Có thể CONNECTED; SEND/SUBSCRIBE bị deny |
| C12 | Alice | Token được expose dạng masked/custom | Kết quả phải khớp handler/integration version; test thực để xác nhận |

**Chú ý:** C4/C8 không thể kết luận giống nhau cho tất cả custom repositories; bảng dùng **session-bound expected token policy** làm giả định. Với `CookieCsrfTokenRepository`, phải kiểm tra cách token được ràng buộc.

### 17.3. Ma trận vòng đời

| Ca | Sự kiện | Kỳ vọng |
| --- | --- | --- |
| L1 | Login tạo/thay đổi ngữ cảnh token | Client lấy token đúng ngữ cảnh mới trước CONNECT |
| L2 | Logout và session invalidation | Token/session cũ không cấp quyền kết nối mới |
| L3 | Bob login trong browser sau Alice | Không dùng lại token/session identity của Alice |
| L4 | Auto-reconnect khi token đã rotate | Client làm mới token, không retry mãi token cũ |
| L5 | Một phiên Alice có hai WebSocket connections | Chính sách token/identity nhất quán với repository |
| L6 | Session hết hạn khi WebSocket vẫn mở | Có cơ chế thu hồi/revalidate trước dữ liệu nhạy cảm |
| L7 | Multi-node, session store khác nhau | Không gây accepted/rejected bất định hoặc lộ thông tin |
| L8 | CSRF token bị ghi vào logs | Logging được redact và có test/kiểm tra vận hành |

### 17.4. Test sau CONNECT

- `SEND /app/notifications.markRead` với notification của Alice → được phép khi role/object ACL đúng.
- `SEND /topic/public` trực tiếp → bị từ chối.
- `SUBSCRIBE /topic/admin` với user thường → bị từ chối.
- Alice gửi notificationId của Bob → service từ chối, **không có side effect**.
- Logout/role revocation → socket cũ không tiếp tục nhận dữ liệu riêng trái quyền theo policy.
- Client ngoài browser khai Origin hợp lệ nhưng auth/CSRF sai → không vượt các kiểm tra tương ứng.

## 18. Kiểm thử tích hợp Spring STOMP thật

### 18.1. Vì sao MockMvc chưa đủ?

`MockMvc` hữu ích để kiểm tra:

- `GET /api/csrf` có session/authentication và response chứa token.
- HTTP CORS chỉ cho trusted frontend.
- HTTP `SecurityFilterChain` xử lý `/ws`.
- HTTP CSRF của form/REST requests.

Nhưng một request MockMvc GET `/ws` **không thay** WebSocket Upgrade thực, STOMP CONNECT frames và `CsrfChannelInterceptor`. Cần integration test với server thật và client STOMP.

### 18.2. WebSocketStompClient skeleton

~~~java
import org.springframework.http.HttpHeaders;
import org.springframework.messaging.simp.stomp.StompHeaders;
import org.springframework.web.socket.WebSocketHttpHeaders;
import org.springframework.web.socket.client.standard.StandardWebSocketClient;
import org.springframework.web.socket.messaging.WebSocketStompClient;

// Skeleton cho test với Spring Boot server đã chạy:
WebSocketStompClient client = new WebSocketStompClient(
    new StandardWebSocketClient()
);

WebSocketHttpHeaders headers = new WebSocketHttpHeaders();
headers.setOrigin("https://app.example.com");

// HTTP cookie theo đúng session của token.
headers.add(
    HttpHeaders.COOKIE,
    "SESSION=" + aliceSessionCookie
);

StompHeaders connectHeaders = new StompHeaders();
connectHeaders.add(csrfHeaderName, aliceCsrfToken);

// client.connectAsync(uri, headers, connectHeaders, sessionHandler);
// Chờ CONNECTED/ERROR/close, assert có timeout.
~~~

Các biến `aliceSessionCookie`, `csrfHeaderName` và `aliceCsrfToken` phải do test setup tạo từ cùng authenticated session. Đây là **khung test**, không phải đoạn Java có thể chạy độc lập; cần test server, session handler, asynchronous frame assertions và message converter theo version.

### 18.3. Quy trình test end-to-end

~~~text
Given:
  - Test server chạy trên random port.
  - /ws chỉ chấp nhận Origin https://app.example.com.
  - Session Alice đã đăng nhập qua HTTP.
  - GET /api/csrf của Alice trả headerName/token.
  - @EnableWebSocketSecurity đang bật.
  - Alice có ROLE_USER và notificationId 1001.
  - Bob sở hữu notificationId 2002.

When:
  1. Handshake với Origin app + Cookie Alice.
  2. STOMP CONNECT dùng token được cấp cho Alice.
  3. Chờ CONNECTED.
  4. SUBSCRIBE /user/queue/notifications.
  5. SEND /app/notifications.markRead với notificationId 1001.

Then:
  - CONNECT thành công.
  - Controller nhận Principal Alice.
  - Notification của Alice được cập nhật.
  - Phản hồi route tới đúng user/session hợp lệ.

Negative:
  A. CONNECT bỏ native CSRF header.
  B. CONNECT gửi token sai.
  C. CONNECT gửi token của Bob trong mô hình session repository.
  D. CONNECT gửi token cũ sau khi đổi phiên.
  E. CONNECT hợp lệ nhưng SEND /topic/public trực tiếp.
  F. CONNECT hợp lệ nhưng gửi notification của Bob.
  G. Handshake Origin evil với session Alice hợp lệ.

Assertions:
  - A-D không CONNECTED, không có business side effects.
  - E-F không có data leak/side effect trái quyền.
  - G bị chặn ngay handshake.
~~~

Không chỉ khẳng định HTTP 101 hoặc frame ERROR xuất hiện; một message bất đồng bộ đã phát nhầm dữ liệu trước khi từ chối vẫn là lỗi bảo mật.

### 18.4. Tách test repository khỏi test interceptor

Một unit test `CsrfTokenRepository` có thể chứng minh token được lưu/trả đúng session. Nhưng nó không chứng minh token đã được truyền qua handshake attributes tới messaging pipeline. Cần thêm integration test để kiểm tra CONNECT thực với token được cấp qua HTTP.

Nếu thay repository/handler hoặc custom handshake interceptor, hãy chạy lại cả positive và negative tests.

## 19. Debug: token đúng nhưng CONNECT vẫn bị từ chối

| Triệu chứng | Nguyên nhân cần kiểm tra | Cách xử lý |
| --- | --- | --- |
| HTTP handshake 401/302 | Cookie/session không hợp lệ, route đòi login | Kiểm tra HTTP principal, cookie Domain/Path/SameSite |
| HTTP handshake 403 từ origin lạ | WebSocket Origin policy từ chối | Kiểm tra `setAllowedOrigins`, không mở wildcard |
| HTTP 101, STOMP không CONNECTED | CSRF CONNECT, principal hoặc protocol error | Xem STOMP CONNECT/ERROR/close và messaging logs |
| Token HTTP trả thành công nhưng CONNECT không có native header | Client chưa dùng `connectHeaders` | Kiểm tra Frames/Messages tab |
| Token xuất hiện trong GET Upgrade nhưng không trong CONNECT | Gửi sai lớp giao thức | Đặt token ở STOMP CONNECT |
| Token header name không khớp | Repository dùng tên khác | Dùng `csrf.getHeaderName()` |
| Token đúng dạng nhưng mismatch | Sai phiên, repository khác, lazy/masked handler | Kiểm tra session ID gián tiếp, repository/handler, integration test |
| Token từ request login cũ | CSRF strategy xóa/rotate sau login | Fetch token sau login với session mới |
| Reconnect lần 1 được, lần 2 bị từ chối | Token/session changed, client reuse token | Refresh bằng `beforeConnect` |
| Multi-node thỉnh thoảng CONNECT fail | Session store hoặc sticky routing thiếu | Kiểm tra cluster/session affinity |
| Custom handshake chỉ copy vài attributes | Mất CSRF context | Kiểm tra handshake security wiring |
| Duplicate CsrfChannelInterceptor | Security config tích hợp trùng | Bỏ wiring trùng, test đúng pipeline |
| Auth interceptor chạy sau authorization | Principal null hoặc quyền sai | Xem thứ tự `ChannelInterceptor` |
| Bearer token đúng nhưng CONNECT CSRF fail | Hai token có nhiệm vụ khác nhau | Thiết kế CSRF strategy thích hợp |
| Client gửi `login:admin`, vẫn anonymous | STOMP login không tự xác thực ứng dụng | Dùng HTTP principal hoặc verified CONNECT token |
| SockJS XHR POST 403 trước STOMP | HTTP CsrfFilter/CORS/transport routing | Điều tra HTTP request path/method |
| Frontend Fetch `/api/csrf` CORS error | HTTP CORS sai | ACAO cụ thể/ACAC đúng; không sửa WS Origin thay |
| Browser CSP `connect-src` chặn WSS | Request không tới backend | Cho đúng WSS destination trong CSP |
| Token đúng nhưng SEND bị deny | Message authorization/role | Xem matcher order, authorities |
| User khác nhận notifications | Subscription/business ACL hoặc outbound routing | Kiểm tra principal/object/tenant và publisher |
| Session logout nhưng socket vẫn mở | Chưa xử lý lifecycle/revocation | Đóng/revalidate WebSocket sessions |
| Debug log chứa X-CSRF-TOKEN | Token bị lộ qua logging | Redact token và hạn chế raw frames |

### 19.1. Chẩn đoán theo mốc

~~~mermaid
flowchart TD
    A["Client báo lỗi realtime"] --> B{"HTTP handshake thành công?"}
    B -- "Không" --> C["TLS/CSP/Origin/HTTP auth/Cookie/Gateway"]
    B -- "Có" --> D{"STOMP CONNECTED?"}
    D -- "Không" --> E["CsrfChannelInterceptor: token/repository/session/context"]
    E --> F["Kiểm tra principal và thứ tự messaging interceptors"]
    D -- "Có" --> G{"SEND/SUBSCRIBE hợp lệ?"}
    G -- "Không" --> H["Message role/destination/object ACL"]
    G -- "Có nhưng data sai" --> I["Outbound/user routing và revocation"]
~~~

Đừng sửa CONNECT CSRF bằng việc mở Origin `*`, tắt toàn bộ HTTP CSRF hoặc bỏ message authorization. Xác định **tầng từ chối** trước khi đổi policy.

## 20. WebFlux native WebSocket không tự có CsrfChannelInterceptor

Spring WebFlux native dùng `WebSocketHandler`/`WebSocketSession` với text/binary frames. Một handler chỉ nhận JSON messages **không tự có STOMP CONNECT hoặc `CsrfChannelInterceptor` của Spring Security Messaging Servlet**.

### 20.1. HTTP authentication trong WebFlux

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveHttpSecurityConfiguration {

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

Đây chỉ là ví dụ bảo vệ HTTP handshake. Phải có cơ chế authentication cụ thể và Origin guard phù hợp. HTTP CSRF WebFlux xử lý các HTTP requests theo policy, **không tự đối chiếu một JSON first-message token** sau khi socket mở.

### 20.2. Handler kiểm tra principal và từng message

~~~java
import java.security.Principal;

import reactor.core.publisher.Mono;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.web.reactive.socket.WebSocketHandler;

interface ReactiveNotificationService {
    Mono<Void> authorizeAndHandle(
        Principal principal, String messageText
    );
}

class SecureReactiveWebSocketHandler {

    static WebSocketHandler create(
        ReactiveNotificationService service
    ) {
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

`ReactiveNotificationService` là interface minh họa; implementation cần parse/validate message, kiểm tra principal và ACL, giới hạn payload/rate và xử lý output/backpressure. Code chưa gồm handler registration hoặc `session.send(...)`.

### 20.3. Nếu cần CSRF/first-message auth trên WebFlux native

Một ứng dụng dùng cookie phiên với native WebFlux WebSocket cần Origin validation chặt và bảo vệ theo threat model của giao thức do chính nó định nghĩa. Nếu chọn một token ở **first application message**, phải xây state machine: không xử lý business messages trước khi token được xác minh, gắn identity/context đúng, và xử lý expiry/revocation.

Đừng gọi JSON frame đó là STOMP CONNECT nếu hệ thống không dùng STOMP. Đừng sao chép `@EnableWebSocketSecurity` của Servlet rồi cho rằng WebFlux native đã được bảo vệ tương đương.

## 21. Checklist production

- [ ] Hiểu rằng HTTP handshake và STOMP CONNECT là **hai bước** có policy riêng.
- [ ] `CsrfChannelInterceptor` được tích hợp qua Spring Security Messaging đúng stack/version, không đăng ký trùng tùy tiện.
- [ ] Expected CSRF token đến từ HTTP/handshake/security context, không từ native header client tự khai.
- [ ] `CsrfTokenRepository` và `CsrfTokenRequestHandler` được kiểm tra để hiểu lưu token, masking và deferred generation.
- [ ] Khi dùng session-based repository, token CONNECT được lấy từ **đúng phiên** dùng để mở WebSocket.
- [ ] Không giả định token mới được tạo cho từng CONNECT hoặc tự rotate mỗi handshake.
- [ ] HTTP `/api/csrf` có authentication, CORS chỉ cho frontend tin cậy và `Cache-Control: no-store`.
- [ ] Frontend lấy token sau login và trước CONNECT hoặc trước lần reconnect cần token.
- [ ] Client dùng `connectHeaders` để gửi token ở native STOMP CONNECT header, không nhét token vào URL.
- [ ] Origin allowlist của WebSocket endpoint là HTTP(S) frontend origin chính xác; không dùng `*` cho session riêng.
- [ ] HTTP handshake principal được xác thực theo mô hình session hoặc token đã thiết kế.
- [ ] CONNECT thiếu/sai token bị từ chối, không xử lý business messages.
- [ ] Test token khác phiên, token cũ sau rotation và custom repository phù hợp binding policy.
- [ ] Nếu có custom bearer CONNECT interceptor, thứ tự authentication/CSRF/authorization được test; JWT không tự thay CSRF.
- [ ] Inbound SEND/SUBSCRIBE deny-by-default và không cho client SEND trực tiếp broker destinations.
- [ ] Business service kiểm tra object/tenant ACL trước khi cập nhật và phát dữ liệu.
- [ ] SockJS XHR fallback được test **HTTP CSRF/CORS** riêng với **STOMP CONNECT CSRF**.
- [ ] Session logout/expiry và role revocation có cơ chế đóng/revalidate socket/subscriptions.
- [ ] Có giới hạn connection, SEND rate, SUBSCRIBE count, frame size và idle time.
- [ ] Không log raw CSRF token, session cookie, access token hoặc payload nhạy cảm.
- [ ] Cấu hình reverse proxy/LB/session store nhất quán giữa HTTP token endpoint và WebSocket handshake.
- [ ] Đối với WebFlux native, không giả định có STOMP CsrfChannelInterceptor; security được xây đúng stack.
- [ ] Integration tests chứng minh **không CONNECTED, không data leak và không side effect** ở negative cases.

## 22. Câu hỏi vận dụng và đáp án

**Tình huống 1 — HTTP 101 là thành công?** WebSocket trả `101 Switching Protocols` nhưng client không nhận STOMP CONNECTED. Có thể do `CsrfChannelInterceptor` không?

**Đáp án:** Có. HTTP 101 mới hoàn thành transport. CONNECT còn phải qua kiểm tra CSRF và message security.

**Tình huống 2 — Token ở HTTP GET.** Frontend gửi `X-CSRF-TOKEN` trong một Fetch trước đó, nhưng không gửi gì trong STOMP CONNECT. Có đủ không?

**Đáp án:** Không. Token cho HTTP request khác không tự được chuyển thành native CONNECT header. STOMP client phải gắn qua `connectHeaders`.

**Tình huống 3 — Token cho mỗi socket.** Dev nghĩ mỗi WebSocket handshake luôn sinh một token một lần. Có chính xác không?

**Đáp án:** Không mặc định. Với repository theo HTTP session, token có thể tồn tại qua nhiều CONNECT trong cùng ngữ cảnh; rotation phụ thuộc security lifecycle và repository.

**Tình huống 4 — Token Alice ở Bob.** Server dùng `HttpSessionCsrfTokenRepository`, Bob trình bày token của session Alice trên CONNECT của Bob. Có được chấp nhận không?

**Đáp án:** Không với session-bound expected token đúng. Messaging layer phải kiểm tra token theo ngữ cảnh của Bob; cần có integration test chứng minh.

**Tình huống 5 — Cookie repository.** Ứng dụng chuyển sang `CookieCsrfTokenRepository`. Có thể tiếp tục khẳng định mọi token đều được ràng buộc với HTTP session theo cùng cách không?

**Đáp án:** Không. Repository và request handler khác có semantics khác; cần đánh giá token binding và kiểm thử cross-session/cross-context lại.

**Tình huống 6 — Token masked.** Controller trả một giá trị token nhìn khác raw token trong repository. Có nghĩa chắc chắn sai không?

**Đáp án:** Không. Một số handler mask token khi expose. Phải đối chiếu integration/version và test STOMP CONNECT thực với token được cấp.

**Tình huống 7 — Lazy token.** HTTP request đi qua Spring Security nhưng không ai đọc `CsrfToken.getToken()`. Có chắc token đã được materialize/lưu không?

**Đáp án:** Không. Với deferred token, cần kích hoạt việc lấy token thích hợp. HTTP endpoint cấp token phải trả token thực, không chỉ tên header.

**Tình huống 8 — Login rồi dùng token cũ.** Token được lấy trước login, sau login CONNECT bị từ chối. Vì sao?

**Đáp án:** Authentication/session/CSRF strategies có thể thay expected token hoặc session context. Lấy token lại sau login bằng session hiện hành.

**Tình huống 9 — Tắt HTTP CSRF.** SockJS XHR POST lỗi nên dev tắt toàn bộ `http.csrf`. Có sửa CONNECT CSRF đúng không?

**Đáp án:** Không. HTTP transport CSRF và STOMP CONNECT CSRF là hai lớp khác. Dùng ngoại lệ hẹp khi thật sự cần, giữ bảo vệ REST và CONNECT.

**Tình huống 10 — Bearer token thay CSRF.** Client gửi JWT hợp lệ trong STOMP Authorization. `CsrfChannelInterceptor` có mặc nhiên cho qua không?

**Đáp án:** Không. JWT dùng cho authentication, còn CSRF CONNECT có expected token/policy riêng. Token-only model cần thiết kế rõ và kiểm thử.

**Tình huống 11 — Origin hợp lệ.** Browser ở `https://app.example.com` nhưng CONNECT thiếu token. Có nên bỏ kiểm tra vì Origin đúng?

**Đáp án:** Không. Origin allowlist và CSRF CONNECT bổ sung nhau, đặc biệt với session cookies.

**Tình huống 12 — Client ngoài browser giả Origin.** Một Java WebSocket client tự đặt `Origin: https://app.example.com`. Có phải Spring xác thực Alice không?

**Đáp án:** Không. Origin không là danh tính. Cần HTTP/bearer authentication thật và message authorization.

**Tình huống 13 — STOMP SEND có X-CSRF-TOKEN.** Client gửi token chỉ trong SEND nhưng CONNECT thiếu. Có hợp lệ không?

**Đáp án:** Không đối với CONNECT CSRF policy. Token được yêu cầu đúng **CONNECT frame**; SEND còn chịu authorization độc lập.

**Tình huống 14 — Interceptor trùng.** Nhóm tự đăng ký thêm `CsrfChannelInterceptor` khi `@EnableWebSocketSecurity` đã tích hợp bảo vệ tương ứng. Rủi ro?

**Đáp án:** Có thể kiểm tra trùng, sai thứ tự/nguồn expected token và khó debug. Cần dùng integration chuẩn hoặc wiring thủ công có kiểm chứng.

**Tình huống 15 — CONNECTED nhưng đọc dữ liệu Bob.** Alice có CSRF token đúng rồi đọc được order của Bob. Lớp nào còn thiếu?

**Đáp án:** Message authorization theo destination/object và business ACL; CSRF không cấp quyền truy cập tất cả dữ liệu.

**Tình huống 16 — Logout nhưng socket còn chạy.** Alice logout HTTP, socket cũ vẫn nhận thông báo. Có phải CsrfChannelInterceptor sai không?

**Đáp án:** Không nhất thiết. CONNECT CSRF được kiểm tra khi kết nối. Cần lifecycle/revocation/revalidate cho connection và subscriptions đang sống.

**Tình huống 17 — Nhiều node.** HTTP token endpoint trả token từ node A, handshake/connect qua node B và mismatch. Điều tra ở đâu?

**Đáp án:** Session store/shared repository, affinity, token generation và security config giữa nodes; không mở CSRF bypass để che lỗi.

**Tình huống 18 — SockJS khác native.** Native WS + CONNECT hoạt động nhưng SockJS XHR POST bị 403 trước CONNECT. Có chắc `CsrfChannelInterceptor` từ chối không?

**Đáp án:** Chưa. HTTP POST có thể bị Servlet `CsrfFilter`, authentication, CORS hoặc gateway chặn trước khi STOMP CONNECT tới messaging.

**Tình huống 19 — WebFlux native.** Ứng dụng chỉ nhận JSON text frames trên `WebSocketHandler` và không dùng STOMP. Có sẵn CsrfChannelInterceptor cho JSON frame đầu không?

**Đáp án:** Không. WebFlux native không mặc định có STOMP CONNECT; phải thiết kế authentication/Origin/per-message security tương ứng.

**Tình huống 20 — Lộ token trong log.** Đội vận hành log toàn bộ STOMP CONNECT frame để debug. Có an toàn không?

**Đáp án:** Không. CSRF/bearer tokens có thể bị lộ; phải redact native headers và chỉ ghi loại lỗi/metadata không nhạy cảm.

---

**Ghi nhớ:** **`CsrfChannelInterceptor` bảo vệ inbound STOMP `CONNECT` bằng cách kiểm tra token client gửi trong native STOMP header so với thông tin expected token/ngữ cảnh server đã chuẩn bị.** Với repository dựa trên HTTP session, token thường gắn với phiên chứ không phải một token mới bắt buộc cho mỗi socket. Hãy làm rõ đường đi từ `CsrfTokenRepository`/request handler qua handshake/session context, cấp token đúng phiên cho frontend và gửi bằng `connectHeaders`. **Không đánh đồng HTTP CSRF, STOMP CONNECT CSRF, Origin, bearer authentication, message authorization và object ACL**; mỗi lớp có ranh giới riêng. Khi dùng SockJS, kiểm thử thêm HTTP/XHR transport; khi dùng WebFlux native, triển khai cơ chế tương đương theo protocol thực tế thay vì giả định có STOMP CONNECT.
