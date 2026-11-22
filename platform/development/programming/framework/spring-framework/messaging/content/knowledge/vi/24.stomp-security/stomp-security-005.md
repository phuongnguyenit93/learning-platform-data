# Tách quyền gửi tới ứng dụng và quyền đọc từ broker

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt STOMP `MESSAGE` (gửi dữ liệu) với `SUBSCRIBE` (đăng ký nhận dữ liệu).
- Giải thích vì sao quyền gửi đến application destination `/app/**` cần tách khỏi quyền đăng ký broker destination `/topic/**` hoặc `/queue/**`.
- Cấu hình Spring Security bằng `AuthorizationManager<Message<?>>`, `simpMessageDestMatchers` và `simpSubscribeDestMatchers`.
- Chặn client gửi trực tiếp vào destination của broker để tránh giả mạo message do server phát.
- Chỉ cấp quyền subscribe đến những luồng dữ liệu mà user được phép đọc.
- Kiểm thử các trường hợp được phép và bị từ chối, đồng thời hiểu vai trò của xác thực, CSRF và kiểm tra quyền nghiệp vụ.

## 1. Vì sao phải tách quyền gửi và quyền đọc?

Trong ứng dụng WebSocket dùng STOMP, một client có thể thực hiện nhiều loại thao tác trên cùng một destination:

- Gửi frame `SEND` đến một destination.
- Gửi frame `SUBSCRIBE` để nhận message từ một destination.

Spring chuyển hai thao tác này thành các message có loại khác nhau trong hệ thống messaging:

| STOMP frame | Loại message Spring | Ý nghĩa |
|---|---|---|
| `SEND` | `SimpMessageType.MESSAGE` | Client gửi payload đến server hoặc broker |
| `SUBSCRIBE` | `SimpMessageType.SUBSCRIBE` | Client đăng ký nhận message |
| `UNSUBSCRIBE` | `SimpMessageType.UNSUBSCRIBE` | Client hủy đăng ký |
| `CONNECT` | `SimpMessageType.CONNECT` | Client bắt đầu phiên STOMP |
| `DISCONNECT` | `SimpMessageType.DISCONNECT` | Client kết thúc phiên STOMP |

Hai thao tác `MESSAGE` và `SUBSCRIBE` có mục đích bảo mật khác nhau. Một user được phép gửi lệnh tạo đơn hàng không có nghĩa là user đó được phép đọc mọi topic của hệ thống. Tương tự, một user được phép theo dõi thông báo trong topic không có nghĩa là user đó được phép gửi dữ liệu vào topic ấy.

Ví dụ:

- Client gửi nội dung chat đến `/app/chat.send`. Spring định tuyến message đến controller có `@MessageMapping`.
- Client đăng ký `/topic/chat/room-42` để nhận các message của phòng chat.
- Server gửi dữ liệu đến `/topic/chat/room-42` sau khi đã xử lý nghiệp vụ.

Quyền cần được tách thành hai câu hỏi:

1. User có được phép **gửi lệnh đến ứng dụng** qua `/app/**` không?
2. User có được phép **đăng ký đọc dữ liệu** từ destination broker cụ thể không?

Nếu chỉ kiểm tra prefix chung hoặc chỉ yêu cầu user đã đăng nhập, ứng dụng có thể vô tình cho phép client gửi message đến nơi mà server dự định dành riêng cho broker hoặc cho phép user đọc dữ liệu ngoài phạm vi của họ.

## 2. Application destination và broker destination

Một cấu hình STOMP thường phân biệt ba nhóm prefix:

| Prefix | Vai trò | Ví dụ |
|---|---|---|
| `/app` | Destination dành cho message đi vào controller của ứng dụng | `/app/chat.send` |
| `/topic`, `/queue` | Destination do message broker xử lý | `/topic/chat/room-42`, `/queue/notifications` |
| `/user` | User destination được Spring phân giải theo Principal/session | `/user/queue/notifications` |

Cấu hình broker có thể trông như sau:

```java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig
        implements WebSocketMessageBrokerConfigurer {

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
```

Luồng gửi đến ứng dụng:

```text
Client -- SEND /app/chat.send --> Spring clientInboundChannel
                                  |
                                  v
                         @MessageMapping("/chat.send")
                                  |
                                  v
                          Xử lý nghiệp vụ
                                  |
                                  v
                         BrokerChannel / Broker
                                  |
                                  v
                      MESSAGE /topic/chat/room-42
```

Luồng đọc từ broker:

```text
Client -- SUBSCRIBE /topic/chat/room-42 --> Spring clientInboundChannel
                                             |
                                             v
                                       Security check
                                             |
                                             v
                                      BrokerChannel
                                             |
                                             v
                                      Subscription
                                             |
                                             v
                              Nhận message được server gửi
```

`/app/**` thường đại diện cho lệnh hoặc dữ liệu client gửi vào ứng dụng. `/topic/**` và `/queue/**` thường đại diện cho luồng dữ liệu do broker phân phối. Tuy nhiên, prefix chỉ là quy ước định tuyến; quyền thực tế phải được cấu hình bằng matcher và authority cụ thể.

Một điểm quan trọng: client cũng có thể gửi `SEND` trực tiếp đến destination broker như `/topic/chat/room-42`. Nếu ứng dụng cho phép thao tác này, client có thể phát message trực tiếp đến subscriber mà không đi qua controller, validation hoặc kiểm tra quyền nghiệp vụ mà server dự định thực hiện.

Vì vậy, trong nhiều ứng dụng, client chỉ được gửi `MESSAGE` đến `/app/**`; message `MESSAGE` đến `/topic/**` hoặc `/queue/**` bị từ chối. Client có thể được phép `SUBSCRIBE` đến một số topic/queue được chỉ định.

## 3. Hai loại quyền cần quản lý riêng

### Quyền gửi đến application destination

Quyền này kiểm soát frame STOMP `SEND` được chuyển thành message `MESSAGE` có destination thuộc `/app/**`.

Ví dụ:

- `chat:send`: được gửi lệnh chat.
- `order:create`: được gửi lệnh tạo đơn.
- `support:reply`: được gửi phản hồi đến hệ thống hỗ trợ.

Quyền này chỉ cho phép message đi vào application handler phù hợp. Controller và service vẫn cần kiểm tra payload, quyền sở hữu tài nguyên và các điều kiện nghiệp vụ.

### Quyền đọc từ broker destination

Quyền này kiểm soát frame STOMP `SUBSCRIBE` được chuyển thành message `SUBSCRIBE`.

Ví dụ:

- `chat:read`: được đăng ký đọc topic chat.
- `order:events:read`: được đọc sự kiện đơn hàng.
- `notification:read`: được nhận thông báo riêng.

Quyền đọc cần xét cả destination. Có quyền `chat:read` không có nghĩa user được subscribe vào tất cả topic chat nếu ứng dụng có các phòng riêng tư. Với dữ liệu nhạy cảm, cần kiểm tra membership hoặc quyền trên từng tài nguyên.

### Bảng phân quyền mẫu

| Thao tác | Destination | Authority | Kết quả |
|---|---|---|---|
| `MESSAGE` | `/app/chat/**` | `chat:send` | Cho phép |
| `SUBSCRIBE` | `/topic/chat/**` | `chat:read` | Cho phép |
| `SUBSCRIBE` | `/user/queue/notifications` | `notification:read` | Cho phép |
| `MESSAGE` | `/topic/chat/**` | Bất kỳ | Từ chối |
| `MESSAGE` | `/queue/**` | Bất kỳ | Từ chối |
| `SUBSCRIBE` | `/queue/**` | Bất kỳ | Từ chối theo chính sách ví dụ |
| `SUBSCRIBE` | `/app/**` | Bất kỳ | Từ chối |
| Destination hoặc loại message chưa khai báo | Bất kỳ | Bất kỳ | Từ chối mặc định |

Bảng này thể hiện một chính sách mẫu. Ứng dụng có thể thêm destination công khai hoặc quyền khác, nhưng mỗi ngoại lệ cần có lý do nghiệp vụ rõ ràng.

## 4. Cấu hình bằng AuthorizationManager

Từ Spring Security 5.8, có thể cấu hình bảo mật message bằng API `AuthorizationManager`. Với Spring Security 6.x/7.x, có thể dùng `@EnableWebSocketSecurity` và công bố bean `AuthorizationManager<Message<?>>`.

Ví dụ:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.security.authorization.AuthorizationManager;
import org.springframework.security.config.annotation.web.socket.EnableWebSocketSecurity;
import org.springframework.security.messaging.access.intercept.MessageMatcherDelegatingAuthorizationManager;

@Configuration
@EnableWebSocketSecurity
public class WebSocketSecurityConfig {

    @Bean
    AuthorizationManager<Message<?>> messageAuthorizationManager(
            MessageMatcherDelegatingAuthorizationManager.Builder messages) {

        messages
            // CONNECT, DISCONNECT và các message không có destination.
            .nullDestMatcher().authenticated()

            // Chỉ cho phép MESSAGE gửi vào application handler.
            .simpMessageDestMatchers("/app/chat/**")
                .hasAuthority("chat:send")

            // Không cho client publish trực tiếp vào broker destination.
            .simpMessageDestMatchers("/topic/**", "/queue/**")
                .denyAll()

            // Chỉ cho phép đọc topic chat khi có quyền chat:read.
            .simpSubscribeDestMatchers("/topic/chat/**")
                .hasAuthority("chat:read")

            // User destination riêng yêu cầu quyền nhận notification.
            .simpSubscribeDestMatchers("/user/queue/notifications")
                .hasAuthority("notification:read")

            // Không cho subscribe trực tiếp vào queue vật lý.
            .simpSubscribeDestMatchers("/queue/**")
                .denyAll()

            // MESSAGE hoặc SUBSCRIBE chưa có rule cụ thể đều bị từ chối.
            .simpTypeMatchers(
                SimpMessageType.MESSAGE,
                SimpMessageType.SUBSCRIBE
            ).denyAll()

            // Các loại message còn lại cũng bị từ chối nếu chưa khai báo.
            .anyMessage().denyAll();

        return messages.build();
    }
}
```

Các matcher quan trọng:

- `nullDestMatcher()` khớp message không có destination, chẳng hạn `CONNECT`, `DISCONNECT`, `UNSUBSCRIBE` và một số message điều khiển. Ví dụ yêu cầu user đã xác thực.
- `simpMessageDestMatchers(...)` chỉ khớp loại `SimpMessageType.MESSAGE` với destination tương ứng.
- `simpSubscribeDestMatchers(...)` chỉ khớp loại `SimpMessageType.SUBSCRIBE` với destination tương ứng.
- `simpTypeMatchers(...)` khớp theo loại message, bất kể destination.
- `anyMessage()` là matcher tổng quát cho mọi message.

Các rule được xét theo thứ tự khai báo; rule đầu tiên khớp sẽ quyết định quyền. Vì vậy, rule cho phép cụ thể phải được đặt trước rule từ chối tổng quát. `anyMessage().denyAll()` giúp hệ thống từ chối những loại message chưa được dự liệu khi thêm destination hoặc chức năng mới.

### Vì sao dùng simpMessageDestMatchers?

`MESSAGE` và `SUBSCRIBE` là hai hành động khác nhau, dù cùng có destination. `simpMessageDestMatchers` giới hạn rule cho thao tác gửi. `simpSubscribeDestMatchers` giới hạn rule cho thao tác đăng ký nhận.

Nếu dùng matcher destination không giới hạn loại message, một rule có thể áp dụng rộng hơn ý định ban đầu. Dùng matcher riêng theo loại message làm chính sách dễ đọc và kiểm tra hơn.

## 5. Cách đọc chính sách theo từng rule

### 5.1. Yêu cầu xác thực với message không có destination

```java
.nullDestMatcher().authenticated()
```

Một số frame điều khiển như `CONNECT`, `DISCONNECT` hoặc `UNSUBSCRIBE` không mang destination. Rule này yêu cầu user đã xác thực cho nhóm message đó.

`@EnableWebSocketSecurity` cũng kích hoạt bảo vệ CSRF cho inbound `CONNECT` theo cấu hình mặc định. Client cần gửi CSRF token hợp lệ trong STOMP headers khi kết nối. Điều này giúp giảm nguy cơ tấn công Cross-Site WebSocket Hijacking.

Nếu ứng dụng cho phép kết nối anonymous, cần thiết kế riêng rule cho các message không có destination và giới hạn những thao tác anonymous có thể thực hiện. Không nên bỏ yêu cầu xác thực một cách rộng rãi chỉ để một client kết nối được.

### 5.2. Cho phép gửi lệnh vào controller

```java
.simpMessageDestMatchers("/app/chat/**")
    .hasAuthority("chat:send")
```

Chỉ frame `SEND` có destination khớp `/app/chat/**` mới được rule này xử lý. User cần authority `chat:send`.

Ví dụ:

- `SEND /app/chat.send` — có thể được cho phép nếu matcher và authority phù hợp.
- `SUBSCRIBE /app/chat.send` — không khớp `simpMessageDestMatchers`; sẽ đi tiếp đến rule khác và bị từ chối nếu không có rule subscribe riêng.
- `SEND /topic/chat/room-42` — không khớp rule `/app/chat/**`; sẽ bị rule deny dành cho broker destination xử lý.

Authority là chuỗi chính xác. `hasAuthority("chat:send")` yêu cầu quyền có tên `chat:send`. Nếu dùng `hasRole("USER")`, Spring kiểm tra authority theo quy ước `ROLE_USER`.

### 5.3. Từ chối client publish trực tiếp đến broker

```java
.simpMessageDestMatchers("/topic/**", "/queue/**")
    .denyAll()
```

Đây là rule quan trọng để tránh client giả mạo message từ server.

Giả sử hệ thống gửi thông báo bảo trì qua `/topic/system/notifications`. Nếu client được `SEND` trực tiếp đến destination đó, client có thể phát thông báo giả cho tất cả subscriber.

Chỉ cho phép `SUBSCRIBE` theo rule riêng nếu user có quyền đọc. `SUBSCRIBE` vào topic không đồng nghĩa được quyền `SEND` vào cùng topic.

### 5.4. Cấp quyền subscribe theo topic

```java
.simpSubscribeDestMatchers("/topic/chat/**")
    .hasAuthority("chat:read")
```

Rule này chỉ kiểm soát frame `SUBSCRIBE`. User có `chat:read` có thể đăng ký topic chat thuộc pattern đã khai báo.

Nếu ứng dụng có nhiều phòng chat riêng tư, một authority tổng quát có thể chưa đủ. Ví dụ, user có `chat:read` không nhất thiết được đọc `/topic/chat/room-42`. Khi đó, cần kiểm tra membership của user với room tương ứng, bằng custom `AuthorizationManager`, matcher theo biến đường dẫn hoặc kiểm tra quyền nghiệp vụ phù hợp.

### 5.5. Bảo vệ user destination

```java
.simpSubscribeDestMatchers("/user/queue/notifications")
    .hasAuthority("notification:read")
```

Client có thể đăng ký user destination như `/user/queue/notifications`. Spring phân giải destination này theo Principal/session của user.

Không cấp quyền subscribe rộng vào `/queue/**` nếu ứng dụng sử dụng queue nội bộ theo session. Subscribe trực tiếp vào queue vật lý có thể làm lộ message dành cho người khác hoặc destination nội bộ.

### 5.6. Từ chối mặc định

```java
.simpTypeMatchers(
    SimpMessageType.MESSAGE,
    SimpMessageType.SUBSCRIBE
).denyAll()
.anyMessage().denyAll()
```

Rule đầu tiên từ chối các thao tác gửi hoặc đăng ký nhận chưa có rule cụ thể. Rule cuối từ chối mọi message còn lại.

Chính sách mặc định từ chối giúp tránh lỗi khi ứng dụng thêm endpoint mới nhưng chưa cập nhật quyền. Khi cần mở một chức năng mới, hãy thêm rule cụ thể cho loại message và destination tương ứng.

## 6. Ví dụ từ client đến controller và broker

Giả sử client có authority `chat:send` và `chat:read`.

Client gửi dữ liệu vào ứng dụng:

```javascript
stompClient.publish({
    destination: "/app/chat.send",
    body: JSON.stringify({
        roomId: "room-42",
        text: "Xin chào mọi người"
    })
});
```

Spring kiểm tra frame `MESSAGE` tại `/app/chat.send`. Nếu user có `chat:send`, message được chuyển đến handler:

```java
@Controller
public class ChatController {

    private final SimpMessagingTemplate messagingTemplate;

    public ChatController(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    @MessageMapping("/chat.send")
    public void send(ChatRequest request, Principal principal) {
        String sender = principal.getName();

        // Kiểm tra sender có quyền tham gia roomId.
        // Lưu hoặc xử lý message theo nghiệp vụ.

        ChatEvent event = new ChatEvent(
                request.roomId(),
                sender,
                request.text()
        );

        messagingTemplate.convertAndSend(
                "/topic/chat/" + request.roomId(),
                event
        );
    }
}

record ChatRequest(String roomId, String text) {}

record ChatEvent(String roomId, String sender, String text) {}
```

Client đăng ký nhận dữ liệu:

```javascript
stompClient.subscribe(
    "/topic/chat/room-42",
    (frame) => {
        const event = JSON.parse(frame.body);
        console.log(event.sender, event.text);
    }
);
```

Spring kiểm tra frame `SUBSCRIBE` tại `/topic/chat/room-42`. Nếu user có `chat:read`, subscription được chấp nhận. Khi server gửi event đến topic, broker phân phối event cho các subscriber hợp lệ.

Nếu client cố publish trực tiếp:

```javascript
stompClient.publish({
    destination: "/topic/chat/room-42",
    body: JSON.stringify({
        sender: "system",
        text: "Thông báo giả"
    })
});
```

Frame này là `MESSAGE` đến `/topic/chat/room-42`, khớp rule `denyAll()` cho broker destination và bị từ chối. Nó không đi qua controller để giả danh server.

Ví dụ controller chỉ minh họa luồng xử lý. Trong ứng dụng thật, cần xác thực `Principal`, kiểm tra room membership, validate DTO và xử lý lỗi theo quy ước của hệ thống.

## 7. Xác thực và phân quyền là hai bước khác nhau

### Xác thực

Xác thực trả lời: **Ai đang kết nối?**

Spring WebSocket thường kế thừa Principal từ HTTP handshake. Nếu HTTP request đã được xác thực bằng Spring Security, danh tính đó được chuyển sang WebSocket session và xuất hiện trong message dưới header `simpUser`.

Đối với ứng dụng dùng token, cần xác thực token trước khi gắn Principal vào message/session. Không coi header `login`, `passcode` hoặc `username` trong STOMP frame là danh tính đáng tin cậy nếu ứng dụng chưa có cơ chế xác thực riêng cho chúng.

### Phân quyền

Phân quyền trả lời: **User này được phép làm gì?**

`AuthorizationManager<Message<?>>` kiểm tra loại message, destination và authority của user. Ví dụ, hai user cùng đăng nhập nhưng một người có `chat:send`, người còn lại chỉ có `chat:read`.

Không dùng trạng thái đã đăng nhập làm lý do tự động cho phép mọi `SEND` và `SUBSCRIBE`. Cần xác định quyền theo chức năng và dữ liệu mà user được phép truy cập.

### Kiểm tra quyền nghiệp vụ

Message authorization theo destination vẫn chưa đủ để bảo vệ tài nguyên riêng tư.

Ví dụ, user có quyền `chat:send` có thể gửi đến `/app/chat.send`, nhưng điều đó không có nghĩa user được phép gửi vào mọi room. Controller/service phải kiểm tra user có phải thành viên của room hay không.

```java
@MessageMapping("/chat.send")
public void send(ChatRequest request, Principal principal) {
    String username = principal.getName();

    if (!roomService.isMember(request.roomId(), username)) {
        throw new AccessDeniedException("Not a member of this room");
    }

    // Xử lý message sau khi quyền trên room đã được xác nhận.
}
```

Tương tự, nếu user chỉ được đọc đơn hàng mà họ sở hữu, không thể chỉ cấp một quyền `orders:read` rồi cho subscribe vào mọi topic đơn hàng. Cần ràng buộc quyền đọc với từng order hoặc tenant.

## 8. Spring Security bảo vệ inbound channel như thế nào?

Spring Security đăng ký các interceptor bảo mật trên `clientInboundChannel`, tức các message đi từ client vào server. Các rule trong `AuthorizationManager<Message<?>>` được áp dụng ở luồng inbound này.

Với dữ liệu phát từ server qua `clientOutboundChannel`, Spring Security không mặc định chạy cùng cơ chế authorization trên từng outbound message. Vì thế, **quyền đọc phải được kiểm soát khi client gửi `SUBSCRIBE`**. Một khi subscription đã được chấp nhận, broker có thể gửi các message phù hợp đến client.

Điều này dẫn đến một số yêu cầu:

- Kiểm soát chặt các destination mà client được subscribe.
- Không cho client subscribe queue vật lý hoặc destination nội bộ.
- Khi user bị thu hồi quyền trong lúc session vẫn mở, cân nhắc hủy subscription/session hoặc áp dụng cơ chế cập nhật quyền phù hợp.
- Với dữ liệu riêng tư, kiểm tra quyền người nhận ở nơi server phát message.
- Không dựa vào outbound interceptor như biện pháp bảo mật duy nhất.

Ví dụ, nếu Alice đã subscribe vào topic phòng chat rồi bị loại khỏi phòng, chỉ cập nhật quyền trong database chưa chắc tự động hủy subscription hiện có. Ứng dụng cần có quy trình thu hồi quyền cho các subscription đang hoạt động hoặc thiết kế destination/session sao cho việc thu hồi được xử lý.

## 9. Kiểm tra quyền theo từng loại message

Khi kiểm thử, hãy tạo các tình huống cho cả `MESSAGE` và `SUBSCRIBE`. Không chỉ kiểm tra rằng user có thể kết nối thành công.

| User / Authority | Thao tác | Destination | Kết quả mong đợi |
|---|---|---|---|
| User có `chat:send` | `MESSAGE` | `/app/chat.send` | Cho phép |
| User không có `chat:send` | `MESSAGE` | `/app/chat.send` | Từ chối |
| User có `chat:read` | `SUBSCRIBE` | `/topic/chat/room-42` | Cho phép theo rule mẫu |
| User không có `chat:read` | `SUBSCRIBE` | `/topic/chat/room-42` | Từ chối |
| User có `chat:read` | `MESSAGE` | `/topic/chat/room-42` | Từ chối |
| User có `chat:send` | `SUBSCRIBE` | `/app/chat.send` | Từ chối |
| User có `notification:read` | `SUBSCRIBE` | `/user/queue/notifications` | Cho phép |
| User có `notification:read` | `SUBSCRIBE` | `/queue/notifications` | Từ chối |
| User đã đăng nhập | `MESSAGE` | `/unknown/action` | Từ chối mặc định |
| User chưa đăng nhập | `CONNECT` | Không có destination | Từ chối theo rule xác thực mẫu |

Các bài kiểm thử nên xác nhận cả kết quả được phép lẫn bị từ chối. Đặc biệt cần kiểm tra rằng quyền đọc không cho phép publish và quyền gửi vào `/app/**` không tự cấp quyền đọc broker.

Trong integration test, có thể dùng STOMP client và xác thực HTTP session tương ứng để kiểm tra toàn bộ handshake, CONNECT, SEND, SUBSCRIBE. Với kiểm thử đơn vị, có thể tạo `Message<?>` mang Simp headers và gọi AuthorizationManager để xác minh các matcher, nhưng không thay thế hoàn toàn kiểm thử luồng kết nối thực tế.

## 10. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Cho phép `MESSAGE` và `SUBSCRIBE` bằng một rule rộng | Không tách thao tác gửi và đọc | Dùng `simpMessageDestMatchers` và `simpSubscribeDestMatchers` |
| Client có thể gửi trực tiếp đến `/topic/**` | Không có rule chặn `MESSAGE` broker destination | Từ chối `MESSAGE` đến `/topic/**` và `/queue/**` |
| User đọc được topic của người khác | Subscribe matcher quá rộng hoặc thiếu kiểm tra membership | Cấp quyền theo destination/tài nguyên và xác minh membership |
| User có `chat:send` nhưng cũng subscribe được `/app/**` | Matcher destination không giới hạn đúng loại message | Dùng matcher riêng cho `MESSAGE` và `SUBSCRIBE` |
| Chỉ kiểm tra HTTP endpoint mà quên STOMP | Inbound message là một bề mặt bảo mật riêng | Bật `@EnableWebSocketSecurity` và cấu hình message authorization |
| Kết nối bị từ chối ở CONNECT | Thiếu authentication hoặc CSRF token | Kiểm tra HTTP Principal, CSRF token và CONNECT headers |
| Thêm endpoint mới nhưng không có rule | Chính sách không có default deny | Dùng `anyMessage().denyAll()` và thêm rule cụ thể |
| User bị thu hồi quyền nhưng vẫn nhận message | Subscription đã được thiết lập trước đó | Hủy subscription/session hoặc cập nhật cơ chế thu hồi |
| Tin username/role trong STOMP header | Client có thể giả mạo metadata | Dùng Principal đã xác thực và authority do server cấp |

## 11. Bài tập tự kiểm tra

Một ứng dụng hỗ trợ phòng chat có các quyền:

- `chat:send`: gửi message vào controller.
- `chat:read`: đọc các topic chat.
- `notification:read`: đọc notification riêng.

Chính sách yêu cầu:

1. User có `chat:send` được gửi `SEND` đến `/app/chat/**`.
2. User có `chat:read` được `SUBSCRIBE` đến `/topic/chat/**`.
3. User có `notification:read` được `SUBSCRIBE` đến `/user/queue/notifications`.
4. Mọi `SEND` trực tiếp đến `/topic/**` hoặc `/queue/**` bị từ chối.
5. Các destination và loại message chưa được khai báo đều bị từ chối.

Hãy trả lời:

1. Vì sao `simpMessageDestMatchers("/app/chat/**")` phù hợp với quyền gửi?
2. Vì sao cần `simpSubscribeDestMatchers("/topic/chat/**")` cho quyền đọc?
3. Một user có cả `chat:send` và `chat:read` có được `SEND` trực tiếp đến `/topic/chat/room-1` không?
4. Vì sao `anyMessage().denyAll()` hữu ích khi ứng dụng thêm endpoint?
5. Nếu user bị xóa khỏi phòng sau khi đã subscribe, ứng dụng cần xử lý điều gì?

Đáp án:

1. Matcher này chỉ áp dụng cho message loại `MESSAGE`, tức frame STOMP `SEND`.
2. Matcher này chỉ áp dụng cho message loại `SUBSCRIBE`, tức thao tác đăng ký nhận dữ liệu.
3. Không. Rule deny `MESSAGE` đến broker destination vẫn chặn thao tác đó; quyền đọc chỉ cấp cho `SUBSCRIBE`.
4. Nó ngăn các message chưa được khai báo tự động được phép khi ứng dụng phát triển.
5. Cần thu hồi subscription/session hoặc có cơ chế bảo đảm user không tiếp tục nhận dữ liệu sau khi mất quyền.

## 12. Ghi nhớ

- `SEND` được ánh xạ thành `SimpMessageType.MESSAGE`; `SUBSCRIBE` được ánh xạ thành `SimpMessageType.SUBSCRIBE`.
- `/app/**` dành cho lệnh gửi vào controller; `/topic/**` và `/queue/**` thường dành cho broker.
- Dùng `simpMessageDestMatchers` để kiểm soát quyền gửi và `simpSubscribeDestMatchers` để kiểm soát quyền đọc.
- Chặn `MESSAGE` trực tiếp đến broker destination để client không thể giả mạo message server.
- Chỉ cho phép `SUBSCRIBE` đến các destination user có quyền đọc.
- `@EnableWebSocketSecurity` bảo vệ inbound channel và yêu cầu CSRF token cho CONNECT theo mặc định.
- Spring Security kiểm soát subscription inbound; không mặc định authorization trên từng outbound message.
- Destination authorization cần kết hợp với kiểm tra membership, ownership và quyền nghiệp vụ.
- Dùng default deny để các endpoint mới không vô tình mở quyền.

## Tài liệu tham khảo

- Spring Security Reference — [WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html)
- Spring Security API — [MessageMatcherDelegatingAuthorizationManager.Builder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/messaging/access/intercept/MessageMatcherDelegatingAuthorizationManager.Builder.html)
- Spring Framework Reference — [STOMP Authorization](https://docs.spring.io/spring/reference/web/websocket/stomp/authorization.html)
- Spring Framework Reference — [Flow of Messages](https://docs.spring.io/spring/reference/web/websocket/stomp/message-flow.html)
- Spring Security API — [EnableWebSocketSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/socket/EnableWebSocketSecurity.html)
