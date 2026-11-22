# Khôi phục kết nối relay và giới hạn bảo đảm khi mất kết nối

## Mục tiêu

Khi Spring Framework dùng STOMP broker relay kết nối tới broker bên ngoài, sự cố mạng có thể ảnh hưởng đến system connection của ứng dụng, các TCP connection riêng của WebSocket client hoặc chính WebSocket giữa client và server. Mỗi kết nối có vòng đời và cơ chế khôi phục khác nhau.

Bài học này trình bày topology kết nối, heartbeat, tự reconnect của relay, `BrokerAvailabilityEvent`, trách nhiệm reconnect/resubscribe của client và giới hạn bảo đảm delivery. Phần cuối hướng dẫn dùng retry, transactional outbox, idempotency và kiểm thử sự cố.

## 1. Các kết nối mà broker relay quản lý

Khi gọi `enableStompBrokerRelay(...)`, Spring chuyển tiếp STOMP message giữa message channel nội bộ và một broker đầy đủ tính năng như RabbitMQ hoặc ActiveMQ có bật STOMP.

Relay quản lý hai nhóm TCP connection:

| Nhóm | Số lượng | Vai trò |
| --- | --- | --- |
| System connection | Một kết nối dùng chung | Gửi message phát sinh từ code phía server tới broker |
| Client connection | Một kết nối cho mỗi WebSocket client đang kết nối | Chuyển STOMP frame của client tới broker và chuyển frame từ broker về client tương ứng |

System connection dành cho message do ứng dụng server phát ra; nó không được dùng để nhận message broker gửi về cho subscriber. Mỗi WebSocket client có một kết nối TCP riêng do relay quản lý.

~~~text
Ứng dụng Spring
      |
      | brokerChannel
      v
STOMP Broker Relay
      |
      +---- System TCP connection --------> STOMP Broker
      |
      +---- Client TCP connection A <-----> STOMP Broker
      |                 |
      |                 +------------------> WebSocket Client A
      |
      +---- Client TCP connection B <-----> STOMP Broker
                        |
                        +------------------> WebSocket Client B
~~~

Message từ service qua `SimpMessagingTemplate` đi qua `brokerChannel` và system connection. Message client gửi bằng STOMP đi qua client connection của session tương ứng. Đây là khác biệt quan trọng khi phân tích reconnect: relay có thể tự khôi phục system connection, còn client phải tự khôi phục session của mình.

## 2. Cấu hình relay và thông tin xác thực

Ví dụ cấu hình Java:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfig
        implements WebSocketMessageBrokerConfigurer {

    private final RelayCredentials credentials;

    public WebSocketConfig(RelayCredentials credentials) {
        this.credentials = credentials;
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.enableStompBrokerRelay("/topic", "/queue")
                .setRelayHost("stomp-broker.internal")
                .setRelayPort(61613)
                .setSystemLogin(credentials.systemLogin())
                .setSystemPasscode(credentials.systemPasscode())
                .setClientLogin(credentials.clientLogin())
                .setClientPasscode(credentials.clientPasscode());

        registry.setApplicationDestinationPrefixes("/app");
        registry.setUserDestinationPrefix("/user");
    }
}
~~~

`RelayCredentials` là một cấu hình do ứng dụng định nghĩa để cung cấp credentials. Đưa mật khẩu vào secret manager hoặc kho cấu hình bảo mật; không commit mật khẩu vào source control.

- `systemLogin` và `systemPasscode` dùng cho system connection.
- `clientLogin` và `clientPasscode` dùng cho các kết nối TCP tạo thay mặt WebSocket client.
- Relay luôn ghi login/passcode của nó vào CONNECT frame chuyển tiếp cho broker. Credentials STOMP do WebSocket client gửi sẽ bị bỏ qua. Client nên xác thực bằng HTTP handshake và cơ chế bảo mật endpoint WebSocket để Spring xác lập danh tính người dùng.
- `/topic` và `/queue` là các prefix chuyển tới broker ngoài; `/app` dành cho handler ứng dụng; `/user` là prefix user destination do Spring phân giải.

## 3. Heartbeat và reconnect của system connection

Relay gửi và nhận STOMP heartbeat trên system connection để phát hiện kết nối không còn hoạt động. Theo tài liệu Spring Framework, mặc định:

- Heartbeat gửi: 10 giây.
- Heartbeat nhận: 10 giây.
- Khi mất kết nối tới broker, relay thử kết nối lại system connection mỗi 5 giây cho tới khi thành công.

Đây là giá trị mặc định, không phải SLA phục hồi. Thời gian phát hiện lỗi thực tế còn phụ thuộc heartbeat negotiation, scheduler, mạng, TCP timeout và trạng thái broker.

Khi broker hoạt động trở lại, relay thiết lập lại system connection. Đường gửi message từ server có thể hoạt động trở lại sau khi kết nối được phục hồi.

Reconnect chỉ khôi phục kết nối. Nó không tự lưu mọi message nghiệp vụ phát sinh trong thời gian gián đoạn và cũng không bảo đảm tự phát lại những message chưa tới broker.

## 4. Theo dõi trạng thái với `BrokerAvailabilityEvent`

Spring phát `BrokerAvailabilityEvent` khi trạng thái sẵn sàng của broker thay đổi. Với broker relay, sự kiện phản ánh việc system connection bị mất hoặc được thiết lập lại.

Ví dụ theo dõi trạng thái bằng `@EventListener`:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

import org.springframework.context.event.EventListener;
import org.springframework.messaging.simp.broker.BrokerAvailabilityEvent;
import org.springframework.stereotype.Component;

@Component
public class BrokerAvailabilityTracker {

    private final AtomicBoolean available = new AtomicBoolean(false);

    @EventListener
    public void onBrokerAvailability(BrokerAvailabilityEvent event) {
        available.set(event.isBrokerAvailable());
    }

    public boolean isAvailable() {
        return available.get();
    }
}
~~~

`AtomicBoolean` cho phép các thread đọc và cập nhật trạng thái an toàn. Trạng thái ban đầu là `false`; event cho biết broker available sẽ chuyển cờ sang `true`, còn event unavailable sẽ chuyển về `false`.

Service có thể kiểm tra trước khi gửi, đồng thời vẫn phải bắt lỗi gửi:

~~~java
import org.springframework.messaging.MessageDeliveryException;
import org.springframework.messaging.simp.SimpMessagingTemplate;
import org.springframework.stereotype.Service;

@Service
public class UpdatePublisher {

    private final SimpMessagingTemplate messaging;
    private final BrokerAvailabilityTracker availability;

    public UpdatePublisher(
            SimpMessagingTemplate messaging,
            BrokerAvailabilityTracker availability) {
        this.messaging = messaging;
        this.availability = availability;
    }

    public void publish(UpdateEvent event) {
        if (!availability.isAvailable()) {
            throw new IllegalStateException(
                    "STOMP broker is currently unavailable");
        }

        try {
            messaging.convertAndSend("/topic/updates", event);
        }
        catch (MessageDeliveryException exception) {
            // Ghi log và chuyển lỗi cho chính sách retry/outbox.
            throw exception;
        }
    }
}
~~~

Kiểm tra availability tránh một số lần gửi khi đã biết system connection đang ngắt. Tuy nhiên, trạng thái có thể đổi ngay sau lần kiểm tra, vì vậy không được bỏ xử lý `MessageDeliveryException`.

Giới hạn của event:

- Phản ánh trạng thái system connection của relay, không phải health check cho từng client connection.
- Không xác nhận một message cụ thể đã được broker lưu hoặc client xử lý.
- Không được phát cho từng message.
- Không thay thế retry hoặc lưu trữ bền vững cho dữ liệu nghiệp vụ.

## 5. Vì sao client phải tự reconnect?

Spring tự reconnect system connection của relay. Các kết nối TCP riêng của từng WebSocket client không được tự động khôi phục thành STOMP session mới bởi cơ chế đó.

Khi broker ngừng hoạt động, client có thể mất kết nối. Nếu heartbeat được bật, client thường phát hiện broker không phản hồi trong khoảng 10 giây theo mô tả của Spring; thời gian thực tế phụ thuộc cấu hình và mạng.

Sau khi mất kết nối, client cần:

1. Đánh dấu session hiện tại đã mất.
2. Thử mở lại WebSocket/STOMP connection theo chính sách retry.
3. Chờ STOMP CONNECTED để xác nhận session mới sẵn sàng.
4. Gửi lại các SUBSCRIBE cần thiết.
5. Đồng bộ hoặc yêu cầu phát lại dữ liệu còn thiếu nếu nghiệp vụ cần.
6. Xử lý duplicate bằng event ID hoặc business key.

Ví dụ với thư viện JavaScript `@stomp/stompjs`:

~~~javascript
import { Client } from "@stomp/stompjs";

const client = new Client({
    brokerURL: "wss://example.com/ws",
    reconnectDelay: 5000,
    heartbeatIncoming: 10000,
    heartbeatOutgoing: 10000
});

client.onConnect = () => {
    // Callback chạy sau mỗi lần kết nối thành công.
    // Đăng ký subscription tại đây để resubscribe sau reconnect.
    client.subscribe("/topic/updates", frame => {
        const event = JSON.parse(frame.body);
        handleUpdate(event);
    });
};

client.onStompError = frame => {
    console.error("STOMP broker error:", frame.headers["message"]);
};

client.activate();
~~~

`reconnectDelay` là cấu hình của thư viện client, không phải thuộc tính của Spring relay. Trong hệ thống lớn, cân nhắc exponential backoff, giới hạn thời gian chờ tối đa và jitter để tránh reconnect storm.

Với `WebSocketStompClient` phía Java, ứng dụng gọi `connect(...)` và nhận callback qua `StompSessionHandler`. Khi gặp lỗi transport hoặc `ConnectionLostException`, code client phải lên lịch kết nối lại. Sau callback `afterConnected` của session mới, đăng ký lại subscription. Không giả định `StompSession` cũ tự sống lại sau khi TCP connection bị mất.

## 6. Subscription và dữ liệu trong thời gian offline

Subscription thuộc về STOMP session. Khi client kết nối lại, nó có session mới và phải gửi lại SUBSCRIBE sau khi nhận CONNECTED. Subscription của session cũ không tự chuyển sang session mới.

Broker có thể hỗ trợ durable subscription, queue bền vững hoặc lưu message cho consumer offline. Khả năng này phụ thuộc loại broker, cấu hình destination, subscription identity, acknowledgement mode và chính sách lưu trữ. Reconnect rồi subscribe lại tự nó không bảo đảm các message phát trong thời gian offline sẽ được phát lại.

Một destination dạng `/topic/...` thường phục vụ subscriber đang hoạt động; nó không mặc nhiên là hộp thư lưu message cho client offline. Với queue hoặc durable subscription, cần đọc tài liệu broker và xác minh chính sách lưu, hết hạn, định danh consumer và phân phối lại.

## 7. Phân biệt các mức xác nhận khi gửi

Không nên gộp mọi trạng thái thành “đã gửi thành công”:

| Mức | Có thể kết luận | Chưa thể kết luận |
| --- | --- | --- |
| `convertAndSend` không ném exception | Lời gọi Spring messaging không báo lỗi đồng bộ | Client đã nhận hoặc xử lý message |
| Broker trả `RECEIPT` | Broker/server đã xử lý frame tương ứng theo STOMP | Logic nghiệp vụ phía consumer đã commit |
| Client nhận `MESSAGE` | Frame đã tới client connection | Ứng dụng client đã xử lý thành công |
| Consumer gửi application ACK sau xử lý | Ứng dụng nhận xác nhận theo giao thức nghiệp vụ tự thiết kế | Không có duplicate nếu thiếu idempotency |

STOMP hỗ trợ `receipt` header. Client có thể yêu cầu broker trả `RECEIPT` sau khi xử lý SEND hoặc SUBSCRIBE. Với Spring Java STOMP client, `StompSession.setAutoReceipt(true)` tự thêm receipt header cho các thao tác tiếp theo; hoặc có thể đặt receipt thủ công trong `StompHeaders`. Kết quả được theo dõi qua `Receiptable`. Tính năng này cần `TaskScheduler` để theo dõi timeout receipt.

Ví dụ:

~~~java
stompSession.setAutoReceipt(true);

Receiptable receipt = stompSession.send(
        "/topic/updates",
        updateEvent
);

receipt.addReceiptTask(() ->
        log.info("Broker acknowledged the SEND frame"));

receipt.addReceiptLostTask(() ->
        log.warn("Timed out waiting for broker receipt"));
~~~

Receipt xác nhận ở mức STOMP broker. Nó không thay thế xác nhận nghiệp vụ từ ứng dụng nhận. Nếu cần biết người nhận đã lưu đơn hàng hoặc hoàn tất tác vụ, cần application-level acknowledgement riêng.

`SimpMessagingTemplate.convertAndSend(...)` trả về `void`. Việc method không ném exception không chứng minh consumer đã xử lý payload. Ngoài ra, simple broker của Spring chỉ hỗ trợ một tập con STOMP command và không hỗ trợ ACK hoặc receipt; các tính năng này cần broker đầy đủ tính năng tương thích STOMP.

## 8. Giới hạn bảo đảm khi mất kết nối

Spring broker relay tự reconnect system connection, nhưng không tự cung cấp delivery end-to-end hoặc exactly-once cho nghiệp vụ.

### Message phát ra khi system connection đang mất

Relay chưa thể chuyển message server-originated tới broker qua system connection. Lời gọi gửi có thể thất bại với `MessageDeliveryException`. Ứng dụng phải quyết định trả lỗi, bỏ qua, retry hoặc lưu message để gửi sau.

### Kết nối đứt đúng lúc gửi

Ứng dụng có thể không biết chắc broker đã nhận frame hay chưa. Retry có thể tạo duplicate nếu broker đã nhận message trước khi kết nối đứt nhưng phản hồi không tới được ứng dụng.

### Broker nhận message trong lúc client offline

Message có được giữ lại hay không phụ thuộc queue/subscription và cấu hình broker. Topic subscription thông thường có thể không giữ message cho client không kết nối. Cần kiểm tra durable queue, persistent message và acknowledgement semantics của broker.

### Client nhận frame nhưng mất kết nối trước khi xử lý xong

Server không tự biết ứng dụng client đã hoàn tất hay chưa. Nếu ứng dụng phát lại message sau reconnect, consumer có thể nhận trùng. Consumer cần xử lý idempotent theo event ID hoặc business key.

### Ứng dụng server restart

Reconnect của relay không thay thế lưu trữ bền vững trong ứng dụng. Message quan trọng chỉ nằm trong bộ nhớ trước khi gửi có thể mất khi process restart. Transactional outbox lưu ý định gửi trong cùng transaction nghiệp vụ.

## 9. Retry và transactional outbox

Với notification quan trọng, lưu message cần phát trong database trước khi gửi. Transactional outbox thường có luồng:

1. Trong cùng database transaction, cập nhật dữ liệu nghiệp vụ và thêm bản ghi outbox.
2. Dispatcher đọc các bản ghi chưa gửi.
3. Dispatcher kiểm tra broker availability và thử gửi.
4. Khi có xác nhận phù hợp với mức bảo đảm yêu cầu, đánh dấu bản ghi đã xử lý.
5. Khi lỗi tạm thời, giữ bản ghi để retry với exponential backoff và jitter.
6. Consumer lưu event ID đã xử lý hoặc dùng unique business key để bỏ qua message trùng.

Ví dụ các trường trong outbox:

| Trường | Mục đích |
| --- | --- |
| `event_id` | ID duy nhất để deduplicate |
| `destination` | STOMP destination |
| `payload` | Nội dung message đã serialize hoặc dữ liệu tham chiếu |
| `status` | `PENDING`, `IN_PROGRESS`, `SENT`, `FAILED` |
| `attempt_count` | Số lần thử |
| `next_attempt_at` | Thời điểm được phép thử tiếp |
| `created_at` | Thời điểm tạo sự kiện |
| `last_error` | Lỗi gần nhất |

Không đánh dấu outbox `SENT` chỉ vì broker availability đang là true. Cũng cần phân biệt broker receipt với xác nhận consumer đã commit nghiệp vụ. Chọn điểm hoàn tất dựa trên mức xác nhận hệ thống thực sự cần.

Retry có thể gây duplicate nếu kết quả lần gửi trước không xác định. Consumer nên có unique constraint trên `event_id`; transaction xử lý message sẽ ghi ID và cập nhật dữ liệu nghiệp vụ một cách nguyên tử.

Mô hình outbox, retry và deduplication thường tạo delivery kiểu at-least-once ở tầng ứng dụng. Không nên gọi đó là exactly-once xuyên suốt broker, mạng, client và database nếu không có giao thức giao dịch phân tán bảo đảm điều đó.

## 10. Backoff và kiểm soát tải

Nếu nhiều client reconnect cùng lúc sau một sự cố, chúng có thể đồng thời tạo kết nối mới, gửi CONNECT và đăng ký subscription. Reconnect storm có thể làm broker quá tải ngay khi vừa phục hồi.

Chính sách retry nên:

- Bắt đầu với khoảng chờ ngắn, sau đó tăng dần theo exponential backoff.
- Giới hạn khoảng chờ tối đa.
- Thêm random jitter để phân tán thời điểm thử.
- Reset backoff sau khi kết nối ổn định đủ lâu.
- Không tạo nhiều reconnect loop cho cùng một client.
- Giới hạn số lần thử nếu nghiệp vụ cần chuyển sang trạng thái cần can thiệp.

Ví dụ hàm backoff minh họa:

~~~java
long delayMillis(int attempt) {
    long base = 1_000L;
    long max = 30_000L;
    int exponent = Math.min(attempt, 5);

    long exponential = Math.min(max, base * (1L << exponent));
    long jitter = ThreadLocalRandom.current()
            .nextLong(0, Math.max(1, exponential / 4));

    return Math.min(max, exponential + jitter);
}
~~~

Đây là chính sách retry của ứng dụng, không phải thuật toán reconnect nội bộ của Spring relay.

## 11. Broker failover và tính sẵn sàng cao

Theo mặc định, relay reconnect tới cùng host và port đã cấu hình. Spring cho phép tùy biến TCP client hoặc cung cấp địa chỉ broker động để chọn địa chỉ khác trong mỗi lần thử kết nối.

Ví dụ cấu hình dùng TCP client tùy biến:

~~~java
registry.enableStompBrokerRelay("/queue/", "/topic/")
        .setTcpClient(createTcpClient());
~~~

`createTcpClient()` phải được triển khai theo phiên bản Spring và Reactor Netty của dự án. Tài liệu Spring minh họa việc dùng `ReactorNettyTcpClient` với address supplier để chọn địa chỉ kết nối.

Khả năng chọn broker khác chỉ giải quyết việc tìm endpoint. Nó không tự sao chép message, queue, subscription hoặc trạng thái giữa các broker node. High availability còn phụ thuộc cluster, replication, quorum, persistence, routing và failover của broker.

Nếu dùng virtual host, relay có thể đặt header STOMP `host` theo thuộc tính `virtualHost`. Điều này hữu ích khi địa chỉ TCP thực tế khác host logic mà broker yêu cầu.

## 12. Theo dõi session và xử lý event

Ngoài `BrokerAvailabilityEvent`, Spring phát các event vòng đời STOMP:

- `SessionConnectEvent`: nhận CONNECT và bắt đầu client session.
- `SessionConnectedEvent`: broker phản hồi CONNECTED; session STOMP đã được thiết lập.
- `SessionSubscribeEvent`: nhận SUBSCRIBE.
- `SessionUnsubscribeEvent`: nhận UNSUBSCRIBE.
- `SessionDisconnectEvent`: session kết thúc.

Có thể dùng các event để theo dõi session, user, subscription và sự cố kết nối. `SessionDisconnectEvent` đôi khi được phát nhiều hơn một lần cho cùng session, vì vậy logic dọn dẹp phải idempotent.

Event vòng đời không phải event cho từng message. Nếu cần quan sát hoặc kiểm soát message inbound/outbound, dùng `ChannelInterceptor` trên channel phù hợp và đọc command/header bằng `StompHeaderAccessor` hoặc `SimpMessageHeaderAccessor`.

## 13. Kiểm thử mất kết nối

Một integration test nên kiểm tra cả trạng thái relay và hành vi client:

1. Khởi động Spring application và STOMP broker.
2. Kết nối STOMP client, đợi CONNECTED và đăng ký subscription.
3. Xác nhận message gửi/nhận bình thường.
4. Dừng broker hoặc chặn đường TCP.
5. Xác nhận ứng dụng nhận trạng thái unavailable qua `BrokerAvailabilityEvent`.
6. Gọi service gửi message và xác nhận lỗi được xử lý đúng.
7. Khởi động broker lại.
8. Chờ relay phát trạng thái available.
9. Xác nhận client reconnect, nhận CONNECTED và resubscribe.
10. Kiểm tra message trong outbox được gửi lại theo chính sách.
11. Gửi lại cùng event ID để xác nhận consumer không thực hiện nghiệp vụ hai lần.
12. Kiểm tra trường hợp kết nối đứt ngay sau khi broker nhận message để đánh giá duplicate và retry.

Đặt timeout rõ ràng cho từng bước; ưu tiên chờ event hoặc receipt thay vì sleep cố định dài. Broker thật hoặc container broker tương thích STOMP sẽ giúp kiểm tra đúng hơn hành vi queue, persistence và acknowledgement.

## 14. Checklist vận hành

- Cấu hình heartbeat phù hợp cho system connection và client.
- Theo dõi trạng thái `BrokerAvailabilityEvent`.
- Bắt và phân loại `MessageDeliveryException`.
- Đo số lần relay reconnect, client reconnect và thời gian broker unavailable.
- Giới hạn reconnect storm bằng backoff và jitter.
- Đảm bảo client resubscribe sau CONNECTED.
- Quyết định destination nào cần durable queue hoặc persistence.
- Dùng event ID và idempotency cho consumer.
- Lưu message quan trọng trong outbox trước khi phát.
- Phân biệt broker receipt với business acknowledgement.
- Kiểm tra failover và replication của broker.
- Giữ logic xử lý `SessionDisconnectEvent` idempotent.

## 15. Tổng kết

Spring STOMP broker relay tự khôi phục **system connection** tới broker ngoài: mặc định gửi/nhận heartbeat mỗi 10 giây và thử kết nối lại sau mỗi 5 giây khi mất kết nối. `BrokerAvailabilityEvent` thông báo thay đổi trạng thái system connection; code gửi message vẫn cần xử lý `MessageDeliveryException`.

Các TCP connection riêng cho WebSocket client có vòng đời độc lập. Client cần tự reconnect, đợi CONNECTED và đăng ký lại subscription. Không được mặc định message phát trong thời gian offline đã được lưu hoặc phát lại.

`SimpMessagingTemplate` và broker relay không tự cung cấp bảo đảm exactly-once cho nghiệp vụ. Với message quan trọng, kết hợp broker persistence phù hợp, transactional outbox, retry có kiểm soát, receipt/acknowledgement đúng tầng và consumer idempotent.

## Tài liệu tham khảo

- [Spring Framework Reference — Connecting to a Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay-configure.html)
- [Spring Framework Reference — Events](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/application-context-events.html)
- [Spring Framework Reference — STOMP Client](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html)
- [Spring Framework Reference — External Broker](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-broker-relay.html)
- [Spring Framework Javadoc — BrokerAvailabilityEvent](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/broker/BrokerAvailabilityEvent.html)
