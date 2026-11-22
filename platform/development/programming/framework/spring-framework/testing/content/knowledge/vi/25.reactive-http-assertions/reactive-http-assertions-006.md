# FluxExchangeResult và dữ liệu streaming

Trong Spring WebFlux, controller có thể trả về `Flux<T>` để phát ra nhiều phần tử theo thời gian. Với response streaming, test cần kiểm tra từng phần tử khi nó được phát ra, có thể kiểm tra thứ tự, thời điểm, số lượng và việc kết thúc hoặc hủy stream. `FluxExchangeResult<T>` kết hợp metadata của HTTP response với một `Flux<T>` chứa body đã được giải mã.

Khi dùng `WebTestClient`, có thể lấy `FluxExchangeResult` từ `ResponseSpec.returnResult(...)`, sau đó dùng Reactor Test `StepVerifier` để xác nhận các phần tử. Cách này phù hợp với Server-Sent Events (SSE), NDJSON và các response có body được truyền theo luồng.

## 1. Vì sao cần FluxExchangeResult?

Với response thông thường, test thường thu thập toàn bộ body rồi kiểm tra:

```java
client.get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isOk()
        .expectBodyList(OrderResponse.class)
        .hasSize(2);
```

Cách này phù hợp với một response hữu hạn mà client có thể đọc toàn bộ body trước khi assertion. Nhưng với stream dài hoặc vô hạn, việc chờ body kết thúc sẽ không phù hợp. Một endpoint gửi giá chứng khoán, log hoặc thông báo có thể tiếp tục phát dữ liệu cho đến khi client đóng kết nối.

`FluxExchangeResult<T>` cho phép test tiếp cận body dưới dạng `Flux<T>` sau khi response headers đã sẵn sàng. Test có thể yêu cầu một số phần tử, kiểm tra chúng, rồi xác nhận stream hoàn tất hoặc chủ động hủy subscription.

Luồng cơ bản:

```text
WebTestClient request
        |
        v
     exchange()
        |
        v
HTTP status + headers
        |
        v
returnResult(BodyType.class)
        |
        v
FluxExchangeResult<T>
        |
        +---- response metadata
        |
        +---- getResponseBody(): Flux<T>
                          |
                          v
                    StepVerifier
```

## 2. FluxExchangeResult chứa gì?

`FluxExchangeResult<T>` nằm trong package `org.springframework.test.web.reactive.server`. Nó là một dạng `ExchangeResult` chuyên cho response body dạng reactive stream.

Phần thường dùng nhất là:

```java
Flux<T> responseBody = result.getResponseBody();
```

`getResponseBody()` trả về publisher chứa các phần tử đã được giải mã theo kiểu `T`. Các thông tin HTTP như status, headers, cookies và request/response metadata vẫn có thể được truy cập từ `ExchangeResult` mà `FluxExchangeResult` kế thừa.

Ví dụ lấy result:

```java
FluxExchangeResult<StockUpdate> result = client.get()
        .uri("/stocks/stream")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
        .returnResult(StockUpdate.class);
```

Các assertion status và header được thực hiện trước khi lấy body stream. `returnResult(StockUpdate.class)` yêu cầu WebTestClient giải mã từng phần tử response thành `StockUpdate`.

## 3. Khai báo dependency cho StepVerifier

`StepVerifier` thuộc module `reactor-test`, không phải `reactor-core`. Nếu dự án chưa có dependency này trong test classpath, thêm dependency test tương ứng:

```groovy
dependencies {
    testImplementation("io.projectreactor:reactor-test")
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

Quản lý version `reactor-test` tương thích với Reactor Core mà Spring Framework hoặc Spring Boot đang sử dụng. Khi dự án dùng BOM của Spring Boot, nên để dependency management chọn version thay vì tự đặt version khác.

Import thường dùng:

```java
import reactor.test.StepVerifier;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
```

## 4. Kiểm tra một stream hữu hạn

Ví dụ controller trả về hai cập nhật giá:

```java
import reactor.core.publisher.Flux;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class StockController {

    @GetMapping(value = "/stocks/stream", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<StockUpdate> stream() {
        return Flux.just(
                new StockUpdate("ACME", 100),
                new StockUpdate("ACME", 105));
    }
}

record StockUpdate(String symbol, int price) {}
```

Test lấy `FluxExchangeResult` rồi kiểm tra các phần tử theo đúng thứ tự:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import reactor.test.StepVerifier;

import static org.springframework.test.web.reactive.server.WebTestClient.bindToController;

class StockControllerTests {

    private final WebTestClient client = bindToController(
            new StockController()).build();

    @Test
    void streamsStockUpdatesInOrder() {
        FluxExchangeResult<StockUpdate> result = client.get()
                .uri("/stocks/stream")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
                .returnResult(StockUpdate.class);

        StepVerifier.create(result.getResponseBody())
                .expectNext(new StockUpdate("ACME", 100))
                .expectNext(new StockUpdate("ACME", 105))
                .verifyComplete();
    }
}
```

`expectNext(...)` xác nhận giá trị và thứ tự của từng phần tử. `verifyComplete()` yêu cầu stream phát xong các phần tử rồi gửi tín hiệu `onComplete`. Nếu stream phát thêm phần tử ngoài dự kiến hoặc kết thúc bằng lỗi, verification sẽ thất bại.

`StockUpdate` là record nên phép so sánh bằng `equals` có thể dùng trực tiếp trong `expectNext`. Với class thông thường, hãy triển khai equality phù hợp hoặc dùng `expectNextMatches(...)` để kiểm tra các thuộc tính.

## 5. Kiểm tra stream vô hạn hoặc kéo dài

Một endpoint streaming có thể không bao giờ gửi `onComplete` trong điều kiện bình thường. Ví dụ server phát số liệu định kỳ:

```java
@GetMapping(value = "/stocks/live", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<StockUpdate> liveUpdates() {
    return Flux.interval(Duration.ofSeconds(1))
            .map(sequence -> new StockUpdate("ACME", 100 + sequence.intValue()));
}
```

Không thể gọi `verifyComplete()` cho stream này vì nó không có ý định hoàn tất. Test nên kiểm tra số phần tử cần thiết rồi chủ động hủy subscription:

```java
FluxExchangeResult<StockUpdate> result = client.get()
        .uri("/stocks/live")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(StockUpdate.class);

StepVerifier.create(result.getResponseBody())
        .expectNextMatches(update -> "ACME".equals(update.symbol()))
        .expectNextMatches(update -> update.price() == 101)
        .thenCancel()
        .verify(Duration.ofSeconds(5));
```

`thenCancel()` hủy subscription sau khi các expectation trước đó được đáp ứng. Điều này quan trọng vì test cần giải phóng stream và kết nối đang mở. Dùng `verify(Duration)` để giới hạn thời gian chờ và tránh test bị treo vô thời hạn nếu server không phát dữ liệu.

Với publisher cần kiểm soát backpressure, có thể bắt đầu với demand bằng 0 rồi yêu cầu từng phần tử:

```java
StepVerifier.create(result.getResponseBody(), 0)
        .expectSubscription()
        .thenRequest(1)
        .expectNextMatches(update -> update.price() >= 100)
        .thenRequest(1)
        .expectNextMatches(update -> update.price() >= 100)
        .thenCancel()
        .verify(Duration.ofSeconds(5));
```

Ví dụ này kiểm tra publisher chỉ được yêu cầu phát dữ liệu theo lượng demand mà test đưa ra. Đây là cách hữu ích khi hành vi backpressure là một phần của hợp đồng cần xác nhận.

## 6. Server-Sent Events và ServerSentEvent<T>

SSE là định dạng streaming qua HTTP thường dùng để server gửi event một chiều tới client. Response thường có media type `text/event-stream`. Mỗi event có thể chứa `id`, `event`, `retry` và `data`.

Spring biểu diễn SSE bằng `ServerSentEvent<T>`. Controller có thể trả về `Flux<ServerSentEvent<StockUpdate>>` để điều khiển metadata của từng event:

```java
import org.springframework.http.codec.ServerSentEvent;

@GetMapping(value = "/stocks/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
Flux<ServerSentEvent<StockUpdate>> stockEvents() {
    return Flux.just(
            ServerSentEvent.<StockUpdate>builder()
                    .id("event-1")
                    .event("stock-update")
                    .data(new StockUpdate("ACME", 100))
                    .build(),
            ServerSentEvent.<StockUpdate>builder()
                    .id("event-2")
                    .event("stock-update")
                    .data(new StockUpdate("ACME", 105))
                    .build());
}
```

Để kiểm tra cả metadata SSE và payload, dùng `ParameterizedTypeReference` giữ lại kiểu generic:

```java
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.codec.ServerSentEvent;

ParameterizedTypeReference<ServerSentEvent<StockUpdate>> eventType =
        new ParameterizedTypeReference<>() {};

FluxExchangeResult<ServerSentEvent<StockUpdate>> result = client.get()
        .uri("/stocks/events")
        .accept(MediaType.TEXT_EVENT_STREAM)
        .exchange()
        .expectStatus().isOk()
        .returnResult(eventType);

StepVerifier.create(result.getResponseBody())
        .expectNextMatches(event ->
                "event-1".equals(event.id())
                && "stock-update".equals(event.event())
                && event.data() != null
                && event.data().price() == 100)
        .expectNextMatches(event ->
                "event-2".equals(event.id())
                && event.data() != null
                && event.data().price() == 105)
        .verifyComplete();
```

Khi chỉ quan tâm payload và không cần metadata SSE, có thể yêu cầu `returnResult(StockUpdate.class)` để nhận từng `StockUpdate`. Khi cần xác nhận event name hoặc event ID, giữ kiểu `ServerSentEvent<StockUpdate>` để kiểm tra những trường đó.

## 7. NDJSON và các định dạng streaming khác

NDJSON (Newline Delimited JSON) truyền mỗi object JSON trên một dòng. Đây là định dạng phù hợp khi server phát ra nhiều JSON object độc lập thay vì gom chúng vào một JSON array.

Controller ví dụ:

```java
private static final MediaType APPLICATION_NDJSON =
        MediaType.parseMediaType("application/x-ndjson");

@GetMapping(value = "/stocks/ndjson", produces = "application/x-ndjson")
Flux<StockUpdate> ndjsonUpdates() {
    return Flux.just(
            new StockUpdate("ACME", 100),
            new StockUpdate("ACME", 105));
}
```

Test có thể giải mã từng dòng thành một object:

```java
MediaType ndjson = MediaType.parseMediaType("application/x-ndjson");

FluxExchangeResult<StockUpdate> result = client.get()
        .uri("/stocks/ndjson")
        .accept(ndjson)
        .exchange()
        .expectStatus().isOk()
        .expectHeader().contentTypeCompatibleWith(ndjson)
        .returnResult(StockUpdate.class);

StepVerifier.create(result.getResponseBody())
        .expectNext(new StockUpdate("ACME", 100))
        .expectNext(new StockUpdate("ACME", 105))
        .verifyComplete();
```

Đối với `application/json` thông thường, một `Flux<T>` ở server thường được encode thành một JSON array như một document hoàn chỉnh. Nếu mục tiêu là kiểm tra một danh sách JSON hữu hạn, `expectBodyList(...)` thường phù hợp hơn. Để kiểm tra từng phần tử theo thời gian, hãy dùng media type có framing streaming như SSE hoặc NDJSON và lấy `FluxExchangeResult`.

## 8. FluxExchangeResult khác với expectBodyList(...)

| API | Dữ liệu nhận được | Hành vi đọc body | Phù hợp với |
|---|---|---|---|
| `expectBody(Class<T>)` | Một object | Thu thập body thành một giá trị | JSON object hoặc response body đơn |
| `expectBodyList(Class<T>)` | `List<T>` | Đọc và thu thập danh sách hoàn chỉnh | JSON array hữu hạn |
| `returnResult(Class<T>)` | `FluxExchangeResult<T>` | Cung cấp body dưới dạng `Flux<T>` | SSE, NDJSON và response streaming |

Không nên dùng `expectBodyList(...)` cho stream vô hạn vì assertion phải đợi body kết thúc mới có danh sách hoàn chỉnh. Ngược lại, không cần `FluxExchangeResult` nếu response chỉ là một JSON object hoặc array hữu hạn và test không cần xác nhận hành vi streaming.

## 9. Kiểm tra lỗi và kết thúc stream

`StepVerifier` cho phép xác nhận cả tín hiệu kết thúc và lỗi:

```java
StepVerifier.create(result.getResponseBody())
        .expectNextCount(2)
        .verifyComplete();
```

Để xác nhận publisher kết thúc bằng một exception cụ thể:

```java
StepVerifier.create(result.getResponseBody())
        .expectNextCount(1)
        .expectErrorMatches(error ->
                error instanceof IllegalStateException
                && "stream failed".equals(error.getMessage()))
        .verify(Duration.ofSeconds(5));
```

Trong HTTP streaming, lỗi có thể xảy ra sau khi response headers đã được gửi. Khi đó status có thể đã là 200 nhưng body stream kết thúc bằng lỗi. Assertion status đơn thuần sẽ không phát hiện được vấn đề; `StepVerifier` mới xác nhận được tín hiệu lỗi phía body publisher.

Phân biệt lỗi HTTP trước khi body bắt đầu với lỗi xảy ra trong quá trình stream:

- Nếu server trả 4xx hoặc 5xx trước khi streaming body được thiết lập, kiểm tra bằng `expectStatus()` và body lỗi theo hợp đồng.
- Nếu server đã bắt đầu response rồi publisher phát `onError`, kiểm tra lỗi từ `getResponseBody()` bằng `expectError...`.
- Nếu client chủ động ngừng nhận dữ liệu, dùng `thenCancel()` để hủy subscription.

## 10. Lưu ý về subscription, timeout và tài nguyên

Body trong `FluxExchangeResult` là reactive publisher gắn với response đang được đọc. Thông thường, hãy subscribe một lần trong một test và để `StepVerifier` quản lý subscription. Không nên gọi `block()` rồi lại tạo verifier trên cùng body hoặc cố subscribe lặp để chạy nhiều assertion độc lập.

Một số nguyên tắc thực tế:

- Dùng `verifyComplete()` với stream hữu hạn có tín hiệu hoàn tất.
- Dùng `thenCancel()` với stream vô hạn hoặc test chỉ cần lấy một số event đầu.
- Đặt timeout cho `verify(...)` nếu stream phụ thuộc thời gian hoặc có khả năng không phát dữ liệu.
- Kiểm tra thứ tự bằng `expectNext(...)` hoặc `expectNextMatches(...)`.
- Chỉ dùng `expectNoEvent(Duration)` khi cần xác nhận không có tín hiệu trong một khoảng thời gian; tránh assertion thời gian quá ngắn khiến test chập chờn trên CI.
- Không thu thập toàn bộ một stream vô hạn bằng `collectList()` hoặc `expectBodyList(...)`.

## 11. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Test bị treo khi xác nhận stream | Gọi `verifyComplete()` trên publisher không bao giờ hoàn tất | Dùng `thenCancel()` sau số event cần kiểm tra và đặt timeout |
| Không nhận được từng JSON object | Server đang trả `application/json` dạng một JSON array | Dùng SSE hoặc NDJSON nếu hợp đồng là streaming; nếu là array thì dùng `expectBodyList(...)` |
| `returnResult(...)` không giải mã được body | Kiểu đích hoặc codec không phù hợp với media type | Kiểm tra `Accept`, response content type và codec đã cấu hình |
| Chỉ kiểm tra status mà bỏ lỡ lỗi giữa stream | Body publisher phát lỗi sau khi headers đã được gửi | Dùng StepVerifier để kiểm tra `onError` hoặc `onComplete` |
| Test chỉ nhận được một event | Test hủy subscription quá sớm hoặc demand không đủ | Kiểm tra các bước `thenRequest(...)` và vị trí `thenCancel()` |
| Assertion SSE không thấy event ID hoặc event name | Chỉ giải mã payload thành DTO | Dùng `ParameterizedTypeReference<ServerSentEvent<T>>` để giữ metadata SSE |
| Test phụ thuộc thời gian và chập chờn | Dùng delay quá ngắn hoặc kiểm tra thời điểm không ổn định | Ưu tiên kiểm tra thứ tự và số lượng; chỉ kiểm tra thời gian khi đó là hợp đồng |

## 12. Ghi nhớ

`FluxExchangeResult<T>` cho phép lấy response body của WebTestClient dưới dạng `Flux<T>` thông qua `returnResult(...)`. Kết hợp với `StepVerifier`, test có thể xác nhận phần tử, thứ tự, tín hiệu hoàn tất, lỗi, backpressure và việc hủy stream. Dùng `verifyComplete()` cho stream hữu hạn, `thenCancel()` cho stream dài hoặc vô hạn. Với SSE, giữ kiểu `ServerSentEvent<T>` nếu cần kiểm tra metadata; với NDJSON, giải mã từng dòng thành DTO. Hãy chọn API streaming khi hợp đồng response thực sự truyền dữ liệu theo luồng.

