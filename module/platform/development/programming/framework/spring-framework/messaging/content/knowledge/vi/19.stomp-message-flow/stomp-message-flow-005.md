# Đường đi của SEND tới @MessageMapping

Trong Spring STOMP over WebSocket, một frame SEND từ client có thể được chuyển thành lời gọi một method Java có @MessageMapping. Spring thực hiện việc đó qua nhiều thành phần: giải mã STOMP frame, tạo Spring Message, đưa message vào clientInboundChannel, chọn handler theo destination, chuyển đổi payload, phân giải tham số và gọi method.

Sau khi method chạy xong, giá trị trả về có thể được chuyển thành message mới và gửi qua brokerChannel để broker phân phối cho các subscriber. Hiểu rõ luồng này giúp xác định lỗi nằm ở protocol, định tuyến, chuyển đổi payload, method nghiệp vụ hay đường gửi response.

## 1. Toàn cảnh luồng SEND

Giả sử server cấu hình application prefix là /app và simple broker nhận /topic. Client gửi một frame SEND tới /app/orders.create.

~~~text
STOMP client
    |
    | SEND destination:/app/orders.create
    v
WebSocket connection
    |
    v
Sub-protocol handler
    | giải mã STOMP frame
    | tạo Spring Message và bổ sung session/header metadata
    v
clientInboundChannel
    |
    | channel interceptors / security checks
    v
SimpAnnotationMethodMessageHandler
    |
    | kiểm tra application destination prefix
    | bỏ /app khỏi phần dùng để lookup
    | tìm @MessageMapping("/orders.create")
    v
Method argument resolvers
    | đọc payload và headers
    | MessageConverter chuyển JSON thành DTO
    | validate và bind tham số
    v
Controller method
    |
    | gọi service / xử lý nghiệp vụ
    | trả về DTO hoặc chủ động gửi message
    v
Return-value handler
    | MessageConverter chuyển kết quả thành payload
    | xác định destination response
    v
brokerChannel
    |
    v
Simple broker hoặc STOMP broker relay
    | tìm subscriber khớp destination
    v
clientOutboundChannel
    |
    | encode thành STOMP MESSAGE frame
    v
WebSocket connection của subscriber
~~~

Có ba channel thường xuất hiện trong sơ đồ:

| Channel | Vai trò |
|---|---|
| clientInboundChannel | Nhận Spring Message được tạo từ frame của client |
| brokerChannel | Chuyển message từ ứng dụng tới broker |
| clientOutboundChannel | Chuyển message từ broker hoặc ứng dụng tới client |

Simple broker xử lý subscription trong bộ nhớ của Spring. Với broker relay, message được chuyển tiếp tới broker ngoài qua kết nối STOMP/TCP; phần định tuyến subscription và broadcast do broker ngoài đảm nhiệm.

## 2. Điều kiện để SEND được xử lý bởi @MessageMapping

Một method được phát hiện để xử lý message khi controller và mapping được khai báo đúng.

Ví dụ cấu hình:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class StompConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic");
    }
}
~~~

Controller:

~~~java
@Controller
public class OrderController {

    @MessageMapping("/orders.create")
    @SendTo("/topic/orders")
    public OrderCreated create(CreateOrderCommand command) {
        return new OrderCreated("ORD-42", "CREATED");
    }
}
~~~

Client phải kết nối WebSocket tới /ws, hoàn tất STOMP CONNECT, rồi mới gửi SEND:

~~~text
SEND
destination:/app/orders.create
content-type:application/json

{"customerId":"CUS-9","items":[{"sku":"BOOK-1","quantity":2}]}
^@
~~~

Các điều kiện cơ bản:

- Endpoint WebSocket/STOMP đã được đăng ký và client kết nối thành công.
- STOMP frame có command SEND và destination phù hợp.
- Application prefix /app đã được cấu hình.
- Class được đánh dấu @Controller và method có @MessageMapping.
- Destination sau khi bỏ application prefix khớp mapping.
- Payload có thể được chuyển đổi sang kiểu tham số của method.
- Client có quyền gửi message tới destination đó nếu ứng dụng bật authorization.

@MessageMapping xử lý STOMP SEND. SUBSCRIBE được định tuyến theo cơ chế subscription của broker hoặc @SubscribeMapping; CONNECT, DISCONNECT và các frame quản lý session cũng có luồng xử lý riêng.

## 3. Bước 1: WebSocket và STOMP frame được giải mã

Sau HTTP Upgrade handshake, WebSocket connection vận chuyển các frame của STOMP. Thành phần xử lý sub-protocol của Spring nhận WebSocket message, giải mã STOMP command, header và body.

Ví dụ frame SEND:

~~~text
SEND
destination:/app/orders.create
content-type:application/json
content-length:68

{"customerId":"CUS-9","items":[{"sku":"BOOK-1","quantity":2}]}
^@
~~~

STOMP decoder tạo một Spring Message biểu diễn frame. Payload ban đầu có thể vẫn là byte[]; header chứa thông tin như:

- STOMP command.
- Destination.
- Content type.
- Native STOMP headers.
- Session ID và Principal gắn với kết nối.
- Loại message ở tầng Spring Messaging.

Các header nội bộ thường được truy cập qua SimpMessageHeaderAccessor hoặc StompHeaderAccessor. Ứng dụng nên dùng accessor/hằng số Spring thay vì tự đoán tên các header nội bộ.

Một frame SEND không phải HTTP POST. Nó đi qua WebSocket/STOMP message pipeline, không đi qua Spring MVC DispatcherServlet như một HTTP request thông thường.

## 4. Bước 2: Message đi vào clientInboundChannel

Sau khi decode, Spring gửi message vào clientInboundChannel để các thành phần xử lý inbound cùng nhận được.

Channel này thường được triển khai bằng ExecutorSubscribableChannel. Vì vậy, việc xử lý có thể được thực hiện qua executor/thread pool theo cấu hình của ứng dụng.

Các thành phần có thể tham gia luồng inbound gồm:

- ChannelInterceptor để quan sát, bổ sung metadata hoặc từ chối message.
- Spring Security messaging để kiểm tra quyền SEND/SUBSCRIBE.
- SimpAnnotationMethodMessageHandler để tìm method @MessageMapping hoặc @SubscribeMapping.
- Message broker handler để xử lý destination thuộc broker prefix.

Ví dụ interceptor đơn giản:

~~~java
@Component
public class InboundAuditInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        StompHeaderAccessor accessor =
                StompHeaderAccessor.wrap(message);

        if (StompCommand.SEND.equals(accessor.getCommand())) {
            String destination = accessor.getDestination();
            logSend(destination, accessor.getSessionId());
        }

        return message;
    }
}
~~~

Đoạn code minh họa cần được đăng ký vào clientInboundChannel qua configureClientInboundChannel. Nếu preSend trả về null, message bị chặn và không tiếp tục qua channel.

Interceptor phù hợp cho kiểm tra chung như correlation metadata, audit hoặc policy kỹ thuật. Xử lý nghiệp vụ như tạo đơn hàng nên nằm trong controller/service để dễ kiểm thử và quản lý transaction.

## 5. Bước 3: Phân loại destination và bỏ application prefix

SimpAnnotationMethodMessageHandler xử lý các message có destination phù hợp với application destination prefixes.

Ví dụ:

~~~java
registry.setApplicationDestinationPrefixes("/app");
~~~

Với destination đầu vào:

~~~text
/app/orders.create
~~~

Handler kiểm tra prefix /app. Khi khớp, phần prefix được loại khỏi destination dùng để tìm method mapping:

~~~text
Destination từ client:       /app/orders.create
Application prefix:          /app
Destination dùng để lookup:  /orders.create
~~~

Do đó, method nên khai báo:

~~~java
@MessageMapping("/orders.create")
public OrderCreated create(CreateOrderCommand command) {
    return orderService.create(command);
}
~~~

Không thêm /app vào annotation. Nếu khai báo @MessageMapping("/app/orders.create"), mapping thường không khớp vì handler đã loại application prefix trước khi lookup.

Nếu không cấu hình application prefix, theo mặc định các destination có thể đủ điều kiện được xét bởi annotated handler. Trong ứng dụng có broker, nên tách rõ prefix ứng dụng và prefix broker để định tuyến dễ dự đoán.

## 6. Bước 4: Tìm method mapping

Các method @MessageMapping được phát hiện khi Spring khởi tạo message-handling infrastructure. SimpAnnotationMethodMessageHandler đăng ký các mapping từ class @Controller và các method được annotation.

Có thể đặt mapping chung ở cấp class:

~~~java
@Controller
@MessageMapping("/orders")
public class OrderController {

    @MessageMapping("/create")
    public OrderCreated create(CreateOrderCommand command) {
        return orderService.create(command);
    }

    @MessageMapping("/{orderId}/cancel")
    public OrderCancelled cancel(
            @DestinationVariable String orderId) {

        return orderService.cancel(orderId);
    }
}
~~~

Mapping kết hợp:

| Destination client gửi | Destination sau khi bỏ /app | Method được chọn |
|---|---|---|
| /app/orders/create | /orders/create | create |
| /app/orders/ORD-42/cancel | /orders/ORD-42/cancel | cancel |

Mặc định, Spring dùng Ant-style path matching. Mapping có thể dùng wildcard và template variable. Giá trị template được bind vào tham số có @DestinationVariable.

Ví dụ /orders/{orderId}/cancel lấy ORD-42 làm orderId. Spring chuyển đổi giá trị chuỗi sang kiểu tham số nếu ConversionService có converter phù hợp.

### 6.1. Mapping không khớp

Nếu không có method phù hợp, controller method không được gọi. Các nguyên nhân thường gặp:

- Client gửi sai destination.
- Application prefix cấu hình không khớp.
- Annotation đã chứa lại application prefix.
- Class thiếu @Controller.
- Method thiếu @MessageMapping.
- Class-level mapping và method-level mapping ghép thành đường dẫn khác dự kiến.
- PathMatcher hoặc separator được tùy chỉnh không đồng nhất.

Nếu destination thuộc broker prefix, message có thể được broker xử lý trực tiếp. Ví dụ SEND tới /topic/orders thường đi đến broker handler nếu /topic là broker prefix; nó không tự động gọi @MessageMapping("/orders").

Không cấu hình cùng một prefix cho broker và annotated controller trừ khi thật sự muốn cả hai handler cùng xử lý message. Khi có nhiều handler trên cùng channel, thứ tự xử lý không phải hợp đồng định tuyến an toàn.

## 7. Bước 5: Phân giải tham số method

Sau khi chọn được mapping, Spring dùng các HandlerMethodArgumentResolver để tạo tham số cho method.

Các kiểu tham số thường dùng:

| Tham số | Dữ liệu nhận được |
|---|---|
| DTO hoặc @Payload DTO | Payload sau khi chuyển đổi |
| @Header("key") | Một header cụ thể |
| @Headers Map | Các header đã ánh xạ |
| Message<?> | Spring Message gồm payload và headers |
| MessageHeaders | Header của message |
| SimpMessageHeaderAccessor | Header qua accessor có kiểu |
| @DestinationVariable | Biến lấy từ destination pattern |
| Principal | Người dùng đã xác thực của WebSocket session |

Một tham số không có annotation thường được xem là payload nếu không được resolver đặc biệt khác xử lý. Dùng @Payload khi muốn thể hiện rõ vai trò hoặc áp dụng validation.

Ví dụ:

~~~java
@MessageMapping("/orders/{orderId}/items")
public void addItem(
        @DestinationVariable String orderId,
        @Payload AddItemCommand command,
        @Header("requestId") String requestId,
        Principal principal) {

    orderService.addItem(
            principal.getName(),
            orderId,
            command,
            requestId
    );
}
~~~

Principal lấy danh tính được Spring gắn với WebSocket handshake. Không lấy user ID từ payload rồi xem đó là danh tính đã xác thực.

## 8. Bước 6: MessageConverter chuyển payload

Body của STOMP SEND thường được nhận ở dạng byte[]. Spring cần chuyển payload sang kiểu method yêu cầu.

Ví dụ client gửi JSON và method nhận CreateOrderCommand:

~~~java
public record CreateOrderCommand(
        String customerId,
        List<OrderItem> items) {
}

public record OrderItem(String sku, int quantity) {
}
~~~

~~~java
@MessageMapping("/orders.create")
public OrderCreated create(@Payload CreateOrderCommand command) {
    return orderService.create(command);
}
~~~

MessageConverter được chọn dựa trên kiểu payload, content-type và converter được cấu hình. Với JSON, ứng dụng thường dùng Jackson-based converter. Nếu client bỏ content-type hoặc gửi định dạng khác với contract, Spring có thể không chọn được converter mong muốn hoặc tạo ra kiểu payload khác.

Các trường hợp phổ biến:

- application/json: body JSON được chuyển thành DTO nếu có JSON converter phù hợp.
- text/plain: body thường được xử lý thành String.
- application/octet-stream: body nhị phân có thể được giữ ở dạng byte[].
- content-type không hỗ trợ: có thể phát sinh MessageConversionException.

Đừng giả định @Payload tự phân tích JSON nếu converter chưa được cấu hình. Hãy kiểm tra cấu hình message converters trong WebSocketMessageBrokerConfigurer và kiểu tham số thực tế.

### 8.1. Validation payload

Có thể kết hợp @Valid với @Payload:

~~~java
@MessageMapping("/orders.create")
public OrderCreated create(
        @Valid @Payload CreateOrderCommand command) {

    return orderService.create(command);
}
~~~

Khi Validator được cấu hình, payload không hợp lệ có thể làm quá trình phân giải tham số thất bại trước khi method nghiệp vụ được gọi.

Validation nên kiểm tra dữ liệu đầu vào như số lượng item, SKU, độ dài chuỗi và trường bắt buộc. Quyền sở hữu đơn hàng, quyền thao tác và các quy tắc phụ thuộc database vẫn cần được kiểm tra trong service.

## 9. Bước 7: Gọi controller method

Khi mapping và các tham số đã sẵn sàng, Spring gọi method qua hạ tầng InvocableHandlerMethod.

Ví dụ controller gọi service:

~~~java
@Controller
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("/orders.create")
    @SendTo("/topic/orders")
    public OrderCreated create(
            @Valid @Payload CreateOrderCommand command,
            Principal principal) {

        return orderService.create(principal.getName(), command);
    }
}
~~~

Controller nên điều phối request và gọi service. Quy tắc nghiệp vụ, truy cập repository và transaction nên nằm trong service để có thể dùng lại từ HTTP API, scheduled job hoặc các luồng messaging khác.

Nếu method cần transaction database, có thể đặt @Transactional ở service. Việc client gửi một STOMP SEND không tự tạo transaction phân tán giữa WebSocket, broker và database.

## 10. Bước 8: Xử lý giá trị trả về

Khi method trả về một object, Spring dùng return-value handler để biến kết quả thành Spring Message và gửi tới destination thích hợp.

Có ba cách phổ biến:

1. Dùng @SendTo để chỉ định destination broadcast.
2. Dùng @SendToUser để gửi kết quả cho user gửi message.
3. Dùng SimpMessagingTemplate để chủ động gửi tới destination do ứng dụng chọn.

### 10.1. @SendTo chỉ định destination

~~~java
@MessageMapping("/orders.create")
@SendTo("/topic/orders")
public OrderCreated create(CreateOrderCommand command) {
    return orderService.create(command);
}
~~~

Giá trị trả về được chuyển đổi thành payload outbound. Message được gửi tới brokerChannel và broker phát tới các subscriber của /topic/orders.

Có thể chỉ định nhiều destination trong @SendTo nếu cùng một kết quả cần phát tới nhiều nhóm nhận.

### 10.2. Destination mặc định khi không có @SendTo

Nếu method @MessageMapping trả về giá trị nhưng không khai báo @SendTo hoặc @SendToUser, Spring áp dụng destination mặc định dựa trên destination đầu vào.

Ví dụ:

~~~text
Destination SEND đầu vào: /app/greeting
Destination response mặc định: /topic/greeting
~~~

Spring thay application prefix bằng broker prefix mặc định /topic theo quy tắc của message flow. Nếu ứng dụng có contract response cụ thể, khai báo @SendTo tường minh giúp tránh phụ thuộc vào quy tắc mặc định.

### 10.3. @SendToUser gửi cho user gửi request

~~~java
@MessageMapping("/profile.refresh")
@SendToUser("/queue/profile")
public ProfileView refresh(Principal principal) {
    return profileService.load(principal.getName());
}
~~~

@SendToUser định tuyến kết quả về user gắn với message đầu vào. Destination là phần phía sau user prefix, ví dụ /queue/profile.

Nếu một user có nhiều session, thuộc tính broadcast điều khiển việc gửi tới các session tương ứng. Khi cần chỉ trả về session đã gửi request, có thể cấu hình broadcast=false theo semantics của annotation.

### 10.4. Method void và SimpMessagingTemplate

Nếu method trả về void, Spring không tạo response tự động từ một giá trị trả về. Ứng dụng có thể gửi message trực tiếp:

~~~java
@Controller
public class OrderController {

    private final SimpMessagingTemplate messagingTemplate;

    public OrderController(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    @MessageMapping("/orders.create")
    public void create(CreateOrderCommand command, Principal principal) {
        OrderCreated result =
                orderService.create(principal.getName(), command);

        messagingTemplate.convertAndSend("/topic/orders", result);
    }
}
~~~

Cách gửi trực tiếp hữu ích khi một method cần phát nhiều event, chọn destination theo kết quả nghiệp vụ hoặc gửi tới một nhóm user cụ thể. Không vừa trả về một giá trị đã được @SendTo xử lý vừa gửi cùng một kết quả qua template nếu không muốn subscriber nhận trùng.

### 10.5. Return type bất đồng bộ

Spring hỗ trợ các kiểu trả về bất đồng bộ như CompletableFuture, CompletionStage và ListenableFuture trong luồng xử lý annotated messaging.

Ví dụ:

~~~java
@MessageMapping("/reports.generate")
@SendToUser("/queue/reports")
public CompletableFuture<ReportResult> generate(ReportCommand command) {
    return reportService.generateAsync(command);
}
~~~

Kết quả được gửi khi future hoàn tất. Cần xử lý cả trường hợp future hoàn tất lỗi và bảo đảm các tác vụ nền không giữ session hoặc request-scoped object sau khi method kết thúc.

## 11. Bước 9: Message đi qua brokerChannel

Return-value handler hoặc SimpMessagingTemplate gửi outbound Spring Message tới brokerChannel.

Broker handler nhận message và xử lý theo cấu hình:

- Với simple broker, broker tìm các subscription đang hoạt động có destination khớp.
- Với broker relay, Spring chuyển tiếp message tới broker ngoài qua STOMP/TCP.
- Với user destination, UserDestinationMessageHandler phân giải destination logic theo user/session trước khi message tới broker destination phù hợp.

Nếu destination response không nằm trong broker prefix mà broker đang quản lý, message có thể không được chuyển tới subscriber như mong đợi.

Ví dụ simple broker:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
}
~~~

Client subscribe /topic/orders trước khi server phát message thì simple broker mới có subscriber đang chờ nhận. Với simple broker, subscription lưu trong memory và không phải kho lưu message cho client offline.

## 12. Bước 10: Broker phát MESSAGE tới client

Khi broker tìm được subscription khớp destination, message được chuyển tới clientOutboundChannel.

Spring mã hóa Spring Message thành STOMP MESSAGE frame, sau đó gửi qua WebSocket connection tương ứng.

Luồng response:

~~~text
Controller return value
    |
    v
MessageConverter
    |
    v
Spring outbound Message
    |
    v
brokerChannel
    |
    v
Broker matches subscriptions
    |
    v
clientOutboundChannel
    |
    v
STOMP MESSAGE frame
    |
    v
Subscriber WebSocket
~~~

Client nhận MESSAGE frame với destination và payload đã được broker chuyển tiếp. Với JSON, client parse body theo content-type hoặc contract mà ứng dụng thống nhất.

Một lần controller method hoàn tất không có nghĩa mọi client đã nhận và xử lý response. Muốn xác nhận nghiệp vụ ở phía client, cần application acknowledgement riêng.

## 13. Channel interceptor và Spring Security trong luồng SEND

clientInboundChannel là vị trí phù hợp để áp dụng kiểm tra chung cho message từ client.

ChannelInterceptor có thể:

- Kiểm tra destination hoặc loại STOMP command.
- Bổ sung correlation ID hoặc metadata nội bộ.
- Từ chối message không hợp lệ trước khi tới controller.
- Ghi nhận audit event.
- Gắn thông tin kỹ thuật phục vụ tracing.

Spring Security messaging cũng có thể kiểm soát quyền gửi tới /app/** và quyền subscribe /topic/**. Việc client biết destination không có nghĩa client được quyền sử dụng destination đó.

Ví dụ quy tắc bảo mật ở mức khái niệm:

| Hoạt động | Quy tắc nên áp dụng |
|---|---|
| SEND /app/orders.create | Chỉ user có quyền tạo đơn |
| SEND /app/orders/{id}/cancel | Phải kiểm tra quyền sở hữu và trạng thái đơn |
| SUBSCRIBE /topic/orders | Chỉ role được phép xem luồng đơn hàng |
| SUBSCRIBE /user/queue/notifications | Chỉ nhận destination user đã xác thực |

Không dùng ChannelInterceptor để thay thế kiểm tra quyền nghiệp vụ trong service. Các quy tắc như user có sở hữu orderId hay không phải được kiểm tra dựa trên dữ liệu tin cậy ở tầng nghiệp vụ.

## 14. Xử lý exception từ @MessageMapping

Lỗi có thể xảy ra ở nhiều giai đoạn:

| Giai đoạn | Ví dụ lỗi |
|---|---|
| Decode STOMP | Frame sai cấu trúc hoặc header không hợp lệ |
| Inbound channel/security | User không được phép SEND |
| Mapping | Destination không khớp method |
| Payload conversion | JSON sai cú pháp hoặc thiếu converter |
| Argument resolution | Header bắt buộc bị thiếu, validation thất bại |
| Controller/service | Đơn hàng không tồn tại hoặc trạng thái không hợp lệ |
| Return/send | Broker không sẵn sàng hoặc destination không hợp lệ |

Có thể dùng @MessageExceptionHandler để xử lý exception phát sinh từ các method messaging trong controller:

~~~java
@Controller
public class OrderController {

    @MessageMapping("/orders.create")
    @SendTo("/topic/orders")
    public OrderCreated create(CreateOrderCommand command) {
        return orderService.create(command);
    }

    @MessageExceptionHandler(OrderRejectedException.class)
    @SendToUser("/queue/errors")
    public ApplicationError handleOrderRejected(
            OrderRejectedException exception) {

        return new ApplicationError(
                "ORDER_REJECTED",
                exception.getMessage()
        );
    }
}
~~~

Có thể đặt handler dùng chung trong @ControllerAdvice nếu muốn áp dụng cho nhiều controller. Error payload cần tránh lộ stack trace, SQL, token hoặc thông tin nội bộ.

Lỗi xảy ra trước khi method được gọi, chẳng hạn STOMP frame sai hoặc authorization bị từ chối, có thể đi theo error handling của protocol/channel. @MessageExceptionHandler chủ yếu xử lý exception từ message-handling method; nó không phải một bộ xử lý mọi lỗi transport.

## 15. Thứ tự xử lý và hiệu năng

clientInboundChannel thường dùng executor để phân phối message tới handler. Vì vậy, nhiều message có thể được xử lý đồng thời.

Nếu hai SEND liên tiếp từ một client cùng thay đổi một entity, không nên mặc định mọi lần xử lý nghiệp vụ luôn hoàn tất theo đúng thứ tự gửi trong mọi cấu hình executor.

Khi cần giữ thứ tự nhận từ cùng session, Spring cung cấp tùy chọn preserveReceiveOrder trên STOMP endpoint registry ở các phiên bản hỗ trợ. Khi cần giữ thứ tự publish tới client, có thể cấu hình preservePublishOrder trên MessageBrokerRegistry.

Các tùy chọn này có overhead. Hãy bật theo yêu cầu nghiệp vụ và kiểm thử dưới tải thực tế.

Một số nguyên tắc vận hành:

- Giữ method @MessageMapping ngắn và gọi service chuyên trách.
- Tránh gọi API ngoài chậm đồng bộ trên inbound executor nếu có thể xử lý bất đồng bộ.
- Đặt giới hạn payload và send buffer.
- Theo dõi độ trễ inbound, thời gian xử lý method và độ trễ outbound.
- Kiểm tra kích thước thread pool của clientInboundChannel/clientOutboundChannel.
- Dùng correlation ID để liên kết log từ frame đầu vào tới event response.

## 16. Kiểm thử đường đi SEND tới @MessageMapping

Unit test controller chỉ kiểm tra logic method. Để kiểm tra toàn bộ đường đi, cần integration test qua WebSocket/STOMP endpoint.

Các bước kiểm thử:

1. Khởi động Spring context và STOMP endpoint.
2. Tạo WebSocketStompClient kết nối tới endpoint.
3. Thiết lập STOMP session thành công.
4. SUBSCRIBE tới destination response như /topic/orders.
5. Gửi SEND tới /app/orders.create với content-type application/json.
6. Chờ MESSAGE frame ở subscriber bằng latch hoặc future có timeout.
7. Kiểm tra payload response và destination.
8. Gửi JSON không hợp lệ và xác nhận lỗi theo error handling đã cấu hình.
9. Gửi tới destination sai prefix và xác nhận controller không được gọi.
10. Gửi message không đủ quyền và xác nhận authorization từ chối.
11. Kiểm tra @DestinationVariable và header được bind đúng.
12. Kiểm tra @MessageExceptionHandler trả error payload đúng.
13. Kiểm tra method void gửi qua SimpMessagingTemplate nếu ứng dụng sử dụng cách này.
14. Kiểm tra broker relay khi dùng broker ngoài thay cho simple broker.

Ví dụ client test dạng khái niệm:

~~~java
WebSocketStompClient client =
        new WebSocketStompClient(new StandardWebSocketClient());

StompSession session = client.connectAsync(
        "ws://localhost:8080/ws",
        new StompSessionHandlerAdapter() {}
).get(5, TimeUnit.SECONDS);

BlockingQueue<OrderCreated> replies = new LinkedBlockingQueue<>();

session.subscribe(
        "/topic/orders",
        new StompFrameHandler() {
            @Override
            public Type getPayloadType(StompHeaders headers) {
                return OrderCreated.class;
            }

            @Override
            public void handleFrame(
                    StompHeaders headers,
                    Object payload) {

                replies.offer((OrderCreated) payload);
            }
        }
);

session.send(
        "/app/orders.create",
        new CreateOrderCommand("CUS-9", List.of(
                new OrderItem("BOOK-1", 2)
        ))
);

OrderCreated result = replies.poll(5, TimeUnit.SECONDS);
assertNotNull(result);
~~~

Đây là ví dụ minh họa cách kiểm tra end-to-end; test thực tế cần cấu hình message converter, client lifecycle, broker và teardown phù hợp. Nếu dùng Jackson, client và server phải thống nhất converter và content-type.

Không dùng Thread.sleep để đoán khi nào broker đã lưu subscription hoặc response đã đến. Dùng receipt nếu broker hỗ trợ, latch, queue hoặc polling có timeout để test ổn định hơn.

## 17. Lỗi thường gặp và cách chẩn đoán

### 17.1. Controller không được gọi

Kiểm tra class có @Controller, method có @MessageMapping, client gửi command SEND, destination đúng và application prefix được cấu hình như dự kiến.

### 17.2. Destination có thêm /app trong annotation

Handler bỏ application prefix trước khi lookup. Mapping cần phần destination còn lại, ví dụ /orders.create.

### 17.3. Client gửi tới /topic thay vì /app

Destination broker prefix được chuyển tới broker handler. Nếu cần gọi controller, client phải SEND tới application prefix.

### 17.4. JSON không được chuyển thành DTO

Kiểm tra content-type, message converter, target Java type và cấu hình Jackson. Việc đổi kiểu tham số method không tự tạo JSON converter.

### 17.5. @DestinationVariable nhận null hoặc không khớp

Kiểm tra template variable trong @MessageMapping và segment thực tế của destination. Tên biến trong annotation và tham số phải tương ứng.

### 17.6. Response không đến subscriber

Kiểm tra client đã SUBSCRIBE đúng destination, broker prefix có được bật, @SendTo có đúng destination và broker có đang hoạt động không.

### 17.7. Response mặc định đi sai destination

Nếu không dùng @SendTo, Spring áp dụng quy tắc destination mặc định dựa trên destination đầu vào. Khai báo @SendTo rõ ràng khi contract cần một route cố định.

### 17.8. Subscriber nhận duplicate

Kiểm tra controller có vừa trả về object vừa gọi SimpMessagingTemplate gửi cùng kết quả hay không. Ngoài ra, kiểm tra retry ở tầng ứng dụng và broker.

### 17.9. Method xử lý message chậm

Đo thời gian ở inbound channel và service. Tách tác vụ dài sang worker/asynchronous processing nếu phù hợp; giới hạn executor và backlog để bảo vệ hệ thống.

### 17.10. Lỗi không đến được client

Kiểm tra @MessageExceptionHandler, @ControllerAdvice, broker availability và error handling của STOMP. Không giả định mọi exception đều tự biến thành một response nghiệp vụ có cấu trúc.

## 18. Checklist theo dõi từng chặng

Khi một SEND không hoạt động, lần theo các câu hỏi sau:

1. WebSocket handshake đã thành công chưa?
2. STOMP CONNECT đã nhận CONNECTED chưa?
3. Client đã gửi đúng STOMP command SEND chưa?
4. Frame có destination và content-type đúng không?
5. Message đã vào clientInboundChannel chưa?
6. Security/interceptor có chặn message không?
7. Destination có khớp application prefix không?
8. Prefix đã được bỏ đúng trước khi mapping chưa?
9. SimpAnnotationMethodMessageHandler có tìm được method không?
10. Payload converter có tạo đúng kiểu tham số không?
11. Header, Principal và DestinationVariable có được bind đúng không?
12. Validation có thành công không?
13. Controller/service có hoàn tất không?
14. Return-value handler có tạo outbound message không?
15. Destination response có nằm trong broker prefix không?
16. brokerChannel có chuyển message tới broker không?
17. Broker có subscriber khớp destination không?
18. clientOutboundChannel có chuyển message tới session không?
19. STOMP MESSAGE frame có được ghi lên WebSocket không?
20. Client có parse body và xử lý response thành công không?

Đặt log hoặc metric theo correlation ID tại các điểm quan trọng giúp tìm chính xác chặng bị lỗi. Không log toàn bộ payload nhạy cảm; chỉ ghi metadata cần thiết như destination, command, session ID, user đã xác thực và thời gian xử lý.

## 19. Tài liệu tham khảo

- [Spring Framework Reference — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework Reference — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html)
- [SimpAnnotationMethodMessageHandler — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/simp/annotation/support/SimpAnnotationMethodMessageHandler.html)
- [MessageMapping — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/handler/annotation/MessageMapping.html)
- [SendToMethodReturnValueHandler — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/simp/annotation/support/SendToMethodReturnValueHandler.html)
- [ChannelInterceptor — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html)
- [SimpMessagingTemplate — Spring Framework 6.1 Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/messaging/simp/SimpMessagingTemplate.html)
- [Spring Framework Reference — STOMP Authorization](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authorization.html)
- [Spring Framework Reference — STOMP Performance](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/configuration-performance.html)

Đường đi của SEND tới @MessageMapping gồm decode STOMP, inbound channel, destination prefix matching, method mapping, argument resolution, invocation và return-value handling. Khi cần chẩn đoán, hãy kiểm tra từng chặng theo đúng thứ tự; điều đó giúp phân biệt lỗi định tuyến với lỗi chuyển đổi payload, lỗi nghiệp vụ và lỗi phát response tới broker.