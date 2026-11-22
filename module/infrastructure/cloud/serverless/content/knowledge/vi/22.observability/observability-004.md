# Đo cold start, độ tuổi thông điệp và backlog

Ứng dụng serverless thường mở rộng theo request hoặc theo lượng công việc đang chờ. Khi lưu lượng tăng đột ngột, function có thể cần khởi tạo execution environment mới. Khi consumer xử lý chậm hơn tốc độ message được đưa vào queue, backlog tăng và thông điệp phải chờ lâu hơn trước khi được xử lý.

Ba tín hiệu giúp nhận ra các vấn đề này là:

- **Cold start:** thời gian khởi tạo execution environment hoặc instance mới trước khi workload sẵn sàng xử lý.
- **Message age:** thời gian một thông điệp đã tồn tại kể từ lúc được publish/enqueue đến một mốc xử lý xác định.
- **Backlog:** lượng công việc đang chờ hoặc chưa được xác nhận hoàn tất.

Không nên xem ba chỉ số này tách rời. Cold start có thể làm giảm tốc độ consumer trong lúc scale-out. Backlog tăng khiến message age tăng. Message age vượt SLA có thể gây lỗi nghiệp vụ dù function vẫn trả về thành công. Bài học này trình bày cách đo, phân tích và cảnh báo các tín hiệu đó trong hệ thống Java serverless.

## 1. Nhìn ba tín hiệu trong cùng một hệ thống

Giả sử một Java function tiêu thụ queue orders. Khi có đợt tăng traffic:

1. Producer gửi message nhanh hơn mức consumer đang xử lý.
2. Nền tảng tăng số execution environment hoặc instance.
3. Instance mới phải khởi tạo JVM, framework và dependency.
4. Trong thời gian cold start, năng lực xử lý chưa tăng ngay.
5. Backlog và tuổi message tăng.
6. Khi các instance mới sẵn sàng, throughput tăng và backlog có thể giảm.

~~~mermaid
flowchart TD
    P["Producer: message arrival rate tăng"] --> Q["Queue"]
    Q --> B["Backlog tăng"]
    B --> A["Autoscaler mở rộng consumer"]
    A --> C["Cold start: JVM và app initialization"]
    C --> W["Consumer capacity tăng"]
    W --> D["Message processing / ack"]
    D --> R["Backlog giảm nếu throughput > arrival rate"]
~~~

Một dashboard chỉ hiển thị số invocation và tỷ lệ lỗi có thể bỏ sót tình huống này. Consumer vẫn trả 2xx hoặc ack message, nhưng message phải đợi quá lâu trước khi được xử lý. Vì vậy, cần theo dõi thời gian chờ và lượng công việc tồn đọng cùng với thời gian khởi tạo.

## 2. Định nghĩa cold start

Cold start xảy ra khi nền tảng cần tạo một execution environment hoặc instance mới trước khi xử lý workload. Với Java, quá trình này có thể gồm:

- Chuẩn bị hoặc khởi chạy runtime.
- Khởi tạo JVM.
- Nạp class và thư viện.
- Chạy static initializer.
- Khởi tạo dependency injection container hoặc framework.
- Đọc cấu hình và secret reference.
- Tạo connection pool hoặc client.
- Chạy startup hook và readiness check.

Không phải mọi invocation đầu tiên của một function đều là cold start. Nền tảng có thể tái sử dụng execution environment đã khởi tạo cho nhiều invocation sau đó. Cold start thường xảy ra khi có environment mới do scale-out, thay thế instance hoặc không còn instance sẵn sàng.

Cold start là một phần của latency mà người dùng hoặc consumer cảm nhận, nhưng cách đo phụ thuộc nền tảng. AWS Lambda có log/runtime signal riêng cho initialization; Cloud Run và Knative thường cần kết hợp instance startup log, request latency và telemetry của ứng dụng để phân tích thời gian khởi động.

### 2.1. Phân biệt các khoảng thời gian

Đừng gộp mọi latency thành một con số. Các khoảng thời gian có thể gồm:

| Khoảng thời gian | Ý nghĩa |
|---|---|
| Provisioning/scheduling | Nền tảng cấp tài nguyên hoặc xếp lịch instance |
| Image pull | Tải container image nếu node chưa có image |
| Runtime initialization | Khởi tạo runtime/JVM |
| Application initialization | Khởi tạo framework, dependency và ứng dụng |
| Request/handler duration | Thời gian xử lý invocation hoặc request |
| Queue wait | Thời gian message chờ trước khi consumer bắt đầu |
| End-to-end processing | Từ lúc message được publish đến lúc xử lý/ack hoàn tất |

Metric Duration của Lambda thường phản ánh thời gian handler chạy; thông tin initialization có thể được ghi riêng. Một request đến Cloud Run có thể bao gồm thời gian chờ instance mới, nhưng không nên suy ra chính xác init duration chỉ từ request latency. Dùng platform logs/telemetry và custom startup timing để phân tách.

## 3. Đo cold start trên AWS Lambda

AWS Lambda ghi thông tin invocation vào CloudWatch Logs. Với execution environment có initialization, log report có thể chứa trường Init Duration. Trường này giúp phân tích thời gian khởi tạo riêng với thời gian handler.

Ví dụ log report minh họa:

~~~text
REPORT RequestId: 8a1... Duration: 42.31 ms
Billed Duration: 120 ms Memory Size: 1024 MB
Max Memory Used: 188 MB Init Duration: 77.64 ms
~~~

Các trường thực tế phụ thuộc runtime, loại invocation và tính năng đang bật. Không giả định mọi invocation đều có Init Duration; môi trường được tái sử dụng có thể không chạy initialization trong invocation đó.

Có thể dùng CloudWatch Logs Insights để tìm report có init duration:

~~~sql
filter @type = "REPORT"
| parse @message /Init Duration: (?<initMs>[0-9.]+) ms/
| filter ispresent(initMs)
| stats
    count() as coldStarts,
    avg(initMs) as avgInitMs,
    pct(initMs, 50) as p50InitMs,
    pct(initMs, 95) as p95InitMs,
    max(initMs) as maxInitMs
  by bin(5m)
~~~

Đây là truy vấn minh họa cho log format tương ứng. Hãy xác minh trường @type, nội dung report và cú pháp Logs Insights với log group/runtime thực tế. Nếu log format thay đổi, điều chỉnh parser thay vì xem kết quả rỗng là không có cold start.

### 3.1. Đếm cold start và tính tỷ lệ

Có thể tính tỷ lệ cold start trong một khoảng thời gian:

\[
\text{Cold start rate} =
\frac{\text{Số lần khởi tạo được quan sát}}
{\text{Tổng số invocation}}
\times 100\%
\]

Định nghĩa tử số phải nhất quán. Nếu dùng Init Duration report để đếm, đây là số initialization event quan sát được theo log, không nhất thiết là một metric chuẩn có sẵn cho mọi runtime.

Theo dõi cả:

- Số initialization trong mỗi phút.
- Tỷ lệ initialization trên invocation.
- p50/p95/p99 của init duration.
- p50/p95/p99 của handler duration.
- p50/p95/p99 latency đầu-cuối.
- Số instance/replica và concurrency.
- Tỷ lệ lỗi hoặc timeout trong các invocation có init.

Tỷ lệ cold start cao không tự động là vấn đề. Một workload batch có thể chấp nhận cold start nếu SLA rộng. Điều quan trọng là latency thực tế, tần suất và tác động đến message age hoặc request SLO.

### 3.2. Lambda Telemetry API và log-based metric

Lambda Telemetry API có thể cung cấp platform events liên quan đến vòng đời runtime và initialization cho extension đã đăng ký. Extension có thể dùng các event platform phù hợp để quan sát init và runtime lifecycle. Đây là cách tạo metric chi tiết hơn khi cần, nhưng cần quản lý overhead, buffering và lỗi của extension.

Một cách đơn giản hơn là tạo metric từ log chứa Init Duration hoặc dùng dashboard truy vấn Logs Insights. Log-based metric có độ trễ và giới hạn khác metric platform. Ghi rõ nguồn metric và khoảng thời gian cập nhật trên dashboard.

Không nên dùng biến static AtomicBoolean trong Java để kết luận cold start của nền tảng. Biến đó chỉ biết process này đã đi qua đoạn code hay chưa; nó không phân biệt chính xác lifecycle do provider quản lý, restore từ snapshot, nhiều classloader hoặc cách runtime khởi tạo. Dùng platform signal cho cold start và custom timing cho application initialization.

## 4. Đo cold start trên Cloud Run và Knative

Cloud Run và Knative chạy container, vì vậy cần quan sát lifecycle của instance cùng thời gian ứng dụng sẵn sàng. Các tín hiệu hữu ích gồm:

- Instance/container startup và shutdown logs.
- Thời điểm process bắt đầu.
- Thời điểm ứng dụng hoàn tất initialization.
- Thời điểm readiness probe thành công.
- Request đầu tiên trên instance.
- Request latency và concurrency.
- Số instance theo thời gian.
- Image pull/startup events nếu nền tảng cung cấp.

Java application có thể ghi log hai mốc riêng: app.initialization.started và app.ready. Chênh lệch giữa hai mốc phản ánh phần khởi tạo trong process. Thời gian từ lúc request đến đến lúc app sẵn sàng có thể còn bao gồm scheduling, image pull, network và ingress queueing.

Ví dụ ghi mốc startup trong Java:

~~~java
import java.time.Duration;
import java.time.Instant;

public final class ApplicationStartup {

    private static final Instant PROCESS_STARTED = Instant.now();

    private ApplicationStartup() {
    }

    public static void markReady() {
        Instant readyAt = Instant.now();
        long initializationMs =
                Duration.between(PROCESS_STARTED, readyAt).toMillis();

        System.out.printf(
                "{\"event\":\"app.ready\",\"initialization_ms\":%d}%n",
                initializationMs);
    }
}
~~~

Gọi markReady() sau khi các thành phần bắt buộc đã sẵn sàng, chẳng hạn sau khi Spring context khởi tạo xong và server bắt đầu nhận request. Nếu gọi quá sớm, metric sẽ đánh giá thấp startup time. Nếu startup có thành phần lazy-load, ghi nhận riêng thời gian khởi tạo của thành phần đó khi được sử dụng.

### 4.1. Tách application startup khỏi request latency

Một request đầu tiên có thể chậm do cache miss hoặc JIT compilation dù process đã sẵn sàng. Ngược lại, process startup có thể nhanh nhưng request đầu tiên chậm vì DNS, TLS hoặc database connection.

Do đó, đo riêng:

- Process initialization duration.
- Framework/context ready duration.
- First request latency trên instance.
- Warm request latency.
- Dependency connection/first-call latency.

So sánh các phân vị thay vì chỉ so sánh trung bình. p95/p99 thường thể hiện tail latency mà người dùng gặp phải.

## 5. Các yếu tố làm Java cold start tăng

| Yếu tố | Tác động | Cách đo/kiểm tra |
|---|---|---|
| Container image lớn | Tăng thời gian pull và khởi động | Image size, pull/start events |
| Nhiều dependency | Tăng class loading và initialization | Startup profile, class loading |
| Framework scanning | Tăng thời gian tạo context | Spring startup report hoặc profiler |
| Static initializer nặng | Kéo dài thời gian trước readiness | Startup log theo thành phần |
| Kết nối database sớm | Chờ network/TLS và pool initialization | Connection latency, pool metrics |
| Tải cấu hình hoặc secret | Thêm dependency call vào startup path | Secret/config request latency |
| Heap và CPU không phù hợp | GC hoặc initialization chậm | CPU, memory, GC logs |
| JIT warm-up | Request đầu có thể chậm hơn | So sánh first request và warm requests |

Các biện pháp tối ưu cần dựa trên profile. Chuyển toàn bộ initialization sang lazy loading có thể giảm startup nhưng làm request đầu tiên chậm hơn. Tăng CPU có thể rút ngắn init nhưng tăng chi phí. Giữ instance ấm có thể giảm cold start nhưng tiêu tốn compute khi không có traffic.

### 5.1. Provisioned concurrency, SnapStart và min instances

Các nền tảng cung cấp cách giảm tác động cold start khác nhau:

- **AWS Lambda Provisioned Concurrency:** chuẩn bị sẵn execution environments để xử lý invocation, đổi lại có chi phí duy trì mức capacity được provision.
- **AWS Lambda SnapStart:** tạo snapshot cho một số runtime/phiên bản Java được hỗ trợ để giảm thời gian khởi tạo khi restore. Cần kiểm tra runtime compatibility và yêu cầu xử lý dữ liệu/connection sau restore.
- **Cloud Run minimum instances:** giữ số instance tối thiểu, giảm khả năng phải khởi tạo từ zero nhưng có chi phí tài nguyên.
- **Knative min-scale:** giữ mức replica tối thiểu theo cấu hình autoscaler.

Các tính năng này giảm thời gian chờ ở một số giai đoạn, không loại bỏ mọi latency. Ví dụ, request vẫn có thể chậm do downstream service, DNS, database hoặc tải tăng vượt capacity đã giữ sẵn.

Không dùng scheduled ping hoặc keep-alive như bảo đảm instance luôn sẵn sàng. Nền tảng có thể tái chế environment; chỉ cấu hình capacity được hỗ trợ mới là cơ chế giữ sẵn có cam kết rõ ràng.

## 6. Định nghĩa message age

Message age là thời gian message đã tồn tại kể từ lúc producer publish/enqueue đến một mốc đo cụ thể.

Có ít nhất hai cách đo hữu ích:

\[
\text{Age at start} =
t_{\text{consumer start}} - t_{\text{published}}
\]

\[
\text{End-to-end age} =
t_{\text{processing complete}} - t_{\text{published}}
\]

- Age at start cho biết message đã chờ bao lâu trước khi consumer bắt đầu xử lý.
- End-to-end age cho biết message đã mất bao lâu để đi từ producer đến khi xử lý hoàn tất.

Nếu cần đo thời gian xử lý riêng:

\[
\text{Processing duration} =
t_{\text{processing complete}} - t_{\text{consumer start}}
\]

Ba metric này giúp phân biệt queue wait tăng với handler xử lý chậm.

### 6.1. Dùng timestamp nguồn đáng tin cậy

Timestamp publish nên được tạo tại producer hoặc lấy từ metadata của broker. Consumer cần parse timestamp theo UTC và ghi rõ đơn vị. Không dùng thời điểm nhận message ở consumer làm publish time vì như vậy age sẽ luôn gần bằng zero.

Đồng hồ giữa producer và consumer có thể lệch. Để giảm sai số:

- Đồng bộ clock của runtime bằng cơ chế thời gian của nền tảng.
- Dùng timestamp do broker cấp nếu có.
- Theo dõi clock skew khi age âm hoặc bất thường.
- Dùng cùng chuẩn UTC.
- Không chuyển timestamp sang local timezone trước khi tính duration.

Nếu broker cung cấp metric oldest message age, dùng metric đó để quan sát queue tổng thể và custom age trong consumer để quan sát message thực tế được xử lý. Hai metric có thể khác vì thời điểm lấy mẫu, semantics và độ trễ cập nhật.

## 7. Metric backlog là gì?

Backlog biểu diễn lượng công việc chưa hoàn tất tại một thời điểm. Cần hiểu trạng thái của từng hệ thống message để không đếm sai.

Một queue có thể có:

- **Visible/ready:** message đang chờ consumer nhận.
- **In-flight/invisible:** message đã được nhận nhưng chưa ack/delete hoặc lease chưa hết hạn.
- **Delayed/scheduled:** message chưa đến thời điểm được giao.
- **Dead-letter:** message đã bị chuyển sang vùng lỗi sau số lần thử hoặc policy.
- **Acknowledged/completed:** message đã được xác nhận xử lý thành công.

Với một số hệ thống, metric backlog chính chỉ tính message chưa được giao; với hệ thống khác, nó có thể tính cả unacked/in-flight. Hãy đọc định nghĩa của metric provider trước khi cộng hoặc so sánh.

Backlog count chỉ là số lượng. Một queue có 10.000 message nhỏ có thể xử lý nhanh hơn queue có 100 message nhưng mỗi message cần gọi nhiều API. Kết hợp count với message age, processing duration và throughput để hiểu mức độ ảnh hưởng.

## 8. Đo backlog theo nền tảng

Tên metric và semantics khác nhau giữa các broker. Ví dụ:

| Nền tảng | Metric thường dùng | Ý nghĩa cần theo dõi |
|---|---|---|
| Amazon SQS | ApproximateNumberOfMessagesVisible | Message đang chờ được nhận |
| Amazon SQS | ApproximateNumberOfMessagesNotVisible | Message đang in-flight/chưa visible |
| Amazon SQS | ApproximateAgeOfOldestMessage | Tuổi xấp xỉ của message cũ nhất theo semantics SQS |
| Google Pub/Sub | subscription/num_undelivered_messages | Số message chưa được giao/xác nhận theo metric subscription |
| Google Pub/Sub | subscription/oldest_unacked_message_age | Tuổi của message chưa ack cũ nhất |
| Kafka | Consumer group lag / records-lag-max | Chênh lệch offset giữa consumer và log end offset |
| Azure Service Bus | Active messages, Dead-lettered messages | Số message active và dead-letter trong entity |

Tên đầy đủ, đơn vị, sampling và availability có thể thay đổi theo dịch vụ/region/metric version. Kiểm tra CloudWatch, Cloud Monitoring, Azure Monitor hoặc exporter của Kafka đang dùng.

### 8.1. Amazon SQS

Với SQS, thường theo dõi cùng lúc:

- ApproximateNumberOfMessagesVisible: lượng message sẵn sàng nhận.
- ApproximateNumberOfMessagesNotVisible: lượng message đã nhận nhưng chưa xóa/ack.
- ApproximateAgeOfOldestMessage: tuổi xấp xỉ của message cũ nhất.
- NumberOfMessagesSent, NumberOfMessagesReceived, NumberOfMessagesDeleted: xu hướng publish, receive và delete.

Các metric SQS là approximate và được cập nhật theo chu kỳ; không dùng một điểm dữ liệu đơn lẻ để suy ra chính xác số message trong queue tại mọi mili giây. Theo dõi trend qua nhiều chu kỳ và đối chiếu với custom processing metrics.

Với standard queue, message có thể được nhận lại nếu visibility timeout hết trước khi consumer xóa message. Điều này làm số receive tăng và có thể tạo duplicate processing. Theo dõi receive count, retry và DLQ cùng với backlog.

### 8.2. Google Pub/Sub

Với Pub/Sub, subscription metrics giúp theo dõi lượng message chưa được xác nhận và tuổi của message cũ nhất chưa ack. Nếu consumer ack chậm, oldest unacked age có thể tăng ngay cả khi message mới vẫn được xử lý.

Theo dõi ack throughput, delivery throughput, outstanding messages và retry/dead-letter. Nếu subscription dùng ordering key hoặc flow control, một nhóm message bị chặn có thể làm một phần backlog tăng dù consumer tổng thể vẫn có capacity.

### 8.3. Kafka

Kafka consumer lag thường là chênh lệch offset giữa log end và offset đã commit của consumer group. Đây là số record/offset lag, không trực tiếp là tuổi theo giây.

Một topic có throughput thấp có thể có lag nhỏ nhưng message đã chờ lâu. Ngược lại, topic throughput cao có lag lớn nhưng age vẫn nằm trong SLA. Kết hợp consumer lag với timestamp của record và processing latency để đánh giá độ trễ thực tế.

## 9. Arrival rate, processing rate và drain time

Hai tốc độ quan trọng:

- **Arrival rate (\(\lambda\)):** số message được đưa vào mỗi giây.
- **Processing/ack rate (\(\mu\)):** số message được xử lý và xác nhận hoàn tất mỗi giây.

Nếu \(\mu > \lambda\), consumer có năng lực dư để xử lý backlog. Nếu \(\mu = \lambda\), backlog hiện có gần như không giảm. Nếu \(\mu < \lambda\), backlog tiếp tục tăng.

Với backlog hiện tại \(B\), giả sử arrival và processing rate tương đối ổn định, thời gian ước lượng để xóa backlog là:

\[
T_{\text{drain}} \approx \frac{B}{\mu-\lambda}
\quad \text{khi } \mu > \lambda
\]

Ví dụ, queue có 12.000 message, consumer xử lý 500 message/giây và producer tiếp tục gửi 200 message/giây:

\[
T_{\text{drain}} \approx \frac{12.000}{500-200}=40 \text{ giây}
\]

Nếu producer dừng gửi, thời gian lý tưởng là \(B/\mu\). Công thức chỉ là ước lượng; throughput thực tế thay đổi theo batch size, message complexity, retry, scaling, throttling và giới hạn downstream.

### 9.1. Ước lượng capacity từ concurrency

Nếu mỗi instance xử lý tối đa \(c\) message đồng thời, thời gian xử lý trung bình một message là \(d\) giây và mỗi lần nhận xử lý batch \(b\) message, throughput lý tưởng gần đúng là:

\[
\mu \approx \frac{c \times b}{d}
\]

Đây là mô hình đơn giản. Batch processing có thể chạy tuần tự hoặc song song; concurrency có thể bị giới hạn bởi thread pool, CPU, memory, database connection hoặc broker. Dùng throughput đo được trong production-like load test để lập kế hoạch capacity.

Không tăng concurrency vô hạn chỉ để làm backlog giảm. Nếu mỗi message gọi database, concurrency cao có thể làm database quá tải, tăng latency và retry, khiến throughput cuối cùng thấp hơn.

## 10. Đo message age trong Java consumer

Một Java consumer nên ghi nhận ít nhất:

- Thời điểm bắt đầu xử lý.
- Publish/enqueue timestamp.
- Message age lúc bắt đầu.
- Processing duration.
- Kết quả: success, retryable failure hoặc permanent failure.
- Batch size nếu nhận theo batch.
- Consumer/service version và queue name.

Ví dụ dùng Micrometer để ghi age và processing duration. publishedAt được lấy từ metadata đáng tin cậy của message:

~~~java
import io.micrometer.core.instrument.DistributionSummary;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;

import java.time.Duration;
import java.time.Instant;

public final class MessageMetrics {

    private final MeterRegistry registry;
    private final Timer processingTimer;
    private final DistributionSummary ageSummary;

    public MessageMetrics(MeterRegistry registry) {
        this.registry = registry;
        this.processingTimer = Timer.builder("serverless.message.processing")
                .description("Time spent processing a message")
                .tag("queue", "orders")
                .tag("consumer", "orders-worker")
                .register(registry);

        this.ageSummary = DistributionSummary
                .builder("serverless.message.age")
                .baseUnit("milliseconds")
                .description("Message age when processing starts")
                .tag("queue", "orders")
                .tag("consumer", "orders-worker")
                .register(registry);
    }

    public Timer.Sample start(Instant publishedAt) {
        Instant startedAt = Instant.now();
        long ageMs = Duration.between(publishedAt, startedAt).toMillis();

        if (ageMs >= 0) {
            ageSummary.record(ageMs);
        } else {
            registry.counter(
                    "serverless.message.clock_skew",
                    "queue", "orders",
                    "consumer", "orders-worker"
            ).increment();
        }

        return Timer.start(registry);
    }

    public void stop(Timer.Sample sample) {
        sample.stop(processingTimer);
    }
}
~~~

Trong code thực, tạo Timer.Sample ngay trước khi xử lý và gọi stop trong finally để ghi cả trường hợp thành công lẫn thất bại. Có thể ghi outcome bằng một Counter riêng với tập giá trị cố định như success, retryable_error, permanent_error.

Không đưa messageId, orderId, customerId, trace ID hoặc exception message vào metric tags. Những giá trị này có cardinality cao; hãy ghi vào log hoặc trace đã kiểm soát.

### 10.1. Đo end-to-end age

Nếu cần đo đến lúc message được ack hoặc xử lý hoàn tất, ghi thêm timestamp hoàn tất:

~~~java
Instant completedAt = Instant.now();
long endToEndAgeMs =
        Duration.between(publishedAt, completedAt).toMillis();
~~~

Nếu ack được thực hiện bất đồng bộ sau khi handler trả về, timestamp hoàn tất trong code chưa chắc là thời điểm broker xác nhận. Khi cần SLA chính xác đến ack, đo tại nơi ack/delete thành công hoặc dùng broker telemetry.

Đối với batch, ghi age cho từng message hoặc phân phối theo batch với sampling có kiểm soát. Nếu chỉ ghi timestamp của message đầu tiên trong batch, metric không phản ánh đúng độ tuổi của tất cả message.

## 11. Backlog age và backlog count cần được đọc cùng nhau

Một số tình huống điển hình:

| Backlog count | Oldest message age | Cách diễn giải |
|---|---|---|
| Thấp | Thấp | Queue đang ổn định |
| Cao | Thấp | Producer vừa tạo burst; consumer có thể đang xử lý tốt |
| Cao | Cao | Consumer thiếu capacity, lỗi hoặc dependency chậm |
| Thấp | Cao | Có thể có message poison, partition/group bị chặn hoặc traffic rất thấp nhưng một message cũ bị kẹt |
| Giảm | Vẫn cao | Queue đang drain nhưng message cũ chưa được xử lý hết |
| Không đổi | Tăng | Arrival và processing có thể cân bằng ở mức backlog cao hoặc consumer không tiến triển |

Oldest age thường là tín hiệu gần với trải nghiệm nghiệp vụ hơn số lượng backlog. Tuy nhiên, nếu chỉ theo dõi age, một burst lớn của message mới có thể bị bỏ qua trước khi message cũ vượt ngưỡng. Kết hợp age, count, throughput và retry/DLQ.

Với Kafka, lag count cần đi cùng record age. Với SQS/Pub/Sub, dùng oldest message age theo semantics của broker và custom age của consumer để đối chiếu.

## 12. Dashboard quan sát cold start và queue

Một dashboard hữu ích có thể chia thành bốn nhóm:

**Startup và latency**

- Init duration p50/p95/p99.
- Cold start count/rate.
- Application initialization duration.
- First request latency và warm request latency.
- Handler/processing duration.

**Queue health**

- Visible/ready backlog.
- In-flight/unacked messages.
- Oldest message age.
- Dead-letter count.
- Retry/receive count.

**Capacity và throughput**

- Arrival rate.
- Processing/ack rate.
- Active instances/replicas.
- Concurrency và batch size.
- Estimated drain time.
- CPU, memory, connection pool và throttling.

**Business SLO**

- Tỷ lệ message được xử lý trước deadline.
- p95/p99 end-to-end age.
- Số message vượt SLA.
- Số đơn hàng/job bị trễ.
- Số compensation hoặc manual recovery do xử lý trễ.

Nên đặt các biểu đồ trên cùng một timeline để nhìn thấy quan hệ: instance count tăng, cold start tăng, processing rate thay đổi và backlog age phản ứng ra sao.

## 13. Cảnh báo dựa trên SLO

Không dùng một ngưỡng cố định cho mọi queue. Queue gửi email có thể chấp nhận age vài phút; queue cập nhật tồn kho hoặc payment event có thể cần SLA chặt hơn.

Ví dụ policy minh họa:

| Tín hiệu | Điều kiện cảnh báo |
|---|---|
| Oldest message age | Vượt 70% thời hạn xử lý nghiệp vụ trong nhiều chu kỳ |
| Backlog | Tăng liên tục trong khi processing rate thấp hơn arrival rate |
| Drain time | Ước lượng vượt thời gian còn lại trước SLA deadline |
| DLQ | Có message mới hoặc số lượng tăng |
| Cold start | p95 init duration tăng đồng thời p95 request/message latency vượt SLO |
| Consumer errors | Retry, timeout hoặc throttling tăng đột biến |
| Capacity | Max concurrency/instance cap đạt giới hạn trong khi backlog tiếp tục tăng |

Dùng warning và critical threshold. Cảnh báo dựa trên nhiều chu kỳ hoặc cửa sổ thời gian giúp tránh alert do một điểm metric nhiễu. Với DLQ, một message có thể đủ nghiêm trọng để phát cảnh báo ngay tùy nghiệp vụ.

Alert cần chỉ ra queue, consumer, environment, region, metric, thời gian vượt ngưỡng và runbook. Không gửi message ID hoặc dữ liệu nhạy cảm vào nội dung alert nếu không cần.

### 13.1. Tính tỷ lệ message đúng hạn

Một SLI có thể là tỷ lệ message được xử lý trong thời hạn D:

\[
\text{On-time processing ratio} =
\frac{\text{Số message có end-to-end age} \leq D}
{\text{Tổng message đã xử lý}}
\times 100\%
\]

Định nghĩa rõ mẫu số: message đã hoàn tất trong cửa sổ đo, message được nhận hay message được publish. Nếu chỉ tính message đã hoàn tất, backlog chưa xử lý có thể bị bỏ khỏi phép tính và làm SLI trông tốt giả tạo. Nên có thêm chỉ số số message đang chờ đã vượt hoặc sắp vượt deadline.

## 14. Điều tra khi backlog tăng

Khi backlog tăng, kiểm tra theo thứ tự:

1. **Arrival rate:** producer có gửi nhiều hơn bình thường không?
2. **Processing rate:** số message được xử lý/ack mỗi giây có giảm không?
3. **Consumer capacity:** số instance, concurrency và batch size có đạt giới hạn không?
4. **Cold start:** scale-out có bị chậm do image, JVM hoặc initialization không?
5. **Processing duration:** một message có chậm hơn do code hoặc dependency không?
6. **Errors/retries:** message có bị retry nhiều lần hoặc visibility timeout lặp không?
7. **Downstream limits:** database, API hoặc connection pool có throttling không?
8. **Poison message:** một message lỗi có chặn partition, message group hoặc retry loop không?
9. **DLQ:** message có bị chuyển sang DLQ và bị bỏ khỏi metric source queue không?
10. **Configuration:** timeout, visibility/ack deadline, max concurrency và batch size có hợp lý không?

Không giải quyết mọi backlog bằng cách tăng concurrency. Nếu processing rate thấp do database throttling, tăng số consumer sẽ làm downstream quá tải hơn. Cần xác định bottleneck trước.

### 14.1. Ví dụ phân tích

Giả sử dashboard cho thấy:

- Arrival rate: 800 message/giây.
- Processing/ack rate: 500 message/giây.
- Backlog: tăng 18.000 message trong một phút.
- Oldest message age: tăng từ 8 lên 55 giây.
- Consumer instances: đã chạm max scale.
- Database latency p95: tăng gấp ba.

Tín hiệu này cho thấy capacity đang thấp hơn arrival rate và downstream database có thể là bottleneck. Việc tăng max scale ngay có thể làm database quá tải. Hãy xem connection pool, query latency, batch size và mức concurrency an toàn trước khi tăng consumer capacity.

Nếu arrival rate trở về 300 message/giây và processing rate duy trì 500 message/giây, backlog 18.000 message có drain time ước tính:

\[
T_{\text{drain}} \approx \frac{18.000}{500-300}=90 \text{ giây}
\]

Theo dõi age trong quá trình drain để xác nhận message cũ đang được xử lý và SLA phục hồi.

## 15. Điều tra cold start tăng

Nếu cold start tăng cùng lúc với latency, kiểm tra:

- Có burst traffic hoặc scale-out bất thường không?
- Min instances/provisioned concurrency có thay đổi không?
- Có deploy image mới hoặc tăng kích thước image không?
- Framework hoặc dependency có thêm startup hook không?
- JVM heap/CPU có bị giới hạn?
- Secret/config/database connection có được tải đồng bộ khi startup?
- Node/region có thiếu capacity hoặc image cache không?
- Có thay đổi runtime version hoặc snapshot configuration không?

So sánh revision hiện tại với revision trước theo cùng traffic profile. Một deploy có thể không làm average latency thay đổi nhiều nhưng p99 tăng mạnh vì init path dài hơn.

Không chỉ so sánh số cold start tuyệt đối. Khi invocation tăng gấp mười, số cold start có thể tăng dù tỷ lệ cold start giảm. Dùng cả count và rate.

## 16. Visibility timeout, ack deadline và retry

Queue consumer thường cần thời gian để xử lý message rồi xác nhận hoàn tất. Nếu lease/visibility/ack deadline quá ngắn, broker có thể giao lại message trong khi worker cũ vẫn xử lý. Điều này tạo duplicate và tăng backlog/in-flight count.

Nếu deadline quá dài, message bị kẹt có thể mất nhiều thời gian mới được giao lại sau khi worker chết.

Hãy kiểm tra:

- Thời gian xử lý p95/p99.
- Timeout của handler và downstream call.
- Visibility timeout hoặc ack deadline.
- Heartbeat/lease extension nếu có.
- Số lần delivery/receive.
- Retry backoff và DLQ policy.
- Idempotency của side effect.

Thời gian visibility/ack nên có khoảng an toàn so với thời gian xử lý dự kiến và cần được gia hạn đúng cách nếu workload dài. Không chỉ đặt timeout thật lớn; timeout dài làm chậm phục hồi khi consumer chết.

Với SQS Lambda event source mapping, cấu hình batch size, maximum batching window và visibility timeout cần được phối hợp theo hướng dẫn của dịch vụ. Với Pub/Sub, ack deadline và ack extension cần phù hợp với thời gian xử lý. Với Kafka, offset commit và consumer rebalancing có semantics khác; không áp dụng visibility timeout của queue khác vào Kafka.

## 17. Batch size và partial failure

Batching có thể tăng throughput và giảm overhead, nhưng một message lỗi có thể ảnh hưởng đến cả batch nếu consumer không hỗ trợ partial batch response hoặc không phân loại lỗi đúng.

Theo dõi:

- Batch size thực tế.
- Batch processing duration.
- Số message thành công/thất bại trong batch.
- Tỷ lệ batch retry.
- Age của message cũ nhất trong batch.
- Số record bị poison hoặc gửi DLQ.

Với AWS Lambda event source mapping, một số nguồn hỗ trợ partial batch response để chỉ yêu cầu retry các record lỗi. Cấu hình response đúng theo event source. Với Kafka hoặc broker khác, cơ chế commit/ack có quy tắc riêng.

Không chỉ đo một processing duration cho batch mà bỏ qua message age của từng record. Một batch có thể chứa message mới và message cũ; SLO cần phản ánh record đã chờ lâu nhất hoặc phân phối age phù hợp.

## 18. OpenTelemetry và metric cardinality

Có thể chuẩn hóa telemetry theo service name, service version, environment, queue/consumer và region. Các metric quan trọng gồm:

~~~text
serverless.cold_start.count
serverless.initialization.duration
serverless.message.age
serverless.message.processing
serverless.message.processed
serverless.message.failed
serverless.queue.backlog
serverless.queue.oldest_message_age
serverless.queue.arrival_rate
serverless.queue.ack_rate
serverless.queue.drain_time
~~~

Đây là tên metric gợi ý; quy ước naming, unit và instrument type cần thống nhất trong hệ thống. Dùng histogram/distribution cho duration và age; counter cho số message và lỗi; gauge cho backlog/current concurrency; rate được tính từ counter trong backend metric.

Giữ metric attributes có cardinality thấp:

~~~text
service.name=orders-worker
deployment.environment.name=production
messaging.destination.name=orders
messaging.operation=process
cloud.region=asia-southeast1
outcome=success
~~~

Không gắn message.id, order.id, customer.id, execution.arn hoặc exception text vào metric labels. Đặt các giá trị định danh trong log hoặc trace khi cần điều tra.

## 19. Kiểm thử và benchmark

Cần kiểm tra cả startup và queue behavior trong môi trường gần production:

1. Gửi một request/message khi không có instance sẵn sàng để quan sát cold start.
2. Gửi burst để kích hoạt scale-out.
3. So sánh warm và cold latency.
4. Tăng dần arrival rate để tìm ngưỡng throughput ổn định.
5. Tạo backlog lớn rồi đo drain time.
6. Làm chậm database/API để xem backpressure và alert.
7. Tạo message lỗi để kiểm tra retry, poison message và DLQ.
8. Dừng consumer khi message đang in-flight để kiểm tra redelivery.
9. Kiểm tra ack/visibility timeout với xử lý gần deadline.
10. Deploy revision mới và so sánh init duration.
11. Kiểm tra dashboard có phân biệt visible, in-flight và DLQ không.
12. Xác minh alert kích hoạt khi age hoặc drain time vượt SLO.

Đừng chạy load test vào production queue có dữ liệu khách hàng hoặc side effect thật. Dùng queue, database và provider sandbox riêng. Đặt giới hạn chi phí và cleanup sau khi test.

## 20. Runbook xử lý message age vượt SLA

Khi oldest message age vượt ngưỡng critical:

1. Xác định queue, subscription hoặc consumer group bị ảnh hưởng.
2. So sánh arrival rate với processing/ack rate.
3. Kiểm tra backlog count, in-flight và DLQ.
4. Kiểm tra số consumer instance, max scale và concurrency.
5. Xem cold start và initialization duration sau lần deploy gần nhất.
6. Kiểm tra processing duration, timeout, retry và downstream latency.
7. Nếu dependency bị quá tải, giảm hoặc giới hạn concurrency để bảo vệ dependency.
8. Nếu consumer có capacity dư và dependency khỏe, tăng capacity có kiểm soát.
9. Xử lý poison message hoặc partition bị chặn theo DLQ/replay policy.
10. Theo dõi drain time và oldest age đến khi trở lại trong SLO.
11. Lưu execution/message correlation để post-incident review.

Khi replay DLQ, phải giữ idempotency key hoặc business identity để không tạo side effect trùng. Không xóa message lỗi chỉ để dashboard xanh; ghi nhận quyết định discard/replay và lý do.

## 21. Quy trình thiết kế observability cho Java serverless

1. **Định nghĩa SLO.** Xác định thời gian tối đa từ publish đến xử lý hoàn tất.
2. **Chọn metric platform.** Dùng init duration, instance count, queue age và backlog metric có sẵn.
3. **Bổ sung custom timing.** Đo application startup, message age và processing duration.
4. **Đo throughput.** Tính arrival, processing/ack rate và drain time.
5. **Phân biệt trạng thái queue.** Ready, in-flight/unacked, delayed và DLQ.
6. **Chuẩn hóa telemetry.** Dùng service/environment/queue attributes ổn định.
7. **Thiết kế dashboard.** Hiển thị startup, latency, backlog, throughput, errors và SLO cùng timeline.
8. **Đặt alert theo deadline.** Cảnh báo sớm trước khi message vượt SLA và cảnh báo DLQ theo mức rủi ro.
9. **Kiểm thử failure mode.** Burst, cold start, dependency slowdown, retry và consumer crash.
10. **Viết runbook.** Hướng dẫn xác định bottleneck và drain backlog an toàn.

Cold start cho biết chi phí khởi tạo compute; message age cho biết công việc đã chờ bao lâu; backlog cho biết còn bao nhiêu công việc chưa hoàn tất. Khi đo cả ba cùng arrival rate, processing rate và downstream health, đội vận hành có thể phân biệt vấn đề do scale-up, consumer capacity hay dependency và chọn cách phục hồi phù hợp.

## 22. Câu hỏi tự kiểm tra

- Cold start khác warm invocation ở điểm nào?
- Vì sao không thể dùng một biến static trong Java để đo chính xác mọi cold start?
- AWS Lambda ghi nhận initialization duration ở đâu?
- Cloud Run/Knative cần những mốc nào để tách process startup khỏi first request latency?
- Message age at start khác end-to-end age ra sao?
- Vì sao phải dùng timestamp publish đáng tin cậy?
- Backlog visible khác in-flight/unacked như thế nào?
- SQS, Pub/Sub và Kafka biểu diễn backlog/lag khác nhau ra sao?
- Điều gì xảy ra khi processing rate thấp hơn arrival rate?
- Công thức drain time có giả định nào?
- Vì sao tăng concurrency có thể làm backlog tệ hơn?
- Visibility timeout hoặc ack deadline quá ngắn gây vấn đề gì?
- Vì sao phải theo dõi DLQ cùng source queue?
- Metric nào phù hợp làm alert gần với message processing SLO?
- Vì sao không đưa message ID hoặc trace ID vào metric labels?

