# Timeout, retry, hủy đăng ký và giải phóng tài nguyên

Trong ứng dụng reactive dùng Spring Data Elasticsearch, các thao tác đọc và ghi thường được biểu diễn bằng `Mono` hoặc `Flux`. Pipeline có thể tiếp tục qua nhiều bước bất đồng bộ, nhưng vẫn cần giới hạn thời gian chờ, xử lý lỗi tạm thời, dừng công việc khi không còn người nhận và giải phóng tài nguyên đã mở.

Bốn cơ chế này có liên quan nhưng không thay thế nhau:

- **Timeout** giới hạn thời gian một thao tác hoặc toàn bộ pipeline được phép chạy.
- **Retry** đăng ký lại nguồn Publisher sau một lỗi có thể phục hồi.
- **Cancellation** thông báo rằng subscriber không còn quan tâm đến kết quả và yêu cầu upstream dừng công việc.
- **Resource cleanup** đóng hoặc trả lại tài nguyên khi pipeline hoàn tất, thất bại hoặc bị hủy.

Thiết kế đúng cần xét cả thời điểm timeout, loại lỗi, tính idempotent của thao tác Elasticsearch, khả năng hủy request ở transport và vòng đời tài nguyên như connection, scheduler, scroll hoặc Point in Time (PIT). Reactive không tự động làm cho một thao tác an toàn khi retry hay bảo đảm server dừng ngay khi subscriber hủy.

## 1. Vòng đời của một reactive operation

### 1.1. Publisher mô tả công việc, subscription kích hoạt công việc

Các API reactive của Spring Data Elasticsearch thường trả về `Mono<T>` hoặc `Flux<T>`. Ví dụ:

~~~java
Mono<Product> saved = reactiveOperations.save(product);

Flux<Product> products = reactiveOperations.search(
    query,
    Product.class
);
~~~

Việc tạo biến `saved` hoặc `products` thường chỉ tạo một Publisher. Công việc được kích hoạt khi có subscription.

Trong WebFlux, framework thường subscribe Publisher được controller trả về. Ở tầng service, nên trả Publisher cho caller quản lý thay vì gọi `subscribe()` thủ công.

### 1.2. Một pipeline có thể có nhiều trạng thái kết thúc

~~~mermaid
stateDiagram-v2
    [*] --> Created
    Created --> Subscribed
    Subscribed --> Running
    Running --> Completed
    Running --> Error
    Running --> Cancelled
    Completed --> Cleanup
    Error --> Cleanup
    Cancelled --> Cleanup
    Cleanup --> [*]
~~~

Một subscription có thể kết thúc theo ba tín hiệu chính:

- `onComplete`: Publisher hoàn tất bình thường.
- `onError`: Publisher phát sinh lỗi.
- `cancel`: subscriber yêu cầu dừng subscription.

Cancellation không phải một loại `onError`. Vì vậy `onErrorResume` không xử lý cancellation và `retryWhen` không retry chỉ vì subscriber đã hủy.

### 1.3. Vì sao cần quản lý toàn bộ vòng đời?

Nếu chỉ thêm timeout mà không hiểu retry, ứng dụng có thể gửi nhiều request hơn dự kiến. Nếu retry mà không xét cancellation, công việc mới có thể tiếp tục được lên lịch sau khi client đã ngắt kết nối. Nếu mở PIT hoặc tài nguyên riêng mà không cleanup trên cả ba nhánh kết thúc, tài nguyên có thể bị giữ lại.

Một pipeline tốt phải trả lời được:

- Một lần request được phép chạy tối đa bao lâu?
- Tổng chuỗi retry được phép kéo dài bao lâu?
- Lỗi nào có thể retry?
- Thao tác có an toàn khi chạy lại không?
- Ai sở hữu subscription và có quyền hủy?
- Tài nguyên nào phải đóng khi complete, error hoặc cancel?

## 2. Các loại timeout cần phân biệt

### 2.1. Connect timeout

Connect timeout giới hạn thời gian thiết lập kết nối tới Elasticsearch hoặc proxy. Nó có thể bao gồm một phần của quá trình kết nối mạng tùy transport.

Nếu endpoint không truy cập được, DNS/network gặp vấn đề hoặc server không nhận kết nối, connect timeout giúp thao tác thất bại sớm thay vì chờ quá lâu.

Connect timeout thuộc cấu hình HTTP transport/client. Reactor `timeout` không thay thế cấu hình kết nối ở tầng transport.

### 2.2. Connection acquisition timeout

Nếu client dùng connection pool, request có thể phải chờ lấy một connection khả dụng. Acquisition timeout giới hạn thời gian chờ trong pool.

Đây là tình huống khác với server chậm: có thể Elasticsearch vẫn khỏe nhưng ứng dụng đã dùng hết connection pool vì quá nhiều request in-flight hoặc response chưa được tiêu thụ/đóng đúng cách.

Nếu acquisition timeout tăng, hãy xem lại concurrency, connection pool và vòng đời response trước khi chỉ tăng pool size.

### 2.3. Response/socket timeout

Response timeout giới hạn thời gian chờ phản hồi từ server sau khi request đã được gửi. Tên cấu hình cụ thể phụ thuộc HTTP client/transport và phiên bản Spring Data Elasticsearch.

Response timeout bảo vệ tầng mạng. Nó thường áp dụng cho request/response exchange, trong khi Reactor timeout có thể bao phủ cả các bước xử lý phía ứng dụng trước hoặc sau request.

Không giả định socket timeout và Reactor timeout có cùng semantics hoặc cùng điểm bắt đầu.

### 2.4. Elasticsearch search timeout

Search API có thể nhận timeout ở phía Elasticsearch để giới hạn thời gian thực hiện tìm kiếm trên shard. Khi hết thời gian, search có thể trả kết quả một phần cùng cờ `timed_out`, tùy request và cấu hình partial results.

Đây là giới hạn thực thi search ở server. Nó không đồng nghĩa với việc client đã ngừng chờ response.

Nếu báo cáo yêu cầu kết quả đầy đủ, ứng dụng cần kiểm tra metadata như `timed_out` và trạng thái shard thay vì coi mọi response hợp lệ là kết quả hoàn chỉnh.

### 2.5. Reactor timeout

Reactor cung cấp operator `timeout` để giới hạn thời gian chờ một Publisher phát tín hiệu:

~~~java
Mono<Product> result = reactiveOperations.findById(id, Product.class)
    .timeout(Duration.ofSeconds(3));
~~~

Nếu Publisher không phát tín hiệu trong khoảng thời gian quy định, downstream nhận `TimeoutException` (hoặc exception được cấu hình), và Reactor hủy subscription upstream.

Timeout này có thể bao phủ cả thời gian chờ request và các operator trước đó trong vị trí đặt nó. Vị trí operator trong chain quyết định chính xác phần công việc được đo.

### 2.6. Timeout cho từng lần thử và timeout tổng thể

Một operation có thể có nhiều lần retry. Cần phân biệt:

- **Per-attempt timeout**: giới hạn thời gian cho từng lần gọi Elasticsearch.
- **Overall deadline**: giới hạn tổng thời gian từ lần đầu tới khi hoàn tất hoặc dừng retry.

Ví dụ một lần gọi tối đa 3 giây, retry tối đa 3 lần, nhưng toàn operation chỉ được phép chạy 10 giây.

Nếu chỉ đặt timeout cho từng lần thử mà không có deadline tổng thể, thời gian chờ cộng dồn và backoff có thể vượt SLA của API.

## 3. Đặt timeout trong Reactor pipeline

### 3.1. Timeout cho một lần gọi

~~~java
Mono<Product> findProduct(String id) {
    return reactiveOperations.findById(id, Product.class)
        .timeout(Duration.ofSeconds(3));
}
~~~

Đây là cách đơn giản để giới hạn thời gian chờ của thao tác đọc. Khi timeout, lỗi được truyền downstream.

Nếu có fallback hợp lệ, có thể xử lý ở tầng service:

~~~java
Mono<Product> findProductOrEmpty(String id) {
    return reactiveOperations.findById(id, Product.class)
        .timeout(Duration.ofSeconds(3))
        .onErrorResume(
            TimeoutException.class,
            error -> Mono.empty()
        );
}
~~~

Chỉ dùng fallback rỗng khi nghiệp vụ coi timeout tương đương không có kết quả hoặc chấp nhận kết quả thiếu. Không biến timeout thành empty một cách tổng quát vì điều đó có thể che giấu lỗi hạ tầng.

### 3.2. Timeout cho từng attempt, retry rồi giới hạn tổng thể

~~~java
Mono<Product> saveWithRetry(Product product) {
    return Mono.defer(() -> reactiveOperations.save(product))
        .timeout(Duration.ofSeconds(3))
        .retryWhen(
            Retry.backoff(3, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(2))
                .jitter(0.5)
                .filter(this::isRetryable)
        )
        .timeout(Duration.ofSeconds(10));
}
~~~

Trong ví dụ:

1. `Mono.defer` tạo operation khi có subscription.
2. Timeout bên trong retry giới hạn mỗi attempt.
3. `retryWhen` chỉ retry lỗi được `isRetryable` chấp nhận.
4. Timeout ngoài cùng giới hạn tổng thời gian của cả chuỗi.

Số 3 trong `Retry.backoff` là số lần retry sau lần đầu, không phải tổng số lần gửi. Cần xác nhận cách đếm attempt trong cấu hình của ứng dụng.

### 3.3. Vị trí timeout làm thay đổi semantics

~~~java
source.timeout(perAttempt)
    .retryWhen(retryPolicy);
~~~

Timeout nằm trước retry nên timeout của một attempt có thể được xem là lỗi để retry.

~~~java
source.retryWhen(retryPolicy)
    .timeout(overallDeadline);
~~~

Timeout nằm sau retry nên giới hạn toàn bộ chuỗi. Khi timeout ngoài cùng xảy ra, pipeline retry bên trong bị cancel.

Nếu chỉ có timeout ngoài cùng, một attempt có thể chiếm gần hết deadline. Nếu chỉ có timeout trong, tổng thời gian có thể kéo dài qua nhiều lần retry.

### 3.4. Timeout cho Flux

Với `Flux`, `timeout(Duration)` thường áp dụng giới hạn thời gian chờ giữa các tín hiệu kế tiếp, không nhất thiết là giới hạn tổng thời gian toàn stream.

~~~java
Flux<SearchHit<Product>> hits =
    reactiveOperations.search(query, Product.class)
        .timeout(Duration.ofSeconds(5));
~~~

Nếu mỗi hit được phát cách nhau dưới 5 giây, stream có thể chạy lâu hơn 5 giây tổng cộng. Nếu cần giới hạn tổng thời gian stream, có thể dùng deadline ở ngoài:

~~~java
Flux<SearchHit<Product>> hits =
    reactiveOperations.search(query, Product.class)
        .timeout(Duration.ofSeconds(5))
        .take(Duration.ofSeconds(30));
~~~

`take(Duration)` hoàn tất stream sau khoảng thời gian được chỉ định. Nếu muốn báo lỗi deadline thay vì complete bình thường, dùng một timeout tổng thể phù hợp với cấu trúc Publisher và scheduler đã chọn.

Đọc kỹ semantics của operator với Mono và Flux; không dùng một con số timeout mà không xác định nó đo thời gian giữa tín hiệu hay tổng thời gian.

### 3.5. Timeout với fallback Publisher

Có thể chỉ định Publisher thay thế khi timeout:

~~~java
Mono<Product> result =
    reactiveOperations.findById(id, Product.class)
        .timeout(
            Duration.ofSeconds(2),
            Mono.defer(() -> cache.findById(id))
        );
~~~

Khi nguồn chính không phát tín hiệu trong thời gian quy định, Reactor chuyển sang Publisher fallback. Nguồn chính bị cancel.

Fallback nên có giới hạn thời gian và semantics rõ ràng. Nếu cache cũng chậm, cần timeout riêng cho cache hoặc một deadline tổng thể cho cả chuỗi.

## 4. Retry trong Reactor

### 4.1. Retry là resubscribe

Retry không tiếp tục từ đúng instruction bị lỗi. Reactor subscribe lại nguồn Publisher theo retry policy.

~~~java
Mono<Product> result =
    reactiveOperations.findById(id, Product.class)
        .retry(2);
~~~

Nếu nguồn là cold Publisher và thao tác được thực hiện khi subscribe, retry sẽ thực hiện lại thao tác đọc. Điều này thường phù hợp với một số lỗi mạng tạm thời.

Với thao tác ghi, retry có thể gửi lại cùng một lệnh. Phải đánh giá tính idempotent trước khi bật retry.

### 4.2. Retry không điều kiện

`retry(n)` thử lại sau mọi error cho tới giới hạn. Cách này đơn giản nhưng thường quá rộng cho ứng dụng production.

Các lỗi như mapping exception, validation failure hoặc authorization error không thể tự hết khi gửi lại. Retry chúng chỉ làm tăng tải và trì hoãn việc báo lỗi thật.

Ưu tiên `retryWhen` với predicate phân loại lỗi.

### 4.3. Exponential backoff và jitter

~~~java
Retry retryPolicy = Retry.backoff(
        3,
        Duration.ofMillis(200)
    )
    .maxBackoff(Duration.ofSeconds(3))
    .jitter(0.5)
    .filter(this::isRetryable);
~~~

`Retry.backoff` tăng khoảng chờ theo lần retry. Jitter thêm biến thiên để nhiều client không cùng retry tại một thời điểm.

Có thể thêm hook để ghi nhận retry:

~~~java
Retry retryPolicy = Retry.backoff(
        3,
        Duration.ofMillis(200)
    )
    .maxBackoff(Duration.ofSeconds(3))
    .jitter(0.5)
    .filter(this::isRetryable)
    .doBeforeRetry(signal -> {
        log.warn(
            "Retrying Elasticsearch operation, attempt={}, cause={}",
            signal.totalRetries() + 1,
            signal.failure().toString()
        );
    });
~~~

Không log payload đầy đủ nếu chứa dữ liệu nhạy cảm. Metric nên đếm retry theo nhóm lỗi, không dùng document ID làm label có cardinality cao.

### 4.4. Phân loại lỗi retryable

Một predicate có thể dựa trên nhóm lỗi:

~~~java
private boolean isRetryable(Throwable error) {
    return error instanceof TimeoutException
        || error instanceof ConnectException
        || isTooManyRequests(error)
        || isTransientServerError(error);
}
~~~

Đây là ví dụ khái niệm. Kiểu exception thực tế phụ thuộc transport và phiên bản client. Trong ứng dụng thực, cần unwrap các wrapper exception phù hợp trước khi phân loại.

Những lỗi thường không nên retry tự động:

- Lỗi mapping hoặc parsing document.
- Validation error.
- 401/403 do authentication hoặc permission.
- Index/mapping không tồn tại do cấu hình sai.
- Query DSL không hợp lệ.
- Lỗi nghiệp vụ không thể khắc phục bằng thời gian chờ.

429, một số lỗi 502/503/504, connection reset và timeout có thể tạm thời, nhưng vẫn phải giới hạn retry và xét idempotency.

### 4.5. Retry exhausted

Khi hết retry budget, Reactor phát lỗi retry exhausted hoặc lỗi cuối cùng tùy cấu hình. Có thể đổi lỗi ở tầng service để tạo contract rõ hơn:

~~~java
.retryWhen(
    Retry.backoff(3, Duration.ofMillis(200))
        .filter(this::isRetryable)
        .onRetryExhaustedThrow((spec, signal) ->
            new ElasticsearchUnavailableException(
                "Elasticsearch operation exhausted retry budget",
                signal.failure()
            )
        )
)
~~~

Không đổi mọi lỗi thành “service unavailable” nếu lỗi ban đầu là mapping hoặc validation. Hãy giữ nguyên nguyên nhân và phân loại lỗi có ý nghĩa.

## 5. Retry phải xét tính idempotent

### 5.1. Timeout không cho biết server đã làm gì

Một tình huống thường gặp:

1. Client gửi lệnh ghi.
2. Elasticsearch nhận và thực hiện lệnh.
3. Response bị mất hoặc đến sau client timeout.
4. Client thấy timeout và không biết lệnh đã thành công chưa.
5. Client retry.

Timeout chỉ cho biết client không nhận được kết quả đúng hạn. Nó không chứng minh server chưa xử lý request.

Vì vậy, retry thao tác ghi cần thiết kế để chạy lại an toàn hoặc có cơ chế xác định trạng thái đã hoàn tất.

### 5.2. Dùng ID ổn định cho thao tác save

Nếu cùng một entity luôn dùng cùng document ID và payload retry không thay đổi, thao tác index/save thường có trạng thái cuối ổn định: document cùng ID được ghi lại.

~~~java
Mono<Product> save(Product product) {
    return Mono.defer(() -> reactiveOperations.save(product));
}
~~~

Điều kiện quan trọng là ID phải ổn định qua các lần subscription. Nếu ID được tạo mới trong mỗi lần retry, thao tác có thể tạo nhiều document.

### 5.3. Các thao tác không idempotent

Cẩn thận với:

- Update script tăng counter.
- Append vào mảng.
- Tạo document bằng ID ngẫu nhiên.
- Tạo event hoặc gửi notification trong cùng pipeline.
- Gọi dịch vụ bên ngoài có side effect.

Nếu retry sau timeout, những thao tác này có thể thực hiện hai lần. Cần event ID để deduplicate, versioning, optimistic concurrency hoặc một quy trình reconciliation.

### 5.4. create và conflict khi retry

Nếu `create` với ID cố định đã thành công ở lần đầu nhưng response bị mất, lần retry có thể nhận version conflict vì document đã tồn tại.

Không tự động coi conflict này là thất bại cuối cùng. Có thể cần đọc document theo ID và so sánh trạng thái/payload để xác định thao tác trước đã thành công hay có xung đột thật.

### 5.5. Retry từng item trong Bulk API

Bulk response có thể có HTTP request thành công nhưng một số item thất bại. Trường hợp này không nhất thiết phát `onError` trong reactive pipeline; ứng dụng có thể nhận response bình thường với metadata `errors` và item statuses.

Do đó:

- Đọc response bulk.
- Xác định item thành công.
- Phân loại từng item lỗi.
- Chỉ tạo retry batch từ item retryable.
- Đưa item lỗi cố định vào dead-letter queue.
- Không retry toàn bộ bulk một cách mù quáng.

`retryWhen` chỉ xử lý error signal của Publisher. Nó không tự đọc cờ `errors` trong một response bulk bình thường.

## 6. Retry và timeout: thứ tự operator

### 6.1. Per-attempt timeout rồi retry

~~~java
Mono<Product> operation =
    Mono.defer(() -> reactiveOperations.save(product))
        .timeout(Duration.ofSeconds(2))
        .retryWhen(
            Retry.backoff(2, Duration.ofMillis(100))
                .filter(this::isRetryable)
        );
~~~

Mỗi lần subscription tới nguồn đều có timeout 2 giây. Nếu một attempt timeout và predicate chấp nhận lỗi, retry policy có thể subscribe lại.

### 6.2. Overall timeout bao quanh retry

~~~java
Mono<Product> operation =
    Mono.defer(() -> reactiveOperations.save(product))
        .timeout(Duration.ofSeconds(2))
        .retryWhen(
            Retry.backoff(3, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(1))
                .filter(this::isRetryable)
        )
        .timeout(Duration.ofSeconds(6));
~~~

Timeout ngoài cùng bao gồm các lần thử và thời gian backoff. Khi deadline hết, upstream retry chain bị cancel.

### 6.3. Đừng retry lỗi timeout tổng thể vô tình

Nếu timeout tổng thể nằm bên trong một retry operator ở tầng ngoài, chính lỗi deadline có thể bị retry lại và làm vượt SLA.

Đặt timeout tổng thể ở ngoài cùng hoặc loại deadline exception khỏi retry predicate. Xác định rõ retry policy nào sở hữu lỗi timeout.

### 6.4. Fallback trước hay sau retry?

Nếu `onErrorResume` xử lý lỗi retryable thành fallback trước `retryWhen`, retry không còn thấy error đó.

~~~java
source
    .onErrorResume(error -> Mono.empty())
    .retryWhen(retryPolicy);
~~~

Ở đây lỗi đã được chuyển thành complete rỗng nên retry không chạy.

Thông thường nên retry lỗi tạm thời trước, rồi mới dùng fallback cho lỗi cuối cùng:

~~~java
source
    .retryWhen(retryPolicy)
    .onErrorResume(
        ElasticsearchUnavailableException.class,
        error -> fallback()
    );
~~~

Fallback phải phản ánh đúng nghiệp vụ; không che giấu lỗi dữ liệu.

## 7. Cancellation trong Reactive Streams

### 7.1. Cancellation là yêu cầu dừng subscription

Subscriber có thể cancel khi:

- Người dùng đóng kết nối HTTP.
- Request bị timeout.
- Operator như `take` đã nhận đủ phần tử.
- Service không còn cần kết quả.
- Job bị dừng hoặc ứng dụng shutdown.
- Một Publisher downstream không còn nhu cầu tiêu thụ dữ liệu.

Cancellation đi ngược từ downstream về upstream qua subscription chain.

### 7.2. Cancellation không phải rollback

Hủy subscription không đảm bảo Elasticsearch rollback một thao tác đã nhận.

Nếu một write request đã tới server, Elasticsearch có thể vẫn hoàn tất write dù client đã ngừng chờ. Transport có thể cố đóng request/connection, nhưng không thể biến cancellation thành transaction rollback.

Với thao tác ghi quan trọng:

- Dùng document ID ổn định.
- Thiết kế update idempotent.
- Ghi nhận operation ID.
- Có thể đọc lại trạng thái để xác minh.
- Dùng durable queue/outbox nếu công việc phải hoàn tất dù client disconnect.

### 7.3. Cancellation không kích hoạt retry

`retryWhen` phản ứng với error signal. Cancellation không phải error signal, nên nó không được retry tự động.

Tương tự, `onErrorResume` không xử lý cancellation. Nếu cần cleanup khi cancel, dùng `doOnCancel`, `doFinally` hoặc resource-scoping operator phù hợp.

### 7.4. Cancellation có thể chỉ dừng phía client

Nếu upstream là Publisher bao một API blocking không hỗ trợ interrupt, cancel có thể không dừng được công việc blocking ngay lập tức.

Tương tự, nếu code đã gọi `subscribe()` để tạo một subscription tách rời, cancellation của request ban đầu không tự hủy subscription phụ đó.

Đây là lý do không nên tạo detached subscription trong controller/service nếu không có owner quản lý vòng đời rõ ràng.

## 8. Quản lý subscription và tránh detached work

### 8.1. Trả Publisher cho caller

Trong WebFlux, controller nên trả Publisher:

~~~java
@GetMapping("/{id}")
public Mono<Product> getProduct(@PathVariable String id) {
    return productService.findById(id);
}
~~~

Khi client disconnect hoặc request timeout ở tầng server, framework có thể cancel subscription và truyền tín hiệu ngược xuống pipeline.

### 8.2. Tránh subscribe trong service

Anti-pattern:

~~~java
public Mono<Product> save(Product product) {
    reactiveOperations.save(product).subscribe();
    return Mono.just(product);
}
~~~

Method trả về trước khi save hoàn tất. Caller không thể quan sát lỗi, chờ kết quả hoặc hủy đúng operation.

Cách đúng:

~~~java
public Mono<Product> save(Product product) {
    return reactiveOperations.save(product);
}
~~~

Nếu cần thêm bước sau save:

~~~java
public Mono<Product> save(Product product) {
    return reactiveOperations.save(product)
        .flatMap(saved ->
            auditService.record(saved)
                .thenReturn(saved)
        );
}
~~~

Toàn bộ công việc nằm trong cùng Publisher.

### 8.3. Khi nào được tự quản lý Disposable?

Một subscription nền do ứng dụng sở hữu, ví dụ worker lâu dài, có thể cần giữ `Disposable` để hủy khi component shutdown.

Trong trường hợp đó:

- Có owner rõ ràng.
- Lưu handle của subscription.
- Dispose khi lifecycle của owner kết thúc.
- Theo dõi lỗi.
- Không tạo một subscription cho mỗi HTTP request rồi bỏ handle.
- Không dùng `subscribe()` như cách né reactive composition.

Các worker nền nên được quản lý bằng lifecycle component, scheduler và durable queue thích hợp.

## 9. Giải phóng tài nguyên với doFinally

### 9.1. doFinally nhận mọi kiểu kết thúc

`doFinally` chạy khi sequence complete, error hoặc cancel:

~~~java
Mono<Product> result =
    reactiveOperations.findById(id, Product.class)
        .doFinally(signalType -> {
            metrics.recordTermination(signalType.name());
        });
~~~

`SignalType` có thể là `ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL`.

Đây là nơi phù hợp cho cleanup đồng bộ, nhẹ như ghi metric, release một permit hoặc cập nhật counter.

### 9.2. doOnCancel chỉ chạy khi cancellation

~~~java
Flux<SearchHit<Product>> hits =
    reactiveOperations.search(query, Product.class)
        .doOnCancel(() ->
            log.debug("Search subscription cancelled")
        );
~~~

`doOnCancel` không chạy cho complete hoặc error. Nếu cần cleanup ở mọi đường kết thúc, dùng `doFinally`.

### 9.3. Cleanup phải idempotent

Có thể nhiều đường code cùng cố giải phóng một tài nguyên. Thiết kế cleanup sao cho không release/close hai lần gây lỗi hoặc làm hỏng pool.

Ví dụ với permit, phải bảo đảm mỗi lần acquire chỉ có đúng một release. Nếu dùng `doFinally`, đặt nó sau vị trí sở hữu permit và bảo đảm permit không được release ở một nhánh khác cùng lúc.

### 9.4. Không dùng doFinally để chờ async cleanup

`doFinally` nhận callback đồng bộ và không compose Publisher cleanup. Nếu cần gọi API bất đồng bộ để đóng PIT, xóa tài nguyên remote hoặc trả resource qua một Publisher, `doFinally` không chờ công việc đó hoàn tất.

Dùng `usingWhen` khi cleanup bất đồng bộ là một phần bắt buộc của lifecycle.

## 10. Quản lý tài nguyên bằng using và usingWhen

### 10.1. using cho tài nguyên đồng bộ

`Mono.using`/`Flux.using` quản lý tài nguyên có hàm cleanup đồng bộ:

~~~java
Mono<Result> result = Mono.using(
    resourceSupplier,
    resource -> performOperation(resource),
    resource -> resource.close()
);
~~~

Resource được tạo khi subscribe, được dùng trong closure và được cleanup khi sequence kết thúc hoặc bị hủy theo semantics của operator.

Dùng `using` cho tài nguyên có `close()` đồng bộ, ví dụ một handle local. Không đặt cleanup blocking nặng trên event-loop.

### 10.2. usingWhen cho cleanup bất đồng bộ

Với resource cần mở và đóng bằng Publisher, dùng `usingWhen`:

~~~java
Mono<SearchResult> result = Mono.usingWhen(
    openPointInTime(),
    pit -> searchWithPointInTime(pit),
    pit -> closePointInTime(pit),
    (pit, error) -> closePointInTime(pit),
    pit -> closePointInTime(pit)
);
~~~

Các tham số lần lượt xử lý:

1. Resource supplier.
2. Công việc sử dụng resource.
3. Cleanup khi complete.
4. Cleanup khi error.
5. Cleanup khi cancel.

`usingWhen` chờ Publisher cleanup tương ứng theo lifecycle. Đây là lựa chọn phù hợp hơn `doFinally` khi cleanup cần I/O bất đồng bộ.

### 10.3. Cleanup lỗi cũng cần được quan sát

Nếu Publisher cleanup thất bại, lỗi cleanup có thể ảnh hưởng terminal signal của pipeline hoặc che khuất lỗi ban đầu tùy operator/đường kết thúc.

Cần quyết định:

- Cleanup failure có làm request thất bại không?
- Có cần retry việc đóng resource không?
- Có cần ghi metric/alert và lưu resource ID để dọn sau?
- Có thể bỏ qua lỗi cleanup trong một số tình huống không?

Nếu dùng `onErrorResume` trong cleanup để không che lỗi gốc, hãy log và đo lỗi cleanup trước khi chuyển thành complete. Không âm thầm bỏ qua mọi lỗi close.

### 10.4. Resource supplier phải tạo resource theo subscription

Dùng Publisher cold để mở resource khi subscribe. Không mở resource ngay lúc tạo pipeline rồi giữ nó cho một Publisher có thể được subscribe nhiều lần.

~~~java
Mono<Result> operation =
    Mono.defer(() ->
        Mono.usingWhen(
            openResource(),
            resource -> useResource(resource),
            this::closeResource,
            (resource, error) -> closeResource(resource),
            this::closeResource
        )
    );
~~~

`Mono.defer` làm rõ rằng mỗi subscription tạo một lifecycle mới. Điều này đặc biệt quan trọng khi retry hoặc cache/subscribe lại.

## 11. Ví dụ với Elasticsearch Point in Time và scroll

### 11.1. PIT là tài nguyên cần đóng

Point in Time (PIT) giữ một view ổn định của index để phân trang/search qua nhiều request. PIT có thời hạn keep-alive và tiêu thụ tài nguyên ở cluster.

Khi ứng dụng mở PIT, thực hiện nhiều search dùng PIT rồi kết thúc, cần đóng PIT khi không còn dùng.

~~~mermaid
flowchart TD
    A[Subscribe] --> B[Open PIT]
    B --> C[Search pages using PIT]
    C --> D{Complete, error or cancel}
    D -->|Complete| E[Close PIT]
    D -->|Error| E
    D -->|Cancel| E
    E --> F[Finish]
~~~

### 11.2. Đặt PIT trong usingWhen

Ví dụ khái niệm:

~~~java
Mono<List<SearchHit<Product>>> searchAllPages() {
    return Mono.usingWhen(
        openPit(),
        pit -> fetchPages(pit).collectList(),
        this::closePit,
        (pit, error) -> closePit(pit),
        this::closePit
    );
}
~~~

`openPit`, `fetchPages` và `closePit` ở đây là các adapter trả Publisher quanh API PIT của Elasticsearch client đang dùng. Chữ ký cụ thể phụ thuộc phiên bản Java API Client và Spring Data Elasticsearch.

Nếu paging bị timeout hoặc subscriber cancel, cleanup path vẫn được gọi để đóng PIT. Keep-alive vẫn cần được đặt hợp lý vì process có thể crash trước khi cleanup chạy.

### 11.3. Scroll context cũng cần được giải phóng

Scroll API duy trì search context giữa các lần lấy trang. Khi hoàn tất hoặc không còn cần dữ liệu, ứng dụng cần clear scroll context theo API tương ứng.

Không để scroll mở vô thời hạn chỉ vì client đã ngừng đọc. Hãy gắn lifecycle scroll với một resource-scoped Publisher và có cơ chế dọn dẹp khi process crash hoặc request bị hủy.

### 11.4. Không mở PIT/scroll cho mọi query nhỏ

PIT/scroll hữu ích khi cần duyệt dữ liệu lớn hoặc có snapshot semantics phù hợp. Với truy vấn thông thường trả một trang kết quả, không cần tạo thêm resource state.

Dùng PIT/scroll có giới hạn keep-alive, giới hạn số phiên đồng thời và cleanup rõ ràng.

### 11.5. Cleanup không thay thế keep-alive

`usingWhen` giúp cleanup khi pipeline kết thúc bình thường, lỗi hoặc cancel. Nó không chạy được nếu process bị kill, máy mất điện hoặc JVM crash.

Keep-alive là lớp bảo vệ bổ sung để server tự giải phóng resource sau một khoảng thời gian. Chọn keep-alive đủ dài cho khoảng nghỉ giữa các trang, nhưng không quá dài làm giữ resource không cần thiết.

## 12. Scheduler và thao tác blocking

### 12.1. Không chặn event-loop

Reactive Elasticsearch client thường dựa trên I/O bất đồng bộ. Callback hoặc operator chạy trên event-loop cần hoàn tất nhanh.

Không gọi:

- `Thread.sleep`.
- `block()`.
- File I/O blocking.
- JDBC blocking.
- HTTP client blocking.
- Lock chờ lâu.

Một thao tác blocking có thể làm chậm nhiều request cùng dùng event-loop.

### 12.2. Bọc blocking work khi chưa thể thay thế

Nếu bắt buộc gọi thư viện blocking, cô lập nó trên bounded elastic scheduler:

~~~java
Mono<LegacyResult> result =
    Mono.fromCallable(() -> legacyBlockingClient.call())
        .subscribeOn(Schedulers.boundedElastic());
~~~

Đây là biện pháp tương thích cho một đoạn blocking cụ thể. Ưu tiên API reactive/non-blocking nếu có thể.

Không chuyển toàn bộ Elasticsearch pipeline sang boundedElastic chỉ để che giấu một callback blocking. Điều đó làm giảm khả năng quan sát và có thể gây nghẽn scheduler riêng.

### 12.3. Không tạo scheduler mới cho từng request

Scheduler là tài nguyên dùng chung. Tạo scheduler cho từng request rồi không dispose có thể làm rò thread và tài nguyên.

Dùng scheduler Reactor phù hợp hoặc một scheduler do application quản lý với lifecycle rõ ràng. Nếu tự tạo scheduler, dispose khi component/application shutdown.

## 13. Retry và cancellation trong pipeline có nhiều bước

### 13.1. Retry đặt ở đâu quyết định phần nào chạy lại

~~~java
Mono<Product> result =
    loadProduct(id)
        .flatMap(this::enrich)
        .flatMap(reactiveOperations::save)
        .retryWhen(retryPolicy);
~~~

Retry ở cuối chain có thể resubscribe toàn bộ chain, nghĩa là `loadProduct`, `enrich` và `save` đều chạy lại.

Nếu chỉ muốn retry lệnh save, đặt retry sát operation save:

~~~java
Mono<Product> result =
    loadProduct(id)
        .flatMap(this::enrich)
        .flatMap(product ->
            Mono.defer(() -> reactiveOperations.save(product))
                .retryWhen(retryPolicy)
        );
~~~

Tuy nhiên, nếu save lỗi do dữ liệu đã thay đổi hoặc conflict, chỉ retry save với cùng entity có thể không đúng. Retry boundary phải phản ánh đơn vị công việc có thể chạy lại an toàn.

### 13.2. Cancellation dừng retry đang chờ

Nếu subscriber cancel trong lúc `retryWhen` đang chờ backoff, retry sequence nên dừng và không tạo attempt tiếp theo.

Đừng tự tạo scheduler task detached để retry rồi bỏ qua subscription lifecycle. Hãy để retry policy nằm trong Publisher hoặc quản lý task riêng bằng owner có thể dispose.

### 13.3. Side effect trước retry có thể chạy nhiều lần

~~~java
source
    .doOnNext(this::sendNotification)
    .retryWhen(retryPolicy);
~~~

Nếu lỗi xảy ra sau `sendNotification`, resubscribe có thể gửi notification lần nữa.

Đưa side effect ra khỏi vùng retry, làm nó idempotent hoặc dùng event ID/outbox để deduplicate.

### 13.4. Retry và timeout có thể tạo tải lớn hơn

Timeout làm client kết luận attempt đã quá lâu. Nếu server vẫn đang xử lý, retry có thể tạo request trùng trong khi request cũ chưa dừng.

Đây là một dạng overlapping attempts. Hãy:

- Đặt per-attempt timeout phù hợp với latency thực tế.
- Dùng concurrency limit.
- Dùng idempotency cho write.
- Theo dõi số request còn in-flight.
- Hạn chế retry khi cluster đang quá tải.

## 14. Error handling và fallback

### 14.1. onErrorMap để chuẩn hóa lỗi

~~~java
Mono<Product> result =
    reactiveOperations.findById(id, Product.class)
        .onErrorMap(
            error -> isTransportFailure(error),
            error -> new ElasticsearchUnavailableException(
                "Could not read product",
                error
            )
        );
~~~

Chỉ map nhóm lỗi phù hợp. Giữ cause gốc để log và phân tích.

### 14.2. onErrorResume cho fallback có chủ đích

~~~java
Mono<Product> result =
    reactiveOperations.findById(id, Product.class)
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(
            ElasticsearchUnavailableException.class,
            error -> cache.findById(id)
        );
~~~

Fallback có thể trả dữ liệu cache, nhưng cần cân nhắc freshness và semantics. Không dùng cache cũ cho nghiệp vụ cần dữ liệu nhất quán tuyệt đối.

### 14.3. Empty khác error

`Mono.empty()` biểu thị không có phần tử; nó không có nghĩa timeout hoặc Elasticsearch unavailable.

Phân biệt:

- Không tìm thấy document: có thể là empty.
- Timeout: error.
- Connection failure: error.
- Subscriber cancel: cancellation.
- Search response partial: response có metadata cần đánh giá.

Nếu biến mọi trường hợp thành empty, tầng gọi không thể biết hệ thống đang không có dữ liệu hay đang gặp lỗi.

## 15. Tích hợp timeout và retry với Spring Data Elasticsearch

### 15.1. ReactiveElasticsearchOperations

Một service có thể đặt policy quanh operation của Spring Data:

~~~java
@Service
public class ProductSearchService {

    private final ReactiveElasticsearchOperations operations;

    public ProductSearchService(
            ReactiveElasticsearchOperations operations) {
        this.operations = operations;
    }

    public Mono<Product> findById(String id) {
        return operations.get(id, Product.class)
            .timeout(Duration.ofSeconds(2))
            .retryWhen(
                Retry.backoff(2, Duration.ofMillis(100))
                    .maxBackoff(Duration.ofSeconds(1))
                    .jitter(0.5)
                    .filter(this::isRetryable)
            );
    }

    private boolean isRetryable(Throwable error) {
        return error instanceof TimeoutException
            || isTransientElasticsearchFailure(error);
    }
}
~~~

Tên method và overload của `ReactiveElasticsearchOperations` có thể khác giữa các release. Hãy dùng API của dependency dự án. Ví dụ tập trung vào vị trí đặt Reactor operators.

### 15.2. Repository reactive

Cùng nguyên tắc có thể áp dụng cho reactive repository:

~~~java
public Mono<Product> load(String id) {
    return repository.findById(id)
        .timeout(Duration.ofSeconds(2))
        .retryWhen(retryPolicy);
}
~~~

Retry policy nên được chia sẻ có kiểm soát, không sao chép predicate và số lần retry khác nhau giữa mọi method.

### 15.3. Timeout transport/client vẫn cần cấu hình riêng

Reactor timeout không thay thế:

- Connect timeout.
- Connection pool acquisition timeout.
- Response/socket timeout.
- TLS/network timeout.
- Elasticsearch search timeout.

Cấu hình transport phụ thuộc reactive client implementation và version. Hãy kiểm tra cách Spring Data Elasticsearch tạo reactive client trong phiên bản dự án, sau đó cấu hình underlying HTTP transport tương ứng.

Không đặt mọi timeout bằng cùng một giá trị mà không tính quan hệ giữa chúng. Thông thường request timeout ở tầng ứng dụng cần lớn hơn các timeout con cần thiết, còn overall deadline phải bao phủ retry/backoff theo SLA.

### 15.4. Không đóng client sau mỗi operation

Reactive Elasticsearch client, connection pool và template thường là application-scoped bean. Spring quản lý vòng đời của chúng.

Không gọi close/dispose client sau mỗi search/save. Chỉ đóng resource riêng do operation mở, chẳng hạn PIT/scroll, hoặc scheduler/custom client mà component sở hữu.

## 16. Kiểm thử timeout và retry

### 16.1. Dùng StepVerifier với virtual time

Không cần chờ thật nhiều giây để test backoff. Reactor Test hỗ trợ virtual time:

~~~java
@Test
void retriesTransientFailureWithBackoff() {
    AtomicInteger attempts = new AtomicInteger();

    Mono<String> operation = Mono.defer(() -> {
        if (attempts.incrementAndGet() < 3) {
            return Mono.error(new TransientFailure());
        }
        return Mono.just("ok");
    }).retryWhen(
        Retry.backoff(2, Duration.ofSeconds(1))
            .jitter(0d)
    );

    StepVerifier.withVirtualTime(() -> operation)
        .thenAwait(Duration.ofSeconds(3))
        .expectNext("ok")
        .verifyComplete();

    assertThat(attempts).hasValue(3);
}
~~~

Với virtual time, tạo Publisher bên trong supplier của `withVirtualTime` trong test phức tạp để operator lấy virtual scheduler thay vì scheduler đã khởi tạo trước.

### 16.2. Test timeout

~~~java
@Test
void timesOutSlowPublisher() {
    StepVerifier.withVirtualTime(() ->
        Mono.<String>never()
            .timeout(Duration.ofSeconds(5))
    )
    .thenAwait(Duration.ofSeconds(5))
    .expectError(TimeoutException.class)
    .verify();
}
~~~

Test xác nhận timeout signal. Integration test riêng cần xác nhận request thực tế có được hủy ở transport theo khả năng của client.

### 16.3. Test cancellation

~~~java
@Test
void observesCancellation() {
    AtomicReference<SignalType> termination =
        new AtomicReference<>();

    Flux<Long> source = Flux.interval(Duration.ofSeconds(1))
        .doFinally(termination::set);

    StepVerifier.withVirtualTime(() -> source)
        .thenAwait(Duration.ofSeconds(2))
        .thenCancel()
        .verify();

    assertThat(termination.get()).isEqualTo(SignalType.CANCEL);
}
~~~

Test này kiểm tra `doFinally` nhận cancellation. Nó không chứng minh Elasticsearch đã hủy một write request ở server.

### 16.4. Test cleanup cho resource bất đồng bộ

Dùng `usingWhen` và một resource giả có close signal:

~~~java
@Test
void closesResourceOnCancellation() {
    AtomicBoolean closed = new AtomicBoolean();

    Mono<String> operation = Mono.usingWhen(
        Mono.just("pit-id"),
        pit -> Mono.<String>never(),
        pit -> Mono.fromRunnable(() -> closed.set(true)),
        (pit, error) -> Mono.fromRunnable(() -> closed.set(true)),
        pit -> Mono.fromRunnable(() -> closed.set(true))
    );

    StepVerifier.create(operation)
        .thenCancel()
        .verify();

    assertThat(closed).isTrue();
}
~~~

Trong test thực tế, nếu cleanup là asynchronous, hãy assert completion của cleanup Publisher và kiểm tra lỗi cleanup riêng.

### 16.5. Test retry không lặp side effect

Tạo counter cho số lần gọi và side effect. Cho attempt đầu lỗi sau side effect, rồi xác nhận retry không gửi notification trùng hoặc deduplication hoạt động.

Đây là test quan trọng với notification, audit event và update script.

### 16.6. Integration test với Elasticsearch thật

Dùng Elasticsearch test instance tương thích để kiểm tra:

- Request chậm hoặc transport bị ngắt.
- Timeout ở tầng Reactor.
- Retry cho lỗi tạm thời có kiểm soát.
- Bulk partial failure.
- Cancellation của search stream.
- PIT/scroll cleanup.
- Client shutdown.
- Response partial hoặc `timed_out`.

Không chỉ mock `Mono.error`; mock không mô phỏng connection pool, transport cancellation và server-side request processing.

## 17. Theo dõi và vận hành

### 17.1. Metric nên có

Theo dõi các chỉ số:

- Request count và success/error rate.
- Timeout count theo tầng.
- Retry count theo error type.
- Số attempt trung bình cho một operation.
- Retry delay thực tế.
- Cancellation count.
- In-flight request count.
- Connection pool active/pending/idle.
- Search latency p50/p95/p99.
- Bulk latency và rejected items.
- PIT/scroll đang mở và tuổi của chúng.
- Cleanup success/failure.
- Scheduler queue và thread usage.

Dùng label có cardinality thấp. Không gắn document ID hoặc request ID tùy ý làm metric label.

### 17.2. Phân biệt timeout của ứng dụng và timeout của Elasticsearch

Log nên ghi rõ timeout đến từ:

- Connect/acquire/response timeout của transport.
- Search execution timeout của Elasticsearch.
- Reactor per-attempt timeout.
- Overall application deadline.
- Timeout của upstream HTTP request.

Nếu chỉ ghi “Elasticsearch timeout”, khó biết tầng nào cần điều chỉnh.

### 17.3. Cảnh báo resource leak

Theo dõi:

- PIT/scroll không được đóng.
- Connection pool pending tăng kéo dài.
- Số connection active không giảm sau khi tải kết thúc.
- Scheduler thread tăng theo thời gian.
- Retry queue tồn đọng.
- Cleanup failure.
- Request vẫn chạy sau khi caller cancel.

Một lần cleanup thất bại có thể không đáng kể; xu hướng tăng liên tục mới là dấu hiệu cần điều tra.

## 18. Các lỗi thường gặp

| Dấu hiệu | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| API vượt SLA dù mỗi attempt có timeout | Chỉ giới hạn per-attempt, không có overall deadline | Thêm timeout bao ngoài retry chain |
| Retry không chạy sau timeout | Timeout đặt ngoài retry hoặc predicate loại TimeoutException | Kiểm tra vị trí operator và retry predicate |
| Retry chạy cả lỗi mapping | Dùng retry không điều kiện | Phân loại error type |
| Một write bị thực hiện hai lần | Timeout xảy ra sau khi server đã nhận request | Idempotent operation và document ID ổn định |
| Client disconnect nhưng công việc vẫn chạy | Detached subscribe hoặc upstream không hỗ trợ cancel | Compose Publisher và quản lý subscription |
| onErrorResume không chạy khi client cancel | Cancellation không phải error | Dùng doOnCancel/doFinally hoặc usingWhen |
| PIT còn tồn tại sau khi search dừng | Thiếu cleanup trên cancel/error | Quản lý bằng usingWhen và keep-alive |
| Cleanup không hoàn tất trước khi method kết thúc | Dùng doFinally cho async cleanup | Dùng usingWhen |
| Event-loop bị nghẽn | block, sleep hoặc I/O blocking | Dùng API non-blocking hoặc cô lập blocking work |
| Connection pool pending tăng | Quá nhiều request in-flight hoặc response/resource chưa được giải phóng | Giới hạn concurrency và kiểm tra lifecycle |
| Retry tiếp tục sau khi request đã timeout tổng thể | Timeout nằm trong retry boundary sai vị trí | Đặt overall timeout ngoài cùng |
| Fallback che mất lỗi hạ tầng | Chuyển mọi error thành empty | Chỉ fallback nhóm lỗi được phép |
| Auditing/side effect chạy nhiều lần | Retry hoặc nhiều subscription | Thiết kế idempotent và kiểm soát subscription |
| Tài nguyên không được dọn khi JVM crash | Cleanup reactive không chạy khi process chết | Keep-alive, TTL và quy trình reconciliation |

## 19. Quy trình thiết kế một reactive operation

Khi xây thao tác reactive với Spring Data Elasticsearch:

1. Chọn `ReactiveElasticsearchOperations` hoặc reactive repository và giữ Publisher trong toàn bộ service flow.
2. Xác định timeout transport, timeout server-side và timeout Reactor riêng biệt.
3. Đặt per-attempt timeout cho request.
4. Đặt overall deadline bao quanh retry/fallback chain.
5. Chỉ retry lỗi tạm thời đã phân loại.
6. Dùng backoff, jitter và giới hạn số attempt.
7. Xác nhận write có idempotent hay không trước khi retry.
8. Với bulk, xử lý partial failure theo từng item.
9. Trả Publisher cho framework/caller quản lý; tránh detached subscribe.
10. Cho cancellation truyền về upstream và không coi cancellation là rollback.
11. Dùng doFinally cho cleanup đồng bộ nhẹ, usingWhen cho cleanup bất đồng bộ.
12. Đóng PIT/scroll hoặc resource riêng ở cả complete, error và cancel.
13. Không đóng client/pool do Spring quản lý sau từng request.
14. Kiểm thử timeout, retry, cancellation, cleanup và side effect bằng StepVerifier.
15. Integration test transport/server behavior và theo dõi metric trong production.

## 20. Những điểm cần ghi nhớ

- Timeout có nhiều tầng: connect, connection pool acquisition, response/socket, Elasticsearch search timeout và Reactor timeout.
- `Mono.timeout` phát lỗi timeout và cancel upstream; nó không tự rollback thao tác đã tới Elasticsearch.
- Với `Flux`, timeout giữa các tín hiệu khác với deadline tổng thể.
- Đặt timeout trước retry để giới hạn từng attempt; đặt timeout ngoài cùng để giới hạn toàn operation.
- `retryWhen` resubscribe nguồn Publisher; mọi bước nằm trong retry boundary có thể chạy lại.
- Chỉ retry lỗi tạm thời; mapping, validation và authorization errors cần xử lý nguyên nhân.
- Retry write cần idempotency, ID ổn định hoặc deduplication.
- Bulk response có thể chứa item lỗi mà Publisher vẫn hoàn tất bình thường; cần đọc từng item.
- Cancellation là tín hiệu riêng, không phải error và không phải rollback.
- Không gọi `subscribe()` hoặc `block()` bên trong service/callback reactive.
- `doFinally` phù hợp với cleanup đồng bộ nhẹ trên complete/error/cancel.
- `usingWhen` phù hợp khi resource cần cleanup bất đồng bộ và cleanup phải được compose.
- PIT và scroll cần được đóng; keep-alive giúp giới hạn resource nếu process crash trước cleanup.
- Không đóng reactive client/connection pool do Spring quản lý sau mỗi operation.
- Dùng StepVerifier/virtual time để kiểm thử timeout, retry và cancellation; integration test để xác nhận transport thực tế.
- Theo dõi timeout theo tầng, retry, cancellation, connection pool và resource cleanup.

Timeout, retry, cancellation và cleanup tạo thành một vòng đời thống nhất cho reactive operation. Khi đặt đúng ranh giới retry, giới hạn tổng thời gian, để cancellation truyền qua pipeline và gắn resource với `usingWhen`, ứng dụng Spring Data Elasticsearch có thể xử lý lỗi tạm thời mà vẫn kiểm soát được tải và giải phóng tài nguyên khi công việc kết thúc.
