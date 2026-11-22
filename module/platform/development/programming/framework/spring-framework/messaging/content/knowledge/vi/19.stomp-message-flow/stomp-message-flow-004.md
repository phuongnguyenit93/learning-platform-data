# clientInboundChannel, brokerChannel và clientOutboundChannel

Trong Spring Framework, khi bật STOMP over WebSocket bằng **@EnableWebSocketMessageBroker**, Spring tạo một luồng message nội bộ gồm ba channel chính: **clientInboundChannel**, **brokerChannel** và **clientOutboundChannel**. Mỗi channel nối một nhóm thành phần trong ứng dụng, giúp tách việc nhận message từ client, xử lý ở phía server và phát message trở lại client.

Ba channel này là các **Spring MessageChannel** trong bộ xử lý phía server. Chúng không phải ba STOMP destination như /app, /topic hoặc /queue. Destination quyết định message được định tuyến đến handler nào; channel là đường chuyển message giữa các thành phần Spring.

## 1. Vai trò của ba channel

| Channel | Hướng luồng | Vai trò chính |
|---|---|---|
| **clientInboundChannel** | WebSocket client → Spring | Nhận các STOMP frame đã được giải mã thành Spring Message để phân tuyến đến controller hoặc broker. |
| **brokerChannel** | Ứng dụng Spring → message broker | Chuyển message do code phía server phát ra đến broker để tìm subscriber phù hợp. |
| **clientOutboundChannel** | Broker/ứng dụng → WebSocket client | Chuyển message gửi đến client để Spring mã hóa thành STOMP frame và ghi lên WebSocket session. |

Có thể hình dung:

~~~text
                 CLIENT
                   |
             STOMP over WS
                   |
                   v
        +-----------------------+
        |  clientInboundChannel |
        +-----------------------+
                   |
          +--------+---------+
          |                  |
       /app/...          /topic/...,
          |               /queue/...
          v                  |
  @MessageMapping            |
          |                  |
   handler return            |
          |                  |
          v                  |
    +---------------+        |
    | brokerChannel |<-------+
    +---------------+
          |
          v
    Message Broker
          |
          v
  +------------------------+
  | clientOutboundChannel  |
  +------------------------+
          |
          v
     STOMP over WS
          |
          v
        CLIENT
~~~

Trong sơ đồ, đường /topic hoặc /queue từ inbound được broker handler xử lý trực tiếp để đăng ký subscription hoặc nhận SEND. Message do controller hoặc service phía server phát ra đi qua brokerChannel.

## 2. clientInboundChannel: đường vào từ client

Khi client gửi frame STOMP qua WebSocket, Spring giải mã frame và tạo một **org.springframework.messaging.Message<?>** gồm payload cùng headers. Message đó được gửi vào clientInboundChannel.

Các frame thường đi qua channel này gồm:

- **CONNECT / STOMP:** bắt đầu STOMP session.
- **SUBSCRIBE:** đăng ký nhận message tại destination.
- **UNSUBSCRIBE:** hủy subscription.
- **SEND:** gửi payload lên server hoặc broker.
- **ACK / NACK:** xác nhận hoặc từ chối message trong subscription dùng explicit acknowledgment.
- **DISCONNECT:** kết thúc STOMP session.

Sau khi vào channel, message được các handler đăng ký nhận xử lý. Spring dựa trên destination prefix và STOMP command để chọn nhánh:

- Destination bắt đầu bằng **/app** thường được chuyển đến các method **@MessageMapping**.
- Destination bắt đầu bằng **/topic** hoặc **/queue** có thể được chuyển trực tiếp đến message broker.
- Các command quản lý connection/subscription được xử lý bởi broker handler và các thành phần STOMP tương ứng.

### Luồng SEND đến controller

Giả sử server cấu hình application prefix là /app:

~~~text
Client SEND
destination:/app/chat

{"text":"Xin chào"}
       |
       v
clientInboundChannel
       |
       | bỏ prefix /app để tìm mapping
       v
@MessageMapping("/chat")
       |
       v
ChatController.handle(...)
~~~

Prefix /app giúp phân biệt message gửi vào logic ứng dụng với message gửi trực tiếp đến broker. Prefix này không phải một channel riêng.

### Luồng SUBSCRIBE đến broker

Khi client gửi:

~~~text
SUBSCRIBE
id:chat-sub
destination:/topic/chat

^@
~~~

Spring chuyển frame vào clientInboundChannel. Broker handler nhận biết destination /topic/chat và đăng ký subscription cho session tương ứng. Khi có message được publish đến destination, broker tìm các subscriber phù hợp rồi phát message ra clientOutboundChannel.

### Những việc phù hợp với inbound channel

- Xác thực STOMP CONNECT nếu ứng dụng dùng token ở tầng STOMP.
- Kiểm tra quyền SEND hoặc SUBSCRIBE theo user và destination.
- Kiểm tra command, header và giới hạn payload.
- Gắn correlation ID hoặc metadata phục vụ tracing.
- Thu thập metric về số lượng message client gửi lên.
- Chặn message không hợp lệ trước khi tới controller hoặc broker.

Không nên đặt truy vấn database dài hoặc gọi HTTP chậm trong interceptor đồng bộ của inbound channel. Việc đó giữ worker thread và có thể làm hàng đợi inbound tăng nhanh.

## 3. brokerChannel: đường từ code server đến broker

**brokerChannel** chuyển các message được tạo bên trong ứng dụng Spring đến message broker. Đây là đường mà controller, service hoặc thành phần khác dùng khi muốn phát message cho subscriber.

Hai nguồn phổ biến:

1. Giá trị trả về từ method **@MessageMapping** được Spring chuyển thành message rồi gửi đến brokerChannel.
2. Ứng dụng gọi **SimpMessagingTemplate.convertAndSend(...)** hoặc **send(...)** để publish từ bất kỳ bean nào.

### Controller trả về message

~~~java
@Controller
public class ChatController {

    @MessageMapping("/chat")
    @SendTo("/topic/chat")
    public ChatMessage handle(ChatMessage message) {
        return message;
    }
}
~~~

Client gửi đến /app/chat. Spring gọi method handle, lấy giá trị trả về và gửi message đến /topic/chat qua brokerChannel. Broker tìm subscriber đang lắng nghe /topic/chat rồi phát đến từng client qua clientOutboundChannel.

### Publish từ service bằng SimpMessagingTemplate

~~~java
@Component
public class NotificationPublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public NotificationPublisher(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publishSystemNotice(String text) {
        messagingTemplate.convertAndSend(
                "/topic/notifications",
                new Notice(text)
        );
    }

    public record Notice(String text) {
    }
}
~~~

SimpMessagingTemplate gửi message đến brokerChannel. Vì vậy, service có thể phát notification sau một thao tác HTTP, một scheduled task hoặc một sự kiện nghiệp vụ mà không cần gọi trực tiếp WebSocketSession của từng client.

### Cấu hình brokerChannel

Trong Java configuration, **MessageBrokerRegistry.configureBrokerChannel()** trả về ChannelRegistration để tùy chỉnh channel này:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");

    registry.configureBrokerChannel()
            .taskExecutor()
            .corePoolSize(2)
            .maxPoolSize(4)
            .queueCapacity(500);
}
~~~

Có thể đăng ký ChannelInterceptor trên brokerChannel để quan sát hoặc áp dụng chính sách cho message do ứng dụng publish. Khi cấu hình executor, cần chọn queue capacity và pool size theo tải thực tế; không đặt giới hạn tùy ý mà không đo throughput và độ trễ.

brokerChannel không phải nơi client gửi trực tiếp frame STOMP. Message client gửi vào được xử lý từ clientInboundChannel; brokerChannel chủ yếu phục vụ luồng phát message bắt nguồn từ phía server.

## 4. clientOutboundChannel: đường ra tới WebSocket client

Khi broker tìm được các subscription phù hợp, nó gửi Spring Message đến clientOutboundChannel. Spring chuyển message thành STOMP frame và ghi lên WebSocket session tương ứng.

Ví dụ server publish:

~~~java
messagingTemplate.convertAndSend(
        "/topic/chat",
        new ChatMessage("server", "Có người vừa tham gia phòng chat")
);
~~~

Luồng:

~~~text
SimpMessagingTemplate
       |
       v
brokerChannel
       |
       v
Message Broker
       |
       | tìm subscriber của /topic/chat
       v
clientOutboundChannel
       |
       | encode thành STOMP MESSAGE
       v
WebSocket session của từng client
~~~

clientOutboundChannel thường mang các message do broker gửi đến client, bao gồm dữ liệu ứng dụng và các phản hồi liên quan đến quá trình xử lý STOMP. Đây cũng là vị trí hữu ích để đo lưu lượng gửi ra, quan sát lỗi và tìm hiện tượng client tiêu thụ chậm.

### Những việc phù hợp với outbound channel

- Thu thập metric số message và byte gửi đến client.
- Ghi nhận thời gian gửi và lỗi transport.
- Áp dụng kiểm tra hoặc biến đổi header khi thật sự cần.
- Quan sát áp lực do các client chậm hoặc mạng có băng thông thấp.

Không nên sửa tùy tiện destination, subscription ID hoặc các header STOMP do framework quản lý. Việc thay đổi metadata định tuyến có thể khiến message đến sai session hoặc không còn khớp subscription.

## 5. Phân biệt destination prefix và channel

Đây là điểm dễ nhầm khi mới học Spring STOMP.

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| WebSocket endpoint | /ws | URL client dùng để handshake WebSocket. |
| Application destination prefix | /app | Prefix định tuyến SEND đến @MessageMapping. |
| Broker destination prefix | /topic, /queue | Prefix destination được broker xử lý theo cấu hình. |
| clientInboundChannel | Channel nội bộ Spring | Nhận message từ client. |
| brokerChannel | Channel nội bộ Spring | Chuyển message từ ứng dụng đến broker. |
| clientOutboundChannel | Channel nội bộ Spring | Chuyển message gửi ra client. |

Ví dụ cấu hình endpoint và broker:

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

- Client kết nối WebSocket đến /ws.
- SEND đến /app/chat được chuyển đến @MessageMapping("/chat").
- SUBSCRIBE /topic/chat đăng ký với broker.
- Controller hoặc service publish đến /topic/chat qua brokerChannel.
- Broker gửi message đến subscriber qua clientOutboundChannel.

Với built-in simple broker, /topic và /queue là quy ước đặt tên để phân biệt kiểu sử dụng; chúng không có ý nghĩa đặc biệt bắt buộc trong STOMP protocol. Với external broker relay, cần dùng destination prefix được broker thực tế hỗ trợ.

## 6. Interceptor trên từng channel

Spring cho phép đăng ký **ChannelInterceptor** để quan sát hoặc can thiệp message trong luồng xử lý. Trong STOMP over WebSocket, thường đăng ký interceptor qua WebSocketMessageBrokerConfigurer.

| Vị trí | Điểm đăng ký | Công dụng thường gặp |
|---|---|---|
| Inbound | configureClientInboundChannel | Xác thực, phân quyền, kiểm tra command/destination, tracing. |
| Broker | MessageBrokerRegistry.configureBrokerChannel() | Kiểm tra hoặc đo message do server publish. |
| Outbound | configureClientOutboundChannel | Đo lưu lượng gửi ra, quan sát metadata và lỗi. |

### ChannelInterceptor hoạt động thế nào?

Một interceptor có thể triển khai các callback:

- **preSend:** chạy trước khi message được gửi vào channel. Trả về message để tiếp tục; trả null để chặn message.
- **postSend:** chạy sau thao tác send và nhận trạng thái send thành công hay không.
- **afterSendCompletion:** chạy sau khi việc gửi hoàn tất, kể cả khi có exception.
- **preReceive / postReceive:** áp dụng với channel có thao tác receive tương ứng.

Với STOMP, dùng **StompHeaderAccessor** để đọc command, destination, session ID, user và native headers.

### Ví dụ interceptor cho inbound

~~~java
public class InboundTraceInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel
    ) {
        StompHeaderAccessor accessor =
                StompHeaderAccessor.wrap(message);

        StompCommand command = accessor.getCommand();
        String destination = accessor.getDestination();
        String sessionId = accessor.getSessionId();

        // Có thể ghi metric/tracing từ command, destination và sessionId.
        // Không ghi toàn bộ payload hoặc token nhạy cảm vào log.

        return message;
    }
}
~~~

Đăng ký:

~~~java
@Override
public void configureClientInboundChannel(ChannelRegistration registration) {
    registration.interceptors(new InboundTraceInterceptor());
}
~~~

Nếu interceptor trả về null từ preSend, message bị loại khỏi luồng và các handler phía sau không nhận được nó. Hãy chỉ làm vậy khi chính sách thực sự yêu cầu chặn; đồng thời thiết kế phản hồi lỗi phù hợp để client hiểu lý do.

### ExecutorChannelInterceptor

**ExecutorChannelInterceptor** mở rộng ChannelInterceptor và cung cấp callback chạy trong thread xử lý của từng MessageHandler đăng ký với channel. Nó hữu ích khi cần gắn context hoặc đo thời gian quanh từng handler invocation.

ChannelInterceptor được gọi một lần cho thao tác gửi message vào channel; ExecutorChannelInterceptor có thể được gọi theo từng handler subscriber. Không nên nhầm hai phạm vi callback này khi đếm message hoặc đo latency.

### Xác thực và Spring Security

Một mẫu phổ biến là xử lý STOMP CONNECT bằng interceptor trên clientInboundChannel, xác thực token rồi đặt Principal vào message qua StompHeaderAccessor. Spring ghi nhận user cho session và gắn user đó vào các message tiếp theo.

Nếu ứng dụng dùng Spring Security message authorization, interceptor xác thực phải được thực thi trước interceptor phân quyền để user đã được thiết lập khi kiểm tra quyền. Nên tham khảo cấu hình thứ tự interceptor trong tài liệu Spring Security thay vì tự giả định thứ tự bean.

## 7. Cấu hình executor và xử lý tải

clientInboundChannel và clientOutboundChannel được hỗ trợ bởi executor để thực hiện message handler bất đồng bộ. brokerChannel cũng có thể cấu hình executor qua MessageBrokerRegistry.

Ví dụ:

~~~java
@Override
public void configureClientInboundChannel(ChannelRegistration registration) {
    registration
            .taskExecutor()
            .corePoolSize(4)
            .maxPoolSize(8)
            .queueCapacity(1000);
}

@Override
public void configureClientOutboundChannel(ChannelRegistration registration) {
    registration
            .taskExecutor()
            .corePoolSize(4)
            .maxPoolSize(8)
            .queueCapacity(1000);
}
~~~

Các con số trên chỉ là giá trị minh họa. Cần chọn theo CPU, thời gian xử lý, số lượng session, tốc độ client và khả năng chịu tải của broker.

### Core pool, max pool và queue capacity

- **corePoolSize:** số worker cốt lõi được duy trì.
- **maxPoolSize:** số worker tối đa khi executor cần mở rộng.
- **queueCapacity:** số task có thể chờ khi chưa có worker rảnh.

Một điểm quan trọng của ThreadPoolExecutor: nếu queue không giới hạn, task thường được đưa vào queue sau khi core threads bận, nên maxPoolSize có thể không được sử dụng như kỳ vọng. Nếu muốn executor mở rộng đến maxPoolSize, cần chọn queue capacity hữu hạn và hiểu chính sách từ chối khi queue đầy.

### Inbound và outbound có đặc tính tải khác nhau

- **Inbound:** tải chủ yếu đến từ số frame client gửi và thời gian xử lý trong controller/interceptor. Nếu handler gọi database hoặc HTTP đồng bộ, worker có thể bị giữ lâu.
- **Outbound:** tải phụ thuộc số message phát và tốc độ ghi tới từng client. Client chậm hoặc mạng yếu có thể làm buffer tăng.
- **Broker channel:** tải đến từ controller và service phía server publish. Nếu broker chậm hoặc nhiều message được phát đồng thời, queue của channel có thể tăng.

Không tăng thread pool một cách máy móc. Thread quá nhiều làm tăng context switching và cạnh tranh tài nguyên; queue quá lớn có thể che giấu tình trạng quá tải và khiến độ trễ tăng.

## 8. Thứ tự message và preserve order

Vì inbound và outbound channel có thể dùng ThreadPoolExecutor, message được nhận theo một thứ tự có thể được xử lý hoặc gửi ra trong các thread khác nhau. Kết quả quan sát tại client có thể khác thứ tự ban đầu.

Spring cung cấp hai cấu hình riêng:

### Giữ thứ tự nhận từ client

Trong **registerStompEndpoints**, bật preserve receive order:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.addEndpoint("/ws");
    registry.setPreserveReceiveOrder(true);
}
~~~

Cấu hình này bảo đảm message trong cùng một WebSocket session được đưa vào clientInboundChannel lần lượt theo thứ tự nhận. Nó không tạo thứ tự toàn cục giữa các client session khác nhau.

### Giữ thứ tự publish đến client

Trong **configureMessageBroker**, bật preserve publish order:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
    registry.setPreservePublishOrder(true);
}
~~~

Cấu hình này khiến message trong cùng client session được gửi đến clientOutboundChannel từng message một theo thứ tự publish. Có chi phí hiệu năng, vì vậy chỉ bật khi nghiệp vụ cần.

Hai cờ có mục đích khác nhau:

| Cấu hình | Bảo vệ thứ tự ở đâu? |
|---|---|
| setPreserveReceiveOrder(true) | Client → clientInboundChannel. |
| setPreservePublishOrder(true) | Broker → clientOutboundChannel → client. |

Chúng không bảo đảm thứ tự toàn cục giữa nhiều client, nhiều server instance hoặc nhiều publisher độc lập. Nếu nghiệp vụ cần thứ tự theo aggregate, vẫn nên dùng sequence number và xử lý idempotent.

## 9. Simple broker và external broker relay

Ba channel vẫn có vai trò tương tự khi dùng built-in simple broker hoặc external STOMP broker. Điểm khác là thành phần nhận message ở phía broker.

### Built-in simple broker

- Broker handler chạy trong ứng dụng Spring.
- Subscription được quản lý trong bộ nhớ của ứng dụng.
- Phù hợp phát triển, thử nghiệm hoặc ứng dụng nhỏ.
- Không cung cấp đầy đủ các tính năng của broker chuyên dụng.
- Không phù hợp để chia sẻ subscription/message state giữa nhiều application instance.

### External broker relay

- Spring chuyển message từ brokerChannel đến STOMP broker bên ngoài qua TCP.
- Broker bên ngoài quản lý subscription và broadcast.
- Message từ broker được đưa ngược về Spring rồi đi qua clientOutboundChannel.
- Có thể mở rộng nhiều application instance cùng kết nối một broker chung.
- Khả năng destination, persistence, acknowledgment và các tính năng nâng cao phụ thuộc broker.

Luồng với relay:

~~~text
WebSocket Client
      |
      v
clientInboundChannel
      |
      +---- /app ---> @MessageMapping
      |                    |
      |                    v
      |               brokerChannel
      |                    |
      |                    v
      |             STOMP Broker Relay
      |                    |
      |                    v
      |              External Broker
      |                    |
      |                    v
      +---------------- clientOutboundChannel
                           |
                           v
                       WebSocket
~~~

Broker relay duy trì kết nối TCP system riêng cho message do server phát và các kết nối TCP riêng đại diện cho từng WebSocket client. Cấu hình credentials, virtual host, host/port và heartbeat theo broker thực tế. Việc dùng relay không làm biến mất ba channel nội bộ của Spring.

## 10. Ví dụ tổng hợp: nhận chat và phát thông báo

Ví dụ dưới đây ghép ba channel với controller, service publisher và interceptor. Đây là các thành phần tích hợp Spring Framework; ứng dụng cần WebSocket endpoint, message broker và client STOMP đang chạy.

### Cấu hình WebSocketConfig.java

~~~java
package com.example.messaging;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.ChannelRegistration;
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
        registry.setPreserveReceiveOrder(true);
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setPreservePublishOrder(true);

        registry.configureBrokerChannel()
                .taskExecutor()
                .corePoolSize(2)
                .maxPoolSize(4)
                .queueCapacity(500);
    }

    @Override
    public void configureClientInboundChannel(ChannelRegistration registration) {
        registration.interceptors(new InboundTraceInterceptor());
        registration.taskExecutor()
                .corePoolSize(4)
                .maxPoolSize(8)
                .queueCapacity(1000);
    }

    @Override
    public void configureClientOutboundChannel(ChannelRegistration registration) {
        registration.taskExecutor()
                .corePoolSize(4)
                .maxPoolSize(8)
                .queueCapacity(1000);
    }
}
~~~

### ChatMessage.java

~~~java
package com.example.messaging;

public record ChatMessage(String sender, String text) {
}
~~~

### ChatController.java

~~~java
package com.example.messaging;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    @MessageMapping("/chat")
    @SendTo("/topic/chat")
    public ChatMessage handle(ChatMessage message) {
        return message;
    }
}
~~~

### NotificationPublisher.java

~~~java
package com.example.messaging;

import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Component;

@Component
public class NotificationPublisher {

    private final SimpMessagingTemplate messagingTemplate;

    public NotificationPublisher(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void publish(String text) {
        messagingTemplate.convertAndSend(
                "/topic/notifications",
                new ChatMessage("system", text)
        );
    }
}
~~~

### InboundTraceInterceptor.java

~~~java
package com.example.messaging;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;

public class InboundTraceInterceptor implements ChannelInterceptor {

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel
    ) {
        StompHeaderAccessor accessor = StompHeaderAccessor.wrap(message);

        StompCommand command = accessor.getCommand();
        String destination = accessor.getDestination();
        String sessionId = accessor.getSessionId();

        // Đưa command, destination và sessionId vào metric/tracing phù hợp.
        // Tránh log token hoặc toàn bộ payload.

        return message;
    }
}
~~~

### Cách client sử dụng

Client kết nối đến endpoint /ws, sau đó subscribe và gửi:

~~~text
SUBSCRIBE
id:chat-sub
destination:/topic/chat

^@

SEND
destination:/app/chat
content-type:application/json

{"sender":"Lan","text":"Xin chào"}^@
~~~

Kết quả luồng:

1. STOMP SEND được giải mã và đi vào clientInboundChannel.
2. InboundTraceInterceptor quan sát command và destination.
3. Prefix /app định tuyến đến ChatController.handle.
4. Giá trị trả về được gửi qua brokerChannel đến broker.
5. Broker tìm subscriber của /topic/chat.
6. Message được gửi qua clientOutboundChannel và mã hóa thành STOMP MESSAGE.
7. Các client đã subscribe nhận nội dung chat.

Nếu một service gọi NotificationPublisher.publish, message đi thẳng từ ứng dụng qua brokerChannel, sau đó broker phân phối ra clientOutboundChannel. Luồng này không cần một client gửi SEND trước.

Đây là ví dụ tích hợp, không có stdout cố định. Kết quả được quan sát qua STOMP client đã kết nối và subscribe; ứng dụng cần cấu hình dependency Spring WebSocket/Messaging và môi trường chạy WebSocket phù hợp.

## 11. Theo dõi và chẩn đoán channel

Spring cung cấp số liệu thống kê cho message broker và các executor liên quan. Có thể dùng **WebSocketMessageBrokerStats** để theo dõi số session, frame, transport error và thống kê thread pool.

Một số dấu hiệu:

| Dấu hiệu | Nơi kiểm tra | Khả năng cần xem xét |
|---|---|---|
| Queue task inbound tăng | clientInboundChannel | Controller/interceptor xử lý chậm, database/HTTP blocking hoặc pool quá nhỏ. |
| Queue task outbound tăng | clientOutboundChannel | Client chậm, mạng yếu, message quá lớn hoặc tốc độ publish cao. |
| Send timeout hoặc buffer tăng | WebSocket transport | Client không tiêu thụ kịp; cần kiểm tra sendTimeLimit và sendBufferSizeLimit. |
| Broker publish chậm | brokerChannel và broker relay | Broker quá tải, TCP chậm hoặc queue brokerChannel bị nghẽn. |
| Client không nhận message | Inbound → broker → outbound | Kiểm tra destination prefix, subscription, authorization và trạng thái broker. |
| Message tới sai handler | clientInboundChannel | Kiểm tra applicationDestinationPrefixes và broker destination prefixes. |

Khi outbound chậm, tăng thread pool không phải lúc nào cũng giải quyết được vấn đề. Spring WebSocket transport có sendTimeLimit và sendBufferSizeLimit để giới hạn thời gian gửi và lượng dữ liệu buffer cho một client.

Với nhiều application instance, simple broker không chia sẻ state giữa các instance. Nếu client kết nối vào instance A nhưng publisher chạy ở instance B, cần external broker relay hoặc một cơ chế chia sẻ message phù hợp.

## 12. Những lỗi thường gặp

1. **Nhầm channel với destination.** clientInboundChannel là đường nội bộ Spring; /app/chat và /topic/chat là destination được định tuyến.
2. **Cho rằng mọi message client gửi đều đi qua brokerChannel.** Client frame vào clientInboundChannel; frame được route trực tiếp đến broker hoặc controller tùy destination/command.
3. **Cho rằng controller return value gửi trực tiếp ra WebSocket.** Return value thường được chuyển thành Spring Message và gửi qua brokerChannel để broker phân phối.
4. **Dùng clientOutboundChannel để publish từ service.** Service nên dùng SimpMessagingTemplate; template gửi qua brokerChannel.
5. **Không phân biệt /app với /topic.** /app thường định tuyến đến @MessageMapping; /topic và /queue thường định tuyến đến broker theo cấu hình.
6. **Đăng ký interceptor sai channel.** Authentication/authorization cho client frame thường đặt ở inbound; kiểm tra message server publish thuộc brokerChannel; đo gửi ra thuộc outbound.
7. **Chặn message nhưng quên phản hồi lỗi.** preSend trả null làm message dừng ở channel; client có thể không biết vì sao thao tác không được xử lý.
8. **Đặt xử lý blocking lâu trong inbound interceptor.** Worker bị giữ làm tăng queue và latency của toàn endpoint.
9. **Tăng maxPoolSize nhưng giữ queue không giới hạn.** Executor có thể tiếp tục queue task và không mở rộng đến maxPoolSize như kỳ vọng.
10. **Bật preserve order rồi nghĩ toàn hệ thống có FIFO.** Hai cờ chỉ bảo vệ thứ tự trong cùng session ở các chặng tương ứng; không tạo thứ tự toàn cục giữa các client hoặc instance.
11. **Dùng simple broker cho nhiều instance.** Simple broker giữ subscription trong bộ nhớ của một instance; dùng broker relay khi cần chia sẻ qua nhiều node.
12. **Bỏ qua outbound backpressure.** Client chậm có thể làm send buffer và executor queue tăng; cần theo dõi timeout, buffer và tốc độ publish.
13. **Sửa header STOMP tùy tiện ở outbound.** Thay đổi destination hoặc subscription metadata có thể làm message không tới đúng client.
14. **Dùng ChannelInterceptor như một handler nghiệp vụ.** Interceptor phù hợp với cross-cutting concerns; nghiệp vụ nên nằm trong controller/service để dễ kiểm thử và quản lý transaction.

## 13. Ghi nhớ

- **clientInboundChannel** nhận các STOMP message từ WebSocket client sau khi Spring giải mã frame.
- **brokerChannel** chuyển message do code phía server tạo đến message broker.
- **clientOutboundChannel** chuyển message từ broker/server đến WebSocket client.
- Destination prefix như /app, /topic và /queue quyết định routing; tên channel là hạ tầng nội bộ Spring.
- Client SEND đến /app thường được xử lý bởi @MessageMapping; SUBSCRIBE /topic hoặc /queue được broker quản lý.
- Return value của controller và SimpMessagingTemplate publish qua brokerChannel.
- ChannelInterceptor dùng cho tracing, xác thực, phân quyền và kiểm tra message; ExecutorChannelInterceptor có callback theo từng MessageHandler.
- WebSocketMessageBrokerConfigurer cấu hình inbound/outbound channel; MessageBrokerRegistry.configureBrokerChannel() cấu hình brokerChannel.
- Executor, queue capacity và send buffer phải được chọn theo workload và đo đạc thực tế.
- setPreserveReceiveOrder và setPreservePublishOrder bảo vệ thứ tự trong cùng session ở hai chặng khác nhau, có chi phí hiệu năng.
- Simple broker phù hợp ứng dụng đơn giản; broker relay kết nối broker bên ngoài và hỗ trợ chia sẻ message giữa nhiều application instance.

Khi debug một message STOMP, hãy lần theo đúng ba chặng: clientInboundChannel để xem message đi vào đâu, brokerChannel để xem ứng dụng publish thế nào, và clientOutboundChannel để xem broker phát message đến client nào. Cách lần theo này giúp khoanh vùng lỗi routing, xử lý và gửi dữ liệu nhanh hơn.

## Tài liệu tham khảo

- [Spring Framework 6.2.19 — Flow of Messages](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/message-flow.html)
- [Spring Framework 6.2 — Enable STOMP](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/enable.html)
- [Spring Framework 6.2 — Interception](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/interceptors.html)
- [Spring Framework 6.2 — Order of Messages](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/ordered-messages.html)
- [Spring Framework 6.2 — Performance](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/configuration-performance.html)
- [Spring Framework 6.2 — WebSocketMessageBrokerConfigurer API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/web/socket/config/annotation/WebSocketMessageBrokerConfigurer.html)
- [Spring Framework 6.2 — MessageBrokerRegistry API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/simp/config/MessageBrokerRegistry.html)
- [Spring Framework 6.2 — ChannelRegistration API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/messaging/simp/config/ChannelRegistration.html)
