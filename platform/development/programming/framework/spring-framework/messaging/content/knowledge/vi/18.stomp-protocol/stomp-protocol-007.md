# destination, subscription id và message id trong STOMP

## 1. Vì sao phải phân biệt ba khái niệm?

Trong STOMP, một message có thể đi qua nhiều destination, được gửi đến nhiều subscription và mang một định danh riêng khi server giao đến client. Ba khái niệm destination, subscription id và message id có liên hệ với nhau nhưng giải quyết ba bài toán khác nhau:

- **destination** cho biết message được gửi đến đâu hoặc client muốn nghe ở đâu.
- **subscription id** xác định một đăng ký nhận message cụ thể của một STOMP connection.
- **message-id** định danh một message mà server gửi về client trong một MESSAGE frame.

Nếu nhầm chúng, ứng dụng có thể hủy nhầm subscription, không phân biệt được các bản nhận cùng destination, ACK sai message hoặc dùng một ID tạm thời làm khóa nghiệp vụ lâu dài.

Ngoài ba giá trị trên, STOMP còn có các định danh khác: id trong SUBSCRIBE/UNSUBSCRIBE, ack token, receipt/receipt-id, session id, transaction id và ID nghiệp vụ do ứng dụng tự định nghĩa. Tên header có thể giống nhau giữa các command nhưng ý nghĩa phụ thuộc command đang được gửi.

Bài học dùng STOMP 1.2 và Spring Framework 6.2 làm nền tảng. Sau bài học, người đọc có thể:

- Xác định destination trong SEND, SUBSCRIBE và MESSAGE.
- Giải thích phạm vi và tính duy nhất của subscription id.
- Đọc message-id trong MESSAGE frame và hiểu ai tạo ra nó.
- Phân biệt message-id với ack token, receipt id, Spring MessageHeaders.ID và business event id.
- Hiểu cách ACK/NACK liên kết với message trong STOMP 1.2.
- Truy cập các header qua StompHeaderAccessor và Spring Message.
- Cấu hình endpoint, broker và @MessageMapping trong Spring.
- Dùng STOMP client để subscribe, publish và đọc các ID trả về.
- Chẩn đoán lỗi routing, subscription và acknowledgement.

## 2. Destination: địa chỉ định tuyến message

### 2.1. Destination xuất hiện ở đâu?

Trong STOMP, destination là header chỉ nơi message được gửi đến hoặc nơi client muốn đăng ký nhận message.

Destination là header bắt buộc trong các frame:

- SEND: nơi client gửi message.
- SUBSCRIBE: nơi client đăng ký nhận message.
- MESSAGE: destination mà message được giao đến.

Ví dụ client gửi một message:

~~~text
SEND
destination:/app/orders.publish
content-type:application/json

{"eventId":"evt-1001","orderId":"ORD-1001","status":"CREATED"}<NUL>
~~~

Ví dụ client đăng ký nhận message:

~~~text
SUBSCRIBE
id:orders-view-1
destination:/topic/orders
ack:auto

<NUL>
~~~

Khi server giao một message đến subscriber, MESSAGE frame có destination:

~~~text
MESSAGE
subscription:orders-view-1
message-id:server-msg-9001
destination:/topic/orders
content-type:application/json

{"eventId":"evt-1001","orderId":"ORD-1001","status":"CREATED"}<NUL>
~~~

Destination trong MESSAGE cho biết message được giao từ destination nào. Theo STOMP 1.2, nếu message được gửi bằng STOMP SEND, destination trong MESSAGE nên giống destination của SEND tương ứng. Một số luồng ứng dụng có thể định tuyến lại message, vì vậy hãy xem destination được server gửi về là nguồn thông tin cuối cùng cho frame đó.

### 2.2. STOMP không áp đặt ý nghĩa của destination

STOMP xem destination là một chuỗi opaque, tức giao thức không quy định cú pháp hoặc delivery semantics cụ thể. Server/broker quyết định chuỗi nào là queue, topic, exchange, routing key, user destination hoặc một kiểu địa chỉ riêng.

Các quy ước thường gặp:

| Destination | Quy ước phổ biến | Lưu ý |
|---|---|---|
| /topic/orders | Publish/subscribe, một message đến nhiều subscriber | Là quy ước tên phổ biến, không phải từ khóa bắt buộc của STOMP |
| /queue/orders | Point-to-point hoặc competing consumers | Semantics thực tế phụ thuộc broker |
| /app/orders.publish | Đích để Spring định tuyến đến @MessageMapping | Đây là quy ước application prefix của Spring |
| /user/queue/notifications | Đích theo người dùng trong Spring | Spring chuyển thành destination cụ thể theo user/session |

Không nên suy luận rằng mọi STOMP server đều xử lý /queue theo cùng một cách. Cần đọc tài liệu broker đang dùng. Spring simple broker cũng không phải một message broker đầy đủ: nó giữ subscription trong bộ nhớ ứng dụng và phát message theo destination đã cấu hình.

### 2.3. Destination trong Spring

Một cấu hình Spring STOMP phổ biến:

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
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Ba nhóm đường dẫn có nhiệm vụ khác nhau:

- /ws là URL HTTP/WebSocket endpoint để client mở kết nối.
- /app là prefix của STOMP destination được định tuyến đến controller.
- /topic và /queue là prefix được simple broker xử lý.

Ví dụ client gửi SEND đến /app/orders.publish. Spring bỏ prefix /app và tìm phương thức @MessageMapping("/orders.publish"). Controller có thể trả kết quả đến /topic/orders bằng @SendTo.

~~~java
@Controller
public class OrderController {

    @MessageMapping("/orders.publish")
    @SendTo("/topic/orders")
    public OrderEvent publish(OrderEvent event) {
        return event;
    }
}
~~~

Đường dẫn /app/orders.publish là destination trong STOMP frame. Nó không phải một HTTP POST URL và không làm phát sinh một HTTP request mới.

### 2.4. Destination là dữ liệu định tuyến, không phải quyền truy cập

Một client có thể tự gửi destination trong SEND hoặc SUBSCRIBE. Vì vậy, server phải kiểm tra user có quyền gửi đến hoặc subscribe destination đó hay không.

Không tin destination do client gửi chỉ vì nó có prefix hợp lệ. Ví dụ, /topic/admin-events có thể tồn tại nhưng không phải user nào cũng được subscribe. Authorization phải được kiểm tra theo Principal, tenant và chính sách nghiệp vụ.

## 3. Subscription id: định danh một đăng ký nhận message

### 3.1. Subscription là gì?

Một client gửi SUBSCRIBE để yêu cầu server đăng ký nhận message từ một destination. Server tạo một subscription gắn với STOMP connection và dùng subscription id để liên kết các MESSAGE hoặc UNSUBSCRIBE tiếp theo với đăng ký đó.

STOMP 1.2 yêu cầu SUBSCRIBE có hai header:

- destination: nơi client muốn nghe.
- id: định danh subscription.

Ví dụ:

~~~text
SUBSCRIBE
id:orders-view-1
destination:/topic/orders
ack:auto

<NUL>
~~~

Giá trị id do client đặt. Trong cùng một STOMP connection, các subscription khác nhau phải dùng ID khác nhau. Một connection có thể có nhiều subscription đến cùng một destination, miễn là mỗi subscription có ID riêng.

Ví dụ:

~~~text
SUBSCRIBE
id:orders-main
destination:/topic/orders

<NUL>

SUBSCRIBE
id:orders-audit
destination:/topic/orders

<NUL>
~~~

Client đang có hai đăng ký riêng cho cùng destination. Khi message được phát đến /topic/orders, cả hai subscription đều có thể nhận message. Vì vậy, một client có thể nhận hai bản giao nếu nó subscribe cùng destination nhiều lần.

### 3.2. Subscription id có phạm vi trong một connection

Subscription id không phải ID toàn hệ thống. STOMP 1.2 chỉ yêu cầu các subscription khác nhau trên cùng connection có ID khác nhau.

Ví dụ hai tab browser có hai WebSocket connection độc lập có thể cùng dùng id:orders-view-1. Điều đó không làm chúng xung đột vì subscription thuộc hai connection khác nhau.

Khi ghi log hoặc lưu trạng thái subscription, nên kết hợp subscription id với session id hoặc user/session context. Không chỉ lưu subscription id rồi giả định nó duy nhất trên toàn hệ thống.

### 3.3. MESSAGE trả lại subscription id bằng header subscription

Khi server gửi MESSAGE đến client, frame phải có header subscription. Giá trị này phải khớp với id của SUBSCRIBE đã nhận message.

Ví dụ:

~~~text
MESSAGE
subscription:orders-view-1
message-id:server-msg-9001
destination:/topic/orders
content-type:application/json

{"eventId":"evt-1001","orderId":"ORD-1001"}<NUL>
~~~

Header subscription cho biết bản MESSAGE này được giao thông qua đăng ký nào. Nếu client có hai subscription cùng nghe /topic/orders, subscription giúp client phân biệt bản giao thuộc subscription nào.

Subscription id không định danh nội dung message. Một subscription có thể nhận hàng nghìn message khác nhau; mỗi MESSAGE vẫn có message-id riêng.

### 3.4. Hủy subscription bằng UNSUBSCRIBE

Để hủy một đăng ký, client gửi UNSUBSCRIBE với id đã dùng trong SUBSCRIBE:

~~~text
UNSUBSCRIBE
id:orders-view-1

<NUL>
~~~

Server dùng ID này để tìm subscription cần xóa. Destination không thay thế được subscription id khi hủy đăng ký.

Nếu client hủy nhầm ID, server có thể báo lỗi hoặc không tìm được subscription tương ứng tùy implementation. Khi tạo nhiều subscription động, nên giữ đối tượng subscription hoặc ID trả về từ client library để hủy đúng đăng ký.

## 4. Message-id: định danh message server giao đến client

### 4.1. Message-id xuất hiện trong MESSAGE frame

STOMP 1.2 yêu cầu mỗi MESSAGE frame có:

- destination: destination của message.
- message-id: định danh duy nhất cho message đó.
- subscription: ID của subscription nhận message.

Ví dụ:

~~~text
MESSAGE
destination:/queue/orders
subscription:orders-worker-1
message-id:broker-message-73
content-type:application/json

{"eventId":"evt-1001","orderId":"ORD-1001"}<NUL>
~~~

message-id là định danh ở tầng giao thức do server/broker sử dụng khi giao message. Client nên xem nó là giá trị opaque: lưu lại nếu cần đối chiếu frame, nhưng không phân tích cấu trúc hoặc tự tạo quy tắc dựa trên phần bên trong.

STOMP không yêu cầu client đặt message-id trong SEND. SEND có destination và body; server/broker tạo MESSAGE frame khi giao message đến subscription và cung cấp message-id.

### 4.2. Message-id không phải business event id

Một sự kiện nghiệp vụ cần ID ổn định để theo dõi qua nhiều hệ thống, retry, log và lần xử lý lại. Ví dụ eventId = evt-1001 có thể được ứng dụng tạo trước khi publish và lưu cùng bản ghi outbox.

Message-id của STOMP phục vụ việc định danh message trong giao thức giao nhận. Không dùng nó thay cho eventId vì:

- Một event nghiệp vụ có thể được publish nhiều lần.
- Broker có thể tạo message-id mới khi message được phát hoặc giao lại.
- Message-id có semantics và phạm vi phụ thuộc server/broker.
- Client reconnect hoặc subscribe lại có thể nhận một MESSAGE frame mới cho cùng event nghiệp vụ.

Nếu cần deduplicate, hãy dùng business event id ổn định trong payload hoặc custom header. Ví dụ consumer lưu eventId đã xử lý vào bảng inbox với unique constraint.

### 4.3. Message-id khác Spring MessageHeaders.ID

Trong Spring Messaging, một Message có MessageHeaders.ID do Spring tạo để định danh object Message trong nội bộ framework. Đây là ID nội bộ của Spring Message.

STOMP message-id là native protocol header được encode vào MESSAGE frame. Hai giá trị có thể khác nhau và có vòng đời khác nhau. Khi cần đọc header STOMP, dùng StompHeaderAccessor.getMessageId() hoặc client frame.headers["message-id"]; không dùng MessageHeaders.getId() rồi giả định đó là STOMP message-id.

## 5. Bảng phân biệt các ID và header liên quan

Một số header có tên gần giống nhau nhưng có ý nghĩa riêng theo command.

| Header/giá trị | Xuất hiện ở frame | Ai tạo | Ý nghĩa |
|---|---|---|---|
| destination | SEND, SUBSCRIBE, MESSAGE | Client ở SEND/SUBSCRIBE; server ở MESSAGE | Địa chỉ định tuyến hoặc nơi nhận |
| id | SUBSCRIBE | Client | Subscription id |
| id | UNSUBSCRIBE | Client | Subscription cần hủy |
| subscription | MESSAGE | Server/broker | Subscription id nhận message |
| message-id | MESSAGE | Server/broker | Định danh message giao đến client |
| ack | MESSAGE khi cần explicit ACK | Server/broker | Token để ACK/NACK message |
| id | ACK/NACK trong STOMP 1.2 | Client | Giá trị phải khớp với ack token của MESSAGE |
| receipt | Frame client có yêu cầu receipt | Client | Token client yêu cầu server phản hồi |
| receipt-id | RECEIPT | Server | Echo giá trị receipt tương ứng |
| session | CONNECTED nếu server cung cấp | Server | Định danh STOMP session |
| eventId | Payload hoặc custom header | Ứng dụng | ID nghiệp vụ ổn định |
| correlationId | Payload hoặc custom header | Ứng dụng | Liên kết các message trong một luồng nghiệp vụ |
| MessageHeaders.ID | Spring Message nội bộ | Spring | Định danh object Message trong Spring |

Lưu ý: header id không có một ý nghĩa duy nhất cho mọi frame. Với SUBSCRIBE, nó là subscription id. Với UNSUBSCRIBE, nó trỏ đến subscription cần hủy. Với ACK/NACK trong STOMP 1.2, nó mang giá trị ack token của MESSAGE.

## 6. ACK token khác message-id

Đây là một trong những điểm dễ nhầm nhất khi làm việc với STOMP 1.2.

### 6.1. Ba acknowledgement mode

SUBSCRIBE có thể đặt header ack:

- auto: mặc định nếu không khai báo. Client không cần gửi ACK; server xem message đã được nhận khi gửi đến client.
- client: client phải ACK. ACK có semantics tích lũy, có thể xác nhận message được chỉ định cùng các message trước đó chưa được ACK.
- client-individual: ACK/NACK áp dụng độc lập cho từng message.

Ví dụ:

~~~text
SUBSCRIBE
id:orders-worker-1
destination:/queue/orders
ack:client-individual

<NUL>
~~~

Với client hoặc client-individual, MESSAGE frame phải có thêm header ack:

~~~text
MESSAGE
subscription:orders-worker-1
message-id:broker-message-73
ack:ack-token-73
destination:/queue/orders
content-type:application/json

{"eventId":"evt-1001","orderId":"ORD-1001"}<NUL>
~~~

### 6.2. ACK trong STOMP 1.2 dùng ack token

Để xác nhận message trên, client gửi:

~~~text
ACK
id:ack-token-73

<NUL>
~~~

Giá trị id của ACK phải bằng giá trị ack trong MESSAGE. Nó không phải message-id.

Đây là điểm khác biệt quan trọng giữa hai header:

- message-id nhận diện MESSAGE frame.
- ack là token được server dùng để liên kết MESSAGE với ACK/NACK.
- id trong ACK/NACK mang giá trị của ack token.

Nếu client gửi ACK với message-id thay vì ack token, broker có thể không xác định được message cần xác nhận.

### 6.3. NACK

Nếu client không xử lý được message, có thể gửi NACK với cùng cách liên kết:

~~~text
NACK
id:ack-token-73

<NUL>
~~~

Broker có thể redeliver, loại bỏ hoặc chuyển message sang dead-letter destination. Hành vi cụ thể phụ thuộc broker và cấu hình redelivery.

ACK/NACK không thay thế business idempotency. Nếu consumer đã cập nhật database nhưng mất kết nối trước khi ACK tới broker, message có thể được giao lại. Consumer cần xử lý eventId lặp một cách an toàn.

## 7. receipt và receipt-id không phải message-id

Client có thể yêu cầu server gửi RECEIPT sau khi xử lý một frame bằng cách thêm header receipt.

Ví dụ client yêu cầu receipt khi subscribe:

~~~text
SUBSCRIBE
id:orders-view-1
destination:/topic/orders
receipt:orders-sub-ready

<NUL>
~~~

Server phản hồi:

~~~text
RECEIPT
receipt-id:orders-sub-ready

<NUL>
~~~

receipt là token do client tạo. receipt-id là giá trị server trả lại để chỉ ra frame nào đã được xử lý.

Receipt xác nhận server đã xử lý frame tương ứng theo semantics của STOMP. Nó không chứng minh consumer cuối cùng đã xử lý xong một message nghiệp vụ. Ví dụ RECEIPT cho SEND không phải bằng chứng rằng tất cả subscriber đã nhận và ghi dữ liệu thành công.

Không dùng receipt-id làm business event id hoặc message-id. Mỗi loại phục vụ một điểm khác nhau trong vòng đời giao thức.

## 8. Luồng hoàn chỉnh từ SEND đến MESSAGE

Giả sử một client gửi event đến Spring và một client khác đã subscribe destination /topic/orders.

~~~mermaid
sequenceDiagram
    participant P as Producer client
    participant S as Spring STOMP
    participant B as Simple broker
    participant C as Consumer client

    C->>S: SUBSCRIBE id=orders-view-1, destination=/topic/orders
    S->>B: Đăng ký subscription
    B-->>C: RECEIPT receipt-id=orders-sub-ready (nếu được yêu cầu)
    P->>S: SEND destination=/app/orders.publish
    S->>S: @MessageMapping("/orders.publish")
    S->>B: Publish đến /topic/orders
    B-->>S: MESSAGE cho subscription phù hợp
    S-->>C: MESSAGE subscription=orders-view-1, message-id=server-msg-1
~~~

Luồng chi tiết:

1. Consumer client gửi SUBSCRIBE với destination và subscription id.
2. Spring giải mã STOMP frame và đưa message vào clientInboundChannel.
3. Spring định tuyến subscription đến broker.
4. Broker lưu đăng ký gắn với session và subscription id.
5. Producer gửi SEND đến /app/orders.publish.
6. Spring loại application prefix /app và gọi @MessageMapping("/orders.publish").
7. Controller xử lý event và gửi kết quả đến /topic/orders.
8. Broker tìm các subscription phù hợp.
9. Spring encode MESSAGE frame cho từng subscriber.
10. MESSAGE chứa destination, message-id và subscription; nếu cần explicit ACK thì có thêm ack token.

Một event có thể được phát đến nhiều subscription. Mỗi MESSAGE frame phải mang subscription id tương ứng với subscription nhận frame đó. Vì vậy, cùng một message nghiệp vụ có thể được client nhìn thấy qua nhiều subscription với các header subscription khác nhau.

## 9. Đọc header trong Spring bằng StompHeaderAccessor

Spring Framework cung cấp StompHeaderAccessor để truy cập STOMP command và header đã được giải mã.

Các method thường dùng:

| Method | Giá trị |
|---|---|
| getCommand() | STOMP command như SEND, SUBSCRIBE, MESSAGE |
| getDestination() | Destination đã được Spring ánh xạ |
| getSubscriptionId() | Subscription id; ánh xạ từ id của SUBSCRIBE/UNSUBSCRIBE hoặc subscription của MESSAGE |
| getMessageId() | Native STOMP message-id |
| getAck() | Native STOMP ack token |
| getFirstNativeHeader(name) | Giá trị đầu tiên của một native STOMP header |
| getSessionId() | Spring WebSocket/STOMP session id |

Điểm đặc biệt trong Spring là getSubscriptionId() chuẩn hóa header theo command:

- Với SUBSCRIBE hoặc UNSUBSCRIBE, Spring đọc native header id.
- Với MESSAGE, Spring đọc native header subscription.

Do đó, code server không phải tự kiểm tra hai tên header khác nhau để lấy subscription id.

### 9.1. Truy cập trong @MessageMapping

Ví dụ controller đọc destination và custom header trace-id:

~~~java
package com.example.websocket;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.stereotype.Controller;

@Controller
public class OrderController {

    @MessageMapping("/orders.publish")
    @SendTo("/topic/orders")
    public OrderEvent publish(
            @Payload OrderEvent event,
            StompHeaderAccessor accessor) {

        String destination = accessor.getDestination();
        String traceId = accessor.getFirstNativeHeader("trace-id");

        if (event.eventId() == null || event.eventId().isBlank()) {
            throw new IllegalArgumentException("eventId is required");
        }

        System.out.println(
            "destination=" + destination + ", traceId=" + traceId
        );

        return event;
    }
}
~~~

Đối với frame SEND gửi đến controller, destination thường là /app/orders.publish. Subscription id và message-id thường không có trên frame SEND vì đây không phải MESSAGE frame được server giao đến subscriber.

Không lấy message-id từ một SEND frame rồi giả định client đã tạo ID đó theo STOMP chuẩn. Nếu muốn theo dõi sự kiện do client gửi, hãy dùng eventId hoặc correlationId do ứng dụng định nghĩa.

### 9.2. Theo dõi SUBSCRIBE và UNSUBSCRIBE bằng ChannelInterceptor

ChannelInterceptor phù hợp để audit hoặc áp dụng chính sách cho từng STOMP frame sau khi Spring đã giải mã.

~~~java
package com.example.websocket;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;

public class SubscriptionAuditInterceptor implements ChannelInterceptor {

    private static final Logger log =
        LoggerFactory.getLogger(SubscriptionAuditInterceptor.class);

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        StompHeaderAccessor accessor =
            StompHeaderAccessor.wrap(message);

        StompCommand command = accessor.getCommand();

        if (StompCommand.SUBSCRIBE.equals(command)) {
            log.info(
                "SUBSCRIBE session={} destination={} subscriptionId={}",
                accessor.getSessionId(),
                accessor.getDestination(),
                accessor.getSubscriptionId()
            );
        }
        else if (StompCommand.UNSUBSCRIBE.equals(command)) {
            log.info(
                "UNSUBSCRIBE session={} subscriptionId={}",
                accessor.getSessionId(),
                accessor.getSubscriptionId()
            );
        }

        return message;
    }
}
~~~

Đăng ký interceptor trên inbound channel:

~~~java
@Override
public void configureClientInboundChannel(ChannelRegistration registration) {
    registration.interceptors(new SubscriptionAuditInterceptor());
}
~~~

Đây là ví dụ audit. Trong ứng dụng thực tế, có thể mở rộng interceptor để kiểm tra quyền subscribe theo destination, giới hạn số subscription của một session hoặc ghi nhận event lifecycle.

Không dùng subscription id làm căn cứ xác thực user. Nó do client gửi và chỉ định danh đăng ký trong connection hiện tại. Danh tính cần lấy từ Principal đã được Spring Security xác thực.

## 10. Ví dụ hoàn chỉnh với Spring Boot, Java 17 và STOMP.js

Ví dụ tạo một endpoint STOMP để publish order event. Client gửi đến /app/orders.publish; Spring xử lý bằng @MessageMapping và phát kết quả đến /topic/orders. Một client subscriber đọc destination, subscription và message-id từ MESSAGE frame.

Dự án dùng Java 17, Spring Boot 3.5.x và Spring Framework 6.2.x. Spring Boot quản lý các phiên bản Spring tương thích.

### 10.1. Cấu trúc dự án

~~~text
stomp-identifiers-demo/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/websocket/
        │   ├── StompIdentifiersApplication.java
        │   ├── StompConfig.java
        │   ├── OrderController.java
        │   ├── OrderEvent.java
        │   └── SubscriptionAuditInterceptor.java
        └── resources/
            └── application.properties
~~~

### 10.2. Maven dependencies

Tạo pom.xml:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>stomp-identifiers-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-websocket</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 10.3. Lớp khởi động

Tạo StompIdentifiersApplication.java:

~~~java
package com.example.websocket;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class StompIdentifiersApplication {

    public static void main(String[] args) {
        SpringApplication.run(StompIdentifiersApplication.class, args);
    }
}
~~~

### 10.4. Cấu hình endpoint và broker

Tạo StompConfig.java:

~~~java
package com.example.websocket;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.ChannelRegistration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class StompConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws")
            .setAllowedOrigins("http://localhost:3000");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }

    @Override
    public void configureClientInboundChannel(ChannelRegistration registration) {
        registration.interceptors(new SubscriptionAuditInterceptor());
    }
}
~~~

### 10.5. Payload nghiệp vụ

Tạo OrderEvent.java:

~~~java
package com.example.websocket;

public record OrderEvent(
    String eventId,
    String orderId,
    String status
) {
}
~~~

eventId là ID nghiệp vụ do ứng dụng quản lý. Nó được giữ trong payload để consumer có thể deduplicate hoặc đối chiếu log qua nhiều lần publish. Đây không phải STOMP message-id.

### 10.6. Controller xử lý SEND

Tạo OrderController.java:

~~~java
package com.example.websocket;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.stereotype.Controller;

@Controller
public class OrderController {

    @MessageMapping("/orders.publish")
    @SendTo("/topic/orders")
    public OrderEvent publish(
            @Payload OrderEvent event,
            StompHeaderAccessor accessor) {

        String traceId = accessor.getFirstNativeHeader("trace-id");

        if (event.eventId() == null || event.eventId().isBlank()) {
            throw new IllegalArgumentException("eventId is required");
        }

        System.out.println(
            "SEND destination=" + accessor.getDestination()
                + ", eventId=" + event.eventId()
                + ", traceId=" + traceId
        );

        return event;
    }
}
~~~

Khi client gửi đến /app/orders.publish, Spring gọi phương thức publish(). Giá trị trả về được gửi đến /topic/orders. Broker tạo MESSAGE frame cho từng subscription phù hợp; frame chứa destination, subscription và message-id.

### 10.7. Interceptor audit subscription

Tạo SubscriptionAuditInterceptor.java:

~~~java
package com.example.websocket;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;

public class SubscriptionAuditInterceptor implements ChannelInterceptor {

    private static final Logger log =
        LoggerFactory.getLogger(SubscriptionAuditInterceptor.class);

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        StompHeaderAccessor accessor =
            StompHeaderAccessor.wrap(message);

        if (StompCommand.SUBSCRIBE.equals(accessor.getCommand())) {
            log.info(
                "SUBSCRIBE session={} destination={} subscriptionId={}",
                accessor.getSessionId(),
                accessor.getDestination(),
                accessor.getSubscriptionId()
            );
        }

        if (StompCommand.UNSUBSCRIBE.equals(accessor.getCommand())) {
            log.info(
                "UNSUBSCRIBE session={} subscriptionId={}",
                accessor.getSessionId(),
                accessor.getSubscriptionId()
            );
        }

        return message;
    }
}
~~~

### 10.8. Cấu hình ứng dụng

Tạo application.properties:

~~~properties
spring.application.name=stomp-identifiers-demo
server.port=8080
~~~

### 10.9. Chạy ứng dụng

Từ thư mục dự án:

~~~bash
mvn spring-boot:run
~~~

Ứng dụng mở WebSocket/STOMP endpoint tại ws://localhost:8080/ws.

### 10.10. Client STOMP.js

Cài thư viện:

~~~bash
npm install @stomp/stompjs
~~~

Ví dụ client:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
    brokerURL: "ws://localhost:8080/ws",
    reconnectDelay: 5000,

    onConnect: () => {
        const subscription = client.subscribe(
            "/topic/orders",
            (frame) => {
                const destination = frame.headers.destination;
                const subscriptionId = frame.headers.subscription;
                const messageId = frame.headers["message-id"];
                const event = JSON.parse(frame.body);

                console.log({
                    destination,
                    subscriptionId,
                    messageId,
                    eventId: event.eventId
                });
            },
            {
                id: "orders-view-1",
                ack: "auto"
            }
        );

        console.log("active subscription:", subscription.id);

        client.publish({
            destination: "/app/orders.publish",
            headers: {
                "content-type": "application/json",
                "trace-id": "trace-1001"
            },
            body: JSON.stringify({
                eventId: "evt-1001",
                orderId: "ORD-1001",
                status: "CREATED"
            })
        });
    },

    onStompError: (frame) => {
        console.error("STOMP error:", frame.headers.message);
        console.error(frame.body);
    }
});

client.activate();
~~~

Trong callback:

- destination là destination mà broker giao message.
- subscriptionId là subscription đã nhận MESSAGE.
- messageId là STOMP message-id do server/broker cấp.
- eventId là định danh nghiệp vụ trong JSON body.

Các giá trị này được đọc từ ba nguồn khác nhau và không nên thay thế cho nhau.

### 10.11. Luồng frame tương ứng

Client gửi SUBSCRIBE:

~~~text
SUBSCRIBE
id:orders-view-1
destination:/topic/orders
ack:auto

<NUL>
~~~

Client gửi SEND:

~~~text
SEND
destination:/app/orders.publish
content-type:application/json
trace-id:trace-1001

{"eventId":"evt-1001","orderId":"ORD-1001","status":"CREATED"}<NUL>
~~~

Server giao MESSAGE:

~~~text
MESSAGE
subscription:orders-view-1
message-id:server-generated-id
destination:/topic/orders
content-type:application/json

{"eventId":"evt-1001","orderId":"ORD-1001","status":"CREATED"}<NUL>
~~~

server-generated-id chỉ là giá trị minh họa. ID thực tế do STOMP server/broker tạo và có thể có định dạng khác.

## 11. Destination, subscription và message-id trong các tình huống thực tế

### 11.1. Một connection subscribe nhiều destination

Client có thể đăng ký:

~~~text
SUBSCRIBE
id:orders-sub
destination:/topic/orders

<NUL>

SUBSCRIBE
id:payments-sub
destination:/topic/payments

<NUL>
~~~

Hai subscription có ID khác nhau. MESSAGE từ /topic/orders mang subscription:orders-sub; MESSAGE từ /topic/payments mang subscription:payments-sub.

### 11.2. Một connection subscribe cùng destination nhiều lần

Ví dụ:

~~~text
SUBSCRIBE
id:orders-panel
destination:/topic/orders

<NUL>

SUBSCRIBE
id:orders-audit
destination:/topic/orders

<NUL>
~~~

Cả hai subscription có thể nhận message từ /topic/orders. Nếu client không muốn xử lý trùng, hãy chỉ tạo một subscription hoặc kiểm soát subscription theo vòng đời component UI.

### 11.3. Client reconnect

Khi WebSocket/STOMP connection bị đóng rồi mở lại, client phải tạo lại các subscription cần thiết. Subscription id cũ có thể được dùng lại trên connection mới, nhưng subscription trước đó đã thuộc connection cũ và không còn là đăng ký đang hoạt động.

Không giả định message-id sẽ giống nhau sau reconnect hoặc redelivery. Nếu cần biết một business event đã được xử lý chưa, hãy dùng eventId ổn định và lưu trạng thái xử lý ở server.

### 11.4. Broker relay

Khi Spring dùng broker relay, STOMP message được chuyển đến broker bên ngoài. Destination semantics, message-id format, redelivery và acknowledgement behavior có thể phụ thuộc broker. Client vẫn phải tuân thủ cấu trúc STOMP frame, nhưng không nên phụ thuộc vào định dạng ID riêng của một broker nếu ứng dụng cần chuyển broker.

## 12. Bảo đảm tính đúng đắn và idempotency

Một message có thể được gửi lại do mất kết nối, broker redelivery hoặc client retry. Vì vậy, message-id của giao thức không phải là cơ chế chống xử lý trùng ở tầng nghiệp vụ.

Một thiết kế thường dùng:

1. Producer tạo eventId ổn định trước lần publish đầu tiên.
2. Producer đưa eventId vào payload hoặc custom native header.
3. Consumer nhận message và kiểm tra eventId đã xử lý hay chưa.
4. Nếu chưa xử lý, consumer thực hiện nghiệp vụ và ghi eventId vào bảng inbox hoặc kho dedup trong cùng transaction phù hợp.
5. Nếu eventId đã tồn tại, consumer bỏ qua tác dụng phụ và xác nhận message theo acknowledgement mode.

Ví dụ payload:

~~~json
{
  "eventId": "evt-1001",
  "orderId": "ORD-1001",
  "status": "CREATED"
}
~~~

eventId phải được tạo bởi ứng dụng và ổn định qua retry. Không tạo eventId mới mỗi lần retry nếu muốn deduplicate cùng một sự kiện.

correlationId có mục đích khác: liên kết request, response hoặc các bước trong một workflow. Có thể dùng eventId để deduplicate và correlationId để trace luồng xử lý; một hệ thống có thể cần cả hai.

## 13. Bảo mật destination và ID

- Không xem subscription id là danh tính user. Client có thể tự chọn giá trị này.
- Không cho client subscribe destination nhạy cảm nếu chưa kiểm tra quyền.
- Kiểm tra quyền SEND và SUBSCRIBE riêng biệt; quyền gửi không đồng nghĩa quyền đọc.
- Không dùng message-id làm access token hoặc secret.
- Không dùng eventId do client gửi làm bằng chứng user đã được xác thực.
- Không cho client tự khai báo userId rồi dùng giá trị đó làm chủ sở hữu subscription.
- Giới hạn số subscription trên mỗi connection để tránh tiêu thụ tài nguyên quá mức.
- Giới hạn kích thước frame, số header và tần suất SEND theo chính sách ứng dụng.
- Ghi log destination, session id và subscription id khi cần audit; tránh log payload hoặc token nhạy cảm.
- Khi dùng broker relay, cấu hình quyền destination và credential riêng cho client/system connection.

Destination và ID giúp định tuyến, tương quan và quản lý vòng đời. Chúng không thay thế authentication hoặc authorization.

## 14. Chẩn đoán lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| SUBSCRIBE bị ERROR | Thiếu destination hoặc id, destination không hợp lệ | Kiểm tra frame SUBSCRIBE và broker destination |
| Hai subscription cùng connection bị xung đột | Dùng trùng id | Gán ID khác nhau cho từng subscription |
| MESSAGE không có subscription mong đợi | Client subscribe nhầm destination hoặc đăng ký đã bị hủy | Kiểm tra SUBSCRIBE, UNSUBSCRIBE và MESSAGE.subscription |
| Client không nhận MESSAGE | Chưa subscribe, sai destination hoặc broker không route | So sánh SEND.destination, SUBSCRIBE.destination và MESSAGE.destination |
| Client hủy nhầm đăng ký | Dùng destination thay cho subscription id | UNSUBSCRIBE phải mang id của SUBSCRIBE |
| ACK bị từ chối hoặc không xác nhận | Dùng message-id thay cho ack token trong STOMP 1.2 | So sánh ACK.id với MESSAGE.ack |
| Message bị xử lý lặp | Redelivery hoặc retry; dùng message-id làm dedup key | Dùng eventId nghiệp vụ ổn định |
| Không tìm thấy message-id ở SEND | Client đang tìm header chỉ bắt buộc trong MESSAGE | Kiểm tra MESSAGE frame phía nhận |
| Receipt không chứng minh xử lý nghiệp vụ thành công | Receipt chỉ xác nhận server đã xử lý frame | Dùng business acknowledgement riêng nếu cần |
| Client nhận message hai lần | Có hai subscription cùng destination hoặc nhiều đường phát | Kiểm tra subscription id và routing |
| Log không khớp native header | Nhầm Spring internal header với STOMP native header | Dùng StompHeaderAccessor và getFirstNativeHeader |

## 15. Kiểm thử STOMP identifier end-to-end

Một bài kiểm thử nên xác minh các bước sau:

1. Mở một STOMP connection.
2. Subscribe hai lần đến cùng destination với hai ID khác nhau.
3. Xác nhận MESSAGE từ mỗi subscription có header subscription tương ứng.
4. Kiểm tra MESSAGE có destination và message-id.
5. Nếu dùng ack:client-individual, xác nhận MESSAGE có ack token.
6. Gửi ACK với id bằng giá trị ack, không dùng message-id.
7. Gửi UNSUBSCRIBE với id chính xác và xác nhận subscription đó ngừng nhận message.
8. Subscribe với receipt và kiểm tra receipt-id khớp receipt đã gửi.
9. Reconnect rồi đăng ký lại subscription.
10. Publish lại cùng eventId và xác minh consumer deduplicate đúng theo quy tắc nghiệp vụ.

Khi dùng Spring, có thể kiểm thử controller riêng nhưng vẫn cần một integration test với STOMP client để xác minh destination mapping, subscription lifecycle, message-id và ACK/receipt trên wire.

## 16. Lỗi tư duy phổ biến

- **Cho rằng destination là ID của message**: destination là địa chỉ định tuyến, một destination chứa nhiều message.
- **Cho rằng subscription id là destination**: destination cho biết nơi nghe; subscription id phân biệt từng đăng ký.
- **Cho rằng subscription id phải duy nhất toàn hệ thống**: STOMP 1.2 yêu cầu duy nhất trong cùng connection.
- **Cho rằng message-id do client gửi trong SEND**: MESSAGE frame do server giao mới bắt buộc có message-id.
- **Dùng message-id làm eventId**: hai ID có vòng đời và mục đích khác nhau.
- **Dùng id của SUBSCRIBE để ACK**: ACK trong STOMP 1.2 cần id bằng giá trị ack của MESSAGE.
- **Dùng message-id để ACK**: message-id và ack token là hai header riêng.
- **Dùng receipt-id để deduplicate business event**: receipt chỉ tương quan frame yêu cầu receipt.
- **Cho rằng /topic và /queue có semantics giống nhau ở mọi broker**: STOMP để server quyết định semantics của destination.
- **Dùng subscription id để xác thực user**: đây là giá trị do client đặt, không phải danh tính đáng tin cậy.
- **Cho rằng reconnect giữ subscription cũ**: connection mới cần tạo lại các subscription.
- **Nhầm MessageHeaders.ID với STOMP message-id**: Spring internal ID không phải native protocol header.

## 17. Checklist triển khai

- [ ] Chọn destination naming convention rõ ràng cho application và broker.
- [ ] Xác định destination nào được phép SEND và destination nào được phép SUBSCRIBE.
- [ ] Gán subscription id riêng cho từng SUBSCRIBE trong cùng connection.
- [ ] Lưu subscription id để UNSUBSCRIBE đúng đăng ký.
- [ ] Đọc subscription từ MESSAGE.subscription.
- [ ] Đọc message-id từ MESSAGE và xem đó là ID giao thức opaque.
- [ ] Chọn ack mode phù hợp với yêu cầu delivery.
- [ ] Với STOMP 1.2 explicit ACK, dùng MESSAGE.ack làm ACK.id.
- [ ] Dùng receipt/receipt-id cho xác nhận server xử lý frame khi cần.
- [ ] Tạo eventId ổn định cho nghiệp vụ và deduplication.
- [ ] Dùng correlationId để trace request/workflow nếu cần.
- [ ] Dùng StompHeaderAccessor để đọc destination, subscription id và message-id.
- [ ] Không dùng ID do client gửi để xác thực hoặc phân quyền.
- [ ] Kiểm thử nhiều subscription trên cùng connection.
- [ ] Kiểm thử reconnect, redelivery, ACK/NACK và receipt.
- [ ] Xác minh destination semantics theo broker thực tế.

## 18. Tổng kết

Destination trả lời câu hỏi message được gửi đến đâu hoặc client muốn nghe ở đâu. Subscription id định danh một đăng ký nhận message trong một STOMP connection. Message-id định danh message mà server giao đến client trong MESSAGE frame.

Trong STOMP 1.2, SUBSCRIBE dùng id để định danh subscription; MESSAGE trả lại ID đó trong header subscription và đồng thời có message-id riêng. Khi bật explicit acknowledgement, MESSAGE còn có ack token; client phải dùng token đó làm header id của ACK/NACK. receipt và receipt-id là một cặp khác để xác nhận server đã xử lý frame yêu cầu receipt.

Trong Spring, StompHeaderAccessor cung cấp getDestination(), getSubscriptionId(), getMessageId(), getAck() và getFirstNativeHeader() để đọc các giá trị này. Hãy giữ business event id và correlation id riêng trong payload hoặc custom header để deduplicate và trace nghiệp vụ qua retry, reconnect và broker khác nhau.

## Tài liệu tham khảo

- STOMP Protocol Specification 1.2 — SEND, SUBSCRIBE, subscription id, ACK/NACK, MESSAGE and RECEIPT: https://stomp.github.io/stomp-specification-1.2.html
- Spring Framework 6.2 — Flow of Messages: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/message-flow.html
- Spring Framework 6.2 — Annotated Controllers: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/handle-annotations.html
- Spring Framework 6.2.14 — StompHeaderAccessor Javadoc: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/messaging/simp/stomp/StompHeaderAccessor.html
- Spring Framework 6.2.3 — SimpMessageHeaderAccessor Javadoc: https://docs.spring.io/spring-framework/docs/6.2.3/javadoc-api/org/springframework/messaging/simp/SimpMessageHeaderAccessor.html
- Spring Framework 6.2 — STOMP overview: https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp.html