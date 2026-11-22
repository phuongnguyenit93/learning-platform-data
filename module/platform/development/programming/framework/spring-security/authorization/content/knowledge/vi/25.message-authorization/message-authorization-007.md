# Principal của phiên và giới hạn tin cậy header do client gửi

## 1. Vấn đề cần giải quyết

Trong hệ thống **Spring Security phân quyền thông điệp**, một browser hoặc mobile client mở WebSocket rồi gửi STOMP frames đến server. Ví dụ client kết nối tới `/ws` và gửi:

~~~text
CONNECT
login:root
passcode:anything
X-User-Id:admin
X-Tenant:finance
X-Role:SUPER_ADMIN

^@
~~~

Sau đó client tiếp tục:

~~~text
SEND
destination:/app/chat.send
X-User-Id:admin
X-Tenant:finance
X-Role:SUPER_ADMIN
content-type:application/json

{"roomId":"private-room","sender":"admin","text":"Approved"}^@
~~~

Ký hiệu `^@` trong tài liệu chỉ biểu diễn ký tự kết thúc frame của STOMP; không phải chuỗi ký tự cần gửi nguyên văn. Những header và JSON do client gửi **không chứng minh caller là admin**. Nếu ứng dụng lấy `X-User-Id`/`sender` làm người gửi, hoặc tin `X-Role` để cho phép gửi/subscribe, attacker có thể **mạo danh** và đọc/phát thông điệp trái quyền.

Ranh giới đúng:

> **Principal của phiên phải đến từ authentication đáng tin; header STOMP và payload do client gửi chỉ là dữ liệu đầu vào. Mọi SEND/SUBSCRIBE cần kiểm tra chủ thể đã xác minh, loại message, destination và quyền trên đúng phòng/tenant/tài nguyên.**

Bài học này thuộc chủ đề **Phân quyền thông điệp**, tập trung vào **Spring Framework STOMP over WebSocket + Spring Security Messaging**, gồm cơ chế HTTP handshake, `simpUser`, xác thực `CONNECT` bằng token, `ChannelInterceptor`, `@EnableWebSocketSecurity`, quyền theo message type/destination, user destination và những giới hạn khi tin header.

Đây không phải bài về HTTP REST API thuần, AMQP/JMS broker auth thuần hoặc WebFlux WebSocketHandler raw. Các ý tưởng trust boundary áp dụng rộng, nhưng API mã nguồn bên dưới chủ yếu dành cho **Spring WebSocket/STOMP trên Servlet stack** như tài liệu chính thức Spring Security.

## 2. Mục tiêu học tập

Sau bài này, bạn có thể:
- Phân biệt **HTTP handshake**, **WebSocket session**, **STOMP CONNECT**, **SEND**, **SUBSCRIBE**, **MESSAGE** và broker output.
- Hiểu Principal được Spring lấy từ request HTTP đã xác thực rồi gắn với WebSocket/STOMP session thế nào.
- Nhận diện sự khác biệt giữa **native STOMP headers** do client tự viết và **server-managed simpUser header**.
- Giải thích tại sao `login`/`passcode` hoặc `Authorization` trong STOMP CONNECT không tự được Spring coi là authentication.
- Chọn xác thực HTTP/session hay JWT Bearer tại STOMP CONNECT một cách có chủ đích.
- Đăng ký custom authentication `ChannelInterceptor` và xếp trước Spring Security authorization interceptors.
- Cấu hình `AuthorizationManager<Message<?>>` cho inbound messages với default-deny.
- Ngăn user tự SEND tới `/topic/**` hoặc SUBSCRIBE trực tiếp `/queue/**` trái quyền.
- Bảo vệ `/user/queue/**` và hiểu cơ chế user destinations.
- Kiểm tenant, room membership, quyền READ/SEND ở mỗi SEND/SUBSCRIBE, không tin roomId/sender trong JSON.
- Phân tích Origin, Same Origin, CSRF CONNECT, SockJS, reconnect, logout và revocation.
- Phân biệt principal của kết nối với permission có thể thay đổi trong phiên dài.
- Xây dựng test matrix tấn công giả mạo headers và Java 17 standalone demo để tự chứng minh policy.

## 3. Bản đồ luồng STOMP trên WebSocket

~~~text
Browser / STOMP client
       |
       | HTTP GET /ws + Upgrade / SockJS transport
       v
Spring Security HTTP filter chain
       | authentication: session cookie / HTTP auth / gateway policy
       | verified HttpServletRequest.getUserPrincipal()
       v
WebSocket handshake -> established WebSocket session
       | Principal associated with session
       v
STOMP CONNECT frame
       | default: Spring trusts HTTP-authenticated session Principal
       | optional: custom CONNECT token auth interceptor (verify token!)
       v
clientInboundChannel
       | security context + AuthorizationManager<Message<?>>
       | differentiate CONNECT, SUBSCRIBE, SEND, DISCONNECT
       v
@MessageMapping controller / application service
       | verified actor, room tenant, membership, object policy
       v
brokerChannel -> simple broker / external broker relay
       |
       v
clientOutboundChannel -> WebSocket subscribers
~~~

Đây là sơ đồ khái niệm về thành phần và trust boundary, không phải một thứ tự tuyệt đối của mọi custom interceptor/transport. Spring Security Messaging hiện hành bảo vệ chủ yếu **clientInboundChannel**; không mặc định kiểm lại mọi message trên `clientOutboundChannel`. Vì thế quyền SUBSCRIBE và cách publish vào destination phải được thiết kế đặc biệt chặt.

**Quan trọng:** WebSocket CONNECT ở lớp transport và STOMP `CONNECT` là hai sự kiện khác nhau. HTTP handshake có thể đã authenticated trước khi STOMP `CONNECT`. Frame CONNECT lại có các native headers tùy client. Không được trộn chúng thành một bằng chứng chung.

## 4. Principal thực sự là gì?

Trong Java, `java.security.Principal` đại diện một identity với `getName()`. Spring Security thường cung cấp `Authentication extends Principal`, ngoài tên còn có authorities/credentials/details và trạng thái authentication.

Ví dụ:
~~~text
HTTP authenticated user:
  issuer = issuerA
  subject = an
  principal name = issuerA|an
  authorities = [ROLE_USER, SCOPE_chat.send]

WebSocket session:
  id = 9fe2...
  Principal = verified Authentication of issuerA|an

STOMP SEND:
  native header X-User-Id = admin (client-controlled)
  simpUser = Authentication of issuerA|an (server-managed)
~~~

Logic nghiệp vụ phải dùng **principal do framework/authentication interceptor đáng tin cung cấp**, không dùng native header `X-User-Id`. Đồng thời, không lấy một `Principal.getName()` tùy ý để chứng minh quyền trong phòng: cần membership/ACL theo tenant và action.

Tên principal có thể là username, internal actor ID hoặc một biểu diễn khác; không tự giả định mỗi username là duy nhất giữa các issuers. Nếu dùng OAuth2 multi-issuer, nên có canonical actor key `(validated issuer, sub)`.

## 5. HTTP handshake gắn Principal vào WebSocket session

Theo tài liệu Spring Framework STOMP authentication:
1. Một STOMP-over-WebSocket session bắt đầu bằng HTTP request (Upgrade hoặc SockJS transport).
2. Nếu Spring Security đã xác thực HTTP request, `HttpServletRequest#getUserPrincipal()` thể hiện actor đáng tin.
3. Spring Framework liên kết Principal đó với WebSocket/SockJS session.
4. Khi xử lý STOMP frames từ session, Spring cung cấp user information trong server-managed header và cho controller dùng tham số `Principal`.

Ví dụ handler:

~~~java
import java.security.Principal;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

@Controller
public class ChatIdentityController {

    @MessageMapping("/whoami")
    public String whoAmI(Principal principal) {
        if (principal == null) {
            throw new org.springframework.security.access.AccessDeniedException(
                "Authenticated session required");
        }
        return principal.getName();
    }
}
~~~

Đây là **Spring integration snippet**, cần cấu hình STOMP endpoint, broker/application prefixes, bảo mật inbound messages và client nhận kết quả. Return value ở `@MessageMapping` được gửi đến destination theo messaging convention, không giống REST controller trả body HTTP. Không dùng endpoint `whoami` làm cách cấp quyền khác.

Với cookie session, bảo vệ HTTP login/session fixation/logout, cookie `Secure`/`HttpOnly`/`SameSite`, WebSocket Origin và CSRF CONNECT. Không coi một socket sống rất lâu là bằng chứng permission không bao giờ thay đổi.

### HTTP authentication không luôn tồn tại

Native/mobile WebSocket clients, API chỉ dùng Bearer header, hoặc browser không thể gửi custom Authorization header tại handshake có thể không nhận một Principal đã xác thực qua HTTP. Khi đó có thể cần **xác thực token trong STOMP CONNECT bằng custom interceptor**, hoặc một protocol khác đáng tin. Đừng lấy identity từ `login` native header như shortcut.

## 6. STOMP native headers không tự là security context

STOMP frame có nhiều native headers:
- `login`, `passcode`.
- `Authorization` do client tự khai.
- `X-User-Id`, `X-Role`, `X-Tenant-Id`.
- `destination`, `subscription id`.
- Tuỳ ứng dụng: `roomId`, `from`, `toUser`.

Mỗi giá trị đều có thể được client thay đổi. Spring Framework **mặc định bỏ qua authentication headers ở STOMP protocol level** đối với STOMP over WebSocket, vì nó thường dựa vào authentication ở HTTP handshake. Đặc biệt:
- `login=root` không đồng nghĩa server xác thực root.
- `passcode=secret` không tự kích hoạt Spring PasswordEncoder.
- `Authorization: Bearer ...` trong CONNECT chưa được verify nếu không có custom token authentication mechanism.
- `X-Role=ADMIN` chỉ là text, không biến thành `GrantedAuthority`.
- `simpUser` dạng server-managed message header có thể chứa Authentication; **đừng** lấy native STOMP header trùng tên để thay giá trị này.

Một anti-pattern:
~~~java
StompHeaderAccessor accessor =
        StompHeaderAccessor.wrap(message);
String role = accessor.getFirstNativeHeader("X-Role");
if ("ADMIN".equals(role)) {
    // BAD: caller controls X-Role.
    approveEverything();
}
~~~

**Đây là code SAI để nhận diện**, không dùng trong production. Dùng `Authentication.getAuthorities()` sau verification và domain policy service.

## 7. Bảng phân biệt các loại header

| Loại | Ví dụ | Ai điều khiển? | Có thể dùng làm identity proof? |
|---|---|---|---|
| HTTP handshake headers | Cookie, Authorization | Client trình bày; filter xác minh | Chỉ **sau** HTTP authn |
| STOMP CONNECT native | `login`, `passcode` | Client | Không mặc định |
| STOMP custom native | `X-User`, `X-Role`, `X-Tenant` | Client | **Không** |
| STOMP destination | `/app/chat.send`, `/topic/rooms/7` | Client chọn | Không, chỉ là action/target |
| STOMP body | `senderId`, `roomId` | Client | Không |
| Server-managed `simpUser` | Principal/Authentication | Framework hoặc trusted interceptor | Có thể dùng **nếu** trust boundary đã được bảo vệ |
| `simpSessionId` | ID session từ transport | Framework | Không phải quyền trên tài nguyên |
| Session attributes | Map thuộc session | Server lưu, có thể bắt nguồn từ request | Chỉ tin thuộc tính có provenance/validation rõ |
| Broker output headers | Destination/metadata do broker tạo | Server/broker | Không thay resource permission |

**Header có tên “authenticated” không chứng minh tính xác thực.** Chỉ quá trình authentication được cấu hình và thực sự chạy mới cấp trust. Nếu tự copy raw STOMP native headers vào server-managed header map, application có thể làm hỏng ranh giới.

## 8. Xác thực HTTP và xác thực STOMP CONNECT: chọn mô hình

Hai mô hình phổ biến:

### Mô hình A — HTTP/session đã xác thực

~~~text
Login form/OIDC web login
     -> session cookie and SecurityContext
HTTP GET /ws
     -> Spring Security authenticated Principal
STOMP CONNECT
     -> user inherited from HTTP handshake
SEND/SUBSCRIBE
     -> message authorization + domain policy
~~~

Phù hợp nhiều ứng dụng browser session-based. Không cần client tự truyền username/password trong STOMP. CSRF CONNECT và Origin restrictions rất quan trọng vì browser có thể tự gửi cookie.

### Mô hình B — Token authentication tại STOMP CONNECT

~~~text
HTTP /ws handshake (token may not be in HTTP headers)
STOMP CONNECT:
  Authorization: Bearer <token>
     |
     v
Trusted ChannelInterceptor
  -> JwtDecoder/AuthManager verifies token, issuer, audience, expiry
  -> constructs Authentication
  -> accessor.setUser(verifiedAuthentication)
     |
     v
Spring Security message authorization
     |
     v
SEND/SUBSCRIBE
~~~

Mô hình B có lý khi browser STOMP client không gửi được custom HTTP handshake headers. Tuy nhiên **chỉ frame CONNECT là nơi trình bày credential**; interceptor phải verify token bằng code đáng tin, không tạo `UsernamePasswordAuthenticationToken` đã authenticated dựa trên chuỗi `sub`/`role` chưa xác minh.

Chọn mô hình phù hợp, thiết kế conflict khi cả handshake HTTP Principal và CONNECT token đều có, và kiểm re-auth/reconnect. Không ngầm cho token của tài khoản B **thay Principal của session A** nếu không có chủ đích và policy.

## 9. Token CONNECT: vì sao cần ChannelInterceptor?

Spring Framework hướng dẫn xác thực STOMP token bằng hai bước:
1. STOMP client gửi authentication header tại CONNECT.
2. Server xử lý trong `ChannelInterceptor` đăng ký trên `clientInboundChannel`, **xác minh token** rồi gọi `StompHeaderAccessor.setUser(authentication)`.

Điểm quan trọng là **chỉ xác thực CONNECT một lần và gắn verified user với session**; Spring Framework quản lý liên kết user cho subsequent STOMP messages.

Bên dưới là một ví dụ **Spring integration** sử dụng Spring Security `AuthenticationManager` đã được cấu hình để xác minh Bearer token. Đây không phải một ứng dụng đứng độc lập:

~~~java
import java.security.Principal;
import java.util.List;

import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageHeaderAccessor;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.Authentication;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthenticationToken;
import org.springframework.web.socket.config.annotation.ChannelRegistration;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;

@Configuration
@Order(Ordered.HIGHEST_PRECEDENCE + 99)
public class StompConnectAuthenticationConfig
        implements WebSocketMessageBrokerConfigurer {

    private final AuthenticationManager bearerAuthenticationManager;

    public StompConnectAuthenticationConfig(
            AuthenticationManager bearerAuthenticationManager) {
        this.bearerAuthenticationManager = bearerAuthenticationManager;
    }

    @Override
    public void configureClientInboundChannel(
            ChannelRegistration registration) {

        registration.interceptors(new ChannelInterceptor() {
            @Override
            public Message<?> preSend(
                    Message<?> message, MessageChannel channel) {
                StompHeaderAccessor accessor =
                        MessageHeaderAccessor.getAccessor(
                                message, StompHeaderAccessor.class);

                if (accessor == null
                        || accessor.getCommand() != StompCommand.CONNECT) {
                    return message;
                }

                List<String> values =
                        accessor.getNativeHeader("Authorization");

                if (values == null || values.size() != 1
                        || !values.get(0).startsWith("Bearer ")) {
                    throw new BadCredentialsException(
                            "Bearer token required at CONNECT");
                }

                String credential =
                        values.get(0).substring("Bearer ".length()).trim();
                if (credential.isBlank()) {
                    throw new BadCredentialsException(
                            "Empty Bearer token");
                }

                Authentication verified =
                        bearerAuthenticationManager.authenticate(
                            new BearerTokenAuthenticationToken(credential));

                if (verified == null || !verified.isAuthenticated()) {
                    throw new BadCredentialsException(
                            "Token authentication failed");
                }

                Principal httpPrincipal = accessor.getUser();
                if (httpPrincipal != null
                        && !httpPrincipal.getName().equals(
                                verified.getName())) {
                    throw new BadCredentialsException(
                            "HTTP/STOMP principal conflict");
                }

                accessor.setUser(verified);
                return message;
            }
        });
    }
}
~~~

**Giới hạn và điều kiện tích hợp của đoạn code:**
- `bearerAuthenticationManager` phải thực sự có provider xác minh token, ví dụ `JwtAuthenticationProvider` với `JwtDecoder`/issuer/audience validators phù hợp. **Không dùng** manager chỉ tạo authenticated user từ raw claim.
- `Authorization` là native STOMP header do client gửi: chỉ dùng nó như **credential để verify**, không tin roles/tenant/header khác.
- Đoạn code giả định mô hình token-at-CONNECT. Nếu dùng HTTP session-only, đừng bắt mọi CONNECT có Bearer token.
- Tránh lưu token dạng raw vào session attributes, exceptions hoặc logs.
- Chuỗi header `Bearer ...` cần có chính sách input length, malformed cases và rate limits thực tế. Mã tập trung trust boundary, không thay toàn bộ hardening.
- Nếu HTTP Principal và token Principal khác nhau, ví dụ chọn **từ chối conflict**. Nếu sản phẩm cho phép identity switching, phải có protocol/session isolation và tests riêng.
- Có thể cần xử lý SecurityContext/authorities trên version và cấu hình cụ thể; chỉ gọi `setUser` với verified Authentication rồi tiếp tục sang authorization.
- **Thứ tự interceptor bắt buộc:** Spring Framework khuyến nghị đặt authentication interceptor trước Spring Security, dùng một `WebSocketMessageBrokerConfigurer` riêng với `@Order(Ordered.HIGHEST_PRECEDENCE + 99)`. Không assume đăng ký ở bean khác sẽ tự có đúng order.
- Với `@EnableWebSocketSecurity`, Spring Security cũng yêu cầu CSRF CONNECT theo mặc định. Bearer-only STOMP flow phải phối hợp với CSRF/Origin protection **theo version và threat model**; đoạn code không có ý nghĩa “Bearer thì tự động bypass CSRF”.

Không sửa Spring Security’s `simpUser` một cách tùy tiện trong interceptor chạy sau authorization; identity phải được xác lập **trước** khi permission decision dựa trên nó.

## 10. Tại sao không tự đọc Authorization header rồi decode token?

Mã sai:

~~~java
String bearer = accessor.getFirstNativeHeader("Authorization");
// SAI: split JWT, Base64URL decode payload,
// lấy "sub" và "roles" rồi tạo Authentication authenticated=true.
~~~

Một JWT có thể được tự encode lại với `sub=admin` mà không có chữ ký hợp lệ. Cần dùng `JwtDecoder` + issuer/audience/timestamps/algorithm trust, hoặc OAuth2 opaque token introspection đáng tin.

Với token thật:
- Chữ ký có thể hợp lệ nhưng `aud` dành cho API khác.
- OIDC ID token cũng có thể là signed JWT nhưng không phải API access token.
- Token có `scope=chat.send` chưa chắc được gửi vào room 42.
- Tenant role có thể stale khi membership bị revoke.
- Token của service account khác token của human user.

**Đừng đồng nhất** `setUser(new UsernamePasswordAuthenticationToken("admin",null,adminAuthorities))` với authentication: nếu lấy username/authorities từ native headers, bạn đang tạo một **principal giả mạo**.

## 11. User principal trong @MessageMapping

Spring Messaging có thể inject `Principal` vào handler:

~~~java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Controller;

@Controller
public class ChatMessageController {

    private final ChatPermissionService permissions;
    private final SimpMessagingTemplate broker;

    public ChatMessageController(
            ChatPermissionService permissions, SimpMessagingTemplate broker) {
        this.permissions = permissions;
        this.broker = broker;
    }

    @MessageMapping("/chat.send")
    public void send(ChatInput input, Principal principal) {
        if (principal == null) {
            throw new org.springframework.security.access.AccessDeniedException(
                "Authenticated WebSocket principal required");
        }

        VerifiedRoom room =
                permissions.requireCanSend(principal, input.roomId());

        ChatEvent event = new ChatEvent(
                principal.getName(), room.id(), input.text());

        broker.convertAndSend(
                "/topic/rooms/" + room.id(), event);
    }
}
~~~

**Code tích hợp**: `ChatInput`, `VerifiedRoom`, `ChatEvent` và `ChatPermissionService` là domain types mà ứng dụng phải hiện thực; tên class/field ở đây minh họa contract. Ưu tiên canonical actor identity thay cho username nếu có multi-issuer. Spring config phải map `/app` application prefix để client `SEND destination:/app/chat.send` vào handler.

**Điểm chính:** `ChatInput` không có `fromUserId` làm authority. Actor được xác định bằng trusted `Principal`, và room thực được tra qua permission service. Nếu body vẫn chứa `sender` vì client UI cần, server phải bỏ qua/đối chiếu, không dùng nó để lập audit identity.

Nếu `roomId` đến từ body, nó là **target được yêu cầu**, phải query room theo tenant và membership. Không trực tiếp publish tới `"/topic/rooms/"+input.roomId()` trước khi authorization.

## 12. Message type: SEND khác SUBSCRIBE

STOMP dùng nhiều frame types:
- `CONNECT`: client mở STOMP protocol session.
- `SUBSCRIBE`: client yêu cầu nhận messages từ destination.
- `SEND`: client gửi một message tới destination.
- `UNSUBSCRIBE`: hủy một subscription.
- `DISCONNECT`: ngắt STOMP session.
- Heartbeat/control frames tùy transport.

Spring Security authorization có thể match kiểu message:
- `SimpMessageType.MESSAGE` tương ứng inbound application message (chẳng hạn STOMP SEND).
- `SimpMessageType.SUBSCRIBE` cho đăng ký nhận.
- `nullDestMatcher()` cho các messages không có destination, như CONNECT/UNSUBSCRIBE/DISCONNECT/heartbeat theo cơ chế tương ứng.

**Không áp cùng rule cho mọi message chỉ dựa destination.** Một phòng chat có thể cho READ nhưng không cho SEND. Đăng ký notification có thể được cho phép, nhưng client không được gửi trực tiếp vào broker topic đó.

Bảng:
| Frame | Destination | Quyền thường cần |
|---|---|---|
| CONNECT | Không có | Authentication/CSRF/Origin phù hợp |
| SUBSCRIBE | `/user/queue/alerts` | Principal đúng session |
| SUBSCRIBE | `/topic/rooms/42` | READ membership của Room #42 |
| SEND | `/app/chat.send` | SEND permission trên Room target |
| SEND | `/topic/system/alerts` | **DENY** với client; server mới được phát |
| SUBSCRIBE | `/queue/internal/**` | **DENY** nếu không có trusted mapping |
| SEND | `/app/admin.deleteRoom` | Role/action admin + tenant/resource policy |
| DISCONNECT | Không có | Lifecycle handling; không tạo side effect thiếu quyền |

## 13. Spring Security @EnableWebSocketSecurity và AuthorizationManager

Spring Security 5.8+ giới thiệu cấu hình message authorization bằng `AuthorizationManager<Message<?>>`. Ví dụ **coarse boundary** mặc định deny:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

import static org.springframework.messaging.simp.SimpMessageType.MESSAGE;
import static org.springframework.messaging.simp.SimpMessageType.SUBSCRIBE;

@Configuration
@EnableWebSocketSecurity
public class ChatMessageSecurityConfiguration {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        messages
            .nullDestMatcher().authenticated()
            .simpSubscribeDestMatchers("/user/queue/alerts")
                .authenticated()
            .simpMessageDestMatchers("/app/chat.send")
                .hasAuthority("SCOPE_chat.send")
            .simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()
            .anyMessage().denyAll();

        return messages.build();
    }
}
~~~

Đây là **Spring Security Messaging integration snippet**, cần Spring Security Messaging, Spring WebSocket broker và authentication scheme phù hợp. Nó cho:
- CONNECT và control messages không có destination cần authenticated (kèm CSRF CONNECT khi enabled).
- User được SUBSCRIBE đúng `/user/queue/alerts` của phiên.
- SEND vào `/app/chat.send` yêu cầu authority `SCOPE_chat.send`.
- Mọi SUBSCRIBE/MESSAGE khác bị từ chối.
- Mọi message khác cũng deny theo fallback.

**Vì sao không cho blanket `/topic/rooms/**`?** Cấu hình coarse `authenticated()` trên topic phòng riêng **không chứng minh quyền READ room**. Đối với topic phòng riêng, cần thêm matcher/policy tùy room+tenant, hoặc không cho subscribe đến khi backend kiểm subscription qua custom authorization manager. Cấu hình ví dụ cố tình **deny** những topics riêng chưa có policy.

`hasRole("USER")` kiểm authority `ROLE_USER`, còn OAuth scope thường thành `SCOPE_chat.send`, do đó dùng `hasAuthority(...)` đúng chuỗi. Không tự tin native header `role=USER`.

### Lưu ý phiên bản

API matchers `simpMessageDestMatchers` và `simpSubscribeDestMatchers` có trong Spring Security Messaging 6.5 và 7.x Javadocs. Các ví dụ cũ dùng `AbstractSecurityWebSocketMessageBrokerConfigurer`/SpEL expressions có thể khác; khi nâng cấp, kiểm Spring Security version, deprecations và migration docs. Không nhầm message authorization `AuthorizationManager<Message<?>>` với WebFlux `ReactiveAuthorizationManager<AuthorizationContext>`.

## 14. SUBSCRIBE vào private topic phải kiểm room membership

Một destination:

~~~text
/topic/tenants/north/rooms/42
~~~

chứa tenant và room ID do **client chọn**. Một người có Principal thật nhưng không thuộc Room #42 vẫn có thể cố subscribe. Phải kiểm:
1. Actor đã được xác thực từ session.
2. Requested tenant/room target có định dạng hợp lệ.
3. Room #42 tồn tại trong tenant north (theo scope cho phép xem).
4. Actor có active membership/READ grant trên room.
5. Subscription destination có đúng prefix và loại message được phép.
6. Policy version/revocation và session subscription lifecycle được quản lý.

Pseudo policy:
~~~text
ALLOW_SUBSCRIBE_ROOM =
    authenticatedSessionPrincipal
    AND frame.type == SUBSCRIBE
    AND destination == verifiedRoomDestination(room)
    AND requestedTenant == verifiedRoom.tenant
    AND activeTenantMembership(actor, verifiedRoom.tenant)
    AND activeRoomMembership(actor, verifiedRoom.id)
    AND canReadMessages(actor, verifiedRoom.id)
~~~

**Không thể dùng** `X-Room-Member=true`, `X-Tenant=north` hoặc body `isOwner=true` làm bằng chứng.

Đối với broker topics chứa dữ liệu riêng, hệ thống phải **chặn SUBSCRIBE trái quyền trước khi broker bắt đầu gửi**. Spring Security chủ yếu kiểm inbound, nên đừng kỳ vọng một outbound interceptor mặc định sẽ dọn dữ liệu nhạy cảm sau đó.

## 15. SEND vào application destination cũng cần resource authorization

Một user có `SCOPE_chat.send` có thể gửi vào application handler `/app/chat.send`. Nhưng scope chức năng chưa đủ để SEND trong mọi room.

Ví dụ:
~~~text
Verified Principal = issuerA|an
Authorities = [SCOPE_chat.send]

Client payload:
{
  "roomId": "room-of-other-tenant",
  "sender": "system",
  "text": "System announcement"
}
~~~

Coarse HTTP/message gate có thể PASS do scope. Application service phải:
- Lấy actor từ Principal/Authentication đã xác minh.
- Lấy room metadata từ trusted repository.
- Kiểm tenant membership và SEND permission.
- Kiểm trạng thái room, muted/blocked/archived, rate limits.
- Ghi sender của ChatEvent bằng verified actor, không bằng JSON field.
- Publish chỉ sau khi authorization và mutation/audit thành công.

Một malicious client có thể tự gửi STOMP `SEND destination:/topic/system/alerts`. Chính vì thế thông lệ an toàn là **deny client SEND tới broker prefixes** như `/topic/**`, `/queue/**`. Application server có thể publish sau khi kiểm quyền; client chỉ gửi vào `/app/**` và các routes được cấp cụ thể.

## 16. /user destination không có nghĩa client được chỉ định tùy ý người nhận

Spring Framework hỗ trợ user destinations:
- Client subscribe `/user/queue/alerts`.
- Server dùng `SimpMessagingTemplate.convertAndSendToUser(username, "/queue/alerts", payload)`.
- `UserDestinationMessageHandler` chuyển destination đến các session tương ứng (tên destination cụ thể được biến đổi để tránh collision).

Đây là **định tuyến theo user/session**, không phải permission system tự động của mọi business object.

Ví dụ:
~~~java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class NotificationPublisher {
    private final SimpMessagingTemplate messaging;

    public NotificationPublisher(SimpMessagingTemplate messaging) {
        this.messaging = messaging;
    }

    public void sendVerifiedRecipient(String canonicalUsername,
                                      Object safePayload) {
        messaging.convertAndSendToUser(
                canonicalUsername, "/queue/alerts", safePayload);
    }
}
~~~

**Code tích hợp**; caller của `sendVerifiedRecipient` phải xác định recipient từ domain policy đáng tin và kiểm privacy. Không dùng giá trị `toUser` của client làm bằng chứng để gửi dữ liệu bí mật cho người khác; đó là **đối tượng yêu cầu**, cần policy cho phép.

Nếu user có nhiều sessions, mặc định user destination có thể gửi tới nhiều sessions của cùng user; `@SendToUser(broadcast = false)` là một cách giới hạn reply vào session hiện tại trong tình huống tương ứng. Đừng suy luận message chỉ tới đúng một browser tab nếu ứng dụng không cấu hình như vậy.

Không cho client subscribe trực tiếp những broker queue đã được resolve, ví dụ `/queue/alerts-user-session-123`, nếu nó có thể vượt cơ chế user destinations.

## 17. Session ID không phải một credential chia sẻ được

`simpSessionId` và WebSocket session ID thường là identifier được framework gắn với kết nối. Nó hữu ích cho logs, subscription mapping và routing. Nhưng:
- Session ID không tự chứng minh một account có quyền trên room.
- Client có thể tự gửi string trông giống session ID trong native header; không có trust.
- Không dùng session ID do request body khai làm identity.
- Không để client chỉ định `simpUser` server header qua direct message map.
- Khi disconnect, session state và subscriptions phải được dọn theo lifecycle.
- Session mới sau reconnect phải xác thực lại theo cơ chế đã chọn.

Nếu cần hỗ trợ nhiều WebSocket connections cho cùng một user, mô hình phải phân biệt **actor identity** (có thể chung) với **session identity** (mỗi kết nối khác nhau).

## 18. Phân biệt WebSocket session, HTTP session và bean scope

| Khái niệm | Vòng đời | Độ tin cậy |
|---|---|---|
| HTTP session | Nhiều HTTP requests theo cookie/session | Tùy authentication provider và session policy |
| WebSocket session | Một kết nối WebSocket; có thể kéo dài | Có authenticated Principal nhưng permission có thể đổi |
| STOMP subscription | Một đăng ký trên session | Phải authorize riêng theo destination |
| Session attributes map | Dữ liệu server gắn với WebSocket session | Chỉ tin field được tạo sau validation |
| WebSocket-scoped bean | Một bean mỗi session khi dùng scope này | Không tự là authorization proof |
| Singleton service | Dùng chung toàn ứng dụng | Không lưu mutable currentUser/currentTenant |
| Message payload/native headers | Một frame do client gửi | Không đáng tin |

Spring Framework hỗ trợ WebSocket-scoped bean với `@Scope(scopeName="websocket", proxyMode=...)`. Scope quản lý **vòng đời**, không xác minh role/owner. Đừng để bean session tự mang quyền ADMIN stale vô hạn mà không có revalidation/revocation design.

Một singleton `@Controller` hoặc `@Service` **không được** lưu:
~~~java
private Principal currentPrincipal;
private String currentTenant;
~~~
rồi ghi đè mỗi frame. Nhiều sessions xử lý đồng thời có thể làm lẫn danh tính. Truyền Principal và resource scope qua handler/service parameters hoặc trusted context per message/session.

## 19. WebSocket Origin và Same Origin: điểm dễ hiểu sai

Browser **không áp Same Origin Policy cho WebSocket giống XMLHttpRequest/fetch**. Một site khác có thể tạo WebSocket handshake với server nếu server cho phép. Khi browser tự gửi cookies phiên, rủi ro **Cross-Site WebSocket Hijacking** có thể xuất hiện.

Lớp phòng thủ:
1. Hạn chế allowed origins của WebSocket endpoints (Spring Framework theo mặc định thường chỉ cho same origin ở cấu hình tương ứng).
2. Giữ CSRF token trên STOMP CONNECT khi dùng Spring Security Messaging hỗ trợ, theo version/flow.
3. Thiết kế cookie `Secure`, `HttpOnly`, `SameSite` phù hợp.
4. Authentication và authorization của mọi message/destination.
5. Không tin `Origin` như role/tenant; non-browser clients có thể tự tạo Origin.
6. Không bật `setAllowedOriginPatterns("*")` chỉ để test kết nối khi dùng session cookies.

Trong WebSocket, thông thường cấu hình:

~~~java
registry.addEndpoint("/ws")
        .setAllowedOrigins("https://app.example.test");
~~~

là **snippet transport** dùng trong `registerStompEndpoints(StompEndpointRegistry registry)`, cần imports/cấu hình đầy đủ. Origin allowlist là browser-oriented protection, không tự thay authentication hoặc tenant ACL.

## 20. Spring Security CSRF token trong STOMP CONNECT

Tài liệu Spring Security WebSocket cho biết mặc định `@EnableWebSocketSecurity` yêu cầu CSRF token cho inbound `CONNECT` để thực thi Same Origin policy (đặc biệt với cookie-authenticated sessions).

Vì SockJS browser client có thể không gửi custom HTTP headers trên transport, token có thể được gửi trong **native STOMP CONNECT headers** theo tên/giá trị mà CSRF support yêu cầu. Token phải đến từ một kênh hợp lệ và được server kiểm.

Quy trình:
~~~text
HTML/SPA lấy CSRF token từ server sau khi có session phù hợp
        |
        v
STOMP CONNECT native header:
  X-CSRF-TOKEN: token-value
        |
        v
Spring Security Messaging CSRF check
        |
        v
Message authorization
~~~

**CSRF token không phải quyền đọc phòng.** Nó chống request từ site khác lợi dụng cookies, không xác nhận user được subscribe private topic. Ngoài ra CSRF CONNECT không thay JWT/HTTP authentication.

Tùy Spring Security version, việc tắt hoặc tùy chỉnh WebSocket CSRF trong `@EnableWebSocketSecurity` có hạn chế và có thể cần cấu hình components/XML thay vì một DSL toggle đơn giản. Đừng copy code `csrf().disable()` của HTTP và nghĩ nó tự giải quyết WebSocket CONNECT; đối chiếu tài liệu và integration tests thực tế.

## 21. SockJS và token trong URL: tránh rò credential

SockJS có transport fallback qua nhiều HTTP requests và những hạn chế browser về custom headers. Đưa Bearer token vào query string:
~~~text
/ws?access_token=eyJ...
~~~
là nguy hiểm vì nó có thể lộ qua access logs, reverse proxy, analytics, history, monitoring hoặc diagnostic URLs.

Lựa chọn:
- HTTP/session authentication nếu có thể.
- STOMP CONNECT token header + trusted authentication interceptor.
- Một cơ chế token ngắn hạn dành riêng WebSocket handshake, audience/scope rõ, có kiểm chống replay/expiry, nếu kiến trúc yêu cầu.
- Bảo vệ TLS/WSS và secrets; không hard-code tokens trong client bundle.

Không đặt refresh token vào STOMP headers nếu chỉ cần access token. Không log toàn bộ STOMP CONNECT frame khi debug. Một token hợp lệ ở CONNECT vẫn có thể hết hạn hoặc bị revoke trong lúc session duy trì lâu — cần lifecycle policy.

## 22. Broker relay login/passcode không phải user auth

Khi ứng dụng dùng external STOMP broker relay, Spring có thể dùng `systemLogin/systemPasscode` cho kết nối system và `clientLogin/clientPasscode` cho các broker-side TCP connections. Broker relay sẽ đặt những credentials này khi chuyển CONNECT đến broker.

**Đừng nhầm** chúng với `login/passcode` do browser client tự gửi trong STOMP frame. Mặc định Spring không dùng native headers đó để xác thực user tại application. Cấp một broker account chung cho relay cũng không thay quyền từng end user ở Spring Security Messaging.

Quy tắc:
- User authorization phải diễn ra trước khi broker được quyền phát nhận.
- Broker credentials lưu trong secret store và rotate.
- Client không được SEND trực tiếp tới broker prefixes hoặc bypass relay.
- External broker permissions là defense in depth, không thay per-room/tenant ACL.
- Nếu broker có endpoint public khác, khóa network access và auth cho endpoint ấy.

## 23. Long-lived session: quyền có thể thay đổi sau CONNECT

Giả sử:
~~~text
T0: An HTTP-authenticated, WebSocket CONNECT thành công.
T1: An được READ room #42 và SUBSCRIBE.
T2: Admin thu hồi READ room #42.
T3: Broker tiếp tục push messages vào subscription đã tồn tại.
~~~

Nếu authorization chỉ kiểm ở T1, An có thể tiếp tục nhận tới khi session/subscription bị hủy. Token signature tại CONNECT vẫn có thể hợp lệ dù membership đã đổi.

Cần xác định policy:
- Khi nào revoke có hiệu lực?
- Có cơ chế chủ động **hủy subscription/disconnect** khi ACL đổi không?
- Có kiểm lại permission trước sensitive outbound publish không?
- Những message cần privacy cao có phải gắn per-recipient user destinations và filtered fan-out?
- Cache ALLOW TTL/policy revision bao lâu?
- Session/token expiration được xử lý thế nào khi kết nối chưa đóng?
- Có chặn reconnect nếu account disabled không?

**Không hứa revocation tức thì** chỉ vì authentication đã được kiểm lúc CONNECT. Với luồng nhiều người subscribe, có thể cần quản lý subscription registry và re-evaluation khi policy đổi. Spring Security chủ yếu bảo vệ inbound, nên đây là trách nhiệm kiến trúc khi stream dữ liệu nhạy cảm.

## 24. CONNECT đã authenticated không tự cho mọi SUBSCRIBE

Một actor có `ROLE_USER` thường được phép kết nối nhưng:
- Không nhất thiết có READ quyền trong mọi room.
- Không có quyền SUBSCRIBE admin events.
- Không có quyền xem user queue của người khác.
- Không nhất thiết có quyền SEND announcements.
- Không có quyền gọi room deletion command.
- Không được bỏ kiểm tenant khi roomId trong destination.

Một policy bảo thủ:
~~~text
CONNECT: verified session + CSRF/Origin checks
SUBSCRIBE /user/queue/alerts: authenticated own-user destination
SUBSCRIBE private rooms: verified tenant + room READ permission
SEND /app/chat.send: scope/action + room SEND permission
SEND /topic/**: deny from client
SUBSCRIBE /queue/** directly: deny
Unknown frame/destination: deny
~~~

Nguyên tắc default deny giúp route mới không vô tình mở khi thêm message handler. Cần test cả control frames CONNECT/UNSUBSCRIBE/DISCONNECT/heartbeat theo cấu hình cụ thể để không làm hỏng lifecycle.

## 25. Subscription path, wildcard và encoded destination

Các destination patterns dễ có lỗi:
- `/topic/rooms/*` quá rộng cho rooms riêng.
- `/topic/tenants/{tenant}/rooms/{room}`: tenant/room là client-requested path variables, không phải verified resource.
- `/user/queue/**`: có thể có queue mới chứa dữ liệu nhạy cảm mà không định nghĩa policy riêng.
- `/topic/**`: topic public và topic private cùng prefix.
- Slash/dot separators hoặc normalized destination khác nhau tùy configured path matcher.

Cần kiểm:
1. Message type (SUBSCRIBE vs SEND).
2. Destination matchers theo version Spring Security và Spring Messaging path matcher.
3. Biến path được validate format/length và resolved thành resource ID.
4. Membership/ACL theo resource thực, không theo wildcard.
5. Wildcard fallback deny.
6. Direct user-resolved queue subscriptions bị từ chối.
7. Broker/application/user prefixes không overlap và không bị route nhầm.

Đừng xây policy “tất cả user authenticated được SUBSCRIBE /topic/**” nếu topic chứa dữ liệu riêng. Đừng tin `X-Subscription-Allowed: true` native header.

## 26. Authentication principal và scope theo tenant

Một Principal có thể biểu diễn:
~~~text
issuerA|an
~~~
nhưng user An có:
~~~text
tenant north: CHAT_READ, CHAT_SEND
tenant south: CHAT_READ only
~~~

Nếu Authentication có global `SCOPE_chat.send`, nó chỉ cho phép **loại action** ở message authorization layer, không cho SEND tại mọi tenant. Service phải kiểm:
~~~text
ALLOW_SEND =
    verifiedPrincipal
    AND message.type == SEND
    AND destination == /app/chat.send
    AND general CHAT_SEND authority
    AND activeTenantMembership(principal, targetRoom.tenant)
    AND roomMembership grants SEND
    AND room.enabled && notMuted(principal)
~~~

Client có thể khai `X-Tenant:south` hoặc `role:owner`, nhưng không chứng minh membership. Actor key cũng cần namespace issuer+subject nếu có nhiều OAuth issuers.

Không coi browser sessionId là token để xác định tenant, vì một user có thể đồng thời vào nhiều tenants trong nhiều tabs/connections. Nếu tenant context gắn riêng session, việc chọn và xác minh tenant tại CONNECT phải chặt, và mỗi message phải đối chiếu destination/resource tenant.

## 27. Headers do gateway thêm: khi nào có thể tin?

Một reverse proxy có thể authenticate rồi gắn:
~~~http
X-Authenticated-User: an
X-Authenticated-Tenant: north
X-Authenticated-Roles: CHAT_SEND
~~~

Nếu backend WebSocket handshake có thể được gọi trực tiếp, hoặc proxy không strip headers client tự gửi, kẻ tấn công chỉ cần tự thêm chúng.

Chỉ coi proxy identity là đáng tin khi:
- Không có đường bypass tới backend.
- Gateway xác thực credential và kiểm audience.
- Proxy loại bỏ/ghi đè incoming identity headers từ public.
- Backend xác nhận nguồn request bằng mTLS/service identity/trusted signed context.
- Identity namespace, tenant scope, expiry, audience và replay protections được kiểm.
- Có test gọi backend trực tiếp với forged identity headers; phải bị chặn.

**Header được đặt tên "Verified" không tự có giá trị xác minh.** Tương tự STOMP native `simpUser`, phải phân biệt data do client gửi với metadata do Spring/framework hoặc trusted interceptor tạo.

## 28. Java 17 độc lập: chứng minh session Principal thắng header giả mạo

Đoạn sau **biên dịch/chạy bằng JDK 17**, không cần Spring. Nó mô phỏng một session đã được server xác thực và server-owned room metadata. Các field `claimedUser`, `claimedRole`, `claimedTenant` của client bị bỏ qua hoàn toàn khi phân quyền. Mục tiêu là minh họa trust boundary, không mô phỏng đầy đủ STOMP protocol/JWT signature.

Tạo file `StompSessionTrustDemo.java`:

~~~java
import java.util.Set;

public class StompSessionTrustDemo {
    enum Type { CONNECT, SEND, SUBSCRIBE }

    record VerifiedSession(
            String sessionId,
            String actorKey,
            String tenant,
            Set<String> scopes) { }

    record Frame(
            Type type,
            String destination,
            String claimedUser,
            String claimedRole,
            String claimedTenant) { }

    record Room(
            String id,
            String tenant,
            Set<String> members,
            boolean locked) { }

    static String decide(
            VerifiedSession session, Frame frame, Room room) {

        if (session == null || session.actorKey() == null
                || session.actorKey().isBlank()) {
            return "DENY_NO_SESSION";
        }
        if (frame == null || frame.type() == null) {
            return "DENY_BAD_FRAME";
        }

        // STOMP native claims are deliberately never read.
        if (frame.type() == Type.CONNECT) {
            return "CONNECT_AS:" + session.actorKey();
        }

        if (frame.type() == Type.SUBSCRIBE
                && "/user/queue/alerts".equals(
                    frame.destination())) {
            return "ALLOW";
        }

        if (frame.type() == Type.SEND
                && frame.destination() != null
                && (frame.destination().startsWith("/topic/")
                    || frame.destination().startsWith("/queue/"))) {
            return "DENY_BROKER_SEND";
        }

        String subscribeDest = room == null
                ? "" : "/topic/rooms/" + room.id();
        String sendDest = room == null
                ? "" : "/app/rooms/" + room.id() + "/post";

        boolean subscribe =
                frame.type() == Type.SUBSCRIBE
                && subscribeDest.equals(frame.destination());
        boolean send =
                frame.type() == Type.SEND
                && sendDest.equals(frame.destination());

        if (!subscribe && !send) {
            return "DENY_DESTINATION";
        }

        if (room == null || session.tenant() == null
                || !session.tenant().equals(room.tenant())) {
            return "DENY_TENANT";
        }

        if (!room.members().contains(session.actorKey())) {
            return "DENY_ROOM_MEMBERSHIP";
        }

        if (send && !session.scopes().contains("CHAT_SEND")) {
            return "DENY_SEND_SCOPE";
        }

        if (subscribe && !session.scopes().contains("CHAT_READ")) {
            return "DENY_READ_SCOPE";
        }

        if (send && room.locked()) {
            return "DENY_LOCKED_ROOM";
        }

        return "ALLOW";
    }

    public static void main(String[] args) {
        VerifiedSession an = new VerifiedSession(
                "session-an", "issuerA|an", "north",
                Set.of("CHAT_READ"));

        VerifiedSession carol = new VerifiedSession(
                "session-carol", "issuerA|carol", "north",
                Set.of("CHAT_READ", "CHAT_SEND"));

        Room room = new Room(
                "r7", "north",
                Set.of("issuerA|an", "issuerA|carol"), false);

        Room privateRoom = new Room(
                "r8", "north",
                Set.of("issuerA|carol"), false);

        Room southRoom = new Room(
                "r9", "south",
                Set.of("issuerA|an"), false);

        Frame connectSpoof = new Frame(
                Type.CONNECT, null, "admin", "SUPER_ADMIN", "south");
        Frame subRoom = new Frame(
                Type.SUBSCRIBE, "/topic/rooms/r7",
                "admin", "SUPER_ADMIN", "north");
        Frame subPrivate = new Frame(
                Type.SUBSCRIBE, "/topic/rooms/r8",
                "issuerA|carol", "ADMIN", "north");
        Frame sendRoom = new Frame(
                Type.SEND, "/app/rooms/r7/post",
                "admin", "SUPER_ADMIN", "north");
        Frame subSouth = new Frame(
                Type.SUBSCRIBE, "/topic/rooms/r9",
                "admin", "SUPER_ADMIN", "south");
        Frame brokerSend = new Frame(
                Type.SEND, "/topic/rooms/r7",
                "system", "SUPER_ADMIN", "north");
        Frame userQueue = new Frame(
                Type.SUBSCRIBE, "/user/queue/alerts",
                "admin", "SUPER_ADMIN", "north");
        Frame rawQueue = new Frame(
                Type.SUBSCRIBE, "/queue/alerts-foreign-session",
                "admin", "SUPER_ADMIN", "north");

        System.out.println("connect-spoofed-header="
                + decide(an, connectSpoof, room));
        System.out.println("member-subscribe="
                + decide(an, subRoom, room));
        System.out.println("spoofed-user-subscribe="
                + decide(an, subPrivate, privateRoom));
        System.out.println("spoofed-role-send="
                + decide(an, sendRoom, room));
        System.out.println("real-sender-send="
                + decide(carol, sendRoom, room));
        System.out.println("cross-tenant-subscribe="
                + decide(an, subSouth, southRoom));
        System.out.println("broker-send="
                + decide(carol, brokerSend, room));
        System.out.println("user-queue="
                + decide(an, userQueue, room));
        System.out.println("raw-queue="
                + decide(an, rawQueue, room));
        System.out.println("no-session="
                + decide(null, subRoom, room));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac StompSessionTrustDemo.java
java StompSessionTrustDemo
~~~

Stdout chính xác:

~~~text
connect-spoofed-header=CONNECT_AS:issuerA|an
member-subscribe=ALLOW
spoofed-user-subscribe=DENY_ROOM_MEMBERSHIP
spoofed-role-send=DENY_SEND_SCOPE
real-sender-send=ALLOW
cross-tenant-subscribe=DENY_TENANT
broker-send=DENY_BROKER_SEND
user-queue=ALLOW
raw-queue=DENY_DESTINATION
no-session=DENY_NO_SESSION
~~~

Tại sao kết quả có ý nghĩa:
1. Client khai admin nhưng CONNECT vẫn gắn verified actor `issuerA|an`.
2. An được subscribe r7 vì có READ và membership.
3. An cố giả tên Carol để subscribe r8 vẫn bị từ chối vì session identity không thuộc r8.
4. Native role SUPER_ADMIN không cấp cho An quyền SEND.
5. Carol có `CHAT_SEND` và room membership nên SEND hợp lệ.
6. Room south không cùng tenant với phiên north.
7. Client SEND trực tiếp tới broker topic bị chặn.
8. User destination của chính session được phép; resolved/raw queue khác bị deny.
9. Không có verified session thì không có quyền, dù frame đúng.

**Giới hạn mô hình:** `VerifiedSession` là fixture tin cậy của demo; production phải xác lập nó từ HTTP authentication hoặc token CONNECT được kiểm signature/issuer/audience/expiry. Demo cũng không mô phỏng CSRF, Origin, STOMP header internals, network broker, username collisions hay revocation sau subscribe. Những thứ đó cần Spring integration tests.

## 29. Tại sao không gắn user vào ThreadLocal/singleton?

Một handler singleton có thể xử lý frames từ nhiều WebSocket sessions cùng lúc:

~~~text
Thread T1: frame An -> currentUser = An
Thread T2: frame Bình -> currentUser = Bình
Thread T1: tiếp tục xử lý -> đọc currentUser = Bình
~~~

Nếu bean chứa `private String currentUser`, identity có thể bị lẫn và gửi message bằng actor khác. Với Servlet/Spring Messaging, Spring Security `SecurityContextChannelInterceptor` có thể đồng bộ SecurityContext trên luồng xử lý inbound; app nên dùng Principal/Authentication ở handler thay vì tự tạo mutable global state.

Nếu dùng async task/scheduled worker, cần truyền verified context một cách explicit và không giả định SecurityContext ThreadLocal luôn hiện diện. Với Reactor/WebFlux handler, dùng Reactor Context/ReactiveSecurityContextHolder theo stack, không copy Servlet ThreadLocal approach. Không subscribe hoặc publish sau khi authorization bị deny.

## 30. Error frames, receipts và disclosure

Một client có thể phát `SEND`/`SUBSCRIBE` sai quyền. Spring Messaging/Security có thể trả STOMP ERROR, đóng session hoặc ném AccessDeniedException tùy configuration.

Không gửi cho client:
- Room owner/ACL graph hoặc memberships ngoài quyền.
- Raw JWT, cookies, native CONNECT headers.
- Full Authentication object và security exceptions.
- Internal broker topology hoặc queue/session IDs của user khác.
- Stack traces/DB query chi tiết.

Nên:
- Log reason code nội bộ như `STOMP_SUBSCRIBE_DENIED_ROOM`, `STOMP_SEND_DENIED_SCOPE`.
- Lưu actor alias/session correlation ID có giới hạn và tenant/resource type.
- Giữ messages error tối thiểu.
- Không cho client tự đổi error/receipt ID thành proof.
- Tách authn failure tại CONNECT, message authorization denial và policy backend outage.

Một `receipt` của STOMP là xác nhận xử lý protocol/broker theo semantics liên quan; **không phải bằng chứng** caller có quyền xem mọi nội dung hoặc business transaction đã commit trừ khi contract định nghĩa và kiểm chứng như vậy.

## 31. Kiểm thử với WebSocketStompClient và Spring Security Messaging

Một end-to-end test tốt cần:
1. HTTP handshake với authenticated principal A.
2. STOMP CONNECT mang native `X-User-Id=B`/`X-Role=ADMIN`.
3. SUBSCRIBE private room thuộc B → bị từ chối.
4. SEND tới application destination với scope/membership đúng → được cho.
5. SEND tới broker `/topic/**` → bị từ chối.
6. SUBSCRIBE `/user/queue/alerts` → nhận đúng user/session notifications.
7. SUBSCRIBE resolved queue của user khác → bị chặn.
8. CONNECT thiếu CSRF khi cookie session auth → thất bại theo config.
9. CONNECT token auth sai chữ ký/issuer/audience → thất bại trước message auth.
10. Reconnect với token hết hạn/revoked → không có Principal trusted.

Spring Framework có `WebSocketStompClient`, `StompSessionHandler` và test support cho STOMP. Dùng client test thật để kiểm session principal và interceptor order. Unit tests của `AuthorizationManager<Message<?>>` có thể dựng messages với trusted server headers nhưng **không chứng minh** handshake/token verification. Cần cả hai tầng.

**Mock Principal test ≠ authentication test.** Nếu test tự inject một Authentication có ROLE_ADMIN, nó giúp kiểm permissions, nhưng không chứng minh server từ chối native `X-Role=ADMIN` hoặc JWT sai signature.

## 32. Ma trận kiểm thử bảo mật

| Tình huống | Session Principal | Native header/payload | Kết quả yêu cầu |
|---|---|---|---|
| HTTP session An, CONNECT khai user B | Verified An | `X-User=B` | Vẫn là An |
| STOMP CONNECT có `login=admin` | Chưa xác thực | login/passcode | Không tự thành admin |
| CONNECT Bearer JWT signature sai | Chưa xác thực | Token giả | Reject |
| CONNECT Bearer JWT wrong audience | Chưa xác thực | Token API khác | Reject |
| HTTP Principal An, CONNECT token Bình | Conflicting | Token Bình | Reject hoặc explicit account switch protocol |
| SUBSCRIBE own user queue | Verified An | `/user/queue/alerts` | Allow nếu policy |
| SUBSCRIBE raw queue session của Bình | Verified An | `/queue/alerts-B` | Deny |
| SUBSCRIBE room An member | Verified An | `/topic/rooms/r7` | Allow READ nếu domain policy |
| SUBSCRIBE room người khác | Verified An | `X-IsMember=true` | Deny |
| SEND room An có scope, không SEND grant | Verified An | `X-Role=ADMIN` | Deny |
| SEND với payload `sender=system` | Verified An | Sender giả | Actor vẫn là An, kiểm action |
| SEND `/topic/system/alerts` | Verified An | Broker prefix | Deny |
| SUBSCRIBE tenant south khi chỉ north member | Verified An | `X-Tenant=south` | Deny |
| CONNECT từ Origin ngoài allowlist | Có cookie | Origin giả | Browser-origin policy từ chối |
| CONNECT không CSRF cookie session | Verified An từ HTTP | Thiếu token | Reject khi CSRF enabled |
| SockJS token trong query | Chưa xác thực | URL token | Tránh dùng; không log credential |
| Room ACL revoked sau SUBSCRIBE | Verified An (long-lived) | Existing subscription | Hủy/revalidate theo revocation policy |
| HTTP session/logout bị revoke | WebSocket còn sống | Phiên cũ | Invalidate/disconnect theo policy |
| Broker unavailable / PDP timeout | Có thể verified | Destination | Không fail open |
| Multi-issuer cùng sub | Verified issuerA|123 | User header 123 | Không gán quyền issuerB|123 |
| Malformed destination | Verified An | Encoded/traversal | Reject/default deny |
| Denied SEND có side effect DB | Verified An | Bad room | Không commit, không publish |
| Destination private topic mới chưa có rule | Verified An | Unknown path | DenyAll |

Đối với mỗi denial, test rằng **không gửi event ra broker, không ghi DB/outbox**, không chỉ thấy ERROR frame. Với private topics, test browser B không nhận được messages của A bằng cả direct queue và topic subscriptions.

## 33. Những lỗi thường gặp và cách sửa

**1. Tin `login`/`passcode` trong STOMP CONNECT là Spring authentication.** Mặc định Spring bỏ qua credentials ở STOMP protocol. Dùng HTTP auth hoặc custom verified CONNECT interceptor.

**2. Lấy `X-User-Id`/`sender` từ STOMP headers/body làm Principal.** Client tự sửa được. Dùng server-managed Principal.

**3. Gọi `accessor.setUser(...)` với Authentication tự tạo từ native claims.** Đây là privilege escalation. Chỉ setUser sau verification qua AuthenticationManager/JwtDecoder.

**4. Custom authentication interceptor chạy sau Spring Security.** Authorization nhìn null/old user. Đặt thứ tự trước, theo docs `@Order(Ordered.HIGHEST_PRECEDENCE + 99)`.

**5. Có HTTP handshake Principal nhưng CONNECT token của người khác ghi đè.** Cần reject conflict/explicit re-auth model.

**6. Cho mọi authenticated user SUBSCRIBE `/topic/**`.** Rò phòng riêng. Kiểm READ ACL theo room/tenant.

**7. Cho client SEND trực tiếp vào broker destination `/topic/**`.** Có thể giả system messages. Chặn và chỉ publish từ application handler.

**8. Coi `/user/queue/**` là wildcard queue tự do.** Chặn direct resolved `/queue/**` và kiểm user-specific destinations.

**9. Coi `simpSessionId`/header roomId là proof.** ID là metadata/target, không phải permission.

**10. Không kiểm room tenant từ database.** User có quyền north có thể đoán room south.

**11. Chỉ check scope `CHAT_SEND` mà không check room membership.** Scope chức năng không là object permission.

**12. Dùng role toàn cục từ token thiếu tenant context.** Quyền tenant A có thể lây sang B.

**13. Tin WebSocket tự áp browser Same Origin như fetch.** Cần server-side Origin/CSRF policy.

**14. Bỏ CSRF CONNECT để “dễ kết nối” với cookie auth.** Có thể mở Cross-Site WebSocket Hijacking.

**15. Đưa access token vào SockJS/WebSocket URL.** Dễ leak qua logs/proxy. Chọn kênh authentication khác.

**16. Chỉ authorize ở CONNECT, không authorize SUBSCRIBE/SEND.** Kết nối không cấp mọi quyền.

**17. Revoke room ACL nhưng giữ subscription nhận messages vô hạn.** Cần revocation propagation/disconnect/revalidate.

**18. Kiểm outbound data bằng giả định Spring Security tự chặn clientOutboundChannel.** Framework chủ yếu bảo vệ inbound; bảo vệ subscribe/publish lifecycle.

**19. Cất currentUser ở field singleton.** Rò context giữa sessions. Dùng Principal mỗi message.

**20. Test với mockUser rồi tin native spoofing đã được ngăn.** Cần integration test handshake, CONNECT và headers thật.

## 34. Checklist triển khai an toàn

- [ ] Xác định stack đang là Spring Servlet STOMP WebSocket (không nhầm WebFlux/raw WebSocket).
- [ ] HTTP handshake được bảo vệ, hoặc STOMP CONNECT có custom trusted token authentication.
- [ ] Principal được lấy từ HTTP-authenticated session hoặc verified AuthenticationManager; không lấy từ native headers.
- [ ] Nếu CONNECT token auth, authentication interceptor chạy trước security message authorization.
- [ ] Nếu cả HTTP Principal và CONNECT token cùng có, conflict được xử lý rõ.
- [ ] JWT/opaque token được kiểm signature/issuer/audience/exp/typ/status theo contract.
- [ ] Native `login`, `passcode`, `X-User`, `X-Role`, `X-Tenant` không cấp quyền.
- [ ] Cookie/Origin/CSRF CONNECT bảo vệ browser flow, SockJS được test riêng.
- [ ] `@EnableWebSocketSecurity` và `AuthorizationManager<Message<?>>` cấu hình đúng version.
- [ ] Rule phân biệt SEND/MESSAGE và SUBSCRIBE, fallback deny.
- [ ] Client không SEND trực tiếp vào broker prefixes /topic, /queue.
- [ ] Client không SUBSCRIBE raw resolved queues ngoài user destination.
- [ ] User destination `/user/queue/**` chỉ expose dữ liệu đúng identity/authorization.
- [ ] Private topics có custom policy theo room/tenant READ membership.
- [ ] SEND handlers kiểm permission trên resource thật trước khi publish.
- [ ] Payload `sender`, `from`, `owner`, `isAdmin` bị bỏ qua làm identity proof.
- [ ] Canonical principal key phân biệt issuer + subject khi cần.
- [ ] Permission revoke/session expiry có propagation/lifecycle SLA rõ.
- [ ] Không cất mutable user/tenant vào singleton, không cache cross-session Principal.
- [ ] Có test spoofed native headers, raw queue, direct topic SEND, wrong-room SUBSCRIBE.
- [ ] Có test token CONNECT invalid, interceptor order, CSRF/Origin, multi-session.
- [ ] Denied SEND/SUBSCRIBE không có DB/broker side effects hoặc data leak.
- [ ] Structured audit không log token, cookies hoặc private message payload trái quyền.

**Kết luận:** Principal của WebSocket/STOMP session phải được hình thành từ **authentication thật**, thông thường ở HTTP handshake hoặc qua một `ChannelInterceptor` xác minh token ở STOMP CONNECT. Native headers do client gửi chỉ là dữ liệu; `login=admin`, `X-Role=ADMIN` hoặc `sender=system` **không làm principal đổi**. Sau đó, Spring Security Messaging giúp kiểm inbound SEND/SUBSCRIBE, nhưng quyền đọc/ghi từng room và tenant, việc publish tới broker, user destinations và revocation của phiên dài vẫn phải được ứng dụng bảo vệ có chủ đích.

## Tài liệu tham khảo chính thức

- [Spring Security — WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html): HTTP Principal inheritance, `@EnableWebSocketSecurity`, `AuthorizationManager<Message<?>>`, inbound security, broker prefixes, CSRF CONNECT.
- [Spring Security 6.5 — WebSocket Security](https://docs.spring.io/spring-security/reference/6.5/servlet/integrations/websocket.html): semantics cho phiên bản 6.x.
- [Spring Security — MessageMatcherDelegatingAuthorizationManager.Builder Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/messaging/access/intercept/MessageMatcherDelegatingAuthorizationManager.Builder.html): `simpMessageDestMatchers`, `simpSubscribeDestMatchers`, `nullDestMatcher`, `anyMessage`.
- [Spring Framework — STOMP Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html): Principal từ HTTP session, STOMP login/passcode mặc định không được dùng.
- [Spring Framework — STOMP Token Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html): custom CONNECT token auth `ChannelInterceptor` và order trước Spring Security.
- [Spring Framework — STOMP Authorization](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html): message authorization.
- [Spring Framework — STOMP User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html): `/user/`, user session routing và `@SendToUser`.
- [Spring Framework — STOMP Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html): `@MessageMapping`, Principal và argument resolution.
- [Spring Framework — STOMP WebSocket Scope](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/scope.html): session attributes, websocket-scoped beans.
- [Spring Framework — Broker Relay](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html): broker/system client credentials khác user auth.
- [Spring Framework — WebSocket Allowed Origins](https://docs.spring.io/spring-framework/reference/web/websocket/server.html): Origin restrictions và browser semantics.
