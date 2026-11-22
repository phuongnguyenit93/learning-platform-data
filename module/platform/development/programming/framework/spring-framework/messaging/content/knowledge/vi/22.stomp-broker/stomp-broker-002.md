# Giới hạn tính năng, độ bền và khả năng mở rộng của Simple Broker trong Spring STOMP

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích Simple Broker của Spring lưu trạng thái gì và phân phối message theo cách nào.
- Nhận biết giới hạn của Simple Broker về tập lệnh STOMP, xác nhận giao nhận, lưu trữ message và subscription.
- Phân biệt prefix như /topic và /queue với ngữ nghĩa thực tế của một message queue.
- Phân tích vì sao Simple Broker phù hợp với ứng dụng nhỏ, một instance và dữ liệu thời gian thực có thể bỏ lỡ.
- Chọn thời điểm chuyển sang STOMP Broker Relay và một message broker bên ngoài.
- Thiết kế kiểm thử, quan sát và xử lý sự cố khi broker hoặc kết nối client gián đoạn.

Bài viết tập trung vào Spring Framework STOMP over WebSocket. Simple Broker là broker tích hợp sẵn, chạy trong bộ nhớ của tiến trình ứng dụng. Đây là một lựa chọn gọn nhẹ để bắt đầu, thử nghiệm và phát thông báo thời gian thực trong phạm vi một ứng dụng đơn giản.

## 1. Simple Broker là gì?

Khi bật STOMP bằng cấu hình WebSocket của Spring, ứng dụng có thể định tuyến message tới hai nơi chính:

1. Các phương thức xử lý trong controller, thường được đánh dấu bằng @MessageMapping.
2. Message broker, nơi quản lý subscription và phát message tới client đã đăng ký.

Simple Broker là thành phần broker tích hợp trong Spring. Nó nhận yêu cầu SUBSCRIBE, lưu thông tin subscription trong bộ nhớ, rồi phát message đến các client đang kết nối có destination khớp. Broker hỗ trợ destination dạng đường dẫn và mẫu Ant-style.

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

Trong cấu hình này:

- Client kết nối WebSocket tới endpoint /ws.
- Message có destination bắt đầu bằng /app được định tuyến tới các handler của ứng dụng.
- Message có destination bắt đầu bằng /topic hoặc /queue được định tuyến tới Simple Broker.
- Handler hoặc service phía server có thể phát message qua SimpMessagingTemplate để broker phân phối cho các subscription phù hợp.

Luồng message ở mức khái quát:

~~~text
WebSocket client
      |
      | STOMP SEND / SUBSCRIBE
      v
clientInboundChannel
      |
      +---- destination /app/... ------> @MessageMapping controller
      |                                      |
      |                                      | gửi message qua brokerChannel
      |                                      v
      +---- destination /topic/... ---> Simple Broker
                                             |
                                             | tìm subscription khớp
                                             v
                                      clientOutboundChannel
                                             |
                                             v
                                      WebSocket clients
~~~

Simple Broker quản lý việc phân phối trong chính tiến trình Spring. Nó không phải một dịch vụ broker độc lập chạy ở máy chủ riêng và cũng không tự tạo ra một kho lưu trữ message lâu dài.

## 2. Simple Broker lưu gì trong bộ nhớ?

Simple Broker lưu trạng thái subscription của các client đang kết nối. Khi một client gửi SUBSCRIBE, broker ghi nhận session, subscription và destination để có thể định tuyến các message tiếp theo. Khi client hủy subscription hoặc phiên kết thúc, trạng thái tương ứng được dọn dẹp.

Điểm cần phân biệt:

- **Subscription state:** thông tin client nào đang nghe destination nào. Simple Broker lưu phần này trong bộ nhớ.
- **Message payload:** nội dung message được phát tới các subscription phù hợp. Simple Broker không phải message store để lưu lịch sử và phát lại message về sau.
- **Business state:** dữ liệu nghiệp vụ của ứng dụng, chẳng hạn đơn hàng, giao dịch hay trạng thái công việc. Dữ liệu này phải được lưu ở cơ sở dữ liệu hoặc hệ thống lưu trữ phù hợp của ứng dụng.

Ví dụ, client A đang đăng ký /topic/orders. Khi server phát một thông báo tới destination đó, Simple Broker phân phối thông báo tới những subscription phù hợp đang tồn tại. Nếu một client chưa kết nối hoặc đã mất kết nối tại thời điểm phát, không nên giả định broker giữ message để client đó nhận lại khi kết nối sau.

Khi tiến trình Spring dừng hoặc khởi động lại, trạng thái subscription trong bộ nhớ bị mất. Client phải kết nối lại và đăng ký subscription lại. Simple Broker không khôi phục danh sách subscriber cũ từ đĩa.

Vì vậy, hãy xem Simple Broker như một cơ chế phát thông báo trực tiếp tới các client hiện đang nghe, thay vì một hệ thống lưu trữ sự kiện hay hàng đợi công việc.

## 3. Giới hạn về tập tính năng STOMP

Simple Broker chỉ hỗ trợ một phần các lệnh và tính năng của STOMP. Theo tài liệu Spring, các tính năng như ACK và RECEIPT không được hỗ trợ, cùng với một số tính năng khác của broker đầy đủ.

### 3.1 Không có ACK theo cơ chế broker

ACK là cơ chế để client xác nhận đã xử lý message theo chế độ acknowledgment mà broker hỗ trợ. Nếu ứng dụng cần xác nhận xử lý từ consumer, phát hiện message chưa được xác nhận hoặc yêu cầu broker phát lại message, Simple Broker không cung cấp đầy đủ cơ chế đó.

Việc client nhận được frame MESSAGE trên kết nối không đồng nghĩa với việc nghiệp vụ ở client đã xử lý và lưu thành công. Nếu cần xác nhận nghiệp vụ, hãy thiết kế giao thức ứng dụng riêng, chẳng hạn client gửi một message xác nhận có mã sự kiện, và server lưu kết quả xác nhận ở nơi bền vững.

### 3.2 Không có RECEIPT của broker

STOMP RECEIPT cho phép client yêu cầu broker phản hồi rằng một frame đã được xử lý theo quy ước giao thức. Simple Broker không hỗ trợ RECEIPT như một broker STOMP đầy đủ.

Do đó, không nên xây dựng logic phụ thuộc vào việc gửi SEND hoặc SUBSCRIBE kèm receipt header rồi chờ RECEIPT từ Simple Broker.

### 3.3 Không phải broker STOMP đầy đủ

STOMP định nghĩa nhiều command và khả năng khác nhau. Simple Broker được thiết kế để đáp ứng một tập hợp cơ bản phục vụ subscribe và broadcast. Khi yêu cầu nghiệp vụ phụ thuộc vào các tính năng broker nâng cao, cần kiểm tra khả năng hỗ trợ của broker bên ngoài được chọn và cấu hình tương ứng.

Đừng suy luận rằng vì ứng dụng sử dụng STOMP nên mọi command hoặc delivery mode trong đặc tả STOMP đều tự động được Spring Simple Broker hỗ trợ.

## 4. Giới hạn về độ bền và giao nhận message

Độ bền (durability) là khả năng bảo toàn dữ liệu hoặc message qua sự cố, khởi động lại và khoảng thời gian consumer không hoạt động. Simple Broker không cung cấp message persistence hay durable subscription như một message broker chuyên dụng.

### 4.1 Không có message persistence

Simple Broker không ghi message vào đĩa hoặc một kho lưu trữ lâu dài để có thể phục hồi sau khi tiến trình dừng. Nếu ứng dụng phát một message rồi tiến trình bị dừng, Simple Broker không thể phát lại message đó sau khi khởi động.

### 4.2 Không có hàng đợi offline cho subscriber

Một subscription trong Simple Broker gắn với client đang kết nối. Nếu client offline khi message được phát, broker không lưu một bản message để giao lại cho client khi nó quay lại.

Ví dụ:

1. Client A đăng ký /topic/notifications.
2. Client A ngắt kết nối.
3. Server phát một notification.
4. Client A kết nối lại và đăng ký lại.
5. Simple Broker không có lịch sử notification bị bỏ lỡ để tự động phát lại.

Nếu người dùng cần xem thông báo cũ, ứng dụng phải đọc chúng từ cơ sở dữ liệu hoặc API lịch sử, rồi dùng STOMP để thông báo rằng có dữ liệu mới.

### 4.3 Không có durable subscription sau khi restart

Subscription được giữ trong bộ nhớ và gắn với phiên client. Sau khi tiến trình ứng dụng dừng, broker không phục hồi subscription từ một kho bền vững. Client cần reconnect và resubscribe.

### 4.4 Không có bảo đảm xử lý nghiệp vụ end-to-end

Một message được gửi qua WebSocket có thể bị ảnh hưởng bởi mất mạng, đóng tab, client ngừng hoạt động, lỗi chuyển đổi payload hoặc lỗi xử lý ở phía nhận. Simple Broker không biến luồng broadcast thành một giao dịch nghiệp vụ đáng tin cậy.

Nếu một sự kiện quan trọng như thanh toán, thay đổi số dư, đặt hàng hay phê duyệt phải được bảo toàn, hãy lưu sự kiện nghiệp vụ trước. Sau đó phát notification để client cập nhật giao diện. Client có thể dùng event ID hoặc version để gọi API đồng bộ lại nếu phát hiện thiếu dữ liệu.

Mẫu thiết kế thường dùng:

~~~text
Business request
      |
      v
Database transaction
      |
      +---- cập nhật dữ liệu nghiệp vụ
      |
      +---- ghi event vào outbox
                    |
                    v
             Background publisher
                    |
                    v
              Message broker
                    |
                    v
              STOMP / WebSocket
                    |
                    v
              Connected clients
~~~

Outbox giúp ứng dụng không đánh mất ý định phát sự kiện khi transaction nghiệp vụ đã commit nhưng quá trình gửi message bị lỗi. Worker có thể thử gửi lại bản ghi outbox. Phía nhận vẫn nên xử lý idempotent vì retry có thể tạo ra message trùng.

## 5. Vì sao /queue không tự trở thành một hàng đợi thật?

Destination name trong STOMP là chuỗi do broker định nghĩa ngữ nghĩa. Trong nhiều hệ thống, /topic thường được dùng cho publish-subscribe và /queue thường gợi ý point-to-point. Tuy nhiên, prefix chỉ là quy ước định tuyến; ngữ nghĩa thật phụ thuộc vào broker đang xử lý destination.

Simple Broker phát message tới các client đang kết nối có subscription khớp destination. Vì vậy, nếu ba client cùng đăng ký /queue/tasks trên Simple Broker, cả ba đều có thể nhận cùng một message được phát tới destination đó.

Tên /queue/tasks không tự tạo ra các tính năng sau:

- Một message chỉ được một consumer trong nhóm nhận.
- Message được giữ lại cho consumer đến sau.
- Message được xác nhận bằng ACK rồi mới loại khỏi queue.
- Message chưa được xác nhận được redeliver.
- Queue có thể tồn tại độc lập với vòng đời ứng dụng Spring.

Đây là khác biệt quan trọng giữa một destination có tên /queue và một queue thực sự do message broker quản lý.

Nếu cần mô hình competing consumers, công việc nền, retry, dead-letter queue hoặc lưu message chờ xử lý, hãy dùng broker chuyên dụng và cấu hình queue theo tài liệu của broker đó.

## 6. Giới hạn mở rộng và clustering

Simple Broker chạy trong bộ nhớ của một instance Spring. Mỗi instance có tập subscription riêng. Nó không phải broker phân tán và Spring nêu rõ Simple Broker không phù hợp để clustering.

Giả sử triển khai hai instance sau load balancer:

~~~text
                 Load balancer
                  /         \
                 v           v
          Spring node A   Spring node B
          Simple Broker   Simple Broker
          subscriptions   subscriptions
                 |           |
              Client A    Client B
~~~

Nếu Client A kết nối vào node A và Client B kết nối vào node B, mỗi Simple Broker chỉ biết các subscription trên node của nó. Một message được phát cục bộ ở node A không tự động được chia sẻ sang Simple Broker ở node B.

Điều này dẫn đến một số rủi ro:

- Người dùng ở các node khác nhau có thể không nhận cùng một broadcast.
- Kết quả phụ thuộc vào node đang giữ WebSocket session.
- Tăng số instance ứng dụng không tự động tăng phạm vi phân phối message toàn hệ thống.
- Sticky session chỉ giữ một client gắn với một node; nó không đồng bộ subscription hoặc message giữa các node.
- Khi node bị thay thế hoặc khởi động lại, subscription của node đó mất và client phải kết nối lại.

Đối với một ứng dụng một instance, phạm vi này có thể hoàn toàn phù hợp. Khi cần chạy nhiều node, cần một thành phần broker dùng chung để các node cùng định tuyến message và subscription.

## 7. Giới hạn hiệu năng và tài nguyên

Simple Broker dùng một vòng lặp gửi message đơn giản. Với mỗi message, broker cần tìm các subscription phù hợp và chuyển message tới các client tương ứng. Khi số lượng client, subscription, tần suất gửi hoặc số người nhận mỗi message tăng lên, công việc phân phối và lưu trạng thái cũng tăng theo.

Các yếu tố ảnh hưởng:

- Số WebSocket session đang hoạt động.
- Số subscription trên mỗi session.
- Số destination pattern cần so khớp.
- Tần suất message gửi vào broker.
- Số lượng subscriber nhận mỗi message.
- Kích thước payload.
- Băng thông outbound và tốc độ xử lý của client.
- Số thread và cấu hình các channel trong ứng dụng.

Spring không đưa ra một ngưỡng số client cố định áp dụng cho mọi hệ thống. Khả năng chịu tải phụ thuộc phần cứng, cấu hình thread, payload, pattern, tần suất broadcast, mạng và hành vi của client. Không nên tự đặt một con số tối đa chung rồi coi đó là giới hạn chính thức của Simple Broker.

Hãy đo trong môi trường gần với production. Kiểm thử tải cần mô phỏng số session, subscription, message rate, kích thước payload và tỷ lệ fan-out thực tế. Theo dõi CPU, heap, GC, số kết nối, độ trễ publish-to-client, outbound throughput, lỗi gửi và số session bị ngắt.

Khi vượt khả năng một instance, tăng CPU hoặc heap có thể giúp trong một phạm vi nhất định nhưng không giải quyết giới hạn kiến trúc về clustering. Nếu nhu cầu là broadcast phân tán, cần chuyển phần broker sang một hệ thống được thiết kế cho việc đó.

## 8. Heartbeat giúp phát hiện kết nối, không tạo durability

Simple Broker có thể hỗ trợ STOMP heartbeat khi được cấu hình với TaskScheduler. Heartbeat giúp phát hiện kết nối không còn hoạt động và hỗ trợ quản lý trạng thái kết nối.

Ví dụ cấu hình phần broker:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.enableSimpleBroker("/topic", "/queue")
            .setHeartbeatValue(new long[] {10_000, 10_000})
            .setTaskScheduler(messageBrokerTaskScheduler);

    registry.setApplicationDestinationPrefixes("/app");
}
~~~

Trong ví dụ, messageBrokerTaskScheduler là một TaskScheduler bean do ứng dụng cung cấp. Hai giá trị heartbeat được tính bằng mili giây cho khoảng gửi và nhận theo cấu hình STOMP.

Heartbeat có ích cho việc phát hiện kết nối im lặng hoặc đã đứt. Nó không:

- Lưu message vào đĩa.
- Khôi phục message bị bỏ lỡ.
- Giữ subscription sau khi ứng dụng restart.
- Xác nhận client đã xử lý nghiệp vụ.
- Đồng bộ subscription giữa nhiều node.

Không nên nhầm heartbeat với ACK, RECEIPT hoặc cơ chế retry. Chúng giải quyết những vấn đề khác nhau.

## 9. Khi nào nên dùng Simple Broker?

Simple Broker phù hợp khi:

- Ứng dụng nhỏ hoặc đang ở giai đoạn phát triển.
- Triển khai chỉ có một instance Spring.
- Client chủ yếu cần nhận thông báo trực tiếp trong lúc đang kết nối.
- Message có thể được tạo lại hoặc client có thể lấy lại dữ liệu qua API.
- Không cần ACK, RECEIPT, durable queue hoặc offline delivery.
- Có thể chấp nhận subscription mất khi tiến trình khởi động lại.
- Tải đã được đo và nằm trong năng lực của một instance.

Ví dụ phù hợp:

- Dashboard hiển thị số liệu mới nhất.
- Trang quản trị cập nhật trạng thái tác vụ đang chạy.
- Chat nội bộ đơn giản khi lịch sử chat được lưu riêng trong database.
- Màn hình giám sát thiết bị đang online.
- Thông báo UI rằng client nên tải lại một bản ghi mới.

Trong các ví dụ trên, database hoặc API vẫn là nguồn dữ liệu chính. STOMP chỉ giúp giao diện nhận tín hiệu cập nhật nhanh hơn.

## 10. Khi nào cần External Broker và Broker Relay?

Hãy cân nhắc broker bên ngoài khi ứng dụng cần:

- Nhiều instance Spring cùng phát và nhận message.
- Khả năng clustering hoặc phân phối message giữa các node.
- ACK, RECEIPT hoặc các tính năng STOMP nâng cao mà broker hỗ trợ.
- Queue thực sự, competing consumers hoặc các chính sách định tuyến phức tạp.
- Durable subscription, persistent message, retry hoặc dead-letter queue.
- Điều phối message giữa nhiều service hoặc ứng dụng.
- Tách vòng đời broker khỏi vòng đời của từng tiến trình Spring.

Spring hỗ trợ kết nối với broker bên ngoài thông qua STOMP Broker Relay. Broker relay là một MessageHandler chuyển tiếp message qua TCP tới một message broker hỗ trợ STOMP, rồi chuyển message nhận từ broker xuống các WebSocket session.

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
        registry.enableStompBrokerRelay("/topic", "/queue");
    }
}
~~~

Ví dụ này minh họa việc thay Simple Broker bằng broker relay. Ứng dụng phải cài đặt và chạy một broker bên ngoài có hỗ trợ STOMP, sau đó cấu hình host, port, thông tin xác thực, virtual host và các destination prefix phù hợp.

Một số broker thường được dùng là RabbitMQ (với STOMP plugin) và ActiveMQ. Cần đọc tài liệu của broker cụ thể để biết cách bật STOMP, tạo exchange/queue, đặt quyền, cấu hình persistence, ACK, retry, dead-letter và giới hạn tài nguyên.

Broker relay không tự tạo ra durability. Nó chuyển tiếp message đến broker ngoài. Muốn message bền vững, cần cấu hình persistence và queue/subscription phù hợp ở broker đó. Khả năng ACK, receipt, durable subscription và routing cũng phụ thuộc vào sản phẩm, phiên bản, giao thức và cấu hình thực tế.

## 11. Broker Relay có những kết nối nào?

Spring STOMP Broker Relay sử dụng hai nhóm kết nối TCP:

1. **System connection:** một kết nối do Spring duy trì để chuyển message phát sinh từ phía ứng dụng server tới broker.
2. **Client connections:** một kết nối TCP riêng cho mỗi WebSocket client đang kết nối; relay chuyển STOMP frame của client qua kết nối tương ứng tới broker.

Cấu trúc khái quát:

~~~text
Spring application
   | 
   +---- system TCP connection -------------------+
   |                                               |
   +---- client A TCP connection -----------------+--> External STOMP broker
   |                                               |
   +---- client B TCP connection -----------------+
   |
   +---- client C TCP connection -----------------+
   
WebSocket clients <---- Spring relay <----> External broker
~~~

Vì mỗi client WebSocket có một TCP connection tương ứng tới broker, khi thiết kế cần tính cả giới hạn kết nối và tài nguyên của broker. Tăng số WebSocket client đồng nghĩa với tăng số kết nối client-side mà relay cần duy trì tới broker.

Relay có cơ chế thử kết nối lại system connection khi broker tạm thời mất kết nối. Tuy nhiên, kết nối WebSocket/STOMP của client không tự động được khôi phục chỉ vì system connection đã phục hồi. Client cần có logic reconnect và subscribe lại.

## 12. Theo dõi trạng thái và xử lý sự cố với Broker Relay

Spring phát ApplicationContext event BrokerAvailabilityEvent để thông báo khi system connection của broker relay mất hoặc được thiết lập lại. Thành phần server có thể lắng nghe event này để biết lúc nào broker sẵn sàng nhận message.

Ví dụ:

~~~java
@Component
public class BrokerStatusListener
        implements ApplicationListener<BrokerAvailabilityEvent> {

    @Override
    public void onApplicationEvent(BrokerAvailabilityEvent event) {
        if (event.isBrokerAvailable()) {
            // Broker system connection đã sẵn sàng
        } else {
            // Broker system connection hiện không sẵn sàng
        }
    }
}
~~~

Đây là tín hiệu về trạng thái kết nối system của relay, không phải bằng chứng rằng mọi client session đều đang hoạt động hoặc mọi message đã được xử lý.

Khi dùng SimpMessagingTemplate để phát message qua relay, ứng dụng cần chuẩn bị xử lý MessageDeliveryException nếu broker chưa sẵn sàng hoặc việc gửi thất bại. Với sự kiện nghiệp vụ quan trọng, nên giữ sự kiện trong outbox hoặc một kho lưu trữ bền vững để có thể gửi lại.

Các event khác có ích cho quản lý session:

- SessionConnectEvent: nhận thông báo khi STOMP CONNECT bắt đầu.
- SessionConnectedEvent: thông báo phiên STOMP đã được xác lập.
- SessionSubscribeEvent: nhận thông báo client đăng ký subscription.
- SessionUnsubscribeEvent: nhận thông báo client hủy subscription.
- SessionDisconnectEvent: nhận thông báo phiên STOMP kết thúc.

SessionDisconnectEvent có thể được phát nhiều hơn một lần cho cùng một session trong một số tình huống. Listener cần xử lý idempotent, ví dụ chỉ đánh dấu offline khi trạng thái hiện tại thực sự cần thay đổi.

## 13. So sánh Simple Broker và External Broker Relay

| Tiêu chí | Simple Broker | External Broker Relay |
|---|---|---|
| Nơi chạy | Trong tiến trình Spring | Broker STOMP bên ngoài, Spring chuyển tiếp |
| Trạng thái subscription | Trong bộ nhớ của một instance | Do broker bên ngoài quản lý theo khả năng của broker |
| Phạm vi phân phối | Các client phù hợp trên cùng instance | Có thể chia sẻ qua nhiều instance dùng chung broker |
| Clustering | Không phù hợp | Hỗ trợ kiến trúc phân tán tùy broker |
| ACK và RECEIPT | Không hỗ trợ đầy đủ; Spring nêu rõ không có ACK/RECEIPT | Phụ thuộc tính năng STOMP của broker |
| Message persistence | Không có kho message bền vững | Có thể cấu hình nếu broker hỗ trợ |
| Offline/durable subscription | Không có durable subscription tích hợp | Có thể có, phụ thuộc broker và cấu hình |
| Vận hành | Ít thành phần, dễ bắt đầu | Cần vận hành, bảo mật và giám sát broker riêng |
| Kịch bản phù hợp | Broadcast tạm thời, một instance | Hệ thống nhiều node, yêu cầu broker nâng cao |

Bảng này mô tả năng lực tổng quát. Khi chọn một broker ngoài, hãy kiểm tra tài liệu chính thức và thử nghiệm đúng phiên bản cùng cấu hình sẽ triển khai.

## 14. Quy trình quyết định và chuyển đổi

Trước khi giữ Simple Broker, hãy trả lời các câu hỏi sau:

1. Nếu một client offline trong vài phút, nó có cần nhận lại toàn bộ message đã bỏ lỡ không?
2. Nếu tiến trình Spring restart, subscription và message có cần được khôi phục không?
3. Một message có cần chỉ được một consumer trong nhóm xử lý không?
4. Ứng dụng có cần ACK, RECEIPT, retry hoặc dead-letter queue không?
5. Có nhiều instance Spring cần chia sẻ cùng một luồng broadcast không?
6. Tải thực tế có nằm trong năng lực của một instance theo kiểm thử hay chưa?

Nếu mọi câu trả lời đều cho thấy message chỉ là tín hiệu thời gian thực tạm thời, Simple Broker có thể là lựa chọn hợp lý.

Nếu cần durable delivery, xử lý nền đáng tin cậy, nhiều consumer hoặc clustering, hãy chọn broker chuyên dụng. Quá trình chuyển đổi thường gồm:

1. Chọn broker có hỗ trợ STOMP và đáp ứng yêu cầu về persistence, ACK, queue và HA.
2. Cài đặt, bật STOMP endpoint và cấu hình quyền truy cập trên broker.
3. Thay enableSimpleBroker bằng enableStompBrokerRelay với prefix phù hợp.
4. Cấu hình host, port, credentials, virtual host và các giới hạn kết nối.
5. Tạo queue/exchange/subscription cùng chính sách durable, persistent, retry hoặc dead-letter ở broker ngoài.
6. Kiểm thử ACK, RECEIPT, reconnect, restart broker, restart ứng dụng và nhiều instance.
7. Theo dõi BrokerAvailabilityEvent, lỗi gửi, số kết nối và độ trễ.
8. Cập nhật client để reconnect, resubscribe và đồng bộ dữ liệu bị bỏ lỡ qua API khi cần.

Controller @MessageMapping và SimpMessagingTemplate thường có thể giữ nguyên mô hình lập trình. Phần thay đổi chủ yếu nằm ở cấu hình broker và các bảo đảm giao nhận mà ứng dụng quyết định sử dụng.

## 15. Kiểm thử các giới hạn quan trọng

Một bài kiểm thử hữu ích nên xác nhận hành vi thực tế, không chỉ kiểm tra cấu hình khởi động.

| Tình huống | Cách kiểm thử | Kỳ vọng với Simple Broker |
|---|---|---|
| Client đang subscribe | Hai client subscribe cùng destination rồi server publish | Các client đang kết nối có subscription khớp đều nhận message |
| Client offline | Ngắt kết nối một client, publish, rồi kết nối lại và subscribe | Không có message lịch sử tự động được phát lại |
| Restart ứng dụng | Có subscription, dừng và khởi động lại Spring | Client phải kết nối và subscribe lại |
| Gửi RECEIPT | Gửi frame có receipt header | Không dựa vào việc Simple Broker trả RECEIPT |
| ACK | Thử dùng acknowledgment mode cần broker hỗ trợ | Không dựa vào ACK/redelivery của Simple Broker |
| Hai instance | Client kết nối vào hai node khác nhau, publish từ một node | Không giả định Simple Broker tự phân phối xuyên node |
| Heartbeat | Cấu hình TaskScheduler và heartbeat rồi ngắt mạng | Kiểm tra phát hiện kết nối lỗi; không coi đây là phục hồi message |
| Fan-out lớn | Tăng dần session, subscriber, message rate và payload | Đo độ trễ, CPU, heap, GC và lỗi thay vì giả định một ngưỡng cố định |

Với broker relay, chạy lại các bài kiểm thử trên và bổ sung tình huống broker restart, broker mất kết nối, reconnect client, durable subscription và persistence theo cấu hình cụ thể. Một bài test chỉ chứng minh broker hoạt động trong cấu hình được thử; nó không chứng minh mọi bảo đảm đều tồn tại trong cấu hình production.

## 16. Lỗi thiết kế thường gặp

| Lỗi | Hệ quả | Cách khắc phục |
|---|---|---|
| Xem Simple Broker như database | Dữ liệu notification bị mất khi ứng dụng dừng | Lưu lịch sử ở database hoặc event store |
| Mong client offline nhận lại message | Client bỏ lỡ thông báo khi không kết nối | Cung cấp API lịch sử hoặc dùng durable queue/subscription của broker phù hợp |
| Đặt tên destination là /queue rồi kỳ vọng competing consumers | Nhiều subscriber khớp destination có thể cùng nhận broadcast | Dùng queue thực do broker bên ngoài quản lý |
| Dựa vào ACK/RECEIPT của Simple Broker | Logic xác nhận giao nhận không hoạt động như mong muốn | Chuyển sang broker hỗ trợ hoặc xây dựng xác nhận nghiệp vụ riêng |
| Chạy nhiều instance nhưng giữ Simple Broker | Subscriber trên node khác không được đồng bộ | Dùng broker dùng chung qua STOMP relay |
| Coi heartbeat là bảo đảm giao hàng | Kết nối được phát hiện nhưng message vẫn có thể mất | Thiết kế persistence, retry và reconciliation riêng |
| Tin rằng relay tự bật durability | Message vẫn có thể không bền nếu broker chưa cấu hình | Cấu hình persistent message và durable queue/subscription tại broker |
| Không kiểm thử reconnect | Client có thể mất subscription sau khi kết nối bị đứt | Client tự reconnect, resubscribe và đồng bộ lại trạng thái |

## 17. Kết luận thực hành

Simple Broker là một bộ phân phối message trong bộ nhớ, dành cho các subscription đang hoạt động trên cùng tiến trình Spring. Nó thuận tiện cho broadcast thời gian thực đơn giản, nhưng không cung cấp message persistence, durable subscription, ACK/RECEIPT đầy đủ hoặc khả năng clustering.

Khi hệ thống cần bảo đảm giao nhận, lưu trữ message, xử lý nền hoặc phân phối qua nhiều instance, hãy dùng STOMP Broker Relay kết nối tới một broker chuyên dụng. Hãy nhớ rằng relay chỉ chuyển tiếp message; persistence, durable queue, retry, ACK và HA phải được hỗ trợ và cấu hình ở broker bên ngoài. Với dữ liệu nghiệp vụ quan trọng, database hoặc outbox vẫn là nguồn bảo đảm bền vững, còn WebSocket/STOMP là kênh thông báo cho client.

## Tài liệu tham khảo

- [Spring Framework — Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework — External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework — Connecting to a Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html)
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework — Application Context Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html)
- [Spring Framework — STOMP Overview](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/overview.html)
