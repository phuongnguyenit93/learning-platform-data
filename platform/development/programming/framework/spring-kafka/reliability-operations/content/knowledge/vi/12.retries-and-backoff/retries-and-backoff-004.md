# Jitter chống retry đồng loạt

Trong Spring Kafka, retry giúp consumer phục hồi sau lỗi tạm thời như database timeout, dịch vụ HTTP không sẵn sàng hoặc lỗi mạng. Tuy nhiên, khi nhiều consumer gặp cùng một sự cố và cùng chờ một khoảng thời gian cố định, chúng có thể gửi lại request gần như đồng thời. Lượng request dồn vào cùng một thời điểm tạo ra **retry storm** hoặc **thundering herd**: dịch vụ phụ thuộc vừa hồi phục lại lập tức bị quá tải, khiến lỗi tiếp tục lặp lại.

**Jitter** là phần ngẫu nhiên được thêm vào thời gian chờ retry. Thay vì tất cả consumer cùng thử lại sau đúng một giây, mỗi consumer nhận một thời điểm thử lại khác nhau trong một khoảng được kiểm soát. Jitter phân tán tải theo thời gian, giảm đỉnh request và tăng cơ hội để dependency phục hồi.

Jitter không thay thế exponential backoff, giới hạn số lần thử, timeout, rate limit hay idempotency. Nó bổ sung độ lệch thời gian cho chính sách retry để nhiều tiến trình không đồng bộ với nhau.

## 1. Vì sao retry đồng loạt gây quá tải?

Giả sử một dịch vụ thanh toán tạm ngừng trong 5 giây. Có 200 consumer đang xử lý các partition khác nhau. Tất cả gọi dịch vụ và nhận timeout gần như cùng lúc. Nếu mỗi consumer dùng FixedBackOff một giây, chúng có thể cùng thử lại ở giây tiếp theo.

    Thời gian:       0s       1s       2s       3s
    Consumer A:      FAIL     RETRY    RETRY    RETRY
    Consumer B:      FAIL     RETRY    RETRY    RETRY
    Consumer C:      FAIL     RETRY    RETRY    RETRY
    ...
    Consumer 200:    FAIL     RETRY    RETRY    RETRY

    Kết quả: nhiều request dồn vào cùng một thời điểm

Nếu dependency chỉ có thể xử lý 50 request đồng thời, đợt retry có thể làm hàng đợi đầy, connection pool cạn hoặc rate limit bị kích hoạt. Các request lại thất bại, rồi tiếp tục tạo một đợt retry đồng loạt tiếp theo.

Hiện tượng này có thể xuất hiện dù mỗi consumer chỉ retry một số lần hữu hạn. Số lần thử hữu hạn ngăn vòng lặp vô tận, nhưng không tự phân tán thời điểm thử lại.

### 1.1. Exponential backoff vẫn có thể đồng bộ

Exponential backoff tăng khoảng chờ sau mỗi lần thất bại, ví dụ 1, 2, 4, 8 giây. Cách này giảm tần suất retry theo thời gian, nhưng nếu nhiều consumer bắt đầu cùng lúc và dùng cùng tham số, lịch retry của chúng vẫn giống nhau.

    Consumer A: 1s -> 2s -> 4s -> 8s
    Consumer B: 1s -> 2s -> 4s -> 8s
    Consumer C: 1s -> 2s -> 4s -> 8s

Jitter làm lệch các mốc đó:

    Consumer A: 0.3s -> 1.4s -> 2.2s -> 6.1s
    Consumer B: 0.8s -> 0.5s -> 3.7s -> 4.9s
    Consumer C: 0.1s -> 1.8s -> 1.1s -> 7.2s

Các con số trên chỉ minh họa. Mục tiêu là phân tán request trong một cửa sổ thời gian, không phải tạo ra thời gian chờ tùy tiện hoặc không có giới hạn.

## 2. Jitter hoạt động như thế nào?

Một retry policy thường có hai thành phần:

- **Backoff ceiling:** khoảng chờ tối đa dự kiến ở lần retry hiện tại, thường tăng theo exponential backoff và bị giới hạn bởi max interval.
- **Jitter:** cách chọn thời gian chờ thực tế trong hoặc quanh khoảng ceiling đó.

Với exponential backoff:

`ceiling_n = min(maxDelay, initialDelay * multiplier^(n-1))`

Jitter chọn một delay thực tế từ ceiling. Ví dụ với full jitter:

`delay_n ~ Uniform(0, ceiling_n)`

Trong đó Uniform(a, b) nghĩa là mỗi giá trị trong khoảng được chọn với xác suất phân bố đều. Nếu ceiling là 8 giây, các consumer có thể chờ từ 0 tới 8 giây thay vì tất cả chờ đúng 8 giây.

Jitter cần có giới hạn rõ ràng. Một retry không nên chờ vô hạn, vượt SLA hoặc tạo ra một lượng request lớn hơn năng lực của dependency.

## 3. Các chiến lược jitter phổ biến

### 3.1. Full jitter

Full jitter chọn thời gian chờ ngẫu nhiên từ 0 tới exponential ceiling:

`delay = random(0, ceiling)`

Ví dụ ceiling lần lượt là 1, 2, 4, 8 giây:

| Lần retry | Ceiling | Khoảng delay full jitter |
|---:|---:|---:|
| 1 | 1 giây | 0–1 giây |
| 2 | 2 giây | 0–2 giây |
| 3 | 4 giây | 0–4 giây |
| 4 | 8 giây | 0–8 giây |

Ưu điểm là phân tán mạnh và giảm đỉnh request. Nhược điểm là có thể chọn delay rất ngắn, kể cả gần 0. Nếu dependency cần một khoảng nghỉ tối thiểu để phục hồi, full jitter có thể cần floor delay hoặc một chiến lược khác.

Full jitter thường phù hợp khi mục tiêu chính là giảm đồng bộ giữa số lượng lớn client/consumer và dependency có thể nhận các lần thử lại rải đều trong cửa sổ.

### 3.2. Equal jitter

Equal jitter giữ một nửa ceiling làm khoảng chờ tối thiểu, sau đó random trong nửa còn lại:

`delay = ceiling/2 + random(0, ceiling/2)`

Ví dụ ceiling là 8 giây thì delay thực tế nằm trong khoảng 4–8 giây.

| Lần retry | Ceiling | Khoảng delay equal jitter |
|---:|---:|---:|
| 1 | 1 giây | 0.5–1 giây |
| 2 | 2 giây | 1–2 giây |
| 3 | 4 giây | 2–4 giây |
| 4 | 8 giây | 4–8 giây |

Equal jitter tránh các lần retry quá sớm, nhưng phân tán hẹp hơn full jitter. Chọn cách này khi dependency cần một khoảng nghỉ tối thiểu mà vẫn cần phân tán thời điểm gọi lại.

### 3.3. Decorrelated jitter

Decorrelated jitter sử dụng delay trước đó để tạo khoảng tiếp theo:

`delay_n = random(baseDelay, min(maxDelay, previousDelay * 3))`

Cách này tạo lịch retry ít đồng bộ hơn vì mỗi consumer có chuỗi delay riêng. Nó cũng tránh việc mọi consumer tăng delay theo cùng một chuỗi cố định.

Decorrelated jitter hữu ích khi cần giảm tương quan giữa các lần retry qua nhiều vòng. Tuy nhiên, cần kiểm tra giới hạn dưới, giới hạn trên và cách khởi tạo previousDelay để không tạo delay bất hợp lý.

### 3.4. So sánh chiến lược

| Chiến lược | Khoảng chọn | Đặc điểm | Khi cân nhắc |
|---|---|---|---|
| Fixed delay | Một giá trị cố định | Đơn giản nhưng dễ đồng bộ | Tải nhỏ, lỗi ít và độc lập |
| Exponential, không jitter | Ceiling tăng dần | Giảm tần suất nhưng vẫn đồng bộ | Ít consumer hoặc không có burst đồng thời |
| Full jitter | 0 đến ceiling | Phân tán rộng, có thể retry sớm | Nhiều consumer cùng phục hồi |
| Equal jitter | Một nửa ceiling đến ceiling | Có thời gian nghỉ tối thiểu | Dependency cần thời gian phục hồi |
| Decorrelated jitter | Base đến min(max, previous × 3) | Chuỗi delay ít tương quan | Nhiều lần retry và nhiều client |

Không có một chiến lược tốt nhất cho mọi workload. Chọn theo thời gian phục hồi của dependency, SLA, số consumer, retry budget và giới hạn request đồng thời.

## 4. Jitter không thay thế exponential backoff

Nếu chỉ thêm jitter vào một khoảng cố định, các lần retry có thể được phân tán nhưng tần suất vẫn cao khi lỗi kéo dài. Exponential backoff tăng dần khoảng chờ để giảm áp lực theo thời gian. Kết hợp hai cơ chế thường hiệu quả hơn:

1. Tính ceiling theo exponential backoff.
2. Chọn delay thực tế bằng một chiến lược jitter.
3. Giới hạn delay tối đa.
4. Giới hạn tổng số lần thử.
5. Chuyển record sang recovery/DLT khi hết retry.

Ví dụ:

    initialDelay = 500 ms
    multiplier = 2
    maxDelay = 8 s

    Ceiling: 0.5s, 1s, 2s, 4s, 8s, 8s, ...
    Full jitter: random(0, ceiling) cho mỗi lần retry

Giới hạn maxDelay ngăn khoảng chờ tăng mãi. Giới hạn maxRetries ngăn record bị retry vô hạn. Jitter phân tán các lần retry nằm trong cùng một ceiling.

## 5. Áp dụng jitter cho blocking retry với DefaultErrorHandler

Trong Spring Kafka, DefaultErrorHandler nhận một đối tượng BackOff. Các implementation có sẵn như FixedBackOff và ExponentialBackOff cung cấp lịch chờ xác định. Khi nhiều consumer dùng cùng một lịch, có thể tạo các đợt retry đồng bộ.

Để thêm jitter cho blocking retry, có thể triển khai interface `org.springframework.util.backoff.BackOff`. Mỗi lần `start()` tạo một BackOffExecution riêng cho chuỗi retry của record. Trạng thái đếm lần retry và ceiling phải nằm trong execution đó, không dùng chung giữa các record.

Ví dụ dưới đây triển khai full jitter với exponential ceiling và số lần retry hữu hạn:

~~~java
import java.util.concurrent.ThreadLocalRandom;
import java.util.function.LongUnaryOperator;

import org.springframework.util.backoff.BackOff;
import org.springframework.util.backoff.BackOffExecution;

public final class FullJitterExponentialBackOff implements BackOff {

    private final long initialInterval;
    private final double multiplier;
    private final long maxInterval;
    private final int maxRetries;
    private final LongUnaryOperator randomBelow;

    public FullJitterExponentialBackOff(
            long initialInterval,
            double multiplier,
            long maxInterval,
            int maxRetries) {

        this(
            initialInterval,
            multiplier,
            maxInterval,
            maxRetries,
            bound -> ThreadLocalRandom.current().nextLong(bound)
        );
    }

    // Constructor có thể dùng trong test để kiểm soát giá trị random.
    FullJitterExponentialBackOff(
            long initialInterval,
            double multiplier,
            long maxInterval,
            int maxRetries,
            LongUnaryOperator randomBelow) {

        if (initialInterval <= 0
                || maxInterval < initialInterval
                || maxInterval == Long.MAX_VALUE
                || multiplier < 1.0
                || !Double.isFinite(multiplier)
                || maxRetries < 0) {
            throw new IllegalArgumentException("Invalid backoff settings");
        }

        this.initialInterval = initialInterval;
        this.multiplier = multiplier;
        this.maxInterval = maxInterval;
        this.maxRetries = maxRetries;
        this.randomBelow = randomBelow;
    }

    @Override
    public BackOffExecution start() {
        return new BackOffExecution() {

            private int retryCount;
            private long ceiling = initialInterval;

            @Override
            public long nextBackOff() {
                if (retryCount >= maxRetries) {
                    return STOP;
                }

                // Full jitter: chọn số millisecond từ 0 tới ceiling.
                long delay = randomBelow.applyAsLong(ceiling + 1);

                if (delay < 0 || delay > ceiling) {
                    throw new IllegalStateException(
                        "Random source returned an invalid delay"
                    );
                }

                retryCount++;

                if (ceiling < maxInterval) {
                    double next = Math.ceil(ceiling * multiplier);
                    ceiling = next >= maxInterval
                            ? maxInterval
                            : Math.max(ceiling, (long) next);
                }

                return delay;
            }
        };
    }
}
~~~

Implementation này có các đặc điểm:

- Mỗi record có một BackOffExecution riêng khi Spring Kafka bắt đầu chuỗi retry.
- Exponential ceiling bắt đầu từ initialInterval và không vượt maxInterval.
- Full jitter chọn delay trong khoảng từ 0 tới ceiling, tính bằng milliseconds.
- maxRetries là số lần retry sau lần xử lý ban đầu; khi hết số lần này, execution trả về BackOffExecution.STOP.
- ThreadLocalRandom tránh dùng một Random instance mutable chung giữa các thread.
- Constructor nhận random source cho phép kiểm thử lịch delay một cách xác định.

Ví dụ dùng constructor với sáu lần retry, bắt đầu 500 ms, tăng gấp đôi và giới hạn 30 giây:

~~~java
@Bean
CommonErrorHandler commonErrorHandler(
        KafkaTemplate<Object, Object> kafkaTemplate) {

    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(kafkaTemplate);

    BackOff jitterBackOff =
            new FullJitterExponentialBackOff(
                500L,
                2.0,
                30_000L,
                6
            );

    DefaultErrorHandler handler =
            new DefaultErrorHandler(recoverer, jitterBackOff);

    handler.addNotRetryableExceptions(
        IllegalArgumentException.class
    );

    return handler;
}
~~~

Factory phải gắn handler này vào container:

~~~java
factory.setCommonErrorHandler(commonErrorHandler);
~~~

Đảm bảo các import và generic của KafkaTemplate, ConsumerFactory, recoverer khớp với serializer/deserializer trong ứng dụng. Code minh họa dùng API BackOff của Spring Framework; kiểm tra dependency Spring Kafka/Spring Framework của dự án trước khi tích hợp.

### 5.1. Điều chỉnh full jitter để có thời gian nghỉ tối thiểu

Full jitter có thể trả về 0 hoặc một giá trị rất nhỏ. Nếu dependency cần tối thiểu 200 ms để phục hồi, có thể dùng equal jitter hoặc giới hạn dưới.

Với equal jitter:

`delay = floor(ceiling/2) + random(0, ceiling - floor(ceiling/2))`

Trong code, chỉ thay cách tính delay:

~~~java
long lowerBound = ceiling / 2;
long range = ceiling - lowerBound + 1;
long delay = lowerBound + randomBelow.applyAsLong(range);
~~~

Cách này giữ delay trong khoảng xấp xỉ một nửa ceiling tới ceiling. Nếu cần một floor độc lập, hãy xác định rõ cách xử lý khi ceiling nhỏ hơn floor và bảo đảm delay cuối không vượt maxDelay.

## 6. Dùng jitter với retry topic

Blocking retry giữ record trong luồng consumer hiện tại trong khi chờ backoff. Điều này phù hợp khi muốn giữ thứ tự trong partition và khoảng retry tương đối ngắn. Với khoảng chờ dài, retry topic có thể tách record lỗi khỏi topic chính để consumer tiếp tục xử lý các record khác.

Spring Kafka hỗ trợ retry topic qua `@RetryableTopic`. Annotation backoff có thể hỗ trợ randomization tùy phiên bản thư viện; hãy kiểm tra thuộc tính của `org.springframework.kafka.annotation.BackOff` trong đúng version trước khi dùng. Đừng nhầm annotation này với `org.springframework.retry.annotation.Backoff`, vì chúng thuộc hai cơ chế khác nhau.

Ví dụ cấu hình retry topic với backoff tăng dần:

~~~java
@RetryableTopic(
    attempts = "5",
    backoff = @BackOff(
        delay = 1_000,
        multiplier = 2.0,
        maxDelay = 30_000
    ),
    dltTopicSuffix = ".DLT"
)
@KafkaListener(
    topics = "orders",
    groupId = "order-service"
)
public void consume(OrderCreated event) {
    orderService.process(event);
}
~~~

Nếu version hỗ trợ thuộc tính random trên annotation backoff, có thể bật nó để random hóa khoảng chờ theo semantics mà version đó định nghĩa. Cần xác nhận cách tính delay và số retry thực tế trong integration test. Nếu version không có randomization, có thể dùng custom retry-topic routing hoặc một cơ chế delay riêng; không nên giả định thêm một giá trị annotation không tồn tại.

Retry topic có thể thay đổi thứ tự xử lý. Record A bị lỗi và được chuyển sang retry topic, trong khi record B phía sau tiếp tục xử lý ở topic chính. Khi A quay lại, B có thể đã hoàn tất trước A. Nếu nghiệp vụ yêu cầu thứ tự theo key, hãy đánh giá blocking retry, version của aggregate hoặc một cơ chế điều phối theo key.

## 7. Chọn blocking retry hay retry topic khi có jitter

| Tiêu chí | Blocking retry với DefaultErrorHandler | Retry topic |
|---|---|---|
| Nơi chờ | Trong luồng xử lý consumer | Broker giữ record ở topic retry |
| Ảnh hưởng partition chính | Có thể giữ các record sau chờ | Topic chính có thể tiếp tục |
| Thứ tự | Dễ giữ thứ tự partition hơn | Có thể thay đổi thứ tự |
| Jitter | Dùng custom BackOff | Dùng random backoff nếu version hỗ trợ hoặc delay strategy riêng |
| Phù hợp | Retry ngắn, cần giữ thứ tự | Retry dài, muốn cô lập record lỗi |
| Vận hành | Theo dõi backoff và consumer poll | Theo dõi retry topics, lag và DLT |

Jitter chỉ phân tán thời gian thử lại. Nó không giải quyết việc partition chính bị block, cũng không tự bảo đảm thứ tự khi chuyển qua retry topic.

## 8. Jitter ở nhiều tầng retry

Một request có thể được retry ở nhiều nơi:

- HTTP client bên trong listener.
- Spring Retry hoặc resilience library.
- DefaultErrorHandler của Spring Kafka.
- Retry topic.
- Một service downstream khác.

Nếu mỗi tầng có ba lần thử, tổng số request thực tế có thể lớn hơn nhiều so với con số mà một cấu hình riêng lẻ thể hiện. Jitter ở từng tầng cũng không giúp nếu tổng retry budget không được quản lý.

Ví dụ, listener gọi một HTTP client có ba lần thử; sau đó listener vẫn ném exception và DefaultErrorHandler retry thêm bốn lần. Một record có thể tạo ra tới mười hai lần gọi HTTP nếu mỗi lần listener invocation đều sử dụng đủ ba lần thử bên trong.

Hãy xác định một retry budget tổng thể:

1. Tầng nào sở hữu retry chính?
2. Tổng số lần gọi dependency tối đa là bao nhiêu?
3. Tổng thời gian xử lý tối đa là bao lâu?
4. Tầng nào quyết định chuyển sang DLT?
5. Tầng nào chịu trách nhiệm phát cảnh báo?

Nếu dependency đã có retry riêng, có thể giảm retry ở listener hoặc đặt số lần thử nhỏ hơn. Tránh để nhiều tầng cùng retry không giới hạn.

## 9. Jitter và giới hạn tải dependency

Jitter làm lệch thời điểm request nhưng không đặt giới hạn tổng request đồng thời. Khi số consumer rất lớn, ngay cả request được phân tán trong một cửa sổ cũng có thể vượt năng lực dependency.

Kết hợp jitter với các cơ chế bảo vệ:

- **Timeout:** giới hạn thời gian một lần gọi dependency.
- **Concurrency limit:** giới hạn số request đồng thời.
- **Rate limit:** giới hạn số request trong một đơn vị thời gian.
- **Circuit breaker:** ngừng gọi dependency khi lỗi vượt ngưỡng, sau đó thử phục hồi có kiểm soát.
- **Bulkhead:** cô lập pool/thread/connection để một dependency không chiếm toàn bộ tài nguyên.
- **Retry budget:** giới hạn tổng số lần thử hoặc tỷ lệ retry so với request gốc.

Ví dụ, nếu API chỉ cho phép 100 request/giây, jitter không thể bảo đảm mọi consumer nằm dưới giới hạn đó. Cần rate limiter hoặc quota phù hợp. Khi API trả 429 hoặc 503, tôn trọng Retry-After nếu ứng dụng và retry mechanism có thể sử dụng giá trị đó.

Không scale consumer để bù cho dependency đã quá tải. Scale out có thể tăng concurrency và làm số request lỗi tăng nhanh hơn. Hãy giảm tải, áp dụng backpressure hoặc tạm dừng consumer theo chính sách vận hành.

## 10. Jitter và idempotency

Retry có thể xảy ra sau khi dependency đã thực hiện side effect nhưng phản hồi bị mất. Ví dụ API thanh toán đã ghi nhận giao dịch nhưng client timeout. Consumer retry request có thể tạo một khoản thanh toán thứ hai nếu API không hỗ trợ idempotency.

Jitter chỉ thay đổi thời điểm retry; nó không ngăn duplicate. Đối với mỗi sự kiện nghiệp vụ:

- Giữ eventId ổn định qua tất cả lần retry.
- Truyền eventId làm idempotency key tới API nếu API hỗ trợ.
- Lưu dấu mốc xử lý trong cùng database transaction với thay đổi nghiệp vụ.
- Dùng unique constraint hoặc upsert có điều kiện.
- Giữ nguyên eventId khi chuyển record qua retry topic hoặc DLT re-drive.

Nếu listener đã commit database nhưng offset Kafka chưa commit, record có thể được giao lại. Consumer cần idempotent ngay cả khi jitter được cấu hình chính xác.

## 11. Chọn tham số jitter theo SLA

Các tham số cần xác định:

| Tham số | Ý nghĩa | Cách chọn |
|---|---|---|
| initialDelay | Ceiling của lần retry đầu | Đủ để lỗi ngắn hạn có thời gian tự phục hồi |
| multiplier | Hệ số tăng ceiling | Thường lớn hơn hoặc bằng 1 |
| maxDelay | Ceiling tối đa | Không vượt thời gian chờ được SLA cho phép |
| maxRetries | Số lần thử lại sau lần đầu | Dựa trên retry budget |
| jitter strategy | Full, equal hoặc decorrelated | Dựa trên mức độ cần phân tán và delay tối thiểu |
| request timeout | Giới hạn một lần gọi dependency | Nhỏ hơn ngân sách thời gian xử lý tổng thể |
| total deadline | Tổng thời gian cho toàn bộ lần thử | Phải phù hợp với SLA nghiệp vụ |

Không chỉ cộng các delay để tính tổng thời gian. Mỗi lần gọi dependency còn có request timeout, thời gian xử lý listener, thời gian commit và có thể có rebalance. Tổng thời gian dự kiến phải tính cả các thành phần đó.

Ví dụ minh họa:

- initial ceiling: 500 ms.
- multiplier: 2.
- max ceiling: 8 giây.
- max retries: 5.
- full jitter: mỗi delay ngẫu nhiên từ 0 tới ceiling hiện tại.

Ceiling lần lượt là 0.5, 1, 2, 4 và 8 giây. Tổng delay tối đa là 15.5 giây, còn tổng delay trung bình lý thuyết của full jitter xấp xỉ một nửa tổng ceiling, tức 7.75 giây. Thời gian thực tế còn cộng thời gian xử lý từng request.

Nếu SLA chỉ cho phép xử lý trong 10 giây, cấu hình này có thể vượt deadline khi cộng request timeout. Hãy giảm số lần thử, giới hạn maxDelay hoặc chọn retry topic nếu nghiệp vụ cho phép trì hoãn lâu hơn.

## 12. Theo dõi hiệu quả của jitter

Để biết jitter có thực sự giảm retry storm, hãy quan sát phân bố thời gian retry chứ không chỉ tổng số lần retry.

Các metric hữu ích:

**Retry behavior**

- Số lần retry theo topic, partition và exception class.
- Delay thực tế được chọn cho mỗi lần retry.
- Histogram khoảng thời gian giữa các lần thử.
- Tỷ lệ retry thành công.
- Số record hết retry và chuyển DLT.

**Dependency**

- Request rate và concurrent request.
- Tỷ lệ 429, 5xx, timeout và connection error.
- Latency p50, p95, p99.
- Queue depth, connection pool usage và saturation.

**Kafka consumer**

- Consumer lag và oldest record age.
- Thời gian listener xử lý record.
- Rebalance count và duration.
- Số consumer đang hoạt động.
- Tỷ lệ record được giao lại.

Có thể so sánh histogram request rate trước và sau khi bật jitter. Nếu các đỉnh request đồng thời giảm và dependency phục hồi nhanh hơn, jitter đang giúp phân tán tải. Nếu tổng request vẫn vượt capacity, cần thêm rate limit hoặc giảm concurrency.

Log nên chứa eventId, topic, partition, offset, delivery attempt, delay được chọn và exception class. Không log toàn bộ payload nhạy cảm.

## 13. Kiểm thử jitter

Kiểm thử cần xác nhận cả giới hạn toán học lẫn hành vi hệ thống.

### 13.1. Kiểm thử BackOffExecution

Với custom BackOff, inject random source xác định trong test. Ví dụ random source trả về một nửa bound:

~~~java
FullJitterExponentialBackOff backOff =
        new FullJitterExponentialBackOff(
            500L,
            2.0,
            2_000L,
            4,
            bound -> bound / 2
        );

BackOffExecution execution = backOff.start();

long first = execution.nextBackOff();
long second = execution.nextBackOff();
long third = execution.nextBackOff();
long fourth = execution.nextBackOff();
long finished = execution.nextBackOff();
~~~

Với ceiling 500, 1.000, 2.000 và 2.000 ms, test có thể xác nhận delay được trả về nằm trong khoảng cho phép và lần tiếp theo trả về STOP. Vì random source đã được kiểm soát, kết quả test không phụ thuộc thời điểm chạy.

Nên kiểm tra thêm:

- initialInterval phải dương.
- maxInterval không nhỏ hơn initialInterval.
- multiplier không nhỏ hơn 1 và phải hữu hạn.
- maxRetries bằng 0 phải trả STOP ngay.
- Delay không âm và không vượt ceiling.
- Ceiling không vượt maxInterval sau nhiều lần retry.
- Mỗi lần gọi start() tạo execution độc lập.

### 13.2. Kiểm thử phân bố

Với random source thật, không nên viết test đòi hỏi một chuỗi số ngẫu nhiên chính xác. Thay vào đó, chạy nhiều mẫu và kiểm tra mọi delay nằm trong giới hạn; có thể kiểm tra phân bố sơ bộ với số mẫu đủ lớn, nhưng tránh ngưỡng thống kê quá chặt khiến test flaky.

Kiểm thử tích hợp nên mô phỏng nhiều consumer cùng thất bại rồi phục hồi dependency. Ghi lại timestamp của request retry để so sánh độ tập trung trước và sau jitter. Dùng tải đủ lớn để thấy sự khác biệt; một consumer duy nhất không thể chứng minh lợi ích phân tán.

### 13.3. Kịch bản cần mô phỏng

1. Nhiều consumer nhận cùng lỗi 503 trong cùng một khoảng thời gian.
2. Dependency phục hồi sau vài giây và có giới hạn request/giây.
3. Retry không jitter để quan sát các đỉnh request đồng bộ.
4. Retry có full jitter để đo phân bố request.
5. Dependency tiếp tục lỗi quá maxRetries và record được chuyển DLT.
6. Một số lần gọi thành công về mặt side effect nhưng phản hồi timeout, xác nhận idempotency ngăn duplicate.
7. Retry topic trì hoãn record trong khi record khác tiếp tục xử lý, xác nhận tác động tới ordering.
8. Tăng số consumer trong lúc dependency gần bão hòa, xác nhận rate limit/concurrency limit vẫn bảo vệ được dependency.

## 14. Những lỗi thường gặp khi cấu hình jitter

| Cách làm | Vấn đề | Cách xử lý |
|---|---|---|
| Dùng fixed delay giống nhau cho mọi consumer | Các consumer có thể retry đồng loạt | Thêm jitter vào backoff |
| Chỉ dùng exponential backoff | Lịch retry vẫn đồng bộ nếu cùng bắt đầu | Kết hợp randomization |
| Jitter không có max delay | Thời gian chờ có thể vượt SLA | Đặt ceiling tối đa |
| Retry vô hạn | Record lỗi giữ tài nguyên và có thể làm lag kéo dài | Giới hạn số lần thử và có recovery |
| Full jitter cho delay quá nhỏ | Có thể thử lại trước khi dependency kịp phục hồi | Dùng equal jitter hoặc floor delay |
| Chỉ thêm jitter mà không rate limit | Tổng request vẫn có thể vượt capacity | Giới hạn concurrency và request rate |
| Retry ở nhiều tầng không có budget | Số lần gọi dependency bị nhân lên | Xác định tổng retry budget |
| Tạo eventId mới ở mỗi lần thử | Không nhận diện được duplicate | Giữ eventId ổn định |
| Coi timeout là chắc chắn chưa thực hiện side effect | Có thể tạo giao dịch hoặc cập nhật lặp | Dùng idempotency key |
| Chỉ đo tổng retry count | Không biết request có còn đồng bộ hay không | Theo dõi histogram delay và request rate |

## 15. Quy trình triển khai trong production

Khi đưa jitter vào một consumer group đang chạy:

1. Đo baseline: retry rate, dependency latency, request burst và consumer lag.
2. Phân loại exception để chỉ retry lỗi có khả năng phục hồi.
3. Chọn blocking retry hoặc retry topic dựa trên ordering và thời gian chờ.
4. Chọn full jitter, equal jitter hoặc decorrelated jitter.
5. Đặt initial delay, multiplier, max delay và max retries theo SLA.
6. Đảm bảo dependency có timeout và consumer có idempotency.
7. Giới hạn concurrency hoặc request rate nếu dependency có quota.
8. Triển khai thử trên một nhóm consumer hoặc một workload có thể quan sát riêng.
9. So sánh histogram request retry, dependency saturation, lag và DLT trước/sau.
10. Mở rộng cấu hình sau khi xác nhận dependency ổn định và retry budget phù hợp.

Khi rollback, hãy cân nhắc rằng việc bỏ jitter có thể làm các lần retry đồng bộ trở lại. Không thay đổi backoff trong lúc một lượng lớn record đang chờ mà không quan sát tác động tới consumer group.

## 16. Nguyên tắc sử dụng jitter

- Dùng jitter khi nhiều consumer hoặc client có thể gặp cùng một lỗi và retry cùng lúc.
- Kết hợp jitter với exponential backoff và max delay.
- Giới hạn số lần thử và tổng thời gian retry.
- Chọn full jitter khi cần phân tán mạnh; chọn equal jitter khi cần thời gian nghỉ tối thiểu.
- Dùng custom BackOff cho DefaultErrorHandler nếu API version không cung cấp chiến lược phù hợp.
- Với retry topic, xác nhận khả năng random backoff của annotation trong đúng version Spring Kafka.
- Giữ retry budget tổng thể khi có nhiều tầng retry.
- Dùng timeout, rate limit, concurrency limit và circuit breaker để bảo vệ dependency.
- Giữ eventId ổn định và làm side effect idempotent.
- Theo dõi phân bố delay, request rate, dependency saturation, consumer lag và DLT.
- Kiểm thử nhiều consumer cùng lỗi và dependency phục hồi dưới tải.

Jitter giúp phá vỡ nhịp retry đồng bộ bằng cách phân tán thời điểm gọi lại. Khi kết hợp với exponential backoff, giới hạn retry, bảo vệ dependency và idempotency, Spring Kafka consumer có thể phục hồi sau sự cố mà không tạo thêm một đợt quá tải ngay khi dịch vụ phụ thuộc bắt đầu hoạt động trở lại.
