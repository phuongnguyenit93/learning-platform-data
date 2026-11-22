# Danh tính người dùng từ HTTP handshake tới STOMP session trong Spring

## Mục tiêu

Một kết nối STOMP over WebSocket bắt đầu bằng một yêu cầu HTTP. Spring có thể lấy danh tính đã xác thực từ yêu cầu HTTP đó, gắn danh tính vào WebSocket session, rồi đưa danh tính ấy vào các message STOMP tiếp theo. Vì vậy, controller có thể nhận tham số Principal mà không cần client tự gửi username trong payload.

Có hai mô hình xác thực thường gặp:

- **Xác thực ở HTTP handshake**: phù hợp khi ứng dụng đã dùng Spring Security và cookie/session hoặc cơ chế HTTP authentication.
- **Xác thực ở STOMP CONNECT**: phù hợp khi client gửi bearer token trong STOMP CONNECT headers, ví dụ ứng dụng SPA hoặc mobile không dùng HTTP session.

Hai mô hình đều phải tạo ra một Principal đáng tin cậy ở phía server. Khác biệt nằm ở thời điểm và tầng xác thực. Không được xem một trường username do client tự khai báo là danh tính đã xác thực.

## 1. Vòng đời từ HTTP handshake tới STOMP message

Với WebSocket tiêu chuẩn, client trước tiên gửi HTTP request có header Upgrade. Nếu server chấp nhận, kết nối chuyển sang giao thức WebSocket. STOMP sau đó chạy như một sub-protocol trên kết nối này.

Với SockJS fallback, Spring có thể dùng một chuỗi HTTP transport requests thay cho WebSocket thuần, nhưng mô hình danh tính vẫn được gắn với phiên SockJS/WebSocket.

Luồng tổng quát:

~~~text
Browser / Mobile client
        |
        | HTTP request: GET /ws
        | Cookie / HTTP authentication
        v
Spring Security filter chain
        |
        | xác thực request, tạo SecurityContext
        v
WebSocket handshake / SockJS transport
        |
        | HttpServletRequest.getUserPrincipal()
        v
WebSocket session gắn với Principal
        |
        | STOMP CONNECT
        | STOMP SEND / SUBSCRIBE / DISCONNECT
        v
Spring clientInboundChannel
        |
        | message có simpUser / Principal
        v
@MessageMapping, ChannelInterceptor, AuthorizationManager
~~~

Với mô hình HTTP session, Spring tự động chuyển Principal của HTTP request sang WebSocket session. Các STOMP message sau đó mang thông tin user tương ứng. Ứng dụng thông thường không cần tự sao chép username từ HTTP sang payload STOMP.

Với mô hình token ở STOMP CONNECT, HTTP handshake có thể chưa có người dùng đã xác thực. Một ChannelInterceptor xác thực token trên frame CONNECT và gọi setUser(...) để Spring ghi nhớ user cho các message tiếp theo trên cùng session.

## 2. Mô hình mặc định: xác thực HTTP trước handshake

Đây là lựa chọn tự nhiên khi ứng dụng đã dùng Spring Security để bảo vệ HTTP:

1. Người dùng đăng nhập bằng form login, HTTP Basic, OAuth2 Login hoặc cơ chế HTTP authentication khác.
2. Spring Security xác thực request và lưu Authentication trong SecurityContext. Với cookie-based session, SecurityContext được gắn với HTTP session.
3. Browser gửi yêu cầu mở WebSocket tới endpoint, ví dụ /ws, kèm cookie session phù hợp.
4. Spring đọc Principal từ HTTP request trong quá trình handshake.
5. WebSocket session được tạo cùng danh tính đó.
6. Mỗi STOMP message từ session được gắn thông tin user tương ứng.

Ví dụ cấu hình endpoint:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Nếu HTTP request tới /ws đã được Spring Security xác thực, Spring WebSocket có thể dùng Principal của request đó. Không cần thêm username vào frame CONNECT để lặp lại danh tính đã được xác thực.

### Vì sao không dùng CONNECT login/passcode mặc định?

STOMP định nghĩa header login và passcode trên frame CONNECT, vốn hữu ích với STOMP qua TCP. Tuy nhiên, với STOMP over WebSocket trong Spring, mặc định Spring không dùng các header này để xác thực user. Spring giả định danh tính đã được xác thực ở tầng HTTP và được gắn với WebSocket/SockJS session.

Điều này giúp tránh việc hai cơ chế xác thực độc lập cùng tồn tại mà không có quy tắc thống nhất. Nếu muốn dùng token hoặc thông tin xác thực ở STOMP CONNECT, ứng dụng phải tự xác thực bằng ChannelInterceptor và đặt Principal vào message.

## 3. Đọc Principal trong controller và message

Một phương thức @MessageMapping có thể nhận Principal trực tiếp:

~~~java
public record ChatCommand(String text) {}

public record ChatMessage(String sender, String text) {}

@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage send(
            @Payload ChatCommand command,
            Principal principal) {

        return new ChatMessage(principal.getName(), command.text());
    }
}
~~~

Đây là đoạn controller minh họa. Ứng dụng cần khai báo DTO, cấu hình message converter và bảo đảm endpoint yêu cầu xác thực trước khi phương thức được gọi.

Với application destination prefix /app, client gửi SEND tới /app/chat.send; Spring định tuyến tới @MessageMapping("/chat.send"). Principal phản ánh danh tính đã gắn với session. Server tự tạo trường sender từ Principal, không dùng giá trị sender do client gửi.

Có thể đọc danh tính trong interceptor bằng StompHeaderAccessor hoặc SimpMessageHeaderAccessor:

~~~java
public class UserAuditInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(Message<?> message, MessageChannel channel) {
        StompHeaderAccessor accessor = StompHeaderAccessor.wrap(message);
        Principal user = accessor.getUser();

        if (user != null) {
            String username = user.getName();
            // Ghi audit event theo chính sách của ứng dụng.
        }

        return message;
    }
}
~~~

Trong message headers của Spring Messaging, user thường xuất hiện dưới header simpUser. Dùng accessor.getUser() hoặc tham số Principal giúp tránh phụ thuộc vào tên header nội bộ.

Không ghi access token, cookie session hoặc thông tin bí mật vào audit log. Nếu cần ghi lại người gửi, chỉ ghi subject/user ID đã được xác thực cùng metadata cần thiết.

## 4. Tùy chỉnh danh tính ngay tại HTTP handshake

Trong một số ứng dụng, HTTP request đã được xác thực bằng cơ chế riêng hoặc cần gắn một Principal đặc biệt vào WebSocket session. Spring cho phép tùy chỉnh HandshakeHandler, ví dụ override determineUser(...).

~~~java
public class CustomHandshakeHandler extends DefaultHandshakeHandler {

    @Override
    protected Principal determineUser(
            ServerHttpRequest request,
            WebSocketHandler wsHandler,
            Map<String, Object> attributes) {

        return request.getPrincipal();
    }
}
~~~

Đoạn này minh họa điểm mở rộng và trả lại Principal do tầng HTTP cung cấp. Trong ứng dụng thực tế, chỉ tạo Principal mới sau khi xác minh danh tính từ nguồn tin cậy. Nếu Spring Security authorization dựa vào Authentication, Principal tùy chỉnh cũng phải là một Authentication phù hợp; một đối tượng chỉ triển khai Principal có thể không cung cấp authorities cho SecurityContext.

Có thể gắn HandshakeHandler vào endpoint:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws")
            .setHandshakeHandler(new CustomHandshakeHandler());
}
~~~

Nếu Spring Security đã tạo Authentication và request Principal chính xác, không cần tùy chỉnh HandshakeHandler. Chỉ thêm custom handler khi có yêu cầu thật sự về cách xác định Principal tại thời điểm handshake.

Cần phân biệt HandshakeInterceptor với HandshakeHandler:

- HandshakeInterceptor chạy trước và sau handshake, thường dùng để kiểm tra request hoặc chuyển metadata vào attributes của WebSocket session.
- HandshakeHandler quyết định handshake và có điểm mở rộng determineUser(...) để xác định Principal của WebSocket session.
- Metadata trong attributes không tự động trở thành Authentication. Một giá trị trong attributes chỉ đáng tin khi server đã xác minh nó.

## 5. Khi nào nên xác thực ở STOMP CONNECT?

Một số client không sử dụng cookie-based HTTP session:

- Ứng dụng SPA dùng access token JWT.
- Ứng dụng mobile gửi bearer token.
- Dịch vụ nội bộ dùng client credentials.
- Ứng dụng stateless không duy trì HTTP session phía server.

WebSocket API trong browser không cho JavaScript tự đặt tùy ý HTTP headers cho quá trình khởi tạo WebSocket. SockJS JavaScript client cũng không cung cấp custom HTTP headers cho transport requests. Vì vậy, nếu không dùng cookie, cách thường dùng là gửi token trong STOMP CONNECT headers rồi xác thực ở server bằng ChannelInterceptor.

Ví dụ phía client với thư viện STOMP:

~~~javascript
const client = new Client({
    brokerURL: "wss://example.com/ws",
    connectHeaders: {
        Authorization: "Bearer " + accessToken
    },
    onConnect: () => {
        client.subscribe("/user/queue/private", frame => {
            console.log(frame.body);
        });
    }
});

client.activate();
~~~

Trong ví dụ, connectHeaders là header của frame STOMP CONNECT. Nó không phải HTTP Authorization header của WebSocket handshake. Với browser, đây là khác biệt quan trọng: JavaScript không thể tự thêm header tùy ý vào HTTP Upgrade request, nhưng STOMP client có thể thêm header ứng dụng vào frame CONNECT sau khi WebSocket được mở.

Không nên đưa bearer token vào query string nếu có lựa chọn khác. URL có thể bị ghi vào access log, reverse proxy log, monitoring, analytics hoặc lịch sử trình duyệt. Nếu buộc phải dùng query parameter cho một môi trường giới hạn, token phải có thời hạn rất ngắn, phạm vi hẹp và không được ghi log; ưu tiên thiết kế khác an toàn hơn.

## 6. Xác thực token bằng ChannelInterceptor

Spring cho phép đăng ký ChannelInterceptor trên clientInboundChannel. Interceptor kiểm tra frame CONNECT, xác thực token và gắn Authentication vào message bằng accessor.setUser(...). Spring lưu user đó và liên kết với các STOMP message tiếp theo trong cùng session.

Ví dụ với JwtDecoder và JwtAuthenticationConverter của Spring Security:

~~~java
@Configuration
@Order(Ordered.HIGHEST_PRECEDENCE + 99)
public class StompTokenAuthenticationConfig
        implements WebSocketMessageBrokerConfigurer {

    private final JwtDecoder jwtDecoder;
    private final JwtAuthenticationConverter jwtAuthenticationConverter;

    public StompTokenAuthenticationConfig(
            JwtDecoder jwtDecoder,
            JwtAuthenticationConverter jwtAuthenticationConverter) {
        this.jwtDecoder = jwtDecoder;
        this.jwtAuthenticationConverter = jwtAuthenticationConverter;
    }

    @Override
    public void configureClientInboundChannel(ChannelRegistration registration) {
        registration.interceptors(new ChannelInterceptor() {

            @Override
            public Message<?> preSend(Message<?> message, MessageChannel channel) {
                StompHeaderAccessor accessor =
                        MessageHeaderAccessor.getAccessor(
                                message, StompHeaderAccessor.class);

                if (accessor != null
                        && StompCommand.CONNECT.equals(accessor.getCommand())) {

                    String authorization =
                            accessor.getFirstNativeHeader("Authorization");

                    if (authorization == null
                            || !authorization.startsWith("Bearer ")) {
                        throw new BadCredentialsException("Missing bearer token");
                    }

                    String token = authorization.substring(7);
                    Jwt jwt = jwtDecoder.decode(token);
                    Authentication authentication =
                            jwtAuthenticationConverter.convert(jwt);

                    if (authentication == null) {
                        throw new BadCredentialsException("Invalid bearer token");
                    }

                    accessor.setUser(authentication);
                }

                return message;
            }
        });
    }
}
~~~

Đây là trích đoạn cấu hình minh họa; imports và bean JwtDecoder/JwtAuthenticationConverter được lược bỏ. Ứng dụng cần dependency Spring Security OAuth2 Resource Server/Jose tương ứng và cấu hình decoder với issuer hoặc public key đáng tin cậy. Cấu hình validator phải kiểm tra các claim cần thiết như issuer, audience và thời hạn. Converter có thể ánh xạ scope/role thành authorities mà Spring Security authorization sử dụng.

Những việc quan trọng trong interceptor:

1. Chỉ xác thực frame CONNECT để thiết lập danh tính cho session.
2. Lấy token từ native STOMP header do client gửi.
3. Kiểm tra chữ ký, issuer, audience, thời hạn và các claim cần thiết thông qua decoder/validator.
4. Tạo Authentication từ kết quả xác thực, bao gồm authorities nếu ứng dụng cần phân quyền.
5. Gọi accessor.setUser(authentication) để gắn Principal đáng tin cậy vào CONNECT message.
6. Từ chối CONNECT bằng exception nếu token thiếu, sai định dạng, hết hạn hoặc không hợp lệ.

Ví dụ dùng JwtAuthenticationConverter là một cách triển khai. Có thể dùng Authentication khác hoặc cơ chế xác thực riêng, miễn là đối tượng được gắn qua setUser(...) là kết quả xác thực phía server và mang authorities cần thiết.

### Thứ tự interceptor

Khi dùng Spring Security để authorization các STOMP message, interceptor xác thực token phải chạy trước interceptor bảo mật của Spring Security để SecurityContext có thể đọc được user đã xác thực.

Tài liệu Spring khuyến nghị khai báo custom WebSocketMessageBrokerConfigurer riêng và đặt @Order(Ordered.HIGHEST_PRECEDENCE + 99). Không nên chỉ thêm interceptor một cách tùy tiện vào cấu hình khác rồi giả định thứ tự thực thi.

Nếu token authentication không được chạy trước, Spring Security có thể đánh giá CONNECT hoặc các message tiếp theo như user anonymous, dẫn tới từ chối truy cập dù token hợp lệ.

## 7. Kết hợp Spring Security: CSRF và authorization

Xác thực và phân quyền là hai việc khác nhau:

- **Authentication** trả lời user là ai.
- **Authorization** quyết định user được phép gửi hoặc nhận message nào.

Có thể bật bảo vệ STOMP bằng @EnableWebSocketSecurity và khai báo AuthorizationManager<Message<?>>. Ví dụ dưới đây minh họa cách phân quyền inbound message:

~~~java
@Configuration
@EnableWebSocketSecurity
public class WebSocketSecurityConfig {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        messages
            .nullDestMatcher().authenticated()
            .simpDestMatchers("/app/**").hasRole("USER")
            .simpSubscribeDestMatchers("/user/**", "/topic/public")
                .hasRole("USER")
            .simpTypeMatchers(SimpMessageType.MESSAGE).denyAll()
            .simpTypeMatchers(SimpMessageType.SUBSCRIBE).denyAll()
            .anyMessage().denyAll();

        return messages.build();
    }
}
~~~

Đây là ví dụ chính sách cơ bản, cần điều chỉnh theo destination và role thật của ứng dụng. Cần xem xét cả SEND, SUBSCRIBE, CONNECT, DISCONNECT và các message nội bộ; không sao chép nguyên xi nếu ứng dụng có yêu cầu khác.

### CSRF trên STOMP CONNECT

Khi bật Spring Security WebSocket support, mặc định inbound CONNECT yêu cầu CSRF token. Cơ chế này giúp chống kết nối WebSocket trái phép từ origin khác bằng cách yêu cầu client có token CSRF hợp lệ.

Với SockJS, do transport không cho gửi tùy ý HTTP headers, CSRF token thường được gửi trong STOMP CONNECT headers. Client phải lấy token từ cơ chế CSRF của ứng dụng, sau đó thêm header tương ứng vào connectHeaders.

~~~javascript
const connectHeaders = {
    Authorization: "Bearer " + accessToken,
    [csrfHeaderName]: csrfToken
};

const client = new Client({
    brokerURL: "wss://example.com/ws",
    connectHeaders
});
~~~

Tên header và token phải khớp giá trị Spring Security cấp cho request hiện tại. Nếu ứng dụng dùng HTTP session, cookie vẫn cần được gửi theo chính sách trình duyệt và cùng origin phù hợp.

Không tắt CSRF toàn cục chỉ để làm cho STOMP CONNECT chạy được. Nếu cần cấu hình ngoại lệ ở HTTP filter chain cho endpoint handshake, hãy giới hạn chính xác URL cần thiết và vẫn giữ CSRF protection ở tầng STOMP CONNECT theo cấu hình bảo mật đã chọn.

### Phân quyền SEND và SUBSCRIBE riêng biệt

Ví dụ, client có thể được phép SUBSCRIBE /topic/system/notifications nhưng không được phép SEND tới destination đó. Nếu cho client gửi message trực tiếp vào destination phát thông báo hệ thống, client có thể giả mạo thông báo.

Một chính sách thường dùng:

- Cho user đã xác thực SEND tới /app/**.
- Cho user có quyền SUBSCRIBE tới /user/** và các topic công khai cụ thể.
- Từ chối MESSAGE từ client tới /topic/** và /queue/** trừ khi có yêu cầu publish trực tiếp.
- Không cho client SUBSCRIBE vào queue vật lý nội bộ đã được Spring phân giải cho user khác.
- Kiểm tra quyền nghiệp vụ trong controller/service, kể cả khi message đã qua authorization matcher.

## 8. Principal, username và dữ liệu do client gửi

Một lỗi phổ biến là nhận username từ payload:

~~~java
public record ChatCommand(String from, String text) {}
~~~

Sau đó dùng trực tiếp trường from để xác định người gửi. Cách này cho phép client giả mạo user khác.

Thay vào đó:

~~~java
@MessageMapping("/chat.send")
public void send(@Payload ChatCommand command, Principal principal) {
    String authenticatedUsername = principal.getName();

    chatService.send(authenticatedUsername, command.text());
}
~~~

Client chỉ gửi nội dung nghiệp vụ. Server tự xác định người gửi từ Principal. Nếu cần gửi tới một người nhận cụ thể, client có thể gửi recipient ID, nhưng service phải kiểm tra user hiện tại có quyền gửi tới recipient đó.

Cũng không nên tin native STOMP header tên user do client tự gửi. Client có thể tùy ý tạo header trong frame CONNECT hoặc SEND. Danh tính phải đến từ HTTP SecurityContext hoặc từ quá trình xác thực token phía server, rồi được gắn qua setUser(...).

## 9. Vòng đời session, token hết hạn và reconnect

Danh tính gắn với WebSocket/STOMP session có vòng đời riêng:

- HTTP handshake tạo WebSocket session và gắn Principal.
- STOMP CONNECT khởi tạo phiên messaging.
- SEND và SUBSCRIBE sử dụng danh tính gắn với phiên.
- DISCONNECT hoặc đóng transport kết thúc phiên.
- Reconnect tạo một WebSocket/SockJS session mới và phải xác thực lại theo chính sách.

Với JWT được xác thực ở CONNECT, Spring không tự động gọi lại JwtDecoder cho từng SEND hoặc SUBSCRIBE. Token thường được kiểm tra lúc kết nối. Vì WebSocket là kết nối dài, cần quyết định cách xử lý token hết hạn hoặc bị thu hồi trong khi socket vẫn mở.

Các chiến lược có thể cân nhắc:

1. Giới hạn tuổi tối đa của WebSocket session theo thời hạn token.
2. Chủ động đóng session khi token hết hạn hoặc user bị thu hồi quyền.
3. Yêu cầu client reconnect và xác thực bằng access token mới.
4. Kiểm tra quyền nghiệp vụ ở từng message đối với thao tác nhạy cảm.
5. Dùng session registry hoặc cơ chế thu hồi tập trung nếu hệ thống cần vô hiệu hóa kết nối ngay lập tức.

Không giả định refresh token tự động cập nhật Principal của một STOMP session đang tồn tại. Nếu token mới được cấp, ứng dụng cần có quy trình reconnect hoặc cơ chế cập nhật danh tính được thiết kế và kiểm soát rõ.

Khi nhận SessionDisconnectEvent, xử lý dọn dẹp nên idempotent vì một session có thể tạo nhiều tín hiệu disconnect trong một số tình huống đóng kết nối. Không để việc xử lý disconnect lặp gây xóa dữ liệu hoặc giải phóng tài nguyên nhiều lần.

## 10. Nhiều tab, nhiều thiết bị và định danh session

Một user có thể mở nhiều tab hoặc kết nối từ nhiều thiết bị. Các session có thể cùng mang một Principal nhưng vẫn có session ID riêng.

Điều này ảnh hưởng đến:

- Gửi message tới mọi session của một user.
- Gửi message chỉ tới session tạo request.
- Theo dõi trạng thái online.
- Dọn dẹp session sau disconnect.
- Phát thông báo khi một thiết bị đăng xuất.
- Quản lý giới hạn số kết nối đồng thời.

Không nên dùng username làm session ID. Username nhận diện user; session ID nhận diện một kết nối cụ thể. Nếu cần gửi riêng cho một tab, hãy dùng cơ chế destination/session của Spring hoặc một correlation ID ở tầng nghiệp vụ; đừng tự tạo queue vật lý bằng cách nối username với chuỗi tùy ý.

Khi chạy nhiều instance, mỗi node có thể quản lý các session WebSocket khác nhau. User registry và broker relay cần được cấu hình phù hợp nếu muốn định tuyến user destination xuyên node. Việc một node biết Principal không có nghĩa node khác tự động biết mọi session của user đó.

## 11. Kiểm thử danh tính từ handshake tới controller

Nên kiểm thử từng ranh giới thay vì chỉ kiểm tra rằng WebSocket mở thành công:

1. **HTTP authentication**: request handshake chưa xác thực phải bị từ chối nếu endpoint yêu cầu login.
2. **Principal propagation**: handshake đã xác thực tạo session với Principal đúng.
3. **STOMP CONNECT**: session được phép CONNECT và có user header phù hợp.
4. **Token authentication**: token thiếu, sai chữ ký, sai issuer/audience hoặc hết hạn phải bị từ chối.
5. **Interceptor order**: Spring Security nhìn thấy Authentication đã được gắn trước khi authorization chạy.
6. **Controller identity**: tham số Principal trong @MessageMapping khớp user đăng nhập.
7. **Spoofing**: payload hoặc native header do client tự đặt không thể thay đổi danh tính đã xác thực.
8. **CSRF/Origin**: CONNECT thiếu CSRF token hoặc request từ origin không được phép phải được xử lý theo chính sách.
9. **Reconnect**: session mới phải xác thực lại; token hết hạn không được vô tình giữ quyền lâu hơn chính sách.
10. **Disconnect**: cleanup an toàn khi disconnect event đến nhiều lần.

Có thể dùng WebSocketStompClient với WebSocketClient hoặc SockJsClient tùy transport. Với kiểm thử tích hợp, hãy chạy cả HTTP handshake, STOMP CONNECT, SEND và SUBSCRIBE qua cùng cấu hình security thực tế để phát hiện lỗi về session, CSRF và thứ tự interceptor.

## 12. Lỗi thường gặp và cách khắc phục

**Principal trong @MessageMapping là null**

- Kiểm tra HTTP handshake request đã được xác thực chưa.
- Kiểm tra cookie/session được gửi tới đúng host, scheme và path.
- Nếu dùng token ở STOMP CONNECT, kiểm tra ChannelInterceptor có chạy trên CONNECT và gọi accessor.setUser(...) không.
- Kiểm tra interceptor có bị đăng ký sai channel hoặc sai thứ tự không.

**Header Authorization có trong CONNECT nhưng Spring vẫn xem user là anonymous**

- Spring mặc định không xác thực STOMP login/passcode cho WebSocket.
- Cần tự xác thực bearer token bằng ChannelInterceptor.
- Gắn Authentication qua setUser(...) trước khi Spring Security authorization chạy.
- Đảm bảo interceptor được đăng ký với thứ tự phù hợp.

**Token hợp lệ nhưng CONNECT bị Spring Security từ chối**

- Kiểm tra CSRF token trong STOMP CONNECT headers khi @EnableWebSocketSecurity đang bật.
- Kiểm tra interceptor token authentication chạy trước Spring Security.
- Kiểm tra authorization matcher có cho phép CONNECT và destination cần dùng hay không.

**Client có thể giả mạo người gửi**

- Không dùng trường from, username hoặc userId trong payload làm Principal.
- Không tin native STOMP header do client tự đặt.
- Lấy danh tính từ request Principal hoặc Authentication đã được server xác thực.

**Browser không gửi được custom Authorization HTTP header**

- WebSocket browser API không cho đặt tùy ý HTTP handshake headers.
- Dùng cookie/session nếu phù hợp hoặc gửi bearer token trong STOMP CONNECT headers rồi xác thực bằng ChannelInterceptor.
- Tránh token trong query string vì URL có thể bị log.

**Một kết nối vẫn hoạt động sau khi token hết hạn**

- CONNECT authentication không tự động kiểm tra token ở mọi frame.
- Thiết kế thời hạn session, đóng kết nối khi hết hạn hoặc yêu cầu reconnect.
- Kiểm tra quyền nghiệp vụ cho thao tác nhạy cảm và có cơ chế thu hồi session khi cần.

**Disconnect event làm cleanup chạy nhiều lần**

- Thiết kế handler idempotent.
- Dùng session ID và trạng thái đã đóng để bảo đảm một session chỉ được dọn dẹp một lần về mặt nghiệp vụ.

## 13. Chọn mô hình xác thực

| Bối cảnh | Mô hình nên ưu tiên |
|---|---|
| Ứng dụng web đã dùng Spring Security và cookie session | Xác thực HTTP handshake, dùng Principal được Spring chuyển sang WebSocket |
| Ứng dụng SPA/mobile dùng JWT, không có HTTP session | Token trong STOMP CONNECT + ChannelInterceptor |
| Java STOMP client có thể gửi custom HTTP headers | Có thể xác thực ở HTTP handshake bằng HTTP header hoặc dùng CONNECT token |
| Cần Principal tùy chỉnh ngay khi tạo WebSocket session | Custom HandshakeHandler / determineUser sau khi xác minh danh tính |
| Cần phân quyền SEND/SUBSCRIBE | Spring Security WebSocket authorization trên inbound messages |
| Dùng @EnableWebSocketSecurity | Bảo đảm CSRF token được gửi trong CONNECT theo cấu hình mặc định |
| Cần thu hồi user hoặc token khi socket còn mở | Session registry, timeout, đóng session hoặc kiểm tra quyền theo message |

Có thể nhớ luồng trách nhiệm như sau: HTTP Security hoặc CONNECT interceptor xác thực user; Spring gắn Principal vào session; controller và message interceptor đọc Principal; Spring Security authorization quyết định hành động được phép. Mỗi bước có trách nhiệm riêng và phải được cấu hình theo cùng một danh tính đáng tin cậy.

## Tài liệu tham khảo

- Spring Framework — Authentication: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html
- Spring Framework — Token Authentication: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html
- Spring Framework — Interception: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/interceptors.html
- Spring Framework — Authorization: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html
- Spring Security — WebSocket Security: https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html
- Spring Framework — WebSocket API and handshake: https://docs.spring.io/spring-framework/reference/web/websocket/server.html
