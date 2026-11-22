# Phân biệt STOMP qua WebSocket và WebSocket thuần

WebSocket và STOMP thường xuất hiện cùng nhau trong ứng dụng realtime, nhưng chúng thuộc hai lớp khác nhau. **WebSocket** là giao thức truyền tải hai chiều, giữ kết nối mở giữa client và server. Nó chuyển các frame text hoặc binary nhưng không quy định nội dung của message, cách định tuyến hay cơ chế publish-subscribe. **STOMP** là giao thức messaging ở lớp ứng dụng, có thể chạy bên trên WebSocket để chuẩn hóa command, header, destination, subscription và acknowledgement.

Vì vậy, “STOMP over WebSocket” vẫn sử dụng kết nối WebSocket. Điểm khác biệt là client và server thống nhất thêm một giao thức message. Trong Spring, WebSocket thuần thường dùng WebSocketHandler; STOMP dùng WebSocket message broker support, @MessageMapping và broker tích hợp hoặc broker relay.

## 1. Hai lớp giao thức

### 1.1. WebSocket là transport

WebSocket được chuẩn hóa trong RFC 6455. Kết nối thường bắt đầu bằng HTTP handshake có header Upgrade. Nếu server chấp nhận, nó trả về status 101 Switching Protocols và giữ kết nối TCP mở để client và server gửi dữ liệu hai chiều.

Sau handshake, hai bên trao đổi WebSocket message dưới dạng:

- **Text message:** dữ liệu văn bản, thường là JSON, XML hoặc chuỗi theo quy ước ứng dụng.
- **Binary message:** dữ liệu nhị phân như protobuf, file chunk hoặc định dạng riêng.

WebSocket còn định nghĩa các control frame như ping, pong và close, cùng cơ chế fragmentation ở tầng frame. Tuy nhiên, nó không quy định rằng một text message là lệnh SEND, một binary message là sự kiện, hay một client đã đăng ký subscription nào.

Một kết nối WebSocket thường có một URL để khởi tạo. Sau khi kết nối được thiết lập, nhiều message ứng dụng đi qua cùng kết nối đó. Đây là mô hình event-driven và full-duplex, khác với HTTP request-response thông thường.

### 1.2. STOMP là messaging protocol

**STOMP (Simple Text Oriented Messaging Protocol)** định nghĩa cách biểu diễn message bằng frame. Một frame có command, các header, phần body tùy chọn và ký tự NULL kết thúc frame.

Ví dụ một client gửi message:

~~~text
SEND
destination:/app/chat.send
content-type:application/json

{"room":"orders","text":"Hello"}^@
~~~

Ký hiệu ^@ trong tài liệu STOMP biểu diễn byte NULL (0x00), không phải hai ký tự dấu mũ và @. STOMP mặc định dùng UTF-8 cho command/header và hỗ trợ payload text hoặc binary.

Các command thường gặp:

| Command | Vai trò |
|---|---|
| CONNECT hoặc STOMP | Bắt đầu STOMP session và thương lượng phiên bản |
| CONNECTED | Server xác nhận kết nối STOMP |
| SEND | Gửi message đến destination |
| SUBSCRIBE | Đăng ký nhận message từ destination |
| UNSUBSCRIBE | Hủy subscription |
| MESSAGE | Server chuyển message đến subscriber |
| ACK / NACK | Xác nhận hoặc từ chối message theo ack mode |
| RECEIPT | Xác nhận server đã xử lý frame yêu cầu receipt |
| ERROR | Báo lỗi giao thức |
| DISCONNECT | Ngắt STOMP session một cách có kiểm soát |

STOMP cũng định nghĩa heartbeat, transaction frame và các chế độ acknowledgement. Nhưng ý nghĩa thực tế của destination, delivery, persistence, redelivery và dead-letter vẫn phụ thuộc STOMP server/broker. Tên /queue/orders hay /topic/prices là quy ước phổ biến; bản thân STOMP xem destination là chuỗi opaque.

## 2. STOMP được thương lượng trên WebSocket như thế nào?

WebSocket cho phép client và server thương lượng subprotocol trong HTTP handshake qua header **Sec-WebSocket-Protocol**. Với STOMP, client có thể đề xuất các phiên bản subprotocol mà nó hỗ trợ; server chọn một phiên bản chung và trả về trong response handshake.

Ví dụ minh họa:

~~~http
GET /ws HTTP/1.1
Host: example.com
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Protocol: v10.stomp, v11.stomp, v12.stomp
Sec-WebSocket-Version: 13
~~~

Server có thể phản hồi:

~~~http
HTTP/1.1 101 Switching Protocols
Upgrade: websocket
Connection: Upgrade
Sec-WebSocket-Protocol: v12.stomp
~~~

Sau handshake, client và server trao đổi STOMP frame bên trong các WebSocket message. Nếu không thương lượng subprotocol, hai bên vẫn có thể dùng WebSocket, nhưng phải thống nhất một định dạng ứng dụng riêng.

Cần phân biệt:

- HTTP Upgrade thiết lập transport WebSocket.
- Sec-WebSocket-Protocol thương lượng giao thức ứng dụng chạy trên WebSocket.
- STOMP CONNECT/CONNECTED thiết lập STOMP session sau khi transport đã sẵn sàng.

## 3. WebSocket thuần trong Spring

Spring cung cấp API trực tiếp để xử lý WebSocket message. Ứng dụng có thể triển khai **WebSocketHandler**, hoặc kế thừa **TextWebSocketHandler** và **BinaryWebSocketHandler** nếu chỉ cần xử lý một loại payload.

Ví dụ handler text:

~~~java
package com.example.websocket;

import java.io.IOException;
import org.springframework.stereotype.Component;
import org.springframework.web.socket.TextMessage;
import org.springframework.web.socket.WebSocketSession;
import org.springframework.web.socket.handler.TextWebSocketHandler;

@Component
public class RawChatHandler extends TextWebSocketHandler {
    @Override
    protected void handleTextMessage(WebSocketSession session, TextMessage message) throws IOException {
        String payload = message.getPayload();
        String response = "received:" + payload;
        session.sendMessage(new TextMessage(response));
    }
}
~~~

Đăng ký handler bằng Java configuration:

~~~java
package com.example.websocket;

import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocket;
import org.springframework.web.socket.config.annotation.WebSocketConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketHandlerRegistry;

@Configuration
@EnableWebSocket
public class RawWebSocketConfiguration implements WebSocketConfigurer {
    private final RawChatHandler rawChatHandler;
    public RawWebSocketConfiguration(RawChatHandler rawChatHandler) {
        this.rawChatHandler = rawChatHandler;
    }
    @Override
    public void registerWebSocketHandlers(WebSocketHandlerRegistry registry) {
        registry.addHandler(rawChatHandler, "/raw-chat")
                .setAllowedOrigins("https://app.example.com");
    }
}
~~~

Trong ví dụ, client kết nối đến /raw-chat, sau đó gửi text message. Handler nhận WebSocketSession và TextMessage, tự parse payload rồi quyết định phản hồi.

Nếu cần binary message, có thể kế thừa BinaryWebSocketHandler và override handleBinaryMessage. Nếu cần quản lý connect/disconnect, có thể override afterConnectionEstablished và afterConnectionClosed.

### 3.1. Ứng dụng phải tự định nghĩa message contract

Với WebSocket thuần, client và server cần thống nhất định dạng. Ví dụ JSON:

~~~json
{
  "version": 1,
  "type": "subscribe",
  "requestId": "req-42",
  "destination": "/prices",
  "payload": null
}
~~~

Một message khác có thể là:

~~~json
{
  "version": 1,
  "type": "publish",
  "requestId": "req-43",
  "destination": "/prices",
  "payload": {
    "symbol": "ACME",
    "price": 125.5
  }
}
~~~

Ứng dụng phải tự quy định:

- type nào được phép gửi và nhận.
- Cấu trúc payload, schema version và cách validate.
- Cách đăng ký/hủy subscription.
- Cách định tuyến message đến một client, một nhóm client hoặc mọi client.
- Correlation ID, request-response và timeout.
- ACK/NACK, retry, duplicate handling và idempotency nếu cần.
- Heartbeat ở tầng ứng dụng nếu ping/pong của WebSocket chưa đáp ứng yêu cầu.
- Quy tắc lỗi, reconnect và khôi phục subscription sau reconnect.

Đây là ưu điểm khi cần giao thức riêng gọn và sát nghiệp vụ. Đổi lại, client và server phải cùng triển khai và duy trì contract đó.

### 3.2. Chú ý gửi message đồng thời

Một WebSocketSession tiêu chuẩn không cho phép nhiều thread gửi đồng thời trên cùng session. Nếu nhiều luồng server cùng gửi đến một client, ứng dụng cần đồng bộ thao tác gửi hoặc dùng **ConcurrentWebSocketSessionDecorator** để tuần tự hóa việc gửi và giới hạn thời gian/buffer theo cấu hình.

Không nên coi WebSocketSession.sendMessage() là một hàng đợi thread-safe không giới hạn. Cần xử lý backpressure, giới hạn message size và trường hợp client đọc chậm.

~~~java
package com.example.websocket;

public record ChatMessage(String sender, String content) {
}
~~~

~~~java
package com.example.websocket;

import java.math.BigDecimal;

public record PriceUpdate(String symbol, BigDecimal price) {
}
~~~
## 4. STOMP over WebSocket trong Spring

Khi dùng STOMP, Spring cung cấp message broker programming model. Cấu hình thường dùng @EnableWebSocketMessageBroker và WebSocketMessageBrokerConfigurer.

Ví dụ:

~~~java
package com.example.websocket;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class StompWebSocketConfiguration implements WebSocketMessageBrokerConfigurer {
    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
                .setAllowedOrigins("https://app.example.com");
    }
    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Ý nghĩa:

- /ws là URL client dùng để thực hiện WebSocket handshake.
- /app là prefix cho message gửi vào application controller.
- /topic và /queue là prefix được dùng để định tuyến đến simple broker trong ví dụ.
- Simple broker lưu subscription trong bộ nhớ và broadcast message đến các subscriber phù hợp.

Các prefix /topic và /queue trong built-in simple broker chỉ là quy ước định tuyến. Khi dùng external broker, phải theo cú pháp destination và semantics mà broker đó hỗ trợ.

### 4.1. Xử lý message bằng @MessageMapping

Controller nhận STOMP message có thể dùng @MessageMapping:

~~~java
package com.example.websocket;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {
    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage send(ChatMessage message) {
        return new ChatMessage(message.sender(), message.content());
    }
}
~~~

Khi client gửi STOMP SEND đến /app/chat.send, Spring bỏ application prefix /app, sau đó ánh xạ phần còn lại vào method @MessageMapping("/chat.send"). Giá trị trả về được gửi đến destination /topic/chat, nơi broker phân phối cho các subscriber.

Nếu muốn gửi message từ service hoặc scheduled task, có thể inject SimpMessagingTemplate:

~~~java
package com.example.websocket;

import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class PricePublisher {
    private final SimpMessagingTemplate messagingTemplate;
    public PricePublisher(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }
    public void publish(PriceUpdate update) {
        messagingTemplate.convertAndSend("/topic/prices", update);
    }
}
~~~

Service có thể phát message mà không cần biết từng WebSocketSession của client. Broker quản lý subscription và phân phối message.

## 5. Luồng message STOMP bên trong Spring

Spring chuyển STOMP frame thành Spring Message<?>, sau đó đưa message qua các channel nội bộ.

~~~mermaid
flowchart TD
    C["WebSocket client"] --> W["WebSocket handshake /ws"]
    W --> S["STOMP frame"]
    S --> I["clientInboundChannel"]
    I --> A{"Destination prefix"}
    A -->|/app| M["@MessageMapping controller"]
    A -->|/topic or /queue| B["Message broker"]
    M --> BC["brokerChannel"]
    BC --> B
    B --> O["clientOutboundChannel"]
    O --> R["STOMP MESSAGE frame"]
    R --> C
~~~

Các thành phần chính:

- **clientInboundChannel:** nhận message từ WebSocket client.
- **brokerChannel:** chuyển message từ application code đến broker.
- **clientOutboundChannel:** chuyển message từ broker về client.
- **@MessageMapping:** xử lý message thuộc application destination.
- **Message broker:** lưu subscription và phân phối message đến subscriber phù hợp.

Luồng này giúp tách logic nghiệp vụ khỏi việc quản lý từng socket. Một HTTP controller hoặc service cũng có thể gửi message qua broker để broadcast đến các WebSocket client đang subscribe.

## 6. Simple broker và external STOMP broker

Spring có hai lựa chọn chính cho broker.

### 6.1. Built-in simple broker

Simple broker là broker nhỏ chạy trong bộ nhớ của ứng dụng Spring. Nó nhận subscription và broadcast message đến các client đang kết nối có destination khớp.

Phù hợp khi:

- Cần demo hoặc phát triển tính năng realtime ban đầu.
- Số client và lưu lượng ở mức vừa phải.
- Không cần broker độc lập hoặc clustering.
- Các giới hạn của tập command STOMP được hỗ trợ là chấp nhận được.

Simple broker chỉ hỗ trợ một phần STOMP. Nó không hỗ trợ ACK, RECEIPT và một số tính năng khác của protocol. Nó cũng không phù hợp để clustering. Vì vậy, không nên suy luận rằng bật enableSimpleBroker sẽ cung cấp mọi bảo đảm delivery của một broker chuyên dụng.

### 6.2. External broker relay

Khi cần broker đầy đủ hơn, có thể cấu hình relay đến RabbitMQ, ActiveMQ hoặc broker hỗ trợ STOMP:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableStompBrokerRelay("/topic", "/queue")
            .setRelayHost("broker.example.com")
            .setRelayPort(61613)
            .setClientLogin("app-client")
            .setClientPasscode("configured-secret");
}
~~~

Thông tin đăng nhập trong ví dụ phải lấy từ cấu hình bảo mật hoặc secret manager của môi trường triển khai, không hard-code vào source code.

Broker relay mở kết nối TCP đến external broker, chuyển STOMP message từ Spring đến broker và chuyển message từ broker về các WebSocket client. Broker chuyên dụng có thể cung cấp tính năng quản lý subscription, ACK, RECEIPT, persistence, clustering hoặc dead-letter tùy sản phẩm và cấu hình.

STOMP không tự bảo đảm message durable hay exactly-once. Cần kiểm tra semantics của broker, destination, acknowledgement mode, persistence và redelivery policy.

## 7. Client JavaScript: WebSocket thuần và STOMP

### 7.1. WebSocket thuần

Browser API có thể kết nối và gửi JSON theo protocol riêng:

~~~javascript
const socket = new WebSocket("wss://app.example.com/raw-chat");

socket.addEventListener("open", () => {
  socket.send(JSON.stringify({
    version: 1,
    type: "subscribe",
    destination: "/prices"
  }));
});

socket.addEventListener("message", event => {
  const message = JSON.parse(event.data);
  console.log("Application message:", message);
});

socket.addEventListener("close", event => {
  console.log("WebSocket closed:", event.code);
});
~~~

Client và server phải hiểu cùng schema JSON. Browser WebSocket không tự biết subscribe là command messaging; đó chỉ là quy ước của ứng dụng.

### 7.2. STOMP client

Với STOMP, có thể dùng thư viện JavaScript STOMP.js:

~~~javascript
const client = new StompJs.Client({
  brokerURL: "wss://app.example.com/ws",
  reconnectDelay: 5000,
  heartbeatIncoming: 10000,
  heartbeatOutgoing: 10000
});

client.onConnect = () => {
  client.subscribe("/topic/chat", frame => {
    const message = JSON.parse(frame.body);
    console.log("Chat message:", message);
  });

  client.publish({
    destination: "/app/chat.send",
    body: JSON.stringify({
      sender: "Ada",
      content: "Hello"
    }),
    headers: {
      "content-type": "application/json"
    }
  });
};

client.onStompError = frame => {
  console.error("Broker error:", frame.headers["message"]);
};

client.activate();
~~~

STOMP client cung cấp API cấp cao cho CONNECT, SUBSCRIBE, SEND, heartbeat, reconnect và xử lý frame. Ứng dụng vẫn cần quản lý subscription sau reconnect và xử lý lỗi theo nghiệp vụ.

## 8. So sánh trực tiếp

| Tiêu chí | WebSocket thuần | STOMP over WebSocket |
|---|---|---|
| Lớp chính | Transport | Messaging protocol trên transport |
| Payload | Text hoặc binary theo contract tự định nghĩa | STOMP frame có command, header và body |
| Định tuyến | Ứng dụng tự xây dựng | Destination header và broker routing |
| Publish-subscribe | Tự quản lý registry/subscription | Có SUBSCRIBE, UNSUBSCRIBE và MESSAGE |
| Request-response | Tự thiết kế correlation ID và response | Có thể xây dựng bằng destination, header và convention |
| ACK/NACK | Tự thiết kế | Có command và ack mode; broker phải hỗ trợ |
| Heartbeat | WebSocket ping/pong hoặc protocol riêng | STOMP heartbeat, bên dưới vẫn là WebSocket |
| Broker | Tự tích hợp nếu cần | Spring simple broker hoặc external STOMP broker |
| Client | Browser WebSocket hoặc client WebSocket bất kỳ | STOMP client tương thích |
| Spring API | WebSocketHandler, TextWebSocketHandler | @EnableWebSocketMessageBroker, @MessageMapping, SimpMessagingTemplate |
| Khả năng tùy biến | Rất cao | Theo protocol và extension của broker |
| Công việc ứng dụng phải tự làm | Định dạng, routing, subscription, ack, correlation, lỗi | Chủ yếu nghiệp vụ, authorization và cấu hình broker |

## 9. Khi nào chọn WebSocket thuần?

WebSocket thuần phù hợp khi:

- Ứng dụng có giao thức riêng đã được định nghĩa rõ.
- Cần binary payload hoặc định dạng message chuyên biệt.
- Chỉ có một số loại message đơn giản, ví dụ stream trạng thái hoặc điều khiển thiết bị.
- Cần kiểm soát chính xác encoding, framing ở tầng ứng dụng và routing.
- Không cần broker subscription model chuẩn hóa.
- Client/server đều do cùng đội phát triển và có thể cùng nâng cấp protocol.

Ví dụ: game realtime có protocol binary riêng, ứng dụng streaming telemetry hoặc thiết bị IoT có message envelope tối giản.

Hãy version protocol, xác thực payload, giới hạn kích thước, kiểm soát tốc độ gửi, đồng bộ send và xử lý reconnect. Nếu nhiều service hoặc client khác nhau cần cùng giao tiếp, chi phí duy trì protocol riêng sẽ tăng nhanh.

## 10. Khi nào chọn STOMP over WebSocket?

STOMP phù hợp khi:

- Cần publish-subscribe hoặc nhiều client subscribe destination.
- Cần gửi message từ controller/service đến nhiều client.
- Muốn dùng @MessageMapping và Spring message channels.
- Cần một protocol có client library cho nhiều ngôn ngữ.
- Muốn tích hợp broker chuyên dụng để quản lý subscription và broadcast.
- Cần command chuẩn cho subscription, acknowledgement, receipt và heartbeat, với broker hỗ trợ các tính năng tương ứng.

Ví dụ: chat, dashboard realtime, bảng giá, thông báo theo user hoặc cập nhật trạng thái đơn hàng cho nhiều client.

Nếu chỉ cần thử nghiệm trong một ứng dụng đơn giản, simple broker có thể đủ. Nếu cần clustering, broker persistence hoặc tính năng STOMP đầy đủ, hãy dùng external broker relay và kiểm tra rõ các semantics mà broker hỗ trợ.

## 11. Bảo mật và độ tin cậy

Cả hai cách đều cần bảo vệ transport và message.

- Dùng **wss://** trong môi trường production để mã hóa kết nối.
- Giới hạn Origin và kiểm tra handshake. Spring WebSocket mặc định chỉ chấp nhận same-origin trong cấu hình tiêu chuẩn; chỉ mở rộng danh sách origin khi có yêu cầu rõ ràng.
- Xác thực người dùng qua cơ chế HTTP/Spring Security phù hợp và kiểm tra quyền ở từng message.
- Không tin destination hoặc user ID do client gửi. Server phải xác định client được phép publish/subscribe vào destination nào.
- Giới hạn kích thước message, số kết nối, tốc độ gửi và số subscription.
- Xử lý disconnect, timeout, heartbeat, reconnect và backpressure.
- Không ghi token, passcode hoặc payload nhạy cảm vào log.

Với WebSocket thuần, ứng dụng phải tự xây dựng authorization theo loại message và destination. Với STOMP, destination và message type đã có cấu trúc nên Spring Security có thể áp dụng quy tắc bảo vệ message theo destination và command.

Cần hiểu rõ ý nghĩa acknowledgement. STOMP RECEIPT xác nhận server đã xử lý frame tương ứng theo protocol; nó không chứng minh nghiệp vụ phía client đã hoàn tất hoặc database transaction đã commit. Với ack mode auto, broker có thể xem message đã được nhận ngay khi gửi cho client; client và client-individual yêu cầu ACK rõ ràng. Hành vi redelivery khi mất kết nối phụ thuộc broker.

## 12. SockJS có thay thế STOMP không?

Không. SockJS là lớp hỗ trợ transport fallback khi môi trường client hoặc proxy không sử dụng được WebSocket. Nó có thể dùng WebSocket hoặc các HTTP-based transport khác theo khả năng môi trường.

STOMP là messaging protocol. Một endpoint STOMP có thể bật SockJS:

~~~java
registry.addEndpoint("/ws").withSockJS();
~~~

Client tương ứng cần dùng SockJS client kết hợp STOMP client. Việc bật SockJS không thay đổi command, destination hay semantics của STOMP.

## 13. Ví dụ Java 17: so sánh một custom message với STOMP frame

Ví dụ sau dùng JDK thuần để phân tích hai biểu diễn của cùng một ý định subscribe. Raw WebSocket dùng một format do ứng dụng tự định nghĩa; STOMP dùng command và header chuẩn. Chương trình chỉ minh họa format, không mở WebSocket connection và không thay thế parser STOMP production.

Tạo file **StompVsRawWebSocketDemo.java**:

~~~java
import java.util.LinkedHashMap;
import java.util.Map;

public class StompVsRawWebSocketDemo {

    record RawEnvelope(
            String operation,
            String destination,
            String payload) {}

    record StompFrame(
            String command,
            Map<String, String> headers,
            String body) {}

    static RawEnvelope parseRawEnvelope(String wire) {
        String[] parts = wire.split("\\|", 3);

        if (parts.length != 3) {
            throw new IllegalArgumentException(
                    "Expected operation|destination|payload");
        }

        return new RawEnvelope(parts[0], parts[1], parts[2]);
    }

    static StompFrame parseStompFrame(String wire) {
        String normalized = wire.replace("\r\n", "\n");
        int separator = normalized.indexOf("\n\n");

        if (separator < 0) {
            throw new IllegalArgumentException(
                    "STOMP frame has no header/body separator");
        }

        String headerBlock = normalized.substring(0, separator);
        String body = normalized.substring(separator + 2);
        String nullOctet = String.valueOf((char) 0);

        if (body.endsWith(nullOctet)) {
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

        return new StompFrame(command, headers, body);
    }

    public static void main(String[] args) {
        String rawWire = "SUBSCRIBE|/topic/prices|";
        RawEnvelope raw = parseRawEnvelope(rawWire);

        String nullOctet = String.valueOf((char) 0);
        String stompWire =
                "SUBSCRIBE\n"
                + "id:sub-1\n"
                + "destination:/topic/prices\n"
                + "ack:client-individual\n"
                + "\n"
                + nullOctet;

        StompFrame stomp = parseStompFrame(stompWire);

        System.out.println(
                "Raw protocol: " + raw.operation()
                        + " " + raw.destination());

        System.out.println(
                "STOMP command: " + stomp.command());

        System.out.println(
                "STOMP destination: "
                        + stomp.headers().get("destination"));

        System.out.println(
                "STOMP ack mode: " + stomp.headers().get("ack"));
    }
}
~~~

Biên dịch và chạy bằng Java 17 trở lên:

~~~bash
javac StompVsRawWebSocketDemo.java
java StompVsRawWebSocketDemo
~~~

Kết quả:

~~~text
Raw protocol: SUBSCRIBE /topic/prices
STOMP command: SUBSCRIBE
STOMP destination: /topic/prices
STOMP ack mode: client-individual
~~~

Ví dụ raw chỉ hiểu ba trường do ứng dụng tự định nghĩa. Parser STOMP mẫu chỉ xử lý một frame đơn giản với header cơ bản; parser production còn phải xử lý escaping header, content-length, body binary, nhiều frame trên stream và các quy tắc khác của STOMP 1.2.

## 14. Checklist lựa chọn và kiểm thử

Trước khi quyết định, hãy trả lời:

1. Ứng dụng cần một kết nối hai chiều hay cần messaging model có destination/subscription?
2. Có cần nhiều client nhận cùng một message không?
3. Có cần ACK/NACK, receipt, heartbeat hoặc broker persistence không?
4. Client có nhiều ngôn ngữ/nền tảng và cần protocol chuẩn không?
5. Có cần broker độc lập để scale hoặc cluster không?
6. Payload chủ yếu là JSON/text hay binary protocol chuyên biệt?
7. Ai chịu trách nhiệm versioning và tương thích protocol?
8. Quy tắc xác thực, authorization, Origin và giới hạn message đã rõ chưa?

Các test quan trọng:

- Handshake và subprotocol negotiation.
- Text/binary payload và giới hạn kích thước.
- Nhiều client kết nối, disconnect và reconnect.
- Subscribe/unsubscribe, routing và broadcast.
- ACK/NACK, receipt và redelivery nếu broker hỗ trợ.
- Heartbeat và timeout khi kết nối idle.
- Client gửi quá nhanh hoặc đọc chậm để kiểm tra backpressure.
- Kiểm tra người dùng không thể subscribe/publish vào destination trái quyền.
- Broker restart và Spring application restart.

WebSocket thuần cung cấp transport full-duplex và để ứng dụng quyết định message contract. STOMP over WebSocket bổ sung một protocol messaging chuẩn với command, header, destination và subscription, nhờ đó Spring có thể cung cấp controller routing, broker và client API cấp cao. Hãy chọn WebSocket thuần khi cần giao thức riêng tối giản hoặc binary chuyên biệt; chọn STOMP khi ứng dụng cần publish-subscribe, định tuyến message và tích hợp broker. Trong cả hai trường hợp, delivery guarantee, bảo mật và khả năng phục hồi vẫn phải được thiết kế theo yêu cầu thực tế.

## Tài liệu tham khảo

- [Spring Framework: WebSocket API](https://docs.spring.io/spring-framework/reference/web/websocket/server.html)
- [Spring Framework: STOMP overview](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/overview.html)
- [Spring Framework: Enable STOMP](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/enable.html)
- [Spring Framework: Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework: Simple Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-simple-broker.html)
- [Spring Framework: External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [STOMP 1.2 Specification](https://stomp.github.io/stomp-specification-1.2.html)
- [RFC 6455: The WebSocket Protocol](https://www.rfc-editor.org/rfc/rfc6455)