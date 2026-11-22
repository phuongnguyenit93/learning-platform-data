# Không giữ stream mở vô hạn để chờ broker

Một messaging bridge có thể nhận lệnh qua gRPC, chuyển lệnh tới broker, rồi chờ kết quả hoặc đẩy event trở lại client. Nếu mỗi request mở một gRPC stream và giữ stream đó vô hạn chỉ để đợi broker có message, số phiên chờ sẽ tăng theo số caller. Các stream nhàn rỗi vẫn giữ state, queue, deadline, transport và tài nguyên theo dõi; proxy hoặc quá trình deploy cũng có thể đóng chúng bất ngờ.

**Không giữ stream mở vô hạn để chờ broker** là nguyên tắc tách vòng đời của broker consumer khỏi vòng đời của một gRPC RPC, đồng thời giới hạn thời gian chờ, số phiên và lượng dữ liệu chờ gửi. Bài thuộc chương **Messaging bridge** của mô-đun **SPRING_GRPC**: phát triển dịch vụ gRPC trong hệ sinh thái Spring bằng hợp đồng Protocol Buffers, sinh mã Java và triển khai client/server cho unary hoặc streaming RPC; người học xử lý metadata, deadline, status, interceptor, TLS, kiểm thử tích hợp và giám sát hiệu năng, độ tin cậy. Trọng tâm là chọn mô hình request/response, long polling hoặc subscription có lease; áp dụng deadline, flow control, bounded queue, cursor/acknowledgement và cleanup khi client rời đi.

## 1. Vì sao stream chờ vô hạn là rủi ro?

Một gRPC stream không phải là một thread luôn bị block, nhưng nó vẫn có lifecycle và tài nguyên cần quản lý:

- Server giữ call state, listener, context, callback và tham chiếu tới session.
- Client giữ stream observer, retry/reconnect state và logic xử lý response.
- Ứng dụng có thể giữ queue, correlation state, subscription hoặc broker delivery state cho từng caller.
- HTTP/2 connection có thể multiplex nhiều stream, nhưng mỗi stream vẫn chiếm một phần tài nguyên và quota.
- Proxy, ingress, load balancer hoặc service mesh có thể có idle timeout hay maximum stream duration riêng.
- Rolling deployment, network interruption và broker rebalance có thể kết thúc stream ở thời điểm bất kỳ.

Nếu một client mở stream để chờ event trong nhiều giờ, service phải quản lý disconnect, reconnect, queue overflow, duplicate delivery, graceful shutdown và cursor phục hồi. Nếu không có các cơ chế đó, stream vẫn mở không đồng nghĩa với bridge đáng tin cậy.

Keepalive cũng không giải quyết vấn đề này. HTTP/2 keepalive PING kiểm tra connection ở tầng transport; nó không chứng minh broker có message, consumer đang tiến triển hoặc application client còn xử lý event. Một connection khỏe vẫn có thể chứa stream chờ vô hạn và không có tiến triển nghiệp vụ.

## 2. Tách vòng đời broker consumer khỏi gRPC RPC

Broker consumer nên được quản lý như một thành phần nền của service, theo consumer group/subscription và lifecycle của ứng dụng. Một gRPC RPC chỉ nên đăng ký nhu cầu nhận dữ liệu hoặc chờ kết quả trong một khoảng thời gian được giới hạn.

~~~mermaid
flowchart LR
    B[Message broker] --> C[Background consumer]
    C --> H[Bridge event hub]
    H --> Q[Bounded session queues]
    Q --> G[gRPC streaming sessions]
    G --> A[Clients]
    A -->|ack/cursor| H
~~~

Mô hình này tách các thành phần:

- **Broker consumer:** đọc message độc lập với số lượng gRPC client đang kết nối.
- **Event hub:** định tuyến event theo subscription, correlation ID hoặc topic đã được cho phép.
- **Session queue:** giữ lượng event hữu hạn cho từng gRPC subscriber.
- **gRPC session:** có thời hạn, giới hạn queue, trạng thái cancellation và quy tắc reconnect.
- **Client:** xử lý event, lưu cursor/acknowledgement và mở session mới khi cần.

Không nên tạo một broker consumer mới cho mỗi gRPC stream nếu mục tiêu là chia sẻ một consumer group hoặc fan-out event. Cách đó có thể làm số consumer tăng theo số client và gây rebalance, tranh chấp partition hoặc duplicate processing. Chỉ tạo consumer riêng khi isolation và semantics của broker thực sự yêu cầu.

Phải phân biệt consumer group load balancing với pub/sub fan-out. Nhiều consumer trong cùng một group thường chia nhau message/partition; chúng không mặc nhiên nhận bản sao của mọi message. Nếu mọi gRPC subscriber đều phải thấy cùng event, bridge cần cơ chế fan-out rõ ràng: mỗi subscription group có offset riêng, một consumer nền phát vào pub/sub nội bộ, hoặc một event store dùng chung để mỗi session đọc theo cursor. Khi chạy nhiều replica, một event hub chỉ nằm trong RAM của một instance không tự chuyển event tới subscriber đang kết nối instance khác.

## 3. Chọn pattern phù hợp thay vì chờ vô hạn

| Pattern | Cách hoạt động | Phù hợp khi |
| --- | --- | --- |
| Request/response bất đồng bộ | RPC nhận command, trả operation ID; client truy vấn trạng thái hoặc nhận notification sau. | Tác vụ broker có thể mất nhiều giây/phút và caller không cần giữ RPC mở. |
| Bounded long polling | RPC đợi tối đa một khoảng ngắn; có event thì trả event, hết thời gian thì trả kết quả rỗng/cursor. Client gọi lại có backoff. | Client cần lấy event nhưng không cần connection liên tục. |
| Subscription stream có lease | Client mở server stream trong một thời hạn; service đẩy event, sau đó đóng có kiểm soát để client reconnect. | Cần latency thấp và client online liên tục, nhưng vẫn phải hỗ trợ reconnect. |
| Webhook/callback | Service gọi endpoint đã đăng ký khi event sẵn sàng. | Client có endpoint nhận callback và chấp nhận quản lý bảo mật/retry callback. |

Không có một pattern đúng cho mọi bridge. Hãy dựa vào latency yêu cầu, số client, thời gian broker xử lý, khả năng reconnect và mức đảm bảo delivery. Điều cần tránh là một RPC không có deadline, không có lease và không có giới hạn số phiên.

## 4. Request/response bất đồng bộ cho tác vụ dài

Nếu client gửi command và chờ broker xử lý, thường nên tách việc nhận command khỏi việc đợi kết quả:

1. Client gọi SubmitCommand.
2. Service validate request, tạo operation_id và ghi command vào broker/outbox.
3. Service trả ACCEPTED cùng operation_id ngay khi command được chấp nhận theo durability contract.
4. Worker xử lý broker message và cập nhật operation state.
5. Client gọi GetOperation(operation_id) hoặc đăng ký notification để nhận kết quả.

Ví dụ response:

~~~protobuf
message SubmitCommandReply {
  string operation_id = 1;
  enum State {
    STATE_UNSPECIFIED = 0;
    ACCEPTED = 1;
    RUNNING = 2;
    SUCCEEDED = 3;
    FAILED = 4;
  }
  State state = 2;
}
~~~

ACCEPTED phải có semantics rõ: command đã được ghi bền vững vào broker hoặc transactional outbox, không chỉ được thêm vào một queue trong RAM. Nếu service trả accepted trước khi dữ liệu bền vững, process crash có thể làm mất command dù client tin rằng hệ thống đã nhận.

operation_id là định danh nghiệp vụ để truy vấn kết quả; nó không thay thế authentication. API GetOperation phải kiểm tra caller có quyền xem operation tương ứng.

## 5. Bounded long polling

Long polling giữ một RPC trong thời gian ngắn để đợi event tiếp theo, nhưng luôn có giới hạn. Client gửi cursor hoặc offset; server chờ tối đa max_wait, trả event nếu có hoặc trả no_event khi hết khoảng chờ.

~~~text
Client                         Bridge                         Broker
  |                              |                               |
  |-- Poll(cursor, max_wait) --->|                               |
  |                              |-- wait/read after cursor ---->|
  |                              |<--------- event / timeout ----|
  |<----- event or no_event -----|                               |
  |                              |                               |
  |-- Poll(next_cursor, ...) --->|   (new bounded RPC)           |
~~~

Giới hạn server phải nhỏ hơn hoặc bằng policy của service, bất kể client yêu cầu bao lâu. Ví dụ client xin 60 giây nhưng service chỉ cho phép tối đa 20 giây, server chỉ chờ tối đa 20 giây.

Deadline của RPC phải bao phủ thời gian chờ cộng phần thời gian xử lý/serialize response. Nếu deadline hết trước khi long poll kết thúc, client nhận DEADLINE_EXCEEDED; nếu khoảng chờ do ứng dụng quy định kết thúc bình thường mà chưa có event, trả no_event thay vì biến timeout nghiệp vụ thành RPC failure.

Ví dụ tính wait budget:

~~~java
import io.grpc.Context;
import io.grpc.Deadline;
import java.time.Duration;
import java.util.concurrent.TimeUnit;

Duration boundedWait(
        Duration requested,
        Duration maxWait,
        Duration responseMargin) {

    long waitMillis = Math.min(
            requested.toMillis(),
            maxWait.toMillis());

    Deadline deadline = Context.current().getDeadline();
    if (deadline != null) {
        long remainingMillis =
                deadline.timeRemaining(TimeUnit.MILLISECONDS);
        waitMillis = Math.min(
                waitMillis,
                Math.max(0, remainingMillis - responseMargin.toMillis()));
    }

    return Duration.ofMillis(waitMillis);
}
~~~

Đây chỉ là phép tính budget; brokerFacade.awaitNext(cursor, wait) cần là API bất đồng bộ hoặc chạy trên executor chuyên dụng. Không block gRPC transport/event-loop thread trong lúc chờ broker. Nếu wait budget bằng không, trả ngay kết quả rỗng hoặc status theo contract đã công bố.

Client nên dùng backoff có jitter khi liên tục nhận no_event, tránh hàng nghìn client poll cùng thời điểm. Có thể điều chỉnh wait duration theo mức tải, nhưng phải giữ giới hạn trên và deadline tổng.

## 6. Subscription stream có thời hạn

Server-streaming vẫn phù hợp khi cần đẩy event với latency thấp. Điểm khác biệt là stream có lease hoặc maximum lifetime rõ ràng:

- Mỗi session có max_session_age hoặc lease expiry.
- Session có giới hạn số event và số byte đang chờ.
- Client gửi cursor/last acknowledged sequence khi reconnect.
- Server đóng session bình thường khi lease hết hoặc trước rolling shutdown.
- Client reconnect với jitter và resume từ cursor đã xác nhận.
- Server áp dụng quota theo caller/tenant đã xác thực.

Ví dụ: session sống tối đa 5 phút. Trước khi đóng, server cung cấp cursor/checkpoint cuối theo semantics đã thống nhất. Client mở session mới và tiếp tục từ vị trí phù hợp. Không yêu cầu broker consumer dừng theo từng session; consumer nền tiếp tục quản lý offset độc lập.

Nếu stream hết hạn trong lúc đang có event chưa được xác nhận, client phải có khả năng nhận lại event đó. Đây là lý do cursor/acknowledgement và idempotent processing quan trọng hơn việc cố giữ socket mở mãi.

## 7. Bounded queue và backpressure

Broker có thể phát message nhanh hơn client đọc. Nếu bridge đưa mọi event vào queue không giới hạn, một client chậm có thể làm heap tăng dần cho tới khi service bị OOM.

Mỗi session cần giới hạn:

- Số event tối đa trong queue.
- Tổng byte payload tối đa.
- Tuổi tối đa của event đang chờ.
- Số session đồng thời trên mỗi principal/tenant.
- Tốc độ gửi tối đa nếu có quota nghiệp vụ.

Với gRPC Java, ServerCallStreamObserver.isReady() cho biết transport có thể nhận thêm message mà không vượt ngưỡng buffering hiện tại; setOnReadyHandler() báo khi trạng thái sẵn sàng thay đổi. Khi chưa ready, giữ event trong bounded queue và chờ callback; không tiếp tục gọi onNext() vô hạn.

~~~java
void drain(
        ServerCallStreamObserver<Event> stream,
        Queue<Event> pending) {

    while (stream.isReady()) {
        Event next = pending.poll();
        if (next == null) {
            return;
        }
        stream.onNext(next);
    }
}
~~~

Đoạn mã chỉ minh họa vòng drain; trong ứng dụng thật, queue phải thread-safe hoặc chỉ được truy cập từ một executor tuần tự. setOnReadyHandler callback cần ngắn và không được block để chờ broker. Dùng một sender/serial executor cho mỗi session để tránh nhiều thread gọi onNext đồng thời.

Khi queue đầy, phải có policy rõ ràng:

| Policy | Khi phù hợp | Hệ quả |
| --- | --- | --- |
| Pause broker consumption | Consumer có thể pause partition/subscription mà không ảnh hưởng subscriber khác. | Backpressure truyền ngược tới broker; cần tránh làm chậm cả consumer group. |
| Persist rồi gửi sau | Event cần giữ bền vững và subscriber có thể resume. | Cần storage/cursor và cleanup dữ liệu đã ack. |
| Disconnect slow subscriber | Subscriber phải reconnect và resume từ cursor. | Giải phóng RAM; cần xử lý duplicate khi reconnect. |
| Drop theo policy | Chỉ với event best-effort, mất event được chấp nhận. | Phải công bố rõ semantics và metric số event bị drop. |

Không âm thầm drop event quan trọng khi queue đầy. Trả lỗi hoặc đóng stream với trạng thái có thể phục hồi, ví dụ RESOURCE_EXHAUSTED kèm hướng dẫn reconnect/resume theo contract.

## 8. Broker acknowledgement không phải gRPC delivery acknowledgement

Gọi responseObserver.onNext(event) không chứng minh client đã nhận hoặc xử lý event. Tương tự, server gửi HTTP/2 frame không đồng nghĩa ứng dụng client đã commit dữ liệu.

Phải xác định khi nào broker message được ack/commit:

- Ack ngay khi đọc khỏi broker: có nguy cơ mất event nếu service crash trước khi gửi/ghi bền vững.
- Ack sau khi đưa vào queue RAM: vẫn có nguy cơ mất event nếu process crash trước khi queue được drain.
- Ack sau khi persist vào durable store/outbox: có thể phục hồi sau crash, nhưng cần quản lý cursor và cleanup.
- Ack sau application acknowledgement: tăng độ tin cậy end-to-end nhưng cần protocol ack, timeout, retry và deduplication.

Với yêu cầu at-least-once, thường chấp nhận event có thể được gửi lại; client xử lý idempotent bằng event ID/sequence. Nếu yêu cầu biết business processing đã hoàn tất, client phải gửi acknowledgement ở tầng ứng dụng. Không gọi onNext() là exactly-once delivery.

## 9. Cursor, resume và duplicate handling

Một subscription có thể bị gián đoạn bởi mạng, deploy, deadline hoặc lease expiry. Client nên lưu cursor/offset đã xử lý thành công và gửi lại khi reconnect:

~~~protobuf
message SubscribeRequest {
  string topic = 1;
  string resume_cursor = 2;
}

message EventEnvelope {
  string event_id = 1;
  string cursor = 2;
  bytes payload = 3;
}

message AckRequest {
  string subscription_id = 1;
  string event_id = 2;
  string cursor = 3;
}
~~~

Cursor phải có semantics rõ: broker offset, sequence per partition hay opaque token do bridge quản lý. Với nhiều partition, một cursor đơn có thể không đủ; cần vector/map offset hoặc opaque checkpoint được server encode.

Client chỉ cập nhật last acknowledged cursor sau khi xử lý event theo mức durability yêu cầu. Nếu cập nhật cursor trước khi commit business state, crash có thể làm mất event. Nếu commit business state trước rồi crash trước khi ack, event có thể được gửi lại; deduplication theo event ID giúp xử lý trường hợp đó.

Không dùng request ID của RPC làm cursor. Request ID liên kết log cho một call; cursor xác định vị trí tiến triển trong luồng event.

## 10. Mẫu session có giới hạn trong Spring gRPC

Service gRPC không nên tự tạo broker consumer trong mỗi subscribe() call. Một EventHub singleton do Spring quản lý nhận event từ consumer nền, sau đó đăng ký session có queue và lease riêng:

~~~java
@GrpcService
public final class EventSubscriptionService
        extends EventSubscriptionGrpc.EventSubscriptionImplBase {

    private static final Duration MAX_SESSION_AGE =
            Duration.ofMinutes(5);

    private final EventHub eventHub;
    private final ScheduledExecutorService scheduler;
    private final Executor serialExecutor;

    public EventSubscriptionService(
            EventHub eventHub,
            ScheduledExecutorService scheduler,
            Executor serialExecutor) {
        this.eventHub = eventHub;
        this.scheduler = scheduler;
        this.serialExecutor = serialExecutor;
    }

    @Override
    public void subscribe(
            SubscribeRequest request,
            StreamObserver<EventEnvelope> responseObserver) {

        ServerCallStreamObserver<EventEnvelope> stream =
                (ServerCallStreamObserver<EventEnvelope>) responseObserver;

        SubscriptionSession session = eventHub.openSession(
                request.getTopic(),
                request.getResumeCursor(),
                256,                 // max pending events
                2 * 1024 * 1024);    // max pending bytes

        session.attach(stream, serialExecutor);
        stream.setOnReadyHandler(session::scheduleDrain);
        stream.setOnCancelHandler(session::cancel);
        session.scheduleDrain(); // xử lý event đã có trước khi onReady chuyển trạng thái

        scheduler.schedule(
                session::expireGracefully,
                MAX_SESSION_AGE.toMillis(),
                TimeUnit.MILLISECONDS);
    }
}
~~~

EventHub, SubscriptionSession và sender ở đây là abstraction của ứng dụng; chúng phải bảo đảm queue có giới hạn, serialize mọi callback ghi stream, không block broker thread và cleanup idempotent. expireGracefully() nên ngừng nhận event mới cho session, flush phần có thể gửi trong budget hữu hạn, ghi checkpoint theo contract rồi gọi onCompleted() trên sender executor. Nếu session bị cancel, không gửi thêm event và giải phóng queue/listener.

Code production cần xử lý lỗi đồng bộ khi mở session, lịch expire bị hủy khi session đã đóng, exception từ sender và race giữa onReady, cancel, expire. Dùng terminal guard để onCompleted/onError không bị gọi nhiều lần. Không giữ SubscriptionSession trong map sau terminal cleanup.

## 11. Deadline, idle timeout và keepalive

Ba khái niệm này không thay thế nhau:

- **RPC deadline:** giới hạn thời gian tổng của một call. Khi hết, client kết thúc call và server nhận cancellation nếu transport/context truyền được.
- **Application idle timeout:** giới hạn khoảng thời gian session không có event hoặc không có tiến triển theo policy.
- **HTTP/2 keepalive:** kiểm tra connection còn phản hồi ở tầng transport; không chứng minh broker có event hoặc client xử lý event.

Với bounded long poll, deadline nên dài hơn max_wait cộng margin để serialize và trả response. Với subscription stream, dùng lease/max session age và reconnect thay vì dựa vào một RPC không deadline kéo dài vô hạn. Idle timeout chỉ nên áp dụng khi semantics cho phép; subscription hợp lệ có thể không có event trong thời gian dài.

Proxy có thể đặt idle timeout/maximum stream duration khác với server. Cấu hình client/server/proxy cần tương thích, và client phải xử lý DEADLINE_EXCEEDED, CANCELLED, UNAVAILABLE bằng reconnect policy có jitter cùng cursor.

## 12. Cancellation và graceful shutdown

Khi client cancel hoặc disconnect:

1. Dừng drain queue và không gọi onNext thêm.
2. Gỡ session khỏi event hub.
3. Hủy timer/heartbeat và callback đã đăng ký.
4. Giải phóng queue, buffer và correlation state.
5. Không hủy broker consumer dùng chung chỉ vì một subscriber rời đi.

Khi ứng dụng shutdown hoặc rolling deploy:

- Ngừng nhận subscription mới.
- Đánh dấu session hiện tại sắp hết hạn.
- Cho phép flush/ack trong một drain window có giới hạn.
- Đóng stream bình thường hoặc với status đã quy định.
- Client reconnect sau backoff có jitter và resume từ cursor.
- Broker consumer commit offset theo durability/ack policy, không commit chỉ vì gRPC socket đóng.

Nếu một session bị đóng vì server shutdown, client cần phân biệt lỗi có thể reconnect với lỗi nghiệp vụ cuối cùng. Đừng biến mọi disconnect thành OK nếu client có thể hiểu nhầm rằng stream đã xử lý hết dữ liệu.

## 13. Capacity và quota cho session

Ngay cả stream có lease cũng có thể quá nhiều nếu không giới hạn số session. Cần đặt:

- Max active sessions toàn service.
- Max sessions trên mỗi authenticated principal/tenant.
- Max pending events/bytes trên mỗi session.
- Max session age và reconnect rate.
- Giới hạn tốc độ tạo session để chống reconnect storm.
- Giới hạn kích thước event và tổng dữ liệu gửi mỗi session.

Khi vượt quota, trả RESOURCE_EXHAUSTED hoặc từ chối đăng ký theo contract. Có thể đưa retry-after hoặc retry hint qua metadata/trailers nếu client hiểu semantics; không gửi thời gian chờ tùy ý mà không giới hạn.

Định danh tenant lấy từ principal đã xác thực, không tin tenant ID tự khai trong request. Request ID, cursor và event ID không phải bằng chứng quyền truy cập.

## 14. Metrics và cảnh báo

Theo dõi các tín hiệu để biết stream có thực sự tiến triển:

| Metric | Ý nghĩa |
| --- | --- |
| active_subscription_sessions | Số gRPC subscription session đang mở. |
| subscription_session_duration | Thời lượng session trước khi kết thúc. |
| subscription_session_expired_total | Số session đóng do lease hết. |
| subscription_cancelled_total | Số session client hủy/disconnect. |
| pending_events / pending_bytes | Queue depth và bộ nhớ chờ gửi. |
| oldest_pending_event_age | Tuổi event lâu nhất trong queue. |
| broker_consumer_lag | Khoảng cách giữa broker head và offset đã commit. |
| event_delivery_attempts / redeliveries | Số lần gửi và gửi lại event. |
| slow_consumer_disconnects_total | Số subscriber bị đóng do không theo kịp. |
| session_reconnects_total | Tốc độ reconnect sau lease/disconnect. |

Đọc queue depth cùng broker lag và delivery rate. Queue tăng nhưng broker lag ổn định có thể chỉ ra client chậm; broker lag tăng trên mọi session có thể là consumer không theo kịp. Active sessions tăng cùng reconnect rate cao có thể báo hiệu lease quá ngắn hoặc proxy timeout không tương thích.

Labels nên có service, method, topic đã chuẩn hóa và outcome hữu hạn. Không đưa request ID, event ID, cursor, user ID hoặc session ID vào metric labels. Dùng log/trace để điều tra từng session.

## 15. Kiểm thử bridge có thời hạn

Kiểm thử nên bao gồm cả broker semantics và gRPC lifecycle:

1. Long poll có event: event được trả trước max_wait và cursor được cập nhật theo contract.
2. Long poll không có event: RPC trả no_event trong thời gian hữu hạn, không giữ call vô hạn.
3. RPC deadline ngắn hơn wait budget: client nhận DEADLINE_EXCEEDED; server cleanup session/waiter.
4. Subscription lease hết: server đóng stream, client reconnect với cursor đã ack.
5. Client cancel: session bị gỡ khỏi event hub, queue và listener được giải phóng.
6. Slow consumer: isReady false, queue không vượt max events/bytes và overflow policy được thực thi.
7. Broker burst: consumer thread không block chờ gRPC client; queue/lag phản ánh tải.
8. Broker ack: crash trước/sau durable handoff cho kết quả đúng với delivery guarantee đã chọn.
9. Duplicate delivery: client xử lý event lặp qua event ID/idempotency.
10. Rolling shutdown: session drain trong giới hạn, reconnect không tạo storm.
11. Nhiều subscriber: quota toàn service và per-principal được áp dụng.
12. Nhiều partition: resume cursor khôi phục đúng vị trí trên mọi partition.

Dùng latch/barrier và fake broker có điều khiển thay cho Thread.sleep() để xác định event/timeout. Bổ sung integration test với broker thật hoặc test container để kiểm tra commit, rebalance, redelivery và partition semantics; in-process gRPC test không kiểm chứng các thuộc tính này.

## 16. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| Stream mở mãi dù không có event | Không có deadline, lease hoặc idle policy. | Dùng bounded long poll hoặc subscription session có lease. |
| Tạo một broker consumer cho mỗi stream | Ghép lifecycle broker với từng caller. | Dùng consumer nền và event hub chung khi semantics cho phép. |
| Heap tăng khi client chậm | Queue không giới hạn hoặc bỏ qua isReady. | Bounded queue, byte cap và slow-consumer policy. |
| Broker ack nhưng client không xử lý event | Coi onNext là delivery/business acknowledgement. | Durable handoff hoặc explicit application ack. |
| Event mất sau restart | Ack broker khi dữ liệu chỉ nằm trong RAM. | Persist trước ack hoặc dùng offset/transaction phù hợp. |
| Event bị xử lý hai lần | Reconnect/resume không có deduplication. | Event ID, cursor và idempotent handler. |
| Keepalive vẫn bật nhưng stream không tiến triển | Nhầm transport health với application progress. | Theo dõi event age, queue, broker lag và lease. |
| Reconnect storm sau deploy | Tất cả session reconnect cùng lúc. | Lease/drain có jitter và client backoff có jitter. |
| Một subscriber chiếm hết tài nguyên | Không có session quota hoặc byte cap. | Quota theo principal/tenant và global capacity limit. |

## 17. Bài tập thực hành

1. Thiết kế API SubmitCommand trả operation_id và GetOperation để theo dõi kết quả broker bất đồng bộ.
2. Viết bounded long-poll method có max wait, deadline margin và kết quả no_event.
3. Thiết kế server-streaming subscription có max session age, resume cursor và bounded queue.
4. Dùng ServerCallStreamObserver.isReady()/setOnReadyHandler() để drain queue theo flow control.
5. Mô phỏng broker burst và slow client; xác minh queue không vượt event/byte cap.
6. Quyết định broker ack tại durable handoff hay application acknowledgement; ghi rõ delivery guarantee.
7. Kiểm thử cancellation, deadline, lease expiry, reconnect, duplicate event và graceful shutdown.
8. Tạo dashboard active sessions, queue bytes, oldest event age, broker lag, redelivery và slow-consumer disconnects.

Sau bài này, bạn cần biết cách tách broker consumer khỏi gRPC session, chọn bounded long polling hoặc subscription có lease, và quản lý queue/cursor/acknowledgement theo delivery guarantee. Stream có thể sống đủ lâu để đáp ứng latency yêu cầu, nhưng phải có giới hạn, khả năng reconnect và cleanup rõ ràng để messaging bridge trong hệ thống Spring gRPC không giữ tài nguyên vô thời hạn.
