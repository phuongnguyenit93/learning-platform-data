# Kiểm thử demand, backpressure và cancellation trong Reactive Streams và Project Reactor

## 1. Mục tiêu học tập

Một luồng reactive có thể trả đúng dữ liệu trong `StepVerifier.expectNext(...)` nhưng vẫn sai ở những vấn đề quan trọng: phát quá số phần tử mà subscriber yêu cầu, prefetch/buffering không phù hợp, không hủy nguồn khi client rời đi hoặc tiếp tục tiêu tốn tài nguyên sau `cancel`. Đây là lý do **kiểm thử demand, backpressure và cancellation** phải xem xét cả **dữ liệu** lẫn **vòng đời subscription**.

Bài học tập trung vào Reactive Streams và Project Reactor (thư viện thường dùng trong Spring WebFlux):

- Hiểu `Subscription.request(n)`, demand tồn đọng, `Long.MAX_VALUE` và `Subscription.cancel()`.
- Phân biệt demand ở **downstream** với số yêu cầu mà operator gửi tới **upstream**; không giả định chúng giống nhau.
- Dùng `StepVerifier.create(publisher, 0)`, `thenRequest(n)`, `expectNext` và `thenCancel()` để tái hiện subscriber điều khiển demand.
- Dùng `doOnRequest`, `doOnCancel`, `doFinally` để quan sát chính xác các signal.
- Kiểm tra request reshaping qua `buffer`, `limitRate`, `flatMap`/`publishOn` và `take`.
- Dùng `TestPublisher` để chủ động phát các signal và assert số request/cancellation; dùng `PublisherProbe` để theo dõi subscription, request, cancel của một nhánh.
- Phân biệt **complete**, **error**, **cancel**, **dispose**, **timeout**, **discard** và giải phóng resource.
- Biết giới hạn của `WebTestClient`: HTTP response PASS không tự chứng minh backpressure theo từng item ở tầng service/Publisher.
- Có ví dụ Maven **Java 17, Spring Boot 3.5.16, Reactor 3.7.x, JUnit Jupiter** gồm unit tests cho Publisher và WebFlux slice test.

**Trọng tâm:** Bài kiểm thử đúng không chỉ hỏi “publisher phát ra giá trị nào?” mà còn hỏi “khi chưa có demand thì điều gì xảy ra?”, “operator đã yêu cầu upstream bao nhiêu?” và “sau cancellation thì tài nguyên/đăng ký còn tồn tại không?”.

## 2. Reactive Streams: ba loại signal và hai lệnh điều khiển

### 2.1. Mô hình Publisher–Subscriber

Một `Publisher<T>` cung cấp một luồng signal cho `Subscriber<T>`. Sau `subscribe`, Publisher cung cấp `Subscription` qua `onSubscribe`. Subscriber dùng subscription để điều khiển:

```text
Publisher<T>                         Subscriber<T>
     |                                      |
     |  onSubscribe(Subscription) --------> |
     |                                      |
     | <-------------------------- request(2)
     |                                      |
     |                 onNext(item1) -----> |
     |                 onNext(item2) -----> |
     |                                      |
     | <-------------------------- request(1)
     |                 onNext(item3) -----> |
     |                                      |
     | <------------------------------- cancel()
     |                                      |
     |       không phát signal tiếp cho subscriber sau cancel
```

Ba signal chính từ publisher là `onNext(T)`, `onError(Throwable)` và `onComplete()`. `onError`/`onComplete` là terminal signals **loại trừ nhau**; không phải luồng nào cũng kết thúc nếu không bị hủy. `cancel()` là yêu cầu điều khiển gửi **từ subscriber lên subscription**, không phải một `onComplete` đặc biệt.

### 2.2. Demand là gì?

`Subscription.request(n)` với `n > 0` cấp thêm quyền phát tối đa `n` giá trị `onNext`. Demand cộng dồn và được trừ khi `onNext` được phát; khi tổng tăng quá giới hạn kiểu số nguyên lớn, implementation thường dùng **saturating arithmetic** tới `Long.MAX_VALUE` (nghĩa là demand không giới hạn).

Ví dụ subscriber có:
- Ban đầu `request(2)` → có quyền nhận tối đa hai `onNext`.
- Đã nhận một → demand chưa sử dụng còn một.
- Gửi thêm `request(3)` → demand còn bốn.
- Sau khi nhận bốn phần tử nữa → demand còn không.
- `request(Long.MAX_VALUE)` → có thể hiểu là **unbounded**; downstream không thực hiện flow control theo từng item.

`request(0)` và `request(-1)` **vi phạm quy tắc** Reactive Streams. Đừng viết test “request âm để xem kết quả business” rồi coi đó là usage bình thường. `StepVerifier.create(publisher, 0)` hợp lệ vì nó thiết lập **initial request = 0, chưa gửi request(0)**. Đây là cách kiểm rằng publisher không tự phát `onNext` trước khi có demand.

### 2.3. Cancellation có ý nghĩa gì?

`Subscription.cancel()` thông báo subscriber không còn muốn dữ liệu. Publisher/operator cần dừng công việc liên quan và giải phóng nguồn theo hợp đồng. Cancellation:
- Không phải `onComplete` và không phải `onError`.
- Có thể bị trì hoãn/race với signal đang chạy trên thread khác; không mặc định tức thời tại mọi external boundary.
- Không tự “rollback” database commit, HTTP call đã gửi hoặc side effect đã hoàn tất.
- Cần cleanup tài nguyên như file handle, scheduled task, socket, consumer registration, queue buffer theo từng implementation.
- Có thể phát sinh khi người dùng hủy HTTP streaming response, `take(n)` đã đủ phần tử, timeout operator, hoặc test chủ động `thenCancel()`.

### 2.4. Bảng ba trạng thái kết thúc

| Trạng thái | Ai khởi phát? | Signal hướng xuống | `doFinally` nhận |
| --- | --- | --- | --- |
| Complete | Publisher phát hết dữ liệu hợp lệ | `onComplete` | `SignalType.ON_COMPLETE` |
| Error | Publisher/operator phát lỗi | `onError` | `SignalType.ON_ERROR` |
| Cancel | Subscriber/operator không cần tiếp | Không có terminal signal bắt buộc gửi xuống | `SignalType.CANCEL` ở vị trí operator quan sát thấy cancel |

Có thể kiểm `doOnCancel` để assert cancel event rõ ràng, `doFinally` để phân biệt ba loại termination/cancellation. `doFinally` nằm ở vị trí nào trong pipeline sẽ quyết định signal nó quan sát; không mặc nhiên mọi `doFinally` trong mọi nhánh đều thấy cùng một kết quả.

## 3. Vì sao một test chỉ expectNext là chưa đủ?

```java
StepVerifier.create(Flux.range(1, 3))
        .expectNext(1, 2, 3)
        .verifyComplete();
```

Đây là một **unit test giá trị** rất hữu ích. Nhưng `StepVerifier.create(publisher)` theo mặc định yêu cầu **unbounded demand** (`Long.MAX_VALUE`). Vì vậy nó **không kiểm**:
- Nguồn có chờ `request(1)` trước khi phát item hay không.
- Khi subscriber chỉ yêu cầu hai item, nguồn có phát tới item thứ ba hay không.
- Một operator có đẩy 256 upstream requests do prefetch hay không.
- Subscription có thực hiện `cancel`/cleanup khi downstream rời đi không.

Để kiểm backpressure, phải **đặt demand hữu hạn/ban đầu bằng 0**, dùng `thenRequest(n)` và theo dõi các side effects của request/cancel ở đúng vị trí pipeline. Để kiểm cancellation, phải kết thúc scenario bằng `thenCancel()` rồi assert rằng source quan sát cancel.

## 4. StepVerifier: viết kịch bản demand theo từng bước

### 4.1. Kiểm ban đầu không có demand

```java
AtomicInteger observed = new AtomicInteger();

Flux<Integer> source = Flux.range(1, 3)
        .doOnNext(value -> observed.incrementAndGet());

StepVerifier.create(source, 0)
        .expectSubscription()
        .then(() -> assertThat(observed.get()).isZero())
        .thenRequest(1)
        .expectNext(1)
        .then(() -> assertThat(observed.get()).isEqualTo(1))
        .thenCancel()
        .verify(Duration.ofSeconds(2));
```

Đoạn trên là code **bên trong JUnit test method**, cần imports Reactor, AssertJ, `AtomicInteger` và `Duration`. Với `Flux.range` đồng bộ, lần kiểm `observed=0` xảy ra sau subscription nhưng trước khi có request. Sau `thenRequest(1)`, chỉ một item được chuyển tới downstream. `thenCancel()` kết thúc scenario bằng cancel thay vì đòi `onComplete`.

Cần hiểu rằng `expectSubscription()` chờ signal đăng ký, không tạo demand. `thenRequest(1)` là hành động **thực sự phát request** từ subscriber test.

### 4.2. Phát demand theo hai lượt

```java
StepVerifier.create(Flux.range(1, 5), 0)
        .expectSubscription()
        .thenRequest(2)
        .expectNext(1, 2)
        .thenRequest(3)
        .expectNext(3, 4, 5)
        .verifyComplete();
```

Trong scenario này, đã nhận đủ năm phần tử nên publisher có thể `onComplete`. Nếu chỉ request 2 rồi `expectNext(1,2,3)`, verifier có cơ chế phát hiện kỳ vọng vượt quá demand được cấp; đó không phải cách hợp lệ để kiểm nguồn “phát thêm” vì **verifier đã cấu hình không cho nhận item thứ ba**.

### 4.3. So sánh initialRequest và StepVerifierOptions

Hai cách gần tương đương để bắt đầu không có demand:

```java
StepVerifier.create(source, 0);
```

```java
StepVerifier.create(
        source,
        StepVerifierOptions.create()
                .initialRequest(0)
                .scenarioName("bounded-demand"));
```

Với `StepVerifierOptions`, bạn còn có thể ghi `scenarioName` để thông báo lỗi rõ hơn và cấu hình `checkUnderRequesting(true)` (mặc định bật). Tên scenario giúp debug, không sửa hành vi publisher.

**Đừng** đặt `checkUnderRequesting(false)` chỉ để test đang đòi nhiều phần tử hơn demand không báo lỗi: làm như vậy che lỗi thiết kế test, không chữa upstream backpressure.

### 4.4. Luôn có lệnh verify cuối cùng

`thenCancel()`, `expectComplete()` hoặc `expectError()` chỉ khai báo cách kết thúc kịch bản. Bạn vẫn cần gọi `verify()` hoặc shortcut như `verifyComplete()` / `verifyError()`. Nếu không, chưa có subscription/test thực thi.

Nên đặt timeout:

```java
StepVerifier.create(source, 0)
        .expectSubscription()
        .thenRequest(1)
        .expectNext(1)
        .thenCancel()
        .verify(Duration.ofSeconds(2));
```

Không có timeout, một số kịch bản có thể chờ vô hạn khi publisher không phát signal hoặc bài test quên cấp demand. Timeout phải dựa vào đặc điểm unit test; đây không phải SLA production.

## 5. Dùng doOnRequest đúng vị trí để quan sát demand upstream

### 5.1. doOnRequest là instrumentation, không phải cầu nối ép request

```java
List<Long> requests = new CopyOnWriteArrayList<>();

Flux<Integer> source = Flux.range(1, 5)
        .doOnRequest(requests::add);

StepVerifier.create(source, 0)
        .expectSubscription()
        .thenRequest(2)
        .expectNext(1, 2)
        .thenRequest(3)
        .expectNext(3, 4, 5)
        .verifyComplete();

assertThat(requests).containsExactly(2L, 3L);
```

`doOnRequest` nhận số lượng của **từng lần yêu cầu** đi qua vị trí operator. Với pipeline đơn giản như trên, các lượt 2/3 được chuyển trực tiếp đến range source. Nhưng với `buffer`, `flatMap`, `publishOn`, `limitRate`, giá trị quan sát **upstream** có thể khác `thenRequest(...)` ở cuối chuỗi.

### 5.2. Hai vị trí doOnRequest cho hai câu trả lời

```java
Flux<List<Integer>> pipeline = Flux.range(1, 12)
        .doOnRequest(n -> System.out.println("SOURCE demand=" + n))
        .buffer(3)
        .doOnRequest(n -> System.out.println("DOWNSTREAM demand=" + n));
```

Đoạn này minh họa luồng được khai báo; output phụ thuộc subscriber và số request thực. Khi downstream yêu cầu **hai buffers**, operator `buffer(3)` phải yêu cầu đủ **sáu items** để tạo hai buffers đầy đủ. `doOnRequest` nằm **sau buffer** thấy demand theo đơn vị **list/buffer**, còn cái nằm **trước buffer** thấy demand theo đơn vị item.

Không thể suy luận từ `doOnRequest(6)` rằng subscriber ứng dụng cũng đã gọi `request(6)`; nó có thể chỉ yêu cầu hai buffers.

### 5.3. Cold, hot và replay làm phép kiểm khác nhau

| Nguồn | Hành vi thường gặp | Chú ý khi test demand |
| --- | --- | --- |
| `Flux.range`, `Flux.fromIterable` | Cold, đáp ứng request tuần tự | Tốt để kiểm hợp đồng request deterministically |
| `Flux.generate` | Cold, tạo từng phần tử theo demand | Phù hợp khi thiết kế producer tự phát có kiểm soát |
| `Flux.create` | Bridge callback có thể nhận events từ hệ ngoài | Cần chọn overflow strategy, resource cleanup |
| `Sinks.Many` | Có thể hot, multicast/replay/buffer tùy flavor | Hot producer có thể phát độc lập nhu cầu của một subscriber |
| `Flux.interval` | Thời gian/scheduler quyết định tick | Không có demand ở tick có thể gây overflow/error |
| `share`, `publish`, `replay` | Thay đổi subscription, caching, multicasting | Không giả định mỗi test là subscriber duy nhất |

Với hot sources, “publisher nhận onNext trước demand” có thể có nhiều ý nghĩa: một sink đúng contract có thể **buffer/drop/error** thay vì chuyển `onNext` trái phép cho subscriber. Luôn phân biệt **nguồn nhận event**, **operator lưu/loại event**, và **subscriber nhận onNext**.

## 6. Backpressure: request được biến đổi bởi operators

### 6.1. buffer(n) đổi đơn vị demand

Giả sử:

```java
Flux<List<Integer>> batches =
        Flux.range(1, 8).buffer(2);
```

Khi subscriber `request(2)` trên `batches`, nhu cầu là **hai List**; upstream có thể nhận `request(4)` cho bốn số nguyên để đóng gói. Vì vậy test phải assert đúng **đơn vị** ở mỗi phía pipeline.

### 6.2. limitRate không phải throttle theo thời gian

`limitRate(highTide)` chia request lớn từ downstream thành các batch nhỏ hơn để gửi upstream. `limitRate(highTide, lowTide)` cho phép điều chỉnh replenishment; `lowTide=0` dùng các batch theo ngưỡng highTide thay vì nạp sớm.

```java
Flux<Integer> source = Flux.range(1, 8)
        .limitRate(2, 0);
```

Nếu downstream yêu cầu tám giá trị, upstream được yêu cầu theo các đợt giới hạn thay vì một `request(8)`. Đây là **demand shaping**, **không** phải đảm bảo “2 events/giây”; muốn giới hạn theo thời gian cần cơ chế rate limiting/scheduling riêng.

### 6.3. flatMap, publishOn và prefetch

Một số operators có `prefetch` hoặc nhu cầu tạo trước nhiều inner sequences. `flatMap` có thể yêu cầu upstream và inner publishers nhiều hơn demand cuối tại một thời điểm; `publishOn` có thể prefetch vào queue. Hầu hết điều này hợp lệ nếu output đưa tới subscriber vẫn tuân thủ demand.

Khi test request ở một vị trí upstream:
- Xem chính xác thứ tự các operators.
- Biết prefetch/concurrency/lowTide đã cấu hình.
- Đừng assert `upstream request == downstream request` nếu có operator reshaping.
- Tránh hard-code một số prefetch mặc định có thể được thay đổi giữa Reactor versions; đặt prefetch rõ ràng khi behavior đó là contract.

### 6.4. take(n) và cancellation

`take(n)` phát tối đa n items và có thể hủy upstream khi đủ n, rồi hoàn tất downstream. Trong Reactor 3.7, `take(n)` mặc định giới hạn tổng request upstream tới n; `take(n,false)` có chế độ **unbounded upstream request** và cancel khi đã nhận đủ n.

Cả hai đều có thể trả cùng các item cho downstream nhưng **chi phí upstream** khác nhau. Đặc biệt với API hoặc broker có side effect khi sản xuất event, việc upstream được yêu cầu vô hạn có thể gây nhiều công việc thừa trước cancellation.

### 6.5. onBackpressureBuffer/drop/latest/error

Các operator có mục tiêu khác nhau:

| Operator | Khi upstream phát nhanh hơn downstream | Đánh đổi chính |
| --- | --- | --- |
| `onBackpressureBuffer` | Lưu tạm giá trị vào buffer | Tiêu thụ memory; dùng giới hạn có ý nghĩa |
| `onBackpressureDrop` | Bỏ các phần tử chưa thể chuyển xuống | Mất dữ liệu; có thể cần metric/callback |
| `onBackpressureLatest` | Giữ giá trị mới nhất và bỏ giá trị cũ chờ phát | Mất các trạng thái trung gian |
| `onBackpressureError` | Báo lỗi thay vì đệm/bỏ lặng lẽ | Fail-fast, consumer phải xử lý |
| `limitRate` | Định hình lượng request đi upstream | Không giải quyết mọi hot producer không tôn trọng request |
| `take(n)` | Giới hạn số phần tử cần và kết thúc sớm | Thường cancel upstream khi đủ n |

Phải hiểu semantics theo nguồn. Với **cold, demand-aware source** như `Flux.range`, downstream request0 thường khiến nguồn **chưa phát phần tử**, nên drop strategy không có gì để drop. Để kiểm overflow/drop thật, dùng một **hot source** hoặc `TestPublisher` mô phỏng producer không tôn trọng demand, đồng thời khống chế timing và giới hạn bộ nhớ.

**Không** giả định “đã dùng onBackpressureBuffer thì production an toàn”: buffer không giới hạn có thể gây áp lực memory nếu upstream luôn nhanh hơn. Bounded buffer/overflow callbacks và metrics cần được kiểm trong context vận hành.

## 7. TestPublisher và PublisherProbe: chủ động điều khiển nguồn

### 7.1. TestPublisher tạo signal theo ý test

`TestPublisher<T>` thuộc `reactor-test`. Nó giúp test tự phát `next`, `complete`, `error`, đồng thời assert trạng thái subscription và demand:

```java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(source.flux(), 0)
        .expectSubscription()
        .then(() -> source.assertSubscribers(1))
        .thenRequest(2)
        .then(() -> source.assertMinRequested(2))
        .then(() -> source.next(11, 12))
        .expectNext(11, 12)
        .thenCancel()
        .verify(Duration.ofSeconds(2));

source.assertCancelled();
```

Đoạn trên sẽ có file hoàn chỉnh ở mục 9. `TestPublisher.create()` thông thường là nguồn **hot, điều khiển bằng test**, không giống `Flux.range` tự phát khi được request. Bạn phải gọi `source.next(...)` trong `then(...)` nếu muốn phát data tại bước đó.

`assertMinRequested`/`assertMaxRequested` nhìn demand theo semantics của TestPublisher tại thời điểm assert; nên assert **trước khi phát hết giá trị**, vì outstanding demand có thể đã bị trừ. Với nhiều subscribers, cần hiểu aggregate/maximum/minimum, không so giản đơn một số duy nhất.

### 7.2. TestPublisher không tự là một nguồn production-like

`TestPublisher.createNoncompliant(TestPublisher.Violation.REQUEST_OVERFLOW)` cho phép mô phỏng Publisher vi phạm demand. Hữu ích để kiểm operator chịu lỗi/đường overflow, **nhưng là phép kiểm resilience với nguồn cố ý sai**, không phải ví dụ chuẩn của Reactive Streams.

Các violation như `ALLOW_NULL` hoặc `DEFER_CANCELLATION` có nghĩa riêng; không bật chúng bừa bãi chỉ để một test xanh. Khi dùng noncompliant publishers, phải chỉ rõ **lỗi của source** hay **hành vi kỳ vọng của operator** đang được kiểm, và xác nhận signal/drop hooks theo phiên bản Reactor.

### 7.3. PublisherProbe quan sát luồng không cần phát dữ liệu thủ công

`PublisherProbe<T>` hữu ích khi muốn biết một nhánh đã được:
- Subscribe chưa?
- Request chưa?
- Cancel chưa?

```java
PublisherProbe<Integer> probe =
        PublisherProbe.of(Flux.range(1, 100));

StepVerifier.create(probe.flux(), 0)
        .expectSubscription()
        .thenRequest(2)
        .expectNext(1, 2)
        .thenCancel()
        .verify(Duration.ofSeconds(2));

probe.assertWasSubscribed();
probe.assertWasRequested();
probe.assertWasCancelled();
```

Không có `onComplete` được yêu cầu; subscriber cố ý cancel sau hai giá trị. `PublisherProbe` phù hợp để kiểm nhánh fallback, cancellation và path execution mà không cần viết biến `AtomicBoolean` ở nhiều vị trí.

### 7.4. TestPublisher và PublisherProbe khác nhau

| Tình huống | Chọn | Vì sao |
| --- | --- | --- |
| Cần tự đẩy next/error/complete vào pipeline | `TestPublisher` | Chủ động điều khiển signal |
| Cần assert minimum request / overflow | `TestPublisher` | Có API kiểm requested/subscriber state |
| Chỉ muốn biết fallback được subscribe/request/cancel | `PublisherProbe` | Nhẹ, tập trung vào đường đi |
| Cần kiểm cancel khi subscriber dừng một Flux thật | `PublisherProbe.of(source)` hoặc `doOnCancel` | Gắn với source thật |
| Cần chứng minh business output | `StepVerifier` | Kiểm onNext/onError/onComplete |
| Cần kiểm cả output và lifecycle | `StepVerifier + Probe` | Thấy data và control |

Một mình `verifyComplete()` không chứng minh fallback đã chạy; một mình `assertWasSubscribed()` không chứng minh output đúng. Nên kết hợp khi contract đòi cả hai.

## 8. Cancellation, doFinally và cleanup

### 8.1. Chủ động cancel bằng StepVerifier

```java
AtomicBoolean cancelled = new AtomicBoolean();

Flux<Integer> values = Flux.range(1, 100)
        .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(values, 0)
        .expectSubscription()
        .thenRequest(3)
        .expectNext(1, 2, 3)
        .thenCancel()
        .verify(Duration.ofSeconds(2));

assertThat(cancelled.get()).isTrue();
```

Trong ví dụ đồng bộ, lệnh `thenCancel` phát cancel đi upstream và callback của `doOnCancel` được chạy. Với async/external producer, có thể cần chờ cleanup được báo theo cách đồng bộ, không assert ngay từ thread khác khi cleanup bất đồng bộ còn đang diễn ra.

### 8.2. doFinally phân biệt ba lý do kết thúc

```java
AtomicReference<SignalType> finalSignal = new AtomicReference<>();

Flux<Integer> source = Flux.range(1, 100)
        .doFinally(finalSignal::set);
```

Nếu `thenCancel` sau vài giá trị, `finalSignal` tại vị trí đó phải quan sát `SignalType.CANCEL`. Nếu publisher phát hết thì `ON_COMPLETE`; nếu phát lỗi thì `ON_ERROR`. Không đồng nhất terminal signal đi downstream với cancellation: `cancel` không gọi `onComplete` cho subscriber.

### 8.3. Dọn tài nguyên với Flux.using

```java
AtomicBoolean closed = new AtomicBoolean();

Flux<Integer> values = Flux.using(
        Object::new,
        handle -> Flux.range(1, 100),
        handle -> closed.set(true));

StepVerifier.create(values, 0)
        .expectSubscription()
        .thenRequest(1)
        .expectNext(1)
        .thenCancel()
        .verify(Duration.ofSeconds(2));

assertThat(closed.get()).isTrue();
```

Ví dụ đơn giản dùng một object resource; thực tế có thể là file handle/connection/stream. `Flux.using` liên kết lifecycle với subscription và cleanup khi complete/error/cancel theo cấu hình. Với resource bất đồng bộ, dùng `usingWhen` với cleanup publishers được thiết kế rõ; không tự gọi `close` trong `map` vì error/cancel dễ bỏ sót.

### 8.4. Cancellation của WebFlux HTTP không đồng nghĩa dừng mọi side effect

Khi client rời khỏi SSE/NDJSON streaming endpoint, Reactor Netty/WebFlux có thể cancel subscription liên quan. Nhưng:
- Network disconnect detection có thể có độ trễ.
- External HTTP request hoặc JDBC blocking call đã khởi phát có thể không thể “rút lại”.
- Một source hot/shared có thể tiếp tục phát cho subscribers khác.
- `doOnCancel` đặt sau/before `share` sẽ quan sát các signal khác nhau.
- Transaction commit, phát message hoặc thanh toán đã xong không tự rollback khi subscriber cancel.

Do đó kiểm cancellation ở **Publisher boundary** bằng `StepVerifier`/`PublisherProbe`, còn việc server phát hiện disconnect và giải phóng resources cần **integration test** có kiểm soát và instrumentation phù hợp.

## 9. Dự án Maven hoàn chỉnh: Java 17 + Spring Boot 3.5.16

Demo chia hai lớp mục tiêu:
1. Unit tests Reactor kiểm demand/backpressure/cancellation **không cần Spring context**.
2. WebFlux slice test kiểm controller dùng reactive service và JSON response — **không thay thế unit tests demand**.

### 9.1. Cây thư mục

```text
reactive-demand-lab/
├── pom.xml
├── src/main/java/com/example/reactivelab/
│   ├── ReactiveDemandApplication.java
│   ├── EventView.java
│   ├── StreamService.java
│   └── StreamController.java
└── src/test/java/com/example/reactivelab/
    ├── DemandContractTest.java
    ├── BackpressureOperatorsTest.java
    ├── CancellationContractTest.java
    ├── TestPublisherProbeTest.java
    └── StreamControllerWebFluxTest.java
```

Tất cả Java files dùng package `com.example.reactivelab`. Không có database, broker hoặc external service. Phần unit tests không dùng `@SpringBootTest` vì không cần nạp container để kiểm Reactive Streams semantics.

### 9.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>reactive-demand-lab</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
```

`reactor-test` khai báo rõ ở test scope, không phụ thuộc giả định rằng một starter nào đó luôn kéo theo. Spring Boot BOM quản lý phiên bản. `spring-boot-starter-webflux` mang Reactor Core/WebFlux và runtime Netty; `spring-boot-starter-test` mang JUnit Jupiter, AssertJ, Mockito, Spring Test.

### 9.3. ReactiveDemandApplication.java

`src/main/java/com/example/reactivelab/ReactiveDemandApplication.java`:

```java
package com.example.reactivelab;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ReactiveDemandApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReactiveDemandApplication.class, args);
    }
}
```

### 9.4. EventView.java

`src/main/java/com/example/reactivelab/EventView.java`:

```java
package com.example.reactivelab;

public record EventView(int id, String name) {}
```

Java record có structural equality mặc định; khi dùng `StepVerifier.expectNext(new EventView(...))`, phép so sánh dựa trên hai thành phần `id` và `name`.

### 9.5. StreamService.java

`src/main/java/com/example/reactivelab/StreamService.java`:

```java
package com.example.reactivelab;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class StreamService {

    public Flux<EventView> events(int count) {
        if (count < 1 || count > 100) {
            return Flux.error(
                    new IllegalArgumentException("count must be 1..100"));
        }
        return Flux.range(1, count)
                .map(i -> new EventView(i, "event-" + i));
    }

    public Flux<Integer> integers(int count) {
        if (count < 0 || count > 100) {
            return Flux.error(
                    new IllegalArgumentException("count must be 0..100"));
        }
        return Flux.range(1, count);
    }
}
```

`Flux.range` là cold demand-aware source. Với count = 0 ở `integers`, Reactor tạo Flux rỗng; `events` cố ý yêu cầu ít nhất 1 vì ví dụ HTTP cần một số bản ghi có giới hạn. Lỗi được đại diện bằng `Flux.error` **khi subscription**, không bị ném đồng bộ ngay khi gọi method.

### 9.6. StreamController.java

`src/main/java/com/example/reactivelab/StreamController.java`:

```java
package com.example.reactivelab;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
@RequestMapping("/streams")
public class StreamController {
    private final StreamService service;

    public StreamController(StreamService service) {
        this.service = service;
    }

    @GetMapping(produces = MediaType.APPLICATION_JSON_VALUE)
    public Flux<EventView> list(
            @RequestParam(defaultValue = "3") int count) {
        return service.events(count);
    }
}
```

Endpoint `GET /streams?count=3` trả JSON array có ba EventView. Dùng `application/json` khiến WebFlux serialize finite `Flux` thành JSON array, có thể buffer/aggregate theo codec; không coi số item client đọc từ JSON array là số lần `Subscription.request(n)` ở tầng service. Đó là lý do unit demand tests nằm riêng.

### 9.7. DemandContractTest.java

`src/test/java/com/example/reactivelab/DemandContractTest.java`:

```java
package com.example.reactivelab;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class DemandContractTest {

    @Test
    void emitsNothingUntilFirstDemand() {
        AtomicInteger emitted = new AtomicInteger();
        Flux<Integer> source = Flux.range(1, 4)
                .doOnNext(n -> emitted.incrementAndGet());

        StepVerifier.create(source, 0)
                .expectSubscription()
                .then(() -> assertThat(emitted.get()).isZero())
                .thenRequest(1)
                .expectNext(1)
                .then(() -> assertThat(emitted.get()).isEqualTo(1))
                .thenCancel()
                .verify(Duration.ofSeconds(2));
    }

    @Test
    void fulfillsDemandInTwoBatches() {
        List<Long> requests = new CopyOnWriteArrayList<>();
        Flux<Integer> source = Flux.range(1, 5)
                .doOnRequest(requests::add);

        StepVerifier.create(source, 0)
                .expectSubscription()
                .thenRequest(2)
                .expectNext(1, 2)
                .thenRequest(3)
                .expectNext(3, 4, 5)
                .verifyComplete();

        assertThat(requests).containsExactly(2L, 3L);
    }

    @Test
    void serviceEmitsRecordsUsingBoundedRequest() {
        StreamService service = new StreamService();

        StepVerifier.create(service.events(4), 0)
                .expectSubscription()
                .thenRequest(2)
                .expectNext(
                        new EventView(1, "event-1"),
                        new EventView(2, "event-2"))
                .thenRequest(2)
                .expectNext(
                        new EventView(3, "event-3"),
                        new EventView(4, "event-4"))
                .verifyComplete();
    }

    @Test
    void baseSubscriberCanRequestOneByOneThenCancel() {
        List<Integer> seen = new CopyOnWriteArrayList<>();
        AtomicInteger cancels = new AtomicInteger();

        Flux<Integer> source = Flux.range(1, 20)
                .doOnCancel(cancels::incrementAndGet);

        BaseSubscriber<Integer> subscriber = new BaseSubscriber<>() {
            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                request(1);
            }

            @Override
            protected void hookOnNext(Integer value) {
                seen.add(value);
                if (value == 3) {
                    cancel();
                } else {
                    request(1);
                }
            }
        };

        source.subscribe(subscriber);

        assertThat(seen).containsExactly(1, 2, 3);
        assertThat(cancels.get()).isEqualTo(1);
    }
}
```

**Điểm kiểm được:**
- `initialRequest=0` không phải `request(0)` trái protocol.
- `thenRequest(2)` và `thenRequest(3)` cho phép đúng hai lượt demand với `Flux.range` trực tiếp.
- Với `StreamService.events`, downstream nhận đúng record theo từng batch, không tự kết luận mọi operator khác cũng truyền 1:1.
- `BaseSubscriber` là cách kiểm soát demand thủ công; `hookOnSubscribe` phát request1, `hookOnNext` yêu cầu phần tử tiếp theo hoặc cancel. `Flux.range` đồng bộ nên assertions sau `subscribe` là deterministic; với async publisher cần cơ chế chờ/dồng bộ.

### 9.8. BackpressureOperatorsTest.java

`src/test/java/com/example/reactivelab/BackpressureOperatorsTest.java`:

```java
package com.example.reactivelab;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

class BackpressureOperatorsTest {

    @Test
    void bufferReshapesRequestIntoItems() {
        List<Long> upstreamRequests = new CopyOnWriteArrayList<>();

        Flux<List<Integer>> pipeline = Flux.range(1, 8)
                .doOnRequest(upstreamRequests::add)
                .buffer(2);

        StepVerifier.create(pipeline, 0)
                .expectSubscription()
                .thenRequest(2)
                .expectNext(List.of(1, 2), List.of(3, 4))
                .thenCancel()
                .verify(Duration.ofSeconds(2));

        // Two requested buffers of size 2 -> four upstream values.
        assertThat(upstreamRequests).contains(4L);
    }

    @Test
    void limitRateSplitsLargeRequestsIntoSmallBatches() {
        List<Long> upstreamRequests = new CopyOnWriteArrayList<>();

        Flux<Integer> source = Flux.range(1, 8)
                .doOnRequest(upstreamRequests::add)
                .limitRate(2, 0);

        StepVerifier.create(source, 0)
                .expectSubscription()
                .thenRequest(8)
                .expectNextCount(8)
                .verifyComplete();

        assertThat(upstreamRequests).isNotEmpty();
        assertThat(upstreamRequests)
                .allMatch(n -> n > 0L && n <= 2L);
        assertThat(upstreamRequests.stream()
                .mapToLong(Long::longValue).sum())
                .isGreaterThanOrEqualTo(8L);
    }

    @Test
    void takeCapsNumberOfDeliveredElements() {
        StepVerifier.create(Flux.range(1, 100).take(3), 0)
                .expectSubscription()
                .thenRequest(3)
                .expectNext(1, 2, 3)
                .verifyComplete();
    }

    @Test
    void badInputIsAnErrorSignalNotAnImmediateThrow() {
        StreamService service = new StreamService();

        Flux<Integer> source = service.integers(-1);

        StepVerifier.create(source)
                .expectErrorMatches(error ->
                        error instanceof IllegalArgumentException
                        && error.getMessage().contains("0..100"))
                .verify(Duration.ofSeconds(2));
    }
}
```

Trong `bufferReshapesRequestIntoItems`, `doOnRequest` đứng **trước** `buffer(2)` để thấy nhu cầu item upstream. Với `limitRate(2,0)`, không assert thứ tự số request cực kỳ chi tiết nếu không cần; invariant quan trọng là mỗi yêu cầu tới upstream có kích thước từ 1 tới 2 và tổng lượng được cấp đủ để phát tám item. Test `take` kiểm output, còn cancellation upstream được kiểm riêng trong lớp kế tiếp.

### 9.9. CancellationContractTest.java

`src/test/java/com/example/reactivelab/CancellationContractTest.java`:

```java
package com.example.reactivelab;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

import static org.assertj.core.api.Assertions.assertThat;

class CancellationContractTest {

    @Test
    void cancelInvokesCallbackAndFinallySignal() {
        AtomicBoolean cancelled = new AtomicBoolean();
        AtomicReference<SignalType> finalSignal = new AtomicReference<>();

        Flux<Integer> source = Flux.range(1, 100)
                .doOnCancel(() -> cancelled.set(true))
                .doFinally(finalSignal::set);

        StepVerifier.create(source, 0)
                .expectSubscription()
                .thenRequest(2)
                .expectNext(1, 2)
                .thenCancel()
                .verify(Duration.ofSeconds(2));

        assertThat(cancelled.get()).isTrue();
        assertThat(finalSignal.get()).isEqualTo(SignalType.CANCEL);
    }

    @Test
    void publisherProbeConfirmsUpstreamCancellation() {
        PublisherProbe<Integer> probe =
                PublisherProbe.of(Flux.range(1, 100));

        StepVerifier.create(probe.flux(), 0)
                .expectSubscription()
                .thenRequest(2)
                .expectNext(1, 2)
                .thenCancel()
                .verify(Duration.ofSeconds(2));

        probe.assertWasSubscribed();
        probe.assertWasRequested();
        probe.assertWasCancelled();
    }

    @Test
    void usingReleasesResourceOnCancel() {
        AtomicBoolean closed = new AtomicBoolean();

        Flux<Integer> values = Flux.using(
                Object::new,
                handle -> Flux.range(1, 100),
                handle -> closed.set(true));

        StepVerifier.create(values, 0)
                .expectSubscription()
                .thenRequest(1)
                .expectNext(1)
                .thenCancel()
                .verify(Duration.ofSeconds(2));

        assertThat(closed.get()).isTrue();
    }
}
```

Lớp này kiểm **cancellation observable** chứ không chỉ dừng assertion sau hai item. Nếu thay `thenCancel()` bằng `expectComplete()` trước khi nguồn gửi hết 100 phần tử, test có thể chờ mãi hoặc fail do thiếu demand. Nếu đổi source thành `Flux.range(1,2)` và yêu cầu đủ hai, upstream có thể complete trước cancel; vì vậy ví dụ dùng range 100 để cancel rõ ràng trước terminal signal.

### 9.10. TestPublisherProbeTest.java

`src/test/java/com/example/reactivelab/TestPublisherProbeTest.java`:

```java
package com.example.reactivelab;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;
import reactor.test.publisher.TestPublisher;

class TestPublisherProbeTest {

    @Test
    void testPublisherChecksDemandAndCancellation() {
        TestPublisher<Integer> upstream = TestPublisher.create();

        StepVerifier.create(upstream.flux(), 0)
                .expectSubscription()
                .then(() -> upstream.assertSubscribers(1))
                .thenRequest(2)
                .then(() -> upstream.assertMinRequested(2))
                .then(() -> upstream.next(11, 12))
                .expectNext(11, 12)
                .thenCancel()
                .verify(Duration.ofSeconds(2));

        upstream.assertCancelled();
        upstream.assertNoRequestOverflow();
    }

    @Test
    void probeChecksFallbackSubscriptionAndRequest() {
        PublisherProbe<Integer> fallback =
                PublisherProbe.of(Flux.just(99));

        Flux<Integer> pipeline = Flux.<Integer>empty()
                .switchIfEmpty(fallback.flux());

        StepVerifier.create(pipeline)
                .expectNext(99)
                .verifyComplete();

        fallback.assertWasSubscribed();
        fallback.assertWasRequested();
        fallback.assertWasNotCancelled();
    }
}
```

**Lý do tách hai tests:**
- `TestPublisher` chủ động phát `next(11,12)` **sau** khi đã quan sát request2; kiểm được cả demand và việc không overflow.
- `PublisherProbe` bao quanh fallback branch; xác nhận nhánh đã subscribe/request và hoàn thành bình thường (không cancel), thay vì chỉ assert output 99 rồi đoán branch nào đã chạy.

### 9.11. StreamControllerWebFluxTest.java

`src/test/java/com/example/reactivelab/StreamControllerWebFluxTest.java`:

```java
package com.example.reactivelab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Flux;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@WebFluxTest(StreamController.class)
class StreamControllerWebFluxTest {
    @Autowired
    WebTestClient client;

    @MockitoBean
    StreamService service;

    @Test
    void controllerDelegatesAndWritesJsonArray() {
        when(service.events(3)).thenReturn(Flux.just(
                new EventView(1, "event-1"),
                new EventView(2, "event-2"),
                new EventView(3, "event-3")));

        client.get()
                .uri("/streams?count=3")
                .exchange()
                .expectStatus().isOk()
                .expectBodyList(EventView.class)
                .hasSize(3);

        verify(service).events(3);
    }
}
```

`@WebFluxTest` kiểm reactive controller/request binding/serialization trong WebFlux slice, `@MockitoBean` cấp service vì slice không tự scan `@Service` như full context. Đây là test **HTTP contract**, không tự chứng minh demand từng item của upstream `Flux`. Muốn bảo vệ semantics đó, phải giữ `DemandContractTest`/`CancellationContractTest` ở Publisher layer. Nếu muốn chứng minh cancellation sau client disconnect thật, cần running-server integration test riêng với streaming representation và observability.

### 9.12. Lệnh chạy dự án

Yêu cầu JDK 17+, Maven, dependency repository truy cập được. Từ thư mục `reactive-demand-lab`:

```bash
mvn -q clean test
mvn -q -Dtest=DemandContractTest test
mvn -q -Dtest=BackpressureOperatorsTest test
mvn -q -Dtest=CancellationContractTest test
mvn -q -Dtest=TestPublisherProbeTest test
mvn -q -Dtest=StreamControllerWebFluxTest test
```

Các lớp được thiết kế PASS; lệnh Maven thành công trả **exit code 0**. Không cam kết stdout/log cố định vì Maven, context startup và scheduler khác nhau. Xem chi tiết tại `target/surefire-reports` nếu FAIL.

Có thể chạy ứng dụng bằng:

```bash
mvn spring-boot:run
```

Rồi ở terminal khác:

```bash
curl "http://localhost:8080/streams?count=3"
```

Response JSON có ba object `id=1,2,3` và `name="event-1","event-2","event-3"`. Tuy nhiên **cURL trả đủ JSON không chứng minh request(1) hay cancellation propagation**; nội dung JSON array có thể đã được WebFlux codec tập hợp trước khi trả.

## 10. Test giả lập nguồn hot và chính sách overflow

### 10.1. Khi nào thật sự có backpressure conflict?

Với `Flux.range` đã biết cách chờ request, downstream chưa yêu cầu sẽ không nhận thêm item. Cần hiểu các nguồn khác:
- Kafka receiver/network consumer có thể có buffer và prefetch riêng.
- SSE/metrics source có thể phát theo clock độc lập với client.
- Callback API có thể đẩy events vào `Flux.create`/`Sinks.Many` mà không biết demand.
- Các operator có prefetch có thể tạm lưu thêm item giữa upstream và downstream.

Backpressure được thỏa mãn ở **ranh giới subscriber**, nhưng không có nghĩa **mọi producer bên ngoài** tự chậm lại. Nếu producer không thể chậm, phải có chính sách buffer/drop/latest/error và capacity rõ ràng.

### 10.2. Ví dụ mô tả có kiểm soát

```java
Flux<String> bounded = incoming
        .onBackpressureBuffer(128);
```

Đây là **snippet minh họa trong code có `Flux<String> incoming`**. Nó không bảo đảm không bao giờ hết memory: với stream kéo dài, producer có thể vượt capacity và phát lỗi overflow theo operator/overload sử dụng. Khi hành vi overflow là contract, dùng overload có callback/strategy và test bằng `TestPublisher` hoặc một source hot có lịch phát deterministically.

```java
Flux<String> fastChanging = incoming
        .onBackpressureLatest();
```

Ở đây chỉ giữ item mới nhất chưa được subscriber nhận; thích hợp hơn với trạng thái UI/telemetry cho phép bỏ intermediate values, không thích hợp với ledger transaction mà mọi event đều phải giữ.

### 10.3. Test noncompliant publishers ở boundary nào?

Nếu muốn kiểm một custom operator xử lý nguồn vi phạm demand:

```java
TestPublisher<Integer> rogue = TestPublisher.createNoncompliant(
        TestPublisher.Violation.REQUEST_OVERFLOW);
```

Snippet trên chỉ tạo publisher **cố ý vi phạm**; một test hoàn chỉnh phải định nghĩa operator cần kiểm, thời điểm `next`, expected error/drop và cleanup. Không tự assert một exception type cụ thể khi chưa biết behavior của operator và version. `TestPublisher` phù hợp để kiểm **khả năng chịu đựng nguồn lỗi**, không là bằng chứng rằng production publisher tuân thủ Reactive Streams.

### 10.4. Discard không giống drop hoặc cancel

- **Drop**: source/operator bỏ signal không thể dùng hoặc signal sau terminal theo semantics/hook tương ứng.
- **Discard**: operator bỏ dữ liệu đang được giữ/buffer vì filter/cancel/error; có thể đăng ký cleanup qua `doOnDiscard` cho resource-bearing elements.
- **Cancel**: điều khiển subscription upstream.
- **Complete**: terminal signal thành công xuống subscriber.

Một cancel có thể kích hoạt discard của queue đã prefetch; muốn test memory/resource cleanup, kiểm các đối tượng bị discard và counter/closed state, không chỉ `PublisherProbe.assertWasCancelled()`. Với operator thay đổi đường đi và async queue, cần test tránh race và dùng cơ chế chờ xác định.

## 11. Virtual time và demand: tránh test đợi thời gian thật

### 11.1. Ví dụ không đợi 2 giờ

`Flux.interval` phát theo scheduler; dùng `StepVerifier.withVirtualTime` để điều khiển clock.

```java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofHours(1)).take(2),
        0)
        .expectSubscription()
        .thenRequest(2)
        .thenAwait(Duration.ofHours(2))
        .expectNext(0L, 1L)
        .verifyComplete();
```

Đây là mẫu test dùng Reactor 3.7 và imports `Flux`, `Duration`, `StepVerifier`. **Tạo publisher bên trong lambda** để Reactor có thể thay scheduler bằng virtual scheduler trước khi lập operator. Nếu xây `Flux.interval` ở ngoài rồi mới đưa vào lambda, timing có thể không dùng virtual clock như mong đợi.

### 11.2. Không có demand ở tick của interval

`Flux.interval` có tính chất đặc biệt: theo clock tick, nếu không có downstream demand khi tick đến, nó có thể phát lỗi overflow thay vì “đợi cho tới khi subscriber muốn” như `Flux.range`. Vì vậy:
- Trong test virtual time, cấp request **trước khi tiến clock** nếu kỳ vọng nhận dữ liệu.
- Đừng dùng `expectNoEvent` với request0 rồi tiến clock nhiều tick và mặc định source sẽ yên lặng.
- Nếu business cần bỏ ticks khi consumer chậm, chọn operator/semantics thích hợp, không dựa vào hành vi tình cờ của interval.

### 11.3. Virtual time không chứng minh hạ tầng thật

Virtual time giúp kiểm operator timing nhưng không mô phỏng chính xác TCP socket, remote scheduler, callback blocking hoặc system clock của mọi thư viện. Test cancellation thật qua HTTP hoặc message broker vẫn cần integration test với resource cleanup và timeout phù hợp.

## 12. Bảng phân loại tình huống kiểm thử

| Mục tiêu | Setup chính | Assertion cần có |
| --- | --- | --- |
| Không emit khi demand=0 | `StepVerifier.create(publisher, 0)` | Trước `thenRequest` không có `onNext`/side effect |
| Phát đúng n items khi request n | `thenRequest(n)` và `expectNext` | Đúng số lượng, thứ tự và giá trị |
| Demand tăng qua nhiều bước | `thenRequest(2)`, `thenRequest(3)` | Chuỗi items theo từng batch |
| Upstream nhận demand bao nhiêu | `doOnRequest` đặt đúng vị trí | List/metric request thay vì đoán |
| Buffer đổi đơn vị request | `buffer(k)` + instrumentation phía source | `request(m buffers)` có thể thành `m × k items` |
| limitRate định hình request | `limitRate(high, 0)` + trace | Mỗi request upstream nằm trong ngưỡng |
| Cancel bằng subscriber | `thenCancel` | `doOnCancel`/`doFinally(CANCEL)`/Probe |
| Đóng resource khi cancel | `Flux.using` hoặc `usingWhen` | Resource closed/cleanup publisher chạy |
| Chủ động phát signal | `TestPublisher` | `next` sau request, no overflow, cancelled |
| Theo dõi nhánh fallback | `PublisherProbe` | subscribed/requested/cancelled flags |
| Thời gian và demand | `withVirtualTime` + `thenRequest` | Ticks/data theo virtual clock |
| HTTP JSON contract | `@WebFluxTest + WebTestClient` | Status/JSON/route/delegation |
| HTTP client disconnect | Running-server integration test | Server-side cancel/cleanup instrumentation |
| Hot producer overflow | Hot Sink/noncompliant publisher có chủ đích | Bounded buffer/drop/error/cleanup đúng contract |

Khi đọc test report, xác định **pha xảy ra lỗi**: thiếu Spring context/bean; `AssertionError` từ StepVerifier; `onError` của publisher; hay timeout do không cấp demand. Chúng có nguyên nhân và hướng sửa khác nhau.

## 13. Debug và lỗi thường gặp

### 13.1. StepVerifier chờ mãi ở expectNext

Nguyên nhân có thể là `initialRequest=0` nhưng quên `thenRequest(n)`, hoặc mới request ít hơn số item đang kỳ vọng. Kiểm:
- Giá trị `StepVerifier.create(..., initialRequest)`.
- Tổng `thenRequest` trước mỗi `expectNext`.
- Operator `buffer(n)`/prefetch ảnh hưởng tín hiệu.
- Có async scheduler mà test chưa tiến thời gian không?

Đặt `verify(Duration.ofSeconds(...))` phù hợp để test không treo vô hạn. Tăng timeout không chữa thiếu demand.

### 13.2. Test expectNext nhiều hơn demand

Với `StepVerifierOptions.checkUnderRequesting` bật mặc định, verifier cố phát hiện kịch bản có ít request nhưng kỳ vọng quá nhiều onNext. Sửa test script cấp đủ `thenRequest`, không tắt check. Nếu **publisher tự phát quá demand**, đó là lỗi nguồn/protocol; dùng source instrumentation hoặc TestPublisher noncompliant khi cần xác minh operator chịu lỗi.

### 13.3. doOnRequest thấy Long.MAX_VALUE

`StepVerifier.create(publisher)` mặc định có unbounded initial request. `subscribe()` lambda-based và `block()` thường cũng tạo unbounded demand. Đây không nhất thiết là bug Reactor, mà là lựa chọn subscriber API. Dùng `StepVerifier.create(publisher,0)` và `thenRequest` nếu muốn kiểm backpressure hữu hạn.

### 13.4. Expect upstream request 2 nhưng thấy 6

`buffer(3)` downstream request2 buffers → upstream request6 items. Với `flatMap`/`publishOn`, prefetch cũng có thể khiến số upstream request lớn hơn downstream. Kiểm operator chain, vị trí `doOnRequest`, kích thước buffer/prefetch; không đổi assertion cho xanh nếu behavior đó thực sự là contract cần kiểm.

### 13.5. thenCancel nhưng không thấy onComplete

Đây là hành vi đúng: `cancel` không đòi publisher gửi `onComplete`. Hãy kiểm `doOnCancel`, `SignalType.CANCEL`, `PublisherProbe.assertWasCancelled()` và resource release. Test không nên đồng thời yêu cầu `expectComplete` sau khi đã `thenCancel` trên cùng subscription.

### 13.6. take(n) hoàn tất nhưng upstream vẫn nhận request lớn

Khác biệt có thể do `take(n,false)` hoặc operators có prefetch trước take. Trong Reactor 3.7, `take(n)` mặc định cap upstream request; nếu cần bảo đảm ranh giới tài nguyên, đặt `doOnRequest` trước đúng operator và kiểm chuỗi thật. Đừng suy luận từ output n items rằng producer không hề tính thêm items.

### 13.7. Callback onCancel chạy nhưng external task vẫn hoạt động

`doOnCancel` chỉ chứng minh callback quan sát cancel. Nếu source đã gửi việc sang thread pool, HTTP client, native API hoặc broker, callback còn phải **thực sự cancel/dispose** handles tương ứng. Kiểm resource object/task handle sau cancel; nếu cleanup async, dùng tín hiệu hoàn thành cleanup thay vì sleep tùy tiện.

### 13.8. Test dùng Flux.interval fail với request0

`Flux.interval` phát tick theo thời gian, có thể `onError` nếu không có demand khi tick xảy ra. Cấp request trước `thenAwait`, hoặc thiết kế source/overflow policy phù hợp. Không giả định mọi source hoạt động như `Flux.range`.

### 13.9. TestPublisher next trước khi subscriber request

`TestPublisher.create()` có kiểm tra một số quy tắc demand; phát quá request có thể lỗi hoặc signal bị xử lý tùy API/violation. Với bài kiểm hợp lệ, viết `thenRequest(2)` rồi `source.next(11,12)`. Dùng `createNoncompliant(REQUEST_OVERFLOW)` chỉ khi test **cố ý** mô phỏng nguồn sai protocol.

### 13.10. PublisherProbe chỉ thấy subscribed nhưng không requested

Subscribe chưa chắc đồng nghĩa đã có demand. Nếu initialRequest=0 và không `thenRequest`, probe có thể được subscribe nhưng chưa nhận request. Kiểm hai flags riêng. Khi fallback không được đi vào, `assertWasNotSubscribed` chứng minh không dùng nhánh; khi fallback được dùng nhưng cancel sớm, `assertWasCancelled` có thể đúng.

### 13.11. WebTestClient test PASS nhưng stream demand sai

`WebTestClient` ở HTTP layer thường tự subscribe/consume response theo codec, có prefetch/aggregation riêng. `expectBodyList` chỉ chứng minh JSON array/response contract. Muốn kiểm `request(n)` chính xác tại service Publisher, dùng `StepVerifier` đặt demand hữu hạn. Muốn kiểm client disconnect propagation, dùng server-bound integration test và instrument subscription tại nơi thích hợp.

### 13.12. Test flake vì scheduler và timing

Nếu test rely on `Thread.sleep` và `Flux.interval` real time, CI tải cao có thể flake. Với operator theo thời gian, dùng `StepVerifier.withVirtualTime` và build publisher **trong supplier**; với integration async, dùng timeout và latch/publisher completion có đồng bộ rõ. Tránh assert thứ tự cross-thread không được contract bảo đảm.

### 13.13. Reused Publisher có state giữa tests

Hot `Sinks.Many`, `TestPublisher` hoặc shared/`cache` Flux có thể giữ subscriber/buffer state. Tạo Publisher và probes mới **trong từng test method** để độc lập; không reuse shared mutable source giữa các test trừ khi đó chính là chủ đề concurrency cần kiểm.

### 13.14. Dữ liệu bị bỏ sau cancellation không được cleanup

Nhiều operators có queue/prefetch. Nếu item chứa tài nguyên cần `close`, cần thiết kế `doOnDiscard` hoặc cleanup theo operator support và kiểm điều kiện dispose. `doOnCancel` của source không tự release tất cả objects đã bị đưa vào buffer của operator khác.

### 13.15. Phân biệt cancel và error trong metrics

Khi một subscriber chủ động hủy, nếu metrics phân loại nhầm thành “error”, dashboard và alert sẽ sai. Dùng `doFinally(signalType -> ...)` hoặc Reactor observation/metrics ở vị trí phù hợp. HTTP client disconnect bình thường không nhất thiết là incident; cần xác định ngữ cảnh trước khi alert.

## 14. Tình huống nâng cao: backpressure qua hệ thống

### 14.1. Reactive HTTP không tự áp đặt từng request(n) ra network

Reactive Streams demand kiểm quan hệ `Publisher`/`Subscriber` trong process. HTTP/1.1 hay HTTP/2 có cơ chế flow control và buffering khác, nhưng chúng **không có một đối-một mapping** mặc định với `Subscription.request(n)` của từng domain event. JSON serialization có thể đổi đơn vị item; Netty có write buffers; TCP có send/receive windows.

Vì vậy, nếu chỉ thấy một HTTP client đã nhận 5 JSON objects, không được tuyên bố upstream được request chính xác5 lần. Nếu rủi ro là DB/repository query quá nhiều dữ liệu, instrument tại data publisher/driver boundary.

### 14.2. R2DBC/reactive repository

Một reactive repository trả `Flux<Entity>` có thể có driver-level prefetch/fetch size/cursors riêng. `take(10)` giới hạn downstream output nhưng chưa chắc database chỉ thực thi tối đa 10 rows vật lý. Kiểm query plan, driver settings và integration test database thật khi đây là yêu cầu hiệu năng. Không nhầm StepVerifier demand test với SQL/driver backpressure guarantee.

### 14.3. Messaging/brokers

Một Kafka/Pulsar/RabbitMQ reactive consumer có thể có broker queues, prefetch, offsets, acknowledgments và commit semantics không trùng Reactor demand. `cancel` subscription có thể ngừng poll hoặc hủy stream nhưng không tự undo offset commit hay message đã ack. Khi test integration, xác định rõ cancel có dừng subscription không và message in-flight xử lý thế nào.

### 14.4. Multicast và slow consumers

Với hot shared publisher, hai subscribers có demand khác nhau. Operator có thể buffer, drop, hoặc lựa chọn multicast strategy tùy `Sinks.Many` flavor. Test phải có **hai subscriptions độc lập**, cấp request khác nhau và assert events/overflow/cancel cho từng subscriber. Không suy từ một StepVerifier rằng toàn bộ multicast system xử lý slow consumers đúng.

### 14.5. Cancellation racing với completion

Một nguồn async có thể chuẩn bị phát `onComplete` đúng lúc downstream cancel. `doFinally` ở các vị trí có thể quan sát terminal signal khác do race; test không nên giả định thứ tự tuyệt đối nếu contract không bảo đảm. Để kiểm behavior deterministically, dùng `TestPublisher`/latches/scheduler có kiểm soát, hoặc assert invariant (không leak, không gửi onNext sau cancel) thay vì yêu cầu một timing duy nhất.

## 15. Bài tập tự luyện

1. Viết `StepVerifier.create(Flux.range(1,10),0)`, cấp `thenRequest(1)`, nhận một item, cấp thêm `thenRequest(2)`, nhận hai item và cancel. Đặt `doOnRequest` trước nguồn để quan sát.
2. Chuyển test trên thành `StepVerifierOptions.create().initialRequest(0).scenarioName(...)`. Thử cố ý kỳ vọng vượt demand để xem thông báo lỗi; sau đó sửa theo protocol.
3. Thêm `buffer(4)` vào Flux. Downstream yêu cầu hai buffers. Trước khi chạy, dự đoán upstream request tối thiểu ở nguồn; xác nhận bằng `doOnRequest`.
4. Dùng `limitRate(3,0)` cho source 20 items và downstream request 20. Assert mọi request tới upstream không vượt ba, nhưng đừng giả định mỗi request từ downstream giữ nguyên.
5. Tạo `PublisherProbe.of(Flux.range(1,100))`, nhận ba item rồi cancel. Assert `wasSubscribed`, `wasRequested`, `wasCancelled`.
6. Tạo `TestPublisher.create()`, không phát trước demand; sau `thenRequest(2)`, gọi `next(9,10)`. Assert output, no overflow, cancel.
7. Dùng `Flux.using` để sở hữu một resource có `close`. Thử ba đường complete/error/cancel và kiểm tài nguyên được đóng đúng một lần.
8. So sánh `Flux.range` với `Flux.interval` khi initialRequest0. Vì sao không nên dùng cùng kỳ vọng “im lặng không có demand” nếu interval vẫn tick theo clock?
9. Bật `@WebFluxTest` kiểm `StreamController` trả JSON ba items. Giải thích vì sao bài test đó không chứng minh upstream nhận `request(3)`.
10. Viết kiểm thử cancellation của streaming HTTP server thật: bạn sẽ instrument tại vị trí nào, dùng client cancellation ra sao, và chờ cleanup bằng gì để tránh race?
11. Với hot stream phát 1000 events/s và client chỉ nhận 10 events/s, đề xuất buffer/drop/latest/error và nêu trade-off mất dữ liệu/memory/latency; viết test theo chính sách đã chọn.
12. Một request1 tới `buffer(10)` khiến upstream nhận10. Đây là vi phạm Reactive Streams không? Giải thích bằng **đơn vị buffer** và **đơn vị item**.

Đạt yêu cầu khi người học biết xác định **demand ở mỗi cạnh của pipeline**, terminal/cancel signal và resource cleanup, thay vì chỉ sửa expected values để test xanh.

## 16. Checklist trước khi merge reactive test

- [ ] Đã xác định Publisher là cold, hot, multicast hoặc có queue/prefetch?
- [ ] Biết `StepVerifier.create(publisher)` mặc định initial request unbounded?
- [ ] Có dùng `initialRequest=0` khi muốn kiểm không phát trước demand?
- [ ] Có cấp `thenRequest(n)` đủ trước các `expectNext(...)`?
- [ ] Có kiểm output **và** request trace, không chỉ expectNext?
- [ ] Có đặt `doOnRequest` ở đúng phía operator đang cần đo?
- [ ] Với `buffer`, đã phân biệt demand theo buffer và theo item?
- [ ] Với `limitRate`, không tuyên bố đó là throttle theo giây?
- [ ] Với `flatMap`/`publishOn`, có hiểu prefetch và avoid brittle exact demand assertions?
- [ ] Với `thenCancel`, có kiểm `doOnCancel`/`doFinally(CANCEL)`/Probe không?
- [ ] Có phân biệt cancel với complete/error và timeout?
- [ ] Resource cleanup có thực sự chạy sau cancel, không chỉ có callback log?
- [ ] Với `TestPublisher`, có tránh phát vượt request trong test “compliant”?
- [ ] Với `PublisherProbe`, có assert subscription/request/cancel đúng nhánh?
- [ ] Với hot producer, có bounded buffer/drop/error policy và metrics?
- [ ] Nếu source dùng scheduler, đã dùng virtual time hoặc đồng bộ thay vì sleep/flaky assertion?
- [ ] Nếu test HTTP với WebTestClient, có hiểu nó không đảm bảo số request(n) ở source?
- [ ] Nếu test external DB/broker, có nhận thức được prefetch/ack/side effects độc lập cancellation?
- [ ] Test có timeout hợp lý, tạo source/probes riêng cho từng method, không leak shared state?
- [ ] Đã chạy JUnit/Maven suite và xem root cause của mọi failure?

**Kết luận:** Reactive Streams demand được điều khiển qua `request(n)`, các operators có thể **định hình lại request** theo buffer/prefetch, và `cancel()` là lệnh dừng subscription **khác** với onComplete/onError. Một bộ kiểm thử tốt dùng `StepVerifier` với request hữu hạn, `doOnRequest` để hiểu demand, `TestPublisher`/`PublisherProbe` để kiểm đường signal và `doOnCancel`/resource cleanup để chắc chắn cancellation có tác dụng. Khi lên WebFlux HTTP layer, giữ riêng các tests kiểm HTTP contract và tests kiểm Publisher semantics.

## 17. Nguồn tham khảo chính thức

- Project Reactor 3.7 — Testing (StepVerifier, TestPublisher, PublisherProbe): https://projectreactor.io/docs/core/3.7.17/reference/testing.html
- Project Reactor 3.7 — On Backpressure and Ways to Reshape Requests: https://projectreactor.io/docs/core/3.7.17/reference/subscribe-backpressure.html
- Project Reactor 3.7 — Flux API (take, limitRate, buffer): https://projectreactor.io/docs/core/3.7.17/api/reactor/core/publisher/Flux.html
- Reactor Test 3.7 — StepVerifier API: https://projectreactor.io/docs/test/3.7.17/api/reactor/test/StepVerifier.html
- Reactor Test 3.7 — TestPublisher API: https://projectreactor.io/docs/test/3.7.17/api/reactor/test/publisher/TestPublisher.html
- Reactor Test 3.7 — PublisherProbe API: https://projectreactor.io/docs/test/3.7.17/api/reactor/test/publisher/PublisherProbe.html
- Reactive Streams Specification v1.0.4: https://www.reactive-streams.org/
- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Framework 6.2 — WebTestClient for WebFlux testing: https://docs.spring.io/spring-framework/reference/6.2/testing/webtestclient.html
