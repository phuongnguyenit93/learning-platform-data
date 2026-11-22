# Phân biệt thứ tự frame, thứ tự thực thi và thứ tự nghiệp vụ

Trong ứng dụng STOMP, thấy client gửi message A trước message B không có nghĩa server chắc chắn hoàn tất xử lý A trước B, cũng không có nghĩa client nhận kết quả A trước kết quả B. Thứ tự tồn tại ở nhiều lớp: thứ tự frame trên kết nối, thứ tự message được Spring đưa qua các channel, thứ tự hoàn tất công việc bất đồng bộ và thứ tự nghiệp vụ mà domain yêu cầu.

Muốn hệ thống đúng, cần xác định chính xác lớp nào cần giữ thứ tự. Spring có các tùy chọn giữ thứ tự nhận và phát message theo từng WebSocket session. Khi nghiệp vụ cần thứ tự theo đơn hàng, tài khoản hoặc một đối tượng cụ thể, ứng dụng vẫn phải thiết kế sequence, xử lý đồng thời và giao dịch ở tầng nghiệp vụ.

## 1. Ba loại thứ tự cần phân biệt

| Loại thứ tự | Câu hỏi cần trả lời | Phạm vi bảo đảm |
| --- | --- | --- |
| **Thứ tự frame** | Frame nào được gửi/nhận trước trên một kết nối STOMP? | Thứ tự byte/frame trên từng stream kết nối |
| **Thứ tự thực thi** | Spring xử lý message nào trước, handler nào hoàn thành trước, outbound frame nào được ghi trước? | Phụ thuộc channel executor, cấu hình giữ thứ tự và công việc bất đồng bộ |
| **Thứ tự nghiệp vụ** | Lệnh nào phải có hiệu lực trước theo quy tắc domain? | Do ứng dụng và broker cụ thể thiết kế, thường theo aggregate hoặc business key |

Ví dụ một client gửi hai lệnh trên cùng WebSocket session:

1. Message A: cập nhật số lượng đơn hàng lên 2.
2. Message B: xác nhận đơn hàng.

Client đã gửi A trước B trên stream. Nhưng nếu server xử lý hai message bằng các worker thread khác nhau, B có thể hoàn tất trước A. Nếu B yêu cầu đơn hàng đã được cập nhật, kết quả có thể sai dù frame được gửi đúng thứ tự.

## 2. Thứ tự frame trên kết nối STOMP

STOMP là giao thức frame chạy trên một reliable two-way streaming transport như TCP. Trên cùng một kết nối, các byte được truyền theo thứ tự; vì vậy các frame mà client ghi liên tiếp lên cùng một STOMP connection được server đọc theo thứ tự stream. Tương tự, server ghi frame theo một thứ tự lên kết nối đó và client nhận lại theo thứ tự truyền.

Điều này chỉ áp dụng cho từng kết nối. Nếu hai trình duyệt, hai thiết bị hoặc hai producer mở hai kết nối khác nhau và cùng gửi message, STOMP không định nghĩa một thứ tự toàn cục giữa hai stream. Thời điểm gửi ở hai máy cũng không đủ để xác định một thứ tự tuyệt đối vì đồng hồ, network latency và scheduling khác nhau.

Ngoài ra, STOMP coi destination là chuỗi opaque và không định nghĩa semantics giao nhận cho destination. Ý nghĩa của /topic, /queue, thứ tự giao hàng, queue durability hay cách phân phối giữa consumer phụ thuộc server/broker. Không thể suy ra FIFO toàn cục chỉ từ tên destination.

## 3. Luồng message và các điểm có thể phát sinh concurrency trong Spring

Trong Spring WebSocket/STOMP, frame nhận từ WebSocket được giải mã thành Spring Message và gửi qua các channel:

~~~text
WebSocket client
      |
      v
STOMP frame decoder
      |
      v
clientInboundChannel
      |
      +---- /app/... ----> @MessageMapping controller
      |                         |
      |                         v
      |                    brokerChannel
      |                         |
      +---- /topic,... ---------+
                                |
                                v
                           Message broker
                                |
                                v
                        clientOutboundChannel
                                |
                                v
                         WebSocket session
~~~

Các channel quan trọng:

- **clientInboundChannel**: nhận message từ WebSocket client và định tuyến tới controller hoặc broker.
- **brokerChannel**: chuyển message từ code phía server tới message broker.
- **clientOutboundChannel**: chuyển message từ broker về WebSocket client.

Spring dùng các channel bất đồng bộ được hỗ trợ bởi executor/thread pool. Vì vậy, các message có thể được xử lý bởi những thread khác nhau. Mặc định, thứ tự handler được gọi hoặc thứ tự client nhận message không nhất thiết giống thứ tự message đã được nhận hoặc được publish.

Một request có thể đi qua controller, gọi service, truy vấn database, đợi HTTP API hoặc gửi kết quả bất đồng bộ. Mỗi điểm chờ có thể làm thay đổi thứ tự hoàn tất. Đây là lý do phải phân biệt thứ tự nhận frame với thứ tự hoàn tất công việc.

## 4. Giữ thứ tự message client gửi vào Spring

Từ Spring Framework 6.1, có thể yêu cầu Spring xử lý message inbound theo thứ tự nhận trong cùng một session bằng **setPreserveReceiveOrder(true)** trên **StompEndpointRegistry**.

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class WebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
        registry.setPreserveReceiveOrder(true);
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
    }
}
~~~

Khi bật flag này, các message từ cùng một client session được đưa tới **clientInboundChannel** lần lượt từng message, giữ thứ tự mà Spring nhận được. Các session khác vẫn có thể được xử lý đồng thời.

Nếu client A gửi frame 1 rồi frame 2, Spring sẽ dispatch frame 1 trước frame 2 trên inbound channel của session đó. Tuy nhiên, flag này không tạo thứ tự giữa hai client session khác nhau.

**Lưu ý về phiên bản:** setPreserveReceiveOrder được bổ sung từ Spring Framework 6.1. Dự án dùng Spring 6.0 hoặc cũ hơn không có API này. Hãy kiểm tra phiên bản thực tế trước khi dùng cấu hình.

## 5. Giữ thứ tự message Spring gửi tới client

Chiều outbound có một vấn đề tương tự. Message từ broker được chuyển tới **clientOutboundChannel** để ghi lên WebSocket session. Vì channel dùng ThreadPoolExecutor, các message có thể được xử lý bởi nhiều thread và client có thể nhận kết quả khác thứ tự publish ban đầu.

Có thể bật **setPreservePublishOrder(true)** trên **MessageBrokerRegistry**:

~~~java
@Override
public void configureMessageBroker(MessageBrokerRegistry registry) {
    registry.setApplicationDestinationPrefixes("/app");
    registry.enableSimpleBroker("/topic", "/queue");
    registry.setPreservePublishOrder(true);
}
~~~

Khi bật, message trong cùng một client session được đưa qua clientOutboundChannel từng message một để giữ thứ tự publish. Flag này có từ Spring Framework 5.1.

Có thể bật cả hai flag trong cùng cấu hình:

~~~java
@Configuration
@EnableWebSocketMessageBroker
public class OrderedWebSocketConfiguration
        implements WebSocketMessageBrokerConfigurer {

    @Override
    public void registerStompEndpoints(StompEndpointRegistry registry) {
        registry.addEndpoint("/ws");
        registry.setPreserveReceiveOrder(true);
    }

    @Override
    public void configureMessageBroker(MessageBrokerRegistry registry) {
        registry.setApplicationDestinationPrefixes("/app");
        registry.enableSimpleBroker("/topic", "/queue");
        registry.setPreservePublishOrder(true);
    }
}
~~~

Hai flag có mục tiêu khác nhau:

| Cấu hình | Vị trí | Giữ thứ tự |
| --- | --- | --- |
| setPreserveReceiveOrder(true) | registerStompEndpoints | Client gửi vào Spring, theo từng session |
| setPreservePublishOrder(true) | configureMessageBroker | Spring/broker publish ra client, theo từng session |

Cả hai đều có overhead hiệu năng. Chỉ bật khi ứng dụng cần thứ tự cho các message trong một session. Chúng không bảo đảm thứ tự giữa các session, giữa nhiều instance Spring hoặc giữa các producer độc lập.

## 6. Giới hạn quan trọng: thứ tự dispatch không phải thứ tự hoàn tất

Hai flag của Spring kiểm soát thứ tự đưa message qua channel. Chúng không làm cho một công việc bất đồng bộ phải hoàn tất trước khi công việc tiếp theo bắt đầu.

Spring cho phép method @MessageMapping trả về **CompletableFuture**, **CompletionStage** hoặc một future tương đương. Điều này hữu ích khi xử lý tác vụ I/O dài, nhưng hai future có thể hoàn tất theo thứ tự ngược với thứ tự được tạo.

Ví dụ minh họa:

~~~java
@Controller
public class OrderController {

    private final OrderService orderService;
    private final Executor taskExecutor;

    public OrderController(
            OrderService orderService,
            @Qualifier("applicationTaskExecutor") Executor taskExecutor) {
        this.orderService = orderService;
        this.taskExecutor = taskExecutor;
    }

    @MessageMapping("/orders/update")
    public CompletableFuture<OrderResult> update(
            @Payload OrderCommand command) {

        return CompletableFuture.supplyAsync(
                () -> orderService.apply(command),
                taskExecutor);
    }
}
~~~

Giả sử client gửi hai command liên tiếp:

- Command sequence 10 bắt đầu truy vấn một hệ thống ngoài và mất 2 giây.
- Command sequence 11 chỉ cập nhật dữ liệu cache và mất 100 ms.

Ngay cả khi bật **setPreserveReceiveOrder(true)**, controller vẫn có thể khởi chạy future cho sequence 10, trả về ngay, rồi xử lý sequence 11. Future của 11 hoàn tất trước future của 10. Nếu kết quả được gửi khi future hoàn tất, client có thể nhận kết quả sequence 11 trước sequence 10.

Tương tự, **setPreservePublishOrder(true)** chỉ giữ thứ tự các message khi chúng được đưa vào outbound channel. Nếu công việc bất đồng bộ đã hoàn tất theo thứ tự 11 rồi 10, outbound channel sẽ giữ thứ tự 11 rồi 10; nó không biết sequence 10 đáng lẽ phải được phát trước.

Nếu thứ tự hoàn tất quan trọng, hãy điều phối công việc theo business key hoặc đợi công việc trước hoàn tất trước khi bắt đầu công việc tiếp theo của cùng key.

## 7. Thứ tự nghiệp vụ phải được định nghĩa theo domain

Một hệ thống có thể cần các quy tắc khác nhau:

- Cập nhật cùng một đơn hàng phải theo sequence.
- Các thao tác trên cùng một tài khoản phải được tuần tự hóa để tránh số dư âm.
- Event của cùng một thiết bị phải theo thứ tự đo hoặc thời điểm phát sinh.
- Các thông báo độc lập của hai người dùng có thể xử lý song song.

Không nên dùng một hàng đợi toàn cục nếu chỉ một số entity cần tuần tự hóa. Thường nên giữ thứ tự theo **aggregate ID**, ví dụ orderId hoặc accountId, và cho phép các aggregate khác nhau xử lý đồng thời.

Có ba cách phổ biến:

1. **Sequence number:** producer hoặc hệ thống có thẩm quyền cấp số thứ tự tăng dần cho từng aggregate. Consumer kiểm tra sequence tiếp theo trước khi áp dụng.
2. **Partition/queue theo key:** broker hoặc message platform định tuyến cùng một aggregate vào cùng partition/consumer lane, bảo đảm xử lý tuần tự trong phạm vi broker hỗ trợ.
3. **Database serialization:** dùng transaction và khóa theo entity để chỉ một transaction cập nhật aggregate tại một thời điểm; kiểm tra sequence/version trước khi commit.

Dù chọn cách nào, cần định nghĩa rõ cách xử lý duplicate, missing sequence và retry. Thứ tự không có ý nghĩa nếu event bị áp dụng hai lần hoặc event bị mất.

## 8. Kiểm soát sequence trong transaction

Ví dụ một command có orderId, eventId và sequence. Sequence được cấp bởi hệ thống có thẩm quyền khi tạo command. Consumer khóa bản ghi đơn hàng trong transaction, kiểm tra sequence và chỉ áp dụng lệnh kế tiếp.

~~~java
public record OrderCommand(
        UUID orderId,
        String eventId,
        long sequence,
        String action) {
}
~~~

Repository có thể khóa hàng cần cập nhật:

~~~java
public interface OrderRepository extends JpaRepository<Order, UUID> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select o from Order o where o.id = :id")
    Optional<Order> findForUpdate(@Param("id") UUID id);
}
~~~

Service xử lý command:

~~~java
@Service
public class OrderCommandService {

    private final OrderRepository orders;
    private final ProcessedEventRepository processedEvents;

    public OrderCommandService(
            OrderRepository orders,
            ProcessedEventRepository processedEvents) {
        this.orders = orders;
        this.processedEvents = processedEvents;
    }

    @Transactional
    public void apply(OrderCommand command) {
        Order order = orders.findForUpdate(command.orderId())
                .orElseThrow();

        if (processedEvents.existsById(command.eventId())) {
            return; // Cùng event đã được xử lý trước đó.
        }

        long expected = order.getLastAppliedSequence() + 1;

        if (command.sequence() != expected) {
            throw new OutOfOrderCommandException(
                    "Expected sequence " + expected
                            + " but received " + command.sequence());
        }

        order.apply(command.action());
        order.setLastAppliedSequence(command.sequence());

        processedEvents.save(new ProcessedEvent(command.eventId()));
    }
}
~~~

Đây là ví dụ minh họa; entity, repository và exception cần được định nghĩa theo dự án. Khóa PESSIMISTIC_WRITE tuần tự hóa transaction cập nhật cùng hàng đơn hàng. Sequence check phát hiện command tới sai thứ tự; transaction rollback để không cập nhật trạng thái.

Nếu sequence lớn hơn expected, không được âm thầm bỏ command. Có thể lưu command vào vùng pending và xử lý lại khi sequence còn thiếu đến, hoặc đưa vào retry/dead-letter workflow. Nếu sequence nhỏ hơn expected nhưng eventId chưa từng xử lý, đó có thể là command cũ hoặc dữ liệu mâu thuẫn; cần chính sách rõ ràng thay vì coi mọi trường hợp là duplicate.

Kiểm tra eventId và cập nhật aggregate nên nằm trong cùng transaction để tránh trường hợp đánh dấu event đã xử lý nhưng thay đổi đơn hàng chưa commit, hoặc ngược lại. Khi publish event ra broker sau commit, cân nhắc transactional outbox để lưu event cùng transaction dữ liệu, sau đó publisher phát theo sequence của aggregate.

## 9. Nhiều producer và thứ tự toàn cục

Khi hai client gửi command cùng lúc, không tồn tại một thứ tự toàn cục tự nhiên chỉ dựa vào timestamp ở client. Đồng hồ trên thiết bị có thể lệch và message có thể đi qua network với độ trễ khác nhau.

Nếu domain cần một thứ tự, phải chọn nơi có thẩm quyền xác lập thứ tự:

- Database tạo sequence trong transaction.
- Một service duy nhất cấp version cho aggregate.
- Broker partition được chọn theo key và có semantics ordering rõ ràng.
- Một coordinator tuần tự hóa các command cùng aggregate.

Ví dụ, hai client đồng thời cập nhật order-42. Cả hai có thể gửi sequence dự kiến 8. Database lock/version check cho phép một command thắng và command còn lại nhận conflict. Client cần tải lại trạng thái hoặc gửi command mới với version đúng; không tự giả định thời gian gửi quyết định command nào thắng.

Đối với nhiều Spring application instance, khóa Java như **synchronized** chỉ có hiệu lực trong một JVM. Nó không bảo vệ entity khi request được xử lý trên instance khác. Dùng database lock/version, distributed lock có fencing token, hoặc broker partitioning phù hợp với yêu cầu.

## 10. Transaction và thứ tự publish event

Một vấn đề khác xuất hiện khi ứng dụng cập nhật database và publish STOMP event. Nếu publish trước khi transaction commit, subscriber có thể nhận thông báo về trạng thái chưa được commit. Nếu transaction rollback, event đã gửi vẫn tồn tại và client thấy trạng thái không có thật.

Một lựa chọn là phát event sau khi transaction commit, nhưng nếu tiến trình chết giữa commit và publish thì event có thể bị mất. Transactional outbox giải quyết khoảng trống này bằng cách lưu thay đổi domain và event vào cùng transaction database; một publisher riêng đọc outbox và phát event.

Outbox cần lưu aggregate ID và sequence để publisher phát theo đúng thứ tự từng aggregate. Nếu có nhiều publisher worker, phải partition hoặc khóa theo aggregate để tránh worker sau phát sequence 12 trước worker đang xử lý sequence 11. Consumer vẫn nên idempotent và kiểm tra sequence vì network/broker có thể redeliver.

**@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)** có thể hữu ích cho tác vụ phát event sau commit trong ứng dụng đơn giản. Tuy nhiên, listener chạy sau commit không tự bảo đảm event được giao bền vững nếu process dừng giữa commit và publish; outbox phù hợp hơn khi không được phép mất event.

## 11. Broker ordering và giới hạn của STOMP

STOMP không định nghĩa delivery semantics của destination. Tên **/topic** hay **/queue** không tự bảo đảm FIFO, durability hoặc thứ tự giữa các producer. Hãy kiểm tra tài liệu broker cụ thể.

Ngay cả khi broker cung cấp FIFO queue, cần kiểm tra phạm vi bảo đảm:

- FIFO theo một queue hay theo từng partition?
- Nhiều producer có thứ tự toàn cục hay chỉ giữ thứ tự trên từng connection?
- Nhiều consumer có thể xử lý song song và hoàn tất ngược thứ tự không?
- Redelivery sau lỗi có thể xuất hiện trước message mới hơn không?
- Retry/dead-letter có làm thay đổi thứ tự không?
- Broker có hỗ trợ message group hoặc routing theo key không?

Ví dụ broker giao message 21 rồi 22 tới cùng một consumer, nhưng consumer dùng hai worker thread. Worker của 22 hoàn tất trước worker của 21. Broker có thể đã giao đúng thứ tự nhưng ứng dụng vẫn hoàn tất nghiệp vụ sai thứ tự. Muốn giữ thứ tự từ đầu tới cuối, cả broker delivery và consumer processing đều phải tuân thủ cùng quy tắc tuần tự hóa.

## 12. Hiệu năng khi giữ thứ tự

Giữ thứ tự thường làm giảm concurrency trong phạm vi cần tuần tự hóa. Với Spring:

- **setPreserveReceiveOrder(true)** giới hạn việc dispatch inbound trong cùng session theo thứ tự.
- **setPreservePublishOrder(true)** giới hạn việc publish outbound tới cùng session theo thứ tự.
- Các session khác vẫn có thể xử lý đồng thời.
- Công việc bất đồng bộ bên trong controller/service vẫn cần cơ chế điều phối riêng.
- Giữ thứ tự không sửa được bottleneck do database, API ngoài hoặc client chậm.

Spring mặc định cấu hình thread pool cho clientInboundChannel và clientOutboundChannel ở mức hai lần số processor khả dụng. Kích thước pool phải phù hợp loại tải CPU-bound hoặc I/O-bound. Tăng thread pool không tạo ra thứ tự; bật preserve-order cũng không thay thế việc thiết kế pool và backpressure phù hợp.

Nếu chỉ một số luồng nghiệp vụ cần thứ tự, ưu tiên tuần tự hóa theo aggregate key thay vì buộc toàn bộ hệ thống xử lý từng message một. Đo throughput, latency p95/p99 và queue depth trước/sau khi bật các flag.

## 13. Cách chẩn đoán message bị đảo thứ tự

Khi thấy event đến sai thứ tự, đừng chỉ nhìn timestamp hiển thị trên UI. Hãy ghi nhận các mốc sau:

1. **Client send:** session ID, frame/event ID, sequence và thời điểm client gửi.
2. **Server receive:** thời điểm frame được giải mã và đưa vào clientInboundChannel.
3. **Handler start:** thời điểm @MessageMapping bắt đầu xử lý.
4. **Business commit:** thời điểm transaction hoàn tất và version/sequence mới được commit.
5. **Broker publish:** thời điểm event được gửi vào brokerChannel hoặc broker.
6. **Outbound send:** thời điểm message được đưa vào clientOutboundChannel và ghi lên WebSocket.
7. **Client receive:** thời điểm client nhận và xử lý message.

Gắn một **correlationId**, **aggregateId** và **sequence** xuyên suốt các log. Dùng sequence để kiểm tra thứ tự logic; timestamp chỉ giúp tìm độ trễ và khoảng thời gian. Nếu chỉ log timestamp với độ chính xác thấp, hai message có thể cùng timestamp dù thứ tự thực tế khác nhau.

Các dấu hiệu thường gặp:

| Quan sát | Lớp có thể gây ra |
| --- | --- |
| Client ghi frame A rồi B nhưng server log nhận B trước A trên cùng session | Kiểm tra client framing, transport, session mapping và điểm ghi log |
| Server nhận A rồi B nhưng handler bắt đầu B trước A | Inbound channel executor; cân nhắc preserveReceiveOrder |
| Handler A bắt đầu trước B nhưng B commit trước A | Async service, database lock hoặc thời gian I/O; cần business sequencing |
| Service commit A rồi B nhưng client nhận B trước A | Outbound channel; cân nhắc preservePublishOrder và broker behavior |
| Hai session khác nhau có thứ tự khác nhau | Không có global order; cần business sequence nếu domain yêu cầu |
| Broker giao A rồi B nhưng consumer hoàn tất B trước A | Consumer concurrency; xử lý theo key hoặc sequence |

## 14. Kiểm thử thứ tự

Một bài test tốt nên tách riêng các lớp thay vì chỉ assert thứ tự cuối cùng trên client:

- Gửi A rồi B trên cùng một session; ghi lại thứ tự handler bắt đầu khi preserveReceiveOrder tắt và bật.
- Dùng CountDownLatch hoặc CompletableFuture điều khiển thời điểm hoàn tất để cố tình cho B hoàn tất trước A; xác nhận inbound flag không tự bảo đảm completion order.
- Publish hai event theo thứ tự xác định tới cùng session; kiểm tra outbound flag giữ thứ tự publish.
- Gửi cùng aggregate từ hai session khác nhau; xác nhận sequence check ngăn cập nhật sai thứ tự.
- Gửi duplicate eventId; xác nhận consumer xử lý idempotent.
- Gửi sequence có khoảng trống; xác nhận event được retry/pending hoặc báo lỗi rõ ràng.
- Chạy test với nhiều application instance nếu production triển khai clustered.
- Test transaction rollback và outbox retry để bảo đảm event không được phát sai trạng thái hoặc sai sequence.

Tránh dùng Thread.sleep để ép thứ tự trong test. Dùng latch, barrier, future hoặc test executor để kiểm soát chính xác thời điểm mỗi handler bắt đầu và hoàn tất.

## 15. Tài liệu tham khảo

- [Spring Framework — Order of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/ordered-messages.html): preserveReceiveOrder, preservePublishOrder và phạm vi theo session.
- [Spring Framework — Flow of Messages](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/message-flow.html): clientInboundChannel, brokerChannel, clientOutboundChannel và message routing.
- [Spring Framework — Performance](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/configuration-performance.html): channel thread pools, blocking work, send limits và scaling.
- [Spring Framework — Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/websocket/stomp/handle-annotations.html): @MessageMapping và hỗ trợ CompletableFuture/CompletionStage.
- [STOMP 1.2 Specification](https://stomp.github.io/stomp-specification-1.2.html): ordered stream, destination semantics và ACK/transaction protocol.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction boundaries và transaction synchronization.
