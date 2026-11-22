# `subscribeOn` điều khiển quá trình đăng ký với nguồn trong Project Reactor

## 1. Mục tiêu và vấn đề cần giải quyết

Trong Project Reactor, một pipeline `Mono` hoặc `Flux` chứa các bước xử lý nhưng phần lớn chưa thực hiện gì cho đến khi có **subscription**. Khi subscription bắt đầu, Reactor phải đi ngược chuỗi operator về phía publisher gốc, thiết lập quan hệ `Publisher–Subscriber–Subscription` và phát các tín hiệu dữ liệu khi có nhu cầu. `subscribeOn(Scheduler)` là công cụ để **chuyển quá trình đăng ký với nguồn sang một `Scheduler.Worker`**, từ đó ảnh hưởng đến ngữ cảnh phát tín hiệu của nguồn trong các pipeline đồng bộ.

Đây là ý nghĩa của đề mục “`subscribeOn` điều khiển quá trình đăng ký với nguồn” thuộc chủ đề **Luồng thực thi**. Cần phân biệt nó với `publishOn`, với việc tự sinh thread, và với một nguồn bất đồng bộ đã tự quyết định nơi phát sự kiện.

Sau bài học, bạn có thể:

- Giải thích điều gì xảy ra ở **assembly**, **subscription**, **request** và **signal delivery**.
- Vẽ chiều truyền của `subscribe()`, `onSubscribe`, `request(n)` và `onNext` qua chuỗi operator.
- Dự đoán đoạn nào được chạy trên worker của `subscribeOn`; hiểu vì sao vị trí gần nguồn thường dễ đọc hơn.
- So sánh `subscribeOn` với `publishOn` và biết cách phối hợp chúng.
- Dùng `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())` khi phải tích hợp I/O đồng bộ trong Spring WebFlux.
- Tránh hiểu sai “đã gọi `subscribeOn` thì toàn bộ pipeline chạy trên thread đó”, “gọi `subscribeOn` là đã subscribe”, “đổi thread là tự động non-blocking”.
- Viết một ví dụ Java 17+ và kiểm thử xác minh hành vi, không dựa vào phỏng đoán thời gian.

## 2. Bốn thời điểm khác nhau

**Assembly**: đoạn code Java chạy để **tạo** publisher và nối các operator:

~~~java
Mono<Integer> pipeline = Mono.fromSupplier(() -> 21)
    .map(value -> value * 2)
    .subscribeOn(Schedulers.boundedElastic());
~~~

Đoạn trên chỉ **lắp ráp** publisher. `fromSupplier` chưa gọi supplier; `map` chưa biến đổi giá trị. `subscribeOn` cũng chưa tự khởi tạo một subscription. Nó chỉ cấu hình cách subscription sẽ được thực hiện về sau.

**Subscription**: downstream gọi `subscribe(...)`, `block()`, `StepVerifier.verify()` hoặc một framework (như Spring WebFlux) đăng ký vào publisher. Khi ấy chuỗi subscriber nội bộ được thiết lập, thường theo hướng từ phần cuối pipeline về nguồn.

**Request**: subscriber yêu cầu số phần tử qua `Subscription.request(n)`. Với một số source, yêu cầu này kích hoạt việc phát dữ liệu. `subscribeOn` mặc định cũng điều phối tín hiệu request tới phía nguồn trên worker của scheduler, theo ngữ nghĩa Reactor và các operator liên quan.

**Signal delivery**: `onNext`, `onError`, `onComplete` được phát từ nguồn về downstream. Với nguồn đồng bộ như `Flux.range` hoặc `Mono.fromCallable`, việc subscribe ở worker thường dẫn tới các tín hiệu nguồn được tạo trên worker ấy; một `publishOn` nằm sau đó có thể tiếp tục chuyển ngữ cảnh phát tín hiệu downstream.

**Không nhầm với đánh giá đối số Java:** lời gọi `Mono.just(blockingRead())` đã thực hiện `blockingRead()` **trước khi tạo `Mono` xong**, nên `subscribeOn` viết sau `just` không thể đưa lệnh blocking đã hoàn thành sang scheduler khác. Khi muốn hoãn, phải đặt lời gọi trong supplier/callable.

## 3. Đăng ký đi ngược, dữ liệu đi xuôi

Xét pipeline:

~~~java
Flux<Integer> pipeline = Flux.range(1, 3)
    .map(i -> i * 10)
    .subscribeOn(Schedulers.boundedElastic())
    .filter(i -> i >= 20);
~~~

Đây là snippet, giả định đã import `Flux` và `Schedulers`.

~~~text
Assembly (thứ tự viết):
Flux.range -> map -> subscribeOn -> filter -> subscriber cuối

Subscription:
subscriber cuối
    -> filter
    -> subscribeOn: lên lịch công việc trên Scheduler.Worker
    -> map
    -> Flux.range (nguồn thực sự được subscribe)

Dữ liệu (ví dụ với nguồn đồng bộ):
Flux.range: onNext(1), onNext(2), onNext(3)
    -> map: 10, 20, 30
    -> subscribeOn
    -> filter: 20, 30
    -> subscriber cuối
~~~

`subscribeOn` **không phải phép chuyển đổi giá trị**. Nó can thiệp vào quá trình đăng ký và điều phối request về nguồn. Khi nguồn phát đồng bộ trên worker đã được lên lịch, các operator đồng bộ liên tiếp cũng thường nhận tín hiệu trên worker đó nếu không có ranh giới bất đồng bộ khác.

**Điểm then chốt:** viết `subscribeOn` sau `map` không có nghĩa `map` sẽ chạy trước scheduler. Subscription được thiết lập ngược về nguồn, nên `map` vẫn thuộc phần nguồn được subscribe trên worker.

Đồng thời, đừng áp dụng kết luận trên một cách tuyệt đối cho mọi publisher: `Flux.interval`, callback API, sink/hot source, network client và các operator tự đặt scheduler có thể có cơ chế phát tín hiệu riêng.

## 4. `subscribeOn` thực sự điều khiển những gì?

Với overload thông dụng:

~~~java
source.subscribeOn(scheduler)
~~~

Reactor sẽ dùng một `Scheduler.Worker` để **thực hiện subscribe với phần upstream**, gồm việc thiết lập subscription và thông thường điều phối yêu cầu `request(n)` tới upstream trên worker đó. Tại đoạn nguồn đồng bộ, thao tác tạo dữ liệu và các callback đồng bộ có thể xảy ra trên worker được chọn.

Có ba hệ quả:

1. **Thread khởi tạo subscription bên ngoài và thread chạy nguồn có thể khác nhau.** Ví dụ `main` gọi `block()`, trong khi `Callable` thực thi ở worker của scheduler. Chính `block()` vẫn làm `main` chờ kết quả.
2. **Đơn vị điều khiển là quá trình đăng ký với nguồn, không phải mỗi phần tử một thread.** `subscribeOn` tự nó không tạo parallelism trên từng phần tử; một chuỗi `map` đồng bộ không tự chia ba phần tử ra ba thread.
3. **Không thể thay đổi thread mà một nguồn bất đồng bộ bên ngoài đã tự chọn để callback.** Ví dụ một SDK phát callback từ thread riêng, hoặc một sink được `tryEmitNext` từ thread khác. `subscribeOn` vẫn chi phối subscription của đoạn Reactor có liên quan, nhưng tín hiệu từ source đó có thể xuất hiện trên thread của chính nó.

Khi debug, tách ba câu hỏi: ai đã gọi `subscribe()`, trên worker nào nguồn được subscribe, và trên thread nào từng `onNext` thực sự chạy. Chúng thường trùng nhau đối với nguồn đồng bộ đơn giản, nhưng không phải một định luật cho mọi nguồn.

## 5. Vị trí `subscribeOn` trong chuỗi

Tài liệu Reactor khuyến nghị đặt `subscribeOn` **ngay sau nguồn** để người đọc nhìn ra ý đồ và tránh các operator trung gian gây nhầm lẫn về ngữ cảnh thực thi.

Hai cách sau thường cho cùng kết quả về thread của source trong một pipeline đồng bộ đơn giản:

~~~java
// Cách 1: gần nguồn, dễ đọc
Flux<Integer> a = Flux.range(1, 3)
    .subscribeOn(Schedulers.parallel())
    .map(i -> i * 2);

// Cách 2: viết sau map; subscription vẫn đi ngược về nguồn
Flux<Integer> b = Flux.range(1, 3)
    .map(i -> i * 2)
    .subscribeOn(Schedulers.parallel());
~~~

Đây là snippet: chỉ **khởi tạo** hai publisher, không có output trước khi subscribe. Khi subscribe, `subscribeOn` bố trí subscription với `Flux.range` trên scheduler được chỉ định. Với các operator đồng bộ như `map`, dữ liệu thường chảy tiếp trên thread được chọn từ scheduler.

Vị trí của `subscribeOn` không giống vị trí của `publishOn`: `publishOn` chỉ chuyển tín hiệu **từ vị trí đặt operator trở xuống downstream**, nên di chuyển nó làm thay đổi rõ rệt những operator nào chạy ở scheduler mới.

### Có nên viết nhiều `subscribeOn`?

Ví dụ:

~~~java
Flux<Integer> stream = Flux.range(1, 3)
    .subscribeOn(Schedulers.single())
    .map(i -> i * 2)
    .subscribeOn(Schedulers.boundedElastic());
~~~

Không nên xem mỗi `subscribeOn` là một “bước chuyển thread” cho `map`. Theo Reactor Reference, **`subscribeOn` gần nguồn hơn trong chuỗi downstream** là operator thực sự điều phối subscribe/request cho nguồn hoặc operator chặn tín hiệu ấy (như `doFirst`, `doOnRequest`); những `subscribeOn` bổ sung có thể tạo các lần chuyển worker không cần thiết. Phần lớn pipeline chỉ cần **một `subscribeOn` thích hợp cho nguồn cần cách ly**.

Cũng không nên dùng thứ tự xuất hiện của nhiều `doOnSubscribe` như một cách duy nhất để đo nguồn đã subscribe ở đâu: một hook nằm phía downstream của ranh giới `subscribeOn` có thể chạy ở thread gọi subscribe. Hãy quan sát ngay trong `Flux.defer`, `Mono.fromCallable` hoặc gần source khi cần xác minh.

## 6. Ví dụ Java 17+ chạy được: nhìn thấy nguồn subscribe ở scheduler nào

Chương trình sau giữ đầu ra ổn định bằng cách chỉ in **kết quả kiểm tra tiền tố tên thread**, thay vì phụ thuộc tên thread/timing cụ thể. Nó cũng chứng minh rằng assembly chưa kích hoạt source.

Tạo dự án Gradle với file `build.gradle`:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.8'
}

application {
    mainClass = 'SubscribeOnDemo'
}
~~~

Tạo file `src/main/java/SubscribeOnDemo.java`:

~~~java
import java.util.List;
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

public final class SubscribeOnDemo {
    public static void main(String[] args) {
        Scheduler sourceScheduler = Schedulers.newSingle("source-worker");

        try {
            Flux<Integer> pipeline = Flux.defer(() -> {
                System.out.println("source subscribed");
                boolean onWorker = Thread.currentThread()
                    .getName().startsWith("source-worker-");
                System.out.println("source on worker: " + onWorker);
                return Flux.range(1, 3);
            })
            .map(value -> {
                boolean onWorker = Thread.currentThread()
                    .getName().startsWith("source-worker-");
                System.out.println("map " + value
                    + " on worker: " + onWorker);
                return value * 10;
            })
            .subscribeOn(sourceScheduler);

            System.out.println("after assembly");
            List<Integer> values = pipeline.collectList().block();
            System.out.println("result=" + values);
        } finally {
            sourceScheduler.dispose();
        }
    }
}
~~~

Chạy bằng `gradle run --quiet`, hoặc `./gradlew run --quiet` nếu đã có Gradle Wrapper.

Với `Flux.range` và scheduler đơn đã tạo, stdout:

~~~text
after assembly
source subscribed
source on worker: true
map 1 on worker: true
map 2 on worker: true
map 3 on worker: true
result=[10, 20, 30]
~~~

Giải thích các kết quả:

1. `Flux.defer` nhận một **factory** tạo publisher. Factory chưa chạy lúc assembly nên dòng đầu tiên là `after assembly`.
2. `collectList().block()` tạo subscription mới. `subscribeOn(sourceScheduler)` chuyển subscription upstream sang worker tên bắt đầu bằng `source-worker-`.
3. Factory của `defer` in `source subscribed` và xác nhận đang ở worker.
4. `Flux.range(1,3)` phát đồng bộ; `map` cùng nhận ba phần tử trên worker, rồi nhân chúng với 10.
5. `collectList()` đưa ba giá trị vào list; `block()` khiến **main chờ** cho đến khi kết quả có sẵn. Không dùng `block()` trong handler WebFlux/reactive thread.
6. `Schedulers.newSingle(...)` tạo scheduler riêng phục vụ demo; `dispose()` giải phóng tài nguyên sau khi đã xong. Với các shared scheduler do Reactor cung cấp như `Schedulers.boundedElastic()`, ứng dụng không tùy tiện dispose chỉ vì một request đã kết thúc.

Thí nghiệm: di chuyển `.subscribeOn(sourceScheduler)` lên ngay sau `Flux.defer(...)`. Với ví dụ đồng bộ này, source vẫn chạy trên worker và output quan sát như trên. Nếu thay bằng `publishOn(sourceScheduler)` đặt sau `map`, thread của source sẽ khác: `publishOn` chỉ đổi ngữ cảnh phát tín hiệu **sau vị trí của nó**.

## 7. So sánh với `publishOn`

Hai operator đều nhận `Scheduler`, nhưng giải quyết bài toán khác nhau:

| Tiêu chí | `subscribeOn(scheduler)` | `publishOn(scheduler)` |
| --- | --- | --- |
| Điểm tác động chính | Quá trình subscription/request về upstream | Tín hiệu `onNext`/terminal đi xuống downstream |
| Vị trí trong chuỗi | Tác động đến subscription của nguồn từ vị trí đặt về upstream; đặt gần nguồn cho dễ hiểu | Tác động từ vị trí đặt về phía downstream cho đến ranh giới chuyển thread khác |
| Thường dùng | Chọn thread cho nguồn đồng bộ, thao tác blocking legacy | Chuyển bối cảnh xử lý cho những operator kế tiếp |
| Có làm chạy pipeline nếu chưa subscribe? | Không | Không |
| Có tự parallelize từng phần tử? | Không | Không |
| Có làm I/O blocking trở thành non-blocking? | Không | Không |
| Có chi phí điều phối? | Có thể lên lịch subscribe/request | Có thêm asynchronous boundary, queue/prefetch tùy overload |

Ví dụ phối hợp (snippet có import `Flux` và `Schedulers`):

~~~java
Flux<String> output = Flux.range(1, 4)
    .doOnNext(i -> log("source-stage", i))
    .subscribeOn(Schedulers.boundedElastic())
    .map(i -> i * 10)
    .publishOn(Schedulers.parallel())
    .map(i -> "value-" + i)
    .doOnNext(s -> log("downstream-stage", s));
~~~

Ở đây `log(...)` là hàm minh họa do ứng dụng cung cấp; snippet **không phải class Java tự biên dịch**. Nguồn đồng bộ và `map(i -> i * 10)` trước `publishOn` thường chạy trên worker của `boundedElastic`. `map(i -> "value-" + i)` và `doOnNext` sau `publishOn` nhận tín hiệu trên worker được chọn từ `parallel`.

Không suy ra rằng mọi log `source-stage` nhất định được in hoàn toàn trước mọi log `downstream-stage`. `publishOn` có boundary bất đồng bộ nên lịch chạy của các worker có thể khiến log xen kẽ; bảo toàn thứ tự `onNext` trong một subscription không có nghĩa thứ tự **mọi log trên nhiều thread** luôn giống hệt nhau.

**Trường hợp `publishOn` nằm trước nguồn blocking:**

~~~java
Mono<String> p = Mono.fromCallable(() -> legacy.readBlocking())
    .publishOn(Schedulers.boundedElastic());
~~~

`publishOn` chỉ đặt **sau** Callable nên không phải giải pháp chuẩn để dời chính lời gọi blocking ra khỏi thread đăng ký. Với nguồn đồng bộ blocking, chọn `fromCallable(...).subscribeOn(Schedulers.boundedElastic())`.

## 8. Vì sao `subscribeOn` thường đi cùng `fromCallable` và `boundedElastic`?

Một số thư viện hiện có API chỉ đồng bộ như JDBC truyền thống, SDK đọc file, REST client đồng bộ hoặc mã hóa/giải nén nặng. Chúng có thể chặn thread đang gọi. Nếu đưa trực tiếp vào event-loop WebFlux, một request chậm có thể giữ thread phục vụ nhiều request khác.

**Sai về thời điểm:**

~~~java
// readBlocking() chạy ngay khi dòng tạo Mono được đánh giá:
Mono<String> bad = Mono.just(legacy.readBlocking())
    .subscribeOn(Schedulers.boundedElastic());
~~~

Việc `subscribeOn` được viết sau `just` không di chuyển được lời gọi blocking đã hoàn thành khi tính đối số Java.

**Đúng về thời điểm và thread:**

~~~java
Mono<String> good = Mono
    .fromCallable(() -> legacy.readBlocking())
    .subscribeOn(Schedulers.boundedElastic());
~~~

- `fromCallable` **hoãn** lời gọi synchronous cho đến khi có subscription.
- `subscribeOn(boundedElastic)` đưa subscription và callable lên worker phù hợp với tác vụ có thể chờ I/O.
- Khi callable trả giá trị, nó được phát qua `onNext`. Khi callable trả `null`, Reactor hoàn tất empty; khi ném exception, lỗi được chuyển thành tín hiệu `onError` theo contract.
- `boundedElastic` là scheduler có **giới hạn** tài nguyên/hàng đợi; thao tác synchronous vẫn chặn một worker trong thời gian chạy. Đây là cách tương thích với thư viện legacy, không phải I/O không chặn thật sự.
- Với nguồn không blocking như Reactor Netty WebClient reactive hoặc database driver R2DBC reactive, thêm `boundedElastic` bừa bãi có thể gây overhead mà không đem lại lợi ích.

Để phân biệt: **`fromCallable` quyết định công việc chạy khi nào**, còn **`subscribeOn` quyết định subscription/source chạy ở worker nào**. Thiếu một trong hai có thể dẫn tới sai mục tiêu hoãn/cách ly.

## 9. Áp dụng trong Spring WebFlux controller

Giả sử cần dùng DAO cũ trả kết quả đồng bộ:

~~~java
// KHÔNG nên làm trong handler WebFlux:
@GetMapping("/users/{id}")
public Mono<UserDto> find(@PathVariable long id) {
    return Mono.just(legacyDao.findByIdBlocking(id));
}
~~~

Khi handler được gọi, `findByIdBlocking(id)` chạy **trước khi Mono tồn tại**. Đổi kiểu trả về thành `Mono<UserDto>` không tự động làm I/O của DAO thành reactive/non-blocking.

Một cách bọc source legacy phù hợp:

~~~java
@GetMapping("/users/{id}")
public Mono<UserDto> find(@PathVariable long id) {
    return Mono.fromCallable(() -> legacyDao.findByIdBlocking(id))
        .subscribeOn(Schedulers.boundedElastic())
        .switchIfEmpty(Mono.error(
            new ResponseStatusException(HttpStatus.NOT_FOUND, "Not found")
        ));
}
~~~

Đây là **snippet** của controller: cần có `@RestController`, `legacyDao`, `UserDto` và các import từ Spring Web, Reactor; không phải một file Java hoàn chỉnh có thể chạy độc lập. Trong ứng dụng thực:

1. Handler trả về một `Mono` được lắp ráp nhanh, không gọi DAO trong lúc tạo `Mono`.
2. Spring WebFlux thực hiện subscription khi xử lý response.
3. `subscribeOn` chuyển subscription/source callable sang `boundedElastic` để thực hiện DAO blocking.
4. Giá trị trở về downstream để WebFlux encode response; nếu DAO trả `null`, `Mono.fromCallable` hoàn tất rỗng và `switchIfEmpty` tạo HTTP 404.
5. Exception từ DAO đi theo `onError`; nó **không tự động** trở thành 404 trừ khi được ánh xạ riêng.

Vẫn phải kiểm soát timeout, giới hạn số request đồng thời, kích thước connection pool và thời gian giữ connection. Dù event-loop không bị giữ bởi DAO, nhiều lời gọi blocking có thể làm quá tải scheduler hoặc database.

**Không dùng `block()` trong controller reactive**:

~~~java
// Sai ý đồ trong một reactive request handler:
UserDto result = Mono.fromCallable(() -> legacyDao.findByIdBlocking(id))
    .subscribeOn(Schedulers.boundedElastic())
    .block();
~~~

Hàm `block()` chặn **thread gọi nó** chờ response; trên thread Reactor đánh dấu NonBlocking, nó có thể ném `IllegalStateException`. Hãy tiếp tục compose bằng `map`, `flatMap`, `switchIfEmpty` và return publisher.

## 10. Chọn `Scheduler` phù hợp

| Scheduler | Đặc tính | Khi nào dùng trong bài toán subscription |
| --- | --- | --- |
| `Schedulers.boundedElastic()` | Phù hợp tương thích công việc blocking, có giới hạn worker và queue | Source blocking cũ như JDBC/HTTP synchronous |
| `Schedulers.parallel()` | Pool worker phục vụ công việc CPU ngắn, không nên block lâu | Toán tử CPU thuần khi muốn chuyển ngữ cảnh |
| `Schedulers.single()` | Shared một worker cho tác vụ cần tuần tự hóa | Công việc không blocking cần duy trì thứ tự trên một thread |
| `Schedulers.newSingle("name")` | Scheduler đơn độc lập; ứng dụng quản lý vòng đời | Demo, thành phần cần lifecycle riêng |
| `Schedulers.immediate()` | Chạy ngay trên thread gọi, không có chuyển worker thực | Khi chủ động không muốn đổi thread; không phù hợp cách ly I/O blocking |

**`subscribeOn(Schedulers.parallel())` không biến tất cả `map` thành tính toán song song.** Nó chọn worker để subscription/nguồn chạy. Muốn xử lý từng phần tử độc lập song song có thể cân nhắc `flatMap(item -> Mono.fromCallable(() -> compute(item)).subscribeOn(...), concurrency)`, nhưng phải xác định concurrency, thứ tự và chi phí tài nguyên; đó là bài toán riêng.

Ví dụ dùng chung một `Schedulers.newSingle(...)` không có nghĩa “mỗi subscription một thread khác nhau”: các subscription có thể cùng dùng worker thuộc scheduler một thread. Nên quản lý vòng đời đối tượng scheduler nếu tự tạo, và tránh tạo một scheduler mới **cho từng HTTP request** chỉ để gọi DAO blocking.

Một số operator tự có scheduler riêng (ví dụ timer/interval mặc định dùng scheduler thích hợp), và các thư viện I/O reactive điều khiển event loop của chúng. `subscribeOn` không nên được xem là công cụ ghi đè vô điều kiện mọi thread do downstream hay bên thứ ba chọn.

## 11. Request/backpressure cũng liên quan đến `subscribeOn`

Đặc tả Reactive Streams sử dụng `Subscription.request(long n)` để subscriber cấp quyền phát dữ liệu. Theo API Reactor, overload `subscribeOn(Scheduler)` chạy `subscribe`, `onSubscribe` và thông thường điều phối cả `request` trên worker của scheduler. Do đó, nó có thể tác động không chỉ thời điểm khởi tạo nguồn mà cả cách request đi lên nguồn.

**Tuy nhiên:** không đọc một log `doOnRequest(n)` rồi suy luận toàn bộ pipeline luôn đang ở worker đó. Các operator như `publishOn`, `buffer`, `flatMap`, `limitRate` có thể giữ queue, prefetch và thay đổi kích thước/tuyến đường request. Khi cần gỡ lỗi, đặt `doOnRequest` gần source, log cả tên thread và giá trị `n`, rồi đối chiếu với các boundary thực tế.

Có một overload nâng cao:

~~~java
Flux<T> sourceOnWorker = source.subscribeOn(scheduler, false);
~~~

Đây là **snippet generic**, giả định `T`, `source`, `scheduler` đã được định nghĩa. Tham số `requestOnSeparateThread=false` yêu cầu Reactor **không buộc tín hiệu request phải được điều phối trên worker đó** như overload mặc định. Reactor API nêu tình huống đặc biệt: nguồn `Flux.create` eager/blocking có thể giữ scheduler thread trong vòng phát dữ liệu, trong khi request đang xếp hàng trên cùng worker, gây bế tắc tiến độ; overload này có thể giúp giải quyết kiểu nguồn ấy.

**Đừng tự thêm `false` như mặc định cho mọi source.** Đây là quyết định phụ thuộc cách source thực thi, tính chất blocking/eager và yêu cầu backpressure; phần lớn code chỉ nên dùng `subscribeOn(scheduler)`.

## 12. Debug luồng thực thi: quan sát đúng chỗ

Các hook hữu ích:

- `doFirst(() -> ...)`: hành động xảy ra trước khi source được subscribe; nhiều hook `doFirst` trong chuỗi có **thứ tự ngược** với thứ tự khai báo vì subscription đi từ downstream lên upstream.
- `doOnSubscribe(subscription -> ...)`: quan sát khi subscription được truyền tại một vị trí của chuỗi; vị trí trước/sau `subscribeOn` quyết định quan sát thread nào.
- `doOnRequest(n -> ...)`: quan sát những đợt request đi qua chặng đang xét.
- `doOnNext(value -> ...)`: quan sát tín hiệu dữ liệu được phát qua chặng; việc callback này chạy ở thread nào phụ thuộc source và các asynchronous boundary.
- `doOnError`, `doFinally`, `doOnCancel`: quan sát kết thúc/hủy.

Ví dụ log gần nguồn (snippet, cần import `Flux` và `Schedulers`):

~~~java
Flux<Integer> p = Flux.defer(() -> {
        System.out.println("source subscribed on "
            + Thread.currentThread().getName());
        return Flux.range(1, 3);
    })
    .doOnRequest(n -> System.out.println(
        "source-side request " + n
        + " on " + Thread.currentThread().getName()))
    .subscribeOn(Schedulers.boundedElastic())
    .doOnNext(i -> System.out.println(
        "next " + i
        + " on " + Thread.currentThread().getName()));
~~~

Đoạn snippet chỉ **lắp ráp** `p`, không in gì cho đến khi có subscription. Khi subscribe, log cho thấy vị trí khởi tạo source và request gần source; đừng phụ thuộc thứ tự/số lượng mọi dòng `request` trong pipeline phức tạp nếu có operator điều tiết prefetch. Việc `subscribe()` thường trả về sớm đối với pipeline bất đồng bộ: một chương trình console có thể kết thúc trước khi log kịp xuất hiện nếu không chờ hoàn tất đúng cách.

Khi đọc một báo cáo thread, đừng chỉ ghi `Thread.currentThread().getName()` trong một `map` cuối rồi suy ra nguồn ở thread ấy. Hãy quan sát **ngay tại source**, trước và sau mọi `publishOn` hoặc boundary bất đồng bộ, và xác định vị trí log trong chuỗi.

## 13. Subscription có phải lúc nào cũng chạy lại nguồn?

Với source lạnh được xây bằng `Mono.fromCallable` hoặc `Flux.defer`, **mỗi subscription** thường thực thi lại source:

~~~java
Mono<String> p = Mono.fromCallable(() -> legacy.load())
    .subscribeOn(Schedulers.boundedElastic());

p.subscribe();
p.subscribe();
~~~

Snippet giả định `legacy.load()` hợp lệ. Hai lượt subscribe có thể gọi `load()` **hai lần**. `subscribeOn` không cache kết quả, không biến source thành singleton và không chống duplicate side effect. Nếu có `retry`, việc resubscribe cũng có thể chạy lại nguồn.

Ngược lại:

~~~java
String value = legacy.load(); // chạy trước khi Mono được tạo
Mono<String> p = Mono.just(value)
    .subscribeOn(Schedulers.boundedElastic());
~~~

Dù có bao nhiêu subscriber, riêng biểu thức `legacy.load()` trong dòng này đã chạy một lần **lúc assembly**. `subscribeOn` chỉ tác động subscription của publisher giá trị đã được capture. Nếu cần logic “thực hiện một lần rồi chia sẻ”, phải chọn policy cache/share và vòng đời dữ liệu phù hợp, không đặt kỳ vọng đó lên scheduler.

Với nguồn hot/broadcast, các subscription có thể quan sát tín hiệu từ một quá trình phát đã bắt đầu độc lập với chúng. `subscribeOn` không dịch chuyển thread của một producer bên ngoài đang gọi callback hoặc `Sinks.Many.tryEmitNext(...)`. Những publisher có nguồn asynchronous riêng cũng có thể phát tín hiệu từ thread của chính nguồn, ngay cả khi subscription diễn ra tại worker khác.

## 14. Kiểm thử tự động: chứng minh chưa chạy lúc assembly và chạy ở worker

Nên kiểm tra bằng trạng thái và tên thread có kiểm soát, không dùng `Thread.sleep` để đoán scheduler. Tiếp tục dự án Gradle ở mục 6: thay **khối dependencies** bằng:

~~~groovy
dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.8'
    testImplementation 'io.projectreactor:reactor-test:3.8.8'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.2'
}

test {
    useJUnitPlatform()
}
~~~

Tạo `src/test/java/SubscribeOnTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class SubscribeOnTest {
    @Test
    void sourceRunsOnChosenWorkerOnlyAfterSubscribe() {
        Scheduler scheduler = Schedulers.newSingle("test-source");
        AtomicInteger calls = new AtomicInteger();
        AtomicReference<String> sourceThread = new AtomicReference<>();

        try {
            Mono<Integer> source = Mono.fromCallable(() -> {
                sourceThread.set(Thread.currentThread().getName());
                return calls.incrementAndGet();
            }).subscribeOn(scheduler);

            assertEquals(0, calls.get()); // assembly chưa chạy nguồn

            StepVerifier.create(source)
                .expectNext(1)
                .verifyComplete();

            assertEquals(1, calls.get());
            assertTrue(sourceThread.get().startsWith("test-source-"));

            StepVerifier.create(source)
                .expectNext(2)
                .verifyComplete();

            assertEquals(2, calls.get()); // subscription mới
        } finally {
            scheduler.dispose();
        }
    }

    @Test
    void justEvaluatesArgumentBeforeSubscription() {
        AtomicInteger calls = new AtomicInteger();
        Mono<Integer> source = Mono.just(calls.incrementAndGet());

        assertEquals(1, calls.get());

        StepVerifier.create(source)
            .expectNext(1)
            .verifyComplete();

        StepVerifier.create(source)
            .expectNext(1)
            .verifyComplete();

        assertEquals(1, calls.get()); // đã capture giá trị 1
    }
}
~~~

Chạy `gradle test`. Hai test phải PASS:

- Test đầu kiểm tra source chưa chạy lúc assembly, chạy tại một worker có tên `test-source-...`, và mỗi subscription độc lập gọi lại nguồn.
- Test thứ hai kiểm tra `Mono.just(calls.incrementAndGet())` đã tính giá trị ở assembly, không gọi lại biểu thức khi subscribe.

Vì `StepVerifier.verifyComplete()` đợi tín hiệu hoàn tất, bài test kiểm tra được trạng thái sau khi nguồn thực thi mà không đợi một khoảng thời gian tùy ý. Test này không cố đo “nhanh hơn bao nhiêu”; đó là bài toán benchmark/performance khác.

## 15. Những điểm thường gây hiểu nhầm

| Nhận định sai | Điều thực sự xảy ra | Cách áp dụng đúng |
| --- | --- | --- |
| “Thêm `subscribeOn` là nguồn chạy ngay” | Nó chỉ cấu hình cách subscribe sẽ diễn ra | Phải có subscription thực sự |
| “Vị trí `subscribeOn` quyết định chỉ các operator đứng sau nó chạy trên worker” | Subscription đi ngược tới nguồn, nên với nguồn đồng bộ việc phát từ nguồn chịu tác động của `subscribeOn` dù viết sau `map` | Đặt gần source cho rõ, đừng hiểu như `publishOn` |
| “`subscribeOn` tự chia mỗi phần tử qua thread khác nhau” | Nó chọn worker cho subscription/source, không tự tạo parallelism theo phần tử | Dùng mô hình concurrency thích hợp nếu cần song song |
| “`Mono.just(jdbc.call()).subscribeOn(boundedElastic)` an toàn” | `jdbc.call()` chạy trước `just` | `Mono.fromCallable(() -> jdbc.call()).subscribeOn(boundedElastic)` |
| “`publishOn` sau `fromCallable` giúp source không block event-loop” | `publishOn` chuyển tín hiệu ở downstream; Callable ở upstream vẫn có thể block thread subscribe | Dùng `subscribeOn` cho source blocking |
| “`subscribeOn` chạy lại giá trị `just` theo mỗi subscriber” | `just` giữ một giá trị đã tính | Muốn gọi lại hàm khi subscribe: `fromCallable`/`defer` |
| “Gắn nhiều `subscribeOn` để đổi thread liên tiếp” | Thường chỉ thêm switch/overhead, không giống nhiều `publishOn` | Một `subscribeOn` rõ ràng cho source |
| “Dùng `parallel()` scheduler thì có xử lý song song mọi item” | Pool scheduler khác việc chia công việc ra nhiều rails/tasks | Cấu hình concurrency có chủ đích |
| “`subscribeOn` cưỡng ép thread của mọi nguồn hot/async” | Source/callback bên ngoài có ngữ cảnh phát riêng | Xác định thread của producer; dùng `publishOn` khi cần chuyển downstream |
| “`boundedElastic` biến JDBC thành non-blocking” | JDBC vẫn chặn worker, queue và tài nguyên có giới hạn | Giới hạn tải, timeout, ưu tiên driver reactive khi phù hợp |
| “Đã `subscribeOn` rồi nên có thể `block()` trong controller” | `block()` vẫn chặn thread gọi, có thể bị Reactor cấm trên NonBlocking thread | Return publisher và dùng operator compose |
| “`subscribeOn` luôn bảo đảm hủy là dừng I/O ngay” | Cancellation không bảo đảm interrupt được mọi API blocking | Cấu hình timeout/cancel ở API gốc và quản lý tài nguyên |

## 16. Bài tập vận dụng có lời giải

**Bài 1.** Với `Flux.range(1,3).map(x -> x+1).subscribeOn(scheduler)`, `map` có luôn chạy trước khi `subscribeOn` thực thi không?

**Đáp án:** Không. `map` là operator được lắp ráp trước nhưng callback của nó chỉ xử lý phần tử khi nguồn được subscribe và phát dữ liệu. Ở nguồn `Flux.range` đồng bộ, quá trình phát/`map` thường diễn ra trên worker do `subscribeOn` chọn.

**Bài 2.** Dời `subscribeOn` từ ngay sau `Flux.range` xuống sau hai `map` đồng bộ có khiến nguồn trở lại thread gọi `subscribe()` không?

**Đáp án:** Không trong pipeline đơn giản này. `subscribeOn` can thiệp vào subscription đi ngược lên source. Tuy nhiên vị trí gần source dễ đọc hơn và các operator bất đồng bộ có thể có quy tắc thread riêng.

**Bài 3.** `Mono.just(service.loadBlocking()).subscribeOn(boundedElastic)` chạy `loadBlocking` lúc nào?

**Đáp án:** Lúc Java tính đối số cho `Mono.just` ở assembly, trước subscription. Muốn hoãn và bố trí trên worker, dùng `Mono.fromCallable(service::loadBlocking).subscribeOn(Schedulers.boundedElastic())`.

**Bài 4.** Pipeline có `subscribeOn(boundedElastic)` rồi `publishOn(parallel)`. Một `map` đồng bộ **sau** `publishOn` thường chạy ở đâu?

**Đáp án:** Trên worker của `parallel` do `publishOn` chuyển tín hiệu xuống downstream. `subscribeOn` vẫn điều khiển subscription/nguồn upstream.

**Bài 5.** Dùng `Mono.fromCallable(call).subscribeOn(scheduler)` và gọi `subscribe()` hai lần. Có được hiểu rằng `call` chạy một lần và được cache không?

**Đáp án:** Không. Với source lạnh này, mỗi subscription có thể gọi lại Callable. Cần thiết kế idempotency hoặc chính sách cache/share nếu có side effect và muốn thay đổi ngữ nghĩa.

**Bài 6.** Vì sao log cuối pipeline cho biết thread `parallel-1` không đủ để khẳng định source cũng chạy trên `parallel-1`?

**Đáp án:** Giữa source và log có thể có `publishOn`, timer, network driver hoặc publisher bất đồng bộ. Muốn biết source được subscribe ở thread nào, log ngay trong `defer`/`fromCallable` hoặc hook gần nguồn.

**Bài 7.** `subscribeOn(Schedulers.boundedElastic())` có làm một lệnh gọi JDBC lâu 3 giây chạy nhanh thành 3 mili giây không?

**Đáp án:** Không. Lệnh vẫn là I/O đồng bộ chặn worker trong thời gian chờ. Scheduler cách ly event-loop khỏi lệnh blocking, không rút ngắn thời gian thực thi I/O của driver.

## 17. Ghi nhớ và nguồn tham khảo

- **`subscribeOn` là công cụ điều phối subscription về nguồn**, thường ảnh hưởng cả thread thực hiện source đồng bộ và request upstream.
- **`publishOn` là ranh giới chuyển thread cho dữ liệu downstream** tại vị trí xuất hiện trong chuỗi.
- **Assembly không đồng nghĩa subscription.** `Mono.just(blockingCall())` đã gọi hàm blocking trước; cần `fromCallable` hoặc `defer` để hoãn.
- **Một `subscribeOn` gần nguồn thường đủ**; nhiều `subscribeOn` không tương đương nhiều `publishOn`.
- **`boundedElastic` dùng cho tương thích blocking**, không biến I/O thành non-blocking và không giải quyết giới hạn tải tự động.
- **Thread của nguồn không luôn là thread mọi `onNext`**; source hot/async và các boundary khác có thể chủ động thay đổi context.

Tài liệu chính thức để tra cứu tiếp:

1. [Project Reactor Reference — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): cách hoạt động của `subscribeOn`, `publishOn`, nhiều lần chuyển scheduler và vị trí khuyến nghị.
2. [Project Reactor FAQ — How Do I Wrap a Synchronous, Blocking Call?](https://projectreactor.io/docs/core/release/reference/faq.html): mẫu `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`.
3. [Flux API — subscribeOn](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): contract `subscribeOn(scheduler)` và `subscribeOn(scheduler, requestOnSeparateThread)`, tình huống đặc biệt với source `Flux.create`.
4. [Project Reactor — Backpressure and Ways to Reshape Requests](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html): `request(n)`, prefetch và request qua operator.
5. [Spring Framework — WebFlux Reference](https://docs.spring.io/spring-framework/reference/web/webflux.html): cách Spring WebFlux dùng publisher và I/O non-blocking.
