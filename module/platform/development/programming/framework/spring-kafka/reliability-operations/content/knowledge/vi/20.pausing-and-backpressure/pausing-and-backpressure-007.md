# Giới hạn tốc độ xử lý

Trong hệ thống Spring Kafka, khả năng **đọc nhanh** từ Kafka không đồng nghĩa với khả năng **xử lý nhanh và an toàn**. Kafka có thể lưu hàng triệu record để consumer đọc dần, nhưng database, REST API, hệ thống thanh toán hoặc tài nguyên tính toán mà listener sử dụng thường có giới hạn riêng. Nếu consumer lấy và xử lý nhiều record hơn mức một dependency chịu được, hệ thống có thể gặp timeout, connection pool cạn, lỗi 429/503 và retry storm. Kết quả là độ trễ tăng dù số consumer hoặc concurrency đã được nâng lên.

**Giới hạn tốc độ xử lý (rate limiting)** là cách khống chế số thao tác nghiệp vụ được thực hiện trong một đơn vị thời gian hoặc số thao tác đồng thời đang chạy. Trong chương **Pause và backpressure**, rate limiting phải được xem cùng với pause/resume, giới hạn in-flight, consumer lag và khả năng phục hồi khi downstream quá tải.

Mục tiêu không phải làm Kafka chậm đi bằng mọi giá, mà là **bảo vệ hệ thống phụ thuộc và giữ một tốc độ xử lý bền vững**, không mất record, không commit offset trước khi nghiệp vụ hoàn tất và không làm consumer mất quyền sở hữu partition vì thời gian xử lý quá dài.

## 1. Tại sao consumer cần được giới hạn tốc độ?

Giả sử một consumer group đọc topic payment.requests với tốc độ trung bình 1.200 record/giây. Mỗi record gọi một API thanh toán. API chỉ tiếp nhận bền vững khoảng 700 request/giây.

Nếu không kiểm soát:

    Kafka: 1.200 records/s
              |
              v
    12 consumer threads
              |
              v
    Payment API: capacity 700 req/s
              |
              +--- HTTP 429 / 503
              +--- timeout và queue tăng
              +--- nhiều lần retry
              +--- latency lớn hơn

Việc nâng concurrency từ 12 lên 24 consumer không làm API mạnh hơn; nó có thể khiến sự cố nghiêm trọng hơn.

Khi đặt một giới hạn tổng khoảng 600–700 thao tác/giây, service có thể hoạt động ổn định hơn:

    Kafka: 1.200 records/s
              |
              v
    Consumer + rate limiter: tối đa 650 API calls/s
              |
              v
    Payment API: capacity 700 req/s
              |
              v
        Xử lý ổn định

Nhưng rate limiting **không xóa backlog**. Nếu dữ liệu tiếp tục vào nhanh hơn tốc độ xử lý, consumer lag vẫn tăng. Hệ thống phải có kế hoạch về retention, thời gian chờ nghiệp vụ và biện pháp giảm tải từ producer hoặc scale dependency.

## 2. Phân biệt rate limit, concurrency limit và backpressure

Ba khái niệm này liên quan nhưng không đồng nhất:

| Cơ chế | Giới hạn điều gì? | Ví dụ |
|---|---|---|
| Rate limit | Số thao tác mỗi đơn vị thời gian | Tối đa 200 request/giây |
| Concurrency limit | Số thao tác đang chạy cùng lúc | Tối đa 20 HTTP request in-flight |
| Backpressure | Cơ chế phản hồi khi downstream không theo kịp | Pause consumer khi queue vượt ngưỡng |
| Batch size limit | Số record hoặc byte mỗi lần đọc/xử lý | Tối đa 100 record trong một poll |
| Retry backoff | Khoảng nghỉ giữa các lần thử lại sau lỗi | Chờ 1, 2, 4 giây |
| Autoscaling | Tăng hoặc giảm số consumer instance | 2 pod thành 4 pod |

Một dependency có thể chịu được 1.000 request/giây nhưng chỉ tối đa 50 request đồng thời. Khi mỗi request mất 200 ms, concurrency và rate giới hạn nhau theo quan hệ gần đúng:

    Throughput <= ConcurrentRequests / AverageRequestDuration

Ví dụ 50 request đồng thời, mỗi request mất 0,2 giây, throughput tối đa lý thuyết khoảng 250 request/giây nếu không có pipeline hoặc overhead bổ sung.

Muốn hệ thống ổn định, có thể phải dùng **cả rate limit và concurrency limit**. Chỉ giới hạn số request/giây không ngăn một đợt request chậm tồn tại quá lâu và chiếm hết connection pool.

## 3. Kafka consumer có tự cung cấp rate limit nghiệp vụ không?

Kafka consumer có các tham số giúp điều chỉnh lượng dữ liệu được fetch và nhịp poll, nhưng chúng không phải một bộ giới hạn chính xác số side effect nghiệp vụ mỗi giây.

Một số cấu hình:

| Tham số | Tác dụng chính | Có phải giới hạn records/second tuyệt đối? |
|---|---|---|
| max.poll.records | Số record tối đa trả về trong một lần poll | Không |
| fetch.min.bytes | Số byte broker cố gắng gom trước khi trả fetch | Không |
| fetch.max.wait.ms | Thời gian broker có thể chờ để gom fetch | Không |
| max.partition.fetch.bytes | Số byte fetch tối đa cho mỗi partition theo cấu hình | Không |
| concurrency (Spring Kafka) | Số consumer con xử lý song song | Không |
| idleBetweenPolls (Spring Kafka) | Khoảng idle giữa các lần poll | Không |
| pause/resume | Tạm dừng/tiếp tục fetch từ các partition | Không, nhưng dùng được để backpressure |

Ví dụ max.poll.records=100 chỉ có nghĩa mỗi poll trả về nhiều nhất 100 record; consumer vẫn có thể gọi poll liên tục nhiều lần trong một giây. Ngược lại, đặt max.poll.records=1 không bảo đảm listener chỉ xử lý một record mỗi giây.

Nếu mục tiêu là bảo vệ API có quota request/giây, rate limiter phải đặt tại **điểm thực hiện request**, nơi có thể đo đúng thao tác bị giới hạn.

## 4. Chọn đơn vị đo trước khi đặt giới hạn

Không phải workload nào cũng nên giới hạn theo số record.

Các cách đo phổ biến:

- **Records/second:** phù hợp khi mỗi record có chi phí xử lý gần như nhau.
- **Requests/second:** phù hợp khi mỗi record gọi một hoặc nhiều API; limiter phải tính số lần gọi thực tế.
- **Bytes/second:** hữu ích khi record kích thước rất khác nhau và network/serialization là bottleneck.
- **Transactions/second:** phù hợp khi dependency giới hạn số DB transaction.
- **Concurrent requests:** phù hợp khi latency không ổn định và connection pool là giới hạn.
- **Weighted tokens:** mỗi record tiêu thụ số token tương ứng độ nặng dự kiến.

Ví dụ một record OrderCreated tạo một lời gọi API, trong khi OrderSettled tạo năm lời gọi. Giới hạn 100 record/giây không đồng nghĩa giới hạn 100 API request/giây.

Trước khi chọn cấu hình, hãy xác định rõ tài nguyên phải bảo vệ và đơn vị quota thực tế của nó.

## 5. Giới hạn theo consumer, pod hay toàn consumer group?

Đây là một quyết định kiến trúc quan trọng.

Giả sử có bốn pod, mỗi pod chạy concurrency=3:

    Pod A: 3 consumer threads
    Pod B: 3 consumer threads
    Pod C: 3 consumer threads
    Pod D: 3 consumer threads

Nếu **mỗi pod** có một rate limiter chung tối đa 50 request/giây, tổng mức tải danh nghĩa là:

    4 pods x 50 req/s = 200 req/s

Nếu **mỗi consumer thread** tạo một limiter 50 request/giây, tổng mức tải danh nghĩa có thể thành:

    4 pods x 3 threads x 50 req/s = 600 req/s

Nếu API bên ngoài chỉ cho phép 200 request/giây cho **toàn ứng dụng**, phương án thứ hai có thể vi phạm quota dù mỗi limiter riêng lẻ đều hoạt động đúng.

| Phạm vi | Ưu điểm | Rủi ro |
|---|---|---|
| Per record handler | Dễ kiểm soát trong logic xử lý | Dễ tạo limiter mới sai cách, không giới hạn chung |
| Per consumer thread | Cô lập từng luồng | Tổng quota tăng theo concurrency |
| Per pod/JVM | Đơn giản, dùng singleton limiter | Tổng quota tăng theo số replica |
| Per tenant/key | Công bằng giữa nhóm người dùng | Cần state/quota riêng và xử lý key cardinality |
| Global/distributed | Bảo vệ quota chung cho toàn cluster | Cần service phối hợp, độ trễ mạng và chiến lược khi limiter lỗi |

Hãy xác định quota của dependency là theo credential, tenant, node hay toàn hệ thống, rồi đặt limiter tương ứng. Đừng nhân nhầm quota khi autoscaler tăng số pod.

## 6. Cách 1: Giới hạn request trong listener bằng rate limiter

Với một số consumer và dependency cần quota request/giây đơn giản, có thể dùng Guava RateLimiter ở dạng **singleton bean** trong mỗi JVM.

Ví dụ cấu hình:

~~~java
import com.google.common.util.concurrent.RateLimiter;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ConsumerRateLimitConfiguration {

    @Bean
    RateLimiter paymentApiRateLimiter(
            @Value("${app.payment.max-requests-per-second:40}")
            double permitsPerSecond) {

        return RateLimiter.create(permitsPerSecond);
    }
}
~~~

Listener:

~~~java
import com.google.common.util.concurrent.RateLimiter;
import org.springframework.kafka.annotation.KafkaListener;
import org.springframework.stereotype.Component;

@Component
public class PaymentRequestListener {

    private final RateLimiter paymentApiRateLimiter;
    private final PaymentGateway paymentGateway;

    public PaymentRequestListener(
            RateLimiter paymentApiRateLimiter,
            PaymentGateway paymentGateway) {

        this.paymentApiRateLimiter = paymentApiRateLimiter;
        this.paymentGateway = paymentGateway;
    }

    @KafkaListener(
        id = "paymentRequestsListener",
        topics = "payment.requests",
        groupId = "payment-service"
    )
    public void consume(PaymentRequested event) {

        // Mọi consumer thread trong JVM chia sẻ cùng limiter bean.
        paymentApiRateLimiter.acquire();

        // Side effect phải idempotent theo event ID.
        paymentGateway.charge(
            event.paymentId(),
            event.amount(),
            event.eventId()
        );
    }
}
~~~

Cần khai báo dependency Guava phù hợp với nền tảng build của dự án. PaymentRequested và PaymentGateway là các kiểu nghiệp vụ minh họa.

Điểm đáng chú ý:

1. RateLimiter bean là singleton theo mặc định trong Spring, nên các listener thread của cùng ứng dụng chia sẻ quota.
2. acquire() **có thể block** để chờ permit; đây là backpressure ngay tại consumer thread.
3. acquire() giới hạn **số lần bắt đầu gọi API**, không bảo đảm số lần xử lý thành công.
4. Nếu có nhiều pod, mỗi pod vẫn có một quota riêng; cần chia quota hoặc dùng distributed limiter.
5. Rate limiter kiểu token/leaky bucket có thể cho phép một số burst ngắn; không nhầm tốc độ trung bình với giới hạn cứng theo từng cửa sổ nhỏ.

**Quan trọng:** không tạo RateLimiter mới bên trong mỗi lần gọi consume(), vì điều đó làm trạng thái quota bị reset liên tục và gần như vô hiệu hóa rate limit.

## 7. Rủi ro khi acquire() block consumer quá lâu

RateLimiter.acquire() đơn giản và phù hợp với giới hạn không quá thấp, nhưng consumer phải poll đủ thường xuyên để duy trì membership.

Giả sử:

- max.poll.records=500.
- Listener xử lý trung bình 20 record/giây vì phải chờ permit và API.
- Một poll có thể trả 500 record.
- Thời gian xử lý toàn bộ tập record gần đúng là 25 giây, chưa kể retry và I/O.

Nếu quota giảm còn 1 record/giây, cùng 500 record có thể cần hơn 8 phút, vượt max.poll.interval.ms mặc định thường gặp là 5 phút. Consumer có thể mất assignment, rebalance và xử lý lại record do offset chưa commit.

Một quy tắc ước lượng:

    PollProcessingTime ~= RecordsPerPoll / EffectiveRecordsPerSecond
                          + AdditionalProcessingAndRetryTime

Đặt max.poll.records, rate và timeout sao cho thời gian xử lý **trong trường hợp xấu hợp lý** còn đủ biên dưới max.poll.interval.ms.

Ngoài ra, các consumer thread trong cùng pod cùng chia sẻ limiter, nên mỗi thread không nhất thiết được cấp permit đều nhau. Nếu muốn fairness theo partition hoặc tenant, cần chính sách lập lịch/quota riêng.

## 8. Tinh chỉnh max.poll.records để hỗ trợ rate limit

Spring Boot:

~~~yaml
spring:
  kafka:
    consumer:
      enable-auto-commit: false
      properties:
        max.poll.records: 50
        max.poll.interval.ms: 300000
    listener:
      concurrency: 2
      ack-mode: record
~~~

max.poll.records=50 chỉ giới hạn số record mỗi poll. Khi kết hợp với limiter, nó giúp đặt trần lượng công việc mà mỗi consumer thread có thể phải xử lý trước khi quay lại poll.

Ví dụ nếu một consumer có thể đạt 10 record/giây, xử lý 50 record cần khoảng 5 giây cộng thời gian I/O. Nếu downstream chậm hơn, hãy giảm batch size hoặc thay đổi chính sách pause thay vì để listener block nhiều phút.

Đừng giảm max.poll.records xuống 1 một cách máy móc. Poll quá thường xuyên có thể làm tăng overhead và giảm throughput. Hãy đo records-consumed-rate, processing duration, poll interval và commit latency trước khi chọn giá trị.

## 9. Cách 2: idleBetweenPolls trên Spring Kafka container

Spring Kafka cung cấp cấu hình **idleBetweenPolls** trên ContainerProperties để thêm khoảng chờ giữa các lần consumer poll. Đây là cách hạ nhịp tiêu thụ ở mức container.

Ví dụ:

~~~java
@Bean
ConcurrentKafkaListenerContainerFactory<String, OrderEvent>
ordersListenerFactory(
        ConsumerFactory<String, OrderEvent> consumerFactory) {

    ConcurrentKafkaListenerContainerFactory<String, OrderEvent> factory =
            new ConcurrentKafkaListenerContainerFactory<>();

    factory.setConsumerFactory(consumerFactory);
    factory.getContainerProperties().setIdleBetweenPolls(500L);

    return factory;
}
~~~

Giá trị 500L là milliseconds. Khi container chờ khoảng này giữa các lần poll, throughput có thể giảm nếu workload phụ thuộc tốc độ poll.

Tuy nhiên:

- **Không phải quota 2 record/giây.** Một poll có thể trả nhiều record.
- Nếu có nhiều consumer thread, mỗi consumer có nhịp poll riêng.
- Với traffic thưa, khoảng idle có thể tăng latency không cần thiết.
- Với listener processing lâu, khoảng chờ phải phối hợp với max.poll.interval.ms.
- Container có thể điều chỉnh khoảng idle để tuân theo giới hạn thời gian poll của consumer; chi tiết phụ thuộc phiên bản.

idleBetweenPolls phù hợp khi muốn giảm nhịp poll đơn giản, không phải khi cần bảo đảm chính xác số HTTP calls/giây trên toàn cluster.

## 10. Cách 3: Pause/resume khi downstream quá tải

Nếu database hoặc API đang quá tải rõ rệt, một số hệ thống không nên tiếp tục nhận việc mới dù vẫn chưa đạt quota trung bình. Khi đó có thể **pause container** và resume sau khi dependency phục hồi.

Spring Kafka có API MessageListenerContainer.pause() và resume(). Có thể truy cập container qua KafkaListenerEndpointRegistry bằng listener ID.

~~~java
import org.springframework.kafka.config.KafkaListenerEndpointRegistry;
import org.springframework.kafka.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public class ConsumerFlowControl {

    private final KafkaListenerEndpointRegistry registry;

    public ConsumerFlowControl(
            KafkaListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    public void pausePayments() {
        MessageListenerContainer container =
                registry.getListenerContainer("paymentRequestsListener");

        if (container != null) {
            container.pause();
        }
    }

    public void resumePayments() {
        MessageListenerContainer container =
                registry.getListenerContainer("paymentRequestsListener");

        if (container != null) {
            container.resume();
        }
    }
}
~~~

Container ID phải trùng với id trên @KafkaListener. Đừng giả định phương thức tìm container luôn trả về non-null; một listener có thể chưa được đăng ký, bị xóa hoặc không chạy.

**Pause không giống stop.** Khi các partition bị pause, Spring Kafka container vẫn duy trì poll phù hợp để consumer tiếp tục tham gia group và gửi heartbeat. Mục tiêu là ngừng nhận record mới từ partition đã pause mà không cố ý rời consumer group.

Dù vậy, pause không phải lời hứa dừng tức thì mọi listener đang chạy. Các record đã poll và task in-flight có thể còn xử lý. Nếu cần xử lý hành vi chính xác ở ranh giới record, xem pauseImmediate.

## 11. pauseImmediate và các record đã poll

Khi gọi pause() trên Spring Kafka container, yêu cầu pause thường có hiệu lực tại điểm an toàn của vòng poll. Với record listener, các record đã được poll trước đó có thể được xử lý tiếp trước khi container thực sự pause.

Ở các phiên bản Spring Kafka hỗ trợ, ContainerProperties có thuộc tính **pauseImmediate**:

~~~java
factory.getContainerProperties().setPauseImmediate(true);
~~~

Với chế độ này, sau khi nhận yêu cầu pause, container có thể tạm dừng xử lý sau record hiện tại, giữ lại các record đã được poll nhưng chưa giao cho listener để tiếp tục sau resume.

Đây là lựa chọn hữu ích khi dependency bắt đầu quá tải và bạn muốn ngừng đưa thêm record tới listener sớm hơn.

Cần hiểu rõ:

- pauseImmediate không hủy side effect đã thực hiện.
- Nó không ngắt cưỡng bức record đang chạy.
- Nó không đồng nghĩa với commit offset của toàn bộ dữ liệu đã poll.
- Record còn giữ lại cần được xử lý sau resume theo hành vi của container.
- Nếu process crash, khả năng replay vẫn phụ thuộc committed offset và Kafka retention.

Hãy kiểm tra API và semantics của Spring Kafka version dự án đang dùng; không dùng cấu hình phiên bản mới trên dependency cũ mà không xác nhận hỗ trợ.

## 12. Pause theo partition thay vì toàn listener

Một số tình huống chỉ một partition hoặc một tenant bị nghẽn. Nếu pause toàn container, các partition khỏe mạnh cũng bị dừng.

Spring Kafka hiện đại hỗ trợ request pause/resume theo TopicPartition thông qua API của listener container:

~~~java
TopicPartition partition =
        new TopicPartition("payments", 3);

MessageListenerContainer container =
        registry.getListenerContainer("paymentRequestsListener");

if (container != null) {
    container.pausePartition(partition);
}

// Khi điều kiện phục hồi đã thỏa:
if (container != null) {
    container.resumePartition(partition);
}
~~~

Cần bảo đảm topic/partition thực sự liên quan tới container, vì assignment có thể chuyển consumer khác sau rebalance. Trong một số phiên bản, các API pausePartition/resumePartition đã được bổ sung sau API pause/resume toàn container.

Dừng một partition không làm Kafka dời record sang partition khác. Key/ordering và ownership vẫn tuân theo assignment hiện tại. Nếu partition đang bị pause vẫn nhận thêm dữ liệu từ producer, lag của partition đó sẽ tiếp tục tăng.

Pause theo partition hữu ích khi có quy tắc xử lý độc lập theo partition. Nếu yêu cầu quota theo tenant nhưng nhiều tenant chung một partition, pause partition có thể làm chậm cả những tenant khỏe mạnh.

## 13. Tạo một controller backpressure theo ngưỡng

Có thể xây một bộ điều khiển định kỳ dựa trên tín hiệu năng lực downstream.

Giả sử service đọc metric queue depth từ một dependency:

    queue depth >= 1.000  -> yêu cầu pause
    queue depth <=   300  -> yêu cầu resume
    ở giữa               -> giữ nguyên trạng thái

Hai ngưỡng khác nhau tạo **hysteresis**, tránh dao động pause/resume liên tục khi queue quanh một giá trị duy nhất.

Ví dụ dạng interface và scheduling:

~~~java
public interface DownstreamCapacitySignal {
    long pendingOperations();
}

@Component
@EnableScheduling
public class PaymentBackpressureController {

    private final DownstreamCapacitySignal capacity;
    private final ConsumerFlowControl flowControl;
    private boolean requestedPause;

    public PaymentBackpressureController(
            DownstreamCapacitySignal capacity,
            ConsumerFlowControl flowControl) {
        this.capacity = capacity;
        this.flowControl = flowControl;
    }

    @Scheduled(fixedDelay = 2_000L)
    public synchronized void evaluate() {
        long pending = capacity.pendingOperations();

        if (!requestedPause && pending >= 1_000L) {
            flowControl.pausePayments();
            requestedPause = true;
        }
        else if (requestedPause && pending <= 300L) {
            flowControl.resumePayments();
            requestedPause = false;
        }
    }
}
~~~

Đây là ví dụ điều khiển **trong một instance**, không phải bộ điều phối quota toàn cluster. Cấu hình @EnableScheduling cần được đặt ở một configuration phù hợp với kiến trúc ứng dụng; ví dụ dùng trên component để minh họa rằng scheduling phải được bật.

Trong triển khai thực tế:

- Nên xác nhận container tồn tại và đang chạy trước khi ghi nhận trạng thái requestedPause.
- Có thể đọc isPauseRequested hoặc trạng thái consumer paused nếu API version hỗ trợ.
- Khi instance restart, biến requestedPause reset; cần quyết định có tự pause lại dựa trên metric downstream hay không.
- Nếu metric không có dữ liệu, phải chọn rõ fail-open/fail-closed theo mức độ quan trọng nghiệp vụ.
- Controller không nên pause khi chỉ có một datapoint bất thường; thêm thời gian duy trì ngưỡng hoặc cooldown.
- Với nhiều pod, mỗi pod có controller riêng; nếu mọi pod cùng pause, lag có thể tăng nhanh. Cần cơ chế phối hợp nếu quota chung.

## 14. Chọn giữa chờ permit và pause consumer

Hai chiến lược có trade-off khác nhau:

| Tiêu chí | Chờ permit trong listener | Pause/resume container |
|---|---|---|
| Độ chính xác theo thao tác | Tốt nếu limiter đặt sát request | Không bảo đảm RPS cụ thể |
| Poll loop | Listener có thể block lâu | Container có thể tiếp tục poll/heartbeat khi paused |
| In-flight | Record hiện tại phải chờ | In-flight có thể tiếp tục trước khi pause có hiệu lực |
| Ordering | Giữ tương đối dễ với xử lý đồng bộ | Resume tiếp tục theo partition |
| Khả năng điều khiển sự cố | Hạn chế nếu dependency hỏng hẳn | Phù hợp khi downstream overload/circuit open |
| Complexity | Đơn giản cho một quota nhỏ | Cần controller và tín hiệu resume |
| Nhiều pod | Limiter local dễ nhân quota | Các pod phải phối hợp trạng thái pause |

Một thiết kế phổ biến là:

1. Dùng per-pod limiter để làm mượt request trong điều kiện bình thường.
2. Dùng concurrency limit để tránh quá nhiều request đang chạy.
3. Dùng pause/resume khi dependency chạm ngưỡng quá tải hoặc circuit breaker mở.
4. Dùng backoff và DLT cho lỗi record đúng nghĩa, không dùng retry vô hạn để giảm tốc.

Không cần dùng mọi cơ chế cho mọi listener. Chọn theo bottleneck và SLA.

## 15. Giới hạn concurrent requests

Rate limit theo giây có thể không đủ khi latency biến động. Nếu dependency xử lý chậm, số request đang chạy tăng dù request-per-second vẫn đúng ngưỡng.

Java Semaphore là một công cụ đơn giản để giới hạn số thao tác đồng thời, đặc biệt khi có thread pool/async worker:

~~~java
public final class BoundedGateway {

    private final Semaphore permits = new Semaphore(8);
    private final PaymentGateway gateway;

    public BoundedGateway(PaymentGateway gateway) {
        this.gateway = gateway;
    }

    public void charge(PaymentRequested event)
            throws InterruptedException {

        permits.acquire();
        try {
            gateway.charge(
                event.paymentId(),
                event.amount(),
                event.eventId()
            );
        }
        finally {
            permits.release();
        }
    }
}
~~~

Ví dụ này chỉ giới hạn concurrency **trong một instance**. Nếu có 5 pod, tổng concurrency có thể là 40. Ngoài ra, acquire() có thể chờ vô hạn; trong production cần timeout, chính sách interrupt và cách pause/retry khi không lấy được permit đủ nhanh.

Nếu listener đang chạy đồng bộ với concurrency=4 mà không có async, số lời gọi gateway đồng thời từ listener thường đã bị giới hạn bởi số consumer threads. Semaphore phát huy giá trị khi nhiều loại workload cùng sử dụng gateway hoặc có async worker pool lớn hơn concurrency.

Không offload task rồi gọi ack ngay chỉ để giải phóng consumer thread. Acknowledgment phải tương ứng với việc side effect đã hoàn tất bền vững.

## 16. Backpressure với async processing và bounded queue

Một thiết kế không an toàn:

    Kafka listener poll nhanh
             |
             v
    executor.submit(record) không giới hạn
             |
             v
    Queue trong JVM tăng liên tục
             |
             v
    OutOfMemory / crash / record replay

Nếu listener trả về ngay sau submit(), Spring Kafka có thể coi record đã xử lý và commit offset theo AckMode, dù task vẫn đang nằm trong queue. Khi JVM crash, các tác vụ đã được ack nhưng chưa làm xong có thể bị mất khỏi luồng nghiệp vụ.

Thiết kế async đáng tin cậy cần:

- Queue bounded, không dùng hàng đợi không giới hạn.
- Giới hạn in-flight theo partition hoặc toàn instance.
- Chỉ acknowledge sau khi task hoàn tất theo ranh giới bền vững được chọn.
- Kiểm soát ack ordering và khả năng pause/resume khi pending tasks lớn.
- Dừng hoặc fencing task cũ khi partition bị revoke/lost.
- Idempotent side effect để an toàn khi redelivery.
- Có chiến lược khi queue đầy: pause upstream, chờ có giới hạn, hoặc từ chối có kiểm soát mà **không ack thành công**.

Async acknowledgments của Spring Kafka có behavior riêng theo phiên bản; việc xử lý out-of-order ack có thể làm container pause để tránh commit vượt record chưa hoàn tất. Không tự giả định cứ ack một record đã xong là offset có thể tiến vượt record trước nó trong cùng partition.

Nếu không cần throughput async thực sự, xử lý đồng bộ với concurrency vừa đủ thường đơn giản và dễ bảo đảm độ tin cậy hơn.

## 17. Rate limiting với retry và DefaultErrorHandler

Khi downstream đã quá tải, retry liên tục sau lỗi 429/503 có thể còn tệ hơn traffic ban đầu.

Ví dụ listener có limiter 50 request/giây nhưng DefaultErrorHandler retry ba lần cho mỗi record. Nếu số lần retry cũng gọi dependency, tổng số request có thể tăng đáng kể.

Cần xác định **permit được tính ở đâu**:

- Nếu limiter đặt trước mỗi HTTP call, cả lần gọi đầu và retry đều tiêu thụ permit.
- Nếu limiter chỉ đặt ở đầu listener nhưng nội bộ HTTP client retry nhiều lần, quota không phản ánh tất cả request.
- Nếu mỗi lần retry listener được gọi lại, limiter vẫn phải được áp dụng cho mỗi lần gọi.
- Nếu recovery/DLT publish dùng dependency khác, nó có thể cần quota riêng.

Một chính sách retry mẫu:

~~~java
DefaultErrorHandler handler =
        new DefaultErrorHandler(
            recoverer,
            new FixedBackOff(1_000L, 3L)
        );

handler.addNotRetryableExceptions(
    InvalidBusinessEventException.class
);
~~~

Đây chỉ là ví dụ cấu hình retry hữu hạn; recoverer và exception class cần được định nghĩa trong ứng dụng.

Rate limiter dùng để **phân bổ năng lực bình thường**; error handler dùng để **xử lý record thất bại**. Không nên ném exception giả để DefaultErrorHandler tạo độ trễ cho mọi record thành công. Cách đó làm tăng log, retry count, lag và có thể gây side effect trùng.

Khi API trả Retry-After, nên tôn trọng thời điểm phục hồi theo contract API nếu có thể, thay vì retry sớm hơn chỉ vì limiter cấp permit.

## 18. Quota chung và distributed rate limiter

Nếu tất cả pod cùng dùng một API key có quota 1.000 request/giây, per-pod limiter không đủ khi replica count thay đổi.

Các hướng triển khai:

**Chia quota theo số replica:** controller tính giới hạn mỗi pod xấp xỉ global quota/replica count. Đơn giản nhưng cần cập nhật nhanh khi scale, có headroom và tránh sai số khi pod chưa sẵn sàng.

**Distributed token bucket:** một hệ thống phối hợp như Redis lưu trạng thái token chung. Mỗi lần gọi API phải xin permit từ quota toàn cluster. Cần xử lý latency, lỗi Redis, clock/lease semantics và lựa chọn fail-open/fail-closed.

**Gateway tập trung:** mọi request đi qua một service có quota chung. Dễ giám sát, nhưng gateway trở thành dependency mới, cần scale và bảo vệ.

**Quota theo tenant/key:** dùng key riêng cho mỗi tenant nếu downstream áp quota theo tenant. Tránh một tenant nóng làm tiêu thụ toàn bộ token của tenant khác.

Ví dụ phân bổ:

    Global API quota: 900 req/s
    Safety reserve:    90 req/s
    Available budget: 810 req/s
    Active pods: 3
    Local target: 270 req/s mỗi pod

Nếu scale thành sáu pod mà không cập nhật quota local:

    6 x 270 = 1.620 req/s -> vượt quota chung

Hãy đo replica count thực tế và áp dụng quy tắc an toàn. Mức reserve là một quyết định vận hành để chừa chỗ cho traffic khác, retry và sai số đo, không phải hằng số bắt buộc.

## 19. Giới hạn theo partition hoặc business key

Kafka duy trì thứ tự trong từng partition. Nếu muốn giới hạn một nhóm dữ liệu mà vẫn xử lý nhóm khác, có thể cân nhắc quota theo partition hoặc key.

Ví dụ một topic có tenant A và tenant B:

    Partition 0: Tenant A traffic rất cao
    Partition 1: Tenant B traffic vừa phải
    Partition 2: Tenant A + B trộn chung

Pause Partition 0 có thể giảm tải Tenant A, nhưng Partition 2 vẫn chứa cả A và B. Nếu chỉ muốn giới hạn A, phải có cơ chế xử lý theo key/tenant hoặc thiết kế partitioning phù hợp.

Các lựa chọn:

- Token bucket theo tenant trong listener.
- Topic riêng cho tenant có SLA khác biệt.
- Partition key ổn định để phân tách workload nếu nghiệp vụ cho phép.
- Quota per tenant tại downstream gateway.
- Weighted fair scheduling với queue bounded.

Tránh tạo một limiter mới cho mỗi eventId. EventId gần như luôn duy nhất, khiến limiter không bao giờ tích lũy đủ trạng thái để thực thi quota. Với high-cardinality tenantId, cần TTL và giới hạn bộ nhớ của map limiter.

Không chuyển key sang random chỉ để trải tải khi nghiệp vụ cần ordering theo orderId/customerId.

## 20. Lag sẽ thay đổi thế nào khi throttle?

Giả sử Kafka producer tạo lambda record/giây và consumer xử lý bền vững mu record/giây. Khi lambda > mu, lag tăng gần đúng:

    LagGrowthRate = lambda - mu
    LagAfter(t) ~= InitialLag + (lambda - mu) * t

Ví dụ:

    Input = 900 records/s
    Safe processing = 600 records/s
    Difference = 300 records/s

    Sau 10 phút:
      Additional lag ~= 300 * 600 = 180.000 records

    Sau 1 giờ:
      Additional lag ~= 300 * 3.600 = 1.080.000 records

Đó là lý do rate limiting không thể là giải pháp duy nhất nếu tốc độ producer liên tục lớn hơn khả năng downstream. Hãy giảm/điều tiết input, tăng khả năng dependency hoặc chấp nhận backlog với SLA và retention được thiết kế.

Nếu sau đó input giảm còn 300 record/giây và consumer vẫn xử lý được 600 record/giây, backlog giảm với tốc độ lý thuyết 300 record/giây:

    DrainRate = 600 - 300 = 300 records/s
    DrainTime ~= CurrentLag / DrainRate

Với lag 180.000 record, thời gian drain tối thiểu ước lượng là 600 giây (10 phút), chưa kể rebalance, retry, partition skew và I/O.

Các công thức chỉ là mô hình gần đúng. Kafka lag được tính từ offset và có thể khác công việc nghiệp vụ còn lại nếu commit sớm hoặc một record tạo nhiều side effect.

## 21. Đặt giới hạn theo SLA và retention

Giới hạn tốc độ là một quyết định về trade-off giữa tính ổn định dependency và độ trễ xử lý record.

Hãy xác định:

- Maximum event processing age mà nghiệp vụ cho phép là bao lâu?
- Kafka retention dài bao nhiêu ngày so với backlog có thể tích lũy?
- Tốc độ input peak và tốc độ bền vững khác nhau thế nào?
- Dependency có quota hard limit hay chỉ một ngưỡng được khuyến nghị?
- Có thể giảm traffic ở producer hoặc ưu tiên một số event không?
- Nếu downstream bị outage 30 phút, backlog sẽ lớn bao nhiêu?
- Sau khi phục hồi, consumer có đủ năng lực dư để drain backlog trước khi record hết retention không?

Ví dụ một topic có retention 24 giờ. Nếu consumer bị throttle xuống mức khiến lag tăng liên tục nhiều ngày, có nguy cơ record cũ bị xóa do retention trước khi được tiêu thụ. Không thể coi rate limiting là an toàn chỉ vì listener không ném exception.

Đặt cảnh báo trên **oldest unprocessed record age** cùng lag. Một backlog 50.000 record có thể xử lý trong vài giây hoặc vài giờ tùy thông lượng.

## 22. Adaptive rate limiting theo tình trạng dependency

Quota cố định dễ cấu hình nhưng không phản ánh năng lực downstream thay đổi theo thời gian. Một bộ điều khiển adaptive có thể tăng/giảm tốc độ dựa trên latency, error rate, queue depth hoặc phản hồi 429.

Ví dụ chính sách minh họa:

| Điều kiện | Hành động |
|---|---|
| p95 API latency thấp, 429 gần 0, queue ổn định | Có thể tăng limit từng bước nhỏ |
| p95 latency tăng liên tục | Giảm limit một mức |
| Tỷ lệ 429/503 vượt ngưỡng | Giảm limit mạnh hoặc pause |
| Circuit breaker mở | Pause container có kiểm soát |
| Dependency phục hồi đủ lâu | Resume rồi tăng limit từ từ |
| Kafka lag quá lớn nhưng dependency khỏe | Tăng limit trong phạm vi quota đã biết |

Cách tăng chậm, giảm nhanh có thể giúp giảm dao động. Nhưng phải có **hysteresis**, cooldown, min/max rate và cơ chế bảo vệ khi metric mất dữ liệu.

Không tăng limit chỉ vì Kafka lag tăng khi dependency đang phát tín hiệu quá tải. Lag là nhu cầu công việc; latency/error/queue depth là khả năng đáp ứng. Một quyết định scale/rate limit tốt cần cả hai nhóm tín hiệu.

Cập nhật rate limiter đang hoạt động phải tuân theo API thread-safe của implementation dùng, và phải tránh tạo lại limiter gây burst không kiểm soát.

## 23. Circuit breaker và pause/resume

Khi dependency lỗi liên tục, một circuit breaker có thể chuyển sang OPEN và từ chối các lời gọi mới. Nếu listener tiếp tục gọi rồi ném exception cho từng record, hệ thống vẫn có thể sinh retry không cần thiết và giữ partition bị lỗi.

Một thiết kế:

    Circuit CLOSED
       -> xử lý record theo rate limit
       -> lỗi tăng vượt ngưỡng
       -> Circuit OPEN
       -> container.pause()
       -> kiểm tra dependency bằng health probe độc lập
       -> Circuit HALF_OPEN
       -> thử lượng request rất nhỏ
       -> thành công ổn định
       -> container.resume()

Hãy bảo đảm cơ chế kiểm tra phục hồi **không phụ thuộc vào listener đang bị pause**. Nếu chỉ listener mới có thể gọi API để chứng minh dependency khỏe, hệ thống có thể rơi vào trạng thái pause vĩnh viễn.

Cần có manual override hoặc runbook cho trường hợp dependency không tự phục hồi. Khi resume, backlog có thể lớn, nên vẫn giữ limiter và tăng tốc dần thay vì lập tức xả hết traffic.

## 24. Xử lý HTTP 429 và Retry-After

HTTP 429 thường báo client đã vượt quota. Một response có thể có Retry-After chỉ thời gian nên chờ trước khi gửi thêm request.

Trong consumer pipeline:

1. Dừng tăng concurrency/replicas.
2. Ghi nhận endpoint hoặc API key đang bị throttle.
3. Tạm giảm global/per-pod rate limit.
4. Nếu cần, pause listener hoặc partition liên quan.
5. Dùng retry có giới hạn cho record lỗi.
6. Không gửi record lỗi sang DLT chỉ vì quota tạm thời nếu vẫn có thể phục hồi trong SLA.
7. Resume theo cooldown và quan sát 429 rate.

Retry-After nên được xử lý có giới hạn thời gian và theo hợp đồng HTTP; giá trị có thể là số giây hoặc ngày giờ, và phải được parse hợp lệ. Không tin mù một header bất thường có thể làm consumer pause nhiều ngày.

Nếu nhiều consumer cùng gặp 429 và resume sau cùng một mốc cố định, sẽ tạo **thundering herd**. Có thể thêm jitter vào thời điểm resume hoặc retry để phân tán tải.

## 25. Observability cho giới hạn tốc độ

Một hệ thống có rate limiter nhưng không đo lường sẽ khó biết giới hạn đang bảo vệ hay đang trở thành bottleneck không cần thiết.

Các metric gợi ý:

| Metric | Ý nghĩa |
|---|---|
| acquired_permits_total | Tổng permit đã cấp cho xử lý |
| limiter_wait_duration | Thời gian listener chờ permit |
| limiter_rejected_total | Số request không được cấp permit khi dùng nonblocking policy |
| downstream_requests_per_second | Tốc độ gọi dependency thực tế |
| downstream_inflight | Số request đang chạy |
| downstream_429_503_total | Lỗi quota/overload |
| downstream_latency_p95_p99 | Độ trễ dependency |
| consumer_lag | Backlog theo group/topic/partition |
| oldest_record_age | Tuổi record cũ nhất chưa xử lý |
| consumer_pause_duration | Thời gian container/partition bị pause |
| rebalance_count | Phát hiện poll bị trễ hoặc membership không ổn định |
| listener_processing_duration | Thời gian xử lý record, gồm cả chờ permit |
| dlt_rate | Theo dõi lỗi thật sự cần recovery |

Nếu limiter đang bảo vệ API nhưng consumer lag tăng mãi, chỉ số limiter có thể “xanh” trong khi SLA nghiệp vụ đã vi phạm. Dashboard cần thể hiện cùng lúc **capacity, backlog và freshness**.

Khi dùng Micrometer/Prometheus, tránh label eventId, orderId hoặc requestId trên metric vì cardinality quá cao. Có thể gắn group, topic, API endpoint category, tenant tier hoặc limiter name.

## 26. Kiểm thử rate limiting

Test cần kiểm tra cả mặt giới hạn tải và độ tin cậy của consumer.

### 26.1. Test đơn vị của limiter

- Với clock hoặc random source điều khiển được, xác nhận số permit trong mỗi khoảng thời gian.
- Xác nhận nhiều listener thread dùng cùng singleton limiter per pod.
- Xác nhận số permit không reset sau mỗi record.
- Xác nhận retry nội bộ HTTP cũng bị tính vào quota nếu yêu cầu giới hạn theo HTTP calls.
- Với limiter nonblocking, kiểm tra đường xử lý khi không có permit mà không ack record sớm.

### 26.2. Test load với broker và dependency giả

Dùng Embedded Kafka hoặc Testcontainers với một HTTP stub ghi nhận request rate:

1. Tạo topic có nhiều partition.
2. Publish burst 10.000 record.
3. Chạy consumer với rate limit 40 request/giây mỗi pod.
4. Ghi nhận histogram requests/second và số request đồng thời.
5. Quan sát lag tăng trong burst rồi giảm khi input dừng.
6. Kiểm tra committed offset chỉ tiến sau nghiệp vụ thành công.
7. Scale từ 1 lên 3 pod và xác nhận quota tổng thay đổi theo đúng thiết kế.

Tránh assertion quá cứng với từng cửa sổ nhỏ vì token bucket có thể cho phép burst và hệ điều hành lập lịch thread không chính xác tuyệt đối theo millisecond. Kiểm tra giới hạn qua cửa sổ đủ dài và dung sai được định nghĩa.

### 26.3. Test pause/resume

1. Làm dependency queue vượt high watermark.
2. Xác nhận controller yêu cầu container.pause().
3. Quan sát container thực sự pause và không nhận thêm record mới sau điểm an toàn.
4. Xác nhận record in-flight được xử lý theo chính sách.
5. Hạ queue dưới low watermark.
6. Xác nhận resume và record còn lại được xử lý.
7. Kill pod trong trạng thái pause; restart và kiểm tra khả năng tiếp tục từ committed offset.

### 26.4. Test max.poll.interval.ms

1. Đặt max.poll.records lớn và quota nhỏ để tạo thời gian xử lý poll dài.
2. Quan sát rebalance, commit failure và redelivery khi vượt poll interval.
3. Giảm max.poll.records hoặc chuyển sang pause thích hợp.
4. Xác nhận consumer duy trì membership ổn định ở mức tải mong muốn.

### 26.5. Test downstream overload

1. Dependency trả 429/503 hoặc tăng latency.
2. Quan sát limiter, circuit breaker và pause.
3. Kiểm tra retry hữu hạn và jitter để tránh đồng loạt.
4. Cho dependency phục hồi.
5. Xác nhận tăng tốc có kiểm soát, không tạo burst vượt quota.
6. Kiểm tra eventId/idempotency để không có side effect trùng sau retry.

## 27. Runbook khi consumer bị throttle quá nhiều

Nếu lag tăng bất thường sau khi đưa rate limit vào production:

1. Xác nhận tốc độ record đầu vào và tốc độ xử lý thành công.
2. Kiểm tra giới hạn hiện tại là per-pod, per-thread hay global.
3. Xem số replica/concurrency có thay đổi khiến quota tổng sai không.
4. Đo thời gian chờ permit và latency thực tế của dependency.
5. Xem consumer có bị pause quá lâu hoặc không có điều kiện resume không.
6. Kiểm tra max.poll.interval.ms và max.poll.records nếu listener đang block.
7. Xem lag từng partition để phát hiện hot partition.
8. Kiểm tra retry và DLT; đừng nhầm lỗi payload cố định với overload.
9. Tính backlog drain time dựa trên capacity dư và SLA/retention.
10. Điều chỉnh quota hoặc capacity dependency một cách có kiểm soát.
11. Nếu cần giảm input, phối hợp producer hoặc kiến trúc nguồn dữ liệu.
12. Ghi lại nguyên nhân, ngưỡng và kết quả để cập nhật runbook.

Không giải quyết lag bằng cách commit bỏ qua record, tăng offset thủ công hoặc tắt validation. Những hành động đó có thể làm mất công việc nghiệp vụ thay vì xử lý nguyên nhân.

## 28. Những lỗi thiết kế thường gặp

| Sai sót | Hậu quả | Cách xử lý |
|---|---|---|
| Tạo limiter mới ở mỗi lần xử lý | Quota bị reset, hầu như không giới hạn | Dùng bean limiter có vòng đời phù hợp |
| Coi max.poll.records là RPS | Quota API vẫn bị vượt | Limit tại thao tác downstream |
| Rate limit per-thread nhưng tưởng per-pod | Tổng quota bị nhân bởi concurrency | Dùng shared limiter hoặc định nghĩa scope rõ |
| Per-pod limiter nhưng quên autoscale | Tổng quota tăng theo pod | Phân bổ quota hoặc dùng distributed limiter |
| acquire() block quá lâu | max.poll.interval.ms bị vượt, rebalance | Giảm poll size, dùng pause hoặc policy khác |
| Pause rồi không có tín hiệu resume | Consumer lag tăng vô hạn | Health probe/cooldown/runbook rõ ràng |
| Pause để che lỗi schema | Poison record không được recover | Phân loại exception, dùng DLT |
| Ack ngay sau executor.submit() | Task chưa xong nhưng offset đã commit | Ack sau completion bền vững |
| Queue async không giới hạn | OOM, crash, backlog trong RAM | Bounded queue và backpressure |
| Chỉ limit request đầu, bỏ qua HTTP retries | Vượt quota downstream | Đặt limiter sát mỗi attempt |
| Chỉ đo lag mà không đo overload | Autoscale làm dependency quá tải | Ghép lag, latency, errors và inflight |
| Scale consumer vượt số partition | Không tăng song song hữu ích | Kiểm tra partition ceiling |
| DLT mọi lỗi 429 | Event lỗi tạm thời bị đẩy sang recovery thủ công | Retry có giới hạn và pause theo sự cố |
| Bỏ idempotency vì đã có limiter | Redelivery có thể tạo duplicate | Dùng eventId/unique key/Inbox |

## 29. Checklist triển khai production

Trước khi bật giới hạn tốc độ xử lý, kiểm tra:

- Quota được tính theo record, API call, DB transaction hay bytes?
- Limit áp dụng cho một thread, một pod, một consumer group hay toàn cluster?
- Có thiết kế cho autoscaling và thay đổi concurrency?
- Listener có thể chờ permit bao lâu trước khi ảnh hưởng max.poll.interval.ms?
- max.poll.records đã được chọn theo processing time thực tế?
- Có dùng pause/resume để phản ứng với overload kéo dài?
- Có phân biệt pause toàn container với pausePartition khi cần?
- Có hysteresis/cooldown và tín hiệu resume độc lập?
- Có giới hạn concurrent requests và queue async không?
- Retry có tiêu thụ quota và có jitter để tránh retry storm không?
- Offset có được commit sau side effect bền vững không?
- Side effect có idempotency khi record redelivery không?
- Có dashboard rate, inflight, 429, latency, lag và oldest age?
- Retention Kafka có đủ cho backlog trong đỉnh tải/outage?
- Đã test pause/resume, restart, rebalance, overload và quota nhiều pod?

## 30. Kết luận

**Giới hạn tốc độ xử lý** trong Spring Kafka phải được thiết kế tại đúng ranh giới tài nguyên: record/second, request/second, concurrent requests hoặc quota dùng chung. Kafka consumer cho phép điều chỉnh poll size, concurrency và pause/resume, nhưng các cơ chế này không tự thay thế một rate limiter ở điểm gọi dependency.

Trong điều kiện bình thường, limiter và concurrency bound giúp bảo vệ downstream. Khi quá tải rõ rệt, pause/resume có kiểm soát giúp tạo backpressure mà không cố ý rời consumer group. Trong mọi trường hợp, cần bảo vệ offset commit, khả năng redelivery/idempotency, theo dõi lag và thời gian chờ nghiệp vụ. **Một consumer chậm nhưng không mất dữ liệu thường an toàn hơn một consumer rất nhanh nhưng làm hệ thống phụ thuộc sụp đổ; tuy nhiên tốc độ giới hạn phải đủ bền vững để đáp ứng SLA và Kafka retention.**
