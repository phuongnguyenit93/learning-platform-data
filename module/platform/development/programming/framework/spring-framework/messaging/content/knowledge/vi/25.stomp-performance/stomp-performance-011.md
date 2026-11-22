# WebSocketMessageBrokerStats và chẩn đoán tải kết nối trong Spring STOMP

## Mục tiêu

Khi ứng dụng dùng Spring WebSocket + STOMP, số kết nối tăng chưa chắc đã là sự cố. Một hệ thống có thể giữ hàng nghìn session ổn định nếu message rate, kích thước payload, fan-out, mạng và tài nguyên xử lý nằm trong giới hạn. Sự cố thường xuất hiện khi một trong các tầng bị nghẽn: WebSocket transport, STOMP processing, executor của inbound/outbound channel, SockJS heartbeat scheduler hoặc broker relay.

Spring cung cấp bean **WebSocketMessageBrokerStats** để gom các bộ đếm và thống kê từ hạ tầng messaging. Bean này giúp trả lời những câu hỏi như:

- Hiện có bao nhiêu WebSocket/SockJS session đang hoạt động?
- Bao nhiêu session đã đóng bất thường vì không gửi frame, gửi chậm hoặc gặp lỗi transport?
- Số CONNECT, CONNECTED và DISCONNECT có cân đối không?
- Inbound channel đang xếp hàng message hay outbound channel đang bị client chậm làm nghẽn?
- Khi dùng broker relay, số TCP connection tới broker có phù hợp với số client session không?
- SockJS task scheduler có đủ khả năng gửi heartbeat không?

Các thống kê này là điểm bắt đầu để khoanh vùng. Chúng không thay thế metrics của JVM, WebSocket container, reverse proxy, database hay broker bên ngoài.

## 1. WebSocketMessageBrokerStats được tạo như thế nào?

Khi cấu hình messaging bằng **@EnableWebSocketMessageBroker** hoặc XML **websocket:message-broker**, Spring tự khai báo bean có tên **webSocketMessageBrokerStats** và kiểu **WebSocketMessageBrokerStats**. Bean tập hợp thông tin từ các thành phần chính của STOMP over WebSocket.

Mặc định, Spring ghi thống kê tổng hợp ở mức **INFO mỗi 30 phút**. Có thể xuất bean qua JMX bằng **MBeanExporter** để xem tại thời điểm chạy, ví dụ bằng JConsole hoặc công cụ JMX tương đương. Khoảng thời gian ghi log có thể điều chỉnh bằng **setLoggingPeriod(long)**; đơn vị là millisecond và giá trị bằng hoặc nhỏ hơn 0 sẽ hủy lịch ghi log.

Từ Spring Framework 6.2, bean cung cấp thêm các accessor trả về đối tượng thống kê có cấu trúc:

- **getWebSocketSessionStats()**: số liệu session WebSocket và SockJS.
- **getStompSubProtocolStats()**: bộ đếm frame CONNECT, CONNECTED, DISCONNECT được xử lý ở tầng STOMP.
- **getStompBrokerRelayStats()**: bộ đếm của broker relay nếu cấu hình relay.

Các accessor này có thể trả về **null** nếu thành phần tương ứng không được cấu hình hoặc không tồn tại. Ví dụ, ứng dụng dùng simple broker sẽ không có thống kê broker relay. Trên phiên bản Spring cũ hơn 6.2, hãy dựa vào chuỗi thống kê tổng hợp và các API có sẵn trong Javadoc của đúng phiên bản đang chạy.

Một cách lấy snapshot có cấu trúc:

~~~java
@Component
public class StompStatsSnapshot {

    private static final Logger log =
            LoggerFactory.getLogger(StompStatsSnapshot.class);

    private final WebSocketMessageBrokerStats stats;

    public StompStatsSnapshot(WebSocketMessageBrokerStats stats) {
        this.stats = stats;
    }

    public void logNow() {
        var sessions = stats.getWebSocketSessionStats();
        if (sessions != null) {
            log.info(
                    "WebSocket sessions: ws={}, sockjsStreaming={}, " +
                    "sockjsPolling={}, total={}, noFirstMessage={}, " +
                    "sendLimitExceeded={}, transportErrors={}",
                    sessions.getWebSocketSessions(),
                    sessions.getHttpStreamingSessions(),
                    sessions.getHttpPollingSessions(),
                    sessions.getTotalSessions(),
                    sessions.getNoMessagesReceivedSessions(),
                    sessions.getLimitExceededSessions(),
                    sessions.getTransportErrorSessions());
        }

        var stomp = stats.getStompSubProtocolStats();
        if (stomp != null) {
            log.info(
                    "STOMP frames: CONNECT={}, CONNECTED={}, DISCONNECT={}",
                    stomp.getTotalConnect(),
                    stomp.getTotalConnected(),
                    stomp.getTotalDisconnect());
        }

        var relay = stats.getStompBrokerRelayStats();
        if (relay != null) {
            log.info(
                    "Broker relay: handlers={}, CONNECT={}, CONNECTED={}, DISCONNECT={}",
                    relay.getTotalHandlers(),
                    relay.getTotalConnect(),
                    relay.getTotalConnected(),
                    relay.getTotalDisconnect());
        }

        log.info(
                "Inbound executor={}, outbound executor={}, SockJS scheduler={}",
                stats.getClientInboundExecutorStatsInfo(),
                stats.getClientOutboundExecutorStatsInfo(),
                stats.getSockJsTaskSchedulerStatsInfo());
    }
}
~~~

Đây là thành phần minh họa để đọc snapshot theo nhu cầu vận hành; ứng dụng cần các import Spring/SLF4J tương ứng. Bean **WebSocketMessageBrokerStats** đã được Spring cung cấp khi bật STOMP message broker, vì vậy không tự tạo thêm một bean cùng kiểu. Trong phần lớn hệ thống, log mặc định và JMX đã đủ để kiểm tra; chỉ thêm snapshot tùy chỉnh khi cần tích hợp với dashboard hoặc quy trình chẩn đoán riêng.

## 2. Hiểu đúng từng nhóm thống kê

### Client WebSocket Sessions

| Trường | Ý nghĩa | Cách sử dụng |
|---|---|---|
| **Current** | Số session hiện tại, chia theo WebSocket, SockJS HTTP streaming và HTTP polling | Đo số kết nối đồng thời trên từng instance |
| **Total** | Tổng số session đã được thiết lập kể từ khi process chạy | Theo dõi tốc độ tạo kết nối và churn |
| **Connect Failures / No Messages Received** | Session đã được tạo nhưng không nhận được message sub-protocol trong 60 giây | Điều tra client không gửi STOMP CONNECT, proxy hoặc mạng |
| **Send Limit Exceeded** | Session bị đóng vì vượt giới hạn thời gian gửi hoặc giới hạn buffer | Điều tra client chậm, mạng yếu, fan-out lớn |
| **Transport Errors** | Session đóng sau lỗi đọc/ghi WebSocket hoặc HTTP transport | Điều tra network, proxy, container và client disconnect |

**Current** là số lượng đồng thời; **Total** là bộ đếm tích lũy. Không so sánh hai số này như thể cùng đơn vị thời gian. Ví dụ, Current ổn định nhưng Total tăng nhanh có thể chỉ ra client liên tục reconnect, load balancer đóng kết nối, mobile network chập chờn hoặc ứng dụng tạo nhiều session ngắn hạn.

Connect Failures không có nghĩa HTTP handshake nhất thiết thất bại. Theo Spring, đây là các session đã được thiết lập nhưng không nhận được message đầu tiên trong vòng 60 giây. Với STOMP, trường hợp thường gặp là WebSocket đã mở nhưng client không gửi CONNECT, hoặc CONNECT không tới được ứng dụng do proxy, network hay client lỗi.

Send Limit Exceeded thường liên quan đến slow client. Spring chỉ dùng một thread tại một thời điểm để gửi tới một client; message tiếp theo được buffer trong khi send đang diễn ra. Khi send vượt thời gian hoặc buffer limit, Spring có thể đóng session để ngăn một client chậm chiếm quá nhiều tài nguyên.

Transport Errors bao gồm lỗi khi đọc hoặc ghi trên WebSocket connection hoặc HTTP request/response của SockJS. Đây là dấu hiệu cần đối chiếu log của server WebSocket, reverse proxy, ingress, TLS và client.

### STOMP Frames

Nhóm này đếm tổng số frame:

- **CONNECT**: client yêu cầu mở phiên STOMP.
- **CONNECTED**: server/broker phản hồi kết nối STOMP thành công.
- **DISCONNECT**: frame kết thúc phiên được xử lý.

Đây là bộ đếm vòng đời kết nối, không phải bộ đếm tổng SEND, MESSAGE hoặc SUBSCRIBE. Không dùng CONNECT/CONNECTED/DISCONNECT để suy ra message throughput.

DISCONNECT thường thấp hơn CONNECT khi session bị đóng bất thường hoặc client đóng transport mà không gửi frame DISCONNECT. Nếu CONNECT tăng nhưng CONNECTED không tăng tương ứng, hãy kiểm tra xác thực, lỗi CONNECT frame, broker không phản hồi hoặc relay không thiết lập được kết nối.

### STOMP Broker Relay

Nhóm này chỉ có ý nghĩa khi Spring dùng **enableStompBrokerRelay(...)** để chuyển tiếp tới broker ngoài.

| Trường | Ý nghĩa | Dấu hiệu cần kiểm tra |
|---|---|---|
| **TCP Connections** | Kết nối TCP tới broker thay mặt các WebSocket/STOMP client | So sánh với số client session hiện tại và system connection |
| **STOMP Frames** | CONNECT, CONNECTED và DISCONNECT được chuyển tiếp hoặc nhận từ broker | Kiểm tra kết nối broker, heartbeat và lỗi protocol |
| **Total Handlers** | Số connection handler mà relay đang theo dõi | Đối chiếu với số client đang kết nối và trạng thái broker |

Thông thường, số TCP connection của broker relay xấp xỉ số client WebSocket session cộng thêm **một system connection dùng chung** cho message phát ra từ ứng dụng. Đây là quy tắc kiểm tra nhanh, không phải một bất biến trong mọi thời điểm: số liệu có thể chênh lệch trong lúc kết nối đang mở/đóng hoặc khi hệ thống gặp lỗi.

Spring gửi DISCONNECT tới broker khi WebSocket session đóng, kể cả khi client đóng bất thường. Vì vậy, nếu bộ đếm DISCONNECT của relay thấp hơn đáng kể so với số kết nối đã thiết lập, có thể broker đang chủ động đóng TCP connection. Hãy kiểm tra broker log, heartbeat không tới đúng hạn, frame không hợp lệ, giới hạn connection hoặc lỗi xác thực.

Với simple broker tích hợp, không có TCP relay tới broker bên ngoài; nhóm relay có thể null hoặc không xuất hiện.

### Client Inbound Channel

**clientInboundChannel** nhận các message STOMP từ WebSocket client và đưa chúng qua interceptor, security, controller hoặc broker handler tùy destination.

Thống kê executor giúp nhìn thấy:

- Số thread hiện có và đang hoạt động.
- Số task đang chờ trong queue.
- Số task đã hoàn tất.
- Kích thước pool và trạng thái xử lý.

Tên và định dạng chi tiết phụ thuộc executor thực tế, vì Spring cung cấp chuỗi thông tin của thread pool. Điểm cần quan sát là queue có tăng liên tục hay không, active threads có thường xuyên chạm giới hạn hay không, và completed tasks có tiếp tục tăng hay bị chững lại.

Queue inbound tăng là dấu hiệu ứng dụng xử lý message chậm hơn tốc độ message đến. Nguyên nhân thường gặp:

- Controller gọi database hoặc REST API đồng bộ và chờ lâu.
- Service giữ lock hoặc thực hiện xử lý CPU nặng.
- Message converter hoặc validation tiêu tốn nhiều CPU.
- Một client gửi message với tốc độ quá cao.
- Inbound thread pool nhỏ so với workload I/O-bound.
- Hệ thống phụ thuộc như database connection pool đã cạn, khiến thread inbound bị chặn.

Nếu xử lý chủ yếu CPU-bound, số thread nên gần số CPU core. Nếu xử lý chủ yếu I/O-bound và chờ database hoặc hệ thống ngoài, có thể cần nhiều thread hơn. Tuy nhiên, tăng thread chỉ có ích nếu hệ thống phụ thuộc còn khả năng phục vụ; nếu database đã nghẽn, tăng thread có thể làm số request chờ tăng thêm.

### Client Outbound Channel

**clientOutboundChannel** đưa message từ broker hoặc ứng dụng về các WebSocket client. Nó thường chịu tải nặng khi một message được broadcast tới nhiều subscriber.

Queue outbound tăng có thể chỉ ra:

- Client có mạng chậm hoặc băng thông thấp.
- Một số client không đọc frame đủ nhanh.
- Payload quá lớn hoặc tần suất gửi quá cao.
- Một topic có quá nhiều subscriber.
- Fan-out tạo nhiều tác vụ gửi đồng thời.
- Outbound thread pool hoặc giới hạn buffer chưa phù hợp.

Khác inbound, tải outbound phụ thuộc nhiều vào mạng và tốc độ tiêu thụ của client. Tăng thread có thể giúp phục vụ nhiều client chậm hơn, nhưng không loại bỏ giới hạn băng thông hoặc khả năng nhận của thiết bị. Cần kiểm tra đồng thời Send Limit Exceeded, kích thước payload, fan-out và network throughput.

### SockJS Task Scheduler

SockJS dùng task scheduler để gửi heartbeat cho các session khi cần. Thống kê của scheduler giúp phát hiện thread pool heartbeat bị quá tải hoặc có nhiều task chờ.

Nếu heartbeat STOMP đã được thương lượng, heartbeat riêng của SockJS sẽ bị tắt. Do đó, khi đọc thống kê scheduler, cần biết ứng dụng đang dùng WebSocket thuần, SockJS fallback hay STOMP heartbeat. Không nên kết luận scheduler lỗi chỉ từ số task thấp hoặc không có heartbeat SockJS.

## 3. Phân biệt thống kê Spring với metrics của hệ thống

**WebSocketMessageBrokerStats** gom số liệu của hạ tầng Spring messaging. Nó không cung cấp toàn bộ bức tranh vận hành.

Cần theo dõi thêm:

| Tầng | Chỉ số cần xem | Vì sao quan trọng |
|---|---|---|
| JVM | CPU, heap/non-heap, GC pause, thread count, direct buffer | Phân biệt nghẽn CPU, memory và thread |
| WebSocket container | Active connections, write errors, message-size errors, buffer usage | Xác định giới hạn của Tomcat/Jetty/Undertow hoặc server đang dùng |
| Reverse proxy / ingress | Active connections, upstream timeout, 4xx/5xx, reset, idle timeout | Phát hiện proxy đóng socket hoặc không chuyển tiếp heartbeat |
| Inbound/outbound executor | Active threads, queue depth, completed tasks, rejected tasks | Xác định channel nào đang nghẽn |
| Database và HTTP client | Pool active/idle, pending acquire, query latency, timeout | Tìm nguyên nhân thread inbound bị chặn |
| Broker ngoài | Connection count, queue depth, unacked messages, publish/delivery rate, memory/disk alarm | Phân biệt app relay nghẽn với broker nghẽn |
| Network | Bytes/s, packet loss, retransmission, RTT, open file descriptors | Xác định giới hạn truyền dữ liệu và tài nguyên kết nối |

Không mặc định rằng mọi số liệu của **WebSocketMessageBrokerStats** đã tự động trở thành Micrometer meter. Bean này có log tổng hợp và có thể xuất JMX. Nếu cần dashboard time-series, hãy bổ sung instrumentation Micrometer phù hợp hoặc thu thập JMX bằng hệ thống giám sát.

Spring Boot Actuator có endpoint **/actuator/metrics** để kiểm tra những meter hiện được đăng ký và giá trị hiện tại. Endpoint này hữu ích cho chẩn đoán thủ công, không nên dùng làm metrics backend hoặc scrape định kỳ trong production. Với Prometheus, dùng registry và endpoint Prometheus tương ứng; bảo vệ các endpoint quản trị và chỉ expose các endpoint cần thiết.

Khi tự tạo meter từ stats, phân biệt rõ:
- **Gauge** cho số session hiện tại, số thread đang active hoặc queue depth.
- **Counter/FunctionCounter** cho tổng session đã tạo, tổng lỗi và các bộ đếm tăng dần.
- **Timer/DistributionSummary** cho latency và kích thước message nếu ứng dụng tự instrument đường xử lý.

Không gắn session ID, user ID hoặc destination có mã định danh riêng vào tag metric. Cardinality quá cao có thể làm hệ thống metrics tốn RAM, CPU và dung lượng lưu trữ. Dùng tag có tập giá trị hữu hạn như transport, channel hoặc nhóm destination đã chuẩn hóa.

## 4. Quy trình chẩn đoán tải kết nối

Một quy trình có thể lặp lại:

1. **Xác định phạm vi**: lỗi xảy ra trên một node hay toàn cluster; chỉ WebSocket hay cả SockJS; chỉ một topic hay mọi destination; bắt đầu từ thời điểm nào.
2. **Chụp baseline**: ghi Current, Total, các bộ đếm abnormal close, STOMP frame, relay connection và inbound/outbound executor khi tải bình thường.
3. **So sánh theo thời gian**: lấy nhiều snapshot trong cùng process uptime. Quan sát delta của Total, Connect Failures, Send Limit Exceeded và Transport Errors; không chỉ nhìn giá trị tuyệt đối.
4. **Tìm channel nghẽn**: queue inbound tăng thì kiểm tra controller, interceptor, database và REST dependency; queue outbound tăng thì kiểm tra slow clients, payload và fan-out.
5. **Đối chiếu broker**: nếu dùng relay, so TCP connection và STOMP frame của Spring với broker log/management metrics.
6. **Đối chiếu hạ tầng**: kiểm tra CPU, GC, memory, file descriptor, network, proxy timeout và giới hạn connection.
7. **Thử nghiệm có kiểm soát**: tăng số client và message rate từng bước, giữ payload, subscription và heartbeat gần với production.
8. **Kiểm tra sau điều chỉnh**: chạy lại cùng workload, so queue depth, error rate, latency, memory và số session ổn định.

Các bộ đếm trong stats thường là tích lũy từ lúc process khởi động. Sau khi restart, giá trị có thể về 0. Vì vậy, khi so sánh theo thời gian, ghi nhận process uptime hoặc đánh dấu thời điểm deploy/restart để không diễn giải nhầm counter reset thành lỗi đã được giải quyết.

### Ví dụ nhận diện từ triệu chứng

| Triệu chứng | Dấu hiệu đi kèm | Hướng điều tra đầu tiên |
|---|---|---|
| Số session hiện tại thấp hơn kỳ vọng | Total tăng nhanh, Connect Failures tăng | Client reconnect, proxy timeout, STOMP CONNECT không tới server |
| CONNECT tăng nhưng CONNECTED thấp | Relay connection thấp hoặc broker log có lỗi | Xác thực, broker availability, heartbeat, lỗi frame |
| Send Limit Exceeded tăng | Outbound queue tăng, mạng client chậm | Slow consumers, payload lớn, fan-out, send timeout/buffer |
| Transport Errors tăng | Proxy reset hoặc container write/read errors | TLS, reverse proxy, network, WebSocket container |
| Inbound queue tăng liên tục | Active threads cao, DB/HTTP pool chờ | Controller blocking, database latency, external API, inbound pool |
| Outbound queue tăng nhưng inbound bình thường | Nhiều subscriber, client chậm, send errors | Outbound pool, băng thông, giảm message rate hoặc payload |
| Relay DISCONNECT thấp hơn nhiều so với CONNECT | Broker chủ động đóng socket | Heartbeat, broker log, connection limit, invalid frame |
| SockJS scheduler queue tăng | Heartbeat trễ hoặc session polling/streaming nhiều | TaskScheduler capacity, transport fallback, heartbeat config |
| CPU cao nhưng queue không tăng rõ | Message converter, serialization, fan-out hoặc GC | CPU profile, payload size, số subscriber trên topic |

Đây là các giả thuyết chẩn đoán, không phải kết luận tự động. Một triệu chứng có thể có nhiều nguyên nhân; luôn đối chiếu thời gian, log và metrics của các tầng liên quan.

## 5. Cấu hình executor inbound và outbound

Spring cấu hình executor cho **clientInboundChannel** và **clientOutboundChannel**. Mặc định cả hai có số thread bằng khoảng hai lần số processor khả dụng. Đây là điểm xuất phát, không phải kích thước tối ưu cho mọi workload.

Ví dụ cấu hình:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration implements WebSocketMessageBrokerConfigurer {

    @Override
    public void configureClientInboundChannel(ChannelRegistration registration) {
        registration.taskExecutor()
                .corePoolSize(8)
                .maxPoolSize(16)
                .queueCapacity(500);
    }

    @Override
    public void configureClientOutboundChannel(ChannelRegistration registration) {
        registration.taskExecutor()
                .corePoolSize(8)
                .maxPoolSize(16)
                .queueCapacity(500);
    }
}
~~~

Các con số chỉ là ví dụ để minh họa cấu hình, không phải khuyến nghị dùng cho mọi server. Hãy benchmark trên phần cứng, message size, số subscriber và tỷ lệ I/O thực tế.

Một điểm dễ nhầm của **ThreadPoolExecutor**: nếu queue có capacity không giới hạn, task thường được đưa vào queue sau khi core threads bận; pool không tăng lên maxPoolSize. Vì vậy, chỉ đặt corePoolSize=8 và maxPoolSize=16 với queue không giới hạn không có nghĩa pool sẽ tự mở rộng tới 16 thread. Queue capacity, core size và max size phải được thiết kế cùng nhau.

Không tăng inbound pool chỉ vì thấy queue có lúc xuất hiện. Nếu nguyên nhân là database connection pool hết kết nối, tăng thread có thể làm nhiều request cùng chờ database hơn. Hãy kiểm tra latency và khả năng phục vụ của dependency trước khi tăng pool.

Outbound pool cũng không nên tăng vô hạn. Nếu client có mạng chậm, thêm thread chỉ làm nhiều lần gửi đồng thời hơn; send buffer và giới hạn timeout vẫn cần để ngăn một client giữ quá nhiều bộ nhớ.

## 6. Giới hạn gửi và buffer cho slow client

Với một client, Spring chỉ dùng một thread tại một thời điểm để gửi. Message bổ sung được buffer trong khi send đang diễn ra. Hai thiết lập quan trọng:

- **sendTimeLimit**: thời gian tối đa cho phép gửi.
- **sendBufferSizeLimit**: dung lượng tối đa được buffer khi gửi tới client.

Ví dụ:

~~~java
@Override
public void configureWebSocketTransport(WebSocketTransportRegistration registration) {
    registration
            .setSendTimeLimit(15 * 1000)
            .setSendBufferSizeLimit(512 * 1024);
}
~~~

Ví dụ trên đặt send timeout 15 giây và buffer 512 KiB. Hãy điều chỉnh theo kích thước message, tần suất broadcast và đặc điểm mạng. Timeout quá thấp có thể đóng nhầm client hợp lệ trên mạng di động; buffer quá lớn có thể làm bộ nhớ tăng mạnh khi nhiều client chậm cùng lúc.

Khi Send Limit Exceeded tăng, không nên chỉ nâng timeout và buffer. Trước tiên xác định:
- Một message có kích thước bao nhiêu?
- Một topic có bao nhiêu subscriber?
- Tần suất publish có vượt tốc độ nhận trung bình của client không?
- Client có xử lý callback đồng bộ quá lâu không?
- Có thể gộp, lấy mẫu, giảm tần suất hoặc chỉ gửi delta thay vì snapshot đầy đủ không?

Đối với dữ liệu realtime, đôi khi bỏ qua các update cũ và chỉ giữ trạng thái mới nhất tốt hơn là buffer một hàng dài message đã lỗi thời. Nếu nghiệp vụ cần mọi event, hãy dùng cơ chế lưu trữ/queue phù hợp thay vì coi WebSocket outbound buffer là hàng đợi bền vững.

## 7. Giới hạn kích thước message và chi phí reassembly

WebSocket container thường có giới hạn kích thước message riêng. STOMP client có thể chia một message lớn thành nhiều WebSocket message nhỏ; Spring phải buffer và ghép lại trước khi xử lý STOMP frame hoàn chỉnh.

Có thể cấu hình giới hạn message STOMP ở Spring:

~~~java
@Override
public void configureWebSocketTransport(WebSocketTransportRegistration registration) {
    registration.setMessageSizeLimit(128 * 1024);
}
~~~

Giới hạn trên là 128 KiB trong ví dụ. Chọn giá trị đủ cho payload hợp lệ nhưng không quá lớn so với memory budget. Một message lớn có thể được chia thành nhiều WebSocket frame, cần buffer/reassembly và làm tăng bộ nhớ cũng như độ trễ. Nếu có nhiều client đồng thời gửi message lớn, tổng bộ nhớ sử dụng có thể tăng đáng kể.

Khi gặp lỗi message size:
- Kiểm tra giới hạn ở Spring, WebSocket container, reverse proxy và client library.
- Xác định kích thước sau serialization, không chỉ kích thước object trước khi chuyển JSON.
- Ưu tiên pagination, payload nhỏ, gửi reference/ID để client lấy dữ liệu lớn qua HTTP khi phù hợp.
- Không tăng mọi giới hạn cùng lúc mà không có test tải và kiểm tra memory.

## 8. Thứ tự message và chi phí hiệu năng

Inbound và outbound channel đều dựa trên executor. Nhiều message của cùng session có thể được xử lý trên các thread khác nhau, nên thứ tự xử lý hoặc gửi tới client có thể khác thứ tự ban đầu.

Nếu nghiệp vụ yêu cầu giữ thứ tự, Spring có các lựa chọn:

~~~java
@Override
public void registerStompEndpoints(StompEndpointRegistry registry) {
    registry.setPreserveReceiveOrder(true);
}

@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setPreservePublishOrder(true);
}
~~~

- **setPreserveReceiveOrder(true)** giữ thứ tự xử lý message nhận từ cùng client session.
- **setPreservePublishOrder(true)** giữ thứ tự publish message gửi tới cùng client session.

Hai thiết lập này có chi phí hiệu năng vì giảm khả năng xử lý song song trong phạm vi session. Chỉ bật khi nghiệp vụ cần thứ tự rõ ràng; không dùng như một biện pháp chung để chữa queue tăng.

Ngay cả khi giữ thứ tự trong một session, điều đó không tự bảo đảm thứ tự toàn cục giữa nhiều user, nhiều node hoặc nhiều producer độc lập. Nếu nghiệp vụ cần ordering theo entity, hãy dùng partition key/sequence number hoặc cơ chế ordering ở tầng broker và ứng dụng phù hợp.

## 9. SockJS, heartbeat và tải kết nối

SockJS có thể dùng WebSocket hoặc fallback sang HTTP streaming/polling. Vì vậy, Current Sessions được chia theo transport. Khi tỷ lệ HTTP streaming/polling tăng bất thường, hãy kiểm tra vì sao WebSocket không được sử dụng: proxy không hỗ trợ Upgrade, TLS/network policy, client browser hoặc cấu hình SockJS.

SockJS task scheduler dùng để gửi heartbeat khi cần. Nếu STOMP heartbeat đã được thương lượng, SockJS heartbeat bị tắt. Cần cấu hình scheduler đủ sức xử lý số session fallback và tần suất heartbeat, nhưng không nên tăng thread chỉ từ số session tổng mà chưa kiểm tra transport thực tế.

Heartbeat có hai vai trò:
- Phát hiện connection chết hoặc mất phản hồi.
- Giữ connection không bị proxy/load balancer coi là idle.

Heartbeat quá dày làm tăng task scheduling và network chatter; quá thưa có thể khiến phát hiện mất kết nối chậm hoặc bị proxy đóng socket trước. Chọn interval dựa trên timeout của reverse proxy, load balancer và broker, rồi kiểm thử trên mạng thực tế.

Với Spring **WebSocketStompClient** dùng làm load generator, mỗi client có thể tạo heartbeat scheduling task. Khi mô phỏng hàng nghìn client từ một máy, heartbeat scheduler của chính load generator có thể trở thành nút nghẽn. Spring gợi ý cân nhắc tắt heartbeat trong bài test tải khi mục tiêu là đo số kết nối từ một máy. Điều này chỉ áp dụng cho thiết kế load test phù hợp; không tắt heartbeat ở production để che giấu vấn đề kết nối.

## 10. Broker relay và khả năng scale nhiều instance

Simple broker tích hợp của Spring giữ subscription trong bộ nhớ và không hỗ trợ triển khai nhiều application instance như một broker phân tán. Nếu nhiều instance chạy độc lập, mỗi instance có thể chỉ biết subscription của client đang kết nối tới chính nó.

Khi dùng full-featured STOMP broker qua **enableStompBrokerRelay(...)**, mỗi application instance kết nối tới broker; message broadcast từ instance này có thể được broker chuyển tới client đang kết nối qua instance khác.

Khi chẩn đoán cluster:
- Ghi nhận Current Sessions và executor stats riêng trên từng instance.
- Tổng hợp số liệu cluster, nhưng không cộng nhầm cumulative counters sau mỗi lần restart.
- Kiểm tra broker relay TCP connection trên từng node.
- Kiểm tra broker connection limit, queue depth, unacked message, memory và disk.
- Xác minh load balancer giữ một WebSocket session trên cùng upstream trong suốt vòng đời kết nối.
- Kiểm tra user registry và cơ chế broadcast user destination nếu ứng dụng gửi message theo user xuyên node.

Broker relay không tự động làm mọi thứ có khả năng scale vô hạn. Broker ngoài vẫn có giới hạn connection, throughput, queue, memory và network. Cần kiểm thử tổng số session trên toàn cluster cùng tốc độ message và fan-out.

## 11. Load test có ý nghĩa

Một bài test chỉ mở nhiều WebSocket connection nhưng không gửi STOMP CONNECT hoặc không subscribe không phản ánh đầy đủ tải của một ứng dụng STOMP. Cần xác định rõ đang đo:

- Khả năng giữ connection đồng thời.
- Tốc độ STOMP CONNECT/CONNECTED.
- Số subscription trên mỗi session.
- SEND messages/second.
- Fan-out tới subscriber.
- Payload size và serialization.
- Heartbeat rate.
- Khả năng reconnect sau khi mạng hoặc broker gián đoạn.

Một kịch bản test thực tế nên:
1. Tăng dần số client theo từng bậc.
2. Cho mỗi client hoàn thành handshake và STOMP CONNECT.
3. Subscribe đúng số destination giống production.
4. Gửi message với payload và tần suất đại diện.
5. Đo latency đầu-cuối, queue inbound/outbound, send limit, transport error và resource usage.
6. Giữ tải ổn định đủ lâu để phát hiện memory leak, queue tăng dần và reconnect churn.
7. Thử client chậm, network latency cao và broker restart riêng biệt.
8. Ghi lại cấu hình server, JVM, container, proxy, broker và load generator để có thể tái lập kết quả.

Khi dùng WebSocketStompClient làm load generator, cần cấp TaskScheduler phù hợp cho STOMP heartbeat nếu muốn đo cả chi phí heartbeat. Nếu tắt heartbeat để tập trung đo số connection, ghi rõ điều kiện này trong kết quả test; không so sánh trực tiếp với production có heartbeat.

Không chỉ nhìn số session tối đa. Một hệ thống giữ được 50.000 socket nhàn rỗi chưa chắc xử lý được cùng số socket khi mỗi client nhận 10 message/giây và mỗi message fan-out tới hàng trăm subscriber.

## 12. Checklist chẩn đoán nhanh

### Khi số kết nối giảm đột ngột
- Xem Current theo transport và theo từng node.
- Xem delta Connect Failures, Send Limit Exceeded và Transport Errors.
- Kiểm tra proxy/ingress timeout, network reset, TLS và broker log.
- So CONNECT với CONNECTED để biết kết nối STOMP có hoàn tất không.

### Khi message gửi vào bị chậm
- Xem inbound executor active threads và queue.
- Đo thời gian controller/service và database/HTTP dependency.
- Kiểm tra message rate, payload size, converter và interceptor.
- Xem database pool có pending acquire hoặc timeout không.

### Khi client nhận message chậm
- Xem outbound executor queue và Send Limit Exceeded.
- Đo fan-out, payload size, network throughput và tốc độ callback của client.
- Giảm message rate hoặc payload nếu phù hợp nghiệp vụ.
- Điều chỉnh send timeout/buffer sau khi đã hiểu memory budget.

### Khi broker relay có lỗi
- So relay TCP connection với client session hiện tại.
- So CONNECT, CONNECTED và DISCONNECT.
- Kiểm tra broker connection limit, heartbeat, authentication và broker availability.
- Đọc broker log cùng timestamp với Spring log.

### Khi SockJS fallback tăng
- Xem số HTTP streaming/polling session.
- Kiểm tra WebSocket Upgrade qua proxy/load balancer.
- Kiểm tra heartbeat scheduler và timeout HTTP transport.
- Xác minh client thực sự cần fallback hay đang bị hạ cấp ngoài ý muốn.

## 13. Giới hạn và cách đọc an toàn

**WebSocketMessageBrokerStats không phải APM đầy đủ.** Nó không cho biết từng user đang gửi bao nhiêu message, destination nào có fan-out lớn nhất, latency p50/p95/p99 của từng controller hay payload nào làm tăng memory. Để có các dữ liệu đó, cần instrumentation ở tầng ứng dụng và broker.

Không kết luận sự cố chỉ từ một snapshot. Một queue ngắn tại một thời điểm có thể là burst bình thường; một counter tăng từ khi process start không nói được lỗi đang xảy ra nhanh hay chậm nếu không có delta theo thời gian. Luôn so sánh cùng cửa sổ thời gian, cùng process uptime và cùng workload.

Khi thay đổi thread pool, queue capacity, send timeout, buffer hoặc message size limit, thay từng nhóm có mục tiêu rõ ràng rồi chạy lại cùng kịch bản tải. Nếu thay tất cả cùng lúc, sẽ khó biết cấu hình nào thực sự cải thiện hoặc gây tác dụng phụ.

## Tài liệu tham khảo

- Spring Framework — Monitoring: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/stats.html
- Spring Framework — WebSocketMessageBrokerStats Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/config/WebSocketMessageBrokerStats.html
- Spring Framework — SubProtocolWebSocketHandler.Stats Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/messaging/SubProtocolWebSocketHandler.Stats.html
- Spring Framework — StompSubProtocolHandler.Stats Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/socket/messaging/StompSubProtocolHandler.Stats.html
- Spring Framework — StompBrokerRelayMessageHandler.Stats Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/simp/stomp/StompBrokerRelayMessageHandler.Stats.html
- Spring Framework — Performance: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/configuration-performance.html
- Spring Framework — Flow of Messages: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html
- Spring Framework — Order of Messages: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/ordered-messages.html
- Spring Framework — STOMP Client: https://docs.spring.io/spring-framework/reference/web/websocket/stomp/client.html
- Spring Boot — Actuator Metrics Endpoint: https://docs.spring.io/spring-boot/api/rest/actuator/metrics.html
