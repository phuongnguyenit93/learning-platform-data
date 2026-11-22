# User registry và user destination trong cụm Spring Messaging

Trong ứng dụng Spring STOMP, user destination cho phép gửi message tới các session thuộc một người dùng mà không cần để client biết tên queue vật lý. Khi ứng dụng chạy trên nhiều application server, mỗi node chỉ trực tiếp quản lý các WebSocket session đang kết nối với node đó. Để gửi đúng người dùng dù họ đang kết nối ở node khác, Spring cung cấp `SimpUserRegistry`, `MultiServerUserRegistry`, `UserRegistryMessageHandler` và hai cơ chế broadcast dành cho cụm.

Điểm cốt lõi: **user destination là lớp định tuyến theo người dùng/session; user registry là dữ liệu về các user/session/subscription đang kết nối.** Trong cluster, registry broadcast giúp các node biết session ở node khác, còn unresolved-destination broadcast cho node khác cơ hội xử lý message mà node hiện tại chưa phân giải được.

## 1. User destination giải quyết vấn đề gì?

Client đăng ký một logical destination như `/user/queue/notifications`. Spring nhận diện tiền tố `/user/` và `UserDestinationMessageHandler` chuyển nó thành một destination thực tế có suffix riêng cho session, ví dụ `/queue/notifications-useri9oqdfzo`. Nhờ suffix theo session, hai người dùng có thể subscribe cùng tên logic mà không nhận nhầm message của nhau.

Ở chiều gửi, ứng dụng gửi tới `/user/{username}/queue/notifications`. Spring tìm các session đang hoạt động của user đó trong `SimpUserRegistry`, rồi chuyển message tới destination tương ứng với từng session. `DefaultUserDestinationResolver` là resolver mặc định; nó dựa trên `SimpUserRegistry` để tìm session và tạo một hoặc nhiều destination thực tế.

```text
Client A (Principal alice)                 Spring application
SUBSCRIBE /user/queue/notifications  ----> UserDestinationMessageHandler
                                            |
                                            v
                                      SimpUserRegistry
                                            |
                                            v
                                      session id A-17
                                            |
                                            v
                                      /queue/notifications-userA17

Application service
convertAndSendToUser("alice", "/queue/notifications", payload)
                                            |
                                            v
                                      resolve alice sessions
                                            |
                                            v
                                      send to actual session destination
```

Đường dẫn `/user/...` là destination logic được Spring xử lý. Broker không nên nhận `/user` như một destination thông thường; hãy cấu hình application và broker prefixes đúng để `UserDestinationMessageHandler` xử lý tiền tố này trước khi message tới broker.

## 2. Những thành phần trong user registry

| Thành phần | Vai trò |
| --- | --- |
| `SimpUserRegistry` | Abstraction lưu các user đang kết nối, session của mỗi user và subscription trong session |
| `SimpUser` | Đại diện cho một user đã kết nối; cung cấp các session của user |
| `SimpSession` | Đại diện cho một WebSocket/STOMP session |
| `SimpSubscription` | Đại diện cho một subscription thuộc session |
| `UserDestinationResolver` | Chuyển logical user destination thành một hoặc nhiều destination thực tế |
| `DefaultUserDestinationResolver` | Resolver mặc định, tra cứu session qua `SimpUserRegistry` |
| `UserDestinationMessageHandler` | Nhận message có tiền tố user, phân giải destination và chuyển tiếp tới broker |
| `MultiServerUserRegistry` | Kết hợp local registry với các remote registry nhận qua broadcast |
| `UserRegistryMessageHandler` | Phát nội dung local registry định kỳ và nhận registry broadcast từ các server khác |

Trong một node đơn, registry chủ yếu phản ánh session được tạo trên node đó. Các API như `getUserCount()`, `getUsers()` và `findSubscriptions(...)` hữu ích để chẩn đoán trạng thái session/subscription. Không nên dùng registry làm nguồn xác thực hoặc dữ liệu hồ sơ người dùng; quyền truy cập vẫn phải được kiểm tra bằng security principal và authorization.

## 3. Vì sao registry cục bộ không đủ trong cluster?

Giả sử có hai application server A và B cùng dùng một broker:

```text
Browser của alice ---- WebSocket ----> App Server A
Browser của bob   ---- WebSocket ----> App Server B

App Server A ---- STOMP broker relay ----+
                                         +---- Shared STOMP broker
App Server B ---- STOMP broker relay ----+
```

Node A biết các session của alice nhưng không tự biết session của bob ở B. Node B biết session của bob nhưng không tự biết session của alice ở A. Nếu một service trên B gọi `convertAndSendToUser("alice", ...)`, registry cục bộ của B có thể không tìm thấy alice. Nếu chỉ có local registry, message có thể không được gửi tới session đang kết nối ở A.

Trong môi trường nhiều node, Spring có thể kết hợp registry từ xa thông qua `MultiServerUserRegistry`. `UserRegistryMessageHandler` gửi snapshot nội dung local registry lên broker theo một destination broadcast và lắng nghe các broadcast từ node khác. Khi nhận được snapshot, `MultiServerUserRegistry` cập nhật tập remote registry mà nó dùng để tra cứu user/session.

Registry broadcast là cơ chế chia sẻ thông tin presence/session giữa các application server. Nó không đồng bộ trạng thái nghiệp vụ, không lưu trữ user lâu dài và không thay thế cơ chế authentication. Dữ liệu registry có thể trễ giữa các lần broadcast; do đó không xem nó là một distributed lock hoặc một nguồn presence strongly consistent.

## 4. Hai broadcast có nhiệm vụ khác nhau

Spring cung cấp hai destination cấu hình riêng trên `StompBrokerRelayRegistration`:

| Cấu hình | Nội dung được broadcast | Mục đích |
| --- | --- | --- |
| `setUserRegistryBroadcast(...)` | Nội dung local user registry của mỗi node | Cho các node khác biết user/session/subscription đang kết nối ở node này; dữ liệu được tổng hợp trong `MultiServerUserRegistry` |
| `setUserDestinationBroadcast(...)` | Message có user destination chưa được node hiện tại phân giải | Cho các node khác thử phân giải destination; node đang giữ session của user có thể xử lý message |

Ví dụ: B nhận yêu cầu gửi tới alice nhưng registry chưa có thông tin mới về session ở A. Với `userDestinationBroadcast`, B phát message unresolved lên broker. Các node khác nhận broadcast và thử phân giải; A có session của alice nên có thể chuyển message tới session đó. Cơ chế này giúp xử lý trường hợp registry chưa kịp cập nhật hoặc thông tin user ở node hiện tại chưa đủ.

Không nhầm hai cấu hình: registry broadcast trao đổi thông tin session; unresolved-destination broadcast chuyển một message cụ thể để node khác thử định tuyến. Hai destination nên khác nhau, được broker fan-out tới các node ứng dụng và được bảo vệ như kênh nội bộ.

## 5. Cấu hình cluster với external STOMP broker relay

Simple broker tích hợp trong Spring chạy trong bộ nhớ của một application instance và không phù hợp để clustering. Với nhiều application server, dùng một broker ngoài hỗ trợ STOMP và cấu hình mỗi node relay tới cùng broker hoặc cụm broker dùng chung.

Ví dụ Java configuration:

```java
@Configuration
@EnableWebSocketMessageBroker
public class ClusterWebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");

        registry.enableStompBrokerRelay("/topic", "/queue")
                .setUserRegistryBroadcast("/topic/internal-simp-user-registry")
                .setUserDestinationBroadcast("/topic/internal-unresolved-user");
    }
}
```

Đoạn cấu hình dùng `enableStompBrokerRelay`, vì các tùy chọn `setUserRegistryBroadcast` và `setUserDestinationBroadcast` thuộc `StompBrokerRelayRegistration`. Mỗi node chạy cùng cấu hình, cùng destination prefix và cùng broker cluster. Hãy thay địa chỉ, thông tin xác thực và virtual host của relay theo môi trường thực tế; không để credential mặc định của broker trong production.

`/topic/internal-simp-user-registry` và `/topic/internal-unresolved-user` chỉ là tên ví dụ. Broker phải hỗ trợ fan-out cho các subscriber của từng node. Không dùng một queue cạnh tranh consumer nếu broker chỉ giao mỗi message cho một consumer; broadcast phải tới được tất cả application server có thể đang giữ WebSocket session.

### 5.1. Các điều kiện để cấu hình hoạt động

1. Tất cả application server phải relay tới cùng một broker hoặc một cụm broker có khả năng chia sẻ các destination broadcast.
2. Mỗi node phải cấu hình cùng `userRegistryBroadcast` và `userDestinationBroadcast` để nhận và phát trên cùng các destination.
3. Broker phải fan-out registry snapshots và unresolved messages tới các node cần nhận.
4. Mỗi node phải dùng cùng quy tắc xác định user destination prefix, application prefix và broker prefix.
5. Principal của cùng một người dùng phải tạo ra cùng một destination username trên mọi node.
6. Broker ACL và Spring message authorization phải giới hạn các destination nội bộ; client thông thường không được subscribe hoặc publish vào registry broadcast.
7. Kiểm tra broker có tự xóa queue/destination riêng theo session khi session kết thúc hay cần cấu hình dọn dẹp.

## 6. Định danh user phải nhất quán giữa các node

`convertAndSendToUser(user, destination, payload)` tìm user theo tên mà Spring lấy từ `Principal` (hoặc destination username provider). Vì vậy, cùng một tài khoản phải có cùng định danh trên mọi application server. Nếu node A nhìn user là `alice` còn node B nhìn user là `tenant-7:alice`, registry và message sender có thể không tìm thấy cùng một user.

Nếu `Principal.getName()` đã là định danh toàn cục, có thể dùng trực tiếp. Nếu tên principal chỉ duy nhất trong một tenant hoặc realm, triển khai `DestinationUserNameProvider` để cung cấp tên duy nhất dùng riêng cho user destination:

```java
public final class TenantPrincipal implements Principal, DestinationUserNameProvider {
    private final String subject;
    private final String tenantId;

    public TenantPrincipal(String subject, String tenantId) {
        this.subject = subject;
        this.tenantId = tenantId;
    }

    @Override
    public String getName() {
        return this.subject;
    }

    @Override
    public String getDestinationUserName() {
        return this.tenantId + ":" + this.subject;
    }
}
```

Đây là class minh họa, cần được tạo từ danh tính đã xác thực ở phía server. `getDestinationUserName()` phải trả về một giá trị ổn định và duy nhất toàn cụm; không dùng chuỗi do client tự gửi lên. Nếu ghép tenant và subject, hãy bảo đảm cách mã hóa không tạo va chạm giữa các cặp giá trị.

## 7. Gửi message tới một user

Client subscribe bằng destination logic:

```javascript
stompClient.subscribe("/user/queue/notifications", frame => {
    const notification = JSON.parse(frame.body);
    renderNotification(notification);
});
```

Application service gửi tới user đã xác thực:

```java
@Service
public class NotificationService {
    private final SimpMessagingTemplate messagingTemplate;

    public NotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void notifyUser(String destinationUserName, Notification notification) {
        messagingTemplate.convertAndSendToUser(
                destinationUserName, "/queue/notifications", notification);
    }
}
```

`destinationUserName` phải được lấy từ danh tính đã xác thực hoặc từ một user identifier được server kiểm tra. Phần `destination` truyền vào `convertAndSendToUser` không cần thêm `/user/{username}`; template thực hiện việc định tuyến user. Client chỉ subscribe `/user/queue/notifications`.

Với annotated controller, `@SendToUser` gửi response tới user gắn với message đang xử lý:

```java
@Controller
public class NotificationController {

    @MessageMapping("/notifications.ack")
    @SendToUser("/queue/acknowledgements")
    public AckResult acknowledge(AckCommand command, Principal principal) {
        return notificationService.acknowledge(principal.getName(), command);
    }
}
```

Đoạn controller là ví dụ minh họa; service và DTO do ứng dụng định nghĩa. Annotation destination là phần đuôi, không có tiền tố `/user`.

## 8. Một user có nhiều session

Một người dùng có thể mở nhiều tab, nhiều trình duyệt hoặc nhiều thiết bị. `SimpUserRegistry` lưu nhiều session cho cùng user; user destination gửi theo mặc định tới các session của user đang subscribe destination đó.

- `@SendToUser("/queue/notifications")` mặc định broadcast tới các session của user có subscription phù hợp.
- `@SendToUser(destinations = "/queue/errors", broadcast = false)` chỉ gửi tới session phát sinh message đang được xử lý.
- `convertAndSendToUser(...)` định tuyến tới các session hiện hoạt của user; nếu cần một session cụ thể, phải thiết kế session-targeting riêng và kiểm soát quyền truy cập session.

`broadcast=false` hữu ích cho lỗi validation hoặc response riêng của một thao tác từ tab hiện tại. Thông báo cần đồng bộ trên mọi thiết bị của user thường dùng hành vi broadcast mặc định. Hãy chọn semantics theo nghiệp vụ để tránh gửi trùng hoặc làm lộ response riêng tư sang session khác.

## 9. Vòng đời session, registry stale và queue cleanup

Registry phản ánh các session đã kết nối và subscription mà Spring quan sát được. Khi WebSocket đóng, Spring phát sự kiện session disconnect và cập nhật local registry. Trong cluster, node khác chỉ biết thay đổi sau khi nhận cập nhật registry broadcast tiếp theo. Vì vậy trong một khoảng ngắn, node khác có thể nhìn thấy session đã đóng hoặc chưa thấy session mới.

Ứng dụng cần xử lý trường hợp stale presence:

- Một user không còn session nào: gửi user destination có thể không tìm được target. Xác định rõ message sẽ bị bỏ, lưu lại để gửi sau, hay chuyển sang notification bền vững.
- Node chết đột ngột: không có disconnect event bình thường; remote registry có thể giữ snapshot cũ trong thời gian giới hạn. Theo dõi thời điểm cập nhật và cấu hình thời hạn/cleanup phù hợp phiên bản Spring.
- User reconnect vào node khác: session id mới được đăng ký; message mới phải phân giải theo session hiện hành, không dựa vào session cũ.
- Broker giữ queue vật lý riêng: kiểm tra cơ chế auto-delete hoặc purge của broker. Spring documentation nêu ví dụ RabbitMQ có thể tạo auto-delete queue với destination dạng `/exchange/amq.direct/...`; ActiveMQ có các tùy chọn dọn destination không hoạt động.

Không coi user registry là hộp thư bền vững. Nếu notification phải được nhận kể cả khi user offline, lưu notification trong database hoặc một durable store và để client lấy lại sau khi đăng nhập. User destination chủ yếu phục vụ delivery tới session đang hoạt động.

## 10. Bảo mật các destination trong cluster

Registry broadcast và unresolved-destination broadcast là traffic nội bộ giữa application server. Chúng có thể chứa thông tin về username, session, subscription và payload message chưa phân giải. Hãy áp dụng các biện pháp sau:

- Dùng broker account riêng cho kết nối system của Spring relay; chỉ cấp quyền publish/subscribe vào các destination cần thiết.
- Chặn client STOMP thông thường truy cập `/topic/internal-simp-user-registry` và `/topic/internal-unresolved-user` bằng broker ACL và message authorization.
- Không tin `username`, `tenantId` hoặc `destinationUserName` do client gửi trong body/header. Xác định người gửi từ `Principal` đã xác thực.
- Kiểm tra quyền subscribe vào từng user destination và quyền gửi tới user khác; biết tên user không đồng nghĩa có quyền gửi message.
- Bảo vệ kết nối ứng dụng tới broker bằng TLS và credential phù hợp; không log nội dung registry hoặc payload nhạy cảm.
- Đặt giới hạn kích thước payload và quyền truy cập broker topic; unresolved broadcast không nên trở thành đường vòng để client phát message tùy ý tới toàn cụm.

User destination chỉ là cơ chế định tuyến. Nó không thay thế authentication, authorization, tenant isolation hoặc kiểm tra quyền nghiệp vụ.

## 11. Kiểm thử multi-node

Kiểm thử bằng một application server duy nhất không chứng minh cấu hình cluster hoạt động. Một bài integration test hữu ích cần ít nhất hai Spring application instance và một STOMP broker dùng chung.

### 11.1. Kịch bản cơ bản

1. Khởi động node A và node B với cùng cấu hình broker relay và các broadcast destination.
2. Kết nối client của alice tới `/ws` trên node A; subscribe `/user/queue/notifications`.
3. Đợi tới khi subscription đã được broker xác nhận hoặc client nhận tín hiệu subscription-ready.
4. Gọi `NotificationService` trên node B để gửi message tới destination username của alice.
5. Xác nhận client kết nối A nhận đúng payload; client của user khác không nhận được.
6. Kết nối thêm một session của alice vào node B và xác nhận hành vi mặc định gửi tới các session phù hợp.
7. Kiểm thử `broadcast=false` từ một session và xác nhận session khác của cùng user không nhận response đó.

### 11.2. Kịch bản lỗi và phục hồi

- Gửi tới user khi registry remote chưa cập nhật để xác nhận `userDestinationBroadcast` cho node đang giữ session cơ hội xử lý.
- Ngắt node đang giữ session, chờ registry cập nhật và xác nhận message không tiếp tục được định tuyến tới session cũ.
- Reconnect user vào node khác và gửi lại; xác nhận destination mới được tìm thấy.
- Tắt broker tạm thời rồi khôi phục; kiểm tra relay reconnect, registry broadcast chạy lại và client session có cần reconnect theo thiết kế hay không.
- Thử subscribe/publish vào các internal broadcast destination bằng client không có quyền; xác nhận broker hoặc Spring Security từ chối.
- Kiểm tra queue/destination của broker sau khi disconnect để xác nhận cơ chế auto-delete/purge.

Không dùng `Thread.sleep` cố định để chờ registry hoặc subscription trong test. Dùng receipt, latch, condition hoặc Awaitility với deadline hữu hạn để chờ sự kiện thực tế. Log session id, node id, destination username và correlation id trong test để chẩn đoán.

## 12. Quan sát và chẩn đoán

Để điều tra routing giữa nhiều node, ghi nhận tối thiểu:

| Tín hiệu | Dùng để tìm vấn đề |
| --- | --- |
| Node/server id | Xác định node nào nhận connection và node nào gửi message |
| Destination username | Xác nhận định danh user giống nhau giữa các node |
| User/session count theo node | Phát hiện registry không nhận session hoặc session stale |
| Registry broadcast received/sent và thời điểm snapshot | Phát hiện broker topic hoặc registry synchronization bị gián đoạn |
| Unresolved user destination count | Phát hiện node không tìm được target local/remote |
| Broker availability và relay reconnect | Phát hiện mất kết nối tới broker |
| Session connect/disconnect events | Theo dõi vòng đời session và cleanup |
| Queue/destination count tại broker | Phát hiện queue tạm thời không được xóa |

Không đưa username, session id hoặc destination username có cardinality cao vào metric tag. Dùng log có cấu trúc hoặc trace để tìm một user cụ thể; metric nên dùng tag có tập giá trị nhỏ như `node`, `outcome`, `broker` và `destination_type`.

## 13. Lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
| --- | --- | --- |
| User gửi từ node B không nhận ở session trên A | Chỉ có local registry, registry broadcast chưa cấu hình hoặc chưa nhận được | Dùng external broker relay và cấu hình `setUserRegistryBroadcast` |
| Unresolved user destination không tới node khác | Chưa cấu hình unresolved broadcast hoặc broker không fan-out topic | Cấu hình `setUserDestinationBroadcast` và kiểm tra broker subscription/ACL |
| Một user không được tìm thấy dù đã đăng nhập | `Principal.getName()` hoặc destination username khác nhau giữa các node | Chuẩn hóa principal; dùng `DestinationUserNameProvider` khi cần tên toàn cục |
| Message `/user/...` bị broker xử lý như queue thường | Prefix hoặc user-destination handler cấu hình sai | Kiểm tra application prefix, broker prefix và user destination prefix |
| Một response xuất hiện trên mọi thiết bị dù chỉ cần tab hiện tại | Dùng broadcast mặc định của `@SendToUser` | Đặt `broadcast = false` cho response gắn với session gửi request |
| Message tới user offline bị mất | User destination chỉ định tuyến tới session đang hoạt động | Lưu notification bền vững và cho client truy vấn lại khi reconnect |
| User nhận message hai lần | Nhiều đường broadcast hoặc xử lý retry không idempotent | Kiểm tra registry/unresolved routing, broker topology và message id |
| Broker có nhiều queue không hoạt động | Destination theo session chưa được dọn | Cấu hình auto-delete/purge theo broker và kiểm tra lifecycle |

## 14. Ghi nhớ

- `/user/queue/...` là destination logic; Spring chuyển nó thành destination thực tế theo session.
- `SimpUserRegistry` lưu user, session và subscription trên node; `DefaultUserDestinationResolver` dùng registry để phân giải.
- `MultiServerUserRegistry` kết hợp local registry với remote registry snapshots.
- `UserRegistryMessageHandler` phát và nhận registry broadcast.
- `setUserRegistryBroadcast` chia sẻ thông tin registry; `setUserDestinationBroadcast` chuyển tiếp message chưa phân giải để node khác thử.
- Dùng external STOMP broker relay cho multi-node; simple broker trong bộ nhớ không phù hợp clustering.
- Cùng một user phải có destination username ổn định và duy nhất trên mọi node; dùng `DestinationUserNameProvider` nếu `Principal.getName()` chưa đủ duy nhất.
- User destination mặc định có thể gửi tới nhiều session của cùng user; `broadcast=false` giới hạn response `@SendToUser` về session hiện tại.
- Registry là thông tin presence tạm thời, không phải durable inbox hoặc nguồn authorization.
- Bảo vệ các broadcast destination nội bộ bằng broker ACL và message security; kiểm thử với hai node thật và broker dùng chung.

## Tài liệu tham khảo

- [Spring Framework Reference — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html)
- [Spring Framework Reference — External STOMP Broker Relay](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework API — SimpUserRegistry](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/user/SimpUserRegistry.html)
- [Spring Framework API — MultiServerUserRegistry](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/user/MultiServerUserRegistry.html)
- [Spring Framework API — UserRegistryMessageHandler](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/user/UserRegistryMessageHandler.html)
- [Spring Framework API — DefaultUserDestinationResolver](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/user/DefaultUserDestinationResolver.html)
- [Spring Framework API — DestinationUserNameProvider](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/user/DestinationUserNameProvider.html)
- [Spring Framework API — StompBrokerRelayRegistration](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/config/StompBrokerRelayRegistration.html)