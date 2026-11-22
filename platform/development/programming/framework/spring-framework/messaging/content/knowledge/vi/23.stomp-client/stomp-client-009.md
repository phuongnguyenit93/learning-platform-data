# Phân biệt lỗi frame, lỗi xử lý và lỗi transport

> Phạm vi: Spring Framework STOMP over WebSocket và client STOMP.js hoặc Spring WebSocketStompClient. Bài học phân loại lỗi theo nơi phát sinh, dấu hiệu quan sát được và cách xử lý. Một lỗi nghiệp vụ ở server đôi khi được chuyển thành STOMP ERROR frame, vì vậy cần phân biệt nguyên nhân gốc với hình thức lỗi mà client nhận được.

## 1. Ba lớp cần phân biệt

Một kết nối STOMP chạy trên WebSocket có ít nhất ba lớp:

1. **Transport (vận chuyển)**: kết nối mạng và WebSocket giữa client với endpoint server. Lỗi ở đây gồm DNS, TLS, HTTP handshake, proxy, socket đóng hoặc mất kết nối.
2. **STOMP frame/protocol**: cấu trúc frame, command, header, body và quy tắc giao thức. Lỗi có thể do frame sai cú pháp, thiếu header bắt buộc, phiên bản không tương thích hoặc broker từ chối một command.
3. **Application processing (xử lý ứng dụng)**: Spring định tuyến frame hợp lệ đến controller, chuyển đổi payload, kiểm tra dữ liệu và chạy logic nghiệp vụ. Lỗi có thể do validation, quyền nghiệp vụ, database hoặc code trong handler.

Ba lớp liên quan với nhau nhưng không đồng nghĩa. Một lỗi xử lý nghiệp vụ có thể được server chuyển thành một STOMP ERROR frame. Ngược lại, WebSocket bị ngắt có thể khiến client không nhận được ERROR frame dù server có lỗi trước đó.

## 2. Lỗi frame và lỗi giao thức STOMP

STOMP là giao thức dựa trên frame. Một frame có command, các header tùy chọn, dòng trống phân tách header và body tùy loại frame, kết thúc bằng NULL byte. Ví dụ SEND:

~~~text
SEND
destination:/app/orders
content-type:application/json

{"orderId":"O-42"}^@
~~~

Một số lỗi frame/protocol thường gặp:

- Frame không có command hợp lệ hoặc thiếu dòng trống phân tách header và body.
- Header sai định dạng, escape sequence không hợp lệ hoặc kết thúc frame sai.
- SEND thiếu header destination.
- SUBSCRIBE thiếu destination hoặc id, hoặc dùng subscription id trùng trong cùng connection.
- Client và server không có STOMP version chung.
- Command hoặc header không được broker hỗ trợ.
- Frame vượt giới hạn kích thước hoặc vi phạm quy tắc giao thức.

Cần phân biệt **lỗi cú pháp frame** với **lỗi broker từ chối command**. Một frame có thể đúng cú pháp nhưng vẫn bị từ chối vì destination không tồn tại, tài khoản không có quyền SUBSCRIBE, thông tin xác thực không hợp lệ hoặc broker không hỗ trợ tính năng được yêu cầu.

### ERROR frame

Khi server/broker gửi STOMP ERROR frame, frame thường có header message mô tả ngắn và body chứa chi tiết hơn:

~~~text
ERROR
message:Subscription denied
content-type:text/plain

The user is not authorized to subscribe to this destination.^@
~~~

Theo STOMP 1.2, server gửi ERROR frame rồi đóng connection. Vì vậy, client thường quan sát cả callback nhận STOMP ERROR và sự kiện WebSocket đóng ngay sau đó. Không nên chỉ nhìn sự kiện đóng rồi kết luận đây là sự cố mạng; hãy kiểm tra xem trước đó client có nhận ERROR frame hay không.

Một ERROR frame cho biết server/broker báo lỗi ở tầng STOMP. Nó không đảm bảo nguyên nhân là parser: lỗi xác thực, phân quyền hoặc xử lý message phía server cũng có thể được biểu diễn bằng ERROR frame.

### Dấu hiệu và hướng điều tra

| Dấu hiệu | Kiểm tra |
|---|---|
| ERROR có message nói thiếu destination hoặc header | Kiểm tra command, header và frame client gửi. |
| ERROR nhắc đến version hoặc CONNECT | Kiểm tra accept-version, host/vhost và phiên bản STOMP được hỗ trợ. |
| ERROR nhắc đến quyền hoặc authentication | Kiểm tra CONNECT headers, HTTP handshake auth, Principal và quyền SEND/SUBSCRIBE. |
| ERROR nhắc đến destination | Kiểm tra prefix /app, /topic, /queue, destination mapping và broker ACL. |
| ERROR sau khi gửi frame lớn | Kiểm tra giới hạn kích thước WebSocket/STOMP ở client, Spring, proxy và broker. |

## 3. Lỗi xử lý ứng dụng

Khi client gửi frame hợp lệ đến destination ứng dụng, Spring có thể định tuyến message đến @MessageMapping. Ví dụ:

~~~java
@Controller
public class OrderController {

    @MessageMapping("/orders")
    public OrderResult create(OrderRequest request) {
        if (request.quantity() <= 0) {
            throw new InvalidOrderException("Quantity must be positive");
        }

        return orderService.create(request);
    }
}
~~~

Nếu payload không chuyển đổi được, validation thất bại hoặc service ném exception, lỗi phát sinh trong quá trình xử lý message của ứng dụng. Đây là lỗi xử lý, dù server có thể đóng gói nó thành ERROR frame ở tầng STOMP để báo cho client.

### Xử lý exception bằng @MessageExceptionHandler

Nếu muốn trả lỗi nghiệp vụ theo một schema ổn định mà client có thể xử lý, khai báo @MessageExceptionHandler và gửi payload lỗi qua một destination riêng:

~~~java
import org.springframework.messaging.handler.annotation.MessageExceptionHandler;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
public class OrderController {

    public record OrderRequest(String orderId, int quantity) {}
    public record OrderResult(String orderId, String status) {}
    public record ApplicationError(String code, String message) {}

    @MessageMapping("/orders")
    public OrderResult create(OrderRequest request) {
        if (request.quantity() <= 0) {
            throw new InvalidOrderException("Quantity must be positive");
        }
        return orderService.create(request);
    }

    @MessageExceptionHandler(InvalidOrderException.class)
    @SendToUser("/queue/errors")
    public ApplicationError handleInvalidOrder(InvalidOrderException ex) {
        return new ApplicationError("INVALID_ORDER", ex.getMessage());
    }
}
~~~

Đây là ví dụ minh họa; InvalidOrderException và orderService là thành phần nghiệp vụ của ứng dụng. Client đã xác thực có thể subscribe /user/queue/errors để nhận lỗi có cấu trúc.

@MessageExceptionHandler xử lý exception phát sinh từ các phương thức @MessageMapping trong controller tương ứng. Có thể đặt handler dùng chung cho nhiều controller bằng @ControllerAdvice. Chỉ trả thông tin lỗi an toàn cho client; ghi stack trace và chi tiết nội bộ vào log server.

Nếu exception không được xử lý ở tầng controller, Spring STOMP sub-protocol handler mặc định có thể tạo ERROR frame rồi đóng WebSocket session. Có thể tùy chỉnh việc tạo lỗi gửi về client bằng StompSubProtocolErrorHandler. Vì thế, khi thấy STOMP ERROR, hãy tìm log server và exception gốc trước khi phân loại nó là lỗi cú pháp frame.

### Những lỗi xử lý phổ biến

- JSON hợp lệ về cú pháp nhưng thiếu trường nghiệp vụ bắt buộc.
- Giá trị enum, ngày giờ hoặc kiểu dữ liệu không phù hợp với DTO.
- @MessageMapping không xử lý được do logic nghiệp vụ ném exception.
- Người dùng có quyền kết nối nhưng không có quyền thực hiện hành động cụ thể.
- Database, cache hoặc dịch vụ bên ngoài không khả dụng.
- Code trong callback nhận MESSAGE phía client ném exception khi parse hoặc render payload.

Lỗi parse JSON ở callback phía client là lỗi xử lý phía client. Nó không tự động có nghĩa broker gửi STOMP ERROR. Hãy phân biệt JSON.parse thất bại trong ứng dụng với client nhận một frame có command ERROR từ server.

## 4. Lỗi transport và vòng đời WebSocket

Transport error xảy ra ở tầng kết nối bên dưới STOMP. Ví dụ:

- DNS không phân giải được host hoặc TCP connection bị từ chối.
- TLS certificate không hợp lệ hoặc TLS handshake thất bại.
- HTTP Upgrade handshake trả 401, 403, 404 hoặc 5xx.
- Reverse proxy, load balancer hoặc firewall đóng kết nối.
- Mạng client thay đổi, laptop sleep, Wi-Fi chập chờn hoặc server restart.
- Heartbeat timeout cho thấy phía bên kia không còn phản hồi trong khoảng thời gian kỳ vọng.

Ở giai đoạn HTTP handshake, STOMP CONNECT chưa được gửi nên không thể có STOMP ERROR frame cho lần kết nối đó. Hãy xem Network tab để kiểm tra request WebSocket, status handshake, TLS và response headers. Sau khi WebSocket đã mở, lỗi transport thường thể hiện qua WebSocket error/close hoặc callback transport của client.

Một WebSocket CloseEvent có code và reason, nhưng browser có thể không cung cấp đầy đủ chi tiết nguyên nhân. WebSocket error event cũng thường ít thông tin. Cần đối chiếu thời điểm đóng với log server, proxy, broker và heartbeat.

## 5. Nhận biết ba loại lỗi trong STOMP.js

Với thư viện @stomp/stompjs, các callback quan trọng là:

- onStompError(frame): client nhận STOMP ERROR frame từ server/broker. Xem frame.headers.message và frame.body.
- onWebSocketError(event): WebSocket bên dưới phát error event.
- onWebSocketClose(event): WebSocket đóng; xem code, reason và wasClean nếu browser cung cấp.
- onHeartbeatLost(): client không nhận heartbeat trong khoảng kỳ vọng.
- onUnhandledMessage(message): có MESSAGE frame nhưng không có subscription handler phù hợp.
- onUnhandledFrame(frame): nhận frame không được client xử lý như các frame thông thường.

Ví dụ cấu hình client:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
    brokerURL: "wss://example.com/ws",
    reconnectDelay: 5000,

    onConnect: () => {
        console.info("STOMP connected");

        client.subscribe("/user/queue/errors", frame => {
            try {
                const error = JSON.parse(frame.body);
                console.error("Application error:", error.code, error.message);
            } catch (exception) {
                console.error("Cannot parse application error payload", exception);
            }
        });
    },

    onStompError: frame => {
        console.error("STOMP ERROR:", frame.headers.message);
        console.error("Broker/server detail:", frame.body);
    },

    onWebSocketError: event => {
        console.error("WebSocket transport error:", event);
    },

    onWebSocketClose: event => {
        console.warn("WebSocket closed:", {
            code: event.code,
            reason: event.reason,
            wasClean: event.wasClean
        });
    },

    onHeartbeatLost: () => {
        console.warn("STOMP heartbeat lost");
    }
});

client.activate();
~~~

onConnect được gọi lại sau mỗi lần kết nối STOMP thành công, vì vậy đăng ký subscription trong callback này giúp client subscribe lại sau reconnect. Nếu đăng ký subscription bên ngoài onConnect, cần chủ động khôi phục chúng khi session mới được tạo.

reconnectDelay bật cơ chế thử kết nối lại sau khi connection rớt. Hãy chọn delay phù hợp và cân nhắc exponential backoff cùng jitter trong hệ thống có nhiều client để tránh tất cả client reconnect đồng thời. Reconnect chỉ khôi phục connection; nó không tự khôi phục trạng thái ứng dụng hoặc bảo đảm một SEND trước đó đã được xử lý.

## 6. Nhận biết lỗi trong Spring WebSocketStompClient

Với Spring client Java, StompSessionHandler có ba đường xử lý riêng:

| Callback | Ý nghĩa |
|---|---|
| handleFrame | Nhận STOMP frame từ server, bao gồm ERROR frame. |
| handleException | Exception khi client xử lý frame, ví dụ lỗi chuyển đổi payload hoặc exception trong StompFrameHandler. |
| handleTransportError | Lỗi tầng transport thấp, như I/O hoặc connection lost; cũng có thể gồm lỗi encode/decode STOMP ở tầng transport client. |

Ví dụ handler tập trung ghi nhận ERROR frame và lỗi transport:

~~~java
import java.lang.reflect.Type;

import org.springframework.messaging.simp.stomp.StompHeaders;
import org.springframework.messaging.simp.stomp.StompSession;
import org.springframework.messaging.simp.stomp.StompSessionHandlerAdapter;

public class LoggingStompSessionHandler extends StompSessionHandlerAdapter {

    @Override
    public Type getPayloadType(StompHeaders headers) {
        // StompSessionHandlerAdapter dùng String cho payload của ERROR frame.
        return String.class;
    }

    @Override
    public void handleFrame(StompHeaders headers, Object payload) {
        System.err.println("STOMP ERROR: " + headers.getFirst("message"));
        System.err.println("Detail: " + payload);
    }

    @Override
    public void handleException(
            StompSession session,
            org.springframework.messaging.simp.stomp.StompCommand command,
            StompHeaders headers,
            byte[] payload,
            Throwable exception) {

        System.err.println("Client frame processing failed: " + exception.getMessage());
    }

    @Override
    public void handleTransportError(StompSession session, Throwable exception) {
        System.err.println("STOMP transport failed: " + exception.getMessage());
    }
}
~~~

Ví dụ trên dành cho handler theo dõi ERROR frame; trong ứng dụng thực tế, payload type của các subscription MESSAGE cần được khai báo đúng DTO hoặc được xử lý bởi StompFrameHandler riêng. handleException không phải callback thay thế cho ERROR frame từ broker. handleTransportError cũng không phải nơi xử lý lỗi nghiệp vụ trong controller server.

## 7. Receipt không đồng nghĩa xử lý nghiệp vụ thành công

STOMP có thể dùng header receipt để client yêu cầu server gửi RECEIPT frame sau khi frame tương ứng đã được xử lý ở tầng giao thức:

~~~text
SEND
destination:/app/orders
receipt:send-order-42
content-type:application/json

{"orderId":"O-42"}^@
~~~

Server có thể phản hồi:

~~~text
RECEIPT
receipt-id:send-order-42

^@
~~~

RECEIPT xác nhận frame tương ứng đã được server xử lý ở mức giao thức. Nó không chứng minh logic nghiệp vụ đã hoàn tất thành công, transaction database đã commit hoặc người nhận cuối cùng đã đọc message.

Nếu cần biết kết quả nghiệp vụ, hãy thiết kế response riêng có correlation/request id, ví dụ orderId hoặc requestId, rồi trả về payload success/error qua destination ứng dụng. Đừng dùng RECEIPT thay cho kết quả nghiệp vụ.

## 8. Quy trình chẩn đoán theo thứ tự

Khi client báo “không nhận được message”, kiểm tra theo trình tự:

1. **WebSocket có mở không?** Kiểm tra HTTP Upgrade, TLS, proxy và CloseEvent. Nếu handshake thất bại, xử lý transport/auth trước STOMP.
2. **STOMP CONNECT có nhận CONNECTED không?** Nếu không, xem ERROR frame, version negotiation, host/vhost và thông tin xác thực.
3. **Client SEND/SUBSCRIBE có đúng frame không?** Kiểm tra command, destination, id, content-type, body và subscription id.
4. **Có nhận ERROR frame không?** Ghi lại header message, body, thời điểm và command trước đó. Kiểm tra broker log và server log.
5. **Controller có được gọi không?** Nếu không, kiểm tra application prefix, mapping, converter, channel interceptor và quyền truy cập.
6. **Handler có ném exception không?** Kiểm tra validation, service, database và @MessageExceptionHandler.
7. **Server có phát MESSAGE không?** Kiểm tra destination outbound, broker và subscription.
8. **Client có nhận MESSAGE nhưng xử lý thất bại không?** Kiểm tra subscription callback, JSON parsing, payload type và UI code.
9. **Có mất heartbeat hoặc connection giữa chừng không?** Đối chiếu log hai đầu, proxy timeout và reconnect timeline.

Trong môi trường phát triển, bật debug logging có chọn lọc cho STOMP client và Spring WebSocket/Messaging để thấy frame direction và destination. Raw frame log có thể chứa payload, token hoặc dữ liệu cá nhân; không bật hoặc lưu chúng ở production nếu chưa có biện pháp che dữ liệu nhạy cảm.

## 9. Bảng phân loại nhanh

| Nhóm lỗi | Dấu hiệu chính | Nơi xử lý đầu tiên |
|---|---|---|
| Frame/protocol | STOMP ERROR, command/header sai, version hoặc destination bị từ chối | Kiểm tra raw STOMP frame, broker response và STOMP version. |
| Application processing | Handler exception, validation, payload conversion hoặc lỗi nghiệp vụ | Kiểm tra server log, DTO/converter, controller và service; trả lỗi có cấu trúc nếu phù hợp. |
| Client processing | MESSAGE đã nhận nhưng callback hoặc JSON parsing thất bại | Kiểm tra subscription handler, payload type và code client. |
| Transport | Handshake thất bại, WebSocket close/error, I/O exception, heartbeat lost | Kiểm tra network, TLS, proxy, server availability và reconnect. |

Một số sự kiện có thể xuất hiện liên tiếp. Ví dụ, handler server ném exception, Spring tạo ERROR frame rồi đóng WebSocket. Client thấy onStompError trước onWebSocketClose. Nguyên nhân gốc là lỗi xử lý server; ERROR frame là cách thông báo ở tầng STOMP; WebSocket close là hậu quả ở tầng transport.

## 10. Retry và phục hồi an toàn

Không phải mọi lỗi đều nên retry theo cùng một cách:

- **Frame/protocol error**: sửa frame, destination, version hoặc quyền. Retry nguyên frame sai thường chỉ lặp lại lỗi.
- **Application validation/business error**: sửa dữ liệu hoặc hiển thị lỗi cho người dùng. Không retry tự động khi dữ liệu không hợp lệ.
- **Application transient error**: có thể retry nếu nghiệp vụ cho phép, nhưng cần idempotency key hoặc request id để tránh tạo giao dịch trùng.
- **Transport error**: reconnect với backoff; sau khi CONNECTED, đăng ký lại subscription và đồng bộ trạng thái cần thiết.
- **Kết quả SEND không rõ ràng do connection mất**: server có thể đã nhận và xử lý frame trước khi connection rớt. Không gửi lại lệnh không idempotent một cách mù quáng; tra cứu request id hoặc trạng thái nghiệp vụ trước.

Nếu cần bảo đảm xử lý một lần theo nghiệp vụ, thiết kế idempotency ở tầng ứng dụng và lưu trạng thái xử lý. WebSocket reconnect hay STOMP receipt không tự cung cấp exactly-once business processing.

## 11. Tự kiểm tra

1. Client nhận ERROR frame có header message: Access denied, rồi WebSocket đóng. Nên kiểm tra điều gì trước?
2. Client không nhận ERROR nhưng onWebSocketClose báo code đóng bất thường. Nên điều tra lớp nào?
3. Server @MessageMapping ném InvalidOrderException, và @MessageExceptionHandler trả JSON đến /user/queue/errors. Đây là loại xử lý nào?
4. Spring Java STOMP client không chuyển đổi được body của MESSAGE sang DTO. Callback nào nhận exception?
5. RECEIPT sau SEND có chứng minh order đã commit trong database không?
6. Một callback STOMP.js nhận MESSAGE nhưng JSON.parse ném exception. Đây là broker ERROR hay lỗi xử lý client?

Đáp án:

1. Kiểm tra quyền CONNECT/SUBSCRIBE/SEND, Principal, destination ACL và body của ERROR frame; đây là broker/server báo từ chối ở tầng STOMP.
2. Điều tra transport: network, TLS, proxy, server restart và heartbeat; đồng thời kiểm tra xem có ERROR frame ngay trước khi đóng hay không.
3. Lỗi xử lý ứng dụng được ánh xạ thành application error payload.
4. StompSessionHandler.handleException.
5. Không. RECEIPT xác nhận frame được xử lý ở tầng giao thức, không xác nhận transaction nghiệp vụ commit.
6. Lỗi xử lý phía client trong callback, không tự động là STOMP ERROR từ broker.

## Tài liệu tham khảo

- [STOMP Protocol Specification 1.2](https://stomp.github.io/stomp-specification-1.2.html): cấu trúc frame, header bắt buộc, ERROR, RECEIPT, kết nối và quy tắc đóng connection.
- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html): @MessageMapping và @MessageExceptionHandler.
- [Spring Framework — STOMP Client](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html): StompSessionHandler, handleFrame, handleException, handleTransportError, receipt và giới hạn message size.
- [Spring Framework — StompSessionHandler Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/stomp/StompSessionHandler.html): callback của ERROR frame, exception xử lý frame và transport error.
- [Spring Framework — StompSubProtocolHandler source](https://github.com/spring-projects/spring-framework/blob/main/spring-websocket/src/main/java/org/springframework/web/socket/messaging/StompSubProtocolHandler.java): hành vi xử lý lỗi và gửi ERROR frame mặc định phía server.
- [STOMP.js Client API](https://stomp-js.github.io/api-docs/latest/classes/Client.html): onStompError, onWebSocketError, onWebSocketClose, heartbeat và reconnect.
