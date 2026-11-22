# Same-origin, CSRF và SockJS theo cấu hình bảo mật

Trong ứng dụng Spring dùng STOMP trên WebSocket, bảo mật cần kiểm soát cả kết nối ban đầu lẫn các frame được gửi sau khi kết nối. Ba cơ chế thường bị nhầm lẫn là **Same-origin**, **CSRF** và **CORS**. Chúng giải quyết các vấn đề khác nhau:

- **Origin validation** giới hạn website nào được phép khởi tạo WebSocket hoặc SockJS connection từ trình duyệt.
- **CSRF protection** yêu cầu bằng chứng mà trang hợp lệ cùng origin có thể lấy được trước khi mở STOMP session.
- **Message authorization** quyết định user được phép gửi frame đến destination nào và subscribe destination nào.

SockJS thêm một điểm cần chú ý: khi không dùng WebSocket, nó có thể chuyển sang các HTTP transport như XHR streaming hoặc polling. Những request HTTP này đi qua Spring Security filter chain, nên cần cấu hình riêng cho endpoint SockJS mà vẫn giữ kiểm tra CSRF ở frame STOMP CONNECT.

## 1. Vì sao WebSocket cần bảo vệ Same-origin?

Same-origin policy của trình duyệt áp dụng cho nhiều API như đọc response của một origin khác, nhưng trình duyệt không tự chặn một trang khác origin mở WebSocket tới server. Nếu người dùng đã đăng nhập vào một website bằng cookie, một website độc hại có thể thử mở WebSocket tới website đó. Cookie phiên có thể được trình duyệt gửi kèm handshake tùy chính sách cookie và request.

Kịch bản tấn công thường gọi là **Cross-Site WebSocket Hijacking (CSWSH)**:

1. Người dùng đăng nhập vào https://bank.example.
2. Trình duyệt giữ cookie phiên đăng nhập.
3. Người dùng mở một trang không đáng tin cậy, ví dụ https://evil.example.
4. Trang đó thử mở WebSocket tới wss://bank.example/ws.
5. Nếu server chấp nhận kết nối dựa trên cookie mà không kiểm tra origin và không yêu cầu bằng chứng CSRF, trang độc hại có thể thực hiện hành động dưới phiên của người dùng.

Khi handshake WebSocket được gửi, trình duyệt thường gửi header Origin. Server cần kiểm tra giá trị này. Spring Framework mặc định chỉ chấp nhận same-origin cho WebSocket và SockJS từ phiên bản 4.1.5. Có thể cấu hình thêm danh sách origin được phép khi frontend và backend thực sự chạy ở các origin khác nhau.

Origin gồm scheme, host và port. Ví dụ https://app.example.com khác origin với http://app.example.com hoặc https://app.example.com:8443.

**Origin không phải thông tin xác thực.** Client không phải trình duyệt có thể tự đặt header Origin. Vì vậy, allowlist giúp bảo vệ trình duyệt khỏi kết nối cross-origin nhưng không thay thế authentication, CSRF hoặc authorization.

## 2. Giới hạn origin ở WebSocket endpoint

Với endpoint chỉ dùng cùng origin, có thể giữ mặc định của Spring:

```java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/chat").withSockJS();
    }
}
```

Nếu frontend được host ở một origin khác, hãy khai báo đúng các origin được phép:

```java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/chat")
            .setAllowedOrigins("https://app.example.com")
            .withSockJS();
}
```

Có thể truyền nhiều origin hoặc dùng setAllowedOriginPatterns(...) khi thật sự cần pattern. Ưu tiên danh sách origin cụ thể. Không cấu hình wildcard trong production chỉ để giải quyết lỗi handshake. Đặc biệt, CORS không cho phép dùng wildcard origin cùng credential theo cách thông thường.

Khi origin bị giới hạn, một số SockJS transport dựa trên iframe không thể kiểm tra origin sẽ bị vô hiệu hóa. Điều này ảnh hưởng đến các trình duyệt cũ và lựa chọn fallback. Hãy xác nhận các transport mà client thực tế cần dùng trước khi thay đổi allowlist.

## 3. CSRF token trên STOMP CONNECT

Spring Security tích hợp bảo vệ STOMP qua @EnableWebSocketSecurity. Mặc định, mọi frame inbound loại CONNECT phải có CSRF token hợp lệ. Việc này bổ sung lớp kiểm tra sau origin validation: chỉ một trang có thể lấy CSRF token hợp lệ mới có thể mở STOMP session.

Token được đặt trong **STOMP CONNECT headers**, không phải trong payload của frame SEND. Khi client dùng thư viện STOMP JavaScript, các header này thường được truyền qua thuộc tính connectHeaders hoặc đối số headers của hàm connect, tùy phiên bản thư viện.

### Cấu hình message authorization

Ví dụ dưới đây dùng API AuthorizationManager của Spring Security 5.8+:

```java
@Configuration
@EnableWebSocketSecurity
public class WebSocketSecurityConfig {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages
    ) {
        messages
                .nullDestMatcher().authenticated()
                .simpDestMatchers("/app/**").hasRole("USER")
                .simpSubscribeDestMatchers("/topic/public").permitAll()
                .simpSubscribeDestMatchers("/user/**").hasRole("USER")
                .simpTypeMatchers(
                        SimpMessageType.MESSAGE,
                        SimpMessageType.SUBSCRIBE
                ).denyAll()
                .anyMessage().denyAll();

        return messages.build();
    }
}
```

Các quy tắc được xét theo thứ tự:

- Message không có destination, bao gồm CONNECT, cần user đã xác thực. @EnableWebSocketSecurity đồng thời áp dụng CSRF token validation cho CONNECT.
- SEND đến /app/** cần role USER.
- Client được subscribe /topic/public theo chính sách công khai của ví dụ.
- Subscribe đến /user/** cần role USER.
- Các MESSAGE hoặc SUBSCRIBE còn lại bị từ chối.
- anyMessage().denyAll() đóng mặc định để một destination mới không vô tình được mở.

Trong ứng dụng thật, điều chỉnh danh sách destination và role theo nghiệp vụ. Đừng cho client SEND trực tiếp vào broker prefix như /topic/** hoặc /queue/** nếu client chỉ nên gửi lệnh tới application prefix. Cũng cần bảo vệ SUBSCRIBE: Spring Security chủ yếu bảo vệ clientInboundChannel, không lọc từng message trên clientOutboundChannel. Việc giới hạn ai được subscribe là lớp bảo vệ quan trọng để ngăn đọc dữ liệu của user khác.

Các import thường dùng:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;
```

## 4. Lấy CSRF token cho client

Với trang render bằng server-side template, có thể đọc CSRF token từ request attribute _csrf. Với frontend tĩnh hoặc SPA, một cách phổ biến là cung cấp endpoint HTTP trả token hiện tại.

```java
@RestController
public class CsrfController {

    @GetMapping("/csrf")
    public CsrfToken csrf(CsrfToken csrfToken) {
        return csrfToken;
    }
}
```

Endpoint này cần tuân theo chính sách xác thực và cache của ứng dụng. Không để CDN hoặc shared cache lưu token của user rồi trả cho user khác. Frontend lấy token bằng request cùng origin, sau đó gắn nó vào STOMP CONNECT headers.

Ví dụ với @stomp/stompjs và SockJS:

```javascript
import { Client } from "@stomp/stompjs";
import SockJS from "sockjs-client";

async function createStompClient() {
    const response = await fetch("/csrf", {
        credentials: "same-origin",
        cache: "no-store"
    });

    if (!response.ok) {
        throw new Error("Cannot obtain CSRF token");
    }

    const csrf = await response.json();

    const client = new Client({
        webSocketFactory: () => new SockJS("/chat"),
        connectHeaders: {
            [csrf.headerName]: csrf.token
        },
        onConnect: () => {
            client.subscribe("/topic/public", frame => {
                console.log("Message:", frame.body);
            });
        },
        onStompError: frame => {
            console.error("STOMP error:", frame.headers["message"]);
        }
    });

    client.activate();
    return client;
}
```

Trong ví dụ, webSocketFactory chọn SockJS transport. Nếu server dùng WebSocket thuần, có thể dùng brokerURL với địa chỉ wss://app.example.com/chat thay cho factory. Token được đưa vào CONNECT headers để Spring Security kiểm tra khi nhận frame CONNECT.

Khi token hết hạn, bị thay đổi sau đăng nhập/đăng xuất hoặc session được làm mới, frontend cần lấy token mới trước khi kết nối lại. Không hard-code CSRF token vào JavaScript bundle vì token phải gắn với phiên người dùng hiện tại.

## 5. SockJS và HTTP CSRF filter

SockJS có thể dùng các HTTP request để thực hiện transport fallback. Với các HTTP-based transport, quá trình kết nối có thể sử dụng POST. Những request này đi qua HTTP security filter chain trước khi Spring SockJS xử lý chúng.

Có một khác biệt quan trọng:

- @EnableWebSocketSecurity kiểm tra CSRF token ở **STOMP CONNECT frame**.
- CsrfFilter bảo vệ các **HTTP request** theo cấu hình web security.

Với SockJS, token ứng dụng không thể luôn được đặt trong HTTP header tùy ý của từng transport request theo cách giống XHR thông thường. Spring Security hướng dẫn bỏ qua HTTP CSRF filter cho riêng đường dẫn SockJS endpoint, rồi giữ nguyên kiểm tra token ở STOMP CONNECT headers.

Ví dụ nếu endpoint là /chat:

```java
@Configuration
@EnableWebSecurity
public class HttpSecurityConfig {

    @Bean
    public SecurityFilterChain filterChain(HttpSecurity http)
            throws Exception {

        http
                .authorizeHttpRequests(authorize -> authorize
                        .requestMatchers("/chat/**", "/csrf").authenticated()
                        .anyRequest().authenticated()
                )
                .csrf(csrf -> csrf
                        // SockJS HTTP transports are protected by the
                        // CSRF token on the STOMP CONNECT frame.
                        .ignoringRequestMatchers("/chat/**")
                )
                .headers(headers -> headers
                        // Required only when iframe-based SockJS
                        // transports must be supported.
                        .frameOptions(frame -> frame.sameOrigin())
                );

        return http.build();
    }
}
```

Điểm cần giữ đúng:

1. Chỉ loại trừ /chat/** khỏi HTTP CSRF filter vì đây là các URL transport của SockJS.
2. Không gọi csrf.disable() cho toàn bộ ứng dụng. Các form POST, API thay đổi dữ liệu và request HTTP khác vẫn cần CSRF protection theo chính sách ứng dụng.
3. Không bỏ @EnableWebSocketSecurity; nếu bỏ cơ chế này, ví dụ trên không còn kiểm tra CSRF token ở STOMP CONNECT theo mặc định.
4. Đường dẫn /chat/** vẫn cần authentication và origin validation. Việc bỏ qua HTTP CSRF filter không đồng nghĩa cho phép anonymous hoặc cross-origin connection.

Nếu ứng dụng chỉ dùng WebSocket thuần và không dùng SockJS HTTP fallback, không cần ngoại lệ /chat/** cho các POST transport của SockJS. CONNECT CSRF của Spring Security vẫn được áp dụng khi bật @EnableWebSocketSecurity.

## 6. X-Frame-Options và SockJS iframe transport

Một số SockJS fallback cũ dùng iframe để tạo môi trường chạy transport. Spring Security mặc định đặt chính sách chống clickjacking, có thể chặn nội dung bị nhúng trong iframe. Nếu cần hỗ trợ iframe transport cùng origin, có thể cấu hình:

```java
.headers(headers -> headers
        .frameOptions(frame -> frame.sameOrigin())
)
```

Header X-Frame-Options: SAMEORIGIN cho phép trang được frame bởi cùng origin và vẫn chặn frame từ origin khác. Chỉ bật khi transport thực tế cần iframe. Khi giới hạn allowed origins, Spring có thể vô hiệu hóa iframe-based transport vì các transport này không xác minh origin request theo cách cần thiết.

Không dùng frameOptions.disable() để làm SockJS chạy được. Tắt hoàn toàn frame protection sẽ mở rộng bề mặt clickjacking của các trang khác trong ứng dụng. Nếu ứng dụng đã dùng Content Security Policy, kiểm tra thêm directive frame-ancestors vì nó cũng quyết định trang nào được phép nhúng nội dung.

## 7. CORS cho SockJS và allowed origins

CORS và allowed origins có liên quan nhưng không đồng nhất:

| Cơ chế | Kiểm tra gì? | Phạm vi |
|---|---|---|
| WebSocket allowed origins | Header Origin của handshake | WebSocket và SockJS endpoint |
| CORS | Origin, method và headers của HTTP request | XHR streaming/polling của SockJS và HTTP API |
| CSRF | Token chứng minh request đến từ trang có quyền lấy token | HTTP request và STOMP CONNECT tùy interceptor |
| Message authorization | User được SEND/SUBSCRIBE destination nào | STOMP inbound messages |

Với SockJS XHR streaming và polling, Spring tự thêm CORS headers nếu response chưa có các CORS headers khác. Nếu ứng dụng đã cấu hình CORS qua Servlet Filter hoặc Spring MVC, tránh tạo hai bộ header CORS mâu thuẫn. Hãy kiểm tra cả preflight request, cookie credentials và danh sách header được phép.

Nếu frontend khác origin và cần gửi cookie phiên, cấu hình origin cụ thể, credential policy phù hợp và cookie SameSite/Secure đúng với môi trường. Không dùng wildcard origin với credential. CORS chỉ cho phép trình duyệt gửi/đọc một số HTTP request; nó không thay thế CSRF token hay authorization của STOMP message.

## 8. Authentication, Origin và CSRF không thay thế nhau

Với STOMP over WebSocket, Spring thường dùng Principal đã xác thực từ HTTP handshake. Nếu Spring Security đã xác thực request HTTP, user đó được gắn vào WebSocket/SockJS session và các STOMP message sau đó.

Các header login và passcode của STOMP CONNECT ban đầu được thiết kế cho STOMP over TCP. Spring mặc định không dùng chúng làm cơ chế xác thực cho STOMP over WebSocket. Hãy xác thực ở HTTP layer hoặc xây dựng cơ chế token riêng ở inbound channel khi có yêu cầu rõ ràng.

Bốn câu hỏi cần trả lời độc lập:

- **Ai đang kết nối?** HTTP authentication và Principal.
- **Trang nào được phép mở kết nối từ trình duyệt?** Origin allowlist.
- **Kết nối được mở bởi trang có quyền lấy token?** CSRF token trên STOMP CONNECT.
- **User được làm gì sau khi kết nối?** Message authorization cho SEND và SUBSCRIBE.

Một origin hợp lệ không có nghĩa user được quyền subscribe mọi destination. Một CSRF token hợp lệ cũng không có nghĩa user được phép gửi lệnh quản trị.

## 9. Kiểm tra cấu hình bảo mật

Nên kiểm tra cả đường thành công và đường bị từ chối:

1. Mở ứng dụng từ origin được phép và xác nhận WebSocket/SockJS handshake thành công.
2. Thử từ origin khác và xác nhận server từ chối handshake hoặc transport request.
3. Gửi STOMP CONNECT không có CSRF token và xác nhận Spring Security từ chối.
4. Gửi CONNECT với token hợp lệ của phiên hiện tại và xác nhận session được thiết lập.
5. Thử token thiếu, token sai và token của phiên khác; tất cả phải bị từ chối.
6. Với SockJS, xác nhận HTTP POST tới transport path không bị HTTP CSRF filter chặn trước khi STOMP CONNECT được kiểm tra.
7. Xác nhận HTTP POST ngoài /chat/** vẫn cần CSRF token.
8. Xác nhận user không đủ role không thể SEND vào /app/** hoặc SUBSCRIBE vào destination riêng.
9. Xác nhận client không thể SEND trực tiếp vào /topic/** để giả mạo message do server phát.
10. Nếu dùng iframe fallback, xác nhận same-origin frame hoạt động và frame từ origin khác bị chặn.

Trong log, phân biệt HTTP 403 ở handshake/transport với lỗi STOMP CONNECT. Hai lỗi có thể cùng hiển thị thành “không kết nối được” ở client nhưng xảy ra ở hai tầng khác nhau.

## 10. Lỗi cấu hình thường gặp

| Sai sót | Hậu quả | Cách xử lý |
|---|---|---|
| Nghĩ rằng trình duyệt tự chặn WebSocket cross-origin | Có thể mở ra CSWSH khi dùng cookie session | Kiểm tra Origin ở server và yêu cầu CSRF token |
| Chỉ bật CORS mà không kiểm tra Origin WebSocket | WebSocket handshake vẫn có thể không được bảo vệ như mong muốn | Cấu hình allowed origins tại STOMP endpoint |
| Tắt toàn bộ HTTP CSRF để SockJS POST chạy | Các form/API HTTP khác có nguy cơ CSRF | Chỉ ignore đường dẫn SockJS transport |
| Ignore /chat/** rồi bỏ luôn CSRF STOMP CONNECT | Kết nối thiếu token có thể được chấp nhận | Giữ @EnableWebSocketSecurity và CONNECT token |
| Gửi CSRF token trong payload SEND | Interceptor không thấy token ở CONNECT header | Đặt token vào STOMP CONNECT headers |
| Cho phép wildcard origins trong môi trường có cookie | Bất kỳ website nào cũng có thể thử kết nối | Dùng allowlist cụ thể |
| Mở frameOptions.disable() | Tăng nguy cơ clickjacking | Chỉ dùng SAMEORIGIN khi iframe fallback cần thiết |
| Tin Origin là danh tính client | Non-browser client có thể giả mạo header | Authentication và authorization độc lập |

## Tài liệu tham khảo

- [Spring Security 6.5 — WebSocket Security](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/websocket.html)
- [Spring Framework 6.2 — WebSocket Allowed Origins](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/server.html)
- [Spring Framework 6.2 — SockJS Fallback and CORS](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/fallback.html)
- [Spring Framework 6.2 — STOMP Authentication](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/authentication.html)
- [Spring Security — CSRF Protection](https://docs.spring.io/spring-security/reference/servlet/exploits/csrf.html)
