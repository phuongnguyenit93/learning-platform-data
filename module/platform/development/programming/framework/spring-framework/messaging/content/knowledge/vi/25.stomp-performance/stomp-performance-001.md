# Cấu hình executor của clientInboundChannel và clientOutboundChannel

## 1. Vai trò của hai message channel

Trong Spring WebSocket/STOMP, message được chuyển qua các channel nội bộ trước khi tới controller, broker hoặc WebSocket client. Hai channel quan trọng nhất ở phía client là:

- **clientInboundChannel** nhận message từ WebSocket client sau khi Spring giải mã STOMP frame. Các frame như CONNECT, SUBSCRIBE, SEND và DISCONNECT đi vào channel này để được xử lý, kiểm tra qua interceptor và định tuyến tiếp.
- **clientOutboundChannel** nhận message từ broker hoặc ứng dụng server để gửi về WebSocket client. Spring chuyển message thành STOMP frame rồi ghi lên session tương ứng.

Luồng khái quát:

~~~mermaid
flowchart LR
    C["WebSocket client"] -->|"STOMP frames"| I["clientInboundChannel"]
    I -->|"SEND /app/**"| H["@MessageMapping controller"]
    I -->|"SUBSCRIBE /topic/**"| B["Message broker"]
    H -->|"application message"| BC["brokerChannel"]
    BC --> B
    B --> O["clientOutboundChannel"]
    H -->|"user / direct reply"| O
    O -->|"STOMP frames"| C
~~~

Trong luồng này:

- Message từ client đi qua `clientInboundChannel`.
- Message từ server-side code tới broker thường đi qua `brokerChannel`.
- Message từ broker hoặc ứng dụng gửi tới client đi qua `clientOutboundChannel`.

`clientInboundChannel` và `clientOutboundChannel` là các `ExecutorSubscribableChannel` được hỗ trợ bởi thread pool. Hai channel có executor riêng vì tải công việc khác nhau: inbound chủ yếu xử lý frame và logic ứng dụng; outbound chủ yếu phân phối message tới các WebSocket session.

## 2. Vì sao cần cấu hình executor?

Executor quyết định số tác vụ message có thể xử lý đồng thời, số tác vụ được xếp hàng và cách hệ thống phản ứng khi tải tăng.

Nếu pool quá nhỏ:

- Message phải chờ lâu trong queue.
- Thời gian xử lý tăng và client thấy độ trễ realtime.
- Inbound controller có thể không theo kịp tốc độ gửi của client.
- Outbound message có thể bị chậm khi nhiều client cùng nhận broadcast.

Nếu pool hoặc queue quá lớn:

- Ứng dụng có thể tạo quá nhiều thread, gây tranh chấp CPU và bộ nhớ.
- Queue lớn giữ nhiều message trong heap, làm tăng độ trễ và nguy cơ thiếu bộ nhớ.
- Database connection pool hoặc dịch vụ bên ngoài có thể bị quá tải nếu quá nhiều handler cùng chờ I/O.
- Tăng max thread không tự động tăng throughput nếu bottleneck nằm ở database, broker, network hoặc client.

Mục tiêu là chọn kích thước phù hợp với loại công việc, thời gian xử lý, số lượng client, tốc độ message và giới hạn tài nguyên của hệ thống.

## 3. Cấu hình qua WebSocketMessageBrokerConfigurer

Spring cung cấp hai callback riêng:

- `configureClientInboundChannel(ChannelRegistration registration)` để cấu hình executor cho message từ client.
- `configureClientOutboundChannel(ChannelRegistration registration)` để cấu hình executor cho message gửi về client.

Dùng `registration.taskExecutor()` để lấy cấu hình thread pool. Các phương thức chính:

| Phương thức | Ý nghĩa |
|---|---|
| `corePoolSize(n)` | Số thread lõi được duy trì trong pool. |
| `maxPoolSize(n)` | Số thread tối đa pool có thể mở rộng tới. |
| `queueCapacity(n)` | Số tác vụ tối đa được xếp hàng chờ thread xử lý. |
| `keepAliveSeconds(n)` | Thời gian thread vượt quá core size có thể nhàn rỗi trước khi bị thu hồi. |

Ví dụ cấu hình độc lập hai pool:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.ChannelRegistration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketTransportRegistration;

@Configuration
@EnableWebSocketMessageBroker
public class MessagingWebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");

        // Bảo toàn thứ tự message client gửi trong cùng một session.
        registry.setPreserveReceiveOrder(true);
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/topic", "/queue");

        // Bảo toàn thứ tự message gửi về cùng một client session.
        registry.setPreservePublishOrder(true);
    }

    @Override
    public void configureClientInboundChannel(ChannelRegistration registration) {
        registration.taskExecutor()
                .corePoolSize(8)
                .maxPoolSize(16)
                .queueCapacity(200)
                .keepAliveSeconds(60);
    }

    @Override
    public void configureClientOutboundChannel(ChannelRegistration registration) {
        registration.taskExecutor()
                .corePoolSize(8)
                .maxPoolSize(16)
                .queueCapacity(500)
                .keepAliveSeconds(60);
    }

    @Override
    public void configureWebSocketTransport(WebSocketTransportRegistration registration) {
        registration
                .setSendTimeLimit(15_000)
                .setSendBufferSizeLimit(512 * 1024);
    }
}
~~~

Các con số 8, 16, 200 và 500 chỉ là giá trị minh họa cho cách cấu hình, không phải khuyến nghị chung. Hãy đo tải thực tế, số CPU, thời gian xử lý, kích thước message và giới hạn database trước khi chọn giá trị production.

Nếu ứng dụng đã có một lớp `WebSocketMessageBrokerConfigurer`, hãy bổ sung các callback vào cấu hình hiện tại thay vì tạo nhiều cấu hình không cần thiết. Spring cho phép nhiều configurer phối hợp, nhưng việc chia cấu hình cần có chủ đích để tránh khó theo dõi.

## 4. Cách ThreadPoolExecutor sử dụng core, queue và max

Hiểu đúng thứ tự nhận task của `ThreadPoolExecutor` rất quan trọng:

1. Nếu số thread đang chạy nhỏ hơn `corePoolSize`, executor tạo thread mới để xử lý task.
2. Khi đã có đủ thread lõi, task mới được đưa vào queue nếu queue còn chỗ.
3. Khi queue đầy, executor mới tạo thêm thread vượt quá core size, cho tới `maxPoolSize`.
4. Nếu queue đầy và số thread đã đạt max, task bị từ chối theo rejection policy.

Ví dụ core=8, max=16 và queueCapacity=200:

- Tối đa 8 task đầu tiên có thể chạy đồng thời bằng thread lõi.
- Các task tiếp theo được xếp hàng, tối đa 200 task.
- Khi queue đầy, pool có thể tăng thêm thread từ 8 lên tới 16.
- Khi cả pool và queue đều đạt giới hạn, task mới không thể được nhận theo cấu hình hiện tại.

Một điểm dễ gây hiểu nhầm: nếu queue không giới hạn (mặc định của `TaskExecutorRegistration` là `Integer.MAX_VALUE`), task mới tiếp tục được xếp hàng sau khi core threads bận. Queue hầu như không đầy, vì vậy `maxPoolSize` không có tác dụng mở rộng pool. Queue không giới hạn cũng có thể giữ quá nhiều task và gây thiếu bộ nhớ khi tốc độ nhận lớn hơn tốc độ xử lý.

Queue có dung lượng hữu hạn giúp giới hạn lượng công việc chờ và cho phép pool mở rộng tới max size. Tuy nhiên, queue quá nhỏ có thể làm task bị từ chối trong các đợt tải ngắn. Cần đo throughput và thời gian chờ để chọn dung lượng hợp lý.

## 5. Chọn kích thước cho clientInboundChannel

`clientInboundChannel` xử lý message do client gửi vào. Ví dụ:

- SUBSCRIBE tới `/topic/**` hoặc `/user/**`.
- SEND tới `/app/**` và được định tuyến tới `MessageMapping`.
- Các interceptor kiểm tra authentication, authorization, header và dữ liệu.
- Các handler xử lý payload và gọi service nghiệp vụ.

Cách chọn pool phụ thuộc loại công việc:

### Công việc CPU-bound

Nếu handler chủ yếu parse dữ liệu, kiểm tra quy tắc, tính toán hoặc biến đổi payload, số thread nên gần với số CPU có thể sử dụng. Tăng thread quá nhiều không làm CPU thực hiện nhiều phép tính hơn; nó có thể làm tăng context switching.

### Công việc I/O-bound

Nếu handler phải chờ database, HTTP service hoặc hệ thống khác, có thể cần nhiều thread hơn số CPU để tận dụng thời gian chờ. Tuy nhiên, phải đối chiếu với connection pool và giới hạn của hệ thống phụ thuộc. Ví dụ, mở 100 inbound threads trong khi database chỉ cho 10 connection có thể tạo hàng đợi chờ database thay vì tăng throughput.

Với tác vụ dài như xử lý báo cáo, gọi dịch vụ chậm hoặc chạy workflow, nên cân nhắc đưa phần công việc đó sang executor hoặc hàng đợi nghiệp vụ riêng. Không để một handler giữ thread của inbound channel quá lâu nếu message khác cần được xử lý nhanh.

Các handler trong controller thường được gọi đồng thời trên nhiều thread. Controller singleton không nên giữ state mutable dùng chung nếu chưa có đồng bộ phù hợp. Dùng service thread-safe, transaction boundary rõ ràng và không giả định mọi message của một user sẽ tự động chạy tuần tự.

## 6. Chọn kích thước cho clientOutboundChannel

`clientOutboundChannel` xử lý message gửi về WebSocket client, bao gồm message từ broker và một số message trực tiếp từ ứng dụng.

Tải outbound chịu ảnh hưởng của:

- Số lượng client đang kết nối.
- Số lượng destination mà mỗi client subscribe.
- Tần suất publish của broker.
- Kích thước payload.
- Băng thông và tốc độ xử lý JavaScript của từng client.
- Số client dùng mạng di động hoặc kết nối có độ trễ cao.

Nếu client ở mạng nhanh và tiêu thụ message kịp thời, pool có thể gần số CPU. Nếu có nhiều client chậm hoặc băng thông thấp, outbound tasks có thể chờ lâu hơn; pool lớn hơn có thể giúp các session khác tiếp tục được phục vụ.

Tuy nhiên, Spring chỉ sử dụng một thread tại một thời điểm để ghi message lên một client session. Các message khác của session đó được buffer. Vì vậy, tăng outbound pool không khiến một WebSocket chậm nhận nhiều message đồng thời. Cần kết hợp giới hạn thời gian gửi, giới hạn buffer, kiểm soát tần suất publish và chính sách ngắt client không theo kịp.

## 7. Giới hạn gửi cho client chậm

Cấu hình executor outbound không thay thế cấu hình transport. `configureWebSocketTransport` cung cấp hai giới hạn hữu ích:

- `setSendTimeLimit(milliseconds)` giới hạn thời gian gửi message tới client.
- `setSendBufferSizeLimit(bytes)` giới hạn lượng dữ liệu được buffer khi gửi cho một client.

Ví dụ:

~~~java
@Override
public void configureWebSocketTransport(WebSocketTransportRegistration registration) {
    registration
            .setSendTimeLimit(15 * 1000)
            .setSendBufferSizeLimit(512 * 1024);
}
~~~

Đây là các giá trị minh họa. Khi client không đọc kịp, dữ liệu outbound có thể tích tụ. Khi vượt giới hạn send time hoặc buffer, Spring có thể đóng session để bảo vệ tài nguyên server.

Không nên tăng buffer vô hạn để che giấu client chậm. Điều đó có thể giữ lượng message lớn trong bộ nhớ, làm dữ liệu cũ tiếp tục được gửi sau khi không còn hữu ích. Với dữ liệu có thể lấy lại, đôi khi tốt hơn là ngắt session chậm và để client kết nối lại rồi đồng bộ snapshot.

## 8. Bảo toàn thứ tự message

Vì inbound và outbound đều dùng thread pool, thứ tự xử lý không mặc nhiên giống thứ tự nhận hoặc publish ban đầu.

Spring cung cấp hai tùy chọn riêng:

### Thứ tự nhận từ client

`StompEndpointRegistry.setPreserveReceiveOrder(true)` yêu cầu Spring chuyển các message của cùng một session vào `clientInboundChannel` lần lượt theo thứ tự nhận.

Điều này hữu ích khi client gửi các lệnh phụ thuộc nhau, ví dụ cập nhật trạng thái rồi gửi thao tác tiếp theo dựa trên trạng thái mới. Tùy chọn này được bổ sung từ Spring Framework 6.1.

### Thứ tự gửi về client

`MessageBrokerRegistry.setPreservePublishOrder(true)` yêu cầu Spring gửi các message tới cùng một client session qua `clientOutboundChannel` lần lượt theo thứ tự publish.

Tùy chọn này hữu ích khi client cần nhận chuỗi sự kiện theo đúng thứ tự. Nó có thêm chi phí hiệu năng, vì vậy chỉ bật khi nghiệp vụ cần.

Hai tùy chọn chỉ bảo đảm thứ tự trong phạm vi cùng client session. Chúng không tạo ra thứ tự toàn cục giữa nhiều user, nhiều session, nhiều broker hoặc nhiều producer. Nếu thứ tự nghiệp vụ quan trọng, vẫn nên mang `sequence` hoặc `version` trong payload và kiểm tra ở phía consumer.

## 9. Thread safety và ranh giới xử lý

Do executor có thể chạy nhiều message song song:

- Controller mặc định là singleton; không lưu trạng thái của từng client trong field mutable không được bảo vệ.
- Các collection chia sẻ giữa nhiều handler cần dùng cấu trúc thread-safe hoặc cơ chế khóa phù hợp.
- Không giả định hai message của cùng session luôn chạy tuần tự nếu chưa bật preserve receive order.
- Không giữ transaction hoặc thread-local context qua một ranh giới executor khác như thể vẫn ở cùng thread.
- Không thực hiện công việc blocking lâu trong handler nếu có thể đưa sang service hoặc worker chuyên trách.
- Không dùng chung một executor nhỏ cho cả inbound và outbound nếu hai luồng có đặc tính tải khác nhau và việc đó khiến một phía chiếm hết thread.

Nếu cần giới hạn số thao tác đồng thời theo user hoặc theo tài nguyên, áp dụng semaphore, rate limiter hoặc cơ chế giới hạn ở tầng nghiệp vụ. Thread pool chỉ kiểm soát số task đang chạy và chờ trong channel; nó không tự hiểu quota của một tài khoản.

## 10. Theo dõi executor và channel

Khi dùng `EnableWebSocketMessageBroker`, Spring cung cấp bean `WebSocketMessageBrokerStats` để tổng hợp số liệu hạ tầng. Theo tài liệu Spring Framework 6.2, bean này mặc định ghi log thống kê ở mức INFO mỗi 30 phút và có thể export qua JMX.

Các số liệu cần quan sát:

| Chỉ số | Dấu hiệu cần chú ý |
|---|---|
| Inbound pool active threads | Pool thường xuyên bận hết thread có thể đang thiếu năng lực xử lý. |
| Inbound queue size | Queue tăng liên tục cho thấy handler hoặc dependency xử lý chậm hơn tốc độ nhận message. |
| Outbound pool active threads | Pool bận kéo dài có thể do số lượng lớn message cần gửi. |
| Outbound queue size | Queue tăng có thể cho thấy client chậm tiêu thụ hoặc lượng broadcast quá cao. |
| WebSocket sessions | So sánh số session hiện tại với số client dự kiến. |
| Send limit exceeded | Có client vượt send timeout hoặc send buffer limit. |
| Transport errors | Có lỗi đọc/ghi WebSocket hoặc HTTP transport. |
| STOMP frames | So sánh CONNECT, CONNECTED, DISCONNECT để phát hiện session đóng bất thường. |

Không chỉ xem một ảnh chụp số liệu. Theo dõi xu hướng queue size, active count, task completion, latency và rejection trong thời gian tải bình thường lẫn cao điểm. Nếu queue chỉ tăng mà không giảm, tăng max pool có thể không giải quyết được bottleneck; cần xem handler, database, broker hoặc client.

## 11. Quy trình tuning thực tế

Một quy trình có thể lặp lại:

1. **Đo baseline**: ghi nhận số client, message/giây, kích thước payload, CPU, heap, latency và queue size.
2. **Tách inbound và outbound**: xác định backlog xuất hiện ở channel nào.
3. **Tìm bottleneck**: inbound thường liên quan tới handler hoặc I/O; outbound thường liên quan tới client chậm, broker fan-out hoặc payload lớn.
4. **Chọn core size**: dựa vào CPU và tỷ lệ thời gian chờ I/O.
5. **Chọn max size và queue capacity**: queue hữu hạn để kiểm soát bộ nhớ; max size để hấp thụ đợt tải ngắn.
6. **Kiểm tra dependency limits**: database connection pool, HTTP connection pool, broker connection và CPU.
7. **Load test**: tăng dần số client và tốc độ message, theo dõi latency p95/p99, queue, memory và lỗi.
8. **Điều chỉnh từng biến**: thay đổi core, max, queue hoặc send limits riêng lẻ để thấy tác động.
9. **Kiểm tra quá tải**: xác nhận hệ thống từ chối hoặc ngắt có kiểm soát thay vì giữ queue tăng vô hạn.
10. **Ghi lại cấu hình**: lưu thông số đã thử, workload, giới hạn hạ tầng và lý do chọn giá trị cuối.

Không có một cấu hình executor tối ưu cho mọi ứng dụng. Pool cần được kiểm tra lại khi thay đổi CPU quota của container, số client, broker, payload hoặc thời gian xử lý handler.

## 12. Lỗi thường gặp

- **Tăng maxPoolSize nhưng queue vẫn không giới hạn:** queue nhận task trước khi pool mở rộng; max có thể không bao giờ được dùng. Đặt queue capacity hữu hạn nếu cần scale beyond core.
- **Dùng cùng một pool cho inbound và outbound:** một luồng tải cao có thể làm nghẽn luồng còn lại. Cấu hình riêng để quan sát và điều chỉnh độc lập.
- **Đặt core/max quá lớn:** thread tranh chấp CPU, heap và connection pool. Bắt đầu từ workload đo được rồi tăng từng bước.
- **Queue quá lớn:** latency tăng và task cũ có thể vẫn được xử lý khi đã hết giá trị. Đặt giới hạn theo thời gian chờ và dung lượng bộ nhớ chấp nhận được.
- **Chỉ tăng outbound threads khi client chậm:** một session vẫn được ghi tuần tự; cần kiểm tra sendTimeLimit, sendBufferSizeLimit và tốc độ client.
- **Bỏ qua thứ tự message:** xử lý song song có thể làm đảo thứ tự. Bật preserveReceiveOrder hoặc preservePublishOrder nếu cần và đo overhead.
- **Dùng state mutable trong singleton controller:** nhiều message chạy đồng thời có thể gây race condition. Dùng state store hoặc dữ liệu thread-safe.
- **Đánh giá hệ thống chỉ bằng CPU:** queue có thể tăng do database chậm, broker chậm hoặc client không đọc kịp dù CPU chưa cao.

## 13. Checklist trước khi đưa vào production

- [ ] Đã hiểu rõ luồng inbound, outbound và brokerChannel.
- [ ] Đã cấu hình riêng executor cho clientInboundChannel và clientOutboundChannel.
- [ ] Đã đặt corePoolSize, maxPoolSize và queueCapacity dựa trên load test.
- [ ] Đã xác nhận queue không giới hạn không làm maxPoolSize bị vô hiệu hóa ngoài dự kiến.
- [ ] Đã kiểm tra database và HTTP connection pool tương ứng với số inbound threads.
- [ ] Đã cấu hình sendTimeLimit và sendBufferSizeLimit cho client chậm.
- [ ] Đã bật preserveReceiveOrder/preservePublishOrder nếu yêu cầu nghiệp vụ cần thứ tự.
- [ ] Controller và handler thread-safe khi chạy đồng thời.
- [ ] Đã theo dõi WebSocketMessageBrokerStats và queue backlog.
- [ ] Đã load test cả tải bình thường, burst và quá tải.
- [ ] Đã xác định hành vi khi queue đầy hoặc task bị từ chối.

## 14. Ghi nhớ

`clientInboundChannel` xử lý message đi từ client vào Spring; `clientOutboundChannel` xử lý message từ broker/ứng dụng đi về client. Cấu hình hai executor độc lập bằng `configureClientInboundChannel` và `configureClientOutboundChannel`. Khi tuning, phải hiểu tương tác giữa corePoolSize, maxPoolSize và queueCapacity: queue không giới hạn có thể khiến maxPoolSize không được dùng. Inbound cần phù hợp với workload controller và dependency I/O; outbound cần tính đến client chậm cùng sendTimeLimit/sendBufferSizeLimit. Bảo toàn thứ tự bằng preserveReceiveOrder hoặc preservePublishOrder khi nghiệp vụ cần, rồi xác nhận bằng metrics và load test.

## Tài liệu tham khảo

- [Spring Framework 6.2 — Performance](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/configuration-performance.html)
- [Spring Framework 6.2 — Monitoring](https://docs.spring.io/spring/reference/6.2/web/websocket/stomp/stats.html)
- [Spring Framework 6.2 — Order of Messages](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/ordered-messages.html)
- [TaskExecutorRegistration API 6.2](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/messaging/simp/config/TaskExecutorRegistration.html)
- [WebSocketMessageBrokerConfigurer API 6.2](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/web/socket/config/annotation/WebSocketMessageBrokerConfigurer.html)