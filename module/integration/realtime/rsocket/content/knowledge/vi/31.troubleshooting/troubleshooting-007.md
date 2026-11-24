# Timeout do tác vụ chặn trên event loop

Một ứng dụng RSocket có thể trả timeout hàng loạt dù server vẫn chạy và CPU chưa chắc đã đạt 100%. Nguyên nhân thường gặp là một tác vụ blocking chạy trên event loop của Reactor Netty. Event loop vốn phải xử lý I/O cho nhiều kết nối; nếu một callback gọi database đồng bộ, đọc file, chờ `Future.get()` hoặc ngủ bằng `Thread.sleep()`, thread đó không thể tiếp tục đọc frame, gửi response hay xử lý KEEPALIVE cho các kết nối khác được gán vào nó.

Trong module `INTEGRATION_REALTIME_RSOCKET`, Spring handler thường trả `Mono` hoặc `Flux`, nhưng việc trả về một reactive type không tự làm cho đoạn code bên trong trở nên non-blocking. Một lời gọi đồng bộ trước khi publisher được tạo, hoặc một operator thực hiện blocking trên thread subscribe, vẫn có thể chặn event loop. Bài viết này giải thích cách nhận diện event-loop starvation, cách chuyển phần blocking sang scheduler có giới hạn hoặc thay bằng API reactive, và cách kiểm thử để timeout không lan sang các stream khác.

## 1. Event loop làm gì trong RSocket?

Reactor Netty dùng event loop để xử lý các sự kiện I/O của kết nối TCP và WebSocket. Một event-loop thread thường phục vụ nhiều channel thay vì dành riêng một thread cho từng request. RSocket chạy trên transport đó; khi frame đến, các callback và reactive pipeline có thể tiếp tục trên thread đang xử lý sự kiện nếu chưa có scheduler boundary.

```text
Event loop thread
  ├─ đọc frame từ connection A
  ├─ dispatch RSocket request A
  ├─ đọc frame từ connection B
  ├─ xử lý KEEPALIVE / CANCEL
  ├─ ghi response cho connection C
  └─ nhận dữ liệu từ connection D

Nếu một callback chạy blocking trong 2 giây:
  └─ các công việc khác trên event loop phải chờ
```

Điểm quan trọng là một event loop có thể phục vụ nhiều kết nối. Nếu thread đó bị chặn, các stream không liên quan về mặt nghiệp vụ vẫn có thể bị ảnh hưởng vì chúng dùng chung event-loop thread. Mức độ ảnh hưởng phụ thuộc số event loop, cách phân phối channel và thời gian blocking.

## 2. Dấu hiệu timeout do event-loop starvation

Các triệu chứng thường xuất hiện cùng lúc:

- Nhiều route hoặc nhiều client khác nhau tăng latency/timeout trong cùng khoảng thời gian.
- Request đơn giản cũng chậm dù dependency của route đó vẫn khỏe.
- KEEPALIVE, response và cancellation đến muộn.
- Khi một tác vụ blocking kết thúc, nhiều request đang chờ có thể được xử lý dồn dập.
- Thread dump cho thấy `reactor-tcp-nio-*`, `reactor-http-nio-*` hoặc thread event-loop tương ứng đang nằm trong JDBC, file I/O, `Future.get()`, `Thread.sleep()` hay lock contention.
- CPU có thể thấp nếu thread đang chờ I/O; CPU có thể cao nếu event loop chạy vòng lặp tính toán nặng.

Một dấu hiệu hữu ích là timeout lan sang những route không dùng chung database hoặc dịch vụ downstream. Nếu một lời gọi blocking trên event loop giữ thread, các channel khác do thread đó phục vụ cũng bị trì hoãn.

Không phải mọi timeout đều do event loop. Cũng cần loại trừ pool cạn, downstream chậm, proxy idle timeout, DNS, packet loss, GC pause và queue quá tải. Thread dump cùng thời điểm timeout là bằng chứng quan trọng để phân biệt.

## 3. Những thao tác thường vô tình chặn event loop

Các ví dụ phổ biến:

| Thao tác | Vì sao blocking hoặc gây starvation |
|---|---|
| JDBC/JPA/Hibernate đồng bộ | Chờ database socket và thực thi truy vấn trên thread gọi. |
| `RestTemplate` hoặc HTTP client đồng bộ | Thread chờ response từ dịch vụ khác. |
| `Files.readAllBytes`, `FileInputStream.read` | Chờ filesystem hoặc storage. |
| `Future.get()`, `CompletableFuture.join()` | Chờ một tác vụ khác hoàn thành. |
| `Thread.sleep()` | Giữ thread mà không làm công việc hữu ích. |
| `CountDownLatch.await()`, semaphore acquire không giới hạn | Chờ đồng bộ trên thread xử lý I/O. |
| `Mono.block()`, `blockFirst()`, `blockLast()` | Chờ reactive publisher đồng bộ; trên non-blocking thread có thể bị Reactor từ chối. |
| Synchronized lock hoặc lock contention | Chờ thread khác nhả khóa. |
| Logging/appender đồng bộ chậm | Có thể chờ file, console hoặc network sink. |
| Vòng lặp CPU dài / serialize dữ liệu khổng lồ | Không nhất thiết là blocking I/O nhưng vẫn chiếm event loop quá lâu. |

`block()` trên Reactor non-blocking thread thường gây `IllegalStateException` để cảnh báo. Nhưng JDBC, `Thread.sleep()` hoặc một thư viện đồng bộ khác không nhất thiết ném lỗi ngay; chúng có thể âm thầm giữ event loop. Vì vậy, không thấy `block()` exception không có nghĩa pipeline an toàn.

## 4. Reactive type không tự biến lời gọi đồng bộ thành non-blocking

Đây là một lỗi phổ biến trong handler Spring RSocket:

```java
@MessageMapping("inventory.lookup")
public Mono<Item> lookup(@Payload LookupRequest request) {
    // Lời gọi này chạy ngay khi method được gọi.
    Item item = blockingRepository.findById(request.itemId());

    return Mono.just(item);
}
```

Method trả về `Mono<Item>`, nhưng `findById(...)` đã chạy đồng bộ trước khi `Mono.just(...)` được tạo. Nếu method được gọi trên event-loop thread, event loop đã bị chặn trước khi Reactor có thể điều phối publisher.

Một biến có kiểu `Mono` hoặc `Flux` không bảo đảm mọi công việc bên trong là non-blocking. Cần kiểm tra thread thực thi tại đúng vị trí lời gọi nguồn.

Một biến thể cũng sai là gọi blocking trong lambda của `map` mà không chuyển scheduler:

```java
return requestMono
    .map(request -> blockingRepository.findById(request.itemId()));
```

`map` chạy trên thread phát tín hiệu upstream. Nếu upstream phát trên event loop, lời gọi repository cũng chạy trên event loop.

## 5. Cách sửa tốt nhất: dùng API reactive end-to-end

Nếu có thể, thay blocking driver/client bằng API reactive để thread không phải chờ I/O.

Ví dụ với repository reactive:

```java
@MessageMapping("inventory.lookup")
public Mono<Item> lookup(@Payload LookupRequest request) {
    return reactiveRepository.findById(request.itemId())
        .switchIfEmpty(Mono.error(
            new ItemNotFoundException(request.itemId())
        ))
        .timeout(Duration.ofSeconds(2));
}
```

Trong ví dụ này, repository trả `Mono<Item>` và dùng driver reactive. Khi database chưa có kết quả, thread không phải ngồi chờ đồng bộ; publisher sẽ phát tín hiệu khi I/O hoàn tất. `timeout` giới hạn thời gian chờ kết quả ở tầng reactive, còn database/client vẫn cần timeout riêng để giới hạn tài nguyên ở tầng kết nối.

Ví dụ nguồn reactive thường gặp:

- R2DBC thay cho JDBC khi database và driver hỗ trợ.
- Reactive HTTP client thay cho client đồng bộ.
- Reactive Redis/MongoDB client thay cho API đồng bộ.
- API filesystem/reactive stream phù hợp nếu thư viện và hệ điều hành hỗ trợ.

Không bọc một API vốn đã reactive vào `Mono.fromCallable()` chỉ để “đưa lên scheduler”. Hãy trả publisher gốc để giữ được cancellation, demand và error propagation.

## 6. Khi phải dùng thư viện blocking: boundedElastic

Nếu chưa thể thay JDBC/JPA hoặc SDK đồng bộ, hãy cô lập phần blocking trên scheduler dành cho blocking work. `Schedulers.boundedElastic()` là lựa chọn Reactor phổ biến cho tác vụ blocking có thời gian chờ, với số thread và hàng đợi được giới hạn theo cấu hình của scheduler.

```java
@MessageMapping("inventory.lookup")
public Mono<Item> lookup(@Payload LookupRequest request) {
    return Mono.fromCallable(() ->
            blockingRepository.findById(request.itemId())
                .orElseThrow(() ->
                    new ItemNotFoundException(request.itemId())
                )
        )
        .subscribeOn(Schedulers.boundedElastic())
        .timeout(Duration.ofSeconds(2));
}
```

`Mono.fromCallable(...)` trì hoãn lời gọi cho tới lúc subscribe. `subscribeOn(boundedElastic())` chuyển việc subscribe và thực thi callable sang scheduler dành cho blocking work. Nhờ vậy, event loop có thể tiếp tục xử lý các connection khác trong khi thread boundedElastic chờ database.

### 6.1. Vì sao phải dùng fromCallable?

Không viết:

```java
Item item = blockingRepository.findById(id).orElseThrow();
return Mono.just(item)
    .subscribeOn(Schedulers.boundedElastic());
```

Lời gọi repository đã xảy ra trước khi `subscribeOn` được gắn vào publisher. Scheduler không thể di chuyển một thao tác đã chạy xong sang thread khác.

Phải đưa chính lời gọi blocking vào callable:

```java
return Mono.fromCallable(() -> blockingRepository.findById(id))
    .subscribeOn(Schedulers.boundedElastic());
```

`Mono.defer(() -> Mono.just(blockingCall()))` chỉ trì hoãn lời gọi tới lúc subscribe; nếu subscriber vẫn là event loop, lời gọi vẫn chặn event loop. `defer` không tự chọn scheduler.

### 6.2. Dùng scheduler riêng khi cần giới hạn theo dependency

`boundedElastic` dùng chung có thể phù hợp với ứng dụng nhỏ, nhưng nhiều loại blocking dependency có thể tranh chấp cùng tài nguyên. Có thể tạo scheduler riêng với giới hạn thread và queue rõ ràng:

```java
@Configuration
public class BlockingSchedulerConfig {

    @Bean(destroyMethod = "dispose")
    Scheduler legacyDatabaseScheduler() {
        return Schedulers.newBoundedElastic(
            24,      // thread cap
            500,     // queued task cap
            "legacy-db"
        );
    }
}
```

Sử dụng scheduler được quản lý theo lifecycle của ứng dụng:

```java
@Service
public class InventoryService {
    private final BlockingRepository repository;
    private final Scheduler legacyDatabaseScheduler;

    public InventoryService(
            BlockingRepository repository,
            Scheduler legacyDatabaseScheduler) {
        this.repository = repository;
        this.legacyDatabaseScheduler = legacyDatabaseScheduler;
    }

    public Mono<Item> find(String id) {
        return Mono.fromCallable(() ->
                repository.findById(id)
                    .orElseThrow(() -> new ItemNotFoundException(id))
            )
            .subscribeOn(legacyDatabaseScheduler);
    }
}
```

Thread cap cần phù hợp với connection pool và khả năng của dependency. Nếu JDBC pool chỉ có 10 connection, tạo 100 thread blocking thường chỉ làm tăng số thread chờ connection. Queue cũng phải hữu hạn; khi đầy, hệ thống nên từ chối hoặc áp dụng backpressure/load shedding theo chính sách thay vì giữ request vô hạn.

Không tạo scheduler mới cho mỗi request. Scheduler là tài nguyên dùng chung và phải được dispose khi ứng dụng shutdown.

## 7. Phân biệt subscribeOn và publishOn

Hai operator đều ảnh hưởng thread thực thi nhưng có vị trí tác động khác nhau:

| Operator | Tác động | Dùng khi |
|---|---|---|
| `subscribeOn(scheduler)` | Điều phối quá trình subscribe và thực thi nguồn upstream trên scheduler đó. | Cô lập một nguồn blocking được tạo bằng `fromCallable`, `fromRunnable` hoặc publisher deferred. |
| `publishOn(scheduler)` | Chuyển các signal và operator downstream sau vị trí đặt nó sang scheduler đó. | Chuyển một đoạn xử lý downstream, ví dụ xử lý CPU hoặc một hàm blocking phía sau. |

Ví dụ `subscribeOn` phù hợp cho nguồn blocking:

```java
Mono<Item> item = Mono.fromCallable(() -> blockingRepository.find(id))
    .subscribeOn(Schedulers.boundedElastic())
    .map(this::toResponse);
```

Ví dụ `publishOn` chuyển một bước xử lý phía sau:

```java
Mono<Response> response = reactiveRepository.findById(id)
    .publishOn(Schedulers.boundedElastic())
    .map(entity -> legacyFormatter.formatBlocking(entity));
```

Ở ví dụ thứ hai, repository reactive vẫn chạy theo cơ chế của nó; bước `legacyFormatter` phía sau `publishOn` chạy trên boundedElastic. Nếu blocking nằm trong source trước `publishOn`, operator này không bảo vệ source.

Ví dụ sai thường gặp:

```java
Mono<Item> item = Mono.fromCallable(() -> blockingRepository.find(id))
    .publishOn(Schedulers.boundedElastic());
```

Callable có thể đã chạy trên thread subscribe trước khi `publishOn` chuyển signal downstream. Hãy dùng `subscribeOn` cho source blocking.

## 8. CPU-bound work cũng có thể làm event loop đói

Không phải chỉ I/O mới gây timeout. Một vòng lặp tính toán dài, mã hóa dữ liệu rất lớn, nén/giải nén nặng hoặc xử lý ảnh trên event loop cũng chiếm thread trong thời gian dài.

Với công việc CPU-bound có thể chia nhỏ hoặc thực thi độc lập, dùng `Schedulers.parallel()` hoặc scheduler CPU riêng có giới hạn:

```java
return reactiveRepository.findById(id)
    .publishOn(Schedulers.parallel())
    .map(this::expensiveCalculation);
```

`parallel()` phù hợp cho công việc CPU-bound không blocking. Không dùng nó cho JDBC hoặc `Thread.sleep()`: các thread parallel là non-blocking worker và blocking ở đó cũng có thể làm cạn scheduler hoặc bị BlockHound phát hiện.

Nếu tính toán rất dài, hãy chia batch hoặc giới hạn concurrency để một tác vụ không chiếm CPU quá lâu. Tăng số event-loop thread không phải cách sửa gốc cho một callback chạy quá lâu.

## 9. Timeout không tự ngắt một lời gọi blocking

Một điểm dễ hiểu nhầm là thêm `.timeout(Duration.ofSeconds(2))` không bảo đảm một lời gọi blocking sẽ dừng sau hai giây.

### 9.1. Blocking trước khi publisher được trả về

```java
public Mono<Item> lookup(String id) {
    Item item = blockingRepository.find(id); // chặn ngay tại đây
    return Mono.just(item).timeout(Duration.ofSeconds(2));
}
```

`timeout` chưa thể hoạt động vì method còn chưa trả publisher về cho caller. Nếu lời gọi mất 10 giây, thread gọi method có thể bị giữ 10 giây trước khi operator timeout được thiết lập.

### 9.2. Blocking bên trong fromCallable nhưng chưa chuyển scheduler

```java
return Mono.fromCallable(() -> blockingRepository.find(id))
    .timeout(Duration.ofSeconds(2));
```

Callable được thực thi khi subscribe. Nếu subscription xảy ra trên event loop, event loop vẫn bị chặn. Timer của `timeout` có thể phát timeout ở scheduler khác, nhưng nó không thể buộc một API đồng bộ bất kỳ dừng ngay lập tức. Thread đang thực hiện blocking call có thể tiếp tục giữ tài nguyên cho tới khi lời gọi trả về hoặc chính API có timeout/cancellation hỗ trợ.

### 9.3. Timeout sau khi đã chuyển sang boundedElastic

```java
return Mono.fromCallable(() -> blockingRepository.find(id))
    .subscribeOn(Schedulers.boundedElastic())
    .timeout(Duration.ofSeconds(2));
```

Event loop không còn bị giữ bởi lời gọi đồng bộ. Nếu quá hai giây, downstream có thể nhận `TimeoutException` và subscription bị cancel. Tuy nhiên, cancellation không bảo đảm driver JDBC hoặc SDK đã dừng thao tác ngay lập tức. Hãy cấu hình query timeout/socket timeout ở chính dependency và đóng tài nguyên theo lifecycle.

Timeout có hai mục đích khác nhau:

- **Giới hạn thời gian chờ của reactive caller:** ngừng chờ kết quả và phát lỗi timeout.
- **Giới hạn thời gian chạy của dependency:** yêu cầu database/HTTP/SDK dừng thao tác theo timeout riêng của nó.

Cần cả hai khi dùng blocking client. Nếu chỉ có timeout reactive, thread boundedElastic có thể tiếp tục bị chiếm sau khi caller đã timeout.

## 10. Thread pool, connection pool và bulkhead

Chuyển blocking sang boundedElastic bảo vệ event loop, nhưng không làm tài nguyên vô hạn. Cần phối hợp các giới hạn:

| Tài nguyên | Cần giới hạn | Nếu không giới hạn |
|---|---|---|
| Blocking scheduler threads | Số thread tối đa | Quá nhiều thread, context switch và memory tăng. |
| Scheduler queue | Số task chờ | Request tích lũy, latency tăng và timeout hàng loạt. |
| JDBC connection pool | Số connection | Thread chờ connection và chiếm scheduler. |
| Downstream concurrency | Số lời gọi đồng thời | Dependency bị quá tải và retry storm. |
| Payload/buffer | Kích thước và số phần tử | Heap/direct memory tăng, GC pause và OOM. |

Một thiết kế thực tế thường đặt concurrency của blocking database work không vượt quá năng lực connection pool, có bounded queue và deadline. Khi scheduler queue đầy, nên trả lỗi quá tải có kiểm soát hoặc dùng bulkhead thay vì tiếp tục xếp hàng.

## 11. Chẩn đoán bằng thread dump và BlockHound

### 11.1. Lấy thread dump khi đang có timeout

Lấy một vài thread dump cách nhau một khoảng ngắn trong lúc sự cố diễn ra. Kiểm tra event-loop thread:

- Thread có tên gợi ý event loop, ví dụ `reactor-tcp-nio-*` hoặc `reactor-http-nio-*` tùy transport/version.
- Stack trace có nằm trong JDBC driver, HTTP client đồng bộ, filesystem, `Future.get()`, `Thread.sleep()` hoặc lock không?
- Cùng một stack trace có lặp lại qua nhiều dump không?
- Có nhiều event-loop thread cùng bị giữ bởi một loại lời gọi không?

Nếu stack trace thay đổi liên tục trong đoạn tính toán CPU nặng, đó có thể là CPU starvation thay vì I/O blocking. Dùng Java Flight Recorder hoặc profiler để xem thread state, CPU hotspot và lock contention.

Tên thread thay đổi theo Reactor Netty version và cấu hình. Hãy nhận diện dựa vào stack trace và thread factory thực tế, không phụ thuộc một prefix cố định.

### 11.2. Dùng BlockHound trong test

BlockHound phát hiện nhiều thao tác blocking khi chúng chạy trên thread được đánh dấu non-blocking, đặc biệt hữu ích với Reactor. Cài đặt và kích hoạt trong test suite hoặc môi trường phát triển theo hướng dẫn tương thích phiên bản:

```java
@BeforeAll
static void installBlockHound() {
    BlockHound.install();
}
```

Một test minh họa:

```java
StepVerifier.create(
        Mono.fromCallable(() -> {
            Thread.sleep(20);
            return "done";
        }).subscribeOn(Schedulers.parallel())
    )
    .expectError(BlockingOperationError.class)
    .verify(Duration.ofSeconds(3));
```

Test này cố ý chạy `Thread.sleep()` trên scheduler non-blocking để xác nhận BlockHound phát hiện. Với code production, không thêm `allowBlockingCallsInside(...)` chỉ để làm test xanh nếu thao tác thực sự vẫn chặn event loop. Chỉ cho phép một lời gọi đặc biệt khi đã hiểu rõ hành vi, giới hạn và lý do thư viện cần ngoại lệ.

BlockHound không phát hiện mọi dạng starvation hoặc mọi thư viện native. Kết hợp nó với thread dump, metrics và integration test.

### 11.3. Metrics cần quan sát

Theo dõi:

- Event-loop pending tasks/queue nếu transport expose metric tương ứng.
- Thời gian xử lý handler và latency theo route/interaction model.
- Số tác vụ đang chạy và đang chờ trong boundedElastic/dedicated scheduler.
- JDBC connection pool active/idle/pending và acquisition time.
- Timeout, cancellation và lỗi downstream.
- CPU, GC pause, heap/direct memory và thread count.
- Số stream đang mở và thời gian từ client cancel tới source cleanup.

Tên metric cụ thể phụ thuộc phiên bản Reactor Netty, Micrometer và cấu hình metrics. Hãy xác minh metric có được bật và tag theo route/service có cardinality thấp; không đưa ID người dùng hoặc token vào metric label.

## 12. Kiểm thử để chứng minh event loop không bị chặn

Unit test cho publisher giúp xác minh scheduler, nhưng nên có integration test qua RSocket để kiểm tra tác động lên kết nối khác.

### 12.1. Kiểm tra thread thực thi

```java
AtomicReference<String> threadName = new AtomicReference<>();

Mono<Item> result = Mono.fromCallable(() -> {
    threadName.set(Thread.currentThread().getName());
    return blockingRepository.find(id);
}).subscribeOn(Schedulers.boundedElastic());

StepVerifier.create(result)
    .expectNextCount(1)
    .verifyComplete();

assertThat(threadName.get()).contains("boundedElastic");
```

Assertion tên thread có thể phụ thuộc scheduler/thread factory và phiên bản. Trong test bền vững hơn, có thể kiểm tra thread không thuộc nhóm event loop đã biết hoặc dùng scheduler test riêng được đặt tên.

### 12.2. Kiểm tra một request chậm không chặn route khác

Tạo hai route:

- `legacy.lookup`: dùng blocking repository nhưng được chuyển sang boundedElastic.
- `health.ping`: trả kết quả reactive nhanh.

Cho `legacy.lookup` chờ một latch trong test fixture, sau đó gọi `health.ping` trên một kết nối RSocket khác. Xác nhận `health.ping` vẫn trả kết quả trong deadline khi lookup còn đang chờ. Sau đó nhả latch và xác nhận lookup hoàn tất.

Test này chứng minh blocking work đã được cô lập khỏi event loop. Nếu cả hai route cùng timeout, kiểm tra scheduler boundary và xem có blocking code nào vẫn chạy trước `subscribeOn` hay không.

### 12.3. Kiểm tra timeout và cancellation

- Tạo blocking call có timeout phía driver dài hơn timeout reactive.
- Xác nhận client nhận timeout đúng theo deadline.
- Xác nhận event-loop thread vẫn xử lý route khác.
- Quan sát blocking worker còn chạy hay đã dừng; không giả định cancel tự interrupt được SDK.
- Xác nhận driver timeout cuối cùng giải phóng thread và connection.
- Kiểm tra cancellation được truyền tới nguồn reactive nếu nguồn hỗ trợ.

## 13. Quy trình xử lý sự cố theo thứ tự

1. **Xác nhận phạm vi:** timeout xảy ra trên một route hay nhiều route/kết nối cùng lúc?
2. **Lấy thread dump:** thu thập trong lúc latency đang cao; tìm event-loop thread đang chờ I/O, lock hoặc tính toán.
3. **Tìm lời gọi đồng bộ:** kiểm tra JDBC/JPA, HTTP client, filesystem, `block()`, `Future.get()` và logging.
4. **Xác định điểm chạy:** lời gọi xảy ra trước khi publisher được tạo, trong source callable hay trong operator downstream?
5. **Chọn cách sửa:** ưu tiên reactive API; nếu chưa có, bọc đúng lời gọi bằng `fromCallable` và `subscribeOn` với scheduler có giới hạn.
6. **Đặt timeout ở đúng tầng:** timeout reactive cho caller và timeout native cho database/HTTP/SDK.
7. **Giới hạn tài nguyên:** thread cap, queue cap, connection pool, concurrency và deadline.
8. **Kiểm thử chéo:** một request blocking không làm route khác timeout; cancellation và cleanup hoạt động.
9. **Theo dõi sau triển khai:** latency, pending tasks, scheduler queue, pool wait và timeout rate.

Không chữa sự cố bằng cách tăng timeout hoặc tăng event-loop thread trước khi tìm blocking call. Tăng timeout chỉ khiến caller chờ lâu hơn; tăng event loop có thể che triệu chứng tạm thời nhưng không sửa việc chặn thread.

## 14. Những lỗi sửa sai thường gặp

- **Chỉ đổi method trả về `Mono`:** lời gọi blocking đã chạy trước khi publisher được tạo.
- **Dùng `Mono.just(blockingCall())`:** tham số được tính ngay, nên vẫn blocking.
- **Đặt `publishOn` sau source blocking:** source có thể đã chạy trên event loop trước khi scheduler đổi thread.
- **Dùng `Mono.defer` mà không đổi scheduler:** chỉ trì hoãn lời gọi, không chuyển thread.
- **Dùng `Schedulers.parallel()` cho JDBC:** scheduler CPU-bound bị chiếm bởi blocking I/O.
- **Tạo scheduler cho mỗi request:** tăng thread và không quản lý được lifecycle.
- **Tăng boundedElastic thread vô hạn:** chuyển starvation từ event loop sang thread/memory/connection pool.
- **Chỉ đặt `.timeout(...)`:** caller có thể timeout trong khi blocking call vẫn giữ worker.
- **Giả định cancellation rollback side effect:** cancel không hoàn tác transaction đã commit.
- **Dùng BlockHound allowlist quá rộng:** che mất lỗi blocking thực tế.

## 15. Checklist trước khi phát hành

- Handler RSocket không gọi JDBC/JPA/HTTP/filesystem đồng bộ trực tiếp trên event loop.
- Không gọi `block()`, `Future.get()`, `join()` hoặc `Thread.sleep()` trong reactive callback.
- Ưu tiên reactive driver/client end-to-end.
- Blocking legacy được bọc trong `Mono.fromCallable`/`Flux.defer` phù hợp và `subscribeOn` scheduler dành cho blocking.
- Scheduler có giới hạn thread và queue; được tái sử dụng và dispose theo lifecycle.
- Concurrency phù hợp với connection pool và năng lực downstream.
- Có timeout native cho database/HTTP/SDK cùng timeout reactive cho caller.
- CPU-bound work được chuyển khỏi event loop và có giới hạn concurrency.
- Có BlockHound hoặc test tương đương để phát hiện blocking trong non-blocking thread.
- Có integration test chứng minh route nhanh không bị route blocking làm chậm.
- Có thread dump/metrics để chẩn đoán khi production gặp timeout.
- Cancellation, timeout và cleanup không bị nhầm với rollback nghiệp vụ.

## 16. Kết luận

Timeout do tác vụ blocking trên event loop xảy ra vì một thread I/O dùng chung bị giữ trong khi chờ database, HTTP, file, lock hoặc công việc đồng bộ khác. Reactive return type không tự làm lời gọi blocking trở nên non-blocking. Ưu tiên reactive API; nếu phải dùng thư viện blocking, đặt lời gọi bên trong `Mono.fromCallable(...)` và chuyển source bằng `subscribeOn(Schedulers.boundedElastic())` hoặc scheduler riêng có giới hạn. `publishOn` chỉ chuyển các bước downstream sau vị trí đặt nó, còn `timeout` và cancellation không bảo đảm ngắt ngay một lời gọi đồng bộ. Dùng thread dump, BlockHound, metrics và integration test để xác nhận event loop tiếp tục phục vụ các kết nối khác khi blocking work đang chạy.
