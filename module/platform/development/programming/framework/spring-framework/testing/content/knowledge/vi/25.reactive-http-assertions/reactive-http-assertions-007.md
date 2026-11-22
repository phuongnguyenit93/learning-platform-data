# StepVerifier để xác nhận phần tử, hoàn tất, lỗi và hủy

Trong ứng dụng reactive, một phương thức có thể trả về `Mono<T>` hoặc `Flux<T>` thay vì trả về một giá trị ngay lập tức. Kết quả chỉ được phát khi có subscriber đăng ký. Vì vậy, kiểm tra một publisher không đơn giản là so sánh một biến trả về; test cần đăng ký, quan sát các tín hiệu được phát và xác nhận publisher kết thúc theo cách mong đợi.

Reactor Test cung cấp `StepVerifier` để mô tả hành vi đó như một kịch bản. Test khai báo các tín hiệu mong đợi theo thứ tự: subscription, phần tử, lỗi hoặc hoàn tất. Khi gọi `verify()`, `StepVerifier` mới thực hiện subscription và kiểm tra publisher có tuân theo kịch bản hay không.

## 1. StepVerifier kiểm tra những gì?

Một reactive publisher có thể phát ba nhóm tín hiệu chính:

- `onNext`: phát một phần tử dữ liệu.
- `onComplete`: kết thúc bình thường, không còn phần tử tiếp theo.
- `onError`: kết thúc do lỗi.

Subscription còn có thể nhận yêu cầu về số lượng phần tử (demand) và có thể bị hủy (cancel). `StepVerifier` cho phép test kiểm tra các tín hiệu và tương tác này theo đúng thứ tự.

Ví dụ, một `Flux` phát hai tên rồi hoàn tất có thể được kiểm tra bằng:

```java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

StepVerifier.create(Flux.just("An", "Binh"))
    .expectNext("An", "Binh")
    .expectComplete()
    .verify();
```

Kịch bản trên yêu cầu publisher phát lần lượt `An`, `Binh`, sau đó phát tín hiệu hoàn tất. Nếu publisher phát thêm phần tử, phát sai thứ tự hoặc kết thúc bằng lỗi, test thất bại.

## 2. Chuẩn bị dependency Reactor Test

`StepVerifier` nằm trong artifact `reactor-test`, tách khỏi `reactor-core`. Với Gradle và Spring Boot dependency management, khai báo test dependency:

```groovy
dependencies {
    testImplementation 'io.projectreactor:reactor-test'
}
```

Để Boot quản lý phiên bản Reactor đồng bộ với ứng dụng, không tự chọn một phiên bản `reactor-test` khác với Reactor đang dùng. Nếu dự án không dùng Spring Boot dependency management, cần chọn phiên bản `reactor-test` tương thích với `reactor-core`.

## 3. Xác nhận các phần tử được phát

`StepVerifier.create(publisher)` tạo kịch bản kiểm tra cho publisher. Một số assertion thường dùng:

- `expectNext(value...)`: yêu cầu một hoặc nhiều phần tử có giá trị và thứ tự chính xác.
- `assertNext(consumer)`: lấy phần tử kế tiếp để kiểm tra nhiều thuộc tính bằng assertion thông thường.
- `expectNextMatches(predicate)`: kiểm tra phần tử kế tiếp bằng điều kiện boolean.
- `expectNextCount(n)`: xác nhận có `n` phần tử tiếp theo nhưng không kiểm tra nội dung của chúng.
- `expectNextSequence(iterable)`: xác nhận publisher phát một chuỗi giá trị theo thứ tự.

Ví dụ với đối tượng nghiệp vụ:

```java
import static org.assertj.core.api.Assertions.assertThat;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

record Order(String id, int quantity) {
}

Flux<Order> orders = Flux.just(
    new Order("ORD-1", 2),
    new Order("ORD-2", 5)
);

StepVerifier.create(orders)
    .assertNext(order -> {
        assertThat(order.id()).isEqualTo("ORD-1");
        assertThat(order.quantity()).isEqualTo(2);
    })
    .expectNextMatches(order ->
        order.id().equals("ORD-2") && order.quantity() == 5)
    .expectComplete()
    .verify();
```

`assertNext` phù hợp khi cần nhiều assertion hoặc thông báo lỗi rõ ràng. `expectNextMatches` phù hợp với một điều kiện ngắn. Nếu chỉ cần kiểm tra số lượng phần tử mà không quan tâm giá trị, dùng `expectNextCount`; không nên dùng nó khi nội dung từng phần tử là một phần của hợp đồng nghiệp vụ.

## 4. Xác nhận publisher hoàn tất bình thường

Một `Mono` có thể phát đúng một giá trị rồi hoàn tất, hoặc hoàn tất mà không phát giá trị nào. `Flux` cũng có thể phát nhiều phần tử rồi hoàn tất.

```java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.create(Mono.just("saved"))
    .expectNext("saved")
    .expectComplete()
    .verify();

StepVerifier.create(Mono.empty())
    .expectComplete()
    .verify();
```

`expectComplete()` xác nhận tín hiệu `onComplete`. Một cách viết ngắn hơn cho trường hợp chỉ cần xác nhận hoàn tất là `verifyComplete()`:

```java
StepVerifier.create(Mono.just(42))
    .expectNext(42)
    .verifyComplete();
```

Nếu publisher được kỳ vọng phát đúng một giá trị, hãy xác nhận cả phần tử lẫn hoàn tất. Chỉ gọi `expectNext(42)` rồi dừng kịch bản có thể bỏ sót việc publisher còn phát thêm dữ liệu hoặc kết thúc bằng lỗi.

## 5. Xác nhận lỗi và nội dung lỗi

Khi publisher kết thúc bằng lỗi, test cần xác nhận loại exception và thông tin cần thiết. `StepVerifier` cung cấp nhiều cách:

- `expectError(Class)`: xác nhận kiểu exception.
- `expectErrorMessage(message)`: xác nhận message.
- `expectErrorMatches(predicate)`: xác nhận lỗi bằng điều kiện.
- `expectErrorSatisfies(consumer)`: chạy assertion trên exception thực tế.

Ví dụ service phát lỗi khi không tìm thấy dữ liệu:

```java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

Mono<String> loadAccount(String id) {
    return Mono.error(new IllegalArgumentException(
        "Account not found: " + id
    ));
}

StepVerifier.create(loadAccount("A-404"))
    .expectErrorMatches(error ->
        error instanceof IllegalArgumentException
            && error.getMessage().equals("Account not found: A-404"))
    .verify();
```

Hoặc dùng `expectErrorSatisfies` để kiểm tra bằng AssertJ:

```java
import static org.assertj.core.api.Assertions.assertThat;

import reactor.test.StepVerifier;

StepVerifier.create(loadAccount("A-404"))
    .expectErrorSatisfies(error -> {
        assertThat(error)
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessage("Account not found: A-404");
    })
    .verify();
```

`onError` là tín hiệu kết thúc của publisher. Vì vậy, sau `expectError...` không có phần tử tiếp theo hoặc `expectComplete()` trong cùng kịch bản. Nếu lỗi được ứng dụng chuyển thành một HTTP response bởi WebFlux exception handler, hãy kiểm tra response bằng `WebTestClient`; `StepVerifier` kiểm tra publisher ở tầng reactive.

## 6. Kiểm tra publisher không phát phần tử hoặc không kết thúc

`Mono.empty()` hoàn tất mà không phát dữ liệu. `Mono.never()` không phát dữ liệu, cũng không hoàn tất và không phát lỗi. Hai trường hợp này khác nhau và cần assertion riêng:

```java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.create(Mono.empty())
    .verifyComplete();

StepVerifier.create(Mono.<String>never())
    .expectSubscription()
    .thenCancel()
    .verify();
```

Với `Mono.never()`, test chủ động hủy subscription. Không chờ `expectComplete()` vì publisher này không phát tín hiệu hoàn tất.

## 7. Xác nhận cancellation

Cancellation quan trọng khi một consumer không còn cần dữ liệu. Ví dụ, client ngắt kết nối hoặc chỉ đọc một phần stream. Có thể dùng `doOnCancel(...)` để quan sát publisher có nhận tín hiệu hủy hay không:

```java
import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

AtomicBoolean cancelled = new AtomicBoolean();

Flux<Long> source = Flux.interval(Duration.ofMillis(100))
    .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(source)
    .expectSubscription()
    .expectNext(0L)
    .thenCancel()
    .verify(Duration.ofSeconds(2));

assertThat(cancelled).isTrue();
```

Kịch bản đợi subscription, nhận phần tử đầu tiên rồi gửi cancellation. Sau khi `verify(...)` hoàn tất, test kiểm tra callback hủy đã được gọi. Đây là cách kiểm tra publisher phản ứng với việc consumer dừng đọc.

Cancellation không đồng nghĩa với `onComplete` hoặc `onError`. Khi đã hủy, subscriber không còn yêu cầu publisher phát thêm tín hiệu cho mình. Vì vậy, dùng `thenCancel()` làm bước kết thúc của kịch bản thay vì nối thêm `expectComplete()`.

## 8. Kiểm tra backpressure và demand

Reactive Streams dùng demand để subscriber yêu cầu publisher phát tối đa bao nhiêu phần tử. `StepVerifier.create(publisher, initialRequest)` cho phép đặt số lượng yêu cầu ban đầu; `thenRequest(n)` tăng demand tại một thời điểm trong kịch bản.

Ví dụ bắt đầu với demand bằng 0, yêu cầu một phần tử, sau đó yêu cầu thêm hai phần tử:

```java
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

StepVerifier.create(Flux.range(1, 3), 0)
    .expectSubscription()
    .thenRequest(1)
    .expectNext(1)
    .thenRequest(2)
    .expectNext(2, 3)
    .expectComplete()
    .verify();
```

Kịch bản này giúp xác nhận publisher chỉ phát dữ liệu theo demand mà subscriber đã yêu cầu. Nó hữu ích khi kiểm tra publisher tự xây dựng, operator tùy chỉnh hoặc luồng cần kiểm soát lượng dữ liệu được tiêu thụ.

Không phải mọi test nghiệp vụ đều cần kiểm tra backpressure. Với một `Mono` đơn giản hoặc một `Flux` hữu hạn dùng trong xử lý thông thường, xác nhận phần tử và tín hiệu kết thúc thường đã đủ. Hãy kiểm tra demand khi hành vi đó là một phần của yêu cầu kỹ thuật.

## 9. Kiểm thử thời gian với virtual time

Publisher có thể phụ thuộc thời gian, ví dụ `delayElements`, `interval`, timeout hoặc retry có delay. Chờ thời gian thực làm test chậm và dễ không ổn định. `StepVerifier.withVirtualTime(...)` cho phép tiến đồng hồ ảo để kiểm tra hành vi theo thời gian mà không phải chờ tương ứng ngoài đời.

```java
import java.time.Duration;

import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;

StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1)).take(3))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(0L)
    .thenAwait(Duration.ofSeconds(2))
    .expectNext(1L, 2L)
    .expectComplete()
    .verify();
```

Publisher phải được tạo bên trong `Supplier` truyền cho `withVirtualTime`. Cách này giúp StepVerifier cài virtual scheduler trước khi publisher được lắp ráp. Nếu tạo publisher trước rồi mới truyền vào, operator có thể đã giữ scheduler thực và test không nhận được lợi ích của virtual time.

`thenAwait(duration)` tiến thời gian ảo mà không yêu cầu một tín hiệu cụ thể trong khoảng đó. `expectNoEvent(duration)` cũng tiến thời gian nhưng sẽ thất bại nếu có tín hiệu xuất hiện trong khoảng được kiểm tra. Khi dùng `expectNoEvent`, cần xác nhận subscription trước để sự kiện subscription không bị tính là một event ngoài dự kiến.

## 10. Đặt giới hạn thời gian cho verify

`verify()` đăng ký publisher và chờ cho đến khi kịch bản hoàn tất. Nếu publisher không phát tín hiệu cần thiết, test có thể chờ vô hạn. Có thể truyền timeout vào `verify(Duration)`:

```java
import java.time.Duration;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

StepVerifier.create(Mono.just("done"))
    .expectNext("done")
    .expectComplete()
    .verify(Duration.ofSeconds(2));
```

Có thể cấu hình timeout mặc định cho các kịch bản trong một test suite bằng `StepVerifier.setDefaultTimeout(...)`. Timeout là giới hạn bảo vệ test khỏi chờ mãi; hãy đặt giá trị đủ rộng cho môi trường CI, tránh đặt quá ngắn khiến test thất bại ngẫu nhiên khi máy bận.

Đối với publisher không bao giờ kết thúc, như `Mono.never()` hoặc stream vô hạn, kịch bản phải chủ động hủy hoặc giới hạn số phần tử. Đặt timeout không thay thế việc xác định điều kiện kết thúc mong muốn.

## 11. Dùng StepVerifier với service và WebFlux controller

Trong unit test service reactive, có thể kiểm tra trực tiếp publisher mà service trả về:

```java
import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class InventoryService {
    Mono<Integer> availableQuantity(String sku) {
        return Mono.just(12);
    }
}

class InventoryServiceTests {

    private final InventoryService service = new InventoryService();

    @Test
    void returnsAvailableQuantity() {
        StepVerifier.create(service.availableQuantity("SKU-1"))
            .expectNext(12)
            .verifyComplete();
    }
}
```

Với WebFlux controller, có hai phạm vi kiểm thử thường gặp:

- Dùng `StepVerifier` để kiểm tra publisher trả về từ service hoặc component reactive, tập trung vào phần tử, lỗi, hoàn tất và cancellation.
- Dùng `WebTestClient` để kiểm tra HTTP request/response. Nếu cần kiểm tra body streaming, có thể lấy publisher từ `returnResult(...)` rồi dùng `StepVerifier` kiểm tra các phần tử phát ra.

Ví dụ với response body của một endpoint streaming:

```java
import java.time.Duration;

import reactor.test.StepVerifier;
import org.springframework.test.web.reactive.server.FluxExchangeResult;
import org.springframework.test.web.reactive.server.WebTestClient;

FluxExchangeResult<String> result = webTestClient.get()
    .uri("/events")
    .exchange()
    .expectStatus().isOk()
    .returnResult(String.class);

StepVerifier.create(result.getResponseBody())
    .expectNext("created", "updated")
    .thenCancel()
    .verify(Duration.ofSeconds(2));
```

Ở đây `WebTestClient` xác nhận request và HTTP status; `StepVerifier` kiểm tra publisher của response body. Hai công cụ bổ sung cho nhau ở hai tầng khác nhau.

## 12. Những lỗi thường gặp khi viết StepVerifier

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Test chờ mãi ở `verify()` | Publisher không kết thúc, hoặc kịch bản đang chờ tín hiệu không được phát; đặt timeout và xem lại terminal signal |
| Test báo sai phần tử | Thứ tự `expectNext` không khớp, publisher phát dữ liệu khác hoặc có operator thay đổi kết quả |
| Test mong hoàn tất nhưng nhận lỗi | Publisher kết thúc bằng `onError`; xác nhận lỗi mong đợi bằng `expectError...` |
| Test mong lỗi nhưng publisher hoàn tất | Điều kiện lỗi không xảy ra hoặc lỗi đã bị xử lý thành giá trị/empty publisher |
| Test cancellation không kích hoạt callback | Kịch bản chưa gọi `thenCancel()` hoặc publisher chưa nhận được subscription |
| Test backpressure phát dữ liệu ngoài dự kiến | Demand ban đầu hoặc các bước `thenRequest(...)` chưa phản ánh đúng hợp đồng |
| Test thời gian chạy lâu | Đang dùng scheduler thực; kiểm tra việc tạo publisher bên trong `withVirtualTime(...)` |
| Test virtual time không tiến như mong đợi | Publisher đã được lắp ráp trước khi virtual scheduler được cài hoặc operator dùng scheduler riêng |

Khi debug, hãy đọc kịch bản từ đầu đến cuối như một chuỗi tín hiệu. Xác định test đang chờ `onNext`, `onComplete`, `onError` hay cancellation, sau đó đối chiếu với publisher thực tế và các operator được áp dụng.

## 13. Quy trình viết một kịch bản StepVerifier

1. Xác định publisher là `Mono` hay `Flux` và hành vi kết thúc mong đợi.
2. Dùng `StepVerifier.create(...)` hoặc `withVirtualTime(...)` nếu publisher phụ thuộc thời gian.
3. Nếu cần, xác nhận subscription bằng `expectSubscription()`.
4. Kiểm tra dữ liệu bằng `expectNext`, `assertNext`, `expectNextMatches` hoặc `expectNextCount`.
5. Kiểm tra terminal signal bằng `expectComplete()` hoặc `expectError...`.
6. Nếu kiểm tra backpressure, điều khiển demand bằng `thenRequest(...)`; nếu kiểm tra hủy, kết thúc bằng `thenCancel()`.
7. Gọi `verify(...)` với timeout phù hợp để thực sự chạy kịch bản và giới hạn thời gian chờ.

`StepVerifier` biến hành vi reactive thành một kịch bản có thể đọc và kiểm tra được: publisher phát dữ liệu gì, kết thúc thế nào, phản ứng ra sao khi subscriber yêu cầu thêm hoặc hủy đăng ký. Khi xác nhận đầy đủ các tín hiệu liên quan, test sẽ phát hiện được lỗi về giá trị, thứ tự, terminal signal, backpressure và cancellation.
