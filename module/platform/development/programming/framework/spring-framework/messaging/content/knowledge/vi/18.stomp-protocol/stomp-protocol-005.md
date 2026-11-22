# ERROR frame và kết thúc phiên do lỗi

## 1. ERROR frame là gì?

STOMP định nghĩa `ERROR` là frame do server gửi về client khi server không thể tiếp tục xử lý giao thức hoặc một frame từ client. Khác với `MESSAGE` dùng để chuyển dữ liệu nghiệp vụ và `RECEIPT` dùng để xác nhận server đã xử lý một frame, `ERROR` biểu thị lỗi ở cấp STOMP connection.

Quy tắc quan trọng nhất của STOMP 1.2: sau khi gửi `ERROR`, server **phải đóng connection ngay sau đó**. Vì vậy, client phải xem một `ERROR` frame nhận được là dấu hiệu phiên STOMP hiện tại đã kết thúc. Client không nên tiếp tục gửi `SEND`, `SUBSCRIBE`, `ACK` hay frame khác trên connection đó.

`ERROR` là server frame. Client không gửi `ERROR` để báo lỗi cho server; client có thể đóng socket hoặc kết thúc transport khi gặp lỗi phía mình.

Trong ứng dụng Spring, cần phân biệt ba loại kết quả:

- **STOMP `ERROR` frame:** lỗi ở cấp protocol/server; connection bị đóng theo STOMP.
- **Application error message:** một `MESSAGE` bình thường chứa mã lỗi nghiệp vụ; session có thể tiếp tục hoạt động.
- **Transport error hoặc WebSocket close:** kết nối mạng/WebSocket bị lỗi hoặc đóng; có thể không có `ERROR` frame nào đến client.

## 2. Cấu trúc một ERROR frame

STOMP frame có cấu trúc chung:

~~~text
COMMAND
header:value
header:value

body
\0
~~~

Ví dụ server từ chối một lệnh `SEND` tới destination không tồn tại:

~~~text
ERROR
message:destination-unavailable
receipt-id:send-42
content-type:text/plain;charset=utf-8
content-length:31

The destination is unavailable.\0
~~~

Ý nghĩa các phần:

| Thành phần | Ý nghĩa |
| --- | --- |
| `ERROR` | Command của server frame |
| `message` | Header tùy chọn; nên chứa mô tả ngắn, dễ đọc |
| `receipt-id` | Nếu lỗi liên quan tới client frame có `receipt`, giá trị này nên khớp với `receipt` của frame đó |
| `content-type` | MIME type của body, nếu có |
| `content-length` | Số byte của body, không phải số ký tự; nên có khi frame mang body |
| Body | Thông tin chi tiết bổ sung; có thể rỗng hoặc không có |
| `\0` | Byte NUL kết thúc frame |

STOMP 1.2 không yêu cầu một header bắt buộc cụ thể cho `ERROR`. Header `message` được khuyến nghị. Nếu body tồn tại, `content-type` và `content-length` được khuyến nghị; nếu body chứa byte NUL, `content-length` là bắt buộc để decoder xác định đúng ranh giới body.

Header value trong STOMP 1.2 dùng escape sequence cho `\r`, `\n`, `\c` và `\\`. Khi tạo frame thủ công, phải áp dụng đúng quy tắc escape. `content-length` đếm octet UTF-8 thực tế; không dùng `String.length()` cho nội dung có ký tự đa byte.

## 3. Khi nào server gửi ERROR?

STOMP 1.2 cho phép server gửi `ERROR` khi có lỗi và quy định server phải đóng connection sau frame đó. Những tình huống thường gặp:

- Server không chấp nhận `CONNECT`/`STOMP`, ví dụ không có protocol version chung hoặc virtual host không hợp lệ.
- Frame không đúng cú pháp, thiếu header bắt buộc hoặc chứa header escape sequence không hợp lệ.
- Client gửi command không được hỗ trợ.
- Server không thể xử lý `SEND`, ví dụ destination không hợp lệ hoặc thao tác bị từ chối.
- Server không thể tạo subscription cho `SUBSCRIBE`.
- Frame vượt giới hạn số header, chiều dài header hoặc kích thước body mà server đặt ra.
- Broker hoặc broker relay trả lỗi khiến server không thể tiếp tục xử lý connection.

Ví dụ lỗi thương lượng phiên bản:

~~~text
ERROR
message:version-not-supported
content-type:text/plain;charset=utf-8

Supported protocol versions are 1.1 and 1.2.\0
~~~

Ví dụ lỗi `SEND` có receipt:

~~~text
SEND
destination:/queue/unknown
receipt:send-42

hello\0

ERROR
message:destination-unavailable
receipt-id:send-42
content-type:text/plain;charset=utf-8

The destination cannot be resolved.\0
~~~

Trong ví dụ thứ hai, `receipt-id` giúp client xác định frame đã gây lỗi. Sau `ERROR`, server đóng connection; client phải tạo connection/STOMP session mới nếu muốn tiếp tục.

## 4. ERROR, RECEIPT và ACK có ý nghĩa khác nhau

Không nên coi các frame này là những cách xác nhận tương đương:

| Frame | Ai gửi? | Điều được xác nhận | Có kết thúc connection không? |
| --- | --- | --- | --- |
| `RECEIPT` | Server | Server đã xử lý client frame có yêu cầu receipt; receipt cũng là xác nhận tích lũy rằng các frame trước đó đã được server nhận | Không |
| `ERROR` | Server | Server gặp lỗi ở cấp STOMP và không thể tiếp tục connection theo protocol | Có; server phải đóng connection sau frame |
| `ACK` | Client | Client xác nhận đã tiêu thụ message theo subscription acknowledgement mode | Không |
| `NACK` | Client | Client từ chối xác nhận message theo acknowledgement mode | Không, nhưng broker có thể redeliver hoặc xử lý theo policy |

`RECEIPT` không chứng minh nghiệp vụ phía consumer đã hoàn tất. STOMP 1.2 mô tả receipt là xác nhận server đã xử lý frame tương ứng và là xác nhận tích lũy các frame trước đã được nhận; các frame trước đó có thể vẫn chưa được xử lý hoàn toàn.

Nếu server không xử lý được frame có `receipt`, nó có thể gửi `ERROR` với `receipt-id` tương ứng rồi đóng connection. Client cần xử lý lỗi receipt và trạng thái connection; không được đợi một `RECEIPT` thành công sau một `ERROR` cho cùng thao tác.

Spring `StompSession.send(...)` và `subscribe(...)` có thể trả về `StompSession.Receiptable`. Khi cấu hình `TaskScheduler`, client có thể đăng ký callback receipt thành công/thất bại và timeout receipt. Receipt timeout là timeout chờ xác nhận ở client; nó không tự chứng minh broker đã từ chối frame.

## 5. ERROR làm kết thúc STOMP session và connection

Một STOMP session giữ trạng thái protocol như version đã thương lượng, subscription ID, transaction ID và các thông tin liên quan. Khi server gửi `ERROR`, connection STOMP bị đóng; trạng thái session hiện tại không còn dùng được.

Với STOMP over WebSocket, server gửi `ERROR` frame trên WebSocket rồi đóng connection WebSocket. Ở phía client, có thể quan sát cả nội dung `ERROR` và sự kiện transport đóng. Không gửi thêm frame trên session cũ sau khi nhận `ERROR`.

STOMP specification có quy tắc connection lingering: server có thể đóng/reset socket rất nhanh sau frame cuối. Vì vậy client có thể không kịp nhận `ERROR` hoặc `RECEIPT` cuối cùng trước khi transport bị đóng. Ứng dụng phải xử lý cả hai đường: nhận được `ERROR` rõ ràng và chỉ nhận được transport close/error.

Không nhầm STOMP session với HTTP session đăng nhập. Kết nối STOMP/WebSocket kết thúc không nhất thiết xóa HTTP session hoặc tài khoản đăng nhập. Client có thể mở WebSocket mới và thực hiện lại STOMP `CONNECT` bằng thông tin xác thực phù hợp.

## 6. Spring xử lý lỗi ở phía server

Với `@EnableWebSocketMessageBroker`, Spring nhận WebSocket message, giải mã STOMP frame, chuyển thành Spring `Message<?>` rồi gửi vào `clientInboundChannel`. Các message có destination `/app` có thể được chuyển tới `@MessageMapping`; message `/topic` hoặc `/queue` có thể được chuyển tới broker.

`StompSubProtocolHandler` quản lý việc chuyển đổi giữa WebSocket và STOMP. Khi lỗi xảy ra trong lúc giải mã hoặc xử lý client message, Spring sử dụng `StompSubProtocolErrorHandler` để chuẩn bị error message gửi về client.

`StompEndpointRegistry.setErrorHandler(...)` cho phép thay handler mặc định. `StompSubProtocolErrorHandler` có hai điểm xử lý chính:

- `handleClientMessageProcessingError(clientMessage, ex)`: xử lý lỗi phát sinh khi Spring xử lý client message; có thể tạo hoặc ngăn gửi `ERROR`.
- `handleErrorMessageToClient(errorMessage)`: xử lý error message được gửi từ phía server tới client, ví dụ lỗi từ broker relay hoặc external broker.

Mặc định, Spring tạo STOMP `ERROR` frame cho lỗi xử lý client message. Vì STOMP yêu cầu server đóng connection sau `ERROR`, client phải kết nối lại nếu muốn tiếp tục.

### 6.1. Tùy chỉnh ERROR frame và che thông tin nội bộ

Không gửi stack trace, SQL, tên bảng, đường dẫn nội bộ, credential hoặc thông tin hạ tầng vào error body. Hãy ghi nguyên nhân chi tiết trong log server có kiểm soát và trả về mã lỗi cùng thông báo an toàn cho client.

Ví dụ cấu hình Spring Framework 6.2:

~~~java
package com.example.messaging;

import java.nio.charset.StandardCharsets;

import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.Message;
import org.springframework.messaging.simp.config.MessageBrokerRegistry;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.util.MimeTypeUtils;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;
import org.springframework.web.socket.messaging.StompSubProtocolErrorHandler;

@Configuration
@EnableWebSocketMessageBroker
public class StompServerErrorConfiguration implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setApplicationDestinationPrefixes("/app");
    }

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/stomp");
        registry.setErrorHandler(new SanitizingErrorHandler());
    }

    private static final class SanitizingErrorHandler
            extends StompSubProtocolErrorHandler {

        @Override
        protected Message<byte[]> handleInternal(
                StompHeaderAccessor errorHeaders,
                byte[] errorPayload,
                Throwable cause,
                StompHeaderAccessor clientHeaders) {

            byte[] body = "Request could not be processed"
                    .getBytes(StandardCharsets.UTF_8);
            errorHeaders.setMessage("Request failed");
            errorHeaders.setNativeHeader("error-code", "PROCESSING_FAILED");
            errorHeaders.setContentType(MimeTypeUtils.TEXT_PLAIN);
            errorHeaders.setContentLength(body.length);
            return MessageBuilder.createMessage(body, errorHeaders.getMessageHeaders());
        }
    }
}
~~~

Handler giữ command `ERROR` do Spring đã tạo, thay message/body bằng nội dung an toàn và thêm header `error-code`. Nếu cần điều tra, ghi `cause` ở log server kèm session/request ID; không chuyển nguyên exception ra client.

Ví dụ trên chỉ cấu hình endpoint và broker đơn giản để minh họa error hook. Ứng dụng thực tế cần bổ sung authentication, authorization, origin policy, broker relay hoặc broker phù hợp với hạ tầng.

### 6.2. Khi nào handler trả về null?

`handleClientMessageProcessingError(...)` có thể trả `null` để ngăn Spring gửi `ERROR` frame. Spring Javadoc nêu ví dụ gửi một notification message qua broker, chẳng hạn user destination.

Chỉ nên làm vậy khi lỗi là lỗi nghiệp vụ mà session vẫn có thể tiếp tục an toàn. Khi đó, gửi một `MESSAGE` có cấu trúc như `code`, `message`, `correlationId` và `retryable` tới `/user/queue/errors`, rồi để client hiển thị lỗi. Nếu frame sai cú pháp hoặc protocol state không còn đáng tin cậy, không nên che lỗi rồi tiếp tục dùng connection.

## 7. Lỗi nghiệp vụ và @MessageExceptionHandler

Một lỗi nghiệp vụ như “đơn hàng đã bị hủy” hoặc “người dùng không có quyền tham gia phòng chat” thường không cần kết thúc STOMP session. Hãy trả lỗi dưới dạng application message.

Ví dụ:

~~~java
public record ApplicationError(
        String code,
        String message,
        String correlationId) {
}

@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    public void send(ChatInput input) {
        if (!isAllowed(input)) {
            throw new ChatRejectedException("Chat is unavailable");
        }
        // Xử lý message hợp lệ.
    }

    @MessageExceptionHandler(ChatRejectedException.class)
    @SendToUser(value = "/queue/errors", broadcast = false)
    public ApplicationError handleChatRejected(ChatRejectedException ex) {
        return new ApplicationError(
                "CHAT_REJECTED",
                "Your message could not be sent",
                null);
    }
}
~~~

Client nhận một STOMP `MESSAGE` trên user destination chứa `ApplicationError`; connection vẫn hoạt động. `broadcast=false` giới hạn response cho session gây ra lỗi khi user có nhiều session. Cần cấu hình user destination và broker tương ứng.

`@MessageExceptionHandler` xử lý exception phát sinh trong message handler method. Nó không thay thế protocol error handler cho lỗi parse frame, lỗi negotiation hoặc lỗi ở tầng transport. Chọn cơ chế theo loại lỗi:

| Tình huống | Cách xử lý |
| --- | --- |
| Sai cú pháp STOMP, command không hợp lệ, không thể tạo subscription | STOMP `ERROR`, đóng connection |
| Broker từ chối frame hoặc protocol state lỗi | STOMP `ERROR` theo server/provider behavior |
| Validation nghiệp vụ hoặc từ chối một thao tác nhưng session còn hợp lệ | `@MessageExceptionHandler` hoặc application `MESSAGE` |
| WebSocket/network bị mất | Transport close/error callback; không nhất thiết có STOMP `ERROR` |

## 8. Client Spring nhận ERROR frame bằng StompSessionHandler

`StompSessionHandler` mở rộng `StompFrameHandler`, vì vậy nó nhận được STOMP `ERROR` frame. `StompSessionHandlerAdapter.getPayloadType(...)` mặc định trả `String.class` cho payload của `ERROR` frame. `handleFrame(...)` là callback để đọc error headers và body.

Ba callback cần phân biệt:

| Callback | Khi nào được gọi? | Dùng để làm gì? |
| --- | --- | --- |
| `handleFrame(headers, payload)` | Nhận STOMP frame như `ERROR` | Đọc header `message`, `receipt-id`, custom error code và body |
| `handleException(session, command, headers, payload, exception)` | Lỗi khi xử lý frame, ví dụ converter lỗi hoặc application `StompFrameHandler` ném exception | Ghi nhận lỗi xử lý ở client |
| `handleTransportError(session, exception)` | Lỗi tầng transport như I/O, encode/decode hoặc `ConnectionLostException` | Đánh dấu kết nối mất và bắt đầu quy trình reconnect phù hợp |

Ví dụ client handler:

~~~java
package com.example.messaging;

import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaders;
import org.springframework.messaging.simp.stomp.StompSession;
import org.springframework.messaging.simp.stomp.StompSessionHandlerAdapter;

public class ClientErrorHandler extends StompSessionHandlerAdapter {

    @Override
    public void handleFrame(StompHeaders headers, Object payload) {
        System.err.println("STOMP ERROR: " + headers.getFirst("message"));
        System.err.println("errorCode=" + headers.getFirst("error-code"));
        System.err.println("body=" + payload);
        // Đánh dấu session hiện tại là không còn dùng được.
    }

    @Override
    public void handleException(
            StompSession session,
            StompCommand command,
            StompHeaders headers,
            byte[] payload,
            Throwable exception) {
        System.err.println(
                "Frame handler failed: " + exception.getClass().getSimpleName());
    }

    @Override
    public void handleTransportError(StompSession session, Throwable exception) {
        System.err.println(
                "STOMP transport failed: " + exception.getClass().getSimpleName());
        // Đưa session vào trạng thái disconnected và lên lịch reconnect.
    }
}
~~~

Ví dụ khởi tạo client:

~~~java
WebSocketStompClient client =
        new WebSocketStompClient(new StandardWebSocketClient());
client.setMessageConverter(new StringMessageConverter());

client.connectAsync(
        "ws://localhost:8080/stomp",
        new ClientErrorHandler());
~~~

Khi nhận `ERROR`, `handleFrame` có thể được gọi trước khi underlying WebSocket đóng. Sau đó client cũng có thể nhận `handleTransportError` hoặc sự kiện đóng transport. Hãy làm logic đánh dấu disconnected và cleanup có tính idempotent để hai callback không tạo hai lần reconnect.

`handleException` không phải callback nhận STOMP `ERROR` từ server. Nó dành cho exception khi client xử lý một frame. `handleTransportError` cũng không mang ý nghĩa “server đã gửi ERROR”; nó báo lỗi ở tầng kết nối/codec.

## 9. Spring phát hiện STOMP session kết thúc

Ở server, Spring phát `SessionDisconnectEvent` khi STOMP session kết thúc. Client có thể đã gửi `DISCONNECT`, hoặc WebSocket session có thể bị đóng và Spring tự kết thúc STOMP session.

Ví dụ listener:

~~~java
@Component
public class StompSessionLifecycleListener {

    @EventListener
    public void onDisconnect(SessionDisconnectEvent event) {
        String sessionId = event.getSessionId();
        // Giải phóng subscription/resource gắn với session.
        // Thao tác cleanup phải an toàn nếu event được phát nhiều lần.
    }
}
~~~

`SessionDisconnectEvent` có thể được phát nhiều lần cho cùng một session trong một số tình huống. Cleanup phải idempotent: xóa trạng thái theo session ID, kiểm tra tồn tại trước khi giải phóng và không phát side effect lặp.

Với broker relay, Spring có thể tự kết nối lại system connection tới broker khi broker tạm ngừng hoạt động. Các client connection không tự được khôi phục; client cần tự reconnect. `BrokerAvailabilityEvent` cho biết broker relay đang sẵn sàng hay không để server tránh gửi message khi broker không khả dụng.

## 10. Reconnect sau ERROR hoặc transport failure

Vì `ERROR` kết thúc connection, reconnect phải tạo một WebSocket connection và STOMP session mới. Quy trình thông thường:

1. Đánh dấu session cũ là disconnected; ngừng gửi frame trên session đó.
2. Đóng và giải phóng resource client gắn với session cũ.
3. Phân loại lỗi: protocol/auth/configuration hay lỗi tạm thời của mạng/broker.
4. Nếu có thể phục hồi, chờ theo exponential backoff có jitter rồi mở transport mới.
5. Gửi `CONNECT` lại, xác thực và chờ `CONNECTED`.
6. Đăng ký lại các subscription cần thiết.
7. Khôi phục state ứng dụng và tiếp tục gửi command theo chính sách retry.

Không reconnect liên tục với tốc độ cao khi lỗi là `version-not-supported`, credential sai hoặc quyền truy cập bị từ chối. Các lỗi cấu hình/auth cần được sửa trước khi thử lại.

### 10.1. Không retry SEND một cách mù quáng

Nếu connection mất sau khi client gửi `SEND` nhưng trước khi nhận `RECEIPT`, client có thể không biết server đã xử lý frame hay chưa. Gửi lại một command có side effect có thể tạo tác động trùng.

Với command nghiệp vụ, gắn `requestId` hoặc `idempotencyKey` ổn định trong payload/header. Server lưu trạng thái theo key và trả kết quả cũ khi nhận lại cùng command. Dùng `receipt` để biết server đã xử lý frame ở cấp STOMP; dùng event/result message hoặc API trạng thái để biết nghiệp vụ hoàn tất.

### 10.2. Khôi phục subscription

Subscription ID thuộc connection hiện tại. Sau reconnect, client phải tạo subscription mới và quản lý handle mới. Không giả định subscription cũ tự tồn tại trên connection mới.

Nếu consumer dùng acknowledgement thủ công, cần xác định broker có thể redeliver message chưa ACK/NACK sau khi connection mất. Consumer phải idempotent và không dùng subscription ID cũ trên session mới.

## 11. Graceful DISCONNECT và ERROR khác nhau

Client có thể đóng socket trực tiếp, nhưng khi đó không có bảo đảm server đã nhận mọi frame trước đó. Để ngắt kết nối có kiểm soát theo STOMP 1.2:

~~~text
DISCONNECT
receipt:disconnect-77

\0

RECEIPT
receipt-id:disconnect-77

\0
~~~

Client chờ `RECEIPT` rồi đóng socket. Sau khi gửi `DISCONNECT`, client không được gửi thêm STOMP frame.

Graceful disconnect là thao tác chủ động, có receipt xác nhận server đã nhận/xử lý frame ngắt kết nối. `ERROR` là server báo lỗi và buộc đóng connection. Hai tình huống có thể cùng dẫn tới `SessionDisconnectEvent`, nhưng nguyên nhân và cách xử lý phía client khác nhau.

## 12. Heartbeat, WebSocket close và lỗi không có ERROR frame

Không phải mọi connection failure đều có `ERROR` frame. Ví dụ:

- TCP reset hoặc mạng mất đột ngột.
- WebSocket container đóng socket do timeout hoặc shutdown.
- Heartbeat không tới trong khoảng thời gian đã thương lượng.
- Proxy/load balancer đóng connection nhàn rỗi.
- STOMP decoder ở client phát hiện lỗi và đóng transport.
- Server process dừng trước khi kịp gửi frame cuối.

Heartbeat STOMP dùng để phát hiện peer không còn hoạt động. Khi client không nhận dữ liệu/heartbeat trong ngưỡng đã thỏa thuận, client có thể coi connection đã chết và đóng nó. Đây là phát hiện transport liveness, không phải một STOMP `ERROR` frame.

Vì vậy, code client cần có cả `handleFrame` cho ERROR và `handleTransportError`/transport close cho các lỗi không có ERROR. Không dựa duy nhất vào nội dung error body để phát hiện session kết thúc.

## 13. Bảo mật và nội dung lỗi

Error frame có thể đi tới browser hoặc client bên ngoài trust boundary. Hãy coi header và body của nó là dữ liệu công khai:

- Dùng error code ổn định như `AUTH_REQUIRED`, `DESTINATION_DENIED`, `INVALID_FRAME` hoặc `PROCESSING_FAILED`.
- Thông báo ngắn gọn, không tiết lộ stack trace, SQL, broker host, queue nội bộ, đường dẫn file, token hoặc credential.
- Không echo toàn bộ frame đầu vào nếu frame có thể chứa secret hoặc dữ liệu cá nhân.
- Log exception chi tiết phía server, gắn correlation ID/session ID và phân quyền truy cập log.
- Giới hạn kích thước error body; tránh trả về payload lớn hoặc dữ liệu do attacker kiểm soát.
- Không đưa passcode hoặc access token vào error log.

Với application error `MESSAGE`, cũng áp dụng nguyên tắc tương tự. Client không nên hiển thị nguyên văn lỗi nội bộ; dùng error code để chọn nội dung phù hợp và hướng xử lý.

## 14. Ví dụ Java 17: giải mã ERROR frame bằng StompDecoder

Ví dụ này dùng `StompDecoder` của Spring Messaging để phân tích một ERROR frame hoàn chỉnh. Chương trình không mở WebSocket hoặc broker; nó kiểm tra đúng cấu trúc STOMP frame và cách Spring trích xuất command/header/body.

Cấu trúc project:

~~~text
stomp-error-frame-demo/
  pom.xml
  src/main/java/com/example/stomp/StompErrorFrameDemo.java
  src/main/java/com/example/stomp/StompServerErrorConfiguration.java
  src/main/java/com/example/stomp/ClientErrorHandler.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>stomp-error-frame-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.18</spring.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-websocket</artifactId>
            <version>${spring.version}</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/com/example/stomp/StompErrorFrameDemo.java`:

~~~java
package com.example.stomp;

import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.List;

import org.springframework.messaging.Message;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompDecoder;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;

public final class StompErrorFrameDemo {
    private StompErrorFrameDemo() {
    }

    public static void main(String[] args) {
        String body = "The destination is unavailable.";
        String wire = "ERROR\n"
                + "message:destination-unavailable\n"
                + "receipt-id:send-42\n"
                + "content-type:text/plain;charset=utf-8\n"
                + "content-length:" + body.getBytes(StandardCharsets.UTF_8).length + "\n"
                + "\n"
                + body
                + '\0';

        List<Message<byte[]>> frames = new StompDecoder().decode(
                ByteBuffer.wrap(wire.getBytes(StandardCharsets.UTF_8)));
        if (frames.size() != 1) {
            throw new IllegalStateException(
                    "Expected one complete STOMP frame, got " + frames.size());
        }

        Message<byte[]> frame = frames.get(0);
        StompHeaderAccessor headers = StompHeaderAccessor.wrap(frame);
        if (headers.getCommand() != StompCommand.ERROR) {
            throw new IllegalStateException(
                    "Expected ERROR frame, got " + headers.getCommand());
        }

        System.out.println("command=" + headers.getCommand());
        System.out.println("message=" + headers.getMessage());
        System.out.println("receiptId=" + headers.getReceiptId());
        System.out.println("body=" +
                new String(frame.getPayload(), StandardCharsets.UTF_8));
    }
}
~~~

`StompServerErrorConfiguration.java` và `ClientErrorHandler.java` lần lượt minh họa cấu hình server error handler và callback client ở các phần 6.1 và 8; đặt chúng cùng package như cấu trúc project để biên dịch toàn bộ ví dụ.

Chạy bằng JDK 17+ và Maven:

~~~bash
mvn -q compile exec:java "-Dexec.mainClass=com.example.stomp.StompErrorFrameDemo"
~~~

Stdout:

~~~text
command=ERROR
message=destination-unavailable
receiptId=send-42
body=The destination is unavailable.
~~~

Ví dụ dùng `content-length` được tính từ số byte UTF-8 của body và kết thúc frame bằng NUL. `StompDecoder` trả Spring `Message<byte[]>`; `StompHeaderAccessor` đọc command và các header STOMP. Khi frame không đầy đủ, decoder có thể trả danh sách rỗng và caller phải buffer phần còn lại trước khi decode tiếp.

## 15. Lỗi thường gặp

- **Coi ERROR là một MESSAGE thông thường:** STOMP `ERROR` là lỗi protocol và server phải đóng connection sau khi gửi.
- **Tiếp tục gửi frame trên session cũ:** sau ERROR, hãy coi session đã kết thúc và tạo connection mới.
- **Nhầm ERROR frame với WebSocket close reason:** WebSocket có thể đóng mà không có STOMP ERROR; xử lý cả transport callback.
- **Dùng ERROR cho mọi lỗi validation:** lỗi nghiệp vụ thường nên trả application MESSAGE để session còn hoạt động.
- **Cho rằng `@MessageExceptionHandler` bắt lỗi parse/protocol:** nó xử lý exception trong message handler; protocol error cần handler ở tầng STOMP.
- **Đưa stack trace hoặc SQL vào body:** client có thể nhìn thấy; hãy trả error code và thông báo an toàn.
- **Bỏ qua `receipt-id`:** khi có receipt, header này giúp xác định frame đã gây lỗi.
- **Coi RECEIPT là xử lý nghiệp vụ hoàn tất:** receipt chỉ xác nhận xử lý frame ở cấp server/protocol.
- **Chờ ERROR frame luôn tới trước khi socket đóng:** connection lingering có thể khiến frame cuối bị mất.
- **Chỉ cài `handleTransportError`:** callback này không thay thế `handleFrame` để đọc ERROR frame.
- **Nhầm `handleException` với ERROR frame:** đây là exception khi client xử lý frame/converter hoặc callback.
- **Không reconnect/resubscribe:** connection mới không tự mang theo subscription ID cũ.
- **Retry SEND mà không có idempotency key:** thao tác có side effect có thể chạy lặp khi kết quả lần gửi trước không xác định.
- **Cleanup session không idempotent:** `SessionDisconnectEvent` có thể được phát nhiều lần.
- **Không phân loại lỗi tạm thời và lỗi cấu hình:** reconnect vô hạn với credential sai hoặc protocol version không tương thích tạo tải không cần thiết.

## 16. Checklist vận hành

1. Server có gửi `ERROR` với header `message` ngắn gọn và body an toàn không?
2. Nếu lỗi liên quan frame có `receipt`, `receipt-id` có khớp giá trị receipt không?
3. Body có `content-type`, `content-length` đúng số byte UTF-8 và NUL terminator không?
4. Server có đóng connection sau ERROR theo STOMP 1.2 không?
5. Client có dừng gửi trên session cũ ngay khi nhận ERROR không?
6. Client có phân biệt `handleFrame`, `handleException` và `handleTransportError` không?
7. Ứng dụng có phân biệt lỗi protocol với lỗi nghiệp vụ cần application MESSAGE không?
8. `StompSubProtocolErrorHandler` có che thông tin nhạy cảm không?
9. Có log server đủ chi tiết với session ID/correlation ID nhưng không lộ secret không?
10. Có xử lý transport close khi ERROR frame cuối không tới client không?
11. Reconnect có backoff, jitter và phân loại lỗi permanent/transient không?
12. Client có gửi CONNECT/authentication và đăng ký lại subscription sau reconnect không?
13. Command có side effect có idempotency key để retry an toàn không?
14. `SessionDisconnectEvent` cleanup có idempotent không?
15. Có kiểm thử malformed frame, version mismatch, destination denied, broker outage, heartbeat timeout và socket reset không?

## 17. Ghi nhớ

STOMP `ERROR` là server frame dùng để báo lỗi ở cấp protocol; theo STOMP 1.2, server phải đóng connection ngay sau khi gửi frame này. Header `message` mô tả ngắn lỗi, body có thể chứa chi tiết và `receipt-id` có thể liên kết lỗi với client frame đã yêu cầu receipt. Spring server dùng `StompSubProtocolErrorHandler` để tạo, tùy chỉnh hoặc ngăn gửi ERROR; nếu muốn session tiếp tục sau lỗi nghiệp vụ, hãy gửi application `MESSAGE` bằng `@MessageExceptionHandler` hoặc user destination. Spring client nhận ERROR qua `StompSessionHandler.handleFrame`; `handleException` xử lý lỗi callback/conversion và `handleTransportError` xử lý lỗi transport. Sau ERROR, tạo STOMP session mới, xác thực và subscribe lại; retry command có side effect phải dùng idempotency key.

### Tài liệu tham khảo

- [STOMP 1.2 Specification — ERROR frames and connection behavior](https://stomp.github.io/stomp-specification-1.2.html)
- [Spring Framework 6.2 — STOMP over WebSocket](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp.html)
- [Spring Framework 6.2 — Application Context Events](https://docs.spring.io/spring-framework/reference/6.2/web/websocket/stomp/application-context-events.html)
- [Spring Framework 6.2.14 — StompSubProtocolErrorHandler Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/web/socket/messaging/StompSubProtocolErrorHandler.html)
- [Spring Framework 6.2.14 — StompSessionHandlerAdapter Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/messaging/simp/stomp/StompSessionHandlerAdapter.html)
- [Spring Framework 6.2.14 — StompDecoder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/messaging/simp/stomp/StompDecoder.html)