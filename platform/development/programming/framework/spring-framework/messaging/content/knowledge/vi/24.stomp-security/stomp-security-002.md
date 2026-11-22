# Giới hạn của login và passcode STOMP trong xác thực ứng dụng Spring

## Mục tiêu và phạm vi

STOMP định nghĩa hai header **login** và **passcode** trong frame **CONNECT**. Chúng thường được hiểu nhầm là cơ chế đăng nhập người dùng cho toàn bộ ứng dụng Spring. Trên thực tế, cần phân biệt xác thực ở ba ranh giới:

1. **Client → Spring WebSocket endpoint:** xác thực người dùng của ứng dụng và tạo **Principal** gắn với WebSocket session.
2. **STOMP CONNECT:** các header của giao thức STOMP. Với STOMP over WebSocket trong Spring, **login/passcode bị bỏ qua theo mặc định**; Spring giả định người dùng đã được xác thực ở tầng HTTP.
3. **Spring broker relay → message broker:** relay dùng credentials cấu hình trên server để xác thực các kết nối TCP tới broker. Đây là danh tính broker của relay, không tự động là danh tính người dùng của ứng dụng.

Do đó, chỉ thêm login và passcode vào connectHeaders của trình duyệt không làm cho Spring Security xác thực người dùng. Muốn xác thực ở tầng STOMP, ứng dụng phải chủ động đọc thông tin xác thực trong frame CONNECT, kiểm tra nó và gắn một đối tượng **Authentication/Principal** vào message.

Nội dung này tập trung vào Spring Framework STOMP over WebSocket/SockJS, Spring Security và trường hợp dùng broker relay. STOMP client kết nối trực tiếp qua TCP tới broker có thể sử dụng login/passcode theo cơ chế xác thực của chính broker; đó là luồng khác với việc đăng nhập vào ứng dụng Spring.

## 1. login và passcode trong giao thức STOMP

### 1.1. Vai trò của hai header

STOMP frame **CONNECT** có thể chứa:

- **accept-version:** các phiên bản STOMP mà client hỗ trợ.
- **host:** virtual host mà client muốn kết nối, tùy broker.
- **login:** tên đăng nhập mà broker hoặc STOMP server có thể dùng để xác thực.
- **passcode:** mật khẩu hoặc bí mật tương ứng.
- **heart-beat:** đề xuất khoảng heartbeat hai chiều.

Ví dụ frame CONNECT minh họa:

~~~text
CONNECT
accept-version:1.2
host:/
login:messaging-client
passcode:example-secret
heart-beat:10000,10000

^@
~~~

Các giá trị trong ví dụ chỉ mang tính minh họa. Không ghi passcode thật vào source control, tài liệu, log hoặc ảnh chụp debug.

### 1.2. Những điều login/passcode không tự thực hiện

Hai header này không tự định nghĩa cách Spring Security đăng nhập người dùng, không tự tạo một SecurityContext, không cấp role/authority và cũng không tự phân quyền cho từng destination.

STOMP là giao thức messaging. Ý nghĩa cụ thể của credentials phụ thuộc server nhận frame CONNECT. Broker có thể dùng login/passcode để xác thực tài khoản broker, trong khi Spring WebSocket mặc định dùng Principal đã có từ HTTP request.

Ngoài ra, login/passcode là cặp bí mật có thể tái sử dụng. Chúng không phải cơ chế challenge-response hoặc token ngắn hạn. Nếu gửi qua kết nối không mã hóa, người quan sát được traffic có thể lấy được credentials. Hãy dùng TLS/WSS trên các chặng mạng tương ứng và quản lý bí mật an toàn.

## 2. Mô hình mặc định của Spring STOMP over WebSocket

### 2.1. Xác thực ở HTTP handshake

Một STOMP over WebSocket session bắt đầu bằng HTTP request để nâng cấp kết nối WebSocket. Với SockJS, session có thể bắt đầu bằng một chuỗi HTTP transport request.

Trong ứng dụng Spring thông thường, Spring Security xác thực request HTTP trước. Ví dụ, người dùng đăng nhập bằng form login và session cookie. Khi WebSocket handshake diễn ra, HttpServletRequest#getUserPrincipal() trả về người dùng đã xác thực. Spring gắn Principal đó với WebSocket/SockJS session và đưa thông tin người dùng vào các STOMP message tiếp theo.

Luồng mặc định:

~~~mermaid
sequenceDiagram
    participant Browser
    participant SpringSecurity as Spring Security / HTTP
    participant WebSocket as Spring WebSocket
    participant App as STOMP application
    Browser->>SpringSecurity: HTTP handshake + session cookie
    SpringSecurity->>SpringSecurity: Authenticate HTTP user
    SpringSecurity->>WebSocket: Authenticated Principal
    Browser->>WebSocket: STOMP CONNECT
    WebSocket->>App: CONNECT with session Principal
    Browser->>WebSocket: SEND / SUBSCRIBE
    WebSocket->>App: Message stamped with Principal
~~~

Spring tự động liên kết Principal của HTTP request với WebSocket/SockJS session. Vì vậy, ứng dụng dùng cookie-based HTTP session thường không cần xác thực người dùng lần nữa bằng STOMP login/passcode.

### 2.2. Spring mặc định bỏ qua login/passcode trên WebSocket

STOMP protocol có header login và passcode, vốn được thiết kế cho các kết nối STOMP như STOMP over TCP. Tuy nhiên, với STOMP over WebSocket, Spring mặc định **bỏ qua các authentication header ở tầng STOMP** và giả định người dùng đã được xác thực ở tầng HTTP transport.

Ví dụ client gửi:

~~~javascript
client.connectHeaders = {
    login: "alice",
    passcode: "secret"
};
~~~

điều đó không khiến Spring Security tự đăng nhập user alice. Nếu HTTP handshake không có Principal, việc thêm hai header trên không tự tạo ra Principal. Nếu cần cơ chế token ở CONNECT, phải cài đặt ChannelInterceptor như phần 5.

### 2.3. Lợi ích và giới hạn

Mô hình HTTP Principal có ưu điểm là tái sử dụng cơ chế bảo mật web đang có: session, form login, OAuth2 login hoặc HTTP authentication. Danh tính được gắn một lần với session, rồi dùng nhất quán cho các message của session đó.

Giới hạn là client phải mang được thông tin xác thực ở HTTP handshake. Cookie-based session hoạt động tự nhiên với trình duyệt. Nhưng một số ứng dụng mobile, máy khách không có cookie session hoặc ứng dụng stateless có thể cần một cách xác thực khác.

## 3. Phân biệt xác thực ứng dụng và xác thực broker relay

Khi cấu hình **enableStompBrokerRelay**, Spring relay mở các kết nối TCP tới broker bên ngoài. Có hai nhóm credentials:

| Cấu hình | Kết nối sử dụng | Ý nghĩa |
|---|---|---|
| **clientLogin / clientPasscode** | Mỗi TCP connection được mở thay mặt một WebSocket client | Tài khoản broker dùng chung cho các client connection qua relay |
| **systemLogin / systemPasscode** | Một TCP system connection dùng chung | Tài khoản broker cho message do mã phía server gửi, ví dụ qua SimpMessagingTemplate |

Relay luôn đặt lại header login và passcode trên CONNECT frame mà nó chuyển tiếp đến broker thay mặt client. Credentials do trình duyệt gửi trong STOMP CONNECT không được chuyển nguyên trạng thành danh tính broker riêng của người dùng. Thay vào đó, relay dùng clientLogin và clientPasscode được cấu hình trên server.

Theo API của Spring, giá trị mặc định cho các credentials broker relay là guest và guest. Không nên giữ mặc định này trong môi trường production; hãy cấu hình tài khoản có quyền tối thiểu cần thiết.

Ví dụ:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class MessagingConfiguration implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        StompBrokerRelayRegistration relay =
                registry.enableStompBrokerRelay("/topic", "/queue");

        relay.setClientLogin("spring-relay-client");
        relay.setClientPasscode(System.getenv("STOMP_CLIENT_PASSCODE"));

        relay.setSystemLogin("spring-relay-system");
        relay.setSystemPasscode(System.getenv("STOMP_SYSTEM_PASSCODE"));

        registry.setApplicationDestinationPrefixes("/app");
    }
}
~~~

Ví dụ trên chỉ cấu hình xác thực giữa relay và broker. Nó không xác thực người dùng đăng nhập vào ứng dụng Spring. Người dùng vẫn cần được xác thực ở HTTP handshake hoặc bằng cơ chế token CONNECT tùy chỉnh.

### 3.1. Hệ quả về danh tính

Các WebSocket client qua broker relay thường dùng chung một cặp clientLogin/clientPasscode để mở kết nối broker. Broker có thể nhìn thấy cùng một tài khoản broker cho nhiều người dùng ứng dụng khác nhau.

Vì vậy:

- Không dùng broker username để suy ra người dùng ứng dụng hiện tại.
- Không coi broker authentication là thay thế cho Spring Security.
- Không giả định quyền broker của một tài khoản sẽ tự ánh xạ thành role/authority của người dùng.
- Phân quyền từng user tại Spring message layer dựa trên Principal đã xác thực.
- Cấp quyền broker tối thiểu cho client relay và system relay; có thể tách hai tài khoản để giới hạn phạm vi thao tác.

Nếu hệ thống bắt buộc mỗi người dùng phải có broker identity riêng, cần thiết kế một kiến trúc xác thực/ủy quyền khác có chủ đích. Cấu hình clientLogin và clientPasscode tiêu chuẩn của relay là credentials dùng chung, không phải cơ chế tự động ánh xạ credentials riêng của từng trình duyệt.

## 4. Những hạn chế khi dùng login/passcode để đăng nhập ứng dụng

### 4.1. Không tự tạo Principal hoặc SecurityContext

Spring không tự chuyển login thành username của Authentication. Header chỉ là dữ liệu trong STOMP CONNECT. Không có một Authentication hợp lệ thì message authorization không thể dựa vào header này để nhận diện người dùng.

### 4.2. Không cấp quyền truy cập destination

Ngay cả khi broker chấp nhận login/passcode, điều đó không có nghĩa người dùng được phép gửi đến /app/admin, subscribe /topic/private hoặc đọc /user/queue/notifications.

Authentication trả lời câu hỏi **ai đang kết nối**. Authorization trả lời **người đó được phép làm gì**. Cần cấu hình riêng các quy tắc cho SEND, SUBSCRIBE và những message type khác.

### 4.3. Không phải token ngắn hạn

Passcode tĩnh có thể bị sao chép, lưu trong browser storage hoặc lộ qua log/debug. Nếu dùng lại trong nhiều session, thu hồi một credential có thể ảnh hưởng nhiều client. JWT hoặc access token có thời hạn, issuer, audience và scope rõ ràng thường phù hợp hơn khi cần xác thực stateless, nhưng vẫn cần kiểm tra token phía server.

### 4.4. Không thay thế TLS

STOMP login/passcode không mã hóa traffic. Nếu kết nối WebSocket/TCP không dùng TLS, credentials và payload có thể bị quan sát trên đường truyền. Với trình duyệt dùng wss://, TLS bảo vệ chặng browser-to-Spring. Nếu Spring relay kết nối tới broker qua TCP riêng, chặng Spring-to-broker cũng cần TLS nếu đi qua mạng không tin cậy.

### 4.5. Không giải quyết CSRF hoặc kiểm soát Origin

Một session cookie hợp lệ có thể tự động được trình duyệt gửi trong WebSocket handshake. Vì vậy, cần bảo vệ endpoint khỏi kết nối cross-site không mong muốn. Spring Security yêu cầu CSRF token trên STOMP CONNECT theo mặc định khi bật WebSocket security. Token này bảo vệ chống CSRF; nó không thay thế xác thực người dùng.

## 5. Dùng token trong STOMP CONNECT khi cần xác thực ở tầng messaging

Nếu không dùng cookie-based session, ứng dụng có thể gửi token trong STOMP CONNECT header và xác thực bằng một ChannelInterceptor.

Quy trình:

1. Client gửi token trong header CONNECT, ví dụ Authorization: Bearer ...
2. Interceptor chỉ xử lý frame CONNECT.
3. Server kiểm tra chữ ký, issuer, audience, thời hạn, trạng thái thu hồi và các claim cần thiết của token.
4. Server tạo một Authentication đã xác thực.
5. Interceptor gọi accessor.setUser(authentication).
6. Spring lưu user cho session và liên kết Principal đó với các STOMP message tiếp theo.
7. Spring Security dùng Principal để áp dụng quy tắc authorization.

### 5.1. Client gửi token trong STOMP CONNECT

Ví dụ với @stomp/stompjs:

~~~javascript
const client = new Client({
    brokerURL: "wss://app.example.com/ws",
    connectHeaders: {
        Authorization: "Bearer " + accessToken
    },
    reconnectDelay: 5000
});

client.activate();
~~~

connectHeaders là header của STOMP CONNECT sau khi WebSocket đã được thiết lập. Đây không phải HTTP header của handshake.

Trình duyệt không cho JavaScript tùy ý đặt HTTP header cho WebSocket handshake. Vì vậy, không nhầm connectHeaders với custom HTTP handshake headers. Với SockJS JavaScript client cũng có hạn chế gửi HTTP header trong các transport request; tuy vậy STOMP CONNECT vẫn có thể mang header của giao thức sau khi transport được thiết lập.

Tránh gửi token qua query parameter của URL vì URL thường xuất hiện trong access log, proxy log, telemetry hoặc công cụ giám sát.

### 5.2. Xác thực token bằng ChannelInterceptor

Ví dụ dưới đây cho thấy vị trí xử lý và cách gắn Principal. TokenAuthenticationService là service của ứng dụng; nó phải xác minh token thật và trả về một Authentication đã xác thực. Không được chỉ giải mã payload JWT rồi tin các claim mà không kiểm tra chữ ký và các điều kiện bảo mật.

~~~java
package com.example.messaging.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.simp.config.ChannelRegistration;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageHeaderAccessor;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
@Order(Ordered.HIGHEST_PRECEDENCE + 99)
public class StompTokenAuthenticationConfiguration
        implements WebSocketMessageBrokerConfigurer {

    private final TokenAuthenticationService tokenAuthenticationService;

    public StompTokenAuthenticationConfiguration(
            TokenAuthenticationService tokenAuthenticationService) {
        this.tokenAuthenticationService = tokenAuthenticationService;
    }

    @Override
    public void configureClientInboundChannel(ChannelRegistration registration) {
        registration.interceptors(new ChannelInterceptor() {
            @Override
            public Message<?> preSend(Message<?> message, MessageChannel channel) {
                StompHeaderAccessor accessor =
                        MessageHeaderAccessor.getAccessor(
                                message, StompHeaderAccessor.class);

                if (accessor != null &&
                        StompCommand.CONNECT.equals(accessor.getCommand())) {

                    String authorization =
                            accessor.getFirstNativeHeader("Authorization");

                    if (authorization == null ||
                            !authorization.startsWith("Bearer ")) {
                        throw new BadCredentialsException(
                                "Missing bearer token");
                    }

                    String token = authorization.substring(7);
                    Authentication authentication =
                            tokenAuthenticationService.authenticate(token);

                    if (authentication == null ||
                            !authentication.isAuthenticated()) {
                        throw new BadCredentialsException(
                                "Invalid bearer token");
                    }

                    accessor.setUser(authentication);
                }

                return message;
            }
        });
    }
}
~~~

Service xác thực là abstraction do ứng dụng cung cấp:

~~~java
public interface TokenAuthenticationService {
    Authentication authenticate(String token);
}
~~~

Implementation có thể dùng Spring Security Resource Server và JwtDecoder để xác minh chữ ký JWT, issuer, audience và thời hạn, sau đó ánh xạ claim thành authorities. Nếu token không hợp lệ hoặc hết hạn, phải từ chối CONNECT.

Đoạn code trên minh họa phần interceptor; để biên dịch thành ứng dụng hoàn chỉnh, cần cung cấp implementation của TokenAuthenticationService và dependency JWT tương ứng.

### 5.3. Thứ tự interceptor

Khi sử dụng Spring Security authorization cho STOMP message, interceptor xác thực token cần chạy **trước** interceptor authorization của Spring Security. Spring khuyến nghị đặt cấu hình xác thực trong WebSocketMessageBrokerConfigurer riêng và dùng:

~~~java
@Order(Ordered.HIGHEST_PRECEDENCE + 99)
~~~

Nếu interceptor chạy sau authorization, Spring Security có thể kiểm tra message trước khi Principal được gắn vào CONNECT/session.

### 5.4. Các giới hạn còn lại của token CONNECT

Token CONNECT xác thực danh tính tại thời điểm mở session. Spring gắn user đó với các message tiếp theo của session. Vì vậy, ứng dụng cần quyết định cách xử lý token hết hạn hoặc bị thu hồi khi WebSocket session vẫn còn mở: giới hạn tuổi session, đóng session khi token hết hạn, hoặc kiểm tra quyền nhạy cảm theo từng message.

Không tin username, role hoặc user ID do client tự gửi trong custom header. Những giá trị này phải được suy ra từ token đã xác minh hoặc từ kho danh tính phía server.

## 6. Authentication và authorization với Spring Security

### 6.1. Bảo vệ message sau khi đã xác thực

@EnableWebSocketSecurity tích hợp Spring Security với STOMP messaging. Spring Security có thể dùng AuthorizationManager<Message<?>> để quyết định user được phép gửi hoặc subscribe destination nào.

Ví dụ về chính sách cần thiết:

- Chỉ user đã xác thực mới được gửi message đến /app/**.
- Chỉ user có role phù hợp mới được subscribe các destination riêng tư.
- Client không được tự gửi vào các broker destination nội bộ như /topic/** hoặc /queue/** nếu ứng dụng không chủ ý cho phép.
- Destination /user/** cần được kiểm soát dựa trên Principal và chính sách của ứng dụng.
- Từ chối message type hoặc destination không được khai báo rõ.

Không nên chỉ xác thực CONNECT rồi cho phép mọi SEND/SUBSCRIBE. Mỗi destination có thể truy cập dữ liệu hoặc thực hiện hành động khác nhau.

### 6.2. CSRF token trên CONNECT

Khi bật Spring Security WebSocket security, inbound STOMP CONNECT mặc định cần có CSRF token hợp lệ. Với browser client, lấy token từ cơ chế CSRF của ứng dụng và gửi trong STOMP CONNECT headers theo tên header mà server cấu hình.

Ví dụ minh họa:

~~~javascript
const client = new Client({
    brokerURL: "wss://app.example.com/ws",
    connectHeaders: {
        Authorization: "Bearer " + accessToken,
        "X-CSRF-TOKEN": csrfToken
    }
});
~~~

Tên header CSRF phải khớp với cấu hình Spring Security và token được cấp cho client. CSRF token không chứng minh user là ai; bearer token hoặc HTTP session mới là thông tin xác thực. Không tắt CSRF toàn cục chỉ để làm cho STOMP CONNECT hoạt động. Nếu dùng SockJS và cần điều chỉnh HTTP CSRF matcher cho transport endpoint, chỉ giới hạn thay đổi ở endpoint cụ thể theo hướng dẫn của Spring Security.

### 6.3. Kiểm tra Origin và endpoint

Cần cấu hình allowed origins cho WebSocket endpoint phù hợp với domain của frontend. Không dùng wildcard origin một cách tùy tiện khi kết nối có credentials/cookie. Kiểm tra xác thực HTTP handshake, CSRF CONNECT, Principal và authorization message là các lớp bổ sung cho nhau.

## 7. Chọn mô hình xác thực phù hợp

| Mô hình | Danh tính ứng dụng đến từ đâu? | Khi nào phù hợp? | Điểm cần lưu ý |
|---|---|---|---|
| HTTP session cookie | Spring Security Principal của HTTP handshake | Web app cùng domain, đã có đăng nhập session | Cần bảo vệ CSRF và session lifecycle |
| HTTP Basic hoặc HTTP auth phù hợp | HTTP request authentication | Client có thể cung cấp cơ chế HTTP auth | Browser API có giới hạn khi tự đặt handshake headers |
| Bearer token trong STOMP CONNECT | Token được interceptor xác minh rồi gắn vào Principal | Mobile, SPA stateless hoặc client không dùng cookie | Phải tự viết interceptor, kiểm tra token và xử lý expiry/revocation |
| STOMP login/passcode trực tiếp tới broker | Tài khoản broker do broker xác thực | Client kết nối trực tiếp tới STOMP broker qua TCP | Không tự tạo Spring application Principal |
| Broker relay clientLogin/clientPasscode | Tài khoản broker cấu hình ở Spring relay | Ứng dụng dùng broker relay | Thường dùng chung cho mọi client connection qua relay |

Đối với ứng dụng Spring WebSocket thông thường, nên tận dụng HTTP Principal sẵn có. Nếu cần stateless token authentication, hãy xác thực token ở CONNECT bằng interceptor và đặt Principal rõ ràng. Chỉ dùng login/passcode như thông tin xác thực broker khi giao thức và kiến trúc yêu cầu; không dựa vào chúng để thay thế bảo mật ứng dụng.

## 8. Các lỗi phổ biến

| Triệu chứng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Client gửi login/passcode nhưng Principal vẫn null | Spring bỏ qua STOMP authentication headers theo mặc định trên WebSocket | Xác thực HTTP handshake hoặc cài CONNECT ChannelInterceptor |
| Broker relay vẫn kết nối bằng một user chung | Relay ghi đè CONNECT login/passcode bằng clientLogin/clientPasscode | Phân biệt broker identity với application Principal |
| Message authorization không nhận role | Principal chưa được gắn hoặc authorities không được ánh xạ đúng | Xác thực token và đặt Authentication vào accessor.setUser |
| Token header bị từ chối trước authorization | Authentication interceptor chạy sai thứ tự | Đặt interceptor trước Spring Security theo thứ tự được Spring hướng dẫn |
| CONNECT bị từ chối dù bearer token đúng | Thiếu CSRF token hoặc Origin không hợp lệ | Kiểm tra CSRF CONNECT và allowed origins |
| Token trong URL xuất hiện ở log | Truyền token bằng query parameter | Gửi token trong CONNECT header hoặc cơ chế HTTP auth phù hợp |
| Một user có thể subscribe destination của user khác | Chỉ xác thực CONNECT mà chưa kiểm tra quyền SUBSCRIBE | Cấu hình authorization cho từng destination và kiểm tra quyền sở hữu tài nguyên |

## 9. Checklist kiểm thử

Trước khi phát hành, kiểm tra các tình huống sau:

1. HTTP session đã xác thực tạo WebSocket session có đúng Principal.
2. HTTP session chưa xác thực bị từ chối tại handshake hoặc theo chính sách endpoint.
3. Gửi STOMP login/passcode nhưng không có HTTP Principal không vô tình được coi là user đã xác thực.
4. Token CONNECT hợp lệ tạo đúng Principal và authorities.
5. Token sai chữ ký, hết hạn, sai issuer hoặc audience bị từ chối.
6. CONNECT thiếu CSRF token bị từ chối khi Spring Security yêu cầu.
7. User đã xác thực chỉ SEND/SUBSCRIBE được destination được cấp quyền.
8. Client không thể giả mạo Principal bằng header username hoặc user ID tùy ý.
9. Broker relay dùng client credentials và system credentials đúng cấu hình; các credentials không bị ghi vào log.
10. Session cũ bị đóng hoặc quyền được cập nhật khi token hết hạn/bị thu hồi theo chính sách của hệ thống.

Có thể dùng integration test với WebSocketStompClient và test broker để kiểm tra CONNECT, Principal, SEND/SUBSCRIBE và việc từ chối message. Unit test riêng cho token validator cần bao phủ chữ ký, issuer, audience, expiration và authority mapping.

## 10. Nguyên tắc bảo mật

1. **Xác thực tại đúng ranh giới.** HTTP Principal xác thực WebSocket user; broker credentials xác thực kết nối relay tới broker.
2. **Không nhầm login/passcode với Spring Security.** Trên STOMP over WebSocket, Spring mặc định bỏ qua hai header này.
3. **Gắn Principal phía server.** Chỉ đặt user sau khi xác minh session hoặc token đáng tin cậy.
4. **Phân quyền từng message.** Kiểm tra SEND, SUBSCRIBE, destination và quyền truy cập tài nguyên.
5. **Bảo vệ CONNECT.** Dùng TLS/WSS, CSRF token phù hợp và giới hạn Origin.
6. **Bảo vệ credentials.** Không hard-code hoặc log passcode, bearer token, session ID hay private secret.
7. **Quản lý vòng đời session.** Xử lý token expiry, revocation, logout và disconnect rõ ràng.
8. **Giới hạn quyền broker.** Cấp quyền tối thiểu cho client relay và system relay; không xem broker account dùng chung là danh tính từng user.

## 11. Tài liệu tham khảo

- [Spring Framework – Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html)
- [Spring Framework – Token Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html)
- [Spring Framework – Authorization](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html)
- [Spring Framework – Connecting to a Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html)
- [StompBrokerRelayRegistration Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/config/StompBrokerRelayRegistration.html)
- [Spring Security – WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html)
- [STOMP 1.2 Specification](https://stomp.github.io/stomp-specification-1.2.html)
