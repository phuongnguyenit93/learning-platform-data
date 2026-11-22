# StompSubProtocolHandler và chuyển đổi STOMP frame sang Message

Trong Spring Framework, **StompSubProtocolHandler** là thành phần nối giao thức STOMP với hệ thống messaging nội bộ của Spring. Nó nhận WebSocket message từ client, giải mã STOMP frame thành đối tượng **Message<byte[]>**, bổ sung metadata của Spring rồi chuyển message vào channel nội bộ. Ở chiều ngược lại, nó nhận Spring Message hướng đến client, mã hóa thành STOMP frame và gửi qua WebSocket.

Cần hiểu đúng phạm vi của handler: nó xử lý giao thức và ranh giới transport. Nó không phải message broker, không tự thực thi logic nghiệp vụ và không tự chuyển JSON thành mọi Java object mà controller yêu cầu. Việc chuyển payload bytes thành DTO thường diễn ra ở bước sau bằng Spring MessageConverter.

## 1. StompSubProtocolHandler nằm ở đâu?

Khi bật STOMP messaging trong Spring bằng @EnableWebSocketMessageBroker, framework đăng ký các thành phần WebSocket và messaging cần thiết. Một trong số đó là **SubProtocolWebSocketHandler**, chịu trách nhiệm chọn protocol handler phù hợp với subprotocol mà client thương lượng trong HTTP WebSocket handshake.

Client có thể gửi header Sec-WebSocket-Protocol với các giá trị như v10.stomp, v11.stomp hoặc v12.stomp. SubProtocolWebSocketHandler chọn handler hỗ trợ protocol được chọn. StompSubProtocolHandler hỗ trợ STOMP 1.0, 1.1 và 1.2.

Các thành phần chính:

- **WebSocketSession:** kết nối WebSocket giữa một client và server.
- **SubProtocolWebSocketHandler:** chọn handler theo subprotocol và điều phối WebSocket message.
- **StompSubProtocolHandler:** chuyển đổi giữa WebSocket message và STOMP frame.
- **StompDecoder / BufferingStompDecoder:** phân tích STOMP frame từ byte buffer và ghép dữ liệu chưa đầy đủ.
- **StompHeaderAccessor:** đọc, chuẩn hóa và tạo STOMP/Spring message header.
- **clientInboundChannel:** nhận Spring Message từ client để chuyển tới controller hoặc broker.
- **clientOutboundChannel:** chuyển message từ broker/application về client.
- **StompEncoder:** mã hóa Spring Message thành STOMP frame.

~~~mermaid
flowchart TD
    C["STOMP client"] --> W["WebSocketSession"]
    W --> S["SubProtocolWebSocketHandler"]
    S --> H["StompSubProtocolHandler"]
    H --> D["BufferingStompDecoder / StompDecoder"]
    D --> M["Message<byte[]> + StompHeaderAccessor"]
    M --> I["clientInboundChannel"]
    I --> R["@MessageMapping / broker"]
    R --> O["clientOutboundChannel"]
    O --> H2["StompSubProtocolHandler"]
    H2 --> E["StompEncoder"]
    E --> W2["WebSocket text/binary message"]
    W2 --> C
~~~

Trong cấu hình ứng dụng thông thường, developer không cần tự tạo StompSubProtocolHandler. Spring tạo và kết nối handler với các channel, broker và WebSocket endpoint. Hiểu class này giúp đọc log, debug protocol và biết nên mở rộng ở tầng nào.

## 2. Hai chiều chuyển đổi

StompSubProtocolHandler thực hiện hai hướng công việc:

| Hướng | Input | Output | Mục đích |
|---|---|---|---|
| Inbound | WebSocket TextMessage hoặc BinaryMessage chứa STOMP bytes | Spring Message<byte[]> | Đưa frame từ client vào hệ thống messaging |
| Outbound | Spring Message<byte[]> hướng đến một session | WebSocket TextMessage hoặc BinaryMessage chứa STOMP frame | Gửi message từ application/broker về client |

Một frame STOMP có command, headers, body và ký tự NULL kết thúc frame. Spring Message có payload và headers riêng. Handler chuyển đổi phần command/header của STOMP sang metadata mà Spring hiểu, đồng thời giữ các native STOMP header để những tầng sau vẫn truy cập được.

Ví dụ client gửi:

~~~text
SEND
destination:/app/orders.create
content-type:application/json

{"orderId":"ORD-42","customer":"Ada"}^@
~~~

Sau khi giải mã, Spring có một Message với payload là mảng byte chứa JSON và metadata tương đương:

~~~text
simpMessageType = MESSAGE
simpDestination = /app/orders.create
simpSessionId = ws-session-42
simpUser = alice
nativeHeaders.content-type = application/json
nativeHeaders.destination = /app/orders.create
~~~

Các header simp là metadata chuẩn hóa của Spring. Native headers giữ các header gốc của STOMP như destination, subscription id, ack, receipt, content-type hoặc content-length.

## 3. Inbound: từ WebSocket message đến STOMP frame

Phương thức chính ở chiều client là handleMessageFromClient. Handler nhận WebSocketSession, WebSocketMessage và MessageChannel đích.

### 3.1. Nhận text và binary message

STOMP có thể được truyền trong WebSocket text hoặc binary message:

- Với TextMessage, handler lấy nội dung và chuyển thành byte buffer theo encoding của WebSocket text.
- Với BinaryMessage, handler sử dụng trực tiếp ByteBuffer payload.
- Các loại WebSocket message không phù hợp với STOMP được bỏ qua.

Việc nhận được WebSocket message chưa có nghĩa là đã nhận được một STOMP frame hoàn chỉnh. Một frame có thể bị chia thành nhiều phần khi client gửi các WebSocket message liên tiếp.

### 3.2. Decoder được giữ theo từng session

Handler duy trì một BufferingStompDecoder cho mỗi WebSocket session. Điều này rất quan trọng vì phần dữ liệu còn thiếu của client A không được ghép nhầm với dữ liệu của client B.

BufferingStompDecoder sử dụng StompDecoder để đọc frame. Khi dữ liệu chưa đủ, decoder giữ phần còn lại và kết hợp với dữ liệu nhận được ở lần tiếp theo. Khi có đủ dữ liệu, decoder có thể trả về một hoặc nhiều Spring Message<byte[]>.

Một WebSocket message có thể chứa nhiều STOMP frame hoàn chỉnh. Ngược lại, một STOMP frame cũng có thể trải qua nhiều WebSocket message. Vì vậy, không nên giả định một WebSocket message luôn tương ứng đúng một STOMP frame.

~~~mermaid
flowchart TD
    A["WebSocket message chunk 1"] --> B["BufferingStompDecoder"]
    C["WebSocket message chunk 2"] --> B
    D["WebSocket message chunk 3"] --> B
    B --> E{"Frame complete?"}
    E -->|No| F["Keep partial bytes"]
    F --> B
    E -->|Yes| G["StompDecoder"]
    G --> H["One or more Message<byte[]>"]
~~~

Nếu frame chứa header content-length, decoder có thể dùng độ dài đó để xác định lượng dữ liệu body còn phải chờ. Nếu buffer chỉ có một phần frame, decoder chưa phát message đó vào channel.

### 3.3. Giới hạn kích thước

StompSubProtocolHandler có giới hạn message buffer mặc định là **64 KB**. Vì STOMP frame có thể được ghép từ nhiều WebSocket message, giới hạn này áp dụng cho kích thước STOMP message sau khi buffering.

Có thể tăng giới hạn qua WebSocket transport configuration:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureWebSocketTransport(
            WebSocketTransportRegistration registration) {

        registration.setMessageSizeLimit(128 * 1024);
    }
}
~~~

Giá trị trên là 128 KiB. Hãy điều chỉnh theo kích thước payload thực tế và giới hạn của reverse proxy, servlet container hoặc WebSocket server. Tăng giới hạn không có nghĩa nên cho phép message không giới hạn; buffer lớn làm tăng mức tiêu thụ bộ nhớ khi có nhiều session đồng thời.

StompSubProtocolHandler còn có hằng số MINIMUM_WEBSOCKET_MESSAGE_SIZE bằng 16 KiB cộng 256 byte. Handler dùng mức tối thiểu này để hỗ trợ client chia STOMP message thành các WebSocket message khoảng 16 KiB, có thêm phần dự phòng cho framing như SockJS. Khi cấu hình transport server, cần bảo đảm giới hạn WebSocket text message đủ lớn cho yêu cầu này.

## 4. StompDecoder tạo Message<byte[]> như thế nào?

StompDecoder không trực tiếp tạo OrderCreated, ChatMessage hoặc DTO nghiệp vụ. Nó phân tích cấu trúc protocol và tạo danh sách Spring Message có payload kiểu byte[].

Các bước khái quát:

1. Đọc command, ví dụ SEND, SUBSCRIBE, CONNECT hoặc DISCONNECT.
2. Đọc các header theo cú pháp STOMP.
3. Xác định body theo content-length nếu có, hoặc theo ký tự NULL kết thúc frame.
4. Tạo StompHeaderAccessor chứa command và native headers.
5. Ánh xạ các header chung thành metadata của Spring.
6. Tạo Message<byte[]> với payload và MessageHeaders.

StompDecoder có thể giải mã nhiều frame trong một ByteBuffer. Nếu phần cuối buffer chưa đủ một frame, phần còn lại được giữ để lần decode sau tiếp tục. Lỗi cú pháp hoặc dữ liệu không hợp lệ có thể phát sinh StompConversionException.

### 4.1. Vì sao payload vẫn là byte[]?

STOMP cho phép payload text hoặc binary. Ở tầng protocol, giữ body ở dạng byte[] giúp handler không phải đoán kiểu dữ liệu nghiệp vụ và tránh chuyển đổi không cần thiết.

Ví dụ body JSON:

~~~json
{"orderId":"ORD-42","customer":"Ada"}
~~~

Sau protocol decoding, body vẫn là byte[]. Khi message được chuyển tới method controller nhận OrderCreated, Spring sử dụng MessageConverter phù hợp với content-type để chuyển byte[] thành Java object.

Đây là hai bước riêng:

| Bước | Thành phần | Kết quả |
|---|---|---|
| Protocol decoding | StompDecoder / StompSubProtocolHandler | STOMP frame thành Message<byte[]> |
| Payload conversion | Spring MessageConverter | byte[] hoặc String thành DTO nghiệp vụ |

Nếu controller không nhận được DTO như mong đợi, hãy kiểm tra content-type, converter được đăng ký và payload schema. Không nên mặc định lỗi nằm ở StompSubProtocolHandler.

## 5. StompHeaderAccessor và hai nhóm header

**StompHeaderAccessor** kế thừa SimpMessageHeaderAccessor và được dùng khi tạo Message từ STOMP frame hoặc khi mã hóa Message trở lại STOMP frame.

Có hai nhóm header quan trọng:

### 5.1. Spring processing headers

SimpMessageHeaderAccessor quản lý các metadata chung cho hệ thống messaging của Spring:

- **simpMessageType:** loại message nội bộ, ví dụ MESSAGE, SUBSCRIBE, CONNECT hoặc DISCONNECT.
- **simpDestination:** destination sau khi được chuẩn hóa.
- **simpSessionId:** ID của WebSocket/STOMP session.
- **simpSessionAttributes:** các attribute gắn với session.
- **simpUser:** Principal của client nếu đã xác thực.
- **simpHeartbeat:** thông tin heartbeat đã thương lượng.

Ví dụ, STOMP SEND được ánh xạ thành message type MESSAGE của Spring. STOMP SUBSCRIBE trở thành message type SUBSCRIBE để broker hoặc interceptor xử lý subscription.

### 5.2. Native STOMP headers

Các header gốc của STOMP được giữ trong native header map. Ví dụ:

- destination
- id
- ack
- receipt
- content-type
- content-length
- accept-version
- heart-beat
- subscription

Có thể đọc native header qua StompHeaderAccessor:

~~~java
StompHeaderAccessor accessor =
        MessageHeaderAccessor.getAccessor(
                message,
                StompHeaderAccessor.class
        );

if (accessor != null) {
    String destination = accessor.getDestination();
    String subscriptionId = accessor.getSubscriptionId();
    String contentType = accessor.getContentType();

    String receipt = accessor.getReceipt();
}
~~~

Đoạn code trên dùng trong ChannelInterceptor hoặc thành phần nhận Spring Message. Cần kiểm tra accessor có tồn tại trước khi đọc. Nếu message đã qua một số bước xử lý, có thể cần wrap message bằng StompHeaderAccessor.

Không nên tự sửa native header tùy tiện trong interceptor. Các header như destination, subscription id, receipt hoặc ack có ý nghĩa protocol và có thể ảnh hưởng routing hoặc acknowledgement.

## 6. Gắn session ID, Principal và session attributes

STOMP frame từ client không tự mang một session ID Spring đáng tin cậy. Handler lấy session ID từ WebSocketSession rồi gắn vào Message.

Handler cũng đưa session attributes và Principal của WebSocket session vào SimpMessageHeaderAccessor. Điều này cho phép các tầng sau xác định message đến từ kết nối nào và user nào.

Nếu ứng dụng xác thực người dùng qua HTTP handshake, Principal được gắn với WebSocket session sẽ được sử dụng cho STOMP session. Có thể bổ sung xác thực/ủy quyền ở clientInboundChannel bằng ChannelInterceptor hoặc Spring Security message authorization.

Khi nhận CONNECT hoặc STOMP đầu tiên, handler tạo SessionInfo cho session và giữ MessageChannel phù hợp. Nó cũng thiết lập callback để một interceptor có thể thay đổi Principal của STOMP session trong trường hợp ứng dụng có cơ chế xác thực riêng.

Không tin các header user ID do client gửi để xác định danh tính. Danh tính cần dựa trên Principal do server xác thực; quyền SEND/SUBSCRIBE phải được kiểm tra ở tầng security.

## 7. CONNECT, CONNECTED và heartbeat

STOMP CONNECT hoặc STOMP là frame đầu tiên thiết lập STOMP session trên một WebSocket session đã được tạo.

Handler nhận frame CONNECT/STOMP, tạo thông tin session, gắn user và session attributes rồi gửi Message vào clientInboundChannel. Broker xử lý CONNECT và trả CONNECTED nếu chấp nhận.

Hai application event giúp phân biệt hai mốc:

- **SessionConnectEvent:** phát khi server nhận STOMP CONNECT; đây là thời điểm client bắt đầu yêu cầu tạo STOMP session.
- **SessionConnectedEvent:** phát sau đó khi broker gửi STOMP CONNECTED; lúc này STOMP session được xem là đã thiết lập hoàn chỉnh.

Heartbeat được khai báo trong header heart-beat của CONNECT và CONNECTED. Handler chuyển thông tin heartbeat vào metadata Spring và xử lý heartbeat frame ở tầng protocol. Heartbeat không phải message nghiệp vụ gửi đến @MessageMapping.

Ví dụ listener nhận event:

~~~java
@Component
public class StompSessionEvents {

    @EventListener
    public void onConnect(SessionConnectEvent event) {
        Message<?> message = event.getMessage();

        StompHeaderAccessor accessor =
                StompHeaderAccessor.wrap(message);

        String sessionId = accessor.getSessionId();
        Principal user = accessor.getUser();

        // Ghi nhận yêu cầu kết nối.
    }

    @EventListener
    public void onConnected(SessionConnectedEvent event) {
        // Broker đã phản hồi CONNECTED.
    }
}
~~~

Ví dụ minh họa việc đọc event. Trong code thực tế, cần import các class tương ứng và xử lý trường hợp Principal có thể null.

Các event khác gồm SessionSubscribeEvent, SessionUnsubscribeEvent và SessionDisconnectEvent. SessionDisconnectEvent có thể được phát nhiều hơn một lần cho cùng session trong một số tình huống; listener xử lý event nên idempotent để tránh giải phóng resource hoặc ghi nhận disconnect trùng.

## 8. Inbound channel và preserveReceiveOrder

Sau khi decode và gắn metadata, handler gửi từng Message vào channel được chọn cho session. Với STOMP messaging thông thường, channel này là clientInboundChannel.

Tại đây, message được chuyển tiếp theo destination:

- Destination thuộc application prefix, ví dụ /app/orders.create, được chuyển tới method @MessageMapping.
- Destination thuộc broker prefix, ví dụ /topic/prices, được chuyển tới message broker.
- SUBSCRIBE và UNSUBSCRIBE được xử lý để quản lý subscription.
- CONNECT và DISCONNECT được xử lý theo lifecycle protocol.

Một điểm quan trọng là clientInboundChannel thường dựa trên ThreadPoolExecutor. Vì vậy, nhiều message từ cùng session có thể được xử lý bởi các thread khác nhau và thứ tự hoàn tất xử lý có thể khác thứ tự nhận.

Từ Spring Framework 6.1, StompSubProtocolHandler hỗ trợ preserveReceiveOrder. Có thể bật ở registry:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class OrderedStompConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.setPreserveReceiveOrder(true);
    }
}
~~~

Khi bật, message trong cùng client session được gửi vào clientInboundChannel từng message một để giữ thứ tự nhận. Tùy chọn này có chi phí điều phối và có thể giảm mức song song; chỉ bật khi nghiệp vụ cần thứ tự.

Cần phân biệt preserveReceiveOrder với preservePublishOrder. Một tùy chọn kiểm soát thứ tự message đi từ client vào ứng dụng; tùy chọn còn lại kiểm soát thứ tự message gửi từ server ra client.

## 9. Outbound: từ Spring Message trở lại STOMP frame

Ở chiều ngược lại, broker hoặc application gửi message qua clientOutboundChannel. SubProtocolWebSocketHandler định tuyến message tới session phù hợp, sau đó gọi StompSubProtocolHandler.handleMessageToClient.

Quy trình khái quát:

1. Xác định session ID từ Spring message header.
2. Kiểm tra payload có phải byte[] theo contract của STOMP encoder.
3. Lấy StompHeaderAccessor hoặc wrap message bằng accessor.
4. Xác định STOMP command cần gửi, ví dụ MESSAGE, CONNECTED, RECEIPT, ERROR hoặc heartbeat.
5. Xử lý header đặc biệt theo command và session.
6. Gọi StompEncoder để tạo byte array của STOMP frame.
7. Gửi qua WebSocketSession.

Thông thường frame được gửi dưới dạng TextMessage. Nếu payload có content-type application/octet-stream và không dùng SockJS session, handler có thể gửi BinaryMessage. Điều này cho phép STOMP mang payload nhị phân mà không phải ép thành text.

StompEncoder chịu trách nhiệm mã hóa command, native headers, content-length khi cần và body thành wire format. Handler quyết định session và kiểu WebSocket message phù hợp.

## 10. Xử lý CONNECTED, DISCONNECT_ACK, HEARTBEAT và MESSAGE

Không phải mọi Spring Message outbound đều đã có sẵn một STOMP command cụ thể. Một số message nội bộ cần được chuyển thành command STOMP tương ứng:

- **CONNECT_ACK:** phản hồi nội bộ từ simple broker được chuyển thành STOMP CONNECTED; handler xác định phiên bản STOMP được chấp nhận và heartbeat.
- **DISCONNECT_ACK:** nếu client đã yêu cầu receipt, handler có thể tạo RECEIPT; nếu không, có thể tạo ERROR thông báo session đã đóng theo luồng xử lý.
- **HEARTBEAT:** được chuyển thành heartbeat frame.
- **MESSAGE:** được gửi tới subscriber; handler kiểm tra subscription header và destination.
- **ERROR:** có thể đi qua error handler tùy cấu hình.

Khi broker trả CONNECTED, handler cập nhật thông tin session và phát SessionConnectedEvent. Nếu có Principal, handler có thể đưa tên user vào header user-name trên CONNECTED frame.

Đối với message MESSAGE, subscription ID là metadata quan trọng để client biết message thuộc subscription nào. Nếu thiếu subscription header, handler ghi cảnh báo vì frame có thể không tuân theo cấu trúc mà client STOMP mong đợi.

## 11. Lỗi protocol và StompSubProtocolErrorHandler

Lỗi có thể xảy ra ở nhiều tầng:

- STOMP frame sai cú pháp hoặc thiếu phần bắt buộc.
- Header hoặc content-length không hợp lệ.
- Buffer vượt message size limit.
- Không có STOMP session hợp lệ cho frame tiếp theo.
- Channel từ chối message do authorization hoặc interceptor.
- Lỗi trong broker hoặc message handling.

Nếu không cấu hình StompSubProtocolErrorHandler, handler mặc định có thể gửi STOMP ERROR frame rồi đóng WebSocket session với CloseStatus.PROTOCOL_ERROR.

StompSubProtocolHandler cung cấp phương thức setErrorHandler(StompSubProtocolErrorHandler) cho tầng protocol. Handler tùy chỉnh có thể tạo một STOMP ERROR message đã loại bỏ thông tin nhạy cảm hoặc trả về null để ngăn gửi frame lỗi.

Cần phân biệt extension point này với configureClientInboundChannel. ChannelInterceptor dùng để kiểm tra, bổ sung metadata hoặc từ chối Spring Message khi message đi vào channel; StompSubProtocolErrorHandler quyết định cách lỗi xử lý protocol/message được biểu diễn thành STOMP ERROR frame. Với exception nghiệp vụ trong @MessageMapping, thường nên dùng @MessageExceptionHandler hoặc cơ chế xử lý lỗi messaging của ứng dụng.

Trong cấu hình @EnableWebSocketMessageBroker thông thường, Spring quản lý StompSubProtocolHandler nội bộ. Nếu cần thay thế hoặc tùy biến handler ở mức thấp, hãy dùng cơ chế cấu hình infrastructure được hỗ trợ trong đúng phiên bản Spring đang triển khai.

Không nên đưa stack trace, SQL, thông tin broker hoặc secret vào ERROR frame gửi cho client. Hãy log chi tiết ở server với correlation/session ID, còn client nhận thông báo ngắn gọn và không chứa dữ liệu nhạy cảm.

Cũng cần phân biệt lỗi protocol với lỗi nghiệp vụ. Lỗi xử lý trong method @MessageMapping có thể được xử lý qua @MessageExceptionHandler hoặc cơ chế error channel/broker. Không phải mọi exception trong nghiệp vụ đều đồng nghĩa STOMP frame bị lỗi cú pháp.

## 12. MessageHeaderInitializer và cấu hình quan sát

StompSubProtocolHandler cho phép đặt MessageHeaderInitializer. Initializer được áp dụng cho header của message tạo từ STOMP frame và các message gửi vào client inbound channel theo cấu hình.

Có thể dùng để chuẩn hóa metadata chung, ví dụ header tracing hoặc các giá trị mặc định nội bộ. Không nên dùng initializer để thay thế authentication hoặc authorization.

Handler còn cung cấp Stats để quan sát số frame CONNECT, CONNECTED và DISCONNECT đã xử lý. Có thể đọc thống kê từ getStats() hoặc getStatsInfo() khi cần chẩn đoán vòng đời session.

Các chỉ số vận hành nên kết hợp với metric của broker và channel:

- Số WebSocket session đang hoạt động.
- Số STOMP CONNECT và CONNECTED thành công.
- Số DISCONNECT và session bị đóng do protocol error.
- Số lỗi decode và số lần vượt message size limit.
- Độ trễ xử lý clientInboundChannel/clientOutboundChannel.
- Số message bị từ chối do authorization hoặc broker.
- Buffer outbound và thời gian gửi khi client đọc chậm.
- Số subscription và lượng message phát ra mỗi session.

## 13. Cấu hình transport, kích thước và thứ tự

Một cấu hình WebSocket STOMP có thể điều chỉnh message size, thời gian gửi và buffer outbound:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class StompTransportConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureWebSocketTransport(
            WebSocketTransportRegistration registration) {

        registration
                .setMessageSizeLimit(128 * 1024)
                .setSendTimeLimit(15 * 1000)
                .setSendBufferSizeLimit(512 * 1024);
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
        registry.setPreserveReceiveOrder(true);
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setPreservePublishOrder(true);
    }
}
~~~

Ví dụ đặt inbound message limit 128 KiB, send time limit 15 giây và outbound buffer limit 512 KiB. Các giới hạn này cần được chọn theo tải và khả năng của server.

Nếu bật preserveReceiveOrder và preservePublishOrder, thứ tự message được giữ trong từng client session ở hai chiều tương ứng. Điều đó có thể làm giảm throughput khi nhiều message liên tiếp phải chờ nhau. Không nên bật chỉ vì muốn “an toàn”; hãy xác định nghiệp vụ thực sự phụ thuộc thứ tự.

## 14. Các lỗi thường gặp

### 14.1. Nghĩ rằng StompSubProtocolHandler chuyển JSON thành DTO

Handler chuyển frame thành Message<byte[]> và chuẩn hóa header. DTO conversion diễn ra sau đó qua MessageConverter.

Cách xử lý: kiểm tra content-type, converter và kiểu tham số method @MessageMapping.

### 14.2. Giả định một WebSocket message bằng một STOMP frame

Client có thể gửi nhiều frame trong một WebSocket message hoặc chia một frame lớn thành nhiều WebSocket message.

Cách xử lý: để BufferingStompDecoder quản lý phần dữ liệu còn thiếu; không tự parse mỗi WebSocket message như một frame hoàn chỉnh.

### 14.3. Bỏ qua native headers

Các header STOMP như subscription, ack, receipt và content-length có thể cần cho xử lý protocol.

Cách xử lý: dùng StompHeaderAccessor để truy cập native headers; tránh xóa hoặc đổi header nếu không hiểu tác động.

### 14.4. Nhầm message type của Spring với STOMP command

STOMP SEND thường được biểu diễn thành SimpMessageType.MESSAGE. Đây là cách Spring chuẩn hóa command để dùng chung message infrastructure.

Cách xử lý: đọc STOMP command qua StompHeaderAccessor khi cần protocol detail; đọc simpMessageType khi cần phân loại message nội bộ.

### 14.5. Cho phép payload không giới hạn

Frame lớn hoặc nhiều session cùng gửi frame lớn có thể làm tăng bộ nhớ do buffering.

Cách xử lý: cấu hình message size limit phù hợp, kiểm tra giới hạn WebSocket server và reverse proxy, đồng thời giới hạn tốc độ gửi.

### 14.6. Không kiểm tra thứ tự inbound

clientInboundChannel dùng thread pool nên message cùng session có thể hoàn tất không theo thứ tự nhận.

Cách xử lý: bật preserveReceiveOrder khi nghiệp vụ cần; nếu không, thiết kế handler idempotent và không phụ thuộc thứ tự ngầm định.

### 14.7. Gộp lỗi protocol và lỗi nghiệp vụ

Frame sai cấu trúc là lỗi protocol; controller ném exception khi xử lý đơn hàng là lỗi nghiệp vụ.

Cách xử lý: xử lý protocol qua StompSubProtocolErrorHandler và xử lý lỗi controller qua exception handler hoặc cơ chế messaging phù hợp.

### 14.8. Xử lý SessionDisconnectEvent không idempotent

Một session có thể phát nhiều disconnect event trong một số trường hợp.

Cách xử lý: khi xóa session, subscription hoặc presence, hãy thiết kế thao tác có thể gọi lặp mà không tạo tác dụng phụ.

## 15. Ví dụ Java 17: mô phỏng STOMP frame thành Spring Message

Ví dụ sau mô phỏng phần chuyển đổi cốt lõi từ một STOMP SEND frame thành cấu trúc Message nội bộ. Nó dùng JDK thuần để minh họa command, native headers, Spring headers và payload byte[].

Đây không phải implementation của StompSubProtocolHandler, StompDecoder hay Spring Message. Handler thật còn xử lý STOMP version, escaping header, content-length, buffering, heartbeat, session, Principal, event và channel dispatch.

Tạo file **StompFrameToMessageDemo.java**:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;

public class StompFrameToMessageDemo {

    record ParsedFrame(
            String command,
            Map<String, String> nativeHeaders,
            byte[] payload) {}

    record SpringMessage(
            Map<String, String> simpHeaders,
            Map<String, String> nativeHeaders,
            byte[] payload) {}

    static ParsedFrame decodeOneFrame(String wire) {
        String normalized = wire.replace("\r\n", "\n");
        int separator = normalized.indexOf("\n\n");

        if (separator < 0) {
            throw new IllegalArgumentException(
                    "Missing STOMP header/body separator");
        }

        String headerBlock = normalized.substring(0, separator);
        String body = normalized.substring(separator + 2);

        if (body.endsWith("\0")) {
            body = body.substring(0, body.length() - 1);
        }

        String[] lines = headerBlock.split("\n");
        String command = lines[0];
        Map<String, String> headers = new LinkedHashMap<>();

        for (int i = 1; i < lines.length; i++) {
            int colon = lines[i].indexOf(':');

            if (colon <= 0) {
                throw new IllegalArgumentException(
                        "Invalid STOMP header: " + lines[i]);
            }

            String name = lines[i].substring(0, colon);
            String value = lines[i].substring(colon + 1);
            headers.putIfAbsent(name, value);
        }

        return new ParsedFrame(
                command,
                Map.copyOf(headers),
                body.getBytes(StandardCharsets.UTF_8)
        );
    }

    static SpringMessage toSpringMessage(
            ParsedFrame frame,
            String sessionId,
            String principalName) {

        if (!"SEND".equals(frame.command())) {
            throw new IllegalArgumentException(
                    "Demo expects a SEND frame");
        }

        Map<String, String> simpHeaders = new LinkedHashMap<>();
        simpHeaders.put("simpMessageType", "MESSAGE");
        simpHeaders.put(
                "simpDestination",
                frame.nativeHeaders().get("destination")
        );
        simpHeaders.put("simpSessionId", sessionId);
        simpHeaders.put("simpUser", principalName);

        return new SpringMessage(
                Map.copyOf(simpHeaders),
                frame.nativeHeaders(),
                frame.payload()
        );
    }

    public static void main(String[] args) {
        String frame =
                "SEND\n"
                + "destination:/app/orders.create\n"
                + "content-type:application/json\n"
                + "\n"
                + "{\"orderId\":\"ORD-42\",\"customer\":\"Ada\"}\0";

        ParsedFrame parsed = decodeOneFrame(frame);

        SpringMessage message = toSpringMessage(
                parsed,
                "ws-session-42",
                "alice"
        );

        System.out.println("STOMP command: " + parsed.command());
        System.out.println(
                "Spring message type: "
                        + message.simpHeaders().get("simpMessageType"));
        System.out.println(
                "simpDestination: "
                        + message.simpHeaders().get("simpDestination"));
        System.out.println(
                "simpSessionId: "
                        + message.simpHeaders().get("simpSessionId"));
        System.out.println(
                "simpUser: " + message.simpHeaders().get("simpUser"));
        System.out.println(
                "native content-type: "
                        + message.nativeHeaders().get("content-type"));
        System.out.println("payload type: byte[]");
        System.out.println(
                "payload: "
                        + new String(
                                message.payload(),
                                StandardCharsets.UTF_8
                        ));
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac StompFrameToMessageDemo.java
java StompFrameToMessageDemo
~~~

Kết quả:

~~~text
STOMP command: SEND
Spring message type: MESSAGE
simpDestination: /app/orders.create
simpSessionId: ws-session-42
simpUser: alice
native content-type: application/json
payload type: byte[]
payload: {"orderId":"ORD-42","customer":"Ada"}
~~~

Ví dụ cho thấy một SEND frame được biểu diễn thành Spring message có destination, session, user, native header và payload byte[]. Session ID và user trong ví dụ được truyền vào từ WebSocket session context; chúng không được lấy từ body JSON của client.

Parser mẫu chỉ xử lý một frame text đơn giản. Parser production phải xử lý header escaping của STOMP 1.1/1.2, content-length, body binary, heartbeat, nhiều frame trong buffer và frame bị chia qua nhiều lần nhận. Trong ứng dụng Spring, hãy để StompDecoder và StompSubProtocolHandler thực hiện các nhiệm vụ protocol đó.

## 16. Quy trình debug khi frame không đến được controller

Khi client gửi SEND nhưng method @MessageMapping không chạy, hãy kiểm tra theo thứ tự:

1. WebSocket handshake có thành công và chọn đúng subprotocol v10.stomp, v11.stomp hoặc v12.stomp không?
2. Client có gửi STOMP CONNECT/STOMP và nhận CONNECTED không?
3. WebSocket message có phải text hoặc binary payload chứa frame STOMP hợp lệ không?
4. Frame có command và header bắt buộc không; body có kết thúc đúng hoặc có content-length hợp lệ không?
5. BufferingStompDecoder có giữ lại frame chưa hoàn chỉnh hoặc báo lỗi vượt message size limit không?
6. StompHeaderAccessor có nhận đúng command, destination và content-type không?
7. Message có được gửi vào clientInboundChannel không?
8. Destination prefix có khớp với cấu hình application prefix không?
9. ChannelInterceptor hoặc Spring Security có từ chối SEND không?
10. MessageConverter có chuyển payload thành kiểu tham số controller được không?

Nếu client nhận ERROR frame, kiểm tra log server và StompSubProtocolErrorHandler. Nếu message vào broker nhưng không đến subscriber, kiểm tra destination, subscription ID và broker semantics. Nếu controller đã chạy nhưng client không nhận phản hồi, kiểm tra clientOutboundChannel, session ID, StompEncoder và WebSocket send buffer.

Không log passcode, token hoặc toàn bộ payload nhạy cảm khi debug. Có thể log command, destination, session ID, message type, kích thước payload và correlation ID để theo dõi luồng.

## 17. Ghi nhớ

StompSubProtocolHandler là adapter giữa WebSocket và Spring messaging. Ở chiều inbound, nó dùng decoder có buffering theo session để chuyển STOMP frame thành Message<byte[]> với native STOMP headers và metadata chuẩn hóa của Spring. Message được gửi vào clientInboundChannel để controller, broker và interceptor xử lý.

Ở chiều outbound, handler nhận Spring Message hướng đến một session, chuẩn hóa STOMP command/header, dùng StompEncoder để tạo frame rồi gửi qua WebSocket text hoặc binary message. CONNECT/CONNECTED, heartbeat, event lifecycle, lỗi protocol, message size và thứ tự inbound đều thuộc các phần việc quan trọng của handler.

Khi debug, hãy xác định lỗi nằm ở WebSocket transport, STOMP decoding, header mapping, channel routing, MessageConverter, broker hay outbound encoding. Phân biệt rõ protocol conversion với payload conversion sẽ giúp tìm đúng tầng cần kiểm tra.

## Tài liệu tham khảo

- [Spring Framework 6.2.17: StompSubProtocolHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.17/javadoc-api/org/springframework/web/socket/messaging/StompSubProtocolHandler.html)
- [Spring Framework: StompDecoder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.17/javadoc-api/org/springframework/messaging/simp/stomp/StompDecoder.html)
- [Spring Framework: StompHeaderAccessor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.17/javadoc-api/org/springframework/messaging/simp/stomp/StompHeaderAccessor.html)
- [Spring Framework: StompEncoder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.17/javadoc-api/org/springframework/messaging/simp/stomp/StompEncoder.html)
- [Spring Framework: Application Context Events](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/application-context-events.html)
- [Spring Framework: Ordered Messages](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/ordered-messages.html)