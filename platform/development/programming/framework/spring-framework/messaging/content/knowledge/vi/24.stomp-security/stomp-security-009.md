# Không ghi token, thông tin đăng nhập hoặc payload nhạy cảm vào log

> Phạm vi: Spring Framework STOMP over WebSocket, Java 17+. Bài này tập trung vào log an toàn trong luồng STOMP: frame CONNECT, SEND, SUBSCRIBE, header xác thực, payload ứng dụng, interceptor, log sự kiện bảo mật và cách kiểm thử để chắc chắn bí mật không lọt vào log.

## 1. Vì sao log STOMP có thể làm lộ dữ liệu?

Một STOMP frame thường có command, headers và body. Ví dụ, CONNECT có thể mang thông tin xác thực; SEND có thể mang nội dung chat, dữ liệu đơn hàng hoặc thông tin cá nhân. Khi bật log quá chi tiết hoặc ghi nguyên đối tượng message, ứng dụng có thể sao chép những dữ liệu này sang file log, hệ thống tập trung, nền tảng APM hoặc dịch vụ lưu trữ log.

Log thường được nhiều người và nhiều hệ thống truy cập hơn dữ liệu nghiệp vụ gốc. Log có thể được chuyển tiếp sang môi trường khác, giữ lâu hơn thời gian sống của session hoặc xuất hiện trong bản sao lưu. Vì vậy, một token bị ghi vào log có thể tiếp tục bị lộ ngay cả sau khi token đã hết hạn hoặc session đã đóng.

Nguyên tắc cần áp dụng: **ghi lại sự kiện và metadata tối thiểu để vận hành, điều tra và giám sát; không ghi bí mật xác thực hoặc nội dung nhạy cảm của message.**

## 2. Những dữ liệu không được ghi trực tiếp

| Nhóm dữ liệu | Ví dụ | Cách xử lý |
|---|---|---|
| Access token và refresh token | JWT, bearer token, opaque token | Không ghi giá trị; chỉ ghi loại xác thực hoặc kết quả xác thực. |
| Thông tin đăng nhập | Password, STOMP login/passcode, API key, client secret | Không ghi; không đưa vào exception hoặc diagnostic message. |
| Header xác thực | Authorization, Cookie, Set-Cookie, custom auth header | Không ghi nguyên header hoặc toàn bộ native header map. |
| Session và CSRF | Session cookie, session ID, CSRF token | Không ghi giá trị thô; nếu cần liên kết sự kiện, dùng mã tương quan hoặc định danh đã được bảo vệ. |
| Payload nhạy cảm | Tin nhắn riêng tư, hồ sơ khách hàng, dữ liệu thanh toán, dữ liệu sức khỏe | Không ghi body; chỉ ghi loại sự kiện và kết quả xử lý. |
| Dữ liệu định danh | Email, số điện thoại, địa chỉ, username hoặc user ID nếu không cần thiết | Loại bỏ hoặc thay bằng mã giả danh theo chính sách. |
| Header và thuộc tính nội bộ | Native headers, simpSessionAttributes, thông tin Principal | Chỉ lấy trường đã được cho phép; không dump toàn bộ object. |
| URL có bí mật | Query parameter chứa token hoặc mã truy cập | Tránh truyền token qua URL; cấu hình access log không ghi query string nhạy cảm. |

Không ghi toàn bộ STOMP frame, body, `Message<?>`, `Message.toString()`, `StompHeaderAccessor.toString()` hoặc map header để debug. Những cách này có thể làm lộ dữ liệu dù đoạn code log không nhắc trực tiếp đến tên token hay password.

Destination cũng cần được xem xét. Một destination như `/user/alice/queue/notifications`, `/tenant/acme/orders/123` hoặc đường dẫn chứa email có thể tiết lộ danh tính hay thông tin nghiệp vụ. Không phải destination nào cũng an toàn để ghi nguyên văn.

## 3. Lưu ý về xác thực STOMP trong Spring

Với ứng dụng STOMP over WebSocket thông thường, Spring gắn Principal đã xác thực từ HTTP handshake vào WebSocket session và các message tiếp theo. Mặc định, Spring bỏ qua các header `login` và `passcode` của STOMP CONNECT khi chạy trên WebSocket; cơ chế xác thực thường dựa vào HTTP request và security context đã có.

Một ứng dụng có thể chọn token authentication ở tầng STOMP. Khi đó client gửi token trong header của CONNECT và ứng dụng dùng `ChannelInterceptor` để xác thực rồi gắn user vào message. Header CONNECT trở thành dữ liệu đặc biệt nhạy cảm. Interceptor có quyền đọc header để xác thực nhưng tuyệt đối không được log header đó.

Không nên đặt access token trong query string của WebSocket URL. URL có thể xuất hiện trong access log, reverse proxy, monitoring hoặc lịch sử công cụ chẩn đoán. Hãy chọn cơ chế xác thực phù hợp với loại client và hướng dẫn của Spring Security; nếu dùng STOMP CONNECT header, chỉ đọc nó trong bước xác thực và không sao chép sang log.

Ví dụ về hai việc khác nhau:

- Được phép: đọc Authorization header trong interceptor để kiểm tra chữ ký, hạn dùng và quyền.
- Không được phép: ghi `accessor.getNativeHeaderMap()`, `accessor.getFirstNativeHeader("Authorization")` hoặc token vào log để “debug đăng nhập”.

## 4. Nên ghi gì để vẫn quan sát được hệ thống?

Một log hữu ích không cần chứa body hoặc token. Hãy ưu tiên các trường đã được allowlist:

| Trường log | Ví dụ an toàn | Mục đích |
|---|---|---|
| Timestamp | Thời điểm theo UTC | Sắp xếp và đối chiếu sự kiện. |
| Event type | `stomp.frame.received`, `stomp.auth.denied` | Phân loại sự kiện. |
| STOMP command | `CONNECT`, `SEND`, `SUBSCRIBE`, `DISCONNECT` | Biết loại thao tác. |
| Route đã chuẩn hóa | `chat.send`, `orders.submit`, `other` | Biết luồng ứng dụng mà không lộ ID động. |
| Outcome | `accepted`, `rejected`, `failed` | Theo dõi kết quả. |
| Reason code | `invalid_token`, `destination_denied` | Điều tra lỗi bằng mã ổn định. |
| Correlation ID | Mã ngẫu nhiên do server tạo | Nối các log của một request hoặc luồng xử lý. |
| User pseudonym | HMAC hoặc mã nội bộ đã được phê duyệt | Tương quan theo user mà không ghi định danh gốc. |
| Application instance | Tên instance hoặc pod đã chuẩn hóa | Xác định node xử lý message. |
| Latency / size bucket | Thời gian xử lý hoặc nhóm kích thước | Quan sát hiệu năng mà không ghi payload. |

Chỉ ghi user pseudonym hoặc session fingerprint khi thật sự cần và đã được phê duyệt. Nếu phải tương quan theo session, dùng HMAC với khóa bí mật được quản lý riêng thay cho session ID thô hoặc hash không khóa. Không đưa user ID, session ID hoặc destination động vào nhãn metrics có cardinality cao.

## 5. Dùng ChannelInterceptor để log metadata đã chọn

Spring cho phép đăng ký `ChannelInterceptor` trên client inbound channel. Interceptor có thể đọc STOMP command và destination bằng `StompHeaderAccessor`. Ví dụ dưới đây chỉ log command và tên route nằm trong allowlist; nó không đọc body, token, native headers, Principal hoặc session ID.

~~~java
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.simp.stomp.StompHeaderAccessor;
import org.springframework.stereotype.Component;

@Component
public class SafeStompLoggingInterceptor implements ChannelInterceptor {

    private static final Logger log =
            LoggerFactory.getLogger(SafeStompLoggingInterceptor.class);

    @Override
    public Message<?> preSend(Message<?> message, MessageChannel channel) {
        StompHeaderAccessor accessor = StompHeaderAccessor.wrap(message);

        if (accessor.getCommand() != null) {
            String route = safeRoute(accessor.getDestination());

            // Chỉ ghi command và route tĩnh đã được allowlist.
            // Không ghi message, payload, headers, Principal hay session ID.
            log.debug("stomp.in command={} route={}",
                    accessor.getCommand(), route);
        }

        return message;
    }

    private static String safeRoute(String destination) {
        if (destination == null) {
            return "none";
        }

        return switch (destination) {
            case "/app/chat.send" -> "chat.send";
            case "/app/orders.submit" -> "orders.submit";
            case "/topic/announcements" -> "announcements";
            default -> "other";
        };
    }
}
~~~

Hàm `safeRoute` trả về nhãn cố định thay vì ghi destination tùy ý từ client. Nếu ứng dụng có destination động như `/app/rooms/{roomId}/messages`, hãy ánh xạ nó sang route template `/app/rooms/{roomId}/messages`; không log giá trị roomId thực tế trừ khi chính sách cho phép.

Đăng ký interceptor trong cấu hình WebSocket hiện có:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig implements WebSocketMessageBrokerConfigurer {

    private final SafeStompLoggingInterceptor safeLoggingInterceptor;

    public WebSocketConfig(SafeStompLoggingInterceptor safeLoggingInterceptor) {
        this.safeLoggingInterceptor = safeLoggingInterceptor;
    }

    @Override
    public void configureClientInboundChannel(ChannelRegistration registration) {
        registration.interceptors(safeLoggingInterceptor);
    }

    // Giữ các cấu hình endpoint, broker và application prefix hiện có.
}
~~~

Đây là phần bổ sung vào cấu hình hiện tại của ứng dụng; không tạo thêm một cấu hình `@EnableWebSocketMessageBroker` thứ hai nếu dự án đã có cấu hình đó. Interceptor mẫu chỉ quan sát inbound frame. Nếu cần quan sát outbound, hãy đăng ký riêng trên client outbound channel và áp dụng cùng nguyên tắc allowlist.

Log ví dụ:

~~~text
stomp.in command=CONNECT route=none
stomp.in command=SEND route=chat.send
stomp.in command=SUBSCRIBE route=other
~~~

Không có body, token, password, username hay session ID trong các dòng này.

## 6. Ghi nhận sự kiện bảo mật mà không lộ bí mật

Không ghi bí mật không có nghĩa là bỏ qua sự kiện bảo mật. Có thể ghi nhận:

- Kết quả xác thực CONNECT: thành công hoặc thất bại.
- Lý do thất bại bằng mã ổn định như `invalid_token`, `expired_credential` hoặc `missing_identity`.
- Lệnh SEND hoặc SUBSCRIBE bị từ chối bởi authorization.
- Client gửi đến destination không được phép.
- Frame sai định dạng, vi phạm giới hạn kích thước hoặc lỗi kiểm tra dữ liệu.
- Kết nối bị ngắt bất thường, heartbeat timeout hoặc broker connection thất bại.
- Tần suất gửi bất thường, hành vi dò destination hoặc vượt rate limit.

Ví dụ log sự kiện từ logic xác thực:

~~~java
log.warn(
    "stomp.auth outcome={} reason={} route={} correlationId={}",
    "rejected",
    "invalid_token",
    "connect",
    correlationId
);
~~~

`correlationId` trong ví dụ phải là mã tương quan do server hoặc hệ thống tracing đáng tin cậy tạo ra. Không lấy nguyên giá trị tùy ý từ client rồi ghi vào log nếu chưa giới hạn định dạng và độ dài. Không ghi token sai, header CONNECT, nội dung exception có thể chứa token hoặc nguyên frame để giải thích lý do từ chối.

Với lỗi, ưu tiên ghi exception class, mã lỗi nội bộ và correlation ID. Chỉ ghi stack trace khi đã kiểm tra rằng exception message và các field liên quan không chứa bí mật hoặc payload. Có thể gửi chi tiết kỹ thuật vào hệ thống chẩn đoán có kiểm soát riêng, nhưng vẫn phải áp dụng cùng chính sách bảo vệ dữ liệu.

## 7. Redaction, allowlist và chống log injection

### Ưu tiên allowlist

Cách an toàn hơn là chọn trước những trường được phép ghi. Đừng log toàn bộ headers rồi cố gắng xóa một danh sách vài tên nhạy cảm. Danh sách bí mật có thể mở rộng, có thể có custom header, và có thể xuất hiện ở nhiều định dạng khác nhau.

Nếu bắt buộc ghi một trường do client cung cấp, hãy:

1. Xác định rõ mục đích vận hành cần trường đó.
2. Kiểm tra kiểu, độ dài và định dạng.
3. Loại bỏ hoặc mã hóa ký tự điều khiển như CR và LF.
4. Giới hạn độ dài trước khi ghi.
5. Không cho phép giá trị ghi đè tên trường hoặc tạo thêm dòng log.
6. Kiểm thử với chuỗi chứa newline, delimiter và dữ liệu giả lập bí mật.

Dùng structured logging và tham số hóa logger để dữ liệu được ghi thành field riêng. Không ghép chuỗi log bằng dữ liệu thô do client gửi. Tuy nhiên, structured logging không thay thế việc lọc và redaction: nếu field chứa token thì JSON log vẫn làm lộ token.

### Redaction ở nguồn

Thực hiện loại bỏ dữ liệu ngay tại điểm tạo log. Không dựa hoàn toàn vào pipeline downstream để che token sau khi nó đã được ghi vào file cục bộ hoặc chuyển qua agent thu thập log. Masking ở hệ thống tập trung chỉ là lớp phòng vệ bổ sung.

Không nên ghi `payload.length()` hoặc hash của payload như một giải pháp mặc định. Kích thước và hash đôi khi vẫn cho phép suy luận dữ liệu; chỉ ghi khi có mục đích rõ ràng và đã đánh giá rủi ro.

## 8. Cấu hình log level và kiểm soát khối lượng

Trong môi trường production:

- Không bật TRACE hoặc DEBUG diện rộng cho các package WebSocket, Messaging, Security hay toàn bộ ứng dụng nếu chưa xác nhận nội dung thực tế mà logger phát ra.
- Dùng logger ứng dụng riêng để ghi event đã được làm sạch.
- Bật debug tạm thời trong môi trường kiểm thử, giới hạn thời gian, người truy cập và dữ liệu thử nghiệm.
- Không bật raw frame logging trong production.
- Dùng sampling cho các sự kiện thành công có tần suất cao; giữ lại các sự kiện bảo mật quan trọng nhưng vẫn phải loại bỏ bí mật.
- Rate-limit các log lặp lại do client gửi frame sai liên tục để tránh log flooding.
- Dùng metrics tổng hợp cho throughput, lỗi, latency và số kết nối; không dùng token, username, session ID hoặc payload làm metric label.

Cần kiểm tra cả log do reverse proxy, load balancer, API gateway, container runtime và APM agent tạo ra. Dù ứng dụng không ghi token, một URL có token trong query string vẫn có thể bị ghi ở tầng HTTP.

## 9. Bảo vệ log sau khi tạo

Log vẫn có thể chứa metadata vận hành và dữ liệu cá nhân đã được giảm thiểu. Hãy bảo vệ chúng như một tài sản cần kiểm soát:

- Giới hạn quyền đọc theo vai trò và nhu cầu công việc.
- Ghi audit khi người dùng truy cập hoặc xuất log nhạy cảm.
- Mã hóa khi truyền và khi lưu trữ.
- Thiết lập retention phù hợp với mục đích và yêu cầu pháp lý; tự động xóa khi hết hạn.
- Tách quyền quản trị log khỏi quyền quản trị ứng dụng khi có thể.
- Bảo vệ tính toàn vẹn và sao lưu theo chính sách vận hành.
- Không sao chép log production có dữ liệu cá nhân sang máy phát triển hoặc ticket công khai.

Nếu phát hiện token hoặc password đã bị ghi vào log, coi đó là một sự cố lộ bí mật: hạn chế quyền truy cập log, xác định phạm vi bản sao và hệ thống downstream, thu hồi hoặc rotate credential liên quan, rồi xử lý bản log theo quy trình sự cố. Xóa một file log cục bộ không đảm bảo các bản sao trong hệ thống tập trung, backup hoặc APM đã biến mất.

## 10. Kiểm thử để chứng minh log không chứa bí mật

Một kiểm thử có ích là gửi dữ liệu canary giả lập qua các đường đi STOMP và xác nhận chúng không xuất hiện trong log:

- CONNECT có header giả lập `Authorization: Bearer CANARY_TOKEN`.
- CONNECT có custom header chứa `CANARY_SECRET`.
- SEND có JSON body chứa `CANARY_PRIVATE_MESSAGE`.
- Payload có email hoặc số điện thoại giả lập.
- Destination có ID động hoặc ký tự CR/LF.

Sau khi chạy, tìm từng chuỗi canary trong tất cả log ứng dụng, access log, proxy log và log collector của môi trường kiểm thử. Kết quả mong đợi: log chỉ chứa command, route allowlist, outcome và correlation ID; không có giá trị canary.

Có thể kiểm tra thêm rằng:

- Log không gọi `message.toString()` hoặc dump headers/body.
- Đường dẫn destination lạ được ánh xạ thành `other`.
- Lỗi xác thực chỉ ghi reason code, không ghi token đầu vào.
- Log injection không tạo thêm dòng hoặc field giả.
- Debug log tạm thời không vô tình bật ở production.

## 11. Ví dụ so sánh log không an toàn và log an toàn

| Không an toàn | An toàn hơn |
|---|---|
| Ghi nguyên `Message<?>` hoặc STOMP frame | Ghi command và route đã chuẩn hóa. |
| Ghi toàn bộ native header map | Ghi tên loại xác thực hoặc kết quả xác thực. |
| Ghi `Authorization` hoặc CONNECT login/passcode | Ghi `auth.outcome=rejected` và `reason=invalid_token`. |
| Ghi JSON body của SEND | Ghi event type và kết quả xử lý. |
| Ghi session ID hoặc cookie | Dùng correlation ID do server tạo; HMAC session identifier nếu thật sự cần. |
| Ghi destination động có email/user ID | Ghi route template hoặc nhãn allowlist. |
| Ghi exception message nguyên văn | Ghi exception class, error code và correlation ID sau khi đánh giá nội dung. |

## 12. Checklist trước khi bật logging cho STOMP

1. Có bất kỳ logger nào ghi raw frame, body, `Message<?>` hoặc native headers không?
2. CONNECT có thể chứa token, login, passcode hoặc CSRF token không?
3. Destination có thể chứa username, tenant ID, email hoặc dữ liệu nghiệp vụ không?
4. Access log có ghi query string của WebSocket URL không?
5. Interceptor có chỉ ghi các field nằm trong allowlist không?
6. Exception message và stack trace có thể chứa payload hoặc credential không?
7. Log có được giới hạn quyền đọc, mã hóa, đặt retention và audit không?
8. Có kiểm thử canary để chứng minh token, credential và payload không xuất hiện trong log không?

Nếu bất kỳ câu trả lời nào cho thấy dữ liệu bí mật có thể đi vào log, hãy sửa tại nguồn tạo log trước khi triển khai production.

## Tài liệu tham khảo

- [Spring Framework — Interception](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/interceptors.html): đăng ký `ChannelInterceptor`, đọc STOMP command và header accessor.
- [Spring Framework — Authentication](https://docs.spring.io/spring/reference/7.1/web/websocket/stomp/authentication.html): xác thực HTTP handshake và Principal gắn với STOMP session.
- [Spring Framework — Token Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html): xử lý token ở CONNECT bằng interceptor và rủi ro token trong query string.
- [Spring Security — WebSocket Security](https://www.springframework.org/spring-security/reference/servlet/integrations/websocket.html): xác thực, phân quyền message và bảo vệ CONNECT.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu cần loại bỏ, che, hash hoặc mã hóa trong log.
