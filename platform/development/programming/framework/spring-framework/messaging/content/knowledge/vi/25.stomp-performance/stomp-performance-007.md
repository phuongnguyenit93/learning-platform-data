# Không ghi token, thông tin đăng nhập hoặc payload nhạy cảm vào log

> Phạm vi: Spring Framework STOMP over WebSocket, Java 17+. Bài này hướng dẫn thiết kế log an toàn cho các frame CONNECT, SEND, SUBSCRIBE và DISCONNECT; xử lý header xác thực; quan sát lỗi; dùng ChannelInterceptor; và kiểm thử để bảo đảm token, thông tin đăng nhập cùng payload nhạy cảm không bị ghi ra log.

## 1. Vì sao log STOMP có thể làm lộ dữ liệu?

Một STOMP frame gồm command, headers và có thể có body. CONNECT có thể liên quan đến thông tin xác thực. SEND có thể chứa tin nhắn riêng tư, dữ liệu khách hàng, thông tin đơn hàng hoặc nội dung do người dùng nhập. SUBSCRIBE có thể mang destination tiết lộ tên user, tenant, phòng chat hoặc tài nguyên nội bộ.

Nếu ứng dụng ghi nguyên frame, message, header map hoặc payload để debug, những dữ liệu đó có thể xuất hiện trong log của ứng dụng, container, reverse proxy, hệ thống APM và nền tảng thu thập log. Các bản sao có thể được lưu lâu hơn vòng đời của token hoặc session và được truy cập bởi nhiều nhóm người hơn dữ liệu nghiệp vụ gốc.

Một token hết hạn vẫn có thể gây rủi ro nếu token đó đã được ghi vào log trước đó. Password, API key, session cookie và refresh token có thể bị khai thác nếu người không có quyền đọc log truy cập được chúng.

Nguyên tắc thực hành là **ghi sự kiện và metadata tối thiểu để vận hành, giám sát và điều tra; không ghi bí mật xác thực hoặc nội dung nhạy cảm của message**.

## 2. Dữ liệu cần loại khỏi log

| Nhóm dữ liệu | Ví dụ | Cách xử lý |
|---|---|---|
| Token | Access token, refresh token, JWT, bearer token, opaque token | Không ghi giá trị; chỉ ghi loại xác thực và kết quả. |
| Thông tin đăng nhập | Password, STOMP login/passcode, API key, client secret | Không ghi; không đưa vào log message hoặc exception. |
| Header xác thực | Authorization, Cookie, Set-Cookie, custom auth header | Không ghi nguyên header hoặc toàn bộ native header map. |
| Session và CSRF | Session cookie, session ID, CSRF token | Không ghi giá trị thô; dùng mã tương quan do server tạo nếu cần. |
| Payload nhạy cảm | Tin nhắn riêng tư, hồ sơ khách hàng, dữ liệu thanh toán, dữ liệu sức khỏe | Không ghi body; chỉ ghi loại sự kiện và kết quả xử lý. |
| Dữ liệu định danh | Email, số điện thoại, địa chỉ, username, user ID | Loại bỏ hoặc dùng mã giả danh nếu có mục đích được phê duyệt. |
| Thông tin nội bộ | Principal, simpSessionAttributes, native headers, broker credentials | Chỉ lấy trường được cho phép; không dump toàn bộ object. |
| URL có bí mật | Query parameter chứa token hoặc mã truy cập | Tránh đưa token vào URL; cấu hình access log không ghi query string nhạy cảm. |

Không dùng các cách sau để debug:

- Ghi nguyên STOMP frame hoặc body của frame.
- Ghi toàn bộ đối tượng Message<?> hoặc gọi Message.toString().
- Ghi StompHeaderAccessor.toString() hoặc toàn bộ header map.
- Ghi accessor.getFirstNativeHeader("Authorization") hoặc giá trị CONNECT login/passcode.
- Ghi exception message mà chưa biết nó có chứa token, payload hoặc header đầu vào hay không.

Destination cũng cần được đánh giá. Các đường dẫn như /user/alice/queue/notifications, /tenant/acme/orders/123 hoặc đường dẫn chứa email có thể tiết lộ danh tính và dữ liệu nghiệp vụ. Nếu cần ghi route, hãy ghi route template hoặc nhãn allowlist thay cho destination động.

## 3. Hiểu đúng xác thực STOMP trong Spring

Một STOMP over WebSocket session bắt đầu bằng HTTP handshake. Trong cấu hình Spring phổ biến, người dùng được xác thực ở tầng HTTP, ví dụ qua Spring Security và cookie session. Spring gắn Principal đã xác thực vào WebSocket session và các STOMP message tiếp theo.

STOMP protocol có header login và passcode trong frame CONNECT. Tuy nhiên, với STOMP over WebSocket, Spring mặc định bỏ qua các header xác thực này và giả định danh tính đã được xác thực ở tầng HTTP. Không nên dựa vào việc client gửi login/passcode trong CONNECT để thay thế cơ chế xác thực của ứng dụng.

Một ứng dụng có thể triển khai token authentication ở tầng STOMP. Khi đó client gửi token trong header của CONNECT và server dùng ChannelInterceptor để xác thực, sau đó gắn Principal vào message bằng accessor.setUser(...). Header CONNECT lúc này chứa bí mật có giá trị cao. Interceptor có thể đọc header để xác thực nhưng không được ghi header hoặc token ra log.

Không nên đặt access token trong query string của WebSocket URL. URL có thể xuất hiện trong access log của server, reverse proxy, load balancer, APM hoặc công cụ giám sát. Tài liệu Spring cũng nêu rõ token trong query parameter có thể vô tình bị ghi cùng URL.

Nếu dùng token trong CONNECT header cùng Spring Security message authorization, cần bảo đảm interceptor xác thực chạy trước interceptor phân quyền của Spring Security để Principal có mặt khi authorization được thực hiện.

## 4. Log gì để vẫn quan sát được hệ thống?

Log hữu ích không cần chứa body hoặc token. Hãy ưu tiên các trường được chọn trước:

| Trường log | Ví dụ | Mục đích |
|---|---|---|
| Timestamp | Thời điểm UTC | Sắp xếp và đối chiếu sự kiện. |
| Event type | stomp.auth.denied, stomp.frame.received | Phân loại sự kiện. |
| STOMP command | CONNECT, SEND, SUBSCRIBE, DISCONNECT | Biết loại thao tác. |
| Route chuẩn hóa | chat.send, orders.submit, other | Biết luồng ứng dụng mà không lộ ID động. |
| Outcome | accepted, rejected, failed | Theo dõi kết quả. |
| Reason code | invalid_token, destination_denied | Điều tra lỗi bằng mã ổn định. |
| Correlation ID | Mã ngẫu nhiên do server tạo | Nối các log của cùng một luồng xử lý. |
| Application instance | Tên instance hoặc pod đã chuẩn hóa | Xác định node xử lý message. |
| Latency | Thời gian xử lý theo ms | Phân tích hiệu năng. |
| Size bucket | Nhóm kích thước, nếu cần | Quan sát xu hướng mà không lưu body. |

Chỉ ghi user pseudonym hoặc session fingerprint khi thật sự cần và đã được phê duyệt. Nếu cần liên kết sự kiện theo session, có thể dùng HMAC với khóa bí mật được quản lý riêng; tránh ghi session ID thô hoặc dùng hash không khóa cho giá trị có thể đoán được.

Không đưa token, username, session ID hoặc destination động vào metric label. Các giá trị có độ đa dạng cao làm tăng cardinality, tiêu tốn tài nguyên hệ thống metrics và có thể làm lộ dữ liệu.

## 5. Dùng ChannelInterceptor để ghi metadata an toàn

Spring cho phép đăng ký ChannelInterceptor trên client inbound channel. Interceptor có thể đọc STOMP command và destination qua StompHeaderAccessor. Ví dụ dưới đây chỉ ghi command và route cố định trong allowlist; nó không đọc body, token, native headers, Principal hoặc session ID.

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

            // Command là enum; route chỉ có thể là một nhãn cố định.
            // Không ghi message, payload, headers, Principal hoặc session ID.
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

Hàm safeRoute trả về nhãn cố định thay cho destination tùy ý từ client. Nếu ứng dụng có destination động như /app/rooms/{roomId}/messages, hãy ánh xạ nó sang một route template hoặc nhãn như room.message. Không ghi roomId thực tế nếu không có nhu cầu và quyền rõ ràng.

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

    // Giữ cấu hình endpoint, broker và application prefix hiện có.
}
~~~

Đây là phần bổ sung vào cấu hình hiện có. Nếu dự án đã có WebSocketConfig với @EnableWebSocketMessageBroker, hãy thêm phương thức configureClientInboundChannel và dependency interceptor vào class đó; không tạo cấu hình broker thứ hai.

Interceptor mẫu chỉ quan sát inbound message. Nếu cần quan sát outbound, có thể đăng ký interceptor trên client outbound channel và áp dụng cùng allowlist. Không được giả định outbound body an toàn chỉ vì message được tạo từ server; body vẫn có thể chứa dữ liệu riêng tư.

Ví dụ log:

~~~text
stomp.in command=CONNECT route=none
stomp.in command=SEND route=chat.send
stomp.in command=SUBSCRIBE route=other
~~~

Các dòng này cho biết loại thao tác và route đã chuẩn hóa mà không chứa token, password, username, session ID hoặc payload.

## 6. Ghi nhận sự kiện bảo mật mà không lộ bí mật

Không ghi bí mật không có nghĩa là bỏ qua sự kiện bảo mật. Có thể ghi:

- Kết quả xác thực CONNECT: accepted hoặc rejected.
- Lý do thất bại bằng mã ổn định như invalid_token, expired_credential hoặc missing_identity.
- Lệnh SEND hoặc SUBSCRIBE bị từ chối bởi authorization.
- Client truy cập destination không được phép.
- Frame sai định dạng, vượt giới hạn kích thước hoặc không vượt qua kiểm tra dữ liệu.
- Kết nối bị ngắt bất thường, heartbeat timeout hoặc broker connection thất bại.
- Tần suất gửi bất thường, hành vi dò destination hoặc vượt rate limit.

Ví dụ log sự kiện xác thực thất bại:

~~~java
log.warn(
    "stomp.auth outcome={} reason={} route={} correlationId={}",
    "rejected",
    "invalid_token",
    "connect",
    correlationId
);
~~~

correlationId trong ví dụ phải do server hoặc hệ thống tracing đáng tin cậy tạo ra. Không lấy nguyên giá trị tùy ý từ client rồi ghi vào log nếu chưa giới hạn định dạng và độ dài.

Với lỗi, ưu tiên ghi exception class, mã lỗi nội bộ và correlation ID. Chỉ ghi stack trace khi đã kiểm tra rằng exception message và các field liên quan không chứa bí mật hoặc payload. Không ghi nguyên token sai, CONNECT header hoặc frame để giải thích lý do từ chối.

## 7. Allowlist, redaction và log injection

### Ưu tiên allowlist

Hãy chọn trước các trường được phép ghi. Không log toàn bộ headers rồi cố gắng xóa một danh sách vài tên nhạy cảm. Danh sách bí mật có thể mở rộng, có thể có custom header và có thể xuất hiện trong nhiều định dạng khác nhau.

Nếu bắt buộc ghi một trường do client cung cấp, hãy:

1. Xác định mục đích vận hành cụ thể.
2. Kiểm tra kiểu, độ dài và định dạng.
3. Loại bỏ hoặc mã hóa ký tự điều khiển như CR và LF.
4. Giới hạn độ dài trước khi ghi.
5. Không cho phép giá trị tạo thêm dòng hoặc field log giả.
6. Kiểm thử với newline, delimiter và dữ liệu canary giả lập bí mật.

Dùng structured logging và tham số hóa logger để dữ liệu được ghi thành field riêng. Structured logging không thay thế việc lọc và redaction: nếu field chứa token thì JSON log vẫn làm lộ token.

### Redaction tại nguồn

Loại bỏ dữ liệu ngay tại điểm tạo log. Không dựa hoàn toàn vào pipeline downstream để che token sau khi token đã được ghi vào file cục bộ hoặc chuyển qua agent thu thập log. Masking ở hệ thống tập trung chỉ là lớp phòng vệ bổ sung.

Không ghi payload.length() hoặc hash của payload như giải pháp mặc định. Kích thước và hash đôi khi vẫn cho phép suy luận dữ liệu; chỉ ghi khi có mục đích rõ ràng và đã đánh giá rủi ro.

## 8. Log level và kiểm soát khối lượng

Trong production:

- Không bật TRACE hoặc DEBUG diện rộng cho WebSocket, Messaging, Security hoặc toàn bộ ứng dụng nếu chưa kiểm tra nội dung thực tế mà logger phát ra.
- Dùng logger ứng dụng riêng để ghi event đã được làm sạch.
- Bật debug tạm thời trong môi trường kiểm thử, giới hạn thời gian, người truy cập và dữ liệu thử nghiệm.
- Không bật raw frame logging trong production.
- Dùng sampling cho sự kiện thành công có tần suất cao; vẫn ghi sự kiện bảo mật quan trọng sau khi loại bỏ bí mật.
- Rate-limit log lặp lại do client gửi frame sai liên tục để tránh log flooding.
- Dùng metrics tổng hợp cho throughput, lỗi, latency và số kết nối; không dùng token, username, session ID hoặc payload làm metric label.

Kiểm tra cả log do reverse proxy, load balancer, API gateway, container runtime và APM agent tạo ra. Dù ứng dụng không ghi token, URL có token trong query string vẫn có thể bị ghi ở tầng HTTP.

## 9. Bảo vệ log sau khi tạo

Log vẫn có thể chứa metadata vận hành và dữ liệu cá nhân đã được giảm thiểu. Hãy bảo vệ chúng như tài sản cần kiểm soát:

- Giới hạn quyền đọc theo vai trò và nhu cầu công việc.
- Ghi audit khi người dùng truy cập hoặc xuất log nhạy cảm.
- Mã hóa khi truyền và khi lưu trữ.
- Thiết lập retention phù hợp với mục đích và yêu cầu pháp lý; tự động xóa khi hết hạn.
- Tách quyền quản trị log khỏi quyền quản trị ứng dụng khi có thể.
- Bảo vệ tính toàn vẹn và sao lưu theo chính sách vận hành.
- Không sao chép log production có dữ liệu cá nhân sang máy phát triển hoặc ticket công khai.

Nếu phát hiện token hoặc password đã bị ghi vào log, xử lý như sự cố lộ bí mật: hạn chế quyền truy cập log, xác định phạm vi bản sao và hệ thống downstream, thu hồi hoặc rotate credential liên quan, rồi xử lý bản log theo quy trình sự cố. Xóa một file log cục bộ không đảm bảo các bản sao trong hệ thống tập trung, backup hoặc APM đã biến mất.

## 10. Kiểm thử để chứng minh log không chứa bí mật

Một kiểm thử hữu ích là gửi dữ liệu canary giả lập qua các đường đi STOMP và xác nhận chúng không xuất hiện trong log:

- CONNECT có header giả lập Authorization: Bearer CANARY_TOKEN.
- CONNECT có custom header chứa CANARY_SECRET.
- SEND có JSON body chứa CANARY_PRIVATE_MESSAGE.
- Payload có email hoặc số điện thoại giả lập.
- Destination có ID động hoặc ký tự CR/LF.

Sau khi chạy, tìm từng chuỗi canary trong log ứng dụng, access log, proxy log và log collector của môi trường kiểm thử. Kết quả mong đợi: log chỉ chứa command, route allowlist, outcome và correlation ID; không có giá trị canary.

Kiểm tra thêm rằng:

- Code logging không gọi message.toString() hoặc dump headers/body.
- Destination lạ được ánh xạ thành other.
- Lỗi xác thực chỉ ghi reason code, không ghi token đầu vào.
- Log injection không tạo thêm dòng hoặc field giả.
- Debug log tạm thời không vô tình bật ở production.

## 11. Ví dụ so sánh log không an toàn và log an toàn

| Không an toàn | An toàn hơn |
|---|---|
| Ghi nguyên Message<?> hoặc STOMP frame | Ghi command và route đã chuẩn hóa. |
| Ghi toàn bộ native header map | Ghi loại xác thực hoặc kết quả xác thực. |
| Ghi Authorization hoặc CONNECT login/passcode | Ghi auth.outcome=rejected và reason=invalid_token. |
| Ghi JSON body của SEND | Ghi event type và kết quả xử lý. |
| Ghi session ID hoặc cookie | Dùng correlation ID do server tạo; HMAC session identifier nếu thật sự cần. |
| Ghi destination động có email/user ID | Ghi route template hoặc nhãn allowlist. |
| Ghi exception message nguyên văn | Ghi exception class, error code và correlation ID sau khi đánh giá nội dung. |

## 12. Checklist trước khi bật logging cho STOMP

1. Có logger nào ghi raw frame, body, Message<?> hoặc native headers không?
2. CONNECT có thể chứa token, login, passcode hoặc CSRF token không?
3. Destination có thể chứa username, tenant ID, email hoặc dữ liệu nghiệp vụ không?
4. Access log có ghi query string của WebSocket URL không?
5. Interceptor có chỉ ghi các field nằm trong allowlist không?
6. Exception message và stack trace có thể chứa payload hoặc credential không?
7. Log có được giới hạn quyền đọc, mã hóa, đặt retention và audit không?
8. Có kiểm thử canary chứng minh token, credential và payload không xuất hiện trong log không?

Nếu bất kỳ câu trả lời nào cho thấy dữ liệu bí mật có thể đi vào log, hãy sửa tại nguồn tạo log trước khi triển khai production.

## Tài liệu tham khảo

- [Spring Framework — Interception](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/interceptors.html): đăng ký ChannelInterceptor, đọc STOMP command và header accessor.
- [Spring Framework — Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication.html): xác thực HTTP handshake và Principal gắn với STOMP session.
- [Spring Framework — Token Authentication](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/authentication-token-based.html): xử lý token ở CONNECT bằng interceptor và rủi ro token trong query string.
- [Spring Security — WebSocket Security](https://docs.spring.io/spring-security/reference/servlet/integrations/websocket.html): xác thực, phân quyền message và bảo vệ CONNECT.
- [OWASP — Logging Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html): dữ liệu cần loại bỏ, che, hash hoặc mã hóa trong log.
