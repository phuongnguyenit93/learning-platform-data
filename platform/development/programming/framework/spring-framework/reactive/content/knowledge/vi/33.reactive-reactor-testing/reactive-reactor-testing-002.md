# Kiểm tra dữ liệu, complete, error và thời hạn verify với Reactor StepVerifier

**Module:** Spring Framework – reactive  
**Chủ đề cha:** Kiểm thử Reactor  
**Bài học:** Kiểm tra dữ liệu, complete, error và thời hạn verify

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Đọc và kiểm thử chuỗi tín hiệu Reactive Streams: `onSubscribe` → nhiều `onNext` → đúng một tín hiệu terminal `onComplete` hoặc `onError`; phân biệt `cancel` do subscriber chủ động.
2. Dùng `reactor-test` và `StepVerifier` để kiểm tra giá trị, thứ tự, số phần tử, predicate và thuộc tính của object.
3. Kiểm tra luồng kết thúc bình thường, luồng rỗng, luồng thất bại và luồng không bao giờ kết thúc.
4. Phân biệt `expectComplete().verify()`, `verifyComplete()`, `expectError(...).verify()` và `verifyError(...)`.
5. Đặt thời hạn cho quá trình **xác minh của test** bằng `verify(Duration)`, thay vì để CI treo vô thời hạn.
6. Hiểu rõ `verify(Duration)` khác với toán tử `Mono.timeout(...)` hoặc `Flux.timeout(...)` nằm trong mã ứng dụng.
7. Viết kiểm thử thời gian với `expectNoEvent`, `thenAwait` và `StepVerifier.withVirtualTime` mà không phải chờ hàng giờ thực.
8. Kiểm thử backpressure bằng initial request bằng 0, `thenRequest` và kiểm thử cancellation bằng `thenCancel`.
9. Chạy bộ test Java 17+/Maven/JUnit 5/Spring Boot BOM với kết quả xác định, không dùng `Thread.sleep` để đo thời gian một cách mong manh.
10. Chẩn đoán assertion failure, quên terminal expectation, request thiếu demand và cấu hình virtual time sai.

## 1. Điều thật sự cần kiểm thử: tín hiệu, không chỉ dữ liệu

`Mono<T>` và `Flux<T>` đều triển khai `Publisher<T>`. Một publisher không đơn thuần là “danh sách trả về bất đồng bộ”; nó có **giao thức tín hiệu** giữa publisher và subscriber.

Luồng cơ bản:

```text
Subscriber                                    Publisher
    |                                            |
    |---------- subscribe() -------------------->|
    |<--------- onSubscribe(subscription) -------|
    |---------- request(n) --------------------->|
    |<--------- onNext(item 1) ------------------|
    |<--------- onNext(item 2) ------------------|
    |<--------- onComplete() --------------------|
    |                                            |
```

Khi có lỗi:

```text
onSubscribe -> onNext(A) -> onNext(B) -> onError(exception)
```

Không có `onComplete` sau `onError`. Trong một subscription đúng chuẩn, `onComplete` và `onError` loại trừ nhau. `onNext` không được phát giá trị `null` theo Reactive Streams contract.

Một subscriber cũng có thể gọi `cancel`:

```text
onSubscribe -> request(2) -> onNext(A) -> onNext(B) -> cancel()
```

`cancel` là lời yêu cầu dừng subscription chứ không phải terminal signal mà publisher gửi cho subscriber. Vì vậy khi test hủy luồng, đừng chờ `onComplete` sau `cancel`.

### 1.1. Sự khác nhau giữa Mono và Flux

| Publisher | Số `onNext` | Terminal bình thường | Ví dụ |
| --- | --- | --- | --- |
| `Mono.just("OK")` | 1 | `onComplete` | Tìm được đối tượng. |
| `Mono.empty()` | 0 | `onComplete` | Không có dữ liệu nhưng không lỗi. |
| `Mono.error(ex)` | 0 | `onError` | Lỗi tra cứu. |
| `Flux.just(1,2,3)` | 3 | `onComplete` | Danh sách có thứ tự. |
| `Flux.empty()` | 0 | `onComplete` | Tập kết quả rỗng. |
| `Flux.concat(Flux.just(1), Flux.never())` | Ít nhất 1 trong ví dụ | Không tự terminal | Luồng giữ mở. |

**Một điểm rất hay bị nhầm:** `Mono.empty()` là kết thúc thành công, không phải exception. Nếu nghiệp vụ coi việc không tìm thấy là lỗi, source hoặc service phải chuyển nó thành lỗi tường minh, chẳng hạn `switchIfEmpty(Mono.error(new NotFoundException(...)))`; `StepVerifier` chỉ kiểm tra contract thật đang tồn tại.

## 2. StepVerifier là gì và chạy khi nào?

`StepVerifier` nằm trong artifact `io.projectreactor:reactor-test`. Nó đóng vai một subscriber có khả năng diễn đạt **kịch bản kỳ vọng** và so sánh chính xác tín hiệu thực tế.

Quy trình:

```text
1. Tạo Mono/Flux cần test
           |
           v
2. StepVerifier.create(publisher)
           |
           v
3. Khai báo từng kỳ vọng
   expectNext / assertNext / expectComplete / expectError
           |
           v
4. Gọi verify() / verify(Duration)
           |
           v
5. StepVerifier subscribe, nhận tín hiệu, so sánh,
   ném AssertionError nếu có mismatch
```

Ví dụ ngắn:

```java
Flux<String> names = Flux.just("An", "Bình", "Chi");

StepVerifier.create(names)
        .expectNext("An", "Bình", "Chi")
        .verifyComplete();
```

Ba giá trị được kiểm tra **đúng thứ tự**. `verifyComplete()` còn xác nhận publisher phát `onComplete`, không chỉ phát đủ ba phần tử.

Đừng quên bước verify:

```java
StepVerifier.create(Flux.just(1, 2))
        .expectNext(1, 2)
        .expectComplete();
// Chưa gọi verify(): không có xác minh nào được thực hiện.
```

`StepVerifier` builder chỉ mô tả kịch bản. Các method `verify...()` là nơi phép kiểm chứng chạy và chặn thread test cho đến khi kết thúc, thất bại, hủy theo kịch bản, hoặc hết hạn xác minh.

## 3. Các cách kiểm tra dữ liệu onNext

### 3.1. expectNext: giá trị và thứ tự chính xác

```java
StepVerifier.create(Flux.just(10, 20, 30))
        .expectNext(10)
        .expectNext(20, 30)
        .verifyComplete();
```

Kiểm tra dựa trên `equals` của đối tượng. Với record Java hoặc value object có `equals` được triển khai chính xác, đây là cách đơn giản nhất.

```java
record Product(long id, String name) {}

StepVerifier.create(Mono.just(new Product(7, "Keyboard")))
        .expectNext(new Product(7, "Keyboard"))
        .verifyComplete();
```

Nếu class DTO không triển khai `equals` hợp lý, hai object có field giống nhau vẫn có thể bị coi là khác nhau. Khi đó hãy dùng `assertNext` để kiểm tra field.

### 3.2. expectNextMatches: xác nhận predicate

```java
StepVerifier.create(Flux.just(5, 12, 18))
        .expectNextMatches(n -> n > 0)
        .expectNextMatches(n -> n % 2 == 0)
        .expectNextMatches(n -> n >= 18)
        .verifyComplete();
```

Predicate phải trả `true` cho đúng **phần tử tiếp theo**. Phần tử đến sai thứ tự hoặc predicate trả false đều làm test thất bại. Không dùng `expectNextMatches` để bỏ qua phần tử không khớp; nó **không phải `filter`**.

Dùng khi giá trị có thuộc tính quan trọng nhưng không muốn ép exact object, ví dụ ID phát sinh động, timestamp hoặc dữ liệu được chuẩn hóa.

### 3.3. assertNext: nhiều assertion trên một phần tử

```java
StepVerifier.create(
        Mono.just(new Product(7, "Keyboard")))
        .assertNext(product -> {
            assertEquals(7L, product.id());
            assertEquals("Keyboard", product.name());
            assertTrue(product.name().length() > 3);
        })
        .verifyComplete();
```

Các assertion `assertEquals` và `assertTrue` là từ JUnit. Có thể dùng AssertJ `assertThat`. Nếu assertion bên trong lambda lỗi, StepVerifier truyền lỗi assertion để test thất bại.

`assertNext` phù hợp khi DTO có nhiều field hoặc cần mô tả bất biến nghiệp vụ. Nó là alias diễn đạt dễ hiểu của `consumeNextWith`.

### 3.4. expectNextCount: kiểm tra số lượng

```java
StepVerifier.create(Flux.range(1, 100))
        .expectNext(1)
        .expectNextCount(98)
        .expectNext(100)
        .verifyComplete();
```

`expectNextCount(98)` chỉ xác nhận **98 lần phát dữ liệu tiếp theo**, không kiểm tra giá trị của chúng. Nếu giá trị từng phần tử quan trọng, đừng chỉ dùng count; kết hợp với `expectNext`, `expectNextMatches` hoặc `assertNext`.

Mỗi phần tử vẫn được tiêu thụ để kịch bản có thể tiếp tục nhận tín hiệu terminal.

### 3.5. expectNextSequence: kiểm tra Iterable

```java
List<String> expected = List.of("an", "binh", "chi");

StepVerifier.create(
        Flux.just("an", "binh", "chi"))
        .expectNextSequence(expected)
        .verifyComplete();
```

Kiểm tra từng phần tử với thứ tự xác định bởi Iterable. Nó hữu ích khi expected data được tạo sẵn từ fixture. Nếu thứ tự output không được bảo đảm (ví dụ `flatMap` xử lý đồng thời), hãy chọn contract phù hợp: sắp xếp trước khi so sánh nếu nghiệp vụ cho phép, hoặc thu thập tập hợp và so sánh không theo thứ tự. Không ép thứ tự ngẫu nhiên chỉ để khiến test thiếu ổn định.

### 3.6. recordWith và consumeRecordedWith

Khi cần kiểm tra toàn bộ nhóm dữ liệu thay vì chỉ số lượng:

```java
StepVerifier.create(Flux.just("A", "B", "C"))
        .recordWith(ArrayList::new)
        .expectNextCount(3)
        .consumeRecordedWith(values -> {
            assertEquals(List.of("A", "B", "C"), values);
        })
        .verifyComplete();
```

`recordWith` khởi động một session ghi lại dữ liệu `onNext`, `consumeRecordedWith` kết thúc việc ghi và đưa tập hợp cho assertion. Nhớ giới hạn số item của test; không ghi một stream vô hạn vào list.

Đoạn code minh họa cần import `java.util.ArrayList` và `java.util.List` cùng JUnit assertions.

## 4. Kiểm tra complete

### 4.1. expectComplete và verifyComplete

Hai cách viết tương đương khi muốn đòi hỏi kết thúc bình thường:

```java
StepVerifier.create(Flux.just(1, 2))
        .expectNext(1, 2)
        .expectComplete()
        .verify();
```

và:

```java
StepVerifier.create(Flux.just(1, 2))
        .expectNext(1, 2)
        .verifyComplete();
```

`verifyComplete()` là shortcut kết hợp `expectComplete()` rồi verify. Nếu publisher phát thêm item không được chờ đợi, phát error, hoặc không complete, test phải thất bại.

### 4.2. Mono.empty và Flux.empty

```java
StepVerifier.create(Mono.<String>empty())
        .verifyComplete();

StepVerifier.create(Flux.<Integer>empty())
        .expectComplete()
        .verify();
```

Cả hai bài kiểm tra thành công vì source phát `onComplete` mà không có `onNext`.

Đừng viết:

```java
StepVerifier.create(Mono.<String>empty())
        .expectNext("fallback")
        .verifyComplete();
```

Đoạn này là ví dụ **cố ý sai**: `Mono.empty()` không phát `"fallback"` nên StepVerifier nhận complete sớm và ném assertion failure. Muốn nhận fallback, hãy thay đổi **mã ứng dụng** bằng `defaultIfEmpty` hoặc `switchIfEmpty` rồi test đúng contract.

### 4.3. Kiểm tra không có giá trị sau dữ liệu dự kiến

`verifyComplete()` xác nhận không có thêm onNext trước terminal. Ví dụ `Flux.just(1,2,3)` không thể vượt qua một kịch bản chỉ `expectNext(1,2).verifyComplete()` vì phần tử 3 xuất hiện trước onComplete.

Do đó StepVerifier kiểm tra cả **kết quả**, **thứ tự** và **cách kết thúc**, không chỉ một mảng expected.

## 5. Kiểm tra error

### 5.1. expectError: kiểm tra terminal error

```java
StepVerifier.create(
        Flux.just(1, 2)
                .concatWith(Mono.<Integer>error(
                        new IllegalArgumentException("bad input"))))
        .expectNext(1, 2)
        .expectError(IllegalArgumentException.class)
        .verify();
```

Error là terminal: không được có `onComplete` sau `onError`. Lưu ý `Flux.error(...)` được dùng để **phát lỗi theo tín hiệu reactive**, không giống việc ném exception tùy ý trước khi publisher được trả về.

Nếu service ném lỗi đồng bộ ngay lúc gọi method, StepVerifier chưa có Publisher để subscribe. Khi cần kiểm thử hành vi lỗi *tại lúc subscribe*, dùng `Mono.defer`, `Flux.defer` hoặc `Mono.fromCallable` nếu đúng với contract.

### 5.2. expectErrorMessage: kiểm tra thông điệp

```java
StepVerifier.create(
        Mono.<String>error(
                new IllegalStateException("permission denied")))
        .expectErrorMessage("permission denied")
        .verify();
```

Cách này chỉ kiểm tra message, không bắt buộc loại exception. Với mã lỗi có quy tắc rõ ràng, có thể kết hợp predicate hoặc consumer để kiểm tra cả type và fields.

### 5.3. expectErrorMatches: predicate của Throwable

```java
StepVerifier.create(
        Mono.<String>error(
                new IllegalArgumentException("age must be positive")))
        .expectErrorMatches(error ->
                error instanceof IllegalArgumentException
                && error.getMessage().contains("age"))
        .verify();
```

Predicate phù hợp khi nhiều thuộc tính lỗi cùng quan trọng. Không match message quá cụ thể nếu nó là chi tiết implementation không ổn định hoặc đã được dịch theo locale.

### 5.4. expectErrorSatisfies: assertion tường minh

```java
StepVerifier.create(
        Mono.<String>error(
                new IllegalStateException("invalid state")))
        .expectErrorSatisfies(error -> {
            assertInstanceOf(IllegalStateException.class, error);
            assertEquals("invalid state", error.getMessage());
        })
        .verify();
```

`assertInstanceOf` là JUnit 5 assertion. Kiểm tra lỗi bằng kiểu cụ thể hoặc mã lỗi nghiệp vụ thường bền hơn kiểm tra stacktrace.

### 5.5. verifyError và verifyErrorMessage

`verifyError(SomeException.class)` và `verifyErrorMessage("...")` là shortcut dùng khi không cần thêm kỳ vọng trước error.

```java
StepVerifier.create(
        Mono.<Integer>error(new ArithmeticException("/ by zero")))
        .verifyError(ArithmeticException.class);
```

Khi có các `onNext` trước lỗi, dùng `expectNext(...).expectError(...).verify()` để mô tả đầy đủ thứ tự. Đừng viết `verifyComplete()` cho publisher đã phát error; đó là hai terminal contract khác nhau.

## 6. Thời hạn của verify: bảo vệ test không treo

### 6.1. Mặc định verify có thể chờ vô hạn

Theo Reactor Test, khi chưa cấu hình default timeout, `verify()` và các shortcut như `verifyComplete()` có thể chờ không giới hạn. Điều này nguy hiểm trong CI nếu source là `Flux.never()` hoặc kịch bản đang chờ demand chưa bao giờ được request.

Ví dụ bẫy:

```java
StepVerifier.create(Flux.never())
        .expectComplete()
        .verify(); // Có thể treo mãi: source không complete.
```

Đây là **ví dụ cố ý không chạy**. Không đưa nó vào test thật nếu chưa đặt thời hạn.

### 6.2. verify(Duration) là deadline cho quá trình xác minh

```java
StepVerifier.create(Flux.just(1, 2, 3))
        .expectNext(1, 2, 3)
        .expectComplete()
        .verify(Duration.ofSeconds(2));
```

Đối số `Duration.ofSeconds(2)` là thời gian **thực tối đa để StepVerifier chạy toàn kịch bản**. Nếu không đủ tín hiệu trước hạn, StepVerifier ném `AssertionError` cho bài test. Nó không tự biến Publisher thành `onError(TimeoutException)`, và không tạo timeout nghiệp vụ cho subscriber production.

Phân biệt:

| Khái niệm | Nằm ở đâu? | Khi quá hạn | Mục tiêu |
| --- | --- | --- | --- |
| `verify(Duration)` | Kịch bản Reactor Test | Test thất bại bởi `AssertionError` khi verify timeout | Tránh test treo, đặt deadline kiểm chứng. |
| `StepVerifier.setDefaultTimeout(Duration)` | Cấu hình toàn cục của StepVerifier được tạo sau khi gọi | Các verify không chỉ định hạn sẽ dùng mặc định đó | Chính sách timeout nhất quán cho test suite. |
| `Mono.timeout(Duration)` / `Flux.timeout(Duration)` | Publisher trong ứng dụng | Cancel upstream và phát `TimeoutException` downstream nếu không có fallback | Kiểm soát thời gian chờ tín hiệu nghiệp vụ. |
| `thenAwait(Duration)` | Một bước của StepVerifier | Chờ thời gian thật hoặc tiến đồng hồ ảo | Cho tác vụ có thời gian phát dữ liệu. |
| `expectNoEvent(Duration)` | Một bước của StepVerifier | Assertion fail nếu có signal trong khoảng đó | Đảm bảo không có tín hiệu quá sớm. |

`verify(Duration)` trả về `Duration` biểu diễn thời gian verify đã dùng (thời gian thật), không phải giá trị do source phát.

```java
Duration elapsed = StepVerifier.create(Mono.just("OK"))
        .expectNext("OK")
        .expectComplete()
        .verify(Duration.ofSeconds(2));

assertTrue(!elapsed.isNegative());
```

Không nên assert millisecond chính xác vì máy CI có tốc độ khác nhau; đo performance bằng benchmark/metric riêng khi cần.

### 6.3. Kiểm thử rằng verify timeout thật sự phát hiện luồng treo

```java
@Test
void verifyDeadlineRejectsNever() {
    AssertionError problem = assertThrows(AssertionError.class, () ->
            StepVerifier.create(Flux.<Integer>never())
                    .expectSubscription()
                    .expectComplete()
                    .verify(Duration.ofMillis(150)));

    assertNotNull(problem);
}
```

`Flux.never()` không phát dữ liệu và cũng không complete/error, nên StepVerifier timeout theo test deadline. `assertThrows` ở đây là **cách chứng minh khả năng phát hiện treo**, không phải một lỗi sản phẩm phải bị bỏ qua. Thời hạn 150 ms chỉ dành cho ví dụ; chọn 1–5 giây trong CI có tải lớn nếu có async thực.

### 6.4. Default timeout: dùng cẩn thận vì trạng thái toàn cục

```java
StepVerifier.setDefaultTimeout(Duration.ofSeconds(5));
try {
    StepVerifier.create(Mono.just("OK"))
            .expectNext("OK")
            .verifyComplete();
} finally {
    StepVerifier.resetDefaultTimeout();
}
```

`setDefaultTimeout` ảnh hưởng tới StepVerifier **được tạo sau lời gọi đó**. Đừng thay global default giữa các bài test chạy song song vì có thể tác động đến test khác. Ưu tiên `verify(Duration)` trên từng bài hoặc cấu hình ở test bootstrap được kiểm soát.

## 7. Thời gian bên trong publisher: virtual time

Các operator như `delayElement`, `delayElements`, `interval`, `timeout` và `retryWhen` có thể phụ thuộc vào scheduler. Test thời gian thật với `Thread.sleep(10_000)` thường chậm và dễ không ổn định.

`StepVerifier.withVirtualTime` thay scheduler thông thường bằng `VirtualTimeScheduler` và cho phép dịch chuyển thời gian logic. Các duration dài ngày có thể được kiểm thử nhanh mà không phải đợi thời gian thật.

### 7.1. Dùng Supplier để source được tạo sau khi bật đồng hồ ảo

Đúng:

```java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofDays(1)))
        .expectSubscription()
        .thenAwait(Duration.ofDays(1))
        .expectNext(0L)
        .verifyComplete();
```

Không nên tạo một pipeline có scheduler trước rồi chỉ return nó từ Supplier:

```java
Mono<Long> tooEarly = Mono.delay(Duration.ofDays(1));

StepVerifier.withVirtualTime(() -> tooEarly)
        .expectSubscription()
        .thenAwait(Duration.ofDays(1))
        .expectNext(0L)
        .verifyComplete();
```

Đoạn thứ hai là **anti-pattern** được đưa ra để giải thích rủi ro; một số operator sẽ bắt scheduler quá sớm và không chịu sự điều khiển của đồng hồ ảo. Tạo publisher **bên trong lambda Supplier**, hoặc dùng method được gọi khi Supplier thực thi.

### 7.2. thenAwait: cho phép thời gian trôi

```java
StepVerifier.withVirtualTime(
        () -> Flux.interval(Duration.ofHours(1)).take(3))
        .expectSubscription()
        .thenAwait(Duration.ofHours(3))
        .expectNext(0L, 1L, 2L)
        .verifyComplete();
```

`Flux.interval` phát 0, 1, 2 sau lần lượt 1, 2, 3 giờ logic. `thenAwait` dịch đồng hồ ảo cho phép các sự kiện đến rồi tiếp tục kiểm tra. Với nguồn hữu hạn và lịch đơn giản, test chạy nhanh. Trong hệ thống thật, nếu source dùng scheduler tùy biến không bị StepVerifier điều khiển, kết quả virtual time không như mong đợi.

### 7.3. expectNoEvent: không được phát sớm

```java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofHours(24)))
        .expectSubscription()
        .expectNoEvent(Duration.ofHours(23))
        .thenAwait(Duration.ofHours(1))
        .expectNext(0L)
        .verifyComplete();
```

Kịch bản đòi hỏi:

1. Có subscription.
2. Trong 23 giờ logic đầu tiên không có `onNext`, `onError` hay `onComplete`.
3. Sau thêm một giờ, nhận `onNext(0L)`.
4. Cuối cùng complete.

**Bẫy quan trọng:** `expectNoEvent` cũng coi `onSubscribe` là một event. Nếu dùng `expectNoEvent(...)` ngay đầu kịch bản trước `expectSubscription()`, test có thể fail ngay khi subscribe. Viết `expectSubscription().expectNoEvent(...)` khi muốn kiểm tra khoảng im lặng sau subscription.

`expectNoEvent` có khả năng phát hiện tín hiệu **đến quá sớm**. Ngược lại, `thenAwait` chỉ cho thời gian trôi, không tuyên bố rằng không được phát signal trong khoảng đó.

### 7.4. Test operator timeout nghiệp vụ

Giả sử ứng dụng có:

```java
Mono<Long> remoteLike =
        Mono.delay(Duration.ofSeconds(10))
                .timeout(Duration.ofSeconds(3));
```

Kỳ vọng: quá ba giây mà chưa có item, operator timeout phát `java.util.concurrent.TimeoutException`.

```java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofSeconds(10))
                .timeout(Duration.ofSeconds(3)))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(3))
        .expectError(TimeoutException.class)
        .verify();
```

Ở đây timeout phát ra từ **mã ứng dụng**, không phải `verify(Duration)`. Dùng virtual time để tránh chờ ba giây thật. `TimeoutException` cần import `java.util.concurrent.TimeoutException`.

Nên thêm hạn xác minh thời gian thật khi tích hợp nhiều scheduler/phụ thuộc ngoài:

```java
StepVerifier.withVirtualTime(
        () -> Mono.delay(Duration.ofSeconds(10))
                .timeout(Duration.ofSeconds(3)))
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(3))
        .expectError(TimeoutException.class)
        .verify(Duration.ofSeconds(5));
```

Lúc này có **hai thời hạn độc lập**: ba giây ảo cho business timeout và tối đa năm giây thật để tránh test treo. Đừng nhầm chúng.

## 8. Backpressure và cancel trong StepVerifier

### 8.1. Kiểm tra request(n)

Mặc định StepVerifier thường yêu cầu đủ lượng demand để nhận chuỗi. Muốn kiểm tra backpressure, đặt initial request bằng 0:

```java
StepVerifier.create(Flux.range(1, 5), 0)
        .expectSubscription()
        .thenRequest(2)
        .expectNext(1, 2)
        .thenRequest(3)
        .expectNext(3, 4, 5)
        .verifyComplete();
```

Luồng chỉ được yêu cầu hai phần tử ở đợt đầu và ba phần tử ở đợt sau. Một publisher tuân thủ demand không được gửi `onNext` trước khi có request dương. Kịch bản này cũng kiểm tra thứ tự.

Nếu bỏ `thenRequest(3)` mà vẫn đòi thêm phần tử, test có thể chờ mãi (hoặc fail do verify deadline). Đây là lỗi test không cấp đủ demand chứ chưa chắc là lỗi sản phẩm.

### 8.2. Cancel có chủ đích

```java
AtomicBoolean cancelled = new AtomicBoolean();

Flux<Integer> source = Flux.range(1, 100)
        .doOnCancel(() -> cancelled.set(true));

StepVerifier.create(source, 2)
        .expectNext(1, 2)
        .thenCancel()
        .verify();

assertTrue(cancelled.get());
```

`thenCancel` kết thúc kịch bản bằng hành động hủy subscription. Sau cancel **không** viết `expectComplete`. `doOnCancel` hỗ trợ xác nhận việc source nhìn thấy tín hiệu hủy.

Đừng dùng `thenCancel` để che một publisher vốn phải complete; nếu business contract yêu cầu complete, hãy dùng `verifyComplete` để test phát hiện stream bị treo.

### 8.3. Test các publisher dài hạn

Với `Flux.interval` hoặc stream live không tự complete, có ba cách phổ biến:

- Kiểm tra số item đầu rồi `thenCancel()` nếu contract là subscription dài hạn.
- Dùng `take(n)` trong chính pipeline cần test nếu nghiệp vụ chỉ yêu cầu n item; lúc đó downstream sẽ thấy complete, upstream nhận cancel.
- Dùng `withVirtualTime` khi behavior phụ thuộc scheduler và thời gian.

Luôn quản lý subscription để không để scheduler/tài nguyên test tồn tại sau test. Không tự gọi `subscribe()` rồi quên `dispose()`.

## 9. Đặt tên scenario để dễ tìm lỗi

`StepVerifierOptions.create().scenarioName("...")` gán tên cho kịch bản, trong khi `as("...")` mô tả kỳ vọng gần nhất.

```java
StepVerifier.create(
        Flux.just(10, 20),
        StepVerifierOptions.create()
                .scenarioName("two pricing values"))
        .expectNext(10)
        .as("first price")
        .expectNext(20)
        .as("second price")
        .verifyComplete();
```

Tên giúp tìm lỗi trong log CI. Lưu ý nếu AssertionError được ném trực tiếp bởi JUnit/AssertJ trong `assertNext`, mô tả StepVerifier không nhất thiết được thêm vào thông điệp lỗi; hãy viết assertion message có ý nghĩa.

## 10. Bộ project Java 17 + Maven + JUnit 5 chạy được

Ví dụ dưới đây sử dụng Java 17+, Maven, BOM từ **Spring Boot 3.3.5** để đồng bộ phiên bản Reactor, `reactor-core` và `reactor-test`. Nó không khởi chạy web server; trọng tâm là kiểm thử **service trả Mono/Flux**.

Cấu trúc:

```text
reactor-step-verifier-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   └── ReactiveExamples.java
    └── test/java/demo/
        └── ReactiveExamplesTest.java
```

### 10.1. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>reactor-step-verifier-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Boot parent quản lý version Java test dependencies và cấu hình surefire. `reactor-test` chỉ được dùng trong test scope; production code không phụ thuộc trực tiếp vào StepVerifier. Dự án này cố tình không thêm WebFlux starter để tránh tạo những dependency không liên quan đến việc kiểm tra publisher.

### 10.2. ReactiveExamples.java

```java
package demo;

import java.time.Duration;
import java.util.concurrent.atomic.AtomicBoolean;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

public final class ReactiveExamples {

    public record Reading(String sensor, int value) {
    }

    public Flux<Reading> readings() {
        return Flux.just(
                new Reading("temp", 21),
                new Reading("temp", 22),
                new Reading("cpu", 66));
    }

    public Mono<Reading> firstBySensor(String sensor) {
        return readings()
                .filter(r -> r.sensor().equals(sensor))
                .next();
    }

    public Flux<Integer> numbers() {
        return Flux.range(1, 5);
    }

    public Flux<Integer> evenSquares() {
        return Flux.range(1, 6)
                .filter(n -> n % 2 == 0)
                .map(n -> n * n);
    }

    public Mono<String> emptyResult() {
        return Mono.empty();
    }

    public Flux<Integer> errorAfterTwo() {
        return Flux.just(1, 2)
                .concatWith(Mono.<Integer>error(
                        new IllegalArgumentException("bad input")));
    }

    public Mono<Long> delayedValue() {
        return Mono.delay(Duration.ofDays(1));
    }

    public Flux<Long> hourlyTicks() {
        return Flux.interval(Duration.ofHours(1)).take(3);
    }

    public Mono<Long> delayedWithTimeout() {
        return Mono.delay(Duration.ofSeconds(10))
                .timeout(Duration.ofSeconds(3));
    }

    public Flux<Integer> neverFinishes() {
        return Flux.just(1)
                .concatWith(Flux.<Integer>never());
    }

    public Flux<Integer> cancellableNumbers(
            AtomicBoolean cancelObserved) {
        return Flux.range(1, 100)
                .doOnCancel(() -> cancelObserved.set(true));
    }
}
```

Mỗi method trả về publisher lazy. Các method dùng `Mono.delay` hoặc `Flux.interval` tạo pipeline khi được gọi. Như vậy với virtual time, chỉ cần gọi method trong lambda của `withVirtualTime` là đủ để scheduler được thiết lập trước.

Các giá trị ví dụ được chọn cố định để test không phụ thuộc network/database hay đồng hồ hệ thống.

### 10.3. ReactiveExamplesTest.java

```java
package demo;

import java.time.Duration;
import java.util.List;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Flux;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ReactiveExamplesTest {

    private final ReactiveExamples examples = new ReactiveExamples();

    @Test
    void verifiesAllValuesAndComplete() {
        StepVerifier.create(examples.readings())
                .expectNext(
                        new ReactiveExamples.Reading("temp", 21),
                        new ReactiveExamples.Reading("temp", 22),
                        new ReactiveExamples.Reading("cpu", 66))
                .verifyComplete();
    }

    @Test
    void verifiesValuesWithPredicates() {
        StepVerifier.create(examples.readings())
                .expectNextMatches(r ->
                        "temp".equals(r.sensor()) && r.value() == 21)
                .expectNextMatches(r -> r.value() > 20)
                .expectNextMatches(r ->
                        "cpu".equals(r.sensor()) && r.value() >= 60)
                .verifyComplete();
    }

    @Test
    void verifiesMonoFieldsWithAssertNext() {
        StepVerifier.create(examples.firstBySensor("temp"))
                .assertNext(reading -> {
                    assertEquals("temp", reading.sensor());
                    assertEquals(21, reading.value());
                })
                .verifyComplete();
    }

    @Test
    void verifiesSequenceAndCount() {
        StepVerifier.create(examples.numbers())
                .expectNextSequence(List.of(1, 2, 3, 4, 5))
                .verifyComplete();

        StepVerifier.create(examples.evenSquares())
                .expectNext(4)
                .expectNextCount(1)
                .expectNext(36)
                .verifyComplete();
    }

    @Test
    void verifiesEmptyCompletion() {
        StepVerifier.create(examples.emptyResult())
                .verifyComplete();

        StepVerifier.create(examples.firstBySensor("unknown"))
                .verifyComplete();
    }

    @Test
    void verifiesErrorAfterTwoValues() {
        StepVerifier.create(examples.errorAfterTwo())
                .expectNext(1, 2)
                .expectErrorSatisfies(error -> {
                    assertInstanceOf(
                            IllegalArgumentException.class, error);
                    assertEquals("bad input", error.getMessage());
                })
                .verify(Duration.ofSeconds(2));
    }

    @Test
    void verifiesErrorByPredicate() {
        StepVerifier.create(examples.errorAfterTwo())
                .expectNext(1, 2)
                .expectErrorMatches(error ->
                        error instanceof IllegalArgumentException
                        && error.getMessage().contains("bad"))
                .verify(Duration.ofSeconds(2));
    }

    @Test
    void verifiesCompleteWithinDeadline() {
        Duration elapsed = StepVerifier.create(examples.numbers())
                .expectNext(1, 2, 3, 4, 5)
                .expectComplete()
                .verify(Duration.ofSeconds(2));

        assertTrue(!elapsed.isNegative());
    }

    @Test
    void verifierDeadlineRejectsNeverCompletingSource() {
        AssertionError problem = assertThrows(
                AssertionError.class, () ->
                        StepVerifier.create(
                                Flux.<Integer>never())
                                .expectSubscription()
                                .expectComplete()
                                .verify(Duration.ofMillis(150)));

        assertNotNull(problem);
    }

    @Test
    void verifiesBoundedDemand() {
        StepVerifier.create(examples.numbers(), 0)
                .expectSubscription()
                .thenRequest(2)
                .expectNext(1, 2)
                .thenRequest(3)
                .expectNext(3, 4, 5)
                .verifyComplete();
    }

    @Test
    void verifiesCancellationWasObservedUpstream() {
        AtomicBoolean cancelled = new AtomicBoolean();

        StepVerifier.create(
                        examples.cancellableNumbers(cancelled), 2)
                .expectNext(1, 2)
                .thenCancel()
                .verify();

        assertTrue(cancelled.get());
    }

    @Test
    void usesVirtualTimeInsteadOfWaitingADay() {
        StepVerifier.withVirtualTime(examples::delayedValue)
                .expectSubscription()
                .expectNoEvent(Duration.ofHours(23))
                .thenAwait(Duration.ofHours(1))
                .expectNext(0L)
                .verifyComplete();
    }

    @Test
    void verifiesScheduledFluxItemsWithVirtualTime() {
        StepVerifier.withVirtualTime(examples::hourlyTicks)
                .expectSubscription()
                .thenAwait(Duration.ofHours(3))
                .expectNext(0L, 1L, 2L)
                .verifyComplete();
    }

    @Test
    void verifiesPublisherTimeoutWithVirtualTime() {
        StepVerifier.withVirtualTime(
                        examples::delayedWithTimeout)
                .expectSubscription()
                .thenAwait(Duration.ofSeconds(3))
                .expectError(TimeoutException.class)
                .verify(Duration.ofSeconds(5));
    }

    @Test
    void namedScenarioIsMoreReadableOnFailure() {
        StepVerifier.create(
                        examples.numbers(),
                        StepVerifierOptions.create()
                                .scenarioName("numbers 1 to 5"))
                .expectNext(1)
                .as("first number")
                .expectNextCount(3)
                .expectNext(5)
                .verifyComplete();
    }
}
```

Đây là một class test JUnit độc lập, dùng 15 test case. Nó kiểm tra:

- Giá trị record, predicate, field, thứ tự và số phần tử.
- Mono rỗng hoàn thành bình thường.
- Flux phát dữ liệu rồi lỗi.
- Verify hoàn tất trước deadline, và deadline phát hiện source không bao giờ complete.
- Request demand thủ công và cancellation quan sát được ở upstream.
- Tạo dữ liệu phụ thuộc thời gian bằng virtual scheduler.
- Timeout nghiệp vụ của Publisher khác với timeout của StepVerifier.
- Tên scenario và mô tả expectation.

### 10.4. Chạy Maven

Trong thư mục chứa `pom.xml`:

```bash
mvn test
```

Với JDK 17+, Maven, dependency đã tải thành công và môi trường phù hợp, kết quả kỳ vọng là **15 tests thành công, 0 failures, 0 errors**. Log có thể chứa các dòng build/plugin và thời gian khác nhau nên không có một stdout cố định cần chép nguyên văn.

Dùng lệnh sau nếu muốn chỉ chạy class test:

```bash
mvn -Dtest=ReactiveExamplesTest test
```

Các lệnh này chạy JUnit thực sự; không cần ứng dụng Spring Boot khởi động HTTP server. Để chạy trong CI, thêm các bước build/test của project theo workflow của hệ thống.

### 10.5. Đọc một test theo từng tín hiệu

Ví dụ test giá trị và complete:

```java
StepVerifier.create(Flux.just("A", "B"))
        .expectSubscription()
        .expectNext("A")
        .expectNext("B")
        .expectComplete()
        .verify(Duration.ofSeconds(2));
```

Thứ tự logic:

```text
1. Subscribe vào Flux.just
2. Quan sát onSubscribe
3. Nhận onNext("A") và so sánh
4. Nhận onNext("B") và so sánh
5. Nhận onComplete
6. Kết thúc verify trước khi hết 2 giây thật
```

Nếu source trả `"B"` trước `"A"`, test fail tại bước 3. Nếu source phát error thay vì complete, test fail tại bước 5. Nếu source không terminal, test fail khi verify đạt thời hạn.

## 11. Bảng lựa chọn API nhanh

| Muốn xác minh | Cách diễn đạt |
| --- | --- |
| Giá trị cụ thể theo thứ tự | `expectNext(v1, v2)` |
| Field của object | `assertNext(item -> assertEquals(...))` |
| Điều kiện trên phần tử tiếp theo | `expectNextMatches(predicate)` |
| N phần tử, không quan tâm giá trị | `expectNextCount(n)` |
| Danh sách kỳ vọng | `expectNextSequence(expected)` |
| Kết thúc thành công | `expectComplete().verify()` hoặc `verifyComplete()` |
| Publisher rỗng complete | `StepVerifier.create(Mono.empty()).verifyComplete()` |
| Lỗi theo loại | `expectError(Type.class).verify()` |
| Lỗi theo thông điệp | `expectErrorMessage("...").verify()` |
| Lỗi theo logic bất kỳ | `expectErrorMatches(...)` hoặc `expectErrorSatisfies(...)` |
| Không để test treo | `expectComplete().verify(Duration.ofSeconds(2))` |
| Đặt default verify timeout | `StepVerifier.setDefaultTimeout(duration)` |
| Không được phát signal trong khoảng t | `expectSubscription().expectNoEvent(t)` |
| Cho thời gian trôi | `thenAwait(t)` |
| Thời gian ảo | `withVirtualTime(() -> publisher)` |
| Nhu cầu request thủ công | `create(source, 0).thenRequest(n)` |
| Chủ động hủy subscription | `thenCancel().verify()` |
| Đặt tên kịch bản | `StepVerifierOptions.scenarioName(...)`, `as(...)` |

Phần này là bản tra cứu, không thay các ví dụ có giải thích ở trên.

## 12. Những bẫy thực tế và cách sửa

### 12.1. Quên verify

**Sai:**

```java
StepVerifier.create(service.fetch())
        .expectNext("OK")
        .expectComplete();
```

Không có `verify` nên chưa thực thi kịch bản. **Đúng:** kết thúc bằng `verify()` hoặc `verifyComplete()`.

### 12.2. Test chỉ kiểm tra onNext, không terminal

**Sai về coverage:** chỉ xác nhận một phần tử nhưng không xác nhận publisher hoàn tất hay lỗi. Nếu hợp đồng là một phản hồi duy nhất, dùng `expectNext(expected).verifyComplete()`. Nếu hợp đồng là luồng sống lâu, dùng một kịch bản có `thenCancel()` và mô tả rõ tại sao không chờ complete.

### 12.3. Dùng expectNext khi DTO không có equals

**Triệu chứng:** object có các field đúng mà test vẫn báo khác. **Cách sửa:** dùng Java record/value object có equals đúng, hoặc `assertNext` kiểm tra field. Không override equals tùy tiện chỉ để khiến test pass nếu phá tính đúng đắn nghiệp vụ.

### 12.4. Nhầm thứ tự của flatMap

`flatMap` có thể phát các item của tác vụ bất đồng bộ theo thứ tự hoàn tất, không nhất thiết theo thứ tự đầu vào. Nếu nghiệp vụ bảo đảm order, dùng `concatMap` hoặc `flatMapSequential` khi phù hợp, rồi test đúng order; nếu không, thu thập và so sánh theo tập hợp thay vì gượng ép một thứ tự ngẫu nhiên.

### 12.5. Test Flux.never bằng verify() không giới hạn

**Triệu chứng:** CI treo. **Cách sửa:** luôn đặt thời hạn `verify(Duration)` khi source có thể không terminal; với live stream có chủ đích, dùng `thenCancel()` khi đủ dữ liệu hoặc khi kết thúc thời gian test.

### 12.6. Gọi expectNoEvent đầu tiên

`expectNoEvent` coi `onSubscribe` là một event. **Cách sửa:** `expectSubscription().expectNoEvent(...)`, hoặc dùng `thenAwait(...)` nếu chỉ cần thời gian trôi.

### 12.7. Tạo publisher trước withVirtualTime

**Triệu chứng:** test vẫn chờ thật hoặc treo. **Cách sửa:** tạo timer/interval/delay trong Supplier đưa vào `StepVerifier.withVirtualTime`. Kiểm tra scheduler custom: virtual time không tự điều khiển executor ngoài Reactor.

### 12.8. Dùng Thread.sleep rồi đo thời gian chính xác

**Triệu chứng:** test chậm và flaky khi máy CI quá tải. **Cách sửa:** test logic với virtual time, để kiểm thử tích hợp thực có tolerance/timeout phù hợp; không assert runtime tới từng millisecond.

### 12.9. Nghĩ verify timeout là onError(TimeoutException)

**Sai:** `verify(Duration.ofMillis(100))` không tự khiến publisher production phát TimeoutException. Khi test deadline hết hạn, StepVerifier báo AssertionError. Muốn kiểm tra timeout nghiệp vụ, thực sự thêm `timeout(Duration)` vào publisher rồi đòi `expectError(TimeoutException.class)`.

### 12.10. Đặt timeout mặc định trong test chạy song song

`setDefaultTimeout` ảnh hưởng StepVerifier mới tạo trong cùng JVM. Nếu test khác chạy song song, chúng có thể nhận policy không mong muốn. Dùng cấu hình cố định ở test suite hoặc ưu tiên deadline explicit trên từng verify.

### 12.11. Thiếu demand trong backpressure test

**Sai:** khởi tạo `create(source, 0)` rồi đòi `expectNext(...)` ngay nhưng không `thenRequest`; source tuân thủ backpressure sẽ không phát item. **Cách sửa:** ghi rõ từng `thenRequest(n)` trước phần dữ liệu cần kiểm tra, sau đó có terminal expectation hoặc cancel.

### 12.12. Coi cancel là complete

Sau `thenCancel()`, đừng chờ `onComplete`. Cancellation là tín hiệu từ subscriber. Nếu muốn kiểm tra xử lý cleanup, đặt `doFinally`/`doOnCancel` trước vị trí bị hủy, hoặc dùng metric/probe phù hợp.

### 12.13. Test lỗi chỉ qua message

Message của framework/library có thể đổi theo version. Khi cần contract bền, assert exception type, mã lỗi nghiệp vụ và thông tin cấu trúc; chỉ assert thông điệp khi nó là hợp đồng thực sự.

### 12.14. Có thêm dữ liệu ngoài mong đợi

`StepVerifier.create(Flux.just(1,2,3)).expectNext(1,2).verifyComplete()` phải fail vì item 3 xuất hiện trước complete. Không “sửa” bằng `expectNextCount(1)` nếu nghiệp vụ không cho phép thêm item; test phải bắt được bug.

### 12.15. subscribe thủ công và quên dispose

Đừng viết test bằng `source.subscribe(...); Thread.sleep(...)` nếu có thể dùng StepVerifier: callback bất đồng bộ khiến lỗi khó bubble tới thread JUnit và dễ rò rỉ subscription. StepVerifier cho mô tả tín hiệu và giới hạn thời gian rõ hơn.

## 13. Câu hỏi tự kiểm tra

**Câu 1.** StepVerifier xác nhận điều gì ngoài dữ liệu?  
**Đáp án:** Thứ tự tín hiệu, termination bằng complete/error hoặc cancellation, demand/time và thời hạn verify.

**Câu 2.** Mono.empty có phải onError không?  
**Đáp án:** Không. Nó phát onComplete mà không phát onNext.

**Câu 3.** `expectNextCount(10)` có xác nhận giá trị từng item không?  
**Đáp án:** Không; chỉ xác nhận số lần phát onNext.

**Câu 4.** Khi nào dùng `assertNext` thay `expectNext`?  
**Đáp án:** Khi muốn kiểm tra thuộc tính object hoặc DTO không có equals phù hợp.

**Câu 5.** `verifyComplete()` khác `verifyError()` ra sao?  
**Đáp án:** verifyComplete đòi onComplete; verifyError đòi terminal onError.

**Câu 6.** Vì sao không được quên `verify()`?  
**Đáp án:** Bởi các `expect...` chỉ cấu hình kịch bản, chưa subscribe/so sánh tín hiệu.

**Câu 7.** `verify(Duration)` có biến source thành `Mono.timeout` không?  
**Đáp án:** Không. Nó giới hạn thời gian kiểm thử; timeout nghiệp vụ phải nằm trong publisher và có thể phát TimeoutException.

**Câu 8.** `withVirtualTime` nhận Supplier vì sao?  
**Đáp án:** Để tạo publisher và timer/scheduler sau khi virtual scheduler được kích hoạt.

**Câu 9.** `expectNoEvent` có tính onSubscribe không?  
**Đáp án:** Có; thường đặt `expectSubscription()` trước nó.

**Câu 10.** Backpressure test với initial request 0 cần gì?  
**Đáp án:** Cần `thenRequest(n)` cấp demand cho từng đợt, hoặc test cố ý chờ để chứng minh source không vượt demand.

**Câu 11.** Làm thế nào kiểm tra một luồng cố ý chạy mãi?  
**Đáp án:** Nhận một số item theo contract rồi `thenCancel()`, hoặc dùng timeout test; không chờ verifyComplete vô hạn.

**Câu 12.** Sau onError có thể có onComplete cùng subscription không?  
**Đáp án:** Không. Hai terminal signals loại trừ nhau.

## 14. Checklist trước khi đưa test vào CI

- [ ] Test có `verify()` hoặc shortcut verify cuối cùng.
- [ ] Có kỳ vọng terminal `complete`, `error` hoặc `cancel` theo đúng contract.
- [ ] Giá trị và thứ tự được kiểm tra ở mức phù hợp; không chỉ đếm phần tử khi cần xác nhận nội dung.
- [ ] Mọi nguồn có nguy cơ treo đều có `verify(Duration)` hoặc deadline test được kiểm soát.
- [ ] Test thời gian dùng `withVirtualTime` nếu phụ thuộc Reactor scheduler và có thể chạy ảo.
- [ ] Publisher/scheduler phụ thuộc thời gian được tạo **bên trong Supplier**.
- [ ] Test `expectNoEvent` đặt sau `expectSubscription`.
- [ ] Test backpressure có đủ `thenRequest`.
- [ ] Test cancellation không chờ onComplete và quan sát upstream ở đúng vị trí.
- [ ] Không dùng Thread.sleep và không tạo subscription rò rỉ.
- [ ] Các expectation có tên/mô tả khi suite nhiều case tương tự.
- [ ] Không coi timeout của test là timeout nghiệp vụ của production.

## 15. Ghi nhớ

- StepVerifier kiểm tra **cả dữ liệu và tín hiệu terminal**, không chỉ giá trị return.
- `expectNext` là so sánh equals và thứ tự; `expectNextMatches` là predicate; `assertNext` kiểm tra field; `expectNextCount` chỉ đếm.
- `verifyComplete` chỉ pass nếu publisher phát onComplete đúng kịch bản. `verifyError` chỉ pass nếu kết thúc bằng onError đúng yêu cầu.
- **Luôn đặt thời hạn xác minh** cho kịch bản có nguy cơ không hoàn tất; `verify(Duration)` là guard của test, không phải xử lý timeout trong ứng dụng.
- `withVirtualTime` giúp kiểm thử delay, interval và timeout mà không chờ thời gian thật; nhớ tạo publisher trong Supplier.
- `expectNoEvent` kiểm tra khoảng thời gian im lặng, còn `thenAwait` chỉ cho đồng hồ trôi.
- `thenRequest` kiểm tra backpressure, `thenCancel` kiểm tra cách hủy một luồng đang mở.

## Tài liệu tham khảo

1. [Project Reactor – Testing (Reference Guide)](https://projectreactor.io/docs/core/release/reference/testing.html): StepVerifier, virtual time, đặt tên expectation và các công cụ reactor-test.
2. [Project Reactor – StepVerifier API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html): `create`, `withVirtualTime`, `verify(Duration)`, default timeout và post-verification assertions.
3. [Project Reactor – StepVerifier.Step API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.Step.html): `expectNext`, `assertNext`, `expectNextMatches`, `expectNextCount`, `expectNextSequence`, `expectNoEvent`, `thenRequest`.
4. [Project Reactor – StepVerifier.LastStep API](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.LastStep.html): `expectComplete`, `expectError`, `verifyComplete`, `verifyError`, `thenCancel`.
5. [Project Reactor – Mono API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Mono.html): `empty`, `error`, `delay`, `timeout`.
6. [Project Reactor – Flux API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html): `range`, `interval`, `take`, `concatWith`.
7. [Reactive Streams 1.0.4 Specification](https://www.reactive-streams.org/): `Publisher`, `Subscriber`, `Subscription.request`, `Subscription.cancel` và tín hiệu terminal.
