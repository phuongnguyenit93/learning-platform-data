# `PublisherProbe`: xác minh nhánh dự phòng đã được đăng ký

Trong module `REACTIVE_PROGRAMMING`, ta xây dựng và kiểm thử các pipeline bất đồng bộ theo hợp đồng Publisher–Subscriber và cơ chế backpressure của Reactive Streams, đồng thời thực hành `Mono`, `Flux`, toán tử, scheduler và xử lý lỗi trong hệ sinh thái Java. Khi một pipeline có nhánh dự phòng, chỉ kiểm tra giá trị cuối cùng đôi khi chưa đủ để chứng minh nhánh nào đã chạy. Ta cần biết Publisher thay thế có thực sự được subscribe hay không, có nhận demand hay bị hủy giữa chừng.

Reactor Test cung cấp `PublisherProbe` để quan sát những sự kiện này mà vẫn giữ nguyên tín hiệu của Publisher được bọc. Công cụ này đặc biệt hữu ích với các toán tử như `switchIfEmpty`, `onErrorResume` hoặc những luồng có nhánh phụ chỉ được kích hoạt trong một điều kiện nhất định. Bài học tập trung vào việc xác minh nhánh dự phòng đã được đăng ký và tiêu thụ theo đúng kịch bản.

## 1. Vì sao cần kiểm tra việc subscribe vào nhánh dự phòng?

Giả sử một service tìm dữ liệu trong cache. Nếu cache rỗng, pipeline chuyển sang database:

```java
Mono<Product> product = cache.find(productId)
    .switchIfEmpty(database.find(productId));
```

Kết quả cuối có thể là một `Product` trong cả hai trường hợp: cache trả dữ liệu hoặc database trả dữ liệu dự phòng. Nếu test chỉ kiểm tra `expectNext(product)`, nó chưa chắc đã xác nhận database có được gọi khi cache rỗng. Có thể pipeline đang phát một giá trị từ nguồn khác hoặc nhánh dự phòng chưa được kích hoạt như dự kiến.

Ta cần kiểm tra hai điều độc lập:

- **Kết quả quan sát được:** subscriber nhận giá trị nào, lỗi nào hoặc tín hiệu hoàn tất nào?
- **Đường đi thực thi:** Publisher dự phòng có được subscribe, có nhận request và có bị cancel không?

`StepVerifier` kiểm tra tín hiệu mà subscriber nhận. `PublisherProbe` bổ sung bằng chứng về subscription và demand ở một Publisher cụ thể. Kết hợp hai công cụ giúp test xác nhận cả kết quả lẫn nhánh đã được chọn.

## 2. `PublisherProbe` ghi nhận những gì?

`PublisherProbe<T>` bọc một Publisher và cung cấp các phương thức để lấy lại Publisher dưới dạng `Mono<T>` hoặc `Flux<T>`. Probe theo dõi các sự kiện subscription mà không thay đổi các phần tử được phát từ Publisher gốc.

Các phương thức thường dùng:

| Phương thức | Ý nghĩa |
|---|---|
| `PublisherProbe.of(publisher)` | Tạo probe bọc Publisher có sẵn |
| `PublisherProbe.empty()` | Tạo probe cho một Publisher rỗng |
| `probe.mono()` | Lấy Publisher dạng `Mono` để đưa vào pipeline |
| `probe.flux()` | Lấy Publisher dạng `Flux` để đưa vào pipeline |
| `assertWasSubscribed()` | Xác nhận Publisher đã nhận subscription |
| `assertWasNotSubscribed()` | Xác nhận Publisher chưa từng được subscribe |
| `assertWasRequested()` | Xác nhận subscription đã nhận demand |
| `assertWasNotRequested()` | Xác nhận chưa có demand được gửi đến subscription |
| `assertWasCancelled()` | Xác nhận subscription đã bị hủy |
| `assertWasNotCancelled()` | Xác nhận subscription không bị hủy |
| `subscribeCount()` | Trả về số lần Publisher được subscribe |

Probe không thay thế `StepVerifier`. Nó không phải công cụ chính để xác minh payload, thứ tự phần tử hoặc nội dung lỗi. Hãy dùng `StepVerifier` cho các tín hiệu và dùng probe cho hành vi subscription của nhánh cần quan sát.

## 3. Chuẩn bị dependency Reactor Test

Trong dự án dùng Maven, thêm `reactor-test` ở phạm vi test và dùng cùng phiên bản Reactor với ứng dụng. Nếu dự án dùng Spring Boot dependency management, nên để BOM quản lý phiên bản thay vì tự chọn một phiên bản không tương thích.

```xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
```

Các import thường dùng:

```java
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.publisher.PublisherProbe;
```

## 4. Xác minh `switchIfEmpty` đã subscribe nhánh dự phòng

`switchIfEmpty` subscribe vào Publisher thay thế khi nguồn chính hoàn tất mà không phát phần tử nào. Ta tạo probe quanh Publisher dự phòng rồi kiểm tra sau khi `StepVerifier` kết thúc:

```java
@Test
void subscribesToFallbackWhenPrimaryIsEmpty() {
    PublisherProbe<String> fallback =
        PublisherProbe.of(Mono.just("from-fallback"));

    Mono<String> result = Mono.<String>empty()
        .switchIfEmpty(fallback.mono());

    StepVerifier.create(result)
        .expectNext("from-fallback")
        .verifyComplete();

    fallback.assertWasSubscribed();
    fallback.assertWasRequested();
    fallback.assertWasNotCancelled();
    assertEquals(1, fallback.subscribeCount());
}
```

Test xác nhận:

1. Nguồn chính hoàn tất rỗng.
2. `switchIfEmpty` chuyển sang Publisher dự phòng.
3. Subscriber nhận giá trị từ nhánh dự phòng.
4. Probe ghi nhận một subscription và có demand.
5. Nhánh dự phòng hoàn tất bình thường, không bị cancel.

Việc kiểm tra `assertWasSubscribed()` là bằng chứng trực tiếp rằng nhánh dự phòng đã được đăng ký. `expectNext` bổ sung bằng chứng rằng giá trị từ nhánh đó đến được downstream.

## 5. Xác minh nhánh dự phòng không được subscribe khi nguồn chính có dữ liệu

Khi nguồn chính phát giá trị, `switchIfEmpty` không cần subscribe Publisher thay thế:

```java
@Test
void doesNotSubscribeToFallbackWhenPrimaryEmits() {
    PublisherProbe<String> fallback =
        PublisherProbe.of(Mono.just("fallback"));

    Mono<String> result = Mono.just("from-primary")
        .switchIfEmpty(fallback.mono());

    StepVerifier.create(result)
        .expectNext("from-primary")
        .verifyComplete();

    fallback.assertWasNotSubscribed();
    assertEquals(0, fallback.subscribeCount());
}
```

Đây là kiểm tra quan trọng để phát hiện việc gọi nhánh dự phòng ngoài ý muốn. Nếu Publisher dự phòng đại diện cho một truy vấn database hoặc request HTTP tốn kém, không subscribe nhánh đó khi cache đã có dữ liệu giúp tránh I/O thừa.

## 6. Phân biệt hoàn tất rỗng với lỗi

`switchIfEmpty` chỉ chuyển nhánh khi nguồn chính hoàn tất mà không phát phần tử. Nó không xử lý `onError`. Khi nguồn chính phát lỗi, lỗi đi xuống downstream và Publisher dự phòng của `switchIfEmpty` không được subscribe.

```java
@Test
void doesNotUseSwitchIfEmptyFallbackForError() {
    PublisherProbe<String> fallback =
        PublisherProbe.of(Mono.just("fallback"));

    Mono<String> result = Mono.<String>error(
            new IllegalStateException("primary failed")
        )
        .switchIfEmpty(fallback.mono());

    StepVerifier.create(result)
        .expectErrorMessage("primary failed")
        .verify();

    fallback.assertWasNotSubscribed();
}
```

Nếu nghiệp vụ cần fallback khi có lỗi, dùng `onErrorResume` thay vì `switchIfEmpty`:

```java
@Test
void subscribesToFallbackWhenPrimaryErrors() {
    PublisherProbe<String> fallback =
        PublisherProbe.of(Mono.just("recovered"));

    Mono<String> result = Mono.<String>error(
            new IOException("temporary failure")
        )
        .onErrorResume(IOException.class, error -> fallback.mono());

    StepVerifier.create(result)
        .expectNext("recovered")
        .verifyComplete();

    fallback.assertWasSubscribed();
    fallback.assertWasRequested();
}
```

Test này chứng minh nhánh dự phòng do `onErrorResume` được subscribe khi lỗi khớp kiểu `IOException`. Lỗi không khớp kiểu sẽ tiếp tục truyền xuống downstream và không kích hoạt nhánh đó.

## 7. Probe xác minh subscription, không chỉ việc tạo Publisher

Trong Java, đối số của một phương thức được đánh giá trước khi phương thức được gọi. Vì vậy, biểu thức tạo Publisher thay thế có thể được thực thi trong lúc lắp ráp pipeline, dù Publisher đó chưa được subscribe.

```java
Mono<Product> result = cache.find(productId)
    .switchIfEmpty(database.find(productId));
```

Nếu `database.find(productId)` có side effect ngay khi phương thức được gọi, side effect đó có thể xảy ra ngay lúc lắp ráp. Một API reactive đúng thiết kế thường chỉ mô tả công việc và trì hoãn I/O đến subscription. Nếu cần trì hoãn cả lời gọi tạo Publisher, dùng `Mono.defer`:

```java
Mono<Product> result = cache.find(productId)
    .switchIfEmpty(Mono.defer(() -> database.find(productId)));
```

Có thể kiểm tra riêng số lần factory được gọi và việc Publisher được subscribe:

```java
AtomicInteger factoryCalls = new AtomicInteger();

Mono<String> fallbackSource = Mono.defer(() -> {
    factoryCalls.incrementAndGet();
    return Mono.just("fallback");
});

PublisherProbe<String> fallback = PublisherProbe.of(fallbackSource);

Mono<String> result = Mono.<String>empty()
    .switchIfEmpty(fallback.mono());

assertEquals(0, factoryCalls.get());

StepVerifier.create(result)
    .expectNext("fallback")
    .verifyComplete();

assertEquals(1, factoryCalls.get());
fallback.assertWasSubscribed();
```

Probe xác nhận subscription; `AtomicInteger` trong ví dụ xác nhận factory bên trong `defer` chỉ chạy khi nhánh được subscribe. Hai kiểm tra này trả lời hai câu hỏi khác nhau.

## 8. Xác minh nhánh dự phòng bị cancel

Một nhánh có thể được subscribe nhưng sau đó bị hủy vì downstream không còn cần dữ liệu. Ví dụ, `take(1)` hủy nguồn sau khi nhận phần tử đầu tiên:

```java
@Test
void fallbackSubscriptionIsCancelledWhenDownstreamStopsEarly() {
    PublisherProbe<Integer> fallback = PublisherProbe.of(
        Flux.just(10, 20, 30)
    );

    Flux<Integer> result = Flux.<Integer>empty()
        .switchIfEmpty(fallback.flux())
        .take(1);

    StepVerifier.create(result)
        .expectNext(10)
        .verifyComplete();

    fallback.assertWasSubscribed();
    fallback.assertWasRequested();
    fallback.assertWasCancelled();
}
```

Test xác nhận nhánh dự phòng đã được subscribe, phát phần tử đầu tiên và nhận cancellation khi `take(1)` kết thúc downstream. Điều này hữu ích khi nhánh dự phòng giữ tài nguyên hoặc thực hiện streaming dài hạn.

Cancellation truyền đến Publisher theo hợp đồng reactive, nhưng không bảo đảm mọi tác vụ bên dưới dừng tức thời. Nếu nhánh dự phòng gọi API blocking hoặc side effect đã được thực hiện, khả năng dừng phụ thuộc implementation của API đó.

## 9. Kiểm tra số lần subscribe và nhiều subscriber

`subscribeCount()` giúp xác minh một Publisher dự phòng được subscribe bao nhiêu lần. Điều này quan trọng khi nguồn chính có thể rỗng trong nhiều subscription độc lập:

```java
PublisherProbe<String> fallback =
    PublisherProbe.of(Mono.just("cached-default"));

Mono<String> result = Mono.<String>empty()
    .switchIfEmpty(fallback.mono());

StepVerifier.create(result)
    .expectNext("cached-default")
    .verifyComplete();

StepVerifier.create(result)
    .expectNext("cached-default")
    .verifyComplete();

assertEquals(2, fallback.subscribeCount());
fallback.assertWasSubscribed();
fallback.assertWasRequested();
```

Publisher lạnh thường chạy lại phần công việc của nó cho mỗi subscription. Vì vậy, hai subscription độc lập có thể kích hoạt nhánh dự phòng hai lần. Nếu nghiệp vụ cần chia sẻ một lần tải dữ liệu, hãy dùng cơ chế chia sẻ/cache có chủ đích và kiểm thử vòng đời của nó. Không nên giả định `PublisherProbe` tự chia sẻ hoặc cache Publisher được bọc.

## 10. Dùng probe với `Mono<Void>` và nhánh side effect

Một nhánh dự phòng có thể không phát giá trị mà chỉ thực hiện một thao tác như ghi log, gửi audit event hoặc cập nhật metric. `PublisherProbe.empty()` phù hợp với Publisher rỗng như `Mono<Void>`:

```java
@Test
void subscribesToAuditFallbackWhenPrimaryIsEmpty() {
    PublisherProbe<Void> auditProbe = PublisherProbe.empty();

    Mono<Void> result = findPrimaryRecord()
        .switchIfEmpty(auditProbe.mono());

    StepVerifier.create(result)
        .verifyComplete();

    auditProbe.assertWasSubscribed();
    auditProbe.assertWasRequested();
}
```

Trong ví dụ, probe chứng minh nhánh audit đã được subscribe và nhận demand. Nếu cần xác minh nội dung audit event hoặc tham số truyền vào service, hãy kết hợp mock/argument captor hoặc một `TestPublisher`/fake phù hợp. `PublisherProbe.empty()` không tự kiểm tra side effect bên trong một service thật.

## 11. Probe kết hợp với `StepVerifier` và mock service

Một test thường có ba lớp xác minh:

1. `StepVerifier` kiểm tra tín hiệu cuối cùng mà client quan sát.
2. `PublisherProbe` kiểm tra nhánh dự phòng có được subscribe/request/cancel.
3. Mock hoặc fake kiểm tra lời gọi service, tham số và side effect ở ranh giới ngoài.

Ví dụ một service tìm trong cache rồi fallback database:

```java
class ProductService {
    private final ProductCache cache;
    private final ProductRepository repository;

    ProductService(ProductCache cache, ProductRepository repository) {
        this.cache = cache;
        this.repository = repository;
    }

    Mono<Product> find(String id) {
        return cache.find(id)
            .switchIfEmpty(Mono.defer(() -> repository.findById(id)));
    }
}
```

Trong unit test, có thể thay Publisher từ repository bằng một probe:

```java
PublisherProbe<Product> databaseProbe =
    PublisherProbe.of(Mono.just(product));

when(cache.find("p-10")).thenReturn(Mono.empty());
when(repository.findById("p-10")).thenReturn(databaseProbe.mono());

StepVerifier.create(service.find("p-10"))
    .expectNext(product)
    .verifyComplete();

databaseProbe.assertWasSubscribed();
verify(repository).findById("p-10");
```

Mock xác nhận phương thức repository được gọi để tạo Publisher. Probe xác nhận Publisher đó thực sự được subscribe. `StepVerifier` xác nhận sản phẩm đến được downstream. Nếu service tạo Publisher bằng `defer`, sự khác biệt giữa gọi factory và subscribe càng quan trọng.

## 12. Những điều `PublisherProbe` không chứng minh

Probe rất hữu ích nhưng có phạm vi cụ thể. Nó không chứng minh:

- Publisher dự phòng kết nối thành công tới database hoặc HTTP server thật.
- Một transaction đã commit hoặc rollback đúng.
- Nội dung request gửi đi chính xác nếu không kiểm tra mock/fake hoặc server.
- Toàn bộ các phần tử của một Flux đã được xử lý nếu test chỉ yêu cầu một phần.
- Một side effect bên ngoài đã hoàn tất chỉ vì Publisher được subscribe.
- Một Publisher đã thực sự phát giá trị cụ thể; việc đó nên được xác minh bằng `StepVerifier`.

Probe cũng không tự tạo backpressure policy. Nó ghi nhận demand được gửi tới subscription, còn hành vi khi producer phát nhanh hơn consumer vẫn phụ thuộc Publisher và các toán tử trong pipeline.

## 13. Những lỗi thường gặp khi dùng PublisherProbe

| Sai lầm | Hệ quả | Cách xử lý |
|---|---|---|
| Chỉ kiểm tra output và kết luận fallback đã chạy | Có thể không phát hiện nhánh dự phòng chưa được subscribe | Dùng `assertWasSubscribed()` |
| Nhầm gọi factory với subscribe Publisher | Bỏ sót side effect lúc lắp ráp hoặc nhánh chưa được tiêu thụ | Dùng `Mono.defer` và probe để kiểm tra riêng hai thời điểm |
| Dùng `switchIfEmpty` để xử lý lỗi | Nhánh fallback không chạy khi nguồn phát `onError` | Dùng `onErrorResume` nếu muốn phục hồi lỗi |
| Chỉ kiểm tra `assertWasSubscribed` | Không biết nhánh có nhận demand hoặc bị cancel không | Bổ sung assertion phù hợp với kịch bản |
| Mong probe xác minh payload | Test không kiểm tra nội dung thực tế | Dùng `StepVerifier.expectNext...` |
| Mong probe kiểm tra side effect bên trong service | Chỉ biết Publisher được subscribe | Dùng mock, fake hoặc integration test |
| Bọc một Publisher dùng chung nhưng giả định mỗi subscriber có nhánh riêng | Có thể hiểu sai số lần subscribe và vòng đời | Kiểm tra `subscribeCount()` và chính sách share/cache |

## 14. Quy trình kiểm thử nhánh dự phòng

Khi kiểm thử một nhánh fallback, hãy thực hiện:

1. **Xác định điều kiện kích hoạt:** nguồn chính rỗng, phát lỗi hay một điều kiện nghiệp vụ khác.
2. **Tạo probe quanh Publisher dự phòng:** dùng `PublisherProbe.of(...)` hoặc `PublisherProbe.empty()`.
3. **Đưa `probe.mono()` hoặc `probe.flux()` vào đúng nhánh:** giữ nguyên cấu trúc pipeline cần kiểm tra.
4. **Dùng `StepVerifier` kiểm tra tín hiệu:** giá trị, lỗi, hoàn tất hoặc cancellation mà downstream nhận.
5. **Assert subscription:** `assertWasSubscribed()` nếu nhánh phải chạy; `assertWasNotSubscribed()` nếu nhánh không được chọn.
6. **Assert demand/cancellation khi cần:** kiểm tra `assertWasRequested()` hoặc `assertWasCancelled()` theo hợp đồng của test.
7. **Kiểm tra số lần subscribe:** dùng `subscribeCount()` khi pipeline có retry, nhiều subscriber hoặc nhánh được gọi lặp.
8. **Kiểm tra side effect riêng:** dùng mock/fake hoặc integration test cho database, HTTP và transaction.

`PublisherProbe` giúp biến câu hỏi “nhánh dự phòng có thực sự được kích hoạt không?” thành một assertion cụ thể. Khi kết hợp nó với `StepVerifier`, ta kiểm tra được cả tín hiệu đầu ra lẫn đường đi subscription, nhờ đó các pipeline dùng `switchIfEmpty`, `onErrorResume` và các nhánh reactive có điều kiện trở nên dễ kiểm thử và ít phụ thuộc vào suy đoán hơn.
