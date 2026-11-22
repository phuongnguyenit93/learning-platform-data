# @DestinationVariable và quy ước dấu chấm trong destination

Trong Spring Messaging dùng STOMP, destination trong STOMP frame là địa chỉ để Spring định tuyến message tới handler. Khi mẫu định tuyến có biến nằm trong dấu ngoặc nhọn, chẳng hạn `{roomId}`, tham số được đánh dấu bằng `@DestinationVariable` nhận giá trị đã được trích xuất từ destination đó. Mặc định Spring dùng dấu gạch chéo `/` làm dấu phân cách. Nếu ứng dụng muốn dùng quy ước destination phân cấp bằng dấu chấm `.`, có thể cấu hình `AntPathMatcher` với separator là dấu chấm.

Hai phần này liên quan trực tiếp: `@DestinationVariable` lấy giá trị từ mẫu `@MessageMapping`, còn `PathMatcher` quyết định cách Spring chia và so khớp các phần của destination.

## 1. Destination và @MessageMapping

WebSocket chỉ cung cấp kênh truyền dữ liệu hai chiều. STOMP bổ sung cấu trúc message và header, trong đó header `destination` cho biết message được gửi tới đâu. Với cấu hình phổ biến:

- Client gửi message tới application destination có tiền tố `/app`.
- Spring loại tiền tố application đã cấu hình rồi so khớp phần destination còn lại với các mẫu `@MessageMapping`.
- Message được xử lý bởi controller phù hợp.
- Kết quả trả về từ handler có thể được chuyển thành message gửi tới broker để các client đang subscribe nhận được.

Ví dụ, khi cấu hình tiền tố application là `/app`, client gửi tới:

```text
/app/chat/rooms/42/messages
```

thì handler có thể khai báo mẫu:

```java
@MessageMapping("/chat/rooms/{roomId}/messages")
```

Phần `{roomId}` là template variable. Với destination trên, Spring trích xuất giá trị chuỗi `42` cho biến `roomId`.

`@MessageMapping` có thể đặt ở cấp class và cấp method. Giá trị ở cấp class tạo phần tiền tố chung; giá trị ở cấp method xác định route cụ thể. Hai phần được kết hợp theo quy tắc của path matcher đang dùng.

Destination thuộc header của STOMP message. Nó độc lập với payload. Vì vậy, `@DestinationVariable` đọc dữ liệu định tuyến từ destination; `@Payload` đọc phần thân message sau khi Spring chuyển đổi bằng message converter.

## 2. Dùng @DestinationVariable với separator mặc định /

Khi không cấu hình path matcher riêng, Spring dùng `AntPathMatcher` với dấu phân cách mặc định là `/`. Một controller có thể nhận mã phòng từ destination như sau:

```java
package com.example.messaging;

import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    @MessageMapping("/chat/rooms/{roomId}/messages")
    public String handleMessage(
            @DestinationVariable("roomId") long roomId,
            @Payload String text) {

        return "room=" + roomId + "; text=" + text;
    }
}
```

Với cấu hình broker có application prefix `/app` và simple broker prefix `/topic`, client có thể gửi và nhận như sau:

```javascript
stompClient.subscribe(
  "/topic/chat/rooms/42/messages",
  frame => console.log(frame.body)
);

stompClient.publish({
  destination: "/app/chat/rooms/42/messages",
  headers: { "content-type": "text/plain" },
  body: "Xin chào"
});
```

Khi message được định tuyến thành công, Spring gọi `handleMessage` với `roomId = 42` và `text = "Xin chào"`. Giá trị trả về được chuyển thành message gửi tới destination phản hồi mặc định dưới tiền tố broker `/topic`, trong ví dụ này là `/topic/chat/rooms/42/messages`. Client đã subscribe destination đó sẽ nhận body:

```text
room=42; text=Xin chào
```

Ví dụ dùng payload kiểu `String` để tập trung vào cơ chế định tuyến. Với payload JSON, ứng dụng cần có message converter JSON phù hợp, thường là Jackson, và kiểu DTO tương ứng.

## 3. Cách khai báo và chuyển đổi biến destination

### Tên biến phải khớp với mẫu

Tên trong annotation phải trùng với tên template variable trong `@MessageMapping`:

```java
@MessageMapping("/orders/{orderId}/events")
public void handle(
        @DestinationVariable("orderId") long id) {
    // Xử lý order có id tương ứng.
}
```

Ở đây tên tham số Java là `id`, còn tên trong destination là `orderId`. Điều đó hợp lệ vì annotation chỉ rõ tên cần lấy. Nên ghi rõ giá trị annotation khi route có nhiều biến hoặc tên tham số Java khác tên trong destination; cách này giúp ý định ánh xạ dễ đọc và ít phụ thuộc vào metadata tên tham số khi biên dịch.

### Spring chuyển đổi kiểu tham số

Giá trị được trích xuất từ destination ban đầu là chuỗi. Spring chuyển đổi nó sang kiểu tham số được khai báo nếu có converter phù hợp. Ví dụ:

```java
@MessageMapping("/accounts/{accountId}/events")
public void handle(
        @DestinationVariable("accountId") Long accountId) {
    // accountId đã được chuyển sang Long.
}
```

Dùng `String` khi định danh có thể chứa chữ, dấu gạch ngang hoặc ký tự khác. Dùng kiểu cụ thể như `Long` khi định danh thực sự là số và ứng dụng muốn Spring thực hiện chuyển đổi. Nếu giá trị không thể chuyển sang kiểu yêu cầu, việc phân giải tham số thất bại và message đi vào luồng xử lý lỗi của ứng dụng. Không nên giả định mọi chuỗi đều hợp lệ chỉ vì chúng khớp được vị trí của biến trong destination.

### Nhiều biến trong cùng một destination

Mỗi template variable có thể được ánh xạ vào một tham số riêng:

```java
@MessageMapping("/rooms/{roomId}/users/{userId}/messages")
public void handle(
        @DestinationVariable("roomId") long roomId,
        @DestinationVariable("userId") long userId,
        @Payload String text) {
    // Xử lý message của user trong room.
}
```

Với destination `/app/rooms/42/users/7/messages`, Spring lấy `42` cho `roomId` và `7` cho `userId`, sau đó chuyển đổi sang `long`.

Một template variable là bắt buộc. `@DestinationVariable` không phải cơ chế khai báo tham số tùy chọn. Nếu một route có phần cuối tùy chọn, hãy thiết kế các mẫu mapping riêng hoặc một mẫu phù hợp rõ ràng thay vì mong đợi biến bị thiếu sẽ tự trở thành `null`.

### Phân biệt với @PathVariable, @Header và @Payload

- `@DestinationVariable`: lấy giá trị từ template variable trong STOMP destination của message.
- `@PathVariable`: lấy biến từ đường dẫn của HTTP request trong Spring MVC/WebFlux.
- `@Header`: lấy giá trị từ một header của message, chẳng hạn header tùy chỉnh hoặc header STOMP.
- `@Payload`: lấy phần thân message sau khi message converter chuyển đổi.

Không dùng `@PathVariable` cho biến trong destination của `@MessageMapping`. Hai annotation phục vụ hai cơ chế định tuyến khác nhau.

## 4. Chuyển sang quy ước dấu chấm trong destination

Một số hệ thống messaging biểu diễn phân cấp bằng dấu chấm, ví dụ `chat.rooms.42.messages`, thay vì dấu gạch chéo. Spring hỗ trợ quy ước này bằng cách đặt một `AntPathMatcher` dùng dấu chấm làm separator trong `configureMessageBroker`:

```java
package com.example.messaging;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.util.AntPathMatcher;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class StompConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setPathMatcher(new AntPathMatcher("."));
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
```

Sau khi bật separator dấu chấm, controller có thể kết hợp mapping cấp class và cấp method:

```java
package com.example.messaging;

import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

@Controller
@MessageMapping("chat")
public class ChatController {

    @MessageMapping("rooms.{roomId}.messages")
    public String handleMessage(
            @DestinationVariable("roomId") long roomId,
            @Payload String text) {

        return "room=" + roomId + "; text=" + text;
    }
}
```

Mapping cấp class là `chat`; mapping cấp method là `rooms.{roomId}.messages`. Khi ghép lại, route là `chat.rooms.{roomId}.messages`. Client gửi message tới:

```text
/app/chat.rooms.42.messages
```

và subscribe destination phản hồi:

```text
/topic/chat.rooms.42.messages
```

Client STOMP.js có thể thực hiện hai thao tác như sau:

```javascript
stompClient.subscribe(
  "/topic/chat.rooms.42.messages",
  frame => console.log(frame.body)
);

stompClient.publish({
  destination: "/app/chat.rooms.42.messages",
  headers: { "content-type": "text/plain" },
  body: "Xin chào"
});
```

Handler nhận `roomId = 42`. Với payload `Xin chào`, giá trị trả về là `room=42; text=Xin chào` và được gửi tới destination phản hồi mặc định dưới tiền tố `/topic`.

### Phần nào vẫn dùng dấu gạch chéo?

Tiền tố application `/app`, endpoint WebSocket `/ws` và các tiền tố broker như `/topic` hoặc `/queue` vẫn được cấu hình riêng. Ví dụ `/app` là tiền tố để Spring phân loại message đi vào application handler; nó không phải một phần của mẫu `@MessageMapping` trong ví dụ trên.

Endpoint `/ws` cũng không phải destination của message. Đây là URL client dùng để thiết lập kết nối WebSocket/STOMP. Sau khi kết nối, client gửi các STOMP frame tới destination như `/app/chat.rooms.42.messages`.

## 5. Ảnh hưởng và giới hạn của dot separator

### Cấu hình áp dụng cho cách so khớp, không chỉ cho một annotation

`registry.setPathMatcher(new AntPathMatcher("."))` thay đổi quy tắc phân tách khi Spring so khớp các mẫu message mapping. Nó không tự động đổi mọi chuỗi destination trong ứng dụng và cũng không sửa destination mà client đang gửi. Mẫu `@MessageMapping`, destination gửi từ client và destination dùng khi subscribe phải tuân theo cùng quy ước.

Khi dùng simple broker tích hợp của Spring, broker cũng dựa vào `PathMatcher` đã cấu hình để so khớp destination của subscription. Vì vậy, thay separator có thể ảnh hưởng cả cách broker so khớp subscription. Cần kiểm tra các mẫu subscribe và publish sau khi đổi cấu hình, đặc biệt khi đang dùng wildcard.

Nếu dùng STOMP broker relay tới broker bên ngoài, quy tắc định tuyến destination của broker bên ngoài do chính broker đó quyết định. Cấu hình `PathMatcher` của Spring không thay đổi quy tắc nội bộ của broker ngoài. Các tiền tố relay như `/topic` và `/queue` vẫn cần phù hợp với cấu hình broker; hãy đối chiếu tài liệu broker đang sử dụng trước khi đổi quy ước destination.

### Dấu chấm trở thành ký tự phân cách

Khi `AntPathMatcher` được cấu hình với separator `.`, dấu chấm có ý nghĩa cấu trúc. Ví dụ `chat.rooms.{roomId}.messages` có các phần `chat`, `rooms`, giá trị `roomId` và `messages`.

Điều này ảnh hưởng đến giá trị biến. Nếu `roomId` có giá trị `team.alpha`, dấu chấm trong giá trị có thể bị hiểu là ranh giới giữa các phần destination thay vì một ký tự thuộc mã định danh. Nên chọn mã định danh không chứa separator, hoặc thiết kế và kiểm thử một quy tắc escaping/encoding thống nhất ở cả client và server. Không giả định Spring tự động mã hóa hay giải mã dấu chấm trong biến.

### Không trộn hai quy ước tùy tiện

Với separator mặc định, dấu gạch chéo phân tách các phần; dấu chấm chỉ là ký tự thông thường trong phần destination. Khi chuyển sang separator dấu chấm, các wildcard và template variable được so khớp theo ranh giới dấu chấm. Vì vậy, một mẫu được viết theo quy ước slash không tự động tương đương với mẫu dot-separated.

Nếu ứng dụng có nhiều client hoặc nhiều module messaging, hãy thống nhất quy ước ở hợp đồng destination trước khi thay đổi cấu hình. Việc đổi path matcher có thể làm những mapping và subscription đang hoạt động không còn khớp như trước.

## 6. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra hoặc sửa |
|---|---|---|
| Handler không được gọi | Destination client gửi không khớp mẫu `@MessageMapping` | Đối chiếu chính xác destination header với mẫu sau khi loại application prefix. |
| Không lấy được biến | Tên trong `@DestinationVariable` khác tên trong `{...}` | Dùng cùng tên, kể cả chữ hoa/chữ thường; khai báo rõ `@DestinationVariable("roomId")`. |
| Client gửi slash nhưng server khai báo dot | Client và server đang dùng hai quy ước separator khác nhau | Thống nhất mẫu mapping và destination ở cả hai phía. |
| Biến không chuyển được sang số | Destination chứa giá trị không phải số nhưng tham số là `long` hoặc `Long` | Kiểm tra dữ liệu gửi; dùng `String` hoặc kiểu phù hợp nếu định danh không phải số. |
| Giá trị biến có dấu chấm bị tách | Dấu chấm đang là separator của path matcher | Chọn định danh không chứa dấu chấm hoặc xây dựng quy tắc escaping/encoding có kiểm thử. |
| Subscribe không nhận được phản hồi với simple broker | Subscription destination không khớp quy tắc matcher hoặc prefix broker | Kiểm tra cả destination phản hồi mặc định, prefix `/topic` và path matcher. |
| Mapping cũ hỏng sau khi đổi separator | `setPathMatcher` ảnh hưởng cách so khớp chung | Rà soát các mapping và subscription dùng simple broker; triển khai thay đổi đồng bộ với client. |
| Nhầm `/ws` với destination | Endpoint WebSocket và STOMP destination là hai địa chỉ khác nhau | Dùng `/ws` để kết nối; dùng `/app/...` để gửi message sau khi kết nối. |

Một destination do client gửi có thể chứa dữ liệu do người dùng kiểm soát. Việc trích xuất thành công bằng `@DestinationVariable` không đồng nghĩa dữ liệu đó đã hợp lệ hoặc người gửi được phép truy cập tài nguyên tương ứng. Hãy kiểm tra miền giá trị trong ứng dụng và thực hiện phân quyền dựa trên người dùng đã xác thực, chẳng hạn thông qua `Principal` và lớp service. Không dùng riêng `roomId` hoặc `userId` trong destination làm bằng chứng phân quyền.

## 7. Checklist kiểm thử

Khi thêm hoặc thay đổi mapping, nên kiểm tra qua kết nối STOMP thực tế với cùng cấu hình mà ứng dụng triển khai:

1. Gửi message tới destination hợp lệ và xác nhận đúng handler được gọi.
2. Xác nhận mỗi `@DestinationVariable` nhận đúng giá trị, đúng kiểu dữ liệu.
3. Gửi giá trị không thể chuyển đổi sang kiểu tham số để xác nhận luồng xử lý lỗi.
4. Gửi destination thiếu một phần hoặc sai thứ tự segment để xác nhận mapping không vô tình khớp.
5. Kiểm tra client dùng đúng separator: slash khi dùng mặc định, dot khi cấu hình `AntPathMatcher(".")`.
6. Với simple broker, kiểm tra cả destination subscribe và destination phản hồi.
7. Với broker relay, kiểm tra quy tắc destination theo broker bên ngoài và xác nhận các prefix broker vẫn đúng.
8. Kiểm tra quyền truy cập bằng nhiều người dùng khác nhau; không chỉ kiểm tra việc route có khớp hay không.

Có thể dùng `WebSocketStompClient` trong integration test hoặc một client STOMP như STOMP.js để gửi frame và subscribe. Kiểm thử ở mức controller đơn lẻ không thay thế được việc xác nhận destination, prefix, path matcher và broker phối hợp đúng trong một phiên STOMP thực tế.

## Tài liệu tham khảo

- [Spring Framework Reference — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html): cách khai báo `@MessageMapping`, các tham số handler và `@DestinationVariable`.
- [Spring Framework Reference — Dots as Separators](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/destination-separator.html): cấu hình `AntPathMatcher(".")`, ví dụ mapping dot-separated và ảnh hưởng tới simple broker.
- [Spring Framework Javadoc — DestinationVariable](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/DestinationVariable.html): mục đích annotation, thuộc tính `value` và yêu cầu template variable phải tồn tại.
