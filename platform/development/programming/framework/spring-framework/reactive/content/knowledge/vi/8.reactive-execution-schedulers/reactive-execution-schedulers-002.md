# Mô hình event loop và tác hại của lệnh chặn

Trong **Spring WebFlux**, đặc biệt khi chạy với **Reactor Netty**, nhiều kết nối HTTP có thể được phục vụ bằng một số lượng tương đối nhỏ các luồng xử lý sự kiện (*event-loop workers*). Cách vận hành này hiệu quả khi ứng dụng **không giữ luồng để đợi I/O**: luồng đăng ký công việc, tiếp tục xử lý những sự kiện khác, rồi nhận thông báo khi kết quả sẵn sàng.

Một lệnh **blocking** như `Thread.sleep`, chờ kết quả `Future.get` hoặc gọi JDBC đồng bộ có thể giữ một event-loop worker trong lúc không làm được việc hữu ích. Trong khoảng đó, những kết nối và callback khác được phân cho worker ấy có thể phải chờ. Tác hại lớn nhất thường là **độ trễ tăng, thông lượng giảm và lỗi timeout dây chuyền khi hệ thống chịu tải**, ngay cả khi CPU chưa dùng hết.

Bài này giải thích cơ chế event loop, nhận diện các dạng blocking, cách phối hợp Reactor `Scheduler`, và cách xử lý API đồng bộ còn tồn tại trong một ứng dụng reactive.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Mô tả event loop xử lý sự kiện I/O và phân biệt việc **đợi bất đồng bộ** với **giữ luồng để đợi**.
2. Giải thích tại sao WebFlux thường cần ít worker hơn mô hình cấp luồng cho từng yêu cầu, đồng thời nhận biết giới hạn của cách so sánh này.
3. Chỉ ra các thao tác có thể chặn worker: `block()`, `Thread.sleep`, JDBC, HTTP client đồng bộ, file I/O, lock contention và công việc CPU quá nặng.
4. Phân biệt `Schedulers.parallel()`, `Schedulers.boundedElastic()`, `subscribeOn` và `publishOn`; chọn cách chuyển ngữ cảnh thực thi thích hợp.
5. Bao một API blocking bằng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`, giới hạn concurrency và giữ chuỗi lỗi/hủy.
6. Viết handler WebFlux trả `Mono` hoặc `Flux` mà không gọi `subscribe()` hoặc `block()` tùy tiện.
7. Quan sát dấu hiệu nghẽn event loop và kiểm thử luồng thực thi bằng Reactor Test.

## 2. Event loop hoạt động như thế nào?

Một event loop là một vòng xử lý sự kiện. Trong hệ thống network không chặn, nó có thể:

- Theo dõi nhiều kết nối/socket và nhận biết khi có sự kiện đọc, ghi hoặc kết nối sẵn sàng.
- Nhận sự kiện, chạy một đoạn xử lý ngắn, cập nhật trạng thái/kết quả và đăng ký công việc bất đồng bộ tiếp theo.
- Trả quyền điều khiển nhanh để worker tiếp tục xử lý những kết nối, timer và callback khác.

Sơ đồ tư duy đơn giản:

~~~text
                Nhiều kết nối HTTP
                  /     |      \
                 A      B       C
                  \     |      /
                 Hàng sự kiện sẵn sàng
                          |
                   Event-loop worker
                          |
                Nhận -> xử lý ngắn
                          |
             +------------+-------------+
             |                          |
       Dữ liệu có sẵn          Cần I/O bất đồng bộ
             |                          |
       Phát tín hiệu           Đăng ký callback/
       hoặc ghi socket         trạng thái chờ I/O
             |                          |
       Trở về event loop       Trở về event loop
                                        |
                              I/O hoàn tất về sau
                                        |
                              Sự kiện mới được xử lý
~~~

Đây là sơ đồ khái niệm, không cố mô tả toàn bộ chi tiết Reactor Netty. Event loop không có nghĩa **mọi kết nối dùng chung đúng một thread**. Runtime thường có **nhiều worker**; một worker có thể xử lý nhiều kết nối theo mô hình multiplexing. Một request cũng **không nhất thiết bám mãi vào một thread**: pipeline Reactor có thể chuyển ngữ cảnh qua scheduler, và callback nguồn ngoài có thể chạy trên thread khác.

### “Non-blocking” chính xác là gì?

Với một thao tác đợi network:

- **Blocking:** thread gọi thao tác rồi nằm chờ cho đến khi có dữ liệu hoặc timeout; trong thời gian chờ nó không phục vụ công việc khác.
- **Non-blocking/asynchronous:** thao tác được khởi động hoặc đăng ký; thread có thể rời đi. Khi dữ liệu đã sẵn sàng, hệ thống lên lịch callback/sự kiện để tiếp tục xử lý.

**Bất đồng bộ không tự đồng nghĩa với non-blocking.** Có thể chạy một lời gọi blocking trên worker pool khác và trả kết quả bằng `Mono`; caller có vẻ bất đồng bộ, nhưng một worker trong pool kia **vẫn bị giữ** để đợi. Giải pháp đó giúp **cô lập** blocking khỏi event loop, chưa biến API blocking thành I/O không chặn thật sự.

## 3. WebFlux khác mô hình thread-per-request ở đâu?

Spring WebFlux hỗ trợ luồng lập trình reactive với `Mono`, `Flux` và Reactive Streams. Khi chạy trên một non-blocking server như Reactor Netty, nó giả định xử lý request **không chặn**, nhờ đó có thể dùng một nhóm event-loop workers tương đối nhỏ.

Trong ứng dụng servlet truyền thống, một request blocking thường giữ một thread từ request pool trong lúc chờ I/O. Server có thể dùng pool lớn hơn để chịu nhiều request đang chờ; đổi lại, mỗi thread, context switch và queue cũng tiêu tốn tài nguyên. Spring MVC hiện đại còn có các cơ chế bất đồng bộ riêng; không nên kết luận rằng mọi Spring MVC request đều cần một thread bị khóa cho đến lúc hoàn tất.

| Góc nhìn | Worker event loop không chặn | Request dùng lời gọi blocking |
| --- | --- | --- |
| Trong lúc đợi network/database | Có thể trả worker về vòng xử lý sự kiện | Thread gọi thường nằm chờ |
| Mô hình tải chính | Sự kiện/callback trên nhiều kết nối | Nhiều thread hoặc pool để hấp thu thời gian chờ |
| Tác vụ xử lý dài | Gây nghẽn worker dùng chung | Gây nghẽn thread/pool riêng cho request |
| Chi phí cần quản lý | Event-loop latency, scheduler, queues, demand | Pool, queue, thread stack, context switching |
| Khi API đồng bộ bắt buộc | Chuyển sang scheduler/adapter phù hợp | Có thể thực thi trong thread pool blocking có kiểm soát |

**WebFlux không chạy trên “0 thread” và không tự làm mọi thư viện trở thành reactive.** WebFlux cũng có thể chạy trên các server dựa trên Servlet API hỗ trợ non-blocking I/O. Cấu hình và số lượng worker thực tế phụ thuộc runtime, tài nguyên và cách triển khai; tránh suy ra số thread cố định cho mọi máy.

## 4. Vì sao chỉ một lệnh chặn cũng nguy hiểm?

Giả sử event-loop worker W đang xử lý nhiều kết nối:

~~~text
Thời gian  --->

Không chặn:
W: [A: bắt đầu I/O][B: xử lý][C: xử lý][A: I/O xong][D: xử lý]...

Có blocking trong A:
W: [A: Thread.sleep(500 ms)........................][B][C][D]...
                    B, C, D phải chờ W rảnh
~~~

Nếu một handler chặn 500 ms, các sự kiện khác cần chính worker đó có thể chờ thêm tới hàng trăm mili giây ngay cả khi chúng chỉ cần xử lý rất nhanh. Nếu **nhiều** worker cùng bị chặn, thời gian chờ của toàn server có thể tăng đột ngột.

Tác động thường thấy:

1. **Latency và tail latency:** p95/p99 tăng, người dùng thấy request ngắn cũng chậm vì chờ worker.
2. **Throughput:** số sự kiện được xử lý mỗi giây giảm; tăng số kết nối không giải quyết được điểm nghẽn worker.
3. **Timeout nối tiếp:** client hết thời gian, retry làm tăng tải, queue/phản hồi tiếp tục chậm.
4. **Bộ nhớ và backlog:** các callback, request hoặc dữ liệu chờ được giữ lại; giới hạn queue có thể bị chạm.
5. **Lỗi khó truy vết:** log chỉ thấy “dịch vụ chậm”, trong khi nguyên nhân là một đoạn đồng bộ nhỏ nằm sâu trong pipeline.

**Không phải mọi công việc CPU đều là blocking I/O**, nhưng một phép tính CPU kéo dài cũng **chiếm worker và ngăn event loop xử lý kết nối khác**. Vì vậy nguyên tắc thực tế là: **giữ callback trên event loop ngắn, không chặn và không tính toán quá nặng**.

## 5. Nhận diện các loại công việc gây nghẽn

| Hành động trong handler/operator | Đặc tính | Điều cần chú ý |
| --- | --- | --- |
| `Thread.sleep(500)` | Chặn thread hiện tại trong thời gian ngủ | Không dùng để chờ timer trong luồng reactive. |
| `mono.block()`, `flux.blockFirst()`, `blockLast()` | Chờ đồng bộ publisher phát kết quả/kết thúc | Trên non-blocking thread của Reactor thường bị từ chối bằng `IllegalStateException`. |
| `Future.get()`, `CompletableFuture.join()` | Có thể chặn khi kết quả chưa sẵn sàng | Không đồng nghĩa đã có API non-blocking end-to-end. |
| JDBC, HTTP client đồng bộ, synchronous file read | Chặn trong lúc I/O hoặc đợi resource | Dùng driver reactive thích hợp hoặc cách cô lập blocking. |
| Chờ lock, semaphore, queue, `synchronized` đang tranh chấp | Có thể làm worker bị giữ | Tránh đoạn critical section dài/đợi lock trên event loop. |
| Vòng lặp CPU nặng, JSON cực lớn, nén/mã hóa tốn CPU | Chiếm CPU liên tục; có thể không gọi API blocking | Tách khỏi event loop, giới hạn song song và đo CPU. |
| `Mono.delay(Duration)` | Đặt timer theo scheduler; không cần giữ thread ngủ trong toàn thời gian chờ | Phù hợp để mô hình hóa việc trì hoãn tín hiệu, không thay cho I/O thực. |
| `WebClient` với API reactive | Có thể dùng non-blocking network I/O | Chỉ non-blocking khi cả chuỗi callback/mapper không chứa thao tác chặn. |

Một số API có kết quả ngay thì `Future.get` không cần đợi; một lock không tranh chấp có thể vào nhanh. Vấn đề là **khả năng giữ worker lâu khi dữ liệu/tài nguyên chưa sẵn sàng**, đặc biệt dưới tải.

### Không hiểu nhầm các cơ chế bảo vệ

Reactor đánh dấu các thread của `Schedulers.parallel()` và `Schedulers.single()` là loại không cho thực hiện các thao tác chờ blocking của chính Reactor. Gọi `block()` trên những thread được đánh dấu *non-blocking* thường ném `IllegalStateException`. Các event-loop thread của Reactor Netty cũng thường được đánh dấu tương tự.

Tuy nhiên, `Thread.sleep` hoặc lời gọi JDBC **không tự động bị Reactor phát hiện và chặn lại** chỉ nhờ đang chạy trên event loop. Chúng có thể làm worker đứng chờ thực sự. Công cụ phát hiện blocking khi chạy test có thể hỗ trợ, nhưng không nên dựa vào một ngoại lệ runtime để thay thế kiểm tra thiết kế.

## 6. Mono/Flux không tự tạo thread mới

Một hiểu nhầm phổ biến:

~~~java
Mono<String> value = Mono.just("hello")
    .map(text -> text.toUpperCase());
~~~

Đoạn này là Reactor pipeline. Trong phần lớn trường hợp, nếu không có scheduler riêng hoặc nguồn bất đồng bộ đặc biệt, các operator sẽ chạy trên thread đang phát tín hiệu/đăng ký, chứ **không có thread mới chỉ vì dùng Mono**.

Tương tự:

~~~java
Mono<String> slow = Mono.fromCallable(() -> legacyClient.load());
~~~

`Mono.fromCallable` chỉ trì hoãn việc gọi `legacyClient.load()` đến lúc subscribe. Nếu nguồn được subscribe trên một event-loop worker, lời gọi blocking có thể chạy **ngay trên worker đó**. Dùng `Mono.fromCallable` **chưa đủ** để xử lý blocking; cần điều khiển nơi tác vụ chạy.

Cũng tránh:

~~~java
Mono<String> wrong = Mono.just(legacyClient.load());
~~~

Ở đây `legacyClient.load()` được Java gọi **ngay khi xây dựng pipeline**, trước cả subscription, nên có thể chặn ngay thread gọi phương thức handler. Hai ví dụ này giả định `legacyClient` là API đồng bộ có sẵn trong ứng dụng; chúng chỉ minh họa phương thức, chưa phải chương trình độc lập.

## 7. Các Scheduler Reactor và cách chọn

Reactor cung cấp `Scheduler` để điều khiển ngữ cảnh thực thi:

| Scheduler | Mục đích chính | Không nên hiểu là |
| --- | --- | --- |
| `Schedulers.immediate()` | Thực thi ngay trong ngữ cảnh thread hiện tại | Một pool thread mới |
| `Schedulers.single()` | Một worker tái sử dụng để thực thi tuần tự | Nơi phù hợp cho I/O blocking hoặc tính toán dài |
| `Schedulers.parallel()` | Pool giới hạn theo CPU để xử lý công việc CPU-bound có kiểm soát | Pool dành cho các lời gọi blocking |
| `Schedulers.boundedElastic()` | Cô lập công việc I/O đồng bộ/blocking còn phải sử dụng | Tài nguyên vô hạn hoặc chuyển API thành non-blocking |
| `Schedulers.fromExecutorService(...)` | Tích hợp pool do ứng dụng quản lý | Pool tự động có quota/concurrency phù hợp nếu chưa cấu hình |

`boundedElastic` giới hạn số thread và có queue cho tác vụ chờ. Khi tải tăng vượt sức chịu đựng, tác vụ vẫn có thể **xếp hàng và trễ hoặc bị từ chối**. Nó không chữa được dịch vụ downstream thiếu công suất. Cấu hình cụ thể phụ thuộc phiên bản Reactor, CPU và lựa chọn runtime; đo và giới hạn cả connection pool/concurrency.

### `subscribeOn` và `publishOn` khác nhau ra sao?

**`subscribeOn(scheduler)`** tác động lên quá trình subscription và việc thực thi source có thể được lịch hóa. Reactor thường khuyến nghị đặt nó **ngay sau source blocking** để việc chuyển thread rõ ràng:

~~~java
Mono<String> safe = Mono.fromCallable(() -> legacyClient.load())
    .subscribeOn(Schedulers.boundedElastic());
~~~

**`publishOn(scheduler)`** chuyển việc phát tín hiệu **sang worker của scheduler đó cho các operator phía sau vị trí đặt** (cho đến khi có chuyển đổi khác):

~~~java
Flux<Integer> computed = Flux.range(1, 100)
    .publishOn(Schedulers.parallel())
    .map(this::cpuIntensiveTransform);
~~~

Đây là đoạn tích hợp: `cpuIntensiveTransform` là phương thức của ứng dụng. `publishOn` phù hợp khi muốn chuyển phần tính toán **phía sau** nó khỏi event loop. Nếu phép tính nặng nằm **trước** `publishOn`, phép tính đó không được bảo vệ bằng việc chuyển scheduler ở phía sau.

**Đừng đặt `publishOn` hoặc `subscribeOn` rải rác không có lý do.** Mỗi ranh giới bất đồng bộ có chi phí điều phối, queue và thay đổi bối cảnh thread; thêm quá nhiều có thể làm tăng độ trễ hoặc mất khả năng dự đoán khi debug. Chúng cũng không thay thế giới hạn tải và cancellation.

## 8. Mẫu đúng khi buộc phải gọi API blocking

Cách Reactor khuyến nghị cho một lời gọi đồng bộ:

~~~java
Mono<Result> result = Mono.fromCallable(
        () -> legacyRepository.lookup(id))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Đây là snippet tích hợp, cần định nghĩa `Result` và `legacyRepository`. Ý nghĩa:

1. `fromCallable` giữ lời gọi đồng bộ bên trong publisher **lazy**, chỉ chạy khi có subscription.
2. `subscribeOn(boundedElastic)` chỉ định worker thích hợp để thực hiện source, giúp không giữ event-loop worker trong lúc gọi API đồng bộ.
3. Kết quả thành công được phát dưới dạng `onNext` rồi `onComplete`. Nếu `Callable` trả `null`, `Mono.fromCallable` hoàn tất rỗng; nếu ném exception, Reactor phát `onError`.
4. Subscriber WebFlux có thể tiếp tục ghép `map`, `flatMap`, `timeout` và xử lý HTTP response mà không cần chờ đồng bộ bằng `block()`.

Nếu nguồn có nhiều phần tử, có thể dùng `Flux.defer` hoặc `Flux.fromIterable` kết hợp adapter thích hợp, nhưng cần kiểm soát **đúng phạm vi của lời gọi blocking**. Chuyển nguyên một pipeline phức tạp sang pool khác có thể làm tải blocking lẫn CPU cùng dồn lên một queue lớn.

### Tại sao không đơn giản gọi `subscribe()` thủ công?

~~~java
public Mono<String> incorrect() {
    legacyWork().subscribe();
    return Mono.just("done");
}
~~~

Ví dụ này chỉ là snippet tích hợp với `legacyWork()` do ứng dụng định nghĩa. Handler trả `"done"` có thể hoàn tất **trước khi tác vụ thật sự xong**; lỗi, cancel và timeout bị tách khỏi lifecycle request. Trong WebFlux, **trả lại publisher đã ghép** cho framework subscribe và quản lý:

~~~java
public Mono<String> correct() {
    return legacyWork().thenReturn("done");
}
~~~

Nếu `legacyWork()` thực sự dùng thư viện blocking, nó vẫn cần được offload **bên trong** service đó. `thenReturn` chỉ nối luồng tín hiệu thành công, không tự chọn scheduler.

## 9. Chương trình Java 17 chạy được: timer non-blocking và blocking đã được cô lập

Ví dụ này có hai công việc:

- Một lời gọi “legacy” giả lập bằng `Thread.sleep`, chạy trong `boundedElastic`.
- Một timer bằng `Mono.delay`; trong thời gian trì hoãn không cần giữ một worker bằng `Thread.sleep`.

Tạo `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.6.8'
    testImplementation 'io.projectreactor:reactor-test:3.6.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.3'
}

application {
    mainClass = 'EventLoopDemo'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Tạo `src/main/java/EventLoopDemo.java`:

~~~java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public class EventLoopDemo {
    public static void main(String[] args) {
        Mono<String> legacy = Mono.fromCallable(() -> {
            Thread.sleep(40); // Giả lập I/O đồng bộ; chỉ chạy trên boundedElastic.
            return "legacy-ok";
        }).subscribeOn(Schedulers.boundedElastic());

        Mono<String> timer = Mono.delay(Duration.ofMillis(20))
            .thenReturn("timer-ok");

        Mono<String> combined = Mono.zip(legacy, timer)
            .map(pair -> pair.getT1() + " | " + pair.getT2());

        System.out.println("pipeline assembled");
        String result = combined.block(Duration.ofSeconds(5));
        System.out.println("result = " + result);
    }
}
~~~

Chạy trong thư mục dự án bằng `gradle run`. Nếu có Gradle Wrapper, dùng `./gradlew run` (trên Windows dùng `gradlew.bat run`). **Stdout của chương trình**, không tính log riêng của Gradle:

~~~text
pipeline assembled
result = legacy-ok | timer-ok
~~~

**Vì sao output ổn định?**

- Việc tạo `Mono` và ghép `Mono.zip` không thực hiện `Callable` hay timer ngay lập tức.
- `block(Duration.ofSeconds(5))` trong **hàm main của ứng dụng command-line** subscribe và chờ kết quả để chương trình có thể in; không dùng cách này trong handler WebFlux.
- `Mono.zip` đợi **cả hai Mono phát giá trị**. Timer có thể hoàn tất trước hoặc sau legacy tùy môi trường, nhưng tuple vẫn chứa `legacy` ở vị trí 1 và `timer` ở vị trí 2.
- `thenReturn("timer-ok")` bỏ giá trị tick của `Mono.delay`, chỉ phát chuỗi sau khi timer hoàn tất.
- Không in tên thread hoặc thời điểm hoàn tất từng nhánh vì những chi tiết đó phụ thuộc lịch thực thi, không nên khẳng định một thứ tự stdout không được bảo đảm.

Đây là ví dụ mô phỏng tính năng offload, **không phải một benchmark**: `Thread.sleep(40)` không đại diện cho toàn bộ đặc điểm timeout, cancellation và tài nguyên của JDBC/HTTP client thực. Một API blocking thật có thể không hợp tác với cancel hoặc cố chạy đến khi I/O xong.

## 10. Ví dụ WebFlux: đoạn controller lỗi và cách sửa

Giả định ứng dụng Spring Boot đã thêm `spring-boot-starter-webflux` và có `LegacyCustomerClient` thực hiện truy vấn đồng bộ trả `CustomerDto`.

### Cách sai: callable có thể chạy trên event loop

~~~java
@GetMapping("/customers/bad/{id}")
public Mono<CustomerDto> bad(@PathVariable String id) {
    return Mono.fromCallable(() -> legacyClient.findById(id));
}
~~~

`fromCallable` có tính lazy nhưng khi framework subscribe vào kết quả, việc chạy callable có thể diễn ra trên thread phục vụ request, ví dụ event loop của Reactor Netty. Nếu `findById` chờ JDBC hoặc HTTP đồng bộ, worker này bị giữ trong thời gian chờ.

### Cách phù hợp: offload ngay tại biên API blocking

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

@RestController
public class CustomerController {
    private final LegacyCustomerClient legacyClient;

    public CustomerController(LegacyCustomerClient legacyClient) {
        this.legacyClient = legacyClient;
    }

    @GetMapping("/customers/{id}")
    public Mono<CustomerDto> find(@PathVariable String id) {
        return Mono.fromCallable(() -> legacyClient.findById(id))
            .subscribeOn(Schedulers.boundedElastic());
    }
}
~~~

Đây là **đoạn tích hợp**, cần định nghĩa `LegacyCustomerClient`, `CustomerDto` và bean của client đồng bộ; mã không phải file Java độc lập. Trong ứng dụng thực tế, nếu `findById` trả `null` thì `Mono.fromCallable` hoàn tất rỗng; hãy quyết định rõ trường hợp “không tìm thấy” (chẳng hạn HTTP 404 bằng `switchIfEmpty(Mono.error(new ResponseStatusException(...)))`), không mặc định một response body rỗng là kết quả nghiệp vụ mong muốn.

### Khi cần tìm nhiều ID

~~~java
Flux<CustomerDto> customers = Flux.fromIterable(customerIds)
    .flatMap(id ->
        Mono.fromCallable(() -> legacyClient.findById(id))
            .subscribeOn(Schedulers.boundedElastic()),
        8
    );
~~~

Đây là snippet tích hợp với `customerIds`, `legacyClient` và `CustomerDto` có sẵn. Tham số `8` giới hạn số **inner publishers được subscribe đồng thời** bởi `flatMap`, giúp tránh phát quá nhiều công việc blocking một lúc. Nó không thay thế giới hạn connection pool, timeout, queue, quota downstream hoặc bộ nhớ.

**Lưu ý thứ tự:** `flatMap` có thể phát kết quả khác thứ tự ID ban đầu vì thời gian hoàn tất khác nhau. Nếu thứ tự kết quả quan trọng, cân nhắc `flatMapSequential`; nếu công việc bắt buộc chạy tuần tự theo nghiệp vụ, dùng `concatMap`.

## 11. Ưu tiên non-blocking end-to-end nếu có thể

`boundedElastic` là cách tích hợp **khi chưa thể thay API blocking**, không phải mục tiêu cuối cùng của một hệ thống reactive. Các cặp thường gặp:

| Tác vụ | Tích hợp blocking | Tùy chọn reactive/non-blocking |
| --- | --- | --- |
| HTTP gọi dịch vụ khác | `RestTemplate` hoặc HTTP client synchronous | Spring `WebClient` với đường xử lý reactive |
| Truy vấn SQL | JDBC trực tiếp | R2DBC hoặc driver/adapter reactive phù hợp |
| Redis | Client đồng bộ | Reactive Redis API/client khi được hỗ trợ |
| Timer/chờ thời gian | `Thread.sleep` | `Mono.delay` hoặc timer theo scheduler |
| Phối hợp nhiều request | Gọi `.block()` từng request | `Mono.zip`, `Flux.flatMap`, `then` kết hợp publisher |
| Đọc/ghi file | Blocking filesystem API | API bất đồng bộ phù hợp với backend hoặc offload có kiểm soát |

**Đừng chỉ đổi kiểu trả về thành `Mono` rồi gọi một API blocking ở bên trong.** Đường đi dữ liệu chỉ thực sự tránh giữ thread khi các thành phần liên quan cũng hợp tác với I/O không chặn hoặc blocking đã được cô lập rõ ràng.

### Sự khác biệt giữa `Mono.delay` và `Thread.sleep`

~~~java
Mono<String> delayed = Mono.delay(Duration.ofSeconds(1))
    .thenReturn("done");
~~~

Pipeline này đăng ký một timer và phát `"done"` sau khoảng thời gian phù hợp, không yêu cầu một thread ứng dụng đứng ngủ nguyên một giây để chờ. Điều đó **không** có nghĩa timer miễn phí hoặc callback sau timer không bao giờ làm nghẽn scheduler; phép biến đổi/tác vụ nặng đặt sau `delay` vẫn phải tuân theo nguyên tắc không blocking trên worker không phù hợp.

## 12. Khi CPU-bound là nguyên nhân

Tình huống sau **không đợi network**, nhưng vẫn gây nghẽn nếu chạy trên event loop:

~~~java
Mono<String> expensive = Mono.just(input)
    .map(value -> cpuHeavyTransform(value));
~~~

Đây là snippet tích hợp với `input` và `cpuHeavyTransform` do ứng dụng định nghĩa. Khi một phép tính thực hiện hàng trăm mili giây, worker không có cơ hội xử lý sự kiện khác trong khoảng đó.

Có thể chuyển tính toán CPU-bound sang một scheduler dành cho loại công việc này:

~~~java
Mono<String> offloaded = Mono.just(input)
    .publishOn(Schedulers.parallel())
    .map(value -> cpuHeavyTransform(value));
~~~

`publishOn` đứng **trước** bước tính toán nên callback `map` được chạy trên scheduler `parallel` theo cơ chế Reactor. Tuy nhiên pool này cũng có giới hạn. Một lượng lớn công việc CPU có thể làm chính pool đó bão hòa; cần giới hạn concurrency, tối ưu thuật toán, tách job chuyên dụng hoặc áp dụng bulkhead theo nhu cầu tải.

Không nên mặc định rằng `boundedElastic` là nơi tốt nhất cho **mọi** tác vụ nặng: nó chủ yếu phục vụ cách ly công việc blocking có thời gian chờ. Tác vụ CPU-heavy cần đo và điều phối riêng.

## 13. Backpressure, queue và concurrency có liên quan nhưng không giống blocking

Reactive Streams có `request(n)` để downstream báo số phần tử còn sẵn sàng nhận. Cơ chế đó giúp nguồn hợp tác **không phát quá nhu cầu**. Nhưng backpressure không thể giải phóng một event-loop worker đang bị giữ bởi `Thread.sleep` hay một lời gọi JDBC đồng bộ.

Ví dụ:

~~~java
Flux<Result> pipeline = Flux.fromIterable(ids)
    .flatMap(id -> callReactiveService(id), 16);
~~~

Đây là snippet tích hợp. `flatMap(..., 16)` giới hạn số inner publisher đang hoạt động; nó không phải giới hạn 16 request/giây, và không cam kết rằng hệ thống không còn buffer nội bộ. Nguồn `callReactiveService` vẫn cần có hợp đồng non-blocking và khả năng hủy/truyền demand thích hợp.

Khi phải offload blocking, cần phối hợp **ít nhất** các yếu tố:

1. **Concurrency:** bao nhiêu thao tác blocking được khởi động và đang hoạt động cùng lúc?
2. **Queue:** có bao nhiêu tác vụ được giữ lại khi pool/scheduler/connection pool đã bận?
3. **Timeout:** bao lâu thì client/người gọi ngừng chờ; timeout có thực sự hủy được công việc downstream không?
4. **Memory:** tổng kích thước request, payload và kết quả đang chờ là bao nhiêu?
5. **Retry:** retry có tăng tải ngay khi dependency đang quá tải hay không?
6. **Backpressure:** publisher thật sự tôn trọng `request(n)` đến đâu và có operator nào prefetch/buffer trước?

Không đưa toàn bộ hoạt động vào một queue lớn “để không mất request” mà bỏ qua giới hạn RAM và thời gian chờ. Khi một dependency không đủ công suất, chính sách từ chối tải, giới hạn concurrency, circuit breaker/bulkhead hoặc queue bền vững phù hợp có thể cần thiết.

## 14. Lỗi, timeout và cancellation

Khi một `Callable` trong `fromCallable` ném exception, Reactor chuyển exception thành tín hiệu `onError`:

~~~java
Mono<Result> operation = Mono.fromCallable(
        () -> blockingService.read(id))
    .subscribeOn(Schedulers.boundedElastic())
    .timeout(Duration.ofSeconds(3));
~~~

Đây là snippet tích hợp cần `Result`, `blockingService` và `id` của ứng dụng; import `java.time.Duration` và `reactor.core.scheduler.Schedulers`. Nếu thao tác mất quá thời gian chờ, `timeout` gây lỗi và hủy subscription upstream. Tuy nhiên:

- **Hủy subscription không chắc hủy được I/O vật lý ngay lập tức.** Một driver đồng bộ có thể tiếp tục giữ thread cho đến khi chính driver hoặc socket timeout.
- Nếu thao tác có side effect, timeout ở caller không chứng minh side effect chưa xảy ra. Retry có thể gây lặp thao tác nếu không có idempotency key/giao dịch.
- Cấu hình timeout ở **đúng tầng**: HTTP client, driver, connection pool, phương thức Reactor và request tổng thể có ý nghĩa riêng.
- `doFinally(signalType -> ...)` có thể quan sát `ON_COMPLETE`, `ON_ERROR` và `CANCEL`, nhưng đo/log trong hook cũng phải ngắn và an toàn đối với scheduler đang thực thi.

Để tránh nuốt lỗi:

~~~java
Mono<Result> logged = operation
    .doOnError(error -> logFailure(error));
~~~

`doOnError` chỉ quan sát và chuyển tiếp lỗi. Dùng `onErrorResume` để tạo fallback **khi chính sách nghiệp vụ cho phép**, không biến mọi sự cố database/network thành thành công rỗng theo mặc định.

## 15. Chẩn đoán: tìm blocking trong WebFlux bằng dấu hiệu nào?

Một request chậm **chưa đủ** chứng minh event loop bị chặn. Network chậm, database chậm, tải CPU, GC pause, connection pool, DNS, bộ đệm và queue đều có thể gây cùng triệu chứng. Cần thu thập bằng chứng phù hợp.

### Quan sát mức hệ thống

| Tín hiệu | Có thể gợi ý | Cần phân biệt với |
| --- | --- | --- |
| p95/p99 HTTP latency tăng trên nhiều endpoint | Worker/bottleneck dùng chung bị nghẽn | DB hoặc mạng có độ trễ tăng riêng |
| Event-loop task pending/lag tăng | Callback không được phục vụ kịp | CPU saturation hoặc quá nhiều sự kiện |
| Thread dump có thread `reactor-http-...` trong `Thread.sleep` / socket read / JDBC | Có khả năng blocking ngay trên event loop | Snapshot đơn lẻ, code path chưa được xác thực |
| Worker `boundedElastic` bận/queue dài | Blocking workload bị dồn | Pool connection ngoài hoặc dependency chậm |
| Timeout/retry tăng cùng lúc | Cascading failure có thể hình thành | Lỗi remote service gây ra ban đầu |
| CPU cao và event-loop hot | Tính toán/loop xử lý dài | GC, encode/decode nặng, log đồng bộ |

Tên thread cụ thể khác nhau theo runtime và phiên bản; **đừng dùng prefix thread làm bằng chứng duy nhất**. Thread dump/Java Flight Recorder, tracing, metrics của server/client/scheduler, log tương quan request và load test có kiểm soát giúp xác nhận điểm nghẽn.

### Ghi log theo đoạn pipeline

~~~java
Mono<String> result = reactiveCall()
    .doOnSubscribe(s -> logThread("subscribe"))
    .doOnNext(v -> logThread("onNext"))
    .doFinally(signal -> logThread("finally"));
~~~

Đây là snippet tích hợp với `reactiveCall()` và `logThread(...)` do ứng dụng định nghĩa. Log thread giúp nhìn nơi tín hiệu được xử lý nhưng **không cam kết mỗi callback luôn chạy trên cùng thread**. Tránh logging đồng bộ quá mức trên event loop, vì bản thân log sink blocking cũng có thể tạo độ trễ.

Reactor có `Schedulers.isInNonBlockingThread()` để kiểm tra thread hiện tại có được đánh dấu không cho phép blocking Reactor API; nó **không** thay thế việc đo thời gian xử lý và không phải máy quét phát hiện mọi I/O blocking.

### Công cụ trong quá trình kiểm thử

- **Thread dump/JFR:** xem stack frame của worker khi tải tăng, tìm blocking I/O, lock contention hoặc vòng CPU dài.
- **Micrometer/Actuator:** theo dõi latency, số request đang xử lý, HTTP client, connection pool và scheduler metrics khi đã bật instrumentation tương ứng.
- **BlockHound:** có thể hỗ trợ phát hiện một số blocking call khi chạy trong các môi trường được hỗ trợ. Công cụ này cần thiết lập và tương thích JVM thích hợp; không coi nó là bảo đảm bắt được mọi thư viện/loại chặn.
- **Load test có kịch bản:** so sánh khi thêm/removing một blocking segment, đo throughput, p99, queue, CPU và timeout; tránh kết luận chỉ từ một request thử bằng browser.

## 16. Kiểm thử với Reactor Test

Tạo tệp `src/test/java/EventLoopTest.java` trong dự án Gradle ở mục 9. Hai dependency test đã được khai báo ở đó.

~~~java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertNull;

class EventLoopTest {

    @Test
    void blockingCallableRunsOnAWorkerAfterSubscription() {
        AtomicReference<Thread> worker = new AtomicReference<>();
        Thread caller = Thread.currentThread();

        Mono<String> operation = Mono.fromCallable(() -> {
            worker.set(Thread.currentThread());
            return "loaded";
        }).subscribeOn(Schedulers.boundedElastic());

        assertNull(worker.get()); // Chưa subscribe, callable chưa chạy.

        StepVerifier.create(operation)
            .expectNext("loaded")
            .verifyComplete();

        assertNotNull(worker.get());
        assertNotSame(caller, worker.get()); // Đã offload khỏi thread test.
    }

    @Test
    void timerCanBeTestedWithVirtualTime() {
        StepVerifier.withVirtualTime(
                () -> Mono.delay(Duration.ofMinutes(2)))
            .expectSubscription()
            .thenAwait(Duration.ofMinutes(2))
            .expectNext(0L)
            .verifyComplete();
    }

    @Test
    void callableErrorIsPropagated() {
        Mono<String> operation = Mono.<String>fromCallable(() -> {
            throw new IllegalStateException("legacy failed");
        }).subscribeOn(Schedulers.boundedElastic());

        StepVerifier.create(operation)
            .expectErrorMatches(error ->
                error instanceof IllegalStateException
                    && "legacy failed".equals(error.getMessage()))
            .verify();
    }
}
~~~

Chạy `gradle test` hoặc Gradle Wrapper tương ứng. **Ba test kỳ vọng PASS.**

- Test 1 kiểm tra callable **chưa chạy trước subscribe** và thực thi trên thread khác khi dùng `boundedElastic`. Nó không kiểm tra tên thread vì prefix là chi tiết triển khai dễ thay đổi.
- Test 2 dùng `StepVerifier.withVirtualTime` thay cho việc ngủ hai phút trong test; nó kiểm tra tín hiệu timer mà không phải chờ toàn bộ thời gian thực.
- Test 3 xác nhận exception từ nguồn blocking vẫn đi qua đường `onError`.

**Giới hạn của test:** test chuyển thread không chứng minh toàn bộ hệ thống WebFlux tránh blocking; test concurrency/latency với server, driver và phụ thuộc thực tế vẫn cần để xác nhận hành vi dưới tải.

## 17. Sai lầm phổ biến và cách sửa

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Xem `Mono.fromCallable` là tự tạo background thread | Callable vẫn có thể chạy trên event loop khi subscribe. | Thêm `subscribeOn(Schedulers.boundedElastic())` gần nguồn blocking. |
| Viết `Mono.just(blockingCall())` | Blocking diễn ra ngay lúc xây dựng publisher. | Bao lệnh trong `fromCallable` hoặc dùng API reactive. |
| Gọi `.block()` từ WebFlux handler | Chặn worker hoặc bị Reactor từ chối trên non-blocking thread. | Trả publisher cho WebFlux; dùng operator để ghép kết quả. |
| Dùng `Thread.sleep` để đợi timer | Giữ thread không làm việc hữu ích. | Dùng `Mono.delay`/timer bất đồng bộ phù hợp. |
| Dùng `Schedulers.parallel()` cho JDBC | Pool CPU nhỏ bị chặn khi đợi I/O. | Cô lập blocking trên `boundedElastic` hoặc đổi driver reactive. |
| Đặt `publishOn` sau phép biến đổi CPU nặng | Phép tính phía trước vẫn chạy trên thread cũ. | Chuyển scheduler **trước** phần cần tách. |
| Offload mọi thứ sang boundedElastic rồi coi đã giải quyết xong | Worker queue và connection pool vẫn có thể quá tải. | Giới hạn concurrency, pool, timeout; đo queue/p99. |
| `subscribe()` thủ công trong controller | Response có thể trả trước khi công việc xong, lỗi và cancel bị tách. | Trả `Mono`/`Flux` đã ghép. |
| Nghĩ backpressure có thể giải phóng thread bị ngủ | Demand không làm `Thread.sleep` kết thúc. | Xóa blocking hoặc chuyển đúng nơi, giới hạn tải. |
| Chỉ đo CPU tổng mà bỏ qua event-loop lag | CPU thấp vẫn có thể gặp request timeout do worker chờ I/O. | Theo dõi p99, worker stack, queues, connection pool và tracing. |
| Tin timeout Reactor luôn cắt được I/O đồng bộ | Driver có thể tiếp tục chạy, side effect có thể đã xảy ra. | Cấu hình timeout bên dưới và thiết kế retry/idempotency. |

## 18. Quy trình xử lý một endpoint WebFlux bị chậm

Khi điều tra một endpoint có p99 tăng bất thường, thực hiện theo thứ tự:

1. **Xác định runtime:** Reactor Netty hay server khác? Cách request được dispatch và scheduler nào đang tham gia?
2. **Đo hiện trạng:** request rate, p95/p99, error, timeout, event-loop lag, CPU, memory, connection pool và thread dump.
3. **Tìm điểm giữ thread:** rà các handler/service/operator để tìm `block()`, `Thread.sleep`, HTTP/JDBC đồng bộ, lock và đoạn CPU dài. Dùng stack/trace xác nhận thay vì suy đoán theo tên method.
4. **Ưu tiên sửa nguồn:** dùng WebClient, R2DBC hoặc client non-blocking khi phù hợp. Nếu chưa thể đổi, đặt `fromCallable(...).subscribeOn(boundedElastic())` sát biên API blocking.
5. **Giới hạn tải:** đặt concurrency, kích thước pool và queue hợp lý; cấu hình timeout đúng tầng, giảm retry bùng phát.
6. **Kiểm thử lại:** so sánh các chỉ số trước/sau dưới cùng kiểu tải, bao gồm downstream chậm, dữ liệu lớn, cancel và lỗi. Kiểm tra latency của endpoint khác dùng chung event-loop workers.
7. **Giữ hợp đồng reactive:** handler trả publisher; tránh gọi `subscribe()`/`block()` ẩn trong thư viện ứng dụng và không bỏ qua tín hiệu lỗi.

**Ghi nhớ:** event loop đạt hiệu quả vì thread có thể nhanh chóng trả về vòng xử lý sau khi đăng ký công việc I/O. Blocking khiến thread phải đứng chờ, ảnh hưởng đến nhiều kết nối chia sẻ worker. Trong Spring WebFlux, hãy **dùng API non-blocking khi có thể**, cô lập những lời gọi đồng bộ bất khả kháng bằng `boundedElastic` với giới hạn tải, và đo hệ thống thật để xác nhận kết quả.

## Tài liệu tham khảo

- Spring Framework — WebFlux, tổng quan và concurrency model: https://docs.spring.io/spring-framework/reference/web/webflux/new-framework.html
- Spring Framework — WebFlux: https://docs.spring.io/spring-framework/reference/web/webflux.html
- Spring Framework — WebClient và cách dùng synchronous/reactive: https://docs.spring.io/spring-framework/reference/web/webflux-webclient/client-synchronous.html
- Project Reactor — Threading and Schedulers: https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html
- Project Reactor — FAQ về bọc synchronous blocking call: https://projectreactor.io/docs/core/release/reference/faq.html
- Project Reactor — Testing với StepVerifier: https://projectreactor.io/docs/core/release/reference/testing.html
