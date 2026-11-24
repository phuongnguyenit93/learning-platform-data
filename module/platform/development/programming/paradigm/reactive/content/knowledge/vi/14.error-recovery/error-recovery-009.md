# Thời gian chờ, hủy đăng ký và chính sách phục hồi

## Vì sao cần thiết kế cả timeout, cancellation và recovery?

Một pipeline reactive thường gọi dịch vụ từ xa, truy vấn cơ sở dữ liệu, đọc message broker hoặc chờ một nguồn sự kiện. Những thao tác này có thể chậm, treo, thất bại tạm thời hoặc không còn cần thiết khi người dùng rời khỏi màn hình. Nếu chỉ xử lý trường hợp thành công và lỗi thông thường, ứng dụng có thể giữ tài nguyên quá lâu, retry không kiểm soát hoặc tiếp tục làm việc sau khi kết quả không còn giá trị.

Trong Project Reactor, ba cơ chế liên quan nhưng có mục đích khác nhau:

- **Timeout** đặt giới hạn thời gian chờ. Khi không nhận được tín hiệu cần thiết trong khoảng thời gian quy định, pipeline chuyển sang nhánh lỗi hoặc publisher dự phòng.
- **Cancellation** cho biết subscriber hoặc toán tử không còn cần dữ liệu. Yêu cầu hủy được truyền ngược về nguồn để dừng việc phát và giải phóng tài nguyên khi có thể.
- **Recovery** quyết định ứng dụng phản ứng ra sao khi có lỗi: thử lại, dùng dữ liệu dự phòng, chuyển sang nguồn khác hoặc truyền lỗi lên tầng gọi.

Ba cơ chế này phải phối hợp với nhau. Timeout thường hủy subscription upstream rồi phát lỗi timeout xuống dưới. Retry có thể đăng ký lại nguồn sau lỗi đó. Ngược lại, cancellation do người gọi chủ động không phải lỗi; nó không nên kích hoạt retry hay fallback như thể thao tác vừa thất bại.

## Phân biệt tín hiệu lỗi và hủy subscription

Reactive Streams có hai kiểu kết thúc bằng tín hiệu: `onComplete()` cho hoàn tất bình thường và `onError(error)` cho kết thúc do lỗi. Cancellation là một lệnh điều khiển đi ngược từ subscriber về publisher thông qua `Subscription.cancel()`; nó không phải tín hiệu kết thúc được phát xuống subscriber.

Trong Reactor, các overload `subscribe(...)` thường trả về `Disposable`. Gọi `dispose()` yêu cầu hủy subscription:

```java
import java.time.Duration;
import reactor.core.Disposable;
import reactor.core.publisher.Flux;

Disposable subscription = Flux.interval(Duration.ofMillis(250))
    .subscribe(tick -> System.out.println("Tick: " + tick));

// Khi thành phần sở hữu luồng không còn cần dữ liệu:
subscription.dispose();
```

Sau khi bị hủy, subscriber không nhận thêm `onNext`, `onComplete` hay `onError` từ subscription đó. Vì cancellation không phải lỗi, các toán tử `onErrorResume` và `retryWhen` không được kích hoạt chỉ vì người gọi gọi `dispose()`.

Có thể quan sát cancellation và mọi kiểu kết thúc bằng các toán tử lifecycle:

```java
import java.time.Duration;
import reactor.core.publisher.Flux;
import reactor.core.publisher.SignalType;

Flux<Long> ticks = Flux.interval(Duration.ofMillis(200))
    .doOnCancel(() -> System.out.println("Nguồn nhận yêu cầu hủy"))
    .doFinally(signal -> {
        if (signal == SignalType.CANCEL) {
            System.out.println("Kết thúc do cancellation");
        }
    });
```

`doOnCancel` chỉ quan sát việc hủy. `doFinally` chạy sau khi pipeline kết thúc và cho biết loại tín hiệu cuối cùng như `ON_COMPLETE`, `ON_ERROR` hoặc `CANCEL`. `doOnTerminate` không thay thế được `doFinally` khi cần quan sát cancellation, vì hủy không phải tín hiệu terminal được gửi xuống.

## Đặt giới hạn thời gian bằng timeout

### Timeout cho Mono

`Mono.timeout(Duration)` đặt giới hạn cho thời gian chờ tín hiệu từ publisher. Nếu `Mono` không phát giá trị hoặc tín hiệu kết thúc trong khoảng thời gian đó, Reactor hủy subscription upstream và phát lỗi timeout xuống downstream.

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;

Mono<Profile> profile = profileClient.findById(userId)
    .timeout(Duration.ofSeconds(2))
    .onErrorResume(TimeoutException.class, error -> profileCache.findById(userId));
```

Nếu dịch vụ hồ sơ không phản hồi trong hai giây, subscription đến dịch vụ bị hủy và pipeline chuyển sang đọc cache. Nếu cache cũng rỗng hoặc lỗi, kết quả đó tiếp tục được truyền xuống. Fallback cần có ý nghĩa nghiệp vụ rõ ràng; không nên trả dữ liệu cũ mà không cho tầng gọi biết đó là dữ liệu dự phòng nếu tính mới của dữ liệu quan trọng.

### Timeout cho Flux

Với `Flux`, `timeout(Duration)` thường giới hạn khoảng thời gian chờ giữa các tín hiệu. Nếu nguồn không phát tín hiệu tiếp theo trong khoảng thời gian quy định, toán tử timeout hủy nguồn và phát lỗi. Cơ chế này hữu ích cho luồng sự kiện cần có heartbeat hoặc dữ liệu đến đều đặn:

```java
import java.time.Duration;
import reactor.core.publisher.Flux;

Flux<Quote> quotes = marketFeed.streamQuotes(symbol)
    .timeout(Duration.ofSeconds(5));
```

Nếu không có quote hoặc tín hiệu tiếp theo trong năm giây, luồng phát lỗi timeout. Nếu nguồn hoàn tất trước thời hạn, pipeline hoàn tất bình thường. Với luồng dữ liệu không có yêu cầu về nhịp phát đều, cần cân nhắc liệu timeout giữa các phần tử có thật sự phù hợp hay không; một nguồn hợp lệ nhưng yên lặng lâu có thể bị xem nhầm là lỗi.

### Timeout với publisher dự phòng

Có thể truyền publisher dự phòng trực tiếp cho `timeout`. Khi hết thời gian, Reactor hủy nguồn chính và chuyển sang publisher thay thế:

```java
import java.time.Duration;
import reactor.core.publisher.Mono;

Mono<ExchangeRate> rate = exchangeClient.fetch("USD", "VND")
    .timeout(
        Duration.ofSeconds(2),
        Mono.defer(() -> exchangeCache.findLatest("USD", "VND"))
    );
```

Trong ví dụ này, timeout không còn được phát như lỗi nếu publisher cache hoàn tất bình thường; subscriber nhận kết quả cache. Nếu publisher dự phòng phát lỗi, lỗi từ nhánh dự phòng được truyền xuống. Nếu publisher dự phòng rỗng, kết quả cuối cùng có thể hoàn tất rỗng.

Điều này khác với `timeout(...).onErrorResume(...)`: dạng đầu tiên chọn publisher thay thế ngay trong toán tử timeout, còn dạng thứ hai nhận lỗi timeout rồi quyết định phục hồi bằng một toán tử riêng. Dạng `onErrorResume` linh hoạt hơn khi cần phân biệt timeout với các loại lỗi khác.

## Timeout từng lần thử và deadline tổng

Khi kết hợp timeout với retry, cần quyết định giới hạn thời gian áp dụng cho mỗi lần gọi hay cho toàn bộ quy trình. Hai cách đặt toán tử có ý nghĩa khác nhau.

```java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

Mono<Response> perAttemptTimeout = Mono.defer(() -> remoteClient.call())
    .timeout(Duration.ofSeconds(2));

Mono<Response> retried = perAttemptTimeout.retryWhen(
    Retry.backoff(2, Duration.ofMillis(200))
        .maxBackoff(Duration.ofSeconds(1))
);

Mono<Response> withTotalDeadline = retried.timeout(Duration.ofSeconds(5));
```

`timeout` bên trong áp dụng cho từng lần gọi. `Retry.backoff(2, ...)` cho phép tối đa hai lần thử lại sau lần đầu, tức tối đa ba lần gọi nguồn. Timeout bên ngoài đặt deadline cho cả chuỗi retry và thời gian backoff. Nếu tổng thời gian vượt năm giây, deadline ngoài hủy chuỗi retry đang chạy và phát lỗi timeout.

Nếu chỉ đặt timeout bên trong rồi retry, tổng thời gian có thể dài hơn nhiều so với timeout của một lần gọi vì mỗi lần thử có thời hạn riêng và còn có khoảng backoff. Nếu chỉ đặt timeout bên ngoài, một lần gọi đầu tiên có thể chiếm phần lớn deadline và không còn thời gian cho retry. Trong hệ thống có ngân sách độ trễ rõ ràng, thường cần cả timeout mỗi lần thử lẫn deadline tổng.

Timeout ở tầng ứng dụng cũng nên tương thích với timeout của HTTP client, driver cơ sở dữ liệu, load balancer và dịch vụ đích. Nếu tầng thấp hơn đã có timeout ngắn hơn, lỗi có thể đến từ tầng đó trước khi Reactor timeout kích hoạt. Hãy xác định timeout nào đang kiểm soát kết nối, chờ phản hồi, đọc dữ liệu và toàn bộ request để tránh cấu hình chồng chéo khó giải thích.

## Cancellation truyền ngược để dừng công việc không còn cần thiết

Cancellation hữu ích khi người dùng rời khỏi trang, request HTTP từ client bị ngắt, một kết quả mới thay thế kết quả cũ hoặc một toán tử đã có đủ dữ liệu. Các toán tử như `take`, `next`, `switchMap` và timeout có thể hủy subscription upstream trong những điều kiện tương ứng.

Ví dụ, `switchMap` hủy publisher con trước khi chuyển sang publisher con được tạo từ giá trị mới:

```java
import reactor.core.publisher.Flux;

Flux<SearchResult> results = searchTerms
    .switchMap(term -> searchClient.search(term));
```

Khi người dùng nhập từ khóa mới, kết quả tìm kiếm cũ không còn cần thiết. `switchMap` hủy nhánh tìm kiếm trước và đăng ký nhánh mới. Điều này giúp tránh tiếp tục tiêu thụ kết quả lỗi thời, nhưng hiệu quả dừng request bên ngoài phụ thuộc `searchClient` có hỗ trợ cancellation hay không.

Cancellation cũng có thể phát sinh khi `take(10)` đã nhận đủ mười phần tử, khi `Mono.firstWithSignal` đã chọn được nguồn thắng hoặc khi subscriber gọi `dispose()`. Hãy xem cancellation là một phần bình thường của vòng đời pipeline, không phải sự cố cần ghi log ở mức lỗi.

### Hủy không bảo đảm tác vụ bên ngoài dừng tức thì

Reactor có thể truyền cancellation đến publisher upstream, nhưng publisher đó phải liên kết việc hủy với tài nguyên hoặc API bên ngoài. Nếu một adapter chỉ bỏ qua tín hiệu sau khi hủy mà không dừng socket, listener hoặc truy vấn đang chạy, công việc vật lý vẫn có thể tiếp tục.

Đối với nguồn callback tự tạo bằng `Flux.create`, gắn cleanup với `FluxSink.onCancel` hoặc `onDispose` để tháo listener và dừng nguồn. Với tài nguyên đồng bộ có thao tác đóng, cân nhắc `using`; với cleanup bất đồng bộ, dùng `usingWhen` để xử lý riêng hoàn tất, lỗi và cancellation.

Một lời gọi blocking đang chạy trên thread cũng có thể không dừng ngay khi subscription bị hủy. Nếu API không hỗ trợ interruption hoặc cancellation, timeout chỉ giúp pipeline ngừng chờ và bỏ qua kết quả về sau; nó không thể tự biến thao tác blocking thành I/O không chặn. Cần chọn driver reactive hoặc cơ chế hủy của thư viện bên dưới, và cô lập tác vụ blocking trên scheduler phù hợp khi chưa thể thay thế API.

## Thử lại có kiểm soát

Retry tạo subscription mới đến publisher upstream khi publisher phát lỗi. Nó không tiếp tục từ đúng lệnh bị lỗi trong cùng một lần chạy; nguồn được đăng ký lại và có thể thực hiện lại toàn bộ side effect từ đầu.

`retry(3)` cho phép tối đa ba lần retry sau lần đăng ký ban đầu, tức có thể có tối đa bốn lần thực thi. Dạng retry không giới hạn có thể khiến dịch vụ lỗi bị gọi liên tục, giữ request lâu và khuếch đại sự cố. Trong ứng dụng thực tế, hãy đặt giới hạn, backoff và điều kiện lọc lỗi.

```java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

Mono<Catalog> catalog = Mono.defer(() -> catalogClient.loadCatalog())
    .retryWhen(
        Retry.backoff(3, Duration.ofMillis(200))
            .maxBackoff(Duration.ofSeconds(3))
            .jitter(0.5)
            .filter(this::isTransientFailure)
            .doBeforeRetry(signal ->
                logger.warn("Thử lại tải catalog, lần {}", signal.totalRetries() + 1,
                    signal.failure()))
    );
```

Chính sách trên cho phép tối đa ba lần retry, với khoảng chờ tăng dần từ 200 mili giây đến tối đa ba giây và jitter để tránh nhiều client thử lại cùng thời điểm. `filter` chỉ cho phép retry lỗi được xác định là tạm thời. `Mono.defer` làm rõ rằng lời gọi tạo publisher được thực hiện lại cho mỗi subscription; bản thân publisher từ client cũng cần hỗ trợ việc đăng ký lại an toàn.

Không nên retry tự động mọi lỗi. Các lỗi xác thực, dữ liệu không hợp lệ, thiếu quyền hoặc vi phạm quy tắc nghiệp vụ thường không tự biến mất sau vài lần gọi. Retry những lỗi này chỉ làm tăng tải và kéo dài thời gian phản hồi.

### Phân biệt lỗi tạm thời và lỗi không thể phục hồi

Một chính sách retry thường phân loại lỗi theo nguyên nhân:

| Nhóm lỗi | Hướng xử lý thường phù hợp |
|---|---|
| Timeout hoặc mất kết nối tạm thời | Có thể retry giới hạn với backoff nếu thao tác an toàn khi lặp |
| HTTP 429 hoặc giới hạn tốc độ | Tôn trọng `Retry-After` nếu có, giảm tốc độ và retry có giới hạn |
| HTTP 5xx từ dịch vụ phụ | Có thể retry một số mã lỗi tùy hợp đồng dịch vụ |
| HTTP 400, dữ liệu sai định dạng | Không retry nếu cùng request luôn tạo cùng lỗi |
| HTTP 401/403 | Sửa xác thực hoặc quyền; retry mù thường không hữu ích |
| Không tìm thấy tài nguyên theo nghiệp vụ | Chuyển sang nhánh empty hoặc lỗi nghiệp vụ tùy hợp đồng |
| Cancellation do caller | Dừng; không retry |

Danh sách này chỉ là hướng dẫn. Hãy dựa vào hợp đồng của API và phân loại exception cụ thể, không chỉ dựa vào tên lớp hoặc mã lỗi tổng quát.

## Retry có thể lặp side effect

Retry đặc biệt nhạy cảm với thao tác ghi. Giả sử client gửi lệnh tạo thanh toán; dịch vụ đích đã xử lý thành công nhưng phản hồi bị mất trên đường truyền. Từ phía client, request có vẻ timeout. Nếu retry bằng một request mới, dịch vụ có thể tạo thanh toán thứ hai.

Với thao tác có side effect, cần bảo đảm tính idempotent trước khi retry. Các biện pháp thường dùng gồm:

- Gửi idempotency key ổn định cho cùng một thao tác nghiệp vụ để dịch vụ đích nhận diện request lặp.
- Dùng mã giao dịch hoặc khóa duy nhất ở cơ sở dữ liệu để ngăn ghi trùng.
- Phân biệt trạng thái “chưa biết kết quả” với “thất bại chắc chắn”; sau timeout có thể cần truy vấn trạng thái giao dịch trước khi gửi lại.
- Chỉ retry lỗi và thao tác được xác định an toàn theo hợp đồng.

Ví dụ, idempotency key phải được tạo một lần bên ngoài `defer` để mọi lần thử dùng cùng khóa:

```java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

String idempotencyKey = request.idempotencyKey();

Mono<PaymentReceipt> payment = Mono.defer(() ->
    paymentClient.charge(request, idempotencyKey)
).retryWhen(
    Retry.backoff(2, Duration.ofMillis(300))
        .filter(this::isRetryablePaymentFailure)
);
```

Nếu tạo khóa mới trong mỗi lần retry, dịch vụ đích có thể xem mỗi lần thử là một thanh toán khác. Idempotency key phải đại diện cho cùng một ý định nghiệp vụ và được dịch vụ nhận request thực sự lưu/kiểm tra.

## Chọn fallback sau khi retry thất bại

Sau khi đã thử lại theo chính sách, ứng dụng có thể chuyển sang dữ liệu cache, giá trị mặc định hoặc lỗi nghiệp vụ rõ ràng. Đặt `onErrorResume` sau `retryWhen` nếu muốn fallback chỉ chạy sau khi các lần retry đã cạn:

```java
Mono<Configuration> configuration =
    Mono.defer(() -> configClient.load())
        .timeout(Duration.ofSeconds(1))
        .retryWhen(Retry.backoff(2, Duration.ofMillis(150))
            .filter(this::isTransientFailure))
        .onErrorResume(error -> {
            logger.warn("Không tải được cấu hình mới, dùng cache", error);
            return configCache.loadLastKnownGood();
        });
```

Nếu đặt `onErrorResume` trước `retryWhen` và fallback biến lỗi thành một giá trị bình thường, retry phía sau sẽ không còn thấy lỗi để thử lại. Thứ tự toán tử vì vậy là một phần của chính sách phục hồi.

Không phải lúc nào fallback cũng nên che lỗi. Nếu cache không có dữ liệu, cấu hình mặc định có thể không an toàn hoặc nghiệp vụ yêu cầu dữ liệu mới nhất, hãy để lỗi truyền đến tầng gọi để trả mã trạng thái phù hợp hoặc yêu cầu thao tác khác.

### Timeout có fallback và retry

Hai dạng dưới đây khác nhau:

```java
import java.time.Duration;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

// Timeout trở thành lỗi, sau đó có thể được retry:
Mono<Data> retryOnTimeout = source
    .timeout(Duration.ofSeconds(1))
    .retryWhen(Retry.max(2));

// Timeout chuyển sang fallback bình thường, nên retry phía sau không chạy nếu fallback thành công:
Mono<Data> fallbackOnTimeout = source
    .timeout(Duration.ofSeconds(1), cachedData);
```

Nếu cần retry trước rồi mới dùng cache, đặt fallback sau retry. Nếu chủ ý dùng cache ngay khi một lần thử vượt thời gian, hãy dùng fallback trong timeout. Hãy chọn theo ngân sách độ trễ và yêu cầu mới của dữ liệu.

## Kết hợp timeout, retry và fallback theo ngân sách

Một quy trình gọi dịch vụ thường có ba tầng quyết định:

1. Timeout mỗi lần thử để không giữ một request đơn lẻ quá lâu.
2. Retry giới hạn cho lỗi tạm thời, với backoff và jitter.
3. Deadline tổng để giới hạn toàn bộ chuỗi, bao gồm các lần thử và thời gian chờ giữa chúng; nếu hết deadline, chuyển sang fallback hoặc báo lỗi.

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;
import reactor.util.retry.Retry;

Mono<Report> loadReport(String reportId) {
    Mono<Report> oneAttempt = Mono.defer(() -> reportClient.fetch(reportId))
        .timeout(Duration.ofSeconds(2));

    return oneAttempt
        .retryWhen(Retry.backoff(2, Duration.ofMillis(200))
            .maxBackoff(Duration.ofSeconds(1))
            .filter(this::isTransientFailure))
        .timeout(Duration.ofSeconds(5))
        .onErrorResume(TimeoutException.class, error ->
            reportCache.findLastSuccessful(reportId));
}
```

Trong ví dụ, mỗi request tối đa hai giây; chuỗi có tối đa hai lần retry; deadline tổng là năm giây. Khi deadline tổng hết, subscription retry đang chạy bị hủy. Fallback cache chỉ xử lý lỗi timeout tổng; các lỗi khác vẫn truyền xuống. Nếu muốn fallback cho mọi lỗi đã retry hết, dùng một `onErrorResume` không giới hạn kiểu lỗi nhưng phải quyết định rõ lỗi nào có thể thay bằng dữ liệu cache.

## Quan sát timeout, retry và cancellation

Để chẩn đoán chính sách phục hồi, nên ghi nhận số lần thử, loại lỗi, thời gian mỗi lần, tổng thời gian, việc chuyển sang fallback và lý do subscription kết thúc. Có thể dùng `doOnSubscribe`, `doOnError`, `doOnCancel` và `doFinally` ở những vị trí phù hợp:

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;

Mono<Response> observed = Mono.defer(() -> remoteClient.call())
    .doOnSubscribe(ignored -> metrics.increment("remote.attempt"))
    .timeout(Duration.ofSeconds(2))
    .doOnError(TimeoutException.class,
        error -> metrics.increment("remote.timeout"))
    .doOnCancel(() -> metrics.increment("remote.cancelled"))
    .doFinally(signal -> logger.debug("Remote pipeline kết thúc: {}", signal));
```

Đặt phép đo trước hay sau retry sẽ cho số liệu khác nhau. `doOnSubscribe` trước retry quan sát từng lần đăng ký upstream nếu nằm trong publisher được đăng ký lại; đặt sau retry có thể chỉ quan sát subscription đến publisher retry tổng thể. Hãy đặt metric ở đúng ranh giới mà bạn muốn đo và dùng correlation ID để liên kết các lần thử thuộc cùng một request nghiệp vụ.

Không ghi log cancellation như lỗi hệ thống ở mức ERROR. Người dùng rời trang hoặc request phía client bị ngắt có thể là hành vi bình thường. Ngược lại, timeout của một request vẫn còn được người dùng chờ có thể cần metric và cảnh báo nếu tỷ lệ tăng cao.

## Kiểm thử timeout và cancellation

Reactor Test cung cấp `StepVerifier` và virtual time để kiểm tra hành vi thời gian mà không phải chờ đồng hồ thật. Ví dụ sau xác nhận một `Mono` chậm bị timeout:

```java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(10))
            .timeout(Duration.ofSeconds(2)))
    .thenAwait(Duration.ofSeconds(2))
    .expectError(TimeoutException.class)
    .verify();
```

`withVirtualTime` tạo publisher sau khi virtual scheduler đã được cài đặt. Khi thời gian ảo tiến đến hai giây, timeout phát lỗi mà không cần chờ mười giây thực tế.

Có thể kiểm tra cancellation được truyền lên nguồn bằng `doOnCancel`:

```java
import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

AtomicBoolean cancelled = new AtomicBoolean();

Flux<Long> source = Flux.interval(Duration.ofMillis(100))
    .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(source.take(1))
    .expectNext(0L)
    .verifyComplete();

assert cancelled.get();
```

`take(1)` hoàn tất phía downstream sau phần tử đầu tiên và hủy nguồn interval. Kiểm thử xác nhận nguồn nhận được cancellation. Với adapter I/O thật, cần kiểm tra thêm rằng request, listener hoặc resource bên ngoài đã được đóng/hủy, không chỉ kiểm tra cờ trong pipeline.

## Những lỗi thiết kế thường gặp

- **Dùng timeout quá ngắn:** request hợp lệ bị hủy liên tục, làm tăng retry và tải hệ thống. Chọn timeout theo phân phối độ trễ, SLA và ngân sách tổng.
- **Chỉ có timeout mỗi lần thử mà không có deadline tổng:** nhiều lần retry và backoff có thể kéo dài request vượt thời gian người dùng chấp nhận.
- **Retry không giới hạn:** một dịch vụ đang lỗi bị gọi liên tục và sự cố lan rộng. Dùng giới hạn, backoff, jitter và lọc lỗi.
- **Retry thao tác ghi không idempotent:** timeout có thể xảy ra sau khi dịch vụ đã xử lý request, dẫn đến side effect trùng lặp.
- **Xem cancellation như onError:** `dispose()` không kích hoạt `retryWhen` hoặc `onErrorResume`; cancellation cần được xử lý bằng lifecycle hook và cleanup.
- **Cho rằng timeout dừng chắc chắn tác vụ vật lý:** adapter hoặc API blocking có thể không hỗ trợ cancellation. Cần kiểm tra hành vi của client/driver.
- **Fallback trước retry:** fallback biến lỗi thành kết quả bình thường nên retry phía sau không được kích hoạt.
- **Dùng cache không kiểm soát:** dữ liệu dự phòng có thể cũ, sai tenant hoặc không còn hợp lệ. Xác định TTL và phạm vi cache.
- **Không đo số lần thử và lý do kết thúc:** khó phân biệt lỗi gốc, timeout mỗi lần, deadline tổng và cancellation bình thường.

## Quy trình xây dựng chính sách phục hồi

Khi thiết kế một lời gọi reactive đến dịch vụ bên ngoài, hãy xác định độ trễ tối đa cho một lần thử và deadline tổng mà nghiệp vụ chấp nhận. Chọn timeout phù hợp với loại nguồn; với luồng sự kiện dài hạn, chỉ dùng timeout giữa các tín hiệu nếu nguồn thực sự phải phát đều hoặc có heartbeat.

Tiếp theo, phân loại lỗi có thể retry, đặt số lần thử tối đa cùng backoff/jitter và xác nhận thao tác có an toàn khi lặp. Đặt fallback sau retry nếu chỉ muốn dùng dữ liệu dự phòng khi các lần thử đã cạn. Bảo đảm cancellation được truyền đến client và tài nguyên nguồn, đồng thời không biến cancellation bình thường thành lỗi.

Cuối cùng, đo thời gian, số lần thử, tỷ lệ timeout, fallback và cancellation; kiểm thử bằng virtual time cùng các nguồn giả lập hỗ trợ hủy. Một chính sách tốt giới hạn thời gian chờ, dừng công việc khi không còn nhu cầu và phục hồi có kiểm soát mà không khuếch đại sự cố hoặc tạo side effect trùng lặp.
