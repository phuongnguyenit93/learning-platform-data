# Backpressure, lượng yêu cầu dữ liệu và giới hạn khi đi qua giao thức HTTP trong Spring WebFlux

## 1. Vì sao WebFlux cần backpressure?

Một server phản hồi API hoặc phát luồng dữ liệu có thể tạo dữ liệu nhanh hơn tốc độ phía nhận xử lý:

```text
Nguồn dữ liệu                   Người tiêu thụ
20.000 events/giây               300 events/giây
         |                              ^
         v                              |
     [ HÀNG ĐỢI ? ] --------------------+
         |
  Bộ nhớ tăng, trễ tăng, có thể OOM
```

Nếu producer cứ tiếp tục tạo không giới hạn, dữ liệu có thể tích tụ trong heap, buffers của codec, network stack hoặc queue nội bộ; nếu giữ mỗi message trong RAM, ứng dụng có thể hết bộ nhớ. **Backpressure** là khả năng phía nhận bày tỏ **nhu cầu (demand)** để phía gửi sản xuất/phát tiếp một lượng phù hợp.

Trong **Reactive Streams**, tín hiệu trung tâm là `Subscription.request(n)`, trong đó `n` là **số phần tử** downstream sẵn sàng nhận; upstream không được gửi `onNext` vượt quá nhu cầu đã cấp cho subscriber đó. Đây là hợp đồng ở **lớp publisher/subscriber**, không phải lệnh HTTP mà browser tự gửi.

**Spring WebFlux** xây trên reactive programming và I/O không blocking để kết nối request/response bodies với các nguồn `Publisher`. Reactor cung cấp `Flux<T>` (0..N giá trị) và `Mono<T>` (0..1 giá trị) cùng operator điều tiết nhu cầu. Nhưng khả năng backpressure từ đầu tới cuối **chỉ có hiệu lực nếu mọi đoạn của pipeline thực sự tôn trọng tín hiệu hoặc xử lý overload có giới hạn**. Một nguồn dữ liệu ngoài hệ thống liên tục đẩy dữ liệu, một API blocking, hoặc một proxy buffer toàn bộ response có thể phá vỡ kỳ vọng “ít tốn RAM”.

Bài học thuộc **Nền tảng WebFlux**, giới thiệu:

- `Publisher`, `Subscriber`, `Subscription` và `request(n)`.
- Cách demand di chuyển **ngược chiều** với dữ liệu.
- `StepVerifier`/`BaseSubscriber` để điều khiển request và quan sát `doOnRequest`.
- Các operator `limitRate`, `buffer`, `flatMap`, `publishOn`, `onBackpressureBuffer/Drop/Latest/Error`.
- Khác biệt giữa cold source và hot source, xử lý slow consumer và nguồn không hỗ trợ demand.
- **Ranh giới quan trọng:** Reactive Streams demand, HTTP response streaming, TCP receive windows, HTTP/2 flow-control windows, proxy buffering và browser đều là những cơ chế khác nhau.
- Thiết kế API WebFlux NDJSON/SSE, cancel/timeout, tests theo layers và production observability.

Baseline ví dụ: **Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, Project Reactor 3.7.x, Reactor Netty**. Code không sử dụng `spring-boot-starter-web`, không lẫn Servlet MVC và WebFlux.

## 2. Mô hình Reactive Streams: hai hướng thông tin

Reactive Streams định nghĩa những interface chính (thuộc `org.reactivestreams`):

```java
interface Publisher<T> {
    void subscribe(Subscriber<? super T> subscriber);
}

interface Subscriber<T> {
    void onSubscribe(Subscription subscription);
    void onNext(T value);
    void onError(Throwable error);
    void onComplete();
}

interface Subscription {
    void request(long n);
    void cancel();
}
```

Đoạn trên là **rút gọn chữ ký để học**, không phải file Java cần tự khai báo. Những quy tắc quan trọng:

1. Subscriber nhận `onSubscribe(subscription)` trước các signal dữ liệu.
2. Subscriber gọi `request(n)` để cấp **số lượng phần tử** có thể nhận thêm; `n` phải **dương**. `request(0)` hoặc số âm vi phạm hợp đồng và thường gây `onError`.
3. Tổng demand có thể được cộng dồn; không phải mỗi lần `request(n)` tạo một subscription mới.
4. Upstream chỉ gửi `onNext` trong giới hạn demand còn lại; `onError` hoặc `onComplete` kết thúc stream.
5. `cancel()` thông báo không cần thêm dữ liệu; cancel không phải lời hứa hủy ngay một HTTP request/database job đã khởi chạy ngoài hệ thống.
6. Tín hiệu cần được **serialize theo hợp đồng**; thiết kế publisher tùy tiện gọi `onNext` song song từ nhiều thread có thể sai.

Đường đi của dữ liệu và demand đối nghịch:

```text
Publisher / Flux                     Subscriber
      |                                  |
      |<---- onSubscribe/subscription ---| (khái niệm gắn Subscription)
      |<----------- request(3) ---------|
      |------------ onNext(A) --------->|  còn 2
      |------------ onNext(B) --------->|  còn 1
      |------------ onNext(C) --------->|  còn 0
      |                                  | không request thêm:
      |       phải chờ demand mới       | không được gửi onNext D
      |<----------- request(2) ---------|
      |------------ onNext(D) --------->|
      |------------ onNext(E) --------->|
      |----------- onComplete() ------->|
```

**Lưu ý:** `onSubscribe` là signal từ Publisher tới Subscriber; subscriber nhận được `Subscription` rồi mới gọi request. Hình chỉ nhằm diễn tả hai chiều điều khiển/dữ liệu.

### 2.1. “n” là số phần tử, không phải số byte

Với `Flux<Integer>`, `request(3)` cho phép ba số nguyên. Với `Flux<Record>`, mỗi record là một item có thể dài 100 byte hoặc 10 MB. Với `Flux<DataBuffer>`, mỗi item là một bộ đệm bytes, kích thước khác nhau.

Vì vậy:

- `request(10)` **không** cam kết cấp đúng 10 KB.
- `request(1)` **không** đồng nghĩa “chỉ đọc 1 byte từ TCP”.
- Nếu mỗi item rất lớn, backpressure theo item count vẫn có thể gây memory pressure.
- Nếu operator `buffer(1000)` tạo `List<T>`, **một item đầu ra** có thể chứa 1000 item nguồn.
- TCP window tính theo bytes và buffer capacity, không theo số Java objects.

Thiết kế phải đo **element size, queue size, bytes in-flight** và throughput, không chỉ xem demand count.

### 2.2. `Long.MAX_VALUE` là unbounded demand

Nhiều cách subscribe tiện lợi dùng demand gần như không giới hạn:

```java
Flux.range(1, 10).subscribe(System.out::println);
```

Đoạn này là fragment trong Java class có Reactor dependency; nó không phải cách test backpressure từng phần tử vì các overload lambda `subscribe` thường request `Long.MAX_VALUE`. Điều đó thích hợp cho những luồng nhỏ và nhanh nhưng **không chứng minh một consumer production có giới hạn demand**.

`block()`, `blockLast()` cũng tiêu thụ eager/unbounded ở nhiều đường xử lý. Trên Netty event-loop của WebFlux, **không gọi `block()`** để “đợi” kết quả reactive, vì nó có thể chặn luồng I/O và giảm nghiêm trọng throughput hoặc ném exception.

## 3. Ví dụ Java: quan sát demand mà không có HTTP

Muốn học backpressure, trước hết tách HTTP khỏi bài toán để nhìn đúng `request(n)`. Phương pháp ổn định là `StepVerifier` với **initial request bằng 0**.

### 3.1. StepVerifier cấp phát từng lô

```java
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

AtomicInteger produced = new AtomicInteger();

Flux<Integer> source = Flux.range(1, 5)
        .doOnNext(value -> produced.incrementAndGet());

StepVerifier.create(source, 0)
        .expectSubscription()
        .then(() -> {
            if (produced.get() != 0) {
                throw new AssertionError(
                        "Source emitted without demand");
            }
        })
        .thenRequest(2)
        .expectNext(1, 2)
        .thenRequest(3)
        .expectNext(3, 4, 5)
        .verifyComplete();
```

Đây là **fragment Java trong một test method**, cần `reactor-test` trong test dependencies. `StepVerifier.create(source, 0)` có nghĩa **không cấp nhu cầu ban đầu**, *không phải* gọi `Subscription.request(0)` (một thao tác không hợp lệ theo Reactive Streams). Sau `thenRequest(2)`, subscriber nhận đúng hai item; sau `thenRequest(3)` nhận ba item còn lại.

Nếu nguồn tôn trọng demand, trước lần request đầu không có `onNext`. `Flux.range` là cold publisher và tôn trọng pull demand, phù hợp quan sát cơ chế.

### 3.2. BaseSubscriber điều khiển thủ công

```java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

Flux.range(1, 6).subscribe(
    new BaseSubscriber<Integer>() {
        @Override
        protected void hookOnSubscribe(Subscription subscription) {
            request(2);
        }

        @Override
        protected void hookOnNext(Integer value) {
            System.out.println("got=" + value);
            if (value == 2) {
                request(2);
            }
            if (value == 4) {
                cancel();
            }
        }

        @Override
        protected void hookOnCancel() {
            System.out.println("cancelled");
        }
    });
```

Đây là fragment trong method Java có Reactor Core. Với `Flux.range` đồng bộ và không thêm scheduler, các giá trị mong đợi là 1,2,3,4 rồi cancel; các giá trị 5,6 **không được yêu cầu**. Ví dụ có output định hướng:

```text
got=1
got=2
got=3
got=4
cancelled
```

Trong các pipeline dùng nhiều schedulers, đừng dựa vào thứ tự log giữa các threads để suy ra request boundaries khi chưa xác định scheduling và concurrency.

**`cancel()` là tín hiệu hủy đối với Subscription**, không tương đương rollback một giao dịch đã commit hoặc thu hồi một message đã gửi sang Kafka.

## 4. Demand không nhất thiết đi nguyên xi qua operator

Trong thực tế, downstream `request(3)` có thể khiến upstream thấy request **khác 3** vì nhiều operator phải lấy trước dữ liệu, gom nhóm hoặc xử lý nhiều inner publishers.

```text
HTTP writer requests 1 record
       |
       v
map          -> thường theo demand 1:1
       |
buffer(10)   -> cần tới 10 upstream records cho 1 List<Record>
       |
flatMap(...) -> có concurrency và prefetch riêng
       |
publishOn   -> hàng đợi + prefetch, replenishment
       |
Data source receives transformed demand
```

### 4.1. `map` / `filter`

- `map` thường biến đổi một input thành một output nên dễ hiểu demand.
- `filter` có thể bỏ qua item. Để cung cấp đủ **n output hợp lệ** cho downstream, nó có thể cần request **nhiều hơn n source items**.
- `take(n)` giới hạn **tổng item downstream được nhận** và cancel upstream khi đạt số lượng mong muốn (xem overload và version semantics).
- `buffer(k)` gom k source items thành một `List<T>`; demand downstream theo **số list**, không phải số phần tử chứa bên trong.

Ví dụ:

```java
Flux<List<Integer>> windows =
        Flux.range(1, 10).buffer(5);
```

Nếu subscriber request **1**, pipeline có thể cần đọc **5 số** để phát một list `[1,2,3,4,5]`. Đây không phải lỗi backpressure; nó là biến đổi đơn vị demand.

### 4.2. `flatMap` và concurrency

```java
Flux<Result> results = keys
        .flatMap(
            key -> repository.findByKey(key),
            8,   // concurrency: tối đa các inner publishers đồng thời
            16); // prefetch cho inner publishers
```

Đây là **fragment**, giả định `keys` là Flux và repository reactive trả Publisher/Mono phù hợp. `flatMap` có thể yêu cầu dữ liệu từ nhiều inner sequences song song; `concurrency=8` và `prefetch=16` giới hạn những thông số operator, **không** phải giới hạn tổng heap có thể dùng trong cả request.

Không suy ra memory upper bound chính xác chỉ bằng phép nhân 8×16: mỗi item có kích thước khác nhau và còn có queues, codecs, outbound buffers và nguồn ngoài operator. Nếu thứ tự kết quả quan trọng, `concatMap` hoặc `flatMapSequential` với trade-offs tương ứng có thể phù hợp.

### 4.3. `publishOn` tạo ranh giới scheduler và queue

```java
Flux<Data> processed = source
        .publishOn(Schedulers.parallel(), 32)
        .map(this::transform);
```

Fragment giả định `source`, `Data`, `transform` đã có. `publishOn` chuyển downstream processing sang scheduler phù hợp và có `prefetch` nội bộ. Nó có thể phát upstream `request(32)` ban đầu ngay cả khi consumer cuối cùng chỉ đang quan sát một vài items.

**Đừng dùng `publishOn(Schedulers.parallel())` cho blocking JDBC, `Thread.sleep`, file I/O blocking hoặc HTTP client blocking.** Những tác vụ này cần hệ thống non-blocking thật hoặc cô lập bằng `boundedElastic` theo thiết kế.

## 5. `limitRate`: chia nhu cầu lớn thành đợt, không chặn tổng

Một subscriber (bao gồm nhiều thành phần do framework quản lý) có thể request lượng lớn hoặc unbounded. `limitRate(int)` giúp upstream nhìn nhu cầu theo **batches**.

```java
Flux<Integer> limited = Flux.range(1, 100)
        .doOnRequest(n ->
                System.out.println("upstream requested=" + n))
        .limitRate(10);
```

Nếu downstream request 100, upstream sẽ nhận các request theo batch với mức high-tide 10 và cơ chế **75% replenishment** mặc định. Tức **không** nhất thiết logs là mười dòng `request(10)` liên tiếp: khi 75% buffer đã tiêu thụ, operator có thể xin thêm sớm.

Để minh họa strict batch theo low-tide=0:

```java
Flux<Integer> strictBatches = Flux.range(1, 100)
        .doOnRequest(n ->
                System.out.println("requested upstream=" + n))
        .limitRate(10, 0);
```

`limitRate(10, 0)` gửi nhu cầu theo từng lô tối đa 10 trước khi cấp tiếp; vẫn có thể truyền **toàn bộ 100 item** khi downstream tiếp tục request. Nó **không** tương đương `take(10)`, không phải time-based rate limiting kiểu “10 requests per second”, và không phải HTTP rate limiter chặn spam.

### 5.1. Ba khái niệm rất dễ nhầm

| API | Tác dụng chính | Không có nghĩa |
| --- | --- | --- |
| `limitRate(10)` | Chia downstream demand trước khi upstream thấy | Không giới hạn tổng output còn 10 |
| `take(10)` | Lấy tối đa 10 items rồi kết thúc/cancel | Không bảo đảm HTTP 10 bytes/chunks |
| `delayElements(Duration.ofMillis(100))` | Hoãn phát phần tử theo thời gian với scheduler | Không đảm bảo rate limit đối với mọi upstream nóng |
| `timeout(Duration.ofSeconds(5))` | Báo lỗi hoặc fallback nếu thiếu signal đúng hạn | Không khống chế số connection đồng thời |
| `flatMap(mapper,8,16)` | Điều chỉnh inner concurrency/prefetch | Không phải application-wide request quota |

Khi cần rate limiting **requests per client/tenant**, dùng gateway, security/rate limiter hoặc cơ chế server-side có shared state. `limitRate` là operator quản lý demand của reactive sequence, không bảo vệ endpoint công khai khỏi DDoS.

## 6. Cold publisher và hot publisher

### 6.1. Cold source

Một publisher như `Flux.range`, `Flux.defer` hoặc `Mono.fromCallable` thường sản xuất riêng theo mỗi subscription. Cold source có khả năng tuân theo request demand tự nhiên nếu implementation đúng.

```java
Flux<Integer> cold = Flux.range(1, 5)
        .doOnSubscribe(s -> System.out.println("new subscriber"));
```

Hai subscribers thường nhận hai lần phát dữ liệu độc lập. Nếu source là truy vấn R2DBC hoặc reactive HTTP client, subscribe mới có thể khởi tạo I/O mới; cần quan tâm cancellation và connection/resource cleanup.

### 6.2. Hot source

Một sensor, WebSocket incoming stream, Kafka consumer hoặc callback listener có thể có dữ liệu **không phụ thuộc** vào subscriber hiện tại. Nếu không còn downstream demand, producer ngoài hệ thống có thể vẫn phát.

```text
Hot source:  event event event event event ...
Subscriber: request 1 rồi chậm 5 giây
              |
              v
  Phải chọn: buffer có giới hạn, drop, latest,
             báo overflow, giảm tốc upstream ngoài hệ thống,
             hoặc disconnect subscriber
```

`Flux.interval` cũng là ví dụ một nguồn theo clock; nếu subscriber không theo kịp, nó **có thể phát lỗi overflow** thay vì cứ âm thầm xếp hàng vô hạn. Đừng giả định mỗi hot publisher tự buffer tất cả messages.

Một API nguồn ngoài có **pause/resume** hoặc hỗ trợ backpressure (ví dụ demand-aware cursor) thuận tiện hơn nguồn callback chỉ có thể push. Với nguồn không thể làm chậm, cần **chiến lược overflow rõ ràng**.

## 7. Các chiến lược `onBackpressure...`

Reactor cung cấp operators để xử lý những nguồn có áp lực không tương thích với downstream.

| Operator | Khi downstream thiếu demand | Trường hợp phù hợp | Rủi ro |
| --- | --- | --- | --- |
| `onBackpressureBuffer()` | Xếp backlog | Chậm tạm thời | Bản unbounded có thể gây OOM |
| `onBackpressureBuffer(maxSize,...)` | Giữ đến giới hạn, rồi overflow theo overload/strategy | Chấp nhận độ trễ có giới hạn | Cần policy, metrics và error handling |
| `onBackpressureDrop()` | Bỏ giá trị không thể giao ngay | Telemetry có thể mất mẫu | Mất dữ liệu; không dùng cho giao dịch |
| `onBackpressureLatest()` | Giữ giá trị mới nhất thay vì mọi giá trị | Tiến độ %, gauge live | Bỏ qua các trạng thái trung gian |
| `onBackpressureError()` | Báo overflow error | Luồng cần integrity, fail-fast | Client cần retry/recovery |
| `limitRate` | Chia nhu cầu đi ngược lên source có demand support | Cursor/DB paging | Không xử lý nguồn ngoài cứ push bất chấp demand |

### 7.1. Bounded buffer — phải có kế hoạch khi đầy

```java
Flux<Event> buffered = hotEvents
        .onBackpressureBuffer(
            256,
            event -> metrics.recordOverflow());
```

Đây là fragment, `Event`, `hotEvents` và `metrics` do ứng dụng cung cấp. Overload trên có capacity hữu hạn và callback overflow; khi đầy có thể kết thúc với overflow error theo API semantics. **Không dùng buffer unbounded** cho bất kỳ topic hoặc user không giới hạn, nhất là dữ liệu nhạy cảm.

Cần xác định:

- Max backlog theo **items và bytes**.
- Khi đầy thì trả lỗi/disconnect, drop oldest/newest hay coalesce.
- Deadline/TTL cho event quá cũ.
- Ai dọn dữ liệu buffered khi client cancel.
- Metrics về backlog size/age/overflow count.
- Sự khác nhau giữa **global buffer** và buffer **mỗi subscriber**, vì 10.000 subscribers × 256 item có thể rất lớn.

### 7.2. Drop/latest không dùng tùy tiện

```java
Flux<Progress> latestProgress = updates
        .onBackpressureLatest();
```

Thích hợp cho dashboard chỉ quan tâm **% mới nhất**, nhưng không thích hợp cho balance changes, payment events, security audit hoặc dữ liệu mà việc bỏ một message làm thay đổi kết quả.

```java
Flux<Telemetry> sampled = telemetry
        .onBackpressureDrop(value ->
                metrics.incrementDropped());
```

Ví dụ fragment này chấp nhận mất mẫu telemetry. Nếu `Telemetry` phải lưu chính xác mọi điểm, không được drop; thay bằng broker/durable log, giảm nguồn hoặc phân tách ingest/serving.

### 7.3. `onBackpressureError` và HTTP response đã commit

Một `Flux` đang được WebFlux dùng để ghi response có thể gặp `onError` vì overflow. Nếu HTTP headers/body đã bắt đầu được gửi, server **không thể chắc chắn đổi status 200 thành 500** hoặc gửi một JSON error envelope nguyên vẹn. Client có thể thấy stream bị ngắt.

Với SSE cần một protocol/reconnect/replay policy; với NDJSON cần xác định incomplete stream/cancel semantics. Không giả định operator lỗi sẽ tự tạo `HTTP 429`. **429 Too Many Requests** là HTTP rate limiting/application policy khác, cần thiết kế tường minh trước khi commit response.

## 8. Spring WebFlux ghép Reactive Streams với HTTP như thế nào?

Spring WebFlux dùng `HttpHandler`, `WebHandler`, HTTP codecs (`HttpMessageReader`, `HttpMessageWriter`), reactive server adapter và `DataBuffer` để xử lý body theo mô hình non-blocking với backpressure.

```text
Business Flux<Item>
    |
    | demand điều phối qua Reactor Publisher/Subscriber
    v
JSON/SSE encoder
    |
    v
Flux<DataBuffer>
    |
    v
ServerHttpResponse / HttpHandler adapter
    |
    v
Reactor Netty / TCP socket output
    |
    v
HTTP/1.1 chunks hoặc HTTP/2 DATA frames
    |
    v
Browser / WebClient / Gateway
```

Khi mạng chậm, server adapter có thể dùng non-blocking write readiness và buffer watermarks để điều tiết số buffers đọc từ pipeline. Nhưng phải phân biệt:

- **Reactor demand:** số `T` hoặc `DataBuffer` theo `request(n)` trong JVM.
- **Netty buffer/write readiness:** trạng thái event loop, output queue và writable thresholds.
- **TCP flow control:** receive window theo **bytes**; endpoint TCP điều phối stream bytes qua ACK/window updates.
- **HTTP/2 flow control:** connection-level và stream-level windows cho **DATA bytes**, không phải `Flux<Item>` request(n).
- **HTTP/1.1 chunked transfer:** phân đoạn body khi không có Content-Length; chunk boundaries không tương ứng 1:1 với `onNext`.
- **HTTP client application:** trình duyệt đọc/parse payload với tốc độ riêng; JavaScript không nhận `Subscription` từ server qua giao thức HTTP tiêu chuẩn.

Điểm cốt lõi: **không có một HTTP header tiêu chuẩn tương đương “request(3) Java objects”** được trình duyệt gửi sau mỗi ba SSE messages. WebFlux xây cầu nối giữa reactive demand và năng lực ghi/đọc tại HTTP adapter, nhưng mapping có buffer/codec và không phải “một item bằng một TCP packet”.

### 8.1. Ví dụ tốc độ bị giới hạn bởi tầng nào?

Giả sử `Flux` sinh 1000 records/s, browser xử lý 100 records/s:

1. Nếu browser/client không kịp đọc bytes, receive buffers và TCP/HTTP2 windows có thể hạn chế tốc độ truyền.
2. Server write queue có thể không writable, HTTP adapter giảm demand hoặc trì hoãn writes.
3. Một vài items vẫn nằm trong codec/operator prefetch/network buffers.
4. Nếu source cold và demand-aware, cuối cùng nó có thể sản xuất chậm lại.
5. Nếu source hot từ một broker vẫn đẩy không giới hạn, **tầng này vẫn cần queue/drop/pause strategy**.
6. Nếu CDN đọc toàn bộ response thật nhanh rồi buffer cho browser, origin **không còn thấy browser chậm theo cùng cách**.

Do đó phải test **end-to-end** trên topology thật, không chỉ nhìn `doOnRequest` trong controller.

### 8.2. Streaming media types quyết định framing

| Media type | Tổ chức body | Streaming thường kỳ vọng |
| --- | --- | --- |
| `application/json` | Một JSON value/array hoàn chỉnh | Một `Flux<T>` có thể được kết thành array, có thể buffering tùy encoder |
| `application/x-ndjson` | Mỗi dòng một JSON object | Có thể encode từng phần tử và truyền dần |
| `text/event-stream` | Các SSE frames `id/event/data` + dòng trống | Truyền sự kiện theo thời gian, browser EventSource |
| `application/octet-stream` | Raw bytes | Dùng `Flux<DataBuffer>`/Resource ở layer phù hợp |
| `text/plain` | Text bytes; không tự biết message delimiter | Cần định nghĩa framing khi nhiều items |

**Một Flux không tự bảo đảm HTTP response stream hiển thị từng event ngay.** Media type, codec, flush semantics, proxy buffering và client parser đều ảnh hưởng.

Với `application/json`, WebFlux có thể cần tổng hợp dữ liệu cho JSON array; với `application/x-ndjson` hoặc SSE, message writer thường xử lý streaming theo item/event. Nếu cần low latency quan sát được, test actual first byte/first frame arrival.

## 9. NDJSON và SSE: cùng Flux nhưng client khác nhau

### 9.1. NDJSON

```http
HTTP/1.1 200 OK
Content-Type: application/x-ndjson

{"id":1,"name":"item-1"}
{"id":2,"name":"item-2"}
{"id":3,"name":"item-3"}
```

Mỗi dòng là một JSON value hợp lệ. Client có thể parse từng line. Nếu request bị cancel sau dòng thứ hai, stream có thể chỉ chứa hai dòng — protocol cần quyết định **partial result** có được coi là hợp lệ hay không.

### 9.2. Server-Sent Events

```http
HTTP/1.1 200 OK
Content-Type: text/event-stream

id: 1
event: progress
data: {"seq":1,"state":"running"}

id: 2
event: done
data: {"seq":2,"state":"complete"}

```

SSE là giao thức **server → browser** qua HTTP GET. Browser `EventSource` hiểu `data`, `id`, `event`, tự reconnect trong nhiều trường hợp. Nhưng `Last-Event-ID` **không tự tạo durable replay ở server**; khi cần không mất events, phải lưu event log, gắn IDs và xử lý resumption.

**SSE không đồng nghĩa Reactive Streams end-to-end qua browser.** `EventSource` không có API `request(5)` điều khiển trực tiếp upstream Reactor. Browser có thể hủy kết nối (`source.close()`) và network stack cung cấp áp lực theo bytes, nhưng application-level demand không truyền thành Reactive Streams request signal một-một.

### 9.3. Heartbeat

WebFlux docs khuyến nghị gửi dữ liệu/heartbeat định kỳ để phát hiện client đã disconnect sớm hơn, vì một kết nối im lặng không luôn báo cancel tức thì. SSE có thể gửi comment:

```text
: keep-alive

```

Heartbeat cần nhỏ hơn idle timeout của reverse proxy/gateway phù hợp và không được tạo vòng lặp/queue không giới hạn cho mỗi subscriber.

## 10. Ví dụ chạy được: Spring Boot 3.5 WebFlux + Java 17

Demo gồm:

1. `GET /api/items` trả năm items dạng một JSON array.
2. `GET /api/items.ndjson` trả năm items NDJSON và log upstream demand.
3. `GET /api/events` gửi ba SSE events có thứ tự, sau đó complete; client có thể thấy từng event.
4. Không dùng DB, network broker hoặc blocking I/O nên ví dụ giữ scope để quan sát Reactive Streams và HTTP framing.
5. Các tests gồm `StepVerifier` kiểm tra demand không có HTTP và `WebTestClient` qua server thật kiểm tra NDJSON/SSE.

### 10.1. Tạo project

Chọn **Spring Boot 3.5.x**, Java 17, Gradle hoặc Maven, dependency **Spring Reactive Web (WebFlux)**. Với project Boot Gradle plugin/BOM/Java toolchain đã cấu hình, dùng:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Đây là **fragment của `build.gradle`**, không phải toàn bộ file build. `spring-boot-starter-webflux` dùng Reactor Netty mặc định khi ứng dụng chạy reactive stack. **Không thêm `spring-boot-starter-web` chỉ vì muốn dùng `@RestController`**: khi cả MVC và WebFlux starters có mặt, Boot 3.x thường chọn MVC làm web application type mặc định; điều này làm demo khác hoàn toàn mục tiêu.

### 10.2. Toàn bộ Java application

Tạo `src/main/java/demo/backpressure/BackpressureApplication.java`:

```java
package demo.backpressure;

import java.time.Duration;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@SpringBootApplication
public class BackpressureApplication {

    public static void main(String[] args) {
        SpringApplication.run(BackpressureApplication.class, args);
    }
}

record Item(int id, String name) {}

record Progress(long seq, String state) {}

@RestController
@RequestMapping("/api")
class BackpressureController {
    private static final Logger log =
            LoggerFactory.getLogger(BackpressureController.class);

    private Flux<Item> items() {
        return Flux.range(1, 5)
                .map(id -> new Item(id, "item-" + id));
    }

    @GetMapping(
            path = "/items",
            produces = MediaType.APPLICATION_JSON_VALUE)
    Flux<Item> jsonItems() {
        return items();
    }

    @GetMapping(
            path = "/items.ndjson",
            produces = MediaType.APPLICATION_NDJSON_VALUE)
    Flux<Item> ndjsonItems() {
        return items()
                .doOnRequest(n ->
                        log.info("items_upstream_demand={}", n))
                .limitRate(2)
                .doOnCancel(() ->
                        log.info("items_stream_cancelled"));
    }

    @GetMapping(
            path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<ServerSentEvent<Progress>> events() {
        return Flux.range(1, 3)
                .delayElements(Duration.ofMillis(150))
                .map(seq ->
                        ServerSentEvent.<Progress>builder()
                            .id(Integer.toString(seq))
                            .event(seq == 3
                                    ? "done" : "progress")
                            .data(new Progress(seq,
                                    seq == 3
                                        ? "complete" : "running"))
                            .build())
                .doOnCancel(() ->
                        log.info("sse_stream_cancelled"));
    }
}
```

**Mã phù hợp Java 17 + Boot 3.5 WebFlux:** file có một `public` class `BackpressureApplication`; records/controller package-private cùng package, được component scan. `Flux.range` là cold, finite và backpressure-aware. Không có `Thread.sleep` hoặc `block()` trong handler, cũng không tự `subscribe()` bên trong controller; **WebFlux sở hữu subscription** khi ghi HTTP response.

**`limitRate(2)` được áp sau `doOnRequest`**, nên logger phía upstream có thể quan sát requests bị chia lô, thay vì nghĩ một HTTP client đã gửi trực tiếp `request(2)`. Exact request log sequence không nên hardcode, vì low-tide replenishment và codec/server có thể khác.

**SSE demo chỉ ba events** để tests chạy hữu hạn. `delayElements` tạo khoảng cách quan sát được giữa events nhưng không phải rate limiter production cho source hot không hợp tác. Nếu client đóng sớm, `doOnCancel` có thể ghi nhận khi tín hiệu cancel tới subscription. Đừng khẳng định TCP đã đóng thì callback chắc xuất hiện ngay tức khắc khi server không còn ghi thêm.

### 10.3. Chạy curl

```bash
./gradlew bootRun
```

**JSON array:**

```bash
curl -i -H 'Accept: application/json' \
  'http://localhost:8080/api/items'
```

Body dự kiến (không phụ thuộc whitespace):

```json
[
  {"id":1,"name":"item-1"},
  {"id":2,"name":"item-2"},
  {"id":3,"name":"item-3"},
  {"id":4,"name":"item-4"},
  {"id":5,"name":"item-5"}
]
```

**NDJSON:**

```bash
curl -N -i -H 'Accept: application/x-ndjson' \
  'http://localhost:8080/api/items.ndjson'
```

Body dự kiến:

```text
{"id":1,"name":"item-1"}
{"id":2,"name":"item-2"}
{"id":3,"name":"item-3"}
{"id":4,"name":"item-4"}
{"id":5,"name":"item-5"}
```

**SSE:**

```bash
curl -N -i -H 'Accept: text/event-stream' \
  'http://localhost:8080/api/events'
```

Body có dạng:

```text
id:1
event:progress
data:{"seq":1,"state":"running"}

id:2
event:progress
data:{"seq":2,"state":"running"}

id:3
event:done
data:{"seq":3,"state":"complete"}

```

Có thể có dấu cách sau `:` hoặc thứ tự field khác theo encoder. Điều quan trọng là event ID, type, data và dòng trống phân cách. Ví dụ finite nên kết nối đóng sau event thứ ba. Browser EventSource có thể **tự kết nối lại**; client demo muốn dừng phải xử lý event `done` rồi `source.close()`.

`curl -N` tắt buffering của **curl output**, không bắt origin, proxy và CDN bắt buộc flush mỗi phần tử.

## 11. Kiểm thử đúng hai tầng: Reactive Streams và HTTP

### 11.1. Unit test demand bằng StepVerifier

Đoạn test này cô lập Reactor core, xác minh nguồn cold **không phát phần tử khi chưa được cấp demand**, rồi phát đủ từng đợt.

Tạo file `src/test/java/demo/backpressure/BackpressureApplicationTests.java` với class test phía dưới.

### 11.2. HTTP integration test bằng WebTestClient

`WebTestClient` có thể chạy cùng server thực khi `@SpringBootTest(webEnvironment=RANDOM_PORT)`. Nó decode response body theo media type; tests sau xác minh status và item/event contents, **không suy ra trực tiếp request(n) qua TCP**.

```java
package demo.backpressure;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class BackpressureApplicationTests {

    @Autowired
    WebTestClient client;

    @Test
    void coldSourceWaitsForRequests() {
        AtomicInteger produced = new AtomicInteger();

        Flux<Integer> source = Flux.range(1, 5)
                .doOnNext(x -> produced.incrementAndGet());

        StepVerifier.create(source, 0)
                .expectSubscription()
                .then(() -> assertEquals(0, produced.get()))
                .thenRequest(2)
                .expectNext(1, 2)
                .thenRequest(3)
                .expectNext(3, 4, 5)
                .verifyComplete();

        assertEquals(5, produced.get());
    }

    @Test
    void ndjsonStreamsFiveItemsThroughHttp() {
        Flux<Item> body = client.get()
                .uri("/api/items.ndjson")
                .accept(MediaType.APPLICATION_NDJSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_NDJSON)
                .returnResult(Item.class)
                .getResponseBody();

        StepVerifier.create(body)
                .expectNextMatches(item ->
                        item.id() == 1
                                && "item-1".equals(item.name()))
                .expectNextCount(3)
                .expectNextMatches(item ->
                        item.id() == 5
                                && "item-5".equals(item.name()))
                .verifyComplete();
    }

    @Test
    void sseCarriesTypedEventsAndCompletes() {
        Flux<ServerSentEvent<Progress>> body =
                client.get()
                    .uri("/api/events")
                    .accept(MediaType.TEXT_EVENT_STREAM)
                    .exchange()
                    .expectStatus().isOk()
                    .expectHeader().contentTypeCompatibleWith(
                            MediaType.TEXT_EVENT_STREAM)
                    .returnResult(
                        new ParameterizedTypeReference<
                            ServerSentEvent<Progress>>() {})
                    .getResponseBody();

        StepVerifier.create(body)
                .expectNextMatches(event ->
                        "progress".equals(event.event())
                            && "1".equals(event.id())
                            && event.data() != null
                            && event.data().seq() == 1)
                .expectNextMatches(event ->
                        "progress".equals(event.event())
                            && "2".equals(event.id())
                            && event.data() != null
                            && event.data().seq() == 2)
                .expectNextMatches(event ->
                        "done".equals(event.event())
                            && "3".equals(event.id())
                            && event.data() != null
                            && "complete".equals(
                                    event.data().state()))
                .verifyComplete();
    }
}
```

Chạy:

```bash
./gradlew test
```

Ba tests được **thiết kế để pass** trên Boot 3.5 WebFlux/Java17 với source ở phần 10. Đây là **kỳ vọng qua kiểm tra mã và tài liệu**, **không phải log thực thi Gradle**. Test dùng WebTestClient qua **RANDOM_PORT** để HTTP codec và Reactor Netty cùng tham gia; khác với mock bindToController tests.

**Điểm cần nhớ:** test `coldSourceWaitsForRequests` trực tiếp chứng minh demand của Reactive Streams. Hai HTTP tests chứng minh serialization/framing/event contents. Chúng **không thể xác nhận “HTTP client gửi `request(5)` đến server”**, vì wire protocol không có signal đó.

## 12. Quan sát request(n) trong pipeline, đúng chỗ và đúng mục tiêu

`doOnRequest` ghi lại demand đi qua một vị trí cụ thể:

```java
Flux<Integer> observable = Flux.range(1, 100)
        .doOnRequest(n ->
                log.debug("upstream_request_count={}", n))
        .publishOn(Schedulers.parallel(), 16)
        .filter(n -> n % 2 == 0)
        .limitRate(4);
```

Một client cuối cùng request 4 giá trị **không bắt buộc** log upstream `request(4)`. `publishOn` có prefetch 16; `filter` cần bỏ item lẻ; `limitRate` bổ sung batch logic.

Nếu chuyển `doOnRequest` sang **sau** `publishOn`, số request được log có thể khác. Vì thế khi debug:

- Đặt `doOnRequest` ở hai đầu của operator nghi ngờ, gắn tên stage cụ thể.
- Dùng `doOnNext`, `doOnCancel`, `doFinally` để quan sát terminal/cleanup signals.
- Nếu cần debug tín hiệu ở mức chi tiết, dùng Reactor `log()` có kiểm soát trong dev/test; không bật log mọi item ở production traffic cao.
- Đừng ghi raw payload, auth tokens hoặc PII vào telemetry.
- Theo dõi **queue size và bytes**, không chỉ `request(n)` count.
- Dùng Reactor metrics/Micrometer hoặc OpenTelemetry theo cấu hình Boot đang dùng; operator labels phải có cardinality thấp.

### `doOnRequest` có thể nhận `Long.MAX_VALUE` mà hệ thống vẫn vận hành hợp lý

Downstream của nhiều operator/framework có thể request unbounded và nội bộ dùng write readiness/queues. Điều đó không đủ chứng minh cả ứng dụng không có backpressure; cần xem toàn chuỗi, khả năng buffering và protocol adapter. Ngược lại, log request(1) cũng không chứng minh client thật đã xử lý xong item trước đó.

## 13. Backpressure và request body uploads

Backpressure không chỉ dành cho **response**. Khi WebFlux nhận HTTP request body, adapter/`HttpMessageReader` có thể cung cấp `Flux<DataBuffer>` hoặc decode thành publisher:

```text
Client POST streamed body
    |
    v
TCP receive buffer / HTTP/2 flow-control
    |
    v
Reactor Netty inbound byte buffers
    |
    v
Flux<DataBuffer> -> HttpMessageReader/Decoder
    |
    v
Application processing & bounded storage
```

Nhưng có ranh giới:

- Nếu controller gọi `bodyToMono(String.class)` hoặc `@RequestBody Mono<LargeObject>`, decoder có thể **tích lũy dữ liệu** để tạo một object.
- `spring.codec.max-in-memory-size` giới hạn bộ nhớ cho nhiều codec khi phải buffer/aggregate; **không phải total HTTP upload cap** cho mọi dạng stream/file.
- `multipart/form-data` có rules/limits riêng (số parts, disk usage, file handling), xem docs chính xác theo Spring version.
- Trực tiếp tiêu thụ `DataBuffer` cần quản lý lifecycle; với pooled Netty buffers, phải **release** đúng khi tự giữ/discard chúng. Nếu dùng standard codecs, framework thường xử lý việc quản lý buffers.
- Đừng chuyển mọi incoming body thành `collectList()` hoặc `DataBufferUtils.join(...)` không giới hạn; có thể mất lợi ích streaming và gây OOM.
- Kiểm tra kích thước request tại **gateway, web server, decoder và nghiệp vụ**, áp quota/rate limits và auth.
- `Flux<DataBuffer>` chỉ thể hiện buffer chunks; một multipart upload có thể chứa file rất lớn dù chỉ từng chunk nhỏ.

Ví dụ property giới hạn các codec phải aggregate:

```properties
spring.codec.max-in-memory-size=256KB
```

**Không kết luận request 10 GB đã an toàn** chỉ vì mỗi codec limit 256 KB: nếu pipeline stream file tới disk/object store, total bytes/quota/cancellation/storage limits vẫn cần kiểm soát riêng.

## 14. Blocking I/O trong WebFlux phá vỡ lợi ích của demand-aware pipeline

Một handler WebFlux sai kiểu:

```java
@GetMapping("/report")
Mono<Report> report() {
    Report report = blockingJdbcDao.load(); // Chạy ngay trên event loop.
    return Mono.just(report);
}
```

Đây là **anti-pattern fragment**, giả định `blockingJdbcDao` trả Report. Spring WebFlux event-loop có ít threads; blocking JDBC hoặc `Thread.sleep` có thể giữ thread quá lâu, ảnh hưởng mọi request khác.

Nếu vẫn buộc dùng thư viện blocking trong giai đoạn migration:

```java
@GetMapping("/report")
Mono<Report> report() {
    return Mono.fromCallable(() -> blockingJdbcDao.load())
            .subscribeOn(Schedulers.boundedElastic());
}
```

Đây là **fragment** cần Reactor `Mono`, `Schedulers`, và service/record `Report`. `boundedElastic` cô lập blocking operation khỏi Netty event loop theo một pool có giới hạn; **không biến JDBC thành non-blocking** và không giải quyết không giới hạn connection pool, timeout, queue hoặc thread count.

Khuyến nghị:

- Dùng R2DBC/reactive database driver nếu cần backpressure ở database read path.
- Dùng `WebClient` thay blocking HTTP client khi pipeline cần async/non-blocking.
- Với cursor/query, kiểm tra driver có thật sự tôn trọng demand và có resource lifecycle.
- Cấu hình DB pool, HTTP outbound concurrency và global rate limits bên cạnh Reactor prefetch.
- Tránh `block()`, `toIterable()`, đồng bộ locks hoặc CPU-heavy loops trên Netty event loop.
- Với CPU-heavy work, scheduler `parallel` hoặc dedicated executor theo measurements; không tùy tiện `subscribeOn`/`publishOn` khắp nơi.

## 15. HTTP/1.1, HTTP/2 và HTTP/3: giới hạn nào là vật lý, giới hạn nào là API?

### 15.1. HTTP/1.1

- Một response stream có thể đi qua chunked transfer khi không có Content-Length; container quyết định framing.
- TCP điều khiển truyền **bytes**, không biết `Flux<Item>` hoặc `ServerSentEvent<T>`.
- Một HTTP/1.1 connection thường có hạn chế multiplexing so với HTTP/2; nhiều SSE connections có thể tốn browser/network resources.
- HTTP clients/proxies có thể buffer, decompress và parse theo cách riêng.
- “`onNext(item)` được gọi” không khẳng định ngay lúc đó client đã nhận đầy đủ item.

### 15.2. HTTP/2

HTTP/2 có **stream-level và connection-level flow control** bằng windows và `WINDOW_UPDATE` cho DATA frames. Đây là cơ chế byte-oriented, độc lập với `Subscription.request(n)` của Reactor. HTTP/2 còn có multiplexing: một connection có nhiều streams; một stream chậm không đồng nghĩa publisher khác có cùng demand pattern.

Mối liên hệ có thể gián tiếp: HTTP/2 send window nhỏ → outbound write bị hạn chế → adapter cần hạn chế đọc thêm data buffers → demand trong reactive pipeline được điều tiết. Nhưng không phải công thức `request(n) = HTTP2 WINDOW_UPDATE(n)`.

### 15.3. HTTP/3/QUIC

HTTP/3 dựa trên QUIC, có stream/connection flow control theo bytes và cơ chế truyền khác TCP, nhưng nguyên lý “giao thức mạng không gửi Reactor `request(n)`” vẫn không đổi. Với WebFlux chạy sau HTTP/3 terminating reverse proxy, HTTP/3 có thể chỉ tồn tại giữa browser và gateway, còn origin dùng HTTP/1.1 hoặc HTTP/2; hãy đo actual deployment.

### 15.4. Các loại giới hạn khác

- **Content-Length**: kích thước body được tuyên bố/biết trước, không phải Reactive Streams demand.
- **Max request size/codec max buffer**: ngưỡng bảo vệ payload/memory, không phải số item consumer sẽ request.
- **Rate limit**: requests hoặc tokens/bytes theo thời gian/user, không phải operator `limitRate`.
- **Timeout**: thời gian phản hồi/idle, không trực tiếp kiểm soát queue bytes.
- **Concurrency cap**: số tasks/connections/subscribers được phép, khác với item prefetch.
- **Backpressure**: nhu cầu flow-controlled giữa các reactive stages, có thể làm chậm upstream phù hợp.

## 16. Proxy/CDN có thể che đi slow consumer

Giả sử client thực đọc chậm nhưng NGINX có response buffering:

```text
WebFlux origin  -->  Proxy buffer RAM/disk  -->  Browser slow
    nhanh                   tích tụ                  chậm

Origin đã gửi xong rất nhanh
=> demand ở origin KHÔNG nhất thiết phản ánh browser đang xử lý chậm
```

Điều này có thể đúng ngay cả khi application Reactor pipeline viết rất “đúng backpressure”. Những tầng cần kiểm tra:

- Reverse proxy `proxy_buffering` / `proxy_request_buffering`, response compression.
- CDN edge caching, transformation, WAF buffering.
- GZIP/Brotli chunk flush policy.
- HTTP/2 → HTTP/1.1 gateway translation.
- Keep-alive, read/write/idle timeout và maximum connections.
- Browser EventSource/client buffering/console output.
- Network latency, packet loss và TCP flow control.

Với streaming latency-sensitive routes, cấu hình proxy phù hợp, ví dụ NGINX có thể tôn trọng:

```http
X-Accel-Buffering: no
Cache-Control: no-cache
Content-Type: text/event-stream
```

`X-Accel-Buffering` là NGINX-specific hint, **không phải bảo đảm tiêu chuẩn HTTP**; proxy phải được cấu hình để honor. Không tắt buffering toàn bộ website vô điều kiện.

Test cả **localhost**, **embedded Reactor Netty**, **gateway staging** và nếu cần **browser thật**; đo time-to-first-event, queue growth và disconnect detection.

## 17. Cancellation, timeout, errors và việc client đóng kết nối

Một consumer có thể dừng bằng `cancel()` (như `take(3)` hoặc StepVerifier cancel). Client HTTP có thể disconnect giữa stream. Nhưng cancel propagation qua codec, adapter, scheduler và driver **không luôn tức thời**.

```java
Flux<Data> stream = source
        .doOnCancel(() ->
                metrics.incrementCancelled())
        .doFinally(signal ->
                metrics.recordTerminal(signal));
```

Đây là fragment. `doFinally` nhận `SignalType` (gồm complete, error hoặc cancel) và phù hợp để theo dõi terminal lifecycle; callback không thay transaction cancellation ở nguồn ngoài.

Khi nguồn là database cursor, file reader hoặc broker subscription, cancellation nên dẫn tới cleanup:

- Đóng/release DB cursor, reactive connection hoặc pooled resource.
- Hủy timer/subscription/producer work không cần thiết.
- Dọn per-client buffers và queue.
- Giới hạn thời gian network requests và external service calls.
- Gắn cancellation với user disconnect ở adapter đúng chỗ.
- Không giữ `DataBuffer` pooled vượt lifecycle nếu chưa retain/release đúng.

### 17.1. Lỗi sau khi response đã bắt đầu

Nếu WebFlux đã gửi header `HTTP 200` và vài NDJSON/SSE items, sau đó upstream `onError`, server có thể **không đổi** response thành một `500 application/problem+json` hợp lệ. Client có thể nhận incomplete stream hoặc connection reset.

Giải pháp phụ thuộc protocol: phát SSE event `error` trong phạm vi stream còn writable, cung cấp event IDs/replay, đặt checksum/end marker cho batch data, hoặc cho client retry/idempotency.

**`onErrorResume` không tự biến mọi stream error thành HTTP 500**; nó chỉ thay Publisher bằng một fallback theo logic Reactor. Nếu fallback object không đúng schema/framing, client có thể đọc sai; nếu lỗi bảo mật, không trả stack trace.

### 17.2. Timeout không thay được overload control

`timeout(Duration)` có thể chấm dứt flow khi thiếu tín hiệu. Nhưng request concurrency, pending upstream calls và buffer memory vẫn cần điều chỉnh. Khi trả timeout/retry, cần tránh tạo **retry storm**.

Không dùng `retry()` vô hạn cho database, gateway hoặc nguồn hot mà không có backoff, jitter, attempt limit và idempotency policy.

## 18. Backpressure phía client dùng WebClient

WebClient trong WebFlux cũng là reactive HTTP client; nếu response body là NDJSON/SSE có thể decode thành `Flux<T>`:

```java
WebClient client = WebClient.create(
        "https://api.example.org");

Flux<Item> items = client.get()
        .uri("/api/items.ndjson")
        .accept(MediaType.APPLICATION_NDJSON)
        .retrieve()
        .bodyToFlux(Item.class)
        .limitRate(8);
```

Đây là **fragment**, cần imports WebClient/Reactor/MediaType và `Item` DTO. Chưa subscribe nên phần lớn pipeline chưa phát HTTP request. `limitRate(8)` điều chỉnh demand Reactor phía client; nó **không gửi HTTP message `request(8)` tới origin**. Network/backpressure bridge có thể giảm lượng bytes được đọc/đệm, nhưng không có contract “đúng tám network objects in-flight”.

Nếu client gọi:

```java
List<Item> all = client.get()
        .uri("/api/items.ndjson")
        .retrieve()
        .bodyToFlux(Item.class)
        .collectList()
        .block();
```

thì sẽ **thu toàn bộ kết quả** vào list (và block thread). Với nguồn dài hoặc vô hạn, đây là anti-pattern gây memory pressure và có thể không bao giờ hoàn tất. Trong WebFlux request thread/event-loop, dùng reactive composition thay vì `block()`.

### WebClient filters, timeouts và connection pooling

- Giới hạn connection pool, pending acquires, response timeout và max in-memory codec buffering.
- Dùng `flatMap(..., concurrency)` để giới hạn số HTTP requests đồng thời.
- Có circuit breaker/bulkhead phù hợp, không chỉ `limitRate`.
- Với retry, kiểm soát idempotency và thundering herd.
- Nếu nhận stream rất dài, đừng dùng `bodyToMono(byte[].class)` để aggregate toàn bộ.
- Đảm bảo response body bị consume hoặc hủy đúng để connection có thể được giải phóng/reuse.

## 19. Đo backpressure đúng trong production

Các chỉ số cần quan sát:

| Metric | Tại sao hữu ích |
| --- | --- |
| Active connections/streams | Phát hiện kết nối kéo dài hoặc leak |
| Inbound/outbound bytes/s | Tốc độ thực của HTTP/network |
| Queue depth **và bytes** | Đo backlog; bytes quan trọng vì item sizes khác nhau |
| Oldest queued item age | Phát hiện dữ liệu đến client đã quá cũ |
| Time-to-first-byte / first-event | Trực tiếp đo streaming UX |
| End-to-end event latency | So sánh lúc tạo và lúc client nhận |
| HTTP write/flush stalls | Phát hiện chậm từ socket/gateway |
| Dropped/latest/overflow count | Biết loss policy đang xảy ra |
| Subscription cancel/error/complete | Phân biệt dừng hợp lệ và sự cố |
| Reactor scheduler pending tasks | Phát hiện scheduling bottleneck |
| DB/outbound pool utilization | Đo upstream có thực sự giảm tải hay không |
| Gateway/edge buffer occupancy | Xác định chỗ nguồn và browser bị tách rời |
| HTTP client consumption latency | Không suy ra UX chỉ từ producer send timestamps |

`doOnRequest` hữu ích cho debug trong giới hạn nhưng **request count không trực tiếp là throughput network**. Tránh gắn từng event payload/PII vào metrics tags; cardinality cao làm observability system bùng nổ.

### 19.1. Thiết kế load test slow consumers

Một test nghiêm túc nên:

1. Tạo 100/1000 concurrent clients trong môi trường kiểm soát.
2. Dùng HTTP client đọc **từng phần**, có client đọc chậm hoặc tạm ngưng đọc.
3. Quan sát heap, direct memory, Netty pending writes, queue depth, GC và CPU.
4. Đo origin so với gateway và client timestamps.
5. Test source cold và hot riêng.
6. Thử buffer policy, drop/latest/error, subscriber limits.
7. Test client disconnect sớm, server cancel và cleanup.
8. Thử cấu hình HTTP/1.1 vs HTTP/2 qua cùng topology.
9. Tăng payload size từng item, không chỉ số item.
10. Kiểm tra retry storm khi overload/circuit breaker hoạt động.

Không dùng `Thread.sleep` trên WebFlux event loop để giả lập slow consumers. Test harness phía client có thể đọc chậm với thread có giới hạn hoặc dùng virtual-time tests cho riêng Reactor logic.

## 20. Những hiểu lầm thường gặp

| Nhận định sai | Điều đúng |
| --- | --- |
| “`Flux` nghĩa là mọi response tự stream ngay.” | Phụ thuộc encoder, media type, flush và proxy |
| “`request(3)` gửi một HTTP command tới browser.” | Signal nội bộ Reactive Streams, không phải wire HTTP |
| “`request(3)` tương ứng 3 KB.” | Theo số **items**, kích thước mỗi item khác nhau |
| “`limitRate(10)` giới hạn 10 request/giây.” | Chia demand thành batches, không phải rate limiter |
| “`take(10)` và `limitRate(10)` giống nhau.” | Take giới hạn tổng items, limitRate chia nhu cầu |
| “Downstream request 1 nên upstream cũng luôn request 1.” | Buffer/filter/flatMap/publishOn/prefetch thay đổi demand |
| “`onBackpressureBuffer()` giải quyết overload mãi mãi.” | Buffer unbounded có thể gây OOM |
| “`onBackpressureDrop` luôn vô hại.” | Không hợp dữ liệu phải giao đủ như thanh toán |
| “Source hot tự chậm lại khi subscriber không request.” | Nguồn ngoài có thể tiếp tục phát; cần policy |
| “SSE EventSource có `request(n)`.” | Browser EventSource không implement Reactive Streams |
| “HTTP/2 WINDOW_UPDATE là request(n).” | Windows theo bytes, không theo objects |
| “TCP chậm sẽ làm origin chậm ngay.” | Proxy/CDN có thể buffer và decouple |
| “`subscribe()` lúc nào cũng đòi 1 item.” | Nhiều overload request `Long.MAX_VALUE` |
| “Reactive = tự động non-blocking dù gọi JDBC.” | Blocking library vẫn block thread |
| “`collectList()` cho stream vô hạn là an toàn.” | Có thể tăng RAM vô hạn và không hoàn tất |
| “Controller trả Flux sẽ chống DDoS.” | Cần auth, quotas, concurrency/request-rate limits |
| “Client đóng tab thì doOnCancel ngay.” | Phụ thuộc write/heartbeat/network detection |
| “onError lúc stream đã bắt đầu sẽ thay status 200.” | Response có thể committed, cần protocol-level handling |

## 21. Checklist khi phát triển WebFlux streaming

- [ ] Xác định chính xác đơn vị demand: `T`, `List<T>` hay `DataBuffer`.
- [ ] Pipeline nguồn thật sự demand-aware; nếu hot source, có overflow policy.
- [ ] Không có buffer/collectList unbounded trên stream dài.
- [ ] Các operator `flatMap/publishOn` có concurrency/prefetch phù hợp.
- [ ] Không dùng `limitRate` như API request rate limiter.
- [ ] Không có blocking I/O/`block()` trên Reactor Netty event loops.
- [ ] Media type `application/x-ndjson` hoặc `text/event-stream` được chọn đúng contract.
- [ ] Client parse đúng framing và hỗ trợ partial stream/cancel.
- [ ] HTTP codec buffer limits, request sizes, queue bytes được kiểm soát.
- [ ] Netty connection pools và outbound HTTP concurrency có upper bounds.
- [ ] Hot SSE có heartbeat, Last-Event-ID replay nếu cần, connection/tenant limits.
- [ ] `doOnCancel`/`doFinally` cleanup DB cursors, subscriptions, timers, pooled buffers.
- [ ] Lỗi sau committed response có xử lý retry/protocol rõ.
- [ ] Proxy/CDN/ingress được kiểm tra về buffering và timeouts.
- [ ] Unit StepVerifier kiểm tra demand từ 0; HTTP WebTestClient kiểm tra framing.
- [ ] Có load test slow consumers cùng direct-memory/queue metrics.
- [ ] Không đưa tokens, payloads hoặc user IDs tùy ý vào logs/metrics tags.
- [ ] Khi nâng Spring/Boot/Reactor, kiểm tra operator prefetch defaults, codecs và server adapter behavior.

## 22. Bài tập tự đánh giá

1. `request(5)` có nghĩa yêu cầu 5 bytes, 5 HTTP chunks hay 5 Reactor elements? Nếu element là `List<Order>` thì sao?
2. Tạo `StepVerifier.create(Flux.range(1,5),0)` rồi `thenRequest(2)`. Vì sao initial request 0 trong test **khác** gọi `Subscription.request(0)`?
3. Đặt `doOnRequest` trước và sau `limitRate(4)`. Dự đoán logs khác nhau khi downstream request 100.
4. So sánh `limitRate(10)` với `limitRate(10,0)`, đặc biệt low-tide replenishment.
5. Với `Flux.range(1,100).buffer(10)`, subscriber request 2 có thể làm source nhận demand bao nhiêu?
6. Vì sao `flatMap(mapper,8,16)` không đặt được hard byte memory limit cho mọi request?
7. Trình bày cách `onBackpressureLatest` làm mất intermediate progress events nhưng vẫn có thể đúng với dashboard percent.
8. Tại sao không dùng `onBackpressureDrop` cho order payments hoặc security audit events?
9. Giả sử upstream publish từ Kafka liên tục 50k msg/s, client SSE nhận 100/s. Bạn chọn pause, bounded buffer, durable broker hay disconnect? Giải thích semantics mất dữ liệu.
10. Cùng `Flux<Item>` nhưng `application/json` và `application/x-ndjson` có thể khác hành vi phát dữ liệu như thế nào?
11. Browser `EventSource` có thể gửi `request(2)` không? Nếu không, backpressure HTTP còn hoạt động bằng các cơ chế nào?
12. HTTP/2 stream window và TCP receive window dùng đơn vị gì? Vì sao không tương đương Reactor element demand?
13. NGINX đọc origin nhanh nhưng buffer response cho browser chậm. Producer `doOnRequest` ở origin còn phản ánh chính xác browser latency không?
14. Nếu `Flux<DataBuffer>` có 1 item 50 MB, `request(1)` có an toàn về memory không? Thiết kế giới hạn kích thước chunk/buffer.
15. Thêm `onBackpressureBuffer(100)` cho hot events. Khi buffer đầy thì policy nào có thể áp? Cần quan sát metric nào?
16. Thay DB access trong WebFlux bằng blocking JDBC trực tiếp. Nó ảnh hưởng Reactor Netty event loops ra sao? `boundedElastic` khắc phục được những gì và không khắc phục được gì?
17. Với `WebClient.bodyToFlux(Item.class)`, nếu đổi thành `collectList().block()` cho infinite stream, lỗi thiết kế là gì?
18. Client ngắt sau 2/5 NDJSON records; server đã trả status 200. Làm sao client phát hiện partial result và retry an toàn?
19. Thiết kế test `StepVerifier` đo demand trực tiếp, test `WebTestClient` kiểm tra SSE fields và load test qua proxy đo first-event latency; phân biệt ba mục tiêu.
20. Trong rolling deployment, browser reconnect SSE với `Last-Event-ID` sang node khác. Vì sao cần shared durable event log nếu không được mất events?
21. Đưa một source hot vào `publishOn` với prefetch 32; nếu client không request thì buffers/overflow có thể hình thành ở những đâu?
22. Xây rate-limit HTTP theo tenant và overflow policy cho stream data; giải thích vì sao không thể chỉ dùng một `limitRate(10)`.

## 23. Tài liệu chính thức

- [Reactive Streams Specification — JVM](https://www.reactive-streams.org/): nguyên tắc `Publisher`/`Subscriber`/`Subscription` và `request(n)` contract.
- [Project Reactor Reference — Backpressure and Ways to Reshape Requests](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html#_on_backpressure_and_ways_to_reshape_requests): demand, BaseSubscriber, prefetch, limitRate.
- [Project Reactor — Flux Javadoc](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): `limitRate`, `flatMap`, `publishOn`, `onBackpressureBuffer/Drop/Latest/Error`.
- [Project Reactor — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): initial request, thenRequest, deterministic signal testing.
- [Spring Framework — WebFlux Reactive Core](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): `HttpHandler`, codecs, non-blocking I/O, Reactive Streams backpressure và `DataBuffer`.
- [Spring Framework — WebFlux Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods.html): reactive controller return values.
- [Spring Framework — WebFlux Reactive Libraries](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-libraries.html): reactive adaptation, cancellation và request signals.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): test HTTP streaming/response bodies.
- [Spring Boot 3.5 — Embedded Web Servers](https://docs.spring.io/spring-boot/3.5/how-to/webserver.html): reactive server mặc định Reactor Netty.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): RANDOM_PORT, WebTestClient, WebFlux test configuration.
- [Spring Boot 3.5 — Common Application Properties](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html): `spring.codec.max-in-memory-size`.
- [RFC 9113 — HTTP/2](https://www.rfc-editor.org/rfc/rfc9113.html): stream/connection byte-oriented flow control.
- [RFC 9293 — Transmission Control Protocol](https://www.rfc-editor.org/rfc/rfc9293.html): TCP receiver windows và byte stream semantics.
- [WHATWG HTML — Server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html): SSE/EventSource protocol/reconnect.
