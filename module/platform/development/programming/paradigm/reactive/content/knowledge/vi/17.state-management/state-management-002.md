# Trạng thái riêng cho mỗi đăng ký và trạng thái dùng chung

## Một publisher có thể được đăng ký nhiều lần

Trong Project Reactor, `Mono` và `Flux` mô tả cách phát dữ liệu qua một pipeline. Khi một subscriber gọi `subscribe`, publisher tạo một subscription với demand và vòng đời riêng. Nếu cùng một publisher được đăng ký nhiều lần, các subscription có thể chạy độc lập hoặc cùng quan sát một nguồn được chia sẻ, tùy cách publisher được xây dựng.

Sự khác biệt này ảnh hưởng trực tiếp đến trạng thái trong ứng dụng. Một bộ đếm, bộ tích lũy, cursor, cache hoặc đối tượng cấu hình có thể được tạo mới cho từng subscription, hoặc được nhiều subscription cùng truy cập. Nếu không xác định rõ phạm vi sở hữu, trạng thái có thể bị dùng chung ngoài ý muốn, gây kết quả sai, race condition hoặc rò rỉ dữ liệu giữa các request.

Trong module `REACTIVE_PROGRAMMING`, trạng thái cần được xem xét cùng với vòng đời `Publisher`–`Subscriber`, việc truyền demand, scheduler và cancellation. Một pipeline reactive có thể chạy trên nhiều thread hoặc có nhiều subscriber; vì vậy, vị trí tạo trạng thái quan trọng không kém vị trí sử dụng nó.

## Ba phạm vi trạng thái thường gặp

| Phạm vi | Vòng đời | Ví dụ | Câu hỏi cần trả lời |
|---|---|---|---|
| Riêng cho subscription | Tạo khi một subscriber đăng ký và kết thúc cùng subscription | Bộ đếm cục bộ, cursor đọc, bộ tích lũy của một lần xử lý | Mỗi subscriber có cần trạng thái độc lập không? |
| Chia sẻ giữa các subscription | Sống lâu hơn một subscription và có thể được nhiều subscriber truy cập | Metric, cache, cấu hình, trạng thái dịch vụ | Có cần đồng bộ, phân vùng theo người dùng hoặc giới hạn thời gian sống không? |
| Chia sẻ tín hiệu của publisher | Nhiều subscriber cùng nhận tín hiệu từ một lần thực thi upstream | `share`, `publish`, `cache`, `Sinks.Many` | Subscriber đến muộn có nhận lịch sử không, và ai sở hữu vòng đời nguồn? |

Hai phạm vi sau thường bị nhầm. Chia sẻ một publisher hoặc một lần phát không tự động có nghĩa là chia sẻ một đối tượng trạng thái nghiệp vụ. `share()` có thể dùng chung một subscription upstream cho nhiều subscriber đang tham gia; `AtomicLong` được capture trong lambda lại có thể dùng chung một bộ đếm qua nhiều subscription độc lập. Đây là hai quyết định khác nhau.

## Tạo trạng thái riêng bằng defer

`defer` nhận một supplier và gọi supplier đó cho từng subscription. Đây là cách trực tiếp để tạo publisher cùng trạng thái mới mỗi lần đăng ký:

```java
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Flux;

Flux<Integer> sequencePerSubscriber = Flux.defer(() -> {
    AtomicInteger counter = new AtomicInteger();

    return Flux.range(1, 3)
        .map(ignored -> counter.incrementAndGet());
});
```

Mỗi subscription gọi lại lambda của `defer`, tạo một `AtomicInteger` mới. Vì vậy, subscriber thứ nhất nhận `1, 2, 3`; subscriber thứ hai cũng bắt đầu lại từ `1`. `AtomicInteger` ở ví dụ này không bắt buộc để bảo vệ truy cập đồng thời bên trong một subscription tuần tự; nó được dùng để làm rõ đối tượng được tạo mới theo từng lần đăng ký. Nếu trạng thái chỉ được truy cập tuần tự, một biến cục bộ đơn giản thường đủ.

Nếu viết bộ đếm ở ngoài `defer`, phạm vi sẽ thay đổi:

```java
AtomicInteger sharedCounter = new AtomicInteger();

Flux<Integer> sequenceSharedAcrossSubscribers = Flux.range(1, 3)
    .map(ignored -> sharedCounter.incrementAndGet());
```

`sharedCounter` được tạo khi dựng pipeline và được lambda giữ lại. Hai subscription độc lập cùng cập nhật một bộ đếm: subscriber đầu có thể nhận `1, 2, 3`, subscriber tiếp theo nhận `4, 5, 6`. Đây là trạng thái dùng chung có chủ ý nếu cần một số thứ tự toàn cục trong một tiến trình; nếu muốn đếm riêng từng request, vị trí tạo counter phải nằm trong `defer`.

### Phân biệt just, fromCallable và defer

Thời điểm đánh giá biểu thức có thể làm thay đổi phạm vi trạng thái:

```java
Mono<Profile> captured = Mono.just(profileRepository.load(userId));

Mono<Profile> lazyPerSubscription = Mono.fromCallable(
    () -> profileRepository.load(userId)
);

Mono<Profile> publisherPerSubscription = Mono.defer(
    () -> profileClient.findById(userId)
);
```

- `Mono.just(expression)` đánh giá `expression` ngay khi Java dựng publisher; các subscriber sau đó nhận cùng giá trị đã được tính.
- `Mono.fromCallable(...)` trì hoãn lời gọi hàm đến subscription. Với publisher này, mỗi subscription gọi lại callable.
- `Mono.defer(...)` gọi supplier để tạo một publisher cho mỗi subscription; phù hợp khi cần chọn nguồn, tham số hoặc trạng thái mới theo thời điểm đăng ký.

Nếu `profileRepository.load` là API blocking, `fromCallable` chỉ trì hoãn lời gọi; cần điều phối nó trên scheduler phù hợp, chẳng hạn `subscribeOn(Schedulers.boundedElastic())`. Việc trì hoãn không biến API blocking thành non-blocking.

## Tạo state tường minh bằng Flux.generate

`Flux.generate` phù hợp với nguồn đồng bộ cần duy trì trạng thái giữa các lần gọi generator. Overload có `stateSupplier` tạo state riêng cho từng subscription; generator nhận state hiện tại và trả state kế tiếp. Mỗi lần gọi generator chỉ được phát tối đa một tín hiệu `onNext` hoặc một tín hiệu kết thúc.

```java
import reactor.core.publisher.Flux;

Flux<Integer> countdown = Flux.generate(
    () -> 3,
    (remaining, sink) -> {
        if (remaining > 0) {
            sink.next(remaining);
            return remaining - 1;
        } else {
            sink.complete();
            return remaining;
        }
    }
);
```

Mỗi subscription bắt đầu với state `3` và phát `3, 2, 1`, sau đó hoàn tất. State ở đây là số nguyên bất biến nên không có đối tượng mutable bị chia sẻ. Nếu generator cần một tài nguyên hoặc đối tượng mutable, hãy tạo nó trong `stateSupplier` thay vì capture từ bên ngoài.

Có thể cung cấp state consumer để giải phóng tài nguyên khi generator kết thúc hoặc bị hủy:

```java
import reactor.core.publisher.Flux;

Flux<Integer> values = Flux.generate(
    () -> new Cursor(),
    (cursor, sink) -> {
        if (cursor.hasNext()) {
            sink.next(cursor.next());
        } else {
            sink.complete();
        }
        return cursor;
    },
    Cursor::close
);
```

`stateSupplier` được gọi riêng cho mỗi subscription; `Cursor::close` dọn tài nguyên state khi subscription kết thúc. Ví dụ giả định `Cursor` là lớp ứng dụng có các phương thức `hasNext`, `next` và `close`. Trong mã thực tế, cần bảo đảm việc đóng cursor an toàn nếu nguồn kết thúc, phát lỗi hoặc bị hủy.

## Trạng thái tích lũy với scanWith và reduceWith

`scan` phát các giá trị tích lũy trung gian, còn `reduce` chỉ phát kết quả cuối khi nguồn hoàn tất. Nếu seed là đối tượng mutable, không nên truyền một instance được tạo ở thời điểm assembly rồi để nhiều subscription cùng sửa đổi nó. Dùng `scanWith` hoặc `reduceWith` với supplier để tạo seed riêng cho mỗi subscription.

```java
import reactor.core.publisher.Flux;

Flux<Integer> runningTotals = Flux.just(2, 3, 5)
    .scanWith(() -> 0, Integer::sum);
```

`scanWith` gọi supplier để lấy seed cho mỗi subscription. Với seed `0`, luồng phát các giá trị tích lũy `0, 2, 5, 10`. Nếu không muốn phát seed ban đầu, có thể bỏ phần tử đầu ra bằng một toán tử phù hợp, nhưng cần cân nhắc nguồn có rỗng hay không.

Với phép tổng hợp chỉ cần kết quả cuối:

```java
import reactor.core.publisher.Mono;

Mono<Long> totalBytes = byteSizes.reduceWith(
    () -> 0L,
    (total, size) -> total + size
);
```

`reduceWith` tạo seed theo subscription và phát một kết quả sau khi nguồn hoàn tất. Nếu nguồn rỗng, seed được dùng làm kết quả. Các phép tích lũy immutable như số nguyên hoặc `BigDecimal` thường dễ suy luận hơn việc sửa đổi một collection dùng chung.

## Trạng thái chia sẻ có chủ ý

Một số trạng thái cần được nhiều subscription cùng cập nhật hoặc đọc, chẳng hạn metric của tiến trình, cache dùng chung, bảng tra cứu hoặc bộ đếm tổng request. Khi chia sẻ state mutable, cần chọn cấu trúc dữ liệu có bảo vệ đồng thời phù hợp.

```java
import java.util.concurrent.atomic.LongAdder;
import reactor.core.publisher.Flux;

LongAdder processedEvents = new LongAdder();

Flux<Event> observedEvents = eventSource
    .doOnNext(event -> processedEvents.increment());
```

`processedEvents` được tạo bên ngoài pipeline nên mọi subscription đi qua lambda đều cập nhật cùng một metric. `LongAdder` phù hợp cho bộ đếm thống kê có nhiều cập nhật đồng thời; nó tối ưu cho tranh chấp ghi và không cung cấp một snapshot giao dịch nhất quán với các thao tác khác. Nếu cần đọc/ghi giá trị chính xác theo một giao dịch hoặc cần compare-and-set, cân nhắc `AtomicLong` hoặc cơ chế đồng bộ phù hợp.

Với trạng thái theo khóa, có thể dùng cấu trúc concurrent:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.LongAdder;

ConcurrentHashMap<String, LongAdder> countsByTenant = new ConcurrentHashMap<>();

void record(String tenantId) {
    countsByTenant
        .computeIfAbsent(tenantId, ignored -> new LongAdder())
        .increment();
}
```

`ConcurrentHashMap` bảo vệ thao tác truy cập map đồng thời; `LongAdder` bảo vệ cập nhật bộ đếm theo tenant. Tuy nhiên, cấu trúc concurrent không tự giải quyết mọi quy tắc nghiệp vụ. Nếu cần giới hạn số tenant, xóa khóa cũ, cập nhật nhiều trường nguyên tử hoặc lưu trạng thái bền vững qua restart, cần thêm chính sách vòng đời và cơ chế lưu trữ phù hợp.

### Tránh capture mutable state ngoài ý muốn

Lambda trong pipeline thường được tạo một lần khi assembly và có thể được dùng lại cho nhiều subscription. Nếu lambda capture một collection hoặc counter mutable, đối tượng đó có thể trở thành trạng thái dùng chung dù người viết nghĩ mỗi subscriber có một pipeline riêng.

```java
import java.util.ArrayList;
import java.util.List;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

// State dùng chung vì được tạo bên ngoài publisher:
List<String> seen = new ArrayList<>();
Flux<String> unsafe = source.doOnNext(seen::add);

// State mới cho mỗi subscription:
Flux<List<String>> isolated = Flux.defer(() -> {
    List<String> localSeen = new ArrayList<>();
    return source
        .doOnNext(localSeen::add)
        .then(Mono.fromCallable(() -> List.copyOf(localSeen)));
});
```

Ví dụ đầu có thể gây race condition nếu nhiều subscription chạy đồng thời và cùng thêm vào `ArrayList`. Ví dụ sau tạo danh sách trong `defer`, nên mỗi subscription có một danh sách riêng. `then(...)` chỉ tạo kết quả sau khi nguồn hoàn tất; nếu nguồn vô hạn, kết quả này sẽ không được phát. Trong thực tế, nếu cần lưu mọi phần tử của nguồn vô hạn thì phải đặt giới hạn hoặc xử lý theo lô.

Không phải mọi mutable state đều sai. State mutable có thể phù hợp nếu có một chủ sở hữu rõ ràng, có đồng bộ phù hợp và vòng đời được giới hạn. Vấn đề nằm ở việc chia sẻ ngầm giữa nhiều subscription hoặc thread mà không có quy tắc bảo vệ.

## Chia sẻ một lần thực thi bằng share và publish

Một publisher cold thường thực hiện nguồn lại cho mỗi subscription. Nếu nhiều subscriber cần cùng nghe một luồng sự kiện đang phát, có thể chia sẻ subscription upstream:

```java
import reactor.core.publisher.Flux;

Flux<Event> sharedEvents = eventSource.events().share();

sharedEvents.subscribe(this::updateDashboard);
sharedEvents.subscribe(this::updateMetrics);
```

Các subscriber đang tham gia có thể cùng nhận tín hiệu từ một lần thực thi upstream. `share()` phù hợp cho luồng live khi nhiều bên cần quan sát cùng sự kiện. Nó không lưu lịch sử để phát lại các `onNext` đã trôi qua cho subscriber đến muộn. Khi không còn subscriber, nguồn upstream có thể bị hủy theo cơ chế ref-count; subscriber mới có thể tạo một lần kết nối mới tùy trạng thái nguồn.

`publish()` tạo `ConnectableFlux`, cho phép đăng ký subscriber trước rồi chủ động gọi `connect()` để bắt đầu nguồn. Cách này hữu ích khi cần bảo đảm nhiều bên nhận đã sẵn sàng trước khi phát dữ liệu. Kết nối trả về một `Disposable`, cần được quản lý nếu nguồn dài hạn.

## Cache chia sẻ kết quả và phát lại tín hiệu

`cache()` có ngữ nghĩa khác `share()`: nó lưu tín hiệu đã phát để subscriber đến sau có thể nhận lại. Với `Mono`, đây là cách phổ biến để chia sẻ một kết quả của lời gọi đắt đỏ trong một khoảng thời gian:

```java
import java.time.Duration;
import reactor.core.publisher.Mono;

Mono<ExchangeRate> sharedRate = Mono.defer(
        () -> exchangeClient.fetchRate("USD", "VND"))
    .cache(Duration.ofSeconds(30));
```

Các subscriber trong thời gian cache còn hiệu lực nhận cùng kết quả đã được tải; nguồn không cần gọi lại cho mỗi subscriber. Sau khi TTL hết, một subscription mới có thể khởi tạo lần tải mới. `Mono.cache()` cũng có thể lưu tín hiệu rỗng hoặc lỗi; cần xác định có muốn phát lại lỗi hay không và đặt retry trước hoặc sau cache theo mục tiêu.

Với `Flux`, cache có thể lưu các phần tử đã phát để phát lại cho subscriber mới. Nếu nguồn vô hạn, giữ toàn bộ lịch sử có thể làm bộ nhớ tăng liên tục. Hãy dùng cache có giới hạn/TTL phù hợp hoặc cơ chế chia sẻ live không replay nếu subscriber đến muộn không cần lịch sử.

| Cơ chế | Dùng chung upstream | Phát lại dữ liệu cũ | Vòng đời cần quản lý |
|---|---|---|---|
| `share()` | Các subscriber đang tham gia cùng dùng một nguồn | Không phát lại lịch sử `onNext` | Ref-count và cancellation của nguồn |
| `publish().connect()` | Nhiều subscriber dùng kết nối được điều khiển thủ công | Không tự replay | Handle `Disposable` của kết nối |
| `cache()` | Một lần thực thi được chia sẻ trong phạm vi cache | Có, theo tín hiệu đã cache | TTL, dung lượng và việc cache lỗi/empty |

## Phát sự kiện dùng chung bằng Sinks

Khi ứng dụng cần chủ động phát sự kiện đến nhiều subscriber, Reactor cung cấp `Sinks`. Một sink multicast có thể phát tín hiệu đến các subscriber đang đăng ký:

```java
import reactor.core.publisher.Sinks;

Sinks.Many<DomainEvent> eventBus = Sinks.many()
    .multicast()
    .onBackpressureBuffer();

eventBus.asFlux().subscribe(this::updateDashboard);
eventBus.asFlux().subscribe(this::updateAuditView);

Sinks.EmitResult result = eventBus.tryEmitNext(new DomainEvent("ORDER_CREATED"));
if (result.isFailure()) {
    logger.warn("Không phát được event: {}", result);
}
```

`asFlux()` cung cấp publisher cho subscriber. Với multicast sink, các subscriber hiện đang tham gia nhận sự kiện mới; sink không tự phát lại lịch sử cho subscriber đăng ký sau. `tryEmitNext` trả về `EmitResult`, vì vậy ứng dụng cần quyết định xử lý các trường hợp thất bại như không có subscriber, sink đã kết thúc hoặc có emission đồng thời không được tuần tự hóa.

Sinks có cơ chế phát hiện một số tình huống gọi đồng thời. Nếu nhiều thread có thể gọi `tryEmitNext`, hãy xử lý kết quả `FAIL_NON_SERIALIZED` bằng cách tuần tự hóa nguồn phát hoặc dùng API emission có handler retry phù hợp. Không bỏ qua `EmitResult`, vì điều đó có thể khiến ứng dụng âm thầm mất sự kiện.

`onBackpressureBuffer()` cho phép sink multicast đệm tín hiệu khi subscriber chưa yêu cầu đủ, nhưng buffer vẫn cần giới hạn và chính sách vận hành phù hợp. Không nên coi sink là message broker bền vững: dữ liệu trong bộ nhớ có thể mất khi tiến trình dừng và không thay thế cơ chế lưu trữ hoặc xác nhận message ở tầng hạ tầng.

Nếu cần phát lại một phần lịch sử cho subscriber mới, chọn loại replay sink với giới hạn rõ ràng, ví dụ `Sinks.many().replay().limit(100)`. Hãy xác định số phần tử giữ lại, thời gian lưu và phạm vi dữ liệu được phép chia sẻ.

## Context là dữ liệu theo subscriber, không phải biến toàn cục

Reactor `Context` cung cấp dữ liệu gắn với subscription, thường dùng cho request ID, thông tin xác thực, tenant, locale hoặc tracing. `Context` có tính bất biến: các toán tử tạo context mới thay vì sửa một map toàn cục. Mỗi subscriber có thể mang một context khác nhau qua cùng một publisher:

```java
import reactor.core.publisher.Mono;

Mono<String> requestInfo = Mono.deferContextual(context ->
    Mono.just("request=" + context.get("requestId"))
);

requestInfo
    .contextWrite(context -> context.put("requestId", "req-A"))
    .subscribe(System.out::println);

requestInfo
    .contextWrite(context -> context.put("requestId", "req-B"))
    .subscribe(System.out::println);
```

Hai subscription dùng cùng publisher nhưng nhận `requestId` khác nhau. `contextWrite` đặt dữ liệu trong context của subscriber; `deferContextual` đọc context ở phía upstream. Đây là lựa chọn phù hợp cho metadata theo request mà không cần capture biến mutable hoặc dựa vào `ThreadLocal`.

Context không phải kho trạng thái dùng chung. Không nên lưu một collection mutable vào Context rồi để nhiều nhánh sửa đổi đồng thời. Hãy dùng Context cho metadata bất biến theo subscription; dùng cấu trúc concurrent hoặc kho dữ liệu chuyên biệt cho trạng thái chia sẻ.

## Scheduler và trạng thái mutable

Một subscription có thể đi qua nhiều thread khi dùng `publishOn`, `subscribeOn` hoặc các publisher bất đồng bộ. Không nên giả định callback luôn chạy trên cùng một thread. Nếu trạng thái mutable được truy cập từ nhiều nhánh hoặc nhiều callback đồng thời, cần cơ chế bảo vệ phù hợp.

Ví dụ, `flatMap` có thể chạy nhiều publisher con đồng thời:

```java
Flux<Result> results = requests.flatMap(
    request -> remoteClient.fetch(request),
    8
);
```

Nếu mỗi nhánh chỉ tạo giá trị cục bộ và trả kết quả, việc kết hợp thường dễ kiểm soát. Nếu các nhánh cùng cập nhật một `ArrayList` hoặc `HashMap` được capture từ bên ngoài, có nguy cơ race condition. Dùng `collectList()` ở cuối nếu muốn thu kết quả của pipeline, hoặc dùng cấu trúc concurrent nếu thật sự cần chia sẻ cập nhật.

`publishOn` chuyển việc xử lý downstream sang worker được chọn; nó không tự làm một mutable object an toàn khi nhiều subscription truy cập. `Schedulers.parallel()` có thể chạy nhiều công việc trên nhiều worker, còn `boundedElastic` cô lập tác vụ blocking. Lựa chọn scheduler không thay thế việc thiết kế phạm vi sở hữu state.

`ThreadLocal` đặc biệt dễ gây lỗi trong reactive pipeline vì một subscription có thể tiếp tục trên thread khác và một thread có thể phục vụ nhiều subscription. Dùng Reactor Context hoặc cơ chế context propagation được tích hợp thay vì dựa vào giả định thread cố định.

## Kiểm thử trạng thái riêng và trạng thái chia sẻ

Có thể kiểm tra trạng thái theo subscription bằng cách subscribe nhiều lần và xác nhận mỗi lần bắt đầu từ giá trị riêng:

```java
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

Flux<Integer> perSubscription = Flux.defer(() -> {
    AtomicInteger counter = new AtomicInteger();
    return Flux.range(1, 3).map(ignored -> counter.incrementAndGet());
});

StepVerifier.create(perSubscription)
    .expectNext(1, 2, 3)
    .verifyComplete();

StepVerifier.create(perSubscription)
    .expectNext(1, 2, 3)
    .verifyComplete();
```

Mỗi lần `StepVerifier.create` tạo subscription mới; supplier trong `defer` tạo counter mới nên cả hai lần đều nhận `1, 2, 3`.

Ngược lại, kiểm thử trạng thái chia sẻ bằng một counter tạo ngoài publisher:

```java
import java.util.concurrent.atomic.AtomicInteger;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

AtomicInteger sharedCounter = new AtomicInteger();
Flux<Integer> sharedState = Flux.range(1, 2)
    .map(ignored -> sharedCounter.incrementAndGet());

StepVerifier.create(sharedState)
    .expectNext(1, 2)
    .verifyComplete();

StepVerifier.create(sharedState)
    .expectNext(3, 4)
    .verifyComplete();
```

Publisher nguồn vẫn cold và chạy lại cho mỗi subscription, nhưng lambda dùng chung `AtomicInteger` ở ngoài. Kiểm thử xác nhận trạng thái capture có vòng đời dài hơn từng subscription. Trong kiểm thử đa luồng, cần kiểm tra thêm tính an toàn đồng thời thay vì chỉ kiểm tra chuỗi giá trị tuần tự.

## Chọn mô hình state theo yêu cầu nghiệp vụ

| Yêu cầu | Cách tổ chức phù hợp | Lưu ý |
|---|---|---|
| Mỗi request có bộ đếm hoặc accumulator riêng | Tạo trong `defer`, `generate` state supplier hoặc `scanWith` | Không capture mutable state từ assembly |
| Mỗi subscription sở hữu cursor hoặc tài nguyên riêng | Tạo trong `using`/`usingWhen` hoặc state supplier và cleanup khi kết thúc | Bao phủ complete, error và cancel |
| Metric toàn tiến trình | `LongAdder` hoặc metric registry dùng chung | Tránh dùng metric làm nguồn sự thật nghiệp vụ |
| Cache dữ liệu dùng chung | Cache có khóa, TTL và giới hạn dung lượng | Phân vùng theo tenant/người dùng nếu dữ liệu phụ thuộc ngữ cảnh |
| Nhiều subscriber nghe cùng luồng live | `share`, `publish` hoặc `Sinks.Many` | Xác định subscriber đến muộn và vòng đời kết nối |
| Subscriber cần nhận lại kết quả đã có | `Mono.cache`, replay sink hoặc cache chuyên biệt | Giới hạn TTL/lịch sử và xử lý lỗi được cache |
| Metadata theo request | Reactor `Context` | Dùng giá trị bất biến, không coi là global mutable state |

## Những lỗi thường gặp

- **Tạo counter ngoài `defer` nhưng mong mỗi subscriber có counter riêng:** lambda capture cùng một đối tượng qua mọi subscription.
- **Dùng `Mono.just(methodCall())` để trì hoãn lời gọi:** Java thực hiện lời gọi ngay khi dựng publisher; dùng `fromCallable` hoặc `defer` nếu cần lazy evaluation.
- **Dùng seed mutable chung trong phép tích lũy:** nhiều subscription có thể sửa cùng đối tượng; dùng supplier như `scanWith` hoặc `reduceWith` để tạo seed riêng.
- **Cho rằng `share()` phát lại sự kiện cũ:** chia sẻ live không đồng nghĩa replay; subscriber đến muộn có thể bỏ lỡ tín hiệu đã phát.
- **Dùng `cache()` không giới hạn cho luồng dài hạn:** lịch sử và tín hiệu có thể giữ bộ nhớ lâu hơn dự kiến.
- **Coi `AtomicInteger` giải quyết mọi vấn đề chia sẻ state:** atomic bảo vệ một số thao tác trên biến, nhưng không tạo tính nguyên tử cho nhiều trường hoặc toàn bộ quy tắc nghiệp vụ.
- **Dùng `ThreadLocal` trong pipeline có scheduler:** thread có thể thay đổi giữa các bước; dùng Reactor Context cho metadata theo subscription.
- **Không cleanup state gắn với tài nguyên:** cancellation hoặc lỗi có thể để lại listener, cursor hoặc kết nối nếu nguồn không gắn cleanup với vòng đời subscription.
- **Dùng một `BaseSubscriber` hoặc stateful subscriber cho nhiều subscription:** trạng thái nội bộ và handle subscription có thể bị ghi đè; tạo instance riêng cho từng lần đăng ký.

## Quy trình thiết kế trạng thái reactive

Trước khi thêm một biến hoặc accumulator vào pipeline, hãy xác định ai sở hữu nó và nó sống bao lâu. Nếu dữ liệu chỉ thuộc một lần đăng ký, tạo nó trong `defer`, state supplier của `generate`, `scanWith` hoặc `using`. Nếu dữ liệu cần được chia sẻ, chọn cấu trúc thread-safe, quy tắc phân vùng, thời hạn lưu và cách xử lý khi nhiều subscriber cập nhật cùng lúc.

Tiếp theo, xác định liệu các subscriber cần chạy nguồn riêng, cùng nghe một luồng live hay nhận lại kết quả đã có. Dùng publisher cold cho thực thi độc lập; dùng `share`/`publish` để chia sẻ tín hiệu đang phát; dùng `cache` hoặc replay khi cần lưu và phát lại; dùng `Context` cho metadata riêng theo subscriber. Cuối cùng, kiểm thử nhiều subscription, cancellation, lỗi và truy cập đồng thời để xác nhận phạm vi trạng thái đúng với nghiệp vụ.

Quản lý rõ trạng thái riêng và trạng thái dùng chung giúp pipeline Reactor tránh rò rỉ dữ liệu giữa request, hạn chế race condition và kiểm soát vòng đời tài nguyên. Đây là nền tảng để ứng dụng reactive xử lý nhiều subscription đồng thời mà vẫn giữ dữ liệu nhất quán và hành vi có thể dự đoán.
