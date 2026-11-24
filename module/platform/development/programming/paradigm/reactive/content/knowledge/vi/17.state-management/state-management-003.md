# Biến khả biến trong lambda và nguy cơ tranh chấp dữ liệu

Lambda giúp viết pipeline reactive ngắn gọn: `map` biến đổi phần tử, `filter` chọn phần tử, `flatMap` gọi một Publisher khác và `doOnNext` quan sát tín hiệu. Tuy nhiên, lambda có thể đọc hoặc thay đổi trạng thái nằm bên ngoài nó. Khi nhiều tín hiệu được xử lý đồng thời, hoặc cùng một pipeline được nhiều Subscriber sử dụng, biến khả biến dùng chung có thể trở thành nguồn gây race condition, mất cập nhật và lỗi khó tái hiện.

Java yêu cầu biến cục bộ được lambda capture phải là `final` hoặc *effectively final*. Quy tắc này chỉ ngăn việc gán lại biến tham chiếu; nó không làm cho object được tham chiếu trở thành bất biến hoặc an toàn luồng. Một mảng, collection, đối tượng nghiệp vụ hay bộ đếm vẫn có thể bị thay đổi từ nhiều luồng.

Chủ đề này thuộc chương **Trạng thái** của REACTIVE_PROGRAMMING. Module học tư duy reactive qua các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; đồng thời thực hành Mono, Flux, kết hợp toán tử, scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Khi viết lambda trong pipeline, hãy xác định trạng thái thuộc riêng một subscription hay được chia sẻ giữa nhiều luồng, rồi chọn cách quản lý phù hợp.

## Lambda capture không đồng nghĩa với trạng thái bất biến

Một lambda có thể capture biến cục bộ nếu biến đó là `final` hoặc effectively final:

```java
int multiplier = 10;

Flux<Integer> scaled = Flux.range(1, 3)
    .map(value -> value * multiplier);
```

`multiplier` không bị gán lại sau khi khởi tạo, nên lambda được phép sử dụng. Giá trị của nó không thay đổi trong phạm vi lambda; ví dụ này không có trạng thái dùng chung cần cập nhật.

Nhưng tham chiếu effectively final vẫn có thể trỏ tới object khả biến:

```java
int[] total = {0};

Flux<Integer> values = Flux.range(1, 3)
    .doOnNext(value -> total[0] += value);
```

Biến `total` không bị gán lại, nhưng phần tử `total[0]` được thay đổi. Trình biên dịch chấp nhận đoạn mã vì tham chiếu mảng là effectively final. Điều đó không bảo đảm phép cộng an toàn nếu nhiều luồng cùng cập nhật phần tử này.

Các trường hợp capture phổ biến gồm:

| Giá trị được capture | Có thể thay đổi không? | Điều cần chú ý |
|---|---|---|
| Biến primitive effectively final | Không thể gán lại trong lambda | Đọc giá trị thường an toàn vì giá trị không đổi |
| Tham chiếu tới object bất biến | Không thay đổi trạng thái object | Phù hợp để chia sẻ giữa các luồng |
| Tham chiếu tới array hoặc collection | Có | Các phần tử có thể bị cập nhật đồng thời |
| Tham chiếu tới object có setter hoặc field mutable | Có | Cần quản lý đồng bộ hoặc tránh chia sẻ |
| `AtomicInteger`, `AtomicLong`, `LongAdder` | Có, qua API đồng bộ hóa của chúng | Chọn đúng loại theo yêu cầu nhất quán và contention |

## Vì sao tranh chấp dữ liệu xuất hiện trong pipeline reactive?

Reactive Streams yêu cầu tín hiệu của một subscription được tuần tự hóa: một Subscriber không nhận các lời gọi `onNext` chồng lấn cho cùng subscription. Điều này giúp một pipeline tuần tự có thể xử lý tín hiệu mà không cần khóa mọi biến cục bộ của nó.

Tuy nhiên, không thể suy rộng tính tuần tự đó thành bảo đảm rằng mọi lambda trong ứng dụng chỉ chạy trên một thread. Nhiều tình huống tạo ra thực thi đồng thời:

- `parallel()` chia một luồng thành nhiều rail và `runOn` có thể chạy các rail trên nhiều worker.
- `flatMap` có thể có nhiều inner Publisher hoạt động cùng lúc; các callback của chúng có thể được thực thi trên các thread khác nhau.
- Một Publisher có thể được nhiều Subscriber subscribe độc lập; các subscription có thể chạy đồng thời.
- Nhiều pipeline khác nhau có thể capture cùng một service hoặc object mutable dùng chung.
- Callback từ event listener hoặc nguồn bên ngoài có thể được gọi bởi nhiều thread.

Race condition xảy ra khi kết quả phụ thuộc vào thứ tự xen kẽ của các thao tác mà không có cơ chế đồng bộ phù hợp. Một thao tác như `counter++` không phải một bước nguyên tử; về khái niệm nó gồm đọc giá trị, tính giá trị mới và ghi lại. Hai thread có thể cùng đọc một giá trị rồi ghi đè kết quả của nhau.

Ngoài race condition, còn có vấn đề visibility theo Java Memory Model: nếu một thread ghi trạng thái và thread khác đọc mà không có quan hệ *happens-before* phù hợp, thread đọc không được bảo đảm quan sát giá trị mới nhất. Việc chuyển scheduler hoặc dùng lambda không tự tạo ra cơ chế đồng bộ cho object được chia sẻ.

## Ví dụ lỗi: cập nhật bộ đếm dùng chung trong các rail song song

Đoạn mã sau capture một mảng rồi cập nhật phần tử của nó từ các rail:

```java
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;

int[] total = {0};

Flux.range(1, 10_000)
    .parallel()
    .runOn(Schedulers.parallel())
    .doOnNext(value -> total[0] += value)
    .sequential()
    .blockLast();

System.out.println("total=" + total[0]);
```

Mỗi rail có thể cập nhật `total[0]` trên một worker khác nhau. Phép cộng không nguyên tử nên một số lần cập nhật có thể bị mất. Kết quả có thể khác nhau giữa các lần chạy và không được bảo đảm bằng tổng toán học của dãy.

Đổi mảng thành `ArrayList<Integer>` rồi gọi `add` từ nhiều rail cũng không giải quyết vấn đề; `ArrayList` không hỗ trợ cập nhật đồng thời. Dùng `HashMap` hoặc object nghiệp vụ mutable tương tự cũng có rủi ro nếu nhiều callback cùng sửa cấu trúc hoặc field bên trong.

Điểm cần sửa là quyền sở hữu trạng thái. Nếu tổng chỉ là kết quả của một phép biến đổi luồng, không cần đặt một accumulator dùng chung bên ngoài lambda. Hãy để pipeline tổng hợp giá trị sau khi các kết quả song song được hợp nhất.

## Ưu tiên phép biến đổi bất biến và tổng hợp trong pipeline

Thay vì thay đổi một biến bên ngoài, hãy biến mỗi phần tử thành kết quả mới rồi dùng operator tổng hợp:

```java
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;

Mono<Long> total = Flux.range(1, 10_000)
    .parallel()
    .runOn(Schedulers.parallel())
    .map(value -> expensiveCalculation(value))
    .sequential()
    .reduce(0L, Long::sum);
```

Các phép tính độc lập có thể chạy trên các rail. `sequential()` hợp nhất kết quả thành một Flux; `reduce` phía sau tổng hợp các giá trị theo một chuỗi tín hiệu tuần tự của subscription đó. Không có accumulator mutable dùng chung do lambda bên ngoài quản lý.

Với luồng không cần song song, `reduce` cũng là cách rõ ràng để tính tổng:

```java
Mono<Integer> sum = Flux.range(1, 100)
    .reduce(0, Integer::sum);
```

`reduce` giữ accumulator thuộc subscription và phát một kết quả khi nguồn hoàn tất. Nếu cần phát trạng thái tích lũy sau mỗi phần tử, `scan` có thể biểu diễn quá trình đó:

```java
Flux<Integer> runningTotals = Flux.range(1, 5)
    .scan(0, Integer::sum);
```

Kết quả là `0, 1, 3, 6, 10, 15`. Cách viết này diễn tả phép biến đổi trạng thái như một phần của pipeline, dễ kiểm thử hơn việc thay đổi biến bên ngoài trong `doOnNext`.

Với collection, hãy dùng operator tạo collection theo subscription như `collectList()` khi cần gom dữ liệu hữu hạn:

```java
Mono<List<Order>> allOrders = orderSource()
    .collectList();
```

Không nên dùng `collectList()` cho nguồn vô hạn hoặc nguồn có thể phát lượng dữ liệu không giới hạn vì collection sẽ tiếp tục tăng. Nếu cần xử lý theo batch, dùng `buffer` hoặc `window` với giới hạn phù hợp.

## Khi cần bộ đếm dùng chung, chọn primitive đồng bộ hóa

Đôi khi trạng thái dùng chung là yêu cầu thật, chẳng hạn metric đếm số sự kiện đã xử lý. Khi đó, dùng cấu trúc hỗ trợ cập nhật đồng thời.

### `AtomicInteger` và `AtomicLong`

```java
import java.util.concurrent.atomic.AtomicLong;
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;

AtomicLong processed = new AtomicLong();

Flux.range(1, 10_000)
    .parallel()
    .runOn(Schedulers.parallel())
    .doOnNext(value -> processed.incrementAndGet())
    .sequential()
    .blockLast();

long count = processed.get();
```

`incrementAndGet()` là thao tác nguyên tử, nên các lần tăng đồng thời không ghi đè lẫn nhau. `AtomicLong` phù hợp khi cần một giá trị đếm chính xác được cập nhật qua nhiều thread.

Tuy nhiên, atomic không làm cho một chuỗi thao tác tùy ý trở thành transaction. Ví dụ `if (balance.get() >= amount) balance.addAndGet(-amount)` vẫn có thể sai vì kiểm tra và cập nhật là hai thao tác riêng. Với invariant nhiều bước, cần một phép cập nhật nguyên tử phù hợp như `updateAndGet`, khóa hoặc mô hình quản lý trạng thái khác.

### `LongAdder` cho metric có nhiều cập nhật đồng thời

Khi có contention cao và mục tiêu là đếm metric, `LongAdder` thường có throughput tốt hơn `AtomicLong` vì nó phân tán cập nhật qua nhiều cell rồi cộng lại khi đọc:

```java
import java.util.concurrent.atomic.LongAdder;

LongAdder receivedEvents = new LongAdder();

eventSource()
    .doOnNext(event -> receivedEvents.increment())
    .subscribe();

long observedCount = receivedEvents.sum();
```

`LongAdder` phù hợp cho thống kê như số sự kiện nhận được, số lần retry hoặc số bản ghi bị bỏ. `sum()` không phải snapshot nguyên tử tuyệt đối trong lúc các thread vẫn cập nhật; nếu cần một giá trị nhất quán tức thời để quyết định nghiệp vụ, hãy chọn cơ chế khác.

## Collection và map dùng chung cần cấu trúc an toàn luồng

Nếu nhiều callback cần cập nhật map dùng chung, có thể dùng `ConcurrentHashMap` thay cho `HashMap`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

ConcurrentHashMap<String, LongAdder> countsByType = new ConcurrentHashMap<>();

eventSource().subscribe(event ->
    countsByType
        .computeIfAbsent(event.type(), ignored -> new LongAdder())
        .increment()
);
```

`computeIfAbsent` đảm bảo việc tạo mapping cho một khóa được xử lý an toàn khi nhiều thread cạnh tranh. `LongAdder` xử lý cập nhật bộ đếm cho từng loại sự kiện. Dù vậy, map vẫn có thể tăng không giới hạn nếu số `event.type()` là vô hạn hoặc do dữ liệu đầu vào không được kiểm soát; cấu trúc an toàn luồng không tự giải quyết vòng đời và dung lượng trạng thái.

Nếu cần cập nhật một giá trị theo khóa trong một thao tác nguyên tử, `ConcurrentHashMap.compute` có thể phù hợp:

```java
ConcurrentHashMap<String, Integer> attemptsById = new ConcurrentHashMap<>();

attemptsById.compute(requestId, (key, oldValue) ->
    oldValue == null ? 1 : oldValue + 1
);
```

Hàm remapping của `compute` cần ngắn, không blocking và tránh gọi lại chính map theo cách gây đệ quy hoặc deadlock. Nếu giá trị là object mutable, việc map an toàn không đồng nghĩa mọi thay đổi bên trong object đó cũng an toàn.

## Khóa và `synchronized`: dùng khi cần bảo vệ invariant nhiều bước

Khi trạng thái cần duy trì một invariant gồm nhiều field, atomic riêng lẻ có thể không đủ. Có thể dùng `synchronized` để bảo vệ toàn bộ thao tác đọc và ghi:

```java
final class Inventory {
    private int available;

    Inventory(int initial) {
        this.available = initial;
    }

    synchronized boolean reserve(int quantity) {
        if (quantity <= 0 || available < quantity) {
            return false;
        }
        available -= quantity;
        return true;
    }

    synchronized int available() {
        return available;
    }
}
```

Khóa bảo vệ điều kiện kiểm tra và cập nhật như một vùng tới hạn. Tuy nhiên, không nên giữ lock trong lúc gọi API mạng, chờ database hoặc thực hiện công việc lâu. Nếu một callback reactive chạy trên event loop hoặc worker dùng chung mà bị chặn bởi lock, nhiều pipeline khác có thể bị chậm. Cần thiết kế vùng tới hạn ngắn và cân nhắc chuyển mô hình trạng thái sang một actor hoặc một luồng xử lý tuần tự.

## Cô lập trạng thái theo subscription

Nếu mỗi Subscriber cần trạng thái riêng, đừng đặt accumulator trong một object mutable dùng chung bên ngoài Publisher. Hãy tạo trạng thái bên trong factory của `defer` hoặc dùng operator có state theo subscription:

```java
Flux<Summary> summaries = Flux.defer(() -> {
    Map<String, Long> counts = new HashMap<>();

    return eventSource()
        .doOnNext(event -> counts.merge(event.type(), 1L, Long::sum))
        .map(event -> new Summary(event.id(), Map.copyOf(counts)));
});
```

Mỗi subscription gọi factory và tạo một map mới, nên các subscription không chia sẻ cùng map. Ví dụ này giả định mỗi subscription xử lý tín hiệu tuần tự và `eventSource()` cung cấp một Publisher mới hoặc một nguồn có thể subscribe nhiều lần. Nếu bên trong pipeline có `parallel()` hoặc nhiều callback đồng thời cập nhật `counts`, map cục bộ vẫn có thể gặp race; “cục bộ trong lambda” không đồng nghĩa “một thread duy nhất”.

Nếu cần state theo từng phần tử và không cần giữ lịch sử, ưu tiên `scan`, `reduce`, `collect` hoặc các operator chuyên biệt. Nếu cần trạng thái qua nhiều subscription, hãy quản lý vòng đời rõ ràng và dùng cấu trúc đồng bộ hóa phù hợp.

## `flatMap` và trạng thái mutable được capture

`flatMap` có thể chạy nhiều inner Publisher đồng thời. Vì vậy, lambda mapper hoặc callback của inner Publisher có thể được thực thi trên các thread khác nhau, tùy nguồn và scheduler:

```java
List<Result> results = new ArrayList<>();

requests()
    .flatMap(request -> callRemote(request)
        .doOnNext(results::add))
    .then()
    .block();
```

`ArrayList` được capture bởi callback của các inner Publisher. Nếu nhiều inner phát đồng thời, nhiều thread có thể gọi `add` trên cùng một list. Điều này không an toàn và có thể làm hỏng cấu trúc hoặc mất phần tử.

Nếu thật sự cần collection kết quả, hãy để Reactor gom chúng:

```java
Mono<List<Result>> results = requests()
    .flatMap(this::callRemote, 8)
    .collectList();
```

`collectList()` gom các phần tử thành collection thuộc subscription và chỉ phát list khi nguồn hoàn tất. Giới hạn `8` kiểm soát số inner Publisher hoạt động đồng thời. Nếu thứ tự đầu vào phải được giữ, cân nhắc `concatMap` thay vì `flatMap`.

Nếu cần xử lý mỗi kết quả ngay và không cần giữ toàn bộ list, hãy tiếp tục biến đổi hoặc ghi dữ liệu theo từng phần tử. Tránh tích lũy toàn bộ kết quả trong heap khi nguồn có thể lớn hoặc vô hạn.

## Chia sẻ một pipeline không đồng nghĩa chia sẻ state an toàn

Một Publisher có thể được chia sẻ cho nhiều Subscriber bằng `share`, `publish().refCount(...)` hoặc cơ chế tương tự. Nếu lambda upstream capture một object mutable dùng chung, nhiều subscriber hoặc callback vẫn có thể tương tác với object đó theo vòng đời của nguồn. Hãy xác định trạng thái nằm trước hay sau ranh giới chia sẻ.

```java
AtomicLong totalSeen = new AtomicLong();

Flux<Event> shared = eventSource()
    .doOnNext(event -> totalSeen.incrementAndGet())
    .share();
```

Ở đây, bộ đếm nằm upstream của `share`, nên nó đếm tín hiệu đi qua nguồn chia sẻ một lần cho mỗi lần phát upstream. Nếu đặt `doOnNext` sau `share`, mỗi Subscriber có thể thực hiện callback riêng cho cùng một sự kiện và bộ đếm tăng theo số lần quan sát downstream. Vị trí operator quyết định ý nghĩa metric, nhưng `AtomicLong` vẫn cần thiết nếu các cập nhật có thể đến đồng thời.

Đừng dùng một biến mutable dùng chung để truyền dữ liệu nghiệp vụ giữa các Subscriber. Hãy phát dữ liệu qua Publisher, dùng `Context` cho metadata gắn với subscription khi phù hợp, hoặc dùng kho trạng thái có giao thức đồng bộ rõ ràng.

## Side effect trong lambda cần có chủ đích

Các operator như `map` và `filter` nên được dùng chủ yếu cho phép biến đổi thuần. Đặt side effect trong `doOnNext` giúp biểu đạt rõ đây là hành động quan sát hoặc tích hợp, nhưng không làm side effect tự động an toàn luồng hay exactly-once.

Một callback có thể được thực thi lại nếu nguồn được subscribe lại, retry xảy ra hoặc nhiều subscription cùng chạy. Nếu side effect là ghi dữ liệu, gửi thông báo hoặc trừ tiền, cần idempotency key, transaction hoặc cơ chế chống xử lý trùng. Không nên giả định một lambda chỉ chạy một lần vì nó xuất hiện một lần trong mã nguồn.

Khi side effect cần thực hiện bất đồng bộ và có thể thất bại, hãy biểu diễn nó bằng Publisher trong `flatMap` hoặc `concatMap` thay vì gọi hàm blocking bên trong `doOnNext`:

```java
Flux<Void> writes = events()
    .concatMap(event -> repository.save(event).then());
```

`concatMap` giữ thứ tự và chỉ tiến tới phần tử tiếp theo khi thao tác lưu hiện tại hoàn tất. Nếu cho phép nhiều thao tác lưu đồng thời, dùng `flatMap` với concurrency phù hợp và bảo đảm repository hỗ trợ mức tải đó.

## Kiểm thử race condition và tính đúng của trạng thái

Race condition thường khó tái hiện bằng một lần chạy thủ công. Hãy viết test có số lượng phần tử đủ lớn và kiểm tra invariant cần giữ, đồng thời tránh khẳng định rằng một test đơn lẻ chứng minh mã hoàn toàn thread-safe.

Ví dụ kiểm thử bộ đếm nguyên tử trong các rail song song:

```java
import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.scheduler.Schedulers;
import static org.junit.jupiter.api.Assertions.assertEquals;

class SharedStateTest {
    @Test
    void atomicCounterDoesNotLoseConcurrentIncrements() {
        AtomicLong count = new AtomicLong();

        Flux.range(1, 10_000)
            .parallel()
            .runOn(Schedulers.parallel())
            .doOnNext(value -> count.incrementAndGet())
            .sequential()
            .blockLast();

        assertEquals(10_000L, count.get());
    }
}
```

Test xác nhận `AtomicLong` không mất lần tăng trong kịch bản được tạo. Với logic nghiệp vụ phức tạp, hãy kiểm thử invariant như không đặt hàng vượt tồn kho, không xử lý trùng event ID hoặc tổng tiền không âm; kiểm tra cả nhiều subscription và nhiều pipeline cùng truy cập state.

Với logic có thể biểu diễn bằng operator thuần, kiểm thử kết quả trực tiếp thường đơn giản hơn:

```java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

class ReductionTest {
    @Test
    void computesTotalWithoutExternalMutableState() {
        StepVerifier.create(Flux.range(1, 4)
                .reduce(0, Integer::sum))
            .expectNext(10)
            .verifyComplete();
    }
}
```

Test thứ hai không cần shared accumulator; kết quả được biểu diễn trực tiếp bởi pipeline. Đây thường là thiết kế dễ kiểm thử và dễ reasoning hơn.

## Những lỗi thiết kế thường gặp

**Cho rằng effectively final làm object an toàn luồng.** Quy tắc capture chỉ giới hạn việc gán lại biến tham chiếu; object được tham chiếu vẫn có thể mutable.

**Cập nhật array hoặc collection từ nhiều rail.** Các thao tác như `counter[0]++` hoặc `list.add` không tự nguyên tử. Dùng operator tổng hợp hoặc cấu trúc đồng bộ hóa phù hợp.

**Dùng atomic cho invariant nhiều bước.** Atomic bảo vệ thao tác đơn hoặc phép cập nhật được định nghĩa; nó không tự biến chuỗi kiểm tra rồi ghi thành transaction.

**Nhầm tín hiệu tuần tự với toàn bộ ứng dụng đơn luồng.** Một subscription tuần tự không ngăn các subscription khác, inner Publisher hoặc rail khác chạy đồng thời.

**Dùng `LongAdder` cho quyết định cần snapshot chính xác.** `LongAdder` phù hợp với metric có contention; `sum()` trong lúc cập nhật không phải snapshot nguyên tử tuyệt đối.

**Tạo map/list mới trong lambda nhưng vẫn chạy song song.** Trạng thái cục bộ theo subscription có thể an toàn giữa các subscription, nhưng nếu nhiều callback trong cùng subscription cùng sửa nó thì vẫn có race.

**Đặt side effect trong `map` rồi nghĩ nó chỉ chạy một lần.** Retry, resubscribe hoặc nhiều subscription có thể gọi lại lambda. Thiết kế side effect idempotent và quản lý vòng đời rõ ràng.

**Giữ lock khi gọi dịch vụ bên ngoài.** Lock dài có thể chặn worker và làm giảm khả năng đáp ứng của pipeline. Giữ vùng tới hạn ngắn và không thực hiện blocking I/O bên trong khóa.

## Tự kiểm tra

1. Vì sao Java cho phép lambda capture một biến mảng effectively final nhưng vẫn không bảo đảm phần tử mảng an toàn khi nhiều thread cập nhật?
2. Reactive Streams tuần tự hóa tín hiệu cho một subscription. Vì sao điều đó không bảo vệ object mutable được nhiều subscription hoặc nhiều rail chia sẻ?
3. Vì sao `counter++` có thể mất cập nhật khi được gọi từ nhiều worker?
4. Khi nào nên dùng `reduce` hoặc `scan` thay cho biến accumulator bên ngoài lambda?
5. So sánh `AtomicLong` và `LongAdder`: loại nào phù hợp cho metric có nhiều cập nhật, và loại nào phù hợp hơn khi cần cập nhật nguyên tử một giá trị chính xác?
6. Vì sao `ConcurrentHashMap` không tự làm object mutable được lưu bên trong map trở nên thread-safe?
7. Một `flatMap` gọi nhiều inner Publisher và cùng thêm kết quả vào `ArrayList`. Rủi ro nằm ở đâu và có thể thay bằng operator nào?
8. Vì sao một side effect trong lambda có thể chạy nhiều lần dù biểu thức lambda chỉ được viết một lần?

Khi xác định rõ ai sở hữu trạng thái, trạng thái tồn tại trong bao lâu và callback nào có thể chạy đồng thời, bạn có thể ưu tiên dữ liệu bất biến cùng các operator tổng hợp, chỉ dùng atomic hoặc collection đồng bộ hóa khi thật sự cần chia sẻ, và tránh race condition trong pipeline reactive.
