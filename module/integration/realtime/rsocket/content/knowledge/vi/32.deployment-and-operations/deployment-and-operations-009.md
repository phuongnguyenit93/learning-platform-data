# Đặt chính sách phục hồi sau khởi động lại và mất trạng thái phiên

Một kết nối RSocket có thể mang nhiều request và stream trong thời gian dài. Khi transport bị ngắt, ứng dụng có thể muốn tiếp tục các interaction đang chạy mà không phải mở lại từng request. RSocket hỗ trợ Session Resumption cho tình huống này, nhưng cơ chế đó dựa trên trạng thái phiên và các frame đã lưu ở cả hai đầu.

Khởi động lại process hoặc chuyển sang một server instance khác là tình huống khó hơn. Nếu server mất session registry, frame buffer hoặc trạng thái handler, client có thể gửi RESUME nhưng server không còn nhận ra token cũ. Khi đó phải mở một session mới và phục hồi công việc từ trạng thái nghiệp vụ đã lưu, chẳng hạn event offset, cursor hoặc checkpoint.

Chính sách vận hành nên có hai tầng:

- **Resume ở tầng giao thức** khi mất transport và cả hai đầu vẫn giữ đủ trạng thái phiên.
- **Reconnect và replay ở tầng ứng dụng** khi process restart, session hết hạn, frame buffer không còn liên tục hoặc failover tới node không giữ session cũ.

Bài học này trình bày cách chọn chính sách, cấu hình RSocket Java/Spring, lưu checkpoint nghiệp vụ, xử lý dữ liệu có thể được phát lại và kiểm thử sau restart.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt mất transport với mất trạng thái phiên do restart hoặc failover.
- Giải thích SETUP, RESUME, RESUME_OK và resume identification token.
- Mô tả vai trò của frame position và resumable frame store.
- Bật Session Resumption ở cả RSocket client và server.
- Chọn session duration, retry policy, keepalive và giới hạn frame buffer.
- Giải thích vì sao in-memory session state không sống qua process restart.
- Phân biệt frame store với session manager và trạng thái nghiệp vụ.
- Thiết kế reconnect mới với cursor/checkpoint khi RESUME bị từ chối.
- Bảo vệ thao tác retry bằng idempotency key, event ID và durable outbox.
- Xây dựng kiểm thử cho network interruption, process restart, failover và rolling deployment.

## 1. Xác định loại sự cố trước khi chọn cách phục hồi

Không phải mọi lần mất kết nối đều cần tạo session mới. Cần xác định trạng thái nào còn tồn tại sau sự cố.

| Sự cố | Trạng thái giao thức | Hướng phục hồi |
|---|---|---|
| Mất mạng ngắn, hai process vẫn sống | Client và server có thể còn session cùng frame buffer | Thử RSocket Resume |
| Wi-Fi đổi mạng hoặc TCP/WebSocket bị reset | Session có thể còn trong thời hạn resume | Kết nối transport mới rồi gửi RESUME |
| Server process restart | Session registry và frame buffer trong RAM có thể đã mất | Tạo SETUP mới, phục hồi từ checkpoint nghiệp vụ |
| Client process restart | Client mất session, frame buffer và stream handle trong RAM | Tạo SETUP mới, khôi phục subscription từ checkpoint bền vững |
| Failover sang server khác | Node mới có thể không sở hữu session token cũ | Resume chỉ khi state được chia sẻ/khôi phục đầy đủ; nếu không, tạo session mới |
| Hết session duration hoặc frame buffer thiếu đoạn | Không thể tái lập vị trí liên tục | Từ chối resume và bắt đầu lại interaction |
| Rolling deploy thay MIME type hoặc protocol config | Thông số connection cũ có thể không còn tương thích | Kết thúc session cũ và kết nối mới theo hợp đồng mới |

~~~mermaid
flowchart TD
    A[Transport bị ngắt] --> B{Client và server còn giữ session state?}
    B -->|Có| C{Còn đủ frame liên tục trong buffer?}
    C -->|Có| D[Thử RESUME]
    D --> E{Server trả RESUME_OK?}
    E -->|Có| F[Tiếp tục interaction hiện tại]
    E -->|Không| G[REJECTED_RESUME]
    C -->|Không| G
    B -->|Không| G
    G --> H[SETUP mới]
    H --> I[Đọc checkpoint nghiệp vụ]
    I --> J[Mở lại stream/channel từ cursor]
    J --> K[Deduplicate và lưu checkpoint mới]
~~~

Điểm quyết định là trạng thái phiên có còn nguyên vẹn hay không. Việc server mở lại cùng port hoặc cùng DNS không có nghĩa session cũ đã được khôi phục.

## 2. RSocket Resume giữ lại những gì?

RSocket Resumption là khả năng tiếp tục một connection sau khi transport bị mất. Client và server lưu vị trí frame đã gửi/đã nhận và giữ các frame cần thiết để phát lại khi transport mới được thiết lập.

Các thành phần chính:

- **Resume identification token:** token nhận diện connection ban đầu. Client gửi lại token này trong frame RESUME.
- **Implied frame positions:** vị trí tích lũy của các frame có liên quan đến interaction trên connection.
- **Resumable frame store:** lưu các frame chưa được peer xác nhận đã nhận, để có thể phát lại.
- **Session registry/manager:** ánh xạ resume token tới session và trạng thái cần thiết để tiếp tục connection.
- **Resume session duration:** khoảng thời gian server giữ session sau khi transport bị mất.
- **Retry policy:** cách client thử kết nối transport lại trong thời hạn resume.

Một số frame như REQUEST, REQUEST_N, CANCEL, ERROR và PAYLOAD tham gia tính vị trí theo protocol. Khi kết nối mới được mở, client gửi RESUME cùng token và vị trí cuối đã nhận. Server chỉ chấp nhận nếu tìm được session và có đủ frame để tiếp tục luồng dữ liệu không bị đứt đoạn.

~~~mermaid
sequenceDiagram
    participant C as RSocket Client
    participant S as RSocket Server
    C->>S: SETUP (resume enabled + token)
    S-->>C: Connection established
    C->>S: REQUEST_STREAM / PAYLOAD
    S-->>C: PAYLOAD frames
    Note over C,S: Transport bị ngắt, hai bên vẫn giữ session và frame buffer
    C->>S: Mở transport mới
    C->>S: RESUME (token + last received position)
    S-->>C: RESUME_OK (server position)
    Note over C,S: Phát lại frame còn thiếu và tiếp tục stream
~~~

RESUME thay thế SETUP trong lần thiết lập transport mới cho session cũ. Sau khi gửi RESUME, client phải chờ RESUME_OK hoặc ERROR phù hợp trước khi gửi các frame khác trên connection đó.

## 3. Giới hạn của Session Resumption

Protocol nêu rõ Resume là tùy chọn và có tính lạc quan. Hai phía không được giả định rằng mọi lần mất kết nối đều có thể khôi phục.

Resume được thiết kế cho mất connectivity khi trạng thái của hai peer vẫn được duy trì. Nó không mặc định giải quyết việc một process bị kill, server restart hoặc một node bất kỳ nhận request resume.

Các giới hạn quan trọng:

- Cả client và server đều phải bật hỗ trợ Resume.
- Client khởi tạo thao tác RESUME; server có quyền chấp nhận hoặc từ chối.
- Client phải dùng đúng token từ SETUP ban đầu.
- Server phải tìm thấy session tương ứng với token.
- Frame buffer phải còn đủ các frame cần phát lại, liên tục theo vị trí protocol.
- Session phải còn trong thời hạn được giữ.
- Khi nhận REJECTED_RESUME, client không được tiếp tục thử RESUME cho session đó; phải chuyển sang chính sách session mới.
- Resume không bảo đảm transaction nghiệp vụ đã commit hay chưa, và không tự tạo exactly-once delivery.
- Các thông số connection như protocol version, data MIME type và metadata MIME type phải tương thích với session ban đầu.
- Lease state không tự được kế thừa qua transport mới; nếu connection dùng LEASE, responder phải cấp lease lại sau khi resume theo protocol.

Resume là cơ chế tiếp tục luồng frame của connection. Nó không thay thế database transaction, event store, message broker hoặc cơ chế checkpoint nghiệp vụ.

## 4. Phân biệt frame state, session state và application state

Khi lập kế hoạch restart recovery, hãy tách ba lớp trạng thái.

| Lớp trạng thái | Ví dụ dữ liệu | Mục đích | Có thể phục hồi bằng RSocket Resume? |
|---|---|---|---|
| Protocol/frame state | Resume token, frame position, frame buffer, stream ID, demand | Tiếp tục connection và phát lại frame | Có, nếu cả hai phía còn đủ state |
| Session/connection state | Principal, SETUP metadata, acceptor context, session registry, connection ownership | Xác định session cũ và khôi phục handler | Phải được implementation giữ lại hoặc khôi phục |
| Application/business state | Subscription ID, last committed offset, order state, idempotency key, event cursor | Tiếp tục nghiệp vụ sau reconnect | Không tự động; ứng dụng phải lưu và khôi phục |

Một frame store bền vững không tự động khôi phục session manager. Nếu token không còn ánh xạ tới session, server có thể trả RejectedResumeException: unknown resume token dù frame bytes vẫn còn trong Redis.

Với rsocket-java, package io.rsocket.resume cung cấp ResumableFramesStore và InMemoryResumableFramesStore. Store này quản lý frame và vị trí của chúng. Nó không tự thay thế việc khôi phục session registry, SETUP context, responder hoặc trạng thái nghiệp vụ.

Một issue của rsocket-java được mở tháng 1/2025 ghi nhận trường hợp dùng persistent ResumableFramesStore nhưng sau khi kill/restart server vẫn gặp unknown resume token do session manager không được lưu/khôi phục. Vì vậy, khi thiết kế HA, cần xác minh chính xác phiên bản thư viện và khả năng mở rộng session manager; không suy ra rằng chỉ thay frame store bằng Redis là đã hỗ trợ restart resume.

## 5. Bật Resume ở rsocket-java

Trong rsocket-java, RSocketServer.resume(Resume) bật Resume cho server. Client dùng RSocketConnector.resume(Resume). Mặc định tính năng này không được bật.

Ví dụ server:

~~~java
import io.rsocket.core.Resume;
import io.rsocket.core.RSocketServer;
import io.rsocket.transport.netty.server.TcpServerTransport;

import java.time.Duration;

Resume serverResume = new Resume()
        .sessionDuration(Duration.ofMinutes(2));

var server = RSocketServer.create(socketAcceptor)
        .resume(serverResume)
        .bind(TcpServerTransport.create("0.0.0.0", 7000))
        .block();
~~~

socketAcceptor là SocketAcceptor đã được cấu hình để xử lý các request của ứng dụng. Ví dụ trên bật Resume và giữ session trong hai phút sau khi transport bị mất. Thời gian này phải được chọn dựa trên outage dự kiến và ngân sách bộ nhớ cho các frame được giữ lại.

Ví dụ client:

~~~java
import io.rsocket.core.Resume;
import io.rsocket.core.RSocketConnector;
import io.rsocket.transport.netty.client.TcpClientTransport;
import reactor.util.retry.Retry;

import java.time.Duration;

Resume clientResume = new Resume()
        .sessionDuration(Duration.ofMinutes(2))
        .retry(Retry.fixedDelay(
                10,
                Duration.ofSeconds(1)));

var rsocketMono = RSocketConnector.create()
        .keepAlive(
                Duration.ofSeconds(20),
                Duration.ofSeconds(90))
        .resume(clientResume)
        .connect(TcpClientTransport.create(
                "rsocket.internal", 7000));
~~~

Trong ví dụ, client thử nối lại transport theo retry policy đã cấu hình. Số lần retry và khoảng delay phải nằm trong thời hạn session mà server còn giữ. Với môi trường mạng không ổn định, có thể dùng backoff và jitter để tránh nhiều client đồng loạt reconnect.

Không cấu hình đồng thời resume(...) và reconnect(...) trên cùng connector. Hai chế độ này loại trừ nhau:

- resume(...) cố tiếp tục session và các interaction đang chạy.
- reconnect(...) tạo một RSocket connection mới khi cần; ứng dụng phải quyết định request nào cần retry và subscription nào phải mở lại.

Dùng reconnect khi server không hỗ trợ Resume hoặc khi ứng dụng chủ động muốn tạo session mới.

## 6. Cấu hình Resume qua Spring

Spring RSocketRequester.Builder cho phép truy cập RSocketConnector qua callback rsocketConnector(...). Có thể cấu hình Resume ở đó:

~~~java
import io.rsocket.core.Resume;
import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.util.retry.Retry;

import java.time.Duration;

Resume clientResume = new Resume()
        .sessionDuration(Duration.ofMinutes(2))
        .retry(Retry.fixedDelay(10, Duration.ofSeconds(1)));

RSocketRequester requester = RSocketRequester.builder()
        .rsocketConnector(connector -> connector
                .keepAlive(
                        Duration.ofSeconds(20),
                        Duration.ofSeconds(90))
                .resume(clientResume))
        .tcp("rsocket.internal", 7000);
~~~

Ở phía Spring Boot server, có thể gắn cấu hình Resume vào RSocket server được auto-configure bằng RSocketServerCustomizer:

~~~java
import io.rsocket.core.Resume;
import org.springframework.boot.rsocket.server.RSocketServerCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.time.Duration;

@Configuration
public class RSocketResumeConfiguration {

    @Bean
    RSocketServerCustomizer resumeServer() {
        return server -> server.resume(
                new Resume().sessionDuration(Duration.ofMinutes(2)));
    }
}
~~~

Các ví dụ này cấu hình tính năng Resume cho kết nối đang sống qua sự cố transport. Chúng chưa tạo persistent session manager hoặc khôi phục session sau khi JVM/server process restart.

## 7. Chọn session duration và retry policy

sessionDuration quyết định thời gian server giữ session để client có thể thử Resume sau khi mất transport. Nếu duration quá ngắn, client chưa kịp reconnect đã mất session. Nếu duration quá dài, server giữ nhiều session và frame buffer trong thời gian dài, làm tăng bộ nhớ và tài nguyên.

| Tham số/chính sách | Cần cân nhắc | Hệ quả nếu cấu hình sai |
|---|---|---|
| Session duration | Outage tối đa cần hỗ trợ, retry delay và thời gian phát hiện lỗi | Session hết hạn trước khi client reconnect |
| Client retry | Số lần thử, backoff, jitter, lỗi có thể retry | Retry quá lâu hoặc tạo retry storm |
| Keepalive interval | Thời gian phát hiện peer mất kết nối | Phát hiện quá chậm hoặc false positive |
| Keepalive max lifetime | Cho phép bỏ lỡ bao nhiêu heartbeat | Đóng connection quá sớm hoặc giữ connection chết |
| Frame store capacity | Lưu lượng frame trong cửa sổ outage | Buffer đầy hoặc mất frame cần phát lại |
| Session cleanup | TTL, cleanup khi session kết thúc, giới hạn session | Rò rỉ session hoặc chiếm bộ nhớ quá lâu |

Một quy trình chọn giá trị:

1. Đo thời gian phát hiện transport lỗi ở client.
2. Ước lượng thời gian reconnect ở môi trường triển khai thật.
3. Chọn retry window nhỏ hơn session duration, chừa khoảng cho jitter và xử lý handshake.
4. Ước lượng lượng frame phát sinh trong outage window.
5. Đặt giới hạn bộ nhớ cho mỗi session và toàn bộ node.
6. Kiểm thử khi buffer đầy hoặc outage dài hơn session duration.

Không chọn session duration chỉ dựa trên thời gian retry trung bình. Hãy dùng percentile của thời gian phục hồi và kiểm tra cả khi nhiều client mất mạng đồng thời.

## 8. Frame buffer và giới hạn khả năng resume

ResumableFramesStore lưu các frame cần thiết để có thể phát lại và theo dõi vị trí frame. Interface cung cấp các thao tác như:

- saveFrames(...): lưu các frame được gửi.
- resumeStream(): đọc các frame từ vị trí lưu trữ để phát lại.
- releaseFrames(...): giải phóng frame mà peer đã xác nhận.
- framePosition() và frameImpliedPosition(): theo dõi vị trí cục bộ.
- resumableFrameReceived(...): cập nhật vị trí khi nhận frame liên quan.

Frame store phải giữ được dãy frame liên tục từ vị trí mà peer cần. Nếu thiếu một đoạn, server không thể tự đoán nội dung còn thiếu và phải từ chối Resume.

### Ước lượng dung lượng

Dung lượng cần giữ phụ thuộc tốc độ gửi frame, kích thước frame và thời gian peer có thể mất kết nối.

Có thể ước lượng sơ bộ:

~~~text
bufferBytesPerSession
    ~= averageOutboundBytesPerSecond
       * maximumExpectedDisconnectSeconds
       + safetyMargin
~~~

Tổng ngân sách bộ nhớ:

~~~text
totalResumeBuffer
    ~= activeResumableSessions
       * bufferBytesPerSession
~~~

Đây là ước lượng để lập ngân sách, không phải công thức sizing cuối cùng. Cần đo frame rate, payload size, keepalive trimming, overhead của store và số session thực tế. Nếu dùng in-memory store, giới hạn phải phù hợp với heap và direct memory của process.

### In-memory và persistent store

| Loại store | Ưu điểm | Giới hạn |
|---|---|---|
| In-memory | Độ trễ thấp, dễ triển khai, phù hợp network interruption khi process còn sống | Mất dữ liệu khi process restart hoặc node bị kill |
| Persistent frame store | Có thể giữ frame qua một số sự cố process nếu storage hoạt động | Chưa đủ nếu session manager và trạng thái phục hồi không được lưu |
| Distributed store | Có thể chia sẻ dữ liệu giữa node | Cần đồng bộ vị trí, thứ tự frame, ownership, atomic update và cleanup |

Không ghi frame buffer vào Redis hoặc database mà không có thiết kế serialization, thứ tự, tính liên tục và atomicity. Frame của RSocket Java có thể sử dụng Netty ByteBuf; implementation custom phải quản lý reference counting, sao chép/giải phóng buffer đúng cách và bảo đảm thứ tự ghi.

## 9. Vì sao restart thường phải tạo session mới?

Giả sử server đang chạy với session A:

1. Client và server trao đổi frame.
2. Server lưu frame cần phát lại trong RAM.
3. Session manager ánh xạ token T-A tới session A.
4. JVM bị kill.
5. Server khởi động lại và tạo session manager mới.
6. Client reconnect bằng token T-A.
7. Server không tìm thấy token hoặc frame state tương ứng và trả REJECTED_RESUME.

Ngay cả khi frame store đã nằm trong Redis, server vẫn cần biết token đó thuộc session nào, trạng thái stream/handler nào cần khôi phục và các frame position nào đang có hiệu lực. Nếu thiếu một trong các phần đó, Resume không thể tiếp tục session cũ.

Với rsocket-java, InMemoryResumableFramesStore là implementation lưu frame trong bộ nhớ. Một persistent ResumableFramesStore có thể là một phần của giải pháp, nhưng cần kiểm tra thêm khả năng persist/restore session manager ở đúng phiên bản thư viện. Issue #1116 của rsocket-java cho thấy việc chỉ thay frame store bằng Redis có thể vẫn gặp unknown resume token sau khi restart.

Chính sách an toàn cho ứng dụng thông thường:

- Dùng Resume cho sự cố transport trong khi process vẫn giữ session.
- Sau restart hoặc REJECTED_RESUME, tạo SETUP mới.
- Xác thực lại principal và khôi phục subscription từ checkpoint nghiệp vụ.
- Dùng event ID/idempotency key để xử lý an toàn dữ liệu có thể được gửi lại.

## 10. Thiết kế checkpoint nghiệp vụ

Checkpoint là vị trí cuối cùng mà ứng dụng đã xử lý và lưu bền vững. Với event stream, checkpoint thường là sequence number, offset hoặc cursor.

Ví dụ client nhận event đơn hàng:

~~~java
public Flux<OrderEvent> consumeOrderEvents() {
    return checkpointStore.load("order-events")
            .flatMapMany(lastCommitted ->
                    requester.route("orders.events")
                            .data(new EventQuery(lastCommitted))
                            .retrieveFlux(OrderEvent.class))
            .concatMap(event ->
                    orderProcessor.processIdempotently(event)
                            .then(checkpointStore.save(
                                    "order-events", event.sequence()))
                            .thenReturn(event));
}
~~~

checkpointStore, orderProcessor và OrderEvent là thành phần do ứng dụng định nghĩa. Ví dụ thể hiện thứ tự quan trọng:

1. Đọc checkpoint đã lưu.
2. Mở stream từ vị trí sau checkpoint đó theo hợp đồng của API.
3. Xử lý event.
4. Lưu checkpoint sau khi xử lý bền vững thành công.
5. Chỉ sau đó mới tiếp tục event kế tiếp.

Nếu chỉ lưu checkpoint khi event vừa được nhận qua socket, nhưng chưa commit xử lý nghiệp vụ, restart có thể làm mất event. Nếu xử lý đã commit nhưng checkpoint chưa kịp lưu, event có thể được gửi lại. Vì vậy handler cần idempotent hoặc deduplicate.

### Server đọc lại từ nguồn bền vững

Server nên phục vụ stream từ event log, database có thứ tự hoặc message broker có offset. Ví dụ:

~~~java
@MessageMapping("orders.events")
public Flux<OrderEvent> events(@Payload EventQuery query) {
    return eventStore.readAfter(query.lastCommittedSequence());
}
~~~

readAfter(...) phải có semantics rõ ràng: trả event có sequence lớn hơn checkpoint, giữ thứ tự ổn định và cho phép client tiếp tục sau reconnect. Nếu dữ liệu không có nguồn lưu bền vững, ứng dụng không thể khôi phục event đã bị mất khi process restart.

## 11. Chống trùng lặp và xử lý side effect

Resume có thể phát lại các frame chưa được peer xác nhận. Reconnect mới cũng có thể đọc lại event từ checkpoint gần nhất. Ứng dụng cần xử lý khả năng một message được nhìn thấy nhiều lần.

Các mẫu thường dùng:

- Event có ID ổn định, ví dụ eventId hoặc commandId.
- Database có unique constraint trên idempotency key.
- Consumer lưu event ID đã xử lý trong cùng transaction với side effect.
- Producer dùng transactional outbox để phát event sau khi commit dữ liệu nghiệp vụ.
- Client chỉ cập nhật checkpoint sau khi commit xử lý.
- Với request-response có side effect, client gửi idempotency key ổn định qua mọi lần retry.

Ví dụ bảng idempotency:

~~~sql
CREATE TABLE processed_command (
    command_id VARCHAR(100) PRIMARY KEY,
    processed_at TIMESTAMP NOT NULL
);
~~~

Transaction xử lý command có thể thực hiện:

1. Insert command_id vào bảng.
2. Nếu key đã tồn tại, trả kết quả đã xử lý hoặc bỏ qua duplicate.
3. Nếu insert thành công, cập nhật dữ liệu nghiệp vụ.
4. Commit cả marker và side effect trong cùng transaction.

Đây là cách đạt hành vi xử lý lặp an toàn ở tầng ứng dụng. RSocket Resume tự nó không cung cấp exactly-once transaction cho database.

### Fire-and-forget cần chú ý đặc biệt

Fire-and-forget không có response nghiệp vụ để client xác nhận server đã commit hay chưa. Nếu transport mất ngay sau khi gửi, client có thể không biết command đã được xử lý hay chưa.

Với lệnh có side effect, hãy gửi commandId/idempotency key và thiết kế consumer deduplicate. Nếu cần xác nhận xử lý, cân nhắc request-response hoặc một acknowledgement/event riêng thay vì chỉ dựa vào việc Mono<Void> hoàn tất ở client.

## 12. Phục hồi request-stream và request-channel sau khi tạo session mới

Khi Resume thành công, interaction đang chạy có thể tiếp tục theo frame state được giữ. Khi phải tạo session mới, ứng dụng cần mở interaction mới.

### Request-stream

Client gửi cursor cuối cùng đã commit:

~~~java
Mono<Long> checkpoint = checkpointStore.load("telemetry");

Flux<TelemetryEvent> stream =
        checkpoint.flatMapMany(sequence ->
                requester.route("telemetry.stream")
                        .data(new TelemetryQuery(sequence))
                        .retrieveFlux(TelemetryEvent.class));
~~~

Server đọc dữ liệu sau sequence đó. Nếu stream dài hạn, nên có heartbeat nghiệp vụ, cursor rõ ràng và chính sách khi cursor đã quá cũ so với retention của event store.

### Request-channel

Channel hai chiều cần checkpoint cho cả hai hướng:

- Sequence cuối client đã gửi và server đã commit.
- Sequence cuối server đã gửi và client đã commit.

Khi mở channel mới, hai bên dùng các cursor đó để tiếp tục. Không chỉ dùng số lượng payload đã gửi qua socket làm checkpoint nghiệp vụ, vì payload có thể đã đến transport nhưng chưa được xử lý/commit.

Mỗi command gửi lên channel cần ID ổn định để server deduplicate nếu client không chắc lần gửi trước đã được xử lý hay chưa.

## 13. Reconnect và fallback sau REJECTED_RESUME

Một client production nên có state machine rõ ràng:

~~~mermaid
stateDiagram-v2
    [*] --> CONNECTED
    CONNECTED --> TRANSPORT_LOST: keepalive timeout / transport close
    TRANSPORT_LOST --> RESUMING: mở transport mới và gửi RESUME
    RESUMING --> CONNECTED: RESUME_OK
    RESUMING --> SESSION_REJECTED: REJECTED_RESUME
    RESUMING --> RESUMING: lỗi transport tạm thời, còn trong retry window
    SESSION_REJECTED --> NEW_SETUP: dừng retry Resume
    NEW_SETUP --> RESTORING: SETUP thành công
    RESTORING --> CONNECTED: load checkpoint và mở interaction mới
    RESTORING --> FAILED: không khôi phục được application state
    FAILED --> [*]
~~~

Khi server trả REJECTED_RESUME, client phải dừng thử Resume cho session cũ. Sau đó:

1. Ghi nhận lý do session không thể resume.
2. Kết thúc/giải phóng state của RSocket session cũ.
3. Tạo một connection mới bằng SETUP.
4. Xác thực lại principal và gửi metadata cần thiết.
5. Tải checkpoint hoặc subscription state từ storage bền vững.
6. Mở lại request-stream/channel theo cursor.
7. Áp dụng idempotency/deduplication cho các event có thể được phát lại.

Không retry vô hạn một token đã bị server từ chối. Việc đó chỉ tạo kết nối lỗi lặp lại và có thể che mất nguyên nhân thật.

## 14. Sticky routing và failover nhiều node

Nếu session state nằm trong RAM của node A, mọi RESUME cho session đó phải được chuyển về node A. Một load balancer phân phối ngẫu nhiên RESUME sang node B thường dẫn đến unknown resume token.

Các lựa chọn triển khai:

| Chiến lược | Cách hoạt động | Giới hạn |
|---|---|---|
| Sticky/session affinity | Token hoặc client ID được route về node sở hữu session | Không cứu được session khi node owner bị kill |
| Một owner node cho mỗi session | Registry giữ mapping token → node | Cần xử lý node mất và stale ownership |
| Shared frame store + shared session manager | Các node có thể khôi phục session từ state chung | Đòi hỏi hỗ trợ đầy đủ từ implementation, đồng bộ và fencing |
| Application reconnect | Node mới tạo session mới, đọc lại event từ checkpoint | Stream được tạo lại; cần replay và deduplicate |

Nếu dùng sticky routing, token cần được coi là opaque; không tự giải mã token để suy ra node nếu implementation không định nghĩa format đó. Có thể dùng một routing key riêng do ứng dụng quản lý.

Với active-active, cần tránh hai node cùng sở hữu một session token. Dùng lease/lock hoặc fencing token ở session registry để ngăn hai owner cùng phát frame cho một session. Nếu phiên bản thư viện không cung cấp cơ chế persistent session manager phù hợp, chọn application reconnect thay vì giả định có thể Resume xuyên node.

## 15. Rolling deployment và thay đổi hợp đồng

Resume dựa trên cấu hình của connection ban đầu. Khi deploy phiên bản mới, cần kiểm tra:

- Protocol version có tương thích không?
- Data MIME type và metadata MIME type có giữ nguyên không?
- Codec có còn giải mã được frame cũ không?
- Route và schema có còn tương thích không?
- Authentication/setup metadata có còn được chấp nhận không?
- Node mới có nhận diện session token và state cũ không?

Không đổi MIME type, data encoding hoặc protocol assumptions giữa một session đang resume. Nếu thay đổi hợp đồng không tương thích, hãy chủ động đóng session cũ và yêu cầu client mở SETUP mới theo version mới.

Một chiến lược triển khai:

1. Duy trì khả năng đọc schema cũ trong thời gian rolling.
2. Ngừng cấp connection mới cho node chuẩn bị thay thế.
3. Drain stream hoặc phát tín hiệu ứng dụng để client lưu checkpoint.
4. Cho các interaction hoàn tất trong grace period.
5. Đóng session cũ và restart node.
6. Client tạo session mới và tiếp tục từ checkpoint.
7. Loại bỏ schema cũ sau khi hết thời gian tương thích.

Với rolling deploy, full reconnect có kiểm soát thường dễ dự đoán hơn cố Resume session qua hai phiên bản server khác nhau.

### Trình tự chuẩn bị một lần restart có kiểm soát

Nếu ứng dụng biết trước thời điểm restart, hãy tạo cơ hội để client lưu checkpoint trước khi process dừng:

1. Đánh dấu node không nhận connection mới và cập nhật readiness/service discovery.
2. Gửi tín hiệu bảo trì ở tầng ứng dụng tới các session đang hoạt động.
3. Client hoàn tất hoặc hủy interaction tại checkpoint, rồi lưu cursor đã commit.
4. Server chờ request-response và channel batch đang xử lý hoàn tất trong grace period.
5. Đóng connection và dừng process.
6. Sau khi restart, client mở SETUP mới và đọc lại từ checkpoint.

Nếu hệ thống có session manager và frame store bền vững đã được kiểm chứng cho đúng phiên bản, có thể thiết kế một đường Resume sau restart. Tuy nhiên, vẫn phải khôi phục được session ownership, setup context, responder state và frame position. Nếu thiếu một thành phần, dùng quy trình SETUP mới ở trên.

## 16. Bảo vệ resume token và session state

Resume token nhận diện một connection đang hoạt động. Cần coi token là dữ liệu nhạy cảm:

- Token phải duy nhất và khó đoán.
- Không ghi token vào log, metric label hoặc URL.
- Giới hạn token theo lifetime của session.
- Ràng buộc session với principal/tenant đã xác thực.
- Kiểm tra quyền và trạng thái tài khoản trước khi tiếp tục session theo policy bảo mật.
- Dùng TLS để bảo vệ token và frame trên transport.
- Xóa session và frame store khi logout, revoke hoặc hết thời hạn.
- Không tái sử dụng token cũ cho một SETUP mới.

Nếu token bị lộ, kẻ khác có thể thử chiếm hoặc resume connection tương ứng. Session registry cần có kiểm soát quyền sở hữu và chống replay.

## 17. Theo dõi và cảnh báo phục hồi

Nên đo cả kết quả Resume và fallback ở tầng ứng dụng.

| Metric | Ý nghĩa |
|---|---|
| rsocket_resume_attempt_total | Tổng số lần client thử Resume |
| rsocket_resume_success_total | Số session được RESUME_OK |
| rsocket_resume_rejected_total | Số session bị REJECTED_RESUME |
| rsocket_resume_duration_seconds | Thời gian từ transport loss tới resume thành công |
| rsocket_resume_sessions_active | Số session đang được giữ |
| rsocket_resume_buffer_bytes | Bộ nhớ frame buffer đang sử dụng |
| rsocket_resume_buffer_overflow_total | Số lần buffer không giữ đủ frame |
| rsocket_full_reconnect_total | Số lần phải tạo SETUP mới |
| application_replay_events_total | Số event được đọc lại từ checkpoint |
| application_duplicate_events_total | Số event/command bị deduplicate |
| application_checkpoint_lag | Khoảng cách giữa event mới nhất và checkpoint đã commit |

Log nên có connection/session ID đã được hash, node ID, principal ID không nhạy cảm, resume outcome và lý do từ chối. Không log raw resume token hoặc payload chứa dữ liệu nhạy cảm.

Các cảnh báo hữu ích:

- Tỷ lệ REJECTED_RESUME tăng đột biến sau deploy.
- Nhiều session hết hạn trước khi client reconnect.
- Frame buffer tăng nhanh hoặc thường xuyên đầy.
- Client reconnect liên tục và tạo retry storm.
- Checkpoint lag tăng sau khi server restart.
- Duplicate command tăng bất thường.

## 18. Kiểm thử chính sách sau mất kết nối và restart

Kiểm thử phải bao gồm cả Resume thành công lẫn fallback. Không chỉ test bằng cách ngắt mạng trong khi hai process vẫn sống.

| Ca kiểm thử | Thao tác | Kết quả mong đợi |
|---|---|---|
| Network interruption ngắn | Ngắt TCP/WebSocket rồi khôi phục trong session duration | RESUME_OK, stream tiếp tục |
| Mất mạng lâu hơn session duration | Giữ client offline tới khi session hết hạn | REJECTED_RESUME, tạo SETUP mới |
| Server restart với in-memory store | Kill process rồi khởi động lại | Resume cũ bị từ chối; client khôi phục từ checkpoint |
| Client process restart | Khởi động client mới không còn protocol state cũ | SETUP mới, đọc checkpoint bền vững |
| Failover sang node khác | Route RESUME tới node không sở hữu session | Resume bị từ chối hoặc routing chuyển đúng owner |
| Persistent frame store nhưng session registry mất | Khởi động lại session manager | Kiểm tra lỗi unknown resume token |
| Frame buffer thiếu đoạn | Làm buffer vượt capacity hoặc xóa frame | Resume bị từ chối, application replay |
| Response mất sau commit | Ngắt kết nối ở khoảng thời gian sau commit | Retry không tạo side effect trùng |
| Request-channel hai chiều | Ngắt kết nối khi cả hai hướng đang phát | Resume hoặc tạo channel mới từ hai checkpoint |
| Rolling deploy đổi MIME/schema | Deploy node không tương thích session cũ | Session cũ kết thúc; SETUP mới theo version |
| Logout/revoke | Thu hồi principal rồi thử resume token cũ | Server từ chối theo security policy |
| Retry storm | Ngắt đồng thời nhiều client | Backoff/jitter giới hạn tải reconnect |

Trong test restart, hãy xác minh cả database/event store và session store. Test thành công khi stream tiếp tục không có gap hoặc duplicate theo hợp đồng nghiệp vụ, không chỉ khi TCP socket được mở lại.

## 19. Checklist chính sách vận hành

- [ ] Phân biệt network interruption, process restart và node failover.
- [ ] Resume được bật ở cả client và server nếu cần tiếp tục interaction cũ.
- [ ] Session duration và retry window được chọn theo outage budget.
- [ ] Keepalive phù hợp với transport và môi trường triển khai.
- [ ] Frame store có giới hạn capacity, TTL và metric.
- [ ] Session manager và frame store được đánh giá riêng.
- [ ] Không giả định in-memory store sống qua restart.
- [ ] Client lưu checkpoint nghiệp vụ bền vững.
- [ ] Server có nguồn event/log đủ retention để replay từ cursor.
- [ ] Side effect có idempotency key hoặc deduplication.
- [ ] Fire-and-forget có event ID và chính sách xử lý khi không rõ kết quả.
- [ ] Client dừng Resume khi nhận REJECTED_RESUME và chuyển sang SETUP mới.
- [ ] Multi-node có sticky routing hoặc application reconnect rõ ràng.
- [ ] Rolling deployment giữ tương thích schema hoặc chủ động tạo session mới.
- [ ] Resume token không bị log và được ràng buộc với principal.
- [ ] Có integration test cho network loss, restart, failover và duplicate event.

## Kết luận

RSocket Resume giúp tiếp tục connection khi transport bị mất và hai peer vẫn giữ đủ session state cùng frame buffer. Nó không tự khôi phục trạng thái đã mất khi JVM restart hoặc khi RESUME được route tới node không sở hữu session. Với restart/failover, ứng dụng cần chuẩn bị đường lui: tạo SETUP mới, tải checkpoint từ storage bền vững, mở lại stream/channel từ cursor và xử lý lặp bằng idempotency key. Chính sách tốt kết hợp Resume cho sự cố mạng ngắn với application-level replay cho các tình huống mất session state, đồng thời đo lường rõ số lần resume thành công, bị từ chối và phải tạo session mới.

## Tài liệu tham khảo

- [RSocket Protocol – Resuming Operation](https://rsocket.io/about/protocol/)
- [RSocket Java 1.1.5 – RSocketServer](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketServer.html)
- [RSocket Java 1.1.5 – RSocketConnector](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/core/RSocketConnector.html)
- [RSocket Java 1.1.5 – Resume Package](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/resume/package-summary.html)
- [RSocket Java 1.1.5 – ResumableFramesStore](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/resume/ResumableFramesStore.html)
- [RSocket Java 1.1.5 – InMemoryResumableFramesStore](https://javadoc.io/static/io.rsocket/rsocket-core/1.1.5/io/rsocket/resume/InMemoryResumableFramesStore.html)
- [Spring Framework Reference – RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [rsocket-java Issue #1116 – Persistent frame store and unknown resume token after restart](https://github.com/rsocket/rsocket-java/issues/1116)
- [rsocket-java Issue #766 – Resume mechanism and session recreation](https://github.com/rsocket/rsocket-java/issues/766)
