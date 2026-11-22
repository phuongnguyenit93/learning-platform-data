# Kiểm tra payload, giới hạn kích thước và tốc độ gửi

STOMP mở một đường giao tiếp hai chiều qua WebSocket. Điều đó cũng có nghĩa server phải tiếp nhận dữ liệu do client kiểm soát: frame có thể quá lớn, JSON có cấu trúc bất thường, trường có giá trị ngoài miền hợp lệ hoặc client gửi command với tốc độ cao hơn khả năng xử lý của ứng dụng.

Bảo vệ messaging cần nhiều lớp:

1. Giới hạn kích thước frame ngay tại tầng WebSocket/STOMP để chặn payload quá lớn trước khi deserialize.
2. Kiểm tra cấu trúc và giá trị của DTO sau khi message converter tạo đối tượng Java.
3. Kiểm tra quyền truy cập destination và dữ liệu theo Principal đã xác thực.
4. Giới hạn tốc độ gửi theo user hoặc session, đồng thời kiểm soát số lượng subscription và tài nguyên xử lý.
5. Kiểm thử các giới hạn, lỗi validation, reconnect và hành vi khi client cố tình gửi quá nhanh.

Không có một annotation hay một giới hạn đơn lẻ nào thay thế được các lớp kiểm soát này. Kích thước nhỏ vẫn có thể chứa dữ liệu không hợp lệ; payload hợp lệ vẫn có thể được gửi với tốc độ gây quá tải.

## 1. Phân biệt các lớp kiểm tra

| Lớp | Câu hỏi cần trả lời | Cơ chế phù hợp |
|---|---|---|
| WebSocket/STOMP transport | Frame đầu vào có vượt kích thước cho phép không? | Giới hạn message size khi cấu hình WebSocket transport |
| Message conversion | Payload có thể chuyển thành kiểu dữ liệu mong đợi không? | MessageConverter và content type |
| DTO validation | Trường có thiếu, quá dài hoặc nằm ngoài miền hợp lệ không? | Jakarta Bean Validation với @Valid |
| Business validation | Người gửi có quyền thao tác trên đối tượng này không? | Principal, authorization và kiểm tra dữ liệu nghiệp vụ |
| Rate limiting | Client có gửi quá nhiều command trong một khoảng thời gian không? | Token bucket hoặc thuật toán giới hạn tốc độ |
| Resource control | Client có mở quá nhiều subscription hoặc tạo quá nhiều công việc không? | Giới hạn connection, subscription, queue và concurrency |

Các lớp có thứ tự thực hiện khác nhau. Giới hạn transport cần hoạt động trước khi ứng dụng parse một payload lớn. DTO validation chỉ chạy sau khi payload đã được chuyển đổi thành object. Business validation cần kiểm tra quyền và trạng thái dữ liệu tại thời điểm xử lý.

## 2. Giới hạn kích thước STOMP message tại transport

Spring cho phép cấu hình giới hạn kích thước message đầu vào trong WebSocket transport bằng configureWebSocketTransport:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.web.socket.config.annotation.EnableWebSocketMessageBroker;
import org.springframework.web.socket.config.annotation.StompEndpointRegistry;
import org.springframework.web.socket.config.annotation.WebSocketMessageBrokerConfigurer;
import org.springframework.web.socket.config.annotation.WebSocketTransportRegistration;

@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
    }

    @Override
    public void configureWebSocketTransport(
            WebSocketTransportRegistration registration) {

        registration.setMessageSizeLimit(64 * 1024);
        registration.setSendBufferSizeLimit(512 * 1024);
        registration.setSendTimeLimit(15_000);
    }
}
~~~

Ý nghĩa của các giới hạn:

- **setMessageSizeLimit:** giới hạn kích thước một STOMP message đầu vào mà Spring nhận qua WebSocket transport. Giá trị thường được tính bằng byte; cấu hình cần phù hợp với kích thước tối đa mà ứng dụng thực sự cần.
- **setSendBufferSizeLimit:** giới hạn lượng dữ liệu outbound được buffer khi gửi đến một client chậm.
- **setSendTimeLimit:** giới hạn thời gian gửi outbound trước khi Spring xem kết nối là quá chậm.

Hai thiết lập send buffer và send time bảo vệ đường gửi ra client; chúng không thay thế giới hạn kích thước message đầu vào.

Không nên đặt giới hạn quá lớn chỉ để tránh lỗi payload. Một frame hàng megabyte có thể làm tăng chi phí cấp phát bộ nhớ, parse JSON, copy dữ liệu và giữ message trong queue. Hãy chọn giới hạn dựa trên payload lớn nhất hợp lệ, cộng một khoảng dự phòng hợp lý.

Khi client gửi một frame vượt giới hạn, transport có thể từ chối hoặc đóng kết nối tùy đường xử lý. Không nên giả định controller sẽ nhận được payload để trả lỗi nghiệp vụ; giới hạn này được áp dụng trước khi message đến controller.

## 3. Giới hạn payload ở tầng ứng dụng

Giới hạn transport kiểm soát kích thước frame tổng thể. Ứng dụng vẫn có thể áp dụng giới hạn riêng cho từng command hoặc từng loại dữ liệu.

Ví dụ một command tạo đơn hàng chỉ cần mã đơn và số lượng nhỏ. Không có lý do để cho phép một chuỗi mô tả dài hàng trăm kilobyte.

~~~java
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record CreateOrder(
    @NotBlank
    @Size(max = 40)
    @Pattern(regexp = "[A-Za-z0-9_-]+")
    String orderId,

    @Min(1)
    @Max(100)
    int quantity,

    @Size(max = 200)
    String note
) {}
~~~

Các ràng buộc có ý nghĩa:

- @NotBlank yêu cầu orderId có nội dung sau khi bỏ khoảng trắng.
- @Size(max = 40) giới hạn độ dài chuỗi.
- @Pattern giới hạn ký tự được phép theo quy tắc mã đơn.
- @Min và @Max giới hạn số lượng.
- note có thể null nếu nghiệp vụ cho phép, nhưng nếu có giá trị thì không được vượt quá 200 ký tự.

Giới hạn độ dài chuỗi trong Bean Validation được tính theo số ký tự Java (UTF-16 code units) của String, không phải số byte UTF-8. Nếu giới hạn lưu trữ hoặc giao thức tính theo byte, cần kiểm tra thêm kích thước byte sau khi xác định encoding.

Với collection hoặc object lồng nhau, phải đặt giới hạn ở từng cấp:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;
import java.util.List;

public record BatchCommand(
    @NotEmpty
    @Size(max = 50)
    List<@Valid CreateOrder> orders
) {}
~~~

@Size(max = 50) giới hạn số phần tử trong danh sách. @Valid yêu cầu tiếp tục kiểm tra từng CreateOrder. Nếu DTO có nhiều cấp lồng nhau, hãy giới hạn độ dài chuỗi, số phần tử và độ sâu cấu trúc theo yêu cầu nghiệp vụ.

## 4. Chạy Bean Validation trên @MessageMapping

Spring có thể kiểm tra payload của phương thức @MessageMapping khi tham số được đánh dấu @Valid hoặc @Validated và ứng dụng có Bean Validation provider.

~~~java
import jakarta.validation.Valid;
import java.security.Principal;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Controller;

@Controller
public class OrderController {

    private final OrderService orderService;

    public OrderController(OrderService orderService) {
        this.orderService = orderService;
    }

    @MessageMapping("/orders")
    public void create(
            @Payload @Valid CreateOrder command,
            Principal principal) {

        orderService.create(principal.getName(), command);
    }
}
~~~

Khi client gửi đến /app/orders:

1. Spring nhận STOMP SEND và định tuyến đến handler.
2. Message converter chuyển payload thành CreateOrder.
3. Bean Validation kiểm tra các constraint.
4. Chỉ khi payload hợp lệ, phương thức controller mới xử lý command.
5. Service vẫn phải kiểm tra quyền và quy tắc nghiệp vụ trước khi ghi dữ liệu.

Validation DTO không chứng minh người gửi có quyền tạo đơn hàng cho một tài khoản cụ thể. Hãy lấy user identity từ Principal đã xác thực và kiểm tra quyền ở tầng service.

Có thể chuyển lỗi validation thành một thông điệp lỗi có cấu trúc:

~~~java
import org.springframework.messaging.handler.annotation.MessageExceptionHandler;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.MethodArgumentNotValidException;

@Controller
public class MessagingValidationAdvice {

    @MessageExceptionHandler(MethodArgumentNotValidException.class)
    @SendToUser(value = "/queue/errors", broadcast = false)
    public ErrorPayload invalidPayload(MethodArgumentNotValidException ex) {
        return new ErrorPayload(
            "INVALID_PAYLOAD",
            "Dữ liệu gửi lên không hợp lệ"
        );
    }

    public record ErrorPayload(String code, String message) {}
}
~~~

Thông báo trả về cho client nên chứa mã lỗi ổn định và nội dung có thể hiển thị. Không gửi stack trace, tên class nội bộ, SQL hoặc thông tin nhạy cảm. Có thể log chi tiết validation ở server với correlation ID để điều tra.

Nếu cần trả lỗi cho command từ anonymous session, hãy kiểm tra cách ứng dụng định tuyến lỗi đến đúng session. Không dùng một destination công khai khiến lỗi validation của người này bị phát cho mọi client.

## 5. Kiểm tra command và destination trước controller

Một ChannelInterceptor trên clientInboundChannel có thể kiểm tra message trước khi nó đến @MessageMapping. Đây là nơi phù hợp để áp dụng chính sách chung cho các command STOMP, ví dụ giới hạn destination và tốc độ gửi.

~~~java
import java.security.Principal;

import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.MessageDeliveryException;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageHeaderAccessor;
import org.springframework.messaging.simp.stomp.StompCommand;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.stereotype.Component;

@Component
public class StompInboundGuard implements ChannelInterceptor {

    private final TokenBucketRateLimiter rateLimiter;

    public StompInboundGuard(TokenBucketRateLimiter rateLimiter) {
        this.rateLimiter = rateLimiter;
    }

    @Override
    public Message<?> preSend(
            Message<?> message,
            MessageChannel channel) {

        StompHeaderAccessor accessor =
            MessageHeaderAccessor.getAccessor(
                message,
                StompHeaderAccessor.class
            );

        if (accessor == null || accessor.getCommand() == null) {
            return message;
        }

        if (accessor.getCommand() == StompCommand.SEND) {
            String destination = accessor.getDestination();

            if (destination == null || !destination.startsWith("/app/")) {
                throw new MessageDeliveryException(
                    message,
                    "STOMP SEND destination is not allowed"
                );
            }

            Principal principal = accessor.getUser();
            String sessionId = accessor.getSessionId();

            String rateLimitKey = principal != null
                ? "user:" + principal.getName()
                : "session:" + sessionId;

            if (!rateLimiter.tryAcquire(rateLimitKey)) {
                throw new MessageDeliveryException(
                    message,
                    "STOMP send rate limit exceeded"
                );
            }
        }

        return message;
    }
}
~~~

Đăng ký interceptor:

~~~java
@Override
public void configureClientInboundChannel(ChannelRegistration registration) {
    registration.interceptors(stompInboundGuard);
}
~~~

Ví dụ chỉ giới hạn command SEND đến application destination /app/. Những destination thực tế phải khớp cấu hình prefix và hợp đồng API của ứng dụng. Không cho client gửi SEND trực tiếp đến destination nội bộ chỉ dành cho broker hoặc các kênh quản trị.

Interceptor không thay thế authorization. Kiểm tra prefix chỉ là kiểm tra hình dạng destination; server vẫn cần xác định Principal có quyền thực hiện command đó và có quyền truy cập dữ liệu liên quan.

Với SUBSCRIBE, nên có chính sách riêng: destination được phép, số subscription tối đa mỗi session, và quyền đọc dữ liệu. Một client có thể không gửi nhiều SEND nhưng vẫn tiêu tốn tài nguyên bằng cách tạo rất nhiều subscription.

## 6. Token bucket để giới hạn tốc độ gửi

Token bucket là một thuật toán đơn giản cho phép một lượng burst nhỏ nhưng giới hạn tốc độ trung bình. Bucket có dung lượng tối đa; theo thời gian, token được nạp lại. Mỗi command hợp lệ tiêu thụ một token.

Ví dụ: bucket chứa tối đa 20 token và nạp lại 5 token mỗi giây. Client có thể gửi một burst tối đa 20 command khi bucket đầy, sau đó tốc độ dài hạn bị giới hạn khoảng 5 command mỗi giây.

~~~java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

public final class TokenBucketRateLimiter {

    private final ConcurrentMap<String, Bucket> buckets =
        new ConcurrentHashMap<>();

    private final int capacity;
    private final double refillPerSecond;

    public TokenBucketRateLimiter(
            int capacity,
            double refillPerSecond) {

        if (capacity < 1 || refillPerSecond <= 0) {
            throw new IllegalArgumentException("Invalid token bucket settings");
        }

        this.capacity = capacity;
        this.refillPerSecond = refillPerSecond;
    }

    public boolean tryAcquire(String key) {
        if (key == null || key.isBlank()) {
            return false;
        }

        Bucket bucket = buckets.computeIfAbsent(
            key,
            ignored -> new Bucket(capacity, System.nanoTime())
        );

        return bucket.tryAcquire(
            capacity,
            refillPerSecond,
            System.nanoTime()
        );
    }

    private static final class Bucket {

        private double tokens;
        private long lastRefillNanos;

        private Bucket(int capacity, long now) {
            this.tokens = capacity;
            this.lastRefillNanos = now;
        }

        private synchronized boolean tryAcquire(
                int capacity,
                double refillPerSecond,
                long now) {

            long elapsed = Math.max(0, now - lastRefillNanos);
            double elapsedSeconds = elapsed / 1_000_000_000.0;

            tokens = Math.min(
                capacity,
                tokens + elapsedSeconds * refillPerSecond
            );

            lastRefillNanos = now;

            if (tokens < 1.0) {
                return false;
            }

            tokens -= 1.0;
            return true;
        }
    }
}
~~~

Đây là ví dụ để minh họa thuật toán. Map trong bộ nhớ sẽ tăng khi có nhiều user/session mới; triển khai thực tế cần cache có TTL/eviction hoặc cơ chế dọn bucket hết hạn. Nếu ứng dụng chạy nhiều instance, mỗi node có map riêng nên client có thể nhận tổng quota lớn hơn dự kiến. Khi cần giới hạn toàn cụm, dùng rate limiter dùng chung như Redis hoặc giới hạn tại API gateway.

Chọn key theo mục tiêu:

- **Principal:** giới hạn tổng tốc độ của một người dùng qua nhiều session.
- **Session ID:** giới hạn từng kết nối, hữu ích cho guest session.
- **Principal + destination:** giới hạn riêng từng nhóm command.
- **IP tại gateway:** chặn burst kết nối hoặc request từ một nguồn mạng; chỉ tin forwarded IP do proxy tin cậy đặt.

Một người dùng có thể mở nhiều tab. Nếu chỉ giới hạn theo session, họ có thể nhân quota bằng cách mở thêm session. Ngược lại, giới hạn chỉ theo user có thể khiến các thiết bị của cùng tài khoản chia sẻ một quota. Hãy chọn chính sách phù hợp với sản phẩm.

## 7. Kiểm tra kích thước payload trong interceptor

Transport limit là lớp bảo vệ đầu tiên. Có thể bổ sung một kiểm tra payload byte ở inbound channel để áp dụng giới hạn riêng cho một nhóm command:

~~~java
import java.nio.charset.StandardCharsets;

import org.springframework.messaging.Message;

public final class PayloadSizePolicy {

    private PayloadSizePolicy() {
    }

    public static boolean exceedsLimit(Message<?> message, int maxBytes) {
        Object payload = message.getPayload();

        if (payload instanceof byte[] bytes) {
            return bytes.length > maxBytes;
        }

        if (payload instanceof String text) {
            return text.getBytes(StandardCharsets.UTF_8).length > maxBytes;
        }

        return false;
    }
}
~~~

Trong inbound STOMP pipeline, payload thường vẫn là byte[] trước khi được message converter chuyển thành DTO. Nếu interceptor được đặt ở giai đoạn khác hoặc một message nội bộ đã mang object Java, cần xác định cách tính kích thước tương ứng. Không dùng String.valueOf(object) để ước lượng kích thước JSON vì chuỗi đó không nhất thiết giống payload được serialize.

Kiểm tra này chỉ là lớp phụ trợ. Nó không thay thế setMessageSizeLimit vì lúc interceptor chạy, frame đã được nhận và decode. Với object đã deserialize, việc tính kích thước bằng serialize lại có thể tốn CPU và tạo thêm allocation.

Nếu dùng giới hạn riêng theo destination, hãy đặt ngưỡng nhỏ cho command nhạy cảm hoặc thường xuyên được gọi, ví dụ heartbeat, typing indicator hoặc command cập nhật trạng thái. Dữ liệu upload lớn nên đi qua HTTP/object storage với giới hạn và streaming phù hợp, sau đó STOMP chỉ phát thông báo tham chiếu đến tài nguyên.

## 8. Giới hạn queue, concurrency và outbound fan-out

Rate limit chỉ kiểm soát số message đến trong một khoảng thời gian. Một message hợp lệ vẫn có thể kích hoạt truy vấn nặng, tính toán lâu hoặc broadcast đến hàng nghìn subscriber.

Cần xem thêm:

- **Inbound executor:** giới hạn thread và queue của clientInboundChannel để message không tích tụ vô hạn khi handler chậm.
- **Outbound buffer:** cấu hình send buffer và send time limit để client đọc chậm không giữ quá nhiều dữ liệu trong bộ nhớ.
- **Số subscription:** giới hạn số subscription trên mỗi session và kiểm tra quyền subscribe.
- **Fan-out:** hạn chế broadcast payload lớn hoặc gửi quá thường xuyên đến destination có nhiều subscriber.
- **Concurrency nghiệp vụ:** giới hạn số công việc đồng thời theo user hoặc loại command.
- **Timeout:** đặt timeout cho việc gọi database và dịch vụ bên ngoài từ handler.

Ví dụ cấu hình inbound executor:

~~~java
@Override
public void configureClientInboundChannel(ChannelRegistration registration) {
    registration
        .taskExecutor()
        .corePoolSize(4)
        .maxPoolSize(16)
        .queueCapacity(500);
}
~~~

Các con số trên chỉ là giá trị minh họa. Hãy điều chỉnh theo số core CPU, độ trễ handler, lượng kết nối đồng thời và giới hạn bộ nhớ. Queue hữu hạn giúp backpressure bộc lộ sớm; khi đầy, hệ thống cần xử lý lỗi gửi hoặc từ chối message theo chính sách đã chọn.

Không nên tăng queue vô hạn để che giấu handler chậm. Queue lớn có thể biến quá tải ngắn hạn thành độ trễ kéo dài và giữ nhiều payload trong heap.

## 9. Bảo vệ trước payload độc hại và dữ liệu bất thường

Payload JSON hợp lệ về cú pháp vẫn có thể nguy hiểm hoặc không phù hợp nghiệp vụ.

- **Chuỗi quá dài:** có thể gây tốn bộ nhớ, log quá lớn hoặc vượt giới hạn cột lưu trữ.
- **Collection quá lớn:** có thể kích hoạt vòng lặp, truy vấn hoặc fan-out lớn.
- **Object lồng sâu:** làm tăng chi phí parse và validation; cần giới hạn độ sâu/độ phức tạp ở parser hoặc schema phù hợp.
- **Số ngoài miền:** giá trị âm, quá lớn hoặc overflow có thể làm sai logic.
- **Enum không hợp lệ:** không dùng giá trị mặc định để che giấu dữ liệu sai nếu nghiệp vụ cần từ chối.
- **Header giả mạo:** custom header do client gửi không phải bằng chứng xác thực.
- **Polymorphic JSON không an toàn:** tránh bật default typing rộng cho dữ liệu không tin cậy; dùng DTO có kiểu rõ ràng và cấu hình Jackson an toàn.
- **Lỗi encoding:** kiểm tra content type và charset, không giả định mọi payload text đều là UTF-8 nếu giao thức cho phép khác.

Validation cần có cả giới hạn cú pháp và giới hạn nghiệp vụ. Ví dụ quantity phải dương và không vượt hạn mức đơn hàng; orderId phải thuộc phạm vi mà Principal được phép thao tác. Chỉ kiểm tra @NotBlank không đủ để bảo vệ tài nguyên.

## 10. Phản hồi lỗi cho client

Một lỗi có thể được phát hiện trước controller (transport/interceptor), trong message conversion, trong Bean Validation hoặc trong service nghiệp vụ. Không phải lỗi nào cũng có thể trả về cùng một response DTO.

Có thể chuẩn hóa lỗi nghiệp vụ ở tầng controller bằng @MessageExceptionHandler:

~~~java
import org.springframework.messaging.handler.annotation.MessageExceptionHandler;
import org.springframework.messaging.simp.annotation.SendToUser;
import org.springframework.stereotype.Controller;

@Controller
public class MessagingErrorHandler {

    @MessageExceptionHandler(IllegalArgumentException.class)
    @SendToUser(value = "/queue/errors", broadcast = false)
    public ErrorPayload handleInvalidCommand(IllegalArgumentException ex) {
        return new ErrorPayload(
            "INVALID_COMMAND",
            "Command không hợp lệ"
        );
    }

    public record ErrorPayload(String code, String message) {}
}
~~~

Đối với payload validation, có thể xử lý exception validation cụ thể và chuyển thành mã lỗi ổn định. Đối với rate limit, nên phân biệt mã RATE_LIMITED và có thể cung cấp thời điểm thử lại nếu ứng dụng tính được. Không gửi chi tiết nội bộ hoặc stack trace cho client.

Lỗi transport như frame vượt kích thước có thể khiến kết nối bị đóng trước khi controller chạy. Trong trường hợp đó, client cần xử lý sự kiện transport error/close và hiển thị trạng thái phù hợp; không nên chờ một message lỗi nghiệp vụ chắc chắn sẽ đến.

## 11. Đo lường và vận hành

Nên theo dõi các chỉ số riêng cho từng lớp:

- Số frame/message bị từ chối do vượt giới hạn kích thước.
- Số lỗi Bean Validation theo loại command và constraint.
- Số command bị từ chối bởi rate limiter.
- Số kết nối WebSocket/STOMP đang hoạt động và số lần reconnect.
- Số subscription trên mỗi session.
- Độ dài queue inbound/outbound và thời gian xử lý handler.
- Số lỗi message conversion, broker error và transport error.
- Tỷ lệ client nhận được message và ACK nghiệp vụ nếu ứng dụng có triển khai.

Gắn correlation ID hoặc event ID vào log để nối các bước. Không dùng giá trị do client cung cấp làm nhãn metric có cardinality vô hạn; ví dụ không tạo metric riêng cho từng session ID hoặc user ID. Dùng nhãn giới hạn như command type, destination group và error code.

Rate limiting phải tạo ra tín hiệu vận hành rõ ràng. Nếu chỉ âm thầm bỏ message, client có thể tưởng command đã được xử lý. Hãy thống nhất phản hồi hoặc trạng thái lỗi mà client có thể quan sát.

## 12. Kiểm thử các giới hạn

Các bài kiểm thử nên xác minh cả trường hợp hợp lệ và trường hợp bị từ chối:

1. Gửi payload JSON hợp lệ và xác minh handler nhận đúng DTO.
2. Gửi chuỗi vượt @Size và xác minh validation từ chối trước khi service ghi dữ liệu.
3. Gửi số lượng âm hoặc vượt @Max và xác minh mã lỗi.
4. Gửi frame vượt setMessageSizeLimit và xác minh transport từ chối/đóng kết nối theo hành vi cấu hình.
5. Gửi nhiều command trong burst để kiểm tra token bucket cho phép burst đúng dung lượng.
6. Tiếp tục gửi khi bucket cạn và xác minh command bị rate limit.
7. Tạo nhiều session cho cùng Principal để xác minh quota theo user hoặc session đúng chính sách.
8. Gửi đến destination ngoài /app và xác minh interceptor từ chối.
9. Mở nhiều subscription và xác minh giới hạn subscription hoạt động.
10. Dùng client đọc chậm để kiểm tra send buffer và send time limit.
11. Chạy hai instance để xác minh rate limit dùng chung nếu yêu cầu áp dụng toàn cụm.
12. Kiểm tra reconnect không gửi lại command đã xử lý nếu không có idempotency key.

Không dùng Thread.sleep cố định để xác minh timing. Dùng latch/future có timeout và kiểm tra trạng thái cụ thể. Với rate limiter, có thể test trực tiếp thuật toán bằng đồng hồ giả để kết quả ổn định, thay vì phụ thuộc thời gian thực.

## 13. Checklist bảo vệ STOMP endpoint

- Transport có giới hạn kích thước STOMP message đầu vào phù hợp không?
- Send buffer và send time limit có bảo vệ client outbound chậm không?
- DTO có giới hạn độ dài chuỗi, số phần tử và miền giá trị không?
- Message converter có kiểu payload rõ ràng và không bật cấu hình polymorphic nguy hiểm không?
- Controller/service có xác thực Principal và quyền trên đối tượng nghiệp vụ không?
- Interceptor có kiểm tra destination, command và rate limit không?
- Có giới hạn số subscription, queue và concurrency không?
- Rate limiter có eviction và có dùng kho chung nếu chạy nhiều node không?
- Lỗi validation, rate limit và transport có cách quan sát phù hợp không?
- Metric/log có correlation ID mà không làm lộ token hoặc tạo cardinality vô hạn không?

Bảo vệ STOMP cần kiểm soát từ frame đến nghiệp vụ. Giới hạn kích thước giảm rủi ro payload lớn; Bean Validation kiểm tra cấu trúc và giá trị; authorization bảo vệ dữ liệu; rate limiting và giới hạn tài nguyên giúp server duy trì khả năng phục vụ khi client gửi quá nhanh.