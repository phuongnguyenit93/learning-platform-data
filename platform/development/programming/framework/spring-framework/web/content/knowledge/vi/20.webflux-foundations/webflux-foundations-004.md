# Event loop, mô hình luồng và tác hại của thao tác chặn trong Spring WebFlux

## 1. Bài toán: vì sao một lệnh `sleep` có thể làm nghẽn cả WebFlux?

Giả sử một server WebFlux dựa trên Reactor Netty tiếp nhận đồng thời nhiều request. Mỗi request cần chờ một dịch vụ ngoài 300 ms. Nếu xử lý bằng I/O bất đồng bộ đúng cách, event-loop thread **không phải nằm chờ** response; nó có thể tiếp tục phục vụ các kết nối khác và được đánh thức khi có sự kiện I/O hoàn tất.

Ngược lại, nếu trong handler bạn thực hiện:

~~~java
@GetMapping("/bad")
public Mono<String> bad() throws InterruptedException {
    Thread.sleep(300);              // CHẶN request/event-loop thread!
    return Mono.just("done");
}
~~~

thì `Thread.sleep(300)` chạy **ngay lúc Spring gọi controller method**, trước khi `Mono.just` được tạo. Trên mô hình Netty event-loop thông thường, điều này có thể chiếm một event-loop thread trong 300 ms. Các kết nối khác được gán tới loop đó phải chờ; kết quả có thể là latency tăng đột biến, throughput giảm, timeout và "cascading failure" khi tải cao.

**`Mono<T>` không tự biến một phép tính chặn thành non-blocking.** Một API trả kiểu reactive nhưng vẫn gọi `Thread.sleep`, `Future.get`, `RestTemplate`, JDBC đồng bộ hoặc `block()` trong sai ngữ cảnh vẫn có thể làm tắc luồng xử lý.

Bài này giải thích chính xác:
1. Event loop xử lý sự kiện như thế nào và vì sao cần giữ mỗi callback ngắn.
2. Reactor Netty dùng bao nhiêu nhóm thread về mặt mô hình, không nhầm một request với một thread.
3. `Mono`/`Flux`, subscription, operators và `Scheduler` liên quan tới thread thế nào.
4. Phân biệt `publishOn`, `subscribeOn` và quy tắc cô lập blocking code.
5. Vì sao `.block()`, `Thread.sleep`, blocking JDBC/HTTP/file I/O và CPU-heavy work gây hại ở các mức độ khác nhau.
6. Cách dùng `Schedulers.boundedElastic()` hoặc một **bounded scheduler riêng** cho thư viện legacy.
7. Cách dùng WebClient/R2DBC để non-blocking end-to-end.
8. Timeout, cancellation, overload, backpressure, context propagation, monitoring và test.

Ví dụ runnable dùng Java 17, Spring Boot **3.3.5**, Spring WebFlux và Reactor Netty. Một vài giá trị implementation (số event-loop threads, tên threads, scheduler defaults) thay đổi theo CPU, container, Reactor release và configuration: **không hard-code chúng thành cam kết API**.

## 2. Hiểu ba thuật ngữ trước khi đọc code

### 2.1. Concurrency (đồng thời) khác parallelism (song song)

**Concurrency** là quản lý tiến độ nhiều tác vụ chồng lấn về thời gian, có thể chỉ sử dụng một CPU/thread nếu các tác vụ dành nhiều thời gian chờ I/O.

**Parallelism** là thực thi nhiều công việc **đồng thời ở mức vật lý** trên nhiều CPU cores.

Một event loop trên một thread có thể phục vụ hàng nghìn connections nhờ hoạt động event-driven, nhưng nó không thể thực thi đồng thời hai đoạn CPU code trên chính thread đó.

Ví dụ:
- 1.000 HTTP connections đang đợi network response không đồng nghĩa cần 1.000 threads.
- 1.000 phép tính CPU nặng cũng không thể tự chạy nhanh chỉ vì được trả về dưới dạng `Flux`.
- Một blocking JDBC query vẫn cần một thread bị chiếm trong khoảng thời gian query chờ nếu dùng driver JDBC truyền thống.

### 2.2. Blocking và non-blocking I/O

**Blocking I/O** thường khiến thread gọi phải chờ tới khi có dữ liệu hoặc kết thúc timeout, ví dụ:

~~~java
String body = legacyHttpClient.executeSynchronousRequest();
~~~

Đây là fragment giả định có biến `legacyHttpClient`, không phải Java SDK cụ thể. Khi network chậm, thread gọi bị chiếm mặc dù CPU phần lớn rảnh.

**Non-blocking I/O** đăng ký quan tâm tới sự kiện đọc/ghi hoặc completion. Thread có thể quay lại xử lý việc khác; khi socket sẵn sàng, event loop nhận notification và tiếp tục pipeline:

~~~java
Mono<String> body =
        webClient.get()
                .uri("/resource")
                .retrieve()
                .bodyToMono(String.class);
~~~

Đây cũng là fragment; `webClient` phải được cấu hình bằng `WebClient` và connector reactive. Đoạn này **không gửi request ngay tại thời điểm tạo pipeline**; thông thường HTTP exchange bắt đầu khi có subscription. Không gọi `body.block()` trong handler WebFlux để biến code trở lại đồng bộ.

### 2.3. "Không bị chặn" khác "không tốn thời gian"

Non-blocking không làm network round-trip từ 300 ms thành 3 ms. Nó giúp thread không bị giữ trong thời gian chờ, nên một số lượng thread nhỏ có thể phục vụ nhiều yêu cầu đang chờ I/O. Tổng latency của request vẫn bao gồm network, server downstream, data decoding, retry và queuing.

## 3. Event loop hoạt động thế nào?

Event loop là cơ chế liên tục chờ và xử lý các sự kiện như socket readable/writable, connection accepted, scheduled timer hoặc task callback. Về khái niệm:

~~~text
while (serverIsRunning) {
    events = waitForReadyEvents();
    for (event : events) {
        handleSmallNonBlockingStep(event);
    }
}
~~~

Đây là **pseudocode**, không phải mã nguồn thực của Netty. Điểm quyết định: `handleSmallNonBlockingStep` phải nhanh và tránh chờ dữ liệu hoặc lock dài. Khi công việc chưa sẵn sàng, đăng ký callback/continuation rồi trao quyền cho event loop xử lý sự kiện khác.

### 3.1. Sơ đồ hai requests

~~~text
                    Một event-loop thread
                           |
time -->  [read A] [read B] [schedule I/O A]
                           |
          [handle B] [write B] [read C]
                           |
             ...network response A arrives...
                           |
          [resume A] [serialize A] [write A]
~~~

Đây là mô hình logic, không khẳng định chỉ có duy nhất một loop của server. Reactor Netty thường quản lý một nhóm worker event loops; một connection có thể gắn với loop nhất định, và một loop phục vụ nhiều connections.

Khi A phải đợi dịch vụ khác, event loop không nên nằm yên trong A; nó tiếp tục B/C. Nếu A chạy `Thread.sleep(1000)` ngay trên loop, B/C trong cùng loop có thể bị trì hoãn đáng kể.

### 3.2. Những gì event loop thực sự làm

- Nhận/đọc/ghi dữ liệu qua socket và phối hợp Netty channel pipeline.
- Kích hoạt downstream reactive callbacks/operators.
- Thực hiện code user mà framework gọi **nếu chưa có scheduler switch**.
- Xử lý timer/scheduled tasks và lifecycle callbacks.
- Phối hợp backpressure và write readiness theo implementation.

Event loop **không** phải một thread riêng cho mỗi HTTP request. Cũng không có lời hứa rằng một request luôn chạy trên cùng thread từ đầu đến cuối nếu pipeline có `publishOn`, `subscribeOn`, thư viện bất đồng bộ hay các scheduler khác.

### 3.3. Reactor Netty và client/server loops

Trong một ứng dụng Boot WebFlux chạy Reactor Netty, bạn thường thấy thread names mang tiền tố như:

~~~text
reactor-http-nio-1
reactor-http-nio-2
...
~~~

Đây là **ví dụ tên threads thường gặp**, không phải giá trị cố định, API contract hoặc căn cứ cho production authorization. Reactor Netty `WebClient` và HTTP server **mặc định có thể chia sẻ event-loop resources** khi cùng dùng Reactor Netty.

Hệ quả: một handler server vô tình chặn event loop có thể đồng thời làm trì hoãn I/O progress của các outbound WebClient requests trên shared resources. Trong production có thể cấu hình `LoopResources`, connection pool hoặc client/server resources riêng, nhưng **tăng số loop không phải phương pháp chữa blocking code**.

Không khẳng định "Netty luôn có đúng 4 threads" hay "mỗi core có 2 event loops": tài liệu, CPU count, cgroup/container limits và configuration thay đổi defaults.

## 4. Mô hình luồng: Spring MVC và Spring WebFlux

| Đặc điểm | Servlet Spring MVC đồng bộ | Spring WebFlux trên Reactor Netty |
| --- | --- | --- |
| Thread cho request | Thường một servlet worker bị giữ khi controller blocking | Số event-loop threads nhỏ phục vụ nhiều connections |
| Giả định thiết kế mặc định | Blocking API được chấp nhận trong giới hạn container thread pool | User code trên event loop phải non-blocking |
| Xử lý I/O chậm | Thread thường chờ | Đăng ký completion và tiếp tục khi socket sẵn sàng |
| Return type | DTO/ResponseEntity hoặc async types | `Mono<T>`, `Flux<T>`, các publishers/adapters |
| Gọi JDBC blocking | Thường trực tiếp trên worker pool | Không gọi trên event loop; cần isolate hoặc đổi stack |
| HTTP client non-blocking | Có thể dùng `WebClient` | `WebClient` là lựa chọn tự nhiên |
| Khi tải vượt năng lực | Queue/worker saturation | Event-loop starvation, scheduler/connection pool saturation |
| Phù hợp | CRUD, JDBC và ecosystem blocking rộng | High concurrency I/O, reactive stack end-to-end |

**Không biến so sánh thành khẩu hiệu “WebFlux luôn nhanh hơn MVC”.** Spring Framework giải thích lợi ích chính của reactive stack là **scalability/predictable resource usage** với workload chờ I/O, chứ không bảo đảm latency thấp hơn trong mọi tác vụ. Với ứng dụng chủ yếu dùng JDBC và các thư viện blocking, MVC có thể đơn giản hơn và hoạt động rất tốt.

### 4.1. Spring WebFlux không chỉ chạy trên Netty

Spring WebFlux có thể chạy trên Reactor Netty hoặc qua adapters cho Servlet non-blocking servers như Tomcat/Jetty. Khi đó thread names/chi tiết scheduling khác nhau. Bài dùng Reactor Netty để giải thích event loop cụ thể, **không suy diễn** toàn bộ WebFlux deployments có cùng số threads với Netty.

### 4.2. Boot chọn MVC hay WebFlux khi có hai starters?

Spring Boot thường ưu tiên **Spring MVC application type** khi cả `spring-boot-starter-web` và `spring-boot-starter-webflux` cùng hiện diện, trừ khi application type được cấu hình chủ đích. Để chạy đúng demo WebFlux/Netty dưới đây, chỉ thêm `spring-boot-starter-webflux`, **không thêm `spring-boot-starter-web`**. Một ứng dụng MVC vẫn có thể dùng reactive `WebClient` mà không cần chuyển server sang WebFlux.

## 5. Reactive Streams, `Mono`, `Flux` và subscription

Reactor cung cấp:
- `Mono<T>`: publisher phát **0 hoặc 1** item, hoặc kết thúc bằng error.
- `Flux<T>`: publisher phát **0 đến N** items, hoặc kết thúc bằng error.

Cả hai biểu diễn một **pipeline**: chuỗi operators, signals và side effects được thực hiện khi subscription và dữ liệu tương ứng xuất hiện.

~~~java
Mono<String> pipeline = Mono.just("spring")
        .map(String::toUpperCase);
~~~

Ở đây `"spring"` được tạo sẵn; toán tử `map` thường chạy khi có subscription. Chỉ tạo biến `pipeline` **không có nghĩa HTTP response đã gửi hoặc network request đã chạy**.

### 5.1. Signals

Luồng reactive có các signals như:
- `onSubscribe`: thiết lập subscription.
- `onNext`: item được phát.
- `onComplete`: hoàn thành bình thường.
- `onError`: kết thúc bằng lỗi.
- `request(n)`: subscriber yêu cầu số lượng items, là cơ chế backpressure.
- `cancel()`: subscriber hủy subscription.

Backpressure giúp mô tả nhu cầu tiêu thụ, **không bảo đảm mọi producer bên ngoài có thể giảm tốc vô hạn**. Nếu upstream không thể chậm lại, hệ thống cần buffering giới hạn, dropping, rejection hoặc control ở ingress. Reactive type không biến memory thành vô hạn.

### 5.2. Tránh gọi `subscribe()` trong controller chỉ để "khởi động"

Ví dụ sai:

~~~java
@GetMapping("/bad-start")
public Mono<String> badStart() {
    remoteCall().subscribe();       // side effect tách khỏi HTTP lifecycle
    return Mono.just("accepted");
}
~~~

`remoteCall()` chỉ là fragment chưa định nghĩa. Khi tự subscribe, bạn tạo một tác vụ độc lập khó liên kết với request cancellation, errors, retries, trace và HTTP response. Nếu mục tiêu là trả kết quả trong cùng request, hãy **return publisher** để WebFlux quản lý subscription:

~~~java
@GetMapping("/good")
public Mono<String> good() {
    return remoteCall();
}
~~~

Nếu mục tiêu thực sự là background job, thiết kế job queue và `202 Accepted` với job ID/status endpoint; không chỉ `subscribe()` rồi hy vọng background operation sẽ bền vững.

## 6. Vì sao blocking call làm hại cả hệ thống?

### 6.1. Event-loop starvation

Giả sử mỗi event-loop worker có nhiều connections đang chờ callback. Một handler chạy:

~~~java
Thread.sleep(1_000);
~~~

Trên event loop, thread đó không xử lý được read/write events hoặc callbacks khác trong khoảng sleep. Nếu nhiều requests cùng mắc lỗi này, event loops lần lượt bị chiếm. Trong logs, CPU usage có thể không cao nhưng latency p99 và timeouts tăng; đây là một dấu hiệu của **blocking wait**, không phải thiếu CPU.

Một loạt sự cố có thể xảy ra:
1. HTTP server nhận request.
2. Handler chặn event loop.
3. Các sockets khác không được phục vụ kịp.
4. Client/gateway timeout, retry tự động gửi thêm request.
5. Hàng đợi và số connections tăng.
6. Retry tiếp tục làm tình hình xấu đi dù downstream đã phục hồi.

Điều này là **mẫu failure**, không phải định luật mọi thread sleep đều gây outage; phụ thuộc concurrency, số loop, thời gian blocking, retry policy và tải.

### 6.2. Blocking API phổ biến

| API/operation | Có thể chặn? | Cách ứng xử |
| --- | --- | --- |
| `Thread.sleep` | Có | Không dùng trong request event loop |
| `Mono.block()`, `Flux.blockLast()` | Có | Không dùng trong reactive chain WebFlux |
| `Future.get()`, `CompletableFuture.join()` | Có nếu chưa hoàn thành | Compose futures/publishers không chờ thread |
| `RestTemplate`, HTTP clients sync | Có | Dùng `WebClient` non-blocking hoặc isolate boundedElastic |
| JDBC `DataSource`/`JdbcTemplate`/JPA | Có | Dùng R2DBC hoặc offload bounded pool |
| File I/O đồng bộ | Có thể | Streaming/async file API khi phù hợp hoặc offload |
| `InputStream.read()` | Có thể | Không đọc blocking stream lâu trên event loop |
| `synchronized`/lock contention | Có thể | Giảm lock/critical sections, tránh khóa dài |
| BCrypt/crypto/hash/compression lớn | CPU-heavy | Giữ callback ngắn, phân bổ CPU rõ; không lạm dụng event loop |
| JSON serialization rất lớn | CPU/memory nặng | Giới hạn payload, streaming/codec strategy |
| `System.out.println` hoặc logging synchronous quá nhiều | Có thể | Structured async logging, metrics và sampling |
| `WebClient.retrieve().bodyToMono(...)` | Non-blocking nếu connector phù hợp | Return/compose publisher, không thêm `block()` |
| R2DBC driver reactive | Thiết kế non-blocking | Chọn stack/driver đúng, kiểm actual behavior |

**Phân biệt I/O-blocking và CPU-bound:** Chuyển phép tính CPU nặng sang `boundedElastic` có thể giảm ảnh hưởng trực tiếp lên event loop nhưng không làm CPU work rẻ hơn; có thể làm quá tải scheduler và tăng context switches. Với CPU workload, dùng `Schedulers.parallel()` hoặc compute worker pool được đo/giới hạn, tùy độ dài/nhiệm vụ. Reactor `parallel()` không phải phép màu tăng thông lượng cho tác vụ vượt số CPU cores.

### 6.3. `.block()` có thể fail-fast hoặc âm thầm làm chậm

Project Reactor biết một số threads được đánh dấu **NonBlocking**. `block()`/`blockFirst()`/`blockLast()` trên các threads này có thể ném `IllegalStateException`, ví dụ thông điệp:

~~~text
block()/blockFirst()/blockLast() are blocking, which is not supported in thread ...
~~~

Không dựa vào thông điệp chính xác theo version. Nếu chạy trên một thread không được đánh dấu NonBlocking, `block()` **có thể không ném** nhưng vẫn chiếm thread và gây chậm. Vì vậy “không có IllegalStateException” **không chứng minh pipeline non-blocking**.

Trong Spring WebFlux handler, đừng chữa lỗi bằng cách đổi exception handler cho `IllegalStateException` và tiếp tục `block()`. Phải sửa nguyên nhân: compose publisher đúng hoặc isolate legacy blocking call trên worker phù hợp.

## 7. Phản ví dụ quan trọng: `Mono.just(blockingCall())` vẫn blocking

Giả sử `legacyService.find(id)` là JDBC/HTTP call đồng bộ.

**Sai:**

~~~java
@GetMapping("/bad/{id}")
public Mono<Product> bad(@PathVariable long id) {
    return Mono.just(legacyService.find(id));
}
~~~

`legacyService.find(id)` được gọi **trước** khi `Mono.just(...)` chạy, có thể ngay trên event-loop thread đang invoke controller. Mặc dù return type là Mono, block đã xảy ra.

**Cũng sai nếu chỉ thêm subscribeOn phía sau:**

~~~java
Mono.just(legacyService.find(id))
    .subscribeOn(Schedulers.boundedElastic());
~~~

`legacyService.find(id)` vẫn được thực thi eager ở thời điểm biểu thức đánh giá; subscribeOn không thể quay ngược thời gian để sửa lời gọi đã chạy.

**Đúng khi bắt buộc dùng blocking library:**

~~~java
Mono<Product> product = Mono.fromCallable(
        () -> legacyService.find(id))
    .subscribeOn(Schedulers.boundedElastic());
~~~

`Mono.fromCallable` hoãn việc thực hiện lambda đến subscription; `subscribeOn` bố trí việc subscribe/source trên bounded elastic worker. Vậy blocking call chiếm **worker phù hợp**, không chiếm event loop.

Ví dụ trên là fragment với `Product` và `legacyService` chưa được định nghĩa; app hoàn chỉnh ở mục 12. Việc offload không loại bỏ số threads cần cho blocking work; nó chỉ **cô lập** phần blocking khỏi I/O loops để server không bị "nghẹt thở" sớm.

### 7.1. `Mono.defer` và `Mono.fromCallable`

`Mono.defer(() -> legacyWrapper())` trì hoãn **việc dựng publisher** theo từng subscription. `Mono.fromCallable(() -> legacyService.find(id))` phù hợp với **một phép tính đồng bộ trả một kết quả**, có thể ném checked exception và trở thành onError.

Chỉ dùng `defer` mà không có scheduling vẫn có thể thực hiện blocking code trên thread subscription (có thể là event loop). Để isolate, vẫn cần `subscribeOn(Schedulers.boundedElastic())` hoặc scheduler tương đương.

### 7.2. Nếu Callable trả `null` thì sao?

`Mono.fromCallable` có thể complete **empty** khi callable trả null. Không nhầm điều đó với JSON null hay HTTP 404 tự động. Nếu không tìm thấy resource, nên ném typed exception/domain error hoặc dùng `switchIfEmpty(Mono.error(...))` với fallback rõ. Ứng dụng demo ném `ProductNotFoundException` để controller/advice biến thành 404.

## 8. Scheduler: không phải mọi operator tạo thread

Reactor `Scheduler` quản lý nơi thực thi việc đã được schedule. Nhiều operators như `map`, `filter`, `flatMap`, `doOnNext` **không mặc nhiên mở thread mới**. Chúng thường chạy trên thread phát signal tại thời điểm đó, trừ khi có asynchronous boundary/scheduler switch.

### 8.1. Những scheduler thường gặp

| Scheduler | Thiết kế chính | Điều cần tránh |
| --- | --- | --- |
| `Schedulers.immediate()` | Thực thi trên thread hiện tại | Không dùng để offload blocking |
| `Schedulers.single()` | Một worker dùng chung | Một task chặn làm trì hoãn các task khác |
| `Schedulers.parallel()` | Thread pool cố định cho tác vụ CPU-bound ngắn | Không gửi JDBC/sleep vào pool này |
| `Schedulers.boundedElastic()` | Worker capacity giới hạn cho blocking I/O legacy | Không coi là pool vô hạn, vẫn có queue/rejection |
| `Schedulers.newBoundedElastic(...)` | Tạo bounded pool riêng, dễ isolate dependency | Phải đặt giới hạn hợp lý và dispose khi ngừng |
| Event-loop threads của Reactor Netty | Network I/O/callbacks | Không chạy blocking code hoặc phép tính kéo dài |

Default boundedElastic trong Reactor 3.6.x có giới hạn thread/queue, nhưng **đừng copy một con số default từ một version khác làm contract**; có thể tùy chỉnh system properties và môi trường. Một số Reactor releases/JDKs hỗ trợ chiến lược virtual-thread cho bounded elastic khi bật cấu hình tương ứng. Java 17 trong demo này sử dụng platform threads truyền thống; **không tự giả định virtual threads đang bật**.

### 8.2. `subscribeOn`: điều phối subscription/source

~~~java
Mono<String> p = Mono.fromCallable(() -> {
            // Blocking operation cần worker riêng.
            return legacyRead();
        })
        .subscribeOn(Schedulers.boundedElastic())
        .map(String::toUpperCase);
~~~

`legacyRead()` là hàm giả định chưa định nghĩa. `subscribeOn` tác động tới quá trình subscription/source upstream. Thường đặt **ngay sau `fromCallable`** để ý đồ rõ ràng. Điều đó không có nghĩa nó tự subscribe; publisher chỉ thực thi khi client/WebFlux subscribe.

Một pipeline có thể chứa nhiều `subscribeOn` nhưng việc thêm liên tiếp nhiều subscribeOn không phải cách "chuyển thread qua lại" dễ hiểu: một `subscribeOn` gần source thường quyết định scheduling của source, tùy structure/operators. Tránh sử dụng chồng chéo khi không cần thiết.

### 8.3. `publishOn`: thay thread cho các bước phía sau

~~~java
Mono<String> p = Mono.just("a")
        .publishOn(Schedulers.parallel())
        .map(value -> value.toUpperCase());
~~~

`publishOn` dùng scheduler cho phần downstream sau operator cho tới khi có scheduler boundary khác. Nó thích hợp để chuyển một phần pipeline sang compute worker.

**Cẩn thận với blocking source:**

~~~java
Mono.fromCallable(() -> legacyRead())
    .publishOn(Schedulers.boundedElastic())
    .map(String::toUpperCase);
~~~

Nếu không có upstream scheduling khác, `fromCallable` có thể **vẫn thực thi trên subscription thread** trước khi publishOn chuyển tín hiệu downstream. Do đó mẫu offload blocking source chuẩn là **`Mono.fromCallable(...).subscribeOn(boundedElastic)`**.

### 8.4. Thread switch là chi phí, không phải thành tựu

Mỗi scheduler boundary có chi phí queueing, context switches, propagation context và latency. Không thêm `publishOn(Schedulers.parallel())` ở mọi toán tử "cho an toàn". Hãy xác định bước nào thực sự blocking/CPU-heavy, sau đó bố trí một boundary có chủ đích, đo hiệu năng và giám sát queue.

## 9. Vì sao `boundedElastic` có giới hạn, và tại sao điều đó tốt?

Một bounded scheduler giúp cô lập những calls không thể chuyển sang reactive ngay, nhưng những calls ấy vẫn sử dụng workers:
- Nếu dependency thường phản hồi sau 50 ms, một số workers có thể phục vụ nhiều requests theo thời gian.
- Nếu dependency treo 30 giây, workers ở trạng thái block lâu, request tiếp theo có thể phải đợi queue.
- Khi queue/pool chạm ngưỡng, schedule có thể bị từ chối (ví dụ Reactor `RejectedExecutionException`), không phải tự tạo vô hạn threads.

**Giới hạn là cơ chế bảo vệ tài nguyên**, không phải lỗi thiết kế. Khi overload, có thể trả status phù hợp (thường 503 với application policy), áp dụng admission control, circuit breaker, rate limit và retry có backoff/jitter giới hạn.

### 9.1. Dedicated bounded scheduler

Thay vì mọi thư viện legacy chia sẻ global boundedElastic, ứng dụng có thể tạo scheduler riêng:

~~~java
@Bean(name = "legacyScheduler", destroyMethod = "dispose")
Scheduler legacyScheduler() {
    return Schedulers.newBoundedElastic(4, 32, "legacy-io");
}
~~~

Đây là fragment thuộc class `@Configuration`, có imports ở ví dụ runnable bên dưới. Ý nghĩa:
- Tối đa 4 workers (theo cài đặt helper này).
- Queue bound là 32 **mỗi backing thread** theo Reactor semantics của factory; đừng coi đây chắc chắn là 32 requests tổng toàn app.
- Prefix thread name `legacy-io` hỗ trợ diagnostics; tên cụ thể không phải security hoặc business contract.
- Khi Spring context shutdown, gọi `dispose` để dọn scheduler resources.

Số `4` và `32` **chỉ dành cho demo**, không phải recommendation production. Trong thực tế cần dựa trên connection pool, service latency, concurrency, CPU, memory, expected load và timeout của upstream.

### 9.2. Không vô tình vượt connection pool

Nếu scheduler cho phép 100 blocking operations nhưng JDBC connection pool chỉ có 10 connections, nhiều workers sẽ **ngồi chờ connection** và lấp queue. Điều chỉnh thread/connection/request admission cùng nhau. Với R2DBC, giới hạn connection pool và số in-flight operations vẫn quan trọng — không có nghĩa non-blocking là unlimited concurrency.

## 10. WebClient: tận dụng non-blocking HTTP thay vì offload mọi call

Nếu downstream hỗ trợ HTTP, `WebClient` có thể xây reactive request mà không cần worker block:

~~~java
public Mono<Product> fetch(long id) {
    return webClient.get()
            .uri("/products/{id}", id)
            .retrieve()
            .bodyToMono(Product.class)
            .timeout(Duration.ofSeconds(2));
}
~~~

Đây là fragment của một class có `WebClient webClient` và record/class `Product` được cấu hình sẵn; nó **không phải project hoàn chỉnh** vì không cung cấp downstream server. Với Reactor Netty connector, HTTP I/O được xử lý non-blocking, và publisher được WebFlux subscribe khi controller return.

**Không làm thế này:**

~~~java
Product product = webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(Product.class)
        .block();
~~~

`block()` biến lời gọi thành đồng bộ, có thể throw trên non-blocking thread hoặc gây starvation. Khi client là WebFlux, hãy return `Mono<Product>` hoặc compose bằng `flatMap`/`zipWhen`.

### 10.1. Chạy nhiều request HTTP I/O độc lập

Nếu cần hai remote responses:

~~~java
Mono<Product> a = productClient.fetch(1);
Mono<Product> b = productClient.fetch(2);

return Mono.zip(a, b)
        .map(tuple -> new ProductPair(tuple.getT1(), tuple.getT2()));
~~~

Đây là fragment, `ProductPair` và `productClient` cần khai báo riêng. Hai publishers có thể có I/O in flight đồng thời; không cần gọi `block()` để chờ từng item theo thứ tự. Tuy nhiên `zip` hoàn thành empty nếu một nguồn empty theo Reactor semantics; muốn xử lý trường hợp không tìm thấy cần `switchIfEmpty`/domain exception cho từng nguồn trước khi zip.

### 10.2. Timeout không tự dừng mọi tác vụ legacy

`timeout(Duration.ofSeconds(2))` phát signal lỗi và cancel upstream khi hết thời gian. Với WebClient non-blocking, cancellation có thể huỷ request/giải phóng resources theo connector. Với `fromCallable` đang chạy code blocking không hỗ trợ interruption, timeout **không bảo đảm** tác vụ/SQL/network call đó dừng ngay. Vì vậy timeout ở từng driver/HTTP client/database vẫn cần thiết.

### 10.3. Reactive data access: R2DBC khác JDBC

R2DBC thiết kế cho reactive database access; JDBC/JPA là các API đồng bộ trên caller thread trong trường hợp truyền thống. Nếu toàn hệ thống chủ yếu là JDBC, có thể:
- Giữ Spring MVC đồng bộ vì đó là một kiến trúc phù hợp.
- Với WebFlux bắt buộc, offload blocking JDBC qua bounded worker và đặt concurrency/connection limits.
- Nếu có yêu cầu và driver hỗ trợ, cân nhắc chuyển riêng data access sang R2DBC theo kế hoạch migration.

Đừng gắn `@Transactional` kiểu imperative/JPA rồi giả định transaction context tự di chuyển qua mọi Scheduler: imperative transaction thường thread-bound; reactive transaction dùng `Reactor Context` và `ReactiveTransactionManager` theo stack phù hợp.

## 11. Phân biệt `Thread.sleep`, blocking I/O và CPU-heavy work

### 11.1. Blocking wait

~~~java
Thread.sleep(2_000);
~~~

Tiêu tốn rất ít CPU nhưng giữ thread. Đặt trên event loop là đặc biệt xấu: loop không quay lại phục vụ sockets/callbacks. Đặt trên bounded worker vẫn sử dụng một worker, gây queue khi nhiều request cùng chờ.

Nếu mục đích chỉ là **đợi một khoảng thời gian** trong pipeline, dùng non-blocking timer:

~~~java
Mono<String> delayed = Mono.delay(Duration.ofSeconds(2))
        .map(ignored -> "done");
~~~

`Mono.delay` không dùng `Thread.sleep` trên event loop; nó dùng scheduler/timer tương ứng. Nhưng đây chỉ là mô phỏng delay, **không thay** một mạng/DB request có side effects.

### 11.2. CPU-bound work

~~~java
long value = expensiveHash(payload);
~~~

Đây là fragment với hai biến chưa khai báo. Dù không gọi bất kỳ I/O nào, nếu `expensiveHash` mất 500 ms trên event loop, nó vẫn khiến loop bận và chậm xử lý sockets. Có thể tách sang compute pool hoặc đưa sang job queue nếu việc nặng; bảo đảm không tạo hàng trăm operations lớn tranh CPU. Dùng scheduler đúng workload: `parallel`/dedicated bounded compute worker thường khác với `boundedElastic` vốn hướng tới blocking I/O.

### 11.3. Synchronous locks

Một callback lấy monitor/lock bị các threads khác giữ lâu cũng là blocking. Một synchronized block rất ngắn không mặc định là lỗi, nhưng lock cạnh tranh dưới tải cao và các call chặn trong lock có thể tạo tail latency nghiêm trọng. Ưu tiên immutable data, concurrent structures và giảm critical section; không chuyển mọi lock sang Reactor context mà không có thiết kế thread-safety.

### 11.4. Logging cũng có thể gây chặn

Ghi debug log quá dày, formatter nặng, synchronous file/network appenders hoặc ghi stdout trong vòng lặp lớn có thể làm chậm event loop. Với production dùng structured logs, bounded asynchronous appenders phù hợp, sampling, redaction và metrics. Tránh log raw Authorization/cookie/session IDs hoặc dữ liệu riêng tư chỉ để đo thread.

## 12. Ứng dụng hoàn chỉnh: Java 17 + Spring Boot 3.3.5 + scheduler cô lập

Ví dụ có:
- `GET /api/health`: trả `Mono` nhanh, không blocking.
- `GET /api/products/{id}`: giả lập thư viện legacy blocking bằng `Thread.sleep(30)` trong service. Controller dùng `Mono.fromCallable(...).subscribeOn(legacyScheduler)` để không chặn Reactor Netty loop.
- Nếu không có product: typed exception được `@RestControllerAdvice` chuyển thành 404.
- Nếu timeout: `TimeoutException` được advice chuyển thành 503.
- Mock HTTP integration dùng `WebTestClient` với embedded Reactor Netty, kiểm cả success/404.
- Test scheduler xác minh công việc chạy trên worker có prefix khác event loop.

`Thread.sleep(30)` **chỉ để mô phỏng blocking code trong demo**; đừng đưa sleep vào production và cũng đừng cho rằng offload giải quyết mọi vấn đề tải.

~~~text
webflux-eventloop-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/com/example/loopdemo/
    │   ├── LoopDemoApplication.java
    │   ├── config/SchedulerConfig.java
    │   ├── domain/Product.java
    │   ├── domain/ProductNotFoundException.java
    │   ├── domain/LegacyProductGateway.java
    │   └── web/
    │       ├── ProductController.java
    │       └── ApiErrorHandler.java
    └── test/java/com/example/loopdemo/
        └── ProductControllerIntegrationTest.java
~~~

### 12.1. Gradle

`settings.gradle`:

~~~groovy
rootProject.name = 'webflux-eventloop-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

**Không thêm `spring-boot-starter-web`**. `starter-webflux` có Reactor/Spring WebFlux/Reactor Netty, `starter-test` có JUnit và Spring Boot testing, `reactor-test` cung cấp StepVerifier. Boot BOM quản lý phiên bản Reactor thống nhất. Khi build thực tế nên dùng Gradle wrapper tương thích Boot 3.3/Java 17.

### 12.2. Main application

`src/main/java/com/example/loopdemo/LoopDemoApplication.java`:

~~~java
package com.example.loopdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LoopDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(LoopDemoApplication.class, args);
    }
}
~~~

### 12.3. Bounded scheduler riêng cho legacy blocking

`src/main/java/com/example/loopdemo/config/SchedulerConfig.java`:

~~~java
package com.example.loopdemo.config;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@Configuration
public class SchedulerConfig {

    @Bean(name = "legacyScheduler", destroyMethod = "dispose")
    public Scheduler legacyScheduler() {
        return Schedulers.newBoundedElastic(4, 32, "legacy-io");
    }
}
~~~

Spring quản lý scheduler bean và gọi `dispose` khi shutdown. Đặt scheduler riêng làm rõ boundary và dễ đo cô lập thư viện legacy. Số workers và queue chỉ mang tính minh họa; ứng dụng có thể dùng `Schedulers.boundedElastic()` chia sẻ nếu không cần isolation.

### 12.4. Domain types

`src/main/java/com/example/loopdemo/domain/Product.java`:

~~~java
package com.example.loopdemo.domain;

public record Product(long id, String title) {}
~~~

`src/main/java/com/example/loopdemo/domain/ProductNotFoundException.java`:

~~~java
package com.example.loopdemo.domain;

public class ProductNotFoundException extends RuntimeException {

    public ProductNotFoundException(long id) {
        super("Product not found: " + id);
    }
}
~~~

### 12.5. Giả lập thư viện legacy blocking

`src/main/java/com/example/loopdemo/domain/LegacyProductGateway.java`:

~~~java
package com.example.loopdemo.domain;

import java.util.Map;
import org.springframework.stereotype.Service;

@Service
public class LegacyProductGateway {

    private final Map<Long, Product> products = Map.of(
            1L, new Product(1L, "Project Reactor"),
            2L, new Product(2L, "Spring WebFlux"));

    public Product find(long id) throws InterruptedException {
        // Demo: thay cho một JDBC/HTTP client synchronous call.
        Thread.sleep(30L);

        Product product = products.get(id);
        if (product == null) {
            throw new ProductNotFoundException(id);
        }
        return product;
    }
}
~~~

`find` là **blocking** do sleep. Nếu gọi thẳng từ Netty event loop sẽ giữ loop ít nhất khoảng 30 ms cộng phần lookup. Đưa nó vào dedicated scheduler chỉ giúp **không chiếm Netty loop**, vẫn tốn một worker. `Map.of` dùng fixture; không chứa dữ liệu người dùng, không phụ thuộc external network và kết quả test deterministic về body.

### 12.6. WebFlux controller đúng cơ chế

`src/main/java/com/example/loopdemo/web/ProductController.java`:

~~~java
package com.example.loopdemo.web;

import com.example.loopdemo.domain.LegacyProductGateway;
import com.example.loopdemo.domain.Product;
import java.time.Duration;
import java.util.Map;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;

@RestController
@RequestMapping("/api")
public class ProductController {

    private final LegacyProductGateway legacy;
    private final Scheduler scheduler;

    public ProductController(
            LegacyProductGateway legacy,
            @Qualifier("legacyScheduler") Scheduler scheduler) {
        this.legacy = legacy;
        this.scheduler = scheduler;
    }

    @GetMapping("/health")
    public Mono<Map<String, String>> health() {
        return Mono.just(Map.of("status", "UP"));
    }

    @GetMapping("/products/{id}")
    public Mono<Product> product(@PathVariable("id") long id) {
        return Mono.fromCallable(() -> legacy.find(id))
                .subscribeOn(scheduler)
                .timeout(Duration.ofSeconds(2));
    }
}
~~~

**Giải thích theo thứ tự:**
1. Khi GET tới `/api/products/{id}`, controller trả **một Mono publisher** nhanh chóng, chưa gọi `legacy.find` tại chỗ.
2. `Mono.fromCallable` giữ công việc legacy ở trạng thái lazy tới subscription.
3. `subscribeOn(scheduler)` chọn bounded worker cho subscription/source; `Thread.sleep` sẽ chạy trên worker đó, không phải request event loop.
4. `timeout(2s)` giới hạn thời gian chờ của publisher; một tác vụ blocking không support interruption vẫn có thể tiếp tục sau khi timeout.
5. Khi worker trả `Product`, WebFlux serialize JSON như response HTTP.
6. Nếu `legacy.find` ném `ProductNotFoundException`, lỗi đi vào reactive `onError` signal; WebFlux error handling chọn advice bên dưới.

Không cần viết `subscribe()` thủ công trong controller. Không có blocking trong `health()`, nên route đó không cần dedicated scheduler. Khi có CPU-heavy JSON serialization hoặc complex response transforms, cần đánh giá riêng thay vì đưa cả controller vào boundedElastic mặc định.

### 12.7. API error handling

`src/main/java/com/example/loopdemo/web/ApiErrorHandler.java`:

~~~java
package com.example.loopdemo.web;

import com.example.loopdemo.domain.ProductNotFoundException;
import java.util.concurrent.TimeoutException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<ProblemDetail> missing(
            ProductNotFoundException exception) {

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.NOT_FOUND);
        problem.setTitle("Product not found");
        problem.setDetail("No product has that id.");
        problem.setProperty("code", "PRODUCT_NOT_FOUND");

        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }

    @ExceptionHandler(TimeoutException.class)
    public ResponseEntity<ProblemDetail> timeout(
            TimeoutException exception) {

        ProblemDetail problem =
                ProblemDetail.forStatus(HttpStatus.SERVICE_UNAVAILABLE);
        problem.setTitle("Product service timed out");
        problem.setDetail("The product could not be fetched in time.");
        problem.setProperty("code", "PRODUCT_TIMEOUT");

        return ResponseEntity.status(
                HttpStatus.SERVICE_UNAVAILABLE).body(problem);
    }
}
~~~

`ProblemDetail` có semantics RFC 9457; Spring WebFlux + Jackson có thể serialize extension field `code`. Advice không trả raw exception messages; đó là lựa chọn an toàn vì thực tế exception có thể chứa SQL, URLs nội bộ hoặc secrets.

**Giới hạn:** Demo chỉ mapping hai error types; executor rejection, malformed path ID, client disconnect, unexpected runtime error và HTTP gateway timeout cần được xử lý/test theo chính sách production. Không gom mọi `Throwable` thành 200/503 và che bug nội bộ. HTTP 504 chỉ phù hợp khi thành phần đóng vai gateway/proxy theo semantics; route application demo cố ý chọn 503 khi dependency timeout.

## 13. WebTestClient và StepVerifier: kiểm đúng WebFlux stack

Trong một ứng dụng WebFlux, `WebTestClient` là cách test HTTP reactive tự nhiên. Demo dùng embedded server với port ngẫu nhiên để kiểm thêm network/Netty; nó không phải MockMvc dành cho Servlet MVC.

`src/test/java/com/example/loopdemo/ProductControllerIntegrationTest.java`:

~~~java
package com.example.loopdemo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.test.StepVerifier;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class ProductControllerIntegrationTest {

    @Autowired
    WebTestClient client;

    @Autowired
    @Qualifier("legacyScheduler")
    Scheduler scheduler;

    @Test
    void healthIsReactiveAndAvailable() {
        client.get().uri("/api/health")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("UP");
    }

    @Test
    void legacyProductStillReturnsJson() {
        client.get().uri("/api/products/1")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(1)
                .jsonPath("$.title").isEqualTo("Project Reactor");
    }

    @Test
    void missingProductBecomes404ProblemDetail() {
        client.get().uri("/api/products/999")
                .exchange()
                .expectStatus().isNotFound()
                .expectBody()
                .jsonPath("$.code").isEqualTo("PRODUCT_NOT_FOUND")
                .jsonPath("$.status").isEqualTo(404);
    }

    @Test
    void dedicatedSchedulerActuallyOffloadsItsSource() {
        Mono<String> workThread =
                Mono.fromCallable(() ->
                        Thread.currentThread().getName())
                    .subscribeOn(scheduler);

        StepVerifier.create(workThread)
                .expectNextMatches(name -> name.startsWith("legacy-io-"))
                .verifyComplete();
    }
}
~~~

**Phân biệt điều test chứng minh:**
- Ba `WebTestClient` tests gửi HTTP đến application và kiểm status/body.
- Test StepVerifier chứng minh **nguồn Mono khi subscribeOn dedicated scheduler** chạy trên worker có prefix do ta đặt. Nó không đo request concurrency dưới tải, nhưng xác minh scheduler hoạt động.
- Demo cố ý không assert tên Reactor Netty event-loop threads vì naming có thể đổi theo runtime.
- Test không dựa vào timing 30 ms chính xác vì `Thread.sleep`/CI scheduler có thể lệch; response test chờ body thay vì tự ước lượng thời gian cố định.
- Không khẳng định chỉ bốn tests có thể chứng minh system chịu 10.000 concurrent requests. Cần load test và scheduler/Netty metrics khi production.

Chạy trong project có Gradle wrapper và Java 17:

~~~bash
./gradlew test
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
.\gradlew.bat bootRun
~~~

Không chạy `bootRun` cùng terminal sau khi `test` chưa hoàn tất. Trong server đang chạy, gọi:

~~~bash
curl -i 'http://localhost:8080/api/health'
curl -i 'http://localhost:8080/api/products/1'
curl -i 'http://localhost:8080/api/products/999'
~~~

Kết quả chính:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"status":"UP"}
~~~

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":1,"title":"Project Reactor"}
~~~

~~~http
HTTP/1.1 404 Not Found
Content-Type: application/problem+json

{"type":"about:blank","title":"Product not found","status":404,"detail":"No product has that id.","code":"PRODUCT_NOT_FOUND"}
~~~

Headers bổ sung, thứ tự header, JSON field order và `instance` có thể khác theo serializer/framework, nhưng status/essential fields phải khớp. Cả ba calls là những HTTP requests độc lập; không phải một request tự động chuyển threads theo số lượng headers.

## 14. Anti-pattern đối chiếu trực tiếp với ví dụ đúng

### 14.1. Sai: tạo Mono sau khi blocking đã chạy

~~~java
return Mono.just(legacy.find(id));
~~~

Lời gọi blocking đã chạy trước khi Mono được dựng. Sửa:

~~~java
return Mono.fromCallable(() -> legacy.find(id))
        .subscribeOn(legacyScheduler);
~~~

### 14.2. Sai: gọi `block()` trên WebClient trong handler

~~~java
return Mono.just(
        webClient.get().uri("/x").retrieve()
                .bodyToMono(String.class).block());
~~~

Nếu API có thể hoàn toàn non-blocking:

~~~java
return webClient.get().uri("/x")
        .retrieve().bodyToMono(String.class);
~~~

### 14.3. Sai: dùng `publishOn` sai vị trí

~~~java
return Mono.fromCallable(() -> legacy.find(id))
        .publishOn(legacyScheduler);
~~~

Source vẫn có thể chạy ngay trên subscriber/event-loop thread. Sửa bằng `subscribeOn` ngay sau source, như code runnable.

### 14.4. Sai: `flatMap` có lambda đồng bộ chậm

~~~java
return ids.flatMap(id -> {
    Product p = legacy.find(id);  // chạy đồng bộ trong lambda
    return Mono.just(p);
});
~~~

`ids` ở đây là Flux/Publisher fragment. Dù tên operator là flatMap, lambda đã block ngay khi upstream phát. Cần:

~~~java
return ids.flatMap(
        id -> Mono.fromCallable(() -> legacy.find(id))
                .subscribeOn(legacyScheduler),
        8);
~~~

`8` giới hạn concurrency ở tầng flatMap trong ví dụ. Khi cần giữ thứ tự, xét `flatMapSequential` hoặc `concatMap` với trade-offs. **Không để số in-flight requests vượt năng lực database/legacy client**; limit concurrency và scheduler queue phải tương thích.

### 14.5. Sai: dùng `doOnNext` cho blocking side-effect

~~~java
return products.doOnNext(product ->
        legacyAuditRepository.save(product));
~~~

`doOnNext` callback chạy đồng bộ trên thread phát signal, không offload. Nếu audit cần tham gia kết quả:

~~~java
return products.concatMap(product ->
        Mono.fromCallable(() -> {
            legacyAuditRepository.save(product);
            return product;
        }).subscribeOn(legacyScheduler));
~~~

`products`, `legacyAuditRepository` là fragments chưa khai báo. Nếu audit là event bền vững/tách khỏi HTTP response, dùng outbox/queue và thiết kế reliability riêng. Không chỉ `subscribe()` ở `doOnNext` vì sẽ mất retry/error ownership.

## 15. Backpressure và overload không giống scheduling

### 15.1. `request(n)` không giới hạn mọi nguồn bên ngoài

Reactive Streams cho phép Subscriber yêu cầu số item tối đa một thời điểm. Với cold Flux phát từ một nguồn do framework điều khiển, upstream có thể tôn trọng demand.

Nhưng HTTP client connections, file watchers, Kafka brokers, GUI/events hay một external service không phải lúc nào dừng ngay được khi downstream giảm demand. Nếu event rate vượt tốc độ xử lý, cần bounded buffers, concurrency limits, backpressure strategy phù hợp, dropping/error policy hoặc admission control. Không dùng buffer vô hạn trong pipeline để "giữ đủ dữ liệu".

### 15.2. `flatMap` có concurrency và prefetch

Một pipeline:

~~~java
Flux.fromIterable(ids)
    .flatMap(id -> productClient.fetch(id), 8);
~~~

giới hạn số inner publishers được subscribed đồng thời theo tham số concurrency. `ids` và `productClient` là fragments. Điều này khác với `Schedulers.boundedElastic`: flatMap giới hạn **lượng công việc đang in flight**, scheduler giới hạn **tài nguyên thực thi**. Khi dùng legacy DB, cả hai có thể cần.

### 15.3. Reactive không loại bỏ connection pools

Non-blocking WebClient vẫn cần connection pool, DNS/TLS resources, limits, read/write timeouts và memory budgets. R2DBC vẫn có pool/concurrent transactions. Nếu downstream chỉ cho phép 20 concurrent calls, application phải kiểm giới hạn đó ngay cả khi event loop có thể quản lý hàng nghìn sockets.

### 15.4. Retry gây snowball nếu không giới hạn

Không viết `retry()` vô hạn cho endpoint đã chậm vì saturation. Retry with exponential backoff/jitter, deadline, idempotency và circuit breakers chỉ nên áp dụng cho transient failures có định nghĩa rõ. Không retry một HTTP POST có side effects mù quáng. Một thread model tốt không cứu được retry storm do architecture sai.

## 16. Timeout và cancellation trong reactive pipeline

### 16.1. `timeout` là deadline cho publisher, không phải global cleanup

~~~java
return legacyPublisher
        .timeout(Duration.ofSeconds(2));
~~~

Khi quá thời gian, `timeout` có thể phát `TimeoutException` và cancel source. Nhưng nếu source đang chặn trong native/JDBC driver không phản hồi interruption, thread vẫn có thể bị giữ. Cần driver-side timeout, database statement timeout, HTTP response timeout và cleanup ở từng tầng.

### 16.2. Hủy request không đồng nghĩa undo transaction

Client đóng tab hoặc hủy subscription có thể khiến HTTP exchange không cần response nữa. Nhưng:
- Một business side effect ở DB đã commit không tự rollback vì subscriber cancel.
- Blocking call đang chạy có thể tiếp tục đến khi driver trả hoặc hết timeout.
- Retry/cancel có thể tạo trạng thái "không biết operation đã thành công chưa".
- Với commands/transactions, cần idempotency keys, transaction boundaries và audit chứ không chỉ rely vào Reactor cancellation.

### 16.3. Error handling operator

~~~java
return productClient.fetch(id)
        .timeout(Duration.ofSeconds(2))
        .onErrorResume(TimeoutException.class,
                ex -> Mono.error(
                        new UpstreamUnavailableException()));
~~~

Fragment có `UpstreamUnavailableException` tự định nghĩa. `onErrorResume` quyết định fallback/error ở reactive chain, nhưng response HTTP 503/504/500 phụ thuộc global WebFlux exception handler, `@RestControllerAdvice` hoặc custom error mapping. Đừng bắt mọi lỗi và trả một default "empty product" vì có thể che dữ liệu sai và lỗi bảo mật.

## 17. WebFlux threading, SecurityContext và Reactor Context

### 17.1. ThreadLocal không an toàn làm định danh logical request

Ở Servlet MVC đồng bộ, nhiều code quen dùng `ThreadLocal` hoặc MDC để giữ user/trace trên thread request. Trong reactive pipeline, callbacks có thể chạy trên event loop, boundedElastic, parallel scheduler hoặc trên thread của asynchronous source. Một logical request **không gắn vĩnh viễn với một Java thread**.

Ví dụ anti-pattern:

~~~java
String user = currentUserThreadLocal.get();
return asyncCall.map(result -> useForUser(user, result));
~~~

Biến được đọc lúc dựng pipeline có thể đúng/sai tùy security integration và timing; nếu ThreadLocal đọc trong asynchronous callback, càng không thể assume nó chứa context cũ. Đừng tự dùng ThreadLocal để phân quyền ở mọi reactive callback.

### 17.2. Reactor `Context`

Reactor cung cấp `Context` để gắn metadata theo subscription, không phụ thuộc identity của worker thread. Ví dụ runnable độc lập trong Java fragment:

~~~java
Mono<String> greeting =
        Mono.deferContextual(ctx ->
                Mono.just("hello " + ctx.get("tenant")))
            .contextWrite(context ->
                context.put("tenant", "demo"));

greeting.subscribe(System.out::println);
~~~

Đây là fragment có imports Reactor `Mono`; stdout khi subscribe:

~~~text
hello demo
~~~

Trong production, tenant phải được lấy từ **authentication/authorization đã xác minh**, không từ request header tùy ý. Context keys/string demo không phải schema mặc định của Spring Security; khi dùng Spring Security reactive, `ReactiveSecurityContextHolder` khai thác Reactor Context để truy cập security identity.

### 17.3. MDC/tracing propagation

MDC của SLF4J thường dựa trên ThreadLocal, nên khi `publishOn` chuyển threads hoặc callback I/O chạy thread khác, MDC fields có thể mất hoặc leak giữa connections nếu quản lý sai. Sử dụng integration với Micrometer Context Propagation, Reactor context-propagation hooks hoặc tracing libraries phù hợp version; tránh tự copy raw ThreadLocal vào global static fields. Luôn clear khi phục vụ trên pooled thread.

### 17.4. Reactive transaction boundaries

Với R2DBC, `ReactiveTransactionManager` và `TransactionalOperator` gắn transactional state theo Reactor Context phù hợp. Với JDBC/JPA `PlatformTransactionManager`, transaction thường thread-bound; việc chuyển scheduler qua subscribeOn/publishOn **không tự giữ nguyên** transaction của một imperative controller/service method. Offload blocking repository calls cần ranh giới transactional thích hợp ngay trong worker được Spring proxy quản lý.

## 18. Debugging event-loop starvation bằng dữ liệu

### 18.1. Những triệu chứng đáng chú ý

- p95/p99 latency tăng trong khi CPU không nhất thiết tăng tương ứng.
- Nhiều request nhỏ và health checks cũng chậm dù DB route riêng đang lỗi.
- Reactor Netty I/O loop có stack traces đứng ở `Thread.sleep`, socket read blocking, JDBC calls hoặc lock.
- WebClient timeouts xuất hiện đồng thời với HTTP server latency.
- Bounded scheduler active workers/queue tăng tới giới hạn; task scheduling rejection.
- Retries từ client/gateway tăng và connections bị giữ lâu.
- Một phần requests rất nhanh, phần khác bị đợi lâu theo phân phối callback/event loop.

Những dấu hiệu trên cần được đối chiếu bằng tracing/profiling; không kết luận một cách chắc chắn chỉ từ metric duy nhất.

### 18.2. Thread dump

Một thread dump ở thời điểm incident có thể chỉ ra:
- Thread `reactor-http-nio-*` nằm trong `Thread.sleep` hoặc JDBC call.
- Thread `legacy-io-*` đang đợi DB theo thiết kế isolation.
- Threads đang tranh lock hoặc ở trạng thái WAITING/BLOCKED.
- Các Netty event loops nhàn rỗi, nhưng connection pool bottleneck có thể nằm nơi khác.

Đọc nhiều dumps trong một khoảng có ý nghĩa thay vì một snapshot; ghi chú stack traces có thể chứa internal paths/identifiers và xử lý theo chính sách bảo mật.

### 18.3. Reactor `Schedulers.isInNonBlockingThread()`

Reactor có API kiểm thread hiện tại có được đánh dấu NonBlocking không:

~~~java
boolean markedNonBlocking =
        Schedulers.isInNonBlockingThread();
~~~

Một callback chạy trên Reactor Netty event loop thường cho kết quả true; nhưng API này **không xác định mọi chỗ blocking về mặt nghiệp vụ**. False chỉ nói thread không mang marker phù hợp, không phải "được phép block vô hạn". Không dùng kết quả boolean để thay latency/throughput measurements.

### 18.4. BlockHound khi phù hợp

**BlockHound** là công cụ bên ngoài có thể instrument JVM để phát hiện một số lời gọi blocking trên threads không được phép blocking. Có thể tích hợp trong testing/diagnostics khi runtime và Java version tương thích. Nó không phát hiện tất cả loại blocking hoặc làm chuẩn đoán production miễn phí; một số JDK/release cần JVM flags và integration cụ thể. Không thêm `BlockHound.install()` trực tiếp trong demo Boot 3 ở trên khi chưa xác minh compatibility và startup behavior.

BlockHound phát hiện `Thread.sleep` trên Reactor nonblocking threads là tình huống minh họa, nhưng **nó không thay load test, source review, thread dumps hoặc observability**.

### 18.5. Micrometer / Actuator metrics

Nếu triển khai Spring Boot Actuator/Micrometer phù hợp có thể quan sát:
- HTTP server request latency/status distribution.
- Reactor Netty connection pools và event-loop behaviors qua metrics được bật.
- Scheduler active/queued/rejected tasks nếu được instrument.
- WebClient client latency, downstream timeouts, connection pending acquires.
- CPU usage, heap, GC, thread states.
- Business-specific deadlines/circuit breaker states.

Tên metric chính xác phụ thuộc phiên bản Boot/Micrometer/Reactor instrumentation và những binders được cấu hình; đừng bịa một metric name rồi giả định nó luôn có. Mục tiêu là **liên hệ event-loop stalls với loại code hoặc dependency**, không phải lập dashboard chỉ đo tổng QPS.

## 19. Tính toán năng lực và chọn kiến trúc

### 19.1. Khi nào WebFlux có lợi?

WebFlux thường đáng cân nhắc nếu:
- Có rất nhiều concurrent I/O requests, thời gian đợi remote service lớn.
- Các dependencies quan trọng có **non-blocking drivers/clients**.
- Đội ngũ hiểu reactive operators, backpressure, cancellation và context propagation.
- Cần streams, SSE/WebSocket hoặc reactive composition.
- Có khả năng test/monitor scheduling, queues và event-loop health.

### 19.2. Khi nào Spring MVC là lựa chọn tốt?

Spring MVC vẫn phù hợp khi:
- Dùng JPA/Hibernate/JDBC và synchronous integrations là chính.
- Hầu hết business logic là CRUD đơn giản, throughput trong khả năng thread pools.
- Team có kinh nghiệm imperative programming; chi phí debugging reactive lớn hơn lợi ích.
- Bottleneck thực sự nằm ở DB/index/network chứ không phải số request threads.
- Không muốn xây pipeline reactive một nửa rồi offload gần như mọi lời gọi blocking.

Một reactive wrapper bên ngoài một lõi blocking lớn không có cùng lợi ích với non-blocking end-to-end.

### 19.3. Ước lượng số blocking workers

Trong steady state, Little's Law cho một hệ ổn định nói rằng **số yêu cầu đang ở hệ thống ≈ arrival rate × thời gian nằm trong hệ thống**. Ví dụ workload blocking có 100 requests/giây, trung bình mỗi operation giữ worker 0,2 giây, số concurrent operations trung bình cần ~20 nếu giả định tất cả đều thành công và không có queueing bất thường.

Đây là phép ước lượng năng lực, **không phải số thread khuyến nghị cố định**; p99, burst, pool limits, memory và retries cần headroom và load test. Không đặt scheduler 20 workers chỉ vì trung bình tính được 20 mà bỏ qua tail latency.

### 19.4. Reactive pipeline cũng cần chính sách bảo mật

Return type `Mono` không thay:
- Authentication và authorization trên mỗi resource/tenant.
- CSRF nếu dùng cookie-based browser credentials.
- CORS khi cross-origin.
- Input validation, limits, JSON deserialization safeguards.
- Timeouts, retries, idempotency.
- Log redaction, SSRF protection trong outbound requests và dependency allowlists.

Không đọc raw `SecurityContextHolder` ThreadLocal từ scheduler callback để quyết định quyền dữ liệu; Spring Security reactive có các API context phù hợp.

## 20. Những nhầm lẫn nguy hiểm và cách sửa

| Nhầm lẫn / triệu chứng | Vì sao sai | Cách xử lý |
| --- | --- | --- |
| "Trả `Mono` là non-blocking" | `Mono.just(blockingCall())` vẫn thực thi eager | `fromCallable` + `subscribeOn` hoặc đổi non-blocking client |
| "`Thread.sleep` chỉ ảnh hưởng request đó" | Event loop phục vụ nhiều connections | Dùng non-blocking timer hoặc offload legacy call |
| "`publishOn` sau fromCallable offload source" | Source có thể chạy trước publishOn | Dùng `subscribeOn` ngay sau source |
| "`block()` không ném nên an toàn" | Có thể chỉ không chạy trên NonBlocking-marked thread | Không block trong reactive request chain |
| "Event loop = 1 thread/HTTP request" | Một loop multiplex nhiều connections | Hiểu event-driven callback scheduling |
| "WebFlux = WebClient" | WebClient có thể dùng ở Spring MVC | Kiểm Spring Boot application type/starter |
| "WebFlux luôn nhanh hơn MVC" | Reactive không rút ngắn tự động DB/network latency | Benchmark workload, chọn theo dependencies |
| "boundedElastic là pool vô hạn" | Có giới hạn workers/queues | Thiết lập capacity, monitor rejection |
| "Tăng Netty worker count chữa JDBC block" | Vẫn giữ mỗi loop khi JDBC chờ | Offload/change driver, giới hạn đồng thời |
| "`parallel()` xử lý JDBC tốt" | CPU pool có số threads nhỏ, blocking gây starvation | boundedElastic/dedicated blocking scheduler |
| "`timeout` dừng mọi SQL call" | Blocking driver có thể không hủy ngay | Statement/socket timeouts, cancellation-aware driver |
| "`flatMap` luôn chạy mỗi item trong thread mới" | flatMap là composition, không tự tạo scheduler | Explicit scheduler/concurrency as needed |
| "`Flux` ngăn RAM vô hạn" | Backpressure phụ thuộc producer/queues | Bounded buffers, admission, drop/error policy |
| "`subscribe()` trong controller là background job đáng tin" | Tách khỏi request lifecycle, lỗi khó quản lý | Return publisher hoặc durable queue |
| "ThreadLocal luôn đúng cho một request" | Callbacks đổi threads | Reactor Context, reactive security/tracing |
| "SecurityContext tự đi qua mọi worker" | Context propagation phụ thuộc tích hợp | Dùng ReactiveSecurityContextHolder/validated context |
| "`@Transactional` JDBC đi qua publishOn" | Imperative transaction thường thread-bound | Ranh giới transactional đúng hoặc R2DBC |
| "CPU không cao nghĩa WebFlux không bị nghẽn" | Blocking waits giữ loop mà ít CPU | Thread dumps, latency/queue metrics |
| "Một test HTTP 200 là đủ chứng minh concurrency" | Không đo starvation dưới tải | Load tests, thread dumps, scheduler metrics |

## 21. Quy trình khắc phục starvation trong production

1. **Đo hiện trạng**: p95/p99, error/timeout rates, connections, Netty event loops, scheduler queues, DB/HTTP client pools.
2. **Thu stack traces** ở thời điểm incident; tìm `sleep`, JDBC, blocking HTTP, Future.get, locks, excessive serialization.
3. **Xác định nơi code chạy**: event loop, boundedElastic, parallel, dedicated executor hay custom library worker.
4. **Phân loại workload**: I/O cần non-blocking; blocking unavoidable; CPU-bound; streaming/buffering.
5. **Loại bỏ blocking ngay trong handler** và các `map`/`flatMap`/`doOnNext` callbacks; chuyển non-blocking HTTP sang WebClient, DB sang R2DBC nếu khả thi.
6. **Cô lập legacy calls** bằng `fromCallable().subscribeOn(dedicatedBoundedScheduler)`, giữ concurrency hợp lý.
7. **Gắn timeout ở dependency** và end-to-end; phân biệt cancellation signal với driver thực sự dừng.
8. **Giới hạn tải** bằng flatMap concurrency, semaphore/connection pool, rate limit, circuit breaker và bounded queues.
9. **Tránh retry storm**; dùng retry có backoff, idempotency và giới hạn số lần.
10. **Giữ context bảo mật/tracing** qua Reactor Context và approved propagation mechanism.
11. **Kiểm bằng WebTestClient/StepVerifier** các trường hợp success, not found, timeout, cancellation nếu test được deterministic.
12. **Load-test** trên staging với concurrency và payload thực tế; quan sát scheduler rejection và event-loop latency.
13. **Đánh giá lại chọn MVC hay WebFlux** nếu phần lớn dependencies vẫn blocking và reactive maintenance cost lớn.
14. **Theo dõi sau thay đổi**: giảm p99 không làm tăng error/queue time ở tầng khác.
15. **Giữ tài liệu vận hành** về scheduler ownership, dependency budgets, thread naming và alert thresholds.

### Câu hỏi tự kiểm tra

**1.** Vì sao WebFlux có thể dùng ít threads mà quản lý nhiều kết nối?

**Trả lời:** Non-blocking/event-driven I/O cho phép thread quay lại phục vụ các sockets khác trong khi chờ sự kiện I/O, thay vì một thread phải đứng chờ mỗi request.

**2.** `Mono.just(jdbc.find(id))` đã non-blocking chưa?

**Trả lời:** Chưa. `jdbc.find(id)` được gọi ngay khi expression đánh giá, có thể block event loop trước khi Mono tồn tại.

**3.** Cách bọc blocking method chuẩn là gì?

**Trả lời:** `Mono.fromCallable(() -> legacy.find(id)).subscribeOn(Schedulers.boundedElastic())` hoặc một bounded scheduler riêng phù hợp.

**4.** `publishOn(boundedElastic)` phía sau `fromCallable` có bảo đảm source offload không?

**Trả lời:** Không. `publishOn` chủ yếu chuyển downstream signals; source có thể đã chạy trên subscription thread. Dùng `subscribeOn` cho nguồn blocking.

**5.** Vì sao `.block()` có thể ném IllegalStateException trên event loop?

**Trả lời:** Reactor đánh dấu một số threads là non-blocking và ngăn các APIs block vốn không phù hợp với event-loop model. Không ném trên thread khác không chứng minh an toàn.

**6.** `timeout(2s)` có chắc hủy SQL query đang block không?

**Trả lời:** Không. Nó cancel reactive subscription/phát lỗi deadline, nhưng blocking driver có thể tiếp tục; cần driver/network statement timeouts.

**7.** Khi `WebClient` và server cùng dùng Reactor Netty, có gì cần lưu ý?

**Trả lời:** Chúng có thể share event-loop resources theo mặc định, nên block server loop có thể ảnh hưởng outbound HTTP I/O callbacks.

**8.** `Schedulers.parallel()` và `boundedElastic()` dùng giống nhau không?

**Trả lời:** Không. Parallel phù hợp CPU tasks; boundedElastic dành cho các calls blocking legacy cần worker capacity giới hạn.

**9.** `Flux` với backpressure có tự ngăn mọi queue vô hạn không?

**Trả lời:** Không. Phải xét producer có thể tôn trọng demand không, bộ đệm/retry/pool và overload policy của từng tầng.

**10.** Cần kiểm gì khi chuyển từ blocking JDBC sang WebFlux?

**Trả lời:** Chọn một reactive database driver như R2DBC hoặc offload bounded worker, kiểm transaction/context, connection pool, request concurrency, timeouts và production observability.

## 22. Tài liệu chính thức và đọc thêm

- [Spring Framework — WebFlux Overview / Concurrency Model](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html): vì sao WebFlux dùng non-blocking I/O và small event-loop worker pool, khác MVC.
- [Spring Framework — WebFlux Reference](https://docs.spring.io/spring-framework/reference/web/webflux.html): annotated controllers, functional endpoints, Reactive Streams và runtime.
- [Project Reactor — FAQ: Wrap a Synchronous Blocking Call](https://projectreactor.io/docs/core/release/reference/faq.html#faq.wrap-blocking): mẫu `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`.
- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): `subscribeOn`, `publishOn`, `parallel`, `boundedElastic`, queue/bounds.
- [Project Reactor — Reactor Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): reactive context thay vì dựa vào ThreadLocal.
- [Project Reactor — Reactor 3.6 Reference](https://projectreactor.io/docs/core/3.6.11/reference/index.html): APIs tương ứng với thế hệ Boot 3.3/Reactor 3.6.
- [Spring Framework — WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html): reactive HTTP client và I/O connectors.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): HTTP-level tests cho reactive server.
- [Spring Framework — WebFlux Error Handling](https://docs.spring.io/spring-framework/reference/web/webflux/ann-controller/ann-exceptions.html): `@ExceptionHandler`, `ProblemDetail` và exception resolution.
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/3.3/reference/web/reactive.html): cấu hình WebFlux, server và tests trong Boot 3.3.
- [Reactive Streams Specification](https://www.reactive-streams.org/): demand, backpressure, publisher/subscriber protocols.
- [Project Reactor — Handling Errors](https://projectreactor.io/docs/core/release/reference/coreFeatures/error-handling.html): `timeout`, `onErrorResume` và error propagation.

**Kết luận:** WebFlux xử lý tốt nhiều kết nối nhờ event loops **không phải chờ blocking I/O**. Chỉ đặt kiểu trả về `Mono`/`Flux` lên code đồng bộ không đem lại lợi ích reactive. Với API non-blocking, hãy compose publishers; với thư viện blocking không thể thay ngay, dùng `Mono.fromCallable(...).subscribeOn(boundedElastic/dedicatedScheduler)` và giới hạn tải. Giữ event-loop callbacks ngắn, kiểm monitoring, timeout, cancellation, bảo mật context và kiểm thử từng dependency để tránh biến một lời gọi chặn thành nghẽn toàn hệ thống.
