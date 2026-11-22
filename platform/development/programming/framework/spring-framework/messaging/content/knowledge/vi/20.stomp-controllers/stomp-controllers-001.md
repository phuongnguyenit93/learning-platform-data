# @Controller và ánh xạ thông điệp bằng @MessageMapping

## Mục tiêu

Trong Spring Framework, ứng dụng dùng WebSocket kết hợp STOMP có thể nhận thông điệp từ trình duyệt và định tuyến thông điệp đến các phương thức Java. **@Controller** đánh dấu bean xử lý; **@MessageMapping** ánh xạ destination của STOMP đến phương thức tương ứng.

Sau bài này, bạn có thể phân biệt xử lý STOMP với HTTP, cấu hình endpoint và broker, nhận payload/header/destination variable, phát kết quả đến topic chung hoặc người dùng cụ thể, và chẩn đoán lỗi định tuyến.

## 1. Vị trí của controller trong luồng STOMP

WebSocket cung cấp kết nối hai chiều lâu dài. STOMP là giao thức thông điệp chạy trên kết nối đó, với các frame như CONNECT, SEND, SUBSCRIBE và MESSAGE. Spring chuyển frame STOMP thành đối tượng Message rồi đưa vào hệ thống Spring Messaging.

Trong cấu hình phổ biến, destination được chia thành hai nhóm:

| Nhóm destination | Ví dụ | Thành phần xử lý |
| --- | --- | --- |
| Application | /app/chat.send | Controller có @MessageMapping |
| Broker | /topic/chat, /queue/alerts | Message broker và các subscription |

Application prefix giúp Spring phân biệt thông điệp cần gọi logic ứng dụng với thông điệp broker có thể phân phối trực tiếp. Prefix này được cấu hình bằng setApplicationDestinationPrefixes("/app"). Broker prefix được cấu hình bằng enableSimpleBroker("/topic", "/queue") hoặc bằng broker relay.

Luồng xử lý điển hình:

1. Trình duyệt mở kết nối WebSocket đến endpoint /ws và thương lượng STOMP.
2. Client gửi SUBSCRIBE đến /topic/chat; broker ghi nhận subscription.
3. Client gửi SEND đến /app/chat.send.
4. Spring nhận ra prefix /app, bỏ prefix này khi tìm mapping và gọi phương thức có @MessageMapping("/chat.send").
5. Spring chuyển payload, chẳng hạn JSON, thành đối tượng Java rồi truyền vào phương thức.
6. Giá trị trả về được chuyển thành thông điệp gửi vào broker channel. Broker phân phối thông điệp đến các client đã subscribe destination phù hợp.
7. Client nhận frame MESSAGE và đọc payload.

Client thường gửi đến /app/... để yêu cầu ứng dụng xử lý, còn subscribe /topic/... hoặc /queue/... để nhận thông điệp từ broker.

## 2. @Controller và @MessageMapping

**@Controller** là stereotype của Spring, giúp component scanning phát hiện controller như một bean. Trong ngữ cảnh STOMP, các phương thức được đánh dấu **@MessageMapping**, **@SubscribeMapping** hoặc **@MessageExceptionHandler** có thể xử lý các loại thông điệp tương ứng.

**@MessageMapping** định tuyến dựa trên destination của frame. Annotation có thể đặt ở cấp lớp hoặc cấp phương thức:

~~~java
@Controller
@MessageMapping("/orders")
public class OrderController {

    @MessageMapping("/created")
    public void handleCreated(OrderCreated event) {
        // Xử lý thông điệp gửi đến /app/orders/created
    }
}
~~~

Với application prefix /app, destination /app/orders/created khớp mapping cấp lớp /orders kết hợp mapping cấp phương thức /created. Mapping mặc định dùng mẫu đường dẫn kiểu Ant và hỗ trợ biến như /rooms/{roomId}/send. Có thể lấy biến bằng **@DestinationVariable**.

**@MessageMapping** không phải annotation ánh xạ HTTP. **@RequestMapping**, **@PostMapping** và các biến thể xử lý request HTTP; **@MessageMapping** xử lý message destination trong tầng Spring Messaging. Một lớp @Controller có thể đồng thời có handler HTTP và handler STOMP nếu ứng dụng có cấu hình tương ứng.

## 3. Các tham số mà phương thức có thể nhận

Spring hỗ trợ nhiều kiểu chữ ký. Chọn đúng tham số giúp phương thức chỉ nhận dữ liệu mà nó cần.

| Tham số | Công dụng |
| --- | --- |
| @Payload | Lấy payload; Spring chuyển đổi từ định dạng thông điệp, ví dụ JSON, sang kiểu Java. Nếu không ghi annotation, tham số chưa được khớp với loại khác thường được xem là payload. |
| @Header("name") | Lấy một header cụ thể và chuyển đổi kiểu nếu cần. |
| @Headers Map<String, Object> | Lấy toàn bộ header dưới dạng Map. |
| Message<?> | Truy cập cả payload và header của message. |
| MessageHeaders, SimpMessageHeaderAccessor, StompHeaderAccessor | Đọc header qua API có kiểu; accessor phù hợp khi cần session id, destination hoặc thông tin STOMP. |
| @DestinationVariable | Lấy biến được trích từ destination, ví dụ roomId trong /rooms/{roomId}/send. |
| Principal | Lấy người dùng đã được xác thực tại thời điểm WebSocket handshake, nếu ứng dụng có xác thực. |

Ví dụ nhận payload và một header:

~~~java
@MessageMapping("/chat.send")
public void send(
        @Payload ChatMessage message,
        @Header("simpSessionId") String sessionId) {
    // Xử lý message; sessionId nhận diện phiên WebSocket hiện tại
}
~~~

Không dùng **@RequestBody**, **@PathVariable** hay **@RequestParam** để thay thế các tham số dành cho message handler. Đó là các cơ chế gắn với request HTTP.

Payload có thể được kiểm tra tự động bằng Jakarta Validation khi tham số được đánh dấu **@Valid** hoặc **@Validated**. Ứng dụng cần có validation provider, chẳng hạn dependency spring-boot-starter-validation khi dùng Spring Boot.

## 4. Giá trị trả về và destination đầu ra

Khi phương thức @MessageMapping trả về một giá trị, Spring dùng MessageConverter phù hợp để chuyển giá trị đó thành payload của message gửi đến broker channel. Với cấu hình application prefix /app, destination đầu vào /app/greeting mặc định được ánh xạ đầu ra thành /topic/greeting.

Có thể ghi rõ destination bằng **@SendTo**:

~~~java
@MessageMapping("/chat.send")
@SendTo("/topic/chat")
public ChatMessage send(@Payload ChatMessage message) {
    return message;
}
~~~

Các subscriber của /topic/chat nhận cùng thông điệp. **@SendTo** cũng có thể chỉ định nhiều destination khi cần phát cùng kết quả đến nhiều nhóm subscriber.

Để gửi phản hồi riêng cho người dùng đã gửi message, dùng **@SendToUser**:

~~~java
@MessageMapping("/profile.refresh")
@SendToUser("/queue/profile")
public ProfileView refresh(Principal principal) {
    return profileService.load(principal.getName());
}
~~~

Client tương ứng subscribe /user/queue/profile. Prefix /user được Spring dùng để phân giải destination riêng theo người dùng. Mặc định, nếu một người dùng có nhiều session, các session phù hợp đều có thể nhận thông điệp. Đặt broadcast = false trên @SendToUser khi chỉ muốn gửi về session đã phát sinh message.

Khi cần chọn destination động, gửi thông điệp từ service hoặc chủ động gửi nhiều message, inject **SimpMessagingTemplate** và gọi convertAndSend(destination, payload). Cách này hữu ích khi destination phụ thuộc vào room id hoặc khi một sự kiện nghiệp vụ phát sinh ngoài phương thức controller.

Nếu phương thức không cần phát phản hồi, có thể trả về void và gửi qua SimpMessagingTemplate khi cần. Phương thức cũng có thể trả về kiểu bất đồng bộ như CompletableFuture hoặc CompletionStage.

## 5. Cấu hình STOMP tối thiểu

Ví dụ dưới đây dùng Spring Boot để khởi động ứng dụng; các annotation và API xử lý message là của Spring Framework. Trong một dự án Spring Boot, thêm dependency WebSocket và dependency validation nếu dùng @Valid. Để phiên bản dependency do Spring Boot BOM quản lý.

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-websocket</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
</dependencies>
~~~

Lớp khởi động:

~~~java
package com.example.messaging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MessagingApplication {

    public static void main(String[] args) {
        SpringApplication.run(MessagingApplication.class, args);
    }
}
~~~

Cấu hình endpoint, application prefix và broker:

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
    }
}
~~~

Ý nghĩa:

- **@EnableWebSocketMessageBroker** bật hạ tầng WebSocket/STOMP có message broker.
- **addEndpoint("/ws")** đăng ký endpoint HTTP handshake để client mở kết nối WebSocket.
- **setApplicationDestinationPrefixes("/app")** dành destination bắt đầu bằng /app cho controller.
- **enableSimpleBroker("/topic", "/queue")** bật simple broker trong bộ nhớ để phân phối thông điệp đến subscriber.

Simple broker phù hợp cho ví dụ và hệ thống nhỏ. Nó không phải broker lưu trữ bền vững hoặc broker phân tán cho nhiều node. Khi cần broker chuyên dụng, có thể cấu hình STOMP broker relay đến hệ thống như RabbitMQ hoặc ActiveMQ.

## 6. Ví dụ controller hoàn chỉnh

DTO dùng Java record, phù hợp Java 17 trở lên:

~~~java
package com.example.messaging;

import jakarta.validation.constraints.NotBlank;

public record ChatMessage(
        @NotBlank String sender,
        @NotBlank String text
) {
}
~~~

Controller nhận JSON, kiểm tra payload và phát kết quả đến topic:

~~~java
package com.example.messaging;

import jakarta.validation.Valid;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.simp.annotation.SendTo;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage send(@Valid @Payload ChatMessage message) {
        return message;
    }
}
~~~

Khi client gửi JSON đến /app/chat.send, Spring chuyển payload thành ChatMessage, chạy validation rồi gọi send. Giá trị trả về được gửi đến /topic/chat. Các client đã subscribe topic này nhận payload JSON tương ứng nếu JSON message converter được cấu hình và có mặt trên classpath. Spring Boot thường cấu hình converter JSON khi Jackson có trong ứng dụng.

Trong ví dụ học tập, sender nằm trong payload để dễ quan sát. Trong ứng dụng thật, không nên tin danh tính do client tự khai báo. Hãy lấy tên người dùng từ Principal đã xác thực và kiểm tra quyền truy cập room trước khi phát thông điệp.

## 7. Client gửi và nhận STOMP

Cài STOMP client cho JavaScript:

~~~bash
npm install @stomp/stompjs
~~~

Ví dụ client dùng WebSocket trực tiếp:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
  brokerURL: "ws://localhost:8080/ws",
  reconnectDelay: 5000
});

client.onConnect = () => {
  client.subscribe("/topic/chat", (frame) => {
    const message = JSON.parse(frame.body);
    console.log(message.sender, message.text);
  });

  client.publish({
    destination: "/app/chat.send",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({
      sender: "An",
      text: "Xin chào mọi người"
    })
  });
};

client.activate();
~~~

Chạy ứng dụng bằng **mvn spring-boot:run**, sau đó mở client. Khi kết nối thành công, client subscribe /topic/chat rồi publish đến /app/chat.send. Mỗi client đang subscribe topic sẽ nhận một message có sender và text tương ứng.

Hai destination có vai trò khác nhau: /app/chat.send gọi phương thức Java; /topic/chat nhận dữ liệu được broker phát đi. Nếu client chỉ publish mà không subscribe, server vẫn có thể xử lý message nhưng client đó sẽ không nhận bản broadcast qua topic.

## 8. Destination variable và gửi đến room cụ thể

Khi destination có biến, dùng **@DestinationVariable** để lấy giá trị. Ví dụ sau kết hợp controller mapping cấp lớp với destination động:

~~~java
package com.example.messaging;

import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Controller;

@Controller
@MessageMapping("/rooms")
public class RoomController {

    private final SimpMessagingTemplate messagingTemplate;

    public RoomController(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    @MessageMapping("/{roomId}/send")
    public void send(
            @DestinationVariable String roomId,
            @Payload ChatMessage message) {

        messagingTemplate.convertAndSend(
                "/topic/rooms/" + roomId,
                message
        );
    }
}
~~~

Client gửi đến /app/rooms/engineering/send sẽ làm roomId nhận giá trị engineering. Controller phát message đến /topic/rooms/engineering; client muốn nhận nội dung phòng này phải subscribe đúng destination. Trước khi gửi, ứng dụng cần kiểm tra người gửi có quyền tham gia phòng tương ứng.

## 9. Một số annotation liên quan

### @SubscribeMapping

**@SubscribeMapping** xử lý frame SUBSCRIBE thay vì frame SEND. Nếu không có @SendTo hoặc @SendToUser, giá trị trả về mặc định được gửi trực tiếp đến client vừa subscribe, không đi qua broker để broadcast. Cách này hữu ích cho yêu cầu lấy dữ liệu khởi tạo một lần, chẳng hạn lịch sử gần đây khi màn hình mở.

~~~java
@Controller
public class ChatHistoryController {

    @SubscribeMapping("/chat.history")
    public List<ChatMessage> history() {
        return chatService.latestMessages();
    }
}
~~~

Client subscribe /app/chat.history để nhận phản hồi ban đầu. Với cập nhật lặp lại, hãy subscribe destination broker như /topic/chat.

### @MessageExceptionHandler

**@MessageExceptionHandler** xử lý ngoại lệ phát sinh trong các phương thức message handler. Có thể đặt trong controller để xử lý ngoại lệ của controller đó, hoặc dùng **@ControllerAdvice** cho xử lý dùng chung. Handler có thể trả về payload và dùng **@SendToUser("/queue/errors")** để gửi lỗi cho người dùng liên quan. Nên trả thông báo có thể hiển thị cho người dùng, không đưa stack trace hoặc chi tiết nội bộ ra client.

## 10. Bảo mật và vận hành

- **Xác thực:** xác thực người dùng tại handshake hoặc tích hợp cơ chế xác thực của ứng dụng. Dùng Principal trong controller để lấy danh tính đã xác thực.
- **Phân quyền message:** giới hạn ai được SEND đến từng application destination và ai được SUBSCRIBE từng topic/queue. @MessageMapping chỉ định tuyến, không tự tạo quy tắc phân quyền.
- **Không tin payload:** không dùng trường sender, role hoặc userId do client gửi làm bằng chứng danh tính. Tự lấy danh tính từ security context và kiểm tra quyền truy cập room hoặc tài nguyên.
- **Kiểm tra dữ liệu:** dùng validation cho payload, giới hạn kích thước thông điệp, kiểm tra dữ liệu đầu vào và xử lý lỗi có kiểm soát.
- **Origin:** chỉ cho phép origin của frontend được tin cậy trong cấu hình WebSocket. Không mở wildcard tùy tiện khi ứng dụng dùng cookie hoặc thông tin xác thực.
- **Broker:** simple broker giữ subscription trong bộ nhớ của một tiến trình. Khi cần mở rộng nhiều node, định tuyến qua broker relay và thiết kế lại việc phân phối, reconnect, retry phù hợp.
- **Quan sát:** ghi log destination, loại sự kiện, mã tương quan và kết quả xử lý; tránh ghi token, cookie hoặc payload nhạy cảm.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra |
| --- | --- | --- |
| Phương thức controller không được gọi | Client gửi sai application prefix hoặc sai mapping | So sánh destination gửi đi với prefix /app, mapping cấp lớp và mapping cấp phương thức. |
| Không nhận được broadcast | Client chưa subscribe hoặc subscribe sai destination | Kiểm tra /topic/... hoặc /queue/... và destination trong @SendTo. |
| Kết nối WebSocket thất bại | Sai endpoint, origin không được phép hoặc handshake bị từ chối | Kiểm tra URL /ws, HTTP handshake và cấu hình origin/security. |
| Payload không chuyển thành DTO | JSON sai định dạng, thiếu content type hoặc thiếu JSON converter | Kiểm tra body, header content-type: application/json và Jackson trên classpath. |
| Validation từ chối message | Payload thiếu trường bắt buộc hoặc sai định dạng | Kiểm tra constraint trên DTO và cách trả lỗi cho client. |
| Client nhận dữ liệu của phòng khác | Quyền truy cập topic/room chưa được kiểm tra | Xác thực người dùng và kiểm tra quyền cả ở SEND lẫn SUBSCRIBE. |
| Controller không được phát hiện | Package controller nằm ngoài vùng component scan | Đặt controller dưới package của lớp @SpringBootApplication hoặc cấu hình component scan rõ ràng. |

## 12. Cách kiểm thử

Nên kiểm thử hai lớp hành vi:

1. **Unit test:** gọi trực tiếp phương thức controller với payload hợp lệ/không hợp lệ để kiểm tra logic nghiệp vụ và kết quả.
2. **Integration test STOMP:** khởi chạy ứng dụng, kết nối đến endpoint WebSocket, subscribe topic, gửi frame SEND đến application destination và xác nhận nhận được frame MESSAGE với payload mong đợi.

Unit test controller không chứng minh prefix, handshake, broker hoặc subscription được cấu hình đúng. Các lỗi định tuyến thường chỉ xuất hiện ở integration test. Khi debug, kiểm tra lần lượt kết nối, frame CONNECT, SUBSCRIBE, SEND, destination sau khi bỏ application prefix và frame MESSAGE trả về.

## 13. Ghi nhớ

- **@Controller** đánh dấu bean xử lý; **@MessageMapping** nối STOMP destination với phương thức Java.
- **/app** thường dành cho thông điệp đi vào ứng dụng; **/topic** và **/queue** thường dành cho subscription broker.
- **@Payload** nhận dữ liệu đã được chuyển đổi; **@Header** và **@DestinationVariable** lấy metadata và biến destination.
- **@SendTo** phát kết quả đến destination broker; **@SendToUser** gửi đến người dùng cụ thể.
- **SimpMessagingTemplate** phù hợp với destination động hoặc gửi message từ thành phần khác.
- Xác thực, phân quyền, validation và kiểm soát origin phải được thiết kế cùng luồng message.

## Tài liệu tham khảo

- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html)
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework — User Destinations](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html)
- [Spring Framework — Sending Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-send.html)
