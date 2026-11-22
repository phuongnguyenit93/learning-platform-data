# Phân biệt đồng bộ, bất đồng bộ, chặn và không chặn

**Ngữ cảnh:** Spring Framework Reactive — Tổng quan.

Khi xử lý HTTP, truy vấn cơ sở dữ liệu hoặc gọi dịch vụ khác, có hai câu hỏi độc lập:

1. **Đồng bộ hay bất đồng bộ (synchronous/asynchronous)?** Người gọi nhận kết quả theo cách nào và ở thời điểm nào?
2. **Chặn hay không chặn (blocking/non-blocking)?** Trong lúc kết quả chưa sẵn sàng, luồng thực thi có phải dừng để đợi không?

Đây là **hai trục khác nhau**. Một lời gọi bất đồng bộ có thể vẫn chặn một luồng ở phía sau; một lời gọi không chặn cũng có thể là thao tác đồng bộ trả ngay trạng thái “chưa có dữ liệu”.

## 1. Hai trục cần tách bạch

### 1.1. Đồng bộ và bất đồng bộ: cách trả kết quả

- **Đồng bộ:** Người gọi thực hiện lời gọi và nhận kết quả/trạng thái của chính lần gọi đó trước khi chuyển sang bước phụ thuộc kết quả. Kết quả có thể là dữ liệu, lỗi, hoặc trạng thái “chưa sẵn sàng”. Khái niệm này **không tự nói** người gọi có phải đợi hay không.
- **Bất đồng bộ:** Người gọi khởi động/đăng ký thao tác rồi có thể tiếp tục công việc khác trước khi thao tác hoàn tất. Kết quả đến sau qua callback, sự kiện, `Future`/`CompletionStage`, hoặc `Mono`/`Flux` khi có subscription. Người nhận kết quả cần phối hợp luồng xử lý tiếp theo.

Ví dụ: `CompletableFuture.supplyAsync(...)` trả về một `CompletableFuture` ngay, trong khi công việc chạy ở executor. Nhưng nếu công việc gọi JDBC đồng bộ, luồng executor vẫn chờ truy vấn hoàn thành.

**Bất đồng bộ không đồng nghĩa với song song.** Một event loop đơn luồng có thể quản lý nhiều thao tác đang chờ I/O và chỉ xử lý sự kiện của từng thao tác khi sẵn sàng; bản thân từng callback vẫn chạy tuần tự trên luồng đó.

### 1.2. Blocking và non-blocking: luồng làm gì lúc phải chờ?

- **Blocking:** Một lời gọi giữ luồng hiện tại trong trạng thái chờ cho đến khi có dữ liệu, timeout hoặc lỗi. Trong lúc chờ, luồng ấy không thể xử lý công việc ứng dụng khác. Ví dụ `InputStream.read()` khi chưa có byte, `Thread.sleep(...)`, `Future.get()` khi tác vụ chưa hoàn tất, hoặc JDBC truy vấn đồng bộ.
- **Non-blocking:** Lời gọi không buộc luồng hiện tại chờ cho đến khi I/O hoàn tất. Nó có thể trả ngay “chưa sẵn sàng”, hoặc đăng ký nhận thông báo rồi nhường luồng cho việc khác. Ví dụ đọc `SocketChannel` ở chế độ non-blocking, hoặc gửi HTTP với `WebClient` và xử lý kết quả bằng chuỗi reactive.

“Không chặn” được xét **tại một thao tác, trên một luồng cụ thể**. Nó không có nghĩa toàn bộ hệ thống không có luồng nào từng chờ, không có hàng đợi, hoặc tác vụ xong ngay lập tức.

## 2. Ma trận bốn trường hợp

| | **Blocking** | **Non-blocking** |
|---|---|---|
| **Synchronous** | Gọi API rồi luồng hiện tại phải đợi kết quả. Ví dụ đọc `InputStream` / JDBC truyền thống. | Gọi API, nhận ngay dữ liệu hoặc “chưa có”; người gọi chủ động thử lại/đăng ký theo dõi. Ví dụ một lần `SocketChannel.read()` với `configureBlocking(false)`. |
| **Asynchronous** | Người gọi gửi việc cho executor rồi đi tiếp; **luồng worker** vẫn bị chặn khi gọi I/O đồng bộ. Ví dụ `CompletableFuture.supplyAsync(() -> legacyJdbcCall(), executor)`. | Người gọi đăng ký I/O; cơ chế sự kiện báo kết quả khi sẵn sàng, không giữ một luồng chờ riêng cho mỗi yêu cầu. Ví dụ `WebClient` dùng HTTP connector non-blocking trong WebFlux. |

Cùng một chương trình có thể chứa nhiều ô của ma trận. Chẳng hạn một yêu cầu HTTP xử lý bất đồng bộ nhưng gọi JDBC blocking trên pool riêng sẽ là **bất đồng bộ ở phía caller, blocking ở phía worker**.

### Mô hình thời gian

```text
Đồng bộ + blocking
caller: [gọi] ------- đợi I/O ------- [nhận dữ liệu] -> bước sau

Đồng bộ + non-blocking
caller: [gọi] -> [nhận "chưa sẵn sàng"] -> việc khác / chờ sự kiện / thử lại

Bất đồng bộ + blocking
caller: [gửi việc] -> việc khác ----------------> [nhận completion]
worker:            [gọi I/O] ---- đợi I/O ----> [hoàn tất]

Bất đồng bộ + non-blocking
event loop: [đăng ký I/O] -> xử lý yêu cầu khác -> [sự kiện sẵn sàng]
handler:                                            [xử lý kết quả]
```

Các dòng biểu diễn *điểm chờ và luồng bị chiếm*, không khẳng định mọi hệ điều hành/HTTP client luôn dùng đúng một số luồng cố định.

## 3. Phân tích từng trường hợp qua Java

### 3.1. Synchronous + blocking

```java
String response = legacyClient.fetch(); // API đồng bộ, giả sử gọi I/O blocking
System.out.println(response);            // chỉ chạy sau khi fetch hoàn tất
```

Đoạn này là **mã minh họa**, với `legacyClient` giả định là client blocking. Luồng gọi `fetch()` phải chờ I/O. Nếu đặt trực tiếp trong request handler và có nhiều yêu cầu chậm, nhiều luồng xử lý request sẽ cùng bị chiếm khi chờ.

### 3.2. Synchronous + non-blocking

```java
// channel là SocketChannel đã kết nối; buffer còn chỗ trống.
channel.configureBlocking(false);
int count = channel.read(buffer);

if (count > 0) {
    // Đã đọc được count byte trong lần gọi này.
} else if (count == 0) {
    // Hiện chưa đọc được byte; luồng không bị giữ để chờ byte đến.
} else {
    // count == -1: phía bên kia đã đóng luồng đọc (end of stream).
}
```

Đây là **mã minh họa một phần**, cần khai báo/khởi tạo `channel` và `buffer` trong chương trình thật. Lần gọi `read` trả kết quả **đồng bộ** (số byte hoặc trạng thái) nhưng không chặn đợi byte. Trong ứng dụng thật, phối hợp `Selector`/readiness để được báo khi có thể đọc; đừng dùng vòng lặp `while (read(...) == 0) {}` liên tục vì nó đốt CPU (busy polling).

Một ví dụ không liên quan I/O: `ConcurrentLinkedQueue.poll()` trả ngay phần tử hoặc `null` nếu hàng đợi rỗng. Đó là kiểu truy vấn đồng bộ, không chặn chờ phần tử xuất hiện.

### 3.3. Asynchronous + blocking

Đoạn Java 17 sau chạy độc lập. `Thread.sleep` **chỉ mô phỏng thời gian phải đợi I/O**, không phải network/database call thực tế:

```java
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class WaitingDemo {
    static String blockingCall() {
        try {
            Thread.sleep(100);
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Interrupted", e);
        }
        return "OK";
    }

    public static void main(String[] args) {
        System.out.println("sync=" + blockingCall());

        ExecutorService workers = Executors.newSingleThreadExecutor();
        try {
            CompletableFuture<String> job =
                    CompletableFuture.supplyAsync(WaitingDemo::blockingCall, workers);

            System.out.println("caller continues");
            System.out.println("async=" + job.join());
        } finally {
            workers.shutdown();
        }
    }
}
```

Lưu file `WaitingDemo.java`, rồi chạy:

```bash
javac WaitingDemo.java
java WaitingDemo
```

Kết quả chuẩn:

```text
sync=OK
caller continues
async=OK
```

Đường đi:

1. `blockingCall()` đầu tiên chạy đồng bộ, chặn luồng `main` khoảng 100 ms.
2. `supplyAsync` giao việc cho `workers` và trả về `job` ngay. `main` có thể in `caller continues`.
3. Luồng worker bị chặn bởi `sleep`. `job.join()` **có thể chặn chính luồng main** nếu kết quả chưa sẵn sàng.
4. Khi worker hoàn thành, `join()` trả chuỗi `OK`. `shutdown()` dừng nhận việc mới vào executor.

Vì vậy, “đã đưa vào `CompletableFuture`” chỉ chứng minh **caller nhận handle bất đồng bộ**; nó **không biến thao tác blocking bên trong thành non-blocking**. Trong dịch vụ thật, quản lý executor, giới hạn số luồng/hàng đợi và timeout khi gọi API blocking.

### 3.4. Asynchronous + non-blocking

Giả sử một HTTP client có connector non-blocking. Khi request được kích hoạt, client đăng ký I/O và hoàn tất lời gọi qua sự kiện khi response đến. Luồng event loop có thể xử lý nhiều kết nối trong lúc chờ mạng. Trong Spring, `WebClient` cùng chuỗi `Mono` là ví dụ điển hình:

```java
Mono<String> response = webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(String.class);

return response; // trong controller trả Mono<String>
```

Đây là **mã minh họa một phần**: `webClient` đã cấu hình base URL, `id` là biến sẵn có, và phương thức bao quanh trả `Mono<String>`. `bodyToMono` mô tả chuỗi xử lý; I/O thường bắt đầu khi publisher được **subscribe**. Trong WebFlux controller, framework quản lý subscription và ghi HTTP response. Không gọi `block()` để “lấy kết quả” bên trong controller reactive.

Lưu ý: “asynchronous” và “non-blocking” ở đây áp dụng cho **đường I/O dùng connector thích hợp**. Nếu lambda `map`/`flatMap` lại gọi JDBC blocking, một phần pipeline vẫn blocking.

## 4. Spring MVC và Spring WebFlux liên quan ra sao?

### 4.1. Mô hình request với nhiều lời gọi chậm

Giả sử 100 yêu cầu/giây, mỗi yêu cầu phải chờ dịch vụ ngoài khoảng 200 ms. Trung bình có thể có xấp xỉ `100 × 0,2 = 20` yêu cầu đang chờ tại một thời điểm (ước lượng đơn giản theo định luật Little khi ổn định).

- Trong mô hình **mỗi request gắn với luồng blocking**, nhiều luồng có thể chỉ chờ mạng. Việc tăng số luồng có giới hạn vì bộ nhớ và scheduling.
- Trong mô hình **event loop + non-blocking I/O**, một số ít luồng có thể quản lý nhiều kết nối chờ sự kiện. Ưu điểm chủ yếu là **sử dụng luồng/tài nguyên và khả năng chịu tải** khi độ trễ I/O cao, không phải làm mạng nhanh hơn.
- Nếu phần lớn thời gian là tính toán CPU nặng, non-blocking I/O không tự làm CPU nhanh lên. Nút cổ chai có thể chuyển sang CPU, DB pool, giới hạn dịch vụ ngoài hoặc khả năng kiểm soát tải.

Con số ví dụ chỉ minh họa số request đang chờ, **không phải benchmark** xác định Spring MVC cần chính xác 20 luồng hay WebFlux chỉ cần một luồng.

### 4.2. Spring MVC

Spring MVC truyền thống hoạt động với Servlet API và thường xử lý request bằng một luồng của server. API blocking như JDBC, `RestTemplate` hoặc client đồng bộ có thể giữ luồng ấy đến khi xong. Tuy nhiên MVC **cũng hỗ trợ kiểu trả kết quả bất đồng bộ** (ví dụ `Callable`, `DeferredResult`, kiểu reactive ở một số tích hợp). Do đó, “MVC = luôn đồng bộ” là kết luận sai.

Java virtual threads có thể giảm chi phí của nhiều tác vụ blocking trong một số cấu hình, nhưng **không thay đổi ngữ nghĩa blocking của API**. Cần đo đạc trước khi chọn chiến lược chạy production.

### 4.3. Spring WebFlux

Spring WebFlux thiết kế quanh xử lý **reactive, event-driven, non-blocking**. Với runtime như Reactor Netty, các event-loop worker phục vụ nhiều request và không nên bị chặn bởi I/O chậm. WebFlux có thể dùng annotated controller (`@RestController`) hoặc functional routes; điểm khác MVC là **mô hình thực thi và hợp đồng bất đồng bộ**, không phải chỉ cú pháp annotation.

Các thành phần quan trọng:

- `Mono<T>`: publisher có tối đa một phần tử (hoặc kết thúc rỗng/lỗi).
- `Flux<T>`: publisher có 0 đến nhiều phần tử.
- `WebClient`: HTTP client hỗ trợ composition bất đồng bộ và non-blocking I/O.
- **Reactive Streams backpressure:** consumer có thể yêu cầu lượng phần tử mà nó sẵn sàng xử lý. Đây là cơ chế điều tiết dòng dữ liệu, **không đồng nghĩa** mọi I/O tự hết blocking hoặc mọi nguồn bên ngoài đều hỗ trợ giảm tốc tương ứng.
- **Scheduler:** quyết định nơi thực thi một số phần công việc. `Mono`/`Flux` tự chúng không có nghĩa tạo thread mới, và nhiều toán tử chạy trên luồng phát tín hiệu hiện tại.

## 5. Minh họa controller WebFlux

Ví dụ sau là class Spring WebFlux đầy đủ về phần controller, dành cho **dự án Spring Boot đã có dependency `spring-boot-starter-webflux`**, và cần một dịch vụ `catalog-service` có endpoint phù hợp để request thành công:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.reactive.function.client.WebClient;
import reactor.core.publisher.Mono;

@RestController
public class ProductController {
    private final WebClient client;

    public ProductController(WebClient.Builder builder) {
        this.client = builder
                .baseUrl("http://catalog-service")
                .build();
    }

    @GetMapping("/products/{id}")
    public Mono<String> getProduct(@PathVariable String id) {
        return client.get()
                .uri("/products/{id}", id)
                .retrieve()
                .bodyToMono(String.class);
    }
}
```

Luồng hoạt động:

1. WebFlux gọi `getProduct`. Controller **trả publisher**, không đợi HTTP response từ catalog service trong thân phương thức.
2. Khi framework subscribe, `WebClient` gửi request qua connector HTTP non-blocking phù hợp.
3. Trong lúc đợi, event loop có thể xử lý các sự kiện khác. Khi response sẵn sàng, publisher phát dữ liệu hoặc lỗi.
4. WebFlux chuyển tín hiệu thành HTTP response của endpoint hiện tại. Nếu upstream lỗi, tín hiệu lỗi cần được xử lý qua chính sách xử lý lỗi của ứng dụng.

**Không khẳng định controller này là ứng dụng tự chạy độc lập:** còn cần Spring Boot app, dependency/runtime, DNS hoặc cấu hình địa chỉ dịch vụ ngoài. Việc trả `Mono` cũng không bảo đảm toàn pipeline non-blocking nếu một thành phần bên trong dùng API blocking.

Một ví dụ đơn giản, không cần dịch vụ ngoài, minh họa timer bất đồng bộ:

```java
@GetMapping("/delayed")
public Mono<String> delayed() {
    return Mono.delay(java.time.Duration.ofMillis(100))
            .map(tick -> "ready");
}
```

Đoạn method trên thuộc một `@RestController` WebFlux, không phải chương trình Java độc lập. `Mono.delay` lên lịch tín hiệu thời gian; nó không cần giữ một request thread ngủ bằng `Thread.sleep(100)`.

## 6. Xử lý API blocking bên trong pipeline reactive

Khi bắt buộc dùng thư viện blocking có sẵn, **cô lập công việc chặn trên scheduler dành cho blocking**:

```java
Mono<String> result = Mono
        .fromCallable(() -> legacyClient.fetch(id))
        .subscribeOn(Schedulers.boundedElastic());
```

Đây là **đoạn mã áp dụng** trong project có Reactor, `legacyClient` (API blocking), `id` và các import tương ứng (`Mono`, `Schedulers`). Ý nghĩa:

- `fromCallable` trì hoãn việc gọi `fetch(id)` đến lúc subscribe; không chạy eagerly ngay lúc tạo `Mono`.
- `subscribeOn(Schedulers.boundedElastic())` bố trí subscription/source execution lên scheduler phù hợp cho blocking work, tránh giữ event-loop thread trong `fetch`.
- **Bản thân `fetch` vẫn blocking** trên worker của `boundedElastic`. Scheduler có giới hạn về năng lực xử lý và công việc xếp hàng, nên cần quan sát tải, timeout và sức chứa downstream.
- Dùng driver/database client non-blocking thật sự, chẳng hạn R2DBC trong trường hợp phù hợp, mới tiến tới đường data-access non-blocking end-to-end.

**Sai lầm thường gặp:**

```java
// Sai: fetch() đã chạy ngay trên thread hiện tại trước khi tạo Mono.
Mono<String> bad = Mono.just(legacyClient.fetch(id))
        .subscribeOn(Schedulers.boundedElastic());

// Sai trong WebFlux request handler: có thể chặn event loop.
String value = webClient.get()
        .uri("/products/{id}", id)
        .retrieve()
        .bodyToMono(String.class)
        .block();
```

`Mono.just(...)` nhận giá trị **đã được tính**, còn `Mono.fromCallable(...)` nhận công việc để thực thi lúc subscribe. `block()`/`blockFirst()`/`blockLast()` chờ kết quả; trên các thread Reactor được đánh dấu non-blocking, lời gọi blocking có thể bị từ chối bằng `IllegalStateException`. Trong controller hãy compose bằng `map`, `flatMap`, `zip` và **return publisher**.

## 7. Những nhầm lẫn phổ biến

1. **“Async luôn non-blocking.”** Sai: `supplyAsync` có thể chạy JDBC blocking trên pool khác. Caller không đợi ngay, worker vẫn bị giữ.
2. **“Non-blocking nghĩa là tác vụ hoàn thành tức thì.”** Sai: mạng và DB vẫn có độ trễ; chỉ cách luồng xử lý thời gian đợi khác nhau.
3. **“Dùng `Mono` là tự tạo một thread.”** Sai: Reactor không tự tạo thread riêng cho từng publisher; lịch thực thi phụ thuộc nguồn, subscription, toán tử và scheduler.
4. **“Thêm `subscribeOn` biến JDBC thành driver non-blocking.”** Sai: chỉ thay nơi phần blocking chạy.
5. **“Gọi `subscribe()` ngay trong controller là cách xử lý chuẩn.”** Thường sai: dễ tách xử lý khỏi vòng đời HTTP, lỗi và hủy đăng ký; nên trả `Mono`/`Flux` để framework quản lý.
6. **“Non-blocking lúc nào cũng nhanh hơn.”** Sai: lợi thế tùy tỷ trọng I/O waiting, throughput, hệ thống downstream và chi phí điều phối; cần benchmark với workload thực tế.
7. **“Event loop không bao giờ chờ.”** Nói quá: loop có thể đợi hệ điều hành phát sự kiện bằng cơ chế readiness; ý quan trọng là **không cấp một thread bị giữ cho mỗi request chờ I/O**.
8. **“Chạy CPU nặng trên event loop vẫn ổn vì không có I/O.”** Sai: tính toán dài giữ event-loop worker bận, trì hoãn request khác; thiết kế tách CPU-bound work phù hợp.
9. **“Có backpressure nghĩa là có giới hạn từ đầu đến cuối.”** Không chắc: hàng đợi, producer, bộ đệm và dịch vụ ngoài phải có cơ chế kiểm soát tương ứng.

## 8. Cách phân loại một đoạn code khi review

Đừng suy luận chỉ từ tên method, annotation hoặc kiểu trả về. Hỏi theo thứ tự:

1. **Caller được trả gì ngay lúc gọi?** Dữ liệu/trạng thái của lần gọi (thường synchronous), hay handle/publisher cho kết quả trong tương lai (asynchronous)?
2. **Khi dữ liệu chưa đến, luồng nào đang đợi?** Request/event-loop thread, worker khác, hay không có worker bị giữ riêng cho thao tác I/O?
3. **API thực sự dùng I/O kiểu gì?** Blocking JDBC, `InputStream`, driver non-blocking, hay HTTP client reactive? `Executor`/`Scheduler` chỉ thay đổi vị trí thực thi.
4. **Có điểm nào chủ động chờ?** `get()`, `join()`, `block()`, `sleep()`, mutex, blocking queue `take()`... Chỉ cần một điểm này là đường xử lý tại đó có thể blocking.
5. **Ai hoàn tất và trả lỗi/hủy?** Callback/Future/Publisher có được trả về hoặc compose để framework quản lý không? Có timeout, cancellation, giới hạn kết nối và backpressure cần thiết chưa?

### Bài tập tự kiểm tra

| Tình huống | Phân loại đúng |
|---|---|
| `InputStream.read()` chạy ngay trên request thread và chờ byte | **Synchronous + blocking** tại lời gọi đọc |
| `SocketChannel` non-blocking: `read` trả 0 khi chưa có dữ liệu | **Synchronous + non-blocking** cho lần thử đọc |
| `CompletableFuture.supplyAsync(() -> jdbcQuery(), pool)` | **Asynchronous** với caller, nhưng **blocking** trên worker lúc JDBC chạy |
| `WebClient` non-blocking được trả dưới dạng `Mono` từ WebFlux controller | Điển hình **asynchronous + non-blocking I/O** sau subscription |
| `WebClient` bên trong lời gọi `.block()` | **Blocking** ở nơi gọi `block()`, dù tầng HTTP dùng non-blocking I/O |
| `Mono.fromCallable(blockingCall).subscribeOn(boundedElastic())` | Caller nhận publisher; **blocking** được dời sang worker của scheduler |
| `Flux.range(1, 3).map(x -> x * 2)` thông thường | Xử lý **đồng bộ trên luồng subscription** khi subscribe; không có I/O cần phân loại blocking/non-blocking |
| `Mono.delay(Duration.ofMillis(100))` | Timer **asynchronous**, không dùng `Thread.sleep` để giữ thread của request |

**Ghi nhớ:** đồng bộ/bất đồng bộ nói về **cách giao kết quả cho người gọi**; blocking/non-blocking nói về **cách sử dụng luồng trong thời gian chờ**. Spring WebFlux đạt hiệu quả khi các thao tác I/O trên đường request chủ yếu **bất đồng bộ và không chặn**, các công việc blocking được nhận diện và cô lập đúng chỗ.

## Tài liệu tham khảo

- Spring Framework — [Spring WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html), [Concurrency Model và Performance](https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html).
- Spring Framework — [WebClient](https://docs.spring.io/spring-framework/reference/web/webflux-webclient.html).
- Project Reactor — [Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html).
