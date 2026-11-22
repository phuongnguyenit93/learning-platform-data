# Backpressure từ downstream

Trong hệ thống Spring Kafka, consumer có thể đọc record nhanh hơn tốc độ mà database, HTTP API, hệ thống thanh toán hoặc dịch vụ nội bộ ở phía sau có thể xử lý. Khi đó, tăng concurrency hoặc retry liên tục không nhất thiết cải thiện throughput: ứng dụng có thể làm connection pool cạn kiệt, tăng timeout, gây retry storm và tạo thêm áp lực lên chính dependency đang suy yếu.

**Backpressure từ downstream** là cơ chế điều chỉnh tốc độ nhận và xử lý record Kafka dựa trên năng lực thực tế của hệ thống phụ thuộc. Mục tiêu không phải giữ consumer lag luôn bằng 0 bằng mọi giá; mục tiêu là **không nhận thêm công việc vượt quá khả năng xử lý an toàn**, đồng thời giữ consumer group ổn định, bảo toàn offset và tiếp tục được khi downstream hồi phục.

Trong Spring Kafka, các công cụ quan trọng gồm `MessageListenerContainer.pause()/resume()`, pause theo partition, `max.poll.records`, bounded concurrency, retry/backoff có kiểm soát, circuit breaker và cơ chế acknowledgment. Từng công cụ giải quyết một tầng khác nhau. Pause Kafka consumer không thay thế timeout của HTTP client, và một thread pool lớn cũng không thay thế giới hạn tải của database.

## 1. Downstream quá tải được biểu hiện như thế nào?

Một pipeline có thể hình dung như sau:

```text
Kafka topic
    |
    v
Spring Kafka consumer
    |
    v
@KafkaListener
    |
    +--> Database / connection pool
    |
    +--> Payment/Inventory HTTP API
    |
    +--> Worker queue / thread pool
    |
    v
Kết quả nghiệp vụ + commit offset
```

Nếu tốc độ record đến từ Kafka lớn hơn tốc độ downstream hoàn tất, phần công việc chưa hoàn thành phải nằm ở đâu đó: trong Kafka log, trong tập record đã poll, trong hàng đợi nội bộ, trong các HTTP request chờ kết quả hoặc trong database pool. **Nơi đặt backlog quyết định rủi ro**.

| Nơi tích lũy công việc | Biểu hiện | Nguy cơ chính |
|---|---|---|
| Kafka topic | Consumer lag tăng | Tăng độ trễ; chịu giới hạn retention và dung lượng broker |
| Tập record đã poll trong consumer | Thời gian giữa hai lần `poll()` dài | Vượt `max.poll.interval.ms`, bị rebalance |
| Hàng đợi trong ứng dụng | Queue depth và heap tăng | OOM, GC pause, mất task khi restart nếu không bền vững |
| HTTP/database in-flight | Latency, timeout và pool waiting tăng | Downstream bị bão hòa, lỗi lan truyền |
| Retry topic hoặc DLT | Backlog lỗi tăng nhanh | Cần thêm năng lực recovery và replay |

Đối với luồng có tải dao động, Kafka log thường là vùng đệm **bền vững và dễ kiểm soát hơn** so với một queue không giới hạn trong JVM. Chủ động để consumer lag tăng trong một khoảng thời gian có thể an toàn hơn cố giữ lag thấp bằng cách gửi hàng nghìn yêu cầu đồng thời tới một database đã quá tải.

## 2. Đo tốc độ đến, tốc độ xử lý và thời gian phục hồi

Gọi `λ` là tốc độ record đến, `μ` là tốc độ xử lý thành công bền vững của downstream, tính theo record/giây. Khi `λ > μ`, backlog tăng; khi `μ > λ`, hệ thống mới có khả năng giảm backlog.

```text
Backlog tăng mỗi giây ≈ max(0, λ - μ)

Ví dụ:
  Kafka nhận 1.200 records/giây
  Downstream xử lý 800 records/giây
  Backlog tăng khoảng 400 records/giây
  Sau một phút có thêm khoảng 24.000 records chờ
```

Đây chỉ là mô hình đơn giản: batching, partition distribution, retries và lỗi nghiệp vụ làm tốc độ thực tế biến động. Nhưng nó cho thấy một điều quan trọng: **pause không tạo ra năng lực downstream mới**. Pause giúp tránh quá tải lan rộng và giữ công việc ở Kafka; sau khi resume, muốn giảm backlog thì tổng năng lực xử lý phải lớn hơn tốc độ event đến.

Ngoài số record, cần tính **kích thước payload**, chi phí CPU, số query/transaction, thời gian giữ connection và hạn mức request của API. Hai record có cùng byte size có thể tiêu thụ năng lực downstream rất khác nhau. Vì vậy, backpressure nên dựa trên tín hiệu sức khỏe thật thay vì một ngưỡng lag cố định duy nhất.

## 3. Chọn tín hiệu phát hiện downstream saturation

Tín hiệu backpressure tốt thường đo năng lực gần điểm nghẽn nhất:

| Tín hiệu | Ý nghĩa | Lưu ý |
|---|---|---|
| HTTP `429 Too Many Requests` | Dependency đang áp dụng rate limit | Đọc `Retry-After` khi có; không retry ngay lập tức với cùng tốc độ |
| HTTP `503`/timeout tăng | Dịch vụ phụ thuộc có thể quá tải hoặc lỗi | Kết hợp latency, circuit breaker và kiểm tra root cause |
| Database pool active/max | Connection pool gần hết | Active cao liên tục có thể do query chậm hoặc transaction giữ lock |
| Queue occupancy | Task đang chờ gần dung lượng tối đa | Chỉ phù hợp nếu queue **bounded** và completion được theo dõi |
| In-flight request count | Số tác vụ đang chiếm tài nguyên | Phải đối chiếu với concurrency limit thực sự được downstream chịu đựng |
| p95/p99 latency | Tăng thời gian xử lý khi quá tải | Thường cần cảnh báo trước khi mọi request bắt đầu timeout |
| Circuit breaker state | Dependency đang bị cách ly sau tỷ lệ lỗi cao | Cần chính sách half-open và khôi phục có điều kiện |
| Consumer lag | Tốc độ xử lý thấp hơn tốc độ đến | **Là hậu quả**, không luôn là nguyên nhân của downstream saturation |

Ví dụ, pool 50 connection có 49 connection đang dùng và hàng chờ 500 request là dấu hiệu rõ ràng hơn việc chỉ thấy Kafka lag tăng. Ngược lại, Kafka lag cao có thể do một lần deploy chưa xong hoặc backlog cần backfill, trong khi database vẫn còn nhiều năng lực. Không nên pause thêm chỉ vì lag cao.

Nên đo tỷ lệ lỗi và latency theo một cửa sổ thời gian đủ ổn định. Một timeout đơn lẻ không nhất thiết đòi hỏi pause toàn bộ listener; nhưng nhiều `429`, latency p99 tăng và queue gần đầy cùng lúc có thể là tín hiệu cần giảm tải ngay.

## 4. Các tầng điều khiển backpressure

Không có một công tắc phù hợp cho mọi loại áp lực. Các phương án nên phối hợp theo mục tiêu:

| Cơ chế | Điều khiển gì? | Phù hợp khi nào? |
|---|---|---|
| `max.poll.records` | Số record trả về mỗi lần poll | Giới hạn lượng việc đang giữ trong vòng xử lý đồng bộ |
| Listener concurrency | Số consumer child containers có thể chạy song song | Cân bằng partition parallelism với năng lực downstream |
| Bounded worker pool / semaphore | Số tác vụ đồng thời trong ứng dụng | Ngăn dồn việc vào queue hoặc API vượt ngưỡng |
| Container `pause()`/`resume()` | Tạm ngừng fetch record mới cho listener | Downstream overload kéo dài hoặc cần chờ phục hồi |
| Pause theo partition | Chỉ ngừng partition cụ thể | Một tenant/key/partition tạo tải bất thường hoặc cần cô lập |
| Blocking retry/backoff | Thử lại record thất bại theo lịch | Lỗi tạm thời, cần giữ thứ tự trong partition |
| `@RetryableTopic` | Chuyển record sang retry topic | Retry dài mà không muốn giữ topic chính; chấp nhận thay đổi ordering |
| Circuit breaker/rate limiter | Giảm lời gọi tới downstream | Dependency có quota hoặc outage cần tránh retry storm |

**Admission control** là nguyên tắc chung: chỉ nhận thêm công việc khi có năng lực để hoàn tất, hoặc có vùng đệm bền vững rõ ràng. Nếu không thể nhận thêm công việc an toàn, giữ record ở Kafka thường tốt hơn enqueue vô hạn rồi commit offset sớm.

## 5. `pause()` và `resume()` trên Spring Kafka listener container

Spring Kafka cung cấp API ở mức listener container để yêu cầu pause và resume. Với container được quản lý bởi `@KafkaListener`, có thể lấy container thông qua `KafkaListenerEndpointRegistry` theo listener ID:

```java
@KafkaListener(
        id = "orderProcessor",
        topics = "orders",
        groupId = "order-service",
        containerFactory = "orderListenerContainerFactory")
public void consume(OrderCreated event) {
    orderService.processIdempotently(event);
}
```

Một component vận hành có thể gọi:

```java
@Component
public class OrderConsumerControl {

    private final KafkaListenerEndpointRegistry registry;

    public OrderConsumerControl(KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pause() {
        MessageListenerContainer container =
                registry.getListenerContainer("orderProcessor");
        if (container != null && container.isRunning()) {
            container.pause();
        }
    }

    public void resume() {
        MessageListenerContainer container =
                registry.getListenerContainer("orderProcessor");
        if (container != null && container.isRunning()) {
            container.resume();
        }
    }
}
```

Việc gọi API của container từ một thread điều phối được hỗ trợ; container sẽ thực hiện thao tác consumer an toàn trong lifecycle của nó. **Không gọi trực tiếp `KafkaConsumer.pause()` từ một thread HTTP hoặc scheduler tùy ý**: Kafka consumer không thread-safe.

Sau khi yêu cầu `pause()`, container thường hoàn thành các record đã nhận trong poll trước rồi mới áp dụng pause. Vì thế pause **không hủy công việc đang chạy** và có thể không có hiệu lực tức thì nếu một listener đang chặn lâu. Container có thể cung cấp các trạng thái như `isPauseRequested()` và `isConsumerPaused()` để phân biệt đã yêu cầu pause với việc Kafka consumer thực sự đã pause.

Từ Spring Kafka 2.9 có tùy chọn `pauseImmediate` để việc pause có hiệu lực sau record hiện tại, thay vì phải xử lý hết các record của lần poll trước; các record còn lại được container giữ để xử lý tiếp khi resume. Đây là một trade-off về độ trễ pause và bộ nhớ, cần xem version hỗ trợ và kiểm thử trước khi sử dụng.

## 6. Điều rất quan trọng: pause không được ngừng poll

Trong Kafka, `pause()` làm cho consumer không fetch record mới từ các partition được pause, **nhưng ứng dụng vẫn phải duy trì vòng `poll()`** để giữ consumer group membership và heartbeat. Spring Kafka listener container có cơ chế tiếp tục polling khi pause để không tự gây timeout group chỉ vì tạm giảm tải.

```text
Khi downstream quá tải:

Container.pause()
       |
       v
Consumer ngừng nhận record mới
       |
       v
Container vẫn poll theo lifecycle của Kafka
       |
       v
Giữ membership/heartbeat; chưa commit thêm record chưa xử lý
       |
       v
Downstream hồi phục -> Container.resume()
```

Đừng nhầm pause với `Thread.sleep(10 * 60_000)` trong `@KafkaListener`. Nếu listener chặn consumer thread quá thời hạn `max.poll.interval.ms`, Kafka có thể xem member không tiến triển, gây rebalance và redelivery. Pause chỉ bảo vệ membership khi **container còn cơ hội gọi poll**. Một HTTP call treo trong listener không tự biến thành non-blocking nhờ gọi `pause()`.

Đối với một listener xử lý batch lớn, pause có thể được thực hiện sau khi batch hiện tại đã xử lý xong. Nếu cần hạn chế thời gian xử lý trước khi poll tiếp theo, phải điều chỉnh `max.poll.records`, timeout downstream, retry budget và có thể chọn `pauseImmediate` phù hợp.

## 7. Backpressure tự động với hysteresis

Nếu chỉ pause khi queue occupancy vừa vượt 80% rồi resume ngay khi giảm xuống 79%, container có thể dao động pause/resume liên tục. **Hysteresis** dùng một ngưỡng cao để dừng nhận việc và một ngưỡng thấp để mở lại, tránh dao động khi tải dao động gần ranh giới.

Ví dụ:

```text
Queue usage >= 80%   -> yêu cầu PAUSE
Queue usage <= 40%   -> có thể RESUME
40% < queue < 80%    -> giữ trạng thái hiện tại

Circuit breaker OPEN -> giữ PAUSE dù queue đã giảm
Circuit breaker CLOSED và queue thấp -> có thể RESUME
```

Một chính sách minh họa trong Spring, với nguồn đo occupancy do ứng dụng cung cấp:

```java
public record DownstreamSnapshot(
        double queueUsage,
        double poolUsage,
        boolean circuitOpen) {

    public boolean shouldPause() {
        return circuitOpen || queueUsage >= 0.80 || poolUsage >= 0.90;
    }

    public boolean canResume() {
        return !circuitOpen && queueUsage <= 0.40 && poolUsage <= 0.60;
    }
}

public interface DownstreamLoadProbe {
    DownstreamSnapshot snapshot();
}

@Component
public class OrderBackpressureCoordinator {

    private final KafkaListenerEndpointRegistry registry;
    private final DownstreamLoadProbe probe;

    public OrderBackpressureCoordinator(
            KafkaListenerEndpointRegistry registry,
            DownstreamLoadProbe probe) {
        this.registry = registry;
        this.probe = probe;
    }

    @Scheduled(fixedDelayString =
            "${app.orders.backpressure.check-ms:1000}")
    public void adjust() {
        MessageListenerContainer container =
                registry.getListenerContainer("orderProcessor");
        if (container == null || !container.isRunning()) {
            return;
        }

        DownstreamSnapshot load = probe.snapshot();
        if (load.shouldPause() && !container.isPauseRequested()) {
            container.pause();
        }
        else if (load.canResume() && container.isPauseRequested()) {
            container.resume();
        }
    }
}
```

Mã trên minh họa **policy điều phối**, không phải implementation đầy đủ của `DownstreamLoadProbe`: ứng dụng phải lấy số liệu từ bounded queue, connection pool, bulkhead/circuit breaker hoặc API quota thực tế. Các giá trị `queueUsage` và `poolUsage` được giả định trong khoảng 0..1. Cần bật scheduling qua `@EnableScheduling` trong cấu hình Spring và tránh gọi probe chậm/chặn trong scheduler. Threshold cần được hiệu chỉnh bằng metric thật, không coi 80%/40% là mặc định của Spring Kafka.

Ở production nên bổ sung thời gian pause tối thiểu, thời gian load khỏe liên tục trước khi resume, event log thay đổi trạng thái, kiểm soát exception của probe và alert khi pause quá lâu. Nếu probe không truy cập được dependency, cần chính sách **fail-safe** rõ ràng: không coi lỗi lấy metric là bằng chứng downstream đã hồi phục.

## 8. Pause toàn container hay pause một partition?

Khi overload ảnh hưởng toàn bộ dependency (ví dụ database chung hết connection), pause cả container thường dễ hiểu. Khi tải được cô lập theo tenant hoặc một partition có record nặng, Spring Kafka có API **pause/resume theo partition** ở các phiên bản hỗ trợ.

```java
MessageListenerContainer container =
        registry.getListenerContainer("orderProcessor");

TopicPartition busyPartition = new TopicPartition("orders", 2);
container.pausePartition(busyPartition);

// Sau khi nguyên nhân được xử lý và có đủ năng lực:
container.resumePartition(busyPartition);
```

Ví dụ chỉ có ý nghĩa nếu container đang sở hữu partition liên quan; với listener concurrency lớn, container cha có thể phải định tuyến thao tác tới child container. API và semantics cụ thể phụ thuộc Spring Kafka version. Khi rebalance khiến ownership thay đổi, bộ điều phối cần cập nhật partition state, không tiếp tục giả định partition 2 luôn thuộc instance hiện tại.

Pause một partition **không tự phân phối lại partition đó cho một consumer khác**. Một consumer bị pause vẫn giữ assignment khi group còn ổn định; đó là điểm hữu ích để tránh tăng số lần rebalance, nhưng cũng có nghĩa throughput của partition bị pause vẫn bằng 0 cho đến khi resume hoặc ownership thay đổi vì lý do khác.

Nếu downstream là dịch vụ chung và tất cả partition đều gọi dependency ấy, pause chỉ partition tạo tải cao có thể không đủ. Nếu một tenant trên nhiều partition gây overload, phải dùng quota/admission control theo tenant ở tầng nghiệp vụ chứ không mặc định mỗi partition tương ứng một tenant.

## 9. `max.poll.records`: giới hạn lượng công việc nhận vào một vòng

Khi container pause, những record đã được `poll()` trả về có thể vẫn đang chờ xử lý trong vòng hiện tại. Vì vậy, nếu mỗi record cần gọi downstream lâu, giảm `max.poll.records` là bước bổ trợ quan trọng.

```properties
spring.kafka.consumer.enable-auto-commit=false
spring.kafka.consumer.max-poll-records=50
spring.kafka.consumer.properties[max.poll.interval.ms]=300000

spring.kafka.listener.ack-mode=record
```

Ví dụ một poll chứa 500 record, mỗi record mất 800 ms để hoàn tất thì thời gian xử lý có thể xấp xỉ 400 giây, vượt `max.poll.interval.ms` mặc định 300 giây. Nếu giới hạn poll ở 50 record, cùng tải đó chỉ cần khoảng 40 giây cho vòng xử lý trước khi quay lại poll, chưa kể overhead. Đây là ước lượng để lập ngân sách, không phải cam kết latency vì các request có tail latency và error retries khác nhau.

`max.poll.records` giới hạn số record được trả về qua mỗi lần `poll()`, **không giới hạn tổng byte mà Kafka client có thể fetch/cache nội bộ**. Đối với payload lớn, cần xem thêm `max.partition.fetch.bytes`, `fetch.max.bytes`, memory và kích thước batch. Đừng chỉ giảm số record rồi kết luận heap đã được kiểm soát.

Tăng `max.poll.interval.ms` giúp consumer có thêm thời gian hoàn tất vòng xử lý, nhưng có giá: member thực sự kẹt có thể giữ partition lâu hơn trước khi group phân bổ lại. Cần đặt giới hạn theo p99/worst-case của listener, không tăng vô hạn để che một dependency đã quá tải.

## 10. Bounded concurrency và bounded queue

Một anti-pattern là lấy record Kafka rồi đẩy sang `ExecutorService` hoặc queue không giới hạn:

```java
@KafkaListener(topics = "orders")
public void consume(OrderCreated event) {
    executor.execute(() -> orderService.process(event));
    // Method trả về: container có thể cho rằng record đã hoàn tất.
}
```

Nếu listener sử dụng ack mode tự động, method trả về trước khi tác vụ async hoàn tất có thể khiến offset được commit quá sớm. Process crash sau commit nhưng trước khi worker xử lý xong sẽ tạo nguy cơ **mất xử lý nghiệp vụ**. Nếu queue không giới hạn, nhiệm vụ chờ cũng có thể ăn hết heap.

Một mô hình nhận việc an toàn cần **giới hạn** số công việc đang chạy và công việc đang chờ. Ví dụ đặt semaphore 32 in-flight requests, queue capacity 100, HTTP timeout 5 giây và áp dụng pause khi vượt ngưỡng. Tuy nhiên, semaphore chỉ giới hạn lời gọi downstream nếu code **không chuyển record thành một background task rồi ack sớm**.

Có hai hướng triển khai:

1. **Listener đồng bộ, xử lý có giới hạn:** giữ công việc trên consumer thread; kiểm soát `max.poll.records`, timeout, retry và pause trước khi overload lan rộng. Đơn giản hơn về offset nhưng throughput có thể bị giới hạn bởi thời gian mỗi record.
2. **Async có tracking/ack:** đưa task sang bounded executor; chỉ acknowledge khi task hoàn tất bền vững, quản lý offset theo partition và thứ tự, backpressure khi in-flight tăng, xử lý kết quả failed futures. Cần dùng khả năng ack bất đồng bộ đúng theo Spring Kafka version và kiểm thử redelivery/rebalance.

Không gọi `BlockingQueue.put()` vô thời hạn bên trong consumer thread khi queue đầy: lời gọi đó lại tạo một poll timeout. Nếu admission control từ chối task, phải có một chiến lược bảo đảm record chưa được ack và sẽ được thử lại/giữ lại an toàn. Không âm thầm nuốt `RejectedExecutionException` rồi để listener kết thúc bình thường.

## 11. Ack và offset: không được xem queueing là processing thành công

Backpressure là vấn đề về **tốc độ**, còn acknowledgment là vấn đề về **tính đúng đắn tiến độ**. Một record chỉ nên được đánh dấu hoàn tất khi tất cả side effect bắt buộc đã được thực hiện hoặc khi record được recover bền vững theo chính sách đã định.

| Tình huống | Hành động offset đúng về nguyên tắc |
|---|---|
| Downstream xử lý thành công và side effect đã bền vững | Cho phép commit theo ack mode |
| Downstream trả `429` hoặc timeout tạm thời | Không ack như đã thành công; retry/backoff hoặc pause có kiểm soát |
| Payload không hợp lệ vĩnh viễn | Recover/DLT theo policy; chỉ tiến offset khi recovery thành công |
| Task async mới enqueue, chưa chạy | Không coi là đã xử lý xong |
| Side effect DB đã commit nhưng Kafka offset chưa commit | Có thể redeliver; dùng idempotent consumer/inbox |

Với `AckMode.RECORD`, container thường commit theo từng record đã được listener xử lý thành công. Với manual acknowledgment (`MANUAL`, `MANUAL_IMMEDIATE`), ứng dụng phải gọi `acknowledge()` đúng sau khi công việc hoàn tất. Trong xử lý async, ack theo thứ tự hoặc xử lý out-of-order cần cơ chế tương ứng của container; không giả định có thể commit một offset tùy ý rồi bỏ qua mọi offset trước nó.

Một số phiên bản Spring Kafka hỗ trợ `asyncAcks`, cho phép ghi nhận acknowledgment lệch thứ tự trong cùng poll nhưng container phải chờ các ack còn thiếu trước khi tiến. Điều này có thể làm consumer bị pause trong khi in-flight task chưa hoàn tất; cần bounded processing, xử lý task bị treo và đo các pending acknowledgments. Cơ chế này không thay thế việc xác minh dữ liệu đã được lưu bền vững.

## 12. Downstream báo lỗi: retry, pause hay DLT?

Khi dependency trả lỗi, chọn phản ứng theo **khả năng phục hồi của lỗi**:

| Tình huống | Phản ứng gợi ý |
|---|---|
| HTTP `429` với `Retry-After` | Giảm tốc, tôn trọng thời gian chờ; có thể pause và retry có kiểm soát |
| HTTP `503` tạm thời, database pool gần đầy | Backoff hữu hạn, pause theo tín hiệu quá tải, circuit breaker |
| Một record lỗi dữ liệu/schema không sửa được bằng retry | Không retry vô ích; gửi DLT/quarantine với metadata nguồn |
| Downstream outage kéo dài | Pause consumer hoặc dùng retry topic nếu ordering cho phép; cảnh báo theo thời gian outage |
| Business rule từ chối hợp lệ | Xử lý như kết quả nghiệp vụ, không đẩy DLT chỉ vì không thành công |

Không nên gửi **mọi record** sang DLT chỉ vì một database có outage dài. DLT dành cho record không thể xử lý theo policy, không phải nơi di chuyển toàn bộ tải từ consumer khi downstream tạm thời mất năng lực. Nếu dependency phục hồi sau 10 phút, việc giữ backlog tại Kafka và resume có kiểm soát có thể đơn giản hơn đẩy hàng triệu record vào DLT rồi replay.

Ngược lại, một record poison cố định có thể chặn progress nếu retry vô hạn. Phân loại not-retryable đúng và recover sang DLT giúp những record hợp lệ phía sau không bị kéo theo.

## 13. Kết hợp `DefaultErrorHandler` với container-pausing backoff

Nếu lỗi tạm thời cần backoff dài, `DefaultErrorHandler` có thể dùng một `BackOffHandler` hỗ trợ pause container để duy trì polling trong thời gian chờ. Spring Kafka cung cấp `ContainerPausingBackOffHandler` trong các phiên bản hỗ trợ, dùng để tránh việc consumer thread chỉ ngủ lâu đến mức vượt `max.poll.interval.ms`.

Ví dụ minh họa:

```java
@Bean
DefaultErrorHandler ordersErrorHandler(
        KafkaTemplate<Object, Object> dltTemplate,
        KafkaListenerEndpointRegistry registry) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(dltTemplate);

    BackOff backOff = new FixedBackOff(30_000L, 3L);

    DefaultErrorHandler handler = new DefaultErrorHandler(
            recoverer,
            backOff,
            new ContainerPausingBackOffHandler(registry));

    handler.addNotRetryableExceptions(
            InvalidOrderPayloadException.class);

    return handler;
}
```

Ở đây `InvalidOrderPayloadException` là class miền nghiệp vụ do ứng dụng định nghĩa; cần cấu hình serializer/ACL/partition DLT phù hợp và gắn `handler` vào đúng listener container factory. API constructor và xử lý backoff cần đối chiếu phiên bản Spring Kafka. `FixedBackOff(30_000L, 3L)` biểu diễn tối đa ba lần retry sau delivery đầu tiên đối với lỗi retryable, nếu không có reset policy làm thay đổi chu kỳ.

**Phân biệt hai mục tiêu:** một bộ điều phối `pause()/resume()` dựa vào metrics điều khiển **tải tổng thể**, còn `ContainerPausingBackOffHandler` là cách thực hiện **backoff cho record lỗi** trong error handler. Nếu cùng dùng, cần thiết kế rõ ai có quyền resume, tránh một controller gọi `resume()` trong khi cơ chế lỗi vẫn cần giữ container tạm dừng. Có thể chọn một chủ sở hữu pause duy nhất hoặc phối hợp trạng thái pause theo nhiều lý do trước khi resume.

## 14. `@RetryableTopic` và việc giải phóng topic chính

Non-blocking retry qua `@RetryableTopic` có thể phù hợp khi một record cần chờ lâu để downstream hồi phục nhưng service vẫn muốn xử lý các record khác trên topic chính.

```java
@RetryableTopic(
        attempts = "4",
        backoff = @Backoff(delay = 5_000, multiplier = 2.0),
        exclude = {InvalidOrderPayloadException.class},
        dltTopicSuffix = "-dlt")
@KafkaListener(topics = "orders", groupId = "order-service")
public void consume(OrderCreated event) {
    orderService.processIdempotently(event);
}
```

Một record lỗi được đưa qua retry topic theo topology mà Spring Kafka tạo. Topic chính có thể tiến tiếp thay vì giữ partition chờ từng lần retry. **Điều này có thể phá vỡ thứ tự xử lý theo key**: record đến sau hoàn tất trước record đang ở retry topic. Nếu downstream yêu cầu trạng thái tuần tự, hãy dùng state versioning, idempotency hoặc chọn blocking retry thay thế.

Non-blocking retry cũng không giải quyết quá tải **toàn hệ thống** nếu tất cả record đều gọi cùng một API đang bị rate limit. Nếu hầu hết record đều bị đẩy sang retry topics, traffic có thể quay trở lại cùng lúc tạo một đợt retry storm khác. Cần rate limiter, jitter/backoff phù hợp, circuit breaker, giới hạn throughput retry consumer và theo dõi backlog ở **cả topic chính lẫn retry topics**.

## 15. Concurrency, partition và năng lực downstream toàn cục

Một cài đặt `concurrency=8` có thể tạo tối đa tám consumer threads trong một instance, nhưng tổng tải downstream còn phụ thuộc **số instance, số partition và concurrency bên trong mỗi listener**.

Ví dụ có bốn application replicas, mỗi replica concurrency 5, mỗi record mở tối đa một HTTP request đồng bộ. Trong tình huống đủ partition và tất cả consumer đang xử lý, số request đồng thời có thể lên tới khoảng 20. Nếu mỗi listener lại chạy mười async tasks, áp lực tổng có thể tăng nhanh hơn nhiều.

```text
4 replicas × 5 consumer threads = tối đa 20 listener calls đồng thời

Nếu mỗi listener tạo 10 async requests:
  có thể tạo tới 200 requests đồng thời (nếu không giới hạn thêm)
```

Năng lực của downstream là **một giới hạn chung**, không phải mỗi replica tự được phép dùng trọn quota. Nếu API chỉ cho phép 100 request/giây toàn hệ thống, bốn replica cùng áp dụng rate limiter 100 request/giây có thể gửi tới 400 request/giây. Cần chia quota hoặc dùng distributed rate limiter khi quota thực sự mang tính toàn cục.

Pause container là hành động cục bộ trên instance/container được gọi; nó không gửi một yêu cầu dừng tới toàn bộ consumer group. Các replica khác có thể tiếp tục tiêu thụ và gọi downstream. Với overload toàn cục, phải có tín hiệu/chính sách nhất quán giữa các replica. Tránh để mọi replica cùng resume ồ ạt sau khi circuit breaker chuyển half-open; dùng ramp-up hoặc giới hạn concurrency từng bước.

## 16. Shutdown, rebalance và retry khi đang pause

Pause không đảm bảo partition sẽ ở trên cùng instance mãi mãi. Rolling deployment, mất mạng, thay đổi group membership hoặc rebalance vẫn có thể làm partition được revoke rồi assigned lại. Khi đó những record đã poll nhưng chưa commit có thể được giao lại.

Các hệ quả cần lưu ý:

- Pause là trạng thái điều khiển **trên container chạy trong JVM**, không phải một cờ bền vững lưu trong Kafka log.
- Khi restart, container sẽ khởi tạo lại; policy backpressure phải đánh giá downstream trước khi nhận quá nhiều tải.
- Khi shutdown, cần drain các công việc đã được nhận, ngừng nhận mới và commit offset đúng theo trạng thái hoàn tất.
- Sau rebalance, chỉ thao tác pause/resume những partition mà container thực sự đang sở hữu; quan sát callback/lifecycle khi cần.
- Nếu DB side effect thành công nhưng offset chưa commit trước shutdown, có thể redelivery; xử lý phải idempotent.

Trong quá trình deploy, tránh pause/resume liên tục vì health check hoặc HPA có thể đánh giá consumer sai. Hãy phân biệt **liveness** (process có thể hoạt động) với **readiness/capacity** (instance nên nhận thêm công việc hay không). Một consumer đang pause có chủ đích vì downstream quá tải không nhất thiết là process chết; tự restart mọi pod chỉ vì lag tăng có thể làm tải tồi tệ hơn.

## 17. Monitoring và alert để điều khiển an toàn

Backpressure cần được quan sát như một trạng thái vận hành có chủ đích, không phải lỗi ẩn sau việc consumer lag tăng. Dashboard tối thiểu nên theo dõi:

| Metric / tín hiệu | Giá trị chẩn đoán |
|---|---|
| Consumer lag theo topic/group/partition | Mức backlog đang chờ ở Kafka |
| Age of oldest unprocessed record | Độ trễ nghiệp vụ do backlog |
| Pause requested / consumer paused | Container đang chờ pause hay đã pause thực sự |
| Pause duration và pause count | Có tình trạng pause quá lâu hoặc dao động liên tục không? |
| Listener processing p95/p99 | Thời gian làm việc từng record/batch |
| In-flight requests và queue occupancy | Downstream còn bao nhiêu khả năng nhận thêm tải |
| HTTP 429/503, timeout rate | Dependency từ chối hoặc không thể xử lý thêm request |
| DB pool active/idle/pending | Thắt cổ chai connection và query |
| Time-between-poll max / rebalance | Consumer có nguy cơ vượt `max.poll.interval.ms` không? |
| Retry rate, retry-topic lag, DLT rate | Áp lực lỗi có di chuyển sang topology khác không? |

Không dùng event ID, offset hay request ID làm label metric vì cardinality cao. Lưu chúng trong log/tracing/audit có kiểm soát. Các log thay đổi trạng thái nên có listener ID, consumer group, reason, ngưỡng quan sát, thời điểm pause/resume, backlog và duration. Nếu nhiều yếu tố cùng khiến container pause, cần log rõ **lý do nào còn hiệu lực** trước khi resume.

Một cảnh báo tốt không chỉ là “lag lớn”; ví dụ: consumer đã pause hơn 15 phút, downstream p99 vẫn cao, oldest event age vượt SLO và retry rate tăng. Trái lại, pause ngắn giúp database hồi phục và lag giảm nhanh sau resume có thể là hành vi bình thường của backpressure.

## 18. Các tình huống lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Gọi `pause()` nhưng listener vẫn chạy thêm record | Container còn record từ poll trước; pause chưa có hiệu lực | Phân biệt pause requested/paused, giảm `max.poll.records`, cân nhắc `pauseImmediate` |
| Consumer bị rebalance khi “pause” | Listener chặn thread quá lâu hoặc code dùng `sleep()` thay vì container pause | Đảm bảo container vẫn poll, giới hạn thời gian xử lý và backoff |
| Resume xong downstream lại `429` hàng loạt | Không hysteresis, mở lại quá nhiều concurrent requests | Giảm tải ban đầu, thêm ramp-up, rate limiter và ngưỡng resume thấp |
| Queue tăng nhưng lag thấp | Listener đẩy task vào queue rồi ack/commit quá sớm | Thiết kế bounded queue và ack sau khi downstream hoàn tất |
| CPU/heap tăng mạnh khi overload | Queue không giới hạn, backlog nằm trong JVM | Đưa áp lực về Kafka; bounded admission và giảm poll batch |
| DLT tăng đột ngột khi DB outage | Retry budget quá ngắn hoặc phân loại mọi timeout là terminal | Tách transient failure khỏi poison record, pause/backoff phù hợp |
| Consumer đã pause nhưng group khác vẫn gọi API | Pause chỉ có tác dụng cục bộ, không điều khiển toàn cluster | Phối hợp global quota/health và rate limiter giữa replicas |
| Partition riêng vẫn lag sau recover | Partition pause chưa resume hoặc ownership đã đổi | Kiểm tra partition pause state, assignment/rebalance và điều phối resume |
| Record bị xử lý trùng sau restart | DB đã commit nhưng offset chưa commit | Inbox/idempotency và theo dõi offset recovery |
| Kafka lag không giảm sau khi downstream khỏe | Năng lực xử lý ≤ tốc độ event đến, concurrency thấp hoặc controller chưa resume | Đo input/process rates, kiểm tra trạng thái pause và scaling hợp lý |

Khi gặp sự cố, đối chiếu Kafka lag với in-flight/queue và downstream errors để xác định backlog đang bị giữ ở đâu. Chỉ tăng `max.poll.interval.ms` hoặc thêm pod theo phản xạ có thể làm hệ thống phụ thuộc sụp đổ nhanh hơn.

## 19. Kiểm thử backpressure từ downstream

Một bộ kiểm thử tích hợp có giá trị nên có Kafka broker, một downstream giả lập có thể đổi latency/quota, và quan sát committed offset cùng trạng thái container. Các kịch bản quan trọng:

1. **Downstream khỏe:** listener nhận và xử lý record bình thường, không pause vô cớ.
2. **Queue vượt ngưỡng cao:** controller yêu cầu pause; kiểm tra container đạt trạng thái paused và không nhận thêm batch mới.
3. **Queue ở vùng giữa hai ngưỡng:** giữ nguyên trạng thái, không pause/resume dao động.
4. **Downstream phục hồi:** queue giảm dưới ngưỡng thấp, circuit đóng; container resume và xử lý backlog.
5. **HTTP 429/Retry-After:** kiểm tra rate limit/backoff, không tạo request storm và không ack record thất bại.
6. **Một listener chặn lâu:** đo `max.poll.interval.ms`; xác nhận pause không che được lời gọi đồng bộ treo.
7. **Task async thất bại:** không được commit offset trước khi side effect hoàn tất, lỗi future không bị nuốt.
8. **Restart khi pause:** record chưa commit được giao lại theo Kafka offset; idempotency bảo vệ side effect.
9. **Rebalance khi in-flight còn nhiều:** partition ownership được cập nhật, không xử lý tiếp một cách thiếu kiểm soát.
10. **DLT và retry:** permanent error được recover đúng; transient outage không đẩy toàn bộ backlog vào DLT ngoài chính sách.
11. **Multi-replica:** tổng request rate không vượt quota toàn cục khi các instance cùng resume.
12. **Backlog lớn:** có thể bắt kịp tải đến sau khi downstream phục hồi, không xảy ra heap spike.

Trong kiểm thử, cần đo cả **Kafka side** (topic, partition, committed offset, lag) và **downstream side** (request count, completion, timeout, unique event ID). Chỉ quan sát trạng thái `isConsumerPaused()` mà không xác minh record chưa bị mất hoặc commit sớm là chưa đủ.

## 20. Runbook khi downstream quá tải

Một quy trình ứng phó tại production có thể đi theo thứ tự:

1. **Xác định phạm vi:** cluster, topic, consumer group, listener ID, dependency nào đang lỗi, số instance bị ảnh hưởng.
2. **Tìm điểm nghẽn:** đo pool usage, queue depth, 429/503, latency và error rate; phân biệt lỗi hệ thống với poison record.
3. **Giảm áp lực:** pause container/partition phù hợp hoặc kích hoạt circuit/rate limiter; không giữ consumer thread bằng `sleep()` dài.
4. **Bảo vệ offset:** xác minh acknowledgment chỉ xảy ra sau khi side effect hoặc recovery thành công; duy trì idempotency.
5. **Giảm in-flight:** hạn chế queue, concurrency, `max.poll.records` và timeout downstream nếu cần.
6. **Sửa dependency:** phục hồi database/API, điều chỉnh pool/index/quota hoặc rollback bản phát hành lỗi.
7. **Đánh giá năng lực phục hồi:** bảo đảm tốc độ xử lý khi resume có thể vượt tốc độ event đến nếu muốn giảm backlog.
8. **Resume có kiểm soát:** chờ các tín hiệu khỏe đủ lâu, mở tải dần; không mở lại tất cả replica với công suất tối đa cùng lúc.
9. **Theo dõi sau resume:** lag, oldest age, p99, request errors, retry-topic/DLT backlog và rebalance phải có xu hướng an toàn.
10. **Đóng sự cố:** ghi lại ngưỡng, lý do pause, duration, dữ liệu đã hồi phục, số record còn chờ và hành động phòng ngừa.

Không reset consumer group offset để “giảm lag” khi chưa có kế hoạch xử lý dữ liệu; reset tiến có thể bỏ qua record, còn reset lùi có thể tạo duplicate. Không tăng retention/partition hay concurrency như một cách chữa tức thời nếu chưa biết năng lực downstream mới được bổ sung ở đâu.

## 21. Nguyên tắc thiết kế production

1. Backpressure là điều tiết **tốc độ nhận việc** theo năng lực downstream, không phải cố xóa mọi consumer lag.
2. Ưu tiên giữ backlog bền vững tại Kafka hơn là tạo queue không giới hạn trong JVM.
3. Chọn tín hiệu overload từ queue, pool, latency, 429/503 và circuit breaker; không dựa đơn độc vào lag.
4. Dùng `MessageListenerContainer.pause()/resume()` qua container API, không thao tác `KafkaConsumer` từ thread khác.
5. Pause chỉ an toàn cho group membership khi container vẫn tiếp tục poll; listener đang chặn phải có timeout riêng.
6. Dùng hysteresis và thời gian hồi phục ổn định để tránh pause/resume liên tục.
7. Phối hợp pause với `max.poll.records`, bounded concurrency và memory limits để tránh nhận quá nhiều record trước khi pause có hiệu lực.
8. Ack chỉ sau khi downstream xử lý thành công hoặc recoverer hoàn tất bền vững; async enqueue không phải hoàn tất nghiệp vụ.
9. Phân biệt lỗi tạm thời và lỗi vĩnh viễn khi chọn retry, pause hay DLT; tránh retry storm và DLT storm.
10. Tính tổng năng lực/giới hạn trên **mọi replica**, không mặc định rate limit mỗi pod là rate limit toàn hệ thống.
11. Thiết kế idempotency cho redelivery sau rebalance, restart hoặc commit offset thất bại.
12. Quan sát pause duration, poll interval, lag, oldest event age và sức khỏe downstream; kiểm thử recovery như một failure mode thực sự.

**Kết luận:** backpressure từ downstream là một phần cốt lõi của vận hành Spring Kafka đáng tin cậy. Consumer cần biết **khi nào nên ngừng lấy thêm việc**, **khi nào an toàn để nhận lại**, và **record nào thực sự đã hoàn tất trước khi commit offset**. Khi kết hợp pause/resume vẫn duy trì polling, giới hạn in-flight, timeout, retry có kiểm soát, idempotency và quan sát theo SLO, hệ thống có thể chịu được các đợt quá tải của database/API mà không biến chúng thành mất dữ liệu, duplicate không kiểm soát hoặc consumer group rebalance liên tục.
