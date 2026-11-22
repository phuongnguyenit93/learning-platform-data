# Giới hạn đồng thời, bộ đệm và tải tối đa của bên nhận

Khi số producer và client tăng, một message receiver có thể nhận nhiều request hơn khả năng xử lý của database, HTTP client, thread pool hoặc chính ứng dụng. Nếu không có giới hạn, request sẽ tích lũy, hàng đợi tăng, bộ nhớ bị chiếm và độ trễ lan rộng. Một hệ thống messaging có thể vẫn nhận được message nhưng không còn đủ tài nguyên để xử lý chúng an toàn.

Thiết kế tải phía nhận cần kiểm soát đồng thời ba đại lượng:

- **Concurrency:** số tác vụ đang được xử lý cùng lúc.
- **Buffer/queue:** số message đang chờ được xử lý.
- **Rate:** số message hoặc request được chấp nhận trong một đơn vị thời gian.

Ba đại lượng này giải quyết các vấn đề khác nhau. Giới hạn concurrency bảo vệ tài nguyên đang hoạt động; giới hạn buffer bảo vệ bộ nhớ và thời gian chờ; rate limit ngăn một producer gửi quá nhanh trong thời gian dài. Backpressure giúp nguồn phát điều chỉnh theo nhu cầu của bên nhận khi cả hai phía hỗ trợ Reactive Streams.

## 1. Vì sao bên nhận cần giới hạn tải?

Một handler có thể trả về Mono hoặc Flux nhưng điều đó không có nghĩa ứng dụng có khả năng xử lý số lượng request vô hạn. Mỗi request vẫn có thể chiếm:

- Một kết nối database hoặc HTTP client.
- Bộ nhớ để giữ payload, context, kết quả trung gian và response.
- CPU để deserialize, validate và chạy nghiệp vụ.
- Một vị trí trong thread pool hoặc scheduler nếu có tác vụ blocking.
- Một vị trí trong hàng đợi khi downstream đang chậm.
- Tài nguyên của broker, socket và transport.

Ví dụ, database connection pool chỉ có 30 connection. Nếu server đồng thời chạy 300 handler đều cần truy vấn database, phần lớn handler sẽ phải chờ connection. Chờ đợi đó vẫn tiêu thụ bộ nhớ, kéo dài thời gian xử lý và có thể làm timeout ở nhiều tầng.

Một luồng tải thường diễn ra như sau:

1. Producer phát message nhanh hơn tốc độ xử lý.
2. Message đến receiver và chờ tài nguyên downstream.
3. Hàng đợi hoặc số request đang hoạt động tăng.
4. Độ trễ tăng, timeout và retry xuất hiện.
5. Retry làm tải tăng thêm, trong khi downstream vẫn đang quá tải.
6. Bộ nhớ, connection hoặc thread pool cạn kiệt và hệ thống mất khả năng phục vụ.

Giới hạn tải phải được đặt trước điểm tiêu thụ tài nguyên đắt đỏ. Chỉ giới hạn số thread ở cuối pipeline có thể chưa đủ nếu ứng dụng đã nhận và giữ quá nhiều payload trước đó.

## 2. Phân biệt concurrency, rate limit, backpressure và buffer

| Cơ chế | Giới hạn điều gì? | Câu hỏi được trả lời |
|---|---|---|
| Concurrency limit / bulkhead | Số operation đang chạy cùng lúc | Có bao nhiêu request được xử lý đồng thời? |
| Rate limit | Số request được phép bắt đầu trong một khoảng thời gian | Một client được gửi bao nhiêu request mỗi giây? |
| Backpressure | Demand mà subscriber gửi ngược về publisher | Consumer hiện muốn nhận thêm bao nhiêu phần tử? |
| Buffer/queue limit | Số phần tử được giữ để chờ xử lý | Có bao nhiêu message được phép xếp hàng? |
| Timeout/deadline | Thời gian chờ hoặc xử lý tối đa | Một request được phép chờ bao lâu? |
| Circuit breaker | Khả năng gọi một dependency đang lỗi | Khi nào cần tạm ngừng gọi downstream? |

Không dùng một cơ chế để thay thế tất cả cơ chế còn lại. Ví dụ:

- Backpressure không tự giới hạn số request độc lập mà nhiều client có thể mở.
- Concurrency limit không ngăn một producer liên tục gửi request mới sau khi request trước hoàn tất.
- Rate limit không giới hạn số request đang chạy nếu mỗi request mất nhiều thời gian.
- Buffer không làm tăng năng lực xử lý; nó chỉ giữ message chờ và cần giới hạn.
- Timeout không giải phóng được tài nguyên nếu thư viện blocking bên dưới không hỗ trợ hủy thao tác.

Một receiver ổn định thường kết hợp concurrency limit, buffer hữu hạn, rate limit phù hợp, timeout và cơ chế từ chối hoặc giảm tải.

## 3. Backpressure trong Reactive Streams và RSocket

Reactive Streams định nghĩa cơ chế demand: subscriber yêu cầu publisher phát một số phần tử thông qua subscription. Publisher chỉ nên phát theo nhu cầu đã được yêu cầu.

Trong Reactor, subscriber có thể yêu cầu dữ liệu bằng các operator hoặc API điều khiển request. Với RSocket, Request-Stream và Channel truyền flow control qua các frame REQUEST_N. Requester thông báo số phần tử muốn nhận; responder điều chỉnh việc phát dữ liệu theo demand.

Điều này giúp tránh việc responder đẩy vô hạn phần tử vào một client không thể tiêu thụ kịp.

Tuy nhiên, cần phân biệt:

- REQUEST_N điều khiển số phần tử trong một stream.
- Nó không phải giới hạn toàn cục số stream hoặc số request đồng thời mà server chấp nhận.
- Một client vẫn có thể mở nhiều stream độc lập.
- Request-Response chỉ có một response cho mỗi request; giới hạn tổng số request đồng thời vẫn cần được thực hiện ở tầng ứng dụng.
- Fire-and-Forget không cung cấp cùng mô hình demand của một response stream; server vẫn cần giới hạn công việc mà request tạo ra.

Ví dụ responder trả về stream:

~~~java
@Controller
class InventoryController {

    @MessageMapping("inventory.watch")
    Flux<InventoryUpdate> watch(InventoryRequest request) {
        return inventoryService.watch(request.sku());
    }
}
~~~

Requester có thể điều khiển demand khi subscribe:

~~~java
Flux<InventoryUpdate> updates = requester
    .route("inventory.watch")
    .data(request)
    .retrieveFlux(InventoryUpdate.class);
~~~

Khi consumer yêu cầu ít phần tử, flow control có thể làm chậm việc phát dữ liệu. Đây là cơ chế quan trọng của Request-Stream và Channel, nhưng server vẫn phải kiểm soát số subscription, chi phí tạo stream và tải của nguồn dữ liệu.

Không giả định mọi transport của Spring Messaging đều có Reactive Streams backpressure end-to-end. RSocket có flow control theo protocol. Với STOMP, WebSocket hoặc một broker cụ thể, adapter và broker có thể có cơ chế buffer, prefetch hoặc acknowledgement riêng. Cần kiểm tra khả năng của transport thực tế.

## 4. Giới hạn concurrency trong một pipeline Reactor

Operator **flatMap** có tham số concurrency để giới hạn số inner publisher được subscribe cùng lúc trong một subscription.

~~~java
Flux<EnrichedOrder> enriched = Flux.fromIterable(orderIds)
    .flatMap(
        id -> orderService.loadAndEnrich(id),
        8
    );
~~~

Với concurrency bằng 8, pipeline này chỉ chạy tối đa tám inner operation cùng lúc. Khi một operation hoàn tất, pipeline có thể subscribe operation tiếp theo.

Có thể dùng thêm prefetch để điều chỉnh số phần tử được yêu cầu trước từ mỗi inner publisher:

~~~java
Flux<Result> results = requests.flatMap(
    request -> remoteService.call(request),
    8,
    1
);
~~~

Trong ví dụ, tối đa tám inner publisher được xử lý đồng thời và prefetch của mỗi inner publisher là một phần tử. Giá trị thực tế cần được chọn dựa trên chi phí xử lý và khả năng của downstream.

Các operator khác:

- **concatMap:** xử lý tuần tự từng phần tử, chỉ subscribe inner publisher tiếp theo sau khi inner trước hoàn tất.
- **flatMapSequential:** cho phép inner publisher chạy đồng thời nhưng giữ thứ tự phát kết quả theo thứ tự đầu vào.
- **parallel:** chia công việc thành rails để xử lý CPU-bound; không phải cơ chế giới hạn số request toàn hệ thống.

Quan trọng: concurrency của flatMap là giới hạn trong một subscription. Nếu có 100 client, mỗi client có pipeline flatMap concurrency bằng 8, tổng số inner operation vẫn có thể tiến đến 800. Muốn giới hạn toàn cục, cần admission control hoặc bulkhead dùng chung ở cấp service/application.

## 5. Giới hạn số request đồng thời ở phía receiver

Với RSocket annotated controller, có thể đặt một giới hạn toàn cục hoặc theo nhóm operation trước khi gọi service tốn tài nguyên. Ví dụ dưới đây dùng Semaphore không chặn để giới hạn tối đa 64 operation reactive đang hoạt động:

~~~java
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.Semaphore;

import org.springframework.messaging.handler.annotation.MessageMapping;
import org.springframework.stereotype.Controller;

import reactor.core.publisher.Mono;

@Controller
class ReportController {

    private final Semaphore permits = new Semaphore(64);
    private final ReportService reportService;

    ReportController(ReportService reportService) {
        this.reportService = reportService;
    }

    @MessageMapping("reports.generate")
    Mono<Report> generate(ReportRequest request) {
        return Mono.defer(() -> {
            if (!permits.tryAcquire()) {
                return Mono.error(
                    new RejectedExecutionException(
                        "Receiver is at capacity"
                    )
                );
            }

            return Mono.defer(() -> reportService.generate(request))
                .doFinally(signal -> permits.release());
        });
    }
}
~~~

Cách hoạt động:

1. **Mono.defer** trì hoãn việc nhận permit đến lúc request thực sự được subscribe.
2. **tryAcquire** không chờ thread. Nếu hết permit, request bị từ chối ngay.
3. Khi có permit, service reactive được gọi.
4. **doFinally** giải phóng permit khi publisher complete, error hoặc nhận cancellation.
5. Khi operation kết thúc, request khác có thể sử dụng permit vừa được trả lại.

Đây là ví dụ fail-fast: không có hàng đợi chờ permit. Cách này phù hợp khi client có thể nhận lỗi quá tải và retry theo chính sách có giới hạn.

Service trong ví dụ trả về Mono và cần tôn trọng cancellation. Nếu gọi một API blocking không thể hủy, cancellation của subscriber có thể xảy ra trước khi tác vụ blocking thực sự dừng. Khi đó, không nên coi thời điểm doFinally chạy là thời điểm tài nguyên vật lý đã được giải phóng. Hãy đặt timeout trong client blocking và dùng executor/bulkhead có giới hạn để kiểm soát chính tác vụ đang chạy.

### Fail-fast hay chờ trong hàng đợi?

Có hai chính sách phổ biến:

- **Fail-fast:** khi hết permit, trả lỗi quá tải ngay. Ưu điểm là không tạo thêm hàng đợi; client có thể backoff rồi thử lại.
- **Bounded wait queue:** cho phép một số lượng hữu hạn request chờ permit. Cần giới hạn số phần tử và thời gian chờ; khi queue đầy hoặc hết deadline thì từ chối.

Không dùng một hàng đợi vô hạn để làm cho hệ thống có vẻ tiếp nhận được mọi request. Hàng đợi càng dài, request càng cũ khi được xử lý và càng dễ hết deadline nghiệp vụ.

## 6. Bulkhead theo dependency và theo tenant

Một giới hạn toàn cục có thể ngăn server quá tải, nhưng chưa chắc bảo vệ được từng dependency. Ví dụ, báo cáo dùng database connection lâu hơn API tra cứu đơn hàng. Nếu cả hai chia sẻ cùng một pool và một semaphore, tác vụ báo cáo có thể chiếm hết năng lực phục vụ.

Bulkhead tách tài nguyên theo nhóm:

- Giới hạn riêng cho truy vấn database.
- Giới hạn riêng cho dịch vụ thanh toán.
- Giới hạn riêng cho tác vụ tạo báo cáo.
- Giới hạn riêng cho tenant hoặc client nếu cần fairness.

Ví dụ có thể có semaphore riêng cho mỗi dependency hoặc dùng thư viện bulkhead như Resilience4j. Mỗi bulkhead cần có giới hạn và chính sách khi đầy: reject, wait trong hàng đợi hữu hạn hoặc trả fallback phù hợp.

Giới hạn theo tenant giúp một khách hàng gửi lượng request lớn không chiếm toàn bộ năng lực hệ thống. Khi triển khai, cần kiểm soát số lượng limiter được tạo ra để tránh tạo map không giới hạn theo tenant ID.

Không nên dùng một semaphore chung cho toàn bộ application nếu các loại request có thời gian xử lý và mức ưu tiên rất khác nhau. Hãy phân loại theo tài nguyên downstream mà operation thực sự sử dụng.

## 7. Bộ đệm hữu hạn và chính sách overflow

Buffer hữu ích khi producer và consumer có tốc độ dao động khác nhau. Nhưng buffer phải có giới hạn.

Với nguồn tuân thủ backpressure, nên ưu tiên để demand truyền ngược đến nguồn thay vì thêm buffer lớn. Với hot source hoặc callback API không thể dừng phát, có thể cần buffer để hấp thụ burst ngắn.

Ví dụ buffer tối đa 256 phần tử và phát lỗi khi đầy:

~~~java
Flux<Event> buffered = hotEventSource
    .onBackpressureBuffer(
        256,
        dropped -> metrics.counter("events.buffer.overflow").increment(),
        BufferOverflowStrategy.ERROR
    );
~~~

Cần chọn chính sách theo ý nghĩa dữ liệu:

| Chính sách | Hành vi | Khi phù hợp |
|---|---|---|
| ERROR | Phát lỗi khi buffer đầy | Không được âm thầm mất dữ liệu |
| DROP_OLDEST | Loại phần tử cũ nhất | Chỉ cần dữ liệu gần nhất |
| DROP_LATEST | Loại phần tử mới đến | Ưu tiên giữ backlog hiện có |
| LATEST | Giữ giá trị mới nhất | Trạng thái snapshot, telemetry có thể thay thế |
| Bounded queue + reject | Từ chối khi hàng đợi đạt giới hạn | Command cần phản hồi quá tải rõ ràng |

Các chiến lược drop chỉ phù hợp khi nghiệp vụ chấp nhận mất một số cập nhật. Không dùng drop cho lệnh thanh toán, tạo đơn hoặc sự kiện cần bảo toàn nếu chưa có cơ chế lưu trữ/replay khác.

Cần theo dõi cả queue depth, số lần overflow, thời gian chờ trong queue và tuổi của message cũ nhất. Chỉ nhìn vào số lượng message đã xử lý sẽ không phát hiện được hàng đợi đang tăng nhanh.

## 8. Giới hạn prefetch và concurrency ở JMS listener

Trong JMS, consumer concurrency được cấu hình ở listener container. Spring hỗ trợ thuộc tính **concurrency** trên **@JmsListener** khi container tương ứng hỗ trợ cấu hình này.

Ví dụ:

~~~java
@Component
class OrderConsumer {

    @JmsListener(
        destination = "orders.commands.submit",
        concurrency = "3-10"
    )
    public void handle(SubmitOrderCommand command) {
        orderService.submit(command);
    }
}
~~~

Cấu hình **3-10** yêu cầu listener container duy trì concurrency trong khoảng từ ba đến mười consumer theo khả năng của container. Số lượng consumer thực tế, cách scale và việc cấp phát session phụ thuộc vào loại listener container và provider.

Khi tăng concurrency, cần kiểm tra:

- Database connection pool có đủ khả năng phục vụ các consumer không.
- Broker có đủ tài nguyên cho số consumer và prefetch đã cấu hình không.
- Acknowledgement và transaction được thực hiện ở thời điểm nào.
- Message có thể được giao lại khi listener lỗi hay không.
- Thứ tự xử lý có được yêu cầu bởi nghiệp vụ hay không.

Tăng số consumer có thể tăng throughput cho đến khi một dependency khác trở thành bottleneck. Sau điểm đó, tăng concurrency chỉ làm tăng tranh chấp và độ trễ.

Prefetch là số message broker có thể giao trước cho một consumer hoặc channel theo cấu hình provider. Prefetch quá lớn có thể khiến message nằm lâu trong bộ nhớ của consumer và phân phối không công bằng giữa các consumer. Prefetch quá nhỏ có thể làm giảm throughput do round trip. Hãy cấu hình theo broker cụ thể và kiểm thử với tải thực tế.

## 9. STOMP và WebSocket: kiểm soát tải ở broker và ứng dụng

Trong STOMP qua WebSocket, client có thể gửi message đến application destination và subscribe broker destination. Spring simple broker cung cấp khả năng cơ bản cho subscription và phát message, nhưng không phải mọi tính năng flow control, acknowledgement, prefetch hoặc persistence của một message broker chuyên dụng đều có sẵn.

Khi tải lớn, cần xem xét:

- Dùng broker relay tới broker chuyên dụng nếu cần khả năng mở rộng và quản lý queue.
- Cấu hình giới hạn kết nối, subscription và kích thước frame ở tầng transport/broker.
- Giới hạn số request mà application handler nhận.
- Dùng executor và task queue có giới hạn cho inbound/outbound channel khi phù hợp.
- Đặt giới hạn message size và kiểm tra payload trước khi deserialize sâu.
- Có chính sách khi client gửi nhanh hơn tốc độ xử lý.

Không giả định một prefix như /topic hoặc /queue tự tạo ra giới hạn tải hay semantics queue trong simple broker. Prefix chủ yếu là quy ước destination; hành vi thực tế phụ thuộc broker và cấu hình Spring.

## 10. Rate limiting và giới hạn tốc độ gửi

Concurrency limit kiểm soát số operation đang chạy; rate limit kiểm soát số operation bắt đầu trong một đơn vị thời gian.

Ví dụ, một API có thể xử lý tối đa 50 request đồng thời nhưng vẫn bị quá tải nếu một producer liên tục gửi 10.000 request mỗi giây và các request hoàn tất rất nhanh. Rate limiter giúp giới hạn tốc độ tiếp nhận theo chính sách.

Các thuật toán thường gặp:

- **Token bucket:** token được bổ sung theo tốc độ cố định; cho phép burst trong giới hạn dung lượng bucket.
- **Leaky bucket:** xử lý hoặc phát request theo tốc độ ổn định, làm phẳng burst.
- **Fixed window:** đếm request trong từng cửa sổ thời gian; đơn giản nhưng có thể tạo burst ở ranh giới hai cửa sổ.
- **Sliding window:** tính request trên cửa sổ trượt để giảm hiệu ứng ranh giới.

Rate limit có thể áp dụng theo API, tenant, user, IP hoặc loại message. Cần tránh chỉ dựa vào IP khi nhiều user chia sẻ NAT hoặc proxy.

Nếu dùng Resilience4j RateLimiter, hãy cấu hình limitForPeriod, limitRefreshPeriod và timeoutDuration phù hợp. Với hệ thống nhiều instance, limiter trong bộ nhớ của mỗi instance không tự tạo ra quota toàn cụm; cần cơ chế chia sẻ quota hoặc phân bổ quota theo instance.

Khi từ chối vì rate limit, trả lỗi có thể nhận biết được và có thể kèm thời gian retry phù hợp. Không retry ngay lập tức khi bị rate limit vì điều đó làm burst nặng hơn.

## 11. Chọn giới hạn từ năng lực thực tế

Không nên chọn concurrency chỉ dựa trên số CPU hoặc số thread mặc định. Hãy đo thời gian xử lý, mức sử dụng dependency và giới hạn tài nguyên.

Định luật Little cung cấp một quan hệ hữu ích:

\[
L = \lambda W
\]

Trong đó:

- \(L\) là số request trung bình đang ở trong hệ thống.
- \(\lambda\) là throughput trung bình, tính bằng request mỗi giây.
- \(W\) là thời gian trung bình một request ở trong hệ thống, tính bằng giây.

Ví dụ, nếu hệ thống xử lý 120 request/giây và thời gian xử lý trung bình là 0,15 giây:

\[
L = 120 \times 0.15 = 18
\]

Trung bình có khoảng 18 request đang hoạt động. Đây là mức trung bình theo giả định ổn định, không phải cấu hình concurrency tối đa được khuyến nghị. Khi chọn giới hạn, cần xem thêm p95/p99 latency, burst, khả năng downstream, queueing delay và headroom.

Một quy trình sizing:

1. Đo throughput và latency của từng loại operation.
2. Xác định dependency chậm nhất và connection pool tương ứng.
3. Đo CPU, heap, số thread, connection và queue depth khi tải tăng.
4. Tăng concurrency theo từng bước để tìm điểm throughput bắt đầu bão hòa.
5. Chọn giới hạn thấp hơn điểm bão hòa để giữ headroom.
6. Chạy burst test và soak test để phát hiện backlog tăng dần.
7. Xác định queue limit và thời gian chờ tối đa dựa trên deadline nghiệp vụ.

Ví dụ database có 40 connection không có nghĩa nên đặt 40 request toàn hệ thống nếu một request có thể mở nhiều connection hoặc có những operation khác cùng dùng pool. Phải tính tổng số connection có thể được giữ bởi mọi consumer.

## 12. Deadline và thời gian chờ trong hàng đợi

Một request có thể hết thời hạn nghiệp vụ trước khi đến lượt xử lý. Vì vậy, queue không chỉ cần giới hạn kích thước mà còn cần giới hạn thời gian chờ.

Ví dụ một request có deadline tổng ba giây:

~~~java
Mono<Result> result = admissionControl.submit(request)
    .timeout(Duration.ofSeconds(3));
~~~

Nếu admission control có hàng đợi, thời gian timeout cần bao gồm cả thời gian chờ permit và thời gian xử lý, hoặc hệ thống phải phân biệt rõ hai loại deadline.

Nên từ chối message đã quá hạn trước khi tiêu thụ tài nguyên đắt đỏ. Nếu message có timestamp hoặc deadline từ producer, cần xác định nguồn thời gian đáng tin cậy, xử lý clock skew và không tin dữ liệu thời gian do client tùy ý gửi nếu nó ảnh hưởng đến quyền truy cập tài nguyên.

Đối với message bền vững trong broker, việc từ chối có thể dẫn đến redelivery. Cần có chính sách retry, dead-letter và poison-message để một message không hợp lệ không bị giao lại vô hạn.

## 13. Kiểm thử giới hạn concurrency và buffer

Test cần xác nhận giới hạn thực sự được giữ khi có nhiều request, không chỉ kiểm tra một request thành công.

Ví dụ kiểm tra concurrency của flatMap:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class ConcurrencyTest {

    @Test
    void shouldLimitConcurrentInnerOperations() {
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maximum = new AtomicInteger();

        StepVerifier.withVirtualTime(() ->
                Flux.range(1, 20)
                    .flatMap(
                        item -> Mono.defer(() -> {
                            int current = active.incrementAndGet();
                            maximum.accumulateAndGet(current, Math::max);

                            return Mono.delay(Duration.ofSeconds(1))
                                .thenReturn(item)
                                .doFinally(signal ->
                                    active.decrementAndGet()
                                );
                        }),
                        4
                    )
            )
            .thenAwait(Duration.ofSeconds(5))
            .expectNextCount(20)
            .verifyComplete();

        assertTrue(maximum.get() <= 4);
        assertEquals(0, active.get());
    }
}
~~~

Test phát 20 phần tử và giới hạn bốn inner operation đồng thời. Virtual time giúp kiểm tra các operation có delay mà không phải đợi năm giây thật.

Đây là test cho concurrency trong một subscription. Nếu muốn kiểm thử limiter toàn cục, hãy tạo nhiều subscription đồng thời dùng chung limiter và xác nhận tổng số operation đang hoạt động không vượt giới hạn.

Các test khác nên bao gồm:

- Hết permit thì request bị reject với lỗi đúng.
- Permit được trả lại sau complete và error.
- Cancellation giải phóng permit khi operation thực sự dừng.
- Buffer đầy thì overflow đúng chính sách.
- Rate limiter cho phép đúng số request trong cửa sổ.
- Tenant A không chiếm hết quota của tenant B.
- Queue wait timeout xảy ra trước khi request hết deadline tổng.
- Retry không làm vượt concurrency hoặc rate limit đã cấu hình.

## 14. Quan sát và vận hành khi quá tải

Cần có metric để nhận biết receiver đang gần giới hạn:

- Số operation đang hoạt động và số permit còn lại.
- Số request bị từ chối do concurrency hoặc rate limit.
- Queue depth, queue wait time và tuổi của message cũ nhất.
- Buffer overflow, số message bị drop và số message được redeliver.
- Throughput theo route, destination, tenant và loại message.
- Latency p50, p95, p99 của handler và dependency.
- Số connection đang dùng trong database/HTTP pool.
- Timeout, retry, circuit breaker open và lỗi downstream.

Log nên có correlation ID, route hoặc destination đã chuẩn hóa, tenant ID nếu được phép và lý do reject. Không ghi payload nhạy cảm hoặc thông tin xác thực.

Khi hệ thống quá tải, phản ứng nên theo thứ tự:

1. Ngăn nhận thêm công việc vượt năng lực bằng admission control.
2. Giữ queue trong giới hạn và từ chối hoặc dead-letter message theo chính sách.
3. Giảm retry đồng loạt bằng backoff và jitter.
4. Bảo vệ dependency bằng bulkhead và circuit breaker.
5. Khôi phục backlog có kiểm soát sau khi dependency ổn định.
6. Xác minh throughput và latency trở về mức bình thường.

Không tự động tăng concurrency mỗi khi queue tăng. Nếu database đã bão hòa, tăng số worker có thể làm contention và latency xấu hơn.

## 15. Những lỗi thường gặp

| Lỗi | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ dùng flatMap concurrency để giới hạn toàn server | Mỗi subscription có giới hạn riêng; tổng tải vẫn tăng theo số client | Dùng limiter toàn cục hoặc bulkhead dùng chung |
| Cho rằng RSocket REQUEST_N giới hạn số request đồng thời | REQUEST_N điều khiển phần tử trong stream, không phải tổng số stream | Thêm admission control ở responder |
| Dùng buffer vô hạn | Heap tăng đến khi hệ thống mất ổn định | Dùng queue hữu hạn và overflow policy |
| Tăng consumer concurrency không đo downstream | Database hoặc HTTP pool bị quá tải | Sizing theo bottleneck và đo tải |
| Chỉ dùng rate limit | Request chậm có thể tích lũy dù tốc độ bắt đầu bị giới hạn | Kết hợp concurrency limit và timeout |
| Chỉ dùng concurrency limit | Burst lớn có thể liên tục thay thế request vừa hoàn tất | Thêm rate limit nếu cần |
| Dùng semaphore acquire blocking trên event loop | Chặn thread xử lý reactive | Dùng tryAcquire hoặc limiter bất đồng bộ |
| Trả permit khi task blocking vẫn chạy | Số tác vụ vật lý có thể vượt giới hạn | Quản lý cancellation và vòng đời task thật |
| Retry ngay khi quá tải | Tạo retry storm | Backoff, jitter và giới hạn retry |
| Một queue dùng cho mọi loại operation | Tác vụ chậm chặn tác vụ nhanh | Tách bulkhead và queue theo dependency |
| Không đo queue wait time | Message cũ có thể hết hạn trước khi xử lý | Theo dõi tuổi message và deadline |

## 16. Checklist trước khi đưa vào production

- [ ] Đã xác định giới hạn concurrency cho từng loại operation.
- [ ] Có admission control dùng chung khi cần giới hạn toàn receiver.
- [ ] Giới hạn theo dependency và tenant được cân nhắc.
- [ ] Không block thread reactive khi chờ permit.
- [ ] Cancellation và release permit có semantics rõ ràng.
- [ ] Buffer và queue có capacity hữu hạn.
- [ ] Overflow policy phù hợp với yêu cầu bảo toàn dữ liệu.
- [ ] Backpressure được dùng khi transport và publisher hỗ trợ.
- [ ] Không nhầm requestN với giới hạn số stream hoặc request đồng thời.
- [ ] Rate limit và concurrency limit được thiết kế riêng.
- [ ] Có timeout cho queue wait và operation deadline.
- [ ] JMS concurrency và broker prefetch phù hợp với năng lực downstream.
- [ ] STOMP/broker relay được kiểm tra theo semantics thực tế.
- [ ] Có metric active requests, queue depth, rejection, latency và downstream pool.
- [ ] Đã chạy burst, load và soak test.
- [ ] Có chính sách retry, dead-letter và idempotency khi reject hoặc redelivery.

## 17. Tài liệu tham khảo

- [Project Reactor Reference: Backpressure](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html) — cách tạo và tiêu thụ Publisher; demand và subscription.
- [Project Reactor API: Flux](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html) — flatMap, concatMap, limitRate và các operator backpressure.
- [Spring Framework Reference: RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html) — Request-Stream, Channel, responder và RSocket integration.
- [RSocket Protocol](https://rsocket.io/about/protocol/) — REQUEST_N và flow control trong protocol.
- [Spring Framework Reference: JMS](https://docs.spring.io/spring-framework/reference/integration/jms.html) — listener container và cấu hình concurrency.
- [Resilience4j](https://resilience4j.readme.io/docs/bulkhead) — bulkhead, concurrency isolation và rate limiting.
