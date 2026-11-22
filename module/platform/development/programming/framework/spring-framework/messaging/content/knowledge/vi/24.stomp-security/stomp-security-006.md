# Ngăn giả mạo người dùng, tenant và destination trong STOMP

## Mục tiêu

Trong ứng dụng Spring WebSocket dùng STOMP, client có thể gửi payload, native headers, destination và các lệnh SEND hoặc SUBSCRIBE. Những dữ liệu này đến từ phía client nên có thể bị sửa bằng trình duyệt, script hoặc một STOMP client khác. Nếu server tin các trường như senderId, userId, tenantId, role hoặc destination do client khai báo, người dùng có thể giả mạo danh tính, truy cập dữ liệu tenant khác hoặc gửi message giả danh hệ thống.

Bảo mật STOMP cần thực hiện ở nhiều lớp:

1. **Authentication** xác định ai đang kết nối và gắn danh tính đã xác thực vào Principal.
2. **Message authorization** quyết định Principal có được SEND hoặc SUBSCRIBE vào destination cụ thể hay không.
3. **Business authorization** kiểm tra người dùng có quyền thao tác trên đúng tenant, room, order hoặc resource hay không.
4. **Server-side routing** để server quyết định destination phát ra, không nhận destination đích tùy ý từ payload của client.

Không có một matcher destination nào thay thế được kiểm tra quyền trên dữ liệu nghiệp vụ. Destination cho biết message đi đâu; nó không chứng minh người gửi có quyền truy cập tài nguyên ở đó.

## 1. Những giá trị client có thể giả mạo

Hãy coi mọi thông tin do client gửi là dữ liệu đầu vào chưa đáng tin, bao gồm:

| Dữ liệu | Ví dụ giả mạo | Rủi ro nếu server tin trực tiếp |
|---|---|---|
| senderId hoặc userId trong payload | Gửi senderId của quản trị viên | Tin nhắn hoặc hành động bị gán cho người khác |
| role hoặc isAdmin | Gửi role=ADMIN | Vượt quyền |
| tenantId | Đổi tenantId từ tenant hiện tại sang tenant khác | Đọc hoặc ghi chéo dữ liệu tenant |
| destination | Gửi SEND trực tiếp tới /topic/system/notifications | Giả danh message do server phát |
| native header user hoặc tenant | Tự thêm userId, tenantId, role vào CONNECT hoặc SEND | Ghi đè ngữ cảnh bảo mật nếu server xử lý sai |
| recipient hoặc targetUserId | Chọn ID của người khác | Gửi dữ liệu tới người nhận không được phép |
| roomId, orderId hoặc resourceId | Thay ID trong destination hoặc payload | Truy cập tài nguyên ngoài phạm vi |

Ngay cả khi client dùng giao diện chính thức, người dùng vẫn có thể sửa frame STOMP. Kiểm tra dữ liệu ở JavaScript chỉ cải thiện trải nghiệm; quyết định bảo mật phải nằm ở server.

## 2. Xác thực ở HTTP handshake và dùng Principal của Spring

Với ứng dụng có đăng nhập HTTP bằng Spring Security, cách đơn giản nhất là xác thực WebSocket handshake bằng cùng cơ chế bảo mật HTTP. Mỗi STOMP session sau đó được gắn với Principal của request đã xác thực.

Luồng cơ bản:

1. Người dùng đăng nhập qua HTTP.
2. Spring Security xác thực request và lưu Authentication trong SecurityContext.
3. Trình duyệt mở WebSocket handshake bằng session cookie hợp lệ.
4. Spring liên kết Principal của HTTP request với WebSocket session.
5. Các STOMP message tiếp theo trên session mang user đã xác thực đó.

Trong handler, nhận Principal trực tiếp:

~~~java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

@Controller
public class AccountController {

    @MessageMapping("/account/ping")
    public String ping(Principal principal) {
        if (principal == null) {
            throw new IllegalStateException("Phiên STOMP chưa được xác thực");
        }

        return "Xin chào " + principal.getName();
    }
}
~~~

Principal là danh tính do server xác lập qua authentication. Không thay thế nó bằng senderId trong payload, userId trong native header hoặc tên người dùng do client tự khai báo.

STOMP có header login và passcode trên frame CONNECT. Với STOMP over WebSocket trong Spring, mặc định Spring bỏ qua các header này để xác thực và kỳ vọng danh tính đã được xác thực ở tầng HTTP. Không được mặc định rằng việc gửi login hoặc passcode trong CONNECT sẽ tự tạo một Principal đáng tin cậy.

## 3. Xác thực token tại STOMP CONNECT khi không dùng cookie session

Một số ứng dụng SPA, mobile hoặc API stateless dùng access token thay vì HTTP session. Trình duyệt WebSocket API không cho tùy ý thêm custom HTTP header vào handshake. Spring hỗ trợ cách xác thực token ở tầng STOMP:

1. Client gửi token trong native header của frame CONNECT.
2. Server lấy header đó trong ChannelInterceptor.
3. Server xác minh chữ ký, issuer, audience, thời hạn và các claim cần thiết.
4. Server tạo Authentication từ danh tính đã xác minh.
5. Server gọi setUser trên StompHeaderAccessor.
6. Spring gắn user đó với các message tiếp theo trong cùng session.

Ví dụ client dùng thư viện STOMP:

~~~javascript
stompClient.connect(
    { Authorization: "Bearer " + accessToken },
    onConnected,
    onError
);
~~~

Đây là ví dụ client minh họa; tên phương thức có thể khác tùy phiên bản thư viện STOMP. Không nên đưa token vào query string của WebSocket URL vì URL có thể xuất hiện trong access log, proxy log hoặc hệ thống theo dõi.

Ví dụ interceptor phía server:

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageHeaderAccessor;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public class StompConnectAuthenticationInterceptor
        implements ChannelInterceptor {

    private final TokenAuthenticationService tokenAuthenticationService;

    public StompConnectAuthenticationInterceptor(
            TokenAuthenticationService tokenAuthenticationService) {
        this.tokenAuthenticationService = tokenAuthenticationService;
    }

    @Override
    public Message<?> preSend(Message<?> message, MessageChannel channel) {
        StompHeaderAccessor accessor =
                MessageHeaderAccessor.getAccessor(
                        message, StompHeaderAccessor.class);

        if (accessor == null) {
            return message;
        }

        if (StompCommand.CONNECT.equals(accessor.getCommand())) {
            String authorization =
                    accessor.getFirstNativeHeader("Authorization");

            Authentication authentication =
                    tokenAuthenticationService.authenticateBearer(authorization);

            accessor.setUser(authentication);
        }

        return message;
    }
}
~~~

TokenAuthenticationService là service do ứng dụng triển khai. Nó phải từ chối token thiếu, sai chữ ký, hết hạn, sai issuer hoặc audience, bị thu hồi nếu có cơ chế thu hồi, và token không có quyền truy cập ứng dụng. Phương thức authenticateBearer chỉ trả về Authentication sau khi xác minh thành công; không được tạo Authentication chỉ từ chuỗi userId client gửi lên.

Đăng ký interceptor trước interceptor phân quyền của Spring Security:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.messaging.simp.config.ChannelRegistration;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@Order(Ordered.HIGHEST_PRECEDENCE + 99)
public class StompAuthenticationConfig
        implements WebSocketMessageBrokerConfigurer {

    private final StompConnectAuthenticationInterceptor authenticationInterceptor;

    public StompAuthenticationConfig(
            StompConnectAuthenticationInterceptor authenticationInterceptor) {
        this.authenticationInterceptor = authenticationInterceptor;
    }

    @Override
    public void configureClientInboundChannel(ChannelRegistration registration) {
        registration.interceptors(authenticationInterceptor);
    }
}
~~~

Theo hướng dẫn Spring, interceptor xác thực cần chạy trước interceptor authorization của Spring Security. Tách cấu hình này thành một WebSocketMessageBrokerConfigurer riêng với thứ tự ưu tiên phù hợp giúp bảo đảm Authentication đã được gắn trước khi các rule phân quyền kiểm tra message.

Nếu dùng HTTP session authentication, không cần thêm interceptor token này. Chỉ chọn một cơ chế xác thực phù hợp với kiến trúc của ứng dụng và tránh vô tình cho phép một kết nối chưa xác thực đi qua đường dự phòng.

## 4. Phân quyền SEND và SUBSCRIBE bằng Spring Security

Xác thực chỉ trả lời câu hỏi ai đang kết nối. Spring Security WebSocket authorization quyết định người đó được gửi message hoặc đăng ký nhận message ở destination nào.

Bật hỗ trợ message security bằng @EnableWebSocketSecurity và khai báo AuthorizationManager:

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
public class StompAuthorizationConfig {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        messages
            .nullDestMatcher().authenticated()
            .simpDestMatchers("/app/**").hasRole("USER")
            .simpSubscribeDestMatchers("/topic/public/**").authenticated()
            .simpSubscribeDestMatchers("/user/queue/**").hasRole("USER")
            .simpDestMatchers("/topic/**", "/queue/**").denyAll()
            .simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()
            .anyMessage().denyAll();

        return messages.build();
    }
}
~~~

Đây là chính sách minh họa cho ứng dụng yêu cầu mọi session phải được xác thực. Rule hasRole("USER") yêu cầu Authentication có authority ROLE_USER:

- Message không có destination, chẳng hạn các frame điều khiển của session, yêu cầu người dùng đã xác thực.
- SEND tới /app/** được phép với user có role USER.
- SUBSCRIBE tới /topic/public/** chỉ được phép sau khi xác thực.
- SUBSCRIBE tới /user/queue/** yêu cầu role USER.
- Client không được SEND trực tiếp tới /topic/** hoặc /queue/**.
- Các kiểu MESSAGE và SUBSCRIBE không khớp rule cho phép sẽ bị từ chối.
- Các message còn lại cũng bị từ chối theo mặc định.

Điểm quan trọng là **MESSAGE và SUBSCRIBE là hai quyền khác nhau**. Client có thể được phép đăng ký nhận một topic nhưng không được phép gửi message vào topic đó. Nếu cho client SEND trực tiếp tới topic hệ thống, client có thể giả danh message do server phát. Spring Security khuyến nghị chặn MESSAGE từ client tới các broker destination như /topic/** và /queue/**.

Tương tự, không nên cho client SUBSCRIBE tùy ý vào các queue nội bộ. Đặc biệt, không cho client subscribe trực tiếp vào queue vật lý của broker nếu điều đó có thể làm lộ message của người dùng khác. Dùng user destination hoặc các destination đã được kiểm soát.

Thứ tự matcher rất quan trọng: các rule cụ thể phải đứng trước rule tổng quát. Ví dụ rule cho phép /topic/public/** cần xuất hiện trước rule từ chối các MESSAGE hoặc SUBSCRIBE không khớp.

Với một ứng dụng cho phép người dùng anonymous kết nối, cần thiết kế lại rule CONNECT và CSRF một cách có chủ đích. Không nên đơn giản đổi toàn bộ rule thành permitAll vì sẽ làm mất lớp kiểm soát message.

## 5. Không để client giả danh message do hệ thống phát

Giả sử server phát thông báo bảo trì tới /topic/system/notifications. Client có thể đăng ký SUBSCRIBE để nhận thông báo, nhưng không được tự gửi SEND tới destination đó.

Một chính sách an toàn thường có dạng:

| Thao tác | Destination | Quyền |
|---|---|---|
| Client SEND | /app/notifications | Được phép nếu đã xác thực và vượt qua kiểm tra nghiệp vụ |
| Client SUBSCRIBE | /topic/system/notifications | Có thể cho phép user đã xác thực |
| Client SEND | /topic/system/notifications | Từ chối |
| Client SEND | /queue/** | Từ chối theo mặc định |
| Client SUBSCRIBE | Queue vật lý nội bộ của broker | Từ chối |
| Server SEND | /topic/system/notifications | Được phép theo quyền nội bộ của server |

Server chỉ phát event hệ thống sau khi tự quyết định nội dung và destination:

~~~java
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class SystemNotificationPublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public SystemNotificationPublisher(
            SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publishMaintenanceNotice(String message) {
        messagingTemplate.convertAndSend(
                "/topic/system/notifications",
                new SystemNotification(message)
        );
    }
}

record SystemNotification(String message) {}
~~~

Client không có quyền gọi trực tiếp phương thức server này. Message chỉ được phát bởi thành phần server sau khi đã áp dụng chính sách nghiệp vụ.

Không dùng một destination nhận từ payload, ví dụ command.getDestination(), rồi chuyển thẳng vào convertAndSend. Nếu cần chọn destination theo nghiệp vụ, server phải ánh xạ một lựa chọn đã được kiểm tra sang destination cố định hoặc destination được xây dựng từ ID đã xác thực quyền truy cập.

## 6. Dùng user destination để gửi message riêng tư

Khi gửi phản hồi riêng cho người dùng hiện tại, lấy tên người nhận từ Principal hoặc từ một đối tượng Authentication đã được xác minh. Không nhận recipient username do client gửi rồi tin trực tiếp.

Ví dụ server gửi phản hồi riêng:

~~~java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Controller;

@Controller
public class PrivateMessageController {

    private final SimpMessagingTemplate messagingTemplate;

    public PrivateMessageController(
            SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    @MessageMapping("/private/ping")
    public void ping(Principal principal) {
        String authenticatedUser = principal.getName();

        messagingTemplate.convertAndSendToUser(
                authenticatedUser,
                "/queue/reply",
                new PrivateReply("Pong")
        );
    }
}

record PrivateReply(String message) {}
~~~

Client subscribe vào /user/queue/reply. Spring phân giải user destination thành destination riêng cho user hoặc session tương ứng. Client không cần biết queue vật lý phía broker.

Nếu server cần gửi tới một user khác, recipient phải được lấy từ dữ liệu nghiệp vụ đã kiểm tra. Ví dụ một service kiểm tra user A có quyền nhắn cho user B trong cùng cuộc hội thoại rồi mới gọi convertAndSendToUser. Không dùng username do client cung cấp như bằng chứng rằng người nhận đó hợp lệ.

## 7. Ngăn giả mạo tenant

Trong hệ thống multi-tenant, mỗi request phải được ràng buộc với tenant mà người dùng đã được cấp quyền. Tenant ID có thể xuất hiện trong URL, STOMP destination, payload hoặc JWT claim, nhưng không phải mọi vị trí đều có độ tin cậy như nhau.

Các quy tắc cần giữ:

1. Lấy danh tính người dùng từ Principal đã xác thực.
2. Xác minh người dùng có membership hoặc quyền truy cập tenant được yêu cầu.
3. Kiểm tra resource thuộc tenant đó trước khi đọc hoặc thay đổi.
4. Đưa tenant ID đã được xác minh vào mọi truy vấn database.
5. Tạo destination phát ra từ tenant và resource đã được server xác nhận.
6. Không tin tenantId do client gửi trong payload hoặc native header.

Ví dụ payload có thể chứa các trường mà client cố tình giả mạo:

~~~java
public record ChatCommand(
        String senderId,
        String tenantId,
        String text
) {}
~~~

Handler không sử dụng senderId hoặc tenantId từ payload. Nó lấy user từ Principal, xác minh membership của tenant được chọn, xác minh room thuộc tenant và tạo event mới bằng dữ liệu server đã xác nhận:

~~~java
import java.security.Principal;

import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Controller;

@Controller
public class TenantChatController {

    private final TenantAccessService tenantAccessService;
    private final RoomAccessService roomAccessService;
    private final SimpMessagingTemplate messagingTemplate;

    public TenantChatController(
            TenantAccessService tenantAccessService,
            RoomAccessService roomAccessService,
            SimpMessagingTemplate messagingTemplate) {
        this.tenantAccessService = tenantAccessService;
        this.roomAccessService = roomAccessService;
        this.messagingTemplate = messagingTemplate;
    }

    @MessageMapping("/tenants/{tenantId}/rooms/{roomId}/messages")
    public void send(
            @DestinationVariable("tenantId") String tenantId,
            @DestinationVariable("roomId") String roomId,
            ChatCommand command,
            Principal principal) {

        String userId = principal.getName();

        Tenant tenant =
                tenantAccessService.requireMembership(userId, tenantId);

        Room room =
                roomAccessService.requireCanPost(userId, tenant.id(), roomId);

        ChatEvent event = new ChatEvent(
                userId,
                tenant.id(),
                room.id(),
                command.text()
        );

        String destination =
                "/topic/tenants/" + tenant.id() + "/rooms/" + room.id();

        messagingTemplate.convertAndSend(destination, event);
    }
}

record ChatEvent(
        String senderId,
        String tenantId,
        String roomId,
        String text
) {}
~~~

TenantAccessService và RoomAccessService là service nghiệp vụ do ứng dụng triển khai. Chúng phải từ chối nếu user không thuộc tenant hoặc room không thuộc tenant đã xác minh. Nếu Principal null, handler phải bị từ chối ở lớp authentication/authorization trước khi chạy.

Trong ví dụ, tenantId trên destination đầu vào chỉ là **tenant được client yêu cầu truy cập**. Nó chưa phải tenant hợp lệ cho đến khi tenantAccessService xác minh membership. Tương tự, roomId phải được xác minh thuộc tenant đó. Server tạo event từ userId, tenant.id() và room.id() đã xác minh; các trường senderId và tenantId trong payload bị bỏ qua.

### Tenant scope phải đi vào truy vấn dữ liệu

Không nên chỉ kiểm tra tenant ở controller rồi sau đó gọi repository bằng resource ID toàn cục. Mỗi truy vấn đọc, sửa hoặc xóa phải ràng buộc cả tenant:

~~~java
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface RoomRepository extends JpaRepository<Room, String> {

    Optional<Room> findByIdAndTenantId(String roomId, String tenantId);
}
~~~

Service sử dụng truy vấn có tenant scope:

~~~java
public Room requireCanPost(
        String userId,
        String tenantId,
        String roomId) {

    membershipService.requireMember(userId, tenantId);

    Room room = roomRepository
            .findByIdAndTenantId(roomId, tenantId)
            .orElseThrow(ResourceNotFoundException::new);

    permissionService.requireCanPost(userId, room);

    return room;
}
~~~

Đây là ví dụ minh họa repository/service; tên entity và exception phụ thuộc ứng dụng. Việc query theo cặp ID và tenant giúp tránh lỗi truy cập chéo tenant do quên điều kiện lọc.

Nếu tenant ID nằm trong JWT, chỉ sử dụng claim sau khi token đã được xác minh. Với người dùng có thể tham gia nhiều tenant hoặc membership có thể bị thu hồi, cần kiểm tra membership hiện tại hoặc dùng một cache quyền có cơ chế hết hạn và invalidation phù hợp. Claim cũ trong token không nên duy trì quyền đã bị thu hồi vô thời hạn.

## 8. Bảo vệ tenant topic khi SUBSCRIBE

Kiểm tra membership trong handler SEND chưa đủ. Client có thể không gửi message nhưng vẫn SUBSCRIBE vào topic của tenant khác để nghe dữ liệu.

Với topic có dạng /topic/tenants/{tenantId}/..., server cần kiểm tra quyền ngay tại thời điểm SUBSCRIBE. Có thể dùng custom AuthorizationManager hoặc ChannelInterceptor để:

1. Đọc destination của frame SUBSCRIBE.
2. Lấy Principal đã xác thực từ message.
3. Phân tích tenant ID theo một mẫu destination được kiểm soát.
4. Kiểm tra membership của Principal trong tenant đó.
5. Từ chối subscription nếu tenant không hợp lệ hoặc người dùng không có quyền.

Rule pattern tổng quát như /topic/** chỉ kiểm tra tiền tố. Nó không tự biết tenant nào thuộc người dùng nào. Cần một bước authorization động dựa trên Principal và tenant ID trong destination.

Nếu không cần broadcast theo tenant, cân nhắc dùng /user/queue/** để gửi riêng theo Principal. Cách này giảm số nơi client có thể tự chọn tenant destination. Nếu có tenant topic, hãy giới hạn pattern và xác minh quyền SUBSCRIBE cho từng tenant.

Không nên cho phép SUBSCRIBE vào queue vật lý như /queue/user/messages-123 hoặc destination nội bộ do broker tạo ra. User destination là giao diện logic dành cho client; queue vật lý phải được quản lý bởi Spring và broker.

## 9. Destination là địa chỉ định tuyến, không phải bằng chứng quyền

Các prefix thường gặp có ý nghĩa khác nhau:

| Prefix | Mục đích | Chính sách thường dùng |
|---|---|---|
| /app/** | Message từ client đi vào controller | Cho phép SEND sau khi xác thực và kiểm tra nghiệp vụ |
| /topic/** | Kênh publish/subscribe broadcast | Cho phép SUBSCRIBE có kiểm soát; từ chối SEND từ client |
| /queue/** | Queue broker | Hạn chế chặt; thường từ chối client SEND và SUBSCRIBE trực tiếp |
| /user/** | Destination logic dành cho một user | Cho phép subscribe vào queue riêng theo Principal |

Một destination an toàn không chỉ phụ thuộc vào prefix. Ví dụ /app/orders/{id}/cancel vẫn cần xác minh người dùng có quyền hủy đúng order. Matcher /app/** chỉ bảo đảm message đi qua vùng controller được phép; nó không tự kiểm tra ownership của order.

Khi xây destination từ dữ liệu client:

- Không nối chuỗi từ một destination tùy ý trong payload.
- Không dùng tenant ID chưa được xác minh.
- Không cho phép client chọn prefix /topic, /queue hoặc /user tùy ý.
- Chuẩn hóa và kiểm tra ID theo định dạng dự kiến.
- Xác minh resource thuộc tenant và người dùng có quyền thực hiện thao tác.
- Ưu tiên một bảng ánh xạ từ loại sự kiện hợp lệ sang destination cố định.

## 10. CSRF, Origin và bảo vệ handshake

Với cấu hình Spring Security WebSocket bằng @EnableWebSocketSecurity, inbound STOMP CONNECT yêu cầu CSRF token hợp lệ. Điều này bảo vệ ứng dụng trước một số kiểu tấn công cross-site khi trình duyệt tự gửi session cookie của người dùng tới WebSocket endpoint.

Các lưu ý:

- Dùng HTTPS và WSS trong môi trường production.
- Giới hạn allowed origins của WebSocket endpoint theo danh sách domain thực sự được phép.
- Giữ CSRF protection cho STOMP CONNECT khi dùng cookie-based session.
- Nếu dùng token trong STOMP CONNECT, thiết kế riêng cách lấy và gửi CSRF token theo cấu hình Spring Security.
- Không tắt CSRF toàn cục chỉ để làm WebSocket hoạt động.
- Không coi kiểm tra Origin là authentication; client không trình duyệt có thể tự tạo header này.
- Không ghi token, cookie, session ID hoặc payload nhạy cảm vào log.

CORS/Origin allowlist giúp giới hạn trang web được phép mở kết nối từ trình duyệt, nhưng không thay thế xác thực hoặc authorization. Một request có Origin hợp lệ vẫn phải qua kiểm tra Principal, destination và quyền tenant.

## 11. Những lỗi bảo mật thường gặp

| Lỗi | Vì sao nguy hiểm | Cách sửa |
|---|---|---|
| Lấy senderId từ payload | Client có thể giả mạo người khác | Lấy từ Principal |
| Tin tenantId từ payload | Client có thể chuyển tenant | Kiểm tra membership và scope mọi truy vấn |
| Cho client SEND vào /topic/** | Có thể giả danh message hệ thống | Chặn MESSAGE tới broker prefixes |
| Cho client SUBSCRIBE vào /queue/** | Có thể nghe queue của user khác | Dùng /user/queue/** và chặn queue vật lý |
| Chỉ kiểm tra role ở frontend | Client có thể bỏ qua giao diện | Authorization tại Spring Security và service |
| Chỉ bảo vệ CONNECT | User hợp lệ vẫn có thể gọi destination ngoài quyền | Phân quyền từng MESSAGE và SUBSCRIBE |
| Chỉ kiểm tra tenant ở controller | Repository có thể đọc resource tenant khác | Scope query theo tenant ở tầng dữ liệu |
| Tin JWT claim mà chưa xác minh | Token có thể giả, hết hạn hoặc sai audience | Verify signature, issuer, audience, expiry |
| Gửi token qua query string | Token có thể lọt vào access log | Gửi token trong CONNECT header hoặc cơ chế HTTP auth phù hợp |
| Cho phép mọi destination đã xác thực | User có thể truy cập chức năng ngoài quyền | Allowlist destination và deny-by-default |

## 12. Kiểm thử chống giả mạo

Bài kiểm thử nên chứng minh server từ chối các frame giả mạo, không chỉ xác minh trường hợp hợp lệ.

| Kịch bản | Kết quả mong đợi |
|---|---|
| User A gửi payload có senderId của User B | Event phát ra vẫn lấy senderId từ Principal A |
| User A gửi tenantId của tenant B mà không có membership | Từ chối trước khi đọc hoặc ghi resource |
| User A sửa tenantId trong native header | Không làm thay đổi tenant context đã xác minh |
| Client SEND trực tiếp tới /topic/system/notifications | Bị Spring Security từ chối |
| Client SUBSCRIBE vào /queue vật lý | Bị từ chối |
| User A SUBSCRIBE tenant topic của tenant B | Custom tenant authorization từ chối |
| Client gửi JWT sai chữ ký hoặc hết hạn | CONNECT bị từ chối |
| User mất membership sau khi token được cấp | Quyền bị thu hồi theo chính sách membership hiện tại |
| User truy cập room ID thuộc tenant khác | Truy vấn có tenant scope không tìm thấy resource hoặc trả lỗi truy cập |
| Client thay destination từ /app sang /topic | SEND bị từ chối bởi matcher |
| Client gửi frame CONNECT thiếu CSRF token khi dùng cookie session | CONNECT bị từ chối |

Nên kiểm thử cả lớp matcher Spring Security, custom tenant authorization và service/repository. Unit test cho service có thể dùng Principal giả lập để xác minh việc kiểm tra membership. Integration test nên gửi STOMP frame thật qua endpoint và xác nhận server từ chối các thao tác trái phép.

## 13. Checklist bảo mật STOMP

- [ ] Principal được tạo từ HTTP authentication hoặc token đã xác minh.
- [ ] Không tin senderId, userId, role hoặc tenantId do client gửi.
- [ ] Nếu xác thực token ở CONNECT, interceptor chạy trước Spring Security authorization.
- [ ] Mọi SEND tới /app/** được kiểm tra quyền nghiệp vụ.
- [ ] Client không thể SEND trực tiếp tới /topic/** hoặc /queue/**.
- [ ] Client chỉ SUBSCRIBE vào destination được allowlist.
- [ ] Tenant topic có authorization động theo Principal và tenant ID.
- [ ] Mọi repository query được scope theo tenant đã xác minh.
- [ ] User destination được gửi từ server dựa trên Principal.
- [ ] Không cho client subscribe queue vật lý của broker.
- [ ] CONNECT có CSRF protection khi dùng cookie session.
- [ ] Allowed origins được giới hạn; Origin không được dùng thay authentication.
- [ ] Token, cookie, session và payload nhạy cảm không xuất hiện trong log.
- [ ] Có test cho giả mạo user, tenant, destination và truy cập chéo tenant.

## Tài liệu tham khảo

- [Spring Framework — Authentication for STOMP over WebSocket](https://docs.spring.io/spring/reference/web/websocket/stomp/authentication.html)
- [Spring Framework — Token Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html)
- [Spring Framework — STOMP Authorization](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html)
- [Spring Security — WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html)
- [Spring Framework — STOMP Interception](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/interceptors.html)
