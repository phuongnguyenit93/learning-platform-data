# @SendToUser và phản hồi cho người dùng gửi yêu cầu trong Spring STOMP

## Mục tiêu

Trong ứng dụng Spring WebSocket dùng STOMP, nhiều message được gửi tới một nhóm subscriber qua destination như **/topic/announcements**. Nhưng có những thao tác chỉ cần trả kết quả cho người đã gửi yêu cầu: kiểm tra trạng thái đơn hàng, xem số dư, thực hiện giao dịch, tải dữ liệu riêng hoặc nhận lỗi xác thực.

Spring hỗ trợ mô hình này bằng **user destination** và hai cách gửi phổ biến:

- **@SendToUser**: gắn phản hồi của một phương thức xử lý STOMP với người dùng của message hiện tại.
- **SimpMessagingTemplate.convertAndSendToUser(...)**: cho phép service hoặc thành phần bất kỳ gửi message tới một người dùng được xác định ở phía server.

Điểm quan trọng là client gửi yêu cầu tới destination ứng dụng, còn Spring phân giải destination phản hồi theo danh tính hoặc session của người nhận. Client không cần tự xây dựng tên queue nội bộ của từng người dùng.

## 1. User destination là gì?

Spring STOMP nhận diện tiền tố user destination, mặc định là **/user/**. Client có thể subscribe một destination chung như:

~~~text
SUBSCRIBE
id:private-replies
destination:/user/queue/replies

^@
~~~

Nhiều người dùng có thể subscribe cùng đường dẫn logic **/user/queue/replies**. Spring dùng **UserDestinationMessageHandler** để chuyển đường dẫn đó thành destination thực tế riêng cho session hoặc người dùng. Ví dụ, destination nội bộ có thể được biến đổi thành một đường dẫn queue có phần định danh session, giúp các user không nhận nhầm message của nhau.

Ở phía gửi, ứng dụng có thể nhắm tới một user cụ thể bằng cách gửi tới destination logic gắn với tên user, hoặc dùng **@SendToUser** để nhắm tới user của message hiện tại. Spring ánh xạ destination logic này sang một hoặc nhiều destination thực tế tương ứng với các session đang hoạt động.

Cần phân biệt:

- **Destination client subscribe**: thường là **/user/queue/replies**.
- **Destination gửi bằng @SendToUser**: thường là **/queue/replies**; annotation tự áp dụng user destination prefix.
- **Destination gửi bằng convertAndSendToUser**: truyền username riêng và destination đuôi như **/queue/replies**; template xử lý phần user prefix.

Không thêm username vào đường dẫn subscribe phía client. Không tự tạo destination nội bộ theo session ID. Việc phân giải là trách nhiệm của Spring.

## 2. Luồng request-response cho người gửi

Giả sử client đã kết nối STOMP với danh tính đã xác thực, subscribe **/user/queue/order-replies**, rồi gửi yêu cầu kiểm tra đơn hàng tới **/app/orders.check**.

~~~text
Client
  | SUBSCRIBE /user/queue/order-replies
  | SEND      /app/orders.check
  v
Spring clientInboundChannel
  |
  v
@MessageMapping("/orders.check")
  |
  v
Xử lý nghiệp vụ và tạo OrderReply
  |
  v
@SendToUser("/queue/order-replies")
  |
  v
UserDestinationMessageHandler
  |
  v
Broker -> destination thực tế của user/session
  |
  v
clientOutboundChannel -> WebSocket -> Client nhận phản hồi
~~~

Các bước chi tiết:

1. Client mở kết nối STOMP. Khi xác thực thành công, Spring gắn **Principal** tương ứng với kết nối.
2. Client đăng ký nhận phản hồi tại **/user/queue/order-replies**.
3. Client gửi frame SEND tới **/app/orders.check**.
4. Spring đưa message vào **clientInboundChannel**. Application destination prefix **/app** định tuyến message tới controller; phần còn lại **/orders.check** được so khớp với **@MessageMapping**.
5. Controller thực hiện nghiệp vụ và trả về một đối tượng phản hồi.
6. **@SendToUser("/queue/order-replies")** yêu cầu Spring gửi giá trị trả về tới user gắn với message hiện tại.
7. Spring phân giải user destination thành destination thực tế cho các session phù hợp. Broker chuyển message tới subscriber và Spring gửi frame MESSAGE về WebSocket client.

Như vậy, controller không phải tự tìm queue vật lý của client. Nó chỉ trả về dữ liệu và chỉ định destination logic dành cho user.

## 3. Ví dụ dùng @SendToUser

Ví dụ sau minh họa yêu cầu kiểm tra đơn hàng. Client gửi mã đơn hàng; server xác định danh tính từ **Principal**, gọi service và trả kết quả riêng cho user đã gửi yêu cầu.

~~~java
public record OrderCheckRequest(String orderId) {}

public record OrderCheckReply(
        String orderId,
        String status,
        String checkedBy) {}

@Controller
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("/orders.check")
    @SendToUser("/queue/order-replies")
    public OrderCheckReply check(
            @Payload OrderCheckRequest request,
            Principal principal) {

        String username = principal.getName();
        return orderService.check(request.orderId(), username);
    }
}
~~~

Đây là đoạn minh họa controller và DTO; nó giả định ứng dụng đã khai báo bean **OrderService**, cấu hình STOMP endpoint, message converter và xác thực. Các import và phần triển khai nghiệp vụ của service được lược bỏ.

Với cấu hình application prefix **/app**, client gửi tới **/app/orders.check** sẽ gọi phương thức **check**. Giá trị trả về được gửi tới user destination dựa trên Principal của message. Nếu client subscribe **/user/queue/order-replies**, client đó nhận được phản hồi.

Một client không được phép chọn username bằng cách tự gửi trường **checkedBy** trong payload. Server lấy username từ **Principal** đã được xác thực và tự gắn vào kết quả. Nếu kết nối không có Principal, không gọi **principal.getName()** trực tiếp; hãy chọn chính sách xác thực hoặc xử lý session ẩn danh phù hợp.

## 4. broadcast: gửi tới mọi session hay chỉ session yêu cầu?

Một người dùng có thể mở nhiều kết nối, ví dụ cùng tài khoản đăng nhập trên hai tab trình duyệt hoặc trên máy tính và điện thoại.

Mặc định, **@SendToUser** có **broadcast=true**. Nếu user có nhiều session đang subscribe cùng destination, Spring gửi phản hồi tới tất cả session đó. Đây thường là hành vi hợp lý khi mọi thiết bị của cùng người dùng đều cần đồng bộ trạng thái.

Nếu phản hồi chỉ dành cho kết nối đã gửi yêu cầu, đặt **broadcast=false**:

~~~java
@MessageMapping("/orders.check")
@SendToUser(value = "/queue/order-replies", broadcast = false)
public OrderCheckReply check(
        @Payload OrderCheckRequest request,
        Principal principal) {

    return orderService.check(request.orderId(), principal.getName());
}
~~~

So sánh:

| Cấu hình | Phạm vi nhận |
|---|---|
| **@SendToUser("/queue/replies")** | Mặc định gửi tới mọi session của user đang subscribe destination đó |
| **@SendToUser(value="/queue/replies", broadcast=false)** | Chỉ session đã gửi message được xử lý nhận phản hồi |
| User destination từ session chưa xác thực | Spring xử lý như phạm vi session gửi message, tương tự broadcast=false |

Với thao tác request-response cho một tab hoặc một kết nối cụ thể, **broadcast=false** thường là lựa chọn rõ ràng. Với thông báo cá nhân cần đồng bộ trên tất cả thiết bị của cùng tài khoản, giữ mặc định broadcast=true.

Lưu ý: broadcast=false chỉ giới hạn session nhận. Nó không thay thế việc kiểm tra quyền truy cập dữ liệu, xác thực người dùng hoặc kiểm soát subscription.

## 5. Gửi chủ động bằng SimpMessagingTemplate

Không phải lúc nào phản hồi cũng được tạo trực tiếp từ giá trị trả về của **@MessageMapping**. Một service có thể gửi thông báo sau khi xử lý xong, sau khi nhận sự kiện từ hệ thống khác hoặc khi một tác vụ nền hoàn tất.

Dùng **SimpMessagingTemplate.convertAndSendToUser(username, destination, payload)**:

~~~java
@Service
public class OrderNotificationService {

    private final SimpMessagingTemplate messagingTemplate;

    public OrderNotificationService(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void sendStatus(String username, OrderStatus status) {
        messagingTemplate.convertAndSendToUser(
                username,
                "/queue/order-status",
                status);
    }
}
~~~

Ở đây:

- Tham số đầu tiên là tên user mà Spring dùng để tìm các session đang hoạt động. Với user đã xác thực, giá trị này thường khớp với **Principal.getName()**.
- Tham số thứ hai là phần destination phía sau user prefix, ví dụ **/queue/order-status**. Không truyền **/user/{username}** vào tham số này.
- Tham số thứ ba là payload được chuyển thành message bằng message converter.

Client nhận thông báo bằng cách subscribe **/user/queue/order-status**. Spring ánh xạ message tới session của user có tên tương ứng.

Một controller có thể lấy username từ Principal rồi truyền cho service:

~~~java
@MessageMapping("/orders.refresh")
public void refresh(
        @Payload OrderRefreshRequest request,
        Principal principal) {

    OrderStatus status = orderService.refresh(request.orderId(), principal.getName());
    notificationService.sendStatus(principal.getName(), status);
}
~~~

Ví dụ này dùng **void** vì service gửi message bằng template. Nếu phương thức vừa trả về giá trị vừa gọi template, hãy xác định rõ có cần hai phản hồi hay không để tránh gửi trùng.

Khác biệt giữa hai cách gửi:

| Tiêu chí | @SendToUser | convertAndSendToUser |
|---|---|---|
| Người nhận | User gắn với message hiện tại | Username được truyền vào |
| Nơi thường dùng | Phương thức xử lý STOMP hoặc exception handler | Service, listener, job hoặc thành phần bất kỳ |
| Nội dung gửi | Giá trị trả về của phương thức | Payload truyền vào template |
| Chọn một session của request hiện tại | Có thuộc tính broadcast=false | Cần thiết kế theo session hoặc ngữ cảnh gửi riêng; template theo username thường nhắm tới các session của user |
| Phù hợp khi | Trả lời ngay yêu cầu đang được xử lý | Gửi thông báo chủ động hoặc gửi từ quy trình nền |

## 6. Phản hồi lỗi cho đúng người gửi yêu cầu

Một lỗi nghiệp vụ phát sinh khi xử lý STOMP cũng có thể được gửi riêng tới người gửi yêu cầu. Dùng **@MessageExceptionHandler** kết hợp với **@SendToUser**:

~~~java
public record OrderError(String code, String message) {}

@Controller
public class OrderController {

    @MessageMapping("/orders.cancel")
    public void cancel(@Payload CancelOrderRequest request, Principal principal) {
        orderService.cancel(request.orderId(), principal.getName());
    }

    @MessageExceptionHandler(OrderNotCancellableException.class)
    @SendToUser(value = "/queue/errors", broadcast = false)
    public OrderError handleOrderError(OrderNotCancellableException exception) {
        return new OrderError("ORDER_NOT_CANCELLABLE", exception.getMessage());
    }
}
~~~

Đây là đoạn minh họa; các DTO, service và exception cần được khai báo trong ứng dụng. Client subscribe **/user/queue/errors** để nhận lỗi cho session đã gửi yêu cầu. **broadcast=false** tránh gửi lỗi của thao tác trên một tab tới tất cả tab khác đang đăng nhập cùng user.

Có thể khai báo nhiều **@MessageExceptionHandler** theo loại exception hoặc tạo một handler chung. Chỉ trả về thông tin lỗi mà client cần biết; không gửi stack trace, câu SQL, token, thông tin xác thực hoặc chi tiết nội bộ của hệ thống.

Nếu handler lỗi cần gửi tới mọi session của user, có thể bỏ **broadcast=false**. Chọn phạm vi dựa trên ý nghĩa của lỗi: lỗi của một thao tác riêng thường chỉ nên trả về session yêu cầu.

## 7. Cấu hình STOMP và subscription phía client

Một cấu hình cơ bản:

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

Spring dùng **/user/** làm user destination prefix mặc định. Nếu ứng dụng thay prefix bằng **setUserDestinationPrefix(...)**, client subscription và cách phân giải destination phải dùng đúng prefix đã cấu hình. Broker cần xử lý được destination thực tế mà Spring tạo ra; simple broker và broker relay đều có thể được cấu hình cho các luồng này.

Ví dụ frame STOMP cho client:

~~~text
SUBSCRIBE
id:order-replies
destination:/user/queue/order-replies

^@

SEND
destination:/app/orders.check
content-type:application/json

{"orderId":"ORD-42"}

^@
~~~

Trong ứng dụng thực tế, client nên đăng ký subscription trước khi gửi yêu cầu để không bỏ lỡ phản hồi nhanh. Khi dùng thư viện như **@stomp/stompjs**, callback của subscription nhận frame MESSAGE; client giải mã body theo định dạng mà server gửi.

Không subscribe vào **/queue/order-replies** trực tiếp nếu đây là user destination. Cũng không tự subscribe vào **/user/alice/queue/order-replies**. Client dùng đường dẫn logic **/user/queue/order-replies**; Spring đảm nhiệm phân giải.

## 8. Xác thực và phân quyền

User destination dựa trên danh tính mà Spring gắn vào message hoặc session. Vì vậy, luồng xác thực phải được thiết lập đúng trước khi dùng **@SendToUser** hoặc **convertAndSendToUser**.

Các nguyên tắc quan trọng:

1. Dùng Principal từ kết nối đã xác thực để xác định user gửi yêu cầu.
2. Không tin username, userId, role hoặc trường người gửi do client đặt trong payload.
3. Khi dùng token trong STOMP CONNECT, xác thực token ở phía server bằng cơ chế phù hợp và gắn Authentication/Principal vào message trước khi controller xử lý.
4. Kiểm soát riêng quyền SEND và SUBSCRIBE. Một user có quyền gửi yêu cầu tới **/app/** không có nghĩa họ được subscribe mọi user destination.
5. Chỉ cho phép client subscribe vào destination cá nhân của chính họ thông qua **/user/**. Không mở quyền subscribe vào queue nội bộ đã được phân giải hoặc destination dùng chung chứa dữ liệu của nhiều user.
6. Kiểm tra quyền nghiệp vụ trước khi đọc hoặc gửi dữ liệu riêng, kể cả khi message được gửi bằng **convertAndSendToUser**.

Ví dụ, Spring Security có thể cho phép người dùng đã xác thực SUBSCRIBE vào **/user/queue/**, cho phép MESSAGE tới các application destination được chỉ định, và từ chối MESSAGE trực tiếp tới broker destination nếu client không có nhu cầu publish. Quy tắc cụ thể phụ thuộc vào ma trận quyền của ứng dụng.

**@SendToUser** chỉ chọn nơi gửi. Annotation không tự xác minh rằng người gửi có quyền xem đơn hàng, tài khoản hoặc tài nguyên trong payload. Controller/service vẫn phải kiểm tra quyền trên từng tài nguyên.

## 9. Nhiều session và triển khai nhiều instance

Với một user đăng nhập nhiều nơi, Spring duy trì thông tin session để ánh xạ user destination. Theo mặc định, gửi tới user đã xác thực có thể phân phối tới mọi session của user đang subscribe destination. Thuộc tính **broadcast=false** của **@SendToUser** giới hạn phản hồi theo session gửi yêu cầu.

Trong triển khai nhiều instance, mỗi node có thể chỉ biết các WebSocket session được kết nối với node đó. Nếu user destination cần được phân giải xuyên node, cần cấu hình cơ chế chia sẻ user registry và phát thông báo user destination chưa phân giải theo hướng dẫn của Spring. Broker relay giúp chuyển message qua broker bên ngoài, nhưng riêng việc dùng broker relay không tự động bảo đảm mọi node đã chia sẻ đầy đủ thông tin session.

Khi thiết kế hệ thống phân tán, hãy kiểm tra các trường hợp:
- User gửi yêu cầu tới node A nhưng phiên nhận đang được quản lý bởi node B.
- User đăng nhập đồng thời trên nhiều node.
- Một node mất kết nối trong lúc gửi phản hồi.
- Client reconnect và tạo session mới.
- Phản hồi là dữ liệu tạm thời hay cần được lưu bền để client lấy lại sau reconnect.

STOMP WebSocket không tự đảm bảo một phản hồi sẽ được lưu và phát lại cho client offline. Nếu yêu cầu cần độ tin cậy sau khi ngắt kết nối, hãy lưu trạng thái/kết quả trong hệ thống nghiệp vụ và cung cấp API hoặc cơ chế đồng bộ lại khi client reconnect.

## 10. Lỗi thường gặp và cách chẩn đoán

**Client không nhận được phản hồi**

- Kiểm tra client đã SUBSCRIBE **/user/queue/...** trước khi gửi request chưa.
- Kiểm tra destination trong **@SendToUser** có khớp với phần queue mà client subscribe hay không. Annotation thường nhận **/queue/replies**, còn client subscribe **/user/queue/replies**.
- Kiểm tra Principal của message có tồn tại và tên user có khớp với user session đã kết nối không.
- Kiểm tra broker prefix có chứa phần queue cần dùng, chẳng hạn **/queue**.
- Kiểm tra message converter, log của controller, broker channel và outbound channel.

**Một phản hồi xuất hiện ở nhiều tab**

- Kiểm tra **broadcast** của **@SendToUser**. Mặc định là true và nhắm tới các session của cùng user.
- Nếu phản hồi thuộc về riêng thao tác trong tab hiện tại, đặt **broadcast=false**.
- Nếu đây là thông báo cá nhân cần đồng bộ giữa thiết bị, giữ broadcast mặc định.

**Phản hồi gửi nhầm user**

- Không lấy recipient từ một trường tự do trong payload nếu không có kiểm tra quyền.
- Với **@SendToUser**, kiểm tra danh tính gắn với STOMP session và Principal.
- Với **convertAndSendToUser**, kiểm tra username truyền vào và cách hệ thống chuẩn hóa tên đăng nhập.

**Dùng convertAndSendToUser nhưng không có subscriber nhận được**

- Tham số username phải khớp với tên user Spring đang quản lý, thường là **Principal.getName()**.
- Destination truyền vào phải là phần đuôi như **/queue/updates**, không tự thêm **/user/{username}**.
- Client phải subscribe **/user/queue/updates**.
- Kiểm tra user session còn hoạt động và đã subscribe đúng destination.

**Người dùng ẩn danh không nhận được phản hồi**

- Một session WebSocket không gắn user đã xác thực vẫn có thể dùng user destination. Với **@SendToUser**, Spring xử lý theo session gửi message, tương tự **broadcast=false**.
- Không gọi **principal.getName()** khi Principal có thể null.
- Nếu cần gửi chủ động từ service tới người dùng ẩn danh sau khi xử lý bất đồng bộ, cần thiết kế cách định danh và vòng đời session rõ ràng.

**Thông báo riêng tư bị lộ**

- Kiểm tra quyền SUBSCRIBE vào **/user/** và từ chối truy cập queue nội bộ.
- Không gửi dữ liệu nhạy cảm qua destination broadcast.
- Kiểm tra quyền nghiệp vụ trước khi phát message và không dựa vào username do client tự khai báo.

## 11. Chọn cách gửi phù hợp

| Nhu cầu | Cách triển khai |
|---|---|
| Trả kết quả của một STOMP request về user gửi request | **@MessageMapping** + **@SendToUser** |
| Chỉ trả về tab/session đã gửi request | **@SendToUser(..., broadcast=false)** |
| Đồng bộ thông báo tới mọi session của cùng user | **@SendToUser** mặc định hoặc **convertAndSendToUser** |
| Gửi thông báo từ service hoặc tác vụ nền tới username cụ thể | **SimpMessagingTemplate.convertAndSendToUser** |
| Trả lỗi của thao tác STOMP cho session gây ra lỗi | **@MessageExceptionHandler** + **@SendToUser(broadcast=false)** |
| Gửi thông báo công khai cho mọi subscriber | **@SendTo** hoặc **convertAndSend** tới **/topic/** |

Có thể ghi nhớ quy tắc sau: **@SendTo** thường dùng để phát kết quả tới destination chung; **@SendToUser** dùng để gửi kết quả tới user của message đang xử lý; **convertAndSendToUser** dùng khi một thành phần phía server cần chủ động gửi tới một username cụ thể. Cả ba đều cần được đặt trong một cấu hình định tuyến và phân quyền rõ ràng.

## Tài liệu tham khảo

- Spring Framework — User Destinations: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html
- Spring Framework — Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html
- Spring Framework — Sending Messages: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html
- Spring Framework — Authorization: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html
- Spring Security — WebSocket Security: https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html
