# Lựa chọn bộ lập lịch cho toán tử phụ thuộc thời gian

Các toán tử thời gian trong Project Reactor cần một cơ chế để lên lịch phát tín hiệu hoặc kiểm tra thời hạn. Nếu không chỉ định rõ, nhiều toán tử dùng scheduler mặc định của Reactor. Điều này tiện cho pipeline đơn giản, nhưng có thể làm ứng dụng khó kiểm soát nơi timer chạy, khó cô lập công việc blocking và khó kiểm thử thời gian một cách ổn định.

Khi lựa chọn scheduler, cần phân biệt **scheduler điều khiển đồng hồ và tác vụ hẹn giờ** với **scheduler điều khiển việc xử lý downstream**. Một nguồn `interval` có thể phát tick trên scheduler dành cho timer, sau đó `publishOn` chuyển phép tính nặng sang scheduler CPU. Chọn đúng ranh giới giúp timer không bị chặn bởi công việc dài và giúp giới hạn tài nguyên rõ ràng.

Chủ đề này thuộc chương **Thời gian** của REACTIVE_PROGRAMMING. Module học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; đồng thời thực hành Mono, Flux, kết hợp toán tử, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Với pipeline phụ thuộc thời gian, mục tiêu là chọn scheduler theo loại công việc, quản lý vòng đời scheduler và kiểm thử mà không phải chờ đồng hồ thực.

## Scheduler làm gì trong một pipeline có thời gian?

Trong Reactor, `Scheduler` là abstraction điều phối nơi và thời điểm một tác vụ được thực thi. Các toán tử như `interval`, `delayElements`, `delaySubscription`, `timeout` và `bufferTimeout` cần lên lịch một hành động trong tương lai hoặc theo chu kỳ. Những toán tử này thường có overload nhận `Scheduler`, nhờ đó ứng dụng có thể chỉ định nơi timer được quản lý.

Ví dụ, `Flux.interval(Duration.ofSeconds(1))` tạo tick định kỳ. Scheduler chịu trách nhiệm lên lịch các tick; khi một tick được phát, những toán tử phía sau sẽ xử lý tín hiệu theo luồng thực thi của pipeline. Nếu xử lý downstream chậm ngay trên thread phát tick, công việc đó có thể ảnh hưởng đến nhịp phát tiếp theo hoặc làm trễ các tác vụ khác dùng cùng scheduler.

```text
Timer scheduler                 Downstream scheduler
      |                                  |
  lên lịch tick                          |
      |                                  |
      +---- onNext(0) ---> publishOn ----+---- xử lý 0
      +---- onNext(1) ---> publishOn ----+---- xử lý 1
      +---- onNext(2) ---> publishOn ----+---- xử lý 2
```

Sơ đồ thể hiện hai trách nhiệm khác nhau: scheduler của timer quyết định lúc tín hiệu thời gian được phát; `publishOn` tạo ranh giới để các bước downstream tiếp tục trên scheduler khác. Đây không phải cam kết thời gian thực chính xác. Tải CPU, độ trễ hệ điều hành và hàng đợi scheduler vẫn có thể làm tín hiệu đến muộn.

## Các scheduler thường dùng trong Reactor

| Scheduler | Đặc điểm | Công việc phù hợp |
|---|---|---|
| `Schedulers.parallel()` | Pool luồng có kích thước gắn với số lõi xử lý; dùng cho tác vụ CPU-bound ngắn và không blocking | Tính toán, biến đổi dữ liệu độc lập |
| `Schedulers.single()` | Một luồng dùng chung cho các tác vụ được gửi tới scheduler đó | Công việc cần một luồng thực thi tuần tự hoặc một timer riêng đơn giản |
| `Schedulers.boundedElastic()` | Pool có giới hạn, phù hợp cho tác vụ có thể blocking; số luồng và hàng đợi được kiểm soát | Gọi thư viện blocking, I/O cũ |
| `Schedulers.newSingle(...)` | Tạo scheduler một luồng riêng, có vòng đời do ứng dụng quản lý | Cô lập timer hoặc công việc tuần tự cho một thành phần |
| `Schedulers.newParallel(...)` | Tạo pool song song riêng với số worker xác định | Cô lập một nhóm tác vụ CPU-bound |
| `Schedulers.fromExecutorService(...)` | Bọc một `ExecutorService` do ứng dụng cung cấp | Tích hợp với cơ chế quản lý thread pool sẵn có |

Các scheduler toàn cục như `Schedulers.parallel()` và `Schedulers.boundedElastic()` được Reactor quản lý và chia sẻ trong tiến trình. Scheduler tạo bằng `newSingle`, `newParallel` hoặc `newBoundedElastic` là tài nguyên riêng mà ứng dụng cần dispose khi thành phần sở hữu dừng hoạt động.

Không có scheduler nào là lựa chọn tốt nhất cho mọi timer. Nếu timer chỉ phát tick và downstream làm phép tính CPU, có thể dùng timer scheduler để phát và `parallel()` để xử lý. Nếu timer kích hoạt một lời gọi blocking, hãy cô lập lời gọi đó bằng `boundedElastic()` hoặc thiết kế một executor riêng có giới hạn. Tránh chạy blocking trên `parallel()` hoặc thread timer dùng chung.

## Chỉ định scheduler trực tiếp cho toán tử thời gian

Nhiều toán tử thời gian cung cấp overload cho phép truyền scheduler. Cách này làm rõ nơi tác vụ hẹn giờ được lên lịch và giúp kiểm soát vòng đời tài nguyên.

### `interval`: phát tick trên scheduler đã chọn

```java
import java.time.Duration;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

Scheduler timerScheduler = Schedulers.newSingle("metrics-timer");

Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1), timerScheduler)
    .take(5);

Disposable subscription = ticks.subscribe(
    tick -> System.out.println("tick=" + tick),
    error -> System.err.println("timer failed: " + error.getMessage()),
    () -> System.out.println("timer completed")
);

// Khi thành phần sở hữu dừng:
subscription.dispose();
timerScheduler.dispose();
```

`interval(period, scheduler)` dùng scheduler được truyền vào để lên lịch các tick. Ví dụ tạo một scheduler một luồng riêng để timer không dùng chung worker với các timer khác trong ứng dụng. Vì `take(5)` làm nguồn hoàn tất sau năm tick, subscription sẽ kết thúc; ứng dụng vẫn phải dispose scheduler riêng khi không còn dùng nó.

Trong ứng dụng có vòng đời dài, không tạo một scheduler mới cho mỗi request hoặc mỗi subscription. Hãy tạo scheduler ở cấp thành phần, tái sử dụng trong phạm vi hợp lý và dispose khi thành phần đóng. Tạo quá nhiều pool riêng làm tăng số thread, chi phí lập lịch và độ phức tạp quản lý.

### `delayElements`: trì hoãn phát trên scheduler đã chọn

```java
Flux<String> delayed = Flux.just("A", "B", "C")
    .delayElements(Duration.ofMillis(250), timerScheduler);
```

`delayElements` lên lịch việc phát từng phần tử sau khoảng trễ đã cấu hình. Scheduler được truyền vào điều khiển các tác vụ trì hoãn và phát tín hiệu của toán tử. Nếu các bước xử lý tiếp theo cần chạy trên scheduler khác, có thể thêm `publishOn` sau toán tử.

### `timeout`: kiểm tra thời hạn bằng scheduler đã chọn

```java
import reactor.core.publisher.Mono;

Mono<String> response = callRemoteService()
    .timeout(Duration.ofSeconds(2), timerScheduler);
```

`timeout` dùng scheduler được chỉ định để quản lý thời hạn. Nếu nguồn không phát tín hiệu tiếp theo trong khoảng thời gian quy định, pipeline kết thúc bằng `TimeoutException` (hoặc chuyển sang Publisher dự phòng nếu dùng overload có fallback). Scheduler timer không làm cho lời gọi mạng tự trở thành non-blocking; API nguồn vẫn phải có cách thực thi phù hợp.

### `bufferTimeout`: kết hợp giới hạn số phần tử và thời gian

```java
import java.util.List;

Flux<List<Event>> batches = eventSource()
    .bufferTimeout(100, Duration.ofSeconds(1), timerScheduler);
```

`bufferTimeout` phát một batch khi đạt số phần tử tối đa hoặc khi khoảng thời gian tối đa trôi qua, tùy điều kiện nào đến trước. Scheduler được truyền vào quản lý giới hạn thời gian. Đây là lựa chọn hữu ích khi cần gom batch vừa tránh batch quá nhỏ vừa không chờ vô hạn khi lưu lượng thấp.

## Tách timer khỏi công việc downstream bằng `publishOn`

Một timer nên phát tín hiệu đúng nhịp tương đối mà ứng dụng cần; phần xử lý nặng nên được chuyển sang scheduler phù hợp. Ví dụ:

```java
import java.time.Duration;
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

Scheduler timerScheduler = Schedulers.newSingle("poll-timer");

Flux<Result> results = Flux.interval(Duration.ofMillis(500), timerScheduler)
    .publishOn(Schedulers.parallel())
    .map(tick -> calculateMetrics(tick));
```

`interval` phát tick từ `timerScheduler`. `publishOn` chuyển tín hiệu downstream sang `Schedulers.parallel()`, vì vậy `calculateMetrics` được thực hiện trên scheduler CPU. Điều này ngăn phép tính giữ thread timer trong lúc chạy. Tuy nhiên, nếu phép tính kéo dài hơn chu kỳ tick, các tick có thể chờ ở ranh giới bất đồng bộ; hàng đợi và độ trễ có thể tăng. Cần đo backlog và chọn chính sách phù hợp nếu không thể xử lý kịp.

`subscribeOn` có vai trò khác. Nó điều khiển nơi subscription tới nguồn được bắt đầu, nhưng không thay thế scheduler timer được truyền trực tiếp vào một toán tử như `interval(period, timerScheduler)`. Khi mục tiêu là chọn đồng hồ cho timer, hãy dùng overload scheduler của chính toán tử. Khi mục tiêu là chuyển xử lý downstream, dùng `publishOn` tại ranh giới cần thiết.

| Cơ chế | Điều khiển chính | Ví dụ sử dụng |
|---|---|---|
| Scheduler truyền vào toán tử thời gian | Nơi timer hoặc tác vụ hẹn giờ được quản lý | `interval(period, timer)`, `delayElements(delay, timer)` |
| `publishOn(scheduler)` | Scheduler xử lý các tín hiệu downstream kể từ vị trí toán tử | Chuyển phép tính sau tick sang `parallel()` |
| `subscribeOn(scheduler)` | Scheduler bắt đầu quá trình subscription và thực thi nguồn theo ngữ nghĩa của nguồn | Cô lập nguồn đồng bộ hoặc blocking |

## Chọn scheduler theo loại công việc

Hãy bắt đầu bằng việc phân loại công việc được kích hoạt bởi timer:

**Timer chỉ phát tín hiệu nhẹ.** Dùng scheduler phù hợp cho timer, có thể là scheduler mặc định hoặc một scheduler dùng chung. Giữ callback trực tiếp ngắn và không blocking.

**Timer kích hoạt phép tính CPU-bound.** Phát tick trên timer scheduler rồi chuyển bước tính toán sang `Schedulers.parallel()`. Giới hạn số công việc đang chờ nếu phép tính có thể chậm hơn nhịp phát.

**Timer kích hoạt I/O blocking.** Chuyển phần gọi blocking sang `Schedulers.boundedElastic()` hoặc một executor giới hạn được quản lý riêng. Đặt timeout và giới hạn concurrency để tránh dồn quá nhiều tác vụ chờ.

**Timer thuộc một thành phần có vòng đời riêng.** Cân nhắc `Schedulers.newSingle(...)` hoặc scheduler riêng tương ứng để có thể quan sát và dispose độc lập. Chỉ tạo một lần cho thành phần, không tạo lại theo từng tick.

**Cần kiểm thử thời gian.** Dùng virtual time hoặc scheduler kiểm thử thay vì chờ đồng hồ thật. Khi truyền scheduler trực tiếp vào toán tử, hãy bảo đảm test kiểm soát chính scheduler đó.

## Scheduler mặc định và khi nào nên ghi rõ lựa chọn

Nhiều toán tử thời gian của Reactor dùng `Schedulers.parallel()` làm scheduler mặc định. Hành vi mặc định giúp mã ngắn gọn, nhưng có thể tạo phụ thuộc ngầm vào scheduler toàn cục. Khi ứng dụng cần cô lập timer, kiểm soát thread name, kiểm thử với virtual time hoặc chia sẻ một timer theo vòng đời thành phần, hãy dùng overload nhận scheduler.

Không nên mặc định rằng mọi toán tử có thời gian đều dùng cùng một scheduler hoặc có cùng chữ ký overload. API thay đổi theo loại toán tử và phiên bản Reactor. Hãy kiểm tra overload của toán tử cụ thể đang dùng; nếu có thể truyền scheduler, ưu tiên truyền rõ ràng khi lựa chọn đó là một phần của thiết kế hệ thống.

Việc truyền scheduler riêng cũng không tự đảm bảo timer có độ chính xác tuyệt đối. Scheduler vẫn phụ thuộc thread scheduling, tải máy và hàng đợi tác vụ. Với yêu cầu deadline nghiêm ngặt, cần thiết kế dung sai thời gian, đo độ trễ thực tế và tránh dùng scheduler reactive như một hệ thống hard real-time.

## Quản lý vòng đời scheduler

Scheduler tạo riêng là tài nguyên. Nếu không dispose, thread và hàng đợi có thể tồn tại lâu hơn thành phần sử dụng chúng. Nên tạo scheduler tại nơi có vòng đời rõ ràng và đóng nó cùng thành phần đó.

```java
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

final class MetricsService implements AutoCloseable {
    private final Scheduler timer = Schedulers.newSingle("metrics-timer");

    Scheduler timerScheduler() {
        return timer;
    }

    @Override
    public void close() {
        timer.dispose();
    }
}
```

Ở tầng framework, có thể gắn `close()` với lifecycle hook của bean hoặc service. Subscription và scheduler là hai tài nguyên khác nhau: dispose subscription dừng việc tiêu thụ một pipeline; dispose scheduler đóng scheduler riêng và ảnh hưởng mọi tác vụ đang dùng scheduler đó. Chỉ dispose scheduler khi thành phần sở hữu chắc chắn không còn consumer khác cần nó.

Không dispose scheduler toàn cục như `Schedulers.parallel()` chỉ vì một pipeline kết thúc. Các scheduler toàn cục được chia sẻ bởi nhiều pipeline; việc dispose nhầm có thể làm hỏng công việc của thành phần khác. Nếu cần reset factory toàn cục trong test hoặc môi trường đặc biệt, dùng lifecycle API được Reactor cung cấp và chỉ thực hiện tại ranh giới quản lý phù hợp.

## Backpressure và độ trễ khi timer phát nhanh

Timer tạo tín hiệu theo nhịp cấu hình, nhưng downstream có thể không xử lý kịp. Ví dụ, `interval` phát mỗi 100 ms trong khi xử lý một phần tử mất 500 ms. Nếu ranh giới downstream xếp hàng các tick, độ trễ của phần tử ngày càng tăng. Một scheduler khác chỉ thay đổi nơi thực thi; nó không tự giải quyết chênh lệch tốc độ.

Hãy quyết định ý nghĩa của tick:

- Nếu mỗi tick đại diện cho một lần kiểm tra độc lập và mọi lần đều quan trọng, giới hạn concurrency, đo backlog và xác định hành vi khi quá tải.
- Nếu tick chỉ báo “đã đến lúc làm mới trạng thái”, có thể bỏ tick cũ và chỉ giữ lần gần nhất.
- Nếu nguồn có thể được điều tiết, giảm nhịp phát hoặc chỉ yêu cầu thêm khi consumer sẵn sàng.
- Nếu công việc có thể chạy lâu hơn chu kỳ, cân nhắc cơ chế không chồng lấn như `concatMap` hoặc một vòng lặp có lịch trình tiếp theo sau khi tác vụ trước hoàn tất.

Ví dụ tránh chồng lấn tác vụ polling:

```java
Flux.interval(Duration.ZERO, Duration.ofSeconds(5), timerScheduler)
    .concatMap(tick -> fetchSnapshot())
    .subscribe(this::updateSnapshot, this::reportFailure);
```

`concatMap` chỉ đăng ký Publisher kế tiếp sau khi Publisher hiện tại hoàn tất, giúp các lần `fetchSnapshot()` không chạy chồng lấn. Nếu một lần gọi kéo dài hơn năm giây, tick tiếp theo có thể chờ được xử lý; điều này vẫn có thể tạo backlog tùy cách nguồn và toán tử điều phối. Nếu nghiệp vụ chỉ cần snapshot mới nhất, hãy cân nhắc chính sách bỏ tick cũ thay vì xếp hàng mọi lần polling.

## Kiểm thử toán tử thời gian bằng virtual time

Kiểm thử dựa trên thời gian thực thường chậm và dễ dao động do tải máy. Reactor Test cung cấp `StepVerifier.withVirtualTime` để tiến đồng hồ ảo mà không phải chờ khoảng thời gian thật.

```java
import java.time.Duration;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1)).take(3)
    )
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(3))
    .expectNext(0L, 1L, 2L)
    .verifyComplete();
```

Publisher được tạo bên trong supplier truyền cho `withVirtualTime`. Điều này cho phép verifier cài virtual scheduler trước khi toán tử tạo timer. `thenAwait` tiến thời gian ảo ba giây; các tick được phát mà test không phải chờ ba giây thực.

Nếu tạo Publisher trước khi gọi `withVirtualTime`, timer có thể đã giữ scheduler thực và không chịu ảnh hưởng của virtual time. Đây là nguyên nhân phổ biến khiến test vẫn phải chờ hoặc timeout dù đã dùng API virtual time.

### Kiểm thử khi truyền scheduler tường minh

Nếu ứng dụng inject một scheduler riêng vào toán tử, test cần inject scheduler ảo tương ứng. Có thể tạo `VirtualTimeScheduler` rồi điều khiển nó:

```java
import java.time.Duration;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.scheduler.VirtualTimeScheduler;

VirtualTimeScheduler virtualTimer = VirtualTimeScheduler.create();

Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1), virtualTimer)
    .take(2);

StepVerifier.create(ticks)
    .then(() -> virtualTimer.advanceTimeBy(Duration.ofSeconds(2)))
    .expectNext(0L, 1L)
    .verifyComplete();

virtualTimer.dispose();
```

Ở đây, test kiểm soát chính scheduler được truyền vào `interval`. Cách inject scheduler giúp mã sản xuất không phụ thuộc scheduler toàn cục và test có thể điều khiển thời gian một cách tường minh. Với pipeline phức tạp có nhiều scheduler, hãy xác định scheduler nào điều khiển timer và scheduler nào xử lý downstream; virtualize đúng scheduler cần kiểm thử.

## Quan sát scheduler khi chạy ứng dụng

Khi điều tra timer chạy sai nhịp hoặc xử lý trên thread không mong muốn, hãy ghi tên thread tại ranh giới quan trọng:

```java
Flux.interval(Duration.ofSeconds(1), timerScheduler)
    .doOnNext(tick -> logThread("timer", tick))
    .publishOn(Schedulers.parallel())
    .map(this::calculate)
    .doOnNext(result -> logThread("calculation", result))
    .subscribe(this::writeResult);
```

`logThread` có thể ghi `Thread.currentThread().getName()` cùng mã tick. Log trước và sau `publishOn` giúp xác nhận tín hiệu đã chuyển scheduler. Trong môi trường production, nên dùng metric và tracing có sampling thay vì log mọi tick nếu tần suất cao.

Các chỉ số nên theo dõi gồm độ trễ từ lúc timer dự kiến phát đến lúc xử lý xong, số tác vụ đang chờ, thời gian thực thi callback, số lần timeout và tình trạng queue của executor liên quan. Nếu thread timer thường xuyên bận vì callback dài, hãy rút ngắn callback hoặc chuyển công việc sang scheduler khác.

## Những lỗi thường gặp khi chọn scheduler

**Dùng `parallel()` cho tác vụ blocking.** Blocking có thể chiếm worker CPU và làm các tác vụ khác trên pool chậm theo. Chuyển phần blocking sang `boundedElastic()` hoặc executor có giới hạn.

**Cho rằng `subscribeOn` thay scheduler của timer.** Toán tử thời gian có thể dùng scheduler riêng của nó. Hãy truyền scheduler trực tiếp vào overload của toán tử khi cần kiểm soát timer.

**Dùng `publishOn` rồi cho rằng backlog biến mất.** `publishOn` chuyển nơi xử lý và dùng hàng đợi; nếu downstream vẫn chậm hơn upstream, phần tử có thể tiếp tục tích tụ.

**Tạo scheduler mới trong mỗi lần subscribe.** Việc này có thể tạo nhiều thread và khiến vòng đời khó quản lý. Tái sử dụng scheduler theo thành phần và dispose khi thành phần đóng.

**Dispose scheduler dùng chung quá sớm.** Một scheduler toàn cục có thể đang phục vụ nhiều pipeline. Chỉ dispose scheduler riêng do thành phần sở hữu.

**Kiểm thử bằng `Thread.sleep`.** Cách này làm test chậm và không ổn định. Dùng virtual time hoặc scheduler kiểm thử để điều khiển mốc thời gian.

**Giả định timer chính xác tuyệt đối.** Scheduler cung cấp cơ chế lập lịch, không phải bảo đảm hard real-time. Hãy đo độ trễ và thiết kế dung sai phù hợp.

## Tự kiểm tra

1. Scheduler được truyền vào `Flux.interval(period, scheduler)` điều khiển phần nào của pipeline?
2. Vì sao `publishOn(Schedulers.parallel())` có thể giúp timer không bị giữ bởi phép tính CPU dài?
3. `subscribeOn` khác gì với scheduler truyền trực tiếp vào một toán tử thời gian?
4. Khi nào nên dùng `boundedElastic()` thay cho `parallel()`?
5. Vì sao không nên tạo `Schedulers.newSingle(...)` trong mỗi request hoặc dispose `Schedulers.parallel()` khi một pipeline kết thúc?
6. Nếu nguồn phát tick mỗi 100 ms nhưng downstream xử lý 500 ms, điều gì có thể xảy ra với hàng đợi và độ trễ?
7. Vì sao Publisher cần được tạo bên trong supplier của `StepVerifier.withVirtualTime`?

Khi phân biệt được scheduler của timer với scheduler xử lý downstream, bạn có thể chọn `parallel`, `boundedElastic` hoặc scheduler riêng theo loại công việc, quản lý tài nguyên đúng vòng đời và kiểm thử các toán tử thời gian bằng virtual time trong pipeline Reactor.
