# HandshakeInterceptor, kiểm tra Origin và thông tin người dùng trong WebSocket/STOMP

## 1. Bối cảnh: WebSocket cần kiểm tra gì trước khi nâng cấp kết nối?

Trong ứng dụng Spring, trình duyệt có thể mở kết nối WebSocket để trao đổi dữ liệu thời gian thực: trò chuyện, thông báo hoặc cập nhật trạng thái. Khác với HTTP request thông thường, một kết nối WebSocket có thể tồn tại lâu và truyền nhiều thông điệp theo hai chiều. Nếu chấp nhận nhầm kết nối của một website không tin cậy hoặc gắn sai người dùng, hậu quả không chỉ là một response đơn lẻ: kẻ tấn công có thể gửi/nhận thông điệp trên một phiên kéo dài.

Giai đoạn bắt đầu bằng HTTP request *handshake*. Máy chủ xét các điều kiện kết nối, sau đó mới đồng ý nâng cấp lên WebSocket (khi thành công, HTTP status điển hình là **101 Switching Protocols**). Nếu ứng dụng dùng STOMP, client tiếp tục gửi frame STOMP `CONNECT` trên kết nối đã được thiết lập; từ đó mới có các frame `SUBSCRIBE`, `SEND` và những thông điệp nghiệp vụ khác.

```text
Trình duyệt                         Spring WebSocket/STOMP server
     |                                            |
     |-- HTTP GET /ws, Upgrade: websocket ------->|
     |   Origin: https://app.example.com          |
     |   Cookie: phiên đăng nhập (nếu có)         |
     |                                            v
     |                             HTTP security filter chain
     |                                            |
     |                             HandshakeInterceptor.beforeHandshake
     |                                  | kiểm tra request/Principal
     |                                  | gắn session attributes
     |                                            |
     |                             kiểm tra Origin và handshake handler
     |                                  |
     |<-------------- HTTP 101 (nếu được chấp nhận)
     |                                            |
     |--------- STOMP CONNECT frame ------------->|
     |                             clientInboundChannel:
     |                             ChannelInterceptor / bảo mật STOMP
     |<------------- STOMP CONNECTED -------------|
     |--------- STOMP SUBSCRIBE / SEND ---------->|
     |                             kiểm tra quyền từng message/destination
```

Ba câu hỏi khác nhau:

1. **Origin có được chấp nhận không?** Origin thể hiện nguồn gốc trang web đã khởi tạo kết nối trong ngữ cảnh trình duyệt; cơ chế này góp phần chống hành vi mở WebSocket trái phép từ website khác.
2. **Người dùng là ai?** Trên đường HTTP handshake, ứng dụng thường đã xác thực bằng Spring Security/session hoặc cơ chế HTTP tương đương; `Principal` đã được xác thực có thể được liên kết với WebSocket session.
3. **Người dùng được phép gửi hoặc đăng ký thông điệp nào?** Đây là kiểm soát quyền theo frame/destination trong STOMP, **không được bỏ qua chỉ vì handshake thành công**.

`HandshakeInterceptor` phù hợp với việc quan sát và chuẩn bị handshake, cho phép từ chối sớm hoặc chuyển metadata sang WebSocket session. Nó không thay thế HTTP authentication, chính sách Origin hay kiểm tra quyền gửi message.

## 2. Phân biệt các thành phần của Spring

| Thành phần | Chạy lúc nào? | Vai trò |
| --- | --- | --- |
| `SecurityFilterChain` (Servlet) | Khi HTTP request đi vào, trước khi upgrade | Xác thực HTTP, phân quyền truy cập endpoint, chính sách CSRF/headers phù hợp |
| `HandshakeInterceptor` | Trước và sau xử lý handshake | Kiểm tra request, từ chối handshake, thêm thuộc tính cho WebSocket session |
| `HandshakeHandler` / `DefaultHandshakeHandler` | Trong bước thương lượng HTTP upgrade | Kiểm tra khả năng upgrade, Origin theo cấu hình, sub-protocol và thiết lập Principal |
| `WebSocketSession` | Sau khi WebSocket được mở | Thể hiện một kết nối, ID, headers và attributes, Principal |
| `ChannelInterceptor` | Khi xử lý message trên channel như `clientInboundChannel` | Đọc/kiểm soát STOMP `CONNECT`, `SEND`, `SUBSCRIBE` và những frame tương ứng |
| Spring Security message authorization | Trong chuỗi xử lý STOMP message inbound | Quyết định ai có thể gửi/đăng ký destination nào |
| `@MessageMapping` / `@SendTo` | Khi message STOMP được điều phối đến controller | Xử lý nghiệp vụ, gửi response đến broker/destination |

Không nhầm `HandshakeInterceptor` với `HandlerInterceptor` dành cho HTTP MVC request thông thường. Cũng không nhầm WebSocket raw handler (`WebSocketConfigurer` và `WebSocketHandler`) với STOMP endpoint (`WebSocketMessageBrokerConfigurer` và `StompEndpointRegistry`).

### 2.1 Hợp đồng HandshakeInterceptor

Interface có hai callback:

```java
boolean beforeHandshake(
        ServerHttpRequest request,
        ServerHttpResponse response,
        WebSocketHandler wsHandler,
        Map<String, Object> attributes) throws Exception;

void afterHandshake(
        ServerHttpRequest request,
        ServerHttpResponse response,
        WebSocketHandler wsHandler,
        Exception exception);
```

- `beforeHandshake` nhận HTTP request/response, handler đích và map attributes của WebSocket session. **Trả `true`** để tiếp tục handshake; **trả `false`** để chặn. Nếu chặn, có thể đặt status (ví dụ 401 hoặc 403) lên response trước khi trả về `false`.
- Map `attributes` được Spring **sao chép** sang session, không dùng nguyên map reference mà interceptor đã nhận. Đặt các giá trị nhỏ, ổn định; không dùng nó như kênh truyền credential bí mật hoặc object có tài nguyên chưa được giải phóng.
- `afterHandshake` chạy sau bước handshake để quan sát kết quả/ngoại lệ nếu có. Nó không có quyền “trả lại true” để phục hồi handshake bị từ chối và **không phải callback sau mỗi STOMP message**.
- Tham số `WebSocketHandler` là handler được cấu hình cho endpoint; trong ứng dụng STOMP, Spring sử dụng hạ tầng xử lý sub-protocol đằng sau endpoint này.

Không dùng `attributes.put("user", "alice")` để tự tạo `Principal` hoặc nâng quyền cho một kết nối. Thuộc tính chỉ là metadata của session; nhận dạng và xác thực cần đến từ thành phần bảo mật đã được tin cậy.

## 3. Kiểm tra Origin: nguyên nhân, cấu hình và giới hạn

### 3.1 Origin không đồng nghĩa Host, Referer hoặc CORS thông thường

Ví dụ trang ở `https://app.example.com` mở `wss://api.example.com/ws`. HTTP WebSocket handshake từ trình duyệt có thể mang:

```http
GET /ws HTTP/1.1
Host: api.example.com
Upgrade: websocket
Connection: Upgrade
Origin: https://app.example.com
Sec-WebSocket-Version: 13
Sec-WebSocket-Key: <giá trị dùng cho handshake>
```

`Origin` phản ánh nguồn gốc trang gọi (scheme + host + port), không phải URL của server đích, cũng không phải `Referer`. Với các công cụ máy chủ/CLI, header `Origin` có thể bị tự đặt hoặc giả mạo. Vì vậy kiểm tra Origin nhằm phòng chống những tình huống liên quan đến **browser**, không đủ để xác thực người dùng hoặc bảo vệ API khỏi client tùy biến.

Trình duyệt không áp dụng nguyên cơ chế same-origin của XHR/fetch để cấm mở WebSocket cross-origin. Máy chủ phải quyết định Origin nào được phép, nhất là khi credential được gửi qua cookie (rủi ro **Cross-Site WebSocket Hijacking**, hay CSWSH).

### 3.2 Cách khuyến nghị: setAllowedOrigins trên endpoint

Trong Spring STOMP, cấu hình danh sách Origin được phép ngay trên endpoint:

```java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws")
            .setAllowedOrigins("https://app.example.com");
}
```

Đây là đoạn phương thức trong class triển khai `WebSocketMessageBrokerConfigurer`, chưa phải tệp độc lập. Spring hỗ trợ kiểm tra Origin tại phần handshake; mặc định WebSocket/SockJS chỉ chấp nhận same-origin. Có thể chỉ định danh sách các origin cụ thể bằng `setAllowedOrigins(...)`, hoặc dùng `setAllowedOriginPatterns(...)` khi thực sự cần pattern và đã đánh giá phạm vi.

Nguyên tắc:

- Ghi **origin đầy đủ** gồm scheme, host và port khi cần, ví dụ `http://localhost:5173` lúc phát triển; `https://app.example.com` khi triển khai. Không gửi path `/dashboard` trong danh sách origin.
- `https://app.example.com` và `http://app.example.com` là hai origin khác nhau; port khác mặc định cũng tạo origin khác.
- Tránh `setAllowedOrigins("*")` trên endpoint được xác thực bằng cookie hoặc truyền dữ liệu nhạy cảm. Cho phép mọi Origin làm mất một lớp bảo vệ trình duyệt.
- Với reverse proxy, bảo đảm xử lý đúng scheme/host theo forwarded headers **chỉ từ proxy tin cậy**. Nếu không, phép so Origin với endpoint nhìn từ ngoài có thể thất bại hoặc bị diễn giải sai.
- Nếu bật `withSockJS()`, thay đổi danh sách Origin còn ảnh hưởng các fallback transport; một số cơ chế như iframe có thể bị vô hiệu khi bật giới hạn origin.

Không cần viết lại bộ so sánh Origin trong `HandshakeInterceptor` khi quy tắc mặc định và `setAllowedOrigins` đã đáp ứng. Interceptor vẫn có thể thực hiện chính sách bổ sung, chẳng hạn kiểm tra thuê bao/tenant từ server hoặc từ chối kết nối bảo mật chưa xác thực.

### 3.3 Vì sao Origin và CSRF có liên quan nhưng khác nhau?

Origin giúp hạn chế website nào có thể thiết lập WebSocket từ browser. CSRF bảo vệ khỏi các hành động tận dụng credential tự động gửi (ví dụ session cookie) trong bối cảnh người dùng đã đăng nhập.

Khi bật Spring Security cho STOMP, cấu hình an toàn còn có thể yêu cầu **CSRF token trong frame STOMP `CONNECT`**, cung cấp lớp bảo vệ tại cấp messaging. Tùy phiên bản/cách kích hoạt security, việc gửi CONNECT mà không có token có thể bị từ chối dù HTTP handshake đã thành công. Đặc biệt với SockJS fallback, một số transport dùng HTTP POST; không giải quyết bằng cách tắt CSRF trên toàn ứng dụng. Nếu cần ngoại lệ HTTP để SockJS hoạt động, giới hạn chặt vào các URL SockJS và vẫn bảo vệ cấp STOMP theo cấu hình security.

**Lỗi phổ biến:** “Đã setAllowedOrigins thì không cần phân quyền message”. Origin không quyết định user nào được `SUBSCRIBE /topic/private` hoặc `SEND /app/admin`. Cần cấu hình chính sách message-level dựa trên Principal/Authentication đáng tin.

## 4. Xác thực và thông tin người dùng trong handshake

### 4.1 Dùng Principal đã xác thực trên HTTP request

Trường hợp thông dụng: người dùng đã đăng nhập qua HTTP/Spring Security; khi trình duyệt mở WebSocket, request handshake gửi cookie phiên của trang phù hợp. Spring lấy `Principal` đã xác thực từ HTTP request và chuyển sang WebSocket/STOMP session. Ở message controller có thể nhận `Principal` như một tham số.

```text
HTTP login / trusted session authentication
    |
    v
SecurityFilterChain xác thực request GET /ws
    |
    v
request.getPrincipal()  ---> DefaultHandshakeHandler
    |                                 |
    |                                 v
    |                         WebSocket Principal
    |                                 |
    v                                 v
HandshakeInterceptor              STOMP message "user"
    |
    +--> session attributes (metadata bổ sung)
```

Không tự tin vào `userId` lấy từ query `?user=alice`, bất kỳ header client tự đặt hoặc native STOMP header `login` để quyết định Principal của một request đã được xác thực bằng HTTP.

Trong cấu hình STOMP mặc định của Spring, header `login` và `passcode` ở frame CONNECT không được dùng để xác thực lại người dùng WebSocket: Spring lấy danh tính từ HTTP handshake. Nếu ứng dụng dùng bearer token riêng trong STOMP CONNECT (thường gặp khi browser không gửi được custom HTTP Authorization header từ WebSocket API), cần một `ChannelInterceptor` xử lý token trên `clientInboundChannel`, xác thực token ở server rồi đặt `accessor.setUser(authentication)` theo quy tắc Spring; việc đó diễn ra **sau handshake**, không phải trong `HandshakeInterceptor`.

### 4.2 Tạo HandshakeInterceptor để từ chối anonymous và gắn metadata

Ví dụ sau cố ý không tự thực hiện username/password validation trong interceptor. Nó giả định HTTP security chain đã xác thực request tới `/ws`. Nếu không có principal hợp lệ, yêu cầu bị từ chối. Thuộc tính `connectedUserId` chỉ phục vụ đối chiếu session; quyền thực tế vẫn dựa vào `Principal`.

**Tệp `VerifiedUserHandshakeInterceptor.java`:**

```java
package com.example.websocket;

import java.security.Principal;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.web.socket.WebSocketHandler;
import org.springframework.web.socket.server.HandshakeInterceptor;

public final class VerifiedUserHandshakeInterceptor
        implements HandshakeInterceptor {

    public static final String USER_ID = "connectedUserId";

    @Override
    public boolean beforeHandshake(
            ServerHttpRequest request,
            ServerHttpResponse response,
            WebSocketHandler wsHandler,
            Map<String, Object> attributes) {

        Principal principal = request.getPrincipal();

        if (principal == null
                || principal.getName() == null
                || principal.getName().isBlank()) {
            response.setStatusCode(HttpStatus.UNAUTHORIZED);
            return false;
        }

        attributes.put(USER_ID, principal.getName());
        return true;
    }

    @Override
    public void afterHandshake(
            ServerHttpRequest request,
            ServerHttpResponse response,
            WebSocketHandler wsHandler,
            Exception exception) {
        // Để trống: không cần xử lý sau handshake cho ví dụ này.
    }
}
```

Đây là mã Java 17+ đầy đủ cho một class dùng trong dự án Spring WebSocket. Nếu dự án có Spring Security, phải bảo đảm **endpoint handshake được bảo vệ bằng HTTP security**: ở nhiều cấu hình, `AnonymousAuthenticationToken` có thể được biểu diễn trong SecurityContext dù người dùng chưa đăng nhập; không dựa duy nhất vào việc một object `Principal` có tên hay không để định nghĩa xác thực ở mọi hạ tầng. Chính sách authentication/authorization chính nên thuộc `SecurityFilterChain`, còn ví dụ interceptor đóng vai trò kiểm tra phụ và sao chép metadata sau khi đã xác thực.

**Điểm cần nhớ:** `attributes.put(USER_ID, principal.getName())` không tự thay đổi Principal của WebSocket session. `DefaultHandshakeHandler`/hạ tầng Spring quản lý việc chọn Principal. Nếu cần ánh xạ danh tính tùy biến ngoài cơ chế HTTP mặc định, phải dùng chiến lược đã xác thực và tích hợp đúng `HandshakeHandler.determineUser(...)` hoặc STOMP `ChannelInterceptor`, tránh tự gán tên người dùng từ dữ liệu không tin cậy.

### 4.3 Các loại dữ liệu được và không nên đưa vào attributes

Phù hợp: ID điều tra sự cố, mã tenant đã xác minh, thời điểm kết nối, marker phiên bản giao thức hoặc cờ kỹ thuật nhỏ. Không phù hợp: mật khẩu, JWT nguyên văn, refresh token, toàn bộ `SecurityContext` mutable, raw cookie, body nhạy cảm, connection/database handle.

Map attributes có vòng đời gắn với WebSocket session; kết nối có thể sống lâu hơn HTTP request. Vì vậy số lượng và kích thước dữ liệu cần nhỏ, có kế hoạch dọn dẹp và chính sách truy cập đúng mức.

## 5. Ví dụ cấu hình STOMP endpoint hoàn chỉnh

**Tệp `WebSocketStompConfig.java`**:

```java
package com.example.websocket;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketStompConfig
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .addInterceptors(new VerifiedUserHandshakeInterceptor())
                .setAllowedOrigins("https://app.example.com");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
```

Giải thích từng thành phần:

- `@EnableWebSocketMessageBroker` bật hạ tầng STOMP over WebSocket.
- `/ws` là đường dẫn **HTTP handshake**; nó không phải destination mà client `SUBSCRIBE` hoặc `SEND` tới.
- `addInterceptors(...)` đăng ký `HandshakeInterceptor` ở bước HTTP handshake.
- `setAllowedOrigins(...)` yêu cầu Origin của trang thuộc danh sách cho phép.
- `/app` là prefix cho thông điệp đến `@MessageMapping`; `/topic` và `/queue` được simple broker quản lý trong ví dụ.

Với ứng dụng Servlet đã dùng Spring Security, nên bảo vệ endpoint bằng chuỗi HTTP security phù hợp. Đoạn sau giả định có `spring-boot-starter-security` và xác thực web đã được cấu hình (login/session hoặc cơ chế khác):

**Tệp `WebHttpSecurityConfig.java`:**

```java
package com.example.websocket;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
public class WebHttpSecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/ws", "/ws/**").authenticated()
                .anyRequest().permitAll());
        http.formLogin(withDefaults());
        return http.build();
    }
}
```

**Lưu ý về phạm vi:** ví dụ này dành cho Spring MVC/Servlet + Spring Security 6, nơi HTTP handshake được xử lý qua Servlet security chain; nó không phải cấu hình Spring WebFlux SecurityFilterChain reactive. Phần `anyRequest().permitAll()` chỉ là giả định để minh họa endpoint riêng; trong sản phẩm thật, thay bằng chính sách HTTP hiện hữu của hệ thống, tuyệt đối không mở toàn bộ route nhạy cảm. Cấu hình ví dụ không tắt CSRF, không cấp quyền STOMP tùy tiện; khi kích hoạt WebSocket message security, cần cấu hình authorization và CONNECT CSRF tương ứng.

Với Spring Boot 3.x/Java 17+, ví dụ Gradle trong dự án đã áp dụng Spring Boot dependency management:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-websocket'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Spring Boot 3.3.x trong module học thường dùng Java 21 nhưng mã trên tương thích Java 17+. Đặt ba class trong package `com.example.websocket` nằm dưới package gốc của ứng dụng Spring Boot để component scanning nhận được `@Configuration`. Ví dụ này có tên miền tượng trưng; kết nối cross-origin từ trang khác ngoài `https://app.example.com` sẽ bị bộ kiểm tra Origin của endpoint từ chối. Tạo tài khoản/xác thực thực tế theo chính sách của ứng dụng; không hardcode username/password sản phẩm trong tài liệu.

## 6. Đọc người dùng và session attributes trong STOMP message controller

Sau khi handshake thành công và STOMP client gửi message, ứng dụng có thể đọc Principal và session attributes ở một `@MessageMapping`. Hai nguồn này khác nhau: Principal là danh tính đã được Spring gắn với session; attributes là dữ liệu bổ sung được tạo trong handshake.

**Tệp `IdentityMessageController.java`:**

```java
package com.example.websocket;

import java.security.Principal;
import java.util.Map;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
public class IdentityMessageController {

    @MessageMapping("/whoami")
    @SendToUser("/queue/identity")
    public String whoAmI(
            Principal principal,
            SimpMessageHeaderAccessor headers) {

        Map<String, Object> attributes = headers.getSessionAttributes();
        Object copiedUser = attributes == null
                ? null
                : attributes.get(VerifiedUserHandshakeInterceptor.USER_ID);

        // Demo: chỉ trả về username đã xác thực.
        // Metadata phiên chỉ được dùng để quan sát/đối chiếu.
        if (principal == null) {
            throw new IllegalStateException("Authenticated user required");
        }

        String verifiedName = principal.getName();
        if (copiedUser != null
                && !verifiedName.equals(copiedUser.toString())) {
            throw new IllegalStateException("Session identity mismatch");
        }
        return verifiedName;
    }
}
```

Một STOMP client đã được xác thực có thể gửi message đến `/app/whoami` và lắng nghe destination người dùng tương ứng như `/user/queue/identity`, tùy cấu hình broker và messaging security. Dữ liệu trả về là tên người dùng đã xác thực; không trả thông tin bí mật.

Ở đây việc so khớp hai trường chỉ để **phát hiện tình huống metadata không nhất quán** trong ví dụ học tập. Quyết định quyền truy cập vẫn cần dựa vào `Authentication`/Principal và chính sách server-side, không dựa riêng vào một giá trị trong session attributes. Khi identity có thể thay đổi trong vòng đời kết nối, thiết kế cần xử lý đổi phiên, token hết hạn, khóa tài khoản và chính sách đóng kết nối riêng.

### 6.1 Phân biệt kết nối, người dùng và phiên đăng ký

- Một tài khoản có thể mở **nhiều WebSocket session** (nhiều tab/thiết bị), nên không coi username là ID kết nối duy nhất.
- `sessionId` được Spring gắn với một WebSocket/STOMP session; user principal name nhận diện người dùng theo cơ chế xác thực.
- `attributes` có thể chứa thông tin bổ trợ theo từng kết nối.
- Một STOMP session có thể chứa nhiều subscription; quyền `SUBSCRIBE` phải kiểm tra dựa trên destination và user chứ không thể chỉ dựa vào “đã handshake”.
- `SimpUserRegistry` và hạ tầng `/user` có thể giúp Spring chuyển thông điệp theo người dùng/phiên; không tự suy luận rằng mỗi user có đúng một socket.

## 7. Nếu token nằm trong STOMP CONNECT thì HandshakeInterceptor có đọc được không?

**Không.** HTTP handshake xảy ra **trước** khi có frame STOMP `CONNECT`. `HandshakeInterceptor` chỉ nhìn thấy HTTP request (cookies, Origin, headers ở lớp HTTP), không thể đọc native headers của một frame STOMP chưa được gửi.

Ứng dụng browser thường có các lựa chọn:

1. **Session/cookie authentication ở HTTP handshake:** Spring Security xác thực request; Principal được Spring nối sang WebSocket/STOMP. Trường hợp phù hợp khi site và WebSocket endpoint dùng chung hệ thống đăng nhập.
2. **Token trong STOMP CONNECT:** sau handshake, `ChannelInterceptor` trên `clientInboundChannel` đọc header token, gọi thành phần xác thực server-side, tạo `Authentication` hợp lệ và dùng `StompHeaderAccessor.setUser(...)` cho CONNECT. Phải xử lý khi token thiếu/sai/hết hạn và áp dụng message authorization.
3. **Token/cookie ở HTTP handshake:** với browser API `new WebSocket(...)` không thể tự do đặt bất kỳ custom HTTP header nào như với `fetch`. Không nên đưa bearer token dài hạn vào URL query vì dễ lộ qua log, browser history hay hạ tầng; chọn cơ chế đúng kiến trúc và các biện pháp bảo vệ thích hợp.

Đoạn sau minh họa **cấu trúc** của interceptor STOMP; phần xác thực token cần một dịch vụ tin cậy của hệ thống nên không viết giả lập có thể gây hiểu nhầm là xác thực thật:

```java
@Override
public void configureClientInboundChannel(ChannelRegistration registration) {
    registration.interceptors(new ChannelInterceptor() {
        @Override
        public Message<?> preSend(Message<?> message,
                                   MessageChannel channel) {
            StompHeaderAccessor accessor =
                    MessageHeaderAccessor.getAccessor(
                            message, StompHeaderAccessor.class);

            if (accessor != null
                    && StompCommand.CONNECT.equals(accessor.getCommand())) {
                // Lấy token từ native STOMP headers.
                // Xác thực token bằng dịch vụ bảo mật thực tế.
                // Chỉ sau khi xác thực thành công:
                // accessor.setUser(validatedAuthentication);
            }
            return message;
        }
    });
}
```

Đây là *mảnh minh họa cấu trúc* trong class `WebSocketMessageBrokerConfigurer`, **không phải logic xác thực chạy độc lập**. Cần import `ChannelRegistration`, `ChannelInterceptor`, `Message`, `MessageChannel`, `MessageHeaderAccessor`, `StompHeaderAccessor` và `StompCommand`. Không dùng mã này như security production nếu chưa hiện thực hóa kiểm tra chữ ký, hạn sử dụng, người dùng, quyền và từ chối kết nối. Với Spring Security messaging authorization, interceptor xác thực CONNECT phải được sắp trước interceptor phân quyền của security.

Nếu dùng xác thực HTTP mặc định, Spring có thể bỏ qua `login` và `passcode` của STOMP CONNECT. Không được nhận một chuỗi tùy ý trong `login` rồi coi đó là tên tài khoản đã xác thực.

## 8. Kiểm thử HandshakeInterceptor không cần server mạng thật

Kiểm thử đơn vị giúp xác nhận quy tắc nhận/từ chối theo Principal và metadata, không yêu cầu mở WebSocket thật. Dùng Mockito để mô phỏng `ServerHttpRequest`, `ServerHttpResponse` và `WebSocketHandler`. Class dưới đây chạy với JUnit 5 + spring-boot-starter-test.

**Tệp `VerifiedUserHandshakeInterceptorTest.java`** trong `src/test/java/com/example/websocket/`:

```java
package com.example.websocket;

import java.security.Principal;
import java.util.HashMap;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.web.socket.WebSocketHandler;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class VerifiedUserHandshakeInterceptorTest {

    private final VerifiedUserHandshakeInterceptor interceptor =
            new VerifiedUserHandshakeInterceptor();

    @Test
    void rejectsHandshakeWithoutPrincipal() {
        ServerHttpRequest request = mock(ServerHttpRequest.class);
        ServerHttpResponse response = mock(ServerHttpResponse.class);
        WebSocketHandler handler = mock(WebSocketHandler.class);
        Map<String, Object> attributes = new HashMap<>();

        boolean proceed = interceptor.beforeHandshake(
                request, response, handler, attributes);

        assertFalse(proceed);
        assertTrue(attributes.isEmpty());
        verify(response).setStatusCode(HttpStatus.UNAUTHORIZED);
    }

    @Test
    void acceptsTrustedPrincipalAndCopiesItsName() {
        ServerHttpRequest request = mock(ServerHttpRequest.class);
        ServerHttpResponse response = mock(ServerHttpResponse.class);
        WebSocketHandler handler = mock(WebSocketHandler.class);
        Map<String, Object> attributes = new HashMap<>();
        Principal trustedUser = () -> "alice";

        when(request.getPrincipal()).thenReturn(trustedUser);

        boolean proceed = interceptor.beforeHandshake(
                request, response, handler, attributes);

        assertTrue(proceed);
        assertEquals("alice", attributes.get(
                VerifiedUserHandshakeInterceptor.USER_ID));
        verify(response, never()).setStatusCode(HttpStatus.UNAUTHORIZED);
    }
}
```

Chạy trong dự án Gradle có wrapper và dependencies đã nêu:

```bash
./gradlew test --tests '*VerifiedUserHandshakeInterceptorTest'
```

Với Windows PowerShell dùng `.\gradlew.bat test --tests '*VerifiedUserHandshakeInterceptorTest'`. Khi cả hai ca thành công, JUnit thông báo **2 tests passed** trong báo cáo test; không có stdout cố định do test này không gọi `System.out.println`.

Bài test này kiểm tra hành vi **của interceptor** trước handshake. Nó không kiểm tra toàn bộ HTTP security, Origin policy của endpoint, websocket upgrade, cookie hay STOMP authorization. Những điều đó cần integration tests ở lớp tương ứng.

### 8.1 Kiểm thử tích hợp Origin và security

Tạo một test server với endpoint `/ws` đã cấu hình và một danh tính được xác thực. Thử các trường hợp:

| Trường hợp | Kỳ vọng |
| --- | --- |
| Origin đúng danh sách và HTTP Principal hợp lệ | Có thể tiếp tục handshake (nếu các điều kiện protocol/security khác đều đạt) |
| Origin không thuộc danh sách | Handshake bị từ chối theo chính sách Origin |
| Không có HTTP Principal hợp lệ | HTTP security hoặc interceptor từ chối; ví dụ interceptor trả 401 nếu được gọi |
| Origin đúng nhưng STOMP CONNECT thiếu CSRF token khi security yêu cầu | Có thể upgrade WebSocket, nhưng CONNECT bị chặn ở lớp messaging |
| User đã xác thực gửi SEND đến destination không được phép | Message bị từ chối ở lớp authorization |
| Browser đổi tab / tạo thêm kết nối | Các WebSocket session riêng có metadata riêng |
| STOMP CONNECT mang username giả mạo | Không được ghi đè Principal xác thực trên HTTP |

Khi kiểm thử handshake bằng công cụ CLI, header `Origin` có thể do công cụ tự tạo. Kết quả Origin hợp lệ **không chứng minh người dùng đã được xác thực**. Kiểm thử browser thật (cookie và CORS/Origin) và HTTP tool nên được xem là hai loại bằng chứng bổ sung.

Không hardcode mã status cụ thể của tất cả trường hợp bị từ chối Origin: status cuối cùng có thể phụ thuộc Spring/Security/container/handler nào chặn trước. Test nên xác minh request bị từ chối ở đúng lớp và lý do, trừ khi ứng dụng đã quy định status thành hợp đồng riêng.

## 9. Lỗi thường gặp

| Sai lầm | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Tin rằng HTTP 101 nghĩa là được phép mọi STOMP destination | Bỏ qua quyền gửi hoặc subscribe | Cấu hình Spring Security message authorization hoặc ChannelInterceptor thích hợp |
| Cho phép Origin `*` để “chữa lỗi CORS” | Cho website bất kỳ thử thiết lập WebSocket, rủi ro với cookie/session | Khai báo allowlist Origin chính xác, hiểu scheme/host/port |
| Coi Origin là danh tính client | Client ngoài browser có thể giả mạo Origin | Kết hợp authentication, authorization, rate limit và chính sách bảo mật |
| Lấy `userId` từ query string rồi gán vào attributes | User có thể tự xưng danh tính bất kỳ | Lấy Principal đáng tin từ HTTP Security hoặc token đã kiểm chứng |
| Dùng `attributes.put(...)` để mong thay Principal | Metadata không tự tạo authentication | Dùng cơ chế chọn Principal/ChannelInterceptor đúng tầng |
| Đọc token STOMP CONNECT trong HandshakeInterceptor | Frame CONNECT đến sau handshake | Dùng `ChannelInterceptor` của `clientInboundChannel` |
| Tự tin vào STOMP `login`/`passcode` mặc định | Spring thường bỏ qua chúng khi xác thực WebSocket dựa trên HTTP | Thiết kế authentication tường minh |
| Không kiểm tra quyền từng `SEND`/`SUBSCRIBE` | User hợp lệ vẫn có thể truy cập dữ liệu của người khác | Phân quyền theo user + destination |
| Đưa JWT hay cookie nguyên văn vào session attributes/log | Lộ bí mật và giữ trong session lâu | Lưu metadata tối thiểu, không ghi secret |
| Dùng `setAllowedOrigins("http://localhost")` nhưng frontend chạy port khác | Handshake cross-origin lỗi | Cấu hình đầy đủ scheme/host/port của frontend |
| Tắt CSRF toàn cục chỉ để SockJS chạy | Mở lỗ hổng ở các endpoint HTTP khác | Cấu hình ngoại lệ hẹp và bảo vệ STOMP CONNECT phù hợp |
| Đổi Origin check theo forwarded headers không tin cậy | Lách hoặc từ chối sai chính sách | Chỉ tin forwarding từ reverse proxy đã kiểm soát |

## 10. Tóm tắt và câu hỏi tự kiểm tra

**Chuỗi quyết định cần nhớ:**

```text
HTTP Security xác thực → Origin policy → HandshakeInterceptor
                  ↓ nếu chấp nhận
        WebSocket session / Principal / attributes
                  ↓
        STOMP CONNECT (có thể có kiểm tra CSRF/token)
                  ↓
        STOMP SEND/SUBSCRIBE → message authorization → nghiệp vụ
```

Câu hỏi tự ôn tập:

1. `HandshakeInterceptor.beforeHandshake` trả `false` nghĩa là gì? **Dừng handshake trước khi kết nối WebSocket được mở.**
2. Tại sao `attributes.put("userId", "...")` không tương đương xác thực? **Nó chỉ đặt metadata, không chứng minh danh tính hoặc tạo Principal.**
3. `Origin` đến từ đâu và có thể tin tuyệt đối không? **Trình duyệt gửi khi bắt đầu WebSocket; client ngoài browser có thể tự giả mạo.**
4. Làm sao giới hạn frontend được kết nối? **Dùng `setAllowedOrigins`/`setAllowedOriginPatterns` với phạm vi cần thiết và bảo vệ authentication tương ứng.**
5. Vì sao STOMP CONNECT token không thể lấy trong HTTP HandshakeInterceptor? **Handshake đi trước frame STOMP CONNECT.**
6. Có phải chỉ cần chặn user lạ ở handshake là đủ? **Không; người dùng hợp lệ vẫn cần được phân quyền theo destination và loại message.**
7. User có thể mở nhiều WebSocket không? **Có; mỗi kết nối có session ID và thuộc tính riêng, dù dùng chung Principal.**
8. Trạng thái HTTP handshake có phải là trạng thái mọi message sau đó? **Không; handshake chỉ tạo phiên, xử lý STOMP là một giai đoạn khác.**

Khi áp dụng trong ứng dụng thật, ưu tiên xây chính sách phân tầng: HTTP authentication hợp lệ, danh sách origin tin cậy, interceptor chỉ lưu thông tin phiên tối thiểu, bảo vệ CONNECT khi cần và kiểm soát quyền ở cấp message.

## 11. Tài liệu chính thức

- [Spring Framework — WebSocket server, Handshake và Allowed Origins](https://docs.spring.io/spring-framework/reference/web/websocket/server.html).
- [Spring Framework — STOMP enable endpoints](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html).
- [Spring Framework — STOMP authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html).
- [Spring Framework — Token authentication ở STOMP CONNECT](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html).
- [Spring Framework — STOMP interception/authorization](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/interceptors.html).
- [Spring Security — WebSocket security, same-origin, CSRF](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html).
- [Javadoc — HandshakeInterceptor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/server/HandshakeInterceptor.html).
