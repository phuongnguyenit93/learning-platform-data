# @MessageExceptionHandler và @ControllerAdvice trong Spring Framework Messaging (STOMP)

## Mục tiêu và phạm vi

Khi client gửi STOMP message đến một phương thức **@MessageMapping**, lỗi có thể phát sinh từ kiểm tra dữ liệu, quy tắc nghiệp vụ hoặc lời gọi service. Thay vì để lỗi làm gián đoạn luồng xử lý và trả thông tin khó hiểu cho client, Spring Messaging cho phép chuyển exception thành một payload có cấu trúc.

Hai annotation có vai trò khác nhau:

- **@MessageExceptionHandler** đánh dấu phương thức xử lý exception.
- **@ControllerAdvice** mở rộng phạm vi của các phương thức xử lý đó ra nhiều controller.

Nội dung này tập trung vào Spring Messaging, đặc biệt là STOMP over WebSocket. **@MessageExceptionHandler** không phải **@ExceptionHandler** của Spring MVC: một bên xử lý lỗi từ message handler, bên còn lại xử lý lỗi từ HTTP controller.

Cơ chế này phù hợp với exception phát sinh trong quá trình Spring gọi phương thức **@MessageMapping**. Lỗi ở giai đoạn WebSocket handshake, giải mã STOMP frame, vận chuyển mạng hoặc kết nối broker có thể xảy ra ngoài phạm vi của controller; cần xử lý ở tầng tương ứng.

## 1. @MessageExceptionHandler

### 1.1. Cách hoạt động

Đặt **@MessageExceptionHandler** trên một phương thức trong controller để xử lý exception được ném ra khi xử lý message. Có thể khai báo loại exception ngay trong annotation hoặc để Spring suy ra từ kiểu exception của tham số phương thức.

Ví dụ:

~~~java
@MessageExceptionHandler(InvalidChatMessageException.class)
public ErrorPayload handleInvalidMessage(InvalidChatMessageException ex) {
    return new ErrorPayload("INVALID_MESSAGE", ex.getMessage());
}
~~~

Nếu không truyền loại exception vào annotation, kiểu exception trong tham số phương thức được dùng để xác định loại lỗi cần xử lý:

~~~java
@MessageExceptionHandler
public ErrorPayload handleInvalidMessage(InvalidChatMessageException ex) {
    return new ErrorPayload("INVALID_MESSAGE", ex.getMessage());
}
~~~

Một phương thức có thể xử lý nhiều loại exception bằng cách truyền danh sách class vào annotation. Nên chọn loại exception đủ cụ thể để mỗi lỗi có cách phản hồi phù hợp.

### 1.2. Phạm vi xử lý

Theo mặc định, phương thức **@MessageExceptionHandler** chỉ áp dụng trong controller khai báo nó và hệ thống phân cấp class của controller đó. Đây là lựa chọn phù hợp khi lỗi thuộc riêng một nhóm chức năng, ví dụ lỗi gửi tin nhắn trong ChatController.

Phương thức xử lý exception hỗ trợ các kiểu tham số và kiểu trả về giống phương thức **@MessageMapping**. Ngoài tham số exception, có thể dùng các thông tin message như **Message**, **MessageHeaders**, **@Header**, **@Headers**, **@DestinationVariable** và **Principal** khi cần ngữ cảnh để tạo phản hồi.

Giá trị trả về được xử lý như một kết quả message handler: Spring dùng **MessageConverter** phù hợp để chuyển đối tượng thành payload. Có thể dùng **@SendTo** hoặc **@SendToUser** để chỉ định nơi nhận. Với lỗi cần gửi riêng cho người phát sinh yêu cầu, **@SendToUser** thường phù hợp hơn.

## 2. @ControllerAdvice cho xử lý lỗi toàn cục

Khi nhiều controller STOMP cần dùng chung cách chuyển exception thành error payload, có thể chuyển các phương thức **@MessageExceptionHandler** sang một class được đánh dấu **@ControllerAdvice**.

**@ControllerAdvice** là một Spring component, vì vậy class cần nằm trong phạm vi component scan hoặc được đăng ký thành bean. Spring Messaging hỗ trợ các phương thức **@MessageExceptionHandler** trong class này để xử lý lỗi trên nhiều controller.

Ví dụ:

~~~java
package com.example.chat;

import org.springframework.messaging.handler.annotation.MessageExceptionHandler;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.web.bind.annotation.ControllerAdvice;

@ControllerAdvice
public class GlobalMessagingExceptionAdvice {

    @MessageExceptionHandler(InvalidChatMessageException.class)
    @SendToUser(destinations = "/queue/errors", broadcast = false)
    public ErrorPayload handleInvalidChatMessage(InvalidChatMessageException ex) {
        return new ErrorPayload(
                "INVALID_MESSAGE",
                "Nội dung tin nhắn không được để trống"
        );
    }
}
~~~

Có thể dùng advice toàn cục cho các lỗi dùng chung như dữ liệu không hợp lệ, tài nguyên không tồn tại hoặc người dùng không được phép thực hiện thao tác. Lỗi có cách phản hồi riêng của một controller vẫn có thể được xử lý ngay trong controller đó.

Nên chọn rõ nơi sở hữu mỗi quy tắc xử lý. Tránh khai báo cùng một mapping exception ở cả controller và advice nếu không có chủ đích, vì điều đó khiến việc theo dõi handler được chọn trở nên khó khăn.

## 3. Gửi error payload về đúng client

### 3.1. Phân biệt @SendTo và @SendToUser

- **@SendTo("/topic/...")** gửi kết quả đến destination được chỉ định, thường dùng cho dữ liệu cần broadcast tới các subscriber.
- **@SendToUser("/queue/...")** gửi kết quả đến user destination của người dùng gắn với message đang được xử lý.
- Với **@SendToUser**, thuộc tính **broadcast = false** giới hạn phản hồi ở đúng WebSocket session đã gửi message. Nếu không đặt false, các session đang đăng ký destination đó của cùng user có thể cùng nhận phản hồi.

Giả sử cấu hình user destination prefix là **/user**. Phương thức xử lý lỗi khai báo destination **/queue/errors**, còn client subscribe vào **/user/queue/errors**. Không thêm **/user** vào giá trị destination trong **@SendToUser**, vì prefix được Spring áp dụng khi phân giải user destination.

### 3.2. Cấu hình STOMP tối thiểu

Đoạn mã sau minh họa các destination được sử dụng trong ví dụ. Nó là cấu hình của ứng dụng Spring Boot hiện có, không phải một chương trình độc lập.

~~~java
package com.example.chat;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setUserDestinationPrefix("/user");
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }
}
~~~

Với cấu hình này:

| Mục đích | Destination |
|---|---|
| Client gửi message để controller xử lý | /app/chat.send |
| Broadcast tin nhắn hợp lệ | /topic/chat |
| Client subscribe để nhận lỗi riêng | /user/queue/errors |
| Destination trong @SendToUser | /queue/errors |

## 4. Ví dụ hoàn chỉnh theo từng file

Các file dưới đây dùng Java 17+ (record) và giả định ứng dụng đã có Spring WebSocket/STOMP cùng JSON MessageConverter trên classpath. Chúng minh họa phần controller và exception handling; cấu hình endpoint được trình bày ở mục trước.

### 4.1. DTO và exception

**ChatMessage.java**

~~~java
package com.example.chat;

public record ChatMessage(String text) {
}
~~~

**ErrorPayload.java**

~~~java
package com.example.chat;

public record ErrorPayload(String code, String message) {
}
~~~

**InvalidChatMessageException.java**

~~~java
package com.example.chat;

public class InvalidChatMessageException extends RuntimeException {

    public InvalidChatMessageException(String message) {
        super(message);
    }
}
~~~

### 4.2. Xử lý lỗi ngay trong controller

**ChatController.java**

~~~java
package com.example.chat;

import org.springframework.messaging.handler.annotation.MessageExceptionHandler;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage send(@Payload ChatMessage message) {
        if (message.text() == null || message.text().isBlank()) {
            throw new InvalidChatMessageException(
                    "Nội dung tin nhắn không được để trống"
            );
        }

        return message;
    }

    @MessageExceptionHandler(InvalidChatMessageException.class)
    @SendToUser(destinations = "/queue/errors", broadcast = false)
    public ErrorPayload handleInvalidMessage(InvalidChatMessageException ex) {
        return new ErrorPayload("INVALID_MESSAGE", ex.getMessage());
    }
}
~~~

Luồng xử lý:

1. Client gửi JSON đến **/app/chat.send**.
2. Spring chuyển payload thành **ChatMessage** rồi gọi **send()**.
3. Nếu nội dung rỗng, controller ném **InvalidChatMessageException**.
4. Spring tìm phương thức **@MessageExceptionHandler** phù hợp trong controller.
5. Phương thức handler trả về **ErrorPayload**; **@SendToUser** định tuyến payload đến session gửi message.
6. Nếu message hợp lệ, phương thức **send()** trả về **ChatMessage** và **@SendTo** gửi kết quả đến **/topic/chat**.

Trong ví dụ, nội dung của exception là thông báo do ứng dụng chủ động tạo và có thể hiển thị cho người dùng. Với exception kỹ thuật hoặc exception không kiểm soát được, không nên gửi nguyên văn message, SQL, stack trace hay thông tin nội bộ cho client. Hãy ghi chi tiết ở log phía server và trả về mã lỗi cùng thông báo an toàn.

### 4.3. Chuyển handler sang @ControllerAdvice

Nếu nhiều controller cần cùng cách xử lý **InvalidChatMessageException**, bỏ phương thức handler tương ứng khỏi **ChatController** và đặt nó trong **GlobalMessagingExceptionAdvice** như ví dụ ở mục 2.

Khi đó, controller chỉ tập trung xử lý nghiệp vụ:

~~~java
@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatMessage send(@Payload ChatMessage message) {
        if (message.text() == null || message.text().isBlank()) {
            throw new InvalidChatMessageException(
                    "Nội dung tin nhắn không được để trống"
            );
        }

        return message;
    }
}
~~~

Advice toàn cục có thể xử lý exception từ ChatController và các controller STOMP khác trong phạm vi áp dụng. Không giữ đồng thời hai handler giống nhau nếu không cần hành vi xử lý riêng tại controller.

## 5. Kiểm tra từ STOMP client

Client cần subscribe trước vào user destination để nhận error payload. Ví dụ với API của **@stomp/stompjs**:

~~~javascript
client.subscribe("/user/queue/errors", (frame) => {
    const error = JSON.parse(frame.body);
    console.log(error.code, error.message);
});

client.publish({
    destination: "/app/chat.send",
    body: JSON.stringify({ text: "" })
});
~~~

Kết quả mong đợi trong callback:

~~~json
{
  "code": "INVALID_MESSAGE",
  "message": "Nội dung tin nhắn không được để trống"
}
~~~

Khi gửi một message hợp lệ, client nhận nội dung ở **/topic/chat**. Với error payload, client nhận một message bình thường ở **/user/queue/errors**. Vì vậy client có thể giữ kết nối và tiếp tục gửi message sau khi xử lý lỗi nghiệp vụ.

Các điểm cần kiểm tra:

- WebSocket endpoint **/ws** kết nối thành công và STOMP session đã sẵn sàng.
- Application prefix, broker prefix và user destination prefix khớp với cấu hình server.
- Client đã subscribe **/user/queue/errors** trước khi gửi message có thể gây lỗi.
- Payload lỗi có đúng schema và mã lỗi mà client hiểu hay không.
- **broadcast = false** chỉ gửi lỗi về session phát sinh message; thử với hai session của cùng user nếu ứng dụng có hỗ trợ nhiều phiên.
- Khi dùng **@ControllerAdvice**, kiểm tra lỗi từ ít nhất hai controller để xác nhận phạm vi toàn cục.

## 6. @MessageExceptionHandler khác STOMP ERROR frame như thế nào?

Đây là hai cơ chế ở hai tầng khác nhau:

| Cơ chế | Mục đích | Hành vi phía client |
|---|---|---|
| @MessageExceptionHandler | Xử lý exception trong message handler và tạo error payload của ứng dụng | Nhận message tại destination như /user/queue/errors; kết nối có thể tiếp tục |
| StompSubProtocolErrorHandler | Tùy biến hoặc ngăn STOMP ERROR frame khi xử lý lỗi ở tầng STOMP sub-protocol | Nếu server gửi STOMP ERROR frame, giao thức yêu cầu server đóng kết nối |

Dùng **@MessageExceptionHandler** cho lỗi nghiệp vụ trong phương thức **@MessageMapping**, ví dụ dữ liệu không hợp lệ hoặc không tìm thấy đối tượng. Dùng **StompSubProtocolErrorHandler** khi cần kiểm soát STOMP ERROR frame, chẳng hạn lỗi xử lý client message ở tầng sub-protocol. API này nằm trong package **org.springframework.web.socket.messaging** và có thể được cấu hình qua STOMP endpoint registry.

Không nên dùng STOMP ERROR frame như cách mặc định để báo lỗi nhập liệu cho người dùng: việc gửi frame đó kéo theo yêu cầu đóng kết nối. Với lỗi nghiệp vụ, một error payload có cấu trúc qua user destination thường dễ xử lý hơn.

## 7. Lỗi thường gặp và cách khắc phục

| Vấn đề | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Handler không được gọi | Dùng @ExceptionHandler thay cho @MessageExceptionHandler | Dùng đúng annotation của Spring Messaging |
| Advice không có tác dụng | Class không được component scan hoặc chưa được đăng ký thành bean | Đặt advice trong package được scan hoặc khai báo bean |
| Client không nhận được error payload | Client chưa subscribe user destination hoặc sai prefix | Kiểm tra /user/queue/errors và cấu hình user prefix |
| Nhiều thiết bị cùng nhận một lỗi | broadcast mặc định cho các session của cùng user | Đặt broadcast = false nếu chỉ muốn trả về session gửi message |
| Client mất kết nối khi có lỗi | Server gửi STOMP ERROR frame | Dùng message-level handler cho lỗi nghiệp vụ; chỉ tùy biến ERROR frame ở tầng sub-protocol khi phù hợp |
| Payload làm lộ chi tiết nội bộ | Trả trực tiếp message của exception kỹ thuật | Dùng error DTO với code và thông báo công khai; log chi tiết ở server |

## 8. Nguyên tắc thiết kế

1. **Bắt exception có chủ đích.** Dùng exception cụ thể cho lỗi nghiệp vụ để ánh xạ chính xác sang mã lỗi và thông báo.
2. **Giữ payload ổn định.** Một DTO như **ErrorPayload(code, message)** giúp frontend xử lý nhất quán mà không phụ thuộc tên class exception.
3. **Chọn đúng phạm vi.** Handler trong controller dành cho quy tắc riêng; **@ControllerAdvice** dành cho quy tắc dùng chung.
4. **Định tuyến rõ ràng.** Dùng **@SendTo** cho kết quả broadcast và **@SendToUser** cho lỗi gắn với người gửi.
5. **Không gửi thông tin nhạy cảm.** Không trả stack trace, câu truy vấn, token hoặc thông tin hạ tầng trong payload.
6. **Tách lỗi ứng dụng và lỗi giao thức.** Lỗi nghiệp vụ nên là message có cấu trúc; lỗi STOMP protocol cần được xử lý ở tầng sub-protocol.

## 9. Tài liệu tham khảo

- [Annotated Controllers – Spring Framework](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html)
- [User Destinations – Spring Framework](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/user-destination.html)
- [MessageExceptionHandler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/MessageExceptionHandler.html)
- [StompSubProtocolErrorHandler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/messaging/StompSubProtocolErrorHandler.html)
- [Controller Advice – Spring Framework](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html)
