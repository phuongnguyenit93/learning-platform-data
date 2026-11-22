# Ánh xạ cấp lớp, cấp phương thức và mẫu đường dẫn trong STOMP Controller

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt endpoint WebSocket, STOMP destination, application destination prefix và broker destination prefix.
- Giải thích cách Spring ghép mẫu ở cấp lớp với mẫu ở cấp phương thức để tìm handler.
- Đọc và viết mẫu đường dẫn Ant-style: ký tự đại diện, biến đường dẫn và biểu thức chính quy.
- Lấy biến từ destination bằng `@DestinationVariable` và nhận payload đã được chuyển đổi.
- Chọn đúng destination khi client gửi lệnh và khi client đăng ký nhận kết quả.

Bài tập trung vào STOMP over WebSocket với controller được đánh dấu `@Controller` trong Spring Framework. Mặc định, Spring dùng `AntPathMatcher` với dấu gạch chéo `/` làm dấu phân cách destination.

## 1. Phân biệt endpoint và destination

Một ứng dụng STOMP thường có ít nhất ba loại đường dẫn khác nhau:

| Thành phần | Ví dụ | Vai trò |
|---|---|---|
| WebSocket endpoint | `/ws` | Địa chỉ HTTP dùng để bắt tay và mở kết nối WebSocket |
| Application destination prefix | `/app` | Prefix để định tuyến message gửi từ client đến controller của ứng dụng |
| Broker destination prefix | `/topic`, `/queue` | Prefix để định tuyến subscription và message qua message broker |

Cấu hình minh họa:

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

Các import chính:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;
~~~

Với cấu hình trên:

- Client mở kết nối WebSocket tới endpoint `/ws`.
- Client gửi STOMP `SEND` tới destination bắt đầu bằng `/app` để yêu cầu ứng dụng xử lý.
- Spring bỏ application prefix `/app` trước khi so khớp phần destination còn lại với các mapping trong controller.
- Client thường gửi `SUBSCRIBE` tới destination bắt đầu bằng `/topic` hoặc `/queue`; broker quản lý subscription đó.

**Endpoint không phải destination.** `/ws` dùng để mở kết nối. `/app/chat/send` và `/topic/chat/events` là các destination trong STOMP frame. Không đưa `/ws` vào `@MessageMapping`.

## 2. Ghép mapping cấp lớp và cấp phương thức

`@MessageMapping` có thể đặt ở cấp lớp hoặc cấp phương thức:

- Mapping cấp lớp mô tả phần đường dẫn dùng chung cho các handler trong controller.
- Mapping cấp phương thức mô tả phần đường dẫn riêng của một handler.
- Spring kết hợp hai phần để tạo mapping đầy đủ cho phương thức.

Ví dụ:

~~~java
@Controller
@MessageMapping("/chat")
public class ChatController {

    @MessageMapping("/send")
    public void send() {
        // Xử lý message gửi tới /chat/send
    }

    @MessageMapping("/rooms/{roomId}/messages")
    public void sendToRoom() {
        // Xử lý message gửi tới /chat/rooms/{roomId}/messages
    }
}
~~~

Các mapping đầy đủ:

| Mapping cấp lớp | Mapping cấp phương thức | Mapping kết hợp |
|---|---|---|
| `/chat` | `/send` | `/chat/send` |
| `/chat` | `/rooms/{roomId}/messages` | `/chat/rooms/{roomId}/messages` |

Với application prefix là `/app`, client gửi tới `/app/chat/send` hoặc `/app/chat/rooms/42/messages`. Sau khi Spring bỏ `/app`, phần còn lại được so khớp với mapping kết hợp.

Lưu ý:

1. Mapping cấp lớp là phần dùng chung, không tự biến mọi phương thức trong lớp thành handler. Phương thức xử lý message vẫn cần annotation mapping phù hợp như `@MessageMapping` hoặc `@SubscribeMapping`.
2. Mapping cấp lớp có thể chứa biến, ví dụ `/tenants/{tenantId}/chat`. Handler có thể nhận biến đó bằng `@DestinationVariable`.
3. Mapping cấp lớp `@MessageMapping` cũng có thể kết hợp với mapping cấp phương thức `@SubscribeMapping`.
4. Không thêm `/app` vào mapping của controller khi `/app` đã được cấu hình bằng `setApplicationDestinationPrefixes`.

## 3. Ví dụ đầy đủ: controller theo tenant và room

Giả sử ứng dụng có destination dạng:

`/app/tenants/{tenantId}/chat/rooms/{roomId}/messages`

Ta muốn phần tenant dùng chung cho cả controller, còn mỗi handler khai báo phần đường dẫn riêng.

~~~java
import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

@Controller
@MessageMapping("/tenants/{tenantId}/chat")
public class ChatController {

    @MessageMapping("/rooms/{roomId}/messages")
    public ChatMessageEvent send(
            @DestinationVariable("tenantId") String tenantId,
            @DestinationVariable("roomId") Long roomId,
            @Payload ChatMessageRequest request) {

        return new ChatMessageEvent(tenantId, roomId, request.text());
    }

    public record ChatMessageRequest(String text) {}

    public record ChatMessageEvent(
            String tenantId,
            Long roomId,
            String text) {}
}
~~~

Đây là các lớp thành phần dành cho một Spring application có bật STOMP message broker; chúng không phải chương trình Java độc lập để chạy chỉ bằng `javac`. Trong ứng dụng Spring Boot, dependency thường dùng là `spring-boot-starter-websocket`. Payload JSON cần có message converter JSON phù hợp, chẳng hạn converter Jackson.

### Phân tích một message cụ thể

Client gửi STOMP frame tới:

~~~text
SEND
destination:/app/tenants/acme/chat/rooms/42/messages
content-type:application/json

{"text":"Xin chào"}
^@
~~~

Spring xử lý theo thứ tự:

1. Nhận frame trên kết nối WebSocket.
2. Nhận ra destination bắt đầu bằng application prefix `/app`.
3. Bỏ `/app`, còn `/tenants/acme/chat/rooms/42/messages`.
4. Ghép mapping cấp lớp `/tenants/{tenantId}/chat` với mapping cấp phương thức `/rooms/{roomId}/messages`.
5. So khớp destination và lấy `tenantId = "acme"`, `roomId = "42"`.
6. Chuyển đổi `roomId` sang kiểu `Long` của tham số phương thức.
7. Chuyển payload JSON thành `ChatMessageRequest`, sau đó gọi handler.

Với cấu hình broker ở phần 1, client có thể đăng ký nhận kết quả tại:

~~~text
SUBSCRIBE
destination:/topic/tenants/acme/chat/rooms/42/messages
id:room-42
^@
~~~

Nếu handler trả về một object, Spring chuyển object thành payload và gửi qua broker. Theo quy tắc mặc định với cấu hình application prefix `/app` và broker prefix `/topic`, destination phản hồi tương ứng là `/topic/tenants/acme/chat/rooms/42/messages`. Có thể dùng `@SendTo` hoặc `@SendToUser` để chỉ định destination phản hồi khác.

## 4. Cú pháp mẫu đường dẫn Ant-style

Theo mặc định, mapping STOMP của Spring dùng `AntPathMatcher`. Các ký hiệu quan trọng:

| Cú pháp | Ý nghĩa | Ví dụ |
|---|---|---|
| `?` | Khớp đúng một ký tự trong một path segment | `/files/report?.csv` khớp `/files/report1.csv` |
| `*` | Khớp không hoặc nhiều ký tự trong một path segment; không đi qua dấu phân cách `/` | `/rooms/*/messages` khớp `/rooms/42/messages` |
| `**` | Khớp không hoặc nhiều path segment | `/files/**` khớp `/files/a/b.txt` |
| `{name}` | Khớp một path segment và lưu giá trị vào biến tên `name` | `/rooms/{roomId}` khớp `/rooms/42` |
| `{name:regex}` | Khớp một path segment theo biểu thức chính quy và lưu vào biến | `/rooms/{roomId:[0-9]+}` khớp `/rooms/42` |

Một số ví dụ chi tiết:

~~~java
@MessageMapping("/rooms/*/messages")
public void anyRoomMessage() {
    // Ví dụ khớp: /rooms/42/messages
    // Không khớp: /rooms/42/archive/messages
}

@MessageMapping("/files/**")
public void anyFilePath() {
    // Có thể khớp: /files/a.txt
    // Có thể khớp: /files/images/2026/a.png
}

@MessageMapping("/rooms/{roomId}/messages/{messageId}")
public void oneMessage(
        @DestinationVariable("roomId") Long roomId,
        @DestinationVariable("messageId") Long messageId) {
    // Xử lý theo hai biến được lấy từ destination
}

@MessageMapping("/rooms/{roomId:[0-9]+}")
public void numericRoom(
        @DestinationVariable("roomId") Long roomId) {
    // Chỉ nhận roomId gồm các chữ số
}
~~~

Phân biệt `*` và `**`:

- `/rooms/*/messages` chỉ có một segment ở giữa `/rooms` và `/messages`.
- `/rooms/**` có thể nhận cả các destination sâu hơn như `/rooms/42/messages/100/attachments`.

Biến `{roomId}` lấy đúng một segment. Với destination `/rooms/42/messages`, biến có giá trị chuỗi `42`; Spring chuyển đổi giá trị sang kiểu tham số nếu có converter phù hợp. Nếu dùng regex, regex giới hạn giá trị được chấp nhận ngay ở bước so khớp.

Mặc định dấu phân cách là `/`. Không áp dụng máy móc quy tắc của `PathPatternParser` trong Spring MVC cho STOMP controller; phần mapping STOMP được mô tả ở đây dùng `AntPathMatcher`.

## 5. Nhiều pattern cho cùng một handler

Một annotation có thể khai báo nhiều destination pattern:

~~~java
@Controller
@MessageMapping("/chat")
public class ChatController {

    @MessageMapping({
        "/rooms/{roomId}/messages",
        "/channels/{roomId}/messages"
    })
    public void publish(
            @DestinationVariable("roomId") Long roomId,
            @Payload ChatMessageRequest request) {
        // Hai destination cùng đi vào handler này
    }

    public record ChatMessageRequest(String text) {}
}
~~~

Với ví dụ trên, handler nhận cả:

- `/app/chat/rooms/42/messages`
- `/app/chat/channels/42/messages`

Khai báo nhiều pattern hữu ích khi một hành động có nhiều tên destination tương thích. Hãy giữ các route rõ ràng và tránh tạo nhiều handler có mapping trùng hoặc chồng lấn khó phân biệt. Khi thêm route mới, kiểm tra cả mapping sau khi ghép cấp lớp và cấp phương thức, không chỉ nhìn riêng annotation ở phương thức.

## 6. Lấy biến và payload trong handler

### `@DestinationVariable`

Dùng annotation này để lấy biến được khai báo trong destination pattern:

~~~java
@MessageMapping("/orders/{orderId}/items/{itemId}")
public void updateItem(
        @DestinationVariable("orderId") Long orderId,
        @DestinationVariable("itemId") Long itemId) {
    // orderId và itemId được chuyển đổi sang Long
}
~~~

Nên ghi rõ tên biến trong annotation, nhất là khi tên tham số Java có thể bị thay đổi trong quá trình biên dịch hoặc refactor. Tên trong annotation phải trùng với tên đặt trong pattern. Spring có thể chuyển đổi giá trị sang kiểu tham số; nếu giá trị không chuyển đổi được, message sẽ không được xử lý thành công.

Dùng `@DestinationVariable` cho biến của STOMP destination. `@PathVariable` thuộc luồng xử lý HTTP request của Spring MVC và không phải annotation phù hợp cho biến destination trong ví dụ này.

### `@Payload`

Payload được chuyển đổi bằng một `MessageConverter` phù hợp. Ví dụ, với payload JSON và converter Jackson:

~~~java
public record ChatMessageRequest(String text) {}

@MessageMapping("/send")
public void send(@Payload ChatMessageRequest request) {
    // request.text() chứa nội dung đã được chuyển đổi
}
~~~

Trong nhiều trường hợp, `@Payload` có thể được lược bỏ vì Spring mặc định xem tham số chưa được ánh xạ sang loại argument khác là payload. Giữ annotation giúp chữ ký handler dễ đọc hơn. Có thể kết hợp `@Valid` hoặc `@Validated` để yêu cầu validation cho payload khi ứng dụng đã cấu hình validation tương ứng.

### Các argument khác

Tùy nhu cầu, handler cũng có thể nhận:

- `Message` hoặc `MessageHeaders` để truy cập message và headers.
- `@Header("simpSessionId")` hoặc header phù hợp để lấy một header cụ thể.
- `Principal` để lấy người dùng đã xác thực gắn với phiên WebSocket.

Không cần tự phân tích chuỗi destination trong thân phương thức nếu có thể khai báo biến bằng `@DestinationVariable`.

## 7. Dùng dấu chấm làm dấu phân cách

Ứng dụng có thể chọn quy ước destination phân cách bằng dấu chấm thay cho dấu gạch chéo. Khi đó, cấu hình `PathMatcher` trước khi sử dụng quy ước này:

~~~java
import org.springframework.util.AntPathMatcher;

@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setPathMatcher(new AntPathMatcher("."));
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
}
~~~

Controller có thể khai báo:

~~~java
@Controller
@MessageMapping("red")
public class RedController {

    @MessageMapping("blue.{green}")
    public void handleGreen(
            @DestinationVariable("green") String green) {
        // ...
    }
}
~~~

Client gửi tới `/app/red.blue.green123`. Trong ví dụ này, `green` nhận giá trị `green123`.

Đây là lựa chọn cấu hình toàn cục cho cách so khớp destination. Simple broker cũng dùng `PathMatcher` đã cấu hình, vì vậy quy tắc so khớp subscription của simple broker cũng thay đổi. Nếu dùng external STOMP broker relay, cách broker ngoài xử lý destination phụ thuộc vào broker đó; cấu hình `PathMatcher` của Spring không tự thay đổi quy tắc nội bộ của broker ngoài.

Nếu không có nhu cầu tương thích với quy ước messaging dùng dấu chấm, nên giữ dấu `/` mặc định để destination dễ đọc và gần với cấu trúc URL.

## 8. Phân biệt các annotation liên quan

| Annotation | Nơi dùng | Mục đích |
|---|---|---|
| `@MessageMapping` | Cấp lớp hoặc phương thức | Ánh xạ message theo destination |
| `@SubscribeMapping` | Phương thức | Ánh xạ yêu cầu STOMP `SUBSCRIBE`; thường dùng cho phản hồi ban đầu trực tiếp tới client |
| `@DestinationVariable` | Tham số phương thức | Lấy biến từ destination pattern |
| `@Payload` | Tham số phương thức | Lấy payload đã được message converter chuyển đổi |
| `@SendTo` | Cấp lớp hoặc phương thức | Chỉ định destination gửi kết quả qua broker |
| `@SendToUser` | Cấp lớp hoặc phương thức | Gửi kết quả tới người dùng tương ứng |

`@MessageMapping` xử lý message theo destination, thường là STOMP `SEND`. `@SubscribeMapping` dành cho subscription message. Với `@SubscribeMapping`, giá trị trả về mặc định được gửi trực tiếp tới client yêu cầu thay vì phát qua broker; thêm `@SendTo` hoặc `@SendToUser` sẽ thay đổi cách gửi kết quả.

`@SendTo` và `@SendToUser` cũng có thể đặt ở cấp lớp làm giá trị mặc định cho các handler. Annotation cùng loại ở cấp phương thức sẽ ghi đè giá trị cấp lớp.

## 9. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
|---|---|---|
| Handler không được gọi | Client gửi sai application prefix hoặc mapping không khớp | Kiểm tra destination của STOMP `SEND`, bỏ prefix đã cấu hình rồi so với mapping kết hợp |
| Mapping không khớp dù phần cuối đúng | Quên phần mapping cấp lớp hoặc thêm nhầm `/app` vào annotation | Ghép đường dẫn cấp lớp và cấp phương thức, sau đó mới so với destination sau khi bỏ `/app` |
| Nhầm `/ws` với `@MessageMapping` | Dùng endpoint bắt tay làm destination | Kiểm tra riêng URL kết nối WebSocket và destination trong STOMP frame |
| `@DestinationVariable` không nhận được giá trị | Tên biến không khớp hoặc pattern không khớp segment | So sánh tên trong `{roomId}` với `@DestinationVariable("roomId")` |
| Chuyển biến sang số bị lỗi | Destination chứa giá trị không chuyển đổi được sang kiểu tham số | Kiểm tra dữ liệu gửi và giới hạn regex của pattern |
| `*` không nhận destination nhiều cấp | `*` không đi qua dấu phân cách `/` | Dùng `**` nếu route cần nhiều segment |
| Client không nhận được kết quả | Subscribe sai broker destination hoặc handler không gửi tới broker | Kiểm tra destination `SUBSCRIBE`, broker prefix, giá trị trả về và `@SendTo` |
| Payload JSON không chuyển đổi được | Thiếu hoặc sai message converter, content type không phù hợp | Kiểm tra header `content-type` và cấu hình converter JSON |
| Hai handler cùng tranh một destination | Mapping trùng hoặc chồng lấn | Rà soát mapping sau khi ghép cấp lớp và cấp phương thức; thiết kế route không mơ hồ |

## 10. Quy trình thiết kế và kiểm tra mapping

Khi thêm một handler STOMP mới, thực hiện theo thứ tự:

1. Chọn application prefix, ví dụ `/app`, và xác định broker prefix dùng để client đăng ký nhận kết quả, ví dụ `/topic`.
2. Chọn phần đường dẫn chung của controller và đặt tại `@MessageMapping` cấp lớp nếu có nhiều handler cùng nhóm.
3. Khai báo phần đường dẫn riêng của từng handler ở annotation cấp phương thức.
4. Ghép hai phần để viết ra mapping đầy đủ; kiểm tra từng segment, wildcard và biến.
5. Đối chiếu destination client gửi với mapping sau khi application prefix được bỏ.
6. Khai báo `@DestinationVariable` cho từng biến cần sử dụng và chọn kiểu Java phù hợp.
7. Xác nhận payload được converter hỗ trợ; thêm validation khi cần.
8. Kiểm tra destination trả về mặc định hoặc chỉ định bằng `@SendTo` / `@SendToUser`.
9. Kiểm tra các destination đại diện: route hợp lệ, route không hợp lệ, biến biên và route nhiều segment.

## 11. Bài tập tự kiểm tra

### Bài 1

Controller có mapping cấp lớp `/orders`, phương thức có mapping `/customers/{customerId}/items/{itemId}`. Client gửi tới `/app/orders/customers/88/items/501`, với application prefix `/app`.

- Mapping đầy đủ của handler là gì?
- Hai biến nhận giá trị nào?

**Đáp án:** Mapping đầy đủ là `/orders/customers/{customerId}/items/{itemId}`. Sau khi bỏ `/app`, Spring lấy `customerId = "88"` và `itemId = "501"`; nếu tham số là `Long`, Spring chuyển đổi các giá trị tương ứng thành số.

### Bài 2

Pattern là `/rooms/*/messages`. Destination `/rooms/42/messages` và `/rooms/42/archive/messages` có cùng khớp không?

**Đáp án:** Không. Destination thứ nhất khớp vì có đúng một segment ở vị trí `*`. Destination thứ hai có thêm segment `archive`, nên cần pattern phù hợp như `/rooms/**` hoặc một pattern cụ thể hơn.

### Bài 3

Với `@MessageMapping("/rooms/{roomId:[0-9]+}")`, destination `/rooms/abc` có được ánh xạ không?

**Đáp án:** Không. Regex `[0-9]+` chỉ chấp nhận một hoặc nhiều chữ số.

### Bài 4

Khi `setApplicationDestinationPrefixes("/app")` đã được cấu hình, nên đặt `@MessageMapping("/app/chat/send")` hay `@MessageMapping("/chat/send")`?

**Đáp án:** Dùng `@MessageMapping("/chat/send")`. Spring bỏ `/app` trước khi so khớp với mapping trong controller.

## Tài liệu tham khảo

- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html)
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html)
- [Spring Framework — Dots as Separators](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/destination-separator.html)
- [Spring Framework API — AntPathMatcher](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/util/AntPathMatcher.html)
