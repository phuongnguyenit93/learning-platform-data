# Kiểm thử timeout, kết nối lại và client chậm mà không dựa vào sleep tùy ý

Các luồng messaging là bất đồng bộ: thời điểm phát tín hiệu, thời điểm nhận response và thời điểm kết nối được khôi phục không nhất thiết trùng nhau. Một bài test dùng **Thread.sleep** để chờ một khoảng thời gian cố định thường phụ thuộc vào tốc độ máy, tải CI và lịch chạy thread. Khi môi trường chậm hơn dự kiến, test có thể fail dù code đúng; khi môi trường nhanh, test lại lãng phí thời gian.

Cách kiểm thử đáng tin cậy là điều khiển thời gian và tín hiệu một cách chủ động:

- Dùng **Reactor Virtual Time** cho các operator có thời gian như timeout, delay và retry backoff.
- Dùng **StepVerifier** để xác nhận thứ tự tín hiệu, thời điểm timeout và lượng request mà subscriber phát ra.
- Dùng tín hiệu đồng bộ có giới hạn thời gian hoặc điều kiện eventual cho kiểm thử tích hợp với socket/broker thật.
- Dùng backpressure để mô phỏng client nhận dữ liệu chậm bằng cách yêu cầu từng phần tử, thay vì làm thread ngủ.
- Kiểm thử riêng chính sách reconnect, việc gửi lại request và hành vi của transport khi kết nối bị ngắt.

## 1. Vì sao Thread.sleep làm test messaging thiếu ổn định?

Một test kiểu sau có nhiều giả định không được kiểm soát:

~~~java
@Test
void shouldReceiveMessageAfterDelay() throws Exception {
    sender.send("orders.created", event);

    Thread.sleep(1000);

    assertEquals(1, repository.count());
}
~~~

Test giả định rằng một giây luôn đủ để message đi qua broker, listener, transaction và thao tác lưu dữ liệu. Nhưng thời gian thực tế có thể thay đổi vì:

- CI đang chạy nhiều test hoặc nhiều tiến trình.
- Broker vừa khởi động hoặc đang rebalance consumer.
- Thread xử lý message chưa được scheduler chạy.
- Database hoặc network phản hồi chậm.
- Test chạy song song và tranh chấp tài nguyên.
- Message đã được nhận nhưng transaction chưa commit.

Tăng sleep lên vài giây chỉ làm test chậm hơn và vẫn không chứng minh được điều kiện đã xảy ra. Nếu message chưa tới sau khoảng chờ, test chỉ biết thời gian đã trôi qua chứ không biết thành phần nào đang chậm.

Thay vào đó, hãy chờ **một điều kiện có ý nghĩa**: publisher phát onError, server nhận kết nối thứ hai, latch báo consumer đã xử lý message hoặc một assertion trở thành đúng. Mỗi lần chờ cần có deadline để test không treo vô hạn.

## 2. Phân biệt các loại timeout

Không phải timeout nào cũng có cùng ý nghĩa. Khi viết test, cần xác định điều gì đang bị giới hạn:

| Loại timeout | Ý nghĩa | Ví dụ |
|---|---|---|
| Connection timeout | Giới hạn thời gian thiết lập kết nối | TCP connect tới RSocket server |
| Response timeout | Giới hạn thời gian chờ một response | Request-Response không trả kết quả |
| Inactivity/idle timeout | Giới hạn thời gian không có tín hiệu mới | Request-Stream bị ngừng phát |
| Overall deadline | Giới hạn tổng thời gian cho cả operation | Toàn bộ quy trình xử lý không quá 10 giây |
| Test verification timeout | Giới hạn thời gian test được phép chờ | StepVerifier phải hoàn tất trong 2 giây thời gian thật |

Trong Reactor, **timeout(Duration)** trên Mono giới hạn thời gian chờ kết quả. Trên Flux, operator này áp dụng timeout giữa các tín hiệu: nếu không có phần tử tiếp theo trong khoảng quy định, publisher phát lỗi timeout. Điều đó khác với một deadline tổng cho toàn bộ stream.

Không dùng một giá trị timeout duy nhất cho mọi lớp. Ví dụ, connection timeout ngắn không thay thế response timeout; timeout của StepVerifier chỉ bảo vệ test khỏi treo, không cấu hình timeout của request trong ứng dụng.

## 3. Kiểm thử timeout bằng StepVerifier và Virtual Time

**StepVerifier** cho phép mô tả các tín hiệu mong đợi của một Publisher. **withVirtualTime** thay scheduler mặc định của Reactor bằng đồng hồ ảo để test có thể tiến thời gian mà không phải đợi thật.

Ví dụ kiểm tra một request không bao giờ trả kết quả và phải timeout sau năm giây:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.time.Duration;
import java.util.concurrent.TimeoutException;

import org.junit.jupiter.api.Test;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

class TimeoutTest {

    @Test
    void shouldTimeoutWithoutWaitingFiveRealSeconds() {
        StepVerifier.withVirtualTime(() ->
                Mono.<String>never()
                    .timeout(Duration.ofSeconds(5))
            )
            .expectSubscription()
            .thenAwait(Duration.ofSeconds(5))
            .expectError(TimeoutException.class)
            .verify(Duration.ofSeconds(1));
    }
}
~~~

Test tiến đồng hồ ảo năm giây rồi xác nhận lỗi **TimeoutException**. Tham số của **verify** là giới hạn thời gian thật để bảo vệ chính test; nó không làm thay đổi timeout năm giây của publisher.

**Phải tạo publisher bên trong supplier** của **withVirtualTime**. Nếu tạo **Mono.delay**, **Flux.interval** hoặc operator timeout trước khi đồng hồ ảo được kích hoạt, operator có thể đã giữ scheduler thật và test không còn được điều khiển như mong đợi.

Ví dụ đúng:

~~~java
StepVerifier.withVirtualTime(() ->
        Mono.delay(Duration.ofMinutes(10))
    )
    .expectSubscription()
    .thenAwait(Duration.ofMinutes(10))
    .expectNext(0L)
    .verifyComplete();
~~~

Không cần đợi mười phút theo thời gian thật. Test hoàn tất sau khi virtual clock được tiến đủ thời lượng.

### Kiểm tra response đến trước deadline

~~~java
@Test
void shouldReturnResponseBeforeTimeout() {
    StepVerifier.withVirtualTime(() ->
            Mono.delay(Duration.ofSeconds(2))
                .thenReturn("OK")
                .timeout(Duration.ofSeconds(5))
        )
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(2))
        .expectNext("OK")
        .verifyComplete();
}
~~~

Test này xác nhận response đến sau hai giây ảo và trước timeout năm giây. Nên có cả test thành công lẫn test timeout để tránh một cấu hình timeout quá ngắn làm hỏng request bình thường.

### Kiểm tra timeout cho stream

~~~java
@Test
void shouldTimeoutWhenFluxStopsEmitting() {
    StepVerifier.withVirtualTime(() ->
            Flux.concat(
                Flux.just("first"),
                Mono.<String>never()
            ).timeout(Duration.ofSeconds(3))
        )
        .expectSubscription()
        .expectNext("first")
        .thenAwait(Duration.ofSeconds(3))
        .expectError(TimeoutException.class)
        .verify(Duration.ofSeconds(1));
}
~~~

Sau phần tử đầu tiên, Flux không phát thêm dữ liệu. Test xác nhận timeout giữa các tín hiệu xảy ra sau ba giây ảo.

Nếu cần giới hạn tổng thời lượng của một stream, hãy thiết kế deadline tổng riêng, ví dụ bằng **take(Duration)** hoặc một deadline được truyền qua toàn bộ operation. Đừng nhầm timeout giữa hai phần tử với thời hạn hoàn tất toàn bộ luồng.

## 4. Kiểm thử retry và backoff bằng Virtual Time

Khi một thao tác lỗi tạm thời, ứng dụng có thể thử lại sau một khoảng chờ tăng dần. Reactor cung cấp **Retry.fixedDelay** và **Retry.backoff** để mô tả chính sách này.

Ví dụ: thử lại tối đa hai lần, mỗi lần cách nhau một giây:

~~~java
import java.io.IOException;
import java.time.Duration;
import java.util.concurrent.atomic.AtomicInteger;

import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;
import reactor.util.retry.Retry;

@Test
void shouldRetryTransientFailureWithVirtualTime() {
    AtomicInteger attempts = new AtomicInteger();

    StepVerifier.withVirtualTime(() ->
            Mono.defer(() -> {
                int attempt = attempts.incrementAndGet();

                if (attempt < 3) {
                    return Mono.error(
                        new IOException("temporary failure")
                    );
                }

                return Mono.just("connected");
            })
            .retryWhen(
                Retry.fixedDelay(2, Duration.ofSeconds(1))
            )
        )
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(2))
        .expectNext("connected")
        .verifyComplete();

    assertEquals(3, attempts.get());
}
~~~

Hai lần đầu phát lỗi; lần thứ ba thành công. Hai khoảng delay được tiến bằng virtual time nên test không cần sleep.

Nếu dùng **Retry.backoff**, hãy kiểm tra cả thời gian chờ tăng dần, giới hạn tối đa và jitter. Ví dụ cấu hình production:

~~~java
Retry retryPolicy = Retry.backoff(
        5,
        Duration.ofMillis(200)
    )
    .maxBackoff(Duration.ofSeconds(3))
    .jitter(0.5)
    .filter(this::isTransientFailure);
~~~

**maxAttempts** trong Retry là số lần retry sau lần gọi ban đầu. Với giá trị 5, tổng số lần thực thi có thể là 6. Bộ lọc lỗi nên chỉ cho phép retry các lỗi tạm thời như lỗi kết nối hoặc lỗi dịch vụ có thể phục hồi. Không retry lỗi validation, lỗi phân quyền hoặc lỗi nghiệp vụ vĩnh viễn.

### Retry phải an toàn với nghiệp vụ

Retry có thể tạo tác dụng phụ trùng lặp. Ví dụ, server đã xử lý lệnh tạo đơn nhưng response bị mất trên đường truyền. Client không biết thao tác đã hoàn tất nên gửi lại request. Nếu không có idempotency key, hệ thống có thể tạo hai đơn hàng.

Với command ghi dữ liệu, hãy cân nhắc:

- Gắn idempotency key ổn định cho cùng một ý định nghiệp vụ.
- Lưu kết quả theo key để request lặp lại trả cùng kết quả.
- Chỉ retry lỗi được phân loại là tạm thời.
- Đặt giới hạn số lần retry và tổng thời gian retry.
- Ghi nhận correlation ID và attempt number để quan sát.

Với stream, retry có thể subscribe lại từ đầu và phát lại phần tử đã nhận. Nếu cần tiếp tục từ vị trí trước khi ngắt, hãy thiết kế cursor, sequence number hoặc offset rõ ràng và kiểm thử duplicate handling.

## 5. Phân biệt reconnect và resume trong RSocket

Trong RSocket, hai khái niệm này giải quyết các vấn đề khác nhau:

- **Reconnect** thiết lập một kết nối RSocket mới sau khi kết nối hiện tại bị mất. Request bị lỗi vẫn cần logic retry ở phía subscriber nếu ứng dụng muốn gửi lại.
- **Resume** là khả năng tiếp tục một session RSocket sau khi gián đoạn. Cả hai phía phải hỗ trợ và cấu hình resume; protocol có thể tiếp tục các stream đang bị ngắt theo cơ chế lưu và phát lại frame.

Reconnect không đồng nghĩa với việc tự động phát lại mọi request đang chạy. Nếu kết nối mất sau khi server đã xử lý request nhưng trước khi client nhận response, client phải quyết định có gửi lại hay không. Đây là lý do idempotency quan trọng.

RSocket Java hỗ trợ cấu hình reconnect qua **RSocketConnector.reconnect(Retry)**. Spring **RSocketRequester.Builder** cung cấp callback **rsocketConnector** để tùy chỉnh connector bên dưới.

Ví dụ:

~~~java
import java.time.Duration;

import org.springframework.messaging.rsocket.RSocketRequester;
import reactor.util.retry.Retry;

RSocketRequester requester = RSocketRequester.builder()
    .rsocketConnector(connector ->
        connector.reconnect(
            Retry.backoff(5, Duration.ofMillis(200))
                .maxBackoff(Duration.ofSeconds(2))
        )
    )
    .tcp("localhost", 7000);
~~~

Đoạn cấu hình này yêu cầu connector thử thiết lập lại kết nối theo retry policy. Kết nối của **RSocketRequester** được thiết lập khi có request đầu tiên. Cần kiểm tra hành vi cụ thể theo phiên bản RSocket Java/Spring đang dùng.

Request riêng lẻ vẫn có thể cần retry:

~~~java
Mono<ServerStatus> status = requester
    .route("system.status")
    .retrieveMono(ServerStatus.class)
    .retryWhen(
        Retry.backoff(2, Duration.ofMillis(100))
            .filter(this::isTransientFailure)
    );
~~~

Connector reconnect quản lý việc có lại connection; **retryWhen** ở request quản lý việc thử lại operation. Hai chính sách cần được phối hợp để không retry vô hạn hoặc tạo request trùng.

## 6. Kiểm thử chính sách reconnect mà không cần socket thật

Có thể kiểm tra chính sách retry độc lập với transport bằng một Publisher mô phỏng kết nối thất bại rồi thành công. Cách này xác nhận số lần thử, khoảng backoff và cách xử lý lỗi mà không cần khởi động server.

Ví dụ ở phần retry dùng **Mono.defer** để mô phỏng một lần connect. Bài test nên kiểm tra:

1. Lần thử đầu tiên thất bại bằng lỗi tạm thời.
2. Retry chỉ diễn ra sau khoảng delay đã cấu hình.
3. Số lần retry không vượt giới hạn.
4. Khi kết nối thành công, publisher hoàn tất.
5. Nếu hết retry, lỗi cuối cùng được truyền về caller.

Có thể kiểm thử trường hợp hết retry:

~~~java
@Test
void shouldFailAfterRetryLimit() {
    AtomicInteger attempts = new AtomicInteger();

    StepVerifier.withVirtualTime(() ->
            Mono.defer(() -> {
                attempts.incrementAndGet();
                return Mono.<String>error(
                    new IOException("server unavailable")
                );
            })
            .retryWhen(
                Retry.fixedDelay(2, Duration.ofSeconds(1))
            )
        )
        .expectSubscription()
        .thenAwait(Duration.ofSeconds(2))
        .expectError(IOException.class)
        .verify(Duration.ofSeconds(1));

    assertEquals(3, attempts.get());
}
~~~

Test này xác nhận một lần gọi ban đầu và hai lần retry. Nó kiểm thử chính sách Reactor, không chứng minh TCP transport hoặc RSocket session thực sự phục hồi. Cần có integration test riêng cho hành vi kết nối thật.

## 7. Kiểm thử reconnect với RSocket server thật

Integration test nên kiểm soát được vòng đời server và nhận biết rõ khi kết nối mới được thiết lập.

Một cách làm:

1. Khởi động RSocket server trên port dành riêng cho test.
2. Cấu hình requester với reconnect policy có số lần retry và backoff giới hạn.
3. Gửi request đầu tiên và xác nhận response.
4. Dừng server bằng API dispose/close của transport để tạo sự kiện mất kết nối xác định.
5. Khởi động lại server trên cùng port và chờ server báo đã sẵn sàng.
6. Subscribe lại request có retry policy phù hợp.
7. Dùng tín hiệu từ **@ConnectMapping** hoặc một probe trong test để xác nhận server đã nhận connection mới.
8. Xác nhận request thành công và kiểm tra không phát sinh tác dụng phụ trùng lặp.

Có thể dùng **CountDownLatch** hoặc **Sinks.One** để báo các sự kiện như server sẵn sàng và connection mới đã được thiết lập. Khi chờ latch, luôn đặt deadline:

~~~java
boolean connected = secondConnection.await(
    5,
    TimeUnit.SECONDS
);

assertTrue(connected, "RSocket did not reconnect in time");
~~~

Đây là chờ một sự kiện có điều kiện và có giới hạn thời gian. Nó khác với sleep cố định vì test chỉ tiếp tục khi tín hiệu thực sự đến; nếu không đến, assertion chỉ ra rõ timeout.

Ví dụ probe phía server có thể tăng bộ đếm khi một SETUP frame được xử lý:

~~~java
@Component
class ConnectionProbe {

    private final AtomicInteger connectionCount =
        new AtomicInteger();

    private final CountDownLatch secondConnection =
        new CountDownLatch(1);

    @ConnectMapping
    Mono<Void> connected() {
        if (connectionCount.incrementAndGet() >= 2) {
            secondConnection.countDown();
        }
        return Mono.empty();
    }

    boolean awaitSecondConnection(Duration timeout)
            throws InterruptedException {
        return secondConnection.await(
            timeout.toMillis(),
            TimeUnit.MILLISECONDS
        );
    }
}
~~~

Đây là ví dụ minh họa probe cho test. Trong test thật, cần tạo probe mới cho mỗi test case hoặc reset bộ đếm/latch phù hợp để tránh trạng thái từ lần chạy trước.

Không dùng virtual time để giả lập thời gian của TCP, Netty hoặc broker thật nếu các timer đó không dùng scheduler Reactor được thay thế. Virtual time phù hợp với operator Reactor; integration test transport cần deadline thời gian thật nhưng có điều kiện chờ rõ ràng.

## 8. Kiểm thử client chậm bằng backpressure

Trong Reactive Streams, subscriber điều khiển số phần tử muốn nhận thông qua demand. Client chậm có thể được mô phỏng bằng cách bắt đầu với demand bằng 0 rồi yêu cầu từng phần tử.

Ví dụ với **StepVerifier**:

~~~java
@Test
void shouldEmitOnlyWhenSubscriberRequests() {
    AtomicLong requested = new AtomicLong();

    Flux<Integer> source = Flux.range(1, 3)
        .doOnRequest(requested::addAndGet);

    StepVerifier.create(source, 0)
        .thenRequest(1)
        .expectNext(1)
        .thenRequest(1)
        .expectNext(2)
        .thenRequest(1)
        .expectNext(3)
        .verifyComplete();

    assertEquals(3L, requested.get());
}
~~~

**create(source, 0)** tạo subscriber ban đầu chưa yêu cầu phần tử nào. Mỗi **thenRequest(1)** tăng demand thêm một. Test xác nhận publisher chỉ được tiêu thụ theo nhịp mà subscriber yêu cầu.

Đây là cách mô phỏng client chậm có tính xác định. Không cần sleep giữa các lần nhận phần tử.

### Kiểm thử stream RSocket từ requester

Giả sử server cung cấp một route trả về stream:

~~~java
@Controller
class ItemController {

    @MessageMapping("items.watch")
    Flux<Item> watch() {
        return Flux.range(1, 3)
            .map(id -> new Item(id, "item-" + id));
    }
}
~~~

Test phía client có thể điều khiển demand qua **StepVerifier**:

~~~java
Flux<Item> stream = requester
    .route("items.watch")
    .retrieveFlux(Item.class);

StepVerifier.create(stream, 0)
    .thenRequest(1)
    .assertNext(item -> assertEquals(1, item.id()))
    .thenRequest(1)
    .assertNext(item -> assertEquals(2, item.id()))
    .thenRequest(1)
    .assertNext(item -> assertEquals(3, item.id()))
    .verifyComplete();
~~~

RSocket hỗ trợ Reactive Streams semantics cho Request-Stream và Channel, vì vậy demand/backpressure có thể truyền qua ranh giới mạng. Test tích hợp như trên giúp xác nhận behavior của cả requester, responder và transport, thay vì chỉ test một Flux cục bộ.

### Kiểm thử hủy subscription

Client có thể ngừng nhận stream trước khi server hoàn tất. Cần xác nhận cancellation được truyền tới publisher nguồn:

~~~java
@Test
void shouldPropagateCancellation() {
    AtomicBoolean cancelled = new AtomicBoolean();

    Flux<Integer> source = Flux.range(1, 100)
        .doOnCancel(() -> cancelled.set(true));

    StepVerifier.create(source)
        .expectNext(1)
        .thenCancel()
        .verify(Duration.ofSeconds(1));

    assertTrue(cancelled.get());
}
~~~

Trong test tích hợp RSocket, có thể đặt **doOnCancel** ở publisher phía responder và dùng probe/latch để xác nhận server đã nhận cancellation sau khi requester hủy stream.

## 9. Client chậm, buffer và giới hạn tài nguyên

Backpressure giúp điều tiết tốc độ phát và nhận khi mọi thành phần tuân thủ Reactive Streams. Nhưng không phải nguồn dữ liệu nào cũng hỗ trợ demand.

Một số nguồn là hot source hoặc callback API đẩy dữ liệu độc lập với subscriber. Khi producer nhanh hơn consumer, ứng dụng cần quyết định rõ cách xử lý:

- **Buffer:** giữ dữ liệu chờ consumer, nhưng phải giới hạn kích thước và có chính sách overflow.
- **Drop:** loại bỏ dữ liệu mới hoặc cũ theo chính sách phù hợp.
- **Latest:** chỉ giữ giá trị mới nhất khi dữ liệu cũ không còn cần thiết.
- **Reject/fail:** phát lỗi khi vượt giới hạn để bảo vệ tài nguyên.
- **Sample/throttle:** giảm tần suất phát theo yêu cầu nghiệp vụ.

Không dùng buffer không giới hạn để che giấu client chậm. Hàng đợi có thể tăng liên tục và gây hết heap. Nếu sử dụng **onBackpressureBuffer**, hãy chọn capacity hữu hạn và kiểm thử hành vi khi đầy.

Test nên xác nhận:

1. Subscriber demand bằng 0 không làm downstream nhận dữ liệu.
2. Khi tăng demand, dữ liệu được phát theo thứ tự đã cam kết.
3. Cancellation dừng việc phát dữ liệu mới.
4. Buffer không vượt giới hạn.
5. Overflow tạo hành vi đã định nghĩa: drop, error hoặc fallback.
6. Nhiều subscriber chậm không làm cạn tài nguyên toàn hệ thống.

Với Request-Stream và Channel của RSocket, backpressure là một phần của protocol. Với STOMP hoặc một broker không cung cấp cùng semantics end-to-end, cần kiểm tra adapter và broker riêng; không giả định mọi transport đều truyền Reactive Streams demand giống RSocket.

## 10. Kiểm thử timeout và reconnect cùng nhau

Timeout và retry thường được kết hợp, nhưng cần xác định thứ tự operator vì thứ tự ảnh hưởng đến tổng thời gian chờ.

Ví dụ:

~~~java
Mono<Reply> response = requester
    .route("orders.lookup")
    .data(request)
    .retrieveMono(Reply.class)
    .timeout(Duration.ofSeconds(2))
    .retryWhen(
        Retry.fixedDelay(2, Duration.ofMillis(100))
    );
~~~

Trong ví dụ này, mỗi lần subscribe có timeout hai giây; retry có thể thực hiện thêm hai lần sau lần đầu. Tổng thời gian tối đa có thể lớn hơn hai giây vì mỗi attempt có deadline riêng và có delay giữa các lần retry.

Nếu muốn giới hạn tổng thời gian của cả operation, có thể đặt deadline bên ngoài retry:

~~~java
Mono<Reply> response = requester
    .route("orders.lookup")
    .data(request)
    .retrieveMono(Reply.class)
    .timeout(Duration.ofSeconds(2))
    .retryWhen(
        Retry.fixedDelay(2, Duration.ofMillis(100))
    )
    .timeout(Duration.ofSeconds(5));
~~~

Timeout ngoài cùng giới hạn toàn bộ operation, bao gồm các lần retry và khoảng backoff. Cần chọn giá trị phù hợp với deadline nghiệp vụ và kiểm thử cả trường hợp thành công ở lần retry cuối lẫn trường hợp hết deadline.

Khi retry request có tác dụng phụ, hãy dùng idempotency key. Với stream, cần xác định liệu retry sẽ phát lại từ đầu, tiếp tục từ cursor hay không được retry. Không dùng cùng một retry policy cho mọi interaction model mà không xem xét semantics.

## 11. Đồng bộ test tích hợp mà không dùng sleep

Một số tình huống cần chờ thread, listener hoặc broker thật. Có thể sử dụng các công cụ sau:

### CountDownLatch

Phù hợp khi một thread test cần chờ một sự kiện do thread khác báo:

~~~java
CountDownLatch messageHandled = new CountDownLatch(1);

void handle(OrderEvent event) {
    repository.save(event);
    messageHandled.countDown();
}

// Trong test:
sender.send(destination, event);

assertTrue(
    messageHandled.await(5, TimeUnit.SECONDS),
    "Message was not handled within deadline"
);
~~~

Nên đặt latch sau điều kiện mà test muốn xác nhận. Nếu cần xác nhận dữ liệu đã commit, hãy đếm latch sau commit hoặc kiểm tra trạng thái transaction phù hợp.

### Awaitility

Awaitility phù hợp khi test cần đợi một điều kiện eventual, ví dụ số bản ghi trong database tăng lên:

~~~java
await()
    .atMost(Duration.ofSeconds(5))
    .untilAsserted(() ->
        assertEquals(1, repository.count())
    );
~~~

Điều kiện được đánh giá lại cho đến khi thành công hoặc hết deadline. Không cần đoán trước thời gian xử lý bằng một sleep cố định.

### Sinks và probe

**Sinks.One** có thể phát tín hiệu một lần khi một sự kiện xảy ra; **Sinks.Many** có thể lưu hoặc phân phối các tín hiệu test theo cấu hình. **PublisherProbe** và **TestPublisher** trong reactor-test hữu ích khi cần xác nhận nhánh publisher được subscribe, cancel hoặc request.

Chọn công cụ theo sự kiện cần xác nhận. Đừng biến mọi test thành test polling nếu một latch hoặc StepVerifier đã thể hiện chính xác điều kiện.

## 12. Các lỗi thường gặp khi kiểm thử

| Lỗi | Hệ quả | Cách sửa |
|---|---|---|
| Dùng Thread.sleep để chờ message | Test phụ thuộc tốc độ máy và dễ flaky | Chờ tín hiệu hoặc điều kiện với deadline |
| Dùng virtual time cho socket thật | Timer của Netty/broker không nhất thiết được điều khiển bởi Reactor | Dùng thời gian thật có giới hạn cho integration test |
| Tạo publisher trước withVirtualTime | Operator có thể đã giữ scheduler thật | Tạo publisher bên trong supplier |
| Không đặt timeout cho verify | Test có thể treo vô hạn | Dùng verify(Duration) hoặc timeout mặc định |
| Retry mọi exception | Lặp lại lỗi vĩnh viễn và gây tải thêm | Filter lỗi tạm thời |
| Không có idempotency key | Request có thể thực thi trùng sau reconnect | Thiết kế xử lý idempotent |
| Nghĩ reconnect tự phát lại request | Request đang chạy có thể đã thất bại | Retry request có kiểm soát |
| Nhầm reconnect với resume | Hiểu sai khả năng tiếp tục stream | Kiểm tra hỗ trợ và cấu hình resume ở cả hai phía |
| Dùng sleep để làm client chậm | Không kiểm soát được demand | Dùng StepVerifier với initial request bằng 0 |
| Buffer không giới hạn | Có nguy cơ tăng bộ nhớ vô hạn | Đặt capacity và overflow policy |
| Test chỉ kiểm tra client | Bỏ sót cancellation/backpressure ở responder | Thêm probe hoặc assertion phía server |
| Retry stream mà không có cursor | Phát lại dữ liệu đã nhận | Dùng sequence/offset và deduplication |

## 13. Checklist trước khi phát hành

- [ ] Timeout được phân biệt rõ: connect, response, inactivity và overall deadline.
- [ ] Test timeout dùng Virtual Time khi operator hỗ trợ scheduler ảo.
- [ ] Publisher được tạo bên trong **withVirtualTime** supplier.
- [ ] Mọi **verify** đều có giới hạn thời gian thật.
- [ ] Retry policy có số lần thử, backoff và filter lỗi rõ ràng.
- [ ] Request có tác dụng phụ được bảo vệ bằng idempotency.
- [ ] Reconnect và resume được hiểu đúng theo khả năng của RSocket.
- [ ] Có integration test ngắt và khôi phục kết nối RSocket.
- [ ] Có tín hiệu xác nhận connection mới thay vì sleep.
- [ ] Slow client được mô phỏng bằng demand/backpressure.
- [ ] Cancellation được xác nhận ở cả requester và responder khi cần.
- [ ] Buffer có giới hạn và overflow policy được kiểm thử.
- [ ] Có test cho request thành công, timeout, retry thành công và retry hết hạn.
- [ ] Không có Thread.sleep tùy ý trong các test đồng bộ messaging.

## 14. Tài liệu tham khảo

- [Project Reactor Reference: Testing](https://projectreactor.io/docs/core/release/reference/testing.html) — StepVerifier, virtual time, thenAwait và kiểm thử tín hiệu.
- [Project Reactor API: StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html) — API điều khiển demand, subscription và verification timeout.
- [Project Reactor API: Retry](https://projectreactor.io/docs/core/release/api/reactor/util/retry/Retry.html) — fixed delay, exponential backoff và retry policy.
- [Spring Framework Reference: RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html) — RSocketRequester, connector configuration, interaction models và backpressure.
- [RSocket Java: RSocketConnector](https://github.com/rsocket/rsocket-java/blob/master/rsocket-core/src/main/java/io/rsocket/core/RSocketConnector.java) — reconnect policy và khác biệt với session resume.
- [Awaitility](https://github.com/awaitility/awaitility) — chờ điều kiện bất đồng bộ với deadline trong integration test.
