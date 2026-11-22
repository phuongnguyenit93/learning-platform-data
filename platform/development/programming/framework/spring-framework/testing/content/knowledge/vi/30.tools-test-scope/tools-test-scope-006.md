# Reactor Test bổ sung kiểm chứng luồng phản ứng

Ứng dụng reactive không trả kết quả theo kiểu gọi hàm rồi nhận ngay một giá trị. `Mono` và `Flux` mô tả một publisher sẽ phát dữ liệu, kết thúc bình thường hoặc phát lỗi khi có subscriber đăng ký. Một luồng còn có thể nhận demand, bị hủy, phụ thuộc thời gian hoặc đi qua những nhánh xử lý khác nhau tùy dữ liệu đầu vào.

Reactor Test cung cấp các công cụ để kiểm chứng những hành vi này một cách có chủ đích. `StepVerifier` mô tả chuỗi tín hiệu mong đợi; `TestPublisher` cho phép test điều khiển thời điểm phát dữ liệu; `PublisherProbe` xác nhận một nhánh publisher có được đăng ký hay không; virtual time giúp kiểm thử operator dựa trên thời gian mà không phải chờ thật. Các tiện ích này bổ sung cho JUnit và AssertJ trong kiểm thử service reactive, operator và thành phần WebFlux.

## 1. Thêm Reactor Test vào test classpath

`StepVerifier`, `TestPublisher` và `PublisherProbe` nằm trong artifact `reactor-test`, không nằm trong `reactor-core`. Với Gradle và Spring Boot dependency management:

```groovy
dependencies {
    testImplementation 'io.projectreactor:reactor-test'
}
```

Với Maven:

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
```

Hãy dùng phiên bản `reactor-test` tương thích với `reactor-core`. Nếu dự án dùng Spring Boot BOM, để dependency management chọn phiên bản thay vì khai báo một phiên bản độc lập có thể lệch với Reactor trong ứng dụng.

## 2. Chọn công cụ theo hành vi cần xác nhận

| Công cụ | Vai trò | Khi nên dùng |
|---|---|---|
| `StepVerifier` | Subscribe và xác nhận chuỗi tín hiệu | Kiểm tra phần tử, thứ tự, hoàn tất, lỗi, demand và cancellation |
| `TestPublisher` | Publisher có thể được test phát dữ liệu theo ý muốn | Kiểm soát thời điểm phát, tạo luồng chưa hoàn tất, kiểm tra consumer phản ứng với tín hiệu |
| `PublisherProbe` | Theo dõi subscription, request và cancellation của một publisher | Xác nhận nhánh `switchIfEmpty`, fallback hoặc publisher phụ có thực sự được dùng |
| `StepVerifier.withVirtualTime` | Chạy kịch bản với đồng hồ ảo | Kiểm tra `delay`, `interval`, timeout hoặc retry có thời gian chờ |
| `verifyThenAssertThat` | Kiểm tra tín hiệu phụ sau khi kịch bản hoàn tất | Xác nhận phần tử bị discard hoặc drop trong pipeline |

Các công cụ này tập trung vào publisher và Reactive Streams. Khi cần xác nhận HTTP method, URI, header, status hoặc JSON của một endpoint WebFlux, dùng `WebTestClient`; có thể kết hợp `WebTestClient` với `StepVerifier` khi response body là một stream cần quan sát từng phần tử.

## 3. StepVerifier: xác nhận tín hiệu của publisher

`StepVerifier.create(publisher)` tạo một kịch bản kiểm thử. Kịch bản thường mô tả:

1. Subscriber đăng ký với publisher.
2. Publisher phát các phần tử qua `onNext`.
3. Publisher kết thúc bằng `onComplete` hoặc `onError`, hoặc subscriber chủ động hủy.

Ví dụ một `Flux` phát hai giá trị rồi hoàn tất:

```java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

StepVerifier.create(Flux.just("red", "blue"))
    .expectNext("red", "blue")
    .verifyComplete();
```

Các assertion phổ biến gồm `expectNext`, `assertNext`, `expectNextMatches`, `expectNextCount`, `expectComplete`, `expectError`, `expectErrorMessage` và `thenCancel`. `verify()` hoặc các biến thể như `verifyComplete()` thực sự subscribe và chạy kịch bản. Nếu chỉ xây dựng chuỗi expectation mà không gọi verify, publisher chưa được kiểm thử.

Có thể kiểm tra một phần tử bằng nhiều assertion:

```java
import static org.assertj.core.api.Assertions.assertThat;

StepVerifier.create(orderService.find("ORD-356"))
    .assertNext(order -> {
        assertThat(order.id()).isEqualTo("ORD-356");
        assertThat(order.status()).isEqualTo("CONFIRMED");
    })
    .verifyComplete();
```

Kịch bản nên kiểm tra cả dữ liệu và tín hiệu kết thúc. Nếu service được kỳ vọng trả đúng một phần tử, chỉ kiểm tra phần tử đầu tiên có thể bỏ sót phần tử thừa hoặc lỗi phát ra sau đó.

## 4. TestPublisher: chủ động điều khiển nguồn dữ liệu

Trong nhiều unit test, `Flux.just(...)` hoặc `Mono.just(...)` phát dữ liệu ngay khi được subscribe. Điều này thuận tiện nhưng không cho phép test quyết định thời điểm publisher phát phần tử. `TestPublisher` giải quyết nhu cầu đó: test tạo publisher, đưa publisher vào component, sau đó chủ động gọi `next`, `complete` hoặc `error` khi cần.

Ví dụ component chuyển đổi giá trị từ publisher:

```java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Publisher;

class ScoreService {

    Flux<Integer> doubleScores(Publisher<Integer> scores) {
        return Flux.from(scores).map(score -> score * 2);
    }
}
```

Test tạo `TestPublisher`, truyền stream của nó vào service và phát dữ liệu sau khi StepVerifier đã subscribe:

```java
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

TestPublisher<Integer> source = TestPublisher.create();
ScoreService service = new ScoreService();

StepVerifier.create(service.doubleScores(source.flux()))
    .then(() -> source.next(4))
    .expectNext(8)
    .then(() -> source.next(7))
    .expectNext(14)
    .then(source::complete)
    .verifyComplete();

source.assertWasRequested();
```

Trình tự này giúp test điều khiển chính xác thời điểm phát từng phần tử. Nó hữu ích khi kiểm tra một component có phản ứng đúng khi dữ liệu đến từng đợt, khi nguồn dữ liệu chưa hoàn tất hoặc khi lỗi xảy ra sau một số phần tử.

### Kiểm tra lỗi từ nguồn dữ liệu

TestPublisher có thể phát lỗi tại thời điểm test chọn:

```java
TestPublisher<String> source = TestPublisher.create();

StepVerifier.create(service.validateNames(source.flux()))
    .then(() -> source.next("Mai"))
    .expectNext("MAI")
    .then(() -> source.error(new IllegalStateException("source failed")))
    .expectErrorMessage("source failed")
    .verify();
```

Ví dụ giả định `validateNames` chuyển tên thành chữ hoa và truyền lỗi nguồn ra downstream. Nếu component chuyển lỗi thành một lỗi nghiệp vụ khác, assertion phải phản ánh hợp đồng chuyển đổi lỗi của component.

### Kiểm tra subscription và demand

`TestPublisher` còn cung cấp assertion để kiểm tra cách consumer đăng ký và yêu cầu dữ liệu. Ví dụ, test có thể xác nhận nguồn đã được subscribe và đã nhận demand:

```java
TestPublisher<Integer> source = TestPublisher.create();

StepVerifier.create(service.doubleScores(source.flux()), 0)
    .expectSubscription()
    .thenRequest(1)
    .then(() -> source.next(5))
    .expectNext(10)
    .then(source::complete)
    .verifyComplete();

source.assertWasSubscribed();
source.assertWasRequested();
```

TestPublisher phù hợp để tạo tín hiệu đầu vào có kiểm soát. Nó không thay thế `StepVerifier`: publisher điều khiển nguồn, còn StepVerifier kiểm tra kết quả và tín hiệu downstream.

### Publisher tuân thủ và publisher không tuân thủ đặc tả

Mặc định, `TestPublisher.create()` tạo publisher tuân thủ quy tắc Reactive Streams. Reactor Test cũng có `createNoncompliant(...)` để mô phỏng một số hành vi vi phạm đặc tả, chẳng hạn phát vượt demand hoặc phát tín hiệu null trong những tình huống đặc biệt. Chỉ dùng chế độ này khi kiểm tra operator hoặc consumer phải phòng vệ trước một publisher không tuân thủ; test nghiệp vụ thông thường nên dùng publisher tuân thủ để phản ánh đúng hợp đồng reactive.

## 5. PublisherProbe: xác nhận nhánh xử lý được chọn

Một pipeline reactive có thể có nhiều nhánh. Ví dụ, `switchIfEmpty` chỉ subscribe publisher dự phòng khi publisher chính không phát phần tử. Kiểm tra kết quả cuối cùng đôi khi chưa đủ để biết nhánh fallback có thực sự được dùng hay không.

`PublisherProbe` bọc một publisher và ghi nhận hành vi subscription. Có thể dùng `PublisherProbe.of(publisher)` để theo dõi publisher có dữ liệu, hoặc `PublisherProbe.empty()` để theo dõi nhánh rỗng.

```java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;

PublisherProbe<String> fallback = PublisherProbe.of(Mono.just("default"));

Mono<String> result = Mono.<String>empty()
    .switchIfEmpty(fallback.mono());

StepVerifier.create(result)
    .expectNext("default")
    .verifyComplete();

fallback.assertWasSubscribed();
```

Để xác nhận fallback không chạy khi nguồn chính có dữ liệu:

```java
PublisherProbe<String> fallback = PublisherProbe.of(Mono.just("default"));

Mono<String> result = Mono.just("primary")
    .switchIfEmpty(fallback.mono());

StepVerifier.create(result)
    .expectNext("primary")
    .verifyComplete();

fallback.assertWasNotSubscribed();
```

Các assertion như `assertWasSubscribed`, `assertWasNotSubscribed`, `assertWasRequested` và `assertWasCancelled` giúp xác nhận nhánh thực thi. Điều này đặc biệt hữu ích với `switchIfEmpty`, fallback khi cache miss, retry branch hoặc một publisher phụ chỉ được gọi khi điều kiện cụ thể xảy ra.

## 6. Virtual time: kiểm tra thời gian mà không phải chờ thật

Các operator như `delayElements`, `interval`, `timeout` và retry có backoff phụ thuộc scheduler và thời gian. Nếu test dùng thời gian thực, một kịch bản vài phút có thể khiến suite chậm; test cũng dễ không ổn định khi CI bị tải.

`StepVerifier.withVirtualTime(...)` tạo môi trường virtual time cho những scheduler mặc định mà Reactor hỗ trợ. Publisher phải được tạo bên trong supplier truyền vào `withVirtualTime` để virtual scheduler được cài trước khi publisher được lắp ráp:

```java
import java.time.Duration;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofHours(1)).take(2))
    .expectSubscription()
    .thenAwait(Duration.ofHours(2))
    .expectNext(0L, 1L)
    .verifyComplete();
```

Hai giờ trong kịch bản được tiến bằng đồng hồ ảo, không phải chờ hai giờ thật. `thenAwait(...)` tiến thời gian; `expectNoEvent(...)` tiến thời gian và xác nhận không có tín hiệu ngoài subscription trong khoảng đó.

Virtual time không tự thay thế mọi scheduler. Nếu code truyền một scheduler cụ thể hoặc dùng executor/timer bên ngoài Reactor, scheduler đó có thể không chịu ảnh hưởng bởi virtual time. Khi ấy, cần inject scheduler để test có thể điều khiển hoặc dùng cơ chế đồng bộ phù hợp.

## 7. Xác nhận Context reactive

Reactor `Context` là dữ liệu gắn với subscription, thường dùng để truyền thông tin như correlation ID, tenant hoặc security context qua chuỗi operator mà không đặt vào từng phần tử dữ liệu.

`StepVerifier` có thể kiểm tra context mà publisher nhận được bằng `expectAccessibleContext()`:

```java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.context.Context;

Mono<String> currentTenant = Mono.deferContextual(context ->
    Mono.just(context.get("tenant"))
);

StepVerifier.create(currentTenant,
        StepVerifierOptions.create()
            .withInitialContext(Context.of("tenant", "tenant-356")))
    .expectAccessibleContext()
    .contains("tenant", "tenant-356")
    .then()
    .expectNext("tenant-356")
    .verifyComplete();
```

`StepVerifierOptions` cần được import từ `reactor.test`. Có thể dùng `withInitialContext(...)` để tạo context ban đầu cho subscription. Assertion này hữu ích khi code dựa vào context để định tuyến tenant, đọc thông tin bảo mật hoặc ghi correlation ID.

Context không phải thuộc tính của từng phần tử `onNext`. Nó gắn với subscription và được đọc qua `deferContextual` hoặc operator tương ứng. Vì vậy, hãy kiểm tra context ở đúng ranh giới reactive nơi ứng dụng tiêu thụ nó.

## 8. Kiểm tra phần tử bị discard hoặc drop

Trong một số pipeline, operator có thể loại bỏ phần tử có chủ đích. Ví dụ, `filter` không phát phần tử không thỏa điều kiện xuống downstream. Reactor có khái niệm discard để các operator hoặc resource-aware pipeline có thể xử lý phần tử bị loại bỏ.

`verifyThenAssertThat()` cho phép kiểm tra các tín hiệu phụ sau khi kịch bản chính đã chạy xong:

```java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

StepVerifier.create(Flux.just(1, 2, 3).filter(value -> value != 2))
    .expectNext(1, 3)
    .verifyComplete();
```

Khi cần xác nhận phần tử bị discard, dùng `verifyThenAssertThat()`:

```java
StepVerifier.create(Flux.just(1, 2, 3).filter(value -> value != 2))
    .expectNext(1, 3)
    .verifyComplete();
```

Đối với pipeline có hook discard hoặc operator cần bảo đảm phần tử bị loại bỏ được xử lý, hãy dùng API `verifyThenAssertThat()` và các assertion như `hasDiscardedElements()` hoặc `hasDiscarded(...)` theo phiên bản Reactor Test của dự án. Tín hiệu drop và discard có ý nghĩa khác nhau: discard thường là loại bỏ có chủ đích trong operator; drop là tín hiệu đến sau khi downstream đã kết thúc hoặc không còn có thể nhận nó. Không nên coi mọi phần tử không xuất hiện ở downstream là lỗi drop.

## 9. Dùng Reactor Test trong unit test service và WebFlux

Với service reactive, test thường kiểm tra trực tiếp publisher được trả về:

```java
class InventoryServiceTests {

    @Test
    void returnsAvailableQuantity() {
        StepVerifier.create(inventoryService.availableQuantity("SKU-1"))
            .expectNext(12)
            .verifyComplete();
    }
}
```

Nếu service phụ thuộc vào một nguồn dữ liệu reactive, `TestPublisher` cho phép điều khiển nguồn đó. Nếu service có nhánh fallback, `PublisherProbe` xác nhận nhánh nào được subscribe. Nếu kết quả phụ thuộc thời gian, dùng virtual time.

Với controller WebFlux, `WebTestClient` kiểm tra giao thức HTTP và response. Nếu endpoint trả về stream, lấy publisher từ `returnResult(...)` rồi dùng `StepVerifier` để xác nhận từng phần tử hoặc cancellation. Không dùng `StepVerifier` thay cho HTTP assertions khi điều cần xác nhận là status code, header hoặc JSON response.

## 10. Lỗi thường gặp và cách chọn đúng phạm vi

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| `StepVerifier` không chạy | Đã tạo expectation nhưng chưa gọi `verify()` hoặc biến thể tương ứng |
| TestPublisher phát dữ liệu nhưng consumer không nhận | Consumer chưa subscribe, chưa có demand hoặc publisher đã kết thúc |
| TestPublisher báo request overflow | Test phát nhiều phần tử hơn demand mà subscriber đã yêu cầu; điều khiển demand đúng thứ tự |
| PublisherProbe không được subscribe | Điều kiện để vào nhánh fallback không xảy ra hoặc publisher probe không nằm trong pipeline đang kiểm tra |
| Virtual time không tiến | Publisher được tạo trước `withVirtualTime` hoặc dùng scheduler riêng không được virtual hóa |
| Test chờ vô hạn | Publisher không kết thúc; giới hạn số phần tử, gọi `thenCancel()` hoặc đặt timeout cho verify |
| Context assertion không thấy key | Context được ghi ở sai vị trí operator hoặc test chưa đặt initial context đúng subscription |
| HTTP assertion thiếu status/header | Đang kiểm tra publisher ở tầng service; chuyển sang `WebTestClient` nếu mục tiêu là HTTP contract |

Không nên dùng `TestPublisher` chỉ để thay `Flux.just(...)` trong mọi test. Dùng nó khi cần điều khiển tín hiệu hoặc kiểm tra phản ứng của consumer. Không nên dùng `PublisherProbe` nếu chỉ cần xác nhận kết quả đầu ra; nó có giá trị khi việc chọn nhánh hoặc subscription tự nó là điều cần xác nhận.

## 11. Quy trình chọn công cụ Reactor Test

1. Xác định hành vi reactive cần kiểm tra: dữ liệu, terminal signal, thời gian, demand, cancellation hay nhánh xử lý.
2. Dùng `StepVerifier` làm công cụ chính để xác nhận chuỗi tín hiệu downstream.
3. Dùng `TestPublisher` khi test cần điều khiển publisher đầu vào theo từng bước.
4. Dùng `PublisherProbe` khi cần chứng minh một nhánh publisher có hoặc không được subscribe.
5. Dùng `withVirtualTime` khi operator phụ thuộc scheduler thời gian mặc định của Reactor.
6. Dùng context và post-verification assertions khi hợp đồng của component bao gồm Context, discard hoặc drop.
7. Dùng `WebTestClient` cho HTTP contract và kết hợp `StepVerifier` cho response stream khi cần.

Reactor Test bổ sung các công cụ kiểm chứng ở tầng reactive: không chỉ xác nhận publisher phát giá trị nào, mà còn xác nhận nó được subscribe ra sao, nhận demand thế nào, chọn nhánh nào, kết thúc hoặc bị hủy khi nào. Chọn đúng công cụ theo hành vi cần quan sát giúp test tập trung vào hợp đồng reactive và giữ ranh giới rõ với kiểm thử HTTP của Spring WebFlux.
