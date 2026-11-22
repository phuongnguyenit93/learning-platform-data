# Phân biệt phương thức trả về reactive với công việc thực sự không chặn

## 1. Một kiểu trả về reactive không chứng minh công việc bên trong là non-blocking

Một controller có thể khai báo:

~~~java
@GetMapping("/products/{id}")
public Mono<Product> find(@PathVariable String id) {
    return Mono.just(repository.findById(id));
}
~~~

Nhìn chữ ký, phương thức trả về **Mono<Product>** nên có vẻ reactive. Nhưng nếu repository dùng JDBC hoặc một thư viện đồng bộ, lời gọi **repository.findById(id)** đã chạy ngay khi Java thực thi phương thức. Thread hiện tại phải đợi database trả kết quả **trước khi Mono.just(...) được tạo xong và trả về**.

Đây là điểm cốt lõi:

> **Reactive return type mô tả cách biểu diễn và kết hợp tín hiệu. Non-blocking mô tả cách công việc thực sự chờ đợi và sử dụng thread. Hai điều này liên quan nhưng không đồng nghĩa.**

Một Mono/Flux có thể:

- Phát dữ liệu đồng bộ ngay trên thread đang subscribe.
- Trì hoãn một lời gọi blocking tới lúc subscribe, nhưng vẫn chạy lời gọi đó trên thread subscribe.
- Bọc một Future đang chạy trên thread pool; caller không chờ trực tiếp, nhưng công việc bên trong có thể vẫn blocking một worker khác.
- Dùng API I/O bất đồng bộ để đăng ký callback, trả quyền điều khiển thread trong lúc chờ I/O và phát tín hiệu khi có kết quả.

Vì vậy, chỉ nhìn kiểu **Mono<T>** hoặc **Flux<T>** không đủ để kết luận request WebFlux sẽ không block event loop.

## 2. Phân biệt bốn khái niệm thường bị dùng lẫn

### 2.1. Reactive

**Reactive** là cách mô tả dữ liệu và hành vi qua Publisher/Subscriber, tín hiệu onNext/onError/onComplete, operator để biến đổi/kết hợp và cơ chế demand/backpressure của Reactive Streams.

Trong Reactor:

- **Mono<T>** biểu diễn 0 hoặc 1 giá trị.
- **Flux<T>** biểu diễn 0 đến nhiều giá trị.
- Các operator như map, filter, flatMap, timeout, retryWhen giúp xây dựng pipeline.

Reactive API giúp mô tả một luồng công việc và phối hợp kết quả. Nó không bắt buộc mọi phép tính trong pipeline đều chạy bất đồng bộ hoặc trên thread riêng.

### 2.2. Asynchronous (bất đồng bộ)

Một thao tác bất đồng bộ cho phép caller tiếp tục công việc khác trong khi kết quả sẽ được thông báo sau, thường qua callback, Future hoặc Publisher.

Tuy nhiên, **asynchronous không tự động có nghĩa non-blocking ở mọi tầng**. Ví dụ:

~~~java
CompletableFuture<Product> future =
        CompletableFuture.supplyAsync(() -> blockingRepository.find(id));
~~~

Caller nhận Future ngay, nhưng một worker của Executor vẫn phải chờ trong blockingRepository.find(id). Đây là cách tách thời gian chờ khỏi caller, không phải biến JDBC thành I/O non-blocking.

### 2.3. Non-blocking

Một thao tác **non-blocking I/O** không giữ một thread chờ đồng bộ cho đến khi socket/database sẵn sàng. Runtime đăng ký sự kiện/hoàn tất I/O và tiếp tục xử lý công việc khác; khi dữ liệu sẵn sàng, callback hoặc tín hiệu reactive được phát.

Mục tiêu trong WebFlux là không chiếm các thread event-loop ít ỏi chỉ để đợi network I/O hoặc database I/O.

### 2.4. Synchronous không nhất thiết là blocking I/O

Một phép tính CPU như:

~~~java
int result = price * quantity;
~~~

được thực thi đồng bộ trên thread hiện tại, nhưng không phải thao tác chờ I/O. Nó vẫn sử dụng CPU và giữ thread trong thời gian tính toán, nhưng không ngủ/chờ socket hay database.

Cần phân biệt:

- **Synchronous CPU work:** chạy ngay trên thread hiện tại; có thể tốn CPU nhưng không chờ I/O.
- **Blocking I/O:** thread bị giữ lại chờ một thao tác bên ngoài.
- **Asynchronous work:** kết quả đến sau qua cơ chế hoàn tất; underlying task có thể non-blocking hoặc vẫn blocking trên worker khác.
- **Reactive composition:** mô tả cách kết hợp Publisher; bản thân nó không chứng nhận loại I/O.

## 3. Vì sao Mono/Flux có thể chứa công việc blocking?

Reactor không thể tự biết mọi lệnh Java bên trong lambda là JDBC, file I/O, socket blocking, tính toán CPU hay API callback. Một Publisher có thể được tạo từ bất kỳ đoạn Java nào.

Ví dụ:

~~~java
Mono<Product> product = Mono.fromCallable(
        () -> jdbcRepository.findById("P01")
);
~~~

**fromCallable** làm lời gọi được trì hoãn cho tới khi có subscription. Nhưng nếu không chỉ định Scheduler, Callable đồng bộ thường được thực thi trong ngữ cảnh yêu cầu/subscription. Nếu request đang được xử lý trên event-loop của WebFlux, lời gọi JDBC vẫn có thể chặn event-loop.

Tương tự:

~~~java
Mono<String> result = remoteClient.fetch()
        .map(response -> legacyBlockingParser.parse(response));
~~~

Nếu remoteClient.fetch() là Publisher non-blocking nhưng **legacyBlockingParser.parse(...)** thực hiện I/O blocking, map sẽ chạy hàm đó đồng bộ trên thread đang phát onNext. Phần nguồn non-blocking không bảo vệ các bước downstream khỏi blocking.

**Kiểu trả về reactive là hợp đồng tín hiệu; tính non-blocking phụ thuộc vào từng thao tác thực thi và nơi thao tác đó chạy.**

## 4. Thời điểm thực thi: Mono.just, fromCallable, defer và Future

Một nguồn reactive thường được mô tả là lazy, nhưng không phải mọi biểu thức Java dùng để tạo nguồn đều lazy. Cần xác định công việc được gọi **lúc dựng Publisher** hay **lúc subscribe**.

### 4.1. Mono.just(expression): expression được đánh giá ngay

~~~java
Mono<Product> wrong = Mono.just(
        jdbcRepository.findById(id)
);
~~~

Java đánh giá tham số trước khi gọi Mono.just. Vì vậy:

1. Gọi jdbcRepository.findById(id).
2. Thread hiện tại chờ JDBC trả kết quả.
3. Sau đó mới gọi Mono.just(product).
4. Publisher phát giá trị đã có khi được subscribe.

**Mono.just không trì hoãn việc tính đối số.** Nó giữ một giá trị đã được tính để phát sau.

### 4.2. Mono.fromCallable: trì hoãn Callable đến subscription

~~~java
Mono<Product> deferred = Mono.fromCallable(
        () -> jdbcRepository.findById(id)
);
~~~

Lúc này JDBC chưa chạy khi chỉ tạo Mono. Callable được gọi khi có subscription. Điều đó giải quyết vấn đề **eager evaluation**, nhưng chưa giải quyết vị trí thread:

- Subscribe trên event-loop: Callable có thể block event-loop.
- Subscribe trên worker được chọn phù hợp: Callable block worker đó.
- Nếu Callable gọi API non-blocking, không có lý do phải chuyển nó sang boundedElastic chỉ vì nó nằm trong fromCallable.

### 4.3. Mono.defer: tạo Publisher mới theo từng subscription

~~~java
Mono<Product> deferred = Mono.defer(() -> {
    String id = requestContext.currentProductId();
    return productService.findReactive(id);
});
~~~

**defer** gọi Supplier khi subscribe và nhận Publisher cho subscription đó. Nó hữu ích khi cần:

- Đọc giá trị context tại thời điểm subscription.
- Tạo request mới cho mỗi lần retry.
- Tránh gọi API tạo Future hoặc Publisher eager khi dựng pipeline.
- Tạo một Publisher riêng cho từng lượt đăng ký.

Nhưng **defer không tự chuyển thread và không làm hàm bên trong non-blocking**. Nếu Supplier gọi API blocking, thao tác vẫn chặn thread đang subscribe trừ khi được điều phối phù hợp.

### 4.4. Mono.fromFuture: Future có thể đã chạy trước khi được bọc

~~~java
CompletableFuture<Product> future =
        CompletableFuture.supplyAsync(() -> remoteService.fetch());

Mono<Product> eagerFuture = Mono.fromFuture(future);
~~~

Trong ví dụ này, **supplyAsync** được gọi ngay khi dựng biểu thức Java. Future có thể bắt đầu thực thi trước khi Mono được subscribe. fromFuture(future) bọc Future đã có.

Nếu muốn tạo Future theo subscription:

~~~java
Mono<Product> lazyFuture =
        Mono.fromFuture(() ->
                CompletableFuture.supplyAsync(
                        () -> remoteService.fetch(),
                        applicationExecutor
                )
        );
~~~

Overload nhận **Supplier<CompletableFuture>** trì hoãn việc tạo Future đến lúc subscribe. Tuy nhiên, nếu remoteService.fetch() vẫn là API blocking, worker của applicationExecutor vẫn bị chiếm trong lúc chờ. **Future là bất đồng bộ ở cách thông báo kết quả; nó không tự thay đổi bản chất của API bên trong.**

Khi dùng fromFuture, hãy hiểu chính sách cancellation: Reactor có thể truyền cancel tới Future theo overload được chọn, nhưng cancel Future không bảo đảm một lệnh remote đã gửi sẽ được rollback hoặc thread đang chạy dừng tức thời.

### 4.5. Bảng so sánh nhanh

| Cách tạo Publisher | Khi lời gọi bên trong chạy? | Có tự non-blocking không? |
| --- | --- | --- |
| **Mono.just(blockingCall())** | Ngay khi dựng biểu thức Java | Không; có thể block trước cả subscription |
| **Mono.fromCallable(blockingCall)** | Khi subscribe | Không; Callable vẫn đồng bộ trên thread subscription nếu không điều phối |
| **Mono.defer(() -> publisher)** | Supplier chạy khi subscribe | Không; phụ thuộc Publisher/hàm được tạo |
| **Mono.fromFuture(existingFuture)** | Future có thể đã chạy trước khi bọc | Không; phụ thuộc cách Future được tạo |
| **Mono.fromFuture(futureSupplier)** | Supplier tạo Future khi subscribe | Không; phụ thuộc công việc bên trong Future |
| **WebClient / reactive driver** | I/O được runtime điều phối theo cơ chế async | Thường non-blocking nếu connector/driver và các bước xung quanh cũng non-blocking |

## 5. map và flatMap không tự thay đổi tính blocking

### 5.1. map thực hiện hàm đồng bộ

~~~java
Mono<String> result = Mono.just("P01")
        .map(id -> jdbcRepository.findById(id).getName());
~~~

Hàm trong map được gọi khi upstream phát onNext. Nó chạy đồng bộ trên thread đang xử lý tín hiệu đó. Nếu JDBC block, thread đó block.

map phù hợp với phép biến đổi đồng bộ, nhanh và không chờ I/O, ví dụ:

~~~java
Mono<Integer> total = Mono.just(10)
        .map(value -> value * 2);
~~~

### 5.2. flatMap kết hợp Publisher, không tự biến hàm blocking thành async

~~~java
Mono<Product> product = Mono.just("P01")
        .flatMap(id -> Mono.just(jdbcRepository.findById(id)));
~~~

Đây vẫn là mã sai nếu repository blocking. Lời gọi jdbcRepository.findById(id) được đánh giá **trước** Mono.just; flatMap không thể làm nó bất đồng bộ.

flatMap hữu ích khi hàm trả về Publisher thực sự:

~~~java
Mono<Product> product = Mono.just("P01")
        .flatMap(id -> webClient.get()
                .uri("/products/{id}", id)
                .retrieve()
                .bodyToMono(Product.class));
~~~

Ở đây flatMap kết hợp Publisher từ WebClient; HTTP I/O được client non-blocking thực hiện. flatMap không tạo thread riêng cho mỗi phần tử; concurrency phụ thuộc vào inner Publisher và overload/concurrency strategy được dùng.

### 5.3. Một cách bọc blocking đúng hơn

~~~java
Mono<Product> product = Mono.fromCallable(
        () -> jdbcRepository.findById(id)
).subscribeOn(Schedulers.boundedElastic());
~~~

Callable được trì hoãn và **subscribeOn** điều phối việc subscribe/nguồn sang worker của boundedElastic. Thread event-loop không phải chờ JDBC.

Đây là cách **cô lập blocking** để tích hợp thư viện chưa có API reactive. Nó không biến JDBC thành non-blocking; mỗi tác vụ vẫn chiếm một worker trong lúc đợi. BoundedElastic có giới hạn thread và hàng đợi, nên cần theo dõi tải và đặt giới hạn phù hợp.

## 6. Scheduler giúp cô lập blocking, không xóa bỏ blocking

### 6.1. subscribeOn: điều phối nguồn

Khi nguồn ban đầu là một Callable blocking:

~~~java
Mono<Product> product = Mono.fromCallable(
        () -> jdbcRepository.findById(id)
).subscribeOn(Schedulers.boundedElastic());
~~~

Đặt subscribeOn gần nguồn giúp điều phối subscription/nguồn sang Scheduler phù hợp. Đây là mẫu Reactor thường khuyến nghị để bọc một lời gọi đồng bộ, blocking.

**boundedElastic** phù hợp cho blocking work bắt buộc phải dùng vì nó giới hạn tài nguyên thay vì tạo thread vô hạn. Khi tải tăng, tác vụ có thể phải chờ trong queue; do đó cần timeout, concurrency limit, metric và chính sách overload.

### 6.2. publishOn: chuyển ngữ cảnh downstream

Nếu nguồn WebClient non-blocking nhưng bước tiếp theo gọi một thư viện blocking:

~~~java
Mono<Report> report = webClient.get()
        .uri("/data/{id}", id)
        .retrieve()
        .bodyToMono(Data.class)
        .publishOn(Schedulers.boundedElastic())
        .map(data -> legacyBlockingFormatter.format(data));
~~~

publishOn đặt trước map để hàm format chạy ở worker boundedElastic. Nếu đặt publishOn **sau** map thì map có thể đã chạy trên thread upstream và đã block trước khi tín hiệu được chuyển.

### 6.3. Scheduler không đồng nghĩa API non-blocking

| Cách xử lý | Điều gì thay đổi? | Điều gì không thay đổi? |
| --- | --- | --- |
| fromCallable + subscribeOn(boundedElastic) | Blocking work chạy trên worker phù hợp hơn, giảm nguy cơ block event-loop | API vẫn blocking và chiếm worker trong thời gian chờ |
| publishOn(boundedElastic) trước một bước blocking | Bước downstream được chuyển sang worker khác | Công việc đó vẫn chiếm worker |
| subscribeOn(parallel) với JDBC | JDBC chạy trên worker CPU-oriented | Không phù hợp với blocking kéo dài; có thể làm nghẽn Scheduler |
| WebClient với connector non-blocking | I/O được điều phối qua callback/event loop | map/filter phía ứng dụng vẫn có thể blocking |
| Mono.delay(Duration) | Timer được lập lịch và phát tín hiệu sau khoảng chờ | Nếu gọi block() để chờ ở caller, chính caller vẫn bị block tại ranh giới đồng bộ |

**Schedulers.parallel()** dành cho công việc CPU-bound, ngắn và không blocking. **Schedulers.boundedElastic()** dành cho blocking work không thể tránh. Không dùng parallel để “chạy nhanh hơn” một API JDBC blocking.

## 7. Vì sao điều này đặc biệt quan trọng trong Spring WebFlux?

WebFlux được thiết kế với giả định các request handler không block. Với runtime event-loop như Reactor Netty, số thread xử lý request tương đối nhỏ và cố định so với số lượng request/kết nối có thể đồng thời được quản lý.

Một event-loop thread có thể điều phối nhiều connection. Nếu một controller gọi JDBC đồng bộ:

~~~text
Event-loop worker
    |
    +--> nhận request A
    |
    +--> gọi JDBC và chờ 800 ms  <--- thread bị giữ
    |
    +--> chưa thể xử lý callback khác trên worker đó
    |
    +--> JDBC trả kết quả
    |
    +--> tiếp tục response
~~~

Trong lúc chờ, các tác vụ khác được giao cho cùng worker có thể bị trì hoãn. Dưới tải, điều này dẫn tới latency tăng, queue dài, timeout dây chuyền và throughput giảm.

Không phải mọi thread trong WebFlux đều là event-loop, và tên thread cụ thể phụ thuộc server/runtime/cấu hình. Tuy nhiên, nguyên tắc vẫn là: **không chạy blocking I/O trên thread được thiết kế để phục vụ nhiều tín hiệu reactive**.

### 7.1. Controller trả Mono nhưng vẫn block trước khi trả

~~~java
@GetMapping("/products/{id}")
Mono<Product> get(@PathVariable String id) {
    Product product = jdbcRepository.findById(id); // Block tại đây.
    return Mono.just(product);
}
~~~

Method return type là Mono, nhưng controller chỉ trả Mono **sau khi JDBC đã hoàn tất**. WebFlux không thể quay ngược thời gian để biến lời gọi đồng bộ thành async.

### 7.2. Controller trả Mono và trì hoãn nhưng vẫn block event-loop

~~~java
@GetMapping("/products/{id}")
Mono<Product> get(@PathVariable String id) {
    return Mono.fromCallable(
            () -> jdbcRepository.findById(id)
    );
}
~~~

Đã tránh eager call, nhưng nếu subscription được thực hiện trên thread request/event-loop, Callable vẫn có thể chạy trên thread đó. Cần dùng driver reactive hoặc điều phối blocking sang boundedElastic.

### 7.3. Controller trả Mono và giữ I/O non-blocking

~~~java
@GetMapping("/products/{id}")
Mono<Product> get(@PathVariable String id) {
    return webClient.get()
            .uri("/products/{id}", id)
            .retrieve()
            .bodyToMono(Product.class);
}
~~~

WebClient với connector non-blocking thực hiện HTTP I/O theo cơ chế event-driven. Controller trả Publisher và framework quản lý subscription/response. Tuy nhiên, mọi bước map/filter/validation sau đó vẫn cần tránh blocking.

## 8. Dùng driver reactive end-to-end khi có thể

Nếu database là thành phần chính gây chờ, lựa chọn driver có ý nghĩa lớn.

| Tầng dữ liệu | API thường gặp | Đặc tính |
| --- | --- | --- |
| JDBC | JdbcTemplate, JDBC Repository | Blocking I/O |
| JPA/Hibernate ORM truyền thống | EntityManager, JpaRepository | Thường blocking theo JDBC |
| R2DBC | DatabaseClient, ReactiveCrudRepository | Reactive/non-blocking I/O nếu driver và cấu hình hỗ trợ |
| Reactive MongoDB driver | ReactiveMongoTemplate/Repository | Reactive I/O |
| HTTP WebClient | retrieve().bodyToMono(...) | Non-blocking với connector hỗ trợ |
| HTTP client đồng bộ | RestTemplate hoặc client blocking | Caller thường chờ response |

Ví dụ service dùng R2DBC:

~~~java
@Service
class ProductService {
    private final ReactiveCrudRepository<Product, String> repository;

    ProductService(ReactiveCrudRepository<Product, String> repository) {
        this.repository = repository;
    }

    Mono<Product> find(String id) {
        return repository.findById(id);
    }
}
~~~

Đây là đoạn minh họa, giả định repository được cấu hình bằng reactive database driver phù hợp. Publisher được tạo từ API reactive; không cần bọc bằng fromCallable hoặc chuyển sang boundedElastic chỉ vì nó là database call.

Một số lưu ý:

- **Reactive driver phải thực sự non-blocking** ở tầng network/driver.
- Nếu trong pipeline reactive lại gọi JDBC hoặc JPA, toàn chuỗi không còn non-blocking end-to-end.
- Transaction cần dùng cơ chế reactive transaction manager phù hợp; không dùng transaction đồng bộ rồi kỳ vọng Publisher tự chuyển đổi.
- Không nên dùng R2DBC chỉ vì có chữ reactive nếu ứng dụng không có nhu cầu concurrency/streaming tương ứng; lựa chọn stack cần dựa vào kiến trúc và vận hành.

## 9. CompletableFuture và thread pool: bất đồng bộ không đồng nghĩa non-blocking

Một ví dụ phổ biến:

~~~java
Mono<Product> result = Mono.fromFuture(
        CompletableFuture.supplyAsync(
                () -> blockingRepository.findById(id)
        )
);
~~~

Caller có thể nhận Mono ngay, nhưng supplyAsync được gọi ngay khi dựng biểu thức. Nó dùng common ForkJoinPool nếu không truyền Executor. Nếu blockingRepository chờ JDBC, worker trong pool vẫn bị giữ. Dưới tải, pool có thể thiếu worker cho các tác vụ khác.

Nếu buộc dùng Future API, hãy:

1. Xác định API underlying có thực sự non-blocking hay chỉ chạy blocking trên executor.
2. Dùng Executor có cấu hình và giới hạn rõ cho blocking work.
3. Dùng Supplier overload của fromFuture hoặc defer nếu cần tạo Future theo subscription.
4. Có timeout, cancellation và xử lý lỗi đúng hợp đồng.
5. Không coi cancel Future là rollback thao tác remote.

Ví dụ tạo Future lazy với executor riêng:

~~~java
Mono<Product> result = Mono.fromFuture(() ->
        CompletableFuture.supplyAsync(
                () -> blockingRepository.findById(id),
                blockingExecutor
        )
);
~~~

Đây vẫn là **cô lập một lời gọi blocking trên Executor**. Nếu thư viện có callback API thực sự non-blocking, ưu tiên adapter Publisher từ chính API đó.

## 10. Backpressure không biến blocking thành non-blocking

Reactive Streams dùng demand để Subscriber điều tiết số phần tử Publisher được phép phát. Cơ chế này giúp quản lý tốc độ dữ liệu, nhưng không làm một lời gọi JDBC, Thread.sleep, Future.get hoặc Mono.block trở nên non-blocking.

Ví dụ:

~~~java
Flux<Integer> values = Flux.range(1, 100)
        .map(number -> {
            Thread.sleep(100);
            return number;
        });
~~~

Đây là đoạn mã minh họa. Dù Flux có hỗ trợ backpressure, map vẫn chặn thread xử lý onNext trong 100 ms cho mỗi phần tử.

Cần tách hai vấn đề:

- **Backpressure:** kiểm soát lượng tín hiệu được yêu cầu/truyền xuống.
- **Non-blocking execution:** không giữ thread chờ I/O; dùng callback/event-loop hoặc cơ chế async thích hợp.

Một nguồn không thể giảm tốc có thể cần buffer, drop hoặc fail theo chính sách. Buffer cũng không sửa được việc một operator đang blocking trên event-loop.

## 11. Cancellation và timeout không bảo đảm công việc blocking dừng ngay

Khi downstream hủy subscription hoặc timeout xảy ra, Reactor gửi tín hiệu cancellation lên upstream. Tuy nhiên:

- Một Callable đã bắt đầu có thể đang ở giữa lệnh JDBC/file I/O.
- Thread interruption có thể không được thư viện ngoài hỗ trợ hoặc không dừng thao tác ngay.
- Future.cancel(true) không bảo đảm mọi task đã bắt đầu đều ngừng tức thì.
- Một HTTP request đã tới server có thể tiếp tục thực thi dù client đã hủy.
- Side effect đã commit không tự rollback chỉ vì Publisher bị cancel.

Vì vậy, với blocking operation cần có:

- Timeout ở đúng tầng client/driver và deadline của operation.
- API hỗ trợ cancellation nếu có.
- Giới hạn concurrency và số tác vụ pending.
- Idempotency cho các thao tác ghi có thể retry.
- Quan sát task còn chạy sau khi request kết thúc.

**Cancellation là tín hiệu điều khiển Publisher, không phải cam kết dừng mọi hệ thống bên ngoài.**

## 12. Ví dụ Java 17+ chạy được: chứng minh khác biệt giữa eager, deferred và offload

Ví dụ sau dùng **Reactor Core** thuần, không cần Spring Boot hay database thật. Hàm blockingRead mô phỏng một API đồng bộ bằng Thread.sleep ngắn. Mục tiêu là quan sát thời điểm và thread chạy hàm.

Cấu trúc:

~~~text
reactive-vs-nonblocking/
├── pom.xml
└── src/main/java/ReactiveDoesNotMeanNonBlockingDemo.java
~~~

### 12.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactive-vs-nonblocking</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>ReactiveDoesNotMeanNonBlockingDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 12.2. ReactiveDoesNotMeanNonBlockingDemo.java

~~~java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public class ReactiveDoesNotMeanNonBlockingDemo {

    private static String blockingRead(AtomicBoolean invoked) {
        invoked.set(true);
        try {
            Thread.sleep(20); // Mô phỏng lời gọi I/O blocking.
        } catch (InterruptedException error) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", error);
        }
        return "record";
    }

    public static void main(String[] args) {
        String callerThread = Thread.currentThread().getName();

        // 1. Mono.just nhận giá trị đã được tính ngay khi dựng Publisher.
        AtomicBoolean eagerInvoked = new AtomicBoolean();
        Mono<String> eager = Mono.just(blockingRead(eagerInvoked));
        boolean eagerRanBeforeSubscribe = eagerInvoked.get();
        eager.block();

        // 2. fromCallable trì hoãn lời gọi đến subscription.
        AtomicBoolean deferredInvoked = new AtomicBoolean();
        AtomicReference<String> deferredThread = new AtomicReference<>();

        Mono<String> deferred = Mono.fromCallable(() -> {
            deferredThread.set(Thread.currentThread().getName());
            return blockingRead(deferredInvoked);
        });

        boolean callableWasDeferred = !deferredInvoked.get();
        deferred.block();
        boolean callableRanOnCaller =
                callerThread.equals(deferredThread.get());

        // 3. subscribeOn chuyển nguồn blocking sang boundedElastic.
        AtomicReference<String> workerThread = new AtomicReference<>();

        Mono<String> isolated = Mono.fromCallable(() -> {
            workerThread.set(Thread.currentThread().getName());
            return blockingRead(new AtomicBoolean());
        }).subscribeOn(Schedulers.boundedElastic());

        isolated.block();
        boolean blockingCallMovedOffCaller =
                !callerThread.equals(workerThread.get());

        // 4. Timer phát tín hiệu bất đồng bộ; block chỉ được dùng
        //    tại ranh giới console để quan sát kết quả.
        long timerValue = Mono.delay(Duration.ofMillis(10)).block();

        System.out.println(
                "eager work ran before subscribe = " + eagerRanBeforeSubscribe);
        System.out.println(
                "fromCallable work was deferred = " + callableWasDeferred);
        System.out.println(
                "fromCallable ran on caller thread = " + callableRanOnCaller);
        System.out.println(
                "boundedElastic moved work off caller = "
                        + blockingCallMovedOffCaller);
        System.out.println("Mono.delay emitted = " + timerValue);
    }
}
~~~

### 12.3. Chạy chương trình

Yêu cầu **JDK 17+**, Maven và kết nối tải dependency lần đầu. Tại thư mục chứa pom.xml:

~~~bash
mvn -q compile exec:java
~~~

**Stdout do chương trình in ra:**

~~~text
eager work ran before subscribe = true
fromCallable work was deferred = true
fromCallable ran on caller thread = true
boundedElastic moved work off caller = true
Mono.delay emitted = 0
~~~

### 12.4. Phân tích kết quả

1. **eager work ran before subscribe = true**: blockingRead đã chạy khi Java đánh giá đối số của Mono.just, trước khi gọi block.
2. **fromCallable work was deferred = true**: Callable chưa chạy khi chỉ tạo Publisher; nó chạy khi block() subscribe.
3. **fromCallable ran on caller thread = true**: fromCallable mặc định không tự đổi Scheduler. block() subscribe trên main thread nên Callable đồng bộ chạy trên thread đó.
4. **boundedElastic moved work off caller = true**: subscribeOn(boundedElastic) điều phối nguồn sang worker khác. Lời gọi vẫn dùng một worker trong thời gian Thread.sleep; nó chỉ được cô lập khỏi caller.
5. **Mono.delay emitted = 0**: timer được lập lịch và phát tín hiệu sau thời gian đặt trước. Trong demo console, block() chờ kết quả để in; controller WebFlux thực tế sẽ trả Publisher thay vì block.

Đây là chương trình **minh họa hành vi thời điểm/thread**, không phải benchmark. Thread.sleep chỉ mô phỏng một API blocking; thời lượng thực tế và tên worker có thể thay đổi theo runtime. Chương trình không kết luận rằng mọi API dùng Future hay Mono đều non-blocking.

## 13. Ví dụ áp dụng trong Controller và Service

### 13.1. Mẫu nên dùng khi bắt buộc gọi JDBC/JPA blocking

~~~java
@Service
class LegacyProductService {
    private final ProductRepository repository;

    LegacyProductService(ProductRepository repository) {
        this.repository = repository;
    }

    Mono<Product> find(String id) {
        return Mono.fromCallable(() -> repository.findById(id))
                .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

Đây là **đoạn minh họa**, giả định ProductRepository là API blocking trả Product. fromCallable trì hoãn lời gọi; subscribeOn cô lập nó trên boundedElastic.

Controller trả Publisher:

~~~java
@RestController
class ProductController {
    private final LegacyProductService service;

    ProductController(LegacyProductService service) {
        this.service = service;
    }

    @GetMapping("/products/{id}")
    Mono<Product> find(@PathVariable String id) {
        return service.find(id);
    }
}
~~~

Không gọi subscribe() hoặc block() trong controller. Framework quản lý vòng đời response. Nếu nguồn blocking có thể mất nhiều thời gian, hãy cấu hình timeout và giới hạn số tác vụ pending; không dựa vào boundedElastic như một pool vô hạn.

### 13.2. Mẫu nên dùng với API reactive thật sự

~~~java
@Service
class ReactiveProductService {
    private final WebClient webClient;

    ReactiveProductService(WebClient.Builder builder) {
        this.webClient = builder.baseUrl("https://catalog.example").build();
    }

    Mono<Product> find(String id) {
        return webClient.get()
                .uri("/products/{id}", id)
                .retrieve()
                .bodyToMono(Product.class);
    }
}
~~~

Đây là đoạn service minh họa với Product và WebClient được cấu hình trong ứng dụng. I/O HTTP được connector non-blocking thực hiện. Không cần bọc WebClient bằng fromCallable hoặc subscribeOn(boundedElastic).

Nếu sau bodyToMono có một bước CPU-bound đáng kể, cân nhắc một ranh giới Scheduler phù hợp. Nếu bước đó gọi API blocking, phải cô lập blocking hoặc thay thư viện bằng API non-blocking.

### 13.3. Không đặt publishOn sau thao tác đã block

~~~java
// Sai: JDBC đã chạy trước publishOn.
Mono<Product> wrong = Mono.just(repository.findById(id))
        .publishOn(Schedulers.boundedElastic());
~~~

~~~java
// Đúng hơn: trì hoãn và điều phối lời gọi blocking.
Mono<Product> wrapped = Mono.fromCallable(
        () -> repository.findById(id)
).subscribeOn(Schedulers.boundedElastic());
~~~

publishOn chỉ thay đổi nơi xử lý **phía downstream** từ vị trí nó được đặt. Nó không thể di chuyển ngược một lời gọi đã chạy xong.

## 14. Kiểm tra xem pipeline có thực sự non-blocking không

Chữ ký method không đủ. Cần quan sát implementation và thread thực thi.

### 14.1. Kiểm tra nguồn dữ liệu và thư viện

- Repository dùng **JDBC/JPA** hay **R2DBC/reactive driver**?
- HTTP client dùng **WebClient/connector non-blocking** hay API đồng bộ?
- File I/O dùng API đồng bộ hay async?
- Có Thread.sleep, Object.wait, CountDownLatch.await, Future.get, CompletableFuture.join, Mono.block hoặc Flux.blockLast không?
- Có hàm mapper/validator/serializer thực hiện truy vấn mạng hoặc đọc file không?
- Có tạo Future eager trước khi Publisher được subscribe không?

### 14.2. Kiểm tra thread

Ghi nhận thread ở các bước nhạy cảm:

~~~java
Mono<Product> result = productService.find(id)
        .doOnNext(product -> log.debug(
                "product received on thread {}",
                Thread.currentThread().getName()
        ));
~~~

Đây là đoạn minh họa với logger. Tên thread có thể giúp nhận ra event-loop (reactor-http-nio-... với Reactor Netty) hoặc boundedElastic (boundedElastic-...), nhưng **không dùng tên thread làm hợp đồng cố định** vì runtime/cấu hình có thể thay đổi.

### 14.3. Dùng BlockHound trong môi trường phát triển/test

**BlockHound** là công cụ tích hợp với Reactor để phát hiện một số lời gọi blocking trên thread được đánh dấu non-blocking. Nó hữu ích để tìm Thread.sleep, chờ đồng bộ hoặc API blocking trong pipeline.

Cần lưu ý:

- Cấu hình BlockHound và integration theo phiên bản JDK, Reactor, thư viện.
- Không phải mọi API blocking tùy chỉnh đều tự động bị phát hiện; có thể cần instrumentation/allow-list phù hợp.
- Chạy trong test hoặc môi trường development để phát hiện sớm.
- BlockHound không thay thế code review, đo hiệu năng hay kiểm tra driver.

### 14.4. Đo dưới tải thực tế

Theo dõi:

- Event-loop thread bị giữ lâu hoặc CPU/queue tăng.
- Latency P95/P99 và số request đang xử lý.
- BoundedElastic active threads, queued tasks và rejected tasks.
- Connection pool pending acquire và thời gian truy vấn DB.
- Tỷ lệ timeout/cancel và số thao tác vẫn tiếp tục ở hệ thống ngoài.
- Số subscription và mức tiêu thụ bộ nhớ khi streaming.

Reactive/non-blocking không tự làm mọi ứng dụng nhanh hơn. Lợi ích thường rõ khi có nhiều I/O chậm hoặc không dự đoán được, và các tầng thật sự hỗ trợ non-blocking. Nếu toàn hệ thống vẫn blocking, chuyển sang WebFlux có thể tăng độ phức tạp mà không đạt lợi ích mong muốn.

## 15. Những hiểu nhầm thường gặp

| Hiểu nhầm | Hậu quả | Cách hiểu đúng |
| --- | --- | --- |
| Method trả Mono nên chắc chắn non-blocking | JDBC có thể block trước khi Mono được trả | Kiểm tra toàn bộ lời gọi và thread thực thi |
| Mono.just trì hoãn biểu thức | Blocking xảy ra ngay khi dựng Mono | Đối số Java được đánh giá trước khi gọi just |
| fromCallable tự chạy bất đồng bộ | Callable có thể chạy trên thread subscribe | Cần Scheduler phù hợp nếu Callable blocking |
| defer biến code thành non-blocking | Supplier vẫn có thể block khi subscribe | defer chỉ trì hoãn việc tạo Publisher |
| flatMap tự tạo thread riêng | Blocking lambda vẫn chạy đồng bộ | flatMap kết hợp Publisher; inner source quyết định hành vi |
| publishOn đặt sau map sẽ chuyển map | Map có thể đã block upstream | Đặt boundary trước bước cần chuyển |
| subscribeOn(boundedElastic) biến JDBC thành reactive | Worker vẫn bị chiếm trong lúc JDBC chờ | Đây là cô lập blocking, không phải non-blocking I/O |
| CompletableFuture luôn non-blocking | Worker trong executor có thể chạy blocking API | Phân tích tác vụ bên trong Future |
| Backpressure ngăn thread bị block | map hoặc JDBC vẫn block thread | Backpressure điều tiết demand, không đổi semantics I/O |
| Cancel nghĩa là server dừng ngay | Remote side effect có thể vẫn chạy | Cancellation phụ thuộc driver/protocol và không tự rollback |
| Reactive luôn nhanh hơn MVC | Thêm scheduler/operator có thể tăng overhead | Đo workload và chọn mô hình phù hợp |
| Tên thread cố định là cách kiểm chứng duy nhất | Test dễ hỏng khi runtime thay đổi | Kiểm tra loại Scheduler, stack trace và metric |

## 16. Checklist trước khi viết một controller reactive

1. **Method có làm công việc trước khi trả Publisher không?** Tránh gọi blocking/eager trước Mono.just.
2. **Nguồn có thực sự lazy không?** Phân biệt Mono.just, fromCallable, defer và Future đã chạy.
3. **I/O client/driver có non-blocking thật không?** Kiểm tra implementation, không chỉ kiểu trả về.
4. **Các lambda map/filter/doOnNext có blocking không?** Operator đồng bộ chạy trên thread phát tín hiệu.
5. **Nếu bắt buộc blocking, đã cô lập đúng chưa?** Dùng fromCallable + subscribeOn(boundedElastic) cho nguồn blocking hoặc publishOn trước bước downstream blocking.
6. **Có dùng đúng Scheduler không?** parallel cho CPU-bound; boundedElastic cho blocking.
7. **Có block/get/join/sleep trên event-loop không?** Loại bỏ hoặc thiết kế ranh giới đồng bộ rõ ràng.
8. **Có giới hạn concurrency/queue không?** Tránh dồn quá nhiều tác vụ blocking.
9. **Cancellation và timeout có ý nghĩa gì với driver/remote API?** Không giả định đã rollback.
10. **Có test/metric phát hiện blocking không?** Dùng BlockHound khi phù hợp, quan sát event-loop và latency dưới tải.

## 17. Kết luận

**Trả về Mono hoặc Flux không đồng nghĩa công việc thực sự non-blocking.** Mono.just có thể nhận một kết quả đã được tính bằng lời gọi blocking; fromCallable trì hoãn lời gọi nhưng vẫn có thể chạy trên thread subscribe; defer chỉ trì hoãn việc tạo Publisher; Future có thể chạy blocking work trên một executor khác.

Muốn một ứng dụng WebFlux thực sự non-blocking, cần dùng **WebClient và reactive database driver** hoặc API async/non-blocking tương ứng xuyên suốt. Khi phải tích hợp thư viện blocking, hãy dùng **fromCallable + subscribeOn(boundedElastic)** hoặc publishOn đúng vị trí để bảo vệ event-loop, đồng thời giới hạn tải và theo dõi queue. Đây là biện pháp cô lập, không phải chuyển API blocking thành non-blocking.

Trước khi kết luận một controller reactive có an toàn cho WebFlux, hãy truy vết **từ lúc method được gọi, lúc Publisher được tạo, lúc subscribe, qua từng operator, tới I/O driver và lúc cancellation**. Kiểu trả về chỉ là một phần của câu trả lời.

**Tài liệu chính thức:**
- [Spring Framework — WebFlux Overview: reactive, non-blocking và concurrency model](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html)
- [Reactor Reference — How do I wrap a synchronous, blocking call?](https://projectreactor.io/docs/core/release/reference/faq.html)
- [Reactor Mono API — fromCallable, fromFuture và subscribeOn](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html)
- [Reactor Reference — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html)
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html)
- [Spring Data R2DBC — Reference](https://docs.spring.io/spring-data/relational/reference/r2dbc.html)
