# setPreservePublishOrder và thứ tự gửi trong một phiên

## Mục tiêu

Trong Spring WebSocket/STOMP, một message có thể được phát đi trước một message khác nhưng client lại nhận chúng theo thứ tự khác. Nguyên nhân phổ biến là các message trên channel được xử lý bởi nhiều thread. Spring cung cấp tùy chọn **setPreservePublishOrder(true)** để giữ thứ tự gửi đến từng WebSocket session.

Bài này giải thích phạm vi bảo đảm của tùy chọn, cách cấu hình, mối quan hệ với thứ tự xử lý message từ client, chi phí hiệu năng và cách kiểm thử. Sau bài học, bạn có thể quyết định khi nào cần bật thứ tự gửi và tránh hiểu nhầm nó thành một cơ chế sắp xếp toàn hệ thống.

## 1. Vì sao thứ tự gửi có thể bị đảo?

Trong cấu hình STOMP phổ biến, message từ broker được chuyển đến **clientOutboundChannel** trước khi được ghi lên WebSocket session. Channel này thường được hỗ trợ bởi ThreadPoolExecutor. Nhiều message có thể được giao cho các worker thread khác nhau và hoàn tất xử lý theo thứ tự khác với thứ tự chúng được đưa vào channel.

Giả sử ứng dụng phát ba sự kiện theo thứ tự:

~~~text
publish(event-1)
publish(event-2)
publish(event-3)
~~~

Nếu việc xử lý outbound chạy song song, một session có thể quan sát kết quả như sau:

~~~text
publish order:  event-1 -> event-2 -> event-3
receive order:  event-2 -> event-1 -> event-3
~~~

Đây là vấn đề đáng chú ý khi client cập nhật giao diện hoặc trạng thái theo chuỗi sự kiện. Ví dụ:

- Một đơn hàng chuyển lần lượt từ CREATED sang PAID rồi SHIPPED.
- Một tiến trình phát các thay đổi tiến độ 10%, 40%, 80%, 100%.
- Một phiên chỉnh sửa cộng tác nhận các thao tác thay đổi tài liệu.
- Một bảng điều khiển nhận các sự kiện trạng thái cần được áp dụng theo thứ tự.

Nếu client nhận SHIPPED trước PAID, logic phía giao diện có thể hiển thị trạng thái cũ sau trạng thái mới hoặc áp dụng phép biến đổi sai.

Thứ tự của frame WebSocket trên một kết nối không tự giải quyết vấn đề này. Vấn đề xảy ra trước khi các message được ghi ra kết nối: các worker thread có thể hoàn tất việc xử lý message theo thứ tự khác nhau.

## 2. setPreservePublishOrder(true) làm gì?

**MessageBrokerRegistry.setPreservePublishOrder(true)** yêu cầu Spring gửi message đến clientOutboundChannel lần lượt theo thứ tự publish đối với từng client session.

Khi bật cờ này, Spring sử dụng cơ chế OrderedMessageChannelDecorator để điều phối việc gửi message. Các message dành cho cùng một session được chuyển đến outbound channel từng message một, giữ thứ tự publish mà broker đưa ra.

Phạm vi bảo đảm cần nhớ:

- Thứ tự được giữ **trong cùng một client session**.
- Mỗi session được xử lý theo chuỗi gửi riêng.
- Không tạo ra một thứ tự tổng thể giữa mọi client hoặc mọi session.
- Không tự xác định thứ tự nghiệp vụ cho các sự kiện được phát đồng thời từ nhiều thread.
- Có chi phí hiệu năng do giảm mức độ xử lý song song trên đường gửi đến một session.

Tùy chọn này không thay thế việc thiết kế thứ tự sự kiện ở tầng nghiệp vụ. Nó giữ thứ tự tại ranh giới publish-to-client của Spring; ứng dụng vẫn cần xác định sự kiện nào phải đứng trước sự kiện nào.

## 3. Cấu hình Java

Cấu hình được thực hiện trong phương thức configureMessageBroker của WebSocketMessageBrokerConfigurer:

~~~java
package com.example.messaging;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

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

        // Giữ thứ tự publish đến từng client session.
        registry.setPreservePublishOrder(true);
    }
}
~~~

Dòng quan trọng là:

~~~java
registry.setPreservePublishOrder(true);
~~~

Mặc định, tùy chọn này là false. Khi không bật, Spring có thể xử lý message outbound song song và thứ tự client nhận không nhất thiết trùng với thứ tự publish.

Có thể bật cờ cùng với simple broker hoặc broker relay trong cấu hình message broker. Việc chọn simple broker hay broker bên ngoài không làm thay đổi ý nghĩa cốt lõi của cờ tại tầng Spring outbound. Tuy nhiên, broker bên ngoài có thêm quy tắc phân phối và thứ tự riêng; cần đánh giá cả hai tầng khi dùng relay.

## 4. Cấu hình XML

Nếu ứng dụng dùng XML namespace thay vì Java configuration, có thể bật cùng tùy chọn bằng thuộc tính preserve-publish-order:

~~~xml
<websocket:message-broker
        application-destination-prefix="/app"
        preserve-publish-order="true">

    <websocket:stomp-endpoint path="/ws"/>

    <websocket:simple-broker prefix="/topic,/queue"/>
</websocket:message-broker>
~~~

Tên thuộc tính XML tương ứng với phương thức Java là preserve-publish-order. Không cấu hình cả hai kiểu chỉ để bật cùng một hành vi; chọn cách cấu hình phù hợp với phong cách của ứng dụng.

## 5. Một ví dụ về chuỗi sự kiện trong cùng session

Giả sử một ứng dụng theo dõi tiến trình xử lý đơn hàng. Service phát ba cập nhật đến topic của người dùng:

~~~java
@Service
public class OrderProgressPublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public OrderProgressPublisher(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publishProgress(String orderId) {
        messagingTemplate.convertAndSend(
                "/topic/orders/" + orderId,
                new ProgressEvent(orderId, 10, "STARTED")
        );

        messagingTemplate.convertAndSend(
                "/topic/orders/" + orderId,
                new ProgressEvent(orderId, 60, "PROCESSING")
        );

        messagingTemplate.convertAndSend(
                "/topic/orders/" + orderId,
                new ProgressEvent(orderId, 100, "COMPLETED")
        );
    }
}
~~~

DTO minh họa:

~~~java
public record ProgressEvent(
        String orderId,
        int percent,
        String status
) {
}
~~~

Client đăng ký nhận sự kiện:

~~~javascript
client.onConnect = () => {
  client.subscribe("/topic/orders/42", (frame) => {
    const event = JSON.parse(frame.body);
    renderProgress(event.percent, event.status);
  });
};
~~~

Với setPreservePublishOrder(true), các message được publish đến cùng session sẽ được gửi lần lượt theo thứ tự publish. Nếu một client có nhiều subscription, thứ tự outbound của các message dành cho session đó cũng được điều phối theo cùng nguyên tắc.

Ví dụ này giả định các lần publish được thực hiện theo trình tự xác định trong cùng luồng xử lý. Nếu nhiều thread đồng thời phát sự kiện cho cùng đơn hàng, trước hết ứng dụng phải xác định thứ tự nghiệp vụ giữa các thread.

## 6. Bảo đảm theo session, không phải thứ tự toàn cục

Đây là giới hạn quan trọng nhất của API.

Giả sử hai client A và B cùng subscribe /topic/orders. Spring giữ thứ tự gửi riêng cho A và riêng cho B. Điều đó không có nghĩa:

- Message đầu tiên chắc chắn đến A trước B.
- Tất cả session đều xử lý message cùng một thời điểm.
- Thứ tự giữa hai destination độc lập được đồng bộ trên toàn hệ thống.
- Một message phát sau từ thread khác sẽ luôn được xem là sự kiện nghiệp vụ mới hơn.

Ví dụ, nếu A và B cùng nhận E1 và E2, Spring bảo toàn thứ tự publish cho mỗi session. Nhưng độ trễ mạng, tốc độ xử lý JavaScript và thời điểm callback của A/B có thể khác nhau.

Nếu cần thứ tự toàn cục hoặc một thứ tự nghiệp vụ nhất quán giữa nhiều instance, cần một cơ chế tạo thứ tự ở tầng ứng dụng hoặc broker. Có thể dùng sequence number, partition key, một luồng xử lý tuần tự theo aggregate hoặc một log sự kiện có thứ tự.

Không dùng setPreservePublishOrder như một khóa phân tán. Nó không đồng bộ transaction, database commit hoặc các publisher độc lập.

## 7. Publisher đồng thời và thứ tự nghiệp vụ

Một tình huống tinh tế xuất hiện khi nhiều thread cùng gọi SimpMessagingTemplate.

~~~java
executor.submit(() -> publish("PAID"));
executor.submit(() -> publish("SHIPPED"));
~~~

Nếu hai tác vụ chạy song song, không thể suy ra thứ tự nghiệp vụ chỉ từ thứ tự hai dòng submit. Thread pool có thể thực thi hoặc gọi broker theo một thứ tự khác. setPreservePublishOrder chỉ giữ thứ tự message khi chúng được đưa qua đường publish đến session; nó không quyết định tác vụ nào phải thắng khi hai publisher cạnh tranh.

Nếu yêu cầu nghiệp vụ nói rằng PAID phải luôn đứng trước SHIPPED, hãy tạo thứ tự trước khi gửi:

- Phát sự kiện từ một luồng tuần tự theo orderId.
- Dùng hàng đợi hoặc executor riêng cho từng aggregate.
- Gán sequence number tăng dần tại nơi quyết định trạng thái.
- Chỉ publish sau khi chuyển trạng thái hợp lệ đã được commit.
- Cho client phát hiện khoảng trống hoặc message đến sai thứ tự bằng sequence number.

Ví dụ DTO có sequence:

~~~java
public record OrderEvent(
        String orderId,
        long sequence,
        String eventType
) {
}
~~~

Client có thể bỏ qua event cũ hoặc tạm giữ event đến trước khi event có sequence liền trước được áp dụng. Cách này giải quyết vấn đề thứ tự ở tầng nghiệp vụ và hữu ích cả khi message đi qua nhiều service hoặc broker.

## 8. Thứ tự message từ client là cấu hình riêng

setPreservePublishOrder điều khiển message đi từ broker ra client qua **clientOutboundChannel**. Nó không điều khiển thứ tự message client gửi vào server.

Luồng inbound đi qua **clientInboundChannel**. Channel này cũng có thể được hỗ trợ bởi ThreadPoolExecutor, nên các message nhận từ cùng một session có thể được xử lý trên các thread khác nhau.

Từ Spring Framework 6.1, có tùy chọn riêng:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws");

    // Giữ thứ tự xử lý các message nhận từ cùng một session.
    registry.setPreserveReceiveOrder(true);
}
~~~

Hai cờ có phạm vi khác nhau:

| Cấu hình | Hướng message | Mục đích |
| --- | --- | --- |
| MessageBrokerRegistry.setPreservePublishOrder(true) | Server → client | Giữ thứ tự publish outbound trong từng session |
| StompEndpointRegistry.setPreserveReceiveOrder(true) | Client → server | Giữ thứ tự xử lý inbound trong từng session |

Nếu nghiệp vụ cần cả hai chiều, có thể bật cả hai. Tuy nhiên, mỗi cờ có chi phí xử lý riêng. Không bật chỉ vì muốn mọi message “an toàn hơn”; hãy xác định chiều nào thực sự cần tuần tự.

## 9. Thứ tự trong callback phía trình duyệt

setPreservePublishOrder kiểm soát thứ tự Spring phát message ra session. Nó không tự tuần tự hóa công việc bất đồng bộ mà callback JavaScript khởi chạy.

Ví dụ:

~~~javascript
client.subscribe("/topic/orders", async (frame) => {
  const event = JSON.parse(frame.body);
  await saveToIndexedDb(event);
  render(event);
});
~~~

Nếu thư viện gọi callback cho E1 rồi E2, nhưng saveToIndexedDb của E2 hoàn tất trước E1, giao diện vẫn có thể render E2 trước E1. Đây là thứ tự hoàn tất tác vụ ở client, khác với thứ tự frame đến.

Nếu client cần áp dụng tuần tự, có thể dùng một promise chain:

~~~javascript
let processing = Promise.resolve();

client.subscribe("/topic/orders", (frame) => {
  const event = JSON.parse(frame.body);

  processing = processing.then(() => processEvent(event)).catch((error) => {
    reportProcessingError(error);
  });
});
~~~

Cách này xếp các tác vụ xử lý theo thứ tự callback gọi. Cần xử lý lỗi trong chain để một lỗi không làm chuỗi promise bị reject vĩnh viễn và chặn mọi message sau đó.

Với luồng dữ liệu có thể đến trùng hoặc trễ, sequence number vẫn là cơ chế kiểm tra đáng tin cậy hơn việc chỉ dựa vào thời điểm callback.

## 10. Chi phí hiệu năng và khi nào nên bật

Khi setPreservePublishOrder bật, Spring gửi message đến mỗi session lần lượt từng message một. Điều này làm giảm khả năng xử lý song song outbound cho cùng session và tạo thêm chi phí điều phối.

Tác động thực tế phụ thuộc vào:

- Số lượng message mỗi giây trên một session.
- Kích thước payload và thời gian ghi WebSocket.
- Số lượng session đang kết nối.
- Số thread và cấu hình channel executor.
- Client có đọc message chậm hoặc thường xuyên nghẽn hay không.
- Message có cần giữ thứ tự tuyệt đối hay có thể sắp xếp ở client.

Nên cân nhắc bật khi:

- Các message là các bước liên tiếp của một trạng thái.
- Client áp dụng patch hoặc delta cần đúng thứ tự.
- Thông điệp sau phụ thuộc vào kết quả của thông điệp trước.
- Việc đảo thứ tự tạo ra trạng thái không hợp lệ và client không có sequence/reordering logic.

Có thể không cần bật khi:

- Message độc lập, ví dụ số liệu telemetry không phụ thuộc nhau.
- Client luôn lấy snapshot mới nhất và bỏ qua cập nhật cũ.
- Tầng nghiệp vụ đã có sequence number và client tự sắp xếp.
- Throughput quan trọng hơn thứ tự xử lý trên từng session.

Đừng dự đoán overhead chỉ từ số lượng session. Hãy benchmark bằng tải đại diện và đo throughput, latency p95/p99, độ dài hàng đợi, CPU, bộ nhớ và số lần client bị chậm. Bật cờ chỉ cho những luồng ứng dụng có yêu cầu thứ tự thực sự khi kiến trúc cho phép cấu hình tách biệt.

## 11. Kiểm thử thứ tự publish

Một integration test hữu ích cần kiểm tra thứ tự message thực tế nhận được từ một session, thay vì chỉ kiểm tra cấu hình có giá trị true.

Quy trình:

1. Khởi động ứng dụng với STOMP endpoint và setPreservePublishOrder(true).
2. Kết nối một client và subscribe một destination.
3. Publish các sự kiện có sequence 1, 2, 3, ... theo một luồng xác định.
4. Thu thập message ở client cho đến khi nhận đủ số lượng.
5. So sánh sequence nhận được với thứ tự mong đợi.
6. Lặp lại với nhiều message và tải cao hơn để tăng khả năng phát hiện race condition.
7. Kết nối client thứ hai và xác minh mỗi session nhận được chuỗi đúng, nhưng không kiểm tra thứ tự tương đối giữa hai client.

Để chứng minh tác dụng của cờ, có thể chạy cùng kịch bản với cấu hình false và true. Tuy nhiên, test với cờ false không nhất thiết luôn tái hiện đảo thứ tự; race condition phụ thuộc lịch thread và tải. Một test không thấy đảo thứ tự không chứng minh rằng mặc định đã đảm bảo thứ tự.

Nên có test riêng cho inbound nếu ứng dụng bật setPreserveReceiveOrder(true): gửi nhiều message theo thứ tự từ cùng client session và kiểm tra thứ tự các handler xử lý. Không dùng test inbound để kết luận về outbound hoặc ngược lại.

## 12. Những hiểu nhầm thường gặp

| Hiểu nhầm | Thực tế |
| --- | --- |
| Bật cờ sẽ giữ thứ tự giữa mọi client | Cờ giữ thứ tự riêng trong từng session, không tạo đồng hồ hay thứ tự toàn cục. |
| Cờ này sắp xếp các sự kiện theo thời gian nghiệp vụ | Cờ giữ thứ tự publish ở đường outbound; ứng dụng phải xác định thứ tự nghiệp vụ trước đó. |
| Nó cũng giữ thứ tự message client gửi lên server | Inbound có cờ riêng setPreserveReceiveOrder. |
| Callback JavaScript bất đồng bộ sẽ hoàn tất đúng thứ tự | Cờ không chờ các Promise do callback tạo ra; client cần tuần tự hóa xử lý nếu cần. |
| Bật cờ không ảnh hưởng hiệu năng | Việc gửi lần lượt làm giảm xử lý song song trên mỗi session và có overhead. |
| Chỉ cần cờ này để có exactly-once delivery | Cờ không cung cấp lưu trữ bền vững, ACK, retry nghiệp vụ hay exactly-once. |
| Nó sửa được race condition giữa các publisher | Nó không quyết định thứ tự nghiệp vụ giữa các tác vụ chạy đồng thời. |

## 13. Ghi nhớ

- Mặc định, clientOutboundChannel có thể xử lý message trên nhiều thread và client có thể nhận khác thứ tự publish.
- setPreservePublishOrder(true) giữ thứ tự outbound trong từng client session bằng cách gửi từng message một.
- Cờ không tạo thứ tự toàn cục giữa session và không giải quyết thứ tự nghiệp vụ giữa các publisher đồng thời.
- setPreserveReceiveOrder(true) là cờ inbound riêng, có từ Spring Framework 6.1.
- Callback bất đồng bộ phía client có thể hoàn tất sai thứ tự dù frame đã đến đúng thứ tự.
- Bảo toàn thứ tự có chi phí; cần benchmark và chỉ bật khi yêu cầu nghiệp vụ cần.
- Sequence number và xử lý tuần tự theo aggregate giúp bảo vệ thứ tự ở tầng nghiệp vụ, kể cả khi message đi qua nhiều hệ thống.

## Tài liệu tham khảo

- [Spring Framework — Order of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/ordered-messages.html)
- [MessageBrokerRegistry Javadoc — setPreservePublishOrder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/config/MessageBrokerRegistry.html)
- [StompEndpointRegistry Javadoc — setPreserveReceiveOrder](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/config/annotation/StompEndpointRegistry.html)
- [Spring Framework — Message Flow](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [OrderedMessageChannelDecorator Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/broker/OrderedMessageChannelDecorator.html)

