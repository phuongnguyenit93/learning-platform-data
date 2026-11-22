# @Header, @Headers và Principal trong phương thức xử lý STOMP

## Mục tiêu

Trong một ứng dụng Spring WebSocket dùng STOMP, một phương thức được đánh dấu bằng @MessageMapping có thể nhận đồng thời payload, metadata của message và danh tính người gửi. Ba cách lấy thông tin thường gặp là:

- **@Header**: lấy một header cụ thể, chẳng hạn mã tương quan, phiên bản client hoặc mức ưu tiên.
- **@Headers**: lấy toàn bộ map header của message để kiểm tra nhiều metadata cùng lúc.
- **Principal**: lấy danh tính người dùng gắn với phiên WebSocket hiện tại.

Chọn đúng tham số giúp chữ ký handler rõ ràng, giảm việc tự đọc map header và tránh nhầm dữ liệu do client gửi với danh tính đã được máy chủ xác thực.

## 1. Vị trí của các tham số trong luồng STOMP

WebSocket cung cấp kênh truyền hai chiều. STOMP định nghĩa cấu trúc frame và các lệnh như CONNECT, SEND, SUBSCRIBE, MESSAGE. Spring chuyển frame STOMP nhận được thành một đối tượng Message có payload và MessageHeaders, rồi chuyển message vào các channel nội bộ để định tuyến.

Với cấu hình thường gặp:

- Client gửi tới /app/...: message được chuyển tới controller có @MessageMapping.
- Client đăng ký /topic/... hoặc /queue/...: message subscription được broker xử lý.
- Controller trả về một giá trị: Spring chuyển giá trị thành payload và gửi qua broker. Với cấu hình mặc định, destination phản hồi thường là destination đầu vào được thêm prefix /topic.

Ví dụ, client gửi SEND tới /app/rooms/42/messages; handler được ánh xạ bằng @MessageMapping("/rooms/{roomId}/messages"). Nếu handler trả về một đối tượng, destination mặc định thường là /topic/rooms/42/messages.

Các tham số của handler được Spring phân giải theo kiểu và annotation. Payload là nội dung nghiệp vụ; header là metadata đi kèm message; Principal là danh tính người dùng của phiên. Chúng không phải ba cách khác nhau để đọc cùng một dữ liệu.

## 2. Cấu hình STOMP tối thiểu để đặt ví dụ vào đúng ngữ cảnh

Đoạn cấu hình sau minh họa hai prefix quan trọng. /app dành cho message đi vào controller, còn /topic và /queue dành cho broker:

~~~java
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

Đây là mã cấu hình trong một ứng dụng Spring, không phải chương trình Java độc lập. Ứng dụng cần các dependency Spring WebSocket và Spring Messaging phù hợp với phiên bản Spring đang dùng; đặt lớp public này trong file WebSocketConfig.java.

Một client STOMP có thể gửi payload cùng custom header như sau:

~~~javascript
stompClient.publish({
    destination: "/app/rooms/42/messages",
    headers: {
        "traceId": "req-7f31",
        "client-version": "1.4.0"
    },
    body: JSON.stringify({ text: "Xin chào mọi người!" })
});
~~~

traceId và client-version là metadata do client gửi trong frame SEND. Chúng không tự trở thành danh tính đã xác thực. Tên header và cách gửi cụ thể phụ thuộc thư viện STOMP client, nhưng về phía server chúng được xử lý như native STOMP headers.

## 3. @Header: lấy một giá trị cụ thể

Dùng annotation thuộc package **org.springframework.messaging.handler.annotation**:

~~~java
import org.springframework.messaging.handler.annotation.Header;

@MessageMapping("/orders")
public void receiveOrder(
        @Header("traceId") String traceId,
        @Header(name = "priority", required = false) Integer priority) {

    // Xử lý đơn hàng với metadata đi kèm.
}
~~~

Spring tìm giá trị header theo tên và chuyển đổi kiểu nếu cần bằng cơ chế conversion của Spring. Vì vậy một giá trị dạng chuỗi có thể được chuyển thành Integer, Long hoặc kiểu khác nếu có converter phù hợp.

### Các thuộc tính quan trọng

| Thuộc tính | Ý nghĩa |
|---|---|
| value | Tên header cần lấy; là alias của name. |
| name | Tên header cần lấy; có thể dùng thay cho value. |
| required | Mặc định là true. Nếu thiếu header bắt buộc, việc gọi handler thất bại với lỗi thiếu header. |
| defaultValue | Giá trị dự phòng khi header không có. Khi khai báo thuộc tính này, required được ngầm đặt thành false. |

Ví dụ:

~~~java
@MessageMapping("/orders")
public void receive(
        @Header("traceId") String traceId,
        @Header(name = "retry-count", required = false) Integer retryCount,
        @Header(name = "source", defaultValue = "web") String source) {
    // traceId là bắt buộc.
    // retryCount có thể là null.
    // source nhận "web" nếu client không gửi header.
}
~~~

Nếu dùng required = false, hãy chọn kiểu tham chiếu như Integer thay vì kiểu nguyên thủy int, vì giá trị thiếu có thể được biểu diễn bằng null. Nếu header bắt buộc mà không tồn tại, Spring không tự điền một giá trị giả; lỗi được chuyển vào cơ chế xử lý lỗi message của ứng dụng.

### Header thường và native STOMP header

Spring Messaging có hai lớp metadata cần phân biệt:

1. **Header cấp cao của Spring**: metadata phục vụ định tuyến và xử lý nội bộ, ví dụ simpDestination, simpSessionId, simpMessageType, simpUser.
2. **Native headers**: các header gốc của giao thức hoặc header tùy chỉnh do client gửi. Trong message Spring, chúng được giữ trong map con có khóa nativeHeaders.

Với handler STOMP, @Header("traceId") có thể phân giải một native header tên traceId. Nếu cần chỉ rõ phải lấy giá trị từ map native, dùng cú pháp `nativeHeaders.` + tên header:

~~~java
@MessageMapping("/events")
public void receive(
        @Header("traceId") String traceId,
        @Header(name = "nativeHeaders.client-version", required = false)
        String clientVersion) {
    // ...
}
~~~

Nếu cùng một tên tồn tại cả ở map header cấp cao và map native, giá trị cấp cao được ưu tiên cho cách tra cứu thông thường. Dùng `nativeHeaders.` + tên header khi cần chỉ định rõ nguồn native.

Native STOMP header có thể có nhiều giá trị. Khi chỉ có một giá trị, Spring phân giải thành giá trị đơn; khi có nhiều giá trị, dữ liệu có thể được biểu diễn dưới dạng danh sách. Nếu giao thức hoặc client cho phép header lặp, hãy kiểm tra kiểu thực tế và cân nhắc nhận List hoặc dùng StompHeaderAccessor để đọc rõ ràng.

### Khi nào nên dùng @Header?

Dùng @Header khi handler chỉ cần một hoặc vài giá trị cụ thể, ví dụ:

- traceId để nối log giữa các service.
- client-version để tương thích hành vi theo phiên bản client.
- priority hoặc retry-count để điều khiển xử lý.
- simpSessionId để chẩn đoán phiên kết nối.

Không nên dùng header do client tự khai báo làm bằng chứng xác thực hoặc phân quyền. Các giá trị như userId, role, isAdmin gửi từ trình duyệt đều có thể bị sửa.

## 4. @Headers: lấy toàn bộ map header

@Headers dùng khi cần xem nhiều metadata trong một lần. Tham số được đánh dấu phải nhận được một kiểu tương thích với Map có key kiểu String và value kiểu Object.

~~~java
import java.util.Map;
import org.springframework.messaging.handler.annotation.Headers;

@MessageMapping("/inspect")
public void inspect(@Headers Map<String, Object> headers) {
    Object destination = headers.get("simpDestination");
    Object sessionId = headers.get("simpSessionId");
    Object nativeHeaders = headers.get("nativeHeaders");

    // Đặt breakpoint hoặc chuyển metadata đã được lọc vào log có cấu trúc.
}
~~~

Map này chứa các header của message, bao gồm metadata nội bộ của Spring và entry nativeHeaders chứa map các native STOMP headers. Ví dụ, simpDestination cho biết destination đã được Spring chuẩn hóa; simpSessionId xác định phiên WebSocket; nativeHeaders giữ các header giao thức hoặc custom header.

Không nên giả định mọi key đều tồn tại trên mọi loại message. CONNECT, SEND, SUBSCRIBE và message do server tạo ra có thể mang metadata khác nhau. Hãy kiểm tra null và kiểu dữ liệu trước khi ép kiểu hoặc sử dụng.

@Headers phù hợp với logging có chọn lọc, tracing, interceptor nghiệp vụ cần nhiều metadata hoặc chẩn đoán. Nếu chỉ cần một key, @Header thường dễ đọc hơn. Tránh ghi toàn bộ map vào log vì nó có thể chứa thông tin nhạy cảm như token hoặc dữ liệu xác thực.

### Phân biệt @Headers với MessageHeaders

Có thể khai báo trực tiếp MessageHeaders để truy cập header map của message mà không dùng annotation:

~~~java
import org.springframework.messaging.MessageHeaders;

@MessageMapping("/inspect")
public void inspect(MessageHeaders headers) {
    Object destination = headers.get("simpDestination");
}
~~~

@Headers biểu thị rõ ý định lấy toàn bộ header thông qua một tham số Map. MessageHeaders là kiểu chuyên biệt của Spring cho metadata message và cũng cung cấp các thao tác đọc theo key. Trong cả hai trường hợp, hãy coi metadata đầu vào là dữ liệu để đọc; đừng cố sửa map header của message đã được tạo.

## 5. Principal: danh tính người gửi

java.security.Principal đại diện cho người dùng được gắn với phiên WebSocket. Trong controller STOMP, Spring hỗ trợ truyền Principal trực tiếp vào tham số handler:

~~~java
import java.security.Principal;

@MessageMapping("/private/ping")
public String ping(Principal principal) {
    if (principal == null) {
        throw new IllegalStateException("Phiên hiện tại chưa được xác thực");
    }

    return "Xin chào " + principal.getName();
}
~~~

principal.getName() trả về tên định danh do cơ chế xác thực cung cấp. Đây là nguồn phù hợp để biết ai đang gửi message. Không nên lấy danh tính người gửi từ @Header("userId") hoặc từ trường userId trong payload rồi tin trực tiếp.

### Principal được tạo và truyền đến đâu?

Trong luồng xác thực HTTP thông thường:

1. Người dùng đăng nhập qua cơ chế bảo mật HTTP, chẳng hạn Spring Security.
2. WebSocket handshake được thực hiện trong ngữ cảnh người dùng đó.
3. Spring tự liên kết Principal của HTTP request với WebSocket session.
4. Các STOMP message trên session mang thông tin user tương ứng.
5. Handler có thể nhận Principal làm tham số.

Vì vậy, nếu ứng dụng đã xác thực người dùng ở HTTP và giữ đúng session/cookie, thường không cần tự gửi tên người dùng trong từng frame SEND.

Nếu ứng dụng dùng token ở tầng STOMP, có thể xác thực frame CONNECT bằng ChannelInterceptor rồi gắn Principal đã xác thực vào message. Ví dụ sau chỉ minh họa điểm tích hợp; authenticationService là thành phần xác thực do ứng dụng cung cấp. Đặt đoạn xử lý trong một lớp triển khai ChannelInterceptor và đăng ký lớp đó với client inbound channel:

~~~java
import java.security.Principal;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageHeaderAccessor;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;

@Override
public Message<?> preSend(Message<?> message, MessageChannel channel) {
    StompHeaderAccessor accessor =
            MessageHeaderAccessor.getAccessor(message, StompHeaderAccessor.class);

    if (accessor != null && StompCommand.CONNECT.equals(accessor.getCommand())) {
        String token = accessor.getFirstNativeHeader("Authorization");
        Principal authenticatedUser = authenticationService.authenticate(token);
        accessor.setUser(authenticatedUser);
    }

    return message;
}
~~~

Spring ghi nhận user được gắn trên CONNECT và liên kết user đó với các message tiếp theo trong cùng session. Khi dùng Spring Security để phân quyền message, cần cấu hình interceptor xác thực chạy trước interceptor phân quyền của Spring Security.

### STOMP login và passcode không tự xác thực WebSocket

STOMP có header login và passcode trên frame CONNECT. Với Spring STOMP over WebSocket, mặc định Spring bỏ qua các header xác thực ở cấp STOMP và kỳ vọng danh tính đã được xác thực ở tầng HTTP. Nếu muốn xác thực token ở tầng STOMP, phải chủ động xử lý header trong ChannelInterceptor và gọi setUser sau khi xác thực thành công.

Không được xem một header do client gửi là Principal đáng tin cậy. Principal phải đến từ handshake đã xác thực hoặc từ bước xác thực token phía server.

### Principal có thể null

Nếu endpoint cho phép kết nối ẩn danh hoặc chưa cấu hình xác thực, Principal có thể null. Hãy quyết định rõ endpoint có cho phép anonymous hay không:

- Endpoint công khai: có thể xử lý trường hợp Principal null như khách chưa đăng nhập.
- Endpoint riêng tư: từ chối message khi Principal null.
- Endpoint cần phân quyền: kiểm tra quyền ở server dựa trên danh tính đã xác thực, không dựa vào header do client khai báo.

Không nên tự gán một tên người dùng mặc định rồi dùng tên đó để cấp quyền.

## 6. Kết hợp @Header, @Headers và Principal trong một handler

Ví dụ sau minh họa một handler nhận payload, destination variable, custom header, toàn bộ metadata và người gửi. DTO dùng Java record nên cần Java 16 trở lên; Java 17 là lựa chọn phù hợp.

~~~java
import java.security.Principal;
import java.util.Map;

import org.springframework.messaging.handler.annotation.DestinationVariable;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    @MessageMapping("/rooms/{roomId}/messages")
    public ChatReply receive(
            @DestinationVariable("roomId") String roomId,
            @Payload ChatMessage request,
            @Header(name = "traceId", required = false) String traceId,
            @Header(name = "nativeHeaders.client-version", required = false)
            String clientVersion,
            @Headers Map<String, Object> allHeaders,
            Principal principal) {

        if (principal == null) {
            throw new IllegalStateException("Cần đăng nhập để gửi tin nhắn");
        }

        String sender = principal.getName();
        String destination = (String) allHeaders.get("simpDestination");

        return new ChatReply(
                roomId,
                sender,
                request.text(),
                traceId,
                clientVersion,
                destination
        );
    }
}

record ChatMessage(String text) {}

record ChatReply(
        String roomId,
        String sender,
        String text,
        String traceId,
        String clientVersion,
        String inboundDestination
) {}
~~~

Khi client gửi tới /app/rooms/42/messages, roomId nhận giá trị 42; payload JSON được chuyển thành ChatMessage; traceId và client-version được lấy từ native header; allHeaders cho phép đọc metadata như simpDestination; Principal cho biết user của session. Giá trị trả về được chuyển thành message và gửi theo quy tắc destination mặc định của broker.

Đây là ví dụ controller cho một ứng dụng Spring đã bật STOMP, có message converter JSON và đã cấu hình xác thực. Các record có thể đặt trong file riêng nếu dự án yêu cầu mỗi kiểu public ở một file. Nếu endpoint thực sự cho phép anonymous, hãy thay điều kiện từ chối bằng chính sách guest rõ ràng.

## 7. Dùng StompHeaderAccessor khi cần metadata STOMP có kiểu

Khi cần nhiều trường giao thức hoặc muốn tránh đọc key bằng chuỗi, nhận StompHeaderAccessor trực tiếp:

~~~java
import java.security.Principal;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;

@MessageMapping("/diagnostics")
public void diagnostics(StompHeaderAccessor accessor) {
    String sessionId = accessor.getSessionId();
    String destination = accessor.getDestination();
    String clientVersion = accessor.getFirstNativeHeader("client-version");
    Principal user = accessor.getUser();
    StompCommand command = accessor.getCommand();
}
~~~

Accessor cung cấp các phương thức có kiểu để đọc metadata thường gặp. Một số ví dụ:

- getSessionId(): ID của WebSocket session.
- getDestination(): destination đã được Spring xử lý.
- getUser(): Principal gắn với message.
- getCommand(): lệnh STOMP như SEND hoặc SUBSCRIBE.
- getFirstNativeHeader(name): giá trị đầu tiên của native header theo tên.

Dùng SimpMessageHeaderAccessor nếu chỉ cần metadata chung của Spring Messaging. Dùng StompHeaderAccessor khi cần chi tiết riêng của STOMP. Với một giá trị đơn giản, @Header vẫn là cách ngắn gọn nhất.

## 8. Trả lời riêng cho người dùng hiện tại

Khi muốn phản hồi riêng cho user đang gửi message, có thể kết hợp Principal với @SendToUser:

~~~java
import java.security.Principal;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.annotation.SendToUser;

@MessageMapping("/private/ping")
@SendToUser("/queue/reply")
public Pong ping(Principal principal) {
    if (principal == null) {
        throw new IllegalStateException("Cần đăng nhập");
    }
    return new Pong("Pong từ " + principal.getName());
}

record Pong(String message) {}
~~~

Spring định tuyến phản hồi tới user destination tương ứng với Principal của message đầu vào. Đây là cách phù hợp hơn việc tự tạo destination từ một userId client gửi lên. Cấu hình broker cần hỗ trợ user destination theo cấu hình STOMP của ứng dụng.

## 9. Những lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Handler báo thiếu header | @Header mặc định required nhưng client không gửi key đó | Gửi header hoặc đặt required = false / defaultValue |
| Lỗi khi gán null vào kiểu số | Dùng kiểu nguyên thủy với header tùy chọn | Dùng Integer, Long hoặc kiểu tham chiếu |
| Giá trị header không chuyển được sang kiểu đích | Chuỗi không hợp lệ hoặc không có converter phù hợp | Kiểm tra giá trị client gửi và kiểu tham số |
| Không thấy custom STOMP header trong map cấp cao | Native header được giữ trong entry nativeHeaders | Dùng @Header theo tên native hoặc StompHeaderAccessor |
| Lấy nhầm giá trị khi hai map trùng tên key | Header cấp cao được ưu tiên trong tra cứu thông thường | Chỉ rõ `nativeHeaders.` + tên header |
| Principal là null | Kết nối anonymous hoặc handshake chưa có user đã xác thực | Kiểm tra cấu hình xác thực và chính sách anonymous |
| Principal không đổi dù client gửi userId khác | Danh tính không được quyết định bởi payload/header tùy ý | Xác thực ở HTTP handshake hoặc ChannelInterceptor |
| Log chứa token hoặc thông tin nhạy cảm | Ghi toàn bộ @Headers map | Chỉ log các key cần thiết và che giá trị nhạy cảm |

Một lỗi khác là import nhầm annotation. @Header dùng cho Spring Messaging handler nằm trong package org.springframework.messaging.handler.annotation. @RequestHeader thuộc Spring MVC và dùng cho tham số của HTTP request; nó không thay thế @Header trong handler STOMP.

## 10. Chọn cách nhận tham số

| Nhu cầu | Cách nên dùng |
|---|---|
| Lấy một custom header | @Header("traceId") |
| Header có thể thiếu | @Header(required = false) hoặc defaultValue |
| Lấy toàn bộ metadata | @Headers Map<String, Object> |
| Đọc header map với kiểu Spring chuyên biệt | MessageHeaders |
| Lấy danh tính người gửi đã được xác thực | Principal |
| Đọc nhiều trường STOMP bằng accessor | StompHeaderAccessor |
| Gửi phản hồi riêng cho user hiện tại | @SendToUser cùng Principal |

## 11. Checklist khi triển khai

- [ ] Phân biệt rõ payload, header và danh tính người gửi.
- [ ] Dùng đúng package org.springframework.messaging.handler.annotation.
- [ ] Chỉ đánh dấu required cho header mà client bắt buộc phải gửi.
- [ ] Dùng kiểu tham chiếu cho header tùy chọn.
- [ ] Kiểm tra dữ liệu trước khi ép kiểu hoặc chuyển đổi.
- [ ] Dùng `nativeHeaders.` + tên header hoặc accessor khi cần đọc rõ native header.
- [ ] Không dùng userId/role do client gửi để quyết định quyền.
- [ ] Xác thực HTTP handshake hoặc xác thực CONNECT bằng ChannelInterceptor.
- [ ] Xử lý Principal null theo chính sách anonymous của endpoint.
- [ ] Không ghi token, passcode hoặc toàn bộ header map vào log.

## Tài liệu tham khảo

- [Spring Framework — Annotated Controllers for STOMP](https://docs.spring.io/spring/reference/web/websocket/stomp/handle-annotations.html)
- [Spring Framework — Authentication for STOMP over WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html)
- [Spring Framework — Token Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html)
- [Javadoc — Header](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/Header.html)
- [Javadoc — Headers](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/handler/annotation/Headers.html)
