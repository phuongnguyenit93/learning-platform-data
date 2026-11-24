# Tránh chặn luồng và lựa chọn Scheduler cho thao tác chặn

## 1. Bài toán: một lời gọi blocking có thể làm chậm cả luồng

Giả sử dịch vụ kiểm tra trạng thái đơn hàng được viết bằng **Spring Cloud Function**. Nghiệp vụ được đóng gói thành một `Function<Flux<OrderEvent>, Flux<Decision>>` để cùng logic có thể được gọi qua HTTP, sự kiện hoặc môi trường serverless. Một lập trình viên viết:

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> decide = orders ->
    orders.map(order ->
        legacyClient.check(order) // Gọi HTTP đồng bộ, có thể chờ 500 ms.
    );
~~~

`map` không tự tạo thread mới. Nếu nguồn `Flux` phát tín hiệu trên một event-loop thread, phương thức `legacyClient.check(order)` cũng có thể chạy **ngay trên event loop đó**. Một lời gọi chờ mạng, chờ JDBC hoặc `Thread.sleep` sẽ giữ thread bận, khiến nhiều request hay message khác cùng dùng thread đó phải đợi.

Từ khóa **reactive** không tự biến một thư viện đồng bộ thành bất đồng bộ. Để hệ thống có khả năng đáp ứng tốt, cần phân biệt:

- **Logic bất đồng bộ không chặn:** dùng client trả publisher như `Mono<Decision>` và kết hợp bằng các toán tử Reactor.
- **Logic blocking bắt buộc phải giữ:** tách nó khỏi những thread không được phép chặn, thường bằng `Schedulers.boundedElastic()` và `Mono.fromCallable(...)`.
- **Logic CPU-bound:** chạy tính toán trên tài nguyên phù hợp, tránh vừa làm nghẽn event loop vừa tạo quá nhiều thread.
- **Điều tiết tải:** giới hạn số tác vụ đồng thời, hàng đợi, timeout và kết nối; đổi Scheduler không thay thế thiết kế về năng lực xử lý.

Bài viết tập trung vào việc **tránh chặn luồng và lựa chọn Scheduler cho thao tác chặn** trong chương *Luồng phản ứng*. Đích đến là các function Spring Cloud Function thuần nghiệp vụ, có thể tái sử dụng qua `FunctionCatalog`, composition, chuyển đổi thông điệp và các adapter khác nhau.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận diện lời gọi blocking và lý do nguy hiểm trên event loop hoặc Scheduler dành cho công việc non-blocking.
2. So sánh `Schedulers.immediate()`, `single()`, `parallel()` và `boundedElastic()`.
3. Phân biệt `subscribeOn` với `publishOn` và hiểu cách chúng tác động tới luồng thực thi.
4. Bọc JDBC, SDK hoặc REST client đồng bộ theo mô hình lazy, không làm chặn thread subscribe.
5. Ghép tác vụ blocking vào `Flux` bằng `flatMap` hoặc `concatMap` mà vẫn kiểm soát lỗi, thứ tự và concurrency.
6. Biết khi nào nên dùng client reactive thực thụ thay cho việc offload công việc blocking.
7. Viết unit test để kiểm tra thời điểm chạy, thread thực thi và tín hiệu lỗi/hoàn tất.
8. Xác định ranh giới trách nhiệm giữa function, Scheduler, HTTP adapter, binder sự kiện và serverless runtime.

## 2. “Không chặn” là gì, và chặn ở đâu?

Một đoạn mã **blocking** khiến thread đang chạy phải đợi sự kiện bên ngoài hoặc một tài nguyên chưa sẵn sàng. Ví dụ điển hình:

~~~java
// Chờ JDBC trả kết quả:
OrderRow row = jdbcRepository.findById(id);

// Chờ HTTP response qua API đồng bộ:
Decision decision = restTemplate.getForObject(url, Decision.class);

// Đợi cố định:
Thread.sleep(500);

// Ép một publisher bất đồng bộ thành giá trị đồng bộ:
Decision result = reactiveClient.check(order).block();
~~~

Các thao tác này có thể làm thread không thực hiện được công việc khác trong thời gian đợi. Ngược lại, client reactive phù hợp có thể biểu diễn trạng thái “đang đợi kết quả” bằng publisher mà không chiếm giữ một thread trong suốt thời gian I/O.

**Điểm quan trọng:** Một chương trình reactive vẫn có các phép tính đồng bộ. `map(String::trim)` là công việc nhỏ, bình thường. Vấn đề không phải “hễ đồng bộ là sai”, mà là **công việc có thể chặn lâu, tốn CPU quá mức hoặc không dự đoán được** trên một thread cần phục vụ nhiều luồng.

### 2.1. Event loop hoạt động như thế nào?

Các runtime như Reactor Netty thường dùng một số lượng event-loop thread giới hạn để xử lý nhiều kết nối. Một event loop lý tưởng chỉ thực hiện các công việc ngắn: đọc/ghi khi I/O sẵn sàng, điều phối callback và chuyển tín hiệu.

~~~mermaid
flowchart LR
    R1["HTTP request A"] --> EL["Event-loop thread"]
    R2["HTTP request B"] --> EL
    R3["HTTP request C"] --> EL
    EL --> BAD["Gọi JDBC blocking 500 ms"]
    BAD --> WAIT["Các callback khác phải đợi"]
~~~

Nếu một callback chiếm thread 500 ms, khả năng phản hồi của các request khác trên thread đó có thể giảm mạnh. Trong thực tế, tốc độ chịu tải còn phụ thuộc số event-loop thread, loại workload, CPU, network và cách ứng dụng được cấu hình.

### 2.2. Reactive Streams không tự giải quyết blocking

`Flux` và `Mono` biểu diễn các publisher với tín hiệu `onNext`, `onError`, `onComplete`. Chúng không tự xác định mỗi thao tác phải chạy trên thread nào.

~~~java
Flux<Integer> source = Flux.range(1, 3);

Flux<Integer> transformed = source.map(value -> {
    System.out.println(Thread.currentThread().getName());
    return value * 2;
});
~~~

Khi subscribe, callback trong `map` thường chạy trên thread đang phát tín hiệu upstream, trừ khi một Scheduler, nguồn bất đồng bộ hoặc toán tử chuyển execution context. `map`, `filter` và `doOnNext` không tự offload công việc.

Trong Spring Cloud Function, `Function.apply(flux)` thường chỉ tạo pipeline. Việc thực thi các callback bắt đầu khi caller/adapter subscribe vào publisher kết quả. Nếu framework đang xử lý nguồn `Flux` trên một thread nhạy cảm, thao tác blocking trong callback có thể ảnh hưởng đến chính thread đó.

## 3. Phân biệt thời điểm tạo pipeline và thời điểm thực thi

Một ví dụ với `Mono.fromCallable`:

~~~java
AtomicInteger calls = new AtomicInteger();

Mono<String> lazyLookup = Mono.fromCallable(() -> {
    calls.incrementAndGet();
    return blockingClient.fetch();
});

// Ở đây calls vẫn bằng 0.
Mono<String> configured = lazyLookup
    .subscribeOn(Schedulers.boundedElastic());

// Khi có subscription, Callable mới được thực thi.
// Sau subscription thành công, calls tăng lên 1.
~~~

`Mono.fromCallable` tạo một publisher *cold* chứa thao tác cần gọi, thay vì chạy `blockingClient.fetch()` ngay khi biến `lazyLookup` được khởi tạo. `subscribeOn` yêu cầu việc subscribe upstream được tổ chức trên Scheduler được chỉ định, nhờ đó lời gọi blocking nằm trong `Callable` có thể chạy trên thread dành cho blocking.

**Ngược lại, đoạn sau vẫn gọi blocking ngay:**

~~~java
// Sai: blockingClient.fetch() được thực thi ngay khi biểu thức được đánh giá.
Mono<String> eager = Mono.just(blockingClient.fetch())
    .subscribeOn(Schedulers.boundedElastic());
~~~

`Mono.just(...)` nhận **giá trị đã tính xong**. Lúc Scheduler tham gia, công việc blocking đã xảy ra. Đây là lỗi quan trọng nhất cần loại bỏ khi chuyển từ imperative sang reactive.

### 3.1. defer và fromCallable

| Cách tạo nguồn | Khi nào chạy logic? | Khi nào phù hợp? |
| --- | --- | --- |
| `Mono.just(value)` | Biểu thức tạo `value` đã chạy trước khi gọi `just` | Giá trị đã có sẵn, không blocking |
| `Mono.fromCallable(() -> call())` | Gọi `call()` khi có subscription | Một tác vụ đồng bộ trả một giá trị hoặc có thể trả `null` |
| `Mono.fromRunnable(() -> action())` | Gọi `action()` khi có subscription | Thao tác `void` đồng bộ, chuyển thành `Mono<Void>` |
| `Mono.defer(() -> monoFactory())` | Tạo publisher mới cho mỗi subscription | Tạo nguồn phụ thuộc trạng thái hiện tại hoặc cơ chế lựa chọn publisher |
| `Flux.defer(() -> fluxFactory())` | Tạo `Flux` mới cho mỗi subscription | Chọn hoặc xây nguồn dữ liệu lúc subscribe |

`Mono.fromCallable` có thể hoàn tất rỗng khi `Callable` trả `null`; nếu nghiệp vụ coi “không tìm thấy” là lỗi, hãy xử lý `switchIfEmpty(...)` hoặc dùng kiểu kết quả tường minh.

### 3.2. Một lần subscribe lại có thể gọi tác vụ blocking lần nữa

~~~java
Mono<String> source = Mono.fromCallable(blockingClient::fetch)
    .subscribeOn(Schedulers.boundedElastic());
~~~

Với publisher cold này, mỗi lần subscribe có thể thực hiện lại `fetch()`. Vì thế:

- Không mặc định lời gọi side effect chỉ thực thi một lần.
- Khi retry hoặc subscribe lại, phải xét idempotency.
- Đối với lệnh cập nhật database hay gửi tiền, phải có khóa nghiệp vụ và hợp đồng giao dịch phù hợp.
- `cache()` có thể thay đổi hành vi phát lại, nhưng không dùng nó như một cơ chế giao dịch hay khử trùng dữ liệu bền vững.

## 4. Các Scheduler phổ biến trong Project Reactor

`Scheduler` là cơ chế trừu tượng để thực thi và lập lịch công việc. Một số Scheduler quen thuộc:

| Scheduler | Đặc tính chính | Trường hợp dùng | Không nên dùng cho |
| --- | --- | --- | --- |
| `Schedulers.immediate()` | Thực thi trên thread hiện tại, không chuyển thread | Không cần scheduling, kiểm thử hoặc trường hợp đơn giản | Offload công việc blocking |
| `Schedulers.single()` | Dùng một worker thread chia sẻ cho công việc tuần tự | Tác vụ ngắn cần tuần tự hóa ở phạm vi thích hợp | Nhiều I/O blocking chờ lâu |
| `Schedulers.parallel()` | Pool thread hữu hạn theo CPU, phù hợp tính toán non-blocking | CPU-bound work ngắn, xử lý song song có kiểm soát | JDBC, REST đồng bộ, `Thread.sleep` hoặc `block()` |
| `Schedulers.boundedElastic()` | Scheduler co giãn có giới hạn cho công việc blocking | Cầu nối với thư viện blocking legacy | Tạo lượng công việc vượt khả năng đích, hoặc coi là giải pháp non-blocking thật |
| Scheduler tùy chỉnh | Từ `Schedulers.newBoundedElastic(...)` hoặc executor được quản lý | Cần tách tài nguyên của các hệ thống legacy | Tạo pool mới cho từng event |

Không có Scheduler “tốt nhất cho mọi thao tác”. Sự lựa chọn dựa vào **mức blocking**, **loại công việc**, **mức song song**, **vòng đời** và **khả năng chờ đợi**.

### 4.1. immediate: không hề rời thread hiện tại

~~~java
Mono.fromCallable(blockingClient::fetch)
    .subscribeOn(Schedulers.immediate());
~~~

Đoạn này **không đưa blocking ra khỏi thread caller**. `immediate` không phải phương án chữa blocking; nó thực hiện công việc trong ngữ cảnh hiện có.

### 4.2. single: tuần tự không có nghĩa phù hợp I/O chậm

~~~java
flux.publishOn(Schedulers.single())
    .map(this::quickTransform);
~~~

`single` có thể hữu ích nếu cần chuyển nhiều tín hiệu tới một worker thread phục vụ tác vụ ngắn. Nhưng một JDBC query 2 giây trên worker này sẽ cản các công việc khác chia sẻ Scheduler đó. Việc “chỉ có một thread” không tự bảo đảm thứ tự nghiệp vụ qua nhiều subscription/instance; thứ tự còn phụ thuộc nguồn và toán tử.

### 4.3. parallel: cho CPU-bound, không cho chờ mạng

~~~java
Flux<Integer> result = Flux.range(1, 100)
    .parallel()
    .runOn(Schedulers.parallel())
    .map(this::expensivePureComputation)
    .sequential();
~~~

`parallel()` tạo `ParallelFlux`, `runOn` gắn Scheduler cho các rail, còn `sequential()` chuyển lại thành `Flux`. Phù hợp cho tính toán thuần có lợi từ nhiều CPU core và chịu được các vấn đề về ordering, overhead, trạng thái chia sẻ.

**Cảnh báo:** Đây không phải cách giải quyết tác vụ I/O blocking. Một thread `parallel` bị chặn sẽ ảnh hưởng khả năng xử lý CPU và các publisher sử dụng Scheduler đó. Reactor cũng nhận diện một số thread non-blocking để từ chối các API như `block()`.

### 4.4. boundedElastic: lựa chọn mặc định để cô lập blocking legacy

~~~java
Mono<Decision> decision = Mono
    .fromCallable(() -> legacyHttpClient.check(order))
    .subscribeOn(Schedulers.boundedElastic());
~~~

`boundedElastic` được Reactor thiết kế cho tác vụ chặn có giới hạn tài nguyên. Thay vì tạo thread không giới hạn, Scheduler này có giới hạn worker/thread và số tác vụ chờ; vượt năng lực có thể dẫn tới hàng đợi lớn hoặc lỗi khi lịch làm việc không còn được chấp nhận.

Cần nhớ:

- Nó **không biến** lời gọi HTTP/JDBC đồng bộ thành non-blocking.
- Thread vẫn bị chiếm trong khi API đồng bộ chờ phản hồi.
- Nếu tốc độ sinh công việc cao hơn tốc độ xử lý lâu dài, queue hoặc độ trễ vẫn tăng.
- Phải có timeout, quản lý tài nguyên I/O, giới hạn concurrency và giám sát.
- `Schedulers.boundedElastic()` là Scheduler chia sẻ của Reactor; không tạo và hủy scheduler mặc định mỗi lần xử lý một phần tử.

### 4.5. Virtual thread là một cấu hình có điều kiện

Ở các phiên bản Reactor/JDK hỗ trợ, implementation của bounded elastic có thể sử dụng **virtual threads** khi được cấu hình phù hợp (ví dụ Java 21+ và thuộc tính Reactor dành cho bounded elastic). Tuy nhiên:

- Không giả định mọi phiên bản Spring Boot/Reactor đều bật hoặc hỗ trợ cùng cấu hình.
- Virtual thread **không làm thư viện blocking thành reactive I/O** và không tăng throughput vượt giới hạn của database/API.
- Pool kết nối, timeout, transaction và chính sách admission vẫn cần thiết.
- Với native method, synchronized/pinning hoặc SDK riêng, hiệu quả thực tế phải được đo đạc.

Đối với bài học và những ví dụ có tính di động, dùng `Schedulers.boundedElastic()` thông thường trước; chỉ thay đổi implementation sau khi kiểm tra phiên bản và benchmark.

## 5. subscribeOn và publishOn: hai điểm đặt ảnh hưởng thread khác nhau

### 5.1. subscribeOn điều phối giai đoạn subscribe upstream

~~~java
Mono<String> result = Mono.fromCallable(() -> {
    log.info("fetch on {}", Thread.currentThread().getName());
    return blockingClient.fetch();
}).subscribeOn(Schedulers.boundedElastic());
~~~

Ở đây nguồn `Mono.fromCallable` được subscribe theo Scheduler được chọn, nên lời gọi blocking trong `Callable` thường chạy trên bounded elastic worker.

Với nhu cầu bọc một nguồn blocking, **đặt `subscribeOn` ngay sau nguồn `fromCallable`** giúp mã dễ đọc và phạm vi chịu trách nhiệm rõ ràng.

`subscribeOn` thường tác động đến việc subscribe/request về phía upstream của pipeline. Với nhiều `subscribeOn` trong cùng một chuỗi, không nên kỳ vọng mỗi lần gọi sẽ tiếp tục đổi thread của cùng một nguồn; lựa chọn gần nguồn/upstream có thể là lựa chọn có hiệu lực cho giai đoạn subscribe đó. Hãy thiết kế một ranh giới rõ thay vì xếp nhiều `subscribeOn` để thử vận may.

### 5.2. publishOn điều phối các tín hiệu downstream

~~~java
Flux<Integer> output = Flux.range(1, 3)
    .map(n -> n * 2)
    .publishOn(Schedulers.parallel())
    .map(n -> heavyCpuTransform(n));
~~~

`publishOn` chuyển việc phát `onNext`, `onComplete` và `onError` xuống các toán tử **phía sau** nó trên Scheduler đã chọn, trong phạm vi hoạt động của pipeline.

Nếu có nhiều `publishOn` ở những điểm khác nhau, mỗi điểm có thể tạo một lần chuyển execution context:

~~~java
Flux<String> output = source
    .publishOn(Schedulers.parallel())
    .map(this::cpuStep)
    .publishOn(Schedulers.boundedElastic())
    .map(this::blockingLegacyStep);
~~~

Ví dụ trên minh họa ranh giới thread. Nhưng trong production, cách tốt hơn thường là **tách `blockingLegacyStep` thành một publisher lazy độc lập dùng `fromCallable(...).subscribeOn(boundedElastic)`**, thay vì chuyển cả luồng downstream sang một Scheduler và giữ nó qua mọi callback.

### 5.3. Bảng so sánh nhanh

| Câu hỏi | `subscribeOn(scheduler)` | `publishOn(scheduler)` |
| --- | --- | --- |
| Tác động chính | Lên quá trình subscribe/upstream | Lên tín hiệu downstream kể từ vị trí đặt |
| Phù hợp khi | Nguồn `fromCallable` hoặc `defer` chứa thao tác blocking | Cần chuyển ngữ cảnh thực thi của chuỗi toán tử phía sau |
| Có biến nguồn eager thành lazy? | **Không** | **Không** |
| Có tự tạo kết nối mạng không chặn? | **Không** | **Không** |
| Có giải quyết bảo đảm thứ tự nghiệp vụ ở broker? | **Không** | **Không** |
| Có thể tăng overhead? | Có, do scheduling | Có, thêm queue/đổi thread/prefetch |

**Quy tắc thực hành:** Ưu tiên `Mono.fromCallable(blockingCall).subscribeOn(Schedulers.boundedElastic())` cho **mỗi công việc blocking**; dùng `publishOn` khi thật sự cần đổi execution context của một đoạn pipeline.

### 5.4. Không có lời hứa “tất cả operator sau subscribeOn luôn chạy ở boundedElastic”

Nhiều nguồn có scheduler nội tại, nguồn hot hoặc callback nhận từ SDK bên ngoài. Dù việc đăng ký nguồn đã dùng `subscribeOn`, các tín hiệu `onNext` sau đó có thể tới từ một thread do nguồn hoặc driver tự quản lý.

Vì vậy, đặt `subscribeOn(boundedElastic)` ở cuối một `Flux` gồm nhiều nguồn bất đồng bộ **không đảm bảo mọi `map` ở phía trên đều chạy trên boundedElastic**. Nếu cần offload một thao tác blocking cụ thể, hãy bọc trực tiếp lời gọi đó thành một publisher lazy và đặt scheduler trên publisher con.

## 6. Mẫu chuẩn: đưa một REST/JDBC API đồng bộ vào pipeline

Giả sử có một client legacy:

~~~java
public interface LegacyFraudClient {
    Decision check(OrderEvent event); // Đồng bộ, có thể chặn.
}
~~~

Cách sai:

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> bad =
    orders -> orders.map(legacyFraudClient::check);
~~~

Cách phù hợp hơn:

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> better =
    orders -> orders.flatMap(
        order -> Mono.fromCallable(
                () -> legacyFraudClient.check(order)
            )
            .subscribeOn(Schedulers.boundedElastic()),
        8
    );
~~~

Giải thích:

1. Mỗi `OrderEvent` dẫn tới một `Mono<Decision>` lazy.
2. `fromCallable` giữ lời gọi blocking bên trong subscription của publisher con.
3. `subscribeOn(boundedElastic)` chuyển lời gọi chặn sang Scheduler phù hợp.
4. `flatMap(..., 8)` giới hạn số inner publishers hoạt động đồng thời trong một subscription.
5. `flatMap` **không** bảo đảm thứ tự kết quả tương ứng với thứ tự `OrderEvent` đầu vào.
6. Nếu lời gọi blocking lỗi, exception trong `Callable` được chuyển thành `onError` của publisher con.

### 6.1. Ví dụ Spring Cloud Function đầy đủ

Các ví dụ sau dùng Java 17+ vì có `record`. Định nghĩa một class cấu hình tự chứa; `LegacyFraudClient` là interface do ứng dụng triển khai bằng thư viện đồng bộ của mình.

~~~java
package demo.scheduler;

import java.util.function.Function;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@Configuration
public class FraudFunctions {

    public record OrderEvent(String orderId, long amountCents) {}

    public record Decision(String orderId, boolean approved) {}

    public interface LegacyFraudClient {
        Decision check(OrderEvent order); // Blocking I/O
    }

    @Bean
    public Function<Flux<OrderEvent>, Flux<Decision>> checkFraud(
            LegacyFraudClient legacyClient) {

        return orders -> orders.flatMap(
            order -> Mono.fromCallable(
                    () -> legacyClient.check(order)
                )
                .subscribeOn(Schedulers.boundedElastic()),
            8
        );
    }
}
~~~

Spring sẽ inject `LegacyFraudClient` khi có bean triển khai phù hợp. `@Bean` đăng ký một `Function<Flux<OrderEvent>, Flux<Decision>>`; qua `FunctionCatalog`, adapter có thể tra cứu tên `checkFraud` và dùng cùng logic bất kể HTTP, message binder hay serverless.

Một cấu hình chọn function có thể là:

~~~properties
spring.cloud.function.definition=checkFraud
~~~

Đây chỉ là định nghĩa function được chọn. Nó không tự cung cấp HTTP server, broker, credential hay chính sách retry; mỗi adapter cần cấu hình tương ứng.

### 6.2. Nếu kết quả phải theo thứ tự đầu vào?

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> ordered =
    orders -> orders.concatMap(
        order -> Mono.fromCallable(
                () -> legacyClient.check(order)
            )
            .subscribeOn(Schedulers.boundedElastic())
    );
~~~

`concatMap` chờ từng publisher con hoàn tất rồi mới xử lý publisher tiếp theo. Đầu ra có thể giữ thứ tự đơn hàng trong subscription đó, và việc gọi client được tuần tự hóa ở ranh giới publisher. Nhưng nếu nguồn xử lý nhiều subscription hoặc nhiều instance song song, không thể suy từ `concatMap` rằng thứ tự hệ thống ngoài được bảo đảm toàn cục.

Nếu chỉ cần kết quả phát theo thứ tự nhưng thao tác nghiệp vụ được phép đồng thời, `flatMapSequential` có thể là lựa chọn trung gian; nó **không** đảm bảo tác dụng phụ thực sự hoàn thành theo thứ tự, và có thể dùng buffer để chờ phần tử đầu.

### 6.3. Bọc truy vấn trả một List

Một repository blocking có thể trả danh sách:

~~~java
public interface LegacyOrderRepository {
    java.util.List<OrderEvent> findPending();
}
~~~

Đừng gọi nó ngay khi tạo publisher:

~~~java
// Sai: findPending() chạy trước khi subscribeOn có tác dụng.
Flux<OrderEvent> wrong = Flux.fromIterable(
    repository.findPending()
).subscribeOn(Schedulers.boundedElastic());
~~~

Cách đưa lời gọi tạo danh sách vào `Callable`:

~~~java
Flux<OrderEvent> pending = Mono
    .fromCallable(repository::findPending)
    .subscribeOn(Schedulers.boundedElastic())
    .flatMapMany(Flux::fromIterable);
~~~

Toàn bộ lần đọc danh sách diễn ra khi có subscription trên Scheduler dành cho blocking. Sau đó danh sách được biến thành `Flux` để xử lý tiếp. Cần cân nhắc:

- `findPending()` có thể trả quá nhiều bản ghi, làm tăng heap dù đã offload.
- Với JDBC streaming/lazy iterator, việc duyệt iterator có thể tiếp tục chặn sau khi truy vấn đầu trả về. Không coi mẫu `fromIterable` là đủ để quản lý `ResultSet` streaming.
- Phân trang, giới hạn batch, đóng tài nguyên và transaction vẫn cần thiết.
- Một query đơn đọc hàng triệu bản ghi không trở thành hiệu quả chỉ nhờ có `Flux`.

## 7. Chọn reactive client thay vì offload khi có thể

Nếu hệ thống đã có thư viện non-blocking thực thụ, ưu tiên dùng nó:

~~~java
public interface ReactiveFraudClient {
    Mono<Decision> check(OrderEvent order);
}

Function<Flux<OrderEvent>, Flux<Decision>> check =
    orders -> orders.flatMap(
        reactiveFraudClient::check,
        8
    );
~~~

`ReactiveFraudClient` có thể được triển khai bằng WebClient hoặc driver reactive. Trong trường hợp này, request được biểu diễn bằng publisher; không cần tự bọc một client thực sự non-blocking trong `Mono.fromCallable` hay đẩy từng thao tác qua `boundedElastic`.

| Trường hợp | Lựa chọn thường hợp lý |
| --- | --- |
| HTTP client đồng bộ như `RestTemplate` hoặc SDK blocking | Bọc lazy bằng `Mono.fromCallable` + `boundedElastic`, hoặc chuyển sang client non-blocking |
| HTTP client reactive như `WebClient` | Trả/ghép `Mono` trực tiếp, kiểm soát concurrency và timeout |
| JDBC đồng bộ | Isolate trên bounded elastic, cân nhắc phân trang/transaction |
| R2DBC/reactive repository | Dùng publisher của driver, tránh `block()` |
| Tính toán CPU thuần ngắn | `map` bình thường, không cần offload |
| Tính toán CPU nặng, độc lập | `parallel`/Scheduler phù hợp, đo CPU và thứ tự |
| `Thread.sleep` để mô phỏng delay | Dùng `Mono.delay` khi mô phỏng thời gian, không giữ thread vô ích |

### 7.1. Ví dụ WebClient

~~~java
public Mono<Decision> check(OrderEvent order) {
    return webClient.post()
        .uri("/risk/check")
        .bodyValue(order)
        .retrieve()
        .bodyToMono(Decision.class);
}
~~~

Đây là ví dụ phương thức trong một class có `WebClient webClient`, `OrderEvent` và `Decision` được khai báo sẵn. `bodyToMono` trả publisher mô tả request/response; xử lý lỗi HTTP status, timeout, retry và giới hạn kết nối cần được thiết kế phù hợp.

Không gọi:

~~~java
Decision decision = check(order).block(); // Phá ý nghĩa non-blocking.
~~~

bên trong `map` hoặc function reactive đang được adapter subscribe. Hãy ghép publisher bằng `flatMap` hoặc `concatMap`.

## 8. Giới hạn concurrency, backpressure và queue

Offload có thể làm ứng dụng không chặn event loop, nhưng **không giải quyết được bài toán nguồn phát nhanh hơn khả năng xử lý**.

Giả sử một database chỉ hỗ trợ tối đa 20 truy vấn đồng thời hiệu quả. Nếu input có 100.000 sự kiện, việc tạo 100.000 tác vụ `boundedElastic` ngay lập tức có thể gây chờ dài, dùng hết connection pool và làm quá tải queue.

### 8.1. flatMap với mức đồng thời hữu hạn

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> limited =
    orders -> orders.flatMap(
        order -> Mono.fromCallable(
                () -> legacyClient.check(order)
            )
            .subscribeOn(Schedulers.boundedElastic()),
        8
    );
~~~

`8` giới hạn số inner publishers đồng thời cho **một subscription ở toán tử này**. Nếu có 10 luồng xử lý độc lập hoặc 10 instance, tổng số tác vụ có thể lớn hơn nhiều. Cần quản lý cả connection pool, số consumer, quota API và số instance.

### 8.2. Backpressure khác concurrency

- **Backpressure:** downstream dùng `request(n)` để thể hiện nhu cầu số phần tử.
- **Concurrency limit:** tối đa bao nhiêu inner publishers đang xử lý.
- **Scheduler queue:** những công việc đã được lên lịch nhưng chưa có worker.
- **Rate limit:** có bao nhiêu lượt gọi mới được bắt đầu trong một khoảng thời gian.
- **Database connection pool:** giới hạn số kết nối đồng thời đang dùng.

Năm khía cạnh có liên quan nhưng không thể thay thế nhau. Đặt `flatMap(..., 8)` không bảo đảm tối đa tám yêu cầu trên toàn cluster hay tối đa tám request/giây. Cũng không có bảo đảm rằng broker sẽ giảm phát khi Reactor giảm nhu cầu nếu binder không truyền được backpressure đến broker.

### 8.3. Không dùng buffer vô hạn để che quá tải

~~~java
Flux<OrderEvent> queued = source.onBackpressureBuffer();
~~~

Một queue không giới hạn trên luồng tốc độ cao có nguy cơ làm hết bộ nhớ. Đặc biệt với đơn hàng hoặc thanh toán, `onBackpressureDrop` và `onBackpressureLatest` có thể làm mất dữ liệu nên không được dùng chỉ để “hết lỗi quá tải”.

Nếu bắt buộc xử lý đủ, hãy ưu tiên nguồn bền vững (broker/outbox), cấu hình khả năng đọc/pause/ack của binder, buffer hữu hạn và xử lý có checkpoint/idempotency.

### 8.4. Mức tải thực tế của boundedElastic

`Schedulers.boundedElastic()` giúp cách ly chờ I/O khỏi event loop, nhưng vẫn có giới hạn worker và queue. Khi giới hạn bị vượt, việc schedule có thể bị từ chối hoặc độ trễ tăng. Không giả định scheduler sẽ tự scale vô hạn theo lượng sự kiện.

Giám sát đồng thời:

- Độ trễ end-to-end của event.
- Thời gian chờ kết nối database/HTTP.
- Số truy vấn/requests đang hoạt động.
- Số job chờ xử lý và thời gian queue.
- CPU, memory, thread/virtual-thread count theo cấu hình.
- Lỗi timeout, queue saturation và tỷ lệ retry.

## 9. Quản lý Scheduler tùy chỉnh thay vì chia sẻ tất cả blocking

Trong ứng dụng lớn, một SDK blocking rất chậm có thể chiếm nhiều tài nguyên của `Schedulers.boundedElastic()` mặc định và ảnh hưởng workload khác. Có thể tạo Scheduler dành riêng với giới hạn rõ ràng:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

@Configuration
public class SchedulerConfiguration {

    @Bean(destroyMethod = "dispose")
    public Scheduler legacyDatabaseScheduler() {
        // Tối đa 8 backing threads; số tác vụ chờ có giới hạn.
        return Schedulers.newBoundedElastic(
            8, 1000, "legacy-db"
        );
    }
}
~~~

Khi inject scheduler:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<Decision>> checkUsingLegacyDb(
        LegacyFraudClient client,
        Scheduler legacyDatabaseScheduler) {

    return incoming -> incoming.flatMap(
        order -> Mono.fromCallable(() -> client.check(order))
            .subscribeOn(legacyDatabaseScheduler),
        8
    );
}
~~~

Ví dụ thứ hai là phương thức `@Bean` trong một class cấu hình có import `Function`, `Flux`, `Mono`, `Scheduler`, `OrderEvent`, `Decision` và `LegacyFraudClient` tương ứng. Các mẫu trên có thể được tích hợp vào class `FraudFunctions` ở mục 6.

**Không tạo `Schedulers.newBoundedElastic(...)` cho mỗi phần tử.** Làm vậy sẽ tạo quá nhiều scheduler/thread, khó quản lý lifecycle và phá giới hạn tài nguyên. Một scheduler tùy chỉnh nên là bean sống theo ứng dụng hoặc một thành phần có vòng đời rõ ràng; cần dispose khi đóng ứng dụng.

### 9.1. Bounded elastic không thay thế bulkhead ở dịch vụ đích

Giới hạn tám thread không chắc chắn đồng nghĩa chỉ có tám truy vấn ở database nếu cùng client còn được sử dụng ở nơi khác hoặc một request tạo thêm công việc ngoài scheduler. Với nhiều instance, tổng nhu cầu vẫn nhân lên. Cần phối hợp:

1. Connection pool size và timeout chờ connection.
2. Giới hạn concurrency tại function.
3. Hạn mức ở dịch vụ đích.
4. Cơ chế queue, circuit breaker hoặc bulkhead khi cần.
5. Phân vùng/điều phối trên nhiều instance.

## 10. JDBC transaction và giới hạn của việc đổi thread

Các API transaction đồng bộ truyền thống thường gắn ngữ cảnh vào thread, chẳng hạn cơ chế `ThreadLocal` trong một số transaction manager. Reactive execution có thể chuyển thread giữa các toán tử, nên không được dựa vào ý tưởng “cứ gắn `subscribeOn` là mọi bước transaction sẽ luôn cùng một thread”.

### 10.1. Nhóm tác vụ blocking thuộc một transaction

Nếu phải giữ giao dịch JDBC đồng bộ, nên gói **toàn bộ phần việc blocking cần cùng transaction** trong một đơn vị đồng bộ rồi offload nguyên đơn vị:

~~~java
Mono<Receipt> saveAtomically(OrderEvent order) {
    return Mono.fromCallable(() ->
        transactionTemplate.execute(status -> {
            legacyOrderRepository.insert(order);
            return legacyAuditRepository.appendAndCreateReceipt(order);
        })
    ).subscribeOn(Schedulers.boundedElastic());
}
~~~

`transactionTemplate`, hai repository và `Receipt` là dependency/DTO của ứng dụng. Mục tiêu ví dụ là giữ các thao tác đồng bộ cần cùng transaction trong callback `Callable`. Nếu transaction callback trả `null`, `Mono.fromCallable` sẽ hoàn tất rỗng; hãy xác định rõ hợp đồng kết quả.

Các transaction reactive dùng R2DBC có cách truyền context khác với transaction JDBC thread-bound. Không trộn mô hình một cách tùy tiện; cần kiểm tra transaction manager và driver đang dùng.

### 10.2. Không “chia nhỏ transaction” bằng nhiều publishOn

~~~java
// Thiết kế đáng nghi với transaction đồng bộ thread-bound:
source.publishOn(Schedulers.boundedElastic())
    .map(order -> jdbcRepository.insert(order))
    .publishOn(Schedulers.parallel())
    .map(order -> jdbcRepository.updateAudit(order));
~~~

Hai thao tác có thể chạy trên thread khác nhau; nếu đang dựa vào transaction thread-bound, tính toàn vẹn có thể bị phá vỡ. Nếu cần transaction cho cả hai thao tác, hãy nhóm chúng trong một unit of work hoặc chuyển hẳn sang giải pháp transaction reactive tương thích.

### 10.3. Cancellation không đảm bảo rollback ở hệ thống ngoài

Khi một subscriber hủy `Mono.fromCallable(...)`, Reactor có thể không phát kết quả tiếp, nhưng lời gọi JDBC hoặc SDK blocking đã bắt đầu **có thể tiếp tục chạy** cho tới khi driver trả về. Không suy ra rằng `cancel` đã hủy truy vấn hoặc rollback transaction.

Do đó:

- Đặt timeout tại chính database/HTTP client, không chỉ trên publisher.
- Phân biệt “caller không còn nhận kết quả” với “tác vụ chưa từng xảy ra”.
- Dùng khóa idempotency nếu retry có thể ghi lặp.
- Đối với sự kiện quan trọng, kiểm tra trạng thái sau lỗi/cancellation theo yêu cầu nghiệp vụ.

## 11. Timeout, lỗi và retry trong pipeline có offload

### 11.1. Timeout từng thao tác

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> checked =
    orders -> orders.flatMap(
        order -> Mono.fromCallable(
                () -> legacyClient.check(order)
            )
            .subscribeOn(Schedulers.boundedElastic())
            .timeout(Duration.ofSeconds(2)),
        8
    );
~~~

`timeout` phát lỗi nếu publisher không tạo tín hiệu terminal/giá trị trong giới hạn theo hợp đồng của toán tử. Tuy nhiên, nếu SDK blocking không hỗ trợ hủy, lời gọi nền **có thể vẫn chiếm thread** sau timeout. Cần cả timeout của HTTP client/JDBC driver và quản lý kết nối.

### 11.2. Phục hồi theo phần tử hay cho toàn luồng?

Nếu mỗi event có thể được đánh dấu “chưa xác định”, phục hồi lỗi trong inner publisher:

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> resilient =
    orders -> orders.flatMap(
        order -> Mono.fromCallable(
                () -> legacyClient.check(order)
            )
            .subscribeOn(Schedulers.boundedElastic())
            .timeout(Duration.ofSeconds(2))
            .onErrorResume(error ->
                Mono.just(new Decision(order.orderId(), false))
            ),
        8
    );
~~~

Giả sử `false` ở ví dụ này là quy tắc *fail closed* được nghiệp vụ chấp nhận. Nếu cần phân biệt từ chối hợp lệ và kiểm tra thất bại, nên dùng DTO có `status = UNAVAILABLE`, không biến mọi lỗi thành kết quả từ chối một cách khó giải thích.

Nếu đặt `onErrorResume` ngoài toàn bộ `flatMap`, một lỗi có thể đã kết thúc subscription nguồn; fallback phía ngoài **không tự tiếp tục từ phần tử kế tiếp**.

### 11.3. Retry cần giới hạn và idempotency

~~~java
Mono<Decision> oneOrder = Mono.fromCallable(
        () -> legacyClient.check(order)
    )
    .subscribeOn(Schedulers.boundedElastic())
    .retryWhen(
        reactor.util.retry.Retry.backoff(
            2, Duration.ofMillis(200)
        )
    );
~~~

`retryWhen` sẽ subscribe lại upstream sau lỗi theo chính sách. Với `fromCallable`, nó có thể **gọi lại client blocking**. Nếu lời gọi có side effect và kết quả lần đầu bị mất, retry có thể gây thực hiện trùng. Hãy thiết kế idempotency và chỉ retry loại lỗi phù hợp.

Cẩn thận với “retry storm”: nhiều event lỗi đồng thời và tất cả cùng retry có thể làm quá tải hệ thống đang gặp sự cố. Giới hạn concurrency, backoff, jitter và circuit breaker/bulkhead là các công cụ bổ sung cần được cân nhắc.

## 12. Luồng hữu hạn, luồng liên tục và vòng đời Scheduler

Một source hữu hạn như `Flux.just(...)` có thể xử lý vài đơn rồi phát `onComplete`. Nhưng `Supplier<Flux<T>>` có thể trả nguồn liên tục như `Flux.interval(...)` hoặc stream từ broker, và subscription tồn tại lâu.

### 12.1. Không để task blocking chiếm thread vô hạn

Một callback chờ mãi trong `Mono.fromCallable` có thể giữ một worker bounded elastic lâu hơn ý định. Với nguồn liên tục, nếu nhiều event tiếp tục tới, số task bị kẹt có thể tăng cho tới khi hàng đợi đầy hoặc timeout.

Giải pháp cần nhìn ở nhiều tầng:

- Timeout ở SDK/driver.
- Hạn mức số tác vụ và connection.
- Phân loại lỗi và cơ chế cô lập dịch vụ kẹt.
- Giám sát thời gian queue và số task đang chạy.
- Một chiến lược shutdown chủ động để ngừng nhận thêm sự kiện và đợi/huỷ công việc đang chạy.

### 12.2. Không gọi subscribe() bên trong Function khi có thể trả publisher

~~~java
// Sai hướng thiết kế: tác vụ chạy ngoài sự quản lý của caller.
Function<Flux<OrderEvent>, Flux<Decision>> hiddenWork = orders -> {
    orders.flatMap(order ->
        Mono.fromCallable(() -> legacyClient.check(order))
            .subscribeOn(Schedulers.boundedElastic())
    ).subscribe();

    return Flux.empty();
};
~~~

Lời gọi `subscribe()` riêng tạo một subscription không gắn với publisher trả về. Caller có thể thấy output kết thúc ngay, trong khi công việc vẫn chạy; lỗi và cancellation khó được xử lý nhất quán.

Thay vì thế:

~~~java
Function<Flux<OrderEvent>, Flux<Decision>> visibleWork =
    orders -> orders.flatMap(
        order -> Mono.fromCallable(
                () -> legacyClient.check(order)
            ).subscribeOn(Schedulers.boundedElastic()),
        8
    );
~~~

Khi trả publisher, caller/adapter có cơ hội quản lý subscription và quan sát tín hiệu.

### 12.3. Consumer<Flux<T>> là trường hợp cần xét riêng

Với `Consumer<Flux<T>>` trả `void`, framework không có publisher kết quả để subscribe. Trong một số cách tích hợp Spring Cloud Function/Stream, reactive consumer tường minh phải tự subscribe và tự quản lý `Disposable`, lỗi và lifecycle.

Nếu mục tiêu là xử lý bất đồng bộ và **báo hoàn tất/lỗi mà không trả payload**, `Function<Flux<T>, Mono<Void>>` với `then()` có thể biểu diễn hợp đồng rõ hơn:

~~~java
Function<Flux<OrderEvent>, Mono<Void>> audit =
    events -> events
        .concatMap(event ->
            Mono.fromRunnable(
                () -> legacyAuditStore.persist(event)
            )
            .subscribeOn(Schedulers.boundedElastic())
        )
        .then();
~~~

`legacyAuditStore.persist(event)` là phương thức blocking trả `void`. `then()` chỉ hoàn tất khi nguồn hữu hạn và các tác vụ con hoàn tất; với nguồn vô hạn, `Mono<Void>` không có tín hiệu hoàn tất cuối luồng trong lúc nguồn còn hoạt động.

## 13. ThreadLocal, MDC, tracing và context khi chuyển Scheduler

Chuyển thread có thể thay đổi hành vi của thông tin gắn với thread. Ví dụ:

~~~java
requestContext.set("trace-123"); // ThreadLocal ở thread hiện tại.

Mono<Decision> result = Mono.fromCallable(() -> {
    // Không mặc định thấy giá trị ThreadLocal của caller.
    return legacyClient.check(order);
}).subscribeOn(Schedulers.boundedElastic());
~~~

Không nên giả định `ThreadLocal`, MDC logging hoặc thông tin bảo mật ở thread caller tự xuất hiện trên thread bounded elastic. Trong ứng dụng Reactor, **Reactor Context** giúp truyền metadata theo subscription; còn việc bridge sang ThreadLocal/MDC cần cơ chế propagation phù hợp với phiên bản Spring/Reactor và thư viện tracing.

### 13.1. Reactor Context cho metadata của subscription

~~~java
Mono<String> task = Mono.deferContextual(ctx -> {
    String traceId = ctx.getOrDefault("traceId", "unknown");

    return Mono.fromCallable(() ->
        legacyClient.fetchWithTrace(traceId)
    ).subscribeOn(Schedulers.boundedElastic());
}).contextWrite(ctx -> ctx.put("traceId", "trace-123"));
~~~

Mẫu này lấy `traceId` từ Reactor Context rồi truyền **tường minh** vào phương thức blocking. Nó không yêu cầu `ThreadLocal` phải tự chảy giữa các thread.

Khi đi qua message broker, header như `correlationId` hoặc `traceId` có thể cần được ánh xạ thành metadata trên `Message<T>` và truyền vào Reactor Context ở biên adapter. Cách đó phụ thuộc stack đang dùng; không tự suy ra context của một subscription là context của mọi message.

### 13.2. SecurityContext và transaction context

Không dùng `ThreadLocal` tự tạo như nguồn sự thật về security/transaction sau nhiều `publishOn`. Cần dùng API context propagation và transaction manager phù hợp (reactive hoặc imperative) của framework thực tế.

Ví dụ, việc ghi JDBC đồng bộ bên trong một `Callable` với transaction đồng bộ có thể được quản lý theo thread của chính callback đó; chuyển thread giữa chừng trong giao dịch có thể gây hành vi sai.

## 14. Test lazy execution và thread thực thi bằng StepVerifier

`StepVerifier` tạo subscription và quan sát tín hiệu hoàn tất/lỗi. Ta có thể dùng nó để chứng minh một thao tác blocking được **trì hoãn đến khi subscribe** và được **chạy trên thread khác**.

### 14.1. Một tác vụ chạy trên Scheduler thay vì thread test

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotSame;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class BlockingSchedulerTest {

    @Test
    void callableIsLazyAndRunsOnBoundedElastic() {
        Thread testThread = Thread.currentThread();
        AtomicInteger calls = new AtomicInteger();
        AtomicReference<Thread> executedOn = new AtomicReference<>();

        Mono<String> source = Mono.fromCallable(() -> {
            calls.incrementAndGet();
            executedOn.set(Thread.currentThread());
            return "ORD-101";
        }).subscribeOn(Schedulers.boundedElastic());

        assertEquals(0, calls.get());

        StepVerifier.create(source)
            .expectNext("ORD-101")
            .verifyComplete();

        assertEquals(1, calls.get());
        assertNotSame(testThread, executedOn.get());
    }
}
~~~

Test chỉ khẳng định mô hình Reactor cụ thể trong ví dụ. Nó **không** kiểm tra mức tải tối đa, timeout của JDBC, khả năng thread propagation hay end-to-end behavior của một adapter.

### 14.2. Lỗi trong Callable trở thành onError

~~~java
@Test
void checkedExceptionIsAnErrorSignal() {
    Mono<String> source = Mono.<String>fromCallable(() -> {
        throw new java.io.IOException("legacy service unavailable");
    }).subscribeOn(Schedulers.boundedElastic());

    StepVerifier.create(source)
        .expectErrorMatches(error ->
            error instanceof java.io.IOException
                && error.getMessage().contains("unavailable"))
        .verify();
}
~~~

Không cần gọi `try/catch` quanh `source` chỉ để lấy lỗi; nếu exception xuất hiện **khi subscribe**, nó đi vào tín hiệu `onError`.

### 14.3. Giới hạn số tác vụ đồng thời bằng test

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

@Test
void innerBlockingCallsHaveBoundedConcurrency() {
    AtomicInteger active = new AtomicInteger();
    AtomicInteger peak = new AtomicInteger();

    Flux<Integer> pipeline = Flux.range(1, 12)
        .flatMap(item ->
            Mono.fromCallable(() -> {
                int now = active.incrementAndGet();
                peak.accumulateAndGet(now, Math::max);
                try {
                    // Chỉ mô phỏng blocking trong unit test;
                    // công việc đã được offload lên boundedElastic.
                    Thread.sleep(15);
                    return item;
                } finally {
                    active.decrementAndGet();
                }
            }).subscribeOn(Schedulers.boundedElastic()),
            3
        );

    StepVerifier.create(pipeline.collectList())
        .assertNext(values -> assertEquals(12, values.size()))
        .verifyComplete();

    assertTrue(peak.get() <= 3);
}
~~~

Đây là kiểm thử **giới hạn concurrency trong một subscription**, không kiểm thử số thread trên cả JVM/cluster. Test dùng `Thread.sleep` để mô phỏng một SDK blocking và đã offload đúng Scheduler; trong ứng dụng production, ưu tiên client không chặn.

### 14.4. Kiểm thử với BlockHound là tùy chọn

Trong môi trường hỗ trợ, **BlockHound** có thể giúp phát hiện những API blocking được gọi trên các thread đánh dấu non-blocking. Tuy nhiên:

- Cần dependency và cài đặt/test integration tương thích với JVM và Reactor đang dùng.
- Có thể cần cấu hình, đặc biệt với agent/instrumentation.
- Không phải mọi hành vi blocking của thư viện bên ngoài đều được phát hiện.
- Nó không thay thế kiểm thử tải, profiler hay kiểm tra transaction/driver.

Không thêm `BlockHound.install()` tùy tiện vào mọi test nếu project chưa có cơ chế cấu hình và hỗ trợ phiên bản; nên tích hợp có chủ đích ở test suite phù hợp.

## 15. Dấu hiệu nghẽn thread khi chạy thật

Một số triệu chứng thường thấy:

| Triệu chứng | Khả năng liên quan | Hướng kiểm tra |
| --- | --- | --- |
| HTTP p99 tăng mạnh dù CPU chưa cao | Event loop bị giữ bởi I/O blocking | Thread dump, profiler, stack traces |
| Nhiều request chờ nhưng throughput không tăng | Connection pool hoặc tài nguyên đích bão hòa | Pool metrics, timeout, pending acquisition |
| Sau khi chuyển boundedElastic vẫn chậm | Công việc blocking vẫn chiếm worker/queue | Thời gian thực thi task, số task chờ, capacity |
| Một số request vô cớ timeout | Retry đồng loạt hoặc queue quá dài | Các mốc timing trong pipeline và client |
| Có lỗi `IllegalStateException` khi `block()` | Gọi API chặn trên thread đánh dấu non-blocking | Tìm `block()`, `blockFirst()`, `blockLast()` trong call path |
| Logs mất traceId khi đổi Scheduler | Metadata dựa vào `ThreadLocal` | Reactor Context / context propagation |
| Sau cancellation vẫn thấy DB query chạy | Driver blocking không hủy được ngay | Client query timeout, transaction/connection cleanup |
| Đơn hàng xử lý trùng sau lỗi | Retry/resubscribe nguồn cold hoặc broker redelivery | Khóa idempotency, offset, transaction |
| Chỉ xảy ra khi production tải cao | Số kết nối/instance lớn hơn test | Load test, capacity planning, limit per instance |

Một thread dump có thể cho thấy các stack chờ socket, `LockSupport.park`, JDBC hoặc sleep. Nhưng trạng thái `WAITING` không luôn là lỗi: worker rảnh cũng có thể đang chờ công việc. Cần đặt thông tin stack cùng bối cảnh latency và throughput.

### 15.1. Các metric đáng theo dõi

- **Độ trễ:** p50/p95/p99 của API, query, I/O task và thời gian từ lúc nhận event tới khi xử lý xong.
- **Resource:** CPU, heap, thread count, connection pool active/pending.
- **Scheduler/queue:** số công việc chờ, độ dài queue và thời gian task chờ nếu instrumentation cho phép.
- **Publisher:** số subscription, số event xử lý, completion/error/cancellation.
- **Reliability:** timeout, retry, dead-letter, redelivery và số event xử lý trùng.
- **Broker:** lag, prefetch, partition/consumer count và các mốc acknowledgment theo binder.

Không log chi tiết mỗi phần tử ở tốc độ cao chỉ để quan sát performance; chính I/O logging đồng bộ có thể làm nghẽn pipeline.

## 16. Khi cùng function được gọi qua HTTP, sự kiện hoặc serverless

Một lợi ích quan trọng của Spring Cloud Function là **giữ nguyên logic nghiệp vụ** nhưng thay adapter. Tuy nhiên, trách nhiệm quản lý thread và completion không đồng nhất ở mọi môi trường.

~~~mermaid
flowchart TD
    CALL["HTTP / Event binder / Serverless"] --> CAT["FunctionCatalog"]
    CAT --> FUNC["Function<Flux<T>, Flux<R>>"]
    FUNC --> ASYNC["Mono.fromCallable(blockingCall)"]
    ASYNC --> SCH["subscribeOn(boundedElastic)"]
    SCH --> OUT["Publisher kết quả"]
    OUT --> ADAPTER["Adapter subscribe, serialize/send"]
    ADAPTER --> DEST["Client / broker / runtime"]
~~~

### 16.1. Gọi qua HTTP

Với một HTTP adapter dùng stack reactive, function có thể nhận publisher từ request body và trả publisher làm response. Không đặt blocking trực tiếp vào `map` trên event loop; thay vào đó offload lời gọi blocking cụ thể hoặc dùng client reactive.

Một request bị client hủy có thể dẫn tới cancellation của subscription; nhưng tác vụ blocking bên ngoài có thể đã commit dữ liệu. Cần xác định status HTTP, timeout và chính sách retry của client, không dựa vào việc request bị hủy để khẳng định side effect chưa xảy ra.

### 16.2. Nhận sự kiện qua Spring Cloud Stream

Khi kết nối với binder sự kiện, framework có thể đưa message vào function theo từng phần tử hoặc thiết lập một reactive pipeline dài hạn. `Function<Flux<T>, Flux<R>>` có thể được áp dụng một lần với một `Flux` có nhiều event; callback bên trong các toán tử mới chạy theo dữ liệu đến.

**Không suy ra rằng backpressure của Reactor sẽ truyền đến Kafka/Rabbit hoặc rằng gửi broker sẽ đợi mọi `Mono.fromCallable` hoàn tất**. Binder, consumer prefetch/poll, acknowledgment và error handling phải được kiểm tra ở phiên bản cụ thể.

Nếu function trả `Flux<R>`, adapter có publisher kết quả để quản lý subscription. Nếu bạn tự `subscribe()` trong function rồi trả một publisher rỗng, adapter có thể hiểu sai thời điểm đã xử lý xong.

### 16.3. Serverless

Runtime serverless có giới hạn thời gian và tài nguyên cho invocation. Đẩy một JDBC call 30 giây vào boundedElastic không khiến invocation hết timeout muộn hơn. Cần đặt timeout và giới hạn số phần tử phù hợp, để publisher kết thúc trước khi runtime đóng invocation.

Không tin rằng một `subscribe()` kiểu fire-and-forget sẽ tiếp tục chạy an toàn sau khi function serverless đã trả kết quả; runtime có thể đóng hoặc đóng băng môi trường.

### 16.4. Composition không “sửa” blocking

Giả sử hai bean:

~~~java
@Bean
Function<Flux<OrderEvent>, Flux<OrderEvent>> validate() {
    return events -> events.filter(e -> e.amountCents() > 0);
}

@Bean
Function<Flux<OrderEvent>, Flux<Decision>> checkFraud(
        LegacyFraudClient client) {
    return events -> events.flatMap(
        e -> Mono.fromCallable(() -> client.check(e))
            .subscribeOn(Schedulers.boundedElastic()),
        8
    );
}
~~~

Có thể chọn composition:

~~~properties
spring.cloud.function.definition=validate|checkFraud
~~~

`FunctionCatalog` hỗ trợ tra cứu và composition theo tên khi các chữ ký tương thích. Tuy vậy, **composition không tự phát hiện mọi lời gọi blocking để chuyển thread**. Mỗi function phải đặt ranh giới scheduling thích hợp trong pipeline của nó.

## 17. Quy trình chọn giải pháp

~~~mermaid
flowchart TD
    START["Cần xử lý một thao tác trong Flux/Mono"] --> Q{"Thao tác có thể blocking?"}
    Q -->|Không, xử lý nhỏ| MAP["map/filter trực tiếp"]
    Q -->|I/O có API reactive| REACTIVE["flatMap/concatMap publisher non-blocking"]
    Q -->|Có, chỉ có SDK/JDBC blocking| WRAP["Mono.fromCallable/fromRunnable"]
    WRAP --> SCHED["subscribeOn(boundedElastic)"]
    SCHED --> LIMIT["Giới hạn concurrency,\ntimeout, pool và queue"]
    MAP --> TEST["Kiểm thử subscription,\nlỗi, tải và adapter"]
    REACTIVE --> TEST
    LIMIT --> TEST
~~~

Để lựa chọn đúng, hãy tự trả lời:

1. **Thực sự blocking ở đâu?** Đọc database, chờ HTTP, sleep, đợi khóa hay CPU thuần?
2. **Có API non-blocking không?** Nếu có, ưu tiên ghép publisher trực tiếp.
3. **Đang chạy ở thread nào?** Event loop, parallel, bounded elastic hay nguồn bên ngoài?
4. **Lời gọi đã lazy chưa?** `Mono.just(blockingCall())` vẫn gọi blocking ngay.
5. **Ai subscribe?** Spring Cloud Function adapter, test hay code đang tự subscribe ngoài luồng?
6. **Concurrency bao nhiêu?** Một `flatMap` có thể mở nhiều tác vụ; toàn cluster còn lớn hơn.
7. **Lỗi/timeout/hủy có ngữ nghĩa gì?** Tác vụ ngoài có thể đã hoàn tất dù subscriber không nhận response.
8. **Giao dịch ở đâu?** Với JDBC thread-bound, đảm bảo transaction được quản lý trong phạm vi phù hợp.
9. **Context nào phải truyền?** Tracing, security, tenant ID có dựa vào ThreadLocal không?
10. **Đã kiểm thử load và adapter chưa?** Unit test Reactor không thay thế thử nghiệm với DB/broker thật.

## 18. Các hiểu nhầm phổ biến

| Hiểu nhầm | Cách hiểu đúng |
| --- | --- |
| “Dùng `Flux` thì mọi code đều non-blocking.” | `Flux` không thay đổi bản chất blocking của code trong callback. |
| “Thêm `subscribeOn` sau `Mono.just(blockingCall())` là đủ.” | Lời gọi đã chạy trước khi `just` nhận giá trị; phải tạo nguồn lazy. |
| “`Schedulers.parallel()` là pool tốt nhất cho JDBC.” | `parallel` dành cho công việc CPU/non-blocking; bounded elastic phù hợp hơn với blocking legacy. |
| “`Schedulers.immediate()` giúp rời event loop.” | `immediate` thực thi trên thread hiện tại. |
| “`publishOn` và `subscribeOn` như nhau.” | Một bên chuyển tín hiệu downstream, bên kia chủ yếu ảnh hưởng subscribe/upstream. |
| “boundedElastic tạo vô hạn thread nếu có việc.” | Đây là scheduler có giới hạn; queue/tải vẫn có thể bão hòa. |
| “Đặt `flatMap(..., 8)` là toàn cluster chỉ có tám request.” | Giới hạn tính theo toán tử/subscription; nhiều instance vẫn nhân tổng tải. |
| “`timeout` chắc chắn ngắt được JDBC đang chạy.” | Timeout của publisher không bảo đảm driver blocking đã hủy I/O hoặc rollback. |
| “`retry` không ảnh hưởng dữ liệu.” | Resubscription có thể thực thi lại side effect; cần idempotency. |
| “Đưa transaction qua nhiều Scheduler vẫn luôn giữ cùng thread.” | Transaction thread-bound có thể không theo qua các ranh giới thread. |
| “Dùng virtual thread thì không cần connection pool.” | Tài nguyên đích, transaction và rate limit vẫn có giới hạn. |
| “Unit test StepVerifier thành công là broker ack đúng.” | Cần integration test ở ranh giới adapter/transport. |

## 19. Câu hỏi tự đánh giá

1. Vì sao một `map(order -> jdbcRepository.save(order))` có thể làm nghẽn event loop?
2. Điểm khác nhau giữa `Mono.just(blockingClient.fetch())` và `Mono.fromCallable(blockingClient::fetch)` là gì?
3. Khi nào `Schedulers.parallel()` phù hợp hơn `Schedulers.boundedElastic()`?
4. Vì sao `Schedulers.immediate()` không phải giải pháp offload một API blocking?
5. `subscribeOn` và `publishOn` tác động tới những phần nào của pipeline?
6. Đặt `subscribeOn(boundedElastic)` ở cuối một nguồn hot có đảm bảo mọi callback `map` đều dùng bounded elastic không?
7. Khi có 100.000 event và database chỉ xử lý tốt 20 query đồng thời, ngoài `boundedElastic` cần những giới hạn gì?
8. Vì sao đặt `flatMap(..., 8)` vẫn có thể làm quá tải một API dùng chung ở nhiều instance?
9. Với `Mono.fromCallable(...)`, retry và subscribe lại có thể khiến side effect xảy ra nhiều lần như thế nào?
10. Vì sao timeout của publisher không bảo đảm một transaction JDBC đã rollback?
11. Khi dùng transaction đồng bộ thread-bound, vì sao nên gói các thao tác blocking trong một unit of work thay vì chèn nhiều `publishOn`?
12. Nếu tracing ID đang lưu trong `ThreadLocal`, cần xử lý gì khi chuyển Scheduler?
13. Vì sao một function tự `subscribe()` rồi trả `Flux.empty()` có thể khiến adapter thấy kết thúc quá sớm?
14. Cách nào giúp kiểm thử rằng blocking `Callable` chưa chạy trước khi subscribe?
15. Sự khác nhau giữa giới hạn thread của Scheduler, giới hạn concurrency của `flatMap` và giới hạn kết nối database là gì?
16. Với luồng sự kiện liên tục và một SDK có thể treo lâu, bạn sẽ đặt timeout và chính sách phục hồi ở những tầng nào?

## 20. Tài liệu tham khảo

- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): mô hình `Scheduler` và cách dùng `subscribeOn`/`publishOn`.
- [Project Reactor — FAQ: Wrapping a Synchronous, Blocking Call](https://projectreactor.io/docs/core/release/reference/faq.html#faq.wrap-blocking): mẫu `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`.
- [Project Reactor — Reference Guide](https://projectreactor.io/docs/core/release/reference/): toán tử Reactor, subscription, backpressure, context và lỗi.
- [Project Reactor — Testing](https://projectreactor.io/docs/test/release/reference/): `StepVerifier` và xác minh tín hiệu.
- [Spring Cloud Function — Programming Model](https://docs.spring.io/spring-cloud-function/reference/spring-cloud-function/programming-model.html): `Supplier`, `Function`, `Consumer` và chữ ký reactive.
- [Spring Cloud Stream — Producing and Consuming Messages](https://docs.spring.io/spring-cloud-stream/reference/spring-cloud-stream/producing-and-consuming-messages.html): trách nhiệm của binder, reactive functions và giới hạn ở ranh giới message.

Các ví dụ chọn cách diễn đạt có thể dùng với Java 17+ và Project Reactor hiện đại. Chi tiết cấu hình Scheduler, virtual threads, transaction manager và binder phụ thuộc phiên bản thư viện thực tế; cần đối chiếu dependency/BOM và thực hiện integration test trước khi triển khai.

**Ghi nhớ:** Tránh blocking bằng cách **ưu tiên client reactive**. Khi còn phụ thuộc JDBC, REST client hoặc SDK đồng bộ, hãy bọc thao tác thành publisher lazy như `Mono.fromCallable(...)` hoặc `Mono.fromRunnable(...)` và đặt `subscribeOn(Schedulers.boundedElastic())` **ngay tại ranh giới blocking**. `publishOn` chỉ chuyển ngữ cảnh các tín hiệu downstream, không sửa một lời gọi đã chạy eager. Scheduler không thay thế giới hạn concurrency, timeout, connection pool, transaction, idempotency và kiểm chứng hành vi thực tế của các adapter Spring Cloud Function.
