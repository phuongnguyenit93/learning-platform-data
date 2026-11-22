# TestPublisher cho các kịch bản nguồn có kiểm soát trong Project Reactor

## 1. Mục tiêu bài học

Trong các ứng dụng dùng Spring WebFlux và Project Reactor, nhiều hành vi chỉ xuất hiện khi nguồn dữ liệu phát tín hiệu vào đúng thời điểm: một message đến sau khi subscriber đăng ký; upstream lỗi giữa chừng; downstream chỉ yêu cầu một phần tử; fallback chỉ được subscribe khi nguồn chính rỗng; hoặc cancellation xảy ra trước khi publisher hoàn tất.

Nếu dùng `Flux.just(...)` hay `Mono.just(...)` cho mọi test, dữ liệu đã được cố định sẵn, nên khó mô phỏng các thời điểm đặc biệt. `TestPublisher<T>` trong thư viện `reactor-test` là một **nguồn Publisher do test điều khiển bằng tay**. Nó cho phép phát `onNext`, `onComplete`, `onError` và quan sát subscription, request, cancellation. Đặt TestPublisher ở đầu pipeline, rồi dùng `StepVerifier` kiểm tra phản ứng của operator/service ở phía sau.

Sau bài này, người học có thể:

1. Tạo nguồn hot/cold có kiểm soát bằng `TestPublisher.create()` và `createCold()`.
2. Phát dữ liệu, hoàn tất và lỗi đúng thời điểm bằng `next(...)`, `emit(...)`, `complete()` và `error(...)`.
3. Kiểm tra hành vi bằng `StepVerifier.then(...)`, `thenRequest(...)`, `thenCancel()` và các assertion của nguồn.
4. Kiểm chứng backpressure, cancellation, fallback, timeout và error recovery mà không phụ thuộc network/database thật.
5. Dùng `createNoncompliant` để thử khả năng phòng vệ trước nguồn vi phạm Reactive Streams.
6. Phân biệt TestPublisher với `PublisherProbe`, `Sinks` và virtual time.
7. Viết một bộ unit test Java 17+ / JUnit 5 chạy được với Reactor Core và reactor-test.

## 2. Vị trí của TestPublisher trong một bài kiểm thử

~~~text
               +-------------------------+
               |        JUnit test       |
               |                         |
               |  TestPublisher<T>       |
               |  next / error / complete|
               +-------------+-----------+
                             |
                 Flux<T> hoặc Mono<T>
                             |
                             v
                  Operator / Service
                   map, filter, retry,
                   take, onErrorResume
                             |
                             v
                     StepVerifier
             expectNext / expectError /
             thenRequest / thenCancel
                             |
                             v
                TestPublisher.assertXxx
             subscribed/requested/cancelled
~~~

Có hai đối tượng với trách nhiệm khác nhau:

- **TestPublisher** quyết định *nguồn* phát signal nào và khi nào.
- **StepVerifier** quyết định *downstream* phải nhìn thấy signal nào và theo thứ tự nào.

Một test thường tạo nguồn, tạo pipeline cần kiểm tra, tạo StepVerifier, phát các signal trong callback `then(...)`, khai báo expectation và gọi `verify(...)` để chạy kiểm tra.

**Điểm mấu chốt:** chỉ gọi `StepVerifier.create(...)` chưa subscribe. Việc subscribe xảy ra khi gọi `verify(...)` hoặc một shortcut như `verifyComplete()`. Vì vậy, với nguồn hot, hãy phát dữ liệu trong callback của StepVerifier sau khi subscription đã được thiết lập.

## 3. Thêm thư viện vào dự án Java

`TestPublisher` nằm trong `reactor-test`, **không nằm trong reactor-core**. Thông thường khai báo `reactor-test` trong scope chỉ dành cho test.

Ví dụ Gradle Java 17, dùng các phiên bản được tài liệu Javadoc công bố:

~~~groovy
plugins {
    id 'java'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.7'

    testImplementation 'io.projectreactor:reactor-test:3.8.7'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.2'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Trong Spring Boot, nên để Spring Boot BOM quản lý cặp phiên bản `reactor-core` và `reactor-test` tương thích thay vì gắn hai phiên bản khác nhau. Với Gradle/Maven standalone, sử dụng hai version cùng dòng như ví dụ.

Import thường dùng:

~~~java
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;
import reactor.test.publisher.PublisherProbe;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
~~~

`TestPublisher` là công cụ kiểm thử, không phải một message broker hoặc publisher dùng trong production. Production dùng repository, WebClient, Sinks hoặc adapter khác tùy yêu cầu; test thay nguồn thực bằng TestPublisher để tái hiện tình huống có chủ đích.

## 4. API cốt lõi của TestPublisher

| API | Ý nghĩa |
| --- | --- |
| `TestPublisher.create()` | Tạo nguồn hot mặc định, có kiểm soát |
| `TestPublisher.createCold()` | Tạo nguồn cold, có buffer và replay cho subscriber |
| `createColdNonBuffering()` | Nguồn cold nhưng báo overflow trong một số tình huống thiếu request |
| `createNoncompliant(Violation...)` | Tạo nguồn hot được phép vi phạm một số quy tắc Reactive Streams |
| `source.flux()` | Bọc nguồn thành Flux |
| `source.mono()` | Bọc nguồn thành Mono, phù hợp luồng tối đa một giá trị |
| `source.next(value)` | Phát một onNext |
| `source.next(a, b, ...)` | Phát nhiều onNext theo thứ tự |
| `source.emit(a, b, ...)` | Phát các giá trị rồi complete |
| `source.complete()` | Phát onComplete |
| `source.error(exception)` | Phát onError |
| `assertSubscribers(n)` | Kiểm tra số subscriber đang hoạt động |
| `assertWasSubscribed()` | Xác minh đã từng có subscription |
| `assertWasRequested()` | Xác minh đã có request |
| `assertCancelled()` | Xác minh đã có cancellation |
| `assertNotCancelled()` | Xác minh chưa có cancellation |
| `assertMinRequested(n)` | Kiểm tra lượng demand tối thiểu hiện tại |
| `assertMaxRequested(n)` | Kiểm tra lượng demand tối đa hiện tại |
| `assertNoRequestOverflow()` | Xác nhận không có event vượt demand đã cấp |

Phần lớn method phát signal trả lại chính TestPublisher để có thể chain:

~~~java
source.next(1, 2).next(3).complete();
~~~

Hoặc:

~~~java
source.emit(1, 2, 3);
~~~

Hai đoạn minh họa đều phát ba giá trị rồi hoàn tất, **với điều kiện** nguồn và subscriber cho phép lượng request cần thiết. `emit(values)` đơn giản là tổ hợp phát giá trị và completion; không phải một sự kiện `onNext(List<T>)`.

## 5. Ví dụ đầu tiên: test map/filter bằng nguồn hot

Giả sử ứng dụng chuẩn hóa chuỗi: trim, bỏ chuỗi rỗng và viết hoa.

~~~java
public Flux<String> normalize(Flux<String> input) {
    return input.map(String::trim)
        .filter(value -> !value.isEmpty())
        .map(String::toUpperCase);
}
~~~

Test:

~~~java
TestPublisher<String> source = TestPublisher.create();

Flux<String> output = normalize(source.flux());

StepVerifier.create(output)
    .then(() -> source.assertSubscribers(1))
    .then(() -> source.next("  java  ", "   ", " reactor "))
    .expectNext("JAVA", "REACTOR")
    .then(source::complete)
    .expectComplete()
    .verify(Duration.ofSeconds(2));
~~~

Giải thích:

1. `create()` tạo một nguồn hot.
2. `normalize(source.flux())` tạo pipeline, chưa chạy.
3. `verify(...)` bắt đầu subscription.
4. `then(() -> source.assertSubscribers(1))` bảo đảm source đã có subscriber.
5. `then(() -> source.next(...))` phát ba giá trị có chủ đích.
6. Operator filter bỏ chuỗi rỗng, nên StepVerifier chỉ mong đợi hai giá trị.
7. `then(source::complete)` cho nguồn hoàn tất.
8. `expectComplete()` xác minh downstream hoàn tất, `verify(Duration)` chạy và giới hạn thời gian.

Nếu đổi thứ tự và gọi `source.next("java")` **trước** `verify(...)` với nguồn hot, giá trị có thể bị bỏ qua vì lúc đó không có subscriber. Test có thể timeout, hoặc chỉ thấy completion sau khi subscribe.

## 6. Hot source và cold source khác nhau

**Hot** trong trường hợp TestPublisher mặc định có nghĩa các giá trị phát ra được chuyển cho subscriber **đang có mặt tại thời điểm phát**. Nó không replay toàn bộ các giá trị trước đó cho subscriber đến muộn. Javadoc còn nêu rằng termination signal đầu tiên có thể được replay cho subscriber về sau.

**Cold TestPublisher** giữ những giá trị đã gọi `next(...)` trong buffer và replay chúng theo demand cho từng subscriber. Nó hữu ích khi muốn xây nguồn trước rồi test subscriber đến sau.

| Hành vi | `create()` hot | `createCold()` |
| --- | --- | --- |
| Phát giá trị trước subscribe | Có thể mất đối với subscriber đến sau | Buffer để replay |
| Subscriber mới | Thấy các onNext tương lai | Có thể nhận lại buffer lịch sử |
| Demand | Hot cần thận trọng không gửi vượt request | Cold buffered source giữ giá trị chờ request |
| Phù hợp | Races, live source, event đến sau subscribe | Replay, request-controlled scenarios, subscription sau khi phát |
| Rủi ro | Phát quá sớm khiến test treo | Buffer lớn làm test không giống nguồn thực tế |

### 6.1. Cold source phát trước khi subscribe

~~~java
TestPublisher<Integer> source = TestPublisher.createCold();
source.emit(10, 20, 30);

StepVerifier.create(source.flux())
    .expectNext(10, 20, 30)
    .expectComplete()
    .verify(Duration.ofSeconds(2));
~~~

Mặc dù `emit(...)` được gọi trước khi StepVerifier subscribe, cold publisher replay cả ba phần tử và completion. Với `create()` hot, test này không có behavior replay tương đương.

### 6.2. Replay cho nhiều subscriber

~~~java
TestPublisher<String> cold = TestPublisher.createCold();
cold.emit("A", "B");

StepVerifier.create(cold.flux())
    .expectNext("A", "B")
    .verifyComplete();

StepVerifier.create(cold.flux())
    .expectNext("A", "B")
    .verifyComplete();
~~~

Mỗi subscription nhận lại các giá trị đã buffer. Điều này không có nghĩa cold TestPublisher thực thi lại logic database; nó replay những giá trị do test đã cung cấp. Nếu cần mô phỏng một nguồn chạy logic mới mỗi lần subscribe, dùng `Flux.defer(...)` với mock/fake service phù hợp.

### 6.3. createColdNonBuffering

`createColdNonBuffering()` cũng có đặc tính cold/replay, nhưng sẽ báo overflow nếu subscriber mới yêu cầu ít hơn số item đã buffer, hoặc nếu item mới đến khi một subscriber không còn demand.

Dùng nó khi muốn test fail-fast với giả định về request mà không muốn cold buffered source âm thầm giữ thêm giá trị. Đây không phải factory “không lưu bất kỳ giá trị nào”; tên có thể gây hiểu lầm. Đọc đúng semantics trong Javadoc của version đang dùng.

## 7. Dùng next, emit, complete và error đúng lúc

### 7.1. next chỉ phát dữ liệu

~~~java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(source.flux())
    .then(() -> source.next(1))
    .expectNext(1)
    .then(() -> source.next(2, 3))
    .expectNext(2, 3)
    .then(source::complete)
    .verifyComplete();
~~~

`next` không tự đóng luồng. Nếu quên completion hoặc cancellation, StepVerifier đang đợi terminal signal có thể treo. Ưu tiên một timeout trên mỗi test.

### 7.2. emit phát rồi complete

~~~java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(source.flux())
    .then(() -> source.emit("a", "b"))
    .expectNext("a", "b")
    .verifyComplete();
~~~

`emit("a","b")` tương đương phát a, b và complete trong tình huống trên. Nó không phát một danh sách gồm a/b.

### 7.3. error kết thúc bằng lỗi

~~~java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(source.flux())
    .then(() -> source.next("ok"))
    .expectNext("ok")
    .then(() ->
        source.error(new IllegalStateException("upstream failed"))
    )
    .expectErrorMatches(error ->
        error instanceof IllegalStateException
            && "upstream failed".equals(error.getMessage())
    )
    .verify(Duration.ofSeconds(2));
~~~

Sau `onError`, không nên tiếp tục gọi `next` hoặc phát thêm terminal signal trên nguồn compliant. Reactive Streams quy định mỗi stream có tối đa một terminal signal. Nếu muốn kiểm thử nguồn vi phạm quy tắc này, phải dùng noncompliant factory phù hợp và ghi rõ rằng đây là adversarial test.

## 8. Kiểm thử error recovery bằng nguồn có kiểm soát

Ví dụ service fallback khi remote source lỗi:

~~~java
Flux<String> withFallback(Flux<String> remote) {
    return remote.onErrorResume(
        IllegalStateException.class,
        error -> Flux.just("cached")
    );
}
~~~

Test:

~~~java
TestPublisher<String> remote = TestPublisher.create();

StepVerifier.create(withFallback(remote.flux()))
    .then(() -> remote.next("live-1"))
    .expectNext("live-1")
    .then(() ->
        remote.error(new IllegalStateException("offline"))
    )
    .expectNext("cached")
    .verifyComplete();
~~~

Khi remote phát lỗi, `onErrorResume` thay bằng Flux fallback. Downstream thấy giá trị đã nhận trước lỗi rồi nhận `cached` và complete.

Nếu lỗi không thuộc kiểu được xử lý, nó phải đi tới downstream:

~~~java
TestPublisher<String> remote = TestPublisher.create();

StepVerifier.create(withFallback(remote.flux()))
    .then(() ->
        remote.error(new IllegalArgumentException("bad payload"))
    )
    .expectError(IllegalArgumentException.class)
    .verify(Duration.ofSeconds(2));
~~~

Điểm cần học: TestPublisher không tự tạo recovery; nó chỉ tạo một tình huống lỗi có thể dự đoán, để bạn kiểm tra logic `onErrorResume` của ứng dụng.

## 9. Kiểm thử empty và fallback subscription

Khi `Mono.empty()` hoàn tất, các toán tử như `defaultIfEmpty` hoặc `switchIfEmpty` có thể kích hoạt nhánh fallback.

### 9.1. Source empty

~~~java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(source.mono().defaultIfEmpty("unknown"))
    .then(source::complete)
    .expectNext("unknown")
    .verifyComplete();
~~~

Ở đây source không phát onNext. `defaultIfEmpty` tạo giá trị `unknown`.

### 9.2. Hai nguồn có kiểm soát

~~~java
TestPublisher<String> primary = TestPublisher.create();
TestPublisher<String> fallback = TestPublisher.create();

Mono<String> result = primary.mono()
    .switchIfEmpty(fallback.mono());

StepVerifier.create(result)
    .then(() -> primary.assertSubscribers(1))
    .then(primary::complete)
    .then(() -> fallback.assertSubscribers(1))
    .then(() -> fallback.emit("from-fallback"))
    .expectNext("from-fallback")
    .verifyComplete();
~~~

Các bước chứng minh fallback **chỉ** được subscribe sau khi primary complete rỗng. Nếu primary phát giá trị, fallback không được subscribe.

### 9.3. Khi chỉ cần biết fallback có được dùng hay không

`PublisherProbe` là công cụ nhẹ hơn nếu không cần tự phát tín hiệu:

~~~java
PublisherProbe<String> probe =
    PublisherProbe.of(Mono.just("fallback"));

StepVerifier.create(
    Mono.<String>empty().switchIfEmpty(probe.mono())
)
    .expectNext("fallback")
    .verifyComplete();

probe.assertWasSubscribed();
probe.assertWasRequested();
~~~

TestPublisher cũng triển khai `PublisherProbe`, nhưng nếu mục tiêu duy nhất là xác minh subscribe/request/cancel của nhánh thì PublisherProbe diễn đạt ý định rõ hơn.

## 10. Kiểm thử backpressure theo request(n)

Reactive Streams dùng tín hiệu `request(n)` để downstream thông báo cho upstream được phát thêm tối đa n phần tử. Nếu không kiểm tra demand, một test có thể vô tình chạy với request không giới hạn.

`StepVerifier.create(publisher, initialRequest)` cho phép bắt đầu với demand bằng 0 và cấp request từng đợt:

~~~java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(source.flux(), 0)
    .expectSubscription()
    .then(() -> source.assertSubscribers(1))
    .thenRequest(1)
    .then(() -> source.assertMinRequested(1).next(10))
    .expectNext(10)
    .thenRequest(1)
    .then(() -> source.next(20))
    .expectNext(20)
    .then(source::complete)
    .verifyComplete();

source.assertNoRequestOverflow();
~~~

Giải thích:

- Ban đầu nguồn có subscriber nhưng chưa được cấp demand.
- `thenRequest(1)` cấp quyền phát một phần tử.
- TestPublisher phát 10 và StepVerifier mong đợi 10.
- Cấp thêm một quyền phát, sau đó phát 20.
- `assertNoRequestOverflow()` xác nhận nguồn không nhận onNext lúc demand bằng 0 theo logic assertion của TestPublisher.

**Lưu ý về demand do operator tạo ra:** StepVerifier `thenRequest(1)` không có nghĩa một source nằm sau `publishOn`, `flatMap` hay `buffer` cũng chỉ thấy đúng `request(1)`. Một số operator có prefetch, batching hoặc request strategy riêng. Đặt assertion demand ở tầng bạn thật sự đang kiểm tra và không cứng hóa con số request nếu operator được phép thay đổi prefetch.

### 10.1. Kiểm tra nguồn có được request hay không

~~~java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(source.flux(), 0)
    .expectSubscription()
    .then(source::assertWasSubscribed)
    .thenRequest(1)
    .then(source::assertWasRequested)
    .then(() -> source.emit("one"))
    .expectNext("one")
    .verifyComplete();
~~~

Đây là một cách tạo checklist subscription/demand đơn giản: subscriber đã được đăng ký rồi mới request, sau đó mới nhận item.

### 10.2. Vì sao không phát vượt demand trên nguồn compliant?

Nếu tạo hot `TestPublisher.create()` rồi cố gọi `next(value)` khi downstream chưa request đủ, implementation có thể báo `IllegalStateException` vì phát vượt nhu cầu là vi phạm Reactive Streams. Đó là behavior bảo vệ của test tool, không nhất thiết là error do operator mà bạn đang thử phát ra.

Khi cần chủ ý kiểm tra operator trong tình huống upstream không tuân thủ, hãy dùng `createNoncompliant(Violation.REQUEST_OVERFLOW)`; đừng tắt mọi validation một cách vô thức.

## 11. Kiểm thử cancellation

Cancellation quan trọng với `take`, `timeout`, `switchMap`, request bị hủy và các pipeline có resource. TestPublisher có thể xác nhận upstream bị cancel.

### 11.1. take(n) ngắt nguồn

~~~java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(source.flux().take(2))
    .then(() -> source.next("first", "second"))
    .expectNext("first", "second")
    .verifyComplete();

source.assertCancelled();
~~~

`take(2)` hoàn tất downstream sau hai phần tử và hủy subscription upstream khi không cần dữ liệu nữa. Đây là behavior cần test nếu upstream đại diện connection, cursor hoặc event feed có chi phí.

### 11.2. Hủy trực tiếp từ StepVerifier

~~~java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(source.flux())
    .then(() -> source.next(1))
    .expectNext(1)
    .thenCancel()
    .verify();

source.assertCancelled();
~~~

`thenCancel()` chủ động hủy subscription thay vì chờ source complete/error. Khi code production làm việc với publisher vô hạn, test theo hướng này thường tự nhiên hơn việc ép source complete.

### 11.3. Không lẫn cancellation với completion

| Tình huống | Downstream | Upstream |
| --- | --- | --- |
| `source.complete()` | Nhận completion | Đã hoàn tất |
| `source.error(e)` | Nhận error hoặc recovery | Đã kết thúc bằng error |
| `take(2)` sau hai item | Hoàn tất bình thường | Có thể nhận cancellation |
| `thenCancel()` | Test chủ động hủy | Nhận cancellation |
| `timeout` khi chưa có item | Nhận TimeoutException nếu không fallback | Subscription nguồn bị cancel |

Không dùng `assertCancelled()` để chứng minh một nguồn đã `complete()` bình thường. Tương tự, `assertNoSubscribers()` và `assertCancelled()` không hỏi cùng một điều: một cái nói về số subscriber hiện tại, một cái nói về lịch sử cancellation.

## 12. Kiểm thử timeout kết hợp virtual time

TestPublisher kiểm soát sự kiện, nhưng để giả lập thời gian trôi mà không chờ thật, dùng `StepVerifier.withVirtualTime(...)`:

~~~java
TestPublisher<String> slow = TestPublisher.create();

StepVerifier.withVirtualTime(() ->
        slow.flux().timeout(Duration.ofSeconds(5))
    )
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(5))
    .expectError(TimeoutException.class)
    .verify(Duration.ofSeconds(2));

slow.assertCancelled();
~~~

Operator `timeout` được tạo **bên trong supplier** của `withVirtualTime` để scheduler ảo có hiệu lực. TestPublisher đã tạo trước có thể giữ nguyên vì nó chỉ phát signal thủ công; scheduler cho timeout là phần cần dựng lười.

Sự khác biệt:

- TestPublisher: quyết định *dữ liệu hoặc lỗi nào phát ra*.
- Virtual time: quyết định *thời gian của scheduler Reactor tiến bao nhiêu*.
- StepVerifier: quyết định *kết quả nào được kỳ vọng*.

Một test có thể dùng cả ba, nhưng virtual time không phải lựa chọn bắt buộc cho mọi kịch bản TestPublisher. Nếu code dùng scheduler được tạo thủ công hoặc clock khác Reactor, virtual time có thể không điều khiển được clock đó.

## 13. Nguồn vi phạm Reactive Streams bằng createNoncompliant

Đôi khi cần test một operator hoặc adapter phòng vệ trước nguồn không đúng chuẩn, ví dụ một thư viện ngoài phát item dù không có demand, phát null, phát terminal signal lần hai hoặc tiếp tục phát sau cancellation.

`TestPublisher.createNoncompliant(TestPublisher.Violation...)` cho phép tạo nguồn hot có thể vi phạm các quy tắc cụ thể.

| Violation | Hành vi được nới lỏng | Điều cần chú ý |
| --- | --- | --- |
| `REQUEST_OVERFLOW` | Cho phát `next` dù subscriber chưa có đủ demand | Có thể khiến downstream phát hiện request overflow |
| `ALLOW_NULL` | Cho truyền null vào `next` | Null trái Reactive Streams; downstream có thể NPE/drop/error |
| `CLEANUP_ON_TERMINATE` | Cho thử nhiều terminal signal liên tiếp | Dùng để kiểm tra tín hiệu sau terminal bị drop/handle |
| `DEFER_CANCELLATION` | Cho giả lập nguồn tiếp tục phát sau cancel | Mô phỏng race giữa cancel và upstream emission |

Ví dụ nguồn vi phạm demand:

~~~java
TestPublisher<Integer> misbehaving =
    TestPublisher.createNoncompliant(
        TestPublisher.Violation.REQUEST_OVERFLOW
    );
~~~

Một test nâng cao có thể gắn subscriber **không gọi request**, sau đó phát một phần tử và xác minh TestPublisher đã ghi nhận request overflow. Nếu đưa nguồn này qua `StepVerifier.create(..., 0)`, việc phát `onNext` trái demand có thể khiến StepVerifier báo lỗi xác minh; đó thường là **mục tiêu** của negative test, không phải dấu hiệu TestPublisher bị hỏng.

### 13.1. Ví dụ positive test kiểm tra nguồn noncompliant

~~~java
TestPublisher<Integer> bad =
    TestPublisher.createNoncompliant(
        TestPublisher.Violation.REQUEST_OVERFLOW
    );

BaseSubscriber<Integer> zeroDemand = new BaseSubscriber<>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        // Cố ý không request.
    }
};

bad.subscribe(zeroDemand);
bad.next(42);
bad.assertRequestOverflow();

zeroDemand.cancel();
bad.assertCancelled();
~~~

Import `reactor.core.publisher.BaseSubscriber` và `org.reactivestreams.Subscription`. Đây là test cho **tình huống nguồn vi phạm**, không phải ví dụ cách implement publisher đúng chuẩn trong production.

### 13.2. Đừng bật mọi Violation để test chạy xanh

Việc dùng `ALLOW_NULL` hoặc `REQUEST_OVERFLOW` như một cách lách assertion của test bình thường sẽ che giấu bug về demand và tín hiệu. Chỉ mở đúng violation mà bạn cố ý mô phỏng và ghi rõ invariant đang kiểm thử.

Không cần tạo nguồn noncompliant để test HTTP 500, Redis timeout hoặc một DomainException; các trường hợp đó dùng `source.error(exception)` là đủ.

## 14. Phân biệt TestPublisher, PublisherProbe, Sinks và StepVerifier

| Công cụ | Chạy ở đâu | Mục đích |
| --- | --- | --- |
| `TestPublisher` | Test source | Chủ động phát onNext/onComplete/onError và assert request/cancel |
| `StepVerifier` | Test subscriber | Định nghĩa expectation của publisher |
| `PublisherProbe` | Test branch | Xác minh một fallback/branch đã subscribe, request, cancel |
| `Sinks.Many` | Thường production hoặc test | Imperative bridge để phát vào Flux, có kết quả emit và concurrency semantics |
| `VirtualTimeScheduler` | Test | Điều khiển scheduler time |
| `Mockito`/fake repository | Test dependency | Kiểm soát lời gọi service/repository |

Dùng TestPublisher khi **thứ tự signal** là trọng tâm. Dùng PublisherProbe khi **việc đi qua một nhánh** là trọng tâm. Dùng StepVerifier để xác nhận **đầu ra**. Dùng Sinks khi production cần một cầu nối nguồn imperative sang stream, với các quy tắc multi-threading và backpressure riêng của Sinks.

Không đưa TestPublisher vào Spring bean production rồi dùng nó thay message bus chỉ vì API `next()` tiện; đây là công cụ trong `reactor-test` và có các giới hạn thread-safety được Javadoc ghi rõ.

## 15. Kịch bản giả lập data source ở service layer

Giả sử một service đọc dữ liệu nhiệt độ rồi chỉ phát cảnh báo khi ngưỡng cao.

Interface:

~~~java
public interface TemperatureSource {
    Flux<Integer> temperatures();
}
~~~

Service:

~~~java
public final class AlertService {
    private final TemperatureSource source;

    public AlertService(TemperatureSource source) {
        this.source = source;
    }

    public Flux<String> alerts() {
        return source.temperatures()
            .filter(value -> value >= 80)
            .map(value -> "HOT:" + value);
    }
}
~~~

Test dùng TestPublisher làm fake nguồn:

~~~java
TestPublisher<Integer> temperatures = TestPublisher.create();
AlertService service = new AlertService(temperatures::flux);

StepVerifier.create(service.alerts())
    .then(() -> temperatures.next(60, 82, 95))
    .expectNext("HOT:82", "HOT:95")
    .then(temperatures::complete)
    .verifyComplete();
~~~

Cách này không cần database, sensor, WebSocket client hoặc scheduler thật. Test tập trung vào **logic lọc và map** của service. Trong hệ thống WebFlux, dependency có thể được inject qua constructor, và test chọn fake implementation trả `temperatures.flux()`.

Nếu cần test cả HTTP status/headers/security, dùng `WebTestClient` như integration test bổ sung. TestPublisher không thay thế hoàn toàn kiểm thử end-to-end.

## 16. Test nguồn rỗng, retry và re-subscription

### 16.1. Empty branch

~~~java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(source.flux().switchIfEmpty(Flux.just(99)))
    .then(source::complete)
    .expectNext(99)
    .verifyComplete();
~~~

Kết quả 99 cho thấy fallback chạy khi nguồn không phát onNext.

### 16.2. retry thực chất là đăng ký lại

Giả sử:

~~~java
Flux<String> retried = source.flux().retry(1);
~~~

`retry(1)` không phát lại một signal lỗi trên cùng subscription; nó **subscribe lại nguồn**. Một hot TestPublisher đã error thường không phù hợp để test tình huống “lần đầu lỗi, lần sau thành công” bằng cách tiếp tục `next(...)` trên cùng instance. Nguồn đã terminal, và subscription mới không tự biến trạng thái terminal thành một attempt độc lập.

Để test retry từng attempt, kết hợp `Flux.defer` với nguồn **mới cho mỗi lần subscribe** hoặc fake service đếm attempt:

~~~java
AtomicInteger attempts = new AtomicInteger();

Flux<String> retried = Flux.defer(() -> {
    int attempt = attempts.incrementAndGet();

    if (attempt == 1) {
        return Flux.error(
            new IllegalStateException("temporary")
        );
    }

    return Flux.just("recovered");
}).retry(1);

StepVerifier.create(retried)
    .expectNext("recovered")
    .verifyComplete();

assertEquals(2, attempts.get());
~~~

TestPublisher vẫn hữu ích khi cần điều khiển từng attempt, nhưng hãy khởi tạo các instance riêng hoặc một factory trả publisher tương ứng. Không gán mọi retry cho một nguồn hot đã hoàn tất và mong kết quả hợp lệ.

### 16.3. Testing subscription count

`TestPublisher` triển khai PublisherProbe, có thể dùng `subscribeCount()` để hỗ trợ kiểm tra bao nhiêu lần upstream được subscribe. Tuy nhiên, nếu mô hình là nguồn hot có terminal cố định, số lần subscribe không chứng minh mỗi attempt đã được thực hiện lại công việc thực tế. Hãy kết hợp assertion trên adapter/factory khi yêu cầu là retry network hoặc database call.

## 17. Hạn chế và vấn đề determinism

TestPublisher không phải phép màu giải quyết mọi asynchronous race. Javadoc nhấn mạnh nguồn này nói chung không an toàn khi nhiều thread đồng thời thao tác.

**Những điều giúp test ổn định:**

1. Phát signal qua `StepVerifier.then(...)` sau subscription.
2. Chỉ dùng một thread điều khiển TestPublisher trừ khi bạn đang cố ý test concurrency.
3. Không dùng `Thread.sleep` để đoán “subscriber đã đăng ký”.
4. Dùng `assertSubscribers(1)` trong callback để chứng minh subscription đã tồn tại.
5. Dùng `thenRequest(n)` khi muốn kiểm tra demand.
6. Luôn có terminal expectation hoặc `thenCancel()`.
7. Đặt timeout cho verification để không chờ vô hạn khi bug xảy ra.
8. Không phụ thuộc order giữa nhiều thread nếu operator cho phép interleaving.
9. Đừng khẳng định exact request count qua operator có prefetch khi API không cam kết.
10. Dọn source và subscriptions cho từng test; tạo TestPublisher mới trong từng method JUnit để tránh chia sẻ state.

Một test dùng `StepVerifier.then(...)` thường dễ đọc hơn việc chạy một ExecutorService riêng, chờ latch rồi bất chợt phát onNext. Chỉ cần threading tools khi race/concurrency chính là hành vi phải thử.

## 18. Dự án Gradle Java 17+ độc lập có thể chạy

Dưới đây là một dự án độc lập sử dụng Reactor Core 3.8.7, reactor-test 3.8.7 và JUnit 5. Tất cả ví dụ test nằm trong một class, không cần server, network, database hoặc Spring Boot.

Cấu trúc:

~~~text
reactor-testpublisher-lab/
  settings.gradle
  build.gradle
  src/
    main/java/demo/
      AlertService.java
      TemperatureSource.java
    test/java/demo/
      TestPublisherLabTest.java
~~~

### 18.1. settings.gradle

~~~groovy
rootProject.name = 'reactor-testpublisher-lab'
~~~

### 18.2. build.gradle

~~~groovy
plugins {
    id 'java'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'io.projectreactor:reactor-core:3.8.7'
    testImplementation 'io.projectreactor:reactor-test:3.8.7'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.12.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.12.2'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

### 18.3. TemperatureSource.java

~~~java
package demo;

import reactor.core.publisher.Flux;

@FunctionalInterface
public interface TemperatureSource {
    Flux<Integer> temperatures();
}
~~~

### 18.4. AlertService.java

~~~java
package demo;

import reactor.core.publisher.Flux;

public final class AlertService {
    private final TemperatureSource source;

    public AlertService(TemperatureSource source) {
        this.source = source;
    }

    public Flux<String> alerts() {
        return source.temperatures()
            .filter(value -> value >= 80)
            .map(value -> "HOT:" + value);
    }
}
~~~

### 18.5. TestPublisherLabTest.java

~~~java
package demo;

import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;
import reactor.test.publisher.TestPublisher;

import static org.junit.jupiter.api.Assertions.assertEquals;

class TestPublisherLabTest {

    private static final Duration VERIFY_TIMEOUT =
        Duration.ofSeconds(3);

    @Test
    void hotSourceRunsMapAndFilter() {
        TestPublisher<String> source = TestPublisher.create();

        Flux<String> output = source.flux()
            .map(String::trim)
            .filter(s -> !s.isEmpty())
            .map(String::toUpperCase);

        StepVerifier.create(output)
            .then(() -> source.assertSubscribers(1))
            .then(() -> source.next(" java ", "  ", "reactor"))
            .expectNext("JAVA", "REACTOR")
            .then(source::complete)
            .expectComplete()
            .verify(VERIFY_TIMEOUT);

        source.assertNotCancelled();
    }

    @Test
    void emitSendsValuesThenCompletes() {
        TestPublisher<String> source = TestPublisher.create();

        StepVerifier.create(source.flux())
            .then(() -> source.emit("A", "B"))
            .expectNext("A", "B")
            .expectComplete()
            .verify(VERIFY_TIMEOUT);
    }

    @Test
    void coldSourceReplaysBufferedValues() {
        TestPublisher<Integer> source = TestPublisher.createCold();
        source.emit(3, 5);

        StepVerifier.create(source.flux(), 0)
            .expectSubscription()
            .thenRequest(1)
            .expectNext(3)
            .thenRequest(1)
            .expectNext(5)
            .expectComplete()
            .verify(VERIFY_TIMEOUT);

        StepVerifier.create(source.flux())
            .expectNext(3, 5)
            .expectComplete()
            .verify(VERIFY_TIMEOUT);
    }

    @Test
    void upstreamErrorTriggersFallback() {
        TestPublisher<String> source = TestPublisher.create();

        Flux<String> output = source.flux()
            .onErrorResume(
                IOException.class,
                error -> Flux.just("cached")
            );

        StepVerifier.create(output)
            .then(() -> source.next("online"))
            .expectNext("online")
            .then(() ->
                source.error(new IOException("down"))
            )
            .expectNext("cached")
            .expectComplete()
            .verify(VERIFY_TIMEOUT);
    }

    @Test
    void unexpectedErrorIsPropagated() {
        TestPublisher<String> source = TestPublisher.create();

        StepVerifier.create(
                source.flux().onErrorResume(
                    IOException.class,
                    error -> Flux.just("cached")
                )
            )
            .then(() ->
                source.error(new IllegalArgumentException("invalid"))
            )
            .expectError(IllegalArgumentException.class)
            .verify(VERIFY_TIMEOUT);
    }

    @Test
    void emptySourceUsesFallback() {
        TestPublisher<String> source = TestPublisher.create();

        StepVerifier.create(
                source.mono().defaultIfEmpty("unknown")
            )
            .then(source::complete)
            .expectNext("unknown")
            .expectComplete()
            .verify(VERIFY_TIMEOUT);
    }

    @Test
    void switchIfEmptySubscribesFallback() {
        TestPublisher<String> primary = TestPublisher.create();
        TestPublisher<String> fallback = TestPublisher.create();

        Mono<String> output = primary.mono()
            .switchIfEmpty(fallback.mono());

        StepVerifier.create(output)
            .then(() -> primary.assertSubscribers(1))
            .then(primary::complete)
            .then(() -> fallback.assertSubscribers(1))
            .then(() -> fallback.emit("from-fallback"))
            .expectNext("from-fallback")
            .expectComplete()
            .verify(VERIFY_TIMEOUT);

        primary.assertWasSubscribed();
        fallback.assertWasSubscribed();
    }

    @Test
    void publisherProbeShowsFallbackWasNotUsed() {
        TestPublisher<String> primary = TestPublisher.create();
        PublisherProbe<String> fallback =
            PublisherProbe.of(Mono.just("cached"));

        StepVerifier.create(
                primary.mono().switchIfEmpty(fallback.mono())
            )
            .then(() -> primary.emit("live"))
            .expectNext("live")
            .expectComplete()
            .verify(VERIFY_TIMEOUT);

        fallback.assertWasNotSubscribed();
    }

    @Test
    void demandIsGrantedInTwoSteps() {
        TestPublisher<Integer> source = TestPublisher.create();

        StepVerifier.create(source.flux(), 0)
            .expectSubscription()
            .then(() -> source.assertSubscribers(1))
            .thenRequest(1)
            .then(() -> source.assertMinRequested(1).next(10))
            .expectNext(10)
            .thenRequest(1)
            .then(() -> source.next(20))
            .expectNext(20)
            .then(source::complete)
            .expectComplete()
            .verify(VERIFY_TIMEOUT);

        source.assertNoRequestOverflow();
    }

    @Test
    void takeCancelsUpstreamAfterEnoughItems() {
        TestPublisher<String> source = TestPublisher.create();

        StepVerifier.create(source.flux().take(2))
            .then(() -> source.next("first", "second"))
            .expectNext("first", "second")
            .expectComplete()
            .verify(VERIFY_TIMEOUT);

        source.assertCancelled();
    }

    @Test
    void verifierCanCancelExplicitly() {
        TestPublisher<Integer> source = TestPublisher.create();

        StepVerifier.create(source.flux())
            .then(() -> source.next(1))
            .expectNext(1)
            .thenCancel()
            .verify(VERIFY_TIMEOUT);

        source.assertCancelled();
    }

    @Test
    void virtualTimeTriggersTimeoutWithoutSleeping() {
        TestPublisher<Integer> silent = TestPublisher.create();

        StepVerifier.withVirtualTime(() ->
                silent.flux().timeout(Duration.ofSeconds(5))
            )
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(5))
            .expectError(TimeoutException.class)
            .verify(VERIFY_TIMEOUT);

        silent.assertCancelled();
    }

    @Test
    void noncompliantSourceCanRecordRequestOverflow() {
        TestPublisher<Integer> source =
            TestPublisher.createNoncompliant(
                TestPublisher.Violation.REQUEST_OVERFLOW
            );

        BaseSubscriber<Integer> noDemand = new BaseSubscriber<>() {
            @Override
            protected void hookOnSubscribe(
                    Subscription subscription) {
                // Chủ ý không gọi request.
            }
        };

        source.subscribe(noDemand);
        source.next(42);
        source.assertRequestOverflow();

        noDemand.cancel();
        source.assertCancelled();
    }

    @Test
    void serviceRespondsToControlledSensorEvents() {
        TestPublisher<Integer> source = TestPublisher.create();
        AlertService service = new AlertService(source::flux);

        StepVerifier.create(service.alerts())
            .then(() -> source.next(60, 82, 95))
            .expectNext("HOT:82", "HOT:95")
            .then(source::complete)
            .expectComplete()
            .verify(VERIFY_TIMEOUT);
    }

    @Test
    void retryResubscribesToFreshDeferredAttempt() {
        AtomicInteger attempts = new AtomicInteger();

        Flux<String> retrying = Flux.defer(() -> {
            if (attempts.incrementAndGet() == 1) {
                return Flux.error(
                    new IllegalStateException("temporary")
                );
            }
            return Flux.just("recovered");
        }).retry(1);

        StepVerifier.create(retrying)
            .expectNext("recovered")
            .expectComplete()
            .verify(VERIFY_TIMEOUT);

        assertEquals(2, attempts.get());
    }
}
~~~

**Cấu trúc này là ví dụ chạy độc lập.** Các đoạn ngắn ở những phần trước đôi khi chỉ là snippet có biến placeholder như `source`, `process(...)` hoặc `withFallback(...)`; chúng dùng để giải thích API, không thay thế các file đầy đủ trên.

### 18.6. Chạy test

Cần Java 17 và một phiên bản Gradle hỗ trợ Java 17, Reactor dependency đã tải được từ Maven Central. Nếu dự án có Gradle Wrapper:

~~~bash
./gradlew test
~~~

Nếu chưa có Wrapper nhưng đã cài Gradle:

~~~bash
gradle test
~~~

Chạy một method:

~~~bash
gradle test --tests demo.TestPublisherLabTest.demandIsGrantedInTwoSteps
~~~

Khi chạy thành công, Gradle báo tác vụ `:test` thành công; bản thân các test không in stdout cố định vì assertions mới là kết quả. Không đưa ra một snapshot stdout với version/elapsed time cố định, vì Gradle output khác nhau theo môi trường.

### 18.7. Đọc kết quả lỗi

Nếu một test timeout, kiểm tra:

- `verify(...)` có thực sự được gọi chưa?
- Source có subscriber trước khi phát `next(...)` chưa?
- Có quên `source.complete()` hoặc `source.error(...)` không?
- StepVerifier đã `thenRequest(n)` đủ chưa?
- Có phát source trước `then(...)` do nhầm hot/cold không?
- Operator có đổi demand hoặc trigger cancellation trước kỳ vọng không?
- Có operator thời gian tạo trước khi virtual scheduler được bật không?

Nếu assertion `assertSubscribers(1)` thất bại, xem lại pipeline subscription và thứ tự callback; không giải quyết bằng Thread.sleep nếu có thể kiểm soát trực tiếp qua StepVerifier.

## 19. Các sai lầm thường gặp

| Sai lầm | Tác hại | Cách sửa |
| --- | --- | --- |
| Gọi next trước verify với hot source | Giá trị bị bỏ qua | Dùng then(...) sau subscription hoặc createCold |
| Quên verify | StepVerifier chỉ là builder, test không chạy | Gọi verify/verifyComplete |
| Quên terminal signal | Test có thể treo | complete/error/thenCancel và timeout |
| Gọi emit rồi tiếp tục next | Nguồn đã complete | Dùng next cho chuỗi chưa kết thúc |
| Dùng createCold với giả định hot event | Replay làm sai timing | Chọn factory theo semantics |
| Dùng createColdNonBuffering mà không hiểu overflow | Test fail bất ngờ khi demand thấp | Xem Javadoc và giới hạn request rõ |
| Phát item vượt request trên compliant source | IllegalStateException do test source | Cấp demand hoặc dùng noncompliant khi có chủ đích |
| Dùng assertMinRequested(1) qua publishOn rồi đòi exact demand | Prefetch làm khác request | Kiểm tra contract của operator, không cứng hóa demand tùy ý |
| Dùng TestPublisher để mô phỏng sleep/time | Test chậm/race | Kết hợp virtual time |
| Dùng TestPublisher hot đã error cho retry lần hai | Không có attempt độc lập | Flux.defer/factory mới cho mỗi subscription |
| Dùng noncompliant để che bug | Mất giá trị kiểm thử RS contract | Chỉ bật violation được chỉ rõ |
| Chia sẻ TestPublisher giữa test chạy song song | Race/flaky | Tạo source trong từng @Test |
| Nhầm error với cancellation | Assertion sai lifecycle | Đọc terminal signal và assertCancelled đúng trường hợp |
| Muốn kiểm tra fallback được subscribe nhưng chỉ so value | Không chứng minh đường đi | PublisherProbe hoặc TestPublisher assertion |
| Dùng TestPublisher trong production | Không phù hợp semantics và concurrency | Sinks / adapter / event producer phù hợp |
| Chỉ test success | Bỏ qua lỗi, empty, cancel | Thêm kịch bản negative/terminal |
| Dùng verify() không giới hạn thời gian | Suite có thể treo | verify(Duration) hoặc setDefaultTimeout |

## 20. Checklist trước khi chốt bài test Reactor

Trước khi commit một test sử dụng TestPublisher, hãy trả lời:

1. Test kiểm tra một operator/service behavior cụ thể hay cả hệ thống?
2. Nguồn cần hot hay cold/replay?
3. Đã đặt TestPublisher ở đúng ranh giới dependency chưa?
4. Với nguồn hot, signal có được phát sau subscription không?
5. Đã dùng `then(...)` để sắp xếp signal và expectation theo thứ tự chưa?
6. Request count có cần kiểm tra không; nếu có, đã dùng initial request 0 và `thenRequest` chưa?
7. Có operator prefetch nào làm thay đổi upstream demand không?
8. Đã xác định terminal outcome: complete, error hay cancel?
9. Có timeout cho test không?
10. Nếu test fallback, đã chứng minh fallback subscribe hoặc không subscribe đúng trường hợp chưa?
11. Nếu test retry, publisher có được tạo mới theo mỗi attempt không?
12. Noncompliant source có phục vụ một kịch bản vi phạm quy tắc cụ thể không?
13. Test có phụ thuộc scheduler/Thread.sleep hoặc race không cần thiết không?
14. Đã tách unit test khỏi integration test với DB, WebSocket và HTTP chưa?
15. Các assertion có kiểm tra ý nghĩa nghiệp vụ, không chỉ kiểm tra “không lỗi” không?

## 21. Câu hỏi ôn tập có đáp án

**Câu 1. TestPublisher dùng để làm gì?**

Cho phép tạo Publisher mà test chủ động phát `onNext`, `onComplete`, `onError` và kiểm tra subscription/request/cancel.

**Câu 2. TestPublisher khác StepVerifier như thế nào?**

TestPublisher điều khiển upstream source; StepVerifier mô tả kỳ vọng ở downstream và thực hiện subscription khi verify.

**Câu 3. Hot create() khác cold createCold()?**

Hot chủ yếu gửi sự kiện tới subscriber hiện tại; cold buffer và replay sự kiện cho subscriber, có demand handling.

**Câu 4. next() khác emit()?**

next phát onNext, không terminal. emit phát các giá trị và complete.

**Câu 5. Vì sao nên phát source.next trong StepVerifier.then?**

Để bảo đảm subscriber đã được đăng ký trước khi nguồn hot phát sự kiện, giảm race và mất event.

**Câu 6. Khi nào sử dụng thenRequest(n)?**

Khi cần kiểm tra backpressure hoặc phân phối demand theo từng bước.

**Câu 7. Vì sao assertMinRequested không phải lúc nào cũng bằng thenRequest?**

Operator trung gian có prefetch/buffering và có thể thay đổi cách request upstream.

**Câu 8. Khi nào assertCancelled() thành công?**

Khi publisher từng có subscriber bị cancel, chẳng hạn do take(n), timeout hoặc thenCancel().

**Câu 9. Một Mono.empty được tạo từ TestPublisher ra sao?**

Gọi source.mono() trong pipeline và source.complete() mà không gọi next.

**Câu 10. PublisherProbe có giá trị gì?**

Nó giúp khẳng định một nhánh đã hoặc chưa được subscribe/request/cancel mà không cần tự phát signal.

**Câu 11. REQUEST_OVERFLOW có nghĩa gì?**

Cho phép TestPublisher mô phỏng nguồn phát onNext dù không có đủ request, để thử behavior với nguồn vi phạm Reactive Streams.

**Câu 12. Tại sao retry với một hot TestPublisher đã error có thể sai?**

Retry là resubscribe; một nguồn hot đã terminal không tự tái chạy một attempt mới. Dùng Flux.defer/factory tạo publisher theo từng subscription.

**Câu 13. TestPublisher có an toàn để gọi next đồng thời từ nhiều thread không?**

Javadoc lưu ý nói chung không an toàn cho đa luồng; test bình thường nên điều khiển sequential.

**Câu 14. Khi nào cần virtual time?**

Khi pipeline có timeout/delay/retryBackoff hoặc logic dựa trên Reactor scheduler. TestPublisher riêng không tự tạo virtual clock.

## 22. Tổng kết và tài liệu chính thức

- `TestPublisher` nằm trong `reactor-test` và là Publisher điều khiển bằng tay.
- `create()` hot, `createCold()` cold replay, `createNoncompliant(...)` mô phỏng nguồn sai quy tắc.
- `next` phát value; `emit` phát value rồi complete; `complete` và `error` kết thúc stream.
- `flux()` và `mono()` giúp kết hợp với operator Reactor.
- `StepVerifier.then(...)` phát signal sau khi subscription đã được thiết lập.
- `thenRequest` và `thenCancel` giúp kiểm tra demand/cancellation.
- Assertion trên TestPublisher kiểm tra subscription, requested demand, cancellation và request overflow.
- `PublisherProbe` là lựa chọn gọn nếu chỉ cần kiểm tra execution path.
- Virtual time điều khiển scheduler, không thay thế việc phát signal thủ công.
- Luôn đặt timeout, tránh race, không sử dụng TestPublisher như event bus production.

Tài liệu tham khảo:

1. [Project Reactor — Testing Reference](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier, TestPublisher, PublisherProbe và virtual time.
2. [Reactor TestPublisher Javadoc 3.8.x](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/TestPublisher.html): các factory, signal emission, assertions và Violation.
3. [Reactor StepVerifier Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): then, thenRequest, thenCancel, verify và terminal expectations.
4. [Reactor PublisherProbe Javadoc](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/PublisherProbe.html): subscription, request và cancellation probing.
5. [Project Reactor — Backpressure Reference](https://projectreactor.io/docs/core/release/reference/coreFeatures/simple-ways-to-create-a-flux-or-mono-and-subscribe-to-it.html): request và subscription behavior.
6. [Reactive Streams Specification](https://www.reactive-streams.org/): các quy tắc request(n), onNext, onError, onComplete và cancellation.
7. [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): cách tổ chức và thực thi kiểm thử Java 17.
