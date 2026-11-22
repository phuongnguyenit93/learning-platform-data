# Lựa chọn simple broker hay broker relay theo yêu cầu hệ thống

> Phạm vi: Spring Framework STOMP over WebSocket, Java 17+. Bài viết giải thích hai lựa chọn message broker trong Spring, cách cấu hình, các năng lực khác nhau và tiêu chí quyết định theo quy mô, khả năng chịu tải, độ tin cậy và vận hành. Các đoạn mã là cấu hình trong ứng dụng Spring, không phải chương trình Java độc lập.

## 1. Vai trò của broker trong kiến trúc STOMP

Trong ứng dụng STOMP, WebSocket cung cấp kết nối hai chiều giữa client và server, còn STOMP định nghĩa các frame như CONNECT, SEND, SUBSCRIBE, MESSAGE, ACK và DISCONNECT. Spring nhận frame từ client, định tuyến message ứng dụng đến controller hoặc chuyển message đến broker để phân phối cho subscriber.

Một luồng thường gặp:

1. Client kết nối đến endpoint WebSocket, ví dụ /ws, rồi gửi STOMP CONNECT.
2. Client SEND đến /app/chat.send. Prefix /app được dành cho message ứng dụng.
3. Spring định tuyến đến phương thức @MessageMapping tương ứng.
4. Controller trả về payload hoặc ứng dụng chủ động gửi bằng SimpMessagingTemplate.
5. Message được chuyển đến brokerChannel.
6. Broker phân phối message đến các client đã SUBSCRIBE destination phù hợp, qua clientOutboundChannel.

Spring cung cấp hai cách xử lý phần broker:

- **Simple broker**: broker đơn giản được tích hợp trong tiến trình Spring application.
- **STOMP broker relay**: Spring chuyển tiếp STOMP frame đến một message broker bên ngoài thông qua TCP, ví dụ broker có hỗ trợ STOMP.

Cả hai đều làm việc với mô hình controller, destination và subscription của Spring. Khác biệt chính nằm ở năng lực broker, cách mở rộng, độ tin cậy và chi phí vận hành.

## 2. Simple broker là gì?

Simple broker là một bộ xử lý broker tối giản có sẵn trong Spring WebSocket. Nó theo dõi các subscription đang hoạt động trong bộ nhớ của ứng dụng và phân phối message đến các subscriber có destination khớp.

Cấu hình cơ bản:

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

Với cấu hình này:

- Client SEND đến /app/... để gọi controller có @MessageMapping.
- Client SUBSCRIBE đến /topic/... hoặc /queue/... để nhận message do simple broker phân phối.
- Controller có thể trả về giá trị với @SendTo, hoặc gửi chủ động bằng SimpMessagingTemplate.
- Simple broker lưu thông tin subscription trong bộ nhớ của process đang chạy.

### Năng lực và giới hạn

Simple broker phù hợp với các luồng publish/subscribe cơ bản. Nó có thể phân phối message đến nhiều subscriber, xử lý đăng ký và hủy đăng ký subscription, và hoạt động mà không cần cài đặt broker riêng.

Tuy nhiên, đây không phải một broker STOMP đầy đủ. Nó không hỗ trợ các tính năng giao thức nâng cao như ACK/NACK và receipt theo cách một broker STOMP đầy đủ có thể cung cấp. Nó không cung cấp hàng đợi bền vững, lưu message để phát lại sau khi client ngắt kết nối, hoặc cơ chế broker cluster. Trạng thái subscription và phân phối message nằm trong bộ nhớ của một instance Spring application.

Nếu một ứng dụng chạy hai instance sau load balancer, mỗi instance có simple broker và tập subscription riêng. Client kết nối vào instance A không tự động nhận message được gửi qua simple broker ở instance B. Sticky session không biến hai simple broker thành một broker dùng chung; nó chỉ ảnh hưởng việc client được định tuyến đến instance nào.

### Heartbeat với simple broker

Simple broker không gửi heartbeat STOMP theo mặc định. Có thể cấu hình heartbeat và TaskScheduler để kiểm tra kết nối:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    private final TaskScheduler heartbeatScheduler;

    public WebSocketConfig(TaskScheduler heartbeatScheduler) {
        this.heartbeatScheduler = heartbeatScheduler;
    }

    @Bean
    public TaskScheduler heartbeatScheduler() {
        ThreadPoolTaskScheduler scheduler = new ThreadPoolTaskScheduler();
        scheduler.setPoolSize(1);
        scheduler.setThreadNamePrefix("stomp-heartbeat-");
        return scheduler;
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue")
                .setHeartbeatValue(new long[] {10000, 10000})
                .setTaskScheduler(heartbeatScheduler);
    }
}
~~~

Đây là cấu hình minh họa cho heartbeat 10 giây theo mỗi chiều. Trong ứng dụng thực tế, cần kiểm tra phiên bản Spring đang dùng, cấu hình scheduler, timeout của proxy/load balancer và heartbeat phía client. Heartbeat giúp phát hiện kết nối không còn hoạt động; nó không biến simple broker thành broker có lưu trữ bền vững hay khả năng clustering.

## 3. STOMP broker relay là gì?

Broker relay là một thành phần của Spring nhận message từ các channel nội bộ rồi chuyển tiếp STOMP frame đến một broker bên ngoài qua TCP. Broker bên ngoài thực hiện việc quản lý destination, subscription và phân phối message.

Một số broker phổ biến có hỗ trợ STOMP thông qua connector hoặc plugin, chẳng hạn RabbitMQ với STOMP plugin và ActiveMQ với STOMP transport. Broker và phiên bản cụ thể quyết định các tính năng STOMP có sẵn cũng như cách cấu hình destination.

Cấu hình cơ bản:

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

        registry.enableStompBrokerRelay("/topic", "/queue")
                .setRelayHost("broker.internal")
                .setRelayPort(61613)
                .setClientLogin("web-client")
                .setClientPasscode("client-secret")
                .setSystemLogin("spring-system")
                .setSystemPasscode("system-secret");
    }
}
~~~

Các host, port, username và password ở trên chỉ là giá trị ví dụ. Hãy lấy chúng từ cấu hình môi trường hoặc secret manager, không hard-code thông tin xác thực thật trong mã nguồn. Port STOMP phụ thuộc cấu hình broker; 61613 thường gặp ở một số cấu hình RabbitMQ/ActiveMQ nhưng không phải cổng bắt buộc cho mọi broker.

### Hai loại kết nối TCP mà relay quản lý

Spring STOMP broker relay duy trì:

1. **System connection**: một kết nối TCP dùng cho message do chính ứng dụng Spring gửi đến broker, ví dụ message được gửi qua SimpMessagingTemplate.
2. **Client connections**: một kết nối TCP riêng đến broker cho mỗi WebSocket/STOMP client được relay phục vụ. Relay chuyển tiếp frame từ client qua kết nối tương ứng và đưa frame broker gửi về lại client qua Spring.

Do đó, broker relay giúp nhiều instance Spring chia sẻ cùng một hạ tầng broker bên ngoài. Tuy nhiên, số lượng client connection, giới hạn connection của broker, file descriptor, bộ nhớ và băng thông cần được tính toán theo số kết nối đồng thời. Relay không làm biến mất chi phí kết nối; nó chuyển phần quản lý phân phối message sang broker chuyên dụng.

Các thuộc tính xác thực có ý nghĩa khác nhau:

- clientLogin/clientPasscode là thông tin relay sử dụng khi kết nối broker thay mặt cho các client.
- systemLogin/systemPasscode là thông tin dùng cho system connection của ứng dụng.
- Broker vẫn cần cấu hình quyền truy cập, destination và chính sách phù hợp với các tài khoản đó.

## 4. So sánh trực tiếp

| Tiêu chí | Simple broker | STOMP broker relay |
|---|---|---|
| Thành phần | Tích hợp trong Spring application | Spring relay kết nối broker bên ngoài |
| Hạ tầng | Không cần cài broker riêng | Cần triển khai và vận hành broker hỗ trợ STOMP |
| Trạng thái subscription | Bộ nhớ của từng Spring instance | Do broker bên ngoài quản lý |
| Phạm vi phân phối | Trong instance chứa kết nối | Có thể phân phối giữa nhiều Spring instance dùng chung broker |
| STOMP nâng cao | Tập tính năng giới hạn; không có ACK/NACK và receipt đầy đủ | Có thể dùng tính năng broker hỗ trợ, ví dụ ACK, receipt, transaction |
| Lưu trữ message | Không cung cấp durable queue hoặc replay mặc định | Có thể dùng queue/durable subscription/persistence nếu broker và cấu hình hỗ trợ |
| Heartbeat | Cần cấu hình scheduler để bật | Relay có cơ chế heartbeat với broker; cấu hình theo nhu cầu và broker |
| Khả năng mở rộng | Hợp với ứng dụng nhỏ hoặc một instance | Phù hợp hơn khi cần nhiều instance và broker dùng chung |
| Vận hành | Đơn giản, ít thành phần | Cần giám sát broker, relay connection, quyền truy cập và dung lượng |
| Kiểm thử | Dễ dùng cho phát triển và kiểm thử tích hợp cơ bản | Cần broker thật hoặc môi trường kiểm thử tương đương production |

Không nên hiểu bảng này là mọi broker bên ngoài đều cung cấp mọi tính năng. Broker relay chỉ chuyển tiếp giao thức; ACK, receipt, transaction, queue bền vững, thời hạn lưu trữ, dead-letter và clustering phụ thuộc broker, plugin, phiên bản và cấu hình cụ thể.

## 5. Phân biệt destination prefix và semantics của broker

Một cấu hình thường có ba nhóm destination:

| Prefix | Mục đích |
|---|---|
| /app | Message inbound dành cho controller Spring qua @MessageMapping. |
| /topic | Thường dùng cho publish/subscribe hoặc broadcast. |
| /queue | Thường dùng cho luồng queue hoặc message riêng. |

Prefix /app thuộc lớp định tuyến ứng dụng của Spring. Nó tiếp tục hoạt động như cũ khi đổi từ simple broker sang broker relay.

Ngược lại, /topic và /queue là destination được chuyển cho broker xử lý. Với simple broker, chúng chủ yếu là tên/prefix để Spring khớp subscription và phân phối message. Với broker bên ngoài, ý nghĩa chính xác của destination phụ thuộc broker. Ví dụ, broker có thể ánh xạ topic thành exchange hoặc queue thành queue có tên; một số broker yêu cầu tạo destination, cấu hình quyền hoặc quy tắc tự động tạo destination trước.

Vì vậy, không nên giả định rằng destination /queue/notifications có cùng hành vi ở mọi broker. Cần đọc tài liệu broker đang chọn và thống nhất convention giữa client, Spring application và broker.

Các controller vẫn có thể giữ nguyên:

~~~java
@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage send(ChatMessage message) {
        return message;
    }
}
~~~

Client gửi đến /app/chat.send và subscribe /topic/chat. Spring vẫn nhận handler result rồi chuyển message qua brokerChannel. Khác biệt là message được phân phối bởi simple broker trong process hoặc được relay đến broker bên ngoài.

## 6. Khi nào chọn simple broker?

Simple broker thường là lựa chọn hợp lý khi:

- Ứng dụng nhỏ, lưu lượng và số kết nối đồng thời ở mức vừa phải.
- Chạy một instance Spring hoặc chấp nhận phạm vi phân phối chỉ trong một instance.
- Chỉ cần SEND, SUBSCRIBE và broadcast cơ bản.
- Không cần ACK/NACK, receipt, transaction hoặc queue bền vững.
- Không cần giữ message để client nhận lại sau khi offline.
- Muốn giảm thành phần hạ tầng và triển khai nhanh.
- Đang phát triển tính năng, làm prototype hoặc chạy integration test không cần kiểm chứng broker production.

Ví dụ: dashboard nội bộ chỉ hiển thị tiến độ của tác vụ đang chạy trên một instance, các client online cùng instance nhận cập nhật, và dữ liệu chính vẫn được lưu trong database. Nếu client mất kết nối, dashboard có thể tải lại trạng thái mới nhất từ API khi kết nối lại.

Không nên chọn simple broker chỉ vì nó dễ cấu hình nếu hệ thống đã có yêu cầu rõ ràng về phân phối đa instance, message durability hoặc protocol features mà simple broker không đáp ứng.

## 7. Khi nào chọn broker relay?

Broker relay phù hợp khi có một hoặc nhiều yêu cầu sau:

- Nhiều instance Spring cần phân phối message thông qua một broker dùng chung.
- Lưu lượng message hoặc số lượng subscriber cần broker chuyên dụng quản lý.
- Cần STOMP ACK/NACK, receipt, transaction hoặc tính năng broker nâng cao.
- Cần queue bền vững, durable subscription hoặc khả năng lưu message khi subscriber offline, với điều kiện broker hỗ trợ và đã cấu hình đúng.
- Muốn tách vòng đời của broker khỏi vòng đời triển khai Spring application.
- Hệ thống cần chính sách định tuyến, phân quyền destination, giám sát và quản trị message ở tầng broker.

Ví dụ: hệ thống thông báo có nhiều instance WebSocket sau load balancer. User A kết nối instance 1, user B kết nối instance 2; khi một service gửi sự kiện lên broker chung, các subscriber ở cả hai instance có thể nhận message thông qua relay và broker.

Relay cũng làm tăng trách nhiệm vận hành: cần triển khai broker, cấu hình network, credentials, ACL, monitoring, capacity, backup hoặc clustering theo yêu cầu. Broker relay không tự đảm bảo message được lưu bền vững; ứng dụng phải chọn và cấu hình đúng queue, exchange, subscription và persistence của broker.

## 8. Ma trận quyết định theo yêu cầu hệ thống

| Câu hỏi | Nếu câu trả lời là “có” | Hướng lựa chọn |
|---|---|---|
| Chỉ chạy một Spring instance và cần broadcast cơ bản? | Không cần phân phối qua nhiều instance. | Simple broker có thể đủ. |
| Cần nhiều instance Spring cùng phát và nhận message? | Cần broker dùng chung giữa các instance. | Broker relay. |
| Cần ACK/NACK hoặc receipt theo STOMP? | Cần protocol feature nâng cao. | Broker relay với broker hỗ trợ tính năng đó. |
| Cần queue/durable subscription hoặc lưu message offline? | Cần semantics lưu trữ do broker quản lý. | Broker relay và cấu hình persistence phù hợp. |
| Không có đội ngũ hoặc nền tảng vận hành broker? | Hạ tầng bổ sung là gánh nặng lớn. | Ưu tiên simple broker nếu các yêu cầu chức năng cho phép. |
| Có yêu cầu SLA, quan sát và kiểm soát message tập trung? | Cần broker có monitoring và chính sách quản trị. | Thường nghiêng về broker relay. |

Không có một ngưỡng số kết nối hoặc throughput cố định để quyết định thay cho đo đạc. Hãy benchmark với payload, tần suất publish, fan-out, kích thước subscription và mạng thực tế. Kiểm tra cả độ trễ p95/p99, CPU, heap, số connection và hành vi khi broker hoặc app instance gặp sự cố.

## 9. Lưu ý về mở rộng, độ tin cậy và bảo mật

### Mở rộng nhiều instance

Với simple broker, mỗi instance giữ subscription của các WebSocket session kết nối vào instance đó. Khi message được phát ở instance khác, không có cơ chế broker chung tự chuyển message đến. Nếu cần phân phối xuyên instance, phải thêm một cơ chế đồng bộ khác hoặc chuyển sang broker relay.

Với broker relay, các instance Spring kết nối cùng broker hoặc cụm broker. Broker chịu trách nhiệm phân phối đến subscription đã đăng ký qua các relay. Thiết kế vẫn phải tính đến khả năng broker cluster, partition, network failure và cấu hình destination.

### Độ tin cậy và message offline

WebSocket là kết nối thời gian thực; subscriber offline không đồng nghĩa message sẽ tự được lưu lại. Simple broker không cung cấp durable queue. Broker bên ngoài có thể hỗ trợ persistence, durable subscription, ACK và replay, nhưng từng tính năng phải được bật và dùng đúng semantics.

Nếu nghiệp vụ yêu cầu không mất thông báo, hãy lưu sự kiện hoặc trạng thái trong database/outbox và cung cấp cơ chế đồng bộ lại khi client kết nối. Không nên dựa riêng vào việc client subscribe topic để làm nguồn dữ liệu lâu dài.

### Bảo mật

- Chỉ cho phép client kết nối tới endpoint ứng dụng; không mở cổng STOMP broker trực tiếp ra Internet nếu không có lý do và lớp bảo vệ phù hợp.
- Bảo vệ relay-to-broker bằng network policy và TLS khi môi trường yêu cầu.
- Quản lý client credentials và system credentials riêng theo nguyên tắc quyền tối thiểu.
- Cấu hình ACL trên broker cho destination và operation cần thiết.
- Xác thực WebSocket/STOMP và phân quyền SEND/SUBSCRIBE ở Spring Security hoặc broker theo thiết kế.
- Không tin destination hoặc username do client tự khai báo khi xử lý dữ liệu riêng tư.

### Quan sát và vận hành

Khi dùng relay, theo dõi số client connection, system connection, reconnect, heartbeat timeout, message rate, queue depth, consumer lag, broker memory/disk và lỗi authorization. Thiết lập cảnh báo cho broker không khả dụng, queue tăng bất thường và connection bị từ chối.

## 10. Chuyển từ simple broker sang broker relay

Một lộ trình chuyển đổi có thể thực hiện theo các bước:

1. Xác định yêu cầu bắt buộc: nhiều instance, ACK/NACK, receipt, durable queue, throughput, latency và SLA.
2. Chọn broker hỗ trợ STOMP; kiểm tra phiên bản, plugin/connector, destination semantics và các giới hạn của broker.
3. Triển khai broker trong môi trường phát triển hoặc staging; mở network path từ các Spring instance đến cổng STOMP.
4. Tạo credentials riêng cho client relay và system connection; cấu hình ACL tối thiểu cần thiết.
5. Thay `enableSimpleBroker(...)` bằng `enableStompBrokerRelay(...)` và cấu hình host, port, credentials, heartbeat phù hợp.
6. Giữ application destination prefix /app và kiểm tra lại các destination /topic, /queue, /user theo semantics của broker.
7. Kiểm thử SEND, SUBSCRIBE, @SendTo, SimpMessagingTemplate, user destination, reconnect, nhiều instance và hành vi khi broker dừng.
8. Đo hiệu năng và giám sát connection, message rate, queue depth trước khi triển khai production.

Không cần viết lại mọi @MessageMapping chỉ vì đổi broker. Phần controller và API client có thể giữ nguyên nếu destination semantics và quyền truy cập được bảo toàn. Tuy vậy, các giả định trước đây về queue, topic, subscription và message offline cần được kiểm tra lại.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Relay không kết nối được broker | Sai host/port, plugin STOMP chưa bật, firewall hoặc credentials không hợp lệ | Kiểm tra log relay, cổng STOMP và log broker. |
| Client SEND thành công nhưng subscriber không nhận | Destination không được broker xử lý hoặc ACL từ chối | Kiểm tra destination, broker routing và quyền publish/subscribe. |
| Message chỉ đến client trên một instance | Ứng dụng vẫn dùng simple broker riêng trên mỗi instance hoặc relay không cùng broker | Kiểm tra loại registration và địa chỉ broker của mọi instance. |
| /queue có hành vi khác sau khi chuyển broker | Destination semantics của broker khác simple broker | Đọc tài liệu broker và cấu hình queue/exchange tương ứng. |
| Client offline rồi kết nối lại nhưng không thấy message cũ | Chưa cấu hình durable queue/subscription hoặc message persistence | Kiểm tra loại queue, subscription, ACK và chính sách lưu trữ. |
| Broker từ chối nhiều kết nối | Giới hạn connection hoặc thiếu capacity | Đo số WebSocket client đồng thời và connection relay đến broker. |
| Kết nối chết nhưng client không phát hiện kịp | Heartbeat, proxy timeout hoặc reconnect chưa được cấu hình phù hợp | Kiểm tra heartbeat hai chiều, timeout và chiến lược reconnect. |
| System message không gửi được nhưng client vẫn kết nối | System connection hoặc system credentials bị lỗi | Kiểm tra log system connection và quyền của system user. |

## 12. Kết luận lựa chọn

Chọn simple broker khi hệ thống chỉ cần pub/sub cơ bản trong phạm vi một Spring instance và muốn giảm hạ tầng. Chọn broker relay khi cần broker dùng chung cho nhiều instance, protocol features nâng cao, hoặc queue và persistence do broker chuyên dụng cung cấp.

Quyết định cuối cùng cần dựa trên yêu cầu chức năng, tải thực tế, mục tiêu độ tin cậy, khả năng vận hành và tính năng thật sự của broker được chọn. Broker relay là đường tích hợp với hạ tầng message broker; nó không tự động biến mọi destination thành queue bền vững hoặc bảo đảm message không mất.

## Tài liệu tham khảo

- [Spring Framework — Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html): cách bật simple broker, destination prefix và giới hạn của broker tích hợp.
- [Spring Framework — STOMP Broker Relay](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html): kết nối broker bên ngoài, system connection và client connection.
- [Spring Framework — Enable STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html): cấu hình endpoint, application prefix và message broker.
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html): luồng message giữa client, application và broker.
