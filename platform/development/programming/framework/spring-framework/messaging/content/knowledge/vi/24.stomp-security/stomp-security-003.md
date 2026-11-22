# Xác thực token qua ChannelInterceptor khi phù hợp

## Mục tiêu

Với STOMP over WebSocket, Spring cần biết người dùng nào đang sở hữu một messaging session trước khi áp dụng quy tắc phân quyền cho message và subscription. Trong ứng dụng dùng cookie hoặc HTTP session, Spring thường lấy danh tính từ quá trình xác thực HTTP handshake. Với ứng dụng stateless, mobile client hoặc browser không thể gửi custom HTTP header trong WebSocket handshake, có thể cần gửi access token trong STOMP CONNECT frame rồi xác thực bằng `ChannelInterceptor`.

Bài này trình bày:

- Khi nào nên dùng xác thực ở HTTP handshake và khi nào nên xác thực token ở STOMP CONNECT.
- Cách đọc Bearer token từ native STOMP header và xác minh JWT.
- Cách gắn `Authentication` vào `Principal` của session bằng `StompHeaderAccessor.setUser`.
- Thứ tự interceptor khi kết hợp Spring Security.
- Cách tách authentication khỏi authorization, bảo vệ CONNECT bằng CSRF và giới hạn destination.
- Các lỗi phổ biến, kiểm thử và lưu ý bảo mật khi token được dùng cho kết nối dài hạn.

## 1. Authentication của WebSocket diễn ra ở đâu?

WebSocket bắt đầu bằng một HTTP request để upgrade kết nối. Spring Security có thể xác thực request đó giống các HTTP request khác. Spring Framework chuyển `Principal` của HTTP request sang WebSocket/SockJS session và gắn danh tính đó vào các STOMP message tiếp theo.

Vì vậy, nếu ứng dụng đã dùng cookie session, HTTP Basic hoặc Bearer token ở HTTP handshake theo cách client hỗ trợ, thường không cần xác thực lại token trong STOMP CONNECT. Hãy để HTTP security xác thực người dùng rồi sử dụng `Principal` có sẵn.

Tuy nhiên, browser WebSocket API không cho phép JavaScript tùy ý thêm header vào HTTP handshake. Thư viện SockJS phía browser cũng không hỗ trợ gửi custom HTTP headers cho các transport request. Java STOMP client của Spring có thể gửi headers cho cả WebSocket và SockJS request, nhưng browser client có giới hạn khác.

Trong trường hợp browser hoặc ứng dụng stateless cần dùng Bearer token mà không thể đặt token trên HTTP handshake, có thể truyền token trong **STOMP CONNECT frame**. Phía server đọc header đó bằng `ChannelInterceptor` trên inbound channel, xác thực token và gắn `Authentication` vào session.

| Phương án | Token/danh tính được lấy từ đâu? | Khi phù hợp |
| --- | --- | --- |
| HTTP handshake authentication | Cookie, HTTP Authorization hoặc Principal đã xác thực | Ứng dụng đã có HTTP session hoặc client gửi được HTTP auth header |
| STOMP CONNECT token | Native header trong CONNECT frame | Browser client cần gửi bearer token mà không thể tùy chỉnh HTTP handshake header |
| Broker STOMP login/passcode | Credentials ở tầng STOMP TCP | Client kết nối trực tiếp broker hoặc kiến trúc broker yêu cầu; không phải mặc định cho browser WebSocket qua Spring |

Không nên gửi token qua query string chỉ để vượt qua giới hạn header. URL có thể xuất hiện trong access log, proxy log, tracing hoặc lịch sử công cụ giám sát.

## 2. Luồng xác thực token qua STOMP CONNECT

Với token authentication, luồng thường gồm:

1. Client mở WebSocket tới endpoint Spring.
2. Client gửi STOMP CONNECT với native header `Authorization: Bearer <access-token>`.
3. `ChannelInterceptor` nhận message trên `clientInboundChannel`.
4. Interceptor chỉ xử lý xác thực khi STOMP command là CONNECT.
5. Interceptor đọc Bearer token, xác minh token qua `JwtDecoder` hoặc cơ chế xác thực tương ứng.
6. Khi hợp lệ, chuyển JWT thành `Authentication` và gọi `accessor.setUser(authentication)`.
7. Spring ghi nhận Principal cho STOMP session và gắn user đó với các message tiếp theo trong cùng session.
8. Spring Security có thể sử dụng user đã xác thực để phân quyền MESSAGE, SUBSCRIBE và các command inbound khác.

Điểm cốt lõi là xác thực CONNECT một lần rồi gắn danh tính vào session. Không lấy username, role hoặc user ID từ header tùy ý do client tự khai báo. Danh tính phải được suy ra từ token đã xác minh hoặc từ hệ thống xác thực đáng tin cậy.

## 3. Client gửi Bearer token trong CONNECT frame

Ví dụ dùng thư viện JavaScript `@stomp/stompjs`:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
    brokerURL: "wss://api.example.com/ws",
    connectHeaders: {
        Authorization: "Bearer " + accessToken
    },
    onConnect: () => {
        client.subscribe("/user/queue/notifications", frame => {
            const notification = JSON.parse(frame.body);
            handleNotification(notification);
        });
    },
    onStompError: frame => {
        console.error("STOMP error:", frame.headers["message"]);
    }
});

client.activate();
~~~

`connectHeaders` là các header của STOMP CONNECT frame. Chúng không phải HTTP header của WebSocket handshake. Server cần có interceptor để đọc và xác thực chúng; Spring mặc định không tự xác thực Bearer token trong native STOMP header.

Nếu dùng Spring Security với `@EnableWebSocketSecurity`, CONNECT còn cần CSRF token theo cấu hình mặc định. Khi đó, client gửi cả Bearer token và CSRF token trong STOMP CONNECT headers:

~~~javascript
const connectHeaders = {
    Authorization: "Bearer " + accessToken
};

connectHeaders[csrfHeaderName] = csrfToken;

const client = new Client({
    brokerURL: "wss://api.example.com/ws",
    connectHeaders,
    onConnect: () => {
        client.subscribe("/user/queue/notifications", onNotification);
    }
});
~~~

`csrfHeaderName` và `csrfToken` được lấy từ CSRF token mà server cung cấp. CSRF token có mục đích khác với access token: nó bảo vệ CONNECT theo Same Origin Policy, còn Bearer token xác định danh tính. Không thay thế token này bằng token kia.

Với SockJS, có thể tạo client bằng `webSocketFactory` và vẫn truyền STOMP headers qua `connectHeaders`. Nếu cấu hình HTTP CSRF cho SockJS fallback, chỉ điều chỉnh chính sách cho endpoint SockJS cần thiết theo hướng dẫn Spring Security; không tắt CSRF cho toàn bộ ứng dụng.

## 4. Xác thực JWT bằng ChannelInterceptor

Spring Framework cho phép đăng ký interceptor trên inbound channel bằng `configureClientInboundChannel`. `StompHeaderAccessor` cung cấp STOMP command và native headers. Khi command là CONNECT, đọc header Authorization, xác minh JWT, chuyển đổi thành Authentication và gọi `setUser`.

Ví dụ dưới đây dùng `JwtDecoder` và `JwtAuthenticationConverter` của Spring Security Resource Server:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpHeaders;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.simp.config.ChannelRegistration;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageHeaderAccessor;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@Order(Ordered.HIGHEST_PRECEDENCE + 99)
public class StompTokenAuthenticationConfig
        implements WebSocketMessageBrokerConfigurer {

    private final JwtDecoder jwtDecoder;
    private final JwtAuthenticationConverter authenticationConverter;

    public StompTokenAuthenticationConfig(
            JwtDecoder jwtDecoder,
            JwtAuthenticationConverter authenticationConverter) {
        this.jwtDecoder = jwtDecoder;
        this.authenticationConverter = authenticationConverter;
    }

    @Override
    public void configureClientInboundChannel(
            ChannelRegistration registration) {

        registration.interceptors(new ChannelInterceptor() {
            @Override
            public Message<?> preSend(
                    Message<?> message,
                    MessageChannel channel) {

                StompHeaderAccessor accessor =
                        MessageHeaderAccessor.getAccessor(
                                message, StompHeaderAccessor.class);

                if (accessor == null) {
                    throw new BadCredentialsException(
                            "Missing STOMP message headers");
                }

                if (StompCommand.CONNECT.equals(accessor.getCommand())) {
                    String authorization =
                            accessor.getFirstNativeHeader(
                                    HttpHeaders.AUTHORIZATION);

                    if (authorization == null) {
                        throw new BadCredentialsException(
                                "Missing Bearer token");
                    }

                    String[] parts = authorization.trim().split("\\s+", 2);
                    if (parts.length != 2
                            || !"Bearer".equalsIgnoreCase(parts[0])
                            || parts[1].isBlank()) {
                        throw new BadCredentialsException(
                                "Invalid Authorization header");
                    }

                    try {
                        Jwt jwt = jwtDecoder.decode(parts[1]);
                        Authentication authentication =
                                authenticationConverter.convert(jwt);

                        if (authentication == null) {
                            throw new BadCredentialsException(
                                    "Could not create Authentication");
                        }

                        accessor.setUser(authentication);

                        // Không để Bearer token tiếp tục đi qua các handler
                        // như một native header không cần thiết.
                        accessor.removeNativeHeader(
                                HttpHeaders.AUTHORIZATION);
                    }
                    catch (JwtException exception) {
                        throw new BadCredentialsException(
                                "Invalid or expired Bearer token",
                                exception);
                    }
                }

                return message;
            }
        });
    }
}
~~~

Đây là cấu hình minh họa cho JWT. Dự án cần có các dependency Spring Security Resource Server và JOSE tương ứng. Nếu dùng Spring Boot, có thể cấu hình issuer và audience để Spring Boot tạo decoder:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/issuer
          audiences: https://api.example.com
~~~

`issuer-uri` cho phép Spring khám phá public key/JWK endpoint và xác minh issuer. Resource Server xác minh chữ ký và các claim thời gian như `exp`, `nbf`; audience cần được cấu hình phù hợp để token được cấp cho đúng resource server. Nếu hệ thống có quy tắc claim riêng, hãy bổ sung validator thay vì tự giải mã JWT rồi tin payload.

`JwtAuthenticationConverter` chuyển JWT đã được xác minh thành `Authentication` cùng authorities. Mặc định, Spring Security có thể ánh xạ scope thành authority có prefix `SCOPE_`. Nếu hệ thống đặt role ở claim riêng như `roles` hoặc `authorities`, cấu hình converter tương ứng để phân quyền dùng đúng authority.

Với opaque access token, không dùng `JwtDecoder`. Hãy xác thực bằng `OpaqueTokenIntrospector` hoặc `AuthenticationManager` được cấu hình để introspect token với authorization server.

### Tại sao chỉ xác thực CONNECT?

Một STOMP session có một user identity được Spring liên kết với các message tiếp theo. Interceptor chỉ cần đọc và xác thực token khi CONNECT, sau đó gọi `setUser`. Các message SEND, SUBSCRIBE hoặc DISCONNECT của session sẽ mang danh tính đã gắn với session đó.

Không cho client tự gửi một header `username`, `userId`, `role` hay `Principal` để thay thế danh tính. Không chấp nhận danh tính từ message payload. Các trường `from`, `sender` trong DTO nếu cần hiển thị phải được server ghi đè bằng `Principal` đã xác thực.

## 5. Thứ tự ChannelInterceptor khi dùng Spring Security

Nếu ứng dụng đồng thời dùng token authentication tự viết và authorization của Spring Security, interceptor xác thực phải chạy **trước** interceptor phân quyền. Spring Framework khuyến nghị đặt custom authentication configurer trong một class `WebSocketMessageBrokerConfigurer` riêng, được đánh dấu:

~~~java
@Order(Ordered.HIGHEST_PRECEDENCE + 99)
~~~

Ví dụ `StompTokenAuthenticationConfig` ở phần trước được tách riêng và đặt order như vậy. Cấu hình authorization của Spring Security được đăng ký độc lập. Nhờ đó, khi interceptor authorization chạy, header user đã chứa Authentication hợp lệ.

Nếu interceptor xác thực chạy sau authorization, Spring Security có thể thấy message CONNECT chưa có user đã xác thực và từ chối kết nối hoặc đánh giá quyền dựa trên anonymous principal.

Không nên đăng ký cùng một interceptor xác thực nhiều lần qua nhiều configurer, vì việc đó có thể làm token bị xử lý lặp và gây khó chẩn đoán.

## 6. Authentication không thay thế Authorization

Authentication trả lời câu hỏi “ai đang kết nối?”. Authorization trả lời “người đó được phép làm gì?”.

Việc `setUser(authentication)` chỉ gắn identity và authorities vào session. Nó không tự động cho phép user gửi tới mọi destination. Hãy cấu hình authorization cho inbound message, đặc biệt phân biệt hai loại STOMP command:

- `MESSAGE`: client gửi dữ liệu tới server hoặc destination.
- `SUBSCRIBE`: client đăng ký nhận message từ destination.

Ví dụ cấu hình Spring Security hiện đại với `@EnableWebSocketSecurity` và `AuthorizationManager`:

~~~java
import static org.springframework.messaging.simp.SimpMessageType.MESSAGE;
import static org.springframework.messaging.simp.SimpMessageType.SUBSCRIBE;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

@Configuration
@EnableWebSocketSecurity
public class WebSocketAuthorizationConfig {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        messages
            .nullDestMatcher().authenticated()
            .simpDestMatchers("/app/**").hasRole("USER")
            .simpSubscribeDestMatchers("/user/**").hasRole("USER")
            .simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()
            .anyMessage().denyAll();

        return messages.build();
    }
}
~~~

Quy tắc mẫu trên có ý nghĩa:

- Message không có destination, bao gồm các command điều khiển session, cần user đã xác thực.
- Client có role `USER` được gửi message tới application destination `/app/**`.
- Client có role `USER` được subscribe destination `/user/**`.
- Các MESSAGE hoặc SUBSCRIBE khác bị từ chối.
- Các message còn lại mặc định bị từ chối.

Đặc biệt, không cho client gửi MESSAGE trực tiếp tới `/topic/**` hoặc `/queue/**` nếu đây là destination broker dành cho message do server phát. Nếu cho phép, client có thể giả mạo message hệ thống hoặc gửi message vào queue không được phép. Tương tự, không cho client subscribe tùy ý `/queue/**` vì có thể làm lộ message của user khác. Hãy cấp quyền subscribe theo destination cụ thể.

Spring Security bảo vệ `clientInboundChannel`; không áp dụng cùng cơ chế authorization cho `clientOutboundChannel`. Vì vậy, cần bảo vệ subscription inbound để kiểm soát ai có thể nhận message outbound.

## 7. CSRF và Same Origin khi dùng token

Bearer token và CSRF giải quyết hai vấn đề khác nhau:

- Bearer token xác thực client và xác định user.
- CSRF token giúp bảo vệ STOMP CONNECT khỏi kết nối trái phép từ origin khác trong mô hình trình duyệt.

Với `@EnableWebSocketSecurity`, Spring Security mặc định yêu cầu CSRF token trong inbound CONNECT. Client phải gửi CSRF token trong STOMP headers cùng với Authorization nếu dùng token authentication ở STOMP layer.

Không tắt CSRF chỉ vì đã có JWT. Nếu ứng dụng cần tùy chỉnh CSRF cho SockJS fallback, chỉ loại trừ đúng endpoint HTTP transport cần thiết và vẫn giữ kiểm tra CSRF ở STOMP CONNECT theo cấu hình phù hợp. Đồng thời cấu hình allowed origins rõ ràng cho WebSocket endpoint.

## 8. Thời hạn token và session WebSocket dài hạn

Token được kiểm tra tại CONNECT không có nghĩa token sẽ tự được xác minh lại trên từng frame. Spring gắn Principal vào session và sử dụng nó cho các message sau đó. Vì vậy, nếu JWT hết hạn trong khi WebSocket session vẫn mở, session có thể vẫn giữ identity đã xác thực cho đến khi bị đóng hoặc có cơ chế kiểm tra bổ sung.

Cần chọn chính sách rõ ràng:

- Dùng access token có thời hạn phù hợp với tuổi thọ session.
- Khi token được refresh, client có thể reconnect bằng token mới.
- Nếu cần thu hồi quyền ngay, cân nhắc opaque token introspection, denylist/revocation state hoặc chủ động đóng session liên quan.
- Với hệ thống yêu cầu kiểm tra quyền thay đổi liên tục, cân nhắc kiểm tra bổ sung ở tầng message hoặc nghiệp vụ.
- Không giả định đổi role trong authorization server sẽ tự cập nhật authorities của session WebSocket đang tồn tại.

Với JWT tự chứa, server thường không biết token đã bị thu hồi trước thời điểm `exp` nếu không có cơ chế trạng thái bổ sung. Đây là trade-off cần tính đến khi chọn JWT cho kết nối dài hạn.

## 9. Lỗi thường gặp

### CONNECT bị từ chối dù HTTP handshake thành công

HTTP handshake thành công chỉ chứng minh transport đã mở. Nếu server yêu cầu Bearer token ở STOMP CONNECT, client vẫn phải gửi native header `Authorization`. Kiểm tra `connectHeaders`, tên header và prefix `Bearer`.

### Token hợp lệ nhưng user vẫn là anonymous

Kiểm tra interceptor có chạy trên `clientInboundChannel`, có chỉ xử lý CONNECT, có gọi `accessor.setUser(authentication)` và có được đăng ký trước Spring Security interceptor hay không. Đảm bảo converter trả về Authentication có principal và authorities phù hợp.

### Không đọc được Authorization header

Dùng `StompHeaderAccessor.getFirstNativeHeader(...)` để đọc STOMP native header. Không dùng HTTP servlet request headers để tìm token nếu client gửi token trong CONNECT frame. Kiểm tra chính xác tên header client gửi.

### JWT được decode nhưng không bị xác minh đầy đủ

Không tự base64-decode JWT rồi tin claim. Dùng `JwtDecoder` đã cấu hình JWK/issuer, signature, thời hạn và audience. Token có chữ ký hợp lệ nhưng audience sai vẫn không nên được chấp nhận cho ứng dụng hiện tại.

### User xác thực được nhưng truy cập destination trái phép

Đây là vấn đề authorization. Kiểm tra quy tắc `AuthorizationManager`, authority mapping và phân biệt MESSAGE với SUBSCRIBE. Không cho client ghi trực tiếp vào broker destination hoặc subscribe queue nội bộ ngoài phạm vi được cấp.

### CONNECT bị lỗi CSRF

Nếu dùng `@EnableWebSocketSecurity`, gửi CSRF token đúng tên header và giá trị trong STOMP CONNECT. Bearer token không thay thế CSRF token. Với SockJS, làm theo hướng dẫn CSRF cho transport endpoint; không tắt CSRF toàn cục.

### Token xuất hiện trong log

Không log toàn bộ STOMP headers hoặc frame CONNECT ở production. Redact Authorization, tránh truyền token trong URL, dùng `wss://` để mã hóa đường truyền và không lưu token vào telemetry hay exception message.

## 10. Kiểm thử token authentication

Nên kiểm thử interceptor và toàn bộ STOMP security chain:

1. CONNECT không có Authorization bị từ chối.
2. Authorization sai định dạng hoặc không có Bearer scheme bị từ chối.
3. JWT sai chữ ký, hết hạn, chưa tới thời điểm hiệu lực hoặc sai issuer bị từ chối.
4. JWT có audience không dành cho ứng dụng bị từ chối.
5. JWT hợp lệ tạo Authentication với đúng principal name và authorities.
6. Các message tiếp theo của session mang cùng user identity.
7. Client không thể tự đổi user bằng header hoặc payload username.
8. User thiếu role không thể gửi tới `/app/**` hoặc subscribe `/user/**`.
9. Client không thể MESSAGE trực tiếp tới `/topic/**` hoặc `/queue/**`.
10. CONNECT thiếu CSRF token bị từ chối khi Spring Security yêu cầu.
11. Token hết hạn trong session dài hạn được xử lý theo chính sách reconnect/reauthentication đã chọn.
12. Authorization header không bị ghi log và không bị chuyển tiếp không cần thiết.

Unit test có thể mock `JwtDecoder` và converter để kiểm tra interceptor. Integration test nên khởi động WebSocket/STOMP endpoint và gửi CONNECT frame thật để xác nhận thứ tự interceptor, CSRF và authorization hoạt động đúng.

## 11. Nguyên tắc triển khai

- Ưu tiên xác thực HTTP handshake nếu ứng dụng đã có session/cookie hoặc client hỗ trợ custom handshake headers.
- Chỉ dùng STOMP CONNECT token khi có lý do thực tế, ví dụ browser client không thể gửi custom HTTP header.
- Chỉ xác thực token ở CONNECT và gắn user bằng `accessor.setUser(authentication)`.
- Dùng `JwtDecoder` hoặc introspection đã cấu hình; không tự giải mã và tin JWT payload.
- Xác minh issuer, audience, chữ ký, thời hạn và các claim bắt buộc.
- Tách authentication interceptor khỏi authorization configuration.
- Đặt interceptor xác thực trước Spring Security interceptor theo hướng dẫn Spring.
- Duy trì CSRF và allowed-origin protection; CSRF token khác Bearer token.
- Phân quyền theo destination và command; bảo vệ SUBSCRIBE cũng quan trọng như MESSAGE.
- Không tin username, role hoặc sender do client gửi trong header/payload.
- Không log token; chỉ dùng TLS/WSS.
- Có chính sách cho token hết hạn hoặc bị thu hồi trong khi session vẫn mở.

## Tài liệu tham khảo

- [Spring Framework Reference — Token Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html)
- [Spring Framework Reference — Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html)
- [Spring Framework Reference — Interception](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/interceptors.html)
- [Spring Security Reference — WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html)
- [Spring Security Reference — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
