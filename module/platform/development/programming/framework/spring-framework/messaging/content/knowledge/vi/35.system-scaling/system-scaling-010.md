# Đánh giá năng lực bằng tải thực tế, p95/p99 và thử nghiệm sự cố

## 1. Mục tiêu: đo hệ thống khi hoạt động như production

Một ứng dụng Spring Messaging có thể chạy tốt khi chỉ có vài client, nhưng chậm hoặc mất ổn định khi số kết nối, subscription và message tăng lên. Để đánh giá năng lực thật, cần tạo workload giống cách người dùng và service thực sự tương tác, đo độ trễ ở nhiều lớp, tìm điểm bão hòa và kiểm tra hành vi khi một thành phần gặp sự cố.

Một kết quả kiểm thử có giá trị phải trả lời được:

- Hệ thống xử lý được bao nhiêu message hoặc request mỗi giây trong khi vẫn đáp ứng SLO?
- Độ trễ điển hình và độ trễ ở phần đuôi là bao nhiêu?
- p95 và p99 thay đổi thế nào khi tăng tải?
- Điểm nghẽn nằm ở ứng dụng Spring, message broker, database, network hay consumer?
- Khi dependency chậm, mất kết nối hoặc restart, hệ thống có backpressure, phục hồi và tránh mất/trùng message không?
- Sau khi sự cố kết thúc, backlog mất bao lâu để xử lý hết?

**Năng lực (capacity)** không chỉ là số request tối đa trước khi server ngừng hoạt động. Đó là mức tải có thể duy trì trong một khoảng thời gian mà latency, error rate, message loss, queue growth và tài nguyên vẫn nằm trong giới hạn chấp nhận được.

## 2. Những chỉ số cần đo

Không nên đánh giá hệ thống bằng một con số throughput hoặc CPU. Hãy quan sát đồng thời các nhóm chỉ số sau.

| Nhóm | Chỉ số | Ý nghĩa |
| --- | --- | --- |
| Tải vào | Offered rate, request/message rate | Số yêu cầu được tạo ra mỗi giây. |
| Tải được chấp nhận | Accepted rate, rejected rate | Số yêu cầu được server hoặc broker nhận và số bị từ chối. |
| Kết quả | Completed/acknowledged rate, error rate | Số yêu cầu hoàn tất hoặc được xác nhận; tỷ lệ lỗi. |
| Độ trễ | p50, p95, p99, max | Phân bố thời gian từ lúc gửi tới lúc nhận kết quả hoặc ACK. |
| Kết nối | Active connections, sessions, streams | Số kết nối WebSocket/RSocket và stream đang hoạt động. |
| Subscription | Subscription count, fan-out | Số đăng ký và số consumer nhận một message được publish. |
| Hàng đợi | Queue depth, oldest message age, consumer lag | Backlog, tuổi message cũ nhất và độ trễ xử lý của consumer. |
| Dữ liệu | Payload size, bytes/s | Kích thước và lưu lượng dữ liệu truyền. |
| Tài nguyên | CPU, heap, GC, threads, network, file descriptors | Mức sử dụng và tình trạng bão hòa của tiến trình. |
| Dependency | DB pool, query latency, broker connections | Khả năng đáp ứng của các thành phần phía sau. |

### 2.1. Đo đúng latency

Đối với một request-response, end-to-end latency thường được đo từ thời điểm client gửi request đến lúc client nhận response hoàn chỉnh. Với message bất đồng bộ, cần xác định chính xác mốc bắt đầu và kết thúc:

- Publish latency: từ lúc producer gửi đến lúc broker xác nhận nhận message.
- Queue latency: từ lúc broker nhận message đến lúc consumer bắt đầu xử lý.
- Processing latency: thời gian consumer thực thi logic.
- Delivery latency: từ lúc publish đến khi consumer nhận message.
- End-to-end business latency: từ lúc người dùng tạo yêu cầu đến khi kết quả nghiệp vụ có thể sử dụng.

Không cộng các metric không cùng mốc thời gian hoặc cùng correlation ID. Nếu cần tổng latency, đo trực tiếp ở client và dùng trace/span để phân rã thời gian qua từng hop.

### 2.2. Throughput phải tính theo kết quả

Phân biệt:

- **Offered throughput:** tốc độ load generator cố gắng gửi.
- **Accepted throughput:** tốc độ hệ thống nhận request.
- **Completed throughput:** tốc độ request hoàn tất thành công.
- **Acknowledged throughput:** tốc độ message được consumer xác nhận, nếu giao thức và broker có ACK.

Một hệ thống có thể nhận 10.000 message/giây nhưng chỉ xử lý được 7.000 message/giây. Khi đó backlog tăng khoảng 3.000 message mỗi giây. Chỉ nhìn vào số message được gửi hoặc accepted sẽ đánh giá quá cao năng lực.

Error rate nên phân loại timeout, rejection, conversion error, disconnect, broker error và business error. Không gộp tất cả vào một nhóm nếu cần tìm nguyên nhân.

## 3. Hiểu đúng p50, p95 và p99

Percentile mô tả vị trí trong phân bố latency sau khi sắp xếp các mẫu theo thứ tự tăng dần.

- **p50 (median):** 50% request có latency nhỏ hơn hoặc bằng giá trị này.
- **p95:** 95% request hoàn tất trong hoặc trước giá trị này; 5% còn lại chậm hơn.
- **p99:** 99% request hoàn tất trong hoặc trước giá trị này; 1% còn lại chậm hơn.

Ví dụ:

| Chỉ số | Latency |
| --- | ---: |
| p50 | 35 ms |
| p95 | 180 ms |
| p99 | 850 ms |

Phần lớn request hoàn tất nhanh, nhưng một phần nhỏ mất gần một giây. Nếu chỉ báo cáo trung bình 60 ms, vấn đề tail latency sẽ bị che khuất.

### 3.1. Tính percentile theo nearest-rank

Một cách minh họa đơn giản là nearest-rank. Với n mẫu đã sắp xếp, vị trí percentile q là:

\[
rank = \lceil q \times n \rceil
\]

Vị trí được đếm từ 1. Đây là phương pháp minh họa; các hệ thống thống kê và histogram có thể dùng cách nội suy khác nhau. Khi so sánh kết quả giữa công cụ, hãy dùng cùng định nghĩa hoặc ghi rõ cách tính.

Ví dụ Java 17+:

~~~java
import java.util.Arrays;

public class PercentileDemo {

    static long percentile(long[] sorted, double q) {
        if (sorted.length == 0 || q <= 0 || q > 1) {
            throw new IllegalArgumentException("Invalid input");
        }
        int rank = (int) Math.ceil(q * sorted.length);
        return sorted[rank - 1];
    }

    public static void main(String[] args) {
        long[] latencyMillis = {8, 10, 11, 12, 13, 14, 15, 18, 25, 80};
        Arrays.sort(latencyMillis);

        System.out.println("p50=" + percentile(latencyMillis, 0.50) + " ms");
        System.out.println("p95=" + percentile(latencyMillis, 0.95) + " ms");
        System.out.println("p99=" + percentile(latencyMillis, 0.99) + " ms");
    }
}
~~~

Lưu file là PercentileDemo.java và chạy:

~~~bash
javac PercentileDemo.java
java PercentileDemo
~~~

Stdout:

~~~text
p50=13 ms
p95=80 ms
p99=80 ms
~~~

Với chỉ 10 mẫu, p95 và p99 đều là giá trị lớn nhất. Đây không phải bằng chứng tail latency đã được đo chính xác; nó cho thấy sample size nhỏ không đủ để hiểu phần đuôi. Nếu có 100.000 request, p99 đại diện cho khoảng 1.000 request chậm nhất, cung cấp nhiều dữ liệu hơn để phân tích.

### 3.2. Vì sao p99 quan trọng?

Tail latency có thể làm hỏng trải nghiệm dù median rất tốt. Một số nguyên nhân phổ biến:

- Request chờ connection pool hoặc thread pool.
- Garbage collection pause.
- Database query có kế hoạch thực thi chậm.
- Broker queue tích tụ hoặc consumer xử lý không kịp.
- Một số message có payload lớn hoặc fan-out tới nhiều subscriber.
- Retry và timeout tạo thêm tải.
- Network congestion hoặc một node bị quá tải.

p95 phù hợp để nhìn trải nghiệm của phần lớn request; p99 hữu ích khi cần kiểm soát những request rất chậm. Không nên chọn percentile cao hơn chỉ để tạo cảm giác chính xác: p99.9 cần lượng mẫu đủ lớn và một cách thu thập histogram phù hợp.

### 3.3. Tránh các sai lầm khi tổng hợp percentile

Không lấy trung bình p95 của nhiều instance để tạo p95 toàn hệ thống. Percentile không cộng tuyến tính. Một instance có ít request và một instance có nhiều request phải đóng góp theo số lượng mẫu thực tế.

Cách tốt hơn là thu thập histogram buckets có thể tổng hợp, cộng số lượng ở từng bucket qua các instance rồi tính quantile trên phân bố đã gộp.

Cũng cần tránh:

- Gộp request thành công với timeout bị loại khỏi mẫu.
- Chỉ đo những request nhanh và bỏ request lỗi.
- Tính percentile trên cửa sổ quá ngắn hoặc số mẫu quá ít.
- Dùng histogram buckets quá thưa khiến p99 bị ước lượng kém.
- So sánh p99 của các lần chạy có workload hoặc sample size khác nhau.

## 4. Thiết kế workload giống thực tế

Load generator cần mô phỏng hành vi người dùng và producer thực tế, không chỉ lặp một message nhỏ với tốc độ cố định.

Trước khi chạy, thu thập hoặc ước lượng các đặc điểm:

1. Số client đồng thời và tốc độ tạo kết nối mới.
2. Số subscription trên mỗi session.
3. Tỷ lệ request-response, request-stream, request-channel hoặc publish/subscribe.
4. Kích thước payload theo phân bố thực tế: nhỏ, trung bình và lớn.
5. Tỷ lệ message được fan-out tới 1, 10, 100 hoặc nhiều subscriber.
6. Tốc độ message theo thời gian, bao gồm giờ cao điểm và burst.
7. Thời gian sống của session, reconnect và heartbeat.
8. Tỷ lệ message lỗi, retry, duplicate và message bị từ chối.
9. Hành vi consumer: xử lý nhanh, chậm, pause, ACK hoặc NACK.
10. Tần suất gọi database và service bên ngoài trong handler.

Dùng dữ liệu giả lập có phân bố gần dữ liệu thật. Không đưa thông tin cá nhân, token, credential hoặc payload nhạy cảm vào load test. Nếu payload được che hoặc tạo tổng hợp, vẫn giữ kích thước và cấu trúc gần thực tế để chi phí serialization và network không bị đánh giá thấp.

### 4.1. Open workload và closed workload

Hai mô hình tạo tải có hành vi khác nhau.

**Open model** phát request theo một arrival rate định trước, ví dụ 200 request/giây, bất kể hệ thống đang phản hồi nhanh hay chậm. Đây là cách phù hợp để mô phỏng dòng sự kiện bên ngoài hoặc producer gửi theo lịch.

**Closed model** duy trì một số lượng virtual users cố định. Mỗi user gửi request, đợi response rồi mới gửi tiếp. Khi hệ thống chậm, mỗi user tạo ít request hơn. Vì vậy closed model có thể tự giảm offered load trong lúc hệ thống đang bão hòa và che giấu vấn đề.

| Đặc điểm | Open model | Closed model |
| --- | --- | --- |
| Điều khiển | Arrival rate | Số user/concurrency |
| Khi server chậm | Vẫn cố giữ tốc độ gửi | Tốc độ gửi giảm theo thời gian chờ |
| Phù hợp | Event stream, producer, traffic rate cố định | Phiên tương tác có think time |
| Rủi ro | Có thể tạo backlog lớn nếu server không theo kịp | Có thể che giấu overload và coordinated omission |

Chọn mô hình dựa trên workload thực. Một hệ thống messaging thường cần cả hai: producer tạo tải theo arrival rate và consumer/session giữ số lượng kết nối hoặc subscription ổn định.

### 4.2. Little's Law: liên hệ giữa throughput, latency và concurrency

Với hệ thống ổn định, Little's Law mô tả:

\[
L = \lambda \times W
\]

Trong đó:

- L là số request trung bình đang ở trong hệ thống.
- λ là throughput trung bình (request/giây).
- W là thời gian trung bình trong hệ thống (giây).

Ví dụ: 200 request/giây với thời gian xử lý trung bình 0,25 giây tương ứng khoảng 50 request đang được xử lý hoặc chờ trong hệ thống. Khi latency tăng lên, concurrency và số request đang tồn tại cũng có thể tăng nếu arrival rate không đổi.

Không thay W bằng p99 trong công thức như thể p99 là latency trung bình. Dùng Little's Law với các đại lượng trung bình trong cùng phạm vi đo.

## 5. Các loại bài kiểm thử tải

Không có một lần chạy duy nhất đủ để kết luận năng lực. Mỗi loại test trả lời một câu hỏi khác nhau.

| Loại test | Cách chạy | Câu hỏi cần trả lời |
| --- | --- | --- |
| Baseline | Tải thấp, ổn định | Latency và tài nguyên khi hệ thống khỏe là bao nhiêu? |
| Load test | Tăng tới tải dự kiến production | Hệ thống có đáp ứng SLO ở tải mục tiêu không? |
| Stress test | Tăng vượt tải mục tiêu | Điểm bão hòa và kiểu thất bại là gì? |
| Spike test | Tăng tải đột ngột | Hệ thống phản ứng với burst và scale như thế nào? |
| Soak test | Duy trì tải lâu | Có memory leak, queue growth hoặc degradation theo thời gian không? |
| Capacity test | Tăng tải theo bước | Mức throughput cao nhất vẫn đáp ứng SLO là bao nhiêu? |
| Resilience test | Tạo lỗi khi đang chịu tải | Hệ thống có tiếp tục phục vụ và phục hồi đúng không? |

Một chu kỳ kiểm thử nên có:

1. **Warm-up:** cho JVM, JIT, connection pool và cache đạt trạng thái ổn định.
2. **Ramp-up:** tăng tải theo bước để tránh một spike không chủ ý.
3. **Steady state:** giữ tải mục tiêu đủ lâu để lấy sample có ý nghĩa.
4. **Ramp-down:** giảm tải có kiểm soát.
5. **Recovery observation:** tiếp tục theo dõi cho tới khi queue, thread và resource trở lại bình thường.

Không dùng kết quả trong giai đoạn warm-up để tính SLO steady-state. Đồng thời đừng bỏ qua warm-up nếu production có traffic ngay sau deploy hoặc restart; đó là một kịch bản riêng cần kiểm thử.

## 6. Những tình huống đặc thù của Spring Messaging

Workload messaging có nhiều yếu tố không xuất hiện trong một HTTP request đơn giản.

### 6.1. WebSocket và STOMP

Với STOMP-over-WebSocket, cần đo:

- Số WebSocket connection đồng thời và connection churn.
- Thời gian handshake và STOMP CONNECT.
- Số subscription trên mỗi session.
- Số message publish mỗi giây và kích thước payload.
- Fan-out: một message được gửi tới bao nhiêu subscriber.
- Thời gian từ SEND tới MESSAGE nhận được.
- Heartbeat, disconnect, reconnect và session cleanup.
- Slow consumer, outbound buffer và queue tích tụ.

Nếu production dùng broker relay như RabbitMQ hoặc ActiveMQ, hãy chạy load test với broker thật. Simple broker trong bộ nhớ hữu ích cho test chức năng nhưng không đại diện cho throughput, persistence, clustering, ACK/NACK hoặc giới hạn của broker production.

Fan-out làm thay đổi khối lượng công việc đáng kể. Ví dụ 1.000 message/giây, mỗi message có 100 subscriber, có thể tạo khoảng 100.000 lần delivery/giây. Producer rate thấp không có nghĩa broker và outbound path chịu tải thấp.

### 6.2. RSocket

Với RSocket, phân biệt số connection, số stream và số payload:

- Request-Response: đo latency mỗi request và số request đồng thời.
- Request-Stream: đo số stream đang hoạt động, demand, tốc độ phát payload và cancellation.
- Request-Channel: đo cả hai chiều, backpressure và thời gian hoàn tất.
- Fire-and-Forget: đo tốc độ nhận, xử lý và xác nhận ở tầng nghiệp vụ; không suy ra hoàn tất chỉ từ việc gửi frame.
- Đo kích thước payload, serialization, reconnect và lỗi theo stream.

Backpressure có thể giới hạn tốc độ phát, nhưng cần kiểm tra toàn bộ pipeline. Nếu consumer chậm, publisher có tôn trọng request(n) hay vẫn đẩy dữ liệu vào một queue không giới hạn? Nếu một stream bị hủy, tài nguyên upstream có được giải phóng không?

### 6.3. Message channel và executor trong Spring

Theo dõi các executor xử lý inbound, outbound và broker channel nếu ứng dụng cấu hình chúng. Những chỉ số hữu ích gồm active threads, pool size, queue size, task rejection và thời gian chờ trong queue.

Một thread pool có queue không giới hạn có thể làm hệ thống trông khỏe trong thời gian đầu: request được nhận nhưng chờ rất lâu trước khi xử lý. Queue tăng liên tục là dấu hiệu offered rate vượt completed rate. Cân nhắc queue có giới hạn, chính sách từ chối rõ ràng và backpressure phù hợp với giao thức.

## 7. Đo lường trong Spring bằng Micrometer

Micrometer cung cấp Timer để đo thời gian và số lần thực hiện. Với ứng dụng Spring Boot, Actuator có thể xuất metrics tới registry đã cấu hình, ví dụ Prometheus.

Một Timer cho thời gian xử lý message:

~~~java
import java.time.Duration;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

public class MessagingMetrics {

    private final MeterRegistry registry;
    private final Timer handlerTimer;

    public MessagingMetrics(MeterRegistry registry) {
        this.registry = registry;
        this.handlerTimer = Timer.builder("messaging.handler.duration")
            .description("Time from handler subscription to termination")
            .tag("interaction", "request-response")
            .publishPercentileHistogram()
            .serviceLevelObjectives(
                Duration.ofMillis(25),
                Duration.ofMillis(50),
                Duration.ofMillis(100),
                Duration.ofMillis(250),
                Duration.ofMillis(500),
                Duration.ofSeconds(1)
            )
            .register(registry);
    }

    public Timer handlerTimer() {
        return handlerTimer;
    }
}
~~~

Với publisher reactive, cần đo từ lúc subscribe tới khi publisher complete, error hoặc cancel. Đừng chỉ đo thời gian tạo Mono/Flux vì nhiều công việc chỉ bắt đầu khi có subscription.

Ví dụ:

~~~java
import io.micrometer.core.instrument.Timer;
import reactor.core.publisher.Mono;

public Mono<Reply> handle(Command command) {
    return Mono.defer(() -> {
        Timer.Sample sample = Timer.start(registry);
        return Mono.defer(() -> service.process(command))
            .doFinally(signal -> sample.stop(handlerTimer));
    });
}
~~~

Timer trên đo thời gian của publisher trong handler đến terminal signal. Nếu subscriber hủy, timer cũng dừng tại thời điểm cancellation; nó không chứng minh công việc detached hoặc tài nguyên bên dưới đã dừng. Hãy đo thêm thời gian thực thi của worker và queue nếu chúng có vòng đời riêng.

Nên có counter riêng cho các outcome như success, error, timeout, cancel và rejected. Dùng các giá trị tag hữu hạn, thống nhất để dashboard có thể so sánh qua các instance.

### 7.1. Histogram và percentile

Có hai cách phổ biến để xuất percentile:

- **Client-side percentile:** registry tính p95/p99 trên từng instance. Giá trị này hữu ích cho instance riêng nhưng không thể cộng/trung bình để tạo percentile toàn cụm.
- **Histogram buckets:** xuất số lượng mẫu theo các bucket latency. Backend có thể tổng hợp buckets qua nhiều instance rồi ước lượng quantile.

Với Prometheus, Timer có histogram có thể tạo metric dạng bucket. Ví dụ truy vấn p99:

~~~promql
histogram_quantile(
  0.99,
  sum by (le) (
    rate(messaging_handler_duration_seconds_bucket[5m])
  )
)
~~~

Tên metric thực tế phụ thuộc registry và quy tắc đặt tên. Hãy xác nhận series được export trước khi đưa query vào dashboard. Histogram quantile là ước lượng theo bucket, không phải percentile chính xác của từng request.

Nếu dùng Prometheus, cần dependency registry phù hợp và expose endpoint metrics theo cấu hình Spring Boot Actuator. Chỉ mở các endpoint cần thiết và bảo vệ quyền truy cập trong môi trường thật.

### 7.2. Tránh high-cardinality tags

Không đưa các giá trị gần như duy nhất vào metric tag:

- sessionId, connectionId, requestId, messageId.
- userId, email, tenantId không giới hạn.
- Destination được tạo động từ ID.
- Exception message chứa dữ liệu tự do.

Mỗi tổ hợp tag tạo một time series. Cardinality cao làm tăng bộ nhớ, CPU và chi phí lưu trữ của hệ thống metrics.

Nên dùng tag có tập giá trị hữu hạn, ví dụ:

| Tag | Giá trị phù hợp |
| --- | --- |
| interaction | request-response, request-stream, channel, fire-and-forget |
| outcome | success, error, timeout, cancel, rejected |
| destination_group | orders, notifications, telemetry |
| payload_class | small, medium, large |
| instance | instance label do nền tảng quản lý |

Correlation ID phù hợp cho log và trace, không phù hợp làm metric tag có số lượng vô hạn.

## 8. Phân rã điểm nghẽn và tìm capacity

Khi tăng tải, vẽ latency p50/p95/p99, completed throughput, error rate và queue depth theo cùng trục thời gian.

Một hệ thống thường có ba vùng:

1. **Underloaded:** latency ổn định, throughput tăng gần tương ứng với offered rate.
2. **Near saturation:** throughput tăng chậm dần, p95/p99 và queue latency tăng nhanh.
3. **Overloaded:** completed throughput không tăng hoặc giảm, queue tăng, timeout/rejection xuất hiện và tài nguyên có thể bão hòa.

Điểm mà latency bắt đầu tăng phi tuyến hoặc backlog không còn tự giảm là tín hiệu cần điều tra. Đừng chỉ ghi nhận số request tối đa trước khi server crash; đó không phải capacity an toàn.

### 8.1. Đọc các mẫu triệu chứng

| Quan sát | Khả năng cần kiểm tra |
| --- | --- |
| CPU gần bão hòa, latency tăng | Serialization, compression, business logic, GC hoặc thread contention. |
| CPU thấp nhưng p99 cao | Queue wait, network, lock, database, broker hoặc dependency chậm. |
| Heap tăng theo thời gian | Queue không giới hạn, giữ reference, session/subscription không được dọn hoặc memory leak. |
| GC pause tăng | Allocation rate, payload lớn, buffer hoặc heap sizing. |
| DB pool luôn hết connection | Query chậm, transaction dài hoặc pool quá nhỏ. |
| Broker queue tăng | Consumer rate thấp hơn producer rate, slow consumer hoặc broker resource limit. |
| Connection count tăng liên tục | Reconnect loop, leak session hoặc client không disconnect. |
| Error rate tăng khi retry bật | Retry amplification, thiếu backoff hoặc retry cả lỗi không thể phục hồi. |
| Chỉ một instance có p99 cao | Load imbalance, noisy neighbor hoặc instance/dependency riêng có vấn đề. |

### 8.2. Ước lượng headroom

Chạy tải theo các bước có kiểm soát, ví dụ 25%, 50%, 75%, 100%, 125% và 150% của tải mục tiêu. Giữ mỗi bước đủ lâu để queue và latency phản ánh trạng thái ổn định.

Capacity an toàn là mức tải cao nhất mà hệ thống vẫn đạt SLO, không tích lũy backlog, không tăng lỗi theo thời gian và vẫn còn khoảng trống để hấp thụ burst hoặc sự cố. Mức headroom cụ thể phụ thuộc biến động traffic, thời gian scale, chi phí và mức độ quan trọng của dịch vụ; không có một tỷ lệ chung phù hợp cho mọi hệ thống.

Nếu tăng số instance mà throughput không tăng, kiểm tra shared bottleneck như broker, database, network hoặc external API. Scale ứng dụng không tự mở rộng các dependency dùng chung.

## 9. Thiết kế thử nghiệm sự cố (fault injection)

Fault injection là chủ động tạo một lỗi có kiểm soát để xem hệ thống phản ứng ra sao. Mục tiêu không phải làm hệ thống hỏng cho vui, mà xác nhận các giả định về timeout, retry, backpressure, failover, dữ liệu và phục hồi.

Bắt đầu bằng một giả thuyết rõ ràng:

- Nếu broker tạm ngừng nhận connection, producer sẽ timeout hoặc bị từ chối trong thời hạn đã định.
- Nếu consumer chậm, queue tăng nhưng memory vẫn nằm trong giới hạn.
- Nếu database tăng latency, request bị giới hạn bởi deadline và không tạo thread/queue vô hạn.
- Nếu một instance bị restart, client reconnect và subscription được khôi phục theo chính sách.
- Nếu network mất kết nối, message có thể được retry mà không tạo side effect trùng.

### 9.1. Các lỗi nên mô phỏng

| Fault | Cách tạo lỗi | Điều cần quan sát |
| --- | --- | --- |
| Network latency/jitter | Thêm delay hoặc biến động latency giữa service và broker | p95/p99, timeout, queue và retry. |
| Packet loss / connection reset | Làm gián đoạn kết nối trong phạm vi test | Reconnect, stream/session cleanup và message delivery. |
| Broker restart | Restart broker hoặc ngắt một node | Failover, reconnect, redelivery và backlog recovery. |
| Slow consumer | Giảm tốc độ xử lý hoặc tạm dừng consumer | Queue depth, backpressure, memory và oldest-message age. |
| Database slowdown | Tạo query chậm có kiểm soát | DB pool, handler latency, timeout và retry. |
| CPU pressure | Giới hạn CPU hoặc tạo workload cạnh tranh | Scheduler delay, throughput và tail latency. |
| Memory pressure | Giảm memory limit trong môi trường test | GC, OOM behavior và khả năng restart. |
| Thread pool saturation | Giới hạn worker hoặc tạo task chờ có kiểm soát | Queue growth, rejection và thread starvation. |
| Instance termination | Restart hoặc terminate một instance test | Load balancing, reconnect và khả năng phục hồi. |
| Downstream failure | Trả lỗi hoặc timeout từ dependency | Circuit breaker, fallback và retry amplification. |

Không nên tạo nhiều fault cùng lúc trong lần thử đầu tiên. Khi biết tác động riêng từng fault, có thể phối hợp hai lỗi để kiểm tra tương tác, ví dụ broker chậm trong lúc một instance đang restart.

### 9.2. Đo khả năng phục hồi

Ngoài latency và error rate trong thời gian fault, cần đo:

- **Detection time:** bao lâu hệ thống phát hiện dependency không khỏe.
- **Time to fail:** bao lâu request thất bại hoặc chuyển sang fallback.
- **Time to recover:** từ lúc dependency khỏe trở lại tới khi service phục vụ bình thường.
- **Backlog drain time:** thời gian xử lý hết queue tích tụ.
- **Data integrity:** số message mất, trùng hoặc xử lý sai thứ tự theo yêu cầu.
- **Recovery amplification:** lượng retry/reconnect phát sinh sau khi phục hồi.
- **User impact:** tỷ lệ request thành công và thời gian người dùng bị ảnh hưởng.

Một hệ thống có thể phục hồi kết nối trong vài giây nhưng mất nhiều phút để xử lý backlog. Vì vậy recovery không chỉ là trạng thái health check chuyển về UP.

### 9.3. Phạm vi và điều kiện dừng

Trước mỗi thử nghiệm, xác định:

- Môi trường, service, instance, broker và dependency nằm trong phạm vi.
- Tải nền và fault sẽ được áp dụng.
- Thời gian thử nghiệm và cách kết thúc fault.
- SLO và ngưỡng abort, ví dụ error rate, queue depth, memory hoặc latency vượt giới hạn đã thống nhất.
- Người theo dõi và cách khôi phục nếu hệ thống không tự phục hồi.

Bắt đầu với phạm vi nhỏ và tăng dần. Dùng staging hoặc môi trường thử nghiệm tương đương production. Nếu chạy fault injection trong production, cần quy trình kiểm soát riêng, phạm vi giới hạn và khả năng dừng ngay.

## 10. Kết hợp tải và fault injection

Thử nghiệm lỗi khi hệ thống đang rảnh thường không phát hiện được vấn đề về capacity. Một dependency có thể chịu được restart lúc không có message, nhưng tạo backlog lớn khi restart trong giờ cao điểm.

Một ma trận thử nghiệm hữu ích:

| Tải | Hệ thống khỏe | Dependency chậm | Dependency mất kết nối | Sau khi phục hồi |
| --- | --- | --- | --- | --- |
| Baseline | Đo baseline | Kiểm tra timeout | Kiểm tra graceful failure | Đo thời gian ổn định lại |
| Tải mục tiêu | Xác nhận SLO | Kiểm tra p95/p99 và queue | Kiểm tra lỗi và retry | Đo backlog drain |
| Burst | Kiểm tra khả năng hấp thụ | Kiểm tra queue limit | Kiểm tra rejection/backpressure | Kiểm tra recovery amplification |
| Near capacity | Xác định điểm bão hòa | Xác định điểm sụp đổ | Kiểm tra fail-fast | Đo khả năng trở lại steady state |

Không phải mọi ô trong ma trận đều phải chạy ngay. Chọn các trường hợp có rủi ro cao, sau đó mở rộng dựa trên kết quả.

## 11. Retry, timeout, backpressure và idempotency

Các cơ chế phục hồi có thể làm tải nặng hơn nếu phối hợp sai.

- **Timeout:** giới hạn thời gian caller chờ hoặc thời gian xử lý được phép.
- **Retry:** thử lại thao tác sau lỗi có thể phục hồi.
- **Backoff:** giãn thời gian giữa các lần retry.
- **Jitter:** thêm biến động ngẫu nhiên để nhiều client không retry đồng loạt.
- **Circuit breaker:** tạm ngừng gọi dependency đang thất bại để tránh tiếp tục làm quá tải.
- **Bulkhead:** giới hạn tài nguyên một nhóm request để lỗi không lan sang nhóm khác.
- **Backpressure:** điều khiển tốc độ phát theo nhu cầu consumer.
- **Idempotency:** bảo đảm retry cùng một ý định nghiệp vụ không tạo side effect lặp.

Không retry vô hạn hoặc retry ngay lập tức. Nếu 1.000 client cùng timeout rồi retry sau đúng một giây, dependency vừa phục hồi có thể nhận một spike mới. Dùng exponential backoff có giới hạn và jitter.

Với message có side effect, timeout tạo ra kết quả không chắc chắn: consumer có thể đã xử lý xong nhưng ACK hoặc response bị mất. Dùng message ID/idempotency key và lưu trạng thái xử lý để deduplicate. Định nghĩa rõ semantics at-most-once, at-least-once hoặc exactly-once trong phạm vi hệ thống; đừng tuyên bố exactly-once chỉ vì broker có ACK.

## 12. Công cụ và cách chọn load generator

Công cụ phải mô phỏng đúng giao thức và không trở thành bottleneck.

| Công cụ / cách tiếp cận | Phù hợp | Lưu ý |
| --- | --- | --- |
| Gatling | Load test HTTP và WebSocket, có thể gửi STOMP frame qua WebSocket | Phải mô phỏng đúng STOMP framing, handshake và session behavior. |
| k6 | HTTP và WebSocket workload | Với STOMP cần tự tạo frame đúng giao thức; k6 không phải RSocket client native. |
| JMeter | HTTP, WebSocket thông qua plugin và nhiều protocol | Xác minh plugin hỗ trợ phiên bản giao thức và kiểu load mong muốn. |
| RSocket-native client/load driver | Request-Response, Request-Stream, Request-Channel | Phù hợp để đo demand, stream lifecycle và frame-level behavior. |
| WebSocketStompClient | Integration/E2E functional tests và tải nhỏ có kiểm soát | Không mặc định là load generator hiệu năng cao cho hàng chục nghìn session. |

Đặt load generator trên máy hoặc container tách biệt với server được đo. Theo dõi CPU, memory, network và số connection ở phía generator. Nếu generator bão hòa trước server, kết quả không phản ánh capacity của ứng dụng.

Chạy nhiều generator khi cần scale connection hoặc throughput. Dùng cùng một workload definition và đồng bộ thời gian để so sánh. Không chạy load test trên production chỉ vì công cụ có thể tạo tải; cần phạm vi, giới hạn và giám sát đã thống nhất.

## 13. Ví dụ thiết kế một bài capacity test cho STOMP

Giả sử hệ thống gửi notification qua STOMP broker relay. Một kế hoạch minh họa:

**Workload**

- 2.000 WebSocket sessions.
- Trung bình 3 subscriptions mỗi session.
- 500 publish message/giây.
- Payload trung vị 1 KB, một phần message 10 KB.
- Fan-out trung bình 20 subscriber/message.
- 10 phút warm-up, 20 phút steady-state, 5 phút ramp-down.

Đây chỉ là số liệu ví dụ để mô tả cách lập kế hoạch; tải thực phải dựa trên traffic production hoặc dự báo đã được xác nhận.

**Đo lường**

- Thời gian handshake và STOMP CONNECT.
- Active sessions và subscriptions.
- Publish rate, broker accepted rate và delivery rate.
- End-to-end publish-to-receive latency: p50, p95, p99.
- Outbound queue, consumer lag và oldest message age.
- CPU, heap, GC, network, thread pool và broker resource.
- Disconnect/reconnect, delivery failure và duplicate count.

**Thử nghiệm**

1. Chạy baseline với 10% tải.
2. Tăng từng bước lên 25%, 50%, 75%, 100% và 125%.
3. Giữ tải mục tiêu để xác nhận p95/p99 ổn định và queue không tăng liên tục.
4. Làm chậm một nhóm consumer để kiểm tra slow-consumer behavior.
5. Restart broker node trong phạm vi test và theo dõi reconnect.
6. Khôi phục broker, đo backlog drain và duplicate/lost message.
7. Chạy soak test để tìm memory leak hoặc subscription không được dọn.

Kết quả cần nêu rõ mức tải cao nhất đạt SLO, thành phần bão hòa đầu tiên, các giới hạn phát hiện được và thời gian phục hồi sau fault.

## 14. Cách đọc kết quả và đưa ra quyết định

Một báo cáo tốt không chỉ có biểu đồ. Nó cần có bối cảnh để người khác lặp lại được:

- Phiên bản ứng dụng, JVM, Spring, Reactor và broker.
- Cấu hình instance, CPU, memory, thread pool, connection pool và broker.
- Load generator, số generator, loại workload và phân bố payload.
- Warm-up, ramp-up, steady-state và thời gian đo.
- Offered/accepted/completed throughput.
- p50/p95/p99, error rate, timeout, rejected và queue depth.
- Các dependency metrics cùng khoảng thời gian.
- Fault được tạo, thời điểm bắt đầu/kết thúc và recovery time.
- Giới hạn đo lường, sample size và các sự kiện làm nhiễu.

So sánh hai lần chạy chỉ khi workload, môi trường, thời gian và định nghĩa metric tương đương. Nếu cấu hình thay đổi, ghi lại chính xác để phân biệt cải thiện do code, do tài nguyên hay do workload nhẹ hơn.

Khi p99 tăng, không vội tăng CPU hoặc số instance. Phân rã latency để xác định nó tăng ở queue, broker, handler, database hay client. Nếu throughput không tăng dù scale application, hãy tìm bottleneck dùng chung. Nếu queue tăng nhưng CPU thấp, có thể consumer bị giới hạn bởi I/O hoặc một executor khác.

## 15. Những lỗi thường gặp

| Lỗi | Vì sao gây hiểu sai | Cách khắc phục |
| --- | --- | --- |
| Chỉ báo cáo average latency | Che giấu tail latency. | Báo p50, p95, p99 và phân bố mẫu. |
| Chỉ đo producer send rate | Không biết consumer xử lý được bao nhiêu. | Đo accepted, delivered, completed và acknowledged rate. |
| Dùng payload nhỏ duy nhất | Đánh giá thấp serialization, network và memory. | Dùng phân bố payload gần thực tế. |
| Chỉ test một connection | Không phản ánh connection/session scale. | Tăng session, subscription và connection churn. |
| Dùng closed model cho traffic cố định | Load giảm khi response chậm, che giấu overload. | Dùng open arrival rate cho workload phù hợp. |
| Dùng Thread.sleep để tạo tải | Không kiểm soát arrival rate hoặc concurrency. | Dùng load generator có scenario và pacing rõ ràng. |
| Lấy trung bình p99 các instance | Percentile không thể tổng hợp theo cách đó. | Gộp histogram buckets rồi tính quantile. |
| Bỏ qua queue depth | Không phát hiện backlog đang tích tụ. | Theo dõi queue, oldest message age và drain rate. |
| Test simple broker rồi kết luận production broker đủ tải | Broker trong bộ nhớ không đại diện broker thật. | Test với đúng broker relay/cluster production. |
| Chạy load generator cùng máy server | Generator cạnh tranh CPU/network và làm sai kết quả. | Tách generator, theo dõi tài nguyên phía load client. |
| Chỉ fault test khi không có tải | Không phát hiện backlog và retry amplification. | Tạo fault ở baseline, tải mục tiêu và burst có kiểm soát. |
| Retry không backoff | Làm dependency vừa phục hồi bị quá tải lần nữa. | Backoff, jitter, giới hạn retry và circuit breaker. |
| Dùng tag metric là requestId/sessionId | Tạo cardinality rất cao. | Dùng metric tags có tập giá trị hữu hạn; ID để ở log/trace. |
| Dừng test khi health check trở lại UP | Queue có thể vẫn còn backlog. | Chờ latency, error và queue trở lại steady state. |

## 16. Checklist trước khi công bố capacity

### Workload

- [ ] Workload phản ánh request rate, session, subscription, fan-out và payload thực tế.
- [ ] Đã chọn open/closed model phù hợp với hành vi hệ thống.
- [ ] Load generator có đủ tài nguyên và không phải bottleneck.
- [ ] Đã xác định thời gian warm-up, ramp-up, steady-state và ramp-down.

### Metrics và SLO

- [ ] Có p50, p95, p99 với sample size đủ lớn.
- [ ] Có offered, accepted, completed và acknowledged throughput.
- [ ] Có error, timeout, rejection, queue depth và consumer lag.
- [ ] Có metrics CPU, heap, GC, threads, network, database và broker.
- [ ] Đã định nghĩa SLO và ngưỡng abort trước khi chạy.

### Resilience

- [ ] Đã kiểm tra slow consumer, dependency latency và connection loss.
- [ ] Đã kiểm tra restart/failover trong phạm vi an toàn.
- [ ] Đã kiểm tra retry, backoff, idempotency và duplicate handling.
- [ ] Đã đo recovery time và backlog drain time.
- [ ] Đã xác nhận không có message loss ngoài semantics đã chấp nhận.

### Báo cáo

- [ ] Ghi phiên bản, cấu hình, môi trường và công cụ.
- [ ] Ghi sample size, thời gian chạy và định nghĩa percentile.
- [ ] Nêu mức tải cao nhất vẫn đạt SLO.
- [ ] Nêu bottleneck, headroom, giới hạn và các bước cải thiện.

## 17. Ghi nhớ

- Capacity là mức tải có thể duy trì trong khi vẫn đáp ứng SLO và không tích tụ backlog.
- p95/p99 cho thấy tail latency; average không đủ để đánh giá trải nghiệm ở tải cao.
- Đo cả offered, accepted, completed và acknowledged throughput.
- Workload cần phản ánh session, subscription, fan-out, payload, heartbeat và consumer behavior.
- Open model giữ arrival rate; closed model giữ số user và có thể che giấu overload.
- Dùng histogram buckets để tổng hợp percentile giữa nhiều instance; không lấy trung bình p95/p99.
- Với Spring Messaging, test đúng broker và protocol production; simple broker không đại diện cho broker relay.
- Fault injection cần có giả thuyết, phạm vi, ngưỡng dừng và đo recovery.
- Retry phải có backoff, jitter và idempotency phù hợp.
- Chỉ công bố capacity sau khi xác nhận SLO, queue stability, headroom và recovery.

## 18. Tài liệu tham khảo

- [Spring Boot Actuator — Metrics](https://docs.spring.io/spring-boot/reference/actuator/metrics.html): tích hợp Micrometer và endpoint metrics.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): Timer, histogram và percentile.
- [Micrometer — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html): client-side percentile và histogram buckets.
- [Prometheus — Histograms and summaries](https://prometheus.io/docs/practices/histograms/): cách tổng hợp histogram và tính quantile.
- [Prometheus — histogram_quantile](https://prometheus.io/docs/prometheus/latest/querying/functions/#histogram_quantile): hàm tính percentile từ histogram buckets.
- [Spring Framework — RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html): interaction models và tích hợp RSocket.
- [Spring Framework — STOMP over WebSocket](https://docs.spring.io/spring-framework/reference/web/websocket/stomp.html): simple broker, broker relay và message routing.
- [Google SRE Book — Monitoring Distributed Systems](https://sre.google/sre-book/monitoring-distributed-systems/): latency, traffic, errors và saturation.
- [Google SRE Workbook — Alerting on SLOs](https://sre.google/workbook/alerting-on-slos/): đo lường và cảnh báo theo SLO.
- [Gatling Documentation](https://docs.gatling.io/): xây dựng scenario và workload cho performance testing.
- [k6 Documentation — Scenarios](https://grafana.com/docs/k6/latest/using-k6/scenarios/): điều khiển workload và arrival rate.
