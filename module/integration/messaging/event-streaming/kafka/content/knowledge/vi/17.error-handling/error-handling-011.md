# Kiểm soát retry storm và giới hạn tài nguyên phục hồi

## Retry có thể giúp phục hồi, nhưng retry không giới hạn có thể làm sự cố nặng hơn

Kafka producer và consumer thường phải xử lý lỗi tạm thời như broker chuyển leader, request timeout, network chập chờn hoặc dịch vụ downstream quá tải. Retry giúp thao tác có cơ hội thành công khi lỗi biến mất. Tuy nhiên, nếu nhiều client cùng retry ngay lập tức, retry không giới hạn hoặc mỗi tầng ứng dụng tự retry độc lập, hệ thống có thể rơi vào **retry storm**: lượng request tăng đúng lúc năng lực phục vụ đang giảm.

Retry storm thường tạo vòng lặp khuếch đại:

1. Một broker hoặc dịch vụ downstream bắt đầu chậm.
2. Request timeout tăng, client retry.
3. Retry chiếm connection, thread, CPU, buffer và băng thông.
4. Request hợp lệ bị chậm thêm, timeout nhiều hơn.
5. Nhiều client cùng retry khiến tải tăng theo cấp số nhân hoặc theo từng đợt đồng bộ.

Với hệ thống KAFKA, cần kiểm soát retry ở producer, consumer, listener container và tầng nghiệp vụ; đồng thời giới hạn concurrency, buffer, thời gian xử lý và tốc độ replay. Mục tiêu là phục hồi có kiểm soát, giữ consumer lag trong giới hạn và bảo vệ broker cũng như các dịch vụ phụ thuộc.

## 1. Phân biệt các loại retry

### 1.1 Retry nội bộ của Kafka producer

Kafka producer có cơ chế retry request khi gặp một số lỗi có thể phục hồi, ví dụ leader đang chuyển đổi hoặc request bị timeout. Client quản lý retry, sequence number và delivery deadline. Với idempotence được bật, retry ở tầng producer được thiết kế để tránh ghi trùng batch trong phạm vi bảo đảm của idempotent producer.

Các cấu hình quan trọng:

| Cấu hình | Vai trò |
|---|---|
| `delivery.timeout.ms` | Tổng thời gian tối đa để một record được gửi thành công, tính cả chờ batch và retry |
| `request.timeout.ms` | Thời gian chờ phản hồi cho một request |
| `retry.backoff.ms` | Khoảng nghỉ ban đầu giữa các lần retry |
| `retry.backoff.max.ms` | Giới hạn trên của khoảng nghỉ retry ở các client hỗ trợ cấu hình này |
| `enable.idempotence` | Bảo vệ khỏi duplicate do retry của producer trong phạm vi Kafka hỗ trợ |
| `max.block.ms` | Giới hạn thời gian các thao tác như `send()` có thể block khi chờ metadata hoặc buffer |
| `buffer.memory` | Bộ nhớ producer dành cho record đang chờ gửi |

`retries` không nên được xem như một ngân sách thời gian độc lập. `delivery.timeout.ms` là giới hạn tổng quan trọng đối với thời gian gửi một record. Cần bảo đảm `delivery.timeout.ms` không nhỏ hơn tổng `request.timeout.ms` và `linger.ms` theo ràng buộc của Kafka client.

Retry nội bộ của producer không thay thế retry nghiệp vụ. Nếu ứng dụng nhận lỗi cuối cùng rồi tự gửi lại record như một thao tác mới, đó là một lần gửi mới và có thể tạo duplicate nếu lần gửi trước thực tế đã được broker chấp nhận nhưng phản hồi bị mất. Dùng event ID/idempotency key và thiết kế consumer idempotent cho tình huống này.

### 1.2 Retry ở consumer/listener

Consumer có thể gặp lỗi khi xử lý record, chẳng hạn database tạm thời không truy cập được, API downstream trả 503 hoặc rate limit. Retry ở listener thường chạy lại xử lý record hiện tại. Nếu retry block trên consumer thread quá lâu, consumer có thể không gọi `poll()` kịp thời và vượt `max.poll.interval.ms`, dẫn đến rebalance.

Retry ở tầng consumer cần quyết định:

- Lỗi nào có thể retry: timeout, lỗi kết nối, HTTP 429/503, deadlock tạm thời.
- Lỗi nào không nên retry: dữ liệu sai schema, vi phạm quy tắc nghiệp vụ, thiếu trường bắt buộc, quyền truy cập bị từ chối cho đến khi cấu hình được sửa.
- Retry bao nhiêu lần, trong bao lâu và với backoff nào.
- Khi hết ngân sách retry thì dừng, đưa vào DLT hay chuyển sang luồng xử lý thủ công.

### 1.3 Retry ở tầng nghiệp vụ hoặc HTTP client

Một record có thể đi qua nhiều tầng: Kafka listener, service, repository và HTTP client. Nếu mỗi tầng tự retry 3 lần, một record có thể tạo đến \(3 \times 3 \times 3 = 27\) lần gọi downstream. Đây là retry amplification.

Chọn một tầng chịu trách nhiệm chính cho retry của từng dependency. Các tầng thấp hơn có thể có retry rất hạn chế cho lỗi kết nối an toàn, nhưng tổng số attempt phải nằm trong một ngân sách chung và không vượt deadline của nghiệp vụ.

## 2. Phân loại lỗi trước khi retry

Không phải lỗi nào cũng sẽ tự biến mất sau một khoảng chờ. Phân loại lỗi giúp tránh tiêu tốn tài nguyên vào những request chắc chắn thất bại.

| Nhóm lỗi | Ví dụ | Hành động gợi ý |
|---|---|---|
| Lỗi tạm thời | Timeout, connection reset, leader transition | Retry có backoff và giới hạn |
| Quá tải | HTTP 429, 503, throttling | Giảm tốc độ, tôn trọng `Retry-After` nếu có, retry có jitter |
| Lỗi dữ liệu | JSON sai, schema không hợp lệ, thiếu key bắt buộc | Không retry; đưa DLT hoặc quarantine |
| Lỗi nghiệp vụ vĩnh viễn | Trạng thái đơn hàng không cho phép chuyển bước | Không retry tự động; ghi nhận để xử lý nghiệp vụ |
| Lỗi cấu hình/quyền | ACL denied, sai credential, topic không tồn tại do cấu hình | Dừng retry dày; cảnh báo và sửa cấu hình |
| Lỗi không rõ nguyên nhân | Exception chưa phân loại | Retry rất hạn chế, log đủ ngữ cảnh và đưa vào điều tra |

Phân loại theo exception cụ thể của client và dependency. Ví dụ, HTTP 401 thường cần sửa credential; retry liên tục không làm credential đúng hơn. HTTP 429 có thể yêu cầu giảm tốc độ thay vì tăng số request.

Với Kafka producer, nhiều lỗi được client phân loại và retry tự động. Không tự retry lại mọi `KafkaException` bằng một vòng lặp chung. Một số lỗi là fatal hoặc cần tạo lại producer; một số lỗi chỉ có thể xử lý sau khi abort transaction. Tuân theo trạng thái và loại exception mà Kafka client đang dùng cung cấp.

## 3. Exponential backoff và jitter

### 3.1 Vì sao không retry ngay lập tức?

Retry ngay lập tức tạo tải liên tục lên thành phần đang lỗi. Nếu hàng nghìn consumer cùng retry sau một timeout, chúng có thể gửi một đợt request mới cùng thời điểm. Khi request lại thất bại, đợt tiếp theo tiếp tục dồn vào hệ thống.

Exponential backoff tăng khoảng nghỉ sau mỗi lần thất bại. Một dạng cơ bản:

\[
delay_n = \min(maxDelay, initialDelay \times multiplier^n)
\]

Ví dụ `initialDelay=200 ms`, `multiplier=2`, `maxDelay=5 s` tạo các khoảng nghỉ cơ sở 200 ms, 400 ms, 800 ms, 1.6 s, 3.2 s, sau đó giữ ở mức tối đa 5 s.

### 3.2 Jitter tránh đồng bộ retry

Nếu mọi client dùng cùng một lịch backoff, chúng vẫn có thể retry cùng thời điểm. Jitter thêm độ ngẫu nhiên vào thời gian chờ.

Một lựa chọn là *full jitter*:

\[
delay_n = random(0, \min(maxDelay, initialDelay \times 2^n))
\]

Full jitter phân tán retry trong một khoảng thời gian, giảm khả năng hàng nghìn client cùng gửi request tại một mốc. Có thể dùng equal jitter hoặc decorrelated jitter tùy thư viện và đặc điểm tải.

### 3.3 Ví dụ Java tạo full-jitter delay

```java
import java.time.Duration;
import java.util.concurrent.ThreadLocalRandom;

Duration fullJitterDelay(
        int attempt,
        Duration initial,
        Duration maximum) {

    long initialMs = initial.toMillis();
    long maximumMs = maximum.toMillis();
    int exponent = Math.min(attempt, 30);

    double exponential = initialMs * Math.pow(2.0, exponent);
    long cap = (long) Math.min(maximumMs, exponential);
    long delay = ThreadLocalRandom.current().nextLong(cap + 1);
    return Duration.ofMillis(delay);
}
```

Đoạn code là ví dụ cho attempt được đánh số từ 0. Trong production cần kiểm tra giá trị đầu vào, overflow và giới hạn delay. Không dùng `Thread.sleep()` trên Kafka consumer thread để thực hiện retry dài; hãy dùng retry topic hoặc cơ chế pause/scheduler phù hợp.

### 3.4 Backoff phải nằm trong deadline

Một request nghiệp vụ thường có deadline. Tổng thời gian retry phải nhỏ hơn thời gian còn lại của deadline:

\[
T_{attempts} + T_{backoff} \leq T_{remaining}
\]

Nếu deadline còn 2 giây mà backoff tiếp theo là 5 giây, không nên tiếp tục retry. Dừng sớm, trả lỗi hoặc chuyển sang xử lý bất đồng bộ.

Khi dependency trả `Retry-After`, có thể dùng giá trị đó làm thời gian chờ tối thiểu, sau đó thêm jitter trong giới hạn deadline và chính sách của hệ thống.

## 4. Retry budget và giới hạn attempt

### 4.1 Giới hạn số lần thử

Đặt `maxAttempts` cho từng loại lỗi. Cần làm rõ số attempt bao gồm lần gọi đầu tiên hay chỉ số lần retry. Ví dụ `maxAttempts=4` có thể nghĩa là 1 lần ban đầu và tối đa 3 lần retry.

Giới hạn attempt ngăn một record lỗi giữ tài nguyên vô thời hạn. Tuy nhiên, chỉ giới hạn attempt chưa đủ: nếu mỗi attempt chờ lâu, thời gian xử lý vẫn có thể vượt SLA. Kết hợp giới hạn số lần với deadline tổng.

### 4.2 Retry budget theo tỷ lệ lưu lượng

Retry budget giới hạn lượng request retry so với request gốc trong một cửa sổ thời gian. Ví dụ minh họa: chỉ cho phép retry tối đa 10% số request gốc trong mỗi phút. Khi budget cạn, hệ thống ngừng retry hoặc chuyển sang hàng đợi phục hồi.

Tỷ lệ cụ thể phải dựa trên năng lực dependency. Không coi 10% là giá trị mặc định cho mọi hệ thống. Với một dependency đang quá tải, budget có thể phải giảm về gần 0 để bảo vệ nó.

### 4.3 Không nhân retry qua nhiều tầng

Nếu Kafka listener retry 5 lần và HTTP client retry 4 lần, một record có thể gây 20 request downstream. Tính tổng attempt của toàn bộ call chain, không chỉ một thư viện.

Thiết kế một ngân sách thống nhất:

- Kafka producer retry theo delivery deadline của producer.
- Consumer retry theo policy của listener hoặc retry topic.
- HTTP/database client retry rất hạn chế cho lỗi transient an toàn.
- Tầng orchestration dừng retry khi deadline hoặc retry budget đã hết.

## 5. Giới hạn retry trong Kafka producer

### 5.1 Cấu hình Java producer

Ví dụ cấu hình giới hạn thời gian gửi và backoff:

```java
Properties props = new Properties();
props.put(ProducerConfig.BOOTSTRAP_SERVERS_CONFIG, "localhost:9092");
props.put(ProducerConfig.KEY_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class.getName());
props.put(ProducerConfig.VALUE_SERIALIZER_CLASS_CONFIG,
        StringSerializer.class.getName());

props.put(ProducerConfig.ENABLE_IDEMPOTENCE_CONFIG, true);
props.put(ProducerConfig.ACKS_CONFIG, "all");
props.put(ProducerConfig.REQUEST_TIMEOUT_MS_CONFIG, 30000);
props.put(ProducerConfig.DELIVERY_TIMEOUT_MS_CONFIG, 120000);
props.put(ProducerConfig.RETRY_BACKOFF_MS_CONFIG, 500);
props.put(ProducerConfig.RETRY_BACKOFF_MAX_MS_CONFIG, 5000);
props.put(ProducerConfig.MAX_BLOCK_MS_CONFIG, 10000);
props.put(ProducerConfig.BUFFER_MEMORY_CONFIG, 33554432L);
```

Các giá trị trên chỉ là ví dụ khởi đầu, không phải cấu hình tối ưu chung. Cần bảo đảm `delivery.timeout.ms >= request.timeout.ms + linger.ms`. Theo dõi tỷ lệ lỗi cuối cùng, record retry rate, request latency và producer buffer wait để biết retry có giúp phục hồi hay đang che giấu bottleneck.

### 5.2 Idempotence không phải idempotency nghiệp vụ

Idempotent producer ngăn duplicate do retry protocol trong phạm vi producer ID/sequence được Kafka hỗ trợ. Nó không tự ngăn ứng dụng gửi lại cùng một event như một lần gửi mới sau restart hoặc sau khi kết quả commit không rõ ràng.

Gắn event ID ổn định vào payload/header, lưu idempotency key ở consumer hoặc dùng upsert/deduplication tại hệ thống đích khi cần xử lý một event nhiều lần mà chỉ tạo một hiệu ứng nghiệp vụ.

### 5.3 Giới hạn buffer và thời gian block

Khi broker chậm, record có thể tích tụ trong producer buffer. Nếu buffer đầy, `send()` có thể block đến `max.block.ms` rồi ném lỗi. Tăng `buffer.memory` không giải quyết được tình trạng broker không theo kịp; nó chỉ trì hoãn thời điểm producer hết bộ nhớ và có thể làm tăng áp lực heap.

Giới hạn số producer instance, kích thước batch và tốc độ gửi theo năng lực cluster. Khi queue phía ứng dụng đầy, cần backpressure hoặc từ chối sớm thay vì giữ vô hạn record trong heap.

## 6. Kiểm soát retry ở Kafka consumer

### 6.1 Blocking retry trong listener

Blocking retry thử lại record trong luồng xử lý hiện tại. Cách này dễ hiểu và giữ thứ tự trong partition nếu xử lý tuần tự, nhưng thời gian chờ cộng dồn có thể làm listener không poll đủ thường xuyên.

Nếu thời gian xử lý và backoff vượt `max.poll.interval.ms`, consumer có thể bị loại khỏi group và gây rebalance. Cần cân đối:

- `max.poll.records`: số record tối đa trong một lần poll.
- `max.poll.interval.ms`: thời gian tối đa giữa các lần poll theo giao thức classic và client tương ứng.
- Thời gian xử lý mỗi record.
- Số lần retry và tổng backoff.

Không tăng `max.poll.interval.ms` vô hạn để che giấu listener bị kẹt. Trước tiên, giảm batch, giới hạn thời gian gọi downstream hoặc chuyển retry dài sang retry topic.

### 6.2 Spring Kafka `DefaultErrorHandler`

Spring Kafka hỗ trợ retry blocking qua `DefaultErrorHandler` và `BackOff`. Ví dụ:

```java
@Bean
DefaultErrorHandler kafkaErrorHandler(DeadLetterPublishingRecoverer recoverer) {
    ExponentialBackOffWithMaxRetries backOff =
            new ExponentialBackOffWithMaxRetries(4);
    backOff.setInitialInterval(500L);
    backOff.setMultiplier(2.0);
    backOff.setMaxInterval(5000L);

    DefaultErrorHandler handler =
            new DefaultErrorHandler(recoverer, backOff);

    handler.addNotRetryableExceptions(
            IllegalArgumentException.class,
            UnsupportedOperationException.class);
    return handler;
}
```

Ví dụ dùng exponential backoff không có jitter. Nếu nhiều consumer có thể thất bại cùng lúc, hãy cân nhắc custom `BackOff` có jitter hoặc chuyển sang retry topic để tránh đồng bộ. Phân loại exception theo nghiệp vụ; không đưa mọi lỗi vào danh sách retry mặc định.

Trong ví dụ này, `ExponentialBackOffWithMaxRetries(4)` giới hạn bốn lần retry sau lần xử lý ban đầu. Ở ví dụ `@RetryableTopic`, thuộc tính `attempts="4"` biểu thị tổng số lần thử, bao gồm lần đầu tiên. Hãy kiểm tra semantics của API đang dùng để tránh nhầm giữa retry count và total attempts.

`DeadLetterPublishingRecoverer` có thể publish record sau khi hết retry. Cần bảo đảm producer dùng để publish DLT hoạt động ổn định, topic DLT có đủ partition/replication, và lỗi publish DLT được xử lý rõ ràng. Nếu không thể ghi DLT, không được âm thầm đánh dấu record đã xử lý.

### 6.3 Non-blocking retry với retry topic

Spring Kafka hỗ trợ `@RetryableTopic` để đưa record thất bại sang các topic retry có thời gian chờ, sau đó chuyển về listener hoặc DLT theo cấu hình.

```java
@RetryableTopic(
    attempts = "4",
    backoff = @Backoff(delay = 1000, multiplier = 2.0, maxDelay = 10000),
    dltTopicSuffix = "-dlt"
)
@KafkaListener(topics = "orders", groupId = "order-workers")
public void listen(OrderEvent event) {
    orderService.process(event);
}
```

Tên annotation và khả năng cấu hình phụ thuộc phiên bản Spring Kafka. Ví dụ minh họa bốn lần thử tổng cộng và backoff; nếu cần jitter hoặc retry budget theo dependency, hãy bổ sung cơ chế riêng.

Retry topic giảm thời gian listener bị block, nhưng có đánh đổi:

- Record lỗi có thể được xử lý sau record mới hơn trong partition gốc.
- Thứ tự toàn cục hoặc thứ tự theo key có thể thay đổi khi record đi qua retry topic.
- Tạo thêm topic, consumer, storage và network traffic.
- Cần kiểm soát vòng lặp retry, thời gian lưu và chính sách DLT.

Nếu thứ tự theo aggregate/key là bắt buộc, hãy thiết kế luồng retry để không cho phép record sau vượt record đang chờ xử lý, hoặc dùng trạng thái/sequence kiểm soát ở tầng nghiệp vụ.

## 7. Backpressure và giới hạn tài nguyên

Retry storm không chỉ do số lần retry. Nó còn xảy ra khi hệ thống tiếp tục nhận việc nhanh hơn tốc độ xử lý và để queue tăng không giới hạn. Backpressure buộc upstream giảm tốc hoặc dừng nhận việc khi downstream không còn năng lực.

### 7.1 Bounded queue

Queue giữa Kafka listener và worker pool phải có dung lượng giới hạn. Nếu queue đầy:

- Tạm dừng partition bằng `consumer.pause()` nếu dùng KafkaConsumer trực tiếp.
- Tiếp tục gọi `poll()` định kỳ để duy trì consumer membership theo protocol/client.
- Chỉ `resume()` khi queue xuống dưới ngưỡng an toàn.
- Không nhận thêm record vào một queue không giới hạn.

Với Spring Kafka, dùng cơ chế pause/resume của listener container phù hợp phiên bản thay vì thao tác trực tiếp vào KafkaConsumer từ thread khác.

### 7.2 Giới hạn concurrency

Concurrency cao không phải lúc nào cũng tăng throughput. Nếu database chỉ chịu được 100 request đồng thời mà consumer tạo 500 worker, connection pool sẽ cạn và retry càng làm tải tăng.

Giới hạn đồng thời theo năng lực dependency:

| Tài nguyên | Giới hạn nên cân nhắc |
|---|---|
| Consumer worker | Số worker cố định, không tạo thread vô hạn |
| Database | Connection pool, query timeout, semaphore theo loại truy vấn |
| HTTP downstream | Max concurrent requests, connection pool và request deadline |
| Producer | Số producer instance, buffer memory và tốc độ gửi |
| Retry queue | Dung lượng tối đa và giới hạn tuổi record |
| DLT/replay worker | Số partition/worker và tốc độ tái xử lý |

Số consumer trong group không thể tăng mức song song xử lý của một topic vượt quá số partition được gán. Nếu mỗi partition cần ordering, xử lý tuần tự theo partition là ràng buộc quan trọng.

### 7.3 Circuit breaker

Circuit breaker ngăn gọi liên tục một dependency đang lỗi:

- **Closed:** request được phép đi qua; đo tỷ lệ lỗi và latency.
- **Open:** tạm chặn request khi lỗi vượt ngưỡng; trả lỗi nhanh hoặc chuyển record sang cơ chế chờ.
- **Half-open:** cho phép một số request thử nghiệm; nếu thành công thì đóng lại, nếu thất bại thì mở lại.

Circuit breaker nên được đặt theo dependency và có ngưỡng phù hợp. Không mở circuit vô thời hạn mà không có quan sát; cần metric trạng thái và cảnh báo. Khi circuit mở, consumer cần chính sách rõ ràng: pause, retry topic, DLT hoặc dừng listener để tránh commit nhầm offset.

### 7.4 Rate limiter và load shedding

Token bucket hoặc leaky bucket giới hạn tốc độ request theo giây. Khi downstream yêu cầu tối đa 500 request/s, consumer/replay worker phải tuân thủ giới hạn đó thay vì cố xử lý toàn bộ lag ngay lập tức.

Load shedding từ chối hoặc trì hoãn công việc có ưu tiên thấp khi hệ thống quá tải. Ví dụ, xử lý event cập nhật trạng thái thanh toán có thể ưu tiên hơn event tạo báo cáo. Quy tắc ưu tiên phải rõ ràng để không làm mất dữ liệu nghiệp vụ.

## 8. Giới hạn kích thước batch và bộ nhớ consumer

### 8.1 `max.poll.records`

`max.poll.records` giới hạn số record trả về trong một lần `poll()`. Giảm giá trị có thể giảm thời gian xử lý một batch và giảm lượng công việc đang giữ trong ứng dụng, đổi lại tăng số lần poll và overhead.

Chọn batch sao cho thời gian xử lý worst-case vẫn nằm trong ngân sách `max.poll.interval.ms`, có tính đến retry blocking nếu đang dùng. Không lấy thời gian trung bình làm căn cứ duy nhất; cần p95/p99.

### 8.2 Fetch limits

Các cấu hình như `fetch.max.bytes` và `max.partition.fetch.bytes` giới hạn dữ liệu fetch ở cấp request/partition. Đây không phải giới hạn cứng tuyệt đối trong mọi trường hợp vì Kafka có thể trả batch đầu tiên để consumer tiến triển dù batch vượt giới hạn cấu hình.

Đặt fetch limit phù hợp với kích thước record batch lớn nhất dự kiến. Nếu đặt quá thấp so với batch hợp lệ, có thể tạo hành vi khó hiểu hoặc không giảm bộ nhớ như kỳ vọng.

### 8.3 Ước lượng bộ nhớ

Một ước lượng thô cho dữ liệu đang giữ trong ứng dụng:

\[
Memory \approx ConcurrentRecords \times AverageRecordSize \times ExpansionFactor
\]

`ExpansionFactor` bao gồm object overhead, deserialization, queue và bản sao dữ liệu. Ví dụ 20.000 record, trung bình 4 KB, expansion factor 3 cần khoảng 240 MB cho phần payload/object liên quan, chưa tính heap nền, producer buffer, batch, cache và các request khác.

Đo heap thực tế bằng metrics/profiling. Giảm batch hoặc queue nếu heap tăng nhanh khi downstream chậm; tăng heap mà không giới hạn queue chỉ kéo dài thời gian trước khi hết bộ nhớ.

## 9. Giới hạn tài nguyên cho replay và phục hồi

Khi broker hoặc downstream phục hồi, consumer lag có thể rất lớn. Nếu tất cả consumer cùng tăng tốc tối đa để bắt kịp, chúng có thể làm database hoặc API vừa phục hồi lại quá tải.

### 9.1 Phân biệt live traffic và replay traffic

Nếu có thể, dành worker pool hoặc quota riêng cho replay. Live traffic cần latency thấp; replay có thể chạy chậm hơn nhưng phải có throughput ổn định. Không để replay chiếm toàn bộ connection pool và CPU của luồng trực tiếp.

### 9.2 Giới hạn tốc độ catch-up

Đặt mục tiêu tốc độ replay theo năng lực downstream, ví dụ tối đa 300 record/s cho một partition hoặc tối đa 1.000 request/s cho toàn service. Đây là ví dụ minh họa; cần benchmark và quan sát database/HTTP latency.

Theo dõi:

- Consumer lag theo partition và tuổi của record cũ nhất.
- Tốc độ đọc, tốc độ xử lý và tốc độ commit.
- Retry rate, DLT rate và tuổi record trong retry topic.
- CPU, heap, GC, queue depth và thread utilization.
- Database connection pool, lock wait, query latency.
- HTTP 429/5xx, timeout, connection pool và circuit breaker state.

### 9.3 Tăng tốc từng bước

Khi downstream vừa phục hồi, bắt đầu với concurrency và rate limit thấp. Tăng dần theo từng khoảng, chỉ khi p95/p99 latency, error rate và resource utilization ổn định. Nếu lỗi tăng hoặc queue phình ra, giảm tốc ngay.

Không dùng một lần scale up lớn để giải quyết lag mà chưa xác nhận bottleneck. Thêm consumer không giúp nếu partition count đã giới hạn hoặc database là bottleneck.

## 10. Retry topic, DLT và chính sách lưu giữ

### 10.1 Retry topic phải có giới hạn

Retry topic cần quy định số tầng retry, thời gian chờ, retention và số lần chuyển tiếp. Tránh cấu hình một topic retry quay lại topic gốc mà không có attempt header hoặc giới hạn vòng lặp; lỗi vĩnh viễn có thể luân chuyển vô hạn.

Mỗi lần chuyển retry nên mang metadata như:

- Số lần thử hoặc retry stage.
- Thời điểm lỗi đầu tiên và lần thử gần nhất.
- Exception class và mã lỗi đã chuẩn hóa.
- Topic, partition, offset nguồn và event ID.
- Trace/correlation ID để liên kết log.

Không đưa secret, credential hoặc dữ liệu nhạy cảm không cần thiết vào header/log.

### 10.2 Dead-letter topic không phải thùng rác vô hạn

DLT lưu record không thể xử lý tự động sau chính sách retry. Cần có owner, cảnh báo, retention, quy trình sửa dữ liệu và replay. Nếu DLT tăng liên tục mà không có người xử lý, nó chỉ chuyển backlog từ topic chính sang một nơi khác.

Đặt retention theo thời gian điều tra và yêu cầu audit. Bảo đảm dung lượng đủ và kiểm tra quyền truy cập, vì DLT có thể chứa payload lỗi hoặc thông tin nghiệp vụ.

### 10.3 Replay DLT an toàn

Trước khi replay:

1. Xác định và sửa nguyên nhân khiến record thất bại.
2. Chọn một tập record rõ ràng theo thời gian, partition, offset hoặc event ID.
3. Kiểm tra idempotency ở consumer và downstream.
4. Giới hạn tốc độ replay và concurrency.
5. Theo dõi kết quả thành công/thất bại và tránh tạo vòng lặp DLT.

Replay record cũ có thể tạo duplicate hoặc vi phạm thứ tự. Nếu nghiệp vụ cần thứ tự theo key, hãy xác định cách xử lý record mới hơn đã được áp dụng trước đó.

## 11. Ví dụ cấu hình Spring Boot tổng hợp

Ví dụ dưới đây minh họa một số giới hạn phía consumer:

```yaml
spring:
  kafka:
    consumer:
      group-id: order-workers
      enable-auto-commit: false
      max-poll-records: 100
      properties:
        max.poll.interval.ms: 300000
        fetch.max.bytes: 52428800
        max.partition.fetch.bytes: 1048576
```

Các con số chỉ là ví dụ. Đo thời gian xử lý một batch với p99 và đặt `max.poll.interval.ms` đủ lớn cho trường hợp xấu có kiểm soát. Không tăng fetch/batch chỉ để giảm số request nếu heap hoặc downstream không đủ sức.

Đối với listener, cấu hình error handler với số retry hữu hạn và DLT; đối với downstream, cấu hình timeout, connection pool, concurrency limit và circuit breaker. Những giới hạn này cần được phối hợp để một record không được retry đồng thời ở nhiều tầng với tổng attempt vượt ngân sách.

## 12. Dashboard và cảnh báo retry storm

### 12.1 Metric cần theo dõi

| Nhóm | Metric gợi ý | Dấu hiệu bất thường |
|---|---|---|
| Producer | Retry rate, record error rate, request latency, buffer wait | Retry tăng cùng buffer đầy hoặc delivery timeout |
| Consumer | Lag, records consumed, poll interval, processing latency | Lag tăng và poll bị gián đoạn |
| Retry | Attempts/record, retry topic rate, retry age | Retry rate tăng nhanh hơn traffic gốc |
| DLT | DLT publish rate, DLT backlog/age | DLT tăng liên tục hoặc publish DLT lỗi |
| Runtime | CPU, heap, GC pause, thread count, queue depth | CPU/heap/queue tăng đồng thời throughput giảm |
| Dependency | HTTP 429/5xx, DB latency, pool utilization | Downstream quá tải hoặc connection pool cạn |
| Broker | Request handler idle, network, disk, ISR | Broker thiếu tài nguyên hoặc replication chậm |

### 12.2 Alert theo tỷ lệ và xu hướng

Không chỉ cảnh báo theo số retry tuyệt đối. Khi traffic tăng gấp đôi, retry count tăng có thể bình thường. Theo dõi tỷ lệ retry trên request gốc, tỷ lệ lỗi cuối cùng, độ tuổi backlog và thời gian phục hồi.

Ví dụ cảnh báo: retry rate vượt 15% trong 5 phút, consumer lag tăng liên tục 10 phút, DLT age vượt 30 phút hoặc connection pool sử dụng trên 90%. Các ngưỡng này chỉ minh họa; hãy hiệu chỉnh theo baseline và SLA.

## 13. Quy trình xử lý khi retry storm xảy ra

1. **Xác định nguồn lỗi:** broker, network, database, API hay logic record.
2. **Ngăn khuếch đại:** giảm concurrency, hạ rate limit, mở circuit breaker hoặc tạm pause partition có vấn đề.
3. **Giữ dữ liệu:** không commit offset nếu record chưa xử lý thành công; đảm bảo retry/DLT publish không làm mất record.
4. **Giới hạn retry:** tạm dừng retry không cần thiết, giảm attempt hoặc tăng backoff có jitter.
5. **Bảo vệ dependency:** giới hạn connection pool, worker, producer buffer và tốc độ replay.
6. **Phục hồi theo giai đoạn:** khôi phục dependency, kiểm tra health rồi tăng throughput dần.
7. **Xử lý backlog:** ưu tiên live traffic, chạy replay theo quota và theo dõi lag/age.
8. **Đối soát:** kiểm tra duplicate, record ở retry/DLT, offset commit và side effect nghiệp vụ.
9. **Rút kinh nghiệm:** xác định tầng retry gây amplification và cập nhật budget, timeout, alert.

Không xóa retry topic hoặc DLT để làm dashboard sạch hơn. Không reset consumer offset về latest chỉ để giảm lag nếu chưa có quyết định nghiệp vụ về việc bỏ qua backlog.

## 14. Những lỗi thiết kế thường gặp

| Lỗi | Tác động | Cách khắc phục |
|---|---|---|
| Retry ngay lập tức | Tạo request burst khi dependency đang lỗi | Exponential backoff và jitter |
| Retry vô hạn | Giữ thread, queue và connection không giới hạn | Max attempts, deadline và retry budget |
| Mỗi tầng retry độc lập | Khuếch đại số request downstream | Một ngân sách retry chung cho call chain |
| Retry lỗi dữ liệu vĩnh viễn | Tốn tài nguyên và làm lag tăng | Phân loại non-retryable, DLT/quarantine |
| Blocking retry quá lâu | Consumer vượt poll interval và rebalance | Retry topic hoặc giảm batch/thời gian xử lý |
| Queue không giới hạn | Heap tăng đến OOM khi downstream chậm | Bounded queue và backpressure |
| Scale consumer vượt partition count | Tăng instance nhưng không tăng song song hữu ích | Điều chỉnh partition hoặc tối ưu consumer hiện có |
| Replay không rate limit | Downstream vừa phục hồi lại bị quá tải | Quota riêng và tăng tốc từng bước |
| DLT không có owner | Record lỗi tích tụ vô hạn | Alert, retention và quy trình replay |
| Nghĩ idempotent producer chống mọi duplicate | Duplicate do application resend vẫn xảy ra | Event ID và idempotency nghiệp vụ |

## 15. Checklist production

- Mỗi loại lỗi được phân loại retryable hoặc non-retryable.
- Producer retry bị giới hạn bởi delivery deadline và backoff phù hợp.
- Idempotence được bật khi phù hợp; event có ID ổn định cho deduplication nghiệp vụ.
- Tổng retry attempts của mọi tầng không vượt retry budget.
- Exponential backoff có jitter cho các client có thể đồng bộ retry.
- Retry có deadline tổng, max attempts và hành vi khi budget cạn.
- Consumer batch và thời gian xử lý phù hợp `max.poll.interval.ms`.
- Retry dài dùng retry topic hoặc cơ chế bất đồng bộ phù hợp.
- Retry topic có attempt metadata, retention và giới hạn vòng lặp.
- DLT có owner, alert, retention và quy trình replay.
- Worker pool, queue, connection pool, producer buffer và replay rate đều có giới hạn.
- Có circuit breaker, rate limiter hoặc load shedding cho dependency quan trọng.
- Dashboard theo dõi retry ratio, lag, queue depth, DLT age và downstream saturation.
- Đã diễn tập broker failover, downstream outage, retry storm và replay backlog trong staging.

## Kết luận

Kiểm soát retry storm cần phối hợp phân loại lỗi, exponential backoff có jitter, retry budget, deadline và giới hạn attempt. Kafka producer có retry nội bộ được ràng buộc bởi delivery timeout; consumer/listener cần tránh blocking retry quá lâu làm vượt poll interval. Với lỗi downstream kéo dài, retry topic và DLT giúp tách thời gian chờ khỏi luồng xử lý chính, nhưng phải quản lý thứ tự, retention và vòng lặp retry.

Phục hồi an toàn còn cần bounded queue, giới hạn concurrency, backpressure, circuit breaker, rate limiter và quota riêng cho replay. Theo dõi retry ratio, consumer lag, DLT age, queue depth và sức khỏe dependency để phát hiện khuếch đại tải sớm. Khi hệ thống phục hồi, tăng tốc từng bước theo năng lực downstream và đối soát offset/side effect. Những giới hạn này giúp KAFKA phục hồi ổn định mà không biến lỗi tạm thời thành sự cố diện rộng.
