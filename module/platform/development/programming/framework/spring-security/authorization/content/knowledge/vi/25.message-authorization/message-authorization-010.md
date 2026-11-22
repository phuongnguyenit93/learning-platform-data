# Kiểm thử giả mạo người gửi, đăng ký sai kênh và thông điệp ngoài quy tắc

> **Chủ đề:** Spring Security – phân quyền thông điệp (STOMP over WebSocket, phía Servlet). Bài thực hành kiểm thử **luồng đi vào ứng dụng**: danh tính người gửi, quyền `SUBSCRIBE` và quyền `SEND` theo loại thông điệp/đích đến. Ví dụ dùng Java 17+, Spring Boot với Spring WebSocket, Spring Security Messaging và JUnit 5.

## 1. Mục tiêu và mô hình đe dọa

Sau bài này, bạn cần chứng minh bằng kiểm thử rằng:

1. Người dùng A không thể tự nhận mình là người dùng B hoặc quản trị viên bằng cách sửa trường `sender`/`from` trong payload hay tự đặt header STOMP.
2. Người dùng chỉ đăng ký (`SUBSCRIBE`) đúng những kênh được cho phép; biết tên destination hoặc đăng nhập thành công **không đồng nghĩa** với quyền xem dữ liệu.
3. Client không thể gửi (`SEND`) trực tiếp tới kênh broker (`/topic/**`, `/queue/**`) để giả mạo thông báo hệ thống hoặc bỏ qua xử lý nghiệp vụ.
4. Mọi cặp **loại thông điệp + destination** ngoài danh sách cho phép bị từ chối theo mặc định.
5. Phép kiểm thử âm tính kiểm tra cả **không phát sinh tác dụng phụ**: không lưu dữ liệu, không phát thông điệp, không rò rỉ payload cho người nhận.

Giả sử hệ thống chat có các tuyến sau:

| Hành động từ client | Destination | Quy tắc |
| --- | --- | --- |
| `SEND` tin nhắn phòng | `/app/rooms/{roomId}/send` | Đăng nhập, thực sự là thành viên phòng; tác giả phải lấy từ `Principal` |
| `SUBSCRIBE` tin nhắn phòng | `/topic/rooms/{roomId}` | Đăng nhập và là thành viên chính phòng đó |
| `SUBSCRIBE` thông báo chung | `/topic/announcements` | Đã đăng nhập |
| `SUBSCRIBE` lỗi cá nhân | `/user/queue/errors` | Đã đăng nhập; dùng user destination của Spring |
| `SEND` thông báo quản trị | `/app/admin/announce` | Có `ROLE_ADMIN` |
| Bất kỳ `SEND` đến `/topic/**`, `/queue/**` hoặc `/user/**` | Broker/user destination | Từ chối |
| `SUBSCRIBE` kênh nội bộ/không có trong chính sách | Ví dụ `/topic/internal`, `/queue/private` | Từ chối |

**Phân biệt quan trọng:** STOMP client gửi frame `SEND`, được biểu diễn thành `SimpMessageType.MESSAGE` trong lớp Spring Messaging; frame `SUBSCRIBE` là `SimpMessageType.SUBSCRIBE`. `MESSAGE` do server gửi cho subscriber là chiều đi ra, không phải một lệnh mà client được phép tự phát tới broker.

```text
Client ──HTTP handshake (/ws)──> WebSocket session với Principal xác thực
       ──STOMP CONNECT────────> kiểm tra kết nối và CSRF STOMP khi bật mặc định
       ──SEND/SUBSCRIBE───────> clientInboundChannel
                                 ├─ xác thực/ngữ cảnh danh tính
                                 ├─ AuthorizationManager: loại + destination + quyền phòng
                                 └─ controller hoặc broker nếu hợp lệ
Server ──brokerChannel / clientOutboundChannel──> người đăng ký hợp lệ
```

Spring Security bảo vệ chủ yếu **`clientInboundChannel`**, không tự kiểm tra từng thông điệp đi ra. Vì vậy phải chặn đăng ký sai kênh ở đầu vào; một bộ lọc HTTP cho `/ws` không thể thay thế chính sách này.

## 2. Ba lỗi bảo mật cần mô phỏng

### 2.1. Giả mạo người gửi

Client hợp lệ của Alice gửi:

```json
{"sender":"admin","text":"Phòng đã được mở khóa"}
```

Nếu server chuyển tiếp nguyên `sender` từ JSON, người nhận có thể tin rằng thông báo đến từ `admin`. Các biến thể cùng bản chất: gửi `fromUserId: "bob"`, đặt header STOMP `user: admin`, chỉnh `login`/`passcode` trong `CONNECT` hoặc đổi `roomId` để gửi thay phòng khác. Với STOMP over WebSocket của Spring, header `login` và `passcode` không tự động thay thế danh tính đã được xác thực qua HTTP; ứng dụng cũng không được tin header tùy ý do client tự khai.

**Bất biến đúng:** `stored.sender == principal.getName()` và `broadcast.sender == principal.getName()`. Nguồn danh tính phải là phiên xác thực hợp lệ do server gắn vào session (hoặc xác thực token STOMP được triển khai đúng bằng interceptor), không phải dữ liệu đầu vào.

### 2.2. Đăng ký sai kênh

Alice là thành viên phòng `r1` nhưng thử `SUBSCRIBE /topic/rooms/r2`. Nếu chỉ có luật `/topic/rooms/** -> authenticated()`, Alice sẽ vượt qua dù không thuộc `r2`. Kiểm tra quyền phải xét **đối tượng tài nguyên** (`roomId`) và danh tính; vai trò `ROLE_USER` không đủ.

Tương tự, client không được tự đăng ký vào `/queue/private` hoặc đích broker vật lý sinh ra sau khi Spring giải quyết `/user/queue/...`. Việc đăng ký đường dẫn `/user/queue/errors` của chính session không trao quyền truy cập mọi queue bên dưới `/queue/**`.

### 2.3. Thông điệp ngoài quy tắc

Một client gửi `SEND /topic/announcements` với nội dung tự nhận là từ hệ thống. Nếu broker nhận trực tiếp, server có thể phát cho toàn bộ subscriber mà không chạy `@MessageMapping`/kiểm tra quyền trong ứng dụng. Một client khác gửi tới `/app/unknown`, `/app/admin/announce` mà không có quyền, hoặc gửi frame không có destination hợp lệ. Đó là các trường hợp phải kiểm tra **kiểu frame, destination, quyền, payload** riêng biệt.

**Không suy diễn** rằng cứ trả về STOMP `ERROR` là an toàn: framework/broker có thể đóng kết nối, trả lỗi hoặc từ chối ở lớp khác. Kết quả bảo mật bắt buộc là **không xảy ra thao tác trái phép**.

## 3. Cấu hình mẫu: cho phép tường minh, từ chối mặc định

Các đoạn mã dưới đây là những tệp Java riêng trong package `example.messaging` của một ứng dụng Spring Boot Servlet có các dependency: `spring-boot-starter-websocket`, `spring-boot-starter-security`, `spring-security-messaging` và `spring-boot-starter-test` (scope `test`). Dùng phiên bản dependency do Spring Boot BOM quản lý. Cấu hình nhấn mạnh **luật message**, không thay thế cấu hình xác thực HTTP, CSRF hay kho thành viên phòng thực tế của dự án.

**`MessagingWebSocketConfig.java`**

```java
package example.messaging;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class MessagingWebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws"); // Mặc định chỉ cho same-origin.
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setUserDestinationPrefix("/user");
    }
}
```

**`RoomMembership.java`** — adapter nghiệp vụ, phải có implementation tra cứu thành viên phòng từ dữ liệu đáng tin cậy:

```java
package example.messaging;

public interface RoomMembership {
    boolean isMember(String roomId, String username);
}
```

**`MessageSecurityConfig.java`** — đặt luật cụ thể **trước** luật từ chối mặc định. `{roomId}` được trích từ destination, còn `Authentication` lấy từ Spring Security:

```java
package example.messaging;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.messaging.access.intercept.MessageAuthorizationContext;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;

import static org.springframework.messaging.simp.SimpMessageType.MESSAGE;
import static org.springframework.messaging.simp.SimpMessageType.SUBSCRIBE;

@Configuration
@EnableWebSocketSecurity
public class MessageSecurityConfig {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages,
            RoomMembership memberships) {

        AuthorizationManager<MessageAuthorizationContext<?>> roomMember =
                (authentication, context) -> {
                    Authentication user = authentication.get();
                    String roomId = context.getVariables().get("roomId");
                    boolean allowed = user != null
                            && user.isAuthenticated()
                            && !(user instanceof AnonymousAuthenticationToken)
                            && roomId != null
                            && memberships.isMember(roomId, user.getName());
                    return new AuthorizationDecision(allowed);
                };

        return messages
                .nullDestMatcher().authenticated()
                .simpSubscribeDestMatchers("/user/queue/errors").authenticated()
                .simpSubscribeDestMatchers("/topic/announcements").authenticated()
                .simpSubscribeDestMatchers("/topic/rooms/{roomId}")
                    .access(roomMember)
                .simpMessageDestMatchers("/app/rooms/{roomId}/send")
                    .access(roomMember)
                .simpMessageDestMatchers("/app/admin/announce").hasRole("ADMIN")
                .simpTypeMatchers(MESSAGE, SUBSCRIBE).denyAll()
                .anyMessage().denyAll()
                .build();
    }
}
```

**Giải thích các điểm dễ sai:**

- `nullDestMatcher().authenticated()` bảo vệ các frame không có destination như `CONNECT`, `UNSUBSCRIBE`, `DISCONNECT`. Kiểm tra CSRF ở `CONNECT` khi dùng `@EnableWebSocketSecurity` vẫn là một lớp khác; chỉ thử `AuthorizationManager` không chứng minh CSRF hoạt động.
- `simpMessageDestMatchers(...)` áp dụng cho message đến từ `SEND`; `simpSubscribeDestMatchers(...)` áp dụng cho `SUBSCRIBE`. Dùng `simpDestMatchers("/topic/**").authenticated()` rộng cho cả hai kiểu có thể mở đường cho client tự phát vào broker.
- Luật thành viên phòng áp dụng cho **cả gửi lẫn đăng ký**. Nếu membership thay đổi trong lúc kết nối còn mở, cần chính sách thu hồi/subscription hiện hữu phù hợp; kiểm tra lúc đăng ký không tự động xóa subscription đã được cấp trước đó.
- `anyMessage().denyAll()` giữ hệ thống an toàn khi có destination hoặc kiểu mới chưa được liệt kê. Luật này cũng khiến các thông điệp mới muốn hợp lệ phải được bổ sung tường minh.
- Tài khoản `ROLE_ADMIN` chỉ được phép `SEND` tới `/app/admin/announce` ở tầng authorization; controller quản trị vẫn phải xử lý đúng nghiệp vụ. Cấu hình minh họa không công bố controller đó.

### 3.1. Ràng buộc danh tính tại controller

**`RoomMessageController.java`** — kiểm tra thành viên lần nữa ở nơi thực hiện thay đổi, và luôn tạo dữ liệu đầu ra với danh tính từ `Principal`:

```java
package example.messaging;

import java.security.Principal;

import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Controller;

@Controller
public class RoomMessageController {

    public record SendCommand(String sender, String text) {}
    public record RoomEvent(String sender, String text) {}

    private final SimpMessagingTemplate messaging;
    private final RoomMembership memberships;

    public RoomMessageController(
            SimpMessagingTemplate messaging, RoomMembership memberships) {
        this.messaging = messaging;
        this.memberships = memberships;
    }

    @MessageMapping("/rooms/{roomId}/send")
    public void send(
            @DestinationVariable("roomId") String roomId,
            SendCommand command,
            Principal principal) {

        if (principal == null || !memberships.isMember(roomId, principal.getName())) {
            throw new AccessDeniedException("Not a room member");
        }
        if (command == null || command.text() == null
                || command.text().isBlank() || command.text().length() > 500) {
            throw new IllegalArgumentException("Invalid message text");
        }

        RoomEvent event = new RoomEvent(principal.getName(), command.text());
        messaging.convertAndSend("/topic/rooms/" + roomId, event);
    }
}
```

Ở đây `command.sender()` **cố ý không sử dụng**; trường đó chỉ tồn tại để mô phỏng client cố giả danh. Trong thiết kế thật, nên loại bỏ `sender` khỏi request DTO. Phải validate payload (định dạng, độ dài, dữ liệu nhạy cảm theo nghiệp vụ) và đảm bảo thứ tự kiểm tra trước khi ghi DB/broadcast. Luật controller là phòng vệ bổ sung khi thay đổi đường gọi, không thay thế chính sách trên `clientInboundChannel`.

## 4. Kiểm thử đơn vị quyền `SEND` và `SUBSCRIBE`

Mục tiêu của kiểm thử authorization thuần là xác minh quyết định **cho phép/từ chối** đối với một `Authentication`, `SimpMessageType` và destination cụ thể. Ta không cần WebSocket thật ở tầng này.

**`src/test/java/example/messaging/MessageSecurityConfigTest.java`**

```java
package example.messaging;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class MessageSecurityConfigTest {

    // Dữ liệu giả cho test: Alice là thành viên r1, không thuộc r2.
    private final RoomMembership memberships =
            (roomId, username) -> "r1".equals(roomId) && "alice".equals(username);

    private final AuthorizationManager<Message<?>> rules =
            new MessageSecurityConfig().messageAuthorizationManager(
                    MessageMatcherDelegatingAuthorizationManager.builder(),
                    memberships);

    private static Authentication user(String username, String role) {
        return new UsernamePasswordAuthenticationToken(
                username, "unused",
                List.of(new SimpleGrantedAuthority("ROLE_" + role)));
    }

    private boolean allowed(Authentication user, SimpMessageType type, String dest) {
        SimpMessageHeaderAccessor headers = SimpMessageHeaderAccessor.create(type);
        headers.setDestination(dest);
        Message<byte[]> incoming =
                MessageBuilder.createMessage(new byte[0], headers.getMessageHeaders());
        var result = rules.authorize(() -> user, incoming);
        return result != null && result.isGranted();
    }

    @Test
    void allowsMemberToSendAndSubscribeWithinOwnRoom() {
        Authentication alice = user("alice", "USER");
        assertTrue(allowed(alice, SimpMessageType.MESSAGE,
                "/app/rooms/r1/send"));
        assertTrue(allowed(alice, SimpMessageType.SUBSCRIBE,
                "/topic/rooms/r1"));
    }

    @Test
    void blocksNonMemberFromSendingAndSubscribingToOtherRoom() {
        Authentication alice = user("alice", "USER");
        assertFalse(allowed(alice, SimpMessageType.MESSAGE,
                "/app/rooms/r2/send"));
        assertFalse(allowed(alice, SimpMessageType.SUBSCRIBE,
                "/topic/rooms/r2"));
    }

    @Test
    void blocksDirectPublishToBrokerEvenWhenSubscribed() {
        Authentication alice = user("alice", "USER");
        assertFalse(allowed(alice, SimpMessageType.MESSAGE,
                "/topic/announcements"));
        assertFalse(allowed(alice, SimpMessageType.MESSAGE,
                "/topic/rooms/r1"));
        assertFalse(allowed(alice, SimpMessageType.MESSAGE,
                "/queue/private"));
    }

    @Test
    void blocksUnknownSubscriptionsAndUnknownApplicationMessages() {
        Authentication alice = user("alice", "USER");
        assertFalse(allowed(alice, SimpMessageType.SUBSCRIBE,
                "/topic/internal"));
        assertFalse(allowed(alice, SimpMessageType.SUBSCRIBE,
                "/queue/private"));
        assertFalse(allowed(alice, SimpMessageType.MESSAGE,
                "/app/unknown"));
    }

    @Test
    void distinguishesMessagePermissionFromSubscribePermission() {
        Authentication alice = user("alice", "USER");
        assertTrue(allowed(alice, SimpMessageType.SUBSCRIBE,
                "/topic/announcements"));
        assertFalse(allowed(alice, SimpMessageType.MESSAGE,
                "/topic/announcements"));
    }

    @Test
    void rejectsAdminSendWithoutAdminRole() {
        assertFalse(allowed(user("alice", "USER"), SimpMessageType.MESSAGE,
                "/app/admin/announce"));
        assertTrue(allowed(user("admin", "ADMIN"), SimpMessageType.MESSAGE,
                "/app/admin/announce"));
    }
}
```

Kiểm thử này **không tạo kết nối STOMP thật**, nên không kiểm tra header/CSRF của `CONNECT`, phân phối dữ liệu, lỗi STOMP do broker sinh ra hoặc quan hệ giữa session và `Principal`. Nó chỉ kiểm tra chính sách matcher và quyền phòng với các giả định đã khai báo. Các phiên bản Spring Security mới dùng `AuthorizationManager.authorize`; trên dự án cũ hơn cần đối chiếu API phiên bản đang chạy.

## 5. Kiểm thử chống giả mạo tại điểm xử lý

Bên cạnh luật message, phải chứng minh handler không tin payload gửi từ client và không tạo side effect khi user không thuộc phòng. Ví dụ sau dùng Mockito/JUnit 5, kiểm tra **đích xuất bản và toàn bộ event** chứ không chỉ trạng thái HTTP/STOMP.

**`src/test/java/example/messaging/RoomMessageControllerTest.java`**

```java
package example.messaging;

import org.junit.jupiter.api.Test;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.security.access.AccessDeniedException;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;

class RoomMessageControllerTest {

    @Test
    void senderInPayloadCannotImpersonateAdmin() {
        SimpMessagingTemplate outbound = mock(SimpMessagingTemplate.class);
        RoomMembership members =
                (room, username) -> "r1".equals(room) && "alice".equals(username);
        RoomMessageController controller = new RoomMessageController(outbound, members);

        controller.send("r1",
                new RoomMessageController.SendCommand("admin", "Xin chào"),
                () -> "alice");

        verify(outbound).convertAndSend(
                "/topic/rooms/r1",
                new RoomMessageController.RoomEvent("alice", "Xin chào"));
    }

    @Test
    void sendingToForeignRoomHasNoBroadcastSideEffect() {
        SimpMessagingTemplate outbound = mock(SimpMessagingTemplate.class);
        RoomMembership members =
                (room, username) -> "r1".equals(room) && "alice".equals(username);
        RoomMessageController controller = new RoomMessageController(outbound, members);

        assertThrows(AccessDeniedException.class, () ->
                controller.send("r2",
                        new RoomMessageController.SendCommand("alice", "Secret"),
                        () -> "alice"));

        verifyNoInteractions(outbound);
    }

    @Test
    void invalidPayloadHasNoBroadcastSideEffect() {
        SimpMessagingTemplate outbound = mock(SimpMessagingTemplate.class);
        RoomMembership members = (room, username) -> true;
        RoomMessageController controller = new RoomMessageController(outbound, members);

        assertThrows(IllegalArgumentException.class, () ->
                controller.send("r1",
                        new RoomMessageController.SendCommand("alice", "  "),
                        () -> "alice"));
        verifyNoInteractions(outbound);
    }
}
```

Chạy trong dự án đã khai báo dependencies và tạo các tệp nguồn ở đúng package:

```bash
./mvnw test -Dtest=MessageSecurityConfigTest,RoomMessageControllerTest
```

Kỳ vọng: Maven kết thúc thành công và **6 test về luật message + 3 test controller** đều pass. Đừng lấy dòng log/stdout giả định làm bằng chứng; đọc kết quả thực tế của runner. Nếu dùng Gradle, chạy các test class tương ứng qua `./gradlew test`. Dự án phải cung cấp implementation `RoomMembership` để khởi động ứng dụng thực; hai unit test ở trên dùng fake membership nên không cần database.

## 6. Kiểm thử tích hợp STOMP: client thực, phiên thực

Unit test không chứng minh được một client có thể hay không thể **đưa header giả qua mạng**. Thêm integration test với embedded server và `WebSocketStompClient` (hoặc client STOMP độc lập), dùng ít nhất hai tài khoản xác thực Alice/Bob, hai phòng `r1`/`r2` và một tài khoản admin. Tạo cả **luồng hợp lệ (positive)** để tránh trường hợp cấu hình từ chối tất cả nhưng test âm tính vẫn xanh.

**Cách sắp đặt fixture:**

1. Alice thuộc `r1`; Bob thuộc `r2`; Admin có `ROLE_ADMIN`. Alice/Bob đều có `ROLE_USER`.
2. Dùng HTTP handshake có phiên/cookie hợp lệ hoặc cơ chế token thực của ứng dụng. Nếu dùng bảo vệ CSRF STOMP mặc định, lấy token đúng phiên và gửi trong **native headers của frame CONNECT**; chỉ xác thực handshake chưa chắc đủ.
3. Alice và Bob mở kết nối riêng, đồng thời có subscriber giám sát hợp lệ cho `/topic/rooms/r1`, `/topic/rooms/r2` và `/topic/announcements`. Đưa tin nhận được vào queue theo session, tách biệt giữa các test.
4. Xóa queue, đồng bộ kết nối/subscription (ACK hoặc tín hiệu server tương ứng nếu giao thức ứng dụng hỗ trợ) rồi mới bắt đầu đếm thông điệp. Kiểm tra trạng thái lưu DB nếu có.
5. Sau frame tấn công, chờ trong **thời hạn hữu hạn** và xác nhận không có thông điệp trái phép, không có bản ghi trái phép, không thay đổi quyền. Phân biệt lỗi protocol, lỗi authorization, timeout và client bị ngắt kết nối.

### 6.1. Ma trận ca kiểm thử âm tính và dương tính

| ID | Principal / frame client gửi | Kỳ vọng quan sát |
| --- | --- | --- |
| P01 | Alice `SEND /app/rooms/r1/send`, `sender=alice` | Được xử lý; event ghi Alice; subscriber `r1` nhận đúng 1 event |
| N01 | Alice gửi cùng destination, `sender=admin` | Không tạo event mang tên admin; nếu được gửi hợp lệ thì event vẫn ghi Alice |
| N02 | Alice `SEND /app/rooms/r2/send` dù khai `sender=bob` | Bị từ chối; Bob/`r2` không nhận, DB không thêm bản ghi |
| N03 | Alice thêm native header `user: admin` hoặc `simpUser: admin` | Header tự khai không nâng quyền; server xác thực vẫn là Alice |
| N04 | Alice tự điền `login=admin`/`passcode=...` trong STOMP `CONNECT` | Không biến Alice thành admin; nếu app có auth interceptor riêng, phải kiểm tra token thật |
| N05 | Alice `SUBSCRIBE /topic/rooms/r2` | Không nhận dữ liệu `r2` kể cả khi server phát thông điệp sau đó |
| N06 | Alice `SUBSCRIBE /queue/private` | Không được tạo subscription nhận dữ liệu riêng tư |
| N07 | Alice `SUBSCRIBE /topic/internal` | Bị từ chối theo mặc định |
| P02 | Alice `SUBSCRIBE /topic/rooms/r1` | Được đăng ký; nhận dữ liệu phòng của mình |
| P03 | Alice `SUBSCRIBE /user/queue/errors` | Được phép cho session của Alice, không mở quyền xem queue vật lý của Bob |
| N08 | Alice `SEND /topic/announcements` | Không phát thông báo chung tới subscriber |
| N09 | Alice `SEND /topic/rooms/r1` | Không qua mặt controller dù là thành viên phòng |
| N10 | Alice `SEND /queue/private` hoặc `/user/queue/errors` | Bị từ chối; không được gửi trực tiếp đến broker/user destination |
| N11 | Alice `SEND /app/admin/announce` | Bị từ chối do thiếu `ROLE_ADMIN` |
| P04 | Admin `SEND /app/admin/announce` | Vượt qua luật phân quyền message; business handler vẫn cần tồn tại và hợp lệ |
| N12 | Alice `SEND /app/unknown` hoặc `SUBSCRIBE /topic/unknown` | Bị từ chối theo `denyAll` |
| N13 | Anonymous/không có xác thực hợp lệ kết nối hoặc gửi frame | Không thực hiện thao tác được bảo vệ; lý do có thể ở handshake, CONNECT/CSRF hoặc authorization |
| N14 | Gửi payload rỗng, quá dài, JSON sai kiểu đến route hợp lệ | Không tạo message/bản ghi sau validation; phản hồi tùy cơ chế xử lý lỗi |
| N15 | Alice bị thu hồi khỏi `r1` sau khi đăng ký | Không tiếp tục nhận dữ liệu nhạy cảm theo chính sách thu hồi đã thiết kế; có thể phải hủy session/subscription hiện hữu |

**Kiểm tra riêng ranh giới HTTP và STOMP:** test `GET /ws`/handshake với session không hợp lệ; test `CONNECT` thiếu CSRF hoặc CSRF sai; rồi test `SEND`/`SUBSCRIBE` có CSRF và session hợp lệ. Nếu gộp thành một test và CONNECT đã thất bại, bạn chưa hề kiểm tra được message authorization.

### 6.2. Gửi frame STOMP thô để bắt lỗi định tuyến

Client STOMP thực phải gửi frame chuẩn (dòng trống phân cách header/payload và kết thúc bằng byte NUL `0x00`). Hai trường hợp cần thử:

```text
SEND
destination:/topic/announcements
content-type:text/plain

Tôi là hệ thống!
[NUL]
```

```text
SUBSCRIBE
id:probe-r2
destination:/topic/rooms/r2

[NUL]
```

`[NUL]` ở đây là **ký hiệu minh họa byte NUL thực**, không phải chuỗi ký tự gửi trên dây. Với ví dụ đầu, Alice không được làm subscriber `/topic/announcements` nhận payload. Với ví dụ thứ hai, sau khi Bob/server gửi sự kiện tới `r2`, kết nối Alice không được thấy nội dung đó. Một test chỉ kiểm tra `subscribe()` trả về đối tượng subscription ở phía client **không đủ** kết luận đã được server cho phép.

### 6.3. Điều kiện kiểm chứng và đồng bộ bất đồng bộ

- Với ca thành công, xác nhận đúng `principal`, `destination`, payload, số lần nhận và người nhận dự kiến; không có người ngoài phòng nhận dữ liệu.
- Với ca bị từ chối, xác nhận **không có side effect** trong khoảng chờ hợp lý, kiểm tra event audit nếu ứng dụng phát và đọc lại DB nếu có. Không phụ thuộc một chuỗi lỗi STOMP cố định vì lỗi có thể xảy ra ở nhiều lớp.
- Dùng `BlockingQueue`/`CountDownLatch`/cơ chế await có timeout để đợi có điều kiện; tránh `Thread.sleep` cố định. Mỗi test dùng session/subscription/queue độc lập và dọn sau khi chạy.
- Gửi sự kiện có ID duy nhất để không lẫn thông điệp trước đó. Nếu một subscription bị từ chối, không mặc định rằng broker sẽ gửi `ERROR`; kết luận theo **việc không nhận dữ liệu** và kiểm chứng phía server.
- Với session đang mở, thử quyền bị thu hồi và kết nối mới. Khả năng còn nhận qua subscription cũ cần test riêng theo cơ chế hủy subscription/đóng session của sản phẩm, không thể suy ra từ kiểm tra lúc `SUBSCRIBE`.

## 7. Các sai sót kiểm thử và thiết kế phổ biến

1. **Chỉ kiểm tra `authenticated()`:** Alice và Bob đều đăng nhập, nhưng vẫn có thể truy cập tài nguyên của nhau. Dùng kiểm tra tài nguyên gắn với `roomId`.
2. **Chỉ khóa controller:** client gửi trực tiếp `/topic/**` vào broker có thể không qua controller. Hạn chế `MESSAGE` đến prefix broker.
3. **Dùng `simpDestMatchers` quá rộng:** matcher không phân biệt `MESSAGE` và `SUBSCRIBE`; dùng matcher theo type, thêm `denyAll` cuối.
4. **Tin `sender` trong JSON:** quyền message vẫn có thể đúng, nhưng danh tính event đã bị giả mạo. Kiểm tra output/DB; lấy actor từ authenticated `Principal`.
5. **Thấy kết nối bị từ chối rồi kết luận mọi luật đúng:** có thể do thiếu CSRF `CONNECT`. Cần có positive control kết nối hợp lệ trước khi gửi frame tấn công.
6. **Chỉ assert lỗi:** không đảm bảo dữ liệu chưa phát hoặc chưa lưu. Luôn assert side effect âm tính và quyền người nhận.
7. **Cho phép `/queue/**` vì nghĩ user queue có bảo vệ tự động:** client được dùng `/user/queue/...` đã được cho phép; không mở trực tiếp queue vật lý.
8. **Kiểm tra subscription ngay khi đăng ký nhưng quên thay đổi quyền:** dữ liệu nhạy cảm có thể rò qua subscription tồn tại sau khi quyền bị thu hồi; định nghĩa yêu cầu ngắt/kick/re-auth.
9. **Trộn lẫn xác thực và phân quyền:** `Origin`/CSRF chống một lớp tấn công, không thay thế kiểm tra vai trò và membership.
10. **Test cùng một tài khoản cho mọi nhánh:** phải có ít nhất user thường, user khác tài nguyên, admin và anonymous; kết hợp cả positive/negative cases.
11. **Khẳng định WebSocket thuần giống STOMP:** `@EnableWebSocketSecurity` ở đây áp dụng cho Spring Messaging/STOMP, không bảo vệ tự động mọi endpoint WebSocket thô sử dụng trực tiếp API khác.
12. **Viết test chỉ với `AuthorizationManager` nhưng báo cáo đã chống được giả mạo header mạng:** test thuần không xác nhận lớp handshake, interceptor xác thực token, hoặc chuyển tiếp thực tế.

## 8. Quy trình hoàn tất bài thực hành

- **Xác định policy:** liệt kê từng `SimpMessageType + destination + vai trò + điều kiện chủ sở hữu`; tất cả đường ngoài danh sách đều từ chối.
- **Kiểm tra danh tính:** đưa `sender` giả vào payload và native STOMP headers; assert thông điệp đầu ra dùng `Principal` thực.
- **Kiểm tra quyền kênh:** thử thành viên/phòng đúng, thành viên/phòng khác, queue vật lý, kênh nội bộ và subscription đã bị thu hồi.
- **Kiểm tra quyền gửi:** thử `SEND` hợp lệ qua `/app/...`, gửi thẳng tới `/topic/**`/`/queue/**`, đường admin và destination lạ.
- **Kiểm tra hậu quả:** xác nhận không broadcast, không ghi DB, không lộ nội dung; dùng nhiều phiên và theo dõi subscriber thật.
- **Tách tầng test:** unit test luật/handler nhanh; integration test có session, CSRF, STOMP và broker; kiểm tra đầy đủ cả trường hợp thành công.

### Tài liệu đối chiếu

- [Spring Security — WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html): `@EnableWebSocketSecurity`, authorization cho `SEND`/`SUBSCRIBE`, giới hạn inbound và chống cross-origin.
- [Spring Framework — STOMP Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html): truyền `Principal` từ HTTP session sang WebSocket.
- [Spring Framework — Token Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html): trường hợp xác thực bằng header trong STOMP `CONNECT` và thứ tự interceptor.
- [Spring Framework — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html): cách `/user/queue/...` chuyển thành destination riêng theo session.
- [Spring Framework — Testing STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/testing.html): unit và end-to-end testing.

**Tiêu chí đạt:** một client hợp lệ có thể dùng đúng quyền của mình; không thể đổi danh tính bằng payload/header, xem kênh không thuộc mình hoặc phát thông điệp ngoài luật. Mọi ca âm tính chứng minh không có hành vi nghiệp vụ trái phép, không chỉ chứng minh có một thông báo lỗi.