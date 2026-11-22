# Phân biệt tạo publisher với bọc một lệnh chặn đã thực thi

## 1. Vấn đề cốt lõi

Trong Reactor và Spring WebFlux, **tạo một đối tượng `Mono`/`Flux` không đồng nghĩa với việc công việc bên trong nó chưa chạy**. Java luôn đánh giá đối số của phương thức trước khi gọi phương thức ấy. Vì vậy:

~~~java
Mono<String> wrong = Mono.just(legacyClient.loadBlocking());
~~~

`legacyClient.loadBlocking()` chạy **ngay khi dòng Java này được thực thi**, trước khi `Mono.just(...)` nhận được kết quả. Nếu lệnh chặn I/O trong 500 ms thì thread hiện tại đã chờ 500 ms; publisher chỉ bọc **giá trị đã có**. Dù chưa có ai `subscribe()`, tác vụ blocking đã diễn ra.

Cách tạo nguồn hoãn thực thi đúng hơn:

~~~java
Mono<String> source = Mono.fromCallable(() -> legacyClient.loadBlocking())
    .subscribeOn(Schedulers.boundedElastic());
~~~

Ở đây lambda giữ **công việc sẽ làm**. Lúc tạo `source`, lệnh blocking chưa chạy. Khi có subscriber, Reactor mới thực thi `Callable`; `subscribeOn(Schedulers.boundedElastic())` bố trí quá trình subscribe/nguồn blocking lên một scheduler phù hợp với tác vụ chờ I/O.

**Ba câu hỏi phải tách biệt:**

1. **Khi nào** công việc thực sự bắt đầu: ngay khi dựng publisher hay khi subscribe?
2. **Ở thread nào** nó chạy: thread gọi phương thức hiện tại, thread subscribe, hay worker của scheduler?
3. **Nó có blocking không**: thao tác JDBC/SDK đồng bộ vẫn chặn một thread, kể cả khi được đưa lên `boundedElastic`; chỉ API I/O không chặn thực sự mới có đặc tính non-blocking ở tầng I/O.

Bài này nằm trong chủ đề **Tạo nguồn dữ liệu**: mục tiêu là chọn đúng factory/source cho công việc cần thực hiện, không chỉ thay kiểu trả về bằng `Mono` hoặc `Flux`.

## 2. Ba thời điểm: thực thi phương thức, assembly, subscription

**Assembly** là lúc chương trình xây dựng chuỗi publisher/operator. **Subscription** là lúc một subscriber đăng ký và kích hoạt công việc đối với nguồn lạnh (cold source). Cần phân biệt với thời điểm **tính đối số** trong Java.

~~~text
Dòng code                          Assembly          Subscription
    |
    |-- legacy.loadBlocking() ------> CHẠY, CHẶN
    |-- Mono.just(result) ----------> tạo Mono bọc kết quả
    |                                         |
    |                                         +----> emit kết quả đã có
    |
    |-- Mono.fromCallable(() -> ...) -> tạo Mono, CHƯA gọi legacy
                                              |
                                              +----> GỌI legacy, có thể CHẶN
~~~

Hai chuỗi mã khác nhau ở thứ tự thực thi:

~~~java
// A: thực thi trước, rồi bọc kết quả
String value = legacyClient.loadBlocking();
Mono<String> a = Mono.just(value);

// B: giữ hành động để thực hiện khi subscription xảy ra
Mono<String> b = Mono.fromCallable(() -> legacyClient.loadBlocking());
~~~

Nếu chưa subscribe:

- `a`: lệnh blocking đã chạy một lần; kết quả nằm trong publisher.
- `b`: lệnh blocking chưa chạy; nó sẽ chạy khi có subscription.
- **Nhưng `b` chưa tự động chạy trên thread riêng.** Nếu subscribe xảy ra ở event-loop và không bố trí scheduler, `Callable` có thể chặn chính event-loop đó.

Do đó cần kiểm soát cả **thời điểm** lẫn **nơi thực thi**.

## 3. Vì sao chỉ bọc giá trị bằng `Mono.just` là sai khi muốn hoãn blocking?

Java đánh giá tham số trước lời gọi hàm:

~~~java
Mono.just(legacyClient.loadBlocking())
~~~

tương đương về thời điểm:

~~~java
String result = legacyClient.loadBlocking(); // thực thi, có thể chờ ở đây
Mono<String> mono = Mono.just(result);       // chỉ bọc result
~~~

Chúng ta không thể “chữa” thời điểm đã xảy ra bằng cách thêm scheduler sau `just`:

~~~java
// SAI nếu kỳ vọng loadBlocking chuyển sang boundedElastic:
Mono<String> mono = Mono.just(legacyClient.loadBlocking())
    .subscribeOn(Schedulers.boundedElastic());
~~~

`subscribeOn` tác động tới **subscription của publisher**, còn `loadBlocking()` đã chạy trong lúc **tính đối số để dựng `Mono.just`**. Lệnh I/O ấy không thể được dời ngược về thời điểm khác.

Một sai lầm trông có vẻ tinh vi hơn:

~~~java
String value = legacyClient.loadBlocking(); // đã chặn trước khi tạo publisher

Mono<String> mono = Mono.fromCallable(() -> value)
    .subscribeOn(Schedulers.boundedElastic());
~~~

`fromCallable` trong trường hợp này chỉ hoãn việc **trả lại biến đã được tính**, không hoãn `loadBlocking()`. Quy tắc cần nhớ: **đặt chính lời gọi blocking trong lambda/callable**, không đặt kết quả của nó trong lambda.

Dùng `Mono.just(value)` hoàn toàn đúng khi `value` là giá trị đã có hoặc hằng số rẻ, chẳng hạn `Mono.just("ok")`, `Mono.just(configValue)`. Vấn đề không nằm ở API `just`; vấn đề nằm ở việc gọi thao tác I/O chặn thread để tạo đối số cho nó.

## 4. Các cách tạo publisher và ý nghĩa thực thi

| Cách tạo nguồn | Thời điểm thực thi công việc | Đặc điểm |
| --- | --- | --- |
| `Mono.just(value)` | `value` đã được tính trước khi gọi `just` | Phù hợp giá trị sẵn có, phát lại giá trị đó cho subscriber |
| `Mono.just(blockingCall())` | `blockingCall()` chạy lúc dựng publisher | Không hoãn blocking, có thể chặn event-loop |
| `Mono.fromCallable(() -> blockingCall())` | Gọi `Callable` khi subscribe | Hoãn thao tác, mỗi subscription có thể gọi lại |
| `Mono.fromSupplier(() -> calculate())` | Gọi `Supplier` khi subscribe | Hoãn tính toán; `Supplier` không khai báo checked exception |
| `Mono.defer(() -> createMono())` | Gọi factory trả về một `Mono` cho mỗi subscription | Hoãn cả quyết định chọn/tạo publisher |
| `Mono.fromRunnable(() -> sideEffect())` | Chạy `Runnable` khi subscribe rồi hoàn tất không có giá trị | Dành cho thao tác trả về `void` |
| `Flux.fromIterable(legacy.findAllBlocking())` | `findAllBlocking()` chạy ngay để tạo đối số | Bọc danh sách đã lấy; việc tạo `Flux` không hoãn truy vấn |
| `Flux.defer(() -> Flux.fromIterable(legacy.findAllBlocking()))` | Gọi `findAllBlocking()` khi subscribe | Hoãn truy vấn, nhưng cần scheduler nếu truy vấn blocking |

**`Mono.fromCallable`** phù hợp nhất với API đồng bộ có trả về **một** kết quả (hoặc `null`) và có thể ném checked exception. Nếu Callable trả về `null`, Reactor hoàn thành `Mono.empty()`; nếu ném exception, subscriber nhận `onError`.

**`Mono.defer`** dùng khi cần hoãn việc tạo một publisher khác; ví dụ đọc thông tin tại thời điểm subscribe rồi quyết định trả `Mono.empty()`, `Mono.error(...)` hoặc một nguồn khác:

~~~java
Mono<String> dynamic = Mono.defer(() -> {
    if (featureEnabled()) {
        return Mono.just("enabled");
    }
    return Mono.empty();
});
~~~

Ví dụ là snippet, giả định `featureEnabled()` có sẵn. Nếu factory trong `defer` lại gọi I/O blocking, chỉ hoãn thời điểm là chưa đủ: vẫn phải định tuyến subscription tới `boundedElastic` hoặc đổi sang API I/O không chặn. Với nguồn một giá trị blocking, `fromCallable` thường dễ đọc hơn `defer(() -> Mono.just(blockingCall()))`.

**Lưu ý về tên gọi cold/hot:** `fromCallable` và `defer` là các nguồn tạo dữ liệu theo subscription. `Mono.just` đã chụp giá trị khi tạo publisher, thường được Reactor dùng để minh họa sắc thái “hot/captured” ở thời điểm assembly; nhưng `just` vẫn có thể gửi cùng giá trị cho nhiều subscriber, không có nghĩa nó tự phát nền hay là một luồng quảng bá sự kiện đang chạy.

## 5. Ví dụ Java 17+ hoàn chỉnh: nhìn thấy chính xác lúc lời gọi chạy

Dùng chương trình sau để xác minh số lần thực thi. `Thread.sleep(30)` chỉ mô phỏng một API blocking; trong ứng dụng thực đó có thể là JDBC, HTTP client đồng bộ hoặc SDK đọc file.

Tạo `build.gradle`:

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
    mainClass = 'PublisherTimingDemo'
}
~~~

Tạo file `src/main/java/PublisherTimingDemo.java`:

~~~java
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public final class PublisherTimingDemo {
    private static final AtomicInteger CALLS = new AtomicInteger();

    private static String blockingRead() throws InterruptedException {
        int invocation = CALLS.incrementAndGet();
        System.out.println("blockingRead call " + invocation);
        Thread.sleep(30); // mo phong I/O dong bo
        return "data-" + invocation;
    }

    public static void main(String[] args) throws InterruptedException {
        System.out.println("assemble eager");
        Mono<String> eager = Mono.just(blockingRead());

        System.out.println("assemble deferred");
        Mono<String> deferred = Mono
            .fromCallable(PublisherTimingDemo::blockingRead)
            .subscribeOn(Schedulers.boundedElastic());

        System.out.println("calls after assembly=" + CALLS.get());

        System.out.println("eager first=" + eager.block());
        System.out.println("eager second=" + eager.block());

        System.out.println("deferred first=" + deferred.block());
        System.out.println("deferred second=" + deferred.block());

        System.out.println("calls at end=" + CALLS.get());
    }
}
~~~

Chạy bằng `gradle run --quiet` hoặc `./gradlew run --quiet` khi có Gradle Wrapper. Với chương trình này, stdout là:

~~~text
assemble eager
blockingRead call 1
assemble deferred
calls after assembly=1
eager first=data-1
eager second=data-1
blockingRead call 2
deferred first=data-2
blockingRead call 3
deferred second=data-3
calls at end=3
~~~

Giải thích từng mốc:

1. Ngay sau chữ `assemble eager`, đối số của `Mono.just` được đánh giá. `blockingRead()` chạy lần 1 **trước khi có publisher `eager`**.
2. `Mono.fromCallable` chỉ lưu một hành động. Sau khi xây xong cả hai publisher, `CALLS` vẫn bằng 1.
3. Hai lần `eager.block()` đều subscribe vào publisher chứa cùng giá trị `data-1`. Chúng không chạy lại `blockingRead`.
4. Mỗi lần `deferred.block()` tạo subscription mới. Callable chạy lần 2 rồi lần 3 và trả `data-2`, `data-3`. `subscribeOn(boundedElastic)` đưa việc thực thi callable lên worker thích hợp.
5. `block()` vẫn khiến **thread main chờ kết quả** trong demo console. Điều đó bình thường để quan sát tuần tự, nhưng **không được gọi `block()` trong luồng xử lý phản ứng trên event-loop WebFlux**.

Tránh dùng tên thread hoặc thời gian đo làm phần output “bất biến” của ví dụ: scheduler có thể thay đổi thread được chọn và thời gian chạy; số lần và thứ tự được in ở đây mới là điều cần kiểm chứng.

## 6. `subscribeOn` giải quyết phần nào? `publishOn` giải quyết phần nào?

Hai thao tác độc lập:

- `fromCallable` / `defer`: hoãn **thời điểm bắt đầu** công việc.
- `subscribeOn(Schedulers.boundedElastic())`: chọn **ngữ cảnh thực thi subscription và nguồn upstream**, giúp một lời gọi đồng bộ blocking không giữ event-loop đang phục vụ các tác vụ reactive khác.

Mẫu được Reactor khuyến nghị khi cần tích hợp API đồng bộ chặn:

~~~java
Mono<Result> publisher = Mono
    .fromCallable(() -> blockingApi.read())
    .subscribeOn(Schedulers.boundedElastic());
~~~

`Result` và `blockingApi` là các kiểu/biến của ứng dụng, nên đây là snippet minh họa. Nên đặt `subscribeOn` ngay sau nguồn cho dễ đọc và để các operator khác không làm người đọc nhầm điểm chuyển thread. Chính `subscribeOn` **không kích hoạt subscribe**; công việc chỉ bắt đầu khi có subscription thực sự.

So sánh ba tình huống:

~~~java
// ĐÚNG: vừa hoãn lệnh blocking, vừa chọn scheduler phù hợp.
Mono<String> a = Mono.fromCallable(() -> legacy.readBlocking())
    .subscribeOn(Schedulers.boundedElastic());

// SAI cho mục tiêu hoãn: legacy.readBlocking() đã chạy trước.
Mono<String> b = Mono.just(legacy.readBlocking())
    .subscribeOn(Schedulers.boundedElastic());

// SAI cho mục tiêu dịch chuyển chính source blocking:
// publishOn ở sau chỉ đổi ngữ cảnh các tín hiệu/operator downstream.
Mono<String> c = Mono.fromCallable(() -> legacy.readBlocking())
    .publishOn(Schedulers.boundedElastic());
~~~

Ba đoạn trên giả định biến `legacy` đã tồn tại, và hàm `readBlocking` trả về String. Với `c`, khi subscribe thông thường, Callable ở phía trước `publishOn` vẫn có thể chạy trên thread subscribe, gây blocking. Có những cách sắp xếp `publishOn` trước operator thực thi blocking, nhưng **mẫu rõ ràng cho một source đồng bộ là `fromCallable(...).subscribeOn(...)`**.

`Schedulers.boundedElastic()` có giới hạn số worker/task queue, dùng để cách ly các lời gọi blocking bắt buộc. Nó **không biến JDBC hay HTTP client đồng bộ thành non-blocking**. Mỗi thao tác vẫn chiếm một worker trong thời gian chờ; quá nhiều tác vụ có thể làm đầy hàng đợi và tăng latency. `Schedulers.parallel()` và `Schedulers.single()` phục vụ loại công việc khác và không phù hợp để đặt một lời gọi I/O blocking kéo dài lên các thread đó.

## 7. Lỗi thực tế trong Spring WebFlux controller

Giả sử controller được gọi trên luồng xử lý HTTP reactive và dùng DAO cũ có API đồng bộ:

~~~java
// Không nên dùng trong controller WebFlux:
@GetMapping("/users/{id}")
public Mono<UserDto> findUser(@PathVariable long id) {
    return Mono.just(legacyDao.findByIdBlocking(id));
}
~~~

Khi xử lý HTTP đi vào `findUser`, câu lệnh `legacyDao.findByIdBlocking(id)` được gọi **trước khi controller trả publisher**. Nếu đây là một thread Netty event-loop, nó có thể chặn việc phục vụ các request khác. Việc đổi return type từ `UserDto` sang `Mono<UserDto>` không làm lời gọi DAO tự trở thành async.

Một cách tích hợp API legacy hợp lý hơn:

~~~java
@GetMapping("/users/{id}")
public Mono<UserDto> findUser(@PathVariable long id) {
    return Mono.fromCallable(() -> legacyDao.findByIdBlocking(id))
        .subscribeOn(Schedulers.boundedElastic())
        .switchIfEmpty(Mono.error(
            new ResponseStatusException(HttpStatus.NOT_FOUND, "User not found")
        ));
}
~~~

**Đây là snippet controller**, cần đặt trong một `@RestController` Spring WebFlux, khai báo `legacyDao` và kiểu `UserDto`, import `Mono`, `Schedulers`, `GetMapping`, `PathVariable`, `ResponseStatusException`, `HttpStatus`. Snippet không phải một chương trình console tự biên dịch nếu đứng riêng.

Luồng xử lý:

~~~text
HTTP vào controller
  -> nhanh chóng tạo Mono.fromCallable(...).subscribeOn(...)
  -> trả publisher
  -> WebFlux subscribe
  -> boundedElastic thực thi DAO đồng bộ
  -> giá trị hoặc lỗi truyền qua Mono
  -> WebFlux hoàn thành HTTP response
~~~

Nếu DAO trả `null`, `Mono.fromCallable` hoàn tất rỗng; `switchIfEmpty` chuyển trường hợp này thành HTTP 404. Nếu DAO ném exception, signal đi theo nhánh `onError` để WebFlux/error handler xử lý; trường hợp đó **không tự động** được coi là 404.

**Không gọi `mono.block()` trong controller** để “lấy giá trị cho tiện”. `block()` vẫn chặn thread gọi; trên những thread được Reactor đánh dấu non-blocking, lệnh này có thể ném `IllegalStateException`. Hãy tiếp tục ghép bằng `map`, `flatMap`, `switchIfEmpty` và trả publisher cho framework.

## 8. Trường hợp `Flux`: từ danh sách có sẵn tới nguồn cần truy vấn

Khi có danh sách đã được chuẩn bị sẵn trong RAM, `Flux.fromIterable(items)` là hợp lý. Nhưng nếu `items` được tạo bằng một lời gọi blocking ngay trong đối số, việc tạo Flux vẫn chặn:

~~~java
// legacyRepository.fetchAllBlocking() chạy ngay ở đây.
Flux<Item> eager = Flux.fromIterable(
    legacyRepository.fetchAllBlocking()
);
~~~

Để hoãn toàn bộ thao tác truy vấn và khởi tạo Flux cho mỗi subscriber:

~~~java
Flux<Item> deferred = Flux
    .defer(() -> Flux.fromIterable(
        legacyRepository.fetchAllBlocking()
    ))
    .subscribeOn(Schedulers.boundedElastic());
~~~

Đây là **snippet** giả định `legacyRepository` có phương thức đồng bộ trả `Iterable<Item>`. Việc dùng `defer` là cần thiết để hoãn cả lời gọi trả về danh sách. Thêm `subscribeOn` nhằm tránh thực hiện chính lời gọi này trên event-loop. Đừng nhầm `Flux.fromIterable` với truy vấn phân trang/streaming thực sự: nếu `fetchAllBlocking()` tải hàng triệu bản ghi vào RAM rồi mới trả danh sách, publisher được tạo muộn vẫn **không** làm thao tác tải cả tập dữ liệu trở thành streaming ít bộ nhớ.

Một nguồn `Flux.create` / callback adapter cũng không tự biến API cũ thành non-blocking; cách callback được gọi và luồng thực thi thực sự phải được xem xét riêng.

## 9. Khi công việc đã bắt đầu, wrapper không làm nó “chưa bắt đầu” được

Quy tắc này còn áp dụng với `CompletableFuture`:

~~~java
// startRequestAsync() bắt đầu công việc tại đây.
CompletableFuture<String> future = startRequestAsync();

// Publisher có thể chưa được subscribe, nhưng future đã chạy.
Mono<String> wrapped = Mono.fromFuture(future);

// Nếu cần mỗi subscriber khởi tạo future riêng khi subscribe:
Mono<String> deferred = Mono.defer(
    () -> Mono.fromFuture(startRequestAsync())
);
~~~

Đây là snippet, `startRequestAsync()` giả định trả `CompletableFuture<String>` đã được lên lịch bởi API async. Khác lời gọi blocking, việc Future đã bắt đầu có thể không chặn thread hiện tại, nhưng nó vẫn là một **side effect đã xảy ra** trước subscription. `fromFuture` nhận một Future đã tồn tại không thể đảo ngược lịch sử khởi tạo của Future.

Sự khác biệt giữa **async thật** và **đẩy blocking sang worker**:

| Cơ chế | Có chặn thread chờ I/O? | Thời điểm bắt đầu |
| --- | --- | --- |
| `Mono.just(blockingRead())` | Có, ngay thread lắp ráp | Trước khi dựng Mono xong |
| `Mono.fromCallable(blockingRead)` không scheduler | Có, thường tại thread subscribe | Khi subscribe |
| `Mono.fromCallable(blockingRead).subscribeOn(boundedElastic)` | Có, nhưng trên worker phù hợp | Khi subscribe và worker chạy task |
| `Mono.fromFuture(existingFuture)` | Phụ thuộc cách Future được tạo và thực thi | Future có thể đã bắt đầu |
| Publisher từ driver I/O reactive thật (ví dụ driver database reactive phù hợp) | Không chiếm thread để chờ I/O theo kiểu blocking | Theo hợp đồng và cơ chế cụ thể của driver |

Đưa blocking vào `boundedElastic` là **giải pháp tương thích** khi chưa thể thay API legacy, không phải phép biến một thư viện synchronous thành reactive driver thực sự.

## 10. Lỗi, `null` và việc lặp lại subscription

### Lỗi xuất hiện lúc nào?

~~~java
// Nếu legacy.readBlocking() ném RuntimeException,
// exception thoát ra lúc tạo Mono, trước khi có subscriber.
Mono<String> eager = Mono.just(legacy.readBlocking());

// Nếu callable ném exception, Reactor gửi onError tại subscription.
Mono<String> lazy = Mono.fromCallable(() -> legacy.readBlocking());
~~~

Khi nguồn được dựng bởi `fromCallable`, có thể xử lý lỗi bằng `onErrorResume`, `onErrorMap` hoặc để error handler của WebFlux tiếp nhận. Với `Mono.just(blockingCall())`, exception đã xảy ra trước lúc publisher được tạo, nên operator `onErrorResume` gắn ở sau `just` không bắt được lỗi của thao tác tính đối số.

### Trả `null` thì sao?

- `Mono.just(null)` không hợp lệ, ném `NullPointerException` khi tạo publisher.
- `Mono.justOrEmpty(value)` có thể phát một giá trị hoặc hoàn tất rỗng, nhưng nếu `value` được tạo bằng lời gọi blocking thì lời gọi ấy **vẫn chạy ngay**.
- `Mono.fromCallable(() -> legacy.lookup())` trả `null` sẽ hoàn thành như `Mono.empty()`; sử dụng `switchIfEmpty` nếu cần chính sách “không tìm thấy”.

### Mỗi subscription có thể chạy lại side effect

~~~java
Mono<String> lookup = Mono.fromCallable(() -> legacy.readBlocking())
    .subscribeOn(Schedulers.boundedElastic());

// Hai subscription => về nguyên tắc hai lần gọi legacy.
lookup.subscribe();
lookup.subscribe();
~~~

Nếu có `retry`, một lần subscription có thể có nhiều lần thực thi nguồn khi xảy ra lỗi; nếu có `repeat` hoặc nhiều subscriber, nguồn cũng có thể được gọi thêm. Với thao tác có side effect như **thu tiền, gửi email, ghi dữ liệu**, cần thiết kế idempotency và ngữ nghĩa retry rõ ràng; không mặc định rằng “tạo một Mono” đồng nghĩa với “thực hiện một lần duy nhất”.

`cache()` có thể dùng để chia sẻ/lưu lại kết quả sau khi có subscription đầu tiên theo ngữ nghĩa operator, nhưng nó thay đổi vòng đời dữ liệu và có thể cache cả tín hiệu lỗi/rỗng; đừng thêm `cache` chỉ để né duplicate execution khi chưa hiểu yêu cầu nghiệp vụ và thời hạn dữ liệu.

### Cancel/timeout không tự ngắt mọi I/O

Hủy subscription hoặc `timeout` có thể ngừng chờ kết quả ở tầng reactive, nhưng **không bảo đảm** thư viện I/O synchronous đã khởi chạy sẽ lập tức dừng. Còn phụ thuộc interrupt, timeout của driver/client, cơ chế cancel của thư viện và trạng thái task. Với API legacy, cấu hình connection timeout/read timeout, quản lý pool kết nối và tài nguyên mở/đóng đúng cách vẫn rất cần thiết.

## 11. Kiểm thử tự động thời điểm thực thi

Có thể kiểm thử sự khác nhau mà không phụ thuộc tốc độ máy hoặc thread scheduler. Giữ ví dụ chính ở mục 5, rồi thay khối `dependencies` trong `build.gradle` bằng khối sau (giữ nguyên các phần `plugins`, `repositories`, `application`):

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

Tạo `src/test/java/LazySourceTest.java`:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class LazySourceTest {
    @Test
    void fromCallableExecutesOnEachSubscription() {
        AtomicInteger calls = new AtomicInteger();
        Mono<Integer> source = Mono.fromCallable(calls::incrementAndGet);

        assertEquals(0, calls.get());

        StepVerifier.create(source).expectNext(1).verifyComplete();
        assertEquals(1, calls.get());

        StepVerifier.create(source).expectNext(2).verifyComplete();
        assertEquals(2, calls.get());
    }

    @Test
    void justCapturesAlreadyComputedValue() {
        AtomicInteger calls = new AtomicInteger();
        Mono<Integer> source = Mono.just(calls.incrementAndGet());

        assertEquals(1, calls.get());

        StepVerifier.create(source).expectNext(1).verifyComplete();
        StepVerifier.create(source).expectNext(1).verifyComplete();

        assertEquals(1, calls.get());
    }
}
~~~

Chạy `gradle test`. Hai test thành công thể hiện:

- `fromCallable` chưa gọi Supplier/Callable tại assembly; sau hai subscription, bộ đếm tăng 2.
- `just` nhận kết quả biểu thức đã tính tại assembly; hai subscription vẫn phát cùng giá trị; bộ đếm không tăng thêm.

Đây là kiểm thử thời điểm/semantics. Nó không cần tạo lời gọi blocking thật, nhờ đó không có test chờ thời gian hoặc phụ thuộc scheduler ngẫu nhiên. Để kiểm tra ứng dụng WebFlux tránh chặn event-loop, còn cần quan sát thread thực tế, latency dưới tải, BlockHound (nếu phù hợp) và driver/client đang dùng.

## 12. Lựa chọn cách thiết kế theo tình huống

| Tình huống | Cách tiếp cận |
| --- | --- |
| Giá trị rẻ, đã có trong RAM, không cần tính lại | `Mono.just(value)` hoặc `Mono.justOrEmpty(value)` |
| Một phép tính thuần, cần chạy khi subscribe | `Mono.fromSupplier(() -> compute())` |
| Một lời gọi đồng bộ blocking trả kết quả, có thể ném exception | `Mono.fromCallable(() -> legacy.call()).subscribeOn(Schedulers.boundedElastic())` |
| Cần quyết định/tạo publisher khác tại thời điểm subscribe | `Mono.defer(() -> choosePublisher())`, kèm scheduler nếu bên trong blocking |
| Nguồn trả `void` và phải được kích hoạt khi subscribe | `Mono.fromRunnable(() -> legacy.doWork())`, kèm scheduler nếu blocking |
| Danh sách đã nằm trong RAM | `Flux.fromIterable(items)` |
| Phải gọi legacy để tải danh sách trước khi phát | `Flux.defer(() -> Flux.fromIterable(legacy.fetchAll())).subscribeOn(Schedulers.boundedElastic())`; cân nhắc phân trang để tránh tải tất cả |
| Có API async/non-blocking bản địa | Dùng publisher/adapter async phù hợp để tránh giữ thread đợi I/O |
| Đã có Future chạy | `Mono.fromFuture(existingFuture)` chỉ bọc Future; dùng `defer` nếu muốn hoãn thao tác khởi tạo Future |

Với API blocking chưa thể loại bỏ trong production, còn phải cân nhắc tốc độ đồng thời, giới hạn database connection pool, timeout, backpressure, retry/idempotency và khả năng queue task. Dùng `boundedElastic` giúp bảo vệ event-loop nhưng vẫn có chi phí tài nguyên và có thể nghẽn nếu upstream vượt khả năng đáp ứng.

## 13. Sai lầm phổ biến và cách sửa

| Sai lầm | Vì sao sai | Sửa |
| --- | --- | --- |
| “Đã trả `Mono` nên non-blocking” | Return type không thay đổi cơ chế I/O đã chạy | Xác định chính xác lệnh nào blocking và thread thực thi |
| `Mono.just(dao.readBlocking())` trong WebFlux | `dao.readBlocking()` chạy ngay trong handler | `Mono.fromCallable(() -> dao.readBlocking()).subscribeOn(boundedElastic)` |
| `fromCallable(() -> cachedValue)` sau khi đã gọi DAO | Chỉ hoãn đọc biến, không hoãn DAO | Đặt **lời gọi DAO** trong callable |
| Thêm `subscribeOn` sau `Mono.just(blockingCall())` | Tác vụ blocking đã hoàn tất trước khi publisher tồn tại | Hoãn công việc trước rồi mới chọn scheduler |
| Dùng `publishOn` sau source blocking | Source upstream vẫn có thể chạy tại subscribe thread | Dùng `subscribeOn` cho source |
| Dùng `Mono.defer` nhưng không chọn scheduler | Hoãn thời điểm, chưa xử lý thread blocking | `defer(...).subscribeOn(boundedElastic)` hoặc `fromCallable` |
| Gọi `block()` trong reactive controller | Có thể chặn event-loop/throw trên NonBlocking thread | Compose bằng operator và return Mono/Flux |
| Tưởng `fromCallable` chỉ chạy một lần | Là nguồn lạnh, thường chạy lại mỗi subscription | Cân nhắc idempotency, retry và cache có chủ đích |
| Tưởng `timeout` luôn ngắt JDBC đang block | Reactive cancellation không bảo đảm dừng driver | Cấu hình timeout/cancellation ở tầng I/O |
| Tưởng `boundedElastic` tăng khả năng phục vụ vô hạn | Worker và queue có hạn | Đặt giới hạn concurrency, bảo vệ pool và đo latency |

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Controller WebFlux trả `Mono.just(jdbcDao.find(id))`. Nếu `find` chờ database 2 giây, controller có thể trả publisher ngay không?

**Đáp án:** Không. Java phải chạy `jdbcDao.find(id)` để tính đối số của `Mono.just` trước, nên method bị chặn khoảng 2 giây (giả sử không có lỗi). Một scheduler gắn sau `just` không đảo ngược thời điểm này.

**Câu 2.** Dùng `Mono.fromCallable(() -> jdbcDao.find(id))` nhưng không có `subscribeOn`. Đã non-blocking chưa?

**Đáp án:** Chưa. Lời gọi được hoãn đến subscription nhưng khi chạy vẫn là I/O đồng bộ blocking trên thread subscribe (trừ khi có cơ chế scheduling khác từ bên ngoài).

**Câu 3.** `Mono.just(service.load())` đã được tạo; sau đó có ba subscriber. Lệnh `service.load()` chạy bao nhiêu lần do câu lệnh tạo publisher ấy?

**Đáp án:** Một lần trong lúc tạo publisher. Ba subscriber thường nhận giá trị đã được capture; không phải ba lần load.

**Câu 4.** Với `Mono.fromCallable(service::load)`, có ba subscription độc lập, không `cache`, `load` chạy bao nhiêu lần?

**Đáp án:** Ba lần nếu các subscription được thực thi bình thường (không hủy trước khi Callable chạy). Mỗi subscription kích hoạt Callable của nguồn lạnh.

**Câu 5.** `Mono.fromCallable(() -> legacy.lookup())` trả `null`. Tín hiệu nào tới downstream?

**Đáp án:** `onComplete` không có `onNext`; trong Reactor, `Mono.fromCallable` quy `null` thành empty. Có thể dùng `switchIfEmpty` để đưa ra giá trị mặc định hoặc lỗi phù hợp.

**Câu 6.** `Mono.fromFuture(startAsync())` có đảm bảo công việc chỉ bắt đầu sau subscription?

**Đáp án:** Không. `startAsync()` được thực hiện khi tính đối số cho `fromFuture`. Nếu cần bắt đầu theo subscription, dùng factory hoãn như `Mono.defer(() -> Mono.fromFuture(startAsync()))`.

## 15. Ghi nhớ và tài liệu chuẩn

**Nguyên tắc quyết định:**

- **Có sẵn giá trị:** dùng `just`.
- **Cần hoãn một hành động tạo giá trị:** dùng `fromCallable` / `fromSupplier`.
- **Cần hoãn cả việc chọn hoặc dựng một publisher:** dùng `defer`.
- **Hành động hoãn vẫn là blocking:** bổ sung `subscribeOn(Schedulers.boundedElastic())` cho nguồn blocking, hoặc ưu tiên API reactive non-blocking thực sự.
- **Hành động đã thực thi trước assembly:** việc bọc kết quả vào `Mono`/`Flux` không thể biến nó thành công việc được trì hoãn.

Tham khảo:

1. [Project Reactor FAQ — How Do I Wrap a Synchronous, Blocking Call?](https://projectreactor.io/docs/core/release/reference/faq.html) — mẫu `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`.
2. [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html) — khác biệt `subscribeOn` / `publishOn`, `boundedElastic` và giới hạn tài nguyên.
3. [Project Reactor — Hot Versus Cold](https://projectreactor.io/docs/core/3.7.0/reference/advancedFeatures/reactor-hotCold.html) — `Mono.just` capture dữ liệu lúc assembly, `defer` chạy theo subscription.
4. [Reactor Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html) — contract `just`, `fromCallable`, `defer`, `fromFuture`.
5. [Spring WebFlux Reference](https://docs.spring.io/spring-framework/reference/web/webflux.html) — lập trình phản ứng trong HTTP stack Spring.
