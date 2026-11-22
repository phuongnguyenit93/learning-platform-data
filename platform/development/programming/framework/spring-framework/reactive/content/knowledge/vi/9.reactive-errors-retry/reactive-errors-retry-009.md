# Giới hạn thử lại, thời gian lùi và nhiễu ngẫu nhiên trong Project Reactor

## 1. Mục tiêu: thử lại có kiểm soát, không tạo “bão request”

Trong ứng dụng Spring WebFlux, một cuộc gọi HTTP, truy vấn tới dịch vụ bên ngoài hoặc thao tác phụ thuộc hệ thống khác có thể thất bại tạm thời: kết nối bị ngắt, dịch vụ trả HTTP 503, gateway quá tải, hoặc xảy ra timeout. **Retry** là cơ chế đăng ký lại vào nguồn Publisher để thử thực hiện lại công việc, nhưng retry vô hạn hoặc retry đồng loạt có thể làm hệ thống đang yếu trở nên quá tải hơn.

Bài học này tập trung vào ba quyết định phải thiết kế cùng nhau:

1. **Giới hạn số lần thử lại** (*retry limit*): sau bao nhiêu lỗi thì dừng, trả lỗi hoặc fallback?
2. **Thời gian lùi** (*backoff*): đợi bao lâu giữa các lần thử để không tấn công lại dịch vụ quá nhanh?
3. **Nhiễu ngẫu nhiên** (*jitter*): thay đổi thời gian đợi giữa các client để tránh hàng loạt request đồng bộ dồn vào cùng thời điểm?

Sau khi học, bạn cần phân biệt `retry` với `retryWhen`, sử dụng `Retry.max`/`Retry.fixedDelay`/`Retry.backoff`, hiểu `maxAttempts` đếm **số lần retry**, biết lọc loại lỗi được phép thử, xử lý retry exhaustion, và dùng đúng chiến lược với mã bất đồng bộ trong Spring WebFlux.

**Quan trọng:** retry là một chính sách phục hồi có điều kiện. Không phải mọi lỗi đều tạm thời; thao tác không idempotent có thể tạo tác dụng phụ lặp lại. Hãy cân nhắc ngữ nghĩa nghiệp vụ trước khi bật retry.

## 2. Retry của Reactor là **đăng ký lại Publisher**, không phải tiếp tục từ chỗ lỗi

Giả sử:

~~~java
Mono<String> result = callRemote()
    .retry(2);
~~~

`retry(2)` cho phép **hai lần đăng ký lại** sau lỗi, tức tối đa **ba lần thực hiện**: một lần ban đầu và hai lần retry. Nếu lần thứ ba vẫn lỗi, downstream nhận tín hiệu `onError`. Nếu bất kỳ lần nào thành công, luồng kết thúc theo tín hiệu thành công và dừng retry.

~~~text
Subscriber đăng ký
       |
       v
Attempt 1: subscribe nguồn -> onError(temporary) --+
                                                    |
                                         retry #1 (resubscribe)
                                                    |
                                                    v
Attempt 2: subscribe nguồn -> onError(temporary) --+
                                                    |
                                         retry #2 (resubscribe)
                                                    |
                                                    v
Attempt 3: subscribe nguồn -> onNext(data) -> onComplete
                                                    |
                                                    v
                              Downstream nhận data và complete
~~~

Retry **không khôi phục trạng thái nội bộ** của subscription cũ và không “quay lại một dòng Java” trong cùng một lần thực thi. Nó tạo **subscription mới** vào upstream của toán tử retry. Vì vậy:

- `Mono.defer(...)`, `Mono.fromCallable(...)`, repository hoặc HTTP request nguồn có thể chạy lại.
- Nếu nguồn là `Mono.just(expensiveOperation())`, đối số Java đã được tính ngay khi lắp ráp Publisher; retry không khiến lời gọi `expensiveOperation()` chạy lại. Nếu muốn thử lại hành động thật, phải bọc hành động ở nguồn có khả năng thực hiện lại **khi subscribe**, như `Mono.defer(() -> client.get(...))` hoặc `Mono.fromCallable(() -> blockingCall())`.
- Với một `Flux` đã phát các phần tử rồi mới lỗi, retry có thể khiến subscription mới **phát lại các phần tử từ đầu**. Subscriber có thể nhận phần tử trùng lặp. Retry không tự bảo đảm *exactly-once processing*.
- Nếu có side effect (ghi DB, thanh toán, gửi email), mỗi subscription mới có thể lặp side effect. Bất cứ dữ liệu nào đã được ghi trước lỗi **không tự rollback**.

~~~java
// Minh họa: code có thể chạy lại mỗi lần được subscribe.
AtomicInteger attempts = new AtomicInteger();

Mono<String> source = Mono.defer(() -> {
    int n = attempts.incrementAndGet();
    return n < 3
        ? Mono.<String>error(new IllegalStateException("temporary"))
        : Mono.just("OK");
});

Mono<String> recovered = source.retry(2);
~~~

Ở đây `source` là *cold* và có logic được chạy cho từng subscription, nên lần thử thứ ba có thể thành công. `AtomicInteger` chỉ phục vụ minh họa; không dùng biến mutable dùng chung xuyên người dùng như cách triển khai retry trong dịch vụ thực.

## 3. Giới hạn số lần retry: đếm đúng để tránh vượt ngân sách

### 3.1. `retry(n)` và `Retry.max(n)`

Hai cách ngắn:

~~~java
source.retry(3);

source.retryWhen(Retry.max(3));
~~~

Cả hai cho phép **tối đa ba lần retry** sau lần subscribe ban đầu (tối đa bốn lần thực hiện nguồn nếu lần nào cũng thất bại). Đây **không phải** giới hạn tổng cộng ba lần gọi. Trong ví dụ, các lần được đánh số:

| Lần thực hiện nguồn | Tính chất | Số retry đã thực hiện |
| --- | --- | --- |
| 1 | Lần gốc | 0 |
| 2 | Retry thứ nhất | 1 |
| 3 | Retry thứ hai | 2 |
| 4 | Retry thứ ba | 3 |
| Lần thứ 4 vẫn lỗi | Dừng, không có lần 5 | Ngân sách retry đã hết |

`retry(n)` là cách đơn giản, thường **retry ngay**, không chờ exponential backoff. `Retry.max(n)` là một `RetrySpec` cũng giới hạn số lần retry và dễ mở rộng thêm `filter`, `doBeforeRetry` hoặc quy tắc exhaustion. Với lỗi dịch vụ bên ngoài, retry liên tục không delay có thể tạo tải dồn dập; khi cần giảm áp lực cho upstream, ưu tiên chính sách có thời gian đợi.

`Retry.indefinitely()` và `retry()` không có giới hạn số lần là lựa chọn rủi ro với dịch vụ bên ngoài: có thể retry mãi, chiếm tài nguyên và che khuất lỗi hệ thống. Chỉ dùng khi có thiết kế vòng đời, cancellation và điều kiện phục hồi rõ ràng.

### 3.2. `maxAttempts` là số lần retry, không phải tổng số attempts

`Retry.max(2)` có nghĩa tối đa **hai lần retry** = tối đa ba subscriptions trong một đợt thất bại liên tục. Tên field/method `maxAttempts` trong `RetrySpec` và `RetryBackoffSpec` cũng được Javadoc mô tả là **maximum number of retry attempts allowed** (lần thử lại thêm), nên cần tránh hiểu nhầm với “tổng số lần gọi”.

Nếu yêu cầu nghiệp vụ “tối đa ba lần gọi HTTP tính cả lần đầu”, hãy đặt `maxAttempts = 2` và ghi rõ trong cấu hình/số liệu đo đạc.

### 3.3. Retry exhaustion và lỗi cuối cùng

Khi `Retry.max(...)` hoặc `Retry.backoff(...)` đã hết ngân sách, mặc định Reactor phát một **retry-exhausted exception** downstream; có thể nhận biết bằng `Exceptions.isRetryExhausted(error)`. Lỗi gây thất bại cuối được gắn trong `getCause()`. Đây là điểm khác khi chỉ nhìn `source.retry(n)`.

~~~java
Mono<String> result = source.retryWhen(
    Retry.max(2)
        .onRetryExhaustedThrow(
            (spec, signal) -> signal.failure())
);
~~~

Cấu hình `onRetryExhaustedThrow` trên trả về **exception gốc của lần thất bại cuối** khi cạn retry, thay vì wrapper exhaustion mặc định. Chỉ làm vậy nếu ứng dụng đã quyết định muốn giữ nguyên kiểu exception để phân loại/fallback; wrapper mặc định thường có lợi cho quan sát “đã hết ngân sách”.

Ví dụ đọc lỗi mặc định:

~~~java
result.doOnError(error -> {
    if (Exceptions.isRetryExhausted(error)) {
        Throwable lastFailure = error.getCause();
        // Ghi nhận số liệu và lỗi gây thất bại cuối.
    }
});
~~~

Đoạn trên minh họa trong class có import Reactor `reactor.core.Exceptions`; khi dùng với result đã cấu hình trả trực tiếp lỗi gốc bằng `onRetryExhaustedThrow`, kiểm tra `isRetryExhausted` sẽ không còn đúng như mặc định.

## 4. Thời gian lùi: fixed delay và exponential backoff

### 4.1. Tại sao cần đợi?

Nếu một server trả 503 do quá tải, gửi lại ngay một loạt request có thể làm server tiếp tục lỗi. **Backoff** chủ động giãn thời gian trước khi thử lại, cho dịch vụ phụ thuộc cơ hội hồi phục. Thời gian chờ này là một phần latency của request, nên phải nằm trong ngân sách timeout tổng.

Ba chiến lược cơ bản:

| Chiến lược | Cấu hình Reactor | Delay dự kiến |
| --- | --- | --- |
| Retry ngay | `Retry.max(3)` hoặc `retry(3)` | Không chủ động thêm delay |
| Retry sau khoảng cố định | `Retry.fixedDelay(3, Duration.ofMillis(200))` | Khoảng 200 ms cho mỗi lần thử lại |
| Exponential backoff | `Retry.backoff(3, Duration.ofMillis(200))` | Khoảng 200 → 400 → 800 ms theo mặc định, trước khi tính jitter/cap |

`Retry.fixedDelay(maxAttempts, fixedDelay)` tạo chiến lược thời gian chờ cố định, cấu hình min và max backoff bằng nhau, jitter mặc định bị tắt trong factory này. `Retry.backoff(maxAttempts, minBackoff)` khởi tạo chiến lược exponential có jitter.

### 4.2. Exponential backoff hoạt động như thế nào?

Với độ trễ ban đầu `base` và multiplier mặc định `2`, delay lý thuyết trước jitter có thể mô tả:

~~~text
retry #1: base
retry #2: base × 2
retry #3: base × 4
retry #4: base × 8
...
bounded delay = min(maxBackoff, base × 2^(retryIndex - 1))
~~~

Đây là **công thức khái niệm cho multiplier = 2** và không phải lời hứa về thời điểm chạy chính xác của mọi Scheduler. Reactor còn áp dụng giới hạn dưới, giới hạn trên và jitter. Nếu cần thay đổi tốc độ tăng, `RetryBackoffSpec.multiplier(double)` cho phép cấu hình hệ số khác.

Ví dụ muốn không đợi lâu hơn 800 ms:

~~~java
Retry retryPolicy = Retry
    .backoff(5, Duration.ofMillis(100))
    .maxBackoff(Duration.ofMillis(800))
    .jitter(0.0);
~~~

Bảng delay mục tiêu khi **jitter = 0**:

| Retry thứ | Delay lý thuyết |
| --- | ---: |
| 1 | 100 ms |
| 2 | 200 ms |
| 3 | 400 ms |
| 4 | 800 ms |
| 5 | 800 ms (bị chặn bởi `maxBackoff`) |

`minBackoff` là độ trễ cơ sở/lower bound, `maxBackoff` là trần; Reactor không để jitter đẩy delay hợp lệ ra ngoài các mốc min/max đã cấu hình. Tên `maxBackoff` **không phải giới hạn tổng thời gian của cả vòng retry**.

**Không nên đẩy số lần retry lên cao chỉ vì đã có `maxBackoff`**: khi bị giới hạn ở trần, nhiều lượt retry vẫn tiếp tục diễn ra và tổng thời gian có thể lớn. Cần kết hợp số lần retry với timeout tổng và giới hạn concurrency.

### 4.3. Có cần gọi `Thread.sleep` để backoff không?

Không. `retryWhen(Retry.backoff(...))` tự quản lý việc lên lịch delay trong Reactor. Với nguồn non-blocking, thời gian chờ theo Scheduler **không buộc ứng dụng phải giữ một thread ngủ cho từng request**. Mặc định Scheduler dùng cho delay được phân giải từ `Schedulers.parallel()`; có thể thay bằng `scheduler(Scheduler)` trên `RetryBackoffSpec` khi có nhu cầu thực sự.

~~~java
Mono<String> result = nonBlockingHttpCall()
    .retryWhen(
        Retry.backoff(3, Duration.ofMillis(200))
             .maxBackoff(Duration.ofSeconds(2))
    );
~~~

Không chèn `Thread.sleep` trong `map`/`flatMap` trên WebFlux event loop để giả lập backoff: đó là blocking thật, ảnh hưởng khả năng phục vụ request.

## 5. Nhiễu ngẫu nhiên — jitter: tránh “thundering herd”

### 5.1. Vấn đề khi các client retry cùng nhịp

Giả sử 5.000 instance cùng gọi một server lúc 10:00:00 và cùng nhận 503. Nếu tất cả retry với `100, 200, 400, 800 ms` chính xác như nhau, chúng lại đồng thời dồn tải ở các mốc tương tự. Hiện tượng nhiều client thức dậy và tấn công lại cùng lúc thường được gọi là **thundering herd** hoặc **retry storm**.

**Jitter** thêm nhiễu ngẫu nhiên vào delay của mỗi retry để làm lệch thời điểm các instance thử lại, giúp trải tải theo thời gian. Đây không phải cơ chế hạn chế request tuyệt đối và không bảo đảm một dịch vụ quá tải sẽ phục hồi; nó là một thành phần của chính sách resilience.

### 5.2. Cấu hình `jitter(double)`

~~~java
Retry retryPolicy = Retry
    .backoff(3, Duration.ofMillis(200))
    .maxBackoff(Duration.ofSeconds(2))
    .jitter(0.5);
~~~

Ý nghĩa:

- `jitter(0.0)`: tắt nhiễu ngẫu nhiên, hữu ích cho demo/test thời gian, nhưng có thể khiến các client đồng bộ.
- `jitter(0.5)`: mức nhiễu tối đa theo hệ số 50% của delay tính được; đây cũng là **mặc định** của `Retry.backoff` trong Reactor.
- `jitter(1.0)`: cho phép nhiễu lớn hơn, nhưng delay hiệu lực vẫn bị ràng buộc bởi min/max.
- API nhận jitter factor trong khoảng **`0.0` đến `1.0`**. Đừng nhầm `jitter(50)` với 50%.

Nếu delay lý thuyết là 400 ms và jitter factor bằng 0.5, có thể hình dung vùng thay đổi *xấp xỉ* quanh 400 ms trước khi xét min/max. **Không ghi một khoảng ngẫu nhiên cố định như bảo đảm tuyệt đối**: Reactor tính jitter và chặn delay theo giới hạn cấu hình, trong khi scheduler/OS còn có overhead.

### 5.3. Vì sao không kiểm thử bằng `Thread.sleep` và đo thời điểm tuyệt đối?

Khi jitter bật, delay biến động mỗi lần chạy. Ngay cả khi `jitter(0)`, thời gian thực tế còn có việc xếp lịch Scheduler và tải máy. Vì vậy:

- Kiểm thử logic retry thông qua **số lần subscribe**, loại lỗi và giá trị cuối.
- Khi cần kiểm thử delay, tắt jitter và dùng **virtual time** với `reactor-test`/`StepVerifier.withVirtualTime`, xây dựng Publisher sau khi virtual-time scheduler được thiết lập.
- Dùng các assertion có dung sai phù hợp khi đo wall-clock, thay vì khẳng định “đúng 200.000 ms”.
- Không dựa vào thứ tự log của những subscription song song để kết luận jitter có hiệu quả.

## 6. Cấu hình hoàn chỉnh trong `retryWhen`

### 6.1. Mẫu cấu hình có giới hạn, backoff, jitter và filter

~~~java
Retry policy = Retry.backoff(3, Duration.ofMillis(200))
    .maxBackoff(Duration.ofSeconds(2))
    .jitter(0.5)
    .filter(error -> error instanceof java.io.IOException)
    .doBeforeRetry(signal -> {
        long retryIndex = signal.totalRetries() + 1;
        System.out.println("retry=" + retryIndex
            + ", error=" + signal.failure().getMessage());
    });

Mono<String> result = remoteCall().retryWhen(policy);
~~~

`remoteCall()` là phương thức minh họa trả `Mono<String>` trong ứng dụng thật. Đặt filter chỉ cho lỗi có thể phục hồi; trong ví dụ, chỉ một dạng `IOException` được chọn để minh họa. Với HTTP, cần phân loại theo response/exception cụ thể thay vì gom mọi lỗi vào một lớp duy nhất.

### 6.2. `filter`: chỉ retry lỗi tạm thời

Mặc định, các factory `Retry.max`/`Retry.backoff` không giới hạn loại exception theo nghiệp vụ: nếu không có filter, một lỗi đầu vào không hợp lệ có thể bị thử lại vô ích. Ví dụ:

| Lỗi | Gợi ý chính sách | Lý do |
| --- | --- | --- |
| HTTP 503/502/504 khi phụ thuộc tạm quá tải | Có thể retry có backoff, nếu thao tác an toàn | Có cơ hội phục hồi |
| Connection reset, network timeout tạm thời | Có thể retry theo điều kiện | Lỗi có thể chỉ nhất thời |
| HTTP 429 Too Many Requests | Chỉ retry nếu phù hợp chính sách; tôn trọng `Retry-After` nếu có | Cần giảm tải theo yêu cầu server |
| HTTP 400/422 do payload sai | Không retry | Gửi lại cùng payload vẫn sai |
| HTTP 401/403 khi thiếu quyền | Không retry mù quáng | Cần xử lý xác thực/ủy quyền |
| Lỗi validate domain hoặc unique constraint | Thường không retry | Tránh lặp request vô ích hoặc làm sai dữ liệu |
| Lỗi không rõ nguyên nhân | Cần phân loại, quan sát | Không được mặc định retry mọi thứ |

Với `WebClient`, HTTP 4xx/5xx thường được thể hiện qua `WebClientResponseException` khi dùng `retrieve()`. Ví dụ rút gọn trong code của dự án Spring:

~~~java
private boolean isRetryable(Throwable error) {
    if (error instanceof WebClientResponseException ex) {
        int status = ex.getStatusCode().value();
        return status == 429 || status == 502
            || status == 503 || status == 504;
    }
    return error instanceof java.io.IOException;
}
~~~

Đây chỉ là **đoạn minh họa nằm trong class** đã import `org.springframework.web.reactive.function.client.WebClientResponseException`; không phải chương trình độc lập. Chính sách thật còn cần tính đến timeout, exception bị wrap, endpoint, idempotency và quy định API.

### 6.3. `doBeforeRetry`, `doAfterRetry`, `RetrySignal`

`RetryBackoffSpec` và `RetrySpec` có các hook đồng bộ:

- `doBeforeRetry(signal)`: thực thi khi chiến lược quyết định có retry, trước khi phát tín hiệu trigger retry.
- `doAfterRetry(signal)`: chạy sau trigger trong quá trình điều phối retry; không nên hiểu là callback báo **kết quả thành công của lần retry mới**.
- `signal.failure()`: exception gây lỗi ở lượt vừa thất bại.
- `signal.totalRetries()`: số retry tính theo vòng đời retry, bắt đầu **0** ở tín hiệu lỗi đầu tiên.
- `signal.totalRetriesInARow()`: đếm số lần retry trong một chuỗi lỗi liên tục; có thể reset sau khi có `onNext` thành công.

Nếu muốn log “Retry #1” ở lỗi đầu tiên, dùng `signal.totalRetries() + 1`. Không tự dùng hook để gọi `subscribe()` lại: điều đó tạo subscription không thuộc cơ chế retry chính.

**Không đặt công việc blocking dài trong hook đồng bộ.** Nếu thực sự cần hành động bất đồng bộ quanh retry, Reactor có `doBeforeRetryAsync` và `doAfterRetryAsync`, nhận `Mono<Void>`; việc đó có thể làm tăng tổng thời gian trước retry.

## 7. Lỗi liên tiếp và chế độ `transientErrors(true)`

Có những `Flux` tồn tại lâu, phát vài phần tử thành công rồi lại có “đợt” lỗi. Giả sử luồng có các đoạn:

~~~text
onNext(A) -> lỗi -> retry -> onNext(B)
                         -> lỗi -> retry -> onNext(C)
~~~

Với chính sách đếm tổng, số retry đã tiêu dùng ở đợt trước vẫn tính vào ngân sách. Với `transientErrors(true)`, Reactor dùng `totalRetriesInARow()` thay vì `totalRetries()` để đánh giá ngân sách/delay, nên một lần nhận `onNext` sau retry có thể **reset đợt lỗi liên tiếp**.

~~~java
Retry retryTransientBursts = Retry.backoff(2, Duration.ofMillis(100))
    .maxBackoff(Duration.ofSeconds(1))
    .jitter(0.5)
    .transientErrors(true);
~~~

Đặc tính:

- Với `transientErrors(false)` (mặc định), retry count là tổng các lần retry trong subscription.
- Với `true`, giới hạn `2` áp dụng theo các lỗi liên tục **không xen kẽ `onNext`**.
- Sau khi một `onNext` được phát từ nguồn retry, chỉ số liên tiếp được reset; delay backoff của đợt lỗi mới trở lại từ mức cơ sở.
- Đây **không** phải cơ chế tự phát hiện một lỗi thuộc loại “transient” về nghiệp vụ. Vẫn cần `filter` để quyết định loại lỗi nào được retry.
- Trên `Mono` thông thường, một `onNext` thành công đi đến hoàn tất và không tiếp tục có các đợt lỗi trong cùng một subscription; tính năng này chủ yếu hữu ích cho `Flux` dài hạn.

**Cảnh báo về duplicate:** Một `Flux` retry vẫn đăng ký lại upstream. Nếu upstream phát lại dữ liệu từ đầu hoặc tiến trình đọc không lưu checkpoint, downstream có thể nhận dữ liệu lặp, dù counter “in a row” đã reset. Muốn phục hồi stream theo offset/checkpoint, phải thiết kế tại nguồn dữ liệu hoặc giao thức riêng.

Ngoài ra `Retry.maxInARow(n)` là factory count-based cho trường hợp chỉ quan tâm số retry liên tiếp; `Retry.backoff(...).transientErrors(true)` kết hợp việc này với backoff.

## 8. Ví dụ Java 17+ hoàn chỉnh, output xác định

Ví dụ dùng **Project Reactor Core 3.8.8**, Java 17 và Maven. Chúng ta chủ động đặt `jitter(0.0)` trong ca exponential để cấu hình độ trễ không ngẫu nhiên; stdout chỉ in số thứ tự attempt và retry, **không in millisecond thực tế**, vì lịch chạy không hoàn toàn chính xác tới đơn vị ms.

Ba tình huống kiểm thử:
1. Nguồn lỗi hai lần rồi thành công với backoff.
2. Nguồn luôn lỗi, hết hai lần retry và dùng fallback.
3. Lỗi không có trong filter nên **không retry**.

Cấu trúc thư mục:

~~~text
reactor-retry-demo/
├── pom.xml
└── src/main/java/example/RetryPolicyDemo.java
~~~

### 8.1. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-retry-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>example.RetryPolicyDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 8.2. `src/main/java/example/RetryPolicyDemo.java`

~~~java
package example;

import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

public final class RetryPolicyDemo {

    private static Mono<String> transientSource(AtomicInteger attempts) {
        return Mono.defer(() -> {
            int n = attempts.incrementAndGet();
            System.out.println("attempt=" + n);
            if (n < 3) {
                return Mono.<String>error(new IOException("temporary"));
            }
            return Mono.just("OK");
        });
    }

    public static void main(String[] args) {
        System.out.println("== backoff succeeds ==");

        String result = transientSource(new AtomicInteger())
            .retryWhen(
                Retry.backoff(3, Duration.ofMillis(20))
                    .maxBackoff(Duration.ofMillis(80))
                    .jitter(0.0)
                    .filter(IOException.class::isInstance)
                    .doBeforeRetry(signal ->
                        System.out.println(
                            "retry #" + (signal.totalRetries() + 1)
                            + " after " + signal.failure().getMessage()))
            )
            .block();
        System.out.println("result=" + result);

        System.out.println("== exhausted retries ==");

        AtomicInteger failingAttempts = new AtomicInteger();
        Mono<String> alwaysFail = Mono.defer(() -> {
            int n = failingAttempts.incrementAndGet();
            System.out.println("permanent attempt=" + n);
            return Mono.<String>error(new IOException("still unavailable"));
        });

        String fallback = alwaysFail
            .retryWhen(
                Retry.max(2)
                    .filter(IOException.class::isInstance)
                    .doBeforeRetry(signal ->
                        System.out.println(
                            "permanent retry #" + (signal.totalRetries() + 1)))
                    .onRetryExhaustedThrow(
                        (spec, signal) -> signal.failure())
            )
            .onErrorResume(IOException.class,
                error -> Mono.just("DEGRADED"))
            .block();
        System.out.println("fallback=" + fallback);

        System.out.println("== non retryable ==");

        Mono<String> badRequest = Mono.defer(() -> {
            System.out.println("bad attempt=1");
            return Mono.<String>error(
                new IllegalArgumentException("invalid input"));
        });

        String badResult = badRequest
            .retryWhen(
                Retry.backoff(2, Duration.ofMillis(20))
                    .filter(IOException.class::isInstance)
            )
            .onErrorResume(IllegalArgumentException.class,
                error -> Mono.just("REJECTED"))
            .block();
        System.out.println("bad result=" + badResult);
    }
}
~~~

Chạy từ thư mục `reactor-retry-demo` (cài JDK 17+ và Maven):

~~~bash
mvn -q compile exec:java
~~~

**Stdout dự kiến:**

~~~text
== backoff succeeds ==
attempt=1
retry #1 after temporary
attempt=2
retry #2 after temporary
attempt=3
result=OK
== exhausted retries ==
permanent attempt=1
permanent retry #1
permanent attempt=2
permanent retry #2
permanent attempt=3
fallback=DEGRADED
== non retryable ==
bad attempt=1
bad result=REJECTED
~~~

Giải thích theo từng luồng:

- Ca 1: `Retry.backoff(3, ...)` cho phép tối đa **3 retry**, nhưng chỉ cần hai retry để thành công. Retry #1 đợi tối thiểu khoảng 20 ms, retry #2 đợi khoảng 40 ms; stdout không thể hiện delay mà chỉ thể hiện thứ tự sự kiện.
- Ca 2: `Retry.max(2)` khiến nguồn được subscribe **ba lần**. `onRetryExhaustedThrow` trả lỗi `IOException` cuối, vì vậy `onErrorResume(IOException.class, ...)` có thể cung cấp fallback `DEGRADED`.
- Ca 3: `IllegalArgumentException` không khớp filter chỉ retry `IOException`, nên không có lần subscribe thứ hai; fallback xử lý lỗi input ngay.
- Các ca độc lập được `block()` tuần tự **trên thread `main`** để demo đơn giản, không gọi `block()` bên trong thread non-blocking/event loop của WebFlux.
- Chữ `permanent` trong log chỉ để phân biệt kịch bản “nguồn luôn lỗi”; không phải phân loại exception tự động của Reactor.

### 8.3. Cách thay đổi demo để tự kiểm tra

Thử các thay đổi **từng lần một**, đối chiếu kết quả:

- Đổi `Retry.backoff(3, ...)` thành `Retry.max(3)`: số lần gọi vẫn giống khi nguồn thành công ở lượt 3, nhưng không còn delay backoff.
- Đổi `jitter(0)` thành `jitter(0.5)`: stdout vẫn giống về **số lượt và thứ tự logic**; thời gian chờ có thể thay đổi.
- Đổi giới hạn retry của ca 1 thành `Retry.backoff(1, ...)`: chỉ có lần gốc + một retry, nên nguồn vẫn thất bại ở lượt thứ hai và sẽ phát retry-exhausted error nếu không có fallback.
- Đổi filter của ca 3 để chấp nhận `IllegalArgumentException`: lỗi input sẽ bị thử lại dù kết quả vẫn sai, minh họa vì sao filter là bắt buộc về mặt nghiệp vụ.
- Bỏ `onRetryExhaustedThrow` ở ca 2: fallback chỉ bắt `IOException` sẽ không còn bắt wrapper retry-exhausted mặc định theo đúng cách; cần xử lý riêng `Exceptions.isRetryExhausted` hoặc nguyên nhân `getCause()`.

## 9. Spring WebFlux: retry cuộc gọi dịch vụ từ xa an toàn hơn

Trong một dịch vụ WebFlux dùng `WebClient`, luồng có thể viết:

~~~java
// Minh họa một method bên trong service có WebClient được inject.
public Mono<ProductDto> fetchProduct(String id) {
    Retry policy = Retry.backoff(3, Duration.ofMillis(200))
        .maxBackoff(Duration.ofSeconds(2))
        .jitter(0.5)
        .filter(this::isRetryable);

    return webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(ProductDto.class)
        .timeout(Duration.ofSeconds(2))
        .retryWhen(policy)
        .timeout(Duration.ofSeconds(8));
}
~~~

Đây là **đoạn minh họa trong một ứng dụng Spring** đã có `WebClient`, `ProductDto` và hàm `isRetryable(Throwable)`; không phải chương trình độc lập trong mục 8.

Phân tích vị trí toán tử:

1. `bodyToMono` nhận response qua cơ chế non-blocking của WebClient.
2. `timeout(Duration.ofSeconds(2))` **trước** `retryWhen` áp dụng cho từng lần subscription của phần gọi từ xa; nếu một lượt chờ quá 2 giây, nó phát timeout error để retry policy xem xét.
3. `retryWhen(policy)` quyết định thử lại hay chuyển lỗi dựa trên số lượt, backoff và `filter`. Phải bảo đảm `isRetryable` có chính sách rõ ràng với `TimeoutException` nếu muốn retry timeout.
4. `timeout(Duration.ofSeconds(8))` **sau** `retryWhen` đặt một hạn mức chờ cho cả chuỗi từ góc nhìn subscriber. Nó có thể cắt ngang cả giai đoạn đang backoff hoặc đang chờ request; vì vậy “3 retries” là trần cho phép, không bảo đảm đủ 3 retries sẽ diễn ra.
5. `GET` thường hướng đến đọc dữ liệu, nhưng vẫn phải xét các semantics thực tế: server có thể có tác dụng phụ không đúng chuẩn, interceptor có thể tạo log/transaction, v.v.

### 9.1. HTTP 429 và `Retry-After`

Khi dịch vụ trả HTTP 429 hoặc 503 kèm header `Retry-After`, client nên cân nhắc **thời điểm retry do server yêu cầu**. `Retry.backoff(...)` **không tự động đọc và tuân thủ `Retry-After`** trong mọi `WebClient` pipeline. Nếu hợp đồng API đòi tôn trọng header đó, cần tách thông tin status/header ra exception hoặc policy, tính delay phù hợp và bảo đảm vẫn có timeout tổng, giới hạn retry, cap.

Đừng áp một bộ jitter/backoff cố định bất chấp chỉ dẫn retry rõ ràng từ dịch vụ phụ thuộc. Với hệ thống có rate limit, `Retry-After` và global rate limiter có thể quan trọng hơn việc tăng số lượt retry.

### 9.2. Không đặt `block()` hoặc `Thread.sleep` trong handler

Trong WebFlux, việc gọi `Thread.sleep` để delay hoặc `block()` để đợi retry trên event loop sẽ chặn thread xử lý I/O. Nên trả về Publisher:

~~~java
@GetMapping("/products/{id}")
public Mono<ProductDto> product(@PathVariable String id) {
    return productService.fetchProduct(id);
}
~~~

Controller chỉ trả Publisher; framework quản lý subscription, cancellation và truyền lỗi theo vòng đời HTTP. Đừng gọi `subscribe()` riêng bên trong handler rồi trả `Mono.just("OK")` trước khi việc thực sự hoàn tất.

Nếu nguồn là API **blocking legacy**, bọc `Mono.fromCallable(() -> blockingCall())` với `subscribeOn(Schedulers.boundedElastic())` rồi mới thiết kế retry. `Retry.backoff` chỉ đặt delay giữa các lần thực hiện; nó **không biến lời gọi blocking thành non-blocking**.

## 10. Hệ quả về độ trễ, tải hệ thống và độ an toàn dữ liệu

### 10.1. Ngân sách thời gian tổng

Một quy tắc ước lượng:

~~~text
thời gian tối đa ≈
  tổng timeout của từng attempt đã thực hiện
  + tổng backoff giữa các attempt
  + overhead lập lịch, mạng, xử lý downstream
~~~

Ví dụ nếu có **lần gốc + ba retries**, timeout per attempt 2 giây, delay danh nghĩa 0.2, 0.4, 0.8 giây, thì tổng biên lý thuyết có thể xấp xỉ **9.4 giây** trước jitter và overhead. Một HTTP client có deadline 5 giây sẽ không cho phép vòng retry chạy trọn vẹn, và đó có thể là quyết định đúng để tránh user đợi quá lâu.

Không chọn `maxAttempts`, `maxBackoff` và timeout độc lập. Đặt ngân sách retry theo deadline request, SLA và số lượng phụ thuộc trong một request.

### 10.2. Retry có thể khuếch đại tải theo nhiều tầng

Nếu một API Gateway, một service và một HTTP client nội bộ **đều tự retry 3 lần** cho cùng yêu cầu, số lần gọi xuống service cuối có thể nhân lên nhiều lần. Trong hệ thống có nhiều tầng, cần xác định **tầng sở hữu retry** và tránh chồng chính sách tùy tiện.

Cần theo dõi:

- Tổng số attempts / retries / success-after-retry.
- Tỷ lệ exhausted, filter-rejected và fallback.
- Latency end-to-end, latency per attempt, thời gian đợi do backoff.
- Số subscription/request đồng thời, connection pool, thread/queue và số lượng client đang chờ retry.
- Lỗi theo status/type và sự khác biệt giữa timeout tổng với timeout của từng attempt.

### 10.3. Idempotency và “không biết server đã xử lý chưa”

Một request POST ghi dữ liệu có thể **thành công ở server nhưng client timeout trước khi nhận response**. Retry request đó có thể tạo hai đơn hàng, hai email hoặc hai lần thanh toán.

Biện pháp tùy nghiệp vụ:

1. Chỉ tự động retry thao tác **idempotent** theo hợp đồng API, hoặc dùng **idempotency key** được server hỗ trợ để khử trùng lặp.
2. Với ghi DB, cân nhắc transaction, unique key, outbox/inbox hoặc điều kiện cập nhật có version để ngăn side effect lặp.
3. Nếu mất kết nối sau khi gửi request, không kết luận chắc server chưa xử lý. Có thể cần query trạng thái trước khi gửi lại.
4. Với thanh toán và các thao tác không thể đảo ngược, thiết kế workflow chuyên dụng thay vì bọc `retryWhen` quanh lời gọi một cách mù quáng.

### 10.4. Kết hợp rate limiting, circuit breaker và bulkhead

Retry có backoff và jitter là **một** lớp resilience, không thay thế:

- **Rate limiter**: bảo vệ giới hạn lưu lượng.
- **Circuit breaker**: tạm ngăn gọi tới phụ thuộc đang lỗi ở mức hệ thống, thay vì mọi request liên tục thử lại.
- **Bulkhead/concurrency cap**: giới hạn số thao tác đang chiếm tài nguyên.
- **Per-attempt và global timeout**: giữ request trong thời gian chấp nhận được.
- **Fallback có ý nghĩa nghiệp vụ**: ví dụ dùng cache cũ có nhãn rõ ràng nếu dữ liệu tạm không có.

Cẩn thận với vòng lặp “retry trên fallback”: nếu đã chọn fallback thành công, đừng để một retry ở phía ngoài lại gửi request chính chỉ vì fallback dùng tín hiệu không phù hợp.

## 11. Các lỗi phổ biến và cách phòng tránh

**Lỗi 1 — Nhầm `maxAttempts` với tổng số lần gọi.** `Retry.max(3)` cho phép **một lần ban đầu + ba lần retry**, không phải ba lần tổng.

**Lỗi 2 — Retry vô hạn với lỗi business cố định.** HTTP 400 hoặc validation fail thường sẽ không được sửa bằng việc gửi lại. Cấu hình `filter` loại bỏ lỗi không retry được.

**Lỗi 3 — Dùng `Retry.max` cho dịch vụ đang quá tải mà không backoff.** Các request có thể được gửi lại liên tục. Với lỗi tạm thời, dùng `Retry.backoff` và trần delay/thời gian.

**Lỗi 4 — Không có jitter khi hàng nghìn client retry cùng lúc.** Delay theo cùng mốc dễ gây thundering herd. Chọn jitter hợp lý, kết hợp rate limiting.

**Lỗi 5 — Tin rằng jitter làm delay ngẫu nhiên không giới hạn.** Jitter factor phải thuộc 0..1; delay hiệu lực vẫn có min/max, và lịch chạy bị ảnh hưởng bởi tải.

**Lỗi 6 — Dùng `Mono.just(remoteCallBlocking())` rồi mong retry gọi lại API.** Đối số Java đã được đánh giá khi assembly. Dùng `Mono.fromCallable`/`Mono.defer` và Scheduler phù hợp cho tác vụ blocking.

**Lỗi 7 — Không nhận ra `retryWhen` là resubscribe.** Với `Flux` hoặc thao tác ghi dữ liệu, có thể nhận duplicate hoặc lặp side effect. Thiết kế checkpoint/idempotency.

**Lỗi 8 — Mặc định mọi IOException hoặc mọi HTTP 5xx đều nên retry.** Cần xét endpoint, method, idempotency, status cụ thể và yêu cầu từ server.

**Lỗi 9 — Bắt sai loại exception sau khi exhausted.** Mặc định Reactor có retry-exhausted wrapper, không nhất thiết là loại exception gốc. Xét `Exceptions.isRetryExhausted`/`getCause()` hoặc cấu hình `onRetryExhaustedThrow`.

**Lỗi 10 — Đặt `onErrorResume` trước `retryWhen` mà không hiểu hệ quả.** Nếu `onErrorResume` thay lỗi bằng một kết quả thành công, `retryWhen` phía sau **không còn thấy lỗi** để retry. Đặt fallback sau retry nếu mục tiêu là chỉ dùng fallback khi đã retry thất bại.

**Lỗi 11 — Tưởng `transientErrors(true)` tự phân loại IOException hoặc HTTP 503.** Nó chỉ đổi cách **đếm chuỗi lỗi và backoff** theo sự xuất hiện của `onNext`; phân loại lỗi vẫn cần `filter`.

**Lỗi 12 — Đưa `Thread.sleep` trong reactive pipeline để tạo backoff.** Làm chặn thread; dùng Scheduler-based delay của `Retry.backoff`.

**Lỗi 13 — Không tính deadline tổng.** Retry ba lần với timeout mỗi lần dài có thể làm request vượt SLA nhiều giây. Đặt timeout tổng phía sau retry và monitor.

**Lỗi 14 — Dùng số retry giống nhau ở mọi tầng.** Có thể nhân tải xuống phụ thuộc; cần ngân sách retry ở cấp request và xác định chủ sở hữu policy.

**Lỗi 15 — Log số retry sai một đơn vị.** `RetrySignal.totalRetries()` bằng 0 ở lần lỗi đầu tiên; để log retry thứ nhất dùng `totalRetries() + 1`.

**Lỗi 16 — Cho rằng cancellation bảo đảm dừng ngay side effect ở server.** Cancel có thể ngăn request tiếp theo hoặc lịch retry, nhưng một thao tác phía server đã bắt đầu có thể vẫn chạy. Không dùng cancel thay transaction/compensation.

## 12. Bài tập tự kiểm tra

1. `Retry.max(2)` cho phép tối đa bao nhiêu lần subscription nguồn nếu luôn lỗi? **Ba**: lần gốc cộng hai retries.
2. Một hệ thống cần tổng tối đa bốn lần gọi. Nên đặt `maxAttempts` bằng bao nhiêu? **Ba**.
3. `Retry.backoff(4, Duration.ofMillis(100)).maxBackoff(Duration.ofMillis(400)).jitter(0)` có delay danh nghĩa thế nào? **100, 200, 400, 400 ms**.
4. Hai nghìn client cùng gặp 503 và retry ở 100/200/400 ms chính xác như nhau. Vì sao có thể không tốt? **Các lượt thử trùng thời điểm**, làm tăng tải dồn; cần jitter/rate limit.
5. `Retry.fixedDelay(3, Duration.ofMillis(200))` khác `Retry.backoff(3, Duration.ofMillis(200))` ở điểm nào? **Fixed delay chờ khoảng 200 ms mỗi lượt; backoff tăng delay theo cấp số nhân và mặc định có jitter**.
6. `Mono.just(doRemoteCall()).retryWhen(...)` có bảo đảm gọi lại `doRemoteCall()` khi retry không? **Không**, đối số đã được đánh giá khi lắp ráp.
7. Nguồn trả HTTP 400 do payload sai. Nên retry bao nhiêu lần? **Thông thường 0**, sửa request trước.
8. Mặc định khi `Retry.max(2)` cạn retry, downstream nhận luôn cùng exception gốc không? **Không nhất thiết**; Reactor thường dùng retry-exhausted wrapper với nguyên nhân là exception cuối.
9. `jitter(0.5)` có làm thứ tự callback/attempt bị đảo không? **Không theo ngữ nghĩa retry tuần tự của một subscription**; nó chủ yếu thay đổi thời điểm delay giữa attempts. Nhiều subscription chạy song song có thể xen log tùy lịch.
10. Khi `transientErrors(true)`, điều gì reset bộ đếm lỗi liên tiếp? **Một hoặc nhiều `onNext` phục hồi giữa các đợt lỗi**.
11. Đặt `onErrorResume` trước `retryWhen` rồi biến lỗi thành `Mono.just("cached")` thì còn retry lỗi cũ không? **Không**, vì lỗi đã được chuyển thành thành công.
12. Vừa có timeout per attempt 2 giây vừa có timeout tổng 5 giây. Liệu luôn chạy đủ ba retries không? **Không**, timeout tổng có thể kết thúc pipeline trước đó.
13. Khi retry POST thanh toán sau timeout, rủi ro lớn nhất là gì? **Server có thể đã thực hiện thanh toán dù client chưa biết**, retry có thể nhân đôi thao tác; cần idempotency key/workflow.
14. Có nên chỉ tăng `maxBackoff` để bảo đảm không vượt ngân sách tổng thời gian? **Không**. Cần tính cả số retries, timeout từng attempt, jitter, scheduler và deadline toàn chuỗi.

## 13. Tổng kết và tài liệu tham khảo

Một cấu hình mẫu dễ đọc khi gọi dịch vụ ngoài:

~~~java
Retry resilientPolicy = Retry.backoff(3, Duration.ofMillis(200))
    .maxBackoff(Duration.ofSeconds(2))
    .jitter(0.5)
    .filter(this::isRetryable);
~~~

Hãy đọc nó thành: “Sau lỗi được phân loại là retryable, cho phép tối đa **ba lần retry**, bắt đầu đợi khoảng **200 ms**, tăng theo backoff nhưng không vượt trần **2 giây**, thêm jitter để tránh các client cùng retry một lúc.” Ngoài cấu hình này vẫn cần deadline tổng, giám sát, giới hạn concurrency và bảo đảm thao tác an toàn khi lặp lại.

Tài liệu đối chiếu API:

- [Reactor Core Reference — Handling Errors, mục Retrying](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): `retry`, `retryWhen`, retry signal, transient errors.
- [Reactor API — Retry](https://projectreactor.io/docs/core/release/api/reactor/util/retry/Retry.html): factory `max`, `maxInARow`, `fixedDelay`, `backoff`.
- [Reactor API — RetryBackoffSpec](https://projectreactor.io/docs/core/release/api/reactor/util/retry/RetryBackoffSpec.html): `minBackoff`, `maxBackoff`, `multiplier`, `jitter`, `filter`, `scheduler` và exhaustion.
- [Reactor API — RetrySpec](https://projectreactor.io/docs/core/release/api/reactor/util/retry/RetrySpec.html): giới hạn số lần retry, exception filtering, hook và exhaustion.
- [Reactive Streams Specification](https://github.com/reactive-streams/reactive-streams-jvm#specification): tín hiệu `onError`, `onComplete`, `cancel` và quy tắc Publisher/Subscriber.
