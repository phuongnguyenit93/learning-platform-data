# Header SIMP và header STOMP native khi gửi

## 1. Hai lớp header trong Spring Messaging

Một message trong Spring Messaging có thể mang hai nhóm metadata:

- **SIMP headers** là metadata chuẩn hóa ở tầng Spring, dùng để định tuyến và xử lý message. Ví dụ: `simpDestination`, `simpMessageType`, `simpSessionId`, `simpUser`, `simpSubscriptionId` và `simpMessageId`.
- **STOMP native headers** là các header thuộc giao thức STOMP, được giữ trong map lồng dưới khóa `nativeHeaders` (hằng `NativeMessageHeaderAccessor.NATIVE_HEADERS`). Ví dụ: `content-type`, `receipt`, `priority` hoặc header tùy chỉnh của ứng dụng.

Hai nhóm cùng tồn tại trong `MessageHeaders`, nhưng có mục đích khác nhau. SIMP headers mô tả message theo mô hình Spring; native headers mang thông tin ở lớp giao thức STOMP. Một header SIMP không tự động trở thành header STOMP, và native header không tự động trở thành thuộc tính định tuyến của Spring.

## 2. Header SIMP thường gặp

SIMP là viết tắt của Simple Messaging Protocol. Đây là mô hình message của Spring, thường gặp trong ứng dụng WebSocket/STOMP.

| Header | Ý nghĩa |
|---|---|
| `simpDestination` | Đích logic, ví dụ `/topic/updates` hoặc `/queue/notifications`. |
| `simpMessageType` | Loại message trong Spring, ví dụ `MESSAGE`, `SUBSCRIBE`. |
| `simpSessionId` | Mã phiên WebSocket/Spring khi có phiên người dùng. |
| `simpUser` | Principal gắn với phiên hoặc message, nếu có. |
| `simpSubscriptionId` | Mã subscription liên quan đến message. |
| `simpMessageId` | Định danh message do Spring quản lý, nếu được thiết lập. |

Khi gửi, destination thường được biểu diễn bằng SIMP metadata. `SimpMessagingTemplate` và broker dùng metadata này để xử lý message trong Spring. Hãy để Spring quản lý các trường nội bộ như session, subscription và message id; không tự gán chúng để giả lập một phiên hay subscription.

## 3. STOMP native headers là gì?

STOMP là giao thức truyền message dạng frame. Một frame có command, header và body. Ví dụ, client gửi frame `SEND` có thể mang `destination`, `content-type`, `receipt` và các header tùy chỉnh. Khi Spring nhận frame STOMP, các header giao thức được giữ trong vùng native headers để ứng dụng có thể đọc hoặc chuyển tiếp.

`NativeMessageHeaderAccessor` cung cấp các API chính:

- `setNativeHeader(name, value)`: đặt một giá trị native header.
- `addNativeHeader(name, value)`: thêm giá trị; một header có thể có nhiều giá trị.
- `getNativeHeader(name)`: lấy danh sách giá trị.
- `toNativeHeaderMap()`: lấy map native headers.

Tên header native được giữ theo tên giao thức. Ví dụ, `setNativeHeader("x-trace-id", "abc-123")` tạo native header `x-trace-id`; nó không tạo một SIMP header tương ứng.

## 4. Tạo message gửi đi với cả SIMP và native headers

Tạo accessor cho message Spring, đặt destination ở lớp SIMP và đặt metadata giao thức bằng `setNativeHeader`:

```java
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.messaging.simp.SimpMessageType;
import org.springframework.messaging.simp.SimpMessagingTemplate;

public class NotificationSender {
    private final SimpMessagingTemplate messagingTemplate;

    public NotificationSender(SimpMessagingTemplate messagingTemplate) {
        this.messagingTemplate = messagingTemplate;
    }

    public void sendUpdate(String jsonPayload) {
        SimpMessageHeaderAccessor headers =
                SimpMessageHeaderAccessor.create(SimpMessageType.MESSAGE);

        // SIMP metadata: Spring dùng destination để định tuyến.
        headers.setDestination("/topic/updates");

        // Native metadata: thuộc lớp giao thức STOMP.
        headers.setNativeHeader("x-event-type", "inventory-updated");
        headers.setNativeHeader("x-trace-id", "trace-123");

        // Cho phép template hoàn thiện headers khi gửi.
        headers.setLeaveMutable(true);

        messagingTemplate.convertAndSend(
                "/topic/updates",
                jsonPayload,
                headers.getMessageHeaders()
        );
    }
}
```

Đây là ví dụ gửi từ server. `SimpMessagingTemplate` cần được cấu hình trong ứng dụng messaging, thường qua `@EnableWebSocketMessageBroker`. Đích `/topic/updates` phải phù hợp với cấu hình broker và quy tắc phân quyền. Tham số destination của template xác định nơi gửi; Spring quản lý SIMP metadata tương ứng.

Nếu cần metadata chỉ dùng nội bộ trong pipeline Spring, có thể dùng `setHeader("appCorrelationId", value)`. Nếu cần header được biểu diễn ở lớp STOMP, dùng `setNativeHeader("x-correlation-id", value)`. Chọn đúng API quyết định header thuộc vùng metadata nào.

## 5. Đọc native headers trong handler

Trong handler nhận message STOMP, có thể bọc message bằng accessor để đọc native header:

```java
import java.security.Principal;
import org.springframework.messaging.Message;
import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.simp.SimpMessageHeaderAccessor;
import org.springframework.stereotype.Controller;

@Controller
public class UpdateController {

    @MessageMapping("/updates")
    public void receive(Message<?> message, Principal principal) {
        SimpMessageHeaderAccessor accessor =
                SimpMessageHeaderAccessor.wrap(message);

        String traceId = accessor.getFirstNativeHeader("x-trace-id");
        String destination = accessor.getDestination();

        System.out.println("user=" +
                (principal != null ? principal.getName() : "anonymous"));
        System.out.println("destination=" + destination);
        System.out.println("traceId=" + traceId);
    }
}
```

Trong code thực tế, hãy xử lý payload theo kiểu dữ liệu của ứng dụng và kiểm tra dữ liệu đầu vào. Nếu header có nhiều giá trị, dùng `getNativeHeader(name)` thay vì chỉ lấy giá trị đầu tiên. Có thể nhận trực tiếp `MessageHeaders` trong handler nếu chữ ký handler phù hợp.

## 6. Chọn đúng loại header

| Nhu cầu | Cách biểu diễn |
|---|---|
| Đặt đích Spring như `/topic/orders` | SIMP destination (`setDestination` hoặc tham số destination của template). |
| Đính kèm trace id cần xuất hiện trong STOMP frame | Native header, ví dụ `setNativeHeader("x-trace-id", id)`. |
| Lưu metadata chỉ dùng nội bộ trong pipeline Spring | Header tùy chỉnh qua `setHeader`. |
| Truyền metadata theo quy ước STOMP/client đã thống nhất | Native header với tên và định dạng đã thỏa thuận. |
| Xác định user/session/subscription | Dùng cơ chế xác thực và metadata Spring quản lý; không giả mạo bằng header tùy chỉnh. |

Đừng nhầm header `destination` trong frame STOMP với một native header tùy ý trên message server-side. Khi client gửi frame STOMP, `destination` là header giao thức đầu vào và Spring ánh xạ nó vào mô hình SIMP. Khi server gửi qua `SimpMessagingTemplate`, hãy cung cấp destination cho template hoặc accessor để Spring định tuyến.

## 7. Lưu ý khi gửi

1. **Không tin native header từ client.** Client có thể tự gửi header tùy chỉnh. Không dùng `x-role`, `tenant-id` hoặc giá trị tương tự làm bằng chứng xác thực hay phân quyền. Lấy danh tính từ `Principal` và kiểm tra quyền ở server.
2. **Tránh ghi đè header framework quản lý.** Destination, session, subscription và message id có ý nghĩa nội bộ. Tự đặt sai giá trị có thể làm sai định tuyến hoặc tạo metadata không nhất quán.
3. **Header có thể có nhiều giá trị.** STOMP cho phép lặp header. Dùng API dạng danh sách khi cần bảo toàn tất cả giá trị; `getFirstNativeHeader` chỉ lấy giá trị đầu tiên.
4. **Phân biệt header với payload.** Header phù hợp cho metadata ngắn như loại sự kiện, trace id hoặc content type. Dữ liệu nghiệp vụ chính nên nằm trong body để có schema rõ ràng.
5. **Không giả định mọi transport đều giữ native headers.** Qua broker relay, broker ngoài hoặc transport khác, việc bảo toàn và chuyển tiếp phụ thuộc cấu hình và giao thức.
6. **Đặt tên header có quy ước.** Dùng prefix riêng như `x-` hoặc namespace ứng dụng để tránh xung đột với header chuẩn STOMP và header Spring.
7. **Kiểm soát dữ liệu nhạy cảm.** Header có thể xuất hiện trong log, tracing hoặc công cụ giám sát. Không gửi token, mật khẩu hay bí mật trong header nếu chưa có thiết kế bảo vệ phù hợp.

## 8. Lỗi thường gặp

- **Dùng `setHeader` nhưng mong header xuất hiện trong STOMP frame:** `setHeader` đặt metadata Spring. Dùng `setNativeHeader` cho header giao thức.
- **Dùng `setNativeHeader` để định tuyến:** native header tùy chỉnh không thay thế SIMP destination. Đặt destination qua `setDestination` hoặc tham số của `convertAndSend`.
- **Đọc sai vùng header:** `MessageHeaders.get("x-trace-id")` tìm khóa cấp cao nhất; native header nằm trong map `nativeHeaders`. Dùng `getFirstNativeHeader` hoặc `getNativeHeader` qua accessor.
- **Giả định broker hiểu header tùy chỉnh:** broker chỉ xử lý header theo giao thức hoặc cấu hình nó hỗ trợ. Header ứng dụng thường là metadata để hai đầu ứng dụng tự thống nhất.
- **Tạo danh tính từ header client:** header không đáng tin cậy cho xác thực. Dùng Spring Security và `Principal`.

## 9. Cách debug

Khi message đến sai đích hoặc client không thấy header, kiểm tra lần lượt:

1. Xác nhận destination truyền vào `SimpMessagingTemplate` có đúng prefix và được broker cấu hình xử lý.
2. Kiểm tra SIMP metadata bằng `SimpMessageHeaderAccessor.wrap(message).getDestination()` và loại message tương ứng.
3. Kiểm tra native headers bằng `toNativeHeaderMap()` hoặc `getNativeHeader("x-trace-id")`; đừng chỉ xem các khóa cấp cao nhất của `MessageHeaders`.
4. Quan sát STOMP frame thực tế ở client hoặc log giao thức để xác định header đã được serialize hay chưa.
5. Nếu dùng broker relay, kiểm tra hành vi broker và cấu hình relay; không suy ra việc chuyển tiếp chỉ từ nội dung `MessageHeaders` trong ứng dụng.

## 10. Ghi nhớ

SIMP headers là metadata của mô hình Spring Messaging, đặc biệt hữu ích cho destination và ngữ cảnh xử lý. STOMP native headers là metadata giao thức được lưu riêng và có thể đi cùng frame STOMP. Khi gửi, dùng destination argument hoặc `setDestination` để định tuyến; dùng `setNativeHeader` cho metadata ở lớp STOMP; dùng `setHeader` cho metadata nội bộ Spring. Chọn đúng lớp header giúp message được định tuyến đúng, client nhận metadata mong muốn và ứng dụng tránh phụ thuộc sai vào chi tiết giao thức.