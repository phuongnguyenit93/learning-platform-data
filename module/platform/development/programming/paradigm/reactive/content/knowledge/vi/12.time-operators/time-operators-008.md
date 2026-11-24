# Đua giữa nguồn dữ liệu, bộ định thời và tín hiệu hủy

Trong một pipeline reactive, một kết quả có thể đến từ nhiều nguồn: dịch vụ chính, bản sao dự phòng, cache hoặc một bộ định thời. Ứng dụng thường cần quyết định nguồn nào thắng, khi nào phải dừng chờ và điều gì xảy ra với các công việc còn lại. Project Reactor cung cấp các toán tử như `firstWithSignal` và `timeout` để phối hợp những tín hiệu này. Cơ chế hủy subscription giúp dừng việc tiêu thụ các nguồn thua cuộc khi kết quả không còn cần thiết.

Bài học thuộc chương **Thời gian** của module **REACTIVE_PROGRAMMING**. Module hướng dẫn tư duy theo các luồng sự kiện bất đồng bộ, hợp đồng Publisher–Subscriber và backpressure của Reactive Streams; người học thực hành `Mono`, `Flux`, kết hợp toán tử, kiểm soát scheduler, xử lý lỗi và kiểm thử pipeline trong hệ sinh thái Java. Nội dung tập trung vào cuộc đua giữa Publisher dữ liệu, timer và cancellation trong Project Reactor.

## Cuộc đua giữa các tín hiệu

Một Publisher không chỉ phát dữ liệu. Nó có thể phát `onNext`, kết thúc bình thường bằng `onComplete` hoặc kết thúc bằng `onError`. Khi nhiều Publisher cùng tham gia một cuộc đua, cần xác định loại tín hiệu nào được xem là điều kiện thắng.

Ví dụ, một ứng dụng cần lấy hồ sơ người dùng từ dịch vụ chính và một bản sao dự phòng. Có thể có ba tình huống:

- Dịch vụ chính trả về dữ liệu trước: kết quả chính được dùng.
- Dịch vụ dự phòng trả về dữ liệu trước: kết quả dự phòng được dùng.
- Một nguồn phát lỗi hoặc hoàn tất rỗng trước khi nguồn còn lại có dữ liệu: kết quả phụ thuộc chính sách chọn tín hiệu của toán tử.

Toán tử đua không tự hiểu ý nghĩa nghiệp vụ của dữ liệu. Nó chỉ áp dụng quy tắc chọn tín hiệu mà ta đã yêu cầu.

## Chọn tín hiệu đầu tiên bằng Mono.firstWithSignal

`Mono.firstWithSignal(...)` chọn `Mono` phát tín hiệu đầu tiên. Tín hiệu đó có thể là:

- `onNext(value)`: Publisher phát một giá trị.
- `onComplete`: Publisher hoàn tất mà không có giá trị.
- `onError(error)`: Publisher kết thúc bằng lỗi.

Ví dụ, hai dịch vụ trả về cùng kiểu kết quả:

~~~java
Mono<Profile> fastestProfile = Mono.firstWithSignal(
    primaryProfileService.fetch(userId),
    replicaProfileService.fetch(userId)
);
~~~

Publisher phát tín hiệu đầu tiên sẽ quyết định kết quả của `fastestProfile`. Khi một nguồn thắng, các nguồn còn lại bị hủy theo cơ chế cancellation của toán tử.

Điều cần chú ý là **tín hiệu đầu tiên không đồng nghĩa với giá trị hợp lệ đầu tiên**. Nếu dịch vụ chính hoàn tất rỗng trước khi bản sao dự phòng phát dữ liệu, `firstWithSignal` có thể hoàn tất rỗng ngay. Nếu dịch vụ chính phát lỗi trước, lỗi đó có thể kết thúc cuộc đua dù bản sao dự phòng sắp trả về dữ liệu.

Ví dụ thể hiện rõ trường hợp rỗng:

~~~java
Mono<String> result = Mono.firstWithSignal(
    Mono.<String>empty(),
    Mono.just("giá trị từ bản sao")
);
~~~

Nguồn rỗng phát `onComplete` ngay, nên cuộc đua có thể kết thúc mà không phát chuỗi từ bản sao. Nếu yêu cầu nghiệp vụ là chọn **giá trị đầu tiên**, cần dùng chính sách phù hợp với giá trị thay vì coi mọi tín hiệu kết thúc là kết quả thắng.

## Chọn giá trị đầu tiên bằng Mono.firstWithValue

Khi có nhiều `Mono` và chỉ một giá trị thực sự mới được xem là thành công, `Mono.firstWithValue(...)` phù hợp hơn `firstWithSignal`. Nó chọn nguồn phát `onNext` đầu tiên; một nguồn hoàn tất rỗng hoặc phát lỗi không lập tức được xem là giá trị thắng trong khi các nguồn khác vẫn có thể trả về dữ liệu.

~~~java
Mono<Profile> fastestAvailableProfile = Mono.firstWithValue(
    primaryProfileService.fetch(userId),
    replicaProfileService.fetch(userId),
    cacheProfileService.fetch(userId)
);
~~~

Nếu không nguồn nào phát giá trị, kết quả cuối cùng sẽ là lỗi thay vì một giá trị giả định. Vì vậy, tầng gọi vẫn cần xác định cách xử lý trường hợp tất cả nguồn đều rỗng hoặc lỗi.

Có thể ghi nhớ sự khác nhau:

| Toán tử | Điều kiện thắng | Khi phù hợp |
|---|---|---|
| `Mono.firstWithSignal(...)` | Tín hiệu đầu tiên: giá trị, hoàn tất rỗng hoặc lỗi | Cần phản ứng ngay với bất kỳ kết thúc nào của một nguồn |
| `Mono.firstWithValue(...)` | Giá trị `onNext` đầu tiên | Cần giá trị thành công đầu tiên từ nhiều nguồn |

Không nên dùng `firstWithValue` chỉ để che giấu lỗi. Nếu mọi nguồn đều lỗi, ứng dụng cần ghi nhận và xử lý thất bại theo chính sách riêng. Khi nguồn có thể trả về rỗng hợp lệ, cũng cần xác định rõ rỗng có phải một kết quả nghiệp vụ hay cần chuyển thành trạng thái khác.

## Đua giữa nguồn dữ liệu và bộ định thời bằng timeout

Một yêu cầu thường có giới hạn thời gian chờ. Nếu nguồn không phát tín hiệu trong khoảng thời gian quy định, ứng dụng cần kết thúc yêu cầu hoặc chuyển sang nguồn dự phòng.

Với `Mono`, có thể dùng `timeout(Duration)`:

~~~java
Mono<Profile> profile = profileService.fetch(userId)
    .timeout(Duration.ofSeconds(2));
~~~

Nếu nguồn không phát giá trị hoặc tín hiệu kết thúc trước thời hạn, `timeout` phát lỗi `TimeoutException`. Nếu nguồn hoàn tất rỗng trước thời hạn, kết quả vẫn là hoàn tất rỗng; timeout không biến một kết quả rỗng bình thường thành lỗi.

Có thể cung cấp Publisher dự phòng khi hết thời gian:

~~~java
Mono<Profile> profile = profileService.fetch(userId)
    .timeout(
        Duration.ofSeconds(2),
        Mono.defer(() -> cacheProfileService.fetch(userId))
    );
~~~

Khi thời hạn hết mà nguồn chính chưa phát tín hiệu, Reactor hủy subscription của nguồn chính và đăng ký Publisher dự phòng. `Mono.defer` trì hoãn việc gọi hàm tạo Publisher dự phòng cho đến khi nhánh fallback thực sự được subscribe. Điều này hữu ích nếu việc tạo fallback có side effect hoặc cần đọc trạng thái tại đúng thời điểm chuyển nhánh.

`timeout` là cách biểu diễn trực tiếp cho yêu cầu “nguồn này phải phản hồi trong thời hạn”. So với việc tự ghép `Mono.delay` bằng toán tử đua, `timeout` diễn đạt rõ mục đích và xử lý việc hủy nguồn bị quá hạn.

## Tự ghép timer với nguồn dữ liệu

Đôi khi timer không chỉ biểu diễn lỗi timeout. Nó có thể là một nhánh nghiệp vụ: hết thời gian thì trả trạng thái mặc định, phát cảnh báo hoặc chuyển sang chế độ dự phòng.

`Mono.delay(Duration)` tạo một `Mono<Long>` phát giá trị sau khoảng thời gian đã định. Có thể chuyển tín hiệu timer thành một kết quả miền rồi đua với nguồn dữ liệu:

~~~java
Mono<LoadResult> data = repository.load();

Mono<LoadResult> deadline = Mono.delay(Duration.ofSeconds(3))
    .thenReturn(LoadResult.timedOut());

Mono<LoadResult> result = Mono.firstWithSignal(data, deadline);
~~~

Ở ví dụ này, timer phát một giá trị `LoadResult.timedOut()` sau ba giây. Nguồn dữ liệu và timer cùng được đăng ký; nhánh phát tín hiệu đầu tiên thắng, nhánh còn lại bị hủy.

Nếu `data` hoàn tất rỗng hoặc lỗi trước khi timer phát, tín hiệu đó cũng thắng vì đang dùng `firstWithSignal`. Nếu chỉ muốn dữ liệu hợp lệ thắng, hãy dùng `firstWithValue` với các Publisher có kiểu kết quả tương thích và định nghĩa rõ hành vi khi không nguồn nào phát giá trị.

Không nên tạo timer bằng một lời gọi blocking như `Thread.sleep` bên trong `map` hoặc `fromCallable`. `Mono.delay` biểu diễn thời gian chờ bằng scheduler, cho phép subscription bị hủy mà không chiếm một thread chỉ để ngủ.

## Timeout giữa các phần tử của Flux

Với `Flux`, `timeout(Duration)` thường được dùng để phát hiện khoảng thời gian không có phần tử. Bộ định thời được áp dụng từ lúc subscribe và được đặt lại khi phần tử tiếp theo đến. Vì vậy, đây là **idle timeout**: pipeline lỗi nếu upstream im lặng quá lâu giữa hai phần tử.

~~~java
Flux<Event> events = eventSource.events()
    .timeout(Duration.ofSeconds(5));
~~~

Nếu nguồn phát các sự kiện cách nhau lần lượt hai giây, luồng tiếp tục bình thường. Nếu một khoảng giữa hai sự kiện vượt quá năm giây, timeout phát `TimeoutException` và hủy upstream.

Có thể dùng fallback Publisher để thay thế luồng khi không có sự kiện đúng hạn:

~~~java
Flux<Event> events = eventSource.events()
    .timeout(
        Duration.ofSeconds(5),
        fallbackEventSource.events()
    );
~~~

Hãy phân biệt idle timeout với deadline tổng:

- Idle timeout giới hạn thời gian chờ giữa các phần tử; mỗi phần tử mới làm bắt đầu một khoảng chờ tiếp theo.
- Deadline tổng giới hạn toàn bộ thời gian của một thao tác, kể cả khi thao tác vẫn phát các phần tử đều đặn.

Nếu cần giới hạn tổng thời gian, phải mô hình hóa deadline riêng. Không nên giả định `Flux.timeout(Duration)` tự giới hạn tổng thời gian sống của một luồng có hoạt động liên tục. Với trường hợp chỉ cần ngừng phát sau một khoảng thời gian và hoàn tất bình thường, có thể cân nhắc `take(Duration)`; nếu hết deadline phải là lỗi, hãy dùng một timer/deadline Publisher và quy tắc kết thúc phù hợp.

## Cancellation khi một nhánh thắng

Trong cuộc đua, khi một nhánh đã thắng, các nhánh còn lại không còn cần thiết. Reactor gửi tín hiệu `cancel` tới subscription của những Publisher thua cuộc. Với nguồn hỗ trợ cancellation, việc này có thể:

- Hủy request HTTP đang chờ và giải phóng kết nối.
- Dừng timer đã lên lịch.
- Hủy truy vấn hoặc thao tác đọc có hỗ trợ hủy.
- Đóng tài nguyên gắn với subscription.

Cancellation là một tín hiệu hợp tác. Nó yêu cầu Publisher dừng gửi tín hiệu tiếp theo và giải phóng tài nguyên nếu có thể. Nó không bảo đảm một API blocking đã chạy sẽ dừng tức thì, cũng không rollback side effect đã được gửi tới hệ thống bên ngoài.

Ví dụ, một request đến dịch vụ thanh toán có thể đã được xử lý trước khi cancellation đến. Hủy subscription chỉ dừng việc chờ hoặc tiêu thụ kết quả ở phía reactive; nó không chứng minh giao dịch chưa xảy ra. Các thao tác quan trọng cần idempotency, mã giao dịch và cơ chế đối soát độc lập.

Sơ đồ minh họa cuộc đua có một nhánh dữ liệu thắng trước deadline:

~~~mermaid
sequenceDiagram
    participant C as Subscriber
    participant R as Nguồn dữ liệu
    participant T as Timer
    C->>R: subscribe
    C->>T: subscribe
    R-->>C: onNext(value)
    C--xT: cancel
    Note over C,T: Timer không còn cần thiết
~~~

Nếu timer thắng trước, hành vi đảo ngược: nguồn dữ liệu bị hủy và pipeline phát lỗi timeout hoặc kết quả fallback đã cấu hình.

## Xử lý lỗi và fallback có chủ đích

Timeout, lỗi từ nguồn chính và kết quả rỗng là ba trạng thái khác nhau. Có thể biểu diễn fallback theo từng trạng thái:

~~~java
Mono<Profile> profile = primaryProfileService.fetch(userId)
    .timeout(
        Duration.ofSeconds(2),
        Mono.defer(() -> replicaProfileService.fetch(userId))
    )
    .switchIfEmpty(
        Mono.defer(() -> cacheProfileService.fetch(userId))
    )
    .onErrorResume(ServiceUnavailableException.class,
        error -> staleProfileCache.fetch(userId));
~~~

Pipeline trên thể hiện ba quyết định:

1. Nếu nguồn chính không phát tín hiệu trong hai giây, chuyển sang bản sao dự phòng.
2. Nếu Publisher kết quả hoàn tất rỗng, đọc cache.
3. Nếu lỗi thuộc loại dịch vụ không khả dụng, dùng cache cũ theo chính sách đã định.

Thứ tự toán tử có ý nghĩa. `timeout` chỉ xử lý trường hợp quá thời hạn; `switchIfEmpty` xử lý hoàn tất rỗng; `onErrorResume` xử lý lỗi. Trong ứng dụng thật, cần tránh để fallback tạo vòng lặp hoặc che giấu lỗi dữ liệu. Hãy ghi log/metric cho nhánh được dùng và giữ lại thông tin nguồn gốc để chẩn đoán.

## Kiểm thử thời gian mà không phải chờ thật

`StepVerifier.withVirtualTime` cho phép kiểm thử các pipeline dựa trên timer mà không phải chờ thời gian thực. Publisher cần được tạo bên trong supplier của `withVirtualTime` để virtual scheduler được cài đặt trước khi pipeline được lắp ráp.

Kiểm thử một nguồn `Mono` không phản hồi:

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.<String>never().timeout(Duration.ofSeconds(3)))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(3))
    .expectError(TimeoutException.class)
    .verify();
~~~

Kiểm thử fallback sau timeout:

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.<String>never().timeout(
            Duration.ofSeconds(2),
            Mono.just("cache")
        ))
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(2))
    .expectNext("cache")
    .verifyComplete();
~~~

Kiểm thử một nguồn dữ liệu thắng và timer bị hủy:

~~~java
AtomicBoolean timerCancelled = new AtomicBoolean();

StepVerifier.withVirtualTime(() -> {
        Mono<String> data = Mono.delay(Duration.ofSeconds(1))
            .thenReturn("data");
        Mono<String> timer = Mono.delay(Duration.ofSeconds(5))
            .doOnCancel(() -> timerCancelled.set(true))
            .thenReturn("deadline");
        return Mono.firstWithSignal(data, timer);
    })
    .expectSubscription()
    .thenAwait(Duration.ofSeconds(1))
    .expectNext("data")
    .verifyComplete();

assertTrue(timerCancelled.get());
~~~

Trong ví dụ cuối, nguồn dữ liệu phát sau một giây, trước timer năm giây. Timer thua cuộc nhận cancellation; kiểm thử xác nhận hành vi đó bằng `doOnCancel`. Đây là cách kiểm tra tài nguyên và công việc nền được dừng khi kết quả đã có.

Khi kiểm thử `Flux.timeout`, nên kiểm tra cả trường hợp luồng phát đều đặn và trường hợp im lặng vượt ngưỡng. Với virtual time, có thể dùng `thenAwait` để đẩy đồng hồ kiểm thử tiến lên mà không phải ngủ trong test. Nếu pipeline sử dụng scheduler tùy chỉnh, hãy bảo đảm scheduler đó cũng tương thích với cơ chế virtual time hoặc inject scheduler để kiểm thử có thể điều khiển được.

## Những lỗi thường gặp khi phối hợp timer và nguồn dữ liệu

| Cách làm | Vấn đề | Cách xử lý |
|---|---|---|
| Dùng `firstWithSignal` trong khi chỉ giá trị mới là thành công | `onComplete` rỗng hoặc `onError` có thể thắng trước giá trị | Dùng `firstWithValue` hoặc chuẩn hóa kết quả theo nghiệp vụ |
| Dùng `Thread.sleep` để tạo timeout | Chiếm thread và không hủy được timer một cách reactive | Dùng `Mono.delay` hoặc `timeout` |
| Xem `Flux.timeout(Duration)` là deadline tổng | Luồng phát đều có thể chạy lâu hơn thời lượng đó | Phân biệt idle timeout với deadline tổng |
| Giả định cancellation rollback side effect | Hệ thống ngoài có thể đã thực hiện thao tác | Dùng idempotency và đối soát |
| Tạo fallback có side effect ngay khi lắp ráp pipeline | Công việc có thể chạy dù nhánh fallback không được chọn | Dùng `Mono.defer` hoặc `Flux.defer` |
| Chỉ kiểm thử kết quả mà không kiểm thử nhánh thua | Timer/request nền có thể vẫn giữ tài nguyên | Dùng `doOnCancel` và kiểm tra cancellation |

## Nguyên tắc thiết kế cuộc đua

Trước khi ghép nguồn dữ liệu với timer hoặc nguồn dự phòng, hãy xác định:

1. Điều kiện thắng là tín hiệu đầu tiên hay giá trị đầu tiên?
2. Hoàn tất rỗng có phải kết quả hợp lệ hay cần tiếp tục chờ nguồn khác?
3. Lỗi từ một nguồn có được phép kết thúc toàn bộ cuộc đua không?
4. Khi timeout, ứng dụng phát lỗi, trả giá trị mặc định hay đăng ký nguồn dự phòng?
5. Nhánh thua có hỗ trợ cancellation và giải phóng tài nguyên không?
6. Timeout là giới hạn cho lần phản hồi đầu tiên, khoảng im lặng giữa các phần tử hay deadline tổng?
7. Kiểm thử có xác nhận cả tín hiệu kết quả, thời gian và cancellation không?

Các toán tử đua và timer giúp pipeline phản ứng với nguồn dữ liệu nhanh nhất, giới hạn thời gian chờ và dừng những công việc không còn cần thiết. Khi phân biệt đúng tín hiệu đầu tiên với giá trị đầu tiên, idle timeout với deadline tổng, và cancellation với rollback, ta có thể xây dựng luồng reactive dễ dự đoán và an toàn hơn.
