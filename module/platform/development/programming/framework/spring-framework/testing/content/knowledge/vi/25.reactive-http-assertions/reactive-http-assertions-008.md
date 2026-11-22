# Đặt giới hạn chờ cho luồng không kết thúc

Trong WebFlux, một endpoint có thể trả về `Flux` phát dữ liệu liên tục mà không bao giờ gửi tín hiệu hoàn tất. Những endpoint như Server-Sent Events (SSE), thông báo trực tiếp, log stream hoặc feed trạng thái thường được thiết kế như vậy: kết nối tiếp tục mở để server gửi các phần tử mới khi có dữ liệu.

Đặc điểm này tạo ra một khác biệt quan trọng khi kiểm thử. Với response thông thường, test có thể đọc toàn bộ body, chờ publisher hoàn tất rồi so sánh kết quả. Với luồng không kết thúc, việc chờ body hoàn tất sẽ không bao giờ kết thúc nếu không có timeout hoặc thao tác hủy. Test cần xác định rõ mình muốn chờ response bắt đầu, chờ một sự kiện cụ thể, xác nhận không có sự kiện trong một khoảng thời gian, hay chủ động kết thúc subscription.

`WebTestClient` kết hợp với Reactor Test (`StepVerifier`) cung cấp cách kiểm soát những mốc chờ này. Ta cũng có thể cấu hình timeout cho client và timeout ở cấp test để tránh một lỗi làm treo toàn bộ bộ kiểm thử.

## 1. Vì sao luồng không kết thúc cần cách kiểm thử riêng?

Một publisher reactive có thể phát các phần tử rồi hoàn tất:

```java
Flux<String> finite = Flux.just("first", "second", "third");
```

Sau phần tử cuối, publisher gửi `onComplete`. Các API gom body như `expectBodyList(...)` có thể đọc đến khi hoàn tất rồi trả kết quả.

Ngược lại, publisher sau không gửi `onComplete` hoặc `onError`:

```java
Flux<String> endless = Flux.interval(Duration.ofSeconds(1))
        .map(index -> "event-" + index);
```

Mỗi giây có một phần tử mới, nhưng publisher không tự kết thúc. Một nguồn khác còn có thể không phát phần tử nào:

```java
Flux<String> silent = Flux.never();
```

`Flux.never()` không phát `onNext`, `onError` hoặc `onComplete`. Đây là nguồn hữu ích để kiểm tra timeout, nhưng nếu test chờ nó hoàn tất thì test sẽ chờ mãi.

Với response streaming, cần phân biệt các giai đoạn:

```text
Request được gửi
      |
      v
Response status và headers đến
      |
      v
Body publisher bắt đầu được đọc
      |
      +---- onNext: dữ liệu đầu tiên
      |
      +---- onNext: dữ liệu tiếp theo
      |
      +---- onNext: heartbeat / dữ liệu mới
      |
      +---- ... stream tiếp tục ...
      |
      +---- onComplete hoặc onError (có thể không bao giờ xảy ra)
```

Một test có thể cần xác nhận status và header ngay khi response mở, sau đó chỉ đọc một vài phần tử rồi hủy. Nó không cần đợi stream hoàn tất để chứng minh những hành vi đó.

## 2. Dùng `returnResult` để nhận stream

Với body hữu hạn, các matcher như `expectBody(...)` và `expectBodyList(...)` thuận tiện vì chúng đợi body được đọc xong. Với stream không kết thúc, dùng `returnResult(...)` để lấy `Flux` response body rồi kiểm soát subscription bằng Reactor Test.

Ví dụ controller phát Server-Sent Events:

```java
import java.time.Duration;

import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
class EventController {

    @GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<ServerSentEvent<String>> events() {
        return Flux.interval(Duration.ofSeconds(1))
                .map(index -> ServerSentEvent.<String>builder()
                        .id(Long.toString(index))
                        .event("tick")
                        .data("event-" + index)
                        .build());
    }
}
```

Bài test chỉ đọc hai event đầu tiên rồi hủy subscription:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.core.ParameterizedTypeReference;
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import reactor.test.StepVerifier;

class EventControllerTest {

    @Test
    void readsSomeEventsAndCancelsTheInfiniteStream() {
        FluxExchangeResult<ServerSentEvent<String>> result = webTestClient.get()
                .uri("/events")
                .accept(MediaType.TEXT_EVENT_STREAM)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().contentTypeCompatibleWith(MediaType.TEXT_EVENT_STREAM)
                .returnResult(new ParameterizedTypeReference<ServerSentEvent<String>>() {});

        StepVerifier.create(result.getResponseBody())
                .assertNext(event -> {
                    assertThat(event.event()).isEqualTo("tick");
                    assertThat(event.data()).isEqualTo("event-0");
                })
                .assertNext(event -> assertThat(event.data()).isEqualTo("event-1"))
                .thenCancel()
                .verify(Duration.ofSeconds(4));
    }
}
```

Trong ví dụ, `webTestClient` được tạo từ cấu hình WebFlux hoặc được inject từ Spring Boot test. `returnResult(...)` trả về `FluxExchangeResult`, cho phép lấy body dưới dạng `Flux<ServerSentEvent<String>>`. `StepVerifier` đăng ký vào stream, kiểm tra hai phần tử và gọi `thenCancel()` để kết thúc subscription.

`verify(Duration.ofSeconds(4))` giới hạn tổng thời gian xác minh. Nếu event không đến đúng hạn, verification thất bại thay vì treo vô hạn. Thời gian này cần đủ cho lịch phát event và độ trễ của môi trường CI; không nên đặt quá sát chu kỳ phát.

## 3. Phân biệt các loại timeout

Không có một timeout duy nhất phù hợp cho mọi giai đoạn. Một bài test streaming thường có nhiều giới hạn độc lập:

| Loại giới hạn | Phạm vi | Mục đích |
|---|---|---|
| Client response timeout | Giai đoạn chờ response từ server trong quá trình exchange | Phát hiện server không trả response hoặc response đến quá chậm. |
| `StepVerifier.verify(Duration)` | Toàn bộ quá trình xác minh publisher | Giới hạn thời gian test chờ các tín hiệu reactive mong đợi. |
| `expectNoEvent(Duration)` | Một khoảng thời gian trong subscription | Xác nhận stream không phát thêm tín hiệu trong khoảng đó. |
| Reactor `timeout(...)` | Publisher trong ứng dụng | Định nghĩa hành vi timeout thực tế của nghiệp vụ hoặc stream. |
| JUnit `@Timeout` | Toàn bộ test method | Lớp bảo vệ cuối cùng nếu test bị kẹt ở bất kỳ bước nào. |

Các giới hạn này không thay thế lẫn nhau. Ví dụ, server có thể trả status và header nhanh chóng, sau đó stream không phát event nào nữa. Client response timeout có thể không phát hiện khoảng im lặng trong body; `StepVerifier` mới là nơi trực tiếp giới hạn thời gian chờ các event.

### Cấu hình timeout cho WebTestClient

Khi tạo client, có thể cấu hình response timeout:

```java
WebTestClient client = WebTestClient.bindToApplicationContext(applicationContext)
        .configureClient()
        .responseTimeout(Duration.ofSeconds(5))
        .build();
```

Với client kết nối server thật, cấu hình tương tự có thể được áp dụng sau `bindToServer()`:

```java
WebTestClient client = WebTestClient.bindToServer()
        .baseUrl("http://localhost:8080")
        .responseTimeout(Duration.ofSeconds(5))
        .build();
```

Response timeout giới hạn giai đoạn chờ response theo cơ chế client. Với response streaming, status và headers có thể đến sớm trong khi body vẫn tiếp tục phát lâu dài. Vì vậy, không dùng response timeout làm cách duy nhất để giới hạn việc đọc một stream không kết thúc; hãy giới hạn subscription của body bằng `StepVerifier`.

### Giới hạn tổng thời gian xác minh

Reactor Test cho phép đặt timeout trực tiếp trên thao tác verify:

```java
StepVerifier.create(responseBody)
        .expectNext("ready")
        .thenCancel()
        .verify(Duration.ofSeconds(3));
```

Đây là timeout tổng cho quá trình verify. Nếu stream không phát `ready`, test thất bại khi hết thời gian. Nếu `ready` đến, verifier hủy subscription và kết thúc sớm.

Nên ưu tiên timeout theo từng bài test thay vì thiết lập `StepVerifier.setDefaultTimeout(...)` toàn cục. Cấu hình mặc định toàn cục có thể ảnh hưởng test khác, đặc biệt khi chạy song song, và làm khó hiểu nguyên nhân một test chậm.

## 4. Xác nhận stream im lặng trong một khoảng thời gian

Đôi khi yêu cầu không phải chờ event tiếp theo, mà là chứng minh server không phát event trong một khoảng thời gian. Ví dụ, một endpoint chỉ phát dữ liệu khi có thay đổi và không được gửi thông báo rỗng liên tục.

`expectNoEvent(Duration)` kiểm tra không có tín hiệu nào trong khoảng thời gian chỉ định:

```java
StepVerifier.create(responseBody)
        .expectSubscription()
        .expectNoEvent(Duration.ofMillis(300))
        .thenCancel()
        .verify(Duration.ofSeconds(2));
```

Phải gọi `expectSubscription()` trước `expectNoEvent(...)`, vì tín hiệu subscription ban đầu cũng được tính là một sự kiện trong quá trình verify. Nếu không, verifier có thể báo lỗi ngay tại bước đầu.

Có thể kết hợp kiểm tra một event đầu tiên, sau đó xác nhận một khoảng im lặng:

```java
StepVerifier.create(responseBody)
        .expectSubscription()
        .expectNextMatches(event -> "connected".equals(event))
        .expectNoEvent(Duration.ofMillis(500))
        .thenCancel()
        .verify(Duration.ofSeconds(2));
```

Đây là phép đo theo thời gian thực. Khoảng im lặng phải lớn hơn độ trễ bình thường nhưng đủ ngắn để test không chậm không cần thiết. Không nên dùng một khoảng vài mili giây để kết luận stream không phát dữ liệu nếu scheduler hoặc CI có thể bị trễ.

## 5. Timeout của ứng dụng với Reactor `timeout`

`StepVerifier.verify(Duration)` chỉ giới hạn thời gian test chờ. Nó không thay đổi hành vi publisher trong ứng dụng. Nếu yêu cầu nghiệp vụ quy định stream phải phát dữ liệu trong một khoảng nhất định, hoặc phải chuyển sang fallback khi không có dữ liệu, hãy cấu hình timeout trong pipeline reactive.

Ví dụ `Flux.timeout(Duration)` phát lỗi `TimeoutException` nếu nguồn không phát phần tử trong khoảng thời gian cho phép:

```java
Flux<String> guarded = source.timeout(Duration.ofSeconds(10));
```

Với `Flux`, khoảng timeout được tính khi chờ phần tử đầu tiên và được đặt lại sau mỗi phần tử. Vì vậy đây là giới hạn thời gian im lặng giữa các event, không phải giới hạn tổng tuổi thọ của stream. Một stream phát heartbeat đều đặn có thể chạy vô thời hạn mà không timeout.

Nếu muốn chuyển sang luồng dự phòng khi quá hạn:

```java
Flux<String> guarded = source.timeout(
        Duration.ofSeconds(10),
        Flux.just("no-data-fallback"));
```

Nếu muốn xử lý lỗi timeout theo nghiệp vụ:

```java
Flux<String> guarded = source
        .timeout(Duration.ofSeconds(10))
        .onErrorResume(TimeoutException.class,
                error -> Flux.just("stream-timeout"));
```

Test cần phân biệt hai kết quả: timeout trong ứng dụng làm thay đổi response stream; timeout của `StepVerifier` chỉ làm bài test kết thúc nếu tín hiệu mong đợi không đến. Không nên thêm `timeout(...)` vào production chỉ để tránh test bị treo.

### Giới hạn tổng thời gian của stream

Nếu yêu cầu là stream chỉ được tồn tại tối đa một khoảng thời gian, dùng một toán tử giới hạn tổng thời gian như `take(Duration)`:

```java
Flux<String> finiteWindow = source.take(Duration.ofMinutes(5));
```

Khác với `timeout(Duration)`, `take(Duration)` hoàn tất sau khoảng thời gian tính từ lúc subscription bắt đầu, ngay cả khi nguồn vẫn liên tục phát event. Chọn toán tử theo yêu cầu: idle timeout để phát hiện không có dữ liệu, hay lifetime limit để đóng stream sau một thời lượng xác định.

## 6. Dùng virtual time cho publisher dựa trên thời gian

Với publisher dùng scheduler hỗ trợ virtual time, Reactor Test có thể chạy thời gian ảo để kiểm tra timeout hoặc interval mà không phải chờ thật. Điều này giúp test nhanh và ổn định hơn khi logic chỉ phụ thuộc vào thời gian của Reactor.

Ví dụ publisher phát hai giá trị cách nhau một giây rồi hoàn tất:

```java
StepVerifier.withVirtualTime(() -> Flux.interval(Duration.ofSeconds(1)).take(2))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(2))
        .expectNext(0L, 1L)
        .verifyComplete();
```

`withVirtualTime` nhận một `Supplier` để publisher được tạo sau khi virtual scheduler đã được cài đặt. Nếu tạo `Flux.interval(...)` trước rồi mới truyền vào verifier, publisher có thể đã giữ scheduler thật và không được điều khiển bởi virtual time.

Virtual time phù hợp cho unit test của publisher hoặc service reactive. Không giả định nó tự điều khiển đồng hồ của Netty, socket, HTTP client hoặc mọi thành phần trong một `WebTestClient` exchange. Với test đi qua transport thật, nên dùng timeout thực tế và đặt giới hạn đủ rộng.

## 7. Xác nhận cancellation khi test kết thúc

Với stream dài hạn, hủy subscription là một phần quan trọng của hợp đồng tài nguyên. Khi client không còn quan tâm đến dữ liệu, cancellation nên truyền ngược về publisher để giải phóng listener, timer, connection hoặc subscription đến message broker.

Có thể gắn `doOnCancel` vào nguồn dữ liệu để quan sát việc hủy trong test:

```java
AtomicBoolean cancelled = new AtomicBoolean(false);

Flux<String> events = Flux.<String>never()
        .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(events)
        .thenCancel()
        .verify(Duration.ofSeconds(1));

assertThat(cancelled).isTrue();
```

Đây là unit test cho publisher. Với WebTestClient, có thể áp dụng cùng ý tưởng cho nguồn được controller trả về rồi kiểm tra cancellation sau khi verifier hủy body stream:

```java
StepVerifier.create(result.getResponseBody())
        .expectNextCount(1)
        .thenCancel()
        .verify(Duration.ofSeconds(2));

assertThat(sourceCancelled.get()).isTrue();
```

Ví dụ tích hợp này giả định controller dùng publisher có `doOnCancel` để cập nhật `sourceCancelled`. Cần kiểm tra đúng nguồn upstream được theo dõi; nếu có operator tạo buffer hoặc prefetch, thời điểm cancellation quan sát được có thể khác một chút. Không nên chỉ xác nhận test kết thúc mà bỏ qua việc upstream có giải phóng tài nguyên hay không khi đó là yêu cầu quan trọng.

## 8. Bảo vệ toàn bộ test bằng JUnit timeout

Timeout ở `StepVerifier` bảo vệ quá trình đọc publisher. Tuy nhiên, test cũng có thể kẹt trước khi tạo được `FluxExchangeResult`, ví dụ server không trả response header hoặc cấu hình test bị lỗi. Có thể đặt thêm timeout ở cấp test method:

```java
import java.util.concurrent.TimeUnit;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.Timeout;

class EventControllerTest {

    @Test
    @Timeout(value = 8, unit = TimeUnit.SECONDS)
    void verifiesStreamingResponseWithinBoundedTime() {
        // Thực hiện request, lấy response stream và dùng StepVerifier.
    }
}
```

JUnit timeout là lớp bảo vệ tổng thể. Nó không thay thế assertion về event, không giải thích stream im lặng bao lâu và không phải chính sách timeout của ứng dụng. Nên có timeout ở cấp thao tác phù hợp, sau đó dùng JUnit để giới hạn tổng thời gian test.

## 9. Những lỗi thường gặp khi kiểm thử luồng không kết thúc

### Dùng `expectBodyList` cho stream vô hạn

`expectBodyList(...)` cần đọc body cho đến khi hoàn tất. Nếu publisher không gửi `onComplete`, test sẽ tiếp tục chờ. Dùng `returnResult(...)` và `StepVerifier` để kiểm tra một phần stream rồi hủy.

### Gọi `verify()` không có giới hạn thời gian

`StepVerifier.verify()` có thể chờ vô hạn nếu tín hiệu mong đợi không đến. Với test có thể bị treo, dùng `verify(Duration)` hoặc cấu hình timeout có kiểm soát. Không dựa vào một timeout mặc định toàn cục mà không hiểu phạm vi ảnh hưởng.

### Nhầm response timeout với body idle timeout

Server có thể gửi status và header ngay lập tức nhưng ngừng phát body. Khi đó exchange đã thành công, trong khi subscription của body vẫn chờ. Dùng `StepVerifier` để giới hạn thời gian đọc hoặc kiểm tra khoảng không có event.

### Dùng `Thread.sleep` để đợi event

`Thread.sleep` chỉ dừng thread của test; nó không chứng minh event đã được phát hoặc subscription đã nhận event. Dùng `StepVerifier` để đồng bộ với tín hiệu reactive. Với logic dựa trên thời gian, cân nhắc virtual time.

### Hủy subscription quá sớm

Nếu gọi `thenCancel()` ngay sau subscription, test có thể kết thúc trước khi event đầu tiên đến. Hãy đặt `expectNext`, `assertNext` hoặc `expectNextCount` trước `thenCancel()` để nêu rõ dữ liệu cần quan sát.

### Dùng virtual time cho transport thật

Virtual scheduler của Reactor không tự tua nhanh thời gian trong Netty hoặc hệ điều hành. Dùng virtual time cho publisher có scheduler được điều khiển; dùng timeout thật cho test HTTP integration.

### Đặt timeout quá ngắn

Timeout chỉ vài mili giây có thể thất bại ngẫu nhiên khi CI tải cao hoặc scheduler bị trễ. Đặt giới hạn theo chu kỳ phát event, thời gian khởi động và độ trễ chấp nhận được. Giữ timeout đủ ngắn để phát hiện lỗi nhưng đủ rộng cho môi trường thực tế.

### Không xác nhận cancellation

Test có thể kết thúc nhưng nguồn vẫn giữ tài nguyên nếu cancellation không truyền ngược đúng cách. Với stream mở lâu, hãy kiểm tra `doOnCancel`, cleanup hoặc việc giải phóng subscription khi client hủy.

## 10. Chọn chiến lược timeout theo mục tiêu

| Mục tiêu kiểm thử | Cách làm |
|---|---|
| Server không trả status/headers | Cấu hình `WebTestClient.responseTimeout(...)` và timeout tổng của test. |
| Stream phát một vài event rồi tiếp tục vô hạn | `returnResult(...)`, `StepVerifier.expectNext(...)`, `thenCancel()`, `verify(Duration)`. |
| Stream phải im lặng trong một khoảng xác định | `expectSubscription()`, `expectNoEvent(Duration)`, rồi `thenCancel()`. |
| Publisher phải phát event trong một giới hạn | `expectNext(...)` cùng `verify(Duration)` để giới hạn thời gian xác minh. |
| Ứng dụng phải chuyển sang fallback khi không có dữ liệu | Reactor `timeout(Duration, fallback)` và assertion trên fallback. |
| Stream phải tự đóng sau tổng thời gian | `take(Duration)` và xác nhận completion. |
| Kiểm tra timer/interval mà không chờ thật | `StepVerifier.withVirtualTime(...)` với publisher tạo bên trong supplier. |
| Đảm bảo tài nguyên được giải phóng khi client dừng đọc | `thenCancel()` và xác nhận cleanup/cancellation upstream. |

## 11. Checklist cho bài test streaming

- [ ] Xác định endpoint trả body hữu hạn hay stream có thể không kết thúc.
- [ ] Kiểm tra status và header trước khi đọc body.
- [ ] Dùng `returnResult(...)` cho body streaming thay vì chờ toàn bộ body hoàn tất.
- [ ] Dùng `StepVerifier` để kiểm tra đúng số event cần thiết.
- [ ] Gọi `thenCancel()` khi test không cần đọc phần còn lại của stream.
- [ ] Đặt `verify(Duration)` để giới hạn thời gian chờ tín hiệu.
- [ ] Dùng `expectNoEvent(Duration)` chỉ khi thực sự cần xác nhận khoảng im lặng.
- [ ] Cấu hình response timeout cho giai đoạn exchange khi cần.
- [ ] Dùng Reactor `timeout(...)` hoặc `take(...)` chỉ khi đó là hành vi của ứng dụng cần kiểm tra.
- [ ] Chỉ dùng virtual time cho scheduler/publisher có thể được điều khiển bởi virtual scheduler.
- [ ] Đặt JUnit `@Timeout` làm giới hạn tổng cho test có nguy cơ treo.
- [ ] Kiểm tra cancellation và cleanup nếu stream quản lý tài nguyên dài hạn.

Với luồng không kết thúc, mục tiêu của test thường là quan sát một phần dữ liệu trong thời gian giới hạn rồi chủ động hủy subscription. `WebTestClient.returnResult(...)` cung cấp body publisher, `StepVerifier` kiểm tra các tín hiệu cần thiết và `verify(Duration)` ngăn test chờ vô hạn. Timeout ở client, publisher và test runner cần được dùng đúng phạm vi để vừa phát hiện lỗi vừa giữ được ý nghĩa của một response streaming lâu dài.
