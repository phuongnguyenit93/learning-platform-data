# Reactor TestPublisher: Điều khiển dữ liệu và tín hiệu từ phụ thuộc trong kiểm thử Reactive

## 1. Vì sao cần điều khiển nguồn phát thay vì chỉ viết Flux.just(...)?

Khi kiểm thử một service Spring Boot dùng Project Reactor, đầu ra thường là `Mono<T>` hoặc `Flux<T>`. Service đó lại nhận tín hiệu từ repository, Kafka receiver, HTTP client hoặc một publisher khác. Mỗi nguồn có thể:

- Phát một hoặc nhiều `onNext(value)`.
- Hoàn thành bằng `onComplete()` mà không có dữ liệu.
- Lỗi bằng `onError(Throwable)`.
- Chưa phát dữ liệu, chờ request/demand hoặc phản ứng với cancellation.
- Phát tín hiệu theo thời điểm ảnh hưởng đến `take`, `switchIfEmpty`, `onErrorResume` hay toán tử bất đồng bộ.

Nếu dùng `Flux.just("A", "B")`, nguồn sẽ phát dữ liệu xác định theo khi có subscription, phù hợp cho bài test đơn giản. Nhưng có những tình huống bạn cần quyết định **chính xác lúc nào upstream gửi từng tín hiệu** sau khi downstream đã subscribe. Lúc này, `reactor-test` cung cấp **`TestPublisher<T>`**, một publisher điều khiển bằng code.

Khái niệm chính:

> **`TestPublisher` thay một publisher phụ thuộc**, còn pipeline của lớp đang kiểm thử (SUT) phải chạy thật. **`StepVerifier`** subscribe vào pipeline đó, kích hoạt tín hiệu theo kịch bản và xác minh downstream nhận được gì.

Ví dụ tối giản:

~~~java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(
        source.flux().map(String::toUpperCase))
    .then(() -> source.next("hello"))
    .expectNext("HELLO")
    .then(source::complete)
    .verifyComplete();
~~~

Đây là **đoạn minh họa trong một test** với import `TestPublisher`, `StepVerifier` và `String`. Nó cho thấy ba phần: **nguồn điều khiển**, **pipeline thật**, **bộ xác minh**. `then(...)` diễn ra sau khi `StepVerifier` đã subscribe, giúp tránh mất tín hiệu khi dùng hot publisher.

Sau bài này, bạn có thể:

1. Hiểu `TestPublisher.create()`, `createCold()`, `createNoncompliant(...)` và phạm vi phù hợp.
2. Chủ động phát `next`, `emit`, `complete`, `error` từ một dependency giả.
3. Xác minh subscribe, request, cancellation cùng với dữ liệu và terminal signal.
4. Kết hợp `TestPublisher`, `StepVerifier` và interface injection trong unit test Spring Boot/Reactive.
5. Kiểm các nhánh hoàn thành rỗng, lỗi upstream, hủy do `take(n)` và backpressure mà không dùng `Thread.sleep`.
6. Tránh hiểu lầm hot/cold, nguồn không tuân thủ Reactive Streams, thread-safety và giới hạn của unit test so với integration test.

## 2. Đặt TestPublisher vào sơ đồ Reactive Streams

Reactive Streams có bốn hoạt động cơ bản giữa publisher và subscriber:

~~~text
Subscriber                         Publisher
    |                                 |
    |---------- subscribe() ---------->|
    |<--------- onSubscribe ----------|
    |---------- request(n) ----------->|
    |<--------- onNext(value) ---------|
    |<--------- onNext(value) ---------|
    |<--------- onComplete() ----------|   (hoặc onError)
    |
    +----- có thể cancel() trước khi kết thúc
~~~

Theo đặc tả, publisher phải tôn trọng demand và không gửi `onNext` sau terminal signal; `onError` và `onComplete` là các kết thúc loại trừ lẫn nhau. `TestPublisher` thông thường giúp tạo một nguồn phát phục vụ test; chế độ **noncompliant** cố ý cho phép một số vi phạm để thử độ bền downstream.

Hãy nhìn ba vai trò:

~~~text
                      SUT (code chạy THẬT)
TestPublisher ------> normalize/filter/take ------> StepVerifier
   nguồn giả           pipeline nghiệp vụ           subscriber test

  .next(...)          .map(...)                    .expectNext(...)
  .complete()         .filter(...)                 .verifyComplete()
  .error(...)         .onErrorResume(...)          .expectError(...)
                      .take(2)                     .thenCancel()
~~~

`TestPublisher` **không phải tool kiểm HTTP** và **không thay thế WebTestClient**. Nó vận hành ở tầng `Publisher`/`Mono`/`Flux`. Dùng nó để mô phỏng dependency reactive; dùng WebTestClient nếu mục tiêu là routing, status, header, body; dùng repository/database thực khi cần kiểm persistence.

### TestPublisher khác StepVerifier

| Thành phần | Chịu trách nhiệm | Ai điều khiển |
| --- | --- | --- |
| `TestPublisher<T>` | Nguồn phát do test quản lý; ghi nhận subscription/request/cancel | Bài test gọi `next`/`complete`/`error` |
| `StepVerifier` | Subscriber đặt kỳ vọng vào chuỗi tín hiệu **sau SUT** | Bài test mô tả kịch bản và gọi `verify()` |
| `Flux`/`Mono` trong SUT | Toán tử nghiệp vụ thật, chọn nhánh và xử lý tín hiệu | Code ứng dụng |
| `PublisherProbe` | Quan sát source có được subscribe/request/cancel; không nhất thiết cần phát tay | Bài test đọc trạng thái probe |
| `VirtualTimeScheduler`/`withVirtualTime` | Điều khiển thời gian của scheduler để test delay/retry/timeouts | Đồng hồ ảo, không thay `onNext` thủ công |

Chúng bổ sung cho nhau. Một `StepVerifier` không tự tạo dữ liệu cho dependency đang chờ; một `TestPublisher` không tự biết downstream có trả kết quả đúng hay không.

## 3. API TestPublisher cần nhớ

Import:

~~~java
import reactor.test.publisher.TestPublisher;
import reactor.test.StepVerifier;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
~~~

`TestPublisher` nằm trong **artifact `io.projectreactor:reactor-test`**, thuộc **test dependency**. Đừng import nó vào `src/main/java` như một implementation production.

### 3.1 Khởi tạo publisher

~~~java
TestPublisher<String> hot = TestPublisher.create();
TestPublisher<String> cold = TestPublisher.createCold();
~~~

- `create()` tạo **hot TestPublisher**: tín hiệu phát đến các subscribers **đang đăng ký**; dữ liệu phát trước subscription thường không được replay. Terminal signal đầu tiên có thể được replay cho subscriber đến sau.
- `createCold()` tạo **cold TestPublisher có buffer**: các `next` được lưu và có thể phát lại cho các subscribers, tuân thủ backpressure.
- `createColdNonBuffering()` là một biến thể cold phục vụ kiểm trường hợp overflow, **không tương đương** `createCold()` trong chính sách buffer/demand.
- `createNoncompliant(Violation...)` cho phép nguồn hot cố ý **không tuân thủ một số quy tắc** để test downstream có chịu được tình huống xấu không.

### 3.2 Phát tín hiệu

~~~java
hot.next("A");                      // 1 onNext
hot.next("B", "C");                 // nhiều onNext
hot.complete();                     // onComplete

TestPublisher<String> alternative = TestPublisher.create();
alternative.emit("A", "B");         // onNext(A), onNext(B), onComplete()

TestPublisher<String> failing = TestPublisher.create();
failing.error(new IllegalStateException("upstream failed"));
~~~

Các dòng trên là **minh họa độc lập từng publisher**, không phải các dòng thay thế có thể gọi vô điều kiện trên một nguồn đã hoàn thành. Sau terminal signal, đừng tiếp tục phát `next/error/complete` với publisher chuẩn.

`emit(values...)` là viết gọn cho **phát các giá trị rồi complete**. Nếu muốn nguồn còn sống sau item đầu, dùng `next(...)` rồi phát tín hiệu tiếp trong một bước sau. `error(Throwable)` là terminal signal; nó **không phải** exception do test trực tiếp `throw` ra tại dòng gọi khi downstream xử lý bình thường.

### 3.3 Đưa TestPublisher vào pipeline

~~~java
Flux<String> upstreamFlux = hot.flux();
Mono<String> upstreamMono = TestPublisher.<String>create().mono();
~~~

`flux()` và `mono()` là cách đưa publisher test vào API Reactor. Chọn `Flux` cho 0..N items, `Mono` cho tối đa một item. **Không dùng `mono()` để mong giữ nhiều `onNext`**, vì hợp đồng `Mono` chỉ cho tối đa một giá trị.

### 3.4 Quan sát subscriber và demand

Các phương thức quan sát hữu ích:

- `assertWasSubscribed()` / `assertWasNotSubscribed()`: source đã từng có subscription hay chưa.
- `assertWasRequested()` / `assertWasNotRequested()`: source có nhận request/demand hay chưa.
- `assertCancelled()` / `assertNotCancelled()`: nguồn có ghi nhận cancellation hay chưa.
- `assertSubscribers(1)`: ở **thời điểm kiểm tra**, có đúng một subscriber.
- `assertNoSubscribers()`: hiện không còn subscriber.
- `assertMinRequested(n)` / `assertMaxRequested(n)`: kiểm demand của các subscribers hiện có theo semantics API.
- `assertRequestOverflow()` / `assertNoRequestOverflow()`: kiểm có overflow request không.

Một số method `assertWas...` đến từ interface `PublisherProbe` mà `TestPublisher` implement. Chúng có ý nghĩa **lịch sử tương tác**, trong khi `assertSubscribers(n)` kiểm trạng thái **hiện tại**. Đừng kiểm `assertSubscribers(1)` sau khi nguồn complete/cancel nếu subscription đã được đóng.

## 4. Vì sao phải phát dữ liệu bên trong StepVerifier.then(...)?

Với hot publisher:

~~~java
TestPublisher<String> source = TestPublisher.create();
source.next("EARLY");  // Không có subscriber: dữ liệu có thể bị mất.

StepVerifier.create(source.flux())
    .then(() -> source.next("LATE"))
    .expectNext("LATE")
    .then(source::complete)
    .verifyComplete();
~~~

Đây là **minh họa về timing**. Dữ liệu `EARLY` đã phát trước subscription nên không nên được kỳ vọng như một item được phát lại. `StepVerifier.create(...)` chỉ **xây scenario**; việc subscribe thực sự được kích hoạt khi gọi `verify()` / `verifyComplete()`. Khi StepVerifier đi tới `then(...)`, subscription của nó đã được thiết lập.

Dòng thời gian:

~~~text
Test xây scenario                 Thời điểm verify()
  |                                    |
  | create(upstream.flux())             | subscribe
  | then(source.next("A"))             | ----> TestPublisher có subscriber
  | expectNext("A")                    | nhận onNext(A) và assert
  | then(source.complete())             | nhận onComplete
  | verifyComplete()                    | PASS
~~~

**Tránh `Thread.sleep(...)`** để “đợi source subscribe”; đây là nguyên nhân tạo flaky test. `StepVerifier.then(() -> source.assertSubscribers(1))` giúp kiểm subscription đã có ngay trong test. Nếu code SUT chuyển subscription sang scheduler khác, cần hiểu ranh giới bất đồng bộ; không mặc định tất cả operations đều đồng bộ.

### Ba pattern thường dùng

**Pattern A — phát một item rồi hoàn thành:**

~~~java
StepVerifier.create(source.flux().map(String::toUpperCase))
    .then(() -> source.emit("a"))
    .expectNext("A")
    .verifyComplete();
~~~

**Pattern B — phát item, rồi phát lỗi:**

~~~java
StepVerifier.create(source.flux())
    .then(() -> source.next("first"))
    .expectNext("first")
    .then(() -> source.error(new IllegalStateException("failed")))
    .expectError(IllegalStateException.class)
    .verify();
~~~

**Pattern C — kiểm hủy thay vì completion:**

~~~java
StepVerifier.create(source.flux())
    .then(() -> source.next("one"))
    .expectNext("one")
    .thenCancel()
    .verify();

source.assertCancelled();
~~~

Ba pattern này là **các ví dụ test riêng biệt**: khởi tạo một `TestPublisher` mới cho **mỗi** pattern. Không chạy cả ba trên cùng source đã terminate. Các ví dụ đầy đủ ở mục 8 dùng các biến/tên chính xác và runnable.

## 5. Hot, cold, multicast và tín hiệu trước subscription

Đây là phần dễ gây hiểu nhầm nhất khi dùng `TestPublisher`.

### 5.1 Hot TestPublisher: dữ liệu phát theo thời điểm

Với `TestPublisher.create()`, dữ liệu đi tới các subscriber **đã đăng ký tại lúc phát**. Điều này gần với một nguồn sự kiện nóng. Khi bạn gọi `next("A")` trước `verify()`, sự kiện có thể không được nhận bởi test subscriber và scenario chờ `expectNext("A")` sẽ thất bại/treo.

Vì vậy, nếu mục đích là kiểm code lúc đang subscribed, hãy đưa lệnh phát vào `StepVerifier.then(...)`. Nếu mục đích là kiểm replay sau subscription, hãy chọn nguồn cold hoặc operator replay/cache thật theo hợp đồng.

### 5.2 Cold TestPublisher: buffer và phát lại

`TestPublisher.createCold()` buffer các sự kiện và có thể replay chúng cho người subscribe sau:

~~~java
TestPublisher<String> cold = TestPublisher.createCold();
cold.next("A", "B").complete();

StepVerifier.create(cold.flux())
    .expectNext("A", "B")
    .verifyComplete();
~~~

Trong đoạn này, dữ liệu được thiết lập **trước** khi StepVerifier subscribe mà vẫn được nhận vì `cold` lưu và phát lại. Đây là ưu điểm khi muốn xây fixture đơn giản, hoặc kiểm multiple subscribers nhận cùng một sequence. Tuy nhiên, nếu bạn muốn kiểm hành vi phụ thuộc **thời điểm event đến**, hot + `then(...)` thường diễn đạt rõ hơn.

`createCold()` cũng tôn trọng backpressure: nếu subscriber chỉ request một phần tử, nguồn chờ demand tiếp theo thay vì ép tất cả dữ liệu vào downstream.

### 5.3 createColdNonBuffering có ý nghĩa gì?

Tên phương thức dễ bị hiểu lầm là “cold nhưng tuyệt đối không giữ bất kỳ item nào”. Theo Reactor API, nó vẫn có cơ chế lưu/phát lại dữ liệu trong tình huống nhất định, **nhưng thay đổi chính sách khi buffer và demand không tương thích**: có thể báo overflow error nếu request đầu tiên thấp hơn buffer hiện có hoặc subscriber đang nhận thêm item khi không có demand.

Đây là công cụ test nâng cao. Nếu bạn chỉ muốn cold fixture dễ hiểu và tôn trọng demand, chọn `createCold()`; nếu bạn muốn kiểm resilience với nguồn không đệm được khi demand thiếu, đọc kỹ semantics của `createColdNonBuffering()` theo version.

### 5.4 Nhiều subscribers

Một nguồn hot có thể phát cùng lúc cho những subscribers hiện có, nhưng không replay toàn bộ quá khứ cho subscriber đến muộn. Nguồn cold có thể replay buffer cho mỗi subscriber. Nếu ứng dụng thực dùng `share()`, `replay()`, `cache()` hoặc `publish().refCount(...)`, hãy **kiểm trực tiếp operator production đó**, không dựa vào cách `TestPublisher` giả lập là đủ.

TestPublisher cũng **không được thiết kế như một bus thread-safe dùng đa luồng song song mặc định**. Để test concurrency, cần quản lý scheduler, race, subscription và thread-safety cẩn thận; không dùng một singleton TestPublisher chung cho tất cả test methods.

## 6. Signal completion, error và cancellation khác nhau thế nào?

### onComplete

`complete()` cho biết upstream kết thúc **thành công**, có hoặc không có giá trị. Downstream có thể chạy `defaultIfEmpty(...)` hoặc `switchIfEmpty(...)`.

~~~java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(source.flux().switchIfEmpty(Flux.just("fallback")))
    .then(source::complete)
    .expectNext("fallback")
    .verifyComplete();
~~~

Điểm cần test ở đây là **source hoàn thành rỗng**, không phải lỗi. `switchIfEmpty` chỉ chuyển nguồn khi không có `onNext` trước `onComplete`. Nếu source gửi lỗi, nhánh fallback này không tự xử lý lỗi trừ khi code thêm `onErrorResume`.

### onError

`error(new IllegalStateException(...))` mô phỏng upstream lỗi **trong luồng reactive**; nó khác với việc mock một method để method đó `throw` ngay khi được gọi.

~~~java
TestPublisher<String> source = TestPublisher.create();
Flux<String> pipeline = source.flux()
        .onErrorResume(IllegalStateException.class,
                error -> Flux.just("temporary-fallback"));

StepVerifier.create(pipeline)
    .then(() -> source.error(new IllegalStateException("unavailable")))
    .expectNext("temporary-fallback")
    .verifyComplete();
~~~

Ở đây `onErrorResume` nằm trong pipeline thật, và test kiểm branch reactive error. Với lỗi không thuộc loại được xử lý, pipeline có thể tiếp tục `onError`; test cần `expectError(...)`.

**Lưu ý:** Một exception được ném **trước khi tạo Publisher** và một `Mono.error(...)` sau subscription khác thời điểm và đường xử lý. Mockito `thenThrow(...)` trên method tạo publisher có thể làm SUT fail ở mức Java call; còn TestPublisher `error(...)` kiểm reactive terminal path.

### Cancellation

`cancel()` là tín hiệu từ **downstream lên upstream**, thường xảy ra khi subscriber bỏ đăng ký hoặc operator `take(n)` đã nhận đủ n item. Cancellation **không phải** `onComplete` từ source. Ví dụ:

~~~java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(source.flux().take(1))
    .then(() -> source.next("A"))
    .expectNext("A")
    .verifyComplete();

source.assertCancelled();
~~~

Downstream đã hoàn thành vì `take(1)` giới hạn item; upstream bị hủy trước khi source tự gọi `complete()`. Nếu chỉ assert `verifyComplete()` mà không kiểm cancellation, bạn có thể bỏ qua rủi ro resource/subscription vẫn sống.

Không nên mong nguồn làm việc I/O ngoài hệ thống sẽ “rollback mọi side effect” chỉ vì subscriber cancel. Việc cancellation có được phản ánh thành dừng HTTP/JDBC/broker request đúng nghĩa hay không thuộc về adapter thật và cần integration testing khi quan trọng.

## 7. Backpressure: sự khác nhau giữa request(n) và số item đã phát

Trong Reactive Streams, `request(n)` biểu diễn **nhu cầu downstream** đối với tối đa n item. `TestPublisher.createCold()` có thể giữ buffer và chờ demand.

~~~java
TestPublisher<Integer> cold = TestPublisher.createCold();
cold.next(10, 20).complete();

StepVerifier.create(cold.flux(), 0)
    .thenRequest(1)
    .expectNext(10)
    .thenRequest(1)
    .expectNext(20)
    .verifyComplete();
~~~

Giải thích:

1. `StepVerifier.create(cold.flux(), 0)` ban đầu subscribe với **initial request = 0**.
2. `thenRequest(1)` cấp demand một phần tử, nên nhận `10`.
3. Request thêm một phần tử, nhận `20`.
4. Vì cold source đã nhận `complete()` trước đó, khi buffer được tiêu thụ, downstream nhận terminal `onComplete`.

Nếu viết `expectNext(10)` trước khi phát demand đầu tiên, test có thể chờ không bao giờ có item. Một `StepVerifier` với initial request mặc định thường request rất lớn, nên **test không chủ ý hạn chế demand không chứng minh backpressure**.

### TestPublisher.assertMinRequested, assertMaxRequested

Các assertion `assertMinRequested(n)`, `assertMaxRequested(n)` quan sát **demand ở các subscribers hiện tại** theo semantics của `TestPublisher`. Chúng có thể hữu ích để kiểm upstream được request ít nhất/tối đa n trong thời điểm xác định, nhưng phải hiểu request có thể được operator **prefetch/transform**:

- `map` và `filter` có thể làm demand khác với số output.
- `flatMap` có concurrency/prefetch; upstream có thể thấy request lớn hơn số item bạn nghĩ.
- `take`, `limitRate` và `onBackpressure...` ảnh hưởng demand/cancellation.
- `StepVerifier` ban đầu có thể request unbounded; kiểm “exactly 1” khi đã request unbounded sẽ sai mục tiêu.

Nếu yêu cầu chỉ là “hai kết quả đến khi cấp demand hai lần”, test `createCold()` ở trên đã rõ. Chỉ assert request counters khi **request policy chính là điều cần bảo đảm**. Không biến các chi tiết prefetch hợp lệ thành hợp đồng nghiệp vụ không cần thiết.

### Cancellation khi chưa có demand

Một publisher chưa phát gì vẫn có thể được cancel. Có thể dùng:

~~~java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(source.flux(), 0)
    .thenCancel()
    .verify();

source.assertCancelled();
~~~

Đây là bài test kiểm hướng **downstream → upstream**; không cần `next` hoặc `complete`. Nhưng cancellation của một producer fake không chứng minh network socket/database query production chắc chắn bị dừng.

## 8. Ví dụ hoàn chỉnh Java 17+: nguồn sự kiện giả và pipeline nghiệp vụ thật

Bài thực hành sẽ tạo một **SUT thật** nhỏ: `EventPipeline` nhận `EventFeed` trả `Flux<String>`. Pipeline chuẩn hóa văn bản, bỏ phần tử trống và chỉ nhận tối đa `limit` kết quả. Nguồn dữ liệu do TestPublisher cung cấp, vì vậy test tự chọn thời điểm phát, hoàn thành, lỗi và cancellation.

Ví dụ này tự chứa trong **một file Java** để dễ học, không cần Spring ApplicationContext, database, Netty, Docker hay network. Trong dự án thực tế, `EventFeed` và `EventPipeline` phải là implementation/port từ `src/main/java`; test import chính **code production**, không sao chép business implementation vào test rồi coi đó là bằng chứng coverage production.

### 8.1 Cấu trúc thư mục

~~~text
src/
  test/
    java/
      example/
        reactive/
          EventPipelineTest.java
~~~

Yêu cầu: Java 17+, JUnit Jupiter, Reactor Core và `reactor-test` cùng release family tương thích.

### 8.2 File EventPipelineTest.java

~~~java
package example.reactive;

import java.util.Locale;

import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;

@DisplayName("TestPublisher điều khiển dependency Reactive")
class EventPipelineTest {

    interface EventFeed {
        Flux<String> events();
    }

    static final class EventPipeline {
        private final EventFeed feed;

        EventPipeline(EventFeed feed) {
            this.feed = feed;
        }

        Flux<String> normalized(int limit) {
            if (limit <= 0) {
                return Flux.error(
                        new IllegalArgumentException(
                                "limit must be positive"));
            }

            return feed.events()
                    .map(String::trim)
                    .filter(value -> !value.isBlank())
                    .map(value -> value.toUpperCase(Locale.ROOT))
                    .take(limit);
        }
    }

    @Test
    @DisplayName("Tự phát onNext rồi onComplete: transform và filter đúng")
    void emitsNormalizedValuesThenCompletes() {
        TestPublisher<String> source = TestPublisher.create();
        EventPipeline service = new EventPipeline(source::flux);

        StepVerifier.create(service.normalized(5))
                .then(() -> source.assertSubscribers(1))
                .then(() -> source.next("  apple  ", "  ", " banana "))
                .expectNext("APPLE", "BANANA")
                .then(source::complete)
                .verifyComplete();

        source.assertWasSubscribed();
        source.assertWasRequested();
        source.assertNotCancelled();
    }

    @Test
    @DisplayName("Hoàn thành rỗng không sinh item")
    void completesWithoutValues() {
        TestPublisher<String> source = TestPublisher.create();
        EventPipeline service = new EventPipeline(source::flux);

        StepVerifier.create(service.normalized(3))
                .then(source::complete)
                .verifyComplete();
    }

    @Test
    @DisplayName("Giữ item đã nhận rồi chuyển lỗi upstream")
    void propagatesUpstreamError() {
        TestPublisher<String> source = TestPublisher.create();
        EventPipeline service = new EventPipeline(source::flux);

        StepVerifier.create(service.normalized(5))
                .then(() -> source.next(" ok "))
                .expectNext("OK")
                .then(() -> source.error(
                        new IllegalStateException("upstream unavailable")))
                .expectErrorSatisfies(error -> {
                    assertInstanceOf(IllegalStateException.class, error);
                    assertEquals("upstream unavailable", error.getMessage());
                })
                .verify();

        source.assertWasSubscribed();
    }

    @Test
    @DisplayName("take(2) hoàn thành downstream và cancel upstream")
    void takeLimitCancelsSource() {
        TestPublisher<String> source = TestPublisher.create();
        EventPipeline service = new EventPipeline(source::flux);

        StepVerifier.create(service.normalized(2))
                .then(() -> source.next(" one ", " two "))
                .expectNext("ONE", "TWO")
                .verifyComplete();

        source.assertCancelled();
        source.assertWasSubscribed();
    }

    @Test
    @DisplayName("Đầu vào limit sai không subscribe vào dependency")
    void invalidLimitDoesNotSubscribe() {
        TestPublisher<String> source = TestPublisher.create();
        EventPipeline service = new EventPipeline(source::flux);

        StepVerifier.create(service.normalized(0))
                .expectErrorMatches(error ->
                        error instanceof IllegalArgumentException
                        && "limit must be positive"
                                .equals(error.getMessage()))
                .verify();

        source.assertWasNotSubscribed();
    }

    @Test
    @DisplayName("Cold source phát lại dữ liệu đã có trước subscription")
    void coldPublisherReplaysBufferedValues() {
        TestPublisher<String> source = TestPublisher.createCold();
        source.next(" cached ").complete();

        EventPipeline service = new EventPipeline(source::flux);

        StepVerifier.create(service.normalized(5))
                .expectNext("CACHED")
                .verifyComplete();

        source.assertWasSubscribed();
    }

    @Test
    @DisplayName("Cold source tôn trọng request từng phần tử")
    void coldSourceHonorsDemand() {
        TestPublisher<Integer> source = TestPublisher.createCold();
        source.next(10, 20).complete();

        StepVerifier.create(source.flux(), 0)
                .thenRequest(1)
                .expectNext(10)
                .thenRequest(1)
                .expectNext(20)
                .verifyComplete();

        source.assertWasRequested();
    }

    @Test
    @DisplayName("Subscriber chủ động hủy, nguồn ghi nhận cancellation")
    void explicitCancellationIsVisible() {
        TestPublisher<String> source = TestPublisher.create();

        StepVerifier.create(source.flux())
                .then(() -> source.next("first"))
                .expectNext("first")
                .thenCancel()
                .verify();

        source.assertCancelled();
    }
}
~~~

**Có 8 phương thức `@Test`**. Trong cấu hình phù hợp, cả tám **được kỳ vọng PASS**; các test không in stdout. Chúng kiểm **tín hiệu của một pipeline** với upstream do test điều khiển, không chạy web server hoặc gọi hệ thống ngoài.

### 8.3 Đọc từng test đúng nghĩa

| Test | TestPublisher phát gì? | StepVerifier kỳ vọng gì? | Bằng chứng |
| --- | --- | --- | --- |
| `emitsNormalizedValuesThenCompletes` | `next(" apple ", " ", " banana ")`; `complete` | `APPLE`, `BANANA`, complete | Pipeline trim, filter và uppercase |
| `completesWithoutValues` | Chỉ `complete` | Không có item, complete | Kết thúc rỗng không gây output giả |
| `propagatesUpstreamError` | `next(" ok ")`; `error` | `OK` rồi `IllegalStateException` | Lỗi reactive được truyền tiếp |
| `takeLimitCancelsSource` | Hai item, không complete upstream | Hai item rồi downstream complete; upstream cancel | `take(2)` giải phóng subscription |
| `invalidLimitDoesNotSubscribe` | Không phát gì | `IllegalArgumentException`; không subscribe | Validation không lãng phí dependency |
| `coldPublisherReplaysBufferedValues` | Item và complete **trước subscription** | `CACHED`, complete | Cold replay/buffer |
| `coldSourceHonorsDemand` | 10, 20 và complete đã có | Hai request(1) nhận lần lượt hai item | Demand điều khiển lượng nhận |
| `explicitCancellationIsVisible` | Một item | Nhận item rồi cancel | `thenCancel` và upstream recording |

**Vì sao không dùng `Thread.sleep`?** Tín hiệu được phát bởi `then(...)` trong lúc StepVerifier đã subscribe; không cần đoán scheduler chạy xong sau bao nhiêu ms. Khi mã nghiệp vụ thật có `publishOn`/`subscribeOn`, hãy tính đến ranh giới scheduler và dùng cách phối hợp phù hợp để tránh race, không biến sleep thành “sync”.

### 8.4 Mối quan hệ giữa limit và cancellation

Trong ví dụ, `take(limit)` sau khi nhận đủ output hợp lệ sẽ hoàn thành downstream và hủy nguồn upstream. Do có `filter(value -> !value.isBlank())`, nếu nguồn phát `" "` ở giữa, giá trị trắng không tính vào **số item đầu ra** để `take` hoàn thành.

Ví dụ:

~~~text
upstream: onNext(" one ") -> onNext(" ") -> onNext(" two ")
                  |                |                |
          trim -> "one"          ""             "two"
          keep & upper         filter           keep & upper
                  |                                 |
downstream:     "ONE"                            "TWO"
                                                       |
                                                take(2) complete
                                                upstream cancel
~~~

Nếu một implementer vô tình đặt `take(limit)` **trước `filter`**, test với phần tử trắng sẽ bắt lỗi: nguồn có thể bị cắt sau 2 raw items, rồi downstream chỉ còn một output. Đây là ví dụ giá trị thực của test điều khiển **chính xác những item phụ thuộc phát**.

## 9. Thêm dependency vào Spring Boot service mà không tải cả ApplicationContext

Trong ứng dụng, có thể định nghĩa port production:

~~~java
package example.reactive;

import reactor.core.publisher.Flux;

public interface EventFeed {
    Flux<String> events();
}
~~~

Service production nhận port qua constructor, thêm logic Reactor:

~~~java
package example.reactive;

import java.util.Locale;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;

@Service
public class EventService {

    private final EventFeed feed;

    public EventService(EventFeed feed) {
        this.feed = feed;
    }

    public Flux<String> normalized(int max) {
        if (max <= 0) {
            return Flux.error(
                    new IllegalArgumentException("max must be positive"));
        }
        return feed.events()
                .map(String::trim)
                .filter(s -> !s.isBlank())
                .map(s -> s.toUpperCase(Locale.ROOT))
                .take(max);
    }
}
~~~

Hai đoạn trên là **hai file production riêng**; nếu dùng cùng project với `EventPipelineTest.java` tự chứa ở mục 8, tên class/interface không trùng vì một bên là nested test class, một bên là top-level types. Unit test thực tế nên **import `EventService` production** và tạo `new EventService(publisher::flux)`, không test một bản sao service.

Ví dụ test ở mức gọi thật production service (mã minh họa, đặt trong test đã import các type):

~~~java
TestPublisher<String> upstream = TestPublisher.create();
EventService service = new EventService(upstream::flux);

StepVerifier.create(service.normalized(1))
    .then(() -> upstream.next("hello"))
    .expectNext("HELLO")
    .verifyComplete();

upstream.assertCancelled();
~~~

Một lambda/method reference `upstream::flux` đóng vai trò fake implementation của port. **Không cần `@SpringBootTest`** nếu mục tiêu là logic operator và cách SUT phản ứng với tín hiệu upstream.

### Khi cần @SpringBootTest hay @WebFluxTest?

- **Unit test pipeline reactive:** JUnit Jupiter + Reactor Test + fake/mocked port; nhanh và cô lập.
- **WebFlux controller contract:** `@WebFluxTest` + `WebTestClient`, thay service bằng `@MockitoBean` hoặc test configuration theo mục tiêu.
- **Bean wiring, profile, auto-configuration:** `@SpringBootTest` hoặc slice phù hợp.
- **HTTP server thật, R2DBC, Kafka, Redis:** integration test với dependencies/tài nguyên thực sự cần kiểm. `TestPublisher` không chứng minh TCP, database transaction hay message broker hoạt động đúng.

Một mock method trả `Flux.just(...)` thường đủ cho kịch bản đơn giản. Nhưng khi cần chủ động chọn **khi nào service nhận error/complete/cancel**, hãy stub method đó trả `testPublisher.flux()`; chính reactive pipeline trong service mới là phần chạy thật.

Ví dụ Mockito minh họa, không phải file độc lập:

~~~java
EventFeed feed = Mockito.mock(EventFeed.class);
TestPublisher<String> upstream = TestPublisher.create();

Mockito.when(feed.events()).thenReturn(upstream.flux());

EventService service = new EventService(feed);
StepVerifier.create(service.normalized(2))
    .then(() -> upstream.emit("A", "B"))
    .expectNext("A", "B")
    .verifyComplete();
~~~

Nếu service gọi `feed.events()` **khi assemble pipeline** và bạn stub method trả Flux phù hợp, test hoạt động. Nếu contract muốn chứng minh nguồn chỉ được tạo/subscribe khi có downstream subscription, tách kiểm **method invocation** với kiểm **Publisher subscription**; tránh đồng nhất hai thời điểm.

## 10. Bẫy về lazy execution: gọi method khác với subscribe

Với Reactor, thường có ba thời điểm:

1. **Call Java method:** `service.normalized(...)` thực thi thân method, tạo pipeline.
2. **Assembly:** các operator `map/filter/take` xây một `Publisher` có thể lazy.
3. **Subscription:** `StepVerifier.verify()` (hoặc subscriber khác) kích hoạt chuỗi, request và xử lý events.

Code SUT có thể gọi `feed.events()` ở bước 1 để lấy một `Flux`, nhưng source này **chưa chắc đã được subscribe** đến bước 3. Vì vậy:

~~~java
TestPublisher<String> source = TestPublisher.create();
Flux<String> result = source.flux().map(String::trim);

// Chưa có subscription vào result:
// source.assertWasNotSubscribed();

StepVerifier.create(result)
    .then(() -> source.next(" X "))
    .expectNext("X")
    .then(source::complete)
    .verifyComplete();

source.assertWasSubscribed();
~~~

Ở ví dụ, `assertWasSubscribed` kiểm có subscription thật. Nếu test chỉ gọi `result.toString()` hoặc tạo `StepVerifier.create(result)` mà quên `verify()`, bạn chưa thực thi scenario.

**Không dùng `subscribe()` thủ công trong code service** chỉ để test dễ nhìn thấy tín hiệu, trừ khi service thật sự sở hữu lifecycle của một subscription dài hạn và phải quản lý cancel/dispose. Thông thường service trả `Flux` hoặc `Mono` để downstream quyết định khi nào subscribe.

## 11. TestPublisher noncompliant: kiểm downstream trước nguồn xấu

Không phải mọi publisher ngoài đời đều tuân thủ chính xác Reactive Streams. Reactor cho phép một số kịch bản **cố ý vi phạm** để thử operator/custom adapter.

Ví dụ khai báo:

~~~java
import reactor.test.publisher.TestPublisher;

TestPublisher<Integer> noncompliant =
        TestPublisher.createNoncompliant(
                TestPublisher.Violation.REQUEST_OVERFLOW);
~~~

Đây là **đoạn minh họa API**, chưa phải một bài test đầy đủ có assertion. `REQUEST_OVERFLOW` cho phép producer đẩy `onNext` ngay cả khi downstream chưa request đủ. Nó hữu ích để kiểm `onBackpressureDrop`, `onBackpressureBuffer` hoặc custom subscriber, nhưng cần chọn kịch bản cụ thể và biết operator nào đang chịu trách nhiệm điều tiết demand.

Các kiểu vi phạm phổ biến:

| Violation | Ý nghĩa kiểm thử |
| --- | --- |
| `REQUEST_OVERFLOW` | Cho phép phát nhiều item hơn demand hiện có |
| `ALLOW_NULL` | Cho phép phát null trái hợp đồng Reactive Streams thông thường |
| `CLEANUP_ON_TERMINATE` | Nới xử lý terminal signals để tạo kịch bản hoàn tất/lỗi bất thường |
| `DEFER_CANCELLATION` | Tiếp tục phát trong điều kiện cancellation bị bỏ qua/trễ |

**Cẩn trọng:**

- Publisher noncompliant **cố ý sai đặc tả**; không dùng nó như dependency giả mặc định cho mọi test.
- Không suy rằng mọi toán tử Reactor phải ứng xử “đẹp” với mọi vi phạm. Đọc hợp đồng operator và hiểu khả năng phát lỗi/hủy hoặc bỏ qua tín hiệu.
- Một `null` `onNext` có thể làm pipeline `map`/`filter` ném lỗi; đó có thể là phản ứng chính đáng khi nguồn xấu.
- Không dùng các test vi phạm để thay cho kiểm source chuẩn, completion, error và cancellation trong kịch bản bình thường.
- Nếu lỗi thực nằm ở driver/kết nối/adapter ngoài, một unit test noncompliant chỉ là mô phỏng; bổ sung integration test khi cần.

### Test request overflow khác test demand chuẩn

Một bài test demand chuẩn dùng `createCold()` + `StepVerifier.create(source, 0)` + `thenRequest(1)`. Một bài test overflow cố ý vi phạm dùng `createNoncompliant(REQUEST_OVERFLOW)`, phát khi demand = 0, rồi kiểm operator xử lý. **Hai mục tiêu khác nhau**: cái đầu chứng minh producer tôn trọng demand; cái sau kiểm downstream ứng phó producer không tôn trọng demand.

### Test đồng thời không đơn giản chỉ vì có TestPublisher

`TestPublisher` thường không thread-safe khi bị điều khiển đồng thời từ nhiều thread. Nếu cần kiểm race như “cancel đến cùng lúc onNext”, nên dùng các công cụ stress/concurrency phù hợp, lặp lại có kiểm soát và tránh giả định kết quả scheduling chính xác. Một bài test tuần tự với `then(...)` **không chứng minh an toàn trong mọi race thực tế**.

## 12. Khi nào dùng PublisherProbe thay vì TestPublisher?

Có những tình huống không cần phát từng `onNext`, chỉ cần biết một nhánh reactive **đã được subscribe hay chưa**. Ví dụ `switchIfEmpty` chuyển sang fallback:

~~~java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

PublisherProbe<String> fallback =
        PublisherProbe.of(Mono.just("FALLBACK"));

Mono<String> result =
        Mono.<String>empty().switchIfEmpty(fallback.mono());

StepVerifier.create(result)
        .expectNext("FALLBACK")
        .verifyComplete();

fallback.assertWasSubscribed();
fallback.assertWasRequested();
~~~

Đây là **đoạn minh họa trong một phương thức test**. `PublisherProbe` quan sát việc sử dụng một nguồn đã có; bạn không cần gọi `next(...)` thủ công. Với `TestPublisher`, có thể vừa phát tín hiệu vừa quan sát subscribe/request/cancel.

**Quy tắc chọn:**

- Cần kiểm một fallback có được dùng, không cần điều khiển thời điểm phát → `PublisherProbe`.
- Cần phát success/error/complete theo timeline cụ thể → `TestPublisher`.
- Cần kiểm thứ tự item và terminal signal downstream → `StepVerifier`.
- Cần kiểm thời gian delay/retry của operator → `StepVerifier.withVirtualTime(...)` hoặc scheduler kiểm soát.
- Cần kiểm HTTP status/body của controller → `WebTestClient`.

## 13. Virtual time và TestPublisher giải quyết hai vấn đề khác nhau

`TestPublisher` giải quyết **tín hiệu nào xuất hiện và khi nào test chủ động phát**. `StepVerifier.withVirtualTime(...)` giải quyết **clock của scheduler** với các toán tử thời gian như `delayElements`, `timeout`, `retryWhen` có backoff.

Ví dụ không cần TestPublisher:

~~~java
StepVerifier.withVirtualTime(
        () -> Flux.just("A")
                .delayElements(Duration.ofHours(1)))
    .thenAwait(Duration.ofHours(1))
    .expectNext("A")
    .verifyComplete();
~~~

Đoạn minh họa cần import `java.time.Duration`, `Flux` và `StepVerifier`. **Điều rất quan trọng:** tạo các operator thời gian **bên trong lambda của `withVirtualTime`** để chúng sử dụng virtual scheduler đúng cách.

Bạn có thể kết hợp virtual time với upstream do `TestPublisher` điều khiển khi cần kiểm cả data signals và deadlines, nhưng không nên trộn tùy tiện hot publisher có event phát từ thread thật với virtual scheduler nếu chưa hiểu timing. Đối với nhiều nhánh business nhỏ, test có `then(() -> source.next(...))` là đủ và ít phức tạp hơn.

Không dùng `Thread.sleep` trong unit tests chỉ để chờ một giờ logic giả; nó làm suite chậm và flaky. Với HTTP/Kafka/database thật, virtual time của Reactor **không thể tua thời gian của hệ thống ngoài** theo cách thần kỳ; cần kiểm timeout ở adapter phù hợp.

## 14. Gradle và cách chạy ví dụ

Với **Spring Boot 3.5.x + Java 17+** trong một dự án đã có Spring Boot Gradle plugin và dependency management, dependencies cần thiết:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây là **đoạn cấu hình Gradle**, không phải file `build.gradle` độc lập. `spring-boot-starter-test` có thể đã mang theo `reactor-test` theo starter version; khai báo riêng giúp mục đích sử dụng rõ ràng nhưng nên theo BOM Spring Boot và tránh version conflict. Nếu đang làm module chỉ dùng Reactor Core mà không có WebFlux server, có thể thay `spring-boot-starter-webflux` bằng dependency `reactor-core` thích hợp; code mẫu ở mục 8 không cần Spring context.

Chạy một file test:

~~~bash
./gradlew test --tests example.reactive.EventPipelineTest
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests example.reactive.EventPipelineTest
~~~

**Kết quả mong đợi:** có **8 phương thức `@Test`** và tất cả PASS trong môi trường JUnit Jupiter/Reactor tương thích. Test không có `System.out.println(...)`, nên không có stdout chương trình cụ thể; Gradle có thể báo `BUILD SUCCESSFUL` và lưu báo cáo ở `build/reports/tests/test/index.html`. Đây là **kết quả kỳ vọng từ thiết kế test**, không phải bản log của một lần chạy đã xác nhận.

### Nếu lỗi package/import

Đảm bảo các import chính:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;
import org.junit.jupiter.api.Test;
~~~

Không nhầm `reactor.test.publisher.TestPublisher` với `org.reactivestreams.Publisher`. `TestPublisher` là công cụ **chỉ dành cho test**, không dùng làm live event bus của Spring Boot.

### Nếu test bị treo

Thường do thiếu một trong các tín hiệu:

- Kỳ vọng `expectNext(...)` nhưng source chưa `next(...)` sau subscription.
- Kỳ vọng `verifyComplete()` mà source chưa gọi `complete()`, hoặc `take(n)` chưa đủ item.
- Một `StepVerifier.create(source, 0)` chưa có `thenRequest(n)` tương ứng.
- Phát item vào hot source **trước subscription**, dẫn tới mất data.
- Dùng `Flux.never()`/`Mono.never()` trong branch mà không có timeout/cancel.
- Quên gọi `verify()` sau terminal expectation.
- Test async có race do dùng state/thread chưa đồng bộ.

Để tránh chạy vô hạn trong test suite, có thể thêm deadline cho `verify(Duration)` khi dùng terminal expectations, hoặc cấu hình default timeout phù hợp cho StepVerifier và CI. Deadline là **biện pháp chặn hang**, không thay cho kịch bản tín hiệu đã được định nghĩa đúng.

## 15. Những lỗi thiết kế thường gặp

**1. Mock chính pipeline đang cần kiểm.**  
Nếu bạn stub `service.normalized(...)` trả `Flux.just("A")` rồi assert A, test không chạy logic filter/transform/take. Giữ SUT thật; thay dependency `EventFeed` bằng TestPublisher.

**2. Phát dữ liệu hot trước khi subscribe.**  
`source.next("A")` trước `verify()` thường không replay, khiến test chờ A mãi. Đưa emission vào `then(...)` hoặc dùng `createCold()` khi muốn pre-buffer.

**3. Chỉ dùng Flux.just cho mọi kịch bản.**  
Nó tốt cho happy path, nhưng khó mô phỏng “đã subscribe rồi mới lỗi”, “upstream không complete”, hoặc “downstream cancel sau hai item” có kiểm soát. Dùng TestPublisher khi timing của tín hiệu là ý nghĩa test.

**4. Nhầm `complete()` với `error()`.**  
`switchIfEmpty` chỉ hoạt động với empty completion, không phải tất cả lỗi. Viết test riêng cho completion, error và cancellation.

**5. Kiểm trạng thái hiện tại sau khi đã terminate.**  
`assertSubscribers(1)` có thể sai sau completion/cancel; nếu muốn kiểm có subscription từng xảy ra, dùng `assertWasSubscribed()`.

**6. Không phân biệt request với onNext.**  
Subscriber có thể đã subscribe nhưng chưa request; cold publisher tôn trọng demand sẽ giữ dữ liệu. Dùng `thenRequest` và đừng mặc định request ban đầu luôn là 1.

**7. Gọi `block()`/`subscribe()` thủ công trong service để test “thực thi”.**  
Có thể che cancellation/backpressure và phá composition. Trả `Mono`/`Flux`; StepVerifier quản lý subscription.

**8. Không test cancellation.**  
`take(2)` downstream complete là một nửa câu chuyện. Nếu resource subscription phải được đóng, thêm `source.assertCancelled()`.

**9. Dùng `createNoncompliant` làm fixture mặc định.**  
Nó cố ý cho phép hành vi vi phạm Reactive Streams; các failure phát sinh có thể không phản ánh nguồn production bình thường. Dùng khi kiểm resilience cụ thể.

**10. Giả định TestPublisher thread-safe với mọi async scheduler.**  
Nó thường không phù hợp cho concurrent control từ nhiều thread. Dùng nguồn riêng mỗi test, giảm race và kiểm scheduling có ý thức.

**11. Dùng cold fixture để kết luận hot behavior đúng.**  
`createCold()` có replay/buffer; hot event bus production có thể làm mất sự kiện khi subscribe trễ. Chọn nguồn giả có semantics gần mục tiêu.

**12. Tưởng PublisherProbe và TestPublisher là một.**  
Probe quan sát subscription/request/cancel; TestPublisher thêm khả năng phát tay. Không cần dùng TestPublisher khi chỉ muốn kiểm fallback được subscribe.

**13. Dùng StepVerifier như HTTP client.**  
StepVerifier kiểm Publisher, không kiểm HTTP status/header/codec. Dùng WebTestClient cho contract web và integration test phù hợp nếu cần HTTP transport.

**14. Không test nhánh input invalid có subscribe phụ thuộc hay không.**  
Nếu service cần fail-fast, test `assertWasNotSubscribed()` là bằng chứng hữu ích; còn một Java method gọi port khi assembly có thể xảy ra dù chưa subscribe.

**15. Mặc định cancellation chắc chắn hủy mọi I/O/transaction.**  
Subscriber cancel là tín hiệu cho chuỗi reactive; external side effects đã xảy ra không tự rollback. Kiểm adapter/database/broker thật khi hợp đồng phụ thuộc hành vi đó.

## 16. Quy trình chọn và viết một test TestPublisher

1. **Xác định SUT thật:** service/operator nhận `Mono`/`Flux` từ dependency.
2. **Chọn điểm seam:** interface hoặc function trả `Publisher`, không giả toàn bộ lớp đang kiểm.
3. **Liệt kê các tín hiệu cần điều khiển:** item, completion rỗng, error, cancellation, demand thiếu.
4. **Chọn hot hay cold:** hot khi muốn event theo thời điểm; cold khi muốn pre-buffer/replay và backpressure.
5. **Dựng pipeline trước:** ví dụ `Flux<String> result = service.normalized(2)`.
6. **Đặt kịch bản StepVerifier:** input/expected output và terminal expectation theo thứ tự.
7. **Phát trong `then(...)`** nếu dùng hot source, sau khi subscriber có mặt.
8. **Kết thúc rõ:** `complete`, `error`, `take` hoặc `thenCancel`; không chờ vô hạn.
9. **Assert source interaction:** `assertWasSubscribed`, `assertWasRequested`, `assertCancelled` khi thuộc hợp đồng.
10. **Kiểm nguồn phụ thuộc bị lỗi và empty:** không chỉ happy path.
11. **Đánh giá ranh giới test:** source fake không chứng minh HTTP/DB/Kafka production hoạt động.
12. **Chạy lặp lại trên CI:** tránh state dùng chung, sleep, race và test phụ thuộc timing không kiểm soát.

### Checklist cuối cùng

- [ ] `TestPublisher` nằm ở test source, có dependency `reactor-test` tương thích.
- [ ] Pipeline nghiệp vụ thật được gọi, không bị mock thay.
- [ ] Dữ liệu hot được phát **sau khi subscription đã xảy ra**, thường dùng `then(...)`.
- [ ] Có test `onNext`, `onComplete` và `onError` theo yêu cầu nghiệp vụ.
- [ ] Khi dùng `take` hoặc `thenCancel`, kiểm cancellation upstream nếu việc hủy là quan trọng.
- [ ] Với cold source, hiểu buffer/replay và request(n).
- [ ] Không dùng `createNoncompliant` trừ khi thực sự kiểm tình huống nguồn vi phạm đặc tả.
- [ ] Không nhầm `TestPublisher` với `PublisherProbe`, `WebTestClient` hoặc `VirtualTimeScheduler`.
- [ ] Test không chờ timeout do quên complete/error/request.
- [ ] Không chia sẻ TestPublisher mutable giữa các test methods/threads.
- [ ] Chỉ assert demand/prefetch khi đó là hợp đồng của operator hoặc adapter.
- [ ] Nếu SUT có external side effects, có integration test riêng cho cancellation/rollback/driver behavior.
- [ ] Test có import, version, file path phù hợp Java 17+/JUnit Jupiter và dùng Gradle `useJUnitPlatform()`.

**Tổng kết:** `TestPublisher` giúp kiểm soát **nguồn phát** — từ `onNext` đến `onComplete`/`onError` — để test phản ứng của pipeline reactive thật. `StepVerifier` đóng vai subscriber và kiểm chuỗi kết quả. Khi hiểu rõ **hot/cold, thời điểm subscribe, demand và cancellation**, bạn có thể viết test nhanh, tái hiện được những kịch bản khó mà không dựa vào `Thread.sleep` hoặc hệ thống ngoài.

### Tài liệu tham khảo chính thức

- [Project Reactor Reference — Testing](https://projectreactor.io/docs/core/release/reference/testing.html): `StepVerifier`, `TestPublisher`, `PublisherProbe` và virtual time.
- [Reactor TestPublisher API](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/TestPublisher.html): `create`/`createCold`/`createNoncompliant`, `next`/`emit`/`complete`/`error` và các assertion.
- [Reactor StepVerifier API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): `then`, `thenRequest`, `expectNext`, `expectError`, `thenCancel` và `verify`.
- [Reactor PublisherProbe API](https://projectreactor.io/docs/test/release/api/reactor/test/publisher/PublisherProbe.html): quan sát subscribe/request/cancel.
- [Reactive Streams Specification](https://www.reactive-streams.org/): hợp đồng demand, signals và cancellation.
- [Spring WebFlux Reference](https://docs.spring.io/spring-framework/reference/web/webflux.html): ứng dụng reactive và cách tích hợp HTTP.
