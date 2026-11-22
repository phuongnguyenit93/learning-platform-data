# @Payload, Message, MessageHeaders và các header accessor

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Phân biệt payload với toàn bộ message envelope trong Spring Messaging.
- Chọn đúng giữa `Message<?>`, `MessageHeaders`, `@Payload`, `@Header` và `@Headers` trong một phương thức `@MessageMapping`.
- Đọc header chung của Spring, header phiên STOMP/Simp và native header của giao thức.
- Tạo hoặc bổ sung header đúng cách mà không sửa trực tiếp một `MessageHeaders` bất biến.
- Nhận biết các lỗi thường gặp khi chuyển đổi payload, đọc header và xử lý metadata từ client.

## 1. Vị trí của các kiểu này trong STOMP controller

Trong ứng dụng WebSocket dùng STOMP, client gửi frame đến server. Spring giải mã frame, tạo một đối tượng `Message<?>` rồi chuyển message qua các channel nội bộ. Message gửi đến destination thuộc prefix dành cho ứng dụng (thường là `/app`) có thể được định tuyến đến phương thức `@MessageMapping`. Destination dành cho broker (thường là `/topic` hoặc `/queue`) được broker xử lý theo cấu hình.

Một message có hai phần chính:

1. **Payload**: dữ liệu nghiệp vụ mà client muốn gửi, ví dụ nội dung chat hoặc dữ liệu đơn hàng.
2. **Headers**: metadata mô tả message, ví dụ destination, loại message, session, content type, message ID, timestamp và các header do ứng dụng hoặc giao thức cung cấp.

Ví dụ, một STOMP frame rút gọn có thể trông như sau:

```text
SEND
destination:/app/chat.send
content-type:application/json
x-trace-id:req-42

{"text":"Xin chào"}
```

Trong ví dụ này, phần JSON là payload. Các dòng destination, content-type và x-trace-id là header của frame. Khi Spring xử lý frame, payload có thể được chuyển thành một DTO Java; metadata được biểu diễn trong headers của `Message<?>`.

Luồng xử lý thường gặp:

1. Client gửi STOMP `SEND` đến `/app/chat.send`.
2. Spring giải mã frame và tạo message nội bộ.
3. `MessageConverter` chuyển payload sang kiểu Java mà phương thức controller yêu cầu.
4. Spring phân giải các tham số của phương thức: payload, toàn bộ message, headers hoặc accessor.
5. Phương thức xử lý nghiệp vụ và có thể trả về kết quả.
6. Nếu dùng `@SendTo`, giá trị trả về được chuyển thành payload của message gửi đến destination đã chỉ định, rồi chuyển qua broker channel.

Điểm cần nhớ: `@Payload` tập trung vào dữ liệu nghiệp vụ; `Message<?>` cho phép xem cả envelope; các header accessor giúp đọc metadata theo đúng ngữ nghĩa của Spring hoặc STOMP.

## 2. `Message<T>`: toàn bộ message envelope

`org.springframework.messaging.Message<T>` là interface biểu diễn một message tổng quát. Nó cung cấp hai phương thức:

- `T getPayload()`: lấy payload.
- `MessageHeaders getHeaders()`: lấy tập header của message.

Tham số kiểu `T` mô tả kiểu payload ở mức biên dịch. Trong lúc chạy, kiểu thực tế vẫn phụ thuộc vào cách message được tạo và bộ chuyển đổi đã dùng.

Ví dụ:

```java
Message<String> message = MessageBuilder.withPayload("hello")
        .setHeader("correlationId", "req-42")
        .build();

String body = message.getPayload();
String correlationId =
        message.getHeaders().get("correlationId", String.class);
```

Ở đây:

- `"hello"` là payload.
- `"correlationId"` là header tùy chỉnh.
- `MessageBuilder` tạo một message mới cùng headers tương ứng.

Dùng `Message<?>` trong controller khi cần truy cập toàn bộ message mà không muốn phụ thuộc vào một kiểu payload cụ thể. Cách này hữu ích cho logging có kiểm soát, tracing, kiểm tra metadata hoặc các xử lý mang tính hạ tầng.

`Message<?>` không thay thế DTO nghiệp vụ. Nếu controller cần một đối tượng có kiểu rõ ràng để kiểm tra và xử lý, hãy nhận DTO bằng `@Payload`. Nếu cần cả DTO lẫn metadata, có thể khai báo thêm các tham số tương ứng trong cùng phương thức.

Thông thường, hãy xem message như một envelope bất biến. Khi cần thay đổi payload hoặc headers, tạo message mới bằng builder hoặc accessor phù hợp thay vì cố sửa message đang được xử lý.

## 3. `@Payload`: lấy và chuyển đổi payload

`@Payload` đánh dấu tham số nhận phần thân của message. Trong STOMP controller, Spring dùng một `MessageConverter` phù hợp để chuyển payload từ dạng nhận được (chẳng hạn byte array hoặc chuỗi JSON) sang kiểu Java được khai báo.

Ví dụ client gửi JSON:

```json
{
  "text": "Xin chào"
}
```

Controller có thể nhận một DTO:

```java
public record ChatRequest(String text) {}

@MessageMapping("/chat.send")
public void send(@Payload ChatRequest request) {
    String text = request.text();
    // Xử lý nội dung chat
}
```

Với cấu hình converter phù hợp, JSON được chuyển thành `ChatRequest` trước khi phương thức chạy. `@Payload` không tự thực hiện việc parse JSON; việc chuyển đổi thuộc trách nhiệm của `MessageConverter`. Content type của message và converter được cấu hình có ảnh hưởng đến khả năng chuyển đổi.

Trong phương thức `@MessageMapping`, `@Payload` có thể được lược bỏ nếu tham số không được nhận diện bởi một resolver khác. Tuy vậy, ghi rõ annotation giúp chữ ký phương thức dễ đọc và thể hiện rõ tham số nào là dữ liệu nghiệp vụ.

### Kết hợp với validation

Có thể dùng `@Valid` hoặc `@Validated` để yêu cầu Spring kiểm tra DTO sau khi chuyển đổi:

```java
public record ChatRequest(
        @NotBlank String text
) {}

@MessageMapping("/chat.send")
public void send(@Valid @Payload ChatRequest request) {
    // Chỉ xử lý khi payload vượt qua validation
}
```

Để validation hoạt động, ứng dụng cần có Bean Validation implementation và cấu hình Spring tương ứng. Với Spring Framework 6 trở lên, dùng namespace `jakarta.validation`; dự án Spring 5 thường dùng `javax.validation`.

Validation payload không thay thế kiểm tra quyền truy cập. Một payload hợp lệ về cấu trúc vẫn có thể chứa dữ liệu mà người gửi không được phép thao tác.

## 4. `MessageHeaders`: đọc metadata của message

`org.springframework.messaging.MessageHeaders` là tập header gắn với một message. Lớp này triển khai `Map<String, Object>` nên có thể đọc theo tên khóa, nhưng **bản thân `MessageHeaders` là bất biến**. Các thao tác thay đổi như `put`, `putAll` hoặc `remove` sẽ không được hỗ trợ.

Ví dụ đọc header:

```java
MessageHeaders headers = message.getHeaders();

UUID messageId = headers.getId();
Long timestamp = headers.getTimestamp();

String correlationId =
        headers.get("correlationId", String.class);

Object contentType =
        headers.get(MessageHeaders.CONTENT_TYPE);
```

Một số header tiêu chuẩn:

| Header | Ý nghĩa |
|---|---|
| `MessageHeaders.ID` | Khóa message ID; thường là UUID do Spring quản lý |
| `MessageHeaders.TIMESTAMP` | Thời điểm tạo message, biểu diễn bằng giá trị thời gian |
| `MessageHeaders.CONTENT_TYPE` | Kiểu nội dung, thường được biểu diễn bằng `MimeType` |
| `MessageHeaders.REPLY_CHANNEL` | Kênh phản hồi nội bộ nếu message có sử dụng |
| `MessageHeaders.ERROR_CHANNEL` | Kênh xử lý lỗi nội bộ nếu message có sử dụng |

ID và timestamp là metadata do Spring quản lý và thuộc nhóm header chỉ đọc theo mặc định. Không nên cố gán lại chúng như một header nghiệp vụ thông thường. Giá trị ID hoặc timestamp có thể không có trong một số message được cấu hình đặc biệt, vì vậy hãy xử lý trường hợp null nếu logic phụ thuộc vào chúng.

Có thể lấy giá trị theo kiểu mong muốn bằng overload `get(name, Class<T>)`. Cách này giúp tránh ép kiểu thủ công:

```java
String tenantId = headers.get("tenant-id", String.class);
Integer priority = headers.get("priority", Integer.class);
```

Nếu header không tồn tại hoặc kiểu giá trị không phù hợp, kết quả có thể là `null`. Đừng giả định mọi header đều có mặt hoặc mọi giá trị đều là chuỗi.

Trong Spring Messaging, header còn có thể chứa metadata riêng của Spring, của transport hoặc của ứng dụng. Với STOMP, cần phân biệt header nội bộ của Spring với native header được giữ lại từ frame gốc; phần tiếp theo giải thích sự khác nhau này.

## 5. Các header accessor và phạm vi sử dụng

Header accessor là lớp bao quanh headers, cung cấp getter/setter có ngữ nghĩa rõ ràng và quản lý trạng thái mutable/immutable. Các lớp chính có quan hệ kế thừa như sau:

```text
MessageHeaderAccessor
    └── NativeMessageHeaderAccessor
            └── SimpMessageHeaderAccessor
                    └── StompHeaderAccessor
```

| Accessor | Phạm vi | Khi nào nên dùng |
|---|---|---|
| `MessageHeaderAccessor` | Header chung của Spring Messaging | Đọc hoặc tạo header chung, xử lý message không phụ thuộc giao thức |
| `NativeMessageHeaderAccessor` | Header nguyên bản từ hệ thống bên ngoài | Là lớp nền để lưu và truy cập native header; thường dùng gián tiếp qua accessor chuyên biệt |
| `SimpMessageHeaderAccessor` | Metadata chung của Spring Messaging đơn giản | Đọc destination, message type, session ID, session attributes, subscription ID và user |
| `StompHeaderAccessor` | Metadata đặc thù STOMP | Đọc STOMP command và native header của STOMP frame |

### 5.1. `MessageHeaderAccessor`

Đây là accessor tổng quát. Các thao tác thường dùng gồm:

- `getHeader(name)`: đọc một header.
- `setHeader(name, value)`: đặt hoặc thay giá trị header.
- `setHeaderIfAbsent(name, value)`: chỉ đặt nếu header chưa có giá trị.
- `removeHeader(name)`: xóa header.
- `getMessageHeaders()`: lấy đối tượng `MessageHeaders` nền.
- `getMutableAccessor(message)`: lấy accessor có thể chỉnh sửa dựa trên message hiện có.

Dùng accessor khi cần thao tác với headers theo cách có kiểm soát. Nếu chỉ cần tạo message mới với một vài header, `MessageBuilder` thường ngắn gọn và dễ đọc hơn.

### 5.2. `NativeMessageHeaderAccessor`

Các header đến từ giao thức hoặc hệ thống bên ngoài được giữ riêng trong một vùng native header, dưới khóa `NATIVE_HEADERS`. Dữ liệu có dạng nhiều giá trị cho một tên header, tương đương `Map<String, List<String>>`.

Các phương thức quan trọng:

- `getNativeHeader(name)`: lấy danh sách tất cả giá trị của native header.
- `getFirstNativeHeader(name)`: lấy giá trị đầu tiên.
- `setNativeHeader(name, value)`: thay các giá trị hiện có bằng một giá trị.
- `addNativeHeader(name, value)`: thêm một giá trị vào danh sách hiện có.

Một header native có thể xuất hiện nhiều lần trong một frame. Vì vậy, nếu cần toàn bộ giá trị, hãy dùng `getNativeHeader` thay vì chỉ lấy giá trị đầu tiên.

`NativeMessageHeaderAccessor` thường được sử dụng thông qua lớp con chuyên biệt cho giao thức. Với STOMP, lớp phù hợp là `StompHeaderAccessor`.

### 5.3. `SimpMessageHeaderAccessor`

`SimpMessageHeaderAccessor` cung cấp cách truy cập thống nhất cho metadata của các giao thức messaging đơn giản. Một số thông tin thường cần đọc:

- `getDestination()`: destination gắn với message.
- `getMessageType()`: loại message Simp, ví dụ message, subscribe hoặc unsubscribe.
- `getSessionId()`: ID của phiên hiện tại.
- `getSessionAttributes()`: map thuộc tính gắn với phiên.
- `getSubscriptionId()`: ID của subscription nếu có.
- `getUser()`: `Principal` gắn với phiên nếu đã được thiết lập.

Ví dụ:

```java
@MessageMapping("/chat.inspect")
public void inspect(SimpMessageHeaderAccessor headers) {
    String destination = headers.getDestination();
    String sessionId = headers.getSessionId();
    Principal user = headers.getUser();

    // Dùng metadata cho logging hoặc xử lý nghiệp vụ phù hợp
}
```

Accessor này phù hợp khi logic cần session hoặc destination nhưng không cần phụ thuộc trực tiếp vào cú pháp của STOMP.

### 5.4. `StompHeaderAccessor`

`StompHeaderAccessor` kế thừa `SimpMessageHeaderAccessor` và bổ sung thông tin đặc thù của STOMP. Một số phương thức hữu ích:

- `getCommand()`: lấy lệnh STOMP, ví dụ `SEND`, `SUBSCRIBE` hoặc `DISCONNECT`.
- `getReceipt()` và `getReceiptId()`: truy cập thông tin receipt.
- `getVersion()`: lấy phiên bản STOMP nếu có.
- `getFirstNativeHeader(name)`: lấy giá trị đầu tiên của native header.
- `getNativeHeader(name)`: lấy toàn bộ giá trị của native header.

Ví dụ đọc header tùy chỉnh do client gửi:

```java
@MessageMapping("/chat.inspect")
public void inspect(StompHeaderAccessor headers) {
    StompCommand command = headers.getCommand();
    String traceId = headers.getFirstNativeHeader("x-trace-id");
    List<String> tags = headers.getNativeHeader("x-tag");

    // Kiểm tra command, traceId hoặc tags khi cần
}
```

STOMP header gốc được giữ trong vùng native headers; một số metadata phục vụ xử lý chung được ánh xạ sang các header Simp. Vì vậy, khi cần destination hoặc session ID, dùng getter của `SimpMessageHeaderAccessor`; khi cần command hoặc header gốc của STOMP, dùng `StompHeaderAccessor`.

## 6. Ví dụ controller kết hợp payload, message và accessor

Ví dụ dưới đây minh họa một controller chat nhận DTO đã được chuyển đổi và validation, đồng thời đọc metadata từ envelope và STOMP frame.

```java
import java.util.UUID;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageHeaders;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.messaging.handler.annotation.SendTo;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.stereotype.Controller;

@Controller
public class ChatController {

    @MessageMapping("/chat.send")
    @SendTo("/topic/chat")
    public ChatEvent send(
            @Valid @Payload ChatRequest request,
            Message<?> message,
            MessageHeaders headers,
            SimpMessageHeaderAccessor simpHeaders,
            StompHeaderAccessor stompHeaders) {

        String traceId =
                stompHeaders.getFirstNativeHeader("x-trace-id");

        return new ChatEvent(
                request.text(),
                simpHeaders.getDestination(),
                simpHeaders.getSessionId(),
                traceId,
                message.getHeaders().getId(),
                headers.getTimestamp()
        );
    }
}

record ChatRequest(@NotBlank String text) {}

record ChatEvent(
        String text,
        String inboundDestination,
        String sessionId,
        String traceId,
        UUID messageId,
        Long receivedAt
) {}
```

Cách đọc ví dụ:

1. `@Payload` yêu cầu Spring chuyển payload sang `ChatRequest`.
2. `@Valid` kích hoạt Bean Validation cho DTO, với điều kiện ứng dụng đã cấu hình validation provider.
3. `Message<?>` cung cấp toàn bộ envelope; ở đây ta đọc message ID từ headers của message.
4. `MessageHeaders` cung cấp metadata ở dạng map; ví dụ lấy timestamp.
5. `SimpMessageHeaderAccessor` đọc destination và session ID theo ngữ nghĩa messaging của Spring.
6. `StompHeaderAccessor` đọc native header `x-trace-id` từ STOMP frame.
7. `@SendTo` định tuyến giá trị trả về đến `/topic/chat`. Spring dùng message converter phù hợp để chuyển đối tượng `ChatEvent` thành payload outbound.

Đây là đoạn controller tích hợp dành cho ứng dụng đã cấu hình WebSocket/STOMP, message converter và validation. Chỉ riêng đoạn mã này không phải chương trình độc lập để chạy bằng `javac`.

## 7. Tạo message và bổ sung header đúng cách

Không sửa trực tiếp `MessageHeaders`. Hãy dùng `MessageBuilder` để tạo message mới:

```java
Message<String> outgoing = MessageBuilder.withPayload("ping")
        .setHeader("correlationId", "req-42")
        .setHeaderIfAbsent("source", "chat-controller")
        .build();
```

Nếu cần dùng accessor tổng quát để tạo headers:

```java
MessageHeaderAccessor accessor = new MessageHeaderAccessor();
accessor.setHeader("correlationId", "req-42");

Message<String> outgoing = MessageBuilder.createMessage(
        "ping",
        accessor.getMessageHeaders()
);
```

Mặc định, khi gọi `getMessageHeaders()`, accessor chuyển headers sang trạng thái bất biến và không thể tiếp tục chỉnh sửa bằng accessor đó. Đây là hành vi có chủ đích để tránh việc metadata thay đổi ngoài ý muốn sau khi message đã được tạo.

Có thể gọi `setLeaveMutable(true)` nếu một quy trình khởi tạo message trong cùng luồng thực sự cần giữ headers mutable qua nhiều bước. Khi hoàn tất, phải gọi `setImmutable()` để khóa headers. Đây là cơ chế nâng cao; trong luồng xử lý thông thường, ưu tiên tạo message hoàn chỉnh bằng `MessageBuilder`.

Nếu cần làm giàu một message hiện có, hãy tạo message mới và đặt header trên builder thay vì gọi `put` trên headers của message gốc:

```java
Message<?> enriched = MessageBuilder.fromMessage(inbound)
        .setHeaderIfAbsent("correlationId", "req-42")
        .build();
```

Message mới là một envelope mới. Hãy kiểm tra chính sách giữ hoặc tạo lại các metadata như ID/timestamp của phiên bản Spring đang dùng nếu nghiệp vụ phụ thuộc vào chúng.

## 8. Chọn tham số nào trong controller?

| Nhu cầu | Tham số nên dùng | Lý do |
|---|---|---|
| Nhận DTO nghiệp vụ đã chuyển đổi | `@Payload MyDto` | Có kiểu rõ ràng, hỗ trợ message conversion và validation |
| Xem toàn bộ envelope | `Message<?>` | Có cả payload và headers |
| Đọc nhiều metadata chung | `MessageHeaders` | Truy cập headers dưới dạng map bất biến |
| Đọc một header | `@Header("headerName")` | Chữ ký gọn, có thể yêu cầu chuyển đổi kiểu |
| Đọc toàn bộ header dưới dạng map | `@Headers Map<String, Object>` | Phù hợp khi cần duyệt tập headers |
| Đọc session, destination, user | `SimpMessageHeaderAccessor` | Getter có ngữ nghĩa messaging rõ ràng |
| Đọc STOMP command hoặc native STOMP header | `StompHeaderAccessor` | Truy cập metadata đặc thù của STOMP |
| Tạo hoặc bổ sung header | `MessageBuilder` hoặc `MessageHeaderAccessor` | Quản lý trạng thái mutable/immutable đúng cách |

Không cần khai báo tất cả các loại tham số trong mọi handler. Chỉ nhận những gì phương thức thực sự cần. Một chữ ký ngắn giúp người đọc thấy ngay ranh giới giữa dữ liệu nghiệp vụ và metadata vận chuyển.

## 9. Lưu ý về bảo mật và độ tin cậy

- **Coi payload và native header từ client là dữ liệu không đáng tin cậy.** Kiểm tra định dạng, kích thước, giá trị hợp lệ và quyền thực hiện thao tác.
- **Không dùng header do client tự gửi để xác định danh tính hoặc quyền.** Không tin các giá trị như `x-user-id`, `role` hay `isAdmin`. Dùng `Principal` đã được xác thực và cơ chế Spring Security.
- **Không nhầm session ID với user ID.** Một user có thể có nhiều session; session ID chỉ nhận diện một phiên kết nối.
- **Xử lý header tùy chọn.** Header có thể vắng mặt; dùng tham số optional hoặc kiểm tra null trước khi sử dụng.
- **Giới hạn việc ghi log.** Không ghi passcode, token, thông tin cá nhân hoặc toàn bộ payload nhạy cảm. Chỉ log trace ID và metadata thực sự cần thiết.
- **Không ghép logic nghiệp vụ vào transport header.** Dữ liệu như nội dung tin nhắn, số lượng hoặc trạng thái đơn hàng nên nằm trong payload/DTO. Header phù hợp hơn cho correlation ID, trace ID, content type hoặc routing metadata.
- **Dùng accessor phù hợp với mức trừu tượng.** Ưu tiên Simp accessor cho metadata chung; chỉ dùng STOMP accessor khi cần chi tiết giao thức.

## 10. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Gọi `headers.put(...)` | `MessageHeaders` bất biến | Dùng `MessageBuilder` hoặc `MessageHeaderAccessor` |
| Không lấy được `x-trace-id` bằng khóa map thông thường | Đây là native STOMP header, được giữ trong vùng native headers | Dùng `StompHeaderAccessor.getFirstNativeHeader(...)` |
| Chỉ đọc giá trị đầu tiên trong khi header có nhiều giá trị | Native header có thể lưu nhiều giá trị | Dùng `getNativeHeader(...)` để lấy danh sách |
| `@Payload` không chuyển được JSON thành DTO | Thiếu hoặc không có converter phù hợp, content type không đúng | Kiểm tra converter và content type của message |
| Giả định header luôn tồn tại | Header tùy chọn có thể vắng mặt | Dùng `required = false` với `@Header` hoặc kiểm tra null |
| Cố sửa accessor sau khi đã lấy `getMessageHeaders()` | Accessor mặc định đã khóa headers | Hoàn tất chỉnh sửa trước khi lấy headers; chỉ dùng `setLeaveMutable(true)` khi có lý do rõ ràng |
| Dùng header client gửi để phân quyền | Client có thể tự đặt giá trị header | Dùng thông tin xác thực từ Spring Security/`Principal` |
| Dùng session ID như danh tính người dùng | Session chỉ đại diện cho một kết nối | Dùng `Principal` để xác định user |

Một lỗi đáng chú ý trong STOMP là nhầm header gốc của giao thức với header xử lý nội bộ của Spring. Nếu cần giá trị do client gửi nguyên bản, hãy kiểm tra native header bằng accessor chuyên biệt. Nếu cần thông tin routing/session do Spring quản lý, hãy dùng getter Simp tương ứng.

## 11. Bài tập tự kiểm tra

Một client gửi STOMP `SEND` đến `/app/orders.submit` với JSON chứa `orderId` và `quantity`, đồng thời gửi native header `x-correlation-id`. Handler cần:

- Nhận DTO có kiểu rõ ràng và validation.
- Đọc session ID.
- Đọc correlation ID.
- Không dùng header do client gửi để quyết định user có quyền sửa đơn hàng hay không.

Một chữ ký phù hợp:

```java
@MessageMapping("/orders.submit")
public void submit(
        @Valid @Payload OrderRequest request,
        SimpMessageHeaderAccessor simpHeaders,
        StompHeaderAccessor stompHeaders) {

    String sessionId = simpHeaders.getSessionId();
    String correlationId =
            stompHeaders.getFirstNativeHeader("x-correlation-id");

    // Kiểm tra quyền bằng Principal/Spring Security ở tầng phù hợp.
    // Sau đó xử lý request theo orderId và quantity.
}

record OrderRequest(
        @NotBlank String orderId,
        @Positive int quantity
) {}
```

Tự trả lời các câu hỏi sau:

1. Vì sao `@Payload OrderRequest` phù hợp hơn `Message<?>` nếu handler chủ yếu xử lý dữ liệu đơn hàng?
2. Vì sao `x-correlation-id` được đọc qua `StompHeaderAccessor`?
3. Vì sao không thể gọi `put` trên `MessageHeaders`?
4. Nếu handler cần cả payload và session ID, có thể khai báo cả `@Payload` lẫn `SimpMessageHeaderAccessor` không?

Đáp án:

1. DTO thể hiện cấu trúc nghiệp vụ và cho phép validation theo kiểu.
2. Đây là native header được gửi trong STOMP frame.
3. `MessageHeaders` được thiết kế bất biến; hãy tạo message mới khi cần thay đổi.
4. Có. Spring hỗ trợ các kiểu tham số này trong chữ ký `@MessageMapping`.

## 12. Ghi nhớ

- `Message<T>` là envelope gồm payload và headers.
- `@Payload` nhận payload đã được `MessageConverter` chuyển đổi; `@Valid` có thể kích hoạt validation.
- `MessageHeaders` là map bất biến với giá trị kiểu `Object`.
- `MessageHeaderAccessor` quản lý việc đọc/ghi header; `NativeMessageHeaderAccessor` giữ header từ transport.
- `SimpMessageHeaderAccessor` đọc metadata messaging chung; `StompHeaderAccessor` đọc command và native header STOMP.
- Dùng `MessageBuilder` để tạo message mới hoặc bổ sung header một cách an toàn.
- Xem mọi payload/native header từ client là dữ liệu đầu vào cần kiểm tra; dùng danh tính đã xác thực để phân quyền.

## Tài liệu tham khảo

- Spring Framework Reference — [Annotated Controllers](https://docs.spring.io/spring/reference/web/websocket/stomp/handle-annotations.html)
- Spring Framework Reference — [Flow of Messages](https://docs.spring.io/spring/reference/web/websocket/stomp/message-flow.html)
- Spring Framework Javadoc — [Message](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/Message.html)
- Spring Framework Javadoc — [MessageHeaders](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html)
- Spring Framework Javadoc — [MessageHeaderAccessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageHeaderAccessor.html)
- Spring Framework Javadoc — [NativeMessageHeaderAccessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/NativeMessageHeaderAccessor.html)
- Spring Framework Javadoc — [SimpMessageHeaderAccessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/SimpMessageHeaderAccessor.html)
- Spring Framework Javadoc — [StompHeaderAccessor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/stomp/StompHeaderAccessor.html)
