# Phân biệt xử lý tại controller với chuyển tiếp thẳng tới broker trong STOMP

## Mục tiêu

Trong Spring WebSocket + STOMP, một frame từ client có thể được định tuyến tới controller của ứng dụng hoặc tới message broker. Hai đường đi này đều bắt đầu từ kết nối WebSocket và đi qua hạ tầng messaging của Spring, nhưng khác nhau ở nơi xử lý nghiệp vụ, cách tạo thông điệp đầu ra và quyền mà client cần có.

“Chuyển tiếp thẳng tới broker” trong bài này có nghĩa là Spring định tuyến frame tới broker handler mà không gọi phương thức controller. Client vẫn kết nối tới endpoint WebSocket của ứng dụng Spring. Nếu dùng broker relay, Spring tiếp tục chuyển frame qua kết nối STOMP tới broker bên ngoài; client không tự động kết nối trực tiếp tới máy chủ broker.


**Phạm vi ví dụ Java:** Các đoạn mã trong bài là snippet minh họa cho các thành phần của một ứng dụng Spring đã cấu hình STOMP. Chúng lược bỏ một số import, DTO, service và cấu hình phụ trợ không liên quan trực tiếp đến luồng đang giải thích. Các ví dụ dùng `@Valid` và `@NotBlank` cần Jakarta Bean Validation API cùng một provider thực thi như Hibernate Validator; với Spring Boot có thể thêm `spring-boot-starter-validation`. Nếu không có provider, các annotation constraint sẽ không tự thực hiện validation.

## 1. Các thành phần và quy ước destination

- **WebSocket** cung cấp kết nối hai chiều lâu dài giữa client và server.
- **STOMP** định nghĩa các frame như CONNECT, SEND, SUBSCRIBE, MESSAGE và DISCONNECT cùng header destination.
- **Spring Messaging** biểu diễn frame thành Message và đưa thông điệp vào các channel nội bộ, tiêu biểu là **clientInboundChannel**, **brokerChannel** và **clientOutboundChannel**.
- **Controller** xử lý message được định tuyến tới các phương thức **@MessageMapping** hoặc subscription được định tuyến tới **@SubscribeMapping**.
- **Broker** quản lý subscription và phân phối message tới các subscriber có destination phù hợp.

Một cấu hình thường gặp tách destination dành cho ứng dụng khỏi destination dành cho broker:

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

Trong cấu hình trên:

- **/ws** là endpoint WebSocket để client thiết lập kết nối.
- **/app** là tiền tố dành cho message đi vào tầng xử lý của ứng dụng.
- **/topic** và **/queue** là các tiền tố được broker xử lý.
- Khi định tuyến tới controller, Spring bỏ tiền tố **/app** trước khi so khớp phần còn lại với **@MessageMapping**.

Tên **/app**, **/topic** và **/queue** là quy ước cấu hình phổ biến, không phải ba từ khóa bắt buộc của giao thức STOMP. Có thể chọn tiền tố khác, nhưng cần giữ chúng rõ ràng và không chồng lấn giữa controller với broker.

## 2. Luồng client gửi message để controller xử lý

Giả sử client gửi một message tới **/app/chat.send**, còn các client nhận tin nhắn bằng cách subscribe **/topic/chat**.

Luồng xử lý:

1. Client gửi frame STOMP SEND tới **/app/chat.send**.
2. Spring giải mã frame, tạo Message và đưa vào **clientInboundChannel**.
3. Tiền tố **/app** khiến message được định tuyến tới nhóm handler của ứng dụng. Spring bỏ tiền tố này, sau đó tìm phương thức khớp với **@MessageMapping("/chat.send")**.
4. Spring chuyển payload, header và thông tin người dùng thành các tham số phương thức phù hợp. Nếu được cấu hình, payload có thể được kiểm tra bằng Jakarta Validation.
5. Controller thực hiện nghiệp vụ: kiểm tra dữ liệu, xác định người gửi từ Principal, gọi service, lưu dữ liệu hoặc áp dụng quy tắc phân quyền.
6. Giá trị trả về được gửi qua **brokerChannel** tới broker. **@SendTo** cho phép chỉ định destination đầu ra.
7. Broker tìm các subscription khớp với destination và gửi frame MESSAGE tới các client tương ứng qua **clientOutboundChannel**.

Ví dụ Java 17+:

~~~java
public record ChatCommand(@NotBlank String text) {}

public record ChatEvent(String sender, String text) {}

@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatEvent send(
            @Valid @Payload ChatCommand command,
            Principal principal) {

        return new ChatEvent(principal.getName(), command.text());
    }
}
~~~

Client gửi tới **/app/chat.send**. Controller nhận phần destination còn lại là **/chat.send**. Sau khi phương thức trả về **ChatEvent**, Spring chuyển kết quả thành message và gửi tới **/topic/chat**; broker phân phối message cho những client đã subscribe destination đó.

**@SendTo** chỉ rõ nơi nhận kết quả. Nếu không chỉ định destination đầu ra, Spring mặc định suy ra destination bằng cách thay tiền tố **/app** của destination đầu vào bằng **/topic**. Ví dụ, kết quả của **/app/greeting** mặc định được gửi tới **/topic/greeting**.

Có thể dùng **@SendToUser("/queue/updates")** để gửi kết quả tới người dùng gắn với message hiện tại. Controller cũng có thể gọi **SimpMessagingTemplate** nếu cần gửi nhiều message, gửi theo điều kiện hoặc gửi tới destination được xác định trong lúc chạy.

Điểm cốt lõi: message đi qua controller trước khi được ứng dụng phát ra broker. Vì vậy, đây là lựa chọn phù hợp khi ứng dụng phải quyết định message có hợp lệ hay không, ai được gửi, gửi cho ai, nội dung cần biến đổi thế nào hoặc có cần lưu lại hay không.

## 3. Luồng client gửi thẳng tới broker

Với cùng ví dụ chat, client có thể gửi frame SEND trực tiếp tới destination broker như **/topic/chat**, nếu cấu hình và chính sách bảo mật cho phép.

~~~text
SUBSCRIBE
id:sub-1
destination:/topic/chat

[SUBSCRIBE frame kết thúc bằng ký tự NUL]

SEND
destination:/topic/chat
content-type:application/json

{"text":"Xin chào mọi người"}
[SEND frame kết thúc bằng ký tự NUL]
~~~

Khi client gửi tới **/topic/chat**:

1. Frame vẫn được Spring nhận qua WebSocket và đưa vào **clientInboundChannel**.
2. Destination khớp với tiền tố broker đã cấu hình.
3. Broker handler nhận message trực tiếp; phương thức **@MessageMapping** trong controller không được gọi.
4. Broker áp dụng quy tắc định tuyến của nó và phân phối message tới các subscription phù hợp.

Ở đường đi này, controller không tự động kiểm tra nội dung, ghi dữ liệu, gắn danh tính người gửi hay thực hiện nghiệp vụ. Broker chịu trách nhiệm xử lý theo destination, subscription và chính sách của broker. Nếu dùng simple broker, việc phân phối diễn ra trong broker đơn giản chạy trong ứng dụng Spring. Nếu dùng broker relay, Spring chuyển tiếp frame tới broker STOMP bên ngoài.

Cần phân biệt “đi thẳng tới broker” với “bỏ qua server Spring”: client vẫn gửi frame qua kết nối WebSocket của ứng dụng. Spring vẫn nhận frame và định tuyến nó tới broker handler. Với broker relay, Spring còn đóng vai trò chuyển tiếp giữa WebSocket client và broker bên ngoài.

## 4. Ba đường đi dễ nhầm lẫn

Có ba cách phổ biến để một message đến broker:

| Đường đi | Nguồn message | Controller có xử lý không? | Điểm vào broker |
|---|---|---|---|
| Client → controller → broker | Client SEND tới **/app/** | Có, qua **@MessageMapping** | Kết quả trả về, **@SendTo** hoặc template |
| Client → broker | Client SEND tới **/topic/** hoặc **/queue/** | Không gọi **@MessageMapping** | Broker handler nhận trực tiếp |
| Ứng dụng → broker | Service, HTTP controller, job hoặc listener phía server | Không cần **@MessageMapping** cho message phát ra | **SimpMessagingTemplate** gửi qua **brokerChannel** |

Ví dụ đường đi thứ ba:

~~~java
@Service
public class NotificationPublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public NotificationPublisher(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publish(SystemEvent event) {
        messagingTemplate.convertAndSend("/topic/system-events", event);
    }
}
~~~

Service có thể phát message sau khi hoàn tất nghiệp vụ, sau khi nhận sự kiện từ hệ thống khác hoặc trong một HTTP request. **convertAndSend** gửi message tới broker channel để broker phân phối; nó không gọi ngược một phương thức **@MessageMapping**.

Vì vậy, khi nói “controller xử lý rồi gửi tới broker”, cần xác định controller có thực sự xử lý message đầu vào hay chỉ là nơi gọi **SimpMessagingTemplate**. Cả hai đều có thể tạo message ở phía server, nhưng chỉ đường đầu tiên bắt đầu bằng một STOMP message được định tuyến tới **@MessageMapping**.

## 5. SUBSCRIBE và trường hợp đặc biệt của @SubscribeMapping

Không phải mọi frame đều được định tuyến giống SEND:

- Client SUBSCRIBE tới **/topic/chat** hoặc **/queue/orders** thường được broker xử lý để đăng ký subscription.
- Client SUBSCRIBE tới destination thuộc tiền tố ứng dụng như **/app/chat.initial** có thể được xử lý bởi phương thức **@SubscribeMapping("/chat.initial")**.

**@SubscribeMapping** phù hợp với kiểu request-reply một lần, chẳng hạn lấy dữ liệu ban đầu khi màn hình vừa mở:

~~~java
@Controller
public class ChatQueryController {

    @SubscribeMapping("/chat.initial")
    public List<ChatEvent> initialMessages() {
        return chatService.findRecentMessages();
    }
}
~~~

Client subscribe **/app/chat.initial**. Theo mặc định, giá trị trả về được gửi trực tiếp về client đã tạo subscription qua **clientOutboundChannel**, không đi qua broker channel và không được lưu thành subscription của broker. Client nhận snapshot ban đầu nhưng sẽ không tự động nhận các cập nhật tiếp theo từ destination này.

Nếu thêm **@SendTo** hoặc **@SendToUser**, kết quả của **@SubscribeMapping** được gửi qua broker thay vì trả trực tiếp. Không nên cấu hình controller và broker cùng xử lý một destination prefix nếu không có chủ đích rõ ràng: các handler có thể xử lý message song song và không có bảo đảm thứ tự handler nào chạy trước.

## 6. So sánh khi lựa chọn

| Tiêu chí | Xử lý tại controller | Chuyển tiếp thẳng tới broker |
|---|---|---|
| Nơi quyết định nghiệp vụ | Mã ứng dụng | Broker và cấu hình broker |
| Kiểm tra payload | Có thể dùng validation và service | Không có validation nghiệp vụ của controller |
| Danh tính người gửi | Có thể lấy từ **Principal** và gắn vào message | Phải dựa vào thông tin xác thực, ACL và metadata được broker tin cậy |
| Biến đổi nội dung | Dễ thực hiện trong controller/service | Thường không có bước biến đổi nghiệp vụ của ứng dụng |
| Lưu dữ liệu nghiệp vụ | Có thể phối hợp với repository/service | Không tự động lưu vào cơ sở dữ liệu ứng dụng |
| Phân phối pub-sub | Controller phát message, broker phân phối | Broker nhận và phân phối trực tiếp |
| Chi phí xử lý ứng dụng | Có thêm bước xử lý controller | Ít xử lý nghiệp vụ trong ứng dụng hơn |
| Phù hợp khi | Cần quy tắc nghiệp vụ, xác thực quyền, kiểm tra hoặc lưu dữ liệu | Luồng pub-sub đơn giản, client được phép publish và broker có thể tự áp dụng chính sách |

Không nên chọn đường broker trực tiếp chỉ vì ít bước hơn. Nếu client có thể tự gửi tới **/topic/**, client có thể phát nội dung mà các subscriber khác nhìn thấy. Nếu message đại diện cho một hành động nghiệp vụ, chẳng hạn đặt hàng, thanh toán, thay đổi trạng thái hoặc gửi thông báo hệ thống, hãy định tuyến qua controller/service để server quyết định nội dung và quyền phát.

## 7. Bảo mật: tách quyền SEND và SUBSCRIBE

Trong STOMP, SEND và SUBSCRIBE là hai loại hành động khác nhau. Một client có thể được phép nhận thông báo nhưng không được phép tự gửi thông báo vào destination đó.

Một chính sách thường dùng với Spring Security:

- Chỉ cho người dùng đã xác thực gửi message tới **/app/**, sau đó kiểm tra quyền nghiệp vụ trong controller/service.
- Cho phép SUBSCRIBE tới những destination mà vai trò của người dùng được phép đọc.
- Từ chối MESSAGE từ client tới **/topic/** và **/queue/** nếu ứng dụng không có nhu cầu cho client publish trực tiếp. Điều này ngăn client giả mạo message hệ thống hoặc gửi dữ liệu tùy ý tới các subscriber.
- Nếu cho phép client gửi thẳng tới broker, giới hạn destination và quyền publish bằng cấu hình phân quyền tương ứng; với broker bên ngoài, cấu hình ACL ở broker cũng cần phù hợp.
- Không tin trường **sender**, **userId**, **role** hoặc tên người dùng do client gửi trong payload. Hãy lấy danh tính từ **Principal** đã được xác thực và tự gắn vào message ở server.
- Bảo vệ SUBSCRIBE cẩn thận vì quyền subscribe quyết định client có thể đọc dữ liệu nào. Spring Security bảo vệ message đi vào; cần kiểm soát subscription để tránh rò rỉ dữ liệu tới người không có quyền.

Đối với message riêng cho từng người dùng, dùng user destination như **/user/queue/updates**, kết hợp **@SendToUser** hoặc **SimpMessagingTemplate.convertAndSendToUser(user, "/queue/updates", payload)**. Client subscribe **/user/queue/updates**; Spring ánh xạ destination logic này tới destination thực tế gắn với user/session. Không nên để client tùy ý subscribe vào queue nội bộ của người dùng khác.

## 8. Simple broker và broker relay

**enableSimpleBroker("/topic", "/queue")** bật simple broker tích hợp trong Spring. Broker này lưu subscription trong bộ nhớ và phát message tới các client đang subscribe destination phù hợp. Nó hữu ích cho ứng dụng nhỏ, môi trường phát triển hoặc luồng pub-sub cơ bản.

Simple broker chỉ hỗ trợ một phần STOMP, không cung cấp đầy đủ các tính năng như ACK và receipt, không phải broker phân tán và không phù hợp cho triển khai clustering. Không nên mặc định rằng tên destination **/queue** sẽ tạo ra hàng đợi bền vững hoặc bảo đảm message được lưu khi không có subscriber.

Khi cần broker đầy đủ tính năng, có thể thay simple broker bằng STOMP broker relay:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("localhost")
            .setRelayPort(61613);
}
~~~

Broker bên ngoài phải được cài đặt và bật hỗ trợ STOMP; thông tin đăng nhập và cấu hình kết nối cần được thiết lập phù hợp môi trường. Relay cho phép Spring chuyển message giữa WebSocket client và broker bên ngoài. Khả năng lưu bền, ACK, phân phối theo queue/topic, clustering và bảo đảm giao nhận phụ thuộc vào loại broker cùng cấu hình cụ thể; không tự suy ra các bảo đảm này chỉ từ việc dùng broker relay.

## 9. Lỗi thường gặp và cách kiểm tra

**Phương thức @MessageMapping không được gọi**

- Kiểm tra frame là SEND và destination có bắt đầu bằng application prefix đã cấu hình hay không.
- Kiểm tra phần destination còn lại có khớp với **@MessageMapping** ở class và method hay không.
- Kiểm tra client có đang gửi nhầm tới **/topic/** hoặc **/queue/** hay không. Các destination này thường được định tuyến tới broker.

**Controller chạy nhưng subscriber không nhận được kết quả**

- Kiểm tra destination trong **@SendTo** có đúng với destination mà client subscribe hay không.
- Kiểm tra broker đã bật prefix tương ứng và subscription đã được đăng ký hay chưa.
- Kiểm tra payload có được message converter chuyển đổi thành công hay không; xem log của inbound channel, controller và broker khi cần.

**Client có thể giả mạo thông báo**

- Kiểm tra chính sách có cho client MESSAGE tới **/topic/** hoặc **/queue/** hay không.
- Tách quyền MESSAGE khỏi SUBSCRIBE; chỉ cho publish trực tiếp khi đó là yêu cầu có chủ đích.
- Lấy danh tính từ Principal thay vì tin trường người gửi trong payload.

**Message bị xử lý hai lần hoặc kết quả không ổn định**

- Kiểm tra application prefix và broker prefix có chồng lấn hay không.
- Tránh ánh xạ cùng destination cho controller và broker nếu không có lý do đặc biệt. Spring có thể chuyển message tới các handler tương ứng song song, nên không thể dựa vào thứ tự xử lý để quyết định kết quả.

**Dùng /queue nhưng mong đợi message được lưu khi client offline**

- Kiểm tra loại broker và cấu hình queue thực tế. Simple broker giữ subscription trong bộ nhớ và không phải hàng đợi bền vững.
- Nếu cần lưu bền, ACK, retry hoặc phân phối giữa nhiều instance, cần chọn broker hỗ trợ và cấu hình rõ các cơ chế đó.

## 10. Quy tắc nhận diện nhanh

| Frame hoặc lời gọi | Đường đi thông thường |
|---|---|
| Client SEND **/app/orders** | Controller qua **@MessageMapping** |
| Client SEND **/topic/notifications** | Broker trực tiếp, nếu được cấu hình và cho phép |
| Client SEND **/queue/tasks** | Broker trực tiếp, nếu được cấu hình và cho phép |
| Client SUBSCRIBE **/topic/notifications** | Broker đăng ký subscription |
| Client SUBSCRIBE **/app/dashboard.initial** | **@SubscribeMapping** nếu có handler phù hợp |
| Server gọi **convertAndSend("/topic/notifications", event)** | Server gửi tới broker channel |
| Controller trả về giá trị với **@SendTo("/topic/notifications")** | Controller xử lý trước, sau đó gửi tới broker |

Có thể nhớ theo destination: **/app/** thường dành cho yêu cầu cần ứng dụng xử lý; **/topic/** và **/queue/** thường dành cho subscription và định tuyến của broker. Quy tắc thực tế vẫn phụ thuộc vào tiền tố được cấu hình và chính sách bảo mật của ứng dụng.

## Tài liệu tham khảo

- Spring Framework — Flow of Messages: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html
- Spring Framework — Annotated Controllers: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html
- Spring Framework — Sending Messages: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html
- Spring Framework — Simple Broker: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html
- Spring Framework — External Broker: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html
- Spring Framework — User Destinations: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html
- Spring Security — WebSocket Security: https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html
