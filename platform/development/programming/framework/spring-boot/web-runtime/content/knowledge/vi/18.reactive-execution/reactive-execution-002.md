# Event loop, Scheduler và phân biệt tác vụ I/O với tác vụ CPU

> **Ngữ cảnh:** Spring Boot web-runtime, đặc biệt là Spring WebFlux chạy trên Reactor Netty. Bài học giải thích mô hình thực thi reactive, nơi công việc chạy, cách nhận diện blocking/non-blocking I/O và CPU-bound, cách chọn `Scheduler` hợp lý, rồi thực hành bằng ứng dụng Java 17+ có thể chạy được.

## 1. Mục tiêu

Sau bài này, bạn có thể:

1. Diễn giải vai trò của **event loop** trong Netty và lý do một số ít thread có thể phục vụ nhiều kết nối HTTP khi thao tác I/O là non-blocking.
2. Phân biệt **I/O-bound** và **CPU-bound**; quan trọng hơn, phân biệt **blocking I/O** với **non-blocking I/O**. Không nhầm “I/O tốn thời gian” với “phải có một thread chờ”.
3. Hiểu sự khác nhau giữa Netty event loop và Reactor `Scheduler`; biết dùng `Schedulers.parallel()`, `Schedulers.boundedElastic()`, `publishOn`, `subscribeOn` đúng mục đích.
4. Biết vì sao `map`, `flatMap`, `Mono`, `Flux` không tự động bảo đảm tác vụ được chuyển sang thread khác.
5. Viết và kiểm tra Spring WebFlux controller không chặn event loop bởi code đồng bộ, đồng thời nhận diện các rủi ro về throughput, latency, số thread, hàng đợi, backpressure và cancellation.

## 2. Từ mô hình thread-per-request đến event loop

Trong mô hình Servlet xử lý request đồng bộ, một request thường chiếm một worker thread của container trong lúc handler chạy. Nếu handler gọi JDBC đồng bộ hoặc chờ HTTP đồng bộ trong 500 ms, worker thread đó thường phải đứng chờ kết quả. Khi nhiều request cùng chờ, container cần nhiều worker hoặc các request bắt đầu xếp hàng. Servlet vẫn có **asynchronous processing**, vì thế không nên nói mọi ứng dụng Servlet đều bắt buộc giữ thread liên tục đến hết response.

Spring WebFlux có thể chạy trên Servlet container nhưng thường được cấu hình cùng **Reactor Netty** khi dự án sử dụng `spring-boot-starter-webflux`. Trong cấu hình đó, Netty dùng một nhóm **event-loop thread** để xử lý các sự kiện I/O: kết nối đã sẵn sàng đọc, đã có byte nhận được, socket có khả năng ghi tiếp, kết nối đóng, v.v.

Hình dung event loop:

```text
              nhiều kết nối TCP / HTTP
                 /       |       \
              client A client B client C
                 \       |       /
             [Netty non-blocking sockets]
                        |
                  event-loop thread
                        |
       nhận readiness / đọc / dispatch callback /
       thực hiện đoạn xử lý ngắn / lên lịch ghi
                        |
               quay lại xử lý sự kiện khác
```

**Điểm mấu chốt:** event loop không tạo một thread cố định cho mỗi request. Thay vào đó, thread xử lý một công việc ngắn rồi quay lại xử lý các kết nối khác. Khi dữ liệu của một thao tác mạng **chưa sẵn sàng**, thread không cần chờ bằng lệnh blocking read; reactor/network stack có thể đăng ký sự kiện và tiếp tục phục vụ kết nối khác.

Ví dụ: nếu upstream trả lời sau 800 ms, một lời gọi `WebClient` non-blocking có thể chờ phản hồi **theo logic ứng dụng** trong 800 ms nhưng không cần chiếm một Java thread để ngủ suốt 800 ms. Kết quả được phát tiếp khi network event tương ứng đến.

### Hai việc không được nhầm

- **Concurrent I/O:** nhiều kết nối cùng đang chờ tiến triển I/O; một số ít event-loop thread có thể phục vụ chúng. Không đồng nghĩa các callback Java của tất cả kết nối chạy thật sự song song trên nhiều lõi.
- **Parallel CPU:** nhiều đoạn mã tính toán cùng thực sự chạy trên nhiều core. Để tận dụng đa lõi, cần phân phối các tác vụ CPU lên các worker thích hợp; chỉ tạo `Flux` không làm phép tính tự chạy song song.

Đặt `Thread.sleep(500)`, JDBC đồng bộ, `RestTemplate` đồng bộ hoặc phép tính CPU rất dài lên event loop sẽ khiến thread không thể xử lý các socket/callback khác trong khoảng đó. **Một request chặn event loop có thể làm chậm nhiều request không liên quan**, vì chúng có thể chia sẻ cùng event-loop thread.

## 3. I/O-bound, CPU-bound và hai kiểu I/O

**I/O-bound** nghĩa là thời gian hoàn tất công việc chủ yếu phụ thuộc tốc độ/độ trễ của hệ thống bên ngoài: mạng, database, file system hoặc dịch vụ từ xa. **CPU-bound** nghĩa là thời gian chủ yếu dành cho tính toán trên CPU: mã hóa, giải mã, nén, tính toán số học, biến đổi dữ liệu lớn, xử lý ảnh.

Tuy nhiên, phải hỏi thêm **API I/O có blocking hay non-blocking**:

| Loại công việc | Ví dụ trong ứng dụng Java | Khi chưa có kết quả | Cách xử lý trong WebFlux |
|---|---|---|---|
| Non-blocking network I/O | `WebClient` trên Reactor Netty, reactive driver tương thích | Đăng ký sự kiện; không cần thread đứng chờ kết quả mạng | Giữ pipeline reactive; thông thường **không cần** thêm `subscribeOn(boundedElastic())` chỉ vì có network I/O |
| Blocking I/O | JDBC đồng bộ, `RestTemplate`, SDK đồng bộ, `Files.readAllBytes`, `InputStream.read` có thể block | Thread gọi API bị giữ lại trong lúc chờ | Nếu chưa thể thay API, bọc thực thi lười (`fromCallable`) rồi `subscribeOn(Schedulers.boundedElastic())`; giới hạn đồng thời |
| CPU-bound ngắn | Kiểm tra điều kiện, ánh xạ DTO nhỏ, phép tính nhẹ | CPU hoạt động ngắn hạn | Có thể thực hiện trực tiếp khi chi phí nhỏ; tránh chuyển scheduler vô ích |
| CPU-bound nặng | Hash hàng triệu bản ghi, nén/biến đổi khối dữ liệu lớn, thuật toán dài | Thread đang chạy tính toán liên tục | Đưa việc CPU nặng khỏi event loop; cân nhắc `Schedulers.parallel()` hoặc executor CPU riêng cùng giới hạn concurrency |
| Cần cả I/O và CPU | Nhận dữ liệu từ mạng rồi giải nén, kiểm tra chữ ký, xử lý ảnh | Xen kẽ giai đoạn chờ I/O và giai đoạn tính toán | Giữ I/O reactive; tách rõ đoạn CPU tốn kém để chuyển scheduler tại ranh giới phù hợp |

Lưu ý: “file I/O” không mặc nhiên non-blocking chỉ vì ứng dụng dùng WebFlux. Nhiều API đọc file truyền thống vẫn là blocking. Tương tự, **JDBC qua `Mono.fromCallable` vẫn là JDBC blocking**; chỉ là phần chờ đã được chuyển khỏi event loop. R2DBC hướng tới kết nối database theo mô hình reactive non-blocking khi driver và đường thực thi hỗ trợ.

**Không có quy tắc “mọi I/O vào boundedElastic”.** Quy tắc đúng là *blocking I/O* cần được cô lập khỏi event loop; *non-blocking I/O* phát huy hiệu quả khi giữ nguyên đường xử lý bất đồng bộ.

## 4. Reactor `Scheduler` là gì và khác event loop như thế nào?

`Scheduler` trong Project Reactor là một abstraction dùng để **lên lịch thực thi** những tác vụ/callback của pipeline. Nó quyết định công việc được chạy bằng worker nào trong các trường hợp operator yêu cầu scheduling. Netty event loop lại là thành phần của network runtime quản lý sự kiện I/O trên socket. Hai thành phần có thể tương tác nhưng **không đồng nhất**.

Trong một request WebFlux chạy trên Reactor Netty, controller và nhiều operator thường bắt đầu trên event-loop thread. Nếu pipeline không có ranh giới bất đồng bộ hay chuyển scheduler khác, các phép biến đổi như `map` thường tiếp tục ở thread đang phát tín hiệu. Khi thêm `publishOn` hoặc `subscribeOn`, các phần liên quan có thể chuyển sang thread pool do Scheduler quản lý.

### Các Scheduler thường gặp

| Scheduler | Đặc tính | Nên dùng | Tránh |
|---|---|---|---|
| `Schedulers.immediate()` | Chạy ngay trên thread hiện tại, không tạo worker pool mới | Tình huống cần thực thi đồng bộ/no-op scheduling | Nghĩ rằng nó tách việc nặng khỏi event loop |
| `Schedulers.single()` | Scheduler dùng một thread chia sẻ | Công việc có lý do cần tuần tự trên một worker | Gửi nhiều blocking call hoặc phép tính kéo dài, vì gây nghẽn mọi tác vụ chia sẻ worker |
| `Schedulers.parallel()` | Pool hữu hạn, hướng tới công việc CPU, thường dựa trên số processor | Tính toán CPU ngắn đến vừa, tác vụ CPU có giới hạn | JDBC/`sleep`/HTTP blocking; CPU chạy vô hạn hoặc quá nhiều tác vụ dài |
| `Schedulers.boundedElastic()` | Pool có giới hạn tài nguyên và hàng đợi; phù hợp cách ly công việc blocking | API đồng bộ còn phải dùng: JDBC blocking, SDK synchronous, thao tác file blocking | Coi đây là “bể thread vô hạn”; đẩy lượng việc không kiểm soát khiến hàng đợi và latency tăng |
| `Schedulers.fromExecutorService(executor)` | Adapter cho executor do ứng dụng cấu hình | Khi cần thread pool riêng, quota, cô lập workload, naming/giám sát | Tự tạo executor vô hạn rồi quên shutdown |

Số thread và cách cài đặt chi tiết còn tùy phiên bản Reactor, cấu hình runtime và phần cứng. Ví dụ, `boundedElastic` có thể có chiến lược dùng platform thread hoặc virtual thread ở cấu hình/JDK hỗ trợ; **ngữ nghĩa “dùng cho blocking work với giới hạn” không thay đổi**. Cần đo thực tế, tránh dựa vào một con số thread mặc định bất biến.

### Một Scheduler có “làm cho code non-blocking” không?

Không. Khi `readLegacy()` là phương thức đồng bộ chặn thread, chạy nó trên `boundedElastic` chỉ **chuyển nơi bị chặn** sang thread được quản lý cho blocking work. Giải pháp này giữ event loop phản hồi tốt hơn, nhưng vẫn tốn thread và có giới hạn tối đa. Muốn non-blocking từ đầu cuối cần API/driver non-blocking và cách xử lý không block dọc toàn pipeline.

## 5. Assembly, subscription và nơi operator chạy

Một publisher có thể được **khai báo** (assembly) mà chưa thực thi công việc. Với publisher cold, công việc phát dữ liệu thông thường bắt đầu khi có **subscription**. Trong WebFlux, framework sẽ subscribe vào publisher do controller trả về để tạo HTTP response; bạn thường không cần gọi `subscribe()` thủ công trong handler.

```java
// Đoạn minh họa đặt trong một phương thức đã import Reactor.
Mono<String> source = Mono.fromCallable(() -> legacyCall());
Mono<String> result = source.map(String::toUpperCase);
// Chưa gọi legacyCall() chỉ vì đã khai báo source/result.
```

`Mono.just(legacyCall())` lại khác: biểu thức `legacyCall()` được Java đánh giá **ngay lúc tạo Mono**, trước khi `subscribeOn` có cơ hội thay đổi thread. Đây là lỗi thường gặp:

```java
// SAI nếu legacyCall() block: nó chạy ngay trên thread đang tạo Mono.
Mono.just(legacyCall()).subscribeOn(Schedulers.boundedElastic());

// ĐÚNG: defer lời gọi blocking cho đến khi subscribe rồi chạy trên worker phù hợp.
Mono.fromCallable(() -> legacyCall())
    .subscribeOn(Schedulers.boundedElastic());
```

Hai đoạn trên là ví dụ cú pháp, với `legacyCall()` đại diện một phương thức đồng bộ đã có, không phải chương trình Java độc lập.

### `subscribeOn` — điều phối hoạt động subscribe/upstream

`subscribeOn(scheduler)` tác động đến quá trình subscription và nguồn phát phía upstream. Đây là cách phổ biến để đẩy **blocking source** ra khỏi event loop:

```java
Mono.fromCallable(() -> blockingJdbcQuery())
    .subscribeOn(Schedulers.boundedElastic())
    .map(result -> transform(result));
```

Phần `blockingJdbcQuery()` chạy trên worker boundedElastic khi có subscription. Trong trường hợp thông thường, `map` nhận tín hiệu trên thread phát `onNext` đó, trừ khi có operator/scheduler khác đổi thread. Không cần gọi `subscribe()` thủ công trong controller.

### `publishOn` — đổi thread cho tín hiệu downstream

`publishOn(scheduler)` yêu cầu các tín hiệu sau điểm đó được xử lý trên worker thuộc scheduler được chọn, cho đến khi có thay đổi scheduling khác:

```java
Mono.fromCallable(() -> blockingJdbcQuery())
    .subscribeOn(Schedulers.boundedElastic())
    .publishOn(Schedulers.parallel())
    .map(result -> expensiveCpuTransform(result));
```

Vùng nguồn chờ JDBC là blocking work trên boundedElastic; vùng `map` CPU sau `publishOn(parallel())` được chuyển sang worker dành cho CPU. Ví dụ này minh họa toán tử; muốn chạy độc lập cần định nghĩa `blockingJdbcQuery` và `expensiveCpuTransform`.

**Cần nhớ:** `publishOn` không biến phép tính thành non-blocking và cũng **không tự chia một `map` lớn ra nhiều core**; nó chủ yếu đổi thread thực thi phần downstream. Nếu cần xử lý nhiều phần tử song song, phải thiết kế phân chia công việc và giới hạn concurrency.

### `map`, `flatMap` và `parallel()`

- `map`: hàm biến đổi **đồng bộ** trên tín hiệu hiện tại; `map(x -> slowBlockingCall(x))` vẫn block thread đang gọi nó.
- `flatMap`: mỗi phần tử có thể ánh xạ sang publisher khác và kết hợp kết quả; hữu ích để compose lời gọi non-blocking, nhưng `flatMap` **không tự chuyển** mã đồng bộ bên trong lambda sang pool riêng.
- `parallel()`: chia một `Flux` thành các rail; để thực sự lên lịch các rail trên workers CPU thường đi với `runOn(Schedulers.parallel())`, rồi `sequential()` nếu cần quay lại `Flux`. Chú ý chi phí chuyển thread, thứ tự kết quả và tài nguyên.
- `subscribe()` thủ công trong WebFlux controller thường tạo một luồng xử lý tách rời mà framework không chờ/cancel/propagate lỗi như response publisher. Nên **return publisher** để framework quản lý vòng đời request.

```java
// Ví dụ định hướng; giả sử cpuTransform(long) đã được định nghĩa.
Flux.range(1, 100)
    .parallel(4)
    .runOn(Schedulers.parallel())
    .map(i -> cpuTransform(i))
    .sequential();
```

Không mặc định cho rằng xử lý song song luôn nhanh hơn: với item nhỏ, chi phí xếp hàng, chuyển thread và gom tín hiệu có thể lớn hơn lợi ích.

## 6. Thực hành: một ứng dụng Spring Boot WebFlux chạy được

Dùng **ứng dụng Spring Boot WebFlux riêng** với Java 17+ và dependency `org.springframework.boot:spring-boot-starter-webflux`. Trong một dự án Gradle Spring Boot hiện có, dòng dependency tương ứng là:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
}
```

Đây là **mảnh cấu hình dependency**, dự án vẫn cần cấu hình Spring Boot/Gradle chuẩn từ ứng dụng của bạn. Để quan sát rõ Reactor Netty, tránh thêm đồng thời `spring-boot-starter-web`: nếu cả MVC và WebFlux cùng có mặt, Spring Boot thường ưu tiên cấu hình MVC làm loại web application, trừ khi có thiết lập khác.

Tạo file đầy đủ `src/main/java/example/reactive/ReactiveExecutionApplication.java`:

```java
package example.reactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@SpringBootApplication
public class ReactiveExecutionApplication {

    public static void main(String[] args) {
        SpringApplication.run(ReactiveExecutionApplication.class, args);
    }

    @RestController
    static class WorkController {

        // Chỉ để thử nghiệm cục bộ với port mặc định 8080.
        // Production: cấu hình URL service qua properties/injection.
        private final WebClient webClient =
                WebClient.create("http://localhost:8080");

        @GetMapping("/demo/echo")
        Mono<String> echo() {
            return Mono.just("pong");
        }

        @GetMapping("/demo/nonblocking-io")
        Mono<String> nonblockingIo() {
            // WebClient dùng network I/O reactive; không cần block().
            return webClient.get()
                    .uri("/demo/echo")
                    .retrieve()
                    .bodyToMono(String.class)
                    .map(body -> "webclient: " + body);
        }

        @GetMapping("/demo/blocking-io")
        Mono<String> blockingIo() {
            // Giả lập một SDK hoặc JDBC đồng bộ tốn 150 ms.
            // Thread.sleep chỉ phục vụ thí nghiệm, không dùng cho I/O thật.
            return Mono.fromCallable(() -> {
                        Thread.sleep(150);
                        return "legacy: ok";
                    })
                    .subscribeOn(Schedulers.boundedElastic());
        }

        @GetMapping("/demo/cpu")
        Mono<Long> cpu() {
            // Công việc CPU thuần; tính tổng 0..1_999_999.
            return Mono.fromCallable(() -> {
                        long sum = 0;
                        for (long i = 0; i < 2_000_000; i++) {
                            sum += i;
                        }
                        return sum;
                    })
                    .subscribeOn(Schedulers.parallel());
        }

        @GetMapping("/demo/threads")
        Mono<String> threads() {
            return Mono.defer(() -> {
                        String sourceThread = Thread.currentThread().getName();
                        return Mono.just("source=" + sourceThread);
                    })
                    .publishOn(Schedulers.parallel())
                    .map(value -> value + ", mapped="
                            + Thread.currentThread().getName());
        }
    }
}
```

**Giải thích từng endpoint:**

- `/demo/echo` là endpoint phụ dùng làm upstream giả lập. Nó trả `pong`.
- `/demo/nonblocking-io` gọi HTTP đến `/demo/echo` qua `WebClient` bằng API reactive; không gọi `block()` hoặc `sleep()`. Khoảng thời gian chờ socket được xử lý bởi network runtime.
- `/demo/blocking-io` dùng `Mono.fromCallable` để **trì hoãn** lời gọi đồng bộ, sau đó `subscribeOn(boundedElastic())` để tránh giữ Netty event loop 150 ms. Bản chất thao tác `Thread.sleep` vẫn là blocking.
- `/demo/cpu` thực hiện phép tính trên worker `parallel`. CPU không phải “I/O chờ”, nên chuyển nó sang boundedElastic chỉ vì handler trả `Mono` là lựa chọn thiếu cơ sở.
- `/demo/threads` ghi lại tên thread khi nguồn được subscribe và tại `map` sau `publishOn`. Với Reactor Netty thường thấy phần `source` có tên gần `reactor-http-nio-...` và phần `mapped` gần `parallel-...`, **nhưng tên thread/số thứ tự không phải API contract**; chúng phụ thuộc cấu hình, runtime và scheduler.

Trong terminal của dự án, chạy ứng dụng bằng `./gradlew bootRun` (Linux/macOS) hoặc `gradlew.bat bootRun` (Windows). Nếu dự án có lớp application chính khác, hãy dùng dự án thử nghiệm riêng hoặc cấu hình lớp main được chạy, tránh hai ứng dụng chính được phát hiện cùng lúc.

Dùng các lệnh kiểm thử (trên PowerShell dùng `curl.exe` để tránh alias `curl` của Windows PowerShell):

```bash
curl -s http://localhost:8080/demo/echo
curl -s http://localhost:8080/demo/nonblocking-io
curl -s http://localhost:8080/demo/blocking-io
curl -s http://localhost:8080/demo/cpu
curl -s http://localhost:8080/demo/threads
```

Nội dung body lần lượt của bốn request đầu, khi ứng dụng chạy ở port 8080:

```text
pong
webclient: pong
legacy: ok
1999999000000
```

Ở `/demo/threads`, **không cố định stdout/body tên thread**; hãy đối chiếu phần `source=` và `mapped=` trong response thực tế. Đường `/demo/cpu` tính đúng tổng `0 + 1 + ... + 1_999_999 = 1_999_999_000_000`.

**Giới hạn của thí nghiệm:** `Thread.sleep(150)` mô phỏng blocking I/O, không phải ví dụ về API đọc network/file thực; `WebClient` gọi loopback nhằm minh họa non-blocking HTTP chứ không đo hiệu năng production. Kết quả latency/throughput từ một request không chứng minh scheduler đã tối ưu: cần chạy đồng thời nhiều request và quan sát event-loop lag, CPU, thread pool, queue, timeouts.

## 7. Từng loại tác vụ nên đặt ở đâu?

### 7.1. Non-blocking I/O: compose publisher, không ép chuyển scheduler

```java
// Ví dụ trong một service đã inject WebClient:
Mono<UserDto> findUser(String userId) {
    return webClient.get()
            .uri("/users/{id}", userId)
            .retrieve()
            .bodyToMono(UserDto.class);
}
```

Đây là **mã minh họa trong service**, cần có field `WebClient webClient` và kiểu `UserDto`. `bodyToMono` trả publisher; WebClient quản lý I/O qua runtime async. Nếu gọi `findUser(id).block()` trong controller trên event loop, bạn đã biến toàn bộ chuỗi thành hoạt động chờ đồng bộ ở thread hiện tại và có nguy cơ bị Reactor từ chối trên thread non-blocking.

Với database, ưu tiên reactive driver phù hợp (ví dụ R2DBC) nếu toàn đường xử lý thật sự muốn non-blocking. Không nhầm `@Async`, trả `Mono` hoặc dùng `Flux` với việc driver phía dưới đã là non-blocking.

### 7.2. Blocking I/O: defer + boundedElastic + giới hạn

```java
// Ví dụ trong một service đã có LegacyRepository:
Mono<Report> loadLegacyReport(long id) {
    return Mono.fromCallable(() -> legacyRepository.load(id))
            .subscribeOn(Schedulers.boundedElastic());
}
```

`LegacyRepository` và `Report` là các kiểu của ứng dụng giả định; đoạn này minh họa pattern, không tự biên dịch riêng. Với JDBC, SDK blocking, API file blocking, wrapping tương tự giúp event loop rảnh hơn. Nhưng nếu có 10.000 request đồng thời, boundedElastic vẫn có giới hạn worker và hàng đợi; cần **pool database, timeout, bulkhead, concurrency limit** tương ứng.

Khi map nhiều phần tử sang blocking tasks, có thể giới hạn số tác vụ hoạt động:

```java
// Giả định blockingLoad(id) đã được định nghĩa; tối đa 8 inner publisher
// được flatMap subscribe đồng thời.
Flux.range(1, 100)
    .flatMap(id ->
            Mono.fromCallable(() -> blockingLoad(id))
                .subscribeOn(Schedulers.boundedElastic()), 8);
```

`flatMap(..., 8)` giúp chặn mở vô hạn lời gọi nội bộ trong pipeline này, nhưng không tự giới hạn tổng tải từ **tất cả HTTP request**. Cần thêm giới hạn ở cấp toàn ứng dụng nếu downstream có quota chung.

### 7.3. CPU-bound: tách khỏi event loop, kiểm soát số luồng

Với tính toán nặng trên từng item:

```java
// Giả định CPU tính toán cho từng item; minh họa không độc lập.
Flux.range(1, 100)
    .parallel(4)
    .runOn(Schedulers.parallel())
    .map(this::expensiveCpuWork)
    .sequential();
```

`parallel(4)` tạo tối đa bốn rail và `runOn` lên lịch tác vụ rail trên Scheduler. Đây là ví dụ phân chia công việc khi CPU có thể xử lý các phần độc lập. Nếu việc tính toán chỉ có **một nhiệm vụ lớn**, `subscribeOn(parallel())` hoặc `publishOn(parallel())` chỉ đưa nhiệm vụ đó sang một worker; nó không tự chia thuật toán ra nhiều core.

Các tác vụ CPU dài và có chi phí lớn dễ làm các thread `parallel()` bận; cân nhắc worker/executor riêng, batch job hoặc kiến trúc hàng đợi để tránh ảnh hưởng request khác. Thêm scheduler không tạo thêm năng lực CPU; số lõi vật lý vẫn là giới hạn.

### 7.4. Pipeline kết hợp blocking I/O và CPU

```text
HTTP request (event loop)
  -> Mono.fromCallable(blockingLoad)
        subscribeOn(boundedElastic)  [chờ JDBC/SDK đồng bộ]
  -> publishOn(parallel)             [biến đổi CPU nặng]
  -> kết quả Mono/Flux được WebFlux ghi response
```

Nếu thay `blockingLoad` bằng `WebClient` non-blocking hoặc truy vấn R2DBC reactive, bỏ phần offload blocking không cần thiết; chỉ chuyển đoạn CPU nặng ở điểm cần thiết. **Đừng đặt `publishOn(parallel())` trước một blocking call rồi mong nó trở thành non-blocking:** bạn chỉ đang chặn thread của pool CPU.

## 8. Timeline của request và tác động đến HTTP response

```text
T0: Netty event loop đọc request, WebFlux gọi handler
T1: Handler trả về Mono/Flux, framework subscribe vào response publisher
T2: I/O non-blocking: đăng ký/đọc sự kiện; phần cần chờ không giữ event loop
    hoặc blocking legacy: callable chạy trên boundedElastic
    hoặc CPU nặng: đoạn tính toán chạy trên parallel/custom pool
T3: Pipeline phát onNext / chuyển signal qua các operator
T4: Framework encode + ghi body; response có thể gửi dần khi streaming
T5: onComplete -> hoàn tất response bình thường
    onError -> lỗi; cancel -> subscription bị hủy (ví dụ client disconnect)
```

Đây là mô hình khái niệm. Thứ tự commit header, flush, I/O callback và `onNext` có thể khác giữa media type, codec, HTTP version, proxy và container. **Một operator chạy xong hoặc publisher `onComplete` không chứng minh trình duyệt đã đọc/hiển thị xong body.**

Với streaming response (`text/event-stream`, NDJSON), app có thể giữ HTTP response mở lâu để gửi nhiều item. Nếu từng item đi qua code CPU/blocking trên event loop, bạn có thể gây lag cho cả kết nối khác. Nếu upstream chậm, cần cân nhắc timeout và xử lý cancellation; nếu client chậm, cần quan sát buffering/backpressure, tránh giữ dữ liệu vô hạn trong RAM.

## 9. Lỗi phổ biến và cách sửa

| Lỗi | Vì sao nguy hiểm | Hướng sửa |
|---|---|---|
| Gọi `.block()`/`.blockFirst()` trong handler WebFlux chạy trên event loop | Giữ thread chờ, có thể ném lỗi do blocking trên `NonBlocking` thread | Trả trực tiếp `Mono`/`Flux` và compose bằng `flatMap`, `map`, `zip`, `then` |
| `Mono.just(legacy.load())` rồi `subscribeOn(boundedElastic())` | `legacy.load()` đã chạy đồng bộ ngay lúc assembly | Dùng `Mono.fromCallable(() -> legacy.load()).subscribeOn(boundedElastic())` |
| Dùng `map` chứa JDBC blocking | `map` chạy trên thread phát signal; nếu đó là event loop thì gây nghẽn | Tách nguồn blocking vào `fromCallable + subscribeOn(boundedElastic)` |
| Chạy `Thread.sleep` trên event loop hoặc `parallel()` | Giữ thread trong thời gian không làm việc | Với delay thuần reactive, dùng `Mono.delay`/`delayElement`; với thư viện synchronous thật, dùng pool blocking |
| Gửi mọi `WebClient` lên `boundedElastic` | Tạo scheduling/queue overhead cho nguồn vốn non-blocking | Giữ đường non-blocking; chỉ tách toán tử CPU/blocking thực sự cần |
| Gửi tác vụ CPU nặng lên `boundedElastic` và mở vô hạn | Tranh chấp CPU, pool/queue bị lấp, latency dao động | `parallel`/executor CPU riêng + concurrency bound/batch |
| Coi `flatMap` là “chạy trên thread khác” | Lambda đồng bộ vẫn chạy tại thread hiện tại | Nhìn operator nguồn có non-blocking không; đặt scheduler cho đoạn blocking |
| Thêm nhiều `publishOn` tùy ý | Tăng context-switch, hàng đợi và độ khó trace | Chuyển thread tại ranh giới công việc có lý do; benchmark |
| Tự `subscribe()` trong controller rồi trả `Mono.empty()` | Tác vụ tách khỏi response, lỗi/cancel khó theo dõi | Return publisher gắn với response; framework quản lý subscription |
| Dùng `ThreadLocal` để giữ security/trace context qua scheduler hop | Dữ liệu thread-local có thể mất hoặc nhầm giữa request | Dùng Reactor `Context`/framework context propagation và cơ chế security/tracing tích hợp |
| Block event loop vì encode JSON khối lớn hoặc log đồng bộ | Reactive network I/O không bảo vệ khỏi đoạn CPU/blocking trong callback | Đo CPU/serialization/logging; tách việc nặng, chia payload/stream phù hợp |

### Vì sao `Mono.delay` không giống `Thread.sleep`?

`Thread.sleep(1000)` giữ thread ngủ 1 giây. `Mono.delay(Duration.ofSeconds(1))` thiết lập timer và sau khoảng trễ phát tín hiệu khi được subscribe; nó không cần giữ thread ngủ cho toàn bộ khoảng chờ. Tuy nhiên, `Mono.delay` **không thể biến một JDBC query blocking thành non-blocking**; nó chỉ mô tả một timer.

### Vì sao test nhỏ có thể “vẫn chạy tốt”?

Khi chỉ có một request, ngay cả `Thread.sleep` trên event loop cũng có thể trả được response sau vài trăm mili giây. Vấn đề lộ ra khi nhiều connection chia sẻ event loop: request không liên quan bị tăng latency. Vì vậy cần tải đồng thời và quan sát tail latency (p95/p99), không chỉ lấy trung bình một request.

## 10. Cách quan sát và kiểm chứng

1. **Xác nhận runtime:** kiểm tra dự án thực dùng WebFlux + Reactor Netty hay Spring MVC + Servlet container. Thread name như `reactor-http-nio-...` thường gợi ý Netty nhưng tên thread không đủ làm bằng chứng duy nhất.
2. **Đo responsiveness:** bắn nhiều request `/demo/blocking-io` đồng thời và kiểm tra `/demo/echo` còn đáp ứng; so với một phiên bản cố ý chặn event loop trong môi trường thử nghiệm để nhìn ảnh hưởng. Không để phiên bản cố ý block ở production.
3. **Quan sát thread dump/metrics:** theo dõi event-loop threads, số worker `boundedElastic` đang bận, hàng đợi, mức dùng CPU, kích thước connection pool, timeout và throughput. Thread dump cho biết nơi đang block, cần kết hợp profiling khi phân tích CPU.
4. **Dùng logs với thread name một cách có chọn lọc:** log ở điểm nguồn, trước/sau `publishOn` và ở callback lỗi để biết code thực chạy ở đâu. Không giả định tất cả onNext của một request luôn dùng duy nhất một thread.
5. **Kiểm tra cancellation/error:** đóng client giữa lúc streaming, bảo đảm nguồn bên ngoài được hủy/cleanup. `doFinally(signal -> ...)` có thể hỗ trợ cleanup/quan sát terminal `ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL`; không tự coi cancel là thành công.
6. **Kiểm tra bằng integration test trên HTTP thực:** mock controller không đủ xác nhận event-loop lag, network flush, connection pool hay hành vi proxy. Một phản hồi đúng status/body không chứng minh không có blocking trong pipeline.
7. **Truy vết trước khi tối ưu:** xác định thời gian chờ I/O, thời gian CPU, pool pressure và proxy latency. Chỉ tăng số thread/đổi scheduler khi phép đo cho thấy bottleneck tương ứng.

Một số thư viện kiểm thử có thể phát hiện blocking calls trên các thread được đánh dấu non-blocking (ví dụ BlockHound ở môi trường tương thích), nhưng không thay thế profiling/load test và có giới hạn theo phiên bản JVM, instrumentation, thư viện.

## 11. Tình huống lựa chọn thiết kế

**Tình huống A — WebFlux gọi REST API từ xa bằng WebClient:** Giữ `Mono` do `WebClient` trả về, compose kết quả; không chờ bằng `.block()`. Thêm timeout, retry có điều kiện/idempotency và giới hạn request phù hợp; không chuyển sang boundedElastic chỉ vì HTTP có độ trễ.

**Tình huống B — WebFlux cần gọi thư viện JDBC cũ:** Thực hiện truy vấn trong `fromCallable`, dùng `subscribeOn(boundedElastic())`; theo dõi JDBC pool, timeout và giới hạn concurrency. Nếu cần end-to-end non-blocking, đánh giá chuyển driver/data stack phù hợp thay vì chỉ bọc bằng `Mono`.

**Tình huống C — Xử lý ảnh hoặc báo cáo CPU nặng:** Không tính trong Netty event loop. Đưa vào scheduler/executor CPU thích hợp, giới hạn số tác vụ chạy đồng thời; cân nhắc xử lý nền nếu thời gian quá dài so với vòng đời HTTP request.

**Tình huống D — SSE liên tục nhận dữ liệu từ upstream reactive:** Giữ luồng non-blocking, phát event theo media type phù hợp. Nếu mỗi event lại gọi API blocking, tách đoạn đó và giới hạn tài nguyên; xử lý cancel khi client ngắt và heartbeat/timeout khi cần.

**Tình huống E — Sử dụng Spring MVC thay cho WebFlux:** Servlet worker thread và async MVC có đặc điểm riêng; một `Mono` ở đâu đó trong code **không biến ứng dụng MVC thành Reactor Netty server**. Cần phân tích runtime thực tế trước khi áp dụng lời khuyên về event loop.

## 12. Câu hỏi tự kiểm tra

**1. WebClient cần 500 ms để nhận response, có cần một event-loop thread ngồi chờ 500 ms không?**  
Không. Với network I/O non-blocking, runtime đăng ký/nhận sự kiện khi có dữ liệu; request vẫn có latency 500 ms nhưng thread có thể xử lý việc khác trong khi chờ.

**2. `Mono.just(jdbcRepository.load())` rồi `subscribeOn(boundedElastic())` đã bảo vệ event loop chưa?**  
Chưa. `load()` chạy ngay lúc tạo `Mono`; phải dùng nguồn lazy như `Mono.fromCallable(() -> jdbcRepository.load()).subscribeOn(boundedElastic())`.

**3. `Schedulers.parallel()` có phải nơi phù hợp để đặt `Thread.sleep` hoặc JDBC blocking?**  
Không. Pool này dành cho CPU work; blocking khiến worker CPU bị giữ lại. Blocking API nên được cô lập trên boundedElastic hoặc executor blocking được quản lý.

**4. `publishOn(parallel())` có biến một phép tính đơn khối thành tính toán đa lõi không?**  
Không. Nó chuyển vùng downstream sang worker khác; muốn chia đa lõi phải chia dữ liệu/thao tác thành các công việc độc lập với concurrency phù hợp.

**5. `flatMap(id -> legacyBlocking(id))` có tự động thực thi `legacyBlocking` trên thread khác không?**  
Không. Nếu lambda gọi một phương thức blocking để tạo dữ liệu, lời gọi đó vẫn diễn ra đồng bộ ở thread hiện tại. Cần defer vào publisher phù hợp, rồi chọn scheduler cho đoạn blocking.

**6. Nếu offload hết blocking I/O sang `boundedElastic`, hệ thống có chắc chịu được vô hạn request không?**  
Không. Thread và hàng đợi của scheduler có giới hạn; database/HTTP pool, CPU, memory, downstream capacity và timeout vẫn giới hạn throughput.

**7. Có nên đoán event loop dựa vào tên thread và giả định thread không bao giờ đổi?**  
Không. Tên thread chỉ hữu ích khi debug; `publishOn`, `subscribeOn`, driver và callback khác có thể thay đổi thread. Quan sát runtime thực và không phụ thuộc thread affinity ngầm định.

## 13. Tài liệu để đối chiếu

- [Spring Framework Reference — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): mô hình thực thi, concurrency và non-blocking của WebFlux.
- [Spring Framework Reference — Execution Model](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html#webflux-concurrency-model): so sánh mô hình WebFlux với Servlet và cách xử lý blocking.
- [Project Reactor Reference — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): `Schedulers`, `publishOn`, `subscribeOn`, ý nghĩa thread boundaries.
- [Project Reactor Reference — Parallelizing Work](https://projectreactor.io/docs/core/release/reference/advancedFeatures/advanced-parallelizing-parralelflux.html): `parallel`, `runOn`, `sequential`.
- [Reactor Netty Reference — HTTP Server](https://projectreactor.io/docs/netty/release/reference/http-server.html): Reactor Netty HTTP server, event-loop resources và cấu hình liên quan.
