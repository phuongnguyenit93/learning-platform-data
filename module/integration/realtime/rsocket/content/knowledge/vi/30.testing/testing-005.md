# Tạo nguồn kiểm thử bằng TestPublisher

Khi kiểm thử một luồng reactive, chỉ kiểm tra giá trị đầu ra đôi khi chưa đủ. Ta còn cần chủ động quyết định khi nào nguồn phát phần tử, khi nào hoàn tất, khi nào phát lỗi và subscriber đã yêu cầu bao nhiêu phần tử. Một nguồn dữ liệu thật như database change stream hoặc message broker khó điều khiển chính xác các thời điểm này trong unit test.

Reactor Test cung cấp **TestPublisher** để tạo một Publisher do bài kiểm thử điều khiển. Test có thể phát dữ liệu theo từng bước, kết thúc bằng complete hoặc error, rồi kiểm tra subscriber đã yêu cầu dữ liệu hay đã hủy subscription. Kết hợp TestPublisher với StepVerifier giúp kiểm tra pipeline reactive một cách xác định mà không cần mở kết nối RSocket hoặc chạy broker thật.

Trong module RSocket, cách làm này hữu ích khi kiểm thử service tạo request-stream, request-channel, xử lý event, áp dụng backpressure hoặc dọn tài nguyên khi client hủy stream.

## 1. TestPublisher giải quyết vấn đề gì?

Giả sử một service theo dõi trạng thái đơn hàng bằng Flux<OrderEvent>. Nguồn event đến từ repository hoặc broker. Một bài kiểm thử cần xác minh:

- Service chuyển tiếp đúng các event và giữ thứ tự.
- Event chỉ được xử lý khi có demand.
- Lỗi từ nguồn được truyền hoặc chuyển đổi theo hợp đồng.
- Khi client hủy stream, service hủy subscription upstream.
- Khi nguồn complete, luồng đầu ra cũng kết thúc đúng cách.

Nếu dùng nguồn thật, bài test phải phụ thuộc vào database, broker, timing hoặc thread khác. TestPublisher cho phép test phát tín hiệu ngay tại bước mong muốn và quan sát hành vi của pipeline.

Phân biệt ba công cụ thường dùng:

| Công cụ | Vai trò |
|---|---|
| TestPublisher | Nguồn phát tín hiệu do test điều khiển |
| StepVerifier | Subscriber kiểm tra tín hiệu, demand, lỗi, complete và cancellation |

TestPublisher không tự xác minh kết quả của pipeline. Nó chỉ tạo nguồn; StepVerifier mới đăng ký vào publisher đầu ra và mô tả chuỗi hành vi mong đợi.

## 2. Thêm dependency Reactor Test

Trong dự án dùng Gradle, thư viện Reactor Test thường được khai báo ở test scope:

~~~groovy
dependencies {
    testImplementation("io.projectreactor:reactor-test")
}
~~~

Nếu dự án quản lý phiên bản bằng Spring Boot dependency management hoặc Reactor BOM, không cần tự đặt version riêng trừ khi dự án có quy định khác. Với Maven, dùng dependency reactor-test có scope test.

Các ví dụ dưới đây dùng JUnit 5, Reactor Core và Reactor Test. Tên lớp domain như OrderEvent hoặc OrderEventService là ví dụ do ứng dụng định nghĩa.

## 3. Tạo TestPublisher và lấy Flux

Tạo một nguồn test bằng TestPublisher.create(), sau đó lấy Flux mà service sẽ tiêu thụ:

~~~java
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;
import reactor.test.publisher.TestPublisher;

TestPublisher<String> source = TestPublisher.create();
Flux<String> events = source.flux();
~~~

TestPublisher cũng có thể cung cấp Mono qua phương thức mono() khi bài test cần mô phỏng nguồn tối đa một phần tử:

~~~java
TestPublisher<String> source = TestPublisher.create();
Mono<String> result = source.mono();
~~~

TestPublisher có thể được truyền trực tiếp như một Publisher, hoặc chuyển thành Flux/Mono để dùng các toán tử Reactor. Trong code production, không để TestPublisher xuất hiện trong service; hãy inject interface Publisher/Flux từ dependency và chỉ tạo TestPublisher ở test.

## 4. Điều khiển tín hiệu next, complete và error

TestPublisher cung cấp các thao tác chính:

| Phương thức | Hành vi |
|---|---|
| next(value...) | Phát một hoặc nhiều phần tử, chưa kết thúc nguồn |
| complete() | Phát tín hiệu hoàn tất |
| error(exception) | Kết thúc nguồn bằng lỗi |
| emit(value...) | Phát các phần tử rồi hoàn tất nguồn |
| flux() | Trả view Flux của nguồn |
| mono() | Trả view Mono của nguồn |

Ví dụ phát dữ liệu theo từng bước:

~~~java
TestPublisher<Integer> source = TestPublisher.create();

source.next(10);
source.next(20, 30);
source.complete();
~~~

Nếu muốn phát các phần tử rồi complete trong một thao tác, dùng emit:

~~~java
source.emit(10, 20, 30);
~~~

Không gọi emit khi bài test cần giữ stream mở để phát thêm dữ liệu hoặc kiểm tra cancellation. Khi muốn kiểm tra lỗi, dùng error:

~~~java
source.error(new IllegalStateException("source unavailable"));
~~~

Complete và error là tín hiệu kết thúc. Sau khi một nguồn đã kết thúc, không tiếp tục phát thêm dữ liệu như thể đó là stream bình thường.

## 5. Viết test đầu tiên với StepVerifier

StepVerifier đăng ký vào publisher khi verify được thực thi. Dùng then để phát tín hiệu từ TestPublisher sau khi subscription của verifier đã bắt đầu:

~~~java
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

class TestPublisherBasicsTest {

    @Test
    void shouldEmitValuesAndComplete() {
        TestPublisher<Integer> source = TestPublisher.create();

        StepVerifier.create(source.flux())
            .then(() -> source.next(10))
            .expectNext(10)
            .then(() -> source.next(20, 30))
            .expectNext(20, 30)
            .then(() -> source.complete())
            .verifyComplete();
    }
}
~~~

Trình tự trên có ý nghĩa:

1. StepVerifier đăng ký vào Flux.
2. then gọi source.next(10).
3. expectNext xác nhận phần tử đầu tiên.
4. Test phát thêm hai phần tử và verifier xác nhận đúng thứ tự.
5. Test phát complete và verifyComplete xác nhận không còn phần tử nào.

Đặt thao tác phát tín hiệu trong then giúp bài test không phát dữ liệu quá sớm trước khi subscriber được đăng ký.

## 6. Dùng TestPublisher làm dependency của service

Ví dụ service nhận event từ repository và chỉ giữ các event hợp lệ:

~~~java
import reactor.core.publisher.Flux;

public interface OrderEventRepository {
    Flux<OrderEvent> watch(String orderId);
}

public class OrderEventService {

    private final OrderEventRepository repository;

    public OrderEventService(OrderEventRepository repository) {
        this.repository = repository;
    }

    public Flux<OrderEvent> watch(String orderId) {
        return repository.watch(orderId)
            .filter(OrderEvent::isVisible);
    }
}
~~~

Trong test, mock repository trả về Flux từ TestPublisher:

~~~java
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

class OrderEventServiceTest {

    @Test
    void shouldForwardVisibleEventsInOrder() {
        OrderEventRepository repository = mock(OrderEventRepository.class);
        TestPublisher<OrderEvent> source = TestPublisher.create();
        when(repository.watch("ORD-42")).thenReturn(source.flux());

        OrderEventService service = new OrderEventService(repository);
        OrderEvent accepted = visibleEvent(1);
        OrderEvent hidden = hiddenEvent(2);
        OrderEvent next = visibleEvent(3);

        StepVerifier.create(service.watch("ORD-42"))
            .then(() -> source.next(accepted, hidden, next))
            .expectNext(accepted, next)
            .then(() -> source.complete())
            .verifyComplete();

        source.assertWasRequested();
    }
}
~~~

mock, visibleEvent và hiddenEvent là helper của test. TestPublisher giúp phát một chuỗi event đã biết, còn StepVerifier kiểm tra service chỉ chuyển tiếp event thỏa điều kiện.

## 7. Hot và cold TestPublisher

TestPublisher.create() tạo nguồn kiểu hot: tín hiệu được phát tới các subscriber hiện có. Nếu phát tín hiệu trước khi có subscriber, không nên kỳ vọng một subscriber đăng ký sau sẽ nhận lại các tín hiệu đó.

TestPublisher.createCold() tạo nguồn kiểu cold để giữ tín hiệu được phát trước khi có subscriber và cung cấp chúng khi có subscriber. Chế độ này hữu ích khi cần chuẩn bị dữ liệu trước khi bắt đầu verify:

~~~java
TestPublisher<String> source = TestPublisher.createCold();
source.next("first", "second");
source.complete();

StepVerifier.create(source.flux())
    .expectNext("first", "second")
    .verifyComplete();
~~~

Chọn loại nguồn theo hành vi cần mô phỏng. Dùng create() khi muốn điều khiển một nguồn nóng và phát tín hiệu sau khi subscriber đã sẵn sàng. Dùng createCold() khi bài test cần buffer các tín hiệu được chuẩn bị trước. Không suy ra rằng createCold mô phỏng đầy đủ mọi hành vi replay/cache của một broker; nếu cần kiểm tra replay cho nhiều subscriber, hãy kiểm tra rõ semantics của nguồn thực tế và viết test riêng.

## 8. Kiểm tra demand và backpressure

StepVerifier có thể bắt đầu với demand bằng 0. Điều này giúp xác minh service chưa yêu cầu upstream phát dữ liệu trước khi downstream có nhu cầu:

~~~java
import static org.mockito.Mockito.when;

// Giả định repository và service đã được tạo trong test fixture.
TestPublisher<OrderEvent> source = TestPublisher.create();
when(repository.watch("ORD-42")).thenReturn(source.flux());

StepVerifier.create(service.watch("ORD-42"), 0)
    .then(() -> source.assertWasNotRequested())
    .thenRequest(1)
    .then(() -> source.next(visibleEvent(1)))
    .expectNextCount(1)
    .thenCancel()
    .verify();

source.assertWasRequested();
~~~

Ví dụ này giả định service truyền demand trực tiếp qua các toán tử không tạo prefetch. Nếu pipeline dùng publishOn, flatMap hoặc một operator có prefetch, upstream có thể nhận request trước khi downstream yêu cầu phần tử đầu tiên. Khi đó cần kiểm tra demand theo semantics của operator, không kết luận pipeline sai chỉ vì source đã được request.

Có thể dùng các assertion của TestPublisher để quan sát demand:

- assertWasRequested(): nguồn đã nhận ít nhất một request.
- assertWasNotRequested(): nguồn chưa nhận request.
- assertMinRequested(n): tổng demand đã nhận ít nhất n.
- assertMaxRequested(n): tổng demand không vượt quá n.
- assertNoRequestOverflow(): không có dấu hiệu phát vượt demand theo chế độ tuân thủ của nguồn.

Demand thường được cộng dồn. Khi kiểm tra một con số chính xác, cần xét request ban đầu, request bổ sung và prefetch của các operator ở giữa.

## 9. Kiểm tra cancellation

Khi client hủy subscription, cancellation cần được truyền ngược về nguồn nếu pipeline không chủ động tách subscription. TestPublisher cho phép xác minh nguồn đã nhận cancel:

~~~java
import static org.mockito.Mockito.when;

// Giả định repository và service đã được tạo trong test fixture.
TestPublisher<OrderEvent> source = TestPublisher.create();
when(repository.watch("ORD-42")).thenReturn(source.flux());

StepVerifier.create(service.watch("ORD-42"), 0)
    .thenRequest(1)
    .then(() -> source.next(visibleEvent(1)))
    .expectNextCount(1)
    .thenCancel()
    .verify();

source.assertCancelled();
~~~

Đây là kiểm thử quan trọng với RSocket request-stream. Khi client gửi CANCEL hoặc hủy subscription ở phía ứng dụng, server cần dừng publisher tương ứng và giải phóng listener, consumer hoặc tài nguyên đang được giữ.

Nếu service dùng cache hoặc chia sẻ một upstream giữa nhiều subscriber, việc một subscriber cancel không nhất thiết hủy nguồn dùng chung. Khi đó cần kiểm tra chính sách ref-count/share của pipeline thay vì mong source luôn bị cancel sau khi một subscriber rời đi.

## 10. Kiểm tra complete và error

Một nguồn có thể kết thúc bình thường:

~~~java
import static org.mockito.Mockito.when;

// Giả định repository và service đã được tạo trong test fixture.
TestPublisher<OrderEvent> source = TestPublisher.create();
when(repository.watch("ORD-42")).thenReturn(source.flux());

StepVerifier.create(service.watch("ORD-42"))
    .then(() -> source.emit(visibleEvent(1), visibleEvent(2)))
    .expectNextCount(2)
    .verifyComplete();
~~~

Hoặc kết thúc bằng lỗi:

~~~java
import static org.mockito.Mockito.when;

// Giả định repository và service đã được tạo trong test fixture.
TestPublisher<OrderEvent> source = TestPublisher.create();
when(repository.watch("ORD-42")).thenReturn(source.flux());
RuntimeException failure = new RuntimeException("event source failed");

StepVerifier.create(service.watch("ORD-42"))
    .then(() -> source.next(visibleEvent(1)))
    .expectNextCount(1)
    .then(() -> source.error(failure))
    .expectErrorMatches(error -> error == failure)
    .verify();
~~~

Nếu service có onErrorResume để chuyển lỗi thành fallback, kiểm tra đúng fallback theo hợp đồng:

~~~java
import static org.mockito.Mockito.when;

// Giả định repository và service đã được tạo trong test fixture.
TestPublisher<OrderEvent> source = TestPublisher.create();
when(repository.watch("ORD-42")).thenReturn(source.flux());

StepVerifier.create(service.watchWithFallback("ORD-42"))
    .then(() -> source.error(new IllegalStateException("offline")))
    .expectNext(fallbackEvent())
    .verifyComplete();
~~~

Không nên chỉ kiểm tra rằng có lỗi. Hãy kiểm tra loại lỗi, thông điệp hoặc domain error code cần thiết, và xác nhận service có chuyển đổi lỗi đúng tầng hay không.

## 11. Dùng TestPublisher để kiểm tra toán tử và thứ tự

Nguồn do test điều khiển giúp tạo các tình huống cụ thể:

- Phần tử hợp lệ xen giữa phần tử không hợp lệ để kiểm tra filter.
- Nhiều phần tử liên tiếp để kiểm tra thứ tự.
- Nguồn phát chậm theo từng bước để kiểm tra concatMap hoặc flatMap.
- Lỗi xuất hiện sau một số phần tử để kiểm tra hành vi partial result.
- Nguồn không complete để kiểm tra stream dài và cancellation.

Ví dụ kiểm tra rằng service chỉ phát response khi từng tác vụ bất đồng bộ hoàn tất:

~~~java
import static org.mockito.Mockito.when;

TestPublisher<OrderCommand> commands = TestPublisher.create();
TestPublisher<OrderResult> firstResult = TestPublisher.create();

when(processor.process(commandA)).thenReturn(firstResult.mono());

StepVerifier.create(service.process(commands.flux()))
    .then(() -> commands.next(commandA))
    .then(() -> firstResult.next(resultA))
    .expectNext(resultA)
    .thenCancel()
    .verify();
~~~

Ví dụ là phác thảo cho service dùng concatMap; test thực tế cần cấu hình processor cho từng command và xác nhận command tiếp theo chỉ được xử lý khi semantics của pipeline cho phép.

## 12. Kiểm tra publisher không tuân thủ Reactive Streams

Theo Reactive Streams, Publisher phải tôn trọng demand và không phát null. Trong một số bài kiểm thử phòng thủ, có thể cần mô phỏng nguồn vi phạm hợp đồng để xem pipeline hoặc adapter xử lý thế nào.

TestPublisher.createNoncompliant(...) tạo nguồn với một hoặc nhiều Violation được chọn. Ví dụ REQUEST_OVERFLOW cho phép test phát onNext vượt demand:

~~~java
TestPublisher<Integer> source =
    TestPublisher.createNoncompliant(
        TestPublisher.Violation.REQUEST_OVERFLOW
    );
~~~

Chỉ dùng nguồn non-compliant khi bài test cố ý kiểm tra hành vi với upstream lỗi hợp đồng. Với test nghiệp vụ thông thường, dùng TestPublisher.create() tuân thủ quy tắc để không tạo ra tín hiệu mà publisher thật không được phép phát.

Một test non-compliant cần ghi rõ điều đang mô phỏng, phản ứng mong đợi và giới hạn của kết luận. Không dùng nó để khẳng định một pipeline xử lý đúng mọi loại publisher vi phạm.

## 13. Kiểm tra subscription và trạng thái nguồn

TestPublisher có các assertion để kiểm tra vòng đời subscription:

| Assertion | Mục đích |
|---|---|
| assertSubscribers() | Xác nhận nguồn có subscriber |
| assertNoSubscribers() | Xác nhận không còn subscriber |
| assertCancelled() | Xác nhận subscription đã bị cancel |
| assertNotCancelled() | Xác nhận chưa có cancellation |
| assertWasRequested() | Xác nhận nguồn đã nhận demand |
| assertWasNotRequested() | Xác nhận nguồn chưa nhận demand |

Ví dụ xác nhận service đăng ký vào nguồn trong lúc verify:

~~~java
import static org.mockito.Mockito.when;

// Giả định repository và service đã được tạo trong test fixture.
TestPublisher<OrderEvent> source = TestPublisher.create();
when(repository.watch("ORD-42")).thenReturn(source.flux());

StepVerifier.create(service.watch("ORD-42"))
    .then(() -> source.assertSubscribers())
    .thenCancel()
    .verify();

source.assertCancelled();
~~~

Sau khi terminal signal hoặc cancellation, trạng thái subscriber có thể được dọn theo semantics của TestPublisher. Nên đặt assertion tại đúng thời điểm cần quan sát, thường là bên trong then trước khi kết thúc verifier.

## 14. Kết hợp TestPublisher với virtual time

TestPublisher điều khiển tín hiệu dữ liệu; nó không tự điều khiển đồng hồ. Khi cần kiểm tra timeout, delay, retry backoff hoặc interval, kết hợp TestPublisher với StepVerifier.withVirtualTime và scheduler ảo.

Ví dụ service đặt timeout cho stream:

~~~java
import java.time.Duration;

public Flux<OrderEvent> watchWithTimeout(String orderId) {
    return repository.watch(orderId)
        .timeout(Duration.ofSeconds(5));
}
~~~

Test dùng virtual time và một TestPublisher chưa phát tín hiệu:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeoutException;
import static org.mockito.Mockito.when;
import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;
import reactor.test.publisher.TestPublisher;

// Giả định repository và service đã được tạo trong test fixture.
TestPublisher<OrderEvent> source = TestPublisher.create();
when(repository.watch("ORD-42")).thenReturn(source.flux());

StepVerifier.withVirtualTime(() -> service.watchWithTimeout("ORD-42"))
    .thenAwait(Duration.ofSeconds(5))
    .expectError(TimeoutException.class)
    .verify();
~~~

Nếu service phụ thuộc vào TestPublisher, hãy tạo nguồn trước hoặc trong supplier theo đúng thời điểm subscription, rồi phát tín hiệu trong then. Đảm bảo operator thời gian được tạo sau khi virtual scheduler được cài đặt; nếu tạo publisher có timer trước supplier, nó có thể giữ scheduler thật và làm test không chạy theo virtual time.

Không dùng Thread.sleep trong test reactive để chờ event. Điều khiển tín hiệu bằng TestPublisher và thời gian bằng StepVerifier virtual time giúp bài test nhanh, xác định và ít phụ thuộc môi trường.

## 15. Những giới hạn của TestPublisher

TestPublisher là công cụ unit test cho Reactive Streams, không thay thế integration test:

- Nó không kiểm tra RSocket frame, transport TCP/WebSocket hoặc codec serialization.
- Nó không mô phỏng đầy đủ latency, packet loss, reconnect hay connection resumption.
- Nó không tự xác nhận Spring route hoặc authentication metadata.
- Nó không chứng minh broker/database có semantics giống nguồn test.
- Nó không thay thế test tải hoặc test race thực tế.

Với RSocket, có thể kiểm tra logic handler/service bằng TestPublisher trước. Sau đó dùng RSocketRequester và server thật trong integration test để xác minh route, metadata, cancellation và transport.

## 16. Lỗi thường gặp

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| StepVerifier không nhận phần tử | Test phát tín hiệu trước khi subscriber được đăng ký hoặc nguồn hot đã bỏ tín hiệu | Phát trong then sau khi verify bắt đầu |
| Test treo chờ complete | Đã gọi next nhưng quên complete hoặc error | Phát terminal signal hoặc dùng thenCancel |
| Assertion demand không như mong đợi | Operator trung gian prefetch hoặc yêu cầu theo batch | Kiểm tra semantics request của từng operator |
| Không thấy cancellation ở source | Pipeline dùng shared source hoặc subscription tách rời | Kiểm tra ownership và compose publisher đúng cách |
| Test lỗi không ổn định | Dùng delay/sleep hoặc thread ngoài không đồng bộ | Điều khiển tín hiệu bằng then và virtual time |
| Dùng non-compliant publisher cho test thường | Nguồn phát tín hiệu trái Reactive Streams | Dùng create() trừ khi đang kiểm tra lỗi hợp đồng |
| Nghĩ TestPublisher kiểm tra được transport | Test chỉ chạy trong cùng tiến trình | Bổ sung integration test RSocket |

## 17. Checklist viết test với TestPublisher

Trước khi hoàn tất bài test, xác nhận:

- TestPublisher được tạo trong test và không lọt vào production code.
- Chọn hot hoặc cold source theo đúng tình huống cần mô phỏng.
- Tín hiệu được phát sau khi subscriber sẵn sàng, trừ khi đang kiểm tra cold buffering.
- Test xác minh cả next và terminal signal.
- Demand và cancellation được kiểm tra khi có ý nghĩa với pipeline.
- Lỗi được kiểm tra theo domain contract.
- Non-compliant mode chỉ dùng trong test phòng thủ có chủ đích.
- Không dùng sleep để đồng bộ bài test.
- Test transport và serialization được thực hiện ở integration test riêng.

## 18. Kết luận

TestPublisher tạo nguồn dữ liệu reactive có thể điều khiển từ bài kiểm thử. Test có thể phát next, complete hoặc error đúng thời điểm, kiểm tra demand và xác nhận cancellation. TestPublisher.create() phù hợp với nguồn hot; createCold() hỗ trợ giữ tín hiệu trước khi có subscriber. Khi kết hợp với StepVerifier, ta kiểm tra được thứ tự dữ liệu, backpressure, lỗi và vòng đời subscription một cách rõ ràng.

Đối với hệ thống RSocket, hãy dùng TestPublisher để kiểm tra logic reactive trong service và handler, sau đó dùng integration test để xác nhận hành vi qua transport thực. Phân chia đúng hai lớp kiểm thử giúp bài test nhanh, xác định và vẫn bao phủ được những vấn đề riêng của kết nối realtime.
