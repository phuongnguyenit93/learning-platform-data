# StepVerifier: xác nhận dữ liệu, thứ tự và tín hiệu kết thúc

Publisher reactive không chạy đầy đủ chỉ vì một test đã gọi phương thức tạo `Mono` hoặc `Flux`. Phần lớn publisher chỉ bắt đầu công việc khi có subscription. Một test vì vậy cần đóng vai trò subscriber, yêu cầu dữ liệu và xác minh những gì thực sự được phát. `StepVerifier` trong Reactor Test cung cấp một cách mô tả kịch bản đó theo thứ tự: đăng ký, nhận phần tử, kiểm tra giá trị, quan sát lỗi hoặc hoàn tất, và chủ động hủy khi cần.

`StepVerifier` đặc biệt hữu ích để kiểm tra ba khía cạnh cốt lõi của một pipeline:

- **Dữ liệu:** publisher phát đúng giá trị và đúng số lượng.
- **Thứ tự:** các phần tử đến theo thứ tự mà hợp đồng của pipeline yêu cầu.
- **Tín hiệu kết thúc:** publisher hoàn tất bình thường, phát lỗi cụ thể hoặc bị subscriber hủy.

Trong module Reactive Programming, các bài thực hành dùng `Mono`, `Flux`, toán tử kết hợp, scheduler và backpressure. `StepVerifier` cho phép kiểm tra các hợp đồng đó ở mức tín hiệu, thay vì chỉ gọi `block()` rồi so sánh một giá trị cuối.

## 1. Cách một kịch bản StepVerifier hoạt động

Một kịch bản cơ bản gồm ba phần:

1. Tạo publisher cần kiểm thử.
2. Tạo `StepVerifier` cho publisher đó và khai báo các tín hiệu mong đợi.
3. Gọi một phương thức `verify...()` để thực sự subscribe và chạy kịch bản.

Ví dụ:

~~~java
Flux<Integer> numbers = Flux.just(1, 2, 3);

StepVerifier.create(numbers)
    .expectNext(1, 2, 3)
    .verifyComplete();
~~~

`create` chuẩn bị một subscriber kiểm thử. `expectNext` xác minh từng phần tử theo thứ tự. `verifyComplete` thực hiện subscription, chờ tín hiệu kết thúc và xác minh publisher complete. Nếu thiếu phần tử, có phần tử sai thứ tự, phát thêm phần tử hoặc phát lỗi thay vì complete, test sẽ thất bại.

Chỉ tạo `StepVerifier` mà không gọi `verify`, `verifyComplete`, `verifyError` hoặc phương thức kết thúc tương ứng thì kịch bản chưa được thực thi.

## 2. Thêm Reactor Test vào dự án

Trong Maven, thêm dependency `reactor-test` với scope test. Nên dùng cùng phiên bản Reactor Core do Spring Boot BOM hoặc dependency management của dự án quản lý:

~~~xml
<dependency>
    <groupId>io.projectreactor</groupId>
    <artifactId>reactor-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Với Gradle:

~~~kotlin
testImplementation("io.projectreactor:reactor-test")
~~~

Các ví dụ Java bên dưới dùng JUnit 5, Reactor Core và Reactor Test. Một test thường cần những import sau:

~~~java
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Set;
import java.util.concurrent.atomic.AtomicBoolean;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.test.StepVerifierOptions;
~~~

## 3. Xác nhận giá trị bằng expectNext và assertNext

`expectNext` phù hợp khi muốn so sánh giá trị bằng equality. Nó nhận một hoặc nhiều giá trị và kiểm tra chúng lần lượt:

~~~java
@Test
void emitsValuesInOrder() {
    Flux<String> names = Flux.just("An", "Bình", "Chi");

    StepVerifier.create(names)
        .expectNext("An")
        .expectNext("Bình", "Chi")
        .verifyComplete();
}
~~~

Có thể gộp các phần tử vào một lần gọi hoặc chia thành nhiều bước để làm rõ ý nghĩa từng giai đoạn. Thứ tự trong `expectNext` là thứ tự tín hiệu bắt buộc.

Với object, dùng `assertNext` khi cần kiểm tra nhiều thuộc tính:

~~~java
record Order(String id, String status, long total) {}

@Test
void emitsExpectedOrder() {
    Mono<Order> order = Mono.just(
        new Order("ORD-42", "CONFIRMED", 150_000)
    );

    StepVerifier.create(order)
        .assertNext(actual -> {
            assertEquals("ORD-42", actual.id());
            assertEquals("CONFIRMED", actual.status());
            assertEquals(150_000, actual.total());
        })
        .verifyComplete();
}
~~~

Consumer truyền cho `assertNext` chạy khi phần tử tương ứng đến. Nếu một assertion thất bại, test báo lỗi tại bước kiểm tra đó. Với một điều kiện boolean đơn giản, `expectNextMatches` thường ngắn gọn hơn:

~~~java
StepVerifier.create(Mono.just(21))
    .expectNextMatches(value -> value > 0 && value % 3 == 0)
    .verifyComplete();
~~~

`consumeNextWith` cũng nhận một Consumer để xử lý phần tử, nhưng tên gọi nhấn mạnh việc consumer tự kiểm tra hoặc tiêu thụ giá trị. Dùng `assertNext` khi muốn thể hiện rõ rằng assertion là mục đích chính của bước.

## 4. Xác nhận số lượng phần tử

`expectNextCount(n)` kiểm tra và tiêu thụ đúng n phần tử mà không so sánh giá trị từng phần tử:

~~~java
StepVerifier.create(Flux.range(1, 5))
    .expectNextCount(5)
    .verifyComplete();
~~~

Phương thức này phù hợp khi số lượng quan trọng hơn nội dung. Nó không xác minh thứ tự hoặc giá trị. Nếu cần kiểm tra cả số lượng lẫn dữ liệu, hãy dùng `expectNext`, `assertNext` hoặc ghi lại các phần tử rồi kiểm tra collection.

Ví dụ ghi lại một nhóm phần tử:

~~~java
StepVerifier.create(Flux.just("red", "green", "blue"))
    .recordWith(ArrayList::new)
    .expectNextCount(3)
    .consumeRecordedWith(actual ->
        assertEquals(List.of("red", "green", "blue"), actual)
    )
    .verifyComplete();
~~~

`recordWith` bắt đầu thu thập các phần tử vào collection do supplier tạo. `consumeRecordedWith` đưa collection đã ghi cho callback để kiểm tra. Cách này hữu ích khi cần kiểm tra toàn bộ tập dữ liệu hoặc tổng hợp kết quả sau khi nhận đủ phần tử.

## 5. Kiểm tra thứ tự khi thứ tự là một phần của hợp đồng

Nếu nghiệp vụ yêu cầu kết quả theo thứ tự đầu vào, test nên xác minh chính xác thứ tự đó:

~~~java
Flux<String> processed = Flux.just("A", "B", "C")
    .concatMap(value -> Mono.just(value + "-done"));

StepVerifier.create(processed)
    .expectNext("A-done", "B-done", "C-done")
    .verifyComplete();
~~~

`concatMap` subscribe và hoàn tất publisher con tuần tự, vì vậy thứ tự đầu ra theo thứ tự nguồn. Nếu thay bằng `flatMap` với publisher con bất đồng bộ, kết quả có thể đến theo thứ tự hoàn tất thay vì thứ tự đầu vào. Không nên viết test yêu cầu một thứ tự mà operator không bảo đảm.

Khi thứ tự không quan trọng nhưng tập kết quả phải đúng, có thể ghi lại các phần tử và so sánh tập hợp:

~~~java
StepVerifier.create(Flux.just("A", "B", "C"))
    .recordWith(ArrayList::new)
    .expectNextCount(3)
    .consumeRecordedWith(actual ->
        assertEquals(Set.of("A", "B", "C"), Set.copyOf(actual))
    )
    .verifyComplete();
~~~

Chỉ dùng cách so sánh không thứ tự khi hợp đồng thực sự không quy định thứ tự. `Set` loại bỏ phần tử trùng, nên nếu số lần xuất hiện cũng quan trọng, hãy so sánh collection đã sắp xếp hoặc dùng một cấu trúc đếm tần suất.

## 6. Xác nhận complete và empty

`verifyComplete()` yêu cầu publisher hoàn tất bình thường. Với `Mono.empty()`, publisher không phát `onNext` nhưng vẫn phải phát `onComplete`:

~~~java
StepVerifier.create(Mono.<String>empty())
    .verifyComplete();
~~~

Nếu publisher đáng lẽ phải có giá trị, thêm expectation cho giá trị trước `verifyComplete`:

~~~java
StepVerifier.create(Mono.just("ready"))
    .expectNext("ready")
    .verifyComplete();
~~~

Hai test này kiểm tra hai hợp đồng khác nhau: một publisher complete rỗng và một publisher phát đúng một giá trị rồi complete. Đừng dùng `expectNextCount(0)` thay cho `verifyComplete`; bước đó chỉ nói rằng không tiêu thụ phần tử nào ở vị trí đó, còn test vẫn cần xác nhận terminal signal.

## 7. Xác nhận lỗi và nội dung exception

Publisher lỗi không complete bình thường. `StepVerifier` cung cấp nhiều cách xác minh loại và nội dung exception:

~~~java
StepVerifier.create(
        Mono.error(new IllegalArgumentException("invalid order"))
    )
    .expectError(IllegalArgumentException.class)
    .verify();
~~~

Nếu cần kiểm tra message:

~~~java
StepVerifier.create(
        Mono.error(new IllegalArgumentException("invalid order"))
    )
    .expectErrorMessage("invalid order")
    .verify();
~~~

`expectErrorMatches` cho phép dùng predicate:

~~~java
StepVerifier.create(
        Mono.error(new IllegalStateException("database unavailable"))
    )
    .expectErrorMatches(error ->
        error instanceof IllegalStateException
            && error.getMessage().contains("database")
    )
    .verify();
~~~

Khi cần nhiều assertion trên exception, dùng `expectErrorSatisfies`:

~~~java
StepVerifier.create(
        Mono.error(new IllegalArgumentException("quantity must be positive"))
    )
    .expectErrorSatisfies(error -> {
        assertInstanceOf(IllegalArgumentException.class, error);
        assertTrue(error.getMessage().contains("quantity"));
    })
    .verify();
~~~

Các phương thức `expectError...` đã mô tả terminal signal mong đợi; gọi `verify()` để chạy kịch bản. Không gọi thêm `verifyComplete()` sau một expectation lỗi.

## 8. Kiểm tra dữ liệu trước khi lỗi xảy ra

Một pipeline có thể phát một số phần tử rồi mới phát lỗi. Test cần xác minh cả phần dữ liệu đã phát và terminal error:

~~~java
Flux<Integer> source = Flux.concat(
    Flux.just(10, 20),
    Flux.error(new IllegalStateException("source failed"))
);

StepVerifier.create(source)
    .expectNext(10, 20)
    .expectErrorMessage("source failed")
    .verify();
~~~

Kịch bản này bảo đảm hai phần tử xuất hiện trước lỗi. Nếu nguồn phát lỗi ngay từ đầu, test sẽ thất bại tại `expectNext`. Nếu nguồn complete thay vì lỗi, test cũng thất bại.

Đây là cách kiểm tra hữu ích cho pipeline có xử lý từng phần, chẳng hạn đọc nhiều bản ghi rồi gặp lỗi kết nối. Cần xác định rõ ứng dụng cho phép consumer nhìn thấy một phần kết quả hay phải gom dữ liệu trước khi phát để bảo đảm tính nguyên tử ở tầng API.

## 9. Xác minh subscription và demand

`StepVerifier.create(publisher, initialRequest)` cho phép thiết lập demand ban đầu. Đặt demand bằng 0 để kiểm tra publisher chưa được yêu cầu phát phần tử; sau đó dùng `thenRequest(n)` để yêu cầu thêm:

~~~java
StepVerifier.create(Flux.range(1, 5), 0)
    .expectSubscription()
    .thenRequest(2)
    .expectNext(1, 2)
    .thenRequest(1)
    .expectNext(3)
    .thenCancel()
    .verify();
~~~

`expectSubscription()` xác nhận subscription đã được thiết lập và cho phép thực hiện hành động tiếp theo trên kịch bản. `thenRequest(2)` yêu cầu thêm hai phần tử. Sau khi nhận ba phần tử qua hai lần request, test hủy publisher.

Ví dụ này kiểm tra mối quan hệ giữa demand và số phần tử được tiêu thụ. Nếu cần chứng minh một publisher tự viết tuân thủ backpressure, nên bổ sung test cho request theo từng đợt, cancellation và các trường hợp request không hợp lệ theo Reactive Streams. Không dùng `Thread.sleep` để suy đoán rằng publisher chưa phát; hãy điều khiển demand trực tiếp.

## 10. Xác nhận cancellation

Cancellation là hành động của subscriber, không phải terminal signal. Dùng `thenCancel()` để hủy subscription:

~~~java
AtomicBoolean cancelled = new AtomicBoolean();

StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1))
            .doOnCancel(() -> cancelled.set(true))
    )
    .thenAwait(Duration.ofSeconds(2))
    .expectNext(0L, 1L)
    .thenCancel()
    .verify();

assertTrue(cancelled.get());
~~~

Trong test này, nguồn timer được tạo bên trong supplier truyền cho `withVirtualTime`, để scheduler ảo được cài trước khi publisher tạo timer. `thenCancel` hủy subscription; `doOnCancel` xác nhận yêu cầu hủy đã đến vị trí hook. Test không nên gọi `verifyComplete()` vì cancellation không phải complete.

Cancellation ở pipeline cũng không chứng minh một I/O bên ngoài đã dừng. Nếu cần xác minh adapter đã gọi `cancel` trên HTTP client, database driver hoặc callback registration, hãy dùng fake/test double để kiểm tra lời gọi đó, rồi có integration test riêng nếu cần xác nhận hành vi của transport thật.

## 11. Kiểm tra thời gian bằng virtual time

Các publisher dùng timer như `delayElements`, `interval`, `timeout` hoặc `take(Duration)` có thể làm test chậm nếu chờ thời gian thực. `StepVerifier.withVirtualTime` cho phép tiến thời gian ảo mà không phải đợi đồng hồ thật:

~~~java
StepVerifier.withVirtualTime(() ->
        Flux.interval(Duration.ofSeconds(1)).take(3)
    )
    .thenAwait(Duration.ofSeconds(3))
    .expectNext(0L, 1L, 2L)
    .verifyComplete();
~~~

`thenAwait` tiến thời gian ảo và cho publisher cơ hội phát tín hiệu. Nó không khẳng định rằng trong khoảng đó không có tín hiệu nào xuất hiện.

Nếu muốn xác nhận publisher không phát tín hiệu trong một khoảng thời gian, dùng `expectNoEvent`:

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofSeconds(5))
    )
    .expectSubscription()
    .expectNoEvent(Duration.ofSeconds(4))
    .thenAwait(Duration.ofSeconds(1))
    .expectNext(0L)
    .verifyComplete();
~~~

`expectNoEvent` xem subscription là một sự kiện. Vì vậy, hãy gọi `expectSubscription()` trước khi dùng nó để kiểm tra khoảng không có tín hiệu tiếp theo. Phân biệt:

- `expectNoEvent(duration)`: xác minh không có tín hiệu trong khoảng thời gian.
- `thenAwait(duration)`: tiến thời gian và tiếp tục kịch bản mà không khẳng định không có tín hiệu.

### Tạo publisher bên trong supplier

Với `withVirtualTime`, hãy lắp ráp publisher có sử dụng scheduler mặc định bên trong supplier:

~~~java
StepVerifier.withVirtualTime(() ->
    Flux.interval(Duration.ofSeconds(1))
        .take(2)
)
    .thenAwait(Duration.ofSeconds(2))
    .expectNext(0L, 1L)
    .verifyComplete();
~~~

Nếu tạo `Flux.interval` trước khi gọi `withVirtualTime`, publisher có thể đã giữ scheduler thật thay vì scheduler ảo. Điều này làm test phụ thuộc thời gian thực hoặc chạy sai kỳ vọng. Publisher dùng một scheduler tùy chỉnh riêng cũng không tự động chuyển sang virtual scheduler; khi đó cần truyền scheduler có thể điều khiển hoặc kiểm thử riêng ranh giới đó.

## 12. Đặt giới hạn thời gian cho verify

Các phương thức `verifyComplete()`, `verify()` và những biến thể tương ứng chờ kịch bản kết thúc. Nếu publisher không phát terminal signal, test có thể chờ lâu. Có thể giới hạn thời gian kiểm thử bằng `verify(Duration)`:

~~~java
StepVerifier.create(Mono.never())
    .expectSubscription()
    .thenCancel()
    .verify(Duration.ofSeconds(1));
~~~

Đây là giới hạn thời gian cho quá trình xác minh test. Nó khác với toán tử `timeout` trong pipeline:

- `verify(Duration)` giới hạn thời gian test chờ kịch bản hoàn tất.
- `timeout(Duration)` thay đổi hành vi publisher bằng cách phát lỗi hoặc chuyển sang fallback khi nguồn không phát kịp.

Không dùng timeout của test để thay thế kiểm tra timeout nghiệp vụ. Ngược lại, một test timeout ngắn có thể làm test không ổn định trên CI nếu máy tải cao; hãy chọn giới hạn hợp lý và dùng virtual time cho logic dựa trên thời gian.

## 13. Đặt tên kịch bản để chẩn đoán lỗi

Khi test có nhiều bước, đặt tên scenario giúp thông báo lỗi dễ định vị hơn:

~~~java
StepVerifier.create(
        Flux.just("accepted", "stored"),
        StepVerifierOptions.create()
            .scenarioName("order events are emitted in order")
    )
    .expectNext("accepted")
    .as("acceptance event")
    .expectNext("stored")
    .as("storage event")
    .verifyComplete();
~~~

`scenarioName` đặt tên cho toàn bộ kịch bản; `as` gắn mô tả cho expectation ngay trước đó. Mô tả nên nói rõ điều kiện đang kiểm tra, ví dụ “emits the saved order” hoặc “fails when inventory is missing”, để dễ đọc báo cáo test.

Không cần đặt tên dài cho mọi test nhỏ. Dùng scenario name khi test có nhiều nhánh, nhiều tín hiệu hoặc dễ nhầm giữa các expectation.

## 14. Một test hoàn chỉnh cho service reactive

Giả sử service lọc đơn hàng đã xác nhận và chỉ phát ID:

~~~java
record OrderSummary(String id, String status) {}

class OrderService {
    Flux<String> confirmedOrderIds(Flux<OrderSummary> orders) {
        return orders
            .filter(order -> "CONFIRMED".equals(order.status()))
            .map(OrderSummary::id);
    }
}
~~~

Test có thể xác minh dữ liệu, thứ tự và completion:

~~~java
@Test
void emitsOnlyConfirmedOrderIdsInSourceOrder() {
    OrderService service = new OrderService();

    Flux<OrderSummary> input = Flux.just(
        new OrderSummary("O-1", "CONFIRMED"),
        new OrderSummary("O-2", "PENDING"),
        new OrderSummary("O-3", "CONFIRMED")
    );

    StepVerifier.create(service.confirmedOrderIds(input))
        .expectNext("O-1", "O-3")
        .verifyComplete();
}
~~~

Test không cần gọi `block()` hoặc tự subscribe. `StepVerifier` sở hữu subscription, nhận tín hiệu và báo lỗi nếu output không đúng hợp đồng. Khi service có repository, scheduler hoặc nguồn ngoài, có thể thay dependency bằng publisher kiểm soát được để kiểm tra logic của service; dùng integration test riêng cho driver và transport.

## 15. Những lỗi thường gặp

- **Quên gọi verify:** tạo expectation nhưng test không subscribe, nên publisher chưa chạy.
- **Chỉ kiểm tra giá trị cuối:** bỏ qua phần tử trung gian hoặc thứ tự tín hiệu có thể làm pipeline sai mà test vẫn qua.
- **Dùng expectNextCount để khẳng định thứ tự:** phương thức chỉ kiểm tra số lượng, không kiểm tra nội dung.
- **Gọi verifyComplete sau khi mong lỗi:** terminal expectation không khớp; dùng `expectError...().verify()`.
- **Coi cancellation là completion:** dùng `thenCancel().verify()` cho kịch bản hủy.
- **Dùng Thread.sleep cho timer:** test chậm và dễ chập chờn; dùng virtual time khi publisher dùng scheduler tương thích.
- **Tạo timer trước withVirtualTime:** publisher có thể giữ scheduler thật và không chạy theo đồng hồ ảo.
- **Dùng expectNoEvent trước expectSubscription:** subscription ban đầu cũng được xem là một sự kiện.
- **Khẳng định thứ tự với flatMap không bảo đảm thứ tự:** chọn operator có hợp đồng thứ tự hoặc kiểm tra tập kết quả nếu thứ tự không quan trọng.
- **Không đặt timeout cho test có thể treo:** dùng `verify(Duration)` phù hợp hoặc cấu hình timeout mặc định cho bộ test.
- **Nhầm verify timeout với publisher timeout:** hai cơ chế có mục đích khác nhau.
- **Chỉ test doOnCancel rồi kết luận I/O đã dừng:** cần kiểm tra adapter/driver hoặc integration test cho lớp I/O.
- **Dùng assertion quá rộng:** kiểm tra loại lỗi hoặc số lượng chung chung có thể bỏ qua lỗi sai; xác minh exception và dữ liệu theo hợp đồng.

## 16. Checklist trước khi hoàn tất test StepVerifier

Trước khi xem test là đủ, hãy tự hỏi:

1. Test đã subscribe publisher bằng một phương thức `verify...()` chưa?
2. Có xác minh đúng giá trị và số lượng phần tử không?
3. Thứ tự có phải một phần của hợp đồng không, và test có kiểm tra đúng điều đó không?
4. Terminal signal mong đợi là complete, error hay cancellation?
5. Nếu có lỗi, test có kiểm tra loại, message hoặc nguyên nhân phù hợp không?
6. Nếu kiểm tra demand, initial request và các lần request tiếp theo có được điều khiển rõ không?
7. Nếu có timer, có thể dùng virtual time không?
8. Publisher dùng scheduler mặc định có được tạo bên trong supplier của `withVirtualTime` không?
9. Test có giới hạn thời gian chờ hợp lý không?
10. Test đang xác minh tín hiệu reactive hay cần integration test để xác minh side effect ở database/network?

`StepVerifier` mô tả một subscriber kiểm thử bằng chuỗi expectation. `expectNext`, `assertNext` và `expectNextCount` xác minh dữ liệu; thứ tự expectation xác minh thứ tự tín hiệu; `verifyComplete` và `expectError...().verify()` xác minh terminal signal; `thenCancel` kiểm tra cancellation; `thenRequest` điều khiển demand; virtual time kiểm tra publisher có timer mà không chờ đồng hồ thật. Một test tốt thể hiện đúng hợp đồng mà consumer dựa vào, gồm dữ liệu, thứ tự và cách pipeline kết thúc. Khi cần xác minh tác động ở database, HTTP client hoặc driver, hãy bổ sung integration test thay vì suy luận từ tín hiệu của publisher.
