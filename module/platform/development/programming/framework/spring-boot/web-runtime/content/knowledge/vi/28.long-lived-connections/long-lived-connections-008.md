# Origin, bước bắt tay và xác thực kết nối WebSocket trong Spring Boot

## 1. Mục tiêu và vấn đề cần giải quyết

WebSocket tạo một **kênh giao tiếp hai chiều (full-duplex)** có thể sống lâu giữa client và server. Khác với REST API chỉ xử lý từng request/response HTTP thông thường, sau khi nâng cấp kết nối thành công, hai phía có thể gửi nhiều **WebSocket frames/messages** mà không bắt đầu một HTTP request mới cho mỗi message.

Điều đó đặt ra ba câu hỏi bảo mật độc lập:

1. **Origin:** Trang web nào đang cố mở WebSocket từ browser? Có nên cho trang đó thiết lập kết nối không?
2. **Handshake:** Request mở đầu có hợp lệ theo giao thức WebSocket, đã đi qua proxy và security filters đúng cách chưa?
3. **Authentication và authorization:** Client đang dùng danh tính nào? Danh tính này có được phép **mở kết nối** và **gửi/nhận từng loại message** hay không?

Một cấu hình an toàn cần kiểm soát **cả ba**, không chỉ cho phép HTTP `GET` tại `/ws` và hy vọng security tự bảo vệ tất cả các message về sau.

Bài này thuộc chủ đề **Kết nối dài** trong Spring Boot web runtime, trọng tâm là **WebSocket trên Spring MVC/Servlet**, Java 17+, Spring Framework 6.2 và Spring Security 6.5. Ví dụ chạy được dùng **raw WebSocket `TextWebSocketHandler`** kết hợp **form login/session cookie**, sau đó so sánh với **STOMP over WebSocket**, SockJS, WebFlux, API token và hạ tầng reverse proxy.

Sau bài học, bạn sẽ:

- Đọc được HTTP handshake `Upgrade` và phản hồi `101 Switching Protocols`.
- Hiểu vì sao `Origin` **không phải credential**, nhưng vẫn là cơ chế quan trọng chống **Cross-Site WebSocket Hijacking (CSWSH)** đối với browser.
- Cấu hình `WebSocketHandlerRegistry.setAllowedOrigins(...)` và Spring Security filter rules nhất quán.
- Biết `Principal` từ HTTP request được chuyển sang `WebSocketSession` khi kết nối được chấp nhận.
- Phân biệt **CSRF ở HTTP form** và **CSRF ở STOMP `CONNECT`**: không áp dụng máy móc cơ chế của STOMP vào raw WebSocket.
- Kiểm tra việc thiếu login hoặc sai Origin từ chối handshake, trong khi message sau `101` phải được xử lý bằng WebSocket semantics.
- Thiết kế kiểm soát message-level authorization, timeout, limits và lifecycle cho kết nối tồn tại lâu.

**Thông điệp chính:** `Origin` trả lời “request bắt nguồn từ trang nào theo thông tin browser cung cấp”; authentication trả lời “client đã được xác minh là ai”; authorization trả lời “client được làm gì”. Không thay thế một câu hỏi bằng câu hỏi khác.

## 2. WebSocket handshake: bắt đầu bằng HTTP nhưng không tiếp tục như HTTP thường

### 2.1. Ví dụ handshake HTTP/1.1

Browser dùng JavaScript:

```javascript
const socket = new WebSocket("wss://app.example.com/ws/chat");
```

Trong mô hình **WebSocket HTTP/1.1 Upgrade**, request mở đầu thường có cấu trúc:

```http
GET /ws/chat HTTP/1.1
Host: app.example.com
Origin: https://app.example.com
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Cookie: JSESSIONID=<giá trị-cookie-do-browser-gửi>
```

Đây là ví dụ cấu trúc; giá trị cookie và key trong hệ thống thật không cố định. **Không copy cookie/session ID thật vào tài liệu, log hay issue tracker.**

Nếu request hợp lệ, được phép và server chấp nhận nâng cấp:

```http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=
```

Giá trị `Sec-WebSocket-Accept` trên là kết quả ví dụ chuẩn RFC 6455 cho `Sec-WebSocket-Key` đã nêu. Server tính từ key và GUID quy định rồi SHA-1 + Base64; phép tính này **xác nhận handshake theo giao thức, không chứng minh danh tính người dùng hay tính bảo mật của kết nối**.

Các header đáng chú ý:

| Thành phần | Vai trò | Lưu ý bảo mật |
| --- | --- | --- |
| `GET` | Trong mô hình HTTP/1.1 Upgrade, WebSocket bắt đầu bằng GET | Không tự động đồng nghĩa “không có tác động trạng thái” sau khi mở |
| `Upgrade: websocket` | Yêu cầu chuyển giao thức | Chỉ có ý nghĩa với handshake đúng phiên bản/proxy |
| `Connection: Upgrade` | Đánh dấu hop-by-hop header trong HTTP/1.1 | Reverse proxy cần chuyển tiếp đúng |
| `Sec-WebSocket-Key` | Nonce ngẫu nhiên cho handshake | **Không phải API key/token xác thực** |
| `Sec-WebSocket-Accept` | Bằng chứng server hiểu handshake key | **Không** chứng minh user authenticated |
| `Sec-WebSocket-Version: 13` | Chỉ định phiên bản WebSocket phổ biến theo RFC 6455 | Phiên bản không hỗ trợ có thể bị từ chối |
| `Origin: https://...` | Nguồn trang web do browser khai báo | Phục vụ kiểm tra cross-site; non-browser có thể giả |
| `Cookie: JSESSIONID=...` | Browser có thể gửi cookie phù hợp domain/path/SameSite/Secure | Cookie phiên là credential; phải chống CSWSH |
| `Sec-WebSocket-Protocol` | Đề nghị một hoặc nhiều subprotocol như `v12.stomp` | Phải negotiate đúng, không lấy làm credential tùy ý |

**Chú ý:** Không phải mọi WebSocket trên Internet luôn dùng header `Upgrade` HTTP/1.1. HTTP/2 có cơ chế **Extended CONNECT** cho WebSocket (RFC 8441), và hỗ trợ còn phụ thuộc client, edge proxy và server. Bài thực hành dùng HTTP/1.1 Upgrade thông dụng; đừng yêu cầu `Connection: Upgrade` trên HTTP/2 vì header hop-by-hop này không được dùng như HTTP/1.1.

### 2.2. Vì sao `Origin` là `https://...`, không phải `wss://...`?

`Origin` mô tả **origin của trang tạo kết nối**, gồm **scheme, host, port**, ví dụ `https://app.example.com`. URL WebSocket có scheme `ws://` hoặc `wss://`, nhưng đó là **đích kết nối**, không phải origin của trang.

Ví dụ:

```text
Trang web:         https://app.example.com/dashboard
WebSocket đích:    wss://app.example.com/ws/chat
Origin gửi đi:     https://app.example.com

Trang độc hại:     https://attacker.example/
WebSocket đích:    wss://app.example.com/ws/chat
Origin gửi đi:     https://attacker.example
```

**Path không thuộc origin.** Hai trang `https://app.example.com/a` và `https://app.example.com/b` có cùng origin; hai trang khác scheme `http://app.example.com` và `https://app.example.com` là khác origin, ngay cả khi cùng host.

### 2.3. Từ chối handshake khác từ chối message

Trước khi hoàn tất `101`, server vẫn đang xử lý HTTP request. Có thể trả:

- **302** redirect tới `/login` nếu dùng Spring Security form login và client chưa authenticated.
- **401** + challenge nếu entry point dùng HTTP Basic/Bearer API authentication.
- **403** nếu Origin không được phép hoặc một chính sách khác từ chối.
- **400** nếu thiếu hoặc sai các WebSocket handshake headers.
- **404** nếu URL không có handler hoặc không được route đúng.
- **426 Upgrade Required** trong một số hệ thống/gateway, tùy contract.

Sau `101`, connection đã chuyển sang WebSocket. Lúc đó **không thể biến một WebSocket message lỗi thành một HTTP status 403 riêng** trên cùng connection như một request mới. Server cần dùng **application error message**, đóng WebSocket với close code phù hợp, hoặc từ chối lệnh theo protocol STOMP nếu dùng STOMP.

Mã close thường gặp:

| Close code | Ý nghĩa tổng quát | Ví dụ |
| --- | --- | --- |
| `1000` | Đóng bình thường | Browser rời trang, hoàn thành phiên |
| `1001` | Endpoint “going away” | Server shutdown hoặc trang bị đóng |
| `1008` | Policy violation | Message không được phép / danh tính không hợp lệ |
| `1009` | Message too big | Vượt giới hạn payload |
| `1011` | Internal server error | Lỗi bất ngờ khi xử lý message |
| `1006` | Abnormal closure (reserved, chỉ quan sát) | Kết nối bị mất mà không nhận close frame |

`1006` là mã dành cho **báo cáo trạng thái nội bộ**, **không gửi nó trong WebSocket Close frame**. Lý do close và status cụ thể phải được chọn theo RFC 6455 và chính sách ứng dụng, không để lộ bí mật/stack trace.

## 3. Origin: vì sao browser cần một rào chắn riêng?

### 3.1. WebSocket không tự bị ràng buộc bởi CORS theo cách `fetch` hoạt động

Browser áp dụng **same-origin policy** và cơ chế CORS cho nhiều HTTP request JavaScript, nhưng **WebSocket API không dựa trên cơ chế CORS preflight `OPTIONS` thông thường**. Một trang ở `https://attacker.example` vẫn có thể **thử mở**:

```javascript
// Đoạn minh họa threat model; không thực hiện với hệ thống không được phép.
const ws = new WebSocket("wss://app.example.com/ws/chat");
```

Nếu browser tự đính kèm cookie đăng nhập phù hợp và server **không kiểm tra Origin**, trang độc hại có thể cố gửi/nhận dữ liệu qua kết nối được xác thực bằng cookie của nạn nhân. Đây là một dạng **Cross-Site WebSocket Hijacking (CSWSH)**.

Hãy đối chiếu:

- Với `fetch("https://api.example.com")`, browser có cơ chế CORS kiểm soát JavaScript được đọc response và xử lý preflight trong một số trường hợp.
- Với `new WebSocket("wss://app.example.com/ws")`, server phải **chủ động quyết định allowed origins** cho handshake WebSocket.
- Thêm `@CrossOrigin` vào một REST controller **không đồng nghĩa** đã cấu hình `WebSocketHandlerRegistry` hay STOMP endpoint.
- WebSocket không có một preflight `OPTIONS` giống `fetch` chỉ để xin phép Origin. Không thiết kế giải pháp chống CSWSH chỉ bằng cách cho phép/từ chối HTTP `OPTIONS`.

### 3.2. Cách Spring Framework kiểm tra Origin

Spring Framework hỗ trợ WebSocket qua `WebSocketConfigurer`:

```java
registry.addHandler(myHandler, "/ws/echo")
        .setAllowedOrigins("https://app.example.com");
```

Đoạn này là snippet trong `registerWebSocketHandlers`, không phải class Java đầy đủ. Theo tài liệu Spring, mặc định WebSocket/SockJS handlers **chỉ chấp nhận same-origin** khi không mở rộng allowlist; `setAllowedOrigins(...)` dùng để định nghĩa những origin được phép.

**Không dùng**:

```java
// ANTI-PATTERN cho ứng dụng dùng cookie/session:
registry.addHandler(myHandler, "/ws/echo")
        .setAllowedOrigins("*");
```

Ký tự `*` mở cho nhiều origin; nếu cookie tự được gửi, nguy cơ CSWSH tăng mạnh. Chỉ cho phép những origin công khai được duyệt. Nếu sản phẩm có nhiều domain cụ thể, liệt kê rõ hoặc dùng `setAllowedOriginPatterns(...)` với pattern chặt chẽ, không dùng wildcard rộng kiểu mọi domain.

**Origin không phải authentication:** client như curl, Java, Python hay một script có thể **tự đặt hoặc giả mạo** header `Origin`. Kiểm tra Origin nhằm bảo vệ browser/cross-site; vẫn phải xác thực credential và phân quyền hành động. Trong một số thư viện, thiếu header Origin có thể được xử lý khác với Origin sai; nếu business yêu cầu chặn cả missing Origin, phải có chính sách cho non-browser clients và interceptor riêng, không suy từ `setAllowedOrigins` rằng mọi client thiếu Origin đều bị chặn.

### 3.3. Cookie và SameSite không thay thế Origin

Browser có thể gửi `JSESSIONID` trong handshake, phụ thuộc:

- Domain và `Path` của cookie.
- `Secure`, tức cookie được gửi qua đường bảo mật phù hợp.
- `HttpOnly`, ngăn JavaScript trực tiếp đọc cookie, **không ngăn browser gửi cookie trong request**.
- `SameSite` và cách browser phân loại same-site/cross-site.
- Các chính sách chặn third-party cookies của trình duyệt.

`SameSite=Lax` hoặc `Strict` giúp giảm một số kịch bản, nhưng **không phải lý do để bỏ Origin check**: same-site không đồng nghĩa same-origin; subdomain có thể cùng site nhưng khác origin, cookie policies của browser khác nhau, client không phải browser có thể giả header. Hãy xem **Origin check + authentication + message authorization + cookie protections** là defense in depth.

## 4. Authentication trong handshake: ai là người dùng ở WebSocketSession?

Spring Security của Servlet stack thường xác thực **HTTP handshake request** bằng cơ chế HTTP đang dùng: form login/session cookie, HTTP Basic, OAuth2 login hoặc mô hình khác.

Trong cấu hình form login:

```text
1. Browser GET /login
2. Browser POST /login (username + password + CSRF token)
3. Spring Security xác thực; lưu SecurityContext theo session policy
4. Browser giữ session cookie hợp lệ
5. JavaScript new WebSocket("wss://app.example.com/ws/echo")
6. Browser gửi HTTP GET Upgrade và cookie theo chính sách
7. SecurityFilterChain xác định Principal ở request handshake
8. WebSocket handler kiểm tra allowed Origin / nâng cấp 101
9. WebSocketSession.getPrincipal() mang danh tính của handshake
10. Handler đọc message, cần kiểm tra quyền với từng hành động
```

Tài liệu Spring Security xác nhận **Principal của HTTP request khi handshake được bàn giao cho WebSocket**. Với Spring MVC raw WebSocket và Spring Security session login, thường không cần tự đọc `JSESSIONID` rồi tra user bằng tay.

Tuy nhiên, có các giới hạn quan trọng:

- **Authentication trong handshake không phải authorization cho mọi message.** `/ws/chat` có thể cho mọi user login, nhưng `DELETE_ORDER` hay `SUBSCRIBE_ADMIN_EVENTS` vẫn phải kiểm tra quyền riêng.
- **Không mặc định đăng nhập lại ở mỗi frame**. HTTP filter chain không chạy lại như GET/POST cho mỗi WebSocket message sau nâng cấp.
- **SecurityContextHolder là thread-bound context** theo cơ chế SecurityContext; đừng giả định mọi callback background của WebSocket đều có cùng ThreadLocal context như HTTP handshake. Dùng `WebSocketSession.getPrincipal()` và service authorization được thiết kế cho connection/message.
- Một user logout, bị khóa hoặc bị thu hồi quyền **sau khi kết nối mở** có thể vẫn còn một WebSocket đang hoạt động nếu ứng dụng không chủ động close/revalidate. Phải thiết kế expiry, revoke, tenant checks và session termination theo nhu cầu.
- Session cookie trong handshake là credential; không in full cookie, `Authorization`, access token hay user session ID ra console/client logs.

### 4.1. HTTP 302, 401 hay 403 khi thiếu đăng nhập?

**Phụ thuộc AuthenticationEntryPoint**:

- Browser app dùng `formLogin`: chưa login vào `/ws/echo` có thể nhận **302 tới `/login`**.
- HTTP Basic API chain: thiếu credential có thể là **401** với `WWW-Authenticate`.
- Resource Server Bearer: thiếu/sai bearer token thường **401**, thiếu scope thường **403**, với challenge tương ứng.
- Origin bị từ chối bởi WebSocket handler: **403** nếu request đã qua security filter và đến bước kiểm tra origin.

Không dùng `new WebSocket(...)` trong browser rồi chờ nó tự xử lý một trang login redirect như link HTML bình thường. WebSocket handshake mong đợi `101`; redirect tới HTML login làm việc kết nối không thành công theo client/protocol. Với browser, người dùng nên login qua HTTP trước, sau đó mới mở WebSocket.

### 4.2. Browser WebSocket API không gửi được custom Authorization header tùy ý

JavaScript chuẩn:

```javascript
const ws = new WebSocket("wss://api.example.com/ws/chat");
```

không có tùy chọn tương đương `fetch(..., {headers: {Authorization: ...}})` để đặt **arbitrary headers** vào opening handshake. Vì vậy:

- **Session cookie + form/OAuth2 login ở HTTP** là một lựa chọn tự nhiên cho browser app trên cùng site.
- **Native/mobile client** có thể gửi Authorization header tùy thư viện, nếu backend được cấu hình để xử lý.
- **STOMP over WebSocket** có thể mang auth metadata trong STOMP `CONNECT` frame sau handshake, nhưng phải dùng `ChannelInterceptor`/message-level auth đúng cách; không tự coi header CONNECT là Principal tin cậy nếu chưa verify.
- **Đừng mặc định nhét long-lived JWT vào query string `?token=...`**: URL có thể lọt vào logs, tracing, monitoring, proxy, bookmarks, lỗi client. Nếu bắt buộc dùng token URL, cần token ngắn hạn, ràng buộc scope/audience, one-time/non-replay, HTTPS/WSS và logging redaction; đó là thiết kế riêng, không phải workaround đơn giản.
- `Sec-WebSocket-Protocol` được dùng để negotiate subprotocol, không nên lạm dụng như một kênh chuyển bearer token mà không có chính sách rõ.

Không cố dùng `Origin` làm credential thay token hoặc session: bất kỳ client ngoài browser nào cũng có thể gửi `Origin: https://trusted.example`.

## 5. HandshakeInterceptor, HandshakeHandler và Spring Security filter chain

Các điểm mở rộng quan trọng:

| Cơ chế | Chạy lúc nào? | Dùng để làm gì? | Không thay cho |
| --- | --- | --- | --- |
| `SecurityFilterChain` (Servlet) | HTTP handshake request, trước controller/handler | Authentication, URL authorization, CSRF policy của HTTP | Per-message authorization |
| `OriginHandshakeInterceptor` / `setAllowedOrigins` | Trong WebSocket handshake | Kiểm tra allowed origins | Credential verification |
| Custom `HandshakeInterceptor` | Trước/sau handshake | Chặn handshake theo policy hoặc copy **attributes an toàn** vào WebSocket session | Authentication provider/security policy hoàn chỉnh |
| `HandshakeHandler` / `DefaultHandshakeHandler` | Nâng cấp HTTP và chọn Principal/subprotocol | Tùy biến negotiation, user strategy khi thực sự cần | Kiểm tra quyền cho mọi business message |
| `TextWebSocketHandler` / `WebSocketHandler` | Sau nâng cấp `101`, xử lý message/close/error | Message validation, business permission, response | HTTP filter cho từng message |
| STOMP `ChannelInterceptor` / Spring Messaging authorization | STOMP CONNECT/SEND/SUBSCRIBE... | Token verification, destination-level authorization | Origin check ở HTTP handshake |

Ví dụ `HandshakeInterceptor` có thể lấy metadata đã được xác thực từ database, kiểm tra quota cho việc mở socket hoặc copy thuộc tính từ HTTP session sang WebSocket session. Đừng copy toàn bộ session/cookie/token không cần thiết; `WebSocketSession` có thể sống lâu hơn vòng đời một request.

**Cẩn thận `HttpSessionHandshakeInterceptor`:** nó copy một số HTTP session attributes vào map của WebSocket session khi được cấu hình. **Nó không phải một authentication filter** và không cấp quyền chỉ vì session chứa một chuỗi `"user"`. Nếu Spring Security đã xác thực request, dùng `Principal` chuẩn thay vì tự tạo một flag `loggedIn=true` do input chi phối.

Nếu dùng cookie/session qua Spring Security, lựa chọn đơn giản nhất cho raw WebSocket là: **bảo vệ URL handshake bằng `authenticated()`, giới hạn allowed origin, và kiểm tra Principal khi xử lý message**. Chỉ viết handshake interceptor bổ sung nếu có một yêu cầu cụ thể chưa được framework giải quyết.

## 6. Ví dụ ứng dụng Spring Boot Java 17+ chạy được

Demo cung cấp:

- `GET /login`: form đăng nhập Spring MVC + Thymeleaf, có CSRF token.
- `POST /login`: Spring Security xác thực session.
- `GET /app`: trang HTML yêu cầu login, kết nối WebSocket từ cùng origin.
- `GET /ws/echo`: endpoint WebSocket handshake; Spring Security yêu cầu authenticated.
- `TextWebSocketHandler`: sau `101`, echo message kèm tên Principal, giới hạn kích thước và từ chối khi thiếu Principal.

Demo dùng **Spring Boot 3.5.16** và Spring Security theo dependency BOM của Boot 3.5, **Java 17+**, embedded Tomcat mặc định. Boot 3.5.16 đã được phát hành nhưng là **bản cuối trong dòng 3.5.x với OSS support**; dự án production mới phải chọn dòng còn hỗ trợ (4.0/4.1 hoặc mới hơn được bảo trì) và điều chỉnh API/import phù hợp. Pin phiên bản ở đây chỉ để người học có một baseline rõ.

**Chỉ dùng tài khoản demo ở localhost; không công bố app với mật khẩu ví dụ, không đặt fake TLS cert để cho rằng đã có WSS production.**

### 6.1. Cấu trúc dự án

```text
websocket-origin-demo/
├─ pom.xml
└─ src/
   ├─ main/
   │  ├─ java/com/example/demo/
   │  │  ├─ WebSocketOriginApplication.java
   │  │  ├─ WebSecurityConfiguration.java
   │  │  ├─ EchoWebSocketHandler.java
   │  │  ├─ WebSocketConfiguration.java
   │  │  └─ PageController.java
   │  └─ resources/
   │     ├─ application.properties
   │     └─ templates/
   │        ├─ login.html
   │        └─ app.html
   └─ test/
      └─ java/com/example/demo/
         └─ WebSocketOriginApplicationTest.java
```

### 6.2. Maven dependencies

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>websocket-origin-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-thymeleaf</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
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
```

`spring-boot-starter-websocket` mang phần WebSocket support cho Servlet app cùng các dependency web cần thiết trong Boot 3.5. `spring-boot-starter-thymeleaf` dùng để render form/trang; `spring-security-test` dùng `MockMvc` helpers như `csrf()` và `user()`.

### 6.3. Application properties

**`src/main/resources/application.properties`**

```properties
server.port=8080

# Chỉ browser app chạy ở URL này được mở WebSocket.
# Origin phải là http(s) origin của TRANG, không viết ws://.
app.websocket.allowed-origin=http://localhost:8080

# Cookie dùng khi chạy HTTP localhost để học.
server.servlet.session.cookie.http-only=true
server.servlet.session.cookie.same-site=lax
```

Production HTTPS cần cấu hình `Secure` cookie đúng, ví dụ `server.servlet.session.cookie.secure=true`, cùng trusted proxy headers/TLS và exact public allowed origin `https://app.example.com`. Không bật `Secure` cookie cho ứng dụng học chạy HTTP thường rồi kết luận session login hỏng.

### 6.4. Main class

**`src/main/java/com/example/demo/WebSocketOriginApplication.java`**

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebSocketOriginApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebSocketOriginApplication.class, args);
    }
}
```

### 6.5. Spring Security: xác thực HTTP handshake

**`src/main/java/com/example/demo/WebSecurityConfiguration.java`**

```java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class WebSecurityConfiguration {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/login", "/error").permitAll()
            .requestMatchers("/app", "/ws/echo").authenticated()
            .anyRequest().denyAll()
        ).formLogin(form -> form
            .loginPage("/login")
            .defaultSuccessUrl("/app", true)
            .permitAll()
        );

        // Giữ CSRF mặc định của Spring Security đối với HTML POST.
        // Raw WebSocket handshake là GET; sau 101 phải kiểm tra message.
        return http.build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(PasswordEncoder encoder) {
        UserDetails demo = User.withUsername("demo")
            .password(encoder.encode("demo-pass"))
            .roles("USER")
            .build();

        return new InMemoryUserDetailsManager(demo);
    }
}
```

**Lý do cấu hình này hợp với mô hình form login:**

1. `/login` được phép truy cập trước khi có session login; `/app` và `/ws/echo` yêu cầu authentication.
2. Login qua HTML `POST /login` vẫn dùng **CSRF protection**. Việc request handshake WebSocket là HTTP GET không tự biến nó thành một request cần CSRF token theo `CsrfFilter` mặc định.
3. `defaultSuccessUrl("/app", true)` chuyển user đã login về đúng trang demo; trong ứng dụng thực có thể dùng saved request nhưng cần chống open redirect.
4. `anyRequest().denyAll()` tránh route mới bất ngờ public.
5. Mật khẩu mẫu được BCrypt encode trước khi lưu vào `InMemoryUserDetailsManager`; vẫn không được hardcode mật khẩu thật trong source.
6. Spring Security quản lý principal của HTTP request. **Không tự lấy thông tin từ `Origin` rồi dựng user**, và không tin một field `userId` do WebSocket client gửi.
7. `/ws/echo` chưa có yêu cầu role cụ thể ngoài authenticated vì demo chỉ echo văn bản. Khi có business operation, phải kiểm tra quyền **cho từng message/đối tượng** trong handler hoặc STOMP messaging infrastructure.

### 6.6. Raw WebSocket handler: không tin data của client

**`src/main/java/com/example/demo/EchoWebSocketHandler.java`**

```java
package com.example.demo;

import java.io.IOException;
import java.security.Principal;

import org.springframework.stereotype.Component;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

@Component
public class EchoWebSocketHandler extends TextWebSocketHandler {

    // Giới hạn ứng dụng demo theo ký tự UTF-16, không phải byte.
    private static final int MAX_TEXT_LENGTH = 1024;

    @Override
    protected void handleTextMessage(
            WebSocketSession session,
            TextMessage message) throws IOException {

        Principal principal = session.getPrincipal();
        if (principal == null) {
            session.close(CloseStatus.POLICY_VIOLATION);
            return;
        }

        String text = message.getPayload();

        if (text.length() > MAX_TEXT_LENGTH) {
            session.close(CloseStatus.TOO_BIG_TO_PROCESS);
            return;
        }

        session.sendMessage(
            new TextMessage(principal.getName() + ": " + text)
        );
    }
}
```

Ở đây:

- `session.getPrincipal()` đến từ HTTP handshake đã authenticated; handler **không nhận tên user từ body**.
- Giới hạn `1024` ký tự chỉ là **application-level demo**. Trong hệ thống thật còn phải giới hạn **byte/frame/buffer** ở WebSocket container và tránh buffer toàn message rất lớn trước khi kiểm tra.
- `CloseStatus.POLICY_VIOLATION` tương ứng **1008**, `TOO_BIG_TO_PROCESS` tương ứng **1009**.
- Handler chưa có business action. Với message đổi tài khoản, gửi tài liệu, subscribe room hoặc thanh toán, phải parse schema, validate payload, authenticate/authorize action và giới hạn resource ownership theo từng message.
- Không tự ghép payload vào HTML của browser như markup. Client demo dùng `textContent` thay vì `innerHTML`.

**Concurrency:** `WebSocketSession.sendMessage` không bảo đảm nhiều thread cùng gửi vào session được phép chạy song song vô điều kiện. Nếu một hệ thống có nhiều luồng đẩy message tới cùng session, cân nhắc `ConcurrentWebSocketSessionDecorator`, giới hạn send time/buffer và thiết kế thứ tự event. Ví dụ chỉ gửi một response khi xử lý một message, chưa xây một broadcast system.

### 6.7. Cấu hình WebSocket endpoint và Origin allowlist

**`src/main/java/com/example/demo/WebSocketConfiguration.java`**

```java
package com.example.demo;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class WebSocketConfiguration implements WebSocketConfigurer {

    private final EchoWebSocketHandler handler;
    private final String allowedOrigin;

    public WebSocketConfiguration(
            EchoWebSocketHandler handler,
            @Value("${app.websocket.allowed-origin}") String allowedOrigin) {
        this.handler = handler;
        this.allowedOrigin = allowedOrigin;
    }

    @Override
    public void registerWebSocketHandlers(
            WebSocketHandlerRegistry registry) {
        registry.addHandler(handler, "/ws/echo")
                .setAllowedOrigins(allowedOrigin);
    }
}
```

Khi truy cập trang tại `http://localhost:8080/app`, browser sẽ gửi `Origin: http://localhost:8080` cho WebSocket `ws://localhost:8080/ws/echo`, khớp allowlist. Trang ở `https://attacker.example` cố mở socket đích này sẽ mang Origin khác và bị từ chối nếu request đến được origin checker.

**Không đặt giá trị `ws://localhost:8080` vào `app.websocket.allowed-origin`.** Spring so sánh HTTP(S) origin của trang, không phải WebSocket URL scheme.

Cấu hình hai lớp bảo vệ là có chủ đích:

1. **Spring Security URL rule** chặn handshake nếu chưa login.
2. **Spring WebSocket Origin restriction** chặn các browser origins không cho phép.

Để bài demo đơn giản, không dùng SockJS và không cấu hình `@EnableWebSocketMessageBroker` hay STOMP messaging; raw WebSocket khác với một broker có destinations, SUBSCRIBE và CONNECT frames.

### 6.8. Controller render trang login và app

**`src/main/java/com/example/demo/PageController.java`**

```java
package com.example.demo;

import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class PageController {

    @GetMapping("/login")
    public String login() {
        return "login";
    }

    @GetMapping("/app")
    public String app() {
        return "app";
    }
}
```

`@Controller` trả tên template `login` / `app`. Nếu đổi thành `@RestController`, Spring sẽ trả string body thay vì render HTML; đây là lỗi thường gặp khi học Spring MVC.

### 6.9. Trang login có CSRF token

**`src/main/resources/templates/login.html`**

```html
<!doctype html>
<html lang="vi" xmlns:th="http://www.thymeleaf.org">
<head>
  <meta charset="UTF-8">
  <title>Đăng nhập WebSocket Demo</title>
</head>
<body>
  <h1>Đăng nhập</h1>

  <p th:if="${param.error}">
    Tên đăng nhập hoặc mật khẩu không hợp lệ.
  </p>

  <form method="post" th:action="@{/login}">
    <label for="username">Tài khoản</label>
    <input id="username" name="username" required>

    <label for="password">Mật khẩu</label>
    <input id="password" name="password" type="password" required>

    <button type="submit">Đăng nhập</button>
  </form>
</body>
</html>
```

Với Spring Security/Thymeleaf integration chuẩn, form POST có `th:action` sẽ được tích hợp CSRF token dưới dạng hidden input. Token **không được hardcode** và thay đổi tùy session/cơ chế bảo vệ. Thiếu token, `POST /login` thường nhận 403 do CSRF; điều đó khác với từ chối Origin ở handshake.

### 6.10. Trang app mở WebSocket sau đăng nhập

**`src/main/resources/templates/app.html`**

```html
<!doctype html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <title>WebSocket Echo</title>
</head>
<body>
  <h1>WebSocket echo sau đăng nhập</h1>
  <p id="connection-status">Đang kết nối...</p>

  <label for="message">Thông điệp</label>
  <input id="message" maxlength="1024" value="Xin chào">
  <button id="send" disabled>Gửi</button>

  <h2>Nhật ký nhận từ server</h2>
  <div id="messages" aria-live="polite"></div>

  <script>
    const status = document.getElementById("connection-status");
    const input = document.getElementById("message");
    const send = document.getElementById("send");
    const log = document.getElementById("messages");

    // Đường dẫn cố định cho demo root-context ở localhost.
    // Khi chạy sau path prefix proxy, dùng URL builder có context awareness.
    const scheme = location.protocol === "https:" ? "wss://" : "ws://";
    const url = scheme + location.host + "/ws/echo";

    const socket = new WebSocket(url);

    socket.addEventListener("open", () => {
      status.textContent = "Đã kết nối";
      send.disabled = false;
    });

    socket.addEventListener("message", event => {
      const row = document.createElement("p");
      row.textContent = event.data; // Text; không dùng innerHTML.
      log.appendChild(row);
    });

    socket.addEventListener("close", event => {
      status.textContent = "Đã đóng: code " + event.code;
      send.disabled = true;
    });

    socket.addEventListener("error", () => {
      // Browser không cho JavaScript đọc mọi chi tiết HTTP handshake.
      status.textContent = "Không kết nối được";
      send.disabled = true;
    });

    send.addEventListener("click", () => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send(input.value);
      }
    });

    window.addEventListener("beforeunload", () => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.close(1000, "Leaving page");
      }
    });
  </script>
</body>
</html>
```

**Bảo mật phía client:**

- `new WebSocket(url)` không có chỗ truyền tùy ý `Authorization` header. Cookie session được browser tự gửi khi phù hợp.
- URL chọn `wss://` nếu trang dùng HTTPS; **không** chạy `ws://` từ một trang HTTPS production (mixed-content/security).
- `row.textContent = event.data` hiển thị message như text, không diễn giải HTML/JS từ payload; `innerHTML` sẽ có rủi ro XSS nếu data không đáng tin cậy.
- Browser UI `maxlength=1024` chỉ hỗ trợ trải nghiệm; server **vẫn kiểm tra lại** `MAX_TEXT_LENGTH`.
- `onerror` thường **không cho biết HTTP 302/403/400 chi tiết** vì API WebSocket và chính sách bảo mật browser. Xem Network → WS/Headers và server logs được kiểm soát để tìm nguyên nhân.
- JS inline trong demo chỉ để người học dễ đọc; production có CSP nghiêm nên đặt mã JS trong file tĩnh riêng, không mở `unsafe-inline` vô tội vạ.

## 7. Chạy và kiểm tra từng bước

### 7.1. Khởi chạy

Trong thư mục dự án có JDK 17+ và Maven:

```bash
java -version
mvn spring-boot:run
```

Nếu tạo bằng Spring Initializr có Maven Wrapper:

```bash
./mvnw spring-boot:run
```

Trên Windows dùng `mvnw.cmd spring-boot:run`. Mặc định demo chạy tại `http://localhost:8080`; hãy đảm bảo port này còn trống.

### 7.2. Browser chưa login

Mở:

```text
http://localhost:8080/app
```

Kỳ vọng bị **redirect tới `/login`**. Đây là Spring Security form login rule đối với trang `/app`, chưa phải WebSocket handshake.

Nếu một script cố kết nối trực tiếp `ws://localhost:8080/ws/echo` khi chưa có session login, HTTP handshake bị security filter yêu cầu authentication. Với `formLogin`, server có thể trả `302 /login`; WebSocket client sẽ coi việc không nhận `101` là handshake thất bại. **Đừng yêu cầu browser WebSocket tự hiển thị form login qua redirect**.

### 7.3. Đăng nhập và mở WebSocket

Ở trang login, nhập:

```text
username: demo
password: demo-pass
```

Browser gửi form POST cùng CSRF token; Spring Security tạo/xác thực session theo cơ chế mặc định. Khi thành công, trang `/app` được tải, JavaScript gọi:

```text
ws://localhost:8080/ws/echo
```

Trong DevTools → Network → WS (hoặc một mục tương đương), kỳ vọng thấy request handshake **101 Switching Protocols**. Khi bấm **Gửi** với `Xin chào`, handler trả:

```text
demo: Xin chào
```

Đó là **payload mong đợi trong Message event**, không phải response body của một GET HTTP thông thường. Kiểm tra tab Frames/Messages để thấy message đi và về. Nếu bấm gửi liên tiếp, session có thể tồn tại cho nhiều message trên cùng một WebSocket connection.

**Không dùng `curl -i http://localhost:8080/ws/echo` làm bằng chứng “WebSocket hoạt động”**: GET HTTP thường thiếu header Upgrade/Key/Version và không duy trì protocol frames, nên có thể bị redirect hoặc trả 400. Để kiểm tra handshake thành công cần browser, WebSocket-aware client hoặc automated WebSocket integration test thực sự.

### 7.4. Origin sai

Để quan sát chính sách, cần **đăng nhập trước** và tạo một handshake có cookie hợp lệ nhưng `Origin` khác. Khi đi qua security filter, bước Origin validation sẽ từ chối handshake, thường bằng **403**.

Đừng dùng một request vừa **không authenticated** vừa **sai Origin** rồi kết luận chính sách Origin đã được kiểm tra: Spring Security có thể redirect login **trước khi** Origin interceptor chạy. Phải phân biệt rõ lớp từ chối.

Ví dụ sau dùng các công cụ HTTP chỉ minh họa cách xem headers (không thể thay một WebSocket client đầy đủ):

```http
GET /ws/echo HTTP/1.1
Host: localhost:8080
Origin: https://attacker.example
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==
Cookie: JSESSIONID=<cookie-đăng-nhập-hợp-lệ>
```

Kết quả mong đợi của Origin policy khi authentication hợp lệ: **không có 101**, thường **403**. Không đặt session cookie thật vào command line công khai hoặc lưu trữ chung chỉ để thử; có thể dùng test MockMvc có authenticated principal như phần tiếp theo.

### 7.5. Thiếu hoặc sai handshake headers

Ngay cả khi đã authenticated và Origin đúng, request không có:

- `Upgrade: websocket`,
- `Connection: Upgrade` (đối với HTTP/1.1),
- `Sec-WebSocket-Version` hỗ trợ,
- `Sec-WebSocket-Key` hợp lệ,

sẽ không được chấp nhận thành một kết nối WebSocket HTTP/1.1. Tùy tầng xử lý và lỗi cụ thể, server thường trả 400 hoặc một lỗi handshake khác, **không phải** tất cả đều trả 403.

### 7.6. Kết nối và session tồn tại lâu

Một WebSocket có thể sống nhiều phút/giờ trong khi HTTP session cookie hết hạn hoặc user logout ở tab khác. **Không giả định Spring Security reauthenticate mọi message**. Với hệ thống nhạy cảm cần:

- Thiết kế thời hạn tối đa của WebSocket session.
- Đóng session khi logout/revoke hoặc yêu cầu kiểm tra lại quyền trước hành động nhạy cảm.
- Đối chiếu `Principal` với trạng thái account hiện tại, nếu business policy yêu cầu hiệu lực tức thì.
- Dùng Spring Session WebSocket integration khi cần phối hợp HTTP session timeout với WebSocket; không nghĩ cứ có WebSocket thì HTTP session bất tử.
- Kiểm tra phiên còn quyền subscribe room/topic hay không; xóa subscription/close nếu mất quyền.

## 8. Kiểm thử Spring MVC, Origin và message handler

Các test sau dùng `spring-boot-starter-test` và `spring-security-test`. Chúng kiểm tra **Spring Security HTTP rules**, **OriginHandshakeInterceptor policy** và **handler behavior** mà không cần socket tới Internet.

**`src/test/java/com/example/demo/WebSocketOriginApplicationTest.java`**

```java
package com.example.demo;

import java.util.HashMap;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.ServletServerHttpRequest;
import org.springframework.http.server.ServletServerHttpResponse;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.web.socket.CloseStatus;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.server.support.OriginHandshakeInterceptor;

import static org.hamcrest.Matchers.containsString;
import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.ArgumentMatchers.argThat;
import static org.mockito.Mockito.*;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestPostProcessors.user;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class WebSocketOriginApplicationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    EchoWebSocketHandler handler;

    @Test
    void anonymousBrowserIsRedirectedToLogin() throws Exception {
        mvc.perform(get("/app"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/login")
            ));
    }

    @Test
    void anonymousHandshakeIsNotAllowed() throws Exception {
        mvc.perform(get("/ws/echo"))
            .andExpect(status().is3xxRedirection())
            .andExpect(header().string(
                "Location", containsString("/login")
            ));
    }

    @Test
    void authenticatedUserCanLoadPage() throws Exception {
        mvc.perform(get("/app")
                .with(user("demo").roles("USER")))
            .andExpect(status().isOk())
            .andExpect(content().string(
                containsString("new WebSocket(url)")
            ));
    }

    @Test
    void missingCsrfTokenRejectsLoginPost() throws Exception {
        mvc.perform(post("/login")
                .param("username", "demo")
                .param("password", "demo-pass"))
            .andExpect(status().isForbidden());
    }

    @Test
    void validFormLoginWithCsrfRedirectsToApp()
            throws Exception {
        mvc.perform(post("/login")
                .with(csrf())
                .param("username", "demo")
                .param("password", "demo-pass"))
            .andExpect(status().is3xxRedirection())
            .andExpect(redirectedUrl("/app"));
    }

    @Test
    void originPolicyRejectsCrossSiteHandshake() throws Exception {
        var request = new MockHttpServletRequest("GET", "/ws/echo");
        request.setScheme("http");
        request.setServerName("localhost");
        request.setServerPort(8080);
        request.addHeader("Origin", "https://attacker.example");

        var response = new MockHttpServletResponse();
        var interceptor = new OriginHandshakeInterceptor(
            List.of("http://localhost:8080")
        );

        boolean allowed = interceptor.beforeHandshake(
            new ServletServerHttpRequest(request),
            new ServletServerHttpResponse(response),
            handler,
            new HashMap<>()
        );

        assertFalse(allowed);
        assertEquals(
            HttpStatus.FORBIDDEN.value(),
            response.getStatus()
        );
    }

    @Test
    void originPolicyAllowsConfiguredOrigin() throws Exception {
        var request = new MockHttpServletRequest("GET", "/ws/echo");
        request.setScheme("http");
        request.setServerName("localhost");
        request.setServerPort(8080);
        request.addHeader("Origin", "http://localhost:8080");

        var response = new MockHttpServletResponse();
        var interceptor = new OriginHandshakeInterceptor(
            List.of("http://localhost:8080")
        );

        boolean allowed = interceptor.beforeHandshake(
            new ServletServerHttpRequest(request),
            new ServletServerHttpResponse(response),
            handler,
            new HashMap<>()
        );

        assertTrue(allowed);
    }

    @Test
    void handlerEchoesAuthenticatedPrincipalNotClientUser()
            throws Exception {
        WebSocketSession session = mock(WebSocketSession.class);
        when(session.getPrincipal()).thenReturn(() -> "demo");

        handler.handleMessage(session, new TextMessage("Xin chao"));

        verify(session).sendMessage(argThat(msg ->
            msg instanceof TextMessage text &&
            "demo: Xin chao".equals(text.getPayload())
        ));
    }

    @Test
    void handlerClosesWhenMessageIsTooLong()
            throws Exception {
        WebSocketSession session = mock(WebSocketSession.class);
        when(session.getPrincipal()).thenReturn(() -> "demo");

        handler.handleMessage(session, new TextMessage(
            "X".repeat(1025)
        ));

        verify(session).close(CloseStatus.TOO_BIG_TO_PROCESS);
        verify(session, never()).sendMessage(
            any(org.springframework.web.socket.WebSocketMessage.class)
        );
    }

    @Test
    void handlerClosesWhenPrincipalIsMissing()
            throws Exception {
        WebSocketSession session = mock(WebSocketSession.class);

        handler.handleMessage(session, new TextMessage("hello"));

        verify(session).close(CloseStatus.POLICY_VIOLATION);
    }
}
```

Chạy:

```bash
mvn test
```

**Kỳ vọng:** với Spring Boot 3.5.16, Spring Security/Thymeleaf/WebSocket và đúng các file trên, mười test được thiết kế để **pass**. Đây là **kết quả kỳ vọng**, không phải tuyên bố đã chạy trong một repository thực tế.

Điều các test chứng minh:

- Anonymous không vượt qua rule `authenticated()` của trang và WebSocket handshake URL.
- Form login thiếu CSRF bị từ chối; form có token đi qua security authentication workflow.
- Chính sách allowed Origin từ chối một origin lạ và chấp nhận origin đã cấu hình.
- `TextWebSocketHandler` dùng `Principal` của session, không dùng username tự khai báo trong message; đóng 1008/1009 ở hai trường hợp tương ứng.

**Giới hạn của test:** các phép thử `OriginHandshakeInterceptor` là **unit tests trực tiếp cho policy**, không phải bằng chứng mọi Nginx/gateway đang forward Origin đúng hoặc rằng HTTP Upgrade thật trả 101. `MockMvc` không thiết lập kết nối WebSocket thật và không chứng minh browser có cookie đúng, server resource limits hoặc frames/ping/pong. Để hoàn tất QA production, phải chạy browser/WebSocket integration test qua embedded server thực và **qua reverse proxy public HTTPS**; kiểm tra frame, close, auth/Origin và các lỗi socket trong Network tab hoặc client test thư viện phù hợp.

## 9. Trường hợp dùng STOMP over WebSocket: authentication, CONNECT và message authorization

Raw WebSocket ví dụ chỉ có message dạng text. **STOMP** là một **messaging subprotocol** chạy trên WebSocket, có frames như:

```text
CONNECT
accept-version:1.2
heart-beat:10000,10000

^@
```

`^@` minh họa byte null kết thúc STOMP frame, không phải hai ký tự bắt buộc trong file giao thức. Sau kết nối, client có thể gửi `SEND`, `SUBSCRIBE`, `UNSUBSCRIBE`, `DISCONNECT`.

Đây là **hai tầng**:

1. HTTP WebSocket handshake mở transport và xác định user theo HTTP.
2. STOMP `CONNECT` mở logical messaging session và có thể có auth/CSRF metadata riêng.

Với Spring Security **messaging WebSocket security** dùng `@EnableWebSocketSecurity`, Spring có cơ chế yêu cầu CSRF token trong inbound STOMP `CONNECT` để bổ trợ kiểm tra same-origin và chống cross-site WebSocket message submission. Không nhầm lẫn:

- **Raw WebSocket `TextWebSocketHandler` ở phần 6**: không có STOMP `CONNECT`, nên không tự áp dụng quy tắc CSRF của STOMP `CONNECT`.
- **Spring STOMP messaging stack**: có `@MessageMapping`, broker prefixes, client STOMP CONNECT/SUBSCRIBE, message security và CSRF ở messaging layer nếu bạn đã bật cấu hình tương ứng.
- **HTTP CSRF filter**: vẫn bảo vệ HTTP state-changing requests như login/logout POST. WebSocket handshake GET không tự bị HTTP CsrfFilter yêu cầu token.

### 9.1. Cấu hình STOMP message authorization theo principle

Một cấu hình riêng cho app STOMP có thể dùng Spring Security `@EnableWebSocketSecurity` và bean `AuthorizationManager<Message<?>>`, thay vì chỉ thêm HTTP `authenticated()`.

**Snippet minh họa — không đặt vào raw WebSocket demo phần 6:**

```java
// Giả sử đã cấu hình STOMP WebSocket endpoint,
// message broker và Spring Security messaging.
@Bean
AuthorizationManager<Message<?>> messageAuthorizationManager(
        MessageMatcherDelegatingAuthorizationManager.Builder messages) {
    return messages
        .simpDestMatchers("/app/public").authenticated()
        .simpDestMatchers("/app/admin/**").hasRole("ADMIN")
        .simpSubscribeDestMatchers("/user/**").authenticated()
        .anyMessage().denyAll()
        .build();
}
```

Đây là snippet, cần import các class `AuthorizationManager`, `Message` và `MessageMatcherDelegatingAuthorizationManager`, cùng configuration bean builder tương ứng với phiên bản Spring Security. **Không copy nguyên đoạn rồi kỳ vọng toàn bộ hệ thống STOMP chạy:** còn cần `@EnableWebSocketMessageBroker`, `registerStompEndpoints`, `configureMessageBroker` và policy đầy đủ cho `CONNECT`/`DISCONNECT`/`HEARTBEAT`; matcher catch-all `denyAll` có thể chặn các message control nếu chưa khai báo rule hợp lệ. Tên destinations phải khớp app prefix và user-destination semantics của hệ thống thật.

**Điểm then chốt:** `SUBSCRIBE` và `SEND` đều có thể là hành động nhạy cảm. Chỉ giới hạn `/app/admin/**` ở HTTP handshake không ngăn một người đã connect dùng STOMP `SUBSCRIBE /topic/admin` nếu message security bị bỏ qua. Phải định nghĩa và test policy trên cả destinations nhận và gửi, tenant ownership và outbound subscriptions.

### 9.2. CSRF token trong STOMP CONNECT

Nếu dùng STOMP, browser không thể tùy ý thêm HTTP headers vào WebSocket handshake, nhưng STOMP JavaScript client có thể đặt **STOMP CONNECT headers** bên trong frame sau khi WebSocket mở. Ví dụ logic khái niệm:

```javascript
// Pseudocode cho STOMP client đã được khởi tạo hợp lệ.
// csrfHeaderName và csrfToken lấy từ endpoint/meta tag
// cùng origin, sau khi đã đăng nhập.
stompClient.connect(
  { [csrfHeaderName]: csrfToken },
  () => console.log("STOMP connected")
);
```

API chính xác phụ thuộc phiên bản STOMP client; trong `@stomp/stompjs` mới có thể dùng `connectHeaders` và `Client.activate()` thay vì method `connect` legacy. Không được lấy token từ trang khác qua CORS wildcard; đảm bảo CSRF token được phát cho đúng browser/session và không log ra ngoài.

Với SockJS fallback, một số transports dùng POST HTTP; Spring Security hướng dẫn **miễn HTTP CSRF theo một matcher hẹp cho các SockJS transport URLs** nếu cần, vì token được kiểm ở STOMP CONNECT layer. Điều này **không có nghĩa disable CSRF toàn ứng dụng**. Hãy theo đúng tài liệu cho stack, transport và phiên bản cụ thể, đồng thời bảo đảm origin restrictions và STOMP CONNECT CSRF vẫn hoạt động.

### 9.3. Token-based STOMP authentication

Nếu mobile/SPA cần bearer auth theo STOMP `CONNECT`:

- Dùng `ChannelInterceptor` đọc CONNECT headers và verify token bằng authentication provider/JWT decoder chuẩn.
- Sau khi xác thực, gán `Principal`/Authentication hợp lệ vào accessor/session theo API Spring messaging và đảm bảo interceptor **chạy trước** security authorization interceptor.
- Không tự tin token do client gửi là người dùng xác thực nếu chưa kiểm chữ ký, hạn, audience/issuer/scope.
- Cân nhắc expiry/revocation trong kết nối dài; auth ngay lúc CONNECT không tự làm token còn hiệu lực vĩnh viễn.
- Không chỉ đặt auth token vào một STOMP header rồi giả định `Spring Security HTTP Bearer filter` sẽ tự đọc nó — đó là **hai tầng khác nhau**.

Cần phân biệt mô hình **cookie-authenticated browser STOMP** (dùng principal của HTTP handshake) và **token-authenticated STOMP CONNECT** (custom token handling). Kết hợp cả hai mà không thiết kế precedence có thể tạo confused-deputy/identity mismatch.

## 10. Reverse proxy, TLS và public Origin trong production

Browser thường truy cập:

```text
Trang:       https://app.example.com/app
WebSocket:  wss://app.example.com/ws/echo
Origin:     https://app.example.com
```

Nhưng Spring Boot có thể nghe **HTTP nội bộ** trên `127.0.0.1:8080`, sau Nginx/gateway kết thúc TLS. Phải cấu hình:

- Chuyển `Upgrade` và `Connection` đúng trong mô hình HTTP/1.1 WebSocket.
- Đảm bảo proxy không xóa `Origin` được browser gửi; nếu proxy cần rewrite, phải dùng quy tắc **đáng tin và có kiểm toán**.
- Cho Spring biết public scheme/host nếu ứng dụng tạo links/redirects/cookie dựa trên request.
- Allowed origin **phải là public HTTP(S) origin** `https://app.example.com`, không phải `http://127.0.0.1:8080` hoặc `wss://app.example.com`.
- Cookie session domain/path/Secure/SameSite phải phù hợp HTTPS URL công khai.
- Backend port phải nằm trong private/trusted network; không để client Internet bypass reverse proxy và giả `X-Forwarded-*`.

Ví dụ Nginx **minh họa** đường WebSocket HTTP/1.1 Upgrade:

```nginx
location /ws/ {
    proxy_pass http://127.0.0.1:8080/ws/;
    proxy_http_version 1.1;

    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";

    proxy_set_header Host app.example.com;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-Host app.example.com;
    proxy_set_header X-Forwarded-Port 443;

    # WebSocket sống lâu: timeout phải phù hợp ping/heartbeat.
    proxy_read_timeout 120s;
}
```

Đây là snippet chỉ phần `location`, cần server TLS/certificate, allowlist host, network isolation và các cấu hình proxy khác. `127.0.0.1` chỉ đúng nếu Nginx và Spring Boot dùng chung network namespace; khi là hai container khác nhau phải dùng private service DNS.

`proxy_read_timeout 120s` không giữ connection vô hạn: nếu không có traffic/heartbeat đủ thường xuyên, proxy có thể đóng. Cần đồng bộ server/session idle timeout, TCP/WebSocket ping/pong hoặc STOMP heartbeat và thời gian các intermediary.

**Cẩn thận header poisoning:** `Origin` và `X-Forwarded-Host` có mục đích khác nhau. `X-Forwarded-Host` phải được **proxy kiểm soát**, không tin client gửi tùy ý để xây absolute URL, redirect hoặc security decisions. Origin policy phải so sánh với public origins đã đăng ký. Không giải quyết lỗi 403 bằng cách đổi sang `setAllowedOrigins("*")` nếu thực sự là sai proxy header hoặc cookie.

### 10.1. WebSocket và HTTP/2 phía proxy

Một CDN/edge có thể phục vụ trang HTTP/2 nhưng chuyển WebSocket sang HTTP/1.1 Upgrade ở một hop khác. Đừng suy từ việc website dùng HTTP/2 rằng WebSocket cũng nhất thiết dùng Extended CONNECT. Kiểm tra từng chặng và server support:

- Browser ↔ CDN/gateway.
- Gateway ↔ Nginx/ingress.
- Nginx/ingress ↔ embedded server.

Nếu client yêu cầu WebSocket trên HTTP/2 Extended CONNECT, proxy phải hỗ trợ RFC 8441 ở chặng đó; không chép nguyên `Connection: Upgrade` vào HTTP/2. Test handshake thật qua public URL, không chỉ localhost.

## 11. Xác thực qua token: những lựa chọn và trade-off

| Client/cơ chế | Cách đưa credential vào kết nối | Điều cần đặc biệt chú ý |
| --- | --- | --- |
| Browser dùng form/OAuth2 login | Cookie phiên tự gửi trong HTTP handshake | Origin allowlist, CSWSH, SameSite/Secure, HTTP session lifecycle |
| Native/mobile client | `Authorization: Bearer ...` trong handshake nếu client hỗ trợ | HTTPS/WSS, validation JWT, expiry và audience |
| Browser + STOMP token | Token trong STOMP `CONNECT` frame, custom ChannelInterceptor | CONNECT xảy ra **sau** HTTP handshake; message auth phải xác minh token trước khi cho phép hoạt động |
| Browser + short-lived one-time ticket | Ticket được backend cấp qua HTTPS, dùng đúng phạm vi | Tránh URL logs, TTL cực ngắn, audience, one-time/replay protection |
| Basic authentication | Credential trong HTTP handshake từ client có hỗ trợ | Browser WebSocket JS không kiểm soát arbitrary Authorization, dùng HTTPS và rate limiting |
| Mutual TLS hoặc proxy authentication | Identity từ transport/proxy được tin cậy | Không tin một header `X-User` tự đặt từ Internet |

**Không phát JWT dài hạn trong URL** để “đơn giản hóa”. Không chuyển thông tin xác thực bằng query string do người dùng tự gửi rồi cache/log raw URL. Nếu dùng signed ticket phải định nghĩa đơn vị xác thực nào cấp, token tồn tại bao lâu, single-use hay không, origin/rate limits và lỗi hết hạn trong kết nối dài.

### Khi người dùng đổi quyền hoặc logout trong khi socket còn mở

HTTP session/authentication tại thời điểm handshake thường được dùng để xác định Principal của WebSocket. Nhưng trạng thái account có thể đổi:

```text
09:00: user demo connect với ROLE_USER
09:05: admin vô hiệu hóa user
09:06: socket cũ vẫn còn sống nếu ứng dụng không chủ động xử lý
```

Cần quyết định contract:

- **Revalidation mỗi message** đối với thao tác nhạy cảm (quyền/tenant từ nguồn tin cậy).
- **Connection registry** để đóng mọi socket của một principal khi bị revoke/logout.
- **Max session lifetime / token expiry** và yêu cầu reconnect.
- **STOMP SUBSCRIBE authorization** cho từng destination/room.
- **Backpressure và message quotas** để tránh một user giữ quá nhiều socket.
- **Spring Session WebSocket** nếu dùng HTTP sessions và cần tích hợp event/timeout của session store.

Không chỉ kiểm tra `session.getPrincipal() != null` ở mọi message rồi coi đó là xác thực còn hiệu lực vô thời hạn.

## 12. WebSocket Session, HTTP Session và concurrency

| Đối tượng | Phạm vi | Có tự đồng nghĩa với user login không? |
| --- | --- | --- |
| HTTP `HttpSession` | Nhiều HTTP requests dùng cùng session ID/cookie | Không; có thể là anonymous session |
| Spring Security `Authentication` | Danh tính đã được xác thực theo filter/security context | Có ý nghĩa authentication nhưng vẫn phải kiểm tra authorization |
| `WebSocketSession` | Một WebSocket connection, có ID/attributes/Principal | Không tự tạo auth; Principal lấy từ handshake hoặc cơ chế custom |
| STOMP session | Logical session ở tầng messaging trên transport | Cần policy CONNECT, SEND, SUBSCRIBE riêng |

Một HTTP session có thể chứa **nhiều WebSocket sessions** (nhiều tab), nhưng từng socket có vòng đời kết nối riêng. Logout trong một tab không tự bảo đảm các WebSocket sessions khác đã đóng tức thì nếu không có integration.

### 12.1. Quản lý write concurrency

Với Spring `WebSocketSession`, nhiều threads cùng gọi `sendMessage(...)` lên một session không phải lúc nào an toàn. Khi một publisher/subscription broadcast có thể gửi đồng thời, dùng cơ chế serialize writes hoặc Spring `ConcurrentWebSocketSessionDecorator` với giới hạn thời gian gửi và buffer size:

```java
// Snippet minh họa khi ứng dụng quản lý nhiều writers:
// new ConcurrentWebSocketSessionDecorator(
//     originalSession, sendTimeLimitMillis, bufferSizeLimitBytes
// );
```

Chọn limits theo kích thước message và số clients; tránh giữ hàng nghìn messages chưa được gửi, vì một client chậm có thể khiến server tăng memory vô hạn.

### 12.2. Heartbeat và timeout

WebSocket có Ping/Pong frames ở protocol layer; STOMP có `heart-beat` semantics riêng. Browser WebSocket API không mở tùy ý Ping/Pong frames từ JavaScript như một custom app message, nên server/proxy có thể cần heartbeat riêng.

- Gửi heartbeat theo nhịp được thiết kế để giữ connection qua idle timeout.
- Không nhầm “TCP connection còn open” với user còn active hoặc quyền vẫn còn hợp lệ.
- Có reconnect exponential backoff + jitter ở client, không reconnect bão khi server restart.
- Cần timeout opening handshake, max sessions/user, max text/binary payload, throttling, rate limiting và idle close policy.
- Log event `connected/disconnected/error` cùng request/connection ID không nhạy cảm; không log session cookie hoặc raw token.

### 12.3. Từ chối message sau handshake

Một request WebSocket đã nhận 101 thì HTTP filter chain không chạy lại cho từng frame. Ví dụ message:

```json
{"type":"DELETE_INVOICE","invoiceId":"123"}
```

Handler phải **parse dữ liệu có schema**, kiểm tra user, quyền xóa invoice 123 theo tenant/owner và chống replay khi cần. Nếu không đủ quyền:

- Không thực thi hành động.
- Có thể trả application error message theo protocol.
- Có thể đóng WebSocket với code `1008` nếu đó là policy của app.
- Không tuyên bố “HTTP 403” như một response body cho WebSocket message sau `101`.

Nếu dùng STOMP, phân quyền destination và business object phải được thực thi tại messaging/service layer; chỉ có `hasRole("USER")` cho HTTP handshake không tự bảo vệ các thao tác bên trong.

## 13. Các lỗi phổ biến cần nhận diện

**Lỗi 1 — Dùng CORS REST để bảo vệ WebSocket.** `@CrossOrigin` trên HTTP controller không tự cấu hình allowed origins của `WebSocketHandlerRegistry`. Dùng `setAllowedOrigins` hoặc cấu hình STOMP endpoint phù hợp.

**Lỗi 2 — `setAllowedOrigins("*")` cho socket dùng cookie login.** Mở rộng bề mặt CSWSH. Chỉ dùng public allowed origins do operator quản lý; không nhận danh sách origins từ request.

**Lỗi 3 — Xem `Origin` là bằng chứng danh tính.** Non-browser client có thể gửi header tùy ý; auth phải dựa vào credential được verify.

**Lỗi 4 — Cho anonymous handshake rồi tin username do client gửi.** Dữ liệu `{"user":"admin"}` trong message không xác thực được admin. Dùng principal từ HTTP handshake/validated CONNECT token, kiểm tra quyền mỗi action.

**Lỗi 5 — Chỉ kiểm tra HTTP `authenticated()` và bỏ qua message-level authorization.** Connection đã mở có thể gửi những message mà business code không giới hạn. Định nghĩa schema/destination/room/action ownership.

**Lỗi 6 — Dùng Browser WebSocket API và cố đặt `Authorization` như fetch.** `new WebSocket(url, protocols)` không nhận arbitrary headers. Chọn cookie session hoặc cơ chế token được thiết kế cho stack và threat model.

**Lỗi 7 — Đặt JWT dài hạn vào query string.** Token có thể lộ qua proxy logs/tracing; dùng phương án khác, hoặc một ticket ngắn hạn/single-use với quy tắc nghiêm ngặt nếu buộc phải có.

**Lỗi 8 — Áp cơ chế STOMP `CONNECT` CSRF vào raw `TextWebSocketHandler`.** Hai stack khác nhau; raw WS không tự có STOMP CONNECT. Cần Origin check và auth theo HTTP/handler, hoặc tự thiết kế app message protocol.

**Lỗi 9 — Tắt toàn bộ CSRF vì login POST trả 403.** CSRF cho HTTP form và CSRF STOMP CONNECT có mục đích/lớp khác nhau. Hãy cung cấp token đúng, không disable bừa.

**Lỗi 10 — Dùng `ws://` khi trang HTTPS.** Dùng `wss://` và proxy/TLS chuẩn; không hạ browser security để sửa handshake.

**Lỗi 11 — Sai public Origin sau reverse proxy.** Backend localhost 8080 không phải origin của browser public. Allowlist phải là `https://app.example.com`, không phải `wss://app.example.com`.

**Lỗi 12 — Dùng `curl GET` thiếu Upgrade rồi kết luận handshake lỗi auth.** Thiếu handshake headers có thể gây HTTP 400; phải test bằng WebSocket client thật và kiểm tra filter/order.

**Lỗi 13 — Sau 101 vẫn trả mã HTTP 401/403 cho từng message.** Lúc này là WebSocket frames; dùng close code hoặc app-level error, kiểm tra principal/permissions.

**Lỗi 14 — Không cập nhật quyền user trong socket đã mở.** Logout/revoke không luôn close socket ngay; phải thiết kế registry, TTL hoặc revalidation.

**Lỗi 15 — Echo HTML vào `innerHTML`.** Dữ liệu gửi qua socket vẫn không tin cậy; render bằng `textContent` hoặc sanitize theo ngữ cảnh.

**Lỗi 16 — Không giới hạn message hoặc đồng thời write.** Client chậm/payload lớn có thể tăng memory hoặc làm lỗi session. Limit sizes, buffer, throughput, concurrent session sends và backpressure.

**Lỗi 17 — Phân biệt sai `Origin` và `Sec-WebSocket-Protocol`.** Origin là nguồn trang; subprotocol là tên giao thức phụ như STOMP. Cả hai không tự xác minh user.

**Lỗi 18 — Quên HTTP session có thể sinh nhiều WebSocket connections.** Nhiều tab và reconnect tạo nhiều sessions; cần quota, cleanup và policy cho một user.

## 14. Quy trình chẩn đoán theo status và sự kiện

| Hiện tượng | Kiểm tra trước | Hướng xử lý |
| --- | --- | --- |
| `302 /login` ở handshake | User đã có cookie/session xác thực chưa? | Login qua HTTP trước, kiểm tra cookie/path/session |
| `401` + challenge | Entry point là Basic/Bearer? Credential thiếu/sai? | Dùng auth scheme đúng, không cố parse HTML |
| `403` trước 101 | Origin mismatch hay rule/CSRF/gateway? | Phân biệt lớp từ chối bằng logs/test authenticated handshake |
| `400` handshake | `Upgrade`, `Connection`, version, key, subprotocol đúng? | Dùng WebSocket-aware client |
| `404` chỉ ở production | Proxy rewrite path, context path hoặc endpoint mapping sai? | Kiểm tra route `/ws/echo` qua ingress |
| Browser báo `WebSocket connection failed` | DevTools → Network WS, server logs/edge logs | Không mong JS onerror cung cấp full response |
| Có `101` nhưng message không về | Handler/authorization/payload size/serialization? | Kiểm tra Frames, close code, logs |
| Disconnect code `1009` | Payload vượt limit | Điều chỉnh contract/giới hạn, không bật vô hạn |
| Disconnect code `1008` | Bị policy violation, không đủ quyền | Kiểm tra auth/tenant/message policy |
| Socket rớt sau một thời gian idle | Proxy/network/server idle timeout | Heartbeat/Ping/Pong, proxy_read_timeout |
| Chỉ khác biệt giữa HTTP và HTTPS | Cookie Secure/SameSite, WS vs WSS, trusted proxy | Sửa public TLS URL và origin allowlist |
| Message gửi được sau logout | Kết nối cũ chưa bị revoke/close | Thiết kế connection revocation và per-message checks |
| Test Origin fail ở MockMvc | Đã xác thực trước khi đến interceptor? | Test Origin policy tách khỏi authentication |
| STOMP CONNECT trả lỗi security | CONNECT CSRF và message authorization đã bật đúng? | Kiểm tra STOMP headers, Spring Messaging configuration |
| User được phép connect nhưng subscribe room riêng người khác | Thiếu message-level/object authorization | Kiểm tra SUBSCRIBE destination và tenant/owner |

## 15. Checklist kiểm thử trước production

- [ ] Có exact public HTTP(S) origins allowlist; không dùng wildcard `*` khi socket dùng cookie.
- [ ] WebSocket endpoint thuộc SecurityFilterChain phù hợp, không vô tình `permitAll` cho business socket nhạy cảm.
- [ ] Anonymous handshake bị từ chối theo entry point đã thiết kế (302/401), không nhận 101.
- [ ] Authenticated user từ origin cho phép được upgrade 101 qua **public WSS URL**.
- [ ] Authenticated user với Origin không cho phép **không** được 101.
- [ ] Non-browser client có thể giả Origin; các business messages vẫn bắt buộc auth/authorization.
- [ ] Request thiếu hoặc sai WebSocket version/key/upgrade bị từ chối đúng giao thức.
- [ ] Browser session cookie có Secure/HttpOnly/SameSite/Path/Domain phù hợp, không lộ trong logs.
- [ ] Login/logout HTTP form có CSRF token; nếu dùng STOMP có kiểm thử `CONNECT` CSRF khi bật Spring Security messaging.
- [ ] `Principal` ở session được xác minh, không lấy từ username string của message.
- [ ] Message schema, tenant/room/resource authorization và subscription policy được kiểm tra từng hành động.
- [ ] Logout, account disable, token expiry, quyền bị revoke trong khi socket mở có chính sách rõ.
- [ ] WebSocket texts/data được render theo ngữ cảnh an toàn (DOM textContent), không tự tạo HTML từ user data.
- [ ] Message/frame/buffer sizes, connections per user, rate/timeout/backpressure và concurrent sends có giới hạn.
- [ ] Proxy hỗ trợ Upgrade, public URL, Origin, WSS, idle timeout/heartbeat và session stickiness/store phù hợp.
- [ ] Có metrics active sockets, accepted/rejected handshakes, reason code, abnormal close, reconnect spikes và error rate.
- [ ] Đã test HTTP handshake từ chối, message authorization sau 101, SockJS/STOMP nếu dùng, và test lại qua ingress thực.
- [ ] Spring Boot/Spring Framework/Spring Security sử dụng phiên bản được vá và còn được bảo trì; không mở cổng backend trực tiếp ra Internet.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** `Origin: https://app.example.com` và WebSocket URL `wss://app.example.com/ws` có mâu thuẫn không?  
**Trả lời:** Không. Origin là HTTP(S) origin của trang; URL đích WebSocket dùng ws/wss.

**Câu 2.** Vì sao `Origin` không phải authentication?  
**Trả lời:** Non-browser client có thể tự đặt giá trị Origin, còn credential phải được server kiểm tra từ session/token/cơ chế xác thực.

**Câu 3.** Vì sao một trang độc hại có thể cố mở WebSocket tới website đã login?  
**Trả lời:** WebSocket không dựa vào CORS preflight như fetch, browser có thể gửi cookie tùy policy. Server phải chặn Origin ngoài allowlist và kiểm tra authentication.

**Câu 4.** Tại sao WebSocket handshake nhận 302 /login thay vì 401?  
**Trả lời:** Ứng dụng dùng Spring Security form login với redirect entry point. Client WebSocket không được nâng cấp nếu không nhận 101.

**Câu 5.** `Sec-WebSocket-Key` có phải bearer token?  
**Trả lời:** Không; đó là nonce handshake của RFC 6455, không xác minh người dùng.

**Câu 6.** `@CrossOrigin` trên REST controller đã đảm bảo WebSocket same-origin chưa?  
**Trả lời:** Chưa. Cấu hình `WebSocketHandlerRegistry.setAllowedOrigins` hoặc STOMP endpoint riêng.

**Câu 7.** Sau 101, mỗi WebSocket message có đi qua HTTP `SecurityFilterChain` không?  
**Trả lời:** Không như request mới. Phải có authorization ở handler/message layer.

**Câu 8.** CSRF của STOMP CONNECT có tự động áp dụng cho raw `TextWebSocketHandler`?  
**Trả lời:** Không. Chúng là hai mô hình messaging khác nhau.

**Câu 9.** Browser JS `new WebSocket(url)` có tùy chọn `headers: {Authorization: ...}` không?  
**Trả lời:** Không có API gửi arbitrary headers như fetch. Chọn cookie session hoặc protocol/auth architecture phù hợp.

**Câu 10.** Nếu người dùng đã logout, socket đang mở có tự đóng ngay không?  
**Trả lời:** Không được bảo đảm; cần phối hợp session lifecycle và connection revocation/revalidation.

**Câu 11.** Một message không được phép sau 101 có thể dùng HTTP 403 như bình thường không?  
**Trả lời:** Không; dùng application error hoặc WebSocket Close frame như 1008.

**Câu 12.** Tại sao test GET với MockMvc không đủ chứng minh WebSocket chạy?  
**Trả lời:** MockMvc không chứng minh HTTP Upgrade thật, frames, cookie và proxy; phải thử WebSocket client/browser qua server thật.

**Câu 13.** Có cần test authentication và Origin riêng không?  
**Trả lời:** Có. Nếu chưa authenticated, filter có thể từ chối trước Origin check; để xác nhận Origin check cần một request đã có danh tính hợp lệ.

**Câu 14.** Nếu không dùng cookie mà dùng STOMP token trong CONNECT, cần gì thêm?  
**Trả lời:** Kiểm chứng token bằng ChannelInterceptor trước message authorization, xử lý CSRF/origin theo kiến trúc và quyền cho SEND/SUBSCRIBE.

## 17. Tài liệu chính thức

- Spring Framework 6.2 — **WebSocket API, Handshake and Allowed Origins**: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/server.html
- Spring Framework — **WebSocket STOMP Overview**: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/overview.html
- Spring Framework 6.2 — **Token Authentication over STOMP**: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/authentication-token-based.html
- Spring Security 6.5 — **WebSocket Security, Authentication, Authorization and STOMP CSRF**: https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/websocket.html
- Spring Security 6.5 — **CSRF for HTTP Forms**: https://docs.spring.io/spring-security/reference/6.5/servlet/exploits/csrf.html
- Spring Security 6.5 — **Form Login**: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/form.html
- Spring Boot — **WebSocket Support**: https://docs.spring.io/spring-boot/reference/messaging/websockets.html
- RFC 6455 — **The WebSocket Protocol** (handshake, frames, close codes): https://www.rfc-editor.org/rfc/rfc6455
- RFC 6454 — **The Web Origin Concept**: https://www.rfc-editor.org/rfc/rfc6454
- RFC 8441 — **Bootstrapping WebSockets with HTTP/2**: https://www.rfc-editor.org/rfc/rfc8441
- MDN — **WebSocket API**: https://developer.mozilla.org/en-US/docs/Web/API/WebSocket
- Spring Boot 3.5.16 release/support notice: https://spring.io/blog/2026/06/25/spring-boot-3-5-16-available-now/

**Kết luận:** WebSocket luôn cần được bảo vệ **trước** và **sau** HTTP handshake. Trước `101`, giới hạn Origin, xác thực HTTP Principal và chỉ nâng cấp request hợp lệ. Sau `101`, kiểm tra quyền **cho từng message/destination**, quản lý session/token expiry, payload limits, concurrency và close codes. Với STOMP, bổ sung security ở `CONNECT`/`SEND`/`SUBSCRIBE`, bao gồm CSRF CONNECT khi cấu hình Spring Security messaging. Đừng coi Origin là authentication, đừng trông chờ HTTP filters bảo vệ mọi message, và hãy kiểm thử cả server thật lẫn reverse proxy WSS.